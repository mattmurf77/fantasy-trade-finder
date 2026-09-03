"""Market-data readiness (operator directive 2026-07-26; PRD #43 data
foundation). Covers the two additive plumbing pieces:

  1. Daily consensus value snapshots — the hourly-tick fallback guard
     writes today's player_value_history rows for BOTH scoring formats
     when missing, skips when present, and never blocks the push work;
     the dedicated /api/cron/value-snapshot route stays idempotent
     within a UTC day.
  2. Executed-trade capture — sleeper_trades_service parses Sleeper
     /league/<id>/transactions/<week> payloads (completed trades only,
     raw payload retained) and database.record_sleeper_trades is
     idempotent on transaction_id (re-sync creates no duplicates).

Harness: test_deck_replenishment.py's isolated in-memory SQLite +
patched server helpers.
"""

import io
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    SCORING_FORMATS,
    metadata,
    record_sleeper_trades,
    record_value_snapshots,
    sleeper_trades_table,
    value_snapshot_formats_for,
)
import backend.sleeper_trades_service as sleeper_trades_service
from backend.sleeper_trades_service import (
    parse_trade_transactions,
    sweep_weeks,
    sync_league_trades,
)

LEAGUE = "998877665544332211"

# ---------------------------------------------------------------------------
# Sleeper transactions fixture — one completed trade (players + pick + FAAB),
# one pending trade, one completed waiver. Only the first should be captured.
# ---------------------------------------------------------------------------

COMPLETED_TRADE = {
    "type": "trade",
    "status": "complete",
    "transaction_id": "1112223334445556677",
    "leg": 1,
    "status_updated": 1721952000000,   # 2024-07-26T00:00:00Z
    "roster_ids": [3, 5],
    "adds": {"4034": 3, "6786": 5},
    "drops": {"4034": 5, "6786": 3},
    "draft_picks": [{"season": "2027", "round": 1, "roster_id": 5,
                     "previous_owner_id": 3, "owner_id": 5}],
    "waiver_budget": [{"sender": 3, "receiver": 5, "amount": 12}],
    "consenter_ids": [3, 5],
}
PENDING_TRADE = {
    "type": "trade", "status": "in_progress",
    "transaction_id": "2223334445556667788",
    "leg": 1, "roster_ids": [1, 2],
    "adds": {"1234": 1}, "drops": {"1234": 2},
}
COMPLETED_WAIVER = {
    "type": "waiver", "status": "complete",
    "transaction_id": "3334445556667778899",
    "leg": 1, "roster_ids": [4], "adds": {"5555": 4},
}
WEEK1_PAYLOAD = [COMPLETED_TRADE, PENDING_TRADE, COMPLETED_WAIVER]


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _fake_opener(request, timeout=15):
    url = request.full_url
    payload = WEEK1_PAYLOAD if url.endswith("/transactions/1") else []
    return _FakeResponse(json.dumps(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "load_all_signed_up_users",
                      MagicMock(return_value=[])), \
         patch.object(server, "drain_due_queued_notifications",
                      MagicMock(return_value={})):
        yield c, engine


def _fake_pools():
    pools = {
        fmt: {"seed": {"p1": 1600.0, "p2": 1400.0}, "players": []}
        for fmt in SCORING_FORMATS
    }
    return (patch.object(server, "_ensure_universal_pools", lambda: None),
            patch.object(server, "g_universal_by_format", pools))


def _trade_rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(sleeper_trades_table)).fetchall()


def _snapshot_count(engine):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM player_value_history")).scalar()


# ---------------------------------------------------------------------------
# Trade capture — parsing
# ---------------------------------------------------------------------------

def test_parse_filters_to_completed_trades_and_normalizes():
    rows = parse_trade_transactions(WEEK1_PAYLOAD, LEAGUE)
    assert len(rows) == 1
    row = rows[0]
    assert row["transaction_id"] == "1112223334445556677"
    assert row["league_id"] == LEAGUE
    assert row["week"] == 1
    assert row["traded_at"].startswith("2024-07-26")
    assert json.loads(row["adds"]) == {"4034": 3, "6786": 5}
    assert json.loads(row["draft_picks"])[0]["season"] == "2027"
    assert json.loads(row["waiver_budget"])[0]["amount"] == 12
    # Full raw payload retained — a future model can re-derive anything.
    assert json.loads(row["raw"]) == COMPLETED_TRADE


