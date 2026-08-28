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
  * resolve_rc_identity() — RevenueCat `app_user_id` + `aliases[]` →
    the one working key we key entitlements on, so a purchase made before
    sign-in ($RCAnonymousID:*) merges into the acct_* row instead of
    stranding a second entitlement (iap-enablement scope §"In scope").

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


def _rc_candidates(app_user_id: str | None, aliases=None) -> list[str]:
    """Ordered, deduped candidate ids for one RevenueCat event.

    app_user_id first (the id the event was addressed to), then `aliases`
    in the order RevenueCat sent them. Non-strings and blanks are dropped —
    the aliases array is provider input, never trusted to be well-formed.
    """
    out: list[str] = []
    for cand in [app_user_id, *(aliases or [])]:
        if not isinstance(cand, str):
            continue
        cand = cand.strip()
        if cand and cand not in out:
            out.append(cand)
    return out


def _is_working_key(conn, candidate: str) -> bool:
    """True when this id is one we already key user state on: an acct_*
    whose account row exists, or a known sleeper_user_id."""
    if is_account_user_id(candidate):
        row = conn.execute(
            select(db.accounts_table.c.account_id)
            .where(db.accounts_table.c.account_id
                   == candidate[len(ACCOUNT_USER_PREFIX):])
        ).fetchone()
        return row is not None
    row = conn.execute(
        select(db.users_table.c.sleeper_user_id)
        .where(db.users_table.c.sleeper_user_id == candidate)
    ).fetchone()
    return row is not None


def resolve_rc_identity(app_user_id: str | None, aliases=None) -> str:
    """The canonical working key for a RevenueCat event.

    RevenueCat addresses each event to one `app_user_id` and carries every
    id it knows to be the same subscriber in `aliases`. A purchase made
    before sign-in arrives under `$RCAnonymousID:<uuid>`; once the app calls
    logIn(<working key>) the acct_* id shows up in that array. We take the
    first candidate that is a key we already recognise (app_user_id, then
    aliases in order), so the anonymous purchase reconciles to the account.

    Falls back to `app_user_id` verbatim when nothing is recognised —
    anonymous events are stored and projected under the anon key, which a
    later event re-keys (see _rekey_billing_rows). Dropping them instead
    would lose a real purchase.
    """
    candidates = _rc_candidates(app_user_id, aliases)
    if not candidates:
        return app_user_id or ""
    with db.engine.begin() as conn:
        for cand in candidates:
            if _is_working_key(conn, cand):
                return cand
    return candidates[0]


def _rekey_billing_rows(conn, canonical: str, from_ids, product_id: str | None,
                        *, active_only: bool = False) -> int:
    """Move billing-source entitlements rows from `from_ids` onto `canonical`.

    Surgical on purpose — the same rule the projector's upsert already
    follows: only `_BILLING_SOURCES` rows, and only this product_id when one
    is known. Manual grants and promo rewards written under an old id are
    never moved by billing traffic. Returns the number of rows moved.
    """
    stale = [i for i in from_ids if i and i != canonical]
    if not stale:
        return 0
    stmt = (update(db.entitlements_table)
            .where(db.entitlements_table.c.user_id.in_(stale))
            .where(db.entitlements_table.c.source.in_(_BILLING_SOURCES)))
    if product_id is not None:
        stmt = stmt.where(db.entitlements_table.c.product_id == product_id)
    if active_only:
        stmt = stmt.where(db.entitlements_table.c.status == "active")
    result = conn.execute(stmt.values(
        user_id=canonical,
        account_id=_account_for_user(conn, canonical),
        updated_at=_now(),
    ))
    return result.rowcount


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
# BILLING_ISSUE and TRANSFER are handled explicitly in _project (grace
# extension / entitlement move); both degrade to a stored no-op when the
# payload carries nothing actionable.
_RC_NOOP = {"CANCELLATION", "SUBSCRIBER_ALIAS", "TEST"}

# product_id → (entitlement, source). Season SKUs are year-labeled; the
# projector maps any ftf_season_pass_* to the season-scoped source.
#
# The ftf_* ids are canonical (00-platform-foundation.md §2.1/§4,
# pro-subscription/lld.md §3). The 2026-08-27 IAP runbook named divergent
# ASC ids (`founder_lifetime`, `season_pass_2026`, `pro_monthly_499`,
# `pro_annual_3499`); the conflict is recorded in
# docs/plans/monetization/iap-enablement/scope.md §"Surfaced conflict".
# The mapping is deliberately tolerant of the runbook spellings so either
# ASC choice reconciles to the right source without a code change — a
# mis-sourced founder row is a perpetual grant silently priced as a
# subscription.
def is_tip_product(product_id: str | None) -> bool:
    """Tip-jar consumables (`ftf_tip_*`) are money with NO entitlement.

    They arrive through the same webhook (RevenueCat sends consumables as
    NON_RENEWING_PURCHASE — an *activating* type), so without this guard the
    default `_product_mapping` branch would silently hand every tipper `pro`.
    The projector stores the event for the revenue ledger and grants nothing.
    """
    return (product_id or "").lower().startswith("ftf_tip_")


