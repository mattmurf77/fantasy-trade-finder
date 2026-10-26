"""S0 at serve (roster contract v0.4 §3, §3b, §5b): I-1 and the gate misses.

The job is built from the session's rosters, which can trail the stored rows
(another member's session-init or a refresh wrote newer ones). So the stored
rows already show the moves when the job is stamped: the job stays fresh, and
`_trade_job_public_view` must drop every card whose give asset the viewer no
longer owns, or whose receive asset the opponent no longer owns, for players
and picks, on the /generate cache-hit path and the /status path.

Also pinned: the C-a log line; C-d (an unknown pick owner passes); generic
picks; the `trade_i1_mode` knob (strict / lenient / off); the two no-card gate
misses (`roster_check_unavailable`, and the §3b withhold with `wait_reason`)
served only at `trade_gate_miss_mode` 1 and held at its default 0; the paged
cursor; co-owners. Harness: test_force_supersedes_running_job's.
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, delete, insert, text, update

import backend.database as db_module
import backend.server as server
from backend import roster_snapshot, trade_service as ts
from backend.database import (draft_picks_table, league_members_table,
                              league_roster_state_table, leagues_table, metadata)
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


def _serve_lines(caplog):
    """The C-a lines, each parsed to {key: value}."""
    out = []
    for record in caplog.records:
        message = record.getMessage()
        if message.startswith("[i1] serve "):
            out.append(dict(part.split("=", 1) for part in message.split()[2:]))
    return out


def _set_mode(monkeypatch, value):
    monkeypatch.setitem(ts._cfg, "trade_i1_mode", value)


@pytest.fixture()
def gates_on(monkeypatch):
    """Full v0.4: the no-card gate misses served (`trade_gate_miss_mode` 1)."""
    monkeypatch.setitem(ts._cfg, "trade_gate_miss_mode", 1.0)


def _now_iso(seconds_ago):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


# ── I-1: moved assets ────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["generate", "status"])
def test_moved_players_and_picks_are_never_served(live, path, caplog):
    client, _, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    job = _complete_job_with_cards()
    body = _via_generate(client) if path == "generate" else _via_status(client, job["job_id"])
    assert body["job_id"] == job["job_id"]
    assert body["status"] == "complete" and body["error"] is None
    assert "wait_reason" not in body
    assert {c["trade_id"] for c in body["cards"]} == SERVABLE
    line = _serve_lines(caplog)[-1]                     # C-a: one line per serve
    assert {k: line[k] for k in ("league", "mode", "status", "outcome", "cards", "kept",
                                 "dropped_give", "dropped_receive")} == {
        "league": LEAGUE, "mode": "strict", "status": "unknown", "outcome": "served",
        "cards": "6", "kept": "2", "dropped_give": "2", "dropped_receive": "2"}


def test_generic_picks_are_exempt_from_the_ownership_check(live, caplog):
    """Generic ladder picks are universal pool assets, never on a roster: a
    card carrying them passes I-1 unchanged, and the exemption is counted."""
    caplog.set_level(logging.INFO, logger="trade_finder")
    job = _complete_job_with_cards()
    generic = _card("generic", ["g2", "generic_pick_1_early"], ["r2", "generic_pick_2_mid"])
    generic_but_moved = _card("generic-moved", ["g1", "generic_pick_1_late"], ["r2"])
    out = server._trade_job_public_view(dict(job, cards=[generic, generic_but_moved]))
    assert out["cards"] == [generic]
    line = _serve_lines(caplog)[-1]
    assert (line["kept"], line["dropped_give"], line["unchecked_generic"]) == ("1", "1", "2")


def test_a_pick_with_no_owner_row_is_an_unknown_owner(live, caplog):
    """C-d: a pick asset absent from the stored picks is lenient and logged; one
    present with another owner is moved (the PK_GONE_* cards above)."""
    caplog.set_level(logging.INFO, logger="trade_finder")
    job = _complete_job_with_cards()
    unknown = _card("unknown-pick", [f"{LEAGUE}_2029_1_1"], ["r2", f"{LEAGUE}_2029_1_2"])
    out = server._trade_job_public_view(dict(job, cards=[unknown]))
    assert out["cards"] == [unknown]
    assert _serve_lines(caplog)[-1]["unchecked_pick_owner"] == "2"


# ── the check itself: missing rows and errors (strict vs lenient) ────────────

@pytest.mark.parametrize("path", ["generate", "status"])
def test_no_stored_rosters_serves_no_cards(live, gates_on, path, caplog):
    """Ruling 30: status `missing` is strict."""
    client, engine, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    with engine.begin() as conn:      # before the stamp, so /generate is still a cache hit
        conn.execute(delete(league_members_table))
    job = _complete_job_with_cards()
    body = _via_generate(client) if path == "generate" else _via_status(client, job["job_id"])
    assert (body["cards"], body["status"], body["error"]) == ([], "error", "roster_check_unavailable")
    line = _serve_lines(caplog)[-1]
    assert (line["status"], line["outcome"], line["kept"]) == (
        "missing", "roster_check_unavailable", "0")


@pytest.mark.parametrize("path", ["generate", "status"])
def test_check_error_serves_no_cards(live, gates_on, path):
    client, _, _ = live
    job = _complete_job_with_cards()
    with patch.object(roster_snapshot, "roster_snapshot",
                      MagicMock(side_effect=RuntimeError("db unavailable"))):
        body = _via_generate(client) if path == "generate" else _via_status(client, job["job_id"])
    assert (body["cards"], body["status"], body["error"]) == ([], "error", "roster_check_unavailable")


def test_a_disposition_failure_is_not_reported_as_a_roster_check_error(live):
    """The pre-existing projection swallows its errors into an empty deck; the
    I-1 failure must stay distinct from that."""
    client, _, _ = live
    job = _complete_job_with_cards()
    with patch.object(server, "load_trade_interest_history",
                      MagicMock(side_effect=RuntimeError("history unavailable"))):
        body = _via_status(client, job["job_id"])
    assert body["cards"] == [] and body["status"] == "complete" and body["error"] is None


# ── C-c: trade_i1_mode ───────────────────────────────────────────────────────

def test_mode_lenient_checks_and_logs_but_serves_every_card(live, monkeypatch, caplog):
    client, engine, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    _set_mode(monkeypatch, 1.0)
    job = _complete_job_with_cards()
    body = _via_status(client, job["job_id"])
    assert {c["trade_id"] for c in body["cards"]} == set(CARDS)
    line = _serve_lines(caplog)[-1]
    assert (line["mode"], line["kept"], line["dropped_give"], line["dropped_receive"]) == (
        "lenient", "6", "2", "2")
    with engine.begin() as conn:                      # missing rows: served, logged
        conn.execute(delete(league_members_table))
    body = _via_status(client, job["job_id"])
    assert len(body["cards"]) == len(CARDS) and body["status"] == "complete"
    assert _serve_lines(caplog)[-1]["outcome"] == "roster_check_unavailable"
    with patch.object(roster_snapshot, "roster_snapshot",
                      MagicMock(side_effect=RuntimeError("db unavailable"))):
        body = _via_status(client, job["job_id"])
    assert len(body["cards"]) == len(CARDS) and body["error"] is None


def test_mode_off_is_the_pre_s0_path(live, monkeypatch, caplog):
    client, _, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    _set_mode(monkeypatch, 0.0)
    job = _complete_job_with_cards()
    reads = MagicMock(side_effect=AssertionError("mode 0 reads no roster rows"))
    with patch.object(roster_snapshot, "roster_snapshot", reads), \
         patch.object(roster_snapshot, "snapshot_ids", reads):
        generated, polled = _via_generate(client), _via_status(client, job["job_id"])
    for body in (generated, polled):
        assert {c["trade_id"] for c in body["cards"]} == set(CARDS)
    assert reads.call_count == 0 and _serve_lines(caplog) == []


@pytest.mark.parametrize("value", [float("nan"), 7.0, -1.0, "strict please"])
def test_mode_reads_strict_for_anything_unexpected(live, monkeypatch, value):
    _set_mode(monkeypatch, value)
    assert server._trade_i1_mode() == 2


def test_mode_is_read_per_request(live, monkeypatch):
    client, _, _ = live
    job = _complete_job_with_cards()
    _set_mode(monkeypatch, 1.0)
    assert len(_via_status(client, job["job_id"])["cards"]) == len(CARDS)
    _set_mode(monkeypatch, 2.0)
    assert {c["trade_id"] for c in _via_status(client, job["job_id"])["cards"]} == SERVABLE


# ── §3b: the Sleeper withhold ────────────────────────────────────────────────

def _roster_state(engine, *, status, refreshed_ago, error=None):
    with engine.begin() as conn:
        conn.execute(delete(league_roster_state_table))
        if status is not None:
            conn.execute(insert(league_roster_state_table).values(
                league_id=LEAGUE, status=status, last_error_code=error, updated_at=_now_iso(0),
                refreshed_at=None if refreshed_ago is None else _now_iso(refreshed_ago)))


def _members_updated(engine, seconds_ago):
    with engine.begin() as conn:
        conn.execute(update(league_members_table).values(updated_at=_now_iso(seconds_ago)))


@pytest.mark.parametrize("status, refreshed_ago, members_ago, error, withheld", [
    ("stale", 600, 10, None, True),              # past the bound, last attempt failed
    ("stale", 100, 10, None, False),             # within the bound: last good rows serve
    ("stale", None, 600, None, True),            # NULL refreshed_at: age from the rows
    ("stale", None, 100, None, False),
    ("fresh", 600, 600, None, False),            # Q1: fresh at any age serves
    (None, None, 600, None, False),              # no state row: unknown, serves
    ("stale", 600, 600, "write_failed", False),  # C-e: a failed session write reads unknown
])
@pytest.mark.parametrize("path", ["generate", "status"])
def test_withhold_by_state_and_age(live, gates_on, caplog, path, status, refreshed_ago,
                                   members_ago, error, withheld):
    client, engine, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    job = _complete_job_with_cards()
    _roster_state(engine, status=status, refreshed_ago=refreshed_ago, error=error)
    _members_updated(engine, members_ago)
    body = _via_generate(client) if path == "generate" else _via_status(client, job["job_id"])
    if withheld:
        assert (body["cards"], body["status"], body["error"], body["wait_reason"]) == (
            [], "running", None, "roster_check")
        assert _serve_lines(caplog)[-1]["outcome"] == "roster_gate_miss"
    else:
        assert {c["trade_id"] for c in body["cards"]} == SERVABLE
        assert body["status"] == "complete" and "wait_reason" not in body


def test_a_linked_platform_never_withholds(live, caplog):
    """Ruling 29: ESPN/MFL/Fleaflicker stale rows serve with I-1, logged."""
    client, engine, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    job = _complete_job_with_cards()
    with engine.begin() as conn:
        conn.execute(insert(leagues_table).values(sleeper_league_id=LEAGUE, user_id=UID,
                                                  platform="espn"))
    _members_updated(engine, 200_000)               # past the 24 h import bound
    body = _via_status(client, job["job_id"])
    assert {c["trade_id"] for c in body["cards"]} == SERVABLE and "wait_reason" not in body
    assert _serve_lines(caplog)[-1]["status"] == "stale"


def test_lenient_mode_never_withholds(live, monkeypatch):
    client, engine, _ = live
    _set_mode(monkeypatch, 1.0)
    job = _complete_job_with_cards()
    _roster_state(engine, status="stale", refreshed_ago=600)
    body = _via_status(client, job["job_id"])
    assert len(body["cards"]) == len(CARDS) and "wait_reason" not in body


def test_withhold_is_rechecked_on_every_poll(live, gates_on):
    """Recovery: the floor's next success sets `fresh`, and the next poll serves."""
    client, engine, _ = live
    job = _complete_job_with_cards()
    _roster_state(engine, status="stale", refreshed_ago=600)
    assert _via_status(client, job["job_id"])["wait_reason"] == "roster_check"
    _roster_state(engine, status="fresh", refreshed_ago=5)
    body = _via_status(client, job["job_id"])
    assert {c["trade_id"] for c in body["cards"]} == SERVABLE and "wait_reason" not in body


