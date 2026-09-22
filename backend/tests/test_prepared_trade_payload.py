"""Lane C: exact prepared card/evidence roundtrip, privacy and fail-closed restore.

Pure tests; no server, provider or database access. Real constructor proofs are
used without re-evaluating them on restore. Publication is a caller operation.
"""
from copy import deepcopy
from dataclasses import asdict, fields
import hashlib
import json

import pytest

from backend import feature_flags as ff, trade_service as ts
from backend import prepared_trade_payload as payload
from backend import trade_gen_bilateral_candidate as candidate
from backend.tests.test_bilateral_contracts import favorable

PREPARED = "2026-09-22T12:00:00+00:00"
SERVED = "2026-09-22T13:00:00+00:00"
EXPIRES = "2026-09-23T12:00:00+00:00"


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))


def public(card):
    value = {name: getattr(card, name) for name in (
        "trade_id", "league_id", "target_user_id", "target_username", "mismatch_score",
        "fairness_score", "composite_score", "basis", "decision", "expires_at", "give_value", "receive_value")}
    value.update(give=[{"id": p, "name": p} for p in card.give_player_ids],
                 receive=[{"id": p, "name": p} for p in card.receive_player_ids],
                 model_arm=card.owner_evaluation.as_dict()["generator"],
                 generator_version=candidate.VERSION)
    return value


def make_cards(n=1):
    originals, _ = candidate.generate_bilateral_trades(**favorable())
    assert originals
    cards = []
    for i in range(n):
        card = deepcopy(originals[0])
        card.trade_id = f"trade-{i}"
        card.created_at, card.expires_at = PREPARED, EXPIRES
        card.lane_shift = -.4
        card.aggression_variant = "fair"
        card.preserve_server_order = True
        cards.append(card)
    return cards


def rows(cards, *, source=None):
    shared = {f"key-{i}": i for i in range(180)}
    return [dict(impression_id=f"imp-{i}", user_id=c.proposing_user_id, league_id=c.league_id,
        deck_job_id="prepared-job", card_index=i,
        trade_hash=payload._trade_hash(c.give_player_ids, c.receive_player_ids, c.target_user_id),
        features_json={"partner_user_id": c.target_user_id, "owner_generation": shared,
                       "owner_request": {"input": shared, "terms": c.give_player_ids},
                       "owner_presentment": {"original_index": i, "final_index": i},
                       "first_deck": True, "ranked_player_count": 0,
                       "last_board_update_at": None, "user_value_basis": "consensus"},
        propensity=1., base_score=c.composite_score, final_score=c.composite_score,
        served_at=PREPARED, assets_json=json.dumps({"give": c.give_player_ids, "receive": c.receive_player_ids}),
        valuation_json=json.dumps(c.owner_evaluation.as_dict()), model_arm=c.owner_evaluation.as_dict()["generator"],
        source_like_impression_id=source) for i, c in enumerate(cards)]


def make_bundle(n=1, *, with_candidates=False, interested=False):
    cards = make_cards(n)
    if interested:
        for card in cards:
            card.likes_you = True
            card.source_like_impression_id = "source-owner-real-impression"
    raw = rows(cards, source="source-owner-real-impression" if interested else None)
    capture = payload.PreparedEvidenceCapture(user_id="viewer", league_id=cards[0].league_id if cards else "league",
                                               job_id="prepared-job")
    if with_candidates:
        members = [{"trade_hash": row["trade_hash"], "give": c.give_player_ids, "receive": c.receive_player_ids,
                    "partner": c.target_user_id, "base_score": c.composite_score, "in_deck": True}
                   for row, c in zip(raw, cards)]
        capture.candidate_set(dict(candidate_set_id="candidate-id", user_id="viewer", league_id=cards[0].league_id,
            deck_job_id="prepared-job", size=len(members), created_at=PREPARED,
            set_hash=hashlib.sha256("|".join(sorted(m["trade_hash"] for m in members)).encode()).hexdigest()[:16],
            candidates_json=json.dumps(members)))
        for row in raw:
            row.update(candidate_set_id="candidate-id", candidate_set_size=len(members))
    for start in range(0, len(raw), 30):
        capture.impressions(raw[start:start + 30])
    return capture.finish(cards, [public(c) for c in cards], significance_by_trade_id=(
        {c.trade_id: ("inbound", (), ()) for c in cards} if interested else None)), cards, raw


