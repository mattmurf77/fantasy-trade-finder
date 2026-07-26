"""F1 — Signal Foundation (flag deck.signal_v2), impression_id spine.

docs/plans/tiktok-discovery/prds/F1-signal-foundation.md. Covers:

  • Flag ON: a completed trade job writes one deck_impressions row per card
    in FINAL SERVED order, with non-null propensity + position, frozen
    features_json (incl. board-state-at-serve), and the published job
    snapshot carries impression_id per card.
  • Flag OFF: zero deck_impressions/deck_outcomes rows and the snapshot has
    no impression_id key (byte-identical payload).
  • Outcomes join by impression_id via the existing endpoints: swipe
    (like/pass + dwell/engagement fields), bad-trade flag (not_interested),
    /api/events side-channel (deck_card_viewed → viewed, swipe_undone →
    undo). Old clients (no impression_id) write nothing.
  • Undo APPENDS (original outcome retained); served-but-never-viewed cards
    have impressions and no viewed outcome.

Harness: same pattern as test_deck_ordering.py (isolated in-memory SQLite
patched into backend.database, flag helpers patched directly) plus the
test_swipe_reconstruct.py Flask-test-client style for the routes.
"""

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    deck_impressions_table,
    deck_outcomes_table,
    metadata,
    save_deck_outcome,
)
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeCard, TradeService


LEAGUE = "league_sig"
ME     = "user_me"
OPP    = "user_opp"
TOKEN  = "test-token-signal"
JOB_ID = "job-signal"


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _insert_decision(conn, user_id, give_ids, recv_ids, decision,
                     league_id=LEAGUE, age_days=1):
    created = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
        "VALUES (:uid, :lid, :give, :recv, :dec, :created)"
    ), {
        "uid": user_id, "lid": league_id,
        "give": json.dumps(give_ids), "recv": json.dumps(recv_ids),
        "dec": decision, "created": created,
    })


def _insert_member_ranking(conn, user_id, player_id, updated_at,
                           league_id=LEAGUE, scoring_format="1qb_ppr"):
    conn.execute(text(
        "INSERT INTO member_rankings "
        "(user_id, league_id, player_id, elo, updated_at, scoring_format) "
        "VALUES (:uid, :lid, :pid, 1500.0, :upd, :fmt)"
    ), {"uid": user_id, "lid": league_id, "pid": player_id,
        "upd": updated_at, "fmt": scoring_format})


def _signal(on: bool):
    """Patch the F1 flag helper directly — independent of features.json."""
    return patch.object(server, "_deck_signal_v2_enabled", lambda: on)


