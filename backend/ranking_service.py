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
# Pick-value tier ladder (2026-07-12, #117 — 8 tiers) — tier keys read
# directly in draft-pick terms; each tier's floor is a rung of the anchor/pick
# Elo ladder (see tier_config.json _calibration +
# docs/cross-client-invariants.md).
ORDERED_TIERS: tuple[str, ...] = (
    "firsts_4plus", "firsts_3", "firsts_2", "first_1",
    "second", "third", "fourth", "waivers",
)


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
    # Cross-position tier check (#132): a trio of SAME-TIER players from
    # DIFFERENT positions — the comparison the cross-position trade finder
    # leans on. Served only once the user has met all four positional
    # thresholds (see _trade_unlocked). Deliberately a small share; 0 = off.
    "trio_cross_pos_rate":        0.15,
    # Don't reuse a player who appeared in the last N served trios (anti-repeat;
    # fixes "2 of the same players 10 trios in a row"). Relaxes gracefully
    # (oldest-seen first) when the pool is too small to honour it. Raised
    # 3 → 8 (FB #97): 3 was too short to stop the top value cluster recurring.
    "trio_repeat_avoid":          8.0,
    # Decline-reason capture (docs/plans/decline-reason-capture/SPEC.md §4).
    # 1.0 = ON (default): a reasoned pass writes Elo only when the user's
    # reason actually asserts "my side is worth more" — see
    # pass_reason_writes_elo below. 0.0 = OFF: every reasoned pass writes Elo
    # exactly as today's unreasoned pass does, i.e. the deploy-free rollback
    # lever for the one part of this feature that touches ranking math. Read
    # ONLY on the reasoned-pass path; /api/trades/swipe never consults it.
    "pass_reason_elo_suppression": 1.0,
    # ── Board-override pins (docs/reviews/2026-08-18-valuation-age-audit.md) ──
    # A tier/reorder save writes an Elo OVERRIDE that pins a player: _compute_elo
    # seeds them from the override and skips every rating update. Two knobs undo
    # the two ways that pin used to work against the user. Both at 0.0 restores
    # the pre-2026-08-18 behaviour exactly (pinned by test_override_pin_unpin).
    #
    # pin_exclude_comparisons — F1. comparison_counts() feeds the trade layer's
    #   confidence shrinkage (trade_service._shrink_user_elo), whose weight
    #   w = n/(n+n0) is DIRECTION-BLIND. Because a pinned player's Elo cannot
    #   move, every extra comparison only raised w and dragged the effective
    #   trade value further toward the pin — voting a pinned player DOWN made
    #   the engine value him MORE (+12.5% on the audited case). 1.0 = count only
    #   the comparisons that actually moved the player's Elo. 0.0 = kill.
    "pin_exclude_comparisons":    1.0,
    # pin_tier_bounded — TIER-BOUNDED VOTING (2026-08-18, operator design call;
    #   supersedes F2 below). A pin is no longer a freeze and no longer
    #   something a later swipe destroys: it is a permanent TIER constraint.
    #   The pinned Elo names the tier the user placed the player in
    #   (tier_for_elo), and the player's rating then evolves from votes
    #   normally, CLAMPED to that tier's band (tier_bands_for /
    #   tier_config.json). Bands are 165-205 Elo wide, so there is real room to
    #   re-rank inside a tier while "nothing massive across a tier" holds.
    #   The clamp is derived at compute time from the pinned value itself, so
    #   all 2,735 pre-existing pins are covered with no data write and no
    #   migration. A pin BELOW the lowest band (tier_for_elo -> None: the #161
    #   demotion Elo 1100 and the anchor "no value" answer) has no band and
    #   stays frozen — those are deliberate "unranked, pending placement"
    #   markers and a vote must not resurrect them. A pin sitting in a GAP
    #   between two bands, or above the top band's max (apply_reorder permutes
    #   raw seed Elos, which do not have to land inside a band), widens the
    #   clamp to contain itself — min(lo, pin) / max(hi, pin) — so a player
    #   with zero votes can never be moved by the clamp alone.
    #   1.0 = on (default), 0.0 = kill (pins freeze again, exactly as before).
    "pin_tier_bounded":           1.0,
    # pin_unpin_on_newer_swipe — F2. SUPERSEDED by pin_tier_bounded and
    #   therefore defaulted OFF (was 1.0 for a few hours on 2026-08-18). Full
    #   release is no longer the model: a pin is a durable band constraint, not
    #   something that expires on the next swipe. Kept, and still functional,
    #   as the revert path to Phase 0 behaviour — set pin_tier_bounded=0 and
    #   this to 1 to get it back. When BOTH are on, a released player is
    #   released outright (no clamp), because the F2 contract is that the pin
    #   is gone; tier-bounding only governs pins that are still in force.
    #   1.0 = on, 0.0 = off (the default).
    "pin_unpin_on_newer_swipe":   0.0,
    # pin_legacy_at_epoch — F2 legacy policy. Overrides written before this
    #   change carry no timestamp. 0.0 (default) = an unstamped pin is treated
    #   as PERMANENT — it is never released by a swipe, so no existing board
    #   changes until the user next tiers/reorders that player (which stamps
    #   it). 1.0 = an unstamped pin is treated as written at the epoch, so ANY
    #   recorded swipe — including historical ones — releases it. The 1.0 side
    #   retroactively re-opens every legacy pin on the next Elo compute; it is
    #   an operator decision, not a default. See docs/config-reference.md.
    #   Also SUPERSEDED by pin_tier_bounded: it only qualifies F2, and F2 is
    #   off by default, so this knob is inert unless F2 is turned back on.
    "pin_legacy_at_epoch":        0.0,
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


