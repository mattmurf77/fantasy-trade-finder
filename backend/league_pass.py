"""
league_pass.py — one buyer's annual subscription covers one league.

Spec: docs/plans/monetization/league-pass/lld.md §3 (hld.md §2–3, prd.md §4).

Coverage is DERIVED at read time from three facts, each with one owner, and
is never stored per member:

  * the buyer's subscription is live — an `entitlements` pro row with source
    `league_pass_iap` (written by the billing projector only);
  * the pass is bound to the league — a `league_passes` row (written here only);
  * the user is currently a member — `league_members` (Sleeper) or
    `platform_league_bindings` (ESPN / MFL), written by league sync only.

The buyer holds ordinary account-level pro through the projector; a covered
member holds no row, so their `pro` stays false and coverage is a separate,
league-keyed answer (`covers`).

A leaf like entitlements.py: never imports `server` or `paywall_gate`
(paywall_gate imports this module to call `covers`).
Write paths refuse with `Refused(reason)`; routes turn it into a 409.

Release can be limited to an allow-list of league ids in the env var
LEAGUE_PASS_LEAGUE_ALLOWLIST (comma-separated, read live; unset or empty = no
restriction). model_config is float-only, so the list lives where the other
id lists do (FOUNDER_ACCOUNTS, TEST_PROFILE_ACCOUNTS).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from . import database as db
from . import entitlements
from .accounts import account_user_id
from .feature_flags import is_enabled

log = logging.getLogger(__name__)

FLAG = "monetize.league_pass"
SOURCE = "league_pass_iap"
PRODUCT_PREFIX = "ftf_league_"
ALLOWLIST_ENV = "LEAGUE_PASS_LEAGUE_ALLOWLIST"
# The one league product: $99.99 a year, with a one-month free trial as its
# App Store introductory offer (D-281 addendum 2026-11-24). A buyer in the
# trial holds a live league_pass_iap row exactly like a paying one.
PRODUCT_ID = "ftf_league_annual"
# The owner of events no one person caused (comp binds, deletion releases).
_SYSTEM_USER = "system:league_pass"

# model_config knobs; the fallback must match the seed (G-064).
_KNOBS = {
    "league_pass_repoint_cooldown_days": 30.0,
    "league_pass_seat_allowance": 2.0,
    "league_pass_intent_ttl_minutes": 60.0,
}


class Refused(Exception):
    """A write path's refusal. `reason` is the closed code a route returns;
    `detail` carries extra fields (e.g. can_repoint_at)."""

    def __init__(self, reason: str, **detail):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Coverage:
    pass_id: int
    league_id: str
    covered_until: str        # ISO UTC
    role: str                 # 'buyer' | 'member'


# ---------------------------------------------------------------------------
# Small reads
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _knob(key: str) -> float:
    try:
        return float(db.get_config().get(key, _KNOBS[key]))
    except Exception:
        return _KNOBS[key]


def _allowed(league_id: str) -> bool:
    ids = {x.strip() for x in os.environ.get(ALLOWLIST_ENV, "").split(",") if x.strip()}
    return not ids or league_id in ids


def _aliases(conn, user_id: str) -> set[str]:
    """Every working key this person is known by: the id itself, the bound
    account's acct_* key, and that account's Sleeper id."""
    out = {user_id}
    account_id = entitlements._account_for_user(conn, user_id)
    if account_id:
        out.add(account_user_id(account_id))
        sleeper = conn.execute(
            select(db.accounts_table.c.sleeper_user_id)
            .where(db.accounts_table.c.account_id == account_id)
        ).scalar()
        if sleeper:
            out.add(sleeper)
    return out


def _platform(conn, league_id: str) -> str | None:
    """The league's platform ('sleeper' for a NULL column); None when the
    league is unknown here."""
    row = conn.execute(
        select(db.leagues_table.c.platform)
        .where(db.leagues_table.c.sleeper_league_id == league_id)
    ).fetchone()
    if row is None:
        return None
    return row.platform or "sleeper"


def _member_ids(conn, league_id: str, platform: str) -> list[str]:
    """App users in the league, oldest first. Sleeper: league_members rows
    with a users row (league_members also lists managers who never used the
    app), oldest app account first (users.created_at, written once at
    insert; a missing one sorts first), then user id: league_members.id is
    not stable, because SQLite's INSERT OR REPLACE sync gives a re-synced
    member a new id. ESPN / MFL: platform_league_bindings by created_at
    (kept on re-link), then user id, because league_members holds a
    synthetic id for every unbound team."""
    if platform == "sleeper":
        lm, u = db.league_members_table, db.users_table
        return list(conn.execute(
            select(lm.c.user_id)
            .join(u, u.c.sleeper_user_id == lm.c.user_id)
            .where(lm.c.league_id == league_id)
            .order_by(func.coalesce(u.c.created_at, ""), lm.c.user_id)
        ).scalars())
    plb = db.platform_league_bindings_table
    return list(conn.execute(
        select(plb.c.user_id).where(plb.c.league_id == league_id)
        .order_by(plb.c.created_at, plb.c.user_id)
    ).scalars())


def _team_count(conn, league_id: str) -> int:
    """total_rosters, else the league_members row count (one per team)."""
    total = conn.execute(
        select(db.leagues_table.c.total_rosters)
        .where(db.leagues_table.c.sleeper_league_id == league_id)
    ).scalar()
    if isinstance(total, int) and total > 0:
        return total
    return conn.execute(
        select(func.count()).select_from(db.league_members_table)
        .where(db.league_members_table.c.league_id == league_id)
    ).scalar() or 0


def _covered_ids(conn, league_id: str, platform: str, allowance: int) -> list[str]:
    """`allowance` is read by the caller before it opens `conn` (get_config
    opens its own connection)."""
    cap = _team_count(conn, league_id) + allowance
    return _member_ids(conn, league_id, platform)[:cap]


def _allowance() -> int:
    return int(_knob("league_pass_seat_allowance"))


def _is_member(conn, user_id: str, league_id: str, platform: str) -> bool:
    ids = _aliases(conn, user_id)
    if platform == "sleeper":
        t = db.league_members_table
        q = select(t.c.id).where(t.c.league_id == league_id).where(t.c.user_id.in_(ids))
    else:
        t = db.platform_league_bindings_table
        q = select(t.c.user_id).where(t.c.league_id == league_id).where(t.c.user_id.in_(ids))
    return conn.execute(q.limit(1)).first() is not None


def _active_pass(conn, league_id: str):
    t = db.league_passes_table
    return conn.execute(
        select(t).where(t.c.league_id == league_id).where(t.c.status == "active")
    ).fetchone()


def _buyer_pass(conn, ids: set[str]):
    """The buyer's active purchase pass (any of their working keys)."""
    t = db.league_passes_table
    return conn.execute(
        select(t).where(t.c.buyer_user_id.in_(ids))
        .where(t.c.origin == "purchase").where(t.c.status == "active")
    ).fetchone()


