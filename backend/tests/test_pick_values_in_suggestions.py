"""#185 — pick values must differentiate inside trade suggestions.

Operator symptom: "Cam Ward for a 29 1st, Ward for a 29 2nd, Ward for a 29
3rd — all three shown as fair value with no diff in value."

Root cause: the v2/v3 engine prices assets through Elo maps (consensus
seed_elo + each member's board), NOT through dynasty_value. The #170
owned-pick injection added PICK pseudo-players to rosters/player maps but
never primed those Elo maps, so every pick fell through the engine's
`.get(pid, 1500.0)` default — Elo 1500 ≈ value 1000 for a 1st, 2nd and 3rd
alike, making them indistinguishable and "fair" against any mid-value player.

Fix: server._inject_owned_picks primes seed_map, the user's Elo map and each
member board with each pick's bridged Elo (_pick_asset_elos: 1200 +
6*pick_value == value_to_elo(pool_value)).
"""
import pytest

import backend.server as srv
import backend.trade_service as ts
import backend.feature_flags as ff
from backend.pick_values import pick_pool_value
from backend.trade_optimizer import _consensus_packages, _fairness_v3
from backend.trade_service import League, LeagueMember, TradeService


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


# 2029 picks in a 2026 season → 3 years out. The values the operator should
# have seen (engine value space): R1≈2117, R2≈503, R3≈250. R1 is the FLAT
# current-year price since D-079 (it was 1300 while firsts still decayed);
# rounds 2-3 keep the 0.85/yr they always had. Every number below is derived
# from `pick_pool_value`, never literal, so a retune moves the fixture with
# the ladder instead of silently falsifying this file.
_PICKS = [
    {"pick_id": f"L185_2029_{rnd}_1", "season": 2029, "round": rnd,
     "owner_user_id": "opp", "is_traded": 0, "original_username": "",
     "pool_value": pick_pool_value(rnd, 3)}
    for rnd in (1, 2, 3)
]


def _pick_assets(monkeypatch):
    monkeypatch.setattr(srv, "load_draft_picks", lambda league_id=None, **k: list(_PICKS))
    monkeypatch.setattr(srv, "get_config", lambda: {"picks_pool_cap": 6})
    return srv._owned_pick_assets("L185", "1qb_ppr")


# ── the bridge itself ──────────────────────────────────────────────────────

def test_pick_asset_elos_reproduce_pool_value(monkeypatch):
    elos = srv._pick_asset_elos(_pick_assets(monkeypatch))
    assert len(elos) == 3
    for pk in _PICKS:
        assert ts.elo_to_value(elos[pk["pick_id"]]) == pytest.approx(
            pk["pool_value"], abs=1.0)


# ── injection wiring: every map the engine reads is primed ─────────────────

def test_inject_owned_picks_primes_all_boards(monkeypatch):
    _pick_assets(monkeypatch)   # install the load_draft_picks patch
    players = {"ward": type("P", (), {"id": "ward", "position": "QB"})()}
    svc = TradeService(players=dict(players))
    opp = LeagueMember(user_id="opp", username="opp", roster=["x1"],
                       elo_ratings={"x1": 1600}, has_rankings=True)
    league = League(league_id="L185", name="T", platform="sleeper", members=[opp])
    seed_map = {"ward": 1500.0}
    user_elo = {"ward": 1500.0}

    new_seed, user_roster, n = srv._inject_owned_picks(
        league_id="L185", scoring_format="1qb_ppr", trade_service=svc,
        players_dict=players, seed_map=seed_map, user_elo=user_elo,
        user_id="user", user_roster=["ward"], league=league)

    assert n == 3
    # original seed dict untouched (service._seed must never grow pick ids)
    assert "L185_2029_1_1" not in seed_map
    for pk in _PICKS:
        pid = pk["pick_id"]
        # seed (fairness + give/receive_value), user board, opponent board
        for board in (new_seed, user_elo, opp.elo_ratings):
            assert ts.elo_to_value(board[pid]) == pytest.approx(
                pk["pool_value"], abs=1.0), f"{pid} unpriced on a board"
        assert pid in opp.roster
        assert players[pid].position == "PICK"
    # user's roster untouched by opponent-owned picks
    assert user_roster == ["ward"]


# ── the exact operator symptom, in the engine's own value space ────────────

