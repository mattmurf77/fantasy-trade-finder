"""P0-1 — `ranking_method` written at the point of USE (mobile UX audit 2026-08-09).

Spec: docs/plans/audit-p0-remediation/lld-p0-1.md §7 (T-1…T-24b, T-H1…T-H6).

The finding: a user who completed a Quick Set board read 4/4 on the ring and
`unlocked:false` from `/api/rankings/progress`, because `ranking_method` stayed
NULL (only the chooser wrote it) and NULL falls to the trio branch. The fix
writes the method from the four save handlers, first-use wins, plus a startup
backfill for the pre-fix cohort whose `unlocked_formats` pre-seed suppresses a
retroactive first-unlock fan-out.

Everything here is offline: in-memory SQLite, an injected fake ranking service,
and a real Flask test client with a seeded `server._sessions` entry.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.server as server
from backend.database import (
    metadata, users_table, players_table, leagues_table, user_events_table,
    set_ranking_method_if_unset,
)
from backend.ranking_service import Player, RankedPlayer, RankSet
from backend.trade_service import League

UID = "u_p01"
LEAGUE_ID = "9910001"
TOKEN = "sess-p01-tok"
SEASON = "2026"
POSITIONS = ("QB", "RB", "WR", "TE")
PIDS = ["p1", "p2", "p3", "p4"]


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db(monkeypatch):
    """Engine only — for the helper (T-H*) and backfill (T-18…T-22b) units."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    with engine.begin() as conn:
        conn.execute(users_table.insert().values(
            sleeper_user_id=UID, created_at="2026-08-10T00:00:00+00:00"))
    return engine


def _p(pid, pos="RB"):
    return Player(id=pid, name=f"Player {pid}", position=pos, team="AAA",
                  age=24, years_experience=2, search_rank=int(pid[1:]))


def _pool():
    return [_p(pid) for pid in PIDS]


class _FakeService:
    """Serves a fixed board. The route wiring is what is under test, so the
    ranking math is irrelevant — but `get_progress` is a real mutable counter,
    because T-15's "unlocked with ZERO trio interactions" assertion rests on it.
    """

    POSITION_THRESHOLDS = {"QB": 10, "RB": 10, "WR": 10, "TE": 10}

    def __init__(self, players):
        self._players = players
        self._elo_overrides = {}
        self.counts = {p: 0 for p in POSITIONS}
        self.applied = []

    # -- shared ------------------------------------------------------------
    def _pool(self, position=None):
        return list(self._players)

    def has_player(self, pid):
        return any(p.id == pid for p in self._players)

    def get_rankings(self, position=None):
        return RankSet(
            position=position,
            rankings=[RankedPlayer(p, 1900.0 - 10 * i, 1, 0, i + 1)
                      for i, p in enumerate(self._players)],
            interaction_count=0, threshold=10, threshold_met=False,
            version=1, computed_at="2026-08-10T00:00:00Z",
        )

    def get_progress(self, position=None):
        n = self.counts.get(position, 0) if position else sum(self.counts.values())
        return {"interaction_count": n, "threshold": 10,
                "threshold_met": n >= 10, "position": position}

    def _tier_info(self, position=None):
        return {}

    # -- write paths -------------------------------------------------------
    def record_ranking(self, ordered_ids):
        return RankSet(position=None, rankings=[], interaction_count=1,
                       threshold=10, threshold_met=False, version=1,
                       computed_at="2026-08-10T00:00:00Z")

    def apply_tiers(self, **kw):
        self.applied.append(kw)

    def apply_tiers_subset(self, **kw):
        self.applied.append(kw)
        return {}

    def apply_reorder(self, position=None, ordered_ids=None):
        self.applied.append({"reorder": ordered_ids})

    def apply_anchor(self, player_id, target_elo):
        for p in self._players:
            if p.id == player_id:
                self._elo_overrides[player_id] = target_elo
                return p
        return None

    def tier_for_elo(self, elo, position, fmt):
        return "second"


