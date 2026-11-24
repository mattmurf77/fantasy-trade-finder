"""League pass at the global paywall gate (paywall_gate.verdict's coverage
check, server._paywall_gate_hook, the league-match check).

Spec: docs/plans/monetization/league-pass/lld.md §4, §9, §11; prd.md R1, R2,
R8, R9, R40.

Covers:
  (1) a covered member's gated request passes, on every resolver kind's
      representative rule, and spends no preview: the handler sees no
      g.paywall_preview and no paywall_previews row is written, while the
      same never-entitled user without a pass is handed the preview
  (2) the same member in another league gets the ordinary 402, the exact
      body a user with no pass gets
  (3) a request naming the covered league while acting on another gets 402:
      an `active` rule whose body names the pass league from another session
      league; a `session` rule (Win Now) likewise; the league-match check in
      _require_initialized_session when the session league moved after the
      hook (the session-switch race); GET /api/trades held to the pass league
  (4) an unverified session gets the same answer with and without a pass,
      and coverage is never read for it (R8)
  (5) flag off: coverage and the resolvers are never called, and every
      response is byte-identical with and without a pass (R40)
  (6) a comp pass covers; an expired comp does not
  (7) the Sleeper co-owner: covered through the session's league identity in
      its active league only, never in another league
  (8) league_pass_coverage_used: first per user, league and UTC day, prop
      `family`; an emitter failure never fails the request

Gated views are stubbed (each reports what the hook left on `g`), so
"through" reads as 200 without running the trade engine. In-memory SQLite.
"""

import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import g, jsonify
from sqlalchemy import select

import backend.database as db_module
import backend.entitlements as entl
import backend.league_pass as lp
import backend.paywall_gate as pg
import backend.server as server
from backend.tests.support import league_pass_world as w

L, L2 = "lg-pass", "lg-free"
BUYER, MATE, CO = "u-buyer", "u-mate", "acct_co_owner"
TOKEN, UNVERIFIED, CO_TOKEN = "lpg-verified", "lpg-unverified", "lpg-co"
MOBILE = {"X-Device": "iphone", "X-OS-Version": "18.1", "X-App-Version": "1.13.2"}
NEVER = {"error": "pro_required", "gate": "never_trialed"}
BOTH = ("monetize.entitlements", "monetize.paywall")

STUBBED = ("generate_trades", "propose_trade_to_sleeper", "trade_job_status",
           "disposition_trade_match", "win_now_search_route", "overhaul_active_route")


@pytest.fixture()
def eng():
    engine = w.make_engine()
    with engine.begin() as conn:
        w.league(conn, L, total_rosters=12)
        w.league(conn, L2, total_rosters=12)
        for lid in (L, L2):
            w.member(conn, lid, BUYER)
            w.member(conn, lid, MATE)
        w.ent_row(conn, BUYER)
        w.knob(conn, "paywall_enforce_enabled", 1.0)
        w.knob(conn, "paywall_preview_pages", 1.0)
    with patch.object(db_module, "engine", engine):
        yield engine


def _add_pass(eng, **kw):
    with eng.begin() as conn:
        return w.pass_row(conn, L, **({"buyer": BUYER} | kw))


@pytest.fixture()
def flag(monkeypatch):
    """monetize.league_pass, on by default; tests flip state['on']."""
    state = {"on": True}
    real = server.is_enabled
    monkeypatch.setattr(pg, "is_enabled", lambda k: state["on"] and k == lp.FLAG)
    monkeypatch.setattr(server, "is_enabled",
                        lambda k: (state["on"] if k == lp.FLAG else real(k)))
    return state


def _seen():
    return jsonify({"pass_league": g.get("paywall_pass_league"),
                    "preview": g.get("paywall_preview") is not None})


@pytest.fixture()
def client(eng, flag, monkeypatch):
    for ep in STUBBED:
        monkeypatch.setitem(server.app.view_functions, ep, lambda **_kw: _seen())
    server.app.config["TESTING"] = True
    sessions = {
        TOKEN: {"user_id": MATE, "verified": True, "league": SimpleNamespace(league_id=L),
                "players": [], "trade_svc": object(), "last_active": time.time()},
        UNVERIFIED: {"user_id": MATE, "league": SimpleNamespace(league_id=L),
                     "players": [], "trade_svc": object(), "last_active": time.time()},
        CO_TOKEN: {"user_id": CO, "league_user_id": MATE, "verified": True,
                   "league": SimpleNamespace(league_id=L), "players": [],
                   "trade_svc": object(), "last_active": time.time()},
    }
    with server._sessions_lock:
        server._sessions.update(sessions)
    try:
        with patch.object(entl, "is_enabled", lambda k: k in BOTH):
            yield server.app.test_client()
    finally:
        with server._sessions_lock:
            for t in sessions:
                server._sessions.pop(t, None)
        pg._gate_hits.clear()


