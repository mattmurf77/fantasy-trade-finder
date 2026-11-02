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
    approved strings: legal's (G7, G8), the approved G2 / G20 / 8i lines, and
    marketing-lead's final Part B (`marketing-lead-copy.md` addendum 17 §B,
    2026-11-01). They are served whenever the capability is.
    `_SLEEPER_SLOTS_DRAFT` holds any slot still awaiting approved words; such
    a slot is served only in `submit` mode (in `handoff` the client uses its
    own neutral fallback). Today it is empty: every slot is final.
  * **Result and refusal messages** (`message`, `result_copy`), returned in
    the move route's `title` / `lines` / `message`. Final (addendum 17 §B,
    and the 8c / 8i / I-2 lines reused verbatim from the trade send). The one
    remaining draft, the MFL/ESPN withdrawal notice, is marked where it is.

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
MFL_ROSTER_MOVES_V1 = "mfl-roster-moves-v1"
MFL_ROSTER_MOVES_V2 = "mfl-roster-moves-v2"
ESPN_ROSTER_MOVES_V1 = "espn-roster-moves-v1"
ESPN_ROSTER_MOVES_V2 = "espn-roster-moves-v2"

# The version the server shows and accepts, per platform. MFL and ESPN have
# none until their texts are final (legal R28.27: once each write path is
# verified against a test league). With no current version no grant can be
# recorded for them, and they stay `unsupported`.
CURRENT_CONSENT_VERSION: dict[str, str] = {"sleeper": SLEEPER_ROSTER_MOVES_V1}

# Versions whose words are still DRAFT. A draft is NEVER served: consent_block
# refuses it even if CURRENT_CONSENT_VERSION pointed at it (pinned by test).
# A version leaves this set only when legal makes its text final.
DRAFT_CONSENT_VERSIONS = frozenset({MFL_ROSTER_MOVES_V1, MFL_ROSTER_MOVES_V2,
                                    ESPN_ROSTER_MOVES_V1, ESPN_ROSTER_MOVES_V2})

PLATFORM_LABEL = {"sleeper": "Sleeper", "mfl": "MFL", "espn": "ESPN"}

# ── Consent texts (R15.3 / R28.26 2a) ────────────────────────────────────────
# One entry per (platform, copy_version, locale) holding EVERY field the
# consent block shows: title, body, checkbox_label, this_move, button_label
# and links. Each entry is hash-pinned whole (test_platform_write_consent.py).
# NEVER edit one in place: a material change is a new version, and everyone
# re-consents. Each platform's texts are written out for that platform, never
# a find-and-replace of "Sleeper" (R28.26 2b).
#
# Legal's "Terms · Privacy" row under the step (R15.8), sent as `links`
# (contract §2): the app's own pages, as the app opens them from Sign in and
# Settings › About.
_APP_ORIGIN = "https://fantasy-trade-finder.onrender.com"
_LINKS = ({"label": "Terms", "url": f"{_APP_ORIGIN}/terms"},
          {"label": "Privacy", "url": f"{_APP_ORIGIN}/privacy"})
CONSENT_LINKS = _LINKS
_THIS_MOVE = "This move: {cta} in {league}."           # R15.8 D10(d); the client fills it
_MAKE_THE_MOVE = "Make the move"
_WINDOW = ("Your OK lasts 7 days. You'll still confirm every move. Turn it off any time "
           "in Settings › Leagues › Stop roster moves.")

