"""AC-9 and P2 page contracts: what a paged deck must preserve.

From models-lead-launch §DEC-2 §3 (AC-9b and AC-9d in #339): page 1 must
equal the first N cards of the full deck in identity and order, and a later
page may never reorder or repeat a card that was already delivered.
Otherwise `card_index` stops being the served order and replay's exposure
model e(k) breaks.

Identity is content, never `trade_id` (a uuid4 minted per build):
`card_identity` hashes the sorted give ids, the sorted receive ids and the
counterparty, with the same formula as `server._deck_trade_hash`, so it
equals the `trade_hash` the impression writer logs for the card.
`_deck_trade_hash` itself lives in backend/server.py and can't be imported
without importing the server, so the formula is restated here;
test_deck_contracts.py pins the two against each other.

How trades-eng calls these from its page-store tests:

    from backend.tests.support.deck_contracts import (
        assert_page_is_top_n, assert_prefix_stable, card_identity)

    # full_deck: the job's complete ranked deck (TradeCards, served card
    # dicts from trade_card_to_dict, or deck_impressions rows by card_index).
    # page_1: what the page store sent first. N: the page size.
    assert_page_is_top_n(page_1, full_deck, N,
                         page_engine_version=..., full_engine_version=...)

    # delivered: the pages already sent, in order. later: the same deck's
    # pages as served afterwards (prefetch, scroll, rebuild), from page 1.
    assert_prefix_stable(delivered=[page_1, page_2], later_deck_pages=later)

Each assertion raises AssertionError with a position-by-position diff.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping


def trade_hash(give: list, receive: list, partner) -> str:
    """server._deck_trade_hash, restated: sha256 of sorted give | sorted
    receive | partner, truncated to 16 hex chars."""
    return hashlib.sha256(
        f"{','.join(sorted(give))}|{','.join(sorted(receive))}|{partner or ''}"
        .encode()).hexdigest()[:16]


def _asset_ids(assets) -> list:
    # Served card dicts carry player dicts ({"id": ...}); TradeCards carry ids.
    return [a["id"] if isinstance(a, Mapping) else a for a in assets]


def card_identity(card) -> str:
    """Content identity of a card: a TradeCard (or any object with
    give_player_ids / receive_player_ids / target_user_id), a served card
    dict (`give` / `receive` lists of player dicts), or a deck_impressions
    row, which only has its logged `trade_hash` (the same value)."""
    if isinstance(card, Mapping):
        give = card.get("give_player_ids")
        recv = card.get("receive_player_ids")
        if give is None and "give" in card:
            give, recv = _asset_ids(card["give"]), _asset_ids(card.get("receive") or [])
        if give is None:
            if card.get("trade_hash"):
                return card["trade_hash"]
            raise ValueError(f"card has no assets and no trade_hash: {sorted(card)}")
        return trade_hash(give, recv or [], card.get("target_user_id"))
    return trade_hash(list(card.give_player_ids), list(card.receive_player_ids),
                      getattr(card, "target_user_id", None))


def _diff(label: str, expected: list[str], got: list[str]) -> str:
    lines = [f"{label}: expected {len(expected)} cards, got {len(got)}"]
    for i in range(max(len(expected), len(got))):
        e = expected[i] if i < len(expected) else "-"
        g = got[i] if i < len(got) else "-"
        lines.append(f"  [{i}] expected {e}  got {g}{'' if e == g else '   <-- differs'}")
    missing = [x for x in expected if x not in got]
    extra = [x for x in got if x not in expected]
    if missing:
        lines.append(f"  expected but absent: {missing}")
    if extra:
        lines.append(f"  present but not expected: {extra}")
    return "\n".join(lines)


def assert_page_is_top_n(page_cards, full_deck_cards, n: int,
                         page_engine_version, full_engine_version) -> None:
    """AC-9: page 1 equals the full deck's top N, with the same identities,
    in the same order, from the same engine version. A full deck shorter
    than N means the page must be the whole deck."""
    assert page_engine_version == full_engine_version, (
        f"engine version mismatch: page built by {page_engine_version!r}, "
        f"full deck by {full_engine_version!r}")
    expected = [card_identity(c) for c in list(full_deck_cards)[:n]]
    got = [card_identity(c) for c in page_cards]
    assert got == expected, _diff(f"page 1 is not the full deck's top {n}",
                                  expected, got)


def assert_prefix_stable(delivered_pages, later_deck_pages) -> None:
    """P2: the cards already delivered keep their identities and order at
    the head of the later deck, and the later deck's new cards repeat none
    of them. Pages are compared flattened, since card_index is a position
    in the whole deck, not within a page."""
    delivered = [card_identity(c) for page in delivered_pages for c in page]
    later = [card_identity(c) for page in later_deck_pages for c in page]
    head = later[:len(delivered)]
    assert head == delivered, _diff(
        "delivered cards moved or changed in the later deck", delivered, head)
    repeated = sorted(set(later[len(delivered):]) & set(delivered))
    assert not repeated, (
        f"new pages repeat already-delivered cards: {repeated}")