def _buyer_row(conn, buyer_user_id: str):
    """The buyer's live league_pass_iap pro row with the furthest expiry."""
    rows = [r for r in entitlements._active_rows(conn, buyer_user_id)
            if r.entitlement == "pro" and r.source == SOURCE]
    return max(rows, key=lambda r: r.expires_at or "9999") if rows else None


def _live_until(conn, row) -> str | None:
    """When a pass stops being live, or None when it is not live now."""
    if row.origin == "comp":
        until = row.comp_expires_at
        return until if until and until > _now().isoformat() else None
    if not row.buyer_user_id:
        return None
    buyer = _buyer_row(conn, row.buyer_user_id)
    if buyer is None:
        return None
    return buyer.expires_at or "9999-12-31T00:00:00+00:00"


def _is_buyer(row, ids: set[str]) -> bool:
    return bool((row.buyer_user_id and row.buyer_user_id in ids)
                or (row.buyer_account_id and account_user_id(row.buyer_account_id) in ids))


def _emit(user_id: str | None, event: str, props: dict, league_id: str | None = None,
          conn=None) -> None:
    db.record_event(user_id or _SYSTEM_USER, event, league_id=league_id, props=props,
                    touch_user=False, conn=conn)


def _drop_dead(league_id: str | None = None, buyer_ids: set[str] | None = None) -> None:
    """End an active row that is no longer live, so a lapsed pass (one whose
    expiry or refund event arrived while the flag was off) never blocks a
    league or a buyer. Write paths only; covers() never writes."""
    with db.engine.begin() as conn:
        rows = []
        if league_id is not None:
            rows.append(_active_pass(conn, league_id))
        if buyer_ids:
            rows.append(_buyer_pass(conn, buyer_ids))
        dead = [r.id for r in rows if r is not None and _live_until(conn, r) is None]
    for pass_id in dead:
        end(pass_id, "ended")