def test_player_vs_1st_2nd_3rd_differ_materially(monkeypatch):
    """A player against a 2029 1st / 2nd / 3rd must yield materially
    different receive values AND different fairness — pre-fix all three were
    identical (the engine's 1500-Elo default)."""
    assets = _pick_assets(monkeypatch)
    # Ward seeded ≈ a 2029 1st — the operator's mental model. DERIVED from
    # the ladder, because D-079 moved the 2029 1st from ~1300 to ~2117 and a
    # hard-coded 1552.0 quietly turned this into "a mid player vs a 1st".
    seed_map = {"ward": ts.value_to_elo(pick_pool_value(1, 3))}
    seed_map.update(srv._pick_asset_elos(assets))
    seed_value = lambda pid: ts.elo_to_value(seed_map.get(pid, 1500.0))

    rvs, verdicts = {}, {}
    for rnd in (1, 2, 3):
        pid = f"L185_2029_{rnd}_1"
        _gv, rv = _consensus_packages(["ward"], [pid], seed_value)
        fairness, ratio, _, _ = _fairness_v3(["ward"], [pid], seed_value,
                                             None, 0.75)
        rvs[rnd] = rv
        verdicts[rnd] = fairness is not None
    # Materially different values (R1 ≈ 2117, R2 ≈ 503, R3 ≈ 250).
    assert rvs[1] - rvs[2] > 300
    assert rvs[2] - rvs[3] > 100
    assert rvs[1] == pytest.approx(pick_pool_value(1, 3), abs=2.0)
    # And the fairness gate must NOT call all three fair: Ward ≈ a 1st, so
    # the 1st passes while the 3rd is lopsided. (Pre-fix all three were
    # ratio-1.0 "fair".)
    assert verdicts[1] and not verdicts[3]
    assert ratio < 0.75    # the 3rd's point ratio is honestly lopsided


def test_unprimed_seed_reproduces_the_bug():
    """Documents the pre-#185 failure mode: without priming, all three picks
    price identically (the 1500-Elo default) — this is the state the fix
    removes from the live path."""
    seed_value = lambda pid: ts.elo_to_value({"ward": 1500.0}.get(pid, 1500.0))
    rvs = set()
    for rnd in (1, 2, 3):
        _gv, rv = _consensus_packages(["ward"], [f"L185_2029_{rnd}_1"], seed_value)
        rvs.add(round(rv, 1))
    assert len(rvs) == 1     # indistinguishable — the reported symptom


# ── end-to-end through generate_trades (consensus opponent) ────────────────

class _P:
    def __init__(self, pid, position="QB"):
        self.id = pid
        self.name = pid
        self.position = position
        self.team = "TST"
        self.age = 24
        self.search_rank = 60
        self.pick_value = None


def test_generated_cards_price_picks_on_pool_scale(monkeypatch):
    """Full engine pass mirroring the trade job: picks injected + boards
    primed, consensus opponent (the operator's scenario). Any emitted card
    receiving a pick must carry a receive_value on the pool scale — never
    the flat 1500-Elo default — so 1st/2nd/3rd cards can't all read fair."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade_engine.v2": True}
    assets = _pick_assets(monkeypatch)

    # Position-complete roster so the consensus path's need filter doesn't
    # drop PICK returns (position_needs empty ⇒ full receive pool).
    roster_spec = [("ward", "QB"), ("give1", "RB"), ("rb2", "RB"),
                   ("wr1", "WR"), ("wr2", "WR"), ("te1", "TE")]
    players = {pid: _P(pid, pos) for pid, pos in roster_spec}
    svc = TradeService(players=players)
    opp = LeagueMember(user_id="opp", username="opp", roster=[],
                       elo_ratings={}, has_rankings=False)
    league = League(league_id="L185", name="T", platform="sleeper", members=[opp])
    svc.add_league(league)

    # give1 seeded just under a 2029 1st so a 1-for-1 pick return clears the
    # consensus path's user-gain + fairness gates.
    seed_map = {"ward": 1500.0, "give1": 1540.0, "rb2": 1450.0,
                "wr1": 1460.0, "wr2": 1440.0, "te1": 1430.0}
    user_elo = dict(seed_map)
    seed_map, user_roster, _n = srv._inject_owned_picks(
        league_id="L185", scoring_format="1qb_ppr", trade_service=svc,
        players_dict=players, seed_map=seed_map, user_elo=user_elo,
        user_id="user", user_roster=[pid for pid, _ in roster_spec],
        league=league)

    cards = svc.generate_trades(
        user_id="user", user_elo=user_elo, user_roster=user_roster,
        league_id="L185", seed_elo=seed_map, fairness_threshold=0.55,
    )
    pick_cards = [c for c in cards
                  if any(p.startswith("L185_") for p in c.receive_player_ids)]
    assert pick_cards, "engine should offer at least one pick-return card"
    flat_default = round(ts.elo_to_value(1500.0), 1)
    for c in pick_cards:
        assert c.receive_value is not None
        if c.receive_player_ids == [f"L185_2029_1_1"]:
            assert c.receive_value == pytest.approx(pick_pool_value(1, 3), abs=2.0)
        assert c.receive_value != pytest.approx(flat_default, abs=0.5)
