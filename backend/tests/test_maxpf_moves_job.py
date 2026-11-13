"""Max PF moves: the weekly-job hook (contract §8, §13.5; plan B4).

The real worker (`service._run`) on an in-memory database, the real
`provider.capture` over the season-signal fixture (12 teams, 14 weeks) and the
real simulation at 5,000 runs. No network.

- test_flag_off_saves_exactly_what_main_saves: with the flag off the stored
  `result_json`, `snapshot_json` and `input_hash` are byte-identical to a run
  with capture called the way main calls it (no `sidecar` keyword) and
  `maxpf_moves` never imported into the run: `compute` and `settings` are
  never called. Sabotage: drop the flag check (moves always on).
- test_flag_on_adds_only_the_block: with the flag on, `result_json` has the
  block and every other key equal to the flag-off run, and `snapshot_json` /
  `input_hash` are unchanged. Records the step's cost (`elapsed_ms`).
- test_exception_leaves_the_forecast_intact: `compute` raising leaves a
  complete run with no block. Sabotage: let the wrapper re-raise.
- test_time_budget_leaves_the_forecast_intact: a budget hit stops the step at
  the next simulation checkpoint; the run completes with no block. Sabotage:
  ignore the budget in the step's cancel hook.
- test_scenario_runs_never_get_a_block.
- test_prior_reuse_recomputes_only_on_a_settings_change; and with the flag
  off a reused block is dropped from the saved result.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest
from sqlalchemy import update

from backend import database as db
from backend.league_projections import batch, clinch, maxpf_moves, provider, service, simulation, store
from backend.league_projections.scoring import BEST_AVAILABLE
from backend.tests.test_outlook_calibration_persistence import engine  # noqa: F401  (fixture)
from backend.tests.test_season_points import CAPTURED_AT, LEAGUE_ID, sleeper_world

SOURCE = sleeper_world()
REAL_CAPTURE = provider.capture
REAL_SETTINGS = batch.settings


def model_cfg():
    return simulation.config({**REAL_SETTINGS()["model"], "draft_season": 2027, "iterations": 5000})


@pytest.fixture
def world(engine, monkeypatch):  # noqa: F811
    flags = {"league.projections": True, "league.projections_provider_approved": True, "league.max_pf_moves": False}
    monkeypatch.setattr(service, "is_enabled", lambda key: flags.get(key, False))
    monkeypatch.setattr(batch, "settings", lambda: {"policy_approved": True, "retention_days": 7})
    monkeypatch.setattr(service, "_viewer_identity", lambda uid: "me")
    calls = []

    def capture(league_id, league_user_id, cfg, fetch_json, **kwargs):
        calls.append(sorted(kwargs))
        return REAL_CAPTURE(league_id, league_user_id, cfg, lambda url: deepcopy(SOURCE[url]),
                            captured_at=CAPTURED_AT, clock=lambda: CAPTURED_AT, **kwargs)
    monkeypatch.setattr(provider, "capture", capture)
    return flags, calls


def make_job(kind="baseline"):
    cfg = model_cfg()
    row = store.create("account", LEAGUE_ID, {"kind": "scenario", "league_user_id": "me", "config": cfg})
    inputs = {**json.loads(row["input_json"]), "kind": kind, "target_id": "t1"}
    with db.engine.begin() as conn:
        conn.execute(update(db.league_projection_runs_table).where(
            db.league_projection_runs_table.c.run_id == row["run_id"]).values(input_json=json.dumps(inputs)))
    return row["run_id"]


def run_job(kind="baseline", keep=False):
    run_id = make_job(kind)
    service._run(lambda url: pytest.fail("no network"))
    row = store.get(run_id, "account", LEAGUE_ID)
    assert row["status"] == "complete", (row["status"], row["reason"])
    if keep:  # left for the next job's prior-result reuse
        return row
    with db.engine.begin() as conn:  # no prior result for the next job
        conn.execute(db.league_projection_runs_table.delete().where(db.league_projection_runs_table.c.run_id == run_id))
    return row


def test_flag_off_saves_exactly_what_main_saves(world, monkeypatch):
    flags, calls = world
    monkeypatch.setattr(maxpf_moves, "compute", lambda *a, **k: pytest.fail("flag off: no moves work"))
    monkeypatch.setattr(maxpf_moves, "settings", lambda: pytest.fail("flag off: settings never read"))
    off = run_job()
    assert calls == [["viewer_user_id"]]  # capture called exactly as on main
    result = json.loads(off["result_json"])
    assert "max_pf_moves" not in result
    # The pre-change worker's result: simulate on the same capture, plus the two keys _run adds,
    # plus the D-262 clinch proof (`clinch.attach`, flag-independent: every run carries it).
    snapshot = json.loads(off["snapshot_json"])
    main = clinch.attach({**simulation.simulate(snapshot, model_cfg()), "reused_compatible_result": False,
                          "verified_at": snapshot["captured_at"]}, snapshot)
    assert off["result_json"] == store.dumps(main)
    assert snapshot == REAL_CAPTURE(LEAGUE_ID, "me", model_cfg(), lambda url: deepcopy(SOURCE[url]),
                                    captured_at=CAPTURED_AT, clock=lambda: CAPTURED_AT)


@pytest.fixture
def both(world):
    flags, calls = world
    off = run_job()
    flags["league.max_pf_moves"] = True
    on = run_job()
    return off, on, calls


def test_flag_on_adds_only_the_block(both):
    off, on, calls = both
    assert calls == [["viewer_user_id"], ["sidecar", "viewer_user_id"]]
    assert on["snapshot_json"] == off["snapshot_json"] and on["input_hash"] == off["input_hash"]
    r_off, r_on = json.loads(off["result_json"]), json.loads(on["result_json"])
    block = r_on.pop("max_pf_moves")
    assert r_on == r_off and r_on["model_version"] == r_off["model_version"]
    assert block["computed"] and len(block["rows"]) == 8 and block["elapsed_ms"] > 0
    assert block["settings_hash"] == maxpf_moves.settings_hash(maxpf_moves.settings())
    print(f"max_pf_moves step on the fixture: {block['elapsed_ms']} ms, {len(json.dumps(block))} bytes")


def test_exception_leaves_the_forecast_intact(world, monkeypatch):
    flags, _ = world
    flags["league.max_pf_moves"] = True
    monkeypatch.setattr(maxpf_moves, "compute", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    row = run_job()
    result = json.loads(row["result_json"])
    assert "max_pf_moves" not in result and result["status"] == "complete" and result["teams"]


def test_time_budget_leaves_the_forecast_intact(world, monkeypatch):
    flags, _ = world
    flags["league.max_pf_moves"] = True
    real = maxpf_moves.settings
    monkeypatch.setattr(maxpf_moves, "settings", lambda: {**real(), "time_budget_seconds": 1})
    clock = [1000.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    seen = []
    real_compute = maxpf_moves.compute

    def slow(*args, cancelled, **kwargs):
        clock[0] += 5  # the budget has passed by the first checkpoint
        seen.append(1)
        return real_compute(*args, cancelled=cancelled, **kwargs)
    monkeypatch.setattr(maxpf_moves, "compute", slow)
    row = run_job()
    assert seen and "max_pf_moves" not in json.loads(row["result_json"])


def test_scenario_runs_never_get_a_block(world):
    flags, calls = world
    flags["league.max_pf_moves"] = True
    row = run_job(kind="scenario")
    assert calls == [["viewer_user_id"]] and "max_pf_moves" not in json.loads(row["result_json"])


def test_prior_reuse_recomputes_only_on_a_settings_change(world, monkeypatch):
    flags, _ = world
    flags["league.max_pf_moves"] = True
    first = json.loads(run_job(keep=True)["result_json"])
    # Same inputs again: the prior result is reused (it already has a block).
    counted = []
    real_compute = maxpf_moves.compute
    monkeypatch.setattr(maxpf_moves, "compute", lambda *a, **k: counted.append(1) or real_compute(*a, **k))
    keep = run_job(keep=True)
    second = json.loads(keep["result_json"])
    assert second["reused_compatible_result"] and counted == []
    assert second["max_pf_moves"] == first["max_pf_moves"]
    # A settings change recomputes.
    real = maxpf_moves.settings
    monkeypatch.setattr(maxpf_moves, "settings", lambda: {**real(), "candidates": 2})
    third = json.loads(run_job(keep=True)["result_json"])
    assert counted == [1] and len(third["max_pf_moves"]["rows"]) == 2
    # Flag off: the reused block is dropped from the saved result.
    flags["league.max_pf_moves"] = False
    fourth = json.loads(run_job()["result_json"])
    assert fourth["reused_compatible_result"] and "max_pf_moves" not in fourth


def test_reused_prior_result_saved_before_d262_gets_the_clinch_keys(world):
    """D-262: a prior result saved without the proof (an older run) gains
    `playoff_clinched` / `playoff_eliminated` on reuse; no probability moves.
    Sabotage: attach only on a fresh simulation (`if not prior`)."""
    first = run_job(keep=True)
    old = json.loads(first["result_json"])
    stripped = {k: v for k, v in old.items() if k != "playoff_proof"}
    stripped["teams"] = [{k: v for k, v in t.items() if k not in ("playoff_clinched", "playoff_eliminated")}
                         for t in old["teams"]]
    with db.engine.begin() as conn:
        conn.execute(update(db.league_projection_runs_table).where(
            db.league_projection_runs_table.c.run_id == first["run_id"]).values(result_json=store.dumps(stripped)))
    second = json.loads(run_job()["result_json"])
    assert second["reused_compatible_result"]
    assert second["playoff_proof"] == old["playoff_proof"] and second["playoff_proof"]["status"] == "exact"
    assert [(t["playoff_clinched"], t["playoff_eliminated"]) for t in second["teams"]] == \
        [(t["playoff_clinched"], t["playoff_eliminated"]) for t in old["teams"]]
    assert [t["playoff_probability"] for t in second["teams"]] == [t["playoff_probability"] for t in old["teams"]]
