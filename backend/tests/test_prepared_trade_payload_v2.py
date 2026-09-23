"""Paged payload: exact native evidence, bounded hydration and fail-closed scans."""
from copy import deepcopy
import json

import pytest

from backend import prepared_trade_payload_v2 as payload
from backend.tests.test_prepared_trade_payload import (
    make_cards, public, rows, make_bundle, topology_rows, PREPARED, SERVED, EXPIRES, isolated_config,
)


class MemoryStage:
    """Small detached protocol fixture, never a production storage substitute."""
    def __init__(self, league_id="synthetic_bilateral"):
        self.league_id = league_id
        self.pages = {"cards": [], "impressions": [], "admission": []}
        self.nodes, self.meta = {}, {}
        self.attestation = None

    @property
    def header(self):
        records = [r for p in self.pages["impressions"] for r in p["records"]]
        return {"schema_version": 2, "scope": {"user_id": "viewer", "league_id": self.league_id},
                "expires_at": EXPIRES, "card_count": sum(len(p["records"]) for p in self.pages["cards"]),
                "impression_count": len(records), "ghost_count": sum(r.get("is_ghost") == 1 for r in records),
                "root_sha256": "fixture-root"}

    def reader(self):
        return self

    def metadata(self):
        return deepcopy(self.meta)

    def finish_metadata(self, metadata):
        self.meta = deepcopy(metadata)

    def append_page(self, *, kind, page_index, ordinal_start, records):
        assert page_index == len(self.pages[kind])
        self.pages[kind].append({"page_index": page_index, "ordinal_start": ordinal_start,
            "ordinal_end": ordinal_start + len(records), "records": deepcopy(records)})

    def put_nodes(self, *, nodes):
        for row in nodes:
            prior = self.nodes.setdefault(row["snapshot_id"], deepcopy(row))
            assert prior == row

    def iter_pages(self, kind, start_ordinal=0):
        for page in self.pages[kind]:
            if page["ordinal_end"] > start_ordinal:
                yield deepcopy(page)

    def get_nodes(self, snapshot_ids):
        return {key: deepcopy(self.nodes[key]) for key in snapshot_ids if key in self.nodes}

    def iter_node_pages(self):
        values = list(self.nodes.values())
        for index in range(0, len(values), 10):
            yield deepcopy(values[index:index + 10])

    def read_cards(self, start, end):
        return [deepcopy(record) for page in self.pages["cards"] for i, record in enumerate(page["records"], page["ordinal_start"])
                if start <= i < end]

    def read_admission(self, start, end):
        return [deepcopy(record) for page in self.pages["admission"] for i, record in enumerate(page["records"], page["ordinal_start"])
                if start <= i < end]

    def verified_attestation(self, *, codec_version, validator_version):
        # Protocol fake only. Production store independently authenticates its
        # reserved seal receipt; these pure tests cannot establish that trust.
        value = deepcopy(self.attestation)
        if (value is None or value.get("codec_version") != codec_version
                or value.get("validator_version") != validator_version):
            raise ValueError("unverified fixture attestation")
        return value

    def read_impressions(self, start, end, ghosts=False):
        values = (record for page in self.pages["impressions"] for record in page["records"]
                  if (record.get("is_ghost") == 1) == ghosts)
        return [deepcopy(record) for i, record in enumerate(values) if start <= i < end]


def capture(n=3, *, candidates=False):
    original, cards, raw = make_bundle(n, with_candidates=candidates)
    stage = MemoryStage(original["league_id"])
    sink = payload.PagedPreparedEvidenceCapture(stage=stage, user_id="viewer", league_id=stage.league_id, job_id="prepared-job")
    if original["candidate_set"] is not None:
        sink.candidate_set(original["candidate_set"])
    for start in range(0, len(raw), 30):
        sink.impressions(raw[start:start + 30])
    completion = sink.finish(cards, (public(card) for card in cards))
    stage.finish_metadata(completion)
    return stage, cards, raw


def restore(stage):
    return payload.restore_inventory(stage, user_id="viewer", league_id=stage.league_id, now=SERVED)