CONSENT_TEXTS: dict[tuple[str, str, str], dict] = {
    # Sleeper: legal-final, R15.8 (legal-lead.md:858-875), verbatim. Bullet 3's
    # "(R15.7(c) [PRO]: keep or drop)" is legal's note, not UI text. v2 has no
    # "You can cancel a pending claim..." sentence until capture Q7b says so.
    ("sleeper", SLEEPER_ROSTER_MOVES_V1, LOCALE): {
        "title": "Let Fleeced make roster moves in Sleeper?",
        "body": [
            "Fleeced will add and drop players in your Sleeper leagues for you, using the "
            "Sleeper sign-in you connected.",
            "Moves are final on Sleeper. Fleeced can't undo them, and a player you drop can "
            "be picked up by another team.",
            "This uses an unofficial Sleeper connection, so it could stop working at any time.",
            _WINDOW,
        ],
        "checkbox_label": ("I authorize Fleeced to add and drop players in my Sleeper "
                           "leagues for the next 7 days."),
        "this_move": _THIS_MOVE,
        "button_label": _MAKE_THE_MOVE,
        "links": _LINKS,
    },
    ("sleeper", SLEEPER_ROSTER_MOVES_V2, LOCALE): {
        "title": "Let Fleeced make roster moves in Sleeper?",
        "body": [
            "Fleeced will add and drop players, and place waiver claims, in your Sleeper "
            "leagues for you, using the Sleeper sign-in you connected.",
            "Moves are final on Sleeper and Fleeced can't undo them. A player you drop can be "
            "picked up by another team. A waiver claim runs on Sleeper's schedule and spends "
            "any bid you set.",
            "This uses an unofficial Sleeper connection, so it could stop working at any time.",
            _WINDOW,
        ],
        "checkbox_label": ("I authorize Fleeced to add and drop players and place waiver "
                           "claims in my Sleeper leagues for the next 7 days."),
        "this_move": _THIS_MOVE,
        "button_label": _MAKE_THE_MOVE,
        "links": _LINKS,
    },
    # MFL: DRAFT (legal R28.27 item 3). No "unofficial connection" bullet: MFL
    # documents its import API (legal re-checks it after the capture).
    ("mfl", MFL_ROSTER_MOVES_V1, LOCALE): {
        "title": "Let Fleeced make roster moves in MFL?",
        "body": [
            "Fleeced will add and drop players in your MFL leagues for you, using the MFL "
            "sign-in you connected.",
            "Moves are final on MFL. Fleeced can't undo them, and a player you drop can be "
            "picked up by another team.",
            _WINDOW,
        ],
        "checkbox_label": ("I authorize Fleeced to add and drop players in my MFL leagues "
                           "for the next 7 days."),
        "this_move": _THIS_MOVE,
        "button_label": _MAKE_THE_MOVE,
        "links": _LINKS,
    },
    ("mfl", MFL_ROSTER_MOVES_V2, LOCALE): {
        "title": "Let Fleeced make roster moves in MFL?",
        "body": [
            "Fleeced will add and drop players, and place waiver claims, in your MFL leagues "
            "for you, using the MFL sign-in you connected.",
            "Moves are final on MFL and Fleeced can't undo them. A player you drop can be "
            "picked up by another team. A waiver claim runs on your league's waiver schedule "
            "and spends any bid you set.",
            _WINDOW,
        ],
        "checkbox_label": ("I authorize Fleeced to add and drop players and place waiver "
                           "claims in my MFL leagues for the next 7 days."),
        "this_move": _THIS_MOVE,
        "button_label": _MAKE_THE_MOVE,
        "links": _LINKS,
    },
    # ESPN: DRAFT (legal R28.27 item 3). Keeps the unofficial-connection bullet
    # (R15.7(c) [PRO], as for Sleeper).
    ("espn", ESPN_ROSTER_MOVES_V1, LOCALE): {
        "title": "Let Fleeced make roster moves in ESPN?",
        "body": [
            "Fleeced will add and drop players in your ESPN leagues for you, using the ESPN "
            "sign-in you connected.",
            "Moves are final on ESPN. Fleeced can't undo them, and a player you drop can be "
            "picked up by another team.",
            "This uses an unofficial ESPN connection, so it could stop working at any time.",
            _WINDOW,
        ],
        "checkbox_label": ("I authorize Fleeced to add and drop players in my ESPN leagues "
                           "for the next 7 days."),
        "this_move": _THIS_MOVE,
        "button_label": _MAKE_THE_MOVE,
        "links": _LINKS,
    },
    ("espn", ESPN_ROSTER_MOVES_V2, LOCALE): {
        "title": "Let Fleeced make roster moves in ESPN?",
        "body": [
            "Fleeced will add and drop players, and place waiver claims, in your ESPN leagues "
            "for you, using the ESPN sign-in you connected.",
            "Moves are final on ESPN and Fleeced can't undo them. A player you drop can be "
            "picked up by another team. A waiver claim runs on your league's waiver schedule "
            "and spends any bid you set.",
            "This uses an unofficial ESPN connection, so it could stop working at any time.",
            _WINDOW,
        ],
        "checkbox_label": ("I authorize Fleeced to add and drop players and place waiver "
                           "claims in my ESPN leagues for the next 7 days."),
        "this_move": _THIS_MOVE,
        "button_label": _MAKE_THE_MOVE,
        "links": _LINKS,
    },
}


