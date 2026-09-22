"""Owner benchmark capture accepts complete evidence and preserves private files."""
import json
import stat

import pytest

from backend.eval.capture_owner_benchmark import coverage_summary, input_fingerprint, owner_request, write_private


def test_complete_request_acceptance_never_fills_missing_roster_or_board():
    request = {"input": {"user_id": "synthetic", "user_roster": [], "members": [],
                         "players": {}, "seed_elo": {}, "user_elo": {}}}
    assert owner_request({"owner_request": request}) is request
    assert owner_request(request) is request
    assert owner_request({"owner_request": {"input": {}}}) is None
    assert owner_request({"owner_request": {"snapshot_ref": "unresolved"}}) is None
    assert owner_request({"input": {**request["input"], "members": "not a list"}}) is None


def test_null_outlooks_are_explicit_unknown_and_json_safe():
    rows = [{"user_id": "synthetic", "league_id": "league", "owner_request": {
        "input": {"outlook": outlook, "members": [{"elo": {}}, {"elo": {"p": 1}}]}}}
        for outlook in (None, "jets")]
    summary = coverage_summary(rows, fetched_count=2, max_runs=100, missing={})
    assert summary["outlooks"] == {"unknown": 1, "jets": 1}
    assert summary["counterparty_boards"] == 2
    assert summary["distinct_manager_leagues"] == 1
    json.dumps(summary, sort_keys=True, allow_nan=False)


def test_frozen_input_dedup_ignores_missing_or_reused_supplied_hash():
    first = {"request_hash": None, "input": {"user_elo": {"p": 1}, "user_id": "synthetic"}}
    changed = {"request_hash": None, "input": {"user_elo": {"p": 2}, "user_id": "synthetic"}}
    assert input_fingerprint(first) != input_fingerprint(changed)
    first["request_hash"] = changed["request_hash"] = "same untrusted hash"
    assert input_fingerprint(first) != input_fingerprint(changed)
    assert input_fingerprint(first) == input_fingerprint({"input": first["input"], "request_hash": "different"})


def test_private_artifact_is_exclusive_and_has_restricted_permissions(tmp_path):
    path = tmp_path / "snapshot.json"
    write_private(path, {"fixture": True})
    assert json.loads(path.read_text()) == {"fixture": True}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_private(path, {"fixture": False})
    assert json.loads(path.read_text()) == {"fixture": True}
