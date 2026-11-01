"""fa_move_copy.py — every user-facing string of D1 free-agent moves.

D1 (docs/plans/sleeper-fa-write/contract.md, scope.md §B4): the server
authors all of the claim sheet's move copy, so legal's launch minimum,
marketing's words and MFL/ESPN wording can land without a binary. The client
bakes in only neutral fallbacks and never consent text. Pure strings and
formatting: no Flask, no DB, no network.

Three kinds of string live here:

  * **Consent texts** (`CONSENT_TEXTS`), keyed by (platform, copy_version,
    locale). Legal-final, verbatim from legal-lead R15.8 (2026-10-20). A
    version is NEVER edited in place: changed wording is a new version, and
    `test_platform_write_consent.py` pins each text by hash (the old S22).
    `CURRENT_CONSENT_VERSION` is the version the server shows and accepts
    (consent.md's `SLEEPER_ROSTER_MOVES_CONSENT_VERSION`); bumping it
    invalidates every older grant. v1 while claims are refused; v2 is
    required, in the same release, before claims are enabled (R15.8 D5).
  * **`move.copy` slots** (contract §7). `_SLEEPER_SLOTS_FINAL` holds the
    strings legal or marketing already approved (G2, G7, G8, G20, and 8i's
    title reused for G16); they are served whenever the capability is.
    `_SLEEPER_SLOTS_DRAFT` holds PLACEHOLDER DRAFTS written by platforms-eng
    so every slot has something to review. They are NOT approved copy:
    marketing's words replace them (via head-product), and until then they
    are served only in `submit` mode, which cannot happen before the
    post-capture commit and the operator's flip. In `handoff` mode the client
    falls back to its own neutral wording for every missing slot.
  * **Result and refusal messages** (`message`, `result_copy`), returned in
    the move route's `title` / `lines` / `message`. Drafts except where
    marked (the 8c / 8i / I-2 lines reused verbatim from the trade send).
    Reached only through the move route, which 404s until the flip.

Straight apostrophes, as R15.8 writes them. Templates use `{add}`, `{drop}`,
`{bid}`, `{league}`, `{date}`, `{name}`, `{cta}` for the CLIENT to fill
(contract §7). The client fills `{bid}` WITH its dollar sign ("$7"), so a
template never writes its own `$`; `{date}` is a short date with no time. The
server-filled strings below (results, refusals, the Settings status line) are
formatted here.
"""
from __future__ import annotations

from . import ownership_copy as _ownership_copy

LOCALE = "en-US"

SLEEPER_ROSTER_MOVES_V1 = "sleeper-roster-moves-v1"
SLEEPER_ROSTER_MOVES_V2 = "sleeper-roster-moves-v2"

# The version the server shows and accepts, per platform. MFL and ESPN have
# none until legal-lead writes their wording (scope §E): no grant can be
# recorded for them, so they can never be in `submit` mode.
CURRENT_CONSENT_VERSION: dict[str, str] = {"sleeper": SLEEPER_ROSTER_MOVES_V1}

PLATFORM_LABEL = {"sleeper": "Sleeper", "mfl": "MFL", "espn": "ESPN"}

# ── Consent texts: legal-final, R15.8 (legal-lead.md:858-875), verbatim ──────
# Bullet 3's "(R15.7(c) [PRO]: keep or drop)" is legal's note, not UI text;
# the bullet ships until a professional says drop it (a new version then).
# v2 bullet 2 has no "You can cancel a pending claim..." sentence: R15.8 adds
# it only once platforms-pm verifies cancelling (capture Q7b, not yet known).
_TITLE = "Let Fleeced make roster moves in Sleeper?"
_UNOFFICIAL = ("This uses an unofficial Sleeper connection, so it could stop working "
               "at any time.")
_WINDOW = ("Your OK lasts 7 days. You'll still confirm every move. Turn it off any time "
           "in Settings › Leagues › Stop roster moves.")
_THIS_MOVE = "This move: {cta} in {league}."           # R15.8 D10(d); the client fills it
_MAKE_THE_MOVE = "Make the move"

