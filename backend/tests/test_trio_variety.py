"""Trio variety + anti-repeat.

Two operator asks:
  1. Trios should VARY between strategies (boundary / within-tier / tightest)
     rather than running the same kind over and over.
  2. Add a "top vs bottom of the SAME tier" variety so intra-tier order is solid.
  3. Fix the observed bug: ~10 trios in a row reusing 2 of the same players.
  4. FB #97 ("I get Bijan Gibbs Jeanty way too frequently"): the top value
     cluster must not recur — deterministic extremes-picking, an elite-first
     cursor on every service rebuild, and all-or-nothing avoid relaxation all
     funneled trios back to the same 2-3 top players.

Plan: docs/plans/trios-tier-calibration-plan-2026-07-08.md
"""

import itertools
import json
import os
import random
from collections import Counter

import pytest

import backend.ranking_service as rs
from backend.data_loader import seed_elo_for_value
from backend.ranking_service import Player, RankingService

# Pick-value ladder bands (2026-07-12 8-tier ladder, uniform in Elo space).
# Pack ~6 players into each band so within-tier trios have >=3 members and
# the pool is large enough for anti-repeat to breathe.
_BANDS = {
    "firsts_4plus": (1927, 1972),
    "firsts_3":     (1869, 1922),
    "firsts_2":     (1788, 1864),
    "first_1":      (1580, 1785),
    "second":       (1400, 1575),
    "third":        (1280, 1395),
    "fourth":       (1220, 1275),
    "waivers":      (1150, 1215),
}


def _big_pool_service():
    seeds = {}
    for tier, (lo, hi) in _BANDS.items():
        for i in range(6):
            seeds[f"{tier}{i}"] = lo + (hi - lo) * i / 5.0
    players = [Player(id=p, name=p, position="WR", team="A", age=25) for p in seeds]
    s = RankingService(players=players, seed_ratings=seeds)
    s._scoring_format = "1qb_ppr"
    return s, seeds


def _ids(trio):
    return {trio.player_a.id, trio.player_b.id, trio.player_c.id}


def test_within_tier_trio_spans_one_tier_top_to_bottom(monkeypatch):
    s, _ = _big_pool_service()
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.0)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 1.0)  # force within-tier
    trio = s.get_next_trio(position="WR")
    assert trio.reasoning.startswith("Within-tier spread:")
    elo = s._compute_elo(s._pool("WR"))
    tiers = {RankingService.tier_for_elo(elo[p.id], "WR", "1qb_ppr")
             for p in (trio.player_a, trio.player_b, trio.player_c)}
    assert len(tiers) == 1, f"within-tier trio must stay in one tier, got {tiers}"
    # a = top of tier, c = bottom.
    assert elo[trio.player_a.id] >= elo[trio.player_c.id]


def test_no_two_consecutive_trios_reuse_two_players(monkeypatch):
    """The core bug: never surface 2 of the same players back-to-back."""
    random.seed(1234)
    s, _ = _big_pool_service()
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.4)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 0.35)
    monkeypatch.setitem(rs._cfg, "trio_repeat_avoid", 3.0)

    prev = None
    for _ in range(14):
        trio = s.get_next_trio(position="WR")
        cur = _ids(trio)
        if prev is not None:
            assert len(cur & prev) < 2, f"repeated {cur & prev} back-to-back"
        prev = cur
        # advance state as if the user ranked them
        s.record_ranking([trio.player_a.id, trio.player_b.id, trio.player_c.id])


def test_strategy_rotates_over_a_session(monkeypatch):
    """Over a run we should see more than one KIND of trio (variety)."""
    random.seed(7)
    s, _ = _big_pool_service()
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.4)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 0.35)

    kinds = set()
    for _ in range(16):
        trio = s.get_next_trio(position="WR")
        kinds.add(trio.reasoning.split(":")[0])   # "Boundary probe" / "Within-tier spread" / "Tightest uncompared trio by Elo."
        s.record_ranking([trio.player_a.id, trio.player_b.id, trio.player_c.id])
    assert len(kinds) >= 2, f"expected varied trio kinds, only saw {kinds}"


def test_pick_variety_never_repeats_immediately(monkeypatch):
    s, _ = _big_pool_service()
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.4)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 0.35)
    random.seed(99)
    last = None
    for _ in range(30):
        v = s._pick_trio_variety("WR")
        if last is not None:
            assert v != last, "strategy repeated immediately despite alternatives"
        last = v
        s._trio_last_variety = v


# ── FB #97 — top-cluster repetition ──────────────────────────────────────
_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                        "dp_values_snapshot_2026-07-10.json")


def _dp_rb_service(fmt="1qb_ppr", top_n=60):
    """Realistic pool: top-N RBs seeded from the checked-in DP snapshot
    through the real seed map (data_loader.seed_elo_for_value — the #117
    value-affine recalibration)."""
    with open(_FIXTURE) as f:
        vals = json.load(f)["values"][fmt]["RB"][:top_n]
    seeds = {f"RB{i+1:02d}": seed_elo_for_value(v) for i, v in enumerate(vals)}
    players = [Player(id=p, name=p, position="RB", team="T", age=24) for p in seeds]
    s = RankingService(players=players, seed_ratings=seeds)
    s._scoring_format = fmt
    return s, seeds


