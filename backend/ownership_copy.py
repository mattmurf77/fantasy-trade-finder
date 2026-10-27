"""I-2 send-time refusal copy, shared by the propose cores (`server.py`) and
team overhaul (`overhaul_service.py`, `overhaul_api.py`).

Pure strings and formatting: no Flask, no DB, no network. Lives here, not in
`server.py`, so overhaul can use it without importing the server. Final copy:
marketing via head-bizops, accepted by Product, 2026-10-26. A later swap is a
change here and nowhere else.

Curly ’ throughout, like the shipped refusals. `{assets}` is either the named
list ("A", "A and B", "A, B and C", with no serial comma) or, when ANY
offending asset has no name, the count subject below: a raw player or pick id
is never shown. `{verb}` agrees with it ("is" / "are"). `{team}’s` takes ’s
even after a final s ("Chris’s").

The unnamed-asset fallback is asset-aware: a player, a pick, or a mixed set
each get their own subject. The pick and asset subjects, and the receipt
variants (a prepare receipt, where nothing has been attempted yet, so "so
nothing was sent" would read oddly), are PLACEHOLDERS pending marketing
(I-2 post-launch). Marketing replaces the strings below and nothing else.
"""
from __future__ import annotations

import re

ASSET_NOT_OWNED = (
    "{assets} {verb} no longer on your roster, so nothing was sent. Find a new trade.")
COUNTERPARTY_NOT_OWNED = (
    "{assets} {verb} no longer on {team}’s roster, so nothing was sent. Find a new trade.")
COUNTERPARTY_NOT_OWNED_UNNAMED = (
    "{assets} {verb} no longer on the other manager’s roster, so nothing was sent. "
    "Find a new trade.")
ONE_UNNAMED_PLAYER = "A player in this trade"
N_UNNAMED_PLAYERS = "{n} players in this trade"
# PLACEHOLDER pending marketing (head-eng → head-bizops → marketing-lead), I-2 post-launch
ONE_UNNAMED_PICK = "A pick in this trade"
# PLACEHOLDER pending marketing (head-eng → head-bizops → marketing-lead), I-2 post-launch
N_UNNAMED_PICKS = "{n} picks in this trade"
# PLACEHOLDER pending marketing (head-eng → head-bizops → marketing-lead), I-2 post-launch
N_UNNAMED_ASSETS = "{n} assets in this trade"
# The prepare-receipt variants: the send-time sentence minus "so nothing was
# sent", because a receipt has attempted nothing yet. Used only by team
# overhaul's prepare-send receipt; every send result keeps the send-time copy.
# PLACEHOLDER pending marketing (head-eng → head-bizops → marketing-lead), I-2 post-launch
RECEIPT_ASSET_NOT_OWNED = "{assets} {verb} no longer on your roster. Find a new trade."
# PLACEHOLDER pending marketing (head-eng → head-bizops → marketing-lead), I-2 post-launch
RECEIPT_COUNTERPARTY_NOT_OWNED = (
    "{assets} {verb} no longer on {team}’s roster. Find a new trade.")
# PLACEHOLDER pending marketing (head-eng → head-bizops → marketing-lead), I-2 post-launch
RECEIPT_COUNTERPARTY_NOT_OWNED_UNNAMED = (
    "{assets} {verb} no longer on the other manager’s roster. Find a new trade.")
ROSTER_READ_FAILED = (
    "Couldn’t confirm rosters with {platform} right now, so nothing was sent. "
    "Try again in a moment.")


def roster_read_failed(platform: str) -> str:
    """The readable sentence for a send blocked because the live roster read
    failed (platforms-pm R3). `platform` is the display name: "Sleeper",
    "MFL", "ESPN"."""
    return ROSTER_READ_FAILED.format(platform=platform)


# The two FTF pick-id shapes a trade array can carry, without a league id:
# `generic_pick_{round}_{tier}` and `{league}_{season}_{round}_{orig}`
# (database.make_pick_id). The same shapes as server._is_ftf_pick_asset, which
# needs the league id and so can't be called from here. A player id is a bare
# digit string (or a defense's team code) with no underscore, so it matches
# neither. The one difference: this also accepts ANOTHER league's pick id,
# which no trade array carries. test_i2_copy_followups pins the two together.
_GENERIC_PICK_ID_PREFIX = "generic_pick_"
_OWNED_PICK_ID = re.compile(r".+_\d{4}_\d{1,2}_.+")


def is_pick_id(asset_id) -> bool:
    """True for an FTF draft-pick asset id (generic rung or owned pick)."""
    a = str(asset_id or "")
    return a.startswith(_GENERIC_PICK_ID_PREFIX) or _OWNED_PICK_ID.fullmatch(a) is not None


def _unnamed_subject(assets) -> str:
    """The count subject used when ANY offending asset has no name. It
    describes all of `assets` (the count covers them all): players, picks, or
    a mix."""
    n = len(assets)
    picks = sum(1 for a in assets if is_pick_id(a))
    if picks == 0:
        return ONE_UNNAMED_PLAYER if n == 1 else N_UNNAMED_PLAYERS.format(n=n)
    if picks == n:
        return ONE_UNNAMED_PICK if n == 1 else N_UNNAMED_PICKS.format(n=n)
    return N_UNNAMED_ASSETS.format(n=n)


def refusal_message(side: str, assets, names, counterparty_name=None, *, receipt: bool = False) -> str:
    """The `asset_not_owned` (side "give") / `counterparty_asset_not_owned`
    (side "receive") sentence for `assets` (offending ids). `names` maps id ->
    display name. If any id has no name, the message counts instead of naming
    (players, picks, or assets, per `_unnamed_subject`). `receipt=True` gives
    the prepare-receipt variant, without "so nothing was sent"."""
    assets = [str(a) for a in assets]
    labels = [(names or {}).get(a) for a in assets]
    if all(labels):
        labels = [str(n) for n in labels]
        listed = labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} and {labels[-1]}"
    else:
        listed = _unnamed_subject(assets)
    verb = "is" if len(assets) == 1 else "are"
    if side == "give":
        return (RECEIPT_ASSET_NOT_OWNED if receipt else ASSET_NOT_OWNED).format(
            assets=listed, verb=verb)
    if counterparty_name:
        return (RECEIPT_COUNTERPARTY_NOT_OWNED if receipt else COUNTERPARTY_NOT_OWNED).format(
            assets=listed, verb=verb, team=counterparty_name)
    return (RECEIPT_COUNTERPARTY_NOT_OWNED_UNNAMED if receipt
            else COUNTERPARTY_NOT_OWNED_UNNAMED).format(assets=listed, verb=verb)
