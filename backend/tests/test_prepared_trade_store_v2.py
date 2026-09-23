"""Versioned bounded storage; synthetic SQL and real codec/proof fixtures."""
from copy import deepcopy
from datetime import timedelta
import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, event, insert, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from backend import database as db, prepared_trade_store as old
from backend import prepared_trade_store_v2 as store, prepared_trade_payload_v2 as codec
from backend import user_data_lifecycle
from backend.tests.test_prepared_trade_payload import (
    make_bundle, public, PREPARED, SERVED, EXPIRES, isolated_config,
)

NOW = old._time(PREPARED)
RECEIPT, MODEL = {"frozen_source": 1}, {"generator": "bilateral-2"}


@pytest.fixture
def engine(monkeypatch, tmp_path):
    local_pg = os.environ.get("FTF_PREPARED_TEST_POSTGRES_URL")
    controller = schema = None
    if local_pg:
        url = make_url(local_pg)
        # This opt-in is ONLY the parent's disposable private Unix-socket PG.
        # Reject network hosts and unrelated databases before any connection.
        assert url.drivername == "postgresql+psycopg2" and not url.host and url.database == "postgres"
        assert str(url.query.get("host", "")).startswith("/private/tmp/prepared-postgres-")
        assert str(url.query.get("port")) == "55439"
        schema = "prepared_a_" + uuid.uuid4().hex
        controller = create_engine(url)
        with controller.begin() as conn:
            conn.execute(CreateSchema(schema))
        result = create_engine(url, connect_args={"options": "-csearch_path=" + schema})
    else:
        result = create_engine("sqlite:///" + str(tmp_path / "paged.db"),
                               connect_args={"check_same_thread": False})
    db.metadata.create_all(result)
    monkeypatch.setattr(db, "engine", result)
    clock = old._time
    monkeypatch.setattr(old, "_time", lambda value=None: NOW if value is None else clock(value))
    with result.begin() as conn:
        for uid in ("viewer", "other"):
            conn.execute(insert(db.users_table).values(sleeper_user_id=uid, created_at="2026-01-01"))
    try:
        yield result
    finally:
        result.dispose()
        if controller is not None:
            # Unique schema created by this fixture; no public/legacy schemas.
            with controller.begin() as conn:
                conn.execute(DropSchema(schema, cascade=True))
            controller.dispose()


def records(engine, table):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(select(table)).mappings()]


def claim(league="synthetic_bilateral"):
    scope = old.InventoryScope("viewer", league, "viewer", "sf_ppr", "organic")
    target = {"scope": scope.as_dict(), "participants": ["viewer", "other"], "binding": {"test": True}}
    sid = old.create_sweep(uuid.uuid4().hex, [target], started=user_data_lifecycle.snapshot(), now=NOW)
    return scope, old.claim_target(sid, now=NOW)


def stage(n=3, candidates=False, seal=True):
    original, cards, raw = make_bundle(n, with_candidates=candidates)
    scope, claimed = claim(original["league_id"])
    value = store.begin_inventory(claimed, dependency_receipt=RECEIPT, model_identity=MODEL,
        participants=claimed["participants"], created_at=NOW, expires_at=NOW + timedelta(hours=24), now=NOW)
    capture = codec.PagedPreparedEvidenceCapture(stage=value, user_id="viewer", league_id=scope.league_id,
                                                job_id="prepared-job")
    if original["candidate_set"]:
        capture.candidate_set(original["candidate_set"])
    for start in range(0, len(raw), 30):
        capture.impressions(raw[start:start + 30])
    completion = capture.finish(cards, map(public, cards))
    store.finish_metadata(value, metadata={**completion, "generation_job_id": "prepared-job",
        "mutations": [], "target": {}, "job_fields": {}}, now=NOW)
    if seal:
        store.seal_inventory(value, completion=completion, dependency_receipt=RECEIPT, model_identity=MODEL, now=NOW)
    return scope, value, completion, cards, raw


def adoption(scope):
    reader = store.peek_inventory(scope, now=NOW)
    inventory = codec.restore_inventory(reader, user_id="viewer", league_id=scope.league_id, now=SERVED)
    claimed = store.claim_adoption(reader.inventory_id, dependency_receipt=RECEIPT, model_identity=MODEL,
                                  publication={"served_at": SERVED}, now=NOW)
    return reader, inventory, claimed


def commit(claimed, batch):
    before, after = batch["cursor_before"], batch["cursor_after"]
    return store.ensure_adoption_evidence(claimed, candidate_set=batch["candidate_set"], rows=batch["impression_rows"],
        ordinal_start=before["cards"], ordinal_end=after["cards"], ghost_start=before["ghosts"], ghost_end=after["ghosts"], now=NOW)


