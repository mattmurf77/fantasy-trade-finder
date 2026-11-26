"""The global server paywall gate (backend/paywall_gate.py + the one
before_request hook in server.py). Lands dark.

Spec: Product scope #393 §2 item 1 and §3, with head-eng's rulings:
enforce = entitlements.is_enforcing(); web gated only with model_config
paywall_web_enforce_enabled == 1; preview = 0 pages; pro counts only on a
verified session (`verify_required`).

Covers:
  (1) the matrix (deck preview off; it has its own file): route class (gated deck, gated send, free, never_gate) ×
      enforce state (dark, flags on + knob 0, knob on + one flag, enforcing)
      × client (mobile, web with the web knob 0, web with it 1) × user state
      (never entitled, trial expired, lapsed, active paid, active trial,
      manual grant). 200, or the exact 402 body
  (2) reason derivation edge cases: an expired comp, an App Store row with no
      ledger, a sandbox trial found through granted_by, a tip never reading
      as paid
  (3) verified sessions: paying + verified passes; the same user_id
      unverified → verify_required, or the route's own 403 where it wears the
      verified gate (R28.14; every gated rule in
      test_paywall_gate_unverified.py); the demo synthetic session passes;
      /api/me/entitlements pro tracks verification
  (4) never a 402: unauthenticated, a bad token, the extension endpoints,
      a web request with the web knob 0 (or missing) while mobile enforces
  (5) hot path: dark → no model_config or entitlement read; not enforcing →
      no entitlement read
  (6) the web knob at 1 (owner 2026-11-25): every gated rule walls a
      non-app request (no header, a browser, X-Device web, the extension, an
      unknown device) exactly like the app, a subscriber passes, a signed-out
      browser never gets a 402; every non-gated rule passes with no
      entitlement read; the website's pages, share/OG/join pages, the
      RevenueCat webhook, cron and admin never answer 402

Gated views are stubbed to a plain 200 so "the hook let it through" reads as
200 without running the trade engine. In-memory SQLite, no network.
"""

import json
import re
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.entitlements as entl
import backend.paywall_gate as pg
import backend.server as server
from backend.database import (
    entitlements_table, metadata, model_config_table, subscription_events_table,
    users_table,
)

USER = "gate_user_1"
TOKEN = "gate-verified-token"
UNVERIFIED_TOKEN = "gate-unverified-token"
DEMO_USER = "demo_user_1a2b3c4d"
DEMO_TOKEN = "gate-demo-token"
ENFORCE_KNOB = "paywall_enforce_enabled"
WEB_KNOB = "paywall_web_enforce_enabled"
# The deck preview has its own file (test_paywall_preview.py). Here it is off,
# so a never-entitled user's deck request is the knob-0 case. Nothing was ever
# served (no paywall_previews row), so it answers 402 never_trialed (K0).
NO_PREVIEW = {"paywall_preview_pages": 0.0}
BOTH_FLAGS = ("monetize.entitlements", "monetize.paywall")

MOBILE = {"X-Device": "iphone", "X-OS-Version": "18.1", "X-App-Version": "1.13.2"}
WEB = {}

# (method, path, endpoint) per route class.
ROUTE_CLASSES = {
    "deck": ("POST", "/api/trades/generate", "generate_trades"),
    "send": ("POST", "/api/trades/propose", "propose_trade_to_sleeper"),
    "free": ("POST", "/api/trade/evaluate", "trade_evaluate_route"),
    "never_gate": ("POST", "/api/cron/daily-tick", "cron_daily_tick"),
}


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


def _ms(delta: timedelta) -> float:
    return (datetime.now(timezone.utc) + delta).timestamp() * 1000


@pytest.fixture()
def eng():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=USER, username="gateuser", created_at=_iso(timedelta(0))))
    with patch.object(db_module, "engine", engine):
        yield engine


@pytest.fixture()
def client(eng):
    server.app.config["TESTING"] = True
    sessions = {
        TOKEN: {"user_id": USER, "verified": True, "last_active": time.time()},
        UNVERIFIED_TOKEN: {"user_id": USER, "last_active": time.time()},
        DEMO_TOKEN: {"user_id": DEMO_USER, "is_demo": True,
                     "last_active": time.time()},
    }
    with server._sessions_lock:
        server._sessions.update(sessions)
    try:
        yield server.app.test_client()
    finally:
        with server._sessions_lock:
            for t in sessions:
                server._sessions.pop(t, None)


