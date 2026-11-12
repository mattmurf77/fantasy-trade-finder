"""Projected pick labels as an exact 1..N ranking (D-257, operator 2026-11-12:
"Pick labels: yes. Make them exact").

The slot a projected pick's label names ("2027 1.04 · projected", `proj_slot`)
is the ORIGINAL team's rank when the league's teams are ordered by expected
slot, ascending; equal expected slots (playoff locks) are broken by expected
win-equivalents, fewer first, then roster id. Pricing is untouched: the value
still reads the whole slot distribution. Scope:
docs/plans/league-projections/pick-slot-rank/scope.md.

Pinned here:
  * labels are a permutation of 1..N for 8/10/12/14-team forecasts;
  * ordering follows expected slot;
  * playoff locks order by expected wins (best team picks last), roster id last;
  * a traded pick shows the original owner's rank;
  * pick values are byte-identical to origin/main 53711036 for a fixture forecast;
  * no usable forecast / an uncovered pick → no label.
"""
import random
from datetime import datetime, timedelta, timezone

import pytest

import backend.pick_projection as pp
from backend.pick_values import priced_pool_value, projected_pick_slot

VERSION = "model-under-test"
NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
FMT = "1qb_ppr"


def _result(teams, *, playoff, season=2027, completed=9, future=5):
    """`teams` is {roster_id: (pick_probabilities, playoff_probability, expected_record|None)}."""
    rows = []
    for rid, (picks, made, record) in teams.items():
        row = {"roster_id": rid, "pick_probabilities": list(picks),
               "playoff_probability": made, "weeks": [{}] * future}
        if record is not None:
            row["expected_record"] = list(record)
        rows.append(row)
    return {"status": "complete", "model_version": VERSION, "completed_weeks": completed,
            "playoff_spots": playoff, "config": {"draft_season": season}, "teams": rows}


def _projection(result):
    summary = pp.compact(result, run_id="run-rank",
                         created_at=(NOW - timedelta(days=1)).isoformat())
    return pp.usable(summary, model_version=VERSION, now=NOW, weight=1.0, min_weeks=3,
                     max_age_days=8, max_round=1)


def _row(rid, season=2027, rnd=1, owner="someone"):
    return {"pick_id": f"L_{season}_{rnd}_{rid}", "season": season, "round": rnd,
            "original_roster_id": rid, "owner_user_id": owner, "pool_value": 2117.0}


def _simulated(n, playoff, seed, worlds=400, records=True):
    """A forecast built the way the simulation builds one (random order per
    world; the last `playoff` make it; the rest fill slots 1..n-playoff), with
    expected_record from each world's order position. Rows and columns sum to 1."""
    rng = random.Random(seed)
    strength = [rng.random() for _ in range(n)]
    picks = [[0] * (n - playoff) for _ in range(n)]
    made, wins = [0] * n, [0.0] * n
    for _ in range(worlds):
        order = sorted(range(n), key=lambda i: strength[i] + rng.gauss(0, 0.3))
        for pos, team in enumerate(order):
            wins[team] += pos
        for slot, team in enumerate(order[:n - playoff]):
            picks[team][slot] += 1
        for team in order[n - playoff:]:
            made[team] += 1
    return {t + 1: ([c / worlds for c in picks[t]], made[t] / worlds,
                    [wins[t] / worlds, n - 1 - wins[t] / worlds, 0.0] if records else None)
            for t in range(n)}


# ── a permutation of 1..N ────────────────────────────────────────────────────