# ---------------------------------------------------------------------------
# §3.1 Membership
# ---------------------------------------------------------------------------

def is_member(user_id: str, league_id: str, platform: str) -> bool:
    """Sleeper: a league_members row under the user's Sleeper id (an acct_*
    key resolves through accounts). ESPN / MFL: a platform_league_bindings
    row for the user; unproven team links count (lld §13 item 2)."""
    with db.engine.begin() as conn:
        return _is_member(conn, user_id, league_id, platform)


def covered_members(league_id: str, platform: str) -> list[str]:
    """The app users who are members, oldest first, cut at total_rosters +
    league_pass_seat_allowance (R7)."""
    allowance = _allowance()
    with db.engine.begin() as conn:
        return _covered_ids(conn, league_id, platform, allowance)


# ---------------------------------------------------------------------------
# §3.2 Coverage
# ---------------------------------------------------------------------------

def covers(user_id: str, league_id: str) -> Coverage | None:
    """None at the first failure of: an active pass for the league; the
    allow-list; the pass is live (buyer's league_pass_iap row, or the comp
    expiry); the user is among covered_members. The caller settles verified-
    ness and the flag before asking (lld §4.1)."""
    if not user_id or not league_id:
        return None
    allowance = _allowance()
    with db.engine.begin() as conn:
        row = _active_pass(conn, league_id)
        if row is None or not _allowed(league_id):
            return None
        until = _live_until(conn, row)
        if until is None:
            return None
        ids = _aliases(conn, user_id)
        if not ids & set(_covered_ids(conn, league_id, row.platform, allowance)):
            return None
    return Coverage(pass_id=row.id, league_id=league_id, covered_until=until,
                    role="buyer" if _is_buyer(row, ids) else "member")


def passes_for(user_id: str, *, league_user_id: str | None = None,
               league_id: str | None = None) -> list[dict]:
    """Every live pass covering this user, starting from the user's leagues:
    [{pass_id, league_id, platform, role, covered_until, buyer_display}].
    buyer_display is the buyer's display name only when show_buyer is 1.

    The Sleeper co-owner, by the gate's rule (paywall_gate.verdict): in
    `league_id` (the session's active league) only, a pass that does not
    cover `user_id` is also tried under `league_user_id` (the session's
    league identity, the roster's primary owner that league_members lists),
    and listed with role 'member'. The co-owner rides that owner's seat: it
    is not a covered_members entry and takes no seat of its own. Omitted, or
    equal to `user_id` (a sole owner), nothing more is read."""
    co = (league_user_id if league_user_id and league_id and league_user_id != user_id
          else None)
    with db.engine.begin() as conn:
        ids = _aliases(conn, user_id)
        lm, plb = db.league_members_table, db.platform_league_bindings_table
        leagues = set(conn.execute(
            select(lm.c.league_id).where(lm.c.user_id.in_(ids))).scalars())
        leagues |= set(conn.execute(
            select(plb.c.league_id).where(plb.c.user_id.in_(ids))).scalars())
        if co:
            leagues.add(league_id)
        t = db.league_passes_table
        bound = conn.execute(
            select(t).where(t.c.league_id.in_(leagues)).where(t.c.status == "active")
            .order_by(t.c.id)
        ).fetchall() if leagues else []
    out = []
    for row in bound:
        cov = covers(user_id, row.league_id)
        role = cov.role if cov is not None else "member"
        if cov is None and co and row.league_id == league_id:
            cov = covers(co, row.league_id)
        if cov is None:
            continue
        out.append({"pass_id": row.id, "league_id": row.league_id,
                    "platform": row.platform, "role": role,
                    "covered_until": cov.covered_until,
                    "buyer_display": _buyer_display(row) if row.show_buyer else None})
    return out


