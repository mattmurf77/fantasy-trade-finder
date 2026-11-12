"""Onboarding test profile — REAL Sleeper onboarding (operator ruling 2026-11-12).

Plan: docs/plans/onboarding-test-profile/design.md §12.

Inside a test profile the production Sleeper path runs — the username step
(/api/extension/auth), league discovery (/api/sleeper/leagues), roster
resolution (/api/sleeper/rosters|league_users), session init and the first
deck request — against the recorded co-owned-league capture
(fixtures/sleeper/co-owned-league, with every real id replaced by a synthetic
one here). Three defences, each tested and sabotage-checked:

  identity   server._sleeper_identity(sess): the session's own user id for
             every real session (pinned byte-identical + an AST guard over
             every site that reads Sleeper with a session-derived id); the
             real account's Sleeper id for the test profile, used for reads
  re-key     every member id stored for a namespaced league goes through
             test_profile.masked_member_id — in session_input, the roster
             proxies AND the league_members writers (a missed upstream
             re-key is still caught at the write)
  outbound   test_profile.outbound_blocked at the narrowest writers: push
             (_send_typed_push), inbox (create_notification, the join
             coalescer), queue (queue_notification), matches
             (create_trade_match), referral credit (claim_referral) and the
             platform-write cores

The decisive test runs the whole onboarding and then scans every table
derived from backend/database.py: (a) no test-profile row holds a real
league-mate id or the real league id, (b) every real row is byte-identical,
(c) nothing was delivered to anyone.
"""
import ast
import copy
import json
import pathlib
import time
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.pool import StaticPool

import backend.database as db
import backend.server as server
import backend.test_profile as tp

pytestmark = pytest.mark.usefixtures("no_real_network")

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "sleeper" / "co-owned-league"
LEAGUE = "990011223344556677"           # synthetic stand-in for the captured league id


def _synth_world():
    """The captured league with every real id replaced deterministically."""
    rosters = json.loads((FIX / "rosters.json").read_text())
    users = json.loads((FIX / "users.json").read_text())
    real_ids = sorted({str(r["owner_id"]) for r in rosters if r.get("owner_id")}
                      | {str(c) for r in rosters for c in (r.get("co_owners") or [])}
                      | {str(u["user_id"]) for u in users})
    idmap = {rid: f"8{i:017d}" for i, rid in enumerate(real_ids, start=1)}
    for r in rosters:
        r["owner_id"] = idmap.get(str(r.get("owner_id")), r.get("owner_id"))
        r["co_owners"] = [idmap[str(c)] for c in (r.get("co_owners") or [])] or None
        r["league_id"] = LEAGUE
    for u in users:
        u["user_id"] = idmap[str(u["user_id"])]
        u["username"] = f"user{u['user_id'][-4:]}"
        u["display_name"] = u["username"]
    co_owned = next(r for r in rosters if r.get("co_owners"))
    real = co_owned["co_owners"][0]          # the operator: a CO-OWNER
    return rosters, users, real, co_owned["owner_id"]


ROSTERS, USERS, REAL, PRIMARY = _synth_world()
PID = "qa_tp_" + REAL
STORE = f"qa_tp:{REAL}:{LEAGUE}"
MATES = sorted({str(r["owner_id"]) for r in ROSTERS if r.get("owner_id")} - {REAL})
OPS_USERNAME = next(u["username"] for u in USERS if u["user_id"] == REAL)
FRIEND_USERNAME = next(u["username"] for u in USERS if u["user_id"] == MATES[0])
META = {"league_id": LEAGUE, "name": "Bush League", "season": "2026", "total_rosters": 12,
        "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", "BN"],
        "scoring_settings": {"rec": 1.0, "pass_td": 4.0}, "settings": {"type": 2}}
REAL_TOK = "tps-real-token"


def _dump(engine):
    out = {}
    with engine.connect() as conn:
        for t in db.metadata.sorted_tables:
            out[t.name] = sorted((tuple(r) for r in conn.execute(select(t))), key=repr)
    return out


