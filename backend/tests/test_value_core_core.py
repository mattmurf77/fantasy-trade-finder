"""Value-core core: pricing, hard rules, enumeration and caps.

Acceptance tests from docs/plans/value-core-engine/specs.md section 5.1; the
implementation spec is lld.md section 4.
"""
import math
from itertools import combinations

import pytest

from backend.value_core import core
from backend.value_core.core import (REJECT_CODES, effective_band, evaluate_trade,
                                     find_fair_trades, stud_premium)
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


# These tests pin the original ±10% band: they test the band mechanics, not the default
# (vc_band defaults to 0.20 since the operator's 2026-10-01 decision).
CFG10 = CoreConfig(band=0.10)


def run(s, cfg=None, viewer="V", **req):
    return find_fair_trades(s, Request(viewer, **req), cfg or CFG10)


def pairs(trades):
    return {(t.give, t.receive) for t in trades}


def two_team(n=14):
    """V and P with n WR/RB assets each, all above the floor and close in value."""
    v = [A(f"v{i:02d}", "WR" if i % 2 else "RB", 1000 + 100 * i) for i in range(n)]
    p = [A(f"p{i:02d}", "RB" if i % 2 else "WR", 1050 + 100 * i) for i in range(n)]
    return snap({"V": v + BODIES("V"), "P": p + BODIES("P")})


def stud(a1, a2):
    return snap({"V": [A("a1", "WR", a1), A("a2", "WR", a2)] + BODIES("V"),
                 "P": [A("s1", "WR", 8457)] + BODIES("P")})


def test_public_api():
    assert set(core.__all__) == {"TIME_BUDGET_S", "MAX_CHECKS_PER_PARTNER", "MAX_PACKAGE_SIZE",
                                 "PREMIUM_EXPONENT", "RATIO_TOL", "REJECT_CODES", "effective_band",
                                 "stud_premium", "evaluate_trade", "find_fair_trades"}
    assert REJECT_CODES == ("floor", "band", "filler", "untouchable", "reducible",
                            "roster_size", "lineup")


def test_one_for_one_inside_band_kept():
    s = snap({"V": [A("a1", "WR", 3000)] + BODIES("V"), "P": [A("b1", "WR", 3150)] + BODIES("P")})
    trades, _ = run(s)
    assert len(trades) == 1
    t = trades[0]
    assert (t.give, t.receive) == (("a1",), ("b1",))
    assert t.adjusted_ratio == pytest.approx(1.05)
    assert t.premium == 0


def test_one_for_one_outside_band_rejected():
    s = snap({"V": [A("a1", "WR", 3000)] + BODIES("V"), "P": [A("b1", "WR", 3400)] + BODIES("P")})
    trades, diag = run(s)
    assert not any("b1" in t.receive for t in trades)
    assert diag.rejected["band"] >= 1


def test_stud_premium_consolidation():
    trades, _ = run(stud(4200, 4200))
    assert not any("s1" in t.receive for t in trades)

    trades, _ = run(stud(4600, 4400))
    t = next(t for t in trades if (t.give, t.receive) == (("a1", "a2"), ("s1",)))
    assert t.premium == pytest.approx(0.15)
    assert t.premium_side == "receive"
    assert t.adjusted_ratio == pytest.approx(8457 * 1.15 / 9000)


def test_stud_premium_scaling():
    assert stud_premium(4228.5, 8457, 0.15) == pytest.approx(0.0375)
    assert stud_premium(2117, 8457, 0.15) == pytest.approx(0.15 * (2117 / 8457) ** 2)
    assert stud_premium(9000, 8457, 0.15) == 0.15
    assert stud_premium(3000, 0, 0.15) == 0.0
    assert stud_premium(0, 8457, 0.15) == 0.0


def test_no_premium_equal_counts():
    s = snap({"V": [A("a1", "WR", 3000), A("a2", "WR", 2000)] + BODIES("V"),
              "P": [A("b1", "WR", 3100), A("b2", "WR", 1900)] + BODIES("P")})
    trades, _ = run(s)
    t = next(t for t in trades if (t.give, t.receive) == (("a1", "a2"), ("b1", "b2")))
    assert t.premium == 0
    assert t.premium_side is None


def test_absolute_floor():
    s = snap({"V": [A("a1", "WR", 3000), A("a3", "WR", 400)] + BODIES("V"),
              "P": [A("b1", "WR", 3100)] + BODIES("P")})
    trades, _ = run(s)
    assert trades
    assert not any("a3" in t.give + t.receive for t in trades)


