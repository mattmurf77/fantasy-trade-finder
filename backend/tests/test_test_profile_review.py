"""Onboarding test profile — the 2026-11-12 independent review's findings.

docs/plans/onboarding-test-profile/design.md §13. One test (or more) per
finding, each sabotage-proven:

  M1  the request fence reads EVERY request source (any content type, nested
      and list bodies, form data, `league_ids`, camelCase) and the database
      write fence default-denies a test request's write under a real league;
      submit_rankings requires league membership for every caller
  M2  background sweeps and loaders never see a `qa_tp:` league
  L1  the chokepoint and the Sleeper refusal match structured ids, never text
  L2  closing the gate evicts test sessions from `_sessions`
  L4  reset drains in-flight work (a pre-reset lease is dead) and purges caches
  L6  a real or anonymous caller can never name a test league
  L7  a real token costs the fence no session lookup
  +   ACTOR is reset even when the request raises
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import insert, select, update

import backend.database as db
import backend.server as server
import backend.test_profile as tp
from backend.tests.test_test_profile import (  # noqa: F401  (world is a fixture)
    ESPN_LG, MATE, MFL_LG, OTHER, PID, REAL, REAL_TOKEN, SLEEPER_LG,
    _call, _dump, _enter, _seed_test_league, _ts, world,
)

pytestmark = pytest.mark.usefixtures("no_real_network")

NS = f"qa_tp:{REAL}:"


def _raw(client, token, path, data, content_type, method="POST"):
    return client.open(path, method=method, headers={"X-Session-Token": token},
                       content_type=content_type, data=data)


# ── M1: every request source is fenced ─────────────────────────────────────

def test_fence_reads_every_request_source(world):
    c = world["client"]
    tok = _enter(world)
    before = _dump(world["engine"])
    shapes = [
        # The review's case: a JSON body sent as text/plain to a force-parsing route.
        ("/api/rankings/submit", json.dumps({"league_id": SLEEPER_LG}), "text/plain"),
        ("/api/rankings/submit", json.dumps({"league_id": SLEEPER_LG}), ""),
        ("/api/rankings/submit", json.dumps({"payload": {"league_id": SLEEPER_LG}}), "application/json"),
        ("/api/rankings/submit", json.dumps([{"league_id": SLEEPER_LG}]), "application/json"),
        ("/api/rankings/submit", json.dumps({"leagueId": SLEEPER_LG}), "application/json"),
        ("/api/rankings/submit", json.dumps({"league_ids": [NS + "1", ESPN_LG]}), "application/json"),
        ("/api/rankings/submit", f"league_id={SLEEPER_LG}", "application/x-www-form-urlencoded"),
    ]
    for path, data, ctype in shapes:
        r = _raw(c, tok, path, data, ctype)
        assert r.status_code == 403 and r.get_json()["error"] == "test_profile_league", (data, ctype)
    r = c.get(f"/api/portfolio?league_ids={NS}1,{MFL_LG}", headers={"X-Session-Token": tok})
    assert r.status_code == 403
    assert _dump(world["engine"]) == before


def test_linking_inputs_stay_open_only_on_the_linking_routes(world):
    """Platform-native ids are link INPUTS on the real linking routes only."""
    c = world["client"]
    tok = _enter(world)
    for path, body in (("/api/rankings/submit", {"espn_league_id": ESPN_LG}),
                       ("/api/rankings/submit", {"mfl_league_id": MFL_LG})):
        assert _call(c, "POST", path, tok, body).status_code == 403
    assert server._TP_LINK_INPUT_KEYS == {
        "espn_link": {"espn_league_id"}, "mfl_link": {"mfl_league_id", "mfl_league_url"},
        "mfl_auth_import": {"league_ids"}}


def test_database_write_fence_denies_a_test_request_under_a_real_league(world):
    eng = world["engine"]
    token = tp.ACTOR.set(PID)
    try:
        row = dict(user_id=PID, league_id=SLEEPER_LG, player_id="p1", elo=1500.0,
                   scoring_format="1qb_ppr", updated_at=_ts())
        with pytest.raises(tp.TestProfileWriteRefused):
            with eng.begin() as conn:
                conn.execute(insert(db.member_rankings_table).values(**row))
        with pytest.raises(tp.TestProfileWriteRefused):      # executemany form
            with eng.begin() as conn:
                conn.execute(insert(db.member_rankings_table), [row])
        with pytest.raises(tp.TestProfileWriteRefused):      # marking a real league stale
            with eng.begin() as conn:
                conn.execute(update(db.leagues_table)
                             .where(db.leagues_table.c.sleeper_league_id == SLEEPER_LG)
                             .values(name="x"))
        with eng.begin() as conn:                              # its own namespace: allowed
            conn.execute(insert(db.member_rankings_table).values(**{**row, "league_id": NS + "1"}))
    finally:
        tp.ACTOR.reset(token)
    with eng.begin() as conn:                                  # a real request: untouched
        conn.execute(update(db.leagues_table)
                     .where(db.leagues_table.c.sleeper_league_id == SLEEPER_LG)
                     .values(name=f"League {SLEEPER_LG}"))


def test_submit_rankings_requires_league_membership_for_every_caller(world, monkeypatch):
    """Pre-existing gap the review found: any session could publish into any
    league. Membership is now required unless it is the session's own league."""
    class _Svc:
        import threading as _t
        _lock = _t.Lock()

        def get_rankings(self, position=None):
            return type("R", (), {"rankings": []})()

    class _Lg:
        league_id = ESPN_LG

    sess = {"user_id": REAL, "service": _Svc(), "league": _Lg(), "verified": True}
    monkeypatch.setattr(server, "_require_initialized_session", lambda: sess)
    monkeypatch.setattr(server, "_ranking_confidence", lambda svc: {})
    monkeypatch.setattr(server, "_confidence_payload", lambda p, conf: p)
    published = []
    monkeypatch.setattr(server, "_publish_member_rankings_for_trade_refresh",
                        lambda **kw: published.append(kw["league_id"]))
    c = world["client"]
    for lid, want in ((ESPN_LG, 200), (MFL_LG, 200), ("424242", 403)):
        r = _call(c, "POST", "/api/rankings/submit", REAL_TOKEN, {"league_id": lid})
        assert r.status_code == want, (lid, r.get_json())
    assert published == [ESPN_LG, MFL_LG]


