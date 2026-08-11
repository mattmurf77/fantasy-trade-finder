"""P1-7 — every ranking method can unlock, and none unlocks for free.

Spec: docs/plans/audit-p1-remediation/LLD-p1-7.md §5/§9, operator decision
D-P1-10 ("every ranking method must be able to unlock; no method may be a
dead end").

TWO defects, one ladder:

  * A-16, `'anchor'`: the method had NO arm in `get_rankings_progress`, so it
    fell to the trio rule — which requires 10 swipe interactions per position.
    `apply_anchor` writes Elo overrides and never a swipe, so the bar was
    STRUCTURALLY unreachable, not merely hard.

  * A-17, `'manual'`: the arm was `unlocked = True`, unconditionally. Post-P0-1
    that is reached by one drag on Manual Ranks — or one Quick Rank step,
    which routes through the same reorder handler — so a permanent unlock was
    one gesture away.

Both now read the same durable evidence: pool-resident entries in the
persisted board (`users.tier_overrides`), counted by
`RankingService.board_override_count()`.

Everything here is offline: in-memory SQLite, an injected fake ranking
service for the route matrix, a REAL RankingService for the counter unit
tests, and a real Flask test client with a seeded `server._sessions` entry.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.server as server
from backend.database import (
    metadata, users_table, players_table, leagues_table, user_events_table,
    backfill_anchor_unlocked_formats, save_tier_overrides, get_unlocked_formats,
    mark_format_unlocked, save_tiers_position,
)
from backend.ranking_service import (
    Player, RankedPlayer, RankSet, RankingService,
)
from backend.trade_service import League

UID = "u_p17"
LEAGUE_ID = "9920001"
TOKEN = "sess-p17-tok"
SEASON = "2026"
POSITIONS = ("QB", "RB", "WR", "TE")
FMT = "1qb_ppr"
OTHER_FMT = "sf_tep"

# Enough ids to sit either side of the 40 bar.
PIDS = [f"p{i}" for i in range(1, 61)]

ANCHOR_MIN = RankingService.ANCHOR_UNLOCK_MIN
MANUAL_MIN = RankingService.MANUAL_UNLOCK_MIN


def _p(pid, pos="RB"):
    return Player(id=pid, name=f"Player {pid}", position=pos, team="AAA",
                  age=24, years_experience=2, search_rank=int(pid[1:]))


def _pool():
    return [_p(pid) for pid in PIDS]


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

class _FakeService:
    """Serves a fixed board. The LADDER is what is under test, so the ranking
    math is irrelevant — but `board_override_count` and `get_progress` are
    real, mutable counters, because every assertion here is about which of
    them the ladder consults."""

    POSITION_THRESHOLDS = {"QB": 10, "RB": 10, "WR": 10, "TE": 10}

    def __init__(self, players):
        self._players = players
        self._elo_overrides = {}
        self.counts = {p: 0 for p in POSITIONS}

    def _pool(self, position=None):
        return list(self._players)

    def board_override_count(self):
        pool_ids = {p.id for p in self._players}
        return sum(1 for pid in self._elo_overrides if pid in pool_ids)

    def get_rankings(self, position=None):
        return RankSet(
            position=position,
            rankings=[RankedPlayer(p, 1900.0 - 10 * i, 1, 0, i + 1)
                      for i, p in enumerate(self._players)],
            interaction_count=0, threshold=10, threshold_met=False,
            version=1, computed_at="2026-08-11T00:00:00Z",
        )

    def get_progress(self, position=None):
        n = self.counts.get(position, 0) if position else sum(self.counts.values())
        return {"interaction_count": n, "threshold": 10,
                "threshold_met": n >= 10, "position": position}

    def _tier_info(self, position=None):
        return {}


@pytest.fixture()
def db(monkeypatch):
    """Engine only — for the counter and backfill units."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    with engine.begin() as conn:
        conn.execute(users_table.insert().values(
            sleeper_user_id=UID, created_at="2026-08-11T00:00:00+00:00"))
    return engine


