"""League pass: how the paywall gate finds the league a gated request acts on
(paywall_gate.LEAGUE_RESOLVERS, resolve_league; server._paywall_job_league).

Spec: docs/plans/monetization/league-pass/lld.md §4.2, §11.

Covers:
  (1) completeness: every GATED rule in ROUTES has a resolver kind, and the
      table names no rule that isn't gated (the way
      test_paywall_gate_allowlist.py keeps ROUTES complete)
  (2) each kind returns the league its handler acts on:
        session — the session's active league, whatever the body names
        active  — the session's league; None when the body names another
                  (raw comparison, as generate reads it); a non-dict body
                  reads as no body
        body    — the body's league stripped like the propose routes, else
                  the session's
        query   — ?league_id=, else the session's
        job     — the requester's in-process job key, else the lineage row
                  of the deck; another user's job is None
        match   — the trade_matches row's league
  (3) an unresolvable league is None (not covered): no session league, an
      unknown job, an unknown match, a rule with no kind
  (4) a resolver exception is None, logged, never raised (a pass must not
      widen access on an error); end to end through the hook, a raising job
      lookup leaves a covered member on the ordinary 402
  (5) the hook's body read matches the handlers' forced get_json: a body
      without a JSON content type is still read, and Flask's JSON cache is
      untouched (server._paywall_pass_league)

In-memory SQLite, no network.
"""

import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import insert

import backend.database as db_module
import backend.entitlements as entl
import backend.paywall_gate as pg
import backend.server as server
from backend.tests.support import league_pass_world as w

L, L2 = "lg-covered", "lg-other"
BUYER, MATE = "u-buyer", "u-mate"
TOKEN = "lpr-token"
MOBILE = {"X-Device": "iphone"}


@pytest.fixture()
def eng():
    engine = w.make_engine()
    with patch.object(db_module, "engine", engine):
        yield engine


def _ask(**kw):
    kw.setdefault("session_league", L)
    return pg.LeagueAsk(**kw)


# ── (1) completeness ───────────────────────────────────────────────────────

def test_every_gated_rule_has_a_resolver():
    gated = {k for k, v in pg.ROUTES.items() if v == pg.GATED}
    assert gated - set(pg.LEAGUE_RESOLVERS) == set()
    assert set(pg.LEAGUE_RESOLVERS) - gated == set()
    kinds = {pg.SESSION, pg.ACTIVE, pg.BODY, pg.QUERY, pg.JOB, pg.MATCH}
    assert set(pg.LEAGUE_RESOLVERS.values()) <= kinds


def test_resolver_table_as_traced():
    """The kinds the handlers were traced to (lld §4.2, deviations in §4.2's
    note): a change here must re-trace the handler."""
    by_kind = {}
    for (method, rule), kind in pg.LEAGUE_RESOLVERS.items():
        by_kind.setdefault(kind, set()).add((method, rule))
    assert by_kind[pg.QUERY] == {("GET", "/api/trades")}
    assert by_kind[pg.JOB] == {("GET", "/api/trades/status")}
    assert by_kind[pg.MATCH] == {("POST", "/api/trades/matches/<int:match_id>/disposition")}
    assert {r for _m, r in by_kind[pg.BODY]} == {
        "/api/trades/propose", "/api/trades/propose-espn", "/api/trades/propose-mfl",
        "/api/trades/respond-mfl"}
    assert {r for _m, r in by_kind[pg.ACTIVE]} == {
        "/api/trades/generate", "/api/trades/pass-reason", "/api/trades/swipe",
        "/api/trades/queue", "/api/trades/asset-ideas", "/api/trades/fair-packages",
        "/api/trades/standing-offer"}
    assert all(r.startswith(("/api/overhauls", "/api/win-now/")) for _m, r in by_kind[pg.SESSION])


# ── (2) each kind ──────────────────────────────────────────────────────────

def test_session_kind_ignores_the_body():
    for rule in ("/api/win-now/search", "/api/overhauls"):
        assert pg.resolve_league(rule, "POST", _ask(body={"league_id": L2})) == L
    assert pg.resolve_league("/api/overhauls", "GET", _ask(args={"league_id": L2})) == L


