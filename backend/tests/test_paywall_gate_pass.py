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
  (9) overhaul_api / win_now_api check the league they act on themselves
      (the session's, the overhaul / job / scenario row's): a session view
      moved to another league after _require_initialized_session's check gets
      the ordinary 402; the pass league goes through; flag off (and pro) the
      check reads nothing and changes no response
  (10) swipe and pass-reason check the card's league before any write: a
      card planted in another league gets the ordinary 402 with nothing
      written; a body naming another league is never covered
  (11) D1, a session with no league yet: a covered member gets the Pro
      user's 409 session_not_initialized from the hook (no handler, no
      preview, no body league standing in); no live coverage, unverified,
      flag off and a coverage-read failure are unchanged
  (12) D3: league_pass_coverage_used stays one row after the in-process
      de-dupe is cleared (a restart, another worker)

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


# ── (9) the league-match check inside overhaul_api and win_now_api ─────────
# Both modules call their injected require_session (server's
# _require_initialized_session, which already confirms the session's league)
# and then read the league themselves: the session's active league, or a
# stored row's (overhaul, Win Now job, scenario). The race below lets that
# check pass and then moves the request's session view to L2, so the module
# reads L2: its own check (server._confirm_pass_league, injected as
# confirm_pass_league) must answer the ordinary 402.

import backend.overhaul_store as ovh_store
import backend.win_now_api as win_now_api
import backend.win_now_store as wn_store

REAL_VIEWS = {ep: server.app.view_functions[ep]
              for ep in ("overhaul_active_route", "overhaul_get_route",
                         "win_now_job_route", "win_now_decision_route",
                         "generate_trades", "win_now_search_route")}


@pytest.fixture()
def real_modules(client, monkeypatch):
    for ep, fn in REAL_VIEWS.items():
        monkeypatch.setitem(server.app.view_functions, ep, fn)
    monkeypatch.setattr(win_now_api, "is_enabled", lambda k: k in (
        "outlook.season_projections", "trades.win_now"))
    monkeypatch.setattr(win_now_api.service, "wake_worker", lambda *_a, **_kw: None)
    with server._sessions_lock:
        server._sessions[TOKEN]["league_user_id"] = MATE
    return client


def _switch_after_the_session_check(monkeypatch, to=L2):
    """The race: _require_initialized_session's own check passes on L, then
    the request's session view (what the module reads) is in `to`."""
    real = server._confirm_pass_session_league

    def check_then_switch(sess):
        real(sess)
        sess.data["league"] = SimpleNamespace(league_id=to)
    monkeypatch.setattr(server, "_confirm_pass_session_league", check_then_switch)


def _overhaul_row(league_id):
    return ovh_store.create_overhaul(
        account_user_id=MATE, league_user_id=MATE, league_id=league_id, platform="sleeper",
        scoring_format="1qb_ppr", client_key=f"ck-{league_id}", settings={}, snapshot=None,
        recovery=None)["overhaul_id"]


def _failed_job(league_id):
    job = wn_store.create_job(MATE, league_id, {"actor": {}, "params": {}})
    wn_store.claim_job(job["job_id"])
    wn_store.finish_job(job["job_id"], reason="no_trades")
    return job["job_id"]


def _stale_scenario(league_id):
    return wn_store.save_scenario(
        MATE, league_id, "playoffs",
        {"partner_roster_id": 2, "give": [], "receive": [], "eligible": True},
        {"snapshot_id": "snap", "expires_at": w.iso(-1)})["scenario_id"]


@pytest.mark.parametrize("read", ["overhaul_active", "overhaul_row", "win_now_job",
                                  "win_now_scenario"])
def test_module_reads_after_a_session_switch_get_the_ordinary_402(eng, real_modules,
                                                                  monkeypatch, read):
    _add_pass(eng)
    method, path, body = {
        "overhaul_active": lambda: ("GET", "/api/overhauls", None),
        "overhaul_row": lambda: ("GET", f"/api/overhauls/{_overhaul_row(L2)}", None),
        "win_now_job": lambda: ("GET", f"/api/win-now/jobs/{_failed_job(L2)}", None),
        "win_now_scenario": lambda: ("POST", f"/api/win-now/scenarios/"
                                     f"{_stale_scenario(L2)}/decision", {"decision": "like"}),
    }[read]()
    _switch_after_the_session_check(monkeypatch)
    r = _call(real_modules, method, path, body=body)
    assert (r.status_code, r.get_json()) == (402, NEVER)


