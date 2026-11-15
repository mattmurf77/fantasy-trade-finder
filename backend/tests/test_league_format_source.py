"""D-268 — a league's own format governs every league surface.

Bug: a one-QB league showed "Dynasty · SF TEP" on League Summary and was
valued on the superflex board, because league surfaces read the SESSION's
active format (carried over from the previous league, set by the Tiers/Trios
SF/1QB toggle, or sent as X-Scoring-Format) instead of the league's stored
`leagues.default_scoring` (NULL reads as 1qb_ppr).

Pins, with flag `league.format_from_league` ON:
  • power rankings in a one-QB league answer 1qb_ppr and value on the one-QB
    pool / the caller's one-QB board, whatever the session or header says;
  • trade generation in that league builds on the one-QB board and can never
    pick up a deck cached under the superflex key;
  • session/init into a different league does not carry the previous
    league's format (the pre-built deck too);
  • ranking surfaces keep the toggle and header in both directions;
  • a league with no `leagues` row keeps the session format.
And with the flag OFF every one of those reads is the pre-fix one.

Synthetic ids only; in-memory SQLite; no network.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import create_engine

import backend.database as db
import backend.server as server
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService, elo_to_value

FLAG = "league.format_from_league"
TOKEN = "lfs-token"
USER = "lfs-user"
LEAGUE = "lfs-one-qb-league"
FORMATS = ("1qb_ppr", "sf_tep")

PLAYERS = {
    "qb1": Player(id="qb1", name="Qb One", position="QB", team="AAA", age=25),
    "rb1": Player(id="rb1", name="Rb One", position="RB", team="AAA", age=25),
}
SEED = {"1qb_ppr": {"qb1": 1500.0, "rb1": 1600.0},
        "sf_tep":  {"qb1": 1950.0, "rb1": 1600.0}}


def _flags(on: bool):
    return lambda key: on and key == FLAG


class _Board:
    """Ranking-service stub: the caller's personal board for one format."""

    def __init__(self, elos):
        self._elos = elos

    def get_rankings(self, position=None):
        return SimpleNamespace(rankings=[
            SimpleNamespace(player=PLAYERS[pid], elo=elo)
            for pid, elo in self._elos.items()])


@pytest.fixture()
def engine(monkeypatch):
    eng = create_engine("sqlite:///:memory:")
    db.metadata.create_all(eng)
    monkeypatch.setattr(db, "engine", eng)
    yield eng
    eng.dispose()


def _store_league(eng, league_id, default_scoring):
    with eng.begin() as conn:
        conn.execute(db.leagues_table.insert().values(
            sleeper_league_id=league_id, user_id=USER, name="Synthetic",
            default_scoring=default_scoring))


# ---------------------------------------------------------------------------
# League Summary / power rankings
# ---------------------------------------------------------------------------

@pytest.fixture()
def pr_client(engine, monkeypatch):
    pool_calls = []

    def fake_pool(fmt):
        pool_calls.append(fmt)
        return list(PLAYERS.values()), dict(SEED[fmt])

    members = [{"user_id": USER, "username": "me", "display_name": "me",
                "player_ids": ["qb1", "rb1"]},
               {"user_id": "lfs-opp", "username": "opp", "display_name": "opp",
                "player_ids": []}]
    monkeypatch.setattr(server, "_get_universal_pool", fake_pool)
    monkeypatch.setattr(server, "load_league_members",
                        lambda lid: [dict(m) for m in members] if lid == LEAGUE else [])
    monkeypatch.setattr(server, "load_draft_picks", lambda league_id=None, **kw: [])
    monkeypatch.setattr(server, "_sleeper_lineup_slots", lambda lid: None)
    monkeypatch.setattr(server, "touch_user_activity", MagicMock())
    monkeypatch.setattr(server, "_verified_read_denial", lambda s: None)
    server._rank_chip_cache.clear()
    boards = {"1qb_ppr": _Board({"qb1": 1700.0}), "sf_tep": _Board({"qb1": 2100.0})}
    sess = {"verified": True, "user_id": USER, "active_format": "sf_tep",
            "last_active": 0.0,
            "league": SimpleNamespace(league_id=LEAGUE, platform=None, members=[]),
            "players": list(PLAYERS.values()),
            "trade_svc": object(), "trade_svcs": {f: object() for f in FORMATS},
            "services": boards, "service": boards["sf_tep"], "user_roster": []}
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    server.app.config["TESTING"] = True
    try:
        yield server.app.test_client(), pool_calls, sess
    finally:
        server._rank_chip_cache.clear()
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