@pytest.fixture()
def client(monkeypatch):
    """Route harness — the shape test_ranking_method_point_of_use.py uses."""
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(users_table.insert().values(
            sleeper_user_id=UID, created_at="2026-08-11T00:00:00+00:00"))
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE_ID, user_id=UID, name="P17",
            season=SEASON, total_rosters=12, platform="sleeper"))
        for pid in PIDS:
            conn.execute(players_table.insert().values(
                player_id=pid, full_name=f"Player {pid}", position="RB",
                team="AAA", years_exp=2, rookie_year="2024"))

    svc = _FakeService(_pool())
    sess = {
        "user_id": UID,
        "active_format": FMT,
        "last_active": 0.0,
        "service": svc,
        "league": League(league_id=LEAGUE_ID, name="P17",
                         platform="sleeper", members=[]),
        "user_roster": [],
        "players": _pool(),
        "trade_svc": MagicMock(),
        "verified": True,
    }

    flags: set[str] = set()
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "_send_typed_push", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield c, svc, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


# -- helpers ----------------------------------------------------------------

def _set_method(engine, method, uid=UID):
    with engine.begin() as conn:
        conn.execute(users_table.update()
                     .where(users_table.c.sleeper_user_id == uid)
                     .values(ranking_method=method))


def _progress(c):
    r = c.get("/api/rankings/progress", headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200, r.data
    return json.loads(r.data)


def _overrides(svc, n, prefix="p"):
    """Give the fake board `n` pool-resident overrides."""
    svc._elo_overrides = {f"{prefix}{i}": 1600.0 for i in range(1, n + 1)}


def _no_unlock_row(engine, uid=UID):
    """The monotonic floor must not be pre-seeded, or every test below passes
    for the wrong reason (LLD X-2)."""
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.unlocked_formats)
            .where(users_table.c.sleeper_user_id == uid)).fetchone()
    return not (row.unlocked_formats and json.loads(row.unlocked_formats))


# ═══════════════════════════════════════════════════════════════════════════
# T-1…T-9 — the 'anchor' arm
# ═══════════════════════════════════════════════════════════════════════════

def test_t1_anchor_below_the_bar_stays_locked(client):
    c, svc, engine = client
    _set_method(engine, "anchor")
    _overrides(svc, ANCHOR_MIN - 1)
    assert _no_unlock_row(engine)
    assert _progress(c)["unlocked"] is False


def test_t2_anchor_at_the_bar_unlocks(client):
    c, svc, engine = client
    _set_method(engine, "anchor")
    _overrides(svc, ANCHOR_MIN)
    assert _no_unlock_row(engine)
    assert _progress(c)["unlocked"] is True


def test_t3_anchor_unlocks_with_zero_trio_interactions(client):
    """The regression itself. Before P1-7 this user could never unlock: the
    trio rule needs 10 swipes per position and the anchor lane writes none."""
    c, svc, engine = client
    _set_method(engine, "anchor")
    _overrides(svc, ANCHOR_MIN)
    svc.counts = {p: 0 for p in POSITIONS}
    assert _no_unlock_row(engine)
    body = _progress(c)
    assert body["unlocked"] is True
    assert body["total_completed"] == 0


def test_t4_anchor_with_a_complete_tier_board_unlocks_on_the_or_clause(client):
    """The legacy-rescue clause: an 'anchor' user who already holds a full
    tier board unlocks even with no overrides at all."""
    c, svc, engine = client
    _set_method(engine, "anchor")
    _overrides(svc, 0)
    with patch.object(db_module, "engine", engine):
        for pos in POSITIONS:
            save_tiers_position(UID, pos, scoring_format=FMT)
    assert _progress(c)["unlocked"] is True


