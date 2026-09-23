"""Independent real-stage lifecycle, corruption and exact-prefix controls."""
from copy import deepcopy
from datetime import timedelta
import json
import uuid

import pytest
from sqlalchemy import event, insert, update

from backend import accounts, database as db, prepared_trade_store as legacy
from backend import prepared_trade_store_v2 as store, prepared_trade_payload_v2 as codec
from backend.tests.test_prepared_trade_store import NOW, RECEIPT, MODEL, claim, rows, target
from backend.tests.test_prepared_trade_store_v2 import engine
from backend.tests.test_prepared_trade_payload import make_cards, public, rows as evidence_rows, isolated_config


@pytest.fixture
def real_stage(engine, monkeypatch):
    clock = legacy._time
    monkeypatch.setattr(legacy, "_time", lambda value=None: clock(NOW if value is None else value))

    def create(count=3, *, seal=True, private="independent-private-marker"):
        cards = make_cards(count)
        uid, lid, peer = cards[0].proposing_user_id, cards[0].league_id, cards[0].target_user_id
        with engine.begin() as conn:
            for actor in (uid, peer):
                if not conn.execute(db.users_table.select().where(db.users_table.c.sleeper_user_id == actor)).first():
                    conn.execute(insert(db.users_table).values(sleeper_user_id=actor, created_at="2026-01-01"))
        scope = legacy.InventoryScope(uid, lid, uid, "1qb_ppr", "independent-review")
        admitted = claim([target(scope, [uid, peer])], now=NOW)
        stage = store.begin_inventory(admitted, dependency_receipt=RECEIPT, model_identity=MODEL,
            participants=admitted["participants"], created_at=NOW, expires_at=NOW + timedelta(hours=20), now=NOW)
        tag = uuid.uuid4().hex
        job = "review-" + tag
        for index, card in enumerate(cards):
            card.trade_id = f"{tag}-trade-{index}"
        originals = evidence_rows(cards)
        for index, row in enumerate(originals):
            row.update(deck_job_id=job, impression_id=f"{tag}-impression-{index}")
            row["features_json"]["owner_request"]["private_review_marker"] = private
        sink = codec.PagedPreparedEvidenceCapture(stage=stage, user_id=uid, league_id=lid, job_id=job)
        sink.impressions(originals)
        completion = sink.finish(cards, (public(card) for card in cards))
        metadata = {**completion, "generation_job_id": job, "mutations": [],
                    "job_fields": {}, "target": {"private_review_marker": private}}
        store.finish_metadata(stage, metadata=metadata, now=NOW)
        if seal:
            store.seal_inventory(stage, completion=completion, dependency_receipt=RECEIPT,
                                 model_identity=MODEL, now=NOW)
        return {"stage": stage, "scope": scope, "completion": completion,
                "cards": cards, "originals": originals, "peer": peer, "owner": uid}
    return create


def _adopt(info, *, now=NOW, lease_seconds=120):
    return store.claim_adoption(info["stage"].inventory_id, dependency_receipt=RECEIPT,
        model_identity=MODEL, publication={"served_at": now.isoformat()}, now=now, lease_seconds=lease_seconds)


def _batches(info, claim, *, first=1, rest=1):
    inventory = codec.restore_inventory(store.peek_inventory(info["scope"], now=NOW),
        user_id=info["owner"], league_id=info["scope"].league_id, now=NOW)
    return inventory.batches(**claim["publication"], first_batch_size=first, batch_size=rest)


def _commit(claim, batch, *, now=NOW):
    start, end = batch["cursor_before"], batch["cursor_after"]
    return store.ensure_adoption_evidence(claim, candidate_set=batch["candidate_set"],
        rows=batch["impression_rows"], ordinal_start=start["cards"], ordinal_end=end["cards"],
        ghost_start=start["ghosts"], ghost_end=end["ghosts"], now=now)


def test_store_encode_rejects_oversize_before_full_json_encoding(monkeypatch):
    monkeypatch.setattr(store, "MAX_PAGE_LOGICAL_BYTES", 128)
    monkeypatch.setattr(legacy, "_encode", lambda *a, **k: pytest.fail("encoded oversized private object"))
    with pytest.raises(ValueError, match="bytes|limit|budget"):
        store._encode({"oversized": "x" * 129})


def test_store_decode_rejects_structural_budget_before_json_allocation(monkeypatch):
    packed = store._encode([{"key": index} for index in range(100)])
    monkeypatch.setattr(codec, "MAX_PARSED_NODES", 20)
    monkeypatch.setattr(json, "loads", lambda *a, **k: pytest.fail("allocated oversized JSON graph"))
    with pytest.raises(ValueError, match="complexity|budget"):
        store._decode(packed)


