"""The retained-policy coordinator must isolate the actual child process."""
import json
from types import SimpleNamespace

import pytest

from backend.eval import bilateral_revision_benchmark as benchmark


def test_retained_replay_uses_fixed_hash_seed_and_removes_database_and_import_inheritance(tmp_path, monkeypatch):
    previous = tmp_path / "previous"
    previous.mkdir()
    (previous / "summary.json").write_text(json.dumps({"results": [
        {"variant": "candidate", "request_index": 1, "cohort": "development"}]}))
    args = SimpleNamespace(output=tmp_path / "output", policy_replay=previous,
        candidate_repo=tmp_path, policy_two=tmp_path / "old_policy.py", timeout=1)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///must-not-inherit.sqlite")
    monkeypatch.setenv("PYTHONPATH", "/not-the-replay-repository")
    monkeypatch.setenv("PYTHONHASHSEED", "random")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "0")
    monkeypatch.setenv("REPLAY_TEST_MARKER", "preserved")

    class ChildObserved(Exception):
        pass

    def observe(command, **kwargs):
        env = kwargs.get("env")
        assert isinstance(env, dict), "policy replay inherits uncontrolled process state"
        assert "DATABASE_URL" not in env and "PYTHONPATH" not in env
        assert env["PYTHONHASHSEED"] == "0"
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        assert env["REPLAY_TEST_MARKER"] == "preserved"
        assert "--policy-worker" in command
        raise ChildObserved

    monkeypatch.setattr(benchmark.subprocess, "run", observe)
    with pytest.raises(ChildObserved):
        benchmark.replay_policy(args)
    assert benchmark.os.environ["PYTHONHASHSEED"] == "random"
    assert benchmark.os.environ["DATABASE_URL"] == "sqlite:///must-not-inherit.sqlite"