def restore(bundle, now=SERVED):
    return payload.restore_inventory(bundle, user_id=bundle["user_id"], league_id=bundle["league_id"], now=now)


def test_explicit_card_schema_tracks_current_dataclass():
    assert payload.CARD_FIELDS == {f.name for f in fields(ts.TradeCard)}


def test_real_owner_card_roundtrip_preserves_proof_and_swipe_weight(monkeypatch):
    bundle, cards, raw = make_bundle(interested=True)
    monkeypatch.setattr(candidate, "evaluate_bilateral_trades", lambda *a, **kw: pytest.fail("repriced"))
    inventory = restore(json.loads(json.dumps(bundle)))
    old, new = cards[0], inventory.cards[0]
    assert asdict(old) == asdict(new)
    assert new.owner_evaluation.snapshot_json == old.owner_evaluation.snapshot_json
    assert new.owner_evaluation.matches(new)
    assert new.owner_groups == old.owner_groups
    assert new.preserve_server_order is True
    assert not getattr(new, "owner_published", False)
    assert inventory.significance_by_trade_id[new.trade_id] == ("inbound", (), ())
    for decision in ("like", "pass"):
        assert ts.fit_congruence_mult(new.lane_shift, decision) == ts.fit_congruence_mult(old.lane_shift, decision)
    batches = list(inventory.batches(served_at=SERVED))
    assert batches[0]["impression_rows"][0]["valuation_json"] == raw[0]["valuation_json"]
    assert batches[0]["impression_rows"][0]["source_like_impression_id"] == old.source_like_impression_id


def test_capture_and_restore_are_detached_and_never_publish():
    bundle, cards, raw = make_bundle(2)
    assert bundle["snapshots"]
    frozen = deepcopy(bundle)
    cards[0].give_player_ids.append("mutation")
    raw[0]["features_json"]["owner_request"]["terms"].append("mutation")
    assert bundle == frozen
    inventory = restore(bundle)
    inventory.public_cards[0]["give"][0]["name"] = "changed"
    inventory.cards[0].lane_shift = 100
    assert bundle == frozen
    assert all(not getattr(c, "owner_published", False) for c in inventory.cards)


def test_full_inventory_batches_are_30_100_100_remainder_with_no_cap():
    bundle, cards, raw = make_bundle(237, with_candidates=True)
    inventory = restore(bundle)
    batches = list(inventory.batches(served_at=SERVED, board_state=(27, PREPARED)))
    assert [len(b["cards"]) for b in batches] == [30, 100, 100, 7]
    assert [c.trade_id for b in batches for c in b["cards"]] == [c.trade_id for c in cards]
    assert [p["impression_id"] for b in batches for p in b["public_cards"]] == [r["impression_id"] for r in raw]
    assert [r["card_index"] for b in batches for r in b["impression_rows"]] == list(range(237))
    assert batches[0]["candidate_set"] == bundle["candidate_set"]
    assert all(b["candidate_set"] is None for b in batches[1:])
    for batch in batches:
        for row in batch["impression_rows"]:
            assert row["served_at"] == SERVED
            features = row["features_json"]
            assert payload.REFERENCE_KEY not in json.dumps(features)
            assert "first_deck" not in features
            assert features["ranked_player_count"] == 27
            assert features["last_board_update_at"] == PREPARED
            assert features["user_value_basis"] == "personal"
            assert features["owner_request"] == raw[row["card_index"]]["features_json"]["owner_request"]
    assert bundle["impressions"][0]["served_at"] == PREPARED