# ── M2: sweeps and loaders never see a test league ─────────────────────────

def _seed_test_espn_league(engine):
    lid = NS + ESPN_LG
    with engine.begin() as conn:
        conn.execute(insert(db.leagues_table).values(
            sleeper_league_id=lid, user_id=PID, name="copy", platform="espn",
            default_scoring="sf_tep", total_rosters=2, season="2026",
            espn_auth="private", espn_season=2026, espn_my_team_id=1,
            updated_at=_ts(), created_at=_ts()))
        conn.execute(insert(db.trade_decisions_table).values(
            user_id=PID, league_id=lid, trade_id="t1", decision="like", created_at=_ts(),
            give_player_ids="[]", receive_player_ids="[]"))
    return lid


def test_background_loaders_and_the_history_sweep_skip_test_leagues(world, monkeypatch):
    lid = _seed_test_espn_league(world["engine"])
    from backend import roster_history as rh
    now = datetime.now(timezone.utc)
    sweep = db.load_history_sweep_leagues(rh.iso_period_key(now), active_within_days=None)
    assert sweep and all(not lg["league_id"].startswith("qa_tp:") for lg in sweep)
    assert all(not x.startswith("qa_tp:")
               for x in db.load_league_ids_for_draft_status_refresh(active_within_days=None))
    assert all(not p["league_id"].startswith("qa_tp:") and not p["user_id"].startswith("qa_")
               for p in db.load_active_deck_user_leagues())
    fetched = []
    monkeypatch.setattr(server, "_sweep_fetch_teams",
                        lambda lg: (fetched.append(lg["league_id"]), (None, "skip"))[1])
    server._run_roster_snapshot_sweep(now, 100, active_within_days=None)
    assert lid not in fetched and fetched          # real leagues still swept
    monkeypatch.undo()
    # Every trigger's shared tail and the platform adapter refuse it too.
    assert server._sweep_fetch_teams({"league_id": lid, "platform": "espn"}) == (None, "test_profile")
    before = _dump(world["engine"])
    out = server._do_league_history_snapshot(lid, "espn", [{"owner_id": "espn:{X}", "players": []}], "weekly")
    assert out["rosters"] == {"skipped": "test_profile"}
    assert _dump(world["engine"]) == before


# ── L1: structured ids, never free text ────────────────────────────────────

def test_real_names_that_contain_the_text_are_not_test_ids():
    assert tp.outbound_blocked(MATE, league_id=SLEEPER_LG, kind="x",
                               payload={"league_name": "qa_tp league", "username": "qa_tp_fan",
                                        "title": f"qa_tp:{REAL}:1 fans"}) is False
    assert tp.outbound_blocked(MATE, payload="qa_tp league") is False
    assert tp.outbound_blocked(MATE, payload={"new_user_id": PID}) is True
    assert tp.outbound_blocked(MATE, payload={"meta": {"league_id": NS + "1"}}) is True
    assert not server._tp_url_names_test_id("https://api.sleeper.app/v1/user/qa_tp_fan")
    assert not server._tp_url_names_test_id("https://api.sleeper.app/v1/league/123?name=qa_tp")
    assert server._tp_url_names_test_id(f"https://api.sleeper.app/v1/league/{NS}123/rosters")
    assert server._tp_url_names_test_id("https://api.sleeper.app/v1/league/qa_tp%3A111222333%3A1")
    for s in ("qa_tp league", "qa_tp_fan", "qa_tp:", "qa_tpo_short"):
        assert not tp.is_test_world_id(s), s


