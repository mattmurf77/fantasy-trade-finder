"""Sign-in timing fix (legal R28.17 condition 4).

POST /api/extension/auth and the POST /api/entry/platform mint are
UNVERIFIED sign-ins. They used to replay the user's swipe history and tier
overrides while building the session, so the response time revealed whether
a typed username had FTF history. They now build with `load_history=False`
(session marked `_history_pending`), and the in-place verify routes
(`sleeper_link` proven-live, `mfl_auth_link`) hydrate the history with
`_hydrate_session_history` immediately BEFORE `verified` flips.

head-eng's condition: a hydration failure refuses the verify with a
retryable 503 `verify_retry` + Retry-After, leaving the session unverified
and still pending, so a retry hydrates exactly once.

Flask test client + in-memory SQLite. No network: the Sleeper user lookup,
the token oracle, MFL login and the player pools are all stubbed.
"""
import base64
import copy
import json
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

import backend.database as db_module
import backend.espn_service as es
import backend.mfl_service as mfl
import backend.server as server
import backend.sleeper_write as sw
from backend.database import metadata
from backend.ranking_service import Player, RankingService

UID = "313560442465169408"       # has FTF history (swipes + pins)
UID_NEW = "424242424242424242"   # has a users row, no history
FORMATS = tuple(server.SCORING_FORMATS)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
MFL_FIXTURE = os.path.join(FIXTURES, "mfl_league_snapshot_2026-07-17.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")
ENTRY_UID = "entry:mfl:10005.f0001"

POOL = [Player(f"{pos.lower()}_{i}", f"{pos} {i}", pos, "AAA", 25, 3)
        for pos in ("QB", "RB", "WR", "TE") for i in range(1, 5)]
SEEDS = {
    "1qb_ppr": {p.id: 1800.0 - 100 * int(p.id[-1]) for p in POOL},
    "sf_tep":  {p.id: 1850.0 - 90 * int(p.id[-1]) for p in POOL},
}
SLEEPER_USERS = {
    "hist":  {"user_id": UID, "display_name": "Hist", "avatar": None},
    "fresh": {"user_id": UID_NEW, "display_name": "Fresh", "avatar": None},
}


def _fake_jwt(user_id):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    claims = {"user_id": user_id, "exp": int(time.time()) + 3600}
    return f"{b64({'alg': 'HS256'})}.{b64(claims)}.sig"


def _fake_sleeper_get(url, timeout=15):
    if "/leagues/" in url:
        return []
    return SLEEPER_USERS.get(url.rsplit("/", 1)[-1])


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


def _seed_history(user_id):
    """Rank swipes in both formats + a pin with a stamp."""
    db_module.upsert_user(sleeper_user_id=user_id, username="hist",
                          display_name="Hist")
    db_module.save_ranking_swipes(user_id, ["rb_4", "rb_1", "rb_2"],
                                  scoring_format="1qb_ppr")
    db_module.save_ranking_swipes(user_id, ["wr_3", "wr_1", "wr_2"],
                                  scoring_format="1qb_ppr")
    db_module.save_ranking_swipes(user_id, ["qb_4", "qb_1", "qb_3"],
                                  scoring_format="sf_tep")
    db_module.save_tier_overrides(user_id, {"te_4": 1950.0},
                                  scoring_format="1qb_ppr",
                                  stamps={"te_4": "2026-10-01T00:00:00+00:00"})


@pytest.fixture()
def world(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    # StaticPool: one shared in-memory DB across threads (the concurrency
    # test hydrates from worker threads).
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    metadata.create_all(engine)
    flags = {"trade.send_in_sleeper", "mfl.auth_link",
             "landing.platform_options", "mfl.link"}

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(server, "is_enabled", lambda k: k in flags)
    monkeypatch.setattr(server, "touch_user_activity", MagicMock())
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "_get_universal_pool",
                        lambda fmt: (list(POOL), dict(SEEDS[fmt])))
    monkeypatch.setattr(server, "_sleeper_get", _fake_sleeper_get)
    monkeypatch.setattr(server, "_link_device_identity", lambda **kw: None)
    monkeypatch.setattr(sw, "verify_token_live", lambda token, **kw: {})

    w = SimpleNamespace(engine=engine, flags=flags,
                        calls={"swipes": 0, "overrides": 0, "stamps": 0,
                               "replay": 0},
                        on_load=None, fail_format=None)

    real_swipes = server.load_swipe_decisions
    real_overrides = server.load_tier_overrides
    real_stamps = server.load_tier_override_stamps
    real_replay = RankingService.replay_from_db

    def spy_swipes(*a, **kw):
        w.calls["swipes"] += 1
        if w.on_load:
            w.on_load()
        if w.fail_format is not None and kw.get("scoring_format") == w.fail_format:
            raise RuntimeError("db unavailable")
        return real_swipes(*a, **kw)

    def spy_overrides(*a, **kw):
        w.calls["overrides"] += 1
        return real_overrides(*a, **kw)

    def spy_stamps(*a, **kw):
        w.calls["stamps"] += 1
        return real_stamps(*a, **kw)

    def spy_replay(self, swipes):
        w.calls["replay"] += 1
        return real_replay(self, swipes)

    monkeypatch.setattr(server, "load_swipe_decisions", spy_swipes)
    monkeypatch.setattr(server, "load_tier_overrides", spy_overrides)
    monkeypatch.setattr(server, "load_tier_override_stamps", spy_stamps)
    monkeypatch.setattr(RankingService, "replay_from_db", spy_replay)

    server.app.config["TESTING"] = True
    w.client = server.app.test_client()
    before = set(server._sessions)
    try:
        yield w
    finally:
        with server._sessions_lock:
            for t in set(server._sessions) - before:
                server._sessions.pop(t, None)


