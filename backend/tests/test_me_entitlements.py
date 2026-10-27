"""GET /api/me/entitlements `founder` (#393 scope §2 item 2, S1).

`founder` is true when the user holds pro through a subscription that
started before the Founding GMs club's closes_at (server._PAYWALL_CLUB_
CLOSES_AT, 2027-01-01): the subscription's INITIAL_PURCHASE in the
subscription_events ledger (a first purchase or an intro-trial start), timed
by the payload's purchased_at_ms, else the row's occurred_at.

Covers:
  (1) founder from fixture ledger payloads: a trial start or a paid first
      purchase before the cut-off → true; at or after it → false; the
      occurred_at fallback on both sides
  (2) no pro → false: never purchased, a lapsed founder, a manual grant with
      no subscription behind it
  (3) the verified-only rule (platforms-eng's #395): an unverified session
      holding a founder's user_id gets founder false with every other field
      blank, and the same key set as the verified view
  (4) the route reads the one server constant

`enforcing` (5b) is platforms-eng's and is covered in
test_entitlements_billing_safety.py. In-memory SQLite, the ledger written
through the real webhook projector (entitlements.ingest_billing_event).
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.entitlements as entl
import backend.server as server
from backend.database import metadata, users_table

USER = "founder_user_1"
TOKEN = "founder-verified-token"
UNVERIFIED_TOKEN = "founder-unverified-token"

BEFORE_CUT = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
AT_CUT = datetime(2027, 1, 1, tzinfo=timezone.utc)
AFTER_CUT = datetime(2027, 1, 2, tzinfo=timezone.utc)


def _ms(dt: datetime) -> float:
    return dt.timestamp() * 1000


def _live() -> float:
    """An expiry 30 days past the real now, so the row is active whatever
    day the suite runs."""
    return _ms(datetime.now(timezone.utc) + timedelta(days=30))


@pytest.fixture()
def eng():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=USER, username="founderuser",
            created_at=datetime.now(timezone.utc).isoformat()))
    with patch.object(db_module, "engine", engine):
        yield engine


@pytest.fixture()
def client(eng):
    server.app.config["TESTING"] = True
    sessions = {
        TOKEN: {"user_id": USER, "verified": True, "last_active": time.time()},
        UNVERIFIED_TOKEN: {"user_id": USER, "last_active": time.time()},
    }
    with server._sessions_lock:
        server._sessions.update(sessions)
    try:
        yield server.app.test_client()
    finally:
        with server._sessions_lock:
            for t in sessions:
                server._sessions.pop(t, None)


def _ingest(eid, etype, *, purchased=None, occurred=None, period="TRIAL",
            expires=None, product="ftf_pro_annual"):
    ev = {"id": eid, "type": etype, "app_user_id": USER, "product_id": product,
          "environment": "PRODUCTION", "period_type": period,
          "expiration_at_ms": _live() if expires is None else expires}
    if purchased is not None:
        ev["purchased_at_ms"] = _ms(purchased)
    entl.ingest_billing_event("revenuecat", eid, etype, ev, user_id=USER,
                              product_id=product,
                              occurred_at=occurred.isoformat() if occurred else None)


def _get(client, token=TOKEN):
    r = client.get("/api/me/entitlements", headers={"X-Session-Token": token})
    assert r.status_code == 200
    return r.get_json()


# ── (1) founder from the ledger ────────────────────────────────────────────

@pytest.mark.parametrize("period", ["TRIAL", "NORMAL"])
def test_started_before_cut_is_founder(client, period):
    """An intro-trial start or a paid first purchase before closes_at."""
    _ingest("ip-1", "INITIAL_PURCHASE", purchased=BEFORE_CUT, period=period)
    body = _get(client)
    assert body["pro"] is True
    assert body["founder"] is True


@pytest.mark.parametrize("started", [AT_CUT, AFTER_CUT])
def test_started_at_or_after_cut_is_not_founder(client, started):
    _ingest("ip-1", "INITIAL_PURCHASE", purchased=started)
    body = _get(client)
    assert body["pro"] is True
    assert body["founder"] is False


def test_trial_converted_after_cut_keeps_founder(client):
    """The trial started before the cut-off; its first paid renewal after it
    is not a new start."""
    _ingest("ip-1", "INITIAL_PURCHASE", purchased=BEFORE_CUT, period="TRIAL")
    _ingest("rn-1", "RENEWAL", purchased=AFTER_CUT, period="NORMAL")
    assert _get(client)["founder"] is True


def test_renewal_alone_after_cut_is_not_founder(client):
    """Only an INITIAL_PURCHASE marks the start."""
    _ingest("rn-1", "RENEWAL", purchased=AFTER_CUT, period="NORMAL")
    body = _get(client)
    assert body["pro"] is True and body["founder"] is False


@pytest.mark.parametrize("occurred, founder", [(BEFORE_CUT, True), (AFTER_CUT, False)])
def test_occurred_at_fallback(client, occurred, founder):
    """No purchased_at_ms in the payload → the ledger row's occurred_at."""
    _ingest("ip-1", "INITIAL_PURCHASE", occurred=occurred)
    assert _get(client)["founder"] is founder


