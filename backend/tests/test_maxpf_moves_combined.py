"""Max PF moves v1.1: combined entries, rows served in every list state, and the
settings-hash re-run (D-261; contract v1.1 note, §3.7, §13.1).

Same worlds as test_maxpf_moves (the season-signal fixture and hand-built
snapshots), the read through `compose` and the route, the job through the real
worker. No network.

- test_together_is_the_exact_resolve_not_the_sum: on the worked example, Sato
  and Pike removed together drop max PF by 91, not 31 + 16 = 47: both needed
  the one bench back. Sabotage: sum the single drops in `resolve_together`.
- test_fixture_combined_entries: the top 2 and top 3 rows, in rank order;
  each `maxpf_change_exact` equals an independent `resolve_together`; never
  smaller in magnitude than the largest member's drop; the size-3 drop at least
  the size-2 drop; valid probabilities; the paired re-run is shared with the
  rows (same seed, so a candidate set of one reproduces that row exactly).
- test_sizes_are_skipped_when_rows_are_fewer.
- test_failure_or_cancellation_keeps_the_rows: `_combined` raising, and a
  cancel hit inside the combined simulations, both save the rows exactly as
  without the step and no `combined` key. Sabotage: drop the try in `compute`.
- test_job_time_budget_in_the_combined_step_keeps_the_rows (worker level).
- test_read_serves_combined_with_values_and_keep; test_combined_never_decides
  the state; test_rows_are_served_in_no_moves; test_old_block_reads_as_v1.
- test_v1_keys_unchanged: the served block still has every key of the v1
  golden (backend/tests/fixtures/maxpf_moves/v1-example.json, the §5.1
  example before v1.1) with the same JSON types, `version` 1, and adds only
  `combined` at the top level. Sabotage: rename a row key.
- test_settings_hash_moves_with_this_release.
- test_moves_missing_flags_an_old_hash_block; end to end: a baseline saved
  under the pre-v1.1 settings is re-run by `retry_missing_moves` and its new
  block has `combined`.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from backend import database as db
from backend.league_projections import batch, maxpf_moves, provider, service, simulation, store
from backend.league_projections.core import Unavailable, VERSION
from backend.tests.test_league_projection_batch import scheduled  # noqa: F401  (fixture)
from backend.tests.test_maxpf_moves import (EXAMPLE, EXAMPLE_SLOTS, HAND_CFG, OPTIONS, _block, _result, _world,
                                            hand_snapshot, result, world)
from backend.tests.test_maxpf_moves_read import _merge_nullable, _types, compose, saved_run
from backend.tests.test_outlook_calibration_persistence import engine  # noqa: F401  (fixture)
from backend.tests.test_season_points import CAPTURED_AT, LEAGUE_ID, sleeper_world

REPO = Path(__file__).resolve().parents[2]
V1 = {k: v for k, v in OPTIONS.items() if k != "combined_sizes"}


# ── the re-solve ────────────────────────────────────────────────────────

def test_together_is_the_exact_resolve_not_the_sum():
    snap, names = hand_snapshot(EXAMPLE_SLOTS, EXAMPLE)
    solved = maxpf_moves.resolve(snap, HAND_CFG, {}, 1, names=names)
    c = solved["candidates"]
    assert (c["sato"]["dM"], c["pike"]["dM"]) == (31, 16)
    together = maxpf_moves.resolve_together(solved, 1, ["sato", "pike"])
    # Weeks 10, 11, 13, 14: 15 + 12 lost, Mercer (10) is the only back left -> 17.
    # Week 12 (Okafor's bye): Mercer was the flex; Quill (4) takes it -> 23.
    assert [together["changes"][w][1] for w in (10, 11, 12, 13, 14)] == [17, 17, 23, 17, 17]
    assert together["dM"] == 91 != c["sato"]["dM"] + c["pike"]["dM"]
    assert together["dM"] >= max(c["sato"]["dM"], c["pike"]["dM"])
    assert maxpf_moves.resolve_together(solved, 1, ["sato"])["dM"] == c["sato"]["dM"]


# ── the saved entries ───────────────────────────────────────────────────

def test_fixture_combined_entries():
    block = deepcopy(_block())
    rows, combined = block["rows"], block["combined"]
    assert [e["size"] for e in combined] == [2, 3]
    snap, side = world()
    solved = maxpf_moves.resolve(snap, result()["config"], side["free_agents"], block["viewer_roster_id"], names=side["names"])
    previous = None
    for entry in combined:
        members = rows[:entry["size"]]
        assert entry["player_ids"] == [r["player_id"] for r in members]
        assert entry["names"] == [r["name"] for r in members] and entry["short_names"] == [r["short_name"] for r in members]
        exact = -maxpf_moves.resolve_together(solved, block["viewer_roster_id"], entry["player_ids"])["dM"]
        assert Decimal(entry["maxpf_change_exact"]) == exact.quantize(Decimal("0.01"))
        assert entry["maxpf_change"] == maxpf_moves._whole(exact) < 0
        assert -Decimal(entry["maxpf_change_exact"]) >= max(-Decimal(r["maxpf_change_exact"]) for r in members)
        assert previous is None or Decimal(entry["maxpf_change_exact"]) <= previous
        previous = Decimal(entry["maxpf_change_exact"])
        assert 0 <= entry["playoff_probability"]["after"] <= 1 and 0 <= entry["top3_probability"]["after"] <= 1
        assert entry["playoff_probability"]["now"] == rows[0]["playoff_probability"]["now"]
        assert entry["pick_if_miss"]["now"] == rows[0]["pick_if_miss"]["now"]
        assert abs(sum(entry["after_pick_probabilities"]) - (1 - entry["after_playoff_probability"])) < 1e-9
        assert entry["label"]["now"] == block["baseline"]["label"]
        assert isinstance(entry["passes_threshold"], bool)
        assert set(entry) == set(maxpf_moves._COMBINED_KEYS) | {"after_pick_probabilities", "after_playoff_probability"}
    print("combined on the fixture:", [(e["size"], e["maxpf_change_exact"], e["pick_if_miss"], e["passes_threshold"])
                                       for e in combined])


def test_sizes_are_skipped_when_rows_are_fewer():
    snap, side = world()
    two = maxpf_moves.compute(snap, result(), side["free_agents"], {**OPTIONS, "candidates": 2, "simulations_per_candidate": 1000})
    assert [e["size"] for e in two["combined"]] == [2]
    one = maxpf_moves.compute(snap, result(), side["free_agents"], {**OPTIONS, "candidates": 1, "simulations_per_candidate": 1000})
    assert len(one["rows"]) == 1 and "combined" not in one
    off = maxpf_moves.compute(snap, result(), side["free_agents"], {**OPTIONS, "combined_sizes": [], "simulations_per_candidate": 1000})
    assert "combined" not in off and len(off["rows"]) == 8


def test_failure_or_cancellation_keeps_the_rows(monkeypatch):
    snap, side = world()
    expected = {k: v for k, v in deepcopy(_block()).items() if k != "combined"}
    monkeypatch.setattr(maxpf_moves, "_combined", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    failed = maxpf_moves.compute(snap, result(), side["free_agents"], OPTIONS, names=side["names"])
    assert failed == expected
    monkeypatch.undo()
    stop = []
    real = maxpf_moves.resolve_together
    monkeypatch.setattr(maxpf_moves, "resolve_together", lambda *a, **k: stop.append(1) or real(*a, **k))
    cancelled = maxpf_moves.compute(snap, result(), side["free_agents"], OPTIONS, names=side["names"],
                                    cancelled=lambda: bool(stop))
    assert stop and cancelled == expected


# ── the job ─────────────────────────────────────────────────────────────

def _job_world(engine, monkeypatch, flags):  # noqa: F811
    for module in (batch, service):
        monkeypatch.setattr(module, "is_enabled", lambda key: flags.get(key, False))
    real = batch.settings()
    options = {**real, "policy_approved": True, "model": {**real["model"], "iterations": 5000}}
    monkeypatch.setattr(batch, "settings", lambda: options)
    monkeypatch.setattr(service, "_viewer_identity", lambda uid: "me")
    monkeypatch.setattr(service, "wake", lambda *a, **kw: None)
    source = sleeper_world()
    real_capture = provider.capture
    monkeypatch.setattr(provider, "capture", lambda league_id, league_user_id, cfg, fetch_json, **kw: real_capture(
        league_id, league_user_id, cfg, lambda url: deepcopy(source[url]), captured_at=CAPTURED_AT, clock=lambda: CAPTURED_AT, **kw))
    batch.register("account", LEAGUE_ID, "me", 2026)
    with engine.begin() as conn:
        conn.execute(db.league_projection_targets_table.update().values(next_due_at="2020-01-01T00:00:00+00:00"))


def _latest():
    item = batch.target("account", LEAGUE_ID)
    return item, store.get(item["last_success_id"], "account", LEAGUE_ID)


def _enqueue_only(*a):
    pytest.fail("enqueue only")


def test_job_time_budget_in_the_combined_step_keeps_the_rows(engine, monkeypatch):  # noqa: F811
    flags = {"league.projections": True, "league.projections_provider_approved": True, "league.max_pf_moves": True}
    _job_world(engine, monkeypatch, flags)
    clock = [1000.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    real = maxpf_moves.resolve_together

    def late(*args, **kwargs):
        clock[0] += 10_000  # past the 60 s budget by the first combined checkpoint
        return real(*args, **kwargs)
    monkeypatch.setattr(maxpf_moves, "resolve_together", late)
    assert batch.dispatch(_enqueue_only)["queued"] == 1
    service._run(lambda url: pytest.fail("no network"))
    _, row = _latest()
    block = json.loads(row["result_json"])["max_pf_moves"]
    assert block["computed"] and len(block["rows"]) == 8 and "combined" not in block
    assert block["settings_hash"] == maxpf_moves.settings_hash(maxpf_moves.settings())


def test_old_hash_block_is_rerun_end_to_end(engine, monkeypatch):  # noqa: F811
    flags = {"league.projections": True, "league.projections_provider_approved": True, "league.max_pf_moves": True}
    _job_world(engine, monkeypatch, flags)
    # A block saved under the v1 settings (no combined_sizes).
    current = maxpf_moves.settings
    monkeypatch.setattr(maxpf_moves, "settings", lambda: {k: v for k, v in current().items() if k != "combined_sizes"})
    assert batch.dispatch(_enqueue_only)["queued"] == 1
    service._run(lambda url: pytest.fail("no network"))
    _, before = _latest()
    old = json.loads(before["result_json"])["max_pf_moves"]
    assert old["computed"] and "combined" not in old
    assert batch.dispatch(_enqueue_only, retry_missing_moves=True)["retried_missing_moves"] == 0, "current under v1 settings"
    monkeypatch.setattr(maxpf_moves, "settings", current)  # this release
    assert batch._moves_missing(before["result_json"])
    out = batch.dispatch(_enqueue_only, retry_missing_moves=True)
    assert (out["queued"], out["retried_missing_moves"]) == (1, 1)
    service._run(lambda url: pytest.fail("no network"))
    _, after = _latest()
    result_ = json.loads(after["result_json"])
    assert after["run_id"] != before["run_id"] and result_["reused_compatible_result"]
    new = result_["max_pf_moves"]
    assert [e["size"] for e in new["combined"]] == [2, 3]
    assert new["settings_hash"] == maxpf_moves.settings_hash(current()) != old["settings_hash"]
    assert [r["player_id"] for r in new["rows"]] == [r["player_id"] for r in old["rows"]]
    assert batch.dispatch(_enqueue_only, retry_missing_moves=True)["retried_missing_moves"] == 0, "Converged"


# ── the read ────────────────────────────────────────────────────────────

def test_read_serves_combined_with_values_and_keep():
    saved = saved_run()
    raw = saved["max_pf_moves"]
    keep = raw["rows"][1]["player_id"]  # in both entries
    out = compose(saved, untouchables=[keep], price=lambda dist: round(1000 * dist[0] + 500, 1))
    assert out["state"] == "ready" and [e["size"] for e in out["combined"]] == [2, 3]
    for served, entry in zip(out["combined"], raw["combined"]):
        assert set(served) == set(maxpf_moves._COMBINED_KEYS) | {"pick_value", "keep"}
        assert served["keep"] is True
        after = round(1000 * entry["after_pick_probabilities"][0] + 500, 1)
        assert served["pick_value"]["after"] == after and served["pick_value"]["change"] == round(after - served["pick_value"]["now"], 1)
        assert all(served[k] == entry[k] for k in maxpf_moves._COMBINED_KEYS)
    assert [e["keep"] for e in compose(saved)["combined"]] == [False, False]
    assert all(e["pick_value"] is None for e in compose(saved)["combined"])
    assert "after_pick_probabilities" not in json.dumps(out)


def test_combined_never_decides_the_state():
    saved = saved_run()
    raw = saved["max_pf_moves"]
    flat = {**saved, "max_pf_moves": {**raw, "rows": [dict(r, passes_threshold=False) for r in raw["rows"]],
                                      "combined": [dict(e, passes_threshold=True) for e in raw["combined"]]}}
    out = compose(flat)
    assert out["state"] == "no_moves" and len(out["combined"]) == 2 and all(e["passes_threshold"] for e in out["combined"])
    for rule in ("reverse_standings", "lottery_or_other"):
        assert compose(saved, draft_order={"rule": rule, "set_at": "x"})["combined"] == []


def test_rows_are_served_in_no_moves():
    saved = saved_run()
    raw = saved["max_pf_moves"]
    flat = {**saved, "max_pf_moves": {**raw, "rows": [dict(r, passes_threshold=False) for r in raw["rows"]]}}
    out = compose(flat)
    assert out["state"] == "no_moves" and [r["player_id"] for r in out["rows"]] == [r["player_id"] for r in raw["rows"]]
    assert all(r["passes_threshold"] is False for r in out["rows"])


def test_old_block_reads_as_v1():
    saved = saved_run()
    old = {**saved, "max_pf_moves": {k: v for k, v in saved["max_pf_moves"].items() if k != "combined"}}
    new_out, old_out = compose(saved), compose(old)
    assert old_out["combined"] == [] and old_out["version"] == 1
    assert {k: v for k, v in old_out.items() if k != "combined"} == {k: v for k, v in new_out.items() if k != "combined"}


def test_v1_keys_unchanged():
    golden = json.loads((REPO / "backend/tests/fixtures/maxpf_moves/v1-example.json").read_text())["max_pf_moves"]
    out = compose(saved_run(), price=lambda dist: 1000.0)
    assert out["version"] == 1 == maxpf_moves.VERSION
    assert set(out) - set(golden) == {"combined"}
    _merge_nullable(_types(golden), _types({k: v for k, v in out.items() if k != "combined"}))


# ── settings ────────────────────────────────────────────────────────────

def test_settings_hash_moves_with_this_release():
    now = maxpf_moves.settings()
    assert now["combined_sizes"] == [2, 3]
    v1 = {k: v for k, v in now.items() if k != "combined_sizes"}
    assert maxpf_moves.settings_hash(now) != maxpf_moves.settings_hash(v1)


def test_moves_missing_flags_an_old_hash_block():
    current = maxpf_moves.settings_hash(maxpf_moves.settings())
    block = {"version": 1, "computed": True, "rows": []}
    assert batch._moves_missing(json.dumps({"max_pf_moves": {**block, "settings_hash": current}})) is False
    assert batch._moves_missing(json.dumps({"max_pf_moves": {**block, "settings_hash": maxpf_moves.settings_hash(V1)}}))
    assert batch._moves_missing(json.dumps({"max_pf_moves": block}))  # no hash at all
    assert batch._moves_missing(json.dumps({"max_pf_moves": {"computed": False, "reason": "not_eligible",
                                                             "settings_hash": "old"}})) is False