def _power(client, basis="consensus", header=None):
    headers = {"X-Session-Token": TOKEN}
    if header:
        headers["X-Scoring-Format"] = header
    r = client.get(f"/api/league/power-rankings?league_id={LEAGUE}&basis={basis}",
                   headers=headers)
    assert r.status_code == 200, r.data
    body = json.loads(r.data)
    me = next(t for t in body["teams"] if t["user_id"] == USER)
    return body["scoring_format"], me["positions"]["QB"]["value"]


@pytest.mark.parametrize("header", [None, "sf_tep"])
def test_one_qb_league_power_rankings_use_league_format_not_session(
        pr_client, engine, monkeypatch, header):
    """Reproduction: superflex session (and header) in a one-QB league whose
    stored default_scoring is NULL. Flag on ⇒ 1qb_ppr label and values."""
    client, pool_calls, _ = pr_client
    _store_league(engine, LEAGUE, None)
    monkeypatch.setattr(server, "is_enabled", _flags(True))
    fmt, qb = _power(client, header=header)
    assert fmt == "1qb_ppr"
    assert set(pool_calls) == {"1qb_ppr"}
    assert abs(qb - round(elo_to_value(SEED["1qb_ppr"]["qb1"]), 1)) < 0.2


def test_personal_basis_reads_callers_board_for_league_format(pr_client, engine, monkeypatch):
    client, _, _ = pr_client
    _store_league(engine, LEAGUE, None)
    monkeypatch.setattr(server, "is_enabled", _flags(True))
    fmt, qb = _power(client, basis="personal", header="sf_tep")
    assert fmt == "1qb_ppr"
    assert abs(qb - round(elo_to_value(1700.0), 1)) < 0.2      # one-QB board


def test_superflex_league_stays_superflex_under_a_one_qb_session(pr_client, engine, monkeypatch):
    client, pool_calls, sess = pr_client
    _store_league(engine, LEAGUE, "sf_tep")
    sess["active_format"] = "1qb_ppr"
    sess["service"] = sess["services"]["1qb_ppr"]
    monkeypatch.setattr(server, "is_enabled", _flags(True))
    fmt, qb = _power(client, header="1qb_ppr")
    assert fmt == "sf_tep"
    assert set(pool_calls) == {"sf_tep"}


def test_flag_off_power_rankings_follow_session_as_before(pr_client, engine, monkeypatch):
    client, pool_calls, _ = pr_client
    _store_league(engine, LEAGUE, None)
    monkeypatch.setattr(server, "is_enabled", _flags(False))
    fmt, qb = _power(client)
    assert fmt == "sf_tep"
    assert set(pool_calls) == {"sf_tep"}
    assert abs(qb - round(elo_to_value(SEED["sf_tep"]["qb1"]), 1)) < 0.2
    pool_calls.clear()
    fmt, _ = _power(client, header="1qb_ppr")
    assert fmt == "1qb_ppr"                                 # header still wins off


def test_league_without_a_stored_row_keeps_session_format(pr_client, monkeypatch):
    client, pool_calls, _ = pr_client
    monkeypatch.setattr(server, "is_enabled", _flags(True))
    fmt, _ = _power(client)
    assert fmt == "sf_tep"


# ---------------------------------------------------------------------------
# Request seam: league surfaces vs ranking surfaces
# ---------------------------------------------------------------------------

@pytest.fixture()
def world(engine, monkeypatch):
    pool = [Player(id=p, name=p.upper(), position="RB", team="AAA", age=25)
            for p in ("give", "receive")]
    league = League(LEAGUE, "Synthetic", "sleeper", [
        LeagueMember(USER, "Me", ["give"], {}),
        LeagueMember("lfs-opp", "Opp", ["receive"], {})])
    services = {fmt: RankingService(pool, seed_ratings={p.id: 1500 + i * 100 for p in pool})
                for i, fmt in enumerate(FORMATS)}
    trades = {fmt: TradeService({p.id: p for p in pool}) for fmt in FORMATS}
    for svc in trades.values():
        svc.add_league(league)
    sess = dict(user_id=USER, league_user_id=USER, league=league, verified=True,
                user_roster=["give"], players=pool, services=services,
                trade_svcs=trades, service=services["sf_tep"],
                trade_svc=trades["sf_tep"], active_format="sf_tep", last_active=0)
    monkeypatch.setitem(server._sessions, TOKEN, sess)
    original_jobs = set(server._trade_jobs)
    yield sess
    for jid in set(server._trade_jobs) - original_jobs:
        job = server._trade_jobs.pop(jid)
        if server._trade_jobs_by_key.get(job["key"]) == jid:
            server._trade_jobs_by_key.pop(job["key"])