def test_t5_the_or_clause_is_format_scoped(client):
    """A complete tier board in the OTHER format does not rescue this one."""
    c, svc, engine = client
    _set_method(engine, "anchor")
    _overrides(svc, 0)
    with patch.object(db_module, "engine", engine):
        for pos in POSITIONS:
            save_tiers_position(UID, pos, scoring_format=OTHER_FMT)
    assert _progress(c)["unlocked"] is False


def test_t6_stale_pids_do_not_count(client):
    """Pool-restriction. 40 overrides, but half are for players no longer in
    the pool, so the honest count is 20."""
    c, svc, engine = client
    _set_method(engine, "anchor")
    svc._elo_overrides = {f"p{i}": 1600.0 for i in range(1, 21)}
    svc._elo_overrides.update({f"gone{i}": 1600.0 for i in range(1, 21)})
    assert svc.board_override_count() == 20
    assert _progress(c)["unlocked"] is False


def test_t7_trio_method_is_not_rescued_by_a_board(client):
    """P-d: nothing outside the two board-evidence arms consults the count."""
    c, svc, engine = client
    _set_method(engine, "trio")
    _overrides(svc, ANCHOR_MIN)
    assert _no_unlock_row(engine)
    assert _progress(c)["unlocked"] is False


def test_t8_null_method_is_not_rescued_by_a_board(client):
    """A draft-room-only anchorer. P0-1 skips via:'draft_room', so their
    method stays NULL, they never enter the 'anchor' arm, and the trio rule
    still applies. DESIGNED behaviour — see the ladder comment."""
    c, svc, engine = client
    _set_method(engine, None)
    _overrides(svc, ANCHOR_MIN)
    assert _no_unlock_row(engine)
    assert _progress(c)["unlocked"] is False


def test_t9_anchor_reports_the_progress_hint(client):
    c, svc, engine = client
    _set_method(engine, "anchor")
    _overrides(svc, 12)
    body = _progress(c)
    assert body["anchor_count"] == 12
    assert body["anchor_required"] == ANCHOR_MIN


# ═══════════════════════════════════════════════════════════════════════════
# T-10…T-14 — the 'manual' arm (A-17, D-P1-10 scope addition)
# ═══════════════════════════════════════════════════════════════════════════

def test_t10_manual_no_longer_unlocks_on_an_empty_board(client):
    """The A-17 fix. Post-P0-1 one drag on Manual Ranks pins 'manual'; before
    P1-7 that alone granted a permanent unlock."""
    c, svc, engine = client
    _set_method(engine, "manual")
    _overrides(svc, 0)
    assert _no_unlock_row(engine)
    assert _progress(c)["unlocked"] is False


def test_t11_manual_below_the_bar_stays_locked(client):
    c, svc, engine = client
    _set_method(engine, "manual")
    _overrides(svc, MANUAL_MIN - 1)
    assert _no_unlock_row(engine)
    assert _progress(c)["unlocked"] is False


def test_t12_manual_at_the_bar_unlocks(client):
    """D-P1-10's governing principle: manual is not a dead end either."""
    c, svc, engine = client
    _set_method(engine, "manual")
    _overrides(svc, MANUAL_MIN)
    assert _progress(c)["unlocked"] is True


def test_t13_manual_with_a_complete_tier_board_unlocks(client):
    c, svc, engine = client
    _set_method(engine, "manual")
    _overrides(svc, 0)
    with patch.object(db_module, "engine", engine):
        for pos in POSITIONS:
            save_tiers_position(UID, pos, scoring_format=FMT)
    assert _progress(c)["unlocked"] is True


def test_t14_manual_reports_its_own_bar_in_the_hint(client):
    c, svc, engine = client
    _set_method(engine, "manual")
    _overrides(svc, 5)
    body = _progress(c)
    assert body["anchor_count"] == 5
    assert body["anchor_required"] == MANUAL_MIN


