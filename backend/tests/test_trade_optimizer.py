"""Tests for the Tier 3 trade optimizer (backend/trade_optimizer.py —
docs/plans/trade-engine-tier3-rebuild.md, work items 3.1-3.4).

Covers:
  - parity: on a 1-for-1 fixture the v3 top card matches the v2 top card
  - exactness: v3 returns EXACTLY the brute-force top-K within the pools
    (objective independently re-derived in the test)
  - 3.2 lineup feasibility: a combo stripping the opponent's only QB never
    surfaces despite having the best objective
  - 3.4 sweeteners: a near-miss pair gets a sweetened card (attribute set,
    fairness restored to band); a hopeless pair gets nothing
  - 3.3 cycles: a 3-team cycle profitable for all three is found with the
    right transfers/nets; a league with no cycle returns []
  - pinned give players always enter the give pool at any divergence

All fixtures are tiny and deterministic — no RNG. Flag + config mutations
are snapshot/restored by an autouse fixture (same style as
test_trade_tier2.py).
"""

from dataclasses import dataclass
from itertools import combinations
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_optimizer import (
    find_three_team_cycles,
    generate_pair_trades_v3,
)
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    elo_to_value,
)


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

@dataclass
class _Player:
    id: str
    name: str
    position: str = "WR"
    team: str = "TST"
    age: int = 25
    ktc_value: Optional[int] = None


@pytest.fixture(autouse=True)
def _isolate_flags_and_cfg():
    """Pin flags to all-off defaults and _cfg to code defaults for every
    test, then restore whatever was there before."""
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)          # everything OFF
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)                   # pristine config
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _set_flags(*extra: str) -> None:
    """Enable trade_engine.v2 plus any extra dotted flag keys."""
    cache = dict(ff.DEFAULT_FLAGS)
    cache["trade_engine.v2"] = True
    for key in extra:
        assert key in cache, f"unknown flag key {key!r}"
        cache[key] = True
    ff._flags_cache = cache


def _member(user_id: str, roster: list[str], elo: dict[str, float],
            has_rankings: bool = True) -> LeagueMember:
    return LeagueMember(user_id=user_id, username=user_id, roster=roster,
                        elo_ratings=elo, has_rankings=has_rankings)


def _players_of(spec: dict[str, str]) -> dict:
    """spec: pid -> position."""
    return {pid: _Player(id=pid, name=f"Player {pid}", position=pos)
            for pid, pos in spec.items()}


# A lineup-feasible base: 1 QB, 2 RB, 2 WR, 1 TE (1qb format needs).
_BASE_POS = {"q0": "QB", "b1": "RB", "b2": "RB",
             "w1": "WR", "w2": "WR", "t0": "TE"}


def _bodies(prefix: str) -> dict[str, str]:
    return {f"{prefix}_{pid}": pos for pid, pos in _BASE_POS.items()}


def _v3(*, user_elo, user_roster, opponent, seed_elo, players, **kw):
    defaults = dict(
        user_id="user",
        shrunk_user_elo=user_elo,
        user_value={pid: elo_to_value(e) for pid, e in user_elo.items()},
        user_roster=user_roster,
        opponent=opponent,
        league_id="L1",
        seed_elo=seed_elo,
        confidence=None,
        max_cards=5,
        fairness_threshold=0.75,
        scoring_format="1qb_ppr",
        players=players,
    )
    defaults.update(kw)
    return generate_pair_trades_v3(**defaults)


# ---------------------------------------------------------------------------
# 1. Parity with the v2 generator on a 1-for-1 fixture
# ---------------------------------------------------------------------------