# ── L2 / L3: gate closing evicts; no existence signal ─────────────────────

def test_closing_the_gate_evicts_test_sessions_from_memory(world):
    tok = _enter(world)
    assert tok.startswith(server._TP_TOKEN_PREFIX)
    with server._sessions_lock:
        assert tok in server._sessions
    world["flags"].discard("dev.test_profile")
    assert server._tp_evict_closed_sessions() >= 1
    with server._sessions_lock:
        assert tok not in server._sessions
        assert not any(s.get("user_id") == PID for s in server._sessions.values())


def test_a_test_session_under_a_real_style_token_is_refused(world):
    with server._sessions_lock:
        server._sessions["forged-real-style"] = {"user_id": PID, "verified": True}
    assert server._get_session("forged-real-style") is None
    with server._sessions_lock:
        assert "forged-real-style" not in server._sessions


# ── L4: reset drains in-flight work and purges caches ─────────────────────

def test_reset_invalidates_pre_reset_work_and_purges_caches(world):
    c = world["client"]
    tok = _enter(world)
    _seed_test_league()
    lease = server._user_data_lifecycle.capture(PID)          # work captured before the reset
    server._FA_LEAGUE_META_CACHE[NS + "1"] = (0.0, {})
    server._FA_LEAGUE_META_CACHE[SLEEPER_LG] = (0.0, {})
    server._LEAGUE_MEMBERS_CACHE[(NS + "1", "x")] = (0.0, [])
    r = _call(c, "POST", "/api/test-profile/reset", tok, {})
    assert r.status_code == 200, r.get_json()
    with lease.active() as admitted:
        assert admitted is False                               # it can never write now
    assert NS + "1" not in server._FA_LEAGUE_META_CACHE
    assert (NS + "1", "x") not in server._LEAGUE_MEMBERS_CACHE
    assert SLEEPER_LG in server._FA_LEAGUE_META_CACHE          # real entries stay
    server._FA_LEAGUE_META_CACHE.pop(SLEEPER_LG, None)
    new = r.get_json()["session_token"]
    with server._user_data_lifecycle.capture(PID).active() as admitted:
        assert admitted is True                                # the fresh incarnation works
    assert server._get_session(new)["user_id"] == PID


# ── L6: nobody else can name a test league ─────────────────────────────────

def test_real_and_anonymous_callers_cannot_name_a_test_league(world):
    c = world["client"]
    tok = _enter(world)
    _seed_test_league()
    path = f"/api/sleeper/rosters/{NS}1"
    assert c.get(path).status_code == 404                                    # anonymous
    assert c.get(path, headers={"X-Session-Token": REAL_TOKEN}).status_code == 404
    assert c.get(f"/api/sleeper/league_users/{NS}1").status_code == 404
    r = c.post("/api/rankings/submit", headers={"X-Session-Token": REAL_TOKEN},
               content_type="text/plain", data=json.dumps({"league_id": NS + "1"}))
    assert r.status_code == 404
    assert c.get(path, headers={"X-Session-Token": tok}).status_code != 404  # its owner


# ── L7: the fence costs a real request nothing ─────────────────────────────

def test_the_fence_never_looks_up_a_real_token(world, monkeypatch):
    calls = []
    real_get = server._get_session
    monkeypatch.setattr(server, "_get_session", lambda t: (calls.append(t), real_get(t))[1])
    with server.app.test_request_context("/api/me/streak",
                                         headers={"X-Session-Token": REAL_TOKEN}):
        assert server._test_profile_request_guard() is None
    assert calls == []
    with server.app.test_request_context("/api/me/streak",
                                         headers={"X-Session-Token": "tp.unknown"}):
        assert server._test_profile_request_guard() is None
    assert calls == ["tp.unknown"]


# ── the request actor is reset even when the request raises ────────────────

def test_actor_is_reset_when_the_request_raises(world, monkeypatch):
    tok = _enter(world)

    def _boom():
        assert tp.ACTOR.get() == PID
        raise RuntimeError("boom")

    monkeypatch.setitem(server.app.view_functions, "test_profile_status", _boom)
    monkeypatch.setitem(server.app.config, "PROPAGATE_EXCEPTIONS", False)
    r = _call(world["client"], "GET", "/api/test-profile", tok)
    assert r.status_code == 500
    assert tp.ACTOR.get() is None


