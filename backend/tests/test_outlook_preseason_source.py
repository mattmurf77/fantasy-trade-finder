"""Regression guards for the preseason `roster_value` backtest (#169).

The headline claim of `dated-values-revalidation-2026-08-09.md` — that the
preseason source has *some* demonstrated playoff skill but is over-confident
at the extremes — rests on three pieces of plumbing that could silently rot:

  1. rosters are rewound to the season's real week-1 roster (the calibration
     harness deliberately does NOT do this; without it a 2022 roster is
     priced as it stands in 2026 and the whole result is hindsight);
  2. `auto` resolves to `roster_value` at `completed_weeks == 0`;
  3. the dated board actually prices the starting lineups it is asked about.

The heavy Monte-Carlo run lives in `scripts/outlook_preseason_backtest.py`;
these tests exercise the plumbing on one league at a small sim count and
re-score the committed per-team records, so they stay fast.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

from backend import dp_values_history as dvh
from backend.outlook.pipeline import run_outlook
from backend.outlook.strength import select_starting_lineup

# The analysis scripts live outside any package; same sys.path shim as
# test_outlook_calibration.py. Imported hard (not `importorskip`) so a broken
# script fails the suite instead of silently skipping its guards.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import scripts.outlook_calibration_backtest as scripts_backtest  # noqa: E402
import scripts.outlook_preseason_backtest as preseason  # noqa: E402

scripts = scripts_backtest

RECORDS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "outlook-hypotheses",
    "preseason-backtest-records.json",
)


@pytest.fixture(scope="module")
def pos_and_index():
    pos_map = preseason.player_positions()
    return ({pid: (m.get("position") or "?") for pid, m in pos_map.items()},
            preseason.roster_name_index(pos_map))


def test_rosters_are_rewound_to_the_real_week_one_roster(pos_and_index):
    fx = scripts.load_fixture("ffv3-2022")
    full = scripts.build_full_state(fx)
    current = {t.roster_id: set(t.player_ids) for t in full.teams}
    st0 = scripts.as_of(full, 0)
    gaps = preseason.rewind_rosters(st0, fx)
    assert gaps == []
    rewound = {t.roster_id: set(t.player_ids) for t in st0.teams}
    # A 2022 week-1 roster cannot equal the 2026 snapshot for every team; if
    # it did, the rewind is a no-op and the backtest is scoring today's teams.
    assert any(rewound[rid] != current[rid] for rid in rewound)
    assert all(rewound[rid] for rid in rewound)


def test_preseason_state_carries_no_results(pos_and_index):
    fx = scripts.load_fixture("ffv3-2022")
    st0 = scripts.as_of(scripts.build_full_state(fx), 0)
    assert st0.completed_weeks == 0
    for t in st0.teams:
        assert (t.wins, t.losses, t.ties) == (0, 0, 0)
        assert t.points_for == 0.0
        assert not st0.weekly_scores.get(t.roster_id)


def test_auto_resolves_to_roster_value_and_the_dated_board_prices_the_lineups(
        pos_and_index):
    player_pos, extra_idx = pos_and_index
    fx = scripts.load_fixture("ffv3-2022")
    full = scripts.build_full_state(fx)
    st0 = scripts.as_of(full, 0)
    preseason.rewind_rosters(st0, fx)

    scoring = preseason.scoring_format_for(fx)
    assert scoring == "1qb"          # FFv3 is a 1QB league
    values, report, meta = dvh.values_as_of(dvh.week_boundary(2022, 0),
                                            scoring=scoring,
                                            extra_name_pos=extra_idx)
    assert meta["scrape_date"] < "2022-09-08"      # published before kickoff
    assert report.unmatched_rate < 0.05

    _ros_cov, slot_cov = preseason.coverage(st0, values, player_pos)
    assert slot_cov > 0.95, slot_cov

    payload = run_outlook(st0, player_value=values, player_pos=player_pos,
                          model_cfg={}, basis="consensus",
                          source_override="auto", n_sims=400)
    assert payload["meta"]["strength_source"] == "roster_value"
    mus = {t["roster_id"]: t["odds"]["projected_wins"] for t in payload["teams"]}
    # A board that failed to resolve would give every team the same mu and
    # therefore identical projected wins.
    assert len(set(round(v, 3) for v in mus.values())) > 1


def test_starting_lineup_selection_uses_the_dated_board(pos_and_index):
    """Sanity: the lineup picked with a 2022 board is not the lineup picked
    with a 2025 board — i.e. the board is genuinely load-bearing."""
    player_pos, extra_idx = pos_and_index
    fx = scripts.load_fixture("ffv3-2022")
    full = scripts.build_full_state(fx)
    st0 = scripts.as_of(full, 0)
    preseason.rewind_rosters(st0, fx)
    v22, _r, _m = dvh.values_as_of(dvh.week_boundary(2022, 0), scoring="1qb",
                                   extra_name_pos=extra_idx)
    v25, _r, _m = dvh.values_as_of(dvh.week_boundary(2025, 0), scoring="1qb",
                                   extra_name_pos=extra_idx)
    differs = 0
    for t in st0.teams:
        a = select_starting_lineup(t.player_ids, v22, player_pos, st0.roster_slots)
        b = select_starting_lineup(t.player_ids, v25, player_pos, st0.roster_slots)
        differs += int(a != b)
    assert differs > 0


# ---------------------------------------------------------------------------
# Committed per-team records — the report's headline, re-scored without sims
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def records():
    with open(RECORDS) as f:
        return json.load(f)


def test_records_cover_the_same_sample_the_report_claims(records):
    assert len(records) == 72
    assert len({r["league"] for r in records}) == 6
    assert sum(r["y_title"] for r in records) == 6
    assert sum(r["y_playoff"] for r in records) == 36


def test_preseason_playoff_odds_beat_climatology_on_the_captured_seasons(records):
    """Regression guard mirroring `test_engine_beats_climatology_on_captured_seasons`
    for the PRESEASON source. Bar is the report's measured +21.6 % skill with
    slack — this catches a regression, it does not re-derive the CI."""
    model = scripts.brier([(r["p_playoff"], r["y_playoff"]) for r in records])
    clim = scripts.brier([(r["clim_playoff"], r["y_playoff"]) for r in records])
    assert model < 0.9 * clim, (model, clim)


def test_preseason_title_odds_are_not_claimed_to_beat_climatology(records):
    """The report's no-ship recommendation for preseason title odds. If a
    future change makes this fail, the recommendation needs revisiting —
    deliberately asserted so the null cannot rot away unnoticed."""
    model = scripts.brier([(r["p_title"], r["y_title"]) for r in records])
    clim = scripts.brier([(r["clim_title"], r["y_title"]) for r in records])
    assert model > 0.9 * clim, (model, clim)


def test_preseason_is_not_materially_worse_than_the_validated_week_three_model(records):
    """The decision the operator faces is 'preseason odds vs nothing until
    week 3'. The report's finding is that the two are indistinguishable on
    playoff Brier."""
    pre = scripts.brier([(r["p_playoff"], r["y_playoff"]) for r in records])
    wk3 = scripts.brier([(r["wk3_playoff"], r["y_playoff"]) for r in records])
    assert abs(pre - wk3) < 0.05, (pre, wk3)
