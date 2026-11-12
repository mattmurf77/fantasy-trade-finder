"""Playoff forecasts for Sleeper league-median leagues (`league_average_match`).

In a median league every week books two results per team: head-to-head, and
against the median of every team's score that week. A score above the median
wins, below it loses, exactly equal ties (the rule was verified against a real
12-team league's official records; the tie case is not observed there). Points
against stay head-to-head. Standings, seeding, byes and the draft order are
unchanged functions of the combined record.

What this pins:
  * the rule itself on even and odd team counts, a cutoff tie, and weeks where
    the head-to-head and median results differ;
  * capture admits a median league and books both results for every completed
    week, so the current record equals the official one; divisions, best ball
    and manual brackets are still refused;
  * simulate adds exactly one median result per team per simulated week, only
    for a median league, and seeds on the combined record;
  * a team that misses the playoffs head-to-head but makes it on median wins;
  * non-median results are byte-identical to the code before this change
    (golden digests produced by origin/main at 455d1265);
  * stored snapshots (scenarios, the worker) and the outlook suggestion.

All data here is invented. Nothing is copied from a real league.
"""
from copy import deepcopy
import json
import math
from types import SimpleNamespace

import pytest
from flask import Flask

from backend import database as db
from backend.league_projections import api, batch, recommendation, service, store
from backend.league_projections.core import VERSION, Unavailable, digest, median_outcomes
from backend.league_projections.provider import API, capture
from backend.league_projections.simulation import simulate
from backend.tests.test_league_projection_provider import run, world
from backend.tests.test_league_projection_reseeding_review import eight_team_world
from backend.tests.test_league_projection_simulation import config as base_config, snapshot as h2h_snapshot
from backend.tests.test_outlook_calibration_persistence import engine  # noqa: F401

MEDIAN = {"median_game": True, "games_per_week": 2}
H2H = {"median_game": False, "games_per_week": 1}


def config(**overrides):
    return {**base_config(), **overrides}


# ── The rule ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("scores,expected", [
    # Even count: the top half wins, the bottom half loses.
    ([100, 90, 80, 70], [0, 0, 1, 1]),
    ([70, 100, 80, 90], [1, 0, 1, 0]),
    # Order-independent: the result follows the score, not the position.
    ([1.5, 1.25, 9.75, 3.0, 0.5, 2.0], [1, 1, 0, 0, 1, 0]),
    # Odd count: the middle score is the median and ties it.
    ([10, 20, 30], [1, 2, 0]),
    ([5, 50, 40, 10, 30], [1, 0, 0, 1, 2]),
    # A tie at the cutoff: both middle scores equal the median and tie.
    ([100, 80, 80, 60], [0, 2, 2, 1]),
    # Every score equal: every team ties the median.
    ([42, 42, 42, 42], [2, 2, 2, 2]),
])
def test_median_rule_on_even_and_odd_counts_and_cutoff_ties(scores, expected):
    """Above the median wins, below loses, equal ties (sabotages: the bottom
    half wins; a tie at the cutoff counted as a win)."""
    assert median_outcomes(scores) == expected


def test_median_is_taken_over_every_team_not_one_game():
    """The cutoff is the league's median, not the matchup's (sabotage: the
    median over the wrong set, e.g. one game's two scores, or all but self)."""
    # Team 0 beats its opponent 51-50 but both sit in the bottom half.
    scores = [51, 50, 99, 98]
    assert median_outcomes(scores) == [1, 1, 0, 0]
    # Excluding a team's own score would move the cutoff and flip team 1.
    assert median_outcomes([60, 59, 10, 9]) == [0, 0, 1, 1]


def test_rule_is_exact_for_decimal_scores():
    from decimal import Decimal
    scores = [Decimal("100.01"), Decimal("100.00"), Decimal("99.99"), Decimal("99.98")]
    assert median_outcomes(scores) == [0, 0, 1, 1]


# ── Capture ─────────────────────────────────────────────────────────────────

