"""S0 — the session-init Sleeper roster refresh is recorded in league_roster_state.

Pins (scope-eng-s0-fetch.md §B.2-§B.3):
  • success → 'fresh', refreshed_at set, last_error_code NULL
  • a failed read → the last good rows are untouched and the state says
    'stale' + last_error_code. The row never stores 'missing' (contract v0.3
    §3: "missing" is derived from absent league_members rows by the reader)
  • a throttled pick read → 'stale' / 'picks_unavailable'
  • a membership refusal (403) is not a refresh failure — nothing is written
  • G-004: a null Sleeper player slot is never stored as the string "None"
  • the accessors: refreshed_at only moves forward; roster_fp is never touched

Real `_sleeper_get` + the shipped FTF_SLEEPER_FIXTURES_DIR cassette seam; the
three urllib-direct daemon fetchers are stubbed. No network.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import backend.database as db_module
import backend.server as server
import backend.sleeper_http as sh
import backend.sleeper_trades_service as trades_service
import backend.suggestion_telemetry as sugg_tel
import backend.trade_block_service as tb_service
from backend.database import metadata

LEAGUE_ID = "1338231586314780672"
USER_ID = "460238423161040896"
OPP_ID = "733459678624915456"
TOKEN = "s0-refresh-token"

META = {"league_id": LEAGUE_ID, "name": "Bush League", "season": "2026",
        "total_rosters": 2, "roster_positions": ["QB", "RB", "WR", "TE", "FLEX", "BN"],
        "scoring_settings": {"rec": 1.0}, "settings": {"draft_rounds": 3}}
ROSTERS = [
    {"roster_id": 1, "owner_id": USER_ID, "co_owners": None,
     "players": ["p1", None, ""], "starters": ["p1"]},
    {"roster_id": 2, "owner_id": OPP_ID, "co_owners": None,
     "players": ["p2"], "starters": ["p2"]},
]
USERS = [{"user_id": USER_ID, "username": "Me"}, {"user_id": OPP_ID, "username": "Opp"}]


@pytest.fixture()
def harness(monkeypatch, tmp_path):
    from backend.ranking_service import Player

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)

    # The shipped cassette seam: …/v1/<path> → <dir>/<path>.json.
    monkeypatch.setattr(server, "_SLEEPER_FIXTURES_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_SLEEPER_RECORD", False)

    def put(rel, doc):
        path = tmp_path / f"{rel}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc))

    base = f"league/{LEAGUE_ID}"
    put(base, META)
    put(f"{base}/rosters", ROSTERS)
    put(f"{base}/users", USERS)
    put(f"{base}/traded_picks", [])
    put(f"{base}/drafts", [])

    # urllib-direct daemon fetchers sit outside the cassette seam.
    monkeypatch.setattr(tb_service, "fetch_league_players",
                        lambda league_id, *, _opener=None, timeout=15: [])
    monkeypatch.setattr(trades_service, "fetch_week_transactions",
                        lambda lid, week, *, _opener=None, timeout=15: [])
    monkeypatch.setattr(sugg_tel, "fetch_league_roster_map",
                        lambda league_id, *, _opener=None, timeout=15: {})
    monkeypatch.setattr(server, "_refresh_league_draft_status",
                        lambda league_id, force=False: None)

    pool = [Player(f"p{i}", f"P{i}", "RB", "AAA", 25, 1) for i in (1, 2)]
    seed = {p.id: 1500.0 for p in pool}
    fake_pools = {"1qb_ppr": {"players": pool, "seed": seed},
                  "sf_tep": {"players": pool, "seed": seed}}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", fake_pools)
    monkeypatch.setattr(server, "g_universal_players", pool)
    monkeypatch.setattr(server, "_kickoff_trade_job", lambda **kw: None)

    real_thread = server.threading.Thread

    class _InlineBgThread(real_thread):
        def start(self):
            if self.name == "session-init-bg-writes":
                self.run()
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _InlineBgThread)
    sh.reset()
    with server._sessions_lock:
        server._sessions[TOKEN] = {"user_id": USER_ID, "verified": True}
    server.app.config["TESTING"] = True
    try:
        yield server.app.test_client(), put
    finally:
        sh.reset()
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
        server._FA_LEAGUE_META_CACHE.pop(LEAGUE_ID, None)
        engine.dispose()


def _init(client):
    return client.post("/api/session/init", content_type="application/json",
                       headers={"X-Session-Token": TOKEN},
                       data=json.dumps({"user_id": USER_ID, "league_id": LEAGUE_ID}))


def _members():
    return {m["user_id"]: m["roster_data"] for m in db_module.load_league_members(LEAGUE_ID)}


# ---------------------------------------------------------------------------
# Session init end to end
# ---------------------------------------------------------------------------

def test_success_marks_fresh_and_never_stores_none_ids(harness):
    client, _put = harness
    assert _init(client).status_code == 200
    state = db_module.get_league_roster_state(LEAGUE_ID)
    assert state["status"] == "fresh"
    assert state["last_error_code"] is None
    assert state["refreshed_at"] and state["roster_fp"].startswith("rfp1:")   # PR-B's stamp
    assert json.loads(_members()[USER_ID]) == ["p1"]               # G-004: no "None", no ""
    # The meta read seeded the trade paths' 15-min meta cache.
    assert server._FA_LEAGUE_META_CACHE[LEAGUE_ID][1] == META


def test_the_session_and_its_pregen_carry_the_read_the_daemon_commits(harness, monkeypatch):
    """#470 QA P2-2: the session, and the pre-gen's session context, carry this
    init's Sleeper read start, the `refreshed_at` its daemon writes, so the
    roster-change handler keeps the deck built on that read. A later init
    replaces it."""
    client, _put = harness
    kicked = []
    monkeypatch.setattr(server, "_kickoff_trade_job", lambda **kw: kicked.append(kw))
    reads = []
    for _ in range(2):
        assert _init(client).status_code == 200
        read = db_module.get_league_roster_state(LEAGUE_ID)["refreshed_at"]
        with server._sessions_lock:
            assert server._sessions[TOKEN]["roster_fetch_started_at"] == read
        assert kicked[-1]["session_context"]["roster_fetch_started_at"] == read
        reads.append(read)
    assert reads[0] < reads[1]


def test_failure_with_no_prior_rows_is_stale_never_missing(harness):
    client, put = harness
    put(f"league/{LEAGUE_ID}/rosters", {"__http_error__": 503})
    resp = _init(client)
    assert resp.status_code == 503
    assert resp.get_json() == {"error": "league_data_unavailable"}   # contract unchanged
    state = db_module.get_league_roster_state(LEAGUE_ID)
    assert (state["status"], state["last_error_code"]) == ("stale", "http_5xx")
    assert state["refreshed_at"] is None                             # never refreshed
    assert _members() == {}                                          # the reader derives "missing"


def test_failure_after_success_keeps_rows_and_marks_stale(harness):
    client, put = harness
    assert _init(client).status_code == 200
    before_rows = _members()
    before = db_module.get_league_roster_state(LEAGUE_ID)

    put(f"league/{LEAGUE_ID}/rosters", ["not", "rosters"])           # shape check fails
    put(f"league/{LEAGUE_ID}/users", {"not": "a list"})
    assert _init(client).status_code == 503

    after = db_module.get_league_roster_state(LEAGUE_ID)
    assert (after["status"], after["last_error_code"]) == ("stale", "invalid_payload")
    assert after["refreshed_at"] == before["refreshed_at"]           # last good kept
    assert _members() == before_rows                                 # rows untouched


def test_failure_with_pre_s0_rows_is_stale(harness):
    client, put = harness
    db_module.upsert_league_members(LEAGUE_ID, [
        {"user_id": USER_ID, "username": "Me", "player_ids": ["p1"]}])   # pre-S0 rows
    put(f"league/{LEAGUE_ID}/rosters", {"__http_error__": 502})
    assert _init(client).status_code == 503
    assert db_module.get_league_roster_state(LEAGUE_ID)["status"] == "stale"


def test_429_marks_rate_limited_and_the_next_init_makes_no_read(harness, monkeypatch):
    client, put = harness
    put(f"league/{LEAGUE_ID}/rosters",
        {"__http_error__": 429, "__headers__": {"Retry-After": "120"}})
    assert _init(client).status_code == 503
    state = db_module.get_league_roster_state(LEAGUE_ID)
    assert (state["status"], state["last_error_code"]) == ("stale", "rate_limited")

    reads = []
    monkeypatch.setattr(server, "_sleeper_get_unguarded",
                        lambda url, timeout=15: reads.append(url))
    assert _init(client).status_code == 503                          # fails fast
    assert reads == []
    assert db_module.get_league_roster_state(LEAGUE_ID)["last_error_code"] == "rate_limited"


def test_recovery_after_failure_clears_the_error(harness):
    client, put = harness
    put(f"league/{LEAGUE_ID}/rosters", {"__http_error__": 500})
    assert _init(client).status_code == 503
    put(f"league/{LEAGUE_ID}/rosters", ROSTERS)
    assert _init(client).status_code == 200
    state = db_module.get_league_roster_state(LEAGUE_ID)
    assert (state["status"], state["last_error_code"]) == ("fresh", None)


def test_throttled_pick_read_marks_picks_unavailable(harness):
    client, put = harness
    put(f"league/{LEAGUE_ID}/traded_picks", {"__http_error__": 429})
    assert _init(client).status_code == 200                          # never blocks
    state = db_module.get_league_roster_state(LEAGUE_ID)
    # Members were written this init, so the league has rows: stale, not missing.
    assert (state["status"], state["last_error_code"]) == ("stale", "picks_unavailable")
    assert state["refreshed_at"] is None                             # never fully refreshed


def test_membership_refusal_is_not_a_refresh_failure(harness):
    client, put = harness
    put(f"league/{LEAGUE_ID}/rosters", [ROSTERS[1]])                 # caller not on a roster
    assert _init(client).status_code == 403
    assert db_module.get_league_roster_state(LEAGUE_ID) is None


# ---------------------------------------------------------------------------
# The accessors
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    yield db_module
    engine.dispose()


def test_refreshed_at_only_moves_forward(db):
    db.mark_league_roster_fresh("L", "2026-10-20T12:00:05.000000+00:00")
    db.mark_league_roster_fresh("L", "2026-10-20T12:00:01.000000+00:00")   # older, finishes last
    assert db.get_league_roster_state("L")["refreshed_at"] == "2026-10-20T12:00:05.000000+00:00"
    db.mark_league_roster_fresh("L", "2026-10-20T12:01:00.000000+00:00")
    assert db.get_league_roster_state("L")["refreshed_at"] == "2026-10-20T12:01:00.000000+00:00"


def test_failure_keeps_fp_and_refreshed_at(db):
    from sqlalchemy import update
    db.mark_league_roster_fresh("L", "2026-10-20T12:00:00.000000+00:00")
    with db.engine.begin() as conn:                                   # as PR-B will stamp
        conn.execute(update(db.league_roster_state_table)
                     .where(db.league_roster_state_table.c.league_id == "L")
                     .values(roster_fp="rfp1:abc"))
    assert db.mark_league_roster_failed("L", "timeout") == "stale"
    state = db.get_league_roster_state("L")
    assert state["roster_fp"] == "rfp1:abc"
    assert state["refreshed_at"] == "2026-10-20T12:00:00.000000+00:00"
    db.mark_league_roster_fresh("L", "2026-10-20T12:05:00.000000+00:00")
    assert db.get_league_roster_state("L")["roster_fp"] == "rfp1:abc"   # fresh never touches it


def test_failure_on_a_never_seen_league_is_stale(db):
    assert db.mark_league_roster_failed("L", "network") == "stale"
    state = db.get_league_roster_state("L")
    assert (state["status"], state["last_error_code"]) == ("stale", "network")
    assert state["refreshed_at"] is None and state["roster_fp"] is None
    assert not hasattr(db, "ROSTER_STATE_MISSING")                # never a stored value


# ---------------------------------------------------------------------------
# Replace semantics for Sleeper league_members (S0, separate commit)
# ---------------------------------------------------------------------------

GHOST_ID = "111111111111111111"


def test_session_init_replaces_sleeper_members_dropping_ghosts(harness):
    client, _put = harness
    db_module.upsert_league_members(LEAGUE_ID, [   # a manager who left (G-075)
        {"user_id": GHOST_ID, "username": "Gone", "player_ids": ["p2"]}])
    assert _init(client).status_code == 200
    assert set(_members()) == {USER_ID, OPP_ID}    # ghost removed, one row per roster


def test_replace_refuses_an_empty_snapshot(db):
    db.upsert_league_members("L", [{"user_id": "u1", "username": "A", "player_ids": ["p1"]}])
    assert db.replace_league_members_snapshot("L", []) is False
    assert db.replace_league_members_snapshot("L", [{"user_id": "", "player_ids": ["p9"]}]) is False
    assert [m["user_id"] for m in db.load_league_members("L")] == ["u1"]   # untouched (G-015)
    assert db.replace_league_members_snapshot("L", [
        {"user_id": "u2", "username": "B", "player_ids": ["p2"]}]) is True
    assert [m["user_id"] for m in db.load_league_members("L")] == ["u2"]


def test_platform_league_rows_are_not_replaced_by_session_init(harness, monkeypatch):
    """ESPN/MFL membership is replaced at import, never by session init."""
    client, _put = harness
    mfl = "62846"
    with db_module.engine.begin() as conn:
        conn.execute(db_module.leagues_table.insert().values(
            sleeper_league_id=mfl, user_id=USER_ID, name="Imported", platform="mfl"))
    db_module.upsert_league_members(mfl, [
        {"user_id": USER_ID, "username": "Me", "player_ids": ["p1"]},
        {"user_id": OPP_ID, "username": "Opp", "player_ids": ["p2"]},
        {"user_id": "mfl:62846.f0003", "username": "Third", "player_ids": []},
    ])
    called = []
    monkeypatch.setattr(server, "replace_league_members_snapshot",
                        lambda *a, **kw: called.append(a) or True)
    resp = client.post("/api/session/init", content_type="application/json",
                       headers={"X-Session-Token": TOKEN},
                       data=json.dumps({"user_id": USER_ID, "league_id": mfl}))
    assert resp.status_code == 200
    assert called == []
    assert len(db_module.load_league_members(mfl)) == 3
