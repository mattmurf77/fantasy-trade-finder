"""`force: true` must supersede an already-RUNNING deck job.

docs/reviews/2026-08-18-bug-sweep — `/api/trades/generate` gated the cache-hit
branch on `force` but not the in-flight branch, so a forced regeneration that
arrived while a job was running returned that job verbatim (same job_id, same
minted trade_ids) and the regeneration never happened. It bit the Quick Set →
Trades handoff — "That's your board now. The deck rebuilds around it." — and
it is the same reason any board change that alters values (an override
released by a newer vote, say) could be invisible to the user.

There is NO cancellation mechanism in the job registry, so the fix has two
halves and both are load-bearing:

  1. a forced request spawns a fresh job, and
  2. the orphaned worker finishes QUIETLY — no further snapshot publishes, no
     deck-impression rows, no trades_generated event.

Without (2), every forced regeneration would silently write impression rows
for a deck no user was ever served, corrupting the corpus that the whole deck
signal pipeline is built on. That is the regression this file guards hardest.

Harness: test_deck_signal_v2 / test_deck_replenishment's in-memory SQLite +
live-session pattern.
"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.server as server
from backend.database import deck_impressions_table, metadata
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

UID = "user_force"
OPP = "user_force_opp"
LEAGUE = "league_force"
TOKEN = "sess-force-tok"
KEY = (UID, LEAGUE, "1qb_ppr")


@pytest.fixture()
def live(monkeypatch):
    """A registered session over an isolated in-memory DB, seeded so the
    likes-you path guarantees at least one generated card."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)

    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(
        league_id=LEAGUE, name="Force League", platform="sleeper",
        members=[
            LeagueMember(user_id=UID, username="me", roster=["g1", "g2"], elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp", roster=["r1", "r2"], elo_ratings={}),
        ],
    )
    trade_svc.add_league(league)
    sess = {
        "verified": True,
        "user_id": UID, "league": league, "user_roster": ["g1", "g2"],
        "players": pool, "services": {"1qb_ppr": service},
        "trade_svcs": {"1qb_ppr": trade_svc}, "service": service,
        "trade_svc": trade_svc, "active_format": "1qb_ppr", "last_active": 0.0,
    }
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO trade_decisions "
            "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
            "VALUES (:uid, :lid, :give, :recv, 'like', :created)"
        ), {"uid": OPP, "lid": LEAGUE, "give": json.dumps(["r1"]),
            "recv": json.dumps(["g1"]),
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
            yield client, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._trade_jobs_lock:
                for jid in [j for j, job in server._trade_jobs.items()
                            if job.get("key") == KEY]:
                    server._trade_jobs.pop(jid, None)
                server._trade_jobs_by_key.pop(KEY, None)


def _generate(client, **body):
    return client.post("/api/trades/generate",
                       json={"league_id": LEAGUE, **body},
                       headers={"X-Session-Token": TOKEN})


def _register_running_job(job_id="job-in-flight"):
    """Park a running job in the registry, exactly as _kickoff_trade_job
    would, without spawning a worker."""
    job = {
        "job_id": job_id, "key": KEY, "status": "running",
        "started_at": 0.0, "finished_at": None,
        "opponents_done": 0, "opponents_total": 1,
        "cards": [], "error": None, "fairness_threshold": 0.75,
        "outlook_value": None, "is_pinned": False, "trade_intent": None,
    }
    with server._trade_jobs_lock:
        server._trade_jobs[job_id] = job
        server._trade_jobs_by_key[KEY] = job_id
    return job


# ═══════════════════════════════════════════════════════════════════════════
# (a) + (b) — the routing decision
# ═══════════════════════════════════════════════════════════════════════════

def test_forced_request_while_running_spawns_a_new_job(live):
    """THE bug. A forced regeneration must not be answered with the job that
    is already in flight."""
    client, _ = live
    old = _register_running_job()

    with patch.object(server, "_kickoff_trade_job",
                      MagicMock(return_value="job-new")) as kick:
        with server._trade_jobs_lock:
            server._trade_jobs["job-new"] = dict(old, job_id="job-new", cards=[])
        resp = _generate(client, force=True)

    assert resp.status_code == 200
    kick.assert_called_once()
    assert resp.get_json()["job_id"] == "job-new"
    assert old["superseded"] is True


def test_unforced_request_while_running_still_shares(live):
    """Unchanged behaviour: concurrent unforced taps share one worker."""
    client, _ = live
    old = _register_running_job()

    with patch.object(server, "_kickoff_trade_job", MagicMock()) as kick:
        resp = _generate(client)

    kick.assert_not_called()
    assert resp.get_json()["job_id"] == "job-in-flight"
    assert "superseded" not in old


def test_kill_switch_restores_the_silent_share(live):
    """force_supersedes_running=0 is the deploy-free revert."""
    client, _ = live
    old = _register_running_job()

    with patch.object(server, "_force_supersede_enabled", lambda: False), \
         patch.object(server, "_kickoff_trade_job", MagicMock()) as kick:
        resp = _generate(client, force=True)

    kick.assert_not_called()
    assert resp.get_json()["job_id"] == "job-in-flight"
    assert "superseded" not in old


def test_supersede_marker_is_never_serialized_to_clients(live):
    """`_trade_job_public_view` picks its keys explicitly; keep it that way so
    an internal marker cannot leak into the client contract."""
    job = _register_running_job()
    job["superseded"] = True
    assert "superseded" not in server._trade_job_public_view(job)


def test_a_superseded_job_may_not_publish(live):
    """`_job_live` is the single gate every publish site now goes through."""
    job = _register_running_job()
    assert server._job_live(job) is True
    job["superseded"] = True
    assert server._job_live(job) is False


# ═══════════════════════════════════════════════════════════════════════════
# (c) — the regression guard: a superseded deck writes NO impressions
# ═══════════════════════════════════════════════════════════════════════════

def _impression_count(engine):
    with engine.connect() as conn:
        return len(conn.execute(select(deck_impressions_table)).fetchall())


def _run_one_job_synchronously():
    return server._kickoff_trade_job(
        sess_token=TOKEN, user_id=UID, league_id=LEAGUE,
        scoring_format="1qb_ppr", opponents_total=1, synchronous=True,
    )


def test_control_a_normal_job_does_write_impressions(live):
    """The control. Without it, the assertion below could pass because the
    harness never writes impressions at all."""
    _, engine = live
    with patch.object(server, "_deck_signal_v2_enabled", lambda: True):
        _run_one_job_synchronously()
    assert _impression_count(engine) > 0


def test_a_superseded_job_writes_no_impressions(live):
    """THE regression guard. The worker keeps running — nothing can stop it —
    but a deck nobody will ever see must leave no trace in the corpus.

    The supersede is injected through `_deck_signal_v2_enabled`, which the
    worker evaluates immediately before the supersede check, so this
    reproduces the real race: the marker lands while the job is mid-flight.
    """
    _, engine = live

    def _flag_then_supersede():
        with server._trade_jobs_lock:
            jid = server._trade_jobs_by_key.get(KEY)
            if jid:
                server._trade_jobs[jid]["superseded"] = True
        return True

    with patch.object(server, "_deck_signal_v2_enabled", _flag_then_supersede), \
         patch.object(server, "record_event", MagicMock()) as ev:
        _run_one_job_synchronously()

    assert _impression_count(engine) == 0
    # ...and it must not count as a generated deck either — a deck that was
    # never served would overstate supply in every per-deck rate.
    assert not [c for c in ev.call_args_list
                if len(c.args) > 1 and c.args[1] == "trades_generated"]


def test_a_superseded_job_still_reaches_a_terminal_status(live):
    """A client still holding the old job_id must not poll forever."""
    _, engine = live

    def _flag_then_supersede():
        with server._trade_jobs_lock:
            jid = server._trade_jobs_by_key.get(KEY)
            if jid:
                server._trade_jobs[jid]["superseded"] = True
        return True

    with patch.object(server, "_deck_signal_v2_enabled", _flag_then_supersede):
        job_id = _run_one_job_synchronously()

    with server._trade_jobs_lock:
        assert server._trade_jobs[job_id]["status"] == "complete"