def has_consent_text(platform: str, copy_version: str, locale: str) -> bool:
    """A version the server may accept: present, and not a DRAFT."""
    return ((platform, copy_version, locale) in CONSENT_TEXTS
            and copy_version not in DRAFT_CONSENT_VERSIONS)


# Why consent is being asked (contract §2 `reason`; fa_move_consent_shown's).
CONSENT_REASONS = ("first", "lapsed", "version", "withdrawn")


def consent_block(platform: str, locale: str = LOCALE, *, reason: str | None = None) -> dict | None:
    """The contract §2 `consent` block for the platform's CURRENT version, or
    None when the platform has no final consent text (the client then hands
    off, ux-lead F4). A DRAFT version is never served. `reason` is included
    only when the server knows it."""
    version = CURRENT_CONSENT_VERSION.get(platform)
    if not version or not has_consent_text(platform, version, locale):
        return None
    text = CONSENT_TEXTS[(platform, version, locale)]
    block = {"copy_version": version, "locale": locale, "title": text["title"],
             "body": list(text["body"]), "checkbox_label": text["checkbox_label"],
             "this_move": text["this_move"], "button_label": text["button_label"],
             "links": [dict(link) for link in text["links"]]}
    if reason in CONSENT_REASONS:
        block["reason"] = reason
    return block


# ── Settings (G19, approved: R15.8 :856 status line; R15.2.6 notice) ─────────
STATUS_LINE = "Roster moves: on until {date}"
STOP_LABEL = "Stop roster moves"
# The withdrawal notice per (platform, copy_version). Sleeper's is R15.2.6,
# verbatim, for both versions. MFL / ESPN are DRAFT (legal R28.27 item 3)
# and, like their consent texts, never served while their versions are drafts.
WITHDRAWAL_NOTICES: dict[tuple[str, str], str] = {
    ("sleeper", SLEEPER_ROSTER_MOVES_V1): (
        "Roster moves are off. Fleeced won't add or drop players until you agree again. "
        "Moves already made stay in Sleeper."),
    ("sleeper", SLEEPER_ROSTER_MOVES_V2): (
        "Roster moves are off. Fleeced won't add or drop players until you agree again. "
        "Moves already made stay in Sleeper."),
    ("mfl", MFL_ROSTER_MOVES_V1): (
        "Roster moves in MFL are off. Fleeced won't add or drop players there until you agree "
        "again. Moves already made stay in MFL."),
    ("mfl", MFL_ROSTER_MOVES_V2): (
        "Roster moves in MFL are off. Fleeced won't add or drop players or place waiver claims "
        "there until you agree again. Moves already made stay in MFL."),
    ("espn", ESPN_ROSTER_MOVES_V1): (
        "Roster moves in ESPN are off. Fleeced won't add or drop players there until you agree "
        "again. Moves already made stay in ESPN."),
    ("espn", ESPN_ROSTER_MOVES_V2): (
        "Roster moves in ESPN are off. Fleeced won't add or drop players or place waiver claims "
        "there until you agree again. Moves already made stay in ESPN."),
}
# A platform with no final version gets R15.2.6's own first sentence: approved
# words, true on any platform, and never a draft. Nothing can be withdrawn
# there anyway: with no version, no grant can exist.
_NOTICE_NO_FINAL_TEXT = "Roster moves are off."


def withdrawal_notice(platform: str) -> str:
    version = CURRENT_CONSENT_VERSION.get(platform)
    if not version or version in DRAFT_CONSENT_VERSIONS:
        return _NOTICE_NO_FINAL_TEXT
    return WITHDRAWAL_NOTICES[(platform, version)]


