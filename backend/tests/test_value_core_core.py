"""Value-core core: pricing, hard rules, enumeration and caps.

Acceptance tests from docs/plans/value-core-engine/specs.md section 5.1; the
implementation spec is lld.md section 4.
"""
import dataclasses
import math
from itertools import combinations

import pytest

from backend.value_core import core
from backend.value_core.core import (REJECT_CODES, THROWIN_MIN_COMPARISONS, effective_band, evaluate_trade,
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
                                 "MAX_THROWIN_OPTIONS", "PREMIUM_EXPONENT", "RATIO_TOL",
                                 "REJECT_CODES", "THROWIN_MIN_COMPARISONS", "effective_band",
                                 "stud_premium", "throwin_ok",
                                 "evaluate_trade", "find_fair_trades"}
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


# ── Throw-ins (operator, 2026-10-01): a piece too small for the junk rules may ride along
#    only if its recipient values it at >= 2x consensus market and at least the floor. ──

def _gap_league():
    """V gives a1 (3000) for b1 (2600): 0.867, outside ±10%. P's sub-floor WR pw9 (300)
    closes the gap. pw8 keeps P's FLEX filled once b1 and pw9 leave."""
    v = [A("a1", "WR", 3000)] + BODIES("V")
    p = [A("b1", "WR", 2600), A("pw9", "WR", 300), A("pw8", "WR", 280)] + BODIES("P")
    return snap({"V": v, "P": p})


def test_throwin_to_viewer_needs_double_value():
    s = _gap_league()
    loves = Board({"pw9": 700.0}, {"pw9": 12})          # 700 >= 2 x 300 and >= 450
    trades, _ = run(s, board=loves)
    t = next(t for t in trades if t.give == ("a1",) and "b1" in t.receive)
    assert t.receive == ("b1", "pw9") and t.throwin == "pw9"
    # a throw-in is not a piece for the stud premium: 1-for-1 core, no premium
    assert t.premium_side is None
    assert t.adjusted_ratio == pytest.approx(2900 / 3000)

    likes = Board({"pw9": 550.0}, {"pw9": 12})          # 550 < 2 x 300: not a clear throw-in
    trades, _ = run(s, board=likes)
    assert not any(t.give == ("a1",) and "b1" in t.receive for t in trades)
    trades, _ = run(s)                                    # no board, no evidence
    assert not any(t.throwin for t in trades)


def test_throwin_value_must_clear_the_floor():
    v = [A("a1", "WR", 3000)] + BODIES("V")
    p = [A("b1", "WR", 2850), A("pw9", "WR", 150), A("pw8", "WR", 280)] + BODIES("P")
    s = snap({"V": v, "P": p})
    trades, _ = run(s, board=Board({"pw9": 400.0}, {"pw9": 5}))  # 400 >= 2 x 150 but < 450
    assert not any(t.throwin for t in trades)
    trades, _ = run(s, board=Board({"pw9": 460.0}, {"pw9": 5}))
    assert any(t.throwin == "pw9" for t in trades)


def test_throwin_to_partner_uses_their_published_board():
    v = [A("a1", "WR", 3000), A("va9", "WR", 300), A("va8", "WR", 280)] + BODIES("V")
    p = [A("b1", "WR", 3500)] + BODIES("P")             # 3500 / 3000 = 1.167: outside ±10%
    s = snap({"V": v, "P": p})
    trades, _ = run(s)
    assert not any(t.receive == ("b1",) for t in trades)
    s2 = dataclasses.replace(s, partner_boards={"P": Board({"va9": 900.0}, {"va9": 20})})
    trades, _ = run(s2)
    t = next(t for t in trades if t.receive == ("b1",))
    assert t.give == ("a1", "va9") and t.throwin == "va9"
    assert t.premium_side is None
    assert t.adjusted_ratio == pytest.approx(3500 / 3300)


