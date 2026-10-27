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


def _fresh(job):
    return server._trade_job_is_fresh(job, job["fairness_threshold"], job["outlook_value"],
                                      request_signature=job["request_signature"],
                                      fingerprints=server._trade_current_fingerprints(LEAGUE, "1qb_ppr"))


@pytest.mark.parametrize("change", ["move_player", "move_pick", "add_member"])
def test_complete_job_goes_stale_after_a_stored_roster_change(live, change):
    client, engine = live
    job = _complete_job()
    assert _fresh(job)
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
    assert not _fresh(job)
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
    client, _ = live
    job = _complete_job()
    with patch.object(roster_snapshot, "snapshot_ids", MagicMock(side_effect=RuntimeError("db"))):
        assert server._trade_current_fingerprints(LEAGUE, "1qb_ppr") is None
        assert not _fresh(job)
        new_id, kicked_off = _generate(client)
    assert new_id != job["job_id"] and kicked_off
    with server._trade_jobs_lock:
        stamped = dict(server._trade_jobs[new_id])
    # A failed kickoff read stamps None, which never matches a good read.
    assert stamped["roster_fp"] is None
    assert not server._trade_fingerprints_match(
        stamped, server._trade_current_fingerprints(LEAGUE, "1qb_ppr"))


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

    def joins():
        return server._trade_running_matches(
            running, running["fairness_threshold"], running["outlook_value"],
            request_signature=running["request_signature"],
            fingerprints=server._trade_current_fingerprints(LEAGUE, "1qb_ppr"))

    assert joins()
    _set_roster(engine, OPP, ["r1", "r2", "r9"])
    assert not joins()
    new_id, kicked_off = _generate(client)
    assert new_id != running["job_id"] and kicked_off
    assert running["superseded"] is True


def test_running_job_is_still_joined_after_a_display_name_change(live):
    client, engine = live
    running = _register_running_copy(_complete_job())
    with engine.begin() as conn:
        conn.execute(update(league_members_table).values(display_name="Renamed FC"))
    assert _generate(client) == (running["job_id"], False)


def test_a_failed_read_keeps_the_running_job(live):
    """A2 (contract §4.4): a failed fingerprint read can't prove a running job
    stale, so it is kept (joined, never superseded); a failed read still never
    makes a completed job fresh."""
    client, _ = live
    job = _complete_job()
    running = _register_running_copy(job)
    with patch.object(roster_snapshot, "snapshot_ids", MagicMock(side_effect=RuntimeError("db"))):
        assert server._trade_current_fingerprints(LEAGUE, "1qb_ppr") is None
        assert server._trade_running_matches(
            running, running["fairness_threshold"], running["outlook_value"],
            request_signature=running["request_signature"], fingerprints=None)
        assert _generate(client) == (running["job_id"], False)
    assert "superseded" not in running
    assert not server._trade_job_is_fresh(job, job["fairness_threshold"], job["outlook_value"],
                                          request_signature=job["request_signature"],
                                          fingerprints=None)


# ── on_roster_change → the trades handler ────────────────────────────────────
#
# A job is built on its session's own Sleeper read, so the handler revokes only
# when a rebuild would read newer rosters: the job's read is older than the
# refreshed rows' (`refreshed_at`) and its user holds a session whose read is
# at least that new (#470 QA P2-2, P2-1). Stamp-less jobs are unchecked (P3-1).

READ_OLD = "2026-10-27T10:00:00.000000+00:00"      # an earlier init's Sleeper read
READ_NOW = "2026-10-27T11:00:00.000000+00:00"      # the read the refresh committed
READ_LATER = "2026-10-27T11:05:00.000000+00:00"


