"""Rookie-draft M2 — the rookie-scope seam (backend half).

Test matrix T-M2-01..13 from docs/plans/rookie-draft/lld.md §7.

The architecture under test (plan D2/D3/D4, lld §4.2/§4.3):

  * `scope=rookie` is a POST-Elo VIEW filter. `_pool` / `_compute_elo` /
    `apply_reorder` / `apply_anchor` all stay on the FULL position pool, so a
    rookie's Elo is byte-identical scoped or not — every rookie-vs-vet swipe
    still counts. Filtering the pool would silently fork the Elo space.
  * A scoped TIER save uses the merged-band rule: merge the scoped pids into
    the current full-band order, spread over the FULL merged list, and persist
    overrides for the scoped pids ONLY. Anything else either respreads the
    whole band (destroying untouched members) or promotes every rookie to the
    top of it.
  * A scoped save NEVER marks a position complete — `tiers_saved`/`all_done`
    feed four other surfaces.
  * Flag off ⇒ the `scope` param is never read ⇒ responses byte-identical.

Everything here is offline: in-memory SQLite, an injected fake service where
the route wiring is what's under test, and a real `RankingService` where the
merge arithmetic is.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.server as server
from backend.database import (
    metadata, users_table, players_table, leagues_table,
    PRE_ROOKIE_SCOPE_KEY, save_tier_overrides, load_tier_overrides,
    take_tier_override_snapshot, load_tier_override_snapshot,
    restore_tier_overrides_from_snapshot,
)
from backend.ranking_service import (
    Player, RankedPlayer, RankSet, MatchupTrio, RankingService,
)
from backend.trade_service import League

UID = "u_m2"
LEAGUE_ID = "9990001"
TOKEN = "sess-m2-tok"
SEASON = "2026"


# ═══════════════════════════════════════════════════════════════════════════
# T-M2-01 — the sibling-key preservation fix (VFF)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    with engine.begin() as conn:
        conn.execute(users_table.insert().values(
            sleeper_user_id=UID, created_at="2026-08-06T00:00:00+00:00"))
    return engine


def test_m2_01_sibling_key_survives_alternating_format_saves(db):
    """T-M2-01 (VFF) — `_parse_per_format_json` narrows to SCORING_FORMATS, so
    every writer that round-trips the column used to DELETE any sibling key on
    the next save. The snapshot lives in exactly such a key."""
    save_tier_overrides(UID, {"a": 1500.0}, scoring_format="1qb_ppr")
    assert take_tier_override_snapshot(UID) is True
    snap = load_tier_override_snapshot(UID)
    assert snap and snap["formats"]["1qb_ppr"] == {"a": 1500.0}

    # Three alternating-format saves — pre-fix, the first one wiped it.
    save_tier_overrides(UID, {"a": 1600.0}, scoring_format="sf_tep")
    save_tier_overrides(UID, {"a": 1700.0}, scoring_format="1qb_ppr")
    save_tier_overrides(UID, {"a": 1800.0}, scoring_format="sf_tep")

    survived = load_tier_override_snapshot(UID)
    assert survived is not None, "snapshot destroyed by a subsequent save"
    assert survived == snap
    # …and the formats themselves are untouched by the extras merge.
    assert load_tier_overrides(UID, "1qb_ppr") == {"a": 1700.0}
    assert load_tier_overrides(UID, "sf_tep") == {"a": 1800.0}


def test_m2_01b_extras_can_never_shadow_a_format_key(db):
    """`{**extras, **all_overrides}` — extras first, so a hostile/legacy extra
    named like a format cannot win."""
    with db_module.engine.begin() as conn:
        conn.execute(users_table.update()
                     .where(users_table.c.sleeper_user_id == UID)
                     .values(tier_overrides=json.dumps(
                         {"1qb_ppr": {"a": 1.0}, "junk": {"b": 2.0}})))
    save_tier_overrides(UID, {"a": 1500.0}, scoring_format="1qb_ppr")
    assert load_tier_overrides(UID, "1qb_ppr") == {"a": 1500.0}
    with db_module.engine.connect() as conn:
        raw = conn.execute(select(users_table.c.tier_overrides).where(
            users_table.c.sleeper_user_id == UID)).fetchone().tier_overrides
    assert json.loads(raw)["junk"] == {"b": 2.0}


# ═══════════════════════════════════════════════════════════════════════════
# T-M2-13 — snapshot lifecycle + restore
# ═══════════════════════════════════════════════════════════════════════════

def test_m2_13_snapshot_is_one_shot_and_restore_is_exact(db):
    """T-M2-13 — taken once, idempotent on the second call, and the restore
    reproduces the pre-scope blob exactly (both formats)."""
    save_tier_overrides(UID, {"p1": 1700.0, "p2": 1600.0}, scoring_format="1qb_ppr")
    save_tier_overrides(UID, {"p1": 1750.0}, scoring_format="sf_tep")

    assert take_tier_override_snapshot(UID) is True
    first = load_tier_override_snapshot(UID)
    assert first["v"] == 1 and first["reason"] == "pre_scope_v1"

    # Second call is a no-op and does NOT re-snapshot the (now damaged) board.
    save_tier_overrides(UID, {"p1": 1100.0}, scoring_format="1qb_ppr")
    assert take_tier_override_snapshot(UID) is False
    assert load_tier_override_snapshot(UID) == first

    counts = restore_tier_overrides_from_snapshot(UID)
    assert counts == {"1qb_ppr": 2, "sf_tep": 1}
    assert load_tier_overrides(UID, "1qb_ppr") == {"p1": 1700.0, "p2": 1600.0}
    assert load_tier_overrides(UID, "sf_tep") == {"p1": 1750.0}
    # Repeatable — the snapshot is not consumed.
    assert load_tier_override_snapshot(UID) == first
    assert restore_tier_overrides_from_snapshot(UID, "sf_tep") == {"sf_tep": 1}


def test_m2_13b_snapshot_of_an_empty_board_restores_to_empty(db):
    assert take_tier_override_snapshot(UID) is True
    save_tier_overrides(UID, {"p1": 1900.0}, scoring_format="1qb_ppr")
    assert restore_tier_overrides_from_snapshot(UID) == {"1qb_ppr": 0, "sf_tep": 0}
    assert load_tier_overrides(UID, "1qb_ppr") == {}


# ═══════════════════════════════════════════════════════════════════════════
# Ranking-service fixtures — a real service over a rookie/vet mixed pool
# ═══════════════════════════════════════════════════════════════════════════

ROOKIES = ["r1", "r2", "r3", "r4", "r5"]
VETS = ["v1", "v2", "v3", "v4", "v5", "v6"]


def _p(pid, pos="RB", yrs=0):
    return Player(id=pid, name=f"Player {pid}", position=pos, team="AAA",
                  age=23 if yrs == 0 else 28, years_experience=yrs,
                  search_rank=int(pid[1:]))


def _mixed_pool():
    return ([_p(pid, yrs=0) for pid in ROOKIES]
            + [_p(pid, yrs=5) for pid in VETS])


def _service(seed=None, overrides=None, swipes=None):
    """A RankingService over the mixed pool with a controllable seed."""
    pool = _mixed_pool()
    seed = seed or {p.id: 1500.0 + 10 * (len(pool) - i)
                    for i, p in enumerate(pool)}
    svc = RankingService(players=pool, seed_ratings=seed)
    svc._scoring_format = "1qb_ppr"
    if overrides:
        svc._elo_overrides.update(overrides)
    if swipes:
        svc.replay_from_db([{"winner_player_id": w, "loser_player_id": l,
                             "decision_type": "rank", "k_factor": 32.0}
                            for w, l in swipes])
    return svc


# ═══════════════════════════════════════════════════════════════════════════
# T-M2-02 / T-M2-03 — Elo identity and write identity by shape
# ═══════════════════════════════════════════════════════════════════════════

def test_m2_02_rookie_elo_is_identical_scoped_and_unscoped(db):
    """T-M2-02 (D2/I-1) — the scope is a VIEW filter, so a rookie's Elo comes
    from the FULL pool including every rookie-vs-vet swipe. Filtering the pool
    instead would fork the Elo space; this pins the difference."""
    # >=50 rookie-vs-vet swipes.
    swipes = []
    for i in range(60):
        r = ROOKIES[i % len(ROOKIES)]
        v = VETS[i % len(VETS)]
        swipes.append((r, v) if i % 3 else (v, r))
    svc = _service(swipes=swipes)

    full_pool = svc._pool("RB")
    unscoped = svc._compute_elo(full_pool)

    # The seam: filter the SERVED list, never the pool.
    rank_set = svc.get_rankings(position="RB")
    served = {rp.player.id: rp.elo for rp in rank_set.rankings}
    for pid in ROOKIES:
        assert served[pid] == pytest.approx(unscoped[pid], abs=0.05)

    # And the anti-pattern the plan rejects: a rookies-only pool produces
    # DIFFERENT Elos — proof the identity above is load-bearing, not trivial.
    rookies_only = RankingService(
        players=[p for p in _mixed_pool() if p.id in ROOKIES],
        seed_ratings={p.id: svc._seed[p.id] for p in _mixed_pool()
                      if p.id in ROOKIES})
    rookies_only.replay_from_db([{"winner_player_id": w, "loser_player_id": l,
                                  "decision_type": "rank", "k_factor": 32.0}
                                 for w, l in swipes])
    forked = rookies_only._compute_elo(rookies_only._pool("RB"))
    assert any(forked[pid] != unscoped[pid] for pid in ROOKIES)


def test_m2_03_reorder_and_anchor_are_already_subset_safe(db):
    """T-M2-03 (D2/I-2) — `apply_reorder`/`apply_anchor` permute/pin only the
    submitted ids. No code change; this pins them against a future edit."""
    base_overrides = {"v1": 1777.0, "v2": 1666.0}
    a = _service(overrides=dict(base_overrides))
    b = _service(overrides=dict(base_overrides))

    a.apply_reorder("RB", ["r3", "r1", "r2"])
    b.apply_reorder("RB", ["r3", "r1", "r2"])
    assert a._elo_overrides == b._elo_overrides
    # Untouched non-scoped pids are byte-identical.
    assert a._elo_overrides["v1"] == 1777.0
    assert a._elo_overrides["v2"] == 1666.0
    assert set(a._elo_overrides) == {"v1", "v2", "r1", "r2", "r3"}

    a.apply_anchor("r4", 1820.0)
    assert a._elo_overrides["r4"] == 1820.0
    assert a._elo_overrides["v1"] == 1777.0


# ═══════════════════════════════════════════════════════════════════════════
# T-M2-04 / 07 / 08 / 09 — the merged-band tier save
# ═══════════════════════════════════════════════════════════════════════════

def _band(svc, tier="second"):
    return svc.tier_bands_for("RB", "1qb_ppr")[tier]


def test_m2_04_scoped_save_never_respreads_the_band(db):
    """T-M2-04 (VFF, D3/I-3) — after a scoped save, every NON-scoped pid's
    override is byte-unchanged, and a non-rookie with no override before has
    none after.

    The pre-M2 path (`apply_tiers` with a rookies-only list) fails both halves:
    it spreads the rookies across the whole band and leaves the vets to be
    re-bucketed against them.
    """
    lo, hi = None, None
    svc = _service()
    lo, hi = _band(svc)
    # Two vets sit in the band with explicit overrides; one vet has none.
    svc._elo_overrides.update({"v1": hi - 5.0, "v2": lo + 5.0})
    before = dict(svc._elo_overrides)

    svc.apply_tiers_subset(position="RB", tiers={"second": ["r2", "r1"]},
                           scope_pids=set(ROOKIES), scoring_format="1qb_ppr")

    for pid in VETS:
        assert svc._elo_overrides.get(pid) == before.get(pid), pid
    assert "v3" not in svc._elo_overrides          # no override before ⇒ none after
    assert set(svc._elo_overrides) == set(before) | {"r1", "r2"}


def test_m2_07_the_equivalence_bar(db):
    """T-M2-07 (D2/D3) — a scoped pid lands at EXACTLY the Elo the equivalent
    full-band `apply_tiers` on the merged order `M` would give it."""
    svc = _service()
    lo, hi = _band(svc)
    svc._elo_overrides.update({"v1": hi - 5.0, "v2": lo + 5.0, "v4": (lo + hi) / 2})

    clone = _service()
    clone._elo_overrides.update(dict(svc._elo_overrides))

    merged = svc.apply_tiers_subset(
        position="RB", tiers={"second": ["r2", "r1"]},
        scope_pids=set(ROOKIES), scoring_format="1qb_ppr")

    assert "second" in merged
    M = merged["second"]
    assert set(M) >= {"r1", "r2", "v1", "v2", "v4"}
    assert len(M) == len(set(M))                    # no pid twice

    clone.apply_tiers(position="RB", tiers={"second": M},
                      scoring_format="1qb_ppr")
    for pid in ("r1", "r2"):
        assert svc._elo_overrides[pid] == clone._elo_overrides[pid]


def test_m2_07b_scoped_spread_is_over_the_full_list_not_the_subset(db):
    """The rejected 'naive scoped-list spread' would pin the top rookie at the
    band ceiling. Over the merged list it cannot, because vets outrank it."""
    svc = _service()
    lo, hi = _band(svc)
    # Four vets hold the TOP of the band; the two rookies currently sit below
    # all of them. A scoped-list-only spread would still pin r1 at `hi`.
    svc._elo_overrides.update({f"v{i}": hi - i for i in range(1, 5)})
    svc._elo_overrides.update({"r1": lo + 20.0, "r2": lo + 10.0})
    svc.apply_tiers_subset(position="RB", tiers={"second": ["r1", "r2"]},
                           scope_pids=set(ROOKIES), scoring_format="1qb_ppr")
    assert svc._elo_overrides["r1"] < hi
    assert svc._elo_overrides["r1"] < svc._elo_overrides["v1"]
    assert svc._elo_overrides["r1"] > svc._elo_overrides["r2"]


def test_m2_08_scoped_save_holds_the_visible_unselected_rookie(db):
    """T-M2-08 (D-160 hold contract, was O4/#161 demote-scoping) — a scoped
    save mutates only the assigned (and cleared) scoped pids. A visible-but-
    unselected rookie HOLDS his value/override state, and an unshown vet is
    NEVER touched."""
    svc = _service()
    lo, hi = _band(svc)
    svc._elo_overrides.update({"v1": hi - 5.0, "r5": lo + 15.0})
    svc.apply_tiers_subset(
        position="RB", tiers={"second": ["r1"]}, scope_pids=set(ROOKIES),
        scoring_format="1qb_ppr")
    assert svc._elo_overrides["r5"] == lo + 15.0       # visible, unselected: held
    assert svc._elo_overrides["v1"] == hi - 5.0        # untouched
    assert "v2" not in svc._elo_overrides


def test_m2_08b_clears_are_scoped_too(db):
    svc = _service()
    svc._elo_overrides.update({"v1": 1700.0, "r5": 1650.0})
    svc.apply_tiers_subset(
        position="RB", tiers={"second": ["r1"]}, scope_pids=set(ROOKIES),
        scoring_format="1qb_ppr", cleared_pids=["r5", "v1"])
    assert "r5" not in svc._elo_overrides
    assert svc._elo_overrides["v1"] == 1700.0


def test_m2_09_promotion_and_demotion_anchor_at_the_band_edges(db):
    """T-M2-09 (§4.3 step 2) — a scoped pid whose current value is above the
    band's `hi` anchors at the TOP of the merge; below `lo`, at the bottom."""
    svc = _service()
    lo, hi = _band(svc)
    # Three incumbents spread through the band.
    svc._elo_overrides.update({"v1": hi - 2.0, "v2": (lo + hi) / 2, "v3": lo + 2.0})
    # r1 comes from far above the band, r2 from far below.
    svc._elo_overrides.update({"r1": hi + 400.0, "r2": lo - 400.0})

    merged = svc.apply_tiers_subset(
        position="RB", tiers={"second": ["r1", "r2"]},
        scope_pids=set(ROOKIES), scoring_format="1qb_ppr")
    M = merged["second"]
    assert M[0] == "r1"
    assert M[-1] == "r2"


def test_m2_09b_empty_scoped_tier_writes_nothing(db):
    svc = _service()
    before = dict(svc._elo_overrides)
    merged = svc.apply_tiers_subset(
        position="RB", tiers={"second": ["v1", "v2"]},   # no scoped pids
        scope_pids=set(ROOKIES), scoring_format="1qb_ppr")
    assert merged == {}
    assert svc._elo_overrides == before


def test_m2_09c_unknown_tier_name_is_skipped(db):
    svc = _service()
    before = dict(svc._elo_overrides)
    assert svc.apply_tiers_subset(
        position="RB", tiers={"not_a_tier": ["r1"]},
        scope_pids=set(ROOKIES), scoring_format="1qb_ppr") == {}
    assert svc._elo_overrides == before


# ═══════════════════════════════════════════════════════════════════════════
# Route-level fixture — the seam in server.py
# ═══════════════════════════════════════════════════════════════════════════

class _FakeService:
    """Serves a fixed board. The seam runs on the SERIALIZED dicts, so the
    ranking math is irrelevant to the route tests."""

    def __init__(self, players):
        self._players = players
        self._elo_overrides = {}
        self.applied = []
        self.subset_calls = []

    def _pool(self, position=None):
        return list(self._players)

    def get_rankings(self, position=None):
        return RankSet(
            position=position,
            rankings=[RankedPlayer(p, 1900.0 - 10 * i, 1, 0, i + 1)
                      for i, p in enumerate(self._players)],
            interaction_count=0, threshold=10, threshold_met=False,
            version=1, computed_at="2026-08-06T00:00:00Z",
        )

    def get_next_trio(self, position=None, skipped_player_ids=None,
                      scoped=False):
        pool = [p for p in self._players
                if p.id not in (skipped_player_ids or set())]
        if len(pool) < 3:
            raise ValueError(f"Need at least 3 players for position={position!r}")
        return MatchupTrio(pool[0], pool[1], pool[2], reasoning="test")

    def _tier_info(self, position=None):
        return {}

    def apply_tiers(self, **kw):
        self.applied.append(kw)

    def apply_tiers_subset(self, **kw):
        self.subset_calls.append(kw)
        return {}


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(users_table.insert().values(
            sleeper_user_id=UID, created_at="2026-08-06T00:00:00+00:00"))
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE_ID, user_id=UID, name="M2",
            season=SEASON, total_rosters=12, platform="sleeper"))
        for pid in ROOKIES:
            conn.execute(players_table.insert().values(
                player_id=pid, full_name=f"Player {pid}", position="RB",
                team="AAA", years_exp=0, rookie_year=SEASON))
        for pid in VETS:
            conn.execute(players_table.insert().values(
                player_id=pid, full_name=f"Player {pid}", position="RB",
                team="BBB", years_exp=5, rookie_year="2021"))

    svc = _FakeService(_mixed_pool())
    sess = {"verified": True,
        "user_id": UID,
        "active_format": "1qb_ppr",
        "last_active": 0.0,
        "service": svc,
        "league": League(league_id=LEAGUE_ID, name="M2",
                         platform="sleeper", members=[]),
        "user_roster": [],
        # `_require_initialized_session` (the save route) wants these present.
        "players": _mixed_pool(),
        "trade_svc": MagicMock(),
    }

    flags = {"ranks.rookie_subset"}
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags), \
         patch.object(server, "touch_user_activity", MagicMock()):
        server._invalidate_rookie_ids_memo()
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield c, flags, svc
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            server._invalidate_rookie_ids_memo()
            server._invalidate_draft_context_cache()


