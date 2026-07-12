"""Suggested-tier occupancy sanity for the 8-tier pick-value ladder (#117).

The default/suggested tiers a user sees are the consensus seed Elos
(data_loader.seed_elo_for_value — DynastyProcess values mapped affinely
onto the trade-value scale, then through the inverse of the exponential
Elo↔value curve) bucketed through tier_config.json via
RankingService.tier_for_elo.

Tiers read directly in draft-pick terms (2026-07-12 8-tier ladder): each
floor is a rung of the anchor/pick Elo ladder — firsts_4plus >= 1927
(just under the 4-mid-1sts Elo 1927.3), firsts_3 >= 1869 (3 firsts =
1869.7), firsts_2 >= 1788 (2 firsts = 1788.6), first_1 >= 1580 (Late
1st), second >= 1400 (Late 2nd), third >= 1280 (Late 3rd), fourth >=
1220 (Late 4th), waivers = the sub-4th tail down to 1150 (below =
unranked). Bands are position- and format-uniform in Elo space because
pick value is position-uniform by design; occupancy differs per
position/format because the seed Elos do.

The #117 recalibration (seed_elo_for_value) fixed the pre-2026-07-12
calibration artifact where the linear seed map capped at Elo 1800 ≈ 2.1
firsts, so no consensus asset could ever reach a 3-firsts rung. Under
the recalibrated map the top consensus asset per format lands at the
4-firsts rung (DP 10000 → Elo ≈ 1927.3) and the elite shelf reads
≈ 3–4 firsts, matching dynasty-market pricing (a mid 1st ≈ 25–30% of a
top asset).

These tests pin, per scoring format, that the resulting occupancy is
dynasty-sane: "worth a 1st or more" is a real cohort but bounded, the
top two tiers are reachable by consensus (not anchor-only), the middle
rounds are populated, zero-value players never rise above Waivers, and
every anchor-wizard rung lands in the tier that carries its name.

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

from backend.data_loader import (
    SEED_VALUE_CEIL,
    SEED_VALUE_FLOOR,
    VALUE_MAX,
    seed_elo_for_value,
)
from backend.ranking_service import ORDERED_TIERS, Player, RankingService

_FIXTURE = (
    Path(__file__).parent / "fixtures" / "dp_values_snapshot_2026-07-10.json"
)
_POOL = json.loads(_FIXTURE.read_text())["values"]

FORMATS = ("1qb_ppr", "sf_tep")
POSITIONS = ("QB", "RB", "WR", "TE")

# "Worth a 1st or more" = the four firsts-denominated tiers.
_FIRST_OR_BETTER = ("firsts_4plus", "firsts_3", "firsts_2", "first_1")

# Value of one generic Mid 1st on the seed scale (the ceiling anchor is
# 4 × Mid 1st by construction).
_MID_FIRST_VALUE = SEED_VALUE_CEIL / 4.0


def _seed_value(dp: float) -> float:
    """DP value → trade-value scale (the affine leg of the seed map)."""
    return SEED_VALUE_FLOOR + (
        min(dp, VALUE_MAX) / VALUE_MAX
    ) * (SEED_VALUE_CEIL - SEED_VALUE_FLOOR)


def _firsts(dp: float) -> float:
    """DP value → 'how many Mid 1sts is this worth' on the seed scale."""
    return _seed_value(dp) / _MID_FIRST_VALUE


def _occupancy(fmt: str, pos: str) -> dict:
    counts = {t: 0 for t in ORDERED_TIERS}
    counts[None] = 0
    for value in _POOL[fmt][pos]:
        tier = RankingService.tier_for_elo(seed_elo_for_value(value), pos, fmt)
        counts[tier] += 1
    return counts


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_first_round_value_is_a_real_but_bounded_cohort(fmt, pos):
    """'Worth a 1st or more' per position: a real cohort (the recalibrated
    scale prices a mid 1st ≈ 25% of a top asset, so dozens of players
    legitimately clear it — KTC-style) but bounded (the FB-69 failure mode
    was tier inflation; snapshot max is 36, WR 1qb)."""
    occ = _occupancy(fmt, pos)
    n = sum(occ[t] for t in _FIRST_OR_BETTER)
    assert 2 <= n <= 40, (
        f"{fmt}/{pos}: {n} players at first-round value or above — "
        f"outside the dynasty-sane band")


@pytest.mark.parametrize("fmt", FORMATS)
def test_top_two_tiers_are_reachable_per_format(fmt):
    """#117's core fix: the OVERALL top consensus assets must reach the top
    two tiers (pre-recalibration the seed ceiling sat below the 3-firsts
    rung, so firsts-tiers above 2 were unreachable). firsts_4plus stays a
    crown reserved for the very top of the market."""
    occ4 = sum(_occupancy(fmt, pos)["firsts_4plus"] for pos in POSITIONS)
    occ3 = sum(_occupancy(fmt, pos)["firsts_3"] for pos in POSITIONS)
    assert 1 <= occ4 <= 3, f"{fmt}: firsts_4plus total {occ4}"
    assert 3 <= occ4 + occ3 <= 25, f"{fmt}: top-two-tier total {occ4 + occ3}"


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_middle_rounds_are_populated(fmt, pos):
    # The failure mode on the other end: bands so high that everyone
    # below the very top falls straight to waivers. Every position must
    # keep real 2nd/3rd/4th-round-value cohorts.
    occ = _occupancy(fmt, pos)
    assert 3 <= occ["second"] <= 35, f"{fmt}/{pos}: second occ {occ['second']}"
    assert 3 <= occ["third"] <= 30, f"{fmt}/{pos}: third occ {occ['third']}"
    assert 5 <= occ["fourth"] <= 40, f"{fmt}/{pos}: fourth occ {occ['fourth']}"


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_zero_value_players_never_rise_above_waivers(fmt, pos):
    tier = RankingService.tier_for_elo(seed_elo_for_value(0.0), pos, fmt)
    assert tier == "waivers"


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_top_consensus_player_is_worth_a_first_or_better(fmt, pos):
    """The consensus #1 at every position clears first-round value on the
    recalibrated scale (even TEs: sf TE1 lands first_1, 1qb TE1 firsts_2)."""
    top = max(_POOL[fmt][pos])
    tier = RankingService.tier_for_elo(seed_elo_for_value(top), pos, fmt)
    assert tier in _FIRST_OR_BETTER, (
        f"{fmt}/{pos}: the consensus #1 (value {top}) bucketed as {tier}")


@pytest.mark.parametrize("fmt", FORMATS)
def test_top_assets_read_as_three_to_four_firsts(fmt):
    """The recalibration's sanity anchor: the top-5 overall consensus
    assets read ≈ 3–4 firsts (dynasty-market pricing), and the format's
    #1 sits at the 4-firsts rung (DP clamps at 10000 → Elo ≈ 1927.3)."""
    all_values = sorted(
        (v for pos in POSITIONS for v in _POOL[fmt][pos]), reverse=True)
    top5 = all_values[:5]
    assert 3.8 <= _firsts(top5[0]) <= 4.05, (
        f"{fmt}: #1 asset reads {_firsts(top5[0]):.2f} firsts")
    for v in top5:
        assert _firsts(v) >= 3.0, (
            f"{fmt}: top-5 asset (dp {v}) reads {_firsts(v):.2f} firsts — "
            f"elites must price at 3+ firsts")
    # And they land in the ladder's top two tiers (position-uniform bands,
    # so RB suffices for the walk).
    top_tiers = {
        RankingService.tier_for_elo(seed_elo_for_value(v), "RB", fmt)
        for v in top5
    }
    assert top_tiers <= {"firsts_4plus", "firsts_3"}, (
        f"{fmt}: top-5 tiers {top_tiers}")


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("pos", POSITIONS)
def test_anchor_rungs_land_in_matching_tiers(fmt, pos):
    """The ladder's defining invariant: every Pick Anchor wizard answer
    lands in the tier that carries its name, for every position/format.
    Elo rungs per docs/cross-client-invariants.md → Pick anchor keys."""
    rungs = {
        1927.3: "firsts_4plus",   # 4 firsts (value_to_elo(4 x Mid 1st))
        1869.7: "firsts_3",       # 3 firsts
        1788.6: "firsts_2",       # 2 firsts
        1650.0: "first_1",        # Mid 1st seed
        1460.0: "second",         # Mid 2nd seed
        1320.0: "third",          # Mid 3rd seed
        1240.0: "fourth",         # Mid 4th seed
        1200.0: "waivers",        # DP value 0 (the seed floor)
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
    seeds = {f"p{i}": seed_elo_for_value(v) for i, v in enumerate(values)}
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
    assert sum(after.get(t, 0) for t in _FIRST_OR_BETTER) <= 40


def test_reorder_respects_requested_order():
    svc, players = _service_from_snapshot("1qb_ppr", "RB")
    pool = svc._pool("RB")
    ordered = [p.id for p in reversed(pool)]
    svc.apply_reorder("RB", ordered)
    elo = svc._compute_elo(pool)
    ranked = sorted(ordered, key=lambda pid: -elo[pid])
    assert ranked == ordered, "reorder must produce strictly the requested order"


def test_subset_reorder_within_tier_preserves_tier_membership():
    """#136 Quick Rank's save contract: one tier's players POSTed to
    /api/rankings/reorder as a SUBSET of the position. apply_reorder permutes
    the Elos of exactly the submitted ids (same multiset), so (a) untouched
    players keep their Elo, (b) every reordered player stays in its tier,
    and (c) the requested within-tier order holds after an elo-desc sort."""
    fmt, pos = "1qb_ppr", "RB"
    svc, _players = _service_from_snapshot(fmt, pos)
    pool = svc._pool(pos)
    elo_before = dict(svc._compute_elo(pool))

    tier_ids = [
        p.id for p in pool
        if RankingService.tier_for_elo(elo_before[p.id], pos, fmt) == "second"
    ]
    assert len(tier_ids) >= 3, "snapshot must populate the 2nd tier"

    # Maximal within-tier shuffle: reverse the tier (worst-first).
    requested = list(reversed(tier_ids))
    svc.apply_reorder(pos, requested)
    elo_after = svc._compute_elo(pool)

    # (a) subset-safe: ids not submitted are untouched.
    for p in pool:
        if p.id not in tier_ids:
            assert elo_after[p.id] == elo_before[p.id], (
                f"{p.id}: Elo changed by a reorder that didn't include it")

    # (b) tier membership invariant under a within-tier permutation.
    for pid in tier_ids:
        assert RankingService.tier_for_elo(elo_after[pid], pos, fmt) == "second"

    # (c) the requested order is exactly what an elo-desc sort now yields.
    ranked = sorted(tier_ids, key=lambda pid: -elo_after[pid])
    assert ranked == requested
