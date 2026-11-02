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
"""
from __future__ import annotations

ASSET_NOT_OWNED = (
    "{assets} {verb} no longer on your roster, so nothing was sent. Find a new trade.")
COUNTERPARTY_NOT_OWNED = (
    "{assets} {verb} no longer on {team}’s roster, so nothing was sent. Find a new trade.")
COUNTERPARTY_NOT_OWNED_UNNAMED = (
    "{assets} {verb} no longer on the other manager’s roster, so nothing was sent. "
    "Find a new trade.")
ONE_UNNAMED_PLAYER = "A player in this trade"
N_UNNAMED_PLAYERS = "{n} players in this trade"
ROSTER_READ_FAILED = (
    "Couldn’t confirm rosters with {platform} right now, so nothing was sent. "
    "Try again in a moment.")
# Overhaul's per-asset send blockers: the shipped sentences, with the asset
# named (`asset_sentence`), never its raw id.
POOL_VIOLATION = "{asset} is outside your eligible pool."
ASSET_RESERVED_BY_OFFER = "{asset} is reserved by a live offer."
GIVE_OVERLAP = "{asset} is in two packages."


def roster_read_failed(platform: str) -> str:
    """The readable sentence for a send blocked because the live roster read
    failed (platforms-pm R3). `platform` is the display name: "Sleeper",
    "MFL", "ESPN"."""
    return ROSTER_READ_FAILED.format(platform=platform)


def asset_sentence(template: str, asset, names) -> str:
    """One of overhaul's per-asset blocker sentences (`POOL_VIOLATION`,
    `ASSET_RESERVED_BY_OFFER`, `GIVE_OVERLAP`) about `asset`, named from
    `names` (id -> display name), else `ONE_UNNAMED_PLAYER`: never a raw id."""
    name = (names or {}).get(str(asset))
    return template.format(asset=str(name) if name else ONE_UNNAMED_PLAYER)


def refusal_message(side: str, assets, names, counterparty_name=None) -> str:
    """The `asset_not_owned` (side "give") / `counterparty_asset_not_owned`
    (side "receive") sentence for `assets` (offending ids). `names` maps id ->
    display name. If any id has no name, the message counts instead of naming."""
    assets = [str(a) for a in assets]
    labels = [(names or {}).get(a) for a in assets]
    if all(labels):
        labels = [str(n) for n in labels]
        listed = labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} and {labels[-1]}"
    elif len(assets) == 1:
        listed = ONE_UNNAMED_PLAYER
    else:
        listed = N_UNNAMED_PLAYERS.format(n=len(assets))
    verb = "is" if len(assets) == 1 else "are"
    if side == "give":
        return ASSET_NOT_OWNED.format(assets=listed, verb=verb)
    if counterparty_name:
        return COUNTERPARTY_NOT_OWNED.format(assets=listed, verb=verb, team=counterparty_name)
    return COUNTERPARTY_NOT_OWNED_UNNAMED.format(assets=listed, verb=verb)
