"""Backlog #10 — crown-asset consolidation premium.

Pins (docs/plans/competitor-top20/10-key-asset-package-adjustment.md):
  1. package_value_v2 is byte-identical without n_other / flag off / on
     equal-or-larger count sides (the neutrality guard).
  2. The top asset of a SMALLER-count side gets a premium scaled by its share,
     zero below crown_share_floor.
  3. Engine: a 1-for-1 trade is unchanged vs flag-off (count-symmetric); an
     N-for-1 shifts the fairness ratio in favor of the single-asset side.

Flags/_cfg snapshot-restored per test.
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League, LeagueMember, TradeService, package_value_v2,
)


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _set(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


# ───────────────────────── package_value_v2 unit ─────────────────────────

def test_no_n_other_is_unchanged():
    # Default (no n_other) never applies crown, flag on or off.
    base = package_value_v2([5000.0], 5000.0)
    _set(**{"trade.crown_asset": True})
    assert package_value_v2([5000.0], 5000.0) == base
    assert package_value_v2([5000.0], 5000.0, n_other=None) == base


def test_flag_off_is_unchanged_even_with_n_other():
    base = package_value_v2([5000.0], 5000.0)
    # flag off (default fixture) + consolidation context ⇒ still no crown.
    assert package_value_v2([5000.0], 5000.0, n_other=3) == base


def test_equal_or_larger_count_no_crown():
    _set(**{"trade.crown_asset": True})
    # 3-asset side vs 1-asset other → len(values) !< n_other → no crown.
    vals = [4000.0, 2000.0, 1000.0]
    assert package_value_v2(vals, 4000.0, n_other=1) == package_value_v2(vals, 4000.0)
    # 2 vs 2 → equal → no crown.
    assert package_value_v2([3000.0, 1000.0], 3000.0, n_other=2) == \
           package_value_v2([3000.0, 1000.0], 3000.0)


def test_smaller_count_top_asset_gets_premium():
    _set(**{"trade.crown_asset": True})
    base = package_value_v2([5000.0], 5000.0)          # lone elite, no context
    crowned = package_value_v2([5000.0], 5000.0, n_other=3)  # 1-for-3 consolidation
    # share = 1.0 > floor 0.5 ⇒ premium = crown_rate * (1-.5)/(1-.5) = 0.12.
    # base for a lone asset == its value (contribution factor 1.0), so crowned
    # ≈ value * 1.12.
    assert crowned == pytest.approx(base * 1.12, rel=1e-6)


def test_premium_zero_below_floor():
    _set(**{"trade.crown_asset": True})
    # Two near-equal assets on the smaller side → top share ~0.5 ≈ floor ⇒ ~no premium.
    vals = [2600.0, 2400.0]   # share 0.52, just over floor → tiny premium
    base = package_value_v2(vals, 2600.0)
    crowned = package_value_v2(vals, 2600.0, n_other=3)
    assert crowned >= base
    assert (crowned - base) / base < 0.02      # small, since share barely clears floor


def test_premium_monotone_in_share():
    _set(**{"trade.crown_asset": True})
    # Higher top-asset share → larger premium.
    low  = package_value_v2([2600.0, 2400.0], 2600.0, n_other=3)   # share .52
    lo_base = package_value_v2([2600.0, 2400.0], 2600.0)
    hi  = package_value_v2([4800.0, 200.0], 4800.0, n_other=3)     # share .96
    hi_base = package_value_v2([4800.0, 200.0], 4800.0)
    assert (hi - hi_base) / hi_base > (low - lo_base) / lo_base


# ───────────────────────── engine neutrality + effect ─────────────────────────

class _Player:
    def __init__(self, pid, position="RB"):
        self.id = pid
        self.name = pid
        self.position = position
        self.team = "TST"
        self.age = 25
        self.search_rank = 50
        self.pick_value = None


def _svc(player_ids, opp):
    players = {pid: _Player(pid) for pid in player_ids}
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    return s


def test_one_for_one_unchanged_by_crown():
    # A 1-for-1 must be byte-identical with crown on (count-symmetric).
    opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                       elo_ratings={"G": 1700, "R": 1500}, has_rankings=True)
    args = dict(user_id="user", user_elo={"G": 1500, "R": 1700},
                user_roster=["G"], league_id="L1",
                seed_elo={"G": 1540, "R": 1500}, fairness_threshold=0.05)

    _set(**{"trade_engine.v2": True})
    off = _svc(["G", "R"], opp)
    base = off.generate_trades(**args)

    _set(**{"trade_engine.v2": True, "trade.crown_asset": True})
    on = _svc(["G", "R"], LeagueMember(user_id="opp", username="opp", roster=["R"],
              elo_ratings={"G": 1700, "R": 1500}, has_rankings=True))
    crowned = on.generate_trades(**args)

    assert [(c.give_player_ids, c.receive_player_ids, c.fairness_score, c.composite_score)
            for c in base] == \
           [(c.give_player_ids, c.receive_player_ids, c.fairness_score, c.composite_score)
            for c in crowned]


def test_consolidation_fairness_shifts():
    # 2-for-1: user gives a stud G for two opponent depth pieces R1+R2. With
    # crown on, G's single-asset side is priced up → the consensus fairness of
    # the same enumerated combo differs from flag-off.
    from backend.trade_service import package_value_v2 as pv
    g_only = [6000.0]
    depth  = [3200.0, 3000.0]
    vmax = 6000.0
    f_off = min(pv(g_only, vmax), pv(depth, vmax)) / max(pv(g_only, vmax), pv(depth, vmax))
    _set(**{"trade.crown_asset": True})
    gv = pv(g_only, vmax, n_other=2)   # 1 < 2 → crown
    rv = pv(depth, vmax, n_other=1)    # 2 !< 1 → no crown
    f_on = min(gv, rv) / max(gv, rv)
    # G side rises ⇒ the give/receive ratio moves (G side closer to the depth side).
    assert f_on != pytest.approx(f_off)
    assert gv > pv(g_only, vmax)       # the stud was priced up
