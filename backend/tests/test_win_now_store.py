"""Win Now proposal §7–8: immutable evidence, durable queue and isolated intent decisions."""
import json
from copy import deepcopy

import pytest
from sqlalchemy import create_engine, delete, event, insert, select, update
from sqlalchemy.exc import IntegrityError

from backend import database as db
from backend import win_now_store as store

TABLES = [db.users_table, db.season_forecast_snapshots_table, db.season_projection_snapshots_table,
          db.win_now_jobs_table, db.win_now_scenarios_table, db.win_now_decisions_table]


@pytest.fixture
def engine(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'win-now.db'}")
    db.metadata.create_all(engine, tables=TABLES)
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id="alice", username="alice"))
    monkeypatch.setattr(db, "engine", engine)
    yield engine
    engine.dispose()


def test_immutable_forecasts_idempotent_and_cannot_rewrite_history(engine):
    snapshot = {"snapshot_id": "frozen", "season": 2026, "provider": "external",
                "captured_at": "2026-09-04T12:00:00Z", "forecasts": [{"player_id": "p", "week": 4}]}
    store.save_forecasts(snapshot)
    store.save_forecasts(deepcopy(snapshot))
    changed = deepcopy(snapshot)
    changed["forecasts"][0]["week"] = 5
    with pytest.raises(IntegrityError):
        store.save_forecasts(changed)
    with engine.connect() as conn:
        rows = conn.execute(select(db.season_forecast_snapshots_table)).mappings().all()
    assert len(rows) == 1
    assert json.loads(rows[0]["payload_json"]) == snapshot


def test_projection_snapshot_reuses_exact_payload_without_rewriting(engine):
    args = ("projection", "league", "forecast", {"teams": [{"roster_id": 1, "wins": 7}]},
            "2026-09-04T12:00:00Z", "2026-09-04T12:15:00Z")
    store.save_projection(*args)
    store.save_projection(*args)
    changed = list(args)
    changed[3] = {"teams": [{"roster_id": 1, "wins": 8}]}
    with pytest.raises(IntegrityError):
        store.save_projection(*changed)


def test_overlapping_startup_preserves_live_job_and_original_worker_completes(engine, monkeypatch):
    inputs = {"actor": {"user_id": "alice"}, "params": {"objective": "wins", "budget": 3}}
    job = store.create_job("alice", "league", inputs)
    assert store.get_job(job["job_id"], "bob") is None
    assert store.claim_job(job["job_id"])
    assert not store.claim_job(job["job_id"])
    database_url = str(engine.url)
    engine.dispose()
    replacement = create_engine(database_url)
    monkeypatch.setattr(db, "engine", replacement)
    try:
        loaded = store.get_job(job["job_id"], "alice")
        assert loaded["status"] == "running"
        assert json.loads(loaded["input_json"]) == inputs
        assert store.recover_interrupted_jobs() == 0
        assert store.get_job(job["job_id"], "alice") == loaded
        assert store.pending_jobs() == []
        assert not store.claim_job(job["job_id"])
        result = {"meta": {"expires_at": job["expires_at"]}, "trades": []}
        store.finish_job(job["job_id"], result=result)
        done = store.get_job(job["job_id"], "alice")
        assert done["status"] == "complete"
        assert done["expires_at"] == result["meta"]["expires_at"]
        assert json.loads(done["result_json"]) == result
        assert store.pending_jobs() == []
    finally:
        replacement.dispose()


def test_new_forecast_scenario_preserves_asset_identity_and_old_decision(engine):
    exchange = {"buyer_roster_id": 1, "partner_roster_id": 2,
                "give": [{"id": "a"}], "receive": [{"id": "b"}], "eligible": True}
    meta = {"snapshot_id": "old", "expires_at": "2026-09-04T12:05:00Z"}
    a = store.save_scenario("alice", "league", "wins", exchange, meta)
    b = store.save_scenario("alice", "league", "wins", exchange,
                            dict(meta, snapshot_id="new"))
    assert a["scenario_id"] != b["scenario_id"]
    assert a["asset_key"] == b["asset_key"]
    assert store.get_scenario(a["scenario_id"], "bob") is None
    store.save_decision("alice", a["scenario_id"], "like")
    assert json.loads(store.get_scenario(a["scenario_id"], "alice")["payload_json"])["meta"]["snapshot_id"] == "old"
    with engine.connect() as conn:
        rows = conn.execute(select(db.win_now_decisions_table)).mappings().all()
    assert [r["scenario_id"] for r in rows] == [a["scenario_id"]]