def _is_test_row(row) -> bool:
    text = repr(row)
    return PID in text or "qa_tp:" in text or tp.OPPONENT_PREFIX in text


# Tables keyed by a user or a league (derived from database.py, as the reset
# scope is). Global tables (model config, player pool, audition state) are
# not "a real user's row"; the product-wide aggregates that read user rows
# skip qa_ ids (test_global_learning_signals_skip_the_test_profile).
KEYED = {name for name, *_ in tp.reset_scope()}


def _real_rows(dump):
    return {t: [r for r in rows if not _is_test_row(r)] for t, rows in dump.items()
            if t in KEYED}


def _leaks(dump):
    """(a): cells of test-profile rows that carry a real league-mate id or
    the real league id outside the namespaced id itself."""
    bad = []
    for t, rows in dump.items():
        for r in rows:
            if not _is_test_row(r):
                continue
            text = repr(r).replace(f"qa_tp:{REAL}:", "qa_tp:<ns>:").replace(PID, "")
            text = text.replace(f"qa_tp:<ns>:{LEAGUE}", "")
            hits = [m for m in MATES if m in text] + ([LEAGUE] if LEAGUE in text else []) \
                + ([REAL] if REAL in text else [])
            if hits:
                bad.append((t, hits, r))
    return bad


@pytest.fixture()
def world(monkeypatch):
    yield from _world(monkeypatch)


@pytest.fixture()
def world_threads(monkeypatch, tmp_path):
    """The same world with PRODUCTION threading: the session-init daemon and
    the trade jobs run on their own threads, where the request's ACTOR
    contextvar is not inherited (Python 3.12). A file database, so the
    threads each get their own connection."""
    yield from _world(monkeypatch, real_threads=tmp_path / "tp.db")


