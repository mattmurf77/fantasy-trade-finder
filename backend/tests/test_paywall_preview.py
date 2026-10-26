"""The paywall deck preview (backend/paywall_gate.py + server._serve_trade_job).

head-eng 2026-10-25: a never-entitled user gets the first
`paywall_preview_pages` pages (default 1) of their FIRST deck free while the
gate enforces. A deck is one trade job (job_id); a page is E2's window of
`trade_page_size` raw cards. Consumption is recorded only when /generate or
/status actually serves cards, never at job kickoff, so warm-up and cron-built
jobs can't spend it.

Covers: page 1 passes, page 2 and any later deck 402 `preview_used`; the
unpaged (legacy) body is capped to the window; swipe/pass-reason on window
cards only; entitled users unaffected; knob 0 / 2 / missing row (G-064: 1);
kickoff and warm-up jobs never consume; the demo session is exempt and a real
verified account is gated; an unverified never-entitled session still gets
the preview; trial-expired keeps its reason; a concurrent second deck loses;
deletion and export include the new table.

Harness: E2's (test_trade_responses_small) real /generate and /status over
seeded jobs; in-memory SQLite; no network.
"""
import time
from unittest.mock import patch

import pytest
from sqlalchemy import insert

import backend.entitlements as entl
import backend.paywall_gate as pg
from backend import accounts, database as db, server, trade_service as ts
from backend.tests.test_fair_packages import harness, ME, LEAGUE, TOKEN  # noqa: F401 (fixture)
from backend.tests.test_trade_responses_small import JOB_ID, card, e2, seed_job  # noqa: F401
from backend.tests import test_trade_page_store as p1mod
from backend.tests.test_i1_serve_filter import live  # noqa: F401 (fixture)
from backend.tests.test_trade_page_store import p1, spawned  # noqa: F401 (fixtures)

PAGE = 5
MOBILE = {"X-Session-Token": TOKEN, "X-Device": "iphone"}
BOTH_FLAGS = ("monetize.entitlements", "monetize.paywall")


def _config(engine, **values):
    with engine.begin() as conn:
        for key, value in values.items():
            conn.execute(db.model_config_table.delete().where(db.model_config_table.c.key == key))
            if value is not None:
                conn.execute(insert(db.model_config_table).values(key=key, value=value))


@pytest.fixture
def gate(e2, monkeypatch):
    """Enforcing, mobile, trade_page_size 5, preview knob 1, a 12-card job."""
    client, engine, spawned = e2
    monkeypatch.setitem(ts._cfg, "trade_page_size", float(PAGE))
    _config(engine, paywall_enforce_enabled=1.0, paywall_preview_pages=1.0)
    seed_job([card(i) for i in range(12)])
    with patch.object(entl, "is_enabled", lambda k: k in BOTH_FLAGS):
        yield client, engine, spawned


def status(client, cursor=None, job_id=JOB_ID, headers=MOBILE):
    query = f"/api/trades/status?job_id={job_id}"
    if cursor is not None:
        query += f"&cursor={cursor}"
    return client.get(query, headers=headers)


def generate(client, **body):
    return client.post("/api/trades/generate", headers=MOBILE,
                       json={"league_id": LEAGUE, "fairness_threshold": .75, **body})


def ids(r):
    return [c["trade_id"] for c in r.get_json()["cards"]]


PREVIEW_USED = {"error": "pro_required", "gate": "preview_used"}


def test_first_page_passes_page_two_blocked(gate):
    client, *_ = gate
    assert pg.preview_row(ME) is None
    r = status(client, 0)
    assert r.status_code == 200 and len(ids(r)) == PAGE
    assert r.get_json()["cursor"] == PAGE
    row = pg.preview_row(ME)
    assert (row["deck_key"], row["pages_served"]) == (JOB_ID, 1)
    r = status(client, PAGE)
    assert r.status_code == 402 and r.get_json() == PREVIEW_USED
    assert status(client, 0).status_code == 200          # page 1 of the same deck re-serves


def test_unpaged_body_capped_to_the_window(gate):
    client, *_ = gate
    r = status(client)
    assert r.status_code == 200
    assert ids(r) == [f"e2-trade-{i:05d}" for i in range(PAGE)]   # 12 in the job
    assert pg.preview_row(ME)["pages_served"] == 1
    assert status(client).status_code == 200                      # the same deck re-polls


