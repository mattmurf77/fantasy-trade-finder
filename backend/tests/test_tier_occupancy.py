"""Suggested-tier occupancy sanity (FB #60 / #69 — "44 elite QBs").

The default/suggested tiers a user sees are the consensus seed Elos
(data_loader: elo = 1200 + value/10000 * 600, DynastyProcess values)
bucketed through tier_config.json via RankingService.tier_for_elo. These
tests pin, per position AND scoring format, that the resulting occupancy
is dynasty-sane: Elite is a small handful, Starter/Solid are populated,
and zero-value players never rise above Bench.

They run against a checked-in snapshot of the DynastyProcess pool
(fixtures/dp_values_snapshot_2026-07-10.json) so they are deterministic
and network-free. If tier_config.json bands or the seed formula change,
these bounds are the guardrail. To refresh the snapshot after a large
consensus shift, re-dump the sorted per-position value lists from
files/values-players.csv in github.com/dynastyprocess/data (columns
value_1qb / value_2qb) into the same JSON shape and update the filename
date.

Also pins that a manual full-board reorder (apply_reorder) is a pure
permutation of existing Elos — the pre-fix linear max→min spread
flattened the convex value curve and pushed dozens of players above the
Elite floor after any Manual Ranks session.
"""
import json
from pathlib import Path

import pytest

from backend.data_loader import ELO_MIN, ELO_RANGE, VALUE_MAX
from backend.ranking_service import Player, RankingService

_FIXTURE = (
    Path(__file__).parent / "fixtures" / "dp_values_snapshot_2026-07-10.json"
)
_POOL = json.loads(_FIXTURE.read_text())["values"]

FORMATS = ("1qb_ppr", "sf_tep")
POSITIONS = ("QB", "RB", "WR", "TE")


def _seed_elo(value: float) -> float:
    """Mirror of data_loader's seed formula."""
    return ELO_MIN + (min(value, VALUE_MAX) / VALUE_MAX) * ELO_RANGE


def _occupancy(fmt: str, pos: str) -> dict[str, int]:
    counts = {"elite": 0, "starter": 0, "solid": 0, "depth": 0,
              "bench": 0, None: 0}
    for value in _POOL[fmt][pos]:
        tier = RankingService.tier_for_elo(_seed_elo(value), pos, fmt)
        counts[tier] += 1
    return counts


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_elite_is_a_small_handful(fmt, pos):
    occ = _occupancy(fmt, pos)
    assert 2 <= occ["elite"] <= 10, (
        f"{fmt}/{pos}: {occ['elite']} elite players from the consensus pool "
        f"— Elite must stay a handful (the FB-69 state was 44)")


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_starter_and_solid_are_populated(fmt, pos):
    # The pre-recalibration failure mode on the other end: bands so high
    # that everyone below ~rank 6 fell straight to depth/bench (SF TE had
    # ZERO elite/starter/solid — Brock Bowers defaulted to "Depth").
    occ = _occupancy(fmt, pos)
    assert 3 <= occ["starter"] <= 15, f"{fmt}/{pos}: starter occ {occ['starter']}"
    assert 3 <= occ["solid"] <= 20, f"{fmt}/{pos}: solid occ {occ['solid']}"
    assert occ["elite"] + occ["starter"] <= 20, (
        f"{fmt}/{pos}: elite+starter = {occ['elite'] + occ['starter']}")


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_zero_value_players_never_rise_above_bench(fmt, pos):
    tier = RankingService.tier_for_elo(_seed_elo(0.0), pos, fmt)
    assert tier == "bench"


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_top_consensus_player_is_elite(fmt, pos):
    top = max(_POOL[fmt][pos])
    assert RankingService.tier_for_elo(_seed_elo(top), pos, fmt) == "elite", (
        f"{fmt}/{pos}: the consensus #1 (value {top}) must default to Elite")


# ---------------------------------------------------------------------------
# Manual reorder must not inflate tier occupancy
# ---------------------------------------------------------------------------

def _service_from_snapshot(fmt: str, pos: str):
    values = _POOL[fmt][pos]
    players = [Player(id=f"p{i}", name=f"P{i}", position=pos, team="AAA", age=25)
               for i in range(len(values))]
    seeds = {f"p{i}": _seed_elo(v) for i, v in enumerate(values)}
    svc = RankingService(players=players, seed_ratings=seeds)
    svc._scoring_format = fmt
    return svc, players


@pytest.mark.parametrize("fmt", ("sf_tep",))
def test_full_board_reorder_does_not_inflate_elite(fmt):
    """The '44 elite QBs' mechanism: a full Manual Ranks reorder used to
    respread every QB linearly from pool max to pool min, pushing the top
    third of the board above the Elite floor. Reorder must keep the tier
    histogram identical (it only permutes Elo values)."""
    pos = "QB"
    svc, players = _service_from_snapshot(fmt, pos)
    pool = svc._pool(pos)

    def histogram():
        elo = svc._compute_elo(pool)
        counts: dict = {}
        for p in pool:
            t = RankingService.tier_for_elo(elo[p.id], pos, fmt)
            counts[t] = counts.get(t, 0) + 1
        return counts

    before = histogram()
    # Full-board reorder: reverse the entire position (worst → best).
    svc.apply_reorder(pos, [p.id for p in reversed(pool)])
    after = histogram()

    assert after == before, (
        f"reorder changed tier occupancy: {before} -> {after}")
    assert after.get("elite", 0) <= 10


def test_reorder_respects_requested_order():
    svc, players = _service_from_snapshot("1qb_ppr", "RB")
    pool = svc._pool("RB")
    ordered = [p.id for p in reversed(pool)]
    svc.apply_reorder("RB", ordered)
    elo = svc._compute_elo(pool)
    ranked = sorted(ordered, key=lambda pid: -elo[pid])
    assert ranked == ordered, "reorder must produce strictly the requested order"