def test_sandbox_start_before_cut_is_founder(client):
    """A sandbox (TestFlight / App Review) start counts like a production one
    while its capped row is active."""
    ev = {"id": "sb-1", "type": "INITIAL_PURCHASE", "app_user_id": USER,
          "product_id": "ftf_pro_monthly", "environment": "SANDBOX",
          "period_type": "TRIAL", "expiration_at_ms": _live(),
          "purchased_at_ms": _ms(BEFORE_CUT)}
    entl.ingest_billing_event("revenuecat", "sb-1", "INITIAL_PURCHASE", ev,
                              user_id=USER, product_id="ftf_pro_monthly")
    assert _get(client)["founder"] is True


# ── (2) no pro → false ─────────────────────────────────────────────────────

def test_no_pro_is_not_founder(client):
    body = _get(client)
    assert body["pro"] is False and body["founder"] is False


def test_lapsed_founder_is_not_founder(client):
    past = _ms(datetime.now(timezone.utc) - timedelta(days=1))
    _ingest("ip-1", "INITIAL_PURCHASE", purchased=BEFORE_CUT, expires=past)
    _ingest("ex-1", "EXPIRATION", purchased=BEFORE_CUT, expires=past)
    body = _get(client)
    assert body["pro"] is False and body["founder"] is False


def test_manual_grant_is_not_founder(client):
    """Pro with no subscription behind it (an operator comp) has no start."""
    entl.grant(USER, "pro", source="manual_grant", granted_by="operator")
    body = _get(client)
    assert body["pro"] is True and body["founder"] is False


def test_other_users_start_does_not_count(client):
    """The ledger is read under the active row's user, never another's."""
    other = {"id": "ot-1", "type": "INITIAL_PURCHASE", "app_user_id": "someone_else",
             "product_id": "ftf_pro_annual", "environment": "PRODUCTION",
             "period_type": "TRIAL", "expiration_at_ms": _live(),
             "purchased_at_ms": _ms(BEFORE_CUT)}
    entl.ingest_billing_event("revenuecat", "ot-1", "INITIAL_PURCHASE", other,
                              user_id="someone_else", product_id="ftf_pro_annual")
    _ingest("ip-1", "INITIAL_PURCHASE", purchased=AFTER_CUT)
    assert _get(client)["founder"] is False


# ── (3) the verified-only rule ─────────────────────────────────────────────

def test_unverified_session_gets_founder_false(client):
    """A founder's user_id on an unverified session: founder is blanked with
    the rest, and the key set matches the verified view."""
    _ingest("ip-1", "INITIAL_PURCHASE", purchased=BEFORE_CUT)
    real = _get(client, TOKEN)
    blank = _get(client, UNVERIFIED_TOKEN)
    assert real["founder"] is True
    assert blank["founder"] is False
    assert set(blank) == set(real) == {
        "pro", "ad_free", "sources", "expires_at", "founder", "enforcing"}
    assert {k: v for k, v in blank.items() if k != "enforcing"} == entl.empty_entitlements()
    assert blank["enforcing"] == real["enforcing"]


def test_unverified_session_never_reads_the_ledger(client):
    """The blank comes from empty_entitlements, never from is_founder."""
    _ingest("ip-1", "INITIAL_PURCHASE", purchased=BEFORE_CUT)
    with patch.object(entl, "is_founder", side_effect=AssertionError("ledger read")):
        assert _get(client, UNVERIFIED_TOKEN)["founder"] is False


# ── (4) the one constant ───────────────────────────────────────────────────

def test_route_reads_the_server_constant(client, monkeypatch):
    _ingest("ip-1", "INITIAL_PURCHASE", purchased=BEFORE_CUT)
    assert _get(client)["founder"] is True
    monkeypatch.setattr(server, "_PAYWALL_CLUB_CLOSES_AT", "2026-12-01T00:00:00Z")
    assert _get(client)["founder"] is False
