"""
accounts.py — identity-provider anchors + account lifecycle (account-auth P2).

Implements the identity layer from docs/plans/account-auth-plan-2026-07-11.md
§3-P2 on top of the app's working key (`sleeper_user_id`):

  * Apple / Google identity-token verification against the provider JWKS
    (RS256 signature + iss + aud + exp). No third-party JWT library — the
    already-required `cryptography` package does the RSA verify; the JWT
    envelope parsing is ~30 lines here.
  * accounts / linked_identities find-or-create + sticky Sleeper binding.
  * Verified-session persistence (users.verified_at / verified_via) shared
    with P1's Sleeper-JWT proof.
  * delete_user_data() — the in-app account-deletion matrix required by
    App Store Guideline 5.1.1(v); table-by-table behavior documented inline
    and in docs/api-reference.md (DELETE /api/account).

Routes live in backend/server.py as thin wrappers; everything stateful or
crypto-shaped lives here so it is unit-testable without Flask.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import ssl
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import delete, insert, or_, select, update

from . import database as db
from . import user_data_lifecycle

# ---------------------------------------------------------------------------
# Provider constants
# ---------------------------------------------------------------------------

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"
# The iOS app's bundle id — Apple identity tokens minted by the native
# Sign in with Apple sheet carry it as `aud`. Overridable for test builds.
APPLE_AUDIENCE = "com.fantasytradefinder.app"

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
# Google historically emits both forms of iss.
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

PROVIDERS = ("apple", "google")

# Tombstone written into shared rows (trade_matches) when one side deletes
# their account — keeps the counterparty's record intact without retaining
# the deleted user's key. Mirrored in docs/glossary.md.
DELETED_USER_PLACEHOLDER = "deleted_user"

# ── Account-first working key (P2.6) ────────────────────────────────────────
# An account with no linked Sleeper source still needs a working key for the
# engine (every user-keyed table treats user_id as opaque). The synthetic
# namespaced key acct_<account_id> cannot collide with Sleeper's numeric ids;
# precedent for synthetic ids in the same keyspace: demo_user_*, test_user_fp_*.
ACCOUNT_USER_PREFIX = "acct_"


def account_user_id(account_id: str) -> str:
    """Working key for an account with no linked Sleeper source."""
    return f"{ACCOUNT_USER_PREFIX}{account_id}"


def is_account_user_id(user_id: str | None) -> bool:
    return bool(user_id) and str(user_id).startswith(ACCOUNT_USER_PREFIX)

_JWKS_TTL_SECONDS = 6 * 3600
_CLOCK_LEEWAY_SECONDS = 60


class TokenVerificationError(Exception):
    """Identity-token rejected. `reason` is a stable machine string."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        super().__init__(f"{reason}{': ' + detail if detail else ''}")


# ---------------------------------------------------------------------------
# JWKS fetch + cache
# ---------------------------------------------------------------------------

_jwks_cache: dict[str, tuple[float, list[dict]]] = {}  # url → (fetched_at, keys)
_jwks_lock = threading.Lock()


def _fetch_jwks(url: str) -> list[dict]:
    """Network fetch of a provider JWKS. Monkeypatched in tests."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    # obs.api_events — Apple/Google sign-in verification egress. Public keys
    # only; no credential ever flows through this call.
    from . import api_observability as _api_obs
    _service = "apple" if "apple.com" in url else "google"
    with _api_obs.observe_call(_service, "jwks") as _ob:
        with urllib.request.urlopen(req, timeout=10,
                                    context=ssl.create_default_context()) as resp:
            raw = resp.read().decode("utf-8")
        body = json.loads(raw)
        keys = body.get("keys")
        if not isinstance(keys, list):
            raise TokenVerificationError("jwks_unavailable", f"malformed JWKS from {url}")
        _ob.ok(status=getattr(resp, "status", 200), response_bytes=len(raw))
    return keys


def _get_jwks(url: str, *, force_refresh: bool = False) -> list[dict]:
    now = time.time()
    with _jwks_lock:
        cached = _jwks_cache.get(url)
        if cached and not force_refresh and now - cached[0] < _JWKS_TTL_SECONDS:
            return cached[1]
    keys = _fetch_jwks(url)
    with _jwks_lock:
        _jwks_cache[url] = (now, keys)
    return keys


# ---------------------------------------------------------------------------
# JWT envelope + RS256 verification (via `cryptography`, no PyJWT)
# ---------------------------------------------------------------------------

def _b64url_decode(seg: str) -> bytes:
    pad = "=" * (-len(seg) % 4)
    import base64
    return base64.urlsafe_b64decode(seg + pad)


def _b64url_uint(seg: str) -> int:
    return int.from_bytes(_b64url_decode(seg), "big")


def _rsa_public_key(jwk: dict):
    numbers = rsa.RSAPublicNumbers(
        e=_b64url_uint(jwk["e"]),
        n=_b64url_uint(jwk["n"]),
    )
    return numbers.public_key()


def verify_identity_token(
    token: str,
    *,
    jwks_url: str,
    issuers: tuple[str, ...],
    audiences: tuple[str, ...],
    leeway: int = _CLOCK_LEEWAY_SECONDS,
) -> dict:
    """Verify an RS256 identity token against a provider JWKS.

    Checks, in order: envelope shape → alg → signature (key looked up by
    `kid`; one forced JWKS refresh on a miss so a provider key rotation
    doesn't strand us for the cache TTL) → iss → aud → exp.

    Returns the verified claims dict; raises TokenVerificationError.
    """
    parts = (token or "").split(".")
    if len(parts) != 3 or not all(parts):
        raise TokenVerificationError("malformed_token")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        claims = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except Exception:
        raise TokenVerificationError("malformed_token")

    if header.get("alg") != "RS256":
        raise TokenVerificationError("bad_alg", str(header.get("alg")))

    kid = header.get("kid")
    keys = _get_jwks(jwks_url)
    jwk = next((k for k in keys if k.get("kid") == kid), None)
    if jwk is None:
        # Key rotation — refetch once before giving up.
        keys = _get_jwks(jwks_url, force_refresh=True)
        jwk = next((k for k in keys if k.get("kid") == kid), None)
    if jwk is None:
        raise TokenVerificationError("unknown_kid", str(kid))

    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    try:
        _rsa_public_key(jwk).verify(
            signature, signing_input, padding.PKCS1v15(), hashes.SHA256()
        )
    except Exception:
        raise TokenVerificationError("bad_signature")

    if claims.get("iss") not in issuers:
        raise TokenVerificationError("wrong_issuer", str(claims.get("iss")))

    aud = claims.get("aud")
    aud_list = aud if isinstance(aud, list) else [aud]
    if not any(a in audiences for a in aud_list):
        raise TokenVerificationError("wrong_audience", str(aud))

    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or exp < time.time() - leeway:
        raise TokenVerificationError("expired")

    return claims


def verify_apple_token(token: str) -> dict:
    """Verify a Sign in with Apple identity token → claims."""
    return verify_identity_token(
        token,
        jwks_url=APPLE_JWKS_URL,
        issuers=(APPLE_ISSUER,),
        audiences=(APPLE_AUDIENCE,),
    )


def verify_google_token(token: str, client_id: str) -> dict:
    """Verify a Google ID token → claims. `client_id` is the OAuth client id."""
    return verify_identity_token(
        token,
        jwks_url=GOOGLE_JWKS_URL,
        issuers=GOOGLE_ISSUERS,
        audiences=(client_id,),
    )


def hash_email(email: str | None) -> str | None:
    """SHA-256 hex of a normalized email — the raw address is never stored."""
    if not email:
        return None
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Account find-or-create + Sleeper binding
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _email_capture_enabled() -> bool:
    """Flag gate for plaintext email storage (2026-07-17 email-capture spec).

    Lazy import + swallow: a flags problem must never break sign-in. Off →
    only the hash is kept, exactly the pre-spec behavior.
    """
    try:
        from .feature_flags import is_enabled
        return bool(is_enabled("auth.email_capture"))
    except Exception:
        return False


def _normalize_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.strip().lower() or None


def set_account_email(account_id: str, email: str | None,
                      source: str = "user") -> bool:
    """Store/refresh an account's email with a fresh consent stamp.

    The capture UI's backend entry point (and the Apple first-auth path).
    No-ops (returns False) when the flag is off or the email is invalid.
    """
    email = _normalize_email(email)
    if not email or not _email_capture_enabled():
        return False
    with db.engine.begin() as conn:
        res = conn.execute(
            update(db.accounts_table)
            .where(db.accounts_table.c.account_id == account_id)
            .values(email=email, email_source=source,
                    email_consent_at=_now_iso())
        )
        return res.rowcount > 0


def find_or_create_account(provider: str, provider_subject: str,
                           email_hash: str | None = None,
                           email: str | None = None) -> dict:
    """Return the account owning (provider, subject), creating both the
    account and the identity row on first sight.

    `email`: plaintext from the provider (Apple sends it on first auth only).
    Stored on the accounts row only when `auth.email_capture` is enabled —
    otherwise discarded after hashing, the pre-spec behavior.

    Returns {account_id, sleeper_user_id, created_at, created: bool}.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}")
    email = _normalize_email(email) if _email_capture_enabled() else None
    with db.engine.begin() as conn:
        ident = conn.execute(
            select(db.linked_identities_table).where(
                (db.linked_identities_table.c.provider == provider)
                & (db.linked_identities_table.c.provider_subject == provider_subject)
            )
        ).fetchone()
        if ident is not None:
            acct = conn.execute(
                select(db.accounts_table).where(
                    db.accounts_table.c.account_id == ident.account_id
                )
            ).fetchone()
            if acct is not None:
                # Backfill email_hash if we learned it later (Apple sends
                # email only on first authorization — usually already set).
                if email_hash and not ident.email_hash:
                    conn.execute(
                        update(db.linked_identities_table)
                        .where(db.linked_identities_table.c.id == ident.id)
                        .values(email_hash=email_hash)
                    )
                # Backfill plaintext email (flag-gated above) if the account
                # doesn't have one yet — never overwrite a user-entered one.
                if email and not acct.email:
                    conn.execute(
                        update(db.accounts_table)
                        .where(db.accounts_table.c.account_id == acct.account_id)
                        .values(email=email, email_source=provider,
                                email_consent_at=_now_iso())
                    )
                return {
                    "account_id": acct.account_id,
                    "sleeper_user_id": acct.sleeper_user_id,
                    "created_at": acct.created_at,
                    "created": False,
                }
            # Orphaned identity (account row lost) — fall through and rebuild.
            conn.execute(
                delete(db.linked_identities_table).where(
                    db.linked_identities_table.c.id == ident.id
                )
            )
        account_id = secrets.token_hex(16)
        now = _now_iso()
        conn.execute(insert(db.accounts_table).values(
            account_id=account_id, sleeper_user_id=None, created_at=now,
            email=email, email_source=(provider if email else None),
            email_consent_at=(now if email else None),
        ))
        conn.execute(insert(db.linked_identities_table).values(
            account_id=account_id, provider=provider,
            provider_subject=provider_subject, email_hash=email_hash,
            linked_at=now,
        ))
        return {"account_id": account_id, "sleeper_user_id": None,
                "created_at": now, "created": True}