def test_generate_serves_page_one_then_any_later_deck_is_blocked(gate):
    client, *_ = gate
    r = generate(client, page=1)                 # cache hit: serves page 1 now
    assert r.status_code == 200 and len(ids(r)) == PAGE
    assert pg.preview_row(ME)["deck_key"] == JOB_ID
    assert generate(client, page=1).get_json() == PREVIEW_USED
    assert generate(client).get_json() == PREVIEW_USED            # unpaged too
    # Another league or format is another job: blocked too.
    server._trade_jobs["other-job"] = {**server._trade_jobs[JOB_ID], "job_id": "other-job"}
    assert status(client, 0, job_id="other-job").get_json() == PREVIEW_USED


@pytest.fixture
def swipe_ok(monkeypatch):
    for ep in ("swipe_trade", "trade_pass_reason"):
        monkeypatch.setitem(server.app.view_functions, ep, lambda **_kw: ("ok", 200))


@pytest.mark.parametrize("path", ["/api/trades/swipe", "/api/trades/pass-reason"])
def test_swipe_and_pass_reason_on_window_cards_only(gate, swipe_ok, path):
    client, *_ = gate
    body = lambda i: {"trade_id": f"e2-trade-{i:05d}", "decision": "pass", "reason": "value"}
    assert client.post(path, headers=MOBILE, json=body(0)).get_json() == PREVIEW_USED  # nothing served yet
    status(client, 0)
    assert client.post(path, headers=MOBILE, json=body(0)).status_code == 200
    assert client.post(path, headers=MOBILE, json=body(PAGE - 1)).status_code == 200
    assert client.post(path, headers=MOBILE, json=body(PAGE)).get_json() == PREVIEW_USED
    assert client.post(path, headers=MOBILE, json={"decision": "pass"}).get_json() == PREVIEW_USED


def test_entitled_user_unaffected(gate):
    client, *_ = gate
    entl.grant(ME, "pro", source="manual_grant")
    assert len(ids(status(client))) == 12
    assert status(client, PAGE).status_code == 200
    assert generate(client).status_code == 200
    assert pg.preview_row(ME) is None


def test_get_trades_pending_view_is_not_the_preview(gate):
    client, *_ = gate
    r = client.get(f"/api/trades?league_id={LEAGUE}", headers=MOBILE)
    assert r.status_code == 402 and r.get_json() == PREVIEW_USED


def test_knob_zero_blocks_the_first_request(gate):
    client, engine, _ = gate
    _config(engine, paywall_preview_pages=0.0)
    assert status(client, 0).get_json() == PREVIEW_USED
    assert generate(client, page=1).get_json() == PREVIEW_USED
    assert pg.preview_row(ME) is None


def test_knob_two_serves_two_pages(gate):
    client, engine, _ = gate
    _config(engine, paywall_preview_pages=2.0)
    assert len(ids(status(client, 0))) == PAGE
    r = status(client, PAGE)
    assert r.status_code == 200 and len(ids(r)) == PAGE
    assert pg.preview_row(ME)["pages_served"] == 2
    assert status(client, 2 * PAGE).get_json() == PREVIEW_USED
    assert len(ids(status(client))) == 2 * PAGE                   # unpaged cap = 2 pages


def test_missing_knob_row_is_one_page(gate):
    client, engine, _ = gate
    _config(engine, paywall_preview_pages=None)                   # other rows remain
    assert pg.PREVIEW_KNOB not in db.get_config()
    assert pg.preview_pages() == 1
    assert status(client, 0).status_code == 200
    assert status(client, PAGE).get_json() == PREVIEW_USED


def test_knob_failed_read_is_one_and_seed_is_one():
    def boom():
        raise RuntimeError("db down")
    with patch.object(db, "get_config", boom):
        assert pg.preview_pages() == 1
    seeded = {k: v for k, v, _ in db._MODEL_CONFIG_DEFAULTS}
    assert seeded["paywall_preview_pages"] == 1


def test_kickoff_and_warm_up_jobs_never_consume(gate):
    client, _engine, spawned = gate
    # A warm-up / cron-built job sitting in the registry spends nothing.
    assert server._trade_jobs[JOB_ID]["cards"] and pg.preview_row(ME) is None
    # A fresh kickoff answers running with no cards: nothing served, nothing spent.
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    r = generate(client, page=1)
    assert r.status_code == 200 and r.get_json()["cards"] == [] and spawned
    assert pg.preview_row(ME) is None
    # The first served page is the consumption point.
    job_id = r.get_json()["job_id"]
    with server._trade_jobs_lock:
        server._trade_jobs[job_id].update(cards=[card(i) for i in range(12)], status="complete")
    assert len(ids(status(client, 0, job_id=job_id))) == PAGE
    assert pg.preview_row(ME)["deck_key"] == job_id