def _buyer_display(row) -> str | None:
    if not row.buyer_user_id:
        return None
    with db.engine.begin() as conn:
        ids = _aliases(conn, row.buyer_user_id)
        u = conn.execute(
            select(db.users_table.c.display_name, db.users_table.c.username)
            .where(db.users_table.c.sleeper_user_id.in_(ids))
        ).fetchone()
    return (u.display_name or u.username) if u else None


# ---------------------------------------------------------------------------
# §3.3 Quote and intent
# ---------------------------------------------------------------------------

def _refund_blocked(user_id: str) -> bool:
    """R36: an account that had a pass refunded can't buy another without
    operator action (the operator revokes or edits the refunded row)."""
    return any(r["source"] == SOURCE and r["status"] == "refunded"
               for r in entitlements.list_for_user(user_id))


def create_intent(user_id: str, league_id: str) -> dict:
    """Record the league a member chose before the purchase sheet. Refuses,
    in order: not_member, league_not_allowed, already_covered, already_buyer,
    refund_blocked. Returns {intent_id, product_id, teams, expires_at}."""
    with db.engine.begin() as conn:
        platform = _platform(conn, league_id)
        if platform is None or not _is_member(conn, user_id, league_id, platform):
            raise Refused("not_member")
        ids = _aliases(conn, user_id)
    if not _allowed(league_id):
        raise Refused("league_not_allowed")
    _drop_dead(league_id, ids)
    with db.engine.begin() as conn:
        if _active_pass(conn, league_id) is not None:
            raise Refused("already_covered")
        if _buyer_pass(conn, ids) is not None:
            raise Refused("already_buyer")
    if _refund_blocked(user_id):
        raise Refused("refund_blocked")
    now = _now()
    expires_at = (now + timedelta(minutes=_knob("league_pass_intent_ttl_minutes"))).isoformat()
    with db.engine.begin() as conn:
        teams = _team_count(conn, league_id)
        intent_id = conn.execute(insert(db.league_pass_intents_table).values(
            user_id=user_id, league_id=league_id, platform=platform,
            product_id=PRODUCT_ID, created_at=now.isoformat(), expires_at=expires_at,
        )).inserted_primary_key[0]
    _emit(user_id, "league_pass_quote_viewed",
          {"platform": platform, "teams": teams}, league_id)
    return {"intent_id": intent_id, "product_id": PRODUCT_ID, "teams": teams,
            "expires_at": expires_at}


# ---------------------------------------------------------------------------
# §3.4 Bind, re-point, rollover
# ---------------------------------------------------------------------------

def _pass_dict(row) -> dict:
    return dict(row._mapping)


def _insert_pass(conn, **values):
    now = _now().isoformat()
    values.setdefault("bound_at", now)
    pass_id = conn.execute(insert(db.league_passes_table).values(
        status="active", created_at=now, updated_at=now, **values,
    )).inserted_primary_key[0]
    return conn.execute(select(db.league_passes_table)
                        .where(db.league_passes_table.c.id == pass_id)).fetchone()


def _bind(user_id: str, league_id: str, platform: str, product_id: str, *,
          via: str, intent_id: int | None = None,
          event_id: str | None = None) -> dict:
    """lld §3.4 steps 3–5: membership, no live pass on the league, then
    insert (and consume the intent) in one transaction."""
    with db.engine.begin() as conn:
        if not _is_member(conn, user_id, league_id, platform):
            raise Refused("not_member")
    _drop_dead(league_id)
    try:
        with db.engine.begin() as conn:
            if _active_pass(conn, league_id) is not None:
                raise Refused("already_covered")
            row = _insert_pass(
                conn, origin="purchase", buyer_user_id=user_id,
                buyer_account_id=entitlements._account_for_user(conn, user_id),
                product_id=product_id, league_id=league_id, platform=platform)
            if intent_id is not None:
                conn.execute(update(db.league_pass_intents_table)
                             .where(db.league_pass_intents_table.c.id == intent_id)
                             .values(consumed_at=row.bound_at, consumed_event_id=event_id))
    except IntegrityError:
        # The partial unique indexes: another bind won the league or buyer.
        raise Refused("already_covered")
    _emit(user_id, "league_pass_bound",
          {"origin": "purchase", "platform": platform, "via": via}, league_id)
    return _pass_dict(row)