def bind_sleeper_user(account_id: str, sleeper_user_id: str) -> dict:
    """Bind an account to a sleeper_user_id. Binding is STICKY:

      * unbound account          → binds; returns bound=sleeper_user_id
      * already bound, same id   → no-op
      * already bound, other id  → NOT rebound (returns the existing binding
        with conflict=True). The provider identity is the durable anchor —
        a later username-only session must not steal it. Rebinding requires
        deleting the account first (DELETE /api/account).

    Returns {sleeper_user_id, conflict: bool}.
    """
    with db.engine.begin() as conn:
        acct = conn.execute(
            select(db.accounts_table).where(
                db.accounts_table.c.account_id == account_id
            )
        ).fetchone()
        if acct is None:
            raise ValueError(f"no such account {account_id!r}")
        if acct.sleeper_user_id is None:
            conn.execute(
                update(db.accounts_table)
                .where(db.accounts_table.c.account_id == account_id)
                .values(sleeper_user_id=sleeper_user_id)
            )
            return {"sleeper_user_id": sleeper_user_id, "conflict": False}
        if acct.sleeper_user_id == sleeper_user_id:
            return {"sleeper_user_id": sleeper_user_id, "conflict": False}
        return {"sleeper_user_id": acct.sleeper_user_id, "conflict": True}


def get_account(account_id: str) -> dict | None:
    """Account + linked identities, or None."""
    with db.engine.connect() as conn:
        acct = conn.execute(
            select(db.accounts_table).where(
                db.accounts_table.c.account_id == account_id
            )
        ).fetchone()
        if acct is None:
            return None
        idents = conn.execute(
            select(db.linked_identities_table).where(
                db.linked_identities_table.c.account_id == account_id
            )
        ).fetchall()
    return {
        "account_id": acct.account_id,
        "sleeper_user_id": acct.sleeper_user_id,
        "created_at": acct.created_at,
        "identities": [
            {"provider": i.provider, "linked_at": i.linked_at}
            for i in idents
        ],
    }


def get_account_for_user(sleeper_user_id: str) -> dict | None:
    """Account bound to a sleeper_user_id (with identities), or None."""
    with db.engine.connect() as conn:
        acct = conn.execute(
            select(db.accounts_table).where(
                db.accounts_table.c.sleeper_user_id == sleeper_user_id
            )
        ).fetchone()
    if acct is None:
        return None
    return get_account(acct.account_id)


def mark_user_verified(sleeper_user_id: str, via: str) -> None:
    """Persist the verified marker on the users row (P1/P2 shared columns)."""
    with db.engine.begin() as conn:
        conn.execute(
            update(db.users_table)
            .where(db.users_table.c.sleeper_user_id == sleeper_user_id)
            .values(verified_at=_now_iso(), verified_via=via)
        )


def get_user_verified_via(sleeper_user_id: str) -> str | None:
    with db.engine.connect() as conn:
        row = conn.execute(
            select(db.users_table.c.verified_via).where(
                db.users_table.c.sleeper_user_id == sleeper_user_id
            )
        ).fetchone()
    return row.verified_via if row else None


def get_user_profile(sleeper_user_id: str) -> dict | None:
    """username / display_name / avatar snapshot for session restore."""
    with db.engine.connect() as conn:
        row = conn.execute(
            select(
                db.users_table.c.username,
                db.users_table.c.display_name,
                db.users_table.c.avatar,
            ).where(db.users_table.c.sleeper_user_id == sleeper_user_id)
        ).fetchone()
    if row is None:
        return None
    return {"username": row.username, "display_name": row.display_name,
            "avatar": row.avatar}


# ---------------------------------------------------------------------------
# Board data — merge support for link-sleeper (P2.6)
# ---------------------------------------------------------------------------
# "Board data" = the user-authored ranking artifacts a merge must not lose:
# swipe history + the users-row board columns (tiers_saved, tier_overrides,
# ranking_method, anchor_scale, unlocked_formats). Mirrors the scope of
# database.reset_user_rankings (the shipped explicit-consent wipe).

_USERS_BOARD_COLUMNS = ("tiers_saved", "tier_overrides", "ranking_method",
                        "anchor_scale", "unlocked_formats")


def board_data_summary(user_id: str) -> dict:
    """Counts/flags of a user's board data, for the merge-choice response.

    Returns {swipes, tiers_saved, tier_overrides, ranking_method,
             anchor_scale, any}.
    """
    from sqlalchemy import func
    with db.engine.connect() as conn:
        swipes = conn.execute(
            select(func.count()).select_from(db.swipe_decisions_table).where(
                db.swipe_decisions_table.c.user_id == user_id
            )
        ).scalar() or 0
        row = conn.execute(
            select(
                db.users_table.c.tiers_saved,
                db.users_table.c.tier_overrides,
                db.users_table.c.ranking_method,
                db.users_table.c.anchor_scale,
            ).where(db.users_table.c.sleeper_user_id == user_id)
        ).fetchone()
    out = {
        "swipes":          int(swipes),
        "tiers_saved":     bool(row and row.tiers_saved),
        "tier_overrides":  bool(row and row.tier_overrides),
        "ranking_method":  (row.ranking_method if row else None),
        "anchor_scale":    bool(row and row.anchor_scale),
    }
    out["any"] = bool(out["swipes"] or out["tiers_saved"] or out["tier_overrides"]
                      or out["ranking_method"] or out["anchor_scale"])
    return out


def migrate_board_data(from_uid: str, to_uid: str) -> dict[str, int]:
    """Re-key board data from one working key to another (link-sleeper merge).

    Caller guarantees the destination board is empty or explicitly wiped —
    users-row board columns are copied where the SOURCE value is non-null.
    Re-keys swipe_decisions / elo_history / user_player_skips; deletes the
    source's member_rankings (they reference the account sentinel league and
    are meaningless under the destination key) and the source users row.
    Notifications / device tokens / events stay behind by design (push
    re-registers on next launch under the new key).
    """
    counts: dict[str, int] = {}
    with db.engine.begin() as conn:
        for name, tbl in (("swipe_decisions", db.swipe_decisions_table),
                          ("elo_history", db.elo_history_table),
                          ("user_player_skips", db.user_player_skips_table)):
            res = conn.execute(
                update(tbl).where(tbl.c.user_id == from_uid)
                .values(user_id=to_uid)
            )
            counts[f"{name}_moved"] = res.rowcount or 0

        res = conn.execute(
            delete(db.member_rankings_table).where(
                db.member_rankings_table.c.user_id == from_uid
            )
        )
        counts["member_rankings_dropped"] = res.rowcount or 0

        src = conn.execute(
            select(db.users_table).where(
                db.users_table.c.sleeper_user_id == from_uid
            )
        ).fetchone()
        if src is not None:
            board_values = {
                col: getattr(src, col)
                for col in _USERS_BOARD_COLUMNS
                if getattr(src, col) is not None
            }
            if board_values:
                dest = conn.execute(
                    select(db.users_table.c.sleeper_user_id).where(
                        db.users_table.c.sleeper_user_id == to_uid
                    )
                ).fetchone()
                if dest is None:
                    conn.execute(insert(db.users_table).values(
                        sleeper_user_id=to_uid, created_at=_now_iso(),
                        **board_values,
                    ))
                else:
                    conn.execute(
                        update(db.users_table)
                        .where(db.users_table.c.sleeper_user_id == to_uid)
                        .values(**board_values)
                    )
            counts["users_board_columns_copied"] = len(board_values)
            conn.execute(
                delete(db.users_table).where(
                    db.users_table.c.sleeper_user_id == from_uid
                )
            )
    return counts


