"""Golden + behavioral tests for INIT-03 ELO/stats memoization.

ELO math is a hard cross-client invariant (docs/cross-client-invariants.md).
The memo on RankingService._compute_elo / _compute_stats must be a PURE
pass-through: for the same ranking state (_version) and the same pool, the
memoized result must be byte-for-byte identical to the un-memoized result.

These tests gate that invariant. They:
  (a) capture a reference ELO/stats output by forcing a full compute,
  (b) assert the memoized 2nd call is byte-for-byte identical (and the same
      object, per AC-1),
  (c) mutate the service (record a swipe, then a tier override / reorder),
      assert _version incremented and the next call recomputes the new values,
  (d) assert (via a spy that counts full-compute executions) that the
      full-compute body runs exactly ONCE per get_rankings / trio request,
      not 3-4x.

The fixture deliberately includes a tier-override scenario so the subtle
override/anchoring path in _compute_elo (ranking_service.py:623-662) is
exercised by the memo equivalence checks.
"""
import copy

import pytest

from backend.ranking_service import RankingService, Player


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_players():
    """A non-trivial RB pool. Enough players to form trios and to place some
    in tiers (overrides) while leaving others to evolve via swipes."""
    return [
        Player(id="r1", name="RB One",   position="RB", team="AAA", age=24),
        Player(id="r2", name="RB Two",   position="RB", team="BBB", age=25),
        Player(id="r3", name="RB Three", position="RB", team="CCC", age=26),
        Player(id="r4", name="RB Four",  position="RB", team="DDD", age=23),
        Player(id="r5", name="RB Five",  position="RB", team="EEE", age=27),
        Player(id="r6", name="RB Six",   position="RB", team="FFF", age=22),
    ]


def _build_service():
    """Build a service and feed it a deterministic, non-trivial swipe history
    plus a tier override, so the resulting ELO is non-uniform AND the
    override/anchoring path is exercised."""
    svc = RankingService(players=_make_players())

    # A deterministic set of 3-player rankings (best -> worst). Each decomposes
    # into 3 pairwise swipes, so this produces a non-trivial, spread-out ELO.
    svc.record_ranking(["r1", "r2", "r3"])
    svc.record_ranking(["r1", "r3", "r4"])
    svc.record_ranking(["r2", "r4", "r5"])
    svc.record_ranking(["r1", "r2", "r5"])
    svc.record_ranking(["r3", "r5", "r6"])

    # A trade signal contributes softer-K swipes through the second loop in
    # _compute_elo (the _trade_swipes branch).
    svc.record_trade_signal(winner_ids=["r4"], loser_ids=["r6"], decision="like")

    # Tier override scenario: pin r1 (top tier) and r6 (waivers) via a tier
    # save. This populates _elo_overrides so the anchoring path (623-662)
    # runs: overridden players keep their pinned ELO while their swipe
    # partners still evolve against the anchor.
    svc.apply_tiers(
        position="RB",
        tiers={"first_1": ["r1"], "waivers": ["r6"]},
        scoring_format="1qb_ppr",
    )
    return svc


# ---------------------------------------------------------------------------
# Spy: count how many times the FULL compute body actually executes.
#
# We wrap the bound method and inspect the cache state at call entry. A full
# compute happens iff the (version, pool) pair is NOT already cached when the
# call is made — i.e. exactly the condition the memo guard checks.
# ---------------------------------------------------------------------------

class _ComputeSpy:
    def __init__(self, svc, attr, cache_attr, version_attr, key_attr):
        self._svc = svc
        self._attr = attr
        self._cache_attr = cache_attr
        self._version_attr = version_attr
        self._key_attr = key_attr
        self._orig = getattr(svc, attr)
        self.calls = 0
        self.full_computes = 0

    def __enter__(self):
        def wrapper(pool, *args, **kwargs):
            self.calls += 1
            cache_key = tuple(p.id for p in pool)
            is_hit = (
                getattr(self._svc, self._cache_attr) is not None
                and getattr(self._svc, self._version_attr) == self._svc._version
                and getattr(self._svc, self._key_attr) == cache_key
            )
            if not is_hit:
                self.full_computes += 1
            return self._orig(pool, *args, **kwargs)

        setattr(self._svc, self._attr, wrapper)
        return self

    def __exit__(self, *exc):
        setattr(self._svc, self._attr, self._orig)
        return False


def _elo_spy(svc):
    return _ComputeSpy(
        svc, "_compute_elo",
        "_elo_cache", "_elo_cache_version", "_elo_cache_key",
    )


def _stats_spy(svc):
    return _ComputeSpy(
        svc, "_compute_stats",
        "_stats_cache", "_stats_cache_version", "_stats_cache_key",
    )


# ---------------------------------------------------------------------------
# (a) + (b) Golden equivalence: memoized output == reference output
# ---------------------------------------------------------------------------

def test_elo_memo_identical_to_reference():
    svc = _build_service()
    pool = svc._pool("RB")

    # (a) Force a full compute by clearing the cache, capture a deep reference.
    svc._elo_cache = None
    reference = copy.deepcopy(svc._compute_elo(pool))
    assert reference, "fixture must produce a non-empty ELO map"

    # (b) Second call is a cache hit: byte-for-byte identical AND same object.
    second = svc._compute_elo(pool)
    assert second == reference            # byte-for-byte equal values
    assert second is svc._elo_cache       # AC-1: returns the cached object