def _session_league(token, league_id):
    with server._sessions_lock:
        server._sessions[token]["league"] = SimpleNamespace(league_id=league_id)


def _call(c, method, path, token=TOKEN, body=None):
    return c.open(path, method=method, headers={"X-Session-Token": token, **MOBILE},
                  json=body)


def _previews(eng):
    with eng.connect() as conn:
        return conn.execute(select(db_module.paywall_previews_table)).fetchall()


# ── (1) covered → through, no preview ──────────────────────────────────────

@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/trades/generate", {"league_id": L}),        # active
    ("POST", "/api/trades/generate", None),                    # active, session league
    ("POST", "/api/trades/propose", {"league_id": L}),         # body
    ("POST", "/api/win-now/search", {"league_id": L}),         # session
    ("GET", "/api/overhauls", None),                           # session
])
def test_covered_request_passes_and_spends_no_preview(eng, client, method, path, body):
    _add_pass(eng)
    r = _call(client, method, path, body=body)
    assert r.status_code == 200
    assert r.get_json() == {"pass_league": L, "preview": False}
    assert _previews(eng) == []


def test_without_a_pass_the_same_request_gets_the_preview(eng, client):
    r = _call(client, "POST", "/api/trades/generate", body={"league_id": L})
    assert r.get_json() == {"pass_league": None, "preview": True}


def test_covered_match_disposition_and_status(eng, client):
    _add_pass(eng)
    from sqlalchemy import insert
    with eng.begin() as conn:
        match_id = conn.execute(insert(db_module.trade_matches_table).values(
            league_id=L, user_a_id=MATE, user_b_id=BUYER, user_a_give="[]",
            user_a_receive="[]")).inserted_primary_key[0]
    r = _call(client, "POST", f"/api/trades/matches/{match_id}/disposition", body={})
    assert r.get_json()["pass_league"] == L
    with server._trade_jobs_lock:
        server._trade_jobs["lpg-job"] = {"key": (MATE, L, "1qb_ppr")}
    try:
        r = _call(client, "GET", "/api/trades/status?job_id=lpg-job")
        assert r.get_json() == {"pass_league": L, "preview": False}
    finally:
        with server._trade_jobs_lock:
            server._trade_jobs.pop("lpg-job", None)


# ── (2) the same member in another league ──────────────────────────────────

@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/trades/propose", {"league_id": L2}),
    ("POST", "/api/win-now/search", {"league_id": L2}),
])
def test_other_league_gets_the_ordinary_402(eng, client, method, path, body):
    _session_league(TOKEN, L2)
    without = _call(client, method, path, body=body)
    _add_pass(eng)
    with_pass = _call(client, method, path, body=body)
    assert (with_pass.status_code, with_pass.get_json()) == (402, NEVER)
    assert with_pass.data == without.data


def test_other_league_deck_request_is_not_covered(eng, client):
    """In L2 the never-entitled member is on the ordinary path: the preview,
    not the pass."""
    _add_pass(eng)
    _session_league(TOKEN, L2)
    r = _call(client, "POST", "/api/trades/generate", body={"league_id": L2})
    assert r.get_json() == {"pass_league": None, "preview": True}


# ── (3) naming the covered league while acting on another ──────────────────

def test_body_naming_the_pass_league_from_another_session_league(eng, client):
    """generate (`active`) and Win Now (`session`) act on the session's L2:
    naming L in the body is not covered. generate falls to the ordinary
    path (the never-entitled member's preview), Win Now to the 402."""
    _add_pass(eng)
    _session_league(TOKEN, L2)
    r = _call(client, "POST", "/api/trades/generate", body={"league_id": L})
    assert r.get_json() == {"pass_league": None, "preview": True}
    r = _call(client, "POST", "/api/win-now/search", body={"league_id": L})
    assert (r.status_code, r.get_json()) == (402, NEVER)


