"""Rules-first deck construction: the per-card deck rules as one admission predicate.

Fast deck v2 (docs/adr/adr-030-rules-first-deck.md, flag ``deck.rules_first``). The deck's
per-card rules, significance (discovery context) and ``deck_quality``'s breakup, filler and
redundant QB/TE, decide whether an owner-bilateral card may exist BEFORE it is ranked, so the
ranker and the page search only ever see cards that can be shown. The order-dependent stages
(likes-you and revised-offer injection, decline-window suppression, dispositions, the bilateral
presentment, the repeat cap) stay downstream, unchanged.

One definition per rule: the quality rules are ``deck_quality.card_rule``, the function
``deck_quality.filter_deck`` calls; significance is whatever callable the worker passes, and
the worker passes its own downstream gate (``server._evaluate_trade_significance``). The
downstream copies keep running as guards and must remove no generated card. The rules
depend on the request only, never on who liked what: liked trades are an overlay the worker
evaluates after generation (``server._inject_likes_you_cards``).

Pure: no I/O, no logging, no flag reads. Memoised per job by the package's terms (the rules
read only the terms and the request's inputs, so a package's verdict never changes inside one
job). One job thread at a time.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable, Mapping, Sequence

from . import deck_quality

VERSION = "deck-rules-1"


class DeckRules:
    """``reason(target, give, receive)``: the first rule the terms break, or None.

    ``significance(target, give, receive) -> bool`` is the discovery significance gate, or
    None when significance is not enforced; ``quality`` is whether the deck quality filters
    run. The rest are exactly the inputs ``deck_quality.filter_deck`` is given downstream.
    """

    def __init__(self, *, viewer_id: str, market: Callable[[str], float | None],
                 position: Callable[[str], str | None], rosters: Mapping[str, Sequence[str]],
                 lineup_slots: Sequence[str] | None, quality: bool = True,
                 significance: Callable[[str, Sequence[str], Sequence[str]], bool] | None = None):
        self.viewer_id, self.market, self.position = str(viewer_id), market, position
        self.rosters, self.quality, self.significance = rosters, bool(quality), significance
        self.caps = deck_quality.position_caps(lineup_slots)
        self._memo: dict = {}

    @property
    def active(self) -> bool:
        """Whether any rule can reject a card (if not, rules-first changes nothing)."""
        return self.quality or self.significance is not None

    def reason(self, target, give, receive) -> str | None:
        key = str(target), frozenset(give), frozenset(receive)
        if key in self._memo:
            return self._memo[key]
        out = None
        if self.significance is not None and not self.significance(str(target), list(give), list(receive)):
            out = "significance"
        elif self.quality:
            out = deck_quality.card_rule(give, receive, target, viewer_id=self.viewer_id,
                                         market=self.market, position=self.position,
                                         rosters=self.rosters, caps=self.caps)
        self._memo[key] = out
        return out

    def admits(self, target, give, receive) -> bool:
        return self.reason(target, give, receive) is None

    def admits_card(self, card) -> bool:
        """A card's verdict. A protected card (``deck_quality.PROTECTED_ATTRS``) is always
        admitted: downstream it is never dropped, so the gate never drops it either."""
        return deck_quality.is_protected(card) or self.admits(
            card.target_user_id, card.give_player_ids, card.receive_player_ids)

    def rejected(self) -> dict:
        """Distinct packages rejected so far, by rule (aggregate counts only)."""
        return dict(Counter(r for r in self._memo.values() if r is not None))