@pytest.fixture()
def hook_db(monkeypatch):
    """In-memory rows for the handler's `league_roster_state` read; parks and
    removes sessions and jobs."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(server, "_roster_moved_reads", {})
    tokens, job_ids = [], []

    def session(token, user_id, league_id, read):
        with server._sessions_lock:
            server._sessions[token] = {"user_id": user_id, "roster_fetch_started_at": read,
                                       "league": League(league_id=league_id, name="L",
                                                        platform="sleeper", members=[])}
        tokens.append(token)

    def job(job_id, user_id, league_id, *, read, roster_fp="rfp1:old", stamped=True):
        j = {"job_id": job_id, "key": (user_id, league_id, "1qb_ppr"), "status": "complete",
             "cards": [{"trade_id": "t"}], "error": None, "values_snapshot_id": "vsn1:x",
             "roster_fetch_started_at": read}
        if stamped:
            j["roster_fp"] = roster_fp
        with server._trade_jobs_lock:
            server._trade_jobs[job_id] = j
            server._trade_jobs_by_key[j["key"]] = job_id
        job_ids.append(job_id)
        return j

    yield session, job
    with server._sessions_lock:
        for token in tokens:
            server._sessions.pop(token, None)
    with server._trade_jobs_lock:
        for job_id in job_ids:
            parked = server._trade_jobs.pop(job_id, None)
            if parked and server._trade_jobs_by_key.get(parked["key"]) == job_id:
                server._trade_jobs_by_key.pop(parked["key"], None)


def _revoked(*jobs):
    with server._trade_jobs_lock:
        return {j["job_id"]: server._trade_job_revoked(j) for j in jobs}


def test_the_handler_is_debounced_by_fingerprint(hook_db):
    """A3: a job already stamped `new_fp` is kept, so a double call, or a call
    landing after a rebuild, changes nothing for the rebuilt job."""
    session, job = hook_db
    db_module.mark_league_roster_fresh("league-d", READ_NOW)
    session("t-d", "u-d", "league-d", READ_NOW)
    old = job("j-old", "u-d", "league-d", read=READ_OLD)
    rebuilt = job("j-new", "u-d", "league-d", read=READ_NOW, roster_fp="rfp1:new")
    with server._trade_jobs_lock:
        server._trade_jobs_by_key[rebuilt["key"]] = "j-new"
    roster_snapshot.on_roster_change("league-d", "rfp1:old", "rfp1:new")
    roster_snapshot.on_roster_change("league-d", "rfp1:old", "rfp1:new")      # the double call
    assert old.get("superseded") is True
    assert "superseded" not in rebuilt
    with server._trade_jobs_lock:
        assert server._trade_jobs_by_key.get(rebuilt["key"]) == "j-new"


def test_on_roster_change_revokes_only_what_a_fresher_session_would_rebuild(hook_db):
    """The refreshing user's older deck is revoked (Try again reads the new
    rosters). A league-mate whose session predates the refresh keeps theirs
    (P2-1: their rebuild would read the same rosters), and another league is
    untouched."""
    session, job = hook_db
    db_module.mark_league_roster_fresh("league-x", READ_NOW)
    session("t-a", "u-a", "league-x", READ_NOW)      # the init that refreshed
    session("t-b", "u-b", "league-x", READ_OLD)      # a league-mate, opened earlier
    session("t-a2", "u-a", "league-y", READ_NOW)
    jobs = [job("j-a", "u-a", "league-x", read=READ_OLD),
            job("j-b", "u-b", "league-x", read=READ_OLD),
            job("j-c", "u-a", "league-y", read=READ_OLD)]
    assert server._invalidate_league_trade_jobs_on_roster_change in \
        roster_snapshot._roster_change_handlers
    roster_snapshot.on_roster_change("league-x", "rfp1:old", "rfp1:new")
    assert _revoked(*jobs) == {"j-a": True, "j-b": False, "j-c": False}
    with server._trade_jobs_lock:
        indexed = {j["job_id"]: server._trade_jobs_by_key.get(j["key"]) for j in jobs}
    assert indexed == {"j-a": None, "j-b": "j-b", "j-c": "j-c"}


def test_a_job_built_on_the_refreshed_read_is_kept(hook_db):
    """P2-2: the init's own pre-gen (or a tap before the daemon commits) is
    stamped from the old rows but built on the read being committed, or a
    later one. A job with no read, or a failed stamp (None), on an older
    session is revoked."""
    session, job = hook_db
    db_module.mark_league_roster_fresh("league-p", READ_NOW)
    session("t-p", "u-p", "league-p", READ_LATER)
    kept = [job("j-same", "u-p", "league-p", read=READ_NOW),
            job("j-later", "u-p", "league-p", read=READ_LATER)]
    gone = [job("j-none", "u-p", "league-p", read=None),
            job("j-failed", "u-p", "league-p", read=READ_OLD, roster_fp=None)]
    server._invalidate_league_trade_jobs_on_roster_change("league-p", "rfp1:old", "rfp1:new")
    assert _revoked(*kept, *gone) == {"j-same": False, "j-later": False,
                                      "j-none": True, "j-failed": True}


def test_a_stampless_job_is_never_revoked(hook_db):
    """P3-1: a job with no `roster_fp` key (prepared inventory, hand-built) is
    unchecked, as in `_trade_fingerprints_match`, including at a league's first
    stamp (old None)."""
    session, job = hook_db
    db_module.mark_league_roster_fresh("league-s", READ_NOW)
    session("t-s", "u-s", "league-s", READ_NOW)
    prepared = job("j-prep", "u-s", "league-s", read=None, stamped=False)
    server._invalidate_league_trade_jobs_on_roster_change("league-s", None, "rfp1:first")
    assert _revoked(prepared) == {"j-prep": False}
    assert server._trade_fingerprints_match(prepared, ("rfp1:first", "vsn1:x"))


@pytest.mark.parametrize("state", ["no_row", "no_refreshed_at", "read_fails"])
def test_no_refreshed_read_revokes_nothing(hook_db, monkeypatch, state):
    """Nothing to compare against: keep every job (the pre-#470 behaviour),
    and never raise into platforms-eng's refresh."""
    session, job = hook_db
    session("t-n", "u-n", "league-n", READ_NOW)
    parked = job("j-n", "u-n", "league-n", read=READ_OLD)
    if state == "no_refreshed_at":
        db_module.mark_league_roster_failed("league-n", "write_failed")
    elif state == "read_fails":
        monkeypatch.setattr(db_module, "get_league_roster_state",
                            MagicMock(side_effect=RuntimeError("db")))
    server._invalidate_league_trade_jobs_on_roster_change("league-n", "rfp1:old", "rfp1:new")
    assert _revoked(parked) == {"j-n": False}


def test_the_handler_never_raises_and_is_off_in_mode_0_or_knob_0(hook_db, monkeypatch):
    session, job = hook_db
    db_module.mark_league_roster_fresh("league-m", READ_NOW)
    session("t-m", "u-m0", "league-m", READ_NOW)
    parked = job("j-m0", "u-m0", "league-m", read=READ_OLD)
    monkeypatch.setattr(server, "_trade_i1_mode", lambda: 0)
    server._invalidate_league_trade_jobs_on_roster_change("league-m", "rfp1:old", "rfp1:new")
    assert "superseded" not in parked
    monkeypatch.setattr(server, "_trade_i1_mode", lambda: 1)
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_roster_change_revoke", 0.0)
    server._invalidate_league_trade_jobs_on_roster_change("league-m", "rfp1:old", "rfp1:new")
    assert "superseded" not in parked
    assert server._roster_moved_reads == {}                   # no move recorded at 0
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_roster_change_revoke", 1.0)
    monkeypatch.setattr(server, "_revoke_trade_job_locked",
                        MagicMock(side_effect=RuntimeError("boom")))
    server._invalidate_league_trade_jobs_on_roster_change("league-m", "rfp1:old", "rfp1:new")


@pytest.mark.parametrize("value", [float("nan"), 7.0, -1.0, "off please"])
def test_the_revoke_knob_reads_on_for_anything_but_0(monkeypatch, value):
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_roster_change_revoke", value)
    assert server._roster_change_revoke_on()


def test_the_revoke_knob_is_seeded_on():
    seeds = [row for row in db_module._MODEL_CONFIG_DEFAULTS
             if row[0] == "trade_roster_change_revoke"]
    assert len(seeds) == 1 and seeds[0][1] == 1.0


def test_only_this_league_s_sessions_count(hook_db):
    """#481 QA S6: the user's newer read in ANOTHER league doesn't make their
    deck here revocable."""
    session, job = hook_db
    db_module.mark_league_roster_fresh("league-6", READ_NOW)
    session("t-6a", "u-6", "league-6", READ_OLD)
    session("t-6b", "u-6", "league-other", READ_LATER)
    parked = job("j-6", "u-6", "league-6", read=READ_OLD)
    server._invalidate_league_trade_jobs_on_roster_change("league-6", "rfp1:old", "rfp1:new")
    assert _revoked(parked) == {"j-6": False}


def test_the_user_s_newest_session_read_counts(hook_db):
    """#481 QA S7: with two sessions in the league (two devices), the newer
    read decides, whichever session was opened first."""
    session, job = hook_db
    db_module.mark_league_roster_fresh("league-7", READ_NOW)
    session("t-7a", "u-7", "league-7", READ_NOW)
    session("t-7b", "u-7", "league-7", READ_OLD)
    parked = job("j-7", "u-7", "league-7", read=READ_OLD)
    server._invalidate_league_trade_jobs_on_roster_change("league-7", "rfp1:old", "rfp1:new")
    assert _revoked(parked) == {"j-7": True}


def test_the_handler_records_the_move_s_read(hook_db):
    """P3-1's input: the newest moved read per league, never rewound."""
    session, job = hook_db
    db_module.mark_league_roster_fresh("league-r", READ_NOW)
    server._invalidate_league_trade_jobs_on_roster_change("league-r", "rfp1:a", "rfp1:b")
    assert server._roster_moved_reads == {"league-r": READ_NOW}
    server._roster_moved_reads["league-r"] = READ_LATER
    server._invalidate_league_trade_jobs_on_roster_change("league-r", "rfp1:b", "rfp1:c")
    assert server._roster_moved_reads == {"league-r": READ_LATER}


def test_a_job_on_the_refreshed_read_is_restamped_when_its_picks_match(hook_db):
    """#481 QA P3-2: built on exactly the committed read, with the committed
    picks and draft state, the job was built on `new_fp`. A different picks
    key, no key, an older read or a revoked job keeps its stamp."""
    session, job = hook_db
    db_module.mark_league_roster_fresh("league-k", READ_NOW)
    session("t-k", "u-k", "league-k", READ_NOW)
    stored = server._roster_picks_key("league-k")
    match = job("j-match", "u-k", "league-k", read=READ_NOW)
    match["roster_picks_key"] = stored
    moved = job("j-moved", "u-k", "league-k", read=READ_NOW)
    moved["roster_picks_key"] = "rfp1:other-picks"
    keyless = job("j-keyless", "u-k", "league-k", read=READ_NOW)
    later = job("j-later", "u-k", "league-k", read=READ_LATER)
    later["roster_picks_key"] = stored
    server._invalidate_league_trade_jobs_on_roster_change("league-k", "rfp1:old", "rfp1:new")
    stamps = {j["job_id"]: j["roster_fp"] for j in (match, moved, keyless, later)}
    assert stamps == {"j-match": "rfp1:new", "j-moved": "rfp1:old",
                      "j-keyless": "rfp1:old", "j-later": "rfp1:old"}
    assert _revoked(match, moved, keyless, later) == dict.fromkeys(stamps, False)


def test_the_picks_key_is_taken_only_while_the_session_s_refresh_is_in_flight(hook_db,
                                                                            monkeypatch):
    db_module.mark_league_roster_fresh("league-q", READ_NOW)
    assert server._roster_picks_key_pending("league-q", READ_OLD) is None
    assert server._roster_picks_key_pending("league-q", READ_NOW) is None
    assert server._roster_picks_key_pending("league-q", None) is None
    assert server._roster_picks_key_pending("league-q", READ_LATER) == \
        server._roster_picks_key("league-q")
    assert server._roster_picks_key_pending("league-never", READ_OLD) is not None
    monkeypatch.setattr(server, "_trade_i1_mode", lambda: 0)
    assert server._roster_picks_key_pending("league-q", READ_LATER) is None
    monkeypatch.setattr(server, "_trade_i1_mode", lambda: 1)
    monkeypatch.setattr(db_module, "get_league_roster_state",
                        MagicMock(side_effect=RuntimeError("db")))
    assert server._roster_picks_key_pending("league-q", READ_LATER) is None


def _set_pick_owner(engine, owner):
    with engine.begin() as conn:
        conn.execute(update(draft_picks_table)
                     .where(draft_picks_table.c.pick_id == f"{LEAGUE}_2027_1_1")
                     .values(owner_user_id=owner))


@pytest.mark.parametrize("change", ["player", "pick"])
def test_the_init_s_own_deck_survives_its_refresh_stamp(live, monkeypatch, change):
    """#470 QA P2-2 repro: the deck is stamped from the stored rows before the
    init's daemon commits the read it was built on, then the stamp's hook
    fires. The deck is kept and a deck from the user's previous read is
    revoked. #481 QA P3-2: after a player move its picks are the committed
    ones, so it is re-stamped and the next tap reuses it; after a pick move it
    keeps its old stamp and is never reused."""
    client, engine = live
    monkeypatch.setattr(server, "_roster_moved_reads", {})
    with server._sessions_lock:
        server._sessions[TOKEN]["roster_fetch_started_at"] = READ_OLD
    previous = _complete_job()
    with server._sessions_lock:
        server._sessions[TOKEN]["roster_fetch_started_at"] = READ_NOW
    with server._trade_jobs_lock:
        server._trade_jobs_by_key.pop(KEY)                     # the new init kicks its own
    pregen = _complete_job()
    assert (previous["roster_fetch_started_at"], pregen["roster_fetch_started_at"]) == \
        (READ_OLD, READ_NOW)
    assert pregen["roster_picks_key"]                          # the refresh is in flight
    old_fp = pregen["roster_fp"]
    if change == "player":
        _set_roster(engine, OPP, ["r2"])                      # the daemon commits the read
    else:
        _set_pick_owner(engine, OPP)
    db_module.mark_league_roster_fresh(LEAGUE, READ_NOW)
    new_fp, _ = server._trade_current_fingerprints(LEAGUE, "1qb_ppr")
    assert new_fp != old_fp
    roster_snapshot.on_roster_change(LEAGUE, old_fp, new_fp)
    assert _revoked(previous, pregen) == {previous["job_id"]: True, pregen["job_id"]: False}
    if change == "player":
        assert pregen["roster_fp"] == new_fp and _fresh(pregen)
        assert _generate(client) == (pregen["job_id"], False)
    else:
        assert pregen["roster_fp"] == old_fp and not _fresh(pregen)


def test_a_stale_session_s_rebuild_is_reused_only_by_that_session(live, monkeypatch):
    """#481 QA P3-1: device 1 holds the user's read from before a roster move,
    device 2 the read that moved it. Device 1's rebuild is stamped from the
    moved rows but built on device 1's rosters: device 2 never reuses or joins
    it, device 1 does, and its pages are never stored."""
    client, engine = live
    monkeypatch.setattr(server, "_roster_moved_reads", {})
    with server._sessions_lock:
        device1 = dict(server._sessions[TOKEN], roster_fetch_started_at=READ_OLD)
        server._sessions["sess-fp-tok-2"] = device1
        server._sessions[TOKEN]["roster_fetch_started_at"] = READ_NOW
    try:
        _set_roster(engine, OPP, ["r2"])
        db_module.mark_league_roster_fresh(LEAGUE, READ_NOW)
        new_fp, _ = server._trade_current_fingerprints(LEAGUE, "1qb_ppr")
        roster_snapshot.on_roster_change(LEAGUE, "rfp1:before", new_fp)
        stale_id = server._kickoff_trade_job(sess_token="sess-fp-tok-2", user_id=UID,
                                             league_id=LEAGUE, scoring_format="1qb_ppr",
                                             opponents_total=1, synchronous=True)
        with server._trade_jobs_lock:
            stale = server._trade_jobs[stale_id]
        assert (stale["roster_fp"], stale["roster_fetch_started_at"]) == (new_fp, READ_OLD)
        assert _fresh(stale)                                   # the stamp alone matches
        with server._trade_jobs_lock:
            assert server._job_read_predates_move(stale)
            assert not server._trade_fingerprints_match(
                stale, (new_fp, stale["values_snapshot_id"]), session_read=READ_NOW)
            assert server._trade_fingerprints_match(
                stale, (new_fp, stale["values_snapshot_id"]), session_read=READ_OLD)
            assert not server._trade_running_policy_matches(
                dict(stale, status="running", finished_at=None), stale["presentation_capture"],
                (new_fp, stale["values_snapshot_id"]), session_read=READ_NOW)
        with patch.object(server, "_start_trade_job_thread", MagicMock()) as start:
            resp = client.post("/api/trades/generate", json={"league_id": LEAGUE},
                               headers={"X-Session-Token": "sess-fp-tok-2"})
        assert (resp.get_json()["job_id"], start.called) == (stale_id, False)   # device 1
        device2_id, kicked = _generate(client)
        assert device2_id != stale_id and kicked                               # device 2
        eligible = MagicMock(return_value=True)
        with patch.object(server, "_trade_page_store_enabled", lambda: True), \
             patch.object(server, "_job_page_eligible", eligible):
            assert server._store_trade_page_row(stale_id) is False
        assert not eligible.called
    finally:
        with server._sessions_lock:
            server._sessions.pop("sess-fp-tok-2", None)