CONSENT_TEXTS: dict[tuple[str, str, str], dict] = {
    ("sleeper", SLEEPER_ROSTER_MOVES_V1, LOCALE): {
        "title": _TITLE,
        "body": [
            "Fleeced will add and drop players in your Sleeper leagues for you, using the "
            "Sleeper sign-in you connected.",
            "Moves are final on Sleeper. Fleeced can't undo them, and a player you drop can "
            "be picked up by another team.",
            _UNOFFICIAL,
            _WINDOW,
        ],
        "checkbox_label": ("I authorize Fleeced to add and drop players in my Sleeper "
                           "leagues for the next 7 days."),
        "this_move": _THIS_MOVE,
        "button_label": _MAKE_THE_MOVE,
    },
    ("sleeper", SLEEPER_ROSTER_MOVES_V2, LOCALE): {
        "title": _TITLE,
        "body": [
            "Fleeced will add and drop players, and place waiver claims, in your Sleeper "
            "leagues for you, using the Sleeper sign-in you connected.",
            "Moves are final on Sleeper and Fleeced can't undo them. A player you drop can be "
            "picked up by another team. A waiver claim runs on Sleeper's schedule and spends "
            "any bid you set.",
            _UNOFFICIAL,
            _WINDOW,
        ],
        "checkbox_label": ("I authorize Fleeced to add and drop players and place waiver "
                           "claims in my Sleeper leagues for the next 7 days."),
        "this_move": _THIS_MOVE,
        "button_label": _MAKE_THE_MOVE,
    },
}


def has_consent_text(platform: str, copy_version: str, locale: str) -> bool:
    return (platform, copy_version, locale) in CONSENT_TEXTS


# Legal's "Terms · Privacy" row under the consent step (R15.8 v1), sent as the
# block's optional `links` (contract §2). The app's own pages, the same URLs
# the app opens from Sign in and Settings › About.
_APP_ORIGIN = "https://fantasy-trade-finder.onrender.com"
CONSENT_LINKS = ({"label": "Terms", "url": f"{_APP_ORIGIN}/terms"},
                 {"label": "Privacy", "url": f"{_APP_ORIGIN}/privacy"})

# Why consent is being asked (contract §2 `reason`; fa_move_consent_shown's).
CONSENT_REASONS = ("first", "lapsed", "version", "withdrawn")


def consent_block(platform: str, locale: str = LOCALE, *, reason: str | None = None) -> dict | None:
    """The contract §2 `consent` block for the platform's CURRENT version, or
    None when the platform has no consent text (the client then hands off,
    ux-lead F4). `reason` is included only when the server knows it."""
    version = CURRENT_CONSENT_VERSION.get(platform)
    text = CONSENT_TEXTS.get((platform, version, locale)) if version else None
    if text is None:
        return None
    block = {"copy_version": version, "locale": locale, "title": text["title"],
             "body": list(text["body"]), "checkbox_label": text["checkbox_label"],
             "this_move": text["this_move"], "button_label": text["button_label"],
             "links": [dict(link) for link in CONSENT_LINKS]}
    if reason in CONSENT_REASONS:
        block["reason"] = reason
    return block


# ── Settings (G19, approved: R15.8 :856 status line; R15.2.6 notice) ─────────
STATUS_LINE = "Roster moves: on until {date}"
STOP_LABEL = "Stop roster moves"
_WITHDRAWAL_NOTICE = {
    # R15.2.6, verbatim.
    "sleeper": ("Roster moves are off. Fleeced won't add or drop players until you agree "
                "again. Moves already made stay in Sleeper."),
}
_WITHDRAWAL_NOTICE_DRAFT = "Roster moves are off. Fleeced won't make moves for you until you agree again."  # DRAFT: MFL/ESPN


def withdrawal_notice(platform: str) -> str:
    return _WITHDRAWAL_NOTICE.get(platform, _WITHDRAWAL_NOTICE_DRAFT)