def test_ordered_disposition_subset_preserves_ids_and_native_ranks():
    bundle, _, _ = make_bundle(5)
    batch, = restore(bundle).batches(served_at=SERVED, trade_ids=["trade-1", "trade-3"], first_deck=True)
    assert [r["card_index"] for r in batch["impression_rows"]] == [0, 1]
    assert [r["impression_id"] for r in batch["impression_rows"]] == ["imp-1", "imp-3"]
    assert [r["features_json"]["owner_presentment"]["final_index"] for r in batch["impression_rows"]] == [1, 3]
    assert all(r["features_json"]["first_deck"] for r in batch["impression_rows"])


@pytest.mark.parametrize("ids", [["trade-1", "trade-0"], ["trade-1", "trade-1"], ["missing"]])
def test_adoption_cannot_reorder_duplicate_or_invent_cards(ids):
    bundle, _, _ = make_bundle(2)
    with pytest.raises(ValueError):
        next(restore(bundle).batches(served_at=SERVED, trade_ids=ids))


@pytest.mark.parametrize("path,value", [
    (("schema",), "unknown"), (("runtime", "__class__"), "Bad"),
    (("dynamic", "owner_published"), True), (("runtime", "lane_shift"), "-.4"),
    (("runtime", "lane_shift"), float("nan")), (("runtime", "likes_you"), 1),
    (("runtime", "proposing_user_id"), "other"), (("runtime", "league_id"), "other"),
    (("runtime", "expires_at"), "2099-01-01"), (("runtime", "decision"), "like"),
    (("public", "give"), [{"id": "different"}]), (("public", "expires_at"), "2099-01-01T00:00:00+00:00"),
    (("public", "owner_evaluation"), {}), (("public", "give"), [{"id": "give", "private_board": {}}]),
    (("owner_evaluation", "give_ids"), ["different"]), (("owner_evaluation", "eligible"), False),
    (("owner_evaluation", "snapshot_json"), '{"market":NaN}'),
    (("owner_evaluation", "snapshot_json"), '{"eligible":true,"eligible":false}'),
])
def test_runtime_corruption_fails_closed(path, value):
    bundle, _, _ = make_bundle()
    record = bundle["cards"][0]
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        restore(bundle)


def test_unknown_runtime_objects_not_stringified_or_resurrected():
    card = make_cards()[0]
    card.unrecognized_authority = object()
    with pytest.raises(ValueError, match="unsupported_runtime_field"):
        payload.capture_runtime_card(card, public(card))
    del card.unrecognized_authority
    card.match_context = {"unsupported": object()}
    with pytest.raises(ValueError, match="unsupported_json_type"):
        payload.capture_runtime_card(card, public(card))


@pytest.mark.parametrize("corrupt", ["missing_row", "duplicate_row", "reorder", "wrong_scope", "source", "proof",
                                    "missing_snapshot", "wrong_snapshot_scope", "snapshot_checksum", "snapshot_cycle",
                                    "candidate_missing", "candidate_checksum", "candidate_wrong_scope"])
def test_complete_bundle_dependency_validation_precedes_any_card(corrupt):
    bundle, _, _ = make_bundle(2, with_candidates=True, interested=True)
    if corrupt == "missing_row": bundle["impressions"].pop()
    elif corrupt == "duplicate_row": bundle["impressions"].append(bundle["impressions"][0])
    elif corrupt == "reorder": bundle["impressions"].reverse()
    elif corrupt == "wrong_scope": bundle["impressions"][1]["user_id"] = "another"
    elif corrupt == "source": bundle["impressions"][1]["source_like_impression_id"] = "new-same-package-like"
    elif corrupt == "proof": bundle["impressions"][1]["valuation_json"] = "{}"
    elif corrupt == "missing_snapshot": bundle["snapshots"].pop()
    elif corrupt == "wrong_snapshot_scope": bundle["snapshots"][0]["user_id"] = "another"
    elif corrupt == "snapshot_checksum": bundle["snapshots"][0]["payload_json"] = "{}"
    elif corrupt == "snapshot_cycle":
        row = bundle["snapshots"][0]
        row["payload_json"] = json.dumps({payload.REFERENCE_KEY: row["snapshot_id"]})
    elif corrupt == "candidate_missing": bundle["candidate_set"] = None
    elif corrupt == "candidate_checksum": bundle["candidate_set"]["set_hash"] = "wrong"
    elif corrupt == "candidate_wrong_scope": bundle["candidate_set"]["league_id"] = "another"
    published = []
    with pytest.raises(ValueError):
        inventory = restore(bundle)
        published.extend(inventory.cards)
    assert published == []


