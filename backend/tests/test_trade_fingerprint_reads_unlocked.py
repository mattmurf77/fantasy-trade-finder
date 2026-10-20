"""S0: the roster/values fingerprint reads never run under `_trade_jobs_lock`.

Lead review of S0 (2026-10-20), ruling 3. Every caller of the freshness and
join checks reads `_trade_current_fingerprints` before taking the global job
lock and passes the result in; under the lock the checks only compare. Modeled
on test_trade_disposition_replay's lock audit: the stored-row reads in
`roster_snapshot` are wrapped to record `_trade_jobs_lock.locked()`, then each
call path that reaches a reuse decision is driven:
/generate (cache hit, running join, miss), `_kickoff_trade_job` dedupe, the
replenishment cron, the /status I-1 read, and the session-init warm-up.
"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, text, update

import backend.database as db_module
import backend.server as server
from backend import roster_snapshot
from backend.database import league_members_table, metadata
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

UID = "user_lock"
OPP = "user_lock_opp"
LEAGUE = "league_lock"
TOKEN = "sess-lock-tok"
KEY = (UID, LEAGUE, "1qb_ppr")


@pytest.fixture()
def reads(monkeypatch):
    """Every stored-row fingerprint read, with whether the job lock was held."""
    seen = []
    for name in ("_read_members", "_read_picks"):
        real = getattr(roster_snapshot, name)

        def audited(conn, league_id, _real=real, _name=name):
            seen.append((_name, server._trade_jobs_lock.locked()))
            return _real(conn, league_id)

        monkeypatch.setattr(roster_snapshot, name, audited)
    return seen


def _assert_unlocked(seen):
    assert seen, "the path never read the fingerprints"
    assert [name for name, locked in seen if locked] == [], "fingerprint read under _trade_jobs_lock"


@pytest.fixture()
def live(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)

    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(league_id=LEAGUE, name="Lock League", platform="sleeper", members=[
        LeagueMember(user_id=UID, username="me", roster=["g1", "g2"], elo_ratings={}),
        LeagueMember(user_id=OPP, username="opp", roster=["r1", "r2"], elo_ratings={}),
    ])
    trade_svc.add_league(league)
    sess = {"verified": True, "user_id": UID, "league": league, "user_roster": ["g1", "g2"],
            "players": pool, "services": {"1qb_ppr": service},
            "trade_svcs": {"1qb_ppr": trade_svc}, "service": service, "trade_svc": trade_svc,
            "active_format": "1qb_ppr", "last_active": 0.0, "trade_fairness_threshold": 0.75}
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO trade_decisions (user_id, league_id, give_player_ids, "
            "receive_player_ids, decision, created_at) "
            "VALUES (:uid, :lid, :give, :recv, 'like', :created)"),
            {"uid": OPP, "lid": LEAGUE, "give": json.dumps(["r1"]), "recv": json.dumps(["g1"]),
             "created": datetime.now(timezone.utc).isoformat()})
        for uid, roster in ((UID, ["g1", "g2"]), (OPP, ["r1", "r2"])):
            conn.execute(insert(league_members_table).values(
                league_id=LEAGUE, user_id=uid, roster_data=json.dumps(roster)))

    client = server.app.test_client()
    with patch.object(server, "load_member_rankings", MagicMock(return_value={})), \
         patch.object(server, "load_league_preference", MagicMock(return_value=None)), \
         patch.object(server, "_likes_you_enabled", lambda: True), \
         patch.object(server, "_thompson_deck_enabled", lambda: False), \
         patch.object(server, "_deck_diversity_enabled", lambda: False), \
         patch.object(server, "_start_trade_job_thread", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield client, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._trade_jobs_lock:
                for jid in [j for j, job in server._trade_jobs.items() if job.get("key") == KEY]:
                    server._trade_jobs.pop(jid, None)
                server._trade_jobs_by_key.pop(KEY, None)


def _complete_job():
    job_id = server._kickoff_trade_job(sess_token=TOKEN, user_id=UID, league_id=LEAGUE,
                                       scoring_format="1qb_ppr", opponents_total=1,
                                       synchronous=True)
    with server._trade_jobs_lock:
        job = server._trade_jobs[job_id]
    assert job["status"] == "complete" and job["roster_fp"]
    return job


def _generate(client):
    resp = client.post("/api/trades/generate", json={"league_id": LEAGUE},
                       headers={"X-Session-Token": TOKEN})
    assert resp.status_code == 200
    return resp.get_json()["job_id"]


def test_generate_cache_hit(live, reads):
    client, _ = live
    job = _complete_job()
    reads.clear()
    assert _generate(client) == job["job_id"]
    _assert_unlocked(reads)


def test_generate_running_join(live, reads):
    client, _ = live
    running = dict(_complete_job(), job_id="job-lock-running", status="running", finished_at=None)
    with server._trade_jobs_lock:
        server._trade_jobs[running["job_id"]] = running
        server._trade_jobs_by_key[KEY] = running["job_id"]
    reads.clear()
    assert _generate(client) == running["job_id"]
    _assert_unlocked(reads)


def test_generate_miss_and_kickoff(live, reads):
    client, engine = live
    job = _complete_job()
    with engine.begin() as conn:
        conn.execute(update(league_members_table)
                     .where(league_members_table.c.user_id == OPP)
                     .values(roster_data=json.dumps(["r1"])))
    reads.clear()
    assert _generate(client) != job["job_id"]
    _assert_unlocked(reads)


@pytest.mark.parametrize("preserve_running", [False, True])
def test_kickoff_dedupe(live, reads, preserve_running):
    job = _complete_job()
    reads.clear()
    assert server._kickoff_trade_job(sess_token=TOKEN, user_id=UID, league_id=LEAGUE,
                                     scoring_format="1qb_ppr", opponents_total=1,
                                     preserve_running=preserve_running) == job["job_id"]
    _assert_unlocked(reads)


def test_replenish(live, reads):
    _complete_job()
    reads.clear()
    assert server._replenish_deck_for(UID, LEAGUE) is not None
    _assert_unlocked(reads)


def test_status_i1_read(live, reads):
    client, _ = live
    job = _complete_job()
    reads.clear()
    resp = client.get(f"/api/trades/status?job_id={job['job_id']}",
                      headers={"X-Session-Token": TOKEN})
    assert resp.status_code == 200 and resp.get_json()["cards"]
    _assert_unlocked(reads)


# ── session-init warm-up (pregen) ─────────────────────────────────────────────
# Harness: test_session_init_sleeper_calls's, on its linked-platform league,
# which makes no Sleeper calls.

PLATFORM_LEAGUE = "mfl:synthetic:lock"
PLATFORM_USER = "460238423161040777"
PLATFORM_OPP = "733459678624915777"
INIT_TOKEN = "lock-init-token"


@pytest.fixture()
def init_harness(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)

    def _no_sleeper(url, timeout=15):
        raise AssertionError(f"unexpected Sleeper GET {url}")

    monkeypatch.setattr(server, "_sleeper_get", _no_sleeper)
    monkeypatch.setattr(server, "_refresh_league_draft_status", lambda league_id, force=False: None)
    pool = [Player(f"p{i}", f"P{i}", "RB", "AAA", 25, 1) for i in (1, 2)]
    seed = {p.id: 1500.0 for p in pool}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format",
                        {"1qb_ppr": {"players": pool, "seed": seed},
                         "sf_tep": {"players": pool, "seed": seed}})
    monkeypatch.setattr(server, "g_universal_players", pool)
    kickoff = MagicMock()
    monkeypatch.setattr(server, "_kickoff_trade_job", kickoff)

    real_thread = server.threading.Thread

    class _InlineBgThread(real_thread):
        def start(self):
            if self.name == "session-init-bg-writes":
                self.run()
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _InlineBgThread)

    with engine.begin() as conn:
        conn.execute(db_module.leagues_table.insert().values(
            sleeper_league_id=PLATFORM_LEAGUE, user_id=PLATFORM_USER,
            name="Imported", platform="mfl"))
    db_module.upsert_league_members(PLATFORM_LEAGUE, [
        {"user_id": PLATFORM_USER, "username": "Me", "player_ids": ["p1"]},
        {"user_id": PLATFORM_OPP, "username": "Opp", "player_ids": ["p2"]},
    ])
    with server._sessions_lock:
        server._sessions[INIT_TOKEN] = {"user_id": PLATFORM_USER, "verified": True}
    key = (PLATFORM_USER, PLATFORM_LEAGUE, "1qb_ppr")
    try:
        yield server.app.test_client(), kickoff, key
    finally:
        with server._sessions_lock:
            server._sessions.pop(INIT_TOKEN, None)
        with server._trade_jobs_lock:
            server._trade_jobs.pop("job-lock-pregen", None)
            server._trade_jobs_by_key.pop(key, None)
        engine.dispose()


def test_session_init_warm_up(init_harness, reads):
    client, kickoff, key = init_harness
    capture = server._capture_trade_presentation()
    significance = server._capture_trade_significance()
    # A running warm-up job that passes every cheap check, so the decision
    # reaches the fingerprint comparison (built on rosters that have moved).
    running = {"job_id": "job-lock-pregen", "key": key, "status": "running",
               "started_at": 0.0, "finished_at": None, "cards": [], "error": None,
               "input_epochs": (), "presentation_capture": capture,
               "owner_model": server._bakeoff.owner_arm(),
               "owner_model_version": server._bakeoff.owner_version(),
               "roster_fp": "rfp1:" + "0" * 32, "values_snapshot_id": "vsn1:" + "0" * 32}
    if significance[0]:
        running["significance_capture"] = significance
    assert server._trade_running_policy_matches(
        running, capture, (running["roster_fp"], running["values_snapshot_id"]))   # control
    with server._trade_jobs_lock:
        server._trade_jobs[running["job_id"]] = running
        server._trade_jobs_by_key[key] = running["job_id"]
    reads.clear()

    resp = client.post("/api/session/init", content_type="application/json",
                       headers={"X-Session-Token": INIT_TOKEN},
                       data=json.dumps({"user_id": PLATFORM_USER, "league_id": PLATFORM_LEAGUE}))

    assert resp.status_code == 200, resp.get_json()
    _assert_unlocked(reads)
    kickoff.assert_called_once()      # stale fingerprints: the warm-up replaces it