def _world(monkeypatch, real_threads=None):
    monkeypatch.setenv(tp.ENV_VAR, REAL)
    if real_threads is None:
        engine = create_engine("sqlite://", poolclass=StaticPool,
                               connect_args={"check_same_thread": False})
    else:
        engine = create_engine(f"sqlite:///{real_threads}",
                               connect_args={"check_same_thread": False, "timeout": 30})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    flags = {"dev.test_profile", "league.projections", "auth.persistent_sessions"}
    monkeypatch.setattr(server, "is_enabled", lambda k: k in flags)

    calls = []

    def _fake_sleeper_get(url, timeout=15):
        calls.append(url)
        assert "qa_tp" not in url, f"a namespaced id reached Sleeper: {url}"
        tail = url.split("/v1/", 1)[-1]
        if tail == f"user/{OPS_USERNAME}":
            return {"user_id": REAL, "username": OPS_USERNAME, "display_name": OPS_USERNAME}
        if tail == f"user/{FRIEND_USERNAME}":
            return {"user_id": MATES[0], "username": FRIEND_USERNAME}
        if tail == f"user/{REAL}/leagues/nfl/2026":
            return [{"league_id": LEAGUE, "name": "Bush League", "total_rosters": 12,
                     "settings": {"type": 2}}]
        if tail == f"league/{LEAGUE}/rosters":
            return copy.deepcopy(ROSTERS)
        if tail == f"league/{LEAGUE}/users":
            return copy.deepcopy(USERS)
        if tail == f"league/{LEAGUE}":
            return dict(META)
        raise AssertionError(f"unexpected Sleeper GET {url}")

    monkeypatch.setattr(server, "_sleeper_get", _fake_sleeper_get)

    from backend.ranking_service import Player
    pids = sorted({str(p) for r in ROSTERS for p in (r.get("players") or [])})
    pos = ["QB", "RB", "WR", "TE"]
    pool = [Player(p, f"Player {p}", pos[i % 4], "AAA", 25, 1) for i, p in enumerate(pids)]
    seed = {p.id: 1500.0 + (i % 40) * 10 for i, p in enumerate(pool)}
    pools = {"1qb_ppr": {"players": pool, "seed": seed}, "sf_tep": {"players": pool, "seed": seed}}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", pools)
    monkeypatch.setattr(server, "g_universal_players", pool)
    monkeypatch.setattr(server, "g_players", pool, raising=False)
    monkeypatch.setattr(server, "_refresh_league_draft_status", lambda *a, **k: None)
    sends = []
    monkeypatch.setattr(server, "_send_expo_push", lambda msgs: sends.append(msgs))
    started = []
    if real_threads is None:
        # Trade jobs (the session-init pre-gen and the first deck request)
        # run on the request thread here, so nothing outlives the database.
        _real_kickoff = server._kickoff_trade_job
        monkeypatch.setattr(server, "_kickoff_trade_job",
                            lambda *a, **k: _real_kickoff(*a, **{**k, "synchronous": True}))

        real_thread = server.threading.Thread

        class _Inline(real_thread):
            def start(self):
                if self.name == "session-init-bg-writes":
                    self.run()
                    return
                super().start()

        monkeypatch.setattr(server.threading, "Thread", _Inline)
    else:
        real_thread = server.threading.Thread

        class _Tracked(real_thread):
            def start(self):
                started.append(self)
                super().start()

        monkeypatch.setattr(server.threading, "Thread", _Tracked)

    # The REAL world: the operator and every league-mate are app users; the
    # operator already synced this league, ranked and set preferences.
    now = "2026-11-01T00:00:00+00:00"
    for uid in [REAL] + MATES:
        db.upsert_user(uid, username=f"app{uid[-4:]}", display_name=f"App {uid[-4:]}")
    with engine.begin() as conn:
        conn.execute(db.users_table.update().values(signup_at=now, first_init_pending=0))
        conn.execute(insert(db.leagues_table).values(
            sleeper_league_id=LEAGUE, user_id=REAL, name="Bush League", platform="sleeper",
            season="2026", default_scoring="sf_tep", total_rosters=12))
        for r in ROSTERS:
            conn.execute(insert(db.league_members_table).values(
                league_id=LEAGUE, user_id=r["owner_id"], username="m", display_name="m",
                roster_data=json.dumps(r.get("players") or []), updated_at=now))
        conn.execute(insert(db.member_rankings_table).values(
            user_id=REAL, league_id=LEAGUE, player_id=pids[0], elo=1600.0,
            scoring_format="1qb_ppr", updated_at=now))
        conn.execute(insert(db.league_preferences_table).values(
            user_id=REAL, league_id=LEAGUE, team_outlook="contender", updated_at=now))
    for i, uid in enumerate([REAL] + MATES):
        db.save_device_token(uid, f"ExponentPushToken[dev{i}]", "ios")

    with server._sessions_lock:
        server._sessions[REAL_TOK] = {"user_id": REAL, "verified": True,
                                      "last_active": time.time(), "_persisted_at": time.time()}
    tp.BLOCKED.clear()
    server.app.config["TESTING"] = True
    try:
        yield {"client": server.app.test_client(), "engine": engine, "calls": calls,
               "sends": sends, "threads": started}
    finally:
        for t in started:
            t.join(timeout=60)
        with server._sessions_lock:
            for t in [t for t, s in server._sessions.items()
                      if s.get("user_id") in (PID, REAL)]:
                server._sessions.pop(t, None)
        engine.dispose()


def _post(w, tok, path, body):
    return w["client"].post(path, headers={"X-Session-Token": tok,
                                           "Content-Type": "application/json"},
                            data=json.dumps(body))


def _get(w, tok, path):
    return w["client"].get(path, headers={"X-Session-Token": tok})


