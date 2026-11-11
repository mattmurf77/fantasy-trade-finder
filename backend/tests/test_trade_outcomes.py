"""Offer-learnings WS2 Part A — outcomes of trades sent through the app.

Scope block: docs/plans/offer-learnings/scope-trade-outcomes.md

Covers, with no network (Sleeper's public `transactions/{leg}` payloads come
from `fixtures/sleeper/trade-outcomes/transactions_leg1.json` through the real
capture parser, the GraphQL send is a mock):

  * the send seam: a confirmed `POST /api/trades/propose` writes one 'sent'
    row with both roster ids and the assets as sent (flag on), and nothing at
    all with an identical response (flag off);
  * every transition the public data can show: sent -> accepted,
    sent -> completed_different_terms (with that trade's terms from the
    sender's side), completed_different_terms -> accepted; and the cases that
    must stay 'sent' (another pair of rosters, a three-team trade, a trade
    before the send, no trade at all);
  * idempotence: a re-sync and re-reconcile change nothing but checked_at; a
    repeated send of the same transaction id is one row and never resets an
    observed status;
  * the session-init seam (reconcile after the capture) and the daily-tick
    step (capture + reconcile, flag-gated, watch window).

Declined / withdrawn / expired are not tested because nothing writes them:
the app cannot observe them (scope block §0).
"""
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db
import backend.server as server
import backend.sleeper_trades_service as sts
import backend.trade_outcomes as to
from backend.database import metadata
from backend.tests import test_sleeper_write_route as propose_t
from backend.tests import test_session_init_sleeper_calls as si
from backend.tests.test_session_init_sleeper_calls import harness  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("no_real_network")

FIX = Path(__file__).resolve().parent / "fixtures/sleeper/trade-outcomes/transactions_leg1.json"
TXNS = json.loads(FIX.read_text())
BY_TX = {t["transaction_id"]: t for t in TXNS}

LEAGUE = "990000000000000001"
USER = "synthetic-sender"
OFFER_TX = "1300000000000000001"      # the sent offer; completes 2026-10-03
COUNTER_TX = "1300000000000000002"    # same two rosters, 2026-10-02
SENT = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


@pytest.fixture()
def engine(monkeypatch):
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    monkeypatch.setattr(db, "engine", eng)
    yield eng
    eng.dispose()


def _send(monkeypatch, tx=OFFER_TX, *, at=SENT, mine=1, theirs=2, league=LEAGUE):
    monkeypatch.setattr(to, "_now", lambda: at)
    return to.record_sent(user_id=USER, league_id=league, transaction_id=tx,
                          my_roster_id=mine, their_roster_id=theirs,
                          give_asset_ids=["100"], receive_asset_ids=["200"])


def _capture(*txids, league=LEAGUE):
    return db.record_sleeper_trades(
        sts.parse_trade_transactions([BY_TX[t] for t in txids], league))


def _rows():
    with db.engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(
            select(db.trade_offer_outcomes_table).order_by(db.trade_offer_outcomes_table.c.id))]


def _row(tx=OFFER_TX):
    return next(r for r in _rows() if r["provider_transaction_id"] == tx)


# ---------------------------------------------------------------------------
# Transitions, from the fixture payloads
# ---------------------------------------------------------------------------

def test_sent_offer_that_completes_is_accepted_at_sleepers_time(engine, monkeypatch):
    _send(monkeypatch)
    assert _row()["status"] == "sent"
    _capture(OFFER_TX)
    c = to.reconcile_league(LEAGUE, SENT + timedelta(days=3))
    r = _row()
    assert (r["status"], r["resolved_transaction_id"]) == ("accepted", OFFER_TX)
    assert r["status_at"] == "2026-10-03T12:00:00+00:00"       # Sleeper's, not the tick's
    assert r["observed_terms_json"] is None
    assert c == {"open": 1, "accepted": 1, "completed_different_terms": 0}


def test_different_trade_between_the_same_rosters_records_its_terms(engine, monkeypatch):
    _send(monkeypatch)
    _capture(COUNTER_TX)
    to.reconcile_league(LEAGUE)
    r = _row()
    assert (r["status"], r["resolved_transaction_id"]) == ("completed_different_terms", COUNTER_TX)
    assert r["status_at"] == "2026-10-02T12:00:00+00:00"
    assert json.loads(r["observed_terms_json"]) == {
        "give_player_ids": ["101"],
        "receive_player_ids": ["200", "201"],
        "give_picks": [{"season": "2028", "round": 1, "original_roster_id": 1}],
        "receive_picks": [{"season": "2027", "round": 2, "original_roster_id": 2}],
        "give_faab": 5,
        "receive_faab": 0,
    }