@pytest.mark.parametrize("rule", ["/api/trades/generate", "/api/trades/queue",
                                  "/api/trades/fair-packages", "/api/trades/swipe"])
def test_active_kind_needs_the_body_to_agree_with_the_session(rule):
    assert pg.resolve_league(rule, "POST", _ask(body={})) == L
    assert pg.resolve_league(rule, "POST", _ask(body={"league_id": ""})) == L
    assert pg.resolve_league(rule, "POST", _ask(body={"league_id": L})) == L
    assert pg.resolve_league(rule, "POST", _ask(body={"league_id": L2})) is None
    # generate reads the raw value: " lg-covered" is not the session's league
    assert pg.resolve_league(rule, "POST", _ask(body={"league_id": f" {L}"})) is None


def test_body_kind_reads_the_league_the_propose_routes_read():
    rule = "/api/trades/propose"
    assert pg.resolve_league(rule, "POST", _ask(body={"league_id": f" {L2} "})) == L2
    assert pg.resolve_league(rule, "POST", _ask(body={"league_id": 123})) == "123"
    assert pg.resolve_league(rule, "POST", _ask(body={})) == L


def test_query_kind():
    assert pg.resolve_league("/api/trades", "GET", _ask(args={"league_id": L2})) == L2
    assert pg.resolve_league("/api/trades", "GET", _ask(args={})) == L
    assert pg.resolve_league("/api/trades", "HEAD", _ask(args={})) == L


def test_job_kind_reads_the_requesters_deck(eng):
    with server._trade_jobs_lock:
        server._trade_jobs["job-mine"] = {"key": (MATE, L, "1qb_ppr")}
        server._trade_jobs["job-theirs"] = {"key": (BUYER, L, "1qb_ppr")}
    try:
        assert server._paywall_job_league(MATE, "job-mine") == L
        assert server._paywall_job_league(MATE, "job-theirs") is None
        assert server._paywall_job_league(MATE, "job-gone") is None
        with eng.begin() as conn:
            conn.execute(insert(db_module.trade_deck_lineage_table).values(
                user_id=MATE, deck_job_id="job-gone", league_id=L2,
                scoring_format="1qb_ppr", request_scope="organic:f=0.50", recorded_at=w.iso()))
        assert server._paywall_job_league(MATE, "job-gone") == L2
        assert server._paywall_job_league(BUYER, "job-gone") is None
    finally:
        with server._trade_jobs_lock:
            server._trade_jobs.pop("job-mine", None)
            server._trade_jobs.pop("job-theirs", None)


def test_job_kind_calls_the_server_lookup():
    ask = _ask(job_league=lambda: L2)
    assert pg.resolve_league("/api/trades/status", "GET", ask) == L2


def test_match_kind_reads_the_row(eng):
    with eng.begin() as conn:
        match_id = conn.execute(insert(db_module.trade_matches_table).values(
            league_id=L2, user_a_id=MATE, user_b_id=BUYER, user_a_give="[]",
            user_a_receive="[]")).inserted_primary_key[0]
    rule = "/api/trades/matches/<int:match_id>/disposition"
    assert pg.resolve_league(rule, "POST", _ask(view_args={"match_id": match_id})) == L2


# ── (3) unresolvable → None ────────────────────────────────────────────────

def test_unresolvable_is_none(eng):
    rule = "/api/trades/matches/<int:match_id>/disposition"
    assert pg.resolve_league(rule, "POST", _ask(view_args={"match_id": 999})) is None
    assert pg.resolve_league("/api/win-now/search", "POST", _ask(session_league=None)) is None
    assert pg.resolve_league("/api/trades/generate", "POST", _ask(session_league=None)) is None
    assert pg.resolve_league("/api/trades/status", "GET", _ask()) is None
    assert pg.resolve_league("/api/trade/evaluate", "POST", _ask()) is None


# ── (4) a resolver exception → None ────────────────────────────────────────

