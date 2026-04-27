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
    # Positional preference multipliers
    "pos_acquire_bonus":     0.20,
    "pos_tradeaway_bonus":   0.15,
    "pos_conflict_penalty":  0.15,
    "pos_multiplier_cap":    2.00,
    # TradeService scoring thresholds
    "min_mismatch_score":   40.0,
    "max_value_ratio":       2.5,
    "mismatch_weight":       0.70,
    "fairness_weight":       0.30,
    "max_candidates":      500.0,
    # Trade ELO gap filter
    "trade_elo_gap_max":   250.0,
    # Agent A8 — trade-math adjustments (all behind feature flags)
    "qb_tax_rate":               0.075,  # 7.5% penalty when a side gets a premium QB
    "star_tax_per_tier_gap":     0.10,   # 10% penalty per tier gap beyond 1
    "star_tax_elite_multiplier": 1.5,    # extra multiplier when a Tier-1 star is traded away
    "roster_spot_penalty":       0.05,   # 5% penalty per extra roster spot used
    "roster_clogger_penalty":    0.10,   # 10% ADDITIONAL penalty per player beyond 2 in a 3+ one-way
    "roster_clogger_threshold":  3.0,    # 3+ players one-way triggers "clogger"
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


def team_outlook_multiplier(
    give_player_ids: list[str],
    receive_player_ids: list[str],
    outlook: str | None,
    player_ages: dict[str, int],
) -> float:
    """
    Return a composite-score multiplier based on the user's team outlook
    and the ages of the players in the trade.

    Applied *after* the standard mismatch/fairness scoring so it acts as
    a soft re-ordering of the generated cards rather than a hard filter.

    Age lookup: player_ages maps player_id → age (int).  Players with no age
    data are excluded from the average; if no data is available at all the
    multiplier falls back to 1.0 (neutral).

    Outlooks
    ────────
    championship   Strongly prefer receiving veterans (≥27) for youth (<27).
                   Penalise receiving youth for vets.
    contender      Same direction, roughly half the magnitude.
    rebuilder      Mirror of championship: prefer receiving youth (≤26) for vets.
    jets           Extreme rebuilder: strong boost for ≤25 received;
                   heavy penalty for anything ≥26 received.
    not_sure       No adjustment (×1.0).
    """
    if not outlook or outlook == "not_sure":
        return _c("neutral")

    def _avg(ids: list[str]) -> float:
        ages = [player_ages[pid] for pid in ids
                if pid in player_ages and player_ages[pid] > 0]
        return sum(ages) / len(ages) if ages else 0.0

    recv_avg = _avg(receive_player_ids)
    give_avg = _avg(give_player_ids)

    if recv_avg == 0.0:
        return _c("neutral")   # no age data — can't meaningfully adjust

    vet_age   = _c("vet_age")
    youth_age = _c("youth_age")
    jets_age  = _c("jets_age")

    if outlook == "championship":
        if recv_avg >= vet_age and give_avg < vet_age:
            return _c("boost_strong")    # receiving veterans, giving youth ✓
        if recv_avg < vet_age and give_avg >= vet_age:
            return _c("penalty_mod")     # receiving youth, giving veterans ✗
        return _c("neutral")

    if outlook == "contender":
        if recv_avg >= vet_age and give_avg < vet_age:
            return _c("boost_moderate")  # same direction, softer signal
        if recv_avg < vet_age and give_avg >= vet_age:
            return _c("penalty_soft")    # ~half the championship penalty
        return _c("neutral")

    if outlook == "rebuilder":
        if recv_avg <= youth_age and give_avg > youth_age:
            return _c("boost_strong")    # receiving youth, giving veterans ✓
        if recv_avg > youth_age and give_avg <= youth_age:
            return _c("penalty_mod")     # receiving veterans, giving youth ✗
        return _c("neutral")

    if outlook == "jets":
        if recv_avg <= jets_age:
            return _c("boost_strong")    # ≤25 received — extreme youth mode
        return _c("penalty_heavy")       # ≥26 received — hard pass

    return _c("neutral")


# ---------------------------------------------------------------------------
# KTC-style Dynasty Value
# ---------------------------------------------------------------------------
# Exponential decay: rank 1 ≈ 9875, rank 200 ≈ 806, rank 500 ≈ ~66
# All constants are now live-loaded from _cfg (seeded from model_config table).


