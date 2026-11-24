"""League pass routes (server.py, thin wrappers over backend/league_pass.py).

Spec: docs/plans/monetization/league-pass/lld.md §6, §6.1, §6.2; hld.md §4.

Covers:
  (1) /api/league-pass/* 404 while monetize.league_pass is off; the admin
      routes stay live
  (2) verified sessions only: an unverified session is the route's own 403
  (3) POST /intent: the quote; 400 without league_id; 409 {error: reason}
      for not_member and already_covered
  (4) GET /api/league-pass: no purchase; unbound (a live league product, no
      pass); bound (covered_count excludes the buyer, can_repoint_at inside
      the cooldown, will_renew from the ledger's CANCELLATION)
  (5) POST /bind: 409 no_purchase; binds an unbound pass
  (6) POST /repoint: 409 cooldown with can_repoint_at; moves after it
  (7) PUT/POST /settings: show_buyer, 400 on a non-bool, 409 no_pass
  (8) GET /api/me/entitlements `league_passes`: present only with the flag
      on; [] for an unverified session; buyer_display only on opt-in
  (9) GET /api/paywall/config `league_pass`: only with the flag on AND
      caps=league_pass
  (10) admin comp / list / end: X-Cron-Secret, refusals, 404s

In-memory SQLite, no network.
"""

import json
import time
from unittest.mock import patch

import pytest
from sqlalchemy import insert

import backend.database as db_module
import backend.league_pass as lp
import backend.server as server
from backend.tests.support import league_pass_world as w

L, L2 = "lg-routes", "lg-routes-2"
BUYER, MATE = "u-rbuyer", "u-rmate"
TOKEN, MATE_TOKEN, UNVERIFIED = "lpr-buyer", "lpr-mate", "lpr-unverified"
SECRET = "lp-secret"

USER_ROUTES = [("POST", "/api/league-pass/intent"), ("GET", "/api/league-pass"),
               ("POST", "/api/league-pass/bind"), ("POST", "/api/league-pass/repoint"),
               ("PUT", "/api/league-pass/settings"), ("POST", "/api/league-pass/settings")]


@pytest.fixture()
def eng():
    engine = w.make_engine()
    with engine.begin() as conn:
        for lid in (L, L2):
            w.league(conn, lid, total_rosters=12)
        w.member(conn, L, BUYER)
        w.member(conn, L, MATE)
        w.member(conn, L2, BUYER)
    with patch.object(db_module, "engine", engine):
        yield engine


@pytest.fixture()
def flag(monkeypatch):
    state = {"on": True}
    real = server.is_enabled
    monkeypatch.setattr(server, "is_enabled",
                        lambda k: (state["on"] if k == lp.FLAG
                                   else True if k == "monetize.paywall" else real(k)))
    monkeypatch.setattr(lp, "is_enabled", lambda k: state["on"] and k == lp.FLAG)
    return state


@pytest.fixture()
def client(eng, flag, monkeypatch):
    monkeypatch.setattr(server, "_CRON_SECRET", SECRET)
    server.app.config["TESTING"] = True
    sessions = {TOKEN: {"user_id": BUYER, "verified": True, "last_active": time.time()},
                MATE_TOKEN: {"user_id": MATE, "verified": True, "last_active": time.time()},
                UNVERIFIED: {"user_id": BUYER, "last_active": time.time()}}
    with server._sessions_lock:
        server._sessions.update(sessions)
    try:
        yield server.app.test_client()
    finally:
        with server._sessions_lock:
            for t in sessions:
                server._sessions.pop(t, None)


def _req(c, method, path, token=TOKEN, body=None):
    return c.open(path, method=method, headers={"X-Session-Token": token}, json=body)


def _admin(c, method, path, body=None, secret=SECRET):
    return c.open(path, method=method, headers={"X-Cron-Secret": secret}, json=body)


# ── (1) flag off ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path", USER_ROUTES)
def test_user_routes_404_while_the_flag_is_off(client, flag, method, path):
    flag["on"] = False
    r = _req(client, method, path, body={"league_id": L, "show_buyer": True})
    assert (r.status_code, r.get_json()) == (404, {"error": "feature_disabled"})


def test_admin_routes_are_live_with_the_flag_off(client, flag):
    flag["on"] = False
    r = _admin(client, "POST", "/api/admin/league-pass/comp",
               {"league_id": L, "days": 7, "note": "beta"})
    assert r.status_code == 201


# ── (2) verified only ──────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path", USER_ROUTES)
def test_unverified_session_is_refused(client, method, path):
    r = _req(client, method, path, UNVERIFIED, {"league_id": L, "show_buyer": True})
    assert (r.status_code, r.get_json()) == (403, {"error": "verification_required"})


# ── (3) intent ─────────────────────────────────────────────────────────────

