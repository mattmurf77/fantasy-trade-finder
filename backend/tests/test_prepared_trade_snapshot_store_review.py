"""Independent frozen-DAG capture -> SQL -> crash-retry publication checks."""
from datetime import timedelta
import json

import pytest
from sqlalchemy import insert

from backend import database as db, prepared_trade_payload as payload, prepared_trade_store as store
from backend.tests.test_prepared_trade_payload import isolated_config, public
from backend.tests.test_prepared_trade_snapshot_review import inputs, capture_for
from backend.tests.test_prepared_trade_store import (
    engine, NOW, RECEIPT, MODEL, target, claim, adoption, rows,
)


@pytest.mark.parametrize("batch_size,sql_chunk", [(1, 1), (1, 200), (2, 1), (2, 200)])
def test_original_dag_and_creation_times_survive_partitioned_publication_and_recovery(
        engine, monkeypatch, batch_size, sql_chunk):
    cards, original, _ = inputs()
    capture = capture_for(cards)
    for row in original:
        capture.impressions([row])
    bundle = capture.finish(cards, [public(card) for card in cards])
    uid, lid = bundle["user_id"], bundle["league_id"]
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=uid, created_at="2026-01-01"))
    scope = store.InventoryScope(uid, lid, uid, "1qb_ppr", "organic")
    admission = claim([target(scope, [uid, cards[0].target_user_id])])
    inventory_id = store.save_inventory(admission, payload={"inventory": bundle},
        dependency_receipt=RECEIPT, model_identity=MODEL, participants=admission["participants"],
        created_at=NOW, expires_at=NOW + timedelta(hours=1), now=NOW)
    publication = adoption(inventory_id, lease_seconds=1)
    inventory = payload.restore_inventory(bundle, user_id=uid, league_id=lid, now=NOW)
    monkeypatch.setattr(db, "DECK_IMPRESSION_INSERT_ROWS", sql_chunk)
    emitted = []
    for batch in inventory.batches(served_at=publication["publication"]["served_at"],
                                   first_batch_size=batch_size, batch_size=batch_size):
        store.ensure_adoption_evidence(publication, candidate_set=batch["candidate_set"],
                                       rows=batch["impression_rows"], now=NOW)
        emitted.extend(batch["impression_rows"])
        # Every already committed impression must have its complete diagnostic
        # closure now, not only after the rest of the deck finishes.
        for row in emitted:
            assert db.load_deck_diagnostics(row["impression_id"], uid) == row["features_json"]
    expected = {row["snapshot_id"]: row for row in bundle["snapshots"]}
    durable = {row["snapshot_id"]: dict(row) for row in rows(engine, db.deck_diagnostic_snapshots_table)}
    assert durable == expected
    assert all(row["served_at"] == NOW.isoformat() for row in rows(engine, db.deck_impressions_table))
    assert {row["created_at"] for row in durable.values()} == {
        "2026-09-22T12:00:00+00:00", "2026-09-22T12:01:00+00:00"}
    before = {table.name: [dict(row) for row in rows(engine, table)] for table in (
        db.deck_impressions_table, db.deck_diagnostic_snapshots_table)}
    # Simulate death after evidence committed but before prefix checkpoint.
    recovered = adoption(inventory_id, now=NOW + timedelta(seconds=2))
    assert recovered["published_count"] == 0
    assert recovered["publication"] == publication["publication"]
    fresh_inventory = payload.restore_inventory(json.loads(json.dumps(bundle)), user_id=uid, league_id=lid, now=NOW)
    for batch in fresh_inventory.batches(served_at=recovered["publication"]["served_at"],
                                         first_batch_size=3 - batch_size, batch_size=3 - batch_size):
        counts = store.ensure_adoption_evidence(recovered, candidate_set=batch["candidate_set"],
            rows=batch["impression_rows"], now=NOW + timedelta(seconds=2))
        assert counts == {"candidate_sets": 0, "snapshots": 0, "impressions": 0}
    store.checkpoint_adoption(recovered, published_count=2, expected_prefix=0, complete=True,
                              now=NOW + timedelta(seconds=2))
    assert before == {table.name: [dict(row) for row in rows(engine, table)] for table in (
        db.deck_impressions_table, db.deck_diagnostic_snapshots_table)}
    assert not rows(engine, db.deck_outcomes_table) and not rows(engine, db.trade_decisions_table)
