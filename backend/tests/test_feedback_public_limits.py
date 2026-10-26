"""#360 QA P2-2 — POST /api/feedback is public, so it gets a body cap and a
throttle.

- A body over FEEDBACK_MAX_BODY_BYTES (64 KiB) is 413 `too_large`, checked on
  Content-Length before the body is read.
- `client_created_at` is cut to 40 characters.
- 20 accepted notes per rolling hour per key; the 21st new note is 429
  `rate_limited`. The key is the verified user_id, else an unverified
  session's token hash (so users behind one carrier NAT don't share the IP's
  budget; the raw token is never in the key or a log), else X-Device-Id, else
  the client IP (the rightmost X-Forwarded-For hop, which Render's proxy
  appends; hops to its left are client-set). Idempotent duplicates don't
  count, and a throttled duplicate is still answered 200 `duplicate`.

The client keeps any rejected note unsynced and retries it later
(useFeedback._syncOne turns every error into `synced: false`).
In-memory SQLite, injected sessions; conftest resets the throttle per test.
"""
import hashlib
import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.server as server
from backend.database import metadata, app_feedback_table

ME = "user_fb_limits"
VERIFIED = "tok-limits-verified"
UNVERIFIED = "tok-limits-unverified"
UNVERIFIED_2 = "tok-limits-unverified-two"   # another person, same carrier NAT


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "record_event", MagicMock()):
        with server._sessions_lock:
            server._sessions[VERIFIED] = {"verified": True, "user_id": ME,
                                          "display_name": "Me", "last_active": 0.0}
            server._sessions[UNVERIFIED] = {"user_id": ME, "last_active": 0.0}
            server._sessions[UNVERIFIED_2] = {"user_id": "user_fb_other", "last_active": 0.0}
        try:
            yield client, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(VERIFIED, None)
                server._sessions.pop(UNVERIFIED, None)
                server._sessions.pop(UNVERIFIED_2, None)