def test_v3_top_card_matches_v2_on_1for1_fixture():
    """The exact optimizer must not LOSE good 1-for-1s: same inputs, same
    objective, same top card as TradeService._generate_for_pair_v2."""
    _set_flags()                       # trade_engine.v2 on; marginal/outlook off

    pos = {**_bodies("u"), **_bodies("o"), "uA": "WR", "oA": "WR"}
    players = _players_of(pos)
    user_roster = list(_bodies("u")) + ["uA"]
    opp_roster = list(_bodies("o")) + ["oA"]

    # uA: opp over-values (+60 Elo). oA: user over-values (+60 Elo).
    # Bodies carry slight NEGATIVE divergence so no body combo ties the top.
    user_elo = {pid: 1500.0 for pid in user_roster}
    user_elo.update({pid: 1490.0 for pid in _bodies("o")})
    user_elo["oA"] = 1560.0
    opp_elo = {pid: 1500.0 for pid in opp_roster}
    opp_elo.update({pid: 1490.0 for pid in _bodies("u")})
    opp_elo["uA"] = 1560.0
    seed_elo = {pid: 1500.0 for pid in pos}
    seed_elo["uA"] = seed_elo["oA"] = 1530.0

    opponent = _member("opp", opp_roster, opp_elo)
    user_value = {pid: elo_to_value(e) for pid, e in user_elo.items()}

    svc = TradeService(players=players)
    v2_cards = svc._generate_for_pair_v2(
        user_id="user",
        shrunk_user_elo=user_elo,
        user_value=dict(user_value),
        user_roster=user_roster,
        opponent=opponent,
        league_id="L1",
        seed_value=lambda p: elo_to_value(seed_elo.get(p, 1500.0)),
        max_cards=5,
        fairness_threshold=0.75,
        acquire_positions=[],
        trade_away_positions=[],
        pinned_give_players=None,
        confidence=None,
        scoring_format="1qb_ppr",
    )
    v3_cards = _v3(user_elo=user_elo, user_roster=user_roster,
                   opponent=opponent, seed_elo=seed_elo, players=players)

    assert v2_cards and v3_cards
    v2_top, v3_top = v2_cards[0], v3_cards[0]
    assert sorted(v3_top.give_player_ids) == sorted(v2_top.give_player_ids)
    assert sorted(v3_top.receive_player_ids) == sorted(v2_top.receive_player_ids)
    assert v3_top.give_player_ids == ["uA"]
    assert v3_top.receive_player_ids == ["oA"]
    assert v3_top.mismatch_score == v2_top.mismatch_score
    assert v3_top.fairness_score == v2_top.fairness_score
    assert v3_top.composite_score == v2_top.composite_score
    assert v3_top.basis == "divergence"


# ---------------------------------------------------------------------------
# 2. Exactness: v3 == independent brute force over the pools
# ---------------------------------------------------------------------------

