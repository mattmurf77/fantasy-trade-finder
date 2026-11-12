"""Onboarding test profile — backend/test_profile.py + /api/test-profile/*.

Plan: docs/plans/onboarding-test-profile/ (design.md §7 Design B, scope.md).
Every safety invariant from the brief has a named test here, sabotage-checked.

Covers:
  gate      flag off ⇒ inert (404, no DB change); account not in
            TEST_PROFILE_ACCOUNTS ⇒ 404, no DB change; no request parameter
            selects another account's profile; enter needs a verified real
            session; removing the env entry kills live test sessions and their
            durable restore
  identity  no sign-in path can mint or claim a `qa_tp_` id (extension auth,
            Test Stages spawner id space, synthetic ids refused by profile_id)
  new user  a fresh profile reads as new on the server-side gates (users row
            first_init_pending, no swipes/tiers/overrides, /api/tiers/status,
            /api/account)
  leagues   (linking itself is the open decision, design.md §10) a league in
            the profile's qa_tp: namespace initializes with zero Sleeper
            calls and reaches nobody real; a test session can never name a
            real league or another profile's namespace, and a real session
            can never enter one
  guards    platform writes / credential capture / imports / identity / delete
            refused (and only for test sessions); the push token never moves
            off the real account; referral never credited; usernames never
            collide; crons, cohorts, calibration, leaderboard and the eval
            spine skip qa_ ids; the hand-written analytics filters exclude them
  reset     scope derived from every table; deletes only test rows (seeded in
            every table that takes a user or league id, next to real rows that
            stay byte-identical); refuses any non-test id
  roundtrip enter → a namespaced league + activity → reset → exit leaves the database
            byte-identical to before

Harness: in-memory SQLite (db.engine patched), server.is_enabled patched to a
flag set, server._sleeper_get stubbed (any league read fails the test),
sessions injected and popped per test (backend/tests/CLAUDE.md patterns 1-3).
"""
import json
import re
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, select, text

import backend.database as db
import backend.server as server
import backend.test_profile as tp

pytestmark = pytest.mark.usefixtures("no_real_network")

REAL = "111222333"            # the operator's real working key (synthetic)
MATE = "555666777"            # a real league-mate who uses the app
OTHER = "999888777"           # another real user, not allow-listed
PID = "qa_tp_" + REAL
SLEEPER_LG, ESPN_LG, MFL_LG = "900100", "7777", "6284"
REAL_TOKEN, MATE_TOKEN, OTHER_TOKEN = "tp-real-tok", "tp-mate-tok", "tp-other-tok"
FLAGS_ON = {"dev.test_profile", "auth.persistent_sessions", "espn.link", "mfl.link"}


def _ts():
    return datetime.now(timezone.utc).isoformat()


def _dump(engine):
    """Every row of every table — the byte-identical comparison."""
    out = {}
    with engine.connect() as conn:
        for t in db.metadata.sorted_tables:
            out[t.name] = sorted((tuple(r) for r in conn.execute(select(t))), key=repr)
    return out


