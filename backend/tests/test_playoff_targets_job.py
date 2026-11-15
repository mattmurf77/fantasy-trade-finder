"""Playoff targets: the weekly-job hook (contract §6.4, §6.5, §8).

The real worker (`service._run`) on an in-memory database, the real
`provider.capture` over the season-signal fixture (12 teams, 14 weeks) and the
real simulation at 5,000 runs, as test_maxpf_moves_job. No network.

- test_flag_off_does_no_work: with the flag off there is no block, `compute`,
  `settings` and the outlook read are never called, and capture is called the
  way main calls it. Sabotage: drop the flag check (targets always on).
- test_flag_on_adds_only_the_block: `result_json` gains the block and every
  other key equals the flag-off run; `snapshot_json` and `input_hash` are
  unchanged. Prints the step's cost on the fixture (`elapsed_ms`).
- test_both_flags_save_both_blocks_and_max_pf_moves_is_unchanged: the Max PF
  moves block is byte-identical with and without this feature.
- test_the_job_reads_saved_outlooks_by_roster_owner: a saved Rebuilding
  outlook for a strong team's owner, and a Tanking one for another team's
  co-owner, make both teams sellers; a Contender one does not. Sabotage: pass
  no outlooks to `compute`.
- test_exception_leaves_the_forecast_intact. Sabotage: let the wrapper re-raise.
- test_time_budget_leaves_the_forecast_intact. Sabotage: ignore the budget.
- test_scenario_runs_never_get_a_block.
- test_prior_reuse_recomputes_on_a_settings_or_seller_change; and with the
  flag off a reused block is dropped from the saved result.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest
from sqlalchemy import update

from backend import database as db
from backend.league_projections import batch, maxpf_moves, playoff_targets, provider, service, simulation, store
from backend.tests.test_outlook_calibration_persistence import engine  # noqa: F401  (fixture)
from backend.tests.test_season_points import API, CAPTURED_AT, LEAGUE_ID, sleeper_world

SOURCE = sleeper_world()
REAL_CAPTURE = provider.capture
REAL_SETTINGS = batch.settings
OWNERS = {r["roster_id"]: r["owner_id"] for r in SOURCE[f"{API}/league/{LEAGUE_ID}/rosters"]}


def model_cfg():
    return simulation.config({**REAL_SETTINGS()["model"], "draft_season": 2027, "iterations": 5000})


@pytest.fixture
def world(engine, monkeypatch):  # noqa: F811
    flags = {"league.projections": True, "league.projections_provider_approved": True,
             "league.max_pf_moves": False, "league.playoff_targets": False}
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
    row = store.create("account", LEAGUE_ID, {"kind": "scenario", "league_user_id": "me", "config": model_cfg()})
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
    if not keep:  # no prior result for the next job
        with db.engine.begin() as conn:
            conn.execute(db.league_projection_runs_table.delete().where(db.league_projection_runs_table.c.run_id == run_id))
    return row


def fast(monkeypatch, **changes):
    """The shipped settings with a smaller search, so a job takes about two seconds."""
    real = playoff_targets.settings()
    options = {**real, "simulations_per_candidate": 500, "candidates": 2, **changes}
    monkeypatch.setattr(playoff_targets, "settings", lambda: options)
    return options


def test_flag_off_does_no_work(world, monkeypatch):
    _, calls = world
    for name in ("compute", "settings"):
        monkeypatch.setattr(playoff_targets, name, lambda *a, **k: pytest.fail("flag off: no targets work"))
    monkeypatch.setattr(service, "_seller_outlooks", lambda *a: pytest.fail("flag off: no outlook read"))
    off = run_job()
    assert calls == [["viewer_user_id"]]  # capture called exactly as on main
    assert "playoff_targets" not in json.loads(off["result_json"])


def test_flag_on_adds_only_the_block(world):
    flags, calls = world
    off = run_job()
    flags["league.playoff_targets"] = True
    on = run_job()
    assert calls == [["viewer_user_id"], ["sidecar", "viewer_user_id"]]
    assert on["snapshot_json"] == off["snapshot_json"] and on["input_hash"] == off["input_hash"]
    r_off, r_on = json.loads(off["result_json"]), json.loads(on["result_json"])
    block = r_on.pop("playoff_targets")
    assert r_on == r_off and "max_pf_moves" not in r_on
    assert block["computed"] and block["elapsed_ms"] > 0
    assert block["settings_hash"] == playoff_targets.settings_hash(playoff_targets.settings())
    # The fixture's viewer (roster 1) sits at 88%: six teams under 50%, every one with its owner id.
    assert sorted(int(rid) for rid, s in block["sellers"].items() if s["eligible"]) == [2, 4, 5, 8, 9, 12]
    assert all(s["owner_ids"] == [OWNERS[int(rid)]] for rid, s in block["sellers"].items())
    assert block["rows"] and block["pool_size"] == 6 * 24
    print(f"playoff_targets step on the fixture: {block['elapsed_ms']} ms, {len(json.dumps(block))} bytes, "
          f"{block['pool_size']} players checked, {block['candidates_total']} candidates, {len(block['rows'])} rows")


def test_both_flags_save_both_blocks_and_max_pf_moves_is_unchanged(world, monkeypatch):
    flags, calls = world
    fast(monkeypatch)
    flags["league.max_pf_moves"] = True
    alone = json.loads(run_job()["result_json"])
    flags["league.playoff_targets"] = True
    both = json.loads(run_job()["result_json"])
    assert calls == [["sidecar", "viewer_user_id"]] * 2
    mine = both.pop("playoff_targets")
    assert mine["computed"] and mine["rows"]
    strip = lambda r: {**r, "max_pf_moves": {k: v for k, v in r["max_pf_moves"].items() if k != "elapsed_ms"}}
    assert strip(both) == strip(alone)
    assert both["max_pf_moves"]["settings_hash"] == maxpf_moves.settings_hash(maxpf_moves.settings())


def test_the_job_reads_saved_outlooks_by_roster_owner(world, monkeypatch):
    flags, _ = world
    flags["league.playoff_targets"] = True
    fast(monkeypatch)
    source = deepcopy(SOURCE)
    next(r for r in source[f"{API}/league/{LEAGUE_ID}/rosters"] if r["roster_id"] == 6)["co_owners"] = ["co6"]
    monkeypatch.setattr(provider, "capture", lambda league_id, user, cfg, fetch, **kw: REAL_CAPTURE(
        league_id, user, cfg, lambda url: deepcopy(source[url]), captured_at=CAPTURED_AT, clock=lambda: CAPTURED_AT, **kw))
    db.upsert_league_preference(OWNERS[3], LEAGUE_ID, "rebuilder")   # 95% in the forecast
    db.upsert_league_preference("co6", LEAGUE_ID, "jets")            # 78%, saved by the co-owner
    db.upsert_league_preference(OWNERS[11], LEAGUE_ID, "contender")  # 73%
    db.upsert_league_preference(OWNERS[10], "another-league", "jets")
    block = json.loads(run_job()["result_json"])["playoff_targets"]
    assert sorted(int(rid) for rid, s in block["sellers"].items() if s["eligible"]) == [2, 3, 4, 5, 6, 8, 9, 12]
    assert block["sellers"]["6"]["owner_ids"] == [OWNERS[6], "co6"] and block["pool_size"] == 8 * 24
    assert "rebuilder" not in json.dumps(block) and "jets" not in json.dumps(block)  # the outlook is not saved


def test_exception_leaves_the_forecast_intact(world, monkeypatch):
    flags, _ = world
    flags["league.playoff_targets"] = True
    monkeypatch.setattr(playoff_targets, "compute", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    result = json.loads(run_job()["result_json"])
    assert "playoff_targets" not in result and result["status"] == "complete" and result["teams"]


def test_time_budget_leaves_the_forecast_intact(world, monkeypatch):
    flags, _ = world
    flags["league.playoff_targets"] = True
    fast(monkeypatch, time_budget_seconds=1)
    clock = [1000.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    seen = []
    real_compute = playoff_targets.compute

    def slow(*args, cancelled, **kwargs):
        clock[0] += 5  # the budget has passed by the first checkpoint
        seen.append(1)
        return real_compute(*args, cancelled=cancelled, **kwargs)
    monkeypatch.setattr(playoff_targets, "compute", slow)
    row = run_job()
    assert seen and "playoff_targets" not in json.loads(row["result_json"])


def test_scenario_runs_never_get_a_block(world):
    flags, calls = world
    flags["league.playoff_targets"] = True
    row = run_job(kind="scenario")
    assert calls == [["viewer_user_id"]] and "playoff_targets" not in json.loads(row["result_json"])


def test_prior_reuse_recomputes_on_a_settings_or_seller_change(world, monkeypatch):
    flags, _ = world
    flags["league.playoff_targets"] = True
    fast(monkeypatch)
    kept = run_job(keep=True)
    first = json.loads(kept["result_json"])
    counted = []
    real_compute = playoff_targets.compute
    monkeypatch.setattr(playoff_targets, "compute", lambda *a, **k: counted.append(1) or real_compute(*a, **k))
    second = json.loads(run_job(keep=True)["result_json"])
    assert second["reused_compatible_result"] and counted == []
    assert second["playoff_targets"] == first["playoff_targets"]
    with db.engine.begin() as conn:  # the store admits four runs per account in ten minutes
        conn.execute(db.league_projection_runs_table.delete().where(
            db.league_projection_runs_table.c.run_id == kept["run_id"]))
    # A manager saves Rebuilding: the set of selling teams changed, so the step runs again.
    db.upsert_league_preference(OWNERS[3], LEAGUE_ID, "rebuilder")
    third = json.loads(run_job(keep=True)["result_json"])
    assert counted == [1] and third["playoff_targets"]["sellers"]["3"]["eligible"]
    # A settings change recomputes.
    fast(monkeypatch, candidates=1)
    fourth = json.loads(run_job(keep=True)["result_json"])
    assert counted == [1, 1] and len(fourth["playoff_targets"]["rows"]) <= 1
    # Flag off: the reused block is dropped from the saved result.
    flags["league.playoff_targets"] = False
    fifth = json.loads(run_job()["result_json"])
    assert fifth["reused_compatible_result"] and "playoff_targets" not in fifth