def test_paged_exact_proof_and_runtime_roundtrip_without_inventory_card_list():
    stage, cards, raw = capture()
    inventory = restore(stage)
    assert inventory.card_count == 3 and inventory.expires_at == EXPIRES
    assert not hasattr(inventory, "cards")
    assert [c.owner_evaluation.snapshot_json for c in inventory.iter_cards()] == [c.owner_evaluation.snapshot_json for c in cards]
    batch, = inventory.batches(served_at=SERVED)
    assert [r["valuation_json"] for r in batch["impression_rows"]] == [r["valuation_json"] for r in raw]
    assert [c.trade_id for c in batch["cards"]] == [c.trade_id for c in cards]
    assert batch["cursor_after"] == {"cards": 3, "ghosts": 0}
    assert set(batch["runtime_records"]) == {c.trade_id for c in cards}


def test_full_preflight_rejects_late_corruption_before_returning_inventory():
    stage, _, _ = capture()
    stage.pages["cards"][-1]["records"][-1]["owner_evaluation"]["snapshot_json"] = "{}"
    with pytest.raises(ValueError):
        restore(stage)


def test_telemetry_candidate_singleton_retains_exact_json_and_links():
    stage, cards, _ = capture(3, candidates=True)
    candidate = deepcopy(stage.meta["candidate_set"])
    batches = list(restore(stage).batches(served_at=SERVED, first_batch_size=1, batch_size=1))
    assert batches[0]["candidate_set"] == candidate
    assert all(batch["candidate_set"] is None for batch in batches[1:])
    assert [c.trade_id for batch in batches for c in batch["cards"]] == [c.trade_id for c in cards]


@pytest.mark.parametrize("corrupt", ["duplicate_trade", "duplicate_impression", "gap", "bool_index", "missing_row", "bad_scope", "bad_assets", "bad_candidate", "count", "expiry"])
def test_cross_page_and_global_corruption_is_rejected(corrupt, monkeypatch):
    monkeypatch.setattr(payload, "PAGE_TARGET_BYTES", 1)
    stage, _, _ = capture(3, candidates=True)
    records = stage.pages["cards"]
    evidence = stage.pages["impressions"]
    if corrupt == "duplicate_trade":
        records[1]["records"][0]["runtime"]["trade_id"] = "trade-0"
        records[1]["records"][0]["public"]["trade_id"] = "trade-0"
    elif corrupt == "duplicate_impression": evidence[1]["records"][0]["impression_id"] = "imp-0"
    elif corrupt == "gap": records[1]["ordinal_start"] += 1
    elif corrupt == "bool_index": records[0]["page_index"] = False
    elif corrupt == "missing_row": evidence.pop()
    elif corrupt == "bad_scope": evidence[1]["records"][0]["user_id"] = "other"
    elif corrupt == "bad_assets": evidence[1]["records"][0]["assets_json"] = '{"give":["wrong"],"receive":["target"]}'
    elif corrupt == "bad_candidate": evidence[1]["records"][0]["candidate_set_id"] = "other"
    elif corrupt == "count": stage.meta["codec"]["card_count"] += 1
    elif corrupt == "expiry": stage.meta["codec"]["expires_at"] = SERVED
    with pytest.raises(ValueError):
        restore(stage)


def test_empty_inventory_has_one_durable_zero_cursor_batch():
    stage = MemoryStage()
    sink = payload.PagedPreparedEvidenceCapture(stage=stage, user_id="viewer", league_id=stage.league_id, job_id="prepared-job")
    stage.finish_metadata(sink.finish([], iter(())))
    inventory = restore(stage)
    batch, = inventory.batches(served_at=SERVED)
    assert not batch["cards"] and not batch["impression_rows"]
    assert batch["cursor_before"] == batch["cursor_after"] == {"cards": 0, "ghosts": 0}
    assert inventory.expires_at == EXPIRES


def test_ghosts_drain_in_bounded_suffix_after_all_real_cards():
    cards = make_cards(2)
    raw = rows(cards)
    ghost = {**deepcopy(raw[0]), "impression_id": "ghost", "is_ghost": 1, "card_index": 17}
    stage = MemoryStage(cards[0].league_id)
    sink = payload.PagedPreparedEvidenceCapture(stage=stage, user_id="viewer", league_id=stage.league_id, job_id="prepared-job")
    sink.impressions([raw[0], ghost, raw[1]])
    stage.finish_metadata(sink.finish(cards, map(public, cards)))
    batches = list(restore(stage).batches(served_at=SERVED, first_batch_size=1, batch_size=1))
    assert [len(batch["cards"]) for batch in batches] == [1, 1, 0]
    assert [row["impression_id"] for batch in batches for row in batch["impression_rows"]] == ["imp-0", "imp-1", "ghost"]
    assert batches[-1]["cursor_after"] == {"cards": 2, "ghosts": 1}
    assert batches[-1]["impression_rows"][0]["card_index"] == 17