def _seed_real_world(engine):
    db.upsert_user(REAL, username="opsreal", display_name="Op Real")
    db.upsert_user(MATE, username="mate", display_name="Mate")
    db.upsert_user(OTHER, username="other", display_name="Other")
    now = _ts()
    with engine.begin() as conn:
        conn.execute(db.users_table.update().values(signup_at=now, first_init_pending=0))
        for lid, platform, opp in ((SLEEPER_LG, None, MATE),
                                   (ESPN_LG, "espn", "espn:7777:2"),
                                   (MFL_LG, "mfl", "mfl:6284:0002")):
            conn.execute(insert(db.leagues_table).values(
                sleeper_league_id=lid, user_id=REAL, name=f"League {lid}",
                platform=platform, default_scoring="sf_tep", total_rosters=2,
                season="2026", opponent_data=json.dumps([{"user_id": opp}])))
            for uid, pl in ((REAL, ["p1"]), (opp, ["p2"])):
                conn.execute(insert(db.league_members_table).values(
                    league_id=lid, user_id=uid, username=f"u{uid}",
                    display_name=f"U {uid}", roster_data=json.dumps(pl), updated_at=now))
        conn.execute(insert(db.swipe_decisions_table).values(
            user_id=REAL, winner_player_id="p1", loser_player_id="p2",
            decision_type="rank", k_factor=32.0))
        conn.execute(insert(db.espn_credentials_table).values(**_row(
            db.espn_credentials_table, "real", user_id=REAL)))
        conn.execute(insert(db.mfl_credentials_table).values(**_row(
            db.mfl_credentials_table, "real", user_id=REAL)))
        conn.execute(insert(db.sleeper_credentials_table).values(**_row(
            db.sleeper_credentials_table, "real", user_id=REAL, sleeper_user_id=REAL)))
    db.save_device_token(REAL, "ExponentPushToken[op-phone]", "ios")
    db.save_device_token(MATE, "ExponentPushToken[mate-phone]", "ios")


def _dummy(col, tag):
    try:
        py = col.type.python_type
    except NotImplementedError:
        py = str
    if py is bool:
        return False
    if py is int:
        return 7
    if py is float:
        return 1.0
    return f"{col.name}-{tag}"


def _row(table, tag, **overrides):
    """A row filling every column (autoincrement ids aside) with dummies."""
    row = {}
    for col in table.columns:
        if col.primary_key and col.autoincrement is True and str(col.type) == "INTEGER":
            continue
        row[col.name] = _dummy(col, tag)
    row.update(overrides)
    return row


