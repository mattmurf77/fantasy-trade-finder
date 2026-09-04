"""Durable Win Now evidence. Never writes dynasty ranking/swipe tables."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from . import database as db


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(value) -> str:
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def _immutable(table, values):
    try:
        with db.engine.begin() as conn:
            conn.execute(insert(table).values(**values))
    except IntegrityError:
        # Reusing an identical immutable snapshot is idempotent. A hash/id
        # collision with different content is an error, never an overwrite.
        pk = list(table.primary_key.columns)[0]
        with db.engine.connect() as conn:
            old = conn.execute(select(table).where(pk == values[pk.name])).mappings().first()
        if old is None or old["payload_json"] != values["payload_json"]:
            raise


def save_forecasts(snapshot: dict) -> None:
    _immutable(db.season_forecast_snapshots_table, {
        "snapshot_id": snapshot["snapshot_id"], "season": str(snapshot["season"]),
        "source": snapshot.get("provider", "unknown"),
        "captured_at": snapshot["captured_at"], "payload_json": dumps(snapshot),
    })


def save_projection(snapshot_id: str, league_id: str, forecast_id: str,
                    payload: dict, created_at: str, expires_at: str) -> None:
    _immutable(db.season_projection_snapshots_table, {
        "snapshot_id": snapshot_id, "league_id": league_id,
        "forecast_snapshot_id": forecast_id, "payload_json": dumps(payload),
        "created_at": created_at, "expires_at": expires_at,
    })


def _lock_live_user(conn, user_id):
    # SQLite needs the write reservation before its read; PostgreSQL locks
    # the account row shared with account deletion. No long simulation holds it.
    if conn.dialect.name == "sqlite":
        conn.exec_driver_sql("BEGIN IMMEDIATE")
    exists = conn.execute(select(db.users_table.c.sleeper_user_id)
                          .where(db.users_table.c.sleeper_user_id == user_id).with_for_update()).scalar()
    if not exists:
        raise ValueError("account_no_longer_available")


def create_job(user_id: str, league_id: str, inputs: dict, *, require_user=False) -> dict:
    now = utc_now()
    row = {"job_id": uuid.uuid4().hex, "user_id": user_id,
           "league_id": league_id, "status": "queued", "created_at": now,
           "updated_at": now,
           "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
           "input_json": dumps(inputs)}
    with db.engine.begin() as conn:
        if require_user:
            _lock_live_user(conn, user_id)
        conn.execute(insert(db.win_now_jobs_table).values(**row))
    return row


def expire_jobs() -> None:
    t = db.win_now_jobs_table
    with db.engine.begin() as conn:
        conn.execute(update(t).where(t.c.status.in_(("queued", "running")), t.c.expires_at <= utc_now())
                     .values(status="failed", reason="job_expired", updated_at=utc_now()))


def prune_history() -> None:
    """Bound storage: jobs 7 days, trade evidence 180, forecast replay 400."""
    now = datetime.now(timezone.utc)
    with db.engine.begin() as conn:
        for table, column, days in (
            (db.win_now_jobs_table, "created_at", 7),
            (db.win_now_decisions_table, "created_at", 180),
            (db.win_now_scenarios_table, "created_at", 180),
            (db.season_projection_snapshots_table, "created_at", 400),
            (db.season_forecast_snapshots_table, "captured_at", 400),
        ):
            conn.execute(delete(table).where(getattr(table.c, column) < (now - timedelta(days=days)).isoformat()))


def get_job(job_id: str, user_id: str) -> dict | None:
    t = db.win_now_jobs_table
    with db.engine.connect() as conn:
        row = conn.execute(select(t).where(t.c.job_id == job_id, t.c.user_id == user_id)).mappings().first()
    return dict(row) if row else None


def pending_jobs(limit: int = 8) -> list[dict]:
    t = db.win_now_jobs_table
    with db.engine.connect() as conn:
        rows = conn.execute(select(t).where(t.c.status == "queued")
                            .order_by(t.c.created_at).limit(limit)).mappings().all()
    return [dict(r) for r in rows]


def recover_interrupted_jobs() -> int:
    """Called once at process startup; committed input survives worker death."""
    t = db.win_now_jobs_table
    with db.engine.begin() as conn:
        result = conn.execute(update(t).where(t.c.status == "running")
                              .values(status="queued", updated_at=utc_now()))
    return result.rowcount


def claim_job(job_id: str) -> bool:
    t = db.win_now_jobs_table
    with db.engine.begin() as conn:
        result = conn.execute(update(t).where(t.c.job_id == job_id, t.c.status == "queued")
                              .values(status="running", updated_at=utc_now()))
    return result.rowcount == 1


def finish_job(job_id: str, result: dict | None = None, reason: str | None = None) -> None:
    t = db.win_now_jobs_table
    values = {"status": "failed" if reason else "complete", "updated_at": utc_now(),
              "reason": reason, "result_json": dumps(result) if result is not None else None}
    if result and result.get("meta", {}).get("expires_at"):
        values["expires_at"] = result["meta"]["expires_at"]
    with db.engine.begin() as conn:
        conn.execute(update(t).where(t.c.job_id == job_id).values(**values))


def save_scenario(user_id: str, league_id: str, objective: str,
                  scenario: dict, meta: dict, *, require_user=False, job_id=None) -> dict:
    row = dict(scenario)
    asset_key = identity({"league_id": league_id, "buyer": row.get("buyer_roster_id"),
                          "partner": row["partner_roster_id"],
                          "give": sorted(a["id"] for a in row["give"]),
                          "receive": sorted(a["id"] for a in row["receive"])})
    # Fresh UUID separates independently evaluated forecasts; asset_key joins
    # the same exchange across refreshes without rewriting earlier evidence.
    row["scenario_id"] = uuid.uuid4().hex
    row["asset_key"] = asset_key
    row["meta"] = meta
    values = {
        "scenario_id": row["scenario_id"], "user_id": user_id,
        "league_id": league_id, "snapshot_id": meta["snapshot_id"],
        "objective": objective, "asset_key": asset_key, "created_at": utc_now(),
        "expires_at": meta["expires_at"], "payload_json": dumps(row),
    }
    if require_user or job_id:
        with db.engine.begin() as conn:
            _lock_live_user(conn, user_id)
            if job_id:
                t = db.win_now_jobs_table
                live = conn.execute(select(t.c.job_id).where(t.c.job_id == job_id, t.c.user_id == user_id,
                                    t.c.status == "running").with_for_update()).scalar()
                if not live:
                    raise ValueError("job_no_longer_available")
            conn.execute(insert(db.win_now_scenarios_table).values(**values))
    else:
        _immutable(db.win_now_scenarios_table, values)
    return row


def get_scenario(scenario_id: str, user_id: str) -> dict | None:
    t = db.win_now_scenarios_table
    with db.engine.connect() as conn:
        row = conn.execute(select(t).where(t.c.scenario_id == scenario_id,
                                           t.c.user_id == user_id)).mappings().first()
    return dict(row) if row else None


def save_decision(user_id: str, scenario_id: str, decision: str, *, require_user=False) -> None:
    if decision not in ("like", "pass"):
        raise ValueError("invalid_decision")
    t = db.win_now_decisions_table
    values = {"user_id": user_id, "scenario_id": scenario_id,
              "decision": decision, "created_at": utc_now()}
    with db.engine.begin() as conn:
        if require_user:
            _lock_live_user(conn, user_id)
        old = conn.execute(select(t.c.id).where(t.c.user_id == user_id,
                                                t.c.scenario_id == scenario_id)).scalar()
        if old is not None:
            conn.execute(update(t).where(t.c.id == old).values(decision=decision))
        else:
            try:
                with conn.begin_nested():
                    conn.execute(insert(t).values(**values))
            except IntegrityError:
                conn.execute(update(t).where(t.c.user_id == user_id,
                                             t.c.scenario_id == scenario_id).values(decision=decision))
