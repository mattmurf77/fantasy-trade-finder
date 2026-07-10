"""
trade_service.py — Fantasy Trade Finder
=========================================
Generates trade cards by comparing ranking sets across league members.

Core algorithm:
  For every pair of players (p1 in user_roster, p2 in opponent_roster):
    - If the user values p1 LESS than the opponent does       (user undervalues p1)
    - AND the opponent values p2 LESS than the user does      (opponent undervalues p2)
    → There's a perceived mutual gain: user trades p1 for p2

  Value mismatch score = (opp_elo[p1] - user_elo[p1])   # what user gives up = opponent gains
                       + (user_elo[p2] - opp_elo[p2])   # what user receives = more than opponent thinks

  Fairness score: trade is filtered out if consensus values are too lopsided
  (prevents surfacing wildly imbalanced trades that nobody would accept)
"""

import heapq
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from itertools import combinations
from typing import Optional

from .feature_flags import FLAGS
from .trade_narrative import build_narrative


# ---------------------------------------------------------------------------
# Runtime config — loaded from model_config DB table at startup and on
# demand.  Falls back to the defaults below if the DB hasn't been seeded yet.
# ---------------------------------------------------------------------------

_DEFAULT_CFG: dict[str, float] = {
    # Team Outlook age thresholds
    "vet_age":               27,
    "youth_age":             26,
    "jets_age":              25,
    # Team Outlook score multipliers
    "boost_strong":          1.50,
    "boost_moderate":        1.25,
    "neutral":               1.00,
    "penalty_soft":          0.75,
    "penalty_mod":           0.60,
    "penalty_heavy":         0.30,
    # KTC dynasty value curve
    "ktc_k":                 0.0126,
    "ktc_max":           10000.0,
    "ktc_fallback_rank":   300.0,
    # Package diminishing-returns weights
    "package_weight_1":      1.00,
    "package_weight_2":      0.75,
    "package_weight_3":      0.55,
    "package_weight_4":      0.40,
    "package_weight_5":      0.28,
    # Backlog #10 — crown-asset consolidation premium (flag: trade.crown_asset).
    # The top asset of the SMALLER-count side gains value ramping from 0 at
    # share<=floor to crown_rate at share=1.0. See package_value_v2.
    "crown_rate":            0.12,
    "crown_share_floor":     0.50,
    # Positional preference multipliers
    "pos_acquire_bonus":     0.20,
    "pos_tradeaway_bonus":   0.15,
    "pos_conflict_penalty":  0.15,
    "pos_multiplier_cap":    2.00,
    # Backlog #2 — per-player target multiplier (flag: trade.preference_lists).
    # +N per received TARGET player, capped by pos_multiplier_cap. Mirrors the
    # (dormant) pos_acquire_bonus pattern at player granularity.
    "target_acquire_bonus":  0.20,
    # TradeService scoring thresholds
    "min_mismatch_score":   40.0,
    "max_value_ratio":       2.5,
    "mismatch_weight":       0.70,
    "fairness_weight":       0.30,
    # Per-opponent candidate ceiling. Was 500 (which never bit, since
    # max_per_opponent filters down to 5 anyway), so 1-for-1 / 2-for-1 /
    # 1-for-2 enumeration ran to the 3s deadline on every opponent
    # instead of short-circuiting once "enough" candidates were found.
    # 30 is comfortably above the 5-card-per-opponent target while still
    # bailing the inner loops early.
    "max_candidates":       30.0,
    # Trade ELO gap filter
    "trade_elo_gap_max":   250.0,
    # Agent A8 — trade-math adjustments (all behind feature flags)
    "qb_tax_rate":               0.075,  # 7.5% penalty when a side gets a premium QB
    "star_tax_per_tier_gap":     0.10,   # 10% penalty per tier gap beyond 1
    "star_tax_elite_multiplier": 1.5,    # extra multiplier when a Tier-1 star is traded away
    "roster_spot_penalty":       0.05,   # 5% penalty per extra roster spot used
    "roster_clogger_penalty":    0.10,   # 10% ADDITIONAL penalty per player beyond 2 in a 3+ one-way
    "roster_clogger_threshold":  3.0,    # 3+ players one-way triggers "clogger"
    # Tier-priority multipliers — applied to composite_score based on the
    # highest tier across both sides of the trade. Without this, the engine
    # gravitates to depth-vs-bench trades because mismatch math favors
    # players with high valuation variance (and depth tiers have more
    # variance than elites). User feedback: trade suggestions over-index
    # on depth tier; we want elite/starter players to dominate the deck.
    "tier_mult_elite":      1.60,
    "tier_mult_starter":    1.25,
    "tier_mult_solid":      1.00,
    "tier_mult_depth":      0.55,
    "tier_mult_bench":      0.35,
    # ------------------------------------------------------------------
    # Trade engine v2 (flag: trade_engine.v2) — Tier 1 plan + amendments
    # ------------------------------------------------------------------
    # Single value space (Change 1): elo_to_value() exponential transform
    "elo_value_k":           0.0050,  # steepness of Elo→value curve
    "elo_value_ref":      1500.0,     # Elo that maps to the reference value
    "elo_value_base":     1000.0,     # value at the reference Elo
    # KTC-style package adjustment exponent (amendment A2)
    "package_adj_gamma":     1.5,
    # True mutual gain (Change 3 + amendment A1)
    "min_side_surplus":    150.0,     # min per-side value gain to surface a trade
    "mutual_gain_cap":    1500.0,     # normalization ceiling for the harmonic mean
    # Waiver/roster-slot cost (amendment A3, FantasyCalc-derived ≈ rank-300 value)
    "waiver_slot_cost":    425.0,     # value cost per extra player received
    # Confidence shrinkage + range-overlap fairness (Change 4 + amendment A4)
    "shrink_pseudocount":    4.0,     # n0 in w = n/(n+n0) shrinkage toward seed
    "range_base":            0.35,    # value half-width FRACTION at n=0 comparisons
    # ------------------------------------------------------------------
    # Tier 2 — work item 2.1: marginal (over-replacement) valuation
    # (flag: trade.marginal_value — docs/plans/trade-engine-tier2-models.md)
    # ------------------------------------------------------------------
    "bench_credit_rate":         0.15,   # fraction of raw value depth keeps
    "waiver_baseline_value":   250.0,    # replacement floor when a position is thin
    # min_side_surplus replacement when the marginal flag is ON: marginal
    # values are systematically smaller than raw values (a package collapses
    # to over-replacement deltas + a 15% bench credit), so the raw-value
    # 150 bar would gate out nearly every legitimate marginal-gain trade.
    "min_side_surplus_marginal": 60.0,
    # ------------------------------------------------------------------
    # Tier 2 — work item 2.2: outlook as now/future valuation blend
    # (flag: trade.outlook_blend). α = weight on NOW value; 1−α on FUTURE.
    # Age-curve breakpoints/slopes live as a code constant table
    # (_AGE_NOW_CURVE / _AGE_FUTURE_CURVE below) — see comment there.
    # ------------------------------------------------------------------
    "outlook_alpha_championship": 1.00,
    "outlook_alpha_contender":    0.75,
    "outlook_alpha_not_sure":     0.50,   # also used for outlook=None/unknown
    "outlook_alpha_rebuilder":    0.25,
    "outlook_alpha_jets":         0.10,
    # Backlog #1 — opponent outlook inference (flag: trade.outlook_infer).
    # Weights on the three contend↔rebuild signals + the score cutoffs that
    # bucket into contender / not_sure / rebuilder. See infer_team_outlook.
    "infer_w_vet_share":          1.00,
    "infer_w_youth_share":        1.00,
    "infer_w_pick_share":         2.00,
    "infer_contender_cut":        0.08,
    "infer_rebuilder_cut":       -0.08,
    # ------------------------------------------------------------------
    # Tier 2 amendment A6 — league-wide deck diversification
    # (flag: trade.deck_diversity — consumed by server._order_deck)
    # ------------------------------------------------------------------
    "diversity_window_days":      7.0,   # lookback for league impression counts
    "diversity_user_cap":         3.0,   # >= this many OTHER members shown a target → penalize
    "diversity_penalty":          0.6,   # ordering-key multiplier for saturated targets
    "deck_max_per_target":        3.0,   # intra-deck cap: cards per top receive asset
    # ------------------------------------------------------------------
    # Tier 3 — trade_optimizer.py (flags: trade_engine.v3, trade.three_team)
    # ------------------------------------------------------------------
    "v3_pool_size":              12.0,   # per-side candidate pool for exact enumeration
    "sweetener_band":             0.15,  # fairness shortfall band eligible for a sweetener
    "sweetener_max_cards":        2.0,   # max sweetened cards per opponent pair
    "cycle_edge_min_gain":      100.0,   # min per-transfer marginal gain for a cycle edge
    "cycle_min_net":            200.0,   # min net gain per team for a 3-team cycle
    "cycle_max_results":          3.0,   # max 3-team cycles returned per league
    # Tier 2 (2.3b) — fuzzy mirror matching tolerance (consumed by server)
    "fuzzy_match_tau":            0.8,   # Jaccard threshold per side
    # Deck composition (verified against real data 2026-06-09)
    "v3_diversity_max_overlap":   0.4,   # max asset Jaccard between two cards of one pair
    "consensus_score_scale":      0.3,   # consensus fallback cards rank below divergence finds
    # FB-47 finder targeting (flag trade.finder_targeting) — counterparty
    # positional-fit blend: composite *= 1 + w * (fit - 0.5), fit ∈ [0,1].
    # Consensus cards lean on fit hard (no divergence signal to compete
    # with); divergence cards keep it at tiebreak strength.
    "fit_consensus_weight":       0.5,
    "fit_divergence_weight":      0.15,
    # FB-96 (flag trade.need_fit) — automatic positional-need fit:
    # composite *= 1 + w * (need_fit - 0.5), need_fit ∈ [0,1]. Bounded
    # multiplier applied AFTER all gates — reorders acceptable trades,
    # never rescues gated ones. 0 disables the reordering entirely.
    "need_fit_weight":            0.30,
}

# Live config — updated by reload_config().  Starts as a copy of defaults.
_cfg: dict[str, float] = dict(_DEFAULT_CFG)


def reload_config() -> None:
    """
    Pull the latest values from model_config and update the module-level
    _cfg dict in-place.  Call this at server startup and after any PUT to
    /api/admin/config.
    """
    global _cfg
    try:
        from .database import get_config as _db_get_config
        fresh = _db_get_config()
        if fresh:
            _cfg.update(fresh)
    except Exception:
        pass  # DB unavailable — keep existing values


def _c(key: str) -> float:
    """Convenience accessor: return live config value with default fallback."""
    return _cfg.get(key, _DEFAULT_CFG[key])


# ---------------------------------------------------------------------------
# KTC-style Dynasty Value
# ---------------------------------------------------------------------------
# Exponential decay: rank 1 ≈ 9875, rank 200 ≈ 806, rank 500 ≈ ~66
# All constants are now live-loaded from _cfg (seeded from model_config table).


def dynasty_value(player, rank_override: int | None = None) -> float:
    """
    KTC-style exponential dynasty value for a single player/pick.

    For draft picks (position == "PICK"): player.pick_value is on the
    0-100 round-tier scale (compute_pick_value in database.py; mid-1st =
    67.5 — NOT 0-10000). Bridge it into the shared value space via the
    same calibration the universal pool's generic picks use, where
    pick_value = (seed_elo - 1200) / 6 (see build_universal_pool in
    server.py): elo = 1200 + 6*pick_value, then elo_to_value(elo). A
    league mid-1st therefore prices identically to its generic-pick twin
    instead of at ~67 (near-zero next to players in the thousands).

    For regular players: uses player.search_rank (1-based, lower = better).
    Falls back to ktc_fallback_rank config if no rank is stored.

    rank_override lets callers supply a rank directly (used in tests / calcs
    where we want to bypass the player object).
    """
    ktc_k   = _c("ktc_k")
    ktc_max = _c("ktc_max")

    if rank_override is not None:
        rank = max(rank_override, 1)
        return round(ktc_max * math.exp(-ktc_k * (rank - 1)), 1)

    if getattr(player, "position", None) == "PICK":
        pv = getattr(player, "pick_value", None)
        if not pv:
            # Unknown pick value → neutral mid-asset value, same number the
            # old fallback returned (= elo_to_value at the reference Elo).
            return 1000.0
        return round(elo_to_value(1200.0 + 6.0 * float(pv)), 1)

    fallback = int(_c("ktc_fallback_rank"))
    rank = getattr(player, "search_rank", None) or fallback
    rank = max(int(rank), 1)
    return round(ktc_max * math.exp(-ktc_k * (rank - 1)), 1)


def package_value(individual_values: list[float]) -> float:
    """
    Aggregate dynasty value for a trade package with diminishing returns.

    The best player is weighted 1.0, second 0.75, third 0.55, etc.
    This mirrors how real dynasty managers value multi-player packages.
    Weights are loaded from _cfg (package_weight_1 … package_weight_5).
    """
    if not individual_values:
        return 0.0
    weights = [
        _c("package_weight_1"),
        _c("package_weight_2"),
        _c("package_weight_3"),
        _c("package_weight_4"),
        _c("package_weight_5"),
    ]
    sorted_vals = sorted(individual_values, reverse=True)
    total = sum(v * w for v, w in zip(sorted_vals, weights))
    return round(total, 1)