def test_original_completing_later_overrides_different_terms(engine, monkeypatch):
    _send(monkeypatch)
    _capture(COUNTER_TX)
    to.reconcile_league(LEAGUE)
    assert _row()["status"] == "completed_different_terms"
    _capture(OFFER_TX)
    to.reconcile_league(LEAGUE)
    r = _row()
    assert (r["status"], r["resolved_transaction_id"], r["observed_terms_json"]) == \
        ("accepted", OFFER_TX, None)


@pytest.mark.parametrize("txid,why", [
    ("1300000000000000003", "another pair of rosters"),
    ("1300000000000000004", "a three-team trade"),
    ("1300000000000000005", "the same rosters, before the send"),
    ("1300000000000000006", "a waiver (never captured)"),
    (None, "nothing captured at all"),
])
def test_unrelated_or_absent_trades_leave_the_offer_sent(engine, monkeypatch, txid, why):
    _send(monkeypatch)
    if txid:
        _capture(txid)
    now = SENT + timedelta(days=5)
    to.reconcile_league(LEAGUE, now)
    r = _row()
    assert (r["status"], r["resolved_transaction_id"], r["status_at"]) == ("sent", None, None), why
    assert r["checked_at"] == now.isoformat()


def test_resync_and_reconcile_are_idempotent_through_the_real_capture(engine, monkeypatch):
    """The whole leg-1 payload through `sync_league_trades` twice, reconciled
    twice: one row per trade, and the second pass changes only checked_at."""
    _send(monkeypatch)

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    def opener(request, timeout=15):
        body = TXNS if request.full_url.endswith("/transactions/1") else []
        return _Resp(json.dumps(body).encode())

    assert sts.sync_league_trades(LEAGUE, _opener=opener) == 5
    first = to.reconcile_league(LEAGUE, SENT + timedelta(days=4))
    after_first = _row()
    assert after_first["status"] == "accepted"       # the original wins over the counter
    assert sts.sync_league_trades(LEAGUE, _opener=opener) == 0
    second = to.reconcile_league(LEAGUE, SENT + timedelta(days=5))
    assert first["accepted"] == 1 and second == {"open": 0, "accepted": 0,
                                                 "completed_different_terms": 0}
    assert _rows() == [after_first]


def test_repeated_send_is_one_row_and_never_resets_an_observed_status(engine, monkeypatch):
    assert _send(monkeypatch) is True
    _capture(OFFER_TX)
    to.reconcile_league(LEAGUE)
    assert _send(monkeypatch, at=SENT + timedelta(days=9)) is False
    rows = _rows()
    assert len(rows) == 1
    assert (rows[0]["status"], rows[0]["sent_at"]) == ("accepted", SENT.isoformat())


def test_send_without_a_transaction_id_records_nothing(engine, monkeypatch):
    assert _send(monkeypatch, tx=None) is False
    assert _rows() == []


# ---------------------------------------------------------------------------
# The send seam: POST /api/trades/propose
# ---------------------------------------------------------------------------

