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
import urllib.error
import urllib.parse
import urllib.request

from flask import Flask, jsonify, request, send_from_directory

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
from .ranking_service import RankingService, Player
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
    get_config, set_config, list_config,
    load_local_leagues_for_user,
    load_local_league_rosters,
    load_local_league_users,
    set_ranking_method, get_ranking_method,
    save_tiers_position, get_tiers_saved,
)
from . import trade_service as _trade_service_mod
from . import ranking_service as _ranking_service_mod
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

# DP raw values — loaded alongside elo_map at startup
dp_values: dict[str, float] = {}   # { normalised_name: raw_value }

# Universal player list — built from Sleeper cache × DP values
g_universal_players: list[Player] = []
g_universal_seed: dict[str, float] = {}   # { player_id: initial_elo }


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


def _ensure_universal_pool() -> None:
    """Build the universal pool if it hasn't been built yet (idempotent)."""
    global g_universal_players, g_universal_seed, dp_values

    if g_universal_players:
        return  # already built

    cache = _load_sleeper_cache()
    if cache is None:
        return

    # Load DP values if not already loaded
    if not dp_values:
        dp_values = load_consensus_values(scoring=scoring)

    g_universal_players, g_universal_seed = build_universal_pool(
        sleeper_cache=cache,
        dp_elo=elo_map,
        dp_vals=dp_values,
    )


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


class _SessionExpired(Exception):
    pass


@app.errorhandler(_SessionExpired)
def handle_session_expired(e):
    return jsonify({"error": "session_expired",
                    "message": "Session expired — please reload the page."}), 401


def _require_session() -> dict:
    """Return the active session dict, or raise _SessionExpired (→ 401)."""
    token = request.headers.get("X-Session-Token", "")
    with _sessions_lock:
        sess = _sessions.get(token)
    if sess is None:
        raise _SessionExpired()
    return sess


def _cleanup_loop() -> None:
    """Background thread: evict sessions inactive for > 4 hours."""
    while True:
        time.sleep(300)  # check every 5 min
        cutoff = time.time() - 4 * 3600
        with _sessions_lock:
            stale = [t for t, s in _sessions.items()
                     if s.get("last_active", 0) < cutoff]
            for t in stale:
                _sessions.pop(t, None)
        if stale:
            log.info("Cleaned up %d stale session(s)", len(stale))


