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
verified account is gated; an unverified session never gets the preview
(R28.14); trial-expired keeps its reason; a concurrent second deck loses;
deletion and export include the new table; the window recorded at serve
time outlives the job (P3-1); every P2 deck path (P3-3).

Harness: E2's (test_trade_responses_small) real /generate and /status over
seeded jobs; in-memory SQLite; no network.
"""
import json
import re
import time
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, delete, event, func, insert, inspect, select, text

import backend.entitlements as entl
import backend.paywall_gate as pg
from backend import accounts, database as db, server, trade_service as ts
from backend.tests.test_fair_packages import harness, ME, LEAGUE, TOKEN  # noqa: F401 (fixture)
from backend.tests.test_trade_responses_small import JOB_ID, card, e2, seed_job  # noqa: F401
from backend.tests import test_trade_page_store as p1mod
from backend.tests.test_i1_serve_filter import live  # noqa: F401 (fixture)
from backend.tests.test_trade_page_store import p1, spawned  # noqa: F401 (fixtures)
from backend.tests import test_trade_pages_p2 as p2mod

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
NEVER_TRIALED = {"error": "pro_required", "gate": "never_trialed"}


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
    assert client.post(path, headers=MOBILE, json=body(0)).get_json() == NEVER_TRIALED  # nothing served yet
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
    """K0: GET /api/trades is outside the preview. Before any card was
    served the 402 is never_trialed (no preview was used); once page 1 was
    served, preview_used. Sabotage: answer preview_used without a row → red."""
    client, *_ = gate
    r = client.get(f"/api/trades?league_id={LEAGUE}", headers=MOBILE)
    assert r.status_code == 402 and r.get_json() == NEVER_TRIALED
    assert pg.preview_row(ME) is None
    assert status(client, 0).status_code == 200                   # spends the preview
    r = client.get(f"/api/trades?league_id={LEAGUE}", headers=MOBILE)
    assert r.status_code == 402 and r.get_json() == PREVIEW_USED


def test_knob_zero_blocks_the_first_request(gate):
    """K0: with the knob at 0 a user never served a card answers
    never_trialed; one whose preview was spent before the knob went to 0
    answers preview_used. Sabotage: answer preview_used without a row → red."""
    client, engine, _ = gate
    _config(engine, paywall_preview_pages=0.0)
    assert status(client, 0).get_json() == NEVER_TRIALED
    assert generate(client, page=1).get_json() == NEVER_TRIALED
    assert pg.preview_row(ME) is None
    pg.record_preview(ME, JOB_ID, 1, ["e2-trade-00000"])
    assert status(client, 0).get_json() == PREVIEW_USED
    assert generate(client, page=1).get_json() == PREVIEW_USED


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


def test_unverified_never_entitled_gets_no_preview(gate):
    """R28.14: settled before the preview. The route's own 403 where it wears
    the verified gate, else 402 verify_required; never a Preview."""
    ask = pg.DeckAsk(page_size=PAGE, job_id=JOB_ID, cursor=0)
    assert pg.verdict("/api/trades/status", "GET", ME, True, False,
                      route_verifies=True, ask=ask) is None
    assert pg.verdict("/api/trades/status", "GET", ME, True, False, ask=ask) == (
        402, {"error": "pro_required", "gate": "verify_required"})
    assert pg.preview_row(ME) is None


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


# ── Legal R28.9 / R28.14: unverified sessions never reveal subscriber status ─
#
# Every deck route wears the account-auth verified gate
# (@_gate_unverified_read/_write → 403 verification_required). The paywall
# hook settles an unverified session before any preview or entitlement read:
# it lets a decorated route answer, and 402s verify_required anywhere else.
# `unverified_deck` swaps /status for its undecorated view (functools.wraps'
# __wrapped__, which carries no gate mark) to exercise the hook's own 402;
# the real decorated route is pinned below. Every gated rule is covered in
# test_paywall_gate_unverified.py.

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
    """(i) No preview page: byte-identical 402s from the first request on."""
    client = unverified_deck
    firsts, sends = [], []
    for uid in (PAYING, FREE, TRIAL):
        firsts.append(_st(client, uid, 0))
        sends.append(client.post("/api/trades/propose", headers=_as(uid), json={}))
    for r in firsts + sends:
        assert r.status_code == 402 and r.get_json() == VERIFY_REQUIRED
    assert _shape(firsts[0]) == _shape(firsts[1]) == _shape(firsts[2])
    assert _shape(sends[0]) == _shape(sends[1]) == _shape(sends[2])


def test_r289_granted_account_answers_like_a_brand_new_one(unverified_deck):
    """(ii) The same 402 at every cursor, and neither writes a preview row."""
    client = unverified_deck
    seen = {}
    for uid in (GRANTED, NEW):
        seen[uid] = [_shape(_st(client, uid, cursor)) for cursor in range(PAGE + 2)]
    assert seen[GRANTED] == seen[NEW]
    assert {s[0] for s in seen[NEW]} == {402}
    assert pg.preview_row(GRANTED) is None and pg.preview_row(NEW) is None


def test_r289_after_verifying_resolves_normally(unverified_deck):
    """(iii) Verified, the same call takes the usual path; the unverified
    requests spent nothing, so a never-entitled account still has its
    preview."""
    client = unverified_deck
    for uid in (PAYING, FREE, TRIAL, LAPSED, GRANTED, NEW):
        assert _st(client, uid, 0).get_json() == VERIFY_REQUIRED
        with server._sessions_lock:
            server._sessions[f"tok-{uid}"]["verified"] = True
    gate = lambda uid, cursor=PAGE: _st(client, uid, cursor)
    assert gate(PAYING).status_code == 200
    assert gate(GRANTED).status_code == 200
    assert gate(FREE, 0).status_code == 200 and len(ids(gate(FREE, 0))) == PAGE
    assert gate(FREE).get_json() == PREVIEW_USED
    assert gate(NEW).get_json() == NEVER_TRIALED                 # nothing served (K0)
    assert gate(TRIAL).get_json() == {"error": "pro_required", "gate": "trial_expired"}
    assert gate(LAPSED).get_json() == {"error": "pro_required", "gate": "lapsed"}
    r = client.post("/api/trades/propose", headers=_as(FREE), json={})
    assert r.get_json() == {"error": "pro_required", "gate": "never_trialed"}


def test_r289_real_deck_route_answers_unverified_identically(gate):
    """The decorated /status answers any unverified session 403
    verification_required (the hook lets it through): identical for every
    user_id, a preview row or not, and nothing is recorded."""
    client, *_ = gate
    shapes = []
    pg.record_preview(FREE, "job-held", 1, ["e2-trade-00000"])
    with server._sessions_lock:
        base = server._sessions[TOKEN]
        for uid in (PAYING, FREE, NEW):
            server._sessions[f"tok-{uid}"] = {**base, "user_id": uid, "verified": False}
    _rc_user(PAYING, [("INITIAL_PURCHASE", "NORMAL", 30)])
    try:
        for uid in (PAYING, FREE, NEW):
            r = status(client, 0, job_id=JOB_ID, headers=_as(uid))
            assert r.status_code == 403 and r.get_json() == {"error": "verification_required"}
            shapes.append(_shape(r))
    finally:
        with server._sessions_lock:
            for uid in (PAYING, FREE, NEW):
                server._sessions.pop(f"tok-{uid}", None)
    assert shapes[0] == shapes[1] == shapes[2]
    assert pg.preview_row(PAYING) is None and pg.preview_row(NEW) is None
    assert pg.preview_row(FREE)["deck_key"] == "job-held"


def test_deleted_and_exported_with_the_account(gate):
    """Alias handling is test_account_deletion_coverage's parametrized case.
    The window's trade ids (P3-1) are exported with the row: they're the
    user's own deck, not a credential."""
    pg.record_preview(ME, JOB_ID, 1, ["e2-trade-00001", "e2-trade-00000"])
    pg.record_preview("someone-else", "y", 1)
    assert "paywall_previews" in accounts._ADDITIONAL_PRIVATE_TABLES
    archive = accounts.export_user_data(ME)
    assert [r["deck_key"] for r in archive["tables"]["paywall_previews"]] == [JOB_ID]
    assert [r["window_trade_ids"] for r in archive["tables"]["paywall_previews"]] == [
        '["e2-trade-00000", "e2-trade-00001"]']
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


