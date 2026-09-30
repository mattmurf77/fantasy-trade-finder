"""Deck assembly for the value-core engine (docs/plans/value-core-engine/lld.md section 5.6).

Orders every scored trade by effective priority with repeat penalties, capping how often
one asset may appear in the first TOP_WINDOW cards. Nothing is dropped. Lazy greedy: exact
because effective scores only fall as the `shown` counters grow. No logging, no I/O.
"""
from __future__ import annotations

import heapq
from collections import Counter
from typing import Sequence

from .ranking import card_reasons
from .types import TOP_WINDOW, DeckEntry, LeagueSnapshot, RankConfig, Request, ScoredTrade

PARTNER_PENALTY_FACTOR = 0.5


def assemble_deck(scored: Sequence[ScoredTrade], cfg: RankConfig, *,
                  snapshot: LeagueSnapshot, request: Request) -> list[DeckEntry]:
    """Order ALL scored trades (nothing dropped). Greedy by effective priority:
        effective = priority - cfg.repeat_penalty * max(shown[a] for a in give+receive)
                             - PARTNER_PENALTY_FACTOR * cfg.repeat_penalty * shown_partner[partner]
    Hard cap: while position < TOP_WINDOW, a card containing any asset with
    shown[a] >= cfg.player_cap is ineligible (deferred). Deferred cards re-enter when
    position reaches TOP_WINDOW, or earlier if nothing eligible remains (cap relaxed for
    that position only). DeckEntry.reasons = ranking.card_reasons(...)."""
    shown: Counter[str] = Counter()
    shown_partner: Counter[str] = Counter()
    assets = [s.trade.give + s.trade.receive for s in scored]

    def eff(i: int) -> float:
        s = scored[i]
        return (s.scores.priority
                - cfg.repeat_penalty * max(shown[a] for a in assets[i])
                - PARTNER_PENALTY_FACTOR * cfg.repeat_penalty * shown_partner[s.trade.partner_team_id])

    heap = [(-s.scores.priority, s.trade.key, i) for i, s in enumerate(scored)]
    heapq.heapify(heap)
    deferred: list[int] = []
    relax_once = False
    out: list[DeckEntry] = []
    while heap or deferred:
        if not heap:  # only capped cards left before position TOP_WINDOW
            heap = [(-eff(i), scored[i].trade.key, i) for i in deferred]
            heapq.heapify(heap)
            deferred = []
            relax_once = True
        _, _, i = heapq.heappop(heap)
        pos = len(out)
        if pos < TOP_WINDOW and not relax_once and any(shown[a] >= cfg.player_cap for a in assets[i]):
            deferred.append(i)
            continue
        e = eff(i)
        if heap and e < -heap[0][0] - 1e-12:  # stale bound: re-queue with the fresh value
            heapq.heappush(heap, (-e, scored[i].trade.key, i))
            continue
        out.append(DeckEntry(pos, scored[i], round(e, 6), card_reasons(scored[i], snapshot, request)))
        for a in assets[i]:
            shown[a] += 1
        shown_partner[scored[i].trade.partner_team_id] += 1
        relax_once = False
        if len(out) == TOP_WINDOW and deferred:
            for j in deferred:
                heapq.heappush(heap, (-eff(j), scored[j].trade.key, j))
            deferred = []
    return out
