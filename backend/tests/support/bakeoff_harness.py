"""Deterministic `_run_trade_job` harness for the trade.bakeoff flag-off golden.

Deliberately imports NOTHING from `backend.bakeoff_runner`: the golden it
produces was captured by running this exact file inside a worktree at the
pre-bake-off `origin/main`, where that module does not exist. Keeping the
harness portable is what makes the golden a real capture rather than a
self-consistent assertion.

`trade_intent` (and, on the same rule, `prefs_preload`) is passed through only
when set, so the golden capture (which never sets either) calls
`_run_trade_job` with exactly the argument list it had at the pre-bake-off
SHA.

`run_capture()` drives one complete trade job through the real engine with a
fixed flag configuration and returns a canonical dict — served cards, every
deck_impressions row, and the job's terminal fields — with the volatile bits
(uuids, timestamps, wall-clock ms) removed. Byte-identity of that dict across
the bake-off change IS the flag-off contract.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.server as server
from backend.database import deck_impressions_table, metadata
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

LEAGUE = "league_bakeoff_golden"
ME     = "user_me"
OPP    = "user_opp"
OPP2   = "user_opp2"
TOKEN  = "test-token-bakeoff-golden"
JOB_ID = "job-bakeoff-golden"

#: Volatile per-run values that must not enter the golden.
_VOLATILE_CARD_KEYS = ("trade_id", "impression_id", "expires_at")
_VOLATILE_ROW_KEYS  = ("impression_id", "served_at", "candidate_set_id")

_POOL = [
    # (id, name, position, team, age, elo)
    ("qb1", "QB One",  "QB", "AAA", 26, 1750.0),
    ("rb1", "RB One",  "RB", "AAA", 24, 1700.0),
    ("rb2", "RB Two",  "RB", "BBB", 27, 1520.0),
    ("wr1", "WR One",  "WR", "BBB", 25, 1680.0),
    ("wr2", "WR Two",  "WR", "CCC", 29, 1430.0),
    ("te1", "TE One",  "TE", "CCC", 23, 1560.0),
    ("rb3", "RB Three", "RB", "DDD", 22, 1600.0),
    ("wr3", "WR Three", "WR", "DDD", 28, 1490.0),
]

SEED = {pid: elo for pid, _n, _p, _t, _a, elo in _POOL}
ME_ROSTER   = ["qb1", "rb1", "wr2", "te1"]
OPP_ROSTER  = ["rb2", "wr1"]
OPP2_ROSTER = ["rb3", "wr3"]


def _players():
    return [Player(id=pid, name=name, position=pos, team=team, age=age)
            for pid, name, pos, team, age, _elo in _POOL]


def _opp_board(roster_bias: float):
    """A league-mate's personal board: consensus shifted so divergence exists
    (without it the engine has nothing to trade on)."""
    return {pid: elo + (roster_bias if pid in OPP_ROSTER + OPP2_ROSTER else -roster_bias)
            for pid, _n, _p, _t, _a, elo in _POOL}


def _flag_patches(*, signal_v2=True, thompson=True, diversity=True):
    """One fixed presentation configuration, patched at the helper level so
    the capture never depends on config/features.json drift.

    The GENERATION-side flags read via the FLAGS proxy must be pinned too —
    the proxy resolves through feature_flags.is_enabled at call time, so a
    features.json flip (e.g. trade.outlook_direction, operator-flipped OFF
    2026-08-20) would otherwise silently re-price the golden. Pinned to the
    values in force when flag_off_golden.json was captured."""
    import backend.feature_flags as _ff
    _real_is_enabled = _ff.is_enabled
    _GOLDEN_FLAG_PINS = {"trade.outlook_direction": True}

    def _pinned_is_enabled(key):
        if key in _GOLDEN_FLAG_PINS:
            return _GOLDEN_FLAG_PINS[key]
        return _real_is_enabled(key)

    return [
        patch.object(_ff, "is_enabled", _pinned_is_enabled),
        patch.object(server, "_deck_signal_v2_enabled", lambda: signal_v2),
        patch.object(server, "_thompson_deck_enabled", lambda: thompson),
        patch.object(server, "_deck_thompson_v2_enabled", lambda: False),
        patch.object(server, "_deck_diversity_enabled", lambda: diversity),
        patch.object(server, "_deck_fatigue_enabled", lambda: False),
        patch.object(server, "_deck_taste_enabled", lambda: False),
        patch.object(server, "_deck_value_model_enabled", lambda: False),
        patch.object(server, "_deck_exploration_enabled", lambda: False),
        patch.object(server, "_deck_first_session_enabled", lambda: False),
        patch.object(server, "_suggestion_telemetry_enabled", lambda: False),
        patch.object(server, "_likes_you_enabled", lambda: True),
        patch.object(server, "load_member_rankings", MagicMock(return_value={})),
        patch.object(server, "load_league_preference", MagicMock(return_value=None)),
        patch.object(server, "create_notification", MagicMock()),
        patch.object(server, "_send_typed_push", MagicMock()),
    ]


def _canonical_cards(cards):
    out = []
    for c in cards or []:
        d = {k: v for k, v in c.items() if k not in _VOLATILE_CARD_KEYS}
        out.append(json.loads(json.dumps(d, sort_keys=True, default=str)))
    return out


def _canonical_rows(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            select(deck_impressions_table)
            .order_by(deck_impressions_table.c.card_index)
        ).fetchall()
    out = []
    for r in rows:
        d = {k: v for k, v in dict(r._mapping).items()
             if k not in _VOLATILE_ROW_KEYS}
        out.append(json.loads(json.dumps(d, sort_keys=True, default=str)))
    return out


def run_capture(extra_patches=(), seed_like=True, trade_intent=None,
                prefs_preload=None):
    """Run one full trade job and return the canonical capture dict."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    pool = _players()
    service = RankingService(players=list(pool))
    service._seed = dict(SEED)
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(
        league_id=LEAGUE, name="Bake-off Golden", platform="sleeper",
        members=[
            LeagueMember(user_id=ME,   username="me",   roster=list(ME_ROSTER),
                         elo_ratings={}),
            LeagueMember(user_id=OPP,  username="opp",  roster=list(OPP_ROSTER),
                         elo_ratings=_opp_board(90.0)),
            LeagueMember(user_id=OPP2, username="opp2", roster=list(OPP2_ROSTER),
                         elo_ratings=_opp_board(140.0)),
        ],
    )
    trade_svc.add_league(league)

    sess = {
        "user_id":       ME,
        "league":        league,
        "user_roster":   list(ME_ROSTER),
        "players":       pool,
        "services":      {"1qb_ppr": service},
        "trade_svcs":    {"1qb_ppr": trade_svc},
        "service":       service,
        "trade_svc":     trade_svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }
    job = {
        "job_id": JOB_ID, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
        "started_at": time.monotonic(), "finished_at": None,
        "opponents_done": 0, "opponents_total": 2, "cards": [],
        "error": None, "fairness_threshold": 0.75,
        "outlook_value": None, "is_pinned": False,
    }

    patches = _flag_patches() + list(extra_patches)
    with patch.object(db_module, "engine", engine):
        if seed_like:
            with engine.begin() as conn:
                created = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
                conn.execute(text(
                    "INSERT INTO trade_decisions (user_id, league_id, "
                    "give_player_ids, receive_player_ids, decision, created_at) "
                    "VALUES (:uid, :lid, :give, :recv, 'like', :created)"
                ), {"uid": OPP, "lid": LEAGUE,
                    "give": json.dumps(["rb2"]), "recv": json.dumps(["rb1"]),
                    "created": created})
        stack = []
        try:
            for p in patches:
                p.start()
                stack.append(p)
            with server._sessions_lock:
                server._sessions[TOKEN] = sess
            with server._trade_jobs_lock:
                server._trade_jobs[JOB_ID] = job
            _job_kw = {"trade_intent": trade_intent} if trade_intent else {}
            if prefs_preload is not None:
                _job_kw["prefs_preload"] = prefs_preload
            server._run_trade_job(JOB_ID, TOKEN, LEAGUE, 0.75, [], **_job_kw)
        finally:
            for p in reversed(stack):
                p.stop()
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._trade_jobs_lock:
                server._trade_jobs.pop(JOB_ID, None)
                server._trade_jobs_by_key.pop((ME, LEAGUE, "1qb_ppr"), None)

        capture = {
            "status":      job.get("status"),
            "error":       job.get("error"),
            "card_count":  len(job.get("cards") or []),
            "cards":       _canonical_cards(job.get("cards")),
            "impressions": _canonical_rows(engine),
            "job_keys":    sorted(k for k in job
                                  if k not in ("started_at", "finished_at",
                                               "cards", "gen_ms")),
        }
    return capture, job, engine
