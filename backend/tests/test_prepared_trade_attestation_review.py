"""Independent sealed-attestation and authenticated admission-index controls.

Synthetic native proofs and isolated SQL only. Tests deliberately rewrite
transport checksums to distinguish semantic/root binding from trivial damage.
"""
import pytest
from sqlalchemy import delete, update

from backend import database as db, prepared_trade_store as legacy
from backend import prepared_trade_store_v2 as store, prepared_trade_payload_v2 as codec
from backend.tests.test_prepared_trade_chunk_store_review import (
    engine, real_stage, isolated_config, NOW, RECEIPT, MODEL, rows, _adopt, _commit,
)


RESERVED = "__semantic_attestation"


def _seal(info):
    return store.seal_inventory(info["stage"], completion=info["completion"],
        dependency_receipt=RECEIPT, model_identity=MODEL, now=NOW)


def _page(engine, info, kind, index=0):
    return next(row for row in rows(engine, store.P)
        if row["inventory_id"] == info["stage"].inventory_id
        and row["kind"] == kind and row["page_index"] == index)


def _replace_page(engine, info, page, records):
    with engine.begin() as conn:
        conn.execute(update(store.P).where(
            store.P.c.inventory_id == info["stage"].inventory_id,
            store.P.c.kind == page["kind"], store.P.c.page_index == page["page_index"])
            .values(**store._encode(records)))


def _rewrite_metadata_with_consistent_transport(engine, info, mutate):
    row = next(dict(row) for row in rows(engine, store.M)
        if row["inventory_id"] == info["stage"].inventory_id)
    metadata = store._parse(store._unpack(row["metadata_json"], row["metadata_sha256"]))
    mutate(metadata)
    packed, digest = store._text_pair(metadata)
    values = {"metadata_json": packed, "metadata_sha256": digest}
    values["root_sha256"] = store._manifest_root({**row, **values})
    with engine.begin() as conn:
        conn.execute(update(store.M).where(store.M.c.inventory_id == row["inventory_id"]).values(**values))


@pytest.mark.parametrize("value", [None, {}, {"validated": True}])
def test_caller_cannot_supply_reserved_semantic_attestation(real_stage, value):
    info = real_stage(seal=False)
    metadata = info["stage"].reader().metadata()
    metadata[RESERVED] = value
    with pytest.raises(legacy.InvalidArtifact, match="attestation|reserved"):
        store.finish_metadata(info["stage"], metadata=metadata, now=NOW)
    assert store.peek_inventory(info["scope"], now=NOW) is None


def test_semantic_scan_authenticates_already_pinned_tree(real_stage, engine, monkeypatch):
    info = real_stage(seal=False)
    original = codec.restore_inventory
    observed = []

    def scan(reader, **kwargs):
        header = reader.header
        tree = header["tree_sha256"]
        assert isinstance(tree, str) and len(tree) == 64
        assert all(row["proof_json"] is not None for row in rows(engine, store.P)
            if row["inventory_id"] == info["stage"].inventory_id)
        observed.append(tree)
        return original(reader, **kwargs)

    monkeypatch.setattr(codec, "restore_inventory", scan)
    _seal(info)
    assert observed == [store.peek_inventory(info["scope"], now=NOW).header["tree_sha256"]]


@pytest.mark.parametrize("when", ["before_scan", "after_scan"])
def test_scan_race_cannot_attest_changed_descriptor_root(real_stage, engine, monkeypatch, when):
    prior = real_stage()
    prior_root = store.peek_inventory(prior["scope"], now=NOW).header["root_sha256"]
    info = real_stage(seal=False)
    original = codec.restore_inventory
    calls = []

    def mutate():
        page = _page(engine, info, "cards")
        records = store._decode(page)
        records[0]["owner_evaluation"]["snapshot_json"] = "{}"
        _replace_page(engine, info, page, records)
        calls.append(True)

    def scan(reader, **kwargs):
        if when == "before_scan":
            mutate()
        result = original(reader, **kwargs)
        if when == "after_scan":
            mutate()
        return result

    monkeypatch.setattr(codec, "restore_inventory", scan)
    with pytest.raises((legacy.InvalidArtifact, ValueError)):
        _seal(info)
    assert calls == [True]
    assert store.peek_inventory(prior["scope"], now=NOW).header["root_sha256"] == prior_root
    assert not rows(engine, db.deck_impressions_table)


@pytest.mark.parametrize("change", ["missing", "null", "unknown_codec", "unknown_validator", "forged_root"])
def test_fast_open_rejects_unrecognized_attestation_even_with_valid_transport(real_stage, engine, change):
    info = real_stage()

    def mutate(metadata):
        assert isinstance(metadata[RESERVED], dict)
        if change == "missing":
            del metadata[RESERVED]
        elif change == "null":
            metadata[RESERVED] = None
        elif change == "unknown_codec":
            metadata[RESERVED]["codec_version"] = "unknown-codec"
        elif change == "unknown_validator":
            metadata[RESERVED]["validator_version"] = "unknown-validator"
        else:
            metadata[RESERVED]["validated_root_sha256"] = "0" * 64

    _rewrite_metadata_with_consistent_transport(engine, info, mutate)
    assert store.peek_inventory(info["scope"], now=NOW) is None
    reader = store.Reader(info["stage"].inventory_id)
    with pytest.raises((legacy.InvalidArtifact, ValueError)):
        codec.open_attested_inventory(reader, user_id=info["owner"], league_id=info["scope"].league_id, now=NOW)
    assert not rows(engine, db.deck_impressions_table)


