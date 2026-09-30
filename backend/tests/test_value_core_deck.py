"""value-core deck assembly: one card per trade idea, acquisitions in rounds, partner and
per-asset caps in the first 30, repeat penalties (lld.md 5.6, specs.md 5.2).
ScoredTrade objects are built by hand with chosen priorities.
"""
import random
from collections import Counter

import pytest

from backend.value_core import ranking
from backend.value_core.deck import (PARTNER_PENALTY_FACTOR, acquisition_key, assemble_deck,
                                     idea_key, partner_cap)
from backend.value_core.types import *   # in tests only


def A(id, pos, market, age=25.0):
    kind = "pick" if pos == "PICK" else "player"
    return Asset(id, kind, pos, id.upper(), None if kind == "pick" else age, float(market))

BODIES = lambda t: [A(f"{t}qb", "QB", 300), A(f"{t}rb1", "RB", 300), A(f"{t}rb2", "RB", 300),
                    A(f"{t}wr1", "WR", 300), A(f"{t}wr2", "WR", 300), A(f"{t}te", "TE", 300)]
SLOTS = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX")

def snap(teams, *, slots=SLOTS, max_players=None, other=None, windows=None):
    assets = {a.id: a for lst in teams.values() for a in lst}
    return LeagueSnapshot("L1", "1qb_ppr", assets,
        {t: Team(t, t, tuple(a.id for a in lst), (other or {}).get(t, 0),
                 (windows or {}).get(t, DEFAULT_WINDOW)) for t, lst in teams.items()},
        RosterRules(tuple(slots), max_players), first_round_value=1492.0, elite_value=8457.0)


NEUTRAL_SIDE = {"window": "middle", "lineup_gain": 0.0, "future_gain": 0.0, "score": 0.5}
REQ = Request("V")


def ST(partner, give, receive, priority):
    """A hand-built ScoredTrade: every asset is worth 1000, neutral detail, chosen priority."""
    trade = FairTrade(partner, tuple(give), tuple(receive), 1000.0 * len(give),
                      1000.0 * len(receive), len(receive) / len(give), 0.0, None, False, (0, 0))
    detail = {"value": {"delta_ln": 0.0, "s_delta": 0.5, "best_in_id": receive[0],
                        "best_in_market": 1000.0, "best_in_starter": False, "s_piece": 0.6702},
              "outlook": {"scale": 1000.0, "viewer": NEUTRAL_SIDE, "partner": NEUTRAL_SIDE},
              "rank": {"has_board": False, "gap_rel": 0.0, "top_asset": None, "top_side": None,
                       "rank_delta": None}}
    return ScoredTrade(trade, Scores(0.5, 0.5, 0.5, priority), detail)


def snap_for(scored):
    """Ids starting with "pk" are picks; everything else is a WR."""
    ids = sorted({a for s in scored for a in s.trade.give + s.trade.receive})
    return snap({"V": [A(i, "PICK" if i.startswith("pk") else "WR", 1000) for i in ids]})


def deck(scored, cfg=RankConfig()):
    return assemble_deck(scored, cfg, snapshot=snap_for(scored), request=REQ)


def test_cap_in_first_30_nothing_dropped():
    stud = [ST(f"P{i:03d}", ["stud"], [f"r{i}"], 0.99 - 0.09 * i / 99) for i in range(100)]
    rest = [ST(f"Q{i:03d}", [f"g{i}"], [f"s{i}"], 0.50 - 0.10 * i / 99) for i in range(100)]
    out = deck(stud + rest)
    assert sum("stud" in e.scored.trade.give for e in out[:TOP_WINDOW]) <= 3
    assert len(out) == 200
    assert {e.scored.trade.key for e in out} == {s.trade.key for s in stud + rest}
    assert [e.position for e in out] == list(range(200))


def test_repeat_penalty_order():
    t1, t2, t3 = ST("A", ["x"], ["a1"], 0.80), ST("B", ["x"], ["b1"], 0.78), ST("C", ["y"], ["c1"], 0.70)
    out = deck([t1, t2, t3], RankConfig(repeat_penalty=0.15))
    assert [e.scored for e in out] == [t1, t3, t2]
    assert out[2].effective == pytest.approx(0.63)


def test_partner_half_penalty():
    t1, t2, t3 = ST("A", ["x"], ["a1"], 0.80), ST("A", ["y"], ["a2"], 0.78), ST("B", ["z"], ["b1"], 0.72)
    out = deck([t1, t2, t3], RankConfig(repeat_penalty=0.15))
    assert [e.scored for e in out] == [t1, t3, t2]
    assert out[2].effective == pytest.approx(0.78 - 0.075)


def test_cap_relaxes_when_only_capped_remain():
    trades = [ST(f"P{i}", ["x"], [f"r{i}"], 0.9 - 0.1 * i) for i in range(5)]
    out = deck(trades)
    assert [e.position for e in out] == [0, 1, 2, 3, 4]
    assert [e.scored for e in out] == trades


