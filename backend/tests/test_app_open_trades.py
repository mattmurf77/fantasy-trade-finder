"""Startup warm-up must prepare the same ordinary search the user opens."""
import time
from unittest.mock import MagicMock, patch
import pytest
from backend import server
from backend.tests.test_session_init_sleeper_calls import harness, _init, USER_ID, NON_SLEEPER_LEAGUE
from backend.tests.test_force_supersedes_running_job import live, _generate, _register_running_job

@pytest.mark.parametrize("value,expected", [(None, .5), (.5, .5), (.75, .75), ("bad", .5), (True, .5), (2, .5)])
def test_startup_uses_native_fairness(harness, monkeypatch, value, expected):
    client, _ = harness
    monkeypatch.setattr(server, "_trade_jobs_by_key", {})
    extra = {} if value is None else {"trade_fairness_threshold": value}
    assert _init(client, NON_SLEEPER_LEAGUE, **extra).status_code == 200
    assert server._kickoff_trade_job.call_args.kwargs["fairness_threshold"] == expected

@pytest.mark.parametrize("status,threshold,kicks", [("error", .5, True), ("complete", .75, True), ("running", .75, False), ("running", .5, False), ("complete", .5, False)])
def test_startup_retries_error_and_reuses_only_matching_threshold(harness, monkeypatch, status, threshold, kicks):
    client, _ = harness
    key = server._trade_job_key(USER_ID, NON_SLEEPER_LEAGUE, "1qb_ppr")
    monkeypatch.setattr(server, "_trade_job_preferences", lambda *args: {"prefs": None, "seeded_outlook": None})
    job = dict(job_id="warm", key=key, status=status, finished_at=time.monotonic(), fairness_threshold=threshold,
               outlook_value=None, safety_policy=server._trade_safety_signature(),
               presentation_capture=server._capture_trade_presentation(),
               significance_capture=server._capture_trade_significance())
    monkeypatch.setattr(server, "_trade_jobs", {"warm": job})
    monkeypatch.setattr(server, "_trade_jobs_by_key", {key: "warm"})
    assert _init(client, NON_SLEEPER_LEAGUE).status_code == 200
    assert bool(server._kickoff_trade_job.call_count) == kicks
    if status == "running" and kicks:
        assert job["superseded"]

@pytest.mark.parametrize("threshold,shared", [(.5, False), (.75, True)])
def test_find_trade_adopts_only_matching_running_warmup(live, threshold, shared):
    client, _ = live
    old = _register_running_job()
    server._trade_jobs["new"] = dict(old, job_id="new", fairness_threshold=threshold)
    with patch.object(server, "_kickoff_trade_job", MagicMock(return_value="new")) as kick:
        response = _generate(client, fairness_threshold=threshold)
    assert response.status_code == 200
    assert response.get_json()["job_id"] == (old["job_id"] if shared else "new")
    assert kick.call_count == int(not shared)
    assert bool(old.get("superseded")) == (not shared)


@pytest.mark.parametrize("outlook", [None, "win_now"])
def test_completed_warmup_is_ready_without_another_worker(live, outlook):
    client, _ = live
    job = _register_running_job()
    job.update(status="complete", finished_at=time.monotonic(), fairness_threshold=.5,
               safety_policy=server._trade_safety_signature(), outlook_value=outlook,
               presentation_capture=server._capture_trade_presentation())
    with patch.object(server, "_infer_user_outlook", return_value=(outlook, None)), \
         patch.object(server, "_kickoff_trade_job", MagicMock()) as kick:
        response = _generate(client, fairness_threshold=.5)
    assert response.status_code == 200
    assert response.get_json()["job_id"] == job["job_id"]
    assert response.get_json()["status"] == "complete"
    kick.assert_not_called()
