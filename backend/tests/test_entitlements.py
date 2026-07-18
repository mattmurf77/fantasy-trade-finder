"""Monetization platform foundation tests
(docs/plans/monetization/00-platform-foundation.md).

Covers:
  (a) flag registration — every monetize.*/growth.*/ranks.*/marketplace.*
      key exists and defaults False (ships dark)
  (b) schema — new tables create on a fresh engine; rank_set uniqueness
  (c) entitlement resolution — grant → pro; expiry; revoked; account bridge
      (grant on account unlocks the bound sleeper id and acct_* key)
  (d) check_pro observe/enforce semantics (§2.4)
  (e) billing ingestion — idempotency, projector activate/renew/expire,
      manual grants untouched by billing deactivation
  (f) routes — manual-grant admin surface + /api/me/entitlements + webhooks

In-memory SQLite via the same patched-engine harness as
test_events_api.py; flags forced via patched is_enabled.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.entitlements as entl
import backend.server as server
from backend.database import (
    accounts_table, entitlements_table, metadata, rank_sets_table,
    rank_set_entries_table, subscription_events_table, users_table,
)
from backend.feature_flags import DEFAULT_FLAGS

USER = "ent_user_1"
TOKEN = "ent-test-token"


def _iso(days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.fixture()
def eng():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=USER, username="entuser", created_at=_iso(0)))
    with patch.object(db_module, "engine", engine):
        yield engine


@pytest.fixture()
def client(eng):
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    sess = {"user_id": USER, "last_active": 0.0}
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


# ── (a) flags ship dark ────────────────────────────────────────────────────

MONETIZATION_FLAGS = [
    "monetize.entitlements", "monetize.paywall", "monetize.pro",
    "monetize.season_pass", "monetize.founder", "monetize.affiliate",
    "monetize.ads_web", "monetize.ads_mobile",
    "growth.referral", "growth.group_unlock",
    "ranks.accuracy_scoring", "ranks.rank_sets", "ranks.set_types_extended",
    "marketplace.publisher_sets", "marketplace.contributor_sales",
    "marketplace.cash_payouts",
]


def test_flags_registered_and_dark():
    for key in MONETIZATION_FLAGS:
        assert key in DEFAULT_FLAGS, f"{key} missing from FLAG_KEYS"
        assert DEFAULT_FLAGS[key] is False


def test_features_json_keys_known():
    """Every monetization key in config/features.json must be registered —
    the loader warns-and-ignores unknown keys, which would silently strand
    a flag flip."""
    import pathlib
    cfg = json.loads(
        (pathlib.Path(__file__).parents[2] / "config" / "features.json").read_text())
    for key in cfg:
        if key.startswith("_comment"):
            continue
        assert key in DEFAULT_FLAGS, f"features.json key {key!r} unregistered"


# ── (b) schema ─────────────────────────────────────────────────────────────

def test_new_tables_create_and_roundtrip(eng):
    with eng.begin() as conn:
        conn.execute(insert(rank_sets_table).values(
            owner_user_id=USER, set_type="dynasty", scoring_format="1qb_ppr",
            title="My Board", created_at=_iso(0), updated_at=_iso(0)))
        set_id = conn.execute(select(rank_sets_table.c.id)).scalar()
        conn.execute(insert(rank_set_entries_table).values(
            rank_set_id=set_id, version=1, player_id="4046", rank=1))
    # duplicate (set, version, player) must violate uq_rank_set_entry
    with pytest.raises(Exception):
        with eng.begin() as conn:
            conn.execute(insert(rank_set_entries_table).values(
                rank_set_id=set_id, version=1, player_id="4046", rank=2))


# ── (c) resolution ─────────────────────────────────────────────────────────

def test_grant_and_resolution(eng):
    assert entl.get_entitlements(USER)["pro"] is False
    entl.grant(USER, "pro", source="manual_grant", duration_days=30,
               granted_by="operator")
    out = entl.get_entitlements(USER)
    assert out["pro"] is True and out["ad_free"] is True
    assert out["sources"] == ["manual_grant"]
    assert out["expires_at"] is not None


def test_expired_and_revoked_rows_do_not_count(eng):
    entl.grant(USER, "pro", source="manual_grant", expires_at=_iso(-1))
    assert entl.get_entitlements(USER)["pro"] is False
    row = entl.grant(USER, "pro", source="manual_grant")  # perpetual
    assert entl.get_entitlements(USER)["pro"] is True
    entl.revoke(row["id"])
    assert entl.get_entitlements(USER)["pro"] is False


def test_account_bridge(eng):
    with eng.begin() as conn:
        conn.execute(insert(accounts_table).values(
            account_id="abc123", sleeper_user_id=USER, created_at=_iso(0)))
    entl.grant(f"acct_abc123", "pro", source="manual_grant")
    # grant keyed to the acct_* working key resolves for the bound sleeper id
    assert entl.get_entitlements(USER)["pro"] is True
    assert entl.get_entitlements("acct_abc123")["pro"] is True


def test_resolve_user_forms(eng):
    assert entl.resolve_user(USER) == (USER, None)
    assert entl.resolve_user("entuser") == (USER, None)
    assert entl.resolve_user("nope-xyz") == (None, None)
    with eng.begin() as conn:
        conn.execute(insert(accounts_table).values(
            account_id="abc123", sleeper_user_id=USER, created_at=_iso(0)))
    assert entl.resolve_user("entuser") == (USER, "abc123")
    assert entl.resolve_user("acct_abc123") == (USER, "abc123")


# ── (d) observe / enforce ──────────────────────────────────────────────────

def _flags(*on):
    return lambda k: k in on


def test_check_pro_flag_off_allows(eng):
    with patch.object(entl, "is_enabled", _flags()):
        assert entl.check_pro(USER, "/api/x") is True


def test_check_pro_observe_logs_never_blocks(eng):
    class Cap:
        lines = []
        def info(self, msg, *a):
            self.lines.append(msg % a)
    cap = Cap()
    with patch.object(entl, "is_enabled", _flags("monetize.entitlements")):
        assert entl.check_pro(USER, "/api/x", logger=cap) is True
    assert any("ENTITLE-OBSERVE" in l and "would_block=True" in l for l in cap.lines)


def test_check_pro_enforces_with_both_flags(eng):
    both = _flags("monetize.entitlements", "monetize.paywall")
    with patch.object(entl, "is_enabled", both):
        assert entl.check_pro(USER, "/api/x") is False
        entl.grant(USER, "pro", source="manual_grant")
        assert entl.check_pro(USER, "/api/x") is True


# ── (e) billing ingestion + projector ──────────────────────────────────────

def _rc_event(eid, etype, *, expires_days=365.0, product="ftf_pro_annual"):
    exp_ms = (datetime.now(timezone.utc)
              + timedelta(days=expires_days)).timestamp() * 1000
    return {"id": eid, "type": etype, "app_user_id": USER,
            "product_id": product, "expiration_at_ms": exp_ms}


def _ingest(ev):
    return entl.ingest_billing_event(
        "revenuecat", ev["id"], ev["type"], ev,
        user_id=ev["app_user_id"], product_id=ev["product_id"])


def test_purchase_renewal_expiration_flow(eng):
    r = _ingest(_rc_event("e1", "INITIAL_PURCHASE"))
    assert r == {"stored": True, "projected": True, "duplicate": False}
    assert entl.get_entitlements(USER)["pro"] is True

    # renewal updates the SAME row (no duplicate entitlements)
    _ingest(_rc_event("e2", "RENEWAL", expires_days=730))
    rows = entl.list_for_user(USER)
    assert len(rows) == 1 and rows[0]["status"] == "active"

    _ingest(_rc_event("e3", "EXPIRATION"))
    assert entl.get_entitlements(USER)["pro"] is False
    assert entl.list_for_user(USER)[0]["status"] == "expired"


def test_ingest_idempotent_on_event_id(eng):
    _ingest(_rc_event("dup1", "INITIAL_PURCHASE"))
    r = _ingest(_rc_event("dup1", "INITIAL_PURCHASE"))
    assert r["duplicate"] is True
    with eng.begin() as conn:
        n = len(conn.execute(select(subscription_events_table)).fetchall())
    assert n == 1
    assert len(entl.list_for_user(USER)) == 1


def test_billing_never_touches_manual_grants(eng):
    entl.grant(USER, "pro", source="manual_grant", note="operator comp")
    _ingest(_rc_event("e10", "INITIAL_PURCHASE"))
    _ingest(_rc_event("e11", "REFUND"))
    rows = {r["source"]: r["status"] for r in entl.list_for_user(USER)}
    assert rows["manual_grant"] == "active"       # untouched
    assert rows["apple_iap"] == "refunded"
    assert entl.get_entitlements(USER)["pro"] is True  # comp survives refund


def test_unhandled_event_stored_with_note(eng):
    r = _ingest(_rc_event("e20", "SOME_FUTURE_TYPE"))
    assert r["projected"] is False
    with eng.begin() as conn:
        row = conn.execute(select(subscription_events_table)).fetchone()
    assert row.process_error and "unhandled" in row.process_error


def test_founder_product_maps_perpetual_source(eng):
    ev = _rc_event("e30", "NON_RENEWING_PURCHASE", product="ftf_founder")
    ev["expiration_at_ms"] = None
    _ingest(ev)
    rows = entl.list_for_user(USER)
    assert rows[0]["source"] == "founder_iap" and rows[0]["expires_at"] is None


# ── (f) routes ─────────────────────────────────────────────────────────────
# Local dev (no CRON_SECRET) → admin routes open; that's the tested path,
# matching the /api/feedback/admin convention.

def test_admin_grant_revoke_list_roundtrip(client):
    r = client.post("/api/admin/entitlements/grant",
                    json={"user": "entuser", "duration_days": 30,
                          "note": "beta thanks"})
    assert r.status_code == 201
    row = r.get_json()
    assert row["user_id"] == USER and row["source"] == "manual_grant"

    r = client.get(f"/api/admin/entitlements?user={USER}")
    assert r.status_code == 200
    assert len(r.get_json()["entitlements"]) == 1

    r = client.delete(f"/api/admin/entitlements/{row['id']}")
    assert r.status_code == 200
    r = client.get(f"/api/admin/entitlements?user={USER}")
    assert r.get_json()["entitlements"][0]["status"] == "revoked"


def test_admin_grant_unknown_user_404(client):
    r = client.post("/api/admin/entitlements/grant", json={"user": "ghost99"})
    assert r.status_code == 404


def test_admin_bulk_grant_partial(client):
    r = client.post("/api/admin/entitlements/bulk-grant",
                    json={"users": ["entuser", "ghost99"], "duration_days": 90})
    assert r.status_code == 201
    body = r.get_json()
    assert len(body["granted"]) == 1 and len(body["failed"]) == 1


def test_me_entitlements_route(client):
    r = client.get("/api/me/entitlements", headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200
    body = r.get_json()
    assert body["pro"] is False and body["enforcing"] is False
    client.post("/api/admin/entitlements/grant", json={"user": USER,
                                                       "perpetual": True})
    r = client.get("/api/me/entitlements", headers={"X-Session-Token": TOKEN})
    assert r.get_json()["pro"] is True


def test_revenuecat_webhook_happy_and_malformed(client):
    ev = _rc_event("wh1", "INITIAL_PURCHASE")
    r = client.post("/api/billing/revenuecat/webhook", json={"event": ev})
    assert r.status_code == 200 and r.get_json()["projected"] is True
    # replay → duplicate no-op
    r = client.post("/api/billing/revenuecat/webhook", json={"event": ev})
    assert r.get_json()["duplicate"] is True
    r = client.post("/api/billing/revenuecat/webhook", json={"event": {}})
    assert r.status_code == 400


def test_stripe_webhook_metadata_path(client):
    body = {"id": "evt_1", "type": "checkout.session.completed",
            "data": {"object": {"metadata": {
                "user_id": USER, "product_id": "ftf_pro_annual"}}}}
    r = client.post("/api/billing/stripe/webhook", json=body)
    assert r.status_code == 200 and r.get_json()["projected"] is True
    assert entl.get_entitlements(USER)["pro"] is True
    rows = entl.list_for_user(USER)
    assert rows[0]["source"] == "stripe"