# ── #369's P2 next pages by deck id (/status?deck=D&cursor=K) ─────────────

def _deck(client, deck, cursor, headers=None):
    return p2mod.deck_status(client, deck, cursor) if headers is None else client.get(
        f"/api/trades/status?deck={deck}&cursor={cursor}", headers=headers)


def test_p2_deck_pages_hold_the_preview(p1_enforcing):
    client = p1_enforcing
    deck = p2mod.build_deck()
    p2mod.restart()
    first = p1mod.generate(client, page=1).get_json()
    assert first["deck_id"] == deck and len(first["cards"]) == 30
    assert pg.preview_row(p1mod.UID)["deck_key"] == deck
    again = _deck(client, deck, 0).get_json()                    # page 1 by deck id
    assert p1mod.ids(again["cards"]) == p2mod.p1_ids(0, 30) and again["deck_id"] == deck
    inside = _deck(client, deck, 10).get_json()                  # capped at the window
    assert p1mod.ids(inside["cards"]) == p2mod.p1_ids(10, 30) and inside["cursor"] == 30
    assert _deck(client, deck, 30).get_json() == PREVIEW_USED     # page 2 by deck id
    assert _deck(client, "another-deck", 0).get_json() == PREVIEW_USED


def test_p2_rebase_onto_a_newer_deck_is_a_different_deck(p1_enforcing):
    client = p1_enforcing
    deck = p2mod.build_deck()
    p2mod.restart()
    assert len(p1mod.generate(client, page=1).get_json()["cards"]) == 30
    p2mod.restart()                                               # drop the rebuild it kicked
    newer = p2mod.build_deck()                                    # its row replaces deck's
    p2mod.restart()
    assert newer != deck and p1mod.stored()["deck_job_id"] == newer
    r = _deck(client, deck, 0)                                    # P2 would rebase onto `newer`
    assert r.status_code == 402 and r.get_json() == PREVIEW_USED
    assert pg.preview_row(p1mod.UID)["deck_key"] == deck


