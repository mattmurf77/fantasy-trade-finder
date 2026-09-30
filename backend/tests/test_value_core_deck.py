"""value-core WP2: greedy deck assembly with repeat penalties and the per-asset cap
(lld.md 5.6, specs.md 5.2). ScoredTrade objects are built by hand with chosen priorities.
"""
import random
from collections import Counter

import pytest

from backend.value_core import ranking
from backend.value_core.deck import PARTNER_PENALTY_FACTOR, assemble_deck
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
    ids = sorted({a for s in scored for a in s.trade.give + s.trade.receive})
    return snap({"V": [A(i, "WR", 1000) for i in ids]})


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


def _naive(scored, cfg):
    """O(n^2) reference greedy: at each position take the best eligible card by
    (effective desc, key asc); if none is eligible before TOP_WINDOW, relax the cap."""
    shown, shown_partner = Counter(), Counter()
    assets = lambda i: scored[i].trade.give + scored[i].trade.receive

    def eff(i):
        return (scored[i].scores.priority - cfg.repeat_penalty * max(shown[a] for a in assets(i))
                - PARTNER_PENALTY_FACTOR * cfg.repeat_penalty * shown_partner[scored[i].trade.partner_team_id])

    remaining, order = list(range(len(scored))), []
    while remaining:
        pos = len(order)
        eligible = [i for i in remaining
                    if pos >= TOP_WINDOW or all(shown[a] < cfg.player_cap for a in assets(i))]
        best = min(eligible or remaining, key=lambda i: (-eff(i), scored[i].trade.key, i))
        order.append(best)
        remaining.remove(best)
        for a in assets(best):
            shown[a] += 1
        shown_partner[scored[best].trade.partner_team_id] += 1
    return [scored[i].trade.key for i in order]


def test_lazy_equals_naive():
    pool_assets = [f"a{i}" for i in range(8)]
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
        assert [e.scored.trade.key for e in out] == _naive(scored, RankConfig()), f"seed {seed}"


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