def test_byte_split_does_not_truncate_or_change_first30_next100_contract(monkeypatch):
    monkeypatch.setattr(payload, "PAGE_TARGET_BYTES", 20_000)
    stage, cards, raw = capture(131)
    assert len(stage.pages["cards"]) > 2
    batches = list(restore(stage).batches(served_at=SERVED))
    assert [len(batch["cards"]) for batch in batches] == [30, 100, 1]
    assert [c.trade_id for batch in batches for c in batch["cards"]] == [c.trade_id for c in cards]
    assert [row["valuation_json"] for batch in batches for row in batch["impression_rows"]] == [row["valuation_json"] for row in raw]


def test_candidate_singleton_refuses_oversize_before_parsing(monkeypatch):
    bundle, _, _ = make_bundle(1, with_candidates=True)
    row = bundle["candidate_set"]
    monkeypatch.setattr(payload, "MAX_CANDIDATE_BYTES", 100)
    monkeypatch.setattr(payload, "_json", lambda *a, **k: pytest.fail("allocated candidate parse before byte refusal"))
    stage = MemoryStage(bundle["league_id"])
    sink = payload.PagedPreparedEvidenceCapture(stage=stage, user_id="viewer", league_id=stage.league_id, job_id="prepared-job")
    with pytest.raises(ValueError, match="record_bytes"):
        sink.candidate_set(row)


def test_public_projection_is_lazy_and_length_exact():
    cards = make_cards(3)
    stage = MemoryStage(cards[0].league_id)
    sink = payload.PagedPreparedEvidenceCapture(stage=stage, user_id="viewer", league_id=stage.league_id, job_id="prepared-job")
    sink.impressions(rows(cards))
    with pytest.raises(ValueError, match="public_count"):
        sink.finish(cards, (public(c) for c in cards[:2]))


@pytest.mark.parametrize("partition", [(1, 2), (2, 1), (1, 1, 1)])
def test_snapshot_topology_changes_preserve_first_representation_and_observation(partition):
    cards, raw = topology_rows()
    stage = MemoryStage(cards[0].league_id)
    sink = payload.PagedPreparedEvidenceCapture(stage=stage, user_id="viewer", league_id=stage.league_id, job_id="prepared-job")
    start, original_nodes = 0, None
    for size in partition:
        batch = deepcopy(raw[start:start + size])
        if start:
            for row in batch:
                row["served_at"] = SERVED
        sink.impressions(batch)
        if original_nodes is None:
            original_nodes = deepcopy(stage.nodes)
        start += size
    stage.finish_metadata(sink.finish(cards, map(public, cards)))
    assert all(stage.nodes[key] == value for key, value in original_nodes.items())
    batches = list(restore(stage).batches(served_at=SERVED))
    assert [row["features_json"] for batch in batches for row in batch["impression_rows"]] == [row["features_json"] for row in raw]


@pytest.mark.parametrize("corrupt", ["missing", "checksum", "scope", "clock", "cycle"])
def test_all_nodes_are_authenticated_even_if_not_referenced_by_first_page(corrupt):
    stage, _, _ = capture()
    sid = next(iter(stage.nodes))
    if corrupt == "missing":
        del stage.nodes[sid]
    elif corrupt == "checksum": stage.nodes[sid]["payload_json"] = '{"forged":true}'
    elif corrupt == "scope": stage.nodes[sid]["user_id"] = "other"
    elif corrupt == "clock": stage.nodes[sid]["created_at"] = "bad"
    elif corrupt == "cycle": stage.nodes[sid]["payload_json"] = json.dumps({payload.REFERENCE_KEY: sid})
    with pytest.raises(ValueError):
        restore(stage)


def test_json_lexical_depth_refuses_before_decoder_allocation(monkeypatch):
    monkeypatch.setattr(payload, "MAX_DEPTH", 3)
    monkeypatch.setattr(payload.json, "loads", lambda *a, **k: pytest.fail("unbounded JSON allocated"))
    with pytest.raises(ValueError, match="json_complexity"):
        payload._json("[[[[0]]]]")


