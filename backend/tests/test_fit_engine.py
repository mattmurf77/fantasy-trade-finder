"""Fit engine (backend/fit_engine.py): the two scorers, the shared generator and deck,
and the rest-of-season projection reader. Operator 2026-10-09, plan "Fit Scorecard Test Plan"."""
import pytest

from backend import fit_engine as fe
from backend.value_core.types import (Asset, Board, CoreConfig, LeagueSnapshot, Request, RosterRules,
                                      Team, TeamWindow, DEFAULT_WINDOW)

SLOTS = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX")
CONTENDER = TeamWindow("contender", 1.0, "declared", None, 0.0)
REBUILDER = TeamWindow("rebuilder", -1.0, "declared", None, 0.0)


def A(id, pos, market, age=26.0):
    kind = "pick" if pos == "PICK" else "player"
    return Asset(id, kind, pos, id.upper(), None if kind == "pick" else age, float(market))


def bodies(t):
    return [A(f"{t}qb", "QB", 500), A(f"{t}rb1", "RB", 500), A(f"{t}rb2", "RB", 500),
            A(f"{t}wr1", "WR", 500), A(f"{t}wr2", "WR", 500), A(f"{t}wr3", "WR", 500),
            A(f"{t}te", "TE", 500), A(f"{t}rb3", "RB", 460)]


def snap(teams, windows=None, partner_boards=None):
    assets = {a.id: a for lst in teams.values() for a in lst}
    return LeagueSnapshot("L1", "1qb_ppr", assets,
                          {t: Team(t, t, tuple(a.id for a in lst), 0, (windows or {}).get(t, DEFAULT_WINDOW))
                           for t, lst in teams.items()},
                          RosterRules(SLOTS, None), first_round_value=1492.0, elite_value=8457.0,
                          partner_boards=partner_boards or {})


def test_slot_demand_counts_flex_shares():
    d = fe.slot_demand(("QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX"))
    assert d == pytest.approx({"QB": 1.8, "RB": 2.48, "WR": 2.6, "TE": 1.12})


def test_team_value_a_window_need_and_board():
    s = snap({"C": [A("star", "WR", 3000, 27), A("k1", "PICK", 2000)] + bodies("C"),
              "R": [A("vet", "WR", 2500, 30), A("kid", "WR", 2400, 22), A("k2", "PICK", 2000)] + bodies("R")},
             windows={"C": CONTENDER, "R": REBUILDER})
    lg = fe.build_league(s)
    need_c = fe.A_NEED["contender"].get(lg.need["C"]["WR"], 1.0)
    assert fe.team_value_a(lg, "C", "star", None) == pytest.approx(3000 * 1.3 * need_c)      # starter
    assert fe.team_value_a(lg, "C", "k1", None) == pytest.approx(2000 * 0.6)                 # pick, contender
    assert fe.team_value_a(lg, "R", "k2", None) == pytest.approx(2000 * 1.3)                 # pick, rebuilder
    need_r = fe.A_NEED["rebuilder"].get(lg.need["R"]["WR"], 1.0)
    assert fe.team_value_a(lg, "R", "vet", None) == pytest.approx(2500 * 0.5 * need_r)       # old, rebuilder
    assert fe.team_value_a(lg, "R", "kid", None) == pytest.approx(2400 * 1.3 * need_r)       # young, rebuilder
    board = Board({"star": 9000.0}, {"star": 20})
    assert fe.team_value_a(lg, "C", "star", board) == pytest.approx(3000 * 1.3 * need_c * 1.5)  # clamped
    # Depth: a 500 body behind better WRs does not start for C.
    assert not lg.would_start("C", "Cwr3")


def test_build_grades_profiles_and_redraft_scale():
    s = snap({"T1": [A("vet", "WR", 470, 31), A("rook", "WR", 3000, 21), A("k", "PICK", 2000)] + bodies("T1"),
              "T2": bodies("T2")})
    lg = fe.build_league(s)
    ros = {"vet": 250.0, "rook": 20.0, **{f"T1{x}": 60.0 for x in ("wr1", "wr2", "wr3")},
           **{f"T2{x}": 40.0 for x in ("wr1", "wr2", "wr3")}}
    g = fe.build_grades(lg, ros, "1qb_ppr")
    assert g.profile["vet"] == "win_now" and g.profile["rook"] == "future" and g.profile["k"] == "future"
    assert g.redraft_pct["vet"] > g.dynasty_pct["vet"]
    assert g.redraft_value["vet"] > 470                 # mapped onto the market scale by quantile
    assert g.redraft_value["k"] == 0.0


def test_team_value_b_priority_and_veteran_fix():
    s = snap({"C": bodies("C"), "R": [A("vet", "WR", 1000, 31)] + bodies("R")},
             windows={"C": CONTENDER, "R": REBUILDER})
    lg = fe.build_league(s)
    g = fe.Grades(dynasty_pct={}, redraft_pct={}, redraft_value={"vet": 4000.0},
                  profile={"vet": "win_now"})
    need = lambda t: fe.B_NEED.get(lg.need[t]["WR"], 1.0)
    # Contender: 0.7 x redraft + 0.3 x dynasty.
    assert fe.team_value_b(lg, g, "C", "vet", None) == pytest.approx((0.7 * 4000 + 0.3 * 1000) * need("C"))
    # Rebuilder (fit-b-2): a Win-now player gets no redraft credit -> 0.8 x market, below market.
    assert fe.team_value_b(lg, g, "R", "vet", None) == pytest.approx(0.8 * 1000 * need("R"))
    assert fe.b_sells(lg, g, "R", "vet") and not fe.b_buys(lg, g, "R", "vet")
    assert fe.b_buys(lg, g, "C", "vet")