def test_parse_tolerates_garbage_and_missing_fields():
    rows = parse_trade_transactions(
        [None, "junk", {}, {"type": "trade", "status": "complete"},  # no txid
         {"type": "trade", "status": "complete", "transaction_id": "42"}],
        LEAGUE,
    )
    assert [r["transaction_id"] for r in rows] == ["42"]
    assert rows[0]["week"] is None
    assert rows[0]["traded_at"] is None


# ---------------------------------------------------------------------------
# Trade capture — storage idempotency
# ---------------------------------------------------------------------------

def test_record_sleeper_trades_idempotent(client):
    _, engine = client
    rows = parse_trade_transactions(WEEK1_PAYLOAD, LEAGUE)
    assert record_sleeper_trades(rows) == 1
    assert record_sleeper_trades(rows) == 0          # re-sync → no duplicates
    assert len(_trade_rows(engine)) == 1


def test_sync_league_trades_end_to_end_and_resync(client):
    _, engine = client
    assert sync_league_trades(LEAGUE, _opener=_fake_opener) == 1
    assert sync_league_trades(LEAGUE, _opener=_fake_opener) == 0
    stored = _trade_rows(engine)
    assert len(stored) == 1
    assert stored[0].transaction_id == "1112223334445556677"
    assert json.loads(stored[0].raw)["status"] == "complete"


def test_sync_survives_per_week_fetch_failures(client):
    _, engine = client

    def _flaky_opener(request, timeout=15):
        if request.full_url.endswith("/transactions/2"):
            raise OSError("sleeper flake")
        return _fake_opener(request, timeout)

    # Week 2 blows up; week 1's trade is still captured.
    assert sync_league_trades(LEAGUE, _opener=_flaky_opener) == 1
    assert len(_trade_rows(engine)) == 1


# ---------------------------------------------------------------------------
# Trade capture — incremental sweep (18 legs only on the first pass)
#
# The 18-leg sweep used to run on EVERY session init, year-round: ~18 of the
# ~26 Sleeper calls one app open cost. Only the live leg (and the one before
# it, for a late-processed trade) can produce new rows once a league has been
# swept, so after the first backfill the sweep shrinks to <=2 legs — and to
# leg 1 alone in the offseason, where Sleeper books every trade.
# ---------------------------------------------------------------------------

def _counting_opener():
    """A `_fake_opener` that records every leg it was asked for."""
    seen: list[int] = []

    def opener(request, timeout=15):
        seen.append(int(request.full_url.rsplit("/", 1)[1]))
        return _fake_opener(request, timeout)

    return opener, seen


def test_current_nfl_week_window_and_offseason():
    start = sleeper_trades_service.SEASON_START
    assert sleeper_trades_service.current_nfl_week(start) == 1
    assert sleeper_trades_service.current_nfl_week(start + timedelta(days=6)) == 1
    assert sleeper_trades_service.current_nfl_week(start + timedelta(days=7)) == 2
    assert sleeper_trades_service.current_nfl_week(start + timedelta(weeks=17)) == 18
    # Offseason on both sides of the season → None, never leg 1.
    assert sleeper_trades_service.current_nfl_week(start - timedelta(days=1)) is None
    assert sleeper_trades_service.current_nfl_week(start + timedelta(weeks=18)) is None


def test_first_sync_backfills_all_18_legs(client):
    _, engine = client
    opener, seen = _counting_opener()
    assert sync_league_trades(LEAGUE, _opener=opener) == 1
    assert seen == list(range(1, 19))          # (a) empty league → full sweep
    assert len(_trade_rows(engine)) == 1


def test_second_sync_only_sweeps_live_legs(client, monkeypatch):
    _, _engine = client
    # Backfill first so the league has rows.
    sync_league_trades(LEAGUE, _opener=_fake_opener)

    monkeypatch.setattr(sleeper_trades_service, "current_nfl_week",
                        lambda today=None: 7)
    opener, seen = _counting_opener()
    assert sync_league_trades(LEAGUE, _opener=opener) == 0
    assert seen == [6, 7]                      # (b) live leg + the one before

    # Week 1 has no predecessor — never fetches leg 0.
    monkeypatch.setattr(sleeper_trades_service, "current_nfl_week",
                        lambda today=None: 1)
    opener, seen = _counting_opener()
    sync_league_trades(LEAGUE, _opener=opener)
    assert seen == [1]