@pytest.fixture()
def stubbed(monkeypatch):
    """Every view the tests hit returns a plain 200, so a request the hook
    lets through is visibly 200."""
    def ok(**_kw):
        return "ok", 200
    for ep in ("generate_trades", "propose_trade_to_sleeper", "trade_evaluate_route",
               "cron_daily_tick", "trade_job_status", "overhaul_active_route",
               "win_now_job_route", "disposition_trade_match", "extension_auth",
               "extension_rankings", "delete_account_route", "get_trade_matches"):
        monkeypatch.setitem(server.app.view_functions, ep, ok)


def _set_config(eng, **values):
    """Write model_config rows straight to the table (None deletes), so a
    changed answer proves the knobs are read live."""
    with eng.begin() as conn:
        for key, value in values.items():
            conn.execute(model_config_table.delete().where(model_config_table.c.key == key))
            if value is not None:
                conn.execute(insert(model_config_table).values(key=key, value=value))


def _flags(*on):
    return lambda k: k in on


# ── user states, built through the real webhook projector ─────────────────

def _rc(eid, etype, period, expires, *, user=USER, product="ftf_pro_monthly",
        env="PRODUCTION"):
    return {"id": eid, "type": etype, "app_user_id": user, "product_id": product,
            "environment": env, "period_type": period,
            "expiration_at_ms": _ms(expires)}


def _ingest(ev):
    entl.ingest_billing_event("revenuecat", ev["id"], ev["type"], ev,
                              user_id=ev["app_user_id"], product_id=ev["product_id"])


PAST, FUTURE = timedelta(days=-1), timedelta(days=30)


def _make_user(state, user=USER):
    if state == "never":
        return
    if state == "active_paid":
        _ingest(_rc(f"{user}-a", "INITIAL_PURCHASE", "NORMAL", FUTURE, user=user))
    elif state == "active_trial":
        _ingest(_rc(f"{user}-a", "INITIAL_PURCHASE", "TRIAL", FUTURE, user=user))
    elif state == "trial_expired":
        _ingest(_rc(f"{user}-a", "INITIAL_PURCHASE", "TRIAL", PAST, user=user))
        _ingest(_rc(f"{user}-b", "EXPIRATION", "TRIAL", PAST, user=user))
    elif state == "lapsed":
        _ingest(_rc(f"{user}-a", "INITIAL_PURCHASE", "TRIAL", PAST, user=user))
        _ingest(_rc(f"{user}-b", "RENEWAL", "NORMAL", PAST, user=user))
        _ingest(_rc(f"{user}-c", "EXPIRATION", "NORMAL", PAST, user=user))
    elif state == "manual_grant":
        entl.grant(user, "pro", source="manual_grant", granted_by="operator")
    else:
        raise AssertionError(state)


ACTIVE = {"active_paid", "active_trial", "manual_grant"}

ENFORCE_STATES = {
    # name: (flags on, enforce knob)
    "dark": ((), 0.0),
    "flags_knob0": (BOTH_FLAGS, 0.0),
    "knob_one_flag": (("monetize.entitlements",), 1.0),
    "enforcing": (BOTH_FLAGS, 1.0),
}

CLIENTS = {
    # name: (headers, web knob)
    "mobile": (MOBILE, 0.0),
    "web_knob0": (WEB, 0.0),
    "web_knob1": (WEB, 1.0),
}


def _expected(route_cls, enforce, client_name, user_state):
    if route_cls not in ("deck", "send") or enforce != "enforcing":
        return 200, None
    if client_name == "web_knob0" or user_state in ACTIVE:
        return 200, None
    gate = {"never": "never_trialed",
            "trial_expired": "trial_expired", "lapsed": "lapsed"}[user_state]
    return 402, {"error": "pro_required", "gate": gate}


# ── (1) the matrix ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("user_state", ["never", "trial_expired", "lapsed",
                                        "active_paid", "active_trial", "manual_grant"])