def _get(c, path, expect=200):
    r = c.get(path, headers={"X-Session-Token": TOKEN})
    assert r.status_code == expect, r.data
    return json.loads(r.data)


# ═══════════════════════════════════════════════════════════════════════════
# T-M2-12 — the golden diff (D4)
# ═══════════════════════════════════════════════════════════════════════════

def test_m2_12_flag_off_is_byte_identical(client):
    """T-M2-12 (D4) — same build, flag on vs off, data held constant ⇒ the
    responses are byte-identical. Structural, not incidental: with the flag
    off `_requested_scope` never reads the parameter."""
    c, flags, _ = client
    on_plain = c.get("/api/rankings?position=RB",
                     headers={"X-Session-Token": TOKEN}).data
    on_trio = c.get("/api/trio?position=RB",
                    headers={"X-Session-Token": TOKEN}).data
    flags.discard("ranks.rookie_subset")
    off_plain = c.get("/api/rankings?position=RB",
                      headers={"X-Session-Token": TOKEN}).data
    off_trio = c.get("/api/trio?position=RB",
                     headers={"X-Session-Token": TOKEN}).data
    assert on_plain == off_plain
    assert on_trio == off_trio

    # …and with the flag OFF the parameter is inert, not an error.
    scoped_off = c.get("/api/rankings?position=RB&scope=rookie",
                       headers={"X-Session-Token": TOKEN}).data
    assert scoped_off == off_plain
    assert c.get("/api/rankings?position=RB&scope=nonsense",
                 headers={"X-Session-Token": TOKEN}).data == off_plain


