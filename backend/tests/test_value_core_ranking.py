"""value-core WP2: three-weight ranking and card reasons (lld.md 5.2-5.5, specs.md 5.2).

FairTrade objects are built by hand; the core is not involved.
"""
import pytest

from backend.value_core import ranking
from backend.value_core.types import *   # in tests only


def A(id, pos, market, age=25.0):
    kind = "pick" if pos == "PICK" else "player"
    return Asset(id, kind, pos, id.upper(), None if kind == "pick" else age, float(market))

BODIES = lambda t: [A(f"{t}qb", "QB", 300), A(f"{t}rb1", "RB", 300), A(f"{t}rb2", "RB", 300),
                    A(f"{t}wr1", "WR", 300), A(f"{t}wr2", "WR", 300), A(f"{t}te", "TE", 300)]
SLOTS = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX")
NO_FLEX = ("QB", "RB", "RB", "WR", "WR", "TE")

def snap(teams, *, slots=SLOTS, max_players=None, other=None, windows=None):
    assets = {a.id: a for lst in teams.values() for a in lst}
    return LeagueSnapshot("L1", "1qb_ppr", assets,
        {t: Team(t, t, tuple(a.id for a in lst), (other or {}).get(t, 0),
                 (windows or {}).get(t, DEFAULT_WINDOW)) for t, lst in teams.items()},
        RosterRules(tuple(slots), max_players), first_round_value=1492.0, elite_value=8457.0)


def ft(s, partner, give, receive):
    order = lambda i: (-s.assets[i].market, i)
    g, r = tuple(sorted(give, key=order)), tuple(sorted(receive, key=order))
    gm, rm = sum(s.assets[i].market for i in g), sum(s.assets[i].market for i in r)
    return FairTrade(partner, g, r, gm, rm, rm / gm, 0.0, None, False, (0, 0))


def score_one(s, trade, *, board=None, cfg=RankConfig()):
    req = Request("V", board=board)
    (st,) = ranking.score_trades(s, req, [trade], cfg)
    return st, req


def TW(window):
    return TeamWindow(window, 0.0, "declared", None, 0.0)


def test_value_even_small_return():
    s = snap({"V": [A("Vqb", "QB", 300), A("Vrb1", "RB", 300), A("Vrb2", "RB", 300),
                    A("Vwr1", "WR", 2000), A("Vwr2", "WR", 2000), A("Vte", "TE", 300),
                    A("x", "WR", 800, age=26)],
              "P": BODIES("P") + [A("y", "WR", 800, age=26)]}, slots=NO_FLEX)
    st, _ = score_one(s, ft(s, "P", ["x"], ["y"]))
    assert st.scores.value == pytest.approx(0.5 * 0.5 + 0.5 * (800 / 1492))
    assert st.detail["value"]["best_in_starter"] is False


def test_value_starter_back_scores_one():
    s = snap({"V": [A("Vqb", "QB", 300), A("Vrb1", "RB", 300), A("Vrb2", "RB", 300),
                    A("Vwr1", "WR", 2000), A("Vwr2", "WR", 500), A("Vte", "TE", 300),
                    A("pk", "PICK", 1300)],
              "P": BODIES("P") + [A("y", "WR", 1300)]})
    st, _ = score_one(s, ft(s, "P", ["pk"], ["y"]))
    assert st.detail["value"]["s_piece"] == 1.0
    assert st.detail["value"]["best_in_starter"] is True


def test_value_first_round_pick_scores_one():
    s = snap({"V": BODIES("V") + [A("x", "WR", 2117)],
              "P": BODIES("P") + [A("pk", "PICK", 2117)]})
    st, _ = score_one(s, ft(s, "P", ["x"], ["pk"]))
    assert st.detail["value"]["s_piece"] == 1.0
    assert st.detail["value"]["best_in_starter"] is False


def test_value_delta_saturation():
    s = snap({"V": BODIES("V") + [A("x", "WR", 1000)],
              "P": BODIES("P") + [A("y1", "WR", 1250), A("y2", "WR", 800)]})
    up, _ = score_one(s, ft(s, "P", ["x"], ["y1"]))
    down, _ = score_one(s, ft(s, "P", ["x"], ["y2"]))
    assert up.detail["value"]["s_delta"] == 1.0
    assert down.detail["value"]["s_delta"] == pytest.approx(0.0)


def test_outlook_rewards_both_windows():
    # Spec deviation (reported): the prospect `p` is an RB here, not a WR. As a WR worth
    # 2500 he would be V's value-optimal WR2 over the 1000 WR, so he could not be both
    # "not a V starter" and have the incoming vet "replace V's WR2 worth 1000". As an RB
    # behind two better RBs (no FLEX slot) every stated condition holds.
    teams = {"V": [A("Vqb", "QB", 300), A("Vrb1", "RB", 3000), A("Vrb2", "RB", 2800),
                   A("p", "RB", 2500, age=21), A("Vwr1", "WR", 3000), A("Vwr2", "WR", 1000),
                   A("Vte", "TE", 300)],
             "P": BODIES("P") + [A("v", "WR", 2400, age=29)]}
    s = snap(teams, slots=NO_FLEX, windows={"V": TW("contender"), "P": TW("rebuilder")})
    trade = ft(s, "P", ["p"], ["v"])
    st, _ = score_one(s, trade)
    assert "p" not in ranking.lineup_value(s.teams["V"].asset_ids, s)[1]
    assert st.detail["outlook"]["viewer"]["lineup_gain"] == 1400.0
    assert st.scores.outlook > 0.5

    swapped = snap(teams, slots=NO_FLEX, windows={"V": TW("rebuilder"), "P": TW("contender")})
    st2, _ = score_one(swapped, ft(swapped, "P", ["p"], ["v"]))
    assert st2.scores.outlook < 0.5