# ---------------------------------------------------------------------------
# Trade engine v2 — single value space + package math
# (flag: trade_engine.v2 — see docs/plans/trade-engine-tier1-fixes.md and
#  docs/reviews/trade-engine-external-research.md §6 amendments A1–A4)
# ---------------------------------------------------------------------------


def elo_to_value(elo: float) -> float:
    """
    Map a personal/seed Elo rating onto the dynasty-value scale used for
    ALL v2 trade math. Monotone increasing. Calibrated so the transform of
    a typical elite Elo (~1790) ≈ the KTC value of a top-5 player and a
    replacement-level Elo (~1300) ≈ a low-end bench value.

        value = elo_value_base * exp(elo_value_k * (elo - elo_value_ref))

    With base=1000, ref=1500, k=0.0050: elo 1790 → ~4263, elo 1500 → 1000,
    elo 1300 → ~368. All constants are config-tunable (model_config).
    """
    return _c("elo_value_base") * math.exp(
        _c("elo_value_k") * (elo - _c("elo_value_ref"))
    )


def value_to_elo(value: float) -> float:
    """
    Inverse of elo_to_value: map a dynasty value back onto the Elo scale.

    Used by the pick-anchor wizard, where a user statement like "worth
    2 firsts" is a VALUE statement (2 × value of a generic mid-1st) that
    must be pinned as an Elo override. Clamps at a tiny positive value so
    a zero/negative input can't blow up the log.
    """
    v = max(float(value), 1e-9)
    return _c("elo_value_ref") + math.log(v / _c("elo_value_base")) / _c("elo_value_k")


def package_value_v2(values: list[float], v_max: float,
                     n_other: int | None = None) -> float:
    """
    KTC-style package value for the v2 engine (amendment A2).

    Inspired by KeepTradeCut's reverse-engineered "raw adjustment": each
    asset in a trade contributes only a fraction of its raw value, and the
    fraction shrinks exponentially as the asset's value falls relative to
    the best asset in the trade ("four quarters ≠ a dollar"). KTC's full
    formula is p·[0.29(p/v)^8 + 0.28(p/t)^1.3 + 0.07(p/(v+2000))^1.28];
    we use the single-term simplification

        contribution(v) = v * (0.15 + 0.85 * (v / v_max) ** package_adj_gamma)

    where v_max is the best single-asset value in the WHOLE trade (in the
    same value space as `values`) and package_adj_gamma (default 1.5) is
    config-tunable. The best asset contributes 100% of its value; lesser
    assets bottom out at 15%. The legacy `package_value` (fixed diminishing
    weights) is retained untouched for the legacy path.

    Backlog #10 — crown-asset premium (flag trade.crown_asset). When
    ``n_other`` (the OTHER side's asset count) is supplied AND this side has
    fewer assets than the other side, the top asset gets a consolidation
    premium scaled by its share of this side's raw total — the market's
    "don't split a dollar into 100 pennies" adjustment (FPTrack Crown Asset /
    Dynasty Daddy Value Adjustment). The cross-side count guard makes the
    premium exactly 0 on equal-count trades (1-for-1, 2-for-2), so flag-off
    and symmetric trades are byte-identical. Callers that omit ``n_other``
    (legacy/unmigrated) are likewise unaffected.
    """
    if not values:
        return 0.0
    v_max = max(v_max, 1e-9)
    gamma = _c("package_adj_gamma")
    total = sum(v * (0.15 + 0.85 * (v / v_max) ** gamma) for v in values)

    if (FLAGS.trade_crown_asset and n_other is not None
            and len(values) < n_other):
        side_sum = sum(values)
        if side_sum > 0:
            v_top = max(values)
            share = v_top / side_sum
            floor = _c("crown_share_floor")
            if share > floor:
                premium = _c("crown_rate") * (share - floor) / max(1.0 - floor, 1e-9)
                top_contrib = v_top * (0.15 + 0.85 * (v_top / v_max) ** gamma)
                total += premium * top_contrib
    return round(total, 1)


def _harmonic_mean(a: float, b: float) -> float:
    """Harmonic mean of two surpluses (amendment A1). 0 if either ≤ 0."""
    if a <= 0 or b <= 0:
        return 0.0
    return 2.0 * a * b / (a + b)


def _shrink_user_elo(
    user_elo: dict[str, float],
    seed_elo: dict[str, float],
    confidence: dict[str, int] | None,
) -> dict[str, float]:
    """
    Confidence shrinkage (Change 4): shrink each personal Elo toward the
    consensus seed by how well-sampled the player is —
    w = n / (n + shrink_pseudocount). A player the user never compared
    sits at consensus (no fake divergence); a heavily-ranked player keeps
    full personal value. confidence=None → no information → no shrinkage.
    """
    if confidence is None:
        return dict(user_elo)
    n0 = _c("shrink_pseudocount")
    out: dict[str, float] = {}
    for pid, elo in user_elo.items():
        n = max(confidence.get(pid, 0), 0)
        w = n / (n + n0)
        out[pid] = w * elo + (1.0 - w) * seed_elo.get(pid, 1500.0)
    return out


def _value_uncertainty(pid: str, confidence: dict[str, int] | None) -> float:
    """
    Per-player value half-width as a FRACTION of value (amendment A4):
    unc = range_base / sqrt(1 + n). confidence=None → 0 (point values),
    which degrades the range-overlap fairness gate to the point gate.
    """
    if confidence is None:
        return 0.0
    n = max(confidence.get(pid, 0), 0)
    return _c("range_base") / math.sqrt(1.0 + n)


# ---------------------------------------------------------------------------
# Roster strength analysis (Feature 2: roster-aware match context)
# ---------------------------------------------------------------------------

# Dynasty-value tier thresholds (KTC-scale, ktc_max=10000).
# Tuned so a typical 12-team starter hits ~1500+, an elite player ~4000+.
_TIER_ELITE   = 4000.0
_TIER_STARTER = 1500.0
_TIER_BENCH   = 500.0

# Per-position starter-depth thresholds. Superflex bumps QB to require 2.
_STARTER_NEED = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
_SURPLUS_AT   = {"QB": 2, "RB": 4, "WR": 4, "TE": 2}


def _bin_player(value: float) -> str | None:
    if value >= _TIER_ELITE:
        return "elite"
    if value >= _TIER_STARTER:
        return "starter"
    if value >= _TIER_BENCH:
        return "bench"
    return None


def analyze_roster_strengths(
    roster_player_ids: list[str],
    players: dict,
    scoring_format: str = "1qb_ppr",
) -> dict:
    """
    Profile a roster's positional depth using dynasty values.

    Returns:
        {
          "tier_depth":      {pos: {"elite": n, "starter": n, "bench": n}},
          "position_needs":  [pos, ...],     # below starter threshold
          "position_surplus":[pos, ...],     # at-or-above surplus threshold
        }
    """
    tier_depth: dict[str, dict[str, int]] = {
        pos: {"elite": 0, "starter": 0, "bench": 0}
        for pos in ("QB", "RB", "WR", "TE")
    }
    starter_count: dict[str, int] = {pos: 0 for pos in tier_depth}

    for pid in roster_player_ids:
        player = players.get(pid)
        if player is None or getattr(player, "position", None) not in tier_depth:
            continue
        bin_ = _bin_player(dynasty_value(player))
        if bin_ is None:
            continue
        tier_depth[player.position][bin_] += 1
        if bin_ in ("elite", "starter"):
            starter_count[player.position] += 1

    is_superflex = scoring_format.startswith("sf")
    needs: list[str] = []
    surplus: list[str] = []
    for pos in tier_depth:
        threshold = _STARTER_NEED[pos]
        if pos == "QB" and is_superflex:
            threshold = 2
        if starter_count[pos] < threshold:
            needs.append(pos)
        if starter_count[pos] >= _SURPLUS_AT[pos]:
            surplus.append(pos)

    return {
        "tier_depth":       tier_depth,
        "position_needs":   needs,
        "position_surplus": surplus,
    }


# ---------------------------------------------------------------------------
# FB-47 — finder targeting (flag: trade.finder_targeting)
# docs/plans/trade-finder-targeting.md
# ---------------------------------------------------------------------------


def _position_strength(profile: dict, pos: str) -> float:
    """0..1 — how loaded a roster is at `pos`, from an
    analyze_roster_strengths profile. 1.0 = at/above the surplus threshold,
    0.0 = no startable players at the position."""
    td = profile.get("tier_depth", {}).get(pos, {})
    starters = td.get("elite", 0) + td.get("starter", 0)
    return min(1.0, starters / max(_SURPLUS_AT.get(pos, 2), 1))


def partner_fit_score(
    opp_profile: dict,
    acquire_targets: list[str],
    sell_targets: list[str],
) -> Optional[float]:
    """Counterparty positional fit for the user's stated targets, 0..1.

    Acquiring at P → opponents LOADED at P score high (they can spare one).
    Selling at P   → opponents THIN at P score high (they want yours).
    Multiple targets average. None when the user expressed no targets —
    callers must treat None as "targeting inactive", not as fit 0.
    """
    parts: list[float] = []
    for pos in acquire_targets:
        if pos in _SURPLUS_AT:
            parts.append(_position_strength(opp_profile, pos))
    for pos in sell_targets:
        if pos in _SURPLUS_AT:
            parts.append(1.0 - _position_strength(opp_profile, pos))
    if not parts:
        return None
    return round(sum(parts) / len(parts), 3)


# ---------------------------------------------------------------------------
# FB-96 — automatic positional-need fit (flag: trade.need_fit)
# Feedback #96: "you're weak in RB but strong in WR — here's another team
# that needs the swap with you." Unlike FB-47's partner_fit (which needs
# user-stated targets), this scores EVERY card from the two rosters'
# positional profiles alone.
# ---------------------------------------------------------------------------


def need_fit_score(
    user_profile: dict,
    opp_profile: dict,
    give_ids: list[str],
    recv_ids: list[str],
    players: dict,
    scoring_format: str = "1qb_ppr",
) -> Optional[float]:
    """Per-card positional-need fit, 0..1 (0.5 = neutral).

    Each traded QB/RB/WR/TE contributes one term:
      given player at P    → high when the USER is loaded at P (surplus to
                             spend) and the OPPONENT is thin at P (fills
                             their need)
      received player at P → high when the USER is thin at P (fills the
                             user's need) and the OPPONENT is loaded at P
                             (they can spare one)
    Terms average. Strength is _position_strength over the PRE-trade
    profiles (same Tier-2 approximation the marginal path uses), except QB
    in superflex needs one extra startable body to count as "loaded"
    (starting 2 QBs means 2 startable QBs is zero surplus).

    Returns None when no traded asset has a positional profile (e.g. a
    picks-only side) — callers must treat None as "no signal", not 0.
    """
    def _strength(profile: dict, pos: str) -> float:
        td = profile.get("tier_depth", {}).get(pos, {})
        starters = td.get("elite", 0) + td.get("starter", 0)
        denom = _SURPLUS_AT.get(pos, 2)
        if pos == "QB" and scoring_format.startswith("sf"):
            denom += 1
        return min(1.0, starters / max(denom, 1))

    parts: list[float] = []
    for pid in give_ids:
        p = players.get(pid)
        pos = getattr(p, "position", None) if p else None
        if pos in _SURPLUS_AT:
            parts.append(0.5 * _strength(user_profile, pos)
                         + 0.5 * (1.0 - _strength(opp_profile, pos)))
    for pid in recv_ids:
        p = players.get(pid)
        pos = getattr(p, "position", None) if p else None
        if pos in _SURPLUS_AT:
            parts.append(0.5 * (1.0 - _strength(user_profile, pos))
                         + 0.5 * _strength(opp_profile, pos))
    if not parts:
        return None
    return round(sum(parts) / len(parts), 3)


# ---------------------------------------------------------------------------
# Tier 2 — work item 2.1: marginal (over-replacement) valuation
# (flag: trade.marginal_value — docs/plans/trade-engine-tier2-models.md)
# ---------------------------------------------------------------------------


def _starters_at(pos: str, scoring_format: str) -> int:
    """Starter slots for a position — _STARTER_NEED, QB bumped to 2 in SF."""
    n = _STARTER_NEED.get(pos, 0)
    if pos == "QB" and scoring_format.startswith("sf"):
        n = 2
    return n


def replacement_levels(
    roster_player_ids: list[str],
    value_of,                            # callable pid → value (one side's space)
    players: dict,
    scoring_format: str = "1qb_ppr",
) -> dict[str, float]:
    """
    Per-position replacement level for a roster:

        replacement(R, pos) = value of R's best player at pos NOT in the
                              starting lineup (the player who would start
                              if a starter left)

    Starters per position come from _STARTER_NEED (QB → 2 in superflex).
    If the position has fewer than starters+1 players the replacement is
    the waiver baseline (config waiver_baseline_value) — losing anyone
    there means dipping into waivers.

    Computed from the PRE-trade roster (Tier 2 approximation; exact
    post-trade lineup re-optimization is a Tier 3 ILP feature). Only
    QB/RB/WR/TE have a replacement concept — other positions are absent
    from the returned dict.
    """
    waiver = _c("waiver_baseline_value")
    by_pos: dict[str, list[float]] = {pos: [] for pos in _STARTER_NEED}
    for pid in roster_player_ids:
        p = players.get(pid)
        pos = getattr(p, "position", None) if p else None
        if pos in by_pos:
            by_pos[pos].append(value_of(pid))
    levels: dict[str, float] = {}
    for pos, vals in by_pos.items():
        starters = _starters_at(pos, scoring_format)
        if len(vals) < starters + 1:
            levels[pos] = waiver
        else:
            vals.sort(reverse=True)
            levels[pos] = vals[starters]
    return levels