def dynasty_value(player, rank_override: int | None = None) -> float:
    """
    KTC-style exponential dynasty value for a single player/pick.

    For draft picks (position == "PICK"):  uses player.pick_value directly
    (already on a 0-10000 scale from pick_value formula in database.py).

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
        return float(getattr(player, "pick_value", 1000) or 1000)

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


def positional_preference_multiplier(
    give_player_ids: list[str],
    receive_player_ids: list[str],
    acquire_positions: list[str],
    trade_away_positions: list[str],
    player_db: dict,  # player_id → player object with .position attribute
) -> float:
    """
    Soft composite-score multiplier based on the user's positional preferences.

    Applied *after* ELO/KTC scoring so it re-orders cards rather than filtering.
    Capped at ×2.0 to prevent extreme over-weighting.

    Boost rules:
      +20% per received player whose position is in acquire_positions
      +15% per given player whose position is in trade_away_positions

    Penalty rule:
      -15% per received player whose position is in trade_away_positions
      (but NOT in acquire_positions) — signals the user explicitly wants
      to move that position, not stack it.
    """
    if not acquire_positions and not trade_away_positions:
        return 1.0

    multiplier = 1.0

    acq_bonus   = _c("pos_acquire_bonus")
    away_bonus  = _c("pos_tradeaway_bonus")
    conf_pen    = _c("pos_conflict_penalty")
    mult_cap    = _c("pos_multiplier_cap")

    # Boost: receiving positions the user wants
    if acquire_positions:
        recv_positions = [
            player_db[pid].position
            for pid in receive_player_ids
            if pid in player_db and player_db[pid].position
        ]
        matches = sum(1 for p in recv_positions if p in acquire_positions)
        if matches > 0:
            multiplier *= (1.0 + acq_bonus * matches)

    # Boost: giving away positions the user wants to shed
    if trade_away_positions:
        give_positions = [
            player_db[pid].position
            for pid in give_player_ids
            if pid in player_db and player_db[pid].position
        ]
        matches = sum(1 for p in give_positions if p in trade_away_positions)
        if matches > 0:
            multiplier *= (1.0 + away_bonus * matches)

    # Mild penalty: receiving a position the user explicitly wants to shed
    if trade_away_positions and acquire_positions:
        recv_positions = [
            player_db[pid].position
            for pid in receive_player_ids
            if pid in player_db and player_db[pid].position
        ]
        conflicts = sum(
            1 for p in recv_positions
            if p in trade_away_positions and p not in acquire_positions
        )
        if conflicts > 0:
            multiplier *= ((1.0 - conf_pen) ** conflicts)

    return min(round(multiplier, 4), mult_cap)


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
        scoring_format: str = "1qb_ppr",
        is_dynasty: bool = False,
        on_opponent_done = None,             # callback(idx_done, total, sorted_cards_so_far)
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
    ) -> list[TradeCard]:

        opp_elo    = opponent.elo_ratings
        opp_roster = opponent.roster
        players    = self._players
        pinned_set = set(pinned_give_players) if pinned_give_players else None

        # Time budget: bail out of expensive combination loops after 3s
        # per opponent to keep the overall request under ~30s.
        _deadline  = time.monotonic() + 3.0
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

        candidates: list[tuple[float, float, list[str], list[str]]] = []

        # ------------------------------------------------------------------
        # 1-for-1 trades
        # ------------------------------------------------------------------
        for give_id in user_roster:
            if give_id not in user_elo or give_id not in opp_elo:
                continue
            # When pinned players specified, only consider those as give candidates
            if pinned_set and give_id not in pinned_set:
                continue
            for recv_id in opp_roster:
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
                candidates.append((composite, mismatch, [give_id], [recv_id]))

                if len(candidates) >= int(_c("max_candidates")):
                    break
            if len(candidates) >= int(_c("max_candidates")):
                break

        # ------------------------------------------------------------------
        # 2-for-1 trades (user gives 2, receives 1 elite player)
        # ------------------------------------------------------------------
        _budget_exceeded = False
        if len(candidates) < int(_c("max_candidates")):
            for recv_id in opp_roster:
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                if recv_id not in user_elo or recv_id not in opp_elo:
                    continue
                recv_dv = _dv(recv_id)

                for give_id_1, give_id_2 in combinations(user_roster, 2):
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
                    candidates.append((composite, mismatch, [give_id_1, give_id_2], [recv_id]))

                    if len(candidates) >= int(_c("max_candidates")):
                        break
                if len(candidates) >= int(_c("max_candidates")):
                    break

        # ------------------------------------------------------------------
        # 1-for-2 trades (user gives 1 elite, receives 2)
        # ------------------------------------------------------------------
        if len(candidates) < int(_c("max_candidates")) and not _budget_exceeded:
            for give_id in user_roster:
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                if give_id not in user_elo or give_id not in opp_elo:
                    continue
                if pinned_set and give_id not in pinned_set:
                    continue

                for recv_id_1, recv_id_2 in combinations(opp_roster, 2):
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
                    candidates.append((composite, mismatch, [give_id], [recv_id_1, recv_id_2]))

                    if len(candidates) >= int(_c("max_candidates")):
                        break
                if len(candidates) >= int(_c("max_candidates")):
                    break

        # ------------------------------------------------------------------
        # 3-for-2 trades (user gives 3, receives 2)
        # ------------------------------------------------------------------
        if len(candidates) < int(_c("max_candidates")) and not _budget_exceeded:
            for recv_id_1, recv_id_2 in combinations(opp_roster, 2):
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                if recv_id_1 not in user_elo or recv_id_2 not in user_elo:
                    continue
                recv_dv_1 = _dv(recv_id_1)
                recv_dv_2 = _dv(recv_id_2)
                recv_pkg_dv = package_value([recv_dv_1, recv_dv_2])

                for give_id_1, give_id_2, give_id_3 in combinations(user_roster, 3):
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
                        composite, mismatch,
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
            filtered: list[tuple[float, float, list[str], list[str]]] = []
            for composite, mismatch, give_ids, recv_ids in candidates:
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
                filtered.append((composite, mismatch, give_ids, recv_ids))
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
        _adjusted: list[tuple[float, float, list[str], list[str], list[str]]] = []
        for composite, mismatch, give_ids, recv_ids in candidates:
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
            _adjusted.append((new_composite, mismatch, give_ids, recv_ids, reasons))

        # Sort and take top N
        # ------------------------------------------------------------------
        _adjusted.sort(key=lambda x: x[0], reverse=True)
        cards = []
        for composite, mismatch, give_ids, recv_ids, reasons in _adjusted[:max_cards]:
            card = TradeCard(
                trade_id          = str(uuid.uuid4())[:8],
                league_id         = league_id,
                proposing_user_id = user_id,
                target_user_id    = opponent.user_id,
                target_username   = opponent.username,
                give_player_ids   = give_ids,
                receive_player_ids= recv_ids,
                mismatch_score    = round(mismatch, 1),
                fairness_score    = round(composite, 3),
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