def test_p2_entitled_user_pages_by_deck_unaffected(p1_enforcing):
    client = p1_enforcing
    entl.grant(p1mod.UID, "pro", source="manual_grant")
    deck = p2mod.build_deck()
    assert p1mod.ids(_deck(client, deck, 30).get_json()["cards"]) == p2mod.p1_ids(30, 60)
    assert pg.preview_row(p1mod.UID) is None


def test_p2_unverified_session_gets_verify_required_and_no_preview(p1_enforcing, monkeypatch):
    """R28.14 on the deck-id path (/status swapped for its undecorated view:
    the account-auth read gate would 403 an unverified session first). A
    subscriber's user_id or not, 402 verify_required at once, nothing served
    and nothing recorded."""
    client = p1_enforcing
    view = server.app.view_functions["trade_job_status"]
    monkeypatch.setitem(server.app.view_functions, "trade_job_status", view.__wrapped__)
    deck = p2mod.build_deck()
    hdr = {"X-Session-Token": "p2-unverified"}
    with server._sessions_lock:
        server._sessions["p2-unverified"] = {**server._sessions[p1mod.TOKEN], "verified": False}
    try:
        answers = [_shape(_deck(client, deck, 0, hdr))]
        entl.grant(p1mod.UID, "pro", source="manual_grant")          # a subscriber's user_id
        answers.append(_shape(_deck(client, deck, 0, hdr)))
        assert answers[0] == answers[1] and answers[0][0] == 402
        assert _deck(client, deck, 0, hdr).get_json() == VERIFY_REQUIRED
        assert _deck(client, "another-deck", 0, hdr).get_json() == VERIFY_REQUIRED
    finally:
        with server._sessions_lock:
            server._sessions.pop("p2-unverified", None)
    assert pg.preview_row(p1mod.UID) is None


# ── P3-1: the preview window outlives the job ─────────────────────────────
#
# With trade.first_page_store off (the prod default), the swipe check read only
# the live job: after 4 h of job retention or any deploy, swipes on held page-1
# cards answered 402. paywall_previews.window_trade_ids now records the window
# at each serve, and the check falls back to it once the deck is gone.

