"""Scheduled advisory preparation. Views never call dispatch or any provider.

The existing authenticated realtime tick supplies a 15-minute opportunity.
Weekly next_due_at is eligibility for an attempt, not a promise of completion.
"""
from datetime import datetime, timedelta, timezone
import json
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, update, or_, tuple_

from .. import database as db
from ..feature_flags import is_enabled
from ..win_now_store import _lock_live_user, utc_now
from . import store
from .core import Unavailable, VERSION, digest
from .recommendation import thresholds
from .simulation import config

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "league_projections.json"


def settings():
    values = json.loads(CONFIG_PATH.read_text())
    schedule = values["schedule"]
    ZoneInfo(schedule["timezone"])
    if not 0 <= schedule["weekday"] <= 6 or not 0 <= schedule["hour"] <= 23 or not 0 <= schedule["minute"] <= 59 or not 1 <= values["batch_limit"] <= 8 or not 1 <= values["retention_days"] <= 30:
        raise ValueError("invalid_projection_batch_configuration")
    # The app-wide score SD and the outlook cuts are configuration, never code
    # defaults: a file without them is refused here, before any run or view.
    config(values["model"])
    thresholds(values)
    return values


def next_weekly_slot(at=None):
    """Next configured local weekly instant, DST-aware; never fixed 168h UTC."""
    at = at or datetime.now(timezone.utc)
    schedule = settings()["schedule"]
    local = at.astimezone(ZoneInfo(schedule["timezone"]))
    candidate = local.replace(hour=schedule["hour"], minute=schedule["minute"], second=0, microsecond=0)
    candidate += timedelta(days=(schedule["weekday"] - local.weekday()) % 7)
    if candidate <= local:
        candidate += timedelta(days=7)
    return candidate.astimezone(timezone.utc).isoformat()


def register(user_id, league_id, league_user_id, season, *, expected_user_created_at=None):
    """Called by successful connected-league sync, DB-only and idempotent."""
    if not is_enabled("league.projections"):
        return
    if not str(league_id).isdigit():
        return
    t = db.league_projection_targets_table
    key = uuid.uuid4().hex
    with db.engine.begin() as conn:
        _lock_live_user(conn, str(user_id))
        if expected_user_created_at is not None:
            incarnation = conn.execute(select(db.users_table.c.created_at).where(db.users_table.c.sleeper_user_id == str(user_id))).scalar()
            if incarnation != expected_user_created_at:
                return
        old = conn.execute(select(t).where(t.c.user_id == str(user_id), t.c.league_id == str(league_id))).mappings().first()
        if old:
            conn.execute(update(t).where(t.c.target_id == old["target_id"]).values(league_user_id=str(league_user_id), season=int(season)))
        else:
            conn.execute(insert(t).values(target_id=key, user_id=str(user_id), league_id=str(league_id), league_user_id=str(league_user_id),
                                          season=int(season), created_at=utc_now(), next_due_at=next_weekly_slot()))


def _expire_other_model_baselines(now):
    """A baseline last attempted under another model version is due now.

    Keyed on the last ATTEMPT, so each target is refreshed once per model
    change: an attempt under the current version, failed or not, waits for its
    weekly slot like any other.
    """
    t, r = db.league_projection_targets_table, db.league_projection_runs_table
    with db.engine.begin() as conn:
        rows = conn.execute(select(t.c.target_id, r.c.input_json).join(r, r.c.run_id == t.c.last_attempt_id)
                            .where(t.c.next_due_at > now.isoformat())).all()
        other = [target_id for target_id, raw in rows if json.loads(raw or "{}").get("expected_model_version") != VERSION]
        if other:
            conn.execute(update(t).where(t.c.target_id.in_(other)).values(next_due_at=now.isoformat()))


def target(user_id, league_id):
    t = db.league_projection_targets_table
    with db.engine.connect() as conn:
        row = conn.execute(select(t).where(t.c.user_id == user_id, t.c.league_id == league_id)).mappings().first()
    return dict(row) if row else None


def _bootstrap_connected(limit, *, user_id=None, league_id=None):
    """Reuse the verified own-action cohort, not imported opponent membership."""
    from ..outlook_calibration import connected_targets
    with db.engine.connect() as conn:
        incarnations = dict(conn.execute(select(db.users_table.c.sleeper_user_id, db.users_table.c.created_at)).tuples().all())
    connected, _ = connected_targets()
    with db.engine.connect() as conn:
        leagues = {r.sleeper_league_id: (r.platform, r.season) for r in conn.execute(
            select(db.leagues_table.c.sleeper_league_id, db.leagues_table.c.platform, db.leagues_table.c.season))}
        existing = set(conn.execute(select(db.league_projection_targets_table.c.user_id,
                                           db.league_projection_targets_table.c.league_id)).tuples())
    added = 0
    for item in connected:
        if added >= limit:
            break
        uid, lid = item["user_id"], item["league_id"]
        if user_id is not None and (uid != user_id or lid != league_id):
            continue
        platform, season = leagues.get(lid, (None, None))
        if (uid, lid) not in existing and (platform or "sleeper") == "sleeper" and str(season).isdigit():
            register(uid, lid, item.get("league_user_id") or uid, int(season), expected_user_created_at=incarnations.get(uid, "missing"))
            added += 1