def test_module_reads_in_the_pass_league_go_through(eng, real_modules):
    _add_pass(eng)
    r = _call(real_modules, "GET", "/api/overhauls")
    assert (r.status_code, r.get_json()) == (200, {"active": None})
    r = _call(real_modules, "GET", f"/api/win-now/jobs/{_failed_job(L)}")
    assert r.status_code == 200 and r.get_json()["status"] == "failed"
    r = _call(real_modules, "POST", f"/api/win-now/scenarios/{_stale_scenario(L)}/decision",
              body={"decision": "like"})
    assert r.status_code == 200 and r.get_json()["reason"] == "stale_forecast"


def test_module_checks_are_inert_without_a_pass(eng, real_modules, flag, monkeypatch):
    """Flag off (and account-level pro), a session in L2 is answered from L2
    exactly as before: the modules' check is a no-op that reads nothing, and
    the same SQL is issued with and without a pass in L."""
    from sqlalchemy import event
    flag["on"] = False
    ids = (_overhaul_row(L2), _failed_job(L2))
    _session_league(TOKEN, L2)
    paths = ["/api/overhauls", f"/api/overhauls/{ids[0]}", f"/api/win-now/jobs/{ids[1]}"]
    # Account-level pro, so these gated reads reach the handler with the flag off.
    with eng.begin() as conn:
        w.ent_row(conn, MATE, product="ftf_pro_annual", source="apple_iap")
    stmts = []
    event.listen(eng, "before_cursor_execute",
                 lambda conn, cur, stmt, params, ctx, many: stmts.append(stmt))
    without = [_call(real_modules, "GET", p) for p in paths]
    before, stmts[:] = list(stmts), []
    _add_pass(eng)
    stmts[:] = []
    with_pass = [_call(real_modules, "GET", p) for p in paths]
    assert stmts == before
    import re
    stamp = re.compile(rb'"checked_at":"[^"]*"')     # the capabilities read time
    for p, a, b in zip(paths, without, with_pass):
        assert a.status_code == 200, (p, a.data)
        assert (a.status_code, stamp.sub(b"", a.data)) == (b.status_code, stamp.sub(b"", b.data)), p


# ── (10) swipe and pass-reason: the card's own league ──────────────────────
# Reachability (lld §4.3): a card is looked up in the session's trade
# service, which session init builds for that session's league only, and a
# card the service no longer holds is rebuilt in the body's league_id, else
# the session's; the `active` resolver never covers a body naming another
# league. So a pass-allowed request cannot name another league's card today.
# The handlers still confirm the card's league before any write, so that
# invariant is not the pass's only guard: a card planted in another league
# gets the ordinary 402 and nothing is written.

class _Deck:
    """A session trade service holding one card; record_decision stops the
    handler right after the league-match check."""

    def __init__(self, league_id):
        self._trade_cards = {"t-1": SimpleNamespace(
            trade_id="t-1", league_id=league_id, target_user_id="u-partner",
            give_player_ids=["p1"], receive_player_ids=["p2"], decision=None)}
        self.decided = []

    def record_decision(self, trade_id, decision):
        self.decided.append(trade_id)
        raise ValueError("stopped_after_the_check")


def _deck(league_id):
    deck = _Deck(league_id)
    with server._sessions_lock:
        server._sessions[TOKEN].update(trade_svc=deck, service=object())
    return deck


def _pass_reasons(eng):
    with eng.connect() as conn:
        return conn.execute(select(db_module.trade_pass_reasons_table)).fetchall()


def test_swipe_on_a_card_from_another_league_gets_the_ordinary_402(eng, client):
    _add_pass(eng)
    deck = _deck(L2)
    r = _call(client, "POST", "/api/trades/swipe", body={"trade_id": "t-1", "decision": "pass"})
    assert (r.status_code, r.get_json()) == (402, NEVER)
    assert deck.decided == [] and deck._trade_cards["t-1"].decision is None