def _trade_league():
    """C (contender) holds a pick it does not need; R (rebuilder) holds a 30-year-old starter."""
    return snap({"C": [A("k1", "PICK", 2600)] + bodies("C"),
                 "R": [A("vet", "WR", 2700, 30), A("Rk", "PICK", 300)] + bodies("R")},
                windows={"C": CONTENDER, "R": REBUILDER})


def _b_league():
    """As _trade_league, but the vet's market sits mid-league so his top redraft makes him Win-now."""
    return snap({"C": [A("k1", "PICK", 900), A("Cstar", "WR", 3000, 24)] + bodies("C"),
                 "R": [A("vet", "WR", 900, 31), A("Rk", "PICK", 300), A("Rstar", "WR", 3000, 24)] + bodies("R")},
                windows={"C": CONTENDER, "R": REBUILDER})


@pytest.mark.parametrize("arm", ["fit_a", "fit_b"])
def test_generate_finds_the_mutual_fit_and_obeys_core_rules(arm):
    s = _trade_league() if arm == "fit_a" else _b_league()
    lg = fe.build_league(s)
    req = Request("C")
    ros = {a: 50.0 for a in s.assets if a[1:] in ("qb", "rb1", "rb2", "rb3", "wr1", "wr2", "wr3", "te")}
    grades = fe.build_grades(lg, {**ros, "vet": 240.0, "Cstar": 200.0, "Rstar": 200.0}, "1qb_ppr")
    scorer = fe.Scorer(arm, lg, req, grades if arm == "fit_b" else None)
    trades, diag = fe.generate(s, req, scorer)
    assert ("R", ("k1",), ("vet",)) in {(t.partner_team_id, t.give, t.receive) for t in trades}
    t = next(t for t in trades if t.give == ("k1",) and t.receive == ("vet",))
    assert t.gain_viewer > 0 and t.mutual == min(t.gain_viewer, t.gain_partner)
    assert t.gain_partner > 0 if arm == "fit_a" else t.gain_partner >= 0   # B: neither side loses
    # Reverse viewpoint: the rebuilder never gives its pick for a player (picks_for_players).
    trades_r, _ = fe.generate(s, Request("R"), fe.Scorer(arm, lg, Request("R"),
                                                         grades if arm == "fit_b" else None))
    assert not any("Rk" in t.give and t.receive for t in trades_r)


def test_scorer_needs_grades_for_b():
    with pytest.raises(ValueError):
        fe.Scorer("fit_b", fe.build_league(_trade_league()), Request("C"))


def test_assemble_one_idea_partner_and_asset_caps():
    s = _trade_league()
    mk = lambda p, g, r, m: fe.FitTrade(p, g, r, m, m, m)
    trades = [mk("R", ("k1",), ("vet",), 0.9),
              mk("R", ("k1",), ("vet", "Rrb3"), 0.8),          # same idea -> dropped
              mk("R", ("Cwr1",), ("Rwr1",), 0.7)]
    deck = fe.assemble(trades, s)
    assert [(t.give, t.receive) for t in deck] == [(("k1",), ("vet",)), (("Cwr1",), ("Rwr1",))]
    many = [mk("R", (f"Cx{i}",), ("vet",), 1 - i / 100) for i in range(6)]
    s2 = snap({"C": [A(f"Cx{i}", "WR", 600 + i) for i in range(6)] + bodies("C"),
               "R": [A("vet", "WR", 2700, 30)] + bodies("R")})
    assert len(fe.assemble(many, s2)) == fe.ASSET_CAP          # "vet" in at most 3 cards


def test_fetch_ros_points_sums_remaining_weeks_and_te_premium():
    calls = []

    def fetch(url):
        calls.append(url)
        if url.endswith("/state/nfl"):
            return {"season": "2026", "week": 16}
        week = int(url.split("/2026/")[1].split("?")[0])
        return [{"player_id": "te1", "player": {"position": "TE"}, "stats": {"pts_ppr": 10.0 * week, "rec": 4}},
                {"player_id": "wr1", "player": {"position": "WR"}, "stats": {"pts_ppr": 12.0}},
                {"player": {}, "stats": {"pts_ppr": 99}}]

    out = fe.fetch_ros_points(fetch, "sf_tep")
    assert (out["season"], out["from_week"], out["weeks"]) == (2026, 16, 2)
    assert out["points"] == {"te1": pytest.approx(160 + 2 + 170 + 2), "wr1": pytest.approx(24.0)}
    assert len(calls) == 3
    assert fe.fetch_ros_points(fetch, "1qb_ppr", season=2026, week=17)["points"]["te1"] == pytest.approx(170)
