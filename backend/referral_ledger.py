"""Referral loop L7 — the referral ledger's server side.

Spec: docs/plans/referral-loop/prd.md @ 91f1cc29 (FR-6, FR-13–FR-20, §7,
§8.1, §8.4, §9), the event grant PR #350 (C1–C9) and engagement-eng's L7
design (docs/plans/org-bringup/leads/engagement-eng-l7.md).

The `referrals` table is the ledger: one row per minted invite id (`t`),
claimed by the first invitee and joined by siblings for the rest (§7.6).
Everything here is behind `growth.referral_ledger` (default OFF). The SQL
lives in backend/database.py; this module holds the rules.
"""
from __future__ import annotations

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