def dispatch(fetch_json, *, initial=False, limit=None, user_id=None, league_id=None, foreground_busy=None):
    """Weekly dispatch, or explicit operator-only first baseline preparation.

    Initial preparation never refreshes a previously attempted baseline and
    uses the same cohort, account locks, bounded queue and next weekly slot.
    """
    if type(initial) is not bool:
        raise ValueError("invalid_initial_mode")
    if (user_id is None) != (league_id is None) or (user_id is not None and
            (not isinstance(user_id, str) or not isinstance(league_id, str) or
             not 1 <= len(user_id) <= 128 or not league_id.isdigit() or len(league_id) > 32)):
        raise ValueError("invalid_projection_target")
    if not initial and (limit is not None or user_id is not None):
        raise ValueError("initial_options_require_initial_mode")
    if not is_enabled("league.projections"):
        return {"status": "disabled", "queued": 0}
    options = settings()
    dispatch_limit = options["batch_limit"] if limit is None and not initial else (1 if limit is None else limit)
    if type(dispatch_limit) is not int or not 1 <= dispatch_limit <= options["batch_limit"]:
        raise ValueError("invalid_projection_batch_limit")
    store.maintenance()
    _bootstrap_connected(dispatch_limit, user_id=user_id, league_id=league_id)
    if not is_enabled("league.projections_provider_approved") or not options["policy_approved"]:
        return {"status": "approval_pending", "queued": 0}
    t, now = db.league_projection_targets_table, datetime.now(timezone.utc)
    if not initial:
        _expire_other_model_baselines(now)
    eligibility = [t.c.last_attempt_id.is_(None)] if initial else [t.c.next_due_at <= now.isoformat()]
    if initial:
        from ..outlook_calibration import connected_targets
        connected, _ = connected_targets()
        own_pairs = [(item["user_id"], item["league_id"]) for item in connected]
        eligibility.append(tuple_(t.c.user_id, t.c.league_id).in_(own_pairs))
    if user_id is not None:
        eligibility.extend([t.c.user_id == user_id, t.c.league_id == league_id])
    with db.engine.connect() as conn:
        due = conn.execute(select(t).where(*eligibility, or_(t.c.lease_until.is_(None), t.c.lease_until <= now.isoformat()))
                           .order_by(t.c.next_due_at, t.c.created_at).limit(dispatch_limit)).mappings().all()
    queued = 0
    for row in due:
        lease_token = uuid.uuid4().hex
        # CAS reserves this target across overlapping scheduler invocations.
        with db.engine.begin() as conn:
            claimed = conn.execute(update(t).where(*eligibility, t.c.target_id == row["target_id"], t.c.next_due_at == row["next_due_at"],
                    or_(t.c.lease_until.is_(None), t.c.lease_until <= now.isoformat()))
                    .values(lease_until=(now + timedelta(minutes=10)).isoformat(), lease_token=lease_token)).rowcount
        if not claimed:
            continue
        try:
            cfg = config({**options["model"], "draft_season": row["season"] + 1})
            job = store.create(row["user_id"], row["league_id"], {"league_user_id": row["league_user_id"], "config": cfg,
                                                              "kind": "baseline", "target_id": row["target_id"],
                                                              "scheduled_slot": ("initial:" + row["target_id"]) if initial else row["next_due_at"],
                                                              "next_weekly_slot": next_weekly_slot(now)}, target_lease=lease_token)
            with db.engine.begin() as conn:
                conn.execute(update(t).where(t.c.target_id == row["target_id"], t.c.lease_token == lease_token).values(last_attempt_id=job["run_id"],
                            next_due_at=next_weekly_slot(now), lease_until=None, lease_token=None))
            queued += 1
        except (Unavailable, ValueError):
            with db.engine.begin() as conn:
                conn.execute(update(t).where(t.c.target_id == row["target_id"], t.c.lease_token == lease_token).values(lease_until=None, lease_token=None))
    from .service import wake
    wake(fetch_json, foreground_busy=foreground_busy)
    return {"status": "dispatched", "queued": queued, "cadence": "weekly", "initial": initial, "schedule_timezone": options["schedule"]["timezone"]}



def view(user_id, league_id):
    """Read only. Stale means next weekly slot; no view-side provider checks."""
    options, item = settings(), target(user_id, league_id)
    success_id = item.get("last_success_id") if item else None
    attempt_id = item.get("last_attempt_id") if item else None
    rows = store.public_rows((success_id, attempt_id), user_id, league_id)
    success, attempt = rows.get(success_id), rows.get(attempt_id)
    state = "no_run"
    if success:
        due = datetime.fromisoformat(next_weekly_slot(datetime.fromisoformat(success["created_at"])))
        state = "stale" if datetime.now(timezone.utc) >= due else "current"
    if attempt and attempt["status"] in {"queued", "running"}:
        state = attempt["status"]
    elif attempt and attempt["status"] != "complete":
        state = "refresh_failed" if success else attempt["status"]
    reason = attempt.get("reason") if attempt else None
    if not options["policy_approved"] or not is_enabled("league.projections_provider_approved"):
        state, reason = "unsupported_policy", "projection_launch_approval_pending"
    return {"state": state, "reason": reason, "run": success, "attempt": attempt,
            "next_attempt_not_before": item["next_due_at"] if item else None,
            "schedule_timezone": options["schedule"]["timezone"], "cadence": "weekly", "schedule": options["schedule"], "retention_days": options["retention_days"],
            "scenario_defaults": options["model"], "live_weeks_supported": False,
            "schedule_note": "Eligible for the next successful scheduled batch; completion time is not guaranteed."}