def test_m2_12b_bad_scope_is_rejected_when_the_flag_is_on(client):
    c, _, _ = client
    r = c.get("/api/rankings?position=RB&scope=nonsense",
              headers={"X-Session-Token": TOKEN})
    assert r.status_code == 400
    assert json.loads(r.data)["error"] == "bad_scope"


# ═══════════════════════════════════════════════════════════════════════════
# The read seam
# ═══════════════════════════════════════════════════════════════════════════

def test_scoped_rankings_return_only_rookies_and_renumber_rank(client):
    c, _, _ = client
    body = _get(c, "/api/rankings?position=RB&scope=rookie")
    ids = [r["id"] for r in body["rankings"]]
    assert ids == ROOKIES                     # relative order preserved
    assert [r["rank"] for r in body["rankings"]] == [1, 2, 3, 4, 5]
    # Elo is untouched by the filter — the view never re-values.
    unscoped = {r["id"]: r["elo"]
                for r in _get(c, "/api/rankings?position=RB")["rankings"]}
    for r in body["rankings"]:
        assert r["elo"] == unscoped[r["id"]]


def test_scoped_rankings_drop_generic_pick_rungs(client):
    """Operator decision O10: NO pick rungs inside rookie scope — players
    only. (The LLD predates the decision and says the opposite.)"""
    c, _, svc = client
    from backend.pick_values import GENERIC_PICK_SEEDS
    rungs = [Player(id=f"generic_pick_{r}_{t.lower()}",
                    name=f"{t} pick", position="RB", team="PICK", age=0,
                    years_experience=0, pick_value=10.0, search_rank=1)
             for (r, t) in list(GENERIC_PICK_SEEDS)[:3]]
    svc._players = _mixed_pool() + rungs
    ids = [r["id"] for r in
           _get(c, "/api/rankings?position=RB&scope=rookie")["rankings"]]
    assert ids == ROOKIES
    assert not any(i.startswith("generic_pick_") for i in ids)