def _view(path, header=None):
    """The request view `_require_session` builds for `path` (routed by the
    test request context exactly as a real request is)."""
    headers = {"X-Session-Token": TOKEN}
    if header:
        headers["X-Scoring-Format"] = header
    # The real route's method: a GET catch-all would otherwise claim POST paths.
    adapter = server.app.url_map.bind("localhost")
    method = next(m for m in ("GET", "POST")
                  if _rule(adapter, path, m) not in (None, "/<path:path>")
                  and _rule(adapter, path, m).startswith("/api/"))
    with server.app.test_request_context(path, method=method, headers=headers):
        assert server.request.url_rule.rule.startswith("/api/"), path
        sess = server._require_session()
        return (server._active_format(sess), sess["service"], sess["trade_svc"],
                sess.get("active_format"))


def _rule(adapter, path, method):
    try:
        return adapter.match(path, method=method, return_rule=True)[0].rule
    except Exception:
        return None


@pytest.mark.parametrize("path", [
    "/api/league/power-rankings", "/api/league/picks", "/api/trades/generate",
    "/api/trades", "/api/trades/swipe", f"/api/leagues/{LEAGUE}/projection-runs",
    "/api/overhauls", "/api/win-now/search"])
def test_league_surfaces_resolve_league_format(world, engine, monkeypatch, path):
    _store_league(engine, LEAGUE, None)
    monkeypatch.setattr(server, "is_enabled", _flags(True))
    fmt, service, trade_svc, raw = _view(path, header="sf_tep")
    assert fmt == "1qb_ppr"
    assert service is world["services"]["1qb_ppr"]
    assert trade_svc is world["trade_svcs"]["1qb_ppr"]
    assert raw == "1qb_ppr"
    assert world["active_format"] == "sf_tep"      # the shared session is untouched


@pytest.mark.parametrize("path", [
    "/api/rankings", "/api/trio", "/api/progress", "/api/tiers/status",
    "/api/rankings/progress", "/api/me/streak", "/api/trends/risers-fallers"])
@pytest.mark.parametrize("toggle", FORMATS)
def test_ranking_surfaces_keep_the_toggle_in_both_directions(world, engine, monkeypatch,
                                                             path, toggle):
    _store_league(engine, LEAGUE, None)
    monkeypatch.setattr(server, "is_enabled", _flags(True))
    world["active_format"] = toggle
    fmt, service, _, _ = _view(path)
    assert fmt == toggle
    assert service is world["services"][toggle]
    other = FORMATS[1 - FORMATS.index(toggle)]
    fmt, service, _, _ = _view(path, header=other)
    assert fmt == other
    assert service is world["services"][other]


def test_scoring_switch_still_flips_the_ranking_board(world, engine, monkeypatch):
    _store_league(engine, LEAGUE, None)
    monkeypatch.setattr(server, "is_enabled", _flags(True))
    client = server.app.test_client()
    for fmt in ("1qb_ppr", "sf_tep", "1qb_ppr"):
        r = client.post("/api/scoring/switch", json={"format": fmt},
                        headers={"X-Session-Token": TOKEN})
        assert r.status_code == 200, r.data
        assert world["active_format"] == fmt
        assert _view("/api/rankings")[0] == fmt
        assert _view("/api/league/power-rankings")[0] == "1qb_ppr"


# ---------------------------------------------------------------------------
# Trade generation and the deck cache
# ---------------------------------------------------------------------------

def _generate(world, monkeypatch, flag_on):
    monkeypatch.setattr(server, "is_enabled", _flags(flag_on))
    import backend.feature_flags as flags
    monkeypatch.setattr(flags, "_flags_cache", {k: False for k in flags.DEFAULT_FLAGS})
    monkeypatch.setattr(server, "load_member_rankings", Mock(return_value={}))
    monkeypatch.setattr(server, "load_league_preference", Mock(return_value=None))
    monkeypatch.setattr(server, "record_event", Mock())
    pending = []

    class DeferredThread:
        def __init__(self, *, target, args, kwargs, daemon):
            pending.append((target, args, kwargs))

        def start(self):
            pass

    monkeypatch.setattr(server.threading, "Thread", DeferredThread)
    observed = []

    def generate(self, **kwargs):
        observed.append(kwargs)
        return []

    monkeypatch.setattr(TradeService, "generate_trades", generate)
    # A complete superflex deck already cached for this user and league.
    stale_id = "lfs-stale-sf-deck"
    stale_key = (USER, LEAGUE, "sf_tep")
    server._trade_jobs[stale_id] = {"job_id": stale_id, "key": stale_key, "status": "complete",
                                    "cards": [], "error": None}
    server._trade_jobs_by_key[stale_key] = stale_id
    try:
        r = server.app.test_client().post(
            "/api/trades/generate", json={"league_id": LEAGUE},
            headers={"X-Session-Token": TOKEN, "X-Scoring-Format": "sf_tep"})
        for target, args, kwargs in pending:
            target(*args, **kwargs)
    finally:
        server._trade_jobs.pop(stale_id, None)
        if server._trade_jobs_by_key.get(stale_key) == stale_id:
            server._trade_jobs_by_key.pop(stale_key)
    return r, observed, stale_id