def test_repetition_bound_over_20_consecutive_trios(monkeypatch):
    """FB #97 regression bound: in 20 consecutive trios from a realistic RB
    pool, no player appears more than 3 times and no exact pair recurs more
    than twice. (Pre-fix: the top RB hit 4+ and the same elite pair kept
    coming back.)"""
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.4)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 0.35)
    monkeypatch.setitem(rs._cfg, "trio_repeat_avoid", 8.0)
    for seed in (0, 1, 2):
        random.seed(seed)
        s, seeds = _dp_rb_service()
        freq, pairs = Counter(), Counter()
        for _ in range(20):
            trio = s.get_next_trio(position="RB")
            ids = sorted(_ids(trio))
            freq.update(ids)
            pairs.update(itertools.combinations(ids, 2))
            s.record_ranking(sorted(ids, key=lambda p: seeds[p], reverse=True))
        worst_p, n_p = freq.most_common(1)[0]
        assert n_p <= 3, f"seed {seed}: {worst_p} served {n_p}x in 20 trios"
        worst_pr, n_pr = pairs.most_common(1)[0]
        assert n_pr <= 2, f"seed {seed}: pair {worst_pr} served {n_pr}x in 20 trios"


def test_session_rebuilds_do_not_open_on_the_same_players(monkeypatch):
    """FB #97 root cause: in-memory variety state resets on every service
    rebuild (app session / server restart), and the within-tier cursor always
    started at elite — so the SAME top players opened every session. Across 6
    simulated rebuilds, no player may appear in every session's opening trios."""
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.4)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 0.35)
    monkeypatch.setitem(rs._cfg, "trio_repeat_avoid", 8.0)
    random.seed(0)
    _, seeds = _dp_rb_service()
    swipe_log: list[dict] = []
    sessions_seen = Counter()
    n_sessions = 6
    for _ in range(n_sessions):
        s, _seeds = _dp_rb_service()   # rebuild = variety state resets
        s.replay_from_db(swipe_log)
        opening = set()
        for _t in range(3):
            trio = s.get_next_trio(position="RB")
            ids = sorted(_ids(trio))
            opening |= set(ids)
            ordered = sorted(ids, key=lambda p: seeds[p], reverse=True)
            s.record_ranking(ordered)
            for i, j in itertools.combinations(range(3), 2):
                swipe_log.append({"winner_player_id": ordered[i],
                                  "loser_player_id": ordered[j],
                                  "decision_type": "rank", "k_factor": 32.0})
        sessions_seen.update(opening)
    worst, n = sessions_seen.most_common(1)[0]
    assert n < n_sessions, (
        f"{worst} opened ALL {n_sessions} sessions — rebuilds keep re-serving "
        "the same faces"
    )


def test_within_tier_avoid_relaxes_partially_not_fully():
    """When a small tier sits entirely inside the avoid window, relaxation
    must re-admit the longest-unseen members — not reset to the full tier and
    re-serve the identical trio (the Bijan/Gibbs/Jeanty loop)."""
    # 4 first_1-band players (so one is always left out of a trio) + a
    # second-band filler cohort.
    seeds = {f"e{i}": 1700 + i * 25 for i in range(4)}       # 1700–1775 = first_1
    seeds.update({f"s{i}": 1410 + i * 20 for i in range(6)})  # 1410–1510 = second
    players = [Player(id=p, name=p, position="WR", team="A", age=25) for p in seeds]
    s = RankingService(players=players, seed_ratings=seeds)
    s._scoring_format = "1qb_ppr"

    random.seed(3)
    s._within_tier_cursor = 0  # walk starts at the top; first_1 is the
    # highest occupied tier (the firsts_* tiers are empty in this pool)
    first = s._within_tier_trio("WR", avoid=s._trio_avoid_ids())
    s._remember_trio(first)
    s._within_tier_cursor = 0  # aim at the same tier again, all 3 now in avoid
    second = s._within_tier_trio("WR", avoid=s._trio_avoid_ids())
    assert second is not None
    assert _ids(second) != _ids(first), (
        "avoid relaxation re-served the identical small-tier trio"
    )
    # The one top-band player who sat out the first trio must be in the second.
    left_out = {f"e{i}" for i in range(4)} - _ids(first)
    assert left_out <= _ids(second)


def test_within_tier_top_pick_varies_across_serves():
    """The tier's #1 player must not headline EVERY within-tier trio for that
    tier (pre-fix: top slot was always the max-Elo member)."""
    s, _ = _big_pool_service()
    random.seed(5)
    tops = set()
    for _ in range(12):
        s._within_tier_cursor = 0  # top tier every time
        trio = s._within_tier_trio("WR", avoid=set())
        tops.add(trio.player_a.id)
    assert len(tops) >= 2, f"top slot always went to {tops}"


def test_boundary_straddlers_vary_across_serves():
    """Boundary probes must rotate among eligible edge straddlers instead of
    always serving the deterministic closest-to-edge pair."""
    s, _ = _big_pool_service()
    random.seed(11)
    pairs = set()
    for _ in range(12):
        trio = s._boundary_trio("WR", avoid=set())
        assert trio is not None
        pairs.add((trio.player_a.id, trio.player_b.id))
    assert len(pairs) >= 2, f"boundary probe always served {pairs}"


def test_within_tier_cursor_covers_multiple_tiers(monkeypatch):
    """Successive within-tier trios should target DIFFERENT tiers over time."""
    s, _ = _big_pool_service()
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.0)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 1.0)
    monkeypatch.setitem(rs._cfg, "trio_repeat_avoid", 0.0)
    seen_tiers = set()
    for _ in range(5):
        trio = s.get_next_trio(position="WR")
        seen_tiers.add(trio.reasoning.split(": ", 1)[1])
        s.record_ranking([trio.player_a.id, trio.player_b.id, trio.player_c.id])
    assert len(seen_tiers) >= 3, f"within-tier trios clustered on {seen_tiers}"