def test_m2_10_class_not_loaded_is_a_typed_200(client):
    """No rows with `rookie_year == season` ⇒ typed empty, never a 400."""
    c, _, _ = client
    with db_module.engine.begin() as conn:
        conn.execute(players_table.delete())
    server._invalidate_rookie_ids_memo()
    body = _get(c, "/api/rankings?position=RB&scope=rookie")
    assert body == {"empty": True, "reason": "class_not_loaded",
                    "position": "RB", "scope": "rookie", "count": 0}


def test_m2_10b_thin_trio_pool_is_a_typed_200_and_unscoped_still_400s(client):
    """T-M2-10 — the scoped trio path returns `200 {empty:true,
    reason:"thin_pool"}`; the unscoped path keeps today's 400 byte-for-byte."""
    c, _, svc = client
    with db_module.engine.begin() as conn:
        conn.execute(players_table.delete().where(
            players_table.c.player_id.in_(["r3", "r4", "r5"])))
    server._invalidate_rookie_ids_memo()

    body = _get(c, "/api/trio?position=RB&scope=rookie")
    assert body == {"empty": True, "reason": "thin_pool",
                    "position": "RB", "scope": "rookie", "count": 2}

    # Unscoped, on a genuinely thin pool: still a 400.
    svc._players = _mixed_pool()[:2]
    r = c.get("/api/trio?position=RB", headers={"X-Session-Token": TOKEN})
    assert r.status_code == 400
    assert json.loads(r.data) == {"error": "bad_request"}