def on_billing_event(user_id: str, product_id: str, event_type: str, event_id: str) -> None:
    """After the projector, while the flag is on, for an ftf_league_* product
    (the product the event projected onto: a PRODUCT_CHANGE into the league
    product counts, entitlements._effective_product), or for an activating
    event of another product that ended the buyer's league row
    (entitlements._supersede).

    Activating, league product: if the buyer already has an active pass (a
    renewal, or a free trial converting to paid), nothing. Else bind from
    their newest unconsumed, unexpired intent, whatever other pro the buyer
    holds (an individual subscription upgraded into the pass, a lifetime
    grant). No intent, or a failed re-check, leaves the pass unbound
    (logged); the buyer keeps pro.
    Another product: when the buyer's league row is no longer live (a
    downgrade to an individual plan took effect), their pass is ended.
    Deactivating (expiry, refund): once the buyer has no live league row
    left, their pass is ended (reporting state; coverage already followed
    the row). A free trial's INITIAL_PURCHASE (period_type TRIAL) binds like
    any other: the projector ignores period_type, and there is no limit on
    trials per league (D-281 addendum 2026-11-24)."""
    if not is_enabled(FLAG):
        return
    league = (product_id or "").lower().startswith(PRODUCT_PREFIX)
    with db.engine.begin() as conn:
        ids = _aliases(conn, user_id)
        current = _buyer_pass(conn, ids)
        live = _buyer_row(conn, user_id) is not None
    if not league:
        if current is not None and not live:
            end(current.id, "ended")
        return
    if event_type in entitlements._RC_DEACTIVATING or event_type in (
            "customer.subscription.deleted", "charge.refunded"):
        if current is not None and not live:
            end(current.id, "refund" if event_type in ("REFUND", "charge.refunded") else "ended")
        return
    if event_type not in entitlements._RC_ACTIVATING or current is not None:
        return
    t = db.league_pass_intents_table
    with db.engine.begin() as conn:
        intent = conn.execute(
            select(t).where(t.c.user_id.in_(ids)).where(t.c.consumed_at.is_(None))
            .where(t.c.expires_at > _now().isoformat()).order_by(t.c.id.desc()).limit(1)
        ).fetchone()
    if intent is None:
        log.warning("LEAGUE-PASS-UNBOUND user=%s reason=no_intent event_id=%s",
                    user_id, event_id)
        return
    try:
        _bind(user_id, intent.league_id, intent.platform, product_id,
              via="webhook", intent_id=intent.id, event_id=event_id)
    except Refused as e:
        log.warning("LEAGUE-PASS-UNBOUND user=%s reason=%s event_id=%s",
                    user_id, e.reason, event_id)


def bind(user_id: str, league_id: str) -> dict:
    """The manual path (R19) for a buyer whose pass is unbound: the same
    checks as the webhook bind. Refuses: no_purchase, already_buyer,
    not_member, league_not_allowed, already_covered."""
    with db.engine.begin() as conn:
        buyer = _buyer_row(conn, user_id)
        ids = _aliases(conn, user_id)
        platform = _platform(conn, league_id)
    if buyer is None:
        raise Refused("no_purchase")
    _drop_dead(buyer_ids=ids)
    with db.engine.begin() as conn:
        if _buyer_pass(conn, ids) is not None:
            raise Refused("already_buyer")
    if platform is None:
        raise Refused("not_member")
    if not _allowed(league_id):
        raise Refused("league_not_allowed")
    return _bind(user_id, league_id, platform, buyer.product_id, via="manual")


