"""S0: a deck job built on rosters or values that have since moved is never reused.

`_kickoff_trade_job` stamps `roster_fp` (rfp1) and `values_snapshot_id` (vsn1);
`_trade_job_is_fresh` and the running-job match recompute both from stored rows
and compare. A display-name change must not miss. Also pins the trades-side
`on_roster_change` handler. Harness: test_force_supersedes_running_job's
in-memory SQLite + live session.
"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, text, update

import backend.database as db_module
import backend.server as server
from backend import roster_snapshot
from backend.database import draft_picks_table, league_members_table, metadata
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

UID = "user_fp"
OPP = "user_fp_opp"
LEAGUE = "league_fp"
TOKEN = "sess-fp-tok"
KEY = (UID, LEAGUE, "1qb_ppr")


@pytest.fixture()
def live(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)

    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(league_id=LEAGUE, name="FP League", platform="sleeper", members=[
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
        for uid, roster in ((UID, ["g1", "g2"]), (OPP, ["r1", "r2"])):
            conn.execute(insert(league_members_table).values(
                league_id=LEAGUE, user_id=uid, username=uid, display_name=uid,
                roster_data=json.dumps(roster), updated_at="2026-10-20"))
        conn.execute(insert(draft_picks_table).values(
            pick_id=f"{LEAGUE}_2027_1_1", league_id=LEAGUE, season=2027, round=1,
            owner_user_id=UID, original_roster_id="1", pool_value=10.0))

    client = server.app.test_client()
    with patch.object(server, "load_member_rankings", MagicMock(return_value={})), \
         patch.object(server, "load_league_preference", MagicMock(return_value=None)), \
         patch.object(server, "_likes_you_enabled", lambda: True), \
         patch.object(server, "_thompson_deck_enabled", lambda: False), \
         patch.object(server, "_deck_diversity_enabled", lambda: False):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield client, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._trade_jobs_lock:
                for jid in [j for j, job in server._trade_jobs.items()
                            if (job.get("key") or ())[:2] == KEY[:2]]:
                    server._trade_jobs.pop(jid, None)
                server._trade_jobs_by_key.pop(KEY, None)


def _complete_job():
    job_id = server._kickoff_trade_job(sess_token=TOKEN, user_id=UID, league_id=LEAGUE,
                                       scoring_format="1qb_ppr", opponents_total=1,
                                       synchronous=True)
    with server._trade_jobs_lock:
        job = server._trade_jobs[job_id]
    assert job["status"] == "complete" and job["cards"]
    assert job["roster_fp"].startswith("rfp1:")
    assert job["values_snapshot_id"].startswith("vsn1:")
    return job


def _generate(client):
    """POST /generate with the worker spawn stubbed: returns (job_id, kicked_off)."""
    with patch.object(server, "_start_trade_job_thread", MagicMock()) as start:
        resp = client.post("/api/trades/generate", json={"league_id": LEAGUE},
                           headers={"X-Session-Token": TOKEN})
    assert resp.status_code == 200
    return resp.get_json()["job_id"], start.called


def _set_roster(engine, user_id, roster):
    with engine.begin() as conn:
        conn.execute(update(league_members_table)
                     .where(league_members_table.c.league_id == LEAGUE,
                            league_members_table.c.user_id == user_id)
                     .values(roster_data=json.dumps(roster)))


# ── complete job: cache hit vs miss ───────────────────────────────────────────

def test_cache_hit_while_stored_rows_are_unchanged(live):
    client, _ = live
    job = _complete_job()
    assert _generate(client) == (job["job_id"], False)


@pytest.mark.parametrize("change", ["move_player", "move_pick", "add_member"])
def test_complete_job_goes_stale_after_a_stored_roster_change(live, change):
    client, engine = live
    job = _complete_job()
    with engine.begin() as conn:
        if change == "move_player":
            conn.execute(update(league_members_table)
                         .where(league_members_table.c.user_id == OPP)
                         .values(roster_data=json.dumps(["r1"])))
        elif change == "move_pick":
            conn.execute(update(draft_picks_table).values(owner_user_id=OPP))
        else:
            conn.execute(insert(league_members_table).values(
                league_id=LEAGUE, user_id="user_fp_new", roster_data="[]"))
    assert not server._trade_job_is_fresh(job, job["fairness_threshold"], job["outlook_value"],
                                          request_signature=job["request_signature"])
    new_id, kicked_off = _generate(client)
    assert new_id != job["job_id"] and kicked_off


def test_values_change_makes_the_job_stale(live, monkeypatch):
    client, _ = live
    job = _complete_job()
    pool = {"players": [], "seed": {"g1": 1600.0}}
    monkeypatch.setitem(server.g_universal_by_format, "1qb_ppr", pool)
    new_id, kicked_off = _generate(client)
    assert new_id != job["job_id"] and kicked_off


def test_display_name_change_is_still_a_cache_hit(live):
    client, engine = live
    job = _complete_job()
    with engine.begin() as conn:
        conn.execute(update(league_members_table).values(
            username="Renamed", display_name="Renamed FC", updated_at="2030-01-01"))
        # (Not pick_value: it feeds the seeded outlook, so the existing
        # request signature already misses on it.)
        conn.execute(update(draft_picks_table).values(owner_username="Renamed"))
    assert _generate(client) == (job["job_id"], False)


def test_failed_fingerprint_read_fails_closed(live):
    job = _complete_job()
    with patch.object(roster_snapshot, "snapshot_ids", MagicMock(side_effect=RuntimeError("db"))):
        assert not server._trade_job_is_fresh(
            job, job["fairness_threshold"], job["outlook_value"],
            request_signature=job["request_signature"])


# ── running job: join vs supersede ────────────────────────────────────────────

def _register_running_copy(job):
    running = dict(job, job_id="job-fp-running", status="running", finished_at=None, cards=[])
    with server._trade_jobs_lock:
        server._trade_jobs[running["job_id"]] = running
        server._trade_jobs_by_key[KEY] = running["job_id"]
    return running


def test_running_job_is_joined_while_rosters_are_unchanged(live):
    client, _ = live
    running = _register_running_copy(_complete_job())
    assert _generate(client) == (running["job_id"], False)
    assert "superseded" not in running


def test_running_job_is_not_joined_after_a_stored_roster_change(live):
    client, engine = live
    running = _register_running_copy(_complete_job())
    _set_roster(engine, OPP, ["r1", "r2", "r9"])
    assert not server._trade_running_matches(
        running, running["fairness_threshold"], running["outlook_value"],
        request_signature=running["request_signature"])
    new_id, kicked_off = _generate(client)
    assert new_id != running["job_id"] and kicked_off
    assert running["superseded"] is True


def test_running_job_is_still_joined_after_a_display_name_change(live):
    client, engine = live
    running = _register_running_copy(_complete_job())
    with engine.begin() as conn:
        conn.execute(update(league_members_table).values(display_name="Renamed FC"))
    assert _generate(client) == (running["job_id"], False)


# ── on_roster_change → the trades handler ────────────────────────────────────

def test_on_roster_change_revokes_every_job_in_the_league_only():
    def park(job_id, user_id, league_id):
        job = {"job_id": job_id, "key": (user_id, league_id, "1qb_ppr"), "status": "complete",
               "input_epochs": server._capture_trade_input_epochs(user_id, league_id),
               "cards": [], "error": None}
        with server._trade_jobs_lock:
            server._trade_jobs[job_id] = job
            server._trade_jobs_by_key[job["key"]] = job_id
        return job

    jobs = [park("j-a", "u-a", "league-x"), park("j-b", "u-b", "league-x"),
            park("j-c", "u-a", "league-y")]
    try:
        assert server._invalidate_league_trade_jobs_on_roster_change in \
            roster_snapshot._roster_change_handlers
        roster_snapshot.on_roster_change("league-x", "rfp1:old", "rfp1:new")
        with server._trade_jobs_lock:
            revoked = {j["job_id"]: server._trade_job_revoked(j) for j in jobs}
            indexed = {j["job_id"]: server._trade_jobs_by_key.get(j["key"]) for j in jobs}
        assert revoked == {"j-a": True, "j-b": True, "j-c": False}
        assert indexed == {"j-a": None, "j-b": None, "j-c": "j-c"}
    finally:
        with server._trade_jobs_lock:
            for job in jobs:
                server._trade_jobs.pop(job["job_id"], None)
                server._trade_jobs_by_key.pop(job["key"], None)
