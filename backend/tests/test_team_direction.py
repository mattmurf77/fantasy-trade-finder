"""The Home playoff card's `team_direction` block, composed (spec
docs/plans/league-projections/direction-pages/spec.md §5, §7, §10.1; D-265,
D-270). Pure: `team_direction.compose` over the real fixture forecast
(test_maxpf_moves) and hand-set feature blocks. The forecast read itself is
test_team_direction_read.py.

Each rule has a named change that makes its test fail:

- test_settings_are_validated. Sabotage: accept middle_min >= middle_max.
- test_band_cuts_exactly: 0.35 is middle, 0.65 is high. Sabotage: `<=` for
  the middle_max cut (0.65 reads middle).
- test_lean_at_045_and_for_each_saved_outlook. Sabotage: `<` for
  REBUILDING_MAX (0.45 leans to the playoffs).
- test_primary_falls_back_to_the_offered_direction. Sabotage: primary =
  lean whether or not it is offered.
- test_spec_worked_examples: the §5.5 table, single column.
- test_every_reason_in_7_3: every feature state maps to its §7.3 reason;
  flag off is feature_off. Sabotage: drop the ownership check (ready +
  another team's pick reads offered).
- test_every_unusable_forecast_state: no band and no primary unless the
  forecast is current, complete and from this model; the figures are still
  served as "last saved". Sabotage: compute the band before the
  unusable check.
- test_projected_pick_equals_the_max_pf_label: for the fixture's viewer the
  label is `max_pf_moves.baseline.label`, raw and served; for every team it
  is the `slot_ranks` slot. Sabotage: round the expected slot instead.
- test_projected_pick_hidden_for_a_non_max_pf_draft_order. Sabotage: drop
  the NOT_MAXPF check.
- test_pick_owner_line.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from backend import pick_projection, pick_slots
from backend.league_projections import maxpf_moves, recommendation, team_direction as td
from backend.tests.test_maxpf_moves import _block, _result

CUTS = {"middle_min": 0.35, "middle_max": 0.65}
READY_PICK = {"state": "ready", "pick_owner": {"owns_own_pick": True}}
READY_TARGETS = {"state": "ready"}


def saved(viewer=None, probability=None, **changes):
    run = {**deepcopy(_result()), **changes}
    if viewer is not None:
        run["viewer_roster_id"] = viewer
    if probability is not None:
        for team in run["teams"]:
            if team["roster_id"] == run["viewer_roster_id"]:
                team["playoff_probability"] = probability
    return run


def compose(run, state="current", *, outlook=None, pick=READY_PICK, targets=READY_TARGETS,
            max_pf_on=True, targets_on=True, draft_order=None, **kw):
    return td.compose(state, run, saved_outlook=outlook, draft_order=draft_order, cuts=CUTS,
                      max_pf_on=max_pf_on, max_pf_block=pick, targets_on=targets_on, targets_block=targets, **kw)


def test_settings_are_validated():
    assert td.settings() == {"middle_min": 0.35, "middle_max": 0.65}
    shipped = json.loads(td.CONFIG_PATH.read_text())["team_direction"]
    assert shipped == {"middle_min": 0.35, "middle_max": 0.65}
    for bad in (None, {}, {"middle_min": 0.35}, {"middle_min": 0.35, "middle_max": 0.65, "x": 1},
                {"middle_min": 0.65, "middle_max": 0.35}, {"middle_min": 0.5, "middle_max": 0.5},
                {"middle_min": 0, "middle_max": 0.65}, {"middle_min": 0.35, "middle_max": 1},
                {"middle_min": True, "middle_max": 0.65}, {"middle_min": "0.35", "middle_max": 0.65}):
        with pytest.raises(ValueError):
            td.parse_settings(bad)


def test_band_cuts_exactly():
    for p, expected in ((0.0, "low"), (0.3499999, "low"), (0.35, "middle"), (0.5, "middle"),
                        (0.6499999, "middle"), (0.65, "high"), (1.0, "high")):
        assert td.band(p, CUTS) == expected, p
        assert compose(saved(probability=p))["band"] == expected, p
    # The cuts are settings, not code.
    assert td.band(0.36, {"middle_min": 0.4, "middle_max": 0.6}) == "low"


def test_lean_at_045_and_for_each_saved_outlook():
    assert td.lean(0.45, None) == "draft_pick" and td.lean(0.4500001, None) == "playoffs"
    assert recommendation.REBUILDING_MAX == 0.45, "the 45% cut is the existing fixed REBUILDING_MAX"
    for outlook in ("rebuilder", "jets"):
        assert td.lean(0.99, outlook) == "draft_pick", outlook
    for outlook in (None, "contender", "championship", "not_sure"):
        assert td.lean(0.2, outlook) == "draft_pick" and td.lean(0.5, outlook) == "playoffs", outlook
    assert compose(saved(probability=0.45))["primary"] == "draft_pick"
    assert compose(saved(probability=0.46))["primary"] == "playoffs"
    assert compose(saved(probability=0.46), outlook="rebuilder")["primary"] == "draft_pick"


def test_primary_falls_back_to_the_offered_direction():
    no_pick = {"state": "no_moves", "pick_owner": {"owns_own_pick": True}}
    assert compose(saved(probability=0.2), pick=no_pick)["primary"] == "playoffs"
    assert compose(saved(probability=0.8), targets={"state": "no_targets"})["primary"] == "draft_pick"
    out = compose(saved(probability=0.5), pick=no_pick, targets={"state": "clinched"})
    assert out["state"] == "ready" and out["primary"] is None and out["band"] == "middle"
    out = compose(saved(probability=0.5), max_pf_on=False, targets_on=False, pick=None, targets=None)
    assert out["primary"] is None and out["options"] == {
        "playoffs": {"offered": False, "reason": "feature_off"},
        "draft_pick": {"offered": False, "reason": "feature_off"}}


def test_spec_worked_examples():
    """§5.5, both directions offered unless the row says otherwise (single column)."""
    owned = {"state": "ready", "pick_owner": {"owns_own_pick": False}}
    rows = [((0.20, None, READY_PICK), "draft_pick"), ((0.50, None, READY_PICK), "playoffs"),
            ((0.50, "rebuilder", READY_PICK), "draft_pick"), ((0.40, None, READY_PICK), "draft_pick"),
            ((0.80, None, READY_PICK), "playoffs"), ((0.50, None, owned), "playoffs")]
    for (p, outlook, pick), primary in rows:
        assert compose(saved(probability=p), outlook=outlook, pick=pick)["primary"] == primary, (p, outlook)


def test_every_reason_in_7_3():
    pick = lambda state, owns=True: td.draft_pick_option(True, {"state": state, "pick_owner": {"owns_own_pick": owns}})
    assert pick("ready") == {"offered": True, "reason": None}
    for state, reason in (("unavailable", "unavailable"), ("season_over", "season_over"),
                          ("after_trade_deadline", "after_trade_deadline"), ("no_moves", "none_found"),
                          ("no_miss", "no_miss"), ("draft_order_not_maxpf", "draft_order_not_maxpf")):
        assert pick(state) == {"offered": False, "reason": reason}, state
    assert pick("ready", owns=False) == {"offered": False, "reason": "pick_owned_elsewhere"}
    assert pick("no_moves", owns=False)["reason"] == "pick_owned_elsewhere"
    # The more basic reasons come first.
    assert pick("season_over", owns=False)["reason"] == "season_over"
    assert pick("draft_order_not_maxpf", owns=False)["reason"] == "draft_order_not_maxpf"
    assert td.draft_pick_option(True, {"state": "unavailable", "pick_owner": None})["reason"] == "unavailable"
    assert td.draft_pick_option(True, None) == {"offered": False, "reason": "unavailable"}
    assert td.draft_pick_option(False, READY_PICK) == {"offered": False, "reason": "feature_off"}
    assert td.draft_pick_option(True, {"state": "brand_new"}) == {"offered": False, "reason": "brand_new"}

    play = lambda state: td.playoffs_option(True, {"state": state})
    assert play("ready") == {"offered": True, "reason": None}
    for state, reason in (("unavailable", "unavailable"), ("season_over", "season_over"),
                          ("after_trade_deadline", "after_trade_deadline"), ("no_targets", "none_found"),
                          ("clinched", "clinched"), ("eliminated", "eliminated"),
                          ("near_certain", "near_certain"), ("no_sellers", "no_sellers")):
        assert play(state) == {"offered": False, "reason": reason}, state
    assert td.playoffs_option(True, None)["reason"] == "unavailable"
    assert td.playoffs_option(False, READY_TARGETS) == {"offered": False, "reason": "feature_off"}
    # Every §7.3 reason is reachable.
    reachable = {"feature_off", "unavailable", "season_over", "after_trade_deadline", "none_found",
                 "pick_owned_elsewhere", "no_miss", "draft_order_not_maxpf", "clinched", "eliminated",
                 "near_certain", "no_sellers"}
    seen = {pick(s, o)["reason"] for s in ("unavailable", "season_over", "after_trade_deadline", "no_moves",
                                            "no_miss", "draft_order_not_maxpf", "ready") for o in (True, False)}
    seen |= {play(s)["reason"] for s in ("unavailable", "no_targets", "clinched", "eliminated", "near_certain",
                                         "no_sellers")}
    seen.add(td.playoffs_option(False, None)["reason"])
    assert reachable <= seen


def test_every_unusable_forecast_state():
    run = saved(viewer=7)
    ready = compose(run)
    assert ready["state"] == "ready" and ready["reason"] is None and ready["band"] == "high"
    assert ready["captured_at"] == run["captured_at"] and ready["playoff_probability"] == pytest.approx(0.693, abs=1e-3)
    cases = [("queued", run, {}, "update_pending"), ("running", run, {}, "update_pending"),
             ("stale", run, {}, "stale"), ("refresh_failed", run, {}, "refresh_failed"),
             ("failed", run, {}, "refresh_failed"),
             ("current", {**run, "model_version": "older"}, {}, "old_model"),
             ("current", {**run, "coverage": {**run["coverage"], "estimate_status": "incomplete"}}, {}, "incomplete"),
             ("stale", run, {"failure_reason": "missing_weekly_projections"}, "missing_projections"),
             ("no_run", None, {}, "no_forecast"),
             ("current", saved(viewer=99), {}, "team_not_found"),
             ("unsupported_policy", run, {}, "unsupported")]
    for state, data, kw, reason in cases:
        out = compose(data, state, **kw)
        assert out["state"] == "unavailable" and out["reason"] == reason, (state, reason, out["reason"])
        assert out["band"] is None and out["primary"] is None, reason
        assert set(out) == set(ready), reason
    # A run that is not current still carries its figures, for "last saved".
    stale = compose(run, "stale")
    assert stale["playoff_probability"] == ready["playoff_probability"]
    assert stale["projected_pick"] == ready["projected_pick"] and stale["captured_at"] == run["captured_at"]
    # No run, an unknown team, or an unsupported league: nothing to show.
    for state, data in (("no_run", None), ("current", saved(viewer=99)), ("unsupported_policy", run)):
        out = compose(data, state)
        assert out["playoff_probability"] is None and out["projected_pick"] is None, state
    assert compose(None, "no_run")["captured_at"] is None
    # A bad probability is "your team cannot be matched".
    assert compose(saved(probability=1.5))["reason"] == "team_not_found"
    failed = td.read_failed(True, False)
    assert failed["state"] == "unavailable" and failed["reason"] == "read_failed"
    assert failed["options"] == {"playoffs": {"offered": False, "reason": "feature_off"},
                                 "draft_pick": {"offered": False, "reason": "unavailable"}}


def test_projected_pick_equals_the_max_pf_label():
    raw = _block()
    run = {**saved(), "max_pf_moves": deepcopy(raw)}
    viewer = run["viewer_roster_id"]
    out = compose(run)
    served = maxpf_moves.compose("current", run, cuts=(0.15, 0.75))
    assert out["projected_pick"]["label"] == raw["baseline"]["label"] == served["baseline"]["label"]
    assert out["projected_pick"]["slot"] == raw["baseline"]["label_slot"] == served["baseline"]["label_slot"]
    # Every team: the D-257 rank, the one label slot.
    slots = pick_projection.compact(run, run_id="x", created_at="").slots
    assert sorted(slots.values()) == list(range(1, len(run["teams"]) + 1))
    for team in run["teams"]:
        pick = compose(saved(viewer=team["roster_id"]))["projected_pick"]
        assert pick["slot"] == slots[str(team["roster_id"])]
        assert pick["label"] == pick_slots.slot_suffix(1, slots[str(team["roster_id"])])
    assert viewer == raw["viewer_roster_id"]


def test_projected_pick_hidden_for_a_non_max_pf_draft_order():
    run = saved()
    for rule in ("reverse_standings", "lottery_or_other"):
        out = compose(run, draft_order={"rule": rule, "set_at": "x"})
        assert out["projected_pick"] is None and out["playoff_probability"] is not None, rule
        assert out["state"] == "ready", "the pick is hidden; the rest of the block stands"
    for order in (None, {"rule": None, "set_at": None}, {"rule": "maxpf_lowest_first", "set_at": "x"}):
        assert compose(run, draft_order=order)["projected_pick"]["label"] == "1.11", order


def test_pick_owner_line():
    run = saved()
    assert compose(run)["projected_pick"] == {"label": "1.11", "slot": 11, "owns_own_pick": True,
                                              "owner_name": "Team 1"}
    for team in run["teams"]:
        if team["roster_id"] == run["viewer_roster_id"]:
            team["pick_owner_roster_id"] = 4
    pick = compose(run)["projected_pick"]
    assert pick["owns_own_pick"] is False and pick["owner_name"] == "Team 4" and pick["label"] == "1.11"


def test_block_shape_is_the_spec_shape():
    out = compose(saved())
    assert set(out) == {"version", "state", "reason", "captured_at", "playoff_probability", "playoff_clinched",
                        "playoff_eliminated", "projected_pick", "band", "primary", "options"}
    assert out["version"] == 1 and set(out["options"]) == {"playoffs", "draft_pick"}
    assert set(out["projected_pick"]) == {"label", "slot", "owns_own_pick", "owner_name"}
    json.dumps(out)