def _naive(scored, cfg, snapshot):
    """O(n^2) reference: keep the best version of each trade idea, then at each position take
    the best eligible card by (acquisition round, effective desc, key asc); if none is
    eligible before TOP_WINDOW, relax the caps for that position."""
    best = {}
    for s in scored:
        k = idea_key(s.trade, snapshot)
        if k not in best or (-s.scores.priority, s.trade.key) < (-best[k].scores.priority, best[k].trade.key):
            best[k] = s
    ideas = list(best.values())
    p_cap = partner_cap(len({s.trade.partner_team_id for s in ideas}))
    shown, shown_partner, shown_acq = Counter(), Counter(), Counter()
    assets = lambda i: ideas[i].trade.give + ideas[i].trade.receive
    partner = lambda i: ideas[i].trade.partner_team_id

    def eff(i):
        return (ideas[i].scores.priority - cfg.repeat_penalty * max(shown[a] for a in assets(i))
                - PARTNER_PENALTY_FACTOR * cfg.repeat_penalty * shown_partner[partner(i)])

    remaining, order = list(range(len(ideas))), []
    while remaining:
        pos = len(order)
        eligible = [i for i in remaining
                    if pos >= TOP_WINDOW or (shown_partner[partner(i)] < p_cap
                                             and all(shown[a] < cfg.player_cap for a in assets(i)))]
        pick = min(eligible or remaining,
                   key=lambda i: (shown_acq[acquisition_key(ideas[i].trade, snapshot)], -eff(i),
                                  ideas[i].trade.key, i))
        order.append(pick)
        remaining.remove(pick)
        for a in assets(pick):
            shown[a] += 1
        shown_partner[partner(pick)] += 1
        shown_acq[acquisition_key(ideas[pick].trade, snapshot)] += 1
    return [ideas[i].trade.key for i in order]


def test_lazy_equals_naive():
    pool_assets = [f"a{i}" for i in range(6)] + ["pk1", "pk2"]
    partners = ["P1", "P2", "P3", "P4"]
    for seed in range(30):
        rng = random.Random(seed)
        seen, scored = set(), []
        while len(scored) < 60:
            k_give, k_recv = rng.randint(1, 3), rng.randint(1, 3)
            picked = rng.sample(pool_assets, k_give + k_recv)
            s = ST(rng.choice(partners), sorted(picked[:k_give]), sorted(picked[k_give:]), rng.random())
            if s.trade.key not in seen:
                seen.add(s.trade.key)
                scored.append(s)
        out = deck(scored)
        assert [e.scored.trade.key for e in out] == _naive(scored, RankConfig(), snap_for(scored)), f"seed {seed}"


def test_reasons_attached():
    s = snap({"V": BODIES("V") + [A("x", "WR", 1100), A("x2", "RB", 1600, age=22)],
              "P": BODIES("P") + [A("y", "WR", 1000), A("y2", "PICK", 1700)]},
             windows={"P": TeamWindow("rebuilder", -0.2, "declared", None, 0.0)})
    trades = [FairTrade("P", g, r, sum(s.assets[i].market for i in g), sum(s.assets[i].market for i in r),
                        1.0, 0.0, None, False, (0, 0))
              for g, r in [(("x",), ("y",)), (("x2",), ("y2",)), (("x2",), ("y",)), (("x",), ("y2",))]]
    req = Request("V", board=Board({"y": 1400.0}, {"y": 6}))
    scored = ranking.score_trades(s, req, trades, RankConfig())
    out = assemble_deck(scored, RankConfig(), snapshot=s, request=req)
    assert len(out) == 4
    for e in out:
        assert e.reasons == ranking.card_reasons(e.scored, s, req)
        assert 1 <= len(e.reasons) <= 3


def test_minor_piece_swaps_are_one_idea():
    """Same partner, same headliners, different throw-ins: only the best version is shown."""
    best = ST("P", ["x"], ["y", "m1"], 0.80)
    worse = ST("P", ["x"], ["y", "m2"], 0.79)
    give_filler = ST("P", ["x", "m3"], ["y"], 0.78)
    other = ST("Q", ["z"], ["w"], 0.50)
    out = deck([best, worse, give_filler, other])
    assert [e.scored for e in out] == [best, other]


def test_pick_years_are_one_idea_and_one_acquisition():
    """A partner's picks are interchangeable for variety: 2026 1st vs 2027 1st for the same
    player is one idea, and pick-headlined returns from one partner count as one acquisition."""
    y26 = ST("P", ["x"], ["pk2026_1"], 0.90)
    y27 = ST("P", ["x"], ["pk2027_1"], 0.89)          # same idea as y26: dropped
    other_give = ST("P", ["z"], ["pk2027_2"], 0.88)   # new idea, but the same acquisition ("a pick from P")
    q1 = ST("Q", ["g1"], ["q1"], 0.40)
    q2 = ST("R", ["g2"], ["r1"], 0.30)
    out = deck([y26, y27, other_give, q1, q2])
    assert [e.scored for e in out] == [y26, q1, q2, other_give]


def test_each_acquisition_once_before_any_repeat():
    """Round 1 shows every (partner, acquired headliner) once; repeats wait for round 2."""
    a1 = ST("P", ["x1"], ["y"], 0.95)
    a2 = ST("P", ["x2"], ["y"], 0.94)                 # acquires y from P again
    rest = [ST(f"Q{i}", [f"g{i}"], [f"r{i}"], 0.30 - 0.01 * i) for i in range(5)]
    out = deck([a1, a2] + rest)
    assert [e.scored for e in out] == [a1] + rest + [a2]


def test_partner_cap_in_first_30():
    """One partner with 40 strong, distinct acquisitions cannot take over the first 30."""
    heavy = [ST("P", [f"x{i}"], [f"y{i}"], 0.99 - 0.001 * i) for i in range(40)]
    light = [ST(f"Q{j}", [f"g{j}_{i}"], [f"r{j}_{i}"], 0.40 - 0.001 * i)
             for j in range(10) for i in range(5)]
    out = deck(heavy + light)
    cap = partner_cap(11)
    assert cap == 4
    assert sum(e.scored.trade.partner_team_id == "P" for e in out[:TOP_WINDOW]) == cap
    assert len(out) == 90   # nothing dropped: every card is a distinct idea