def test_elo_override_anchoring_preserved_through_memo():
    """The override/anchoring path (623-662) must survive memoization: pinned
    players keep their exact override ELO on both the cold and warm call."""
    svc = _build_service()
    pool = svc._pool("RB")

    overrides = dict(svc._elo_overrides)
    assert overrides, "fixture must apply at least one tier override"

    svc._elo_cache = None
    cold = svc._compute_elo(pool)        # full compute
    warm = svc._compute_elo(pool)        # cache hit

    for pid, pinned in overrides.items():
        # Overridden players are anchored: their ELO equals the pinned value
        # exactly, with no drift, on both the cold and the warm path.
        assert cold[pid] == pinned
        assert warm[pid] == pinned
    assert warm == cold


def test_stats_memo_identical_to_reference():
    svc = _build_service()
    pool = svc._pool("RB")

    svc._stats_cache = None
    reference = copy.deepcopy(svc._compute_stats(pool))
    assert reference

    second = svc._compute_stats(pool)
    assert second == reference
    assert second is svc._stats_cache


# ---------------------------------------------------------------------------
# (c) Mutation invalidates the cache and forces a correct recompute
# ---------------------------------------------------------------------------

def test_recording_swipe_bumps_version_and_recomputes():
    svc = _build_service()
    pool = svc._pool("RB")

    before = svc._compute_elo(pool)          # warm the cache
    v_before = svc._version
    cached_obj = svc._elo_cache
    assert svc._compute_elo(pool) is cached_obj  # confirm warm

    # Mutate: a new ranking swipe must bump _version.
    svc.record_ranking(["r5", "r4", "r3"])
    assert svc._version > v_before           # AC-2 / AC-5

    after = svc._compute_elo(pool)
    assert svc._elo_cache_version == svc._version
    assert after is not cached_obj           # recomputed, not the stale object
    # The new swipe pushed r5 above r4 (winner over loser): the ELO map moved.
    assert after != before


def test_tier_override_bumps_version_and_recomputes():
    svc = _build_service()
    pool = svc._pool("RB")

    before = svc._compute_elo(pool)
    v_before = svc._version

    # Re-tier r2 into the top tier — apply_tiers must bump _version (ranking_service:828).
    svc.apply_tiers(
        position="RB",
        tiers={"firsts_4plus": ["r2"]},
        scoring_format="1qb_ppr",
    )
    assert svc._version > v_before

    after = svc._compute_elo(pool)
    assert after != before
    # r2's new override must now be reflected exactly (anchored).
    assert after["r2"] == svc._elo_overrides["r2"]


def test_reorder_bumps_version_and_recomputes():
    svc = _build_service()
    pool = svc._pool("RB")

    svc._compute_elo(pool)
    v_before = svc._version

    # apply_reorder must bump _version (ranking_service:859).
    svc.apply_reorder("RB", ["r6", "r5", "r4", "r3", "r2", "r1"])
    assert svc._version > v_before

    after = svc._compute_elo(pool)
    assert svc._elo_cache_version == svc._version
    # The reorder put r6 first: its override ELO is now the pool max.
    assert after["r6"] == max(after.values())


# ---------------------------------------------------------------------------
# (d) Full-compute body runs ONCE per request, not 3-4x
# ---------------------------------------------------------------------------

def test_get_rankings_computes_elo_once():
    """get_rankings calls _compute_elo and _compute_stats once each. Across a
    single warm request the full-compute body must run at most once per
    method, and a second get_rankings on the unchanged service must reuse the
    cache (zero additional full computes)."""
    svc = _build_service()

    with _elo_spy(svc) as elo, _stats_spy(svc) as stats:
        svc.get_rankings(position="RB")
        assert elo.full_computes == 1
        assert stats.full_computes == 1

        # A second read with no mutation: pure cache hits.
        svc.get_rankings(position="RB")
        assert elo.full_computes == 1
        assert stats.full_computes == 1
        assert elo.calls == 2             # called both times, computed once


def test_trio_path_computes_elo_once_per_request():
    """The algorithmic trio path (_algorithmic_trio) calls _compute_elo and
    _compute_stats; on a warm instance each full-compute body runs at most once
    for the request (AC-4: collapse 3-4x -> 1x)."""
    svc = _build_service()
    # Warm the position pool once so the trio request below is "warm".
    svc.get_rankings(position="RB")

    with _elo_spy(svc) as elo, _stats_spy(svc) as stats:
        # get_next_trio -> _algorithmic_trio over the same RB pool.
        svc.get_next_trio(position="RB")
        # Warm instance: no full compute should be needed for the same pool.
        assert elo.full_computes == 0
        assert stats.full_computes == 0

    # And from a cold instance the trio request computes each at most once.
    svc2 = _build_service()
    with _elo_spy(svc2) as elo2, _stats_spy(svc2) as stats2:
        svc2.get_next_trio(position="RB")
        assert elo2.full_computes <= 1
        assert stats2.full_computes <= 1


# ---------------------------------------------------------------------------
# Pool-sensitivity: different pools at the same _version must NOT collide.
# This guards the (version, pool) cache key — a version-only key would return
# a wrong-pool result here and silently corrupt tier placement.
# ---------------------------------------------------------------------------

def test_different_pools_same_version_do_not_collide():
    svc = _build_service()
    full_pool = svc._pool("RB")
    sub_pool = full_pool[:3]              # a distinct, smaller pool

    full_elo = dict(svc._compute_elo(full_pool))
    sub_elo = dict(svc._compute_elo(sub_pool))

    # Sub-pool result is keyed only to its members.
    assert set(sub_elo.keys()) == {p.id for p in sub_pool}
    # Re-asking for the full pool at the same _version must still return the
    # full-pool result, not the cached sub-pool result.
    full_again = svc._compute_elo(full_pool)
    assert full_again == full_elo
    assert set(full_again.keys()) == {p.id for p in full_pool}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
