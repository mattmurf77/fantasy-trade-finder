"""POST /api/events — first-party client-event ingestion, P1 contract
(docs/plans/analytics-platform/lld.md §2.1 / §4.1). Rewritten from the v0
contract (404/400/429, {accepted,dropped}) to the final always-200 pipeline.

Covers:
  (a) flag off (`analytics.ingest`) → 200 disposition "disabled", no rows
  (b) flag on → batch lands rows with the full envelope; {accepted, deduped,
      rejected, dropped, disposition}
  (c) identity — session token wins; else user_id='device:<id>'; neither →
      all-rejected(no_identity), still 200
  (d) dedup on event_id (within a batch and across retries) → `deduped`
  (e) unknown event_type → accepted-and-dropped (counted in accepted + dropped,
      no row), rest of batch unaffected
  (f) oversize batch (>50) → disposition batch_rejected:too_many, no rows
  (g) per-device rate limit → 200, accepted-and-dropped (never 429)
  (h) accounting invariant (T-3): accepted + deduped + len(rejected) == N
      across a batch mixing every disposition
  (i) empty batch → legal no-op
  (j) PII scrub of an allowed prop value (FR-47)

Isolated in-memory SQLite. The pipeline lives in backend/analytics_ingest.py
and writes via db.ingest_engine, so the harness patches BOTH db.engine and
db.ingest_engine to the same engine (two sqlite:///:memory: engines are
different databases), and patches analytics_ingest.is_enabled (the pipeline
imports the name directly).
"""
import json
import time
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.database as db_module
import backend.server as server
from backend.database import metadata, user_events_table

USER = "user_events_test"
TOKEN = "events-test-token"
DEVICE = "dev_abc123"


def _envelope(i=0, event_type="screen_viewed", **over):
    env = {
        "event_id": f"evt-{i:04d}xx",           # ≥8 chars, matches _EVENT_ID_RE
        "event_type": event_type,
        "client_ts": "2026-07-17T12:00:00Z",
        "screen": "Trades",
        "props": {"tab": "trades"},             # allowed prop for screen_viewed
        "session_id": "sess-uuid-0001",
        "seq": i + 1,
    }
    env.update(over)
    return env