@pytest.fixture()
def client(monkeypatch):
    """Route harness — copied from test_rookie_scope.py's `client` fixture."""
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(users_table.insert().values(
            sleeper_user_id=UID, created_at="2026-08-10T00:00:00+00:00"))
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE_ID, user_id=UID, name="P01",
            season=SEASON, total_rosters=12, platform="sleeper"))
        for pid in PIDS:
            conn.execute(players_table.insert().values(
                player_id=pid, full_name=f"Player {pid}", position="RB",
                team="AAA", years_exp=2, rookie_year="2024"))

    svc = _FakeService(_pool())
    sess = {
        "user_id": UID,
        "active_format": "1qb_ppr",
        "last_active": 0.0,
        "service": svc,
        "league": League(league_id=LEAGUE_ID, name="P01",
                         platform="sleeper", members=[]),
        "user_roster": [],
        "players": _pool(),
        "trade_svc": MagicMock(),
        # P0-1 §7.1(2): keeps `_gate_unverified_read` out of the way so the
        # test stays about the ranking method, not the verification matrix.
        "verified": True,
    }

    flags: set[str] = set()
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags), \
         patch.object(server, "touch_user_activity", MagicMock()):
        server._invalidate_rookie_ids_memo()
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield c, flags, svc, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            server._invalidate_rookie_ids_memo()
            server._invalidate_draft_context_cache()


# -- helpers ----------------------------------------------------------------

def _method(engine=None, uid=UID):
    eng = engine if engine is not None else db_module.engine
    with eng.connect() as conn:
        row = conn.execute(
            select(users_table.c.ranking_method)
            .where(users_table.c.sleeper_user_id == uid)).fetchone()
    return row.ranking_method if row else None


def _set_method(engine, method, uid=UID):
    with engine.begin() as conn:
        conn.execute(users_table.update()
                     .where(users_table.c.sleeper_user_id == uid)
                     .values(ranking_method=method))


def _post(c, path, body, expect=200):
    r = c.post(path, json=body, headers={"X-Session-Token": TOKEN})
    assert r.status_code == expect, r.data
    return json.loads(r.data) if r.data else {}


def _get(c, path, expect=200):
    r = c.get(path, headers={"X-Session-Token": TOKEN})
    assert r.status_code == expect, r.data
    return json.loads(r.data)


def _save_tiers(c, position="RB", expect=200, **body):
    payload = {"position": position, "tiers": {"second": [PIDS[0]]}}
    payload.update(body)
    return _post(c, "/api/tiers/save", payload, expect=expect)


def _event_count(engine, name, uid=UID):
    with engine.connect() as conn:
        return len(conn.execute(
            select(user_events_table.c.id)
            .where(user_events_table.c.user_id == uid)
            .where(user_events_table.c.event_type == name)).fetchall())


# ═══════════════════════════════════════════════════════════════════════════
# §7.2 — point-of-use writes
# ═══════════════════════════════════════════════════════════════════════════

def test_t1_tiers_save_via_quickset_writes_quickset(client):
    c, _, _, engine = client
    _save_tiers(c, via="quickset")
    assert _method(engine) == "quickset"


def test_t2_tiers_save_without_via_writes_the_routes_default(client):
    """The write reuses the route's whitelisted `via` local (server.py:7383-7386),
    it does not re-read the body — so an absent `via` lands as 'tiers'."""
    c, _, _, engine = client
    _save_tiers(c)
    assert _method(engine) == "tiers"


def test_t3_rank3_writes_trio(client):
    c, _, _, engine = client
    _post(c, "/api/rank3", {"ranked": PIDS[:3]})
    assert _method(engine) == "trio"


def test_t4_reorder_writes_manual(client):
    c, _, _, engine = client
    _post(c, "/api/rankings/reorder",
          {"position": "RB", "ordered_ids": PIDS[:2]})
    assert _method(engine) == "manual"


def test_t5_anchor_save_via_anchors_writes_anchor(client):
    c, _, _, engine = client
    _post(c, "/api/anchor/save",
          {"player_id": PIDS[0], "anchor": "2_firsts", "via": "anchors"})
    assert _method(engine) == "anchor"


def test_t5b_anchor_save_without_via_still_writes_anchor(client):
    """`_ANCHOR_VIA`'s fallback (:7519) resolves an absent via to 'anchors',
    and old binaries that send nothing are wizard traffic."""
    c, _, _, engine = client
    _post(c, "/api/anchor/save", {"player_id": PIDS[0], "anchor": "2_firsts"})
    assert _method(engine) == "anchor"


def test_t6_draft_room_anchor_writes_nothing(client):
    c, _, _, engine = client
    _post(c, "/api/anchor/save",
          {"player_id": PIDS[0], "anchor": "2_firsts", "via": "draft_room"})
    assert _method(engine) is None