def test_demo_session_exempt_real_account_gated(gate):
    client, *_ = gate
    demo_user, demo_token = "demo_user_1a2b3c4d", "preview-demo-token"
    with server._sessions_lock:
        server._sessions[demo_token] = {**server._sessions[TOKEN], "user_id": demo_user,
                                        "is_demo": True, "verified": False}
    try:
        server._trade_jobs["demo-job"] = {**server._trade_jobs[JOB_ID], "job_id": "demo-job",
                                          "key": (demo_user, LEAGUE, "1qb_ppr")}
        hdr = {"X-Session-Token": demo_token, "X-Device": "iphone"}
        assert len(ids(status(client, None, job_id="demo-job", headers=hdr))) == 12
        assert status(client, PAGE, job_id="demo-job", headers=hdr).status_code == 200
        assert pg.preview_row(demo_user) is None
    finally:
        with server._sessions_lock:
            server._sessions.pop(demo_token, None)
    # ME is a real, verified, never-entitled account (an App Review demo account
    # is one of these): the normal preview, then gated.
    assert status(client, 0).status_code == 200
    assert status(client, PAGE).get_json() == PREVIEW_USED


def test_unverified_never_entitled_still_gets_the_preview(gate):
    ask = pg.DeckAsk(page_size=PAGE, job_id=JOB_ID, cursor=0)
    got = pg.verdict("/api/trades/status", "GET", ME, True, False, ask=ask)
    assert got == pg.Preview(pages=1, page_size=PAGE)


def test_trial_expired_gets_no_preview(gate):
    client, *_ = gate
    for eid, etype in (("t-a", "INITIAL_PURCHASE"), ("t-b", "EXPIRATION")):
        ev = {"id": eid, "type": etype, "app_user_id": ME, "product_id": "ftf_pro_monthly",
              "environment": "PRODUCTION", "period_type": "TRIAL",
              "expiration_at_ms": (time.time() - 86400) * 1000}
        entl.ingest_billing_event("revenuecat", eid, etype, ev, user_id=ME,
                                  product_id="ftf_pro_monthly")
    assert status(client, 0).get_json() == {"error": "pro_required", "gate": "trial_expired"}
    assert pg.preview_row(ME) is None


def test_concurrent_second_deck_loses(gate):
    assert pg.record_preview(ME, "deck-a", 1) is True
    assert pg.record_preview(ME, "deck-b", 1) is False
    assert pg.record_preview(ME, "deck-a", 1) is True
    assert pg.preview_row(ME)["deck_key"] == "deck-a"


def test_concurrent_second_deck_serve_answers_402(gate):
    client, *_ = gate
    pg.record_preview(ME, "another-deck", 1)       # won the race just now
    # The hook read no row for this request; the serve-time claim catches it.
    with patch.object(pg, "preview_row", side_effect=[None, {"deck_key": "another-deck",
                                                             "pages_served": 1}]):
        r = status(client, 0)
    assert r.status_code == 402 and r.get_json() == PREVIEW_USED


# ── Legal R28.9: unverified sessions never reveal subscriber status ───────
#
# Every deck route also wears the account-auth verified gate
# (@_gate_unverified_read/_write → 403 verification_required), which answers
# an unverified session before any card is served. To exercise the paywall
# gate's own rule, `unverified_deck` swaps /status for its undecorated view
# (functools.wraps' __wrapped__); the real decorated route is pinned below.

PAYING, FREE, TRIAL, LAPSED, GRANTED, NEW = (
    "r289_paying", "r289_free", "r289_trial", "r289_lapsed", "r289_granted", "r289_new")
VERIFY_REQUIRED = {"error": "pro_required", "gate": "verify_required"}
VOLATILE_HEADERS = {"Date"}   # the Flask test client sets none; excluded anyway


def _rc_user(uid, events):
    for i, (etype, period, days) in enumerate(events):
        ev = {"id": f"{uid}-{i}", "type": etype, "app_user_id": uid,
              "product_id": "ftf_pro_monthly", "environment": "PRODUCTION",
              "period_type": period, "expiration_at_ms": (time.time() + days * 86400) * 1000}
        entl.ingest_billing_event("revenuecat", ev["id"], etype, ev, user_id=uid,
                                  product_id="ftf_pro_monthly")