def test_record_without_owner_proof_retains_existing_parser_contract():
    stage, _, _ = capture(1)
    record = stage.pages["cards"][0]["records"][0]
    record["owner_evaluation"] = None
    record["public"].pop("model_arm")
    record["public"].pop("generator_version")
    row = stage.pages["impressions"][0]["records"][0]
    row.pop("valuation_json")
    row.pop("model_arm")
    inventory = restore(stage)
    batch, = inventory.batches(served_at=SERVED)
    assert not hasattr(batch["cards"][0], "owner_evaluation")


def test_authentic_batch_projection_is_only_requested_ordered_slice_and_closure():
    stage, cards, _ = capture(4)
    projection = payload.adoption_projection(stage, card_start=1, card_end=3, ghost_start=0, ghost_end=0)
    assert [record["runtime"]["trade_id"] for record in projection["cards"]] == [c.trade_id for c in cards[1:3]]
    assert [row["card_index"] for row in projection["impressions"]] == [1, 2]
    assert projection["snapshots"] and len(projection["snapshots"]) <= len(stage.nodes)


def test_byte_limited_batches_keep_complete_inventory(monkeypatch):
    stage, cards, _ = capture(4)
    monkeypatch.setattr(payload, "MAX_BATCH_BYTES", 50_000)
    batches = list(restore(stage).batches(served_at=SERVED))
    assert len(batches) > 1
    assert [c.trade_id for batch in batches for c in batch["cards"]] == [c.trade_id for c in cards]


def test_immutable_page_iteration_does_not_query_header_per_card(monkeypatch):
    stage, cards, _ = capture(100)
    inventory = restore(stage)
    original_header = MemoryStage.header.fget
    calls = []

    def header(reader):
        calls.append(None)
        return original_header(reader)

    monkeypatch.setattr(MemoryStage, "header", property(header))
    assert [card.trade_id for card in inventory.iter_cards()] == [card.trade_id for card in cards]
    assert len(calls) == 1
    calls.clear()
    batches = list(inventory.batches(served_at=SERVED))
    assert [len(batch["cards"]) for batch in batches] == [30, 70]
    # Reader authenticates each immutable page. The codec checks its root at
    # batch boundaries; the store independently re-reads before commitment.
    assert 2 <= len(calls) <= 8


def attested(stage):
    restore(stage)  # Unit fixture never labels an unvalidated bundle attested.
    stage.attestation = {"codec_version": payload.VERSION,
        "validator_version": payload.VALIDATOR_VERSION, "root_sha256": stage.header["root_sha256"]}
    return payload.open_attested_inventory(stage, user_id="viewer", league_id=stage.league_id, now=SERVED)


def test_capture_emits_compact_exact_admission_correspondence():
    stage, cards, raw = capture(3)
    entries = stage.read_admission(0, 3)
    assert len(entries) == 3
    for ordinal, (entry, card, row) in enumerate(zip(entries, cards, raw)):
        assert entry == {"ordinal": ordinal, "trade_id": card.trade_id,
            "give_player_ids": card.give_player_ids, "receive_player_ids": card.receive_player_ids,
            "target_user_id": card.target_user_id, "likes_you": card.likes_you,
            "standing_offer_reason": card.standing_offer_reason,
            "source_like_impression_id": card.source_like_impression_id,
            "impression_id": row["impression_id"], "expires_at": card.expires_at}
        assert "owner_evaluation" not in entry


@pytest.mark.parametrize("field,value", [
    ("ordinal", True), ("trade_id", "wrong"), ("give_player_ids", ["wrong"]),
    ("receive_player_ids", ["wrong"]), ("target_user_id", "wrong"),
    ("likes_you", True), ("standing_offer_reason", "wrong"),
    ("source_like_impression_id", "wrong"), ("impression_id", "wrong"),
    ("expires_at", PREPARED),
])
def test_full_seal_preflight_crossbinds_every_admission_field(field, value):
    stage, _, _ = capture(3)
    stage.pages["admission"][0]["records"][2][field] = value
    with pytest.raises(ValueError):
        restore(stage)