def _cooldown_anchor(conn, ids: set[str]) -> str | None:
    """The buyer's latest bind or re-point. A rollover's new row is bound at
    the instant its predecessor was released for 'rollover', so those binds
    are left out: a rollover never uses the cooldown (R22)."""
    t = db.league_passes_table
    rows = conn.execute(
        select(t.c.bound_at, t.c.released_at, t.c.release_reason)
        .where(t.c.buyer_user_id.in_(ids)).where(t.c.origin == "purchase")
    ).fetchall()
    rolled = {r.released_at for r in rows if r.release_reason == "rollover"}
    binds = [r.bound_at for r in rows if r.bound_at not in rolled]
    return max(binds) if binds else None


def repoint(user_id: str, league_id: str) -> dict:
    """Move the buyer's live pass to another league they are in, once per
    league_pass_repoint_cooldown_days (R21). Release and insert are one transaction. Refuses: no_pass, cooldown
    (detail can_repoint_at), not_member, league_not_allowed, already_covered."""
    with db.engine.begin() as conn:
        ids = _aliases(conn, user_id)
        current = _buyer_pass(conn, ids)
        if current is None or _live_until(conn, current) is None:
            raise Refused("no_pass")
        anchor = _cooldown_anchor(conn, ids)
        platform = _platform(conn, league_id)
    if anchor:
        ready = (datetime.fromisoformat(anchor)
                 + timedelta(days=_knob("league_pass_repoint_cooldown_days")))
        if _now() < ready:
            raise Refused("cooldown", can_repoint_at=ready.isoformat())
    if platform is None or not is_member(user_id, league_id, platform):
        raise Refused("not_member")
    if not _allowed(league_id):
        raise Refused("league_not_allowed")
    _drop_dead(league_id)
    try:
        with db.engine.begin() as conn:
            if _active_pass(conn, league_id) is not None:
                raise Refused("already_covered")
            row = _move(conn, current, league_id, platform, "repoint")
    except IntegrityError:
        raise Refused("already_covered")
    _emit(current.buyer_user_id, "league_pass_bound",
          {"origin": "purchase", "platform": platform, "via": "repoint"},
          league_id)
    return _pass_dict(row)


def _move(conn, current, league_id: str, platform: str, reason: str):
    """Release `current` and insert its successor on `league_id`, stamped
    with the same instant (the cooldown reads that, _cooldown_anchor)."""
    now = _now().isoformat()
    t = db.league_passes_table
    released = conn.execute(
        update(t).where(t.c.id == current.id).where(t.c.status == "active")
        .values(status="released", released_at=now, release_reason=reason, updated_at=now)
    ).rowcount
    if not released:
        raise Refused("no_pass")
    return _insert_pass(
        conn, origin=current.origin, buyer_user_id=current.buyer_user_id,
        buyer_account_id=current.buyer_account_id, product_id=current.product_id,
        league_id=league_id, platform=platform,
        comp_expires_at=current.comp_expires_at, show_buyer=current.show_buyer,
        note=current.note, bound_at=now)


def follow_rollover(new_league_id: str, previous_league_id: str | None) -> bool:
    """Called by Sleeper league sync (hld §3.5). Moves the previous league's
    active pass to the new league when the buyer is a member of the new one
    (a comp pass moves with its league), the new league has no pass, and the
    flag is on. Never uses the buyer's re-point cooldown (R22)."""
    previous = str(previous_league_id or "").strip()
    if (not is_enabled(FLAG) or not new_league_id or previous in ("", "0")
            or previous == new_league_id):
        return False
    with db.engine.begin() as conn:
        current = _active_pass(conn, previous)
        if current is None or _active_pass(conn, new_league_id) is not None:
            return False
        if current.origin == "purchase" and not (
                current.buyer_user_id
                and _is_member(conn, current.buyer_user_id, new_league_id, "sleeper")):
            return False
    try:
        with db.engine.begin() as conn:
            row = _move(conn, current, new_league_id, "sleeper", "rollover")
    except (IntegrityError, Refused):
        return False
    _emit(current.buyer_user_id, "league_pass_bound",
          {"origin": current.origin, "platform": "sleeper", "via": "rollover"}, new_league_id)
    return True