@pytest.fixture()
def world(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setenv(tp.ENV_VAR, f" {REAL} ,123")
    flags = set(FLAGS_ON)
    monkeypatch.setattr(server, "is_enabled", lambda k: k in flags)

    sleeper_calls = []

    def _fake_sleeper_get(url, timeout=15):
        sleeper_calls.append(url)
        if url.endswith("/v1/user/opsreal"):
            return {"user_id": REAL, "username": "opsreal"}
        if url.endswith("/v1/user/mate"):
            return {"user_id": MATE, "username": "mate"}
        raise AssertionError(f"unexpected Sleeper GET {url}")

    monkeypatch.setattr(server, "_sleeper_get", _fake_sleeper_get)
    from backend.ranking_service import Player
    pool = [Player(f"p{i}", f"P{i}", "RB", "AAA", 25, 1) for i in (1, 2)]
    seed = {p.id: 1500.0 for p in pool}
    fake_pools = {"1qb_ppr": {"players": pool, "seed": seed},
                  "sf_tep": {"players": pool, "seed": seed}}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", fake_pools)
    monkeypatch.setattr(server, "g_universal_players", pool)
    _seed_real_world(engine)
    with server._sessions_lock:
        # last_active / _persisted_at = now: the per-request activity touch
        # and durable heartbeat stay throttled, so a DB diff is the feature's.
        for tok, uid in ((REAL_TOKEN, REAL), (MATE_TOKEN, MATE), (OTHER_TOKEN, OTHER)):
            server._sessions[tok] = {"user_id": uid, "verified": True,
                                     "last_active": time.time(), "_persisted_at": time.time()}
    server.app.config["TESTING"] = True
    try:
        yield {"client": server.app.test_client(), "engine": engine, "flags": flags,
               "sleeper_calls": sleeper_calls}
    finally:
        with server._sessions_lock:
            for t in [t for t, s in server._sessions.items()
                      if str(s.get("user_id") or "").startswith("qa_tp_")
                      or t in (REAL_TOKEN, MATE_TOKEN, OTHER_TOKEN)]:
                server._sessions.pop(t, None)
        engine.dispose()


def _call(client, method, path, token, body=None, **kw):
    headers = {"X-Session-Token": token} if token else {}
    if body is not None:
        return client.open(path, method=method, headers=headers,
                           content_type="application/json", data=json.dumps(body), **kw)
    return client.open(path, method=method, headers=headers, **kw)


def _enter(w):
    r = _call(w["client"], "POST", "/api/test-profile/enter", REAL_TOKEN, {})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["session_token"]


# ── gate ───────────────────────────────────────────────────────────────────

ROUTES = (("GET", "/api/test-profile"), ("POST", "/api/test-profile/enter"),
          ("POST", "/api/test-profile/exit"), ("POST", "/api/test-profile/reset"))


def test_flag_off_is_inert(world):
    world["flags"].discard("dev.test_profile")
    before = _dump(world["engine"])
    for method, path in ROUTES:
        r = _call(world["client"], method, path, REAL_TOKEN, {"username": "opsreal"})
        assert r.status_code == 404, (path, r.status_code)
    assert _dump(world["engine"]) == before


def test_account_not_listed_is_404_and_changes_nothing(world, monkeypatch):
    before = _dump(world["engine"])
    for method, path in ROUTES:
        r = _call(world["client"], method, path, OTHER_TOKEN,
                  {"user_id": REAL, "username": "opsreal", "platform": "espn"})
        assert r.status_code == 404, (path, r.status_code)
    for method, path in ROUTES:   # no session at all
        assert _call(world["client"], method, path, None, {}).status_code == 404
    monkeypatch.setenv(tp.ENV_VAR, "")   # unset env ⇒ inert even for REAL
    for method, path in ROUTES:
        assert _call(world["client"], method, path, REAL_TOKEN, {}).status_code == 404
    assert _dump(world["engine"]) == before


def test_no_parameter_selects_another_accounts_profile(world):
    c = world["client"]
    # The caller's own real key is the only input; body and query are ignored.
    r = _call(c, "POST", f"/api/test-profile/enter?user_id={OTHER}&real_id={OTHER}",
              REAL_TOKEN, {"user_id": OTHER, "real_id": OTHER, "profile_id": "qa_tp_" + OTHER})
    assert r.get_json()["user_id"] == PID
    # A non-listed caller naming the listed account gets nothing.
    r = _call(c, "POST", f"/api/test-profile/enter?user_id={REAL}", OTHER_TOKEN,
              {"user_id": REAL, "real_id": REAL})
    assert r.status_code == 404
    with server._sessions_lock:
        assert not any(s.get("user_id") == "qa_tp_" + OTHER for s in server._sessions.values())


def test_enter_requires_a_verified_real_session(world):
    with server._sessions_lock:
        server._sessions[REAL_TOKEN]["verified"] = False
    r = _call(world["client"], "POST", "/api/test-profile/enter", REAL_TOKEN, {})
    assert r.status_code == 404           # review L3: no existence signal when unverified
    r = _call(world["client"], "GET", "/api/test-profile", REAL_TOKEN)
    assert r.status_code == 404           # nor from the status route
    tok = None
    with server._sessions_lock:
        server._sessions[REAL_TOKEN]["verified"] = True
    tok = _enter(world)
    # A test session cannot enter a test profile of itself.
    assert _call(world["client"], "POST", "/api/test-profile/enter", tok, {}).status_code == 404


def test_removing_the_account_from_env_kills_test_sessions(world, monkeypatch):
    tok = _enter(world)
    assert _call(world["client"], "GET", "/api/test-profile", tok).get_json()["active"] is True
    monkeypatch.setenv(tp.ENV_VAR, OTHER)
    assert server._get_session(tok) is None
    assert _call(world["client"], "GET", "/api/test-profile", tok).status_code == 404
    with server._sessions_lock:   # durable restore refuses too
        server._sessions.pop(tok, None)
    assert server._restore_persisted_session(tok) is None


# ── identity ───────────────────────────────────────────────────────────────

def test_no_sign_in_path_can_mint_a_test_profile_id(world):
    with pytest.raises(ValueError):
        server._extension_build_session(PID, PID, "x", None)
    # /api/extension/auth takes its id from Sleeper: even a Sleeper answer of
    # a qa_tp_ id is refused, and no session is created for it.
    with patch.object(server, "_sleeper_get",
                      lambda url, timeout=15: {"user_id": PID} if "/v1/user/" in url
                      and "/leagues/" not in url else []):
        r = world["client"].post("/api/extension/auth", json={"username": "evil"})
    assert r.status_code != 200
    with server._sessions_lock:
        assert not any(s.get("user_id") == PID for s in server._sessions.values())
    # profile_id only accepts real working keys.
    for bad in ("qa_1a2b3c4d", PID, "demo_user_ab", "acct_", "espn:1:2", "", "x y"):
        with pytest.raises(ValueError):
            tp.profile_id(bad)
    assert tp.profile_id("acct_9f8e") == "qa_tp_acct_9f8e"
    # Test Stages mints qa_ + 8 HEX chars — 't' is not hex, so never qa_tp_.
    src = open(server.__file__).read()
    assert 'user_id = "qa_" + uuid.uuid4().hex[:8]' in src
    assert "t" not in "0123456789abcdef"


# ── a fresh profile reads as a new user ────────────────────────────────────

def test_fresh_profile_reads_as_new_user(world):
    tok = _enter(world)
    with world["engine"].connect() as conn:
        u = conn.execute(select(db.users_table).where(
            db.users_table.c.sleeper_user_id == PID)).mappings().one()
    assert u["first_init_pending"] == 1 and u["signup_at"] is None
    assert u["ranking_method"] is None and not u["tiers_saved"] and not u["tier_overrides"]
    assert u["verified_via"] is None and u["username"] == PID
    assert db.load_swipe_decisions(user_id=PID) == []
    r = _call(world["client"], "GET", "/api/tiers/status", tok)
    assert r.status_code == 200 and r.get_json()["saved"] == []
    st = _call(world["client"], "GET", "/api/test-profile", tok).get_json()
    assert st == {"available": True, "active": True, "user_id": PID,
                  "display_name": "Test profile"}


# ── leagues: the private namespace ─────────────────────────────────────────
# How leagues reach `qa_tp:X:` is the open decision (design.md §10, operator
# ruling 2026-11-11: real linking flows). These tests seed a namespaced league
# directly (as an imported-platform league) and pin the rules
# that hold regardless: a test profile enters only its own namespace, nobody
# else enters it, and nothing in it reaches a real user.

TLID = f"qa_tp:{REAL}:{SLEEPER_LG}"


def _seed_test_league(extra_members=()):
    now = _ts()
    with db.engine.begin() as conn:
        conn.execute(insert(db.leagues_table).values(
            sleeper_league_id=TLID, user_id=PID, name="League copy", platform="espn",
            default_scoring="sf_tep", total_rosters=2, season="2026",
            created_at=now, updated_at=now))
    db.upsert_league_members(TLID, [
        {"user_id": PID, "username": PID, "display_name": "Test profile", "player_ids": ["p1"]},
        {"user_id": "qa_tpo_" + MATE, "username": "umate", "player_ids": ["p2"]},
        *extra_members])


def test_test_session_cannot_name_a_real_league_and_vice_versa(world):
    from backend.session_input import SessionInputError, resolve_session_input
    tok = _enter(world)
    _seed_test_league()
    c, tlid = world["client"], TLID
    for path in (f"/api/sleeper/rosters/{SLEEPER_LG}", f"/api/league/activity?league_id={SLEEPER_LG}"):
        r = _call(c, "GET", path, tok)
        assert r.status_code == 403 and r.get_json()["error"] == "test_profile_league", path
    r = _call(c, "POST", "/api/session/init", tok, {"user_id": PID, "league_id": SLEEPER_LG})
    assert r.status_code == 403
    assert _call(c, "GET", f"/api/sleeper/rosters/{tlid}", tok).status_code == 200
    # Another test profile's namespace is not "own" either.
    assert _call(c, "GET", "/api/sleeper/rosters/qa_tp:123:900100", tok).status_code == 403
    # Even if a test-profile id were somehow a member of a REAL league (e.g.
    # written by a path that missed a guard), session input refuses it.
    db.upsert_league_members(ESPN_LG, [{"user_id": PID, "username": PID, "player_ids": ["p1"]}])
    with pytest.raises(SessionInputError):
        resolve_session_input({"user_id": PID, "verified": True},
                              {"user_id": PID, "league_id": ESPN_LG}, server._sleeper_get)
    # A real session can never enter a namespaced league (session_input refuses).
    for uid, tok_sess in ((REAL, {"user_id": REAL, "verified": True}),
                          (MATE, {"user_id": MATE, "verified": True})):
        with pytest.raises(SessionInputError):
            resolve_session_input(tok_sess, {"user_id": uid, "league_id": tlid},
                                  server._sleeper_get)


@pytest.fixture()
def init_harness(world, monkeypatch):
    """session_init with an inline daemon and fake pools (test_session_init_
    sleeper_calls.py's harness)."""
    kick = MagicMock()
    monkeypatch.setattr(server, "_kickoff_trade_job", kick)
    pushes = []
    # The LOWEST sender is patched (the Expo transport), so every guard above
    # it — including the _send_typed_push chokepoint — runs as in production.
    monkeypatch.setattr(server, "_send_expo_push", lambda msgs: pushes.append(msgs))
    for uid in (MATE, OTHER):
        db.save_device_token(uid, f"ExponentPushToken[{uid}]", "ios")
    real_thread = server.threading.Thread

    class _Inline(real_thread):
        def start(self):
            if self.name == "session-init-bg-writes":
                self.run()
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _Inline)
    world["pushes"] = pushes
    return world