@pytest.fixture
def unverified_deck(gate, monkeypatch):
    client, *_ = gate
    _rc_user(PAYING, [("INITIAL_PURCHASE", "NORMAL", 30)])
    _rc_user(TRIAL, [("INITIAL_PURCHASE", "TRIAL", -1), ("EXPIRATION", "TRIAL", -1)])
    _rc_user(LAPSED, [("INITIAL_PURCHASE", "NORMAL", -1), ("EXPIRATION", "NORMAL", -1)])
    entl.grant(GRANTED, "pro", source="manual_grant")
    view = server.app.view_functions["trade_job_status"]
    monkeypatch.setitem(server.app.view_functions, "trade_job_status", view.__wrapped__)
    users = (PAYING, FREE, TRIAL, LAPSED, GRANTED, NEW)
    with server._sessions_lock:
        base = server._sessions[TOKEN]
        for uid in users:
            server._sessions[f"tok-{uid}"] = {**base, "user_id": uid, "verified": False}
            server._trade_jobs[f"job-{uid}"] = {**server._trade_jobs[JOB_ID], "job_id": f"job-{uid}",
                                                "key": (uid, LEAGUE, "1qb_ppr")}
    try:
        yield client
    finally:
        with server._sessions_lock:
            for uid in users:
                server._sessions.pop(f"tok-{uid}", None)


def _as(uid):
    return {"X-Session-Token": f"tok-{uid}", "X-Device": "iphone"}


def _st(client, uid, cursor):
    return status(client, cursor, job_id=f"job-{uid}", headers=_as(uid))


def _shape(r):
    """Status, body bytes and every header but the volatile ones."""
    return (r.status_code, r.get_data(),
            sorted((k, v) for k, v in r.headers.items() if k not in VOLATILE_HEADERS))


def test_r289_unverified_paying_free_trial_identical(unverified_deck):
    """(i) Each gets the preview page, then byte-identical 402s."""
    client = unverified_deck
    nexts, sends = [], []
    for uid in (PAYING, FREE, TRIAL):
        page = _st(client, uid, 0)
        assert page.status_code == 200 and len(ids(page)) == PAGE
        nexts.append(_st(client, uid, PAGE))
        sends.append(client.post("/api/trades/propose", headers=_as(uid), json={}))
    for r in nexts + sends:
        assert r.status_code == 402 and r.get_json() == VERIFY_REQUIRED
    assert _shape(nexts[0]) == _shape(nexts[1]) == _shape(nexts[2])
    assert _shape(sends[0]) == _shape(sends[1]) == _shape(sends[2])


def test_r289_granted_account_answers_like_a_brand_new_one(unverified_deck):
    """(ii) Same page-1 allowance, same preview end, same 402."""
    client = unverified_deck
    seen = {}
    for uid in (GRANTED, NEW):
        rows = []
        for cursor in range(PAGE + 2):
            r = _st(client, uid, cursor)
            body = {k: v for k, v in (r.get_json() or {}).items() if k != "job_id"}
            rows.append((r.status_code, body))
        seen[uid] = rows
    assert seen[GRANTED] == seen[NEW]
    statuses = [s for s, _ in seen[NEW]]
    assert statuses == [200] * PAGE + [402, 402]          # the preview ends at cursor PAGE
    assert seen[NEW][PAGE][1] == VERIFY_REQUIRED
    assert len(seen[NEW][0][1]["cards"]) == PAGE


def test_r289_after_verifying_resolves_normally(unverified_deck):
    """(iii) Verified, the same call takes the usual path."""
    client = unverified_deck
    for uid in (PAYING, FREE, TRIAL, LAPSED, GRANTED, NEW):
        _st(client, uid, 0)                                 # spend the unverified preview
        with server._sessions_lock:
            server._sessions[f"tok-{uid}"]["verified"] = True
    gate = lambda uid: _st(client, uid, PAGE)
    assert gate(PAYING).status_code == 200
    assert gate(GRANTED).status_code == 200
    assert gate(FREE).get_json() == PREVIEW_USED
    assert gate(NEW).get_json() == PREVIEW_USED
    assert gate(TRIAL).get_json() == {"error": "pro_required", "gate": "trial_expired"}
    assert gate(LAPSED).get_json() == {"error": "pro_required", "gate": "lapsed"}
    r = client.post("/api/trades/propose", headers=_as(FREE), json={})
    assert r.get_json() == {"error": "pro_required", "gate": "never_trialed"}


