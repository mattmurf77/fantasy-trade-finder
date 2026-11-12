"""Bounded durable work with the existing account-deletion row fence."""
from datetime import datetime, timezone, timedelta
import json
import uuid

from sqlalchemy import delete, insert, select, update, func

from .. import database as db
from ..win_now_store import _lock_live_user, dumps, utc_now
from .core import Unavailable, VERSION, digest, semantic_facts


def table():
    return db.league_projection_runs_table


def maintenance():
    t = table()
    now = datetime.now(timezone.utc)
    from .batch import settings
    options = settings()
    retention = options["retention_days"]
    # Decision 8 (operator, 2026-11-11): complete weekly BASELINE runs are
    # kept for `baseline_retention_days` so the season's forecasts can be
    # scored against the final order. Absent = `retention_days`, unchanged.
    # A run kept only for scoring drops its snapshot (the pick odds live in
    # result_json), so the extension costs the result, not the capture.
    keep_days = options.get("baseline_retention_days", retention)
    cutoff = (now - timedelta(days=retention)).isoformat()
    with db.engine.begin() as conn:
        conn.execute(update(t).where(t.c.status == "running", t.c.expires_at <= now.isoformat(), t.c.retry_count < 1)
                     .values(status="queued", retry_count=t.c.retry_count + 1, worker_token=None,
                             expires_at=(now + timedelta(minutes=45)).isoformat(), updated_at=now.isoformat(), reason="interrupted_attempt_requeued"))
        conn.execute(update(t).where(t.c.status.in_(("queued", "running")), t.c.expires_at <= now.isoformat())
                     .values(status="failed", reason="job_deadline_exceeded", updated_at=now.isoformat()))
        retained = select(db.league_projection_targets_table.c.last_success_id).where(db.league_projection_targets_table.c.last_success_id.is_not(None))
        kept = []
        if keep_days > retention:
            old = conn.execute(select(t.c.run_id, t.c.input_json).where(
                t.c.created_at < cutoff, t.c.created_at >= (now - timedelta(days=keep_days)).isoformat(),
                t.c.status == "complete", t.c.run_id.not_in(retained))).all()
            kept = [run_id for run_id, text in old if _is_baseline(text)]
            if kept:
                conn.execute(update(t).where(t.c.run_id.in_(kept), t.c.snapshot_json.is_not(None)).values(snapshot_json=None))
        conn.execute(delete(t).where(t.c.created_at < cutoff, t.c.run_id.not_in(retained), t.c.run_id.not_in(kept)))


def _is_baseline(input_json):
    try:
        return json.loads(input_json or "{}").get("kind") == "baseline"
    except (TypeError, ValueError, AttributeError):
        return False