def _reset_calls(w):
    for k in w.calls:
        w.calls[k] = 0


def _live(token):
    with server._sessions_lock:
        return server._sessions[token]


def _auth(w, username="hist"):
    r = w.client.post("/api/extension/auth", json={"username": username})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["session_token"]


def _link(w, token, user_id=UID):
    return w.client.post("/api/sleeper/link", headers=_h(token),
                         data=json.dumps({"token": _fake_jwt(user_id)}))


def _board(svc):
    """Everything the history load sets on a service, in comparable form."""
    return {
        "rankings": {pos: [(rp.player.id, rp.elo)
                           for rp in svc.get_rankings(position=pos).rankings]
                     for pos in ("QB", "RB", "WR", "TE")},
        "swipes": len(svc._swipes),
        "overrides": dict(svc._elo_overrides),
        "override_at": dict(svc._elo_override_at),
    }


def _stored_rank_rows(user_id, fmt):
    return len(db_module.load_swipe_decisions(user_id=user_id, scoring_format=fmt))


# ── 1. Unverified sign-ins never touch the history loaders ─────────────────

def test_extension_auth_defers_history(world):
    _seed_history(UID)
    _reset_calls(world)
    token = _auth(world)
    assert world.calls == {"swipes": 0, "overrides": 0, "stamps": 0, "replay": 0}
    sess = _live(token)
    assert sess["_history_pending"] is True
    assert not sess.get("verified")
    # Pristine services: seed ratings only, nothing replayed or pinned.
    for fmt in FORMATS:
        svc = sess["services"][fmt]
        assert svc._swipes == [] and svc._elo_overrides == {}


def test_entry_mint_defers_history(world, monkeypatch):
    _seed_history(ENTRY_UID)
    xwalk = es.load_crosswalk(XWALK_FIXTURE)
    with open(MFL_FIXTURE) as f:
        bundle = json.load(f)
    monkeypatch.setattr(es, "get_crosswalk", lambda _opener=None: xwalk)
    monkeypatch.setattr(mfl, "resolve_host",
                        lambda *a, **kw: "www48.myfantasyleague.com")
    monkeypatch.setattr(mfl, "fetch_league_bundle",
                        lambda *a, **kw: copy.deepcopy(bundle))
    _reset_calls(world)
    r = world.client.post("/api/entry/platform", json={
        "platform": "mfl", "mfl_league_id": "10005", "year": 2026,
        "franchise_id": "0001"})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["user_id"] == ENTRY_UID
    assert world.calls == {"swipes": 0, "overrides": 0, "stamps": 0, "replay": 0}
    sess = _live(body["session_token"])
    assert sess["_history_pending"] is True and not sess.get("verified")


def test_extension_auth_work_is_identical_with_and_without_history(world):
    """The oracle itself: the same loader calls (none) and the same number
    of SQL statements whether or not the typed username has history."""
    _seed_history(UID)
    db_module.upsert_user(sleeper_user_id=UID_NEW, username="fresh",
                          display_name="Fresh")
    statements = []

    def count(*a, **kw):
        statements.append(1)
    event.listen(world.engine, "before_cursor_execute", count)
    try:
        observed = {}
        for name in ("hist", "fresh"):
            _reset_calls(world)
            statements.clear()
            _auth(world, name)
            observed[name] = (dict(world.calls), len(statements))
    finally:
        event.remove(world.engine, "before_cursor_execute", count)
    zero = {"swipes": 0, "overrides": 0, "stamps": 0, "replay": 0}
    assert observed["hist"][0] == observed["fresh"][0] == zero
    assert observed["hist"][1] == observed["fresh"][1]