def test_trade_generation_in_one_qb_league_uses_one_qb_board(world, engine, monkeypatch):
    _store_league(engine, LEAGUE, None)
    r, observed, stale_id = _generate(world, monkeypatch, flag_on=True)
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["job_id"] != stale_id                        # sf deck never served
    assert server._trade_jobs[body["job_id"]]["key"] == (USER, LEAGUE, "1qb_ppr")
    assert observed and observed[0]["scoring_format"] == "1qb_ppr"
    one_qb = world["services"]["1qb_ppr"]
    assert observed[0]["user_elo"]["give"] == one_qb._seed["give"]


def test_flag_off_trade_generation_follows_session_header(world, engine, monkeypatch):
    _store_league(engine, LEAGUE, None)
    r, observed, stale_id = _generate(world, monkeypatch, flag_on=False)
    assert r.status_code == 200, r.data
    job = server._trade_jobs.get(r.get_json()["job_id"]) or {}
    # Off: the request is keyed on the session/header format, exactly as before.
    assert r.get_json()["job_id"] == stale_id or job.get("key") == (USER, LEAGUE, "sf_tep")
    assert all(o["scoring_format"] == "sf_tep" for o in observed)


# ---------------------------------------------------------------------------
# session/init: switching leagues does not carry the previous format
# ---------------------------------------------------------------------------

from backend.tests.test_session_init_sleeper_calls import (  # noqa: E402
    NON_SLEEPER_LEAGUE, NUMERIC_MFL_LEAGUE, _init, harness)

SF_LEAGUE, ONE_QB_LEAGUE = NUMERIC_MFL_LEAGUE, NON_SLEEPER_LEAGUE


def _switch(harness, monkeypatch, flag_on):
    client, _ = harness
    real = server.is_enabled
    monkeypatch.setattr(server, "is_enabled",
                        lambda k: flag_on if k == FLAG else real(k))
    with db.engine.begin() as conn:
        conn.execute(db.leagues_table.update()
                     .where(db.leagues_table.c.sleeper_league_id == SF_LEAGUE)
                     .values(default_scoring="sf_tep"))
    assert _init(client, SF_LEAGUE).status_code == 200
    sess = server._sessions["budget-verified-token"]
    assert sess["active_format"] == "sf_tep"
    server._kickoff_trade_job.reset_mock()
    assert _init(client, ONE_QB_LEAGUE).status_code == 200
    sess = server._sessions["budget-verified-token"]
    kicked = [c.kwargs.get("scoring_format") for c in server._kickoff_trade_job.call_args_list]
    return sess, kicked


def test_league_switch_superflex_to_one_qb_does_not_carry_superflex(harness, monkeypatch):
    sess, kicked = _switch(harness, monkeypatch, flag_on=True)
    assert sess["active_format"] == "1qb_ppr"
    assert sess["service"] is sess["services"]["1qb_ppr"]
    assert kicked == ["1qb_ppr"]


def test_flag_off_league_switch_carries_format_as_before(harness, monkeypatch):
    sess, kicked = _switch(harness, monkeypatch, flag_on=False)
    assert sess["active_format"] == "sf_tep"


def test_same_league_reinit_keeps_the_toggle(harness, monkeypatch):
    client, _ = harness
    real = server.is_enabled
    monkeypatch.setattr(server, "is_enabled", lambda k: True if k == FLAG else real(k))
    assert _init(client, ONE_QB_LEAGUE).status_code == 200
    server._sessions["budget-verified-token"]["active_format"] = "sf_tep"   # toggled
    server._kickoff_trade_job.reset_mock()
    assert _init(client, ONE_QB_LEAGUE).status_code == 200
    # The ranking toggle survives a re-init of the same league ...
    assert server._sessions["budget-verified-token"]["active_format"] == "sf_tep"
    # ... but the league's pre-built deck is still on the league's format.
    kicked = [c.kwargs.get("scoring_format") for c in server._kickoff_trade_job.call_args_list]
    assert kicked == ["1qb_ppr"]
