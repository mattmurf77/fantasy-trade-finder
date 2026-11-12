"""Sleeper trade universe crawler: standings, outcomes, schedule, as-of inputs.

Covers: weekly standings match the simulator's own standings (median league:
H2H and median records stored apart and combined; a tie); divisions;
the playoff cut-off (no playoff week enters the record; playoff vs
consolation phases); games back of the last playoff spot; derived vs
reported (/rosters) records, with a planted disagreement reported, not
hidden; outcomes from both brackets; a bye / unpaired row; an unplayed
future week judged by /state/nfl, not by zero points; the standing helper
for in-season, offseason-with-prior-season and prior-season-missing trades;
the outlook inputs as of a trade, proven to contain nothing dated after it
by changing every later value and getting identical output.
"""
from __future__ import annotations

import json

import pytest

from backend.sleeper_universe import asof, derive, standings
from backend.tests.support.sleeper_universe_world import L, connect, run_cli, standard_world


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    d = tmp_path_factory.mktemp("stand")
    w = standard_world()
    assert run_cli(w, d, "run")[0] == 0
    c = connect(d)
    yield w, c
    c.close()


def _week(c, lid, week):
    return {r["roster_id"]: dict(r) for r in c.execute(
        "SELECT * FROM standings_weeks WHERE league_id=? AND week=?", (lid, week))}


def test_records_match_simulator_including_median(full):
    w, c = full
    for lid in (L(101), L(102), L(103), L(201), L(301)):
        last = c.execute("SELECT MAX(week) FROM standings_weeks WHERE league_id=?",
                         (lid,)).fetchone()[0]
        got = _week(c, lid, last)
        for rid, t in w.truth_standings[lid].items():
            g = got[rid]
            assert (g["wins"], g["losses"], g["ties"]) == (t["w"], t["l"], t["t"]), (lid, rid)
            assert g["points_for"] == round(t["pf"], 2)
            assert g["points_against"] == round(t["pa"], 2)
    b = _week(c, L(201), 3)
    for g in b.values():
        assert g["h2h_wins"] + g["h2h_losses"] + g["h2h_ties"] <= 3
        assert g["median_wins"] + g["median_losses"] + g["median_ties"] == 3
        assert g["wins"] == g["h2h_wins"] + g["median_wins"]
    a = _week(c, L(103), 3)
    assert all(g["median_wins"] + g["median_losses"] == 0 for g in a.values())


def test_tie(full):
    w, c = full
    wk1 = _week(c, L(201), 1)
    assert wk1[1]["h2h_ties"] == wk1[2]["h2h_ties"] == 1
    assert wk1[1]["week_result"] == "T" and wk1[1]["week_opponent"] == 2


def test_divisions(full):
    w, c = full
    wk = _week(c, L(201), 3)
    assert {g["division"] for rid, g in wk.items() if rid <= 5} == {1}
    assert {g["division"] for rid, g in wk.items() if rid > 5} == {2}
    for d in (1, 2):
        members = sorted((g for g in wk.values() if g["division"] == d), key=lambda g: g["rank"])
        assert [g["division_rank"] for g in members] == [1, 2, 3, 4, 5]


def test_playoff_cutoff_and_phases(full):
    w, c = full
    assert c.execute("SELECT MAX(week) FROM standings_weeks WHERE league_id=?",
                     (L(101),)).fetchone()[0] == 3
    ph = {(r["week"], r["roster_id"]): r["phase"] for r in c.execute(
        "SELECT week, roster_id, phase FROM matchups WHERE league_id=?", (L(101),))}
    assert ph[(3, 1)] == "regular" and ph[(4, 1)] == "playoff" and ph[(4, 5)] == "consolation"
    assert ph[(5, 2)] == "playoff"


def test_games_back(full):
    w, c = full
    uneven = 0
    for lid in (L(103), L(201)):          # league B has a bye: unequal games played
        wk = _week(c, lid, 3)
        cut = next(g for g in wk.values() if g["rank"] == 4)
        assert cut["games_back"] == 0
        for g in wk.values():
            cw, cl = cut["wins"] + cut["ties"] / 2, cut["losses"] + cut["ties"] / 2
            gw, gl = g["wins"] + g["ties"] / 2, g["losses"] + g["ties"] / 2
            exp = ((cw - gw) + (gl - cl)) / 2
            assert g["games_back"] == exp
            uneven += exp != cw - gw
    assert uneven > 0                     # the losses term matters somewhere


def test_reported_mismatch_is_reported(full):
    w, c = full
    rows = {r["league_id"]: dict(r) for r in c.execute("SELECT * FROM standings_checks")}
    # league C: a wrong record, points right; league B: a stat correction on
    # one roster's points, records right. Judged apart, both reported.
    assert rows[L(301)]["matched"] == 0
    assert json.loads(rows[L(301)]["kinds_json"]) == {"wins": 1}
    assert (rows[L(301)]["record_matched"], rows[L(301)]["points_matched"]) == (0, 1)
    assert json.loads(rows[L(201)]["kinds_json"]) == {"points_for": 1}
    assert (rows[L(201)]["record_matched"], rows[L(201)]["points_matched"]) == (1, 0)
    assert all(r["matched"] == 1 for lid, r in rows.items() if lid not in (L(301), L(201)))


