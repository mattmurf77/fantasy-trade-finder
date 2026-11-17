"""Operator-only `retry_missing_targets` dispatch option (D-273, 2026-11-16).

The Playoff targets twin of `retry_missing_moves` (test_maxpf_moves_rerun).
It makes due now every target whose latest successful baseline was made under
the current model and has no current Playoff targets block (absent; not
computed for a reason other than `not_eligible`; or computed under other
settings, e.g. `min_playoff_gain` 0.01 before D-272), is not leased and has
no attempt in flight. With the flag off it marks nothing and says so.
Scheduled ticks never pass it.

The end-to-end case runs the real dispatch, store and worker (`service._run`)
over the season-signal fixture with the fake fetch: a baseline saved without a
block, then a `retry_missing_targets` dispatch gives it a computed block; the
settings change (0.01 -> 0.02) makes that block stale, a second dispatch
re-runs it under the current hash, and a third call marks nothing.
"""
from copy import deepcopy
import json

import pytest

from backend import database as db
from backend.league_projections import batch, playoff_targets, provider, service, store
from backend.tests.test_league_projection_batch import scheduled  # noqa: F401  (fixture)
from backend.tests.test_maxpf_moves_rerun import enqueue_only, runs, saved_success
from backend.tests.test_outlook_calibration_persistence import engine  # noqa: F401  (fixture)
from backend.tests.test_season_points import CAPTURED_AT, LEAGUE_ID, sleeper_world

T = db.league_projection_targets_table
CURRENT = playoff_targets.settings()
OLD = {**CURRENT, "min_playoff_gain": 0.01}  # the shipped value before D-272


def block(options=CURRENT, **changes):
    return {"playoff_targets": {"version": playoff_targets.VERSION, "computed": True, "reason": None, "skipped": None,
                                "rows": [], "settings": options, "settings_hash": playoff_targets.settings_hash(options),
                                **changes}}


def retry(**kw):
    return batch.dispatch(enqueue_only, retry_missing_targets=True, **kw)


def test_settings_raised_the_threshold():
    assert CURRENT["min_playoff_gain"] == 0.02, "D-272; OLD below assumes it"
    assert playoff_targets.settings_hash(OLD) != playoff_targets.settings_hash(CURRENT)


@pytest.mark.parametrize("result", [{}, {"playoff_targets": None},
                                    {"playoff_targets": {"computed": False, "reason": "time_budget"}},
                                    {"playoff_targets": {"computed": False}},
                                    {"max_pf_moves": {"computed": True}}])
def test_marks_a_current_model_success_without_a_block(scheduled, result):  # noqa: F811
    due = saved_success(scheduled, result)  # noqa: F811
    plain = batch.dispatch(enqueue_only)
    assert plain["queued"] == 0 and "retried_missing_targets" not in plain, "Ordinary ticks keep their shape"
    out = retry()
    assert (out["queued"], out["retried_missing_targets"]) == (1, 1)
    assert not {"retried", "retried_unsupported", "retried_missing_moves", "retried_missing_targets_skipped"} & set(out)
    assert runs(scheduled)  # noqa: F811 == 2 and batch.target("account", "123")["next_due_at"] == batch.next_weekly_slot() >= due


@pytest.mark.parametrize("result", [block(OLD), block(OLD, skipped="no_sellers"), block(settings_hash=None)])
def test_marks_a_block_saved_under_other_settings(scheduled, result):  # noqa: F811
    saved_success(scheduled, result)  # noqa: F811
    out = retry()
    assert (out["queued"], out["retried_missing_targets"]) == (1, 1)


@pytest.mark.parametrize("result", [block(), block(skipped="near_certain"),
                                    {"playoff_targets": {"computed": False, "reason": "not_eligible"}},
                                    {"playoff_targets": {"computed": False, "reason": "not_eligible",
                                                         "settings_hash": playoff_targets.settings_hash(OLD)}}])
def test_leaves_a_current_or_settled_block_alone(scheduled, result):  # noqa: F811
    due = saved_success(scheduled, result)  # noqa: F811
    out = retry()
    assert (out["queued"], out["retried_missing_targets"]) == (0, 0)
    assert batch.target("account", "123")["next_due_at"] == due and runs(scheduled)  # noqa: F811 == 1


def test_flag_off_marks_nothing_and_says_so(scheduled, monkeypatch):  # noqa: F811
    due = saved_success(scheduled, {})
    monkeypatch.setattr(batch, "is_enabled", lambda key: key != "league.playoff_targets")
    monkeypatch.setattr(playoff_targets, "settings", lambda: pytest.fail("flag off: settings never read"))
    out = retry()
    assert (out["queued"], out["retried_missing_targets"], out["retried_missing_targets_skipped"]) == (0, 0, "playoff_targets_disabled")
    assert batch.target("account", "123")["next_due_at"] == due