def test_fast_opener_reads_no_native_cards_or_diagnostics(monkeypatch):
    stage, cards, _ = capture(3, candidates=True)
    attested(stage)
    original_pages = stage.iter_pages
    seen = []

    def pages(kind, start_ordinal=0):
        assert kind == "admission", "fast admission hydrated native evidence"
        seen.append(kind)
        yield from original_pages(kind, start_ordinal)

    monkeypatch.setattr(stage, "iter_pages", pages)
    monkeypatch.setattr(stage, "iter_node_pages", lambda: pytest.fail("fast admission scanned diagnostics"))
    inventory = payload.open_attested_inventory(stage, user_id="viewer", league_id=stage.league_id, now=SERVED)
    dispositions = list(inventory.iter_disposition_cards())
    assert seen and [card.trade_id for card in dispositions] == [card.trade_id for card in cards]
    assert all(not isinstance(card, dict) and not hasattr(card, "owner_evaluation") for card in dispositions)
    assert inventory.card_count == 3


@pytest.mark.parametrize("reason", ["missing", "unknown_codec", "unknown_validator", "wrong_root"])
def test_fast_opener_requires_recognized_store_attestation(reason):
    stage, _, _ = capture(1)
    attested(stage)
    if reason == "missing": stage.attestation = None
    elif reason == "unknown_codec": stage.attestation["codec_version"] = "unknown"
    elif reason == "unknown_validator": stage.attestation["validator_version"] = "unknown"
    else: stage.attestation["root_sha256"] = "other"
    with pytest.raises(ValueError):
        payload.open_attested_inventory(stage, user_id="viewer", league_id=stage.league_id, now=SERVED)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "expiry", "unknown_field"])
def test_fast_opener_checks_entire_authenticated_index(damage):
    stage, _, _ = capture(3)
    attested(stage)
    values = stage.pages["admission"][0]["records"]
    if damage == "missing":
        values.pop()
        stage.pages["admission"][0]["ordinal_end"] -= 1
    elif damage == "duplicate": values[2]["trade_id"] = values[0]["trade_id"]
    elif damage == "expiry": values[2]["expires_at"] = SERVED
    else: values[2]["unrecognized"] = True
    with pytest.raises(ValueError):
        payload.open_attested_inventory(stage, user_id="viewer", league_id=stage.league_id, now=SERVED)


def test_fast_admission_still_fully_validates_native_publishing_batch():
    stage, _, _ = capture(3)
    inventory = attested(stage)
    stage.pages["cards"][0]["records"][2]["owner_evaluation"]["snapshot_json"] = "{}"
    # Admission relies on the store attestation. Native publication never does.
    inventory = payload.open_attested_inventory(stage, user_id="viewer", league_id=stage.league_id, now=SERVED)
    batches = inventory.batches(served_at=SERVED, first_batch_size=1, batch_size=1)
    assert len(next(batches)["cards"]) == 1
    with pytest.raises(ValueError):
        next(batches)


def test_publishing_batch_rebinds_current_exact_admission_entry():
    stage, _, _ = capture(3)
    inventory = attested(stage)
    stage.pages["admission"][0]["records"][0]["standing_offer_reason"] = "forged standing offer"
    with pytest.raises(ValueError):
        next(inventory.batches(served_at=SERVED))


@pytest.mark.parametrize("kind", ["cards", "impressions"])
def test_attested_batch_missing_trailing_record_cannot_finish_short(kind):
    stage, _, _ = capture(3)
    inventory = attested(stage)
    stage.pages[kind][-1]["records"].pop()
    stage.pages[kind][-1]["ordinal_end"] -= 1
    with pytest.raises(ValueError, match="incomplete_evidence"):
        list(inventory.batches(served_at=SERVED, first_batch_size=1, batch_size=1))


def test_attested_batch_missing_ghost_suffix_cannot_finish_complete():
    stage, cards, _ = capture(2)
    originals = rows(cards)
    ghost = {**deepcopy(originals[0]), "impression_id": "ghost", "is_ghost": 1, "card_index": 17}
    stage = MemoryStage(cards[0].league_id)
    sink = payload.PagedPreparedEvidenceCapture(stage=stage, user_id="viewer", league_id=stage.league_id, job_id="prepared-job")
    sink.impressions([*originals, ghost])
    stage.finish_metadata(sink.finish(cards, map(public, cards)))
    inventory = attested(stage)
    stage.pages["impressions"][-1]["records"].pop()
    stage.pages["impressions"][-1]["ordinal_end"] -= 1
    with pytest.raises(ValueError, match="incomplete_evidence"):
        list(inventory.batches(served_at=SERVED))


