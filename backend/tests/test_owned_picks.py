"""Owned draft picks in calculator + suggestions (#158 / #170 / #171).

Covers the revived Sleeper sync (grid + traded overlay, 4-round leagues,
double-traded picks), MFL normalization into the same store, the value-scale
reconciliation (pool_value on the generic-ladder scale), /api/trade/evaluate
resolving league-pick ids, the capped suggestion-pool injection helper, and
flag-off parity.
"""
import json

import pytest

import backend.server as srv
import backend.database as db
import backend.trade_service as ts
from backend.pick_values import pick_pool_value, GENERIC_PICK_SEEDS, YEAR_DISCOUNT


# ── Value-scale reconciliation (FR-4) ──────────────────────────────────────

def test_pool_value_reconciles_with_generic_mid_twin():
    # A league 1st at years_out=0 must equal the generic 'Mid 1st' pool value
    # exactly (reconciled by construction).
    assert pick_pool_value(1, 0) == round(ts.elo_to_value(GENERIC_PICK_SEEDS[(1, "Mid")]), 1)
    assert pick_pool_value(2, 0) == round(ts.elo_to_value(GENERIC_PICK_SEEDS[(2, "Mid")]), 1)


def test_pool_value_year_discount_is_monotonic():
    vals = [pick_pool_value(1, y) for y in range(0, 4)]
    assert vals == sorted(vals, reverse=True)          # strictly decreasing
    # discount applied in value space at the configured rate
    assert pick_pool_value(1, 1) == round(pick_pool_value(1, 0) * YEAR_DISCOUNT, 1)


def test_pool_value_clamps_deep_rounds():
    # rounds beyond the ladder clamp to the (4,'Mid') seed, never crash.
    assert pick_pool_value(9, 0) == pick_pool_value(4, 0)


def test_pick_asset_round_trips_pool_value_through_engine():
    # The injected PICK pseudo-player's pick_value is set so dynasty_value's
    # PICK bridge reproduces pool_value exactly (engine untouched).
    pool_v = pick_pool_value(1, 0)
    inv = (ts.value_to_elo(pool_v) - 1200.0) / 6.0

    class _Pick:
        position = "PICK"
        pick_value = inv
        search_rank = None
    assert ts.dynasty_value(_Pick()) == pytest.approx(pool_v, abs=1.0)


# ── Sleeper sync: grid + traded overlay (FR-1) ─────────────────────────────

_LEAGUE = "test_owned_picks_sleeper"


@pytest.fixture
def _clean_league():
    yield _LEAGUE
    db.replace_draft_picks(_LEAGUE, [])   # tear down synthetic rows


def test_sync_builds_full_grid_with_pool_value_and_platform(_clean_league):
    rows = db.sync_draft_picks(
        league_id=_LEAGUE,
        roster_ids=[1, 2],
        traded_picks=[],
        roster_id_to_user={"1": "u1", "2": "u2"},
        user_id_to_name={"u1": "Alice", "u2": "Bob"},
        current_season=2026,
        rounds=4,                 # 4-round league (the plan's dropped-4th bug)
        seasons_ahead=3,
        league_size=12,
    )
    # 2 rosters × 4 seasons (2026..2029) × 4 rounds = 32 picks
    assert len(rows) == 2 * 4 * 4
    # 4th-round picks are NOT dropped
    assert any(r["round"] == 4 for r in rows)
    # every row carries the new fields
    for r in rows:
        assert r["platform"] == "sleeper"
        assert r["pool_value"] is not None
    # a current-season 1st reconciles with the generic Mid-1st value
    cur_first = next(r for r in rows if r["round"] == 1 and r["season"] == 2026)
    assert cur_first["pool_value"] == pick_pool_value(1, 0)


