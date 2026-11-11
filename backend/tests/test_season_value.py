"""Win-now season signal WI-1: season evidence, league profile, labels, conflict predicate.

Spec: docs/plans/win-now-season-signal/lld.md §1.2, §2, §3.5 and invariants I11, I12
(§10); PRD §2.5, §4, §5.1; build-plan WI-1. Fixture: the real capture over the
committed 12-team league of public players (see test_season_points.py), viewed at
the capture time, so the horizon is regular-season weeks 1-14.

Covered (each proven red against the named sabotage):
- test_unprojected_player_has_no_points_no_label_never_zero (I11). Sabotage:
  default a missing player to 0.0.
- test_week_already_kicked_off_is_not_in_the_horizon. Sabotage: compare kickoff
  with captured_at instead of as_of.
- test_digest_stable_inside_a_horizon_and_changes_with_the_snapshot (I12).
  Sabotage: hash as_of.
- test_each_unavailable_reason_has_its_own_input; test_viewer_unprojected_asset_rule.
  Sabotage: return stale for an old-model run.
- test_label_table_* (one per row of PRD §4.3, the PRD's named players). Sabotage:
  `_now_lean >= 0.05` as the cliff test (Justin Jefferson turns win-now).
- test_29_year_old_startable_rb_with_future_over_floor_is_win_now. Sabotage: drop
  the cliff clause.
- test_conflict_predicate_*: All-in at -0.5, Contending at -1.0, the Rebuilding /
  Tanking mirror, never for Not sure, an unsaved plan, a pinned search or without
  usable evidence. Sabotage: use 0.5 for Contending.
- test_label_distribution_on_the_fixture: the per-label counts, pinned.
- test_free_agent_level_reads_v6_rows: v6 free-agent rows set the empty-slot level
  and never enter `players`; a v5 snapshot gives zeros.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import timedelta
import json

import pytest

from backend import season_value as sv
from backend.league_projections import season_points
from backend.league_projections.core import VERSION
from backend.tests.test_season_points import (CAPTURED_AT, LEAGUE_ID, _schedule, captured_snapshot,
                                              load_league, load_pool)

LEAGUE, POOL = load_league(), load_pool()
SLOTS = LEAGUE["slots"]


def evidence(snapshot=None, **overrides):
    kwargs = dict(as_of=CAPTURED_AT, league_id=LEAGUE_ID, slots=SLOTS, platform="sleeper",
                  run_id="run-1", model_version=VERSION, current=True)
    kwargs.update(overrides)
    return sv.build_evidence(captured_snapshot() if snapshot is None else snapshot, **kwargs)


def world():
    """rosters, position, market, age for the fixture league (picks included)."""
    rosters, position, market, age = {}, {}, {}, {}
    for team in LEAGUE["teams"]:
        rosters[team["owner_id"]] = team["players"] + list(team["picks"])
        for pid in team["players"]:
            row = POOL[pid]
            position[pid], market[pid] = row["position"], float(row["dp_value_1qb"])
            # The pool has no age for most rookies: a first-year player is 22.
            age[pid] = row["age"] or (22 if (row.get("years_exp") or 0) == 0 else None)
        for pid, value in team["picks"].items():
            position[pid], market[pid], age[pid] = "PICK", float(value), None
    return rosters, position, market, age


ROSTERS, POSITION, MARKET, AGE = world()
BY_NAME = {POOL[pid]["full_name"]: pid for team in LEAGUE["teams"] for pid in team["players"]}


def profile(ev=None):
    return sv.league_profile(ev or evidence(), rosters=ROSTERS, position=POSITION, market=MARKET, age=AGE)


@pytest.fixture(scope="module")
def prof():
    return profile()


def label_of(prof, name):
    return prof["players"][BY_NAME[name]]


# --- I11: unknown is never zero ---------------------------------------------------

def test_unprojected_player_has_no_points_no_label_never_zero():
    snapshot = captured_snapshot()
    # Stefon Diggs has Sleeper rows but no NFL team in the metadata: capture leaves
    # him unpriced. Davante Adams loses every row: absent from the snapshot entirely.
    adams = BY_NAME["Davante Adams"]
    snapshot["player_week_inputs"] = [e for e in snapshot["player_week_inputs"] if e["player_id"] != adams]
    ev = evidence(snapshot)
    prof = profile(ev)
    for name in ("Stefon Diggs", "Davante Adams"):
        pid = BY_NAME[name]
        assert pid in ev["unprojected"] and pid not in ev["players"]
        assert prof["players"][pid] == {"label": None, "future": None, "startable": None}
    assert all(item["ppg"] is not None and item["games"] > 0 for item in ev["players"].values())


# --- horizon -------------------------------------------------------------------

def test_week_already_kicked_off_is_not_in_the_horizon():
    week3 = min(g["kickoff"] for g in _schedule() if g["week"] == 3)
    # The Thursday game of week 3 has kicked off; week 3 is out for everyone.
    ev = evidence(as_of=(week3 + timedelta(minutes=1)).isoformat())
    assert ev["state"] == "usable" and ev["weeks"] == list(range(4, 15))
    assert evidence(as_of=(week3 - timedelta(minutes=1)).isoformat())["weeks"] == list(range(3, 15))
    last = min(g["kickoff"] for g in _schedule() if g["week"] == 14)
    assert evidence(as_of=(last + timedelta(seconds=1)).isoformat()) == sv.unavailable("no_upcoming_week")


def test_points_per_game_ignore_byes_and_follow_the_horizon():
    ev = evidence()
    jefferson = BY_NAME["Justin Jefferson"]
    assert ev["players"][jefferson] == {"ppg": 16.81, "games": 13}  # 14 weeks, one bye
    week3 = min(g["kickoff"] for g in _schedule() if g["week"] == 3)
    later = evidence(as_of=(week3 + timedelta(minutes=1)).isoformat())
    assert later["players"][jefferson]["games"] in (10, 11)


# --- I12: purity and digest ----------------------------------------------------

def test_digest_stable_inside_a_horizon_and_changes_with_the_snapshot():
    first, second = evidence(as_of="2026-09-02T00:00:00+00:00"), evidence(as_of="2026-09-05T00:00:00Z")
    assert first["weeks"] == second["weeks"] and first["as_of"] != second["as_of"]
    assert first["digest"] == second["digest"]
    assert evidence(as_of="2026-09-02T00:00:00+00:00") == first  # a pure function
    changed = captured_snapshot()
    entry = next(e for e in changed["player_week_inputs"] if e["input"].get("stats", {}).get("rec_yd"))
    entry["input"]["stats"]["rec_yd"] = str(float(entry["input"]["stats"]["rec_yd"]) + 10)
    assert evidence(changed, as_of="2026-09-02T00:00:00+00:00")["digest"] != first["digest"]
    assert evidence(run_id="run-2")["digest"] != evidence()["digest"]
    week3 = min(g["kickoff"] for g in _schedule() if g["week"] == 3)
    assert evidence(as_of=(week3 + timedelta(minutes=1)).isoformat())["digest"] != first["digest"]
    payload = {k: v for k, v in first.items() if k not in ("digest", "as_of")}
    assert json.loads(json.dumps(payload)) == payload


# --- unavailable reasons --------------------------------------------------------

def _not_json():
    return "{not json"


@pytest.mark.parametrize("reason,overrides", [
    ("platform_unsupported", {"platform": "espn"}),
    ("no_forecast", {"snapshot": None}),
    ("old_model", {"model_version": "projected-lineup-universal-sd-v4"}),
    ("stale", {"current": False}),
    ("league_changed", {"league_id": "900002"}),
    ("league_changed", {"slots": SLOTS + ["SUPER_FLEX"]}),
    ("no_upcoming_week", {"as_of": "2027-01-15T00:00:00+00:00"}),
    ("read_failed", {"snapshot": {"league_id": LEAGUE_ID, "slots": SLOTS}}),
    ("read_failed", {"snapshot": _not_json()}),
    ("read_failed", {"as_of": "2026-09-02T00:00:00"}),
])
def test_each_unavailable_reason_has_its_own_input(reason, overrides):
    assert evidence()["state"] == "usable"
    if "snapshot" in overrides:
        snapshot = overrides.pop("snapshot")
        result = sv.build_evidence(snapshot, **{**dict(as_of=CAPTURED_AT, league_id=LEAGUE_ID, slots=SLOTS,
                                                       platform="sleeper", model_version=VERSION), **overrides})
    else:
        result = evidence(**overrides)
    assert result == sv.unavailable(reason)


def test_snapshot_json_text_and_slot_order_are_accepted():
    snapshot = captured_snapshot()
    text = evidence(json.dumps(snapshot))
    assert text["state"] == "usable" and text["digest"] == evidence()["digest"]
    assert evidence(slots=list(reversed(SLOTS)))["state"] == "usable"


def test_viewer_unprojected_asset_rule():
    ev, viewer = evidence(), list(ROSTERS["me"])
    # The viewer holds Stefon Diggs (unprojected: no NFL team) worth under 450.
    diggs = BY_NAME["Stefon Diggs"]
    assert diggs in viewer and diggs in ev["unprojected"] and MARKET[diggs] < 450
    assert sv.require_viewer_projected(ev, roster=viewer, position=POSITION, market=MARKET) is ev
    rich = {**MARKET, diggs: 450.0}
    assert sv.require_viewer_projected(ev, roster=viewer, position=POSITION,
                                       market=rich) == sv.unavailable("viewer_unprojected_asset")
    # Injured / reserve players never count; picks are never projected and never count.
    assert sv.require_viewer_projected(ev, roster=viewer, position=POSITION, market=rich, inactive={diggs}) is ev
    assert any(MARKET[pid] >= 450 for pid in viewer if POSITION[pid] == "PICK")
    # Another roster's unprojected player does not make the viewer's lineup unknown.
    other = next(pid for team in LEAGUE["teams"][1:] for pid in team["players"] if pid in ev["unprojected"])
    assert sv.require_viewer_projected(ev, roster=viewer, position=POSITION, market={**MARKET, other: 9000.0}) is ev
    stale = sv.unavailable("stale")
    assert sv.require_viewer_projected(stale, roster=viewer, position=POSITION, market=rich) is stale


def test_unusable_evidence_has_no_profile():
    assert sv.league_profile(sv.unavailable("stale"), rosters=ROSTERS, position=POSITION,
                             market=MARKET, age=AGE) is None
    with pytest.raises(ValueError):
        sv.unavailable("made_up")


# --- labels (PRD §4.3) ------------------------------------------------------------

@pytest.mark.parametrize("name", ["Christian McCaffrey", "Derrick Henry", "Josh Jacobs", "Davante Adams",
                                  "Travis Kelce", "George Kittle"])
def test_label_table_win_now_piece(prof, name):
    assert label_of(prof, name)["label"] == "win_now" and label_of(prof, name)["startable"] is True


@pytest.mark.parametrize("name", ["Justin Jefferson", "Bijan Robinson", "Josh Allen", "Brock Bowers"])
def test_label_table_cornerstone(prof, name):
    item = label_of(prof, name)
    assert item["label"] == "cornerstone" and item["startable"] is True and item["future"] >= sv.FUTURE_FLOOR


def test_label_table_rebuild_piece_and_picks(prof):
    lemon = label_of(prof, "Makai Lemon")
    assert lemon["label"] == "rebuild" and lemon["startable"] is False
    picks = [pid for pid in prof["players"] if POSITION[pid] == "PICK"]
    assert len(picks) == 48
    assert all(prof["players"][pid] == {"label": "rebuild", "future": MARKET[pid], "startable": None} for pid in picks)


@pytest.mark.parametrize("name", ["Patrick Mahomes", "Lamar Jackson"])
def test_label_table_qb_inside_the_band_is_unlabelled(prof, name):
    pid = BY_NAME[name]
    ppg = evidence()["players"][pid]["ppg"]
    assert abs(ppg - prof["line"]["QB"]) < prof["margin"]["QB"]
    assert label_of(prof, name)["label"] is None and label_of(prof, name)["startable"] is None


def test_label_table_depth_is_not_startable_and_not_a_rebuild_piece(prof):
    ev = evidence()
    depth = [pid for pid, item in prof["players"].items() if item["label"] == "depth"]
    assert depth
    for pid in depth:
        pos = POSITION[pid]
        assert ev["players"][pid]["ppg"] <= prof["line"][pos] - prof["margin"][pos] + 1e-9
        assert MARKET[pid] < 450 or not sv.young(pos, AGE[pid])


def test_label_table_rows_follow_the_definitions(prof):
    """Every labelled player, re-derived from the PRD's words."""
    ev = evidence()
    for pid, item in prof["players"].items():
        pos = POSITION[pid]
        if pos == "PICK" or pid not in ev["players"]:
            continue
        ppg, line, margin = ev["players"][pid]["ppg"], prof["line"][pos], prof["margin"][pos]
        future = max(0.0, MARKET[pid] - 400 * max(0.0, ppg - line))
        assert item["future"] == pytest.approx(future, abs=0.01)
        if ppg >= line + margin:
            cliff = AGE[pid] is not None and ((pos == "RB" and AGE[pid] >= 27) or (pos == "WR" and AGE[pid] >= 30)
                                              or (pos == "TE" and AGE[pid] >= 32))
            assert item["label"] == ("win_now" if future < 1500 or cliff else "cornerstone"), pid
        elif ppg <= line - margin:
            young = AGE[pid] is not None and AGE[pid] <= {"QB": 27, "WR": 25, "TE": 25, "RB": 24}[pos]
            assert item["label"] == ("rebuild" if MARKET[pid] >= 450 and young else "depth"), pid
        else:
            assert item["label"] is None, pid