@pytest.mark.parametrize("field,value", [
    ("give_player_ids", ["forged"]), ("receive_player_ids", ["forged"]),
    ("target_user_id", "forged"), ("likes_you", True),
    ("standing_offer_reason", "forged"), ("source_like_impression_id", "forged"),
    ("impression_id", "forged"), ("expires_at", "2026-09-23T15:00:00+00:00"),
])
def test_seal_rejects_authenticated_index_that_disagrees_with_native_pair(real_stage, engine, field, value):
    info = real_stage(seal=False)
    page = _page(engine, info, "admission")
    records = store._decode(page)
    assert records[0][field] != value
    records[0][field] = value
    _replace_page(engine, info, page, records)
    with pytest.raises((legacy.InvalidArtifact, ValueError)):
        _seal(info)
    assert store.peek_inventory(info["scope"], now=NOW) is None
    assert not rows(engine, db.deck_impressions_table)


@pytest.mark.parametrize("change", ["duplicate_identity", "duplicate_ordinal", "missing"])
def test_seal_rejects_cross_page_index_duplicates_and_gaps(real_stage, engine, monkeypatch, change):
    monkeypatch.setattr(codec, "PAGE_TARGET_BYTES", 1)
    info = real_stage(seal=False)
    first, second = _page(engine, info, "admission", 0), _page(engine, info, "admission", 1)
    if change == "missing":
        with engine.begin() as conn:
            conn.execute(delete(store.P).where(store.P.c.inventory_id == info["stage"].inventory_id,
                store.P.c.kind == "admission", store.P.c.page_index == 1))
    else:
        original, altered = store._decode(first)[0], store._decode(second)
        key = "trade_id" if change == "duplicate_identity" else "ordinal"
        altered[0][key] = original[key]
        _replace_page(engine, info, second, altered)
    with pytest.raises((legacy.InvalidArtifact, ValueError)):
        _seal(info)
    assert store.peek_inventory(info["scope"], now=NOW) is None


def test_late_preexisting_corruption_only_permits_an_earlier_valid_durable_prefix(real_stage, engine, monkeypatch):
    monkeypatch.setattr(codec, "PAGE_TARGET_BYTES", 1)
    info = real_stage()
    page = _page(engine, info, "cards", 2)
    records = store._decode(page)
    records[0]["owner_evaluation"]["snapshot_json"] = "{}"
    _replace_page(engine, info, page, records)
    inventory = codec.open_attested_inventory(store.peek_inventory(info["scope"], now=NOW),
        user_id=info["owner"], league_id=info["scope"].league_id, now=NOW)
    assert [card.trade_id for card in inventory.iter_disposition_cards()] == [card.trade_id for card in info["cards"]]
    adoption = _adopt(info)
    committed = []
    with pytest.raises((legacy.InvalidArtifact, ValueError)):
        for batch in inventory.batches(**adoption["publication"], first_batch_size=1, batch_size=1):
            _commit(adoption, batch)
            before, after = batch["cursor_before"]["cards"], batch["cursor_after"]["cards"]
            store.checkpoint_adoption(adoption, published_count=after, expected_prefix=before, now=NOW)
            adoption["published_count"] = after
            committed.extend(card.trade_id for card in batch["cards"])
    assert 0 < len(committed) < 3
    assert committed == [card.trade_id for card in info["cards"][:len(committed)]]
    assert len(rows(engine, db.deck_impressions_table)) == len(committed)
    manifest, = rows(engine, store.M)
    assert manifest["adoption_prefix"] == len(committed)
    assert not rows(engine, db.trade_decisions_table) and not rows(engine, db.user_events_table)


def test_missing_trailing_native_and_evidence_pages_cannot_short_complete(real_stage, engine, monkeypatch):
    monkeypatch.setattr(codec, "PAGE_TARGET_BYTES", 1)
    info = real_stage()
    with engine.begin() as conn:
        conn.execute(delete(store.P).where(store.P.c.inventory_id == info["stage"].inventory_id,
            store.P.c.kind.in_(("cards", "impressions")), store.P.c.page_index == 2))
    inventory = codec.open_attested_inventory(store.peek_inventory(info["scope"], now=NOW),
        user_id=info["owner"], league_id=info["scope"].league_id, now=NOW)
    adoption = _adopt(info)
    committed = []
    with pytest.raises((legacy.InvalidArtifact, ValueError, RuntimeError)):
        for batch in inventory.batches(**adoption["publication"], first_batch_size=1, batch_size=1):
            _commit(adoption, batch)
            before, after = batch["cursor_before"]["cards"], batch["cursor_after"]["cards"]
            store.checkpoint_adoption(adoption, published_count=after, expected_prefix=before, now=NOW)
            adoption["published_count"] = after
            committed.extend(card.trade_id for card in batch["cards"])
    assert committed == [card.trade_id for card in info["cards"][:len(committed)]]
    assert 0 < len(committed) < 3
    manifest, = rows(engine, store.M)
    assert manifest["adoption_prefix"] == len(committed)
    assert manifest["adoption_token"] == adoption["token"]  # Not completed.
    assert len(rows(engine, db.deck_impressions_table)) == len(committed)