@pytest.fixture()
def harness(mem_engine):
    """Job + route harness: session and a running job registered in server
    module state, DB-independent side effects patched, Thompson ordering
    forced on (so propensity capture exercises the real draw path)."""
    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service   = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(
        league_id=LEAGUE, name="Signal League", platform="sleeper",
        members=[
            LeagueMember(user_id=ME,  username="me",  roster=["g1", "g2"], elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp", roster=["r1", "r2"], elo_ratings={}),
        ],
    )
    trade_svc.add_league(league)

    sess = {
        "user_id":       ME,
        "league":        league,
        "user_roster":   ["g1", "g2"],
        "players":       pool,
        "services":      {"1qb_ppr": service},
        "trade_svcs":    {"1qb_ppr": trade_svc},
        "service":       service,
        "trade_svc":     trade_svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }
    job = {
        "job_id": JOB_ID, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
        "started_at": time.monotonic(), "finished_at": None,
        "opponents_done": 0, "opponents_total": 1, "cards": [],
        "error": None, "fairness_threshold": 0.75,
        "outlook_value": None, "is_pinned": False,
    }

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(server, "load_member_rankings", MagicMock(return_value={})), \
         patch.object(server, "load_league_preference", MagicMock(return_value=None)), \
         patch.object(server, "_likes_you_enabled", lambda: True), \
         patch.object(server, "_thompson_deck_enabled", lambda: True), \
         patch.object(server, "_deck_diversity_enabled", lambda: False), \
         patch.object(server, "create_notification", MagicMock()), \
         patch.object(server, "_send_typed_push", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        with server._trade_jobs_lock:
            server._trade_jobs[JOB_ID] = job
        try:
            yield client, job, trade_svc, mem_engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._trade_jobs_lock:
                server._trade_jobs.pop(JOB_ID, None)
                server._trade_jobs_by_key.pop((ME, LEAGUE, "1qb_ppr"), None)


def _run_job(mem_engine, job):
    """Seed a likes-you source decision (guarantees ≥1 served card, same as
    test_deck_ordering) and run the worker to completion."""
    with mem_engine.begin() as conn:
        _insert_decision(conn, OPP, ["r1"], ["g1"], "like")
    server._run_trade_job(JOB_ID, TOKEN, LEAGUE, 0.75, [])
    assert job["status"] == "complete", job.get("error")
    return job["cards"]


def _impression_rows(mem_engine):
    with mem_engine.connect() as conn:
        return conn.execute(
            select(deck_impressions_table)
            .order_by(deck_impressions_table.c.card_index)
        ).fetchall()


def _outcome_rows(mem_engine):
    with mem_engine.connect() as conn:
        return conn.execute(
            select(deck_outcomes_table).order_by(deck_outcomes_table.c.id)
        ).fetchall()


def _post(client, path, body, token=TOKEN):
    headers = {"X-Device-Id": "dev_test"}
    if token:
        headers["X-Session-Token"] = token
    return client.post(path, data=json.dumps(body),
                       content_type="application/json", headers=headers)


# ---------------------------------------------------------------------------
# Impressions — flag ON
# ---------------------------------------------------------------------------

def test_flag_on_writes_impressions_in_served_order(harness):
    client, job, trade_svc, eng = harness
    with _signal(True):
        cards = _run_job(eng, job)

    rows = _impression_rows(eng)
    assert len(cards) >= 1
    assert len(rows) == len(cards)
    for pos, (row, card) in enumerate(zip(rows, cards)):
        # Non-null propensity + position, and the snapshot carries the id.
        assert row.card_index == pos
        assert row.propensity is not None
        assert 0.5 < row.propensity < 1.5          # Thompson multiplier bounds
        assert row.user_id == ME and row.league_id == LEAGUE
        assert row.deck_job_id == JOB_ID
        assert row.shape_bucket
        assert row.served_at
        assert card["impression_id"] == row.impression_id


def test_flag_on_features_frozen_at_serve(harness):
    client, job, trade_svc, eng = harness
    ts_old = "2026-07-20T00:00:00+00:00"
    ts_new = "2026-07-25T12:00:00+00:00"
    with eng.begin() as conn:
        _insert_member_ranking(conn, ME, "g1", ts_old)
        _insert_member_ranking(conn, ME, "g2", ts_new)
    with _signal(True):
        _run_job(eng, job)

    rows = _impression_rows(eng)
    assert rows
    for row in rows:
        f = json.loads(row.features_json)
        # Card attributes the generation path already computed
        for key in ("shape", "basis", "likes_you", "give_positions",
                    "receive_positions", "give_value_band", "involves_pick",
                    "partner_user_id", "surplus_margin"):
            assert key in f, f"missing feature {key!r}"
        assert f["shape"] == row.shape_bucket
        # Board-state-at-serve (PRD amendment 2026-07-26)
        assert f["ranked_player_count"] == 2
        assert f["last_board_update_at"] == ts_new
        assert f["user_value_basis"] == "personal"


def test_flag_on_cold_board_features(harness):
    client, job, trade_svc, eng = harness
    with _signal(True):
        _run_job(eng, job)
    f = json.loads(_impression_rows(eng)[0].features_json)
    assert f["ranked_player_count"] == 0
    assert f["last_board_update_at"] is None
    assert f["user_value_basis"] == "consensus"


def test_served_but_never_viewed_has_no_viewed_outcome(harness):
    client, job, trade_svc, eng = harness
    with _signal(True):
        _run_job(eng, job)
    assert len(_impression_rows(eng)) >= 1
    assert _outcome_rows(eng) == []       # impressions exist, zero outcomes


# ---------------------------------------------------------------------------
# Flag OFF — byte-identical behavior
# ---------------------------------------------------------------------------

def test_flag_off_writes_no_rows_and_no_payload_field(harness):
    client, job, trade_svc, eng = harness
    with _signal(False):
        cards = _run_job(eng, job)
    assert _impression_rows(eng) == []
    assert _outcome_rows(eng) == []
    assert all("impression_id" not in c for c in cards)


def test_flag_off_swipe_with_impression_id_writes_nothing(harness):
    client, job, trade_svc, eng = harness
    with _signal(False):
        cards = _run_job(eng, job)
        res = _post(client, "/api/trades/swipe", {
            "trade_id": cards[0]["trade_id"], "decision": "pass",
            "impression_id": "imp_stale_client", "dwell_ms": 1234,
        })
    assert res.status_code == 200
    assert _outcome_rows(eng) == []


# ---------------------------------------------------------------------------
# Outcomes — swipe / flag / events joins
# ---------------------------------------------------------------------------

def test_swipe_writes_outcome_joined_by_impression_id(harness):
    client, job, trade_svc, eng = harness
    with _signal(True):
        cards = _run_job(eng, job)
        iid = cards[0]["impression_id"]
        res = _post(client, "/api/trades/swipe", {
            "trade_id": cards[0]["trade_id"], "decision": "pass",
            "impression_id": iid, "dwell_ms": 4321,
            "detail_expanded": True, "calc_opened": False,
        })
    assert res.status_code == 200, res.get_data(as_text=True)
    rows = _outcome_rows(eng)
    assert len(rows) == 1
    row = rows[0]
    assert row.impression_id == iid
    assert row.action == "pass"
    assert row.dwell_ms == 4321
    assert row.detail_expanded == 1
    assert row.calc_opened == 0
    assert row.acted_at
    # Joins back to its impression
    imp = [r for r in _impression_rows(eng) if r.impression_id == iid]
    assert len(imp) == 1


def test_swipe_like_outcome(harness):
    client, job, trade_svc, eng = harness
    card = TradeCard(
        trade_id="manual1", league_id=LEAGUE, proposing_user_id=ME,
        target_user_id=OPP, target_username="opp",
        give_player_ids=["g1"], receive_player_ids=["r2"],
        mismatch_score=100.0, fairness_score=0.9, composite_score=0.8,
    )
    trade_svc._trade_cards[card.trade_id] = card
    iid = uuid.uuid4().hex
    with _signal(True):
        res = _post(client, "/api/trades/swipe", {
            "trade_id": "manual1", "decision": "like",
            "impression_id": iid, "dwell_ms": 900,
        })
    assert res.status_code == 200, res.get_data(as_text=True)
    rows = _outcome_rows(eng)
    assert [(r.impression_id, r.action) for r in rows] == [(iid, "like")]


def test_swipe_without_impression_id_writes_nothing(harness):
    client, job, trade_svc, eng = harness
    with _signal(True):
        cards = _run_job(eng, job)
        res = _post(client, "/api/trades/swipe", {
            "trade_id": cards[0]["trade_id"], "decision": "pass",
        })
    assert res.status_code == 200
    assert _outcome_rows(eng) == []       # old client → existing path exactly


def test_bad_trade_flag_writes_not_interested(harness):
    client, job, trade_svc, eng = harness
    iid = uuid.uuid4().hex
    with _signal(True):
        res = _post(client, "/api/trades/flag", {
            "give_player_ids": ["g1"], "receive_player_ids": ["r1"],
            "league_id": LEAGUE, "impression_id": iid,
        })
    assert res.status_code in (200, 201), res.get_data(as_text=True)
    rows = _outcome_rows(eng)
    assert [(r.impression_id, r.action) for r in rows] == [(iid, "not_interested")]


def test_events_viewed_and_undo_append(harness):
    client, job, trade_svc, eng = harness
    with _signal(True):
        cards = _run_job(eng, job)
        iid = cards[0]["impression_id"]
        # pass first (the original outcome) …
        _post(client, "/api/trades/swipe", {
            "trade_id": cards[0]["trade_id"], "decision": "pass",
            "impression_id": iid, "dwell_ms": 1000,
        })
        # … then the client's viewed + undo signals via /api/events
        res = _post(client, "/api/events", {"events": [
            {"event_type": "deck_card_viewed",
             "props": {"impression_id": iid, "dwell_ms": 700}},
            {"event_type": "swipe_undone",
             "props": {"impression_id": iid}},
        ]})
    assert res.status_code == 200
    rows = _outcome_rows(eng)
    assert [r.action for r in rows] == ["pass", "viewed", "undo"]
    # Append-only: the original pass row is retained, unmutated.
    assert rows[0].impression_id == iid and rows[0].dwell_ms == 1000
    assert rows[1].dwell_ms == 700
    assert all(r.impression_id == iid for r in rows)


def test_events_flag_off_ignores_impression_props(harness):
    client, job, trade_svc, eng = harness
    with _signal(False):
        res = _post(client, "/api/events", {"events": [
            {"event_type": "deck_card_viewed",
             "props": {"impression_id": "imp_x", "dwell_ms": 700}},
        ]})
    assert res.status_code == 200
    assert _outcome_rows(eng) == []


# ---------------------------------------------------------------------------
# save_deck_outcome — closed action enum
# ---------------------------------------------------------------------------

def test_outcome_action_enum(mem_engine):
    save_deck_outcome("imp_1", "propose")
    with pytest.raises(ValueError):
        save_deck_outcome("imp_1", "clicked")   # not a legal action
    rows = _outcome_rows(mem_engine)
    assert [(r.impression_id, r.action) for r in rows] == [("imp_1", "propose")]