def test_traded_pick_attributes_to_final_owner(_clean_league):
    # roster 1's 2026 1st, traded (roster_id=1 is original, owner_id=2 current).
    db.sync_draft_picks(
        league_id=_LEAGUE,
        roster_ids=[1, 2],
        traded_picks=[
            {"season": "2026", "round": 1, "roster_id": 1,
             "owner_id": 2, "previous_owner_id": 1},
        ],
        roster_id_to_user={"1": "u1", "2": "u2"},
        user_id_to_name={"u1": "Alice", "u2": "Bob"},
        current_season=2026, rounds=3, seasons_ahead=3,
    )
    picks = db.load_draft_picks(_LEAGUE)
    pk = next(p for p in picks
              if p["season"] == 2026 and p["round"] == 1 and p["original_roster_id"] == "1")
    assert pk["owner_user_id"] == "u2"        # current holder
    assert pk["original_user_id"] == "u1"     # identity pinned to original
    assert pk["is_traded"] == 1


def test_double_traded_pick_resolves_to_last_owner(_clean_league):
    # Two hops for the same pick — final owner_id wins (previous_owner_id ignored).
    db.sync_draft_picks(
        league_id=_LEAGUE,
        roster_ids=[1, 2, 3],
        traded_picks=[
            {"season": "2026", "round": 1, "roster_id": 1, "owner_id": 2},
            {"season": "2026", "round": 1, "roster_id": 1, "owner_id": 3},
        ],
        roster_id_to_user={"1": "u1", "2": "u2", "3": "u3"},
        user_id_to_name={"u1": "A", "u2": "B", "u3": "C"},
        current_season=2026, rounds=3, seasons_ahead=3,
    )
    picks = db.load_draft_picks(_LEAGUE)
    pk = next(p for p in picks
              if p["season"] == 2026 and p["round"] == 1 and p["original_roster_id"] == "1")
    assert pk["owner_user_id"] == "u3"


# ── #220 — a flaked Sleeper read must never wipe the pick grid ─────────────
# sync_draft_picks REPLACE-syncs, so the daemon feeding it an empty rosters
# list (the only real producer is an upstream Sleeper fetch failure) deleted
# every pick the league had — League Summary, suggestions and the calculator
# then showed no draft capital until the next successful init. The sync now
# no-ops on empty roster_ids, and the daemon step (_sync_sleeper_owned_picks)
# skips outright when the rosters or meta read is unavailable.

def _seed_grid(league_id):
    return db.sync_draft_picks(
        league_id=league_id, roster_ids=[1, 2], traded_picks=[],
        roster_id_to_user={"1": "u1", "2": "u2"},
        user_id_to_name={"u1": "Alice", "u2": "Bob"},
        current_season=2026, rounds=4, seasons_ahead=3,
    )


def test_sync_empty_roster_ids_keeps_prior_snapshot(_clean_league):
    before = _seed_grid(_LEAGUE)
    assert len(before) == 32
    # The pre-#220 behavior: an empty roster list replace-synced to nothing.
    out = db.sync_draft_picks(
        league_id=_LEAGUE, roster_ids=[], traded_picks=[],
        roster_id_to_user={}, user_id_to_name={},
        current_season=2026, rounds=4, seasons_ahead=3,
    )
    assert out == []
    assert len(db.load_draft_picks(_LEAGUE)) == 32   # snapshot preserved


def test_daemon_step_skips_when_sleeper_rosters_unavailable(
        _clean_league, monkeypatch):
    _seed_grid(_LEAGUE)
    monkeypatch.setattr(srv, "_fetch_sleeper_traded_picks", lambda lid: [])
    monkeypatch.setattr(srv, "_fetch_league_rosters", lambda lid: None)
    monkeypatch.setattr(srv, "_fetch_sleeper_league_meta",
                        lambda lid: {"season": "2026", "total_rosters": 2,
                                     "settings": {"draft_rounds": 4}})
    assert srv._sync_sleeper_owned_picks(_LEAGUE, {}, "1qb_ppr") is None
    assert len(db.load_draft_picks(_LEAGUE)) == 32   # snapshot preserved