def test_intent_quotes_the_league(client):
    r = _req(client, "POST", "/api/league-pass/intent", body={"league_id": L})
    assert r.status_code == 200
    body = r.get_json()
    assert (body["product_id"], body["tier"], body["teams"]) == ("ftf_league_annual", 0, 12)
    assert set(body) == {"intent_id", "product_id", "tier", "teams", "expires_at"}


def test_intent_refusals(client, eng):
    assert _req(client, "POST", "/api/league-pass/intent", body={}).status_code == 400
    r = _req(client, "POST", "/api/league-pass/intent", MATE_TOKEN, {"league_id": L2})
    assert (r.status_code, r.get_json()) == (409, {"error": "not_member"})
    with eng.begin() as conn:
        w.pass_row(conn, L, origin="comp", buyer=None, comp_days=10)
    r = _req(client, "POST", "/api/league-pass/intent", body={"league_id": L})
    assert (r.status_code, r.get_json()) == (409, {"error": "already_covered"})


# ── (4) GET /api/league-pass ───────────────────────────────────────────────

def test_buyer_view_without_a_purchase(client):
    r = _req(client, "GET", "/api/league-pass")
    assert r.get_json() == {"pass": None, "unbound": False}


def test_buyer_view_unbound(client, eng):
    with eng.begin() as conn:
        w.ent_row(conn, BUYER)
    assert _req(client, "GET", "/api/league-pass").get_json() == {"pass": None, "unbound": True}


def test_buyer_view_bound(client, eng):
    with eng.begin() as conn:
        w.ent_row(conn, BUYER, granted_by="evt-buy")
        w.pass_row(conn, L, buyer=BUYER, bound_days=-1)
    view = _req(client, "GET", "/api/league-pass").get_json()
    p = view["pass"]
    assert view["unbound"] is False
    assert (p["league_id"], p["platform"], p["tier"], p["covered_count"]) == (L, "sleeper", 0, 1)
    assert p["will_renew"] is True and p["show_buyer"] is False
    assert p["can_repoint_at"] > w.iso(28)
    with eng.begin() as conn:
        conn.execute(insert(db_module.subscription_events_table).values(
            source="revenuecat", event_type="CANCELLATION", user_id=BUYER,
            product_id="ftf_league_annual", event_id="evt-cancel",
            payload=json.dumps({}), occurred_at=w.iso()))
    assert _req(client, "GET", "/api/league-pass").get_json()["pass"]["will_renew"] is False


# ── (5) bind ───────────────────────────────────────────────────────────────

def test_bind(client, eng):
    r = _req(client, "POST", "/api/league-pass/bind", body={"league_id": L})
    assert (r.status_code, r.get_json()) == (409, {"error": "no_purchase"})
    with eng.begin() as conn:
        w.ent_row(conn, BUYER)
    r = _req(client, "POST", "/api/league-pass/bind", body={"league_id": L})
    assert r.status_code == 200
    assert r.get_json()["pass"]["league_id"] == L


# ── (6) repoint ────────────────────────────────────────────────────────────

def test_repoint_cooldown_then_move(client, eng):
    with eng.begin() as conn:
        w.ent_row(conn, BUYER)
        pass_id = w.pass_row(conn, L, buyer=BUYER, bound_days=-1)
    r = _req(client, "POST", "/api/league-pass/repoint", body={"league_id": L2})
    assert r.status_code == 409
    assert r.get_json()["error"] == "cooldown" and r.get_json()["can_repoint_at"] > w.iso(28)
    with eng.begin() as conn:
        conn.execute(db_module.league_passes_table.update()
                     .where(db_module.league_passes_table.c.id == pass_id)
                     .values(bound_at=w.iso(-40)))
    r = _req(client, "POST", "/api/league-pass/repoint", body={"league_id": L2})
    assert r.status_code == 200 and r.get_json()["pass"]["league_id"] == L2


# ── (7) settings ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("method", ["PUT", "POST"])
def test_settings(client, eng, method):
    path = "/api/league-pass/settings"
    assert _req(client, method, path, body={"show_buyer": "yes"}).status_code == 400
    r = _req(client, method, path, body={"show_buyer": True})
    assert (r.status_code, r.get_json()) == (409, {"error": "no_pass"})
    with eng.begin() as conn:
        w.ent_row(conn, BUYER)
        w.pass_row(conn, L, buyer=BUYER)
    r = _req(client, method, path, body={"show_buyer": True})
    assert r.status_code == 200 and r.get_json()["pass"]["show_buyer"] is True
    assert w.passes(eng)[0]["show_buyer"] == 1


# ── (8) /api/me/entitlements ───────────────────────────────────────────────