def test_session_init_in_namespace_reaches_nobody_real(init_harness):
    w = init_harness
    tok = _enter(w)
    _seed_test_league()
    tlid = TLID
    real_rows = {t: rows for t, rows in _dump(w["engine"]).items()}
    r = _call(w["client"], "POST", "/api/session/init", tok,
              {"user_id": PID, "league_id": tlid, "invited_by": "mate",
               "invite_id": "inv-123"})
    assert r.status_code == 200, r.get_json()
    assert w["sleeper_calls"] == []                       # no Sleeper read at all
    sess = server._get_session(tok)
    assert server._league_user_id(sess) == PID
    assert {m.user_id for m in sess["league"].members} == {"qa_tpo_" + MATE}
    after = _dump(w["engine"])
    assert after["notifications"] == [] and after["referrals"] == [] and w["pushes"] == []
    # Real users' rows and real leagues untouched.
    for t in ("leagues", "league_members"):
        real = [x for x in after[t] if "qa_tp" not in repr(x)]
        assert real == [x for x in real_rows[t] if "qa_tp" not in repr(x)]
    real_users = [x for x in after["users"] if x[0] in (REAL, MATE, OTHER)]
    assert real_users == [x for x in real_rows["users"] if x[0] in (REAL, MATE, OTHER)]