def test_daemon_step_skips_when_league_meta_unavailable(
        _clean_league, monkeypatch):
    _seed_grid(_LEAGUE)
    monkeypatch.setattr(srv, "_fetch_sleeper_traded_picks", lambda lid: [])
    monkeypatch.setattr(
        srv, "_fetch_league_rosters",
        lambda lid: [{"roster_id": 1, "owner_id": "u1"},
                     {"roster_id": 2, "owner_id": "u2"}])
    monkeypatch.setattr(srv, "_fetch_sleeper_league_meta", lambda lid: None)
    assert srv._sync_sleeper_owned_picks(_LEAGUE, {}, "1qb_ppr") is None
    assert len(db.load_draft_picks(_LEAGUE)) == 32   # snapshot preserved


# ── #228 — completed rookie draft hides that season's picks ────────────────

def test_sync_excludes_completed_draft_season(_clean_league):
    rows = db.sync_draft_picks(
        league_id=_LEAGUE, roster_ids=[1, 2],
        traded_picks=[
            # a traded CURRENT-season pick must be excluded too
            {"season": "2026", "round": 1, "roster_id": 1, "owner_id": 2},
            # future-season trades keep applying
            {"season": "2027", "round": 1, "roster_id": 1, "owner_id": 2},
        ],
        roster_id_to_user={"1": "u1", "2": "u2"},
        user_id_to_name={"u1": "Alice", "u2": "Bob"},
        current_season=2026, rounds=4, seasons_ahead=3,
        exclude_seasons={2026},
    )
    assert all(r["season"] != 2026 for r in rows)
    # 2 rosters × 3 remaining seasons (2027..2029) × 4 rounds
    assert len(rows) == 2 * 3 * 4
    traded = next(r for r in rows if r["season"] == 2027 and r["round"] == 1
                  and r["original_roster_id"] == "1")
    assert traded["owner_user_id"] == "u2" and traded["is_traded"] == 1


def test_replace_sync_cleans_stale_current_season_rows(_clean_league):
    # Synced BEFORE the draft: 2026 rows exist…
    _seed_grid(_LEAGUE)
    assert any(p["season"] == 2026 for p in db.load_draft_picks(_LEAGUE))
    # …the draft completes; the next sync excludes 2026 and the replace-sync
    # semantics clean the stale rows.
    db.sync_draft_picks(
        league_id=_LEAGUE, roster_ids=[1, 2], traded_picks=[],
        roster_id_to_user={"1": "u1", "2": "u2"},
        user_id_to_name={"u1": "Alice", "u2": "Bob"},
        current_season=2026, rounds=4, seasons_ahead=3,
        exclude_seasons={2026},
    )
    picks = db.load_draft_picks(_LEAGUE)
    assert picks and all(p["season"] != 2026 for p in picks)


def test_daemon_step_excludes_current_season_when_draft_complete(
        _clean_league, monkeypatch):
    monkeypatch.setattr(srv, "_fetch_sleeper_traded_picks", lambda lid: [])
    monkeypatch.setattr(
        srv, "_fetch_league_rosters",
        lambda lid: [{"roster_id": 1, "owner_id": "u1"},
                     {"roster_id": 2, "owner_id": "u2"}])
    monkeypatch.setattr(srv, "_fetch_sleeper_league_meta",
                        lambda lid: {"season": "2026", "total_rosters": 2,
                                     "settings": {"draft_rounds": 4}})
    monkeypatch.setattr(srv, "_fetch_sleeper_drafts",
                        lambda lid: [{"draft_id": "d1", "status": "complete",
                                      "season": "2026", "type": "linear"}])
    rows = srv._sync_sleeper_owned_picks(_LEAGUE, {"u1": "Alice"}, "1qb_ppr")
    assert rows is not None
    assert all(r["season"] != 2026 for r in rows)
    assert any(r["season"] == 2027 for r in rows)     # future seasons intact


