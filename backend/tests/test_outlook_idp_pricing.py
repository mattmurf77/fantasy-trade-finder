"""BUG-5 — unpriced IDP/K starting slots in `RosterValueStrength` (#169).

The DynastyProcess board FTF seeds from carries QB/RB/WR/TE only. In the
operator's FFv3 league — 4 of the 6 backtested league-seasons — the starting
lineup is `QB,RB,RB,WR,WR,TE,FLEX,K,DL,DL,LB,LB,DB,DB,IDP_FLEX`, so **8 of 15
starting slots price at exactly 0.0** and the preseason strength estimate sees
under half of every roster.

Three things are pinned here:

  1. **the premise** — the board really does carry no defender and no kicker,
     so a future board that starts pricing them makes this test fail loudly
     rather than leaving `lineup_pricing()` quietly wrong;
  2. **the detection** — `lineup_pricing()` reports the unpriceable slots of a
     real IDP league-season, and reports full coverage for an offence-only one;
  3. **the neutrality of the fix** — teaching `select_starting_lineup()` real
     IDP slot eligibility changes WHICH players fill the defensive slots but
     cannot change `starting_lineup_value`, because every newly-selectable
     player is priced 0.0. The pre-BUG-5 selection is used as the oracle.

Verdict and the measured before/after: `docs/feedback/items/
169-outlook-league-summary/idp-pricing-2026-08-09.md`.
"""

from __future__ import annotations

import csv
import json
import os
import sys

import pytest

from backend import dp_values_history as dvh
from backend.outlook.strength import (
    RosterValueStrength, StrengthContext, eligible_positions, lineup_pricing,
    select_starting_lineup, starting_lineup_value,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import scripts.outlook_calibration_backtest as scripts_backtest  # noqa: E402
import scripts.outlook_idp_pricing_backtest as idp  # noqa: E402
import scripts.outlook_preseason_backtest as preseason  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "outlook-hypotheses")
RECORDS = os.path.join(FIXTURES, "idp-pricing-backtest-records.json")
TODAY_BOARD = os.path.join(FIXTURES, "dp-values-players-2026-08-09.csv")

IDP_SEASONS = {"ffv3-2025": 2025, "ffv3-2024": 2024,
               "ffv3-2023": 2023, "ffv3-2022": 2022}
OFFENCE_SEASONS = {"lakeview-2025": 2025, "lakeview-2024": 2024}

# The exact slots the board cannot price in FFv3, in roster order.
FFV3_UNPRICEABLE = ("K", "DL", "DL", "LB", "LB", "DB", "DB", "IDP_FLEX")


@pytest.fixture(scope="module")
def pos_and_index():
    pos_map = preseason.player_positions()
    return ({pid: (m.get("position") or "?") for pid, m in pos_map.items()},
            preseason.roster_name_index(pos_map))


def _week0(name, season, extra_idx):
    """Real week-1 rosters + the kickoff-day dated board for a league-season."""
    fx = scripts_backtest.load_fixture(name)
    st0 = scripts_backtest.as_of(scripts_backtest.build_full_state(fx), 0)
    assert preseason.rewind_rosters(st0, fx) == []
    values, _rep, _meta = dvh.values_as_of(
        dvh.week_boundary(season, 0),
        scoring=preseason.scoring_format_for(fx), extra_name_pos=extra_idx)
    return st0, values


# ---------------------------------------------------------------------------
# 1. The premise — the value board is offence-only
# ---------------------------------------------------------------------------

def test_the_value_board_prices_no_defender_and_no_kicker():
    """If DynastyProcess ever starts publishing IDP or K values this fails,
    which is the signal to revisit the whole finding — the coverage number,
    the docs, and the no-fix verdict all rest on this being true."""
    with open(TODAY_BOARD, newline="") as f:
        positions = {(row.get("pos") or "").upper() for row in csv.DictReader(f)}
    assert positions == {"QB", "RB", "WR", "TE"}, sorted(positions)


# ---------------------------------------------------------------------------
# 2. Detection — lineup_pricing()
# ---------------------------------------------------------------------------

def test_lineup_pricing_flags_the_unpriceable_slots_of_a_synthetic_idp_league():
    value = {"qb": 9000.0, "rb": 5000.0, "de": 0.0, "k": 0.0}
    pos = {"qb": "QB", "rb": "RB", "de": "DE", "k": "K"}
    lp = lineup_pricing(["QB", "RB", "FLEX", "K", "DL", "IDP_FLEX"], value, pos)
    assert lp.total_slots == 6
    assert lp.priceable_slots == 3
    assert lp.unpriceable_slots == ("K", "DL", "IDP_FLEX")
    assert lp.coverage == pytest.approx(0.5)