def test_expiry_is_never_renewed_on_restore_or_later_adoption():
    bundle, _, _ = make_bundle()
    with pytest.raises(ValueError, match="expired_card"):
        restore(bundle, now=EXPIRES)
    inventory = restore(bundle)
    with pytest.raises(ValueError, match="expired_card"):
        next(inventory.batches(served_at=EXPIRES))
    assert bundle["cards"][0]["runtime"]["expires_at"] == EXPIRES


def test_empty_inventory_and_empty_disposition_result_are_not_errors():
    capture = payload.PreparedEvidenceCapture(user_id="viewer", league_id="league", job_id="empty")
    bundle = capture.finish([], [])
    assert restore(bundle).cards == []
    assert list(restore(bundle).batches(served_at=SERVED)) == []
    bundle, _, _ = make_bundle()
    assert list(restore(bundle).batches(served_at=SERVED, trade_ids=[])) == []


def test_commit_failure_has_no_publication_and_does_not_mark_cards():
    inventory = restore(make_bundle(32)[0])
    published = []
    def commit(_):
        raise RuntimeError("database unavailable")
    with pytest.raises(RuntimeError):
        for batch in inventory.batches(served_at=SERVED):
            commit(batch["impression_rows"])
            published.extend(batch["public_cards"])
    assert not published
    assert all(not getattr(c, "owner_published", False) for c in inventory.cards)


def test_capture_is_one_shot_and_rejects_wrong_scope_before_sealing():
    card = make_cards()[0]
    capture = payload.PreparedEvidenceCapture(user_id="viewer", league_id=card.league_id, job_id="prepared-job")
    row = rows([card])[0]
    bad = {**row, "user_id": "other"}
    with pytest.raises(ValueError): capture.impressions([bad])
    capture.impressions([row])
    capture.finish([card], [public(card)])
    with pytest.raises(ValueError): capture.impressions([row])
    with pytest.raises(ValueError): capture.finish([card], [public(card)])


def test_real_logger_and_public_serializer_are_compatible_without_database_writes(monkeypatch):
    # Existing logger constructs every field; two injected sinks are the only
    # persistence seams. No wrapper-generated replacement proof/row is used.
    from backend import server
    args = favorable()
    cards = make_cards(2)
    capture = payload.PreparedEvidenceCapture(user_id="viewer", league_id=cards[0].league_id,
                                               job_id="prepared-job")
    monkeypatch.setattr(server, "save_deck_impressions", capture.impressions)
    monkeypatch.setattr(server, "save_deck_candidate_set", capture.candidate_set)
    monkeypatch.setattr(server, "load_board_state", lambda *a: (7, PREPARED))
    monkeypatch.setattr(server, "_pick_gap_equivalent", lambda v: {"pick_equivalent": None})
    imp_ids = server._log_deck_signal_impressions(user_id="viewer", league_id=cards[0].league_id,
        job_id="prepared-job", cards=cards, players_dict=args["players"], capture=None,
        scoring_format="1qb_ppr", structured_features=True, policy_version="captured-policy",
        initial_publication_batch_size=1, publication_batch_size=1)
    public_cards = [{**server.trade_card_to_dict(c, args["players"]),
                     "impression_id": imp_ids[id(c)]} for c in cards]
    bundle = capture.finish(cards, public_cards)
    inventory = restore(bundle)
    assert inventory.public_cards == public_cards
    assert [server.trade_card_to_dict(c, args["players"]) for c in inventory.cards] == [
        server.trade_card_to_dict(c, args["players"]) for c in cards]
    batch, = inventory.batches(served_at=SERVED)
    assert [r["trade_hash"] for r in batch["impression_rows"]] == [
        server._deck_trade_hash(c.give_player_ids, c.receive_player_ids, c.target_user_id) for c in cards]


