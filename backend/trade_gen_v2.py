"""
trade_gen_v2.py — divergence-driven, dual-board, staged trade generation.

Flag: ``trade_gen.v2`` (default OFF). When the flag is off this module is
never imported and every existing generation path (legacy, v2 pair, v3
optimizer, consensus fallback) is byte-identical. When on,
``TradeService.generate_trades`` routes here INSTEAD of the v2/v3 engine —
this pipeline ships alongside the existing generator, it does not replace
or modify it.

Research grounding (docs/research/matchmaking/):
  round-2/02 §1.6 + §6   — divergence-driven joint gain; the 7-step pipeline
  round-2/02 §2 BP 1-10  — staged search, dual-board IR gate, fairness band
                           as constraint, MESO variants, two-sided rationale,
                           diversity, non-additive package math
  round-2/01             — max-weight framing, cold-team priority weights,
                           completion-probability multiplier; 2-team scope
                           with a 3-team-cycle bolt-on kept possible (below)
  round-1/01 BP 1/6/7    — min-skewed fusion (harmonic-mean tiebreak),
                           dealbreakers as filters, asymmetric weights
  round-1/03 BP 1-2      — exposure as a budget: per-team appearance caps +
                           a per-team suggestion floor across a batch

Pipeline stages (never raw combinatorial search):
  1. Partner + centerpiece selection — for each boarded opponent, pick the
     opponent-roster assets X where the user's own-board value exceeds the
     opponent's own-board value most (``v_user(X) − v_opp(X)`` large),
     gated by the user's want/accept boards (not_interested excluded,
     targets prioritized).
  2. Return-package search around each centerpiece — user-side return
     assets ranked by ``v_opp(y) − v_user(y)`` (things the opponent likes
     more than the user does); packages capped at 3 assets (picks included
     as pick pseudo-assets) per side.
  3. Hard gates, IN ORDER:
       a. roster feasibility both sides (post-trade legal lineup, reusing
          the v3 ``_feasible_after`` rule);
       b. dual-board ε-gain: each side must gain ≥ ``gen2_epsilon`` on its
          OWN board, with the non-linear consolidation discount (below)
          applied to every multi-asset side — junk cannot stuff a package
          to fairness;
       c. consensus fairness band: the consolidation-discounted consensus
          package values must sit within ±``gen2_band`` of each other
          (min/max ≥ 1 − band). Own-board gain decides acceptance; the
          consensus band decides defensibility — never conflated.
  4. Rank survivors by joint gain (sum of both sides' own-board gains),
     tiebreak by symmetry of the surplus split (min/max of the two gains).
  5. Completion-probability hook — every suggestion's score is multiplied
     by an empirical-Bayes-shrunk per-manager acceptance prior
     (``acceptance_prior``), falling back to a global prior when no data
     exists. The interface is a plain ``{user_id: (accepts, responses)}``
     dict so a learned model can replace it without touching the pipeline.
  6. League-level exposure shaping — ORDERING, never truncation (operator
     decision 2026-08-16: uncapped discovery + uncapped browsable list;
     scarcity applies only to endorsement). The floor-first + cap-greedy
     pass shapes the HEAD of the list (who gets endorsed/featured
     placement, and every viable counterparty guaranteed head presence);
     cap-overflow cards are demoted below the head, never dropped. The
     engine returns the FULL ranked survivor set. Per-team exposure
     counts (full emission + shaped head) are logged (GenerationReport).
  7. Presentation payload — every card carries a ``tier``: ``endorsed``
     (the single best mutual pick of the cycle, at most 1), ``featured``
     (the next ``gen2_featured_count``), ``browse`` (all remaining
     survivors, still ranked). The per-pair top suggestion carries up to
     3 MESO return-package variants (approximately equivalent on the
     RECIPIENT's board, different in shape), and every suggestion carries
     structured two-sided rationale + per-suggestion health metrics.

Consolidation discount curve (documented decision)
---------------------------------------------------
Multi-asset sides are valued non-additively, KTC-style:

    consolidated_value(V) = Σ  v · (floor + (1 − floor) · (v / v_best)^γ)

where ``v_best`` is the side's OWN best asset, ``γ = gen2_consol_gamma``
(default 1.5) and ``floor = gen2_consol_floor`` (default 0.15). A
single-asset side is exactly its raw value (the bracket evaluates to 1.0).
A near-worthless filler contributes ≈ floor·v → junk-stuffing a package
moves its discounted value almost nothing, so neither the dual-board ε
gate nor the consensus band can be gamed by piling on bodies ("four
quarters ≠ a dollar"). The curve is deliberately independent of the
per-user stud-tax mode so the gate is the same for every user.

Dedup rule (documented decision)
--------------------------------
Within one batch a suggestion is a near-duplicate and dropped when ANY of:
  1. its exact give/receive asset sets already appeared;
  2. a higher-scored suggestion with the same (counterparty, centerpiece,
     shape bucket ``"GxR"``) was kept;
  3. a higher-scored KEPT suggestion against the same counterparty shares
     ≥ ``gen2_dedup_jaccard`` Jaccard overlap of the combined asset set.
Surviving suggestions therefore vary counterparty, centerpiece, or package
shape — never five perturbations of the same deal.

3-team bolt-on (deliberately NOT built)
---------------------------------------
Scoring is decomposed into directed transfers: ``side_gain(in, out,
value_of)`` scores what one team receives minus what it sends, on that
team's own board. A future 3-team cycle layer enumerates bounded cycles
and gates/sums the same directed ``side_gain`` per participating team —
no pairwise assumption is baked into the gate or the ranking math.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from .trade_service import (
    League,
    LeagueMember,
    TradeCard,
    _c,
    _harmonic_mean,
    _shrink_user_elo,
    analyze_roster_strengths,
    elo_to_value,
    filler_ok,
    infer_team_outlook,
    is_pick_asset,
    pick_swap_ok,
)
from .trade_optimizer import (
    _consensus_packages,
    _feasible_after,
    _pos_counts,
    _subset_pos_delta,
    close_value_gap,
)
# trade.negmem — MODULE import, attribute calls only (T1, LLD §6.3).
from . import negmem as _negmem

logger = logging.getLogger(__name__)

# Enumeration safety valve. The staged pools keep the real search tiny
# (≈ a few thousand combos per pair); this only guards pathological config.
_ITER_BUDGET = 60_000


# ---------------------------------------------------------------------------
# Value math — non-additive package valuation + directed gain
# ---------------------------------------------------------------------------

def consolidated_value(values: list[float]) -> float:
    """Non-additive package value (see module docstring for the curve).

    Single-asset sides are returned at raw value; multi-asset sides are
    discounted against their OWN best asset so low-value fillers contribute
    ≈ ``gen2_consol_floor`` of their raw value.
    """
    if not values:
        return 0.0
    v_best = max(values)
    if v_best <= 0:
        return sum(values)
    gamma = _c("gen2_consol_gamma")
    floor = _c("gen2_consol_floor")
    return sum(
        v * (floor + (1.0 - floor) * (max(v, 0.0) / v_best) ** gamma)
        for v in values
    )


def side_gain(in_ids: list[str], out_ids: list[str], value_of) -> float:
    """Directed gain of ONE team from a transfer, on that team's own board:
    consolidated value received minus consolidated value sent.

    This is the unit a 3-team cycle layer reuses: gate every participating
    team's ``side_gain ≥ gen2_epsilon`` and rank by the cycle's summed
    gains — identical semantics to the 2-team case below.
    """
    return (consolidated_value([value_of(p) for p in in_ids])
            - consolidated_value([value_of(p) for p in out_ids]))


# ---------------------------------------------------------------------------
# G6 presentment-rule parity — #341 net-position cap + #339 pick-gap band
# ---------------------------------------------------------------------------
# Ported 2026-08-16 (operator directive, ahead of the G6 wave's own v1-path
# merge) from the G6 spec at docs/feedback/items/304-positional-need-filter/
# (prd R-2 / R-3, lld-delta §3). These join the composition-hygiene gate so
# the successor generator carries the same package-shape guardrails as the
# v1 path will after G6 ships. Deliberately NOT ported: #304's positional-
# need hard gate — gen-v2 optimizes need in the objective, and a hard need
# filter would double-penalize and kill the consolidation shapes G6 itself
# protects (docs/plans/matchmaking-engine/2026-08-16-g6-validation.md).
#
# RECONCILED 2026-08-17 (G6 shipped ON in the 2026-08-16 wave): these gates
# now read G6's OWN model_config knobs — `pos_net_cap`, `pick_gap_frac`,
# `pick_gap_min_value` — rather than gen-v2 copies. One source of truth, so a
# knob change (notably G6 prd R-12's pending pick-league calibration of
# `pick_gap_frac`) moves both pipelines at once, and each knob is a single
# kill switch for the rule everywhere.
#
# Scope note: the knobs govern BOTH pipelines; G6's `trade.presentment_rules`
# flag is the v1 path's group revert only. Turning that flag off leaves these
# rules active in gen-v2 (which has its own flag, `trade_gen.v2`). To disable
# a rule everywhere, zero its knob.

# #341 counts positional bodies only: the four lineup positions, never
# picks (a pick is not a positional body; picks are #339's domain) and
# never K/DEF/IDP in exotic leagues (uncounted by design, per the spec).
_G6_NET_POSITIONS = ("QB", "RB", "WR", "TE")


def g6_pos_net_ok(give_ids: list[str], recv_ids: list[str],
                  players: dict) -> bool:
    """#341 package-shape cap (G6 prd R-2): for each position P in
    {QB, RB, WR, TE}, the signed net ``count(recv at P) − count(give at P)``
    — one quantity per position, not a per-side count — must satisfy
    ``|net_P| ≤ pos_net_cap`` (G6's knob — shared, not a gen-v2 copy).

    Semantics (operator's words): 2RB→2WR kills (net RB = −2); "give 2 RBs
    only if getting 1 back" passes (net −1); 2RB→2RB is net 0 and passes;
    every 1-for-1 passes trivially. Pick pseudo-assets are excluded
    (``is_pick_asset``), as are positions outside the four. The net is one
    side's view — the counterparty's net is its negation, so a single check
    covers both sides. ``pos_net_cap ≤ 0`` disables (per-rule
    kill switch, following the G6 `pos_net_cap`/`filler_min_frac` pattern).
    """
    cap = _c("pos_net_cap")
    if cap <= 0:
        return True
    net: dict[str, int] = defaultdict(int)
    for pid in recv_ids:
        p = players.get(pid)
        pos = getattr(p, "position", None)
        if pos in _G6_NET_POSITIONS and not is_pick_asset(p):
            net[pos] += 1
    for pid in give_ids:
        p = players.get(pid)
        pos = getattr(p, "position", None)
        if pos in _G6_NET_POSITIONS and not is_pick_asset(p):
            net[pos] -= 1
    return all(abs(n) <= cap for n in net.values())


def g6_pick_gap_ok(give_ids: list[str], recv_ids: list[str], cval,
                   players: dict) -> bool:
    """#339 pick-not-the-gap (G6 prd R-3): only evaluated when the package
    contains ≥1 pick. With ``g``/``r`` the RAW consensus sums of each side
    (players and picks, undiscounted — the D-055 Δ currency), ``gap =
    |g − r|``, and H the heavier side:

        KILL when gap ≥ pick_gap_min_value
             AND ∃ pick p ∈ H with
                 pick_gap_frac × gap ≤ cval(p) ≤ gap / pick_gap_frac

    Two-sided band: the pick must *be* the gap — within the band of it in
    both directions — not merely exceed a fraction of it. A pick far larger
    than the gap (centerpiece consolidation, e.g. gap 300 with a mid-1st at
    3,000 — "player + mid-1st for a stud", the operator's own stud-scaled
    style) passes; the #339 shape (heavier by exactly one mid-1st: gap
    3,000, pick 3,000) dies. The enumerators generate the pick-less sibling
    shape independently, so the kill loses nothing.
    ``pick_gap_frac = 0`` disables.
    """
    frac = _c("pick_gap_frac")
    if frac <= 0:
        return True
    if not any(is_pick_asset(players.get(p)) for p in give_ids) \
            and not any(is_pick_asset(players.get(p)) for p in recv_ids):
        return True
    g = sum(cval(p) for p in give_ids)
    r = sum(cval(p) for p in recv_ids)
    gap = abs(g - r)
    if gap < _c("pick_gap_min_value"):
        return True
    heavier = give_ids if g > r else recv_ids
    for pid in heavier:
        if not is_pick_asset(players.get(pid)):
            continue
        v = cval(pid)
        if frac * gap <= v <= gap / frac:
            return False
    return True


# ---------------------------------------------------------------------------
# Completion-probability hook (empirical-Bayes acceptance prior)
# ---------------------------------------------------------------------------

def acceptance_prior(
    user_id: str,
    acceptance_stats: dict[str, tuple[int, int]] | None,
) -> float:
    """P(this manager responds positively to a proposal), shrunk.

    Empirical-Bayes shrinkage of the manager's observed accept/response
    base rate toward the global prior:

        p = (accepts + m·p0) / (responses + m)

    with ``m = gen2_accept_prior_strength`` pseudo-observations and
    ``p0 = gen2_accept_global_prior``. No data (or no stats supplied) →
    exactly ``p0``, which scales every score uniformly and leaves ordering
    untouched. The narrow dict interface (``uid → (accepts, responses)``)
    is deliberate: a learned acceptance model replaces this function
    without touching the pipeline.
    """
    p0 = _c("gen2_accept_global_prior")
    m = _c("gen2_accept_prior_strength")
    if not acceptance_stats or user_id not in acceptance_stats:
        return p0
    accepts, responses = acceptance_stats[user_id]
    responses = max(int(responses), 0)
    accepts = min(max(int(accepts), 0), responses)
    return (accepts + m * p0) / (responses + m)


# ---------------------------------------------------------------------------
# Package shape classification (MESO + rationale vocabulary)
# ---------------------------------------------------------------------------

def classify_package_shape(ids: list[str], players: dict, value_of) -> str:
    """'consolidation' | 'pick_heavy' | 'youth_heavy' | 'balanced'.

    consolidation — a single asset (one bigger piece);
    pick_heavy    — ≥50% of package value carried by pick assets;
    youth_heavy   — value-weighted mean age of the non-pick players ≤
                    ``gen2_youth_age``;
    balanced      — everything else.
    """
    if len(ids) == 1:
        return "consolidation"
    total = sum(value_of(p) for p in ids) or 1.0
    pick_v = sum(value_of(p) for p in ids if is_pick_asset(players.get(p)))
    if pick_v / total >= 0.5:
        return "pick_heavy"
    aged = [(value_of(p), getattr(players.get(p), "age", None))
            for p in ids if not is_pick_asset(players.get(p))]
    aged = [(v, a) for v, a in aged if a]
    if aged:
        wsum = sum(v for v, _ in aged)
        if wsum > 0:
            mean_age = sum(v * a for v, a in aged) / wsum
            if mean_age <= _c("gen2_youth_age"):
                return "youth_heavy"
    return "balanced"


# ---------------------------------------------------------------------------
# Internal candidate + report containers
# ---------------------------------------------------------------------------

@dataclass
class _Candidate:
    opponent_id: str
    centerpiece: str
    give_ids: list[str]
    recv_ids: list[str]
    user_gain: float
    opp_gain: float
    joint_gain: float
    symmetry: float          # min/max of the two gains, 1 = even split
    split_ratio: float       # user_gain / joint_gain
    fairness_ratio: float    # consensus min/max on discounted packages
    band_position: float     # signed, −1..+1, 0 = perfectly balanced
    accept_prior: float
    score: float             # joint_gain × accept_prior × priority weight
    give_val_opp: float      # opp-board discounted value of the give side
                             # (the RECIPIENT's valuation of the return —
                             # the MESO equivalence metric)
    #: 2026-08-21 gap auto-sweetener — {player_id, side, gap_before,
    #: gap_after} when this candidate was equalized, else None. Carried on
    #: the CANDIDATE (not stamped on the card later) because the sweetener
    #: runs inside `_pair_survivors`: every derived field above is rebuilt
    #: from the sweetened ids, so the record has to travel with them.
    gap_sweetener: dict | None = None


@dataclass
class GenerationReport:
    """Per-batch health + exposure telemetry. Logged as one JSON line;
    returned to the caller so the (separately-built) telemetry layer can
    persist it without this module owning any tables."""
    league_id: str
    user_id: str
    #: Stage 0 — how many opponents reached the pair loop at all. `boarded`
    #: is `has_rankings and elo_ratings`; everyone else is listed in
    #: `unranked_opponents`. Zero here is the ONLY explanation for a batch
    #: in which every other counter is also zero, and it is a property of
    #: the LEAGUE (nobody else has ranked), never of this pipeline.
    boarded_opponents: int = 0
    #: Stage 1a — boarded pairs whose tradeable universe came out empty on
    #: one side or both: divergence needs a pid the user has an opinion on
    #: (`user_known`) AND the opponent has ranked (`opp_elo_map`), minus
    #: the want/accept-board filters. No overlap ⇒ nothing to compare.
    pairs_no_board_overlap: int = 0
    #: Stage 1b — pairs WITH overlap that still produced no centerpiece:
    #: no opponent asset cleared `v_user − v_opp > gen2_min_divergence`.
    #: This is the "two real boards that happen to agree" case, and it is
    #: the counter that separates a starved arm from a gated one.
    pairs_no_centerpiece: int = 0
    considered: int = 0
    composition_rejects: int = 0  # #141 filler / #227 pick-churn hygiene
    net_cap_rejects: int = 0     # G6 #341 net-position cap kills
    pick_band_rejects: int = 0   # G6 #339 pick-not-the-gap band kills
    feasibility_rejects: int = 0
    ir_rejects: int = 0          # dual-board ε-gate failures
    band_rejects: int = 0        # consensus fairness-band failures
    #: 2026-08-21 gap auto-sweetener — survivors whose absolute consensus
    #: gap was closed by an added equalizer. Not a kill counter: these
    #: candidates survived either way, the pass only narrowed the gap.
    gap_sweetened: int = 0
    survivors: int = 0
    emitted: int = 0
    ir_rate: float = 0.0         # survivors of gate b / entrants to gate b
    mean_split_ratio: float | None = None
    mean_symmetry: float | None = None
    viable_by_opponent: dict = field(default_factory=dict)
    exposure_by_opponent: dict = field(default_factory=dict)   # full emission
    shaped_head_by_opponent: dict = field(default_factory=dict)  # cap-shaped head
    unranked_opponents: list = field(default_factory=list)

    @property
    def starvation_reason(self) -> str | None:
        """Why this batch emitted nothing, when nothing was emitted.

        `None` means the batch either produced cards or died at a real
        GATE (in which case the per-stage counters below say which one).
        A non-None value means no candidate was ever ENUMERATED, so no
        gate can be blamed — the pipeline never had inputs:

          ``no_boarded_opponents`` — nobody else in the league has ranked.
            Divergence-only by design (config/features.json
            `_comment_trade_gen_v2`); unranked opponents belong to the
            flag-off engine's consensus path, so this is the league
            telling the engine it is out of scope, not a defect.
          ``no_board_overlap``  — boarded opponents exist, but no asset is
            priced on both boards after the want/accept filters.
          ``no_divergence``     — both boards are real and overlapping and
            simply agree: nothing clears `gen2_min_divergence`.
        """
        if self.emitted:
            return None
        if not self.boarded_opponents:
            return "no_boarded_opponents"
        if self.considered:
            return None                       # gated, not starved
        if self.pairs_no_board_overlap >= self.boarded_opponents:
            return "no_board_overlap"
        if self.pairs_no_centerpiece:
            return "no_divergence"
        return None

    def kill_counts(self) -> dict:
        """Per-stage attrition for one batch, in PIPELINE ORDER.

        Mirrors `TradeService.presentment_kill_counts()` (G6 R-9): one flat
        dict of counters a query can read without parsing prose, so "arm C
        produced nothing" resolves to a stage instead of a shrug. Keys are
        prefixed with the stage that owns them (S0 supply, S1 selection,
        S2 enumeration, S3a-d the hard gates in the order they run, S4/S6
        the survivors and the emission).
        """
        return {
            "S0_boarded_opponents":     self.boarded_opponents,
            "S0_unranked_opponents":    len(self.unranked_opponents),
            "S1_no_board_overlap":      self.pairs_no_board_overlap,
            "S1_no_centerpiece":        self.pairs_no_centerpiece,
            "S2_considered":            self.considered,
            "S3a_composition":          self.composition_rejects,
            "S3a_net_cap":              self.net_cap_rejects,
            "S3a_pick_band":            self.pick_band_rejects,
            "S3b_feasibility":          self.feasibility_rejects,
            "S3c_dual_board_ir":        self.ir_rejects,
            "S3d_fairness_band":        self.band_rejects,
            "S4_survivors":             self.survivors,
            "S6_emitted":               self.emitted,
            "starvation_reason":        self.starvation_reason,
        }

    def as_dict(self) -> dict:
        return {
            "league_id": self.league_id,
            "user_id": self.user_id,
            "boarded_opponents": self.boarded_opponents,
            "pairs_no_board_overlap": self.pairs_no_board_overlap,
            "pairs_no_centerpiece": self.pairs_no_centerpiece,
            "considered": self.considered,
            "composition_rejects": self.composition_rejects,
            "net_cap_rejects": self.net_cap_rejects,
            "pick_band_rejects": self.pick_band_rejects,
            "feasibility_rejects": self.feasibility_rejects,
            "ir_rejects": self.ir_rejects,
            "band_rejects": self.band_rejects,
            "gap_sweetened": self.gap_sweetened,
            "survivors": self.survivors,
            "emitted": self.emitted,
            "ir_rate": round(self.ir_rate, 4),
            "mean_split_ratio": self.mean_split_ratio,
            "mean_symmetry": self.mean_symmetry,
            "viable_by_opponent": self.viable_by_opponent,
            "exposure_by_opponent": self.exposure_by_opponent,
            "shaped_head_by_opponent": self.shaped_head_by_opponent,
            "unranked_opponents": self.unranked_opponents,
        }


# ---------------------------------------------------------------------------
# Stage 1+2+3+4: per-pair survivor search
# ---------------------------------------------------------------------------

def _pair_survivors(
    *,
    opponent: LeagueMember,
    players: dict,
    user_roster: list[str],
    user_known: set,             # pids present on the user's board — same
                                 # both-boards-required rule as the v2 pools
                                 # (no divergence claim without a real
                                 # opinion on BOTH boards)
    uval,                        # pid → user's own-board value (shrunk)
    oval,                        # pid → opponent's own-board value
    cval,                        # pid → consensus value
    scoring_format: str,
    untouchable_ids: set,
    target_ids: set,
    not_interested_ids: set,
    past_decision_keys: set,
    accept_prior: float,
    priority_weight: float,
    report: GenerationReport,
) -> list[_Candidate]:
    """Stages 1-4 for one (user, opponent) pair. Returns gate-surviving
    candidates sorted by (score desc, symmetry desc)."""
    epsilon = _c("gen2_epsilon")
    band = _c("gen2_band")
    top_k = int(_c("gen2_centerpiece_top_k"))
    give_pool_n = int(_c("gen2_give_pool"))
    extra_pool_n = int(_c("gen2_recv_extra_pool"))
    min_div = _c("gen2_min_divergence")

    opp_elo_map = opponent.elo_ratings

    # Tradeable universes: known on both boards, accept/want boards applied
    # as FILTERS (round-1 BP 6 — dealbreakers never score, they gate).
    opp_assets = [p for p in opponent.roster
                  if p in opp_elo_map and p in user_known
                  and p not in not_interested_ids]
    user_assets = [p for p in user_roster
                   if p in opp_elo_map and p in user_known
                   and p not in untouchable_ids]

    # Stage 1 — centerpieces: divergence-positive opponent assets the user
    # values above the opponent's own board; explicit targets outrank raw
    # divergence (want board as priority, not filter).
    # Stage 1a — no shared, tradeable universe at all. Recorded rather
    # than silently returning: an empty universe and an empty divergence
    # set produce the same zero card count and have completely different
    # fixes (get the opponent to rank vs. widen the divergence floor).
    if not opp_assets or not user_assets:
        report.pairs_no_board_overlap += 1
        return []

    divergent = [(p, uval(p) - oval(p)) for p in opp_assets]
    divergent = [(p, d) for p, d in divergent if d > min_div]
    divergent.sort(key=lambda t: (t[0] in target_ids, t[1]), reverse=True)
    centerpieces = [p for p, _ in divergent[:top_k]]
    if not centerpieces:
        # Stage 1b — two real boards that agree. The pipeline is fed and
        # still has nothing to propose; see GenerationReport.
        report.pairs_no_centerpiece += 1
        return []

    # Stage 2 pools — return assets the OPPONENT values above the user's
    # board (the log-rolling direction), and small divergence-positive
    # extras to round out the receive side.
    give_pool = sorted(user_assets, key=lambda p: oval(p) - uval(p),
                       reverse=True)[:give_pool_n]
    extras_all = [p for p, _ in divergent]

    user_counts = _pos_counts(user_roster, players)
    opp_counts = _pos_counts(opponent.roster, players)

    # 2026-08-21 gap auto-sweetener (`sweetener_gap_threshold`), arm C.
    # `_gap_gates_ok` re-earns THIS path's ENTIRE hard-gate stack for a
    # sweetened combo, in the same order the enumeration applies it. It
    # deliberately touches no `report` counter: a sweetened combo that
    # fails a gate is not a rejected candidate, it is a candidate that
    # ships unsweetened. `close_value_gap` itself covers the absolute-gap
    # test and 3.2 lineup feasibility (same `_feasible_after`/`_pos_counts`
    # helpers this loop uses), so neither is repeated here.
    _GAP_THR = _c("sweetener_gap_threshold")

    def _gap_gates_ok(g: list[str], r: list[str]) -> bool:
        # A sweetened combo is a DIFFERENT trade, so the past-decision
        # ban has to be re-tested against its own key — the enumeration's
        # check only ever saw the unsweetened shape.
        if (frozenset(g), frozenset(r)) in past_decision_keys:
            return False
        if not filler_ok(g, r, uval, oval):
            return False
        if not pick_swap_ok(g, r, players):
            return False
        if not g6_pos_net_ok(g, r, players):
            return False
        if not g6_pick_gap_ok(g, r, cval, players):
            return False
        # Gate b — dual-board ε-gain. Load-bearing here: an equalizer
        # added to the give side moves user_gain DOWN and opp_gain UP
        # (and the reverse for a receive-side one), so either side can
        # fall through ε that the organic combo cleared.
        if side_gain(r, g, uval) < epsilon:
            return False
        if side_gain(g, r, oval) < epsilon:
            return False
        # Gate c — arm C's OWN consensus fairness band, over
        # `consolidated_value`. This is why `close_value_gap` is called
        # with fairness_threshold=0.0: its built-in ratio gate is the
        # v2/v3 `_consensus_packages` notion, a different functional that
        # arm C has never gated on. The native band test binds instead.
        _gc = consolidated_value([cval(p) for p in g])
        _rc = consolidated_value([cval(p) for p in r])
        _hi = max(_gc, _rc)
        if _hi > 0 and min(_gc, _rc) / _hi < 1.0 - band:
            return False
        return True

    survivors: list[_Candidate] = []
    iters = 0
    ir_entrants = 0

    for cp in centerpieces:
        extras = [p for p in extras_all if p != cp][:extra_pool_n]
        recv_options: list[list[str]] = [[cp]]
        recv_options += [[cp, e] for e in extras]
        recv_options += [[cp, e1, e2] for e1, e2 in combinations(extras, 2)]

        give_options: list[list[str]] = []
        for r in (1, 2, 3):
            give_options += [list(c) for c in combinations(give_pool, r)]

        for recv_ids in recv_options:
            for give_ids in give_options:
                iters += 1
                if iters > _ITER_BUDGET:
                    logger.warning("trade_gen_v2: iteration budget hit for "
                                   "pair vs %s", opponent.user_id)
                    survivors.sort(key=lambda s: (s.score, s.symmetry),
                                   reverse=True)
                    return survivors
                if (frozenset(give_ids), frozenset(recv_ids)) \
                        in past_decision_keys:
                    continue
                report.considered += 1

                # Composition hygiene — the existing engine conventions
                # apply here too: the #141 junk-filler gate (both floors,
                # max-of-boards metric) and the #227 pick-for-pick churn
                # ban. These are dealbreaker FILTERS, never scores.
                if not filler_ok(give_ids, recv_ids, uval, oval):
                    report.composition_rejects += 1
                    continue
                if not pick_swap_ok(give_ids, recv_ids, players):
                    report.composition_rejects += 1
                    continue
                # G6 parity rules (ported 2026-08-16; see the module
                # section above): #341 net-position cap and #339
                # pick-not-the-gap band join the hygiene gate — same
                # placement as G6's v1 hooks (before feasibility, so a
                # killed shape is refilled from the enumeration).
                if not g6_pos_net_ok(give_ids, recv_ids, players):
                    report.net_cap_rejects += 1
                    continue
                if not g6_pick_gap_ok(give_ids, recv_ids, cval, players):
                    report.pick_band_rejects += 1
                    continue

                # Gate a — roster feasibility, BOTH sides.
                g_delta = _subset_pos_delta(give_ids, players)
                r_delta = _subset_pos_delta(recv_ids, players)
                if not _feasible_after(user_counts, g_delta, r_delta,
                                       scoring_format):
                    report.feasibility_rejects += 1
                    continue
                if not _feasible_after(opp_counts, r_delta, g_delta,
                                       scoring_format):
                    report.feasibility_rejects += 1
                    continue

                # Gate b — dual-board ε-gain, each side on its OWN board,
                # consolidation discount on every multi-asset side.
                ir_entrants += 1
                user_gain = side_gain(recv_ids, give_ids, uval)
                if user_gain < epsilon:
                    report.ir_rejects += 1
                    continue
                opp_gain = side_gain(give_ids, recv_ids, oval)
                if opp_gain < epsilon:
                    report.ir_rejects += 1
                    continue

                # Gate c — consensus fairness band (defensibility, not
                # acceptance): discounted consensus packages within ±band.
                gc = consolidated_value([cval(p) for p in give_ids])
                rc = consolidated_value([cval(p) for p in recv_ids])
                hi = max(gc, rc)
                if hi > 0 and min(gc, rc) / hi < 1.0 - band:
                    report.band_rejects += 1
                    continue
                band_pos = 0.0 if hi <= 0 or band <= 0 \
                    else (rc - gc) / (band * hi)

                # ---- 2026-08-21 gap auto-sweetener, arm C --------------
                # This combo passed every gate, but the band gate above is
                # a RATIO and therefore scale-blind: 1 − gen2_band on a
                # five-figure package still leaves more than a late 1st of
                # consensus value on the table. Arm C inherited the
                # parent's trade-wide package benchmark (which WIDENS
                # absolute gaps) without the closer, so its measured
                # over-the-line share rose to 13.6% / 10.5% on the two
                # fixtures while every other served arm sits at 0–5.3%.
                #
                # Placement is deliberate. The gap is only computable from
                # `_consensus_packages`, which the card builder calls much
                # later — but sweetening THERE would leave `_dedup_batch`,
                # `_meso_variants`, `_rationale`, `classify_package_shape`
                # (whose "consolidation" label is literally `len(ids) == 1`),
                # `card.health`, `mismatch_score`, `fairness_score`,
                # `composite_score` and the Stage 6/7 exposure+tier ranking
                # all describing the UNSWEETENED trade — arm C's much
                # larger analogue of the v3 stale-`fit_premium` defect.
                # Sweetening here instead, and rebuilding every derived
                # field below from the sweetened ids, keeps one coherent
                # trade all the way to the card.
                #
                # New names, not a rebind: `recv_ids` is the OUTER loop
                # variable and reassigning it would corrupt every later
                # give-side iteration for this centerpiece.
                s_give, s_recv, _gap_info = give_ids, recv_ids, None
                if _GAP_THR > 0:
                    _gv, _rv = _consensus_packages(give_ids, recv_ids, cval)
                    if abs(_gv - _rv) > _GAP_THR:
                        _closed = close_value_gap(
                            give_ids, recv_ids, seed_value=cval,
                            gap_threshold=_GAP_THR,
                            # 0.0 = the helper's own consensus-ratio gate
                            # is inert; `_gap_gates_ok` applies arm C's
                            # native `consolidated_value` band instead.
                            fairness_threshold=0.0,
                            user_roster=user_roster,
                            opp_roster=opponent.roster,
                            players=players,
                            scoring_format=scoring_format,
                            untouchable_ids=untouchable_ids,
                            not_interested_ids=not_interested_ids,
                            # Arm C PRUNES rather than gating per combo, so
                            # the equalizer universe must be passed — drawing
                            # from the raw roster is the round-2 consensus
                            # defect (49c1d76). But arm C prunes in TWO
                            # layers, and only one of them is semantic:
                            #
                            #   semantic  `user_assets` = on BOTH boards and
                            #             not untouchable; `extras_all` =
                            #             divergence-positive and not
                            #             not-interested. These encode real
                            #             rules — an equalizer violating one
                            #             would be an asset arm C could never
                            #             legitimately trade.
                            #   budget    `[:gen2_give_pool]` /
                            #             `[:gen2_recv_extra_pool]` — pure
                            #             enumeration cost, documented as
                            #             bounding "SEARCH BREADTH, never
                            #             output length" alongside
                            #             gen2_centerpiece_top_k.
                            #
                            # So we pass the SEMANTIC universes, not the
                            # budget slices. This is not the 49c1d76 defect
                            # relaxed: that one crossed a semantic line (a
                            # #174 pinned "trade away G" job smuggling in an
                            # unpinned player — a broken user instruction).
                            # A rank-11 give asset breaks no rule; it is
                            # simply one the combinatorial search had no
                            # budget to enumerate as a PRIMARY piece, and
                            # the sweetener adds at most one asset to an
                            # already-gated card. Measured: the budget slice
                            # was the binding constraint — 78/112 and 63/86
                            # rejected equalizers were undershoot (nothing in
                            # the pool big enough), against 8 and 13 killed
                            # by arm C's own gates. Widening moves the
                            # 12-team fixture 3 -> 1 cards over the line.
                            # `close_value_gap` still takes the CHEAPEST
                            # sufficient equalizer, so this buys reach, not
                            # a licence to overpay. Full rosters above still
                            # drive the 3.2 feasibility counts.
                            give_candidates=user_assets,
                            recv_candidates=extras_all,
                            extra_ok_fn=_gap_gates_ok)
                        if _closed is not None:
                            _s_pid, _side, _ng, _nr, _ngv, _nrv, _ = _closed
                            _gap_info = {
                                "player_id": _s_pid, "side": _side,
                                "gap_before": round(abs(_gv - _rv), 1),
                                "gap_after": round(abs(_ngv - _nrv), 1),
                            }
                            s_give, s_recv = _ng, _nr
                            # Rebuild every derived field from the
                            # sweetened ids. Gate b/c already re-passed
                            # inside `_gap_gates_ok`; these are the same
                            # quantities, kept for the candidate record.
                            user_gain = side_gain(s_recv, s_give, uval)
                            opp_gain = side_gain(s_give, s_recv, oval)
                            gc = consolidated_value(
                                [cval(p) for p in s_give])
                            rc = consolidated_value(
                                [cval(p) for p in s_recv])
                            hi = max(gc, rc)
                            band_pos = 0.0 if hi <= 0 or band <= 0 \
                                else (rc - gc) / (band * hi)
                            report.gap_sweetened += 1

                joint = user_gain + opp_gain
                mx = max(user_gain, opp_gain)
                symmetry = (min(user_gain, opp_gain) / mx) if mx > 0 else 1.0
                split = (user_gain / joint) if joint > 0 else 0.5
                score = joint * accept_prior * priority_weight

                survivors.append(_Candidate(
                    opponent_id=opponent.user_id,
                    centerpiece=cp,
                    give_ids=list(s_give),
                    recv_ids=list(s_recv),
                    gap_sweetener=_gap_info,
                    user_gain=round(user_gain, 1),
                    opp_gain=round(opp_gain, 1),
                    joint_gain=round(joint, 1),
                    symmetry=round(symmetry, 4),
                    split_ratio=round(split, 4),
                    fairness_ratio=round(min(gc, rc) / hi, 3) if hi > 0
                    else 1.0,
                    band_position=round(band_pos, 3),
                    accept_prior=round(accept_prior, 4),
                    score=round(score, 2),
                    give_val_opp=round(
                        consolidated_value([oval(p) for p in s_give]), 1),
                ))

    if ir_entrants:
        # Cumulative across pairs; recomputed by the caller for the batch.
        report.survivors += len(survivors)
    # Rank: joint gain (via score — prior/priority are pair-constant here)
    # first, symmetry of the split as the tiebreak (research §6 step 4).
    survivors.sort(key=lambda s: (s.score, s.symmetry), reverse=True)
    return survivors


# ---------------------------------------------------------------------------
# Stage 6 helper — batch dedup (documented rule in module docstring)
# ---------------------------------------------------------------------------

def _dedup_batch(cands: list[_Candidate]) -> list[_Candidate]:
    jac_bar = _c("gen2_dedup_jaccard")
    kept: list[_Candidate] = []
    seen_exact: set = set()
    seen_bucket: set = set()
    kept_assets_by_opp: dict[str, list[frozenset]] = defaultdict(list)
    for c in sorted(cands, key=lambda s: (s.score, s.symmetry), reverse=True):
        exact = (c.opponent_id, frozenset(c.give_ids), frozenset(c.recv_ids))
        if exact in seen_exact:
            continue
        bucket = (c.opponent_id, c.centerpiece,
                  f"{len(c.give_ids)}x{len(c.recv_ids)}")
        if bucket in seen_bucket:
            continue
        assets = frozenset(c.give_ids) | frozenset(c.recv_ids)
        dup = False
        for prev in kept_assets_by_opp[c.opponent_id]:
            inter = len(assets & prev)
            union = len(assets | prev)
            if union and inter / union >= jac_bar:
                dup = True
                break
        if dup:
            continue
        seen_exact.add(exact)
        seen_bucket.add(bucket)
        kept_assets_by_opp[c.opponent_id].append(assets)
        kept.append(c)
    return kept


# ---------------------------------------------------------------------------
# Stage 7 helpers — MESO variants + two-sided rationale
# ---------------------------------------------------------------------------

def _meso_variants(
    base: _Candidate,
    pair_pool: list[_Candidate],
    players: dict,
    cval,
) -> list[dict]:
    """Up to gen2_meso_max_variants return-package variants for the pair's
    top suggestion: same receive side, different give side, opp-board
    (RECIPIENT) value within ±gen2_meso_band of the base give package,
    each with a distinct shape label (youth / picks / consolidation /
    balanced). Every variant already passed all hard gates."""
    band = _c("gen2_meso_band")
    max_n = int(_c("gen2_meso_max_variants"))
    base_recv = frozenset(base.recv_ids)
    base_give = frozenset(base.give_ids)
    base_val = base.give_val_opp
    if base_val <= 0:
        return []
    out: list[dict] = []
    shapes_used: set[str] = set()
    for c in pair_pool:
        if len(out) >= max_n:
            break
        if frozenset(c.recv_ids) != base_recv:
            continue
        if frozenset(c.give_ids) == base_give:
            continue
        if abs(c.give_val_opp - base_val) > band * base_val:
            continue
        # G6 #339 on MESO variants: a variant that violates the pick-gap
        # band is dropped, never emitted. Belt-and-suspenders — the pool
        # only holds hard-gate survivors, which already passed the band —
        # but the MESO surface must hold the invariant on its own even if
        # the pool's provenance ever changes (e.g. a pick-heavy variant
        # generator that doesn't re-run the hygiene gate).
        if not g6_pick_gap_ok(c.give_ids, c.recv_ids, cval, players):
            continue
        shape = classify_package_shape(c.give_ids, players, cval)
        if shape in shapes_used:
            continue
        shapes_used.add(shape)
        out.append({
            "shape": shape,
            "give_player_ids": list(c.give_ids),
            "recipient_value_delta_pct": round(
                (c.give_val_opp - base_val) / base_val * 100.0, 1),
        })
    return out


def _positions_of(ids: list[str], players: dict) -> list[str]:
    out = []
    for pid in ids:
        p = players.get(pid)
        pos = getattr(p, "position", None) if p else None
        if pos and pos != "PICK":
            out.append(pos)
    return out


def _timeline_fit(outlook: str | None, receive_shape: str) -> str | None:
    """Why the counterparty's timeline plausibly wants what they receive."""
    if outlook in ("rebuilder", "jets") and receive_shape in (
            "pick_heavy", "youth_heavy"):
        return "rebuild_gets_youth_or_picks"
    if outlook in ("contender", "championship") and receive_shape in (
            "consolidation", "balanced"):
        return "contender_gets_win_now"
    return None


def _rationale(
    c: _Candidate,
    players: dict,
    cval,
    user_profile: dict,
    opp_profile: dict,
    opp_outlook: dict | None,
) -> dict:
    """Structured, two-sided rationale — never a single winner score.
    'user' = your gain in YOUR board's terms; 'counterparty' = why they
    plausibly say yes (their own-board gain + timeline/positional need)."""
    cp = players.get(c.centerpiece)
    recv_pos = _positions_of(c.recv_ids, players)
    give_pos = _positions_of(c.give_ids, players)
    user_needs = set(user_profile.get("position_needs", []))
    opp_needs = set(opp_profile.get("position_needs", []))
    opp_surplus = set(opp_profile.get("position_surplus", []))
    give_shape = classify_package_shape(c.give_ids, players, cval)
    outlook_val = (opp_outlook or {}).get("value")
    return {
        "user": {
            "own_board_gain": c.user_gain,
            "board": "personal",
            "centerpiece": {
                "id": c.centerpiece,
                "name": getattr(cp, "name", c.centerpiece) if cp
                else c.centerpiece,
            },
            "receive_positions": recv_pos,
            "fills_needs": sorted(set(recv_pos) & user_needs),
        },
        "counterparty": {
            "own_board_gain": c.opp_gain,
            "board": "personal",
            "timeline": opp_outlook,
            "why_yes": {
                "values_return_above_cost": True,   # by the ε-gate
                "gives_from_surplus": sorted(set(recv_pos) & opp_surplus),
                "fills_needs": sorted(set(give_pos) & opp_needs),
                "timeline_fit": _timeline_fit(outlook_val, give_shape),
            },
        },
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def generate_league_suggestions(
    *,
    players: dict,
    league: League,
    user_id: str,
    user_elo: dict[str, float],
    user_roster: list[str],
    seed_elo: dict[str, float],
    confidence: dict[str, int] | None = None,
    placements: dict[str, tuple[float, float]] | None = None,
    max_per_opponent: int | None = None,
    scoring_format: str = "1qb_ppr",
    untouchable_ids: set | None = None,
    target_ids: set | None = None,
    not_interested_ids: set | None = None,
    opponent_user_id: str | None = None,
    opponent_outlooks: dict[str, str] | None = None,
    opponent_pick_shares: dict[str, float] | None = None,
    acceptance_stats: dict[str, tuple[int, int]] | None = None,
    priority_weights: dict[str, float] | None = None,
    past_decision_keys: set | None = None,
    negmem_map=None,                    # trade.negmem — the job's NegmemMap
                                        # (LLD §6.3). Distinct from
                                        # `acceptance_stats` above: different
                                        # math, same map. None ⇒ no seam.
    on_opponent_done=None,
) -> tuple[list[TradeCard], GenerationReport]:
    """Full staged pipeline for one user against one league.

    Returns (cards, report). Cards are ordinary TradeCards (basis
    "divergence") additionally carrying ``tier``, ``rationale``,
    ``health`` and — on each pair's top card — ``meso_variants``. The
    report carries batch health + per-team exposure counts and is also
    logged as one JSON line; the suggestion-telemetry layer consumes it
    at its own merge time.

    **No engine truncation** (operator decision 2026-08-16):
    ``max_per_opponent`` defaults to None = the FULL post-dedup survivor
    set is returned, ranked. Passing an int is a caller-owned
    presentation limit, never an engine default. Scarcity is expressed
    through the ``tier`` field instead (one ``endorsed``, a few
    ``featured``, everything else ``browse``).

    ``acceptance_stats`` (uid → (accepts, responses)) feeds the
    completion-probability multiplier; ``priority_weights`` (uid → mult)
    is the cold-team boost hook from the thin-markets research — both
    default to neutral.
    """
    untouchable_ids = untouchable_ids or set()
    target_ids = target_ids or set()
    not_interested_ids = not_interested_ids or set()
    past_decision_keys = past_decision_keys or set()
    priority_weights = priority_weights or {}
    declared_outlooks = opponent_outlooks or {}
    pick_shares = opponent_pick_shares or {}

    report = GenerationReport(league_id=league.league_id, user_id=user_id)

    # User board: confidence shrinkage toward consensus, then the D-085
    # placement clamp, then the value transform — same convention AND the same
    # call as the v2 engine, so the two arms cannot price a deliberately
    # placed player differently.
    shrunk = _shrink_user_elo(user_elo, seed_elo, confidence, placements)
    user_value = {pid: elo_to_value(e) for pid, e in shrunk.items()}
    _def_val = elo_to_value(1500.0)

    def uval(pid: str) -> float:
        return user_value.get(pid, _def_val)

    _cv_cache: dict[str, float] = {}

    def cval(pid: str) -> float:
        v = _cv_cache.get(pid)
        if v is None:
            v = elo_to_value(seed_elo.get(pid, 1500.0))
            _cv_cache[pid] = v
        return v

    # Divergence needs two REAL boards — unranked opponents are out of
    # scope for this engine (the existing consensus fallback still serves
    # them on the flag-off path).
    eligible = [m for m in league.members
                if m.user_id != user_id and m.roster]
    if opponent_user_id:
        eligible = [m for m in eligible if m.user_id == opponent_user_id]
    boarded = [m for m in eligible if m.has_rankings and m.elo_ratings]
    report.unranked_opponents = [m.user_id for m in eligible
                                 if m not in boarded]
    report.boarded_opponents = len(boarded)

    user_profile = analyze_roster_strengths(user_roster, players,
                                            scoring_format)
    num_teams = len(league.members)

    cards: list[TradeCard] = []
    all_selected: list[tuple[_Candidate, TradeCard]] = []
    per_pair: dict[str, list[_Candidate]] = {}
    total = len(boarded)

    for idx, member in enumerate(boarded):
        opp_elo_map = member.elo_ratings

        _ov_cache: dict[str, float] = {}

        def oval(pid: str, _m=opp_elo_map, _cache=_ov_cache) -> float:
            v = _cache.get(pid)
            if v is None:
                v = elo_to_value(_m.get(pid, 1500.0))
                _cache[pid] = v
            return v

        prior = acceptance_prior(member.user_id, acceptance_stats)
        weight = max(priority_weights.get(member.user_id, 1.0), 0.0)
        # trade.negmem (D-4, LLD §6.3) — the pair-constant M1 multiplier.
        # Distinct from the acceptance prior on the line above: different
        # math, same map (HLD §2.2). Resolved ONCE per pair here and applied
        # at card creation below — deliberately NOT inside _Candidate.score:
        # a pair-constant factor cannot change within-pair selection anyway,
        # and keeping it out of the candidate score leaves _pair_survivors,
        # the exposure/dedup machinery and the MESO layer byte-identical
        # (membership is never affected, R4).
        _nm_eff, _nm_stamp = 1.0, None
        if negmem_map is not None:
            _nm_eff = _negmem.effective_mult(negmem_map, member.user_id,
                                             strength=_c("negmem_strength"),
                                             floor=_c("negmem_floor"))
            if _nm_eff != 1.0:
                _nm_stamp = _negmem.stamp_payload(negmem_map, member.user_id,
                                                  _nm_eff)

        # survivors_raw keeps every gate-passer: the MESO layer needs the
        # near-equivalent alternates that batch dedup (deliberately)
        # removes from the emitted list.
        survivors_raw = _pair_survivors(
            opponent=member,
            players=players,
            user_roster=user_roster,
            user_known=set(user_value),
            uval=uval,
            oval=oval,
            cval=cval,
            scoring_format=scoring_format,
            untouchable_ids=untouchable_ids,
            target_ids=target_ids,
            not_interested_ids=not_interested_ids,
            past_decision_keys=past_decision_keys,
            accept_prior=prior,
            priority_weight=weight,
            report=report,
        )
        survivors = _dedup_batch(survivors_raw)
        per_pair[member.user_id] = survivors
        report.viable_by_opponent[member.user_id] = len(survivors)
        if not survivors:
            continue

        opp_profile = analyze_roster_strengths(member.roster, players,
                                               scoring_format)
        declared = declared_outlooks.get(member.user_id)
        if declared:
            opp_outlook = {"value": declared, "source": "declared"}
        else:
            inferred, _, _ = infer_team_outlook(
                member.roster, players,
                pick_shares.get(member.user_id, 0.0), num_teams)
            opp_outlook = {"value": inferred, "source": "inferred"}

        # No engine truncation (operator decision 2026-08-16): None ⇒ every
        # post-dedup survivor becomes a card; an int is a caller-owned
        # presentation limit only.
        if max_per_opponent is None:
            pair_pool = survivors
        else:
            pair_pool = survivors[:max(int(max_per_opponent), 1)]
        pair_cards: list[tuple[_Candidate, TradeCard]] = []
        for rank, cand in enumerate(pair_pool):
            gv, rv = _consensus_packages(cand.give_ids, cand.recv_ids, cval)
            card = TradeCard(
                trade_id=str(uuid.uuid4())[:8],
                league_id=league.league_id,
                proposing_user_id=user_id,
                target_user_id=member.user_id,
                target_username=member.username,
                give_player_ids=cand.give_ids,
                receive_player_ids=cand.recv_ids,
                mismatch_score=round(
                    _harmonic_mean(cand.user_gain, cand.opp_gain), 1),
                fairness_score=cand.fairness_ratio,
                composite_score=round(cand.score / 1500.0, 4),
                basis="divergence",
            )
            # trade.negmem — the pair-constant multiplier resolved above, on
            # the EMITTED card's composite only. Rounding is pinned at 4 dp
            # because that is the precision this constructor publishes one
            # line up; any other precision would change the formatting of
            # rows that must be byte-identical when the flag is off.
            if _nm_stamp is not None:
                card.negmem_stamp = _nm_stamp
                card.composite_score = round(card.composite_score * _nm_eff, 4)
            card.give_value = round(gv, 1)
            card.receive_value = round(rv, 1)
            # 2026-08-21 gap auto-sweetener — the equalizer was chosen back
            # in `_pair_survivors` (so that dedup, MESO, the rationale and
            # the tier ranking all saw the sweetened ids); this only moves
            # the record onto the card. `server.py` already reads
            # `card.gap_sweetener` generically for both the
            # `deck_impressions.features_json` spine and the card payload,
            # so arm C needs no serving-layer change — it simply stops
            # being null there.
            card.gap_sweetener = cand.gap_sweetener
            card.rationale = _rationale(cand, players, cval, user_profile,
                                        opp_profile, opp_outlook)
            card.health = {
                "joint_gain": cand.joint_gain,
                "split_ratio": cand.split_ratio,
                "ir_margin_user": round(cand.user_gain - _c("gen2_epsilon"), 1),
                "ir_margin_opp": round(cand.opp_gain - _c("gen2_epsilon"), 1),
                "band_position": cand.band_position,
                "fairness_ratio": cand.fairness_ratio,
                "accept_prior": cand.accept_prior,
                "symmetry": cand.symmetry,
            }
            if rank == 0:
                variants = _meso_variants(cand, survivors_raw, players, cval)
                if variants:
                    card.meso_variants = variants
            pair_cards.append((cand, card))

        all_selected.extend(pair_cards)
        if on_opponent_done is not None:
            try:
                snapshot = [c for _, c in sorted(
                    all_selected, key=lambda t: t[0].score, reverse=True)]
                on_opponent_done(idx + 1, total, snapshot)
            except Exception:
                pass

    # Stage 6 — league-level exposure shaping (round-1/03 BP 1-2), as
    # ORDERING rather than truncation (operator decision 2026-08-16):
    # the floor-first + cap-greedy selection builds the HEAD of the list
    # (every viable counterparty guaranteed head presence; no counterparty
    # over-represented in the head); cap-overflow cards are demoted below
    # the head IN RANK ORDER, never dropped. The full survivor set ships.
    cap = max(int(_c("gen2_exposure_cap")), 1)
    floor_n = max(int(_c("gen2_exposure_floor")), 0)

    ranked = sorted(all_selected,
                    key=lambda t: (t[0].score, t[0].symmetry), reverse=True)
    head_counts: dict[str, int] = defaultdict(int)
    head: list[tuple[_Candidate, TradeCard]] = []
    head_ids: set[str] = set()

    if floor_n > 0:
        by_opp: dict[str, list[tuple[_Candidate, TradeCard]]] = defaultdict(list)
        for pair in ranked:
            by_opp[pair[0].opponent_id].append(pair)
        for uid, group in by_opp.items():
            for pair in group[:floor_n]:
                head.append(pair)
                head_ids.add(pair[1].trade_id)
                head_counts[uid] += 1

    for pair in ranked:
        cand, card = pair
        if card.trade_id in head_ids:
            continue
        if head_counts[cand.opponent_id] >= cap:
            continue
        head.append(pair)
        head_ids.add(card.trade_id)
        head_counts[cand.opponent_id] += 1

    head.sort(key=lambda t: (t[0].score, t[0].symmetry), reverse=True)
    tail = [pair for pair in ranked if pair[1].trade_id not in head_ids]
    ordered = head + tail

    # Stage 7 — tier metadata: scarcity lives here, not in list length.
    # endorsed = the single best mutual pick of the cycle (at most 1);
    # featured = the next gen2_featured_count by final rank; browse =
    # every remaining survivor, still ranked.
    featured_n = max(int(_c("gen2_featured_count")), 0)
    for i, (_cand, card) in enumerate(ordered):
        if i == 0:
            card.tier = "endorsed"
        elif i <= featured_n:
            card.tier = "featured"
        else:
            card.tier = "browse"

    cards = [c for _, c in ordered]

    full_counts: dict[str, int] = defaultdict(int)
    for cand, _card in ordered:
        full_counts[cand.opponent_id] += 1
    report.exposure_by_opponent = dict(full_counts)
    report.shaped_head_by_opponent = dict(head_counts)
    report.emitted = len(cards)
    gate_b_entrants = (report.considered - report.composition_rejects
                       - report.net_cap_rejects - report.pick_band_rejects
                       - report.feasibility_rejects)
    report.ir_rate = ((gate_b_entrants - report.ir_rejects)
                      / gate_b_entrants) if gate_b_entrants > 0 else 0.0
    if ordered:
        report.mean_split_ratio = round(
            sum(c.split_ratio for c, _ in ordered) / len(ordered), 4)
        report.mean_symmetry = round(
            sum(c.symmetry for c, _ in ordered) / len(ordered), 4)

    try:
        logger.info("trade_gen_v2 report %s", json.dumps(report.as_dict()))
    except Exception:                                # pragma: no cover
        pass

    return cards, report