def _even():
    s = snap({"V": BODIES("V") + [A("a1", "WR", 3000)], "P": BODIES("P") + [A("b1", "WR", 3000)]})
    return s, ft(s, "P", ["a1"], ["b1"])


def test_rank_neutral_without_board():
    s, trade = _even()
    st, _ = score_one(s, trade, board=None)
    assert st.scores.rank == 0.5
    assert st.detail["rank"]["has_board"] is False


def test_rank_above_in_below_out():
    s, trade = _even()
    st, _ = score_one(s, trade, board=Board({"b1": 3600.0, "a1": 2700.0}, {"b1": 10, "a1": 10}))
    r = st.detail["rank"]
    assert r["gap_rel"] == pytest.approx(0.30)
    assert st.scores.rank == 1.0
    assert r["top_asset"] == "b1"
    assert r["top_side"] == "receive"


def test_priority_weighted_mean():
    s, trade = _even()
    st, _ = score_one(s, trade, board=Board({"b1": 3300.0}, {"b1": 4}), cfg=RankConfig(2, 1, 1))
    v, o, r = st.scores.value, st.scores.outlook, st.scores.rank
    assert st.scores.priority == pytest.approx((2 * v + o + r) / 4)


def test_zero_weights_raise():
    s, trade = _even()
    with pytest.raises(ValueError):
        ranking.score_trades(s, Request("V"), [trade], RankConfig(0, 0, 0))


def test_reasons_value_outlook_rank():
    ws = [A(f"w{i:02d}", "WR", 5000 - 200 * (i - 1), age=30 if i == 20 else 25.0) for i in range(1, 21)]
    s = snap({"V": BODIES("V") + [A("x", "WR", 1200, age=22)], "P": BODIES("P") + ws},
             windows={"P": TW("rebuilder")})
    st, req = score_one(s, ft(s, "P", ["x"], ["w20"]), board=Board({"w20": 3700.0}, {"w20": 12}))
    assert ranking.card_reasons(st, s, req) == (
        "Fair on value", "Fits their rebuild", "You rank W20 12 spots above market")


def test_reasons_pay_over_market():
    s = snap({"V": BODIES("V") + [A("x", "WR", 1100)], "P": BODIES("P") + [A("y", "WR", 1000)]})
    st, req = score_one(s, ft(s, "P", ["x"], ["y"]))
    assert ranking.card_reasons(st, s, req)[0] == "You pay 9% over market"


def test_reasons_piece_fills_slot():
    s = snap({"V": BODIES("V") + [A("x", "WR", 1000)], "P": BODIES("P") + [A("y", "WR", 1000)]})
    st, req = score_one(s, ft(s, "P", ["x"], ["y"]))
    assert ranking.card_reasons(st, s, req) == ("Fair on value", "Y would start for you")


def test_score_order_preserved():
    s = snap({"V": BODIES("V") + [A("a1", "WR", 3000), A("a2", "RB", 1500), A("a3", "TE", 900)],
              "P": BODIES("P") + [A("b1", "WR", 3100), A("b2", "RB", 1400), A("b3", "WR", 950)]})
    trades = [ft(s, "P", ["a3"], ["b3"]), ft(s, "P", ["a1"], ["b1"]), ft(s, "P", ["a2"], ["b2"]),
              ft(s, "P", ["a1", "a3"], ["b1", "b3"]), ft(s, "P", ["a2"], ["b3", "b2"])]
    scored = ranking.score_trades(s, Request("V"), trades, RankConfig())
    assert [st.trade for st in scored] == trades


def test_reasons_explain_the_throwin():
    """A card carrying a throw-in says whose board values it, and by how much."""
    import dataclasses
    s = snap({"V": BODIES("V") + [A("x", "WR", 1000), A("vt", "WR", 200)],
              "P": BODIES("P") + [A("y", "WR", 950), A("pt", "RB", 250)]})
    to_viewer = dataclasses.replace(ft(s, "P", ["x"], ["y", "pt"]), throwin="pt")
    st, req = score_one(s, to_viewer, board=Board({"pt": 575.0}, {"pt": 9}))
    assert "Throw-in: you rank PT at 2.3× market" in ranking.card_reasons(st, s, req)

    s2 = dataclasses.replace(s, partner_boards={"P": Board({"vt": 600.0}, {"vt": 30})})
    to_partner = dataclasses.replace(ft(s2, "P", ["x", "vt"], ["y"]), throwin="vt")
    st2, req2 = score_one(s2, to_partner)
    assert "Throw-in: they rank VT at 3.0× market" in ranking.card_reasons(st2, s2, req2)
    assert len(ranking.card_reasons(st2, s2, req2)) <= 3