# Four teams, two completed weeks, one future week (3), playoffs from week 4.
# Week 1: 1-2 (100-90), 3-4 (80-70). Median between 90 and 80: 1, 2 win.
#   Team 2 loses head-to-head but wins the median; team 3 the reverse.
# Week 2: 1-3 (60-50), 2-4 (110-40). Median between 60 and 50: 1, 2 win.
WEEK_POINTS = {1: {1: 100, 2: 90, 3: 80, 4: 70}, 2: {1: 60, 3: 50, 2: 110, 4: 40}}
PAIRS = {1: [(1, 2), (3, 4)], 2: [(1, 3), (2, 4)], 3: [(1, 4), (2, 3)]}
# Hand-computed: head-to-head + median.
#   1: H2H 2-0, median 2-0 -> 4-0     2: H2H 1-1, median 2-0 -> 3-1
#   3: H2H 1-1, median 0-2 -> 1-3     4: H2H 0-2, median 0-2 -> 0-4
OFFICIAL = {1: (4, 0), 2: (3, 1), 3: (1, 3), 4: (0, 4)}
PF = {1: 160, 2: 200, 3: 130, 4: 110}
PA = {1: 140, 2: 140, 3: 130, 4: 190}   # head-to-head opponents only


def median_world(flag=1):
    source, _ = world()
    league = source[f"{API}/league/123"]
    league["total_rosters"] = 4
    league["settings"].update(playoff_week_start=4, playoff_teams=2, league_average_match=flag)
    source[f"{API}/state/nfl"]["week"] = 3
    source[f"{API}/league/123/rosters"] = [
        {"roster_id": i, "league_id": "123", "owner_id": "me" if i == 1 else f"owner{i}", "players": [f"p{i}"],
         "reserve": [], "taxi": [],
         "settings": {"wins": OFFICIAL[i][0], "losses": OFFICIAL[i][1], "ties": 0, "fpts": PF[i],
                      "fpts_against": PA[i], "ppts": PF[i]}} for i in range(1, 5)]
    for w, points in WEEK_POINTS.items():
        source[f"{API}/league/123/matchups/{w}"] = [
            {"roster_id": i, "matchup_id": m, "points": points[i], "starters": [f"p{i}"], "starters_points": [points[i]]}
            for m, pair in enumerate(PAIRS[w], 1) for i in pair]
    source[f"{API}/league/123/matchups/3"] = [{"roster_id": i, "matchup_id": m} for m, pair in enumerate(PAIRS[3], 1) for i in pair]
    source[f"{API}/players/nfl"] = {f"p{i}": {"fantasy_positions": ["WR"]} for i in range(1, 5)}

    class Feed:
        def weeks(self, season, weeks, player_ids):
            return {"source": "synthetic", "captured_at": "2026-11-01T00:00:00+00:00",
                    "weeks": {"3": {f"p{i}": {"kickoff_at": "2026-11-08T18:00:00+00:00", "availability": 1,
                                              "stats": {"rec": 10 * i}, "supported_keys": ["rec"]} for i in range(1, 5)}}}
    return source, Feed()


def test_capture_admits_a_median_league_and_books_both_results_per_completed_week():
    """Each completed week adds a median result, so the current record is the
    official one (sabotage: skip the median results for completed weeks, and
    capture refuses the league as unreconciled)."""
    source, feed = median_world()
    snap = run(source, feed)
    assert snap["league_format"] == MEDIAN
    records = {t["roster_id"]: (t["wins"], t["losses"], t["ties"]) for t in snap["teams"]}
    assert records == {rid: (w, l, 0) for rid, (w, l) in OFFICIAL.items()}
    for team in snap["teams"]:
        assert sum((team["wins"], team["losses"], team["ties"])) == 2 * snap["completed_weeks"]
        # Points for, points against and Max PF are unchanged by the median game.
        assert team["points_for"] == str(PF[team["roster_id"]])
        assert team["points_against"] == str(PA[team["roster_id"]])
    assert any("league median" in w for w in snap["warnings"])
    result = simulate(snap, config())
    assert [t["current_record"] for t in result["teams"]] == [[w, l, 0] for _, (w, l) in sorted(OFFICIAL.items())]


