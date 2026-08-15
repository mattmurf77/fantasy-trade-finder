"""P0-5 near-duplicate deck dedup — the metric and the greedy pass (LLD §4.6).

The problem: the generator happily emits five cards that are the same trade
wearing different sweeteners. They burn five deck slots, five impressions and
five swipes to learn one thing.

**The metric (LLD §4.6, DECIDED — do not re-litigate here).** Two cards A and B
are near-duplicates iff ALL THREE hold:

1. same ``partner_user_id``,
2. same centerpiece (the package's highest-consensus asset — server.py's
   ``_fatigue_centerpiece``, computed by the caller and handed in so there is
   exactly ONE definition of "centerpiece" in the codebase), and
3. ``jaccard(assets_A, assets_B) >= tau`` where ``assets = set(give) | set(receive)``
   and ``tau = dedup_overlap_tau`` (0.75).

**Where it runs (the part that matters for correctness).** The caller applies
this in ``_order_deck`` on the BASE-KEYED list, before the Thompson draw and
before the ``capture`` out-param is populated. That placement is what keeps the
HLD §2.3 serving contract intact: dedup is deterministic given the candidate
set, it contributes nothing to the logged propensity, and a dropped card is
never logged as an impression — so offline replay, which only ever reorders
logged cards, cannot see the drops at all. Not "we checked replay still works":
replay is correct *by construction*.

**Always measure, conditionally drop (PRD M4).** ``dedup_cards`` always returns
the pair/participant counts, even with ``apply_drops=False``. Drops are
pre-capture, so a counter is the ONLY thing that can ever see them — the
pre-ship baseline has to accumulate while the flag is still off.

Purity: no Flask, no DB, no config reads, no clock, no RNG (D12). Everything
the metric needs arrives as a ``DedupCard``. O(n²) over a deck of ≤40 cards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

__all__ = [
    "DEFAULT_TAU",
    "DedupCard",
    "jaccard",
    "is_near_dup",
    "near_dup_pairs",
    "dedup_cards",
]

# Mirrors the DB-seeded `dedup_overlap_tau` default (database.py). The live
# value reaches this module as the `tau` argument, resolved by the caller via
# `relevance.config.resolve` — this constant is only the last-resort fallback.
# This module deliberately reads no config of its own (T-28: one read path).
DEFAULT_TAU = 0.75


@dataclass(frozen=True)
class DedupCard:
    """A candidate card reduced to exactly what the §4.6 metric reads.

    The caller builds these; this module never touches a live trade card. That
    is the whole point of the shape — the metric stays unit-testable with six
    literals and no Flask app.

    ident
        Stable card identity (server.py's ``_deck_trade_hash``). Used ONLY as
        the deterministic tie-break when two cards carry the same base key,
        and for reporting which cards were dropped. Never ``id(card)``: that
        is a memory address and would make the pass non-reproducible across
        processes.
    partner_user_id / centerpiece
        The two exact-match keys. ``None`` on either side means "we could not
        key this card", and an unkeyable card is never collapsed with anything
        (fail-closed: a malformed card loses a deck slot only if we are sure).
    assets
        ``set(give_player_ids) | set(receive_player_ids)``. Direction-blind by
        design — the same three players shuffled across the two sides is the
        same trade idea to a user staring at a deck.
    protected
        ``likes_you`` cards. Never dropped, but they DO suppress their own
        duplicates (a protected card still occupies the cluster's kept slot).
    ref
        Opaque caller handle (the real card object). Untouched here.
    """

    ident: str
    partner_user_id: str | None
    centerpiece: str | None
    assets: frozenset[str] = field(default_factory=frozenset)
    protected: bool = False
    ref: Any = None


def jaccard(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    """|A ∩ B| / |A ∪ B|, with the empty union defined as 0.0.

    Empty-union ⇒ 0.0 (not 1.0) is deliberate: two cards with no assets at all
    are degenerate, and defining them as identical would collapse every one of
    them into a single deck slot on the strength of a data bug.
    """
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def is_near_dup(a: DedupCard, b: DedupCard, tau: float) -> bool:
    """The §4.6 metric, whole. Symmetric in a/b."""
    if a.partner_user_id is None or a.centerpiece is None:
        return False
    if a.partner_user_id != b.partner_user_id:
        return False
    if a.centerpiece != b.centerpiece:
        return False
    return jaccard(a.assets, b.assets) >= tau


def near_dup_pairs(
    cards: Sequence[DedupCard], *, tau: float = DEFAULT_TAU
) -> list[tuple[int, int]]:
    """Every near-duplicate pair as ``(i, j)`` index tuples, ``i < j``, in the
    incoming order.

    This is the M4 numerator ("served pairs meeting the §4.6 metric"): it is
    measured on the candidate set regardless of whether anything is dropped.
    """
    out: list[tuple[int, int]] = []
    n = len(cards)
    for i in range(n):
        for j in range(i + 1, n):
            if is_near_dup(cards[i], cards[j], tau):
                out.append((i, j))
    return out


def dedup_cards(
    cards: Sequence[DedupCard],
    *,
    tau: float = DEFAULT_TAU,
    min_cards: int = 0,
    apply_drops: bool = True,
) -> tuple[list[DedupCard], dict]:
    """Greedy near-dup collapse. Returns ``(kept, stats)``.

    ``cards`` MUST already be in base-key-descending order with a deterministic
    tie-break (the caller sorts on ``(-base_key, ident)``); the pass keeps the
    FIRST card of each cluster, which is therefore the highest-keyed one. A
    single forward pass, no randomness, no dict-iteration order dependence —
    the same candidate set produces the same drops forever (T-5).

    ``min_cards`` is the deck floor (``_DECK_MIN_CARDS``). If dedup would thin
    the survivors below it, the best dropped cards are restored in key order,
    mirroring ``_cap_per_target``'s restore. Decks already at or below the
    floor are measured but never thinned.

    ``apply_drops=False`` is the PRD M4 baseline mode: measure everything, drop
    nothing. ``stats`` is identical in shape either way, so the counter series
    is continuous across the flag flip.

    stats keys:
        cards           input card count
        pairs           near-dup pairs found (M4 numerator)
        cards_in_pairs  distinct cards participating in ≥1 pair
        dropped         cards actually removed (0 when apply_drops is False)
        restored        cards put back by the min-cards floor
        tau             the threshold actually used
        applied         whether dropping was enabled
        dropped_idents  idents of the removed cards (ordering-independent audit)
    """
    cards = list(cards)
    tau = float(tau)
    pairs = near_dup_pairs(cards, tau=tau)
    participants = {i for pair in pairs for i in pair}

    stats: dict = {
        "cards": len(cards),
        "pairs": len(pairs),
        "cards_in_pairs": len(participants),
        "dropped": 0,
        "restored": 0,
        "tau": tau,
        "applied": bool(apply_drops),
        "dropped_idents": [],
    }

    if not apply_drops or not pairs or len(cards) <= min_cards:
        return cards, stats

    kept_idx: list[int] = []
    dropped_idx: list[int] = []
    for i, card in enumerate(cards):
        if not card.protected and any(
            is_near_dup(cards[k], card, tau) for k in kept_idx
        ):
            dropped_idx.append(i)
            continue
        kept_idx.append(i)

    # Never serve a deck thinner than the floor because of dedup. dropped_idx
    # is still in base-key order, so pop(0) restores the best-dropped first.
    restored = 0
    while len(kept_idx) < min_cards and dropped_idx:
        kept_idx.append(dropped_idx.pop(0))
        restored += 1

    kept_idx.sort()
    stats["dropped"] = len(dropped_idx)
    stats["restored"] = restored
    stats["dropped_idents"] = sorted(cards[i].ident for i in dropped_idx)
    return [cards[i] for i in kept_idx], stats