def test_lineup_pricing_reports_full_coverage_for_an_offence_only_league():
    value = {"qb": 9000.0, "wr": 6000.0}
    pos = {"qb": "QB", "wr": "WR"}
    lp = lineup_pricing(["QB", "WR", "FLEX", "SUPER_FLEX"], value, pos)
    assert lp.unpriceable_slots == ()
    assert lp.coverage == 1.0


def test_lineup_pricing_is_vacuously_full_when_the_league_has_no_slots():
    """ESPN imports arrive without roster_positions; `starting_lineup_value`
    sums the whole roster there, so there is no slot to be blind to."""
    assert lineup_pricing([], {"a": 1.0}, {"a": "QB"}).coverage == 1.0


@pytest.mark.parametrize("name,season", sorted(IDP_SEASONS.items()))
def test_real_idp_league_season_has_eight_of_fifteen_slots_unpriced(
        name, season, pos_and_index):
    player_pos, extra_idx = pos_and_index
    st0, values = _week0(name, season, extra_idx)
    lp = lineup_pricing(st0.roster_slots, values, player_pos)
    assert lp.total_slots == 15
    assert lp.unpriceable_slots == FFV3_UNPRICEABLE
    assert lp.coverage == pytest.approx(7 / 15)


@pytest.mark.parametrize("name,season", sorted(OFFENCE_SEASONS.items()))
def test_real_offence_only_league_season_is_fully_priced(name, season, pos_and_index):
    player_pos, extra_idx = pos_and_index
    st0, values = _week0(name, season, extra_idx)
    lp = lineup_pricing(st0.roster_slots, values, player_pos)
    assert lp.unpriceable_slots == ()
    assert lp.coverage == 1.0


# ---------------------------------------------------------------------------
# 3. The eligibility fix — IDP slots fill, and nothing else moves
# ---------------------------------------------------------------------------

def test_idp_slots_accept_nfl_positions_not_just_the_group_name():
    """A "DL" slot is a fantasy position GROUP; a player's position is his NFL
    position. Pre-BUG-5 a DL slot only accepted a player literally labelled
    "DL", so a roster of DEs and DTs started nobody there."""
    assert "DE" in eligible_positions("DL") and "NT" in eligible_positions("DL")
    assert "CB" in eligible_positions("DB") and "FS" in eligible_positions("DB")
    assert "OLB" in eligible_positions("LB")
    assert set(eligible_positions("IDP_FLEX")) >= {"DE", "OLB", "CB"}
    # unknown slots still match their own name — QB/RB/WR/TE/K/DEF unchanged
    assert eligible_positions("K") == ("K",)
    assert eligible_positions("DEF") == ("DEF",)


def test_defensive_slots_are_filled_and_never_by_an_offensive_player():
    value = {"qb": 9000.0, "de": 0.0, "cb": 0.0, "olb": 0.0}
    pos = {"qb": "QB", "de": "DE", "cb": "CB", "olb": "OLB"}
    picked = select_starting_lineup(list(value), value, pos,
                                    ["QB", "DL", "DB", "IDP_FLEX"])
    assert picked == ["qb", "de", "cb", "olb"]
    # a WR-only roster leaves every defensive slot empty rather than starting him
    assert select_starting_lineup(["wr"], {"wr": 100.0}, {"wr": "WR"},
                                  ["DL", "LB", "DB"]) == []


def test_idp_flex_takes_the_leftover_defender_after_the_group_slots():
    value = {"dl1": 0.0, "dl2": 0.0, "lb1": 0.0}
    pos = {"dl1": "DT", "dl2": "DE", "lb1": "LB"}
    picked = select_starting_lineup(list(value), value, pos, ["DL", "IDP_FLEX"])
    assert len(picked) == 2 and set(picked) <= set(value)


@pytest.mark.parametrize("name,season", sorted({**IDP_SEASONS, **OFFENCE_SEASONS}.items()))
def test_eligibility_fix_cannot_change_any_starting_lineup_value(
        name, season, pos_and_index):
    """THE load-bearing invariant. The fix changes which players fill the
    defensive slots; it must not change the priced total, because the board
    values every one of them at 0.0. Oracle is the verbatim pre-BUG-5
    selection kept in `scripts/outlook_idp_pricing_backtest.py`."""
    player_pos, extra_idx = pos_and_index
    st0, values = _week0(name, season, extra_idx)
    for t in st0.teams:
        before = sum(values.get(pid, 0.0) for pid in idp.legacy_select(
            t.player_ids, values, player_pos, st0.roster_slots))
        after = starting_lineup_value(t.player_ids, values, player_pos,
                                      st0.roster_slots)
        assert after == pytest.approx(before), (name, t.roster_id)


def test_eligibility_fix_does_fill_slots_the_old_rule_left_empty():
    """The mirror of the invariant above — if the fix moved nothing at all it
    would be dead code. Uses a synthetic roster so it does not depend on the
    fixture leagues' position mix."""
    value = {"de": 0.0, "cb": 0.0}
    pos = {"de": "DE", "cb": "CB"}
    slots = ["DL", "DB"]
    assert idp.legacy_select(list(value), value, pos, slots) == []
    assert len(select_starting_lineup(list(value), value, pos, slots)) == 2