@pytest.mark.parametrize("client_name", list(CLIENTS))
@pytest.mark.parametrize("enforce", list(ENFORCE_STATES))
@pytest.mark.parametrize("route_cls", list(ROUTE_CLASSES))
def test_gate_matrix(eng, client, stubbed, route_cls, enforce, client_name, user_state):
    flags, knob = ENFORCE_STATES[enforce]
    headers, web_knob = CLIENTS[client_name]
    _set_config(eng, **{ENFORCE_KNOB: knob, WEB_KNOB: web_knob, **NO_PREVIEW})
    _make_user(user_state)
    method, path, _ep = ROUTE_CLASSES[route_cls]
    with patch.object(entl, "is_enabled", _flags(*flags)):
        r = client.open(path, method=method,
                        headers={"X-Session-Token": TOKEN, **headers})
    status, body = _expected(route_cls, enforce, client_name, user_state)
    assert r.status_code == status
    if body is not None:
        assert r.get_json() == body


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/trades/status"),
    ("GET", "/api/overhauls"),
    ("GET", "/api/win-now/jobs/j1"),
    ("POST", "/api/trades/matches/7/disposition"),
])
def test_other_gated_routes_block_never_entitled(eng, client, stubbed, method, path):
    _set_config(eng, **{ENFORCE_KNOB: 1.0, **NO_PREVIEW})
    with patch.object(entl, "is_enabled", _flags(*BOTH_FLAGS)):
        r = client.open(path, method=method, headers={"X-Session-Token": TOKEN, **MOBILE})
    assert r.status_code == 402
    assert r.get_json() == {"error": "pro_required", "gate": "never_trialed"}


def test_knob_kill_is_live(eng, client, stubbed):
    """Knob 1 → 402; set it 0 → the next request passes, no reload."""
    with patch.object(entl, "is_enabled", _flags(*BOTH_FLAGS)):
        _set_config(eng, **{ENFORCE_KNOB: 1.0, **NO_PREVIEW})
        hdr = {"X-Session-Token": TOKEN, **MOBILE}
        assert client.post("/api/trades/generate", headers=hdr).status_code == 402
        _set_config(eng, **{ENFORCE_KNOB: 0.0})
        assert client.post("/api/trades/generate", headers=hdr).status_code == 200


# ── (2) reason derivation ──────────────────────────────────────────────────

def test_never_entitled_reason_is_preview_used_only_once_spent(eng):
    """K0: a never-entitled user reads never_trialed on a deck route until a
    preview row exists, then preview_used; never_trialed off the deck."""
    assert pg.gate_reason(USER, deck=True) == "never_trialed"
    pg.record_preview(USER, "job-k0", 1, ["t-1"])
    assert pg.gate_reason(USER, deck=True) == "preview_used"
    assert pg.gate_reason(USER, deck=False) == "never_trialed"


def test_expired_comp_reads_lapsed(eng):
    entl.grant(USER, "pro", source="manual_grant", expires_at=_iso(PAST))
    assert pg.gate_reason(USER, deck=True) == "lapsed"


def test_store_row_without_ledger_reads_lapsed(eng):
    """No period_type to read → can't prove a trial → lapsed."""
    now = _iso(timedelta(0))
    with eng.begin() as conn:
        conn.execute(insert(entitlements_table).values(
            user_id=USER, entitlement="pro", source="apple_iap",
            product_id="ftf_pro_monthly", status="expired", starts_at=now,
            expires_at=_iso(PAST), granted_by="evt-missing",
            created_at=now, updated_at=now))
    assert pg.gate_reason(USER, deck=False) == "lapsed"


def test_sandbox_trial_found_through_granted_by(eng):
    """The ledger row sits under another id (pre-alias); the entitlement row's
    granted_by (sandbox-prefixed) still points at it."""
    now = _iso(timedelta(0))
    with eng.begin() as conn:
        conn.execute(insert(subscription_events_table).values(
            source="revenuecat", event_type="INITIAL_PURCHASE",
            user_id="$RCAnonymousID:abc", product_id="ftf_pro_annual",
            event_id="sbx1", payload=json.dumps({"period_type": "TRIAL"}),
            occurred_at=now))
        conn.execute(insert(entitlements_table).values(
            user_id=USER, entitlement="pro", source="apple_iap",
            product_id="ftf_pro_annual", status="active", starts_at=now,
            expires_at=_iso(PAST), granted_by="sandbox:sbx1",
            created_at=now, updated_at=now))
    assert pg.gate_reason(USER, deck=True) == "trial_expired"


def test_tip_never_reads_as_paid(eng):
    _make_user("trial_expired")
    _ingest(_rc("tip1", "NON_RENEWING_PURCHASE", "NORMAL", FUTURE,
                product="ftf_tip_499"))
    assert pg.gate_reason(USER, deck=True) == "trial_expired"


def test_sandbox_trial_expired_end_to_end(eng):
    _ingest(_rc("s-a", "INITIAL_PURCHASE", "TRIAL", PAST, env="SANDBOX"))
    assert entl.get_entitlements(USER)["pro"] is False
    assert pg.gate_reason(USER, deck=False) == "trial_expired"


