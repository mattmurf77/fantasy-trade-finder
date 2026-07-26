"""F10 — Deck Replenishment Ritual (flag deck.replenishment).

docs/plans/tiktok-discovery/prds/F10-deck-replenishment.md. Covers:

  • Flag OFF: daily-tick produces no replenish work, no pushes, no marker
    rows, and the tick response payload is byte-identical (no `replenish`
    key).
  • Flag ON: one pre-generated deck + one push per ACTIVE user-league per
    ISO week; idempotent on a repeat tick in the same week (marker gate);
    inactive (>30d) user-leagues are skipped entirely.
  • Push behavior: names concrete inventory ("N fresh trades…"), reflects
    the expired-card count only when true, is skipped for zero-card decks,
    and honors the notification-preference surface — a reengagement opt-out
    (explicit, or via the `notif.reengagement_default_off` policy) still
    gets the deck but never the push.
  • Weekly gate: days before the configured `replenish_weekday` are gated;
    the rest of the week self-heals a missed cron run.
  • Real generation path: _replenish_deck_for runs the existing job
    machinery synchronously against a live session, stamps the job's
    `source="replenish"` marker, and (with deck.signal_v2 on) freezes
    `deck_source` into the F1 impression features.

Harness: test_notif_teardown.py's isolated in-memory SQLite + patched flag
helpers for the cron tests; test_deck_signal_v2.py's session/job harness for
the real-generation test.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.feature_flags as feature_flags
import backend.server as server
from backend.database import deck_replenish_log_table, deck_impressions_table, metadata
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

UID    = "313560442465169408"
LEAGUE = "league_repl"
OPP    = "user_opp_repl"
TOKEN  = "sess-replenish-tok"


def _iso_week(now=None) -> str:
    now = now or datetime.now(timezone.utc)
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


def _insert_decision(conn, user_id, league_id, age_days=1):
    created = (datetime.now(timezone.utc).replace(tzinfo=None)
               - timedelta(days=age_days)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
        "VALUES (:uid, :lid, :give, :recv, 'pass', :created)"
    ), {"uid": user_id, "lid": league_id,
        "give": json.dumps(["g1"]), "recv": json.dumps(["r1"]),
        "created": created})


def _marker_rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(deck_replenish_log_table)).fetchall()


def _replenish(on: bool):
    """Patch the F10 flag helper directly — independent of features.json."""
    return patch.object(server, "_deck_replenishment_enabled", lambda: on)


def _weekday_cfg(value: float):
    """Patch _deck_cfg for replenish_weekday only; other keys keep defaults."""
    real = server._deck_cfg
    return patch.object(
        server, "_deck_cfg",
        lambda key, default: value if key == "replenish_weekday" else real(key, default),
    )


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    flags_on: set = set()
    flag_fn = lambda k: k in flags_on   # noqa: E731
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", flag_fn), \
         patch.object(feature_flags, "is_enabled", flag_fn), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "load_all_signed_up_users",
                      MagicMock(return_value=[])):
        yield c, engine, flags_on


def _tick(c):
    r = c.post("/api/cron/daily-tick", headers={"X-Cron-Secret": "x"})
    assert r.status_code == 200
    return r.get_json()


# ---------------------------------------------------------------------------
# Flag OFF — byte-identical daily-tick
# ---------------------------------------------------------------------------

def test_flag_off_no_replenish_work_no_push_no_payload_change(client):
    c, engine, _ = client
    with engine.begin() as conn:
        _insert_decision(conn, UID, LEAGUE)

    with _replenish(False), \
         patch.object(server, "_replenish_deck_for", MagicMock()) as gen, \
         patch.object(server, "_send_typed_push", MagicMock()) as push:
        body = _tick(c)

    assert "replenish" not in body           # response payload unchanged
    assert body == {"ok": True, "winback_matches": 0, "winback_dormant": 0,
                    "finish_ranking": 0, "season_start": 0}
    gen.assert_not_called()
    push.assert_not_called()
    assert _marker_rows(engine) == []


# ---------------------------------------------------------------------------
# Flag ON — one deck + one push per active user-league per week
# ---------------------------------------------------------------------------

def test_flag_on_one_deck_one_push_per_active_user_league(client):
    c, engine, _ = client
    with engine.begin() as conn:
        _insert_decision(conn, UID, LEAGUE)

    with _replenish(True), _weekday_cfg(0), \
         patch.object(server, "_replenish_deck_for",
                      MagicMock(return_value=(5, 0))) as gen, \
         patch.object(server, "_send_typed_push", MagicMock()) as push:
        body = _tick(c)

    gen.assert_called_once_with(UID, LEAGUE)
    push.assert_called_once()
    args, kwargs = push.call_args
    assert args == (UID, "deck_replenished")
    assert kwargs["title"] == "Your new deck is ready"
    assert kwargs["body"] == "5 fresh trades for your league."
    assert kwargs["data"] == {"league_id": LEAGUE}
    assert kwargs["dedup_key"] == f"{LEAGUE}:{_iso_week()}"

    rows = _marker_rows(engine)
    assert len(rows) == 1
    assert (rows[0].user_id, rows[0].league_id) == (UID, LEAGUE)
    assert rows[0].iso_week == _iso_week()
    assert (rows[0].deck_size, rows[0].expired_count) == (5, 0)

    assert body["replenish"] == {"eligible": 1, "generated": 1, "pushed": 1,
                                 "skipped_done": 0, "errors": 0}


def test_repeat_tick_same_week_is_idempotent(client):
    c, engine, _ = client
    with engine.begin() as conn:
        _insert_decision(conn, UID, LEAGUE)

    with _replenish(True), _weekday_cfg(0), \
         patch.object(server, "_replenish_deck_for",
                      MagicMock(return_value=(5, 0))) as gen, \
         patch.object(server, "_send_typed_push", MagicMock()) as push:
        _tick(c)
        body2 = _tick(c)

    gen.assert_called_once()                 # no regeneration on rerun
    push.assert_called_once()                # hard 1/week/league cap
    assert len(_marker_rows(engine)) == 1
    assert body2["replenish"]["skipped_done"] == 1
    assert body2["replenish"]["generated"] == 0
    assert body2["replenish"]["pushed"] == 0


def test_inactive_user_leagues_are_skipped(client):
    c, engine, _ = client
    with engine.begin() as conn:
        _insert_decision(conn, UID, LEAGUE, age_days=40)   # outside 30d window

    with _replenish(True), _weekday_cfg(0), \
         patch.object(server, "_replenish_deck_for", MagicMock()) as gen, \
         patch.object(server, "_send_typed_push", MagicMock()) as push:
        body = _tick(c)

    gen.assert_not_called()
    push.assert_not_called()
    assert body["replenish"]["eligible"] == 0
    assert _marker_rows(engine) == []


# ---------------------------------------------------------------------------
# Weekly gate
# ---------------------------------------------------------------------------

def test_weekday_gate_blocks_before_configured_day(client):
    tuesday   = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)   # weekday 1
    wednesday = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)   # weekday 2
    sunday    = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)   # weekday 6

    with _weekday_cfg(2):
        assert server._run_weekly_replenishment(tuesday).get("gated") is True
        # On/after the configured day the pass runs (empty DB → no pairs);
        # >= (not ==) means a missed Wednesday self-heals later in the week.
        assert "gated" not in server._run_weekly_replenishment(wednesday)
        assert "gated" not in server._run_weekly_replenishment(sunday)


# ---------------------------------------------------------------------------
# Push behavior — preference gating, expiry honesty, zero-card decks
# ---------------------------------------------------------------------------

def test_pref_opt_out_gets_deck_but_no_push(client):
    """Reengagement bucket off ⇒ the deck is still pre-generated (marker
    written) but _send_typed_push's bucket gate drops the push."""
    c, engine, _ = client
    with engine.begin() as conn:
        _insert_decision(conn, UID, LEAGUE)
    db_module.upsert_notification_prefs(UID, reengagement=0,
                                        quiet_hours_enabled=0)

    with _replenish(True), _weekday_cfg(0), \
         patch.object(server, "_replenish_deck_for",
                      MagicMock(return_value=(5, 0))), \
         patch.object(server, "load_device_tokens_for_users",
                      MagicMock(return_value=[{"device_token":
                                               "ExponentPushToken[x1]"}])), \
         patch.object(server, "_send_expo_push", MagicMock()) as expo, \
         patch.object(server, "queue_notification", MagicMock()) as q:
        _tick(c)

    assert len(_marker_rows(engine)) == 1    # deck happened
    expo.assert_not_called()                 # push did not
    q.assert_not_called()