@pytest.mark.parametrize("records", [True, False])
@pytest.mark.parametrize("n", [8, 10, 12, 14])
def test_labels_are_a_permutation_of_one_to_n(n, records):
    """Sabotage: the old rounded expected slot → duplicates and gaps."""
    proj = _projection(_result(_simulated(n, n // 2, 40 + n, records=records), playoff=n // 2))
    slots = [projected_pick_slot(_row(r), proj, FMT) for r in range(1, n + 1)]
    assert sorted(slots) == list(range(1, n + 1))


@pytest.mark.parametrize("n", [8, 10, 12, 14])
def test_ordering_follows_expected_slot(n):
    """A lower expected slot never shows a later label. Sabotage: sort
    descending → the worst team shows the last slot."""
    proj = _projection(_result(_simulated(n, n // 2, 70 + n), playoff=n // 2))
    expected = {r: pp.expected_slot(proj.dists[str(r)]) for r in range(1, n + 1)}
    shown = {r: projected_pick_slot(_row(r), proj, FMT) for r in range(1, n + 1)}
    for a in expected:
        for b in expected:
            if expected[a] < expected[b] - 1e-9:
                assert shown[a] < shown[b], (a, b, expected[a], expected[b])


# ── playoff locks: the stronger team picks later ────────────────────────────

def _locks(records):
    """12 teams, 6 spots: rosters 1-6 miss for certain (point mass on slot r),
    rosters 7-12 are playoff locks (identical rows, expected slot 9.5)."""
    teams = {r: ([1.0 if k == r - 1 else 0.0 for k in range(6)], 0.0, [12 - r, r, 0])
             for r in range(1, 7)}
    teams.update({r: ([0.0] * 6, 1.0, records.get(r)) for r in range(7, 13)})
    return _projection(_result(teams, playoff=6))


def test_playoff_locks_order_by_expected_wins_best_team_last():
    """Sabotage: drop the wins tie-break (roster id only) → 7 shows 1.07, not 1.12;
    reverse it → the best team picks first."""
    proj = _locks({7: [12, 2, 0], 8: [8, 6, 0], 9: [10, 4, 0],
                   10: [9, 5, 0], 11: [11, 3, 0], 12: [7, 6, 1]})
    assert {r: pp.expected_slot(proj.dists[str(r)]) for r in range(7, 13)} == \
        {r: pytest.approx(9.5) for r in range(7, 13)}
    shown = {r: projected_pick_slot(_row(r), proj, FMT) for r in range(1, 13)}
    assert [shown[r] for r in range(1, 7)] == [1, 2, 3, 4, 5, 6]
    # win-equivalents: 12 → 7.5, 8 → 8, 10 → 9, 9 → 10, 11 → 11, 7 → 12
    assert {r: shown[r] for r in range(7, 13)} == {12: 7, 8: 8, 10: 9, 9: 10, 11: 11, 7: 12}


def test_equal_wins_fall_back_to_roster_id():
    proj = _locks({r: [9, 5, 0] for r in range(7, 13)})
    assert [projected_pick_slot(_row(r), proj, FMT) for r in range(7, 13)] == [7, 8, 9, 10, 11, 12]


def test_strength_is_used_only_when_every_team_has_it():
    """One team without an expected_record → the whole run breaks ties by
    roster id, never a mix of the two tie-breaks."""
    proj = _locks({7: [12, 2, 0], 8: [8, 6, 0], 9: None,
                   10: [9, 5, 0], 11: [11, 3, 0], 12: [7, 6, 1]})
    assert [projected_pick_slot(_row(r), proj, FMT) for r in range(7, 13)] == [7, 8, 9, 10, 11, 12]


def test_numeric_roster_ids_sort_numerically():
    assert pp.slot_ranks({"10": (0.5, 0.5), "9": (0.5, 0.5)}) == {"9": 1, "10": 2}


# ── traded picks ─────────────────────────────────────────────────────────────

def test_traded_pick_shows_the_original_owners_rank():
    """Sabotage: rank the holder → the pick says where its new owner picks."""
    proj = _locks({7: [12, 2, 0], 8: [8, 6, 0], 9: [10, 4, 0],
                   10: [9, 5, 0], 11: [11, 3, 0], 12: [7, 6, 1]})
    held_by_7 = _row(2, owner="holder-of-roster-7")
    assert projected_pick_slot(held_by_7, proj, FMT) == 2
    assert projected_pick_slot({**_row(7), "owner_user_id": "roster-2-owner"}, proj, FMT) == 12


# ── values are untouched ─────────────────────────────────────────────────────

# priced_pool_value for each roster's 2027 1st under `_simulated(12, 6, 99)`,
# captured on origin/main 53711036 (before D-257) against the conftest DP
# fixture. The label change must not move a single one.
MAIN_VALUES = {
    1: 1845.9, 2: 2498.7, 3: 2721.3, 4: 2417.6, 5: 1170.0, 6: 2370.2,
    7: 2056.7, 8: 1239.8, 9: 1506.9, 10: 1051.0, 11: 1679.8, 12: 1756.2,
}
# The labels main showed for the same forecast (rounded expected slot): three
# 1.05s, three 1.09s, two 1.07s, no 1.01 — the defect D-257 removes.
MAIN_LABELS = {1: 6, 2: 5, 3: 4, 4: 5, 5: 9, 6: 5, 7: 6, 8: 9, 9: 8, 10: 9, 11: 7, 12: 7}


def test_values_are_byte_identical_to_before_the_rank():
    """Sabotage: price off the label slot (a point mass on the rank) → values move."""
    proj = _projection(_result(_simulated(12, 6, 99), playoff=6))
    values = {r: priced_pool_value(_row(r), scoring_format=FMT, projection=proj)
              for r in range(1, 13)}
    assert values == MAIN_VALUES
    shown = [projected_pick_slot(_row(r), proj, FMT) for r in range(1, 13)]
    assert sorted(shown) == list(range(1, 13))
    assert sorted(MAIN_LABELS.values()) != list(range(1, 13))


def test_values_never_read_the_label_slots():
    """Scrambling the rank map leaves every price unchanged."""
    import dataclasses
    proj = _projection(_result(_simulated(12, 6, 99), playoff=6))
    scrambled = dataclasses.replace(proj, slots={str(r): 13 - r for r in range(1, 13)})
    for r in range(1, 13):
        assert priced_pool_value(_row(r), scoring_format=FMT, projection=scrambled) == \
            priced_pool_value(_row(r), scoring_format=FMT, projection=proj)


# ── no forecast, no label ───────────────────────────────────────────────────

def test_uncovered_league_or_pick_has_no_label():
    """Unchanged behaviour: no usable forecast (None, a malformed run, a gate
    failing) or a pick the forecast does not cover → no projected slot."""
    proj = _projection(_result(_simulated(12, 6, 5), playoff=6))
    assert projected_pick_slot(_row(1), None, FMT) is None
    assert pp.compact({"status": "running"}, run_id="x", created_at=NOW.isoformat()) is None
    stale = pp.compact(_result(_simulated(12, 6, 5), playoff=6, completed=2), run_id="x",
                       created_at=NOW.isoformat())
    assert pp.usable(stale, model_version=VERSION, now=NOW, weight=1.0, min_weeks=3,
                     max_age_days=8, max_round=1) is None
    assert projected_pick_slot(_row(1, season=2028), proj, FMT) is None
    assert projected_pick_slot(_row(1, rnd=2), proj, FMT) is None
    assert projected_pick_slot(_row(99), proj, FMT) is None
    assert projected_pick_slot({**_row(1), "original_roster_id": None}, proj, FMT) is None


# ── the real forecast carries the tie-break ──────────────────────────────────

def test_real_simulation_output_feeds_the_wins_tie_break():
    """`league_projections.simulation.simulate` emits `expected_record` for every
    team, so stored runs take the wins tie-break, not the roster-id fallback.
    Sabotage: `_win_equivalents` demands a 4-field record → red here; `compact`
    reading a key the simulation does not write → the playoff-lock tests go red."""
    from backend.league_projections.simulation import simulate
    from backend.tests.test_league_projection_simulation import config, snapshot
    result = simulate(snapshot(), config())
    wins = {t["roster_id"]: pp._win_equivalents(t.get("expected_record")) for t in result["teams"]}
    assert wins and all(w is not None for w in wins.values())
    assert sum(wins.values()) == pytest.approx(
        sum(sum(t["expected_record"]) for t in result["teams"]) / 2)