def test_decide_pure_matches_hook(eng):
    _set_config(eng, **{ENFORCE_KNOB: 1.0, **NO_PREVIEW})
    with patch.object(entl, "is_enabled", _flags(*BOTH_FLAGS)):
        assert pg.decide("/api/trades/generate", "POST", USER, True, True) == (
            402, {"error": "pro_required", "gate": "never_trialed"})
        assert pg.decide("/api/trade/evaluate", "POST", USER, True, True) is None
        assert pg.decide("/api/trades/generate", "POST", None, True, True) is None
        assert pg.decide("/api/trades/generate", "HEAD", USER, True, True) is None  # HEAD only maps for GET rules
        assert pg.decide("/api/trades/status", "HEAD", USER, True, True)[0] == 402


# ── (3) pro needs a verified session ───────────────────────────────────────

def _enforcing(eng):
    _set_config(eng, **{ENFORCE_KNOB: 1.0, WEB_KNOB: 1.0, **NO_PREVIEW})
    return patch.object(entl, "is_enabled", _flags(*BOTH_FLAGS))


def test_paying_user_verified_session_passes(eng, client, stubbed):
    _make_user("active_paid")
    with _enforcing(eng):
        r = client.post("/api/trades/generate", headers={"X-Session-Token": TOKEN, **MOBILE})
    assert r.status_code == 200


@pytest.mark.parametrize("headers", [MOBILE, WEB])
def test_same_user_unverified_gets_verify_required(eng, client, stubbed, headers):
    _make_user("active_paid")
    with _enforcing(eng):
        r = client.post("/api/trades/propose",
                        headers={"X-Session-Token": UNVERIFIED_TOKEN, **headers})
    assert r.status_code == 402
    assert r.get_json() == {"error": "pro_required", "gate": "verify_required"}


@pytest.mark.parametrize("headers", [MOBILE, WEB])
def test_same_user_unverified_on_a_verified_gate_route_gets_its_403(eng, client, headers):
    """R28.14: /generate wears @_gate_unverified_write, so the hook lets an
    unverified session through and the route's own 403 answers (real view)."""
    _make_user("active_paid")
    with _enforcing(eng):
        r = client.post("/api/trades/generate",
                        headers={"X-Session-Token": UNVERIFIED_TOKEN, **headers}, json={})
    assert r.status_code == 403
    assert r.get_json() == {"error": "verification_required"}


@pytest.mark.parametrize("method,path", [("POST", "/api/trades/propose"),
                                         ("GET", "/api/overhauls")])
def test_unverified_never_pro_also_gets_verify_required(eng, client, stubbed, method, path):
    """Legal R28.9: every unverified session gets verify_required at a gated
    action whose route doesn't answer it itself, subscriber or not."""
    with _enforcing(eng):
        r = client.open(path, method=method,
                        headers={"X-Session-Token": UNVERIFIED_TOKEN, **MOBILE})
    assert r.get_json() == {"error": "pro_required", "gate": "verify_required"}


def test_unverified_path_never_reads_entitlements(eng, client):
    _make_user("active_paid")
    ent, hist = _Spy(entl.get_entitlements), _Spy(entl.list_for_user)
    row = _Spy(pg.preview_row)
    with _enforcing(eng), patch.object(entl, "get_entitlements", ent), \
            patch.object(entl, "list_for_user", hist), patch.object(pg, "preview_row", row):
        for path in ("/api/trades/generate", "/api/trades/propose"):
            client.post(path, headers={"X-Session-Token": UNVERIFIED_TOKEN, **MOBILE}, json={})
    assert (ent.calls, hist.calls, row.calls) == (0, 0, 0)


def test_demo_synthetic_session_passes(eng, client, stubbed):
    entl.grant(DEMO_USER, "pro", source="manual_grant")
    with _enforcing(eng):
        r = client.post("/api/trades/generate", headers={"X-Session-Token": DEMO_TOKEN, **MOBILE})
    assert r.status_code == 200


def test_demo_session_exempt_on_deck_routes_only(eng, client, stubbed):
    """head-eng 2026-10-25: the server-made demo session (try-before-sync)
    holds no pro but is exempt on deck routes; a send still gates."""
    with _enforcing(eng):
        hdr = {"X-Session-Token": DEMO_TOKEN, **MOBILE}
        assert client.post("/api/trades/generate", headers=hdr).status_code == 200
        r = client.post("/api/trades/propose", headers=hdr)
    assert r.get_json() == {"error": "pro_required", "gate": "never_trialed"}


