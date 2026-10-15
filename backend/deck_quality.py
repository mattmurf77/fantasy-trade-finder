"""Quality filters on the live trade deck (operator, 2026-10-14; flag `deck.quality_filters`).

Calibration grades showed today's engine failing in four repeatable ways; each is a rule here:

- breakup:   the viewer gives up their best piece for lesser ones (best piece received worth
             < BREAKUP_MIN_RATIO of the best piece given) -> dropped.
- filler:    a piece too small for the trade (below max(FILLER_FLOOR, FILLER_FRAC x the trade's
             headliner)) -> dropped.
- redundant: either side receives a TE or QB while keeping as many comparable ones (each worth
             >= REDUNDANT_MIN_RATIO of the incoming player) as it starts -> dropped. TE cap =
             dedicated TE slots; QB cap = dedicated QB + SUPER_FLEX slots (each min 1). Sending
             one back frees the slot. Skipped when the lineup is unknown.
- repeat:    within the first REPEAT_WINDOW cards no asset appears in more than REPEAT_CAP
             cards; a card that would break it is deferred to just after the window (not dropped).

Protected cards (likes-you, standing offers, injected/wildcard/retest/published) are never
dropped or moved. An asset with no known market value never triggers a value rule.
Pure: no I/O, no logging, no flag reads. The same thresholds as the value core's rules
(backend/value_core/core.py), applied to the served cards of the incumbent engine.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable, Mapping, Sequence

BREAKUP_MIN_RATIO = 0.70
FILLER_FLOOR = 450.0
FILLER_FRAC = 0.25
REDUNDANT_MIN_RATIO = 0.70
REPEAT_WINDOW = 30
REPEAT_CAP = 3
PROTECTED_ATTRS = ("likes_you", "source_like_impression_id", "standing_offer_reason", "injected",
                   "wildcard", "fatigue_retest", "retest", "owner_published")


def is_protected(card) -> bool:
    return any(getattr(card, a, None) for a in PROTECTED_ATTRS)


def position_caps(lineup_slots: Sequence[str] | None) -> dict[str, int] | None:
    """{"TE": n, "QB": n} from the league's starting slots; None when the lineup is unknown."""
    if not lineup_slots:
        return None
    slots = list(lineup_slots)
    return {"TE": max(1, slots.count("TE")),
            "QB": max(1, slots.count("QB") + slots.count("SUPER_FLEX"))}


def _breakup(give, receive, market) -> bool:
    g = [market(a) for a in give]
    r = [market(a) for a in receive]
    if not g or not r or any(v is None for v in g + r):
        return False
    return max(r) < BREAKUP_MIN_RATIO * max(g)


def _filler(give, receive, market) -> bool:
    values = [market(a) for a in (*give, *receive)]
    known = [v for v in values if v is not None]
    if not known:
        return False
    bar = max(FILLER_FLOOR, FILLER_FRAC * max(known))
    return any(v < bar for v in known)


def _redundant_side(roster, out, into, market, position, caps) -> bool:
    out = set(out)
    for a in into:
        pos = position(a)
        cap = caps.get(pos)
        value = market(a)
        if cap is None or value is None:
            continue
        bar = REDUNDANT_MIN_RATIO * value
        kept = sum(1 for p in roster if p not in out and position(p) == pos
                   and (market(p) or 0.0) >= bar)
        also = sum(1 for b in into if b != a and position(b) == pos and (market(b) or 0.0) >= bar)
        if kept + also >= cap:
            return True
    return False


def filter_deck(cards: Sequence, *, viewer_id: str, market: Callable[[str], float | None],
                position: Callable[[str], str | None], rosters: Mapping[str, Sequence[str]],
                lineup_slots: Sequence[str] | None) -> tuple[list, dict]:
    """(kept cards in served order, counts). Each card needs give_player_ids,
    receive_player_ids and target_user_id (the counterparty); rosters maps team id -> asset ids
    (the viewer's under viewer_id)."""
    caps = position_caps(lineup_slots)
    counts = {"breakup": 0, "filler": 0, "redundant": 0, "deferred": 0}
    kept = []
    for c in cards:
        if is_protected(c):
            kept.append(c)
            continue
        give, receive = list(c.give_player_ids), list(c.receive_player_ids)
        if _breakup(give, receive, market):
            counts["breakup"] += 1
            continue
        if _filler(give, receive, market):
            counts["filler"] += 1
            continue
        if caps is not None and (
                _redundant_side(rosters.get(viewer_id, ()), give, receive, market, position, caps)
                or _redundant_side(rosters.get(str(c.target_user_id), ()), receive, give,
                                   market, position, caps)):
            counts["redundant"] += 1
            continue
        kept.append(c)
    ordered, deferred = _repeat_cap(kept)
    counts["deferred"] = deferred
    return ordered, counts


def _repeat_cap(cards: list) -> tuple[list, int]:
    """No asset in more than REPEAT_CAP of the first REPEAT_WINDOW cards; over-cap cards move to
    just after the window in their original order. Protected cards hold their positions."""
    seen: Counter = Counter()
    head, deferred, tail = [], [], []
    for c in cards:
        if len(head) >= REPEAT_WINDOW:
            tail.append(c)
            continue
        assets = (*c.give_player_ids, *c.receive_player_ids)
        if not is_protected(c) and any(seen[a] >= REPEAT_CAP for a in assets):
            deferred.append(c)
            continue
        seen.update(assets)
        head.append(c)
    return head + deferred + tail, len(deferred)