def create(user_id, league_id, inputs, *, target_lease=None, snapshot=None):
    maintenance()
    # Freeze server-owned execution identity at admission. Pre-version jobs are
    # never silently migrated during recovery after a deployment.
    inputs = {**inputs, "expected_model_version": VERSION}
    if inputs.get("baseline_run_id"):
        inputs["expected_baseline_model_version"] = VERSION
    t, stamp = table(), utc_now()
    request_hash = digest(inputs)
    with db.engine.begin() as conn:
        _lock_live_user(conn, user_id)
        if inputs.get("kind") == "baseline":
            target = db.league_projection_targets_table
            existing = conn.execute(select(target.c.target_id).where(target.c.target_id == inputs.get("target_id"),
                                    target.c.user_id == user_id, target.c.league_id == league_id,
                                    target.c.lease_token == target_lease, target.c.lease_until > stamp)).scalar()
            if not existing:
                raise ValueError("target_generation_changed")
        pending = conn.execute(select(t).where(t.c.user_id == user_id, t.c.status.in_(("queued", "running")))).mappings().all()
        if pending:
            same = next((r for r in pending if r["request_hash"] == request_hash and r["league_id"] == league_id), None)
            if same:
                return dict(same)
            raise Unavailable("another_run_pending", state="busy")
        if conn.execute(select(func.count()).select_from(t).where(t.c.status.in_(("queued", "running")))).scalar() >= 8:
            raise Unavailable("queue_full", state="busy")
        recent = conn.execute(select(func.count()).select_from(t).where(t.c.user_id == user_id,
                              t.c.created_at > (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat())).scalar()
        if recent >= 4:
            raise Unavailable("refresh_rate_limit", state="busy")
        row = {"run_id": uuid.uuid4().hex, "user_id": user_id, "league_id": league_id, "status": "queued",
               "created_at": stamp, "updated_at": stamp, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat(),
               "request_hash": request_hash, "input_json": dumps(inputs), "snapshot_json": dumps(snapshot) if snapshot is not None else None}
        conn.execute(insert(t).values(**row))
        if inputs.get("kind") == "baseline":
            conn.execute(update(db.league_projection_targets_table).where(
                db.league_projection_targets_table.c.target_id == inputs["target_id"],
                db.league_projection_targets_table.c.lease_token == target_lease).values(last_attempt_id=row["run_id"], next_due_at=inputs["next_weekly_slot"], lease_until=None, lease_token=None))
        return row


def get(run_id, user_id, league_id):
    t = table()
    with db.engine.connect() as conn:
        row = conn.execute(select(t).where(t.c.run_id == run_id, t.c.user_id == user_id, t.c.league_id == league_id)).mappings().first()
    return dict(row) if row else None



def public_rows(run_ids, user_id, league_id):
    """Request-local view rows; exclude private snapshots and worker inputs."""
    ids = tuple(dict.fromkeys(run_id for run_id in run_ids if run_id))
    if not ids:
        return {}
    t = table()
    columns = (t.c.run_id, t.c.status, t.c.created_at, t.c.updated_at,
               t.c.input_hash, t.c.reason, t.c.details_json, t.c.result_json)
    with db.engine.connect() as conn:
        rows = conn.execute(select(*columns).where(
            t.c.run_id.in_(ids), t.c.user_id == user_id, t.c.league_id == league_id)).mappings().all()
    return {row["run_id"]: dict(row) for row in rows}


def control(run_id, user_id, league_id):
    """Read only cancellation facts; never transfer the captured/result payload."""
    t = table()
    with db.engine.connect() as conn:
        row = conn.execute(select(t.c.status, t.c.worker_token, t.c.expires_at).where(
            t.c.run_id == run_id, t.c.user_id == user_id, t.c.league_id == league_id)).mappings().first()
    return dict(row) if row else None


def latest(user_id, league_id):
    t = table()
    with db.engine.connect() as conn:
        row = conn.execute(select(t).where(t.c.user_id == user_id, t.c.league_id == league_id, t.c.status == "complete")
                           .order_by(t.c.created_at.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def claim():
    maintenance()
    t = table()
    with db.engine.begin() as conn:
        # A single application process serves today. Atomic row claiming also
        # prevents duplicate jobs across a rolling deploy; queue cap is best
        # effort globally, strict per user under that user's row lock.
        row = conn.execute(select(t).where(t.c.status == "queued").order_by(t.c.created_at).limit(1)).mappings().first()
        if not row:
            return None
        token = uuid.uuid4().hex
        deadline = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        result = conn.execute(update(t).where(t.c.run_id == row["run_id"], t.c.status == "queued")
                              .values(status="running", worker_token=token, expires_at=deadline, updated_at=utc_now()))
        return {**dict(row), "worker_token": token, "expires_at": deadline, "status": "running"} if result.rowcount else None


def _write(row, **values):
    t = table()
    try:
        with db.engine.begin() as conn:
            _lock_live_user(conn, row["user_id"])
            updated = bool(conn.execute(update(t).where(t.c.run_id == row["run_id"], t.c.status == "running",
                           t.c.worker_token == row.get("worker_token"), t.c.expires_at > utc_now())
                           .values(updated_at=utc_now(), **values)).rowcount)
            if updated and values.get("status") == "complete":
                inputs = json.loads(row["input_json"])
                if inputs.get("kind") == "baseline":
                    target = db.league_projection_targets_table
                    conn.execute(update(target).where(target.c.target_id == inputs["target_id"],
                                 target.c.user_id == row["user_id"], target.c.last_attempt_id == row["run_id"])
                                 .values(last_success_id=row["run_id"]))
            return updated
    except ValueError:
        return False  # Account was deleted: never recreate its run or evidence.


def save_snapshot(row, snapshot, cfg):
    facts = semantic_facts(snapshot)
    input_hash = digest({"snapshot": facts, "config": cfg, "model_version": VERSION})
    if not _write(row, snapshot_json=dumps(snapshot), input_hash=input_hash):
        raise Unavailable("cancelled", state="cancelled")
    t = table()
    with db.engine.connect() as conn:
        previous = conn.execute(select(t.c.result_json).where(t.c.user_id == row["user_id"], t.c.league_id == row["league_id"],
                                t.c.status == "complete", t.c.input_hash == input_hash).order_by(t.c.created_at.desc()).limit(1)).scalar()
    return json.loads(previous) if previous else None


def finish(row, result):
    return _write(row, status="complete", result_json=dumps(result), reason=None, details_json=None)


def fail(row, exc):
    return _write(row, status=exc.state, reason=exc.reason, details_json=dumps(exc.details))


def cancel(run_id, user_id, league_id):
    t = table()
    with db.engine.begin() as conn:
        _lock_live_user(conn, user_id)
        return bool(conn.execute(update(t).where(t.c.run_id == run_id, t.c.user_id == user_id, t.c.league_id == league_id,
                    t.c.status.in_(("queued", "running"))).values(status="cancelled", updated_at=utc_now(), reason="cancelled")).rowcount)