def test_the_fence_never_reads_a_body_past_the_smallest_route_cap(world, monkeypatch):
    """Capped routes (feedback, events) answer 413 before ANY read; the fence
    must not read such a body first, for a real token or a test token."""
    from unittest.mock import patch
    tok = _enter(world)
    big = b"x" * (server._TP_BODY_SCAN_LIMIT + 1)
    assert server._TP_BODY_SCAN_LIMIT <= server.FEEDBACK_MAX_BODY_BYTES
    for t in (REAL_TOKEN, tok, ""):
        with server.app.test_request_context("/api/feedback", method="POST", data=big,
                                             headers={"X-Session-Token": t},
                                             content_type="application/json"):
            with patch.object(server.app.request_class, "get_data",
                              side_effect=AssertionError("body read by the fence")):
                assert server._test_profile_request_guard() is None


# ── second review (2026-11-12) ─────────────────────────────────────────────

def _route_body_caps():
    """Every Content-Length cap a route in backend/ checks before reading,
    resolved to bytes: `content_length … > N` and `max_content_length = N`."""
    import importlib
    import pathlib
    import re
    root = pathlib.Path(server.__file__).parent
    caps = []
    pat = re.compile(r"content_length[^\n]*?(?:>|=)\s*([A-Z_][A-Z0-9_]*|\d[\d_]*)(\s*\+\s*1)?")
    for path in root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        mod = None
        for m in pat.finditer(path.read_text()):
            tok = m.group(1)
            if tok[0].isdigit():
                val = int(tok.replace("_", ""))
            else:
                if mod is None:
                    rel = path.relative_to(root.parent).with_suffix("")
                    mod = importlib.import_module(".".join(rel.parts))
                val = getattr(mod, tok, None)
                if not isinstance(val, int):
                    continue
            caps.append((f"{path.name}:{tok}", val))
    return caps


def test_the_body_scan_limit_is_at_most_every_route_cap():
    """A route that answers 413 from Content-Length must never have its body
    read by the fence first, so the fence's limit is the smallest cap."""
    caps = _route_body_caps()
    names = {n for n, _ in caps}
    assert any("api.py:8192" in n for n in names), names          # projection runs
    assert any("FEEDBACK_MAX_BODY_BYTES" in n for n in names), names
    assert any("MAX_CONTENT_LENGTH" in n for n in names), names
    too_small = [(n, v) for n, v in caps if v < server._TP_BODY_SCAN_LIMIT]
    assert too_small == [], f"a route cap is below the fence's scan limit: {too_small}"


def test_a_wrong_content_type_request_behaves_as_without_the_feature(world):
    """The fence parses with cache=False: a route's own non-forced get_json()
    on a text/plain request still sees no JSON, marker text or not."""
    from werkzeug.exceptions import UnsupportedMediaType
    for body in ('{"league_id": "900100", "note": "a qa_tp league"}',
                 '{"league_id": "900100", "note": "plain"}'):
        for tok in (REAL_TOKEN, ""):
            with server.app.test_request_context(
                    "/api/rankings/submit", method="POST", data=body,
                    headers={"X-Session-Token": tok}, content_type="text/plain"):
                assert server._test_profile_request_guard() is None
                assert server.request.get_json(silent=True) is None
                with pytest.raises(UnsupportedMediaType):
                    server.request.get_json()


def test_the_cache_purge_takes_each_caches_own_lock(world):
    """A purge can never land between another thread's get(key) == job and
    its pop(key): it waits for _trade_jobs_lock."""
    import threading
    key = (PID, NS + "1", "1qb_ppr")
    server._trade_jobs_by_key[key] = "job-1"
    done = threading.Event()
    with server._trade_jobs_lock:
        t = threading.Thread(target=lambda: (server._tp_purge_caches(PID), done.set()))
        t.start()
        assert not done.wait(0.3)                  # blocked behind the lock
        assert server._trade_jobs_by_key.get(key) == "job-1"
        server._trade_jobs_by_key.pop(key)         # the finishing thread's own pop
    t.join(5)
    assert done.is_set()
    for name, lock_name in server._TP_KEYED_CACHES:
        assert isinstance(getattr(server, name), dict), name
        assert lock_name is None or hasattr(getattr(server, lock_name), "acquire"), lock_name


def test_a_failing_sweep_never_fails_the_flag_reload(world, monkeypatch):
    def boom():
        raise RuntimeError("sweep broke")
    monkeypatch.setattr(server, "_tp_evict_closed_sessions", boom)
    monkeypatch.setattr(server, "_CRON_SECRET", "s3")
    monkeypatch.setattr(server, "reload_flags", lambda: {})
    r = world["client"].post("/api/feature-flags/reload", headers={"X-Cron-Secret": "s3"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