def test_relative_filler_vs_trade_headliner():
    # 1600 >= 0.25*6000 passes the within-package pre-prune, and the band holds
    # (7300*1.1118/7600 ~= 1.068), but 1600 < 0.25*7300 = 1825 against the trade headliner.
    s = snap({"V": [A("a1", "WR", 6000), A("a4", "WR", 1600)] + BODIES("V"),
              "P": [A("b3", "WR", 7300)] + BODIES("P")})
    trades, diag = run(s)
    assert (("a1", "a4"), ("b3",)) not in pairs(trades)
    assert diag.rejected["filler"] >= 1
    verdict = evaluate_trade(s, Request("V"), CFG10, partner_team_id="P",
                             give=["a1", "a4"], receive=["b3"])
    assert verdict.reason == "filler"
    assert verdict.trade.adjusted_ratio == pytest.approx(1.068, abs=1e-3)


def test_reducible_trade_rejected():
    s = snap({"V": [A("a1", "WR", 3000), A("a5", "WR", 500)] + BODIES("V"),
              "P": [A("b1", "WR", 3250)] + BODIES("P")})
    trades, diag = run(s, CoreConfig(filler_min_frac=0.0))
    assert (("a1", "a5"), ("b1",)) not in pairs(trades)
    assert diag.rejected["reducible"] >= 1
    assert (("a1",), ("b1",)) in pairs(trades)


def test_untouchable_needs_above_market():
    s = snap({"V": [A("a1", "WR", 3000)] + BODIES("V"),
              "P": [A("b1", "WR", 3100), A("b2", "WR", 3280)] + BODIES("P")})
    trades, diag = run(s, untouchable_ids=frozenset({"a1"}))
    assert (("a1",), ("b1",)) not in pairs(trades)
    assert diag.rejected["untouchable"] >= 1
    t = next(t for t in trades if (t.give, t.receive) == (("a1",), ("b2",)))
    assert t.uses_untouchable is True


def test_not_interested_never_received():
    s = snap({"V": [A("a1", "WR", 3000)] + BODIES("V"),
              "P": [A("b1", "WR", 3050), A("b2", "WR", 3100)] + BODIES("P")})
    trades, _ = run(s)
    assert {("b1",), ("b2",)} <= {t.receive for t in trades}
    trades, _ = run(s, not_interested_ids=frozenset({"b1"}))
    assert trades
    assert not any("b1" in t.receive for t in trades)


def test_pinned_give_any_and_all():
    s = snap({"V": [A("a1", "WR", 3000), A("a2", "WR", 3100)] + BODIES("V"),
              "P": [A("b1", "WR", 3050), A("b2", "WR", 3150)] + BODIES("P")})
    trades, _ = run(s, pinned_give_ids=frozenset({"a1"}), pinned_give_mode="any")
    assert trades
    assert all("a1" in t.give for t in trades)

    trades, _ = run(s, pinned_give_ids=frozenset({"a1", "a2"}), pinned_give_mode="all")
    assert all({"a1", "a2"} <= set(t.give) for t in trades)
    assert (("a2", "a1"), ("b2", "b1")) in pairs(trades)


def test_pinned_receive_skips_partners():
    s = snap({"V": [A("a1", "WR", 3000)] + BODIES("V"),
              "P1": [A("b1", "WR", 3050)] + BODIES("P1"),
              "P2": [A("c1", "WR", 3100), A("c2", "WR", 3000)] + BODIES("P2")})
    trades, diag = run(s, pinned_receive_ids=frozenset({"c1"}))
    assert trades
    assert all(t.partner_team_id == "P2" and "c1" in t.receive for t in trades)
    assert diag.partners == 1


def test_partner_scope():
    s = snap({"V": [A("a1", "WR", 3000)] + BODIES("V"),
              "P1": [A("b1", "WR", 3050)] + BODIES("P1"),
              "P2": [A("c1", "WR", 3100)] + BODIES("P2")})
    trades, diag = run(s, partner_team_id="P2")
    assert trades
    assert all(t.partner_team_id == "P2" for t in trades)
    assert diag.partners == 1