def test_r289_real_deck_route_answers_unverified_identically(gate):
    """Today's decorated /status answers any unverified session 403
    verification_required before the deck: identical for every user_id."""
    client, *_ = gate
    shapes = []
    with server._sessions_lock:
        base = server._sessions[TOKEN]
        for uid in (PAYING, FREE):
            server._sessions[f"tok-{uid}"] = {**base, "user_id": uid, "verified": False}
    _rc_user(PAYING, [("INITIAL_PURCHASE", "NORMAL", 30)])
    try:
        for uid in (PAYING, FREE):
            r = status(client, 0, job_id=JOB_ID, headers=_as(uid))
            assert r.status_code == 403
            shapes.append(_shape(r))
    finally:
        with server._sessions_lock:
            for uid in (PAYING, FREE):
                server._sessions.pop(f"tok-{uid}", None)
    assert shapes[0] == shapes[1]


def test_deleted_and_exported_with_the_account(gate):
    """Alias handling is test_account_deletion_coverage's parametrized case."""
    pg.record_preview(ME, JOB_ID, 1)
    pg.record_preview("someone-else", "y", 1)
    assert "paywall_previews" in accounts._ADDITIONAL_PRIVATE_TABLES
    archive = accounts.export_user_data(ME)
    assert [r["deck_key"] for r in archive["tables"]["paywall_previews"]] == [JOB_ID]
    accounts.delete_user_data(ME)
    assert pg.preview_row(ME) is None and pg.preview_row("someone-else") is not None


# ── #368's P1 first-page store (flag trade.first_page_store on) ───────────
#
# /generate `page: 1` and /status cursors inside a page-served deck answer from
# the store (server._serve_trade_page / _trade_page_status_view), not from a
# job snapshot. The preview must cap and consume those serves too.

@pytest.fixture
def p1_enforcing(p1, spawned):
    client, engine, _sess = p1
    _config(engine, paywall_enforce_enabled=1.0, paywall_web_enforce_enabled=1.0,
            paywall_preview_pages=1.0)
    with patch.object(entl, "is_enabled", lambda k: k in BOTH_FLAGS):
        yield client


def test_p1_stored_first_page_is_previewed_and_consumed(p1_enforcing, monkeypatch):
    client = p1_enforcing
    job_id = p1mod.build_page()
    server._trade_jobs.clear()               # a restart: only the store can serve
    server._trade_jobs_by_key.clear()
    r = p1mod.generate(client, page=1)
    body = r.get_json()
    assert r.status_code == 200 and body["serve_source"] == "page"
    assert p1mod.ids(body["cards"]) == [f"p1-{i:03d}" for i in range(30)]
    row = pg.preview_row(p1mod.UID)
    assert (row["deck_key"], row["pages_served"]) == (job_id, 1)
    # A stored cursor inside the window is capped at the window's end.
    inside = p1mod.status(client, job_id, 10).get_json()
    assert p1mod.ids(inside["cards"]) == [f"p1-{i:03d}" for i in range(10, 30)]
    assert inside["cursor"] == 30
    # Page 2 (stored) and a new deck request are past the preview.
    assert p1mod.status(client, job_id, 30).get_json() == PREVIEW_USED
    assert p1mod.generate(client, page=1).get_json() == PREVIEW_USED
    # Swipes: a stored page-1 card passes the gate, a page-2 card doesn't.
    monkeypatch.setitem(server.app.view_functions, "swipe_trade", lambda **_kw: ("ok", 200))
    swipe = lambda tid: client.post("/api/trades/swipe", headers=p1mod.HEADERS,
                                    json={"trade_id": tid, "decision": "like"})
    assert swipe("p1-005").status_code == 200
    assert swipe("p1-030").get_json() == PREVIEW_USED


def test_p1_store_serves_are_untouched_without_a_preview(p1_enforcing):
    """An entitled user gets the stored pages exactly as before."""
    client = p1_enforcing
    entl.grant(p1mod.UID, "pro", source="manual_grant")
    job_id = p1mod.build_page()
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    assert len(p1mod.generate(client, page=1).get_json()["cards"]) == 30
    assert p1mod.ids(p1mod.status(client, job_id, 30).get_json()["cards"]) == [
        f"p1-{i:03d}" for i in range(30, 60)]
    assert pg.preview_row(p1mod.UID) is None
