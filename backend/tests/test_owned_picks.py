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
