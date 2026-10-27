"""Unverified sessions at the paywall gate: legal R28.9 as amended by R28.14
(approved with conditions, 2026-10-27).

An unverified, non-demo session is settled from verified-ness alone, before
any paywall_previews or entitlement read:
  * a gated rule whose view wears the account-auth verified gate for the
    method (@_gate_unverified_read / _write) → the hook lets it through and
    the route's own 403 `verification_required` answers;
  * any other gated rule → 402 `verify_required`;
  * it never gets the deck preview and never writes paywall_previews.

Legal condition (b), the CI proof: for EVERY gated rule in
paywall_gate.ROUTES, an unverified session's response (status, body bytes,
headers but Date) is byte-identical across four account states of its
user_id: no history, a paywall_previews row, active pro, lapsed pro. Run on
the native app and on the web with the web knob on; real views, nothing
stubbed (neither answer runs a route body).

Sabotages recorded in living-memory/TEST_LEDGER.md (2026-10-27).
"""

import json
import re
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, func, insert, select

import backend.database as db_module
import backend.entitlements as entl
import backend.paywall_gate as pg
import backend.server as server
from backend.database import metadata, model_config_table, users_table

BOTH_FLAGS = ("monetize.entitlements", "monetize.paywall")
MOBILE = {"X-Device": "iphone", "X-OS-Version": "18.1", "X-App-Version": "1.13.2"}
CLIENTS = {"mobile": MOBILE, "web_knob1": {}}
STATES = ("no_history", "preview_row", "active_pro", "lapsed_pro")
VOLATILE_HEADERS = {"Date"}

GATED_RULES = sorted(k for k, v in pg.ROUTES.items() if v == pg.GATED)

# The gated rules whose view answers an unverified session itself (403
# verification_required). Every other gated rule gets the hook's 402. Pinned
# so a decorator added or dropped shows up here as a reviewed change.
ROUTE_ANSWERS = {
    ("GET", "/api/trades"), ("POST", "/api/trades/generate"),
    ("POST", "/api/trades/pass-reason"), ("GET", "/api/trades/status"),
    ("POST", "/api/trades/swipe"), ("POST", "/api/trades/queue"),
    ("POST", "/api/trades/asset-ideas"), ("POST", "/api/trades/fair-packages"),
    ("POST", "/api/trades/matches/<int:match_id>/disposition"),
    ("POST", "/api/trades/standing-offer"),
}
VERIFICATION_REQUIRED = (403, {"error": "verification_required"})
VERIFY_REQUIRED = (402, {"error": "pro_required", "gate": "verify_required"})


def _iso(delta=timedelta(0)):
    return (datetime.now(timezone.utc) + delta).isoformat()


def _path(rule: str) -> str:
    """A concrete path for a Flask rule (<int:x> → 7, any other <x> → x1)."""
    rule = re.sub(r"<int:[^>]+>", "7", rule)
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"\g<1>1", rule)


@pytest.fixture()
def eng():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with patch.object(db_module, "engine", engine):
        yield engine


def _config(engine, **values):
    with engine.begin() as conn:
        for key, value in values.items():
            conn.execute(model_config_table.delete().where(model_config_table.c.key == key))
            conn.execute(insert(model_config_table).values(key=key, value=value))


def _rc(uid, events):
    for i, (etype, period, days) in enumerate(events):
        ev = {"id": f"{uid}-{i}", "type": etype, "app_user_id": uid,
              "product_id": "ftf_pro_monthly", "environment": "PRODUCTION",
              "period_type": period, "expiration_at_ms": (time.time() + days * 86400) * 1000}
        entl.ingest_billing_event("revenuecat", ev["id"], etype, ev, user_id=uid,
                                  product_id="ftf_pro_monthly")


def _make(state, uid):
    if state == "preview_row":
        assert pg.record_preview(uid, "job-held", 1, ["t-0", "t-1"])
    elif state == "active_pro":
        _rc(uid, [("INITIAL_PURCHASE", "NORMAL", 30)])
        assert entl.get_entitlements(uid)["pro"] is True
    elif state == "lapsed_pro":
        _rc(uid, [("INITIAL_PURCHASE", "NORMAL", -1), ("EXPIRATION", "NORMAL", -1)])
        assert entl.get_entitlements(uid)["pro"] is False
        assert pg._held_pro(uid) == "paid"


@pytest.fixture()
def accounts(eng):
    """One unverified session per account state; enforcing, both knobs on,
    the preview knob 1 (so a preview path, if one came back, would show)."""
    _config(eng, paywall_enforce_enabled=1.0, paywall_web_enforce_enabled=1.0,
            paywall_preview_pages=1.0)
    server.app.config["TESTING"] = True
    tokens = {}
    with eng.begin() as conn:
        for state in STATES:
            conn.execute(insert(users_table).values(
                sleeper_user_id=f"r2814_{state}", username=f"u_{state}", created_at=_iso()))
    for state in STATES:
        uid = f"r2814_{state}"
        _make(state, uid)
        tokens[state] = f"r2814-tok-{state}"
    with server._sessions_lock:
        for state, tok in tokens.items():
            server._sessions[tok] = {"user_id": f"r2814_{state}", "last_active": time.time()}
    try:
        with patch.object(entl, "is_enabled", lambda k: k in BOTH_FLAGS):
            yield server.app.test_client(), tokens
    finally:
        with server._sessions_lock:
            for tok in tokens.values():
                server._sessions.pop(tok, None)


class _Spy:
    def __init__(self, real):
        self.real, self.calls = real, 0

    def __call__(self, *a, **kw):
        self.calls += 1
        return self.real(*a, **kw)


def _shape(r):
    return (r.status_code, r.get_data(),
            sorted((k, v) for k, v in r.headers.items() if k not in VOLATILE_HEADERS))