def test_29_year_old_startable_rb_with_future_over_floor_is_win_now(prof):
    barkley = label_of(prof, "Saquon Barkley")
    assert AGE[BY_NAME["Saquon Barkley"]] == 29 and POSITION[BY_NAME["Saquon Barkley"]] == "RB"
    assert barkley["startable"] is True and barkley["future"] >= sv.FUTURE_FLOOR
    assert barkley["label"] == "win_now"
    # The same rule on a synthetic league, well clear of the floor.
    ev = {"state": "usable", "slots": ["RB", "RB"], "players": {"old": {"ppg": 20.0, "games": 4}, "kid": {"ppg": 20.0, "games": 4},
                                                         "a": {"ppg": 10.0, "games": 4}, "b": {"ppg": 5.0, "games": 4}}}
    result = sv.league_profile(ev, rosters={"t1": ["old", "b"], "t2": ["kid", "a"]}, position=dict.fromkeys(["old", "kid", "a", "b"], "RB"),
                               market={"old": 9000.0, "kid": 9000.0, "a": 100.0, "b": 100.0},
                               age={"old": 29, "kid": 25, "a": 30, "b": 30})
    assert result["line"]["RB"] == 5.0 and result["players"]["old"]["future"] == 3000.0
    assert result["players"]["old"]["label"] == "win_now" and result["players"]["kid"]["label"] == "cornerstone"