def _onboard(w):
    """The production Sleeper path a new user runs, in the test profile."""
    tok = _post(w, REAL_TOK, "/api/test-profile/enter", {}).get_json()["session_token"]
    r = _post(w, tok, "/api/extension/auth", {"username": OPS_USERNAME})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["user_id"] == PID and body["session_token"] == tok
    assert [lg["league_id"] for lg in body["leagues"]] == [STORE]
    leagues = _get(w, tok, f"/api/sleeper/leagues/{PID}").get_json()
    assert [lg["league_id"] for lg in leagues] == [STORE]
    rosters = _get(w, tok, f"/api/sleeper/rosters/{STORE}").get_json()
    users = _get(w, tok, f"/api/sleeper/league_users/{STORE}").get_json()
    mine = [r for r in rosters if r["owner_id"] == PID]
    assert len(mine) == 1                               # the co-owned roster is the profile's
    assert all(r["owner_id"] == PID or r["owner_id"].startswith("qa_tpo_") for r in rosters)
    assert all(u["user_id"] == PID or u["user_id"].startswith("qa_tpo_") for u in users)
    r = _post(w, tok, "/api/session/init", {"user_id": PID, "league_id": STORE})
    assert r.status_code == 200, r.get_json()
    return tok


def _first_deck(w, tok):
    r = _post(w, tok, "/api/trades/generate", {"league_id": STORE})
    assert r.status_code in (200, 202), r.get_json()
    job = r.get_json().get("job_id")
    deadline = time.time() + 30
    while time.time() < deadline:
        with server._trade_jobs_lock:
            st = (server._trade_jobs.get(job) or {}).get("status")
        if st in ("complete", "error", None):
            break
        time.sleep(0.05)
    return job


# ── identity accessor ──────────────────────────────────────────────────────

def test_sleeper_identity_is_the_session_user_for_every_real_session():
    for uid in ("313", "acct_9f8e", "demo_user_ab12", "qa_1a2b3c4d", ""):
        assert server._sleeper_identity({"user_id": uid}) == uid
    assert server._sleeper_identity(None) == ""
    assert server._sleeper_identity({"user_id": PID}) == REAL


SERVER = pathlib.Path(server.__file__)
SESSION_INPUT = pathlib.Path(server.__file__).with_name("session_input.py")


def test_sleeper_reads_with_a_session_id_go_through_the_accessor():
    """Every place that reads Sleeper with an id taken from the SESSION
    (the username/discovery/roster seams) uses the accessor; session_input's
    roster resolution uses the identity it is handed."""
    tree = ast.parse(SESSION_INPUT.read_text())
    finds = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "find_user_roster"]
    assert finds and all(ast.unparse(n.args[1]) == "sleeper_uid" for n in finds)
    src = SERVER.read_text()
    assert '{"sleeper_identity": _sleeper_identity(existing_sess)}' in src
    assert src.count("fetch_uid = _sleeper_identity(caller)") == 1
    assert src.count("mine = _fur(rosters, _sleeper_identity(caller))") == 2
    assert "if str(user_id) != _sleeper_identity(_tp_caller):" in src


# ── the decisive scan ──────────────────────────────────────────────────────

def test_full_sleeper_onboarding_reaches_nobody_and_writes_nothing_real(world):
    w = world
    before = _real_rows(_dump(w["engine"]))
    tok = _onboard(w)
    sess = server._get_session(tok)
    assert server._league_user_id(sess) == PID
    assert {m.user_id for m in sess["league"].members} <= {
        m for m in (tp.masked_member_id(STORE, x, own_ids=(PRIMARY,)) for x in MATES)}
    _first_deck(w, tok)
    after = _dump(w["engine"])
    assert _leaks(after) == []                                    # (a)
    assert _real_rows(after) == before                            # (b)
    assert w["sends"] == []                                       # (c) no push
    assert all("qa_tp" not in c for c in w["calls"])              # only native ids read
    with w["engine"].connect() as conn:                           # (c) no cross-user rows
        assert conn.execute(select(db.notifications_table)).fetchall() == []
        assert conn.execute(select(db.trade_matches_table)).fetchall() == []
        tok_owner = dict(conn.execute(select(db.device_tokens_table.c.device_token,
                                             db.device_tokens_table.c.user_id)).all())
    assert PID not in tok_owner.values()
    with w["engine"].connect() as conn:                           # projections never registered
        assert conn.execute(select(db.league_projection_targets_table)).fetchall() == []