def test_scoped_trio_serves_only_rookies(client):
    c, _, _ = client
    body = _get(c, "/api/trio?position=RB&scope=rookie")
    for key in ("player_a", "player_b", "player_c"):
        assert body[key]["id"] in ROOKIES


# ═══════════════════════════════════════════════════════════════════════════
# T-M2-11 — the trio lane audit
# ═══════════════════════════════════════════════════════════════════════════

def test_m2_11_cross_position_lane_is_off_under_scope(db):
    """T-M2-11 — `_pick_trio_variety` must never return `cross_pos` under
    scope: that lane reaches across the FULL pool by design and would leak
    vets (and off-position players) into a scoped trio."""
    svc = _service()
    # Force the unlock so the cross-position lane is eligible at all.
    svc._interactions = {p: 999 for p in ("QB", "RB", "WR", "TE")}
    assert svc._trade_unlocked() is True

    unscoped = {svc._pick_trio_variety("RB") for _ in range(500)}
    assert "cross_pos" in unscoped, "fixture no longer exercises the lane"

    scoped = {svc._pick_trio_variety("RB", scoped=True) for _ in range(500)}
    assert "cross_pos" not in scoped


def test_m2_11b_no_non_rookie_ever_appears_in_a_scoped_trio(client):
    c, _, _ = client
    for _ in range(200):
        body = _get(c, "/api/trio?position=RB&scope=rookie")
        for key in ("player_a", "player_b", "player_c"):
            assert body[key]["id"] in ROOKIES


