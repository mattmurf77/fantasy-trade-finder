"""Offline scorecard integration: fixed request counts, Unknown, replay and privacy.

No runtime model/DB import. Golden synthetic contexts are not production grades.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.eval.scorecard_runner import (cluster_mean_interval, expand_offer, fingerprint,
                                          render_markdown, run_manifest, write_report)

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "backend/tests/fixtures/model-evaluation/dimensions/opposite-objectives.json"


def manifest():
    offer = json.loads(FIXTURE.read_text())
    return {"schema_version": 1, "benchmark_id": "synthetic-test", "evidence_class": "synthetic",
            "requests": [{"model_id": "model", "request_id": "r1", "status": "ok"},
                         {"model_id": "model", "request_id": "r2", "status": "empty"},
                         {"model_id": "empty-model", "request_id": "r1", "status": "failed"}],
            "offers": [{"model_id": "model", "model_version": "v1", "request_id": "r1",
                        "stage": "native", "native_rank": 1, "offer": offer}]}


def test_unknown_never_promotes_and_failed_empty_requests_stay():
    m = manifest()
    original = deepcopy(m)
    r = run_manifest(m)
    assert m == original
    assert r["promotion_status"] == "insufficient_evidence"
    assert r["outcomes"]["status"] == "unknown"
    assert r["requests"] == 3
    assert r["zero_output_models"] == ["empty-model"]
    stage = r["models"]["model@v1"]["stages"]["native"]
    assert stage["evaluated_offers_per_request"] == .5
    for dimension in stage["dimensions"].values():
        assert set(dimension["managers"]) == {"A", "B"}
        for manager in dimension["managers"].values():
            assert set(manager) == {"give", "receive", "package"}


def test_shared_context_and_full_input_results_match():
    full = manifest()
    compact = deepcopy(full)
    row = compact["offers"][0]
    offer = row.pop("offer")
    compact["contexts"] = {"ctx": offer}
    row.update(context_id="ctx", offer_id=offer["offer_id"],
               terms={r: m["give"] for r, m in offer["managers"].items()})
    assert expand_offer(row, compact) == offer
    assert run_manifest(full)["models"] == run_manifest(compact)["models"]


def test_hash_and_summary_are_reproducible():
    m = manifest()
    assert run_manifest(m) == run_manifest(deepcopy(m))
    assert fingerprint({"b": 1, "a": 2}) == fingerprint({"a": 2, "b": 1})


@pytest.mark.parametrize("change", ["duplicate_request", "duplicate_offer", "orphan", "version"])
def test_bad_identity_rejected(change):
    m = manifest()
    if change == "duplicate_request":
        m["requests"].append(m["requests"][0])
    elif change == "duplicate_offer":
        m["offers"].append(m["offers"][0])
    elif change == "orphan":
        m["offers"][0]["request_id"] = "missing"
    else:
        del m["offers"][0]["model_version"]
    with pytest.raises(ValueError):
        run_manifest(m)


def test_no_mixed_versions_under_same_denominator():
    m = manifest()
    other = deepcopy(m["offers"][0])
    other.update(model_version="v2", stage="other")
    m["offers"].append(other)
    with pytest.raises(ValueError, match="variant IDs"):
        run_manifest(m)


def test_ambiguous_compact_full_envelope_is_rejected():
    m = manifest()
    m["offers"][0].update(context_id="ambiguous", terms={"A": ["rb"], "B": ["wr", "first"]})
    with pytest.raises(ValueError, match="mutually exclusive"):
        run_manifest(m)


def test_invalid_evaluator_result_quarantines_without_dropping_request():
    m = manifest()
    m["offers"][0]["offer"]["assets"]["rb"]["owner_id"] = "wrong-owner"
    r = run_manifest(m)
    assert r["requests"] == 3
    assert r["quarantined_offers"] == [{"row_number": 0, "error_type": "invalid_offer_integrity"}]
    assert r["models"] == {}


def test_report_private_create_only_and_no_board_leak(tmp_path):
    r = run_manifest(manifest())
    output = tmp_path / "run"
    write_report(r, output)
    assert output.stat().st_mode & 0o777 == 0o700
    assert (output / "scorecard.json").stat().st_mode & 0o777 == 0o600
    text = (output / "scorecard.json").read_text()
    assert "synthetic-explicit-board" not in text
    assert "tanker" not in text
    assert "private_details" not in text
    assert "A package evidence" in render_markdown(r)
    with pytest.raises(FileExistsError):
        write_report(r, output)


def test_no_fabricated_one_cluster_interval_and_seeded_bootstrap():
    assert cluster_mean_interval([{"cluster_id": "L", "value": 1}])["ci95"] is None
    rows = [{"cluster_id": "A", "value": 0}, {"cluster_id": "B", "value": 2}]
    assert cluster_mean_interval(rows) == cluster_mean_interval(rows)
    assert cluster_mean_interval(rows)["estimate"] == 1
    with pytest.raises(ValueError):
        cluster_mean_interval([{"cluster_id": "A", "value": float("nan")}])


def test_outcome_pipeline_retains_historical_event_without_default_private_rows():
    fixture = json.loads((REPO / "backend/tests/fixtures/model-evaluation/outcomes/synthetic-mutual-withdrawal.json").read_text())
    m = manifest()
    m.update({key: fixture[key] for key in ("cohort", "episodes", "cutoff")})
    r = run_manifest(m)
    assert r["outcomes"]["primary_yield"]["numerator"] == 1
    assert r["outcomes"]["non_reversed_yield"]["numerator"] == 0
    assert r["outcomes"]["guardrails"]["status"] == "unratified"
    assert "episodes" not in r["outcomes"]
    assert "cohort_id" not in r["outcomes"]
    assert "private_outcome_details" not in r
    assert "private_outcome_details" in run_manifest(m, include_details=True)