def test_skips_a_leased_target(scheduled):  # noqa: F811
    from datetime import datetime, timedelta, timezone
    due = saved_success(scheduled, {})
    with scheduled.begin() as conn:
        conn.execute(T.update().values(lease_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()))
    out = retry()
    assert (out["queued"], out["retried_missing_targets"]) == (0, 0)
    assert batch.target("account", "123")["next_due_at"] == due


@pytest.mark.parametrize("status", ["queued", "running"])
def test_skips_a_target_with_an_attempt_in_flight(scheduled, status):  # noqa: F811
    due = saved_success(scheduled, {}, attempt_status=status)
    out = retry()
    assert out["retried_missing_targets"] == 0 and batch.target("account", "123")["next_due_at"] == due


def test_other_model_success_stays_with_the_other_model_rule(scheduled):  # noqa: F811
    saved_success(scheduled, {}, model_version="joint-season-scenario-v2")
    out = retry()
    assert (out["queued"], out["retried_missing_targets"]) == (1, 0), "The model-change rule refreshes it; this must not count it"


def test_no_success_yet_is_not_marked(scheduled):  # noqa: F811
    assert batch.dispatch(enqueue_only)["queued"] == 1
    out = retry()
    assert (out["queued"], out["retried_missing_targets"]) == (0, 0)


def test_repeated_calls_converge_to_zero(scheduled):  # noqa: F811
    saved_success(scheduled, block(OLD))
    assert retry()["retried_missing_targets"] == 1
    # The new attempt is queued: in flight, so not marked again.
    assert retry()["retried_missing_targets"] == 0


def test_combines_with_the_other_retry_options(scheduled):  # noqa: F811
    saved_success(scheduled, {})
    out = retry(retry_missing_moves=True, retry_incomplete=True, retry_unsupported=True)
    assert out["queued"] == 1 and (out["retried"], out["retried_unsupported"]) == (0, 0)
    assert (out["retried_missing_moves"], out["retried_missing_targets"]) == (1, 0), "Marked once, by the first option"


@pytest.mark.parametrize("kwargs,error", [(dict(retry_missing_targets=True, initial=True), "retry_missing_targets_requires_weekly_mode"),
                                          (dict(retry_missing_targets=1), "invalid_retry_missing_targets"),
                                          (dict(retry_missing_targets="true"), "invalid_retry_missing_targets"),
                                          (dict(retry_missing_targets=None), "invalid_retry_missing_targets")])
def test_refuses_initial_mode_and_non_bool(scheduled, kwargs, error):  # noqa: F811
    with pytest.raises(ValueError) as exc:
        batch.dispatch(None, **kwargs)
    assert str(exc.value) == error


@pytest.mark.parametrize("off,expected", [("league.projections", {"status": "disabled", "queued": 0}),
                                          ("league.projections_provider_approved", {"status": "approval_pending", "queued": 0})])
def test_marks_nothing_when_dispatch_returns_early(scheduled, monkeypatch, off, expected):  # noqa: F811
    due = saved_success(scheduled, {})
    monkeypatch.setattr(batch, "is_enabled", lambda key: key != off)
    assert retry() == expected
    assert batch.target("account", "123")["next_due_at"] == due


def test_scheduled_dispatch_is_unchanged(scheduled, monkeypatch):  # noqa: F811
    """Without the option: the targets flag is never read, nothing is marked
    and the response has exactly the keys it had before."""
    saved_success(scheduled, {})
    seen = []
    monkeypatch.setattr(batch, "is_enabled", lambda key: seen.append(key) or True)
    monkeypatch.setattr(batch, "_retry_missing_targets_baselines", lambda now: pytest.fail("never without the option"))
    out = batch.dispatch(enqueue_only)
    assert "league.playoff_targets" not in seen
    assert set(out) == {"status", "queued", "cadence", "initial", "schedule_timezone"} and out["queued"] == 0


def test_cron_route_passes_retry_missing_targets_and_still_rejects_unknown_keys(monkeypatch):
    from backend import server
    monkeypatch.setattr(server, "_CRON_SECRET", "synthetic-secret")
    monkeypatch.setattr(server, "_IS_PROD_ENV", True)
    called = []
    monkeypatch.setattr(batch, "dispatch", lambda fetch, **kw: called.append(kw) or {"queued": 0})
    client, path, headers = server.app.test_client(), "/api/cron/league-projections", {"X-Cron-Secret": "synthetic-secret"}
    assert client.post(path, json={"retry_missing_targets": True}).status_code == 401
    assert client.post(path, json={"retry_missing_targets": True, "force": True}, headers=headers).status_code == 400
    assert not called
    assert client.post(path, json={"retry_missing_targets": True}, headers=headers).status_code == 200
    both = {"retry_missing_targets": True, "retry_missing_moves": True}
    assert client.post(path, json=both, headers=headers).status_code == 200
    fg = server._projection_foreground_busy
    assert called == [{"retry_missing_targets": True, "foreground_busy": fg}, {**both, "foreground_busy": fg}]