def test_background_threads_hold_isolation_without_the_request_actor(world_threads, monkeypatch):
    """Review: production threads do not inherit the request's ACTOR. Run the
    session-init daemon and the trade jobs on REAL threads, prove ACTOR is
    None there, and prove the decisive scan still holds — isolation rests on
    the namespace and the re-key alone, not on the contextvar."""
    w = world_threads
    seen = {}
    real_members = server.write_session_init_members
    real_start = server._start_trade_job_thread

    def _members(*a, **k):
        seen.setdefault("daemon", []).append(tp.ACTOR.get())
        return real_members(*a, **k)

    def _start(*, target, args, kwargs):
        def _job(*a, **k):
            seen.setdefault("job", []).append(tp.ACTOR.get())
            return target(*a, **k)
        return real_start(target=_job, args=args, kwargs=kwargs)

    monkeypatch.setattr(server, "write_session_init_members", _members)
    monkeypatch.setattr(server, "_start_trade_job_thread", _start)
    before = _real_rows(_dump(w["engine"]))
    tok = _onboard(w)
    for t in list(w["threads"]):
        t.join(timeout=60)
    _first_deck(w, tok)
    for t in list(w["threads"]):
        t.join(timeout=60)
    assert seen.get("daemon") and set(seen["daemon"]) == {None}
    assert seen.get("job") and set(seen["job"]) == {None}
    after = _dump(w["engine"])
    assert _leaks(after) == []
    assert _real_rows(after) == before
    assert w["sends"] == []
    with w["engine"].connect() as conn:
        assert conn.execute(select(db.notifications_table)).fetchall() == []
        assert conn.execute(select(db.trade_matches_table)).fetchall() == []


def test_a_dead_test_token_never_mints_a_real_session(world):
    """Review M3: a test token that no longer resolves (exit or reset on
    another device, the gate closed) must get 401, never a fresh REAL session
    a phone still showing TEST PROFILE would store."""
    w = world
    tok = _post(w, REAL_TOK, "/api/test-profile/enter", {}).get_json()["session_token"]
    assert _post(w, tok, "/api/test-profile/exit", {}).status_code == 200

    def real_sessions():
        with server._sessions_lock:
            return sorted(t for t, s in server._sessions.items() if s.get("user_id") == REAL)
    before = real_sessions()
    r = _post(w, tok, "/api/extension/auth", {"username": OPS_USERNAME})
    assert r.status_code == 401 and r.get_json()["error"] == "test_profile_ended"
    assert real_sessions() == before
    # A real sign-in (no test token) is unchanged.
    r = w["client"].post("/api/extension/auth", headers={"Content-Type": "application/json"},
                         data=json.dumps({"username": OPS_USERNAME}))
    assert r.status_code == 200 and r.get_json()["user_id"] == REAL


def test_the_username_step_refuses_another_persons_sleeper_account(world):
    w = world
    tok = _post(w, REAL_TOK, "/api/test-profile/enter", {}).get_json()["session_token"]
    before = _dump(w["engine"])
    r = _post(w, tok, "/api/extension/auth", {"username": FRIEND_USERNAME})
    assert r.status_code == 403 and r.get_json()["error"] == "not_your_sleeper_account"
    assert _dump(w["engine"]) == before
    assert server._get_session(tok)["user_id"] == PID          # identity never replaced


def test_a_missed_rekey_is_still_masked_at_the_member_writer(world):
    """Defence in depth: hand the writers raw real ids for a namespaced
    league — they are re-keyed at the write."""
    raw = [{"user_id": m, "username": "x", "player_ids": []} for m in MATES[:3]]
    db.upsert_league_members(STORE, raw)
    db.replace_espn_league_members(f"qa_tp:{REAL}:7777", raw)
    _onboard(world)                     # the profile's users row: the daemon writer locks it
    db.write_session_init_members(STORE, raw, user_id=PID, existed=set(), replace=True)
    rows = _dump(world["engine"])["league_members"]
    assert _leaks({"league_members": rows}) == []