def test_m2_11c_qc_branch_is_skipped_under_scope(client):
    """The QC-trio path builds its own pool and filters only skips — under
    scope it is skipped entirely (a deliberate degradation: QC compliments on
    a thin rookie pool are low-value)."""
    c, flags, _ = client
    flags.add("swipe.qc_compliments")
    called = []
    import backend.smart_matchup_generator as smg
    with patch.object(smg, "find_qc_trio",
                      lambda *a, **k: called.append(1) or None):
        for _ in range(server.QC_TRIO_INTERVAL + 3):
            _get(c, "/api/trio?position=RB&scope=rookie")
    assert called == []


# ═══════════════════════════════════════════════════════════════════════════
# T-M2-05 / T-M2-06 — the scoped SAVE route
# ═══════════════════════════════════════════════════════════════════════════

def _save(c, body, expect=200):
    r = c.post("/api/tiers/save", json=body,
               headers={"X-Session-Token": TOKEN})
    assert r.status_code == expect, r.data
    return json.loads(r.data)


def test_m2_05_scoped_save_never_marks_a_position_complete(client):
    """T-M2-05 (VFF, D3/I-4) — `tiers_saved`/`all_done` are completeness
    markers consumed by LeagueScreen's ranked count, quicksetProgress's cache,
    the web celebration and #244 launch routing. A rookies-only save must not
    trip them: no entry before ⇒ none after."""
    c, _, _ = client
    from backend.database import get_tiers_saved
    assert get_tiers_saved(UID, scoring_format="1qb_ppr") == []

    out = _save(c, {"position": "RB", "tiers": {"second": ["r1", "r2"]},
                    "scope": "rookie", "via": "rookie_tiers"})
    assert out["saved"] == []
    assert out["all_done"] is False
    assert get_tiers_saved(UID, scoring_format="1qb_ppr") == []

    # …while an UNSCOPED save on the same route still marks it, unchanged.
    _save(c, {"position": "RB", "tiers": {"second": ["r1", "r2"]}})
    assert get_tiers_saved(UID, scoring_format="1qb_ppr") == ["RB"]

    # A scoped save AFTER that must not extend the list either.
    _save(c, {"position": "QB", "tiers": {"second": ["r1"]},
              "scope": "rookie", "via": "rookie_quickset"})
    assert get_tiers_saved(UID, scoring_format="1qb_ppr") == ["RB"]