def test_capture_refuses_a_median_league_whose_official_record_lacks_the_median_game():
    """The reconciliation still bites: official records that are head-to-head
    only do not match a median league's weekly scores."""
    source, feed = median_world()
    for roster in source[f"{API}/league/123/rosters"]:
        h2h = {1: (2, 0), 2: (1, 1), 3: (1, 1), 4: (0, 2)}[roster["roster_id"]]
        roster["settings"].update(wins=h2h[0], losses=h2h[1])
    with pytest.raises(Unavailable) as exc:
        run(source, feed)
    assert exc.value.reason == "standings_include_unfinalized_or_adjusted_points"


def test_head_to_head_league_is_unchanged_and_marked():
    source, feed = world()
    assert run(source, feed)["league_format"] == H2H


@pytest.mark.parametrize("value", [2, -1, "1", 1.0, True, [], {}])
def test_unknown_median_setting_is_refused(value):
    source, feed = median_world()
    source[f"{API}/league/123"]["settings"]["league_average_match"] = value
    with pytest.raises(Unavailable) as exc:
        run(source, feed)
    assert exc.value.reason == "unsupported_median_setting"


@pytest.mark.parametrize("setting", ["divisions", "best_ball", "bracket_overrides_id"])
def test_divisions_best_ball_and_manual_brackets_are_still_refused(setting):
    source, feed = median_world()
    league = source[f"{API}/league/123"]
    if setting == "bracket_overrides_id":
        league[setting] = "synthetic-override"
    else:
        league["settings"][setting] = 1
    with pytest.raises(Unavailable) as exc:
        run(source, feed)
    assert exc.value.reason == "unsupported_divisions_bestball_or_manual_seeding"


# ── Simulate ────────────────────────────────────────────────────────────────

def median_snapshot(fmt=MEDIAN):
    """Two completed weeks (records above), two future weeks with fixed
    projections. Week 3: 1-4 (50-80), 2-3 (100-90); median between 90 and 80.
    Week 4: 1-2 (70-60), 3-4 (65-100); median between 70 and 65."""
    projections = {3: {1: 50, 2: 100, 3: 90, 4: 80}, 4: {1: 70, 2: 60, 3: 65, 4: 100}}
    games = {3: [[1, 4], [2, 3]], 4: [[1, 2], [3, 4]]}
    base = OFFICIAL if fmt["median_game"] else {1: (2, 0), 2: (1, 1), 3: (1, 1), 4: (0, 2)}
    history = {i: [str(WEEK_POINTS[1][i]), str(WEEK_POINTS[2][i])] for i in range(1, 5)}
    snap = {"playoff_spots": 2, "playoff_byes": 1, "completed_weeks": 2, "source": "synthetic",
            "captured_at": "2026-11-01T00:00:00+00:00", "viewer_roster_id": 2,
            "coverage": {"estimate_status": "complete"},
            "teams": [{"roster_id": i, "name": f"Team{i}", "wins": base[i][0], "losses": base[i][1], "ties": 0,
                       "points_for": str(PF[i]), "points_against": str(PA[i]), "maxpf": str(PF[i]),
                       "actual_history": history[i], "maxpf_history": []} for i in range(1, 5)],
            "weeks": [{"week": w, "games": games[w],
                       "teams": {str(i): {"actual": {"points": str(projections[w][i])}, "maxpf": {"points": str(projections[w][i])},
                                          "maxpf_dominates_actual": True} for i in range(1, 5)}} for w in (3, 4)],
            "pick_ownership": []}
    if fmt is not None:
        snap["league_format"] = fmt
    return snap