# ═══════════════════════════════════════════════════════════════════════════
# T-15…T-17 — the arms that must NOT have moved
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("method", ["tiers", "quickset"])
def test_t15_tiers_and_quickset_still_use_the_tiers_rule(client, method):
    """`_tiers_rule` was EXTRACTED, not changed. Overrides alone must not
    unlock these two."""
    c, svc, engine = client
    _set_method(engine, method)
    _overrides(svc, ANCHOR_MIN)
    assert _progress(c)["unlocked"] is False
    with patch.object(db_module, "engine", engine):
        for pos in POSITIONS:
            save_tiers_position(UID, pos, scoring_format=FMT)
    assert _progress(c)["unlocked"] is True


def test_t16_the_trio_rule_still_works(client):
    c, svc, engine = client
    _set_method(engine, "trio")
    svc.counts = {p: 10 for p in POSITIONS}
    assert _progress(c)["unlocked"] is True


def test_t17_the_monotonic_floor_still_wins(client):
    """A previously-unlocked user is never re-locked by the tightened manual
    arm — which is what makes A-17's fix safe to ship to live users."""
    c, svc, engine = client
    _set_method(engine, "manual")
    _overrides(svc, 0)
    with patch.object(db_module, "engine", engine):
        mark_format_unlocked(UID, FMT)
    assert _progress(c)["unlocked"] is True


# ═══════════════════════════════════════════════════════════════════════════
# T-18…T-19 — the first-unlock fan-out (RL-5)
# ═══════════════════════════════════════════════════════════════════════════

def test_t18_crossing_the_anchor_bar_fires_the_first_unlock_fanout(client):
    """The control for T-19: a GENUINELY new unlock still announces itself."""
    c, svc, engine = client
    _set_method(engine, "anchor")
    _overrides(svc, ANCHOR_MIN)
    assert _progress(c)["unlocked"] is True
    with engine.connect() as conn:
        n = len(conn.execute(
            select(user_events_table.c.id)
            .where(user_events_table.c.user_id == UID)
            .where(user_events_table.c.event_type
                   == "ranking_complete_first_time")).fetchall())
    assert n == 1


def test_t19_a_preseeded_anchor_user_does_not_fan_out_retroactively(client):
    """P1-7 matches P0-1's answer to the same question: suppression is a
    pre-seeded `unlocked_formats` row written by the boot backfill, NOT a
    special case in the fan-out branch."""
    c, svc, engine = client
    _set_method(engine, "anchor")
    _overrides(svc, ANCHOR_MIN)
    with patch.object(db_module, "engine", engine):
        save_tier_overrides(UID, {f"p{i}": 1600.0 for i in range(1, ANCHOR_MIN + 1)},
                            scoring_format=FMT)
        assert backfill_anchor_unlocked_formats(ANCHOR_MIN) == 1
    assert _progress(c)["unlocked"] is True
    with engine.connect() as conn:
        n = len(conn.execute(
            select(user_events_table.c.id)
            .where(user_events_table.c.user_id == UID)
            .where(user_events_table.c.event_type
                   == "ranking_complete_first_time")).fetchall())
    assert n == 0


# ═══════════════════════════════════════════════════════════════════════════
# T-20…T-23 — board_override_count on the REAL service
# ═══════════════════════════════════════════════════════════════════════════

def test_t20_override_count_survives_rebuild_but_interactions_do_not():
    """The executable form of the Option-2 rejection.

    `_interactions` is rebuilt from persisted rank swipes at session build, so
    an in-memory bump in apply_anchor would evaporate on the next cold start
    (unlock Tuesday, re-locked Wednesday). Overrides are persisted and
    restored, so they are the only durable evidence available."""
    svc = RankingService(players=_pool())
    for pid in PIDS[:ANCHOR_MIN]:
        svc.apply_anchor(pid, 1650.0)
    assert svc.board_override_count() == ANCHOR_MIN
    assert svc._interactions == {}

    # The rebuild: a fresh service, restored the way session_init restores it.
    persisted = dict(svc._elo_overrides)
    rebuilt = RankingService(players=_pool())
    rebuilt._elo_overrides = persisted
    assert rebuilt.board_override_count() == ANCHOR_MIN
    assert rebuilt._interactions == {}


