"""Clinched / eliminated proof and the playoff-odds display rule (D-262).

Pure: no database, no network, no `backend.server`.

- Hand-built leagues: clinched; not clinched only because of a possible tie
  in standing points; eliminated; not eliminated (a tie is still possible).
- The operator's shape: 12 teams, 6 spots, two 8-1 teams with five weeks left
  are NOT clinched.
- Agreement with brute force over every outcome (each game a win, loss or
  tie) on random 4- and 6-team league states.
- Conservative returns: median leagues, divisions, partial or missing
  schedule, unreconciled records, too many rival sets, garbage input.
- Season over: the final standings decide, an exact tie is not proven.
- `attach`: every team gets both keys; on failure the result is unchanged.
- `odds_text` boundaries at one decimal and at whole percents.
"""
from __future__ import annotations

from itertools import product
import random

import pytest

from backend.league_projections import clinch


def league(records, schedule, spots, *, completed=None, median=False, **extra):
    """records: {rid: (w, l, t)}; schedule: list of weeks, each a list of pairs."""
    done = completed if completed is not None else sum(next(iter(records.values())))
    return {"teams": [{"roster_id": r, "wins": w, "losses": l, "ties": t,
                       "points_for": "100", "points_against": "100"} for r, (w, l, t) in records.items()],
            "weeks": [{"week": done + 1 + i, "games": [list(g) for g in week]} for i, week in enumerate(schedule)],
            "playoff_spots": spots, "completed_weeks": done,
            "league_format": {"median_game": median, "games_per_week": 2 if median else 1}, **extra}


def flags(snapshot):
    proof = clinch.prove(snapshot)
    return proof["status"], proof["teams"]


def brute(snapshot):
    """Every outcome of every remaining game: clinched iff in every outcome
    fewer than `spots` others finish level or above; eliminated iff in every
    outcome at least `spots` others finish strictly above."""
    pts = {t["roster_id"]: 2 * t["wins"] + t["ties"] for t in snapshot["teams"]}
    games = [tuple(g) for w in snapshot["weeks"] for g in w["games"]]
    spots = snapshot["playoff_spots"]
    clinched = {r: True for r in pts}
    eliminated = {r: True for r in pts}
    for outcome in product((2, 1, 0), repeat=len(games)):
        final = dict(pts)
        for (a, b), share in zip(games, outcome):
            final[a] += share
            final[b] += 2 - share
        for x in pts:
            if sum(1 for t in pts if t != x and final[t] >= final[x]) >= spots:
                clinched[x] = False
            if sum(1 for t in pts if t != x and final[t] > final[x]) < spots:
                eliminated[x] = False
    return {r: (clinched[r], eliminated[r]) for r in pts}


# ── Hand-built leagues ───────────────────────────────────────────────────
def test_clinched_with_one_week_left():
    # 4 teams, 2 spots, one week left: A 5-0 v D, B 2-3 v C. A loses -> 5-1;
    # B and C max 3 wins. D wins out -> 2-4, below A and the B/C winner.
    s = league({1: (5, 0, 0), 2: (2, 3, 0), 3: (2, 3, 0), 4: (1, 4, 0)}, [[(1, 4), (2, 3)]], 2)
    status, teams = flags(s)
    assert status == "exact"
    assert teams[1] == (True, False)
    assert teams[4] == (False, True)
    assert teams == brute(s)


def test_not_clinched_only_because_of_a_possible_tie():
    # 4 teams, 1 spot. A 4-1 v C, B 3-2 v D. A loses -> 4-2; B wins -> 4-2:
    # level on wins, the tiebreak is future points. Not clinched.
    s = league({1: (4, 1, 0), 2: (3, 2, 0), 3: (2, 3, 0), 4: (1, 4, 0)}, [[(1, 3), (2, 4)]], 1)
    status, teams = flags(s)
    assert status == "exact" and teams[1] == (False, False)
    # One more win for A and it is clinched.
    s2 = league({1: (5, 0, 0), 2: (3, 2, 0), 3: (1, 4, 0), 4: (1, 4, 0)}, [[(1, 3), (2, 4)]], 1)
    assert flags(s2)[1][1] == (True, False)
    assert flags(s)[1] == brute(s) and flags(s2)[1] == brute(s2)