def test_real_codec_roundtrip_seal_before_ready_and_exact_evidence(engine):
    scope, value, completion, cards, raw = stage(3, candidates=True, seal=False)
    assert store.peek_inventory(scope, now=NOW) is None
    assert old.sweep_status(value.claim["sweep_id"], now=NOW)["counts"] == {"running": 1}
    for table in (db.deck_impressions_table, db.deck_candidate_sets_table, db.user_events_table):
        assert not records(engine, table)
    store.seal_inventory(value, completion=completion, dependency_receipt=RECEIPT, model_identity=MODEL, now=NOW)
    assert old.sweep_status(value.claim["sweep_id"], now=NOW)["unexpired_artifacts"] == 1
    reader, inventory, claimed = adoption(scope)
    assert not hasattr(reader, "payload")
    assert [card.owner_evaluation.snapshot_json for card in inventory.iter_cards()] == [card.owner_evaluation.snapshot_json for card in cards]
    batch, = inventory.batches(**claimed["publication"])
    with pytest.raises(store.InvalidArtifact, match="non-durable"):
        store.checkpoint_adoption(claimed, published_count=3, expected_prefix=0, now=NOW)
    result = commit(claimed, batch)
    assert result["impressions"] == 3 and result["candidate_sets"] == 1
    assert commit(claimed, batch) == {"impressions": 0, "candidate_sets": 0, "snapshots": 0}
    store.checkpoint_adoption(claimed, published_count=3, expected_prefix=0, complete=True, now=NOW)
    assert [row["valuation_json"] for row in records(engine, db.deck_impressions_table)] == [row["valuation_json"] for row in raw]
    assert not records(engine, db.user_events_table)


def test_exact_append_retry_gap_and_metadata_conflict(engine):
    scope, claimed = claim()
    value = store.begin_inventory(claimed, dependency_receipt=RECEIPT, model_identity=MODEL,
        participants=claimed["participants"], created_at=NOW, expires_at=NOW + timedelta(hours=24), now=NOW)
    row = {"exact": [1, 1.0, True]}
    first = value.append_page("cards", 0, 0, [row], now=NOW)
    assert value.append_page("cards", 0, 0, [row], now=NOW) == first
    with pytest.raises(store.InvalidArtifact, match="changed content"):
        value.append_page("cards", 0, 0, [{"exact": [1, 1, True]}], now=NOW)
    with pytest.raises(store.InvalidArtifact, match="contiguous"):
        value.append_page("cards", 2, 1, [row], now=NOW)
    assert len(records(engine, store.P)) == 1


def test_seal_freezes_append_before_semantic_validation(engine, monkeypatch):
    scope, value, completion, _, _ = stage(1, seal=False)
    original = codec.restore_inventory
    def validate(reader, **kwargs):
        with pytest.raises(store.StaleWork):
            value.append_page("cards", 1, 1, [{"unexpected": True}], now=NOW)
        with pytest.raises(store.StaleWork):
            value.put_nodes([], now=NOW)
        return original(reader, **kwargs)
    monkeypatch.setattr(codec, "restore_inventory", validate)
    store.seal_inventory(value, completion=completion, dependency_receipt=RECEIPT, model_identity=MODEL, now=NOW)
    assert store.peek_inventory(scope, now=NOW).header["card_count"] == 1


def test_failed_seal_preserves_prior_active_head(engine, monkeypatch):
    scope, prior, _, _, _ = stage(1)
    _, value, completion, _, _ = stage(1, seal=False)
    monkeypatch.setattr(codec, "restore_inventory", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("synthetic invalid")))
    with pytest.raises(ValueError):
        store.seal_inventory(value, completion=completion, dependency_receipt=RECEIPT, model_identity=MODEL, now=NOW)
    assert store.peek_inventory(scope, now=NOW).inventory_id == prior.inventory_id
    assert store.abort_inventory(value, now=NOW) == 1


@pytest.mark.parametrize("kind", ["cards", "node"])
def test_adjacent_checksum_rewrite_cannot_change_sealed_root(engine, kind):
    scope, value, _, _, _ = stage(1)
    reader = store.peek_inventory(scope, now=NOW)
    table = store.P if kind == "cards" else store.N
    with engine.begin() as conn:
        stmt = select(table).where(table.c.inventory_id == value.inventory_id)
        if kind == "cards": stmt = stmt.where(table.c.kind == "cards")
        row = dict(conn.execute(stmt).mappings().first())
        body = store._decode(row)
        if kind == "cards": body[0]["runtime"]["trade_id"] = "tampered"
        else: body["created_at"] = SERVED
        replacement = store._encode(body)
        changed = update(table).where(table.c.inventory_id == value.inventory_id)
        if kind == "cards": changed = changed.where(table.c.kind == "cards", table.c.page_index == row["page_index"])
        else: changed = changed.where(table.c.snapshot_id == row["snapshot_id"])
        conn.execute(changed.values(**replacement))
    with pytest.raises(store.InvalidArtifact, match="sealed root"):
        if kind == "cards": reader.read_cards(0, 1)
        else: reader.get_nodes([row["snapshot_id"]])


