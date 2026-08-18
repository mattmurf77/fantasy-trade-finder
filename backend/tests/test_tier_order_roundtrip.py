"""B2 (2026-08-18 bug sweep) — within-tier ARRAY ORDER round-trips.

The B2 investigation blamed the client and cleared the server, but the
server half of that verdict was never pinned by a test. It is load-bearing:
the whole fix is "insert the mover at index 0 instead of appending", which
is only a fix if the submitted index survives the save/read cycle. If
`apply_tiers` ever stopped honouring array position — spread the band in
seed order, sort the list, dedupe unstably — the client would look broken
again and the search would restart in the wrong file.

The mechanism (`ranking_service.apply_tiers`): a tier's submitted list is
spread linearly across that tier's Elo band, `hi - (hi - lo) * i / (n - 1)`,
so index 0 lands on the band ceiling and index n-1 on its floor. Reads sort
by Elo descending, so submitted order comes back verbatim.
"""

import pytest

from backend.ranking_service import RankingService, Player

FMT = "1qb_ppr"
POS = "WR"
TIER = "second"


def _svc():
    # Seeds are deliberately in the OPPOSITE order to the submissions below,
    # so a passing round-trip cannot be explained by seed Elo leaking through.
    players = [
        Player(id="a", name="Alpha",   position=POS, team="AAA", age=24),
        Player(id="b", name="Bravo",   position=POS, team="BBB", age=25),
        Player(id="c", name="Charlie", position=POS, team="CCC", age=26),
        Player(id="z", name="Zulu",    position=POS, team="ZZZ", age=27),
    ]
    seeds = {"a": 1300.0, "b": 1500.0, "c": 1700.0, "z": 1400.0}
    svc = RankingService(players=players, seed_ratings=seeds)
    svc._scoring_format = FMT
    return svc


def _band():
    return RankingService.tier_bands_for(POS, FMT)[TIER]


def _read_order(svc, ids):
    """Submitted-tier members, in the order a client reads them back."""
    wanted = set(ids)
    return [
        r.player.id for r in svc.get_rankings(POS).rankings if r.player.id in wanted
    ]


def test_submitted_order_becomes_strictly_descending_elo():
    svc = _svc()
    svc.apply_tiers(POS, {TIER: ["a", "b", "c"]}, FMT)
    elos = [svc._elo_overrides[pid] for pid in ("a", "b", "c")]
    assert elos[0] > elos[1] > elos[2], elos


def test_every_override_lands_inside_the_tier_band():
    svc = _svc()
    svc.apply_tiers(POS, {TIER: ["a", "b", "c"]}, FMT)
    lo, hi = _band()
    for pid in ("a", "b", "c"):
        elo = svc._elo_overrides[pid]
        assert lo <= elo <= hi, f"{pid}={elo} outside band {(lo, hi)}"
        # …and the inverse lookup agrees, so the player reads as this tier.
        assert RankingService.tier_for_elo(elo, POS, FMT) == TIER


def test_endpoints_pin_to_the_band_ceiling_and_floor():
    svc = _svc()
    svc.apply_tiers(POS, {TIER: ["a", "b", "c"]}, FMT)
    lo, hi = _band()
    assert svc._elo_overrides["a"] == pytest.approx(hi)
    assert svc._elo_overrides["c"] == pytest.approx(lo)


def test_rankings_read_back_in_submitted_order():
    svc = _svc()
    svc.apply_tiers(POS, {TIER: ["a", "b", "c"]}, FMT)
    assert _read_order(svc, ["a", "b", "c"]) == ["a", "b", "c"]


def test_reordering_the_submission_reorders_the_read_back():
    """The B2-relevant claim: WHERE the client puts a player in the array is
    what decides where they land. Index 0 is the top of the tier."""
    svc = _svc()
    svc.apply_tiers(POS, {TIER: ["a", "b", "c"]}, FMT)
    assert _read_order(svc, ["a", "b", "c"]) == ["a", "b", "c"]
    # Same members, "c" promoted to the head of the tier (the fix's insert).
    svc.apply_tiers(POS, {TIER: ["c", "a", "b"]}, FMT)
    assert _read_order(svc, ["a", "b", "c"]) == ["c", "a", "b"]


def test_single_member_pins_to_the_band_ceiling():
    # n == 1 has its own branch (the linear spread divides by n-1).
    svc = _svc()
    svc.apply_tiers(POS, {TIER: ["b"]}, FMT)
    _lo, hi = _band()
    assert svc._elo_overrides["b"] == pytest.approx(hi)
    assert RankingService.tier_for_elo(svc._elo_overrides["b"], POS, FMT) == TIER


def test_unknown_pids_do_not_consume_a_slot():
    """Off-pool ids are dropped BEFORE the spread, so the survivors still
    take the full band — an off-by-one here would silently compress a tier."""
    svc = _svc()
    svc.apply_tiers(POS, {TIER: ["a", "ghost", "b", "c"]}, FMT)
    lo, hi = _band()
    assert "ghost" not in svc._elo_overrides
    assert svc._elo_overrides["a"] == pytest.approx(hi)
    assert svc._elo_overrides["c"] == pytest.approx(lo)
    assert _read_order(svc, ["a", "b", "c"]) == ["a", "b", "c"]