def test_league_match_check_refuses_a_session_moved_after_the_hook(eng, client, monkeypatch):
    """The hook resolved L (covered); by the time the handler reads the
    session it is in L2. _require_initialized_session's league-match check
    answers the ordinary 402."""
    _add_pass(eng)
    monkeypatch.setitem(server.app.view_functions, "win_now_search_route",
                        lambda **_kw: jsonify(str(server._require_initialized_session()
                                                  ["league"].league_id)))
    real = server._paywall_pass_league

    def resolve_then_switch(rule, sess, ask):
        out = real(rule, sess, ask)
        _session_league(TOKEN, L2)
        return out
    monkeypatch.setattr(server, "_paywall_pass_league", resolve_then_switch)
    r = _call(client, "POST", "/api/win-now/search", body={"league_id": L})
    assert (r.status_code, r.get_json()) == (402, NEVER)


def test_league_match_check_lets_the_pass_league_through(eng, client, monkeypatch):
    _add_pass(eng)
    monkeypatch.setitem(server.app.view_functions, "win_now_search_route",
                        lambda **_kw: jsonify(str(server._require_initialized_session()
                                                  ["league"].league_id)))
    r = _call(client, "POST", "/api/win-now/search", body={"league_id": L})
    assert (r.status_code, r.get_json()) == (200, L)


def test_confirm_pass_league_is_a_noop_without_a_pass():
    with server.app.test_request_context("/api/trades/generate", method="POST"):
        server._confirm_pass_league("anything")     # no g.paywall_pass_league
        g.paywall_pass_league = L
        server._confirm_pass_league(L)
        with pytest.raises(Exception) as exc:
            server._confirm_pass_league(L2)
        assert exc.value.response.status_code == 402


def test_get_trades_is_held_to_the_pass_league(eng, client, monkeypatch):
    """GET /api/trades without league_id lists every league's cards; a
    request a pass let through lists only the pass league's."""
    _add_pass(eng)
    asked = []

    class Svc:
        _players = {}

        def get_pending_trades(self, user_id, league_id):
            asked.append(league_id)
            return []
    with server._sessions_lock:
        server._sessions[TOKEN]["trade_svc"] = Svc()
    monkeypatch.setattr(server, "_capture_trade_significance", lambda: (None,))
    for path in ("/api/trades", f"/api/trades?league_id={L}"):
        r = _call(client, "GET", path)
        assert r.status_code == 200, r.data
    assert asked == [L, L]
    # flag off (and account-level pro would be the same): the handler's own filter
    with patch.object(pg, "is_enabled", lambda k: False):
        with eng.begin() as conn:
            w.ent_row(conn, MATE, product="ftf_pro_annual", source="apple_iap")
        _call(client, "GET", "/api/trades")
    assert asked[-1] is None


# ── (4) unverified: the same answer with and without a pass ────────────────

@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/trades/generate", {"league_id": L}),
    ("POST", "/api/trades/propose", {"league_id": L}),
    ("GET", "/api/overhauls", None),
])
def test_unverified_answer_does_not_depend_on_a_pass(eng, client, monkeypatch,
                                                      method, path, body):
    without = _call(client, method, path, UNVERIFIED, body)
    _add_pass(eng)
    calls = []
    real = lp.covers
    monkeypatch.setattr(lp, "covers", lambda *a: calls.append(a) or real(*a))
    with_pass = _call(client, method, path, UNVERIFIED, body)
    assert (with_pass.status_code, with_pass.data) == (without.status_code, without.data)
    assert with_pass.status_code == 402
    assert with_pass.get_json()["gate"] == "verify_required"
    assert calls == []


# ── (5) flag off: byte-identical, nothing read ─────────────────────────────

FLAG_OFF_REQUESTS = [
    ("POST", "/api/trades/generate", {"league_id": L}),
    ("POST", "/api/trades/propose", {"league_id": L}),
    ("GET", "/api/trades/status?job_id=x", None),
    ("GET", "/api/overhauls", None),
    ("GET", "/api/me/entitlements", None),
    ("GET", "/api/paywall/config?caps=league_pass", None),
]


def test_flag_off_is_byte_identical_and_reads_no_coverage(eng, client, flag, monkeypatch):
    flag["on"] = False
    calls = []    # recorded, not raised: the hook swallows resolver errors

    def never(*a, **_kw):
        calls.append(a)
        raise AssertionError("read with monetize.league_pass off")
    for name in ("covers", "passes_for", "covered_members", "is_member"):
        monkeypatch.setattr(lp, name, never)
    monkeypatch.setattr(pg, "resolve_league", never)
    monkeypatch.setattr(server, "_paywall_job_league", never)
    with patch.object(server, "_paywall_now",
                      lambda: server._PAYWALL_PRICE_RISE_AT), \
         patch.object(server, "is_enabled",
                      lambda k: k == "monetize.paywall"):
        without = [_call(client, m, p, body=b) for m, p, b in FLAG_OFF_REQUESTS]
        _add_pass(eng)
        with_pass = [_call(client, m, p, body=b) for m, p, b in FLAG_OFF_REQUESTS]
    assert calls == []
    for (m, p, _b), a, b in zip(FLAG_OFF_REQUESTS, without, with_pass):
        assert (a.status_code, a.data) == (b.status_code, b.data), p
    by_path = {p: r for (_m, p, _b), r in zip(FLAG_OFF_REQUESTS, with_pass)}
    assert by_path["/api/trades/generate"].get_json() == {"pass_league": None, "preview": True}
    assert by_path["/api/trades/propose"].get_json() == NEVER
    assert "league_passes" not in by_path["/api/me/entitlements"].get_json()
    assert "league_pass" not in by_path["/api/paywall/config?caps=league_pass"].get_json()