@pytest.mark.parametrize("slots", [
    ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "FLEX", "SUPER_FLEX"],
    ["QB", "RB", "WR", "REC_FLEX", "FLEX", "WRRB_FLEX"],
    ["QB", "RB", "FLEX"],
])
def test_offence_only_selection_is_unchanged_slot_for_slot(slots):
    """Non-IDP leagues must be bit-identical, including leagues that mix
    several flex kinds — the fill order changed shape, not behaviour."""
    value = {"qb1": 9000.0, "qb2": 3000.0, "rb1": 5000.0, "rb2": 4000.0,
             "wr1": 6000.0, "wr2": 2000.0, "wr3": 1500.0, "te1": 3500.0}
    pos = {"qb1": "QB", "qb2": "QB", "rb1": "RB", "rb2": "RB", "wr1": "WR",
           "wr2": "WR", "wr3": "WR", "te1": "TE"}
    assert (select_starting_lineup(list(value), value, pos, slots)
            == idp.legacy_select(list(value), value, pos, slots))


def test_roster_value_strength_mu_is_unchanged_on_a_real_idp_league(pos_and_index):
    """Provider level, on the operator's own league: the fix must not move a
    single team's mu."""
    player_pos, extra_idx = pos_and_index
    st0, values = _week0("ffv3-2024", 2024, extra_idx)
    ctx = StrengthContext(player_value=values, player_pos=player_pos, cfg={})
    after = RosterValueStrength().estimate(st0, ctx)
    before = idp.V0StatusQuo().estimate(st0, ctx)
    assert {r: s.mu for r, s in after.items()} == pytest.approx(
        {r: s.mu for r, s in before.items()})


# ---------------------------------------------------------------------------
# 4. The measured verdict — re-scored from committed records, no sims
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def records():
    with open(RECORDS) as f:
        return json.load(f)


def _brier(records, variant, key, leagues=None):
    rows = [r for r in records if leagues is None or r["league"] in leagues]
    return scripts_backtest.brier([(r[variant][key], r["y_" + key]) for r in rows])


def test_records_cover_the_same_sample_the_report_claims(records):
    assert len(records) == 72
    assert {r["league"] for r in records} == set(IDP_SEASONS) | set(OFFENCE_SEASONS)
    assert sum(r["y_playoff"] for r in records) == 36


def test_eligibility_fix_left_every_backtested_prediction_identical(records):
    for r in records:
        assert r["V1 eligibility fix"] == r["V0 status quo"], r["league"]


def test_no_available_pricing_fix_beats_the_status_quo(records):
    """The report's verdict. Both fabricating a price for the unpriced slots
    (V2) and attenuating the signal by coverage (V3) were measured; neither
    improves playoff Brier by more than noise. Bar is deliberately loose — it
    catches a variant becoming *materially* better or worse, which is the
    signal to revisit the recommendation."""
    base = _brier(records, "V0 status quo", "playoff", IDP_SEASONS)
    for variant in ("V2 league-mean fallback", "V3 attenuation (sqrt)",
                    "V3 attenuation (linear)"):
        assert abs(_brier(records, variant, "playoff", IDP_SEASONS) - base) < 0.02, variant


def test_the_non_idp_league_is_untouched_by_every_variant(records):
    """Lakeview has full coverage, so no unpriced-slot policy can reach it.
    Any movement here means a variant leaked into offence-only leagues."""
    for r in (r for r in records if r["league"] in OFFENCE_SEASONS):
        for variant in ("V1 eligibility fix", "V2 league-mean fallback",
                        "V3 attenuation (sqrt)", "V3 attenuation (linear)"):
            assert r[variant] == r["V0 status quo"], (r["league"], variant)


def test_the_backtest_state_is_a_genuine_preseason_state():
    """Guard against the records being regenerated from an in-season state —
    every claim in the report is an as-of-week-0 claim."""
    fx = scripts_backtest.load_fixture("ffv3-2024")
    st0 = scripts_backtest.as_of(scripts_backtest.build_full_state(fx), 0)
    assert st0.completed_weeks == 0
    assert all((t.wins, t.losses, t.ties) == (0, 0, 0) for t in st0.teams)


def test_lineup_pricing_takes_plain_data_and_no_league_state():
    """It is a pure function of slot shape × board coverage — no LeagueState,
    no simulation — so the serializer (owned elsewhere) can call it straight
    off `state.roster_slots`. Pinned so a refactor does not couple it."""
    lp = lineup_pricing(["QB", "DL"], {"a": 1.0}, {"a": "QB"})
    assert lp.unpriceable_slots == ("DL",)
    assert lp.coverage == pytest.approx(0.5)
