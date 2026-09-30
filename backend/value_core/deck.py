"""Deck assembly for the value-core engine (docs/plans/value-core-engine/lld.md section 5.6).

Three variety rules, then a greedy order by effective priority:

1. One card per trade idea. Trades with the same partner and the same headliner on each
   side are one idea (only the minor pieces differ); a pick headliner counts as "a pick",
   whatever its year or round. Only the highest-priority version is kept; the rest are
   dropped.
2. Acquisitions in rounds. Every (partner, acquired headliner) pair is shown once before
   any is shown twice. Picks again count as one acquisition per partner.
3. Partner and asset caps in the first TOP_WINDOW cards: no partner past partner_cap(n),
   no asset past cfg.player_cap. A card that breaks a cap is deferred; the caps relax for
   one position only when nothing eligible is left.

Lazy greedy: exact because a card's (round, -effective) key only grows as cards are shown.
No logging, no I/O.
"""
from __future__ import annotations

import heapq
import math
from collections import Counter
from typing import Sequence

from .ranking import card_reasons
from .types import TOP_WINDOW, DeckEntry, FairTrade, LeagueSnapshot, RankConfig, Request, ScoredTrade

PARTNER_PENALTY_FACTOR = 0.5
PICK_IDEA = "PICK"


def _idea_asset(asset_id: str, snapshot: LeagueSnapshot) -> str:
    asset = snapshot.assets.get(asset_id)
    return PICK_IDEA if asset is not None and asset.kind == "pick" else asset_id


def idea_key(trade: FairTrade, snapshot: LeagueSnapshot) -> tuple[str, str, str]:
    """(partner, give headliner, receive headliner), picks collapsed to "PICK". Trades that
    share it differ only in minor pieces or pick years: the same trade idea."""
    return (trade.partner_team_id, _idea_asset(trade.give[0], snapshot),
            _idea_asset(trade.receive[0], snapshot))


def acquisition_key(trade: FairTrade, snapshot: LeagueSnapshot) -> tuple[str, str]:
    """(partner, acquired headliner), picks collapsed to "PICK"."""
    return (trade.partner_team_id, _idea_asset(trade.receive[0], snapshot))


def partner_cap(n_partners: int) -> int:
    """Most cards one partner may take in the first TOP_WINDOW: a fair share plus one,
    never below 2. 11 partners -> 4; 5 -> 7; 1 -> 31 (no effect)."""
    return max(2, math.ceil(TOP_WINDOW / max(1, n_partners)) + 1)


def assemble_deck(scored: Sequence[ScoredTrade], cfg: RankConfig, *,
                  snapshot: LeagueSnapshot, request: Request) -> list[DeckEntry]:
    """Order the scored trades, one card per trade idea (lower-priority versions of an idea
    are dropped). Greedy by (acquisition round, effective priority):
        effective = priority - cfg.repeat_penalty * max(shown[a] for a in give+receive)
                             - PARTNER_PENALTY_FACTOR * cfg.repeat_penalty * shown_partner[partner]
    While position < TOP_WINDOW a card is deferred if any of its assets has
    shown[a] >= cfg.player_cap or its partner has partner_cap(n) cards. Deferred cards
    re-enter at position TOP_WINDOW, or earlier if nothing eligible remains (caps relaxed for
    that position only). DeckEntry.reasons = ranking.card_reasons(...)."""
    best: dict[tuple, ScoredTrade] = {}
    for s in scored:
        k = idea_key(s.trade, snapshot)
        kept = best.get(k)
        if kept is None or (-s.scores.priority, s.trade.key) < (-kept.scores.priority, kept.trade.key):
            best[k] = s
    ideas = list(best.values())

    shown: Counter[str] = Counter()
    shown_partner: Counter[str] = Counter()
    shown_acq: Counter[tuple] = Counter()
    assets = [s.trade.give + s.trade.receive for s in ideas]
    acq = [acquisition_key(s.trade, snapshot) for s in ideas]
    p_cap = partner_cap(len({s.trade.partner_team_id for s in ideas}))

    def eff(i: int) -> float:
        s = ideas[i]
        return (s.scores.priority
                - cfg.repeat_penalty * max(shown[a] for a in assets[i])
                - PARTNER_PENALTY_FACTOR * cfg.repeat_penalty * shown_partner[s.trade.partner_team_id])

    def entry(i: int) -> tuple:
        return (shown_acq[acq[i]], -eff(i), ideas[i].trade.key, i)

    def capped(i: int) -> bool:
        return (shown_partner[ideas[i].trade.partner_team_id] >= p_cap
                or any(shown[a] >= cfg.player_cap for a in assets[i]))

    heap = [(0, -s.scores.priority, s.trade.key, i) for i, s in enumerate(ideas)]
    heapq.heapify(heap)
    deferred: list[int] = []
    relax_once = False
    out: list[DeckEntry] = []
    while heap or deferred:
        if not heap:  # only capped cards left before position TOP_WINDOW
            heap = [entry(i) for i in deferred]
            heapq.heapify(heap)
            deferred = []
            relax_once = True
        i = heapq.heappop(heap)[3]
        pos = len(out)
        if pos < TOP_WINDOW and not relax_once and capped(i):
            deferred.append(i)
            continue
        fresh = entry(i)
        if heap and fresh[:3] > heap[0][:3]:  # stale bound: re-queue with the fresh key
            heapq.heappush(heap, fresh)
            continue
        out.append(DeckEntry(pos, ideas[i], round(-fresh[1], 6),
                             card_reasons(ideas[i], snapshot, request)))
        for a in assets[i]:
            shown[a] += 1
        shown_partner[ideas[i].trade.partner_team_id] += 1
        shown_acq[acq[i]] += 1
        relax_once = False
        if len(out) == TOP_WINDOW and deferred:
            for j in deferred:
                heapq.heappush(heap, entry(j))
            deferred = []
    return out
