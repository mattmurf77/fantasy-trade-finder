"""Evidence contract v1: local read-only sources, exact snapshots and honest gaps.

Covers SQLite write barriers/allowlist, source identities, diagnostic retention,
malformed and absent evidence, views versus generation, and sends versus trades.
All inputs are synthetic scratch files; no application imports or network calls.
"""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from backend.eval.scorecard_evidence import (
    audit_rows, frozen_owner_requests, load_export, load_sqlite_snapshot,
    occurrence_to_offer,
)


def occurrence(**updates):
    row = {"impression_id": "i1", "user_id": "alice", "league_id": "league",
           "deck_job_id": "job", "served_at": "2026-09-01T00:00:00Z",
           "model_arm": "owner_v2_bilateral", "assets_json": json.dumps({"give": ["p1"], "receive": ["p2"]}),
           "features_json": json.dumps({"partner_user_id": "bob"}),
           "valuation_json": json.dumps({"schema_version": 1, "generator_version": "test",
                "assets": [{"id": "p1", "market": 100}, {"id": "p2", "market": 110}],
                "viewer": {"roster_ids": ["p1"], "outlook": "jets", "outlook_source": "declared"},
                "counterparty": {"roster_ids": ["p2"], "outlook": "contender", "outlook_source": "inferred"}})}
    row.update(updates)
    return row


def private(tables):
    return audit_rows(tables, include_records=True)["private_records"]


def test_generated_rows_do_not_establish_views_or_fixed_cohort():
    report = audit_rows({"deck_impressions": [occurrence()]})
    assert report["counts"]["persisted_occurrences"] == 1
    assert report["counts"]["view_event_occurrences"] == 0
    assert report["fixed_eligible_cohort"]["status"] == "absent"
    assert "private_records" not in report
    assert "alice" not in json.dumps(report)
    assert "p1" not in json.dumps(report)
    assert report["occurrence_coverage"]["actual_expiry"] == 0
    assert report["occurrence_coverage"]["projection_backed_lineup"] == 0


def test_policy_snapshot_must_bind_both_directions_not_just_asset_union():
    valuation = {"assets": {"give": [{"id": "p2"}], "receive": [{"id": "p1"}]}}
    row = occurrence(valuation_json=json.dumps(valuation))
    assert private({"deck_impressions": [row]})["occurrences"][0]["snapshot_binding"] == "mismatch"
    valuation["assets"] = {"give": [{"id": "p1"}], "receive": [{"id": "p2"}]}
    row["valuation_json"] = json.dumps(valuation)
    assert private({"deck_impressions": [row]})["occurrences"][0]["snapshot_binding"] == "exact_directional"


def test_invalid_assets_are_retained_as_unknown_not_deduplicated():
    assets = {"give": ["p1", "p1"], "receive": ["p2"]}
    row = private({"deck_impressions": [occurrence(assets_json=json.dumps(assets))]})["occurrences"][0]
    assert row["assets"] == assets
    assert row["assets_status"] == "duplicate_or_overlapping_assets"
    assert row["snapshot_binding"] == "unknown"


def test_view_requires_unique_join_and_valid_timestamp_not_likes_or_ghosts():
    tables = {"deck_impressions": [occurrence(), occurrence(impression_id="i2", is_ghost=1)],
              "deck_outcomes": [
                  {"id": 1, "impression_id": "i1", "action": "like", "acted_at": "2026-09-01T01:00:00Z"},
                  {"id": 2, "impression_id": "i1", "action": "viewed", "acted_at": "broken"},
                  {"id": 3, "impression_id": "i2", "action": "viewed", "acted_at": "2026-09-01T01:00:00Z"},
                  {"id": 4, "impression_id": "absent", "action": "viewed", "acted_at": "2026-09-01T01:00:00Z"}]}
    report = audit_rows(tables)
    assert report["counts"]["view_event_occurrences"] == 0
    assert report["counts"]["outcome_orphan_or_ambiguous"] == 1
    assert report["integrity_issues"] == {"ghost_with_view_event": 1, "invalid_event_timestamp": 1}
    tables["deck_outcomes"].append({"id": 5, "impression_id": "i1", "action": "viewed", "acted_at": "2026-09-01T00:01:00Z"})
    assert audit_rows(tables)["counts"]["view_event_occurrences"] == 1
    tables["deck_impressions"].append(occurrence())
    assert audit_rows(tables)["counts"]["view_event_occurrences"] == 0


def test_actor_is_linked_from_occurrence_and_pass_reasons_are_not_actions():
    report = private({"deck_impressions": [occurrence()],
        "deck_outcomes": [{"id": 7, "impression_id": "i1", "action": "pass", "acted_at": "2026-09-02T00:00:00Z"}],
        "trade_pass_reasons": [{"impression_id": "i1", "reason": "fit", "free_text": "PRIVATE"}]})
    assert report["events"][0]["actor_id"] == "alice"
    assert report["events"][0]["source"] == {"table": "deck_outcomes", "key": "id", "value": 7}
    assert len(report["events"]) == 1
    assert "PRIVATE" not in json.dumps(report)