def test_reengagement_default_off_policy_gates_push(client):
    """No stored pref + `notif.reengagement_default_off` (the shipping
    default) ⇒ the deck_replenished push is dropped by the bucket gate."""
    c, engine, flags_on = client
    flags_on.add("notif.reengagement_default_off")
    with engine.begin() as conn:
        _insert_decision(conn, UID, LEAGUE)

    with _replenish(True), _weekday_cfg(0), \
         patch.object(server, "_replenish_deck_for",
                      MagicMock(return_value=(5, 0))), \
         patch.object(server, "load_device_tokens_for_users",
                      MagicMock(return_value=[{"device_token":
                                               "ExponentPushToken[x1]"}])), \
         patch.object(server, "_send_expo_push", MagicMock()) as expo, \
         patch.object(server, "queue_notification", MagicMock()) as q:
        _tick(c)

    assert len(_marker_rows(engine)) == 1
    expo.assert_not_called()
    q.assert_not_called()


def test_expired_count_reflected_in_copy_only_when_true(client):
    c, engine, _ = client
    with engine.begin() as conn:
        _insert_decision(conn, UID, LEAGUE)

    with _replenish(True), _weekday_cfg(0), \
         patch.object(server, "_replenish_deck_for",
                      MagicMock(return_value=(11, 4))), \
         patch.object(server, "_send_typed_push", MagicMock()) as push:
        _tick(c)

    body = push.call_args.kwargs["body"]
    assert body == "11 fresh trades for your league. 4 expired — values moved."