def test_flag_off_hook_issues_the_same_queries(eng, client, flag):
    """The hook's SQL with the flag off is the same with and without a pass
    in the league (no coverage or resolver query is ever issued)."""
    from sqlalchemy import event
    flag["on"] = False
    stmts = []
    event.listen(eng, "before_cursor_execute",
                 lambda conn, cur, stmt, params, ctx, many: stmts.append(stmt))
    _call(client, "POST", "/api/trades/propose", body={"league_id": L})
    before, stmts[:] = list(stmts), []
    _add_pass(eng)
    stmts[:] = []
    pg._gate_hits.clear()          # so the 402's paywall_gate_hit is written again
    _call(client, "POST", "/api/trades/propose", body={"league_id": L})
    assert stmts == before
    assert not any("league_pass" in s for s in stmts)


# ── (6) comp passes ────────────────────────────────────────────────────────

def test_comp_pass_covers_and_an_expired_comp_does_not(eng, client):
    pass_id = _add_pass(eng, buyer=None, origin="comp", comp_days=30)
    r = _call(client, "POST", "/api/trades/propose", body={"league_id": L})
    assert r.get_json()["pass_league"] == L
    with eng.begin() as conn:
        conn.execute(db_module.league_passes_table.update()
                     .where(db_module.league_passes_table.c.id == pass_id)
                     .values(comp_expires_at=w.iso(-1)))
    r = _call(client, "POST", "/api/trades/propose", body={"league_id": L})
    assert (r.status_code, r.get_json()) == (402, NEVER)


# ── (7) the Sleeper co-owner ───────────────────────────────────────────────

def test_co_owner_is_covered_through_the_league_identity(eng, client):
    """CO is not in league_members (only the roster's primary owner, MATE,
    is); the session's league identity is."""
    _add_pass(eng)
    r = _call(client, "POST", "/api/trades/propose", CO_TOKEN, {"league_id": L})
    assert r.get_json()["pass_league"] == L
    r = _call(client, "GET", "/api/overhauls", CO_TOKEN)
    assert r.get_json()["pass_league"] == L


def test_co_owner_identity_is_tried_only_in_the_active_league(eng, client):
    _add_pass(eng)
    _session_league(CO_TOKEN, L2)
    r = _call(client, "POST", "/api/trades/propose", CO_TOKEN, {"league_id": L})
    assert (r.status_code, r.get_json()) == (402, NEVER)


def test_co_owner_without_a_league_identity_is_not_covered(eng, client):
    _add_pass(eng)
    with server._sessions_lock:
        server._sessions[CO_TOKEN].pop("league_user_id")
    r = _call(client, "POST", "/api/trades/propose", CO_TOKEN, {"league_id": L})
    assert (r.status_code, r.get_json()) == (402, NEVER)


# ── (8) league_pass_coverage_used ──────────────────────────────────────────

def test_coverage_used_first_per_user_league_and_day(eng, client):
    _add_pass(eng)
    _call(client, "POST", "/api/trades/propose", body={"league_id": L})
    _call(client, "GET", "/api/overhauls")
    _call(client, "POST", "/api/trades/propose", CO_TOKEN, {"league_id": L})
    rows = w.events(eng, pg.COVERAGE_USED_EVENT)
    assert rows == [(MATE, {"family": "send"}, L), (CO, {"family": "send"}, L)]


def test_coverage_used_failure_never_fails_the_request(eng, client, monkeypatch):
    _add_pass(eng)

    def boom(*_a, **_kw):
        raise RuntimeError("events down")
    monkeypatch.setattr(pg, "record_coverage_used", boom)
    r = _call(client, "POST", "/api/trades/propose", body={"league_id": L})
    assert r.status_code == 200 and r.get_json()["pass_league"] == L