def test_daemon_step_no_exclusion_when_draft_pending_or_flaked(
        _clean_league, monkeypatch):
    monkeypatch.setattr(srv, "_fetch_sleeper_traded_picks", lambda lid: [])
    monkeypatch.setattr(
        srv, "_fetch_league_rosters",
        lambda lid: [{"roster_id": 1, "owner_id": "u1"},
                     {"roster_id": 2, "owner_id": "u2"}])
    monkeypatch.setattr(srv, "_fetch_sleeper_league_meta",
                        lambda lid: {"season": "2026", "total_rosters": 2,
                                     "settings": {"draft_rounds": 4}})
    # pre_draft status → keep current-season picks
    monkeypatch.setattr(srv, "_fetch_sleeper_drafts",
                        lambda lid: [{"draft_id": "d1", "status": "pre_draft",
                                      "season": "2026", "type": "linear"}])
    rows = srv._sync_sleeper_owned_picks(_LEAGUE, {}, "1qb_ppr")
    assert any(r["season"] == 2026 for r in rows)
    # drafts read flaked ([]) → degrade to today's behavior (no exclusion)
    monkeypatch.setattr(srv, "_fetch_sleeper_drafts", lambda lid: [])
    rows = srv._sync_sleeper_owned_picks(_LEAGUE, {}, "1qb_ppr")
    assert any(r["season"] == 2026 for r in rows)


# ── MFL normalization (FR-2) ───────────────────────────────────────────────

_MFL_LEAGUE = "test_owned_picks_mfl"


@pytest.fixture
def _mfl_seeded():
    db.upsert_platform_league(
        league_id=_MFL_LEAGUE, user_id="link_user", name="MFL Test",
        platform="mfl", season=2026, auth="public", my_team="0001",
        total_rosters=12, host="www44.myfantasyleague.com",
        future_picks=[
            {"franchise_id": "0001", "year": "2027", "round": "1",
             "original_owner": "0001"},                       # own pick
            {"franchise_id": "0001", "year": "2027", "round": "2",
             "original_owner": "0002"},                       # acquired from 0002
        ],
    )
    db.replace_espn_league_members(_MFL_LEAGUE, [
        {"user_id": "link_user", "username": "Me", "display_name": "Me", "player_ids": []},
        {"user_id": srv._mfl_member_id(_MFL_LEAGUE, "0002"),
         "username": "Rival", "display_name": "Rival", "player_ids": []},
    ])
    yield _MFL_LEAGUE
    db.replace_draft_picks(_MFL_LEAGUE, [])


def test_mfl_normalization_same_row_shape(_mfl_seeded):
    n = srv._sync_mfl_owned_picks(_MFL_LEAGUE)
    assert n == 2
    picks = db.load_draft_picks(_MFL_LEAGUE)
    assert all(p["platform"] == "mfl" for p in picks)
    assert all(p["pool_value"] is not None for p in picks)
    # own pick → linking user, not traded
    own = next(p for p in picks if p["round"] == 1)
    assert own["owner_user_id"] == "link_user"
    assert own["is_traded"] == 0
    # acquired pick → current owner is linking user, original is the rival, traded
    acq = next(p for p in picks if p["round"] == 2)
    assert acq["owner_user_id"] == "link_user"
    assert acq["original_user_id"] == srv._mfl_member_id(_MFL_LEAGUE, "0002")
    assert acq["is_traded"] == 1


# ── #207/#228 MFL parity — verdict-gated current-season exclusion ──────────
# Sleeper's #228 exclusion lives in the sync/write path
# (_sync_sleeper_owned_picks → sync_draft_picks(exclude_seasons=…)); MFL's
# twin write path is _sync_mfl_owned_picks, so the rule lands at the SAME
# layer for both platforms and every load_draft_picks consumer stays untouched.
# The verdict comes from the #207 leagues.draft_status cache (no network), and
# the fail-safe is #228's: only a positive `drafted` excludes anything.

_MFL_VERDICT = "test_owned_picks_mfl_verdict"