def test_t7_rookie_scope_tier_save_writes_nothing(client):
    c, flags, _, engine = client
    flags.add("ranks.rookie_subset")
    _save_tiers(c, scope="rookie", via="rookie_quickset")
    assert _method(engine) is None


def test_t7b_rookie_scope_with_a_full_board_via_still_writes_nothing(client):
    """Proves `scope != "rookie"` is not redundant with the `via` whitelist:
    a rookie-scoped save that sends via:'quickset' is reachable today."""
    c, flags, _, engine = client
    flags.add("ranks.rookie_subset")
    _save_tiers(c, scope="rookie", via="quickset")
    assert _method(engine) is None


def test_t8_rookie_ranks_reorder_writes_nothing(client):
    c, _, _, engine = client
    _post(c, "/api/rankings/reorder",
          {"position": "RB", "ordered_ids": PIDS[:2], "via": "rookie_ranks"})
    assert _method(engine) is None


def test_t8b_quickrank_reorder_writes_manual(client):
    """Quick Rank is a FULL-board flow — only the literal 'rookie_ranks' is
    excluded."""
    c, _, _, engine = client
    _post(c, "/api/rankings/reorder",
          {"position": "RB", "ordered_ids": PIDS[:2], "via": "quickrank"})
    assert _method(engine) == "manual"


# ═══════════════════════════════════════════════════════════════════════════
# §7.3 — idempotence / precedence (first-use wins)
# ═══════════════════════════════════════════════════════════════════════════

def test_t9_an_established_trio_method_is_never_overwritten(client):
    """THE re-lock guard. Overwriting 'trio' with 'quickset' would move the
    user onto a completeness rule they may not satisfy."""
    c, _, _, engine = client
    _set_method(engine, "trio")
    _save_tiers(c, via="quickset")
    assert _method(engine) == "trio"


def test_t10_manual_survives_a_trio_swipe(client):
    c, _, _, engine = client
    _set_method(engine, "manual")
    _post(c, "/api/rank3", {"ranked": PIDS[:3]})
    assert _method(engine) == "manual"


def test_t11_anchor_is_upgraded_by_a_quickset_save(client):
    """S-01: the one approved overwrite in the whole design."""
    c, _, _, engine = client
    _set_method(engine, "anchor")
    _save_tiers(c, via="quickset")
    assert _method(engine) == "quickset"


def test_t11b_the_anchor_upgrade_is_not_via_specific(client):
    c, _, _, engine = client
    _set_method(engine, "anchor")
    _save_tiers(c)
    assert _method(engine) == "tiers"


def test_t11c_rank3_does_not_upgrade_anchor(client):
    """`allow_over` is passed by the tiers/quickset call ONLY."""
    c, _, _, engine = client
    _set_method(engine, "anchor")
    _post(c, "/api/rank3", {"ranked": PIDS[:3]})
    assert _method(engine) == "anchor"


def test_t12_a_rookie_scope_save_never_upgrades_anchor(client):
    c, flags, _, engine = client
    flags.add("ranks.rookie_subset")
    _set_method(engine, "anchor")
    _save_tiers(c, scope="rookie", via="quickset")
    assert _method(engine) == "anchor"


def test_t13_the_second_identical_save_writes_nothing_and_drops_no_cache(client):
    """Idempotence AND the cache-drop-only-on-write contract, in one: the
    league-members cache must be invalidated exactly once across two saves."""
    c, _, _, engine = client
    with patch.object(server, "_invalidate_league_members_cache") as inval:
        _save_tiers(c, via="quickset")
        _save_tiers(c, via="quickset")
    assert _method(engine) == "quickset"
    assert inval.call_count == 1


def test_t14_a_failed_tier_save_leaves_no_method(client):
    c, _, _, engine = client
    _save_tiers(c, position="XX", expect=400)
    assert _method(engine) is None


def test_t14b_a_failed_rank3_leaves_no_method(client):
    c, _, _, engine = client
    _post(c, "/api/rank3", {"ranked": PIDS[:1]}, expect=400)
    assert _method(engine) is None


# ═══════════════════════════════════════════════════════════════════════════
# §7.4 — helper-level units (no route)
# ═══════════════════════════════════════════════════════════════════════════

def test_th1_writes_when_unset(db):
    assert set_ranking_method_if_unset(UID, "trio") is True
    assert _method(db) == "trio"


def test_th2_is_a_no_op_when_already_set(db):
    set_ranking_method_if_unset(UID, "trio")
    assert set_ranking_method_if_unset(UID, "quickset") is False
    assert _method(db) == "trio"