def test_fast_opener_missing_reader_is_explicit_validation_failure():
    with pytest.raises(ValueError, match="missing_reader"):
        payload.open_attested_inventory(None, user_id="viewer", league_id="league", now=SERVED)


def test_disposition_callback_uses_one_complete_bounded_admission_scan(monkeypatch):
    stage, cards, _ = capture(203)
    attested(stage)
    original_pages = stage.iter_pages
    scans, checked = [], []

    def pages(kind, start_ordinal=0):
        assert kind == "admission", "disposition check hydrated native cards"
        scans.append(kind)
        yield from original_pages(kind, start_ordinal)

    def check(batch):
        assert 0 < len(batch) <= 100
        assert all(isinstance(card, payload.DispositionCard) for card in batch)
        assert all(not hasattr(card, "owner_evaluation") for card in batch)
        checked.append(tuple(card.trade_id for card in batch))
        return True

    monkeypatch.setattr(stage, "iter_pages", pages)
    inventory = payload.open_attested_inventory(stage, user_id="viewer", league_id=stage.league_id,
        now=SERVED, disposition_check=check)
    assert inventory.card_count == 203
    assert scans == ["admission"]
    assert [len(batch) for batch in checked] == [100, 100, 3]
    assert [trade_id for batch in checked for trade_id in batch] == [card.trade_id for card in cards]


@pytest.mark.parametrize("result", [False, None, 0, "true"])
def test_unverified_current_dispositions_are_distinct_nonmutating_cache_miss(result):
    stage, _, _ = capture(3)
    attested(stage)
    original = deepcopy((stage.pages, stage.nodes, stage.meta))
    with pytest.raises(payload.CurrentDispositionMismatch) as error:
        payload.open_attested_inventory(stage, user_id="viewer", league_id=stage.league_id,
            now=SERVED, disposition_check=lambda batch: result)
    assert not isinstance(error.value, ValueError), "current activity is not artifact corruption"
    assert (stage.pages, stage.nodes, stage.meta) == original
    # A later current-disposition check may accept this same sealed inventory.
    assert payload.open_attested_inventory(stage, user_id="viewer", league_id=stage.league_id,
        now=SERVED, disposition_check=lambda batch: True).card_count == 3


def test_successful_early_disposition_callbacks_cannot_approve_late_bad_index():
    stage, _, _ = capture(201)
    attested(stage)
    stage.pages["admission"][-1]["records"][-1]["trade_id"] = "trade-0"
    checked = []

    def check(batch):
        checked.extend(card.trade_id for card in batch)
        return True

    with pytest.raises(ValueError, match="duplicate_admission_identity"):
        payload.open_attested_inventory(stage, user_id="viewer", league_id=stage.league_id,
            now=SERVED, disposition_check=check)
    assert len(checked) == 200


def test_empty_attested_inventory_needs_no_disposition_callback():
    stage = MemoryStage()
    sink = payload.PagedPreparedEvidenceCapture(stage=stage, user_id="viewer", league_id=stage.league_id, job_id="prepared-job")
    stage.finish_metadata(sink.finish([], iter(())))
    attested(stage)
    inventory = payload.open_attested_inventory(stage, user_id="viewer", league_id=stage.league_id,
        now=SERVED, disposition_check=lambda batch: pytest.fail("empty check must not create work"))
    assert inventory.card_count == 0


def test_codec_rejections_have_typed_artifact_identity():
    with pytest.raises(payload.PreparedPayloadError):
        payload._require(False, "fixture_invalid")
    with pytest.raises(payload.PreparedPayloadError):
        payload._json("{")
    assert payload.is_artifact_error(payload.PreparedPayloadError("typed"))
    assert payload.is_artifact_error(ValueError("prepared_payload:invalid_json"))


@pytest.mark.parametrize("error", [
    ValueError("database unavailable"), RuntimeError("database unavailable"),
    ValueError("prepared_payload_v2:invalid_json"), TypeError("invalid callback"),
])
def test_generic_failures_are_not_mislabeled_artifact_corruption(error):
    assert not payload.is_artifact_error(error)


def test_current_disposition_mismatch_is_never_artifact_corruption():
    error = payload.CurrentDispositionMismatch("current pass")
    assert not isinstance(error, payload.PreparedPayloadError)
    assert not payload.is_artifact_error(error)