@pytest.mark.parametrize("key,value", [("lane_shift", True), ("match_context", []), ("reasons", {}),
                                       ("meso_variants", ["bad"]), ("lane", {}), ("give_value", float("inf"))])
def test_malformed_runtime_semantic_fields_do_not_reach_decision_consumers(key, value):
    bundle, _, _ = make_bundle()
    bundle["cards"][0]["runtime"][key] = value
    with pytest.raises(ValueError):
        restore(bundle)


@pytest.mark.parametrize("key,value", [("propensity", -1), ("base_score", True),
    ("arm_rank", 1.5), ("candidate_set_size", False), ("valuation_json", "[]"),
    ("assets_json", '{"give":["give"],"receive":["target"],"extra":true}')])
def test_malformed_evidence_types_fail_before_first_batch(key, value):
    bundle, _, _ = make_bundle(2)
    bundle["impressions"][-1][key] = value
    with pytest.raises(ValueError):
        restore(bundle)


def test_ghost_evidence_is_preserved_but_never_public_or_actionable():
    bundle, _, _ = make_bundle(2, with_candidates=True)
    ghost = deepcopy(bundle["impressions"][1])
    ghost.update(impression_id="ghost-only", is_ghost=1)
    bundle["impressions"].append(ghost)
    batches = list(restore(bundle).batches(served_at=SERVED, first_batch_size=1))
    assert [len(b["cards"]) for b in batches] == [1, 1]
    assert [len(b["impression_rows"]) for b in batches] == [1, 2]
    assert batches[-1]["impression_rows"][-1]["impression_id"] == "ghost-only"
    assert all(p["impression_id"] != "ghost-only" for b in batches for p in b["public_cards"])


def test_owner_header_identity_must_match_exact_runtime_terms():
    bundle, _, _ = make_bundle()
    bundle["cards"][0]["owner_evaluation"]["give_ids"] = ["other-owned-asset"]
    with pytest.raises(ValueError, match="proof_binding"):
        restore(bundle)


@pytest.mark.parametrize("field", ["lane_shift", "give_value", "composite_score"])
def test_oversized_json_integer_is_uniform_codec_error(field):
    bundle, _, _ = make_bundle()
    bundle["cards"][0]["runtime"][field] = 10 ** 400
    with pytest.raises(ValueError, match="number"):
        restore(bundle)


@pytest.mark.parametrize("mutation", ["terms", "lane_shift", "public", "provenance", "candidate"])
def test_mutation_after_restore_cannot_change_an_adopted_offer(mutation):
    inventory = restore(make_bundle(2, with_candidates=True, interested=True)[0])
    if mutation == "terms": inventory.cards[1].give_player_ids = ["changed"]
    elif mutation == "lane_shift": inventory.cards[1].lane_shift = .4
    elif mutation == "public": inventory.public_cards[1]["give"][0]["name"] = "changed"
    elif mutation == "provenance": inventory.significance_by_trade_id["trade-1"] = ("explicit_search", ("give",), ())
    elif mutation == "candidate": inventory.candidate_set["created_at"] = SERVED
    with pytest.raises(ValueError):
        next(inventory.batches(served_at=SERVED, first_batch_size=1))


