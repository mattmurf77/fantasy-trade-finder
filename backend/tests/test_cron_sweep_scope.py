"""What the cron sweeps are allowed to touch.

Two scope rules, both added because the sweeps grew linearly with every
league ever synced rather than with the leagues anyone still opens:

  1. ACTIVE-LEAGUE FILTER — `load_league_ids_for_draft_status_refresh`
     (hourly draft-status) and `load_history_sweep_leagues` (weekly roster
     snapshot) only return leagues whose `leagues.updated_at` falls inside
     ACTIVE_LEAGUE_WINDOW_DAYS. `updated_at` is stamped by `upsert_league`,
     which every session_init runs for the league it is opening. The filter
     is disableable (`active_within_days=None`) so the manual admin lever
     still reaches everything.

  2. SEASON GATE — a `not_drafted` league is re-probed every 3 h while
     rookie drafts can plausibly be happening and only daily outside that
     window. `drafted` / `unknown` and the explicit force path are untouched.

The clock is pinned by passing `now` into `_draft_status_is_fresh` (which
already accepted it) rather than freezing globally — freezegun is not a
dependency of this repo.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, insert
from unittest.mock import patch

import backend.database as db_module
import backend.server as server
from backend.database import leagues_table, metadata

LEAGUE_ACTIVE  = "league_active"
LEAGUE_DORMANT = "league_dormant"


@pytest.fixture()
def mem_db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with patch.object(db_module, "engine", engine):
        yield engine


def _days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _seed_two_leagues(engine):
    """One league opened yesterday, one untouched for a year."""
    with engine.begin() as conn:
        conn.execute(insert(leagues_table), [
            {"sleeper_league_id": LEAGUE_ACTIVE,  "user_id": "u1",
             "platform": "sleeper", "updated_at": _days_ago(1)},
            {"sleeper_league_id": LEAGUE_DORMANT, "user_id": "u1",
             "platform": "sleeper", "updated_at": _days_ago(365)},
        ])


# ── 1. active-league filter ────────────────────────────────────────────────

def test_draft_status_queue_skips_a_league_nobody_opens(mem_db):
    """SABOTAGE: drop the `updated_at >= cutoff` predicate and the dormant
    league comes back into the hourly sweep, at three Sleeper reads a pop."""
    _seed_two_leagues(mem_db)
    assert db_module.load_league_ids_for_draft_status_refresh() == [
        LEAGUE_ACTIVE]


def test_history_sweep_worklist_skips_a_league_nobody_opens(mem_db):
    _seed_two_leagues(mem_db)
    out = db_module.load_history_sweep_leagues("2026-W33")
    assert [o["league_id"] for o in out] == [LEAGUE_ACTIVE]


def test_a_league_on_the_window_boundary_is_still_active(mem_db):
    """The window is `ACTIVE_LEAGUE_WINDOW_DAYS` days, inclusive-ish: a
    league opened just inside it is swept, one just outside is not."""
    edge = db_module.ACTIVE_LEAGUE_WINDOW_DAYS
    with mem_db.begin() as conn:
        conn.execute(insert(leagues_table), [
            {"sleeper_league_id": "just_in",  "user_id": "u1",
             "updated_at": _days_ago(edge - 1)},
            {"sleeper_league_id": "just_out", "user_id": "u1",
             "updated_at": _days_ago(edge + 1)},
        ])
    assert db_module.load_league_ids_for_draft_status_refresh() == ["just_in"]


def test_both_loaders_have_an_escape_hatch(mem_db):
    """`active_within_days=None` sweeps everything — this is what the manual
    POST /api/cron/roster-snapshot lever passes, so an operator forcing a
    sweep is never silently limited to active leagues."""
    _seed_two_leagues(mem_db)
    assert sorted(db_module.load_league_ids_for_draft_status_refresh(
        active_within_days=None)) == sorted([LEAGUE_ACTIVE, LEAGUE_DORMANT])
    out = db_module.load_history_sweep_leagues("2026-W33",
                                               active_within_days=None)
    assert sorted(o["league_id"] for o in out) == sorted(
        [LEAGUE_ACTIVE, LEAGUE_DORMANT])


def test_the_manual_roster_snapshot_lever_disables_the_filter():
    """Pinned at the call site, not just the loader: the admin route must
    pass the escape hatch through the daemon starter."""
    seen = {}
    with patch.object(server, "_start_roster_snapshot_daemon",
                      lambda now, budget, active_within_days=object():
                          seen.update(active=active_within_days)), \
         patch.object(server, "is_enabled", lambda k: True), \
         patch.object(server, "_require_cron_auth", lambda: None):
        server.app.config["TESTING"] = True
        r = server.app.test_client().post("/api/cron/roster-snapshot")
    assert r.status_code == 200
    assert seen["active"] is None


# ── 2. season gate on the not_drafted TTL ──────────────────────────────────

_IN_WINDOW  = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)   # rookie season
_OUT_WINDOW = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)   # deep offseason


def _ctx(status, now, hours_ago):
    return {"status": status,
            "checked_at": (now - timedelta(hours=hours_ago)).isoformat()}


@pytest.mark.parametrize("now,hours_ago,fresh", [
    # Inside the window the TTL is the historical 3 h.
    (_IN_WINDOW,  2, True),
    (_IN_WINDOW,  4, False),
    # Outside it, the same 4-hour-old verdict is still good — 24 h TTL.
    (_OUT_WINDOW, 4, True),
    (_OUT_WINDOW, 25, False),
])
def test_not_drafted_ttl_is_season_gated(now, hours_ago, fresh):
    """SABOTAGE: delete the `_in_rookie_draft_window` branch and the two
    _OUT_WINDOW rows fail — the December sweep goes back to re-probing every
    undrafted league every 3 h, all winter."""
    assert server._draft_status_is_fresh(
        _ctx("not_drafted", now, hours_ago), now=now) is fresh


@pytest.mark.parametrize("status,hours_ago,fresh", [
    ("drafted", 6, True),
    ("drafted", 13, False),
    ("unknown", 0.5, True),
    ("unknown", 2, False),
])
def test_the_season_gate_touches_only_not_drafted(status, hours_ago, fresh):
    """The live (`drafting`-adjacent) and flake-backoff TTLs are the same
    number in December as in June."""
    assert server._draft_status_is_fresh(
        _ctx(status, _OUT_WINDOW, hours_ago), now=_OUT_WINDOW) is fresh


@pytest.mark.parametrize("when,inside", [
    (datetime(2026, 3, 31, tzinfo=timezone.utc), False),
    (datetime(2026, 4,  1, tzinfo=timezone.utc), True),
    (datetime(2026, 7, 20, tzinfo=timezone.utc), True),
    (datetime(2026, 9, 15, tzinfo=timezone.utc), True),
    (datetime(2026, 9, 16, tzinfo=timezone.utc), False),
    (datetime(2027, 1, 10, tzinfo=timezone.utc), False),
])
def test_the_rookie_draft_window_bounds(when, inside):
    assert server._in_rookie_draft_window(when) is inside
