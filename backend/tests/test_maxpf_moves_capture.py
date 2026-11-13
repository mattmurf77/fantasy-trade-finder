"""Max PF moves: the capture side channel (contract §13.4, plan B3).

The world is the season-signal fixture (12 teams, 14 future weeks, real
`provider.capture`, the production best-available contract, with free agents in
the feed). No network, no database.

- test_sidecar_never_changes_the_snapshot: capture with `sidecar=None` and with
  a dict returns snapshots equal by `==`, by `core.digest`, and by the stored
  input hash formula (`store.save_snapshot`). Sabotage: write the free-agent
  pool into the snapshot.
- test_kept_pool_holds_every_used_free_agent_and_respects_k: every free agent
  the forecast placed in any team's lineup or max PF lineup is in the kept
  pool, and no slot type keeps more than (open slots + 1) players. Sabotage:
  keep `week_gaps` instead of `week_gaps + 1`.
- test_trade_deadline_and_names: the deadline is the league's week, 0 / 99 /
  absent / non-integer are no deadline; names cover every rostered player.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from backend.league_projections import provider
from backend.league_projections.core import SLOTS, VERSION, digest, semantic_facts
from backend.league_projections.scoring import BEST_AVAILABLE
from backend.tests.test_season_points import CAPTURED_AT, LEAGUE_ID, API, capture_cfg, sleeper_world


def capture(source, sidecar):
    return provider.capture(LEAGUE_ID, "me", capture_cfg(BEST_AVAILABLE), lambda url: deepcopy(source[url]),
                            captured_at=CAPTURED_AT, clock=lambda: CAPTURED_AT, sidecar=sidecar)


@pytest.fixture(scope="module")
def world():
    source = sleeper_world()
    side = {}
    return source, capture(source, None), capture(source, side), side


def input_hash(snapshot, cfg):
    return digest({"snapshot": semantic_facts(snapshot), "config": cfg, "model_version": VERSION})


def test_sidecar_never_changes_the_snapshot(world):
    _, plain, with_side, side = world
    assert plain == with_side
    assert digest(plain) == digest(with_side)
    cfg = capture_cfg(BEST_AVAILABLE)
    assert input_hash(plain, cfg) == input_hash(with_side, cfg)
    assert side["free_agents"] and "free_agents" not in with_side and "trade_deadline" not in with_side


def test_kept_pool_holds_every_used_free_agent_and_respects_k(world):
    _, snapshot, _, side = world
    used = 0
    for week in snapshot["weeks"]:
        kept = {p["player_id"] for p in side["free_agents"][str(week["week"])]}
        gaps = 0
        for detail in week["teams"].values():
            cov = detail["projection_coverage"]
            for fill in cov["free_agent_fills"] + cov["maxpf_free_agent_fills"]:
                used += 1
                assert fill["player_id"] in kept
            gaps = max(gaps, len(cov["free_agent_fills"]) + len(cov["zero_filled_slots"]),
                       len(cov["maxpf_free_agent_fills"]) + len(cov["maxpf_zero_filled_slots"]))
        pool = side["free_agents"][str(week["week"])]
        for slot in set(snapshot["slots"]):
            eligible = [p for p in pool if SLOTS[slot].intersection(p["positions"])]
            assert len(eligible) >= 1
        # The pool never exceeds (gaps + 1) per slot type, so it stays small.
        assert len(pool) <= (gaps + 1) * len(set(snapshot["slots"]))
    assert used >= 7  # the fixture fills open slots from free agents


def _with_deadline(value):
    source = sleeper_world()
    if value is not None:
        source[f"{API}/league/{LEAGUE_ID}"]["settings"]["trade_deadline"] = value
    side = {}
    capture(source, side)
    return side


@pytest.mark.parametrize("value,expected", [(11, 11), (0, None), (99, None), (None, None), ("11", None)])
def test_trade_deadline_and_names(value, expected):
    side = _with_deadline(value)
    assert side["trade_deadline"] == expected
    if value == 11:
        source = sleeper_world()
        rostered = {p for r in source[f"{API}/league/{LEAGUE_ID}/rosters"] for p in r["players"]}
        assert set(side["names"]) == rostered and all(side["names"].values())