def test_intent_decision_update_touches_only_its_own_table(engine):
    statements = []
    def inspect(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            statements.append(statement)
    event.listen(engine, "before_cursor_execute", inspect)
    store.save_decision("alice", "scenario", "like")
    store.save_decision("alice", "scenario", "pass")
    with pytest.raises(ValueError, match="invalid_decision"):
        store.save_decision("alice", "scenario", "rank")
    with engine.connect() as conn:
        rows = conn.execute(select(db.win_now_decisions_table)).mappings().all()
    assert len(rows) == 1 and rows[0]["decision"] == "pass"
    assert statements and all("win_now_decisions" in s for s in statements)


def test_expired_queued_and_running_jobs_stop_consuming_capacity(engine):
    queued = store.create_job("alice", "league", {})
    running = store.create_job("alice", "league", {})
    finished = store.create_job("alice", "league", {})
    fresh = store.create_job("alice", "league", {})
    store.claim_job(running["job_id"])
    assert store.claim_job(finished["job_id"])
    store.finish_job(finished["job_id"], result={"trades": []})
    with engine.begin() as conn:
        conn.execute(update(db.win_now_jobs_table).where(db.win_now_jobs_table.c.job_id.in_(
            [queued["job_id"], running["job_id"], finished["job_id"]])).values(expires_at="2020-01-01T00:00:00Z"))
    store.expire_jobs()
    for job in [queued, running]:
        result = store.get_job(job["job_id"], "alice")
        assert result["status"] == "failed" and result["reason"] == "job_expired"
        assert not store.claim_job(job["job_id"])
    assert store.get_job(finished["job_id"], "alice")["status"] == "complete"
    assert [row["job_id"] for row in store.pending_jobs()] == [fresh["job_id"]]
    assert store.recover_interrupted_jobs() == 0


@pytest.mark.parametrize("table_name,column,days", [
    ("win_now_jobs_table", "created_at", 7), ("win_now_decisions_table", "created_at", 180),
    ("win_now_scenarios_table", "created_at", 180), ("season_projection_snapshots_table", "created_at", 400),
    ("season_forecast_snapshots_table", "captured_at", 400)])
def test_retention_removes_old_evidence_and_preserves_current_rows(engine, table_name, column, days):
    from datetime import datetime, timedelta, timezone
    table = getattr(db, table_name)
    now = datetime.now(timezone.utc)
    values = {
        "win_now_jobs_table": {"job_id": "old", "user_id": "alice", "league_id": "league", "status": "complete",
                               "created_at": "", "updated_at": now.isoformat(), "expires_at": now.isoformat(), "input_json": "{}"},
        "win_now_decisions_table": {"user_id": "alice", "scenario_id": "old", "decision": "like", "created_at": ""},
        "win_now_scenarios_table": {"scenario_id": "old", "user_id": "alice", "league_id": "league", "snapshot_id": "s",
                                    "objective": "wins", "asset_key": "a", "created_at": "", "expires_at": now.isoformat(), "payload_json": "{}"},
        "season_projection_snapshots_table": {"snapshot_id": "old", "league_id": "league", "forecast_snapshot_id": "f",
                                               "created_at": "", "expires_at": now.isoformat(), "payload_json": "{}"},
        "season_forecast_snapshots_table": {"snapshot_id": "old", "season": "2026", "source": "fixture", "captured_at": "", "payload_json": "{}"},
    }[table_name]
    with engine.begin() as conn:
        for age, identity in [(days + 2, "old"), (days - 2, "fresh")]:
            row = {key: (identity if value == "old" else value) for key, value in values.items()}
            row[column] = (now - timedelta(days=age)).isoformat()
            conn.execute(insert(table).values(**row))
    store.prune_history()
    with engine.connect() as conn:
        rows = conn.execute(select(table)).mappings().all()
    assert len(rows) == 1
    assert rows[0][column] == (now - timedelta(days=days - 2)).isoformat()


def test_deleted_running_job_cannot_be_resurrected_by_delayed_worker(engine):
    job = store.create_job("alice", "league", {}, require_user=True)
    assert store.claim_job(job["job_id"])
    with engine.begin() as conn:
        conn.execute(delete(db.win_now_jobs_table).where(db.win_now_jobs_table.c.job_id == job["job_id"]))
    with pytest.raises(ValueError, match="job_no_longer_available"):
        store.save_scenario("alice", "league", "wins", {"buyer_roster_id": 1, "partner_roster_id": 2,
            "give": [{"id": "a"}], "receive": [{"id": "b"}]},
            {"snapshot_id": "s", "expires_at": "2099-01-01T00:00:00Z"}, require_user=True, job_id=job["job_id"])
    store.finish_job(job["job_id"], result={"trades": []})
    with engine.connect() as conn:
        assert conn.execute(select(db.win_now_scenarios_table)).first() is None
        assert conn.execute(select(db.win_now_jobs_table)).first() is None


def test_account_deletion_removes_personal_win_now_rows_and_blocks_delayed_writes(engine):
    from backend import accounts
    db.metadata.create_all(engine)
    job = store.create_job("alice", "league", {}, require_user=True)
    store.claim_job(job["job_id"])
    exchange = {"buyer_roster_id": 1, "partner_roster_id": 2, "give": [{"id": "a"}], "receive": [{"id": "b"}]}
    meta = {"snapshot_id": "s", "expires_at": "2099-01-01T00:00:00Z"}
    scenario = store.save_scenario("alice", "league", "wins", exchange, meta, require_user=True, job_id=job["job_id"])
    store.save_decision("alice", scenario["scenario_id"], "like", require_user=True)
    foreign = store.create_job("bob", "league", {})
    counts = accounts.delete_user_data("alice")
    assert counts["win_now_jobs_deleted"] == counts["win_now_scenarios_deleted"] == counts["win_now_decisions_deleted"] == 1
    assert store.get_job(foreign["job_id"], "bob") is not None
    for write in [lambda: store.create_job("alice", "league", {}, require_user=True),
                  lambda: store.save_scenario("alice", "league", "wins", exchange, meta, require_user=True, job_id=job["job_id"]),
                  lambda: store.save_decision("alice", scenario["scenario_id"], "like", require_user=True)]:
        with pytest.raises(ValueError, match="account_no_longer_available"):
            write()


@pytest.mark.parametrize("recover_first", [False, True])
def test_expired_running_job_cannot_be_revived_by_late_worker(engine, recover_first):
    job = store.create_job("alice", "league", {}, require_user=True)
    assert store.claim_job(job["job_id"])
    with engine.begin() as conn:
        conn.execute(update(db.win_now_jobs_table).where(db.win_now_jobs_table.c.job_id == job["job_id"])
                     .values(expires_at="2020-01-01T00:00:00+00:00"))
    if recover_first:
        assert store.recover_interrupted_jobs() == 1
        assert store.recover_interrupted_jobs() == 0
    before = store.get_job(job["job_id"], "alice")
    store.finish_job(job["job_id"], result={"meta": {"expires_at": "2099-01-01T00:00:00+00:00"}, "trades": []})
    store.finish_job(job["job_id"], reason="generation_failed")
    assert store.get_job(job["job_id"], "alice") == before
    assert store.pending_jobs() == []
    assert not store.claim_job(job["job_id"])
    if recover_first:
        assert before["status"] == "failed" and before["reason"] == "job_expired"


@pytest.mark.parametrize("state", ["queued", "complete", "failed"])
def test_finish_requires_running_job_and_preserves_terminal_results(engine, state):
    job = store.create_job("alice", "league", {})
    if state != "queued":
        assert store.claim_job(job["job_id"])
        store.finish_job(job["job_id"], result={"trades": []} if state == "complete" else None,
                         reason="original_failure" if state == "failed" else None)
    before = store.get_job(job["job_id"], "alice")
    store.finish_job(job["job_id"], result={"trades": ["late"]})
    assert store.get_job(job["job_id"], "alice") == before
    assert before["status"] == state