def test_label_distribution_on_the_fixture(prof):
    """Pinned counts. The planner's prototype reported 36 win-now, 48 cornerstone and 16
    rebuild pieces on the same rosters; differences are explained in the WI-1 report."""
    ev = evidence()
    kinds = Counter()
    for pid, item in prof["players"].items():
        if POSITION[pid] == "PICK":
            continue
        kinds[item["label"] or ("unprojected" if pid not in ev["players"] else "borderline")] += 1
    assert dict(kinds) == {"win_now": 36, "cornerstone": 47, "rebuild": 18, "depth": 136,
                           "borderline": 36, "unprojected": 15}
    assert prof["starters"] == {"QB": 12, "RB": 35, "WR": 46, "TE": 15}
    under_27 = sum(1 for pid, item in prof["players"].items() if item["label"] == "win_now" and AGE[pid] < 27)
    assert under_27 == 16


def test_free_agent_level_reads_v6_rows():
    base = evidence()["free_agent_level"]
    if not season_points.free_agent_points(captured_snapshot()):  # a v5 snapshot has no free agents
        assert base == {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0}
    snapshot = captured_snapshot()
    rb = BY_NAME["Josh Jacobs"]
    for entry in [e for e in snapshot["player_week_inputs"] if e["player_id"] == rb]:
        fa = deepcopy(entry)
        fa.update(player_id="fa-rb", free_agent=True)
        snapshot["player_week_inputs"].append(fa)
    ev = evidence(snapshot)
    assert ev["players"][rb]["ppg"] > base["RB"]
    assert ev["free_agent_level"] == {**base, "RB": ev["players"][rb]["ppg"]}
    assert "fa-rb" not in ev["players"] and "fa-rb" not in ev["unprojected"]


