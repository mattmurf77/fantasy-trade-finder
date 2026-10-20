"""A job with status "error" (any error, timeout included) is never reused for a new tap.

head-eng ruling 9 (2026-10-20): the view keeps a timed-out job's cards for the
caller still polling it, but no new request may be answered with it. Three
gates must hold, and each is pinned here against a job that would otherwise
match on every other input:
  - `_trade_job_is_fresh` requires status "complete";
  - the running-job match goes through `_job_live`, which requires "running";
  - `_kickoff_trade_job` dedupes only through those two, so it admits a new job.
The timeout is applied exactly as the cleanup sweep does (server.py
`_cleanup_loop`: status "error", error "timeout", finished_at now, cards kept).
Harness: test_force_supersedes_running_job's.
"""
import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
import backend.server as server
from backend.database import metadata
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

UID = "user_err"
OPP = "user_err_opp"
LEAGUE = "league_err"
TOKEN = "sess-err-tok"
KEY = (UID, LEAGUE, "1qb_ppr")
ERRORS = ["timeout", "inputs_changed", "worker_start_failed"]


@pytest.fixture()
def live(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)

    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(league_id=LEAGUE, name="Err League", platform="sleeper", members=[
        LeagueMember(user_id=UID, username="me", roster=["g1", "g2"], elo_ratings={}),
        LeagueMember(user_id=OPP, username="opp", roster=["r1", "r2"], elo_ratings={}),
    ])
    trade_svc.add_league(league)
    sess = {"verified": True, "user_id": UID, "league": league, "user_roster": ["g1", "g2"],
            "players": pool, "services": {"1qb_ppr": service},
            "trade_svcs": {"1qb_ppr": trade_svc}, "service": service, "trade_svc": trade_svc,
            "active_format": "1qb_ppr", "last_active": 0.0}
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO trade_decisions (user_id, league_id, give_player_ids, "
            "receive_player_ids, decision, created_at) "
            "VALUES (:uid, :lid, :give, :recv, 'like', :created)"),
            {"uid": OPP, "lid": LEAGUE, "give": json.dumps(["r1"]), "recv": json.dumps(["g1"]),
             "created": datetime.now(timezone.utc).isoformat()})

    client = server.app.test_client()
    with patch.object(server, "load_member_rankings", MagicMock(return_value={})), \
         patch.object(server, "load_league_preference", MagicMock(return_value=None)), \
         patch.object(server, "_likes_you_enabled", lambda: True), \
         patch.object(server, "_thompson_deck_enabled", lambda: False), \
         patch.object(server, "_deck_diversity_enabled", lambda: False):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield client
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._trade_jobs_lock:
                for jid in [j for j, job in server._trade_jobs.items()
                            if job.get("key") == KEY]:
                    server._trade_jobs.pop(jid, None)
                server._trade_jobs_by_key.pop(KEY, None)


def _matching_running_job():
    """A running job that matches a default tap on every input (it is a
    running copy of a real completed job, partial cards included)."""
    done_id = server._kickoff_trade_job(sess_token=TOKEN, user_id=UID, league_id=LEAGUE,
                                        scoring_format="1qb_ppr", opponents_total=1,
                                        synchronous=True)
    with server._trade_jobs_lock:
        done = server._trade_jobs[done_id]
        assert done["status"] == "complete" and done["cards"]
        job = dict(done, job_id="job-err", status="running", finished_at=None)
        server._trade_jobs[job["job_id"]] = job
        server._trade_jobs_by_key[KEY] = job["job_id"]
    return job


def _fail(job, error):
    with server._trade_jobs_lock:          # the sweep's exact mutation
        job["status"] = "error"
        job["error"] = error
        job["finished_at"] = time.monotonic()


def _generate(client):
    with patch.object(server, "_start_trade_job_thread", MagicMock()) as start:
        resp = client.post("/api/trades/generate", json={"league_id": LEAGUE},
                           headers={"X-Session-Token": TOKEN})
    assert resp.status_code == 200
    return resp.get_json()["job_id"], start.called


def test_control_the_running_job_is_joined(live):
    job = _matching_running_job()
    assert _generate(live) == (job["job_id"], False)


@pytest.mark.parametrize("error", ERRORS)
def test_errored_job_is_neither_fresh_nor_joinable(live, error):
    job = _matching_running_job()
    _fail(job, error)
    capture = server._capture_trade_presentation()
    with server._trade_jobs_lock:
        assert not server._trade_job_is_fresh(
            job, job["fairness_threshold"], job["outlook_value"],
            presentation_capture=capture, request_signature=job["request_signature"])
        assert not server._trade_running_policy_matches(job, capture)
        assert not server._trade_running_matches(
            job, job["fairness_threshold"], job["outlook_value"],
            presentation_capture=capture, request_signature=job["request_signature"])


@pytest.mark.parametrize("error", ERRORS)
def test_generate_starts_a_new_job_instead_of_reusing_an_errored_one(live, error):
    job = _matching_running_job()
    _fail(job, error)
    new_id, kicked_off = _generate(live)
    assert new_id != job["job_id"] and kicked_off
    with server._trade_jobs_lock:
        assert server._trade_jobs_by_key[KEY] == new_id


@pytest.mark.parametrize("preserve_running", [False, True])
def test_kickoff_never_dedupes_onto_an_errored_job(live, preserve_running):
    job = _matching_running_job()
    _fail(job, "timeout")
    with patch.object(server, "_start_trade_job_thread", MagicMock()) as start:
        new_id = server._kickoff_trade_job(sess_token=TOKEN, user_id=UID, league_id=LEAGUE,
                                           scoring_format="1qb_ppr", opponents_total=1,
                                           preserve_running=preserve_running)
    assert new_id != job["job_id"] and start.called
    with server._trade_jobs_lock:
        assert server._trade_jobs_by_key[KEY] == new_id