def test_offseason_sync_sweeps_only_leg_1_after_backfill(client, monkeypatch):
    _, engine = client
    sync_league_trades(LEAGUE, _opener=_fake_opener)

    monkeypatch.setattr(sleeper_trades_service, "current_nfl_week",
                        lambda today=None: None)
    opener, seen = _counting_opener()
    assert sync_league_trades(LEAGUE, _opener=opener) == 0
    assert seen == [1]                         # (c) offseason → leg 1 only
    assert len(_trade_rows(engine)) == 1

    # But a league that has NEVER been swept still gets its backfill, even
    # in the offseason — that is the one pass that must not be skipped.
    opener, seen = _counting_opener()
    sync_league_trades("111122223333444455", _opener=opener)
    assert seen == list(range(1, 19))


def test_sweep_weeks_is_date_driven(client):
    _, _engine = client
    start = sleeper_trades_service.SEASON_START
    # No rows yet → backfill regardless of the date.
    assert sweep_weeks(LEAGUE, start + timedelta(weeks=4)) == list(range(1, 19))
    record_sleeper_trades(parse_trade_transactions(WEEK1_PAYLOAD, LEAGUE))
    assert sweep_weeks(LEAGUE, start + timedelta(weeks=4)) == [4, 5]
    assert sweep_weeks(LEAGUE, start - timedelta(days=30)) == [1]


# ---------------------------------------------------------------------------
# Daily value snapshot — dedicated cron route idempotency
# ---------------------------------------------------------------------------

def test_cron_value_snapshot_idempotent_same_day(client):
    c, engine = client
    p1, p2 = _fake_pools()
    with p1, p2:
        r1 = c.post("/api/cron/value-snapshot", headers={"X-Cron-Secret": "x"})
        r2 = c.post("/api/cron/value-snapshot", headers={"X-Cron-Secret": "x"})
    assert r1.status_code == 200 and r2.status_code == 200
    body = r1.get_json()
    for fmt in SCORING_FORMATS:
        assert body[fmt] == 2                     # 2 fake pool players
    # Re-run upserts, never duplicates: 2 players × N formats total.
    assert _snapshot_count(engine) == 2 * len(SCORING_FORMATS)


# ---------------------------------------------------------------------------
# Daily value snapshot — hourly-tick fallback guard
# ---------------------------------------------------------------------------

def test_hourly_tick_writes_missing_snapshot_for_both_formats(client):
    c, engine = client
    assert _snapshot_count(engine) == 0
    p1, p2 = _fake_pools()
    with p1, p2:
        r = c.post("/api/cron/hourly-tick", headers={"X-Cron-Secret": "x"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["value_snapshot"] == {fmt: 2 for fmt in SCORING_FORMATS}
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert value_snapshot_formats_for(today) == set(SCORING_FORMATS)


def test_hourly_tick_skips_when_snapshot_already_written(client):
    c, engine = client
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record_value_snapshots([
        {"player_id": "p1", "scoring_format": fmt, "consensus_elo": 1600.0,
         "consensus_value": 5000.0, "search_rank": 1, "adp": 1.0,
         "snapshot_date": today}
        for fmt in SCORING_FORMATS
    ])
    with patch.object(server, "_write_daily_value_snapshots",
                      MagicMock()) as writer:
        r = c.post("/api/cron/hourly-tick", headers={"X-Cron-Secret": "x"})
    assert r.status_code == 200
    writer.assert_not_called()
    assert "value_snapshot" not in r.get_json()


def test_hourly_tick_snapshot_failure_never_blocks_tick(client):
    c, _ = client
    with patch.object(server, "_write_daily_value_snapshots",
                      MagicMock(side_effect=RuntimeError("pool boom"))):
        r = c.post("/api/cron/hourly-tick", headers={"X-Cron-Secret": "x"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