# ── 2. Verify hydrates first, then flips verified ──────────────────────────

def test_sleeper_link_hydrates_before_verified_flips(world):
    _seed_history(UID)
    token = _auth(world)
    seen = []
    world.on_load = lambda: seen.append(_live(token).get("verified"))
    _reset_calls(world)
    r = _link(world, token)
    assert r.status_code == 200 and r.get_json()["verified"] is True
    assert seen and not any(seen), "history loaded after verified flipped"
    sess = _live(token)
    assert sess["verified"] is True and "_history_pending" not in sess
    assert world.calls["swipes"] == len(FORMATS)
    assert world.calls["replay"] == len(FORMATS)   # both formats have rows
    for fmt in FORMATS:
        assert len(sess["services"][fmt]._swipes) == _stored_rank_rows(UID, fmt)
    assert sess["service"] is sess["services"][server.DEFAULT_SCORING]


def test_mfl_auth_link_gate_still_refuses_a_pending_session(world):
    """Today the write gate 403s an unverified session before its verify,
    so the MFL hydrate is defensive: nothing loads, nothing changes."""
    _seed_history(UID)
    token = _auth(world)
    _reset_calls(world)
    with patch.object(mfl, "login") as login:
        r = world.client.post("/api/mfl/auth-link", headers=_h(token),
                              data=json.dumps({"username": "u", "password": "p"}))
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"
    login.assert_not_called()
    assert world.calls["swipes"] == 0
    sess = _live(token)
    assert sess["_history_pending"] is True and not sess.get("verified")


def _call_mfl_auth_link_body(token):
    """Run mfl_auth_link's body past its write gate (functools.wraps keeps
    the undecorated function on __wrapped__) to pin the defensive hydrate."""
    with patch.object(mfl, "login",
                      lambda u, p, y, **kw: {"cookie": "MFL_USER_ID=x"}), \
         patch.object(mfl, "fetch_my_leagues", lambda c, y, **kw: []), \
         server.app.test_request_context(
             "/api/mfl/auth-link", method="POST", headers=_h(token),
             data=json.dumps({"username": "u", "password": "p", "year": 2026})):
        out = server.mfl_auth_link.__wrapped__()
        resp = server.app.make_response(out)
        return resp.status_code, resp.get_json(), dict(resp.headers)


def test_mfl_auth_link_body_hydrates_before_verified_flips(world):
    _seed_history(UID)
    token = _auth(world)
    seen = []
    world.on_load = lambda: seen.append(_live(token).get("verified"))
    _reset_calls(world)
    status, body, _ = _call_mfl_auth_link_body(token)
    assert status == 200 and body["verified"] is True
    assert seen and not any(seen)
    sess = _live(token)
    assert sess["verified"] is True and "_history_pending" not in sess
    assert world.calls["replay"] == len(FORMATS)


# ── 3. Single-flight: never a double replay ────────────────────────────────

def test_second_link_does_not_replay_again(world):
    _seed_history(UID)
    token = _auth(world)
    assert _link(world, token).status_code == 200
    _reset_calls(world)
    assert _link(world, token).status_code == 200
    assert world.calls == {"swipes": 0, "overrides": 0, "stamps": 0, "replay": 0}
    sess = _live(token)
    for fmt in FORMATS:
        assert len(sess["services"][fmt]._swipes) == _stored_rank_rows(UID, fmt)


def test_concurrent_hydration_replays_once(world):
    _seed_history(UID)
    token = _auth(world)
    sess = _live(token)
    entered, release = threading.Event(), threading.Event()

    def hold_first_loader():
        if not entered.is_set():
            entered.set()
            release.wait(5)
    world.on_load = hold_first_loader
    _reset_calls(world)

    errors = []

    def run():
        try:
            server._hydrate_session_history(sess)
        except Exception as e:   # pragma: no cover — surfaced below
            errors.append(e)

    t1 = threading.Thread(target=run)
    t1.start()
    assert entered.wait(5)
    t2 = threading.Thread(target=run)
    t2.start()
    time.sleep(0.1)          # t2 is now parked on the session's lock
    release.set()
    t1.join(5)
    t2.join(5)
    assert not errors
    assert world.calls["replay"] == len(FORMATS)
    assert world.calls["swipes"] == len(FORMATS)
    for fmt in FORMATS:
        assert len(sess["services"][fmt]._swipes) == _stored_rank_rows(UID, fmt)
    assert "_history_pending" not in sess


# ── 4. Deferred + hydrated == eager ────────────────────────────────────────