# Sentinel meaning "written at the beginning of time" — every recorded swipe is
# newer than this, so a pin carrying it is released by any comparison. Used for
# legacy (unstamped) overrides when pin_legacy_at_epoch is on.
_PIN_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_ts(raw: str | None) -> Optional[datetime]:
    """Parse an ISO-8601 stamp to an aware UTC datetime, or None.

    Both sources are written by `datetime.now(timezone.utc).isoformat()`
    (SwipeDecision.timestamp in-memory, `database._now()` for the persisted
    `swipe_decisions.created_at`), so they are directly comparable. Naive
    strings are assumed UTC rather than dropped: an unparseable or missing
    stamp returns None, and every caller treats None as "no information",
    which never releases a pin.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Decline-reason capture — which passes are allowed to move Elo (SPEC §4)
# ---------------------------------------------------------------------------
# Today EVERY pass fires record_trade_signal(winner=give, loser=receive),
# i.e. it asserts "I value my players more than theirs". Once the user
# tells us WHY they passed, that assertion is true for exactly one answer:
#
#   value_giving  "Giving up too much"  -> KEEP.   The user did say their
#                                                  side is worth more.
#   value_getting "Getting too much"    -> SUPPRESS. The user said the
#                                                  OPPOSITE; writing the
#                                                  usual signal inverts it.
#   fit_*, other*, and layer-1-only     -> SUPPRESS. No value claim was
#   value / fit / other                            made at all.
#
# The `other_player_*` pair added 2026-08-19 is the near-miss worth naming:
# `other_player_keep` ("won't trade one of my players") LOOKS adjacent to
# `value_giving`, but it is attachment, not a market-value assertion — the
# user is saying "not this player, at any price", which is the opposite of a
# claim about price. Both player codes suppress, and they do so for free:
# PASS_REASON_ELO_KEEP is an allow-list, so a new code suppresses unless
# somebody deliberately adds it here.
#
# This is the only ranking-math change in the feature and it is knob-gated
# both ways: `pass_reason_elo_suppression` = 0 restores today's behavior for
# every code without a deploy.

#: The one code whose pass still asserts a valuation. A frozenset (not an
#: `== "value_giving"`) so extending the taxonomy is a one-line change here
#: rather than an edit inside the route.
PASS_REASON_ELO_KEEP: frozenset[str] = frozenset({"value_giving"})


def pass_reason_writes_elo(code: str | None) -> bool:
    """Should a pass carrying reason/detail `code` write an Elo signal?

    `code` is the MOST SPECIFIC code known at the moment of the write — the
    layer-2 detail when there is one, else the layer-1 reason. With the knob
    off this always returns True, which is exactly the pre-feature behavior
    (every pass writes Elo, whatever the user said).
    """
    if _c("pass_reason_elo_suppression") < 0.5:
        return True
    return bool(code) and code in PASS_REASON_ELO_KEEP


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

    # ── Board-evidence unlock bars (A-16 / A-17, P1-7, 2026-08-11) ──────────
    # The trio bar above is counted in SWIPES. The two bars below are counted
    # in BOARD OVERRIDES (users.tier_overrides), because the anchor and manual
    # lanes produce no swipes at all — see board_override_count().
    #
    # ANCHOR_UNLOCK_MIN — the anchor method's bar. Equal to the trio bar
    # (10 × 4 positions) so the product has ONE number to explain.
    # Deliberately NOT per-position: the Pick Anchor wizard's default scope is
    # a single cross-position, value-descending queue (#133,
    # PickAnchorScreen.tsx), so a 4-position completeness rule would import a
    # shape that surface does not have.
    ANCHOR_UNLOCK_MIN = 40

    # MANUAL_UNLOCK_MIN — the manual method's bar. Set equal to the other two
    # for the same one-number-to-explain reason.
    #
    # *** ASSUMPTION AWAITING OPERATOR CONFIRMATION (P1-7, 2026-08-11). ***
    # The VALUE is a product judgement nobody has made yet; the SHAPE (a
    # durable board-evidence count rather than the unconditional `True` this
    # replaces) follows D-P1-10's governing principle that every ranking
    # method unlocks on evidence of real ranking work. 40 is a placeholder
    # chosen for consistency, not a decided number. Note that with today's
    # client payload — ManualRanksScreen posts the WHOLE visible list on every
    # drag, so one drag writes an override per row — this bar is a floor
    # against "pinned to 'manual' with no board at all", not a strong gate.
    # Making it a strong gate (audit A-17) needs a product decision AND a
    # client payload change, and is P1-8's job, not this item's.
    MANUAL_UNLOCK_MIN = 40

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
        # When each override was written — ISO-8601 UTC, pid-keyed, PARALLEL to
        # _elo_overrides rather than folded into it so the persisted per-format
        # `{pid: elo}` shape (users.tier_overrides) is unchanged. A pid present
        # in _elo_overrides but absent here is a LEGACY pin (written before
        # 2026-08-18); pin_legacy_at_epoch decides what that means. Persisted
        # under the `__OVERRIDE_AT__` sibling key by database.save_tier_overrides.
        self._elo_override_at: dict[str, str] = {}
        # Scoring format this service ranks in — drives which tier_config.json
        # value bands the boundary-probing trio selector reads. Defaults to
        # 1qb_ppr; multi-format callers set it post-construct (like _user_id).
        self._scoring_format = "1qb_ppr"
        # Trio variety state (in-session, per position where relevant). Recent
        # trios drive anti-repeat; the cursors rotate strategy + which tier a
        # within-tier trio calibrates so successive trios feel varied.
        self._recent_trios: list[frozenset] = []      # last-served trio id-sets
        self._trio_last_variety: Optional[str] = None
        # Random start (FB #97): a fixed 0 start meant every rebuilt service
        # (each app session / server restart) aimed its first within-tier trio
        # at ORDERED_TIERS[0] (the top tier), so the same top-cluster faces
        # opened every session. The cursor still rotates deterministically
        # from here.
        self._within_tier_cursor: int = random.randrange(len(ORDERED_TIERS))
        # #132 cross-position lane: separate cursor (same random-start
        # rationale) so cross-position trios rotate tiers independently of
        # the within-tier lane.
        self._cross_pos_cursor: int = random.randrange(len(ORDERED_TIERS))

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
        # {pinned pid: opponents whose RANKING comparison actually changed that
        # player's rating}. Written by _compute_elo alongside _elo_cache (and
        # therefore valid under the same cache key); read by comparison_counts
        # as the definition of a LIVE comparison. Only pinned players are
        # tracked — everyone else's live count is just len(stats["compared"]).
        self._elo_moved: dict[str, set[str]] = {}
        self._stats_cache: Optional[dict[str, dict]] = None
        self._stats_cache_version: int = 0
        self._stats_cache_key: Optional[tuple] = None
        # comparison_counts() memo — same _version keying, no pool key because
        # it always runs over the full player set.
        self._conf_cache: Optional[dict[str, int]] = None
        self._conf_cache_version: Optional[tuple] = None

    # ------------------------------------------------------------------
    # Board-override pins
    # ------------------------------------------------------------------

    @staticmethod
    def _pin_cfg_key() -> tuple:
        """The three pin knobs, as a cache-key component.

        `_compute_elo` / `comparison_counts` memoize on `_version`, which only
        moves on a state mutation — a live `PUT /api/admin/config` would not
        bump it, so a kill switch pulled in an incident would not take effect
        on warm sessions until the user next swiped. Folding the knobs into the
        key makes the kill immediate.
        """
        return (_c("pin_exclude_comparisons"),
                _c("pin_unpin_on_newer_swipe"),
                _c("pin_legacy_at_epoch"),
                _c("pin_tier_bounded"))

    def _pin(self, pid: str, elo: float, at: Optional[str] = None) -> None:
        """Write an Elo override and stamp WHEN it was written.

        Every override write goes through here so `_elo_override_at` can never
        drift from `_elo_overrides` — an unstamped entry means "legacy", and a
        mutator that forgot to stamp would silently make a brand-new pin
        unreleasable. `at` lets one bulk save share a single stamp.
        """
        self._elo_overrides[pid] = float(elo)
        self._elo_override_at[pid] = at or datetime.now(timezone.utc).isoformat()

    def _unpin(self, pid: str) -> None:
        """Drop an override and its stamp together."""
        self._elo_overrides.pop(pid, None)
        self._elo_override_at.pop(pid, None)

    def _pin_release(self, pool_ids: set[str]) -> dict[str, datetime]:
        """Which pinned players a newer ranking swipe has RELEASED, and from when.

        Returns {pid: released_from} for every override that a swipe has
        unpinned. `released_from` is the pin's own timestamp: the pin stays as
        the player's starting rating and only swipes STRICTLY newer than it are
        applied on top. That is the point of the fix — the tier placement
        already summarises everything the user said before it, so replaying
        pre-pin history would resurrect the very swipes the placement
        superseded. Pins absent from the result stay frozen.

        Only RANKING swipes (`_swipes`) can trigger a release. A trade like/pass
        is an indirect, low-K signal about a whole package; letting one destroy
        a deliberate tier placement would be a much bigger product change than
        the defect warrants. Once a pin IS released, newer trade swipes do
        apply — the player is simply un-pinned from that moment on.
        """
        if not self._elo_overrides or _c("pin_unpin_on_newer_swipe") != 1.0:
            return {}

        legacy_at_epoch = _c("pin_legacy_at_epoch") == 1.0
        pin_at: dict[str, datetime] = {}
        for pid in self._elo_overrides:
            if pid not in pool_ids:
                continue
            stamp = _parse_ts(self._elo_override_at.get(pid))
            if stamp is None:
                if not legacy_at_epoch:
                    continue          # unstamped + policy off ⇒ permanent pin
                stamp = _PIN_EPOCH
            pin_at[pid] = stamp
        if not pin_at:
            return {}

        released: dict[str, datetime] = {}
        for s in self._swipes:
            for pid in (s.winner_id, s.loser_id):
                if pid not in pin_at or pid in released:
                    continue
                other = s.loser_id if pid == s.winner_id else s.winner_id
                if other not in pool_ids:
                    continue          # swipe is skipped by _compute_elo anyway
                ts = _parse_ts(s.timestamp)
                if ts is not None and ts > pin_at[pid]:
                    released[pid] = pin_at[pid]
        return released

    def _pin_bounds(
        self,
        pool_ids: set[str],
        released: dict[str, datetime],
    ) -> dict[str, tuple[float, float]]:
        """Per-pin Elo band for TIER-BOUNDED voting — {pid: (lo, hi)}.

        The operator's design call (2026-08-18): a deliberately placed player
        should still be re-rankable *by voting*, but only inside the tier he
        was placed in — "some adjustment is expected, but nothing massive
        across a tier". So the pinned Elo is read as a tier label
        (`tier_for_elo`) and the player's rating is clamped to that tier's band
        (`tier_bands_for`, i.e. `tier_config.json`) after every update. Bands
        are 165-205 Elo wide, which is genuine room to move.

        Nothing is written anywhere: the band is derived at compute time from
        the pinned value the board already stores, so every pre-existing pin is
        covered without a migration or a backfill.

        Two populations are deliberately absent from the result and therefore
        stay FROZEN, exactly as before this change:

        * **Pins with no band** — `tier_for_elo` returns None below the lowest
          band (1150 in every cell). That is where `DEMOTED_ELO` (#161, a
          player explicitly passed over in a Quick Set save) and the anchor
          wizard's "no value" answer put people. Those are deliberate
          "unranked, pending placement" markers, not tier placements; a stray
          comparison must not drag one back onto the board.
        * **Pins F2 has released** — if `pin_unpin_on_newer_swipe` is turned
          back on, a released pin is *gone*, so the player evolves unclamped.
          Tier-bounding only governs pins still in force. (F2 is off by
          default; this is the interaction rule, not the normal path.)

        The band is widened to contain the pin itself — `min(lo, pin)` /
        `max(hi, pin)`. `tier_config.json` has small GAPS between bands (e.g.
        1576-1579 sits between `second`.max and `first_1`.min) and the top
        band's max is finite, while `apply_reorder` permutes raw seed Elos that
        need not land inside any band. Without the widening, a pinned player
        with zero votes could be silently moved by the first vote that touched
        him, purely by the clamp snapping him into the band; with it, a player
        can never be pushed further from his own pin than the band already is.
        """
        if not self._elo_overrides or _c("pin_tier_bounded") != 1.0:
            return {}
        return self._placement_bands(pool_ids, released)

    def _placement_bands(
        self,
        pool_ids: set[str],
        released: dict[str, datetime],
    ) -> dict[str, tuple[float, float]]:
        """The band derivation itself, with no knob attached — {pid: (lo, hi)}.

        Split out of `_pin_bounds` (2026-08-19, D-085) because a SECOND
        consumer needs the same answer under a different knob: the trade engine
        clamps a placed player's *priced* Elo to this band
        (`trade_service.placement_tier_clamp`), which is the voting rule above
        applied one layer further out. Both consumers must agree on what "the
        tier the user placed him in" means, so exactly one function computes
        it. Every rule documented on `_pin_bounds` — the tier lookup, the
        no-band skip, the widening to contain the pin — lives here.
        """
        bounds: dict[str, tuple[float, float]] = {}
        bands_by_pos: dict[Optional[str], dict[str, tuple[float, float]]] = {}
        for pid, pin in self._elo_overrides.items():
            if pid not in pool_ids or pid in released:
                continue
            player = self._players.get(pid)
            pos = player.position if player else None
            bands = bands_by_pos.get(pos)
            if bands is None:
                bands = bands_by_pos[pos] = self.tier_bands_for(
                    pos, self._scoring_format)
            tier = self.tier_for_elo(pin, pos, self._scoring_format)
            if tier is None or tier not in bands:
                continue                      # unranked pin -> stays frozen
            lo, hi = bands[tier]
            bounds[pid] = (min(lo, pin), max(hi, pin))
        return bounds

    def placement_bands(self) -> dict[str, tuple[float, float]]:
        """Per-player Elo band for every player this user actually PLACED.

        {pid: (lo, hi)} over the whole player pool, for pins still in force
        that sit in a tier band — the public read of `_placement_bands`,
        consumed by the trade layer as `placements` (see
        `trade_service._shrink_user_elo` and the `placement_tier_clamp` knob).

        A manual tier save or drag-reorder is the strongest signal the product
        accepts: an explicit ASSERTION of value, not a sample. The shrinkage
        weight `w = n/(n+n0)` cannot see assertions — it counts comparisons —
        so a deliberately placed player with few head-to-head votes was priced
        toward consensus regardless of where the user put him. This map is what
        lets the trade engine honour the placement while keeping the shrinkage
        that protects against fake divergence.

        Deliberately NOT gated on `pin_tier_bounded`: that knob governs how
        VOTES move a pin, and the two questions are independent. With
        tier-bounded voting off a pin is a total freeze, so `user_elo` equals
        the pin exactly and the blend still drags the priced value clean across
        tiers — precisely the case the clamp exists for. The trade-side kill
        switch is `placement_tier_clamp`.

        Two populations are absent, exactly as in `_pin_bounds`: pins F2
        (`pin_unpin_on_newer_swipe`) has released, which are no longer
        placements in force; and pins below the lowest band (the #161 demotion
        Elo and the anchor "no value" answer at 1100), which `tier_for_elo`
        maps to None. The latter are "unranked, pending placement" markers
        rather than tier placements — clamping a player's trade value into a
        sub-1150 non-band would price him at ~nothing on the strength of a
        marker the user never meant as a valuation.

        Empty dict when the user has placed nobody, which is the whole
        population of boards built purely by swiping.
        """
        if not self._elo_overrides:
            return {}
        pool_ids = set(self._players)
        return self._placement_bands(pool_ids, self._pin_release(pool_ids))

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
        fit_mult: float = 1.0,
    ) -> None:
        """
        Apply a soft ELO update from a trade decision.

        decision='like'  (Interested): user values the received players over the
                          given players → winner_ids=receive, loser_ids=give.
                          Uses TRADE_K_LIKE (~25% of a ranking swipe).

        decision='pass': user preferred keeping their players → winner_ids=give,
                          loser_ids=receive. Weaker signal, uses TRADE_K_PASS
                          (~12% of a ranking swipe).

        fit_mult: fit-congruence weight (D-060) on the looked-up K — how
                  surprising this swipe is given the user's window, computed
                  by the caller via trade_service.fit_congruence_mult(). A
                  rebuilder passing a fairly-priced vet is making a WINDOW
                  statement, not a value one, so that pass is discounted;
                  the same rebuilder LIKING the vet is weighted at full K.
                  Default 1.0 = the pre-D-060 behavior exactly. Callers that
                  also persist the swipe (save_trade_swipes) must apply the
                  same multiplier to the stored k_factor, or the DB replay
                  in _compute_elo will disagree with this in-memory state.

        For multi-player sides (e.g. 2-for-1 trades) every winner is paired
        against every loser, same as the ranking engine's pairwise decomposition.
        """
        k = _c("trade_k_like") if decision == "like" else _c("trade_k_pass")
        k *= fit_mult
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
        scoped: bool = False,
    ) -> MatchupTrio:
        """Return the most informative next 3 players to rank.

        skipped_player_ids (Agent 1): persistent "I don't know this player"
        exclusions. Players in this set are filtered out of the candidate pool
        so they never appear in future trios for this user + format.

        scoped (rookie-draft M2): the caller has narrowed the candidate set via
        `skipped_player_ids` (rookie scope reuses that channel so no new
        parameter threads through the selectors). The ONE lane that channel
        cannot constrain is `cross_pos`, which reaches across the FULL pool by
        design — so it is dropped from the variety table. Default False keeps
        every existing caller byte-identical.
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
        variety = self._pick_trio_variety(position, scoped=scoped)

        trio: Optional[MatchupTrio] = None
        if variety == "boundary":
            trio = self._boundary_trio(position, skipped=_skipped, avoid=avoid)
        elif variety == "within_tier":
            trio = self._within_tier_trio(position, skipped=_skipped, avoid=avoid)
        elif variety == "cross_pos":
            # #132 — reaches across the FULL pool (all positions), like the
            # boundary lane reaches past the tiered pool. Post-unlock only
            # (gated in _pick_trio_variety), so serving off-position faces
            # under a positional request can't stall pre-unlock progress.
            trio = self._cross_position_trio(skipped=_skipped, avoid=avoid)

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

    def _last_seen_at(self, player_id: str) -> int:
        """Index in _recent_trios where the player last appeared (-1 = never).
        Higher = more recently seen. Lets avoid-relaxation degrade gracefully:
        re-admit the LONGEST-unseen players first instead of all at once."""
        for i in range(len(self._recent_trios) - 1, -1, -1):
            if player_id in self._recent_trios[i]:
                return i
        return -1

    def _trade_unlocked(self) -> bool:
        """All four positional interaction thresholds met — the trio-method
        trade-finder unlock. Gates the #132 cross-position lane. The service
        only sees interaction counts, so users who unlocked via the tiers/
        manual methods stay gated here until their swipe counts catch up:
        a conservative under-serve, never a pre-unlock leak."""
        return all(
            self._interactions.get(p, 0) >= self.POSITION_THRESHOLDS.get(p, 10)
            for p in ("QB", "RB", "WR", "TE")
        )

    def _pick_trio_variety(self, position: Optional[str],
                           scoped: bool = False) -> str:
        """Weighted choice of trio strategy, avoiding an immediate repeat.

        Overall mode (position=None) has no positional bands, so only the
        tightest (position-agnostic) strategy applies.

        `scoped` (M2 lane audit): drop `cross_pos`. Every other lane honours
        the caller's `skipped_player_ids` exclusion, but `_cross_position_trio`
        buckets the FULL pool across positions, so under a scoped request it
        would serve players the user is not being shown.
        """
        if position is None:
            return "tightest"
        w_b = max(0.0, _c("trio_boundary_rate"))
        w_w = max(0.0, _c("trio_within_tier_rate"))
        # #132 — cross-position lane joins the mix only post-unlock; its
        # share comes out of the tightest remainder, so the boundary /
        # within-tier calibration lanes keep their tuned rates.
        w_x = (0.0 if scoped
               else max(0.0, _c("trio_cross_pos_rate")) if self._trade_unlocked()
               else 0.0)
        w_t = max(0.0, 1.0 - w_b - w_w - w_x)
        choices = {k: v for k, v in
                   (("boundary", w_b), ("within_tier", w_w),
                    ("cross_pos", w_x), ("tightest", w_t))
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
            # Prefer members not recently seen. Relax PARTIALLY when that
            # drops below 3: re-admit only the longest-unseen avoided members
            # (FB #97 — the old all-or-nothing relax re-served the exact same
            # trio whenever a small tier was fully inside the avoid window).
            picks = [p for p in members if p.id not in _avoid]
            if len(picks) < 3:
                stale_first = sorted(
                    (p for p in members if p.id in _avoid),
                    key=lambda p: self._last_seen_at(p.id),
                )
                picks += stale_first[:3 - len(picks)]
            picks.sort(key=lambda p: elo[p.id], reverse=True)  # top → bottom
            # Randomise WHICH extremes get probed (FB #97): always taking the
            # single max/min-Elo member put the tier's #1 (e.g. the top RB) in
            # every within-tier trio for that tier. Still a top-vs-bottom
            # spread — just sampled from the top/bottom two.
            top = random.choice(picks[:2]) if len(picks) >= 4 else picks[0]
            bottom = random.choice(picks[-2:]) if len(picks) >= 4 else picks[-1]
            interior = [p for p in picks if p.id not in (top.id, bottom.id)]
            # Middle = least-compared interior member (freshest signal).
            interior.sort(key=lambda p: (len(stats[p.id]["compared"]), -elo[p.id]))
            middle = interior[0]
            self._within_tier_cursor = (self._within_tier_cursor + off + 1) % n
            return MatchupTrio(
                player_a=top, player_b=middle, player_c=bottom,
                reasoning=f"Within-tier spread: {tier}",
            )
        return None

    def _cross_position_trio(
        self,
        skipped: Optional[set] = None,
        avoid: Optional[set] = None,
    ) -> Optional[MatchupTrio]:
        """#132 — same-tier players from DIFFERENT positions.

        Post-unlock only (gated in _pick_trio_variety): probes how the user
        values equally-tiered assets across position groups — exactly the
        comparison the cross-position trade finder relies on. Buckets the
        FULL pool by each player's own positional bands (bands are uniform
        by design, but going through each player's position keeps this
        honest if they ever diverge), rotates a cursor over the tiers, and
        serves 3 same-tier players spanning as many positions as possible
        (>= 2). Returns None when no tier holds 3+ members across 2+
        positions — the caller falls back to tightest.
        """
        _skip = skipped or set()
        _avoid = avoid or set()
        full = [p for p in self._pool(None) if p.id not in _skip]
        if len(full) < 3:
            return None
        elo = self._compute_elo(full)
        stats = self._compute_stats(full)

        by_tier: dict = {t: [] for t in ORDERED_TIERS}
        try:
            for p in full:
                t = self.tier_for_elo(elo[p.id], p.position, self._scoring_format)
                if t in by_tier:
                    by_tier[t].append(p)
        except Exception:
            return None

        n = len(ORDERED_TIERS)
        for off in range(n):
            tier = ORDERED_TIERS[(self._cross_pos_cursor + off) % n]
            members = by_tier.get(tier, [])
            if len(members) < 3 or len({p.position for p in members}) < 2:
                continue
            # Anti-repeat with the FB #97 partial-relaxation pattern: prefer
            # unseen members; re-admit only the longest-unseen avoided ones,
            # and never let relaxation collapse the position spread below 2.
            picks = [p for p in members if p.id not in _avoid]
            if len(picks) < 3 or len({p.position for p in picks}) < 2:
                stale_first = sorted(
                    (p for p in members if p.id in _avoid),
                    key=lambda p: self._last_seen_at(p.id),
                )
                for p in stale_first:
                    picks.append(p)
                    if len(picks) >= 3 and len({q.position for q in picks}) >= 2:
                        break
            if len(picks) < 3 or len({p.position for p in picks}) < 2:
                continue
            # One player per position first (up to 3 distinct positions,
            # random position order so the same pairing doesn't headline
            # every serve), freshest (least-compared) within each position;
            # when only 2 positions are present the third slot fills from
            # the remaining picks by freshness.
            by_pos: dict[str, list[Player]] = {}
            for p in picks:
                by_pos.setdefault(p.position, []).append(p)
            for plist in by_pos.values():
                plist.sort(key=lambda p: (len(stats[p.id]["compared"]), -elo[p.id]))
            pos_order = list(by_pos.keys())
            random.shuffle(pos_order)
            chosen: list[Player] = [by_pos[pos][0] for pos in pos_order[:3]]
            if len(chosen) < 3:
                taken = {c.id for c in chosen}
                rest = [p for p in picks if p.id not in taken]
                rest.sort(key=lambda p: (len(stats[p.id]["compared"]), -elo[p.id]))
                chosen += rest[:3 - len(chosen)]
            if len(chosen) < 3:
                continue
            chosen.sort(key=lambda p: elo[p.id], reverse=True)
            self._cross_pos_cursor = (self._cross_pos_cursor + off + 1) % n
            return MatchupTrio(
                player_a=chosen[0], player_b=chosen[1], player_c=chosen[2],
                reasoning=f"Cross-position tier check: {tier}",
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
        """Per-player count of unique opponents whose comparison actually
        MOVED that player's Elo — the player's LIVE comparisons.

        Consumed by the trade layer as `confidence`: it feeds
        `trade_service._shrink_user_elo` (personal Elo blended toward the
        consensus seed with w = n/(n+n0)) and `_value_uncertainty` (per-player
        value half-width, range_base/sqrt(1+n)).

        Why "actually moved" and not "was shown" (pin_exclude_comparisons, F1,
        2026-08-18). The shrinkage weight is direction-BLIND — it reads how
        MUCH you voted, never which way. When a pin was a total freeze, every
        comparison a pinned player was shown only raised w and pulled the
        effective trade value further toward the pin; on the audited board the
        pin sat above consensus, so voting a player DOWN 17 times raised his
        trade value 12.5%.

        Under TIER-BOUNDED voting (pin_tier_bounded) most of those comparisons
        are no longer inert — a pinned player's rating really does move inside
        his tier band — so they are counted again, and the rule NARROWS to the
        genuinely inert residue:

        * a player clamped at a band edge with the vote still pushing him
          further out (the update changes nothing, so it is not evidence), and
        * a pin with no tier band at all (below the lowest band: the #161
          demotion Elo and the anchor "no value" answer), which stays frozen.

        Keeping the rule in this narrowed form rather than reverting it is what
        makes the value truer: a vote that moved a player is real evidence and
        now counts, while a vote the tier floor swallowed would otherwise raise
        confidence in a number the user was trying to lower — the same
        inversion, one tier down. Reverting it outright would reinstate that
        inversion for exactly the players at a band edge, which is where a user
        who keeps voting someone down ends up.

        `_value_uncertainty` deliberately shares this map rather than keeping
        the raw counts, for the same reason it did before: confidence that came
        from updates which changed nothing is false precision. One knob turns
        both consumers back off together.

        Pure read: `_compute_stats` supplies the base counts and `_compute_elo`
        supplies the live-comparison map (`_elo_moved`); both are memoized on
        the same key, and neither is re-run when warm. Only PINNED players are
        recounted — everyone else's comparisons all move them by definition.
        """
        conf_key = (self._version, self._pin_cfg_key())
        if self._conf_cache is not None and self._conf_cache_version == conf_key:
            return self._conf_cache

        pool = list(self._players.values())
        stats = self._compute_stats(pool)
        counts = {pid: len(s["compared"]) for pid, s in stats.items()}

        if _c("pin_exclude_comparisons") == 1.0 and self._elo_overrides:
            self._compute_elo(pool)          # populates self._elo_moved
            moved = self._elo_moved
            counts.update({pid: len(moved.get(pid, ()))
                           for pid in self._elo_overrides if pid in counts})

        self._conf_cache = counts
        self._conf_cache_version = conf_key
        return counts

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
            # Carry the PERSISTED timestamp. SwipeDecision defaults it to now,
            # which is right for a live swipe and catastrophic for a replay:
            # every historical swipe would look newer than every pin, so a
            # server restart would silently unpin whole boards (F2).
            sd    = SwipeDecision(winner_id=wid, loser_id=lid,
                                  timestamp=row.get("created_at") or "")

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
        cache_key = (tuple(p.id for p in pool), self._pin_cfg_key())
        if (
            self._elo_cache is not None
            and self._elo_cache_version == self._version
            and self._elo_cache_key == cache_key
        ):
            return self._elo_cache

        pool_ids = {p.id for p in pool}
        # Seed each player's starting ELO.  Manual overrides (from tier saves
        # or drag-and-drop reorders) are the user's EXPLICIT ranking, so they
        # are the STARTING rating and, under pin_tier_bounded, also the tier
        # the player is confined to. (The original behaviour re-applied every
        # swipe on top of the override without any bound, which silently
        # dragged tier-placed players away from where the user put them — tier
        # saves became decorative and chips appeared in unexpected tiers after
        # refresh. The fix for that was a total freeze, which then made the
        # vote loop inert; the band is the middle ground.)
        ratings: dict[str, float] = {}
        for p in pool:
            if p.id in self._elo_overrides:
                ratings[p.id] = self._elo_overrides[p.id]
            else:
                ratings[p.id] = self._seed.get(p.id, self.ELO_INITIAL)

        elo_k = _c("elo_k")
        override_ids = self._elo_overrides  # dict — `in` is O(1)
        # F2 (pin_unpin_on_newer_swipe): pins that a LATER ranking swipe has
        # released, mapped to the pin's own timestamp. A released player keeps
        # the pin as their starting rating (set above) but evolves from every
        # swipe newer than it. Empty dict ⇒ the pre-fix "pins are permanent"
        # behaviour, so the knob at 0.0 is byte-identical.
        released = self._pin_release(pool_ids)
        # Tier-bounded voting (pin_tier_bounded, 2026-08-18): {pid: (lo, hi)}
        # for every pin that is still in force and sits in a tier band. Those
        # players DO evolve from votes, clamped to their band. Empty dict =>
        # the pre-2026-08-18 "a pin is a freeze" behaviour, so the knob at 0.0
        # is byte-identical.
        bounds = self._pin_bounds(pool_ids, released)
        # {pinned pid: opponents whose ranking comparison actually changed his
        # rating} — the LIVE comparisons, consumed by comparison_counts().
        moved: dict[str, set[str]] = {}

        def _moves(pid: str, ts: Optional[datetime]) -> bool:
            """Does this swipe update `pid`'s rating?

            Un-pinned players always move. A pinned player moves if a newer
            swipe released him (F2, and then only for swipes strictly newer
            than the pin) or if tier-bounding gave him a band to move inside.
            A pin that is neither released nor banded is frozen.
            """
            if pid not in override_ids:
                return True
            since = released.get(pid)
            if since is not None:
                return ts is not None and ts > since
            return pid in bounds

        def _apply(pid: str, delta: float, other: str, track: bool) -> None:
            """Add `delta` to `pid`'s rating, clamped to his tier band if any.

            A clamped-away update is exactly the case the trade layer must not
            count as evidence: the player is at the edge of the tier the user
            put him in and the vote is pushing him further out, so it moves
            nothing. `track` records only RANKING comparisons, matching the
            base counts in `_compute_stats` (which ignores trade swipes).
            """
            before = ratings[pid]
            after = before + delta
            band = bounds.get(pid)
            if band is not None:
                after = min(max(after, band[0]), band[1])
            if after == before:
                return
            ratings[pid] = after
            if track and pid in override_ids:
                moved.setdefault(pid, set()).add(other)

        # Regular ranking swipes — full K factor.
        # A pinned player's update is bounded (or, for a pin with no tier band,
        # skipped) — the user has explicitly placed them via tiers/reorder and
        # wants that placement to hold, but voting still re-orders them inside
        # it. The OTHER side of the swipe still evolves against the pinned
        # player's anchor ELO, which is the right behaviour: a non-tier-placed
        # player who beat a top-tier player should still gain ELO.
        for s in self._swipes:
            w, l = s.winner_id, s.loser_id
            if w not in pool_ids or l not in pool_ids:
                continue
            ts = _parse_ts(s.timestamp) if released else None
            ra, rb  = ratings[w], ratings[l]
            ea       = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            if _moves(w, ts):
                _apply(w, elo_k * (1.0 - ea), l, True)
            if _moves(l, ts):
                _apply(l, elo_k * (0.0 - (1.0 - ea)), w, True)

        # Trade-decision swipes — reduced K factor (softer signal).
        # Same anchoring rule as above. A trade swipe can never RELEASE a pin
        # (see _pin_release), but it does move an already-released player.
        for s, k in self._trade_swipes:
            w, l = s.winner_id, s.loser_id
            if w not in pool_ids or l not in pool_ids:
                continue
            ts = _parse_ts(s.timestamp) if released else None
            ra, rb  = ratings[w], ratings[l]
            ea       = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            if _moves(w, ts):
                _apply(w, k * (1.0 - ea), l, False)
            if _moves(l, ts):
                _apply(l, k * (0.0 - (1.0 - ea)), w, False)

        self._elo_cache = ratings
        self._elo_cache_version = self._version
        self._elo_cache_key = cache_key
        self._elo_moved = moved
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

            # Candidate = a fresh below-edge player (its tier is most in doubt).
            # Recently-seen players sort last (anti-repeat) but stay eligible.
            # Random pick among the top-2 eligibles (FB #97): edge pools are
            # small, and a deterministic closest-first pick re-served the same
            # 2-3 straddlers every time this edge was probed.
            below.sort(key=lambda p: (p.id in _avoid, len(stats[p.id]["compared"]), -elo[p.id]))
            cand = random.choice(below[:2])
            # Opponent = above-edge player, preferring not-recent, then
            # uncompared-with-candidate, then fresher, then closest to the edge.
            above.sort(key=lambda p: (
                p.id in _avoid,
                cand.id in stats[p.id]["compared"],
                len(stats[p.id]["compared"]),
                elo[p.id] - edge,
            ))
            opp = random.choice(above[:2])
            # Third = fresh, not-recent player nearest the edge (any tier).
            rest = [p for p in full if p.id not in (cand.id, opp.id)]
            if not rest:
                continue
            rest.sort(key=lambda p: (p.id in _avoid, len(stats[p.id]["compared"]), abs(elo[p.id] - edge)))
            third = random.choice(rest[:3])

            already = int(opp.id in stats[cand.id]["compared"])
            recent = sum(1 for p in (opp, cand, third) if p.id in _avoid)
            # random() < 1 breaks integer-score ties between edges randomly —
            # otherwise a fresh board always probed the FIRST tied edge
            # (the top of the ladder, the hottest cluster) on every boundary
            # trio.
            total_cmp = sum(len(stats[p.id]["compared"]) for p in (opp, cand, third))
            score = recent * 200 + already * 100 + total_cmp + random.random()
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

        Returns one of ORDERED_TIERS ('firsts_4plus', 'firsts_3', 'firsts_2',
        'first_1', 'second', 'third', 'fourth', 'waivers'), or None when the
        ELO falls below the lowest band (unranked).

        This is the source of truth for the browser extension's tier badge
        and for anywhere the backend needs to label a player without going
        through the frontend's threshold table.
        """
        if elo is None:
            return None
        bands = cls.tier_bands_for(position, scoring_format)
        # Walk tiers top-down; return the first tier whose lo <= elo. Elo
        # above the top tier's hi still registers as the top tier.
        for tier in ORDERED_TIERS:
            lo, hi = bands[tier]
            if elo >= lo:
                return tier
        return None

    # #161 — demotion target for players explicitly passed over during a
    # Quick Set tier save: below every tier band (the waivers floor is 1150
    # in every format/position cell), so they render UNRANKED — pending
    # placement — rather than keeping a stale higher tier. Same Elo the
    # anchor wizard's "no value" answer pins (server.ANCHOR_NO_VALUE_ELO).
    DEMOTED_ELO = 1100.0

    def apply_tiers(
        self,
        position: Optional[str],
        tiers: dict[str, list[str]],
        scoring_format: str = "1qb_ppr",
        cleared_pids: Optional[list[str]] = None,
        demoted_pids: Optional[list[str]] = None,
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

        ``demoted_pids`` (#161) — players the user explicitly passed over
        in a Quick Set tier save (visible in the step's grid, previously
        bucketed in the saved tier or higher, left unselected). Their
        override is pinned to ``DEMOTED_ELO`` — below every band — so they
        read as unranked until the user places them, instead of silently
        keeping the old higher tier. Distinct from ``cleared_pids``, which
        restores the consensus-suggested tier. If a pid appears in both,
        demotion wins; a pid both demoted and assigned to a tier in the
        same save takes the tier (the tier loop runs last).
        """
        pool_ids = {p.id for p in self._pool(position)}
        bands = self.tier_bands_for(position, scoring_format)

        # Drop overrides for explicitly-cleared pids first, so a pid that's
        # both cleared and re-tiered in the same save (rare, e.g. concurrent
        # tab) ends up with the new tier's band rather than left without an
        # override. The tier-write loop below will re-set it.
        # One stamp for the whole save — every pin this call writes was
        # written at the same instant (F2, _pin_release).
        now = datetime.now(timezone.utc).isoformat()

        if cleared_pids:
            for pid in cleared_pids:
                self._unpin(pid)

        # Pin demoted pids below every band (after clears, before tier
        # writes — see the precedence note in the docstring).
        if demoted_pids:
            for pid in demoted_pids:
                if pid in pool_ids:
                    self._pin(pid, self.DEMOTED_ELO, now)

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
                self._pin(valid[0], hi, now)
            else:
                for i, pid in enumerate(valid):
                    self._pin(pid, hi - (hi - lo) * i / (n - 1), now)

        self._version += 1

    def apply_tiers_subset(
        self,
        position: Optional[str],
        tiers: dict[str, list[str]],
        scope_pids: set[str],
        scoring_format: str = "1qb_ppr",
        cleared_pids: Optional[list[str]] = None,
        demoted_pids: Optional[list[str]] = None,
    ) -> dict[str, list[str]]:
        """Scoped tier save — the merged-band rule (rookie-draft plan D2/D3).

        `apply_tiers` above is deliberately NOT modified: the unscoped lane
        stays byte-identical (D4), and this is the only lane that knows about
        a subset.

        THE PROBLEM. A scoped board shows the user only part of a tier's
        membership (today: only the rookies). Two obvious implementations both
        destroy boards:

          * spread the SUBMITTED list over the band — the "naive scoped-list
            spread". The top rookie lands at the band ceiling, leapfrogging
            every veteran incumbent the user never saw.
          * spread the submitted list and persist the whole band — rewrites
            the overrides of untouched members the user never saw either.

        THE RULE. Reconstruct the *merged full-band order* `M` by merging the
        scoped pids (anchored by their CURRENT values) into the band's current
        full membership, spread linearly over the FULL merged list with
        arithmetic identical to `apply_tiers`, and persist the result for the
        SCOPED pids ONLY. That is the only construction satisfying both
        write-identity (a scoped pid gets exactly the Elo the equivalent
        full-band save would give it — the equivalence bar, T-M2-07) and
        no-respread (untouched members' overrides are byte-unchanged, D3/I-3).

        `cleared_pids` / `demoted_pids` (#161) are scoped too: a clear or a
        demotion for a pid the user could not see is ignored (O4). Demoting an
        unshown veteran is the one way this can silently damage a board.

        Returns `{tier_name: M}` so the caller can assert the equivalence bar
        without recomputing the merge.

        Known, accepted (plan round 4, RB-7): because incumbents are POSITIONED
        but not rewritten, a partial save can cosmetically invert against stale
        neighbours until the next full-band save. That is inherent to any
        partial save.
        """
        pool = self._pool(position)
        pool_ids = {p.id for p in pool}
        bands = self.tier_bands_for(position, scoring_format)
        # FULL-pool Elo — every rookie-vs-vet swipe still counts. Computed
        # once, BEFORE the mutations below, exactly as apply_tiers reads a
        # single consistent picture of the board.
        current = self._compute_elo(pool)

        def value_of(pid: str) -> float:
            """Where this pid sits right now: their override if they have
            one, else their computed Elo."""
            return self._elo_overrides.get(pid, current.get(pid, self.ELO_INITIAL))

        # ── clears and demotions, SCOPED (D3 / #161 / O4) ──────────────────
        now = datetime.now(timezone.utc).isoformat()   # one stamp per save (F2)
        for pid in (cleared_pids or []):
            if pid in scope_pids:            # a clear for an unshown vet is ignored
                self._unpin(pid)
        for pid in (demoted_pids or []):
            if pid in scope_pids and pid in pool_ids:   # visible + scoped only
                self._pin(pid, self.DEMOTED_ELO, now)

        merged_orders: dict[str, list[str]] = {}
        _SLOT = ("SCOPED_SLOT",)

        for tier_name, submitted in tiers.items():
            band = bands.get(tier_name)
            if band is None:
                continue
            lo, hi = band

            scoped = [pid for pid in submitted
                      if pid in pool_ids and pid in scope_pids]
            if not scoped:
                continue                      # nothing to write for this tier

            # 1. INCUMBENTS — the band's current membership, minus everything
            #    in scope (so a pid can never appear twice in M).
            incumbents = [pid for pid in pool_ids
                          if pid not in scope_pids and lo <= value_of(pid) <= hi]
            #    value desc, pid asc — fully deterministic regardless of set
            #    iteration order.
            incumbents.sort(key=lambda p: (-value_of(p), p))

            # 2. ANCHOR the scoped block by its CURRENT values, clamped into
            #    the band. The clamp is what makes a promotion INTO the tier
            #    well-defined: without it a scoped pid outside the band has no
            #    merge position at all.
            anchors = {pid: min(max(value_of(pid), lo), hi) for pid in scoped}

            # 3. MERGE two descending sequences into positional slots. Ties
            #    resolve to the user's submitted order.
            merged: list = []
            i = 0                             # incumbent cursor
            for pid in sorted(scoped,
                              key=lambda p: (-anchors[p], scoped.index(p))):
                while i < len(incumbents) and value_of(incumbents[i]) > anchors[pid]:
                    merged.append(incumbents[i])
                    i += 1
                merged.append(_SLOT)
            merged.extend(incumbents[i:])

            # 4. FILL the scoped slots, top-to-bottom, with the USER'S
            #    submitted order — that order is authoritative among them.
            it = iter(scoped)
            merged = [next(it) if s is _SLOT else s for s in merged]

            # 5. SPREAD over the FULL merged list. `len(merged)`, NOT
            #    `len(scoped)` — see the naive-spread trap in the docstring.
            #    Arithmetic identical to apply_tiers.
            n = len(merged)
            for idx, pid in enumerate(merged):
                v = hi if n == 1 else hi - (hi - lo) * idx / (n - 1)
                # 6. PERSIST SCOPED PIDS ONLY. This `if` is the whole of D3 —
                #    removing it produces the rejected full-band persist.
                if pid in scope_pids:
                    self._pin(pid, v, now)

            merged_orders[tier_name] = merged

        self._version += 1
        return merged_orders

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
        self._pin(player_id, target_elo)
        self._version += 1
        return player

    def board_override_count(self) -> int:
        """How many of this service's Elo overrides are for players still in
        the pool. The durable evidence behind the 'anchor' and 'manual' unlock
        rules (server.get_rankings_progress).

        WHY THE BOARD AND NOT THE INTERACTION COUNTER. `_interactions` is
        rebuilt from persisted rank swipes on every session build
        (see the `{pos: rank_swipe_count // 3}` rehydration below), so a
        counter bumped in apply_anchor/apply_reorder would be discarded on the
        next cold start — unlock on Tuesday, re-locked on Wednesday. Overrides
        are persisted (server.save_tier_overrides) and restored per format, so
        they survive. They are also format-scoped for free: this service
        instance IS the active format's instance.

        POOL-RESTRICTED ON PURPOSE. `_elo_overrides` deliberately retains
        stale pids — session_init keeps the full stored dict rather than
        filtering it, precisely so a pid missing from one day's pool is not
        destroyed. A raw len() would therefore over-count a long-lived board
        and could unlock a user on players who are no longer rankable.
        """
        pool_ids = {p.id for p in self._pool(None)}
        return sum(1 for pid in self._elo_overrides if pid in pool_ids)

    def apply_reorder(self, position: Optional[str], ordered_ids: list[str]) -> None:
        """
        Apply a manual reorder by setting ELO overrides that match the
        desired ranking order.  The reordered players receive the SORTED
        MULTISET OF THEIR OWN CURRENT ELOs (rank 1 gets the highest, rank
        2 the next, ...), i.e. a reorder is a pure permutation of the
        existing Elo values.

        Why not linear interpolation between pool max and min (the old
        behaviour): consensus dynasty values decay convexly, so a linear
        max→min spread flattened the value curve and pushed the top third
        of a position board above the Elite band floor — a full-board
        manual reorder then mislabelled dozens of players Elite on the
        Tiers screen (FB #60/#69, "44 elite QBs"). Permuting the existing
        Elos changes ORDER without distorting the value distribution, so
        tier occupancy is invariant under reorders.
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

        # Sorted (desc) Elo values of exactly the players being reordered.
        target_elos = sorted((current_elo[pid] for pid in valid_ids), reverse=True)

        # Break exact ties with a hair of descending epsilon so the user's
        # requested order survives an elo-desc re-sort (tail players often
        # share an identical seed Elo).
        for i in range(1, len(target_elos)):
            if target_elos[i] >= target_elos[i - 1]:
                target_elos[i] = target_elos[i - 1] - 0.001

        now = datetime.now(timezone.utc).isoformat()   # one stamp per save (F2)
        for pid, target_elo in zip(valid_ids, target_elos):
            self._pin(pid, target_elo, now)

        self._version += 1

    def apply_value_map(self, position: Optional[str], ordered_ids: list[str]) -> int:
        """
        Cross-format value mapping for the copy-from-format flow (#124).

        ``ordered_ids`` is a rank order established in ANOTHER scoring
        format (best first). Write ELO overrides that preserve that order
        while re-expressing each player's VALUE on THIS service's
        consensus curve: the group's own seed Elos in this format are
        sorted desc and dealt out to the given order (rank 1 gets the
        group's highest seed, rank 2 the next, ...).

        This is `apply_reorder`'s permutation trick pointed at the seed
        distribution instead of the current Elos — order comes from the
        user (the source format's board), magnitudes come from this
        format's consensus. Tier labels then land wherever this format's
        consensus puts the group: a QB worth "4+ firsts" in SF maps to
        whatever the top of the 1QB QB seed curve is worth (≈2 firsts),
        which is the #124 fix — copying a tier LABEL across formats
        overvalues (SF→1QB) or undervalues (1QB→SF) QBs. Permuting real
        seed values (not interpolating a band) keeps the convex value
        curve intact, so tier occupancy matches consensus occupancy —
        same rationale as apply_reorder's "44 elite QBs" note above.

        Exact seed ties get a hair of descending epsilon so the user's
        order survives an elo-desc re-sort. Returns the number of
        overrides written.
        """
        pool_ids = {p.id for p in self._pool(position)}
        valid_ids = [pid for pid in ordered_ids if pid in pool_ids]
        if not valid_ids:
            return 0

        target_elos = sorted(
            (self._seed.get(pid, self.ELO_INITIAL) for pid in valid_ids),
            reverse=True,
        )
        for i in range(1, len(target_elos)):
            if target_elos[i] >= target_elos[i - 1]:
                target_elos[i] = target_elos[i - 1] - 0.001

        now = datetime.now(timezone.utc).isoformat()   # one stamp per save (F2)
        for pid, target_elo in zip(valid_ids, target_elos):
            self._pin(pid, target_elo, now)

        self._version += 1
        return len(valid_ids)