def test_outcomes_from_both_brackets(full):
    w, c = full
    o = {r["roster_id"]: dict(r) for r in c.execute("SELECT * FROM outcomes WHERE league_id=?",
                                                     (L(101),))}
    assert o[2]["champion"] == 1 and o[2]["final_place"] == 1
    assert o[1]["final_place"] == 2 and o[3]["final_place"] == 3 and o[4]["final_place"] == 4
    assert o[6]["final_place"] == 5 and o[5]["final_place"] == 6
    assert o[6]["finish_basis"] == "losers_bracket" and o[6]["made_playoffs"] == 0
    assert sorted(o[r]["seed"] for r in (1, 2, 3, 4)) == [1, 2, 3, 4]
    fin = _week(c, L(101), 3)
    assert sorted((1, 2, 3, 4), key=lambda r: fin[r]["rank"]) == sorted(
        (1, 2, 3, 4), key=lambda r: o[r]["seed"])
    ip = {r["finish_basis"] for r in c.execute("SELECT finish_basis FROM outcomes WHERE"
                                               " league_id=?", (L(103),))}
    assert ip == {"season_in_progress"}


def test_bye_or_unpaired_row(full):
    w, c = full
    m = {r["roster_id"]: dict(r) for r in c.execute(
        "SELECT * FROM matchups WHERE league_id=? AND week=2", (L(201),))}
    assert m[10]["matchup_id"] == 99 and m[10]["paired"] == 0 and m[10]["opponent_roster"] is None
    assert m[9]["matchup_id"] is None and m[9]["paired"] == 0
    assert m[1]["paired"] == 1 and m[m[1]["opponent_roster"]]["opponent_roster"] == 1
    wk2 = _week(c, L(201), 2)
    assert wk2[10]["week_result"] is None and wk2[9]["week_opponent"] is None


def test_unplayed_future_week_by_nfl_state(full):
    w, c = full
    pl = {r["week"]: (r["played"], r["has_points"]) for r in c.execute(
        "SELECT week, MAX(played) played, MAX(has_points) has_points FROM roster_weeks"
        " WHERE league_id=? GROUP BY week", (L(103),))}
    assert pl[3] == (1, 1)
    assert pl[4] == (0, 1)      # week in progress: points on the board, not played
    assert pl[5] == (0, 0)
    fut = c.execute("SELECT COUNT(*) FROM matchups WHERE league_id=? AND week=5 AND paired=1",
                    (L(103),)).fetchone()[0]
    assert fut == 8             # the remaining schedule is known
    assert c.execute("SELECT COUNT(*) FROM matchups WHERE league_id=? AND played=0 AND"
                     " paired=0", (L(201),)).fetchone()[0] > 0


def test_standing_helper(full, tmp_path):
    w, c = full
    s = standings.standing_for_trade(c, L(103), w.truth_trades[L(103)][1])
    assert s[1]["basis"] == "current_season" and s[1]["week"] == 1
    assert s[1]["weeks_remaining"] == 6 - 1
    off = standings.standing_for_trade(c, L(103), w.truth_trades[L(103)][0])
    assert off[3]["basis"] == "prior_season_final" and off[3]["final_place"] == 3
    w2 = standard_world()
    assert run_cli(w2, tmp_path, "run", "--seasons", "2026")[0] == 0
    c2 = connect(tmp_path)
    off2 = standings.standing_for_trade(c2, L(103), w2.truth_trades[L(103)][0])
    assert off2[3] == {"basis": "prior_season_not_in_store"}


def test_outlook_inputs_contain_nothing_after_the_trade(tmp_path):
    w = standard_world()
    assert run_cli(w, tmp_path, "run")[0] == 0
    c = connect(tmp_path)
    txid = w.truth_trades[L(103)][3]           # leg 3: known weeks are 1 and 2
    before = asof.outlook_inputs(c, L(103), txid)
    assert before["as_of_week"] == 2
    side = before["sides"][4]
    assert [p["week"] for p in side["played"]] == [1, 2]
    assert [r["week"] for r in side["remaining"]] == [3, 4, 5, 6]
    assert all(int(k) <= 2 for p in side["roster"] for k in p["weekly_points"])
    assert side["roster"] and {p["player_id"] for p in side["roster"]} == w.truth_pre_trade[txid][4]
    # Change every value dated at or after the trade's week, re-derive: same answer.
    c.execute("UPDATE roster_weeks SET points=points+1000, players_points_json="
              "replace(players_points_json, ':', ':9') WHERE league_id=? AND week>=3", (L(103),))
    c.execute("UPDATE matchups SET points=points+1000 WHERE league_id=? AND week>=3", (L(103),))
    c.commit()
    derive.derive_all(c)
    after = asof.outlook_inputs(c, L(103), txid)
    assert json.dumps(after, sort_keys=True, default=sorted) == json.dumps(
        before, sort_keys=True, default=sorted)