def marginal_value(
    pid: str,
    value_of,                            # callable pid → value (same space)
    repl_levels: dict[str, float],       # from replacement_levels()
    players: dict,
) -> float:
    """
    Value of a player OVER the roster's replacement at his position, plus
    a small bench credit so depth keeps some worth (byes, injuries):

        marginal(p, R) = max(0, value(p) - replacement(R, pos(p)))
                         + bench_credit_rate * value(p)

    Positions without a replacement concept (picks, unknown, anything
    outside QB/RB/WR/TE) keep their raw value.
    """
    v = value_of(pid)
    p = players.get(pid)
    pos = getattr(p, "position", None) if p else None
    if pos not in repl_levels:
        return v
    return max(0.0, v - repl_levels[pos]) + _c("bench_credit_rate") * v


# ---------------------------------------------------------------------------
# Tier 2 — work item 2.2: outlook as now/future valuation blend
# (flag: trade.outlook_blend — replaces the deleted, never-wired
#  team_outlook_multiplier post-hoc multiplier)
# ---------------------------------------------------------------------------
# DESIGN CHOICE: the per-position age curves live here as a code constant
# table rather than ~30 model_config keys. The breakpoints and slopes were
# calibrated together as a set (DynastyProcess pattern: RB cliff ~26, WR
# plateau into ~29, QB ~flat into the 30s, TE late peak) and only make
# sense moving together; exposing each number individually would explode
# the config surface for no tuning benefit. The outlook → α map IS
# config-tunable (outlook_alpha_* keys) since it's a genuine product knob.
#
# Each entry maps age → multiplier, piecewise-linear with a floor.

_AGE_NOW_CURVE = {
    # win-now weight: peak-age production favored
    "QB": lambda a: 0.95 if a < 23 else 1.0,
    "RB": lambda a: (0.95 if a < 23 else
                     1.05 if a <= 26 else
                     max(0.60, 1.05 - 0.12 * (a - 26))),
    "WR": lambda a: (0.92 if a < 23 else
                     1.0 if a <= 29 else
                     max(0.65, 1.00 - 0.10 * (a - 29))),
    "TE": lambda a: (0.90 if a < 24 else
                     1.0 if a <= 31 else
                     max(0.70, 1.00 - 0.10 * (a - 31))),
}

_AGE_FUTURE_CURVE = {
    # youth-weighted mirror: long-horizon value favored
    "QB": lambda a: 1.05 if a <= 25 else max(0.70, 1.05 - 0.05 * (a - 25)),
    "RB": lambda a: 1.10 if a <= 23 else max(0.40, 1.10 - 0.12 * (a - 23)),
    "WR": lambda a: 1.10 if a <= 24 else max(0.50, 1.10 - 0.09 * (a - 24)),
    "TE": lambda a: 1.05 if a <= 25 else max(0.55, 1.05 - 0.08 * (a - 25)),
}


def age_now_mult(pos: str | None, age) -> float:
    """Win-now age multiplier. Unknown position or missing age → 1.0."""
    if not age or age <= 0:
        return 1.0
    fn = _AGE_NOW_CURVE.get(pos)
    return fn(age) if fn else 1.0


def age_future_mult(pos: str | None, age) -> float:
    """Future-value age multiplier. Unknown position or missing age → 1.0."""
    if not age or age <= 0:
        return 1.0
    fn = _AGE_FUTURE_CURVE.get(pos)
    return fn(age) if fn else 1.0


_OUTLOOK_ALPHA_CFG_KEY = {
    "championship": "outlook_alpha_championship",
    "contender":    "outlook_alpha_contender",
    "not_sure":     "outlook_alpha_not_sure",
    "rebuilder":    "outlook_alpha_rebuilder",
    "jets":         "outlook_alpha_jets",
}


def outlook_alpha(outlook: str | None) -> float:
    """Blend weight α (1.0 = pure now-value, 0.0 = pure future-value).
    None / unknown outlooks fall back to the not_sure 50/50 blend."""
    key = _OUTLOOK_ALPHA_CFG_KEY.get(outlook or "not_sure",
                                     "outlook_alpha_not_sure")
    return _c(key)


def outlook_blend_mult(pos: str | None, age, alpha: float) -> float:
    """Combined now/future multiplier: α·now_mult + (1−α)·future_mult.
    Players with no age data get exactly 1.0 from both curves."""
    return (alpha * age_now_mult(pos, age)
            + (1.0 - alpha) * age_future_mult(pos, age))


def infer_team_outlook(
    roster_ids: list[str],
    players: dict,
    pick_share: float = 0.0,
    num_teams: int = 12,
) -> tuple[str, float, dict]:
    """Infer a team's contend↔rebuild window from observable roster shape
    (backlog #1). Pure function: no DB, no I/O — feeds the same
    `outlook_alpha` blend the user side already uses.

    Signals (all consensus-based via `dynasty_value`, so stable across users):
      • vet value share   — fraction of roster value held by players aged ≥ vet_age
      • youth value share — fraction held by players aged ≤ youth_age
      • pick capital share — this team's draft-pick value / league total, centred
                             on an equal split (1/num_teams) so an average pick
                             holder contributes 0

    Score (higher = more contending) = w_vet·vet − w_youth·youth − w_pick·(pick − equal).
    Buckets into contender / not_sure / rebuilder. The extreme labels
    (championship / jets) are deliberately NOT inferred — inference confidence
    rarely justifies α = 1.00 / 0.10; those stay reserved for self-declaration.

    Returns (outlook, score, signals).
    """
    vet_age   = _c("vet_age")
    youth_age = _c("youth_age")
    total = 0.0
    vet_val = 0.0
    youth_val = 0.0
    for pid in roster_ids:
        p = players.get(pid)
        if p is None:
            continue
        v = dynasty_value(p)
        total += v
        age = getattr(p, "age", None)
        if age is None:
            continue
        if age >= vet_age:
            vet_val += v
        elif age <= youth_age:
            youth_val += v

    signals = {"vet_share": 0.0, "youth_share": 0.0, "pick_share": pick_share}
    # No roster value to read ⇒ no opinion. Guard before the pick-centering
    # term, which would otherwise read "owns zero picks" as a contend signal.
    if total <= 0:
        signals["score"] = 0.0
        return "not_sure", 0.0, signals
    signals["vet_share"]   = vet_val / total
    signals["youth_share"] = youth_val / total

    equal_share = 1.0 / max(num_teams, 1)
    score = (
        _c("infer_w_vet_share")   * signals["vet_share"]
        - _c("infer_w_youth_share") * signals["youth_share"]
        - _c("infer_w_pick_share")  * (pick_share - equal_share)
    )
    signals["score"] = score

    if score >= _c("infer_contender_cut"):
        outlook = "contender"
    elif score <= _c("infer_rebuilder_cut"):
        outlook = "rebuilder"
    else:
        outlook = "not_sure"
    return outlook, score, signals


def build_match_context(
    user_profile: dict,
    opponent_profile: dict,
    scoring_format: str,
    is_dynasty: bool = False,
) -> dict:
    """
    Produce the structured 'why this match' object that ships on each
    TradeCard. Pure function; deterministic.
    """
    user_needs       = user_profile.get("position_needs", [])
    opp_surplus      = opponent_profile.get("position_surplus", [])
    overlap          = [p for p in user_needs if p in opp_surplus]

    if overlap:
        rationale = f"You're thin at {overlap[0]}; opponent is {overlap[0]}-heavy."
    elif user_needs:
        rationale = f"You're thin at {user_needs[0]} — see if any reach across."
    else:
        rationale = "Roster profiles align without a single standout gap."

    # Both supported formats (1qb_ppr, sf_tep) are PPR. Treat anything not
    # explicitly marked standard/std as PPR by default.
    fmt_lower = scoring_format.lower()
    is_standard = "standard" in fmt_lower or "_std" in fmt_lower or fmt_lower == "std"
    return {
        "user_needs":       user_needs,
        "opponent_surplus": opp_surplus,
        "league_settings":  {
            "scoring":     "standard" if is_standard else "ppr",
            "superflex":   fmt_lower.startswith("sf"),
            "te_premium":  "tep" in fmt_lower,
            "dynasty":     is_dynasty,
        },
        "positional_rationale": rationale,
    }


# ---------------------------------------------------------------------------
# Agent A8 — trade-math adjustments (behind feature flags)
# ---------------------------------------------------------------------------
# These functions compute multiplicative adjustments to the composite score
# and, when the human_explanations flag is on, append a plain-English reason
# to the supplied `reasons` list.  All adjustments are ADDITIVE — each flag
# that is on contributes independently and stacks multiplicatively.
#
# Signatures follow a consistent pattern:
#   (give_ids, recv_ids, *context, reasons: list[str]) -> float multiplier
# where 1.0 means "no adjustment".
#
# The caller passes the same `reasons` list to each function.  If
# human_explanations is off the caller simply drops the list at the end
# rather than paying per-function branches.
# ---------------------------------------------------------------------------

# Elite-tier ELO lower bound — matches RankingService.UNIFORM_TIER_ELO_BANDS
# elite band (1720-1790). We use the "starter" lower bound (1600) for
# "premium QB" per the QB Tax spec; any QB at or above 1600 qualifies.
_QB_PREMIUM_ELO = 1600.0


def _position_of(pid: str, player_db: dict) -> Optional[str]:
    p = player_db.get(pid)
    if not p:
        return None
    return getattr(p, "position", None)


def _seed_of(pid: str, seed_elo: dict[str, float]) -> float:
    return seed_elo.get(pid, 1500.0)


def qb_tax_adjustment(
    give_ids: list[str],
    recv_ids: list[str],
    seed_elo: dict[str, float],
    player_db: dict,
    reasons: list[str],
) -> float:
    """
    Feature: trade_math.qb_tax.

    When one side of the trade RECEIVES a premium QB (seed ELO >=
    _QB_PREMIUM_ELO) without GIVING one back, apply a penalty to that
    side — i.e. the side that is handing over a premium QB is effectively
    getting short-changed, so the composite score drops.

    The penalty symmetrically models both directions:
      * If user receives a premium QB and opponent does not → user's
        side is advantaged; we actually want to discount the composite
        because the opp would likely refuse. So the composite drops.
      * If user gives a premium QB without getting one back → user is
        disadvantaged; composite drops.
    Either direction shaves the configured rate off the composite.

    Returns a multiplier in (0, 1].
    """
    if not FLAGS.trade_math_qb_tax:
        return 1.0

    rate = _c("qb_tax_rate")

    def _premium_qbs(ids: list[str]) -> list[str]:
        out = []
        for pid in ids:
            if _position_of(pid, player_db) != "QB":
                continue
            if _seed_of(pid, seed_elo) >= _QB_PREMIUM_ELO:
                out.append(pid)
        return out

    user_recv_qbs = _premium_qbs(recv_ids)   # user receives these
    user_give_qbs = _premium_qbs(give_ids)   # user gives these

    multiplier = 1.0
    # Team 1 (user) receives a premium QB without giving one back.
    if user_recv_qbs and not user_give_qbs:
        multiplier *= (1.0 - rate)
        if FLAGS.trade_math_human_explanations:
            reasons.append(
                f"⚠️ QB tax: Team 1 receives a premium QB without giving one back (−{rate*100:.1f}%)"
            )
    # Team 2 (opponent) receives a premium QB without giving one back
    # (from user's perspective: user gives a QB without getting one).
    if user_give_qbs and not user_recv_qbs:
        multiplier *= (1.0 - rate)
        if FLAGS.trade_math_human_explanations:
            reasons.append(
                f"⚠️ QB tax: Team 2 receives a premium QB without giving one back (−{rate*100:.1f}%)"
            )
    return multiplier