def test_join_fanout_never_fires_for_a_test_profile(init_harness):
    """Defense in depth behind the namespace: even if a REAL app user's id
    ended up as a member of a test league, the profile's first session never
    announces it to them."""
    w = init_harness
    tok = _enter(w)
    _seed_test_league()
    with db.engine.begin() as conn:   # bypass the writer's re-key: a missed re-key
        conn.execute(insert(db.league_members_table).values(
            league_id=TLID, user_id=MATE, username="mate", display_name="Mate",
            roster_data='["p2"]', updated_at=_ts()))
    tlid = TLID
    r = _call(w["client"], "POST", "/api/session/init", tok, {"user_id": PID, "league_id": tlid})
    assert r.status_code == 200, r.get_json()
    assert w["pushes"] == []
    assert _dump(w["engine"])["notifications"] == []


# ── guards ─────────────────────────────────────────────────────────────────

BLOCKED = (
    ("POST", "/api/trades/propose"), ("POST", "/api/trades/propose-mfl"),
    ("POST", "/api/trades/respond-mfl"), ("POST", "/api/trades/propose-espn"),
    ("POST", "/api/league/free-agents/move"), ("POST", "/api/sleeper/link"),
    ("POST", "/api/fleaflicker/link"), ("POST", "/api/account/link-sleeper"),
    ("POST", "/api/auth/apple"), ("DELETE", "/api/account"), ("POST", "/api/invite/token"),
    ("POST", "/api/test-users"),
)