# ── move.copy (contract §7) ──────────────────────────────────────────────────
_SLEEPER_SLOTS_FINAL = {
    # G2, approved (s351.connect, consent.md :78).
    "connect_line": "Connect your Sleeper sign-in to make moves from here.",
    # marketing-lead addendum 17 §B (final, 2026-11-01). "Keep" rows keep the
    # words the drafts already had.
    "header_add": "Add {name}",                                         # G24
    "header_claim": "Claim {name}",                                     # G24
    "cta_add": "Add {add}",                                             # G6
    "cta_add_drop": "Add {add}, drop {drop}",                           # G6
    "cta_claim": "Claim {add} for {bid}",                               # G6
    "cta_claim_drop": "Claim {add} for {bid}, drop {drop}",             # G6
    "cta_claim_no_bid": "Claim {add}",                                  # G6, priority waivers
    "cta_claim_drop_no_bid": "Claim {add}, drop {drop}",                # G6, priority waivers
    "league_line": "In {league}",                                       # G22
    "window_line": "Roster moves: on until {date}",                     # G9 (= Settings' line)
    "turn_off": "Turn off",
    "open_platform": "Open in Sleeper to claim",                        # #509's button
    "handoff_footer": "You'll finish this move in Sleeper.",            # G1
    "verify_line": "Verify your Sleeper sign-in to make moves from here.",  # G3
    "other_account_line": ("The Sleeper account you connected isn't in {league}. "
                           "Connect the one that owns your team."),     # F3
    "not_sent_line": "Couldn't reach Sleeper right now, so nothing was sent.",  # G15 (8c)
    "unknown_body": ("Couldn't confirm whether this move reached Sleeper. Check your roster "
                     "and claims in Sleeper before you make it again."),  # G16
    "unavailable_line": ("Moves from Fleeced aren't available right now. You can still make "
                         "this move in Sleeper."),                     # F4
    "still_sending": "Still sending to Sleeper…",                       # state 7
    # G7, legal-final (R15.8 D10(b)).
    "finality": "Final on Sleeper. Fleeced can't undo it.",
    # G8, legal-final (R15.1 :766), in its forms (contract §7): with a drop,
    # without one, and "Bid: ${n}" as its own line the client shows only when
    # the claim has a bid (the client's `{bid}` carries the "$").
    "waiver_line": ("This places a waiver claim for {add} (dropping {drop} if it clears). "
                    "Sleeper processes it on its waiver schedule."),
    "waiver_line_no_drop": ("This places a waiver claim for {add}. "
                            "Sleeper processes it on its waiver schedule."),
    "bid_line": "Bid: {bid}",
    # G20, approved (s351.secondary, consent.md :132).
    "do_in_platform": "Do it in Sleeper instead",
    # G16's title reuses 8i (mobile/src/utils/sendOutcomeCopy.ts:9).
    "unknown_title": "Check before resending",
}

# Slots still awaiting approved words: marked DRAFT here, served only in
# `submit` mode. Empty since addendum 17 §B made every slot final.
_SLEEPER_SLOTS_DRAFT: dict[str, str] = {}

# Keys the client knows (contract §7); a test pins both dicts against it.
MOVE_COPY_KEYS = frozenset({
    "header_add", "header_claim", "cta_add", "cta_add_drop", "cta_claim", "cta_claim_drop",
    "cta_claim_no_bid", "cta_claim_drop_no_bid", "league_line", "finality", "waiver_line",
    "waiver_line_no_drop", "bid_line", "window_line", "turn_off", "do_in_platform",
    "open_platform", "handoff_footer", "connect_line", "verify_line", "other_account_line",
    "not_sent_line", "unknown_title", "unknown_body", "unavailable_line", "still_sending",
})


# MFL / ESPN slots: DRAFT (legal R28.27 item 3), written per platform. Never
# served: those platforms are `unsupported` until their write paths are
# verified, and move_copy below returns nothing for them. The client fills
# `{bid}` with its "$".
PLATFORM_SLOTS_DRAFT: dict[str, dict[str, str]] = {
    "mfl": {
        "finality": "Final on MFL. Fleeced can't undo it.",
        "waiver_line": ("This places a waiver claim for {add} (dropping {drop} if it clears). "
                        "MFL processes it on your league's waiver schedule."),
        "waiver_line_no_drop": ("This places a waiver claim for {add}. MFL processes it on "
                                "your league's waiver schedule."),
        "bid_line": "Bid: {bid}",
    },
    "espn": {
        "finality": "Final on ESPN. Fleeced can't undo it.",
        "waiver_line": ("This places a waiver claim for {add} (dropping {drop} if it clears). "
                        "ESPN processes it on your league's waiver schedule."),
        "waiver_line_no_drop": ("This places a waiver claim for {add}. ESPN processes it on "
                                "your league's waiver schedule."),
        "bid_line": "Bid: {bid}",
    },
}


def move_copy(platform: str, *, include_drafts: bool) -> dict:
    """The capability's `move.copy` map. Sleeper only today: MFL and ESPN are
    `unsupported`, where the client shows NO_ADD_REASON and reads no slot, and
    their slots are still drafts (PLATFORM_SLOTS_DRAFT), never served."""
    if platform != "sleeper":
        return {}
    out = dict(_SLEEPER_SLOTS_FINAL)
    if include_drafts:
        out.update(_SLEEPER_SLOTS_DRAFT)
    return out