def star_tax_adjustment(
    give_ids: list[str],
    recv_ids: list[str],
    seed_elo: dict[str, float],
    player_db: dict,
    scoring_format: str,
    reasons: list[str],
) -> float:
    """
    Feature: trade_math.star_tax.

    Compare the TOP asset on each side (highest seed ELO).  If they sit
    more than one tier apart, apply `star_tax_per_tier_gap` per extra
    tier step to the side RECEIVING the lower-tier package.  When the
    higher-tier star is Tier 1 (elite), multiply the penalty by
    `star_tax_elite_multiplier` — trading away an elite star is extra
    costly.

    Tiers from RankingService.tier_for_elo. Tier order (top→bottom):
      elite (0) → starter (1) → solid (2) → depth (3) → bench (4) → unranked (5)
    Gap = |give_tier_idx - recv_tier_idx|.
    """
    if not FLAGS.trade_math_star_tax:
        return 1.0

    try:
        from .ranking_service import RankingService
    except Exception:
        return 1.0

    tier_order = ("elite", "starter", "solid", "depth", "bench")

    def _top_tier_idx(ids: list[str]) -> tuple[int, Optional[str], Optional[str]]:
        """Return (tier_index, tier_name, pid) of the highest-ELO asset."""
        best_idx = 99
        best_name: Optional[str] = None
        best_pid: Optional[str] = None
        for pid in ids:
            elo = _seed_of(pid, seed_elo)
            pos = _position_of(pid, player_db)
            tier = RankingService.tier_for_elo(elo, pos, scoring_format)
            if tier is None:
                idx = len(tier_order)  # unranked sinks below bench
            else:
                idx = tier_order.index(tier)
            if idx < best_idx:
                best_idx = idx
                best_name = tier
                best_pid = pid
        return best_idx, best_name, best_pid

    give_idx, give_tier, _give_pid = _top_tier_idx(give_ids)
    recv_idx, recv_tier, _recv_pid = _top_tier_idx(recv_ids)

    gap = abs(give_idx - recv_idx)
    if gap <= 1:
        return 1.0

    per_gap  = _c("star_tax_per_tier_gap")
    elite_m  = _c("star_tax_elite_multiplier")
    extra    = gap - 1  # only count gaps BEYOND 1

    # Side receiving the lower tier (higher idx) eats the penalty.
    # Equivalently: the side trading away the higher tier is over-paying.
    # We apply the penalty to the composite (which represents user utility
    # regardless of side). Elite bump applies when the HIGHER-tier side
    # is Tier 1.
    higher_is_elite = (min(give_idx, recv_idx) == 0)
    penalty = per_gap * extra
    if higher_is_elite:
        penalty *= elite_m

    multiplier = max(0.0, 1.0 - penalty)

    if FLAGS.trade_math_human_explanations:
        if give_idx < recv_idx:
            # User trades away the better star
            side_label = "Team 1 trades away"
            tier_label = give_tier or "unranked"
        else:
            side_label = "Team 2 trades away"
            tier_label = recv_tier or "unranked"
        tier_tag = "Tier 1" if higher_is_elite else tier_label.capitalize()
        reasons.append(
            f"⭐ Star tax: {side_label} a {tier_tag} star (−{penalty*100:.1f}%)"
        )
    return multiplier


def roster_clogger_adjustment(
    give_ids: list[str],
    recv_ids: list[str],
    reasons: list[str],
) -> float:
    """
    Feature: trade_math.roster_clogger.

    Penalise asymmetric-size trades.
    * roster_spot_penalty per extra roster spot used
    * Plus an ADDITIONAL roster_clogger_penalty per player beyond 2 for
      a "clogger" trade (>= roster_clogger_threshold players one-way).
    """
    if not FLAGS.trade_math_roster_clogger:
        return 1.0

    n_give = len(give_ids)
    n_recv = len(recv_ids)
    diff   = abs(n_give - n_recv)
    if diff <= 0:
        return 1.0

    spot_rate    = _c("roster_spot_penalty")
    clogger_rate = _c("roster_clogger_penalty")
    threshold    = int(_c("roster_clogger_threshold"))

    multiplier = 1.0
    penalty_total = spot_rate * diff

    # Clogger: the bigger side has >= threshold players.
    bigger = max(n_give, n_recv)
    if bigger >= threshold:
        # Each player beyond 2 in the bigger side adds clogger_rate
        extra_players = bigger - 2
        penalty_total += clogger_rate * extra_players

    multiplier = max(0.0, 1.0 - penalty_total)

    if FLAGS.trade_math_human_explanations:
        # Label the side doing the "clogging" — the side giving up more
        # players. From user POV: n_give > n_recv means user gives more.
        if n_give > n_recv:
            side_label = "Team 1 gives up"
            count_label = f"{n_give} players for {n_recv}"
        else:
            side_label = "Team 2 gives up"
            count_label = f"{n_recv} players for {n_give}"
        if bigger >= threshold:
            reasons.append(
                f"📦 Roster clogger: {side_label} {count_label} (−{penalty_total*100:.1f}%)"
            )
        else:
            reasons.append(
                f"📦 Roster spots: {side_label} {count_label} (−{penalty_total*100:.1f}%)"
            )
    return multiplier


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class LeagueMember:
    user_id: str
    username: str
    roster: list[str]                   # list of player IDs on this user's team
    elo_ratings: dict[str, float]       # { player_id: personal_elo }
    # True only when this member has REAL saved rankings (member_rankings rows).
    # The v2 engine refuses to run divergence math against fabricated/seeded
    # elo_ratings — unranked members get consensus-basis cards instead.
    has_rankings: bool = False


@dataclass
class TradeCard:
    trade_id: str
    league_id: str
    proposing_user_id: str              # the logged-in user
    target_user_id: str                 # the other party
    target_username: str
    give_player_ids: list[str]          # what the logged-in user gives
    receive_player_ids: list[str]       # what the logged-in user receives
    mismatch_score: float               # higher = more compelling trade
    fairness_score: float               # 0–1, higher = more balanced
    composite_score: float              # final sort key
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(default_factory=lambda: (
        datetime.now(timezone.utc) + timedelta(days=7)).isoformat())
    decision: Optional[str] = None      # None | "like" | "pass"
    # Agent A8 — human-readable trade adjustment explanations.
    # Populated only when trade-math flags are on. Empty list means no
    # adjustment-level reasons for this trade. The server view converts
    # an empty list to an omitted JSON key when human_explanations is off.
    reasons: list[str] = field(default_factory=list)
    # Feature 2 — structured roster-aware match context, computed from
    # analyze_roster_strengths() / build_match_context(). None when not yet wired.
    match_context: Optional[dict] = None
    # Feature 1 — templated, deterministic plain-English narrative (≤2 sentences).
    narrative: Optional[str] = None
    # Trade engine v2 — how this card was generated:
    #   "divergence"  — built on real valuation disagreement between the two
    #                   members' personal rankings (the core product signal)
    #   "consensus"   — fallback card vs an opponent with no rankings; built
    #                   purely from consensus (seed) values + roster fit
    basis: str = "divergence"
    # Tier 2 (2.3a) — True when the counterparty already liked the mirror of
    # this trade (flag trade.likes_you). Serialized only when true.
    likes_you: bool = False
    # Tier 3 (3.4) — when a low-value player was added to balance an
    # otherwise-unfair trade: {"player_id": str, "side": "give"|"receive"}.
    # The player is already included in that side's id list. None otherwise.
    sweetener: Optional[dict] = None
    # FB-47 (flag trade.finder_targeting) — counterparty positional fit for
    # the user's stated targets, 0..1 (1 = ideal partner). None when the
    # flag is off or the user expressed no targets. Serialized when set.
    partner_fit: Optional[float] = None
    # FB-96 (flag trade.need_fit) — automatic positional-need fit, 0..1
    # (1 = gives from the user's surplus into the opponent's need AND
    # receives at the user's need from the opponent's surplus). None when
    # the flag is off or no traded asset has a positional profile.
    # Serialized when set.
    need_fit: Optional[float] = None


@dataclass
class League:
    league_id: str
    name: str
    platform: str                       # "sleeper" | "espn" | "yahoo" | "demo"
    members: list[LeagueMember]


# ---------------------------------------------------------------------------
# Trade Service
# ---------------------------------------------------------------------------