def _previews(engine):
    t = db_module.paywall_previews_table
    with engine.begin() as conn:
        return [tuple(r) for r in conn.execute(select(t).order_by(t.c.user_id))]


def test_matrix_covers_every_gated_rule():
    assert len(GATED_RULES) == 32
    assert ROUTE_ANSWERS <= set(GATED_RULES)
    assert pg.DECK_ROUTES <= ROUTE_ANSWERS


@pytest.mark.parametrize("client_name", sorted(CLIENTS))
@pytest.mark.parametrize("method,rule", GATED_RULES)
def test_unverified_answer_is_byte_identical_across_account_states(
        eng, accounts, method, rule, client_name):
    client, tokens = accounts
    before = _previews(eng)
    reads = {"preview_row": _Spy(pg.preview_row),
             "get_entitlements": _Spy(entl.get_entitlements),
             "list_for_user": _Spy(entl.list_for_user)}
    shapes = {}
    with patch.object(pg, "preview_row", reads["preview_row"]), \
            patch.object(entl, "get_entitlements", reads["get_entitlements"]), \
            patch.object(entl, "list_for_user", reads["list_for_user"]):
        for state in STATES:
            kwargs = {"json": {}} if method in ("POST", "PUT") else {}
            r = client.open(_path(rule), method=method,
                            headers={"X-Session-Token": tokens[state], **CLIENTS[client_name]},
                            **kwargs)
            shapes[state] = _shape(r)
    first = shapes[STATES[0]]
    for state in STATES[1:]:
        assert shapes[state] == first, (method, rule, client_name, state)
    status, body = VERIFICATION_REQUIRED if (method, rule) in ROUTE_ANSWERS else VERIFY_REQUIRED
    assert first[0] == status
    assert json.loads(first[1]) == body
    assert {name: spy.calls for name, spy in reads.items()} == dict.fromkeys(reads, 0)
    assert _previews(eng) == before                     # never writes paywall_previews


@pytest.mark.parametrize("method,rule", GATED_RULES)
def test_hook_reads_the_route_gate_off_the_live_view(method, rule):
    names = {r.endpoint for r in server.app.url_map.iter_rules()
             if r.rule == rule and method in r.methods}
    assert len(names) == 1
    assert server._route_answers_unverified(names.pop(), method) is ((method, rule) in ROUTE_ANSWERS)


@pytest.mark.parametrize("method,rule", sorted(pg.DECK_ROUTES))
@pytest.mark.parametrize("route_verifies", [True, False])
def test_unverified_deck_request_never_reaches_the_preview(eng, method, rule, route_verifies):
    """The pure decision, with the deck view's own gate on and off: the
    route's answer (None) or 402 verify_required, never a Preview, and no
    paywall_previews or entitlement read, whatever the row says."""
    _config(eng, paywall_enforce_enabled=1.0, paywall_preview_pages=1.0)
    pg.record_preview("r2814_held", "job-held", 1, ["t-0"])
    ask = pg.DeckAsk(page_size=5, job_id="job-held", cursor=0, trade_id="t-0",
                     page_trade_ids=lambda _j, _l: {"t-0"})
    boom = lambda *_a, **_k: pytest.fail("read on an unverified session")
    with patch.object(entl, "is_enabled", lambda k: k in BOTH_FLAGS), \
            patch.object(pg, "preview_row", boom), \
            patch.object(entl, "get_entitlements", boom), \
            patch.object(entl, "list_for_user", boom):
        for uid in ("r2814_held", "r2814_new"):
            got = pg.decide(rule, method, uid, True, False, route_verifies=route_verifies, ask=ask)
            assert got == (None if route_verifies else VERIFY_REQUIRED)


def test_demo_session_keeps_its_deck_exemption(eng):
    """The synthetic demo session is unchanged: through on deck routes."""
    _config(eng, paywall_enforce_enabled=1.0)
    with patch.object(entl, "is_enabled", lambda k: k in BOTH_FLAGS):
        for method, rule in sorted(pg.DECK_ROUTES):
            assert pg.decide(rule, method, "demo_user_1a2b3c4d", True, True, demo=True) is None


def test_unverified_web_request_with_the_web_knob_off_is_untouched(eng):
    """Web with paywall_web_enforce_enabled 0: the gate doesn't apply to web,
    unverified or not (the route's own auth answers), as before."""
    _config(eng, paywall_enforce_enabled=1.0, paywall_web_enforce_enabled=0.0)
    with patch.object(entl, "is_enabled", lambda k: k in BOTH_FLAGS):
        assert pg.decide("/api/trades/propose", "POST", "u1", False, False) is None
        assert pg.decide("/api/trades/propose", "POST", "u1", True, False) == VERIFY_REQUIRED


def test_no_statement_touches_paywall_or_entitlement_tables(eng, accounts):
    """The same proof at the SQL layer, over every gated rule at once."""
    client, tokens = accounts
    seen = []
    listener = lambda conn, cursor, statement, *a: seen.append(statement)
    event.listen(eng, "before_cursor_execute", listener)
    try:
        for method, rule in GATED_RULES:
            kwargs = {"json": {}} if method in ("POST", "PUT") else {}
            client.open(_path(rule), method=method,
                        headers={"X-Session-Token": tokens["active_pro"], **MOBILE}, **kwargs)
    finally:
        event.remove(eng, "before_cursor_execute", listener)
    touched = [s for s in seen if re.search(
        r"\b(paywall_previews|entitlements|subscription_events)\b", s)]
    assert touched == []
    with eng.begin() as conn:
        assert conn.execute(select(func.count()).select_from(
            db_module.paywall_previews_table)).scalar() == 1   # the preview_row state's own