def test_actual_counterparty_delete_removes_staging_sealed_retired_and_fences_old_writes(real_stage, engine):
    retired = real_stage(private="retired-counterparty-secret")
    sealed = real_stage(private="sealed-counterparty-secret")
    adoption = _adopt(sealed)
    prefetched = next(_batches(sealed, adoption))
    staging = real_stage(seal=False, private="staging-counterparty-secret")
    before = rows(engine, store.M)
    assert {row["state"] for row in before} == {"staging", "sealed", "retired"}
    assert rows(engine, store.P) and rows(engine, store.N)
    exported = accounts.export_user_data(sealed["owner"])["tables"]
    assert "counterparty-secret" not in json.dumps(exported)
    manifests = exported["prepared_trade_manifests_v2"]
    assert len(manifests) == 3
    for manifest in manifests:
        assert not {"generation_token", "adoption_token", "header_json", "metadata_json",
                    "adoption_json"} & set(manifest)
    assert not exported.get("prepared_trade_pages_v2") and not exported.get("prepared_trade_nodes_v2")
    assert before == rows(engine, store.M)
    accounts.delete_user_data(sealed["peer"])
    assert not rows(engine, store.M) and not rows(engine, store.P) and not rows(engine, store.N)
    assert store.peek_inventory(sealed["scope"], now=NOW) is None
    assert store.peek_inventory(retired["scope"], now=NOW) is None
    with pytest.raises(legacy.StaleWork):
        _commit(adoption, prefetched)
    assert not rows(engine, db.deck_impressions_table)
    with pytest.raises(legacy.StaleWork):
        store.append_page(staging["stage"], kind="cards", page_index=1, ordinal_start=3,
                          records=[{"private": "deleted actor"}], now=NOW)
    with pytest.raises(legacy.StaleWork):
        store.seal_inventory(staging["stage"], completion=staging["completion"],
                             dependency_receipt=RECEIPT, model_identity=MODEL, now=NOW)


@pytest.mark.parametrize("kind", ["cards", "admission"])
def test_prefetched_corrupt_page_cannot_commit_suffix_or_advance_prefix(real_stage, engine, kind):
    info = real_stage()
    adoption = _adopt(info)
    batches = _batches(info, adoption)
    first = next(batches)
    _commit(adoption, first)
    store.checkpoint_adoption(adoption, published_count=1, expected_prefix=0, now=NOW)
    adoption["published_count"] = 1
    before = [dict(row) for row in rows(engine, db.deck_impressions_table)]
    second = next(batches)  # Valid prefetched native terms before corruption.
    page = next(row for row in rows(engine, store.P) if row["kind"] == kind)
    records = store._decode(page)
    if kind == "cards":
        records[1]["owner_evaluation"]["snapshot_json"] = "{}"
    else:
        records[1]["source_like_impression_id"] = "forged-after-prefetch"
    # Even an attacker changing the local checksum alongside bytes cannot
    # make a different page satisfy the original sealed-root path.
    with engine.begin() as conn:
        conn.execute(update(store.P).where(store.P.c.inventory_id == info["stage"].inventory_id,
            store.P.c.kind == kind, store.P.c.page_index == page["page_index"]).values(**store._encode(records)))
    with pytest.raises(legacy.InvalidArtifact):
        _commit(adoption, second)
    assert before == [dict(row) for row in rows(engine, db.deck_impressions_table)]
    manifest, = rows(engine, store.M)
    assert manifest["adoption_prefix"] == 1


def test_activation_sql_failure_restores_previous_active_root_and_keeps_stage_unready(real_stage, engine):
    prior = real_stage()
    original_header = store.peek_inventory(prior["scope"], now=NOW).header
    replacement = real_stage(seal=False)
    failures = []

    def fail_activation(_conn, _cursor, statement, _parameters, context, _many):
        if (statement.startswith("UPDATE prepared_trade_manifests_v2") and any(
                values.get("state") == "sealed" for values in context.compiled_parameters)):
            failures.append(True)
            raise RuntimeError("synthetic failure after old-root retirement")

    event.listen(engine, "before_cursor_execute", fail_activation)
    try:
        with pytest.raises(RuntimeError, match="old-root retirement"):
            store.seal_inventory(replacement["stage"], completion=replacement["completion"],
                dependency_receipt=RECEIPT, model_identity=MODEL, now=NOW)
    finally:
        event.remove(engine, "before_cursor_execute", fail_activation)
    assert failures == [True]
    assert store.peek_inventory(prior["scope"], now=NOW).header == original_header
    manifests = {row["inventory_id"]: row for row in rows(engine, store.M)}
    assert manifests[replacement["stage"].inventory_id]["state"] == "validating"
    assert manifests[replacement["stage"].inventory_id]["active_scope_key"] is None
    assert store.abort_inventory(replacement["stage"], now=NOW) == 1
    assert {row["inventory_id"] for row in rows(engine, store.P)} == {prior["stage"].inventory_id}