class TradeService:
    """
    Generates and manages trade cards for a user across their leagues.

    In production, league + member data comes from the League Service
    (Sleeper API etc.). For the demo, leagues are simulated.
    """

    def __init__(self, players: dict, past_decision_keys: set | None = None):
        """
        players: { player_id: Player } — full player pool
        past_decision_keys: set of (frozenset(give_ids), frozenset(receive_ids))
            from past trade decisions — used to filter out already-swiped trades.
        """
        self._players     = players
        self._trade_cards: dict[str, TradeCard] = {}    # trade_id → TradeCard
        self._leagues:     dict[str, League]    = {}    # league_id → League
        self._past_decision_keys = past_decision_keys or set()

    # ------------------------------------------------------------------
    # League management
    # ------------------------------------------------------------------

    def add_league(self, league: League):
        self._leagues[league.league_id] = league

    # ------------------------------------------------------------------
    # Trade generation
    # ------------------------------------------------------------------

    def generate_trades(
        self,
        user_id: str,
        user_elo: dict[str, float],          # { player_id: elo } — logged-in user
        user_roster: list[str],              # player IDs on user's team
        league_id: str,
        seed_elo: dict[str, float],          # consensus elo for fairness checks
        max_per_opponent: int = 5,
        fairness_threshold: float = 0.75,    # min package_value ratio (0.5–1.0)
        acquire_positions: list[str] | None = None,    # positions user wants to receive
        trade_away_positions: list[str] | None = None, # positions user wants to give
        pinned_give_players: list[str] | None = None,  # specific players user wants to trade away
        pinned_receive_players: list[str] | None = None,  # specific players user wants to acquire
                                                          # (FB-47; v2-only, legacy ignores it)
        scoring_format: str = "1qb_ppr",
        is_dynasty: bool = False,
        on_opponent_done = None,             # callback(idx_done, total, sorted_cards_so_far)
        confidence: dict[str, int] | None = None,  # pid → comparison count for the
                                                   # requesting user (v2 shrinkage; A4 ranges)
        outlook: str | None = None,          # championship | contender | not_sure |
                                             # rebuilder | jets | None — Tier 2 (2.2)
                                             # now/future blend; v2-only, legacy ignores it
        opponent_outlooks: dict[str, str] | None = None,    # uid → declared outlook (#1)
        opponent_pick_shares: dict[str, float] | None = None,  # uid → pick-capital share (#1)
        untouchable_ids: set | None = None,    # never trade these away (#2)
        target_ids: set | None = None,         # bias toward acquiring these (#2)
    ) -> list[TradeCard]:
        """
        Generate trade cards for the user against all league members
        who have established rankings.

        fairness_threshold: minimum ratio of lesser/greater KTC package value.
          0.75 (default) = packages must be within 25% of each other.
          1.00 = perfectly balanced packages only.
          0.50 = allow up to 2× imbalance.

        acquire_positions / trade_away_positions: soft multipliers applied after
          scoring — trades that match these preferences bubble up in the list.

        pinned_give_players: when set, only generate trades where the user's
          give side includes at least one of these player IDs.  This lets
          users say "I want to trade away X" and see what comes back.

        Returns new cards (not already in trade_cards).
        """
        league = self._leagues.get(league_id)
        if not league:
            raise ValueError(f"Unknown league: {league_id!r}")

        # Trade engine v2 — entirely separate scoring path so the legacy
        # branch below stays byte-for-byte identical when the flag is off.
        if FLAGS.trade_engine_v2:
            return self._generate_trades_v2(
                user_id              = user_id,
                user_elo             = user_elo,
                user_roster          = user_roster,
                league               = league,
                league_id            = league_id,
                seed_elo             = seed_elo,
                max_per_opponent     = max_per_opponent,
                fairness_threshold   = fairness_threshold,
                acquire_positions    = acquire_positions,
                trade_away_positions = trade_away_positions,
                pinned_give_players  = pinned_give_players,
                pinned_receive_players = pinned_receive_players,
                scoring_format       = scoring_format,
                is_dynasty           = is_dynasty,
                on_opponent_done     = on_opponent_done,
                confidence           = confidence,
                outlook              = outlook,
                opponent_outlooks    = opponent_outlooks,
                opponent_pick_shares = opponent_pick_shares,
                untouchable_ids      = untouchable_ids,
                target_ids           = target_ids,
            )

        new_cards: list[TradeCard] = []

        # Pre-compute the user's roster profile once.
        user_profile = analyze_roster_strengths(user_roster, self._players, scoring_format)

        # Build the list of eligible opponents up-front so the callback can
        # report a stable "X of N" without surprises when members get filtered.
        eligible = [
            m for m in league.members
            if m.user_id != user_id and m.elo_ratings
        ]
        total = len(eligible)

        # Once we've collected enough cards across all opponents, further
        # scanning rarely surfaces a card good enough to crack the top of
        # the deck. The cap has to be loose enough that productive leagues
        # don't truncate too early — we saw 7-of-10 opponents yielding 6
        # cards trip the cap when set to 15, leaving 4 opponents unsampled.
        # Bumping to 30 lets the typical 11-opponent league complete its
        # full sweep in nearly all real cases (since the per-opponent yield
        # is usually 1-2 cards) while still bounding pathological cases.
        # Cold leagues (returning 0 cards across 11 opponents) still
        # complete in one full pass — the cap never trips, but the
        # per-opponent deadline reduction is what saves them.
        global_target = max(30, max_per_opponent * 6)

        for idx, member in enumerate(eligible):
            opp_profile = analyze_roster_strengths(member.roster, self._players, scoring_format)
            match_ctx = build_match_context(user_profile, opp_profile, scoring_format, is_dynasty)

            cards = self._generate_for_pair(
                user_id              = user_id,
                user_elo             = user_elo,
                user_roster          = user_roster,
                opponent             = member,
                league_id            = league_id,
                seed_elo             = seed_elo,
                max_cards            = max_per_opponent,
                fairness_threshold   = fairness_threshold,
                acquire_positions    = acquire_positions or [],
                trade_away_positions = trade_away_positions or [],
                pinned_give_players  = pinned_give_players,
            )
            for c in cards:
                c.match_context = match_ctx
                c.narrative = build_narrative(c, match_ctx, self._players)
            new_cards.extend(cards)

            # Streaming hook — let callers (e.g. /api/trades/generate's
            # background worker) snapshot a sorted, dedup-aware view as
            # cards land. The list is sorted descending by composite_score
            # so the snapshot already represents "best so far". Errors from
            # the callback are isolated; we never let a UI bug crash the
            # generator.
            if on_opponent_done is not None:
                try:
                    snapshot = self._dedup_and_sort(new_cards)
                    on_opponent_done(idx + 1, total, snapshot)
                except Exception:
                    pass  # callback issues must not derail the loop

            # Global early exit: enough cards collected, stop scanning more
            # opponents. Always lets the LAST opponent's results land first
            # (the "snapshot" above already includes them).
            if len(new_cards) >= global_target:
                break

        # Filter out trades the user has already swiped on (within memory window)
        # and dedup, then sort by composite score
        new_cards = self._dedup_and_sort(new_cards)

        # Store
        for card in new_cards:
            self._trade_cards[card.trade_id] = card

        return new_cards

    def _dedup_and_sort(self, cards: list[TradeCard]) -> list[TradeCard]:
        """Apply past-decision filter (skip trades the user already swiped on)
        and return cards sorted by composite_score descending. Pulled out of
        the main loop so it can be called both incrementally (snapshot for
        progress callback) and at the end of generation."""
        if self._past_decision_keys:
            cards = [
                c for c in cards
                if (frozenset(c.give_player_ids), frozenset(c.receive_player_ids))
                   not in self._past_decision_keys
            ]
        return sorted(cards, key=lambda c: c.composite_score, reverse=True)

    # ------------------------------------------------------------------
    # Trade engine v2 (flag: trade_engine.v2)
    # Tier 1 plan (docs/plans/trade-engine-tier1-fixes.md) with research
    # amendments A1–A4 (docs/reviews/trade-engine-external-research.md §6):
    #   - single value space via elo_to_value()           (Change 1)
    #   - KTC-style package_value_v2 in each side's space  (Change 2 + A2)
    #   - both-sides surplus gate, harmonic-mean ranking   (Change 3 + A1)
    #   - waiver-slot cost on the side receiving more      (A3)
    #   - confidence shrinkage + range-overlap fairness    (Change 4 + A4)
    #   - bounded top-K heap, anchor-first candidate order (Change 5)
    #   - consensus-basis cards for unranked opponents
    # ------------------------------------------------------------------

    def _tier_mult_v2(self, elo_map: dict[str, float], pids) -> float:
        """Tier-priority multiplier (same bands as the legacy closure),
        computed from the supplied Elo map (v2 uses the shrunk user Elo)."""
        best = _c("tier_mult_bench")
        for pid in pids:
            e = elo_map.get(pid, 1500)
            if   e >= 1700: m = _c("tier_mult_elite")
            elif e >= 1580: m = _c("tier_mult_starter")
            elif e >= 1460: m = _c("tier_mult_solid")
            elif e >= 1350: m = _c("tier_mult_depth")
            else:           m = _c("tier_mult_bench")
            if m > best:
                best = m
        return best

    def _generate_trades_v2(
        self,
        *,
        user_id: str,
        user_elo: dict[str, float],
        user_roster: list[str],
        league: League,
        league_id: str,
        seed_elo: dict[str, float],
        max_per_opponent: int,
        fairness_threshold: float,
        acquire_positions: list[str] | None,
        trade_away_positions: list[str] | None,
        pinned_give_players: list[str] | None,
        pinned_receive_players: list[str] | None = None,
        scoring_format: str = "1qb_ppr",
        is_dynasty: bool = False,
        on_opponent_done = None,
        confidence: dict[str, int] | None = None,
        outlook: str | None = None,
        opponent_outlooks: dict[str, str] | None = None,
        opponent_pick_shares: dict[str, float] | None = None,
        untouchable_ids: set | None = None,
        target_ids: set | None = None,
    ) -> list[TradeCard]:
        """v2 orchestration: mirrors the legacy loop structure (profiles,
        narrative, streaming callback, global target, dedup) but routes each
        opponent to divergence-based or consensus-based generation."""
        new_cards: list[TradeCard] = []
        user_profile = analyze_roster_strengths(user_roster, self._players, scoring_format)

        # FB-47 finder targeting — derive position targets from explicit
        # prefs + the positions of pinned players. Player-level acquires
        # (pinned receive) restrict cards to the rosters holding those
        # players via the generators; position-level targets drive the
        # counterparty fit ranking below.
        _targeting = FLAGS.trade_finder_targeting
        # FB-96 — automatic positional-need fit (no user input required).
        _need_fit_on = FLAGS.trade_need_fit
        acquire_targets: list[str] = []
        sell_targets: list[str] = []
        if _targeting:
            acquire_targets = list(acquire_positions or [])
            sell_targets = list(trade_away_positions or [])
            for pid in (pinned_give_players or []):
                p = self._players.get(pid)
                pos = getattr(p, "position", None) if p else None
                if pos and pos not in sell_targets:
                    sell_targets.append(pos)

        # Confidence shrinkage BEFORE the value transform (Change 4).
        shrunk_elo = _shrink_user_elo(user_elo, seed_elo, confidence)
        user_value = {pid: elo_to_value(e) for pid, e in shrunk_elo.items()}

        # Tier 2 (2.2) — outlook blend applied to the USER's value map only:
        # the α blend encodes the USER's contender↔rebuilder stance; we don't
        # know the opponent's outlook here (future: read their stored league
        # preference). Because the blend is an INPUT to surplus math it
        # composes with the fairness gate, unlike the old post-hoc multiplier.
        # Flag OFF → values untouched (exactly the Tier 1 output).
        if FLAGS.trade_outlook_blend:
            alpha = outlook_alpha(outlook)
            for pid in user_value:
                p = self._players.get(pid)
                user_value[pid] *= outlook_blend_mult(
                    getattr(p, "position", None) if p else None,
                    getattr(p, "age", None) if p else None,
                    alpha,
                )

        _vs_cache: dict[str, float] = {}
        def _vs(pid: str) -> float:
            """Consensus (seed) value of a player in the v2 value space."""
            v = _vs_cache.get(pid)
            if v is None:
                v = elo_to_value(seed_elo.get(pid, 1500.0))
                _vs_cache[pid] = v
            return v

        # v2 eligibility: every other member with a roster. Members without
        # real rankings are NOT compared in divergence space (their
        # elo_ratings are fabricated noise) — they get consensus cards.
        eligible = [m for m in league.members if m.user_id != user_id and m.roster]
        # FB-47 — counterparty fit per opponent (None ⇒ targeting inactive
        # or no targets expressed). Profiles are recomputed inside the loop
        # for match_ctx; this pre-pass is cheap (rosters are small) and lets
        # the visit order put high-fit opponents first within each group.
        _fit_by_uid: dict[str, float] = {}
        if _targeting and (acquire_targets or sell_targets):
            for m in eligible:
                prof = analyze_roster_strengths(m.roster, self._players, scoring_format)
                fit = partner_fit_score(prof, acquire_targets, sell_targets)
                if fit is not None:
                    _fit_by_uid[m.user_id] = fit
        # Ranked opponents FIRST: divergence cards are the core product
        # signal and must never be crowded out of the global card budget by
        # consensus fallback cards (a league with many unranked members would
        # otherwise hit global_target before any ranked opponent is visited).
        # Within each group, best-fit first when targeting is active;
        # stable sort keeps roster order otherwise.
        eligible.sort(key=lambda m: (
            not (m.has_rankings and m.elo_ratings),
            -_fit_by_uid.get(m.user_id, 0.5),
        ))
        total = len(eligible)
        global_target = max(30, max_per_opponent * 6)

        # Backlog #1 — opponent outlook resolution. Active only when BOTH the
        # infer flag and the blend machinery are on (the blend supplies the
        # multiplier; without it the user side is unblended too and a one-sided
        # opponent blend would be inconsistent). Resolution order per opponent:
        # declared league preference → inferred from roster shape → not_sure.
        _infer_outlook = FLAGS.trade_outlook_infer and FLAGS.trade_outlook_blend
        _declared = opponent_outlooks or {}
        _pick_shares = opponent_pick_shares or {}
        _num_teams = len(league.members)

        for idx, member in enumerate(eligible):
            opp_profile = analyze_roster_strengths(member.roster, self._players, scoring_format)
            match_ctx = build_match_context(user_profile, opp_profile, scoring_format, is_dynasty)

            alpha_opp = None
            if _infer_outlook:
                declared = _declared.get(member.user_id)
                if declared:
                    resolved, source = declared, "declared"
                else:
                    resolved, _, _ = infer_team_outlook(
                        member.roster, self._players,
                        _pick_shares.get(member.user_id, 0.0), _num_teams)
                    source = "inferred"
                alpha_opp = outlook_alpha(resolved)
                match_ctx["opponent_outlook"] = {"value": resolved, "source": source}

            if member.has_rankings and member.elo_ratings:
                if FLAGS.trade_engine_v3:
                    # Tier 3 — exact top-K package construction within pruned
                    # candidate pools (trade_optimizer). Same objective as
                    # _generate_for_pair_v2; adds 2x2/2x3/3x3 shapes, lineup
                    # feasibility, and sweeteners. Lazy import: the optimizer
                    # imports this module, so a top-level import would cycle.
                    from .trade_optimizer import generate_pair_trades_v3
                    cards = generate_pair_trades_v3(
                        user_id              = user_id,
                        shrunk_user_elo      = shrunk_elo,
                        user_value           = user_value,
                        user_roster          = user_roster,
                        opponent             = member,
                        league_id            = league_id,
                        seed_elo             = seed_elo,
                        confidence           = confidence,
                        max_cards            = max_per_opponent,
                        fairness_threshold   = fairness_threshold,
                        scoring_format       = scoring_format,
                        acquire_positions    = acquire_positions or [],
                        trade_away_positions = trade_away_positions or [],
                        pinned_give_players  = pinned_give_players,
                        pinned_receive_players = pinned_receive_players,
                        players              = self._players,
                        alpha_opp            = alpha_opp,
                        untouchable_ids      = untouchable_ids,
                        target_ids           = target_ids,
                    )
                else:
                    cards = self._generate_for_pair_v2(
                        user_id              = user_id,
                        shrunk_user_elo      = shrunk_elo,
                        user_value           = user_value,
                        user_roster          = user_roster,
                        opponent             = member,
                        league_id            = league_id,
                        seed_value           = _vs,
                        max_cards            = max_per_opponent,
                        fairness_threshold   = fairness_threshold,
                        acquire_positions    = acquire_positions or [],
                        trade_away_positions = trade_away_positions or [],
                        pinned_give_players  = pinned_give_players,
                        pinned_receive_players = pinned_receive_players,
                        confidence           = confidence,
                        scoring_format       = scoring_format,
                        alpha_opp            = alpha_opp,
                        untouchable_ids      = untouchable_ids,
                        target_ids           = target_ids,
                    )
            else:
                cards = self._generate_consensus_for_pair(
                    user_id              = user_id,
                    opponent             = member,
                    league_id            = league_id,
                    seed_value           = _vs,
                    shrunk_user_elo      = shrunk_elo,
                    user_roster          = user_roster,
                    max_cards            = max_per_opponent,
                    fairness_threshold   = fairness_threshold,
                    user_profile         = user_profile,
                    opp_profile          = opp_profile,
                    acquire_positions    = acquire_positions or [],
                    trade_away_positions = trade_away_positions or [],
                    pinned_give_players  = pinned_give_players,
                    pinned_receive_players = pinned_receive_players,
                    untouchable_ids      = untouchable_ids,
                    target_ids           = target_ids,
                )
            # FB-47 — stamp partner fit and blend it into the composite:
            # strongly on consensus cards (no divergence signal there),
            # tiebreak-strength on divergence cards. Flag off / no targets
            # ⇒ _fit_by_uid is empty and this is a no-op.
            _fit = _fit_by_uid.get(member.user_id)
            if _fit is not None:
                for c in cards:
                    c.partner_fit = _fit
                    w = (_c("fit_consensus_weight") if c.basis == "consensus"
                         else _c("fit_divergence_weight"))
                    c.composite_score = round(
                        c.composite_score * (1.0 + w * (_fit - 0.5)), 3)
            # FB-96 — per-card positional-need fit: boost swaps that give
            # from the user's surplus into the opponent's need and receive
            # at the user's need from the opponent's surplus. Bounded
            # composite multiplier applied AFTER all gates (fairness /
            # mutual gain are already settled) — it reorders acceptable
            # trades, never rescues gated ones. Flag off ⇒ no-op.
            if _need_fit_on:
                w_nf = _c("need_fit_weight")
                for c in cards:
                    nf = need_fit_score(
                        user_profile, opp_profile,
                        c.give_player_ids, c.receive_player_ids,
                        self._players, scoring_format)
                    if nf is not None:
                        c.need_fit = nf
                        c.composite_score = round(
                            c.composite_score * (1.0 + w_nf * (nf - 0.5)), 3)
            for c in cards:
                c.match_context = match_ctx
                c.narrative = build_narrative(c, match_ctx, self._players)
            new_cards.extend(cards)

            if on_opponent_done is not None:
                try:
                    snapshot = self._dedup_and_sort(new_cards)
                    on_opponent_done(idx + 1, total, snapshot)
                except Exception:
                    pass  # callback issues must not derail the loop

            if len(new_cards) >= global_target:
                break

        new_cards = self._dedup_and_sort(new_cards)
        for card in new_cards:
            self._trade_cards[card.trade_id] = card
        return new_cards

    def _generate_for_pair_v2(
        self,
        *,
        user_id: str,
        shrunk_user_elo: dict[str, float],
        user_value: dict[str, float],
        user_roster: list[str],
        opponent: LeagueMember,
        league_id: str,
        seed_value,                          # callable pid → consensus value
        max_cards: int,
        fairness_threshold: float,
        acquire_positions: list[str],
        trade_away_positions: list[str],
        pinned_give_players: list[str] | None,
        pinned_receive_players: list[str] | None = None,
        confidence: dict[str, int] | None = None,
        scoring_format: str = "1qb_ppr",
        alpha_opp: float | None = None,
        untouchable_ids: set | None = None,
        target_ids: set | None = None,
    ) -> list[TradeCard]:
        """Divergence-based v2 generation for one (user, opponent) pair.

        All math happens in value units (elo_to_value). Packages are valued
        KTC-style per side (package_value_v2 with the trade-wide best asset
        in that side's own value space as the reference). A trade surfaces
        only when BOTH sides clear min_side_surplus; candidates are ranked
        by the harmonic mean of the two surpluses, blended with consensus
        fairness and the existing tier multiplier, kept in a bounded
        min-heap (true top-K instead of first-K).
        """
        opp_elo    = opponent.elo_ratings
        players    = self._players
        pinned_set = set(pinned_give_players) if pinned_give_players else None
        # FB-47 — pinned ACQUIRE targets: cards must receive at least one.
        pinned_recv_set = (set(pinned_receive_players)
                           if pinned_receive_players else None)

        _deadline    = time.monotonic() + 1.0
        _iter_budget = 200_000
        _iters       = 0

        # Tier 2 (2.1) — when the marginal flag is on, surpluses are computed
        # on over-replacement values, which run much smaller than raw values,
        # so the per-side gate switches to min_side_surplus_marginal (see the
        # _DEFAULT_CFG comment for the rationale).
        MARGINAL = FLAGS.trade_marginal_value
        MIN_SIDE = (_c("min_side_surplus_marginal") if MARGINAL
                    else _c("min_side_surplus"))
        GAIN_CAP = max(_c("mutual_gain_cap"), 1.0)
        WAIVER   = _c("waiver_slot_cost")
        MAX_GAP  = _c("trade_elo_gap_max")
        W_MIS    = _c("mismatch_weight")
        W_FAIR   = _c("fairness_weight")
        TARGET_BONUS = _c("target_acquire_bonus")   # #2 per-target composite reward
        MULT_CAP     = _c("pos_multiplier_cap")

        _vo_cache: dict[str, float] = {}
        def _vo(pid: str) -> float:
            v = _vo_cache.get(pid)
            if v is None:
                v = elo_to_value(opp_elo.get(pid, 1500.0))
                # Backlog #1 — opponent outlook blend (mirrors the user-side
                # blend on user_value). alpha_opp None ⇒ flag off ⇒ raw value
                # (byte-identical to pre-change). Blending here propagates to
                # _mo / opp_repl too, since both read through _vo.
                if alpha_opp is not None:
                    p = players.get(pid)
                    v *= outlook_blend_mult(
                        getattr(p, "position", None) if p else None,
                        getattr(p, "age", None) if p else None,
                        alpha_opp,
                    )
                _vo_cache[pid] = v
            return v

        if MARGINAL:
            # Replacement levels computed ONCE per pair from the PRE-trade
            # rosters, in each side's own value space — the two (roster,
            # value-map) combos the surplus formulas need: the acquiring
            # side values an incoming player at his marginal over THEIR
            # roster, and the shedding side's loss is his marginal on their
            # own roster. (Exact post-trade re-optimization is Tier 3.)
            _def_uval = elo_to_value(1500.0)
            def _uv(pid: str) -> float:
                return user_value.get(pid, _def_uval)
            user_repl = replacement_levels(
                user_roster, _uv, players, scoring_format)
            opp_repl = replacement_levels(
                opponent.roster, _vo, players, scoring_format)

            _mu_cache: dict[str, float] = {}
            def _mu(pid: str) -> float:
                """Marginal value of pid on the USER's roster, user's space."""
                v = _mu_cache.get(pid)
                if v is None:
                    v = marginal_value(pid, _uv, user_repl, players)
                    _mu_cache[pid] = v
                return v

            _mo_cache: dict[str, float] = {}
            def _mo(pid: str) -> float:
                """Marginal value of pid on the OPPONENT's roster, opp space."""
                v = _mo_cache.get(pid)
                if v is None:
                    v = marginal_value(pid, _vo, opp_repl, players)
                    _mo_cache[pid] = v
                return v

        def _gap_ok(give_ids: list[str], recv_ids: list[str]) -> bool:
            """Same guard as legacy _elo_gap_ok, on the shrunk user Elo."""
            if MAX_GAP <= 0:
                return True
            max_give = max(shrunk_user_elo.get(p, 1500) for p in give_ids)
            max_recv = max(shrunk_user_elo.get(p, 1500) for p in recv_ids)
            return abs(max_recv - max_give) <= MAX_GAP

        _acq  = acquire_positions
        _away = trade_away_positions
        def _positions_ok(give_ids: list[str], recv_ids: list[str]) -> bool:
            """Positional preference hard filter (same semantics as legacy)."""
            if _acq:
                recv_pos = [players[p].position for p in recv_ids
                            if p in players and getattr(players[p], "position", None)]
                if not any(p in _acq for p in recv_pos):
                    return False
            if _away:
                give_pos = [players[p].position for p in give_ids
                            if p in players and getattr(players[p], "position", None)]
                if not any(p in _away for p in give_pos):
                    return False
            return True

        def _fairness(give_ids: list[str], recv_ids: list[str]) -> float | None:
            """
            Consensus fairness with range overlap (amendment A4).

            fairness = lesser/greater point ratio of consensus package
            values (value space, NOT summed seed Elo). The GATE passes when
            the two sides' value intervals [v·(1−unc), v·(1+unc)] overlap —
            unc per package is the value-weighted mean of member
            uncertainties — OR the point ratio clears fairness_threshold.
            Returns the fairness score, or None when gated out.
            """
            gvals = [seed_value(p) for p in give_ids]
            rvals = [seed_value(p) for p in recv_ids]
            v_max = max(gvals + rvals)
            gv = package_value_v2(gvals, v_max, n_other=len(recv_ids))
            rv = package_value_v2(rvals, v_max, n_other=len(give_ids))
            if gv <= 0 or rv <= 0:
                return 1.0
            fairness = min(gv, rv) / max(gv, rv)
            g_unc = (sum(v * _value_uncertainty(p, confidence)
                         for v, p in zip(gvals, give_ids)) / sum(gvals))
            r_unc = (sum(v * _value_uncertainty(p, confidence)
                         for v, p in zip(rvals, recv_ids)) / sum(rvals))
            overlap = (gv * (1 + g_unc) >= rv * (1 - r_unc)
                       and rv * (1 + r_unc) >= gv * (1 - g_unc))
            if not overlap and fairness < fairness_threshold:
                return None
            return round(fairness, 3)

        # Bounded top-K heap (Change 5). K gives max_cards headroom so the
        # final cut is a true top-N regardless of enumeration order.
        K = max(int(max_cards) * 4, 1)
        heap: list[tuple] = []
        _tb = 0
        def _offer(composite, hm, fairness, give_ids, recv_ids):
            nonlocal _tb
            _tb += 1
            entry = (composite, _tb, hm, fairness, give_ids, recv_ids)
            if len(heap) < K:
                heapq.heappush(heap, entry)
            elif composite > heap[0][0]:
                heapq.heapreplace(heap, entry)

        def _consider(give_ids: list[str], recv_ids: list[str]) -> None:
            if pinned_set and not (set(give_ids) & pinned_set):
                return
            if pinned_recv_set and not (set(recv_ids) & pinned_recv_set):
                return
            if not _positions_ok(give_ids, recv_ids):
                return
            if not _gap_ok(give_ids, recv_ids):
                return

            # Package values in EACH side's own value space (Change 2).
            # Tier 2 (2.1): with the marginal flag on, each side's packages
            # are built from over-replacement values against THAT side's own
            # pre-trade roster — clogger packages collapse, need-fillers
            # keep their value. Same package_value_v2 + waiver math after.
            if MARGINAL:
                uvals_give = [_mu(p) for p in give_ids]
                uvals_recv = [_mu(p) for p in recv_ids]
            else:
                uvals_give = [user_value[p] for p in give_ids]
                uvals_recv = [user_value[p] for p in recv_ids]
            u_max = max(uvals_give + uvals_recv)
            give_val_user = package_value_v2(uvals_give, u_max, n_other=len(recv_ids))
            recv_val_user = package_value_v2(uvals_recv, u_max, n_other=len(give_ids))

            if MARGINAL:
                ovals_give = [_mo(p) for p in give_ids]
                ovals_recv = [_mo(p) for p in recv_ids]
            else:
                ovals_give = [_vo(p) for p in give_ids]
                ovals_recv = [_vo(p) for p in recv_ids]
            o_max = max(ovals_give + ovals_recv)
            give_val_opp = package_value_v2(ovals_give, o_max, n_other=len(recv_ids))  # opp receives
            recv_val_opp = package_value_v2(ovals_recv, o_max, n_other=len(give_ids))  # opp gives

            # Waiver-slot cost (A3): the side receiving MORE players drops a
            # waiver-level player per extra slot — subtract from that side's
            # received package value. Replaces the clogger tax in v2.
            extra = len(recv_ids) - len(give_ids)
            if extra > 0:        # user receives more players
                recv_val_user -= WAIVER * extra
            elif extra < 0:      # opponent receives more players
                give_val_opp -= WAIVER * (-extra)

            user_surplus = recv_val_user - give_val_user
            opp_surplus  = give_val_opp - recv_val_opp
            # True mutual gain (Change 3): BOTH sides must clear the bar.
            if user_surplus < MIN_SIDE or opp_surplus < MIN_SIDE:
                return

            fairness = _fairness(give_ids, recv_ids)
            if fairness is None:
                return

            hm = _harmonic_mean(user_surplus, opp_surplus)   # A1 ranking
            composite = (W_MIS * min(hm, GAIN_CAP) / GAIN_CAP
                         + W_FAIR * fairness)
            composite *= self._tier_mult_v2(shrunk_user_elo, give_ids + recv_ids)
            # Backlog #2 — reward cards that LAND a target on the receive side.
            # Applied after the mutual-gain gates (a target never rescues a
            # non-mutual-gain trade), capped by pos_multiplier_cap.
            if target_ids:
                n_t = len(set(recv_ids) & target_ids)
                if n_t:
                    composite *= min(1.0 + TARGET_BONUS * n_t, MULT_CAP)
            _offer(composite, hm, fairness, give_ids, recv_ids)

        # ------------------------------------------------------------------
        # Candidate pools — same prune idea as legacy but in value space and
        # direction-correct: gives the opponent over-values, receives the
        # user over-values. Anchor-first pre-sort (Change 5) visits the
        # highest-divergence players first so the deadline loses little.
        # ------------------------------------------------------------------
        # Backlog #2 — untouchables never leave the user's roster: drop them
        # from the give pool at the source, so they can't appear in any single
        # or multi-give combo.
        _known_user = [p for p in user_roster
                       if p in shrunk_user_elo and p in opp_elo
                       and not (untouchable_ids and p in untouchable_ids)]
        _known_opp  = [p for p in opponent.roster if p in shrunk_user_elo and p in opp_elo]
        _PRUNE_MIN_SIZE = 5
        _give = [p for p in _known_user if _vo(p) >= user_value[p] * 0.97]
        _recv = [p for p in _known_opp if user_value[p] >= _vo(p) * 0.97]
        give_candidates = _give if len(_give) >= _PRUNE_MIN_SIZE else list(_known_user)
        recv_candidates = _recv if len(_recv) >= _PRUNE_MIN_SIZE else list(_known_opp)
        # FB-47 — pinned acquire targets must survive the divergence prune,
        # mirroring how pinned give players are always kept in the optimizer.
        if pinned_recv_set:
            for pid in _known_opp:
                if pid in pinned_recv_set and pid not in recv_candidates:
                    recv_candidates.append(pid)
        # Backlog #2 — targets the opponent rosters survive the prune too, so a
        # coveted player is always offered when this opponent holds him.
        if target_ids:
            for pid in _known_opp:
                if pid in target_ids and pid not in recv_candidates:
                    recv_candidates.append(pid)
        give_candidates.sort(key=lambda p: _vo(p) - user_value[p], reverse=True)
        recv_candidates.sort(key=lambda p: user_value[p] - _vo(p), reverse=True)

        # 1-for-1
        for give_id in give_candidates:
            if time.monotonic() > _deadline:
                break
            for recv_id in recv_candidates:
                _iters += 1
                _consider([give_id], [recv_id])

        # 2-for-1 (user gives 2, receives 1)
        _budget_exceeded = _iters > _iter_budget
        if not _budget_exceeded:
            for recv_id in recv_candidates:
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                for g1, g2 in combinations(give_candidates, 2):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    _consider([g1, g2], [recv_id])

        # 1-for-2 (user gives 1, receives 2)
        if not _budget_exceeded:
            for give_id in give_candidates:
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                for r1, r2 in combinations(recv_candidates, 2):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    _consider([give_id], [r1, r2])

        # 3-for-2 (user gives 3, receives 2)
        if not _budget_exceeded:
            for r1, r2 in combinations(recv_candidates, 2):
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                for g1, g2, g3 in combinations(give_candidates, 3):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    _consider([g1, g2, g3], [r1, r2])

        # NOTE: no qb_tax / star_tax / roster_clogger in the v2 path — the
        # clogger phenomenon is handled by package_value_v2 diminishing
        # returns + the waiver-slot cost; QB/star reconciliation is Tier 2.
        ranked = sorted(heap, key=lambda e: (e[0], e[1]), reverse=True)
        cards: list[TradeCard] = []
        for composite, _t, hm, fairness, give_ids, recv_ids in ranked[:max_cards]:
            cards.append(TradeCard(
                trade_id          = str(uuid.uuid4())[:8],
                league_id         = league_id,
                proposing_user_id = user_id,
                target_user_id    = opponent.user_id,
                target_username   = opponent.username,
                give_player_ids   = give_ids,
                receive_player_ids= recv_ids,
                mismatch_score    = round(hm, 1),
                fairness_score    = round(fairness, 3),
                composite_score   = round(composite, 3),
                basis             = "divergence",
            ))
        return cards

    def _generate_consensus_for_pair(
        self,
        *,
        user_id: str,
        opponent: LeagueMember,
        league_id: str,
        seed_value,                          # callable pid → consensus value
        shrunk_user_elo: dict[str, float],
        user_roster: list[str],
        max_cards: int,
        fairness_threshold: float,
        user_profile: dict,
        opp_profile: dict,
        acquire_positions: list[str],
        trade_away_positions: list[str],
        pinned_give_players: list[str] | None,
        pinned_receive_players: list[str] | None = None,
        untouchable_ids: set | None = None,
        target_ids: set | None = None,
    ) -> list[TradeCard]:
        """Consensus-basis fallback cards for an opponent with NO rankings.

        Divergence math against fabricated elo_ratings is meaningless noise,
        so instead surface simple, fair-by-consensus 1-for-1 / 2-for-1 ideas
        oriented around roster fit: the user receives a needed position and
        gives from positions the opponent needs where possible. Scored by
        fairness × tier multiplier only (no divergence term) and labeled
        basis="consensus". A deliberately simple, labeled fallback.
        """
        players    = self._players
        pinned_set = set(pinned_give_players) if pinned_give_players else None

        def _pos(pid: str) -> Optional[str]:
            p = players.get(pid)
            return getattr(p, "position", None) if p else None

        # Explicit user preferences win; otherwise fall back to the roster
        # profiles already computed by generate_trades.
        need_positions = list(acquire_positions) or list(user_profile.get("position_needs", []))
        shed_positions = list(trade_away_positions) or list(opp_profile.get("position_needs", []))

        recv_pool = list(opponent.roster)
        # FB-47 — player-level acquire targets dominate: restrict the receive
        # pool to the pinned players this opponent actually rosters. (When
        # they roster none, no cards — correct: the pin names specific
        # players, not a position.)
        pinned_recv_set = (set(pinned_receive_players)
                           if pinned_receive_players else None)
        if pinned_recv_set:
            recv_pool = [p for p in recv_pool if p in pinned_recv_set]
        elif need_positions:
            recv_pool = [p for p in recv_pool if _pos(p) in need_positions]
        # Backlog #2 — targets the opponent rosters survive the need-position
        # filter, so a coveted player is offered even off-need.
        if target_ids:
            for pid in opponent.roster:
                if pid in target_ids and pid not in recv_pool:
                    recv_pool.append(pid)
        recv_pool.sort(key=seed_value, reverse=True)

        give_pool = list(user_roster)
        # Backlog #2 — untouchables are never given away, consensus path too.
        if untouchable_ids:
            give_pool = [p for p in give_pool if p not in untouchable_ids]
        if pinned_set:
            give_pool = [p for p in give_pool if p in pinned_set]
        # "Where possible": positions the opponent needs first, best value first.
        give_pool.sort(key=lambda p: (_pos(p) in shed_positions, seed_value(p)),
                       reverse=True)

        cards: list[TradeCard] = []
        seen: set[tuple] = set()

        def _emit(give_ids: list[str], recv_ids: list[str]) -> None:
            key = (frozenset(give_ids), frozenset(recv_ids))
            if key in seen:
                return
            gvals = [seed_value(p) for p in give_ids]
            rvals = [seed_value(p) for p in recv_ids]
            v_max = max(gvals + rvals)
            gv = package_value_v2(gvals, v_max, n_other=len(recv_ids))
            rv = package_value_v2(rvals, v_max, n_other=len(give_ids))
            if gv <= 0 or rv <= 0:
                return
            fairness = min(gv, rv) / max(gv, rv)
            if fairness < fairness_threshold:
                return
            seen.add(key)
            # consensus_score_scale keeps fallback cards (no divergence
            # signal, mismatch 0) from outranking genuine divergence finds —
            # the two composites would otherwise live on different scales
            # (fairness×tier ≈ 1.6 vs surplus-blend ≈ 0.3–0.7).
            composite = (fairness * self._tier_mult_v2(shrunk_user_elo, give_ids + recv_ids)
                         * _c("consensus_score_scale"))
            cards.append(TradeCard(
                trade_id          = str(uuid.uuid4())[:8],
                league_id         = league_id,
                proposing_user_id = user_id,
                target_user_id    = opponent.user_id,
                target_username   = opponent.username,
                give_player_ids   = give_ids,
                receive_player_ids= recv_ids,
                mismatch_score    = 0.0,     # no divergence signal by construction
                fairness_score    = round(fairness, 3),
                composite_score   = round(composite, 3),
                basis             = "consensus",
            ))

        # 1-for-1 first (most acceptable shape), then 2-for-1.
        for recv_id in recv_pool:
            if len(cards) >= max_cards:
                break
            for give_id in give_pool:
                if len(cards) >= max_cards:
                    break
                _emit([give_id], [recv_id])
        if len(cards) < max_cards:
            for recv_id in recv_pool:
                if len(cards) >= max_cards:
                    break
                for g1, g2 in combinations(give_pool, 2):
                    if len(cards) >= max_cards:
                        break
                    _emit([g1, g2], [recv_id])
        return cards

    def get_pending_trades(self, user_id: str, league_id: Optional[str] = None) -> list[TradeCard]:
        """Return undecided trade cards for a user, newest first."""
        cards = [
            c for c in self._trade_cards.values()
            if c.proposing_user_id == user_id
            and c.decision is None
            and (league_id is None or c.league_id == league_id)
            and (frozenset(c.give_player_ids), frozenset(c.receive_player_ids))
                not in self._past_decision_keys
        ]
        return sorted(cards, key=lambda c: c.composite_score, reverse=True)

    def record_decision(self, trade_id: str, decision: str) -> TradeCard:
        """Record 'like' or 'pass' on a trade card."""
        if trade_id not in self._trade_cards:
            raise ValueError(f"Unknown trade_id: {trade_id!r}")
        if decision not in ("like", "pass"):
            raise ValueError("decision must be 'like' or 'pass'")
        self._trade_cards[trade_id].decision = decision
        return self._trade_cards[trade_id]

    def get_liked_trades(self, user_id: str) -> list[TradeCard]:
        return [
            c for c in self._trade_cards.values()
            if c.proposing_user_id == user_id and c.decision == "like"
        ]

    # ------------------------------------------------------------------
    # Core algorithm
    # ------------------------------------------------------------------

    def _generate_for_pair(
        self,
        user_id: str,
        user_elo: dict[str, float],
        user_roster: list[str],
        opponent: LeagueMember,
        league_id: str,
        seed_elo: dict[str, float],
        max_cards: int,
        fairness_threshold: float = 0.75,
        acquire_positions: list[str] | None = None,
        trade_away_positions: list[str] | None = None,
        pinned_give_players: list[str] | None = None,
        prune_candidates: bool = True,
    ) -> list[TradeCard]:

        opp_elo    = opponent.elo_ratings
        opp_roster = opponent.roster
        players    = self._players
        pinned_set = set(pinned_give_players) if pinned_give_players else None

        # Time budget: bail out of expensive combination loops after 1s
        # per opponent. Was 3s; combined with max_candidates=30 (was 500),
        # opponents that won't yield candidates exit much faster. 11
        # opponents × 1s worst case ≈ 11s total wall clock, vs the 33s
        # we were burning before — pre-gen now actually beats the user
        # to the Trades page in the common cold-cache flow.
        _deadline  = time.monotonic() + 1.0
        _iter_budget = 200_000  # max iterations across multi-player sections
        _iters     = 0

        # ------------------------------------------------------------------
        # Helpers
        # ------------------------------------------------------------------

        # Memoize per-pair _dv lookups. Without this, dynasty_value(p) is
        # recomputed for every (give, recv) combination — same player IDs
        # appear in tens of thousands of combinations per opponent. The
        # cache is local to each opponent so it doesn't outlive the call.
        _dv_cache: dict[str, float] = {}
        _ktc_fallback_dv = dynasty_value(None, rank_override=int(_c("ktc_fallback_rank")))

        def _dv(pid: str) -> float:
            """Dynasty value for a player by ID (KTC-style)."""
            v = _dv_cache.get(pid)
            if v is not None:
                return v
            p = players.get(pid)
            v = _ktc_fallback_dv if p is None else dynasty_value(p)
            _dv_cache[pid] = v
            return v

        # Tier-priority multiplier. Applied to composite_score so trades
        # involving higher-tier players (Elite, Starter) outrank trades
        # composed of Depth/Bench scraps — even when the depth-vs-depth
        # mismatch math is "better" on paper. Tiers are derived from the
        # USER's personal ELO (so it reflects how the user values the
        # players, not the consensus). Thresholds mirror the uniform
        # tier bands in backend/ranking_service.py:bucket_for. Picks the
        # MAX tier across both sides — if a trade involves any one
        # Elite-tier player, the whole trade gets the Elite multiplier.
        _MULT_ELITE   = _c("tier_mult_elite")
        _MULT_STARTER = _c("tier_mult_starter")
        _MULT_SOLID   = _c("tier_mult_solid")
        _MULT_DEPTH   = _c("tier_mult_depth")
        _MULT_BENCH   = _c("tier_mult_bench")
        def _tier_mult_for_pids(pids):
            best = _MULT_BENCH
            for pid in pids:
                e = user_elo.get(pid, 1500)
                if   e >= 1700: m = _MULT_ELITE
                elif e >= 1580: m = _MULT_STARTER
                elif e >= 1460: m = _MULT_SOLID
                elif e >= 1350: m = _MULT_DEPTH
                else:           m = _MULT_BENCH
                if m > best: best = m
            return best

        def _ktc_ok(give_ids: list[str], recv_ids: list[str]) -> bool:
            """
            Return True if the KTC package values satisfy fairness_threshold.
            i.e. lesser_package / greater_package >= fairness_threshold
            """
            give_val = package_value([_dv(pid) for pid in give_ids])
            recv_val = package_value([_dv(pid) for pid in recv_ids])
            if give_val == 0 and recv_val == 0:
                return True
            greater = max(give_val, recv_val)
            lesser  = min(give_val, recv_val)
            return (lesser / greater) >= fairness_threshold

        def _elo_gap_ok(give_ids: list[str], recv_ids: list[str]) -> bool:
            """
            Return True if the user's personal ELO gap between the best player
            on each side is within the configured max.  Catches ridiculous trades
            where consensus values are similar but the user's rankings diverge
            (e.g. Charbonnet 1289 for Jeanty 1665).
            """
            max_gap = _c("trade_elo_gap_max")
            if max_gap <= 0:
                return True  # disabled
            give_elos = [user_elo.get(pid, 1500) for pid in give_ids]
            recv_elos = [user_elo.get(pid, 1500) for pid in recv_ids]
            max_give = max(give_elos) if give_elos else 1500
            max_recv = max(recv_elos) if recv_elos else 1500
            return abs(max_recv - max_give) <= max_gap

        # (composite, mismatch, fairness, give_ids, recv_ids)
        candidates: list[tuple[float, float, float, list[str], list[str]]] = []

        # ------------------------------------------------------------------
        # Pre-prune: restrict iteration space to players whose ELO divergence
        # creates a give-side surplus for the opponent (give_candidates) or a
        # receive-side surplus for the user (recv_candidates).  This mirrors
        # the condition _mismatch_score must see > 0.
        #
        # Threshold 0.97 (slightly below 1.0) ensures equal-ELO boundary
        # players are INCLUDED rather than dropped (AC-4).
        #
        # Fallback: if either pruned set is too small (< 5 players) we use the
        # full roster for that side so new users with all-ELO-at-1500 still get
        # trade cards (AC-5).
        # ------------------------------------------------------------------
        _PRUNE_THRESHOLD = 0.97
        _PRUNE_MIN_SIZE  = 5

        if prune_candidates:
            _give_cands = [
                pid for pid in user_roster
                if pid in user_elo and pid in opp_elo
                and opp_elo[pid] >= user_elo[pid] * _PRUNE_THRESHOLD
            ]
            _recv_cands = [
                pid for pid in opp_roster
                if pid in user_elo and pid in opp_elo
                and opp_elo[pid] >= user_elo[pid] * _PRUNE_THRESHOLD
            ]
            # Fallback: if the pruned set is too thin (e.g. all-1500 new user)
            # use the full roster so we still surface trade cards.
            give_candidates = (
                _give_cands if len(_give_cands) >= _PRUNE_MIN_SIZE else user_roster
            )
            recv_candidates = (
                _recv_cands if len(_recv_cands) >= _PRUNE_MIN_SIZE else opp_roster
            )
        else:
            give_candidates = user_roster
            recv_candidates = opp_roster

        # ------------------------------------------------------------------
        # 1-for-1 trades
        # ------------------------------------------------------------------
        for give_id in give_candidates:
            if give_id not in user_elo or give_id not in opp_elo:
                continue
            # When pinned players specified, only consider those as give candidates
            if pinned_set and give_id not in pinned_set:
                continue
            for recv_id in recv_candidates:
                if recv_id not in user_elo or recv_id not in opp_elo:
                    continue

                # KTC fairness gate (replaces old MAX_VALUE_RATIO check)
                if not _ktc_ok([give_id], [recv_id]):
                    continue
                # User-ELO gap gate — catches ridiculous trades where consensus
                # is similar but user's personal rankings strongly diverge
                if not _elo_gap_ok([give_id], [recv_id]):
                    continue

                mismatch = self._mismatch_score(give_id, recv_id, user_elo, opp_elo)
                if mismatch <= 0:
                    continue

                fairness = self._fairness_score([give_id], [recv_id], seed_elo)
                composite = (_c("mismatch_weight") * min(mismatch, 300) / 300 +
                             _c("fairness_weight") * fairness)
                composite *= _tier_mult_for_pids([give_id, recv_id])
                candidates.append((composite, mismatch, fairness, [give_id], [recv_id]))

                if len(candidates) >= int(_c("max_candidates")):
                    break
            if len(candidates) >= int(_c("max_candidates")):
                break

        # ------------------------------------------------------------------
        # 2-for-1 trades (user gives 2, receives 1 elite player)
        # ------------------------------------------------------------------
        _budget_exceeded = False
        if len(candidates) < int(_c("max_candidates")):
            for recv_id in recv_candidates:
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                if recv_id not in user_elo or recv_id not in opp_elo:
                    continue
                recv_dv = _dv(recv_id)

                for give_id_1, give_id_2 in combinations(give_candidates, 2):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    if give_id_1 not in user_elo or give_id_2 not in user_elo:
                        continue
                    # At least one of the give players must be pinned
                    if pinned_set and not ({give_id_1, give_id_2} & pinned_set):
                        continue

                    # Quick KTC pre-filter before expensive ELO math
                    if not _ktc_ok([give_id_1, give_id_2], [recv_id]):
                        continue
                    if not _elo_gap_ok([give_id_1, give_id_2], [recv_id]):
                        continue

                    combined_give_user = user_elo.get(give_id_1, 1500) + user_elo.get(give_id_2, 1500)
                    combined_give_opp  = opp_elo.get(give_id_1, 1500) + opp_elo.get(give_id_2, 1500)
                    recv_user = user_elo.get(recv_id, 1500)
                    recv_opp  = opp_elo.get(recv_id, 1500)

                    # User values the single player more than the combined pair
                    if recv_user <= combined_give_user * 0.95:
                        continue
                    # Opponent values the pair more than the single player
                    if combined_give_opp <= recv_opp * 0.95:
                        continue

                    mismatch = (recv_user - combined_give_user) + (combined_give_opp - recv_opp)
                    if mismatch <= 0:
                        continue

                    fairness = self._fairness_score([give_id_1, give_id_2], [recv_id], seed_elo)
                    composite = (_c("mismatch_weight") * min(mismatch, 400) / 400 +
                                 _c("fairness_weight") * fairness)
                    composite *= _tier_mult_for_pids([give_id_1, give_id_2, recv_id])
                    candidates.append((composite, mismatch, fairness, [give_id_1, give_id_2], [recv_id]))

                    if len(candidates) >= int(_c("max_candidates")):
                        break
                if len(candidates) >= int(_c("max_candidates")):
                    break

        # ------------------------------------------------------------------
        # 1-for-2 trades (user gives 1 elite, receives 2)
        # ------------------------------------------------------------------
        if len(candidates) < int(_c("max_candidates")) and not _budget_exceeded:
            for give_id in give_candidates:
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                if give_id not in user_elo or give_id not in opp_elo:
                    continue
                if pinned_set and give_id not in pinned_set:
                    continue

                for recv_id_1, recv_id_2 in combinations(recv_candidates, 2):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    if recv_id_1 not in user_elo or recv_id_2 not in user_elo:
                        continue

                    # Quick KTC pre-filter
                    if not _ktc_ok([give_id], [recv_id_1, recv_id_2]):
                        continue
                    if not _elo_gap_ok([give_id], [recv_id_1, recv_id_2]):
                        continue

                    give_user = user_elo.get(give_id, 1500)
                    give_opp  = opp_elo.get(give_id, 1500)
                    combined_recv_user = user_elo.get(recv_id_1, 1500) + user_elo.get(recv_id_2, 1500)
                    combined_recv_opp  = opp_elo.get(recv_id_1, 1500) + opp_elo.get(recv_id_2, 1500)

                    # User values the pair more than the single player they give
                    if combined_recv_user <= give_user * 0.95:
                        continue
                    # Opponent values the single player more than the pair
                    if give_opp <= combined_recv_opp * 0.95:
                        continue

                    mismatch = (combined_recv_user - give_user) + (give_opp - combined_recv_opp)
                    if mismatch <= 0:
                        continue

                    fairness = self._fairness_score([give_id], [recv_id_1, recv_id_2], seed_elo)
                    composite = (_c("mismatch_weight") * min(mismatch, 400) / 400 +
                                 _c("fairness_weight") * fairness)
                    composite *= _tier_mult_for_pids([give_id, recv_id_1, recv_id_2])
                    candidates.append((composite, mismatch, fairness, [give_id], [recv_id_1, recv_id_2]))

                    if len(candidates) >= int(_c("max_candidates")):
                        break
                if len(candidates) >= int(_c("max_candidates")):
                    break

        # ------------------------------------------------------------------
        # 3-for-2 trades (user gives 3, receives 2)
        # ------------------------------------------------------------------
        if len(candidates) < int(_c("max_candidates")) and not _budget_exceeded:
            for recv_id_1, recv_id_2 in combinations(recv_candidates, 2):
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                if recv_id_1 not in user_elo or recv_id_2 not in user_elo:
                    continue
                recv_dv_1 = _dv(recv_id_1)
                recv_dv_2 = _dv(recv_id_2)
                recv_pkg_dv = package_value([recv_dv_1, recv_dv_2])

                for give_id_1, give_id_2, give_id_3 in combinations(give_candidates, 3):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    if (give_id_1 not in user_elo or give_id_2 not in user_elo
                            or give_id_3 not in user_elo):
                        continue
                    # At least one give player must be pinned
                    if pinned_set and not ({give_id_1, give_id_2, give_id_3} & pinned_set):
                        continue

                    # Quick KTC pre-filter (cheap — avoids ELO math on bad pairs)
                    give_ids_3 = [give_id_1, give_id_2, give_id_3]
                    recv_ids_2 = [recv_id_1, recv_id_2]
                    give_pkg_dv = package_value([_dv(g) for g in give_ids_3])
                    if give_pkg_dv == 0 and recv_pkg_dv == 0:
                        pass  # both zero — let ELO decide
                    else:
                        greater = max(give_pkg_dv, recv_pkg_dv)
                        lesser  = min(give_pkg_dv, recv_pkg_dv)
                        if greater > 0 and (lesser / greater) < fairness_threshold:
                            continue
                    if not _elo_gap_ok(give_ids_3, recv_ids_2):
                        continue

                    combined_give_user = sum(user_elo.get(g, 1500) for g in give_ids_3)
                    combined_give_opp  = sum(opp_elo.get(g, 1500) for g in give_ids_3)
                    combined_recv_user = user_elo.get(recv_id_1, 1500) + user_elo.get(recv_id_2, 1500)
                    combined_recv_opp  = opp_elo.get(recv_id_1, 1500) + opp_elo.get(recv_id_2, 1500)

                    # User values the 2-pack more than the 3-pack they give
                    if combined_recv_user <= combined_give_user * 0.95:
                        continue
                    # Opponent values the 3-pack more than the 2-pack they give
                    if combined_give_opp <= combined_recv_opp * 0.95:
                        continue

                    mismatch = (combined_recv_user - combined_give_user) + (combined_give_opp - combined_recv_opp)
                    if mismatch <= 0:
                        continue

                    fairness = self._fairness_score(
                        [give_id_1, give_id_2, give_id_3], [recv_id_1, recv_id_2], seed_elo)
                    composite = (_c("mismatch_weight") * min(mismatch, 500) / 500 +
                                 _c("fairness_weight") * fairness)
                    candidates.append((
                        composite, mismatch, fairness,
                        [give_id_1, give_id_2, give_id_3],
                        [recv_id_1, recv_id_2],
                    ))

                    if len(candidates) >= int(_c("max_candidates")):
                        break
                if len(candidates) >= int(_c("max_candidates")):
                    break

        # ------------------------------------------------------------------
        # ------------------------------------------------------------------
        # Apply positional preference hard filter (not a score multiplier)
        # ------------------------------------------------------------------
        _acq  = acquire_positions    or []
        _away = trade_away_positions or []
        if _acq or _away:
            filtered: list[tuple[float, float, float, list[str], list[str]]] = []
            for composite, mismatch, fairness, give_ids, recv_ids in candidates:
                # If acquire_positions set, at least one received player must match
                if _acq:
                    recv_positions = [
                        players[pid].position for pid in recv_ids
                        if pid in players and players[pid].position
                    ]
                    if not any(p in _acq for p in recv_positions):
                        continue
                # If trade_away_positions set, at least one given player must match
                if _away:
                    give_positions = [
                        players[pid].position for pid in give_ids
                        if pid in players and players[pid].position
                    ]
                    if not any(p in _away for p in give_positions):
                        continue
                filtered.append((composite, mismatch, fairness, give_ids, recv_ids))
            candidates = filtered

        # ------------------------------------------------------------------
        # Agent A8 — apply trade-math adjustments (flag-gated).
        # Each candidate's composite score is multiplied by the product
        # of all enabled adjustments. Adjustments are ADDITIVE — each
        # enabled flag contributes independently and compounds.
        # When ALL flags are off this loop is a no-op (each function
        # short-circuits to 1.0 and leaves reasons untouched), so the
        # final candidate list is IDENTICAL to the legacy behaviour.
        # ------------------------------------------------------------------
        # Determine active scoring format once (for star-tax tier lookup).
        # We don't have explicit access here, so fall back to "1qb_ppr".
        _scoring_format = getattr(self, "_scoring_format", "1qb_ppr")
        _adjusted: list[tuple[float, float, float, list[str], list[str], list[str]]] = []
        for composite, mismatch, fairness, give_ids, recv_ids in candidates:
            reasons: list[str] = []
            adj = 1.0
            adj *= qb_tax_adjustment(
                give_ids, recv_ids, seed_elo, players, reasons,
            )
            adj *= star_tax_adjustment(
                give_ids, recv_ids, seed_elo, players, _scoring_format, reasons,
            )
            adj *= roster_clogger_adjustment(give_ids, recv_ids, reasons)
            new_composite = composite * adj
            _adjusted.append((new_composite, mismatch, fairness, give_ids, recv_ids, reasons))

        # Sort and take top N
        # ------------------------------------------------------------------
        _adjusted.sort(key=lambda x: x[0], reverse=True)
        cards = []
        for composite, mismatch, fairness, give_ids, recv_ids, reasons in _adjusted[:max_cards]:
            card = TradeCard(
                trade_id          = str(uuid.uuid4())[:8],
                league_id         = league_id,
                proposing_user_id = user_id,
                target_user_id    = opponent.user_id,
                target_username   = opponent.username,
                give_player_ids   = give_ids,
                receive_player_ids= recv_ids,
                mismatch_score    = round(mismatch, 1),
                fairness_score    = round(fairness, 3),
                composite_score   = round(composite, 3),
                reasons           = reasons if FLAGS.trade_math_human_explanations else [],
            )
            cards.append(card)
        return cards

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _mismatch_score(
        self,
        give_id: str,
        recv_id: str,
        user_elo: dict[str, float],
        opp_elo: dict[str, float],
    ) -> float:
        """
        How much perceived mutual gain exists in this 1-for-1 trade.
        Positive = both parties think they're winning.
        """
        user_gives_up   = user_elo.get(give_id, 1500)
        opp_values_give = opp_elo.get(give_id, 1500)
        user_gains      = user_elo.get(recv_id, 1500)
        opp_gives_up    = opp_elo.get(recv_id, 1500)

        # Opponent values what user gives MORE than user does
        opp_surplus = opp_values_give - user_gives_up
        # User values what they receive MORE than opponent does
        user_surplus = user_gains - opp_gives_up

        return opp_surplus + user_surplus

    def _fairness_score(
        self,
        give_ids: list[str],
        recv_ids: list[str],
        seed_elo: dict[str, float],
    ) -> float:
        """
        How balanced the trade is in consensus value (0–1).
        1.0 = perfectly balanced. Drops toward 0 as imbalance grows.
        """
        give_val = sum(seed_elo.get(pid, 1500) for pid in give_ids)
        recv_val = sum(seed_elo.get(pid, 1500) for pid in recv_ids)
        if give_val == 0 and recv_val == 0:
            return 1.0
        ratio = max(give_val, recv_val) / max(min(give_val, recv_val), 1)
        return round(1.0 / ratio, 3)