def test_eliminated_and_not_eliminated_by_a_possible_tie():
    # 2 spots. D 1-4 wins out -> 2-4; A, B, C already 3-2: above forever.
    s = league({1: (3, 2, 0), 2: (3, 2, 0), 3: (3, 2, 0), 4: (1, 4, 0)}, [[(1, 2), (3, 4)]], 2)
    assert flags(s)[1][4] == (False, True)
    # D 2-3 wins out -> 3-3; A v B gives one 4 wins and the other 3 (level
    # with D): only one strictly above. Alive.
    s2 = league({1: (3, 2, 0), 2: (3, 2, 0), 3: (2, 3, 0), 4: (2, 3, 0)}, [[(1, 2), (3, 4)]], 2)
    assert flags(s2)[1][4] == (False, False)
    assert flags(s)[1] == brute(s) and flags(s2)[1] == brute(s2)


def test_in_game_ties_count_half_a_win_exactly():
    # A 3-1-1 (7 pts) v D; B 3-2 (6 pts) v C. A loses -> 7; B can reach 8.
    s = league({1: (3, 1, 1), 2: (3, 2, 0), 3: (2, 2, 1), 4: (1, 4, 0)}, [[(1, 4), (2, 3)]], 1)
    status, teams = flags(s)
    assert status == "exact" and teams == brute(s)


def operator_league():
    """12 teams, 6 spots, 9 weeks played, 5 left; two teams at 8-1."""
    records = {1: (8, 1, 0), 2: (8, 1, 0), 3: (6, 3, 0), 4: (6, 3, 0), 5: (5, 4, 0), 6: (5, 4, 0),
               7: (4, 5, 0), 8: (4, 5, 0), 9: (3, 6, 0), 10: (2, 7, 0), 11: (2, 7, 0), 12: (1, 8, 0)}
    rot = list(range(2, 13))
    schedule = []
    for w in range(5):
        order = [1] + rot[w:] + rot[:w]
        schedule.append([(order[i], order[11 - i]) for i in range(6)])
    return league(records, schedule, 6)


def test_operator_case_two_8_1_teams_five_weeks_left_are_not_clinched():
    status, teams = flags(operator_league())
    assert status == "exact"
    assert teams[1] == (False, False) and teams[2] == (False, False)
    assert not any(c for c, _ in teams.values())


def test_operator_case_clinches_once_it_is_settled():
    # Same league, one week left, the two leaders at 12-1 and the 7th team
    # at 7-6 at best: 12-2 cannot be matched by six others.
    records = {1: (12, 1, 0), 2: (12, 1, 0), 3: (10, 3, 0), 4: (9, 4, 0), 5: (8, 5, 0), 6: (7, 6, 0),
               7: (6, 7, 0), 8: (5, 8, 0), 9: (4, 9, 0), 10: (2, 11, 0), 11: (2, 11, 0), 12: (1, 12, 0)}
    s = league(records, [[(1, 12), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)]], 6)
    status, teams = flags(s)
    assert status == "exact" and teams[1] == (True, False) and teams[2] == (True, False)
    assert teams[12] == (False, True)


# ── Brute force agreement ───────────────────────────────────────────────
def random_league(rng, n, weeks_left, done):
    ids = list(range(1, n + 1))
    records = {r: [0, 0, 0] for r in ids}
    for _ in range(done):
        rng.shuffle(ids)
        for i in range(0, n, 2):
            a, b = ids[i], ids[i + 1]
            o = rng.choice((0, 0, 0, 1, 1, 1, 2))
            if o == 2:
                records[a][2] += 1
                records[b][2] += 1
            else:
                records[a][o] += 1
                records[b][1 - o] += 1
    schedule = []
    for _ in range(weeks_left):
        rng.shuffle(ids)
        schedule.append([(ids[i], ids[i + 1]) for i in range(0, n, 2)])
    return league({r: tuple(v) for r, v in records.items()}, schedule, rng.randint(1, n - 1), completed=done)


