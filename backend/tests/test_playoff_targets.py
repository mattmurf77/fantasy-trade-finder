"""Playoff targets: the eligibility rule, the calculation and the composer.

Contract: docs/plans/league-projections/playoff-targets/contract.md. Two
worlds, as test_maxpf_moves: the season-signal fixture (real `provider.capture`,
12 teams, 14 future weeks, 20,000-run forecast) and hand-built two-team
snapshots. No network, no database.

Fixture playoff chances by roster id: 1 .88, 2 .10, 3 .95, 4 .06, 5 .20,
6 .78, 7 .69, 8 .34, 9 .28, 10 .62, 11 .73, 12 .36. Seen from team 7 the
teams under 50% are 2, 4, 5, 8, 9 and 12.

THE ELIGIBILITY RULE (contract §2), one test per condition, each with a named
sabotage in `playoff_targets.py` that turns it red. Each test goes through the
job's `compute` and the read's `compose`; test_is_seller_truth_table pins the
rule on its own and goes red under S1, S2, S3 and S4 as well, and alone
catches S6 "inclusive cut" (`<=` for `<`; no fixture team sits at exactly 50%):
- test_playoff_chance_below_half_makes_a_seller. Sabotage S3 "no probability
  rule": `is_seller` returns `saved_outlook in SELLING_OUTLOOKS` only.
- test_saved_rebuilding_outlook_makes_a_seller. Sabotage S1: drop
  "rebuilder" from SELLING_OUTLOOKS.
- test_saved_tanking_outlook_makes_a_seller. Sabotage S2: drop "jets" from
  SELLING_OUTLOOKS.
- test_a_team_at_or_above_half_without_a_selling_outlook_is_never_listed.
  Sabotage S4 "everyone sells": `is_seller` returns True.
- test_the_read_applies_the_rule_again_with_the_outlooks_saved_now. Sabotage
  S5: `compose` serves every saved row (no `selling` filter).

THE CALCULATION (contract §6):
- test_pruning_never_changes_a_gain. Sabotage: prune on `value <= floor + 5`.
- test_hand_built_*: a starter is replaced, a bye is a known zero, an
  unprojected week leaves the player out, an open slot, a free agent.
- test_rows_are_valid_and_ranked_by_playoff_gain.
- test_the_player_leaves_his_own_team. Sabotage: skip the seller's removal.
- test_only_the_largest_gains_are_resimulated, test_same_input_same_output.
- test_nothing_to_compute_skips_the_simulations (every skip reason),
  test_not_eligible_team, test_cancellation_stops_the_step.

THE READ (contract §3-§4): test_every_state_in_precedence_order,
test_unavailable_reasons, test_served_block_matches_the_contract_example,
test_the_served_block_never_carries_an_outlook_or_an_owner.

SETTINGS: test_settings_*.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
import re

import pytest

from backend.league_projections import batch, maxpf_moves, playoff_targets as pt, simulation
from backend.league_projections.core import Unavailable
from backend.league_projections.scoring import BEST_AVAILABLE
from backend.tests.test_maxpf_moves import HAND_CFG, _result, _world, hand_snapshot, model_cfg, result, world

REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / "docs/plans/league-projections/playoff-targets/contract.md"
OPTIONS = {"simulations_per_candidate": 5000, "candidates": 8, "min_playoff_gain": 0.01,
           "near_certain_min": 0.99, "time_budget_seconds": 60}
SMALL = {**OPTIONS, "simulations_per_candidate": 1000, "candidates": 4}
VIEWER = 7
UNDER_HALF = {2, 4, 5, 8, 9, 12}


@lru_cache(maxsize=None)
def _targets(viewer=VIEWER, outlooks=(), small=True):
    snap, side = _world()
    return pt.compute(snap, _result(), side["free_agents"], SMALL if small else OPTIONS, names=side["names"],
                      roster_id=viewer, seller_outlooks=dict(outlooks),
                      owners={str(t["roster_id"]): [f"owner{t['roster_id']}"] for t in snap["teams"]})


def targets(*args, **kwargs):
    return deepcopy(_targets(*args, **kwargs))


def selling(block):
    return {int(rid) for rid, s in block["sellers"].items() if s["eligible"]}


def served(block, live=None, *, state="current", viewer=VIEWER, **changes):
    saved = {**result(), "viewer_roster_id": viewer, "playoff_targets": block, **changes}
    return pt.compose(state, saved, live_outlooks=live, cuts=(0.15, 0.75))


# ---------------------------------------------------------------------------
# The eligibility rule
# ---------------------------------------------------------------------------

def test_is_seller_truth_table():
    """The rule on its own; the tests below prove the job and the read use it."""
    assert pt.is_seller(0.4999, None) and pt.is_seller(0.0, "championship")   # condition 1
    assert not pt.is_seller(0.5, None)  # strictly below, on the unrounded value
    assert pt.is_seller(0.95, "rebuilder")                                    # condition 2
    assert pt.is_seller(0.95, "jets")                                         # condition 3
    for outlook in (None, "contender", "championship", "not_sure", "", "Rebuilder", "tanking"):
        assert not pt.is_seller(0.5, outlook) and not pt.is_seller(0.95, outlook), outlook


def test_playoff_chance_below_half_makes_a_seller():
    block = targets()
    assert selling(block) == UNDER_HALF
    assert block["pool_size"] == 6 * 24  # every player on the six teams, nobody else
    assert block["rows"] and {r["seller_roster_id"] for r in block["rows"]} <= UNDER_HALF
    # The read reaches the same teams from the saved run with no outlook at all.
    out = served(block, {})
    assert out["state"] == "ready" and out["eligible_teams"] == 6 and not out["sellers_changed"]
    assert [r["player_id"] for r in out["rows"]] == [r["player_id"] for r in block["rows"]]


def _selling_outlook(outlook, team):
    """Shared body of the two saved-outlook tests below: a team well above
    50% whose manager saved `outlook` is a seller, in the job and on the read."""
    block = targets(outlooks=((team, outlook),))
    assert selling(block) == UNDER_HALF | {team}
    assert block["pool_size"] == 7 * 24
    assert any(r["seller_roster_id"] == team for r in block["rows"])
    out = served(block, {team: outlook})
    assert out["eligible_teams"] == 7 and not out["sellers_changed"]
    assert any(r["seller"]["roster_id"] == team for r in out["rows"])


def test_saved_rebuilding_outlook_makes_a_seller():
    _selling_outlook("rebuilder", 3)


def test_saved_tanking_outlook_makes_a_seller():
    _selling_outlook("jets", 6)


def test_a_team_at_or_above_half_without_a_selling_outlook_is_never_listed():
    block = targets(outlooks=((1, "contender"), (3, "championship"), (6, "not_sure"), (10, None)))
    assert selling(block) == UNDER_HALF and block["pool_size"] == 6 * 24
    assert not {r["seller_roster_id"] for r in block["rows"]} & {1, 3, 6, 10, 11}
    out = served(block, {1: "contender", 3: "championship", 6: "not_sure"})
    assert not {r["seller"]["roster_id"] for r in out["rows"]} & {1, 3, 6, 10, 11}


def test_the_read_applies_the_rule_again_with_the_outlooks_saved_now():
    block = targets(outlooks=((3, "rebuilder"),))
    from_three = [r["player_id"] for r in block["rows"] if r["seller_roster_id"] == 3]
    assert from_three
    # Still selling, under either selling outlook: the rows stay.
    for live in ({3: "rebuilder"}, {3: "jets"}, {"3": "jets"}):
        out = served(block, live)
        assert [r["player_id"] for r in out["rows"]] == [r["player_id"] for r in block["rows"]]
        assert out["eligible_teams"] == 7 and not out["sellers_changed"]
    # The manager changed or cleared the outlook after the job: the rows go.
    for live in ({3: "contender"}, {3: None}, {}, None):
        out = served(block, live)
        assert not {r["player_id"] for r in out["rows"]} & set(from_three)
        assert not any(r["seller"]["roster_id"] == 3 for r in out["rows"])
        assert out["eligible_teams"] == 6 and out["sellers_changed"]
    # A team under 50% in the run keeps selling whatever its manager saves.
    out = served(block, {3: "rebuilder", 12: "championship", 2: "contender"})
    assert {r["seller"]["roster_id"] for r in out["rows"]} == {r["seller_roster_id"] for r in block["rows"]}
    # A team that started selling after the job has no rows yet; the block says the set changed.
    out = served(block, {3: "rebuilder", 11: "jets"})
    assert out["eligible_teams"] == 8 and out["sellers_changed"]
    assert not any(r["seller"]["roster_id"] == 11 for r in out["rows"])


# ---------------------------------------------------------------------------
# The calculation: hand-built
# ---------------------------------------------------------------------------

SLOTS = ["QB", "RB", "WR", "FLEX"]
MINE = {"qb": ("Nico Varga", "QB", {"all": 20}), "rb1": ("Jonah Pike", "RB", {"all": 15}),
        "wr1": ("Milo Brandt", "WR", {"all": 14}), "rb2": ("Cal Mercer", "RB", {"all": 9}),
        "wr2": ("Ezra Quill", "WR", {"all": 6})}
THEIRS = {"star": ("Rhett Sato", "RB", {"all": 22, 12: "bye"}), "scrub": ("Tavi Lund", "WR", {"all": 5}),
          "mid": ("Dale Okafor", "WR", {"all": 10, 11: "out"}), "nodata": ("Bo Halvorsen", "WR", {10: 30}),
          "hurt": ("On Reserve", "RB", {"all": 40}), "their_qb": ("Q Two", "QB", {"all": 18}),
          "their_rb": ("R Two", "RB", {"all": 7})}


def two_teams(slots=SLOTS, mine=MINE, theirs=THEIRS, *, reserve=("hurt",), free_agents=None):
    """Team 1 is the viewer, team 2 the other roster (hand_snapshot's shape)."""
    snap, names = hand_snapshot(slots, {**mine, **theirs}, free_agents=free_agents)
    snap["teams"] = [{"roster_id": 1, "roster": {"players": sorted(mine), "taxi": [], "reserve": []}},
                     {"roster_id": 2, "roster": {"players": sorted(theirs), "taxi": [],
                                                 "reserve": sorted(set(reserve) & set(theirs))}}]
    for week in snap["weeks"]:
        week["teams"]["2"] = deepcopy(week["teams"]["1"])
    ctx = maxpf_moves._Context(snap, HAND_CFG, free_agents or {}, names)
    return snap, ctx, pt._base(ctx, snap, 1)[0]


def test_hand_built_a_starter_is_replaced_and_a_bye_is_a_known_zero():
    snap, ctx, base = two_teams()
    gains = pt.lineup_gains(ctx, 1, base, "star")
    # 58 -> 71 a week (he takes RB, Pike moves to FLEX, Mercer sits); nothing in his bye week.
    assert gains == {10: 13, 11: 13, 12: 0, 13: 13, 14: 13}
    joined = pt.joined(ctx, 1, base, "star")
    assert joined["gain"] == 52 and joined["weeks_affected"] == 4
    assert joined["replaces"] == [{"player_id": "rb2", "name": "Cal Mercer", "short_name": "C. Mercer",
                                   "free_agent": False, "weeks": 4}]
    assert joined["changes"][10] == (Decimal(-13), Decimal(-13)) and 12 not in joined["changes"]
    # A week the provider says he will not play is a known zero, not unknown.
    assert pt.lineup_gains(ctx, 1, base, "mid") == {10: 1, 11: 0, 12: 1, 13: 1, 14: 1}
    # He projects below every starter: no gain (and no re-solve).
    assert set(pt.lineup_gains(ctx, 1, base, "scrub").values()) == {0}
    # No usable projection in a week that is not a bye: left out, never scored as zero.
    assert pt.lineup_gains(ctx, 1, base, "nodata") is None
    # Reserve is not a candidate under `ir_maxpf: exclude`.
    assert "hurt" not in pt._candidate_ids(ctx, 2) and "star" in pt._candidate_ids(ctx, 2)
    # His own team re-solved without him: 18 + 22 + 10 + 7 = 57 -> 18 + 7 + 10 + 5 = 40.
    lost = pt.departed(ctx, 2, pt._base(ctx, snap, 2)[0], "star")
    assert lost[13] == (Decimal(17), Decimal(17)) and lost[12] == (Decimal(0), Decimal(0))


def test_hand_built_an_open_slot_and_a_free_agent():
    slots = ["QB", "TE"]
    mine = {"qb": ("Nico Varga", "QB", {"all": 20})}
    theirs = {"te8": ("Good Tight", "TE", {"all": 8}), "te2": ("Thin Tight", "TE", {"all": 2})}
    _, ctx, base = two_teams(slots, mine, theirs)
    joined = pt.joined(ctx, 1, base, "te8")
    assert joined["gain"] == 40 and joined["weeks_affected"] == 5
    assert joined["replaces"] == [{"player_id": None, "name": None, "short_name": None, "free_agent": False, "weeks": 5}]
    # With a projected free agent in the open slot, he replaces the free agent.
    pool = {str(w): [{"player_id": "fa", "name": "Free Tight", "positions": ["TE"], "points": "3"}] for w in range(10, 15)}
    _, ctx, base = two_teams(slots, mine, theirs, free_agents=pool)
    joined = pt.joined(ctx, 1, base, "te8")
    assert joined["gain"] == 25
    assert joined["replaces"] == [{"player_id": "fa", "name": "Free Tight", "short_name": "F. Tight",
                                   "free_agent": True, "weeks": 5}]
    # A rostered player takes the slot from a better free agent, as the forecast does: a loss, so no candidate.
    assert sum(pt.lineup_gains(ctx, 1, base, "te2").values()) == -5


# ---------------------------------------------------------------------------
# The calculation: the fixture world
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("viewer", [VIEWER, 2])
def test_pruning_never_changes_a_gain(viewer):
    snap, side = world()
    ctx = maxpf_moves._Context(snap, model_cfg(), side["free_agents"], side["names"])
    base = pt._base(ctx, snap, viewer)[0]
    checked = skipped = 0
    for team in snap["teams"]:
        if team["roster_id"] == viewer:
            continue
        for pid in pt._candidate_ids(ctx, team["roster_id"]):
            pruned, full = pt.lineup_gains(ctx, viewer, base, pid), pt.lineup_gains(ctx, viewer, base, pid, prune=False)
            assert pruned == full, pid
            checked += 1
            skipped += bool(full) and not any(full.values())
    assert checked == 11 * 24 and skipped > 20  # the fixture exercises the skip


def test_rows_are_valid_and_ranked_by_playoff_gain():
    block = targets(small=False)
    snap, side = world()
    ctx = maxpf_moves._Context(snap, model_cfg(), side["free_agents"], side["names"])
    base = pt._base(ctx, snap, VIEWER)[0]
    team = next(t for t in result()["teams"] if t["roster_id"] == VIEWER)
    rosters = {t["roster_id"]: set(t["roster"]["players"]) for t in snap["teams"]}
    assert block["computed"] and block["skipped"] is None and block["baseline"]["weeks_remaining"] == 14
    assert 1 <= len(block["rows"]) <= 8 and block["candidates_total"] >= len(block["rows"])
    assert [r["rank"] for r in block["rows"]] == list(range(1, len(block["rows"]) + 1))
    assert len({r["player_id"] for r in block["rows"]}) == len(block["rows"])
    previous = None
    for row in block["rows"]:
        now, after = row["playoff_probability"]["now"], row["playoff_probability"]["after"]
        assert now == team["playoff_probability"] and now < after <= 1
        assert row["passes_threshold"] == (after - now >= 0.01)
        assert previous is None or after - now <= previous
        previous = after - now
        assert row["player_id"] in rosters[row["seller_roster_id"]] and row["player_id"] not in rosters[VIEWER]
        exact = sum(pt.lineup_gains(ctx, VIEWER, base, row["player_id"], prune=False).values())
        assert Decimal(row["lineup_gain_exact"]) == exact.quantize(Decimal("0.01")) and exact > 0
        assert row["lineup_gain"] == maxpf_moves._whole(exact)
        assert 1 <= row["weeks_affected"] <= 14 and len(row["replaces"]) <= 3
        assert all(1 <= rep["weeks"] <= row["weeks_affected"] for rep in row["replaces"])
        assert row["name"] and row["short_name"] and row["position"] in {"QB", "RB", "WR", "TE"}
    print(f"playoff_targets fixture rows: {[(r['short_name'], r['lineup_gain'], round(r['playoff_probability']['after'], 3)) for r in block['rows']]}")


def test_only_the_largest_gains_are_resimulated():
    snap, side = world()
    ctx = maxpf_moves._Context(snap, model_cfg(), side["free_agents"], side["names"])
    base = pt._base(ctx, snap, VIEWER)[0]
    totals = {}
    for rid in UNDER_HALF:
        for pid in pt._candidate_ids(ctx, rid):
            by_week = pt.lineup_gains(ctx, VIEWER, base, pid)
            if by_week is not None and sum(by_week.values()) > 0:
                totals[pid] = sum(by_week.values())
    block = targets()
    assert block["candidates_total"] == len(totals) > SMALL["candidates"]
    top = sorted(totals, key=lambda pid: (-totals[pid], pid))[:SMALL["candidates"]]
    assert {r["player_id"] for r in block["rows"]} <= set(top)


def test_the_player_leaves_his_own_team(monkeypatch):
    snap, side = world()
    calls = []
    real = pt._lowered

    def spy(snapshot, roster_id, changes):
        calls.append((roster_id, changes))
        return real(snapshot, roster_id, changes)
    monkeypatch.setattr(pt, "_lowered", spy)
    block = pt.compute(snap, result(), side["free_agents"], {**SMALL, "candidates": 2}, names=side["names"],
                       roster_id=VIEWER)
    assert len(calls) == 4  # two finalists: his team lowered, then the viewer raised
    for (seller, lost), (viewer, gained) in zip(calls[::2], calls[1::2]):
        assert viewer == VIEWER and seller in UNDER_HALF
        assert sum(d_a for d_a, _ in lost.values()) > 0      # his team loses lineup points
        assert sum(d_a for d_a, _ in gained.values()) < 0    # the viewer's projection rises
    assert {r["seller_roster_id"] for r in block["rows"]} <= {seller for seller, _ in calls[::2]}


def test_same_input_same_output():
    snap, side = world()
    again = pt.compute(snap, result(), side["free_agents"], SMALL, names=side["names"], roster_id=VIEWER,
                       owners={str(t["roster_id"]): [f"owner{t['roster_id']}"] for t in snap["teams"]})
    assert json.dumps(again, sort_keys=True) == json.dumps(_targets(), sort_keys=True)


def _no_simulation(monkeypatch):
    monkeypatch.setattr(simulation, "simulate", lambda *a, **k: pytest.fail("nothing to compute: no simulation"))


@pytest.mark.parametrize("reason", ["season_over", "after_trade_deadline", "clinched", "eliminated", "near_certain",
                                    "no_sellers"])
def test_nothing_to_compute_skips_the_simulations(reason, monkeypatch):
    snap, side = world()
    saved, options, deadline = result(), dict(SMALL), None
    mine = next(t for t in saved["teams"] if t["roster_id"] == VIEWER)
    if reason == "season_over":
        snap["weeks"] = []
    elif reason == "after_trade_deadline":
        saved["completed_weeks"], deadline = 11, 11
    elif reason in ("clinched", "eliminated"):
        mine[f"playoff_{reason}"] = True
    elif reason == "near_certain":
        options["near_certain_min"] = mine["playoff_probability"]  # inclusive
    else:
        for team in saved["teams"]:
            team["playoff_probability"] = max(team["playoff_probability"], 0.5)
    _no_simulation(monkeypatch)
    block = pt.compute(snap, saved, side["free_agents"], options, names=side["names"], roster_id=VIEWER,
                       trade_deadline=deadline)
    assert block["computed"] and block["skipped"] == reason and block["rows"] == [] and block["pool_size"] == 0
    out = pt.compose("current", {**saved, "viewer_roster_id": VIEWER, "playoff_targets": block}, cuts=(0.15, 0.75))
    assert out["state"] == reason and out["rows"] == [] and out["reason"] is None
    assert (out["baseline"] is None) == (reason in ("season_over", "after_trade_deadline"))


def test_not_eligible_team():
    snap, side = world()
    block = pt.compute(snap, result(), side["free_agents"], SMALL, roster_id=99)
    assert block["computed"] is False and block["reason"] == "not_eligible" and block["rows"] == []
    assert served(block)["reason"] == "not_computed"


def test_cancellation_stops_the_step():
    snap, side = world()
    with pytest.raises(Unavailable) as caught:
        pt.compute(snap, result(), side["free_agents"], SMALL, roster_id=VIEWER, cancelled=lambda: True)
    assert caught.value.reason == "cancelled"


# ---------------------------------------------------------------------------
# The read
# ---------------------------------------------------------------------------

def test_every_state_in_precedence_order():
    block = targets()
    assert served(block)["state"] == "ready"
    none_pass = deepcopy(block)
    for row in none_pass["rows"]:
        row["passes_threshold"] = False
    out = served(none_pass)
    assert out["state"] == "no_targets" and len(out["rows"]) == len(block["rows"])  # still served
    # Each later condition also holds in the cases above it: the earlier state wins.
    everyone_safe = [{**t, "playoff_probability": 0.5} if t["roster_id"] != VIEWER else t for t in result()["teams"]]
    no_sellers = deepcopy(block)
    for seller in no_sellers["sellers"].values():
        seller["playoff_probability"] = 0.5
    assert served(no_sellers, teams=everyone_safe)["state"] == "no_sellers"
    certain = [{**t, "playoff_probability": 0.99} if t["roster_id"] == VIEWER else t for t in everyone_safe]
    assert served(no_sellers, teams=certain)["state"] == "near_certain"
    out = served(no_sellers, teams=[{**t, "playoff_eliminated": t["roster_id"] == VIEWER} for t in certain])
    assert out["state"] == "eliminated" and out["baseline"]["playoff_eliminated"]
    both = [{**t, "playoff_eliminated": t["roster_id"] == VIEWER, "playoff_clinched": t["roster_id"] == VIEWER}
            for t in certain]
    assert served(no_sellers, teams=both)["state"] == "clinched"
    deadline = {**no_sellers, "trade_deadline": 9}
    out = served(deadline, teams=both, completed_weeks=9)
    assert out["state"] == "after_trade_deadline" and out["baseline"] is None
    assert served(deadline, teams=both, completed_weeks=8)["state"] == "clinched"  # the deadline week has not begun
    over = {**deadline, "baseline": {**deadline["baseline"], "weeks_remaining": 0}}
    assert served(over, teams=both, completed_weeks=9)["state"] == "season_over"
    assert served(over, state="stale", teams=both, completed_weeks=9)["state"] == "unavailable"


def test_unavailable_reasons():
    block = targets()
    assert pt.compose("no_run", None) == {
        "version": 1, "state": "unavailable", "reason": "no_forecast", "viewer_roster_id": None, "captured_at": None,
        "saved_outlook": None, "baseline": None, "eligible_teams": 0, "sellers_changed": False,
        "candidates_total": 0, "rows": []}
    assert pt.compose("queued", None)["reason"] == "update_pending"
    assert served(block, state="stale")["reason"] == "stale"
    assert served(block, state="refresh_failed")["reason"] == "refresh_failed"
    assert served(block, state="unsupported_policy")["reason"] == "unsupported"
    assert served(block, model_version="older")["reason"] == "old_model"
    assert served(block, coverage={"estimate_status": "incomplete"})["reason"] == "incomplete"
    assert served(block, viewer=99)["reason"] == "team_not_found"
    for raw in (None, {}, {**block, "computed": False}, {**block, "version": 2}):
        out = served(raw)
        assert out["state"] == "unavailable" and out["reason"] == "not_computed" and out["viewer_roster_id"] == VIEWER
    assert pt.compose("current", {**result(), "viewer_roster_id": VIEWER, "playoff_targets": block},
                      saved_outlook="contender")["saved_outlook"] == "contender"


def _shape(value):
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def test_served_block_matches_the_contract_example():
    text = CONTRACT.read_text()
    examples = [json.loads(m)["playoff_targets"] for m in
                re.findall(r"```json\n(.*?)```", text[text.index("## 5. Example payloads"):text.index("## 6.")], re.S)]
    ready, unavailable, near_certain = examples
    out = pt.compose("current", {**result(), "viewer_roster_id": VIEWER, "playoff_targets": targets()},
                     saved_outlook="contender", cuts=(0.15, 0.75))
    assert out["state"] == ready["state"] == "ready"
    mine, theirs = _shape(out), _shape(ready)
    # A `replaces` entry is one shape whether or not it names a player (the example shows both).
    for shape in (mine, theirs):
        for row in shape["rows"]:
            row["replaces"] = [{k: "any" for k in row["replaces"][0]}]
    assert mine == theirs
    assert set(pt.compose("stale", {**result(), "viewer_roster_id": VIEWER})) == set(unavailable) == set(ready)
    assert unavailable["state"] == "unavailable" and near_certain["state"] == "near_certain"
    assert set(near_certain["baseline"]) == set(out["baseline"])


def test_the_served_block_never_carries_an_outlook_or_an_owner():
    block = targets(outlooks=((3, "rebuilder"),))
    out = pt.compose("current", {**result(), "viewer_roster_id": VIEWER, "playoff_targets": block},
                     live_outlooks={3: "rebuilder", 6: "jets"}, cuts=(0.15, 0.75))
    text = json.dumps(out)
    assert out["saved_outlook"] is None and any(r["seller"]["roster_id"] == 3 for r in out["rows"])
    for private in ("owner", "rebuilder", "jets", "eligible\"", "sellers\"", "skipped", "settings"):
        assert private not in text, private
    assert all(set(r["seller"]) == {"roster_id", "name", "playoff_probability", "playoff_clinched", "playoff_eliminated"}
               for r in out["rows"])
    assert "owner3" in json.dumps(block)  # saved, for the read's lookup; never served


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def test_settings_file_is_valid_and_leaves_the_batch_settings_alone():
    assert pt.settings() == OPTIONS
    assert batch.settings()["playoff_targets"] == OPTIONS  # carried, never read by the batch
    assert len(pt.settings_hash(OPTIONS)) == 64 and pt.settings_hash(OPTIONS) != pt.settings_hash(SMALL)
    assert maxpf_moves.settings()["candidates"] == 8  # Max PF moves' own object is untouched


@pytest.mark.parametrize("change", [
    {"candidates": 0}, {"candidates": 21}, {"candidates": 8.0}, {"candidates": True},
    {"simulations_per_candidate": 99}, {"min_playoff_gain": -0.01}, {"min_playoff_gain": 1.5},
    {"near_certain_min": 0.4}, {"near_certain_min": True}, {"time_budget_seconds": 0}, {"extra": 1},
])
def test_settings_reject_a_bad_value(change):
    with pytest.raises(ValueError, match="invalid_playoff_targets_configuration"):
        pt.parse_settings({**OPTIONS, **change})


def test_settings_reject_a_missing_key_or_a_missing_object():
    for raw in (None, [], {k: v for k, v in OPTIONS.items() if k != "candidates"}):
        with pytest.raises(ValueError, match="invalid_playoff_targets_configuration"):
            pt.parse_settings(raw)
    assert BEST_AVAILABLE  # the fixture world uses the production scoring contract
