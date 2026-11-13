"""Operator-only `retry_missing_moves` dispatch option (D-260, 2026-11-13).

After `league.max_pf_moves` is turned on, every forecast saved earlier has no
moves block until its weekly slot. `retry_missing_moves` makes due now every
target whose latest successful baseline was made under the current model and
saved no computed block, is not leased and has no attempt in flight. With the
flag off it marks nothing and says so. Scheduled ticks never pass it.

The end-to-end case runs the real dispatch, store and worker (`service._run`)
over the season-signal fixture with the fake fetch: a baseline saved without a
block, then a `retry_missing_moves` dispatch, and the new latest success has a
computed block; a second call marks nothing.
"""
from copy import deepcopy
import json

import pytest

from backend import database as db
from backend.league_projections import batch, maxpf_moves, provider, service, store
from backend.league_projections.core import VERSION
from backend.tests.test_league_projection_batch import scheduled  # noqa: F401  (fixture)
from backend.tests.test_outlook_calibration_persistence import engine  # noqa: F401  (fixture)
from backend.tests.test_season_points import CAPTURED_AT, LEAGUE_ID, sleeper_world

T, R = db.league_projection_targets_table, db.league_projection_runs_table


def enqueue_only(*a):
    pytest.fail("enqueue only")


def saved_success(engine, result, *, model_version=VERSION, attempt_status=None):
    """Queue the weekly baseline and record it as the latest success with
    `result`; the target is left due next week."""
    assert batch.dispatch(enqueue_only)["queued"] == 1
    with engine.begin() as conn:
        run_id = conn.execute(db.select(T.c.last_attempt_id)).scalar()
        inputs = json.loads(conn.execute(db.select(R.c.input_json).where(R.c.run_id == run_id)).scalar())
        inputs["expected_model_version"] = model_version
        conn.execute(R.update().where(R.c.run_id == run_id).values(status="complete", result_json=json.dumps(result),
                                                                   input_json=json.dumps(inputs)))
        conn.execute(T.update().values(last_success_id=run_id))
        if attempt_status:
            conn.execute(R.insert().values(run_id="a" * 32, user_id="account", league_id="123", status=attempt_status,
                                           created_at=store.utc_now(), updated_at=store.utc_now(), expires_at="2999-01-01T00:00:00+00:00",
                                           request_hash="x", input_json=json.dumps({"kind": "baseline", "expected_model_version": VERSION})))
            conn.execute(T.update().values(last_attempt_id="a" * 32))
    return batch.target("account", "123")["next_due_at"]


def runs(engine):
    with engine.connect() as conn:
        return len(conn.execute(db.select(R)).all())


COMPUTED = {"max_pf_moves": {"version": maxpf_moves.VERSION, "computed": True, "rows": [],
                             "settings_hash": maxpf_moves.settings_hash(maxpf_moves.settings())}}


@pytest.mark.parametrize("result", [{}, {"max_pf_moves": None},
                                    {"max_pf_moves": {"computed": False, "reason": "time_budget"}}])
def test_marks_a_current_model_success_without_a_computed_block(scheduled, result):  # noqa: F811
    due = saved_success(scheduled, result)
    plain = batch.dispatch(enqueue_only)
    assert plain["queued"] == 0 and "retried_missing_moves" not in plain, "Ordinary ticks keep their shape"
    out = batch.dispatch(enqueue_only, retry_missing_moves=True)
    assert (out["queued"], out["retried_missing_moves"]) == (1, 1)
    assert "retried" not in out and "retried_unsupported" not in out and "retried_missing_moves_skipped" not in out
    assert runs(scheduled) == 2 and batch.target("account", "123")["next_due_at"] == batch.next_weekly_slot() >= due


@pytest.mark.parametrize("result", [COMPUTED, {"max_pf_moves": {"computed": False, "reason": "not_eligible"}}])
def test_leaves_a_computed_or_settled_block_alone(scheduled, result):  # noqa: F811
    due = saved_success(scheduled, result)
    out = batch.dispatch(enqueue_only, retry_missing_moves=True)
    assert (out["queued"], out["retried_missing_moves"]) == (0, 0)
    assert batch.target("account", "123")["next_due_at"] == due and runs(scheduled) == 1


def test_flag_off_marks_nothing_and_says_so(scheduled, monkeypatch):  # noqa: F811
    due = saved_success(scheduled, {})
    monkeypatch.setattr(batch, "is_enabled", lambda key: key != "league.max_pf_moves")
    out = batch.dispatch(enqueue_only, retry_missing_moves=True)
    assert (out["queued"], out["retried_missing_moves"], out["retried_missing_moves_skipped"]) == (0, 0, "max_pf_moves_disabled")
    assert batch.target("account", "123")["next_due_at"] == due


def test_skips_a_leased_target(scheduled):  # noqa: F811
    from datetime import datetime, timedelta, timezone
    due = saved_success(scheduled, {})
    with scheduled.begin() as conn:
        conn.execute(T.update().values(lease_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()))
    out = batch.dispatch(enqueue_only, retry_missing_moves=True)
    assert (out["queued"], out["retried_missing_moves"]) == (0, 0)
    assert batch.target("account", "123")["next_due_at"] == due


@pytest.mark.parametrize("status", ["queued", "running"])
def test_skips_a_target_with_an_attempt_in_flight(scheduled, status):  # noqa: F811
    due = saved_success(scheduled, {}, attempt_status=status)
    out = batch.dispatch(enqueue_only, retry_missing_moves=True)
    assert out["retried_missing_moves"] == 0 and batch.target("account", "123")["next_due_at"] == due