@pytest.fixture
def _mfl_verdict_seeded():
    def _seed(status=None, confidence=None):
        db.upsert_platform_league(
            league_id=_MFL_VERDICT, user_id="link_user", name="MFL Verdict",
            platform="mfl", season=2026, auth="public", my_team="0001",
            total_rosters=12, host="www44.myfantasyleague.com",
            future_picks=[
                {"franchise_id": "0001", "year": "2026", "round": "1",
                 "original_owner": "0001"},
                {"franchise_id": "0001", "year": "2026", "round": "2",
                 "original_owner": "0002"},
                {"franchise_id": "0001", "year": "2027", "round": "1",
                 "original_owner": "0001"},
                {"franchise_id": "0001", "year": "2028", "round": "1",
                 "original_owner": "0001"},
            ],
        )
        db.replace_espn_league_members(_MFL_VERDICT, [
            {"user_id": "link_user", "username": "Me", "display_name": "Me",
             "player_ids": []},
            {"user_id": srv._mfl_member_id(_MFL_VERDICT, "0002"),
             "username": "Rival", "display_name": "Rival", "player_ids": []},
        ])
        # NULL status = never checked; anything else goes through the #207 cache.
        db.set_league_draft_status(_MFL_VERDICT, status, confidence)
        return _MFL_VERDICT
    yield _seed
    db.replace_draft_picks(_MFL_VERDICT, [])
    db.set_league_draft_status(_MFL_VERDICT, None, None)


def test_mfl_drafted_verdict_excludes_only_the_current_season(
        _mfl_verdict_seeded):
    _mfl_verdict_seeded(status="drafted", confidence="high")
    assert srv._sync_mfl_owned_picks(_MFL_VERDICT) == 2
    seasons = sorted(p["season"] for p in db.load_draft_picks(_MFL_VERDICT))
    assert seasons == [2027, 2028]          # 2026 gone, future years intact


@pytest.mark.parametrize("status,confidence", [
    ("not_drafted", "high"),
    ("unknown", "low"),
    ("drafted", None),        # confidence gates nothing — status is the gate
    (None, None),             # never checked
])
def test_mfl_exclusion_fail_safe_matches_228(status, confidence,
                                             _mfl_verdict_seeded):
    """Only a positive `drafted` hides anything. A phantom current-year pick
    is visible and self-correcting; a silently hidden real asset is not."""
    _mfl_verdict_seeded(status=status, confidence=confidence)
    srv._sync_mfl_owned_picks(_MFL_VERDICT)
    seasons = sorted(p["season"] for p in db.load_draft_picks(_MFL_VERDICT))
    expected = [2027, 2028] if status == "drafted" else [2026, 2026, 2027, 2028]
    assert seasons == expected


def test_mfl_replace_sync_cleans_stale_current_season_rows(
        _mfl_verdict_seeded):
    """A league linked BEFORE its draft: the stale 2026 rows disappear on the
    first normalization after the verdict flips — no repair job (#228 parity)."""
    _mfl_verdict_seeded()                          # never checked → 4 rows
    assert srv._sync_mfl_owned_picks(_MFL_VERDICT) == 4
    assert any(p["season"] == 2026 for p in db.load_draft_picks(_MFL_VERDICT))
    db.set_league_draft_status(_MFL_VERDICT, "drafted", "high")
    assert srv._sync_mfl_owned_picks(_MFL_VERDICT) == 2
    picks = db.load_draft_picks(_MFL_VERDICT)
    assert picks and all(p["season"] != 2026 for p in picks)


def test_current_season_picks_visible_is_the_one_shared_predicate():
    """The #207 rung relabel and the MFL owned-pick exclusion both call this,
    so the two platforms' asymmetry cannot drift apart."""
    assert srv._current_season_picks_visible("drafted", "high") is False
    assert srv._current_season_picks_visible("drafted", None) is False
    for st in ("not_drafted", "unknown", None, ""):
        assert srv._current_season_picks_visible(st) is True