def test_expired_original_generation_claim_cannot_write_or_be_revived(engine):
    _, value, _, _, _ = stage(1, seal=False)
    with pytest.raises(store.StaleWork):
        value.put_nodes([], now=NOW + timedelta(seconds=301))
    assert records(engine, store.M)[0]["state"] == "staging"


def test_generation_renewal_retains_token_and_never_extends_artifact_expiry(engine):
    _, value, _, _, _ = stage(1, seal=False)
    original = records(engine, store.M)[0]
    value.put_nodes([], now=NOW + timedelta(seconds=200))
    target = records(engine, db.prepared_trade_targets_table)[0]
    assert target["lease_token"] == value.claim["lease_token"]
    assert old._time(target["lease_until"]) == NOW + timedelta(seconds=500)
    assert records(engine, store.M)[0]["expires_at"] == original["expires_at"]


def test_byte_partition_bounds_entire_sql_execute_and_singleton(engine, monkeypatch):
    monkeypatch.setattr(store, "MAX_SQL_STATEMENT_BYTES", 10000)
    values = [{"payload": "x" * 1800, "id": i} for i in range(7)]
    chunks = list(store._sql_chunks(values))
    assert sum(map(len, chunks)) == len(values) and len(chunks) > 1
    assert all(store.sql_bytes(chunk) <= 10000 for chunk in chunks)
    with pytest.raises(store.InvalidArtifact, match="SQL statement") as caught:
        list(store._sql_chunks([{"payload": "x" * 5000}]))
    assert old.safe_failure_details(caught.value)["reason"] == "inventory_sql_limit"


def test_page_precheck_rejects_before_whole_encoder_or_json_loader(monkeypatch):
    monkeypatch.setattr(store, "MAX_PAGE_LOGICAL_BYTES", 100)
    monkeypatch.setattr(old, "_encode", lambda *args, **kwargs: pytest.fail("whole encoder reached"))
    with pytest.raises(store.InvalidArtifact, match="structural budget"):
        store._encode({"large": "x" * 200})
    monkeypatch.setattr(codec.json, "loads", lambda *args, **kwargs: pytest.fail("unbounded parser reached"))
    with pytest.raises(store.InvalidArtifact, match="structural budget"):
        store._parse("[" * 81 + "0" + "]" * 81)


def test_v1_reuse_status_and_prune_dispatch_to_v2_without_json_materialization(engine):
    scope, value, _, _, _ = stage(1)
    _, again = claim(scope.league_id)
    old.complete_target(again, status="reused", now=NOW)
    assert old.sweep_status(again["sweep_id"], now=NOW)["counts"] == {"reused": 1}
    assert old.sweep_status(again["sweep_id"], now=NOW)["unexpired_artifacts"] == 1
    assert old.peek_inventory(scope, now=NOW) is None
    assert old.prune(now=NOW + timedelta(hours=24)) == 1
    for table in (store.M, store.P, store.N): assert not records(engine, table)


def test_failure_after_retiring_head_rolls_back_switch_and_target_completion(engine):
    scope, previous, _, _, _ = stage(1)
    _, incoming, completion, _, _ = stage(1, seal=False)
    def fail(_conn, _cursor, statement, parameters, _context, _many):
        values = parameters.values() if isinstance(parameters, dict) else parameters
        if statement.startswith("UPDATE prepared_trade_manifests_v2") and "sealed" in values:
            raise RuntimeError("synthetic seal write failure")
    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic seal"):
            store.seal_inventory(incoming, completion=completion, dependency_receipt=RECEIPT, model_identity=MODEL, now=NOW)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert store.peek_inventory(scope, now=NOW).inventory_id == previous.inventory_id
    assert old.sweep_status(incoming.claim["sweep_id"], now=NOW)["counts"] == {"running": 1}
    incoming_row = next(row for row in records(engine, store.M) if row["inventory_id"] == incoming.inventory_id)
    assert incoming_row["state"] == "validating"
    assert incoming_row["root_sha256"] == incoming.validation_root == store._manifest_root(incoming_row)
    assert incoming_row["active_scope_key"] is None
    assert store.ATTESTATION_KEY not in incoming.reader().metadata()