def test_t21_override_count_is_pool_restricted():
    """`_elo_overrides` deliberately retains stale pids, so a raw len() would
    over-count a long-lived board."""
    svc = RankingService(players=_pool())
    svc.apply_anchor(PIDS[0], 1650.0)
    svc._elo_overrides["retired_player"] = 1400.0
    assert len(svc._elo_overrides) == 2
    assert svc.board_override_count() == 1


def test_t22_a_manual_reorder_produces_board_evidence():
    """The manual arm is only implementable because apply_reorder writes one
    override per reordered player, through the same persisted store."""
    svc = RankingService(players=_pool())
    svc.apply_reorder(position=None, ordered_ids=PIDS[:MANUAL_MIN])
    assert svc.board_override_count() == MANUAL_MIN


def test_t23_apply_anchor_writes_no_swipe_and_no_interaction():
    """Restates fact 4 of the defect proof at the service boundary."""
    svc = RankingService(players=_pool())
    svc.apply_anchor(PIDS[0], 1650.0)
    assert svc._interactions == {}
    assert svc._swipes == []


# ═══════════════════════════════════════════════════════════════════════════
# T-24…T-27 — the backfill
# ═══════════════════════════════════════════════════════════════════════════

def test_t24_backfill_preseeds_a_qualifying_anchor_user(db):
    _set_method(db, "anchor")
    save_tier_overrides(UID, {f"p{i}": 1600.0 for i in range(1, ANCHOR_MIN + 1)},
                        scoring_format=FMT)
    assert backfill_anchor_unlocked_formats(ANCHOR_MIN) == 1
    assert get_unlocked_formats(UID) == [FMT]


def test_t25_backfill_skips_a_user_below_the_bar(db):
    _set_method(db, "anchor")
    save_tier_overrides(UID, {f"p{i}": 1600.0 for i in range(1, ANCHOR_MIN)},
                        scoring_format=FMT)
    assert backfill_anchor_unlocked_formats(ANCHOR_MIN) == 0
    assert get_unlocked_formats(UID) == []


def test_t26_backfill_ignores_other_methods(db):
    """Narrow by design: it exists to suppress the ANCHOR cohort's burst.
    'manual' is only ever tightened by P1-7, so it can produce no new unlock
    and needs no suppression."""
    _set_method(db, "manual")
    save_tier_overrides(UID, {f"p{i}": 1600.0 for i in range(1, ANCHOR_MIN + 1)},
                        scoring_format=FMT)
    assert backfill_anchor_unlocked_formats(ANCHOR_MIN) == 0
    assert get_unlocked_formats(UID) == []


def test_t27_backfill_is_idempotent(db):
    _set_method(db, "anchor")
    save_tier_overrides(UID, {f"p{i}": 1600.0 for i in range(1, ANCHOR_MIN + 1)},
                        scoring_format=FMT)
    assert backfill_anchor_unlocked_formats(ANCHOR_MIN) == 1
    assert backfill_anchor_unlocked_formats(ANCHOR_MIN) == 0
    assert get_unlocked_formats(UID) == [FMT]


def test_t28_backfill_is_per_format(db):
    """Only the format that carries the board is pre-seeded."""
    _set_method(db, "anchor")
    save_tier_overrides(UID, {f"p{i}": 1600.0 for i in range(1, ANCHOR_MIN + 1)},
                        scoring_format=OTHER_FMT)
    save_tier_overrides(UID, {"p1": 1600.0}, scoring_format=FMT)
    assert backfill_anchor_unlocked_formats(ANCHOR_MIN) == 1
    assert get_unlocked_formats(UID) == [OTHER_FMT]