def _post(client, client_id, *, token=None, device=None, xff=None, created="2026-10-26T12:00:00Z",
          text="the trade card overlapped the tab bar", raw=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Session-Token"] = token
    if device:
        headers["X-Device-Id"] = device
    if xff:
        headers["X-Forwarded-For"] = xff
    data = raw if raw is not None else json.dumps({
        "client_id": client_id, "screen": "Trades", "severity": "bug",
        "text": text, "client_created_at": created})
    return client.post("/api/feedback", headers=headers, data=data)


def _count(engine):
    with engine.connect() as conn:
        return len(conn.execute(select(app_feedback_table.c.id)).fetchall())


def _fill(client, n, prefix, **kw):
    for i in range(n):
        r = _post(client, f"{prefix}-{i}", **kw)
        assert r.status_code == 201, (i, r.get_json())


# ── size cap ────────────────────────────────────────────────────────────────

def test_oversized_body_is_413_before_it_is_read(harness):
    client, engine = harness
    big = json.dumps({"client_id": "fb-big", "screen": "Trades", "severity": "bug",
                      "text": "x" * (server.FEEDBACK_MAX_BODY_BYTES + 10),
                      "client_created_at": "2026-10-26T12:00:00Z"})
    with patch.object(server.app.request_class, "get_json",
                      side_effect=AssertionError("body read before the size check")):
        r = _post(client, "fb-big", raw=big)
    assert r.status_code == 413
    assert r.get_json()["error"] == "too_large"
    assert _count(engine) == 0


def test_a_body_at_the_cap_is_still_read(harness):
    client, engine = harness
    r = _post(client, "fb-normal", text="y" * server.FEEDBACK_TEXT_MAX)
    assert r.status_code == 201
    assert _count(engine) == 1


# ── client_created_at ─────────────────────────────────────────────────────────

def test_client_created_at_is_truncated_to_40_chars(harness):
    client, engine = harness
    r = _post(client, "fb-ts", created="2026-10-26T12:00:00.000000+00:00" + "Z" * 500)
    assert r.status_code == 201
    with engine.connect() as conn:
        stored = conn.execute(select(app_feedback_table.c.client_created_at)).scalar_one()
    assert len(stored) == 40
    assert stored == ("2026-10-26T12:00:00.000000+00:00" + "Z" * 500)[:40]


# ── throttle ────────────────────────────────────────────────────────────────

def test_the_21st_new_note_in_an_hour_is_429(harness):
    client, engine = harness
    _fill(client, 20, "fb-n", device="dev-1")
    r = _post(client, "fb-n-20", device="dev-1")
    assert r.status_code == 429
    assert r.get_json() == {"error": "rate_limited"}
    assert _count(engine) == 20


def test_duplicates_do_not_count_and_are_answered_even_when_throttled(harness):
    client, engine = harness
    _fill(client, 19, "fb-d", device="dev-2")
    for _ in range(5):                                   # idempotent retries
        r = _post(client, "fb-d-0", device="dev-2")
        assert r.status_code == 200 and r.get_json()["duplicate"] is True
    assert _post(client, "fb-d-19", device="dev-2").status_code == 201   # 20th new
    assert _post(client, "fb-d-20", device="dev-2").status_code == 429   # 21st new
    held = _post(client, "fb-d-3", device="dev-2")                       # throttled dup
    assert held.status_code == 200
    assert held.get_json()["duplicate"] is True and held.get_json()["server_id"] > 0
    assert _count(engine) == 20


def test_separate_device_keys_are_independent(harness):
    client, engine = harness
    _fill(client, 20, "fb-a", device="dev-a")
    assert _post(client, "fb-a-20", device="dev-a").status_code == 429
    assert _post(client, "fb-b-0", device="dev-b").status_code == 201


def test_a_verified_user_is_keyed_by_user_id_across_devices(harness):
    client, engine = harness
    _fill(client, 20, "fb-v", token=VERIFIED, device="phone")
    # Same verified user, another device: the same budget.
    assert _post(client, "fb-v-20", token=VERIFIED, device="tablet").status_code == 429
    # An UNVERIFIED session naming the same user_id is not that user: it is
    # keyed by its own token hash, so it neither spends nor inherits the budget.
    assert _post(client, "fb-u-0", token=UNVERIFIED, device="other").status_code == 201


def test_no_device_id_falls_back_to_the_rightmost_forwarded_hop(harness):
    client, engine = harness
    _fill(client, 20, "fb-ip", xff="1.2.3.4, 9.9.9.9")
    # A spoofed leading hop neither resets nor splits the count: the rightmost
    # hop (the address Render's proxy saw) is the key.
    assert _post(client, "fb-ip-20", xff="5.6.7.8, 9.9.9.9").status_code == 429
    assert _post(client, "fb-ip-21", xff="9.9.9.9").status_code == 429
    assert "ip:9.9.9.9" in server._feedback_rate
    assert not any(k in server._feedback_rate for k in ("ip:1.2.3.4", "ip:5.6.7.8"))
    # A different real hop is a different caller.
    assert _post(client, "fb-ip2-0", xff="1.2.3.4, 9.9.9.8").status_code == 201


# ── unverified sessions: keyed by token hash, not the shared IP ─────────────
# The mobile POST and the web form send no X-Device-Id, so without a session
# key every unverified note behind one carrier NAT shared the IP's budget.

NAT = "10.0.0.1, 100.64.0.9"        # one carrier-grade NAT egress (rightmost, as Render sees it)


def _sha(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def test_unverified_sessions_behind_one_ip_have_independent_budgets(harness):
    client, engine = harness
    _fill(client, 20, "fb-s1", token=UNVERIFIED, xff=NAT)
    assert _post(client, "fb-s1-20", token=UNVERIFIED, xff=NAT).status_code == 429
    # Another unverified session on the same IP: its own 20.
    _fill(client, 20, "fb-s2", token=UNVERIFIED_2, xff=NAT)
    assert _post(client, "fb-s2-20", token=UNVERIFIED_2, xff=NAT).status_code == 429
    # And a no-token post from that IP still has the IP's whole budget.
    assert _post(client, "fb-anon-0", xff=NAT).status_code == 201
    assert _count(engine) == 41


def test_one_unverified_session_is_429_at_note_21_whatever_its_device_or_ip(harness):
    client, engine = harness
    for i in range(20):
        r = _post(client, f"fb-one-{i}", token=UNVERIFIED, device=f"dev-{i}", xff=f"198.51.100.{i}")
        assert r.status_code == 201, (i, r.get_json())
    r = _post(client, "fb-one-20", token=UNVERIFIED, device="dev-new", xff="203.0.113.99")
    assert r.status_code == 429 and r.get_json() == {"error": "rate_limited"}
    assert _count(engine) == 20


def test_the_session_key_is_the_token_hash_never_the_raw_token(harness):
    client, engine = harness
    assert _post(client, "fb-k-0", token=UNVERIFIED, device="dev-k", xff=NAT).status_code == 201
    assert list(server._feedback_rate) == [f"session:{_sha(UNVERIFIED)}"]
    assert not any(UNVERIFIED in k for k in server._feedback_rate)


def test_no_token_falls_back_to_device_then_ip(harness):
    client, engine = harness
    # Device beats IP: the same device on another IP shares one budget.
    _fill(client, 20, "fb-nd", device="dev-nat", xff=NAT)
    assert _post(client, "fb-nd-20", device="dev-nat", xff="203.0.113.5").status_code == 429
    # No device: the IP, whose budget the device's notes never spent.
    _fill(client, 20, "fb-ni", xff=NAT)
    assert _post(client, "fb-ni-20", xff=NAT).status_code == 429
    # A token that resolves to no session counts as no token (it can't mint
    # a fresh budget per made-up token): it falls back to the device.
    _fill(client, 20, "fb-nu", token="tok-made-up-1", device="dev-u")
    assert _post(client, "fb-nu-20", token="tok-made-up-2", device="dev-u").status_code == 429
    assert set(server._feedback_rate) == {"device:dev-nat", "ip:100.64.0.9", "device:dev-u"}


def test_no_log_record_carries_the_raw_token_or_its_hash(harness, caplog):
    client, engine = harness
    caplog.set_level(logging.DEBUG)
    _fill(client, 20, "fb-log", token=UNVERIFIED, xff=NAT)
    assert _post(client, "fb-log-20", token=UNVERIFIED, xff=NAT).status_code == 429
    throttled = [r for r in caplog.records if "rate_limited" in r.getMessage()]
    assert throttled and throttled[-1].getMessage() == "feedback: rate_limited key=session"
    for rec in caplog.records:
        msg = rec.getMessage()
        assert UNVERIFIED not in msg, msg
        assert _sha(UNVERIFIED) not in msg, msg


def test_the_window_rolls(harness):
    client, engine = harness
    t0 = 1_800_000_000.0
    with patch.object(server.time, "time", return_value=t0):
        _fill(client, 20, "fb-w", device="dev-w")
        assert _post(client, "fb-w-20", device="dev-w").status_code == 429
    with patch.object(server.time, "time", return_value=t0 + server.FEEDBACK_RATE_WINDOW_S + 1):
        assert _post(client, "fb-w-21", device="dev-w").status_code == 201


def test_the_key_table_is_memory_bounded(harness):
    client, engine = harness
    with patch.object(server, "FEEDBACK_RATE_MAX_KEYS", 5):
        for i in range(12):
            assert _post(client, f"fb-m-{i}", device=f"dev-m-{i}").status_code == 201
        assert len(server._feedback_rate) <= 5


def test_zz_the_throttle_starts_empty_in_every_test():
    """conftest's autouse reset: every Flask test client posts from one IP,
    so without it the suite's feedback tests would share one 20-note budget.
    Runs last in this file, after tests that left keys behind."""
    assert server._feedback_rate == {}