def test_cron_route_maps_the_validation_error_to_400(monkeypatch):
    from backend import server
    monkeypatch.setattr(server, "_CRON_SECRET", "synthetic-secret")
    monkeypatch.setattr(server, "_IS_PROD_ENV", True)
    resp = server.app.test_client().post("/api/cron/league-projections", json={"retry_missing_targets": "yes"},
                                         headers={"X-Cron-Secret": "synthetic-secret"})
    assert resp.status_code == 400 and resp.get_json() == {"error": "invalid_retry_missing_targets"}


# ── end to end: dispatch → worker → a computed block under current settings ──

def test_end_to_end_missing_then_stale_blocks_are_recomputed(engine, monkeypatch):  # noqa: F811
    flags = {"league.projections": True, "league.projections_provider_approved": True,
             "league.max_pf_moves": False, "league.playoff_targets": False}
    for module in (batch, service):
        monkeypatch.setattr(module, "is_enabled", lambda key: flags.get(key, False))
    real = batch.settings()
    options = {**real, "policy_approved": True, "model": {**real["model"], "iterations": 5000}}
    monkeypatch.setattr(batch, "settings", lambda: options)
    # A smaller search so each job takes seconds; the 0.01 settings stand in
    # for blocks saved before D-272.
    current = {**CURRENT, "simulations_per_candidate": 500, "candidates": 2}
    targets = {"options": {**current, "min_playoff_gain": 0.01}}
    monkeypatch.setattr(playoff_targets, "settings", lambda: targets["options"])
    monkeypatch.setattr(service, "_viewer_identity", lambda uid: "me")
    monkeypatch.setattr(service, "wake", lambda *a, **kw: None)  # the worker runs below, in this thread
    source = sleeper_world()
    real_capture = provider.capture
    monkeypatch.setattr(provider, "capture", lambda league_id, league_user_id, cfg, fetch_json, **kw: real_capture(
        league_id, league_user_id, cfg, lambda url: deepcopy(source[url]), captured_at=CAPTURED_AT, clock=lambda: CAPTURED_AT, **kw))
    batch.register("account", LEAGUE_ID, "me", 2026)
    with engine.begin() as conn:
        conn.execute(T.update().values(next_due_at="2020-01-01T00:00:00+00:00"))

    def latest():
        item = batch.target("account", LEAGUE_ID)
        return item, store.get(item["last_success_id"], "account", LEAGUE_ID)

    # A weekly baseline saved before the flag went on: no block.
    assert batch.dispatch(enqueue_only)["queued"] == 1
    service._run(lambda url: pytest.fail("no network"))
    _, first = latest()
    assert first["status"] == "complete" and "playoff_targets" not in json.loads(first["result_json"])
    flags["league.playoff_targets"] = True
    assert batch.dispatch(enqueue_only)["queued"] == 0, "Not due until next week without the option"

    # Missing block: marked, re-run, computed (under the old 0.01 settings).
    out = retry()
    assert (out["queued"], out["retried_missing_targets"]) == (1, 1)
    queued = store.get(batch.target("account", LEAGUE_ID)["last_attempt_id"], "account", LEAGUE_ID)
    assert queued["snapshot_json"] is None, "A dispatched baseline captures fresh, so the targets step runs"
    service._run(lambda url: pytest.fail("no network"))
    item, second = latest()
    assert second["run_id"] != first["run_id"] and second["run_id"] == item["last_attempt_id"]
    result = json.loads(second["result_json"])
    assert result["reused_compatible_result"], "Same capture: the prior forecast is reused and only the block is added"
    old_block = result["playoff_targets"]
    assert old_block["computed"] and old_block["settings"]["min_playoff_gain"] == 0.01
    assert retry()["retried_missing_targets"] == 0, "Current under the 0.01 settings"

    # The threshold is raised: the 0.01 block is stale, so it is re-run.
    targets["options"] = current
    out = retry()
    assert (out["queued"], out["retried_missing_targets"]) == (1, 1)
    service._run(lambda url: pytest.fail("no network"))
    item, third = latest()
    assert third["run_id"] != second["run_id"] and third["run_id"] == item["last_attempt_id"]
    new_block = json.loads(third["result_json"])["playoff_targets"]
    assert new_block["computed"] and new_block["rows"]
    assert new_block["settings_hash"] == playoff_targets.settings_hash(current) != old_block["settings_hash"]
    assert new_block["settings"]["min_playoff_gain"] == 0.02
    assert retry()["retried_missing_targets"] == 0, "Converged"