def test_throwin_is_exempt_from_reducible_and_at_most_one():
    """A qualifying throw-in can sweeten an already-fair trade (the deck keeps the better
    version of the idea); no trade ever carries two sub-floor pieces."""
    v = [A("a1", "WR", 3000)] + BODIES("V")
    p = [A("b1", "WR", 3000), A("pw9", "WR", 250), A("pw7", "WR", 260), A("pw8", "WR", 280)] + BODIES("P")
    s = snap({"V": v, "P": p})
    board = Board({"pw9": 600.0, "pw7": 700.0}, {"pw9": 4, "pw7": 4})
    trades, _ = run(s, board=board)
    got = pairs(trades)
    assert (("a1",), ("b1",)) in got
    assert (("a1",), ("b1", "pw7")) in got and (("a1",), ("b1", "pw9")) in got
    for t in trades:
        assert sum(s.assets[a].market < 450 for a in t.give + t.receive) <= 1


def test_evaluate_trade_marks_the_explicit_throwin():
    s = _gap_league()
    ok = evaluate_trade(s, Request("V", board=Board({"pw9": 700.0}, {"pw9": 3})), CFG10,
                        partner_team_id="P", give=["a1"], receive=["b1", "pw9"])
    assert ok.ok and ok.trade.throwin == "pw9"
    no = evaluate_trade(s, Request("V"), CFG10, partner_team_id="P", give=["a1"], receive=["b1", "pw9"])
    assert not no.ok and no.reason == "floor" and no.trade.throwin is None


def test_throwin_needs_real_evidence_on_both_sides():
    """No ranking work behind the recipient's value (a default Elo), or no consensus value on
    the piece (market 0: there is no "double" to clear), never qualifies a throw-in."""
    s = _gap_league()
    unranked = Board({"pw9": 900.0}, {"pw9": 0})
    trades, _ = run(s, board=unranked)
    assert not any(t.throwin for t in trades)
    v = [A("a1", "WR", 3000)] + BODIES("V")
    p = [A("b1", "WR", 2850), A("pw9", "WR", 0), A("pw8", "WR", 280)] + BODIES("P")
    trades, _ = run(snap({"V": v, "P": p}), board=Board({"pw9": 900.0}, {"pw9": 10}))
    assert not any(t.throwin for t in trades)


def test_throwin_never_switches_the_stud_premium():
    """Review finding 2026-10-01: counting the throw-in as a piece turned a 2-for-1 into a
    2-for-2, dropped the consolidation premium and let a too-big gain through."""
    v = [A("a", "WR", 4000), A("b", "WR", 3600)] + BODIES("V")
    p = [A("s", "WR", 8000), A("ti", "WR", 300), A("pw8", "WR", 280)] + BODIES("P")
    s = snap({"V": v, "P": p})
    trades, _ = run(s, board=Board({"ti": 700.0}, {"ti": 5}))
    assert (("a", "b"), ("s",)) not in pairs(trades)          # 1.194 with the premium: too big a gain
    assert (("a", "b"), ("s", "ti")) not in pairs(trades)     # still 2-for-1 at the core: still too big


def test_throwin_shortlist_is_cut_per_pair_after_the_junk_check():
    """Review finding 2026-10-01: three bigger players the viewer also loves (not junk in a
    3000 trade) used to fill the shortlist and hide the real throw-in."""
    v = [A("a1", "WR", 3000)] + BODIES("V")
    p = ([A("b1", "WR", 2600), A("pw9", "WR", 300), A("pw8", "WR", 280)]
         + [A(f"m{i}", "RB", 1000 + 100 * i) for i in range(1, 4)] + BODIES("P"))
    s = snap({"V": v, "P": p})
    board = Board({"pw9": 700.0, "m1": 2400.0, "m2": 2600.0, "m3": 2800.0},
                  {"pw9": 5, "m1": 5, "m2": 5, "m3": 5})
    trades, _ = run(s, board=board)
    t = next(t for t in trades if (t.give, t.receive) == (("a1",), ("b1", "pw9")))
    assert t.throwin == "pw9"
    assert evaluate_trade(s, Request("V", board=board), CFG10, partner_team_id="P",
                          give=["a1"], receive=["b1", "pw9"]).ok


def test_throwin_needs_three_comparisons():
    """One or two matchups are not an opinion (review finding: partner boards take full weight
    from a single comparison)."""
    s = _gap_league()
    trades, _ = run(s, board=Board({"pw9": 700.0}, {"pw9": 2}))
    assert not any(t.throwin for t in trades)
    trades, _ = run(s, board=Board({"pw9": 700.0}, {"pw9": THROWIN_MIN_COMPARISONS}))
    assert any(t.throwin == "pw9" for t in trades)