@pytest.mark.parametrize("n,weeks_left,cases", [(4, 1, 150), (4, 2, 150), (4, 3, 60), (6, 1, 150), (6, 2, 25), (6, 3, 6)])
def test_agrees_with_brute_force(n, weeks_left, cases):
    rng = random.Random(1000 * n + weeks_left)
    proven = 0
    for _ in range(cases):
        s = random_league(rng, n, weeks_left, rng.randint(1, 6))
        status, teams = flags(s)
        assert status == "exact"
        assert teams == brute(s), s
        proven += sum(c or e for c, e in teams.values())
    assert proven > 0  # the comparison is not all-False on both sides


# ── Conservative returns ────────────────────────────────────────────────
SETTLED = ({1: (5, 0, 0), 2: (2, 3, 0), 3: (2, 3, 0), 4: (1, 4, 0)}, [[(1, 4), (2, 3)]], 2)


@pytest.mark.parametrize("mutate,reason", [
    (lambda s: s.update(league_format={"median_game": True, "games_per_week": 2}), "median_game"),
    (lambda s: s.update(divisions=2), "divisions"),
    (lambda s: s.pop("weeks"), "missing_schedule"),
    (lambda s: s["weeks"][0].update(games=[[1, 4]]), "partial_schedule"),
    (lambda s: s["weeks"][0].update(week=9), "partial_schedule"),
    (lambda s: s["teams"][0].update(wins=6), "unreconciled_records"),
    (lambda s: s.update(playoff_spots=0), "invalid_league"),
    (lambda s: s["teams"][0].update(wins="5"), "unreconciled_records"),
])
def test_conservative_inputs_prove_nothing(mutate, reason):
    s = league(*SETTLED)
    assert flags(s)[1][1] == (True, False)  # proven before the change
    mutate(s)
    proof = clinch.prove(s)
    assert proof == {"status": "not_proven", "reason": reason, "teams": {}}


def test_garbage_never_raises():
    for bad in (None, [], "x", {"teams": "x"}, {"teams": [{"roster_id": 1}], "weeks": None}):
        assert clinch.prove(bad)["teams"] == {}


def test_too_many_rival_sets_is_not_proven(monkeypatch):
    monkeypatch.setattr(clinch, "MAX_SETS", 3)
    proof = clinch.prove(operator_league())
    assert proof["status"] == "not_proven" and proof["reason"] == "too_many_rival_sets"


def test_season_over_uses_final_standings():
    s = league({1: (5, 1, 0), 2: (4, 2, 0), 3: (2, 4, 0), 4: (1, 5, 0)}, [], 2)
    pf = {1: "700.5", 2: "650", 3: "640", 4: "600"}
    for t in s["teams"]:
        t["points_for"] = pf[t["roster_id"]]
    assert clinch.prove(s)["reason"] == "missing_precision"
    proof = clinch.prove(s, decimals=2)
    assert proof["status"] == "exact"
    assert proof["teams"] == {1: (True, False), 2: (True, False), 3: (False, True), 4: (False, True)}
    # Teams 2 and 3 exactly level on points, PF and PA for the last spot:
    # the lottery decides, so neither is proven either way.
    level = league({1: (4, 2, 0), 2: (3, 3, 0), 3: (3, 3, 0), 4: (2, 4, 0)}, [], 2)
    for t, value in zip(level["teams"], ("700", "650", "650", "600")):
        t["points_for"] = value
    assert clinch.prove(level, decimals=2)["teams"] == {1: (True, False), 2: (False, False),
                                                        3: (False, False), 4: (False, True)}
    # PF differing past the precision the simulation rounds to is still level.
    level["teams"][2]["points_for"] = "650.001"
    assert clinch.prove(level, decimals=2)["teams"][3] == (False, False)
    assert clinch.prove(level, decimals=3)["teams"][3] == (True, False)


