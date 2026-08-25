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
from backend.pick_values import (market_pick_pool_value, pick_pool_value,
                                 priced_pool_value)
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


# 2029 picks in a 2026 season → 3 years out.
#
# TWO SCALES LIVE HERE SINCE D-144 (2026-08-21), and conflating them is how
# this file breaks:
#
#   * `pool_value` on the row is what the league-wide sync path really WRITES:
#     the ladder price, `pick_pool_value(rnd, 3)` — R1 2117.0 (flat since
#     D-079), R2 372.5, R3 249.7.
#   * what the engine SERVES is the market price for that absolute
#     season+round — `market_pick_pool_value(2029, rnd)`, R2 303.9 / R3 210.7
#     (1QB, against the snapshot `conftest.py` pins) — with, SINCE D-161
#     (2026-08-24), the round-1 YoY floor on top of it. A 2029 first no longer
#     takes DP's year discount: it prices at the CURRENT class's first,
#     1859.5, re-asserting D-079's flat-firsts ruling at the market seam.
#     Rounds 2 and 3 are untouched by the floor ("other picks can degrade")
#     and still ride DP's curve, which is why this fixture keeps all three.
#
# The stored column is deliberately left on the ladder, because that is the
# honest fixture: `priced_pool_value` reprices at READ time and never rewrites
# the column, so a row whose stored value already equalled the market price
# would hide the very substitution this file exists to check.
#
# Every expectation below is DERIVED from one of the two functions, never a
# literal, so a retune of either curve moves the fixture with it instead of
# silently falsifying the file.
_PICKS = [
    {"pick_id": f"L185_2029_{rnd}_1", "season": 2029, "round": rnd,
     "owner_user_id": "opp", "is_traded": 0, "original_username": "",
     "pool_value": pick_pool_value(rnd, 3)}
    for rnd in (1, 2, 3)
]


def _served(rnd: int) -> float:
    """What the engine prices a 2029 pick of `rnd` at.

    Reads through `priced_pool_value` — the engine's own seam, with the same
    `slot=None` every future season gets (#273) — rather than reproducing one
    step of the waterfall by hand. That was safe while step 2 WAS the answer;
    since D-161 put the round-1 YoY floor on top of it, reproducing step 2
    here would quietly assert the pre-floor price at four call sites.
    """
    market = market_pick_pool_value(2029, rnd, "1qb_ppr")
    assert market is not None, "the DP snapshot conftest.py pins must reach 2029"
    row = next(p for p in _PICKS if p["round"] == rnd)
    return priced_pool_value(dict(row), scoring_format="1qb_ppr", slot=None)


def test_the_served_price_is_the_market_not_the_stored_ladder():
    """The premise every other test in this file now rests on, asserted once.

    D-144: owned picks price off DynastyProcess, not off the stored ladder
    value. Both curves are exercised so a future change that silently
    reunified them fails here first, with a clear message, rather than
    somewhere downstream in a fairness assertion."""
    for pk in _PICKS:
        stored = pk["pool_value"]
        served = _served(pk["round"])
        assert served != pytest.approx(stored, abs=1.0), pk["pick_id"]
        assert served < stored, "the market is cheaper at every 2029 round"


def _pick_assets(monkeypatch):
    monkeypatch.setattr(srv, "load_draft_picks", lambda league_id=None, **k: list(_PICKS))
    monkeypatch.setattr(srv, "get_config", lambda: {"picks_pool_cap": 6})
    return srv._owned_pick_assets("L185", "1qb_ppr")


# ── the bridge itself ──────────────────────────────────────────────────────

def test_pick_asset_elos_reproduce_pool_value(monkeypatch):
    elos = srv._pick_asset_elos(_pick_assets(monkeypatch))
    assert len(elos) == 3
    for pk in _PICKS:
        # The bridge must reproduce the PRICED value — which is the whole
        # point of #185's inverse. Post-D-144 that is the market price.
        assert ts.elo_to_value(elos[pk["pick_id"]]) == pytest.approx(
            _served(pk["round"]), abs=1.0)


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
                _served(pk["round"]), abs=1.0), f"{pid} unpriced on a board"
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
    # Ward seeded ≈ a 2029 1st — the operator's mental model. DERIVED from the
    # price the engine actually SERVES a 2029 1st at — D-144 moved that off
    # the ladder's 2117.0 onto the market's 1263.0, and D-161's round-1 floor
    # moved it again, to the current class's 1859.5. Seeding him off a
    # hardcoded number would quietly turn this into "a stud vs a 1st" the
    # next time either curve moves, and break the premise.
    seed_map = {"ward": ts.value_to_elo(_served(1))}
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
    # Materially different values. Post-D-161: R1 ≈ 1859.5 (floored to the
    # current class), R2 ≈ 304, R3 ≈ 211 (DP's curve, unfloored).
    #
    # THE R2/R3 BOUND MOVED, AND THAT IS A REAL FINDING, NOT A LOOSENED
    # TOLERANCE. On the ladder a 2029 2nd and 3rd sat 122.8 apart; on the
    # market they sit 93.2 apart, because DP's curve compresses the deep-future
    # middle rounds harder than our uniform 0.85/yr discount does. The bound
    # is therefore restated against the CURVE — `_served(2) - _served(3)` —
    # rather than against a literal that would have to be re-guessed on every
    # retune. The engine still distinguishes them, which is all #185 claimed.
    assert rvs[1] - rvs[2] > 300
    assert rvs[2] - rvs[3] == pytest.approx(_served(2) - _served(3), abs=2.0)
    assert rvs[2] > rvs[3]
    assert rvs[1] == pytest.approx(_served(1), abs=2.0)
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

    # give1 seeded below a 2029 1st so a 1-for-1 pick return clears the
    # consensus path's user-gain + fairness gates. (It was "just under" while
    # a 2029 1st served at 1263.0; D-161's floor lifted the pick to 1859.5 and
    # widened the margin, which loosens this gate rather than tightening it.)
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
            assert c.receive_value == pytest.approx(_served(1), abs=2.0)
        assert c.receive_value != pytest.approx(flat_default, abs=0.5)