def test_rankings_after_auth_and_link_match_an_eager_build(world):
    _seed_history(UID)
    token = _auth(world)
    assert _link(world, token).status_code == 200

    eager_tok, eager = server._extension_build_session(
        user_id=UID, username="hist", display_name="Hist", avatar=None)
    assert "_history_pending" not in eager
    eager["verified"] = True

    def rankings(tok):
        r = world.client.get("/api/extension/rankings", headers=_h(tok))
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        body.pop("updated_at")
        return body

    deferred_body, eager_body = rankings(token), rankings(eager_tok)
    assert deferred_body == eager_body
    assert deferred_body["players"]          # a non-trivial board
    live = _live(token)
    for fmt in FORMATS:
        assert _board(live["services"][fmt]) == _board(eager["services"][fmt])
    assert live["services"]["1qb_ppr"]._elo_overrides == {"te_4": 1950.0}


# ── 5. Every other caller stays eager ──────────────────────────────────────

def test_default_build_is_eager(world):
    _seed_history(UID)
    _reset_calls(world)
    _, payload = server._extension_build_session(
        user_id=UID, username="hist", display_name="Hist", avatar=None)
    assert "_history_pending" not in payload and "_history_lock" not in payload
    assert world.calls["swipes"] == world.calls["overrides"] == len(FORMATS)
    assert world.calls["replay"] == len(FORMATS)


def test_persisted_session_restore_is_eager(world):
    _seed_history(UID)
    world.flags.add("auth.persistent_sessions")
    db_module.persist_session("restore-tok", user_id=UID,
                              verified_via="sleeper", username="hist",
                              display_name="Hist")
    _reset_calls(world)
    sess = server._get_session("restore-tok")
    assert sess is not None and sess["verified"] is True
    assert "_history_pending" not in sess
    assert world.calls["replay"] == len(FORMATS)
    for fmt in FORMATS:
        assert len(sess["services"][fmt]._swipes) == _stored_rank_rows(UID, fmt)


def test_account_build_is_eager(world):
    acct_uid = "acct_feedface"
    _seed_history(acct_uid)
    _reset_calls(world)
    _, payload = server._account_build_session(acct_uid, "Manager")
    assert "_history_pending" not in payload
    assert world.calls["replay"] == len(FORMATS)
    assert payload["services"]["1qb_ppr"]._elo_overrides == {"te_4": 1950.0}


def test_eager_build_still_swallows_load_failures(world):
    """The eager callers' behaviour is unchanged: a failed load is logged
    and the session is built anyway (partial board), as before."""
    _seed_history(UID)
    world.fail_format = "sf_tep"
    _, payload = server._extension_build_session(
        user_id=UID, username="hist", display_name="Hist", avatar=None)
    assert payload["services"]["sf_tep"]._swipes == []
    assert len(payload["services"]["1qb_ppr"]._swipes) == \
        _stored_rank_rows(UID, "1qb_ppr")


# ── 6. head-eng's condition: a failed hydrate refuses the verify ────────────

def test_hydration_failure_refuses_verify_with_retryable_503(world):
    _seed_history(UID)
    token = _auth(world)
    # Fail on the SECOND format: the first one has already replayed into a
    # fresh service by then — that partial work must never reach the session.
    world.fail_format = FORMATS[-1]
    _reset_calls(world)
    r = _link(world, token)
    assert r.status_code == 503
    body = r.get_json()
    assert body["error"] == "verify_retry"
    assert isinstance(body["message"], str) and body["message"]
    assert int(r.headers["Retry-After"]) > 0
    sess = _live(token)
    assert not sess.get("verified")
    assert sess.get("_history_pending") is True
    for fmt in FORMATS:                       # nothing half-replayed
        assert sess["services"][fmt]._swipes == []
        assert sess["services"][fmt]._elo_overrides == {}
    # Private reads stay closed while unverified.
    assert world.client.get("/api/extension/rankings",
                            headers=_h(token)).status_code == 403

    # Retry once the store is back: verifies, replays exactly once.
    world.fail_format = None
    _reset_calls(world)
    r2 = _link(world, token)
    assert r2.status_code == 200 and r2.get_json()["verified"] is True
    assert world.calls["replay"] == len(FORMATS)
    sess = _live(token)
    assert sess["verified"] is True and "_history_pending" not in sess
    for fmt in FORMATS:
        assert len(sess["services"][fmt]._swipes) == _stored_rank_rows(UID, fmt)
    assert sess["services"]["1qb_ppr"]._elo_overrides == {"te_4": 1950.0}


def test_mfl_body_hydration_failure_refuses_verify(world):
    _seed_history(UID)
    token = _auth(world)
    world.fail_format = FORMATS[0]
    status, body, headers = _call_mfl_auth_link_body(token)
    assert status == 503 and body["error"] == "verify_retry"
    assert int(headers["Retry-After"]) > 0
    sess = _live(token)
    assert not sess.get("verified") and sess.get("_history_pending") is True