@pytest.mark.parametrize("value,status", [(None, "missing"), ("{", "malformed"), ("[]", "wrong_type"),
                                          ('{"x": NaN}', "malformed")])
def test_missing_and_malformed_snapshots_are_unknown(value, status):
    report = audit_rows({"deck_impressions": [occurrence(valuation_json=value)]}, include_records=True)
    assert report["occurrence_coverage"]["valuation:" + status] == 1
    row = report["private_records"]["occurrences"][0]
    assert row["valuation"] is None
    assert row["raw"]["valuation_json"] == value
    assert row["snapshot_binding"] == "unknown"


def test_distinct_snapshots_and_raw_asset_ids_are_never_overwritten():
    original = occurrence(assets_json=json.dumps({"give": ["league_2027_1_4"], "receive": ["p2"]}))
    tables = {"deck_impressions": [original], "trade_matches": [{"id": 9, "user_a_id": "bob", "user_b_id": "alice",
        "first_like_at": "2026-09-01", "second_like_at": "2026-09-04", "match_valuation_json": '{"match_only": true}'}],
        "trade_proposals": [{"id": 10, "valuation_json": '{"send_only": true}'}]}
    before = deepcopy(tables)
    record = private(tables)
    assert record["occurrences"][0]["assets"]["give"] == ["league_2027_1_4"]
    assert record["occurrences"][0]["snapshot_binding"] == "mismatch"
    assert record["source_tables"]["trade_matches"][0]["user_a_id"] == "bob"
    assert record["source_tables"]["trade_matches"][0]["match_valuation_json"] == '{"match_only": true}'
    record["occurrences"][0]["raw"]["user_id"] = "changed"
    assert tables == before


def test_provider_send_and_similarity_link_do_not_become_exact_completions():
    report = audit_rows({"trade_proposals": [{"id": 1, "provider_transaction_id": "tx"}],
                        "suggestion_trade_links": [{"id": 2, "transaction_id": "tx", "match_type": "exact"}],
                        "sleeper_trades": [{"id": 3, "transaction_id": "tx"}]})
    assert report["counts"]["confirmed_provider_sends"] == 1
    assert report["counts"]["captured_completed_provider_transactions_unlinked_to_episodes"] == 1
    assert report["counts"]["verified_exact_episode_completions"] == 0


def test_diagnostic_resolution_is_scoped_to_actor_and_job_with_expiry_marker():
    row = occurrence(features_json=json.dumps({"owner_request": {"$deck_diagnostic_v1": "snap"}}))
    snap = {"snapshot_id": "snap", "user_id": "alice", "deck_job_id": "wrong-job", "payload_json": '{"input": {"players": {}}}'}
    tables = {"deck_impressions": [row], "deck_diagnostic_snapshots": [snap]}
    missing = private(tables)["occurrences"][0]
    assert missing["features"]["owner_request"]["diagnostic_status"] == "expired_missing_or_ambiguous"
    snap["deck_job_id"] = "job"
    found = private(tables)["occurrences"][0]
    assert found["features"]["owner_request"] == {"input": {"players": {}}}
    assert found["raw"]["features_json"] == row["features_json"]


@pytest.mark.parametrize("payload,issue", [('{"$deck_diagnostic_v1":"snap"}', "cyclic_diagnostic_reference"),
                                          ("{", "malformed_diagnostic_payload")])
def test_invalid_diagnostic_graph_is_not_silently_repaired(payload, issue):
    report = audit_rows({"deck_impressions": [occurrence(features_json='{"owner_request":{"$deck_diagnostic_v1":"snap"}}')],
        "deck_diagnostic_snapshots": [{"snapshot_id": "snap", "user_id": "alice", "deck_job_id": "job", "payload_json": payload}]})
    assert report["integrity_issues"][issue] == 1


def test_manifest_is_input_order_invariant():
    tables = {"deck_impressions": [occurrence(), occurrence(impression_id="i2")]}
    first = audit_rows(tables)
    tables["deck_impressions"].reverse()
    assert audit_rows(tables) == first


def test_sqlite_is_read_only_allowlisted_and_does_not_use_environment(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE deck_impressions (impression_id TEXT, user_id TEXT, secret_token TEXT)")
        conn.execute("INSERT INTO deck_impressions VALUES ('i1','alice','PRIVATE')")
        conn.execute("CREATE TABLE credentials (token TEXT)")
        conn.execute("INSERT INTO credentials VALUES ('PRIVATE')")
    before = path.read_bytes()
    monkeypatch.setenv("DATABASE_URL", "postgresql://never-connect")
    real_connect = sqlite3.connect
    called = []
    def connect(database, **kwargs):
        called.append((database, kwargs))
        connection = real_connect(database, **kwargs)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE not_allowed (id INT)")
        return connection
    monkeypatch.setattr(sqlite3, "connect", connect)
    assert load_sqlite_snapshot(path) == {"deck_impressions": [{"impression_id": "i1", "user_id": "alice"}]}
    assert called == [(path.as_uri() + "?mode=ro", {"uri": True})]
    assert path.read_bytes() == before


def test_missing_sqlite_file_is_not_created_and_remote_uri_is_refused(tmp_path):
    path = tmp_path / "does-not-exist.db"
    with pytest.raises(FileNotFoundError):
        load_sqlite_snapshot(path)
    assert not path.exists()
    for uri in ("postgresql://remote/db", "file:/tmp/db?mode=rw", ":memory:"):
        with pytest.raises(ValueError):
            load_sqlite_snapshot(uri)


def test_allowlisted_name_cannot_be_a_view(tmp_path):
    path = tmp_path / "snapshot.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE VIEW deck_impressions AS SELECT 'secret' AS user_id")
    with pytest.raises(ValueError, match="ordinary tables"):
        load_sqlite_snapshot(path)