def test_replacement_root_fences_original_reader_claim_and_checkpoint(real_stage, engine):
    prior = real_stage()
    reader = store.peek_inventory(prior["scope"], now=NOW)
    adopted = _adopt(prior)
    batch = next(_batches(prior, adopted))
    _commit(adopted, batch)
    original_evidence = [dict(row) for row in rows(engine, db.deck_impressions_table)]
    replacement = real_stage()
    assert store.peek_inventory(prior["scope"], now=NOW).inventory_id == replacement["stage"].inventory_id
    with pytest.raises(legacy.StaleWork):
        reader.read_cards(0, 1)
    with pytest.raises(legacy.StaleWork):
        store.checkpoint_adoption(adopted, published_count=1, expected_prefix=0, now=NOW)
    assert original_evidence == [dict(row) for row in rows(engine, db.deck_impressions_table)]


def test_evidence_before_checkpoint_crash_recovers_exact_ids_with_new_partition(real_stage, engine):
    info = real_stage(4)
    first = _adopt(info, lease_seconds=1)
    first_batch = next(_batches(info, first, first=2))
    _commit(first, first_batch)
    before = {row["impression_id"]: dict(row) for row in rows(engine, db.deck_impressions_table)}
    manifest, = rows(engine, store.M)
    resumed_at = legacy._time(manifest["adoption_lease_until"]) + timedelta(seconds=1)
    recovered = _adopt(info, now=resumed_at)
    assert recovered["token"] != first["token"] and recovered["published_count"] == 0
    assert recovered["publication"] == first["publication"]
    prefix = 0
    for batch in _batches(info, recovered, first=1, rest=3):
        _commit(recovered, batch, now=resumed_at)
        end = batch["cursor_after"]["cards"]
        store.checkpoint_adoption(recovered, published_count=end, expected_prefix=prefix,
            complete=end == 4, now=resumed_at)
        prefix = recovered["published_count"] = end
    durable = {row["impression_id"]: dict(row) for row in rows(engine, db.deck_impressions_table)}
    assert len(durable) == 4 and all(durable[key] == value for key, value in before.items())
    assert {row["served_at"] for row in durable.values()} == {first["publication"]["served_at"]}
    assert not rows(engine, db.deck_outcomes_table) and not rows(engine, db.trade_decisions_table)


def test_retire_invalid_root_is_exact_and_preserves_committed_evidence_and_private_artifact(real_stage, engine):
    info = real_stage()
    adopted = _adopt(info)
    batches = _batches(info, adopted)
    first = next(batches)
    _commit(adopted, first)
    store.checkpoint_adoption(adopted, published_count=1, expected_prefix=0, now=NOW)
    adopted["published_count"] = 1
    second = next(batches)
    original_manifest, = rows(engine, store.M)
    original_pages = rows(engine, store.P)
    original_nodes = rows(engine, store.N)
    original_evidence = rows(engine, db.deck_impressions_table)
    inventory_id, root = original_manifest["inventory_id"], original_manifest["root_sha256"]
    assert not store.retire_invalid_inventory(inventory_id, "0" * 64)
    assert rows(engine, store.M) == [original_manifest]
    assert store.retire_invalid_inventory(inventory_id, root)
    retired, = rows(engine, store.M)
    assert retired["state"] == "retired" and retired["active_scope_key"] is None
    assert retired["adoption_token"] is None and retired["adoption_lease_until"] is None
    for key in original_manifest.keys() - {"state", "active_scope_key", "adoption_token", "adoption_lease_until"}:
        assert retired[key] == original_manifest[key], key
    assert rows(engine, store.P) == original_pages
    assert rows(engine, store.N) == original_nodes
    assert rows(engine, db.deck_impressions_table) == original_evidence
    assert store.peek_inventory(info["scope"], now=NOW) is None
    with pytest.raises(legacy.StaleWork):
        _commit(adopted, second)
    assert rows(engine, db.deck_impressions_table) == original_evidence
    assert not store.retire_invalid_inventory(inventory_id, root)


def test_retire_stale_inventory_cannot_quarantine_its_active_replacement(real_stage, engine):
    original = real_stage()
    old = store.peek_inventory(original["scope"], now=NOW).header
    replacement = real_stage()
    active = store.peek_inventory(original["scope"], now=NOW).header
    before = rows(engine, store.M)
    assert not store.retire_invalid_inventory(old["inventory_id"], old["root_sha256"])
    assert not store.retire_invalid_inventory(replacement["stage"].inventory_id, old["root_sha256"])
    assert rows(engine, store.M) == before
    assert store.peek_inventory(original["scope"], now=NOW).header == active