def _brute_force_topk(give_pool, recv_pool, user_elo, opp_elo, seed_elo,
                      k, fairness_threshold=0.75):
    """Independent re-derivation of the v2 objective (raw values, flags
    off, confidence=None) over every subset combo in the given pools."""
    uval = {p: elo_to_value(user_elo[p]) for p in set(give_pool) | set(recv_pool)}
    oval = {p: elo_to_value(opp_elo[p]) for p in uval}
    sval = {p: elo_to_value(seed_elo[p]) for p in uval}

    def pkg(vals, v_max):
        gamma = ts._c("package_adj_gamma")
        return round(sum(v * (0.15 + 0.85 * (v / v_max) ** gamma)
                         for v in vals), 1)

    def tier_mult(pids):
        best = ts._c("tier_mult_bench")
        for pid in pids:
            e = user_elo.get(pid, 1500)
            if   e >= 1700: m = ts._c("tier_mult_elite")
            elif e >= 1580: m = ts._c("tier_mult_starter")
            elif e >= 1460: m = ts._c("tier_mult_solid")
            elif e >= 1350: m = ts._c("tier_mult_depth")
            else:           m = ts._c("tier_mult_bench")
            best = max(best, m)
        return best

    min_side = ts._c("min_side_surplus")
    cap = max(ts._c("mutual_gain_cap"), 1.0)
    waiver = ts._c("waiver_slot_cost")
    max_gap = ts._c("trade_elo_gap_max")
    out = []
    g_subsets = [list(c) for n in (1, 2, 3) for c in combinations(give_pool, n)]
    r_subsets = [list(c) for n in (1, 2, 3) for c in combinations(recv_pool, n)]
    for g in g_subsets:
        for r in r_subsets:
            if abs(len(g) - len(r)) > 1:
                continue
            if abs(max(user_elo[p] for p in r)
                   - max(user_elo[p] for p in g)) > max_gap:
                continue
            u_max = max(uval[p] for p in g + r)
            gv_u, rv_u = pkg([uval[p] for p in g], u_max), pkg([uval[p] for p in r], u_max)
            o_max = max(oval[p] for p in g + r)
            gv_o, rv_o = pkg([oval[p] for p in g], o_max), pkg([oval[p] for p in r], o_max)
            extra = len(r) - len(g)
            if extra > 0:
                rv_u -= waiver * extra
            elif extra < 0:
                gv_o -= waiver * (-extra)
            us, os_ = rv_u - gv_u, gv_o - rv_o
            if us < min_side or os_ < min_side:
                continue
            s_max = max(sval[p] for p in g + r)
            gs, rs = pkg([sval[p] for p in g], s_max), pkg([sval[p] for p in r], s_max)
            ratio = min(gs, rs) / max(gs, rs)
            # confidence=None -> zero uncertainty -> overlap iff equal;
            # the gate degrades to the point-ratio threshold.
            if gs != rs and ratio < fairness_threshold:
                continue
            fairness = round(ratio, 3)
            hm = 2 * us * os_ / (us + os_)
            comp = (ts._c("mismatch_weight") * min(hm, cap) / cap
                    + ts._c("fairness_weight") * fairness) * tier_mult(g + r)
            out.append((comp, frozenset(g), frozenset(r)))
    out.sort(key=lambda e: e[0], reverse=True)
    return out[:k]


def test_v3_returns_exact_brute_force_topk():
    ts._cfg["v3_pool_size"] = 5
    # Disable the diverse-top-K filter (overlap <= 1.0 is always true) so the
    # exactness contract under test is plain best-K by composite.
    ts._cfg["v3_diversity_max_overlap"] = 1.0
    give_pool = [f"g{i}" for i in range(1, 6)]
    recv_pool = [f"r{i}" for i in range(1, 6)]
    pos = {**_bodies("u"), **_bodies("o")}
    pos.update({pid: "WR" for pid in give_pool + recv_pool})
    players = _players_of(pos)
    user_roster = list(_bodies("u")) + give_pool
    opp_roster = list(_bodies("o")) + recv_pool

    user_elo = {pid: 1500.0 for pid in pos}
    opp_elo = {pid: 1500.0 for pid in pos}
    # Bodies: slight negative divergence keeps them out of the top-5 pools.
    for pid in _bodies("u"):
        opp_elo[pid] = 1490.0
    for pid in _bodies("o"):
        user_elo[pid] = 1490.0
    for i, pid in enumerate(give_pool):
        opp_elo[pid] = 1560.0 - 5 * i          # 1560..1540
    for i, pid in enumerate(recv_pool):
        user_elo[pid] = 1558.0 - 5 * i         # 1558..1538
    seed_elo = {pid: 1500.0 for pid in pos}
    for pid in give_pool + recv_pool:
        seed_elo[pid] = 1520.0

    opponent = _member("opp", opp_roster, opp_elo)
    cards = _v3(user_elo=user_elo, user_roster=user_roster, opponent=opponent,
                seed_elo=seed_elo, players=players, max_cards=4)
    expected = _brute_force_topk(give_pool, recv_pool, user_elo, opp_elo,
                                 seed_elo, k=4)

    assert len(cards) == 4
    got = [(c.composite_score, frozenset(c.give_player_ids),
            frozenset(c.receive_player_ids)) for c in cards]
    want = [(round(comp, 3), g, r) for comp, g, r in expected]
    assert got == want


