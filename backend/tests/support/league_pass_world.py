"""Shared seeding for the league pass tests (test_league_pass_*.py).

Import-only. Every helper writes straight into the tables league_pass.py reads,
on an in-memory engine the caller patches in as backend.database.engine.
"""

import json
from datetime import datetime, timedelta, timezone
from itertools import count

from sqlalchemy import create_engine, insert, select

import backend.database as db

_ids = count(1)


def iso(days: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def make_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    return engine


def user(conn, uid, display=None):
    conn.execute(insert(db.users_table).values(
        sleeper_user_id=uid, username=uid, display_name=display, created_at=iso()))


def account(conn, account_id, sleeper_user_id=None):
    conn.execute(insert(db.accounts_table).values(
        account_id=account_id, sleeper_user_id=sleeper_user_id, created_at=iso()))


def league(conn, league_id, platform="sleeper", total_rosters=None):
    conn.execute(insert(db.leagues_table).values(
        sleeper_league_id=league_id, user_id="importer", name=league_id, season="2026",
        platform=None if platform == "sleeper" else platform, total_rosters=total_rosters))


def member(conn, league_id, uid, *, app_user=True):
    """A Sleeper league_members row; app_user also writes the users row."""
    if app_user and conn.execute(select(db.users_table.c.sleeper_user_id).where(
            db.users_table.c.sleeper_user_id == uid)).first() is None:
        user(conn, uid)
    conn.execute(insert(db.league_members_table).values(league_id=league_id, user_id=uid))


def binding(conn, uid, league_id, platform, created_days=0.0):
    conn.execute(insert(db.platform_league_bindings_table).values(
        user_id=uid, league_id=league_id, platform=platform, team_id=str(next(_ids)),
        source="link", created_at=iso(created_days), updated_at=iso(created_days)))


def ent_row(conn, uid, *, product="ftf_league_annual", source="league_pass_iap",
            expires_days=365.0, status="active", granted_by=None, period=None):
    """An entitlements pro row; `period` also writes its ledger event
    (RevenueCat period_type) so paywall_gate._period_types can read it."""
    event_id = granted_by or f"evt-{next(_ids)}"
    conn.execute(insert(db.entitlements_table).values(
        user_id=uid, entitlement="pro", source=source, product_id=product, status=status,
        starts_at=iso(-30), expires_at=None if expires_days is None else iso(expires_days),
        granted_by=event_id, created_at=iso(-30), updated_at=iso(-30)))
    if period is not None:
        conn.execute(insert(db.subscription_events_table).values(
            source="revenuecat", event_type="INITIAL_PURCHASE", user_id=uid,
            product_id=product, event_id=event_id.removeprefix("sandbox:"),
            payload=json.dumps({"period_type": period}), occurred_at=iso(-30)))


def pass_row(conn, league_id, *, buyer=None, origin="purchase", platform="sleeper",
             product="ftf_league_annual", tier=0, comp_days=None, status="active",
             bound_days=-1.0, show_buyer=0):
    now = iso()
    return conn.execute(insert(db.league_passes_table).values(
        origin=origin, buyer_user_id=buyer, product_id=product if origin == "purchase" else None,
        league_id=league_id, platform=platform, status=status, tier=tier,
        comp_expires_at=None if comp_days is None else iso(comp_days), show_buyer=show_buyer,
        bound_at=iso(bound_days), created_at=now, updated_at=now,
    )).inserted_primary_key[0]


def knob(conn, key, value):
    conn.execute(insert(db.model_config_table).values(key=key, value=float(value)))


def passes(engine):
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(
            select(db.league_passes_table).order_by(db.league_passes_table.c.id))]


def events(engine, event_type):
    with engine.connect() as conn:
        rows = conn.execute(select(db.user_events_table.c.user_id, db.user_events_table.c.props,
                                   db.user_events_table.c.league_id)
                            .where(db.user_events_table.c.event_type == event_type)
                            .order_by(db.user_events_table.c.id)).fetchall()
    return [(r.user_id, json.loads(r.props) if r.props else None, r.league_id) for r in rows]
