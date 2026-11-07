"""Independent cancellation controls promoted to hermetic regressions.

The direct worker fixture skips admission; the final-evaluation tests attach
its real consumed-participant epoch tokens before entering the actual worker.
"""
from datetime import timedelta
import pytest
from sqlalchemy import select
from backend import database as db, prepared_trade_store as old, prepared_trade_store_v2 as paged
from backend.tests.test_prepared_trade_store_v2 import engine, claim, NOW, EXPIRES, RECEIPT, MODEL

def create():
    scope, work = claim()
    stage = paged.begin_inventory(work, dependency_receipt=RECEIPT, model_identity=MODEL, participants=work['participants'], created_at=NOW, expires_at=EXPIRES, now=NOW)
    return (scope, work, stage)

def test_stage_poll_refuses_changed_account_incarnation(engine):
    _, work, stage = create()
    with engine.begin() as conn:
        conn.execute(db.users_table.update().where(db.users_table.c.sleeper_user_id == 'viewer').values(created_at='2026-11-07T00:00:00Z'))
    with pytest.raises(old.StaleWork):
        paged.check_generation_stage(stage, now=NOW)
    with engine.connect() as conn:
        row = conn.execute(select(db.prepared_trade_targets_table).where(db.prepared_trade_targets_table.c.target_id == work['target_id'])).mappings().one()
    assert row['status'] == 'running' and row['lease_token'] == work['lease_token']

def test_stale_poll_cannot_renew_successor_claim(engine):
    _, work, stage = create()
    later = NOW + timedelta(seconds=301)
    successor = old.claim_target(work['sweep_id'], now=later)
    assert successor and successor['lease_token'] != work['lease_token']
    with pytest.raises(old.StaleWork):
        paged.check_generation_stage(stage, now=later)
    with engine.connect() as conn:
        row = conn.execute(select(db.prepared_trade_targets_table).where(db.prepared_trade_targets_table.c.target_id == work['target_id'])).mappings().one()
    assert row['lease_token'] == successor['lease_token'] and row['status'] == 'running'
