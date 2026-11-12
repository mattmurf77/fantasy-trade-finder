"""Sleeper trade universe crawler: leagues with no bracket, and null answers (pilot hotfix).

The pilot (2026-11-12) stopped on three 2024 leagues whose brackets answer
JSON null: playoffs switched off (playoff_week_start 0, bracket_id null).
Covers: a null bracket is an empty bracket and the league-season completes;
with no playoffs every played week is regular season, outcomes record no
playoff result and the finish is the regular-season rank (labelled), and the
standing and as-of helpers still work; null on the other list endpoints whose
evidence does not settle it is a non-fatal "none" counted per endpoint in
runs and the report, while null on rosters, an empty body and a dict stay
failures; three failed league-seasons of the same rejected shape say so.
"""
from __future__ import annotations

import json

import pytest

from backend.sleeper_universe import asof, client as cl, pull, standings
from backend.sleeper_universe.report import build_report
from backend.tests.support.sleeper_universe_world import (
    FakeClock, L, add_no_playoff_league, connect, run_cli, standard_world)


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    d = tmp_path_factory.mktemp("nobracket")
    w = standard_world()
    lid = add_no_playoff_league(w)
    code, lines = run_cli(w, d, "run")
    assert code == 0, lines
    c = connect(d)
    yield w, c, lid
    c.close()


def test_null_bracket_league_completes_with_no_playoff_result(store):
    w, c, lid = store
    assert c.execute("SELECT COUNT(*) FROM pull_checkpoints WHERE league_id=?", (lid,)).fetchone()[0] == 1
    assert c.execute("SELECT playoff_week_start FROM leagues WHERE league_id=?", (lid,)).fetchone()[0] == 0
    weeks = [r[0] for r in c.execute("SELECT DISTINCT week FROM standings_weeks WHERE league_id=?"
                                     " ORDER BY week", (lid,))]
    assert weeks == [1, 2, 3, 4, 5]
    assert {r[0] for r in c.execute("SELECT DISTINCT phase FROM matchups WHERE league_id=?",
                                    (lid,))} == {"regular"}
    final = {r["roster_id"]: r["rank"] for r in c.execute(
        "SELECT roster_id, rank FROM standings_weeks WHERE league_id=? AND week=5", (lid,))}
    for o in c.execute("SELECT * FROM outcomes WHERE league_id=?", (lid,)):
        assert o["finish_basis"] == "regular_season_rank"
        assert o["final_place"] == final[o["roster_id"]]
        assert o["made_playoffs"] is None and o["champion"] is None and o["seed"] is None


def test_standing_and_asof_work_without_playoffs(store):
    w, c, lid = store
    txid = w.truth_trades[lid][0]                 # leg 3: weeks 1-2 known
    s = standings.standing_for_trade(c, lid, txid)
    assert s[1]["basis"] == "current_season" and s[1]["week"] == 2
    assert s[1]["weeks_remaining"] == 3           # weeks 3, 4, 5 still to play
    inputs = asof.outlook_inputs(c, lid, txid)
    assert [r["week"] for r in inputs["sides"][1]["remaining"]] == [3, 4, 5]
    assert {p["player_id"] for p in inputs["sides"][1]["roster"]} == w.truth_pre_trade[txid][1]


def test_null_on_unsettled_list_endpoints_is_counted_not_fatal(tmp_path):
    w = standard_world()
    lid = add_no_playoff_league(w)
    w.faults[f"league/{L(102)}/transactions/18"] = (200, b"null")
    w.faults[f"league/{L(102)}/traded_picks"] = (200, b"null")
    code, lines = run_cli(w, tmp_path, "run")
    assert code == 0
    c = connect(tmp_path)
    assert c.execute("SELECT COUNT(*) FROM pull_checkpoints WHERE league_id IN (?,?)",
                     (L(102), lid)).fetchone()[0] == 2
    nulls = json.loads(c.execute("SELECT summary_json FROM runs ORDER BY run_id DESC"
                                 ).fetchone()[0])["null_as_none"]
    assert nulls == {"league.transactions": 1, "league.traded_picks": 1,
                     "league.winners_bracket": 1, "league.losers_bracket": 1}
    rep = build_report(c)
    assert rep["null_answers_accepted_as_none_by_endpoint"]["league.traded_picks"] == 1
    assert any(x.startswith("null answers accepted as none") for x in lines)


def test_null_on_rosters_is_still_a_failure(tmp_path):
    w = standard_world()
    w.faults[f"league/{L(102)}/rosters"] = (200, b"null")
    run_cli(w, tmp_path, "run")
    c = connect(tmp_path)
    assert c.execute("SELECT kind FROM pull_failures WHERE league_id=?",
                     (L(102),)).fetchone()[0] == "league.rosters:not_a_list"


def test_client_null_rules():
    clock = FakeClock()
    seq = [(200, {}, b"null"), (200, {}, b"null")] + [(200, {}, b"null")] * 6 + [(200, {}, b"")] * 6

    def tr(url, h, t):
        return seq.pop(0)
    c = cl.SleeperClient(tr, clock=clock, sleep=clock.sleep)
    assert c.get("/league/1/winners_bracket", expect=list, null_ok=True) is None
    assert c.nulls == {"league.winners_bracket": 1}
    assert c.get("/league/1/drafts", expect=list, null_ok=True) is None
    with pytest.raises(cl.RequestFailed) as e:
        c.get("/league/1/rosters", expect=list)            # null not allowed here
    assert e.value.status == "not_a_list"
    c2 = cl.SleeperClient(tr, clock=clock, sleep=clock.sleep)   # fresh failure count
    with pytest.raises(cl.RequestFailed) as e:
        c2.get("/league/1/winners_bracket", expect=list, null_ok=True)   # empty body
    assert e.value.status == "empty_body"


def test_three_same_shape_failures_say_the_assumption_is_wrong(tmp_path):
    w = standard_world()
    for n in (101, 102, 103, 201, 301):
        w.faults[f"league/{L(n)}/winners_bracket"] = (200, b'{"unexpected": 1}')
    assert run_cli(standard_world(), tmp_path, "discover")[0] == 0
    code, lines = run_cli(w, tmp_path, "pull")
    assert code == cl.CircuitOpen.exit_code
    msg = next(x for x in lines if x.startswith("Stopped:"))
    assert "failed the same way (league.winners_bracket:not_a_list)" in msg
    assert "assumption" in msg


def test_shape_kinds_are_not_transport_kinds():
    assert pull._is_shape_kind("league.winners_bracket:not_a_list")
    assert pull._is_shape_kind("league_id_mismatch")
    assert not pull._is_shape_kind("league.users:500")
    assert not pull._is_shape_kind("league.users:network")


def test_token_bucket_never_stalls_on_a_float_remainder():
    """Found by the hotfix tests: a remainder like 1e-12 s cannot move a clock
    at 1e9 s, so the bucket waited forever. It now treats a token within 1e-9
    as whole and sleeps at least 1 ms."""
    clock = FakeClock()
    clock.t = 1e9
    calls = []

    def sleep(s):
        calls.append(s)
        if len(calls) > 1000:
            raise AssertionError("token bucket stalled")
        clock.sleep(s)
    b = cl.TokenBucket(3, clock=clock, sleep=sleep)
    b.tokens, b.last = 1.0 - 1e-12, clock.t
    b.acquire()
    b.tokens, b.last = 0.5, clock.t
    b.acquire()
    assert len(calls) < 10