def test_session_input_rekeys_everything_it_hands_on(world):
    """The first re-key layer: what resolve_session_input returns and the raw
    rosters it hands the session-init daemon carry no league-mate id."""
    from backend import session_input
    raw = {}
    out = session_input.resolve_session_input(
        {"user_id": PID, "verified": True}, {"user_id": PID, "league_id": STORE}, server._sleeper_get,
        raw=raw, sleeper_identity=REAL)
    text = repr(out) + repr(raw.get("rosters"))
    assert raw.get("rosters") and out["opponent_rosters"]
    assert [m for m in MATES if m in text] == []
    assert out["league_user_id"] == PID


def test_outbound_chokepoints_drop_every_cross_user_delivery(world):
    w = world
    tp.BLOCKED.clear()
    token = tp.ACTOR.set(PID)
    try:
        assert db.create_notification(MATES[0], "trade_match", "t", "b")["blocked"] is True
        assert db.create_or_coalesce_league_join_notification(
            MATES[0], STORE, "L", "x", "b") is None
        db.queue_notification(MATES[0], "match_expiring", title="t", body="b",
                              deliver_after="2026-11-12T08:00:00+00:00")
        with pytest.raises(tp.OutboundBlocked):
            db.create_trade_match(STORE, PID, "qa_tpo_x", ["a"], ["b"])
        assert db.claim_referral(1, PID, "league_match") is False
        server._send_typed_push(MATES[0], "first_match", title="t", body="b", data={})
        own = db.create_notification(PID, "deck_replenished", "t", "b")   # own inbox: allowed
        assert own.get("id") is not None
    finally:
        tp.ACTOR.reset(token)
    # A background writer (no request actor) touching a namespaced league or a
    # test id is dropped too.
    assert db.create_notification(MATES[1], "x", "t", "b", {"league_id": STORE})["blocked"]
    with pytest.raises(tp.OutboundBlocked):
        db.create_trade_match(STORE, MATES[0], MATES[1], ["a"], ["b"])
    assert w["sends"] == []
    kinds = {b["kind"] for b in tp.BLOCKED}
    assert {"trade_match", "league_member_joined", "match_expiring", "referral_credit",
            "push:first_match"} <= kinds
    with w["engine"].connect() as conn:
        ids = [r.user_id for r in conn.execute(select(db.notifications_table))]
        assert ids == [PID]
        assert conn.execute(select(db.notification_queue_table)).fetchall() == []
    # Real users are untouched by the predicate.
    assert tp.outbound_blocked(MATES[0], league_id=LEAGUE, payload="{}") is False


def test_platform_write_cores_refuse_a_test_profile_session(world):
    sess = {"user_id": PID, "verified": True}
    import inspect
    for core in (server._sleeper_propose_core, server._mfl_propose_core,
                 server._espn_propose_core):
        kw = {n: None for n, p in inspect.signature(core).parameters.items()
              if p.kind is p.KEYWORD_ONLY and p.default is p.empty}
        kw.update(league_id=STORE, their_user_id="qa_tpo_x", give_ids=["a"], receive_ids=["b"])
        body, status = core(sess, **kw)
        assert (status, body["error"]) == (403, "test_profile_blocked"), core.__name__
    body, status = server._fa_move_core(sess, {})
    assert (status, body["error"]) == (403, "test_profile_blocked")