def on_transfer(from_ids, to_user_id: str) -> None:
    """A TRANSFER moved a subscription to `to_user_id` (lld §5). When the new
    owner now holds a live league row, the from-side's active pass is
    re-keyed to them if they are a member of its league, else released."""
    if not is_enabled(FLAG):
        return
    from_ids = {i for i in from_ids if i and i != to_user_id}
    if not from_ids:
        return
    t = db.league_passes_table
    with db.engine.begin() as conn:
        if _buyer_row(conn, to_user_id) is None:
            return
        current = _buyer_pass(conn, from_ids)
        if current is None or _buyer_pass(conn, _aliases(conn, to_user_id)) is not None:
            return
        now = _now().isoformat()
        if _is_member(conn, to_user_id, current.league_id, current.platform):
            conn.execute(update(t).where(t.c.id == current.id).values(
                buyer_user_id=to_user_id,
                buyer_account_id=entitlements._account_for_user(conn, to_user_id),
                show_buyer=0, updated_at=now))
            return
        conn.execute(update(t).where(t.c.id == current.id).values(
            status="released", released_at=now, release_reason="transfer", updated_at=now))


def comp(league_id: str, days: int, note: str | None) -> dict:
    """An operator comp pass (R39): no buyer; live until comp_expires_at.
    Refuses: bad_days, unknown_league, already_covered."""
    if not isinstance(days, int) or isinstance(days, bool) or days <= 0:
        raise Refused("bad_days")
    with db.engine.begin() as conn:
        platform = _platform(conn, league_id)
    if platform is None:
        raise Refused("unknown_league")
    _drop_dead(league_id)
    expires = (_now() + timedelta(days=days)).isoformat()
    try:
        with db.engine.begin() as conn:
            if _active_pass(conn, league_id) is not None:
                raise Refused("already_covered")
            row = _insert_pass(conn, origin="comp", league_id=league_id,
                               platform=platform, comp_expires_at=expires, note=note)
    except IntegrityError:
        raise Refused("already_covered")
    _emit(None, "league_pass_bound",
          {"origin": "comp", "platform": platform, "via": "comp"}, league_id)
    return _pass_dict(row)


def end(pass_id: int, reason: str) -> bool:
    """Mark an active pass ended (reporting state; a purchase pass's liveness
    already follows the buyer's row). reason: ended | refund | admin. False
    when there is no active pass with that id."""
    now = _now().isoformat()
    t = db.league_passes_table
    with db.engine.begin() as conn:
        row = conn.execute(select(t).where(t.c.id == pass_id)).fetchone()
        done = conn.execute(
            update(t).where(t.c.id == pass_id).where(t.c.status == "active")
            .values(status="ended", released_at=now, release_reason=reason, updated_at=now)
        ).rowcount
    if not done:
        return False
    _emit(row.buyer_user_id, "league_pass_ended", {"reason": reason}, row.league_id)
    return True


# ---------------------------------------------------------------------------
# §6 Route reads and the one settings write
# ---------------------------------------------------------------------------

_RENEWAL_EVENTS = ("INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION", "PRODUCT_CHANGE",
                   "CANCELLATION")


def _will_renew(conn, row) -> bool:
    """False when the buyer's latest App Store renewal-state event for the
    row's product is a CANCELLATION (auto-renew off; the projector treats it
    as a no-op, so only the ledger knows)."""
    t = db.subscription_events_table
    last = conn.execute(
        select(t.c.event_type).where(t.c.user_id == row.user_id)
        .where(t.c.product_id == row.product_id).where(t.c.event_type.in_(_RENEWAL_EVENTS))
        .order_by(t.c.occurred_at.desc(), t.c.id.desc()).limit(1)
    ).scalar()
    return last != "CANCELLATION"