def test_roster_size_uses_droppable_bench():
    v = [A("a1", "WR", 1600), A("a2", "RB", 1500)] + BODIES("V")
    trades, _ = run(snap({"V": v, "P": [A("b1", "WR", 3300)] + BODIES("P")},
                         max_players=10, other={"P": 3}))
    t = next(t for t in trades if (t.give, t.receive) == (("a1", "a2"), ("b1",)))
    assert t.drops_needed == (0, 1)

    # the same bench at market 500 is above the floor, so it is not droppable
    heavy = [A(b.id, b.position, 500) for b in BODIES("P")]
    trades, diag = run(snap({"V": v, "P": [A("b1", "WR", 3300)] + heavy},
                            max_players=10, other={"P": 3}))
    assert (("a1", "a2"), ("b1",)) not in pairs(trades)
    assert diag.rejected["roster_size"] >= 1


def test_lineup_blocks_losing_only_qb():
    v = [A("vq", "QB", 3000), A("vw", "WR", 300)]
    p = [A("pw", "WR", 3100), A("pw2", "WR", 300), A("pq", "QB", 300)]
    trades, diag = run(snap({"V": v, "P": p}, slots=("QB", "WR")))
    assert (("vq",), ("pw",)) not in pairs(trades)
    assert diag.rejected["lineup"] >= 1

    trades, _ = run(snap({"V": v + [A("vq2", "QB", 300)], "P": p}, slots=("QB", "WR")))
    assert (("vq",), ("pw",)) in pairs(trades)


def test_fairness_threshold_only_tightens():
    s = snap({"V": [A("a1", "WR", 3000)] + BODIES("V"), "P": [A("b1", "WR", 3150)] + BODIES("P")})
    trades, _ = run(s, fairness_threshold=0.97)          # band 0.03
    assert (("a1",), ("b1",)) not in pairs(trades)
    trades, _ = run(s, fairness_threshold=0.5)           # cannot loosen past 0.10
    assert (("a1",), ("b1",)) in pairs(trades)
    assert effective_band(0.10, 0.5) == 0.10
    assert effective_band(0.10, 0.99) == 0.02
    assert effective_band(0.10, None) == 0.10


def test_per_partner_cap_spreads_headliner_pairs():
    v = [A("a1", "WR", 3000), A("a2", "WR", 3000), A("a3", "WR", 2000), A("a4", "WR", 2000)]
    p = [A("b1", "WR", 3050), A("b2", "WR", 3050), A("b3", "WR", 2050), A("b4", "WR", 2050)]
    s = snap({"V": v + BODIES("V"), "P": p + BODIES("P")})
    trades, diag = run(s, CoreConfig(max_per_partner=2))
    assert len(trades) == 2
    assert diag.fair > 2
    # round-robin over (give headliner, receive headliner): no pair repeats until every pair has one
    assert len({(t.give[0], t.receive[0]) for t in trades}) == 2
    for t in trades:
        assert max(s.assets[t.give[0]].market, s.assets[t.receive[0]].market) >= 3000
    assert diag.truncated_partners == 1


def test_check_cap_and_budget():
    s = two_team()
    _, diag = find_fair_trades(s, Request("V"), CFG10, max_checks_per_partner=50)
    assert diag.pairs_checked <= 50
    assert diag.truncated_partners == 1

    _, diag = find_fair_trades(s, Request("V"), CFG10, time_budget_s=0.0)
    assert diag.budget_exhausted is True


def test_deterministic():
    s = two_team()
    first, d1 = run(s)
    second, d2 = run(s)
    assert first and first == second
    assert (d1.pairs_checked, d1.fair, d1.rejected) == (d2.pairs_checked, d2.fair, d2.rejected)

    # lld 4.5 output order
    def key(t):
        h = max(s.assets[t.give[0]].market, s.assets[t.receive[0]].market)
        return (t.partner_team_id, -h, len(t.give) + len(t.receive),
                abs(math.log(t.adjusted_ratio)), t.give, t.receive)
    assert first == sorted(first, key=key)
    # every package side is sorted by (-market, id)
    for t in first:
        for side in (t.give, t.receive):
            assert list(side) == sorted(side, key=lambda a: (-s.assets[a].market, a))


def test_diagnostics_account_for_every_check():
    trades, diag = run(two_team(5))
    assert set(diag.rejected) == set(REJECT_CODES)
    assert diag.pairs_checked == diag.fair + sum(diag.rejected.values())
    assert diag.truncated_partners == 0
    assert diag.fair == len(trades)
    assert diag.packages_viewer > 0 and diag.partners == 1


