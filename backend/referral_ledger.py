"""Referral loop L7 — the referral ledger's server side.

Spec: docs/plans/referral-loop/prd.md @ 91f1cc29 (FR-6, FR-13–FR-20, §7,
§8.1, §8.4, §9), the event grant PR #350 (C1–C9) and engagement-eng's L7
design (docs/plans/org-bringup/leads/engagement-eng-l7.md).

The `referrals` table is the ledger: one row per minted invite id (`t`),
claimed by the first invitee and joined by siblings for the rest (§7.6).
Everything here is behind `growth.referral_ledger` (default OFF). The SQL
lives in backend/database.py; this module holds the rules. The join
landing's helpers (server.INVITE_ID_RE, server._invite_status, the 30-day
window) are reused, never copied: server imports this module, so they are
imported lazily at call time.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import database as db
from . import feature_flags

log = logging.getLogger(__name__)

LEDGER_FLAG = "growth.referral_ledger"

# The closed InviteSurface set (PRD §8.1, §10 "Surface vocabulary"): the
# existing `surface` prop values plus `web_invite`. Stored in
# referrals.surface at mint.
INVITE_SURFACES: frozenset[str] = frozenset({
    "league_home", "matches_empty", "trades_banner", "members_overlay",
    "notif_empty", "web_invite",
})

# FR-6 / §7.9: mints per inviter per league per UTC day (assumed). The 11th
# is a 429 and the client falls back to the league-only link.
MINT_DAILY_CAP = 10

# §7.5: a landing open older than this is never league-matched. The id's
# own 30-day credit window (§7.1) is server._INVITE_ID_VALID_DAYS, reused.
LEAGUE_MATCH_OPEN_DAYS = 14

# The inviter's bell rows (FR-18, FR-19): marketing-lead's strings
# (docs/plans/referral-loop/marketing-inputs.md @ 91f1cc29 §A), verbatim.
# Title != body by rule (AC-18, AC-19). One dict so a copy change is one hunk.
COPY = {
    # gp.push.joined_inbox_title / gp.push.joined_inbox_body
    "joined_title": "@{new_username} joined Fleeced via your invite",
    "joined_body":  "Once they rank, trades with them can use their board, not just consensus.",
}


# ═══════════════════════════════════════════════════════════════════════════
# Attribution — a NEW user's first session (FR-13–FR-16, FR-18, FR-20)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FirstSession:
    """What the session-init daemon needs back from attribution.

    invited_by       the users.invited_by value upsert_user stores on INSERT:
                     the referrer's username when the ledger credited
                     someone (FR-13 step 5, server-derived), else the
                     client's legacy value, unverified (FR-15).
    signup_props     the `signup` event's props (FR-16), or None: flag off,
                     or not a new user (app_open carries none).
    inviter_user_id  FR-20: the credited referrer, whose coalesced
                     league_member_joined inbox row the fanout skips.
    legacy_notify    may the pre-ledger referral_joined path (a bell row from
                     invited_by alone) run? Only while the flag is OFF.
    """
    invited_by: str | None
    signup_props: dict | None
    inviter_user_id: str | None
    legacy_notify: bool


def attribute_first_session(*, is_new_user: bool, user_id: str, league_id: str,
                            league_platform: str, invite_id: str | None,
                            invited_by: str | None,
                            new_username: str) -> FirstSession:
    """FR-13–FR-16 + FR-18, run by the session-init daemon BEFORE upsert_user
    (so a credit's server-derived invited_by lands on the INSERT).

    Flag off → exactly today's behaviour: the client's invited_by, no props,
    the legacy referral_joined path. Flag on and an existing user → no
    credit, no props, no legacy row. Flag on and a new user → §7.4 credit by
    token (`invite_id`, the well-formed id from the body), else §7.5 league
    match, else nothing; the `signup` props say which.

    NEVER raises: any failure is logged and degrades to "not attributed"
    (with the flag on, the legacy row still never fires, FR-15).
    """
    try:
        if not feature_flags.is_enabled(LEDGER_FLAG):
            return FirstSession(invited_by, None, None, True)
        if not is_new_user:
            return FirstSession(invited_by, None, None, False)
        return _attribute(user_id=str(user_id), league_id=str(league_id),
                          league_platform=league_platform, invite_id=invite_id,
                          invited_by=invited_by, new_username=new_username)
    except Exception:
        log.exception("referral attribution failed (continuing)")
        return FirstSession(invited_by, None, None, False)


def _attribute(*, user_id, league_id, league_platform, invite_id, invited_by,
               new_username) -> FirstSession:
    # A repeat first session (the users INSERT failed after an earlier
    # credit) finds its own row: report it, credit and notify nothing again.
    prior = db.get_referral_for_referred(user_id)
    if prior is not None:
        return _result(prior, prior.get("attribution_method") or "token", None)

    credited, miss = None, None
    if invite_id:
        credited, miss = _credit_by_token(invite_id, user_id, league_id)
    if credited is None:
        credited = _credit_by_league_match(league_id, user_id, invited_by)
    if credited is None:
        props = {"attribution": "legacy_ref" if invited_by else "none",
                 "attribution_miss": miss}
        return FirstSession(invited_by, props, None, False)

    notified = _post_joined_row(credited, user_id, new_username)
    platform = (league_platform if str(credited["league_id"]) == league_id
                else db.get_league_platform(credited["league_id"]))
    db.record_event(
        str(credited["referrer_user_id"]), "referral_attributed",
        league_id=str(credited["league_id"]), source="api",
        props={"invite_id":          credited.get("share_token"),
               "referral_id":        credited["id"],
               "league_id":          str(credited["league_id"]),
               "attribution_method": credited["attribution_method"],
               "league_platform":    platform,
               "notified":           notified},
        platform="server", touch_user=False,
    )
    return _result(credited, credited["attribution_method"], miss)


def _result(row: dict, method: str, miss: str | None) -> FirstSession:
    names = db.get_user_names(str(row["referrer_user_id"])) or {}
    return FirstSession(
        invited_by=names.get("username") or None,
        signup_props={"attribution": method, "attribution_miss": miss},
        inviter_user_id=str(row["referrer_user_id"]),
        legacy_notify=False,
    )


def _credit_by_token(invite_id: str, user_id: str, league_id: str):
    """§7.4 steps 1–4. Returns (credited row | None, miss | None)."""
    from .server import _invite_status      # the join landing's 30-day rule
    row = db.get_referral_by_invite_token(invite_id)
    # Only a live minted row: its share_token IS the id (a sibling's token
    # can't match INVITE_ID_RE; a deleted referrer's share_token is NULLed).
    if row is None or row.get("share_token") != invite_id:
        return None, "unknown"
    row_league = str(row["league_id"])
    if _invite_status(row, row_league) != "valid":
        return None, "expired"
    if str(row["referrer_user_id"]) == user_id:
        return None, "unknown"
    # Step 3: the session's league was proven by resolve_session_input; any
    # other league is checked against the league_members snapshot.
    if row_league != league_id and not db.league_has_member(row_league, user_id):
        return None, "not_member"
    if not db.claim_referral(row["id"], user_id, "token"):
        if db.insert_referral_sibling(row, user_id) is None:
            return None, None   # this exact pair already exists: credited elsewhere
    return db.get_referral_for_referred(user_id), None


def _credit_by_league_match(league_id: str, user_id: str, invited_by: str | None):
    """§7.5. Candidates opened within 14 days, minted within 30, pending,
    unclaimed, referrer ≠ invitee. A legacy invited_by naming a candidate's
    referrer wins the tie; else the latest open."""
    from .server import _INVITE_ID_VALID_DAYS
    now = datetime.now(timezone.utc)
    cands = db.league_match_candidates(
        league_id, user_id,
        opened_since=(now - timedelta(days=LEAGUE_MATCH_OPEN_DAYS)).isoformat(),
        created_since=(now - timedelta(days=_INVITE_ID_VALID_DAYS)).isoformat())
    if invited_by:
        named = [c for c in cands
                 if (c.get("referrer_username") or "").lower() == invited_by.lower()]
        cands = named + [c for c in cands if c not in named]
    for cand in cands:          # newest open first; the next one if a race is lost
        if db.claim_referral(cand["id"], user_id, "league_match"):
            return db.get_referral_for_referred(user_id)
    return None


def _post_joined_row(credited: dict, user_id: str, new_username: str) -> bool:
    """FR-18: one referral_joined bell row for the inviter, title != body.
    Route unchanged (League). True when the row was written."""
    try:
        db.create_notification(
            user_id=str(credited["referrer_user_id"]), type_="referral_joined",
            title=COPY["joined_title"].format(new_username=new_username),
            body=COPY["joined_body"],
            metadata={"new_user_id":  user_id,
                      "new_username": new_username,
                      "league_id":    str(credited["league_id"]),
                      "referral_id":  credited["id"]},
        )
        return True
    except Exception as e:
        log.warning("referral_joined row failed (continuing): %s", e)
        return False
