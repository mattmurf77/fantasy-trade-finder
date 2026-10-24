"""S0 I-1 at serve: never serve a card with an asset either side no longer owns.

The job is built from the session's rosters, which can trail the stored rows
(another member's session-init or a refresh wrote newer ones). So the stored
rows already show the moves when the job is stamped: the job stays fresh, and
`_trade_job_public_view` must drop every card whose give asset the viewer no
longer owns, or whose receive asset the opponent no longer owns. That covers
players and picks, on the /generate cache-hit path and the /status path. When
the check itself fails, no cards are served: status "error", error
"roster_check_unavailable". Harness: test_force_supersedes_running_job's.
"""
import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, delete, insert, text

import backend.database as db_module
import backend.server as server
from backend import roster_snapshot
from backend.database import draft_picks_table, league_members_table, metadata
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

UID = "user_i1"
OPP = "user_i1_opp"
THIRD = "user_i1_third"
LEAGUE = "league_i1"
TOKEN = "sess-i1-tok"
KEY = (UID, LEAGUE, "1qb_ppr")

PK_MINE = f"{LEAGUE}_2027_1_1"
PK_OPP = f"{LEAGUE}_2027_1_2"
PK_GONE_FROM_ME = f"{LEAGUE}_2027_2_1"
PK_GONE_FROM_OPP = f"{LEAGUE}_2027_2_2"

# Stored truth: g1 moved from me to OPP; r1 moved from OPP to THIRD; one pick
# each moved from me and from OPP to THIRD.
STORED_ROSTERS = {UID: ["g2"], OPP: ["r2", "g1"], THIRD: ["r1"]}
STORED_PICKS = {PK_MINE: UID, PK_OPP: OPP, PK_GONE_FROM_ME: THIRD, PK_GONE_FROM_OPP: THIRD}

CARDS = {  # trade_id -> (give, receive)
    "ok-players":       (["g2"], ["r2"]),
    "ok-picks":         ([PK_MINE], [PK_OPP]),
    "moved-give-player": (["g1"], ["r2"]),
    "moved-recv-player": (["g2"], ["r1"]),
    "moved-give-pick":   ([PK_GONE_FROM_ME], ["r2"]),
    "moved-recv-pick":   (["g2"], [PK_GONE_FROM_OPP]),
}
SERVABLE = {"ok-players", "ok-picks"}


def _card(trade_id, give, receive):
    return {"trade_id": trade_id, "league_id": LEAGUE, "target_user_id": OPP,
            "target_username": "opp", "give": [{"id": pid} for pid in give],
            "receive": [{"id": pid} for pid in receive], "decision": None}