def test_th3_empty_string_counts_as_unset(db):
    _set_method(db, "")
    assert set_ranking_method_if_unset(UID, "tiers") is True
    assert _method(db) == "tiers"


def test_th4_allow_over_widens_by_exactly_that_tuple(db):
    _set_method(db, "anchor")
    assert set_ranking_method_if_unset(
        UID, "quickset", allow_over=("anchor",)) is True
    assert _method(db) == "quickset"


def test_th5_never_invents_a_users_row(db):
    with db.connect() as conn:
        before = len(conn.execute(select(users_table.c.sleeper_user_id)).fetchall())
    assert set_ranking_method_if_unset("ghost", "trio") is False
    with db.connect() as conn:
        after = len(conn.execute(select(users_table.c.sleeper_user_id)).fetchall())
    assert after == before


def test_th6_an_unknown_method_never_lands(db):
    assert set_ranking_method_if_unset(UID, "vibes") is False
    assert _method(db) is None


# ═══════════════════════════════════════════════════════════════════════════
# §7.5 — acceptance, end to end
# ═══════════════════════════════════════════════════════════════════════════

def _complete_quickset(c, svc, positions=POSITIONS):
    for pos in positions:
        _save_tiers(c, position=pos, via="quickset")


def test_t15_four_quickset_saves_unlock_with_zero_trio_interactions(client):
    """The machine-checkable half of the acceptance criterion."""
    c, _, svc, engine = client
    _complete_quickset(c, svc)
    prog = _get(c, "/api/rankings/progress")
    assert prog["unlocked"] is True
    assert _method(engine) == "quickset"
    assert [prog[p] for p in POSITIONS] == [0, 0, 0, 0]


def test_t16_a_partial_board_does_not_unlock(client):
    c, _, svc, engine = client
    _complete_quickset(c, svc, positions=("QB", "RB", "WR"))
    assert _get(c, "/api/rankings/progress")["unlocked"] is False


def test_t17_first_unlock_fires_exactly_once(client):
    c, _, svc, engine = client
    _complete_quickset(c, svc)
    with patch.object(server, "_send_typed_push", MagicMock()):
        _get(c, "/api/rankings/progress")
        _get(c, "/api/rankings/progress")
    assert _event_count(engine, "ranking_complete_first_time") == 1


def test_t17b_the_push_fanout_does_not_repeat(client):
    c, _, svc, engine = client
    _complete_quickset(c, svc)
    with patch.object(server, "_send_typed_push", MagicMock()) as push:
        _get(c, "/api/rankings/progress")
        first = push.call_count
        _get(c, "/api/rankings/progress")
        assert push.call_count == first


# ═══════════════════════════════════════════════════════════════════════════
# §7.6 — the startup backfill
# ═══════════════════════════════════════════════════════════════════════════

def _seed_backfill_row(engine, tiers_saved, method=None, unlocked=None,
                       uid=UID):
    with engine.begin() as conn:
        conn.execute(users_table.update()
                     .where(users_table.c.sleeper_user_id == uid)
                     .values(tiers_saved=tiers_saved, ranking_method=method,
                             unlocked_formats=unlocked))


def _unlocked(engine, uid=UID):
    with engine.connect() as conn:
        row = conn.execute(
            select(users_table.c.unlocked_formats)
            .where(users_table.c.sleeper_user_id == uid)).fetchone()
    return json.loads(row.unlocked_formats) if row and row.unlocked_formats else None


ALL_FOUR = ["QB", "RB", "WR", "TE"]


def test_t18_a_complete_board_is_tagged_and_the_format_pre_seeded(db):
    _seed_backfill_row(db, json.dumps({"1qb_ppr": ALL_FOUR, "sf_tep": []}))
    assert db_module.backfill_ranking_method_from_tiers() == 1
    assert _method(db) == "quickset"
    assert _unlocked(db) == ["1qb_ppr"]


def test_t18b_both_formats_pre_seed_in_scoring_format_order(db):
    _seed_backfill_row(db, json.dumps({"1qb_ppr": ALL_FOUR, "sf_tep": ALL_FOUR}))
    db_module.backfill_ranking_method_from_tiers()
    assert _unlocked(db) == ["1qb_ppr", "sf_tep"]