# ── move.copy (contract §7) ──────────────────────────────────────────────────
_SLEEPER_SLOTS_FINAL = {
    # G2, approved (s351.connect, consent.md :78).
    "connect_line": "Connect your Sleeper sign-in to make moves from here.",
    # G7, legal-final (R15.8 D10(b)).
    "finality": "Final on Sleeper. Fleeced can't undo it.",
    # G8, legal-final (R15.1 :766, "Bid: ${n}" appended when there's a bid;
    # the client's `{bid}` carries the "$", contract §7). FLAGGED in the build
    # report: R15.1's line has two conditional halves and contract §7 gives it
    # ONE slot. With no drop the client drops the slot for its fallback
    # (contract §7); with no bid it fills "$0", wrong for a priority-waiver
    # league. Claims are off (`claims: false`) until D5 holds, so it is never
    # rendered before that is settled.
    "waiver_line": ("This places a waiver claim for {add} (dropping {drop} if it clears). "
                    "Sleeper processes it on its waiver schedule. Bid: {bid}"),
    # G20, approved (s351.secondary, consent.md :132).
    "do_in_platform": "Do it in Sleeper instead",
    # G16's title reuses 8i (mobile/src/utils/sendOutcomeCopy.ts:9).
    "unknown_title": "Check before resending",
}

_SLEEPER_SLOTS_DRAFT = {
    # PLACEHOLDER DRAFTS (platforms-eng, 2026-11-01). NOT approved copy:
    # marketing-lead's words replace every one (scope §G). Served only in
    # `submit` mode.
    "header_add": "Add {name}",                                         # G24
    "header_claim": "Claim {name}",                                     # G24
    "cta_add": "Add {add}",                                             # G6
    "cta_add_drop": "Add {add}, drop {drop}",                           # G6
    "cta_claim": "Claim {add} for {bid}",                               # G6
    "cta_claim_drop": "Claim {add} for {bid}, drop {drop}",             # G6
    "league_line": "In {league}",                                       # G22
    "window_line": "Adds authorized until {date}",                      # G9 (consent.md :115)
    "turn_off": "Turn off",                                             # G9
    "open_platform": "Open in Sleeper to claim",                        # #509's CTA
    "handoff_footer": "You'll finish this move in Sleeper.",            # G1
    "verify_line": "Your Sleeper connection needs a quick check before you make moves from here.",  # G3
    "other_account_line": ("The Sleeper account you connected isn't in {league}. "
                           "Connect the one that owns your team."),     # F3
    "not_sent_line": "Couldn't reach Sleeper, so nothing was sent.",    # G15
    "unknown_body": ("We couldn't confirm whether this move reached Sleeper. Check your "
                     "roster in Sleeper before you try again."),        # G16
    "unavailable_line": "Moves from Fleeced aren't available right now.",  # F4
    "still_sending": "Still sending to Sleeper…",                       # state 7
}

# Keys the client knows (contract §7); a test pins both dicts against it.
MOVE_COPY_KEYS = frozenset({
    "header_add", "header_claim", "cta_add", "cta_add_drop", "cta_claim", "cta_claim_drop",
    "league_line", "finality", "waiver_line", "window_line", "turn_off", "do_in_platform",
    "open_platform", "handoff_footer", "connect_line", "verify_line", "other_account_line",
    "not_sent_line", "unknown_title", "unknown_body", "unavailable_line", "still_sending",
})


def move_copy(platform: str, *, include_drafts: bool) -> dict:
    """The capability's `move.copy` map. Sleeper only today: MFL and ESPN are
    `unsupported`, where the client shows NO_ADD_REASON and reads no slot."""
    if platform != "sleeper":
        return {}
    out = dict(_SLEEPER_SLOTS_FINAL)
    if include_drafts:
        out.update(_SLEEPER_SLOTS_DRAFT)
    return out


# Per-row override lines (scope §B6(b)). DRAFTS.
ROW_LINE_UNCONFIRMED = ("A recent move for this player wasn't confirmed. Check {platform} "
                        "before you try again.")
ROW_LINE_PENDING_CLAIM = "A claim for this player is already pending in {platform}."


def row_line(reason: str, platform: str) -> str:
    tpl = ROW_LINE_PENDING_CLAIM if reason == "pending_claim" else ROW_LINE_UNCONFIRMED
    return tpl.format(platform=PLATFORM_LABEL.get(platform, platform))