def test_paged_withhold_holds_the_cursor(live, gates_on):
    client, engine, _ = live
    job = _complete_job_with_cards()
    _roster_state(engine, status="stale", refreshed_ago=600)
    resp = client.get(f"/api/trades/status?job_id={job['job_id']}&cursor=0",
                      headers={"X-Session-Token": TOKEN})
    body = resp.get_json()
    assert (body["cards"], body["cursor"], body["total_ready"], body["wait_reason"]) == (
        [], 0, 0, "roster_check")
    _roster_state(engine, status="fresh", refreshed_ago=5)
    resp = client.get(f"/api/trades/status?job_id={job['job_id']}&cursor=0",
                      headers={"X-Session-Token": TOKEN})
    body = resp.get_json()
    assert {c["trade_id"] for c in body["cards"]} == SERVABLE
    assert body["cursor"] == len(CARDS) and "wait_reason" not in body


# ── co-owners ────────────────────────────────────────────────────────────────

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


# ── trade_gate_miss_mode 0 (the default): no-card gate misses held ───────────
# Until 1.22.0 is distributed, older binaries show either gate miss as
# "Search failed" (release-lead's #363 QA), so the default holds both.

def test_held_no_rows_serve_every_card_unchecked(live, caplog):
    client, engine, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    with engine.begin() as conn:
        conn.execute(delete(league_members_table))
    job = _complete_job_with_cards()
    body = _via_status(client, job["job_id"])
    assert {c["trade_id"] for c in body["cards"]} == set(CARDS)
    assert (body["status"], body["error"]) == ("complete", None) and "wait_reason" not in body
    line = _serve_lines(caplog)[-1]
    assert (line["outcome"], line["kept"]) == ("roster_check_unavailable_held", "6")