# ---------------------------------------------------------------------------
# Account deletion (App Store 5.1.1(v)) — the deletion matrix
# ---------------------------------------------------------------------------
#
# Honors web/privacy.html §6 ("remove your user record, rankings, comparison
# history, activity events, push tokens, and any stored Sleeper connection
# token") and goes further where rows are user-keyed. Counterparty-safe:
# rows that are one side of a SHARED record (trade matches, other users'
# impressions/flags that reference this user) are anonymized in place so the
# other manager's history stays intact.
#
#   DELETE   users, swipe_decisions, trade_decisions, member_rankings,
#            elo_history, league_preferences, asset_preferences,
#            user_player_skips, notifications, device_tokens,
#            notification_prefs, notification_events_log, notification_queue,
#            user_events, wrapped_events, sleeper_credentials,
#            league_members (own row), leagues (rows this user synced —
#            recreated from Sleeper's public API by any member's next
#            session_init), bad_trade_flags (own flags — dedupe_key embeds
#            the user id, so anonymizing in place would still retain it),
#            trade_impressions (own decks), accounts + linked_identities.
#
#   ANONYMIZE (counterparty-safe)
#            trade_matches — the deleted side's user id is replaced with
#            DELETED_USER_PLACEHOLDER; status/decisions stay so the other
#            manager's match history is intact.
#            trade_impressions.target_user_id → NULL where it names this
#            user (the row belongs to the OTHER user's deck).
#            bad_trade_flags.target_user_id/target_username → NULL where the
#            deleted user was the counterparty on someone else's flag.
#            app_feedback.user_id/username → NULL (feedback is retained as a
#            product record per privacy policy §5; submitted freeform text
#            is removed because it can itself contain personal identifiers).
#
#   ALSO DELETE newer private tables in _ADDITIONAL_PRIVATE_TABLES,
#            durable sessions, account-linked billing (including raw payloads),
#            own deck impressions/outcomes (outcomes also by their own
#            user_id, G3-e), identity links, linked anonymous
#            device events/assignments, private ranking sets/entries, and
#            trade_share_tokens the user minted (created_by).
#            Resolve acct_<account_id> aliases before removing identity rows.
#   ALSO ANONYMIZE shared packages, public ranking authors, referral sides,
#            affiliate attribution, recorded-pick authors, trade-block owners,
#            strong roster-history owners and suggestion impression links.
#            Weak user-keyed roster history is deleted. Other identified
#            users' events/identity links on a shared device are preserved.
#            Platform pick grids (draft_picks.platform set and not 'sleeper',
#            i.e. MFL/ESPN): owner_user_id / original_user_id → the
#            DELETED_USER_PLACEHOLDER where they name a deleted id, and that
#            side's owner_username / original_username → "Team <slot>" (the
#            writers' own fallback; the placeholder if no slot is known). There
#            the importer's own picks carry their FLEECED id (entry:*, acct_*;
#            server._sync_mfl_owned_picks) and their name, and nothing re-syncs
#            the grid once they are gone. The row itself stays: other members
#            rely on it.
#            recorded_picks.picking_team_id → the placeholder where it is a
#            deleted Fleeced-minted id (entry:*, acct_*; no platform column).
#            pick_assignment_changed events (OTHER users'): old_owner /
#            new_owner / actor → the placeholder where they are a deleted
#            Fleeced-minted id; the audit trail stays readable.
#            leagues.pick_assignment_settings.order (any row, incl. other
#            importers'): a deleted Fleeced-minted id → the placeholder in
#            place, so other owners' slot positions don't shift.
#            Team overhaul: own overhauls (account_user_id) are deleted with
#            their offers, roadmaps, attempts and reservations. In OTHER
#            users' overhauls an offer naming this user (or their league
#            member id) keeps its package and history; its counterparty id and
#            name, and the card's target id and name, → the placeholder; the
#            card loses the counterparty's Fleeced-derived fields; its
#            evidence_json → NULL; a liked or undecided one goes stale, and
#            an undecided one's package_hash is re-minted. Those overhauls'
#            roadmap summaries list the placeholder instead, and a
#            Fleeced-minted id (entry:*, acct_*) keying their snapshot
#            rosters or holding their recovery pick → the placeholder.
#   KEEP     player_value_history + model_config (not user-keyed),
#            draft_picks on Sleeper grids (and legacy rows with no platform),
#            ids and usernames alike, and recorded_picks.picking_team_id
#            holding a Sleeper id: public Sleeper data other members rely on,
#            re-synced from Sleeper. Platform grids keep the row, never the
#            deleted person's id or name (ANONYMIZE above). players.
# ---------------------------------------------------------------------------

def _user_data_scope(conn, user_id: str, account_id: str | None = None):
    """Resolve account aliases, never other users linked through a shared device."""
    acct_ids = set(conn.execute(select(db.accounts_table.c.account_id).where(
        db.accounts_table.c.sleeper_user_id == user_id)).scalars())
    if account_id:
        acct_ids.add(account_id)
    if is_account_user_id(user_id):
        acct_ids.add(user_id[len(ACCOUNT_USER_PREFIX):])
    user_ids = {user_id} | {account_user_id(aid) for aid in acct_ids}
    user_ids.update(uid for uid in conn.execute(
        select(db.accounts_table.c.sleeper_user_id).where(
            db.accounts_table.c.account_id.in_(acct_ids))).scalars() if uid)
    # Durable sessions also record historical working keys. Resolve these
    # before revocation so their private rows cannot outlive the account.
    user_ids.update(conn.execute(select(db.sessions_table.c.user_id).where(
        db.sessions_table.c.account_id.in_(acct_ids))).scalars())
    return user_ids, acct_ids


# Additional private rows introduced after the original deletion matrix.
# Billing payloads are deleted too: nulling their keys leaves identity in JSON.
_ADDITIONAL_PRIVATE_TABLES = (
    "espn_credentials", "mfl_credentials", "deck_candidate_sets", "bakeoff_runs",
    "deck_suppressions", "deck_fatigue_resets", "deck_replenish_log", "user_taste",
    "trade_pass_reasons", "standing_offers", "league_board_history",
    "rank_set_adoptions", "accuracy_scores", "mock_drafts", "receipts_grades",
    "trade_proposals", "trade_policy_shadow", "deck_diagnostic_snapshots",
    "grading_sessions", "grading_cards", "trade_page_store", "trade_deck_lineage",
    "deck_card_withdrawals", "deck_evidence_packs",
)

# Team overhaul (BUILD-CONTRACT §4) keys its owner as `account_user_id`, and
# the rest by `overhaul_id`, so none of it fits the user_id loop above.
_OVERHAUL_CHILD_TABLES = ("overhaul_offers", "overhaul_roadmaps", "overhaul_attempts",
                          "overhaul_reservations")
# Public-card fields drawn from the counterparty's own Fleeced account (legal
# R28.20 c2; trade_card_to_dict): the generators' reasons (the bilateral arm's
# says whether the other manager has preferences), and the deck-card fields
# the shared serializer can carry.
_OVERHAUL_CARD_PARTNER_KEYS = ("reasons", "likes_you", "standing_offer_reason", "breaker",
                               "fit", "roster_evaluation", "rationale", "narrative")


def _overhaul_card_without_partner_fields(card: dict) -> dict:
    """An overhaul offer's public card minus the counterparty's Fleeced-derived
    fields: the keys above, and match_context's `counterparty*` keys (the owner
    arms' benefits and preference evidence) and `opponent_outlook` (the
    narrative arms', which can be the partner's declared outlook)."""
    out = {k: v for k, v in card.items() if k not in _OVERHAUL_CARD_PARTNER_KEYS}
    if isinstance(out.get("match_context"), dict):
        out["match_context"] = {k: v for k, v in out["match_context"].items()
                                if not k.startswith("counterparty") and k != "opponent_outlook"}
    return out


# A scrubbed card's id and name, and its blended scalars under legal's test
# (R28.22 b, b2; every card of the partner alike). On the owner arms
# `mismatch_score` (the deck's surplus_margin) and `composite_score` (its
# base_score) are the same number, the card's presentation rank
# (trade_gen_owner.py:649-650, trade_gen_bilateral.py:517): surplus_margin is
# nulled, so its copy goes with it. `fit` (and fit.aggregate) is already
# dropped above; no final_score is stored on an overhaul card.
_OVERHAUL_REDACTED_CARD_VALUES = {"target_user_id": DELETED_USER_PLACEHOLDER,
                                  "target_username": DELETED_USER_PLACEHOLDER,
                                  "mismatch_score": None, "composite_score": None}


# A users row created this long after an overhaul is a new account under a
# reused id (deleted before overhauls were covered, then signed up again),
# not the overhaul's owner. The margin covers session_init's users-row write,
# which runs in a background thread after its response (server.py:27838-27920).
_OVERHAUL_RESIGNUP_MARGIN = timedelta(hours=1)