@pytest.fixture()
def live(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)

    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    # The session's (older) view of the league: nothing has moved yet.
    league = League(league_id=LEAGUE, name="I1 League", platform="sleeper", members=[
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
        for uid, roster in STORED_ROSTERS.items():
            conn.execute(insert(league_members_table).values(
                league_id=LEAGUE, user_id=uid, username=uid, display_name=uid,
                roster_data=json.dumps(roster), updated_at="2026-10-20"))
        for pick_id, owner in STORED_PICKS.items():
            conn.execute(insert(draft_picks_table).values(
                pick_id=pick_id, league_id=LEAGUE, season=2027, round=1,
                owner_user_id=owner, original_roster_id="1", pool_value=10.0))

    client = server.app.test_client()
    with patch.object(server, "load_member_rankings", MagicMock(return_value={})), \
         patch.object(server, "load_league_preference", MagicMock(return_value=None)), \
         patch.object(server, "_likes_you_enabled", lambda: True), \
         patch.object(server, "_thompson_deck_enabled", lambda: False), \
         patch.object(server, "_deck_diversity_enabled", lambda: False):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield client, engine, sess
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._trade_jobs_lock:
                for jid in [j for j, job in server._trade_jobs.items()
                            if job.get("key") == KEY]:
                    server._trade_jobs.pop(jid, None)
                server._trade_jobs_by_key.pop(KEY, None)


def _complete_job_with_cards():
    job_id = server._kickoff_trade_job(sess_token=TOKEN, user_id=UID, league_id=LEAGUE,
                                       scoring_format="1qb_ppr", opponents_total=1,
                                       synchronous=True)
    with server._trade_jobs_lock:
        job = server._trade_jobs[job_id]
        assert job["status"] == "complete"
        # Published card lists are replaced, never mutated in place.
        job["cards"] = [_card(tid, give, recv) for tid, (give, recv) in CARDS.items()]
    return job


def _via_generate(client):
    with patch.object(server, "_start_trade_job_thread", MagicMock()) as start:
        resp = client.post("/api/trades/generate", json={"league_id": LEAGUE},
                           headers={"X-Session-Token": TOKEN})
    assert resp.status_code == 200 and not start.called, "expected the cache-hit path"
    return resp.get_json()


def _via_status(client, job_id):
    resp = client.get(f"/api/trades/status?job_id={job_id}",
                      headers={"X-Session-Token": TOKEN})
    assert resp.status_code == 200
    return resp.get_json()


def _unchecked_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("[i1] unchecked")]


@pytest.mark.parametrize("path", ["generate", "status"])
def test_moved_players_and_picks_are_never_served(live, path, caplog):
    client, _, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    job = _complete_job_with_cards()
    body = _via_generate(client) if path == "generate" else _via_status(client, job["job_id"])
    assert body["job_id"] == job["job_id"]
    assert body["status"] == "complete" and body["error"] is None
    assert {c["trade_id"] for c in body["cards"]} == SERVABLE
    assert _unchecked_lines(caplog) == []        # everything served was checked


def test_generic_picks_are_exempt_from_the_ownership_check(live, caplog):
    """Generic ladder picks are universal pool assets, never on a roster: a
    card carrying them passes I-1 unchanged, and the exemption is logged."""
    _, _, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    job = _complete_job_with_cards()
    generic = _card("generic", ["g2", "generic_pick_1_early"], ["r2", "generic_pick_2_mid"])
    generic_but_moved = _card("generic-moved", ["g1", "generic_pick_1_late"], ["r2"])
    job = dict(job, cards=[generic, generic_but_moved])
    out = server._trade_job_public_view(job)
    assert out["cards"] == [generic]
    assert _unchecked_lines(caplog) == [
        "[i1] unchecked: generic_picks league=league_i1 cards=1 generic_picks=2"]


@pytest.mark.parametrize("path", ["generate", "status"])
def test_check_error_serves_no_cards(live, path):
    client, _, _ = live
    job = _complete_job_with_cards()
    with patch.object(roster_snapshot, "roster_snapshot",
                      MagicMock(side_effect=RuntimeError("db unavailable"))):
        body = _via_generate(client) if path == "generate" else _via_status(client, job["job_id"])
    assert body["cards"] == []
    assert body["status"] == "error"
    assert body["error"] == "roster_check_unavailable"


def test_a_disposition_failure_is_not_reported_as_a_roster_check_error(live):
    """The pre-existing projection swallows its errors into an empty deck; the
    I-1 failure must stay distinct from that."""
    client, _, _ = live
    job = _complete_job_with_cards()
    with patch.object(server, "load_trade_interest_history",
                      MagicMock(side_effect=RuntimeError("history unavailable"))):
        body = _via_status(client, job["job_id"])
    assert body["cards"] == [] and body["status"] == "complete" and body["error"] is None


def test_kickoff_stamps_the_viewers_league_identity(live):
    _, _, sess = live
    assert _complete_job_with_cards()["league_user_id"] == UID
    sess["league_user_id"] = "co_owner_primary"
    job_id = server._kickoff_trade_job(sess_token=TOKEN, user_id=UID, league_id=LEAGUE,
                                       scoring_format="1qb_ppr", opponents_total=1,
                                       synchronous=True, force_fresh=True)
    with server._trade_jobs_lock:
        assert server._trade_jobs[job_id]["league_user_id"] == "co_owner_primary"


def test_co_owner_give_side_is_checked_against_the_league_identity(live):
    """A co-owner's roster row is keyed by the roster's owner_id, not the
    account id, so the give side is checked against the stamped identity."""
    _, engine, _ = live
    job = _complete_job_with_cards()
    with engine.begin() as conn:
        conn.execute(league_members_table.update()
                     .where(league_members_table.c.user_id == UID)
                     .values(user_id="co_owner_primary"))
        conn.execute(draft_picks_table.update()
                     .where(draft_picks_table.c.owner_user_id == UID)
                     .values(owner_user_id="co_owner_primary"))
    as_co_owner = dict(job, league_user_id="co_owner_primary")
    assert {c["trade_id"] for c in server._trade_job_public_view(as_co_owner)["cards"]} == SERVABLE
    as_account = dict(job, league_user_id=UID)
    assert server._trade_job_public_view(as_account)["cards"] == []


def test_league_with_no_stored_rosters_passes_unchanged_and_loudly(live, caplog):
    """No stored league_members rows: nothing to check against (status
    "missing"). Lead ruling 2026-10-20: lenient on today's path, with one
    warning line per serve (P1's page-store serve will be strict)."""
    _, engine, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    job = _complete_job_with_cards()
    with engine.begin() as conn:
        conn.execute(delete(league_members_table))
    assert {c["trade_id"] for c in server._trade_job_public_view(dict(job))["cards"]} == set(CARDS)
    lines = [r for r in caplog.records if r.getMessage().startswith("[i1] unchecked")]
    assert [(r.levelno, r.getMessage()) for r in lines] == [(
        logging.WARNING,
        f"[i1] unchecked: league_members_missing league={LEAGUE} cards={len(CARDS)} generic_picks=0")]