@pytest.mark.parametrize("path", ["generate", "status"])
def test_held_check_error_serves_unchecked_cards_with_no_error(live, path, caplog):
    client, _, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    job = _complete_job_with_cards()
    with patch.object(roster_snapshot, "roster_snapshot",
                      MagicMock(side_effect=RuntimeError("db unavailable"))):
        body = _via_generate(client) if path == "generate" else _via_status(client, job["job_id"])
    assert {c["trade_id"] for c in body["cards"]} == set(CARDS)
    assert (body["status"], body["error"]) == ("complete", None)
    assert any("served unchecked" in r.getMessage() and r.levelno == logging.WARNING
               for r in caplog.records)


@pytest.mark.parametrize("path", ["generate", "status"])
def test_held_withhold_serves_filtered_cards_and_still_kicks(live, path, caplog):
    client, engine, _ = live
    caplog.set_level(logging.INFO, logger="trade_finder")
    job = _complete_job_with_cards()
    _roster_state(engine, status="stale", refreshed_ago=600)
    with patch.object(server._roster_refresh, "maybe_refresh_async",
                      MagicMock(return_value=False)) as kick:
        body = _via_generate(client) if path == "generate" else _via_status(client, job["job_id"])
    assert {c["trade_id"] for c in body["cards"]} == SERVABLE      # I-1 still filters
    assert body["status"] == "complete" and "wait_reason" not in body
    assert _serve_lines(caplog)[-1]["outcome"] == "roster_gate_miss_held"
    kick.assert_called_once_with(LEAGUE, max_age_s=300.0)            # P41 still fires