def test_me_entitlements_league_passes(client, eng, flag):
    with eng.begin() as conn:
        conn.execute(db_module.users_table.update()
                     .where(db_module.users_table.c.sleeper_user_id == BUYER)
                     .values(display_name="Buyer Name"))
        w.ent_row(conn, BUYER, expires_days=100)
        pass_id = w.pass_row(conn, L, buyer=BUYER)
    entry = _req(client, "GET", "/api/me/entitlements", MATE_TOKEN).get_json()["league_passes"]
    assert [(e["league_id"], e["platform"], e["role"], e["buyer_display"]) for e in entry] == \
        [(L, "sleeper", "member", None)]
    assert set(entry[0]) == {"league_id", "platform", "role", "covered_until", "buyer_display"}
    with eng.begin() as conn:
        conn.execute(db_module.league_passes_table.update()
                     .where(db_module.league_passes_table.c.id == pass_id).values(show_buyer=1))
    entry = _req(client, "GET", "/api/me/entitlements", MATE_TOKEN).get_json()["league_passes"]
    assert entry[0]["buyer_display"] == "Buyer Name"
    assert _req(client, "GET", "/api/me/entitlements", UNVERIFIED).get_json()["league_passes"] == []
    flag["on"] = False
    assert "league_passes" not in _req(client, "GET", "/api/me/entitlements", MATE_TOKEN).get_json()


# ── (9) /api/paywall/config ────────────────────────────────────────────────

def test_paywall_config_league_pass_block(client, flag):
    block = _req(client, "GET", "/api/paywall/config?caps=league_pass").get_json()["league_pass"]
    assert block["offering"] == "league" and block["renews_at_price"] == "$99.99"
    assert [(p["product_id"], p["tier"], p.get("promo_offer_id")) for p in block["products"]] == [
        ("ftf_league_annual", 0, None), ("ftf_league_annual_t1", 1, "league_t1_y1"),
        ("ftf_league_annual_t2", 2, "league_t2_y1")]
    assert "league_pass" in _req(client, "GET",
                                 "/api/paywall/config?caps=x,league_pass").get_json()
    no_caps = _req(client, "GET", "/api/paywall/config").get_json()
    assert "league_pass" not in no_caps
    flag["on"] = False
    off = _req(client, "GET", "/api/paywall/config?caps=league_pass")
    assert "league_pass" not in off.get_json()
    assert off.data == _req(client, "GET", "/api/paywall/config").data


# ── (10) admin ─────────────────────────────────────────────────────────────

def test_admin_auth(client):
    for method, path in [("POST", "/api/admin/league-pass/comp"),
                         ("GET", "/api/admin/league-pass?league_id=x"),
                         ("DELETE", "/api/admin/league-pass/1")]:
        assert _admin(client, method, path, {}, secret="wrong").status_code == 401


def test_admin_comp_list_end(client, eng):
    r = _admin(client, "POST", "/api/admin/league-pass/comp",
               {"league_id": L, "days": 30, "note": "phase 1"})
    assert r.status_code == 201
    row = r.get_json()
    assert (row["origin"], row["league_id"], row["note"]) == ("comp", L, "phase 1")
    r = _admin(client, "POST", "/api/admin/league-pass/comp", {"league_id": L, "days": 30})
    assert (r.status_code, r.get_json()) == (409, {"error": "already_covered"})
    r = _admin(client, "POST", "/api/admin/league-pass/comp", {"league_id": L2, "days": "30"})
    assert (r.status_code, r.get_json()) == (409, {"error": "bad_days"})
    r = _admin(client, "POST", "/api/admin/league-pass/comp", {"league_id": "nope", "days": 3})
    assert (r.status_code, r.get_json()) == (409, {"error": "unknown_league"})

    listed = _admin(client, "GET", f"/api/admin/league-pass?league_id={L}").get_json()["passes"]
    assert [(p["id"], p["status"]) for p in listed] == [(row["id"], "active")]
    assert listed[0]["live_until"] == row["comp_expires_at"]
    assert _admin(client, "GET", "/api/admin/league-pass").status_code == 400
    assert _admin(client, "GET", "/api/admin/league-pass?user=nobody").status_code == 404

    assert _admin(client, "DELETE", f"/api/admin/league-pass/{row['id']}").get_json() == \
        {"ended": row["id"]}
    assert _admin(client, "DELETE", f"/api/admin/league-pass/{row['id']}").status_code == 404
    listed = _admin(client, "GET", f"/api/admin/league-pass?league_id={L}").get_json()["passes"]
    assert (listed[0]["status"], listed[0]["release_reason"], listed[0]["live_until"]) == \
        ("ended", "admin", None)


def test_admin_list_by_user(client, eng):
    with eng.begin() as conn:
        w.ent_row(conn, BUYER)
        pass_id = w.pass_row(conn, L, buyer=BUYER)
    body = _admin(client, "GET", f"/api/admin/league-pass?user={BUYER}").get_json()
    assert body["user_id"] == BUYER and [p["id"] for p in body["passes"]] == [pass_id]
