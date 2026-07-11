"""Suggested-tier occupancy sanity for the pick-value tier ladder.

The default/suggested tiers a user sees are the consensus seed Elos
(data_loader: elo = 1200 + value/10000 * 600, DynastyProcess values)
bucketed through tier_config.json via RankingService.tier_for_elo.

Tiers read directly in draft-pick terms (2026-07-11 ladder): each floor
is a rung of the anchor/pick Elo ladder — firsts_2plus >= 1788 (just under the 2-mid-1sts Elo 1788.6, so a
'2 firsts' anchor pin lands inside), first_1 >= 1580 (Late 1st), second >= 1400 (Late 2nd), third >=
1280 (Late 3rd), fourth >= 1220 (Late 4th), bench = the sub-4th tail
down to 1150 (below = unranked). Bands are position- and format-uniform
in Elo space because pick value is position-uniform by design; occupancy
differs per position/format because the seed Elos do (e.g. 1QB QBs are
rarely worth a 1st — that asymmetry is the point of the ladder).

These tests pin, per scoring format, that the resulting occupancy is
dynasty-sane: "worth a 1st or more" stays a handful, the middle rounds
are populated, zero-value players never rise above Bench, and every
anchor-wizard rung lands in the tier that carries its name.

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
flattened the convex value curve and pushed dozens of players into the
top bands after any Manual Ranks session.
"""
import json
from pathlib import Path

import pytest

from backend.data_loader import ELO_MIN, ELO_RANGE, VALUE_MAX
from backend.ranking_service import ORDERED_TIERS, Player, RankingService

_FIXTURE = (
    Path(__file__).parent / "fixtures" / "dp_values_snapshot_2026-07-10.json"
)
_POOL = json.loads(_FIXTURE.read_text())["values"]

FORMATS = ("1qb_ppr", "sf_tep")
POSITIONS = ("QB", "RB", "WR", "TE")


def _seed_elo(value: float) -> float:
    """Mirror of data_loader's seed formula."""
    return ELO_MIN + (min(value, VALUE_MAX) / VALUE_MAX) * ELO_RANGE


def _occupancy(fmt: str, pos: str) -> dict:
    counts = {t: 0 for t in ORDERED_TIERS}
    counts[None] = 0
    for value in _POOL[fmt][pos]:
        tier = RankingService.tier_for_elo(_seed_elo(value), pos, fmt)
        counts[tier] += 1
    return counts


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_first_round_value_is_a_small_handful(fmt, pos):
    """'Worth a 1st or more' (firsts_2plus + first_1) must stay a handful
    per position — the ladder's honesty check (the old FB-69 failure mode
    was 44 'elite' QBs)."""
    occ = _occupancy(fmt, pos)
    assert occ["firsts_2plus"] + occ["first_1"] <= 12, (
        f"{fmt}/{pos}: {occ['firsts_2plus'] + occ['first_1']} players at "
        f"first-round value or above — must stay a handful")


@pytest.mark.parametrize("fmt", FORMATS)
def test_top_of_ladder_is_reachable_per_format(fmt):
    """firsts_2plus is a legitimate consensus tier (not anchor-only): at
    least one player per format sits at 2-firsts value, but never more
    than a few (the seed scale caps at Elo 1800 = DP value 10000)."""
    total = sum(_occupancy(fmt, pos)["firsts_2plus"] for pos in POSITIONS)
    assert 1 <= total <= 5, f"{fmt}: firsts_2plus total {total}"


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_middle_rounds_are_populated(fmt, pos):
    # The failure mode on the other end: bands so high that everyone
    # below the very top falls straight to bench. Every position must
    # keep real 2nd/3rd/4th-round-value cohorts.
    occ = _occupancy(fmt, pos)
    assert 3 <= occ["second"] <= 20, f"{fmt}/{pos}: second occ {occ['second']}"
    assert 3 <= occ["third"] <= 20, f"{fmt}/{pos}: third occ {occ['third']}"
    assert 6 <= occ["fourth"] <= 40, f"{fmt}/{pos}: fourth occ {occ['fourth']}"


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_zero_value_players_never_rise_above_bench(fmt, pos):
    tier = RankingService.tier_for_elo(_seed_elo(0.0), pos, fmt)
    assert tier == "bench"


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_top_consensus_player_is_worth_a_second_or_better(fmt, pos):
    """The consensus #1 at every position is worth at least a 2nd. (TEs
    top out at 2nd-round value on the consensus seed scale in both
    formats — an honest pick-value statement, not a bug.)"""
    top = max(_POOL[fmt][pos])
    tier = RankingService.tier_for_elo(_seed_elo(top), pos, fmt)
    assert tier in ("firsts_2plus", "first_1", "second"), (
        f"{fmt}/{pos}: the consensus #1 (value {top}) bucketed as {tier}")


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_anchor_rungs_land_in_matching_tiers(fmt, pos):
    """The ladder's defining invariant: every Pick Anchor wizard answer
    lands in the tier that carries its name, for every position/format.
    Elo rungs per docs/cross-client-invariants.md → Pick anchor keys."""
    rungs = {
        1927.0: "firsts_2plus",   # 4 firsts
        1869.7: "firsts_2plus",   # 3 firsts
        1788.6: "firsts_2plus",   # 2 firsts (value_to_elo(2 x Mid 1st))
        1650.0: "first_1",        # Mid 1st seed
        1460.0: "second",         # Mid 2nd seed
        1320.0: "third",          # Mid 3rd seed
        1240.0: "fourth",         # Mid 4th seed
    }
    for elo, expected in rungs.items():
        assert RankingService.tier_for_elo(elo, pos, fmt) == expected, (
            f"{fmt}/{pos}: Elo {elo} should bucket as {expected}")
    # no_value pins below every band → unranked.
    assert RankingService.tier_for_elo(1100.0, pos, fmt) is None


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
def test_full_board_reorder_does_not_inflate_top_tiers(fmt):
    """The '44 elite QBs' mechanism: a full Manual Ranks reorder used to
    respread every QB linearly from pool max to pool min, pushing the top
    third of the board above the top-band floor. Reorder must keep the tier
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
    assert after.get("firsts_2plus", 0) + after.get("first_1", 0) <= 12


def test_reorder_respects_requested_order():
    svc, players = _service_from_snapshot("1qb_ppr", "RB")
    pool = svc._pool("RB")
    ordered = [p.id for p in reversed(pool)]
    svc.apply_reorder("RB", ordered)
    elo = svc._compute_elo(pool)
    ranked = sorted(ordered, key=lambda pid: -elo[pid])
    assert ranked == ordered, "reorder must produce strictly the requested order"
