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
import json
import logging
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

from flask import Flask, g, jsonify, request, send_from_directory

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
from .data_loader import load_consensus_elo, load_consensus_values, seed_elo_for_players, normalise_name
from .database import (
    init_db,
    upsert_user, upsert_league,
    save_ranking_swipes, save_trade_swipes,
    save_trade_decision, load_swipe_decisions, load_trade_decisions,
    upsert_league_members, upsert_member_rankings,
    load_member_rankings, load_league_members, get_ranking_coverage,
    check_for_match, match_already_exists,
    create_trade_match, load_matches,
    record_match_disposition,
    upsert_league_preference, load_league_preference,
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
    mark_format_unlocked, get_unlocked_formats,
    set_league_scoring, get_league_scoring, get_league_summary,
    # Agent A4 additions — league social features
    load_league_member_unlock_states, load_league_activity,
    SCORING_FORMATS, DEFAULT_SCORING,
    # Trends tab (Agent 2)
    record_elo_snapshot, load_elo_history, load_community_elo_for_league,
    load_user_cross_league_exposure,
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
)
from . import trade_service as _trade_service_mod
from . import ranking_service as _ranking_service_mod
from . import trends_service as _trends_service_mod
from .feature_flags import FLAGS, is_enabled, flags_dict, reload as reload_flags
from .trade_service import TradeService, League, LeagueMember

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

# Load DynastyProcess consensus values as Elo seed
scoring  = os.environ.get("SCORING_FORMAT", "1qb")
elo_map  = load_consensus_elo(scoring=scoring)
seed     = seed_elo_for_players(DEMO_PLAYERS, elo_map) if elo_map else {}

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
PLAYERS_CACHE_FILE = CACHE_DIR / ".sleeper_players_cache.json"
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


def _sleeper_get(url: str, timeout: int = 15) -> dict | list:
    """Fetch JSON from Sleeper API with full request/response logging."""
    global _SSL_CTX  # may be replaced on first SSL failure
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
        return json.loads(raw)
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
g_universal_by_format: dict[str, dict] = {}             # {fmt: {'players': [...], 'seed': {...}}}

# Backwards-compat aliases (default format). These reference the same lists
# as g_universal_by_format['1qb_ppr'] after _ensure_universal_pools runs.
dp_values: dict[str, float] = {}
g_universal_players: list[Player] = []
g_universal_seed: dict[str, float] = {}


