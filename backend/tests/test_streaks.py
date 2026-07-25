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

Residual fixes (same item, follow-up):
  6. Read-time decay — get_user_streak reports an EFFECTIVE current of 0
     once the last rank is >1 local day old (stored row untouched, longest
     preserved), and the streak leaderboard drops lapsed users so they
     don't squat on top spots.
  7. Read-decay didn't break write math: a lapsed user's next rank still
     resets to 1 and increments to 2 the next day.
  8. anchor_answered / ranking_reorder bump users.last_rank_at like the
     other rank-class events (notification-nudge gating undercounted
     anchor-wizard and manual-board users).

Dates are FROZEN by patching backend.database.datetime — no sleeping. Same
isolated-engine pattern as test_analytics_p0.py.
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

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


# ── 6. Residual: lapsed streaks decay to 0 on read ───────────────────────

def _stored_streak_row(uid=USER):
    """The raw stored row — read-time decay must never mutate it."""
    with db_module.engine.begin() as conn:
        return conn.execute(
            select(
                users_table.c.current_streak,
                users_table.c.longest_streak,
                users_table.c.last_rank_local_date,
                users_table.c.last_rank_at,
            ).where(users_table.c.sleeper_user_id == uid)
        ).first()


def _rank_two_days(at, tz="America/New_York"):
    """Streak 2: rank on the 20th and 21st (noon UTC = same local dates)."""
    at(2026, 7, 20)
    db_module.record_event(USER, "anchor_answered", tz=tz)
    at(2026, 7, 21)
    r = db_module.record_event(USER, "anchor_answered", tz=tz)
    assert r["current"] == 2


def test_lapsed_user_reads_zero_longest_preserved_row_unmutated(frozen_db):
    at = frozen_db
    _rank_two_days(at)

    at(2026, 7, 25)  # 3+ days after the last rank — lapsed
    snap = db_module.get_user_streak(USER, tz="America/New_York")
    assert snap["current"] == 0
    assert snap["longest"] == 2
    assert snap["last_rank_local_date"] == "2026-07-21"

    row = _stored_streak_row()  # display-time computation only — no write
    assert row.current_streak == 2
    assert row.longest_streak == 2
    assert row.last_rank_local_date == "2026-07-21"


def test_active_user_reads_unchanged(frozen_db):
    at = frozen_db
    _rank_two_days(at)
    # Last rank today → unchanged.
    assert db_module.get_user_streak(USER, tz="America/New_York")["current"] == 2
    # Last rank yesterday → still unchanged (ranking today would increment).
    at(2026, 7, 22)
    assert db_module.get_user_streak(USER, tz="America/New_York")["current"] == 2


def test_read_decay_uses_stored_tz_when_no_viewer_tz(frozen_db):
    """02:00 UTC on the 23rd is still the evening of the 22nd in New York:
    a last-rank-date of the 21st is 'yesterday' there (active) but 2 days
    back in the UTC frame (lapsed). No viewer tz → the stored last_rank_tz
    frame applies; an explicit viewer tz wins over it."""
    at = frozen_db
    _rank_two_days(at)  # last_rank_local_date = 2026-07-21, tz stored = NY

    at(2026, 7, 23, hour=2)  # 22nd, 10pm ET
    assert db_module.get_user_streak(USER)["current"] == 2          # NY frame
    assert db_module.get_user_streak(USER, tz="UTC")["current"] == 0  # viewer frame wins


def test_lapsed_user_ranking_again_resets_then_increments(frozen_db):
    """Read-time decay must not break write-time math: the stored value +
    date still drive the transition, so a lapsed user's next rank is a
    day-1 reset and the day after increments normally."""
    at = frozen_db
    _rank_two_days(at)

    at(2026, 7, 25)
    assert db_module.get_user_streak(USER, tz="America/New_York")["current"] == 0
    r = db_module.record_event(USER, "anchor_answered", tz="America/New_York")
    assert r["current"] == 1       # reset, not 0+1-from-display
    assert r["longest"] == 2       # longest survives

    at(2026, 7, 26)
    r = db_module.record_event(USER, "anchor_answered", tz="America/New_York")
    assert r["current"] == 2       # day-2 increment path intact post-decay


# ── 7. Residual: leaderboard drops lapsed users ──────────────────────────

def test_leaderboard_lapsed_high_streak_ranks_below_active(frozen_db):
    at = frozen_db
    active = "user_streaks_152_active"
    with db_module.engine.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=active, username=active, created_at="2026-07-19",
        ))

    # USER builds a streak of 5 (Jul 14-18), then stops.
    for day in range(14, 19):
        at(2026, 7, day)
        db_module.record_event(USER, "anchor_answered", tz="America/New_York")
    # `active` builds a streak of 2 (Jul 24-25) and is current.
    for day in (24, 25):
        at(2026, 7, day)
        db_module.record_event(active, "trio_swipe", tz="America/New_York")

    at(2026, 7, 25)
    board = db_module.load_leaderboard(metric="streak")
    uids = [r["user_id"] for r in board["rows"]]
    assert uids == [active]                      # lapsed 5-streak is off the board
    assert board["rows"][0]["value"] == 2

    assert db_module._streak_self_rank(active, None) == (1, 2)
    assert db_module._streak_self_rank(USER, None) is None  # lapsed → not ranked


# ── 8. Residual: anchor/reorder events bump users.last_rank_at ───────────

@pytest.mark.parametrize("event_type", ["anchor_answered", "ranking_reorder"])
def test_rank_surface_events_update_last_rank_at(frozen_db, event_type):
    at = frozen_db
    at(2026, 7, 20)
    assert _stored_streak_row().last_rank_at is None  # precondition
    db_module.record_event(USER, event_type, tz="America/New_York")
    assert _stored_streak_row().last_rank_at == "2026-07-20T12:00:00+00:00"