def _swipe(client, i, path="/api/trades/swipe"):
    return client.post(path, headers=MOBILE, json={"trade_id": f"e2-trade-{i:05d}",
                                                   "decision": "pass", "reason": "value"})


def _evict():
    """The 4 h job retention, or a deploy: the job is gone from the process."""
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()


@pytest.mark.parametrize("path", ["/api/trades/swipe", "/api/trades/pass-reason"])
def test_p31_window_persists_across_the_jobs_disappearance(gate, swipe_ok, path):
    client, *_ = gate
    assert not server._trade_page_store_enabled()                 # the prod default
    assert status(client, 0).status_code == 200
    window = [f"e2-trade-{i:05d}" for i in range(PAGE)]
    assert json.loads(pg.preview_row(ME)["window_trade_ids"]) == window
    _evict()
    assert server._paywall_page_trade_ids(ME, JOB_ID, PAGE) is None
    assert _swipe(client, 0, path).status_code == 200              # a held page-1 card
    assert _swipe(client, PAGE - 1, path).status_code == 200
    assert _swipe(client, PAGE, path).get_json() == PREVIEW_USED   # outside the window
    assert status(client, PAGE).get_json() == PREVIEW_USED          # page 2 still 402
    assert generate(client, page=1).get_json() == PREVIEW_USED      # a new deck too


def test_p31_the_live_window_decides_while_the_job_is_held(gate, swipe_ok):
    """The stored window is only the fallback: while the job is held, a card
    the live window doesn't hold is 402 even if the stored window lists it."""
    client, engine, _ = gate
    status(client, 0)
    with engine.begin() as conn:
        conn.execute(db.paywall_previews_table.update().values(
            window_trade_ids=json.dumps(["e2-trade-00007"])))
    assert _swipe(client, 7).get_json() == PREVIEW_USED
    assert _swipe(client, 0).status_code == 200
    _evict()
    assert _swipe(client, 7).status_code == 200
    assert _swipe(client, 0).get_json() == PREVIEW_USED


def test_p31_a_row_from_before_the_column_fails_closed_once_the_job_is_gone(gate, swipe_ok):
    client, engine, _ = gate
    status(client, 0)
    with engine.begin() as conn:
        conn.execute(db.paywall_previews_table.update().values(window_trade_ids=None))
    assert _swipe(client, 0).status_code == 200                    # the live job still holds it
    _evict()
    assert _swipe(client, 0).get_json() == PREVIEW_USED


def test_p31_the_window_follows_a_running_job_and_only_its_deck():
    """record_preview rewrites the window when a later serve of the same deck
    sees a different one (a running job publishing); another deck never
    touches it."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    with patch.object(db, "engine", engine):
        assert pg.record_preview("u", "d", 1, ["t1"])
        assert pg.stored_window(pg.preview_row("u")) == {"t1"}
        assert pg.record_preview("u", "d", 1, ["t2", "t1", None])
        assert pg.preview_row("u")["window_trade_ids"] == '["t1", "t2"]'
        assert pg.record_preview("u", "other", 1, ["z"]) is False
        assert pg.record_preview("u", "d", 1) is True                 # no window: unchanged
        row = pg.preview_row("u")
        assert (row["deck_key"], row["window_trade_ids"]) == ("d", '["t1", "t2"]')
        for bad in (None, "", "not json", "{}", '[1, "t3"]'):
            assert pg.stored_window({"window_trade_ids": bad}) <= {"t3"}


def test_p31_window_column_reaches_an_existing_table_through_migrate_db():
    """The additive path: a paywall_previews table created before P3-1 gets
    the nullable column from _migrate_db's migration_cols, its old rows NULL."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE paywall_previews"))
        conn.execute(text("CREATE TABLE paywall_previews (user_id VARCHAR PRIMARY KEY, "
                          "deck_key VARCHAR NOT NULL, pages_served INTEGER NOT NULL, "
                          "first_served_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL)"))
        conn.execute(text("INSERT INTO paywall_previews VALUES ('old', 'job', 1, 'x', 'x')"))
    with patch.object(db, "engine", engine):
        db._migrate_db()
        cols = {c["name"]: c for c in inspect(engine).get_columns("paywall_previews")}
        assert "window_trade_ids" in cols and cols["window_trade_ids"]["nullable"]
        assert pg.preview_row("old")["window_trade_ids"] is None
        db._migrate_db()                                           # idempotent
    assert ("paywall_previews", "window_trade_ids", "TEXT") in _migration_cols()


