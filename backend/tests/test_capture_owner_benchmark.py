"""Owner benchmark capture accepts complete evidence and preserves private files."""
import hashlib
import io
import json
import stat

import pytest

from backend.eval import capture_owner_benchmark
from backend.eval.capture_owner_benchmark import coverage_summary, input_fingerprint, owner_request, write_private


class _ReadOnlyResult:
    def __init__(self, rows):
        self.rows = rows

    def scalar(self):
        return "on"

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _ReadOnlyEngine:
    """Synthetic bakeoff_runs rows behind the read-only connection contract."""

    def __init__(self, rows):
        self.rows = rows

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        return _ReadOnlyResult(self.rows[:params["limit"]] if params else [])

    def dispose(self):
        pass


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


def test_fingerprint_canonical_form_is_pinned_for_the_writer_input_sha256():
    owner_input = {"user_id": "u1", "user_elo": {"p2": 1612.5, "p1": 1500}, "outlook": "jéts",
                   "user_roster": ["p2", "p1"]}
    canonical = b'{"outlook":"j\\u00e9ts","user_elo":{"p1":1500,"p2":1612.5},"user_id":"u1","user_roster":["p2","p1"]}'
    expected = "51ebfed005e8fb980d467c86a901b1299679149ac04fec65886d1bc4dc345bc4"
    assert hashlib.sha256(canonical).hexdigest() == expected
    assert input_fingerprint({"input": owner_input}) == expected
    with pytest.raises(ValueError):
        input_fingerprint({"input": {"user_elo": {"p1": float("nan")}}})


def test_capture_counts_unsampled_rows_and_sha_matched_coverage(monkeypatch, tmp_path):
    from scripts import set_knob
    from backend.tools import prod_analytics
    sampled = {"input": {"user_id": "synthetic", "user_roster": ["p1"], "members": [{"id": "m", "elo": {"p2": 1}}],
                         "players": {}, "seed_elo": {}, "user_elo": {"p1": 1500}, "outlook": "jets"}}
    configs = [
        ("unsampled_match", {"base": {}, "owner_request_sampled": False,
                             "input_sha256": input_fingerprint(sampled), "input_bytes": 321}),
        ("sampled", {"base": {}, "owner_request": sampled}),
        ("unsampled", {"base": {}, "owner_request_sampled": False, "input_sha256": "0" * 64, "input_bytes": 654}),
        ("legacy", {"base": {}}),
    ]
    rows = [{"run_id": run_id, "user_id": "synthetic", "league_id": "league",
             "created_at": "2026-10-20T00:00:00+00:00", "config_json": json.dumps(config)}
            for run_id, config in configs]
    rows += [{"run_id": run_id, "user_id": "synthetic", "league_id": "league",
              "created_at": "2026-10-20T00:00:00+00:00", "config_json": raw}
             for run_id, raw in (("legacy_list", "[]"), ("invalid", "{"))]
    monkeypatch.setattr(set_knob, "SECRETS", set_knob.SECRETS)
    monkeypatch.setattr(prod_analytics, "SECRETS", prod_analytics.SECRETS)
    monkeypatch.setattr(set_knob, "_from_secrets",
                        {"FTF_API_BASE": "https://api.invalid", "CRON_SECRET": "synthetic"}.get)
    monkeypatch.setattr(prod_analytics, "_load_prod_url", lambda: "postgresql://synthetic")
    monkeypatch.setattr(prod_analytics, "_connect_readonly", lambda url, timeout: _ReadOnlyEngine(rows))
    monkeypatch.setattr(capture_owner_benchmark.urllib.request, "urlopen", lambda request, timeout: io.BytesIO(b"{}"))
    output = tmp_path / "capture.json"
    summary = capture_owner_benchmark.capture(secrets=tmp_path / "synthetic.env", output=output)
    assert summary["omitted"] == {"not_sampled": 2, "full_owner_request_absent": 2, "invalid_config_json": 1}
    assert summary["run_rows_scanned"] == 6
    assert summary["sampled"] == summary["unique_requests"] == 1
    assert summary["not_sampled"] == 2
    assert summary["not_sampled_covered_by_sampled"] == 1
    assert summary["query_truncated"] is False
    envelope = json.loads(output.read_text())
    assert [r["run_id"] for r in envelope["requests"]] == ["sampled"]
    assert envelope["requests"][0]["owner_request"] == sampled
    assert envelope["summary"] == summary


def test_coverage_counts_only_unsampled_fingerprints_matching_a_captured_request():
    rows = [{"user_id": "synthetic", "league_id": "league",
             "owner_request": {"input": {"user_id": "synthetic", "members": []}}}]
    captured = input_fingerprint(rows[0]["owner_request"])
    summary = coverage_summary(rows, fetched_count=4, max_runs=100, missing={"not_sampled": 3},
                               not_sampled_shas=[captured, captured, None])
    assert (summary["sampled"], summary["not_sampled"], summary["not_sampled_covered_by_sampled"]) == (1, 3, 2)
    legacy = coverage_summary(rows, fetched_count=1, max_runs=100, missing={})
    assert (legacy["not_sampled"], legacy["not_sampled_covered_by_sampled"]) == (0, 0)


def test_private_artifact_is_exclusive_and_has_restricted_permissions(tmp_path):
    path = tmp_path / "snapshot.json"
    write_private(path, {"fixture": True})
    assert json.loads(path.read_text()) == {"fixture": True}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_private(path, {"fixture": False})
    assert json.loads(path.read_text()) == {"fixture": True}
