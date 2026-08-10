"""Phase 4 — PlayoffFormat (seeding, byes, tiebreak, bracket).

Owns how a set of end-of-regular-season standings becomes a seeded playoff
field and how that field plays out. `StandardFormat` implements the common
fantasy shape: seed by record (win_credit) with points_for as the tiebreak,
top `playoff_slots` make it, top `num_byes` get a first-round bye, single-
elimination.

How the bracket advances between rounds is itself a Sleeper league setting —
`settings.playoff_seed_type` — modeled here as `playoff_seed_type` (BUG-3,
docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md
§7). See `_resolve_seed_type` for the verified value semantics and the
explicit, logged fallback for anything unrecognized.

Swap seam: `PlayoffFormat` Protocol + `PLAYOFF_FORMATS` registry. A league
with divisions-win-priority, two-week championship rounds, consolation
brackets, etc. is a new class + one registry line.
"""

from __future__ import annotations

import logging
from typing import Callable, Protocol, runtime_checkable

log = logging.getLogger(__name__)

# A standings row the format ranks: (roster_id, win_credit, points_for, division)
SeedRow = tuple[int, float, float, "int | None"]

# `playoff_seed_type` modes (see `_resolve_seed_type`).
_SEED_TYPE_RESEED = "reseed"  # highest remaining seed always plays the lowest
_SEED_TYPE_FIXED = "fixed"    # bracket slot is locked at the start; no reseeding


def _resolve_seed_type(playoff_seed_type: "int | None") -> str:
    """Map Sleeper's raw `settings.playoff_seed_type` to a seeding mode.

    Verified against real Sleeper league payloads, not guessed (BUG-3):
      - **0 → "fixed"** (Sleeper's own docs/support: "standard bracket, no
        re-seeding"). Confirmed empirically against
        `backend/tests/fixtures/outlook-calibration/ffv3-2022/2023/2025.json`
        — all `playoff_seed_type: 0` leagues — via 3 independent
        "divergent" instances (a round-1 upset that would have produced a
        DIFFERENT round-2 pairing under reseeding than under a fixed bracket):
        every one of them matched the fixed-bracket prediction exactly, none
        matched reseed. See `_play_fixed_bracket`.
      - **1 → "reseed"** (Sleeper's own support article: "the highest seed
        will always play the lowest [remaining] if that option is turned
        on"; independently corroborated by third-party Sleeper API docs and
        client libraries mapping this field to a reseed boolean). This is
        also what the engine has always modeled — i.e. "today's behavior".
        The two `playoff_seed_type: 1` fixture leagues (lakeview-2024/2025)
        never produced a round with a divergent upset pattern, so this value
        is corroborated by documentation + no contradicting evidence, not by
        a fixture replay proof the way 0 is.
      - **anything else** (missing/`None`, or an integer other than 0/1) →
        explicit, LOGGED fallback to "reseed" — today's shipped behavior —
        rather than guessing at an unverified value's semantics.
    """
    if playoff_seed_type == 0:
        return _SEED_TYPE_FIXED
    if playoff_seed_type == 1:
        return _SEED_TYPE_RESEED
    if playoff_seed_type is not None:
        log.warning(
            "playoff_format: unrecognized settings.playoff_seed_type=%r — "
            "falling back to %r (today's behavior). Only 0 (fixed bracket) "
            "and 1 (reseed) are modeled; see BUG-3 in "
            "docs/feedback/items/169-outlook-league-summary/"
            "calibration-report-2026-08-09.md.",
            playoff_seed_type, _SEED_TYPE_RESEED,
        )
    return _SEED_TYPE_RESEED


@runtime_checkable
class PlayoffFormat(Protocol):
    playoff_slots: int
    num_byes: int

    def seed(self, standings: list[SeedRow]) -> list[int]:
        """Return ALL roster_ids best→worst (seed order). The first
        `playoff_slots` are the playoff field."""
        ...

    def champion(self, seed_order: list[int],
                 sample: Callable[[int], float]) -> int:
        """Play the bracket; return the champion roster_id. `sample(roster_id)`
        draws that team's score for a game (provided by the simulator)."""
        ...