def test_resolver_exception_is_none(eng, caplog):
    def boom():
        raise RuntimeError("lookup down")
    assert pg.resolve_league("/api/trades/status", "GET", _ask(job_league=boom)) is None
    assert "league resolver failed" in caplog.text
    rule = "/api/trades/matches/<int:match_id>/disposition"
    assert pg.resolve_league(rule, "POST", _ask(view_args={"match_id": "x"})) is None
    assert pg.resolve_league(rule, "POST", _ask(view_args=None)) is None


@pytest.fixture()
def covered_world(eng, monkeypatch):
    """MATE is covered in L by BUYER's live purchase pass; the gate enforces
    on mobile with the deck preview off and the league pass flag on."""
    with eng.begin() as conn:
        w.league(conn, L, total_rosters=12)
        w.member(conn, L, BUYER)
        w.member(conn, L, MATE)
        w.ent_row(conn, BUYER)
        w.pass_row(conn, L, buyer=BUYER)
        w.knob(conn, "paywall_enforce_enabled", 1.0)
        w.knob(conn, "paywall_preview_pages", 0.0)
    monkeypatch.setattr(pg, "is_enabled", lambda k: k == pg.league_pass.FLAG)
    monkeypatch.setitem(server.app.view_functions, "trade_job_status",
                        lambda **_kw: ("ok", 200))
    server.app.config["TESTING"] = True
    with server._sessions_lock:
        server._sessions[TOKEN] = {"user_id": MATE, "verified": True,
                                   "league": SimpleNamespace(league_id=L),
                                   "last_active": time.time()}
    try:
        with patch.object(entl, "is_enabled",
                          lambda k: k in ("monetize.entitlements", "monetize.paywall")):
            yield server.app.test_client()
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
        with server._trade_jobs_lock:
            server._trade_jobs.pop("job-lp", None)


def test_hook_covers_a_status_poll_on_the_pass_league(covered_world):
    with server._trade_jobs_lock:
        server._trade_jobs["job-lp"] = {"key": (MATE, L, "1qb_ppr")}
    r = covered_world.get("/api/trades/status?job_id=job-lp",
                          headers={"X-Session-Token": TOKEN, **MOBILE})
    assert r.status_code == 200


def test_hook_unresolvable_job_is_the_ordinary_402(covered_world):
    r = covered_world.get("/api/trades/status?job_id=nope",
                          headers={"X-Session-Token": TOKEN, **MOBILE})
    assert (r.status_code, r.get_json()) == (402, {"error": "pro_required",
                                                   "gate": "never_trialed"})


def test_hook_resolver_exception_is_the_ordinary_402_not_fail_open(covered_world, monkeypatch):
    with server._trade_jobs_lock:
        server._trade_jobs["job-lp"] = {"key": (MATE, L, "1qb_ppr")}

    def boom(*_a):
        raise RuntimeError("lookup down")
    monkeypatch.setattr(server, "_paywall_job_league", boom)
    r = covered_world.get("/api/trades/status?job_id=job-lp",
                          headers={"X-Session-Token": TOKEN, **MOBILE})
    assert r.status_code == 402


def test_hook_coverage_read_exception_is_the_ordinary_402(covered_world, monkeypatch):
    with server._trade_jobs_lock:
        server._trade_jobs["job-lp"] = {"key": (MATE, L, "1qb_ppr")}

    def boom(*_a):
        raise RuntimeError("db down")
    monkeypatch.setattr(pg.league_pass, "covers", boom)
    r = covered_world.get("/api/trades/status?job_id=job-lp",
                          headers={"X-Session-Token": TOKEN, **MOBILE})
    assert r.status_code == 402


# ── (5) the hook reads the body the handlers read ──────────────────────────

def test_hook_reads_a_body_without_a_json_content_type(covered_world):
    seen = {}
    with server.app.test_request_context(
            "/api/trades/generate", method="POST", data=f'{{"league_id": "{L2}"}}',
            content_type="text/plain"):
        sess = {"league": SimpleNamespace(league_id=L)}
        league, _uid = server._paywall_pass_league("/api/trades/generate", sess,
                                                   SimpleNamespace(job_id=None))
        seen["unforced"] = server.request.get_json(silent=True)
        seen["forced"] = server.request.get_json(force=True)
    assert league is None                       # the body names another league
    assert seen == {"unforced": None, "forced": {"league_id": L2}}
