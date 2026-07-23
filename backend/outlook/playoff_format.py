"""Phase 4 — PlayoffFormat (seeding, byes, tiebreak, bracket).

Owns how a set of end-of-regular-season standings becomes a seeded playoff
field and how that field plays out. `StandardFormat` implements the common
fantasy shape: seed by record (win_credit) with points_for as the tiebreak,
top `playoff_slots` make it, top `num_byes` get a first-round bye, single-
elimination with reseeding (higher seed always plays the lowest survivor).

Swap seam: `PlayoffFormat` Protocol + `PLAYOFF_FORMATS` registry. A league
with divisions-win-priority, two-week championship rounds, consolation
brackets, etc. is a new class + one registry line.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

# A standings row the format ranks: (roster_id, win_credit, points_for, division)
SeedRow = tuple[int, float, float, "int | None"]


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
    def __init__(self, playoff_slots: int, num_byes: int, num_divisions: int = 0):
        self.playoff_slots = playoff_slots
        self.num_byes = num_byes
        self.num_divisions = num_divisions

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
        byes = field[:self.num_byes]
        playing = field[self.num_byes:]
        # Round 1: only non-bye teams play.
        survivors = _play_round(playing, sample)
        # Reseed survivors + byes by original seed for subsequent rounds.
        alive = _reseed(field, set(byes) | set(survivors))
        while len(alive) > 1:
            alive = _reseed(field, set(_play_round(alive, sample)))
        return alive[0]


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


PLAYOFF_FORMATS: dict[str, type] = {
    "standard": StandardFormat,
}


def get_playoff_format(key: str, playoff_slots: int, num_byes: int,
                       num_divisions: int = 0) -> PlayoffFormat:
    factory = PLAYOFF_FORMATS.get((key or "standard").lower())
    if factory is None:
        raise KeyError(f"no PlayoffFormat registered for {key!r}")
    return factory(playoff_slots, num_byes, num_divisions)
