"""Safe preparation failure phases and sanitized durable operator diagnostics."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from backend import prepared_trade_runtime as runtime, prepared_trade_store as store
from backend.tests.test_prepared_trade_runtime_review import (
    headless, large_exclusive, exclusive, owner_harness, harness, new_claim, server,
)


@pytest.mark.parametrize("phase", sorted(runtime._ARTIFACT_PHASES))
def test_artifact_phase_preserves_original_exception_and_only_labels_fixed_stage(phase):
    failure = store.InvalidArtifact("unknown secret-like synthetic message")
    with pytest.raises(store.InvalidArtifact) as seen:
        with runtime._artifact_phase(phase):
            raise failure
    assert seen.value is failure
    assert runtime._artifact_failure_details(failure) == {
        "reason": "preparation_failed", "phase": phase}


@pytest.mark.parametrize("phase", [None, [], {"raw": "private"}, "private identity", 5])
def test_unknown_or_forged_phase_is_not_logged(phase):
    failure = store.InvalidArtifact("synthetic private terms and credentials")
    failure.prepared_phase = phase
    assert runtime._artifact_failure_details(failure) == {
        "reason": "preparation_failed", "phase": "unknown"}
    with pytest.raises(ValueError, match="unknown_preparation_phase"):
        with runtime._artifact_phase(phase):
            pytest.fail("invalid stage admitted")


def test_named_raw_exception_projection_sabotage_is_detected(monkeypatch):
    failure = store.InvalidArtifact("synthetic-secret and private trade terms")
    def privacy_contract():
        assert runtime._artifact_failure_details(failure) == {
            "reason": "preparation_failed", "phase": "unknown"}
    privacy_contract()
    monkeypatch.setattr(runtime, "_artifact_failure_details", lambda exc: {
        "reason": str(exc), "phase": "unknown"})
    with pytest.raises(AssertionError):
        privacy_contract()


@pytest.mark.parametrize("message,reason", sorted(runtime._CAPTURE_FAILURE_REASONS.items()))
@pytest.mark.parametrize("typed", [False, True])
def test_paged_capture_codes_are_exact_literals_without_raw_text(message, reason, typed):
    from backend.prepared_trade_payload_v2 import PreparedPayloadError
    error_type = PreparedPayloadError if typed else ValueError
    failure = error_type(message)
    with pytest.raises(ValueError) as seen:
        with runtime._artifact_phase("inventory_capture"):
            raise failure
    assert seen.value is failure
    assert runtime._artifact_failure_details(failure) == {"reason": reason, "phase": "inventory_capture"}
    assert runtime._artifact_failure_details(error_type(message + " private-user-secret")) == {
        "reason": "preparation_failed", "phase": "unknown"}


@pytest.mark.parametrize("known", [True, False])
def test_sweep_persists_only_safe_reason_and_logs_sanitized_phase(headless, monkeypatch, caplog, known):
    _, target = headless
    now = datetime.now(timezone.utc)
    _, sweep, _ = new_claim(target, now=now, lease_seconds=1)
    monkeypatch.setattr(runtime, "utcnow", lambda: now + timedelta(seconds=2))
    monkeypatch.setattr(runtime, "_active", False)
    monkeypatch.setattr(runtime, "_state", {"status": "idle"})
    monkeypatch.setattr(runtime, "discover", lambda *a: pytest.fail("resume rediscovered cohort"))
    message = ("prepared payload exceeds byte limit; nothing truncated" if known
               else "synthetic-sensitive-owner cookie=value terms=private")
    def fail(_server, claim):
        with runtime._artifact_phase("inventory_save"):
            raise store.InvalidArtifact(message)
    monkeypatch.setattr(runtime, "prepare_target", fail)
    class InlineThread:
        def __init__(self, *, target, **kwargs): self.target = target
        def start(self): self.target()
    monkeypatch.setattr(runtime.threading, "Thread", InlineThread)
    result = runtime.start(server, idempotency_key="safe-error-resume", resume_sweep_id=sweep)
    assert result["status"] == "complete"
    assert result["result"]["counts"] == {"error": 1}
    assert result["result"]["unexpired_artifacts"] == 0
    reason = "inventory_logical_limit" if known else "preparation_failed"
    logs = [record.message for record in caplog.records if "prepared inventory" in record.message]
    assert any(json.dumps({"phase": "inventory_save", "reason": reason}, sort_keys=True) in row for row in logs)
    assert all(message not in row for row in logs)
    assert not runtime._active