def test_direct_adoption_claim_cannot_bypass_missing_semantic_attestation(engine):
    _, value, _, _, _ = stage(1)
    current = next(row for row in records(engine, store.M) if row["inventory_id"] == value.inventory_id)
    metadata = store.Reader(value.inventory_id).metadata()
    del metadata[store.ATTESTATION_KEY]
    packed, digest = store._text_pair(metadata)
    changed = {"metadata_json": packed, "metadata_sha256": digest}
    changed["root_sha256"] = store._manifest_root({**current, **changed})
    with engine.begin() as conn:
        conn.execute(update(store.M).where(store.M.c.inventory_id == value.inventory_id).values(**changed))
    assert store.claim_adoption(value.inventory_id, dependency_receipt=RECEIPT, model_identity=MODEL,
        publication={"served_at": SERVED}, now=NOW) is None
    current = next(row for row in records(engine, store.M) if row["inventory_id"] == value.inventory_id)
    assert current["adoption_token"] is None and current["adoption_json"] is None


def test_late_evidence_write_failure_rolls_back_candidate_and_diagnostics(engine):
    scope, _, _, _, _ = stage(1, candidates=True)
    _, inventory, claimed = adoption(scope)
    batch, = inventory.batches(**claimed["publication"])
    def fail(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO deck_impressions"):
            raise RuntimeError("synthetic evidence write failure")
    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic evidence"):
            commit(claimed, batch)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    for table in (db.deck_impressions_table, db.deck_diagnostic_snapshots_table, db.deck_candidate_sets_table):
        assert not records(engine, table)
    assert store.peek_inventory(scope, now=NOW).header["published_count"] == 0


def test_adoption_renewal_and_forged_count_control(engine):
    scope, _, _, _, _ = stage(2)
    _, inventory, claimed = adoption(scope)
    first, second = list(inventory.batches(**claimed["publication"], first_batch_size=1, batch_size=1))
    store.ensure_adoption_evidence(claimed, candidate_set=first["candidate_set"], rows=first["impression_rows"],
        ordinal_start=0, ordinal_end=1, now=NOW + timedelta(seconds=80))
    manifest = records(engine, store.M)[0]
    assert old._time(manifest["adoption_lease_until"]) == NOW + timedelta(seconds=200)
    assert manifest["expires_at"] == old._iso(EXPIRES)
    forged = {**claimed, "card_count": 1}
    with pytest.raises(store.StaleWork):
        store.checkpoint_adoption(forged, published_count=1, expected_prefix=0, complete=True, now=NOW + timedelta(seconds=80))
    assert store.peek_inventory(scope, now=NOW).header["published_count"] == 0


def test_root_proof_text_is_bounded_before_decoding(monkeypatch):
    monkeypatch.setattr(store, "_leaf", lambda *args: "0" * 64)
    monkeypatch.setattr(store, "_parse", lambda *args: pytest.fail("oversized proof was decoded"))
    with pytest.raises(store.InvalidArtifact, match="root proof"):
        store._proof_check("page", {"proof_json": " " * 16385}, "0" * 64)


def test_abandoned_unsealed_stage_pruned_after_claim_expiry(engine):
    scope, value, _, _, _ = stage(1, seal=False)
    assert old.prune(now=NOW + timedelta(seconds=301)) == 1
    for table in (store.M, store.P, store.N): assert not records(engine, table)
    assert not [row for row in records(engine, db.prepared_trade_participants_table)
                if row["subject_id"] == value.inventory_id]


@pytest.mark.parametrize("inventory_id,root", [
    (None, "0" * 64), (1, "0" * 64), ("", "0" * 64),
    ("x" * 129, "0" * 64), ("inventory", None), ("inventory", "g" * 64),
    ("inventory", "0" * 63),
])
def test_retirement_rejects_unbound_arguments_before_sql(monkeypatch, inventory_id, root):
    monkeypatch.setattr(db.engine, "begin", lambda: pytest.fail("unbound retirement queried SQL"))
    with pytest.raises(store.InvalidArtifact, match="retirement binding"):
        store.retire_invalid_inventory(inventory_id, root)


def test_retirement_never_decodes_corrupt_header_and_does_not_touch_staging(engine, monkeypatch):
    _, staged, completion, _, _ = stage(1, seal=False)
    before = records(engine, store.M)
    assert not store.retire_invalid_inventory(staged.inventory_id, "0" * 64)
    assert records(engine, store.M) == before
    store.seal_inventory(staged, completion=completion, dependency_receipt=RECEIPT, model_identity=MODEL, now=NOW)
    sealed = staged
    manifest = next(row for row in records(engine, store.M) if row["inventory_id"] == sealed.inventory_id)
    with engine.begin() as conn:
        conn.execute(update(store.M).where(store.M.c.inventory_id == sealed.inventory_id).values(header_json="corrupt"))
    monkeypatch.setattr(store, "_header", lambda *_: pytest.fail("retirement decoded corrupt private header"))
    assert store.retire_invalid_inventory(sealed.inventory_id, manifest["root_sha256"])
    result = next(row for row in records(engine, store.M) if row["inventory_id"] == sealed.inventory_id)
    assert result["state"] == "retired" and result["header_json"] == "corrupt"
    assert result["root_sha256"] == manifest["root_sha256"]
