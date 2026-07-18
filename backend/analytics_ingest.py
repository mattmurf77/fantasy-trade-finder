"""
analytics_ingest.py — the POST /api/events pipeline (analytics platform P1).

Normative spec: docs/plans/analytics-platform/lld.md §2.1 (contract),
§4.1 (exact step order), §3.4 (rate limiter), §5 (races/timeouts/caps).
The route in server.py is a thin shim (it owns `_sessions` so it resolves
the session identity) delegating to `ingest_request()` here.

Contract highlights (LLD §2.1):
  • Always 200 for content — rate limiting, unknown types, PII scrubs and
    oversized props are "accepted-and-dropped" (counted in `accepted` and
    the observability-only `dropped` field), never a 4xx/429.
  • Accounting invariant (KD-2 / I-3): on any committed transaction,
    accepted + deduped + len(rejected) == len(events). The ONLY sum-short
    case is a whole-txn failure → {"accepted":0,"deduped":0,"rejected":[]}.
  • `rejected` reasons are a closed enum: bad_envelope | bad_event_id |
    bad_seq | no_identity.
  • Flag gate `analytics.ingest` (NOT analytics.client_events — that flag
    is the CLIENT emission gate only, P1 split); off → disposition
    "disabled", clients retain their queue.

Import discipline (invariant I-2, test T-2): this module must never import
record_event / touch_user_activity — ingestion never touches `users`,
denorm pointers, or streaks. Writes go through `database.ingest_engine`
(150 ms lock budget, BEGIN IMMEDIATE on SQLite — KD-12/RC-8), referenced
as a module attribute at call time so tests can patch it.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone

from flask import g, jsonify, request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError

from . import database as db
from .analytics_taxonomy import ALLOWED_CLIENT_EVENTS, CLIENT_EVENT_PROPS
from .database import user_events_table
from .feature_flags import is_enabled

# ---------------------------------------------------------------------------
# Health counters (LLD §2.3) — in-process, reset on deploy ("since": deploy).
# Moved here from server.py with the P1 route rewrite; the admin Health tab
# reads them via GET /api/admin/analytics/health → health_counters().
# ---------------------------------------------------------------------------

_health_lock = threading.Lock()
_health: dict[str, int] = {
    "accepted":                0,   # rows landed in user_events + accepted-and-dropped
    "deduped":                 0,   # intra-batch + already-in-db event_id repeats
    "dropped_unknown_type":    0,   # allowlist misses (accepted-and-dropped)
    "dropped_unknown_prop":    0,   # props stripped by the per-event registry
    "dropped_rate_limited":    0,   # envelopes shed by the per-device budget
    "dropped_oversized_props": 0,   # props > 4096 B serialized (envelope dropped)
    "pii_scrubbed":            0,   # denylist keys dropped / values redacted
    "rejected":                0,   # bad_envelope/bad_event_id/bad_seq/no_identity
    "txn_failed":              0,   # ingest txn raised (rolled back, sum-short 200)
}


def _health_bump(key: str, n: int = 1) -> None:
    if n <= 0:
        return
    with _health_lock:
        _health[key] = _health.get(key, 0) + n


def health_counters() -> dict[str, int]:
    """Snapshot of the ingest health counters (admin Health tab)."""
    with _health_lock:
        return dict(_health)


# ---------------------------------------------------------------------------
# Rate limiter (LLD §3.4) — dict[key → (hour_bucket, count)] under a lock.
# Whole-batch granularity (§4.1 step 6): the counter increments by the
# batch's valid-envelope count; busting the cap accepts-and-drops the whole
# batch's remaining envelopes. Advisory by design (RC-7): any bug here
# over-accepts, never rejects. Bounded at 10 000 entries — device_id is
# attacker-controlled, an unbounded dict is a memory DoS. Resets on deploy
# (deploy = free window; accepted, documented).
# ---------------------------------------------------------------------------

_RATE_DICT_MAX = 10_000
_RATE_LIMIT_FALLBACK = 600            # model_config `analytics_events_per_hr` seed
_rate_lock = threading.Lock()
_events_rate: dict[str, tuple[int, int]] = {}

_limit_cache: tuple[float, int] = (0.0, _RATE_LIMIT_FALLBACK)
_LIMIT_TTL_S = 60.0


def _rate_limit_per_hr() -> int:
    """Per-device hourly budget from model_config (cached 60 s, fail-open)."""
    global _limit_cache
    now = time.time()
    ts, val = _limit_cache
    if now - ts < _LIMIT_TTL_S:
        return val
    try:
        val = int(db.get_config().get("analytics_events_per_hr",
                                      _RATE_LIMIT_FALLBACK))
        if val <= 0:
            val = _RATE_LIMIT_FALLBACK
    except Exception:
        val = _RATE_LIMIT_FALLBACK
    _limit_cache = (now, val)
    return val


def _rate_exceeded(key: str, n: int) -> bool:
    """Increment key's hour bucket by n; True when the budget is busted."""
    bucket = int(time.time() // 3600)
    limit = _rate_limit_per_hr()
    with _rate_lock:
        b, c = _events_rate.get(key, (bucket, 0))
        if b != bucket:
            b, c = bucket, 0
        c += n
        _events_rate[key] = (b, c)
        if len(_events_rate) > _RATE_DICT_MAX:
            # Evict stale-bucket entries first, then oldest-inserted.
            stale = [k for k, (kb, _) in _events_rate.items() if kb != bucket]
            for k in stale:
                del _events_rate[k]
            while len(_events_rate) > _RATE_DICT_MAX:
                _events_rate.pop(next(iter(_events_rate)))
        return c > limit


# ---------------------------------------------------------------------------
# Batch / envelope caps (LLD §2.1)
# ---------------------------------------------------------------------------

MAX_BATCH = 50
MAX_CONTENT_LENGTH = 131_072      # 128 KiB, checked pre-read (never a Flask
                                  # MAX_CONTENT_LENGTH — that's app-global and
                                  # would break feedback screenshots)
MAX_PROPS_BYTES = 4_096           # client truncates at 2 048 — the margin is the point
MAX_PROPS_KEYS = 40
MAX_PROPS_DEPTH = 3
CLIENT_TS_CLAMP_S = 48 * 3600     # |server − client| beyond this → props.ts_suspect

_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_SEQ = 1_000_000

# ---------------------------------------------------------------------------
# PII denylist (FR-47) — extends the v0 _scrub_event_props key-substring
# rule with value-shape regexes. Server-side re-validation: the client
# scrubs before enqueue, this pass assumes the client is buggy or hostile.
# ---------------------------------------------------------------------------

_PROP_KEY_DENYLIST = ("token", "password", "email")
_PII_VALUE_RES = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),   # emails
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*"),                # bearer creds
    re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}"
               r"(?:\.[A-Za-z0-9_-]+)?"),                            # JWT shapes
    re.compile(r"\b\d(?:[ -]?\d){15,}\b"),                           # 16-digit runs
)
_PII_REPLACEMENT = "[scrubbed]"
_CLIENT_ERROR_MSG_MAX = 200