def build_universal_pool(
    sleeper_cache: dict | None = None,
    dp_elo: dict[str, float] | None = None,
    dp_vals: dict[str, float] | None = None,
) -> tuple[list[Player], dict[str, float]]:
    """
    Build the universal ranking pool: every Sleeper player that has a
    DynastyProcess value > 0.

    Returns (players, seed_ratings) where seed_ratings maps player.id → elo.
    """
    if not sleeper_cache or not dp_vals:
        return [], {}

    players: list[Player] = []
    seeds: dict[str, float] = {}
    seen_ids: set[str] = set()

    # Try to load enriched DB records first
    try:
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
    # against players.  Elo seeds are calibrated to match typical dynasty values.
    _PICK_SEEDS = {
        # (round, tier): elo_seed — calibrated to dynasty trade value expectations
        (1, "Early"):  1720,   # ~top-3 pick: elite rookie prospect
        (1, "Mid"):    1650,   # ~mid-1st: solid first-round value
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
    _ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
    # Distribute generic picks across position tabs so they mix in with players
    _PICK_POS = {1: "RB", 2: "WR", 3: "TE", 4: "QB"}

    for (rnd, tier), seed_elo in _PICK_SEEDS.items():
        ordinal = _ORDINALS[rnd]
        pick_id = f"generic_pick_{rnd}_{tier.lower()}"
        label   = f"{tier} {ordinal} Round Pick"
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
             len(players) - len(_PICK_SEEDS), len(_PICK_SEEDS))
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
    for fmt in DL_SCORING_FORMATS:
        if fmt in g_universal_by_format:
            continue
        # Load per-format DP data
        if fmt not in dp_values_by_format:
            dp_values_by_format[fmt] = load_consensus_values(scoring=fmt)
        if fmt not in dp_elo_by_format:
            dp_elo_by_format[fmt] = load_consensus_elo(scoring=fmt)

        players, seed = build_universal_pool(
            sleeper_cache=cache,
            dp_elo=dp_elo_by_format[fmt],
            dp_vals=dp_values_by_format[fmt],
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


def _active_format(sess: dict) -> str:
    """Return the format that `_require_session` resolved for this request."""
    return sess.get("_effective_format") or sess.get("active_format") or "1qb_ppr"


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
    try:
        touch_user_activity(user_id, **info)
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


def _run_trade_job(
    job_id: str,
    sess_token: str,
    league_id: str,
    fairness_threshold: float,
    pinned_give: list,
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
        g_league       = sess["league"]
        g_user_roster  = sess["user_roster"]
        g_players      = sess["players"]
        if not (service and trade_service and g_league):
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

        # Update outlook on the job for cache freshness checks
        with _trade_jobs_lock:
            j = _trade_jobs.get(job_id)
            if j is not None:
                j["outlook_value"] = outlook_value

        players_dict = {p.id: p for p in g_players}
        progress_cb  = _make_progress_cb(job_id, players_dict, real_user_ids, outlook_value)

        trade_service.generate_trades(
            user_id              = g_user_id,
            user_elo             = elo_map_rt,
            user_roster          = g_user_roster,
            league_id            = league_id,
            seed_elo             = seed_map,
            fairness_threshold   = fairness_threshold,
            acquire_positions    = acquire_positions,
            trade_away_positions = trade_away_positions,
            pinned_give_players  = pinned_give or None,
            scoring_format       = active_format,
            on_opponent_done     = progress_cb,
        )

        # Mark complete. Final card snapshot was already published by the
        # last on_opponent_done invocation.
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
    opponents_total: int | None = None,
) -> str:
    """Register a new job in _trade_jobs and start its worker thread.
    Returns the job_id. Caller is responsible for any pre-existing-job
    deduplication; this always creates a fresh one."""
    job_id = uuid.uuid4().hex
    is_pinned = bool(pinned_give)
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
        args=(job_id, sess_token, league_id, fairness_threshold, pinned_give or []),
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
        # Agent A1 — swipe.qc_compliments: occasionally (~1/15) substitute
        # a lopsided "QC" trio so we can reward the user when they match the
        # community consensus. Flag-off behavior is unchanged.
        qc_trio_obj = None
        qc_expected_order: list = []
        if is_enabled("swipe.qc_compliments"):
            try:
                import random as _rand
                if _rand.random() < (1.0 / 15.0):
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

        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


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
def get_me_streak():
    """GET /api/me/streak → {current, longest, last_rank_local_date}.

    The streak counter advances inside record_event() whenever a rank-class
    event fires (see _RANK_STREAK_EVENTS). This endpoint just reads the
    denormalized columns on `users`.
    """
    sess = _require_session()
    return jsonify(get_user_streak(sess["user_id"]))


@app.route("/api/rank3", methods=["POST"])
def post_rank3():
    """POST /api/rank3  {ranked: [id1, id2, id3]}  →  updated progress"""
    sess = _require_session()
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
        return jsonify({"error": str(e)}), 400


@app.route("/api/rankings")
def get_rankings():
    """GET /api/rankings?position=RB  →  ordered player list"""
    sess = _require_session()
    sess["last_active"] = time.time()
    service = sess["service"]
    position = request.args.get("position") or None
    try:
        rank_set = service.get_rankings(position=position)
        return jsonify({
            "position":          rank_set.position,
            "rankings":          [ranked_player_to_dict(rp) for rp in rank_set.rankings],
            "interaction_count": rank_set.interaction_count,
            "threshold":         rank_set.threshold,
            "threshold_met":     rank_set.threshold_met,
            "version":           rank_set.version,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/progress")
def get_progress():
    """GET /api/progress?position=RB  →  completion status"""
    sess = _require_session()
    sess["last_active"] = time.time()
    service = sess["service"]
    position = request.args.get("position") or None
    try:
        return jsonify(service.get_progress(position=position))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/rankings/progress")
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
    elif ranking_method == "tiers":
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
        _unlock_res = {"inserted": False, "was_first": False}
        try:
            _unlock_res = mark_format_unlocked(g_user_id, fmt) or _unlock_res
        except Exception as db_err:
            log.warning("mark_format_unlocked failed: %s", db_err)

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
def set_ranking_method_route():
    """POST /api/ranking-method {method: 'trio'|'manual'|'tiers'}"""
    sess = _require_session()
    g_user_id = sess["user_id"]
    body   = request.get_json(force=True) or {}
    method = body.get("method", "")
    if method not in ("trio", "manual", "tiers"):
        return jsonify({"error": f"Invalid method: {method!r}"}), 400
    try:
        set_ranking_method(g_user_id, method)
        log.info("ranking-method set for %s: %s", g_user_id, method)
        return jsonify({"ok": True, "method": method})
    except Exception as e:
        log.error("set ranking-method error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/scoring/switch", methods=["POST"])
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
        "tiers": ["elite","starter","solid","depth","bench"],   # display order
        "config": {
          "1qb_ppr": {
            "QB": { "elite": {"min": 1600, "max": 1680}, ... },
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
def copy_tiers_from_format_route():
    """POST /api/tiers/copy-from-format {from_format: '1qb_ppr'}

    Copy the user's tier ASSIGNMENTS (tier label + within-tier rank) from
    one scoring format to the active scoring format. The raw ELO values
    differ between formats because the bands differ — copying ELOs
    directly would re-bucket players incorrectly. So we:

      1) Read source overrides
      2) For each pid, determine which tier it sits in under the SOURCE
         format using tier_for_elo(elo, position, source_format).
      3) Group by (position, tier) and sort each group by source ELO desc
         (this preserves within-tier rank — Josh Allen at QB1 Elite stays
         at QB1 Elite).
      4) For each position, call to_svc.apply_tiers(position, tiers,
         scoring_format=to_format) — which writes new override ELOs in
         the TARGET format's band.
      5) Wholesale-replace the target's _elo_overrides dict (i.e. clear
         first) so leftover overrides not present in the source aren't
         retained — the user asked to "copy", which implies overwrite.
      6) Persist + mark all touched positions as saved + republish to
         member_rankings.

    Body:
      from_format: '1qb_ppr' or 'sf_tep' — which format to copy FROM.
      The TO format is the user's currently active format.

    Response:
      { ok: true, from_format, to_format, position_counts: {QB: N, ...},
        total: N }
    """
    sess = _require_session()
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

    # Group by (position, tier_in_source_format), sorted by source ELO desc.
    # The sort preserves within-tier rank — top of source-Elite ends up at
    # top of target-Elite, etc.
    #
    # CRITICAL: iterate every player's EFFECTIVE rendered ELO via
    # get_rankings(), NOT just from_svc._elo_overrides. The override dict
    # only contains players the user has EXPLICITLY tier-saved or
    # manual-reordered. Players whose default-DP seed ELO happens to land
    # inside a tier band ALSO render in that tier on the page (per
    # autoAssignTiers) — but they don't have an explicit override.
    #
    # Real bug example: Kyler Murray's seed ELO in 1QB PPR is 1227.2,
    # which falls in the 1QB QB depth band [1200, 1330], so the page
    # renders him at "Depth QB20." But he has no override entry. The
    # previous version of this code iterated from_overrides only, so
    # Kyler was silently skipped during the copy. After the wholesale-
    # clear of the target's overrides, he had no SF TEP override either,
    # fell back to his SF TEP seed (~1300), and that seed landed in the
    # SF TEP bench band [1200, 1330] → he showed up as "Bench QB1" in
    # the target view, dropping a full tier from where he was supposed
    # to be. With get_rankings() iteration we capture every visibly-
    # tiered player, override or not.
    grouped: dict[tuple[str, str], list[tuple[str, float]]] = {}
    seen_anything = False
    for position in ("QB", "RB", "WR", "TE"):
        try:
            rank_set = from_svc.get_rankings(position=position)
        except Exception as e:
            log.warning("copy-from-format: get_rankings(%s) failed: %s", position, e)
            continue
        for rp in rank_set.rankings:
            seen_anything = True
            elo = rp.elo
            if elo is None:
                continue
            tier = RankingService.tier_for_elo(elo, position, from_format)
            if not tier:
                continue
            grouped.setdefault((position, tier), []).append((rp.player.id, float(elo)))

    if not seen_anything:
        return jsonify({
            "ok": False,
            "error": f"No data to copy from {from_format}",
        }), 400

    for key in grouped:
        grouped[key].sort(key=lambda pe: -pe[1])  # ELO desc

    # Build per-position {tier_name: [pids in rank order]} dicts.
    by_position: dict[str, dict[str, list[str]]] = {}
    for (position, tier), pid_elo_list in grouped.items():
        by_position.setdefault(position, {})[tier] = [pid for pid, _ in pid_elo_list]

    # Wholesale replace: clear target overrides FIRST. The apply_tiers calls
    # below then rewrite each position's slice fresh, in the target format's
    # bands. Any pre-existing target override for a pid not in the source
    # is dropped — that's what "copy" means here.
    to_svc._elo_overrides = {}

    for position, tiers in by_position.items():
        to_svc.apply_tiers(
            position=position,
            tiers=tiers,
            scoring_format=to_format,
        )

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

    position_counts = {pos: sum(len(pids) for pids in tiers.values())
                       for pos, tiers in by_position.items()}
    log.info("tiers/copy %s → %s for %s — copied %d overrides across %d positions",
             from_format, to_format, g_user_id,
             sum(position_counts.values()), len(position_counts))
    return jsonify({
        "ok":              True,
        "from_format":     from_format,
        "to_format":       to_format,
        "position_counts": position_counts,
        "total":           sum(position_counts.values()),
    })


@app.route("/api/tiers/save", methods=["POST"])
def save_tiers_route():
    """POST /api/tiers/save {position: 'RB', tiers: {elite: [...ids], ...}, cleared_pids: [...]}

    Converts tier assignments into ELO overrides and marks the position as saved.

    `cleared_pids` (optional): list of pids the user explicitly removed
    from all tiers (× button → back to pool). Their override is deleted
    so they don't snap back to a previous tier on the next refresh.
    """
    sess = _require_session()
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
        return jsonify({"error": str(e)}), 500


@app.route("/api/tiers/status")
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
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 400

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

    sess = _require_session()
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
def reset():
    """POST /api/reset  {position: "RB"}"""
    sess = _require_session()
    sess["last_active"] = time.time()
    service = sess["service"]
    body     = request.get_json(force=True) or {}
    position = body.get("position") or None
    return jsonify(service.reset(position=position))


@app.route("/api/rankings/reorder", methods=["POST"])
def reorder_rankings():
    """POST /api/rankings/reorder {position, ordered_ids}

    Apply a manual reorder to the user's rankings.  The ordered_ids list
    represents the user's desired ranking from best (index 0) to worst.
    ELO values are overridden to match the desired order.
    """
    sess = _require_session()
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
        return jsonify({"error": str(e)}), 400


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# Player DB Routes
# ---------------------------------------------------------------------------

@app.route("/api/players")
def get_players_route():
    """
    GET /api/players?position=RB
    Returns all synced players from the DB, optionally filtered by position.
    Each record includes all extended attributes: depth chart, injury status,
    age, years_exp, height/weight, college, search_rank, ADP.
    """
    position = request.args.get("position") or None
    try:
        players = load_players(position=position)
        return jsonify(players)
    except Exception as e:
        log.error("get_players error: %s", e)
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@app.route("/api/league/picks")
def get_league_picks():
    """
    GET /api/league/picks?league_id=...
    Returns all draft pick assets currently held by the logged-in user in
    the specified league, along with the full league pick state so the
    frontend can show which picks opponents hold.
    """
    sess = _require_session()
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
        return jsonify({"error": str(e)}), 500


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
        "target_username":   card.target_username,
        "give":              [p(pid) for pid in card.give_player_ids],
        "receive":           [p(pid) for pid in card.receive_player_ids],
        "mismatch_score":    card.mismatch_score,
        "composite_score":   card.composite_score,
        "decision":          card.decision,
        "expires_at":        card.expires_at,
    }
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
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    if not (g_user_id and g_league):
        return jsonify({"error": "session missing user/league"}), 400

    body               = request.get_json(force=True) or {}
    league_id          = body.get("league_id") or g_league.league_id
    pinned_give        = body.get("pinned_give_players") or []
    # Default to 50% when pinned players are selected (wide net), 75% otherwise
    default_fairness   = 0.50 if pinned_give else 0.75
    fairness_threshold = float(body.get("fairness_threshold", default_fairness))
    fmt                = _active_format(sess)

    # Read current outlook for cache-freshness comparison. The actual job
    # worker reads it again; this is just for the cache hit decision.
    try:
        prefs = load_league_preference(user_id=g_user_id, league_id=league_id)
        outlook_value = (prefs or {}).get("team_outlook")
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
        existing_id = _trade_jobs_by_key.get(key) if not pinned_give else None
        existing    = _trade_jobs.get(existing_id) if existing_id else None

        if existing and not pinned_give:
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
        opponents_total    = opponents_total,
    )
    with _trade_jobs_lock:
        snapshot = _trade_job_public_view(_trade_jobs[job_id])
    return jsonify(snapshot)


@app.route("/api/trades/status")
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
def get_trades():
    """GET /api/trades?league_id=...  →  pending trade cards"""
    sess = _require_session()
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


@app.route("/api/trades/swipe", methods=["POST"])
def swipe_trade():
    """POST /api/trades/swipe  {trade_id, decision: 'like'|'pass'}"""
    sess = _require_session()
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
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/trades/liked")
def get_liked_trades():
    """GET /api/trades/liked  →  trades the user has liked"""
    sess = _require_session()
    sess["last_active"] = time.time()
    trade_service = sess["trade_svc"]
    g_user_id     = sess["user_id"]
    g_players     = sess["players"]
    cards        = trade_service.get_liked_trades(user_id=g_user_id)
    players_dict = {p.id: p for p in g_players}
    return jsonify([trade_card_to_dict(c, players_dict) for c in cards])


@app.route("/api/trades/matches")
def get_trade_matches():
    """
    GET /api/trades/matches  →  all trade matches for the current user
    (all statuses: pending, accepted, declined), enriched with player names
    and disposition state from the caller's perspective.
    """
    sess = _require_session()
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
                    # Multiple users may have a row per league — first wins;
                    # the names are the same regardless of which user owns it.
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
        for m in matches:
            give_ids    = m.get("my_give")    or []
            receive_ids = m.get("my_receive") or []
            enriched.append({
                **m,
                "league_name":      league_name_by_id.get(m["league_id"], ""),
                "my_give_names":    [player_name_by_id.get(pid, pid) for pid in give_ids],
                "my_receive_names": [player_name_by_id.get(pid, pid) for pid in receive_ids],
            })
        return jsonify(enriched)
    except Exception as e:
        log.warning("get_trade_matches_all error: %s", e)
        return jsonify([])


@app.route("/api/trades/matches/<int:match_id>/disposition", methods=["POST"])
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
    service   = sess["service"]
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    g_players = sess["players"]
    body     = request.get_json(force=True) or {}
    decision = body.get("decision")

    if decision not in ("accept", "decline"):
        return jsonify({"error": "decision must be 'accept' or 'decline'"}), 400

    if not g_user_id or not g_league:
        return jsonify({"error": "session not initialised"}), 400

    try:
        result = record_match_disposition(
            match_id = match_id,
            user_id  = g_user_id,
            decision = decision,
        )

        if result["status"] == "not_found":
            return jsonify({"error": "match not found"}), 404
        if result["status"] == "already_decided":
            return jsonify({"error": "you have already recorded a decision for this match"}), 409

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
                # 1. Apply to in-memory service for the current user
                if sig["user_id"] == g_user_id:
                    service.record_disposition_signal(
                        winner_ids = sig["winner_ids"],
                        loser_ids  = sig["loser_ids"],
                        k_factor   = sig["k_factor"],
                    )
                # 2. Persist swipes for both users (non-current user gets
                #    them on next session_init via replay_from_db)
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

                # Get player names from the current user's match perspective
                _raw_ms   = load_matches(user_id=g_user_id, league_id=g_league.league_id
                                         if g_league else "")
                _this_m   = next((m for m in _raw_ms if m["id"] == match_id), None)
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

        # Return refreshed match list so the frontend can re-render
        league_id    = g_league.league_id
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
        return jsonify({"ok": True, "both_decided": result["both_decided"],
                        "outcome": result["outcome"], "matches": enriched})

    except Exception as e:
        log.error("disposition_trade_match error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/leagues")
def get_leagues():
    """GET /api/leagues  →  current active league"""
    sess = _require_session()
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
    """GET /api/portfolio → aggregate exposure across every league this user
    has synced. Returns {players: [...]} sorted by exposure desc."""
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    try:
        players = load_user_cross_league_exposure(g_user_id)
        return jsonify({"players": players})
    except Exception as e:
        log.error("get_portfolio error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/rankings/submit", methods=["POST"])
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
    sess = _require_session()
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
        return jsonify({"error": str(e)}), 500


@app.route("/api/league/preferences", methods=["GET"])
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
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    league_id = request.args.get("league_id") or g_league.league_id
    user_id   = request.args.get("user_id")   or g_user_id
    try:
        prefs = load_league_preference(user_id=user_id, league_id=league_id)
        if prefs is None:
            return jsonify({
                "team_outlook":          None,
                "acquire_positions":     [],
                "trade_away_positions":  [],
            })
        return jsonify(prefs)
    except Exception as e:
        log.error("get_league_preferences error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/league/preferences", methods=["POST"])
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
    sess = _require_session()
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
        return jsonify({"error": str(e)}), 500


@app.route("/api/league/summary")
def league_summary_route():
    """GET /api/league/summary?league_id=XXX

    Returns the roll-up shown on the League Summary page:
      - matches_pending / matches_accepted (current user's)
      - leaguemates_total / _joined / _unlocked_1qb / _unlocked_sf
      - default_scoring, league_name
    """
    sess = _require_session()
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
        return jsonify({"error": str(e)}), 500


@app.route("/api/league/scoring", methods=["POST"])
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
        return jsonify({"error": str(e)}), 500


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
    sess = _require_session()
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
        return jsonify({"error": str(e)}), 500


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
        members = load_league_member_unlock_states(
            league_id       = league_id,
            exclude_user_id = g_user_id,
        )
        return jsonify({"members": members})
    except Exception as e:
        log.error("league/member-unlock-states error: %s", e)
        return jsonify({"error": str(e)}), 500


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
        # the join determination.
        rows = load_league_member_unlock_states(
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
    sess = _require_session()
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
        return jsonify({"error": str(e)}), 500


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
    sess = _require_session()
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
        return jsonify({"error": str(e)}), 500


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
    if username.startswith("test_user_fp_"):
        log.info("  🧪 test user bypass for %r", username)
        return jsonify({
            "user_id": username,
            "display_name": username,
            "username": username,
            "avatar": None,
            "is_bot": False,
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
        log.warning("  HTTPError %s — user not found", e.code)
        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        log.error("  exception: %s\n%s", e, traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/sleeper/leagues/<user_id>")
def sleeper_leagues(user_id):
    """Fetch NFL leagues for a Sleeper user (2026 season) + local DB leagues."""
    url = f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/2026"
    log.info("=== /api/sleeper/leagues  user_id=%r", user_id)
    try:
        sleeper_data = _sleeper_get(url) or []
    except Exception as e:
        log.error("  leagues error: %s", e)
        sleeper_data = []

    # Append any locally-stored leagues where this user is a member
    try:
        local = load_local_leagues_for_user(user_id)
        if local:
            log.info("  appending %d local league(s) for user %s", len(local), user_id)
        sleeper_data = list(sleeper_data) + local
    except Exception as e:
        log.warning("  local leagues load failed: %s", e)

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
    except Exception as e:
        log.error("  rosters error: %s\n%s", e, traceback.format_exc())
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@app.route("/api/debug/log")
def debug_log():
    """GET /api/debug/log?n=100  →  last N log entries as JSON"""
    try:
        n    = min(int(request.args.get("n", 100)), 200)
        entries = list(_LOG_BUFFER)[-n:]
        return jsonify({"entries": entries, "total_buffered": len(_LOG_BUFFER)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Admin: model config (runtime-tunable multipliers)
# ---------------------------------------------------------------------------

@app.route("/api/admin/config", methods=["GET"])
def admin_config_list():
    """
    GET /api/admin/config
    Returns all model_config rows: [{key, value, description}, ...]
    sorted alphabetically by key.
    """
    try:
        rows = list_config()
        return jsonify(rows)
    except Exception as e:
        log.exception("admin_config_list failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/config/<key>", methods=["PUT"])
def admin_config_update(key: str):
    """
    PUT /api/admin/config/<key>
    Body: {"value": <float>}
    Updates the config value, reloads both service modules, returns {key, value}.
    """
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
        return jsonify({"error": str(e)}), 500


@app.route("/api/sleeper/players")
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
        return jsonify({"error": str(e)}), 500


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
    members: list[LeagueMember] = []
    for opp in opponent_rosters:
        opp_id    = str(opp.get("user_id", f"opp_{len(members)+1}"))
        opp_name  = opp.get("username", f"Opponent {len(members)+1}")
        opp_ids   = [str(x) for x in opp.get("player_ids", []) if str(x) in players_dict]
        if not opp_ids:
            continue
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
            members.append(LeagueMember(
                user_id     = dbm_uid,
                username    = dbm.get("username") or dbm.get("display_name") or dbm_uid,
                roster      = dbm_ids,
                elo_ratings = _biased_elo_random(dbm_ids, ranking_seed),
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
                user_id     = f"opp_{i+1}",
                username    = opp_name,
                roster      = opp_ids,
                elo_ratings = _biased_elo_random(opp_ids, ranking_seed),
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
        new_services: dict = {}
        from .database import SCORING_FORMATS as DB_SCORING_FORMATS
        for fmt in DB_SCORING_FORMATS:
            fmt_pool, fmt_seed = _get_universal_pool(fmt)
            svc = RankingService(
                players           = fmt_pool,
                matchup_generator = matchup_gen,
                seed_ratings      = fmt_seed,
            )
            svc._user_id = user_id

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
            existing_sess.update(session_payload)
        else:
            token = secrets.token_urlsafe(32)
            _sessions[token] = session_payload

    # ── Persist user + league snapshot ──────────────────────────────────
    # Agent 4 addition: capture INSERT-vs-UPDATE state BEFORE upsert_user runs
    # so we can emit a one-time referral-receipt notification on the referred
    # user's first session. upsert_user only applies `invited_by` on INSERT,
    # so this is also our only window to attribute the join.
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
        log.info("  ✅ user + league upserted in DB")

        # User-event log: signup on first session, app_open thereafter.
        # Fires after upsert_user so the row is guaranteed to exist for the
        # FK-style update inside record_event().
        _ev_info = getattr(g, "device_info", {}) or {}
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

        # ── Agent 4: referral receipt notification ─────────────────────────
        # Fires exactly once: on the NEW user's very first session_init when
        # they arrived with an invited_by attribution. Posts a bell
        # notification to the referrer resolved-by-username.
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

        # ── league_member_joined: ping existing leaguemates on the app ──
        # Fires once per (existing leaguemate, joining user) pair on the
        # joining user's first session. Doesn't ping the joiner. Capped
        # implicitly by the dedup_key — a returning user re-init won't
        # re-fire because _is_new_user is False.
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

        # ── Auto-detect league scoring format from Sleeper metadata ─────────
        # Fires on every session/init for leagues without a format on file.
        # Retrying on each init (when existing_fmt is falsy) self-heals
        # leagues whose first sync hit a Sleeper API flake — subsequent
        # logins keep attempting until detection succeeds. Once stored, the
        # Sleeper call is skipped.
        #
        # AUDIT (2026-04-16): session/init is the only path that calls
        # upsert_league — no other league-sync code path exists in server.py,
        # so guarding auto-detect here covers every new + returning league
        # connection. If additional sync paths are introduced, they must
        # also invoke _detect_scoring_format_from_meta + set_league_scoring.
        # Re-detect scoring format on EVERY session_init (not just when
        # unset) so any previously-miscategorized league self-heals. Cost
        # is one cached Sleeper API call per init; writes only happen when
        # the detected value differs from what's on file.
        try:
            existing_fmt = None
            try:
                existing_fmt = get_league_scoring(league_id)
            except Exception:
                pass
            meta = _fetch_sleeper_league_meta(league_id)
            if meta:
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

    # ── Persist full league membership roster ────────────────────────────
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
    except Exception as db_err:
        log.warning("  league_members upsert failed (continuing): %s", db_err)

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

    return jsonify({
        "ok":           True,
        "token":        token,
        "player_count": real_player_count,
        "pick_count":   generic_pick_count,
        "user_roster":  [player_to_dict(players_dict[pid]) for pid in new_user_roster if pid in players_dict],
        "league_id":    league_id,
        "opponents":    len(members),
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
def list_notifications():
    """
    GET /api/notifications?user_id=<uid>

    Returns unread + the last 20 read notifications for the given user,
    sorted newest-first.  The user_id is accepted as a query param (and
    cross-checked against the current session user) so the frontend can
    pass it without extra auth plumbing.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    uid = request.args.get("user_id") or g_user_id
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
def read_notifications():
    """
    POST /api/notifications/read  { "user_id": "...", "ids": [1, 2, 3] }

    Marks the specified notification IDs as read for the given user.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    body    = request.get_json(force=True) or {}
    uid     = body.get("user_id") or g_user_id
    ids     = body.get("ids") or []
    if not uid:
        return jsonify({"error": "user_id required"}), 400
    try:
        updated = mark_notifications_read(uid, notification_ids=ids if ids else None)
        return jsonify({"ok": True, "updated": updated})
    except Exception as e:
        log.error("read_notifications error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/notifications/read-all", methods=["POST"])
def read_all_notifications():
    """
    POST /api/notifications/read-all  { "user_id": "..." }

    Marks ALL unread notifications as read for the given user.
    """
    sess = _require_session()
    sess["last_active"] = time.time()
    g_user_id = sess["user_id"]
    body = request.get_json(force=True) or {}
    uid  = body.get("user_id") or g_user_id
    if not uid:
        return jsonify({"error": "user_id required"}), 400
    try:
        updated = mark_notifications_read(uid, notification_ids=None)
        return jsonify({"ok": True, "updated": updated})
    except Exception as e:
        log.error("read_all_notifications error: %s", e)
        return jsonify({"error": str(e)}), 500


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
    if sent != _CRON_SECRET:
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
def trends_risers_fallers_route():
    """
    GET /api/trends/risers-fallers?window_days=30&top_n=5
    Returns the user's ELO risers + fallers over the requested window,
    grouped by position.  Computed from the `elo_history` table written on
    every ranking submit.
    """
    sess = _require_session()
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
def trends_contrarian_route():
    """
    GET /api/trends/contrarian?league_id=...
    Compares the user's ELO to the community consensus in the league for
    the active scoring format.  Returns a single 0-100 contrarian score
    plus Top-5-above / Top-5-below splits.  Falls back to
    {has_baseline: false} when fewer than 3 other users have rankings.
    """
    sess = _require_session()
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
def trends_consensus_gap_route():
    """
    GET /api/trends/consensus-gap?league_id=...&top_n=5
    Per-player gap between the user's ELO and the community ELO (for
    non-roster picks: vs the specific owner's ELO).  Returns
    "easiest_sells" (own roster, over-valued vs market) and
    "easiest_buys" (not on roster, over-valued vs owner).
    """
    sess = _require_session()
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
    No auth check for v1 — this just re-reads files/env the server
    already has access to, so there's no privileged data exposed.
    """
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
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Pre-load Sleeper player cache from disk if available
    _load_sleeper_cache()

    # Sync player cache to DB (no-op if data is fresh, runs in ~1 s)
    _maybe_sync_players()

    print("\n🏈 Fantasy Trade Finder — Dynasty Rankings")
    print("   Open http://127.0.0.1:5000 in your browser\n")
    app.run(debug=True, port=5000)