def test_other_model_success_stays_with_the_other_model_rule(scheduled):  # noqa: F811
    saved_success(scheduled, {}, model_version="joint-season-scenario-v2")
    out = batch.dispatch(enqueue_only, retry_missing_moves=True)
    assert (out["queued"], out["retried_missing_moves"]) == (1, 0), "The model-change rule refreshes it; this must not count it"


def test_no_success_yet_is_not_marked(scheduled):  # noqa: F811
    assert batch.dispatch(enqueue_only)["queued"] == 1
    out = batch.dispatch(enqueue_only, retry_missing_moves=True)
    assert (out["queued"], out["retried_missing_moves"]) == (0, 0)


def test_repeated_calls_converge_to_zero(scheduled):  # noqa: F811
    saved_success(scheduled, {})
    assert batch.dispatch(enqueue_only, retry_missing_moves=True)["retried_missing_moves"] == 1
    # The new attempt is queued: in flight, so not marked again.
    assert batch.dispatch(enqueue_only, retry_missing_moves=True)["retried_missing_moves"] == 0


@pytest.mark.parametrize("kwargs,error", [(dict(retry_missing_moves=True, initial=True), "retry_missing_moves_requires_weekly_mode"),
                                          (dict(retry_missing_moves=1), "invalid_retry_missing_moves"),
                                          (dict(retry_missing_moves="true"), "invalid_retry_missing_moves"),
                                          (dict(retry_missing_moves=None), "invalid_retry_missing_moves")])
def test_refuses_initial_mode_and_non_bool(scheduled, kwargs, error):  # noqa: F811
    with pytest.raises(ValueError) as exc:
        batch.dispatch(None, **kwargs)
    assert str(exc.value) == error


@pytest.mark.parametrize("off,expected", [("league.projections", {"status": "disabled", "queued": 0}),
                                          ("league.projections_provider_approved", {"status": "approval_pending", "queued": 0})])
def test_marks_nothing_when_dispatch_returns_early(scheduled, monkeypatch, off, expected):  # noqa: F811
    due = saved_success(scheduled, {})
    monkeypatch.setattr(batch, "is_enabled", lambda key: key != off)
    assert batch.dispatch(enqueue_only, retry_missing_moves=True) == expected
    assert batch.target("account", "123")["next_due_at"] == due


def test_scheduled_dispatch_is_unchanged(scheduled, monkeypatch):  # noqa: F811
    """Without the option: the moves flag is never read, nothing is marked and
    the response has exactly the keys it had before."""
    saved_success(scheduled, {})
    seen = []
    monkeypatch.setattr(batch, "is_enabled", lambda key: seen.append(key) or True)
    monkeypatch.setattr(batch, "_retry_missing_moves_baselines", lambda now: pytest.fail("never without the option"))
    out = batch.dispatch(enqueue_only)
    assert "league.max_pf_moves" not in seen
    assert set(out) == {"status", "queued", "cadence", "initial", "schedule_timezone"} and out["queued"] == 0


def test_cron_route_passes_retry_missing_moves_and_still_rejects_unknown_keys(monkeypatch):
    from backend import server
    monkeypatch.setattr(server, "_CRON_SECRET", "synthetic-secret")
    monkeypatch.setattr(server, "_IS_PROD_ENV", True)
    called = []
    monkeypatch.setattr(batch, "dispatch", lambda fetch, **kw: called.append(kw) or {"queued": 0})
    client, path, headers = server.app.test_client(), "/api/cron/league-projections", {"X-Cron-Secret": "synthetic-secret"}
    assert client.post(path, json={"retry_missing_moves": True}).status_code == 401
    assert client.post(path, json={"retry_missing_moves": True, "force": True}, headers=headers).status_code == 400
    assert not called
    assert client.post(path, json={"retry_missing_moves": True}, headers=headers).status_code == 200
    assert called == [{"retry_missing_moves": True, "foreground_busy": server._projection_foreground_busy}]


# ── end to end: dispatch → worker → a computed block ─────────────────────

def test_end_to_end_a_saved_baseline_gets_its_block(engine, monkeypatch):  # noqa: F811
    flags = {"league.projections": True, "league.projections_provider_approved": True, "league.max_pf_moves": False}
    for module in (batch, service):
        monkeypatch.setattr(module, "is_enabled", lambda key: flags.get(key, False))
    real = batch.settings()
    options = {**real, "policy_approved": True, "model": {**real["model"], "iterations": 5000}}
    monkeypatch.setattr(batch, "settings", lambda: options)
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
    item, before = latest()
    assert before["status"] == "complete" and "max_pf_moves" not in json.loads(before["result_json"])
    flags["league.max_pf_moves"] = True
    assert batch.dispatch(enqueue_only)["queued"] == 0, "Not due until next week without the option"

    out = batch.dispatch(enqueue_only, retry_missing_moves=True)
    assert (out["queued"], out["retried_missing_moves"]) == (1, 1)
    queued = store.get(batch.target("account", LEAGUE_ID)["last_attempt_id"], "account", LEAGUE_ID)
    assert queued["snapshot_json"] is None, "A dispatched baseline captures fresh, so the moves step runs"
    service._run(lambda url: pytest.fail("no network"))
    item, after = latest()
    assert after["run_id"] != before["run_id"] and after["run_id"] == item["last_attempt_id"]
    result = json.loads(after["result_json"])
    assert result["reused_compatible_result"], "Same capture: the prior forecast is reused and only the block is added"
    assert result["max_pf_moves"]["computed"] and result["max_pf_moves"]["rows"]
    assert batch.dispatch(enqueue_only, retry_missing_moves=True)["retried_missing_moves"] == 0, "Converged"