@pytest.mark.parametrize("value, on", [(1.0, True), (0.0, False), (float("nan"), False),
                                       (2.0, False), ("yes", False)])
def test_gate_mode_reads_0_unless_exactly_1(live, monkeypatch, value, on):
    monkeypatch.setitem(ts._cfg, "trade_gate_miss_mode", value)
    assert server._trade_gate_miss_on() is on


def test_lenient_i1_never_serves_a_gate_miss_even_with_gates_on(live, gates_on, monkeypatch):
    client, engine, _ = live
    _set_mode(monkeypatch, 1.0)
    job = _complete_job_with_cards()
    _roster_state(engine, status="stale", refreshed_ago=600)
    body = _via_status(client, job["job_id"])
    assert len(body["cards"]) == len(CARDS) and "wait_reason" not in body
    with engine.begin() as conn:
        conn.execute(delete(league_members_table))
    body = _via_status(client, job["job_id"])
    assert len(body["cards"]) == len(CARDS) and body["error"] is None


# ── admin gate-miss test hook (TestFlight A10) ───────────────────────────────

HOOK = "/api/admin/trades/gate-miss-test"


@pytest.fixture()
def hook(live, monkeypatch):
    client, _, _ = live
    monkeypatch.setattr(server, "_CRON_SECRET", "s0-test-secret")
    with server._gate_miss_tests_lock:
        server._gate_miss_tests.clear()
    try:
        yield client
    finally:
        with server._gate_miss_tests_lock:
            server._gate_miss_tests.clear()


