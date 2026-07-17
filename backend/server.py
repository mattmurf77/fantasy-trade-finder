"""
server.py — Fantasy Trade Finder
=================================
Run with:
    pip3 install flask
    python3 server.py

Then open http://127.0.0.1:5000 in your browser.

Set ANTHROPIC_API_KEY in your environment to enable Claude-powered
matchup selection. Without it, the algorithmic fallback is used instead.

Sleeper integration: Users log in with their Sleeper username. Player
data is fetched from the Sleeper public API (no OAuth required).
"""

import collections
import concurrent.futures
import functools
import hashlib
import hmac
import json
import logging
import math
import os
import pathlib
import random
import secrets
import ssl
import threading
import time
import traceback
import uuid
import urllib.error
import urllib.parse
import urllib.request

from datetime import datetime, timedelta, timezone

from flask import Flask, g, jsonify, make_response, request, send_from_directory

# ---------------------------------------------------------------------------
# Logging setup — writes to stdout AND keeps a ring-buffer for /api/debug/log
# ---------------------------------------------------------------------------

logging.basicConfig(
    level   = logging.DEBUG,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%H:%M:%S",
)
log = logging.getLogger("trade_finder")

# Ring-buffer: last 200 log entries exposed via /api/debug/log
_LOG_BUFFER: collections.deque = collections.deque(maxlen=200)


class _BufferHandler(logging.Handler):
    def emit(self, record):
        _LOG_BUFFER.append({
            "ts":    self.formatter.formatTime(record, "%H:%M:%S.%f")[:-3],
            "level": record.levelname,
            "msg":   self.format(record),
        })

_bh = _BufferHandler()
_bh.setFormatter(logging.Formatter("%(levelname)s  %(message)s"))
log.addHandler(_bh)
from .ranking_service import RankingService, Player, TIER_CONFIG, ORDERED_TIERS
from .data_loader import load_consensus_maps, seed_elo_for_players, normalise_name
from .database import (
    init_db,
    upsert_user, upsert_league,
    save_ranking_swipes, save_trade_swipes,
    save_trade_decision, load_swipe_decisions, load_trade_decisions,
    load_recent_league_likes, log_trade_impressions,
    load_trade_decision_shape_counts, load_recent_impression_target_user_counts,
    load_engine_telemetry,
    set_feedback_status, list_feedback_for_user, FEEDBACK_STATUSES, FEEDBACK_SEVERITIES,
    upsert_league_members, upsert_member_rankings,
    load_member_rankings, load_league_members, get_ranking_coverage,
    check_for_match, match_already_exists,
    create_trade_match, load_matches,
    load_awaiting_trades,
    record_match_disposition,
    dismiss_match,
    upsert_league_preference, load_league_preference,
    load_asset_preferences, set_asset_preference, ASSET_PREF_LISTS,
    sync_players, needs_player_sync,
    load_players, load_player, load_players_by_ids,
    load_rookies,
    sync_draft_picks, load_draft_picks,
    create_notification, get_notifications, mark_notifications_read,
    # M5 Push additions — device tokens
    save_device_token, load_device_tokens_for_users,
    # Agent 4 additions — referral receipt helpers
    user_exists, get_user_by_username, push_notification,
    # Agent 5 additions — invite K-factor dashboard
    count_referrals, list_referral_activity,
    get_config, set_config, list_config,
    load_local_leagues_for_user,
    load_local_league_rosters,
    load_local_league_users,
    set_ranking_method, get_ranking_method,
    save_tiers_position, get_tiers_saved,
    save_tier_overrides, load_tier_overrides,
    save_anchor_scale, load_anchor_scale,
    mark_format_unlocked, get_unlocked_formats,
    set_league_scoring, get_league_scoring, get_league_summary,
    set_league_total_rosters,
    # Agent A4 additions — league social features
    load_league_member_unlock_states, load_league_activity,
    SCORING_FORMATS, DEFAULT_SCORING,
    # Trends tab (Agent 2)
    record_elo_snapshot, load_elo_history, load_community_elo_for_league,
    load_user_cross_league_exposure,
    # Player value history (#57 / #17)
    record_value_snapshots, load_value_history, load_value_extremes,
    load_value_snapshot_baseline,
    # Agent 1 additions — user_player_skips helpers
    add_skip as _skip_add,
    load_skips as _skip_load,
    # User-event logging
    record_event, touch_user_activity, load_user_events,
    # Streak — driven by record_event, read for the chip + leaderboard
    get_user_streak,
    # Notification prefs / send log / quiet-hours queue
    get_notification_prefs, upsert_notification_prefs,
    log_notification_send, count_notification_sends_since,
    notification_dedup_sent,
    queue_notification, drain_due_queued_notifications,
    load_pending_matches_older_than, load_unread_match_count,
    load_all_signed_up_users,
    NOTIF_KIND_TO_BUCKET, NOTIF_PREF_DEFAULTS,
    # Leaderboards — read-only aggregations across users / leagues
    load_leaderboard, get_self_leaderboard_row,
    # In-app feedback (TestFlight helper) — POST /api/feedback writes here
    save_feedback,
    # GET /api/feedback/admin — operator readback, CRON_SECRET-protected
    list_feedback,
    # Bad-trade flags (FB #85) — POST /api/trades/flag + admin readback
    save_bad_trade_flag, list_bad_trade_flags,
    # "Send in Sleeper" — encrypted Sleeper write-token storage (flagged beta)
    upsert_sleeper_credential, get_sleeper_credential, delete_sleeper_credential,
)
from . import sleeper_write as _sleeper_write
from . import trade_service as _trade_service_mod
from . import ranking_service as _ranking_service_mod
from . import trends_service as _trends_service_mod
from .feature_flags import FLAGS, is_enabled, flags_dict, reload as reload_flags
from .trade_service import TradeService, TradeCard, League, LeagueMember

# ---------------------------------------------------------------------------
# Demo Player Pool (used until Sleeper roster is loaded)
# ---------------------------------------------------------------------------

DEMO_PLAYERS = [
    # Quarterbacks
    Player("qb_1",  "Lamar Jackson",      "QB", "BAL", 27, 6),
    Player("qb_2",  "Jalen Hurts",         "QB", "PHI", 26, 4),
    Player("qb_3",  "Josh Allen",          "QB", "BUF", 27, 6),
    Player("qb_4",  "CJ Stroud",           "QB", "HOU", 23, 2),
    Player("qb_5",  "Anthony Richardson",  "QB", "IND", 23, 2),
    Player("qb_6",  "Jayden Daniels",      "QB", "WSH", 24, 1),
    Player("qb_7",  "Bo Nix",              "QB", "DEN", 24, 1),
    Player("qb_8",  "Patrick Mahomes",     "QB", "KC",  29, 7),

    # Running Backs
    Player("rb_1",  "Breece Hall",         "RB", "NYJ", 23, 3),
    Player("rb_2",  "Bijan Robinson",      "RB", "ATL", 22, 2),
    Player("rb_3",  "Jahmyr Gibbs",        "RB", "DET", 22, 2),
    Player("rb_4",  "De'Von Achane",       "RB", "MIA", 23, 2),
    Player("rb_5",  "Jonathon Brooks",     "RB", "CAR", 22, 1),
    Player("rb_6",  "Kyren Williams",      "RB", "LAR", 25, 3),
    Player("rb_7",  "Isiah Pacheco",       "RB", "KC",  25, 3),
    Player("rb_8",  "Josh Jacobs",         "RB", "GB",  26, 6),
    Player("rb_9",  "Tony Pollard",        "RB", "TEN", 27, 6),
    Player("rb_10", "Derrick Henry",       "RB", "BAL", 30, 8),

    # Wide Receivers
    Player("wr_1",  "Ja'Marr Chase",       "WR", "CIN", 24, 4),
    Player("wr_2",  "CeeDee Lamb",         "WR", "DAL", 25, 5),
    Player("wr_3",  "Justin Jefferson",    "WR", "MIN", 25, 5),
    Player("wr_4",  "Malik Nabers",        "WR", "NYG", 21, 1),
    Player("wr_5",  "Rome Odunze",         "WR", "CHI", 22, 1),
    Player("wr_6",  "Puka Nacua",          "WR", "LAR", 23, 2),
    Player("wr_7",  "Drake London",        "WR", "ATL", 23, 3),
    Player("wr_8",  "Amon-Ra St. Brown",   "WR", "DET", 24, 4),
    Player("wr_9",  "Stefon Diggs",        "WR", "NE",  31, 10),
    Player("wr_10", "Tyreek Hill",         "WR", "MIA", 30, 9),

    # Tight Ends
    Player("te_1",  "Sam LaPorta",         "TE", "DET", 23, 2),
    Player("te_2",  "Brock Bowers",        "TE", "LV",  22, 1),
    Player("te_3",  "Trey McBride",        "TE", "ARI", 24, 3),
    Player("te_4",  "Dalton Kincaid",      "TE", "BUF", 24, 2),
    Player("te_5",  "Travis Kelce",        "TE", "KC",  35, 12),
    Player("te_6",  "Mark Andrews",        "TE", "BAL", 29, 6),
]

DEMO_USER_ROSTER = ["rb_1", "rb_3", "rb_8", "wr_2", "wr_5", "wr_8", "qb_6", "te_2", "te_4"]
DEMO_USER_ID     = "user_me"

# QC ("quality control") trio throttle — at most one QC trio per
# QC_TRIO_INTERVAL rankings, per (session, position). TestFlight bug #19
# (was probabilistic 1/15 ≈ 6.7% per trio; users reported QC trios firing
# too often; 50 was still too chatty). Operator-set 2026-06-10: 1 per 100.
# Counter lives on the in-memory session dict under
# sess["_qc_counters"]: { position_str: rankings_since_last_qc }.
QC_TRIO_INTERVAL = 100

# ---------------------------------------------------------------------------
# Mutable session state (replaced when a Sleeper league is loaded)
# ---------------------------------------------------------------------------

g_players:      list[Player] = list(DEMO_PLAYERS)
g_user_roster:  list[str]    = list(DEMO_USER_ROSTER)
g_user_id:      str          = DEMO_USER_ID

# ---------------------------------------------------------------------------
# Service setup
# ---------------------------------------------------------------------------

matchup_gen = None
api_key = os.environ.get("ANTHROPIC_API_KEY")
if api_key:
    try:
        from .smart_matchup_generator import SmartMatchupGenerator
        matchup_gen = SmartMatchupGenerator(api_key=api_key)
        print("✅ Claude matchup generator enabled")
    except Exception as e:
        print(f"⚠️  Claude generator unavailable ({e}), using algorithmic fallback")
else:
    print("ℹ️  No ANTHROPIC_API_KEY — using algorithmic matchup selection")

# Load DynastyProcess consensus values as Elo seed. Position-strict name
# matching (#127): the pos map keeps a shared name from seeding across
# positions (Kenneth Walker WR vs Kenneth Walker III RB).
scoring  = os.environ.get("SCORING_FORMAT", "1qb")
elo_map, _demo_vals, _demo_pos = load_consensus_maps(scoring=scoring)
seed     = seed_elo_for_players(DEMO_PLAYERS, elo_map, pos_map=_demo_pos) if elo_map else {}

service = RankingService(players=g_players, matchup_generator=matchup_gen, seed_ratings=seed)

# ---------------------------------------------------------------------------
# Demo league (simulated opponents — used until real league data arrives)
# ---------------------------------------------------------------------------

def _biased_elo(player_ids: list[str], base_seed: dict, biases: dict) -> dict[str, float]:
    """Apply per-player biases to consensus Elo to simulate distinct opinions."""
    result = {}
    for pid in player_ids:
        base  = base_seed.get(pid, 1500)
        delta = biases.get(pid, 0)
        result[pid] = max(1100, min(1900, base + delta))
    return result


def _biased_elo_random(player_ids: list[str], base_seed: dict) -> dict[str, float]:
    """Apply random biases to simulate personal Elo opinions."""
    result = {}
    for pid in player_ids:
        base  = base_seed.get(pid, 1500)
        delta = random.uniform(-120, 120)
        result[pid] = max(1100, min(1900, base + delta))
    return result


def _build_demo_league(players: list[Player], base_seed: dict) -> tuple[League, list[str]]:
    """Build the simulated demo league from a player pool."""
    all_ids = [p.id for p in players]

    # Simulated rosters — if pool is small, distribute evenly
    n = len(all_ids)
    chunk = max(1, n // 5)

    rosters_map = {
        "opp_1": all_ids[0:chunk],
        "opp_2": all_ids[chunk:chunk*2],
        "opp_3": all_ids[chunk*2:chunk*3],
        "opp_4": all_ids[chunk*3:chunk*4],
    }
    # user gets the remainder
    user_roster = all_ids[chunk*4:]

    if not user_roster:          # edge case: very small pool
        user_roster = all_ids[:chunk]

    # Hard-code biases only for the original DEMO_PLAYERS IDs; random for others
    static_biases = {
        "opp_1": {"rb_9":+90, "te_5":+80, "wr_9":+70, "rb_5":+50,
                  "rb_1":-60, "wr_3":-50, "qb_2":-40},
        "opp_2": {"rb_10":+100,"wr_10":+70, "te_6":+60,
                  "rb_2":-70,  "wr_1":-50,  "qb_4":-40, "te_2":-50},
        "opp_3": {"wr_2":+80, "wr_4":+70, "wr_8":+60,
                  "rb_3":-80, "rb_7":-70, "qb_5":-30},
        "opp_4": {"qb_3":+90, "qb_7":+80, "qb_8":+70,
                  "te_4":-80, "te_5":-70, "rb_4":-40},
    }

    members = [
        LeagueMember(
            user_id     = uid,
            username    = name,
            roster      = rosters_map[uid],
            elo_ratings = _biased_elo(
                rosters_map[uid],
                base_seed,
                static_biases.get(uid, {}),
            ),
            # Demo league: simulated opinions count as rankings so the
            # trade-engine v2 ranked-opponent gate leaves demo unchanged.
            has_rankings = True,
        )
        for uid, name in [
            ("opp_1", "DynastyKing"),
            ("opp_2", "RookieDrafter"),
            ("opp_3", "VetHeavy"),
            ("opp_4", "WRCorner"),
        ]
        if rosters_map[uid]
    ]

    league = League(
        league_id = "league_demo",
        name      = "The Demo League",
        platform  = "demo",
        members   = members,
    )
    return league, user_roster


demo_league, demo_roster = _build_demo_league(g_players, seed)
# Override with the hand-crafted demo roster if using demo players
if g_players == DEMO_PLAYERS:
    g_user_roster = list(DEMO_USER_ROSTER)

g_league    = demo_league
trade_service = TradeService(players={p.id: p for p in g_players})
trade_service.add_league(g_league)

# ---------------------------------------------------------------------------
# Database — create tables once on startup
# ---------------------------------------------------------------------------

init_db()
log.info("✅ Database initialised")

# Load runtime config from DB into both service modules
_trade_service_mod.reload_config()
_ranking_service_mod.reload_config()
log.info("✅ Model config loaded from DB")

# ---------------------------------------------------------------------------
# Sleeper player cache (large ~5MB payload — cached to disk)
# ---------------------------------------------------------------------------

CACHE_DIR          = pathlib.Path(__file__).parent.parent / "data"
# FTF_PLAYERS_CACHE_FILE: UI-test harness redirect. The default path is shared
# with real dev usage, so test runs must never write it (docs/plans/mobile-testing/prd.md R-06).
_players_cache_override = os.environ.get("FTF_PLAYERS_CACHE_FILE")
PLAYERS_CACHE_FILE = (pathlib.Path(_players_cache_override) if _players_cache_override
                      else CACHE_DIR / ".sleeper_players_cache.json")
_sleeper_cache: dict | None = None   # in-memory cache


def _load_sleeper_cache() -> dict | None:
    """Load Sleeper player data from disk cache if available."""
    global _sleeper_cache
    if _sleeper_cache is not None:
        return _sleeper_cache
    if PLAYERS_CACHE_FILE.exists():
        try:
            data = json.loads(PLAYERS_CACHE_FILE.read_text())
            _sleeper_cache = data
            print(f"✅ Loaded Sleeper player cache ({len(data)} players) from disk")
            return data
        except Exception as e:
            print(f"⚠️  Could not read Sleeper cache ({e})")
    return None


def _make_ssl_context() -> ssl.SSLContext:
    """
    Return an SSL context for outbound HTTPS calls.

    On macOS with a python.org Python install the bundled SSL library often
    cannot locate the system CA bundle, causing CERTIFICATE_VERIFY_FAILED.
    We try a verified context first; if that's unavailable we fall back to
    an unverified one and log a clear warning.  This is acceptable for a
    local dev tool calling a known-good public API.
    """
    try:
        ctx = ssl.create_default_context()
        # Quick self-test: if the cert store is empty, fall through to fallback
        if ctx.verify_mode == ssl.CERT_REQUIRED:
            return ctx
    except Exception:
        pass

    log.warning(
        "SSL certificate store unavailable — falling back to unverified HTTPS. "
        "Fix permanently by running: "
        "/Applications/Python*/Install\\ Certificates.command"
    )
    ctx = ssl._create_unverified_context()
    return ctx


# Build once at import time; reused for every Sleeper call
_SSL_CTX = _make_ssl_context()

# ---------------------------------------------------------------------------
# UI-test harness seams (docs/plans/mobile-testing/lld.md §4.3). Every branch
# below is dead unless the FTF_* env vars are set; backend/tests/
# test_test_support.py asserts inertness (guardrail G5).
# ---------------------------------------------------------------------------
_TEST_MODE            = os.environ.get("FTF_TEST_MODE") == "1"
_SLEEPER_FIXTURES_DIR = os.environ.get("FTF_SLEEPER_FIXTURES_DIR")
_SLEEPER_RECORD       = os.environ.get("FTF_SLEEPER_RECORD") == "1"

if _TEST_MODE and not (_SLEEPER_FIXTURES_DIR and _players_cache_override
                       and os.environ.get("FTF_DP_VALUES_FILE")):
    raise SystemExit(
        "FTF_TEST_MODE=1 requires FTF_SLEEPER_FIXTURES_DIR, FTF_PLAYERS_CACHE_FILE and "
        "FTF_DP_VALUES_FILE — a test-mode backend that can reach live Sleeper/DynastyProcess "
        "or write the real players cache is a rails hole (prd.md R-12).")
if _SLEEPER_RECORD and _TEST_MODE:
    raise SystemExit("FTF_SLEEPER_RECORD is deliberately live — it cannot run with FTF_TEST_MODE=1.")
if _SLEEPER_RECORD and _SLEEPER_FIXTURES_DIR and any(
        pathlib.Path(_SLEEPER_FIXTURES_DIR).glob("**/*.json")):
    raise SystemExit(
        "FTF_SLEEPER_RECORD=1 refuses a fixtures dir that already contains cassettes — "
        "never silently overwrite; move or delete them first.")


def _sleeper_fixture_path(url: str) -> pathlib.Path:
    rel = url.split("api.sleeper.app/v1/", 1)[1].split("?", 1)[0].strip("/")
    return pathlib.Path(_SLEEPER_FIXTURES_DIR) / f"{rel}.json"


def _sleeper_record(url: str, data) -> None:
    """Record-mode cassette write, with token-bearing fields scrubbed by key name."""
    def scrub(obj):
        if isinstance(obj, dict):
            return {k: ("__scrubbed__" if "token" in k.lower() else scrub(v))
                    for k, v in obj.items()}
        if isinstance(obj, list):
            return [scrub(v) for v in obj]
        return obj
    path = _sleeper_fixture_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scrub(data), indent=1))
    log.info("sleeper-record WROTE %s", path)


def _sleeper_get(url: str, timeout: int = 15) -> dict | list:
    """Fetch JSON from Sleeper API with full request/response logging."""
    global _SSL_CTX  # may be replaced on first SSL failure
    if _SLEEPER_FIXTURES_DIR and not _SLEEPER_RECORD:
        # Fixture seam: serve canned JSON; a miss is a test bug, never a live call.
        from . import test_support as _ts
        fpath = _sleeper_fixture_path(url)
        if not fpath.exists():
            _ts.counters["vcr_misses"] += 1
            log.error("sleeper-fixture MISS %s (wanted %s)", url, fpath)
            raise urllib.error.HTTPError(url, 599, "ftf-fixture-miss", None, None)
        doc = json.loads(fpath.read_text())
        log.info("sleeper-fixture HIT %s", url)
        if isinstance(doc, dict) and "__http_error__" in doc:
            raise urllib.error.HTTPError(url, int(doc["__http_error__"]), "fixture", None, None)
        return doc
    if _TEST_MODE:
        # Unreachable given the startup rules; belt-and-braces rail counter.
        from . import test_support as _ts
        _ts.counters["sleeper_live_egress_attempts"] += 1
    log.info("→ Sleeper GET  %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "FantasyTradeFinder/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            status = r.status
            raw    = r.read()
        preview = raw[:200].decode("utf-8", errors="replace")
        log.info("← Sleeper %s  body_preview=%r  body_len=%d", status, preview, len(raw))
        data = json.loads(raw)
        log.debug("   parsed type=%s", type(data).__name__)
        if _SLEEPER_RECORD and _SLEEPER_FIXTURES_DIR:
            _sleeper_record(url, data)
        return data
    except ssl.SSLCertVerificationError as e:
        # Verified context failed at runtime — retry once with unverified
        log.warning("SSL verification failed (%s) — retrying without verification", e)
        _SSL_CTX = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            status = r.status
            raw    = r.read()
        preview = raw[:200].decode("utf-8", errors="replace")
        log.info("← Sleeper (unverified) %s  body_preview=%r  body_len=%d", status, preview, len(raw))
        data = json.loads(raw)
        if _SLEEPER_RECORD and _SLEEPER_FIXTURES_DIR:
            _sleeper_record(url, data)
        return data
    except urllib.error.HTTPError as e:
        body_preview = e.read(200).decode("utf-8", errors="replace")
        log.warning("← Sleeper HTTPError %s %s  body=%r", e.code, e.reason, body_preview)
        raise
    except urllib.error.URLError as e:
        log.error("← Sleeper URLError: %s", e.reason)
        raise
    except Exception as e:
        log.error("← Sleeper unexpected error: %s", e)
        raise


# ---------------------------------------------------------------------------
# Player DB sync helpers
# ---------------------------------------------------------------------------

def _fetch_sleeper_adp() -> dict:
    """
    Try to fetch ADP data from the undocumented Sleeper ADP endpoint.
    Returns {player_id: float} or {} on any failure.

    The endpoint (https://api.sleeper.app/v1/players/nfl/adp) is not
    officially documented; if unavailable, ADP is stored as None.
    """
    url = "https://api.sleeper.app/v1/players/nfl/adp"
    try:
        log.info("→ Fetching Sleeper ADP …")
        raw = _sleeper_get(url, timeout=10)
        adp_map: dict = {}
        if isinstance(raw, dict):
            for pid, val in raw.items():
                if isinstance(val, (int, float)):
                    adp_map[str(pid)] = float(val)
                elif isinstance(val, dict):
                    # Some formats nest by scoring: {"ppr": 1.2, "standard": 1.5}
                    adp_val = val.get("ppr") or val.get("standard") or val.get("half_ppr")
                    if adp_val is not None:
                        try:
                            adp_map[str(pid)] = float(adp_val)
                        except (TypeError, ValueError):
                            pass
        log.info("  ADP: fetched %d entries", len(adp_map))
        return adp_map
    except Exception as e:
        log.info("  ADP fetch skipped (endpoint unavailable): %s", e)
        return {}


def _parse_league_url(url: str) -> tuple[str | None, str | None]:
    """
    Parse a pasted league URL into (platform, league_id).

    Supported formats:
      - Sleeper: https://sleeper.com/leagues/<18-digit-id>/...
                 https://sleeper.app/leagues/<id>/...
                 Bare 18-digit ID
      - ESPN:    https://fantasy.espn.com/football/league?leagueId=<id>
                 https://fantasy.espn.com/football/team?leagueId=<id>
                 https://fantasy.espn.com/football/league/settings?leagueId=<id>
      - MFL:     https://www47.myfantasyleague.com/2024/home/<5-digit-id>
                 https://www47.myfantasyleague.com/2024/options?L=<id>
                 https://*.myfantasyleague.com/... with ?L=<id>

    Returns (None, None) when the URL can't be recognized.
    """
    import re
    if not url or not isinstance(url, str):
        return None, None
    url = url.strip()

    # Sleeper canonical URL
    m = re.search(r'sleeper\.(?:com|app)/leagues?/(\d{10,})', url)
    if m:
        return "sleeper", m.group(1)

    # Bare Sleeper ID pasted without the URL (currently 15-20 digits)
    if re.match(r'^\d{15,20}$', url):
        return "sleeper", url

    # ESPN Fantasy — leagueId in the query string
    m = re.search(r'fantasy\.espn\.com/.*[?&]leagueId=(\d+)', url, re.IGNORECASE)
    if m:
        return "espn", m.group(1)

    # MFL — /YEAR/home/<id> or /YEAR/options/<id> or similar path-style
    m = re.search(r'myfantasyleague\.com/\d{4}/(?:home|options|standings)/(\d{4,6})', url, re.IGNORECASE)
    if m:
        return "mfl", m.group(1)
    # MFL — ?L=<id> query-style
    m = re.search(r'myfantasyleague\.com/.*[?&]L=(\d{4,6})', url, re.IGNORECASE)
    if m:
        return "mfl", m.group(1)

    return None, None


def _fetch_sleeper_league_meta(league_id: str) -> dict | None:
    """
    Fetch the full league metadata (roster_positions + scoring_settings + settings)
    from Sleeper. Returns the raw dict or None on failure / non-Sleeper league IDs.

    Endpoint: https://api.sleeper.app/v1/league/{league_id}
    """
    if not league_id or not str(league_id).isdigit():
        return None
    url = f"https://api.sleeper.app/v1/league/{league_id}"
    try:
        log.info("→ Fetching Sleeper league meta  league_id=%s", league_id)
        raw = _sleeper_get(url, timeout=10)
        return raw if isinstance(raw, dict) else None
    except Exception as e:
        log.info("  league meta fetch failed: %s", e)
        return None


def _detect_scoring_format_from_meta(meta: dict) -> str:
    """
    Derive our scoring_format key ('1qb_ppr' or 'sf_tep') from a Sleeper league
    metadata dict.

    We only have two format buckets, so the rule is:
      - Superflex present → 'sf_tep' (Superflex is the dominant value-driver;
                                      QB scarcity reshapes the whole ranking)
      - TE Premium present → 'sf_tep' (TE-value distortion makes the TEP
                                       rankings a closer fit than 1QB PPR)
      - Otherwise → '1qb_ppr'

    Superflex detection: roster_positions contains "SUPER_FLEX" (Sleeper's
    canonical marker), or QB slot count ≥ 2 as a fallback.

    TE Premium detection: scoring_settings.bonus_rec_te > 0 (typically 0.5).

    Previously required BOTH conditions, which mis-bucketed SF-without-TEP
    and 1QB-with-TEP leagues into '1qb_ppr'.
    """
    if not isinstance(meta, dict):
        return "1qb_ppr"

    roster_positions = meta.get("roster_positions") or []
    is_superflex = "SUPER_FLEX" in roster_positions
    if not is_superflex:
        qb_count = sum(1 for p in roster_positions if p == "QB")
        is_superflex = qb_count >= 2

    scoring = meta.get("scoring_settings") or {}
    try:
        bonus_rec_te = float(scoring.get("bonus_rec_te") or 0)
    except (TypeError, ValueError):
        bonus_rec_te = 0.0
    is_tep = bonus_rec_te > 0

    return "sf_tep" if (is_superflex or is_tep) else "1qb_ppr"


def _maybe_sync_players() -> None:
    """
    Sync the Sleeper player cache to the players DB table if the table is
    empty or the last sync was more than 24 hours ago.

    Runs at server startup and is a no-op if data is fresh.
    """
    try:
        if not needs_player_sync():
            log.info("✅ Player DB is up-to-date — skipping sync")
            return

        cache = _load_sleeper_cache()
        if cache is None:
            log.info("ℹ️  No Sleeper cache on disk — player DB sync deferred")
            return

        adp_map = _fetch_sleeper_adp()   # {} if endpoint unavailable
        count   = sync_players(cache, adp_map=adp_map or None)
        log.info("✅ Synced %d players to DB%s",
                 count, f"  ({len(adp_map)} with ADP)" if adp_map else "")
    except Exception as e:
        log.warning("Player DB sync failed (non-fatal): %s", e)


# ---------------------------------------------------------------------------
# Universal Player Pool
# ---------------------------------------------------------------------------
# The ranking pool includes ALL Sleeper players that have a Dynasty Process
# value > 0.  Rankings are user-level (not league-specific), so this pool is
# built once and stays constant regardless of which league is selected.
# Trade generation still uses league-specific rosters.
# ---------------------------------------------------------------------------

# DP raw values — loaded per scoring format (two independent rank sets)
# Format keys: '1qb_ppr' and 'sf_tep'. Legacy globals below are aliases that
# always point to the 1qb_ppr pool so existing references keep working.
dp_values_by_format: dict[str, dict[str, float]] = {}   # {fmt: {name: value}}
dp_elo_by_format:    dict[str, dict[str, float]] = {}   # {fmt: {name: elo}}
dp_pos_by_format:    dict[str, dict[str, str]]   = {}   # {fmt: {name: DP pos}} (#127)
g_universal_by_format: dict[str, dict] = {}             # {fmt: {'players': [...], 'seed': {...}}}

# Backwards-compat aliases (default format). These reference the same lists
# as g_universal_by_format['1qb_ppr'] after _ensure_universal_pools runs.
dp_values: dict[str, float] = {}
g_universal_players: list[Player] = []
g_universal_seed: dict[str, float] = {}

# ── Generic draft-pick assets (shared constants) ───────────────────────────
# Elo seeds for the 12 generic Early/Mid/Late picks (rounds 1–4) injected into
# the universal pool, calibrated to typical dynasty trade values. Module-scoped
# because they double as the reference ladder for pick-denominated features:
# the pick-anchor wizard (/api/anchor/save) and the calculator's gap-to-pick
# equivalence (/api/trade/evaluate `gap`). The MID column of each round is the
# canonical "a 1st / a 2nd / …" anchor; a generic Mid 1st is the base unit.
GENERIC_PICK_SEEDS: dict[tuple[int, str], float] = {
    # (round, tier): elo_seed
    (1, "Early"):  1720,   # ~top-3 pick: elite rookie prospect
    (1, "Mid"):    1650,   # ~mid-1st: solid first-round value (BASE FIRST)
    (1, "Late"):   1580,   # ~late-1st: still premium but less certain
    (2, "Early"):  1520,   # ~early-2nd: solid starter potential
    (2, "Mid"):    1460,   # ~mid-2nd: depth/upside piece
    (2, "Late"):   1400,   # ~late-2nd: dart throw
    (3, "Early"):  1360,   # ~early-3rd: longshot upside
    (3, "Mid"):    1320,   # ~mid-3rd: roster filler
    (3, "Late"):   1280,   # ~late-3rd: minimal value
    (4, "Early"):  1260,   # ~early-4th: very speculative
    (4, "Mid"):    1240,   # ~mid-4th: low value
    (4, "Late"):   1220,   # ~late-4th: minimal
}
_PICK_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def generic_pick_label(rnd: int, tier: str) -> str:
    """Display label matching the universal pool's pick naming."""
    return f"{tier} {_PICK_ORDINALS[rnd]} Round Pick"


def _pick_gap_equivalent(gap_value: float) -> dict:
    """
    Express a package-value gap in pick-denominated terms.

    Returns {firsts, pick_equivalent}: `firsts` is the gap in units of a
    generic Mid 1st (the base first), and `pick_equivalent` is the single
    generic pick whose value is nearest the gap — or None when the gap is
    negligible (< half a Mid 4th) or bigger than any single pick (then the
    client leans on `firsts`, e.g. "≈ 2.3 firsts").
    """
    e2v = _trade_service_mod.elo_to_value
    base_first = e2v(GENERIC_PICK_SEEDS[(1, "Mid")])
    firsts = round(gap_value / base_first, 2)

    values = {key: e2v(seed) for key, seed in GENERIC_PICK_SEEDS.items()}
    min_val = min(values.values())
    max_val = max(values.values())
    pick = None
    if gap_value >= min_val * 0.5 and gap_value <= max_val * 1.25:
        (rnd, tier), v = min(
            values.items(), key=lambda kv: abs(kv[1] - gap_value))
        pick = {
            "pick_id": f"generic_pick_{rnd}_{tier.lower()}",
            "label":   generic_pick_label(rnd, tier),
            "value":   round(v, 1),
        }
    return {"firsts": firsts, "pick_equivalent": pick}


# ── Pick-anchor wizard (POST /api/anchor/save) ─────────────────────────────
# Anchor keys are a cross-client enum (mobile sends them verbatim — see
# docs/cross-client-invariants.md). Single-pick anchors pin directly to that
# generic pick's Elo seed; multi-first anchors are VALUE multiples of the
# base first (a generic Mid 1st) mapped back through value_to_elo — a player
# "worth 2 firsts" is a value statement, not an Elo one. "no_value" pins
# below the lowest tier band (→ unranked / no trade value).
ANCHOR_NO_VALUE_ELO = 1100.0
_ANCHOR_SINGLE_PICK = {
    "1_first":  (1, "Mid"),
    "1_second": (2, "Mid"),
    "1_third":  (3, "Mid"),
    "1_fourth": (4, "Mid"),
}
_ANCHOR_FIRST_MULTIPLES = {"4_firsts": 4.0, "3_firsts": 3.0, "2_firsts": 2.0}
VALID_ANCHORS = (
    set(_ANCHOR_FIRST_MULTIPLES) | set(_ANCHOR_SINGLE_PICK) | {"no_value"}
)

# Per-user pick-value scale (#111, re-derived 2026-07-12 for #117): "a
# top-tier asset is worth N firsts". The #117 seed recalibration puts the
# consensus board's top asset at the 4-firsts rung (Elo ≈ 1927), so the
# default math now implies N = 4 — a "4 firsts" answer pins there. A user
# who says N = 2 (or 3) believes firsts are more expensive relative to
# elite players, so their multi-first answers are re-spaced along a power
# curve:  m firsts → value(Mid 1st) × m^γ  with  γ = log 4 / log N.
# The curve is exact at both ends the user can see: m = 1 is still the
# actual generic Mid 1st asset in their pool (Elo 1650), and m = N — the
# user's own definition of a top-tier asset — lands on the same Elo the
# default math gives "4 firsts". N = 4 → γ = 1 → byte-identical to the
# plain m × base mapping (so the default anchor Elos are unchanged by the
# re-derivation). Applies ONLY to the anchor wizard's multi-first keys:
# single-pick anchors, the generic pick assets in the pool, and the
# public calculator gap line stay consensus-denominated.
ANCHOR_TOP_TIER_FIRSTS_DEFAULT = 4.0
ANCHOR_TOP_TIER_FIRSTS_CHOICES = (2.0, 3.0, 4.0)
_ANCHOR_TOP_LADDER_FIRSTS = 4.0   # the ladder's top rung, in firsts


def _anchor_target_elo(
    anchor: str,
    top_tier_firsts: float = ANCHOR_TOP_TIER_FIRSTS_DEFAULT,
) -> float | None:
    """Map an anchor key to its target Elo. None for unknown keys.

    `top_tier_firsts` is the user's pick-value scale (see the comment on
    ANCHOR_TOP_TIER_FIRSTS_DEFAULT); it re-spaces the multi-first anchors
    only. The default reproduces the original mapping exactly.
    """
    if anchor == "no_value":
        return ANCHOR_NO_VALUE_ELO
    if anchor in _ANCHOR_SINGLE_PICK:
        return float(GENERIC_PICK_SEEDS[_ANCHOR_SINGLE_PICK[anchor]])
    mult = _ANCHOR_FIRST_MULTIPLES.get(anchor)
    if mult is None:
        return None
    base_val = _trade_service_mod.elo_to_value(GENERIC_PICK_SEEDS[(1, "Mid")])
    gamma = math.log(_ANCHOR_TOP_LADDER_FIRSTS) / math.log(top_tier_firsts)
    return _trade_service_mod.value_to_elo((mult ** gamma) * base_val)


def build_universal_pool(
    sleeper_cache: dict | None = None,
    dp_elo: dict[str, float] | None = None,
    dp_vals: dict[str, float] | None = None,
    all_db_players: list | None = None,
    dp_pos: dict[str, str] | None = None,
) -> tuple[list[Player], dict[str, float]]:
    """
    Build the universal ranking pool: every Sleeper player that has a
    DynastyProcess value > 0.

    Returns (players, seed_ratings) where seed_ratings maps player.id → elo.

    ``all_db_players`` is the pre-loaded players-table scan, passed in by the
    caller so it is read once and reused across both format builds (instead of
    re-querying the full table per format). When None, falls back to loading it
    here so direct callers still work.

    ``dp_pos`` ({normalised name: DP position}, from load_consensus_maps)
    makes the DP↔Sleeper name join position-strict (#127): several NFL
    players share a normalised name (Kenneth Walker WR vs Kenneth Walker III
    RB), and without the position check every Sleeper namesake inherited the
    one DP row's value and entered the pool — a duplicate at the wrong
    position. When None (legacy callers), the join stays name-only.
    """
    if not sleeper_cache or not dp_vals:
        return [], {}

    players: list[Player] = []
    seeds: dict[str, float] = {}
    seen_ids: set[str] = set()

    # Use the enriched DB records passed in by the caller (loaded once and
    # reused across formats); only hit the DB here if none were provided.
    try:
        if all_db_players is None:
            all_db_players = load_players(position=None)
        db_by_id = {str(p["player_id"]): p for p in all_db_players} if all_db_players else {}
    except Exception:
        db_by_id = {}

    for pid, p_data in sleeper_cache.items():
        pid_str = str(pid)
        if pid_str in seen_ids:
            continue

        pos = (p_data.get("position") or "").upper()
        if pos not in VALID_POSITIONS:
            continue

        full_name = p_data.get("full_name") or ""
        if not full_name:
            continue

        # Check if this player has a DP value > 0
        # The DP_TO_SLEEPER_NAME reference table has already been applied
        # inside _fetch_dynasty_process, so dp_vals keys use Sleeper names.
        # Exact match only — no fuzzy fallback.
        normed = normalise_name(full_name)
        if normed not in dp_vals:
            continue  # no DP value → skip

        # #127 — never name-match across positions: the DP row's position
        # must agree with the Sleeper player's, or a namesake at another
        # position (Kenneth Walker WR) silently inherits the value meant
        # for the real asset (Kenneth Walker III, RB).
        if dp_pos is not None and dp_pos.get(normed) != pos:
            continue

        seen_ids.add(pid_str)

        # Build Player — prefer enriched DB record if available
        db_row = db_by_id.get(pid_str)
        if db_row:
            players.append(Player(
                id                   = pid_str,
                name                 = db_row.get("full_name") or full_name,
                position             = pos,
                team                 = db_row.get("team") or p_data.get("team") or "FA",
                age                  = db_row.get("age") or int(p_data.get("age") or 0) or 25,
                years_experience     = db_row.get("years_exp") or int(p_data.get("years_exp") or 0),
                depth_chart_position = db_row.get("depth_chart_position"),
                depth_chart_order    = db_row.get("depth_chart_order"),
                injury_status        = db_row.get("injury_status"),
                injury_body_part     = db_row.get("injury_body_part"),
                birth_date           = db_row.get("birth_date"),
                height               = db_row.get("height"),
                weight               = db_row.get("weight"),
                college              = db_row.get("college"),
                search_rank          = db_row.get("search_rank"),
                adp                  = db_row.get("adp"),
            ))
        else:
            players.append(Player(
                id               = pid_str,
                name             = full_name,
                position         = pos,
                team             = p_data.get("team") or "FA",
                age              = int(p_data.get("age") or 0) or 25,
                years_experience = int(p_data.get("years_exp") or 0),
            ))

        # Seed Elo from DP data
        if dp_elo and normed in dp_elo:
            seeds[pid_str] = dp_elo[normed]
        else:
            seeds[pid_str] = 1500.0

    # ── Generic draft pick assets ────────────────────────────────────
    # Add Early/Mid/Late picks for rounds 1–4 as universal rankable assets.
    # These are generic (not league-specific) and let users rank draft capital
    # against players. Elo seeds live at module scope (GENERIC_PICK_SEEDS)
    # because the anchor wizard + calculator gap equivalence share them.
    # Distribute generic picks across position tabs so they mix in with players
    _PICK_POS = {1: "RB", 2: "WR", 3: "TE", 4: "QB"}

    for (rnd, tier), seed_elo in GENERIC_PICK_SEEDS.items():
        pick_id = f"generic_pick_{rnd}_{tier.lower()}"
        label   = generic_pick_label(rnd, tier)
        pick_pos = _PICK_POS.get(rnd, "QB")

        # Compute a pick_value that matches the Elo seed (inverse of 1200 + pv*6)
        pv = max(0, (seed_elo - 1200) / 6)

        players.append(Player(
            id               = pick_id,
            name             = label,
            position         = pick_pos,
            team             = "PICK",
            age              = 0,
            years_experience = 0,
            pick_value       = round(pv, 1),
            search_rank      = {1: 10, 2: 50, 3: 100, 4: 200}.get(rnd, 200),
        ))
        seeds[pick_id] = seed_elo

    log.info("✅ Universal player pool: %d players with DP value > 0 + %d generic picks",
             len(players) - len(GENERIC_PICK_SEEDS), len(GENERIC_PICK_SEEDS))
    return players, seeds


def _ensure_universal_pools() -> None:
    """Build the universal pool for BOTH scoring formats (idempotent).

    Each format gets its own player list + seed map so 1QB PPR and SF TEP
    rank sets stay completely independent.
    """
    global g_universal_players, g_universal_seed, dp_values

    if g_universal_by_format.get("1qb_ppr") and g_universal_by_format.get("sf_tep"):
        return  # both built

    cache = _load_sleeper_cache()
    if cache is None:
        return

    from .data_loader import SCORING_FORMATS as DL_SCORING_FORMATS

    # Read the enriched players table ONCE and reuse it across both format
    # builds, instead of re-scanning the full table inside each build.
    try:
        all_db_players = load_players(position=None)
    except Exception:
        all_db_players = None

    # The per-format DynastyProcess CSV fetches are independent network calls.
    # Run the two formats concurrently so the build phase isn't bottlenecked on
    # serial round-trips. Each task loads that format's values + elo maps.
    # A fetch failure inside load_consensus_* is already handled gracefully by
    # data_loader (returns {} → flat-Elo baseline), so a failing format yields
    # empty maps rather than raising; we still guard the future result here so
    # one format's failure can never block or break the other.
    def _load_format_dp(fmt: str) -> tuple[dict[str, float], dict[str, float], dict[str, str]]:
        # Single fetch per format via load_consensus_maps — also yields the
        # DP position map that makes the pool join position-strict (#127).
        elo, vals, pos = load_consensus_maps(scoring=fmt)
        return vals, elo, pos

    pending = [
        fmt for fmt in DL_SCORING_FORMATS
        if fmt not in g_universal_by_format
        and (fmt not in dp_values_by_format or fmt not in dp_elo_by_format
             or fmt not in dp_pos_by_format)
    ]
    if pending:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(pending)) as ex:
            future_to_fmt = {ex.submit(_load_format_dp, fmt): fmt for fmt in pending}
            for future in concurrent.futures.as_completed(future_to_fmt):
                fmt = future_to_fmt[future]
                try:
                    vals, elo, pos = future.result()
                except Exception as e:
                    log.warning("  DP fetch failed for %s (%s) — flat-Elo baseline", fmt, e)
                    vals, elo, pos = {}, {}, {}
                dp_values_by_format.setdefault(fmt, vals)
                dp_elo_by_format.setdefault(fmt, elo)
                dp_pos_by_format.setdefault(fmt, pos)

    for fmt in DL_SCORING_FORMATS:
        if fmt in g_universal_by_format:
            continue
        players, seed = build_universal_pool(
            sleeper_cache=cache,
            dp_elo=dp_elo_by_format.get(fmt, {}),
            dp_vals=dp_values_by_format.get(fmt, {}),
            all_db_players=all_db_players,
            dp_pos=dp_pos_by_format.get(fmt),
        )
        g_universal_by_format[fmt] = {"players": players, "seed": seed}
        log.info("  universal pool built for %s: %d players", fmt, len(players))

    # Maintain backwards-compat aliases pointing at the default 1qb_ppr pool
    default = g_universal_by_format.get("1qb_ppr", {})
    g_universal_players[:] = default.get("players", [])
    g_universal_seed.clear()
    g_universal_seed.update(default.get("seed", {}))
    dp_values.clear()
    dp_values.update(dp_values_by_format.get("1qb_ppr", {}))


# Legacy single-pool entry point kept for any external callers. Calls through
# to the dual-pool version.
def _ensure_universal_pool() -> None:
    _ensure_universal_pools()


def _get_universal_pool(scoring_format: str) -> tuple[list[Player], dict[str, float]]:
    """Return (players, seed) for a given scoring format. Builds on demand."""
    _ensure_universal_pools()
    pool = g_universal_by_format.get(scoring_format) or g_universal_by_format.get("1qb_ppr") or {}
    return pool.get("players", []), pool.get("seed", {})


# ---------------------------------------------------------------------------
# Consensus positional ranks + 30d trend (FB4-61 tile stats)
# ---------------------------------------------------------------------------
# A player's consensus positional rank = their 1-based rank within their
# position by consensus seed Elo over the format's universal pool. The 30d
# trend compares that rank against the oldest in-window player_value_history
# snapshot (daily cron #57). Both inputs change at most once per UTC day
# (pool rebuild on boot + daily snapshot), so results are memoised per
# (format, day).
# ---------------------------------------------------------------------------

# fmt → (utc_date, pos_rank_map, pos_rank_delta_map)
_consensus_rank_cache: dict[str, tuple[str, dict, dict]] = {}


def _consensus_pos_ranks(scoring_format: str) -> tuple[dict[str, int], dict[str, int]]:
    """({pid: consensus_pos_rank}, {pid: 30d rank delta, + = moved UP}).

    The delta map only carries players present in the baseline snapshot —
    absent players (or no accrued history at all) simply have no trend, and
    clients omit the glyph.
    """
    from .trends_service import compute_consensus_pos_ranks
    today  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cached = _consensus_rank_cache.get(scoring_format)
    if cached and cached[0] == today:
        return cached[1], cached[2]
    players, seed = _get_universal_pool(scoring_format)
    players_by_id = {p.id: {"position": p.position} for p in players}
    baseline = load_value_snapshot_baseline(scoring_format=scoring_format, days=30)
    out = compute_consensus_pos_ranks(seed, baseline, players_by_id)
    _consensus_rank_cache[scoring_format] = (today, out["pos_rank"], out["pos_rank_delta"])
    return out["pos_rank"], out["pos_rank_delta"]


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

_PROJECT_ROOT = pathlib.Path(__file__).parent.parent
app = Flask(__name__, static_folder=str(_PROJECT_ROOT / "web"), static_url_path="")

# ---------------------------------------------------------------------------
# Session store — multi-user support
# Each session: {user_id, league, players, user_roster, service, trade_svc,
#                display_name, last_active}
# ---------------------------------------------------------------------------

_sessions: dict[str, dict] = {}  # token → per-session dict
_sessions_lock = threading.Lock()  # guards all _sessions reads/writes

if _TEST_MODE:
    # UI-test harness blueprint (/__test__/*) — see backend/test_support.py.
    from . import test_support as _test_support_mod
    _test_support_mod.install(app, sessions=_sessions, sessions_lock=_sessions_lock)
_player_sync_lock = threading.Lock()  # serialises concurrent player DB syncs

# ─── Trade-generation jobs (streaming + pre-gen cache) ────────────────────
# Each job represents one /api/trades/generate run. The actual work is done
# by a background daemon thread; the request thread returns immediately with
# a job_id so the mobile app can poll /api/trades/status. The same dict
# doubles as a cache: a complete job younger than _PREGEN_TTL_SECONDS is
# returned instantly to the next caller for the same (user, league, format).
#
# Job state shape:
#   {
#     "job_id":               str,
#     "key":                  (user_id, league_id, scoring_format),
#     "status":               "running" | "complete" | "error",
#     "started_at":           float (time.monotonic),
#     "finished_at":          float | None,
#     "opponents_done":       int,
#     "opponents_total":      int,
#     "cards":                list[dict],     # public trade_card_to_dict shape
#     "error":                str | None,
#     "fairness_threshold":   float,
#     "outlook_value":        str | None,
#     "is_pinned":            bool,           # pinned-give jobs are never cached
#   }
_trade_jobs: dict[str, dict] = {}                     # job_id → state
_trade_jobs_by_key: dict[tuple, str] = {}             # (uid,lid,fmt) → job_id
_trade_jobs_lock = threading.Lock()
_PREGEN_TTL_SECONDS  = 1800   # 30 min — fresh cache window
_JOB_HARD_TIMEOUT    = 60     # seconds — past this a stuck job is marked error
_JOB_RETENTION       = 4 * 3600  # keep finished jobs around for ~4hr cleanup


class _SessionExpired(Exception):
    pass


@app.errorhandler(_SessionExpired)
def handle_session_expired(e):
    return jsonify({"error": "session_expired",
                    "message": "Session expired — please reload the page."}), 401


class _SessionNotInitialized(Exception):
    pass


@app.errorhandler(_SessionNotInitialized)
def handle_session_not_initialized(e):
    return jsonify({"error": "session_not_initialized",
                    "message": "League data is still loading — "
                               "try again in a moment."}), 409


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    log.exception("Unhandled error on %s %s", request.method, request.path)
    return jsonify({"error": "internal_error",
                    "message": "Unexpected server error."}), 500


def _require_session() -> dict:
    """Return the active session dict, or raise _SessionExpired (→ 401).

    Also resolves the "effective format" for this request and syncs the
    sess['service'] / sess['trade_svc'] aliases to match. Priority for the
    effective format:
      1. X-Scoring-Format request header (per-call override, no state change)
      2. sess['active_format'] (set by /api/scoring/switch)
      3. '1qb_ppr' default

    The header path is useful when the frontend wants to peek at one
    format's data without changing the user's active view.
    """
    token = request.headers.get("X-Session-Token", "")
    with _sessions_lock:
        sess = _sessions.get(token)
    if sess is None:
        raise _SessionExpired()

    # Resolve effective format for this single request
    from .database import SCORING_FORMATS as DB_SCORING_FORMATS
    header_fmt = request.headers.get("X-Scoring-Format", "")
    if header_fmt in DB_SCORING_FORMATS:
        effective_format = header_fmt
    else:
        effective_format = sess.get("active_format") or "1qb_ppr"

    # Sync aliases so legacy endpoints that read sess['service'] / sess['trade_svc']
    # automatically get the right format's instance for this request.
    services = sess.get("services") or {}
    trade_svcs = sess.get("trade_svcs") or {}
    if effective_format in services:
        sess["service"] = services[effective_format]
    if effective_format in trade_svcs:
        sess["trade_svc"] = trade_svcs[effective_format]
    sess["_effective_format"] = effective_format

    return sess


def _require_initialized_session() -> dict:
    """Like _require_session, but also requires /api/session/init to have
    completed for this token (league / players / trade services present).

    Mobile sign-in (INIT-08) mints a session via /api/extension/auth and
    navigates to Main BEFORE /api/session/init finishes, so any league-backed
    route can be hit with a valid-but-bare session. Routes that index
    sess["league"] / sess["players"] / sess["trade_svc"] must use this helper
    so that window returns a structured 409 instead of KeyError → 500.
    (Same failure class as the FB-01 disposition bug.)
    """
    sess = _require_session()
    if ("league" not in sess or "players" not in sess
            or not (sess.get("trade_svcs") or sess.get("trade_svc"))):
        raise _SessionNotInitialized()
    return sess


def _active_format(sess: dict) -> str:
    """Return the format that `_require_session` resolved for this request."""
    return sess.get("_effective_format") or sess.get("active_format") or "1qb_ppr"


# ---------------------------------------------------------------------------
# Verified-session write gate — account-auth plan P1
# (docs/plans/account-auth-plan-2026-07-11.md §3-P1)
#
# A session becomes VERIFIED when the mobile app captures a Sleeper JWT
# whose user_id claim matches the session's user_id AND the token is proven
# live against Sleeper's authenticated API (POST /api/sleeper/link — the
# oracle probe closes the unverified-signature gap in plan §2c). Verified
# state is stamped on the session (sess["verified"]) and persisted on the
# users row (verified_at / verified_via='sleeper', shared with P2's
# Apple/Google anchors via backend/accounts.py).
#
# Decision matrix for a mutating request (also in docs/api-reference.md):
#   session verified                    → allow
#   unverified + user has a verified
#     controller (users.verified_via)   → 403 verification_required
#                                         (first-verified-controller-wins,
#                                         even during grace)
#   unverified, no controller, grace
#     (auth.enforce_verified_writes=F)  → allow + one AUTH-GRACE log line
#   unverified, no controller, enforce  → 403 verification_required
#
# The two highest-blast-radius routes never use this gate's grace path:
# POST /api/sleeper/link carries its own proof inline, and POST
# /api/trades/propose requires sess["verified"] outright.
# ---------------------------------------------------------------------------

_MUTATING_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def _verified_controller_via(user_id: str) -> str | None:
    """users.verified_via for this user_id — the persisted "someone proved
    control of this account" marker. Shared by the write and read gates.

    Returns None on a DB hiccup (fail open + log): both gates treat an
    unreadable marker as no-controller rather than locking every session
    out on a transient DB error.
    """
    try:
        from . import accounts as _accounts
        return _accounts.get_user_verified_via(user_id)
    except Exception as e:
        log.warning("verified-controller lookup failed for %s: %s", user_id, e)
        return None


def _verified_write_denial(sess: dict):
    """Return a Flask (response, status) to DENY this write, or None to allow.

    Assumes `sess` is a live session dict. Reads users.verified_via for
    unverified sessions so a squatter loses write access the moment the real
    owner verifies — no restart or session expiry needed.
    """
    if sess.get("verified"):
        return None
    user_id = sess.get("user_id") or ""
    controller_via = _verified_controller_via(user_id)
    if controller_via:
        log.warning("AUTH-DENY unverified_write user_id=%s method=%s path=%s "
                    "reason=verified_controller_exists via=%s",
                    user_id, request.method, request.path, controller_via)
        return jsonify({"error": "verification_required"}), 403
    if is_enabled("auth.enforce_verified_writes"):
        log.warning("AUTH-DENY unverified_write user_id=%s method=%s path=%s "
                    "reason=enforcement", user_id, request.method, request.path)
        return jsonify({"error": "verification_required"}), 403
    # Grace: allowed but instrumented. ONE stable line format — the runbook's
    # grace-funnel monitoring greps for "AUTH-GRACE" (docs/runbook.md).
    log.info("AUTH-GRACE unverified_write user_id=%s method=%s path=%s",
             user_id, request.method, request.path)
    return None


def _gate_unverified_write(fn):
    """Route decorator applying `_verified_write_denial` to mutating methods.

    Stack UNDER @app.route (so Flask registers the wrapped function). Reads
    the session directly by token; a missing/expired session falls through
    to the route's own _require_session → 401, keeping error contracts
    unchanged. GETs on mixed-method routes pass through untouched.
    """
    @functools.wraps(fn)
    def _wrapper(*args, **kwargs):
        if request.method in _MUTATING_METHODS:
            with _sessions_lock:
                sess = _sessions.get(request.headers.get("X-Session-Token", ""))
            if sess is not None:
                denial = _verified_write_denial(sess)
                if denial is not None:
                    return denial
        return fn(*args, **kwargs)
    return _wrapper


# ---------------------------------------------------------------------------
# Verified-session READ gate — account-auth plan P2.5 (read privacy)
# (docs/plans/account-auth-plan-2026-07-11.md §"P2.5")
#
# "Ranks hidden behind an account" (#102) means reads too: without this, an
# attacker with just a username can mint a session and VIEW the victim's
# board even though the write gate blocks mutation. The read rule mirrors
# the write rule's verified-controller branch ONLY:
#
#   session verified                    → allow
#   unverified + user has a verified
#     controller (users.verified_via)   → 403 verification_required
#                                         (no grace — the owner has proven
#                                         control; squatters get nothing)
#   unverified, no controller           → allow (grace-era behavior:
#                                         onboarding users must be able to
#                                         see their own board)
#
# auth.enforce_verified_writes is deliberately NOT consulted here:
# enforcement hard-denies writes, but a user mid-onboarding (no controller
# anywhere) must still see their own board or nobody could ever onboard.
# ---------------------------------------------------------------------------


def _verified_read_denial(sess: dict):
    """Return a Flask (response, status) to DENY this board-content read,
    or None to allow. Same per-request users.verified_via check as the
    write gate, so a squatter loses read access the moment the real owner
    verifies — no restart or session expiry needed.
    """
    if sess.get("verified"):
        return None
    user_id = sess.get("user_id") or ""
    controller_via = _verified_controller_via(user_id)
    if controller_via:
        log.warning("AUTH-DENY unverified_read user_id=%s method=%s path=%s "
                    "reason=verified_controller_exists via=%s",
                    user_id, request.method, request.path, controller_via)
        return jsonify({"error": "verification_required"}), 403
    return None


def _gate_unverified_read(fn):
    """Route decorator applying `_verified_read_denial` to non-mutating
    methods. Board-content READ routes only (gated-read matrix in
    docs/api-reference.md) — global/public data (/api/players,
    /api/trade/values, /api/tier-config, share pages) and league-shared
    aggregates stay open. Stack UNDER @app.route; on mixed GET+POST routes
    stack alongside @_gate_unverified_write (each filters to its own
    methods, so nothing is double-checked or double-logged). A missing or
    expired session falls through to the route's own _require_session →
    401, keeping error contracts unchanged.
    """
    @functools.wraps(fn)
    def _wrapper(*args, **kwargs):
        if request.method not in _MUTATING_METHODS:
            with _sessions_lock:
                sess = _sessions.get(request.headers.get("X-Session-Token", ""))
            if sess is not None:
                denial = _verified_read_denial(sess)
                if denial is not None:
                    return denial
        return fn(*args, **kwargs)
    return _wrapper


def _cleanup_loop() -> None:
    """Background thread: evict stale sessions + stuck/old trade jobs."""
    while True:
        time.sleep(300)  # check every 5 min

        # Sessions — 4hr inactivity
        cutoff = time.time() - 4 * 3600
        with _sessions_lock:
            stale = [t for t, s in _sessions.items()
                     if s.get("last_active", 0) < cutoff]
            for t in stale:
                _sessions.pop(t, None)
        if stale:
            log.info("Cleaned up %d stale session(s)", len(stale))

        # Trade jobs — three reasons to evict:
        #   (a) running jobs older than _JOB_HARD_TIMEOUT → mark as error so
        #       the frontend stops polling
        #   (b) finished jobs older than _JOB_RETENTION → drop entirely
        #   (c) keep _trade_jobs_by_key in sync with _trade_jobs
        now = time.monotonic()
        evicted = 0
        timed_out = 0
        with _trade_jobs_lock:
            to_drop = []
            for jid, job in _trade_jobs.items():
                age = now - (job.get("finished_at") or job.get("started_at") or now)
                if job.get("status") == "running" and (now - job.get("started_at", now)) > _JOB_HARD_TIMEOUT:
                    job["status"] = "error"
                    job["error"]  = "timeout"
                    job["finished_at"] = now
                    timed_out += 1
                if age > _JOB_RETENTION:
                    to_drop.append(jid)
            for jid in to_drop:
                key = _trade_jobs[jid].get("key")
                _trade_jobs.pop(jid, None)
                if key and _trade_jobs_by_key.get(key) == jid:
                    _trade_jobs_by_key.pop(key, None)
                evicted += 1
        if evicted or timed_out:
            log.info("Trade jobs swept: %d evicted, %d timed out", evicted, timed_out)


threading.Thread(target=_cleanup_loop, daemon=True).start()


# ---------------------------------------------------------------------------
# Device-info + activity middleware
# ---------------------------------------------------------------------------
# Reads the client's device snapshot from request headers (set by mobile/web
# clients on every API call) and stashes it on flask.g so request handlers
# and record_event() callers can read it cheaply. Also bumps the user's
# last_active_at + device snapshot columns when a session token is present.
#
# Headers (all optional — old clients that don't send them just no-op):
#   X-Device       — 'iphone' | 'ipad' | 'macos' | 'web' | 'extension'
#   X-OS-Version   — '17.4' | '18.1' | etc.
#   X-App-Version  — semver string '1.2.3'
#
# We deliberately do NOT write a user_events row per request — that would
# be O(requests) writes. App-open events are fired explicitly from the
# session-create flow; per-request we only bump the cheap denorm column.
#
# That denorm bump (touch_user_activity → UPDATE users) is throttled per
# session: at most one write per TOUCH_THROTTLE_S, so a poll storm (e.g.
# /api/trades/status at 1.5s) collapses to ≤1 write/min/user. last_active_at
# is a coarse "last seen" pointer (see database.py touch_user_activity); ~1min
# staleness is acceptable. Discrete actions still write precise user_events rows.
TOUCH_THROTTLE_S = 60  # min seconds between per-session last_active_at writes


def _device_info_from_request() -> dict:
    return {
        "device_type": request.headers.get("X-Device") or None,
        "os_version":  request.headers.get("X-OS-Version") or None,
        "app_version": request.headers.get("X-App-Version") or None,
    }


@app.before_request
def _stash_device_and_touch_activity() -> None:
    info = _device_info_from_request()
    g.device_info = info
    # IANA tz from the client (e.g. 'America/New_York'). Powers local-day
    # streak math in record_event(). Not part of device_info because it's
    # neither device-shaped nor written to users.last_device_*.
    g.user_tz = request.headers.get("X-User-TZ") or None
    # Only bump activity if a valid session is attached. We resolve user_id
    # without raising — _require_session would 401 here, which is wrong for
    # endpoints that don't require auth (login, static, demo, etc.).
    token = request.headers.get("X-Session-Token", "")
    if not token:
        return
    with _sessions_lock:
        sess = _sessions.get(token)
    if not sess:
        return
    user_id = sess.get("user_id")
    if not user_id:
        return
    # Throttle the synchronous UPDATE users write: skip it unless the in-session
    # last_active pointer is at least TOUCH_THROTTLE_S old. A fresh session has
    # no 'last_active' yet → the .get(...) default of 0 makes the first request
    # always touch. Collapses poll storms into ≤1 write/min/user.
    now = time.time()
    if now - sess.get("last_active", 0) < TOUCH_THROTTLE_S:
        return
    try:
        touch_user_activity(user_id, **info)
        # Record the write only after it's dispatched, so a failed touch doesn't
        # suppress the next attempt for a full TOUCH_THROTTLE_S window.
        sess["last_active"] = now
    except Exception:
        pass  # never break the request on activity logging



# ─── Trade-job helpers (streaming + pre-gen) ─────────────────────────────

def _trade_job_key(user_id: str, league_id: str, scoring_format: str) -> tuple:
    return (user_id, league_id, scoring_format)


def _trade_job_public_view(job: dict) -> dict:
    """Shape returned to the mobile app by /api/trades/generate + /status.
    Hides internal-only fields like the cache key."""
    return {
        "job_id":          job["job_id"],
        "status":          job["status"],
        "opponents_done":  job["opponents_done"],
        "opponents_total": job["opponents_total"],
        "cards":           job.get("cards") or [],
        "error":           job.get("error"),
    }


def _trade_job_is_fresh(job: dict, fairness_threshold: float, outlook_value) -> bool:
    """True iff this job's result can be returned as-is to a new caller —
    i.e. it's complete, recent, and was generated for the same parameters."""
    if job.get("status") != "complete":
        return False
    if job.get("is_pinned"):
        return False
    if (time.monotonic() - (job.get("finished_at") or 0)) > _PREGEN_TTL_SECONDS:
        return False
    # Allow ±0.01 wiggle on threshold — frontend may round
    if abs((job.get("fairness_threshold") or 0) - fairness_threshold) > 0.01:
        return False
    if (job.get("outlook_value") or None) != (outlook_value or None):
        return False
    return True


def _make_progress_cb(job_id: str, players_dict: dict, real_user_ids: set, outlook_value):
    """Build a callback that snapshots cards into _trade_jobs[job_id] as
    each opponent finishes. Pre-binds the players_dict + outlook so the
    closure can run inside the worker thread without re-reading session state."""
    def _cb(opponents_done: int, opponents_total: int, sorted_cards):
        # Convert internal TradeCard objects → public dicts (same shape as
        # /api/trades/matches enrichment uses).
        snapshot = []
        for c in sorted_cards:
            d = trade_card_to_dict(c, players_dict)
            d["real_opponent"] = c.target_user_id in real_user_ids
            d["outlook"]       = outlook_value
            snapshot.append(d)
        with _trade_jobs_lock:
            j = _trade_jobs.get(job_id)
            if j and j["status"] == "running":
                j["opponents_done"]  = opponents_done
                j["opponents_total"] = opponents_total
                j["cards"]           = snapshot
    return _cb


# ─── Tier 2 (2.3) — likes-you queue + fuzzy mirror helpers ────────────────
# Flags read via getattr so server keeps working until the orchestrator
# registers "trade.likes_you" / "trade.fuzzy_match" in feature_flags.FLAG_KEYS
# (FLAGS raises AttributeError for unknown attrs; getattr defaults to False).

def _likes_you_enabled() -> bool:
    return getattr(FLAGS, "trade_likes_you", False)


def _fuzzy_match_enabled() -> bool:
    return getattr(FLAGS, "trade_fuzzy_match", False)


def _fuzzy_match_tau() -> float:
    """model_config key 'fuzzy_match_tau' (default 0.8), read through
    trade_service's live config dict so database.py stays config-free.
    Defensive: a missing key or import problem can never break the swipe path."""
    try:
        from .trade_service import _cfg as _ts_cfg
        return float(_ts_cfg.get("fuzzy_match_tau", 0.8))
    except Exception:
        return 0.8


_LIKES_YOU_CAP = 3   # max likes-you injections per generated deck


def _inject_likes_you_cards(
    cards: list,
    trade_service,
    user_id: str,
    league_id: str,
    league,
    user_roster: list,
    seed_map: dict,
    untouchable_ids: set | None = None,
) -> list:
    """Tier 2 work item 2.3a — surface trades the counterparty already liked.

    Queries league-mates' 'like' decisions (90 days) that are still
    actionable (their give ⊆ their current roster, their receive ⊆ the
    user's current roster) and mirrors each into the user's perspective:
    give = their_receive, receive = their_give, target = that opponent.

    - If an equivalent card (same give/receive sets, same opponent) already
      exists in the generated deck: flag likes_you=True and boost its
      composite_score to max(existing)+1.0 so it sorts to the top.
    - Otherwise synthesize a consensus-basis TradeCard (fairness from summed
      seed elo per side — deliberately simple; the card's pull is "they
      already want this", not its score) and give it the same boost.
    - At most _LIKES_YOU_CAP injections; trades the user already swiped on
      (past_decision_keys) are skipped.

    Returns the deck re-sorted by composite_score descending. Synthesized
    cards are registered in trade_service._trade_cards so /api/trades/swipe
    can resolve them by trade_id.
    """
    likes = load_recent_league_likes(
        league_id=league_id, exclude_user_id=user_id, days=90,
    )
    if not likes:
        return cards

    members_by_id   = {m.user_id: m for m in league.members}
    user_roster_set = set(user_roster)
    boost_score     = round(max((c.composite_score for c in cards), default=0.0) + 1.0, 3)
    existing_by_key = {
        (frozenset(c.give_player_ids), frozenset(c.receive_player_ids), c.target_user_id): c
        for c in cards
    }

    injected  = 0
    seen_keys = set()
    new_cards = []
    for like in likes:
        if injected >= _LIKES_YOU_CAP:
            break
        opp = members_by_id.get(like["user_id"])
        if opp is None or opp.user_id == user_id:
            continue
        their_give = like["give_player_ids"]
        their_recv = like["receive_player_ids"]
        if not their_give or not their_recv:
            continue
        # Still actionable? Rosters change — their give must still be theirs,
        # their receive must still be on the user's roster.
        if not set(their_give) <= set(opp.roster):
            continue
        if not set(their_recv) <= user_roster_set:
            continue
        # Backlog #2 / feedback #95 — untouchables never leave the user's
        # roster, even when the counterparty already liked the mirror. Their
        # receive side IS the user's give side after mirroring.
        if untouchable_ids and set(their_recv) & untouchable_ids:
            continue

        my_give, my_recv = list(their_recv), list(their_give)
        key = (frozenset(my_give), frozenset(my_recv), opp.user_id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        # Don't resurface a trade the user already swiped on.
        if (key[0], key[1]) in trade_service._past_decision_keys:
            continue

        existing = existing_by_key.get(key)
        if existing is not None:
            existing.likes_you       = True
            existing.composite_score = boost_score
            injected += 1
            continue

        give_val = sum(seed_map.get(pid, 1500.0) for pid in my_give)
        recv_val = sum(seed_map.get(pid, 1500.0) for pid in my_recv)
        fairness = (round(min(give_val, recv_val) / max(give_val, recv_val), 3)
                    if give_val > 0 and recv_val > 0 else 0.0)
        card = TradeCard(
            trade_id           = f"likesyou_{uuid.uuid4().hex[:12]}",
            league_id          = league_id,
            proposing_user_id  = user_id,
            target_user_id     = opp.user_id,
            target_username    = opp.username,
            give_player_ids    = my_give,
            receive_player_ids = my_recv,
            mismatch_score     = 0.0,
            fairness_score     = fairness,
            composite_score    = boost_score,
            basis              = "consensus",
            likes_you          = True,
        )
        trade_service._trade_cards[card.trade_id] = card
        new_cards.append(card)
        injected += 1

    if injected == 0:
        return cards
    return sorted(new_cards + cards, key=lambda c: c.composite_score, reverse=True)


# ─── Tier 2 amendments A5 + A6 — deck ordering helpers ───────────────────
# A5 (flag trade.thompson_deck): Thompson-sample a Beta posterior of the
# user's like-rate per card bucket and scale each card's sort key by the
# sampled probability. Works at n≈0 decisions, keeps the deck from serving
# the same cards in the same order forever, and generates the exploration
# data the future learned acceptance model (2.4) needs.
#
# Bucket choice: package_shape only — f"{len(give)}x{len(receive)}" ("1x1",
# "2x1", …). It is the ONLY card feature derivable from BOTH a live card
# and a historical trade_decisions row (basis / likes_you live only on
# trade_impressions; joining impressions→decisions on give/receive sets is
# fragile and the data volume — 20 decisions — doesn't justify it). One
# Beta sample per bucket per job, so cards in the same bucket keep their
# relative composite order; cross-bucket inversions are bounded by the
# (0.5, 1.5) multiplier.
#
# A6 (flag trade.deck_diversity): a player can only be traded once, so one
# stud saturating every league member's deck caps total possible matches.
# Cards whose top receive asset already appeared in >= diversity_user_cap
# OTHER members' recent decks get their key multiplied by diversity_penalty,
# and the served deck keeps at most deck_max_per_target cards per target
# (never dropping likes_you cards, never shrinking below _DECK_MIN_CARDS).

_DECK_MIN_CARDS = 5   # intra-deck cap never shrinks the deck below this


def _thompson_deck_enabled() -> bool:
    return getattr(FLAGS, "trade_thompson_deck", False)


def _deck_diversity_enabled() -> bool:
    return getattr(FLAGS, "trade_deck_diversity", False)


def _deck_cfg(key: str, default: float) -> float:
    """model_config key via trade_service's live config dict (same pattern
    as _fuzzy_match_tau). Defaults inline so a missing key never breaks
    the trade path. Keys are also declared in trade_service._DEFAULT_CFG."""
    try:
        from .trade_service import _cfg as _ts_cfg
        return float(_ts_cfg.get(key, default))
    except Exception:
        return float(default)


def _deck_rng_seed(user_id: str, league_id: str, job_id: str) -> int:
    """Deterministic per-job RNG seed — re-polls of the same job (and a
    re-run of the same job id in tests) see a stable order. hashlib, not
    hash(): Python salts str hashes per process."""
    digest = hashlib.sha256(f"{user_id}|{league_id}|{job_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _card_shape(card) -> str:
    give = getattr(card, "give_player_ids", None) or []
    recv = getattr(card, "receive_player_ids", None) or []
    return f"{len(give)}x{len(recv)}"


def _top_receive_asset(card, seed_map: dict) -> str | None:
    """The card's most valuable receive asset by consensus (seed) value —
    the 'target' for diversification purposes. Falls back to the first
    receive id when seed values are missing (all tie at 1500)."""
    recv = getattr(card, "receive_player_ids", None) or []
    if not recv:
        return None
    return max(recv, key=lambda pid: seed_map.get(pid, 1500.0))


def _cap_per_target(ordered: list, seed_map: dict, max_per: int) -> list:
    """A6 intra-deck cap: at most `max_per` cards per top receive asset,
    keeping the best (the deck is already sorted). Edge cases: likes_you
    cards are never dropped (they still occupy a slot in the count); if
    dropping would shrink the deck below _DECK_MIN_CARDS, the best dropped
    cards are restored (in their original positions)."""
    if len(ordered) <= _DECK_MIN_CARDS or max_per <= 0:
        return ordered
    kept, dropped = [], []
    per_target: dict = {}
    for c in ordered:
        pid = _top_receive_asset(c, seed_map)
        if (pid is not None
                and per_target.get(pid, 0) >= max_per
                and not getattr(c, "likes_you", False)):
            dropped.append(c)
            continue
        if pid is not None:
            per_target[pid] = per_target.get(pid, 0) + 1
        kept.append(c)
    # Never serve a deck thinner than _DECK_MIN_CARDS because of the cap.
    while len(kept) < _DECK_MIN_CARDS and dropped:
        kept.append(dropped.pop(0))   # dropped[] is still in deck (score) order
    if len(kept) < len(ordered):
        original_pos = {id(c): i for i, c in enumerate(ordered)}
        kept.sort(key=lambda c: original_pos[id(c)])
    return kept


def _order_deck(
    cards: list,
    *,
    user_id: str,
    league_id: str,
    job_id: str,
    seed_map: dict,
) -> list:
    """Apply A5 (Thompson ordering) and A6 (diversification) to a generated
    deck. Returns a new list; the input is never mutated. Both flags off →
    the input list is returned untouched. Likes-you cards stay pinned to
    the top regardless of sampling or penalties."""
    thompson  = _thompson_deck_enabled()
    diversity = _deck_diversity_enabled()
    if not cards or not (thompson or diversity):
        return cards

    key = {id(c): float(getattr(c, "composite_score", 0.0) or 0.0) for c in cards}

    if thompson:
        rng = random.Random(_deck_rng_seed(user_id, league_id, job_id))
        try:
            shape_counts = load_trade_decision_shape_counts(user_id, league_id)
        except Exception as e:
            log.warning("thompson deck: shape counts unavailable: %s", e)
            shape_counts = {}
        sample_by_shape: dict[str, float] = {}
        # Sample shapes in sorted order so the draw sequence (hence the
        # ordering) doesn't depend on the incoming card order.
        for shape in sorted({_card_shape(c) for c in cards}):
            likes, passes = shape_counts.get(shape, (0, 0))
            # Beta(1 + likes, 2 + passes): exploration-friendly prior that
            # still expects passes (mean 1/3 at n=0).
            sample_by_shape[shape] = rng.betavariate(1 + likes, 2 + passes)
        for c in cards:
            # Bounded multiplier in (0.5, 1.5) — exploration reorders across
            # buckets but never fully inverts quality.
            key[id(c)] *= 0.5 + sample_by_shape[_card_shape(c)]

    if diversity:
        user_cap = int(_deck_cfg("diversity_user_cap", 3))
        penalty  = _deck_cfg("diversity_penalty", 0.6)
        window   = int(_deck_cfg("diversity_window_days", 7))
        try:
            target_counts = load_recent_impression_target_user_counts(
                league_id, exclude_user_id=user_id, days=window,
            )
        except Exception as e:
            log.warning("deck diversity: impression counts unavailable: %s", e)
            target_counts = {}
        if target_counts:
            for c in cards:
                pid = _top_receive_asset(c, seed_map)
                if pid is not None and target_counts.get(pid, 0) >= user_cap:
                    key[id(c)] *= penalty

    ordered = sorted(
        cards,
        key=lambda c: (bool(getattr(c, "likes_you", False)), key[id(c)]),
        reverse=True,
    )

    if diversity:
        ordered = _cap_per_target(ordered, seed_map, int(_deck_cfg("deck_max_per_target", 3)))

    return ordered


def _user_pick_share(user_id: str, league_id: str) -> float:
    """The user's share of total draft-pick value in a league (0.0 when no
    picks synced). Feeds the #8 outlook seed and #1's classifier."""
    try:
        picks = load_draft_picks(league_id=league_id)
    except Exception:
        return 0.0
    grand = sum((pk.get("pick_value") or 0.0) for pk in picks)
    if grand <= 0:
        return 0.0
    mine = sum((pk.get("pick_value") or 0.0) for pk in picks
               if pk.get("owner_user_id") == user_id)
    return mine / grand


def _infer_user_outlook(user_id: str, league_id: str, sess: dict, league):
    """Backlog #8 — infer the USER's own contend/rebuild window from their
    roster, for leagues with no declared outlook. Returns (outlook, signals)
    or (None, None) when the seed flag is off or roster/player data is absent.

    Called from BOTH the generate-route cache pre-read and the worker so the
    cache-freshness key resolves identically on both sides.
    """
    if not FLAGS.trade_outlook_seed:
        return None, None
    roster  = (sess or {}).get("user_roster") or []
    players = (sess or {}).get("players") or []
    if not roster or not players:
        return None, None
    from .trade_service import infer_team_outlook
    pdict = {p.id: p for p in players}
    num_teams = len(league.members) if league and getattr(league, "members", None) else 12
    outlook, _score, signals = infer_team_outlook(
        roster, pdict, _user_pick_share(user_id, league_id), num_teams)
    return outlook, signals


def _run_trade_job(
    job_id: str,
    sess_token: str,
    league_id: str,
    fairness_threshold: float,
    pinned_give: list,
    pinned_receive: list | None = None,
):
    """Daemon-thread entry point. Resolves the session itself (rather than
    capturing closures over per-request state) so the request that kicked
    us off can return immediately. All exceptions caught — a thread death
    here would leave the job 'running' forever, which is a worse failure
    than surfacing the error to the polling frontend."""
    try:
        with _sessions_lock:
            sess = _sessions.get(sess_token)
        if not sess:
            raise RuntimeError("session expired before trade job started")

        # Resolve format-scoped service. Mirrors the resolution path used by
        # /api/trades/generate's request handler — see _require_session.
        active_format  = sess.get("_effective_format") or sess.get("active_format") or "1qb_ppr"
        services       = sess.get("services") or {}
        trade_svcs     = sess.get("trade_svcs") or {}
        service        = services.get(active_format) or sess.get("service")
        trade_service  = trade_svcs.get(active_format) or sess.get("trade_svc")
        g_user_id      = sess["user_id"]
        g_league       = sess.get("league")
        g_user_roster  = sess.get("user_roster")
        g_players      = sess.get("players")
        if not (service and trade_service and g_league
                and g_user_roster and g_players):
            raise RuntimeError("session missing required state for trade gen")

        user_elo   = service.get_rankings(position=None)
        elo_map_rt = {rp.player.id: rp.elo for rp in user_elo.rankings}
        seed_map   = service._seed or {}

        # Inject real leaguemate ELOs (same logic as /api/trades/generate)
        real_count = 0
        real_user_ids: set = set()
        try:
            real_rankings = load_member_rankings(
                league_id=league_id, exclude_user_id=g_user_id,
                scoring_format=active_format,
            )
            if real_rankings:
                for member in g_league.members:
                    if member.user_id in real_rankings:
                        rd = real_rankings[member.user_id]
                        ue = dict(rd["elo_ratings"])
                        if ue:
                            member.elo_ratings = ue
                            member.username    = rd["username"] or member.username
                            # Trade-engine v2: mark members whose values come
                            # from real member_rankings rows (vs. seed/sim).
                            member.has_rankings = True
                            real_count += 1
                real_user_ids = set(real_rankings.keys()) if real_count else set()
        except Exception as db_err:
            log.warning("trade-job: could not load real rankings: %s", db_err)

        # Outlook + positional preferences
        outlook_value        = None
        acquire_positions    = []
        trade_away_positions = []
        try:
            prefs = load_league_preference(user_id=g_user_id, league_id=league_id)
            if prefs:
                outlook_value        = prefs.get("team_outlook")
                acquire_positions    = prefs.get("acquire_positions",    []) or []
                trade_away_positions = prefs.get("trade_away_positions", []) or []
        except Exception as pref_err:
            log.warning("trade-job: could not load league preference: %s", pref_err)

        # Backlog #8 — no declared outlook ⇒ seed from the user's own roster
        # (flag-gated). Must mirror the generate-route pre-read exactly so the
        # job-cache freshness key agrees.
        if not outlook_value:
            seeded, _sig = _infer_user_outlook(g_user_id, league_id, sess, g_league)
            if seeded:
                outlook_value = seeded

        # Update outlook on the job for cache freshness checks
        with _trade_jobs_lock:
            j = _trade_jobs.get(job_id)
            if j is not None:
                j["outlook_value"] = outlook_value

        # Backlog #1 — opponent outlook inputs. Only assembled when the flag
        # is on (avoids per-member DB reads on the default path). Declared
        # outlooks come from each member's stored league preference; pick
        # shares come from draft_picks. The engine fills any gap by inferring
        # from roster shape.
        opponent_outlooks: dict[str, str] = {}
        opponent_pick_shares: dict[str, float] = {}
        if FLAGS.trade_outlook_infer:
            try:
                for m in g_league.members:
                    if m.user_id == g_user_id:
                        continue
                    mp = load_league_preference(user_id=m.user_id, league_id=league_id)
                    if mp and mp.get("team_outlook"):
                        opponent_outlooks[m.user_id] = mp["team_outlook"]
                picks = load_draft_picks(league_id=league_id)
                totals: dict[str, float] = {}
                grand = 0.0
                for pk in picks:
                    owner = pk.get("owner_user_id")
                    pv = pk.get("pick_value") or 0.0
                    if owner:
                        totals[owner] = totals.get(owner, 0.0) + pv
                    grand += pv
                if grand > 0:
                    opponent_pick_shares = {u: t / grand for u, t in totals.items()}
            except Exception as outlook_err:
                log.warning("trade-job: opponent outlook assembly failed: %s", outlook_err)

        # Backlog #2 — asset preference lists (untouchables + targets). Loaded
        # only when the flag is on. Sets flow into the engine as a give-side
        # hard filter (untouchables) + a receive-side reward (targets).
        untouchable_ids: set = set()
        target_ids: set = set()
        if FLAGS.trade_preference_lists:
            try:
                ap = load_asset_preferences(user_id=g_user_id, league_id=league_id)
                untouchable_ids = set(ap.get("untouchables", []))
                target_ids = set(ap.get("targets", []))
            except Exception as ap_err:
                log.warning("trade-job: asset prefs load failed: %s", ap_err)

        players_dict = {p.id: p for p in g_players}
        progress_cb  = _make_progress_cb(job_id, players_dict, real_user_ids, outlook_value)

        # Per-player comparison counts for the requesting user — feeds the
        # v2 confidence-shrinkage step (Tier 1, Change 4). None when the
        # session has no ranking service for this format.
        confidence_counts = service.comparison_counts() if service else None

        final_cards = trade_service.generate_trades(
            user_id              = g_user_id,
            user_elo             = elo_map_rt,
            user_roster          = g_user_roster,
            league_id            = league_id,
            seed_elo             = seed_map,
            confidence           = confidence_counts,
            outlook              = outlook_value,
            fairness_threshold   = fairness_threshold,
            acquire_positions    = acquire_positions,
            trade_away_positions = trade_away_positions,
            pinned_give_players  = pinned_give or None,
            pinned_receive_players = pinned_receive or None,
            scoring_format       = active_format,
            on_opponent_done     = progress_cb,
            opponent_outlooks    = opponent_outlooks or None,
            opponent_pick_shares = opponent_pick_shares or None,
            untouchable_ids      = untouchable_ids or None,
            target_ids           = target_ids or None,
        )

        # Tier 2 (2.3a) — likes-you queue. Inject/boost cards league-mates
        # already liked the mirror of, then republish the final snapshot so
        # the served deck includes them. Non-fatal: a failure here serves
        # the organic deck exactly as before. Skipped for pinned-give decks
        # ("what can I get for X?") — unrelated injections would pollute them.
        if (_likes_you_enabled() and league_id != "league_demo"
                and not pinned_give and not pinned_receive):
            try:
                final_cards = _inject_likes_you_cards(
                    cards         = final_cards,
                    trade_service = trade_service,
                    user_id       = g_user_id,
                    league_id     = league_id,
                    league        = g_league,
                    user_roster   = g_user_roster,
                    seed_map      = seed_map,
                    untouchable_ids = untouchable_ids or None,
                )
                snapshot = []
                for c in final_cards:
                    d = trade_card_to_dict(c, players_dict)
                    d["real_opponent"] = c.target_user_id in real_user_ids
                    d["outlook"]       = outlook_value
                    snapshot.append(d)
                with _trade_jobs_lock:
                    j = _trade_jobs.get(job_id)
                    if j is not None and j["status"] == "running":
                        j["cards"] = snapshot
            except Exception as ly_err:
                log.warning("likes-you injection failed (non-fatal): %s", ly_err)

        # Tier 2 amendments A5 + A6 — Thompson-sampled ordering + league-wide
        # diversification. Runs AFTER likes-you injection (so pinning sees
        # the final likes_you flags) and BEFORE impression logging (so
        # trade_impressions records true served positions). Deterministically
        # seeded per job, so /status re-polls see a stable order. Non-fatal:
        # any failure serves the deck exactly as generated.
        if league_id != "league_demo" and (_thompson_deck_enabled() or _deck_diversity_enabled()):
            try:
                ordered = _order_deck(
                    final_cards,
                    user_id   = g_user_id,
                    league_id = league_id,
                    job_id    = job_id,
                    seed_map  = seed_map,
                )
                if [id(c) for c in ordered] != [id(c) for c in final_cards]:
                    final_cards = ordered
                    snapshot = []
                    for c in final_cards:
                        d = trade_card_to_dict(c, players_dict)
                        d["real_opponent"] = c.target_user_id in real_user_ids
                        d["outlook"]       = outlook_value
                        snapshot.append(d)
                    with _trade_jobs_lock:
                        j = _trade_jobs.get(job_id)
                        if j is not None and j["status"] == "running":
                            j["cards"] = snapshot
            except Exception as ord_err:
                log.warning("deck ordering (A5/A6) failed (non-fatal): %s", ord_err)

        # Tier 2 (2.4) — impression logging: one row per card in final deck
        # order, once per completed job (NOT per /status poll — polls only
        # read the stored snapshot). This is the training-data pipeline for
        # the future acceptance model. Never allowed to break generation.
        try:
            if league_id != "league_demo":
                log_trade_impressions(g_user_id, league_id, final_cards)
        except Exception as imp_err:
            log.warning("trade impression logging failed (non-fatal): %s", imp_err)

        # Mark complete. Final card snapshot was already published by the
        # last on_opponent_done invocation (or the likes-you republish above).
        with _trade_jobs_lock:
            j = _trade_jobs.get(job_id)
            if j is not None:
                j["status"]      = "complete"
                j["finished_at"] = time.monotonic()

    except Exception as e:
        log.exception("trade-job %s failed", job_id)
        with _trade_jobs_lock:
            j = _trade_jobs.get(job_id)
            if j is not None:
                j["status"]      = "error"
                j["error"]       = str(e)
                j["finished_at"] = time.monotonic()


def _invalidate_trade_jobs(*, user_id: str, league_id: str | None = None) -> int:
    """Drop cached trade jobs so the next /api/trades/generate kicks off
    a fresh run. Two scopes:
      - league_id=None: drop all of this user's jobs (used after /api/rank3
        — user ELOs just changed, so trades for any league are stale).
      - league_id=...: drop only that league's job (used after a league
        preferences POST — only this league's outlook changed).

    Doesn't touch in-flight 'running' jobs — those will publish their
    final result and be flushed by the next call. We only remove the
    `_trade_jobs_by_key` index entry so the next request creates a new
    job instead of reusing the stale one.
    """
    dropped = 0
    with _trade_jobs_lock:
        for key in list(_trade_jobs_by_key.keys()):
            uid, lid, _fmt = key
            if uid != user_id:
                continue
            if league_id is not None and lid != league_id:
                continue
            jid = _trade_jobs_by_key.get(key)
            job = _trade_jobs.get(jid) if jid else None
            # Only drop the index pointer for completed/errored jobs;
            # leave running jobs alone so concurrent /generate calls don't
            # wastefully spawn duplicates while the worker is still going.
            if job and job.get("status") != "running":
                _trade_jobs_by_key.pop(key, None)
                dropped += 1
    return dropped


def _kickoff_trade_job(
    sess_token: str,
    user_id: str,
    league_id: str,
    scoring_format: str,
    fairness_threshold: float = 0.75,
    pinned_give: list | None = None,
    pinned_receive: list | None = None,
    opponents_total: int | None = None,
) -> str:
    """Register a new job in _trade_jobs and start its worker thread.
    Returns the job_id. Caller is responsible for any pre-existing-job
    deduplication; this always creates a fresh one."""
    job_id = uuid.uuid4().hex
    # Pinned flows (give OR receive) bypass the shared per-key cache — they
    # answer a specific question, not the league-wide deck.
    is_pinned = bool(pinned_give) or bool(pinned_receive)
    job = {
        "job_id":             job_id,
        "key":                _trade_job_key(user_id, league_id, scoring_format),
        "status":             "running",
        "started_at":         time.monotonic(),
        "finished_at":        None,
        "opponents_done":     0,
        "opponents_total":    opponents_total or 0,
        "cards":              [],
        "error":              None,
        "fairness_threshold": fairness_threshold,
        "outlook_value":      None,    # populated when the worker reads prefs
        "is_pinned":          is_pinned,
    }
    with _trade_jobs_lock:
        _trade_jobs[job_id] = job
        if not is_pinned:
            # Pin into the per-key index so future generate calls dedupe.
            _trade_jobs_by_key[job["key"]] = job_id

    threading.Thread(
        target=_run_trade_job,
        args=(job_id, sess_token, league_id, fairness_threshold,
              pinned_give or [], pinned_receive or []),
        daemon=True,
    ).start()
    return job_id
def player_to_dict(p) -> dict:
    d = {
        "id":               p.id,
        "name":             p.name,
        "position":         p.position,
        "team":             p.team,
        "age":              p.age,
        "years_experience": p.years_experience,
    }
    # Extended fields — only included when present (non-None)
    for attr in (
        "depth_chart_position", "depth_chart_order",
        "injury_status",        "injury_body_part",
        "birth_date",           "height",  "weight",
        "college",              "search_rank", "adp",
        "pick_value",
    ):
        val = getattr(p, attr, None)
        if val is not None:
            d[attr] = val
    return d


def ranked_player_to_dict(rp) -> dict:
    return {**player_to_dict(rp.player), "elo": rp.elo,
            "wins": rp.wins, "losses": rp.losses, "rank": rp.rank}


# ---------------------------------------------------------------------------
# Ranking API Routes
# ---------------------------------------------------------------------------

@app.route("/api/trio")
def get_trio():
    """GET /api/trio?position=RB  →  next 3 players to rank"""
    sess = _require_session()
    sess["last_active"] = time.time()
    service = sess["service"]
    position = request.args.get("position") or None
    # Agent 1: persistent "I don't know this player" skips for this user+format
    try:
        skipped_ids = _skip_load(
            user_id=sess.get("user_id", ""),
            scoring_format=_active_format(sess),
        )
    except Exception as _skip_err:
        log.warning("load_skips failed (continuing without filter): %s", _skip_err)
        skipped_ids = set()
    try:
        # Agent A1 — swipe.qc_compliments: periodically substitute a lopsided
        # "QC" trio so we can reward the user when they match the community
        # consensus. Throttled to at most 1 QC trio per QC_TRIO_INTERVAL
        # rankings per position (deterministic counter — see TestFlight bug
        # #19). Flag-off behavior is unchanged.
        qc_trio_obj = None
        qc_expected_order: list = []
        qc_counter_key: str | None = None  # set below if QC eligible
        if is_enabled("swipe.qc_compliments"):
            try:
                # Per-session counter keyed by position (or "" for cross-pos).
                # Counts rankings *since* the last QC trio for that position.
                # First request of a session starts at 0 so users don't get a
                # QC trio on their very first ranking after login.
                qc_counters = sess.setdefault("_qc_counters", {})
                qc_counter_key = position or ""
                rankings_since_last = qc_counters.get(qc_counter_key, 0)
                if rankings_since_last >= QC_TRIO_INTERVAL:
                    from .smart_matchup_generator import find_qc_trio as _find_qc
                    _pool = service._pool(position)
                    if skipped_ids:
                        _pool = [p for p in _pool if p.id not in skipped_ids]
                    picked = _find_qc(_pool, service._seed)
                    if picked is not None:
                        a, b, c = picked
                        qc_expected_order = [a.id, b.id, c.id]
                        # Duck-type a trio object compatible with the
                        # serialisation code below.
                        class _QCTrio:  # local, tiny
                            pass
                        qc_trio_obj = _QCTrio()
                        qc_trio_obj.player_a = a
                        qc_trio_obj.player_b = b
                        qc_trio_obj.player_c = c
                        qc_trio_obj.reasoning = "Consensus check — clear tier gap."
            except Exception as _qc_err:
                log.warning("qc_compliments trio generation failed: %s", _qc_err)
                qc_trio_obj = None

        if qc_trio_obj is not None:
            trio = qc_trio_obj
        else:
            trio = service.get_next_trio(position=position, skipped_player_ids=skipped_ids)
        resp = {
            "player_a":  player_to_dict(trio.player_a),
            "player_b":  player_to_dict(trio.player_b),
            "player_c":  player_to_dict(trio.player_c),
            "reasoning": trio.reasoning,
            "tier_info": service._tier_info(position),
        }

        # Agent A1 — swipe.community_compare: attach community-consensus
        # signal so the frontend can show "X% agreed with your #1" toast.
        # Flag-off: no new keys in the response.
        if is_enabled("swipe.community_compare"):
            try:
                from .smart_matchup_generator import community_trio_signal
                sig = community_trio_signal(
                    seed_elo=service._seed,
                    trio_ids=[trio.player_a.id, trio.player_b.id, trio.player_c.id],
                )
                if sig is not None:
                    resp["community_signal"] = sig
            except Exception as _cs_err:
                log.warning("community_compare signal failed: %s", _cs_err)

        # Agent A1 — swipe.qc_compliments: mark the response so the frontend
        # can reward consensus-matching rankings. Flag-off or non-QC trio:
        # no new keys in the response.
        if is_enabled("swipe.qc_compliments") and qc_trio_obj is not None and qc_expected_order:
            resp["is_qc_trio"] = True
            resp["qc_expected_order"] = qc_expected_order

        # Throttle counter: reset on QC served, otherwise increment. Only
        # touched when the flag is on so non-QC sessions stay cheap.
        if qc_counter_key is not None:
            qc_counters = sess.get("_qc_counters")
            if qc_counters is not None:
                if qc_trio_obj is not None:
                    qc_counters[qc_counter_key] = 0
                else:
                    qc_counters[qc_counter_key] = (
                        qc_counters.get(qc_counter_key, 0) + 1
                    )

        return jsonify(resp)
    except Exception as e:
        log.exception("get_trio failed")
        return jsonify({"error": "bad_request"}), 400


# ── Leaderboard cache ─────────────────────────────────────────────────────
# Universal-scope queries scan the full users / user_events tables. Cache
# the result for 5 min so a hot leaderboards screen doesn't hammer the DB.
# Keyed on (scope, league_id, metric, window) — self-row + is_self flags
# are computed outside the cache so two users in the same league still see
# their own rank highlighted correctly.
_LEADERBOARD_CACHE: dict[tuple, tuple[float, dict]] = {}
_LEADERBOARD_TTL_SECONDS = 300


def _leaderboard_cached(metric: str, window: str | None, league_id: str | None) -> dict:
    key = ("league" if league_id else "universal", league_id, metric, window)
    now = time.time()
    hit = _LEADERBOARD_CACHE.get(key)
    if hit and (now - hit[0]) < _LEADERBOARD_TTL_SECONDS:
        return hit[1]
    data = load_leaderboard(metric=metric, window=window, league_id=league_id)
    _LEADERBOARD_CACHE[key] = (now, data)
    return data


# ── League members / unlock-states cache (review #B4) ─────────────────────
# Both /api/league/members and /api/league/member-unlock-states call the
# same `load_league_member_unlock_states(league_id, exclude_user_id)`
# loader, which runs two SELECTs + JSON parsing. Mobile/web hit both on
# first render of the League screen → doubled DB chatter. Mirror the
# leaderboard cache: short TTL, keyed on (league_id, exclude_user_id).
# Writes that change membership/rankings invalidate via
# `_invalidate_league_members_cache(league_id)`.
_LEAGUE_MEMBERS_CACHE: dict[tuple, tuple[float, list[dict]]] = {}
_LEAGUE_MEMBERS_TTL_SECONDS = 60


def _league_members_cached(league_id: str, exclude_user_id: str | None) -> list[dict]:
    key = (league_id, exclude_user_id or "")
    now = time.time()
    hit = _LEAGUE_MEMBERS_CACHE.get(key)
    if hit and (now - hit[0]) < _LEAGUE_MEMBERS_TTL_SECONDS:
        return hit[1]
    data = load_league_member_unlock_states(
        league_id=league_id, exclude_user_id=exclude_user_id,
    )
    _LEAGUE_MEMBERS_CACHE[key] = (now, data)
    return data


def _invalidate_league_members_cache(league_id: str) -> None:
    """Drop any cached entries for `league_id` (all exclude_user_id variants).
    Called from write paths that change leaguemate roster, unlock state, or
    ranking_method — the three fields the loader projects.
    """
    if not league_id:
        return
    stale = [k for k in _LEAGUE_MEMBERS_CACHE if k[0] == league_id]
    for k in stale:
        _LEAGUE_MEMBERS_CACHE.pop(k, None)


@app.route("/api/leaderboard", methods=["GET"])
def get_leaderboard():
    """GET /api/leaderboard?scope=league|universal&metric=streak|ranks&window=week|month|season|all&league_id=...

    `window` is required when `metric=ranks`, ignored when `metric=streak`.
    `league_id` is required when `scope=league`. Universal scope ignores any
    league_id passed in.

    The cached top slice carries no per-user is_self info — we tag it on
    the way out so the same cached payload personalizes for every viewer.
    Out-of-top users get a `self_row` populated via a one-off uncached
    scan so they can see their own rank pinned at the bottom on mobile.
    """
    sess = _require_session()
    self_user_id = sess["user_id"]

    scope     = (request.args.get("scope") or "universal").lower()
    metric    = (request.args.get("metric") or "streak").lower()
    window    = (request.args.get("window") or None)
    league_id = request.args.get("league_id") or None

    if scope == "league" and not league_id:
        return jsonify({"error": "league_id is required when scope=league"}), 400
    if scope == "universal":
        league_id = None  # ignore stray league_id on universal queries

    if metric not in ("streak", "ranks"):
        return jsonify({"error": "metric must be 'streak' or 'ranks'"}), 400
    if metric == "streak":
        window = None
    elif window not in ("week", "month", "season", "all"):
        return jsonify({"error": "window must be week/month/season/all when metric=ranks"}), 400

    base = _leaderboard_cached(metric, window, league_id)

    rows = [{**r, "is_self": (r["user_id"] == self_user_id)} for r in base["rows"]]
    in_top = any(r["is_self"] for r in rows)
    self_row = None
    if not in_top:
        # Out-of-top: a single SQL count-of-better-positions gives the
        # viewer's rank without re-ranking everyone or invalidating the
        # cache when ranks shift.
        self_row = get_self_leaderboard_row(
            metric=metric, window=window, league_id=league_id, user_id=self_user_id,
        )

    return jsonify({
        "metric":    metric,
        "window":    window,
        "scope":     scope,
        "league_id": league_id,
        "rows":      rows,
        "self_row":  self_row,
    })


@app.route("/api/me/streak", methods=["GET"])
@_gate_unverified_read
def get_me_streak():
    """GET /api/me/streak → {current, longest, last_rank_local_date}.

    The streak counter advances inside record_event() whenever a rank-class
    event fires (see _RANK_STREAK_EVENTS). This endpoint just reads the
    denormalized columns on `users`.
    """
    sess = _require_session()
    return jsonify(get_user_streak(sess["user_id"]))


@app.route("/api/rank3", methods=["POST"])
@_gate_unverified_write
def post_rank3():
    """POST /api/rank3  {ranked: [id1, id2, id3]}  →  updated progress"""
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    service      = sess["service"]
    g_user_id    = sess["user_id"]
    g_league     = sess["league"]
    body   = request.get_json(force=True) or {}
    ranked = body.get("ranked", [])

    if len(ranked) < 2:
        return jsonify({"error": "ranked must contain at least 2 player IDs"}), 400

    # Guard against stale trios: the service may have been rebuilt (server
    # restart or league switch) between when the trio was displayed and when
    # the user submitted their ranking.  Filter out any IDs that are no longer
    # in the current pool and recover gracefully instead of crashing.
    ranked_valid = [pid for pid in ranked if service.has_player(pid)]
    if len(ranked_valid) < len(ranked):
        dropped = [pid for pid in ranked if not service.has_player(pid)]
        log.warning(
            "post_rank3: %d/%d submitted IDs not in current player pool "
            "(stale trio — service may have been rebuilt).  Dropped: %s",
            len(dropped), len(ranked), dropped,
        )
    if len(ranked_valid) < 2:
        # Cannot record a meaningful ranking — tell the frontend to refresh
        return jsonify({
            "error":      "stale_trio",
            "message":    "Player data was refreshed while you were ranking. "
                          "These players will be shown again — please re-rank them.",
        }), 409

    try:
        rank_set = service.record_ranking(ordered_ids=ranked_valid)
        fmt = _active_format(sess)

        # Persist swipe history — lets rankings survive server restarts
        try:
            save_ranking_swipes(
                user_id        = g_user_id,
                ordered_ids    = ranked_valid,
                scoring_format = fmt,
            )
        except Exception as db_err:
            log.warning("DB write failed for ranking swipe (continuing): %s", db_err)

        # Auto-publish current ELO snapshot to member_rankings so leaguemates
        # can use the real valuations in their trade generation.
        # We submit ALL positions each time — cheap and always-consistent.
        try:
            if g_league and g_league.league_id not in ("league_demo",):
                all_rankings = service.get_rankings(position=None)
                ranking_payload = [
                    {"player_id": rp.player.id, "elo": rp.elo}
                    for rp in all_rankings.rankings
                ]
                upsert_member_rankings(
                    user_id        = g_user_id,
                    league_id      = g_league.league_id,
                    rankings       = ranking_payload,
                    scoring_format = fmt,
                )
        except Exception as db_err:
            log.warning("member_rankings auto-publish failed (continuing): %s", db_err)

        # ── Trends: record ELO snapshot for any player involved in this
        # ranking.  We only write the players that actually changed in this
        # submission (the three IDs in `ranked_valid`) — the Risers/Fallers
        # computation uses oldest-first ordering, so per-submit rows here
        # feed cleanly into /api/trends/risers-fallers without a cron job.
        try:
            snapshot_league = g_league.league_id if g_league else None
            current_rankings = service.get_rankings(position=None).rankings
            changed = {
                rp.player.id: rp.elo
                for rp in current_rankings
                if rp.player.id in set(ranked_valid)
            }
            if changed:
                record_elo_snapshot(
                    user_id         = g_user_id,
                    league_id       = snapshot_league,
                    scoring_format  = fmt,
                    changed_ratings = changed,
                )
        except Exception as db_err:
            log.warning("elo_history snapshot failed (continuing): %s", db_err)

        # record_event returns the post-event streak so we don't need a
        # separate get_user_streak() round-trip below.
        post_streak: dict | None = None
        try:
            post_streak = record_event(
                g_user_id,
                "trio_swipe",
                league_id = g_league.league_id if g_league else None,
                source    = "api",
                props     = {"ordered_ids": ranked_valid, "scoring_format": fmt},
                tz        = getattr(g, "user_tz", None),
                **(getattr(g, "device_info", {}) or {}),
            )
        except Exception as ev_err:
            log.warning("record_event(trio_swipe) failed: %s", ev_err)

        # Invalidate cached trade-generation jobs — the user's ELO map just
        # changed, so any cached deck is stale. Drop across all leagues
        # since rankings are user-level. Don't synchronously regenerate;
        # the next user-tap on Find a Trade (or the next session_init for
        # a league) will pick up the fresh state.
        try:
            _invalidate_trade_jobs(user_id=g_user_id)
        except Exception as inv_err:
            log.warning("rank3: trade-cache invalidation failed: %s", inv_err)

        pct = min(100, round(rank_set.interaction_count / rank_set.threshold * 100))
        # Inline the post-rank streak from record_event's return value (same
        # transaction). Fall back to a fresh read only if the dual-write
        # itself failed — rare and already logged.
        streak = post_streak if post_streak is not None else get_user_streak(g_user_id)
        return jsonify({
            "interaction_count": rank_set.interaction_count,
            "threshold":         rank_set.threshold,
            "threshold_met":     rank_set.threshold_met,
            "percent":           pct,
            "streak":            streak,
        })
    except Exception as e:
        log.exception("post_rank3 failed")
        return jsonify({"error": "bad_request"}), 400


@app.route("/api/rankings")
@_gate_unverified_read
def get_rankings():
    """GET /api/rankings?position=RB  →  ordered player list"""
    sess = _require_session()
    sess["last_active"] = time.time()
    service = sess["service"]
    position = request.args.get("position") or None
    try:
        rank_set = service.get_rankings(position=position)
        rankings = [ranked_player_to_dict(rp) for rp in rank_set.rankings]
        # FB4-61 tile stats — attach the market side: consensus positional
        # rank + its 30d delta. Additive & best-effort: an enrichment failure
        # must never break the rankings read, and both fields follow
        # player_to_dict's omit-when-absent convention (the trend is absent
        # until player_value_history has a prior-day snapshot in-window).
        try:
            cons_rank, cons_delta = _consensus_pos_ranks(_active_format(sess))
            for d in rankings:
                r = cons_rank.get(d["id"])
                if r is None:
                    continue
                d["consensus_pos_rank"] = r
                dd = cons_delta.get(d["id"])
                if dd is not None:
                    d["consensus_pos_rank_delta_30d"] = dd
        except Exception:
            log.warning("consensus pos-rank enrichment failed", exc_info=True)
        # TestFlight #71 tile meters — attach tradeability (owned) /
        # acquirability (unowned) 0-1 scores derived from the Trends
        # consensus-gap math (trends_service.compute_tile_trade_scores).
        # Additive & best-effort like the block above; both fields are
        # omit-when-unavailable: no real league in session, demo league,
        # < 3 community rankers, or no comparison basis for the player
        # (free agent / absent from the community pool).
        try:
            g_league = sess.get("league")
            league_id = g_league.league_id if g_league else None
            if league_id and league_id != "league_demo":
                community = load_community_elo_for_league(
                    league_id       = league_id,
                    exclude_user_id = sess.get("user_id", ""),
                    scoring_format  = _active_format(sess),
                )
                members = [{
                    "user_id":  m.user_id,
                    "username": m.username,
                    "roster":   list(getattr(m, "roster", []) or []),
                } for m in g_league.members]
                scores = _trends_service_mod.compute_tile_trade_scores(
                    user_elo           = {d["id"]: d.get("elo") for d in rankings},
                    community_rankings = community,
                    user_roster        = sess.get("user_roster") or [],
                    league_members     = members,
                )
                for d in rankings:
                    s = scores.get(d["id"])
                    if not s:
                        continue
                    key = "tradeability" if s["owned"] else "acquirability"
                    d[key] = s["score"]
        except Exception:
            log.warning("tile trade-score enrichment failed", exc_info=True)
        return jsonify({
            "position":          rank_set.position,
            "rankings":          rankings,
            "interaction_count": rank_set.interaction_count,
            "threshold":         rank_set.threshold,
            "threshold_met":     rank_set.threshold_met,
            "version":           rank_set.version,
        })
    except Exception as e:
        log.exception("get_rankings failed")
        return jsonify({"error": "bad_request"}), 400


@app.route("/api/progress")
@_gate_unverified_read
def get_progress():
    """GET /api/progress?position=RB  →  completion status"""
    sess = _require_session()
    sess["last_active"] = time.time()
    service = sess["service"]
    position = request.args.get("position") or None
    try:
        return jsonify(service.get_progress(position=position))
    except Exception as e:
        log.exception("get_progress failed")
        return jsonify({"error": "bad_request"}), 400


@app.route("/api/rankings/progress")
@_gate_unverified_read
def get_rankings_progress():
    """
    GET /api/rankings/progress
    Returns per-position interaction counts for the current user and whether
    the Trade Finder is unlocked (all 4 positions >= threshold).

    Uses the in-memory ranking service for accurate counts (each 3-player
    ranking = 1 interaction, not 3 raw DB rows).

    Response:
        {
            "QB": 7, "RB": 12, "WR": 3, "TE": 10,
            "threshold": 10,
            "unlocked": false,
            "total_required": 40,
            "total_completed": 32
        }
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    service = sess["service"]
    fmt = _active_format(sess)
    POSITIONS = ("QB", "RB", "WR", "TE")

    counts: dict[str, int] = {}
    for pos in POSITIONS:
        progress = service.get_progress(position=pos)
        counts[pos] = progress["interaction_count"]

    threshold       = service.POSITION_THRESHOLDS.get("QB", 10)  # all are 10 now
    total_required  = threshold * len(POSITIONS)
    total_completed = sum(counts.values())

    # Unlock logic depends on the user's chosen ranking method
    g_user_id = sess["user_id"]
    ranking_method = None
    try:
        ranking_method = get_ranking_method(g_user_id)
    except Exception:
        pass

    if ranking_method == "manual":
        unlocked = True
    elif ranking_method in ("tiers", "quickset"):
        # 'quickset' (#119) commits through the same /api/tiers/save
        # contract as the Tiers board, so it unlocks the same way.
        try:
            saved = get_tiers_saved(g_user_id, scoring_format=fmt)
            unlocked = all(p in saved for p in POSITIONS)
        except Exception:
            unlocked = False
    else:
        # 'trio' or null — original threshold logic
        unlocked = all(counts[p] >= threshold for p in POSITIONS)

    # Pull the user's prior unlocked formats now so we can apply a
    # monotonic floor to the per-method decision above. Users who already
    # qualified via one method (e.g. trio swipes) and later switched their
    # method (e.g. to "tiers") were getting re-locked here because the
    # method-specific check failed — even though they had already passed.
    # mark_format_unlocked is monotonic by contract, so OR'ing here is safe.
    try:
        unlocked_formats_list = get_unlocked_formats(g_user_id) or []
    except Exception:
        unlocked_formats_list = []

    if not unlocked and fmt in unlocked_formats_list:
        unlocked = True

    # Mark the format as unlocked once (monotonic) so the League Summary
    # adoption counts can query users.unlocked_formats efficiently.
    # mark_format_unlocked returns {'inserted', 'was_first'} computed in
    # the same transaction as the write — gating on `was_first` is race-free
    # (concurrent /progress calls won't both see was_first=True). When the
    # user is reaching this from the monotonic OR above (already in the
    # list), `was_first` will be False and the event/push fan-out won't
    # spuriously fire.
    if unlocked:
        # Short-circuit when the user is already unlocked in this format.
        # `mark_format_unlocked` is monotonic and inserts only on the first
        # transition (returns inserted=False, was_first=False otherwise), so
        # skipping it here is equivalent — we save the write txn + the
        # subsequent peer-push fanout on every poll for already-unlocked users.
        # The transition write still runs because `fmt in unlocked_formats_list`
        # is only True after `mark_format_unlocked` has previously persisted.
        _already_unlocked = fmt in unlocked_formats_list
        _unlock_res = {"inserted": False, "was_first": False}
        if not _already_unlocked:
            try:
                _unlock_res = mark_format_unlocked(g_user_id, fmt) or _unlock_res
            except Exception as db_err:
                log.warning("mark_format_unlocked failed: %s", db_err)

        if _unlock_res.get("inserted"):
            # User's `unlocked_formats` just changed → drop cached
            # member-unlock-states for the active league so leaguemates
            # see the new badge on next fetch.
            try:
                _lid_for_invalidate = getattr(
                    sess.get("league"), "league_id", None
                )
                if _lid_for_invalidate:
                    _invalidate_league_members_cache(_lid_for_invalidate)
            except Exception:
                pass

        if _unlock_res.get("was_first"):
            try:
                record_event(
                    g_user_id,
                    "ranking_complete_first_time",
                    source="api",
                    props={"scoring_format": fmt},
                    **(getattr(g, "device_info", {}) or {}),
                )
            except Exception as ev_err:
                log.warning("record_event(ranking_complete_first_time) failed: %s", ev_err)
            # Fire league_member_unlocked_trades to leaguemates already on
            # the app. League is resolved via the active session.
            try:
                _league_obj  = sess.get("league")
                _league_id   = getattr(_league_obj, "league_id", None)
                _league_name = getattr(_league_obj, "name", "") or ""
                if _league_id:
                    _members  = load_league_member_unlock_states(
                        _league_id, exclude_user_id=g_user_id,
                    )
                    _my_username = (sess.get("display_name")
                                    or sess.get("username") or g_user_id)
                    for _p in _members:
                        if not _p.get("joined") or not _p.get("user_id"):
                            continue
                        _send_typed_push(
                            _p["user_id"],
                            "league_member_unlocked_trades",
                            title = "🔓 New trade options in your league",
                            body  = f"@{_my_username} just unlocked Trade Finder. Tap to look for matches.",
                            data  = {"unlocker_user_id": g_user_id,
                                     "league_id": _league_id,
                                     "league_name": _league_name},
                            dedup_key = f"unlock:{g_user_id}:{_p['user_id']}",
                        )
            except Exception as _lm_err:
                log.warning("league_member_unlocked_trades push failed: %s", _lm_err)

        # If the per-method branch decided unlocked=True for a format
        # we hadn't seen before, fold it into the response list now —
        # mark_format_unlocked above already persisted, but our local
        # cache was read before that write.
        if fmt not in unlocked_formats_list:
            unlocked_formats_list = list(unlocked_formats_list) + [fmt]

    return jsonify({
        **counts,
        "threshold":        threshold,
        "unlocked":         unlocked,
        "ranking_method":   ranking_method,
        "scoring_format":   fmt,
        "total_required":   total_required,
        "total_completed":  total_completed,
        "unlocked_formats": unlocked_formats_list,
    })


@app.route("/api/ranking-method", methods=["POST"])
@_gate_unverified_write
def set_ranking_method_route():
    """POST /api/ranking-method {method: 'trio'|'manual'|'tiers'|'anchor'|'quickset'}

    'anchor' (2026-07-10) = the Pick Anchor wizard — added alongside the
    mobile rank-home chooser, which records the user's preferred ranking
    flow here (the routing itself is client-side; see cross-client-
    invariants.md → Ranking method strings).
    'quickset' (2026-07-12, #119) = the guided tier quick-set walk
    (QuickSetTiersScreen) promoted to a first-class method. Saves flow
    through /api/tiers/save, so unlock treats it like 'tiers'.
    """
    sess = _require_session()
    g_user_id = sess["user_id"]
    body   = request.get_json(force=True) or {}
    method = body.get("method", "")
    if method not in ("trio", "manual", "tiers", "anchor", "quickset"):
        return jsonify({"error": f"Invalid method: {method!r}"}), 400
    try:
        set_ranking_method(g_user_id, method)
        log.info("ranking-method set for %s: %s", g_user_id, method)
        # `has_ranking_method` is one of the fields the league-members
        # loader projects; flip the cache so leaguemates see the update.
        try:
            _lid_for_invalidate = getattr(
                sess.get("league"), "league_id", None
            )
            if _lid_for_invalidate:
                _invalidate_league_members_cache(_lid_for_invalidate)
        except Exception:
            pass
        return jsonify({"ok": True, "method": method})
    except Exception as e:
        log.error("set ranking-method error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/scoring/switch", methods=["POST"])
@_gate_unverified_write
def switch_scoring_format():
    """POST /api/scoring/switch {format: '1qb_ppr'|'sf_tep'}

    Updates the session's active scoring format. Both formats' services
    stay in memory; this just flips which one is "active" for subsequent
    ranking/trade calls. Returns the new active format.
    """
    from .database import SCORING_FORMATS as DB_SCORING_FORMATS
    sess = _require_session()
    body = request.get_json(force=True) or {}
    fmt  = body.get("format", "")
    if fmt not in DB_SCORING_FORMATS:
        return jsonify({"error": f"Invalid format: {fmt!r}. Must be one of {DB_SCORING_FORMATS}"}), 400
    sess["active_format"] = fmt
    # Re-sync aliases so the next reader uses the new format even before
    # _require_session runs again.
    services   = sess.get("services") or {}
    trade_svcs = sess.get("trade_svcs") or {}
    if fmt in services:
        sess["service"] = services[fmt]
    if fmt in trade_svcs:
        sess["trade_svc"] = trade_svcs[fmt]
    log.info("scoring/switch %s → %s", sess.get("user_id"), fmt)
    return jsonify({"ok": True, "active_format": fmt})


@app.route("/api/tier-config")
def get_tier_config():
    """GET /api/tier-config — return the shared tier band table.

    Single source of truth for both backend (apply_tiers) and frontend
    (autoAssignTiers / autosave bucketing). Loaded from
    backend/tier_config.json at process start. The frontend fetches this
    once on init so the two sides cannot drift on (format, position, tier)
    band ranges.

    Response shape:
      {
        "tiers": ["firsts_4plus","firsts_3","firsts_2","first_1",
                  "second","third","fourth","waivers"],   # display order
        "config": {
          "1qb_ppr": {
            "QB": { "firsts_4plus": {"min": 1927, "max": 1972}, ... },
            "RB": {...}, "WR": {...}, "TE": {...}
          },
          "sf_tep": { ...same shape... }
        }
      }
    """
    return jsonify({
        "tiers":  list(ORDERED_TIERS),
        "config": TIER_CONFIG,
    })


@app.route("/api/tiers/copy-from-format", methods=["POST"])
@_gate_unverified_write
def copy_tiers_from_format_route():
    """POST /api/tiers/copy-from-format {from_format: '1qb_ppr'}

    VALUE-AWARE copy (#124/#139) of the user's board from one scoring
    format to the active scoring format. Until 2026-07-17 this preserved
    each player's tier LABEL — but the tier labels are pick-denominated
    ("worth 4+ firsts"), and a player worth 4+ firsts in SF is NOT worth
    4+ firsts in 1QB: the formats' value distributions differ, QBs most
    of all. Label-preserving copy therefore systematically overvalued
    QBs on SF→1QB and undervalued them on 1QB→SF.

    Now the copy preserves the user's RANK ORDER per position and
    re-seeds the value magnitudes from the TARGET format's consensus
    curve at those ranks (RankingService.apply_value_map — a permutation
    of the copied group's own target-format seed Elos):

      1) For each position, read the source board via
         from_svc.get_rankings() — every VISIBLY-TIERED player (source
         tier_for_elo non-None), override or not, in elo-desc order.
         (get_rankings, not _elo_overrides: seed-tiered players without
         an explicit override render on the board too and must copy —
         the Kyler Murray bug.)
      2) Wholesale-replace the target's _elo_overrides (clear first) so
         leftover target overrides not present in the source aren't
         retained — "copy" means overwrite.
      3) to_svc.apply_value_map(position, ordered_pids): rank i gets the
         group's i-th largest TARGET-format seed Elo. Order is the
         user's; magnitudes (and hence tier labels) are the target
         consensus — QBs shift most, by design. A player may fall below
         the target waivers floor and render unranked (correct: e.g. a
         board-worthy SF QB2x can be waiver fodder in 1QB).
      4) Persist + mark all touched positions as saved + republish to
         member_rankings.

    Deterministic and idempotent for an unchanged source board:
    re-copying reproduces the same target overrides.

    Body:
      from_format: '1qb_ppr' or 'sf_tep' — which format to copy FROM.
      The TO format is the user's currently active format.

    Response:
      { ok: true, from_format, to_format, mapping: 'value_rank',
        position_counts: {QB: N, ...}, total: N }
    """
    sess = _require_initialized_session()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    body      = request.get_json(force=True) or {}
    from_format = body.get("from_format")

    # Resolve target format with explicit overrides taking precedence over
    # the session's stored active_format. This is critical because a user
    # can land on the Tiers page on SF TEP without ever clicking the format
    # toggle in this session — the localStorage UI state would say SF TEP
    # but sess['active_format'] would still be the session_init default
    # (1qb_ppr). _active_format reads sess['_effective_format'] (set by
    # _require_session from the X-Scoring-Format header) first, then falls
    # back to sess['active_format']. We ALSO accept to_format in the body
    # as a final fallback so older deploys / cache scenarios still work.
    to_format = body.get("to_format") or _active_format(sess)

    valid_formats = ("1qb_ppr", "sf_tep")
    if from_format not in valid_formats or to_format not in valid_formats:
        return jsonify({"error": f"Invalid format. Got from={from_format!r} to={to_format!r}"}), 400
    if from_format == to_format:
        return jsonify({"error": "from and to formats must differ"}), 400

    services = sess.get("services") or {}
    from_svc = services.get(from_format)
    to_svc   = services.get(to_format)
    if not from_svc or not to_svc:
        return jsonify({"error": "Per-format services not initialised — please refresh"}), 500

    # Collect each position's source board as an ordered pid list (source
    # effective ELO desc — get_rankings is already sorted).
    #
    # CRITICAL: iterate every player's EFFECTIVE rendered ELO via
    # get_rankings(), NOT just from_svc._elo_overrides. The override dict
    # only contains players the user has EXPLICITLY tier-saved or
    # manual-reordered. Players whose default-DP seed ELO happens to land
    # inside a tier band ALSO render on the board (per autoAssignTiers) —
    # but they don't have an override entry. (Real bug: Kyler Murray's
    # 1QB seed rendered him "Depth QB20" with no override; an overrides-
    # only copy silently skipped him and the wholesale clear then dropped
    # him a tier in the target view.) get_rankings captures every
    # visibly-tiered player, override or not.
    by_position: dict[str, list[str]] = {}
    seen_anything = False
    for position in ("QB", "RB", "WR", "TE"):
        try:
            rank_set = from_svc.get_rankings(position=position)
        except Exception as e:
            log.warning("copy-from-format: get_rankings(%s) failed: %s", position, e)
            continue
        ordered: list[str] = []
        for rp in rank_set.rankings:
            seen_anything = True
            if rp.elo is None:
                continue
            # Only players on the visible source board (in some tier under
            # the SOURCE format) are part of the copied list.
            if not RankingService.tier_for_elo(rp.elo, position, from_format):
                continue
            ordered.append(rp.player.id)
        if ordered:
            by_position[position] = ordered

    if not seen_anything:
        return jsonify({
            "ok": False,
            "error": f"No data to copy from {from_format}",
        }), 400

    # Wholesale replace: clear target overrides FIRST. The apply_value_map
    # calls below rewrite each position's slice fresh, on the target
    # format's consensus value curve. Any pre-existing target override for
    # a pid not in the source is dropped — that's what "copy" means here.
    to_svc._elo_overrides = {}

    position_counts: dict[str, int] = {}
    for position, ordered_pids in by_position.items():
        # Value-aware mapping (#124): keep the user's rank order, deal out
        # the group's own TARGET-format seed Elos to those ranks. Tier
        # labels land wherever the target consensus puts them — QBs shift
        # most between SF and 1QB, which is the point.
        position_counts[position] = to_svc.apply_value_map(position, ordered_pids)

    # Persist override dict.
    try:
        save_tier_overrides(g_user_id, to_svc._elo_overrides, scoring_format=to_format)
    except Exception as db_err:
        log.warning("copy-from-format: save_tier_overrides failed: %s", db_err)
        return jsonify({"error": f"DB write failed: {db_err}"}), 500

    # Mark each touched position as saved for the target format.
    for position in by_position:
        try:
            save_tiers_position(g_user_id, position, scoring_format=to_format)
        except Exception as db_err:
            log.warning("copy-from-format: save_tiers_position(%s) failed: %s", position, db_err)

    # Republish to member_rankings so leaguemates see the new format's rank
    # set when generating trades.
    if g_league and g_league.league_id not in ("league_demo",):
        try:
            all_rankings = to_svc.get_rankings(position=None)
            ranking_payload = [
                {"player_id": rp.player.id, "elo": rp.elo}
                for rp in all_rankings.rankings
            ]
            upsert_member_rankings(
                user_id        = g_user_id,
                league_id      = g_league.league_id,
                rankings       = ranking_payload,
                scoring_format = to_format,
            )
        except Exception as db_err:
            log.warning("copy-from-format: member_rankings publish failed: %s", db_err)

    # Invalidate any cached trade-generation jobs since rankings just changed.
    try:
        _invalidate_trade_jobs(user_id=g_user_id)
    except Exception:
        pass

    log.info("tiers/copy %s → %s for %s — value-mapped %d overrides across %d positions",
             from_format, to_format, g_user_id,
             sum(position_counts.values()), len(position_counts))
    return jsonify({
        "ok":              True,
        "from_format":     from_format,
        "to_format":       to_format,
        "mapping":         "value_rank",
        "position_counts": position_counts,
        "total":           sum(position_counts.values()),
    })


@app.route("/api/feedback", methods=["POST"])
@_gate_unverified_write
def submit_feedback_route():
    """POST /api/feedback — in-app feedback capture from mobile.

    Body:
      client_id           required, unique per note (mobile's local id)
      screen              required, non-empty (≤ 100 chars; truncated)
      severity            required, one of bug | polish | idea
      text                required, non-empty, ≤ 2000 chars
      client_created_at   required, ISO timestamp from the client

    Auth is best-effort: if X-Session-Token resolves to a session we
    attribute the note to that user, otherwise we accept anonymously.
    External testers' submissions land regardless of sign-in state.

    Idempotent on client_id — retries return 200 with `duplicate: true`.

    Contract spec: docs/plans/feedback-backend-sync.md
    """
    body = request.get_json(force=True, silent=True) or {}

    client_id_raw = body.get("client_id")
    screen_raw    = body.get("screen")
    severity_raw  = body.get("severity")
    text_raw      = body.get("text")
    client_created_at = body.get("client_created_at")

    # ── Validation (matches the locked contract in the plan doc) ────────
    if not isinstance(client_id_raw, str) or not client_id_raw.strip():
        return jsonify({"error": "missing_field", "field": "client_id"}), 400
    if not isinstance(screen_raw, str) or not screen_raw.strip():
        return jsonify({"error": "missing_field", "field": "screen"}), 400
    if not isinstance(text_raw, str) or not text_raw.strip():
        return jsonify({"error": "missing_field", "field": "text"}), 400
    if severity_raw not in ("bug", "polish", "idea"):
        return jsonify({"error": "invalid_severity"}), 400

    client_id = client_id_raw.strip()[:100]
    screen    = screen_raw.strip()[:100]
    severity  = severity_raw
    text_body = text_raw.strip()
    if len(text_body) > 2000:
        return jsonify({"error": "text_too_long", "limit": 2000}), 400

    # ── Best-effort session lookup; anonymous on miss ──────────────────
    user_id = None
    username = None
    token = request.headers.get("X-Session-Token", "")
    if token:
        with _sessions_lock:
            sess = _sessions.get(token)
        if sess:
            user_id  = sess.get("user_id")
            username = sess.get("display_name") or sess.get("username")

    # Device snapshot — same headers client.ts already attaches.
    platform_label = "ios" if (request.headers.get("X-Device") or "").lower() in ("iphone", "ipad", "macos") else None
    device_type    = request.headers.get("X-Device")
    os_version     = request.headers.get("X-OS-Version")
    app_version    = request.headers.get("X-App-Version")

    try:
        result = save_feedback(
            client_id=client_id,
            screen=screen,
            severity=severity,
            text_body=text_body,
            user_id=user_id,
            username=username,
            app_version=app_version,
            platform=platform_label,
            device_type=device_type,
            os_version=os_version,
            client_created_at=client_created_at if isinstance(client_created_at, str) else None,
        )
    except Exception as e:
        log.exception("save_feedback failed: %s", e)
        return jsonify({"error": "internal"}), 500

    status = 200 if result.get("duplicate") else 201
    return jsonify({
        "ok":          True,
        "server_id":   result["server_id"],
        "created_at":  result["created_at"],
        "duplicate":   bool(result.get("duplicate")),
    }), status


@app.route("/api/feedback/admin", methods=["GET"])
def list_feedback_route():
    """GET /api/feedback/admin?since_id=N&limit=M — operator readback of
    captured TestFlight feedback.

    Auth: same CRON_SECRET pattern as /api/cron/* (X-Cron-Secret header).
    Local dev with no CRON_SECRET set: open. Prod without CRON_SECRET:
    503 (fail closed).

    Response:
      {
        "items": [{id, client_id, screen, severity, text, user_id,
                   username, app_version, platform, device_type,
                   os_version, client_created_at, created_at}, ...],
        "count": N,
        "next_since_id": <max id in items, or input since_id when empty>
      }

    Poll with `since_id=<last next_since_id>` to stream new captures.
    """
    _require_cron_auth()
    try:
        since_id = int(request.args.get("since_id", 0))
    except (TypeError, ValueError):
        since_id = 0
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    items = list_feedback(since_id=since_id, limit=limit)
    next_since = items[-1]["id"] if items else since_id
    return jsonify({"items": items, "count": len(items), "next_since_id": next_since})


@app.route("/api/feedback/admin/<int:feedback_id>/status", methods=["PUT"])
def set_feedback_status_route(feedback_id: int):
    """PUT /api/feedback/admin/<id>/status — operator update for one note.

    Auth: X-Cron-Secret (same as the admin readback). Body accepts either
    or both of:
      status    ∈ FEEDBACK_STATUSES — what the in-app inbox shows
      severity  ∈ FEEDBACK_SEVERITIES — reclassify a note's type (e.g. a
                  'bug' that is really an 'idea')
    """
    _require_cron_auth()
    body = request.get_json(force=True, silent=True) or {}
    status = body.get("status")
    severity = body.get("severity")
    if status is None and severity is None:
        return jsonify({"error": "missing_fields",
                        "expected": ["status", "severity"]}), 400
    if status is not None and status not in FEEDBACK_STATUSES:
        return jsonify({
            "error": "invalid_status",
            "allowed": list(FEEDBACK_STATUSES),
        }), 400
    if severity is not None and severity not in FEEDBACK_SEVERITIES:
        return jsonify({
            "error": "invalid_severity",
            "allowed": list(FEEDBACK_SEVERITIES),
        }), 400
    result = set_feedback_status(feedback_id, status=status, severity=severity)
    if result is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(result)


@app.route("/api/feedback/mine", methods=["GET"])
@_gate_unverified_read
def my_feedback_route():
    """GET /api/feedback/mine — the caller's own feedback notes with their
    lifecycle status (newest first). Read side of the in-app feedback
    widget's status chips. Requires a session; submission (POST
    /api/feedback) remains anonymous-friendly and is unchanged.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    try:
        items = list_feedback_for_user(sess["user_id"])
        return jsonify({"items": items, "count": len(items)})
    except Exception as e:
        log.exception("my_feedback_route failed")
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/tiers/save", methods=["POST"])
@_gate_unverified_write
def save_tiers_route():
    """POST /api/tiers/save {position: 'RB', tiers: {first_1: [...ids], ...}, cleared_pids: [...]}

    Converts tier assignments into ELO overrides and marks the position as saved.

    `cleared_pids` (optional): list of pids the user explicitly removed
    from all tiers (× button → back to pool). Their override is deleted
    so they don't snap back to a previous tier on the next refresh.
    """
    sess = _require_initialized_session()
    service   = sess["service"]
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    fmt       = _active_format(sess)
    body      = request.get_json(force=True) or {}
    position  = body.get("position")
    tiers     = body.get("tiers", {})
    cleared_pids = body.get("cleared_pids") or []
    if not isinstance(cleared_pids, list):
        cleared_pids = []
    cleared_pids = [str(x) for x in cleared_pids if x]

    if position not in ("QB", "RB", "WR", "TE"):
        return jsonify({"error": f"Invalid position: {position!r}"}), 400

    # Must have at least one player in some tier OR something to clear.
    # (Pure "clear-only" saves are valid — e.g. user removes their last
    # tier-placed RB; we still need to apply the deletion server-side.)
    total_assigned = sum(len(ids) for ids in tiers.values() if isinstance(ids, list))
    if total_assigned == 0 and not cleared_pids:
        return jsonify({"error": "No players in any tier"}), 400

    try:
        # apply_tiers assigns ELOs inside each tier's band (see
        # backend/tier_config.json) so on reload the frontend re-buckets
        # players into the same tier they were placed. Bands are
        # position+format-aware. cleared_pids lets the frontend tell us
        # "this player is back in the pool — drop their override".
        service.apply_tiers(
            position=position,
            tiers=tiers,
            scoring_format=fmt,
            cleared_pids=cleared_pids,
        )

        # Persist the full tier override dict for THIS format so it survives
        # session rebuilds. The other format's overrides are untouched.
        try:
            save_tier_overrides(g_user_id, service._elo_overrides, scoring_format=fmt)
        except Exception as db_err:
            log.warning("save_tier_overrides failed: %s", db_err)

        # Persist updated ELO snapshot to member_rankings (per-format row) so
        # leaguemates see this rank set when generating trades in this format.
        try:
            if g_league and g_league.league_id not in ("league_demo",):
                all_rankings = service.get_rankings(position=None)
                ranking_payload = [
                    {"player_id": rp.player.id, "elo": rp.elo}
                    for rp in all_rankings.rankings
                ]
                upsert_member_rankings(
                    user_id        = g_user_id,
                    league_id      = g_league.league_id,
                    rankings       = ranking_payload,
                    scoring_format = fmt,
                )
        except Exception as db_err:
            log.warning("member_rankings publish after tiers save failed: %s", db_err)

        # Mark this position as saved for the active format
        saved = save_tiers_position(g_user_id, position, scoring_format=fmt)
        all_done = all(p in saved for p in ("QB", "RB", "WR", "TE"))

        log.info("tiers/save [%s] %s for %s — saved: %s, all_done=%s",
                 fmt, position, g_user_id, saved, all_done)

        return jsonify({
            "ok":             True,
            "position":       position,
            "saved":          saved,
            "all_done":       all_done,
            "count":          total_assigned,
            "scoring_format": fmt,
        })
    except Exception as e:
        log.error("tiers/save error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/anchor/save", methods=["POST"])
@_gate_unverified_write
def save_anchor_route():
    """POST /api/anchor/save {player_id: '4046', anchor: '2_firsts'}

    Pick-anchor wizard: pin a player's Elo to a pick-denominated value
    statement ("worth 2 firsts", "worth a mid 2nd", "no trade value").
    Anchors are position-uniform by design — the pick ladder drives the
    same valuation across position groups, and tier assignment falls out
    of the pinned Elo via the normal band walk (tier_for_elo). Writes the
    same authoritative override apply_tiers uses, so the placement shows
    up on Tiers, in trade math, and for leaguemates immediately.
    """
    sess = _require_initialized_session()
    service   = sess["service"]
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    fmt       = _active_format(sess)
    body      = request.get_json(force=True) or {}
    player_id = str(body.get("player_id") or "").strip()
    anchor    = str(body.get("anchor") or "").strip()

    if not player_id:
        return jsonify({"error": "player_id required"}), 400
    if anchor not in VALID_ANCHORS:
        return jsonify({"error": f"Invalid anchor: {anchor!r}",
                        "valid_anchors": sorted(VALID_ANCHORS)}), 400

    # #111 — the user's pick-value scale re-spaces the multi-first anchors.
    # Best-effort read: any DB hiccup falls back to the legacy default.
    try:
        top_tier_firsts = (load_anchor_scale(g_user_id, scoring_format=fmt)
                           or ANCHOR_TOP_TIER_FIRSTS_DEFAULT)
    except Exception as db_err:
        log.warning("load_anchor_scale failed (using default): %s", db_err)
        top_tier_firsts = ANCHOR_TOP_TIER_FIRSTS_DEFAULT

    target_elo = _anchor_target_elo(anchor, top_tier_firsts=top_tier_firsts)

    try:
        player = service.apply_anchor(player_id, target_elo)
        if player is None:
            return jsonify({"error": f"Unknown player_id: {player_id}"}), 404

        # Persist the override dict for THIS format (same path as tiers/save)
        # so the anchor survives session rebuilds.
        try:
            save_tier_overrides(g_user_id, service._elo_overrides, scoring_format=fmt)
        except Exception as db_err:
            log.warning("save_tier_overrides after anchor failed: %s", db_err)

        # Publish the updated Elo snapshot so leaguemates' trade generation
        # sees the anchored value (mirrors tiers/save).
        try:
            if g_league and g_league.league_id not in ("league_demo",):
                all_rankings = service.get_rankings(position=None)
                ranking_payload = [
                    {"player_id": rp.player.id, "elo": rp.elo}
                    for rp in all_rankings.rankings
                ]
                upsert_member_rankings(
                    user_id        = g_user_id,
                    league_id      = g_league.league_id,
                    rankings       = ranking_payload,
                    scoring_format = fmt,
                )
        except Exception as db_err:
            log.warning("member_rankings publish after anchor failed: %s", db_err)

        tier = service.tier_for_elo(target_elo, player.position, fmt)
        log.info("anchor/save [%s] %s → %s (elo %.0f, tier %s) for %s",
                 fmt, player_id, anchor, target_elo, tier, g_user_id)

        return jsonify({
            "ok":              True,
            "player_id":       player_id,
            "anchor":          anchor,
            "elo":             round(target_elo, 1),
            "value":           round(_trade_service_mod.elo_to_value(target_elo), 1),
            "tier":            tier,
            "scoring_format":  fmt,
            "top_tier_firsts": top_tier_firsts,
        })
    except Exception as e:
        log.error("anchor/save error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/anchor/scale", methods=["GET", "POST"])
@_gate_unverified_write
@_gate_unverified_read
def anchor_scale_route():
    """GET/POST /api/anchor/scale — per-user pick-value scale (#111).

    {top_tier_firsts: 2|3|4} = "a top-tier dynasty asset is worth N firsts".
    Persisted per user + scoring format (users.anchor_scale). Recalibrates
    ONLY the anchor wizard's multi-first keys (see _anchor_target_elo);
    single-pick anchors, the generic pick assets in the pool, and the
    public calculator gap line stay consensus-denominated. Default 2 ==
    the legacy mapping, so users who never touch it see identical behavior.
    """
    sess = _require_session()
    g_user_id = sess["user_id"]
    fmt = _active_format(sess)

    if request.method == "GET":
        try:
            n = (load_anchor_scale(g_user_id, scoring_format=fmt)
                 or ANCHOR_TOP_TIER_FIRSTS_DEFAULT)
        except Exception as db_err:
            log.warning("anchor/scale read failed (using default): %s", db_err)
            n = ANCHOR_TOP_TIER_FIRSTS_DEFAULT
        return jsonify({"top_tier_firsts": n, "scoring_format": fmt})

    body = request.get_json(force=True) or {}
    try:
        n = float(body.get("top_tier_firsts"))
    except (TypeError, ValueError):
        return jsonify({"error": "top_tier_firsts must be a number",
                        "valid_values": list(ANCHOR_TOP_TIER_FIRSTS_CHOICES)}), 400
    if n not in ANCHOR_TOP_TIER_FIRSTS_CHOICES:
        return jsonify({"error": f"Invalid top_tier_firsts: {n!r}",
                        "valid_values": list(ANCHOR_TOP_TIER_FIRSTS_CHOICES)}), 400
    try:
        save_anchor_scale(g_user_id, n, scoring_format=fmt)
    except Exception as e:
        log.error("anchor/scale save error: %s", e)
        return jsonify({"error": "internal_error"}), 500
    log.info("anchor/scale [%s] top_tier_firsts=%s for %s", fmt, n, g_user_id)
    return jsonify({"ok": True, "top_tier_firsts": n, "scoring_format": fmt})


@app.route("/api/tiers/status")
@_gate_unverified_read
def tiers_status_route():
    """GET /api/tiers/status — which positions have saved tiers for the active format."""
    sess = _require_session()
    g_user_id = sess["user_id"]
    fmt = _active_format(sess)
    try:
        saved = get_tiers_saved(g_user_id, scoring_format=fmt)
        return jsonify({
            "saved":    saved,
            "all_done": all(p in saved for p in ("QB", "RB", "WR", "TE")),
            # FB-76: the mobile Tiers screen re-buckets by ELO thresholds
            # and needs the session's active format. It always read this
            # field; the route never sent it, so SF leagues fell back to
            # 1qb_ppr thresholds and QB/TE tier saves displayed one tier
            # high after the round-trip.
            "scoring_format": fmt,
        })
    except Exception as e:
        log.exception("tiers_status_route failed")
        return jsonify({"error": "internal_error"}), 500


# ---------------------------------------------------------------------------
# Agent A2 — Tier UX helper endpoints (flag-gated; default-off)
# ---------------------------------------------------------------------------
# /api/tiers/community-diff — returns {player_id: {user_tier, community_tier}}
#   community_tier is derived from the *universal seed ELO* (the consensus
#   starting point before any swipes/overrides) using RankingService.tier_for_elo
#   so it represents "where the market places this player" independent of the
#   active user's own rank-set.
#
# /api/tiers/stability — returns {player_id: "stable" | "volatile"}
#   Reads elo_history for the last 30 days, counts the number of distinct
#   tier buckets the user's ELO has fallen into per player, and labels:
#       1 distinct tier  → stable
#       3+ distinct tiers → volatile
#       2 distinct tiers  → (omitted — no badge)
# ---------------------------------------------------------------------------

@app.route("/api/tiers/community-diff")
@_gate_unverified_read
def tiers_community_diff_route():
    """GET /api/tiers/community-diff?position=RB
    → { position, scoring_format, diffs: {player_id: {user_tier, community_tier}} }

    Flag-gated by tiers.community_diff. When flag is off, returns an empty
    diffs map so the frontend (which also gates) never shows the overlay.
    """
    if not is_enabled("tiers.community_diff"):
        return jsonify({
            "position":       request.args.get("position") or "",
            "scoring_format": "",
            "diffs":          {},
            "disabled":       True,
        })

    sess = _require_session()
    sess["last_active"] = time.time()
    service = sess["service"]
    fmt = _active_format(sess)
    position = request.args.get("position") or None
    if position not in ("QB", "RB", "WR", "TE"):
        return jsonify({"error": f"Invalid position: {position!r}"}), 400

    try:
        # User ELO comes from the active service's rankings (applies overrides
        # + replayed swipes).
        rank_set = service.get_rankings(position=position)
    except Exception as e:
        log.exception("tiers_community_diff_route failed")
        return jsonify({"error": "bad_request"}), 400

    # Community ELO is the universal seed for this format — the consensus
    # "starting point" before the user touched anything.
    try:
        _, community_seed = _get_universal_pool(fmt)
    except Exception as e:
        log.warning("community-diff seed fetch failed: %s", e)
        community_seed = {}

    diffs: dict[str, dict] = {}
    for rp in rank_set.rankings:
        pid = rp.player.id
        user_elo = getattr(rp, "elo", None)
        comm_elo = community_seed.get(pid)
        user_tier = RankingService.tier_for_elo(user_elo, position, fmt) if user_elo is not None else None
        comm_tier = RankingService.tier_for_elo(comm_elo, position, fmt) if comm_elo is not None else None
        # Only include players where we have at least one tier assignment —
        # otherwise the overlay has nothing useful to show.
        if user_tier is None and comm_tier is None:
            continue
        diffs[pid] = {
            "user_tier":      user_tier,
            "community_tier": comm_tier,
        }

    return jsonify({
        "position":       position,
        "scoring_format": fmt,
        "diffs":          diffs,
    })


@app.route("/api/tiers/stability")
@_gate_unverified_read
def tiers_stability_route():
    """GET /api/tiers/stability?position=RB
    → { position, scoring_format, stability: {player_id: "stable" | "volatile"} }

    Flag-gated by tiers.stability_indicator. Reads elo_history for the last
    30 days, buckets each snapshot via RankingService.tier_for_elo, and
    classifies players:
        1 distinct tier       → "stable"
        3+ distinct tiers     → "volatile"
        2 distinct tiers      → (omitted)
        <2 total snapshots    → (omitted — insufficient data)
    """
    if not is_enabled("tiers.stability_indicator"):
        return jsonify({
            "position":       request.args.get("position") or "",
            "scoring_format": "",
            "stability":      {},
            "disabled":       True,
        })

    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    fmt = _active_format(sess)
    position = request.args.get("position") or None
    if position not in ("QB", "RB", "WR", "TE"):
        return jsonify({"error": f"Invalid position: {position!r}"}), 400

    try:
        history = load_elo_history(
            user_id        = g_user_id,
            scoring_format = fmt,
            since_days     = 30,
            league_id      = g_league.league_id if g_league else None,
        )
    except Exception as e:
        log.warning("tiers/stability: load_elo_history failed: %s", e)
        history = []

    # Bucket each snapshot into a tier keyed by player_id. We only look at
    # rows for players that belong to the requested position — cheap filter
    # via the session's pool.
    try:
        pool_players = sess["service"]._pool(position)
        valid_pids = {p.id for p in pool_players}
    except Exception:
        valid_pids = set()

    # player_id → set(tier_name)
    tiers_seen: dict[str, set] = {}
    counts: dict[str, int] = {}
    for row in history:
        pid = row.get("player_id")
        if not pid:
            continue
        if valid_pids and pid not in valid_pids:
            continue
        elo = row.get("elo")
        tier = RankingService.tier_for_elo(elo, position, fmt)
        if tier is None:
            continue
        tiers_seen.setdefault(pid, set()).add(tier)
        counts[pid] = counts.get(pid, 0) + 1

    stability: dict[str, str] = {}
    for pid, tier_set in tiers_seen.items():
        if counts.get(pid, 0) < 2:
            # Need at least 2 snapshots before we label anything.
            continue
        distinct = len(tier_set)
        if distinct == 1:
            stability[pid] = "stable"
        elif distinct >= 3:
            stability[pid] = "volatile"
        # distinct == 2 → no badge (neutral)

    return jsonify({
        "position":       position,
        "scoring_format": fmt,
        "stability":      stability,
    })


@app.route("/api/reset", methods=["POST"])
@_gate_unverified_write
def reset():
    """POST /api/reset  {position: "RB"}"""
    sess = _require_session()
    sess["last_active"] = time.time()
    service = sess["service"]
    body     = request.get_json(force=True) or {}
    position = body.get("position") or None
    return jsonify(service.reset(position=position))


@app.route("/api/rankings/reorder", methods=["POST"])
@_gate_unverified_write
def reorder_rankings():
    """POST /api/rankings/reorder {position, ordered_ids}

    Apply a manual reorder to the user's rankings.  The ordered_ids list
    represents the user's desired ranking from best (index 0) to worst.
    ELO values are overridden to match the desired order.
    """
    sess = _require_initialized_session()
    service    = sess["service"]
    g_user_id  = sess["user_id"]
    g_league   = sess["league"]
    fmt        = _active_format(sess)
    body       = request.get_json(force=True) or {}
    position   = body.get("position")   # None = overall
    ordered_ids = body.get("ordered_ids", [])

    if len(ordered_ids) < 2:
        return jsonify({"error": "Need at least 2 player IDs"}), 400

    try:
        service.apply_reorder(position=position, ordered_ids=ordered_ids)
        try:
            from .wrapped_collector import record_event
            record_event(g_user_id, getattr(g_league, "league_id", None),
                         "ranking_reorder",
                         {"position": position, "count": len(ordered_ids),
                          "scoring_format": fmt})
        except Exception: pass

        # Persist override dict for THIS format so it survives session rebuilds
        try:
            save_tier_overrides(g_user_id, service._elo_overrides, scoring_format=fmt)
        except Exception as db_err:
            log.warning("save_tier_overrides after reorder failed: %s", db_err)

        # Persist updated ELO snapshot for this format
        try:
            if g_league and g_league.league_id not in ("league_demo",):
                all_rankings = service.get_rankings(position=None)
                ranking_payload = [
                    {"player_id": rp.player.id, "elo": rp.elo}
                    for rp in all_rankings.rankings
                ]
                upsert_member_rankings(
                    user_id        = g_user_id,
                    league_id      = g_league.league_id,
                    rankings       = ranking_payload,
                    scoring_format = fmt,
                )
        except Exception as db_err:
            log.warning("member_rankings publish after reorder failed: %s", db_err)

        return jsonify({"ok": True, "count": len(ordered_ids), "scoring_format": fmt})
    except Exception as e:
        log.error("reorder_rankings error: %s", e)
        return jsonify({"error": "bad_request"}), 400


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/privacy")
def privacy_page():
    """Clean URL for the privacy policy (also the App Store Connect URL)."""
    return send_from_directory(app.static_folder, "privacy.html")


@app.route("/terms")
def terms_page():
    """Clean URL for the terms of use."""
    return send_from_directory(app.static_folder, "terms.html")


# ---------------------------------------------------------------------------
# Player DB Routes
# ---------------------------------------------------------------------------

# Column projection views for GET /api/players?view=<name>.
# Each entry lists exactly the DB column names to SELECT.
# 'full' / omitted: all columns (backward-compatible default).
_PLAYER_VIEWS: dict[str, list[str]] = {
    # Tier-board / pool display: id, name, position, team, age, relevance rank.
    "summary": [
        "player_id", "full_name", "position", "team", "age", "search_rank",
    ],
    # Rank/swipe info-sheet: adds experience, injury, ADP.
    "detail": [
        "player_id", "full_name", "first_name", "last_name",
        "position", "team", "age", "years_exp",
        "injury_status", "adp", "search_rank",
    ],
}


@app.route("/api/players")
def get_players_route():
    """
    GET /api/players?position=RB[&view=summary|detail|full]

    Returns synced players from the DB, optionally filtered by position.

    ``view`` controls which fields are returned:
      - ``summary`` — id, name, position, team, age, search_rank (6 fields)
      - ``detail``  — adds years_exp, injury_status, adp (11 fields)
      - ``full`` or omitted — all columns, backward-compatible default

    Responses include ETag and Cache-Control headers so browsers serve
    repeat requests from disk (player data changes at most once per day).
    """
    position = request.args.get("position") or None
    view     = (request.args.get("view") or "full").lower()
    columns  = _PLAYER_VIEWS.get(view)   # None → select all (full)
    try:
        players  = load_players(position=position, columns=columns)
        payload  = json.dumps(players)
        etag     = '"' + hashlib.md5(payload.encode()).hexdigest()[:16] + '"'

        if request.headers.get("If-None-Match") == etag:
            return "", 304

        resp = make_response(payload, 200)
        resp.headers["Content-Type"]  = "application/json"
        resp.headers["ETag"]          = etag
        resp.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
        return resp
    except Exception as e:
        log.error("get_players error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/players/<player_id>")
def get_player_route(player_id):
    """
    GET /api/players/<player_id>
    Returns full detail for a single player by Sleeper player_id.
    """
    try:
        player = load_player(player_id)
        if player is None:
            return jsonify({"error": "Player not found"}), 404
        return jsonify(player)
    except Exception as e:
        log.error("get_player error (%s): %s", player_id, e)
        return jsonify({"error": "internal_error"}), 500


# ---------------------------------------------------------------------------
# Manual Trade Calculator (docs/plans/manual-trade-calculator-plan.md)
# Open, consensus-basis endpoints — no session, no league. Values come from
# the same universal pool + elo_to_value transform the finder trades on, and
# fairness reuses trade_optimizer._fairness_v3, so the calculator's numbers
# cannot disagree with generated trades.
# ---------------------------------------------------------------------------

_CALC_MAX_SIDE = 6   # assets per side — matches the engine's practical bounds


def _calc_scoring_format(raw) -> str:
    fmt = raw.strip() if isinstance(raw, str) else ""
    return fmt if fmt in SCORING_FORMATS else DEFAULT_SCORING


@app.route("/api/trade/values")
def trade_calc_values_route():
    """
    GET /api/trade/values?scoring_format=1qb_ppr|sf_tep

    Consensus value list for the manual trade calculator: every universal-
    pool player (id, name, position, team, age) plus their consensus value —
    elo_to_value over the pool's seed Elo, the exact per-player numbers the
    trade engine prices with. Open endpoint; ETag/Cache-Control like
    /api/players (values change at most daily).
    """
    fmt = _calc_scoring_format(request.args.get("scoring_format"))
    try:
        pool_players, seed = _get_universal_pool(fmt)
        e2v = _trade_service_mod.elo_to_value
        rows = [{
            "id":       p.id,
            "name":     p.name,
            "position": p.position,
            "team":     getattr(p, "team", None),
            "age":      getattr(p, "age", None),
            "value":    round(e2v(seed.get(p.id, 1500.0)), 1),
        } for p in pool_players]
        rows.sort(key=lambda r: r["value"], reverse=True)
        payload = json.dumps({"scoring_format": fmt, "players": rows})
        etag = '"' + hashlib.md5(payload.encode()).hexdigest()[:16] + '"'
        if request.headers.get("If-None-Match") == etag:
            return "", 304
        resp = make_response(payload, 200)
        resp.headers["Content-Type"]  = "application/json"
        resp.headers["ETag"]          = etag
        resp.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
        return resp
    except Exception as e:
        log.error("trade_calc_values error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/trade/evaluate", methods=["POST"])
def trade_evaluate_route():
    """
    POST /api/trade/evaluate
    Body: {give_player_ids: [...], receive_player_ids: [...],
           scoring_format?: '1qb_ppr'|'sf_tep', fairness_threshold?: float,
           league_id?: str, opponent_user_id?: str}

    Mode A (default — no auth, no league): consensus values + fairness verdict
    for a hand-built trade. Reuses trade_optimizer._consensus_packages/
    _fairness_v3 over the universal pool so the numbers match the finder's.
    confidence=None degrades the range-overlap gate to the point-ratio gate.
    Unvalued ids are dropped and reported (the engine's graceful-drop rule).

    Mode B (when league_id + opponent_user_id given — requires a session): adds
    the two-sided, both-boards read. Prices each side by the CALLER'S rankings
    and the OPPONENT'S rankings (member_rankings), returning per-board deltas +
    `mutual_gain` + `basis` ('divergence', or 'consensus' when the opponent
    hasn't ranked). This is the finder's mutual-gain math applied to one fixed
    package — a directed, manual counterpart to trade generation.
    """
    from .trade_optimizer import _consensus_packages, _fairness_v3

    body = request.get_json(silent=True) or {}
    give_raw = body.get("give_player_ids") or []
    recv_raw = body.get("receive_player_ids") or []
    if not isinstance(give_raw, list) or not isinstance(recv_raw, list):
        return jsonify({"error": "give_player_ids / receive_player_ids must be lists"}), 400
    give_raw = [str(x) for x in give_raw if x][:_CALC_MAX_SIDE]
    recv_raw = [str(x) for x in recv_raw if x][:_CALC_MAX_SIDE]
    if not give_raw and not recv_raw:
        return jsonify({"error": "at least one player id required"}), 400

    fmt = _calc_scoring_format(body.get("scoring_format"))
    try:
        thr = float(body.get("fairness_threshold", 0.75))
    except (TypeError, ValueError):
        thr = 0.75
    thr = min(max(thr, 0.5), 1.0)

    # Mode B (in-league, both boards): triggered by league_id + opponent_user_id.
    # Requires a session (needs the caller's + opponent's member_rankings).
    # Resolved OUTSIDE the try so a missing session yields 401, not a 500.
    league_id = str(body.get("league_id") or "").strip()
    opponent_user_id = str(body.get("opponent_user_id") or "").strip()
    mode_b = bool(league_id and opponent_user_id)
    caller_user_id = None
    if mode_b:
        # Mode B prices by the CALLER's board — board-derived content, so the
        # read gate applies inline (the route can't take @_gate_unverified_read
        # wholesale because Mode A is public by design).
        _mode_b_sess = _require_session()
        _read_denial = _verified_read_denial(_mode_b_sess)
        if _read_denial is not None:
            return _read_denial
        caller_user_id = _mode_b_sess.get("user_id")

    try:
        _pool_players, seed = _get_universal_pool(fmt)
        e2v = _trade_service_mod.elo_to_value

        def seed_value(pid: str) -> float:
            return e2v(seed.get(pid, 1500.0))

        give    = [p for p in give_raw if p in seed]
        recv    = [p for p in recv_raw if p in seed]
        dropped = [p for p in give_raw + recv_raw if p not in seed]

        per_player = [
            {"player_id": pid, "side": side, "value": round(seed_value(pid), 1)}
            for side, ids in (("give", give), ("receive", recv))
            for pid in ids
        ]

        give_value = receive_value = 0.0
        point_ratio = fairness = verdict = favors = None
        if give or recv:
            gv, rv = _consensus_packages(give, recv, seed_value)
            give_value, receive_value = round(gv, 1), round(rv, 1)
        if give and recv:
            fairness, point_ratio, _gv, _rv = _fairness_v3(
                give, recv, seed_value, None, thr)
            if point_ratio >= 0.95:
                verdict, favors = "even", "even"
            else:
                verdict = "fair" if fairness is not None else "unfair"
                favors = "receive" if receive_value > give_value else "give"

        # Pick-denominated gap read: how far apart the packages are, expressed
        # as generic-pick equivalents ("≈ a Mid 2nd") so the delta is an
        # actionable counteroffer instead of an abstract number. `add_to` is
        # the LIGHTER side — the one that needs the sweetener.
        gap = None
        if give and recv:
            gap_val = abs(receive_value - give_value)
            gap = {
                "value":  round(gap_val, 1),
                "add_to": (None if gap_val == 0
                           else "give" if give_value < receive_value
                           else "receive"),
                **_pick_gap_equivalent(gap_val),
            }

        result = {
            "scoring_format":     fmt,
            "give_value":         give_value,
            "receive_value":      receive_value,
            "point_ratio":        point_ratio,
            "fairness":           fairness,
            "verdict":            verdict,
            "favors":             favors,
            "gap":                gap,
            "per_player":         per_player,
            "dropped_player_ids": dropped,
            "basis":              "consensus",
        }

        # ── Mode B — in-league, both owners' boards ──────────────────────────
        # Reuse the finder's per-package math (_consensus_packages) once per
        # board: the caller's rankings and the opponent's, from member_rankings.
        # Each board's value fn falls back to the consensus seed for players
        # that owner hasn't ranked — so an unranked opponent degrades to a
        # consensus read with no special-casing (basis flips to 'consensus').
        if mode_b:
            from .database import load_member_rankings
            boards = load_member_rankings(league_id, exclude_user_id="", scoring_format=fmt)
            user_elo = (boards.get(caller_user_id) or {}).get("elo_ratings") or {}
            opp_entry = boards.get(opponent_user_id) or {}
            opp_elo = opp_entry.get("elo_ratings") or {}
            opp_has_rankings = bool(opp_elo)

            def _board_value(elo_map):
                return lambda pid: e2v(elo_map.get(pid, seed.get(pid, 1500.0)))

            gv_u = rv_u = gv_o = rv_o = 0.0
            if give or recv:
                gv_u, rv_u = _consensus_packages(give, recv, _board_value(user_elo))
                gv_o, rv_o = _consensus_packages(give, recv, _board_value(opp_elo))
            your_delta  = round(rv_u - gv_u, 1)   # you receive rv, give gv — by YOUR board
            their_delta = round(gv_o - rv_o, 1)   # they receive the give side, give up the receive side — by THEIR board

            result.update({
                "basis":                 "divergence" if opp_has_rankings else "consensus",
                "opponent_user_id":      opponent_user_id,
                "opponent_username":     opp_entry.get("username"),
                "opponent_has_rankings": opp_has_rankings,
                "your_give_value":       round(gv_u, 1),
                "your_receive_value":    round(rv_u, 1),
                "their_give_value":      round(gv_o, 1),
                "their_receive_value":   round(rv_o, 1),
                "your_value_delta":      your_delta,
                "their_value_delta":     their_delta,
                "mutual_gain":           bool(your_delta > 0 and their_delta > 0),
            })

        return jsonify(result)
    except Exception as e:
        log.error("trade_evaluate error: %s", e)
        return jsonify({"error": "internal_error"}), 500


def _delta_since(history: list[dict], current: float, days: int) -> float | None:
    """Consensus-value delta vs the oldest snapshot within `days`.

    `history` is oldest-first (load_value_history). Returns None when there is
    no snapshot old enough to compare against (chart started too recently).
    """
    if not history:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    prior = [h for h in history if h["snapshot_date"] <= cutoff
             and h.get("consensus_value") is not None]
    base = prior[-1] if prior else None
    if base is None:
        return None
    return round(current - base["consensus_value"], 1)


def _user_player_elo(user_id: str, player_id: str, scoring_format: str) -> tuple[float | None, int]:
    """The session user's personal Elo for one player, averaged across the
    leagues they've ranked in this format, with the number of ranking sets it
    came from. (None, 0) when the user has never ranked this player."""
    from .database import member_rankings_table, engine as _engine
    from sqlalchemy import select as _select
    with _engine.connect() as conn:
        rows = conn.execute(
            _select(member_rankings_table.c.elo).where(
                (member_rankings_table.c.user_id   == user_id) &
                (member_rankings_table.c.player_id == str(player_id)) &
                ((member_rankings_table.c.scoring_format == scoring_format) |
                 (member_rankings_table.c.scoring_format.is_(None)))
            )
        ).fetchall()
    elos = [r.elo for r in rows if r.elo is not None]
    if not elos:
        return None, 0
    return sum(elos) / len(elos), len(elos)


@app.route("/api/players/<player_id>/profile")
def get_player_profile_route(player_id):
    """GET /api/players/<id>/profile — the player-profile aggregate (#17).

    Identity + consensus value with trend deltas/extremes + the caller's
    you-vs-market diff + zipped value history + recent appearances in the
    caller's own suggestions. Gated by the players.profile_pages flag.
    """
    if not is_enabled("players.profile_pages"):
        return jsonify({"error": "not_enabled"}), 404
    try:
        sess = _require_session()
    except _SessionExpired:
        return jsonify({"error": "session_expired"}), 401

    player = load_player(player_id)
    if player is None:
        return jsonify({"error": "Player not found"}), 404

    fmt     = sess.get("_effective_format", DEFAULT_SCORING)
    user_id = sess["user_id"]
    from .trade_service import elo_to_value

    # ── consensus: current value from the live pool, history/extremes from the
    #    snapshot table (#57). Current may lead the last snapshot by <1 day. ──
    _ensure_universal_pools()
    pool = g_universal_by_format.get(fmt) or {}
    seed = pool.get("seed") or {}
    cur_elo = seed.get(str(player_id))
    cur_val = round(elo_to_value(float(cur_elo)), 1) if cur_elo is not None else None
    history = load_value_history(player_id, fmt, since_days=120)
    extremes = load_value_extremes(player_id, fmt)
    consensus = {
        "value":          cur_val,
        "elo":            round(float(cur_elo), 1) if cur_elo is not None else None,
        "delta_7d":       _delta_since(history, cur_val, 7)  if cur_val is not None else None,
        "delta_30d":      _delta_since(history, cur_val, 30) if cur_val is not None else None,
        "delta_90d":      _delta_since(history, cur_val, 90) if cur_val is not None else None,
        "high":           (extremes or {}).get("high"),
        "low":            (extremes or {}).get("low"),
        "tracking_since": (extremes or {}).get("tracking_since"),
    }

    # ── you vs market ──
    your_elo, comparisons = _user_player_elo(user_id, player_id, fmt)
    you_vs_market = None
    if your_elo is not None and cur_val:
        your_val = round(elo_to_value(your_elo), 1)
        diff_pct = round((your_val - cur_val) / cur_val, 3) if cur_val else 0.0
        you_vs_market = {
            "your_value":   your_val,
            "market_value": cur_val,
            "diff_pct":     diff_pct,
            "state":        "higher" if diff_pct > 0.05 else
                            "lower"  if diff_pct < -0.05 else "aligned",
            "comparisons":  comparisons,
        }

    # ── zipped history series (consensus + the user's personal Elo) ──
    your_hist = {
        h["player_id"] and h["snapshot_at"][:10]: h["elo"]
        for h in load_elo_history(user_id, fmt, since_days=120)
        if str(h["player_id"]) == str(player_id)
    }
    series = [
        {"date": h["snapshot_date"],
         "consensus_value": h.get("consensus_value"),
         "your_value": round(elo_to_value(your_hist[h["snapshot_date"]]), 1)
                       if h["snapshot_date"] in your_hist else None}
        for h in history
    ]

    # ── recent appearances in THIS user's suggestions (LIKE scan, fine at
    #    current impression volume; see #17 LLD open question) ──
    from .database import trade_impressions_table, engine as _engine
    from sqlalchemy import select as _select, desc as _desc
    pid_token = f'%"{player_id}"%'
    with _engine.connect() as conn:
        imp_rows = conn.execute(
            _select(trade_impressions_table).where(
                (trade_impressions_table.c.user_id == user_id) &
                (trade_impressions_table.c.give_player_ids.like(pid_token) |
                 trade_impressions_table.c.receive_player_ids.like(pid_token))
            ).order_by(_desc(trade_impressions_table.c.shown_at)).limit(5)
        ).fetchall()
    recent = []
    for r in imp_rows:
        try:
            give = json.loads(r.give_player_ids or "[]")
        except Exception:
            give = []
        recent.append({
            "league_id":    r.league_id,
            "counterparty": r.target_user_id,
            "side":         "give" if str(player_id) in [str(x) for x in give] else "receive",
            "basis":        r.basis,
            "shown_at":     r.shown_at,
        })

    return jsonify({
        "player": {
            "player_id":     player["player_id"],
            "full_name":     player.get("full_name"),
            "position":      player.get("position"),
            "team":          player.get("team"),
            "age":           player.get("age"),
            "years_exp":     player.get("years_exp"),
            "injury_status": player.get("injury_status"),
        },
        "consensus":          consensus,
        "you_vs_market":      you_vs_market,
        "history":            series,
        "recent_suggestions": recent,
    })


@app.route("/api/rookies")
def get_rookies_route():
    """
    GET /api/rookies
    Returns all rookie / pre-draft prospect players from the DB for the
    dynasty rookie draft board.  Includes:
      • players with years_exp = 0 (first-year players)
      • players with years_exp IS NULL (undrafted prospects)
    Grouped by position in the response for easy frontend rendering.
    """
    try:
        rookies = load_rookies()
        # Group by position for convenient frontend rendering
        grouped: dict[str, list] = {"QB": [], "RB": [], "WR": [], "TE": []}
        for r in rookies:
            pos = r.get("position", "")
            if pos in grouped:
                grouped[pos].append(r)
        return jsonify({"grouped": grouped, "total": len(rookies)})
    except Exception as e:
        log.error("get_rookies error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/picks")
def get_league_picks():
    """
    GET /api/league/picks?league_id=...
    Returns all draft pick assets currently held by the logged-in user in
    the specified league, along with the full league pick state so the
    frontend can show which picks opponents hold.
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_league  = sess["league"]
    g_user_id = sess["user_id"]
    league_id = request.args.get("league_id") or (g_league.league_id if g_league else None)
    if not league_id or league_id == "league_demo":
        return jsonify({"my_picks": [], "all_picks": []})
    try:
        all_picks = load_draft_picks(league_id=league_id)
        my_picks  = [p for p in all_picks if p.get("owner_user_id") == g_user_id]
        return jsonify({"my_picks": my_picks, "all_picks": all_picks})
    except Exception as e:
        log.error("get_league_picks error: %s", e)
        return jsonify({"error": "internal_error"}), 500


# ---------------------------------------------------------------------------
# Trade API Routes
# ---------------------------------------------------------------------------

def trade_card_to_dict(card, players: dict) -> dict:
    def p(pid):
        pl = players.get(pid)
        return player_to_dict(pl) if pl else {"id": pid, "name": "Unknown",
                                               "position": "?", "team": "?", "age": 0}
    out = {
        "trade_id":          card.trade_id,
        "league_id":         card.league_id,
        # FB-46: clients echo this back on /api/trades/swipe so a card can
        # be reconstructed (and match detection still works) after a server
        # restart wipes the in-memory deck.
        "target_user_id":    card.target_user_id,
        "target_username":   card.target_username,
        "give":              [p(pid) for pid in card.give_player_ids],
        "receive":           [p(pid) for pid in card.receive_player_ids],
        "mismatch_score":    card.mismatch_score,
        # P1-9: true fairness in [0,1] — mobile's fairness meter
        # (mobile/src/api/trades.ts, TradeCard.tsx) reads this field and
        # multiplies by 100; it was never serialized before.
        "fairness_score":    card.fairness_score,
        "composite_score":   card.composite_score,
        # v2 cards may be consensus/need-based vs. disagreement-driven.
        "basis":             getattr(card, "basis", "divergence"),
        "decision":          card.decision,
        "expires_at":        card.expires_at,
    }
    # Tier 2 (2.3a) — only serialized when true so payloads for ordinary
    # cards stay byte-identical to the pre-likes-you shape.
    if getattr(card, "likes_you", False):
        out["likes_you"] = True
    # Tier 3 (3.4) — sweetener annotation, only when present. The sweetener
    # player is already inside the give/receive arrays; this identifies it.
    sweetener = getattr(card, "sweetener", None)
    if sweetener:
        out["sweetener"] = sweetener
    # FB-47 — counterparty positional fit, only when targeting stamped it.
    partner_fit = getattr(card, "partner_fit", None)
    if partner_fit is not None:
        out["partner_fit"] = partner_fit
    # FB-96 — automatic positional-need fit, only when the flag stamped it.
    need_fit = getattr(card, "need_fit", None)
    if need_fit is not None:
        out["need_fit"] = need_fit
    # Interview phase 2 — two-lane label ("window" | "value"), only when
    # trade.lanes stamped it (user has a resolved window).
    lane = getattr(card, "lane", None)
    if lane:
        out["lane"] = lane
    # Interview phase 2 — honest fit-premium flag: {value_paid, position}.
    fit_premium = getattr(card, "fit_premium", None)
    if fit_premium:
        out["fit_premium"] = fit_premium
    # Interview phase 2 — aggression A/B bucket, for event joins.
    aggression_variant = getattr(card, "aggression_variant", None)
    if aggression_variant:
        out["aggression_variant"] = aggression_variant
    # Agent A8 — expose human-readable reasons only when the flag is on
    # AND the card actually has some. Keeps legacy JSON identical when off.
    reasons = getattr(card, "reasons", None)
    if reasons:
        try:
            from .feature_flags import FLAGS as _FLAGS
            if _FLAGS.trade_math_human_explanations:
                out["reasons"] = list(reasons)
        except Exception:
            pass
    # Feature 1 + 2 — templated narrative + structured roster-aware match context.
    narrative = getattr(card, "narrative", None)
    if narrative:
        out["narrative"] = narrative
    match_context = getattr(card, "match_context", None)
    if match_context:
        out["match_context"] = match_context
    return out


@app.route("/api/trades/generate", methods=["POST"])
@_gate_unverified_write
def generate_trades():
    """POST /api/trades/generate
    Spawns (or reuses) a background trade-generation job and returns a
    snapshot. The actual matching algorithm runs asynchronously; the
    mobile client polls /api/trades/status?job_id=X to stream cards as
    they're generated.

    Response shape (TradeJobSnapshot):
      {
        job_id, status: 'running'|'complete'|'error',
        opponents_done, opponents_total,
        cards: [...],          # public trade card dicts (may be partial)
        error: str | null,
      }

    Caching:
      - A complete job for the same (user, league, format) within 30 min
        is returned instantly with status='complete'.
      - In-flight jobs are shared across concurrent callers — second tap
        gets the same job_id and the current snapshot.
      - Pinned-give jobs always create a fresh, uncached job.
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    if not (g_user_id and g_league):
        return jsonify({"error": "session missing user/league"}), 400

    body               = request.get_json(force=True) or {}
    league_id          = body.get("league_id") or g_league.league_id
    pinned_give        = body.get("pinned_give_players") or []
    # FB-47 — "I want to acquire X". Honored only when trade.finder_targeting
    # is on so flag-off behavior stays byte-identical for any early client.
    pinned_receive     = (body.get("pinned_receive_players") or []
                          if is_enabled("trade.finder_targeting") else [])
    _any_pinned        = bool(pinned_give) or bool(pinned_receive)
    # Default to 50% when pinned players are selected (wide net), 75% otherwise
    default_fairness   = 0.50 if _any_pinned else 0.75
    fairness_threshold = float(body.get("fairness_threshold", default_fairness))
    fmt                = _active_format(sess)

    # Read current outlook for cache-freshness comparison. The actual job
    # worker reads it again; this is just for the cache hit decision. Must
    # resolve declared-else-seeded identically to the worker (#8) or every
    # seeded-league cache check would miss.
    try:
        prefs = load_league_preference(user_id=g_user_id, league_id=league_id)
        outlook_value = (prefs or {}).get("team_outlook")
        if not outlook_value:
            seeded, _sig = _infer_user_outlook(g_user_id, league_id, sess, g_league)
            if seeded:
                outlook_value = seeded
    except Exception:
        outlook_value = None

    sess_token = request.headers.get("X-Session-Token", "")
    key        = _trade_job_key(g_user_id, league_id, fmt)

    # Opponent count for early progress reporting (best-effort).
    opponents_total = 0
    try:
        opponents_total = sum(
            1 for m in g_league.members
            if m.user_id != g_user_id and m.elo_ratings
        )
    except Exception:
        pass

    with _trade_jobs_lock:
        existing_id = _trade_jobs_by_key.get(key) if not _any_pinned else None
        existing    = _trade_jobs.get(existing_id) if existing_id else None

        if existing and not _any_pinned:
            # Cache hit: complete + fresh + same params → return instantly.
            if _trade_job_is_fresh(existing, fairness_threshold, outlook_value):
                return jsonify(_trade_job_public_view(existing))
            # In-flight: share the current job. Note: if the request used
            # different fairness/outlook, the snapshot will reflect the
            # original params — the frontend can re-tap once status flips.
            if existing.get("status") == "running":
                return jsonify(_trade_job_public_view(existing))
            # Otherwise: stale or errored → drop the index entry and fall
            # through to spawn a new job.
            _trade_jobs_by_key.pop(key, None)

    # Kick off a fresh job. No locks held during the worker spawn so we
    # don't accidentally serialize parallel users.
    job_id = _kickoff_trade_job(
        sess_token         = sess_token,
        user_id            = g_user_id,
        league_id          = league_id,
        scoring_format     = fmt,
        fairness_threshold = fairness_threshold,
        pinned_give        = pinned_give or None,
        pinned_receive     = pinned_receive or None,
        opponents_total    = opponents_total,
    )
    with _trade_jobs_lock:
        snapshot = _trade_job_public_view(_trade_jobs[job_id])
    return jsonify(snapshot)


@app.route("/api/trades/status")
@_gate_unverified_read
def trade_job_status():
    """GET /api/trades/status?job_id=X
    Cheap dict lookup. Used by the mobile app to poll an in-flight
    /api/trades/generate job. 404 if the job has been evicted."""
    sess = _require_session()
    sess["last_active"] = time.time()
    job_id = request.args.get("job_id") or ""
    with _trade_jobs_lock:
        job = _trade_jobs.get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        # Defense: don't leak another user's job. The lookup key includes
        # user_id, but we double-check here in case of a stale id.
        if job["key"][0] != sess["user_id"]:
            return jsonify({"error": "job not found"}), 404
        return jsonify(_trade_job_public_view(job))


@app.route("/api/trades")
@_gate_unverified_read
def get_trades():
    """GET /api/trades?league_id=...  →  pending trade cards"""
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    trade_service = sess["trade_svc"]
    g_user_id     = sess["user_id"]
    g_players     = sess["players"]
    league_id = request.args.get("league_id") or None
    cards     = trade_service.get_pending_trades(
        user_id   = g_user_id,
        league_id = league_id,
    )
    players_dict = {p.id: p for p in g_players}
    return jsonify([trade_card_to_dict(c, players_dict) for c in cards])


def _reconstruct_swipe_card(trade_service, body: dict, user_id: str, league_id: str):
    """FB-46 — rebuild a TradeCard from the swipe payload's card context.

    Trade decks live in the per-session TradeService's memory; a Render
    deploy (or session re-init) wipes them while clients may still be
    displaying the old deck. When record_decision can't find the trade_id,
    this reconstructs the card from the give/receive ids the client echoes
    back, registers it, and lets the normal decision flow proceed — Elo
    signal, persistence, and mutual-match detection all behave identically.

    Returns the registered TradeCard, or None when the payload doesn't
    carry enough context (legacy clients) — callers should re-raise then.
    """
    give_ids = body.get("give_player_ids") or []
    recv_ids = body.get("receive_player_ids") or []
    if not (isinstance(give_ids, list) and isinstance(recv_ids, list)
            and give_ids and recv_ids):
        return None
    card = TradeCard(
        trade_id           = str(body.get("trade_id")),
        league_id          = str(body.get("league_id") or league_id),
        proposing_user_id  = user_id,
        target_user_id     = str(body.get("target_user_id") or ""),
        target_username    = str(body.get("target_username") or ""),
        give_player_ids    = [str(x) for x in give_ids],
        receive_player_ids = [str(x) for x in recv_ids],
        mismatch_score     = 0.0,
        fairness_score     = 0.0,
        composite_score    = 0.0,
    )
    trade_service._trade_cards[card.trade_id] = card
    return card


@app.route("/api/trades/swipe", methods=["POST"])
@_gate_unverified_write
def swipe_trade():
    """POST /api/trades/swipe  {trade_id, decision: 'like'|'pass'}

    Optional card-context fields (give_player_ids, receive_player_ids,
    target_user_id, target_username, league_id) make the swipe
    restart-proof: if the in-memory deck was lost since generation, the
    card is reconstructed from them instead of failing with
    "Unknown trade_id" (FB-46).
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    service       = sess["service"]
    trade_service = sess["trade_svc"]
    g_user_id     = sess["user_id"]
    g_league      = sess["league"]
    g_players     = sess["players"]
    body     = request.get_json(force=True) or {}
    trade_id = body.get("trade_id")
    decision = body.get("decision")

    if not trade_id or not decision:
        return jsonify({"error": "trade_id and decision required"}), 400

    try:
        try:
            card = trade_service.record_decision(trade_id=trade_id, decision=decision)
        except ValueError as ve:
            # Unknown trade_id → deck predates a restart/re-init. Recover
            # from the client-echoed card context when present; otherwise
            # surface the original error (legacy payloads).
            if "Unknown trade_id" not in str(ve):
                raise
            rebuilt = _reconstruct_swipe_card(trade_service, body, g_user_id, g_league.league_id)
            if rebuilt is None:
                raise
            log.info("swipe: reconstructed card %s from payload context (FB-46)", trade_id)
            card = trade_service.record_decision(trade_id=trade_id, decision=decision)

        if decision == "like":
            service.record_trade_signal(
                winner_ids = card.receive_player_ids,
                loser_ids  = card.give_player_ids,
                decision   = "like",
            )
            from .ranking_service import _c as _rs_c
            k_factor = _rs_c("trade_k_like")
            win_ids, lose_ids = card.receive_player_ids, card.give_player_ids
        else:  # "pass"
            service.record_trade_signal(
                winner_ids = card.give_player_ids,
                loser_ids  = card.receive_player_ids,
                decision   = "pass",
            )
            from .ranking_service import _c as _rs_c
            k_factor = _rs_c("trade_k_pass")
            win_ids, lose_ids = card.give_player_ids, card.receive_player_ids

        # Persist to DB — write-through
        match_data = None
        try:
            save_trade_decision(
                user_id            = g_user_id,
                league_id          = card.league_id,
                trade_id           = trade_id,
                give_player_ids    = card.give_player_ids,
                receive_player_ids = card.receive_player_ids,
                decision           = decision,
            )
            save_trade_swipes(
                user_id        = g_user_id,
                winner_ids     = win_ids,
                loser_ids      = lose_ids,
                k_factor       = k_factor,
                scoring_format = _active_format(sess),
            )

            try:
                record_event(
                    g_user_id,
                    "trade_proposed" if decision == "like" else "match_swiped",
                    league_id = card.league_id,
                    source    = "api",
                    props     = {
                        "decision":   decision,
                        "trade_id":   trade_id,
                        "give":       card.give_player_ids,
                        "receive":    card.receive_player_ids,
                        "target":     card.target_user_id,
                        # Interview phase 2 — join swipe outcomes to the
                        # aggression bucket / lane / fit-premium flag.
                        "aggression_variant": getattr(card, "aggression_variant", None),
                        "lane":               getattr(card, "lane", None),
                        "fit_premium":        bool(getattr(card, "fit_premium", None)),
                    },
                    **(getattr(g, "device_info", {}) or {}),
                )
            except Exception as ev_err:
                log.warning("record_event(trade swipe) failed: %s", ev_err)

            # Mutual match detection — only on "like" decisions
            if decision == "like" and card.target_user_id and card.league_id != "league_demo":
                is_mirror = check_for_match(
                    current_user_id    = g_user_id,
                    league_id          = card.league_id,
                    target_user_id     = card.target_user_id,
                    give_player_ids    = card.give_player_ids,
                    receive_player_ids = card.receive_player_ids,
                    # Tier 2 (2.3b) — fuzzy mirror matching behind
                    # trade.fuzzy_match; exact behavior unchanged when off.
                    fuzzy              = _fuzzy_match_enabled(),
                    fuzzy_tau          = _fuzzy_match_tau(),
                )
                if is_mirror:
                    already = match_already_exists(
                        league_id          = card.league_id,
                        user_a_id          = g_user_id,
                        user_b_id          = card.target_user_id,
                        give_player_ids    = card.give_player_ids,
                        receive_player_ids = card.receive_player_ids,
                    )
                    if not already:
                        match_data = create_trade_match(
                            league_id      = card.league_id,
                            user_a_id      = g_user_id,
                            user_b_id      = card.target_user_id,
                            user_a_give    = card.give_player_ids,
                            user_a_receive = card.receive_player_ids,
                        )
                        log.info(
                            "🎉 Trade match! league=%s  %s ↔ %s  give=%s receive=%s",
                            card.league_id, g_user_id, card.target_user_id,
                            card.give_player_ids, card.receive_player_ids,
                        )
                        # ── Fire notifications for both users ──────────────
                        _pd = {p.id: p for p in g_players}
                        _give_names    = [_pd[pid].name for pid in card.give_player_ids    if pid in _pd]
                        _receive_names = [_pd[pid].name for pid in card.receive_player_ids if pid in _pd]
                        _partner_a     = card.target_username or card.target_user_id
                        _my_username   = sess.get("display_name") or g_user_id
                        _meta_base = {
                            "match_id":        match_data["id"],
                            "give":            _give_names,
                            "receive":         _receive_names,
                        }
                        _league_name = getattr(g_league, "name", None) or ""
                        _in_league   = f" in {_league_name}" if _league_name else ""
                        try:
                            # Notification for current user (user_a)
                            create_notification(
                                user_id  = g_user_id,
                                type_    = "trade_match",
                                title    = f"🤝 New trade match with {_partner_a}{_in_league}!",
                                body     = (
                                    f"New trade match with {_partner_a}{_in_league}! "
                                    + (f"{', '.join(_give_names)} for {', '.join(_receive_names)}"
                                       if _give_names and _receive_names else "")
                                ).strip(),
                                metadata = {**_meta_base, "partner_username": _partner_a,
                                            "league_name": _league_name},
                            )
                            # Notification for counterparty (user_b)
                            create_notification(
                                user_id  = card.target_user_id,
                                type_    = "trade_match",
                                title    = f"🤝 New trade match with {_my_username}{_in_league}!",
                                body     = (
                                    f"New trade match with {_my_username}{_in_league}! "
                                    + (f"{', '.join(_receive_names)} for {', '.join(_give_names)}"
                                       if _give_names and _receive_names else "")
                                ).strip(),
                                metadata = {
                                    **_meta_base,
                                    "partner_username": _my_username,
                                    "league_name":      _league_name,
                                    "give":    _receive_names,   # flipped perspective
                                    "receive": _give_names,
                                },
                            )
                        except Exception as notif_err:
                            log.warning("create_notification failed (non-fatal): %s", notif_err)

                        # ── Push — typed dispatch to both match participants ──
                        # _send_typed_push handles prefs, freq caps, and
                        # quiet-hours bundling. Non-throwing.
                        # Each recipient also gets a one-time `first_match`
                        # push if this is their first-ever match (gated by
                        # the dedup-cap on the `first_match` kind — fires
                        # once per user, ever).
                        for _recipient_id, _partner_name, _give, _recv in [
                            (g_user_id,           _partner_a,    _give_names,    _receive_names),
                            (card.target_user_id, _my_username,  _receive_names, _give_names),
                        ]:
                            _body_detail = (
                                f"{', '.join(_give)} for {', '.join(_recv)}"
                                if _give and _recv else
                                "Tap to view the matched trade."
                            )
                            _send_typed_push(
                                _recipient_id,
                                "new_match",
                                title = f"🎯 Match with @{_partner_name}",
                                body  = _body_detail,
                                data  = {
                                    "match_id":  match_data["id"],
                                    "league_id": card.league_id,
                                },
                                dedup_key = str(match_data["id"]),
                            )
                            _send_typed_push(
                                _recipient_id,
                                "first_match",
                                title = "🎉 You got your first trade match!",
                                body  = f"@{_partner_name} matched a trade with you. Tap to review.",
                                data  = {
                                    "match_id":  match_data["id"],
                                    "league_id": card.league_id,
                                },
                                dedup_key = "lifetime",
                            )

        except Exception as db_err:
            log.warning("DB write failed for trade swipe (continuing): %s", db_err)

        players_dict = {p.id: p for p in g_players}
        resp = trade_card_to_dict(card, players_dict)
        if match_data:
            resp["matched"]      = True
            resp["match_id"]     = match_data["id"]
            resp["partner_name"] = card.target_username or match_data["user_b_id"]
            resp["my_give"]      = [players_dict[pid].name for pid in card.give_player_ids
                                     if pid in players_dict]
            resp["my_receive"]   = [players_dict[pid].name for pid in card.receive_player_ids
                                     if pid in players_dict]
        else:
            resp["matched"] = False
        return jsonify(resp)
    except ValueError as ve:
        # Client-actionable validation feedback (e.g. unknown/stale trade_id).
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        log.exception("swipe_trade failed")
        return jsonify({"error": "bad_request"}), 400


# ---------------------------------------------------------------------------
# Bad-trade flags (FB #85) — "this is a bad trade" on the swipe deck.
# Distinct from a pass: a flag means "the engine got this one wrong". Rows
# feed operator review to iterate on the trade-generation logic.
# ---------------------------------------------------------------------------

def _flag_num(value) -> float | None:
    """Client-echoed telemetry fallback: accept real numbers, drop the rest."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


@app.route("/api/trades/flag", methods=["POST"])
@_gate_unverified_write
def flag_bad_trade():
    """POST /api/trades/flag — flag a generated trade card as a bad trade.

    Body:
      give_player_ids      required, non-empty list of player ids (my give side)
      receive_player_ids   required, non-empty list of player ids
      trade_id             optional — used to pull authoritative engine
                           telemetry from the in-memory deck when it's alive
      league_id            optional — defaults to the session's active league
      target_user_id / target_username   optional counterparty context
      reason               optional free text (≤ 500 chars)
      mismatch_score / fairness_score / composite_score / need_fit /
      partner_fit / basis  optional client-echoed telemetry fallback, used
                           only when the in-memory card is gone (restart)

    Idempotent per (user, league, give set, receive set) — re-flagging the
    same package returns 200 with `duplicate: true` instead of a new row.
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    body = request.get_json(force=True, silent=True) or {}

    give_raw = body.get("give_player_ids")
    recv_raw = body.get("receive_player_ids")
    if not isinstance(give_raw, list) or not give_raw:
        return jsonify({"error": "missing_field", "field": "give_player_ids"}), 400
    if not isinstance(recv_raw, list) or not recv_raw:
        return jsonify({"error": "missing_field", "field": "receive_player_ids"}), 400
    give_ids = [str(p) for p in give_raw]
    recv_ids = [str(p) for p in recv_raw]

    league_id = body.get("league_id") or (g_league.league_id if g_league else None)
    if not league_id:
        return jsonify({"error": "missing_field", "field": "league_id"}), 400

    reason_raw = body.get("reason")
    reason = reason_raw.strip()[:500] if isinstance(reason_raw, str) and reason_raw.strip() else None

    trade_id = body.get("trade_id") if isinstance(body.get("trade_id"), str) else None

    # Engine telemetry: prefer the live in-memory card (authoritative),
    # fall back to client-echoed values when the deck predates a restart.
    card = None
    if trade_id:
        try:
            card = sess["trade_svc"]._trade_cards.get(trade_id)
        except Exception:
            card = None
    if card is not None:
        mismatch_score  = card.mismatch_score
        fairness_score  = card.fairness_score
        composite_score = card.composite_score
        need_fit        = getattr(card, "need_fit", None)
        partner_fit     = getattr(card, "partner_fit", None)
        basis           = getattr(card, "basis", "divergence")
        target_user_id  = card.target_user_id
        target_username = card.target_username
    else:
        mismatch_score  = _flag_num(body.get("mismatch_score"))
        fairness_score  = _flag_num(body.get("fairness_score"))
        composite_score = _flag_num(body.get("composite_score"))
        need_fit        = _flag_num(body.get("need_fit"))
        partner_fit     = _flag_num(body.get("partner_fit"))
        basis           = body.get("basis") if body.get("basis") in ("divergence", "consensus") else None
        target_user_id  = str(body["target_user_id"]) if body.get("target_user_id") else None
        target_username = str(body["target_username"]) if body.get("target_username") else None

    try:
        result = save_bad_trade_flag(
            user_id            = g_user_id,
            username           = sess.get("display_name") or sess.get("username"),
            league_id          = str(league_id),
            target_user_id     = target_user_id,
            target_username    = target_username,
            give_player_ids    = give_ids,
            receive_player_ids = recv_ids,
            scoring_format     = _active_format(sess),
            trade_id           = trade_id,
            mismatch_score     = mismatch_score,
            fairness_score     = fairness_score,
            composite_score    = composite_score,
            need_fit           = need_fit,
            partner_fit        = partner_fit,
            basis              = basis,
            reason             = reason,
        )
    except Exception:
        log.exception("save_bad_trade_flag failed")
        return jsonify({"error": "internal"}), 500

    status = 200 if result.get("duplicate") else 201
    return jsonify({
        "ok":         True,
        "flag_id":    result["server_id"],
        "created_at": result["created_at"],
        "duplicate":  bool(result.get("duplicate")),
    }), status


@app.route("/api/trades/flags/admin", methods=["GET"])
def list_bad_trade_flags_route():
    """GET /api/trades/flags/admin?since_id=N&limit=M — operator readback of
    bad-trade flags for engine-quality review.

    Auth: same CRON_SECRET pattern as /api/feedback/admin (X-Cron-Secret
    header). Local dev with no CRON_SECRET set: open. Prod without
    CRON_SECRET: 503 (fail closed).

    Response mirrors /api/feedback/admin:
      { "items": [...], "count": N,
        "next_since_id": <max id in items, or input since_id when empty> }
    """
    _require_cron_auth()
    try:
        since_id = int(request.args.get("since_id", 0))
    except (TypeError, ValueError):
        since_id = 0
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    items = list_bad_trade_flags(since_id=since_id, limit=limit)
    next_since = items[-1]["id"] if items else since_id
    return jsonify({"items": items, "count": len(items), "next_since_id": next_since})


# ---------------------------------------------------------------------------
# "Send in Sleeper" — link a Sleeper account + propose trades directly.
# ⚠️ FLAGGED-BETA / ToS-adverse. Gated by `trade.send_in_sleeper` (default OFF).
# See docs/plans/sleeper-write-capture-runbook.md. The stored token is a
# full-account credential — encrypted at rest, never logged.
# ---------------------------------------------------------------------------

def _fetch_league_rosters(league_id: str):
    """Public rosters array for a league, or None on failure."""
    try:
        rosters = _sleeper_get(f"https://api.sleeper.app/v1/league/{league_id}/rosters")
    except Exception:
        return None
    return rosters if isinstance(rosters, list) else None


def _roster_id_for_owner(rosters, owner_id) -> int | None:
    """Server-authoritative roster resolution: the roster_id owned by owner_id
    (a Sleeper user_id). Clients never assert roster_ids directly."""
    if not owner_id or not rosters:
        return None
    for r in rosters:
        if isinstance(r, dict) and str(r.get("owner_id")) == str(owner_id):
            try:
                return int(r.get("roster_id"))
            except (TypeError, ValueError):
                return None
    return None


@app.route("/api/sleeper/link", methods=["GET", "POST", "DELETE"])
def sleeper_link():
    """Manage the caller's stored Sleeper write token.

    POST   {token}  → validate the JWT + store it encrypted (link/re-link).
                      DOUBLES AS SESSION VERIFICATION (account-auth P1):
                      the token's user_id claim must match the session's
                      user_id (403 token_user_mismatch otherwise) and the
                      token is exercised once against Sleeper's authed API
                      — the signature oracle (401 token_rejected on a
                      forged/dead token). On proof the session is marked
                      verified and users.verified_via='sleeper' persisted.
                      If the oracle is unreachable (network/config) the
                      link still stores, but `verified` stays false.
    GET             → {connected, sleeper_user_id, expires_at, expired}. No token.
    DELETE          → drop the stored token (disconnect). Standard write gate.
    """
    if not is_enabled("trade.send_in_sleeper"):
        return jsonify({"error": "feature_disabled"}), 404
    sess = _require_session()
    user_id = sess.get("user_id")
    if not user_id:
        return jsonify({"error": "no_user"}), 401

    if request.method == "DELETE":
        denial = _verified_write_denial(sess)
        if denial is not None:
            return denial
        delete_sleeper_credential(user_id)
        return jsonify({"connected": False})

    if request.method == "GET":
        cred = get_sleeper_credential(user_id)
        if not cred:
            return jsonify({"connected": False})
        expired = False
        if cred.get("expires_at"):
            try:
                expired = datetime.fromisoformat(cred["expires_at"]) <= datetime.now(timezone.utc)
            except Exception:
                expired = False
        return jsonify({
            "connected": True,
            "sleeper_user_id": cred.get("sleeper_user_id"),
            "expires_at": cred.get("expires_at"),
            "expired": expired,
        })

    # POST — store a freshly captured token
    if not _sleeper_write.token_encryption_available():
        return jsonify({"error": "sleeper_unconfigured"}), 503
    body = request.get_json(force=True) or {}
    token = (body.get("token") or "").strip()
    if not token or token.count(".") != 2:
        return jsonify({"error": "invalid_token"}), 400
    if _sleeper_write.is_expired(token):
        return jsonify({"error": "token_expired"}), 400
    sleeper_user_id = _sleeper_write.token_sleeper_user_id(token)

    # ── P1 hard gate #1: the claim must name the session's user ──────────
    # Without this, any session could park an arbitrary Sleeper login under
    # this user_id. This is also half of the verification predicate.
    if str(sleeper_user_id or "") != str(user_id):
        log.warning("AUTH-DENY sleeper_link claim mismatch: session=%s claim=%s",
                    user_id, sleeper_user_id)
        return jsonify({"error": "token_user_mismatch"}), 403

    # ── P1 oracle probe: prove the token is REAL, not just well-formed ───
    # token_sleeper_user_id() decodes without checking the HS256 signature,
    # so we exercise the token once against Sleeper's authenticated GraphQL
    # endpoint. Sleeper rejecting it (401/403) ⇒ forged or dead ⇒ deny.
    # A transport/config failure is INCONCLUSIVE: store the link (existing
    # best-effort behavior) but do not verify.
    proven_live = False
    try:
        _sleeper_write.verify_token_live(token)
        proven_live = True
    except _sleeper_write.SleeperAuthError as e:
        log.warning("AUTH-DENY sleeper_link oracle rejected token for %s: %s",
                    user_id, getattr(e, "detail", None))
        return jsonify({"error": "token_rejected"}), 403
    except _sleeper_write.SleeperWriteError as e:
        log.warning("sleeper_link oracle inconclusive [%s] for %s: %s — "
                    "linking unverified", e.kind, user_id, getattr(e, "detail", None))

    exp = _sleeper_write.token_expiry(token)
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat() if exp else None
    try:
        ciphertext = _sleeper_write.encrypt_token(token)
        upsert_sleeper_credential(user_id, sleeper_user_id, ciphertext, expires_at)
    except _sleeper_write.SleeperWriteError:
        return jsonify({"error": "sleeper_unconfigured"}), 503
    except Exception:
        log.exception("sleeper_link store failed")
        return jsonify({"error": "store_failed"}), 500

    if proven_live:
        # Claim matches + oracle passed → this session controls the account.
        sess["verified"] = True
        sess["verified_via"] = "sleeper"
        try:
            from . import accounts as _accounts
            first_time = _accounts.get_user_verified_via(user_id) is None
            if not user_exists(user_id):
                # Link can beat session_init's background user upsert; make
                # sure the row exists so the marker isn't dropped.
                upsert_user(sleeper_user_id=user_id)
            _accounts.mark_user_verified(user_id, "sleeper")
            if first_time:
                # Support trail for the squatter transition (plan §2d):
                # from this moment unverified sessions for this user_id
                # lose write access.
                log.info("AUTH-VERIFIED first verified controller user_id=%s "
                         "via=sleeper", user_id)
        except Exception:
            log.exception("persisting verified marker failed (session still "
                          "verified in memory)")

    return jsonify({
        "connected": True,
        "sleeper_user_id": sleeper_user_id,
        "expires_at": expires_at,
        "verified": bool(sess.get("verified")),
    })


@app.route("/api/trades/propose", methods=["POST"])
def propose_trade_to_sleeper():
    """Send a built trade to Sleeper as a real proposal.

    Body: {league_id, their_user_id (or their_roster_id), give_player_ids[],
           receive_player_ids[], draft_picks?[]}  (players-only v1; picks pre-encoded).
    Success → {status:"proposed", transaction_id}. Structured errors the client
    maps to the deep-link fallback / reconnect prompt:
      404 feature_disabled | 403 verification_required | 409 sleeper_not_linked
      409 sleeper_expired | 503 sleeper_unconfigured | 502 sleeper_write_failed
      400 bad_request
    """
    if _TEST_MODE:
        # Fail closed: there is no legitimate automated send. Route-hit
        # accounting happens in test_support's request hook so injected and
        # fail-closed requests count identically (lld.md §4.3c).
        return jsonify({"error": "test_mode_propose_disabled"}), 599
    if not is_enabled("trade.send_in_sleeper"):
        return jsonify({"error": "feature_disabled"}), 404
    sess = _require_session()
    user_id = sess.get("user_id")
    if not user_id:
        return jsonify({"error": "no_user"}), 401

    # ── P1 hard gate #2 (account-auth plan §3): highest blast radius —
    # this route writes into the victim's REAL Sleeper league. Only a
    # session that proved control of this user_id (Sleeper-JWT capture +
    # oracle, i.e. POST /api/sleeper/link in THIS session) may fire it.
    # No grace period. The client routes 403 verification_required back
    # into the SleeperConnect flow, which re-verifies in one tap.
    if not sess.get("verified"):
        log.warning("AUTH-DENY unverified_write user_id=%s method=%s path=%s "
                    "reason=hard_route", user_id, request.method, request.path)
        return jsonify({"error": "verification_required"}), 403

    body = request.get_json(force=True) or {}
    league_id = str(body.get("league_id") or "").strip()
    their_user_id = body.get("their_user_id")
    their_roster_id_in = body.get("their_roster_id")
    give = [str(p) for p in (body.get("give_player_ids") or [])]
    receive = [str(p) for p in (body.get("receive_player_ids") or [])]
    picks = [str(p) for p in (body.get("draft_picks") or [])]
    if not league_id.isdigit() or (their_user_id is None and their_roster_id_in is None):
        return jsonify({"error": "bad_request"}), 400

    cred = get_sleeper_credential(user_id)
    if not cred:
        return jsonify({"error": "sleeper_not_linked"}), 409
    try:
        token = _sleeper_write.decrypt_token(cred["token_encrypted"])
    except _sleeper_write.SleeperWriteError:
        return jsonify({"error": "sleeper_unconfigured"}), 503
    if _sleeper_write.is_expired(token):
        delete_sleeper_credential(user_id)
        return jsonify({"error": "sleeper_expired"}), 409

    # Resolve BOTH rosters server-authoritatively from one public rosters fetch:
    # mine from the linked Sleeper account, the counterparty's from their user_id
    # (FTF user_id == Sleeper user_id). A client-supplied their_roster_id wins.
    rosters = _fetch_league_rosters(league_id)
    my_roster_id = _roster_id_for_owner(rosters, cred.get("sleeper_user_id"))
    if my_roster_id is None:
        return jsonify({"error": "roster_not_found"}), 400
    if their_roster_id_in is not None:
        try:
            their_rid = int(their_roster_id_in)
        except (TypeError, ValueError):
            return jsonify({"error": "bad_request"}), 400
    else:
        their_rid = _roster_id_for_owner(rosters, their_user_id)
        if their_rid is None:
            return jsonify({"error": "opponent_roster_not_found"}), 400

    req = _sleeper_write.ProposeTradeRequest(
        league_id=league_id, my_roster_id=my_roster_id, their_roster_id=their_rid,
        give_player_ids=give, receive_player_ids=receive,
        draft_picks=picks or None,
    )
    try:
        result = _sleeper_write.propose_trade(token, req)
    except _sleeper_write.SleeperAuthError as e:
        # Sleeper rejected the freshly-captured token (401/403 or an
        # auth-flavored GraphQL error). Reconnecting re-captures the SAME
        # token, so it would just loop — the client must NOT bounce back to
        # the login webview here. Surface `sleeper_rejected` (distinct from
        # `sleeper_expired`, which is a time-expiry the client CAN fix by
        # reconnecting) plus a short detail so we can see WHY Sleeper says no.
        log.warning("sleeper propose auth-rejected: %s", getattr(e, "detail", None))
        delete_sleeper_credential(user_id)
        return jsonify({
            "error": "sleeper_rejected",
            "detail": (str(getattr(e, "detail", "") or ""))[:200],
        }), 409
    except _sleeper_write.SleeperWriteError as e:
        log.warning("sleeper propose write-failed [%s]: %s", e.kind, getattr(e, "detail", None))
        return jsonify({
            "error": "sleeper_write_failed",
            "kind": e.kind,
            "detail": (str(getattr(e, "detail", "") or ""))[:200],
        }), 502
    # A real outbound Sleeper send happened — the gating guardrail counter.
    # Unreachable under FTF_TEST_MODE (fail-closed above); the import is lazy
    # so normal operation never touches test_support.
    if _TEST_MODE:  # pragma: no cover — defense-in-depth, structurally dead
        from . import test_support as _ts
        _ts.counters["completed_proposes"] += 1
    return jsonify({
        "status": result.get("status") or "proposed",
        "transaction_id": result.get("transaction_id"),
    })


@app.route("/api/account/reset-rankings", methods=["POST"])
def account_reset_rankings():
    """Wipe every persisted ranking artifact for the caller (all formats).

    Account-auth P1 squatter remedy (plan §2d "first verified controller
    wins"): a user who just VERIFIED may be inheriting rankings/tiers a
    username-squatter authored before verification shipped. This offers a
    clean slate: deletes swipe history + published member_rankings and
    clears tier overrides / saved-tier markers / ranking method, then
    resets this session's in-memory ranking services so the wipe is
    immediate (not next-login).

    VERIFIED-ONLY — 403 verification_required otherwise, no grace: the
    reset destroys data, so it demands the same proof-of-control bar as
    the hard-gated routes. UI entry point lands with P2's Settings
    account section. Response: {ok, counts:{...}}.
    """
    sess = _require_session()
    user_id = sess.get("user_id")
    if not user_id:
        return jsonify({"error": "no_user"}), 401
    if not sess.get("verified"):
        log.warning("AUTH-DENY unverified_write user_id=%s method=%s path=%s "
                    "reason=hard_route", user_id, request.method, request.path)
        return jsonify({"error": "verification_required"}), 403

    from .database import reset_user_rankings
    try:
        counts = reset_user_rankings(user_id)
    except Exception:
        log.exception("account reset-rankings DB wipe failed")
        return jsonify({"error": "reset_failed"}), 500

    # In-memory: reset every format's ranking service for THIS session so
    # the board reflects the wipe without a re-login. Other live sessions
    # for this user_id rebuild from the (now empty) DB on their next
    # session_init.
    for svc in (sess.get("services") or {}).values():
        try:
            svc.reset(position=None)
            svc._elo_overrides = {}
        except Exception:
            log.exception("account reset-rankings in-memory reset failed")
    log.info("AUTH-VERIFIED reset-rankings user_id=%s counts=%s", user_id, counts)
    return jsonify({"ok": True, "counts": counts})


@app.route("/api/trades/liked")
@_gate_unverified_read
def get_liked_trades():
    """GET /api/trades/liked  →  trades the user has liked"""
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    trade_service = sess["trade_svc"]
    g_user_id     = sess["user_id"]
    g_players     = sess["players"]
    cards        = trade_service.get_liked_trades(user_id=g_user_id)
    players_dict = {p.id: p for p in g_players}
    return jsonify([trade_card_to_dict(c, players_dict) for c in cards])


@app.route("/api/trades/matches")
@_gate_unverified_read
def get_trade_matches():
    """
    GET /api/trades/matches  →  all trade matches for the current user
    (all statuses: pending, accepted, declined), enriched with player names
    and disposition state from the caller's perspective.
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    g_players = sess["players"]
    if not g_user_id or not g_league:
        return jsonify([])

    league_id = g_league.league_id
    if league_id == "league_demo":
        return jsonify([])

    try:
        matches      = load_matches(user_id=g_user_id, league_id=league_id)
        players_dict = {p.id: p for p in g_players}

        enriched = []
        for m in matches:
            enriched.append({
                **m,
                "my_give_names":    [players_dict[pid].name for pid in m["my_give"]
                                     if pid in players_dict],
                "my_receive_names": [players_dict[pid].name for pid in m["my_receive"]
                                     if pid in players_dict],
            })
        if matches:
            try:
                record_event(
                    g_user_id,
                    "match_viewed",
                    league_id = league_id,
                    source    = "api",
                    props     = {"count": len(matches)},
                    **(getattr(g, "device_info", {}) or {}),
                )
            except Exception:
                pass
        return jsonify(enriched)
    except Exception as e:
        log.warning("get_trade_matches error: %s", e)
        return jsonify([])


@app.route("/api/trades/matches/all")
@_gate_unverified_read
def get_trade_matches_all():
    """
    GET /api/trades/matches/all
    Returns trade matches across EVERY league the user is in (all statuses),
    enriched with `league_name` plus `my_give_names` / `my_receive_names`
    for display. Used by the mobile Matches tab so users can see pending /
    accepted / declined matches without flipping through their league list.

    Player-name enrichment uses the global players_table (not session state)
    because cross-league matches reference players outside the active
    league's roster pool. League names come from the leagues table.

    Response is a bare array — same contract as /api/trades/matches.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    if not g_user_id:
        return jsonify([])

    try:
        matches = load_matches(user_id=g_user_id, league_id=None)
        if not matches:
            return jsonify([])
        try:
            record_event(
                g_user_id,
                "match_viewed",
                source = "api",
                props  = {"count": len(matches), "scope": "cross_league"},
                **(getattr(g, "device_info", {}) or {}),
            )
        except Exception:
            pass

        # Batch enrichment — two IN-clause queries instead of one per match.
        from sqlalchemy import select as _sa_select
        from .database import leagues_table, players_table, engine as _engine

        league_ids = {m["league_id"] for m in matches}
        all_pids: set[str] = set()
        for m in matches:
            all_pids.update(m.get("my_give") or [])
            all_pids.update(m.get("my_receive") or [])

        league_name_by_id: dict[str, str] = {}
        player_name_by_id: dict[str, str]     = {}
        player_team_by_id: dict[str, str]     = {}
        player_pos_by_id:  dict[str, str]     = {}
        with _engine.connect() as _conn:
            if league_ids:
                lrows = _conn.execute(
                    _sa_select(
                        leagues_table.c.sleeper_league_id,
                        leagues_table.c.name,
                    ).where(leagues_table.c.sleeper_league_id.in_(league_ids))
                ).fetchall()
                for lr in lrows:
                    # Multiple users may have a row per league — first wins;
                    # the names are the same regardless of which user owns it.
                    league_name_by_id.setdefault(lr.sleeper_league_id, lr.name or "")
            if all_pids:
                # team + position come from the global players_table — mobile
                # MatchesScreen needs them to render chips, and they're not
                # available in the active league's session state for
                # cross-league matches.
                prows = _conn.execute(
                    _sa_select(
                        players_table.c.player_id,
                        players_table.c.full_name,
                        players_table.c.team,
                        players_table.c.position,
                    ).where(players_table.c.player_id.in_(all_pids))
                ).fetchall()
                for pr in prows:
                    player_name_by_id[pr.player_id] = pr.full_name or pr.player_id
                    player_team_by_id[pr.player_id] = pr.team or ""
                    player_pos_by_id[pr.player_id]  = pr.position or ""

        enriched = []
        for m in matches:
            give_ids    = m.get("my_give")    or []
            receive_ids = m.get("my_receive") or []
            enriched.append({
                **m,
                "league_name":         league_name_by_id.get(m["league_id"], ""),
                "my_give_names":       [player_name_by_id.get(pid, pid) for pid in give_ids],
                "my_receive_names":    [player_name_by_id.get(pid, pid) for pid in receive_ids],
                "my_give_teams":       [player_team_by_id.get(pid, "") for pid in give_ids],
                "my_receive_teams":    [player_team_by_id.get(pid, "") for pid in receive_ids],
                "my_give_positions":   [player_pos_by_id.get(pid, "")  for pid in give_ids],
                "my_receive_positions":[player_pos_by_id.get(pid, "")  for pid in receive_ids],
            })
        return jsonify(enriched)
    except Exception as e:
        log.warning("get_trade_matches_all error: %s", e)
        return jsonify([])


@app.route("/api/trades/awaiting")
@_gate_unverified_read
def get_awaiting_trades():
    """
    GET /api/trades/awaiting
    Returns cross-league trades the caller has liked that have NOT yet
    matured into a mutual match. Powers the "Awaiting them" segment on
    MatchesScreen so users can see their one-sided likes — the gap between
    "I swiped accept" and "we both swiped accept".

    Response shape (bare array, mirrors /api/trades/matches/all where it
    overlaps so the same mobile tile component can render either):
      [
        {
          trade_id, league_id, league_name?,
          partner_id, partner_name,
          my_give[], my_receive[],
          my_give_names[], my_receive_names[],
          liked_at,
        },
        ...
      ]
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    if not g_user_id:
        return jsonify([])

    try:
        awaiting = load_awaiting_trades(user_id=g_user_id)
        if not awaiting:
            return jsonify([])

        # Batch enrichment — same pattern as /api/trades/matches/all so we
        # don't N+1 the players/leagues tables.
        from sqlalchemy import select as _sa_select
        from .database import leagues_table, players_table, engine as _engine

        league_ids = {a["league_id"] for a in awaiting}
        all_pids: set[str] = set()
        for a in awaiting:
            all_pids.update(a.get("my_give") or [])
            all_pids.update(a.get("my_receive") or [])

        league_name_by_id: dict[str, str] = {}
        player_name_by_id: dict[str, str] = {}
        with _engine.connect() as _conn:
            if league_ids:
                lrows = _conn.execute(
                    _sa_select(
                        leagues_table.c.sleeper_league_id,
                        leagues_table.c.name,
                    ).where(leagues_table.c.sleeper_league_id.in_(league_ids))
                ).fetchall()
                for lr in lrows:
                    league_name_by_id.setdefault(lr.sleeper_league_id, lr.name or "")
            if all_pids:
                prows = _conn.execute(
                    _sa_select(
                        players_table.c.player_id,
                        players_table.c.full_name,
                    ).where(players_table.c.player_id.in_(all_pids))
                ).fetchall()
                for pr in prows:
                    player_name_by_id[pr.player_id] = pr.full_name or pr.player_id

        enriched = []
        for a in awaiting:
            give_ids    = a.get("my_give")    or []
            receive_ids = a.get("my_receive") or []
            enriched.append({
                **a,
                "league_name":      league_name_by_id.get(a["league_id"], ""),
                "my_give_names":    [player_name_by_id.get(pid, pid) for pid in give_ids],
                "my_receive_names": [player_name_by_id.get(pid, pid) for pid in receive_ids],
            })
        return jsonify(enriched)
    except Exception as e:
        log.warning("get_awaiting_trades error: %s", e)
        return jsonify([])


@app.route("/api/trades/matches/<int:match_id>/dismiss", methods=["POST"])
@_gate_unverified_write
def dismiss_trade_match(match_id):
    """
    POST /api/trades/matches/<match_id>/dismiss

    Archive a mutual match from the caller's Matches inbox. Persisted and
    per-user: it never returns for this user (survives sessions/redeploys),
    the counterparty is unaffected, and NO ELO signal is applied. This is the
    "Dismiss" CTA on mobile — distinct from a decline (which record_match_
    disposition handles with a corrective ELO nudge).
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess.get("user_id")
    if not g_user_id:
        return jsonify({"error": "session not initialised"}), 400

    result = dismiss_match(match_id=match_id, user_id=g_user_id)
    if result["status"] == "not_found":
        return jsonify({"error": "match not found"}), 404

    try:
        record_event(
            g_user_id,
            "match_dismissed",
            source = "api",
            props  = {"match_id": match_id},
            **(getattr(g, "device_info", {}) or {}),
        )
    except Exception as ev_err:
        log.warning("record_event(match_dismissed) failed: %s", ev_err)

    return jsonify({"status": "dismissed", "match_id": match_id})


@app.route("/api/trades/matches/<int:match_id>/disposition", methods=["POST"])
@_gate_unverified_write
def disposition_trade_match(match_id):
    """
    POST /api/trades/matches/<match_id>/disposition
    Body: { "decision": "accept" | "decline" }

    Records the current user's disposition on a mutual trade match.

    When both parties have decided:
      • Both accept  → K=20 ELO boost for each user's received players
      • Any decline  → K=20 corrective ELO signal for each decliner,
                       which nets to ≈ −12 after the original +8 nudge

    The ELO signals are:
      1. Applied immediately to the in-memory RankingService for the caller.
      2. Written to swipe_decisions for both users so they survive restarts
         and the counterparty gets them on their next session_init replay.

    Returns the updated match record (same shape as GET /api/trades/matches).
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    # Null-guard every session read: extension sessions (and partially-built
    # main sessions) may lack `league` / `players`, and `service` is only set
    # when the effective format has a built RankingService. A missing key must
    # never raise KeyError and turn a legitimate tap into "Action failed".
    service   = sess.get("service")
    g_user_id = sess.get("user_id")
    g_league  = sess.get("league")
    g_players = sess.get("players") or []
    body     = request.get_json(force=True) or {}
    decision = body.get("decision")

    if decision not in ("accept", "decline"):
        return jsonify({"error": "decision must be 'accept' or 'decline'"}), 400

    # Disposition is keyed on match_id alone — the match carries its own
    # league_id, so we don't require the caller's active session league to
    # match. This lets the cross-league Matches inbox accept/decline a
    # match from any league without first switching context.
    if not g_user_id:
        return jsonify({"error": "session not initialised"}), 400

    # Resolved inside the try once the match is loaded; pre-seed so the
    # diagnostic logging in the except block can reference them even if the
    # failure happens before they're assigned.
    _match_league_id = None
    is_cross_league = False

    try:
        result = record_match_disposition(
            match_id = match_id,
            user_id  = g_user_id,
            decision = decision,
        )

        if result["status"] == "not_found":
            return jsonify({"error": "match not found"}), 404
        if result["status"] == "already_decided":
            # Feedback #77 (recurrence of #8/#35/#36): mobile builds ≤1.3.0
            # render Accept/Decline on EVERY match tile — including ones the
            # caller already decided — and surface any non-2xx as a generic
            # "Action failed" toast. Re-sending the SAME decision is a
            # harmless retry, so answer it idempotently with 200 (no second
            # ELO signal, no re-persist — record_match_disposition returns
            # elo_signals=[] on this path). Only a CONFLICTING decision is
            # still a 409. `matches` is deliberately omitted: the web client
            # re-renders from `data.matches` when present, and an empty list
            # here would wipe its inbox instead of triggering its
            # loadMatches() fallback.
            if decision == result.get("existing_decision"):
                return jsonify({
                    "ok":           True,
                    "idempotent":   True,
                    "both_decided": result["both_decided"],
                    "outcome":      result["outcome"],
                })
            return jsonify({"error": "you have already recorded a decision for this match"}), 409

        # Cross-league flag: the match carries its own league_id. The active
        # in-memory `service` belongs to the session's active league/format, so
        # applying an ELO signal to it for a DIFFERENT league's match would
        # mutate the wrong service. When cross-league, we skip the in-memory
        # apply and rely on persistence (save_trade_swipes below) — the signal
        # replays into the correct service on that league's next session_init.
        _match_league_id = result.get("league_id")
        _active_league_id = g_league.league_id if g_league else None
        is_cross_league = bool(
            _match_league_id and _active_league_id
            and _match_league_id != _active_league_id
        )

        try:
            record_event(
                g_user_id,
                "trade_accepted" if decision == "accept" else "trade_declined",
                league_id = g_league.league_id if g_league else None,
                source    = "api",
                props     = {"match_id": match_id},
                **(getattr(g, "device_info", {}) or {}),
            )
            # ── Push: match_accepted → notify the OTHER party as soon as
            # this user taps Accept, regardless of whether both have decided.
            # Skipped on Decline (no need to ping the proposer that they
            # were rejected via push; in-app inbox + the existing
            # create_notification path covers it).
            #
            # We read partner_user_id (always set on status=='ok') instead of
            # walking elo_signals — elo_signals is only populated when both
            # parties have decided, which would defeat the purpose of an
            # accept-immediate ping.
            if decision == "accept":
                _other_uid = result.get("partner_user_id")
                if _other_uid:
                    _members_map = {m.user_id: (m.username or m.user_id)
                                    for m in (g_league.members if g_league else [])}
                    _my_name = _members_map.get(g_user_id, g_user_id)
                    _send_typed_push(
                        _other_uid,
                        "match_accepted",
                        title = f"✅ @{_my_name} accepted your trade",
                        body  = "Tap to ratify on Sleeper.",
                        data  = {"match_id": match_id,
                                 "league_id": g_league.league_id if g_league else None},
                        dedup_key = f"accept:{match_id}:{g_user_id}",
                    )
            if result.get("both_decided") and result.get("outcome") == "accepted":
                # Mutual accept = ratified. Log for both users.
                _partner = next(
                    (s["user_id"] for s in (result.get("elo_signals") or [])
                     if s["user_id"] != g_user_id),
                    None,
                )
                for uid in filter(None, [g_user_id, _partner]):
                    record_event(
                        uid,
                        "trade_ratified",
                        league_id = g_league.league_id if g_league else None,
                        source    = "api",
                        props     = {"match_id": match_id},
                    )
        except Exception as ev_err:
            log.warning("record_event(trade disposition) failed: %s", ev_err)

        # ── Apply ELO signals when both parties have decided ─────────────
        if result["both_decided"] and result["elo_signals"]:
            for sig in result["elo_signals"]:
                # 1. Apply to in-memory service for the current user — but ONLY
                #    when the match belongs to the active league. For a
                #    cross-league disposition the active `service`'s ratings are
                #    for a different league, so we skip the apply and let
                #    persistence (step 2) replay it on next session_init.
                if (sig["user_id"] == g_user_id
                        and service is not None
                        and not is_cross_league):
                    service.record_disposition_signal(
                        winner_ids = sig["winner_ids"],
                        loser_ids  = sig["loser_ids"],
                        k_factor   = sig["k_factor"],
                    )
                # 2. Persist swipes for both users (non-current user gets
                #    them on next session_init via replay_from_db). This ALWAYS
                #    runs — including cross-league — so the decision survives.
                try:
                    save_trade_swipes(
                        user_id        = sig["user_id"],
                        winner_ids     = sig["winner_ids"],
                        loser_ids      = sig["loser_ids"],
                        k_factor       = sig["k_factor"],
                        decision_type  = sig["decision_type"],
                        scoring_format = _active_format(sess),
                    )
                except Exception as db_err:
                    log.warning("Failed to persist disposition swipe for %s: %s",
                                sig["user_id"], db_err)

            outcome = result["outcome"]
            log.info(
                "⚖️  Trade disposition — match=%s outcome=%s  %s vs %s",
                match_id, outcome, g_user_id,
                next((s["user_id"] for s in result["elo_signals"]
                      if s["user_id"] != g_user_id), "?"),
            )

            # ── Fire accepted / declined notifications for both users ─────
            try:
                _partner_uid = next(
                    (s["user_id"] for s in result["elo_signals"] if s["user_id"] != g_user_id),
                    None,
                )
                _members_map  = {m.user_id: (m.username or m.user_id)
                                 for m in (g_league.members if g_league else [])}
                _my_name      = _members_map.get(g_user_id, g_user_id)
                _partner_name = _members_map.get(_partner_uid, _partner_uid or "your leaguemate")

                # Get player names from the current user's match perspective.
                # Use the match's own league_id (not the caller's active session
                # league) so cross-league dispositions still find the row —
                # mirrors the refresh path below (~3401). `load_matches` keys
                # rows on "match_id", not "id".
                _match_league_id = result.get("league_id") or (
                    g_league.league_id if g_league else "")
                _raw_ms   = load_matches(user_id=g_user_id, league_id=_match_league_id)
                _this_m   = next((m for m in _raw_ms if m["match_id"] == match_id), None)
                _pd       = {p.id: p for p in g_players}
                _gv_names = ([_pd[pid].name for pid in _this_m["my_give"]    if pid in _pd]
                             if _this_m else [])
                _rv_names = ([_pd[pid].name for pid in _this_m["my_receive"] if pid in _pd]
                             if _this_m else [])

                _trade_str_a = (f"{', '.join(_gv_names)} for {', '.join(_rv_names)}"
                                if _gv_names and _rv_names else "")
                _trade_str_b = (f"{', '.join(_rv_names)} for {', '.join(_gv_names)}"
                                if _gv_names and _rv_names else "")

                _league_name  = getattr(g_league, "name", None) or ""
                _in_league    = f" in {_league_name}" if _league_name else ""
                _emoji   = "✅" if outcome == "accepted" else "❌"
                _verb    = "accepted" if outcome == "accepted" else "declined"
                _type_k  = f"trade_{outcome}"
                _meta_a  = {"match_id": match_id, "partner_username": _partner_name,
                            "league_name": _league_name, "give": _gv_names, "receive": _rv_names}
                _meta_b  = {"match_id": match_id, "partner_username": _my_name,
                            "league_name": _league_name, "give": _rv_names, "receive": _gv_names}

                # Current user notification
                create_notification(
                    user_id  = g_user_id,
                    type_    = _type_k,
                    title    = f"{_emoji} {_partner_name} {_verb} your trade{_in_league}",
                    body     = f"{_emoji} {_partner_name} {_verb} your trade{_in_league}: {_trade_str_a}".strip(),
                    metadata = _meta_a,
                )
                # Partner notification
                if _partner_uid:
                    create_notification(
                        user_id  = _partner_uid,
                        type_    = _type_k,
                        title    = f"{_emoji} {_my_name} {_verb} your trade{_in_league}",
                        body     = f"{_emoji} {_my_name} {_verb} your trade{_in_league}: {_trade_str_b}".strip(),
                        metadata = _meta_b,
                    )
            except Exception as _notif_err:
                log.warning("Disposition notification failed (non-fatal): %s", _notif_err)

        # Return refreshed match list so the frontend can re-render.
        # Use the match's own league_id (not the caller's active session
        # league) so a cross-league disposition refreshes the correct slice.
        match_league_id = result.get("league_id") or (g_league.league_id if g_league else None)
        matches      = load_matches(user_id=g_user_id, league_id=match_league_id)
        players_dict = {p.id: p for p in g_players} if g_players else {}

        enriched = []
        for m in matches:
            enriched.append({
                **m,
                "my_give_names":    [players_dict[pid].name for pid in m["my_give"]
                                     if pid in players_dict],
                "my_receive_names": [players_dict[pid].name for pid in m["my_receive"]
                                     if pid in players_dict],
            })
        return jsonify({"ok": True, "both_decided": result["both_decided"],
                        "outcome": result["outcome"], "matches": enriched})

    except Exception as e:
        # FB-01: capture the REAL exception + traceback with full context so a
        # live "Action failed" repro surfaces the actual cause. Return a typed
        # error the client can render instead of a bare unhandled 500.
        log.error(
            "disposition_trade_match failed — match_id=%s user_id=%s "
            "decision=%s match_league_id=%s cross_league=%s — %s\n%s",
            match_id, g_user_id, decision, _match_league_id, is_cross_league,
            e, traceback.format_exc(),
        )
        return jsonify({
            "error": "disposition_failed",
            "message": "Could not record your decision. Please try again.",
        }), 500


@app.route("/api/leagues")
def get_leagues():
    """GET /api/leagues  →  current active league"""
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_league = sess["league"]
    return jsonify([{
        "league_id": g_league.league_id,
        "name":      g_league.name,
        "platform":  g_league.platform,
        "members":   len(g_league.members),
    }])


# ---------------------------------------------------------------------------
# Agent 6 — Cross-league portfolio
# ---------------------------------------------------------------------------

@app.route("/api/portfolio")
def get_portfolio():
    """GET /api/portfolio?league_ids=a,b,c → aggregate exposure across this
    user's leagues. Returns {players: [...]} sorted by exposure desc.

    league_ids (optional, FB-48): comma-separated allow-list. Sleeper mints
    a new league_id per season, so the DB accumulates last season's instance
    of each league; clients pass their current-season list so carried-over
    players aren't double-counted. Omitted → all synced leagues (legacy)."""
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    try:
        raw_ids = (request.args.get("league_ids") or "").strip()
        league_ids = [x for x in (s.strip() for s in raw_ids.split(",")) if x] or None
        players = load_user_cross_league_exposure(g_user_id, league_ids=league_ids)
        return jsonify({"players": players})
    except Exception as e:
        log.error("get_portfolio error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/rankings/submit", methods=["POST"])
@_gate_unverified_write
def submit_rankings():
    """
    POST /api/rankings/submit
    Explicitly publish the caller's current ELO snapshot to member_rankings
    so leaguemates can use their real valuations in trade generation.

    Body (all optional — defaults to current session state):
    {
      "user_id":   "sleeper_user_id",   # defaults to g_user_id
      "league_id": "league_id",         # defaults to g_league.league_id
    }

    Called automatically after every swipe via post_rank3(), but can also
    be triggered manually (e.g. on tab switch).
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    service   = sess["service"]
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    body      = request.get_json(force=True) or {}
    user_id   = body.get("user_id")   or g_user_id
    league_id = body.get("league_id") or g_league.league_id

    all_rankings = service.get_rankings(position=None)
    payload = [
        {"player_id": rp.player.id, "elo": rp.elo}
        for rp in all_rankings.rankings
    ]

    try:
        upsert_member_rankings(
            user_id        = user_id,
            league_id      = league_id,
            rankings       = payload,
            scoring_format = _active_format(sess),
        )
        log.info("rankings/submit [%s] — user=%s league=%s players=%d",
                 _active_format(sess), user_id, league_id, len(payload))
        return jsonify({"ok": True, "submitted": len(payload)})
    except Exception as e:
        log.error("rankings/submit error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/preferences", methods=["GET"])
@_gate_unverified_read
def get_league_preferences():
    """
    GET /api/league/preferences?league_id=...
    Returns the logged-in user's stored preferences for the given league.

    Response:
        {
          "team_outlook":          "championship" | null,
          "acquire_positions":     ["WR", "TE"],
          "trade_away_positions":  ["QB"]
        }
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    league_id = request.args.get("league_id") or g_league.league_id
    user_id   = request.args.get("user_id")   or g_user_id
    try:
        prefs = load_league_preference(user_id=user_id, league_id=league_id)
        declared = (prefs or {}).get("team_outlook")
        payload = prefs if prefs is not None else {
            "team_outlook":          None,
            "acquire_positions":     [],
            "trade_away_positions":  [],
        }
        # Backlog #8 — when no outlook is declared, surface the inferred one
        # (+ signals) so the client can render a one-tap confirm. Additive and
        # flag-gated; absent when trade.outlook_seed is off.
        if not declared and user_id == g_user_id:
            inferred, signals = _infer_user_outlook(g_user_id, league_id, sess, g_league)
            if inferred:
                payload = {**payload,
                           "inferred_outlook": inferred,
                           "inferred_signals": signals}
        return jsonify(payload)
    except Exception as e:
        log.error("get_league_preferences error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/preferences", methods=["POST"])
@_gate_unverified_write
def set_league_preferences():
    """
    POST /api/league/preferences
    Body: {
        "league_id":             "...",
        "team_outlook":          "championship|contender|rebuilder|jets|not_sure",
        "acquire_positions":     ["WR", "TE"],   (optional)
        "trade_away_positions":  ["QB"]           (optional)
    }

    Sets the user's team outlook and optional positional preferences for the
    given league. Persisted in DB.
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    body                 = request.get_json(force=True) or {}
    league_id            = body.get("league_id")    or g_league.league_id
    user_id              = body.get("user_id")      or g_user_id
    outlook              = body.get("team_outlook")
    acquire_positions    = body.get("acquire_positions")    # may be None or list
    trade_away_positions = body.get("trade_away_positions") # may be None or list

    valid = {"championship", "contender", "rebuilder", "jets", "not_sure"}
    if not outlook or outlook not in valid:
        return jsonify({"error": f"team_outlook must be one of {sorted(valid)}"}), 400

    # Validate positional arrays if supplied
    valid_positions = {"QB", "RB", "WR", "TE"}
    if acquire_positions is not None and not isinstance(acquire_positions, list):
        return jsonify({"error": "acquire_positions must be an array"}), 400
    if trade_away_positions is not None and not isinstance(trade_away_positions, list):
        return jsonify({"error": "trade_away_positions must be an array"}), 400

    try:
        upsert_league_preference(
            user_id              = user_id,
            league_id            = league_id,
            team_outlook         = outlook,
            acquire_positions    = acquire_positions,
            trade_away_positions = trade_away_positions,
        )
        log.info("league_preferences/set — user=%s league=%s outlook=%s acquire=%s away=%s",
                 user_id, league_id, outlook, acquire_positions, trade_away_positions)
        # Outlook drives the trade-engine's preference multiplier — any
        # cached deck for THIS league is now stale. Drop the league-scoped
        # cache entry so the next /api/trades/generate spawns a fresh job.
        try:
            _invalidate_trade_jobs(user_id=user_id, league_id=league_id)
        except Exception as inv_err:
            log.warning("league/preferences: trade-cache invalidation failed: %s", inv_err)
        return jsonify({
            "ok":                    True,
            "team_outlook":          outlook,
            "acquire_positions":     acquire_positions or [],
            "trade_away_positions":  trade_away_positions or [],
        })
    except Exception as e:
        log.error("set_league_preferences error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/asset-prefs", methods=["GET"])
@_gate_unverified_read
def get_asset_prefs():
    """GET /api/league/asset-prefs?league_id=... — the caller's untouchables +
    targets for a league (backlog #2).

    Response: {"untouchables": [player_id, ...], "targets": [player_id, ...]}
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    league_id = request.args.get("league_id") or g_league.league_id
    try:
        return jsonify(load_asset_preferences(user_id=g_user_id, league_id=league_id))
    except Exception as e:
        log.error("get_asset_prefs error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/asset-prefs", methods=["POST"])
@_gate_unverified_write
def set_asset_prefs():
    """POST /api/league/asset-prefs — tag/untag one player for a league (#2).

    Body: {"league_id": "...", "player_id": "4046",
           "list": "untouchable" | "target" | "none"}
    "none" removes any tag. A player can hold only one tag per league (setting
    a new one replaces the old). Returns the refreshed lists.
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    body      = request.get_json(force=True) or {}
    league_id = body.get("league_id") or g_league.league_id
    player_id = body.get("player_id")
    list_arg  = body.get("list")
    if not player_id:
        return jsonify({"error": "player_id required"}), 400
    list_type = None if list_arg in (None, "none") else list_arg
    if list_type is not None and list_type not in ASSET_PREF_LISTS:
        return jsonify({"error": f"list must be one of {sorted(ASSET_PREF_LISTS)} or 'none'"}), 400
    try:
        lists = set_asset_preference(
            user_id=g_user_id, league_id=league_id,
            player_id=str(player_id), list_type=list_type,
        )
        # Label stream for the deferred acceptance model (#65) — non-fatal.
        try:
            record_event(
                g_user_id,
                "asset_pref_removed" if list_type is None else "asset_pref_added",
                league_id=league_id,
                props={"player_id": str(player_id), "list_type": list_type},
            )
        except Exception:
            pass
        # Tags change candidate generation — drop this league's cached deck.
        try:
            _invalidate_trade_jobs(user_id=g_user_id, league_id=league_id)
        except Exception as inv_err:
            log.warning("asset-prefs: trade-cache invalidation failed: %s", inv_err)
        return jsonify({"ok": True, **lists})
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        log.error("set_asset_prefs error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/summary")
def league_summary_route():
    """GET /api/league/summary?league_id=XXX

    Returns the roll-up shown on the League Summary page:
      - matches_mutual / matches_awaiting (current user's; mirror the
        Matches tab's "Mutual matches" / "Awaiting them" segments — #91)
      - matches_pending / matches_accepted (deprecated status-split counts,
        kept for pre-1.4 clients)
      - total_teams (TOTAL teams in the league, caller included — Sleeper's
        total_rosters when known, else leaguemates_total + 1; FB #41)
      - leaguemates_total / _joined / _unlocked_1qb / _unlocked_sf
      - default_scoring, league_name
    """
    sess = _require_initialized_session()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    league_id = request.args.get("league_id") or (g_league.league_id if g_league else "")
    if not league_id:
        return jsonify({"error": "league_id is required"}), 400
    try:
        summary = get_league_summary(league_id=league_id, user_id=g_user_id)
        return jsonify(summary)
    except Exception as e:
        log.error("league/summary error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/scoring", methods=["POST"])
@_gate_unverified_write
def league_scoring_route():
    """POST /api/league/scoring {league_id, format}

    Sets the league's default scoring format (shown on League Summary).
    This is informational — each user still has their own per-format
    rank sets that they switch between independently.
    """
    sess = _require_session()
    body       = request.get_json(force=True) or {}
    league_id  = body.get("league_id")
    fmt        = body.get("format", "")
    if not league_id:
        return jsonify({"error": "league_id is required"}), 400
    if fmt not in SCORING_FORMATS:
        return jsonify({"error": f"Invalid format: {fmt!r}"}), 400
    try:
        set_league_scoring(league_id, fmt)
        log.info("league/scoring %s → %s (by %s)", league_id, fmt, sess.get("user_id"))
        return jsonify({"ok": True, "league_id": league_id, "default_scoring": fmt})
    except Exception as e:
        log.error("league/scoring error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/coverage")
def league_coverage():
    """
    GET /api/league/coverage?league_id=...
    Returns how many leaguemates have submitted rankings for the league.

    Response:
    {
      "ranked": 3,
      "total":  11,
      "members": [
        {"user_id": "...", "username": "...", "has_rankings": true}, ...
      ]
    }
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    league_id = request.args.get("league_id") or g_league.league_id
    user_id   = request.args.get("user_id")   or g_user_id

    try:
        coverage = get_ranking_coverage(
            league_id       = league_id,
            exclude_user_id = user_id,
        )
        return jsonify(coverage)
    except Exception as e:
        log.error("league/coverage error: %s", e)
        return jsonify({"error": "internal_error"}), 500


# ---------------------------------------------------------------------------
# Agent A4 — per-member unlock states + league activity feed
# ---------------------------------------------------------------------------
# Both endpoints are no-ops (return an empty payload) when their feature
# flag is off so the frontend can call them unconditionally without
# leaking data. Still gate in the UI for defence-in-depth.
# ---------------------------------------------------------------------------

@app.route("/api/league/member-unlock-states")
def league_member_unlock_states_route():
    """
    GET /api/league/member-unlock-states?league_id=...
    Returns each leaguemate's unlock state for the league summary card.

    Response:
        {
          "members": [
            {
              "user_id":            str,
              "username":           str,
              "display_name":       str,
              "avatar":             str | None,
              "joined":             bool,
              "unlocked_formats":   [..],
              "unlocked_count":     int,
              "has_ranking_method": bool
            }, ...
          ]
        }

    When the `league.unlock_badges_per_member` flag is off, returns
    `{"members": [], "flag_off": true}`.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    # Extension-auth sessions don't carry a 'league' key; guard with .get()
    g_league  = sess.get("league")
    league_id = request.args.get("league_id") or (g_league.league_id if g_league else "")
    if not league_id:
        return jsonify({"error": "league_id is required"}), 400

    if not is_enabled("league.unlock_badges_per_member"):
        return jsonify({"members": [], "flag_off": True})

    try:
        members = _league_members_cached(
            league_id       = league_id,
            exclude_user_id = g_user_id,
        )
        return jsonify({"members": members})
    except Exception as e:
        log.error("league/member-unlock-states error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/members")
def league_members_route():
    """
    GET /api/league/members?league_id=...
    Returns the roster of leaguemates with their join status. Powers
    the "Leaguemates" roster section on the League Summary page (with
    its Invite button in the top-right).

    Unlike /api/league/member-unlock-states this endpoint is NOT
    flag-gated — join status is base info, always shown.

    Response:
        {
          "members": [
            {
              "user_id":      str,
              "username":     str,
              "display_name": str,
              "avatar":       str | None,
              "joined":       bool,    # has a users row (i.e. has signed in to FTF)
            }, ...
          ]
        }

    Sort order: joined first (alphabetically by display_name), then
    not-joined (alphabetically by display_name).
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess.get("league")
    league_id = request.args.get("league_id") or (g_league.league_id if g_league else "")
    if not league_id:
        return jsonify({"error": "league_id is required"}), 400

    try:
        # Reuse existing per-member loader, then trim to the join-status
        # fields this section needs. Keeps a single source of truth for
        # the join determination. Cached (60s TTL) to coalesce the
        # back-to-back League screen calls — see _league_members_cached.
        rows = _league_members_cached(
            league_id       = league_id,
            exclude_user_id = g_user_id,
        )
        members = [
            {
                "user_id":      r["user_id"],
                "username":     r["username"],
                "display_name": r["display_name"],
                "avatar":       r["avatar"],
                "joined":       r["joined"],
            }
            for r in rows
        ]
        # Sort: joined first, then not-joined; alphabetical within each group.
        members.sort(key=lambda r: (
            0 if r["joined"] else 1,
            (r["display_name"] or "").lower(),
        ))
        return jsonify({"members": members})
    except Exception as e:
        log.error("league/members error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/activity")
def league_activity_route():
    """
    GET /api/league/activity?league_id=...&limit=20
    Returns a formatted activity feed of recent league events.

    Response:
        {
          "events": [
            {"ts": ISO, "emoji": str, "message": str,
             "actor_user_id": str, "event_type": str}, ...
          ]
        }

    When the `league.activity_feed` flag is off, returns
    `{"events": [], "flag_off": true}`.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    # Extension-auth sessions don't carry a 'league' key; guard with .get()
    g_league  = sess.get("league")
    league_id = request.args.get("league_id") or (g_league.league_id if g_league else "")
    if not league_id:
        return jsonify({"error": "league_id is required"}), 400

    if not is_enabled("league.activity_feed"):
        return jsonify({"events": [], "flag_off": True})

    try:
        raw_limit = request.args.get("limit", "20")
        try:
            limit = max(1, min(100, int(raw_limit)))
        except (TypeError, ValueError):
            limit = 20
        events = load_league_activity(league_id=league_id, limit=limit)
        return jsonify({"events": events})
    except Exception as e:
        log.error("league/activity error: %s", e)
        return jsonify({"error": "internal_error"}), 500


# ---------------------------------------------------------------------------
# League Contrarian Leaderboard
# ---------------------------------------------------------------------------
# Surfaces per-position "most contrarian" and "most consensus" ranking-takers
# in the league. Deviation is computed as the mean absolute difference between
# each user's ELO and the community-mean ELO, restricted to players that at
# least 2 users have ranked in the target position. Requires ≥3 users with
# rankings for the league + format; otherwise returns an empty-state message
# prompting the user to invite leaguemates.
# ---------------------------------------------------------------------------

_CONTRARIAN_POSITIONS = ("QB", "RB", "WR", "TE")


def _compute_contrarian_per_position(
    users_rankings: dict,
    player_positions: dict,
    position: str,
) -> dict:
    """Given {user_id: {username, elo_ratings: {player_id: elo}}} and a
    player_id→position map, compute each user's mean absolute deviation from
    the community mean for this position. Returns:

        {
            "most_contrarian": [{user_id, username, deviation}, ...],  # top 3
            "most_consensus":  [{user_id, username, deviation}, ...],  # top 3
            "ranked_users":    int,
            "player_count":    int,
        }

    Players are only included if at least 2 users have an ELO for them (so
    the community mean is non-trivial). Users are only included if they have
    at least 3 qualifying players.
    """
    # Collect ELOs per player for the target position
    pos_upper = position.upper()
    player_elos: dict[str, list[tuple[str, float]]] = {}
    for uid, udata in users_rankings.items():
        for pid, elo in (udata.get("elo_ratings") or {}).items():
            if player_positions.get(pid) == pos_upper:
                player_elos.setdefault(pid, []).append((uid, float(elo)))

    # Keep only players with >=2 raters so the mean is meaningful
    community_means = {
        pid: sum(e for _, e in entries) / len(entries)
        for pid, entries in player_elos.items()
        if len(entries) >= 2
    }

    # Per-user absolute deviations from community mean
    user_deviations: dict[str, list[float]] = {}
    for pid, mean_elo in community_means.items():
        for uid, elo in player_elos[pid]:
            user_deviations.setdefault(uid, []).append(abs(elo - mean_elo))

    # Require each user to have ranked at least 3 qualifying players
    leaderboard = []
    for uid, devs in user_deviations.items():
        if len(devs) < 3:
            continue
        username = users_rankings.get(uid, {}).get("username") or uid
        deviation = sum(devs) / len(devs)
        leaderboard.append({
            "user_id":       uid,
            "username":      username,
            "deviation":     round(deviation, 2),
            "player_count":  len(devs),
        })

    leaderboard.sort(key=lambda x: x["deviation"], reverse=True)
    top_contrarian = leaderboard[:3]
    top_consensus  = sorted(leaderboard, key=lambda x: x["deviation"])[:3]
    return {
        "most_contrarian": top_contrarian,
        "most_consensus":  top_consensus,
        "ranked_users":    len(leaderboard),
        "player_count":    len(community_means),
    }


@app.route("/api/league/contrarian")
def league_contrarian_route():
    """GET /api/league/contrarian?league_id=...&format=1qb_ppr|sf_tep

    Per-position contrarian leaderboard for the league. Requires at least 3
    users in the league to have stored rankings for the requested format.
    When the threshold isn't met, responds with an `insufficient_data` flag
    and a human-readable message.

    Response shape:
    {
        "league_id": "...",
        "format":    "1qb_ppr",
        "insufficient_data": false,
        "message":   "Invite leaguemates to unlock.",  # only when insufficient
        "qb": { "most_contrarian": [...], "most_consensus": [...],
                "ranked_users": 4, "player_count": 23 },
        "rb": { ... },
        "wr": { ... },
        "te": { ... }
    }
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    league_id = request.args.get("league_id") or (g_league.league_id if g_league else "")
    if not league_id:
        return jsonify({"error": "league_id is required"}), 400

    fmt = request.args.get("format") or _active_format(sess)
    if fmt not in SCORING_FORMATS:
        fmt = DEFAULT_SCORING

    try:
        # Fetch rankings for ALL users in the league (empty exclude matches
        # no real user_id). This returns {user_id: {username, elo_ratings}}.
        users_rankings = load_member_rankings(
            league_id       = league_id,
            exclude_user_id = "",
            scoring_format  = fmt,
        )

        # Distinct users with stored rankings for this format
        ranked_user_count = len(users_rankings)

        # Need at least 3 users with data to compute a meaningful community
        # baseline (contrarian score is relative to everyone else's mean).
        if ranked_user_count < 3:
            needed = 3 - ranked_user_count
            return jsonify({
                "league_id":          league_id,
                "format":             fmt,
                "insufficient_data":  True,
                "ranked_users":       ranked_user_count,
                "needed":             needed,
                "message":            "Invite leaguemates to unlock.",
                "qb": None, "rb": None, "wr": None, "te": None,
            })

        # Build player_id → position lookup once
        all_players = load_players(position=None)
        player_positions = {
            str(p.get("player_id")): (p.get("position") or "").upper()
            for p in all_players
            if p.get("player_id")
        }

        out = {
            "league_id":         league_id,
            "format":            fmt,
            "insufficient_data": False,
            "ranked_users":      ranked_user_count,
        }
        for pos in _CONTRARIAN_POSITIONS:
            out[pos.lower()] = _compute_contrarian_per_position(
                users_rankings, player_positions, pos
            )
        return jsonify(out)
    except Exception as e:
        log.error("league/contrarian error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/league/format-stats")
def league_format_stats_route():
    """GET /api/league/format-stats?league_id=...

    Lightweight check for the empty-state nudge on ranking views. Returns
    how many rankings the CURRENT user has saved in each scoring format,
    plus the league's detected default format. The frontend uses this to
    decide whether to show a "You haven't started ranking for {format}
    yet" CTA when a user navigates to a format they've never used.

    Response:
    {
      "league_id":       "...",
      "default_scoring": "1qb_ppr",
      "formats": {
        "1qb_ppr": { "ranking_count": 47 },
        "sf_tep":  { "ranking_count": 0 }
      }
    }
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    league_id = request.args.get("league_id") or (g_league.league_id if g_league else "")
    if not league_id:
        return jsonify({"error": "league_id is required"}), 400

    try:
        # Per-format counts for THIS user only. load_member_rankings excludes
        # a single user, so we call it with a dummy value to get every user,
        # then filter to our own rows. Simple and avoids a new DB helper.
        by_user = load_member_rankings(
            league_id       = league_id,
            exclude_user_id = "",
            scoring_format  = DEFAULT_SCORING,
        )
        count_default = len((by_user.get(g_user_id) or {}).get("elo_ratings") or {})

        other_fmt = "sf_tep" if DEFAULT_SCORING == "1qb_ppr" else "1qb_ppr"
        by_user_other = load_member_rankings(
            league_id       = league_id,
            exclude_user_id = "",
            scoring_format  = other_fmt,
        )
        count_other = len((by_user_other.get(g_user_id) or {}).get("elo_ratings") or {})

        # Detected league scoring (for informational badge)
        try:
            detected = get_league_scoring(league_id)
        except Exception:
            detected = None

        return jsonify({
            "league_id":       league_id,
            "default_scoring": detected or DEFAULT_SCORING,
            "formats": {
                DEFAULT_SCORING: {"ranking_count": count_default},
                other_fmt:       {"ranking_count": count_other},
            },
        })
    except Exception as e:
        log.error("league/format-stats error: %s", e)
        return jsonify({"error": "internal_error"}), 500


# ---------------------------------------------------------------------------
# Sleeper API Proxy Routes
# ---------------------------------------------------------------------------

@app.route("/api/sleeper/user/<path:username>")
def sleeper_user(username):
    """Validate a Sleeper username and return basic user info.

    Sleeper usernames are always lowercase and the API is case-sensitive —
    it returns JSON null (not a 404) for unknown users.  We normalise to
    lowercase here so users don't have to type their name exactly right.
    """
    raw_username = username
    username = username.strip().lower()
    log.info("=== /api/sleeper/user  raw=%r  normalised=%r", raw_username, username)

    if not username:
        log.warning("  rejected: empty username")
        return jsonify({"error": "Username is required"}), 400

    # ── Local test user bypass ──────────────────────────────────────────
    # Usernames matching "test_user_fp_*" skip the Sleeper API and return
    # a synthetic user object so test accounts can log in locally.
    # Disabled in production (non-SQLite DATABASE_URL): otherwise anyone
    # could mint phantom accounts or log in as the seeded test users.
    if username.startswith("test_user_fp_"):
        if _IS_PROD_ENV:
            log.warning("  test user bypass rejected in production for %r", username)
            return jsonify({"error": "User not found"}), 404
        log.info("  🧪 test user bypass for %r", username)
        return jsonify({
            "user_id": username,
            "display_name": username,
            "username": username,
            "avatar": None,
            "is_bot": False,
        })

    # ── Seeded test-league logins (User1..User5) ────────────────────────
    # Hardcoded so the synthetic "Lakeview League (Test)" owners are loginable
    # (these shadow the real Sleeper user1..user5 names). Resolved against the
    # DB case-insensitively so ONLY actually-seeded test owners bypass Sleeper;
    # if a name in the set isn't seeded, fall through to the real lookup below.
    if username in {"user1", "user2", "user3", "user4", "user5"}:
        _seeded = get_user_by_username(username)
        if _seeded:
            log.info("  🧪 seeded test-league login for %r", username)
            return jsonify({
                "user_id":      _seeded["sleeper_user_id"],
                "display_name": _seeded.get("display_name") or _seeded.get("username") or username,
                "username":     _seeded.get("username") or username,
                "avatar":       _seeded.get("avatar"),
                "is_bot":       False,
            })

    url = f"https://api.sleeper.app/v1/user/{urllib.parse.quote(username)}"
    log.info("  calling Sleeper: %s", url)

    try:
        data = _sleeper_get(url)

        log.info("  Sleeper returned type=%s  value=%r", type(data).__name__,
                 str(data)[:200] if data is not None else "null")

        # Sleeper returns JSON null for unknown users — treat as 404
        if data is None:
            log.warning("  result=NULL → user not found")
            return jsonify({"error": "User not found"}), 404

        # Sanity-check: a valid user object always has a user_id
        if not isinstance(data, dict):
            log.error("  unexpected response type %s: %r", type(data).__name__, str(data)[:200])
            return jsonify({"error": f"Unexpected Sleeper response type: {type(data).__name__}"}), 500

        user_id = data.get("user_id")
        log.info("  user_id=%r  display_name=%r  username_field=%r",
                 user_id, data.get("display_name"), data.get("username"))

        if not user_id:
            log.warning("  result has no user_id — treating as not found. keys=%s", list(data.keys()))
            return jsonify({"error": "User not found"}), 404

        log.info("  ✅ login OK  user_id=%s", user_id)
        return jsonify(data)

    except urllib.error.HTTPError as e:
        # Only a 4xx means the user genuinely doesn't exist. A 5xx is a
        # Sleeper outage — telling the user "User not found" sends them down
        # a dead end of retyping a correct username. Surface it as 503 so the
        # client can show a "try again shortly" message instead.
        if e.code >= 500:
            log.warning("  Sleeper HTTPError %s — upstream unavailable", e.code)
            return jsonify({"error": "sleeper_unavailable",
                            "message": "Sleeper is unavailable — try again shortly."}), 503
        log.warning("  HTTPError %s — user not found", e.code)
        return jsonify({"error": "User not found"}), 404
    except urllib.error.URLError as e:
        log.warning("  Sleeper URLError — upstream unreachable: %s", e)
        return jsonify({"error": "sleeper_unavailable",
                        "message": "Sleeper is unavailable — try again shortly."}), 503
    except Exception as e:
        log.error("  exception: %s\n%s", e, traceback.format_exc())
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/sleeper/leagues/<user_id>")
def sleeper_leagues(user_id):
    """Fetch NFL leagues for a Sleeper user (2026 season) + local DB leagues."""
    url = f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/2026"
    log.info("=== /api/sleeper/leagues  user_id=%r", user_id)
    sleeper_failed = False
    try:
        sleeper_data = _sleeper_get(url) or []
    except Exception as e:
        log.error("  leagues error: %s", e)
        sleeper_data = []
        sleeper_failed = True

    # Append any locally-stored leagues where this user is a member
    try:
        local = load_local_leagues_for_user(user_id)
        if local:
            log.info("  appending %d local league(s) for user %s", len(local), user_id)
        sleeper_data = list(sleeper_data) + local
    except Exception as e:
        log.warning("  local leagues load failed: %s", e)

    # Distinguish "Sleeper is down" from "this user genuinely has no leagues".
    # An empty list after a Sleeper failure would otherwise render as the
    # misleading "No leagues found — check your username" dead end.
    if sleeper_failed and not sleeper_data:
        log.error("  sleeper unavailable and no local leagues for user %s", user_id)
        return jsonify({"error": "sleeper_unavailable",
                        "message": "Couldn't reach Sleeper — try again shortly."}), 503

    if not sleeper_data:
        log.error("  no leagues found for user %s", user_id)
    return jsonify(sleeper_data)


@app.route("/api/sleeper/rosters/<league_id>")
def sleeper_rosters(league_id):
    """Fetch all rosters for a league — serves DB data for local non-Sleeper leagues."""
    log.info("=== /api/sleeper/rosters  league_id=%r", league_id)
    try:
        if not league_id.isdigit():
            data = load_local_league_rosters(league_id)
            log.info("  local league: returning %d rosters from DB", len(data))
            return jsonify(data)
        data = _sleeper_get(f"https://api.sleeper.app/v1/league/{league_id}/rosters")
        log.info("  returned %s rosters", len(data) if isinstance(data, list) else "non-list")
        return jsonify(data or [])
    except urllib.error.HTTPError as e:
        # 4xx → the league doesn't exist on Sleeper; 5xx → Sleeper outage.
        # Don't leak the raw upstream error string to the client.
        if e.code >= 500:
            log.warning("  rosters: Sleeper %s — upstream unavailable", e.code)
            return jsonify({"error": "sleeper_unavailable",
                            "message": "Sleeper is unavailable — try again shortly."}), 503
        log.warning("  rosters: Sleeper %s — league not found", e.code)
        return jsonify({"error": "league_not_found"}), 404
    except urllib.error.URLError as e:
        log.warning("  rosters: Sleeper unreachable: %s", e)
        return jsonify({"error": "sleeper_unavailable",
                        "message": "Sleeper is unavailable — try again shortly."}), 503
    except Exception as e:
        log.error("  rosters error: %s\n%s", e, traceback.format_exc())
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/sleeper/league_users/<league_id>")
def sleeper_league_users(league_id):
    """Fetch all users for a league — serves DB data for local non-Sleeper leagues."""
    log.info("=== /api/sleeper/league_users  league_id=%r", league_id)
    try:
        if not league_id.isdigit():
            data = load_local_league_users(league_id)
            log.info("  local league: returning %d users from DB", len(data))
            return jsonify(data)
        data = _sleeper_get(f"https://api.sleeper.app/v1/league/{league_id}/users")
        log.info("  returned %s users", len(data) if isinstance(data, list) else "non-list")
        return jsonify(data or [])
    except Exception as e:
        log.error("  league_users error: %s\n%s", e, traceback.format_exc())
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/debug/log")
def debug_log():
    """GET /api/debug/log?n=100  →  last N log entries as JSON

    Operator-only: the log buffer contains usernames, Sleeper user_ids and
    tracebacks, so this requires the same X-Cron-Secret as /api/cron/*.
    """
    _require_cron_auth()
    try:
        n = min(int(request.args.get("n", 100)), 200)
    except (TypeError, ValueError):
        return jsonify({"error": "n must be an integer"}), 400
    try:
        entries = list(_LOG_BUFFER)[-n:]
        return jsonify({"entries": entries, "total_buffered": len(_LOG_BUFFER)})
    except Exception as e:
        log.exception("debug_log failed")
        return jsonify({"error": "internal_error"}), 500


# ---------------------------------------------------------------------------
# Admin: model config (runtime-tunable multipliers)
# ---------------------------------------------------------------------------

@app.route("/api/admin/config", methods=["GET"])
def admin_config_list():
    """
    GET /api/admin/config
    Returns all model_config rows: [{key, value, description}, ...]
    sorted alphabetically by key.

    Operator-only (X-Cron-Secret, same as /api/cron/*).
    """
    _require_cron_auth()
    try:
        rows = list_config()
        return jsonify(rows)
    except Exception as e:
        log.exception("admin_config_list failed")
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/admin/config/<key>", methods=["PUT"])
def admin_config_update(key: str):
    """
    PUT /api/admin/config/<key>
    Body: {"value": <float>}
    Updates the config value, reloads both service modules, returns {key, value}.

    Operator-only (X-Cron-Secret, same as /api/cron/*): this mutates live
    ranking/trade math for every user, so it must never be world-callable.
    """
    _require_cron_auth()
    try:
        body = request.get_json(force=True) or {}
        if "value" not in body:
            return jsonify({"error": "body must contain 'value'"}), 400
        new_value = float(body["value"])
        result = set_config(key, new_value)

        # Reload live config in both service modules so the change takes
        # effect immediately (no server restart required).
        _trade_service_mod.reload_config()
        _ranking_service_mod.reload_config()

        log.info("🔧 Config updated: %s = %s", key, new_value)
        return jsonify(result)
    except KeyError:
        return jsonify({"error": f"Unknown config key: {key!r}"}), 404
    except (TypeError, ValueError) as e:
        return jsonify({"error": f"Invalid value: {e}"}), 400
    except Exception as e:
        log.exception("admin_config_update failed for key=%s", key)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/admin/engine-metrics", methods=["GET"])
def admin_engine_metrics():
    """
    GET /api/admin/engine-metrics?days=30&league_id=...

    Read-only aggregate health metrics for the trade engine: impression
    volume, like/pass rates by card basis / likes-you / deck position /
    package shape / league, and match conversion. This is the data the
    fairness_threshold and package_adj_gamma tuning is blocked on.

    Operator-only (X-Cron-Secret, same as /api/cron/*).
    """
    _require_cron_auth()
    try:
        days = max(1, min(int(request.args.get("days", 30)), 365))
        league_id = request.args.get("league_id") or None
        return jsonify(load_engine_telemetry(days=days, league_id=league_id))
    except (TypeError, ValueError):
        return jsonify({"error": "days must be an integer"}), 400
    except Exception as e:
        log.exception("admin_engine_metrics failed")
        return jsonify({"error": "internal_error"}), 500


def _ensure_sleeper_cache_populated() -> dict:
    """Populate the Sleeper player cache if it's missing.

    Returns the (in-memory) cache dict on success, or raises on network error.
    Shared by /api/sleeper/players and the browser-extension auth flow so
    the extension can work as the first hit on a cold server instance.
    """
    global _sleeper_cache
    cached = _load_sleeper_cache()
    if cached is not None:
        return cached

    if _TEST_MODE:
        # This bulk fetch uses raw urllib (not _sleeper_get), so the fixture
        # seam can't intercept it. In test mode the seeded warm-cache file IS
        # the data source — a miss here means the seeder output is missing.
        raise RuntimeError(
            f"players cache missing in test mode (expected seeded file at {PLAYERS_CACHE_FILE})")

    log.info("  📡 cache miss — fetching from Sleeper (~5MB)…")
    req = urllib.request.Request(
        "https://api.sleeper.app/v1/players/nfl",
        headers={"User-Agent": "FantasyTradeFinder/1.0"},
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = json.loads(r.read())

    log.info("  raw payload has %d players", len(raw))

    # Filter to skill positions only (cuts ~80% of the payload)
    relevant = {
        pid: p for pid, p in raw.items()
        if p.get("position") in ("QB", "RB", "WR", "TE")
        and p.get("full_name")
    }
    log.info("  filtered to %d skill-position players", len(relevant))

    # Persist to disk
    try:
        PLAYERS_CACHE_FILE.write_text(json.dumps(relevant))
        log.info("  ✅ wrote cache to %s", PLAYERS_CACHE_FILE)
    except Exception as e:
        log.warning("  could not write Sleeper cache: %s", e)

    _sleeper_cache = relevant

    # Sync to players DB table so /api/players has data.
    # Lock prevents two concurrent cold clients from running sync_players twice.
    try:
        with _player_sync_lock:
            if needs_player_sync():
                adp_map = _fetch_sleeper_adp()
                count = sync_players(relevant, adp_map=adp_map or None)
                log.info("  ✅ synced %d players to DB after cache fetch", count)
            else:
                log.info("  player DB already fresh — skipping sync")
    except Exception as sync_err:
        log.warning("  player DB sync after fetch failed: %s", sync_err)

    return relevant


@app.route("/api/sleeper/players")
def sleeper_players():
    """
    Return cached Sleeper bulk player data (QB/RB/WR/TE only).
    First call fetches ~5MB from Sleeper and caches to disk; subsequent
    calls are served instantly from memory.
    """
    log.info("=== /api/sleeper/players  (cache_loaded=%s)", _sleeper_cache is not None)
    cached = _load_sleeper_cache()
    if cached is not None:
        log.info("  serving from cache  size=%d", len(cached))
        return jsonify(cached)
    try:
        return jsonify(_ensure_sleeper_cache_populated())
    except Exception as e:
        log.error("  sleeper_players fetch error: %s\n%s", e, traceback.format_exc())
        return jsonify({"error": "internal_error"}), 500


# Mobile callers only want the side-effect (server-side cache hydration);
# the full /api/sleeper/players payload is ~4.8MB and discarded on the floor.
# This variant returns only {ok, count} so the warm hop is a few hundred bytes.
# Web client keeps /api/sleeper/players because it consumes the body.
@app.route("/api/sleeper/players/warm")
def sleeper_players_warm():
    try:
        cache = _ensure_sleeper_cache_populated()
        return jsonify({"ok": True, "count": len(cache)})
    except Exception as e:
        log.error("  sleeper_players_warm fetch error: %s\n%s", e, traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# Session Init — rebuilds player pool from real Sleeper roster
# ---------------------------------------------------------------------------

VALID_POSITIONS = {"QB", "RB", "WR", "TE"}


@app.route("/api/session/init", methods=["POST"])
def session_init():
    """
    Initialize the app with a real Sleeper roster.

    Expected body:
    {
      "user_id":          "sleeper_user_id",
      "league_id":        "sleeper_league_id",
      "league_name":      "My League Name",
      "user_player_ids":  ["1234", "5678", ...],
      "opponent_rosters": [
        { "user_id": "abc", "username": "SomeName", "player_ids": [...] },
        ...
      ]
    }
    """
    body              = request.get_json(force=True) or {}
    user_id           = body.get("user_id",          DEMO_USER_ID)
    league_id         = body.get("league_id",        "sleeper_league")
    league_name       = body.get("league_name",      "My Sleeper League")
    user_player_ids   = [str(x) for x in body.get("user_player_ids",  [])]
    opponent_rosters  = body.get("opponent_rosters", [])
    # Optional user info for the users table (sent by the frontend on first login)
    display_name      = body.get("display_name", "")
    username          = body.get("username", "")
    avatar            = body.get("avatar", None)
    # Referrer attribution (set only on user INSERT)
    invited_by        = body.get("invited_by") or None

    log.info("=== /api/session/init  user_id=%r  league=%r  "
             "user_players=%d  opponents=%d",
             user_id, league_id, len(user_player_ids), len(opponent_rosters))

    # ── Resolve existing session (league-switch reuses same token) ────────
    incoming_token = request.headers.get("X-Session-Token", "")
    with _sessions_lock:
        existing_sess  = _sessions.get(incoming_token)

    # ── Build universal ranking pool (once) ────────────────────────────
    # Rankings are user-level, not league-specific.  The ranking service
    # uses ALL Sleeper players that have a Dynasty Process value > 0, so
    # swipe history is preserved across league switches and page refreshes.
    player_db = _load_sleeper_cache()
    if player_db is None:
        return jsonify({"error": "Player database not cached — call GET /api/sleeper/players first"}), 400

    _ensure_universal_pools()
    if not g_universal_by_format.get("1qb_ppr", {}).get("players"):
        return jsonify({"error": "Could not build universal player pool — Dynasty Process data may be unavailable"}), 400

    # ── Ranking pools: one per scoring format ────────────────────────────
    # Rankings in 1QB PPR and SF TEP are completely independent rank sets.
    # Build ranking service state for both formats in parallel; the user's
    # "active format" governs which one is visible on each request.
    default_pool, default_seed = _get_universal_pool("1qb_ppr")
    ranking_pool = list(default_pool)   # for legacy code paths below
    ranking_seed = dict(default_seed)

    # Build a combined players dict for trade service (default pool)
    players_dict = {p.id: p for p in ranking_pool}

    # ── Build opponent LeagueMembers (league-specific for trades) ────────
    # Trade-engine v2 (P0-3): real league members must NOT get fabricated
    # random-noise valuations. Members without saved member_rankings carry
    # the consensus seed verbatim (has_rankings stays False); members WITH
    # real rankings get them injected later (_run_trade_job sets
    # has_rankings=True). Legacy path (flag off) keeps the noise byte-
    # for-byte. The simulated-fallback block further down is demo-only and
    # keeps its noise in both modes.
    _v2 = getattr(FLAGS, "trade_engine_v2", False)
    members: list[LeagueMember] = []
    for opp in opponent_rosters:
        opp_id    = str(opp.get("user_id", f"opp_{len(members)+1}"))
        opp_name  = opp.get("username", f"Opponent {len(members)+1}")
        opp_ids   = [str(x) for x in opp.get("player_ids", []) if str(x) in players_dict]
        if not opp_ids:
            continue
        if _v2:
            opp_elo = {pid: ranking_seed.get(pid, 1500) for pid in opp_ids}
        else:
            opp_elo = _biased_elo_random(opp_ids, ranking_seed)
        members.append(LeagueMember(
            user_id     = opp_id,
            username    = opp_name,
            roster      = opp_ids,
            elo_ratings = opp_elo,
        ))

    # ── Merge DB-stored league members (e.g. test users) ──────────────
    # Any member in the DB's league_members table who has a roster but
    # wasn't sent by the frontend (not a real Sleeper user) gets injected
    # so their member_rankings are used during trade generation.
    existing_member_ids = {m.user_id for m in members} | {user_id}
    try:
        db_members = load_league_members(league_id)
        for dbm in db_members:
            dbm_uid = dbm["user_id"]
            if dbm_uid in existing_member_ids:
                continue  # already in the list or is the logged-in user
            dbm_ids = [str(x) for x in dbm.get("player_ids", []) if str(x) in players_dict]
            if not dbm_ids:
                continue
            if _v2:
                # Real league member (DB-stored) — consensus seed, no noise.
                dbm_elo = {pid: ranking_seed.get(pid, 1500) for pid in dbm_ids}
            else:
                dbm_elo = _biased_elo_random(dbm_ids, ranking_seed)
            members.append(LeagueMember(
                user_id     = dbm_uid,
                username    = dbm.get("username") or dbm.get("display_name") or dbm_uid,
                roster      = dbm_ids,
                elo_ratings = dbm_elo,
            ))
            log.info("  📎 injected DB league member %s (%s) with %d roster players",
                     dbm_uid, dbm.get("username"), len(dbm_ids))
    except Exception as db_err:
        log.warning("  could not merge DB league members: %s", db_err)

    if not members:
        pool_ids = [p.id for p in ranking_pool if p.id not in set(user_player_ids)]
        random.shuffle(pool_ids)
        chunk = max(3, len(pool_ids) // 4)
        for i, opp_name in enumerate(["DynastyKing", "RookieDrafter", "VetHeavy", "WRCorner"]):
            opp_ids = pool_ids[i * chunk: (i + 1) * chunk]
            if not opp_ids:
                break
            members.append(LeagueMember(
                user_id      = f"opp_{i+1}",
                username     = opp_name,
                roster       = opp_ids,
                # Simulated (demo-style) opponents: keep the random-bias
                # opinions and treat them as "ranked" so demo behavior is
                # unchanged under trade-engine v2.
                elo_ratings  = _biased_elo_random(opp_ids, ranking_seed),
                has_rankings = True,
            ))

    new_league = League(
        league_id = league_id,
        name      = league_name,
        platform  = "sleeper",
        members   = members,
    )

    new_user_roster = [pid for pid in user_player_ids if pid in players_dict]

    # ── Ranking services: one per scoring format, rebuilt on user change ──
    # Rankings are user-level — the universal pools stay constant, so we
    # only rebuild when the user changes or on first load. Each format gets
    # its own RankingService loaded with only that format's swipes/overrides.
    existing_services = existing_sess.get("services") if existing_sess else None
    existing_tagged_user = None
    if existing_services:
        any_svc = next(iter(existing_services.values()), None)
        existing_tagged_user = getattr(any_svc, "_user_id", None) if any_svc else None
    need_rebuild = existing_services is None or existing_tagged_user != user_id

    if need_rebuild:
        from .database import SCORING_FORMATS as DB_SCORING_FORMATS

        def _build_service_for_format(fmt: str) -> tuple[str, RankingService]:
            """Build one format's RankingService — runs in a worker thread.

            Each format's pool/seed read from g_universal_by_format is
            read-only (populated by _ensure_universal_pools above), and the
            RankingService instance is freshly allocated here, so there is
            no shared mutable state between workers. DB reads
            (load_swipe_decisions, load_tier_overrides) use the engine's
            connection pool which is thread-safe.

            Exceptions on the per-format DB reads are already caught
            individually below to preserve the original behavior (partial
            replay is better than no service); any other unexpected
            exception propagates up to the executor and is re-raised from
            the main thread so the caller still sees the error.
            """
            fmt_pool, fmt_seed = _get_universal_pool(fmt)
            svc = RankingService(
                players           = fmt_pool,
                matchup_generator = matchup_gen,
                seed_ratings      = fmt_seed,
            )
            svc._user_id = user_id
            svc._scoring_format = fmt

            # Replay only the swipes tagged with this format
            try:
                historical = load_swipe_decisions(user_id=user_id, scoring_format=fmt)
                if historical:
                    replayed = svc.replay_from_db(historical)
                    log.info("  ✅ [%s] replayed %d/%d swipes", fmt, replayed, len(historical))
                else:
                    log.info("  [%s] (no stored swipe history)", fmt)
            except Exception as db_err:
                log.warning("  [%s] DB replay failed: %s", fmt, db_err)

            # Restore tier overrides for this format.
            #
            # IMPORTANT — do NOT filter overrides by current pool membership.
            # The previous version did:
            #     svc._elo_overrides = {pid: elo for pid, elo in overrides.items() if pid in valid_ids}
            # which silently dropped any pid that wasn't in fmt_pool at this
            # session_init (e.g. a QB who was momentarily missing from the
            # daily DP refresh, a rookie not yet ranked, a player rotated
            # off Sleeper's active list, etc).
            #
            # The dropped overrides then survived in memory just long enough
            # for the user's next save (any position) to overwrite the DB
            # row with the truncated dict — permanently destroying the
            # missing pids' overrides. A user who had 30+ QBs manually
            # elevated to Elite could end up with only 5 the next time
            # they opened the app.
            #
            # The fix is to keep the full override dict in memory unchanged.
            # apply_tiers and apply_reorder both already filter by current
            # pool when ASSIGNING overrides, so a stale pid sitting in the
            # dict is harmless — it just doesn't influence current rankings
            # until/unless that pid returns to the pool. No data loss.
            try:
                overrides = load_tier_overrides(user_id=user_id, scoring_format=fmt)
                svc._elo_overrides = {pid: float(elo) for pid, elo in overrides.items()}
                if svc._elo_overrides:
                    log.info("  ✅ [%s] restored %d tier overrides", fmt, len(svc._elo_overrides))
            except Exception as db_err:
                log.warning("  [%s] tier override restore failed: %s", fmt, db_err)

            return fmt, svc

        # Build each format's RankingService in parallel. The two formats
        # are independent (separate pools, separate DB queries, separate
        # service instances), so wall time drops to ~max(fmt_a, fmt_b)
        # instead of the sum. Result is required before /api/trio can run,
        # so we block on completion here — see "critical path" in PR.
        new_services: dict = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(DB_SCORING_FORMATS),
            thread_name_prefix="session-init-rank",
        ) as pool:
            futures = [pool.submit(_build_service_for_format, fmt)
                       for fmt in DB_SCORING_FORMATS]
            for fut in concurrent.futures.as_completed(futures):
                # If a worker raised, surface it here. The inner try/except
                # blocks already swallow DB-read failures (preserving the
                # original "best-effort replay" behavior); anything that
                # reaches this point is a real programming error and
                # should fail the request loudly rather than silently
                # returning a half-built session.
                fmt, svc = fut.result()
                new_services[fmt] = svc
    else:
        new_services = existing_services
        log.info("  ✅ ranking services preserved (same user, universal pools)")

    # Backwards-compat: keep sess['service'] pointing at the currently-active
    # format's service. Any legacy endpoint that still reads sess['service']
    # gets the right one automatically.
    # Active format is resolved below after we load the league's default.


    # Trade services: one per scoring format, rebuilt per league.
    # Load past trade decisions (last 7 days) so already-swiped trades don't reappear.
    past_decision_keys: set = set()
    try:
        past_td = load_trade_decisions(user_id=user_id, league_id=league_id, since_days=7)
        for td in past_td:
            key = (frozenset(td["give_player_ids"]), frozenset(td["receive_player_ids"]))
            past_decision_keys.add(key)
        if past_decision_keys:
            log.info("  loaded %d past trade decisions (7-day window)", len(past_decision_keys))
    except Exception as db_err:
        log.warning("  could not load past trade decisions: %s", db_err)

    new_trade_svcs: dict = {}
    from .database import SCORING_FORMATS as DB_SCORING_FORMATS
    for fmt in DB_SCORING_FORMATS:
        fmt_pool, _ = _get_universal_pool(fmt)
        fmt_players_dict = {p.id: p for p in fmt_pool}
        tsvc = TradeService(players=fmt_players_dict, past_decision_keys=past_decision_keys)
        tsvc.add_league(new_league)
        new_trade_svcs[fmt] = tsvc

    # ── Resolve active format ────────────────────────────────────────────
    # Priority: body param > session carry-over > league default > DEFAULT
    requested_format = body.get("active_format")
    try:
        from .database import get_league_scoring, DEFAULT_SCORING as DB_DEFAULT
    except ImportError:
        DB_DEFAULT = "1qb_ppr"
    if requested_format in DB_SCORING_FORMATS:
        active_format = requested_format
    elif existing_sess and existing_sess.get("active_format") in DB_SCORING_FORMATS:
        active_format = existing_sess["active_format"]
    else:
        try:
            active_format = get_league_scoring(league_id)
        except Exception:
            active_format = DB_DEFAULT

    # ── Create or update session ─────────────────────────────────────────
    session_payload = {
        "user_id":       user_id,
        "league":        new_league,
        "players":       ranking_pool,
        "user_roster":   new_user_roster,
        "services":      new_services,                  # dict[format, RankingService]
        "service":       new_services[active_format],   # alias to active format
        "trade_svcs":    new_trade_svcs,                # dict[format, TradeService]
        "trade_svc":     new_trade_svcs[active_format], # alias to active format
        "active_format": active_format,
        "display_name":  display_name,
        "last_active":   time.time(),
    }
    with _sessions_lock:
        if existing_sess:
            token = incoming_token
            # Verified state (account-auth P1) survives a same-user re-init
            # (league switch, revalidate) — the Sleeper-JWT proof bound the
            # SESSION to the user, not to a league. It must NOT survive the
            # token being re-pointed at a different user_id.
            if existing_sess.get("user_id") != user_id:
                existing_sess.pop("verified", None)
                existing_sess.pop("verified_via", None)
            existing_sess.update(session_payload)
            session_verified = bool(existing_sess.get("verified"))
        else:
            token = secrets.token_urlsafe(32)
            _sessions[token] = session_payload
            session_verified = False

    # ── Defer DB upserts + push fanout + Sleeper meta to a daemon ────────
    # Everything below this point that isn't required for the response
    # (session is already in `_sessions`, all in-memory services are
    # built) runs on a background daemon thread so the client sees the
    # response as soon as the ranking services are ready.
    #
    # What runs on the daemon (all best-effort, no caller depends on it
    # before /api/trio fires):
    #   • upsert_user + upsert_league + record_event
    #   • referral_joined push (first-session-with-invited_by only)
    #   • league_member_joined peer push fanout (N peers × push)
    #   • _fetch_sleeper_league_meta + set_league_scoring (auto-detect)
    #   • upsert_league_members
    #
    # Why this is safe:
    #   • The Flask `g` is request-scoped and unsafe to touch from
    #     another thread, so `device_info` is captured here.
    #   • All other names used inside the closure are local variables
    #     bound at function entry (request body, computed locals like
    #     `token`, `new_user_roster`, `opponent_rosters`) — they remain
    #     valid for the lifetime of the daemon since the closure holds
    #     references to them.
    #   • Each sub-step is already wrapped in try/except in the original
    #     code; the outer wrapper here is the explicit "swallow all"
    #     boundary required for daemon threads (silent swallowed
    #     exceptions in daemons are the silent-bug anti-pattern, so we
    #     log.exception any escapee).
    _ev_info = getattr(g, "device_info", {}) or {}

    def _session_init_background_writes() -> None:
        """Run after-response side effects on a daemon thread.

        Wrapped in a single broad except — a daemon that raises silently
        is exactly the silent-bug pattern called out in
        docs/reviews/2026-05-22-silent-bugs.md, so we log.exception on
        any escape rather than letting the thread die quietly.
        """
        try:
            # Agent 4 addition: capture INSERT-vs-UPDATE state BEFORE
            # upsert_user runs so we can emit a one-time referral-receipt
            # notification on the referred user's first session.
            # upsert_user only applies `invited_by` on INSERT, so this is
            # also our only window to attribute the join.
            _is_new_user = False
            try:
                _is_new_user = not user_exists(user_id)
            except Exception as _check_err:
                log.warning("  referral receipt: user_exists check failed (%s)", _check_err)
            try:
                upsert_user(
                    sleeper_user_id=user_id,
                    username=username,
                    display_name=display_name,
                    avatar=avatar,
                    invited_by=invited_by,
                )
                upsert_league(
                    league_id        = league_id,
                    user_id          = user_id,
                    name             = league_name,
                    season           = "2026",
                    user_player_ids  = new_user_roster,
                    opponent_rosters = opponent_rosters,
                )
                log.info("  ✅ user + league upserted in DB (bg)")

                # User-event log: signup on first session, app_open
                # thereafter. Fires after upsert_user so the row is
                # guaranteed to exist for the FK-style update inside
                # record_event().
                try:
                    record_event(
                        user_id,
                        "signup" if _is_new_user else "app_open",
                        league_id  = league_id,
                        session_id = token,
                        source     = "api",
                        **_ev_info,
                    )
                except Exception as _ev_err:
                    log.warning("  record_event failed: %s", _ev_err)

                # ── Referral receipt notification ────────────────────
                # Fires exactly once: on the NEW user's very first
                # session_init when they arrived with an invited_by
                # attribution. Posts a bell notification to the
                # referrer resolved-by-username.
                if _is_new_user and invited_by:
                    try:
                        referrer = get_user_by_username(invited_by)
                        if referrer and referrer.get("sleeper_user_id"):
                            referrer_uid  = referrer["sleeper_user_id"]
                            new_username  = username or display_name or user_id
                            push_notification(
                                user_id=referrer_uid,
                                type="referral_joined",
                                body=f"🤝 @{new_username} joined Fantasy Trade Finder via your invite.",
                                meta={
                                    "new_user_id":   user_id,
                                    "new_username":  new_username,
                                    "invited_by":    invited_by,
                                },
                            )
                            log.info("  ✅ referral_joined notification → @%s (uid=%s)",
                                     invited_by, referrer_uid)
                        else:
                            log.info("  referral_joined: referrer @%s not found in users table",
                                     invited_by)
                    except Exception as ref_err:
                        log.warning("  referral receipt emit failed (continuing): %s", ref_err)

                # ── league_member_joined peer push fanout ────────────
                # Fires once per (existing leaguemate, joining user)
                # pair on the joining user's first session. Doesn't ping
                # the joiner. Capped implicitly by the dedup_key — a
                # returning user re-init won't re-fire because
                # _is_new_user is False.
                if _is_new_user:
                    try:
                        _new_username = username or display_name or user_id
                        _peers = load_league_member_unlock_states(
                            league_id, exclude_user_id=user_id,
                        )
                        for _p in _peers:
                            if not _p.get("joined") or not _p.get("user_id"):
                                continue
                            _send_typed_push(
                                _p["user_id"],
                                "league_member_joined",
                                title = "🤝 New leaguemate on Fantasy Trade Finder",
                                body  = f"@{_new_username} joined {league_name}. More trades may unlock.",
                                data  = {"new_user_id":  user_id,
                                         "new_username": _new_username,
                                         "league_id":    league_id,
                                         "league_name":  league_name},
                                dedup_key = f"joined:{user_id}:{_p['user_id']}",
                            )
                    except Exception as lm_err:
                        log.warning("  league_member_joined push failed: %s", lm_err)

                # ── Auto-detect league scoring format from Sleeper ───
                # Fires on every session/init for leagues without a
                # format on file. Retrying on each init (when
                # existing_fmt is falsy) self-heals leagues whose first
                # sync hit a Sleeper API flake — subsequent logins keep
                # attempting until detection succeeds. Once stored, the
                # Sleeper call is skipped.
                #
                # NOTE: now runs on the background daemon. The session
                # response uses whatever format `get_league_scoring`
                # returned at request time (or the body override). On
                # a brand-new league this is the DB default until the
                # daemon writes the detected format — the next
                # session_init picks it up. Existing leagues are
                # unaffected: the detected format already matches the
                # stored format in steady state.
                try:
                    existing_fmt = None
                    try:
                        existing_fmt = get_league_scoring(league_id)
                    except Exception:
                        pass
                    meta = _fetch_sleeper_league_meta(league_id)
                    if meta:
                        # FB #41 — persist the league's TRUE team count.
                        # league_members can't be trusted for this: clients
                        # drop ownerless rosters from opponent_rosters and
                        # stale rows linger after a manager leaves.
                        try:
                            _tr = meta.get("total_rosters")
                            if isinstance(_tr, int) and _tr > 0:
                                set_league_total_rosters(league_id, _tr)
                        except Exception as tr_err:
                            log.warning("  total_rosters persist failed (continuing): %s", tr_err)
                        detected = _detect_scoring_format_from_meta(meta)
                        if detected != existing_fmt:
                            set_league_scoring(league_id, detected)
                            log.info("  ✅ league scoring (re-)detected: %s (was: %r)", detected, existing_fmt)
                        else:
                            log.info("  ✅ league scoring confirmed: %s", detected)
                    else:
                        log.info("  ℹ️  league scoring auto-detect deferred — Sleeper meta unavailable")
                except Exception as e:
                    log.warning("  league scoring auto-detect failed (continuing): %s", e)
            except Exception as db_err:
                log.warning("  DB upsert failed (continuing): %s", db_err)

            # ── Persist full league membership roster ────────────────
            try:
                all_members_for_db = [
                    {
                        "user_id":      user_id,
                        "username":     display_name or username or user_id,
                        "display_name": display_name,
                        "player_ids":   new_user_roster,
                    }
                ] + [
                    {
                        "user_id":      str(opp.get("user_id", "")),
                        "username":     opp.get("username", ""),
                        "display_name": opp.get("username", ""),
                        "player_ids":   [str(x) for x in opp.get("player_ids", [])],
                    }
                    for opp in opponent_rosters
                    if opp.get("user_id")
                ]
                upsert_league_members(league_id=league_id, members=all_members_for_db)
                log.info("  ✅ league_members upserted (%d members)", len(all_members_for_db))
                # Roster changed → drop cached _league_members projections
                # so the next /api/league/members call rebuilds the
                # join-status list. (Picked up from PR #63 #B4 cache.)
                _invalidate_league_members_cache(league_id)
            except Exception as db_err:
                log.warning("  league_members upsert failed (continuing): %s", db_err)
        except Exception:
            # Daemon top-level catch — see docstring. Never silently die.
            log.exception("session/init background writes crashed")

    threading.Thread(
        target=_session_init_background_writes,
        name="session-init-bg-writes",
        daemon=True,
    ).start()

    generic_pick_count = sum(1 for p in g_universal_players if p.pick_value is not None)
    log.info("✅ session/init done — %d universal players (%d generic picks), %d on roster, %d opponents",
             len(g_universal_players), generic_pick_count, len(new_user_roster), len(members))

    real_player_count = sum(1 for p in ranking_pool if p.pick_value is None)

    # ── Pre-generate trade cards in the background ───────────────────────
    # The user just imported a league; they're a few taps away from the
    # Trades tab. Kick off a generate job now so the deck is ready by the
    # time they get there. We only kick off if there's no fresh cached job
    # for (user, league, format) already. The thread.start() returns
    # immediately — session_init's response is unaffected.
    try:
        # `active_format`, `token`, and `members` are all in local scope at
        # this point (set above). Don't re-read from the session dict —
        # we already have the right values.
        pregen_key = _trade_job_key(user_id, league_id, active_format)
        with _trade_jobs_lock:
            existing_id = _trade_jobs_by_key.get(pregen_key)
            existing    = _trade_jobs.get(existing_id) if existing_id else None
            should_kickoff = (existing is None) or (
                existing.get("status") == "complete"
                and (time.monotonic() - (existing.get("finished_at") or 0)) > _PREGEN_TTL_SECONDS
            )
        if should_kickoff:
            opp_total = sum(1 for m in members if m.user_id != user_id and m.elo_ratings)
            _kickoff_trade_job(
                sess_token         = token,
                user_id            = user_id,
                league_id          = league_id,
                scoring_format     = active_format,
                fairness_threshold = 0.75,
                pinned_give        = None,
                opponents_total    = opp_total,
            )
            log.info("session/init: kicked off pre-gen trade job for league=%s", league_id)
    except Exception as pregen_err:
        # Pre-gen is best-effort. Never let it break session_init.
        log.warning("session/init: pre-gen kickoff failed: %s", pregen_err)

    # ── Verified-session state (account-auth P1, additive field) ─────────
    # The mobile "Verify your account" banner keys off this:
    #   session_verified — THIS session proved control (Sleeper-JWT + oracle)
    #   user_verified    — SOME controller has verified this user_id; an
    #                      unverified session for a verified user_id has
    #                      already lost write access (squatter case)
    #   enforced         — grace is over (auth.enforce_verified_writes)
    verified_via = None
    try:
        from . import accounts as _accounts
        verified_via = _accounts.get_user_verified_via(user_id)
    except Exception as verif_err:
        log.warning("session/init: verified_via lookup failed: %s", verif_err)
    return jsonify({
        "ok":           True,
        "token":        token,
        "player_count": real_player_count,
        "pick_count":   generic_pick_count,
        "user_roster":  [player_to_dict(players_dict[pid]) for pid in new_user_roster if pid in players_dict],
        "league_id":    league_id,
        "opponents":    len(members),
        "verification": {
            "session_verified": session_verified,
            "user_verified":    bool(verified_via),
            "verified_via":     verified_via,
            "enforced":         is_enabled("auth.enforce_verified_writes"),
        },
    })


# ---------------------------------------------------------------------------
# Session Ping — lightweight liveness check
# ---------------------------------------------------------------------------

@app.route("/api/session/ping", methods=["GET"])
def session_ping():
    """GET /api/session/ping — check whether the current session is alive."""
    with _sessions_lock:
        sess = _sessions.get(request.headers.get("X-Session-Token", ""))
    if not sess:
        return jsonify({"ok": False}), 401
    sess["last_active"] = time.time()
    return jsonify({
        "ok":      True,
        "user_id": sess["user_id"],
        "league":  sess.get("league", {}).name if sess.get("league") else "",
    })


# ---------------------------------------------------------------------------
# Notifications API
# ---------------------------------------------------------------------------

@app.route("/api/notifications")
@_gate_unverified_read
def list_notifications():
    """
    GET /api/notifications?user_id=<uid>

    Returns unread + the last 20 read notifications for the session user,
    sorted newest-first.  A user_id query param is accepted for backwards
    compatibility but must match the session user — anything else is 403
    (notifications are private to their owner).
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    req_uid = request.args.get("user_id")
    if req_uid and req_uid != g_user_id:
        return jsonify({"error": "forbidden",
                        "message": "user_id does not match session user"}), 403
    uid = g_user_id
    if not uid:
        return jsonify({"notifications": [], "unread_count": 0})
    try:
        notifs      = get_notifications(uid)
        unread      = sum(1 for n in notifs if not n.get("is_read"))
        return jsonify({"notifications": notifs, "unread_count": unread})
    except Exception as e:
        log.error("list_notifications error: %s", e)
        return jsonify({"notifications": [], "unread_count": 0})


@app.route("/api/notifications/read", methods=["POST"])
@_gate_unverified_write
def read_notifications():
    """
    POST /api/notifications/read  { "user_id": "...", "ids": [1, 2, 3] }

    Marks the specified notification IDs as read for the session user.
    A body user_id is accepted for backwards compatibility but must match
    the session user — anything else is 403.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    body    = request.get_json(force=True) or {}
    req_uid = body.get("user_id")
    if req_uid and req_uid != g_user_id:
        return jsonify({"error": "forbidden",
                        "message": "user_id does not match session user"}), 403
    uid     = g_user_id
    ids     = body.get("ids") or []
    if not uid:
        return jsonify({"error": "user_id required"}), 400
    # Validate ids before touching the DB — a non-list (or non-int members)
    # otherwise reaches SQLAlchemy and 500s with leaked SQL internals.
    if not isinstance(ids, list):
        return jsonify({"error": "ids must be a list of integers"}), 400
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({"error": "ids must be a list of integers"}), 400
    try:
        updated = mark_notifications_read(uid, notification_ids=ids if ids else None)
        return jsonify({"ok": True, "updated": updated})
    except Exception as e:
        log.error("read_notifications error: %s", e)
        return jsonify({"error": "internal_error"}), 500


@app.route("/api/notifications/read-all", methods=["POST"])
@_gate_unverified_write
def read_all_notifications():
    """
    POST /api/notifications/read-all  { "user_id": "..." }

    Marks ALL unread notifications as read for the session user.
    A body user_id is accepted for backwards compatibility but must match
    the session user — anything else is 403.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    body = request.get_json(force=True) or {}
    req_uid = body.get("user_id")
    if req_uid and req_uid != g_user_id:
        return jsonify({"error": "forbidden",
                        "message": "user_id does not match session user"}), 403
    uid  = g_user_id
    if not uid:
        return jsonify({"error": "user_id required"}), 400
    try:
        updated = mark_notifications_read(uid, notification_ids=None)
        return jsonify({"ok": True, "updated": updated})
    except Exception as e:
        log.error("read_all_notifications error: %s", e)
        return jsonify({"error": "internal_error"}), 500


# ---------------------------------------------------------------------------
# Push dispatch — typed wrapper + raw Expo POST
# ---------------------------------------------------------------------------
# Two-layer design:
#
#   _send_expo_push(messages)         — raw Expo POST. Knows nothing about
#                                       prefs/quiet hours/caps. Direct callers
#                                       should be rare; the bundled-summary
#                                       cron uses it because it's already
#                                       made the gating decisions.
#
#   _send_typed_push(user_id, kind,   — high-level entry point. Looks up the
#                    title, body,     user's prefs, applies bucket gate,
#                    data, dedup_key) frequency cap, quiet-hours bundling,
#                                     fans out to all registered devices,
#                                     records event + log row. This is what
#                                     match-create / cron jobs / hooks call.
#
# Quiet-hours rule (per the plan):
#   If quiet_hours_enabled AND now-local is in 22:00–08:00 user-local, the
#   push is queued in notification_queue with deliver_after = next 08:00
#   user-local converted to UTC. The 8am hourly tick collapses every queued
#   row for a user into ONE bundled summary push.
#
# Frequency cap rules:
#   _NOTIF_FREQ_CAPS maps kind → (window_days, max_count). Re-engagement
#   kinds are the main consumers; transactional kinds are unbounded.

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_EXPO_TOKEN_PREFIX = "ExponentPushToken["

# kind → (window_days, max_within_window). Pushes exceeding the cap are
# silently dropped (still logged in user_events as `push_skipped` with the
# reason). Kinds not in this map have no cap.
_NOTIF_FREQ_CAPS: dict[str, tuple[int, int]] = {
    "winback_matches": (7,   1),
    "winback_dormant": (30,  1),
    "finish_ranking":  (30,  1),
    "season_start":    (365, 1),
}

# Per-dedup_key caps (e.g. "fire match_expiring at most 1× per match_id").
# Each kind here pairs with a dedup_key passed by the call site so the same
# logical event never re-pushes:
#   match_expiring                  → dedup_key = match_id
#   first_match                     → dedup_key = "lifetime" (per-user)
#   match_accepted                  → dedup_key = "accept:{match_id}:{actor_uid}"
#   league_member_joined            → dedup_key = "joined:{joiner_uid}:{leaguemate_uid}"
#   league_member_unlocked_trades   → dedup_key = "unlock:{user_uid}:{leaguemate_uid}"
_NOTIF_DEDUP_CAPS: set[str] = {
    "match_expiring",
    "first_match",
    "match_accepted",
    "league_member_joined",
    "league_member_unlocked_trades",
}


def _send_expo_push(messages: list) -> None:
    """POST a batch of Expo push messages. Non-throwing — swallows all
    errors and logs a warning. Chunks at 100 per request (Expo limit).

    Each message: { to: str, title: str, body: str, data: dict, sound?: "default" }
    Use _send_typed_push() for normal pushes; this is the raw transport.
    """
    if not messages:
        return
    try:
        clean = [m for m in messages if isinstance(m.get("to"), str)
                 and m["to"].startswith(_EXPO_TOKEN_PREFIX)]
        if not clean:
            return
        for i in range(0, len(clean), 100):
            chunk = clean[i:i + 100]
            body = json.dumps(chunk).encode("utf-8")
            req = urllib.request.Request(
                _EXPO_PUSH_URL,
                data=body,
                headers={
                    "Content-Type":  "application/json",
                    "Accept":        "application/json",
                    "Accept-encoding": "gzip, deflate",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                status = r.status
                if status >= 300:
                    log.warning("Expo push non-2xx: status=%s", status)
                else:
                    log.info("Expo push delivered: %d message(s)", len(chunk))
    except Exception as e:
        log.warning("_send_expo_push failed (non-fatal): %s", e)


def _local_hour_in_quiet_window(tz_name: str | None) -> bool:
    """True if the current time in `tz_name` is between 22:00 and 08:00."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name or "America/New_York")
    except Exception:
        return False
    h = datetime.now(tz).hour
    return h >= 22 or h < 8


def _next_8am_utc(tz_name: str | None) -> str:
    """Return the next 08:00 in `tz_name` as an ISO UTC string. On any tz
    resolution failure, fall back to 13:00 UTC tomorrow (~08:00 ET) so the
    queued push still drains in roughly the right morning window.
    """
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name or "America/New_York")
        now_local = datetime.now(tz)
        target = now_local.replace(hour=8, minute=0, second=0, microsecond=0)
        if now_local >= target:
            target = target + timedelta(days=1)
        return target.astimezone(timezone.utc).isoformat()
    except Exception:
        now_utc = datetime.now(timezone.utc)
        target = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
        if now_utc >= target:
            target = target + timedelta(days=1)
        return target.isoformat()


def _freq_cap_blocks(user_id: str, kind: str, dedup_key: str | None) -> bool:
    """Return True if the cap for (user_id, kind) is reached and the push
    must be skipped.
    """
    if kind in _NOTIF_DEDUP_CAPS and dedup_key:
        # Per-dedup_key lifetime cap (e.g. "fire match_expiring at most 1×
        # per match_id"). Skip if any prior row exists.
        return notification_dedup_sent(user_id, kind, dedup_key)

    cap = _NOTIF_FREQ_CAPS.get(kind)
    if not cap:
        return False
    window_days, max_count = cap
    since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    sent = count_notification_sends_since(user_id, kind, since)
    return sent >= max_count


def _send_typed_push(
    user_id: str,
    kind: str,
    *,
    title: str,
    body: str,
    data: dict | None = None,
    dedup_key: str | None = None,
) -> None:
    """High-level push entry point. Applies pref / cap / quiet-hours rules.
    Non-throwing — failures are logged.

    Flow:
      1. Look up user's prefs (defaults if missing row).
      2. Bucket gate — skip if the user has the relevant toggle off.
      3. Frequency cap — skip if (kind, user, window) is at or over the cap.
      4. Quiet hours — if active for the user, write to notification_queue
         and exit. The 8am cron drains and bundles.
      5. Otherwise: load device tokens, send via Expo, log + record_event.
    """
    if not user_id or not kind:
        return
    try:
        prefs = get_notification_prefs(user_id)
        bucket = NOTIF_KIND_TO_BUCKET.get(kind)
        if bucket and not int(prefs.get(bucket, 1)):
            log.info("push skipped (bucket=%s off): user=%s kind=%s", bucket, user_id, kind)
            return

        if _freq_cap_blocks(user_id, kind, dedup_key):
            log.info("push skipped (cap): user=%s kind=%s dedup=%s", user_id, kind, dedup_key)
            return

        # Quiet-hours check uses the user's saved tz, falling back to ET.
        if int(prefs.get("quiet_hours_enabled", 1)) and \
                _local_hour_in_quiet_window(prefs.get("tz")):
            queue_notification(
                user_id, kind,
                title=title, body=body, data=data or {},
                deliver_after=_next_8am_utc(prefs.get("tz")),
                dedup_key=dedup_key,
            )
            log.info("push queued (quiet hrs): user=%s kind=%s", user_id, kind)
            return

        # Active hours — fan out to every registered device for this user.
        targets = load_device_tokens_for_users([user_id])
        if not targets:
            return
        msgs = [{
            "to":    t["device_token"],
            "title": title,
            "body":  body,
            "data":  {**(data or {}), "type": kind},
            "sound": "default",
        } for t in targets]
        _send_expo_push(msgs)
        log_notification_send(user_id, kind, dedup_key=dedup_key)
        try:
            record_event(
                user_id, "push_sent",
                source="api",
                props={"kind": kind, "dedup_key": dedup_key},
            )
        except Exception:
            pass
    except Exception as e:
        log.warning("_send_typed_push failed (non-fatal): user=%s kind=%s err=%s",
                    user_id, kind, e)


@app.route("/api/notifications/register-device", methods=["POST"])
@_gate_unverified_write
def register_device_for_push():
    """Register an Expo push token for the authenticated user.

    Body: { "device_token": "ExponentPushToken[...]", "platform": "ios"|"android" }
    Returns: { ok: true }

    Idempotent — the underlying save_device_token() upserts on (device_token)
    so re-calling with the same token from the same user is a no-op beyond
    refreshing last_seen_at.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    body = request.get_json(force=True) or {}
    token    = (body.get("device_token") or "").strip()
    platform = (body.get("platform") or "").strip().lower()

    if not token or not token.startswith(_EXPO_TOKEN_PREFIX) or not token.endswith("]"):
        return jsonify({"error": "invalid_token",
                        "message": "device_token must be a valid Expo push token"}), 400
    if platform not in ("ios", "android"):
        return jsonify({"error": "invalid_platform",
                        "message": "platform must be 'ios' or 'android'"}), 400

    try:
        save_device_token(user_id=g_user_id, device_token=token, platform=platform)
        return jsonify({"ok": True})
    except Exception as e:
        log.error("register-device failed: %s", e)
        return jsonify({"error": "save_failed", "message": str(e)}), 500


@app.route("/api/notifications/prefs", methods=["GET"])
def get_notification_prefs_route():
    """GET /api/notifications/prefs → user's per-bucket toggles + quiet-hours
    setting + tz. Defaults are returned when no row exists; the response
    shape is stable regardless.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    return jsonify(get_notification_prefs(sess["user_id"]))


@app.route("/api/notifications/prefs", methods=["PUT"])
@_gate_unverified_write
def update_notification_prefs_route():
    """PUT /api/notifications/prefs — partial update. Body keys (all optional):
      trade_matches, weekly_digest, reengagement, quiet_hours_enabled (bool/0/1),
      tz (IANA string)
    Returns the full merged prefs dict.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    body = request.get_json(force=True) or {}
    allowed = {"trade_matches", "weekly_digest", "reengagement",
               "quiet_hours_enabled", "tz"}
    fields = {k: v for k, v in body.items() if k in allowed}
    if not fields:
        return jsonify({"error": "no_valid_fields"}), 400
    if "tz" in fields:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(str(fields["tz"]))
        except Exception:
            return jsonify({"error": "invalid_tz"}), 400
    try:
        out = upsert_notification_prefs(sess["user_id"], **fields)
        try:
            record_event(
                sess["user_id"], "notif_pref_changed",
                source="api", props={"changed": list(fields.keys())},
            )
        except Exception:
            pass
        return jsonify(out)
    except Exception as e:
        log.error("update_notification_prefs failed: %s", e)
        return jsonify({"error": "save_failed", "message": str(e)}), 500


# ---------------------------------------------------------------------------
# Cron-tick endpoints — called by Render Cron jobs over HTTP
# ---------------------------------------------------------------------------
# Three endpoints:
#   /api/cron/realtime-tick (15-min) — match_expiring scan
#   /api/cron/hourly-tick           — drain quiet-hours bundle, weekly_digest
#                                      (Tue 9am local), pending_review (Wed)
#   /api/cron/daily-tick            — winback_matches, winback_dormant,
#                                      finish_ranking, season_start
#
# Auth: each call must include `X-Cron-Secret: <CRON_SECRET env value>`.
# Setting CRON_SECRET on Render disables anonymous calls. If unset (local
# dev), any X-Cron-Secret value is accepted so smoke tests don't need
# environment scaffolding.

_CRON_SECRET = os.environ.get("CRON_SECRET", "")
# "Production" = anything that isn't pointed at the bundled SQLite DB.
# Render sets DATABASE_URL=postgresql://… so this evaluates True there.
# Local dev (sqlite:///…) is the only path where missing CRON_SECRET
# is treated as an explicit "auth disabled" rather than a misconfig.
_IS_PROD_ENV = not (os.environ.get("DATABASE_URL", "")
                    .startswith("sqlite") or
                    os.environ.get("DATABASE_URL", "") == "")

if _IS_PROD_ENV and not _CRON_SECRET:
    log.warning("⚠️  CRON_SECRET is unset in a non-SQLite environment — "
                "/api/cron/* endpoints will reject ALL requests until set")


def _require_cron_auth() -> None:
    """Raises a flask abort if the X-Cron-Secret header doesn't match
    CRON_SECRET.

    Local dev (sqlite or no DATABASE_URL): missing CRON_SECRET disables
    the check so smoke tests don't need scaffolding.

    Production (any non-sqlite DATABASE_URL): missing CRON_SECRET fails
    closed — every request is rejected with 503. This prevents an
    accidentally-unset secret from leaving the cron endpoints world-
    callable on Render.
    """
    from flask import abort
    if _IS_PROD_ENV and not _CRON_SECRET:
        abort(503)
    if not _CRON_SECRET:
        return
    sent = request.headers.get("X-Cron-Secret", "")
    if not hmac.compare_digest(sent, _CRON_SECRET):
        abort(401)


def _summary_push(items: list[dict]) -> tuple[str, str]:
    """Build (title, body) for the bundled morning summary push.
    Adapts based on the count + mix of queued items:
      1 item → preserve original title/body
      multi-of-one-kind → "You have N new trade matches"
      mixed → "N new matches and M updates while you slept"
    """
    if len(items) == 1:
        it = items[0]
        return (it.get("title") or "Notification",
                it.get("body")  or "Tap to view.")
    by_kind: dict[str, int] = {}
    for it in items:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    matches = by_kind.get("new_match", 0)
    if len(by_kind) == 1 and matches:
        return ("🌅 Good morning",
                f"You have {matches} new trade matches waiting.")
    other = sum(c for k, c in by_kind.items() if k != "new_match")
    if matches and other:
        return ("🌅 Good morning",
                f"{matches} new matches and {other} updates while you slept.")
    return ("🌅 Good morning",
            f"{sum(by_kind.values())} updates while you slept.")


@app.route("/api/cron/realtime-tick", methods=["POST"])
def cron_realtime_tick():
    """Every 15 minutes. Pushes match_expiring for pending matches >48h
    old that the recipient hasn't decided. Dedup gate (`match_expiring`
    in _NOTIF_DEDUP_CAPS) ensures one push per match per user.
    """
    _require_cron_auth()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    rows = load_pending_matches_older_than(cutoff)
    sent = 0
    for r in rows:
        for uid, dec in [
            (r["user_a_id"], r.get("user_a_decision")),
            (r["user_b_id"], r.get("user_b_decision")),
        ]:
            if dec is not None:
                continue   # already decided their side
            _send_typed_push(
                uid,
                "match_expiring",
                title = "⏳ A trade match is expiring soon",
                body  = "Tap to review before it disappears.",
                data  = {"match_id":  r["id"], "league_id": r.get("league_id")},
                dedup_key = str(r["id"]),
            )
            sent += 1
    log.info("realtime-tick: scanned %d pending; pushed %d", len(rows), sent)
    return jsonify({"ok": True, "scanned": len(rows), "pushed": sent})


@app.route("/api/cron/hourly-tick", methods=["POST"])
def cron_hourly_tick():
    """Every hour. Drains the quiet-hours queue (8am bundle delivery) +
    fires Tue/Wed 9am-local digest pushes for any user whose local time
    falls in this window.
    """
    _require_cron_auth()
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── 1. Drain the quiet-hours queue and bundle per-user ──
    drained = drain_due_queued_notifications(now_iso)
    bundled_users = 0
    for uid, items in drained.items():
        if not items:
            continue
        targets = load_device_tokens_for_users([uid])
        if not targets:
            continue
        title, body = _summary_push(items)
        msgs = [{
            "to":    t["device_token"],
            "title": title,
            "body":  body,
            "data":  {"type": "bundle_summary",
                      "kinds": [it["kind"] for it in items],
                      "count": len(items)},
            "sound": "default",
        } for t in targets]
        _send_expo_push(msgs)
        # Log every kind covered by the bundle so frequency caps stay
        # accurate. We pass the original dedup_key (threaded through the
        # queue row) so per-dedup_key caps for kinds in _NOTIF_DEDUP_CAPS
        # — match_expiring, first_match, match_accepted, league_member_*
        # — keep working when their pushes were deferred to this morning.
        for it in items:
            log_notification_send(
                uid, it["kind"], dedup_key=it.get("dedup_key"),
            )
        bundled_users += 1

    # ── 2. Tuesday 9am weekly_digest, Wednesday 9am pending_review ──
    digest_sent = 0
    review_sent = 0
    try:
        from zoneinfo import ZoneInfo
    except Exception:
        ZoneInfo = None  # type: ignore
    if ZoneInfo is None:
        log.warning("hourly-tick: zoneinfo unavailable, skipping digest scan")
        return jsonify({"ok": True, "bundled_users": bundled_users,
                        "digest_sent": 0, "review_sent": 0})

    week_window = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
    for u in load_all_signed_up_users():
        prefs = get_notification_prefs(u["sleeper_user_id"])
        if not int(prefs.get("weekly_digest", 1)):
            continue
        try:
            tz = ZoneInfo(prefs.get("tz") or "America/New_York")
        except Exception:
            continue
        local = datetime.now(tz)
        # Tuesday=1, Wednesday=2 (Python weekday())
        if local.weekday() == 1 and local.hour == 9:
            if count_notification_sends_since(
                u["sleeper_user_id"], "weekly_digest", week_window) == 0:
                _send_typed_push(
                    u["sleeper_user_id"],
                    "weekly_digest",
                    title = "📰 Your weekly trade roundup",
                    body  = "Tap to see what's new in your leagues.",
                    data  = {"week": local.strftime("%Y-W%U")},
                )
                digest_sent += 1
        elif local.weekday() == 2 and local.hour == 9:
            unread = load_unread_match_count(u["sleeper_user_id"])
            if unread <= 0:
                continue
            if count_notification_sends_since(
                u["sleeper_user_id"], "pending_review", week_window) == 0:
                _send_typed_push(
                    u["sleeper_user_id"],
                    "pending_review",
                    title = "👀 You have unreviewed matches",
                    body  = f"You have {unread} match{'es' if unread != 1 else ''} waiting.",
                    data  = {"unread_count": unread},
                )
                review_sent += 1

    log.info("hourly-tick: bundled=%d digest=%d review=%d",
             bundled_users, digest_sent, review_sent)
    return jsonify({"ok": True, "bundled_users": bundled_users,
                    "digest_sent": digest_sent, "review_sent": review_sent})


@app.route("/api/cron/daily-tick", methods=["POST"])
def cron_daily_tick():
    """Once per day. Re-engagement pushes — winback variants, finish_ranking,
    and season_start. Frequency caps in `_NOTIF_FREQ_CAPS` enforce per-window
    limits (winback_matches: 1/7d, winback_dormant: 1/30d, finish_ranking:
    1/30d, season_start: 1/365d). The cap check happens inside
    _send_typed_push, so the loop here is the broad scan.
    """
    _require_cron_auth()
    now = datetime.now(timezone.utc)
    cutoff_7d  = (now - timedelta(days=7)).isoformat()
    cutoff_30d = (now - timedelta(days=30)).isoformat()
    cutoff_3d  = (now - timedelta(days=3)).isoformat()

    counters: dict[str, int] = {
        "winback_matches": 0, "winback_dormant": 0,
        "finish_ranking":  0, "season_start":    0,
    }
    is_aug25 = (now.month == 8 and now.day == 25)

    for u in load_all_signed_up_users():
        uid = u["sleeper_user_id"]
        last_active = u.get("last_active_at")
        signup_at   = u.get("signup_at")
        unlocked    = u.get("unlocked_formats") or []

        # ── season_start: Aug 25 fan-out, all signed-up users ──
        if is_aug25:
            _send_typed_push(
                uid, "season_start",
                title = "🏈 Football is back",
                body  = "Re-rank your players to find this year's trades.",
                data  = {"season": now.year},
            )
            counters["season_start"] += 1
            continue   # don't double-stack a winback on top of season kickoff

        # ── finish_ranking: signed up >3d ago, no format unlocked ──
        if signup_at and signup_at < cutoff_3d and not unlocked:
            _send_typed_push(
                uid, "finish_ranking",
                title = "🎯 You're 5 minutes away from your first trade",
                body  = "Finish ranking your players to unlock matches.",
                data  = {},
            )
            counters["finish_ranking"] += 1
            continue

        # ── winback_dormant: 30d inactive ──
        if last_active and last_active < cutoff_30d:
            _send_typed_push(
                uid, "winback_dormant",
                title = "👋 Your league misses you",
                body  = "New trade matches are waiting when you're ready.",
                data  = {},
            )
            counters["winback_dormant"] += 1
            continue

        # ── winback_matches: 7d inactive AND ≥1 unread match ──
        if last_active and last_active < cutoff_7d:
            unread = load_unread_match_count(uid)
            if unread > 0:
                _send_typed_push(
                    uid, "winback_matches",
                    title = "🔥 Trade matches are waiting",
                    body  = f"You have {unread} unreviewed match{'es' if unread != 1 else ''}.",
                    data  = {"unread_count": unread},
                )
                counters["winback_matches"] += 1

    log.info("daily-tick: %s", counters)
    return jsonify({"ok": True, **counters})


@app.route("/api/cron/value-snapshot", methods=["POST"])
def cron_value_snapshot():
    """Once per day. Persist the CONSENSUS value of every universal-pool
    player, per scoring format, into player_value_history (backlog #57 / #17).

    Deliberately a DEDICATED endpoint, not folded into daily-tick: this is
    data retention, and a bug in daily-tick's push-notification scan must not
    be able to silently stop history collection (every un-logged day is chart
    history lost forever — the universal pool is rebuilt from the live DP CSV
    on each boot, so yesterday's numbers are otherwise unrecoverable).

    Idempotent: re-running on the same UTC day upserts rather than
    duplicating (uq_value_snapshot). Auth: X-Cron-Secret, same as /api/cron/*.
    """
    _require_cron_auth()
    from .trade_service import elo_to_value
    _ensure_universal_pools()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    counters: dict[str, int] = {}
    for fmt in SCORING_FORMATS:
        pool = g_universal_by_format.get(fmt) or {}
        seed: dict[str, float] = pool.get("seed") or {}
        players_by_id = {p.id: p for p in pool.get("players", [])}
        rows = []
        for pid, elo in seed.items():
            p = players_by_id.get(pid)
            rows.append({
                "player_id":       str(pid),
                "scoring_format":  fmt,
                "consensus_elo":   float(elo),
                "consensus_value": round(elo_to_value(float(elo)), 1),
                "search_rank":     getattr(p, "search_rank", None) if p else None,
                "adp":             getattr(p, "adp", None) if p else None,
                "snapshot_date":   today,
            })
        counters[fmt] = record_value_snapshots(rows)

    log.info("value-snapshot: %s (%s)", counters, today)
    return jsonify({"ok": True, "snapshot_date": today, **counters})


# ---------------------------------------------------------------------------
# Trends tab routes (Agent 2)
# ---------------------------------------------------------------------------

def _players_by_id_for(session_players) -> dict[str, dict]:
    """Build a {player_id: {name, position, team}} lookup from a list of
    RankingService Player dataclasses.  Used to enrich Trends responses."""
    out: dict[str, dict] = {}
    for p in (session_players or []):
        try:
            out[p.id] = {
                "name":     p.name,
                "position": p.position,
                "team":     getattr(p, "team", None),
            }
        except Exception:
            continue
    return out


@app.route("/api/trends/risers-fallers")
@_gate_unverified_read
def trends_risers_fallers_route():
    """
    GET /api/trends/risers-fallers?window_days=30&top_n=5
    Returns the user's ELO risers + fallers over the requested window,
    grouped by position.  Computed from the `elo_history` table written on
    every ranking submit.
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    service       = sess["service"]
    g_user_id     = sess["user_id"]
    g_league      = sess["league"]
    g_players     = sess["players"]
    fmt           = _active_format(sess)

    try:
        window_days = int(request.args.get("window_days", 30))
    except ValueError:
        window_days = 30
    try:
        top_n       = int(request.args.get("top_n", 5))
    except ValueError:
        top_n       = 5

    current = {rp.player.id: rp.elo for rp in service.get_rankings(position=None).rankings}
    try:
        history = load_elo_history(
            user_id        = g_user_id,
            scoring_format = fmt,
            since_days     = window_days,
            league_id      = g_league.league_id if g_league else None,
        )
    except Exception as e:
        log.warning("load_elo_history failed: %s", e)
        history = []

    players_by_id = _players_by_id_for(g_players)
    result = _trends_service_mod.compute_risers_fallers(
        current_elo   = current,
        history_rows  = history,
        players_by_id = players_by_id,
        top_n         = top_n,
        window_days   = window_days,
    )
    result["has_history"] = bool(history)
    return jsonify(result)


@app.route("/api/trends/contrarian")
@_gate_unverified_read
def trends_contrarian_route():
    """
    GET /api/trends/contrarian?league_id=...
    Compares the user's ELO to the community consensus in the league for
    the active scoring format.  Returns a single 0-100 contrarian score
    plus Top-5-above / Top-5-below splits.  Falls back to
    {has_baseline: false} when fewer than 3 other users have rankings.
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    service       = sess["service"]
    g_user_id     = sess["user_id"]
    g_league      = sess["league"]
    g_players     = sess["players"]
    fmt           = _active_format(sess)
    league_id     = request.args.get("league_id") or (g_league.league_id if g_league else None)

    if not league_id or league_id == "league_demo":
        return jsonify({
            "has_baseline":        False,
            "baseline_user_count": 0,
            "score":               None,
            "compared_players":    0,
            "above_consensus":     [],
            "below_consensus":     [],
            "reason":              "no_league",
        })

    user_elo = {rp.player.id: rp.elo for rp in service.get_rankings(position=None).rankings}
    try:
        community = load_community_elo_for_league(
            league_id       = league_id,
            exclude_user_id = g_user_id,
            scoring_format  = fmt,
        )
    except Exception as e:
        log.warning("load_community_elo_for_league failed: %s", e)
        community = {}

    players_by_id = _players_by_id_for(g_players)
    result = _trends_service_mod.compute_contrarian_score(
        user_elo           = user_elo,
        community_rankings = community,
        players_by_id      = players_by_id,
    )
    return jsonify(result)


@app.route("/api/trends/consensus-gap")
@_gate_unverified_read
def trends_consensus_gap_route():
    """
    GET /api/trends/consensus-gap?league_id=...&top_n=5
    Per-player gap between the user's ELO and the community ELO (for
    non-roster picks: vs the specific owner's ELO).  Returns
    "easiest_sells" (own roster, over-valued vs market) and
    "easiest_buys" (not on roster, over-valued vs owner).
    """
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    service       = sess["service"]
    g_user_id     = sess["user_id"]
    g_league      = sess["league"]
    g_user_roster = sess.get("user_roster") or []
    g_players     = sess["players"]
    fmt           = _active_format(sess)
    league_id     = request.args.get("league_id") or (g_league.league_id if g_league else None)
    try:
        top_n = int(request.args.get("top_n", 5))
    except ValueError:
        top_n = 5

    if not league_id or league_id == "league_demo":
        return jsonify({
            "has_baseline":        False,
            "baseline_user_count": 0,
            "easiest_sells":       [],
            "easiest_buys":        [],
            "reason":              "no_league",
        })

    user_elo = {rp.player.id: rp.elo for rp in service.get_rankings(position=None).rankings}
    try:
        community = load_community_elo_for_league(
            league_id       = league_id,
            exclude_user_id = g_user_id,
            scoring_format  = fmt,
        )
    except Exception as e:
        log.warning("load_community_elo_for_league failed: %s", e)
        community = {}

    # League-members shape expected by trends_service: list of dicts with
    # user_id, username, roster.
    members = []
    if g_league:
        for m in g_league.members:
            members.append({
                "user_id":  m.user_id,
                "username": m.username,
                "roster":   list(getattr(m, "roster", []) or []),
            })

    players_by_id = _players_by_id_for(g_players)
    result = _trends_service_mod.compute_consensus_gap(
        user_elo           = user_elo,
        community_rankings = community,
        user_roster        = g_user_roster,
        league_members     = members,
        players_by_id      = players_by_id,
        top_n              = top_n,
    )
    return jsonify(result)


# ---------------------------------------------------------------------------
# Agent 1 additions — Skip / Dismiss persistent routes
# ---------------------------------------------------------------------------
# /api/trio/skip      — user says "I don't know this player" on the Trios page
# /api/tiers/dismiss  — user taps × on an unassigned card on the Tiers page
#
# Both routes:
#   • Scope the skip to (user_id, scoring_format) — not league.
#   • Accept a single player_id OR a list via `player_ids` for bulk calls.
#   • Do NOT write a swipe / do NOT update ELO.  Skipped players simply
#     vanish from future trios and the unassigned pool.
# ---------------------------------------------------------------------------

@app.route("/api/trio/skip", methods=["POST"])
def post_trio_skip():
    """POST /api/trio/skip
    Body: { player_id: str }  OR  { player_ids: [str, ...] }
    Optional: { scoring_format: '1qb_ppr' | 'sf_tep' } — defaults to active.
    Response: { ok: true, skipped: [ids], skipped_count: int }
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    user_id = sess.get("user_id", "")
    if not user_id:
        return jsonify({"error": "no_user_in_session"}), 400

    body = request.get_json(force=True) or {}
    fmt = body.get("scoring_format") or _active_format(sess)
    if fmt not in SCORING_FORMATS:
        fmt = _active_format(sess)

    ids: list = []
    if "player_ids" in body and isinstance(body["player_ids"], list):
        ids = [str(x) for x in body["player_ids"] if x]
    elif "player_id" in body and body["player_id"]:
        ids = [str(body["player_id"])]

    if not ids:
        return jsonify({"error": "player_id or player_ids required"}), 400

    for pid in ids:
        try:
            _skip_add(user_id=user_id, player_id=pid, scoring_format=fmt)
        except Exception as e:
            log.warning("skip add failed for pid=%s: %s", pid, e)

    return jsonify({
        "ok":             True,
        "skipped":        ids,
        "skipped_count":  len(ids),
        "scoring_format": fmt,
    })


@app.route("/api/tiers/dismiss", methods=["POST"])
@_gate_unverified_write
def post_tiers_dismiss():
    """POST /api/tiers/dismiss
    Body: { player_id: str }  OR  { player_ids: [str, ...] }
    Optional: { scoring_format: '1qb_ppr' | 'sf_tep' }
    Response: { ok: true, dismissed: [ids], dismissed_count: int }

    Shares the user_player_skips table with /api/trio/skip — a dismiss on the
    tiers page also hides the player from the Trios flow, and vice versa.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    user_id = sess.get("user_id", "")
    if not user_id:
        return jsonify({"error": "no_user_in_session"}), 400

    body = request.get_json(force=True) or {}
    fmt = body.get("scoring_format") or _active_format(sess)
    if fmt not in SCORING_FORMATS:
        fmt = _active_format(sess)

    ids: list = []
    if "player_ids" in body and isinstance(body["player_ids"], list):
        ids = [str(x) for x in body["player_ids"] if x]
    elif "player_id" in body and body["player_id"]:
        ids = [str(body["player_id"])]

    if not ids:
        return jsonify({"error": "player_id or player_ids required"}), 400

    for pid in ids:
        try:
            _skip_add(user_id=user_id, player_id=pid, scoring_format=fmt)
        except Exception as e:
            log.warning("dismiss add failed for pid=%s: %s", pid, e)

    return jsonify({
        "ok":               True,
        "dismissed":        ids,
        "dismissed_count":  len(ids),
        "scoring_format":   fmt,
    })


@app.route("/api/skips")
def get_skips():
    """GET /api/skips  →  { skipped_ids: [pid, ...], scoring_format: '...' }

    Returns the user's current persistent skips for the active format — the
    frontend uses this to hide already-dismissed unassigned cards on the
    Tiers page without round-tripping each card through /api/players.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    user_id = sess.get("user_id", "")
    fmt = _active_format(sess)
    try:
        ids = _skip_load(user_id=user_id, scoring_format=fmt)
    except Exception as e:
        log.warning("load_skips endpoint failed: %s", e)
        ids = set()
    return jsonify({
        "skipped_ids":    sorted(ids),
        "scoring_format": fmt,
    })


# ---------------------------------------------------------------------------
# OG Share Cards (server-side rendered PNG + HTML wrappers)
#
# These routes are public (no session required) because social crawlers
# like Twitter/Facebook/iMessage fetch them without cookies.
# ---------------------------------------------------------------------------

from flask import Response, make_response  # noqa: E402

try:
    from . import og_image as _og_image
    _OG_IMPORT_ERROR: Exception | None = None
except Exception as _og_err:  # pragma: no cover
    _og_image = None  # type: ignore[assignment]
    _OG_IMPORT_ERROR = _og_err
    log.error("og_image import failed: %s — /og and /s routes will 503", _og_err)


def _og_unavailable_response() -> "Response":
    """503 fallback when Pillow isn't installed."""
    body = (
        "OG share cards require Pillow. Install with: pip install Pillow>=10.0\n"
        f"Error: {_OG_IMPORT_ERROR}"
    )
    return Response(body, status=503, mimetype="text/plain")


def _png_response(data: bytes, status: int = 200) -> "Response":
    resp = make_response(data, status)
    resp.headers["Content-Type"]  = "image/png"
    resp.headers["Cache-Control"] = "public, max-age=300"
    resp.headers["Content-Length"] = str(len(data))
    return resp


@app.route("/og/tiers/<pos>/<username>.png")
def og_tier_card(pos, username):
    """Render a user's tier snapshot for a position as a 1200x630 PNG."""
    if _og_image is None:
        return _og_unavailable_response()
    # Attempt to detect the user's active format for nicer subtitle. Since
    # share URLs are public, we can't consult the session — default to 1QB PPR
    # unless a ?fmt= query overrides it.
    fmt = request.args.get("fmt", "1qb_ppr")
    if fmt not in SCORING_FORMATS:
        fmt = DEFAULT_SCORING
    try:
        png, status = _og_image.render_tier_card(username, pos, fmt)
    except Exception as e:
        log.error("og_tier_card error (%s/%s): %s", pos, username, e)
        png = _og_image.render_placeholder_card("Share card unavailable", str(e)[:80])
        status = 500
    return _png_response(png, status=status)


@app.route("/og/trade/<match_id>.png")
def og_trade_card(match_id):
    """Render a trade match's give/get + fairness as a 1200x630 PNG."""
    if _og_image is None:
        return _og_unavailable_response()
    try:
        png, status = _og_image.render_trade_card(match_id)
    except Exception as e:
        log.error("og_trade_card error (%s): %s", match_id, e)
        png = _og_image.render_placeholder_card("Share card unavailable", str(e)[:80])
        status = 500
    return _png_response(png, status=status)


def _share_html(
    *,
    title: str,
    description: str,
    image_url: str,
    cta_text: str,
    cta_url: str,
) -> "Response":
    """Minimal HTML wrapper with OG tags + small human-readable body."""
    # Escape minimal HTML special chars — we never render user-controlled
    # HTML inside any attribute, so basic replacement is sufficient.
    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;") \
                         .replace(">", "&gt;").replace('"', "&quot;")

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{esc(title)} · Fantasy Trade Finder</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="{esc(description)}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:image" content="{esc(image_url)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{esc(title)}">
  <meta name="twitter:description" content="{esc(description)}">
  <meta name="twitter:image" content="{esc(image_url)}">
  <style>
    body{{margin:0;background:#0f1322;color:#f5f7fc;font-family:-apple-system,Segoe UI,Roboto,sans-serif;
         min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;}}
    .card{{max-width:720px;width:100%;text-align:center;}}
    .card img{{width:100%;max-width:720px;height:auto;border-radius:16px;
               box-shadow:0 10px 40px rgba(0,0,0,.4);}}
    h1{{font-size:28px;margin:24px 0 8px;}}
    p{{color:#a0aec8;margin:0 0 24px;}}
    .cta{{display:inline-block;background:#6eb4ff;color:#0f1322;padding:14px 28px;
          border-radius:999px;font-weight:600;text-decoration:none;}}
    .cta:hover{{background:#8cc6ff;}}
    .brand{{margin-top:36px;color:#6b7a9a;font-size:13px;}}
  </style>
</head>
<body>
  <div class="card">
    <img src="{esc(image_url)}" alt="{esc(title)}">
    <h1>{esc(title)}</h1>
    <p>{esc(description)}</p>
    <a class="cta" href="{esc(cta_url)}">{esc(cta_text)}</a>
    <div class="brand">Fantasy Trade Finder</div>
  </div>
</body>
</html>"""
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@app.route("/s/tiers/<pos>/<username>")
def share_tiers_page(pos, username):
    """HTML wrapper with OG tags for a tier snapshot share link."""
    fmt = request.args.get("fmt", "1qb_ppr")
    if fmt not in SCORING_FORMATS:
        fmt = DEFAULT_SCORING
    pos_u = (pos or "").upper()
    title = f"{username}'s {pos_u} Tiers"
    fmt_label = "1QB PPR" if fmt == "1qb_ppr" else "SF TEP"
    description = f"See how @{username} tiers their {pos_u}s in {fmt_label} dynasty."
    image_url = f"/og/tiers/{pos}/{username}.png"
    if fmt != "1qb_ppr":
        image_url += f"?fmt={fmt}"
    return _share_html(
        title=title,
        description=description,
        image_url=image_url,
        cta_text="Build your tiers",
        cta_url="/",
    )


@app.route("/s/trade/<match_id>")
def share_trade_page(match_id):
    """HTML wrapper with OG tags for a trade verdict share link."""
    title = "Trade Match"
    description = "A dynasty fantasy trade — see the give/get breakdown and fairness verdict."
    image_url = f"/og/trade/{match_id}.png"
    return _share_html(
        title=title,
        description=description,
        image_url=image_url,
        cta_text="Find your next trade",
        cta_url="/",
    )


# ---------------------------------------------------------------------------
# Browser extension — /api/extension/auth + /api/extension/rankings
# ---------------------------------------------------------------------------
# The Chrome/Edge extension injects the user's personal tier + pos-rank next
# to player names on sleeper.com. It needs a lean auth that takes a Sleeper
# username (same UX as the main app) and a compact rankings payload. We do
# NOT reuse /api/session/init because (a) the extension can't drive the
# full frontend Sleeper-fetch flow, and (b) we don't need the trade service
# or opponent-member hydration for read-only badge injection.

def _extension_build_session(user_id: str, username: str,
                             display_name: str, avatar: str | None) -> tuple[str, dict]:
    """Build a user-scoped session for the browser extension.

    No league locked in — the scoring format is resolved per-request from
    the league_id query param on /api/extension/rankings. Builds one
    RankingService per scoring_format with swipes + tier overrides
    replayed, so switching leagues on sleeper.com just picks the right
    service instantly.

    Returns (token, session_payload).
    """
    # Ensure the Sleeper player cache is populated — on a cold Render
    # instance the extension could be the first caller.
    if _load_sleeper_cache() is None:
        try:
            _ensure_sleeper_cache_populated()
        except Exception as e:
            raise RuntimeError(
                f"Could not populate Sleeper player cache: {e}. "
                "Try again in a moment."
            )
    _ensure_universal_pools()

    # Persist user (no invited_by — extension isn't a referral surface)
    try:
        upsert_user(
            sleeper_user_id=user_id,
            username=username,
            display_name=display_name,
            avatar=avatar,
        )
    except Exception as e:
        log.warning("  extension auth: upsert_user failed: %s", e)

    # Build RankingServices per format with replayed swipes + tier overrides
    new_services: dict = {}
    for fmt in SCORING_FORMATS:
        fmt_pool, fmt_seed = _get_universal_pool(fmt)
        svc = RankingService(
            players           = fmt_pool,
            matchup_generator = matchup_gen,
            seed_ratings      = fmt_seed,
        )
        svc._user_id = user_id
        svc._scoring_format = fmt
        try:
            historical = load_swipe_decisions(user_id=user_id, scoring_format=fmt)
            if historical:
                svc.replay_from_db(historical)
        except Exception as e:
            log.warning("  [%s] extension replay failed: %s", fmt, e)
        try:
            # See server.py:4022 for why we no longer filter overrides
            # through the current pool — the filter destroys data.
            overrides = load_tier_overrides(user_id=user_id, scoring_format=fmt)
            svc._elo_overrides = {pid: float(elo) for pid, elo in overrides.items()}
        except Exception as e:
            log.warning("  [%s] extension override restore failed: %s", fmt, e)
        new_services[fmt] = svc

    payload = {
        "user_id":       user_id,
        "username":      username,
        "display_name":  display_name,
        # User-scoped: no 'league_id' or locked 'active_format' — resolved
        # per-request based on the ?league_id= query param on /rankings.
        "services":      new_services,
        # Default service alias (main-app code paths that read sess['service']
        # expect one). The rankings endpoint overrides this per-request.
        "service":       new_services[DEFAULT_SCORING],
        "active_format": DEFAULT_SCORING,
        "extension":     True,
        "last_active":   time.time(),
    }
    token = secrets.token_urlsafe(32)
    with _sessions_lock:
        _sessions[token] = payload
    return token, payload


@app.route("/api/extension/auth", methods=["POST"])
def extension_auth():
    """
    One-shot username auth for the browser extension.

    Body: {"username": "<sleeper_username>"}
    Returns: {session_token, expires_at, user_id, username, display_name,
              avatar, leagues: [...]}

    The returned `leagues` list is informational — the popup can display
    the user's league count, but the extension does NOT need to choose
    one up front. The content script detects league_id from
    sleeper.com/leagues/<id>/... URLs and passes it to /api/extension/rankings.
    """
    body     = request.get_json(force=True) or {}
    username = (body.get("username") or "").strip().lower()

    if not username:
        return jsonify({"error": "missing_username", "message": "Sleeper username required."}), 400

    # Resolve Sleeper username → user_id
    try:
        user_data = _sleeper_get(
            f"https://api.sleeper.app/v1/user/{urllib.parse.quote(username)}"
        )
    except Exception as e:
        return jsonify({"error": "sleeper_error", "message": str(e)}), 502
    if not isinstance(user_data, dict) or not user_data.get("user_id"):
        return jsonify({"error": "user_not_found",
                        "message": f"Sleeper user @{username} not found."}), 404

    user_id      = user_data["user_id"]
    display_name = user_data.get("display_name") or username
    avatar       = user_data.get("avatar")

    # Best-effort league list for popup display (non-blocking)
    leagues_compact: list = []
    try:
        leagues = _sleeper_get(
            f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/2026"
        ) or []
        leagues_compact = [
            {
                "league_id":     str(lg.get("league_id")),
                "name":          lg.get("name") or "League",
                "total_rosters": lg.get("total_rosters"),
                "avatar":        lg.get("avatar"),
            }
            for lg in (leagues if isinstance(leagues, list) else [])
            if lg.get("league_id")
        ]
    except Exception as e:
        log.info("extension_auth: leagues fetch failed (non-fatal): %s", e)

    # Mint session immediately
    try:
        token, payload = _extension_build_session(
            user_id=user_id,
            username=username,
            display_name=display_name,
            avatar=avatar,
        )
    except Exception as e:
        log.exception("extension_auth: session build failed")
        return jsonify({"error": "session_build_failed", "message": str(e)}), 500

    expires_at = int(payload["last_active"]) + 4 * 3600
    return jsonify({
        "stage":         "connected",
        "session_token": token,
        "expires_at":    expires_at,
        "user_id":       user_id,
        "username":      username,
        "display_name":  display_name,
        "avatar":        avatar,
        "leagues":       leagues_compact,
    })


@app.route("/api/extension/rankings")
@_gate_unverified_read
def extension_rankings():
    """Return a compact tier + pos_rank map for the authenticated user.

    Query param: league_id (optional but recommended) — if provided, the
    backend looks up that league's scoring format (auto-detecting from
    Sleeper metadata on first sync) and returns rankings for that format.
    If omitted, falls back to the session's default format (1qb_ppr).

    Only players with a non-default ELO tier are included — unranked
    players don't get a badge.

    Shape:
      { format, league_id, league_name, username, updated_at,
        players: {pid: {name, pos, pos_rank, tier}} }
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    req_league_id = (request.args.get("league_id") or "").strip() or None

    # Resolve scoring format:
    #   1. If league_id provided: look up leagues.default_scoring
    #   2. If not on file: fetch Sleeper meta and cache it
    #   3. Fall back to session default (1qb_ppr)
    fmt = None
    league_name = ""
    if req_league_id:
        try:
            fmt = get_league_scoring(req_league_id)
        except Exception:
            fmt = None
        if fmt not in SCORING_FORMATS:
            meta = _fetch_sleeper_league_meta(req_league_id)
            if meta:
                league_name = meta.get("name") or ""
                detected = _detect_scoring_format_from_meta(meta)
                try:
                    set_league_scoring(req_league_id, detected)
                except Exception:
                    pass
                fmt = detected
    if fmt not in SCORING_FORMATS:
        fmt = sess.get("active_format") or DEFAULT_SCORING

    service = sess["services"][fmt] if sess.get("services") else sess["service"]

    # Build per-position rankings
    players_map: dict[str, dict] = {}
    for pos in ("QB", "RB", "WR", "TE"):
        try:
            rankset = service.get_rankings(position=pos)
        except Exception as e:
            log.warning("extension_rankings: get_rankings(%s) failed: %s", pos, e)
            continue
        for i, rp in enumerate(rankset.rankings, start=1):
            elo = getattr(rp, "elo", None)
            tier = RankingService.tier_for_elo(elo, pos, fmt) if elo is not None else None
            if tier is None:
                continue
            pid = rp.player.id
            players_map[pid] = {
                "name":     rp.player.name,
                "pos":      pos,
                "pos_rank": i,
                "tier":     tier,
            }

    return jsonify({
        "format":       fmt,
        "league_id":    req_league_id or "",
        "league_name":  league_name,
        "username":     sess.get("username") or "",
        "updated_at":   int(time.time()),
        "players":      players_map,
    })


# ---------------------------------------------------------------------------
# Invite K-factor dashboard (Agent 5) — feature-flagged
# ---------------------------------------------------------------------------

# Milestone thresholds for the "Your invite impact" section of the invite
# modal. Kept here (not in a config file) because the frontend also needs
# to know the exact list to render a progress bar; single source of truth
# lives in the /api/invite/impact response.
_INVITE_MILESTONES: tuple[tuple[int, str], ...] = (
    (1,  "🌱 First Recruit"),
    (3,  "🤝 League Builder"),
    (5,  "🔥 Five-Spot"),
    (10, "👑 Ambassador"),
)


def _compute_invite_impact(username: str, user_id: str) -> dict:
    """Build the K-factor dashboard payload for the given user.

    Returns the shape consumed by GET /api/invite/impact — see that route's
    docstring for the contract.
    """
    # count_referrals accepts either a username or user_id; prefer username
    # because invited_by is stored by-username on the referred users' rows.
    key = username or user_id or ""
    total_joined = count_referrals(key)

    # Richer activity — "actively ranking" = has ≥1 swipe. We keep the
    # query cheap by only running it when the dashboard flag is on (i.e.
    # inside this helper, which only fires from the flagged route).
    activity = list_referral_activity(key) if key else []
    active_rankers = sum(1 for r in activity if r.get("has_swiped"))

    # v1 definition: invited == joined because every referred row exists
    # only after that user's session_init. We still return both fields so
    # the frontend copy can evolve without a backend change.
    invited = total_joined
    joined = total_joined

    # Next milestone = smallest threshold strictly greater than joined.
    # Once past the last threshold there is no "next" — return null so the
    # UI can hide the progress bar.
    next_milestone: dict | None = None
    for threshold, label in _INVITE_MILESTONES:
        if joined < threshold:
            next_milestone = {"badge": label, "at": threshold}
            break

    badges_earned = [label for threshold, label in _INVITE_MILESTONES
                     if joined >= threshold]

    return {
        "invited":        invited,
        "joined":         joined,
        "active_rankers": active_rankers,
        "k_factor":       float(joined),   # v1 fan-out per user
        "next_milestone": next_milestone,
        "badges_earned":  badges_earned,
        "milestones":     [{"at": t, "badge": b} for t, b in _INVITE_MILESTONES],
    }


@app.route("/api/invite/impact")
def invite_impact_route():
    """GET /api/invite/impact — returns the inviter's K-factor snapshot.

    Gated by the `invite.k_factor_dashboard` flag. When the flag is off we
    still respond 200 with a zeroed payload so the frontend can fail quiet
    without a console error, matching the other flagged endpoints.
    """
    sess = _require_session()
    sess["last_active"] = time.time()

    if not is_enabled("invite.k_factor_dashboard"):
        return jsonify({
            "enabled":        False,
            "invited":        0,
            "joined":         0,
            "active_rankers": 0,
            "k_factor":       0.0,
            "next_milestone": None,
            "badges_earned":  [],
            "milestones":     [{"at": t, "badge": b} for t, b in _INVITE_MILESTONES],
        })

    username = sess.get("username") or ""
    user_id  = sess.get("user_id")  or ""
    payload = _compute_invite_impact(username, user_id)
    payload["enabled"] = True
    return jsonify(payload)


# ---------------------------------------------------------------------------
# Feature flags — powers the sprint's on/off toggling via config/features.json
# ---------------------------------------------------------------------------

@app.route("/api/feature-flags")
def feature_flags_route():
    """Return the current effective feature-flag map.

    Shape: {"flags": {"swipe.community_compare": false, ...}}

    Frontend fetches this at boot and stashes it in window.FTF_FLAGS so
    UI code can do `if (window.FTF_FLAGS["swipe.community_compare"]) ...`.
    Backend code uses FLAGS.swipe_community_compare or is_enabled(key).
    """
    return jsonify({"flags": flags_dict()})


@app.route("/api/feature-flags/reload", methods=["POST"])
def feature_flags_reload_route():
    """Force-reload flags from config/features.json + FTF_FLAGS env.

    Useful when flipping a flag in prod without a full server restart.
    Operator-only (X-Cron-Secret, same as /api/cron/*) — flag state gates
    user-facing behavior, so reloads shouldn't be world-triggerable.
    """
    _require_cron_auth()
    flags = reload_flags()
    return jsonify({"ok": True, "flags": flags})


# ---------------------------------------------------------------------------
# League URL parsing — powers the "Connect another league" dropdown action
# ---------------------------------------------------------------------------

@app.route("/api/league/parse-url", methods=["POST"])
def parse_league_url():
    """Parse a pasted league URL into {platform, league_id, name, supported}.

    Body: {"url": "<league-url>"}
    Response shape:
      {
        "platform":   "sleeper" | "espn" | "mfl",
        "league_id":  "<id>",
        "name":       "<League name, if resolvable>" (optional),
        "supported":  true  if we can complete the sync flow today,
                      false for ESPN / MFL where full sync is still on the
                            roadmap (the frontend shows a "coming soon" state)
      }
    Errors: {"error": "<code>", "message": "<human-readable>"}
    """
    body = request.get_json(force=True) or {}
    url = (body.get("url") or "").strip()
    if not url:
        return jsonify({"error": "missing_url",
                        "message": "Paste a league URL to continue."}), 400

    platform, league_id = _parse_league_url(url)
    if not platform or not league_id:
        return jsonify({
            "error":   "unrecognized_url",
            "message": "Couldn't recognize that URL. Paste a link from "
                       "Sleeper, ESPN Fantasy, or MyFantasyLeague.",
        }), 400

    # For Sleeper, we can resolve the league name immediately so the
    # confirmation UI shows "Lakeview League" rather than a bare ID.
    name = None
    if platform == "sleeper":
        try:
            meta = _fetch_sleeper_league_meta(league_id)
            if meta:
                name = meta.get("name")
        except Exception as e:
            log.info("parse_league_url: Sleeper meta lookup failed (non-fatal): %s", e)

    return jsonify({
        "platform":  platform,
        "league_id": league_id,
        "name":      name,
        "supported": platform == "sleeper",
    })


# ---------------------------------------------------------------------------
# Agent A7 — new surfaces
# ---------------------------------------------------------------------------
# Three features, each flag-gated. When the flag is off, routes return 404
# (profile) or the feature simply isn't wired on the frontend.
#   • profiles.public_pages   — /u/<username> + /api/profile/<username>
#   • landing.smart_start_cta — frontend only (flag-gated)
#   • landing.try_before_sync — /api/session/demo builds a seeded demo session
# ---------------------------------------------------------------------------

_PROFILE_POSITIONS = ("QB", "RB", "WR", "TE")


def _build_profile_tiers_snapshot(
    user_id: str,
    scoring_format: str,
    player_positions: dict,
    player_name_map: dict,
) -> dict:
    """Bucket a user's saved tier overrides into {position: {tier: [names]}}.

    Reads from load_tier_overrides (what the user saved via the tiers UI)
    and buckets each player by their stored ELO using the canonical
    RankingService.tier_for_elo.
    """
    from .ranking_service import RankingService as _RS
    try:
        overrides = load_tier_overrides(user_id=user_id, scoring_format=scoring_format)
    except Exception as e:
        log.warning("profile tiers load failed: %s", e)
        overrides = {}

    snapshot: dict = {}
    for pid, elo in overrides.items():
        pos = (player_positions.get(str(pid)) or "").upper()
        if pos not in _PROFILE_POSITIONS:
            continue
        try:
            elo_f = float(elo)
        except (TypeError, ValueError):
            continue
        tier = _RS.tier_for_elo(elo_f, pos, scoring_format)
        if not tier:
            continue
        name = player_name_map.get(str(pid), str(pid))
        snapshot.setdefault(pos.lower(), {}).setdefault(tier, []).append({
            "player_id": str(pid),
            "name":      name,
            "elo":       round(elo_f, 1),
        })

    for pos_buckets in snapshot.values():
        for entries in pos_buckets.values():
            entries.sort(key=lambda e: -e["elo"])

    return snapshot


def _build_profile_contrarian(
    user_id: str,
    scoring_format: str,
    player_positions: dict,
    player_name_map: dict,
    top_n: int = 3,
) -> dict:
    """Compute the user's top-N above/below community picks per position.

    Aggregates community ELO across every league the user belongs to and
    diffs against the user's own stored ELOs. A player needs at least 2
    non-user raters to count. Returns {pos: {above: [...], below: [...]}}.
    """
    # Get all league IDs this user is a member of
    league_ids: list = []
    try:
        from .database import league_members_table, engine as _engine  # type: ignore
        from sqlalchemy import select as _select
        with _engine.connect() as _conn:
            rows = _conn.execute(
                _select(league_members_table.c.league_id).where(
                    league_members_table.c.user_id == user_id
                )
            ).fetchall()
            league_ids = sorted({r.league_id for r in rows})
    except Exception as e:
        log.warning("profile league_ids load failed: %s", e)

    user_by_pid: dict = {}
    community_by_pid: dict = {}
    try:
        for lid in league_ids:
            everyone = load_member_rankings(
                league_id=lid,
                exclude_user_id="",
                scoring_format=scoring_format,
            )
            for uid, urow in everyone.items():
                for pid, elo in (urow.get("elo_ratings") or {}).items():
                    try:
                        fe = float(elo)
                    except (TypeError, ValueError):
                        continue
                    if uid == user_id:
                        user_by_pid[str(pid)] = fe
                    else:
                        community_by_pid.setdefault(str(pid), []).append(fe)
    except Exception as e:
        log.warning("profile rankings aggregation failed: %s", e)

    out: dict = {pos.lower(): {"above": [], "below": []} for pos in _PROFILE_POSITIONS}
    if not user_by_pid:
        return out

    for pos in _PROFILE_POSITIONS:
        deltas: list = []
        pos_u = pos.upper()
        for pid, u_elo in user_by_pid.items():
            if (player_positions.get(pid) or "").upper() != pos_u:
                continue
            c_list = community_by_pid.get(pid) or []
            if len(c_list) < 2:
                continue
            c_mean = sum(c_list) / len(c_list)
            delta = u_elo - c_mean
            deltas.append({
                "player_id":      pid,
                "name":           player_name_map.get(pid, pid),
                "user_elo":       round(u_elo, 1),
                "community_elo":  round(c_mean, 1),
                "delta":          round(delta, 1),
                "raters":         len(c_list),
            })
        above = sorted(deltas, key=lambda d: -d["delta"])[:top_n]
        below = sorted(deltas, key=lambda d: d["delta"])[:top_n]
        out[pos.lower()] = {"above": above, "below": below}
    return out


@app.route("/u/<path:username>")
def public_profile_page(username):
    """Serve the public profile page when flag is on; 404 otherwise."""
    if not is_enabled("profiles.public_pages"):
        return jsonify({"error": "not_found"}), 404
    return send_from_directory(app.static_folder, "profile.html")


@app.route("/api/profile/<path:username>")
def public_profile_data(username):
    """Public profile JSON. Read-only; only data the user has created.

    404 when flag off or user not found. No private league info exposed.
    """
    if not is_enabled("profiles.public_pages"):
        return jsonify({"error": "not_found"}), 404

    uname = (username or "").strip().lower()
    if not uname:
        return jsonify({"error": "missing_username"}), 400

    try:
        user = get_user_by_username(uname)
    except Exception as e:
        log.warning("profile: user lookup failed: %s", e)
        user = None
    if not user:
        return jsonify({"error": "not_found"}), 404

    user_id = user.get("sleeper_user_id") or user.get("user_id")
    if not user_id:
        return jsonify({"error": "not_found"}), 404

    # Count distinct leagues
    leagues_count = 0
    try:
        from .database import league_members_table, engine as _engine  # type: ignore
        from sqlalchemy import select as _select, func as _func
        with _engine.connect() as _conn:
            row = _conn.execute(
                _select(_func.count(_func.distinct(league_members_table.c.league_id))).where(
                    league_members_table.c.user_id == user_id
                )
            ).fetchone()
            if row:
                leagues_count = int(row[0] or 0)
    except Exception as e:
        log.warning("profile leagues_count failed: %s", e)

    # Players lookup
    try:
        all_players = load_players(position=None)
    except Exception as e:
        log.warning("profile load_players failed: %s", e)
        all_players = []
    player_positions = {
        str(p.get("player_id")): (p.get("position") or "").upper()
        for p in all_players if p.get("player_id")
    }
    player_name_map = {
        str(p.get("player_id")): (p.get("full_name") or "—")
        for p in all_players if p.get("player_id")
    }

    # Pick the format with the larger tiers snapshot
    best_fmt = DEFAULT_SCORING
    best_tiers: dict = {}
    for fmt in SCORING_FORMATS:
        tiers_snap = _build_profile_tiers_snapshot(
            user_id, fmt, player_positions, player_name_map
        )
        cur = sum(len(v) for v in tiers_snap.values())
        best = sum(len(v) for v in best_tiers.values())
        if cur > best:
            best_tiers = tiers_snap
            best_fmt = fmt

    contrarian = _build_profile_contrarian(
        user_id, best_fmt, player_positions, player_name_map, top_n=3
    )

    avatar_url = None
    avatar = user.get("avatar")
    if avatar:
        avatar_url = f"https://sleepercdn.com/avatars/thumbs/{avatar}"

    return jsonify({
        "username":         user.get("username") or uname,
        "display_name":     user.get("display_name") or user.get("username") or uname,
        "avatar_url":       avatar_url,
        "leagues_count":    leagues_count,
        "scoring_format":   best_fmt,
        "contrarian_takes": contrarian,
        "tiers_snapshot":   best_tiers,
    })


@app.route("/api/session/demo", methods=["POST", "GET"])
def session_demo():
    """Bootstrap a seeded demo session — no Sleeper auth, nothing persists."""
    if not is_enabled("landing.try_before_sync"):
        return jsonify({"error": "not_found"}), 404

    try:
        demo_user_id = "demo_user_" + secrets.token_hex(4)

        from .database import SCORING_FORMATS as DB_SCORING_FORMATS
        new_services: dict = {}
        new_trade_svcs: dict = {}
        final_league = None
        for fmt in DB_SCORING_FORMATS:
            svc = RankingService(
                players=list(DEMO_PLAYERS),
                matchup_generator=matchup_gen,
                seed_ratings=seed,
            )
            svc._user_id = demo_user_id
            svc._scoring_format = fmt
            new_services[fmt] = svc

            tsvc = TradeService(players={p.id: p for p in DEMO_PLAYERS})
            dl, _dr = _build_demo_league(DEMO_PLAYERS, seed)
            tsvc.add_league(dl)
            new_trade_svcs[fmt] = tsvc
            final_league = dl

        active_format = DEFAULT_SCORING
        token = secrets.token_urlsafe(32)
        payload = {
            "user_id":       demo_user_id,
            "league":        final_league,
            "players":       list(DEMO_PLAYERS),
            "user_roster":   list(DEMO_USER_ROSTER),
            "services":      new_services,
            "service":       new_services[active_format],
            "trade_svcs":    new_trade_svcs,
            "trade_svc":     new_trade_svcs[active_format],
            "active_format": active_format,
            "display_name":  "Demo User",
            "last_active":   time.time(),
            "is_demo":       True,
        }
        with _sessions_lock:
            _sessions[token] = payload

        players_dict = {p.id: p for p in DEMO_PLAYERS}
        return jsonify({
            "ok":           True,
            "demo":         True,
            "token":        token,
            "user_id":      demo_user_id,
            "display_name": "Demo User",
            "league_id":    final_league.league_id,
            "league_name":  final_league.name,
            "player_count": len(DEMO_PLAYERS),
            "user_roster":  [player_to_dict(players_dict[pid]) for pid in DEMO_USER_ROSTER if pid in players_dict],
            "opponents":    len(final_league.members),
        })
    except Exception as e:
        log.error("session/demo failed: %s\n%s", e, traceback.format_exc())
        return jsonify({"error": "internal_error"}), 500


# ─── Account auth — Apple/Google identity anchors + in-app deletion ────────
# Account-auth plan P2 (docs/plans/account-auth-plan-2026-07-11.md §3-P2).
# Thin wrappers over backend/accounts.py. The sign-in surface is gated on
# the `auth.accounts` flag (ships dark); DELETE /api/account is deliberately
# ungated — App Store Guideline 5.1.1(v) requires in-app account deletion.

from . import accounts as _accounts


def _account_session() -> dict | None:
    """Best-effort session lookup for the auth routes — no 401 on miss.

    Demo sessions don't persist anything, so they never bind to an account.
    """
    token = request.headers.get("X-Session-Token", "")
    with _sessions_lock:
        sess = _sessions.get(token)
    if sess is None:
        return None
    if sess.get("is_demo") or str(sess.get("user_id", "")).startswith("demo_user_"):
        return None
    return sess


# Sentinel league for account-only sessions (P2.6): a REAL empty league —
# never session_init's simulated-opponent fallback — so league-scoped
# features return empty states instead of 409s or fake demo opponents.
ACCOUNT_NO_LEAGUE_ID = "no_league"
ACCOUNT_NO_LEAGUE_NAME = "No league linked"


def _account_build_session(user_id: str, display_name: str) -> tuple[str, dict]:
    """Build a full session for an account-only user (P2.6).

    Contract: upserts the users row for `user_id` and returns
    (token, session_payload) with per-format Ranking + Trade services and an
    EMPTY league, so `_require_initialized_session` routes (rank3,
    tiers/save, anchor/save, reorder) work; trade generation yields zero
    cards (no members) and match routes return empty — the honest
    "link a league" state.
    """
    token, payload = _extension_build_session(
        user_id=user_id,
        username="",
        display_name=display_name,
        avatar=None,
    )
    empty_league = League(
        league_id=ACCOUNT_NO_LEAGUE_ID,
        name=ACCOUNT_NO_LEAGUE_NAME,
        platform="none",
        members=[],
    )
    default_pool, _ = _get_universal_pool(DEFAULT_SCORING)
    trade_svcs: dict = {}
    for fmt in SCORING_FORMATS:
        fmt_pool, _ = _get_universal_pool(fmt)
        tsvc = TradeService(players={p.id: p for p in fmt_pool},
                            past_decision_keys=set())
        tsvc.add_league(empty_league)
        trade_svcs[fmt] = tsvc
    payload.update({
        "league":       empty_league,
        "players":      list(default_pool),
        "user_roster":  [],
        "trade_svcs":   trade_svcs,
        "trade_svc":    trade_svcs[DEFAULT_SCORING],
        "account_only": True,
    })
    payload.pop("extension", None)
    return token, payload


def _provider_auth_response(provider: str, claims: dict):
    """Shared find-or-create + bind + verify flow for /api/auth/<provider>.

    Binding rules (see accounts.bind_sleeper_user — binding is sticky):
      * session present, account unbound      → bind to session's user_id
        (never an acct_* working key — synthetic keys are not Sleeper
        sources; those sessions get account-only re-auth instead)
      * session present, same binding         → no-op
      * session present, DIFFERENT binding    → keep existing binding, flag
        `conflict` (identity anchor wins; no silent rebinding)
      * no session, account bound             → device-loss restore: mint a
        session for the bound user
      * no session, account unbound           → ACCOUNT-FIRST (P2.6): mint an
        account-keyed session (working key acct_<account_id>); the user can
        rank immediately and link a Sleeper username later from Settings
    """
    sub = claims.get("sub")
    if not sub:
        return jsonify({"error": "invalid_token", "reason": "missing_sub"}), 401
    acct = _accounts.find_or_create_account(
        provider, sub, _accounts.hash_email(claims.get("email"))
    )
    sess = _account_session()

    out: dict = {
        "ok": True,
        "provider": provider,
        "account_id": acct["account_id"],
        "linked": False,
        "sleeper_user_id": None,
        "conflict": False,
    }

    def _mint_account_only_session():
        """No linked Sleeper source: session under the synthetic acct_ key."""
        acct_uid = _accounts.account_user_id(acct["account_id"])
        # Apple sends the user's name only to the CLIENT (and only on first
        # authorization) — the client forwards it as display_name.
        body = request.get_json(force=True, silent=True) or {}
        display = (body.get("display_name") or "").strip() or "Manager"
        try:
            token, payload = _account_build_session(acct_uid, display)
        except Exception as e:
            log.exception("auth/%s: account session build failed", provider)
            return jsonify({"error": "session_build_failed",
                            "message": str(e)}), 500
        payload["verified"] = True
        payload["verified_via"] = provider
        payload["account_id"] = acct["account_id"]
        try:
            # The provider proof IS the identity proof for an account-keyed
            # user (no Sleeper account exists to squat); persisting the
            # marker also arms the P1/P2.5 gates against anyone else
            # naming this key via /api/session/init.
            _accounts.mark_user_verified(acct_uid, provider)
        except Exception as e:
            log.warning("auth/%s: mark_user_verified failed: %s", provider, e)
        out.update({
            "account_only": True,
            "user_id": acct_uid,
            "display_name": payload.get("display_name"),
            "session_token": token,
            "verified_via": provider,
            "league_id": ACCOUNT_NO_LEAGUE_ID,
            "league_name": ACCOUNT_NO_LEAGUE_NAME,
        })
        return jsonify(out)

    bound_uid = acct["sleeper_user_id"]
    if sess is not None and _accounts.is_account_user_id(sess.get("user_id")):
        # An account-keyed session re-authing with a provider: never bind the
        # synthetic key into accounts.sleeper_user_id. Refresh the session's
        # verified state instead (same-account case); a different account's
        # token just returns that account's state untouched.
        if sess.get("user_id") == _accounts.account_user_id(acct["account_id"]):
            sess["verified"] = True
            sess["verified_via"] = provider
            sess["account_id"] = acct["account_id"]
            out.update({
                "account_only": True,
                "user_id": sess["user_id"],
                "verified_via": provider,
                "league_id": ACCOUNT_NO_LEAGUE_ID,
                "league_name": ACCOUNT_NO_LEAGUE_NAME,
            })
        return jsonify(out)
    if sess is not None:
        bind = _accounts.bind_sleeper_user(acct["account_id"], sess["user_id"])
        out["linked"] = True
        out["sleeper_user_id"] = bind["sleeper_user_id"]
        out["conflict"] = bind["conflict"]
        if not bind["conflict"]:
            # Session's user is now anchored to this provider identity.
            sess["verified"] = True
            sess["verified_via"] = provider
            sess["account_id"] = acct["account_id"]
            out["verified_via"] = provider
            try:
                _accounts.mark_user_verified(sess["user_id"], provider)
            except Exception as e:
                log.warning("auth/%s: mark_user_verified failed: %s", provider, e)
    elif bound_uid:
        # Device-loss restore: no session, but this identity already anchors
        # a Sleeper-keyed user. Mint a user-scoped session (same shape the
        # extension auth builds) and mark it verified.
        profile = _accounts.get_user_profile(bound_uid) or {}
        try:
            token, payload = _extension_build_session(
                user_id=bound_uid,
                username=profile.get("username") or "",
                display_name=profile.get("display_name") or profile.get("username") or "",
                avatar=profile.get("avatar"),
            )
        except Exception as e:
            log.exception("auth/%s: restore session build failed", provider)
            return jsonify({"error": "session_build_failed", "message": str(e)}), 500
        payload["verified"] = True
        payload["verified_via"] = provider
        payload["account_id"] = acct["account_id"]
        try:
            _accounts.mark_user_verified(bound_uid, provider)
        except Exception as e:
            log.warning("auth/%s: mark_user_verified failed: %s", provider, e)
        out.update({
            "linked": True,
            "sleeper_user_id": bound_uid,
            "username": profile.get("username"),
            "display_name": profile.get("display_name"),
            "avatar": profile.get("avatar"),
            "session_token": token,
            "verified_via": provider,
        })
    else:
        # ACCOUNT-FIRST (P2.6): brand-new identity, no session, no bound
        # Sleeper source — the account itself is the primary identity.
        return _mint_account_only_session()

    return jsonify(out)


@app.route("/api/auth/apple", methods=["POST"])
def auth_apple():
    """Sign in with Apple — verify the identity token, find-or-create the
    account, bind/restore per the rules on _provider_auth_response."""
    if not is_enabled("auth.accounts"):
        return jsonify({"error": "not_found"}), 404
    body = request.get_json(force=True, silent=True) or {}
    token = (body.get("identity_token") or "").strip()
    if not token:
        return jsonify({"error": "missing_token",
                        "message": "identity_token required."}), 400
    try:
        claims = _accounts.verify_apple_token(token)
    except _accounts.TokenVerificationError as e:
        log.info("auth/apple: token rejected (%s)", e.reason)
        return jsonify({"error": "invalid_token", "reason": e.reason}), 401
    return _provider_auth_response("apple", claims)


@app.route("/api/auth/google", methods=["POST"])
def auth_google():
    """Google ID-token sign-in — same code path as Apple, different issuer.

    Requires GOOGLE_OAUTH_CLIENT_ID in the environment (the token `aud`);
    returns 503 not_configured until the operator sets it. The mobile
    surface for Google is stubbed for now — Apple is the App-Store-mandatory
    anchor (Guideline 4.8)."""
    if not is_enabled("auth.accounts"):
        return jsonify({"error": "not_found"}), 404
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    if not client_id:
        return jsonify({"error": "not_configured",
                        "message": "Google sign-in is not configured."}), 503
    body = request.get_json(force=True, silent=True) or {}
    token = (body.get("id_token") or body.get("identity_token") or "").strip()
    if not token:
        return jsonify({"error": "missing_token",
                        "message": "id_token required."}), 400
    try:
        claims = _accounts.verify_google_token(token, client_id)
    except _accounts.TokenVerificationError as e:
        log.info("auth/google: token rejected (%s)", e.reason)
        return jsonify({"error": "invalid_token", "reason": e.reason}), 401
    return _provider_auth_response("google", claims)


@app.route("/api/account")
def get_account_route():
    """Current account: linked identities + bound Sleeper id + verified state."""
    if not is_enabled("auth.accounts"):
        return jsonify({"error": "not_found"}), 404
    sess = _require_session()
    user_id = sess["user_id"]
    acct = None
    if sess.get("account_id"):
        acct = _accounts.get_account(sess["account_id"])
    if acct is None:
        acct = _accounts.get_account_for_user(user_id)
    verified_via = sess.get("verified_via")
    if verified_via is None:
        try:
            verified_via = _accounts.get_user_verified_via(user_id)
        except Exception:
            verified_via = None
    # P2.6 additive: is this an account-keyed (no linked Sleeper) session,
    # and — when a Sleeper source IS bound — its username for the Settings
    # "linked sources" list. ESPN leagues will join this list later.
    account_only = _accounts.is_account_user_id(user_id)
    sleeper_username = None
    if acct and acct.get("sleeper_user_id"):
        profile = _accounts.get_user_profile(acct["sleeper_user_id"]) or {}
        sleeper_username = profile.get("username") or None
    return jsonify({
        "ok": True,
        "sleeper_user_id": user_id,
        "verified_via": verified_via,
        "account": acct,   # null when no identity is linked yet
        "account_only": account_only,
        "sleeper_username": sleeper_username,
    })


@app.route("/api/account/link-sleeper", methods=["POST"])
def link_sleeper_source():
    """Link a Sleeper username as a source on the session's account (P2.6).

    Body: {username, strategy?}. Requires an account-backed session (only
    provider auth sets sess["account_id"], so a plain username squatter can
    never reach the merge). Rules — full reasoning in the plan doc §P2.6:

      * sticky binding: account bound to a DIFFERENT Sleeper id
        → 409 sleeper_conflict (nothing touched)
      * first-verified-wins: the target Sleeper id already has a verified
        controller → 403 sleeper_already_claimed (no takeover)
      * both boards have data and no `strategy`
        → 409 merge_choice_required + both summaries
      * strategy='keep_sleeper' → account board wiped (explicit choice)
      * strategy='keep_account' → Sleeper board wiped, account board moved
      * account board only → migrated; Sleeper board only / neither → adopt

    On success: account bound, Sleeper user marked verified via the
    account's provider, every acct_* session evicted, and a fresh session
    for the Sleeper user returned (client re-runs the league picker).
    """
    if not is_enabled("auth.accounts"):
        return jsonify({"error": "not_found"}), 404
    sess = _require_session()
    account_id = sess.get("account_id")
    if not account_id:
        return jsonify({"error": "no_account",
                        "message": "Sign in with Apple or Google first."}), 400

    body = request.get_json(force=True, silent=True) or {}
    username = (body.get("username") or "").strip().lower()
    strategy = (body.get("strategy") or "").strip() or None
    if not username:
        return jsonify({"error": "missing_username",
                        "message": "Sleeper username required."}), 400
    if strategy not in (None, "keep_sleeper", "keep_account"):
        return jsonify({"error": "bad_strategy"}), 400

    try:
        user_data = _sleeper_get(
            f"https://api.sleeper.app/v1/user/{urllib.parse.quote(username)}"
        )
    except Exception as e:
        return jsonify({"error": "sleeper_error", "message": str(e)}), 502
    if not isinstance(user_data, dict) or not user_data.get("user_id"):
        return jsonify({"error": "user_not_found",
                        "message": f"Sleeper user @{username} not found."}), 404
    sleeper_uid = str(user_data["user_id"])
    display_name = user_data.get("display_name") or username
    avatar = user_data.get("avatar")

    acct = _accounts.get_account(account_id)
    if acct is None:
        return jsonify({"error": "no_account"}), 400
    bound = acct.get("sleeper_user_id")
    if bound and bound != sleeper_uid:
        return jsonify({"error": "sleeper_conflict",
                        "message": "This account is already linked to a "
                                   "different Sleeper username."}), 409
    already_bound = bound == sleeper_uid

    # First-verified-wins: an account cannot take over a Sleeper id whose
    # control someone already proved (Sleeper-JWT owner or another account).
    if not already_bound:
        controller_via = _verified_controller_via(sleeper_uid)
        if controller_via:
            log.warning("link-sleeper: DENY account=%s target=%s "
                        "reason=verified_controller via=%s",
                        account_id, sleeper_uid, controller_via)
            return jsonify({
                "error": "sleeper_already_claimed",
                "message": "That Sleeper account is already verified by "
                           "another sign-in.",
            }), 403

    acct_uid = sess["user_id"]
    provider = sess.get("verified_via") or next(
        (i["provider"] for i in (acct.get("identities") or [])), "apple")

    merged = None
    if _accounts.is_account_user_id(acct_uid) and not already_bound:
        from .database import reset_user_rankings
        acct_board = _accounts.board_data_summary(acct_uid)
        sleeper_board = _accounts.board_data_summary(sleeper_uid)
        if acct_board["any"] and sleeper_board["any"] and strategy is None:
            # Explicit user choice — never silently prefer a side.
            return jsonify({
                "error": "merge_choice_required",
                "account_board": acct_board,
                "sleeper_board": sleeper_board,
            }), 409
        if acct_board["any"] and sleeper_board["any"]:
            if strategy == "keep_sleeper":
                reset_user_rankings(acct_uid)
                merged = "kept_sleeper"
            else:  # keep_account
                reset_user_rankings(sleeper_uid)
                _accounts.migrate_board_data(acct_uid, sleeper_uid)
                merged = "kept_account"
        elif acct_board["any"]:
            _accounts.migrate_board_data(acct_uid, sleeper_uid)
            merged = "migrated"
        else:
            merged = "adopted_sleeper"

    bind = _accounts.bind_sleeper_user(account_id, sleeper_uid)
    if bind["conflict"]:  # raced binding — nothing more to do safely
        return jsonify({"error": "sleeper_conflict"}), 409

    try:
        token, payload = _extension_build_session(
            user_id=sleeper_uid,
            username=username,
            display_name=display_name,
            avatar=avatar,
        )
    except Exception as e:
        log.exception("link-sleeper: session build failed")
        return jsonify({"error": "session_build_failed", "message": str(e)}), 500
    payload["verified"] = True
    payload["verified_via"] = provider
    payload["account_id"] = account_id
    try:
        _accounts.mark_user_verified(sleeper_uid, provider)
    except Exception as e:
        log.warning("link-sleeper: mark_user_verified failed: %s", e)

    # Evict the account-keyed sessions — their working key just migrated.
    if _accounts.is_account_user_id(acct_uid):
        with _sessions_lock:
            for t in [t for t, s in _sessions.items()
                      if s.get("user_id") == acct_uid]:
                _sessions.pop(t, None)

    log.info("link-sleeper: account=%s bound sleeper=%s merge=%s",
             account_id, sleeper_uid, merged)
    return jsonify({
        "ok": True,
        "sleeper_user_id": sleeper_uid,
        "username": username,
        "display_name": display_name,
        "avatar": avatar,
        "session_token": token,
        "verified_via": provider,
        "merge": merged,
    })


@app.route("/api/account", methods=["DELETE"])
def delete_account_route():
    """In-app account deletion (App Store 5.1.1(v)) — NOT flag-gated.

    Deletes/anonymizes per the matrix documented in accounts.delete_user_data
    (honors web/privacy.html §6). When the user record has been verified
    (users.verified_via set), the calling session must itself be verified —
    a username-only squatter session cannot delete a verified user's data.
    Also evicts every live session for the user (server-side sign-out).
    """
    sess = _require_session()
    user_id = sess.get("user_id")
    if sess.get("is_demo") or str(user_id or "").startswith("demo_user_"):
        return jsonify({"error": "demo_session",
                        "message": "Demo sessions have no stored data."}), 400
    try:
        verified_via = _accounts.get_user_verified_via(user_id)
    except Exception:
        verified_via = None
    if verified_via and not sess.get("verified"):
        return jsonify({
            "error": "verification_required",
            "message": "This account is verified — verify this session "
                       "before deleting it.",
        }), 403
    try:
        counts = _accounts.delete_user_data(user_id,
                                            account_id=sess.get("account_id"))
    except Exception as e:
        log.exception("delete_account: deletion failed for %s", user_id)
        return jsonify({"error": "deletion_failed", "message": str(e)}), 500
    with _sessions_lock:
        for t in [t for t, s in _sessions.items()
                  if s.get("user_id") == user_id]:
            _sessions.pop(t, None)
    log.info("delete_account: user %s deleted (%s)", user_id, counts)
    return jsonify({"ok": True, "deleted": counts})


# ---------------------------------------------------------------------------
# ESPN league linking — Phase 1 read-only import (#101 / feedback #115)
# Flag: `espn.link` (default OFF — every route 404s dark).
# Plan: docs/plans/espn-league-linking-plan-2026-07-11.md
#
# Flow: POST /api/espn/link without team_id → preview (teams + crosswalk
# match report, nothing persisted) → the user picks their team → POST again
# with team_id → league + members persisted (rosters as crosswalked SLEEPER
# player ids). The mobile client then activates the league through the
# standard /api/session/init using GET /api/espn/leagues as the roster
# source (no session_init changes needed — its existing DB-member merge and
# upsert paths treat the imported league like any other).
#
# Binding note (account-first seam): imported leagues bind to the session's
# user_id as identity works TODAY (Sleeper-keyed users). When the
# account-first model lands, this binding rides along automatically because
# it lives in leagues.user_id / league_members.user_id — the same seam every
# Sleeper league sits on. Counterparties get synthetic `espn:` user ids that
# must never reach push/notification paths (same class as unlinked members).
#
# Private leagues: espn_s2+SWID cookies may be pasted with the link request;
# they are Fernet-encrypted at rest (SLEEPER_TOKEN_KEY) and replayed on
# re-imports. The in-app WebView cookie capture is Phase 1b.
# ---------------------------------------------------------------------------

_ESPN_DEFAULT_SEASON = 2026


def _espn_member_id(league_id: str, team) -> str:
    """Deterministic synthetic user_id for a non-FTF ESPN manager."""
    if team.owner_swid:
        return f"espn:{team.owner_swid}"
    return f"espn:{league_id}.t{team.team_id}"


def _espn_error_response(e):
    """Map an EspnError to a (json, status) response."""
    kind = getattr(e, "kind", "http")
    if kind == "auth":
        return jsonify({
            "error": "espn_auth_required",
            "message": "ESPN wouldn't share this league — it's private or the "
                       "saved cookies expired. Paste fresh espn_s2 + SWID "
                       "cookies to continue.",
        }), 403
    if kind == "not_found":
        return jsonify({
            "error": "espn_league_not_found",
            "message": "ESPN has no league with that ID for that season. "
                       "ESPN purges old leagues — check the ID and season.",
        }), 404
    if kind == "input":
        return jsonify({"error": "espn_bad_league_id",
                        "message": "ESPN league IDs are numeric."}), 400
    log.warning("espn fetch failed [%s]: %s", kind, e)
    return jsonify({"error": "espn_unavailable",
                    "message": "Couldn't reach ESPN — try again shortly."}), 502


def _espn_import_payload(league_id: str, season: int, espn_s2: str | None,
                         swid: str | None):
    """Fetch + parse + crosswalk one ESPN league. Returns (league, mapped)."""
    from . import espn_service as _espn
    raw = _espn.fetch_league(league_id, season, espn_s2=espn_s2, swid=swid)
    league = _espn.parse_league(raw)
    mapped = _espn.map_rosters(league["teams"], _espn.get_crosswalk())
    return league, mapped


def _espn_report_json(report: dict) -> dict:
    """Client-facing crosswalk report — unmatched players are skipped from
    rosters and reported by name (plan §3: never invent placeholders)."""
    return {
        "pool_players":    report["pool_players"],
        "matched_by_id":   report["matched_by_id"],
        "matched_by_name": report["matched_by_name"],
        "match_rate":      round(report["match_rate"], 4),
        "out_of_pool":     report["out_of_pool"],
        "unmatched":       [
            {"name": u["name"], "position": u["position"]}
            for u in report["unmatched"]
        ],
    }


@app.route("/api/espn/link", methods=["POST"])
@_gate_unverified_write
def espn_link():
    """Link (import) an ESPN league for the session user.

    Body: {espn_league_id, season?, team_id?, espn_s2?, swid?}
      • no team_id  → PREVIEW: fetch + crosswalk, return the team list and
        match report; nothing is persisted.
      • team_id     → IMPORT: persist the league (platform='espn') + all
        member rosters (Sleeper player ids); the chosen team binds to the
        session's user_id. Idempotent — re-linking refreshes everything.
      • espn_s2+swid (both or neither) → private-league cookies; encrypted
        at rest and reused for future re-imports.
    404 while the espn.link flag is off.
    """
    if not is_enabled("espn.link"):
        return jsonify({"error": "feature_disabled"}), 404
    from . import espn_service as _espn
    from .database import (get_espn_credential, upsert_espn_credential,
                           upsert_espn_league, replace_espn_league_members)

    sess = _require_session()
    user_id = sess.get("user_id")
    if not user_id:
        return jsonify({"error": "no_user"}), 401

    body = request.get_json(force=True) or {}
    league_id = str(body.get("espn_league_id") or "").strip()
    if not league_id.isdigit():
        return jsonify({"error": "espn_bad_league_id",
                        "message": "ESPN league IDs are numeric."}), 400
    try:
        season = int(body.get("season") or _ESPN_DEFAULT_SEASON)
    except (TypeError, ValueError):
        return jsonify({"error": "espn_bad_season"}), 400

    espn_s2 = (body.get("espn_s2") or "").strip() or None
    swid    = (body.get("swid") or "").strip() or None
    if bool(espn_s2) != bool(swid):
        return jsonify({"error": "espn_cookies_incomplete",
                        "message": "Private leagues need BOTH espn_s2 and SWID."}), 400

    # Fall back to previously-stored cookies so re-links of a private league
    # don't require a fresh paste.
    pasted_cookie = bool(espn_s2)
    if not espn_s2:
        cred = get_espn_credential(user_id)
        if cred:
            try:
                espn_s2 = _sleeper_write.decrypt_token(cred["espn_s2_encrypted"])
                swid = cred.get("swid")
            except _sleeper_write.SleeperWriteError as e:
                log.warning("espn_link: stored cookie undecryptable for %s: %s",
                            user_id, e)
                espn_s2 = swid = None

    try:
        league, mapped = _espn_import_payload(league_id, season, espn_s2, swid)
    except _espn.EspnError as e:
        return _espn_error_response(e)

    teams_json = [
        {
            "team_id":        t.team_id,
            "name":           t.name,
            "owner_display":  t.owner_display,
            "mapped_players": len(mapped["rosters"].get(t.team_id, [])),
        }
        for t in league["teams"]
    ]

    team_id = body.get("team_id")
    if team_id is None:
        # Preview — the client renders "which team is yours?"
        return jsonify({
            "status": "choose_team",
            "league": {
                "espn_league_id": league["league_id"] or league_id,
                "name":           league["name"],
                "season":         league["season"] or season,
                "total_teams":    league["total_teams"],
            },
            "teams":  teams_json,
            "report": _espn_report_json(mapped["report"]),
        })

    try:
        team_id = int(team_id)
    except (TypeError, ValueError):
        return jsonify({"error": "espn_bad_team_id"}), 400
    if team_id not in {t.team_id for t in league["teams"]}:
        return jsonify({"error": "espn_bad_team_id",
                        "message": "That team isn't in this league."}), 400

    # Persist cookies first (so a later re-import can reuse them), then the
    # league + membership snapshot.
    auth_mode = "cookie" if (espn_s2 and swid) else "public"
    if pasted_cookie:
        if not _sleeper_write.token_encryption_available():
            return jsonify({"error": "espn_unconfigured",
                            "message": "Credential encryption key missing."}), 503
        try:
            upsert_espn_credential(user_id, swid,
                                   _sleeper_write.encrypt_token(espn_s2))
        except Exception:
            log.exception("espn_link: credential store failed")
            return jsonify({"error": "store_failed"}), 500

    members = []
    for t in league["teams"]:
        mid = user_id if t.team_id == team_id else _espn_member_id(league_id, t)
        members.append({
            "user_id":      mid,
            "username":     t.owner_display or t.name,
            "display_name": t.name,
            "player_ids":   mapped["rosters"].get(t.team_id, []),
        })
    try:
        upsert_espn_league(
            league_id       = league_id,
            user_id         = user_id,
            name            = league["name"] or f"ESPN league {league_id}",
            espn_season     = league["season"] or season,
            espn_auth       = auth_mode,
            espn_my_team_id = team_id,
            total_rosters   = league["total_teams"],
        )
        replace_espn_league_members(league_id, members)
    except Exception:
        log.exception("espn_link: persistence failed")
        return jsonify({"error": "store_failed"}), 500

    r = mapped["report"]
    log.info("espn_link: user=%s league=%s season=%s teams=%d auth=%s "
             "match_rate=%.1f%% unmatched=%d",
             user_id, league_id, season, len(members), auth_mode,
             r["match_rate"] * 100, len(r["unmatched"]))
    return jsonify({
        "ok": True,
        "league_id":      league_id,
        "name":           league["name"],
        "platform":       "espn",
        "season":         league["season"] or season,
        "auth":           auth_mode,
        "total_teams":    league["total_teams"],
        "teams_imported": len(members),
        "my_team_id":     team_id,
        "my_roster":      mapped["rosters"].get(team_id, []),
        "report":         _espn_report_json(r),
    })


@app.route("/api/espn/leagues")
def espn_leagues():
    """ESPN leagues linked by the session user, with the full membership
    snapshot (Sleeper player ids) so the client can build a standard
    /api/session/init body. 404 while the espn.link flag is off."""
    if not is_enabled("espn.link"):
        return jsonify({"error": "feature_disabled"}), 404
    from .database import load_espn_leagues_for_user
    sess = _require_session()
    user_id = sess.get("user_id")
    if not user_id:
        return jsonify({"error": "no_user"}), 401
    leagues = load_espn_leagues_for_user(user_id)
    for lg in leagues:
        lg["members"] = [
            {
                "user_id":      m["user_id"],
                "username":     m.get("username") or "",
                "display_name": m.get("display_name") or "",
                "player_ids":   m.get("player_ids", []),
            }
            for m in lg["members"]
        ]
    return jsonify({"leagues": leagues})


@app.route("/api/espn/import", methods=["POST"])
@_gate_unverified_write
def espn_import():
    """Re-sync an already-linked ESPN league's rosters (manual refresh).

    Body: {league_id}. Re-fetches from ESPN using the stored auth mode
    (public, or the user's encrypted cookies), re-runs the crosswalk, and
    replaces the membership snapshot while preserving the user's team
    binding. 404 while the espn.link flag is off; 403 espn_auth_required
    when a private league's cookies are missing/expired (reconnect UX).
    """
    if not is_enabled("espn.link"):
        return jsonify({"error": "feature_disabled"}), 404
    from . import espn_service as _espn
    from .database import (get_espn_league, get_espn_credential,
                           replace_espn_league_members, upsert_espn_league)

    sess = _require_session()
    user_id = sess.get("user_id")
    if not user_id:
        return jsonify({"error": "no_user"}), 401

    body = request.get_json(force=True) or {}
    league_id = str(body.get("league_id") or "").strip()
    row = get_espn_league(league_id) if league_id else None
    if not row:
        return jsonify({"error": "espn_not_linked",
                        "message": "Link this ESPN league first."}), 404

    espn_s2 = swid = None
    if row.get("espn_auth") == "cookie":
        cred = get_espn_credential(user_id)
        if not cred:
            return jsonify({"error": "espn_auth_required",
                            "message": "This private league needs your ESPN "
                                       "cookies again."}), 403
        try:
            espn_s2 = _sleeper_write.decrypt_token(cred["espn_s2_encrypted"])
            swid = cred.get("swid")
        except _sleeper_write.SleeperWriteError:
            return jsonify({"error": "espn_unconfigured"}), 503

    season = row.get("espn_season") or _ESPN_DEFAULT_SEASON
    try:
        league, mapped = _espn_import_payload(league_id, season, espn_s2, swid)
    except _espn.EspnError as e:
        return _espn_error_response(e)

    my_team_id = row.get("espn_my_team_id")
    if my_team_id not in {t.team_id for t in league["teams"]}:
        return jsonify({"error": "espn_team_missing",
                        "message": "Your team is no longer in this ESPN "
                                   "league — re-link to pick a team."}), 409

    members = []
    for t in league["teams"]:
        mid = user_id if t.team_id == my_team_id else _espn_member_id(league_id, t)
        members.append({
            "user_id":      mid,
            "username":     t.owner_display or t.name,
            "display_name": t.name,
            "player_ids":   mapped["rosters"].get(t.team_id, []),
        })
    try:
        upsert_espn_league(
            league_id       = league_id,
            user_id         = row["user_id"],
            name            = league["name"] or row.get("name") or "",
            espn_season     = league["season"] or season,
            espn_auth       = row.get("espn_auth") or "public",
            espn_my_team_id = my_team_id,
            total_rosters   = league["total_teams"],
        )
        replace_espn_league_members(league_id, members)
    except Exception:
        log.exception("espn_import: persistence failed")
        return jsonify({"error": "store_failed"}), 500

    return jsonify({
        "ok": True,
        "league_id":      league_id,
        "name":           league["name"],
        "platform":       "espn",
        "season":         league["season"] or season,
        "auth":           row.get("espn_auth") or "public",
        "total_teams":    league["total_teams"],
        "teams_imported": len(members),
        "my_team_id":     my_team_id,
        "my_roster":      mapped["rosters"].get(my_team_id, []),
        "report":         _espn_report_json(mapped["report"]),
    })


# ---------------------------------------------------------------------------
# League power rankings (#142/#144) — math in backend/power_rankings.py
# ---------------------------------------------------------------------------

@app.route("/api/league/power-rankings")
def league_power_rankings_route():
    """GET /api/league/power-rankings?league_id=...&basis=consensus|personal|redraft

    Ranks every team in the league by summed roster value; each team carries
    its full roster (grouped by position, value-desc within group — #144) so
    the client's team drill-in needs no second call.

    basis:
      - consensus (default): universal-pool consensus values (elo_to_value
        over the pool seed) — the same numbers /api/trade/values serves.
        League-shared aggregate, open like /api/league/coverage.
      - personal: the CALLER's live board for the active format (their Elo
        starts at the consensus seed and diverges as they rank), consensus
        fallback for players outside their board. Board-derived content →
        the P2.5 read gate applies inline (mirrors /api/trade/evaluate
        Mode B; the route can't take @_gate_unverified_read wholesale
        because the consensus basis is league-shared by design).
      - redraft: 501 not_available — FTF's value source (DynastyProcess) is
        dynasty-only today. The parameter shape is reserved so clients can
        probe; UI shows a disabled "(soon)" chip.

    ESPN-imported leagues work unchanged: their members sit in league_members
    with synthetic `espn:` user ids but Sleeper player ids (crosswalked at
    import), so value resolution is identical.
    """
    from .power_rankings import compute_power_rankings

    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess.get("league")
    league_id = request.args.get("league_id") or (g_league.league_id if g_league else "")
    if not league_id:
        return jsonify({"error": "league_id is required"}), 400

    basis = (request.args.get("basis") or "consensus").strip().lower()
    if basis == "redraft":
        return jsonify({
            "error":   "not_available",
            "message": ("Redraft rankings aren't available yet — FTF values "
                        "are dynasty-only. Use basis=consensus or "
                        "basis=personal."),
        }), 501
    if basis not in ("consensus", "personal"):
        return jsonify({"error": "basis must be one of consensus, personal, redraft"}), 400

    board_elo = None
    if basis == "personal":
        denial = _verified_read_denial(sess)
        if denial is not None:
            return denial
        service = sess["service"]
        board_elo = {
            rp.player.id: rp.elo
            for rp in service.get_rankings(position=None).rankings
        }

    fmt = _active_format(sess)
    try:
        members = load_league_members(league_id)
        if not members and g_league and g_league.league_id == league_id:
            # Fresh/demo leagues may not have a league_members snapshot yet —
            # fall back to the in-session league (leaguemates) + the caller's
            # own roster (session league members exclude the caller).
            members = [{
                "user_id":      m.user_id,
                "username":     m.username,
                "display_name": m.username,
                "player_ids":   list(m.roster),
            } for m in g_league.members]
            members.append({
                "user_id":      g_user_id,
                "username":     sess.get("display_name") or g_user_id,
                "display_name": sess.get("display_name") or g_user_id,
                "player_ids":   list(sess.get("user_roster") or []),
            })
        if not members:
            return jsonify({"error": "league_not_found"}), 404

        pool_players, seed = _get_universal_pool(fmt)
        # Demo-style sessions rank a synthetic player pool whose ids never
        # appear in the universal pool; their consensus lives in the session
        # service's seed ratings. Merge those in as a FALLBACK (pool seed
        # wins) so demo consensus totals aren't all-zero. Real leagues are
        # unaffected — their session ranking pool is the universal pool.
        svc_seed = getattr(sess.get("service"), "_seed", None) or {}
        if svc_seed:
            seed = {**svc_seed, **seed}
        # Metadata: universal pool first, session players filling any gaps
        # (league roster players outside the pool still need name/position).
        players_meta = {p.id: p for p in pool_players}
        for p in (sess.get("players") or []):
            players_meta.setdefault(p.id, p)

        teams = compute_power_rankings(members, seed, players_meta, board_elo=board_elo)
        for t in teams:
            t["is_you"] = (t["user_id"] == g_user_id)
        return jsonify({
            "league_id":      league_id,
            "basis":          basis,
            "scoring_format": fmt,
            "teams":          teams,
        })
    except Exception as e:
        log.error("league/power-rankings error: %s", e)
        return jsonify({"error": "internal_error"}), 500


# ---------------------------------------------------------------------------
# Free-agent finder (feedback #143) — logic in backend/free_agent_service.py
# ---------------------------------------------------------------------------

@app.route("/api/league/free-agents")
@_gate_unverified_read
def league_free_agents_route():
    """GET /api/league/free-agents?league_id=...&position=RB

    Best available free agents in the league, ranked by the CALLER'S board
    value (personal Elo, consensus seed fallback for anything they haven't
    ranked). FA pool = active format's universal pool minus every rostered
    player in the league — session-league rosters when league_id matches the
    session (Sleeper / ESPN-imported / demo alike), league_members snapshot
    otherwise. Each row may carry a drop_suggestion: the caller's lowest-
    valued same-position rostered player whose value is strictly below the
    FA's, with the add/drop delta.

    Query params:
      league_id  — optional, defaults to the session league.
      position   — optional QB|RB|WR|TE (or ALL/omitted for all positions).

    Response:
      {
        "league_id":         str,
        "scoring_format":    "1qb_ppr" | "sf_tep",
        "position":          "QB"|"RB"|"WR"|"TE"|"ALL",
        "user_has_rankings": bool,   # False = whole list is pure consensus
        "free_agents": [
          {"player_id", "name", "position", "team", "age",
           "value": float,          # caller-board dynasty value
           "pos_rank": int,         # 1-based rank within position among FAs
           "drop_suggestion": {"player_id", "name", "position",
                               "value", "delta"} | null}, ...
        ]  # top 50 after the position filter
      }

    Read-gated (@_gate_unverified_read): the list is priced by the caller's
    board, so it's board-derived content like /api/rankings.
    """
    from .free_agent_service import (
        FA_POSITIONS, board_is_personalized, compute_free_agents,
    )
    sess = _require_initialized_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess.get("league")
    league_id = request.args.get("league_id") or (g_league.league_id if g_league else "")
    if not league_id:
        return jsonify({"error": "league_id is required"}), 400

    raw_pos  = (request.args.get("position") or "").strip().upper()
    position = None if raw_pos in ("", "ALL") else raw_pos
    if position is not None and position not in FA_POSITIONS:
        return jsonify({"error": f"Invalid position: {raw_pos!r}"}), 400

    fmt = _active_format(sess)
    try:
        pool_players, seed = _get_universal_pool(fmt)
        service  = sess["service"]
        user_elo = {rp.player.id: rp.elo
                    for rp in service.get_rankings(position=None).rankings}

        # Rosters: the in-session league object when it matches (covers
        # Sleeper, ESPN-imported and demo leagues — session init builds all
        # three); DB league_members snapshot for any other league_id.
        if g_league and league_id == g_league.league_id:
            member_rosters = [list(m.roster or []) for m in g_league.members]
            user_roster    = list(sess.get("user_roster") or [])
        else:
            rows = load_league_members(league_id)
            member_rosters = [r.get("player_ids") or [] for r in rows
                              if r.get("user_id") != g_user_id]
            user_roster    = next((r.get("player_ids") or [] for r in rows
                                   if r.get("user_id") == g_user_id), [])
        rostered = {pid for roster in member_rosters for pid in roster}

        free_agents = compute_free_agents(
            pool_players = pool_players,
            seed_elo     = seed,
            user_elo     = user_elo,
            rostered_ids = rostered,
            user_roster  = user_roster,
            position     = position,
        )
        return jsonify({
            "league_id":         league_id,
            "scoring_format":    fmt,
            "position":          position or "ALL",
            "user_has_rankings": board_is_personalized(user_elo, seed),
            "free_agents":       free_agents,
        })
    except Exception as e:
        log.error("league/free-agents error: %s", e)
        return jsonify({"error": "internal_error"}), 500


if __name__ == "__main__":
    # Pre-load Sleeper player cache from disk if available
    _load_sleeper_cache()

    # Sync player cache to DB (no-op if data is fresh, runs in ~1 s)
    _maybe_sync_players()

    print("\n🏈 Fantasy Trade Finder — Dynasty Rankings")
    print("   Open http://127.0.0.1:5000 in your browser\n")
    app.run(debug=True, port=5000)