def buyer_view(user_id: str) -> dict:
    """GET /api/league-pass: the caller's own pass, as its buyer.
    {pass: {league_id, platform, covered_until, will_renew,
    covered_count, can_repoint_at, show_buyer} | None, unbound}. `unbound`:
    the caller holds a live league product but no live pass (R19).
    covered_count counts covered members other than the buyer (R27).
    can_repoint_at is null when a re-point is allowed now."""
    allowance = _allowance()
    cooldown = _knob("league_pass_repoint_cooldown_days")
    with db.engine.begin() as conn:
        ids = _aliases(conn, user_id)
        buyer = _buyer_row(conn, user_id)
        current = _buyer_pass(conn, ids)
        until = _live_until(conn, current) if current is not None else None
        if until is None:
            return {"pass": None, "unbound": buyer is not None}
        covered = [m for m in _covered_ids(conn, current.league_id, current.platform, allowance)
                   if m not in ids]
        anchor = _cooldown_anchor(conn, ids)
        paying = _buyer_row(conn, current.buyer_user_id)   # live, so not None
        will_renew = paying is not None and _will_renew(conn, paying)
    ready = (datetime.fromisoformat(anchor) + timedelta(days=cooldown)) if anchor else None
    return {"pass": {"league_id": current.league_id, "platform": current.platform,
                     "covered_until": until, "will_renew": will_renew,
                     "covered_count": len(covered),
                     "can_repoint_at": ready.isoformat() if ready and ready > _now() else None,
                     "show_buyer": bool(current.show_buyer)},
            "unbound": False}


def set_show_buyer(user_id: str, show: bool) -> None:
    """The buyer's opt-in to be named to covered members (R28). Refuses:
    no_pass (no active pass bought by this user)."""
    t = db.league_passes_table
    with db.engine.begin() as conn:
        current = _buyer_pass(conn, _aliases(conn, user_id))
        if current is None:
            raise Refused("no_pass")
        conn.execute(update(t).where(t.c.id == current.id).values(
            show_buyer=1 if show else 0, updated_at=_now().isoformat()))


def list_passes(*, league_id: str | None = None, user_id: str | None = None) -> list[dict]:
    """Operator read (R39): every pass row, any status, for a league or for a
    buyer (any of their working keys), newest first, with `live_until` (null
    when not live now)."""
    t = db.league_passes_table
    with db.engine.begin() as conn:
        q = select(t).order_by(t.c.id.desc())
        if league_id is not None:
            q = q.where(t.c.league_id == league_id)
        if user_id is not None:
            ids = _aliases(conn, user_id)
            account_id = entitlements._account_for_user(conn, user_id)
            q = q.where(t.c.buyer_user_id.in_(ids) | (t.c.buyer_account_id == account_id)
                        if account_id else t.c.buyer_user_id.in_(ids))
        rows = conn.execute(q).fetchall()
        return [{**_pass_dict(r),
                 "live_until": _live_until(conn, r) if r.status == "active" else None}
                for r in rows]


def release_for_deletion(conn, user_ids, account_ids) -> dict[str, int]:
    """Account deletion (lld §2.4, R38), inside accounts' deletion
    transaction: the buyer's active pass is released ('deleted') and every
    pass row they bought loses its buyer ids. The league and dates stay
    as a non-personal record. Intents go with accounts._ADDITIONAL_PRIVATE_TABLES."""
    t = db.league_passes_table
    mine = t.c.buyer_user_id.in_(user_ids) | t.c.buyer_account_id.in_(account_ids)
    now = _now().isoformat()
    active = conn.execute(select(t.c.league_id).where(mine)
                          .where(t.c.status == "active")).scalars().all()
    released = conn.execute(update(t).where(mine).where(t.c.status == "active").values(
        status="released", released_at=now, release_reason="deleted", updated_at=now)).rowcount
    anonymized = conn.execute(update(t).where(mine).values(
        buyer_user_id=None, buyer_account_id=None, show_buyer=0, updated_at=now)).rowcount
    for league_id in active:
        _emit(None, "league_pass_ended", {"reason": "deleted"}, league_id, conn=conn)
    return {"league_passes_released": released or 0,
            "league_passes_anonymized": anonymized or 0}