def delete_orphaned_overhauls() -> dict[str, int]:
    """Legal R28.22 d2: overhauls whose owner account no longer exists (deleted,
    or purged as an entry user, before deletion covered overhauls) go with every
    row under them, and so do child rows whose overhaul is already gone.

    An owner is live while ANY of these names their account_user_id: a users
    row, a durable session row (the strongest signal: a signed-in user's
    session/init can return before its background users-row write lands), or an
    accounts row (as the acct_ alias, or as the bound Sleeper id:
    migrate_board_data deletes the from-id's users row on a bind). Deletion
    removes all of them. An overhaul is also orphaned when its owner's users row
    was created more than _OVERHAUL_RESIGNUP_MARGIN after it (release-lead #540
    QA P2-2), unless a durable session or accounts row for that owner is no
    newer than the overhaul: that owner was live when they made it (a users
    row can land late when its best-effort writes fail; QA re-QA P3). Deletion
    removes both, so a real re-signup never has one older than its old plans.
    Returns counts only; callers log only those."""
    ovh, users, sessions, accts = (db.overhauls_table, db.users_table, db.sessions_table,
                                   db.accounts_table)
    counts = {"overhauls": 0, "child_rows": 0}
    with db.engine.begin() as conn:
        ids = set(conn.execute(select(ovh.c.overhaul_id).where(
            ~ovh.c.account_user_id.in_(select(users.c.sleeper_user_id)),
            ~ovh.c.account_user_id.in_(select(sessions.c.user_id)),
            ~ovh.c.account_user_id.in_(select(ACCOUNT_USER_PREFIX + accts.c.account_id)),
            ~ovh.c.account_user_id.in_(select(accts.c.sleeper_user_id).where(
                accts.c.sleeper_user_id.isnot(None))))).scalars())
        for oid, owner, made, joined in conn.execute(
                select(ovh.c.overhaul_id, ovh.c.account_user_id, ovh.c.created_at, users.c.created_at)
                .join(users, users.c.sleeper_user_id == ovh.c.account_user_id)
                .where(users.c.created_at.isnot(None))).all():
            made_at, joined_at = _parse_utc(made), _parse_utc(joined)
            if made_at is None or joined_at is None or joined_at - made_at <= _OVERHAUL_RESIGNUP_MARGIN:
                continue
            anchors = list(conn.execute(select(sessions.c.created_at).where(
                sessions.c.user_id == owner)).scalars()) + list(conn.execute(
                select(accts.c.created_at).where(
                    (ACCOUNT_USER_PREFIX + accts.c.account_id == owner)
                    | (accts.c.sleeper_user_id == owner))).scalars())
            if any(t is not None and t <= made_at for t in map(_parse_utc, anchors)):
                continue
            ids.add(oid)
        ids = sorted(ids)
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            for name in _OVERHAUL_CHILD_TABLES:
                tbl = getattr(db, name + "_table")
                counts["child_rows"] += conn.execute(
                    delete(tbl).where(tbl.c.overhaul_id.in_(chunk))).rowcount or 0
            counts["overhauls"] += conn.execute(
                delete(ovh).where(ovh.c.overhaul_id.in_(chunk))).rowcount or 0
        for name in _OVERHAUL_CHILD_TABLES:
            tbl = getattr(db, name + "_table")
            counts["child_rows"] += conn.execute(delete(tbl).where(
                ~tbl.c.overhaul_id.in_(select(ovh.c.overhaul_id)))).rowcount or 0
    return counts


def _parse_utc(raw):
    """An ISO timestamp as an aware UTC datetime (a bare date or naive time is
    UTC); None when it doesn't parse."""
    try:
        value = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _loads_dict(raw):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


@contextmanager
def deletion_scope(sleeper_user_id: str, account_id: str | None = None):
    """Drain the full alias set, retrying if a just-finished bind expanded it."""
    deadline = time.monotonic() + 10.0
    while True:
        with db.engine.connect() as conn:
            user_ids, acct_ids = _user_data_scope(conn, sleeper_user_id, account_id)
            work_keys = _deletion_work_keys(conn, user_ids, acct_ids)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise user_data_lifecycle.UserDataBusy("account aliases changed during deletion")
        with user_data_lifecycle.hold(work_keys, timeout=remaining):
            with db.engine.connect() as conn:
                latest_users, latest_accounts = _user_data_scope(conn, sleeper_user_id, account_id)
                latest_keys = _deletion_work_keys(conn, latest_users, latest_accounts)
            if not latest_keys <= work_keys or not latest_accounts <= acct_ids:
                continue
            yield user_ids, acct_ids
            return


def identity_work_key(provider: str, subject: str) -> str:
    """Stable admission key even when deletion removes the account mapping."""
    digest = hashlib.sha256((provider + "\0" + subject).encode()).hexdigest()
    return "identity_work:" + digest


def _deletion_work_keys(conn, user_ids, account_ids):
    identities = conn.execute(select(db.linked_identities_table.c.provider,
                                     db.linked_identities_table.c.provider_subject).where(
        db.linked_identities_table.c.account_id.in_(account_ids)))
    return set(user_ids) | {identity_work_key(provider, subject) for provider, subject in identities}


def delete_user_data(sleeper_user_id: str,
                     account_id: str | None = None) -> dict[str, int]:
    """Drain authorized work, atomically delete, then reject queued old work."""
    with deletion_scope(sleeper_user_id, account_id) as (user_ids, account_ids):
        with db.engine.connect() as conn:
            work_keys = _deletion_work_keys(conn, user_ids, account_ids)
        counts = _delete_user_data(sleeper_user_id, account_id)
        user_data_lifecycle.invalidate(work_keys)
        return counts