def test_mutation_during_adoption_withholds_next_batch_but_keeps_prior_identity():
    inventory = restore(make_bundle(2)[0])
    batches = inventory.batches(served_at=SERVED, first_batch_size=1)
    first = next(batches)
    first["cards"][0].owner_published = True  # caller's post-commit mark is permitted
    inventory.cards[1].lane_shift = .7
    with pytest.raises(ValueError, match="restored_card_mutated"):
        next(batches)
    assert first["public_cards"][0]["impression_id"] == "imp-0"


def topology_rows():
    """Same expanded root; child is shared only in the second batch."""
    cards = make_cards(3)
    raw = rows(cards)
    child = {f"diagnostic-{i}": i for i in range(180)}
    for i, row in enumerate(raw):
        row["features_json"] = {"partner_user_id": cards[i].target_user_id,
            "roster_evaluation": {"kind": "B" if i == 2 else "A", "shared": child}}
    return cards, raw


@pytest.mark.parametrize("partition", [(3,), (1, 2), (2, 1), (1, 1, 1)])
def test_capture_preserves_expanded_diagnostics_across_batch_local_reference_topologies(partition):
    cards, raw = topology_rows()
    # Witness why complete packed-row equality is NOT content identity.
    _, first = payload.compact_rows(deepcopy(raw[:1]))
    _, later = payload.compact_rows(deepcopy(raw[1:]))
    root = first[-1]
    alternate = next(row for row in later if row["snapshot_id"] == root["snapshot_id"])
    assert root["payload_json"] != alternate["payload_json"]
    assert {k: v for k, v in root.items() if k != "payload_json"} == {
        k: v for k, v in alternate.items() if k != "payload_json"}
    capture = payload.PreparedEvidenceCapture(user_id="viewer", league_id=cards[0].league_id,
                                               job_id="prepared-job")
    start = 0
    for size in partition:
        capture.impressions(raw[start:start + size])
        start += size
    bundle = capture.finish(cards, [public(c) for c in cards])
    inventory = restore(bundle)
    emitted = [row for batch in inventory.batches(served_at=SERVED) for row in batch["impression_rows"]]
    assert [r["features_json"] for r in emitted] == [r["features_json"] for r in raw]
    assert [r["valuation_json"] for r in emitted] == [r["valuation_json"] for r in raw]
    assert [c.owner_evaluation.snapshot_json for c in inventory.cards] == [c.owner_evaluation.snapshot_json for c in cards]
    assert [r["impression_id"] for r in emitted] == [r["impression_id"] for r in raw]
    assert [r["card_index"] for r in emitted] == [0, 1, 2]
    assert all(row["created_at"] == PREPARED for row in bundle["snapshots"])


@pytest.mark.parametrize("corrupt", ["payload", "scope", "timestamp", "missing_child", "cycle"])
def test_semantic_snapshot_merge_rejects_corruption_without_partial_capture(monkeypatch, corrupt):
    cards, raw = topology_rows()
    capture = payload.PreparedEvidenceCapture(user_id="viewer", league_id=cards[0].league_id,
                                               job_id="prepared-job")
    capture.impressions(raw[:1])
    before = deepcopy((capture._rows, capture._nodes))
    existing = next(iter(capture._nodes))
    original = payload.compact_rows
    def broken(value):
        compacted, nodes = original(value)
        root = next(node for node in nodes if node["snapshot_id"] == existing)
        if corrupt == "payload": root["payload_json"] = '{"different":"evidence"}'
        elif corrupt == "scope": root["user_id"] = "other"
        elif corrupt == "timestamp": root["created_at"] = "not-a-timestamp"
        elif corrupt == "cycle": root["payload_json"] = json.dumps({payload.REFERENCE_KEY: existing})
        elif corrupt == "missing_child":
            referenced = json.loads(root["payload_json"])["shared"][payload.REFERENCE_KEY]
            nodes = [node for node in nodes if node["snapshot_id"] != referenced]
        return compacted, nodes
    monkeypatch.setattr(payload, "compact_rows", broken)
    with pytest.raises(ValueError):
        capture.impressions(raw[1:])
    assert (capture._rows, capture._nodes) == before