def test_zero_sd_record_is_exactly_head_to_head_plus_median_every_remaining_week():
    """Hand-computed finals. Week 3: 1 L/L, 2 W/W, 3 L/W, 4 W/L. Week 4: 1 W/W,
    2 L/L, 3 L/L, 4 W/W (sabotages: median result not added in simulated
    weeks; added twice)."""
    result = simulate(median_snapshot(), config(score_sd=0))
    assert result["league_format"] == MEDIAN
    finals = {t["roster_id"]: t["final_record_distribution"] for t in result["teams"]}
    assert finals == {1: [{"record": [6, 2, 0], "probability": 1.0}], 2: [{"record": [5, 3, 0], "probability": 1.0}],
                      3: [{"record": [2, 6, 0], "probability": 1.0}], 4: [{"record": [3, 5, 0], "probability": 1.0}]}
    weeks = {t["roster_id"]: [(w["win_probability"], w["median_win_probability"], w["median_loss_probability"]) for w in t["weeks"]]
             for t in result["teams"]}
    assert weeks == {1: [(0, 0, 1), (1, 1, 0)], 2: [(1, 1, 0), (0, 0, 1)], 3: [(0, 1, 0), (0, 0, 1)], 4: [(1, 0, 1), (1, 1, 0)]}


def test_head_to_head_league_gets_no_median_result():
    """Sabotage: the median result added for a non-median league."""
    result = simulate(median_snapshot(H2H), config(score_sd=0))
    finals = {t["roster_id"]: t["final_record_distribution"][0]["record"] for t in result["teams"]}
    # H2H only: week 3 4 beats 1, 2 beats 3; week 4 1 beats 2, 4 beats 3.
    assert finals == {1: [3, 1, 0], 2: [2, 2, 0], 3: [1, 3, 0], 4: [2, 2, 0]}
    assert result["league_format"] == H2H
    assert not any("median_win_probability" in w for t in result["teams"] for w in t["weeks"])


def test_noisy_median_simulation_conserves_games_and_playoff_spots():
    """With noise and a fixed seed: every world gives each team two results a
    week, league-wide median wins equal median losses each week (ties are
    shared symmetrically), and playoff chances sum to the playoff spots."""
    result = simulate(median_snapshot(), config(score_sd=25, iterations=2000))
    teams = result["teams"]
    for team in teams:
        assert all(sum(r["record"]) == 2 * 4 for r in team["final_record_distribution"])
        assert math.isclose(sum(team["expected_record"]), 8)
        for w in team["weeks"]:
            assert math.isclose(w["median_win_probability"] + w["median_loss_probability"] + w["median_tie_probability"], 1)
    for k in range(2):
        wins = sum(t["weeks"][k]["median_win_probability"] for t in teams)
        losses = sum(t["weeks"][k]["median_loss_probability"] for t in teams)
        assert math.isclose(wins, losses) and math.isclose(wins + sum(t["weeks"][k]["median_tie_probability"] for t in teams) / 2, 2)
    assert math.isclose(sum(t["playoff_probability"] for t in teams), 2)
    assert math.isclose(sum(t["bye_probability"] for t in teams), 1)
    # Same seed, same snapshot, same result.
    assert result == simulate(median_snapshot(), config(score_sd=25, iterations=2000))


def test_median_wins_seed_a_team_that_misses_on_head_to_head_alone():
    """The point of the feature. Team 2 scores 99 every week but always meets
    team 1 (100); team 3 scores 10 and always beats team 4 (9). Head-to-head:
    1 and 3 are 3-0, team 2 is 0-3 and misses. With the median game team 2
    wins three median games, ties team 3 at 3-3 and takes the second spot on
    points for. Team 4 is 0-6."""
    def snap(fmt):
        return {"playoff_spots": 2, "playoff_byes": 0, "completed_weeks": 0, "source": "synthetic",
                "captured_at": "2026-11-01T00:00:00+00:00", "league_format": fmt, "pick_ownership": [],
                "teams": [{"roster_id": i, "name": f"Team{i}", "wins": 0, "losses": 0, "ties": 0, "points_for": "0",
                           "points_against": "0", "maxpf": "0", "actual_history": [], "maxpf_history": []} for i in range(1, 5)],
                "weeks": [{"week": w, "games": [[1, 2], [3, 4]],
                           "teams": {str(i): {"actual": {"points": str(p)}, "maxpf": {"points": str(p)}, "maxpf_dominates_actual": True}
                                     for i, p in ((1, 100), (2, 99), (3, 10), (4, 9))}} for w in (1, 2, 3)]}
    head_to_head = {t["roster_id"]: t["playoff_probability"] for t in simulate(snap(H2H), config(score_sd=0))["teams"]}
    median = {t["roster_id"]: (t["playoff_probability"], t["modal_record"]) for t in simulate(snap(MEDIAN), config(score_sd=0))["teams"]}
    assert head_to_head == {1: 1, 2: 0, 3: 1, 4: 0}
    assert median == {1: (1, [6, 0, 0]), 2: (1, [3, 3, 0]), 3: (0, [3, 3, 0]), 4: (0, [0, 6, 0])}