class StandardFormat:
    def __init__(self, playoff_slots: int, num_byes: int, num_divisions: int = 0,
                 playoff_seed_type: "int | None" = None):
        self.playoff_slots = playoff_slots
        self.num_byes = num_byes
        self.num_divisions = num_divisions
        # Raw Sleeper value kept around for diagnostics; `_seed_mode` is the
        # normalized mode `champion()` actually branches on.
        self.playoff_seed_type = playoff_seed_type
        self._seed_mode = _resolve_seed_type(playoff_seed_type)

    def seed(self, standings: list[SeedRow]) -> list[int]:
        # Optional division-winner priority: each division's best team seeds
        # ahead of every wildcard (common in Sleeper leagues with divisions).
        if self.num_divisions and self.num_divisions > 1:
            div_best: dict[int, SeedRow] = {}
            for row in standings:
                div = row[3]
                if div is None:
                    continue
                cur = div_best.get(div)
                if cur is None or (row[1], row[2]) > (cur[1], cur[2]):
                    div_best[div] = row
            winners = set(id(r) for r in div_best.values())
            winner_rows = sorted(div_best.values(),
                                 key=lambda r: (-r[1], -r[2], r[0]))
            rest_rows = sorted(
                (r for r in standings if id(r) not in winners),
                key=lambda r: (-r[1], -r[2], r[0]))
            ordered = winner_rows + rest_rows
        else:
            ordered = sorted(standings, key=lambda r: (-r[1], -r[2], r[0]))
        return [r[0] for r in ordered]

    def champion(self, seed_order: list[int],
                 sample: Callable[[int], float]) -> int:
        field = seed_order[:self.playoff_slots]
        if not field:
            return -1
        if len(field) == 1:
            return field[0]
        if self._seed_mode == _SEED_TYPE_FIXED:
            return _play_fixed_bracket(field, self.num_byes, sample)
        return _play_reseed_bracket(field, self.num_byes, sample)


def _play_round(teams_in_seed_order: list[int],
                sample: Callable[[int], float]) -> list[int]:
    """Highest seed vs lowest seed; higher score advances (tie → higher seed)."""
    winners: list[int] = []
    i, j = 0, len(teams_in_seed_order) - 1
    while i < j:
        a, b = teams_in_seed_order[i], teams_in_seed_order[j]
        winners.append(a if sample(a) >= sample(b) else b)
        i += 1
        j -= 1
    if i == j:  # odd count → top team auto-advances
        winners.append(teams_in_seed_order[i])
    return winners


def _reseed(full_field: list[int], alive: set[int]) -> list[int]:
    """Order the survivors by their original seed."""
    return [rid for rid in full_field if rid in alive]


def _play_reseed_bracket(field: list[int], num_byes: int,
                         sample: Callable[[int], float]) -> int:
    """`playoff_seed_type == 1` (or unrecognized/absent — today's behavior):
    after every round, re-rank the survivors by their ORIGINAL seed and pair
    highest vs lowest again. This is what the engine has always done."""
    byes = field[:num_byes]
    playing = field[num_byes:]
    # Round 1: only non-bye teams play.
    survivors = _play_round(playing, sample)
    # Reseed survivors + byes by original seed for subsequent rounds.
    alive = _reseed(field, set(byes) | set(survivors))
    while len(alive) > 1:
        alive = _reseed(field, set(_play_round(alive, sample)))
    return alive[0]


def _bracket_slot_order(n: int) -> list[int]:
    """Standard single-elimination bracket seed order for `n` a power of two
    (1-indexed seed numbers), e.g. `n=8` → `[1,8,4,5,2,7,3,6]`. Adjacent pairs
    are the round-1 matchups; each later round pairs adjacent WINNER pairs.
    Classic recursive tournament-seeding construction (each half mirrors the
    other: seed `s` is always paired against seed `n + 1 - s`)."""
    if n <= 1:
        return [1]
    half = _bracket_slot_order(n // 2)
    order: list[int] = []
    for s in half:
        order.append(s)
        order.append(n + 1 - s)
    return order


def _next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


def _play_fixed_bracket(field: list[int], num_byes: int,
                        sample: Callable[[int], float]) -> int:
    """`playoff_seed_type == 0` — "standard bracket, no re-seeding". Every
    team's slot in the bracket TREE is fixed once from the original seed
    order; who a bye plays in round 2 depends only on bracket position, never
    on which team actually won round 1. Byes are seeds beyond `playoff_slots`
    in the padded-to-a-power-of-2 bracket (phantom opponents an early seed
    auto-advances past). See `_resolve_seed_type` for the empirical proof this
    reproduces Sleeper's own recorded brackets."""
    n = len(field)
    size = _next_pow2(n)
    slots = _bracket_slot_order(size)
    alive: list["int | None"] = [field[s - 1] if s <= n else None for s in slots]
    while len(alive) > 1:
        nxt: list["int | None"] = []
        for i in range(0, len(alive), 2):
            a, b = alive[i], alive[i + 1]
            if a is None:
                nxt.append(b)
            elif b is None:
                nxt.append(a)
            else:
                nxt.append(a if sample(a) >= sample(b) else b)
        alive = nxt
    champ = alive[0]
    assert champ is not None  # at least one real seed exists (len(field) >= 2)
    return champ


PLAYOFF_FORMATS: dict[str, type] = {
    "standard": StandardFormat,
}


def get_playoff_format(key: str, playoff_slots: int, num_byes: int,
                       num_divisions: int = 0,
                       playoff_seed_type: "int | None" = None) -> PlayoffFormat:
    factory = PLAYOFF_FORMATS.get((key or "standard").lower())
    if factory is None:
        raise KeyError(f"no PlayoffFormat registered for {key!r}")
    return factory(playoff_slots, num_byes, num_divisions, playoff_seed_type)