def _product_mapping(product_id: str) -> tuple[str, str]:
    pid = (product_id or "").lower()
    if pid.startswith("ftf_founder") or pid.startswith("founder_lifetime"):
        return "pro", "founder_iap"
    if (pid.startswith("ftf_season_pass") or pid.startswith("ftf_rookie_pass")
            or pid.startswith("season_pass_")):
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
                         occurred_at: str | None = None,
                         aliases=None) -> dict:
    """Store one webhook event (idempotent on event_id) and project it.

    Returns {'stored': bool, 'projected': bool, 'duplicate': bool}.
    Duplicates no-op entirely — provider retries are expected.

    `aliases` is RevenueCat's `event.aliases` array. When present the
    stored row and every projection are keyed to the canonical working key
    resolve_rc_identity() picks out of it, and rows written earlier under a
    sibling id are re-keyed onto it (foundation §2.1: one row per
    subscriber per product, bridged to the account).
    """
    candidates = _rc_candidates(user_id, aliases)
    if source == "revenuecat" and user_id:
        user_id = resolve_rc_identity(user_id, aliases)
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
                                user_id=user_id, product_id=product_id,
                                candidates=candidates)
    with db.engine.begin() as conn:
        conn.execute(
            update(db.subscription_events_table)
            .where(db.subscription_events_table.c.event_id == event_id)
            .values(processed_at=_now(), process_error=error)
        )
    return {"stored": True, "projected": projected, "duplicate": False}


def _project_transfer(event_id: str, payload: dict,
                      product_id: str | None) -> tuple[bool, str | None]:
    """TRANSFER — the subscription MOVED to another subscriber.

    RevenueCat carries the two sides in `transferred_from` / `transferred_to`
    arrays of app_user_ids, not in `app_user_id`. We project it as a move,
    not a deactivation: 'expired' would say the subscription lapsed and
    'revoked' would say we took it away, and both are false — the same paid
    period is simply now somebody else's. So the row is re-keyed onto the
    transferred-to working key (and its bound account_id), which leaves the
    ledger's `granted_by` pointing at this event for the audit trail.

    No active row on the from-side → stored with a process note; the
    to-side gets its entitlement from its own INITIAL_PURCHASE/RENEWAL.
    """
    to_ids = [i for i in (payload.get("transferred_to") or [])
              if isinstance(i, str) and i.strip()]
    from_ids = [i for i in (payload.get("transferred_from") or [])
                if isinstance(i, str) and i.strip()]
    if not to_ids or not from_ids:
        return False, "ignored: TRANSFER missing transferred_from/_to"

    canonical = resolve_rc_identity(to_ids[0], to_ids[1:])
    with db.engine.begin() as conn:
        moved = _rekey_billing_rows(conn, canonical, from_ids, product_id,
                                    active_only=True)
        if moved:
            conn.execute(
                update(db.entitlements_table)
                .where(db.entitlements_table.c.user_id == canonical)
                .where(db.entitlements_table.c.source.in_(_BILLING_SOURCES))
                .where(db.entitlements_table.c.status == "active")
                .values(granted_by=event_id, updated_at=_now())
            )
    if not moved:
        return False, "ignored: TRANSFER matched no active billing rows"
    return True, None


def _project_grace(event_id: str, payload: dict, user_id: str,
                   product_id: str) -> tuple[bool, str | None]:
    """BILLING_ISSUE — a renewal failed; the store may still be retrying.

    Access persists through the grace period (pro-subscription LLD §6: keep
    active until EXPIRATION), so the only thing to project is the new floor
    on `expires_at` when RevenueCat tells us one. Extends, never shortens,
    and never touches a perpetual row. No grace field → stored no-op.
    """
    grace = _ms_to_iso(payload.get("grace_period_expiration_at_ms"))
    if not grace:
        return False, None
    with db.engine.begin() as conn:
        row = conn.execute(
            select(db.entitlements_table.c.id, db.entitlements_table.c.expires_at)
            .where(db.entitlements_table.c.user_id == user_id)
            .where(db.entitlements_table.c.product_id == product_id)
            .where(db.entitlements_table.c.source.in_(_BILLING_SOURCES))
            .where(db.entitlements_table.c.status == "active")
        ).fetchone()
        if row is None:
            return False, "ignored: BILLING_ISSUE matched no active row"
        if row.expires_at is None or row.expires_at >= grace:
            return False, None
        conn.execute(
            update(db.entitlements_table)
            .where(db.entitlements_table.c.id == row.id)
            .values(expires_at=grace, granted_by=event_id, updated_at=_now())
        )
    return True, None


def _project(source: str, event_id: str, event_type: str, payload: dict, *,
             user_id: str | None, product_id: str | None,
             candidates=None) -> tuple[bool, str | None]:
    """Apply one billing event to entitlements. Upserts by
    (user_id, product_id) among billing-source rows only — promo and manual
    rows are never touched by billing traffic."""
    # TRANSFER carries its identities in payload arrays rather than
    # app_user_id, so it is handled ahead of the user_id guard below.
    if event_type == "TRANSFER":
        return _project_transfer(event_id, payload, product_id)

    if not user_id or not product_id:
        return False, "ignored: missing user_id/product_id"

    # Tips: ledger-only, before BOTH the activating and deactivating paths —
    # a tip REFUND has no entitlement row to touch either.
    if is_tip_product(product_id):
        return False, "tip: no entitlement (by design)"

    # Alias reconciliation. `user_id` is already the canonical key (resolved
    # in ingest_billing_event); anything else RevenueCat calls this
    # subscriber may still own rows written before the alias appeared, so
    # merge them onto the canonical key BEFORE the upsert looks for one.
    if candidates and len(candidates) > 1:
        with db.engine.begin() as conn:
            _rekey_billing_rows(conn, user_id, candidates, product_id)

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

    if event_type == "BILLING_ISSUE":
        return _project_grace(event_id, payload, user_id, product_id)

    if event_type in _RC_NOOP:
        return False, None
    return False, f"ignored: unhandled event_type {event_type!r}"