# ---------------------------------------------------------------------------
# 3. Lineup feasibility (3.2): never strip a roster below starter needs
# ---------------------------------------------------------------------------

def test_infeasible_only_qb_trade_never_surfaces():
    """User covets the opponent's ONLY QB — by raw objective that's the
    best combo, but it would leave the opponent with 0 QBs, so it must be
    rejected at the constraint level. A lesser WR-for-WR card survives.

    Pool size 2 keeps the user's own QB out of the give pool (its
    divergence is strongly negative), so no combo can send a QB back —
    every combo containing qO is infeasible for the opponent."""
    ts._cfg["v3_pool_size"] = 2
    pos = {**_bodies("u"), **_bodies("o"), "uW": "WR", "oW": "WR"}
    # Replace the opp QB body with the coveted QB so opp has EXACTLY 1 QB.
    del pos["o_q0"]
    pos["qO"] = "QB"
    players = _players_of(pos)
    user_roster = list(_bodies("u")) + ["uW"]
    opp_roster = [p for p in _bodies("o") if p != "o_q0"] + ["qO", "oW"]

    user_elo = {pid: 1500.0 for pid in pos}
    opp_elo = {pid: 1500.0 for pid in pos}
    for pid in _bodies("u"):
        opp_elo[pid] = 1490.0
    for pid in opp_roster:
        user_elo[pid] = 1490.0
    user_elo["qO"] = 1620.0     # user massively over-values the QB
    user_elo["oW"] = 1570.0     # moderate-divergence WR fallback
    opp_elo["uW"] = 1600.0      # opp over-values the user's WR
    user_elo["uW"] = 1500.0
    opp_elo["qO"] = 1500.0
    opp_elo["oW"] = 1500.0
    opp_elo["u_q0"] = 1400.0    # user's QB: strongly negative divergence
    opp_elo["u_w1"] = 1495.0    # second give-pool slot (a WR, not the QB)
    seed_elo = {pid: 1500.0 for pid in pos}
    seed_elo.update({"uW": 1550.0, "qO": 1560.0, "oW": 1535.0})

    opponent = _member("opp", opp_roster, opp_elo)
    cards = _v3(user_elo=user_elo, user_roster=user_roster, opponent=opponent,
                seed_elo=seed_elo, players=players)

    assert cards, "the feasible WR-for-WR trade should still surface"
    for c in cards:
        assert "qO" not in c.receive_player_ids, (
            "trade strips the opponent's only QB — must be infeasible")
    top = cards[0]
    assert top.give_player_ids == ["uW"]
    assert top.receive_player_ids == ["oW"]


# ---------------------------------------------------------------------------
# 4. Sweeteners (3.4)
# ---------------------------------------------------------------------------

def _sweetener_fixture(uA_seed: float):
    """1-for-1 near-miss pair: huge mutual surplus, consensus ratio set by
    uA's seed Elo. Pool size 1 so the sweetened combo is NOT organically
    enumerable. s1 (dirt cheap) can't close the gap; s2 can.

    NOTE: consensus package values use package_value_v2 against the
    trade-wide v_max, so the under-paying single asset is discounted —
    uA seed 1494 vs oA seed 1536 yields a point ratio ~0.624 (in the
    [0.60, 0.75) sweetener band), and the missing contribution (~150) is
    more than s1 provides (~109) but less than s2 (~490)."""
    ts._cfg["v3_pool_size"] = 1
    pos = {**_bodies("u"), **_bodies("o"),
           "uA": "WR", "oA": "WR", "s1": "WR", "s2": "WR"}
    players = _players_of(pos)
    user_roster = list(_bodies("u")) + ["uA", "s1", "s2"]
    opp_roster = list(_bodies("o")) + ["oA"]

    user_elo = {pid: 1500.0 for pid in pos}
    opp_elo = {pid: 1500.0 for pid in pos}
    for pid in _bodies("u"):
        opp_elo[pid] = 1490.0
    for pid in _bodies("o"):
        user_elo[pid] = 1490.0
    user_elo.update({"oA": 1620.0, "s1": 1455.0, "s2": 1455.0})
    opp_elo.update({"uA": 1620.0, "s1": 1455.0, "s2": 1455.0})
    seed_elo = {pid: 1500.0 for pid in pos}
    seed_elo.update({"uA": uA_seed, "oA": 1536.0,
                     "s1": 1300.0, "s2": 1455.0})
    opponent = _member("opp", opp_roster, opp_elo)
    return players, user_roster, opponent, user_elo, seed_elo