def test_m2_05b_tiers_status_all_done_is_unchanged_by_a_scoped_save(client):
    c, _, _ = client
    before = _get(c, "/api/tiers/status")
    _save(c, {"position": "RB", "tiers": {"second": ["r1"]},
              "scope": "rookie", "via": "rookie_tiers"})
    assert _get(c, "/api/tiers/status") == before


def test_m2_06_scoped_save_publishes_the_full_board_and_never_passes_scope(client):
    """T-M2-06 (I-5) — leaguemates' trade math reads `member_rankings`. A
    scoped save publishes the FULL board exactly as an unscoped save does, and
    `scope` is never threaded into `upsert_member_rankings`."""
    c, _, _ = client
    seen = []
    with patch.object(server, "upsert_member_rankings",
                      lambda **kw: seen.append(kw)):
        _save(c, {"position": "RB", "tiers": {"second": ["r1", "r2"]},
                  "scope": "rookie", "via": "rookie_tiers"})
    assert len(seen) == 1
    call = seen[0]
    assert "scope" not in call
    published = {r["player_id"] for r in call["rankings"]}
    assert published == set(ROOKIES) | set(VETS)      # the FULL board


def test_scoped_save_routes_to_the_subset_lane_with_rookie_pids(client):
    c, _, svc = client
    _save(c, {"position": "RB", "tiers": {"second": ["r1", "r2"]},
              "scope": "rookie", "via": "rookie_tiers"})
    assert svc.applied == []
    assert len(svc.subset_calls) == 1
    assert svc.subset_calls[0]["scope_pids"] == set(ROOKIES)


