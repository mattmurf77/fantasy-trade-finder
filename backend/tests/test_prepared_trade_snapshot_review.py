"""Independent cross-batch DAG regressions for the prepared capture hotfix."""
from copy import deepcopy
import hashlib

import pytest

from backend import prepared_trade_payload as payload
from backend.deck_diagnostics import compact_rows, dumps, REFERENCE_KEY
from backend.tests.test_prepared_trade_payload import (
    PREPARED, SERVED, isolated_config, make_cards, public, rows,
)


def sid(value):
    return hashlib.sha256((dumps(("viewer", "prepared-job")) + "\n" + dumps(value)).encode()).hexdigest()


def inputs(*, reference_first=False):
    cards = make_cards(2)
    raw = rows(cards)
    child = {"large": "x" * 1500, "typed": [True, 1, 1.0]}
    root = {"same": child}
    for index, row in enumerate(raw):
        row["features_json"]["owner_request"] = deepcopy(root)
        shared_here = (index == 0) == reference_first
        row["features_json"]["owner_generation"] = ({"distinct-parent": deepcopy(child)}
            if shared_here else {"small": index})
    raw[1]["served_at"] = "2026-09-22T12:01:00+00:00"
    return cards, raw, root


def capture_for(cards):
    return payload.PreparedEvidenceCapture(user_id="viewer", league_id=cards[0].league_id,
                                          job_id="prepared-job")


@pytest.mark.parametrize("reference_first", [False, True])
def test_equal_expanded_subtree_survives_opposite_topology_and_later_timestamp(reference_first):
    cards, raw, root = inputs(reference_first=reference_first)
    packed = [compact_rows([row])[1] for row in raw]
    first, second = [next(n for n in batch if n["snapshot_id"] == sid(root)) for batch in packed]
    assert first["payload_json"] != second["payload_json"]  # Real mechanism, not a mocked hash.
    capture = capture_for(cards)
    capture.impressions([raw[0]])
    original = deepcopy(capture._nodes[sid(root)])
    capture.impressions([raw[1]])
    assert capture._nodes[sid(root)] == original  # First encoding AND observation remain immutable.
    bundle = capture.finish(cards, [public(c) for c in cards])
    assert [row["served_at"] for row in bundle["impressions"]] == [row["served_at"] for row in raw]
    restored = payload.restore_inventory(bundle, user_id="viewer", league_id=cards[0].league_id, now=SERVED)
    batch, = restored.batches(served_at=SERVED)
    for before, after in zip(raw, batch["impression_rows"]):
        for key in ("owner_request", "owner_generation"):
            assert after["features_json"][key] == before["features_json"][key]
        assert after["valuation_json"] == before["valuation_json"]


@pytest.mark.parametrize("corruption", ["user", "job", "timestamp", "wrong_content", "missing", "cycle"])
def test_duplicate_semantics_cannot_hide_invalid_new_encoding_or_partial_commit(monkeypatch, corruption):
    cards, raw, root = inputs()
    capture = capture_for(cards)
    capture.impressions([raw[0]])
    before = deepcopy((capture._rows, capture._nodes))
    bad = deepcopy(capture._nodes[sid(root)])
    if corruption == "user": bad["user_id"] = "foreign"
    elif corruption == "job": bad["deck_job_id"] = "foreign"
    elif corruption == "timestamp": bad["created_at"] = "not-a-time"
    elif corruption == "wrong_content": bad["payload_json"] = dumps({"different": "content"})
    elif corruption == "missing": bad["payload_json"] = dumps({REFERENCE_KEY: "missing-child"})
    elif corruption == "cycle": bad["payload_json"] = dumps({REFERENCE_KEY: bad["snapshot_id"]})
    value = {"new-valid-node": "y" * 1500}
    good = dict(snapshot_id=sid(value), user_id="viewer", deck_job_id="prepared-job",
                created_at=PREPARED, payload_json=dumps(value))
    # A valid earlier node must not leak into state when a later duplicate fails.
    monkeypatch.setattr(payload, "compact_rows", lambda incoming: (incoming, [good, bad]))
    with pytest.raises(ValueError):
        capture.impressions([raw[1]])
    assert (capture._rows, capture._nodes) == before
    monkeypatch.setattr(payload, "compact_rows", compact_rows)
    capture.impressions([raw[1]])
    capture.finish(cards, [public(c) for c in cards])  # A rejected batch cannot poison the valid retry.


def test_valid_prior_node_may_be_referenced_by_later_batch_without_redefinition():
    cards, raw, root = inputs()
    capture = capture_for(cards)
    capture.impressions([raw[0]])
    raw[1]["features_json"]["owner_request"] = {REFERENCE_KEY: sid(root)}
    capture.impressions([raw[1]])
    bundle = capture.finish(cards, [public(c) for c in cards])
    restored = payload.restore_inventory(bundle, user_id="viewer", league_id=cards[0].league_id, now=SERVED)
    batch, = restored.batches(served_at=SERVED)
    assert all(row["features_json"]["owner_request"] == root for row in batch["impression_rows"])


def test_many_collisions_validate_graphs_once_per_batch_not_once_per_node(monkeypatch):
    first, second = [], []
    for index in range(64):
        child = {"id": index, "large": "x" * 1500}
        root = {"same": child}
        base = {"user_id": "viewer", "league_id": "league", "deck_job_id": "prepared-job",
                "served_at": PREPARED}
        first.append({**base, "features_json": {"owner_request": root}})
        second.append({**base, "features_json": {"owner_request": deepcopy(root),
                                                "owner_generation": {"distinct": deepcopy(child)}}})
    capture = payload.PreparedEvidenceCapture(user_id="viewer", league_id="league", job_id="prepared-job")
    capture.impressions(first)
    calls = []
    validate = payload._snapshots
    def observe(*args, **kwargs):
        calls.append(len(args[0]))
        return validate(*args, **kwargs)
    monkeypatch.setattr(payload, "_snapshots", observe)
    capture.impressions(second)
    assert len(calls) == 2  # Old and proposed graph, not two global walks per conflict.
    assert len(capture._rows) == 128