def test_sweetener_rescues_near_miss_pair():
    # uA seed 1494 -> consensus ratio ~0.624: inside [0.60, 0.75) band.
    players, user_roster, opponent, user_elo, seed_elo = _sweetener_fixture(1494.0)
    cards = _v3(user_elo=user_elo, user_roster=user_roster, opponent=opponent,
                seed_elo=seed_elo, players=players)

    assert len(cards) == 1
    card = cards[0]
    sweet = getattr(card, "sweetener", None)
    assert sweet == {"player_id": "s2", "side": "give"}
    assert sorted(card.give_player_ids) == ["s2", "uA"]   # sweetener INCLUDED
    assert card.receive_player_ids == ["oA"]
    assert card.fairness_score >= 0.75                    # back in band
    assert card.basis == "divergence"


def test_sweetener_skips_hopeless_pair():
    # uA seed 1450 -> ratio ~0.388: below threshold - band, not rescuable.
    players, user_roster, opponent, user_elo, seed_elo = _sweetener_fixture(1450.0)
    cards = _v3(user_elo=user_elo, user_roster=user_roster, opponent=opponent,
                seed_elo=seed_elo, players=players)
    assert all(getattr(c, "sweetener", None) is None for c in cards)
    assert cards == []


# ---------------------------------------------------------------------------
# 5. Three-team cycles (3.3)
# ---------------------------------------------------------------------------

def _cycle_league():
    """A, B, C each hold one player the NEXT team over-values: pA->B,
    pB->C, pC->A. No reciprocal valuation, so no pairwise edge back."""
    pos = {}
    rosters = {}
    for uid, star in (("A", "pA"), ("B", "pB"), ("C", "pC")):
        bodies = _bodies(uid)
        pos.update(bodies)
        pos[star] = "WR"
        rosters[uid] = list(bodies) + [star]
    players = _players_of(pos)
    members = [_member(uid, rosters[uid], {}, has_rankings=True)
               for uid in ("A", "B", "C")]
    league = League(league_id="L1", name="Cycle League", platform="demo",
                    members=members)
    return league, players


def test_three_team_cycle_found_with_correct_transfers_and_nets():
    league, players = _cycle_league()
    # Own values default to consensus 1000 (empty seed_elo). Deviations:
    # each team values the PREVIOUS team's star at 1600 -> directed edges
    # A->B (pA), B->C (pB), C->A (pC), each with gain 600 >= 100.
    member_values = {
        "A": {"pC": 1600.0, "pB": 900.0},   # pB undervalued: no B->A edge
        "B": {"pA": 1600.0},
        "C": {"pB": 1600.0},
    }
    cycles = find_three_team_cycles(
        league=league, member_values=member_values, seed_elo={},
        scoring_format="1qb_ppr", players=players)

    assert len(cycles) == 1
    cyc = cycles[0]
    assert sorted(cyc["teams"]) == ["A", "B", "C"]
    transfers = {(t["from"], t["to"]): t["player_id"]
                 for t in cyc["transfers"]}
    assert transfers == {("A", "B"): "pA", ("B", "C"): "pB",
                         ("C", "A"): "pC"}
    # Net for each team = own value of what it gets - own value of what it
    # gives = 1600 - 1000 = 600, all >= cycle_min_net (200).
    assert cyc["nets"] == {"A": 600.0, "B": 600.0, "C": 600.0}
    assert cyc["min_net"] == 600.0


