"""notif-inbox-growth (2026-08-13) — the bell inbox as a growth surface.

Scope + operator decisions: docs/plans/notif-inbox-growth/scope.md.
Strategy: docs/business/product/2026-08-12-notification-inbox-growth-surface.md.

Three behaviours are pinned here, each because getting it wrong is silent
rather than loud:

  (a) GD-8 coalescing — one `league_member_joined` row per league per UTC
      day. Without it a five-person onboarding wave writes five rows on a
      recency-ordered list and buries everything else in the inbox.
  (b) The `match_expiring` idempotency gate. The cron behind it runs every
      15 minutes over the SAME pending matches, and the push's dedup log is
      only written when a push actually leaves — so borrowing it would let
      the row re-fire ~96×/day per match.
  (c) GD-4 server-side dismissal. "Clear all" was cosmetic on both clients
      in two different ways; the fix is one server-side stamp, not a third
      client mechanism.

Harness pattern follows test_analytics_p0.py: isolated file-backed SQLite
engine patched into backend.database.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
from backend.database import metadata, notifications_table

USER = "user_notif_growth"
LEAGUE = "L_notif"


def _engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'notif.db'}",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    return eng


def _rows(eng, user_id=USER):
    with eng.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(
            select(notifications_table)
            .where(notifications_table.c.user_id == user_id)
            .order_by(notifications_table.c.id)
        ).fetchall()]


# ---------------------------------------------------------------------------
# (a) GD-8 — league_member_joined coalescing
# ---------------------------------------------------------------------------

def test_league_join_coalesces_to_one_row_per_league_per_day(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        for name in ("dave", "erin", "fred"):
            db_module.create_or_coalesce_league_join_notification(
                user_id=USER, league_id=LEAGUE, league_name="Sleepy League",
                new_username=name, body="A new leaguemate can mean new trade matches.",
            )

    rows = _rows(eng)
    assert len(rows) == 1, "a three-person wave must read as ONE row"
    meta = json.loads(rows[0]["metadata_json"])
    assert meta["joined_count"] == 3
    assert meta["new_usernames"] == ["dave", "erin", "fred"]
    # The title must state the count, not the first arrival — the row
    # represents today's wave, not a stale receipt of its first member.
    assert rows[0]["title"] == "3 leaguemates joined Sleepy League"
    # Folding resets it to unread: the row changed, so it is news again.
    assert rows[0]["is_read"] == 0


def test_league_join_singular_title_and_per_league_separation(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        db_module.create_or_coalesce_league_join_notification(
            user_id=USER, league_id=LEAGUE, league_name="Sleepy League",
            new_username="dave", body="b",
        )
        # A DIFFERENT league must not fold into the first league's row.
        db_module.create_or_coalesce_league_join_notification(
            user_id=USER, league_id="L_other", league_name="Other League",
            new_username="gina", body="b",
        )

    rows = _rows(eng)
    assert len(rows) == 2
    assert rows[0]["title"] == "@dave joined Sleepy League"
    assert rows[1]["title"] == "@gina joined Other League"


def test_league_join_falls_back_when_league_name_unknown(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        db_module.create_or_coalesce_league_join_notification(
            user_id=USER, league_id=LEAGUE, league_name="",
            new_username="dave", body="b",
        )
    assert _rows(eng)[0]["title"] == "@dave joined your league"


def test_league_join_does_not_resurrect_a_dismissed_row(tmp_path):
    """A dismissed row is not a coalescing target. Folding a new arrival
    into it would un-clear something the user cleared — the exact broken
    promise GD-4 exists to fix."""
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        db_module.create_or_coalesce_league_join_notification(
            user_id=USER, league_id=LEAGUE, league_name="Sleepy League",
            new_username="dave", body="b",
        )
        db_module.dismiss_all_notifications(USER)
        db_module.create_or_coalesce_league_join_notification(
            user_id=USER, league_id=LEAGUE, league_name="Sleepy League",
            new_username="erin", body="b",
        )

    rows = _rows(eng)
    assert len(rows) == 2
    assert rows[0]["dismissed_at"] is not None
    assert rows[1]["dismissed_at"] is None
    # The fresh row starts its own count rather than inheriting the
    # dismissed one's.
    assert json.loads(rows[1]["metadata_json"])["joined_count"] == 1


def test_league_join_yesterdays_row_is_not_a_target(tmp_path):
    eng = _engine(tmp_path)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with eng.begin() as conn:
        conn.execute(insert(notifications_table).values(
            user_id=USER, type="league_member_joined",
            title="@dave joined Sleepy League", body="b",
            metadata_json=json.dumps({"league_id": LEAGUE, "joined_count": 1}),
            is_read=1, created_at=yesterday,
        ))
    with patch.object(db_module, "engine", eng):
        db_module.create_or_coalesce_league_join_notification(
            user_id=USER, league_id=LEAGUE, league_name="Sleepy League",
            new_username="erin", body="b",
        )
    assert len(_rows(eng)) == 2, "the window is per DAY, not per league forever"


# ---------------------------------------------------------------------------
# (b) match_expiring idempotency
# ---------------------------------------------------------------------------

def test_notification_exists_with_meta_matches_on_metadata(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        db_module.create_notification(
            USER, "match_expiring", "t", "b", {"match_id": 42, "league_id": LEAGUE},
        )
        assert db_module.notification_exists_with_meta(
            USER, "match_expiring", "match_id", 42) is True
        # Same value, different type → no match.
        assert db_module.notification_exists_with_meta(
            USER, "trade_match", "match_id", 42) is False
        # Different match → no match. This is the one that matters: it is
        # what lets a SECOND expiring match still reach the inbox.
        assert db_module.notification_exists_with_meta(
            USER, "match_expiring", "match_id", 43) is False
        # Different user → no match.
        assert db_module.notification_exists_with_meta(
            "someone_else", "match_expiring", "match_id", 42) is False


def test_notification_exists_with_meta_compares_across_types(tmp_path):
    """metadata round-trips through JSON, so an int written as 42 can come
    back as 42 or "42" depending on the caller. Both must match."""
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        db_module.create_notification(
            USER, "match_expiring", "t", "b", {"match_id": "42"})
        assert db_module.notification_exists_with_meta(
            USER, "match_expiring", "match_id", 42) is True


def test_notification_exists_with_meta_counts_dismissed_rows(tmp_path):
    """Once written, never rewritten. A user who cleared an expiring-match
    row said they were done with it; re-writing it 15 minutes later is the
    nag this surface exists to avoid."""
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        db_module.create_notification(
            USER, "match_expiring", "t", "b", {"match_id": 42})
        db_module.dismiss_all_notifications(USER)
        assert db_module.notification_exists_with_meta(
            USER, "match_expiring", "match_id", 42) is True


def test_notification_exists_with_meta_fails_closed(tmp_path):
    """On a read error it must claim the row exists. A missing inbox row is
    a lost receipt the next real event recovers from; a row duplicated on
    every cron tick is the surface losing the user."""
    broken = create_engine("sqlite:///:memory:")   # no schema → operational error
    with patch.object(db_module, "engine", broken):
        assert db_module.notification_exists_with_meta(
            USER, "match_expiring", "match_id", 42) is True


# ---------------------------------------------------------------------------
# (c) GD-4 — server-side dismissal
# ---------------------------------------------------------------------------

def test_dismiss_all_hides_rows_from_reads_without_deleting_them(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        db_module.create_notification(USER, "trade_match", "t1", "b", {})
        db_module.create_notification(USER, "referral_joined", "t2", "b", {})
        assert len(db_module.get_notifications(USER)) == 2

        assert db_module.dismiss_all_notifications(USER) == 2
        # Gone from the read API…
        assert db_module.get_notifications(USER) == []
    # …but retained in the table. These rows are the only history this
    # surface has; a dismissal is a display decision, not a data one.
    assert len(_rows(eng)) == 2
    assert all(r["dismissed_at"] is not None for r in _rows(eng))
    assert all(r["is_read"] == 1 for r in _rows(eng))


def test_dismiss_all_is_scoped_to_one_user(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        db_module.create_notification(USER, "trade_match", "mine", "b", {})
        db_module.create_notification("other_user", "trade_match", "theirs", "b", {})
        db_module.dismiss_all_notifications(USER)
        assert db_module.get_notifications(USER) == []
        assert len(db_module.get_notifications("other_user")) == 1


def test_dismiss_all_does_not_hide_rows_written_afterwards(tmp_path):
    """Clearing is a point-in-time act, not a mute. The next real event
    must still reach the bell."""
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        db_module.create_notification(USER, "trade_match", "old", "b", {})
        db_module.dismiss_all_notifications(USER)
        db_module.create_notification(USER, "referral_joined", "new", "b", {})
        live = db_module.get_notifications(USER)
    assert [r["title"] for r in live] == ["new"]


def test_dismiss_all_on_an_empty_inbox_is_a_no_op(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        assert db_module.dismiss_all_notifications(USER) == 0
        assert db_module.dismiss_all_notifications("") == 0
