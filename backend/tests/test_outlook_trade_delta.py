"""With-trade playoff-odds delta (#357, operator-directed 2026-08-19).

These tests carry the evidence that justified reversing [D-025]'s deferral of
the card odds block. Two of them are not ordinary regression tests — they are
the measurements the product decision rests on, and they are written to fail
loudly if the property ever stops holding:

  * `test_unchanged_roster_yields_exactly_zero` — the honesty property. A
    trade that changes nothing must show EXACTLY 0.0, not "approximately".
  * `test_delta_is_stable_across_sim_counts` — the cost property, AND the only
    test here that actually guards common random numbers. This is what
    licenses running the delta path at 2000 sims.

WHICH SABOTAGE EACH TEST CATCHES — measured 2026-08-19, not assumed
------------------------------------------------------------------
An earlier draft of this docstring claimed both tests above guarded the CRN
property. Sabotage runs showed that was wrong, and the correction is recorded
here because the mistake is easy to repeat:

| Sabotage | Caught by |
|---|---|
| Simulator seed made roster-dependent (CRN destroyed) | `test_delta_is_stable_across_sim_counts` ONLY — spread went 0.0224 vs the 0.02 bar |
| Simulator RNG unseeded (nondeterminism) | both zero-delta tests |
| `apply_trade_to_state` stops deep-copying | `test_apply_trade_does_not_mutate_the_input_state` |
| `title_pct` leaked into the payload | `test_payload_never_carries_title_pct` |

**`test_unchanged_roster_yields_exactly_zero` cannot detect CRN loss**, and
that is structural rather than a weakness to fix: with an empty trade the
rosters are identical, so even a roster-derived seed is unchanged and the two
runs still agree exactly. It guards determinism and the no-false-signal rule;
the stability test is the one that guards CRN. If you weaken the stability
test, nothing is left watching the property this whole surface rests on.
"""

from __future__ import annotations

import pytest

from backend.outlook.league_state import LeagueState, TeamState
from backend.outlook.trade_delta import (
    DELTA_SIM_COUNT,
    apply_trade_to_state,
    compute_trade_odds_impact,
    playoff_band,
    resim_baseline,
)

LEAGUE = "L-delta-1"
SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"]


def _state(completed_weeks: int = 0) -> LeagueState:
    teams = [
        TeamState(
            roster_id=i,
            user_id=f"u{i}",
            username=f"t{i}",
            display_name=f"t{i}",
            player_ids=[f"p{i}_{j}" for j in range(25)],
            starters=[f"p{i}_{j}" for j in range(9)],
        )
        for i in range(1, 13)
    ]
    schedule = {
        w: [(a, b) for a, b in zip(range(1, 13, 2), range(2, 13, 2))]
        for w in range(1, 15)
    }
    return LeagueState(
        league_id=LEAGUE,
        platform="sleeper",
        season="2026",
        regular_season_weeks=14,
        playoff_slots=6,
        num_byes=2,
        roster_slots=list(SLOTS),
        teams=teams,
        schedule=schedule,
        completed_weeks=completed_weeks,
        status="in_season",
    )


def _values(bump: dict[str, float] | None = None) -> dict[str, float]:
    pv = {
        f"p{i}_{j}": float(2000 - (i * 40) - (j * 15))
        for i in range(1, 13)
        for j in range(25)
    }
    pv.update(bump or {})
    return pv


def _positions() -> dict[str, str]:
    return {
        f"p{i}_{j}": ["QB", "RB", "WR", "TE"][j % 4]
        for i in range(1, 13)
        for j in range(25)
    }


def _impact(give, recv, *, pv=None, n_sims=DELTA_SIM_COUNT, completed_weeks=0):
    st = _state(completed_weeks)
    pv = pv if pv is not None else _values()
    pp = _positions()
    base = resim_baseline(
        st, player_value=pv, player_pos=pp, model_cfg={},
        basis="consensus", scoring_format="1qb_ppr", n_sims=n_sims,
    )
    return compute_trade_odds_impact(
        base, st,
        user_roster_id=1, opponent_roster_id=2,
        give_player_ids=give, receive_player_ids=recv,
        player_value=pv, player_pos=pp, model_cfg={},
        basis="consensus", scoring_format="1qb_ppr", n_sims=n_sims,
    )


# ---------------------------------------------------------------------------
# The honesty property
# ---------------------------------------------------------------------------

def test_unchanged_roster_yields_exactly_zero():
    """The no-false-signal guarantee: an empty trade is bit-identical, not
    merely close.

    If this fails, the surface must be pulled — it would mean a trade that
    changes nothing can display a shift, the exact false-precision failure the
    playoff-odds band rules exist to prevent.

    Scope note (see the module docstring): this test guards DETERMINISM, not
    common random numbers. It passes even with a roster-derived seed, because
    an empty trade leaves the rosters — and therefore that seed — unchanged.
    `test_delta_is_stable_across_sim_counts` is the CRN guard."""
    imp = _impact([], [])
    assert imp is not None
    assert imp.delta_pct == 0.0
    assert imp.before_pct == imp.after_pct
    assert imp.band_changed is False
    assert imp.seed_delta == 0.0