def test_median_record_scale_is_checked_against_the_snapshot_format():
    """A median snapshot whose records cover one game a week is refused, and
    a head-to-head snapshot with two-a-week records is refused."""
    bad = median_snapshot()
    bad["teams"] = median_snapshot(H2H)["teams"]
    with pytest.raises(Unavailable) as exc:
        simulate(bad, config())
    assert exc.value.reason == "unreconciled_records"
    bad = median_snapshot(H2H)
    bad["teams"] = median_snapshot()["teams"]
    with pytest.raises(Unavailable) as exc:
        simulate(bad, config())
    assert exc.value.reason == "unreconciled_records"


# ── Non-median: byte-identical ─────────────────────────────────────────────

# sha256 of the canonical JSON, produced by origin/main (455d1265, before the
# median change) with the `league_format` marker absent. Regenerate only for a
# deliberate model change (and bump core.VERSION then).
GOLDEN = {
    "sim_fixture": "8fb28464c926eeb8fac5189a0a897e57ec571970be00c00028e2ec5c5dfcef85",
    "two_team_capture": "dc773d63c7b80fdf0a152d261b48ced79dba1b89fcdda2a04a5e3d3f2170f502",
    "two_team_result": "c4539cdd17a313c492562eca3f7f0594901264debfdc8df448e836783b9e8327",
    "eight_team_capture": "4b6f94fcb3877e6446609ce9b3c22c91c41bbfc1972c9a956ab2163b56e3d8ea",
    "eight_team_result": "895c45d08ff1803de40adfefa663706fe5ba49132eb1cdeff2e3f311c97c55a5",
}


def _without_marker(value):
    value = dict(value)
    assert value.pop("league_format") == H2H
    return value


def test_non_median_snapshot_and_result_are_byte_identical_to_before():
    """Same seed, same snapshot: the result equals the pre-change result apart
    from the new `league_format` marker, so core.VERSION is not bumped."""
    assert digest(_without_marker(simulate(h2h_snapshot(), config()))) == GOLDEN["sim_fixture"]
    for name, (source, feed) in (("two_team", world()), ("eight_team", eight_team_world(0))):
        snap = _without_marker(run(source, feed))
        assert digest(snap) == GOLDEN[name + "_capture"]
        # A snapshot saved before the marker existed reads as head-to-head.
        assert digest(_without_marker(simulate(snap, config()))) == GOLDEN[name + "_result"]


def test_marker_on_a_head_to_head_snapshot_changes_only_the_snapshot_hash():
    source, feed = world()
    marked = run(source, feed)
    old = {k: v for k, v in marked.items() if k != "league_format"}
    a, b = simulate(marked, config()), simulate(old, config())
    assert a["snapshot_hash"] != b["snapshot_hash"]
    a.pop("snapshot_hash"), b.pop("snapshot_hash")
    assert a == b


# ── Scenarios, the worker, the outlook ──────────────────────────────────────

def _install(monkeypatch, sess):
    monkeypatch.setattr(api, "is_enabled", lambda key: True)
    monkeypatch.setattr(batch, "settings", lambda: {"policy_approved": True, "retention_days": 7, "model": config()})
    monkeypatch.setattr(service, "wake", lambda *a, **k: None)
    app = Flask("median-scenario")
    api.install(app, require_session=lambda: sess, read_denial=lambda s: None, write_denial=lambda s: None,
                league_user_id=lambda s: "account", fetch_json=lambda *a: pytest.fail("provider fetch"))
    return app.test_client()