def test_swipe_on_a_pass_league_card_goes_through(eng, client):
    _add_pass(eng)
    deck = _deck(L)
    r = _call(client, "POST", "/api/trades/swipe", body={"trade_id": "t-1", "decision": "pass"})
    assert (r.status_code, r.get_json()) == (400, {"error": "stopped_after_the_check"})
    assert deck.decided == ["t-1"]
    # A card no longer held is rebuilt in the session's league: through.
    r = _call(client, "POST", "/api/trades/swipe", body={"trade_id": "t-gone", "decision": "pass"})
    assert r.status_code != 402 and deck.decided == ["t-1", "t-gone"]


def test_swipe_naming_another_league_is_never_covered(eng, client):
    """The FB-46 rebuild would use the body's league: the gate does not
    cover it, so the answer is the one a user without a pass gets."""
    _deck(L)
    body = {"trade_id": "t-gone", "decision": "pass", "league_id": L2,
            "give_player_ids": ["p1"], "receive_player_ids": ["p2"]}
    without = _call(client, "POST", "/api/trades/swipe", body=body)
    _add_pass(eng)
    with_pass = _call(client, "POST", "/api/trades/swipe", body=body)
    assert (with_pass.status_code, with_pass.data) == (without.status_code, without.data)


def test_pass_reason_on_a_card_from_another_league_gets_the_ordinary_402(eng, client,
                                                                         monkeypatch):
    monkeypatch.setattr(server, "_decline_reasons_enabled", lambda: True)
    _add_pass(eng)
    _deck(L2)
    r = _call(client, "POST", "/api/trades/pass-reason",
              body={"trade_id": "t-1", "reason": "value"})
    assert (r.status_code, r.get_json()) == (402, NEVER)
    assert _pass_reasons(eng) == []