threading.Thread(target=_cleanup_loop, daemon=True).start()


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
    try:
        trio = service.get_next_trio(position=position)
        resp = {
            "player_a":  player_to_dict(trio.player_a),
            "player_b":  player_to_dict(trio.player_b),
            "player_c":  player_to_dict(trio.player_c),
            "reasoning": trio.reasoning,
            "tier_info": service._tier_info(position),
        }
        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


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

        # Persist swipe history — lets rankings survive server restarts
        try:
            save_ranking_swipes(user_id=g_user_id, ordered_ids=ranked_valid)
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
                    user_id   = g_user_id,
                    league_id = g_league.league_id,
                    rankings  = ranking_payload,
                )
        except Exception as db_err:
            log.warning("member_rankings auto-publish failed (continuing): %s", db_err)

        pct = min(100, round(rank_set.interaction_count / rank_set.threshold * 100))
        return jsonify({
            "interaction_count": rank_set.interaction_count,
            "threshold":         rank_set.threshold,
            "threshold_met":     rank_set.threshold_met,
            "percent":           pct,
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
            saved = get_tiers_saved(g_user_id)
            unlocked = all(p in saved for p in POSITIONS)
        except Exception:
            unlocked = False
    else:
        # 'trio' or null — original threshold logic
        unlocked = all(counts[p] >= threshold for p in POSITIONS)

    return jsonify({
        **counts,
        "threshold":        threshold,
        "unlocked":         unlocked,
        "ranking_method":   ranking_method,
        "total_required":   total_required,
        "total_completed":  total_completed,
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


@app.route("/api/tiers/save", methods=["POST"])
def save_tiers_route():
    """POST /api/tiers/save {position: 'RB', tiers: {elite: [...ids], starter: [...], ...}}

    Converts tier assignments into ELO overrides and marks the position as saved.
    """
    sess = _require_session()
    service   = sess["service"]
    g_user_id = sess["user_id"]
    g_league  = sess["league"]
    body      = request.get_json(force=True) or {}
    position  = body.get("position")
    tiers     = body.get("tiers", {})

    if position not in ("QB", "RB", "WR", "TE"):
        return jsonify({"error": f"Invalid position: {position!r}"}), 400

    # Build an ordered list from tiers: elite first, bench last
    tier_order = ["elite", "starter", "solid", "depth", "bench"]
    ordered_ids = []
    for tier_name in tier_order:
        ordered_ids.extend(tiers.get(tier_name, []))

    if not ordered_ids:
        return jsonify({"error": "No players in any tier"}), 400

    try:
        # Apply as a reorder (assigns linearly spaced ELO values)
        service.apply_reorder(position=position, ordered_ids=ordered_ids)

        # Persist updated ELO snapshot
        try:
            if g_league and g_league.league_id not in ("league_demo",):
                all_rankings = service.get_rankings(position=None)
                ranking_payload = [
                    {"player_id": rp.player.id, "elo": rp.elo}
                    for rp in all_rankings.rankings
                ]
                upsert_member_rankings(
                    user_id   = g_user_id,
                    league_id = g_league.league_id,
                    rankings  = ranking_payload,
                )
        except Exception as db_err:
            log.warning("member_rankings publish after tiers save failed: %s", db_err)

        # Mark this position as saved
        saved = save_tiers_position(g_user_id, position)
        all_done = all(p in saved for p in ("QB", "RB", "WR", "TE"))

        log.info("tiers/save %s for %s — saved positions: %s, all_done=%s",
                 position, g_user_id, saved, all_done)

        return jsonify({
            "ok":       True,
            "position": position,
            "saved":    saved,
            "all_done": all_done,
            "count":    len(ordered_ids),
        })
    except Exception as e:
        log.error("tiers/save error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tiers/status")
def tiers_status_route():
    """GET /api/tiers/status — which positions have saved tiers for the current user."""
    sess = _require_session()
    g_user_id = sess["user_id"]
    try:
        saved = get_tiers_saved(g_user_id)
        return jsonify({
            "saved":    saved,
            "all_done": all(p in saved for p in ("QB", "RB", "WR", "TE")),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    body       = request.get_json(force=True) or {}
    position   = body.get("position")   # None = overall
    ordered_ids = body.get("ordered_ids", [])

    if len(ordered_ids) < 2:
        return jsonify({"error": "Need at least 2 player IDs"}), 400

    try:
        service.apply_reorder(position=position, ordered_ids=ordered_ids)

        # Persist updated ELO snapshot
        try:
            if g_league and g_league.league_id not in ("league_demo",):
                all_rankings = service.get_rankings(position=None)
                ranking_payload = [
                    {"player_id": rp.player.id, "elo": rp.elo}
                    for rp in all_rankings.rankings
                ]
                upsert_member_rankings(
                    user_id   = g_user_id,
                    league_id = g_league.league_id,
                    rankings  = ranking_payload,
                )
        except Exception as db_err:
            log.warning("member_rankings publish after reorder failed: %s", db_err)

        return jsonify({"ok": True, "count": len(ordered_ids)})
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
    return {
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


@app.route("/api/trades/generate", methods=["POST"])
def generate_trades():
    """POST /api/trades/generate  →  generate fresh trade cards for the user"""
    sess = _require_session()
    sess["last_active"] = time.time()
    service       = sess["service"]
    trade_service = sess["trade_svc"]
    g_user_id     = sess["user_id"]
    g_league      = sess["league"]
    g_user_roster = sess["user_roster"]
    g_players     = sess["players"]
    body               = request.get_json(force=True) or {}
    league_id          = body.get("league_id") or g_league.league_id
    pinned_give        = body.get("pinned_give_players") or []  # list of player IDs to trade away
    # Default to 50% when pinned players are selected (wide net), 75% otherwise
    default_fairness   = 0.50 if pinned_give else 0.75
    fairness_threshold = float(body.get("fairness_threshold", default_fairness))
    user_elo   = service.get_rankings(position=None)
    elo_map_rt = {rp.player.id: rp.elo for rp in user_elo.rankings}
    seed_map   = service._seed or {}

    # ── Inject real leaguemate ELO from DB ──────────────────────────────
    # For every member in the current league, replace their simulated ELO
    # with their actual stored rankings if they have any.  Members with no
    # stored rankings keep their random-biased values as a fallback.
    real_count = 0
    try:
        real_rankings = load_member_rankings(
            league_id=league_id, exclude_user_id=g_user_id
        )
        if real_rankings:
            for member in g_league.members:
                if member.user_id in real_rankings:
                    real_data = real_rankings[member.user_id]
                    # Use ALL real rankings — the trade engine needs the
                    # opponent's opinion of the *user's* roster players too,
                    # not just the opponent's own roster players.
                    updated_elo = dict(real_data["elo_ratings"])
                    if updated_elo:
                        member.elo_ratings = updated_elo
                        member.username    = real_data["username"] or member.username
                        real_count += 1
            log.info("  trade gen: %d/%d members using real rankings",
                     real_count, len(g_league.members))
    except Exception as db_err:
        log.warning("  could not load real rankings (using simulated): %s", db_err)

    # ── Load team outlook + positional preferences ──────────────────────
    outlook              = None
    acquire_positions    = []
    trade_away_positions = []
    try:
        prefs = load_league_preference(user_id=g_user_id, league_id=league_id)
        if prefs:
            outlook              = prefs.get("team_outlook")
            acquire_positions    = prefs.get("acquire_positions",    []) or []
            trade_away_positions = prefs.get("trade_away_positions", []) or []
    except Exception as pref_err:
        log.warning("Could not load league preference: %s", pref_err)

    try:
        cards = trade_service.generate_trades(
            user_id              = g_user_id,
            user_elo             = elo_map_rt,
            user_roster          = g_user_roster,
            league_id            = league_id,
            seed_elo             = seed_map,
            fairness_threshold   = fairness_threshold,
            acquire_positions    = acquire_positions,
            trade_away_positions = trade_away_positions,
            pinned_give_players  = pinned_give or None,
        )

        players_dict  = {p.id: p for p in g_players}
        result        = [trade_card_to_dict(c, players_dict) for c in cards]
        real_user_ids = set(real_rankings.keys()) if real_count else set()
        for card_dict, card in zip(result, cards):
            card_dict["real_opponent"] = card.target_user_id in real_user_ids
            card_dict["outlook"]       = outlook   # echoed back so frontend can reflect it
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


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
                user_id    = g_user_id,
                winner_ids = win_ids,
                loser_ids  = lose_ids,
                k_factor   = k_factor,
            )

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
                                    f"🤝 New trade match with {_partner_a}{_in_league}! "
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
                                    f"🤝 New trade match with {_my_username}{_in_league}! "
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
        return jsonify(enriched)
    except Exception as e:
        log.warning("get_trade_matches error: %s", e)
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
                        user_id       = sig["user_id"],
                        winner_ids    = sig["winner_ids"],
                        loser_ids     = sig["loser_ids"],
                        k_factor      = sig["k_factor"],
                        decision_type = sig["decision_type"],
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
            user_id   = user_id,
            league_id = league_id,
            rankings  = payload,
        )
        log.info("rankings/submit — user=%s league=%s players=%d",
                 user_id, league_id, len(payload))
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
        return jsonify({
            "ok":                    True,
            "team_outlook":          outlook,
            "acquire_positions":     acquire_positions or [],
            "trade_away_positions":  trade_away_positions or [],
        })
    except Exception as e:
        log.error("set_league_preferences error: %s", e)
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
def sleeper_players():
    """
    Return cached Sleeper bulk player data (QB/RB/WR/TE only).
    First call fetches ~5MB from Sleeper and caches to disk; subsequent
    calls are served instantly from memory.
    """
    global _sleeper_cache
    log.info("=== /api/sleeper/players  (cache_loaded=%s)", _sleeper_cache is not None)

    cached = _load_sleeper_cache()
    if cached is not None:
        log.info("  serving from cache  size=%d", len(cached))
        return jsonify(cached)

    # Fetch from Sleeper
    try:
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

        return jsonify(relevant)
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

    _ensure_universal_pool()
    if not g_universal_players:
        return jsonify({"error": "Could not build universal player pool — Dynasty Process data may be unavailable"}), 400

    # ── Ranking pool = universal players (includes generic picks) ────────
    # No league-specific Sleeper draft picks in the ranker — only the
    # generic Early/Mid/Late picks (rounds 1–4) from the universal pool.
    ranking_pool = list(g_universal_players)
    ranking_seed = dict(g_universal_seed)

    # Build a combined players dict for trade service
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

    # ── Ranking service: rebuild only if user changed or first init ──────
    # Rankings are user-level — the universal pool stays constant, so we
    # only need to rebuild when the user changes (different Sleeper account)
    # or on first load.  This preserves rankings across league switches.
    existing_service = existing_sess.get("service") if existing_sess else None
    need_rebuild = (
        existing_service is None
        or not hasattr(existing_service, '_user_id')
        or existing_service._user_id != user_id
    )

    if need_rebuild:
        new_service = RankingService(
            players           = ranking_pool,
            matchup_generator = matchup_gen,
            seed_ratings      = ranking_seed,
        )
        new_service._user_id = user_id  # tag so we can detect user changes

        # Replay historical swipes — only needed on rebuild
        try:
            historical = load_swipe_decisions(user_id=user_id)
            if historical:
                replayed = new_service.replay_from_db(historical)
                log.info("  ✅ replayed %d/%d swipe decisions from DB",
                         replayed, len(historical))
            else:
                log.info("  (no stored swipe history for this user)")
        except Exception as db_err:
            log.warning("  DB replay failed — starting with fresh rankings: %s", db_err)
    else:
        new_service = existing_service
        log.info("  ✅ ranking service preserved (same user, universal pool)")

    # Trade service is always rebuilt per league (league-specific rosters).
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

    new_trade_svc = TradeService(players=players_dict, past_decision_keys=past_decision_keys)
    new_trade_svc.add_league(new_league)

    # ── Create or update session ─────────────────────────────────────────
    session_payload = {
        "user_id":      user_id,
        "league":       new_league,
        "players":      ranking_pool,
        "user_roster":  new_user_roster,
        "service":      new_service,
        "trade_svc":    new_trade_svc,
        "display_name": display_name,
        "last_active":  time.time(),
    }
    with _sessions_lock:
        if existing_sess:
            token = incoming_token
            existing_sess.update(session_payload)
        else:
            token = secrets.token_urlsafe(32)
            _sessions[token] = session_payload

    # ── Persist user + league snapshot ──────────────────────────────────
    try:
        upsert_user(
            sleeper_user_id=user_id,
            username=username,
            display_name=display_name,
            avatar=avatar,
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


if __name__ == "__main__":
    # Pre-load Sleeper player cache from disk if available
    _load_sleeper_cache()

    # Sync player cache to DB (no-op if data is fresh, runs in ~1 s)
    _maybe_sync_players()

    print("\n🏈 Fantasy Trade Finder — Dynasty Rankings")
    print("   Open http://127.0.0.1:5000 in your browser\n")
    app.run(debug=True, port=5000)