def test_unscoped_save_is_untouched_when_the_flag_is_on(client):
    c, _, svc = client
    _save(c, {"position": "RB", "tiers": {"second": ["r1", "r2"]}})
    assert svc.subset_calls == []
    assert len(svc.applied) == 1


def test_scope_in_the_save_body_is_ignored_when_the_flag_is_off(client):
    c, flags, svc = client
    flags.discard("ranks.rookie_subset")
    _save(c, {"position": "RB", "tiers": {"second": ["r1"]}, "scope": "rookie"})
    assert svc.subset_calls == []
    assert len(svc.applied) == 1


def test_snapshot_is_taken_before_the_first_scoped_save(client):
    """The snapshot is the recovery path for a damaged board — it must exist
    before the first partial write, and it must not be re-taken afterwards."""
    c, _, _ = client
    save_tier_overrides(UID, {"v1": 1700.0}, scoring_format="1qb_ppr")
    assert load_tier_override_snapshot(UID) is None

    _save(c, {"position": "RB", "tiers": {"second": ["r1"]},
              "scope": "rookie", "via": "rookie_tiers"})
    snap = load_tier_override_snapshot(UID)
    assert snap is not None
    assert snap["formats"]["1qb_ppr"] == {"v1": 1700.0}

    _save(c, {"position": "RB", "tiers": {"second": ["r2"]},
              "scope": "rookie", "via": "rookie_tiers"})
    assert load_tier_override_snapshot(UID) == snap     # idempotent


def test_unscoped_save_does_not_take_a_snapshot(client):
    c, _, _ = client
    _save(c, {"position": "RB", "tiers": {"second": ["r1"]}})
    assert load_tier_override_snapshot(UID) is None


def test_rookie_via_tags_are_recorded_and_do_not_fire_quickset_completed(client):
    """`via:'rookie_*'` is the forensic tag the restore procedure keys off
    (KD-10). It extends the whitelist rather than replacing it, and it must
    NOT be mistaken for a QuickSet position completion."""
    c, _, _ = client
    events = []
    with patch.object(server, "record_event",
                      lambda uid, name, **kw: events.append((name, kw))):
        _save(c, {"position": "RB", "tiers": {"second": ["r1"]},
                  "scope": "rookie", "via": "rookie_quickset"})
    names = [n for n, _ in events]
    assert "quickset_completed" not in names
    tier_save = next(kw for n, kw in events if n == "tier_save")
    assert tier_save["props"]["via"] == "rookie_quickset"


def test_unknown_via_still_falls_back_to_tiers(client):
    c, _, _ = client
    events = []
    with patch.object(server, "record_event",
                      lambda uid, name, **kw: events.append((name, kw))):
        _save(c, {"position": "RB", "tiers": {"second": ["r1"]},
                  "via": "who_knows"})
    tier_save = next(kw for n, kw in events if n == "tier_save")
    assert tier_save["props"]["via"] == "tiers"
