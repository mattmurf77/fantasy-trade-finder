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
    # Trios → tier calibration (Lever A). Fraction of trios that probe a
    # value-band boundary — pairing a player just below a tier edge against
    # one just above it, drawn from the FULL pool — instead of the default
    # "tightest local trio". Boundary comparisons are the only ones that move
    # a player across a tier (and thus meaningfully change value). 0 = legacy
    # behaviour. See docs/plans/trios-tier-calibration-plan-2026-07-08.md.
    "trio_boundary_rate":         0.4,
    "trio_boundary_margin":      60.0,  # Elo window around an edge to pull straddlers from
    # Trio variety: the loop rotates among three strategies so the pattern
    # varies and the same players don't recur. Weights are shares of the mix;
    # tightest-ordering gets whatever's left after boundary + within-tier.
    #   boundary     — cross-tier edge probe (moves value across a band)
    #   within_tier  — top-vs-bottom of the SAME tier (nails intra-tier order)
    #   tightest     — legacy near-equal fine ordering
    "trio_within_tier_rate":      0.35,
    # Don't reuse a player who appeared in the last N served trios (anti-repeat;
    # fixes "2 of the same players 10 trios in a row"). Relaxes when the pool is
    # too small to honour it.
    "trio_repeat_avoid":          3.0,
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
        # Scoring format this service ranks in — drives which tier_config.json
        # value bands the boundary-probing trio selector reads. Defaults to
        # 1qb_ppr; multi-format callers set it post-construct (like _user_id).
        self._scoring_format = "1qb_ppr"
        # Trio variety state (in-session, per position where relevant). Recent
        # trios drive anti-repeat; the cursors rotate strategy + which tier a
        # within-tier trio calibrates so successive trios feel varied.
        self._recent_trios: list[frozenset] = []      # last-served trio id-sets
        self._trio_last_variety: Optional[str] = None
        self._within_tier_cursor: int = 0

        # INIT-03: instance-level memo for _compute_elo / _compute_stats.
        # Both methods re-iterate the full swipe history and are called 3-4x
        # per rank request. The inputs change only on a state mutation, which
        # every mutator already signals by bumping _version. We invalidate
        # automatically whenever _version moves.
        #
        # Both computations are POOL-DEPENDENT (a swipe is applied only when
        # both players are in the pool, and the result is keyed to the pool),
        # so the cache key is (_version, pool fingerprint) — not _version
        # alone. Keying on _version only would return a wrong-pool result when
        # different pools are passed at the same version (e.g. get_rankings'
        # full pool vs. _tier_info's top tier), violating the pure-pass-through
        # invariant. The pool fingerprint is the tuple of pool player ids.
        self._elo_cache: Optional[dict[str, float]] = None
        self._elo_cache_version: int = 0
        self._elo_cache_key: Optional[tuple] = None
        self._stats_cache: Optional[dict[str, dict]] = None
        self._stats_cache_version: int = 0
        self._stats_cache_key: Optional[tuple] = None

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

        # Players seen in the last N served trios — avoided so the same faces
        # don't recur trio after trio. Selectors relax this when honouring it
        # would leave too few candidates.
        avoid = self._trio_avoid_ids()

        # Rotate among strategies for variety (no long runs of one kind), each
        # weighted, never repeating the immediately-previous strategy when an
        # alternative exists:
        #   boundary    — cross-tier edge probe (moves value across a band)
        #   within_tier — top-vs-bottom of the same tier (fixes intra-tier order)
        #   tightest    — legacy near-equal fine ordering (smart/algorithmic)
        variety = self._pick_trio_variety(position)

        trio: Optional[MatchupTrio] = None
        if variety == "boundary":
            trio = self._boundary_trio(position, skipped=_skipped, avoid=avoid)
        elif variety == "within_tier":
            trio = self._within_tier_trio(position, skipped=_skipped, avoid=avoid)

        # Whatever actually produced the trio is the "effective" variety — a
        # boundary/within lane that found nothing degrades to tightest, and the
        # anti-run cursor should reflect that.
        effective = variety if trio is not None else "tightest"

        # Tightest lane (and the fallback for an empty boundary/within lane):
        # Claude-powered selection when enabled, else the algorithmic tightest.
        if trio is None and self._generator is not None and _c("smart_matchup_enabled") == 1.0:
            try:
                from .smart_matchup_generator import SwipeDecision as SD
                history = [SD(winner_id=s.winner_id, loser_id=s.loser_id) for s in self._swipes]
                trio = self._generator.generate_next_trio(
                    players=pool,
                    swipe_history=history,
                    position_filter=position,
                    skipped_player_ids=_skipped,
                )
            except Exception:
                trio = None
        if trio is None:
            trio = self._algorithmic_trio(pool, position=position, avoid=avoid)

        self._trio_last_variety = effective
        self._remember_trio(trio)
        return trio

    # ── Trio variety helpers ─────────────────────────────────────────────
    def _trio_avoid_ids(self) -> set:
        """Player ids from the last `trio_repeat_avoid` served trios."""
        n = int(_c("trio_repeat_avoid"))
        if n <= 0 or not self._recent_trios:
            return set()
        avoid: set = set()
        for s in self._recent_trios[-n:]:
            avoid |= s
        return avoid

    def _remember_trio(self, trio: MatchupTrio) -> None:
        """Record a served trio's id-set for anti-repeat."""
        self._recent_trios.append(
            frozenset({trio.player_a.id, trio.player_b.id, trio.player_c.id})
        )
        cap = max(6, int(_c("trio_repeat_avoid")) + 3)
        if len(self._recent_trios) > cap:
            self._recent_trios = self._recent_trios[-cap:]

    def _pick_trio_variety(self, position: Optional[str]) -> str:
        """Weighted choice of trio strategy, avoiding an immediate repeat.

        Overall mode (position=None) has no positional bands, so only the
        tightest (position-agnostic) strategy applies.
        """
        if position is None:
            return "tightest"
        w_b = max(0.0, _c("trio_boundary_rate"))
        w_w = max(0.0, _c("trio_within_tier_rate"))
        w_t = max(0.0, 1.0 - w_b - w_w)
        choices = {k: v for k, v in
                   (("boundary", w_b), ("within_tier", w_w), ("tightest", w_t))
                   if v > 0.0}
        if not choices:
            return "tightest"
        # Anti-run: drop the previous strategy when an alternative remains.
        if self._trio_last_variety in choices and len(choices) > 1:
            alt = {k: v for k, v in choices.items() if k != self._trio_last_variety}
            if alt:
                choices = alt
        total = sum(choices.values())
        r = random.random() * total
        upto = 0.0
        for k, v in choices.items():
            upto += v
            if r <= upto:
                return k
        return "tightest"

    def _within_tier_trio(
        self,
        position: Optional[str],
        skipped: Optional[set] = None,
        avoid: Optional[set] = None,
    ) -> Optional[MatchupTrio]:
        """Compare the TOP and BOTTOM of the same tier (plus a middle) to nail
        down intra-tier ordering. Rotates through tiers via a cursor so
        successive within-tier trios cover different bands. Returns None when no
        tier currently holds >= 3 players (caller falls back to tightest)."""
        if position is None:
            return None
        _skip = skipped or set()
        _avoid = avoid or set()
        full = [p for p in self._pool(position) if p.id not in _skip]
        if len(full) < 3:
            return None
        elo = self._compute_elo(full)
        stats = self._compute_stats(full)
        try:
            self.tier_bands_for(position, self._scoring_format)
        except Exception:
            return None

        by_tier: dict = {t: [] for t in ORDERED_TIERS}
        for p in full:
            t = self.tier_for_elo(elo[p.id], position, self._scoring_format)
            if t in by_tier:
                by_tier[t].append(p)

        order = ORDERED_TIERS
        n = len(order)
        for off in range(n):
            tier = order[(self._within_tier_cursor + off) % n]
            members = by_tier.get(tier, [])
            if len(members) < 3:
                continue
            # Prefer members not recently seen; relax if that drops below 3.
            fresh = [p for p in members if p.id not in _avoid]
            picks = fresh if len(fresh) >= 3 else members
            picks.sort(key=lambda p: elo[p.id], reverse=True)  # top → bottom
            top, bottom = picks[0], picks[-1]
            interior = picks[1:-1]
            # Middle = least-compared interior member (freshest signal).
            interior.sort(key=lambda p: (len(stats[p.id]["compared"]), -elo[p.id]))
            middle = interior[0] if interior else picks[1]
            self._within_tier_cursor = (self._within_tier_cursor + off + 1) % n
            return MatchupTrio(
                player_a=top, player_b=middle, player_c=bottom,
                reasoning=f"Within-tier spread: {tier}",
            )
        return None

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

    def comparison_counts(self) -> dict[str, int]:
        """Per-player count of unique opponents faced in ranking swipes.

        Consumed by the trade layer (Tier 1 confidence shrinkage) to shrink
        under-sampled personal Elo toward consensus. Pure read: delegates to
        the memoized _compute_stats over the full pool — no ranking math is
        touched and repeat calls at the same _version are O(pool).
        """
        stats = self._compute_stats(list(self._players.values()))
        return {pid: len(s["compared"]) for pid, s in stats.items()}

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
        # INIT-03 memo: return the cached ratings when neither the ranking
        # state (_version) nor the pool has changed since the last full
        # compute. The returned object is shared by reference (identity is
        # intentional — see AC-1); all current callers treat the result as
        # read-only (audited: get_rankings, _algorithmic_trio, apply_reorder).
        cache_key = tuple(p.id for p in pool)
        if (
            self._elo_cache is not None
            and self._elo_cache_version == self._version
            and self._elo_cache_key == cache_key
        ):
            return self._elo_cache

        pool_ids = {p.id for p in pool}
        # Seed each player's starting ELO.  Manual overrides (from tier saves
        # or drag-and-drop reorders) are the user's EXPLICIT ranking — once
        # set, they pin the player's ELO and historical swipes do not move
        # them. (Previous behavior re-applied every swipe on top of the
        # override, which silently dragged tier-placed players away from
        # where the user put them. For a user with many past trios swipes,
        # tier saves became decorative — the round-trip broke and chips
        # appeared in unexpected tiers after refresh.)
        ratings: dict[str, float] = {}
        for p in pool:
            if p.id in self._elo_overrides:
                ratings[p.id] = self._elo_overrides[p.id]
            else:
                ratings[p.id] = self._seed.get(p.id, self.ELO_INITIAL)

        elo_k = _c("elo_k")
        override_ids = self._elo_overrides  # dict — `in` is O(1)

        # Regular ranking swipes — full K factor.
        # Skip the rating update for any pid that has an override: the user
        # has explicitly placed them via tiers/reorder and wants that value
        # to stick. The OTHER side of the swipe (if not overridden) still
        # evolves against the overridden player's anchor ELO, which is the
        # right behaviour: a non-tier-placed player who beat a tier-elite
        # player should still gain ELO.
        for s in self._swipes:
            w, l = s.winner_id, s.loser_id
            if w not in pool_ids or l not in pool_ids:
                continue
            ra, rb  = ratings[w], ratings[l]
            ea       = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            if w not in override_ids:
                ratings[w] += elo_k * (1.0 - ea)
            if l not in override_ids:
                ratings[l] += elo_k * (0.0 - (1.0 - ea))

        # Trade-decision swipes — reduced K factor (softer signal).
        # Same anchoring rule as above.
        for s, k in self._trade_swipes:
            w, l = s.winner_id, s.loser_id
            if w not in pool_ids or l not in pool_ids:
                continue
            ra, rb  = ratings[w], ratings[l]
            ea       = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            if w not in override_ids:
                ratings[w] += k * (1.0 - ea)
            if l not in override_ids:
                ratings[l] += k * (0.0 - (1.0 - ea))

        self._elo_cache = ratings
        self._elo_cache_version = self._version
        self._elo_cache_key = cache_key
        return ratings

    def _compute_stats(self, pool: list[Player]) -> dict[str, dict]:
        # INIT-03 memo: same (_version, pool) keying as _compute_elo. The
        # returned dict contains mutable sets ("compared"); all current callers
        # are read-only (audited: get_rankings, _tiered_pool, _tier_info,
        # _algorithmic_trio), so the cached object is shared by reference.
        cache_key = tuple(p.id for p in pool)
        if (
            self._stats_cache is not None
            and self._stats_cache_version == self._version
            and self._stats_cache_key == cache_key
        ):
            return self._stats_cache

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

        self._stats_cache = stats
        self._stats_cache_version = self._version
        self._stats_cache_key = cache_key
        return stats

    def _boundary_trio(
        self,
        position: Optional[str],
        skipped: Optional[set] = None,
        avoid: Optional[set] = None,
    ) -> Optional[MatchupTrio]:
        """Lever A — build a trio that straddles a value-band boundary.

        Unlike `_algorithmic_trio` (tightest LOCAL trio) and the top-24 tiered
        pool, this deliberately reaches into the FULL position pool to pair a
        player sitting just *below* a tier edge against one just *above* it —
        the comparison that lets a genuinely under/over-rated player cross a
        band (and move value). Returns None when no contested edge exists
        (e.g. single-tier pool, position=None/Overall), so the caller can fall
        back to the normal selectors.
        """
        if position is None:
            return None  # Overall mode has no single positional band set
        _skip = skipped or set()
        _avoid = avoid or set()
        full = [p for p in self._pool(position) if p.id not in _skip]
        if len(full) < 3:
            return None

        elo   = self._compute_elo(full)
        stats = self._compute_stats(full)
        try:
            bands = self.tier_bands_for(position, self._scoring_format)
        except Exception:
            return None

        margin = _c("trio_boundary_margin")
        best: Optional[tuple] = None
        best_score = float("inf")

        # Each adjacent tier pair shares a crossing point at the UPPER tier's
        # low edge: elo >= upper.lo ⇒ upper tier, else the lower tier.
        for upper, lower in zip(ORDERED_TIERS, ORDERED_TIERS[1:]):
            band = bands.get(upper)
            if not band:
                continue
            edge = band[0]
            below = [p for p in full if edge - margin <= elo[p.id] < edge]
            above = [p for p in full if edge <= elo[p.id] <= edge + margin]
            if not below or not above:
                continue

            # Candidate = freshest below-edge player (its tier is most in doubt).
            # Recently-seen players sort last (anti-repeat) but stay eligible.
            below.sort(key=lambda p: (p.id in _avoid, len(stats[p.id]["compared"]), -elo[p.id]))
            cand = below[0]
            # Opponent = above-edge player, preferring not-recent, then
            # uncompared-with-candidate, then fresher, then closest to the edge.
            above.sort(key=lambda p: (
                p.id in _avoid,
                cand.id in stats[p.id]["compared"],
                len(stats[p.id]["compared"]),
                elo[p.id] - edge,
            ))
            opp = above[0]
            # Third = fresh, not-recent player nearest the edge (any tier).
            rest = [p for p in full if p.id not in (cand.id, opp.id)]
            if not rest:
                continue
            rest.sort(key=lambda p: (p.id in _avoid, len(stats[p.id]["compared"]), abs(elo[p.id] - edge)))
            third = rest[0]

            already = int(opp.id in stats[cand.id]["compared"])
            recent = sum(1 for p in (opp, cand, third) if p.id in _avoid)
            total_cmp = sum(len(stats[p.id]["compared"]) for p in (opp, cand, third))
            score = recent * 200 + already * 100 + total_cmp  # fresher/uncompared/unseen = better
            if score < best_score:
                best_score = score
                best = ((opp, cand, third), upper, lower)

        if best is None:
            return None
        (a, b, c), upper, lower = best
        return MatchupTrio(
            player_a=a, player_b=b, player_c=c,
            reasoning=f"Boundary probe: {lower} vs {upper}",
        )

    def _algorithmic_trio(
        self,
        pool: list[Player],
        position: Optional[str] = None,
        avoid: Optional[set] = None,
    ) -> MatchupTrio:
        """Pick 3 adjacent players in Elo order that haven't all been compared.

        When position is None (cross-position / Overall mode), a diversity
        bonus is applied to prefer trios spanning 2+ positions. `avoid` (players
        served in recent trios) is strongly penalised so the same faces don't
        recur, but stays eligible if the pool is too small to avoid them.
        """
        _avoid       = avoid or set()
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
                    # Anti-repeat: heavily penalise players from recent trios.
                    repeat_penalty = sum(
                        200 for p in (p1, p2, p3) if p.id in _avoid
                    )
                    score = spread + existing * 50 + freshness_penalty + diversity_bonus + repeat_penalty
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

    def apply_anchor(self, player_id: str, target_elo: float):
        """
        Pin one player's Elo from a pick-anchor statement (anchor wizard:
        "worth 2 firsts" → a target Elo computed by the caller).

        Same authoritative-override semantics as apply_tiers — the override
        survives swipe replay (_compute_elo skips overridden ids) and the
        caller persists it via save_tier_overrides. Returns the Player so
        the route can report position/tier, or None when the id isn't in
        the pool.
        """
        player = next((p for p in self._pool(None) if p.id == player_id), None)
        if player is None:
            return None
        self._elo_overrides[player_id] = float(target_elo)
        self._version += 1
        return player

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