def test_no_cycle_league_returns_empty():
    league, players = _cycle_league()
    # C values nothing of B's -> the B->C edge never forms -> no 3-cycle.
    member_values = {"A": {"pC": 1600.0}, "B": {"pA": 1600.0}, "C": {}}
    cycles = find_three_team_cycles(
        league=league, member_values=member_values, seed_elo={},
        scoring_format="1qb_ppr", players=players)
    assert cycles == []


# ---------------------------------------------------------------------------
# 6. Pinned give players always enter the give pool
# ---------------------------------------------------------------------------

def test_pinned_player_in_give_pool_despite_low_divergence():
    ts._cfg["v3_pool_size"] = 1          # top-1 divergence pool only
    pos = {**_bodies("u"), **_bodies("o"), "uA": "WR", "uP": "WR", "oA": "WR"}
    players = _players_of(pos)
    user_roster = list(_bodies("u")) + ["uA", "uP"]
    opp_roster = list(_bodies("o")) + ["oA"]

    user_elo = {pid: 1500.0 for pid in pos}
    opp_elo = {pid: 1500.0 for pid in pos}
    for pid in _bodies("u"):
        opp_elo[pid] = 1490.0
    for pid in _bodies("o"):
        user_elo[pid] = 1490.0
    opp_elo["uA"] = 1620.0      # top divergence -> the ONE pool slot
    opp_elo["uP"] = 1560.0      # lower divergence -> outside the pool
    user_elo["oA"] = 1620.0
    seed_elo = {pid: 1500.0 for pid in pos}
    seed_elo.update({"uA": 1550.0, "uP": 1530.0, "oA": 1560.0})

    opponent = _member("opp", opp_roster, opp_elo)
    cards = _v3(user_elo=user_elo, user_roster=user_roster, opponent=opponent,
                seed_elo=seed_elo, players=players,
                pinned_give_players=["uP"])

    assert cards, "pinned player must reach the pool and produce cards"
    for c in cards:
        assert "uP" in c.give_player_ids, (
            "pinned filter: every card must trade away uP")


# ---------------------------------------------------------------------------
# Engine selection: trade_engine.v3 routes ranked opponents through the
# optimizer; flag off falls back to _generate_for_pair_v2.
# ---------------------------------------------------------------------------

def test_engine_selection_flag_routes_to_v3(monkeypatch):
    import backend.trade_optimizer as topt
    from backend.trade_service import League

    pos = {**_bodies("u"), **_bodies("o"), "uA": "WR", "oA": "WR"}
    players = _players_of(pos)
    user_roster = list(_bodies("u")) + ["uA"]
    opp_roster = list(_bodies("o")) + ["oA"]
    user_elo = {pid: 1500.0 for pid in pos}
    user_elo["oA"] = 1560.0
    opp_elo = {pid: 1500.0 for pid in pos}
    opp_elo["uA"] = 1560.0
    seed_elo = {pid: 1500.0 for pid in pos}

    calls = []
    real_v3 = topt.generate_pair_trades_v3

    def spy(**kw):
        calls.append(kw["opponent"].user_id)
        return real_v3(**kw)

    monkeypatch.setattr(topt, "generate_pair_trades_v3", spy)

    def run():
        svc = TradeService(players=players)
        svc.add_league(League(league_id="L", name="L", platform="sleeper",
                              members=[_member("user", user_roster, user_elo),
                                       _member("opp", opp_roster, opp_elo)]))
        return svc.generate_trades(
            user_id="user", user_elo=user_elo, user_roster=user_roster,
            league_id="L", seed_elo=seed_elo)

    _set_flags("trade_engine.v3")
    run()
    assert calls == ["opp"], "v3 flag on: ranked opponent must route to the optimizer"

    calls.clear()
    _set_flags()                       # v2 only
    run()
    assert calls == [], "v3 flag off: optimizer must not be called"