def test_zero_card_deck_writes_marker_but_never_pushes(client):
    c, engine, _ = client
    with engine.begin() as conn:
        _insert_decision(conn, UID, LEAGUE)

    with _replenish(True), _weekday_cfg(0), \
         patch.object(server, "_replenish_deck_for",
                      MagicMock(return_value=(0, 0))), \
         patch.object(server, "_send_typed_push", MagicMock()) as push:
        body = _tick(c)

    push.assert_not_called()                 # no fake inventory
    assert len(_marker_rows(engine)) == 1    # still idempotent for the week
    assert body["replenish"]["pushed"] == 0


# ---------------------------------------------------------------------------
# Real generation path — live session, existing job machinery, source marker
# ---------------------------------------------------------------------------

@pytest.fixture()
def live_session(client):
    """A league-backed session registered in server module state, seeded so
    the likes-you path guarantees ≥1 generated card (same construction as
    test_deck_signal_v2's harness)."""
    c, engine, flags_on = client
    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service   = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(
        league_id=LEAGUE, name="Replenish League", platform="sleeper",
        members=[
            LeagueMember(user_id=UID, username="me",  roster=["g1", "g2"], elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp", roster=["r1", "r2"], elo_ratings={}),
        ],
    )
    trade_svc.add_league(league)
    sess = {
        "user_id":       UID,
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
    with engine.begin() as conn:
        # OPP liked the mirror trade → likes-you synthesizes ≥1 card.
        conn.execute(text(
            "INSERT INTO trade_decisions "
            "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
            "VALUES (:uid, :lid, :give, :recv, 'like', :created)"
        ), {"uid": OPP, "lid": LEAGUE,
            "give": json.dumps(["r1"]), "recv": json.dumps(["g1"]),
            "created": datetime.now(timezone.utc).isoformat()})

    with patch.object(server, "load_member_rankings", MagicMock(return_value={})), \
         patch.object(server, "load_league_preference", MagicMock(return_value=None)), \
         patch.object(server, "_likes_you_enabled", lambda: True), \
         patch.object(server, "_thompson_deck_enabled", lambda: False), \
         patch.object(server, "_deck_diversity_enabled", lambda: False), \
         patch.object(server, "create_notification", MagicMock()), \
         patch.object(server, "_send_typed_push", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield c, engine, flags_on
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._trade_jobs_lock:
                for jid in [j for j, job in server._trade_jobs.items()
                            if job.get("key") == (UID, LEAGUE, "1qb_ppr")]:
                    server._trade_jobs.pop(jid, None)
                server._trade_jobs_by_key.pop((UID, LEAGUE, "1qb_ppr"), None)


def test_replenish_runs_real_job_with_source_marker(live_session):
    c, engine, _ = live_session
    with patch.object(server, "_deck_signal_v2_enabled", lambda: True):
        result = server._replenish_deck_for(UID, LEAGUE)

    assert result is not None
    deck_size, expired = result
    assert deck_size >= 1
    assert expired == 0                      # no prior deck → nothing expired

    # The pre-generated deck sits in the normal job cache, marked replenish.
    with server._trade_jobs_lock:
        jid = server._trade_jobs_by_key.get((UID, LEAGUE, "1qb_ppr"))
        job = server._trade_jobs.get(jid)
    assert job is not None
    assert job["status"] == "complete"
    assert job.get("source") == "replenish"
    assert (time.monotonic() - job["finished_at"]) < server._PREGEN_TTL_SECONDS

    # F1 seam: deck_source frozen into the impression features (F5/analytics
    # can split pull vs replenish engagement).
    with engine.connect() as conn:
        rows = conn.execute(select(deck_impressions_table)).fetchall()
    assert rows
    for row in rows:
        assert json.loads(row.features_json).get("deck_source") == "replenish"


def test_replenish_reuses_fresh_cached_job_without_regenerating(live_session):
    c, engine, _ = live_session
    first = server._replenish_deck_for(UID, LEAGUE)
    assert first is not None

    # A second call inside the TTL must reuse the cached deck, not respawn.
    with patch.object(server, "_kickoff_trade_job", MagicMock()) as kick:
        second = server._replenish_deck_for(UID, LEAGUE)
    kick.assert_not_called()
    assert second is not None
    assert second[0] == first[0]