def test_cached_verdict_does_not_leak_into_the_sleeper_sync(
        _clean_league, monkeypatch):
    """No change for Sleeper leagues: #228 keeps reading its OWN live drafts
    fetch, so a cached `drafted` row cannot start hiding Sleeper picks (and a
    cached `not_drafted` cannot start un-hiding them)."""
    db.upsert_league(league_id=_LEAGUE, user_id="u1", name="Sleeper Test",
                     season="2026", user_player_ids=[], opponent_rosters=[])
    db.set_league_draft_status(_LEAGUE, "drafted", "high")
    assert db.get_league_draft_context(_LEAGUE)["status"] == "drafted"
    try:
        monkeypatch.setattr(srv, "_fetch_sleeper_traded_picks", lambda lid: [])
        monkeypatch.setattr(
            srv, "_fetch_league_rosters",
            lambda lid: [{"roster_id": 1, "owner_id": "u1"},
                         {"roster_id": 2, "owner_id": "u2"}])
        monkeypatch.setattr(srv, "_fetch_sleeper_league_meta",
                            lambda lid: {"season": "2026", "total_rosters": 2,
                                         "settings": {"draft_rounds": 4}})
        monkeypatch.setattr(srv, "_fetch_sleeper_drafts",
                            lambda lid: [{"draft_id": "d1",
                                          "status": "pre_draft",
                                          "season": "2026", "type": "linear"}])
        rows = srv._sync_sleeper_owned_picks(_LEAGUE, {}, "1qb_ppr")
        assert rows is not None and any(r["season"] == 2026 for r in rows)
    finally:
        db.set_league_draft_status(_LEAGUE, None, None)


# ── #200 — numeric platform ids must not hit the Sleeper grid sync ─────────
# MFL native league ids are NUMERIC, so session-init's old
# `str(league_id).isdigit()` gate misrouted them into the Sleeper pick sync:
# the Sleeper fetches came back empty and sync_draft_picks REPLACE-synced the
# league to an EMPTY grid, wiping the picks the MFL link normalized (League
# Summary then showed no draft capital). The daemon now discriminates with
# is_linked_platform_league and re-runs _sync_mfl_owned_picks instead, which
# also self-heals leagues clobbered before the guard.

_MFL_NUMERIC = "990062846"          # numeric, like real MFL ids


@pytest.fixture
def _mfl_numeric_seeded():
    db.upsert_platform_league(
        league_id=_MFL_NUMERIC, user_id="link_user", name="MFL Numeric",
        platform="mfl", season=2026, auth="public", my_team="0001",
        total_rosters=12, host="www44.myfantasyleague.com",
        future_picks=[
            {"franchise_id": "0001", "year": "2027", "round": "1",
             "original_owner": "0001"},
            {"franchise_id": "0001", "year": "2027", "round": "2",
             "original_owner": "0002"},
        ],
    )
    db.replace_espn_league_members(_MFL_NUMERIC, [
        {"user_id": "link_user", "username": "Me", "display_name": "Me", "player_ids": []},
        {"user_id": srv._mfl_member_id(_MFL_NUMERIC, "0002"),
         "username": "Rival", "display_name": "Rival", "player_ids": []},
    ])
    yield _MFL_NUMERIC
    db.replace_draft_picks(_MFL_NUMERIC, [])


def test_numeric_mfl_id_detected_as_platform_league(_mfl_numeric_seeded):
    # The old gate's discriminator says "Sleeper"; the platform lookup — the
    # #149/#150-style guard the daemon now uses — says otherwise.
    assert str(_MFL_NUMERIC).isdigit()
    assert db.is_linked_platform_league(_MFL_NUMERIC) is True


def test_mfl_renormalization_restores_clobbered_picks(_mfl_numeric_seeded):
    # Link-time normalization writes the picks…
    assert srv._sync_mfl_owned_picks(_MFL_NUMERIC) == 2
    assert len(db.load_draft_picks(_MFL_NUMERIC)) == 2
    # …the pre-fix daemon wiped them (replace-sync to an empty grid)…
    db.replace_draft_picks(_MFL_NUMERIC, [])
    assert db.load_draft_picks(_MFL_NUMERIC) == []
    # …and the daemon's re-normalization self-heals from the stored raw list.
    assert srv._sync_mfl_owned_picks(_MFL_NUMERIC) == 2
    picks = db.load_draft_picks(_MFL_NUMERIC)
    assert len(picks) == 2
    assert all(p["platform"] == "mfl" and p["pool_value"] is not None
               for p in picks)