def _scrub_pii(props: dict, event_type: str) -> tuple[dict, int]:
    """Drop denylisted keys, redact PII-shaped string values. Returns the
    scrubbed dict + the number of scrub actions taken."""
    scrubbed = 0
    clean: dict = {}
    for k, v in props.items():
        if any(s in str(k).lower() for s in _PROP_KEY_DENYLIST):
            scrubbed += 1
            continue
        if isinstance(v, str):
            new_v = v
            for rx in _PII_VALUE_RES:
                new_v = rx.sub(_PII_REPLACEMENT, new_v)
            if new_v != v:
                scrubbed += 1
            v = new_v
        clean[k] = v
    if event_type == "client_error" and isinstance(clean.get("message"), str):
        clean["message"] = clean["message"][:_CLIENT_ERROR_MSG_MAX]
    return clean, scrubbed


def _props_depth_ok(obj, depth: int = 1) -> bool:
    if depth > MAX_PROPS_DEPTH:
        return False
    if isinstance(obj, dict):
        return all(_props_depth_ok(v, depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return all(_props_depth_ok(v, depth + 1) for v in obj)
    return True


# ---------------------------------------------------------------------------
# Envelope validation (§4.1 step 5) — closed reject enum
# ---------------------------------------------------------------------------

def _validate_envelope(env) -> str | None:
    """Return a reject reason (bad_envelope | bad_event_id | bad_seq) or
    None when structurally valid. Optional fields are lenient (coerced in
    _normalize); required fields are strict."""
    if not isinstance(env, dict):
        return "bad_envelope"
    etype = env.get("event_type")
    if not isinstance(etype, str) or not (1 <= len(etype) <= 64):
        return "bad_envelope"
    sid = env.get("session_id")
    if not isinstance(sid, str) or not (8 <= len(sid) <= 64):
        return "bad_envelope"
    props = env.get("props")
    if props is not None and not isinstance(props, dict):
        return "bad_envelope"
    eid = env.get("event_id")
    if not isinstance(eid, str) or not _EVENT_ID_RE.match(eid):
        return "bad_event_id"
    seq = env.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) \
            or not (1 <= seq <= MAX_SEQ):
        return "bad_seq"
    return None


def _parse_client_ts(raw) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ---------------------------------------------------------------------------
# FR-32 experiment stamping — guarded import stub. experiments.py does not
# exist until P3; P1 ships before it, so the except branch runs in
# production. Fail-open to no stamp, never to a failed batch.
# ---------------------------------------------------------------------------

def _experiment_stamp(user_id: str, event_type: str,
                      screen: str | None) -> str | None:
    try:
        from . import experiments  # type: ignore  # noqa: F401 — P3 module
    except Exception:
        return None
    try:
        stamp = experiments.stamp_for_event(user_id, event_type, screen)  # type: ignore[attr-defined]
        return json.dumps(stamp) if stamp else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Conflict-ignore insert — sanctioned dialect spot 1 (LLD §4.1 / FR-5)
# ---------------------------------------------------------------------------

def _insert_events_ignore(conn, rows: list[dict]) -> None:
    # NO index_where: the shipped ix_user_events_event_id is a FULL unique
    # index (§3.1) — a partial predicate here fails to match it on Postgres
    # ("no unique constraint matching the given keys").
    ins = sqlite_insert if conn.dialect.name == "sqlite" else pg_insert
    stmt = ins(user_events_table).on_conflict_do_nothing(
        index_elements=["event_id"])
    conn.execute(stmt, rows)


# ---------------------------------------------------------------------------
# The pipeline (LLD §4.1, exact order)
# ---------------------------------------------------------------------------

def _respond(accepted: int, deduped: int, rejected: list[dict],
             dropped: int, disposition: str):
    return jsonify({
        "accepted":    accepted,
        "deduped":     deduped,
        "rejected":    rejected,
        "dropped":     dropped,          # observability only — never in the
                                         # sum invariant or the purge rule
        "disposition": disposition,
    })


def ingest_request(session_user_id: str | None):
    """Handle POST /api/events. `session_user_id` is resolved by the
    server.py shim (it owns `_sessions`); None covers both no-token and
    dead-token (E-15 — silent fallback to device identity)."""

    # 1 — flag gate. Off → "disabled": clients RETAIN their queue (§4.6);
    # the queue cap bounds it and the backlog flows in on re-enable.
    if not is_enabled("analytics.ingest"):
        return _respond(0, 0, [], 0, "disabled")

    # 2 — Content-Length cap, pre-read. Purge-class: requeueing a
    # forever-unparseable batch is the bug.
    if (request.content_length or 0) > MAX_CONTENT_LENGTH:
        return _respond(0, 0, [], 0, "batch_rejected:too_large")

    # 3 — parse. Empty/absent events → legal no-op (sum 0 == 0).
    body = request.get_json(force=True, silent=True) or {}
    events = body.get("events")
    if not isinstance(events, list) or not events:
        return _respond(0, 0, [], 0, "ok")
    n = len(events)
    if n > MAX_BATCH:
        return _respond(0, 0, [], 0, "batch_rejected:too_many")

    # 4 — identity. Header X-Device-Id preferred; body device_id fallback
    # kept for v0 binaries (§1.1). No live session and no device id → the
    # one unattributable case: all-rejected(no_identity), client purges.
    device_id = ((request.headers.get("X-Device-Id") or "").strip()
                 or str(body.get("device_id") or "").strip() or None)
    if device_id:
        device_id = device_id[:64]
    user_id = session_user_id or (f"device:{device_id}" if device_id else None)
    if not user_id:
        rejected = [{"index": i, "reason": "no_identity"} for i in range(n)]
        _health_bump("rejected", n)
        return _respond(0, 0, rejected, 0, "ok")

    # 5 — per-envelope structural validation (closed reject enum).
    rejected: list[dict] = []
    valid: list[tuple[int, dict]] = []
    for i, env in enumerate(events):
        reason = _validate_envelope(env)
        if reason:
            rejected.append({"index": i, "reason": reason})
        else:
            valid.append((i, env))
    _health_bump("rejected", len(rejected))

    accepted = 0          # inserted + accepted-and-dropped
    dropped = 0           # the accepted-and-dropped share (observability)
    deduped = 0

    # 6 — rate limit, WHOLE-BATCH granularity: the hour counter takes the
    # batch's valid count; busting the cap sheds every remaining envelope
    # as accepted-and-dropped (never 429 — KD-2).
    if valid and _rate_exceeded(device_id or user_id, len(valid)):
        _health_bump("dropped_rate_limited", len(valid))
        accepted = dropped = len(valid)
        _health_bump("accepted", accepted)
        return _respond(accepted, 0, rejected, dropped, "ok")

    # Request-level stamps shared by every row.
    info = getattr(g, "device_info", {}) or {}
    source = (request.headers.get("X-Source") or "").strip() or "mobile"
    dev = (info.get("device_type") or "").lower()
    platform = (str(body.get("platform") or "").strip()
                or ("ios" if dev in ("iphone", "ipad", "macos") else dev)
                or None)
    now_iso = db._now()
    now_dt = datetime.now(timezone.utc)

    to_insert: list[dict] = []
    seen_ids: set[str] = set()
    for _i, env in valid:
        etype = env["event_type"]

        # 7 — taxonomy allowlist + namespace check (server-fired names are
        # not client-submittable) → accepted-and-dropped; unknown props
        # stripped + counted.
        if etype not in ALLOWED_CLIENT_EVENTS:
            _health_bump("dropped_unknown_type")
            accepted += 1
            dropped += 1
            continue
        props = dict(env.get("props") or {})
        allowed_props = CLIENT_EVENT_PROPS.get(etype, frozenset())
        unknown = [k for k in props if k not in allowed_props]
        if unknown:
            _health_bump("dropped_unknown_prop", len(unknown))
            for k in unknown:
                props.pop(k, None)

        # Oversized/over-deep props → whole envelope accepted-and-dropped
        # (client truncates at 2 048 B; hitting this means a client bug).
        if (len(props) > MAX_PROPS_KEYS
                or not _props_depth_ok(props)
                or len(json.dumps(props)) > MAX_PROPS_BYTES):
            _health_bump("dropped_oversized_props")
            accepted += 1
            dropped += 1
            continue

        # 8 — PII denylist re-validation (FR-47).
        if props:
            props, n_scrubbed = _scrub_pii(props, etype)
            _health_bump("pii_scrubbed", n_scrubbed)

        # 9 — client_ts clamp: advisory only (FR-12); |Δ| > 48 h flags the
        # row, occurred_at stays server time either way.
        client_ts = env.get("client_ts")
        client_ts = client_ts if isinstance(client_ts, str) else None
        parsed_ts = _parse_client_ts(client_ts)
        if parsed_ts and abs((now_dt - parsed_ts).total_seconds()) > CLIENT_TS_CLAMP_S:
            props["ts_suspect"] = True

        # `seq` rides in props — no new column (LLD §4.1); gap analysis is
        # sampled per (device_id, session_id), not scanned.
        props["seq"] = env["seq"]

        # 10 — intra-batch dedupe, first wins. Without this the txn's
        # SELECT misses same-batch repeats and they'd double-count.
        eid = env["event_id"]
        if eid in seen_ids:
            deduped += 1
            continue
        seen_ids.add(eid)

        screen = env.get("screen")
        screen = str(screen)[:64] if isinstance(screen, str) and screen else None

        to_insert.append({
            "user_id":     user_id,
            "event_type":  etype,
            "occurred_at": now_iso,
            "league_id":   None,
            "session_id":  env["session_id"][:64],
            "device_type": info.get("device_type"),
            "os_version":  info.get("os_version"),
            "app_version": info.get("app_version"),
            "source":      source,
            "props":       json.dumps(props) if props else None,
            "event_id":    eid,
            "device_id":   device_id,
            "platform":    platform,
            "screen":      screen,
            "client_ts":   client_ts[:32] if client_ts else None,
            # FR-32 stamp via guarded import — None until P3 lands.
            "experiments": _experiment_stamp(user_id, etype, screen),
        })

    # 11/12 — single transaction on ingest_engine: pre-insert SELECT for
    # dedupe ACCOUNTING, conflict-ignore insert for CORRECTNESS (races).
    # The OperationalError handler wraps the context-manager ENTRY too:
    # with BEGIN IMMEDIATE in the begin event (RC-8), the 150 ms lock
    # failure raises at .begin() entry, not at execute/commit.
    if to_insert:
        try:
            with db.ingest_engine.begin() as conn:
                if conn.dialect.name == "postgresql":
                    # Self-reverting per-txn budget (KD-12; RC-8 is
                    # sqlite-only — MVCC has no snapshot-upgrade class).
                    conn.exec_driver_sql("SET LOCAL lock_timeout = '150ms'")
                incoming = [r["event_id"] for r in to_insert]
                existing = {row[0] for row in conn.execute(
                    select(user_events_table.c.event_id)
                    .where(user_events_table.c.event_id.in_(incoming))
                ).fetchall()}
                fresh = [r for r in to_insert
                         if r["event_id"] not in existing]
                deduped += len(to_insert) - len(fresh)
                if fresh:
                    _insert_events_ignore(conn, fresh)
                accepted += len(fresh)
                dropped_rows = 0  # placeholder for symmetry; races that
                # slip past the SELECT are swallowed by conflict-ignore and
                # still counted `accepted` (documented imprecision, I-4).
        except OperationalError:
            # Lock budget blown (Sunday burst) or transient DB failure —
            # shed the batch, keep product writes healthy (KD-12). The ONE
            # sum-short case: client requeues everything (§2.1).
            _health_bump("txn_failed")
            return _respond(0, 0, [], 0, "ok")

    _health_bump("accepted", accepted)
    _health_bump("deduped", deduped)

    # 13 — respond. Invariant I-3: accepted + deduped + len(rejected) == N.
    return _respond(accepted, deduped, rejected, dropped, "ok")
