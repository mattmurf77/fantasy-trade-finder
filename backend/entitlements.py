"""
entitlements.py — monetization platform foundation (entitlement service).

Implements docs/plans/monetization/00-platform-foundation.md §2–§4:

  * get_entitlements() — read-time resolution of who has 'pro' / 'ad_free',
    bridging the working key (sleeper id or acct_*) and the account layer so
    grants survive Sleeper re-links.
  * grant / revoke / list — the ONLY writers of entitlements rows besides
    the billing projector (manual-grant admin routes wrap these).
  * check_pro() — flag-aware gate used by server.py's @require_pro wrapper.
    monetize.entitlements OFF → allow (all users implicitly pro).
    ON without monetize.paywall → OBSERVE mode: log `ENTITLE-OBSERVE …
    would_block=…`, never block (foundation §2.4, mirrors the AUTH-GRACE
    rollout). Both ON → enforce (caller returns 402).
  * ingest_billing_event() — append-only subscription_events ledger with
    event_id idempotency, plus a minimal projector for the RevenueCat /
    Stripe event types the launch SKUs emit. Client receipts are never
    trusted; these webhooks are the only billing path into entitlements.

Everything here is dark by default: with all monetize.* flags false the
module only ever *logs*. Routes live in backend/server.py as thin wrappers;
everything stateful lives here so it is unit-testable without Flask.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, or_, select, update

from . import database as db
from .accounts import ACCOUNT_USER_PREFIX, is_account_user_id
from .feature_flags import is_enabled

# Entitlement values (docs/glossary.md). 'pro' unlocks the Pro gate list;
# 'ad_free' is the lightweight ads-only value (ads plan HLD §4).
ENTITLEMENTS = ("pro", "ad_free")

# Sources whose rows the projector may overwrite/expire. Manual grants and
# promo rewards are never touched by billing events.
_BILLING_SOURCES = ("apple_iap", "stripe", "founder_iap", "season_pass_iap", "trial")

VALID_SOURCES = _BILLING_SOURCES + (
    "promo_referral", "promo_group_unlock", "manual_grant", "rankset_purchase",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Identity resolution
# ---------------------------------------------------------------------------

def resolve_user(identifier: str) -> tuple[str | None, str | None]:
    """Resolve an operator-supplied identifier to (user_id, account_id).

    Accepts a sleeper_user_id, a Sleeper username, an acct_* working key,
    or a bare account_id. Returns (None, None) when nothing matches —
    callers surface that as a 404, never a silent grant to a typo.
    """
    ident = (identifier or "").strip()
    if not ident:
        return None, None

    with db.engine.begin() as conn:
        if is_account_user_id(ident):
            account_id = ident[len(ACCOUNT_USER_PREFIX):]
            row = conn.execute(
                select(db.accounts_table.c.account_id, db.accounts_table.c.sleeper_user_id)
                .where(db.accounts_table.c.account_id == account_id)
            ).fetchone()
            if row is None:
                return None, None
            return row.sleeper_user_id or ident, row.account_id

        # sleeper_user_id or username
        row = conn.execute(
            select(db.users_table.c.sleeper_user_id)
            .where(or_(db.users_table.c.sleeper_user_id == ident,
                       db.users_table.c.username == ident))
        ).fetchone()
        if row is not None:
            user_id = row.sleeper_user_id
            acct = conn.execute(
                select(db.accounts_table.c.account_id)
                .where(db.accounts_table.c.sleeper_user_id == user_id)
            ).fetchone()
            return user_id, (acct.account_id if acct else None)

        # bare account_id
        row = conn.execute(
            select(db.accounts_table.c.account_id, db.accounts_table.c.sleeper_user_id)
            .where(db.accounts_table.c.account_id == ident)
        ).fetchone()
        if row is not None:
            return row.sleeper_user_id or f"{ACCOUNT_USER_PREFIX}{row.account_id}", row.account_id

    return None, None


def _account_for_user(conn, user_id: str) -> str | None:
    """account_id bound to this working key, if any."""
    if is_account_user_id(user_id):
        return user_id[len(ACCOUNT_USER_PREFIX):]
    row = conn.execute(
        select(db.accounts_table.c.account_id)
        .where(db.accounts_table.c.sleeper_user_id == user_id)
    ).fetchone()
    return row.account_id if row else None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _active_rows(conn, user_id: str) -> list:
    account_id = _account_for_user(conn, user_id)
    id_match = [db.entitlements_table.c.user_id == user_id]
    if account_id:
        id_match.append(db.entitlements_table.c.account_id == account_id)
    now = _now()
    rows = conn.execute(
        select(db.entitlements_table)
        .where(or_(*id_match))
        .where(db.entitlements_table.c.status == "active")
    ).fetchall()
    # expires_at is read-time truth (ISO-8601 UTC strings compare lexically);
    # the hygiene cron stamping status='expired' is reporting-only.
    return [r for r in rows if r.expires_at is None or r.expires_at > now]


def get_entitlements(user_id: str) -> dict:
    """{'pro': bool, 'ad_free': bool, 'sources': [...], 'expires_at': ...}.

    ad_free is implied by pro (ads plan HLD §4). expires_at is the furthest
    expiry among active pro rows, null when any pro row is perpetual.
    """
    with db.engine.begin() as conn:
        rows = _active_rows(conn, user_id)

    pro_rows = [r for r in rows if r.entitlement == "pro"]
    ad_free_rows = [r for r in rows if r.entitlement == "ad_free"]
    pro = bool(pro_rows)

    expires_at: str | None = None
    if pro_rows and all(r.expires_at is not None for r in pro_rows):
        expires_at = max(r.expires_at for r in pro_rows)

    return {
        "pro": pro,
        "ad_free": pro or bool(ad_free_rows),
        "sources": sorted({r.source for r in rows}),
        "expires_at": expires_at,
    }


def check_pro(user_id: str, route: str, logger=None) -> bool:
    """Flag-aware gate. Returns True when the request may proceed.

    OFF → True. Observe (entitlements on, paywall off) → log + True.
    Enforce (both on) → resolution result.
    """
    if not is_enabled("monetize.entitlements"):
        return True
    has_pro = get_entitlements(user_id)["pro"]
    if not is_enabled("monetize.paywall"):
        if logger is not None:
            logger.info("ENTITLE-OBSERVE user=%s route=%s would_block=%s",
                        user_id, route, not has_pro)
        return True
    return has_pro


# ---------------------------------------------------------------------------
# Grants (manual + promo + projector writes)
# ---------------------------------------------------------------------------

def grant(user_id: str, entitlement: str, *,
          source: str,
          account_id: str | None = None,
          product_id: str | None = None,
          duration_days: int | None = None,
          expires_at: str | None = None,
          granted_by: str | None = None,
          note: str | None = None,
          metadata: dict | None = None) -> dict:
    """Insert an entitlements row. duration_days wins over expires_at;
    neither → perpetual. Returns the row as a dict."""
    if entitlement not in ENTITLEMENTS:
        raise ValueError(f"unknown entitlement {entitlement!r}")
    if source not in VALID_SOURCES:
        raise ValueError(f"unknown source {source!r}")
    now = _now()
    if duration_days is not None:
        expires_at = (datetime.now(timezone.utc)
                      + timedelta(days=duration_days)).isoformat()
    with db.engine.begin() as conn:
        if account_id is None:
            account_id = _account_for_user(conn, user_id)
        result = conn.execute(insert(db.entitlements_table).values(
            user_id=user_id, account_id=account_id, entitlement=entitlement,
            source=source, product_id=product_id, status="active",
            starts_at=now, expires_at=expires_at, granted_by=granted_by,
            note=note, metadata=json.dumps(metadata) if metadata else None,
            created_at=now, updated_at=now,
        ))
        row_id = result.inserted_primary_key[0]
    db.record_event(user_id, "entitlement_granted",
                    props={"entitlement": entitlement, "source": source,
                           "expires_at": expires_at})
    return {"id": row_id, "user_id": user_id, "account_id": account_id,
            "entitlement": entitlement, "source": source,
            "product_id": product_id, "status": "active",
            "starts_at": now, "expires_at": expires_at}


def revoke(entitlement_id: int) -> bool:
    """status='revoked' — audit-preserving, never hard-deletes."""
    with db.engine.begin() as conn:
        result = conn.execute(
            update(db.entitlements_table)
            .where(db.entitlements_table.c.id == entitlement_id)
            .values(status="revoked", updated_at=_now())
        )
    return result.rowcount > 0


def list_for_user(user_id: str) -> list[dict]:
    """All rows (any status) for support/readback."""
    with db.engine.begin() as conn:
        account_id = _account_for_user(conn, user_id)
        id_match = [db.entitlements_table.c.user_id == user_id]
        if account_id:
            id_match.append(db.entitlements_table.c.account_id == account_id)
        rows = conn.execute(
            select(db.entitlements_table).where(or_(*id_match))
            .order_by(db.entitlements_table.c.id)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# Billing ingestion + projector
# ---------------------------------------------------------------------------

# RevenueCat event types the projector understands. Everything else is
# stored + consciously skipped (processed with process_error note).
_RC_ACTIVATING = {"INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION",
                  "NON_RENEWING_PURCHASE", "PRODUCT_CHANGE"}
_RC_DEACTIVATING = {"EXPIRATION": "expired", "REFUND": "refunded"}
# CANCELLATION = auto-renew toggled off; access runs to expiry — no-op.
_RC_NOOP = {"CANCELLATION", "BILLING_ISSUE", "SUBSCRIBER_ALIAS", "TEST"}

# product_id → (entitlement, source). Season SKUs are year-labeled; the
# projector maps any ftf_season_pass_* to the season-scoped source.
def _product_mapping(product_id: str) -> tuple[str, str]:
    pid = (product_id or "").lower()
    if pid.startswith("ftf_founder"):
        return "pro", "founder_iap"
    if pid.startswith("ftf_season_pass") or pid.startswith("ftf_rookie_pass"):
        return "pro", "season_pass_iap"
    return "pro", "apple_iap"


def _ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc).isoformat()


def ingest_billing_event(source: str, event_id: str, event_type: str,
                         payload: dict, *,
                         user_id: str | None = None,
                         product_id: str | None = None,
                         occurred_at: str | None = None) -> dict:
    """Store one webhook event (idempotent on event_id) and project it.

    Returns {'stored': bool, 'projected': bool, 'duplicate': bool}.
    Duplicates no-op entirely — provider retries are expected.
    """
    now = _now()
    with db.engine.begin() as conn:
        dup = conn.execute(
            select(db.subscription_events_table.c.id)
            .where(db.subscription_events_table.c.event_id == event_id)
        ).fetchone()
        if dup is not None:
            return {"stored": False, "projected": False, "duplicate": True}
        conn.execute(insert(db.subscription_events_table).values(
            source=source, event_type=event_type, user_id=user_id,
            account_id=None, product_id=product_id, event_id=event_id,
            payload=json.dumps(payload), occurred_at=occurred_at or now,
        ))

    projected, error = _project(source, event_id, event_type, payload,
                                user_id=user_id, product_id=product_id)
    with db.engine.begin() as conn:
        conn.execute(
            update(db.subscription_events_table)
            .where(db.subscription_events_table.c.event_id == event_id)
            .values(processed_at=_now(), process_error=error)
        )
    return {"stored": True, "projected": projected, "duplicate": False}


def _project(source: str, event_id: str, event_type: str, payload: dict, *,
             user_id: str | None, product_id: str | None) -> tuple[bool, str | None]:
    """Apply one billing event to entitlements. Upserts by
    (user_id, product_id) among billing-source rows only — promo and manual
    rows are never touched by billing traffic."""
    if not user_id or not product_id:
        return False, "ignored: missing user_id/product_id"

    entitlement, mapped_source = _product_mapping(product_id)
    expires_at = _ms_to_iso(payload.get("expiration_at_ms"))

    if event_type in _RC_ACTIVATING or event_type in (
            "checkout.session.completed", "customer.subscription.updated",
            "invoice.paid"):
        src = "stripe" if source == "stripe" else mapped_source
        with db.engine.begin() as conn:
            existing = conn.execute(
                select(db.entitlements_table.c.id)
                .where(db.entitlements_table.c.user_id == user_id)
                .where(db.entitlements_table.c.product_id == product_id)
                .where(db.entitlements_table.c.source.in_(_BILLING_SOURCES))
            ).fetchone()
            if existing is not None:
                conn.execute(
                    update(db.entitlements_table)
                    .where(db.entitlements_table.c.id == existing.id)
                    .values(status="active", expires_at=expires_at,
                            granted_by=event_id, updated_at=_now())
                )
                return True, None
        grant(user_id, entitlement, source=src, product_id=product_id,
              expires_at=expires_at, granted_by=event_id)
        return True, None

    deactivate_status = _RC_DEACTIVATING.get(event_type) or {
        "customer.subscription.deleted": "expired",
        "charge.refunded": "refunded",
    }.get(event_type)
    if deactivate_status:
        with db.engine.begin() as conn:
            conn.execute(
                update(db.entitlements_table)
                .where(db.entitlements_table.c.user_id == user_id)
                .where(db.entitlements_table.c.product_id == product_id)
                .where(db.entitlements_table.c.source.in_(_BILLING_SOURCES))
                .values(status=deactivate_status, granted_by=event_id,
                        updated_at=_now())
            )
        return True, None

    if event_type in _RC_NOOP:
        return False, None
    return False, f"ignored: unhandled event_type {event_type!r}"