def test_t18c_the_pre_seed_merges_and_never_clobbers(db):
    _seed_backfill_row(db, json.dumps({"1qb_ppr": [], "sf_tep": ALL_FOUR}),
                       unlocked=json.dumps(["1qb_ppr"]))
    db_module.backfill_ranking_method_from_tiers()
    assert _unlocked(db) == ["1qb_ppr", "sf_tep"]


def test_t19_a_partial_board_is_excluded(db):
    """The narrow cohort: tagging a partial-tiers + full-trio user would move
    them onto the tiers rule and could RE-LOCK them."""
    _seed_backfill_row(db, json.dumps({"1qb_ppr": ["QB", "RB"], "sf_tep": []}))
    assert db_module.backfill_ranking_method_from_tiers() == 0
    assert _method(db) is None
    assert _unlocked(db) is None


def test_t20_an_established_method_is_never_touched(db):
    _seed_backfill_row(db, json.dumps({"1qb_ppr": ALL_FOUR, "sf_tep": []}),
                       method="trio")
    assert db_module.backfill_ranking_method_from_tiers() == 0
    assert _method(db) == "trio"
    assert _unlocked(db) is None


def test_t21_the_backfill_is_idempotent(db):
    _seed_backfill_row(db, json.dumps({"1qb_ppr": ALL_FOUR, "sf_tep": []}))
    assert db_module.backfill_ranking_method_from_tiers() == 1
    assert db_module.backfill_ranking_method_from_tiers() == 0
    assert _method(db) == "quickset"
    assert _unlocked(db) == ["1qb_ppr"]


@pytest.mark.parametrize("raw", [
    None, "", "{}", "not json", '["QB","RB","WR","TE"]',
])
def test_t22_malformed_tiers_saved_is_absorbed(db, raw):
    _seed_backfill_row(db, raw)
    assert db_module.backfill_ranking_method_from_tiers() == 0
    assert _method(db) is None


def test_t22b_the_empty_string_cohort_is_backfilled(db):
    _seed_backfill_row(db, json.dumps({"1qb_ppr": ALL_FOUR, "sf_tep": []}),
                       method="")
    assert db_module.backfill_ranking_method_from_tiers() == 1
    assert _method(db) == "quickset"


# -- T-24 / T-24b: the S-03 suppression, and its control --------------------

def _make_backfilled_user(engine, unlocked_formats):
    """A row in exactly the shape the backfill leaves behind."""
    with engine.begin() as conn:
        conn.execute(users_table.update()
                     .where(users_table.c.sleeper_user_id == UID)
                     .values(ranking_method="quickset",
                             tiers_saved=json.dumps(
                                 {"1qb_ppr": ALL_FOUR, "sf_tep": ALL_FOUR}),
                             unlocked_formats=unlocked_formats))


def test_t24_a_backfilled_user_does_not_fan_out_retroactively(client):
    """S-03. The pre-seeded floor short-circuits `mark_format_unlocked`, so the
    first post-deploy poll emits no `ranking_complete_first_time` and no
    leaguemate push."""
    c, _, _, engine = client
    _make_backfilled_user(engine, json.dumps(["1qb_ppr", "sf_tep"]))
    with patch.object(server, "_send_typed_push", MagicMock()) as push:
        assert _get(c, "/api/rankings/progress")["unlocked"] is True
    assert push.call_count == 0
    assert _event_count(engine, "ranking_complete_first_time") == 0


def test_t24b_control_without_the_pre_seed_the_fanout_does_fire(client):
    """Without this control, T-24 would pass on a build where the whole
    fan-out was accidentally dead."""
    c, _, _, engine = client
    _make_backfilled_user(engine, "[]")
    with patch.object(server, "_send_typed_push", MagicMock()):
        assert _get(c, "/api/rankings/progress")["unlocked"] is True
    assert _event_count(engine, "ranking_complete_first_time") == 1


# ═══════════════════════════════════════════════════════════════════════════
# §7.7 — regression guard: nobody loses an unlock
# ═══════════════════════════════════════════════════════════════════════════

def test_t23_a_trio_unlocked_user_stays_unlocked_after_a_tier_save(client):
    c, _, svc, engine = client
    with engine.begin() as conn:
        conn.execute(users_table.update()
                     .where(users_table.c.sleeper_user_id == UID)
                     .values(ranking_method="trio",
                             unlocked_formats=json.dumps(["1qb_ppr"])))
    for pos in POSITIONS:
        svc.counts[pos] = 10
    _save_tiers(c, via="quickset")
    assert _method(engine) == "trio"
    assert _get(c, "/api/rankings/progress")["unlocked"] is True