def test_evaluate_trade_agrees_with_find():
    s = stud(4600, 4400)
    req, cfg = Request("V"), CFG10
    trades, _ = find_fair_trades(s, req, cfg)
    assert trades
    for t in trades:
        verdict = evaluate_trade(s, req, cfg, partner_team_id=t.partner_team_id,
                                 give=t.give, receive=t.receive)
        assert verdict.ok and verdict.reason is None
        assert verdict.trade.adjusted_ratio == t.adjusted_ratio
        assert verdict.trade == t

    verdict = evaluate_trade(stud(4200, 4200), req, cfg, partner_team_id="P",
                             give=("a1", "a2"), receive=("s1",))
    assert verdict.ok is False
    assert verdict.reason == "band"
    assert verdict.trade is not None


def test_evaluate_trade_matches_find_on_every_package_pair():
    # Small enough that find_fair_trades never truncates: evaluate_trade must admit exactly
    # the pairs it kept, among every 1..3 x 1..3 package of the eligible assets.
    v = [A("v1", "WR", 3000), A("v2", "RB", 2400), A("v3", "WR", 1500), A("v4", "TE", 900),
         A("v5", "QB", 700)]
    p = [A("p1", "RB", 3300), A("p2", "WR", 2000), A("p3", "WR", 1200), A("p4", "TE", 1000),
         A("p5", "QB", 800)]
    s = snap({"V": v + BODIES("V"), "P": p + BODIES("P")}, max_players=13)
    req = Request("V", untouchable_ids=frozenset({"v2"}), pinned_give_ids=frozenset(),
                  fairness_threshold=0.93)
    cfg = CFG10
    trades, diag = find_fair_trades(s, req, cfg)
    assert trades and diag.truncated_partners == 0
    kept = {(t.give, t.receive): t for t in trades}

    def packs(ids):
        return [c for k in (1, 2, 3) for c in combinations(ids, k)]

    admitted = {}
    for g in packs([a.id for a in v]):
        for r in packs([a.id for a in p]):
            verdict = evaluate_trade(s, req, cfg, partner_team_id="P", give=g, receive=r)
            if verdict.ok:
                admitted[(verdict.trade.give, verdict.trade.receive)] = verdict.trade
    assert admitted == kept


def test_evaluate_trade_rejects_foreign_ids():
    s = snap({"V": [A("a1", "WR", 3000)] + BODIES("V"), "P": [A("b1", "WR", 3100)] + BODIES("P")})
    req, cfg = Request("V"), CFG10
    with pytest.raises(ValueError):
        evaluate_trade(s, req, cfg, partner_team_id="P", give=["b1"], receive=["b1"])
    with pytest.raises(ValueError):
        evaluate_trade(s, req, cfg, partner_team_id="P", give=["a1"], receive=["a1"])
    with pytest.raises(ValueError):
        evaluate_trade(s, req, cfg, partner_team_id="P", give=["zz"], receive=["b1"])
    with pytest.raises(ValueError):
        evaluate_trade(s, req, cfg, partner_team_id="P", give=[], receive=["b1"])
    with pytest.raises(ValueError):
        evaluate_trade(s, req, cfg, partner_team_id="nobody", give=["a1"], receive=["b1"])


def test_evaluate_trade_floor_and_unpriced():
    s = snap({"V": [A("a1", "WR", 3000), A("z0", "WR", 0)] + BODIES("V"),
              "P": [A("b1", "WR", 3100)] + BODIES("P")})
    req, cfg = Request("V"), CFG10
    verdict = evaluate_trade(s, req, cfg, partner_team_id="P", give=["a1", "Vwr1"], receive=["b1"])
    assert (verdict.ok, verdict.reason) == (False, "floor")
    assert verdict.trade is not None
    verdict = evaluate_trade(s, req, cfg, partner_team_id="P", give=["z0"], receive=["b1"])
    assert (verdict.ok, verdict.reason, verdict.trade) == (False, "floor", None)


def test_unknown_viewer_raises():
    s = snap({"V": [A("a1", "WR", 3000)] + BODIES("V"), "P": [A("b1", "WR", 3100)] + BODIES("P")})
    with pytest.raises(ValueError):
        find_fair_trades(s, Request("nobody"), CFG10)
    with pytest.raises(ValueError):
        evaluate_trade(s, Request("nobody"), CFG10, partner_team_id="P",
                       give=["a1"], receive=["b1"])