def _post(client, events, device_id=DEVICE, token=None, headers=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["X-Session-Token"] = token
    if device_id is not None:
        h["X-Device-Id"] = device_id
    if headers:
        h.update(headers)
    return client.post("/api/events", headers=h,
                       data=json.dumps({"events": events}))


def _rows(engine):
    with engine.begin() as conn:
        return conn.execute(
            select(user_events_table).order_by(user_events_table.c.id)
        ).fetchall()


def _assert_invariant(body, n):
    """The one contract that must always hold on a committed txn."""
    assert body["accepted"] + body["deduped"] + len(body["rejected"]) == n


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    sess = {"user_id": USER, "last_active": 0.0}
    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(db_module, "ingest_engine", engine), \
         patch.object(ingest, "is_enabled",
                      lambda k: k == "analytics.ingest"):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        with ingest._rate_lock:
            ingest._events_rate.clear()
        try:
            yield client, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with ingest._rate_lock:
                ingest._events_rate.clear()


# ── (a) flag off → disabled, queue retained (no 404) ───────────────────────

def test_flag_off_disabled():
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(ingest, "is_enabled", lambda k: False):
        r = _post(client, [_envelope()])
    assert r.status_code == 200
    assert r.get_json()["disposition"] == "disabled"
    assert r.get_json()["accepted"] == 0


# ── (b) batch insert works ─────────────────────────────────────────────────

def test_batch_insert_with_session(harness):
    client, engine = harness
    events = [_envelope(i, event_type=t) for i, t in
              enumerate(["app_opened", "screen_viewed", "find_trades_tapped"])]
    r = _post(client, events, token=TOKEN,
              headers={"X-Device": "iphone", "X-OS-Version": "18.1",
                       "X-App-Version": "1.8.0"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["accepted"] == 3 and body["deduped"] == 0
    assert body["rejected"] == [] and body["disposition"] == "ok"
    _assert_invariant(body, 3)

    rows = _rows(engine)
    assert len(rows) == 3
    first = rows[0]._mapping
    assert first["user_id"] == USER          # session identity wins
    assert first["event_type"] == "app_opened"
    assert first["device_id"] == DEVICE
    assert first["platform"] == "ios"        # derived from X-Device
    assert first["screen"] == "Trades"
    assert first["session_id"] == "sess-uuid-0001"
    assert first["source"] == "mobile"
    assert first["occurred_at"]              # server-stamped
    # screen_viewed row keeps its allowed prop + the seq rider
    sv = next(r._mapping for r in rows if r._mapping["event_type"] == "screen_viewed")
    props = json.loads(sv["props"])
    assert props["tab"] == "trades" and props["seq"] == 2


# ── (c) identity resolution ────────────────────────────────────────────────

def test_no_session_uses_device_identity(harness):
    client, engine = harness
    r = _post(client, [_envelope(event_type="signin_attempted",
                                 props={"method": "apple"})])
    body = r.get_json()
    assert body["accepted"] == 1
    assert _rows(engine)[0]._mapping["user_id"] == f"device:{DEVICE}"


def test_no_session_no_device_all_rejected(harness):
    client, _ = harness
    r = _post(client, [_envelope(), _envelope(1)], device_id=None)
    assert r.status_code == 200
    body = r.get_json()
    assert body["accepted"] == 0
    assert [x["reason"] for x in body["rejected"]] == ["no_identity", "no_identity"]
    _assert_invariant(body, 2)


# ── (d) dedup on event_id ──────────────────────────────────────────────────

def test_dedup_across_retries(harness):
    client, engine = harness
    batch = [_envelope(1), _envelope(2)]
    r1 = _post(client, batch, token=TOKEN)
    assert r1.get_json()["accepted"] == 2
    r2 = _post(client, batch, token=TOKEN)           # idempotent replay
    body = r2.get_json()
    assert body["accepted"] == 0 and body["deduped"] == 2
    _assert_invariant(body, 2)
    assert len(_rows(engine)) == 2


def test_dedup_within_batch(harness):
    client, engine = harness
    r = _post(client, [_envelope(7), _envelope(7)], token=TOKEN)
    body = r.get_json()
    assert body["accepted"] == 1 and body["deduped"] == 1
    _assert_invariant(body, 2)
    assert len(_rows(engine)) == 1


# ── (e) unknown event types → accepted-and-dropped, batch continues ────────

def test_unknown_type_dropped(harness):
    client, engine = harness
    r = _post(client, [
        _envelope(1, event_type="screen_viewed"),
        _envelope(2, event_type="totally_made_up", props={}),
        _envelope(3, event_type="find_trades_tapped", props={}),
    ], token=TOKEN)
    body = r.get_json()
    # accepted counts the dropped-unknown (accepted-and-dropped); dropped=1
    assert body["accepted"] == 3 and body["dropped"] == 1 and body["deduped"] == 0
    _assert_invariant(body, 3)
    types = [row._mapping["event_type"] for row in _rows(engine)]
    assert types == ["screen_viewed", "find_trades_tapped"]   # unknown never landed


# ── (f) oversize batch → batch_rejected, no rows ───────────────────────────

def test_oversize_batch_rejected(harness):
    client, engine = harness
    r = _post(client, [_envelope(i) for i in range(51)], token=TOKEN)
    assert r.status_code == 200
    assert r.get_json()["disposition"] == "batch_rejected:too_many"
    assert len(_rows(engine)) == 0


# ── (g) rate limit → accepted-and-dropped, never 429 ───────────────────────

def test_rate_limit_accepts_and_drops(harness):
    client, engine = harness
    bucket = int(time.time() // 3600)
    with ingest._rate_lock:
        ingest._events_rate[DEVICE] = (bucket, 10_000)   # cap already blown
    r = _post(client, [_envelope()], token=TOKEN)
    assert r.status_code == 200
    body = r.get_json()
    assert body["accepted"] == 1 and body["dropped"] == 1
    _assert_invariant(body, 1)
    assert len(_rows(engine)) == 0                        # nothing persisted


# ── (h) accounting invariant across a fully mixed batch (T-3) ──────────────

def test_accounting_invariant_mixed_batch(harness):
    client, engine = harness
    # Pre-seed one event_id so it dedups against the DB.
    _post(client, [_envelope(1)], token=TOKEN)
    batch = [
        _envelope(1),                                   # dup-in-db → deduped
        _envelope(2), _envelope(2),                     # dup-in-batch → 1 deduped
        _envelope(3, event_type="nope", props={}),      # unknown → accepted-and-dropped
        {"event_type": "screen_viewed"},                # malformed (no id/seq) → rejected
        _envelope(4),                                   # clean insert
    ]
    r = _post(client, batch, token=TOKEN)
    body = r.get_json()
    _assert_invariant(body, len(batch))
    assert body["deduped"] == 2                          # db-dup + batch-dup
    assert len(body["rejected"]) == 1
    assert body["accepted"] == 3                         # unknown(1) + evt-2(1) + evt-4(1)


# ── (i) empty batch → legal no-op ──────────────────────────────────────────

def test_empty_batch_noop(harness):
    client, _ = harness
    r = _post(client, [], token=TOKEN)
    body = r.get_json()
    assert body == {"accepted": 0, "deduped": 0, "rejected": [],
                    "dropped": 0, "disposition": "ok"}


# ── (j) PII scrub of an allowed prop value (FR-47) ─────────────────────────

def test_pii_scrubbed_in_allowed_prop(harness):
    client, engine = harness
    r = _post(client, [_envelope(
        1, event_type="client_error",
        props={"screen": "SignIn", "error_kind": "auth",
               "message": "failed for a@b.com bearer eyJabc.def.ghi", "fatal": False},
    )], token=TOKEN)
    assert r.get_json()["accepted"] == 1
    props = json.loads(_rows(engine)[0]._mapping["props"])
    assert "a@b.com" not in props["message"]
    assert "[scrubbed]" in props["message"]
    assert props["error_kind"] == "auth"        # non-PII prop preserved