def _propose_with(flags, client):
    with patch.object(server, "is_enabled", lambda k: k in flags):
        r, *_ = propose_t._propose(client, {"give_player_ids": ["100"],
                                            "receive_player_ids": ["200"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


@pytest.fixture()
def client(monkeypatch):
    yield from propose_t.client.__wrapped__(monkeypatch)


def test_confirmed_send_writes_the_sent_row(client):
    body = _propose_with({"trade.send_in_sleeper", "trade.outcome_tracking"}, client)
    rows = _rows()
    assert len(rows) == 1
    r = rows[0]
    assert (r["user_id"], r["league_id"], r["provider"], r["provider_transaction_id"]) == \
        (propose_t.USER, propose_t.LEAGUE, "sleeper", body["transaction_id"])
    assert (r["my_roster_id"], r["their_roster_id"]) == (1, 2)
    assert (json.loads(r["give_asset_ids"]), json.loads(r["receive_asset_ids"])) == (["100"], ["200"])
    assert r["status"] == "sent" and r["sent_at"] and r["proposal_event_id"]


def test_flag_off_send_is_identical_and_writes_nothing(client):
    off = _propose_with({"trade.send_in_sleeper"}, client)
    assert _rows() == []
    on = _propose_with({"trade.send_in_sleeper", "trade.outcome_tracking"}, client)
    assert off == on == {"status": "proposed", "transaction_id": "TX9"}


# ---------------------------------------------------------------------------
# The session-init seam (reconcile after the league's trade capture)
# ---------------------------------------------------------------------------

def _seed_for_session_init(monkeypatch):
    monkeypatch.setattr(to, "_now", lambda: datetime(2026, 9, 1, tzinfo=timezone.utc))
    to.record_sent(user_id=si.USER_ID, league_id=si.LEAGUE_ID,
                   transaction_id=si.CAPTURED_TRADE["transaction_id"],
                   my_roster_id=1, their_roster_id=2,
                   give_asset_ids=["p1"], receive_asset_ids=["p2"])
    db.record_sleeper_trades([dict(si.CAPTURED_TRADE)])


@pytest.mark.parametrize("flag_on,expected", [(True, "accepted"), (False, "sent")])
def test_session_init_reconciles_after_capture_only_when_on(harness, monkeypatch,  # noqa: F811
                                                           flag_on, expected):
    client, _calls = harness
    _seed_for_session_init(monkeypatch)
    real = server.is_enabled
    monkeypatch.setattr(server, "is_enabled",
                        lambda k: (flag_on if k == "trade.outcome_tracking" else real(k)))
    assert si._init(client, si.LEAGUE_ID).status_code == 200
    assert _row(si.CAPTURED_TRADE["transaction_id"])["status"] == expected


# ---------------------------------------------------------------------------
# The daily-tick step
# ---------------------------------------------------------------------------

def _tick_flags(monkeypatch, flags):
    monkeypatch.setattr(server, "is_enabled", lambda k: k in flags)
    sync = MagicMock(side_effect=lambda lid: _capture(OFFER_TX, league=lid))
    monkeypatch.setattr(sts, "sync_league_trades", sync)
    return sync


def test_daily_step_captures_and_reconciles(engine, monkeypatch):
    _send(monkeypatch)
    sync = _tick_flags(monkeypatch, {"trade.outcome_tracking", "market.trade_capture"})
    outcome, stats = server._daily_tick_trade_outcomes(SENT + timedelta(days=3))
    assert outcome == "ok"
    assert stats == {"leagues": 1, "errors": 0, "accepted": 1, "completed_different_terms": 0}
    sync.assert_called_once_with(LEAGUE)
    assert _row()["status"] == "accepted"


def test_daily_step_is_skipped_when_the_flag_is_off(engine, monkeypatch):
    _send(monkeypatch)
    sync = _tick_flags(monkeypatch, {"market.trade_capture"})
    assert server._daily_tick_trade_outcomes(SENT + timedelta(days=3)) == ("skipped", "flag off")
    sync.assert_not_called()
    r = _row()
    assert (r["status"], r["checked_at"]) == ("sent", None)


def test_daily_step_reconciles_without_capturing_when_capture_is_off(engine, monkeypatch):
    _send(monkeypatch)
    _capture(OFFER_TX)
    sync = _tick_flags(monkeypatch, {"trade.outcome_tracking"})
    outcome, stats = server._daily_tick_trade_outcomes(SENT + timedelta(days=3))
    sync.assert_not_called()
    assert (outcome, stats["accepted"], _row()["status"]) == ("ok", 1, "accepted")


def test_daily_step_leaves_offers_past_the_watch_window_to_session_init(engine, monkeypatch):
    _send(monkeypatch)
    sync = _tick_flags(monkeypatch, {"trade.outcome_tracking", "market.trade_capture"})
    late = SENT + timedelta(days=to.OUTCOME_WATCH_DAYS + 1)
    assert server._daily_tick_trade_outcomes(late) == \
        ("ok", {"leagues": 0, "errors": 0, "accepted": 0, "completed_different_terms": 0})
    sync.assert_not_called()


def test_one_failing_league_does_not_stop_the_tick(engine, monkeypatch):
    _send(monkeypatch, league="990000000000000002", tx="1300000000000000099")
    _send(monkeypatch)
    monkeypatch.setattr(server, "is_enabled",
                        lambda k: k in {"trade.outcome_tracking", "market.trade_capture"})

    def sync(lid):
        if lid == "990000000000000002":
            raise RuntimeError("synthetic 429")
        _capture(OFFER_TX, league=lid)

    monkeypatch.setattr(sts, "sync_league_trades", sync)
    _outcome, stats = server._daily_tick_trade_outcomes(SENT + timedelta(days=3))
    assert (stats["leagues"], stats["errors"], stats["accepted"]) == (2, 1, 1)
    assert _row()["status"] == "accepted"