# Per-row override lines (scope §B6(b)). Final (addendum 17 §B).
ROW_LINE_UNCONFIRMED = ("A recent move for this player isn't confirmed. Check {platform} "
                        "before you make it again.")
ROW_LINE_PENDING_CLAIM = "A claim for this player is already pending in {platform}."


def row_line(reason: str, platform: str) -> str:
    tpl = ROW_LINE_PENDING_CLAIM if reason == "pending_claim" else ROW_LINE_UNCONFIRMED
    return tpl.format(platform=PLATFORM_LABEL.get(platform, platform))


# ── Refusal and failure messages (the move route's `message` / `title`) ──────
# Keyed by the code SUFFIX (contract §4); `{platform}` is the display name.
# Final: marketing-lead addendum 17 §B (2026-11-01), "Keep" rows unchanged.
# Never "we" / "our", and never a "try again" where the outcome is unknown or
# a move is in progress (pinned). `{remaining}` is filled HERE, so its "$" is
# written here; `{bid}` in the slots is the client's and carries its own.
_UNAVAILABLE = ("Moves from Fleeced aren't available right now, so nothing was sent. "
                "You can still make this move in {platform}.")
_UNCONFIRMED = ("Couldn't confirm whether this move reached {platform}. Check your roster "
                "and claims in {platform} before you make it again.")
_MESSAGES = {
    "feature_disabled": _UNAVAILABLE,                                   # G14, one line for both
    "bad_request": "Nothing was sent. Close this and start the move again.",
    "verification_required": ("Nothing was sent. Verify your {platform} sign-in to make moves "
                              "from here."),
    "not_linked": "Connect your {platform} sign-in to make moves from here.",   # G2 (Sleeper: approved)
    "not_linked_other_account": ("The {platform} account you connected isn't in {league}. "
                                 "Connect the one that owns your team. Nothing was sent."),
    "expired": ("Your {platform} sign-in has expired, so nothing was sent. Sign in again to "
                "make moves from here."),
    "consent_required": "Nothing was sent. Agree to roster moves to make this move.",
    "roster_full_drop_required": ("Your roster is full, so nothing was sent. Pick a player to "
                                  "drop."),                             # 10a
    "asset_not_owned": ("{drop} is no longer on your roster, so nothing was sent. Pick another "
                        "player to drop."),                             # 10b
    "player_unavailable": "{add} is no longer a free agent, so nothing was sent.",  # 10c
    "player_already_yours": "{add} is already on your roster, so nothing was sent.",
    "waiver_bid_over_budget": ("Your bid is more than the ${remaining} you have left, so "
                               "nothing was sent. Lower it to make the claim."),  # 10d
    "move_kind_changed": ("{add}'s waiver status changed, so nothing was sent. The button now "
                          "shows the right move."),                     # 10e
    "waiver_claim_unsupported": ("{add} is on waivers, and waiver claims can't be made from "
                                 "here right now, so nothing was sent. Claim in {platform} "
                                 "instead."),                           # G18
    "rejected": ("{platform} turned down Fleeced's connection, so nothing changed. Connect "
                 "again to make moves."),                                           # G17
    # 8c/8d (marketing addendum 10), verbatim: the trade send's not-sent line.
    "write_failed_network": ("Couldn't reach {platform} right now, so nothing was sent. "
                             "Try again in a moment."),
    # G13 (10f): R15.1's rejection line with 8a's ending; legal OKs it.
    "write_failed": ("{platform} didn't accept this move, so nothing changed. You can still "
                     "try it in {platform}."),
    "unconfigured": _UNAVAILABLE,                                       # G14 (10g)
    "outcome_unknown": _UNCONFIRMED,                                    # G16 (state 12)
    "move_in_progress": ("A recent move for {add} isn't confirmed yet. Check your roster in "
                         "{platform} before you make it again."),
    "move_in_progress_pending_claim": ("A claim for {add} is already pending in {platform}. "
                                       "Check your claims there before you make another."),
    "internal_error": _UNCONFIRMED,             # to the user, a 500 is an unknown outcome
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
    """(title, lines) for a 200. Final (addendum 17 §B; R15.1's success line).
    Says exactly what the platform reported: a claim is "submitted", never
    "added"; a partial names each half as reported, then says where to look
    (K-F6)."""
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
        lines.append(f"Check your roster in {label}.")
        return "Part of this move was made", lines
    if drop:
        return "Done", [f"{add} added, {drop} dropped in {league}."]
    return "Done", [f"{add} added in {league}."]