# ── attach ──────────────────────────────────────────────────────────────
def test_attach_adds_both_keys_to_every_team():
    s = league(*SETTLED)
    result = {"config": {"score_decimals": 2}, "teams": [{"roster_id": r} for r in (1, 2, 3, 4)]}
    out = clinch.attach(result, s)
    assert out["playoff_proof"] == {"status": "exact", "reason": None}
    assert [(t["playoff_clinched"], t["playoff_eliminated"]) for t in out["teams"]] == [
        (True, False), (False, False), (False, False), (False, True)]
    assert "playoff_clinched" not in result["teams"][0]  # input not mutated
    median = clinch.attach(result, league(*SETTLED, median=True))
    assert median["playoff_proof"] == {"status": "not_proven", "reason": "median_game"}
    assert not any(t["playoff_clinched"] or t["playoff_eliminated"] for t in median["teams"])


def test_attach_failure_returns_the_result_unchanged():
    result = {"teams": "not a list of teams"}
    assert clinch.attach(result, league(*SETTLED)) is result


# ── Display rule ────────────────────────────────────────────────────────
@pytest.mark.parametrize("percent,clinched,eliminated,one,whole", [
    (99.94, False, False, "99.9%", ">99%"),
    (99.95, False, False, ">99.9%", ">99%"),
    (99.99, False, False, ">99.9%", ">99%"),
    (100, False, False, ">99.9%", ">99%"),
    (100, True, False, "100.0%", "100%"),
    (50, False, False, "50.0%", "50%"),
    (0.05, False, False, "0.1%", "<1%"),
    (0.04, False, False, "<0.1%", "<1%"),
    (0, False, False, "<0.1%", "<1%"),
    (0, False, True, "0.0%", "0%"),
    (0.04, False, True, "0.0%", "0%"),
])
def test_odds_text_boundaries(percent, clinched, eliminated, one, whole):
    p = percent / 100
    assert clinch.odds_text(p, clinched=clinched, eliminated=eliminated) == one
    assert clinch.odds_text(p, clinched=clinched, eliminated=eliminated, decimals=0) == whole


# ── Server-made strings and payloads ────────────────────────────────────
def test_recommendation_sentence_and_payloads_follow_the_proof():
    """The one server-composed sentence with a playoff chance, the outlook
    block and Team Review's `playoff_chance` carry the proof. Sabotage:
    format the explanation with `{probability * 100:.1f}%` again."""
    from backend.league_projections import recommendation
    from backend.league_projections.core import VERSION

    def result(**team):
        return {"model_version": VERSION, "coverage": {"estimate_status": "complete"}, "viewer_roster_id": 1,
                "captured_at": "2026-11-10T15:00:00+00:00",
                "teams": [{"roster_id": 1, "playoff_probability": 1.0, **team}]}
    cuts = (.2, .7)
    unproven = recommendation.build("current", result(), None, cuts)
    assert "makes the playoffs in >99.9% of the simulated seasons" in unproven["explanation"]
    assert (unproven["playoff_clinched"], unproven["playoff_eliminated"]) == (False, False)
    proven = recommendation.build("current", result(playoff_clinched=True), None, cuts)
    assert "makes the playoffs in 100.0% of the simulated seasons" in proven["explanation"]
    assert proven["playoff_clinched"] is True and proven["playoff_probability"] == 1.0
    view = {"state": "current", "next_attempt_not_before": "2026-11-15T12:00:00+00:00",
            "run": {"status": "complete", "result_json": __import__("json").dumps(result(playoff_clinched=True))}}
    from datetime import datetime, timezone
    chance = recommendation.saved_chance(view, datetime(2026, 11, 12, tzinfo=timezone.utc))
    assert chance["playoff_clinched"] is True and chance["playoff_eliminated"] is False