def test_json_export_allowlist_and_errors(tmp_path):
    path = tmp_path / "export.json"
    path.write_text(json.dumps({"tables": {"credentials": [{"token": "PRIVATE"}],
                                          "deck_impressions": [occurrence(secret_token="PRIVATE")]}}))
    assert "PRIVATE" not in json.dumps(load_export(path))
    path.write_text('{"deck_impressions": {}}')
    with pytest.raises(ValueError, match="list of rows"):
        load_export(path)
    path.write_text('{')
    with pytest.raises(ValueError):
        load_export(path)


def test_owner_input_replay_preserves_request_unit_not_experiment_cohort():
    config = {"unit": "request_inputs", "assignment_probability": .5, "input": {"user_elo": {"p1": 1700}},
              "market_as_of": "unavailable"}
    records = frozen_owner_requests({"bakeoff_runs": [{"run_id": "run", "config_json": json.dumps(config)}]})
    assert records[0]["assignment"] == config
    assert records[0]["fixed_preassignment_cohort"] is False
    assert records[0]["source"] == {"table": "bakeoff_runs", "key": "run_id", "value": "run"}


def test_occurrence_bridge_preserves_intent_missingness_and_never_uses_support_as_grade():
    features = {"partner_user_id": "bob", "owner_request": {"market_as_of": "unavailable", "input": {
        "players": {"p1": {"position": "RB", "age": 27}, "p2": {"position": "WR", "age": 23}}}}}
    captured = private({"deck_impressions": [occurrence(features_json=json.dumps(features))]})["occurrences"][0]
    offer = occurrence_to_offer(captured)
    assert offer["managers"]["A"]["selected_outlook"] == "jets"
    assert offer["managers"]["B"]["inferred_outlook"] == "contender"
    assert "selected_outlook" not in offer["managers"]["B"]
    assert offer["assets"]["p1"] == {"market_value": 100, "owner_id": "alice", "kind": "player", "position": "RB", "age": 27}
    assert offer["evidence"]["market"]["provenance"]["as_of"] is None
    assert offer["captured_at"] == "2026-09-01T00:00:00Z"
    assert "reviews" not in offer["evidence"]
    assert "personal_board" not in offer["managers"]["A"]
    assert "projections" not in offer["managers"]["A"]
    captured["snapshot_binding"] = "mismatch"
    with pytest.raises(ValueError, match="asset-bound"):
        occurrence_to_offer(captured)


@pytest.mark.parametrize("served_at", [None, "broken", "2026-09-01T00:00:00"])
def test_bridge_never_repairs_missing_or_ambiguous_capture_time(served_at):
    captured = private({"deck_impressions": [occurrence(served_at=served_at)]})["occurrences"][0]
    assert occurrence_to_offer(captured)["captured_at"] is None


def test_bridge_revised_dimensions_respect_capture_boundary():
    from backend.eval.scorecard_dimensions import evaluate_offer
    features = {"partner_user_id": "bob", "owner_request": {"input": {
        "players": {"p1": {"position": "RB"}, "p2": {"position": "WR"}}}}}
    row = occurrence(features_json=json.dumps(features))
    valuation = json.loads(row["valuation_json"])
    valuation["market"] = {"consensus_asof": "2026-09-02T00:00:00Z"}
    row["valuation_json"] = json.dumps(valuation)
    captured = private({"deck_impressions": [row]})["occurrences"][0]
    result = evaluate_offer(occurrence_to_offer(captured))
    assert result["dimensions"]["fairness"]["managers"]["A"]["give"]["raw_features"]["market_total"] is None
    valuation["market"]["consensus_asof"] = "2026-08-31T00:00:00Z"
    row["valuation_json"] = json.dumps(valuation)
    captured = private({"deck_impressions": [row]})["occurrences"][0]
    result = evaluate_offer(occurrence_to_offer(captured))
    assert result["dimensions"]["fairness"]["managers"]["A"]["give"]["raw_features"]["market_total"] == 100


def test_import_does_not_load_application_or_database():
    code = "import sys; import backend.eval.scorecard_evidence; assert 'backend.database' not in sys.modules; assert 'backend.server' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2], check=True)