def _delete_user_data(sleeper_user_id: str,
                     account_id: str | None = None) -> dict[str, int]:
    """Delete/anonymize everything keyed to `sleeper_user_id`.

    `account_id`: also delete this account (e.g. an unbound account attached
    to the session). The account bound to the user is found and deleted
    regardless. Returns a per-action count map for the route's response/log.
    """
    uid = sleeper_user_id
    counts: dict[str, int] = {}

    with db.engine.begin() as conn:
        user_ids, acct_ids = _user_data_scope(conn, uid, account_id)

        def _del(name: str, tbl, col="user_id"):
            res = conn.execute(delete(tbl).where(getattr(tbl.c, col).in_(user_ids)))
            counts[f"{name}_deleted"] = res.rowcount or 0

        # Keep the DB fence as well as the in-process lifecycle lease: a
        # rolling deploy may still have a Win Now writer in another container.
        # Lock every resolved alias in a stable order before deleting evidence.
        conn.execute(select(db.users_table.c.sleeper_user_id)
                     .where(db.users_table.c.sleeper_user_id.in_(user_ids))
                     .order_by(db.users_table.c.sleeper_user_id).with_for_update()).all()
        conn.execute(select(db.accounts_table.c.account_id)
                     .where(db.accounts_table.c.account_id.in_(acct_ids))
                     .order_by(db.accounts_table.c.account_id).with_for_update()).all()
        # Prepared decks contain all consumed managers' private evidence, not
        # only the viewer's data. Delete dependent artifacts and queued targets
        # in this same transaction; stale generation/adoption tokens then fail.
        from .prepared_trade_store import delete_for_users as delete_prepared_for_users
        counts.update(delete_prepared_for_users(conn, user_ids))
        # Legal R28.20 (ii) / R28.22: the scrub of this person's traces in
        # OTHER users' decks. Its job row (a random token, the ids, and the
        # leagues, read before the deletes below remove them) commits with
        # this deletion; the route kicks the deck stores off the request and
        # the cleanup loop retries them (backend/deletion_scrub.py). The small
        # stores take the same token here.
        from . import deletion_scrub
        token = deletion_scrub.enqueue(conn, user_ids,
                                       deletion_scrub.capture_leagues(conn, user_ids))
        counts["deletion_scrub_jobs_enqueued"] = 1
        counts.update(deletion_scrub.scrub_side_tables(conn, user_ids, token))
        # Revoke durable tokens in this transaction. A failure must roll back
        # the deletion, never return success with restorable credentials.
        for name in ("sessions", "entitlements", "subscription_events"):
            tbl = getattr(db, name + "_table")
            res = conn.execute(delete(tbl).where(
                tbl.c.user_id.in_(user_ids) | tbl.c.account_id.in_(acct_ids)))
            counts[name + "_deleted"] = res.rowcount or 0

        links = db.identity_links_table
        own_link = (links.c.sleeper_user_id.in_(user_ids)
                    | links.c.account_id.in_(acct_ids))
        device_ids = set(conn.execute(select(links.c.device_id).where(own_link)).scalars())
        # Delete pre-auth history associated with these devices. Preserve
        # identified events for another person who used the same installation.
        anonymous_ids = {"device:" + did for did in device_ids}
        events = db.user_events_table
        res = conn.execute(delete(events).where(
            events.c.user_id.in_(user_ids | anonymous_ids)))
        counts["user_events_deleted"] = res.rowcount or 0
        res = conn.execute(delete(links).where(
            own_link | (links.c.device_id.in_(device_ids)
                        & links.c.sleeper_user_id.is_(None)
                        & links.c.account_id.is_(None))))
        counts["identity_links_deleted"] = res.rowcount or 0
        assignments = db.experiment_assignments_table
        res = conn.execute(delete(assignments).where(
            assignments.c.unit_id.in_(user_ids | anonymous_ids | device_ids | acct_ids)))
        counts["experiment_assignments_deleted"] = res.rowcount or 0

        impressions = select(db.deck_impressions_table.c.impression_id).where(
            db.deck_impressions_table.c.user_id.in_(user_ids))
        # A packed card's outcomes are keyed by its contract id, with or
        # without a row: the evidence prune deletes a packed deck's rows at 90
        # days and keeps its outcomes with the pack (#523 QA P1-1, E-b4).
        contract_ids = db.deck_pack_contract_ids(conn, user_ids)
        chunks = [contract_ids[k:k + 500] for k in range(0, len(contract_ids), 500)]
        res = conn.execute(delete(db.deck_outcomes_table).where(
            db.deck_outcomes_table.c.impression_id.in_(impressions)))
        counts["deck_outcomes_deleted"] = (res.rowcount or 0) + sum(
            conn.execute(delete(db.deck_outcomes_table).where(
                db.deck_outcomes_table.c.impression_id.in_(chunk))).rowcount or 0
            for chunk in chunks)
        # Shared executed-trade records keep their aggregate classification,
        # but cannot retain links to deleted private suggestions.
        links = db.suggestion_trade_links_table
        for col in ("matched_impression_id", "ghost_impression_id"):
            res = conn.execute(update(links).where(links.c[col].in_(impressions))
                               .values({col: None}))
            # Contract ids are only ever non-ghost cards' (a ghost keeps its
            # uuid4), so only the matched column can hold one; neither column
            # is indexed, so the ghost pass would scan for nothing.
            counts["suggestion_trade_links_" + col + "_anonymized"] = (res.rowcount or 0) + (sum(
                conn.execute(update(links).where(links.c[col].in_(chunk))
                             .values({col: None})).rowcount or 0
                for chunk in chunks) if col == "matched_impression_id" else 0)
        _del("deck_impressions", db.deck_impressions_table)
        for name in _ADDITIONAL_PRIVATE_TABLES:
            _del(name, getattr(db, name + "_table"))
        # G3-e (legal R28.22): outcomes by their own user_id too, after the
        # row and pack paths above, so this count is the outcomes only it
        # reached.
        _del("deck_outcomes_by_owner", db.deck_outcomes_table)

        # Another manager owns their confirmed-send record. Preserve its
        # package/provider history, but remove deleted-counterparty attribution
        # and the frozen valuation, which can contain their private board data.
        proposals = db.trade_proposals_table
        res = conn.execute(update(proposals).where(
            proposals.c.target_user_id.in_(user_ids)).values(
                target_user_id=None, valuation_json=None))
        counts["trade_proposals_counterparty_anonymized"] = res.rowcount or 0

        # Team overhaul: the user's own overhauls go with every row under them.
        # In OTHER users' overhauls, an offer naming them as the counterparty
        # keeps its package, decision and send history, but the id and name
        # become the placeholder, the card loses the counterparty's
        # Fleeced-derived fields, and the frozen evidence (both sides' private
        # boards) goes, as trade_proposals.valuation_json above. A liked or
        # undecided offer goes stale, the native retirement: a stale offer is
        # never sent (the placeholder resolves to no roster) and a refresh
        # rebuilds against current rosters. An undecided one also gets a fresh
        # package_hash, so regeneration can't revive the scrubbed row by hash;
        # a liked or passed one keeps its hash, which is what stops a passed
        # package coming back. An offer names its counterparty by league member
        # id: on ESPN/MFL that's the user's own id (session_input.py:58), on
        # Sleeper the roster's owner, so user_ids is the whole set. NOT their
        # overhauls' league_user_id: a Sleeper co-owner's is the roster's
        # PRIMARY owner, another live person (release-lead #540 QA P1).
        ovh = db.overhauls_table
        own = select(ovh.c.overhaul_id).where(ovh.c.account_user_id.in_(user_ids))
        named_ids = set(user_ids)
        for name in _OVERHAUL_CHILD_TABLES:
            tbl = getattr(db, name + "_table")
            res = conn.execute(delete(tbl).where(tbl.c.overhaul_id.in_(own)))
            counts[name + "_deleted"] = res.rowcount or 0
        res = conn.execute(delete(ovh).where(ovh.c.account_user_id.in_(user_ids)))
        counts["overhauls_deleted"] = res.rowcount or 0
        offers = db.overhaul_offers_table
        named = conn.execute(select(offers.c.id, offers.c.offer_id, offers.c.overhaul_id,
                                    offers.c.card_json, offers.c.decision).where(
            offers.c.counterparty_user_id.in_(named_ids))).all()
        for row in named:
            card = _loads_dict(row.card_json)
            values = dict(
                counterparty_user_id=DELETED_USER_PLACEHOLDER,
                counterparty_username=DELETED_USER_PLACEHOLDER,
                card_json=json.dumps(dict(_overhaul_card_without_partner_fields(card),
                                          **_OVERHAUL_REDACTED_CARD_VALUES)
                                     if card is not None else {}),
                evidence_json=None)
            if row.decision != "pass":
                values["availability"] = "stale"
            if row.decision == "undecided":
                values["package_hash"] = "redacted_" + secrets.token_hex(16)
            conn.execute(update(offers).where(offers.c.id == row.id).values(**values))
        counts["overhaul_offers_counterparty_anonymized"] = len(named)
        # Their roadmaps list each package's counterparty id in the summary, and
        # a stored ownership blocker on a scrubbed offer names the team in its
        # message (release-lead #540 QA P2-1): it becomes the shared copy's
        # unnamed form, the same sentence a nameless counterparty gets.
        from .ownership_copy import refusal_message
        scrubbed_offers = {r.offer_id for r in named}
        roadmaps = db.overhaul_roadmaps_table
        touched = 0
        for row in conn.execute(select(roadmaps.c.id, roadmaps.c.summary_json, roadmaps.c.compat_json)
                                .where(roadmaps.c.overhaul_id.in_({r.overhaul_id for r in named}))).all():
            values = {}
            summary = _loads_dict(row.summary_json)
            cps = summary.get("counterparties") if summary is not None else None
            if isinstance(cps, list) and {str(c) for c in cps} & named_ids:
                summary["counterparties"] = [DELETED_USER_PLACEHOLDER if str(c) in named_ids else c
                                             for c in cps]
                values["summary_json"] = json.dumps(summary)
            compat = _loads_dict(row.compat_json)
            hits = [item for items in (compat or {}).values() if isinstance(items, list)
                    for item in items if isinstance(item, dict)
                    and item.get("code") == "counterparty_asset_not_owned"
                    and item.get("offer_id") in scrubbed_offers]
            for item in hits:
                assets = item.get("assets") if isinstance(item.get("assets"), list) else []
                item["message"] = refusal_message("receive", assets, {}, None)
            if hits:
                values["compat_json"] = json.dumps(compat)
            if values:
                conn.execute(update(roadmaps).where(roadmaps.c.id == row.id).values(**values))
                touched += 1
        counts["overhaul_roadmaps_counterparty_anonymized"] = touched
        # Their snapshots key `rosters` by league member id and pick owner, and
        # their recovery names a pick's holder. On ESPN/MFL grids those can be
        # this user's Fleeced-minted id (entry:*, acct_*; the same rule as
        # recorded_picks below), which then becomes the placeholder. Platform
        # ids stay.
        minted = {u for u in user_ids if u.startswith("entry:") or is_account_user_id(u)}
        snapshots = 0
        if minted:
            for row in conn.execute(select(ovh.c.id, ovh.c.snapshot_json, ovh.c.recovery_json).where(
                    or_(*[col.contains(m, autoescape=True) for m in minted
                          for col in (ovh.c.snapshot_json, ovh.c.recovery_json)]))).all():
                values = {}
                snapshot = _loads_dict(row.snapshot_json)
                rosters = snapshot.get("rosters") if snapshot is not None else None
                if isinstance(rosters, dict) and set(rosters) & minted:
                    kept = {k: v for k, v in rosters.items() if k not in minted}
                    kept[DELETED_USER_PLACEHOLDER] = list(kept.get(DELETED_USER_PLACEHOLDER) or []) + [
                        a for k in sorted(set(rosters) & minted) for a in rosters[k] or []]
                    snapshot["rosters"] = kept
                    values["snapshot_json"] = json.dumps(snapshot)
                recovery = _loads_dict(row.recovery_json)
                if recovery is not None and recovery.get("holder_user_id") in minted:
                    recovery.update(holder_user_id=DELETED_USER_PLACEHOLDER,
                                    holder_username=DELETED_USER_PLACEHOLDER)
                    values["recovery_json"] = json.dumps(recovery)
                if values:
                    conn.execute(update(ovh).where(ovh.c.id == row.id).values(**values))
                    snapshots += 1
        counts["overhaul_snapshots_anonymized"] = snapshots

        # Preserve published ranking snapshots and other users' adoptions;
        # remove attribution and freeform author metadata. Private sets have
        # no shared contract, so remove their entries and the sets themselves.
        sets = db.rank_sets_table
        private_sets = select(sets.c.id).where(
            sets.c.owner_user_id.in_(user_ids), sets.c.visibility == "private")
        for name in ("rank_set_entries", "rank_set_adoptions"):
            tbl = getattr(db, name + "_table")
            res = conn.execute(delete(tbl).where(tbl.c.rank_set_id.in_(private_sets)))
            counts[name + "_private_deleted"] = res.rowcount or 0
        res = conn.execute(delete(sets).where(sets.c.id.in_(private_sets)))
        counts["rank_sets_deleted"] = res.rowcount or 0
        res = conn.execute(update(sets).where(sets.c.owner_user_id.in_(user_ids))
                           .values(owner_user_id=DELETED_USER_PLACEHOLDER,
                                   title="Deleted contributor", description=None))
        counts["rank_sets_anonymized"] = res.rowcount or 0

        for name, col, values in (
            ("shared_packages", "user_id", {"user_id": DELETED_USER_PLACEHOLDER}),
            ("affiliate_clicks", "user_id", {"user_id": None}),
            ("trade_block", "user_id", {"user_id": None}),
            ("users", "invited_by", {"invited_by": None}),
            ("recorded_picks", "recorded_by", {"recorded_by": DELETED_USER_PLACEHOLDER}),
            ("draft_picks", "assigned_by", {"assigned_by": None}),
        ):
            tbl = getattr(db, name + "_table")
            res = conn.execute(update(tbl).where(tbl.c[col].in_(user_ids)).values(**values))
            counts[name + "_" + col + "_anonymized"] = res.rowcount or 0
        # Platform (non-Sleeper) pick grids hold the importer's Fleeced id as
        # the owner of their own picks. `platform` is the LEAGUE's provenance,
        # written by every draft_picks writer; Sleeper grids and legacy NULL
        # rows keep their public Sleeper ids untouched.
        # The writers also fill owner_username / original_username from the
        # member's own name (server._sync_mfl_owned_picks, the assignment
        # seeder), so each scrubbed side's name becomes those writers' own
        # fallback, "Team <slot>". The original side's slot is the row's
        # original_roster_id. The owner side's is the same when the person is
        # on both sides (their own pick); otherwise it's their one slot in that
        # league (their own original picks, aliases included), else the
        # placeholder.
        picks = db.draft_picks_table
        platform_grid = picks.c.platform.isnot(None) & (picks.c.platform != "sleeper")
        named = conn.execute(select(
            picks.c.id, picks.c.league_id, picks.c.owner_user_id,
            picks.c.original_user_id, picks.c.original_roster_id).where(
            platform_grid,
            picks.c.owner_user_id.in_(user_ids) | picks.c.original_user_id.in_(user_ids),
        )).all()
        own_slots: dict[str, set] = {}
        for r in named:
            if r.original_user_id in user_ids and r.original_roster_id:
                own_slots.setdefault(r.league_id, set()).add(str(r.original_roster_id))

        def _team(slot) -> str:
            return f"Team {slot}" if slot else DELETED_USER_PLACEHOLDER

        # One UPDATE per distinct set of new values, not per row: a person's
        # rows share a handful of slots, and this runs inside the deletion
        # transaction.
        batches: dict[tuple, list] = {}
        for r in named:
            values = {}
            if r.original_user_id in user_ids:
                values.update(original_user_id=DELETED_USER_PLACEHOLDER,
                              original_username=_team(r.original_roster_id))
            if r.owner_user_id in user_ids:
                slots = own_slots.get(r.league_id, set())
                slot = (r.original_roster_id if r.original_user_id in user_ids
                        else next(iter(slots)) if len(slots) == 1 else None)
                values.update(owner_user_id=DELETED_USER_PLACEHOLDER, owner_username=_team(slot))
            batches.setdefault(tuple(sorted(values.items())), []).append(r.id)
        for key, ids in batches.items():
            for i in range(0, len(ids), 500):
                conn.execute(update(picks).where(picks.c.id.in_(ids[i:i + 500])).values(**dict(key)))
        counts["draft_picks_owner_anonymized"] = len(named)
        # recorded_picks.picking_team_id (a league_members.user_id) has no
        # platform column to apply the rule above with, so it is anonymized
        # only where it holds a Fleeced-minted id (entry:*, acct_*), which
        # exists nowhere but here and names the person. Public Sleeper ids
        # stay, as on Sleeper grids (#452 D2).
        minted = [u for u in user_ids if u.startswith("entry:") or is_account_user_id(u)]
        recorded = db.recorded_picks_table
        res = conn.execute(update(recorded).where(recorded.c.picking_team_id.in_(minted))
                           .values(picking_team_id=DELETED_USER_PLACEHOLDER))
        counts["recorded_picks_picking_team_id_anonymized"] = res.rowcount or 0
        # pick_assignment_changed is the pick grid's audit trail (contested
        # derivation and the runbook's grid reconstruction read it). OTHER
        # users' events can name this user as old_owner / new_owner / actor.
        # A Fleeced-minted id there names the person, so it becomes the
        # placeholder, matching the grid rows above; public Sleeper ids stay,
        # as on Sleeper grids (#452 QA P2).
        events_tbl = db.user_events_table
        minted_set = set(minted)
        scrubbed = 0
        if minted:
            rows = conn.execute(select(events_tbl.c.id, events_tbl.c.props).where(
                events_tbl.c.event_type == "pick_assignment_changed",
                or_(*[events_tbl.c.props.contains(m, autoescape=True) for m in minted]),
            )).all()
            for event_id, raw in rows:
                try:
                    props = json.loads(raw or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(props, dict):   # a malformed row must not abort the deletion
                    continue
                hits = [k for k in ("old_owner", "new_owner", "actor") if props.get(k) in minted_set]
                if hits:
                    for k in hits:
                        props[k] = DELETED_USER_PLACEHOLDER
                    conn.execute(update(events_tbl).where(events_tbl.c.id == event_id)
                                 .values(props=json.dumps(props)))
                    scrubbed += 1
        counts["pick_assignment_events_anonymized"] = scrubbed
        # leagues.pick_assignment_settings.order lists every member's id in
        # slot order (seed_pick_grid), including on rows OTHER users imported.
        # A Fleeced-minted id there names the person (an entry:espn:{SWID}
        # carries a third party's SWID, R28.16). It becomes the placeholder in
        # place, so the other owners' slot positions don't shift; public
        # Sleeper ids stay, as on Sleeper grids (#452 QA round 3).
        leagues_tbl = db.leagues_table
        orders = 0
        if minted:
            rows = conn.execute(select(leagues_tbl.c.sleeper_league_id,
                                       leagues_tbl.c.pick_assignment_settings).where(
                or_(*[leagues_tbl.c.pick_assignment_settings.contains(m, autoescape=True)
                      for m in minted]))).all()
            for league_id, raw in rows:
                try:
                    settings = json.loads(raw or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                order = settings.get("order") if isinstance(settings, dict) else None
                if not isinstance(order, list):
                    continue
                anonymized = [DELETED_USER_PLACEHOLDER if o in minted_set else o for o in order]
                if anonymized != order:
                    settings["order"] = anonymized
                    conn.execute(update(leagues_tbl)
                                 .where(leagues_tbl.c.sleeper_league_id == league_id)
                                 .values(pick_assignment_settings=json.dumps(settings)))
                    orders += 1
        counts["pick_assignment_order_anonymized"] = orders
        # Weak roster keys embed the user ID; strong keys are public team slots.
        history = db.league_roster_history_table
        res = conn.execute(delete(history).where(history.c.owner_user_id.in_(user_ids),
                                                history.c.team_key_quality == "weak"))
        counts["league_roster_history_weak_deleted"] = res.rowcount or 0
        res = conn.execute(update(history).where(history.c.owner_user_id.in_(user_ids))
                           .values(owner_user_id=None))
        counts["league_roster_history_anonymized"] = res.rowcount or 0
        referrals = db.referrals_table
        # NULL the invitee first; per-row sender tombstones avoid collisions
        # in the unique sender/invitee index after several account deletions.
        res = conn.execute(update(referrals).where(referrals.c.referred_user_id.in_(user_ids))
                           .values(referred_user_id=None))
        counts["referrals_referred_anonymized"] = res.rowcount or 0
        rows = conn.execute(select(referrals.c.id).where(
            referrals.c.referrer_user_id.in_(user_ids))).scalars().all()
        for rid in rows:
            conn.execute(update(referrals).where(referrals.c.id == rid).values(
                referrer_user_id=f"{DELETED_USER_PLACEHOLDER}:{rid}"))
        counts["referrals_referrer_anonymized"] = len(rows)

        _del("swipe_decisions", db.swipe_decisions_table)
        _del("trade_decisions", db.trade_decisions_table)
        _del("win_now_decisions", db.win_now_decisions_table)
        _del("win_now_scenarios", db.win_now_scenarios_table)
        _del("win_now_jobs", db.win_now_jobs_table)
        _del("member_rankings", db.member_rankings_table)
        _del("elo_history", db.elo_history_table)
        _del("league_preferences", db.league_preferences_table)
        _del("asset_preferences", db.asset_preferences_table)
        _del("user_player_skips", db.user_player_skips_table)
        _del("notifications", db.notifications_table)
        _del("device_tokens", db.device_tokens_table)
        _del("notification_prefs", db.notification_prefs_table)
        _del("notification_events_log", db.notification_events_log_table)
        _del("notification_queue", db.notification_queue_table)
        _del("wrapped_events", db.wrapped_events_table)
        _del("sleeper_credentials", db.sleeper_credentials_table)
        _del("league_members", db.league_members_table)
        _del("leagues", db.leagues_table)
        _del("bad_trade_flags", db.bad_trade_flags_table)
        _del("trade_impressions", db.trade_impressions_table)
        # Trade share links this user minted die with the account (build O8);
        # the other party's own tokens for the same match are untouched.
        _del("trade_share_tokens", db.trade_share_tokens_table, "created_by")

        # Shared rows — anonymize the deleted side, keep the counterparty's
        # record (incl. status + both decisions) intact. The match-time
        # valuation holds both sides' boards (user_a's own as the viewer,
        # user_b's as the partner), so it goes either way (legal R28.22 e).
        res = conn.execute(
            update(db.trade_matches_table)
            .where(db.trade_matches_table.c.user_a_id.in_(user_ids))
            .values(user_a_id=DELETED_USER_PLACEHOLDER, match_valuation_json=None)
        )
        n = res.rowcount or 0
        res = conn.execute(
            update(db.trade_matches_table)
            .where(db.trade_matches_table.c.user_b_id.in_(user_ids))
            .values(user_b_id=DELETED_USER_PLACEHOLDER, match_valuation_json=None)
        )
        counts["trade_matches_anonymized"] = n + (res.rowcount or 0)

        res = conn.execute(
            update(db.trade_impressions_table)
            .where(db.trade_impressions_table.c.target_user_id.in_(user_ids))
            .values(target_user_id=None)
        )
        counts["trade_impressions_target_anonymized"] = res.rowcount or 0

        res = conn.execute(
            update(db.bad_trade_flags_table)
            .where(db.bad_trade_flags_table.c.target_user_id.in_(user_ids))
            .values(target_user_id=None, target_username=None)
        )
        counts["bad_trade_flags_target_anonymized"] = res.rowcount or 0

        res = conn.execute(
            update(db.app_feedback_table)
            .where(db.app_feedback_table.c.user_id.in_(user_ids))
            .values(user_id=None, username=None,
                    text="[Removed following account deletion]")
        )
        counts["app_feedback_anonymized"] = res.rowcount or 0

        # Identity layer — the bound account plus any session-attached one.
        n_acct = n_ident = 0
        for aid in acct_ids:
            res = conn.execute(
                delete(db.linked_identities_table).where(
                    db.linked_identities_table.c.account_id == aid
                )
            )
            n_ident += res.rowcount or 0
            res = conn.execute(
                delete(db.accounts_table).where(
                    db.accounts_table.c.account_id == aid
                )
            )
            n_acct += res.rowcount or 0
        counts["linked_identities_deleted"] = n_ident
        counts["accounts_deleted"] = n_acct

        # The user record itself — last, per privacy policy §6.
        res = conn.execute(
            delete(db.users_table).where(
                db.users_table.c.sleeper_user_id.in_(user_ids)
            )
        )
        counts["users_deleted"] = res.rowcount or 0

    return counts


# ---------------------------------------------------------------------------
# Data export (GDPR Art. 20 portability — teardown 06-02, flag
# `account.data_export` on the route). The export includes the deletion
# scope's private rows and user-attributed shared rows. Credential ciphertext,
# legacy session identifiers and raw billing payloads are never exported.
# Route in server.py (GET /api/account/export) applies the
# same auth gates as deletion (demo-blocked, verified-user step-up).
# ---------------------------------------------------------------------------

# (table_key, table, user column, columns to omit from the export)
# sleeper_credentials.token_encrypted is omitted: a Fernet-encrypted
# full-account Sleeper credential is useless to the user and dangerous in a
# plaintext archive. Prepared payloads also contain counterparty-private inputs;
# export only their owned metadata, never the payload or recovery runtime.
_EXPORT_TABLES: tuple = (
    ("users",                   "users_table",                   "sleeper_user_id", ()),
    ("swipe_decisions",         "swipe_decisions_table",         "user_id",         ()),
    ("trade_decisions",         "trade_decisions_table",         "user_id",         ()),
    ("win_now_decisions",       "win_now_decisions_table",       "user_id",         ()),
    ("win_now_scenarios",       "win_now_scenarios_table",       "user_id",         ()),
    ("win_now_jobs",            "win_now_jobs_table",            "user_id",         ()),
    ("member_rankings",         "member_rankings_table",         "user_id",         ()),
    ("elo_history",             "elo_history_table",             "user_id",         ()),
    ("league_preferences",      "league_preferences_table",      "user_id",         ()),
    ("asset_preferences",       "asset_preferences_table",       "user_id",         ()),
    ("user_player_skips",       "user_player_skips_table",       "user_id",         ()),
    ("notifications",           "notifications_table",           "user_id",         ()),
    ("device_tokens",           "device_tokens_table",           "user_id",         ("device_token",)),
    ("notification_prefs",      "notification_prefs_table",      "user_id",         ()),
    ("notification_events_log", "notification_events_log_table", "user_id",         ()),
    ("notification_queue",      "notification_queue_table",      "user_id",         ()),
    ("user_events",             "user_events_table",             "user_id",         ("session_id",)),
    ("wrapped_events",          "wrapped_events_table",          "user_id",         ()),
    ("sleeper_credentials",     "sleeper_credentials_table",     "user_id",         ("token_encrypted",)),
    ("league_members",          "league_members_table",          "user_id",         ()),
    ("leagues",                 "leagues_table",                 "user_id",         ("espn_auth", "platform_auth")),
    ("bad_trade_flags",         "bad_trade_flags_table",         "user_id",         ()),
    ("trade_impressions",       "trade_impressions_table",       "user_id",         ()),
    # session_key is NULL on every user-linked row (attach clears it); omitted
    # anyway so a token hash can never leave in an export.
    ("app_feedback",            "app_feedback_table",            "user_id",         ("session_key",)),
    ("espn_credentials", "espn_credentials_table", "user_id", ("espn_s2_encrypted",)),
    ("mfl_credentials", "mfl_credentials_table", "user_id", ("cookie_encrypted",)),
    ("deck_impressions", "deck_impressions_table", "user_id", ()),
    ("shared_packages", "shared_packages_table", "user_id", ()),
    # The share token is a bearer capability for a public link: omitted like
    # referrals.invite_token; match_id + timestamps carry the user's history.
    ("trade_share_tokens", "trade_share_tokens_table", "created_by", ("token",)),
    ("affiliate_clicks", "affiliate_clicks_table", "user_id", ()),
    ("trade_block", "trade_block_table", "user_id", ()),
    ("rank_sets", "rank_sets_table", "owner_user_id", ()),
    ("recorded_picks", "recorded_picks_table", "recorded_by", ()),
    ("draft_picks", "draft_picks_table", "assigned_by", ()),
    ("league_roster_history", "league_roster_history_table", "owner_user_id", ()),
    ("prepared_trade_inventories", "prepared_trade_inventories_table", "user_id",
     ("adoption_token", "payload_json")),
    ("prepared_trade_manifests_v2", "prepared_trade_manifests_v2_table", "user_id",
     ("generation_token", "adoption_token", "header_json", "metadata_json", "adoption_json")),
    ("prepared_trade_targets", "prepared_trade_targets_table", "user_id",
     ("lease_token", "payload_json")),
    ("prepared_trade_participants", "prepared_trade_participants_table", "user_id", ()),
    ("overhauls", "overhauls_table", "account_user_id", ()),
)

_EXPORT_TABLES += tuple(
    (name, name + "_table", "user_id", ())
    for name in _ADDITIONAL_PRIVATE_TABLES
    if name not in {"espn_credentials", "mfl_credentials"}
)


def _rows_as_dicts(rows, omit: tuple = ()) -> list[dict]:
    return [
        {k: v for k, v in r._mapping.items() if k not in omit}
        for r in rows
    ]


def _export_candidate_set(row: dict) -> None:
    """A packed deck_candidate_sets row (S8, eng-evidence-contract §9) exports
    the reader's unpacked JSON in candidates_json, not the bytes; a pack that
    can't be read exports candidates_json None and its error."""
    packed = row.pop("candidates_packed", None)
    if packed is None:
        return
    from .eval import evidence_pack
    try:
        _run, members = evidence_pack.unpack_candidates(evidence_pack.PackedCandidates(
            row.get("cand_pack_version"), bytes(packed)))
    except evidence_pack.PackIntegrityError as e:
        row.update(candidates_json=None, candidates_pack_error=str(e))
    else:
        row["candidates_json"] = json.dumps(members)


def _export_evidence_pack(row: dict) -> None:
    """A deck_evidence_packs row exports its unpacked run metadata and cards
    (`run`, `cards`), not cards_blob; an unreadable pack exports its error."""
    from .eval import evidence_pack
    blob = row.pop("cards_blob", None)
    try:
        row["run"], row["cards"] = evidence_pack.unpack_run(evidence_pack.PackedRun(
            row["pack_version"], row["header_json"], bytes(blob or b""), row["checksum"],
            row["card_count"]))
    except evidence_pack.PackIntegrityError as e:
        row["pack_error"] = str(e)


def _export_deck_features(raw):
    """Remove only prepared recovery evidence; retain the existing text contract."""
    if not isinstance(raw, str):
        return raw
    try:
        features = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    if not isinstance(features, dict) or "prepared_runtime" not in features:
        return raw
    del features["prepared_runtime"]
    return json.dumps(features)


def export_user_data(sleeper_user_id: str,
                     account_id: str | None = None) -> dict:
    """JSON-serializable archive of every user-keyed row (deletion-matrix
    scope). `account_id`: also include an unbound session-attached account,
    mirroring delete_user_data's account resolution.
    """
    uid = sleeper_user_id
    out: dict = {
        "export_version": 2,
        "exported_at":    _now_iso(),
        "user_id":        uid,
        "tables":         {},
    }
    tables = out["tables"]
    with db.engine.connect() as conn:
        user_ids, acct_ids = _user_data_scope(conn, uid, account_id)
        for key, tbl_attr, col, omit in _EXPORT_TABLES:
            tbl = getattr(db, tbl_attr)
            tables[key] = _rows_as_dicts(conn.execute(
                select(tbl).where(tbl.c[col].in_(user_ids))).fetchall(), omit)
            if key == "deck_impressions":
                for row in tables[key]:
                    row["features_json"] = _export_deck_features(row["features_json"])
            elif key == "deck_candidate_sets":
                for row in tables[key]:
                    _export_candidate_set(row)
            elif key == "deck_evidence_packs":
                for row in tables[key]:
                    _export_evidence_pack(row)

        for name, predicate, omit in (
            ("trade_matches", db.trade_matches_table.c.user_a_id.in_(user_ids)
             | db.trade_matches_table.c.user_b_id.in_(user_ids), ()),
            ("referrals", db.referrals_table.c.referrer_user_id.in_(user_ids)
             | db.referrals_table.c.referred_user_id.in_(user_ids), ("invite_token",)),
            ("accounts", db.accounts_table.c.account_id.in_(acct_ids), ()),
            ("linked_identities", db.linked_identities_table.c.account_id.in_(acct_ids), ()),
            ("identity_links", db.identity_links_table.c.sleeper_user_id.in_(user_ids)
             | db.identity_links_table.c.account_id.in_(acct_ids), ()),
        ):
            tbl = getattr(db, name + "_table")
            tables[name] = _rows_as_dicts(conn.execute(select(tbl).where(predicate)).fetchall(), omit)

        for name, omit in (("sessions", ("token_hash",)), ("entitlements", ()),
                           ("subscription_events", ("payload", "process_error"))):
            tbl = getattr(db, name + "_table")
            tables[name] = _rows_as_dicts(conn.execute(select(tbl).where(
                tbl.c.user_id.in_(user_ids) | tbl.c.account_id.in_(acct_ids))).fetchall(), omit)

        devices = {r["device_id"] for r in tables["identity_links"]}
        anonymous_ids = {"device:" + did for did in devices}
        tables["user_events"] += _rows_as_dicts(conn.execute(
            select(db.user_events_table).where(
                db.user_events_table.c.user_id.in_(anonymous_ids))).fetchall(), ("session_id",))
        tables["experiment_assignments"] = _rows_as_dicts(conn.execute(
            select(db.experiment_assignments_table).where(
                db.experiment_assignments_table.c.unit_id.in_(
                    user_ids | acct_ids | anonymous_ids | devices))).fetchall())
        # Through the rows, and through the packs' contract ids: a packed
        # card's outcomes outlive its row (#523 QA P1-1).
        impression_ids = list(dict.fromkeys(
            [r["impression_id"] for r in tables["deck_impressions"]]
            + db.deck_pack_contract_ids(conn, user_ids)))
        tables["deck_outcomes"] = [
            row for k in range(0, len(impression_ids), 500)
            for row in _rows_as_dicts(conn.execute(
                select(db.deck_outcomes_table).where(
                    db.deck_outcomes_table.c.impression_id.in_(impression_ids[k:k + 500]))
                .order_by(db.deck_outcomes_table.c.id)).fetchall())]
        # G3-e: and by the outcome's own user_id, each row once.
        outcomes = db.deck_outcomes_table
        known = {r["id"] for r in tables["deck_outcomes"]}
        tables["deck_outcomes"] += [r for r in _rows_as_dicts(conn.execute(
            select(outcomes).where(outcomes.c.user_id.in_(user_ids))).fetchall())
            if r["id"] not in known]
        tables["deck_outcomes"].sort(key=lambda r: r["id"])
        rank_set_ids = [r["id"] for r in tables["rank_sets"]]
        tables["rank_set_entries"] = _rows_as_dicts(conn.execute(
            select(db.rank_set_entries_table).where(
                db.rank_set_entries_table.c.rank_set_id.in_(rank_set_ids))).fetchall())
        # The rows under the user's own overhauls. An offer's evidence_json
        # (both sides' private boards, "never on the wire") is left out, and
        # its card goes out without the counterparty's Fleeced-derived fields
        # (R28.20 c2), the same fields deletion scrubs.
        overhaul_ids = [r["overhaul_id"] for r in tables["overhauls"]]
        for name in _OVERHAUL_CHILD_TABLES:
            tbl = getattr(db, name + "_table")
            tables[name] = _rows_as_dicts(conn.execute(
                select(tbl).where(tbl.c.overhaul_id.in_(overhaul_ids)).order_by(tbl.c.id)).fetchall(),
                ("evidence_json",) if name == "overhaul_offers" else ())
        for row in tables["overhaul_offers"]:
            card = _loads_dict(row["card_json"])
            row["card_json"] = (json.dumps(_overhaul_card_without_partner_fields(card))
                                if card is not None else None)

    return out


# ---------------------------------------------------------------------------
# Sign in with Apple token revocation (App Store 5.1.1(v) companion —
# teardown 06-02, unflagged; called best-effort from DELETE /api/account)
# ---------------------------------------------------------------------------
#
# Apple's /auth/revoke takes a refresh or access token from the
# /auth/token code exchange. FTF never performs that exchange during
# sign-in (it only verifies identity tokens against the JWKS), so nothing
# revocable is stored server-side. Full revocation therefore needs the
# client to send a FRESH `authorizationCode` from a Sign in with Apple
# re-auth at deletion time; the deletion route passes it through as
# `apple_authorization_code`. Without the code — or without the signing
# env keys — this logs and returns False, and local deletion proceeds
# (log-and-continue by design).
#
# Required env: APPLE_TEAM_ID, APPLE_KEY_ID, APPLE_PRIVATE_KEY (the .p8
# PEM contents; literal "\n" escapes accepted).

APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_REVOKE_URL = "https://appleid.apple.com/auth/revoke"
# Per Apple HTTP call. Deletion makes up to two (/auth/token, /auth/revoke)
# before it deletes, and the app's DELETE /api/account gives up at 15 s
# (mobile api/client DEFAULT_TIMEOUT_MS): 2 x 5 s leaves room for the
# deletion itself, so a slow Apple can't make the user see "took too
# long" while the server still deletes (release-lead QA on #446).
APPLE_HTTP_TIMEOUT_S = 5


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _apple_client_secret() -> str | None:
    """ES256 client-secret JWT per Apple's Sign in with Apple REST docs.
    None when any required env key is missing or the key won't load."""
    team_id = os.environ.get("APPLE_TEAM_ID", "").strip()
    key_id = os.environ.get("APPLE_KEY_ID", "").strip()
    pem = os.environ.get("APPLE_PRIVATE_KEY", "").strip()
    if not (team_id and key_id and pem):
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import (
            decode_dss_signature,
        )
        from cryptography.hazmat.primitives.serialization import (
            load_pem_private_key,
        )
        key = load_pem_private_key(
            pem.replace("\\n", "\n").encode("utf-8"), password=None
        )
        now = int(time.time())
        header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
        claims = {
            "iss": team_id,
            "iat": now,
            "exp": now + 600,
            "aud": APPLE_ISSUER,
            "sub": APPLE_AUDIENCE,
        }
        signing_input = (
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
        )
        der_sig = key.sign(signing_input.encode("ascii"),
                           ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_sig)
        raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return f"{signing_input}.{_b64url_encode(raw_sig)}"
    except Exception as e:
        print(f"[apple_revoke] client-secret build failed: {e}")
        return None


def _apple_form_post(url: str, fields: dict) -> tuple[int, dict]:
    """POST a form to an Apple auth endpoint → (status, json body or {})."""
    data = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    # obs.api_events — the form fields (client_secret / authorization_code /
    # tokens) are never event properties; endpoint class from the URL path.
    from . import api_observability as _api_obs
    _endpoint = "auth." + (urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
                           or "token")
    with _api_obs.observe_call("apple", _endpoint, method="POST") as _ob:
        with urllib.request.urlopen(
            req, timeout=APPLE_HTTP_TIMEOUT_S, context=ssl.create_default_context()
        ) as resp:
            raw = resp.read().decode("utf-8", "replace")
        _ob.ok(status=getattr(resp, "status", 200), response_bytes=len(raw))
    try:
        return resp.status, (json.loads(raw) if raw else {})
    except Exception:
        return resp.status, {}


def _id_token_sub(id_token) -> str | None:
    """`sub` from an Apple id_token's payload, or None."""
    try:
        claims = json.loads(_b64url_decode(str(id_token).split(".")[1]))
        sub = claims.get("sub")
        return sub if isinstance(sub, str) and sub else None
    except Exception:
        return None


def revoke_apple_tokens(authorization_code: str | None = None,
                        expected_subjects=None) -> bool:
    """Best-effort SIWA revocation. True only when Apple confirmed the
    revoke; never raises. See the section comment for why a fresh
    `authorization_code` is required.

    `expected_subjects`: the Apple `sub`(s) this Fleeced account linked.
    The code is revoked only when ITS Apple account is one of them: if a
    different Apple ID is signed in on the device, the code belongs to that
    Apple ID, and revoking would cut ITS grant (release-lead QA on #446, d).
    No expected subject, no id_token, or a mismatch → nothing is revoked."""
    try:
        client_secret = _apple_client_secret()
        if not client_secret:
            print("[apple_revoke] skipped: APPLE_TEAM_ID/APPLE_KEY_ID/"
                  "APPLE_PRIVATE_KEY not configured")
            return False
        if not authorization_code:
            print("[apple_revoke] skipped: no apple_authorization_code "
                  "supplied with the deletion request")
            return False
        status, body = _apple_form_post(APPLE_TOKEN_URL, {
            "client_id":     APPLE_AUDIENCE,
            "client_secret": client_secret,
            "code":          authorization_code,
            "grant_type":    "authorization_code",
        })
        token = body.get("refresh_token") or body.get("access_token")
        if status != 200 or not token:
            print(f"[apple_revoke] token exchange failed: status={status} "
                  f"error={body.get('error')}")
            return False
        # Whose code is this? Decoding the id_token without verifying its
        # signature is fine here: it came straight from Apple's /auth/token,
        # over TLS, in reply to our own client_secret-signed request, so the
        # app can't have forged it.
        sub = _id_token_sub(body.get("id_token"))
        if not sub:
            print("[apple_revoke] skipped: Apple's token response carried no "
                  "usable id_token, so the code's Apple account is unknown")
            return False
        if not expected_subjects or sub not in set(expected_subjects):
            print("[apple_revoke] WARNING skipped: the code belongs to a "
                  "different Apple account than the one this account linked")
            return False
        hint = "refresh_token" if body.get("refresh_token") else "access_token"
        status, _ = _apple_form_post(APPLE_REVOKE_URL, {
            "client_id":       APPLE_AUDIENCE,
            "client_secret":   client_secret,
            "token":           token,
            "token_type_hint": hint,
        })
        if status == 200:
            print("[apple_revoke] Apple token revoked")
            return True
        print(f"[apple_revoke] revoke call failed: status={status}")
        return False
    except Exception as e:
        print(f"[apple_revoke] failed (non-fatal): {e}")
        return False


def apple_identity_subjects(sleeper_user_id: str,
                            account_id: str | None = None) -> set[str]:
    """The Apple `sub`s linked to the user's bound account (or the
    session-attached one). Empty when none. Never raises."""
    subjects: set[str] = set()
    try:
        with db.engine.connect() as conn:
            acct_ids = {
                r.account_id for r in conn.execute(
                    select(db.accounts_table.c.account_id).where(
                        db.accounts_table.c.sleeper_user_id == sleeper_user_id
                    )
                ).fetchall()
            }
            if account_id:
                acct_ids.add(account_id)
            if acct_ids:
                subjects.update(conn.execute(
                    select(db.linked_identities_table.c.provider_subject).where(
                        db.linked_identities_table.c.account_id.in_(acct_ids)
                        & (db.linked_identities_table.c.provider == "apple")
                    )
                ).scalars())
    except Exception as e:
        print(f"[apple_revoke] identity lookup failed: {e}")
    return subjects


def has_apple_identity(sleeper_user_id: str,
                       account_id: str | None = None) -> bool:
    """True if the user's bound account (or the session-attached one) has a
    linked Apple identity. Never raises."""
    return bool(apple_identity_subjects(sleeper_user_id, account_id))
