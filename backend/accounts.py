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

import hashlib
import json
import secrets
import ssl
import threading
import time
import urllib.request
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import delete, insert, select, update

from . import database as db

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
    with urllib.request.urlopen(req, timeout=10,
                                context=ssl.create_default_context()) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    keys = body.get("keys")
    if not isinstance(keys, list):
        raise TokenVerificationError("jwks_unavailable", f"malformed JWKS from {url}")
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


def find_or_create_account(provider: str, provider_subject: str,
                           email_hash: str | None = None) -> dict:
    """Return the account owning (provider, subject), creating both the
    account and the identity row on first sight.

    Returns {account_id, sleeper_user_id, created_at, created: bool}.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}")
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
#            product record per privacy policy §5; becomes anonymous, which
#            the submission contract already allows).
#
#   KEEP     player_value_history + model_config (not user-keyed),
#            draft_picks (public league pick grid other members rely on;
#            re-synced from Sleeper), players.
# ---------------------------------------------------------------------------

def delete_user_data(sleeper_user_id: str,
                     account_id: str | None = None) -> dict[str, int]:
    """Delete/anonymize everything keyed to `sleeper_user_id`.

    `account_id`: also delete this account (e.g. an unbound account attached
    to the session). The account bound to the user is found and deleted
    regardless. Returns a per-action count map for the route's response/log.
    """
    uid = sleeper_user_id
    counts: dict[str, int] = {}

    with db.engine.begin() as conn:
        def _del(name: str, tbl, col="user_id"):
            res = conn.execute(delete(tbl).where(getattr(tbl.c, col) == uid))
            counts[f"{name}_deleted"] = res.rowcount or 0

        _del("swipe_decisions", db.swipe_decisions_table)
        _del("trade_decisions", db.trade_decisions_table)
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
        _del("user_events", db.user_events_table)
        _del("wrapped_events", db.wrapped_events_table)
        _del("sleeper_credentials", db.sleeper_credentials_table)
        _del("league_members", db.league_members_table)
        _del("leagues", db.leagues_table)
        _del("bad_trade_flags", db.bad_trade_flags_table)
        _del("trade_impressions", db.trade_impressions_table)

        # Shared rows — anonymize the deleted side, keep the counterparty's
        # record (incl. status + both decisions) intact.
        res = conn.execute(
            update(db.trade_matches_table)
            .where(db.trade_matches_table.c.user_a_id == uid)
            .values(user_a_id=DELETED_USER_PLACEHOLDER)
        )
        n = res.rowcount or 0
        res = conn.execute(
            update(db.trade_matches_table)
            .where(db.trade_matches_table.c.user_b_id == uid)
            .values(user_b_id=DELETED_USER_PLACEHOLDER)
        )
        counts["trade_matches_anonymized"] = n + (res.rowcount or 0)

        res = conn.execute(
            update(db.trade_impressions_table)
            .where(db.trade_impressions_table.c.target_user_id == uid)
            .values(target_user_id=None)
        )
        counts["trade_impressions_target_anonymized"] = res.rowcount or 0

        res = conn.execute(
            update(db.bad_trade_flags_table)
            .where(db.bad_trade_flags_table.c.target_user_id == uid)
            .values(target_user_id=None, target_username=None)
        )
        counts["bad_trade_flags_target_anonymized"] = res.rowcount or 0

        res = conn.execute(
            update(db.app_feedback_table)
            .where(db.app_feedback_table.c.user_id == uid)
            .values(user_id=None, username=None)
        )
        counts["app_feedback_anonymized"] = res.rowcount or 0

        # Identity layer — the bound account plus any session-attached one.
        acct_ids = set()
        for row in conn.execute(
            select(db.accounts_table.c.account_id).where(
                db.accounts_table.c.sleeper_user_id == uid
            )
        ).fetchall():
            acct_ids.add(row.account_id)
        if account_id:
            acct_ids.add(account_id)
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
                db.users_table.c.sleeper_user_id == uid
            )
        )
        counts["users_deleted"] = res.rowcount or 0

    return counts