# ── /api/trade/evaluate resolves league-pick ids (FR-5) ────────────────────

_EVAL_POOL = [type("P", (), {"id": "stud", "name": "Stud", "position": "WR"})()]
_EVAL_SEED = {"stud": 1800.0}


@pytest.fixture
def _eval_env(monkeypatch):
    monkeypatch.setattr(srv, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(srv.g_universal_by_format, "1qb_ppr",
                        {"players": _EVAL_POOL, "seed": dict(_EVAL_SEED)})
    fake_pick = {
        "pick_id": "L_2027_1_1", "season": 2027, "round": 1,
        "owner_user_id": "u1", "is_traded": 0, "original_username": "",
        "pool_value": pick_pool_value(1, 1),
    }
    monkeypatch.setattr(srv, "load_draft_picks", lambda league_id=None, **k: [fake_pick])
    yield


def test_evaluate_resolves_league_pick_not_dropped(_eval_env):
    with srv.app.test_client() as c:
        r = c.post("/api/trade/evaluate", json={
            "give_player_ids": ["stud"],
            "receive_player_ids": ["L_2027_1_1"],
            "league_id": "L",
        })
    assert r.status_code == 200
    d = r.get_json()
    # the league pick is priced, NOT dropped. Its per-player value is the raw
    # pool_value (package-side totals apply the engine's normal v_max scaling,
    # same as any player — that math is unchanged here).
    assert "L_2027_1_1" not in d["dropped_player_ids"]
    per = {p["player_id"]: p["value"] for p in d["per_player"]}
    assert per["L_2027_1_1"] == pytest.approx(pick_pool_value(1, 1), abs=1.0)
    assert d["receive_value"] > 0


def test_evaluate_without_league_id_still_drops_unknown(_eval_env):
    # No league_id → league picks aren't resolvable → unknown id dropped (parity).
    with srv.app.test_client() as c:
        r = c.post("/api/trade/evaluate", json={
            "give_player_ids": ["stud"],
            "receive_player_ids": ["L_2027_1_1"],
        })
    d = r.get_json()
    assert "L_2027_1_1" in d["dropped_player_ids"]


# ── Suggestion-pool injection helper (FR-6) ────────────────────────────────

def test_owned_pick_assets_caps_and_prices(monkeypatch):
    picks = [
        {"pick_id": f"L_{yr}_{rnd}_1", "season": yr, "round": rnd,
         "owner_user_id": "u1", "is_traded": 0, "original_username": "",
         "pool_value": pick_pool_value(rnd, yr - 2026)}
        for yr in range(2026, 2030) for rnd in range(1, 5)
    ]  # 16 picks for one owner
    monkeypatch.setattr(srv, "load_draft_picks", lambda league_id=None, **k: picks)
    monkeypatch.setattr(srv, "get_config", lambda: {"picks_pool_cap": 6})

    assets = srv._owned_pick_assets("L", "1qb_ppr")
    assert set(assets.keys()) == {"u1"}
    # capped to 6 (top-N by pool_value)
    assert len(assets["u1"]) == 6
    # top asset is the current-season 1st (highest pool_value)
    top = assets["u1"][0]
    assert top.position == "PICK" and top.team == "PICK"
    assert ts.dynasty_value(top) == pytest.approx(pick_pool_value(1, 0), abs=2.0)


def test_owned_pick_assets_cap_zero_returns_empty(monkeypatch):
    monkeypatch.setattr(srv, "load_draft_picks",
                        lambda league_id=None, **k: [
                            {"pick_id": "L_2027_1_1", "season": 2027, "round": 1,
                             "owner_user_id": "u1", "is_traded": 0,
                             "original_username": "", "pool_value": 1000.0}])
    monkeypatch.setattr(srv, "get_config", lambda: {"picks_pool_cap": 0})
    assert srv._owned_pick_assets("L", "1qb_ppr") == {}