def _migration_cols():
    import inspect as _inspect
    src = _inspect.getsource(db._migrate_db)
    return [tuple(m) for m in re.findall(r'\(\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\s*\)', src)]


# ── P3-3: the preview on every P2 deck path ───────────────────────────────
#
# test_trade_pages_p2.DECK_PATHS: (a) D's stored pages, (b) D's live job past
# them, (c) a rebase onto the scope's newer deck from a row or from a job.

def _swipe_p1(client, trade_id):
    return client.post("/api/trades/swipe", headers=p1mod.HEADERS,
                       json={"trade_id": trade_id, "decision": "like"})


@pytest.mark.parametrize("path", sorted(p2mod.DECK_PATHS))
def test_p33_every_deck_path_is_capped_and_recorded_against_the_served_deck(
        p1, p1_enforcing, monkeypatch, path):
    """With the window wide enough for the path's cursor (4 pages = 120 raw
    cards): served cards sit inside the served deck's window, the preview is
    recorded against that deck with its window, swipes hold to the window,
    and they still do once the deck is gone from the process (P3-1)."""
    client, engine, _ = p1
    target, cursor = p2mod._deck_path(engine, path)
    _config(engine, paywall_preview_pages=4.0)
    limit = 4 * server._trade_page_size()
    body = _deck(client, target, cursor).get_json()
    served = body["deck_id"]
    assert body["cards"] and ("rebased" in body) == path.startswith("rebased")
    window = server._paywall_page_trade_ids(p1mod.UID, served, limit)
    assert set(p1mod.ids(body["cards"])) <= window and body["cursor"] <= limit
    row = pg.preview_row(p1mod.UID)
    assert row["deck_key"] == served
    assert row["pages_served"] == pg.Preview(4, server._trade_page_size()).pages_for(body["cursor"])
    assert pg.stored_window(row) == window
    monkeypatch.setitem(server.app.view_functions, "swipe_trade", lambda **_kw: ("ok", 200))
    first = body["cards"][0]["trade_id"]
    assert _swipe_p1(client, first).status_code == 200
    assert _swipe_p1(client, "p1-999").get_json() == PREVIEW_USED
    assert _deck(client, "another-deck", 0).get_json() == PREVIEW_USED
    p2mod.restart()
    with engine.begin() as conn:
        conn.execute(delete(db.trade_page_store_table))
    assert server._paywall_page_trade_ids(p1mod.UID, served, limit) is None
    assert _swipe_p1(client, first).status_code == 200
    assert _swipe_p1(client, "p1-999").get_json() == PREVIEW_USED


@pytest.mark.parametrize("path", sorted(p2mod.DECK_PATHS))
def test_p33_every_deck_path_at_its_own_cursor_with_the_default_knob(p1, p1_enforcing, path):
    """Knob 1 (30 raw cards): the stored (cursor 30) and live (cursor 90)
    paths are past the window → 402 with nothing recorded; the two rebases
    (cursor 0) serve the newer deck's first page and record THAT deck."""
    client, engine, _ = p1
    target, cursor = p2mod._deck_path(engine, path)
    r = _deck(client, target, cursor)
    if cursor >= server._trade_page_size():
        assert r.status_code == 402 and r.get_json() == NEVER_TRIALED   # nothing served (K0)
        assert pg.preview_row(p1mod.UID) is None
        return
    body = r.get_json()
    assert r.status_code == 200 and body["rebased"] is True and body["deck_id"] != target
    assert body["cards"] and body["cursor"] <= server._trade_page_size()
    assert pg.preview_row(p1mod.UID)["deck_key"] == body["deck_id"]
    assert _deck(client, body["deck_id"], 0).status_code == 200    # the recorded deck re-serves
    assert _deck(client, body["deck_id"], 30).get_json() == PREVIEW_USED