def test_me_entitlements_pro_tracks_verification(eng, client):
    entl.grant(USER, "pro", source="manual_grant")
    entl.grant(DEMO_USER, "pro", source="manual_grant")
    get = lambda t: client.get("/api/me/entitlements", headers={"X-Session-Token": t}).get_json()
    assert get(TOKEN)["pro"] is True
    assert get(UNVERIFIED_TOKEN)["pro"] is False
    assert get(DEMO_TOKEN)["pro"] is True


def test_me_entitlements_unverified_gets_empty_view(eng, client):
    """A paying user_id on an unverified session: every entitlement field is
    blank/false (founder too, once S1 adds it); `enforcing` stays the server
    fact. The verified session of the same user gets the real values."""
    _make_user("active_paid")
    get = lambda t: client.get("/api/me/entitlements", headers={"X-Session-Token": t}).get_json()

    real = get(TOKEN)
    assert real["pro"] is True and real["ad_free"] is True
    assert real["sources"] == ["apple_iap"] and real["expires_at"] is not None

    blank = get(UNVERIFIED_TOKEN)
    assert set(blank) == set(real)
    assert blank["enforcing"] == real["enforcing"]
    user_fields = {k: v for k, v in blank.items() if k != "enforcing"}
    assert user_fields == {**entl.empty_entitlements()}
    assert all(not v for v in user_fields.values()), user_fields
    assert blank["pro"] is False and blank["ad_free"] is False
    assert blank["sources"] == [] and blank["expires_at"] is None
    if "founder" in blank:
        assert blank["founder"] is False


# ── (4) never a 402 ────────────────────────────────────────────────────────

def test_unauthenticated_and_bad_token_never_402(eng, client, stubbed):
    with _enforcing(eng):
        assert client.post("/api/trades/generate", headers=MOBILE).status_code == 200
        assert client.post("/api/trades/generate",
                           headers={"X-Session-Token": "nope", **MOBILE}).status_code == 200


def test_unauthenticated_real_route_gets_its_own_auth_answer(eng, client):
    with _enforcing(eng):
        r = client.get("/api/trades/status", headers=MOBILE)
    assert r.status_code != 402


@pytest.mark.parametrize("method,path", [("POST", "/api/extension/auth"),
                                         ("GET", "/api/extension/rankings")])
@pytest.mark.parametrize("headers", [{"X-Source": "extension"}, MOBILE])
def test_extension_endpoints_never_402(eng, client, stubbed, method, path, headers):
    with _enforcing(eng):
        r = client.open(path, method=method, headers={"X-Session-Token": TOKEN, **headers})
    assert r.status_code == 200


@pytest.mark.parametrize("headers", [WEB, {"X-Device": "web"}, {"X-Source": "extension"}])
def test_web_with_web_knob_0_never_402_while_mobile_enforces(eng, client, stubbed, headers):
    _set_config(eng, **{ENFORCE_KNOB: 1.0, WEB_KNOB: 0.0, **NO_PREVIEW})
    with patch.object(entl, "is_enabled", _flags(*BOTH_FLAGS)):
        hdr = {"X-Session-Token": TOKEN}
        assert client.post("/api/trades/generate", headers={**hdr, **MOBILE}).status_code == 402
        assert client.post("/api/trades/generate", headers={**hdr, **headers}).status_code == 200


