"""
ranking_service.py — Fantasy Trade Finder
==========================================
Core ranking logic supporting both 2-player (pairwise) and
3-player (full-rank) interactions.

3-player ranking: user orders 3 players best→worst in one interaction.
Each ranking is decomposed into 3 pairwise decisions (A>B, A>C, B>C)
and fed into the Elo engine — 2.6x more information per interaction
than a single head-to-head.

Progress is tracked in "interactions" (not raw swipes) for clean UX.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
import json
import random


# ---------------------------------------------------------------------------
# Tier-band config — single source of truth for both backend and frontend.
# The frontend fetches the same JSON via GET /api/tier-config so the two
# sides cannot drift. Each (scoring_format, position, tier) row carries a
# [min, max] ELO band.
# ---------------------------------------------------------------------------

_TIER_CONFIG_PATH = Path(__file__).parent / "tier_config.json"

def _load_tier_config() -> dict:
    """Load and validate the tier band config. Cached per-process — the
    file changes only on deploy, so no hot reload needed."""
    raw = json.loads(_TIER_CONFIG_PATH.read_text())
    # Strip the comment key. Keep the rest verbatim.
    return {k: v for k, v in raw.items() if not k.startswith("_")}

TIER_CONFIG: dict = _load_tier_config()
ORDERED_TIERS: tuple[str, ...] = ("elite", "starter", "solid", "depth", "bench")


# ---------------------------------------------------------------------------
# Runtime config — loaded from model_config DB table via reload_config().
# Falls back to _DEFAULT_CFG if the DB isn't available yet.
# ---------------------------------------------------------------------------

_DEFAULT_CFG: dict[str, float] = {
    "elo_k":                     32.0,
    "trade_k_like":               8.0,
    "trade_k_pass":               4.0,
    "trade_k_accept":            20.0,
    "trade_k_decline_correction": 20.0,
    # Tier engine
    "tier_engine_enabled":        1.0,
    "smart_matchup_enabled":      1.0,
    "tier_size":                 24.0,
    "mix_in_rate_base":           0.35,
    "mix_in_rate_max":            0.80,
    "mix_in_saturation_pct":      0.70,
    "mix_in_pre_unlock_start":    5.0,
}

_cfg: dict[str, float] = dict(_DEFAULT_CFG)


def reload_config() -> None:
    """Pull latest ELO K-factor values from model_config into _cfg."""
    global _cfg
    try:
        from .database import get_config as _db_get_config
        fresh = _db_get_config()
        if fresh:
            _cfg.update({k: fresh[k] for k in _DEFAULT_CFG if k in fresh})
    except Exception:
        pass


def _c(key: str) -> float:
    return _cfg.get(key, _DEFAULT_CFG[key])


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class Player:
    id: str
    name: str
    position: str       # "QB" | "RB" | "WR" | "TE"
    team: str
    age: int
    years_experience: int = 0
    # Extended fields — populated when loaded from the players DB table
    depth_chart_position: str | None = None   # e.g. "WR" (same as position)
    depth_chart_order:    int | None = None   # 1=starter, 2=backup, etc.
    injury_status:        str | None = None   # "Questionable" | "Out" | etc.
    injury_body_part:     str | None = None   # "Knee" | "Hamstring" | etc.
    birth_date:           str | None = None   # "YYYY-MM-DD"
    height:               str | None = None   # inches as string, e.g. "73"
    weight:               str | None = None   # lbs as string, e.g. "215"
    college:              str | None = None
    search_rank:          int | None = None   # Sleeper's internal rank proxy
    adp:                  float | None = None # ADP if available
    pick_value:           float | None = None # non-None only for PICK pseudo-players


@dataclass
class SwipeDecision:
    winner_id: str
    loser_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RankedPlayer:
    player: Player
    elo: float
    wins: int
    losses: int
    rank: int


@dataclass
class RankSet:
    position: Optional[str]
    rankings: list[RankedPlayer]
    interaction_count: int
    threshold: int
    threshold_met: bool
    version: int
    computed_at: str


@dataclass
class MatchupTrio:
    player_a: Player
    player_b: Player
    player_c: Player
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Ranking Service
# ---------------------------------------------------------------------------

class RankingService:
    """
    Manages player rankings for a single user session.

    Supports 3-player ranking interactions: user sees 3 players and
    ranks them 1st / 2nd / 3rd. Each interaction is decomposed into
    3 pairwise Elo updates, cutting required interactions by ~60%.

    Thresholds are expressed in interactions (not raw swipes).
    """

    # Interactions needed to establish rankings
    # 3-player ranking ≈ 2.58 bits; 2-player ≈ 1.0 bit
    # These are calibrated for ~5 effective comparisons per player
    POSITION_THRESHOLDS = {
        "QB": 10,   # Standardised: 10 interactions per position
        "RB": 10,   # Matches the Trade Finder unlock gate
        "WR": 10,
        "TE": 10,
        None: 16,   # all positions combined
    }

    # ELO_INITIAL is a structural constant (not a tunable multiplier) — kept here.
    ELO_INITIAL = 1500.0

    # ELO K-factors are now loaded from model_config via _c() at call time.
    # Default values live in _DEFAULT_CFG at module level.
    # Keys: elo_k, trade_k_like, trade_k_pass, trade_k_accept,
    #       trade_k_decline_correction

    def __init__(
        self,
        players: list[Player],
        matchup_generator=None,
        seed_ratings: Optional[dict[str, float]] = None,
    ):
        """
        seed_ratings: { player.id: initial_elo } from consensus data.
        Players not present in seed_ratings start at ELO_INITIAL (1500).
        """
        self._players    = {p.id: p for p in players}
        self._swipes: list[SwipeDecision] = []
        self._trade_swipes: list[tuple[SwipeDecision, float]] = []  # (swipe, k_factor)
        self._interactions: dict[Optional[str], int] = {}
        self._version    = 0
        self._generator  = matchup_generator
        self._seed       = seed_ratings or {}
        self._elo_overrides: dict[str, float] = {}  # manual reorder overrides

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has_player(self, player_id: str) -> bool:
        """Return True if player_id is in the current player pool."""
        return player_id in self._players

    def record_ranking(self, ordered_ids: list[str]) -> RankSet:
        """
        Record a 3-player (or 2-player) ranking.

        ordered_ids: player IDs ordered best → worst.
        Decomposes into all pairwise comparisons for the Elo engine.
        """
        if len(ordered_ids) < 2:
            raise ValueError("Need at least 2 player IDs")
        for pid in ordered_ids:
            if pid not in self._players:
                raise ValueError(f"Unknown player id: {pid!r}")

        # Decompose: for [A, B, C] → A>B, A>C, B>C
        for i in range(len(ordered_ids)):
            for j in range(i + 1, len(ordered_ids)):
                self._swipes.append(SwipeDecision(
                    winner_id=ordered_ids[i],
                    loser_id=ordered_ids[j],
                ))

        # Track interaction count per position
        pos = self._players[ordered_ids[0]].position
        self._interactions[pos]  = self._interactions.get(pos, 0)  + 1
        self._interactions[None] = self._interactions.get(None, 0) + 1
        self._version += 1

        return self.get_rankings(position=pos)

    def record_trade_signal(
        self,
        winner_ids: list[str],
        loser_ids: list[str],
        decision: str = "like",
    ) -> None:
        """
        Apply a soft ELO update from a trade decision.

        decision='like'  (Interested): user values the received players over the
                          given players → winner_ids=receive, loser_ids=give.
                          Uses TRADE_K_LIKE (~25% of a ranking swipe).

        decision='pass': user preferred keeping their players → winner_ids=give,
                          loser_ids=receive. Weaker signal, uses TRADE_K_PASS
                          (~12% of a ranking swipe).

        For multi-player sides (e.g. 2-for-1 trades) every winner is paired
        against every loser, same as the ranking engine's pairwise decomposition.
        """
        k = _c("trade_k_like") if decision == "like" else _c("trade_k_pass")
        for wid in winner_ids:
            for lid in loser_ids:
                if wid == lid:
                    continue
                if wid not in self._players or lid not in self._players:
                    continue
                self._trade_swipes.append((
                    SwipeDecision(winner_id=wid, loser_id=lid),
                    k,
                ))
        self._version += 1

    def record_disposition_signal(
        self,
        winner_ids: list[str],
        loser_ids: list[str],
        k_factor: float,
    ) -> None:
        """
        Apply a disposition-triggered ELO update with an explicit K-factor.

        Called when both parties have confirmed (or declined) a matched trade:
          Accept  → winner=receive_ids, loser=give_ids, k=TRADE_K_ACCEPT (20)
          Decline → winner=give_ids, loser=receive_ids, k=TRADE_K_DECLINE_CORRECTION (20)
                    (net ≈ −12 after the original +8 Interested swipe)

        Uses the same _trade_swipes list as record_trade_signal so it is
        automatically included in _compute_elo and replayed from the DB.
        """
        for wid in winner_ids:
            for lid in loser_ids:
                if wid == lid:
                    continue
                if wid not in self._players or lid not in self._players:
                    continue
                self._trade_swipes.append((
                    SwipeDecision(winner_id=wid, loser_id=lid),
                    float(k_factor),
                ))
        self._version += 1

    def get_next_trio(
        self,
        position: Optional[str] = None,
        skipped_player_ids: Optional[set] = None,
    ) -> MatchupTrio:
        """Return the most informative next 3 players to rank.

        skipped_player_ids (Agent 1): persistent "I don't know this player"
        exclusions. Players in this set are filtered out of the candidate pool
        so they never appear in future trios for this user + format.
        """
        _skipped: set = skipped_player_ids or set()

        # Tier engine: filter the pool based on ranking progress phase
        if _c("tier_engine_enabled") == 1.0:
            pool = self._tiered_pool(position)
        else:
            pool = self._pool(position)

        # Agent 1: remove any skipped players before size check so the error
        # message reflects the *usable* pool size.
        if _skipped:
            pool = [p for p in pool if p.id not in _skipped]

        if len(pool) < 3:
            raise ValueError(f"Need at least 3 players for position={position!r}")

        # Claude-powered matchup selection (gated by feature flag)
        if self._generator is not None and _c("smart_matchup_enabled") == 1.0:
            try:
                from .smart_matchup_generator import SwipeDecision as SD
                history = [SD(winner_id=s.winner_id, loser_id=s.loser_id) for s in self._swipes]
                trio = self._generator.generate_next_trio(
                    players=pool,
                    swipe_history=history,
                    position_filter=position,
                    skipped_player_ids=_skipped,
                )
                return trio
            except Exception:
                pass

        return self._algorithmic_trio(pool, position=position)

    def get_rankings(self, position: Optional[str] = None) -> RankSet:
        """Return current ordered rankings for a position."""
        pool      = self._pool(position)
        elo       = self._compute_elo(pool)
        stats     = self._compute_stats(pool)
        threshold = self.POSITION_THRESHOLDS.get(position, 10)
        count     = self._interactions.get(position, 0)

        sorted_players = sorted(pool, key=lambda p: elo[p.id], reverse=True)
        ranked = [
            RankedPlayer(
                player=p,
                elo=round(elo[p.id], 1),
                wins=stats[p.id]["wins"],
                losses=stats[p.id]["losses"],
                rank=i + 1,
            )
            for i, p in enumerate(sorted_players)
        ]

        return RankSet(
            position=position,
            rankings=ranked,
            interaction_count=count,
            threshold=threshold,
            threshold_met=count >= threshold,
            version=self._version,
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_progress(self, position: Optional[str] = None) -> dict:
        threshold = self.POSITION_THRESHOLDS.get(position, 10)
        count     = self._interactions.get(position, 0)
        pct       = min(100, round(count / threshold * 100))
        return {
            "position":         position,
            "interaction_count": count,
            "threshold":         threshold,
            "threshold_met":     count >= threshold,
            "percent":           pct,
        }

    def replay_from_db(self, swipes: list[dict]) -> int:
        """
        Replay persisted swipe decisions into the in-memory ELO engine.

        Called once during session_init() to restore a user's ranking history
        after a server restart.  Any swipe referencing a player not in the
        current pool (e.g. from a different league) is silently skipped.

        swipes: list of dicts as returned by database.load_swipe_decisions():
            winner_player_id, loser_player_id, decision_type, k_factor

        Returns the number of rows that were actually replayed.
        """
        replayed = 0

        for row in swipes:
            wid = row["winner_player_id"]
            lid = row["loser_player_id"]
            if wid not in self._players or lid not in self._players:
                continue   # player from a different league / no longer in pool

            dtype = row.get("decision_type", "rank")
            k     = float(row.get("k_factor", _c("elo_k")))
            sd    = SwipeDecision(winner_id=wid, loser_id=lid)

            if dtype == "rank":
                self._swipes.append(sd)
            else:
                self._trade_swipes.append((sd, k))

            replayed += 1

        # Reconstruct interaction counts from replayed ranking swipes.
        # Each 3-player ranking produces exactly 3 pairwise rows in the DB
        # (A>B, A>C, B>C), all for the same position.  So:
        #   interaction_count[pos] = rank_swipes_for_pos // 3
        pos_swipe_counts: dict = {}
        for s in self._swipes:
            pos = self._players[s.winner_id].position
            pos_swipe_counts[pos]  = pos_swipe_counts.get(pos, 0)  + 1
            pos_swipe_counts[None] = pos_swipe_counts.get(None, 0) + 1

        self._interactions = {
            pos: cnt // 3
            for pos, cnt in pos_swipe_counts.items()
        }

        self._version = replayed
        return replayed

    def reset(self, position: Optional[str] = None) -> dict:
        if position is None:
            self._swipes.clear()
            self._trade_swipes.clear()
            self._interactions.clear()
        else:
            pool_ids = {p.id for p in self._pool(position)}
            self._swipes = [
                s for s in self._swipes
                if s.winner_id not in pool_ids or s.loser_id not in pool_ids
            ]
            self._trade_swipes = [
                (s, k) for s, k in self._trade_swipes
                if s.winner_id not in pool_ids or s.loser_id not in pool_ids
            ]
            self._interactions.pop(position, None)
        self._version += 1
        return {"reset": True, "position": position}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pool(self, position: Optional[str]) -> list[Player]:
        """Return ALL players for a position (unfiltered)."""
        players = list(self._players.values())
        if position:
            players = [p for p in players if p.position == position]
        return players

    # ------------------------------------------------------------------
    # Tier Engine
    # ------------------------------------------------------------------

    def _tiered_pool(self, position: Optional[str]) -> list[Player]:
        """
        Return a tier-filtered player pool based on the user's ranking
        progress phase.

        Pre-unlock (interactions < threshold):
            Only the top `tier_size` players by seed Elo for the position.
            Focuses early swipes on the most dynasty-relevant players so
            the Trade Finder unlock is backed by meaningful rankings.

        Post-unlock:
            The full top tier is always included. Lower-tier players are
            mixed in probabilistically — the mix-in rate scales from
            `mix_in_rate_base` up to `mix_in_rate_max` as comparison
            coverage within the top tier saturates.
        """
        full_pool = self._pool(position)
        if len(full_pool) <= 3:
            return full_pool

        tier_size = int(_c("tier_size"))

        # Sort by seed Elo descending (consensus value = initial priority)
        sorted_by_seed = sorted(
            full_pool,
            key=lambda p: self._seed.get(p.id, self.ELO_INITIAL),
            reverse=True,
        )

        top_tier = sorted_by_seed[:tier_size]
        lower_tier = sorted_by_seed[tier_size:]

        interactions = self._interactions.get(position, 0)
        threshold = self.POSITION_THRESHOLDS.get(position, 10)

        # -- Pre-unlock: top tier + early mix-in after a few interactions --
        if interactions < threshold:
            pre_unlock_start = int(_c("mix_in_pre_unlock_start"))
            if interactions >= pre_unlock_start and lower_tier:
                # Introduce 1-2 fresh lower-tier players to broaden rankings
                lower_stats = self._compute_stats(full_pool)
                lower_by_freshness = sorted(
                    lower_tier,
                    key=lambda p: (
                        len(lower_stats[p.id]["compared"]),
                        -self._seed.get(p.id, self.ELO_INITIAL),
                    ),
                )
                return list(top_tier) + lower_by_freshness[:2]
            return top_tier

        # -- Post-unlock: mix in lower-tier players progressively --
        if not lower_tier:
            return top_tier  # no lower players to mix in

        # Compute comparison saturation within the top tier.
        # saturation = (unique pairs compared) / (total possible pairs)
        stats = self._compute_stats(top_tier)
        compared_pairs = set()
        for pid, s in stats.items():
            for cid in s["compared"]:
                compared_pairs.add(tuple(sorted([pid, cid])))
        total_possible = max(1, len(top_tier) * (len(top_tier) - 1) // 2)
        saturation = len(compared_pairs) / total_possible

        # Scale mix-in rate: base → max as saturation approaches threshold
        sat_pct = _c("mix_in_saturation_pct")
        mix_base = _c("mix_in_rate_base")
        mix_max = _c("mix_in_rate_max")

        if sat_pct > 0 and saturation >= sat_pct:
            mix_rate = mix_max
        elif sat_pct > 0:
            mix_rate = mix_base + (mix_max - mix_base) * (saturation / sat_pct)
        else:
            mix_rate = mix_base

        # Decide how many lower-tier players to include.
        # For a trio of 3, mix_rate represents the probability that one
        # slot goes to a lower-tier player. We pick 0 or 1 (or rarely 2)
        # lower players to inject into the pool.
        mix_count = 0
        for _ in range(2):  # max 2 lower-tier players per pool refresh
            if random.random() < mix_rate:
                mix_count += 1

        # Force mix-in when the top tier is heavily compared
        if mix_count == 0 and lower_tier:
            min_comparisons = min(len(stats[p.id]["compared"]) for p in top_tier) if top_tier else 0
            if min_comparisons >= 3:
                mix_count = 1

        if mix_count == 0:
            return top_tier

        # Pick the highest-seed lower-tier players that have the fewest
        # existing comparisons (freshest signal).
        lower_stats = self._compute_stats(full_pool)
        lower_by_freshness = sorted(
            lower_tier,
            key=lambda p: (
                len(lower_stats[p.id]["compared"]),       # fewer comparisons first
                -self._seed.get(p.id, self.ELO_INITIAL),  # then by seed Elo desc
            ),
        )

        mixed = list(top_tier) + lower_by_freshness[:mix_count]
        return mixed

    def _tier_info(self, position: Optional[str]) -> dict:
        """
        Return metadata about the current tier state for a position.
        Used by the /api/trio endpoint to inform the frontend.
        """
        full_pool = self._pool(position)
        tier_size = int(_c("tier_size"))
        interactions = self._interactions.get(position, 0)
        threshold = self.POSITION_THRESHOLDS.get(position, 10)
        unlocked = interactions >= threshold

        if unlocked and len(full_pool) > tier_size:
            # Compute saturation for reporting
            sorted_by_seed = sorted(
                full_pool,
                key=lambda p: self._seed.get(p.id, self.ELO_INITIAL),
                reverse=True,
            )
            top_tier = sorted_by_seed[:tier_size]
            stats = self._compute_stats(top_tier)
            compared_pairs = set()
            for pid, s in stats.items():
                for cid in s["compared"]:
                    compared_pairs.add(tuple(sorted([pid, cid])))
            total_possible = max(1, len(top_tier) * (len(top_tier) - 1) // 2)
            saturation = len(compared_pairs) / total_possible
        else:
            saturation = 0.0

        return {
            "phase": "post_unlock" if unlocked else "pre_unlock",
            "tier_size": tier_size,
            "total_players": len(full_pool),
            "pool_size": min(tier_size, len(full_pool)) if not unlocked else len(full_pool),
            "saturation": round(saturation, 3),
            "tier_engine_enabled": _c("tier_engine_enabled") == 1.0,
        }

    def _compute_elo(self, pool: list[Player]) -> dict[str, float]:
        pool_ids = {p.id for p in pool}
        # Seed each player's starting ELO.  Manual overrides (from tier saves
        # or drag-and-drop reorders) take priority over the DP consensus seed —
        # they represent the user's explicit rankings and become the anchor
        # point that subsequent swipes evolve from.
        ratings: dict[str, float] = {}
        for p in pool:
            if p.id in self._elo_overrides:
                ratings[p.id] = self._elo_overrides[p.id]
            else:
                ratings[p.id] = self._seed.get(p.id, self.ELO_INITIAL)

        elo_k = _c("elo_k")

        # Regular ranking swipes — full K factor. Applied AFTER overrides so
        # tier-saved players' ELOs can still evolve when the user ranks them.
        for s in self._swipes:
            w, l = s.winner_id, s.loser_id
            if w not in pool_ids or l not in pool_ids:
                continue
            ra, rb  = ratings[w], ratings[l]
            ea       = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            ratings[w] += elo_k * (1.0 - ea)
            ratings[l] += elo_k * (0.0 - (1.0 - ea))

        # Trade-decision swipes — reduced K factor (softer signal)
        for s, k in self._trade_swipes:
            w, l = s.winner_id, s.loser_id
            if w not in pool_ids or l not in pool_ids:
                continue
            ra, rb  = ratings[w], ratings[l]
            ea       = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            ratings[w] += k * (1.0 - ea)
            ratings[l] += k * (0.0 - (1.0 - ea))

        return ratings

    def _compute_stats(self, pool: list[Player]) -> dict[str, dict]:
        pool_ids = {p.id for p in pool}
        stats    = {p.id: {"wins": 0, "losses": 0, "compared": set()} for p in pool}
        for s in self._swipes:
            w, l = s.winner_id, s.loser_id
            if w not in pool_ids or l not in pool_ids:
                continue
            stats[w]["wins"]   += 1
            stats[l]["losses"] += 1
            stats[w]["compared"].add(l)
            stats[l]["compared"].add(w)
        return stats

    def _algorithmic_trio(self, pool: list[Player], position: Optional[str] = None) -> MatchupTrio:
        """Pick 3 adjacent players in Elo order that haven't all been compared.

        When position is None (cross-position / Overall mode), a diversity
        bonus is applied to prefer trios spanning 2+ positions.
        """
        elo          = self._compute_elo(pool)
        sorted_p     = sorted(pool, key=lambda p: elo[p.id], reverse=True)
        stats        = self._compute_stats(pool)
        best_trio    = None
        best_score   = float("inf")
        cross_pos    = position is None  # Overall mode

        for i in range(len(sorted_p) - 2):
            for j in range(i + 1, min(i + 5, len(sorted_p) - 1)):
                for k in range(j + 1, min(j + 5, len(sorted_p))):
                    p1, p2, p3 = sorted_p[i], sorted_p[j], sorted_p[k]
                    # Elo spread of the trio (smaller = tighter competition)
                    spread = elo[p1.id] - elo[p3.id]
                    # Prefer trios with fewer existing pairwise comparisons
                    existing = sum([
                        p2.id in stats[p1.id]["compared"],
                        p3.id in stats[p1.id]["compared"],
                        p3.id in stats[p2.id]["compared"],
                    ])
                    # Penalise over-compared players — steers toward fresher faces
                    total_comparisons = sum(
                        len(stats[p.id]["compared"]) for p in [p1, p2, p3]
                    )
                    freshness_penalty = total_comparisons * 10
                    # In Overall mode, bonus for trios spanning multiple positions
                    diversity_bonus = 0
                    if cross_pos:
                        positions = {p1.position, p2.position, p3.position}
                        diversity_bonus = -30 * (len(positions) - 1)  # reward multi-position
                    score = spread + existing * 50 + freshness_penalty + diversity_bonus
                    if score < best_score:
                        best_score = score
                        best_trio  = (p1, p2, p3)

        p1, p2, p3 = best_trio
        return MatchupTrio(
            player_a=p1,
            player_b=p2,
            player_c=p3,
            reasoning="Tightest uncompared trio by Elo.",
        )

    # ELO bands for tier-based saves are now defined ONCE in
    # backend/tier_config.json (loaded into TIER_CONFIG above) and shared
    # with the frontend via GET /api/tier-config. The previous class
    # attributes (UNIFORM_TIER_ELO_BANDS, QB_TE_1QB_TIER_ELO_BANDS) and
    # the format-aware fallback they encoded have moved into that file.

    @classmethod
    def tier_bands_for(
        cls,
        position: Optional[str],
        scoring_format: str = "1qb_ppr",
    ) -> dict[str, tuple[float, float]]:
        """Return the (lo, hi) ELO band per tier for a given position +
        scoring format, sourced from TIER_CONFIG (backend/tier_config.json).
        Used by apply_tiers server-side; the frontend reads the same JSON
        via /api/tier-config so the two sides cannot drift."""
        fmt_cfg = TIER_CONFIG.get(scoring_format) or TIER_CONFIG.get("1qb_ppr") or {}
        # Fall back to RB row when position is unspecified (general pool case).
        pos_key = position if position in fmt_cfg else "RB"
        pos_cfg = fmt_cfg.get(pos_key, {})
        return {
            tier: (float(band["min"]), float(band["max"]))
            for tier, band in pos_cfg.items()
        }

    @classmethod
    def tier_for_elo(
        cls,
        elo: float,
        position: Optional[str],
        scoring_format: str = "1qb_ppr",
    ) -> Optional[str]:
        """Inverse of `tier_bands_for` — bucket a raw ELO into a tier name.

        Returns one of: 'elite', 'starter', 'solid', 'depth', 'bench', or
        None when the ELO falls below the lowest band (unranked). Uses the
        band's `hi` as the upper inclusive cutoff per tier so the mapping
        matches what `apply_tiers` writes.

        This is the source of truth for the browser extension's tier badge
        and for anywhere the backend needs to label a player without going
        through the frontend's threshold table.
        """
        if elo is None:
            return None
        bands = cls.tier_bands_for(position, scoring_format)
        # Walk tiers top-down; return the first band whose hi >= elo >= lo.
        # We allow elo above 'elite' hi to still register as elite.
        ordered = ("elite", "starter", "solid", "depth", "bench")
        for tier in ordered:
            lo, hi = bands[tier]
            if elo >= lo:
                return tier
        return None

    def apply_tiers(
        self,
        position: Optional[str],
        tiers: dict[str, list[str]],
        scoring_format: str = "1qb_ppr",
        cleared_pids: Optional[list[str]] = None,
    ) -> None:
        """
        Apply a positional-tier save by setting ELO overrides that fall
        inside each tier's band (see tier_bands_for / tier_config.json).

        Within a tier, players are spread linearly across the band in the
        order they were submitted, preserving the user's intra-tier order.

        ``cleared_pids`` — when the frontend removes a player from all
        tiers (× button, "send to pool"), it forwards the pid here so we
        can DELETE the override from the in-memory dict. Without this,
        the player's old override survived and re-bucketed them on the
        next refresh, snapping them right back into their previous tier.
        """
        pool_ids = {p.id for p in self._pool(position)}
        bands = self.tier_bands_for(position, scoring_format)

        # Drop overrides for explicitly-cleared pids first, so a pid that's
        # both cleared and re-tiered in the same save (rare, e.g. concurrent
        # tab) ends up with the new tier's band rather than left without an
        # override. The tier-write loop below will re-set it.
        if cleared_pids:
            for pid in cleared_pids:
                self._elo_overrides.pop(pid, None)

        for tier_name, player_ids in tiers.items():
            band = bands.get(tier_name)
            if band is None:
                continue
            lo, hi = band
            valid = [pid for pid in player_ids if pid in pool_ids]
            n = len(valid)
            if n == 0:
                continue
            if n == 1:
                self._elo_overrides[valid[0]] = hi
            else:
                for i, pid in enumerate(valid):
                    self._elo_overrides[pid] = hi - (hi - lo) * i / (n - 1)

        self._version += 1

    def apply_reorder(self, position: Optional[str], ordered_ids: list[str]) -> None:
        """
        Apply a manual reorder by setting ELO overrides that match the
        desired ranking order.  ELO values are linearly interpolated
        between the current max and min of the pool.
        """
        pool = self._pool(position)
        if len(pool) < 2:
            return

        current_elo = self._compute_elo(pool)
        pool_ids = {p.id for p in pool}

        # Only include IDs that are actually in the pool
        valid_ids = [pid for pid in ordered_ids if pid in pool_ids]
        if len(valid_ids) < 2:
            return

        # Compute target ELO range from the current pool
        elo_vals = list(current_elo.values())
        max_elo = max(elo_vals)
        min_elo = min(elo_vals)
        spread = max(max_elo - min_elo, 100)  # at least 100 ELO spread

        # Assign linearly spaced ELO values from max to min
        for i, pid in enumerate(valid_ids):
            target_elo = max_elo - (spread * i / max(len(valid_ids) - 1, 1))
            self._elo_overrides[pid] = target_elo

        self._version += 1