def test_mfl_free_agent_move_refuses_a_test_profile_before_any_mfl_call(world, monkeypatch):
    """The MFL move (in-app-claims design.md §4) is a platform write: live,
    with the profile holding an MFL credential and a binding in its namespaced
    league, a fully formed move is refused at `_fa_move_core`'s chokepoint,
    for the namespaced id and the native one alike, and nothing reaches MFL
    or the move/consent tables. The capability never offers `submit` either."""
    import backend.mfl_service as mfl_service
    import backend.mfl_write as mfl_write
    from backend import fa_move_copy as fcopy
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())
    flags = {"dev.test_profile", "mfl.send_add_drop"}
    monkeypatch.setattr(server, "is_enabled", lambda k: k in flags)
    monkeypatch.setattr(mfl_write, "FA_MOVE_SHAPES_VERIFIED", True)
    monkeypatch.setitem(fcopy.CURRENT_CONSENT_VERSION, "mfl", fcopy.MFL_ROSTER_MOVES_V1)
    mfl_calls = []
    for mod, name in ((mfl_write, "fa_move"), (mfl_service, "fetch_rosters"),
                      (mfl_service, "resolve_host"), (mfl_service, "fetch_league_bundle")):
        monkeypatch.setattr(mod, name, lambda *a, _n=name, **k: mfl_calls.append(_n))
    native, fid = "61204", "0003"
    store = tp.storage_league_id(PID, native)
    with world["engine"].begin() as conn:
        conn.execute(insert(db.leagues_table).values(
            sleeper_league_id=store, user_id=PID, name="MFL", platform="mfl",
            platform_season=2026, platform_host="www44.myfantasyleague.com",
            platform_auth="cookie", platform_my_team=fid))
        db._upsert_platform_binding(conn, PID, store, "mfl", fid)
    db.upsert_mfl_credential(PID, "tp-coach", server._sleeper_write.encrypt_token("MFL_USER_ID=tp"),
                             2026)
    sess = {"user_id": PID, "verified": True}
    for lid in (store, native):
        body, status = server._fa_move_core(sess, {
            "league_id": lid, "add_player_id": "1001", "drop_player_id": "1002",
            "move_kind": "add", "attempt_id": "tp-attempt-0001",
            "consent": {"copy_version": fcopy.MFL_ROSTER_MOVES_V1, "locale": "en-US"}})
        assert (status, body["error"]) == (403, "test_profile_blocked"), lid
        assert server._fa_move_capability(sess, lid, None)[0]["mode"] != "submit"
    assert mfl_calls == []
    with world["engine"].connect() as conn:
        assert conn.execute(select(db.platform_write_moves_table)).fetchall() == []
        assert conn.execute(select(db.platform_write_consents_table)).fetchall() == []


def test_background_readers_skip_the_sleeper_linked_profile(world):
    w = world
    tok = _onboard(w)
    del tok
    with w["engine"].begin() as conn:
        conn.execute(db.users_table.update().where(db.users_table.c.sleeper_user_id == PID)
                     .values(signup_at="2026-11-01T00:00:00+00:00", verified_via="apple"))
    assert PID not in {u["sleeper_user_id"] for u in db.load_all_signed_up_users()}
    from backend import outlook_calibration
    targets, _ = outlook_calibration.connected_targets()
    assert all(not t["user_id"].startswith("qa_") for t in targets)
    for fn, args in ((__import__("backend.trade_block_service", fromlist=["x"]).fetch_league_players, (STORE,)),
                     (__import__("backend.sleeper_trades_service", fromlist=["x"]).fetch_week_transactions, (STORE, 1)),
                     (__import__("backend.suggestion_telemetry", fromlist=["x"]).fetch_league_roster_map, (STORE,))):
        with pytest.raises(ValueError):
            fn(*args)


def test_reset_after_sleeper_onboarding_leaves_only_real_rows(world):
    w = world
    before = _real_rows(_dump(w["engine"]))
    _onboard(w)
    tp.reset_profile(PID)
    after = _dump(w["engine"])
    assert not any(_is_test_row(r) for rows in after.values() for r in rows)
    assert _real_rows(after) == before


def test_global_learning_signals_skip_the_test_profile(world):
    w = world
    now = "2026-11-11T00:00:00+00:00"
    with w["engine"].begin() as conn:
        for uid in (PID, MATES[0]):
            conn.execute(insert(db.trade_decisions_table).values(
                user_id=uid, league_id=STORE if uid == PID else LEAGUE, decision="like",
                give_player_ids="[]", receive_player_ids="[]", created_at=now))
    likes, total = db.load_global_like_rate(days=30)
    assert (likes, total) == (1, 1)