# --- conflict predicate (PRD §5.1) -------------------------------------------------

def conflict(**kwargs):
    base = dict(plan="championship", declared=True, usable_evidence=True)
    return sv.plan_conflict(**{**base, **kwargs})


def test_conflict_predicate_all_in_and_contending_thresholds():
    assert conflict(delta_pts_week=-0.5) and conflict(delta_pts_week=-1.82)
    assert not conflict(delta_pts_week=-0.49) and not conflict(delta_pts_week=0.0)
    assert conflict(plan="contender", delta_pts_week=-1.0)
    assert not conflict(plan="contender", delta_pts_week=-0.6)
    assert not conflict(plan="contender", delta_pts_week=-0.99)
    assert not conflict(delta_pts_week=None)


def test_conflict_predicate_never_without_a_saved_plan_or_usable_evidence_or_when_pinned():
    for plan in ("not_sure", None):
        assert not conflict(plan=plan, delta_pts_week=-9.0)
    assert not conflict(declared=False, delta_pts_week=-9.0)
    assert not conflict(usable_evidence=False, delta_pts_week=-9.0)
    assert not conflict(pinned=True, delta_pts_week=-9.0)


@pytest.mark.parametrize("plan", ["rebuilder", "jets"])
def test_conflict_predicate_rebuilding_mirror(prof, plan):
    cmc, lemon, jefferson = BY_NAME["Christian McCaffrey"], BY_NAME["Makai Lemon"], BY_NAME["Justin Jefferson"]
    jacobs, mahomes = BY_NAME["Josh Jacobs"], BY_NAME["Patrick Mahomes"]
    pick = next(pid for pid in ROSTERS["me"] if POSITION[pid] == "PICK")
    mirror = lambda receive, give, **kw: conflict(plan=plan, receive=receive, give=give, profile=prof, market=MARKET, **kw)
    assert mirror([cmc], [lemon])                     # win-now piece for a rebuild piece
    assert mirror([cmc], [pick])                      # ... or for a pick
    assert mirror([cmc], [jefferson])                 # ... or for a cornerstone
    assert not mirror([lemon], [cmc])                 # receives a rebuild piece
    assert not mirror([cmc], [jacobs])                # gives only a win-now piece
    assert not mirror([cmc, jefferson], [lemon])      # the most valuable incoming is a cornerstone
    assert not mirror([cmc], [mahomes])               # gives an unlabelled (borderline) player
    assert mirror([cmc], [lemon], delta_pts_week=5.0)  # the points do not matter for the mirror
    assert not mirror([cmc], [lemon], declared=False)
    # Less future must come back than goes out.
    rich = {**MARKET, cmc: 20000.0}
    rich_prof = sv.league_profile(evidence(), rosters=ROSTERS, position=POSITION, market=rich, age=AGE)
    assert rich_prof["players"][cmc]["label"] == "win_now"
    assert not conflict(plan=plan, receive=[cmc], give=[lemon], profile=rich_prof, market=rich)