def test_ids_not_on_the_roster_are_ignored_and_still_yield_zero():
    """A stale or pick id must not move the number. Picks cannot start, so
    they contribute 0 to every lineup by construction."""
    imp = _impact(["pick_2027_1st", "not_a_real_player"], ["also_fake"])
    assert imp is not None
    assert imp.delta_pct == 0.0


# ---------------------------------------------------------------------------
# The cost property
# ---------------------------------------------------------------------------

def test_delta_is_stable_across_sim_counts():
    """What licenses DELTA_SIM_COUNT = 2000 — and the ONLY test here that
    detects common-random-numbers loss (sabotage-verified: a roster-derived
    simulator seed pushes the spread to 0.0224 against the 0.02 bar).

    Two bars, both two-sided by construction:
      (a) the 2000-sim delta lands within 2 points of the 10000-sim delta;
      (b) the delta is MORE stable across that reduction than the absolute
          `playoff_pct` it is computed from — the whole CRN argument.
    """
    pv = _values({"p2_5": 2000 - 40 - (8 * 15) + 120.0})
    give, recv = ["p1_8"], ["p2_5"]

    hi = _impact(give, recv, pv=pv, n_sims=10000)
    lo = _impact(give, recv, pv=pv, n_sims=DELTA_SIM_COUNT)
    assert hi is not None and lo is not None

    delta_spread = abs(hi.delta_pct - lo.delta_pct)
    absolute_spread = abs(hi.before_pct - lo.before_pct)

    assert delta_spread <= 0.02, (
        f"delta moved {delta_spread:.4f} between 10000 and {DELTA_SIM_COUNT} "
        "sims; the reduced sim count is no longer defensible")
    assert delta_spread <= absolute_spread, (
        f"delta spread {delta_spread:.4f} exceeded absolute spread "
        f"{absolute_spread:.4f} — the common-random-numbers property that "
        "justifies showing a shift at all has been lost (did the simulator's "
        "seed start depending on rosters?)")


# ---------------------------------------------------------------------------
# Direction and shape
# ---------------------------------------------------------------------------

def test_a_real_upgrade_moves_the_odds_up():
    pv = _values({"p2_5": 3200.0})
    imp = _impact(["p1_8"], ["p2_5"], pv=pv)
    assert imp is not None
    assert imp.delta_pct > 0, "receiving a far better player must not lower odds"


def test_a_real_downgrade_moves_the_odds_down():
    pv = _values({"p1_0": 3200.0})
    imp = _impact(["p1_0"], ["p2_20"], pv=pv)
    assert imp is not None
    assert imp.delta_pct < 0, "giving away a stud for a scrub must not raise odds"


def test_apply_trade_does_not_mutate_the_input_state():
    """The baseline state is reused for every card in a deck; mutating it
    would corrupt every later comparison in the same deck."""
    st = _state()
    before_user = list(st.teams[0].player_ids)
    before_opp = list(st.teams[1].player_ids)
    out = apply_trade_to_state(
        st, user_roster_id=1, opponent_roster_id=2,
        give_player_ids=["p1_8"], receive_player_ids=["p2_5"],
    )
    assert st.teams[0].player_ids == before_user
    assert st.teams[1].player_ids == before_opp
    assert "p2_5" in out.teams[0].player_ids
    assert "p1_8" in out.teams[1].player_ids
    assert "p1_8" not in out.teams[0].player_ids


def test_payload_never_carries_title_pct():
    """`title_pct` is unrenderable at any week on an absence of demonstrated
    skill. This module must not put it within a client's reach."""
    imp = _impact(["p1_8"], ["p2_5"])
    assert imp is not None
    blob = imp.as_dict()
    assert "title_pct" not in blob
    assert not any("title" in k for k in blob)


@pytest.mark.parametrize(
    "frac,band",
    [(1.0, "likely"), (0.65, "likely"), (0.6499, "tossup"),
     (0.35, "tossup"), (0.3499, "unlikely"), (0.0, "unlikely")],
)
def test_band_boundaries_belong_to_the_higher_band(frac, band):
    """Same top-down walk every client uses — exactly 0.65 is `likely`,
    exactly 0.35 is `tossup`."""
    assert playoff_band(frac) == band


def test_unresolvable_roster_returns_none_rather_than_guessing():
    st = _state()
    pv, pp = _values(), _positions()
    base = resim_baseline(st, player_value=pv, player_pos=pp, model_cfg={},
                          basis="consensus", scoring_format="1qb_ppr")
    out = compute_trade_odds_impact(
        base, st,
        user_roster_id=999, opponent_roster_id=2,
        give_player_ids=[], receive_player_ids=[],
        player_value=pv, player_pos=pp, model_cfg={},
        basis="consensus", scoring_format="1qb_ppr",
    )
    assert out is None