# ── Refusal and failure messages (the move route's `message` / `title`) ──────
# Keyed by the code SUFFIX (contract §4); `{platform}` is the display name.
# DRAFT unless marked. Never a "try again" where the outcome is unknown.
_MESSAGES = {
    "feature_disabled": "Moves from Fleeced aren't available right now.",
    "bad_request": "Something about this move didn't look right, so nothing was sent.",
    "verification_required": ("Verify your {platform} connection to make moves from here. "
                              "Nothing was sent."),
    "not_linked": "Connect your {platform} sign-in to make moves from here.",   # G2 (Sleeper: approved)
    "not_linked_other_account": ("The {platform} account you connected isn't in {league}. "
                                 "Connect the one that owns your team. Nothing was sent."),
    "expired": ("Your {platform} connection needs a quick check before you make moves from "
                "here. Nothing was sent."),
    "consent_required": "Agree to roster moves to make this move. Nothing was sent.",
    "roster_full_drop_required": "Your roster is full. Pick a player to drop. Nothing was sent.",
    "asset_not_owned": "{drop} is no longer on your roster, so nothing was sent.",
    "player_unavailable": "{add} was just picked up, so nothing was sent.",
    "player_already_yours": "{add} is already on your roster, so nothing was sent.",
    "waiver_bid_over_budget": ("Your bid is more than the ${remaining} you have left, so "
                               "nothing was sent."),
    "move_kind_changed": ("{add}'s status changed in {platform}, so nothing was sent. Check "
                          "the button before you tap again."),
    "waiver_claim_unsupported": ("{add} is on waivers, and claims from Fleeced aren't on yet. "
                                 "Nothing was sent. Claim in {platform} instead."),   # G18
    "rejected": ("{platform} turned down Fleeced's connection, so nothing changed. Connect "
                 "again to make moves."),                                           # G17
    # 8c/8d (marketing addendum 10), verbatim: the trade send's not-sent line.
    "write_failed_network": ("Couldn't reach {platform} right now, so nothing was sent. "
                             "Try again in a moment."),
    # R15.1's rejection line (G13 draft, consent.md :769).
    "write_failed": "{platform} didn't accept this move, so nothing changed. Try again in {platform}.",
    "unconfigured": "Moves from Fleeced aren't available right now.",              # G14
    "outcome_unknown": ("We couldn't confirm whether this move reached {platform}. Check your "
                        "roster in {platform} before you try again."),              # G16 body
    "move_in_progress": ("A recent move for {add} wasn't confirmed yet. Check {platform} "
                         "before you try again."),
    "move_in_progress_pending_claim": ("A claim for {add} is already pending in {platform}. "
                                       "Check {platform} before you try again."),
    "internal_error": ("Something went wrong on our side, so we can't confirm this move. "
                       "Check {platform} before you try again."),
}


def message(key: str, platform: str = "sleeper", **fmt) -> str:
    """The readable sentence for a refusal or failure. `kind` 'roster_read'
    uses the I-2 line verbatim (approved, ownership_copy.ROSTER_READ_FAILED)."""
    label = PLATFORM_LABEL.get(platform, "the platform")
    if key == "write_failed_roster_read":
        return _ownership_copy.roster_read_failed(label)
    values = {"add": "This player", "drop": "That player", "league": "this league",
              "remaining": "0"}
    values.update({k: v for k, v in fmt.items() if v not in (None, "")})
    return _MESSAGES[key].format(platform=label, **values)


# Titles for the outcome-unknown panel (state 12): 8i, reused (G16 title).
UNKNOWN_TITLE = "Check before resending"


def result_copy(*, status: str, result: str, platform: str, add: str, drop: str | None,
                league: str, added: list[str], dropped: list[str], bid: int | None) -> tuple[str, list[str]]:
    """(title, lines) for a 200. DRAFTS (G10/G11; R15.1's success line is the
    model). Says exactly what the platform reported: a claim is "submitted",
    never "added"; a partial names each half as reported (K-F6)."""
    label = PLATFORM_LABEL.get(platform, platform)
    if status == "pending":
        lines = [f"Your claim for {add} was submitted in {league}"
                 + (f", with a ${bid} bid." if bid is not None else ".")]
        if drop:
            lines.append(f"{drop} will be dropped if the claim clears.")
        lines.append(f"{label} processes it on its waiver schedule.")
        return "Claim submitted", lines
    if result == "partial":
        lines = []
        lines.append(f"{add} added in {league}." if added else f"{add} was not added.")
        if drop:
            lines.append(f"{drop} dropped." if dropped else f"{drop} was not dropped.")
        return "Partly done", lines
    if drop:
        return "Done", [f"{add} added, {drop} dropped in {league}."]
    return "Done", [f"{add} added in {league}."]
