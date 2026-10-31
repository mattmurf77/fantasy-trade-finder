"""C8 §A: `entitlement_granted` is registered server-fired and NON_INTENT, and
entitlements.grant() writes it non-touching (analytics-lead's C8 spec,
2026-10-27).

grant() fires for manual, comp, bulk, Founders, referral and group-unlock
grants as well as webhook projections, so the row must never move the
recipient's last_active_at or events_count, and never count as a user-day.

In-memory SQLite; no network.
"""
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.entitlements as entl
from backend import analytics_queries, analytics_taxonomy
from backend.database import metadata, user_events_table, users_table

USER = "c8_grant_user"
SEEN_AT = "2026-10-01T12:00:00+00:00"


@pytest.fixture()
def eng():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=USER, username="c8user",
            created_at=datetime.now(timezone.utc).isoformat(),
            last_active_at=SEEN_AT, events_count=7))
    with patch.object(db_module, "engine", engine):
        yield engine


def test_registered_server_fired_and_non_intent():
    """Both memberships, in the same commit; never client-registered (the
    import-time disjointness assert would raise anyway)."""
    assert "entitlement_granted" in analytics_taxonomy.SERVER_FIRED_EVENTS
    assert "entitlement_granted" in analytics_queries.NON_INTENT_EVENTS
    assert "entitlement_granted" not in analytics_taxonomy.ALLOWED_CLIENT_EVENTS


def test_grant_writes_exact_props(eng):
    entl.grant(USER, "pro", source="manual_grant", duration_days=30)
    with eng.begin() as conn:
        rows = conn.execute(select(user_events_table).where(
            user_events_table.c.event_type == "entitlement_granted")).fetchall()
    assert len(rows) == 1
    row = rows[0]._mapping
    assert row["user_id"] == USER
    props = json.loads(row["props"])
    assert set(props) == {"entitlement", "source", "expires_at"}
    assert (props["entitlement"], props["source"]) == ("pro", "manual_grant")
    assert props["expires_at"]


def test_grant_does_not_touch_the_recipient(eng):
    """Sabotage: drop touch_user=False at entitlements.grant() → red
    (last_active_at moves to now, events_count becomes 8)."""
    entl.grant(USER, "pro", source="manual_grant")
    with eng.begin() as conn:
        user = conn.execute(select(users_table).where(
            users_table.c.sleeper_user_id == USER)).fetchone()._mapping
    assert user["last_active_at"] == SEEN_AT
    assert user["events_count"] == 7