def test_web_knob_missing_row_reads_0(eng, client, stubbed):
    """G-064: a missing web knob row (other rows present) is 0, not on."""
    _set_config(eng, **{ENFORCE_KNOB: 1.0, WEB_KNOB: None})
    assert WEB_KNOB not in db_module.get_config()
    with patch.object(entl, "is_enabled", _flags(*BOTH_FLAGS)):
        r = client.post("/api/trades/generate", headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200


def test_web_knob_failed_read_is_off(eng):
    def boom():
        raise RuntimeError("db down")
    with patch.object(db_module, "get_config", boom):
        assert pg._web_knob_on() is False


def test_web_knob_seeded_zero():
    seeded = {k: v for k, v, _ in db_module._MODEL_CONFIG_DEFAULTS}
    assert seeded[WEB_KNOB] == 0


def test_free_routes_pass_while_enforcing(eng, client, stubbed):
    with _enforcing(eng):
        hdr = {"X-Session-Token": TOKEN, **MOBILE}
        assert client.delete("/api/account", headers=hdr).status_code == 200
        assert client.get("/api/trades/matches", headers=hdr).status_code == 200


# ── (5) hot path ───────────────────────────────────────────────────────────

class _Spy:
    def __init__(self, real):
        self.real, self.calls = real, 0

    def __call__(self, *a, **kw):
        self.calls += 1
        return self.real(*a, **kw)


@pytest.mark.parametrize("headers", [MOBILE, WEB])
def test_dark_reads_nothing(eng, client, stubbed, headers):
    """Flags off: neither a gated nor a free request reads model_config or
    an entitlement."""
    cfg, ent, hist = (_Spy(db_module.get_config), _Spy(entl.get_entitlements),
                      _Spy(entl.list_for_user))
    with patch.object(entl, "is_enabled", _flags()), \
            patch.object(db_module, "get_config", cfg), \
            patch.object(entl, "get_entitlements", ent), \
            patch.object(entl, "list_for_user", hist):
        hdr = {"X-Session-Token": TOKEN, **headers}
        assert client.post("/api/trades/generate", headers=hdr).status_code == 200
        assert client.post("/api/trade/evaluate", headers=hdr).status_code == 200
    assert (cfg.calls, ent.calls, hist.calls) == (0, 0, 0)


def test_not_enforcing_reads_no_entitlement(eng, client, stubbed):
    """Flags on, knob 0: the knob is read, no entitlement is."""
    _set_config(eng, **{ENFORCE_KNOB: 0.0, WEB_KNOB: 1.0})
    ent, hist = _Spy(entl.get_entitlements), _Spy(entl.list_for_user)
    with patch.object(entl, "is_enabled", _flags(*BOTH_FLAGS)), \
            patch.object(entl, "get_entitlements", ent), \
            patch.object(entl, "list_for_user", hist):
        assert client.post("/api/trades/generate",
                           headers={"X-Session-Token": TOKEN, **MOBILE}).status_code == 200
    assert (ent.calls, hist.calls) == (0, 0)


def test_entitlement_read_failure_fails_open(eng, client, stubbed):
    def boom(_uid):
        raise RuntimeError("entitlements down")
    with _enforcing(eng), patch.object(entl, "get_entitlements", boom):
        r = client.post("/api/trades/generate", headers={"X-Session-Token": TOKEN, **MOBILE})
    assert r.status_code == 200


@pytest.mark.parametrize("headers", [MOBILE, {"X-Device": "web"}])
@pytest.mark.parametrize("method,path,endpoint", [
    ("POST", "/api/invite/token", "mint_invite_token"),
    ("GET", "/app/league/join/league-1/go/web", "league_join_go"),
])
def test_referral_routes_pass_global_gate_while_enforcing(
        eng, client, monkeypatch, headers, method, path, endpoint):
    # Keep route-owned membership/flag checks separate; this specifically
    # proves the global gate never asks a free referral route to subscribe.
    monkeypatch.setitem(server.app.view_functions, endpoint, lambda **kw: ("free referral", 200))
    with _enforcing(eng):
        _set_config(eng, **{WEB_KNOB: 1.0})
        response = client.open(path, method=method,
                               headers={"X-Session-Token": TOKEN, **headers})
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "free referral"


@pytest.mark.parametrize("path", ["/api/trades/propose", "/api/trades/propose-espn",
                                  "/api/trades/propose-mfl"])
@pytest.mark.parametrize("verified", [False, True])
def test_integrated_account_shop_send_is_stopped_before_elo(eng, client, path, verified):
    """Platform sign-in's account key uses the same gate before Shop signals."""
    account_user = "acct_launch-boundary"
    with eng.begin() as conn:
        conn.execute(insert(users_table).values(sleeper_user_id=account_user))
    with server._sessions_lock:
        server._sessions[TOKEN].update(user_id=account_user, verified=verified)
    with _enforcing(eng), patch.object(server, "_record_shop_send_signal") as signal:
        response = client.post(path, json={"source": "shop"},
                               headers={"X-Session-Token": TOKEN, **MOBILE})
    assert response.status_code == 402, response.get_json()
    assert response.get_json()["gate"] == ("never_trialed" if verified else "verify_required")
    signal.assert_not_called()


# ── (6) the web knob at 1 (owner 2026-11-25: "aligned. Close this") ───────
#
# paywall_web_enforce_enabled = 1 is a required turn-on step (turn-on-runbook
# §B). With it on, a request without the native app's X-Device is walled
# exactly like the app; nothing the website still serves after the launch cut
# of web sign-in (landing, legal, ranking-method, share and OG landings, the
# referral join page, the RevenueCat webhook, cron) may start answering 402.
# The seed stays 0 (test_web_knob_seeded_zero): turning it on is the
# operator's step, never a default.

BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Version/18.1 Safari/605.1.15"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
NON_APP = {
    "no_header": {},
    "browser": BROWSER,
    "expo_web": {"X-Device": "web", **BROWSER},
    "extension": {"X-Source": "extension"},
    "unknown_device": {"X-Device": "windows"},
}


def _rule_keys():
    return sorted({(m, r.rule) for r in server.app.url_map.iter_rules()
                   for m in r.methods if m not in ("HEAD", "OPTIONS")},
                  key=lambda k: (k[1], k[0]))


GATED_RULES = [k for k in _rule_keys() if pg.ROUTES.get(k) == pg.GATED]
NOT_GATED_RULES = [k for k in _rule_keys() if pg.ROUTES.get(k) != pg.GATED]


def _concrete(rule):
    """A request path for a Flask rule: <int:x> → 7, any other <x> → x1."""
    return re.sub(r"<[^>]+>", "x1", re.sub(r"<int:[^>]+>", "7", rule))


def _web_wall(eng):
    """Enforcing with the web knob at 1, the preview off."""
    _set_config(eng, **{ENFORCE_KNOB: 1.0, WEB_KNOB: 1.0, **NO_PREVIEW})
    return patch.object(entl, "is_enabled", _flags(*BOTH_FLAGS))


@pytest.fixture()
def gated_stubbed(monkeypatch):
    """Every gated rule's view returns a plain 200."""
    endpoints = {r.endpoint for r in server.app.url_map.iter_rules()
                 if any(pg.ROUTES.get((m, r.rule)) == pg.GATED for m in r.methods)}
    for ep in endpoints:
        monkeypatch.setitem(server.app.view_functions, ep, lambda **_kw: ("ok", 200))


def test_gated_rule_lists_are_not_vacuous():
    assert len(GATED_RULES) >= 30 and ("POST", "/api/trades/propose-espn") in GATED_RULES
    assert ("POST", "/api/billing/revenuecat/webhook") in NOT_GATED_RULES
    assert ("GET", "/<path:filename>") in NOT_GATED_RULES


@pytest.mark.parametrize("method,rule", GATED_RULES)
def test_web_knob_1_walls_every_gated_rule_like_the_app(eng, method, rule):
    """Pure decide(): with the web knob at 1 a non-app request gets the app's
    answer on every gated rule: 402 for a never-entitled verified session,
    through for a subscriber, through with no session (the route's own auth
    answers). Knob 0: the same non-app request passes."""
    blocked = (402, {"error": "pro_required", "gate": "never_trialed"})
    with _web_wall(eng):
        assert pg.decide(rule, method, USER, False, True) == blocked
        assert pg.decide(rule, method, USER, True, True) == blocked
        assert pg.decide(rule, method, None, False, True) is None
        _set_config(eng, **{WEB_KNOB: 0.0})
        assert pg.decide(rule, method, USER, False, True) is None
        _set_config(eng, **{WEB_KNOB: 1.0})
        entl.grant(USER, "pro", source="manual_grant")
        assert pg.decide(rule, method, USER, False, True) is None


@pytest.mark.parametrize("client_name", list(NON_APP))
def test_web_knob_1_http_every_gated_rule_402s_a_non_app_request(
        eng, client, gated_stubbed, client_name):
    headers = {"X-Session-Token": TOKEN, **NON_APP[client_name]}
    with _web_wall(eng):
        for method, rule in GATED_RULES:
            r = client.open(_concrete(rule), method=method, headers=headers)
            assert (r.status_code, r.get_json()) == (
                402, {"error": "pro_required", "gate": "never_trialed"}), (method, rule)


@pytest.mark.parametrize("client_name", list(NON_APP))
def test_web_knob_1_http_subscriber_passes_every_gated_rule(
        eng, client, gated_stubbed, client_name):
    _make_user("active_paid")
    headers = {"X-Session-Token": TOKEN, **NON_APP[client_name]}
    with _web_wall(eng):
        for method, rule in GATED_RULES:
            r = client.open(_concrete(rule), method=method, headers=headers)
            assert r.status_code == 200, (method, rule)


@pytest.mark.parametrize("client_name", ["browser", "expo_web"])
def test_web_knob_1_unverified_browser_gets_verify_required(eng, client, stubbed, client_name):
    """A browser holding an unverified session: verify_required, never a
    price, the same as the app (every gated rule: test_paywall_gate_unverified)."""
    _make_user("active_paid")
    with _web_wall(eng):
        r = client.post("/api/trades/propose",
                        headers={"X-Session-Token": UNVERIFIED_TOKEN, **NON_APP[client_name]})
    assert (r.status_code, r.get_json()) == (
        402, {"error": "pro_required", "gate": "verify_required"})


@pytest.mark.parametrize("client_name", list(NON_APP))
def test_web_knob_1_no_session_never_402(eng, client, gated_stubbed, client_name):
    """What a signed-out browser gets: never a 402 (the route's own auth
    answers; here the stub's 200)."""
    with _web_wall(eng):
        for method, rule in GATED_RULES:
            r = client.open(_concrete(rule), method=method, headers=NON_APP[client_name])
            assert r.status_code == 200, (method, rule)


def test_web_knob_1_every_non_gated_rule_passes_without_a_read(eng):
    """Pure decide() over every non-gated rule in app.url_map: a verified,
    never-entitled, non-app session passes, and no entitlement is read."""
    ent, hist = _Spy(entl.get_entitlements), _Spy(entl.list_for_user)
    with _web_wall(eng), patch.object(entl, "get_entitlements", ent), \
            patch.object(entl, "list_for_user", hist):
        through = [(m, r) for m, r in NOT_GATED_RULES
                   if pg.decide(r, m, USER, False, True) is not None]
    assert through == []
    assert (ent.calls, hist.calls) == (0, 0)


# What the website still serves after the 2026-11-25 cut (web/CLAUDE.md
# §Pages), plus the provider and operator traffic that reaches the same host.
# Real views except the cron tick (stubbed: with no CRON_SECRET in a test
# env it would run the whole tick). Status is whatever the view answers (200,
# 302 for a cut page, 404 for an unknown share token, 4xx for an empty body),
# never 402.
WEBSITE_REQUESTS = [
    ("GET", "/"), ("GET", "/index.html"), ("GET", "/faq.html"), ("GET", "/contact.html"),
    ("GET", "/privacy"), ("GET", "/terms"), ("GET", "/privacy.html"), ("GET", "/terms.html"),
    ("GET", "/ranking-method.html"), ("GET", "/profile.html"), ("GET", "/404.html"),
    ("GET", "/robots.txt"), ("GET", "/sitemap.xml"), ("GET", "/css/styles.css"),
    ("GET", "/js/landing-steps.js"), ("GET", "/no-such-page"),
    ("GET", "/calculator.html"), ("GET", "/positional-tiers.html"),
    ("GET", "/.well-known/apple-app-site-association"),
    ("GET", "/u/someone"), ("GET", "/s/trade/tok1"), ("GET", "/s/p/abc"),
    ("GET", "/s/tiers/QB/someone"), ("GET", "/og/trade/tok1.png"), ("GET", "/og/p/abc.png"),
    ("GET", "/app/league/join/l1"), ("GET", "/app/league/join/l1/go/web"),
    ("GET", "/api/feature-flags"), ("GET", "/api/me/entitlements"),
    ("GET", "/api/paywall/config"), ("GET", "/api/session/ping"),
    ("POST", "/api/feedback"), ("POST", "/api/events"),
    ("POST", "/api/billing/revenuecat/webhook"), ("POST", "/api/cron/daily-tick"),
    ("GET", "/api/admin/config"),
]


@pytest.mark.usefixtures("no_real_network")
@pytest.mark.parametrize("token", [None, TOKEN], ids=["signed_out", "stale_session"])
@pytest.mark.parametrize("method,path", WEBSITE_REQUESTS)
def test_web_knob_1_website_and_provider_routes_never_402(
        eng, client, monkeypatch, method, path, token):
    monkeypatch.setitem(server.app.view_functions, "cron_daily_tick", lambda: ("ok", 200))
    headers = dict(BROWSER, **({"X-Session-Token": token} if token else {}))
    with _web_wall(eng):
        r = client.open(path, method=method, headers=headers,
                        json={} if method == "POST" else None)
    assert r.status_code != 402, (method, path, r.status_code)
    assert b"pro_required" not in r.get_data(), (method, path)