def test_platform_writes_and_imports_refused_for_test_profile(world):
    tok = _enter(world)
    for method, path in BLOCKED:
        r = _call(world["client"], method, path, tok, {})
        assert r.status_code == 403, (path, r.status_code)
        body = r.get_json()
        assert body["error"] == "test_profile_blocked" and "Back to my profile" in body["message"]
    if "overhaul_send_route" in server.app.view_functions:
        r = _call(world["client"], "POST", "/api/overhauls/x/send", tok, {})
        assert r.get_json().get("error") == "test_profile_blocked"
    # The same routes are untouched for a real session.
    for method, path in BLOCKED:
        r = _call(world["client"], method, path, REAL_TOKEN, {})
        assert (r.get_json() or {}).get("error") != "test_profile_blocked", path


def test_push_token_never_moves_off_the_real_account(world):
    tok = _enter(world)
    r = _call(world["client"], "POST", "/api/notifications/register-device", tok,
              {"device_token": "ExponentPushToken[op-phone]", "platform": "ios"})
    assert r.status_code == 200 and r.get_json()["skipped"] == "test_profile"
    with world["engine"].connect() as conn:
        owners = dict(conn.execute(select(db.device_tokens_table.c.device_token,
                                          db.device_tokens_table.c.user_id)).all())
    assert owners["ExponentPushToken[op-phone]"] == REAL
    assert PID not in owners.values()


def test_usernames_never_collide(world):
    _enter(world)
    assert db.get_user_by_username("opsreal")["sleeper_user_id"] == REAL
    assert db.get_user_by_username(PID)["display_name"] == "Test profile"


def test_crons_cohorts_and_training_skip_qa_ids(world):
    _enter(world)
    _seed_test_league()   # the profile is a "connected" (user, league) pair too
    eng = world["engine"]
    with eng.begin() as conn:
        conn.execute(db.users_table.update().where(
            db.users_table.c.sleeper_user_id == PID).values(
            signup_at=_ts(), verified_via="apple", current_streak=99,
            last_rank_local_date=datetime.now(timezone.utc).date().isoformat()))
        conn.execute(db.users_table.update().where(
            db.users_table.c.sleeper_user_id == REAL).values(
            current_streak=3, last_rank_local_date=datetime.now(timezone.utc).date().isoformat()))
    ids = {u["sleeper_user_id"] for u in db.load_all_signed_up_users()}
    assert REAL in ids and PID not in ids
    from backend import outlook_calibration
    targets, _ = outlook_calibration.connected_targets()
    assert all(not t["user_id"].startswith("qa_") for t in targets)
    from backend import prepared_trade_cohort as cohort
    res = cohort.discover_targets(
        users=[{"sleeper_user_id": PID, "verified_via": "apple"}], leagues=[],
        read_source=lambda *a, **k: None, season=2026, now=datetime.now(timezone.utc))
    assert any(c.get("reason") == "opponent_only_actor" for c in res.get("coverage", []))
    board = db.load_leaderboard(metric="streak", limit=50)
    assert PID not in [r["user_id"] for r in board["rows"]]
    from backend.eval.data import load_decks
    with eng.begin() as conn:
        for uid in (REAL, PID):
            conn.execute(insert(db.deck_impressions_table).values(**_row(
                db.deck_impressions_table, uid, user_id=uid, served_at=_ts())))
    assert {d.user_id for d in load_decks(engine=eng)} == {REAL}


