"""#152 — daily ranking streak increments (record_event → users streak cols).

Operator report: "My streak always stays at 1." Root cause: the operator's
daily ranking surface is the Pick Anchor wizard (anchor_answered — 405 events
in the dev DB, zero trio_swipe/tier_save), and neither anchor_answered nor
ranking_reorder (manual board / Quick Rank) was in _RANK_STREAK_EVENTS — so
daily anchor/reorder activity never advanced the streak past whatever an
earlier qualifying day had written.

Pins:
  1. Day-1 activity → 1, day-2 activity → 2 (the task's regression shape),
     for the previously-broken surfaces (anchor_answered, ranking_reorder)
     AND the baseline surface (trio_swipe).
  2. Gap day (day-1 then day-3) → reset to 1, longest preserved.
  3. Same-local-day re-rank is a no-op.
  4. Local-day frame follows the client tz.

Dates are FROZEN by patching backend.database.datetime — no sleeping. Same
isolated-engine pattern as test_analytics_p0.py.
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
from backend.database import metadata, users_table

USER = "user_streaks_152"


class _FrozenDT(datetime):
    """datetime whose now() returns a settable instant (tz-converted)."""
    _now: datetime = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):  # noqa: D102 — signature mirrors datetime.now
        return cls._now.astimezone(tz) if tz else cls._now


@pytest.fixture()
def frozen_db():
    """Isolated in-memory engine + frozen clock; yields the set-clock fn."""
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=USER, username=USER, created_at="2026-07-19",
        ))

    def at(y, m, d, hour=12):
        _FrozenDT._now = datetime(y, m, d, hour, tzinfo=timezone.utc)

    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "datetime", _FrozenDT):
        yield at


# ── 1. Consecutive-day increment (the #152 regression shape) ─────────────

@pytest.mark.parametrize("event_type", [
    "anchor_answered",   # Pick Anchor wizard — the operator's daily surface
    "ranking_reorder",   # manual board + Quick Rank
    "trio_swipe",        # baseline (was already qualifying)
])
def test_day1_then_day2_increments_to_2(frozen_db, event_type):
    at = frozen_db
    at(2026, 7, 20)
    r1 = db_module.record_event(USER, event_type, tz="America/New_York")
    assert r1 is not None, f"{event_type} must be a rank-class streak event"
    assert r1["current"] == 1

    at(2026, 7, 21)
    r2 = db_module.record_event(USER, event_type, tz="America/New_York")
    assert r2["current"] == 2
    assert r2["longest"] == 2
    assert db_module.get_user_streak(USER)["current"] == 2


# ── 2. Gap day resets to 1 ───────────────────────────────────────────────

def test_gap_day_resets_to_1_and_keeps_longest(frozen_db):
    at = frozen_db
    at(2026, 7, 20)
    db_module.record_event(USER, "anchor_answered", tz="America/New_York")
    at(2026, 7, 21)
    r2 = db_module.record_event(USER, "anchor_answered", tz="America/New_York")
    assert r2["current"] == 2

    at(2026, 7, 23)  # skipped the 22nd
    r3 = db_module.record_event(USER, "anchor_answered", tz="America/New_York")
    assert r3["current"] == 1
    assert r3["longest"] == 2  # longest survives the reset


# ── 3. Same-local-day is a no-op ─────────────────────────────────────────

def test_same_day_re_rank_is_noop(frozen_db):
    at = frozen_db
    at(2026, 7, 20, hour=8)
    db_module.record_event(USER, "anchor_answered", tz="America/New_York")
    at(2026, 7, 20, hour=22)
    r = db_module.record_event(USER, "anchor_answered", tz="America/New_York")
    assert r["current"] == 1
    assert r["last_rank_local_date"] == "2026-07-20"


# ── 4. Local-day frame follows the client tz ─────────────────────────────

def test_local_day_uses_client_tz_not_utc(frozen_db):
    """03:00 UTC on the 21st is still the evening of the 20th in New York:
    an evening rank + a next-morning rank must count as TWO local days even
    though they're on the same/adjacent UTC dates."""
    at = frozen_db
    at(2026, 7, 21, hour=3)   # 20th, 11pm ET
    r1 = db_module.record_event(USER, "trio_swipe", tz="America/New_York")
    assert r1["last_rank_local_date"] == "2026-07-20"

    at(2026, 7, 21, hour=13)  # 21st, 9am ET
    r2 = db_module.record_event(USER, "trio_swipe", tz="America/New_York")
    assert r2["current"] == 2
    assert r2["last_rank_local_date"] == "2026-07-21"


# ── 5. Non-rank events never touch the streak ────────────────────────────

def test_non_rank_events_do_not_advance_streak(frozen_db):
    at = frozen_db
    at(2026, 7, 20)
    assert db_module.record_event(USER, "app_open", tz="America/New_York") is None
    assert db_module.get_user_streak(USER)["current"] == 0
