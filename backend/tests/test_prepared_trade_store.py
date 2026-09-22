"""Hermetic durable preparation/adoption, tamper and deletion controls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import uuid

import pytest
from sqlalchemy import create_engine, delete, event, insert, select, update

from backend import accounts, database as db, prepared_trade_store as store, user_data_lifecycle

NOW = datetime(2026, 9, 22, 15, tzinfo=timezone.utc)
OWNER, PEER = "prepared-synthetic-owner", "prepared-synthetic-peer"
RECEIPT = {"source_revision": 1, "rosters": {"a": ["p1", "p2"]}}
MODEL = {"generator": "bilateral-2", "policy": "survivors-3"}


@pytest.fixture
def engine(monkeypatch, tmp_path):
    result = create_engine("sqlite:///" + str(tmp_path / "prepared.db"),
                           connect_args={"check_same_thread": False})
    db.metadata.create_all(result)
    monkeypatch.setattr(db, "engine", result)
    with result.begin() as conn:
        for uid in (OWNER, PEER):
            conn.execute(insert(db.users_table).values(sleeper_user_id=uid, created_at="2026-01-01"))
    yield result
    result.dispose()


def scope(owner=OWNER, league="synthetic-league", canonical=None, request="organic"):
    return store.InventoryScope(owner, league, canonical or owner, "sf_ppr", request)


def target(value=None, participants=None):
    value = value or scope()
    return {"scope": value.as_dict(), "participants": participants if participants is not None else [OWNER, PEER],
            "binding": {"platform": "sleeper", "source": "synthetic"}}


def sweep(targets=None, now=NOW, **kwargs):
    return store.create_sweep(uuid.uuid4().hex, [target()] if targets is None else targets,
                              started=user_data_lifecycle.snapshot(), now=now, **kwargs)


def claim(targets=None, now=NOW):
    return store.claim_target(sweep(targets, now=now), now=now)


def save(value=None, cards=None, now=NOW, **kwargs):
    value = value or claim(now=now)
    return store.save_inventory(value, payload={"cards": [{"trade_id": "synthetic-card"}] if cards is None else cards},
        dependency_receipt=RECEIPT, model_identity=MODEL, participants=value["participants"],
        created_at=now, expires_at=now + timedelta(hours=24), now=now, **kwargs)


def load(value=None, now=NOW, receipt=RECEIPT, model=MODEL):
    return store.load_inventory(value or scope(), dependency_receipt=receipt, model_identity=model, now=now)


def rows(engine, table):
    with engine.connect() as conn:
        return list(conn.execute(select(table)).mappings())


def test_default_dark_and_no_user_activity_writes(engine):
    assert [value for key, value, *_ in db._MODEL_CONFIG_DEFAULTS if key == "prepared_trade_inventory_enabled"] == [0.0]
    original = rows(engine, db.users_table)
    save()
    assert rows(engine, db.users_table) == original
    for table in (db.deck_impressions_table, db.deck_candidate_sets_table, db.user_events_table,
                  db.notifications_table, db.deck_outcomes_table):
        assert rows(engine, table) == []


def test_detached_roundtrip_full_order_and_empty_is_not_miss(engine):
    cards = [{"trade_id": str(i), "private": [i, 1.0, True]} for i in range(237)]
    inventory_id = save(cards=cards)
    cards[0]["private"].append("mutated")
    result = load()
    assert result["inventory_id"] == inventory_id
    assert len(result["payload"]["cards"]) == 237
    assert result["payload"]["cards"][0]["private"] == [0, 1.0, True]
    result["payload"]["cards"].reverse()
    assert load()["payload"]["cards"][0]["trade_id"] == "0"
    save(cards=[])
    assert load()["card_count"] == 0 and load()["payload"]["cards"] == []
    assert load(scope(request="missing")) is None


def test_parent_explicit_inventory_envelope_supported(engine):
    value = claim()
    store.save_inventory(value, payload={"inventory": {"cards": [{"trade_id": "a"}]}, "job_fields": {}},
        dependency_receipt=RECEIPT, model_identity=MODEL, participants=value["participants"],
        created_at=NOW, expires_at=NOW + timedelta(hours=1), now=NOW)
    assert load()["card_count"] == 1


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), {1: "a"}, ("a",), {"a"}, object()])
def test_hash_rejects_non_json_and_nonfinite(bad):
    with pytest.raises(store.InvalidArtifact):
        store.dependency_hash(bad)


def test_hash_preserves_types_and_semantic_array_order():
    assert store.dependency_hash({"a": 1, "b": 2}) == store.dependency_hash({"b": 2, "a": 1})
    assert len({store.dependency_hash(v) for v in [1, 1.0, True, "1", [1, 2], [2, 1]]}) == 6


def test_expiry_never_renews_and_prune_is_scoped(engine):
    inventory_id = save()
    initial = load()["expires_at"]
    assert load(now=NOW + timedelta(hours=23))["expires_at"] == initial
    assert load(now=NOW + timedelta(hours=24)) is None
    assert store.prune(now=NOW + timedelta(hours=24)) == 1
    assert not rows(engine, db.prepared_trade_inventories_table)
    assert not [r for r in rows(engine, db.prepared_trade_participants_table) if r["subject_id"] == inventory_id]


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(hours=24, seconds=1), timedelta(seconds=-1)])
def test_expiry_bound_rejected_not_silently_extended(engine, offset):
    value = claim()
    with pytest.raises(store.InvalidArtifact):
        store.save_inventory(value, payload={"cards": []}, dependency_receipt=RECEIPT, model_identity=MODEL,
            participants=value["participants"], created_at=NOW, expires_at=NOW + offset, now=NOW)


@pytest.mark.parametrize("change", ["scope", "receipt", "model"])
def test_exact_scope_source_and_model_required(engine, change):
    save()
    assert load(scope(request="different") if change == "scope" else None,
                receipt={"source_revision": 2} if change == "receipt" else RECEIPT,
                model={"generator": "different"} if change == "model" else MODEL) is None
    assert store.peek_inventory(scope(), now=NOW)["dependency_receipt"] == RECEIPT


@pytest.mark.parametrize("field,value", [("payload_sha256", "wrong"), ("card_count", 2),
    ("schema_version", 999), ("dependency_hash", "wrong"), ("model_hash", "wrong"),
    ("payload_json", '{"cards":[]'), ("user_id", "different"), ("created_at", "bad")])
def test_corrupt_or_partial_metadata_fails_closed(engine, field, value):
    save()
    with engine.begin() as conn:
        conn.execute(update(db.prepared_trade_inventories_table).values(**{field: value}))
    assert load() is None


def test_strict_decoder_rejects_duplicate_keys_and_bounded_bytes(engine, monkeypatch):
    with pytest.raises(store.InvalidArtifact):
        store._decode('{"a":1,"a":2}')
    value = claim()
    monkeypatch.setattr(store, "MAX_PAYLOAD_BYTES", 16)
    with pytest.raises(store.InvalidArtifact, match="byte limit"):
        save(value)
    assert not rows(engine, db.prepared_trade_inventories_table)


def test_sweep_idempotency_is_exact_and_status_has_no_identities(engine):
    key = uuid.uuid4().hex
    first = store.create_sweep(key, [target()], started=user_data_lifecycle.snapshot(), now=NOW)
    second = store.create_sweep(key, [target()], started=user_data_lifecycle.snapshot(), now=NOW)
    assert first == second
    with pytest.raises(store.InvalidArtifact, match="different cohort"):
        store.create_sweep(key, [target(scope(request="changed"))], started=user_data_lifecycle.snapshot(), now=NOW)
    result = store.sweep_status(first, now=NOW)
    assert result["target_count"] == 1 and result["counts"] == {"pending": 1}
    assert OWNER not in json.dumps(result) and PEER not in json.dumps(result)
    assert result["freshness_requires_source_revalidation"] is True


def test_reused_status_links_current_unexpired_inventory_without_renewing_it(engine):
    inventory_id = save()
    value = claim()
    store.complete_target(value, status="reused", now=NOW)
    status = store.sweep_status(value["sweep_id"], now=NOW)
    assert status["counts"] == {"reused": 1} and status["unexpired_artifacts"] == 1
    assert load()["inventory_id"] == inventory_id
    assert store.sweep_status(value["sweep_id"], now=NOW + timedelta(days=1))["unexpired_artifacts"] == 0


def test_global_one_claim_across_sweeps_and_threads(engine):
    first, second = sweep(), sweep()
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda sid: store.claim_target(sid, now=NOW), [first, second]))
    assert sum(value is not None for value in result) == 1
    active = next(value for value in result if value)
    store.complete_target(active, status="deferred", now=NOW)
    other = second if active["sweep_id"] == first else first
    assert store.claim_target(other, now=NOW) is not None


def test_concurrent_identical_sweep_key_creates_one_complete_cohort(engine):
    key = uuid.uuid4().hex
    def create(_):
        return store.create_sweep(key, [target()], started=user_data_lifecycle.snapshot(), now=NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(create, range(2)))
    assert result[0] == result[1]
    assert len(rows(engine, db.prepared_trade_sweeps_table)) == 1
    assert len(rows(engine, db.prepared_trade_targets_table)) == 1


def test_sweep_late_target_failure_rolls_back_denominator_and_bindings(engine):
    pages = []
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO prepared_trade_targets"):
            pages.append(1)
            if len(pages) == 2:
                raise RuntimeError("synthetic late target failure")
    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="late target"):
            sweep([target(), target(scope(league="second-league"))])
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert len(pages) == 2
    assert rows(engine, db.prepared_trade_sweeps_table) == []
    assert rows(engine, db.prepared_trade_targets_table) == []
    assert rows(engine, db.prepared_trade_participants_table) == []


def test_expired_worker_cannot_replace_recovered_inventory(engine, monkeypatch):
    sid = sweep()
    old = store.claim_target(sid, now=NOW, lease_seconds=1)
    restarted_engine = create_engine(str(engine.url), connect_args={"check_same_thread": False})
    monkeypatch.setattr(db, "engine", restarted_engine)
    try:
        new = store.claim_target(sid, now=NOW + timedelta(seconds=2))
        assert new["target_id"] == old["target_id"] and new["lease_token"] != old["lease_token"]
        new_id = save(new, now=NOW + timedelta(seconds=2))
        with pytest.raises(store.StaleWork):
            save(old, now=NOW + timedelta(seconds=3))
        assert load(now=NOW + timedelta(seconds=3))["inventory_id"] == new_id
    finally:
        restarted_engine.dispose()


def test_expired_retries_bounded_and_empty_sweep_complete(engine):
    sid = sweep(max_attempts=1)
    assert store.claim_target(sid, now=NOW, lease_seconds=1)
    assert store.claim_target(sid, now=NOW + timedelta(seconds=2)) is None
    assert store.sweep_status(sid, now=NOW)["counts"] == {"error": 1}
    assert store.sweep_status(sid, now=NOW)["status"] == "complete"
    assert store.sweep_status(sweep([]), now=NOW)["status"] == "complete"


def test_retry_availability_and_stop_revokes_active_claim(engine):
    sid = sweep()
    value = store.claim_target(sid, now=NOW)
    store.complete_target(value, status="source_error", reason="provider_unavailable",
                          retry_at=NOW + timedelta(minutes=1), now=NOW)
    assert store.claim_target(sid, now=NOW) is None
    retry = store.claim_target(sid, now=NOW + timedelta(minutes=1))
    assert retry
    assert store.stop_sweep(sid, now=NOW + timedelta(minutes=1))
    with pytest.raises(store.StaleWork):
        save(retry, now=NOW + timedelta(minutes=1))
    assert store.sweep_status(sid, now=NOW)["counts"] == {"cancelled": 1}


def test_failed_replacement_rolls_back_old_artifact_and_claim(engine):
    original = save()
    value = claim()
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO prepared_trade_participants"):
            raise RuntimeError("synthetic partial write")
    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="partial write"):
            save(value, cards=[{"trade_id": "replacement"}])
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert load()["inventory_id"] == original
    assert store.sweep_status(value["sweep_id"], now=NOW)["counts"] == {"running": 1}
    assert save(value) != original


def test_unknown_owners_never_created_and_account_only_existing_supported(engine):
    before = rows(engine, db.users_table)
    with pytest.raises(store.StaleWork, match="no longer exists"):
        sweep([target(scope(owner="unknown"), ["unknown"])])
    assert rows(engine, db.users_table) == before
    aid = "prepared-account"
    with engine.begin() as conn:
        conn.execute(insert(db.accounts_table).values(account_id=aid, created_at="2026-01-01"))
    uid = accounts.account_user_id(aid)
    value = claim([target(scope(owner=uid), [uid, PEER])])
    save(value)
    assert load(scope(owner=uid)) is not None
    assert rows(engine, db.users_table) == before


def test_all_consumed_participants_required_before_generation(engine):
    value = claim()
    with pytest.raises(store.StaleWork, match="before generation"):
        store.save_inventory(value, payload={"cards": []}, dependency_receipt=RECEIPT,
            model_identity=MODEL, participants=value["participants"] + ["unexpected-peer"],
            created_at=NOW, expires_at=NOW + timedelta(hours=1), now=NOW)


def test_owner_and_counterparty_deletion_removes_all_private_dependents(engine):
    save()
    active = claim()
    unrelated = sweep([target(scope(league="unrelated"), [OWNER])])
    counts = accounts.delete_user_data(PEER)
    assert counts["prepared_trade_inventories_deleted"] == 1
    assert counts["prepared_trade_targets_deleted"] == 2
    assert load() is None
    assert store.sweep_status(active["sweep_id"], now=NOW)["deleted_count"] == 1
    assert store.claim_target(unrelated, now=NOW)
    with pytest.raises(store.StaleWork):
        save(active)
    assert not any(r["participant_user_id"] == PEER for r in rows(engine, db.prepared_trade_participants_table))


def test_delete_then_recreate_identity_cannot_resurrect_original_claim(engine):
    value = claim()
    accounts.delete_user_data(OWNER)
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=OWNER, created_at="new-incarnation"))
    with pytest.raises(store.StaleWork):
        save(value)
    assert load() is None


def test_lifecycle_token_before_cohort_reads_rejects_deleted_alias(engine):
    started = user_data_lifecycle.snapshot()
    accounts.delete_user_data(PEER)
    with pytest.raises(store.StaleWork, match="revoked"):
        store.create_sweep(uuid.uuid4().hex, [target()], started=started, now=NOW)


def test_account_delete_late_failure_rolls_back_prepared_data(engine):
    original = save()
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM users"):
            raise RuntimeError("synthetic deletion failure")
    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            accounts.delete_user_data(PEER)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert load()["inventory_id"] == original


def test_export_retains_owned_metadata_without_prepared_payloads_or_live_tokens(engine):
    private_target = target()
    private_target["binding"]["private_counterparty"] = "target-only-counterparty-secret"
    value = claim([private_target])
    inventory_id = save(value, cards=[{"trade_id": "synthetic-card",
                                       "private_counterparty": "inventory-only-counterparty-secret"}])
    claim()
    adoption(inventory_id)
    stored_inventories = rows(engine, db.prepared_trade_inventories_table)
    stored_targets = rows(engine, db.prepared_trade_targets_table)
    assert "inventory-only-counterparty-secret" in store._unpack_payload(stored_inventories[0]["payload_json"])
    assert any("target-only-counterparty-secret" in row["payload_json"] for row in stored_targets)
    exported = accounts.export_user_data(OWNER)["tables"]
    assert len(exported["prepared_trade_inventories"]) == 1
    assert len(exported["prepared_trade_targets"]) == 2
    inventory = exported["prepared_trade_inventories"][0]
    assert inventory["inventory_id"] == inventory_id
    assert inventory["user_id"] == OWNER and inventory["league_id"] == scope().league_id
    assert inventory["card_count"] == 1
    assert inventory["payload_sha256"] == stored_inventories[0]["payload_sha256"]
    assert inventory["dependency_hash"] == stored_inventories[0]["dependency_hash"]
    assert all(row["user_id"] == OWNER and row["scope_key"] for row in exported["prepared_trade_targets"])
    assert all("payload_json" not in row for row in exported["prepared_trade_inventories"])
    assert all("payload_json" not in row for row in exported["prepared_trade_targets"])
    assert all("lease_token" not in row for row in exported["prepared_trade_targets"])
    assert all("adoption_token" not in row for row in exported["prepared_trade_inventories"])
    assert "counterparty-secret" not in json.dumps(exported)
    assert rows(engine, db.prepared_trade_inventories_table) == stored_inventories
    assert rows(engine, db.prepared_trade_targets_table) == stored_targets


def _insert_export_impression(engine, features):
    with engine.begin() as conn:
        conn.execute(insert(db.deck_impressions_table).values(
            impression_id="export-impression", user_id=OWNER, league_id=scope().league_id,
            deck_job_id="export-job", card_index=0, trade_hash="own-terms",
            features_json=features, propensity=1.0, served_at=NOW.isoformat()))


def test_export_strips_only_prepared_runtime_preserving_legacy_features_and_text_type(engine):
    legacy = {"partner_user_id": PEER, "legacy": [True, None, 1, 1.5, "own-data"],
              "nested": {"prepared_runtime": "unrelated-legacy-key"},
              "prepared_inventory_id": "own-inventory", "deck_source": "prepared_adoption"}
    features = dict(legacy, prepared_runtime={"proof": '{"tier":"runtime-only-counterparty-secret"}'})
    raw = json.dumps(features, indent=2)
    _insert_export_impression(engine, raw)
    original = rows(engine, db.deck_impressions_table)
    exported = accounts.export_user_data(OWNER)["tables"]["deck_impressions"][0]
    assert type(exported["features_json"]) is str
    assert json.loads(exported["features_json"]) == legacy
    assert exported["impression_id"] == "export-impression" and exported["trade_hash"] == "own-terms"
    assert "runtime-only-counterparty-secret" not in json.dumps(exported)
    assert rows(engine, db.deck_impressions_table) == original


@pytest.mark.parametrize("raw", [None, "", "not-json", "null", "[]", "3", '"legacy"',
                                '{ "legacy": true, "value": 1.0 }'])
def test_export_without_prepared_runtime_preserves_original_features_verbatim(engine, raw):
    _insert_export_impression(engine, raw)
    exported = accounts.export_user_data(OWNER)["tables"]["deck_impressions"][0]
    assert exported["features_json"] == raw
    assert type(exported["features_json"]) is type(raw)


def adoption(inventory_id, now=NOW, **kwargs):
    return store.claim_adoption(inventory_id, dependency_receipt=RECEIPT, model_identity=MODEL,
        publication={"served_at": now.isoformat(), "job_id": "synthetic-adoption"}, now=now, **kwargs)


def test_adoption_recovery_preserves_original_publication_and_durable_prefix(engine):
    existing, candidate, impressions = evidence_inventory(237)
    inventory_id = existing["inventory_id"]
    store.release_adoption(existing)
    first = adoption(inventory_id, lease_seconds=1)
    assert first["published_count"] == 0
    assert adoption(inventory_id) is None
    with pytest.raises(store.InvalidArtifact, match="non-durable"):
        store.checkpoint_adoption(first, published_count=30, expected_prefix=0, now=NOW)
    store.ensure_adoption_evidence(first, candidate_set=candidate, rows=impressions[:30], now=NOW)
    store.checkpoint_adoption(first, published_count=30, expected_prefix=0, now=NOW)
    recovered = adoption(inventory_id, now=NOW + timedelta(seconds=2))
    assert recovered["publication"] == first["publication"] and recovered["published_count"] == 30
    with pytest.raises(store.StaleWork):
        store.checkpoint_adoption(first, published_count=130, expected_prefix=30, now=NOW + timedelta(seconds=2))
    store.ensure_adoption_evidence(recovered, candidate_set=None, rows=impressions[30:], now=NOW + timedelta(seconds=2))
    with pytest.raises(store.StaleWork):
        store.checkpoint_adoption(recovered, published_count=130, expected_prefix=0, now=NOW + timedelta(seconds=2))
    store.checkpoint_adoption(recovered, published_count=237, expected_prefix=30,
                              complete=True, now=NOW + timedelta(seconds=2))
    assert adoption(inventory_id, now=NOW + timedelta(seconds=3))["published_count"] == 237


def test_adoption_replacement_deletion_and_receipt_mismatch_fail_closed(engine):
    inventory_id = save()
    assert store.claim_adoption(inventory_id, dependency_receipt={"changed": True}, model_identity=MODEL,
                                publication={}, now=NOW) is None
    value = adoption(inventory_id)
    save()
    with pytest.raises(store.StaleWork):
        store.checkpoint_adoption(value, published_count=1, expected_prefix=0, complete=True, now=NOW)
    replacement = load()["inventory_id"]
    value = adoption(replacement)
    accounts.delete_user_data(PEER)
    with pytest.raises(store.StaleWork):
        store.checkpoint_adoption(value, published_count=1, expected_prefix=0, now=NOW)


def test_named_negative_control_checksum_removal_exposes_corruption(engine, monkeypatch):
    save()
    with engine.begin() as conn:
        conn.execute(update(db.prepared_trade_inventories_table).values(payload_sha256="sabotaged"))
    assert load() is None
    original = store._verified
    def bypass(row, value, now):
        import hashlib
        row = dict(row)
        row["payload_sha256"] = hashlib.sha256(store._unpack_payload(row["payload_json"]).encode()).hexdigest()
        return original(row, value, now)
    monkeypatch.setattr(store, "_verified", bypass)
    with pytest.raises(AssertionError):
        assert load() is None


def evidence_inventory(count=3, with_candidate=True, mutations=None, diagnostics=None,
                       adopt_at=NOW, snapshot_edit=None):
    """Synthetic exact JSON evidence, without importing a generator/service."""
    cards = [{"runtime": {"trade_id": f"trade-{i}"}, "public": {"trade_id": f"trade-{i}"}}
             for i in range(count)]
    candidate = {"candidate_set_id": "prepared-candidate", "deck_job_id": "prepared-job", "user_id": OWNER,
                 "league_id": scope().league_id, "size": count, "set_hash": "synthetic-set-hash",
                 "candidates_json": "[]", "created_at": NOW.isoformat()} if with_candidate else None
    impressions = [{"impression_id": f"prepared-imp-{i}", "user_id": OWNER, "league_id": scope().league_id,
        "deck_job_id": "prepared-job", "card_index": i, "trade_hash": f"terms-{i}",
        "features_json": {"partner_user_id": PEER, "owner_request": {"shared": ["x"] * 1500}, "first_deck": True},
        "propensity": 1.0, "served_at": NOW.isoformat(), "valuation_json": '{"private":"original"}',
        "candidate_set_id": candidate["candidate_set_id"] if candidate else None,
        "candidate_set_size": count if candidate else None} for i in range(count)]
    if diagnostics is not None:
        for i, row in enumerate(impressions):
            row["features_json"]["owner_request"] = diagnostics(i)
    from backend.deck_diagnostics import compact_rows
    compacted, snapshots = compact_rows(impressions)
    if snapshot_edit is not None:
        snapshot_edit(snapshots)
    bundle = {"cards": cards, "job_id": "prepared-job", "candidate_set": candidate,
              "impressions": compacted, "snapshots": snapshots}
    value = claim()
    inventory_id = store.save_inventory(value, payload={"inventory": bundle, "mutations": mutations or []}, dependency_receipt=RECEIPT,
        model_identity=MODEL, participants=value["participants"], created_at=NOW,
        expires_at=NOW + timedelta(hours=24), now=NOW)
    adopted = adoption(inventory_id, now=adopt_at)
    for i, row in enumerate(impressions):
        row["served_at"] = adopt_at.isoformat()
        row["features_json"].pop("first_deck", None)
        row["features_json"].update(prepared_runtime=cards[i], prepared_inventory_id=inventory_id,
                                     deck_source="prepared_adoption")
    return adopted, candidate, impressions


def test_adoption_keeps_original_diagnostic_dag_across_30_and_100_card_batches(engine):
    from backend.deck_diagnostics import REFERENCE_KEY, compact_rows
    shared = {"long_shared": ["unchanged diagnostic"] * 100}
    diagnostic = lambda i: {"family": "first" if i <= 30 else "later", "shared": shared}
    served_at = NOW + timedelta(seconds=30)
    value, candidate, impressions = evidence_inventory(130, diagnostics=diagnostic, adopt_at=served_at)
    original = load()["payload"]["inventory"]
    frozen = {node["snapshot_id"]: node for node in original["snapshots"]}
    first_sid = json.loads(original["impressions"][0]["features_json"])["owner_request"][REFERENCE_KEY]
    later_sid = json.loads(original["impressions"][-1]["features_json"])["owner_request"][REFERENCE_KEY]
    # The unchanged compactor actually encodes the same first root differently
    # across these page contexts: inline child versus shared child reference.
    _, first_nodes = compact_rows(impressions[:30])
    _, later_nodes = compact_rows(impressions[30:])
    first_encoding = next(n for n in first_nodes if n["snapshot_id"] == first_sid)
    later_encoding = next(n for n in later_nodes if n["snapshot_id"] == first_sid)
    assert first_encoding["payload_json"] != later_encoding["payload_json"]
    store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions[:30], now=served_at)
    before = rows(engine, db.deck_diagnostic_snapshots_table)
    assert later_sid not in {r["snapshot_id"] for r in before}
    store.ensure_adoption_evidence(value, candidate_set=None, rows=impressions[30:], now=served_at)
    persisted = rows(engine, db.deck_diagnostic_snapshots_table)
    assert {r["snapshot_id"]: dict(r) for r in persisted} == frozen
    assert all(r["created_at"] == NOW.isoformat() for r in persisted)
    assert all(r["served_at"] == served_at.isoformat() for r in rows(engine, db.deck_impressions_table))
    assert len(rows(engine, db.deck_impressions_table)) == 130
    for row in impressions:
        assert db.load_deck_diagnostics(row["impression_id"], OWNER) == row["features_json"]
    assert store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions,
        now=served_at) == {"candidate_sets": 0, "snapshots": 0, "impressions": 0}


@pytest.mark.parametrize("fault", ["checksum", "user_scope", "job_scope", "dangling", "cycle",
                                  "timestamp", "duplicate", "reference_shape", "unknown_column"])
def test_prepared_snapshot_closure_rejects_corruption_before_any_publication(engine, fault):
    from backend.deck_diagnostics import REFERENCE_KEY
    def damage(nodes):
        node = nodes[-1]
        if fault == "checksum":
            node["payload_json"] = '{"changed":true}'
        elif fault == "user_scope":
            node["user_id"] = PEER
        elif fault == "job_scope":
            node["deck_job_id"] = "foreign-job"
        elif fault == "dangling":
            node["payload_json"] = json.dumps({REFERENCE_KEY: "missing"})
        elif fault == "cycle":
            node["payload_json"] = json.dumps({REFERENCE_KEY: node["snapshot_id"]})
        elif fault == "timestamp":
            node["created_at"] = "2026-09-22"
        elif fault == "duplicate":
            nodes.append(dict(node))
        elif fault == "reference_shape":
            node["payload_json"] = json.dumps({REFERENCE_KEY: node["snapshot_id"], "other": True})
        elif fault == "unknown_column":
            node["unrecognized"] = "no"
    value, candidate, impressions = evidence_inventory(snapshot_edit=damage)
    with pytest.raises(store.InvalidArtifact):
        store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    for table in (db.deck_candidate_sets_table, db.deck_diagnostic_snapshots_table, db.deck_impressions_table):
        assert not rows(engine, table)


def test_invalid_later_closure_preserves_only_the_committed_prefix(engine):
    shared = {"long_shared": ["unchanged diagnostic"] * 100}
    diagnostic = lambda i: {"family": "first" if i < 30 else "later", "shared": shared}
    def damage(nodes):
        for node in nodes:
            if json.loads(node["payload_json"]).get("family") == "later":
                node["payload_json"] = '{"changed":true}'
    value, candidate, impressions = evidence_inventory(130, diagnostics=diagnostic, snapshot_edit=damage)
    store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions[:30], now=NOW)
    tables = (db.deck_candidate_sets_table, db.deck_diagnostic_snapshots_table, db.deck_impressions_table)
    before = [rows(engine, table) for table in tables]
    with pytest.raises(store.InvalidArtifact, match="checksum"):
        store.ensure_adoption_evidence(value, candidate_set=None, rows=impressions[30:], now=NOW)
    assert [rows(engine, table) for table in tables] == before
    assert len(before[-1]) == 30


def test_atomic_idempotent_evidence_roundtrip_preserves_snapshots_and_private_runtime(engine):
    value, candidate, impressions = evidence_inventory(237)
    first = store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions[:30], now=NOW)
    assert first["impressions"] == 30 and first["candidate_sets"] == 1 and first["snapshots"] > 0
    second = store.ensure_adoption_evidence(value, candidate_set=None, rows=impressions[30:], now=NOW)
    assert second["impressions"] == 207
    assert store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions[:30], now=NOW) == {
        "candidate_sets": 0, "snapshots": 0, "impressions": 0}
    assert len(rows(engine, db.deck_impressions_table)) == 237
    expanded = db.load_deck_diagnostics(impressions[0]["impression_id"], OWNER)
    assert expanded == impressions[0]["features_json"]
    for table in (db.trade_impressions_table, db.deck_outcomes_table, db.user_events_table, db.notifications_table):
        assert not rows(engine, table)


@pytest.mark.parametrize("field,new_value", [("impression_id", "unreserved"), ("trade_hash", "changed-terms"),
    ("valuation_json", "{}"), ("served_at", "2027-01-01T00:00:00+00:00"), ("user_id", PEER), ("card_index", 8)])
def test_evidence_exact_binding_rejects_changed_prepared_terms(engine, field, new_value):
    value, candidate, impressions = evidence_inventory()
    impressions[0][field] = new_value
    with pytest.raises(store.InvalidArtifact):
        store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    assert not rows(engine, db.deck_impressions_table)
    assert not rows(engine, db.deck_candidate_sets_table)


def test_evidence_rejects_forged_runtime_and_changed_original_features(engine):
    value, candidate, impressions = evidence_inventory()
    impressions[0]["features_json"]["prepared_runtime"]["runtime"]["trade_id"] = "forged"
    with pytest.raises(store.InvalidArtifact, match="frozen evidence"):
        store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    assert not rows(engine, db.deck_impressions_table)


def test_existing_evidence_id_conflict_rejected_without_overwrite(engine):
    value, candidate, impressions = evidence_inventory()
    store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    with engine.begin() as conn:
        conn.execute(update(db.deck_impressions_table).where(db.deck_impressions_table.c.impression_id == "prepared-imp-0")
                     .values(valuation_json='{"conflicting":true}'))
    with pytest.raises(store.InvalidArtifact, match="different content"):
        store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    assert rows(engine, db.deck_impressions_table)[0]["valuation_json"] == '{"conflicting":true}'


def test_candidate_and_snapshot_dependencies_conflict_or_missing_fail_closed(engine):
    value, candidate, impressions = evidence_inventory()
    with pytest.raises(store.InvalidArtifact, match="dependency not durably"):
        store.ensure_adoption_evidence(value, candidate_set=None, rows=impressions, now=NOW)
    store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    with engine.begin() as conn:
        conn.execute(update(db.deck_diagnostic_snapshots_table).values(payload_json='{"corrupt":true}'))
    with pytest.raises(store.InvalidArtifact, match="different content"):
        store.ensure_adoption_evidence(value, candidate_set=None, rows=impressions, now=NOW)


@pytest.mark.parametrize("field", ["user_id", "deck_job_id", "created_at", "payload_json"])
def test_existing_snapshot_scope_time_and_transport_remain_byte_exact(engine, field):
    value, candidate, impressions = evidence_inventory()
    store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions[:1], now=NOW)
    snapshot = rows(engine, db.deck_diagnostic_snapshots_table)[0]
    changed = {"user_id": PEER, "deck_job_id": "foreign-job",
               "created_at": (NOW + timedelta(seconds=1)).isoformat(),
               "payload_json": " " + snapshot["payload_json"]}[field]
    with engine.begin() as conn:
        conn.execute(update(db.deck_diagnostic_snapshots_table).where(
            db.deck_diagnostic_snapshots_table.c.snapshot_id == snapshot["snapshot_id"])
            .values(**{field: changed}))
    tables = (db.deck_candidate_sets_table, db.deck_diagnostic_snapshots_table, db.deck_impressions_table)
    before = [rows(engine, table) for table in tables]
    with pytest.raises(store.InvalidArtifact, match="different content"):
        store.ensure_adoption_evidence(value, candidate_set=None, rows=impressions[1:], now=NOW)
    assert [rows(engine, table) for table in tables] == before
    assert len(before[-1]) == 1


def test_evidence_late_page_failure_rolls_back_candidate_snapshots_and_all_rows(engine):
    value, candidate, impressions = evidence_inventory(237)
    pages = []
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO deck_impressions"):
            pages.append(1)
            if len(pages) == 2:
                raise RuntimeError("synthetic second page failure")
    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="second page"):
            store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert len(pages) == 2
    assert not rows(engine, db.deck_impressions_table)
    assert not rows(engine, db.deck_candidate_sets_table)
    assert not rows(engine, db.deck_diagnostic_snapshots_table)
    assert store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)["impressions"] == 237


def test_expired_or_deleted_adoption_cannot_write_late_evidence(engine):
    value, candidate, impressions = evidence_inventory()
    with pytest.raises(store.StaleWork):
        store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW + timedelta(seconds=121))
    accounts.delete_user_data(PEER)
    with pytest.raises(store.StaleWork):
        store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    assert not rows(engine, db.deck_impressions_table)


def test_named_negative_control_idempotency_conflict_check_is_load_bearing(engine, monkeypatch):
    value, candidate, impressions = evidence_inventory()
    store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    with engine.begin() as conn:
        conn.execute(update(db.deck_impressions_table).values(valuation_json="changed"))
    with pytest.raises(store.InvalidArtifact):
        store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    monkeypatch.setattr(store, "_ensure_exact_rows", lambda *args: 0)
    with pytest.raises(pytest.fail.Exception):
        with pytest.raises(store.InvalidArtifact):
            store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)


def test_resumable_sweeps_include_delayed_and_expired_work_but_not_stopped(engine):
    sid = sweep()
    value = store.claim_target(sid, now=NOW)
    store.complete_target(value, status="deferred", retry_at=NOW + timedelta(minutes=5), now=NOW)
    stopped = sweep(now=NOW + timedelta(seconds=1))
    store.stop_sweep(stopped, now=NOW)
    assert store.resumable_sweeps(now=NOW) == [sid]
    state = store.sweep_status(sid, now=NOW)
    assert state["remaining_count"] == 1 and state["next_retry_at"] == store._iso(NOW + timedelta(minutes=5))
    assert state["status"] == "running"


def suppression(engine, **changes):
    values = {"user_id": OWNER, "league_id": scope().league_id, "centerpiece_id": "synthetic-centerpiece",
              "shape_bucket": "1x1", "created_at": NOW.isoformat(), "declined_at": (NOW - timedelta(days=2)).isoformat(),
              "expires_at": (NOW - timedelta(days=1)).isoformat(), "retested_at": None,
              "retest_trade_hash": None, "lifted_at": None}
    values.update(changes)
    with engine.begin() as conn:
        row_id = conn.execute(insert(db.deck_suppressions_table).values(**values)).inserted_primary_key[0]
    before = {key: values[key] for key in ("declined_at", "expires_at", "retested_at", "retest_trade_hash", "lifted_at")}
    return row_id, before


def test_retest_consumed_only_with_exact_published_card_and_retry_idempotent(engine):
    row_id, before = suppression(engine)
    mutation = {"id": row_id, "kind": "retest", "before": before, "trade_id": "trade-2", "trade_hash": "terms-2"}
    value, candidate, impressions = evidence_inventory(mutations=[mutation])
    assert rows(engine, db.deck_suppressions_table)[0]["retested_at"] is None
    store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions[:2], now=NOW)
    assert rows(engine, db.deck_suppressions_table)[0]["retested_at"] is None
    store.ensure_adoption_evidence(value, candidate_set=None, rows=impressions[2:], now=NOW)
    after = rows(engine, db.deck_suppressions_table)[0]
    assert after["retested_at"] == value["publication"]["served_at"] and after["retest_trade_hash"] == "terms-2"
    assert store.ensure_adoption_evidence(value, candidate_set=None, rows=impressions[2:], now=NOW)["impressions"] == 0
    assert rows(engine, db.deck_suppressions_table)[0] == after


@pytest.mark.parametrize("change", ["missing", "lifted", "other_scope", "changed_hash"])
def test_suppression_concurrent_change_rolls_back_all_adoption_evidence(engine, change):
    row_id, before = suppression(engine)
    mutation = {"id": row_id, "kind": "retest", "before": before, "trade_id": "trade-0", "trade_hash": "terms-0"}
    value, candidate, impressions = evidence_inventory(mutations=[mutation])
    with engine.begin() as conn:
        if change == "missing":
            conn.execute(delete(db.deck_suppressions_table))
        else:
            conn.execute(update(db.deck_suppressions_table).values(**{
                "lifted": {"lifted_at": NOW.isoformat()}, "other_scope": {"user_id": PEER},
                "changed_hash": {"retest_trade_hash": "competing-retet"}}[change]))
    with pytest.raises(store.StaleWork):
        store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    assert not rows(engine, db.deck_impressions_table)
    assert not rows(engine, db.deck_candidate_sets_table)
    assert not rows(engine, db.deck_diagnostic_snapshots_table)


def test_resuppress_first_publication_only_and_empty_inventory_supported(engine):
    row_id, before = suppression(engine, retested_at=NOW.isoformat(), retest_trade_hash="prior-retest")
    mutation = {"id": row_id, "kind": "resuppress", "before": before,
                "passed_at": NOW.isoformat(), "expires_at": (NOW + timedelta(days=3)).isoformat()}
    value, candidate, impressions = evidence_inventory(count=0, mutations=[mutation])
    store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    updated = rows(engine, db.deck_suppressions_table)[0]
    assert updated["declined_at"] == NOW.isoformat() and updated["retested_at"] is None
    assert updated["expires_at"] == mutation["expires_at"]
    store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions, now=NOW)
    store.checkpoint_adoption(value, published_count=0, expected_prefix=0, complete=True, now=NOW)


def test_original_adoption_metadata_readback_has_no_lease_token(engine):
    value, candidate, impressions = evidence_inventory()
    store.ensure_adoption_evidence(value, candidate_set=candidate, rows=impressions[:1], now=NOW)
    store.checkpoint_adoption(value, published_count=1, expected_prefix=0, now=NOW)
    peek = store.peek_inventory(scope(), now=NOW)
    assert peek["publication"] == value["publication"] and peek["published_count"] == 1
    assert "adoption_token" not in peek and "token" not in peek


def test_frozen_aggregate_coverage_survives_restart_and_excludes_identity_values(engine):
    expected = {"app_users": 10, "eligible": 3, "source_failures": 2,
                "discovery_complete": False, "reasons": {"no_known_team": 5}}
    sid = store.create_sweep("coverage-key", [], started=user_data_lifecycle.snapshot(), now=NOW, coverage=expected)
    expected["app_users"] = 999
    assert store.sweep_status(sid, now=NOW)["coverage"]["app_users"] == 10
    with pytest.raises(store.InvalidArtifact, match="non-identifying"):
        store.create_sweep("bad-coverage", [], started=user_data_lifecycle.snapshot(), now=NOW, coverage={"user_id": OWNER})


def test_missing_participant_index_rejects_reuse_and_adoption(engine):
    inventory_id = save()
    with engine.begin() as conn:
        conn.execute(delete(db.prepared_trade_participants_table).where(
            db.prepared_trade_participants_table.c.subject_kind == "inventory",
            db.prepared_trade_participants_table.c.participant_user_id == PEER))
    assert load() is None
    with pytest.raises(store.InvalidArtifact, match="deletion index"):
        adoption(inventory_id)


def test_corrupt_frozen_publication_metadata_fails_closed(engine):
    inventory_id = save()
    value = adoption(inventory_id)
    store.release_adoption(value)
    with engine.begin() as conn:
        conn.execute(update(db.prepared_trade_inventories_table).values(adoption_json='{"served_at":"forged"}'))
    assert store.peek_inventory(scope(), now=NOW) is None
    assert adoption(inventory_id) is None


def test_real_payload_lane_bundle_crosses_durable_writer_without_repricings(engine):
    from backend.tests.test_prepared_trade_payload import make_bundle
    from backend.prepared_trade_payload import restore_inventory
    bundle, cards, _ = make_bundle(3, with_candidates=True)
    uid, lid = bundle["user_id"], bundle["league_id"]
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=uid, created_at="2026-01-01"))
    value_scope = scope(uid, lid)
    value = claim([target(value_scope, [uid, PEER])])
    inventory_id = store.save_inventory(value, payload={"inventory": bundle}, dependency_receipt=RECEIPT,
        model_identity=MODEL, participants=value["participants"], created_at=NOW,
        expires_at=NOW + timedelta(hours=1), now=NOW)
    value = adoption(inventory_id)
    inventory = restore_inventory(bundle, user_id=uid, league_id=lid, now=NOW)
    batch = next(inventory.batches(served_at=value["publication"]["served_at"]))
    store.ensure_adoption_evidence(value, candidate_set=batch["candidate_set"], rows=batch["impression_rows"], now=NOW)
    store.checkpoint_adoption(value, published_count=3, expected_prefix=0, complete=True, now=NOW)
    durable = rows(engine, db.deck_impressions_table)
    assert [row["valuation_json"] for row in durable] == [row["valuation_json"] for row in batch["impression_rows"]]
    assert len(durable) == len(cards) == 3


def test_large_repetitive_inventory_compressed_sql_value_and_lossless_logical_hash(engine):
    """3500 synthetic ordered cards exceed the previous observed28MB SQL hazard."""
    cards = [{"trade_id": f"synthetic-{i}", "frozen_evidence": "valuation-proof-" * 700}
             for i in range(3500)]
    lengths = []
    def measure(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO prepared_trade_inventories"):
            assert not executemany
            lengths.append(sum(len(value.encode()) for value in parameters if isinstance(value, str)))
    event.listen(engine, "before_cursor_execute", measure)
    try:
        inventory_id = save(cards=cards)
    finally:
        event.remove(engine, "before_cursor_execute", measure)
    row = rows(engine, db.prepared_trade_inventories_table)[0]
    assert row["payload_json"].startswith(store.STORAGE_PREFIX)
    logical = store._artifact_text(row)
    assert len(logical.encode()) > 28_000_000
    assert len(lengths) == 1 and lengths[0] < store.MAX_STORED_PAYLOAD_BYTES + 1024
    assert len(row["payload_json"]) < 250_000
    restored = load()
    assert restored["inventory_id"] == inventory_id and restored["payload"]["cards"] == cards
    assert row["payload_sha256"] == store.dependency_hash(json.loads(logical))


@pytest.mark.parametrize("kind", ["invalid_base64", "truncated", "trailing", "unsupported", "wrong_checksum"])
def test_corrupt_compressed_inventory_is_never_reused(engine, kind):
    import base64
    save()
    row = rows(engine, db.prepared_trade_inventories_table)[0]
    raw = base64.b64decode(row["payload_json"][len(store.STORAGE_PREFIX):])
    if kind == "invalid_base64":
        corrupted = store.STORAGE_PREFIX + "invalid!"
    elif kind == "truncated":
        corrupted = store.STORAGE_PREFIX + base64.b64encode(raw[:-2]).decode()
    elif kind == "trailing":
        corrupted = store.STORAGE_PREFIX + base64.b64encode(raw + b"trailing").decode()
    elif kind == "unsupported":
        corrupted = "prepared-unknown-2:" + row["payload_json"]
    else:
        corrupted = store._pack_payload(store._artifact_text(row).replace("synthetic-card", "different-card"))
    with engine.begin() as conn:
        conn.execute(update(db.prepared_trade_inventories_table).values(payload_json=corrupted))
    assert load() is None
    assert adoption(row["inventory_id"]) is None


def test_decompression_bomb_stops_at_decoded_limit_without_materializing_whole_input(monkeypatch):
    import base64
    import zlib
    compressed = zlib.compress(b"x" * 1_000_000)
    monkeypatch.setattr(store, "MAX_PAYLOAD_BYTES", 4096)
    with pytest.raises(store.InvalidArtifact, match="compression stream"):
        store._unpack_payload(store.STORAGE_PREFIX + base64.b64encode(compressed).decode())


def test_encoded_size_failure_preserves_old_artifact_and_running_claim(engine, monkeypatch):
    old = save()
    value = claim()
    monkeypatch.setattr(store, "MAX_STORED_PAYLOAD_BYTES", 80)
    with pytest.raises(store.InvalidArtifact, match="SQL byte limit"):
        save(value)
    assert rows(engine, db.prepared_trade_inventories_table)[0]["inventory_id"] == old
    assert store.sweep_status(value["sweep_id"], now=NOW)["counts"] == {"running": 1}


def test_small_legacy_plain_json_is_readable_with_same_checksum(engine):
    save()
    row = rows(engine, db.prepared_trade_inventories_table)[0]
    raw = store._artifact_text(row)
    with engine.begin() as conn:
        conn.execute(update(db.prepared_trade_inventories_table).values(payload_json=raw))
    assert load()["payload"]["cards"] == [{"trade_id": "synthetic-card"}]


def test_named_negative_control_unbounded_decompressor_breaks_bomb_guard(monkeypatch):
    import base64
    import zlib
    encoded = store.STORAGE_PREFIX + base64.b64encode(zlib.compress(b"x" * 1_000_000)).decode()
    monkeypatch.setattr(store, "MAX_PAYLOAD_BYTES", 4096)
    with pytest.raises(store.InvalidArtifact):
        store._unpack_payload(encoded)
    monkeypatch.setattr(store, "_unpack_payload", lambda value: zlib.decompress(
        base64.b64decode(value[len(store.STORAGE_PREFIX):])).decode())
    with pytest.raises(pytest.fail.Exception):
        with pytest.raises(store.InvalidArtifact):
            store._unpack_payload(encoded)