def test_analytics_hand_filters_exclude_qa_ids(world):
    import backend.analytics_queries as aq
    eng = world["engine"]
    day = datetime.now(timezone.utc).date().isoformat()
    with eng.begin() as conn:
        for uid in (REAL, PID):
            conn.execute(insert(db.user_events_table).values(**_row(
                db.user_events_table, uid, user_id=uid, event_type="tier_save",
                occurred_at=day + "T00:00:00+00:00")))
        conn.execute(db.users_table.update().values(last_active_at="2020-01-01T00:00:00"))
    _enter(world)
    with eng.begin() as conn:
        conn.execute(db.users_table.update().values(last_active_at="2020-01-01T00:00:00"))
    with eng.connect() as conn:
        assert aq._event_count(conn, day, day, ["tier_save"]) == 1
        churn = aq.report_churn(conn, day, day, False, 100)
    churned = json.dumps(churn, default=str)
    assert REAL in churned and PID not in churned


# ── reset ──────────────────────────────────────────────────────────────────

# Review 2026-11-12: the coverage check must not reuse the code's own
# column predicate. This enumerates the SCHEMA with a deliberately broad
# identity pattern; every match is either in the reset's reach or listed here
# with the reason it is not a user/league key the test profile can own.
_IDENTITY_COL = re.compile(
    r"user|owner|actor|_by$|creator|league|partner|member|account|subject|recipient"
    r"|referr|invit|target|counterparty", re.I)
_NOT_IDENTITY = re.compile(
    r"_at$|_count$|_json$|^targets$|_fit$|_version$|decision|dismissed|_give$|_receive$"
    r"|impression_id$|_scope$|team_outlook|_kind$", re.I)
NOT_KEYED = {
    "accounts.account_id": "a test profile is minted without an account",
    "entitlements.account_id": "no account, so no entitlement",
    "identity_links.account_id": "no account (its user_id column is covered)",
    "linked_identities.account_id": "no account: Apple/Google are fenced",
    "linked_identities.provider_subject": "a provider subject, never an app id",
    "sessions.account_id": "no account (sessions.user_id is covered)",
    "sessions.account_only": "a boolean",
    "subscription_events.account_id": "no account, no purchase",
    "entitlements.granted_by": "the operator's admin key on a manual grant",
    "affiliate_clicks.partner": "an affiliate partner name, not a user",
    "bad_trade_flags.target_username": "a league-mate's name; the row's user_id is covered",
    "draft_picks.owner_username": "a display name inside a league row (league_id covered)",
    "draft_picks.original_username": "same",
    "overhaul_offers.counterparty_username": "same; overhaul sends are fenced",
    "mfl_credentials.mfl_username": "the MFL login name; the row's user_id is covered",
    "users.invited_by": "a referrer's username, dropped for a test profile",
    "referrals.invite_token": "a token; referral credit is refused for a test profile",
    "standing_offers.team_user_ids": "a JSON list inside a row whose user_id is covered",
    "rank_sets.owner_type": "an enum",
    "swipe_decisions.k_factor": "a number",
    "league_projection_targets.target_id": "a uuid; registration refuses a namespaced league",
    "prepared_trade_manifests_v2.target_id": "a uuid; the prepared cohort skips qa_ users",
    "prepared_trade_targets.target_id": "same",
    "prepared_trade_worker.target_id": "same",
    "prepared_trade_participants.subject_id": "written only by the prepared cohort, which skips qa_",
}


def test_reset_scope_covers_every_identity_column_in_the_schema():
    covered = {(name, c) for name, u, l in tp.reset_scope() for c in u + l}
    missing = []
    for t in db.metadata.sorted_tables:
        for c in t.columns:
            if not _IDENTITY_COL.search(c.name) or _NOT_IDENTITY.search(c.name):
                continue
            if (t.name, c.name) not in covered and f"{t.name}.{c.name}" not in NOT_KEYED:
                missing.append(f"{t.name}.{c.name}")
    assert missing == [], f"identity columns the reset does not cover: {missing}"
    stale = [k for k in NOT_KEYED if tuple(k.split(".")) in covered]
    assert stale == [], f"listed as not keyed but covered: {stale}"
    for must in (("trade_matches", "user_a_id"), ("trade_matches", "user_b_id"),
                 ("recorded_picks", "recorded_by"), ("trade_share_tokens", "created_by"),
                 ("draft_picks", "assigned_by"), ("users", "sleeper_user_id")):
        assert must in covered, must