def _admin(client, method, body, secret="s0-test-secret"):
    headers = {"X-Cron-Secret": secret} if secret else {}
    return client.open(HOOK, method=method, json=body, headers=headers)


@pytest.mark.parametrize("kind, expected", [
    ("withhold", {"status": "running", "error": None, "wait_reason": "roster_check"}),
    ("check_error", {"status": "error", "error": "roster_check_unavailable"}),
])
def test_the_hook_forces_its_gate_miss_on_the_target_league_only(live, hook, kind, expected):
    client = hook
    job = _complete_job_with_cards()                  # trade_gate_miss_mode stays 0
    assert _admin(client, "POST", {"league_id": LEAGUE, "kind": kind, "ttl_s": 60}).status_code == 200
    body = _via_status(client, job["job_id"])
    assert body["cards"] == [] and {k: body.get(k) for k in expected} == expected
    other = dict(job, key=(UID, "league_other", "1qb_ppr"))
    assert server._trade_job_public_view(other)["cards"], "another league is untouched"


def test_the_hook_expires_and_clears(live, hook):
    client = hook
    job = _complete_job_with_cards()
    assert _admin(client, "POST", {"league_id": LEAGUE, "kind": "withhold",
                                   "ttl_s": 0.05}).status_code == 200
    time.sleep(0.1)
    assert {c["trade_id"] for c in _via_status(client, job["job_id"])["cards"]} == SERVABLE
    assert LEAGUE not in server._gate_miss_tests
    _admin(client, "POST", {"league_id": LEAGUE, "kind": "check_error", "ttl_s": 900})
    resp = _admin(client, "DELETE", {"league_id": LEAGUE})
    assert resp.status_code == 200 and resp.get_json()["cleared"] is True
    assert {c["trade_id"] for c in _via_status(client, job["job_id"])["cards"]} == SERVABLE


@pytest.mark.parametrize("method, body", [
    ("POST", {"league_id": LEAGUE, "kind": "withhold", "ttl_s": 60}),
    ("DELETE", {"league_id": LEAGUE}),
])
def test_the_hook_requires_the_admin_secret(live, hook, method, body):
    client = hook
    assert _admin(client, method, body, secret=None).status_code == 401
    assert _admin(client, method, body, secret="wrong").status_code == 401
    assert LEAGUE not in server._gate_miss_tests


@pytest.mark.parametrize("body, error", [
    ({"league_id": LEAGUE, "kind": "withhold", "ttl_s": 901}, "invalid_ttl_s"),
    ({"league_id": LEAGUE, "kind": "withhold", "ttl_s": 0}, "invalid_ttl_s"),
    ({"league_id": LEAGUE, "kind": "withhold", "ttl_s": True}, "invalid_ttl_s"),
    ({"league_id": LEAGUE, "kind": "withhold"}, "invalid_ttl_s"),
    ({"league_id": LEAGUE, "kind": "updating", "ttl_s": 60}, "invalid_kind"),
    ({"kind": "withhold", "ttl_s": 60}, "invalid_league_id"),
])
def test_the_hook_refuses_bad_input(live, hook, body, error):
    resp = _admin(hook, "POST", body)
    assert resp.status_code == 400 and resp.get_json()["error"] == error
    assert server._gate_miss_tests == {}