def test_pass_reason_on_a_pass_league_card_goes_through(eng, client, monkeypatch):
    monkeypatch.setattr(server, "_decline_reasons_enabled", lambda: True)
    _add_pass(eng)
    _deck(L)
    r = _call(client, "POST", "/api/trades/pass-reason",
              body={"trade_id": "t-1", "reason": "value"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert len(_pass_reasons(eng)) == 1


# ── (11) D1: a covered member on a session with no league yet ──────────────
# Signed in, /api/session/init not run (or a session restored after a
# restart): a `session` / `active` rule cannot resolve a league. A Pro user
# gets the handler's 409 session_not_initialized; a member some live pass
# covers gets the same body from the hook, before any handler, the preview or
# a body-named league is consulted. Everyone else's answer is unchanged.

BARE, BARE_PRO, BARE_UNVERIFIED = "lpg-bare", "lpg-bare-pro", "lpg-bare-unverified"
PRO = "u-pro"
SESSION_NOT_READY = {"error": "session_not_initialized",
                     "message": "League data is still loading — try again in a moment."}
BARE_REQUESTS = [
    ("POST", "/api/trades/generate", {"league_id": L}),               # active, deck
    ("POST", "/api/trades/swipe", {"trade_id": "t-1", "decision": "pass", "league_id": L}),
    ("GET", "/api/overhauls", None),                                  # session
    ("POST", "/api/win-now/search", {"league_id": L}),                # session
]


@pytest.fixture()
def bare(eng, real_modules, monkeypatch):
    """Sessions with no league; every handler behind BARE_REQUESTS is real."""
    for ep in ("generate_trades", "win_now_search_route"):
        monkeypatch.setitem(server.app.view_functions, ep, REAL_VIEWS[ep])
    with eng.begin() as conn:
        w.ent_row(conn, PRO, product="ftf_pro_annual", source="apple_iap")
    base = {"verified": True, "last_active": time.time()}
    sessions = {BARE: {"user_id": MATE, **base}, BARE_PRO: {"user_id": PRO, **base},
                BARE_UNVERIFIED: {"user_id": MATE, "last_active": time.time()}}
    with server._sessions_lock:
        server._sessions.update(sessions)
    yield real_modules
    with server._sessions_lock:
        for t in sessions:
            server._sessions.pop(t, None)


@pytest.mark.parametrize("method,path,body", BARE_REQUESTS)
def test_bare_session_covered_member_gets_the_pro_answer(eng, bare, method, path, body):
    _add_pass(eng)
    pro = _call(bare, method, path, BARE_PRO, body)
    member = _call(bare, method, path, BARE, body)
    assert (pro.status_code, pro.get_json()) == (409, SESSION_NOT_READY)
    assert (member.status_code, member.data) == (pro.status_code, pro.data)
    assert _previews(eng) == [] and w.events(eng, pg.COVERAGE_USED_EVENT) == []


def test_bare_session_never_reaches_a_handler(eng, client, monkeypatch):
    """The 409 comes from the hook: a stubbed handler (which would answer
    200) is never run, even with a body naming the covered league."""
    _add_pass(eng)
    with server._sessions_lock:
        server._sessions[BARE] = {"user_id": MATE, "verified": True,
                                  "last_active": time.time()}
    try:
        for method, path, body in [("POST", "/api/trades/generate", {"league_id": L}),
                                   ("GET", "/api/overhauls", None)]:
            r = _call(client, method, path, BARE, body)
            assert (r.status_code, r.get_json()) == (409, SESSION_NOT_READY), path
    finally:
        with server._sessions_lock:
            server._sessions.pop(BARE, None)


@pytest.mark.parametrize("method,path,body", BARE_REQUESTS)
def test_bare_session_without_live_coverage_is_unchanged(eng, bare, method, path, body):
    """No pass, an ended pass, or a pass in a league the user is not in:
    the answer is today's (verdict never returns the 409 for them)."""
    expected = _call(bare, method, path, BARE, body)
    with eng.begin() as conn:
        w.league(conn, "lg-other", total_rosters=12)
        w.pass_row(conn, "lg-other", origin="comp", comp_days=30)
        w.pass_row(conn, L2, origin="comp", comp_days=-1)
    r = _call(bare, method, path, BARE, body)
    assert (r.status_code, r.data) == (expected.status_code, expected.data)


def test_bare_session_without_coverage_keeps_the_402_and_preview(eng, bare):
    r = _call(bare, "POST", "/api/trades/swipe", BARE,
              {"trade_id": "t-1", "decision": "pass"})
    assert (r.status_code, r.get_json()) == (402, NEVER)


def test_bare_unverified_session_does_not_depend_on_a_pass(eng, bare, monkeypatch):
    without = [_call(bare, m, p, BARE_UNVERIFIED, b) for m, p, b in BARE_REQUESTS]
    _add_pass(eng)
    calls = []
    for name in ("covers", "passes_for"):
        real = getattr(lp, name)
        monkeypatch.setattr(lp, name, lambda *a, _r=real, **kw: calls.append(a) or _r(*a, **kw))
    with_pass = [_call(bare, m, p, BARE_UNVERIFIED, b) for m, p, b in BARE_REQUESTS]
    assert [(r.status_code, r.data) for r in with_pass] == \
        [(r.status_code, r.data) for r in without]
    assert calls == []


def test_bare_session_flag_off_reads_no_coverage(eng, bare, flag, monkeypatch):
    flag["on"] = False
    without = [_call(bare, m, p, BARE, b) for m, p, b in BARE_REQUESTS]
    _add_pass(eng)

    def never(*a, **_kw):
        raise AssertionError("read with monetize.league_pass off")
    monkeypatch.setattr(lp, "passes_for", never)
    monkeypatch.setattr(lp, "covers", never)
    with_pass = [_call(bare, m, p, BARE, b) for m, p, b in BARE_REQUESTS]
    assert [(r.status_code, r.data) for r in with_pass] == \
        [(r.status_code, r.data) for r in without]


def test_bare_session_coverage_read_failure_is_not_covered(eng, bare, monkeypatch):
    _add_pass(eng)

    def boom(*_a, **_kw):
        raise RuntimeError("db down")
    monkeypatch.setattr(lp, "passes_for", boom)
    r = _call(bare, "POST", "/api/trades/swipe", BARE, {"trade_id": "t-1", "decision": "pass"})
    assert (r.status_code, r.get_json()) == (402, NEVER)


# ── (12) D3: league_pass_coverage_used once per user, league and day ───────

def test_coverage_used_survives_a_restart_the_same_day(eng, client):
    """A cleared in-process de-dupe (a restart, another worker) still writes
    no second row for the same user, league and UTC day."""
    _add_pass(eng)
    _call(client, "POST", "/api/trades/propose", body={"league_id": L})
    pg._gate_hits.clear()
    _call(client, "POST", "/api/trades/propose", body={"league_id": L})
    assert w.events(eng, pg.COVERAGE_USED_EVENT) == [(MATE, {"family": "send"}, L)]