def test_diverse_topk_skips_sibling_combos():
    """Five junk QBs padding the same core trade must collapse to ONE card,
    freeing slots for genuinely different cores (real-data bug 2026-06-09)."""
    pos = {**_bodies("u"), **_bodies("o"), "uA": "WR", "oA": "WR", "oB": "RB"}
    junk = {f"uJ{i}": "QB" for i in range(5)}          # interchangeable filler
    pos.update(junk)
    players = _players_of(pos)
    user_roster = list(_bodies("u")) + ["uA"] + list(junk)
    opp_roster = list(_bodies("o")) + ["oA", "oB"]

    user_elo = {pid: 1500.0 for pid in pos}
    opp_elo = {pid: 1500.0 for pid in pos}
    seed_elo = {pid: 1500.0 for pid in pos}
    # Core divergence: user over-values oA strongly, opp over-values uA.
    user_elo["oA"] = 1640.0; opp_elo["oA"] = 1500.0; seed_elo["oA"] = 1560.0
    user_elo["uA"] = 1500.0; opp_elo["uA"] = 1640.0; seed_elo["uA"] = 1560.0
    # Secondary, weaker core: oB.
    user_elo["oB"] = 1580.0; opp_elo["oB"] = 1480.0; seed_elo["oB"] = 1530.0
    for j in junk:   # junk: worthless to everyone
        user_elo[j] = opp_elo[j] = seed_elo[j] = 1280.0

    _set_flags()
    cards = _v3(user_elo=user_elo, user_roster=user_roster,
                opponent=_member("opp", opp_roster, opp_elo),
                seed_elo=seed_elo, players=players, max_cards=5)
    assert cards, "core trade must surface"
    # No two cards may share most of their assets (the sibling bug).
    for i, a in enumerate(cards):
        sa = set(a.give_player_ids) | set(a.receive_player_ids)
        for b in cards[i + 1:]:
            sb = set(b.give_player_ids) | set(b.receive_player_ids)
            j = len(sa & sb) / len(sa | sb)
            assert j <= 0.5, f"sibling cards survived diversity filter: {sa} vs {sb}"


def test_consensus_cards_rank_below_divergence_finds():
    """Mixed league (one ranked, one unranked opponent): real divergence cards
    must outrank consensus filler in the merged deck (real-data bug 2026-06-09)."""
    from backend.trade_service import League

    pos = {**_bodies("u"), **_bodies("o"), **_bodies("c"), "uA": "WR", "oA": "WR"}
    players = _players_of(pos)
    user_roster = list(_bodies("u")) + ["uA"]
    ranked_roster = list(_bodies("o")) + ["oA"]
    unranked_roster = list(_bodies("c"))

    user_elo = {pid: 1500.0 for pid in pos}
    opp_elo = {pid: 1500.0 for pid in pos}
    seed_elo = {pid: 1500.0 for pid in pos}
    user_elo["oA"] = 1640.0; seed_elo["oA"] = 1560.0
    opp_elo["uA"] = 1640.0; seed_elo["uA"] = 1560.0

    _set_flags("trade_engine.v3")
    svc = TradeService(players=players)
    svc.add_league(League(
        league_id="L", name="L", platform="sleeper",
        members=[
            # Unranked listed FIRST: ranked-first ordering must still win.
            _member("cold", unranked_roster, {}, has_rankings=False),
            _member("user", user_roster, user_elo),
            _member("opp", ranked_roster, opp_elo),
        ]))
    cards = svc.generate_trades(user_id="user", user_elo=user_elo,
                                user_roster=user_roster, league_id="L",
                                seed_elo=seed_elo)
    bases = [c.basis for c in cards]
    assert "divergence" in bases, "ranked opponent must produce divergence cards"
    if "consensus" in bases:
        assert bases.index("divergence") < bases.index("consensus"), (
            "divergence finds must outrank consensus filler")
        first_div = next(c for c in cards if c.basis == "divergence")
        for c in cards:
            if c.basis == "consensus":
                assert c.composite_score < first_div.composite_score