# ── P3-4: no DB write while dark ──────────────────────────────────────────

DARK_STATES = {
    # name: (flags on, paywall_enforce_enabled)
    "flags_off": ((), 1.0),
    "knob_zero": (BOTH_FLAGS, 0.0),
}
PAYWALL_SQL = re.compile(r"\bpaywall_previews\b")
BILLING_WRITE_SQL = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE)\b.*\b(entitlements|subscription_events)\b", re.S | re.I)


@pytest.fixture
def statements_on(request):
    seen = []

    def attach(engine):
        listener = lambda conn, cursor, statement, *a: seen.append(statement)
        event.listen(engine, "before_cursor_execute", listener)
        request.addfinalizer(lambda: event.remove(engine, "before_cursor_execute", listener))
        return seen
    return attach


class _Spy:
    def __init__(self, real):
        self.real, self.calls = real, 0

    def __call__(self, *a, **kw):
        self.calls += 1
        return self.real(*a, **kw)


def _assert_no_paywall_write(engine, seen, recorded):
    assert recorded.calls == 0
    assert [s for s in seen if PAYWALL_SQL.search(s)] == []
    assert [s for s in seen if BILLING_WRITE_SQL.search(s)] == []
    with engine.begin() as conn:
        assert conn.execute(select(func.count()).select_from(db.paywall_previews_table)).scalar() == 0


@pytest.mark.parametrize("dark", sorted(DARK_STATES))
def test_p34_dark_deck_routes_write_nothing_to_the_paywall(e2, monkeypatch, statements_on, dark):
    """Enforcement dark: a never-entitled, verified mobile user walks every
    gated deck route, past the preview window, and swipes and passes outside
    it: full decks, no 402, zero paywall_previews statements (no read, no
    write), no billing write, record_preview never called."""
    client, engine, _ = e2
    flags, knob = DARK_STATES[dark]
    monkeypatch.setitem(ts._cfg, "trade_page_size", float(PAGE))
    _config(engine, paywall_enforce_enabled=knob, paywall_preview_pages=1.0,
            paywall_web_enforce_enabled=1.0)
    seed_job([card(i) for i in range(12)])
    recorded = _Spy(pg.record_preview)
    seen = statements_on(engine)
    with patch.object(entl, "is_enabled", lambda k: k in flags), \
            patch.object(pg, "record_preview", recorded):
        assert not entl.is_enforcing()
        responses = [status(client, 0), status(client, PAGE), status(client),
                     generate(client, page=1), generate(client),
                     client.get(f"/api/trades?league_id={LEAGUE}", headers=MOBILE),
                     _swipe(client, 0), _swipe(client, PAGE + 1),
                     _swipe(client, PAGE + 2, "/api/trades/pass-reason")]
    assert all(r.status_code != 402 for r in responses), [r.status_code for r in responses]
    assert len(ids(responses[2])) == 12                             # the uncapped deck
    assert len(ids(responses[1])) == PAGE                           # page 2 served
    _assert_no_paywall_write(engine, seen, recorded)


@pytest.mark.parametrize("dark", sorted(DARK_STATES))
def test_p34_dark_page_store_and_deck_paths_write_nothing(p1, spawned, statements_on, dark):
    """The same on #368's stored page and #369's deck-id pages."""
    client, engine, _ = p1
    flags, knob = DARK_STATES[dark]
    _config(engine, paywall_enforce_enabled=knob, paywall_preview_pages=1.0,
            paywall_web_enforce_enabled=1.0)
    deck = p2mod.build_deck()
    p2mod.restart()
    recorded = _Spy(pg.record_preview)
    seen = statements_on(engine)
    with patch.object(entl, "is_enabled", lambda k: k in flags), \
            patch.object(pg, "record_preview", recorded):
        first = p1mod.generate(client, page=1)
        later = [_deck(client, deck, cursor) for cursor in (0, 30, 60)]
    assert first.status_code == 200 and len(first.get_json()["cards"]) == 30
    assert [len(r.get_json()["cards"]) for r in later] == [30, 30, 30]
    _assert_no_paywall_write(engine, seen, recorded)