def test_scenario_on_a_median_baseline_reruns_the_stored_snapshot_with_the_median_game(engine, monkeypatch):  # noqa: F811
    """The scenario POST freezes the median snapshot, and the worker's run of
    it (no provider call) counts two results a week."""
    cfg = config(score_sd=0)
    source = median_snapshot()
    baseline = "d" * 32
    saved = simulate(source, cfg)
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.insert().values(
            run_id=baseline, user_id="account", league_id="123", status="complete", created_at=store.utc_now(),
            updated_at=store.utc_now(), expires_at=store.utc_now(), request_hash="median", input_json="{}",
            snapshot_json=json.dumps(source), result_json=json.dumps(saved)))
    client = _install(monkeypatch, {"user_id": "account", "league": SimpleNamespace(league_id="123", platform="sleeper")})
    monkeypatch.setattr(batch, "settings", lambda: {"policy_approved": True, "retention_days": 7, "model": config(score_sd=0)})
    response = client.post("/api/leagues/123/projection-runs", json={"baseline_run_id": baseline, "config": {**cfg, "seed": 1}})
    assert response.status_code == 202, response.json
    queued = store.get(response.json["run_id"], "account", "123")
    assert json.loads(queued["snapshot_json"])["league_format"] == MEDIAN
    monkeypatch.setattr(service, "is_enabled", lambda key: True)
    monkeypatch.setattr(service.provider, "capture", lambda *a, **k: pytest.fail("scenario recaptured"))
    service._run(lambda *a: pytest.fail("provider fetch"))
    done = store.get(response.json["run_id"], "account", "123")
    assert done["status"] == "complete", (done["reason"], done["details_json"])
    result = json.loads(done["result_json"])
    assert result["league_format"] == MEDIAN
    assert [t["final_record_distribution"][0]["record"] for t in result["teams"]] == [[6, 2, 0], [5, 3, 0], [2, 6, 0], [3, 5, 0]]


def test_scenario_on_a_saved_result_without_the_marker_is_accepted(engine, monkeypatch):  # noqa: F811
    """Results and snapshots saved before this change carry no marker; the
    scenario POST and the worker still accept them as head-to-head."""
    cfg = config()
    old_snapshot = h2h_snapshot()
    old_result = simulate(old_snapshot, cfg)
    old_result.pop("league_format")
    baseline = "e" * 32
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.insert().values(
            run_id=baseline, user_id="account", league_id="123", status="complete", created_at=store.utc_now(),
            updated_at=store.utc_now(), expires_at=store.utc_now(), request_hash="old", input_json="{}",
            snapshot_json=json.dumps(old_snapshot), result_json=json.dumps(old_result)))
    client = _install(monkeypatch, {"user_id": "account", "league": SimpleNamespace(league_id="123", platform="sleeper")})
    response = client.post("/api/leagues/123/projection-runs", json={"baseline_run_id": baseline, "config": {**cfg, "seed": 2}})
    assert response.status_code == 202, response.json
    monkeypatch.setattr(service, "is_enabled", lambda key: True)
    service._run(lambda *a: pytest.fail("provider fetch"))
    result = json.loads(store.get(response.json["run_id"], "account", "123")["result_json"])
    assert result["league_format"] == H2H


def test_outlook_suggestion_reads_a_median_league_playoff_probability():
    """recommendation.build is unchanged: it reads the viewer's playoff
    probability, which for a median league already counts the median game."""
    result = simulate(median_snapshot(), config(score_sd=25, iterations=2000))
    team = next(t for t in result["teams"] if t["roster_id"] == 2)
    block = recommendation.build("current", result, "rebuilder", (.15, .75))
    assert block["status"] == "available"
    assert block["playoff_probability"] == team["playoff_probability"]
    assert block["recommended_outlook"] == recommendation.classify(team["playoff_probability"], (.15, .75))
    # The same snapshot read head-to-head gives the viewer a different chance:
    # the suggestion follows the median-aware number, not a head-to-head one.
    h2h = simulate({**median_snapshot(H2H)}, config(score_sd=25, iterations=2000))
    assert next(t for t in h2h["teams"] if t["roster_id"] == 2)["playoff_probability"] != team["playoff_probability"]