def test_reset_refuses_any_non_test_id(world):
    before = _dump(world["engine"])
    for bad in (REAL, "qa_1a2b3c4d", "qa_tp_", "qa_tp_qa_x", "qa_tp_" + "demo_user_1", "", None):
        with pytest.raises(ValueError):
            tp.reset_profile(bad)
    assert _dump(world["engine"]) == before


def test_reset_deletes_only_test_rows_across_every_table(world):
    eng = world["engine"]
    prefix = f"qa_tp:{REAL}:"
    seeded = 0
    for name, ucols, lcols in tp.reset_scope():
        t = db.metadata.tables[name]
        # Look-alikes share a PREFIX with the profile's ids and must survive.
        for tag, uid, lid in (("test", PID, prefix + "1"), ("real", REAL, "1"),
                              ("other", "qa_tp_123", "qa_tp:123:1"),
                              ("lookalike", PID + "9", f"qa_tp:{REAL}9:1"),
                              ("lookalike2", REAL + "9", f"qa_tp:{REAL}"),
                              ("lookalike3", "qa_tp_" , prefix[:-1])):
            vals = _row(t, f"{name}-{tag}", **{c: uid for c in ucols}, **{c: lid for c in lcols})
            try:
                with eng.begin() as conn:
                    conn.execute(insert(t).values(**vals))
                seeded += tag == "test"
            except Exception:
                pass
    assert seeded >= 55, seeded
    before = _dump(eng)
    counts = tp.reset_profile(PID)
    after = _dump(eng)
    assert sum(counts.values()) >= seeded

    def _is_test(table, r):
        # Independent of the code's predicate: any identity-like column of the
        # schema holding exactly PID, or any league column in the namespace.
        m = dict(zip([c.name for c in table.columns], r))
        return any(v == PID for k, v in m.items()
                   if _IDENTITY_COL.search(k) and not _NOT_IDENTITY.search(k)) or any(
            str(v or "").startswith(prefix) for k, v in m.items() if k.endswith("league_id"))

    for t in db.metadata.sorted_tables:
        kept = [r for r in before[t.name] if not _is_test(t, r)]
        assert after[t.name] == kept, t.name   # every other row byte-identical


def test_roundtrip_leaves_database_byte_identical(world):
    c = world["client"]
    before = _dump(world["engine"])
    tok = _enter(world)
    _seed_test_league()   # stands in for the linking step (design.md §10)
    with world["engine"].begin() as conn:   # test-profile activity
        conn.execute(insert(db.swipe_decisions_table).values(
            user_id=PID, winner_player_id="p2", loser_player_id="p1",
            decision_type="rank", k_factor=32.0))
    assert _dump(world["engine"]) != before
    r = _call(c, "POST", "/api/test-profile/reset", tok, {})
    assert r.status_code == 200
    new_tok = r.get_json()["session_token"]
    assert server._get_session(tok) is None and new_tok != tok
    assert _call(c, "POST", "/api/test-profile/exit", new_tok, {}).status_code == 200
    assert server._get_session(new_tok) is None
    # Back on the real profile: every row that is not the test profile's is
    # byte-identical to before (the reset re-minted only the profile's own
    # users row, kept so onboarding can start again).
    after = _dump(world["engine"])
    not_test = lambda rows: [r for r in rows if PID not in repr(r) and "qa_tp:" not in repr(r)]
    assert {t: not_test(r) for t, r in after.items()} == {t: not_test(r) for t, r in before.items()}
    tp.reset_profile(PID)   # and one more reset leaves nothing at all behind
    assert _dump(world["engine"]) == before
    # The real session was never touched.
    assert server._get_session(REAL_TOKEN)["user_id"] == REAL
