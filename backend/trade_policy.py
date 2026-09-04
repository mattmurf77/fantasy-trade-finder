"""
backend/trade_policy.py — the ONE trade-policy evaluator.

Scope block: docs/plans/personal-market-policy/scope.md
Decisions:   living-memory/DECISIONS.md D-180 (constraint, not objective),
             D-181 (policy is an orthogonal dimension, not a fourth arm).

The product decision this module encodes
----------------------------------------
Consensus value answers **"is this trade plausible in the wider dynasty
market?"**.  It is a hard, non-bypassable eligibility guardrail — not 30% of a
blended objective.  Personal rankings answer **"which of the plausible trades
are these two managers uniquely positioned to prefer?"** and become the primary
ordering signal.  Ranking **confidence** — applied symmetrically to BOTH
managers — controls how far the engine may depart from consensus.

Why one module
--------------
Before this, threshold logic lived in three places (`trade_service`'s v2 pair
generator, `trade_optimizer`'s v3 package search, and the several post-generation
mutation paths in `server.py`) and each of them could reach the deck by a route
the others did not gate.  `fairness_floor_divergence` at 0.55, the relaxed
fallback, sweeteners, swaps, likes-you injection, wildcards and weekly
replenishment were six separate ways for a card to arrive at a user having
cleared a *different* bar than the one the product intended.  Every one of them
now funnels through :func:`evaluate_trade_policy`.

Leaf-module discipline
----------------------
Nothing here imports `server`.  `trade_service` and `trade_optimizer` are
imported **lazily inside functions** — `trade_optimizer` already imports
`trade_service`, and `trade_service` lazily imports `trade_optimizer`, so a
top-level import either way would cycle.  The lazy `trade_service._c` read is
also what makes this module honour a bake-off arm's thread-local
`_cfg_override` overlay: an arm evaluating its own candidates reads its own
knobs, exactly as its generator did.

Flag posture
------------
Two flags, both defaulting False in code and in `config/features.json`:

* ``trade.valuation_telemetry``  — Phase 1/2.  Snapshots, concept ids,
  policy-variant stamping, shadow evaluation, proposal records.  Additive
  writes only; eligibility and ordering are untouched.
* ``trade.personal_market_policy_v1`` — Phase 3.  The evaluator actually gates
  and orders.

With BOTH off, no caller in the tree changes a single value it computes, a
single card it emits, or a single column it writes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: `policy_variant` values.  Stamped on every impression INDEPENDENTLY of
#: `model_arm`: the three generators keep generating inside both variants, and
#: the question "did the policy help?" is a different question from "which
#: generator produced this card?".
POLICY_LEGACY = "legacy"
POLICY_V1 = "personal_market_v1"

#: Bump when the shape of the valuation snapshot changes.  Readers MUST branch
#: on it rather than assuming keys exist.
VALUATION_SCHEMA_VERSION = 1

#: Bump when the canonical concept hash's INPUTS change.  A bump makes old and
#: new ids incomparable on purpose — it is the version, not a salt.
CONCEPT_SCHEMA_VERSION = 1

#: Deck lanes.
LANE_CORE = "core"
LANE_CONVICTION = "conviction"
LANE_FALLBACK = "fallback"

#: `value_basis` — what the card's personal math actually rests on.
BASIS_TWO_BOARD = "two_board"
BASIS_ONE_BOARD = "one_board"
BASIS_CONSENSUS = "consensus"

#: Confidence provenance.  `legacy` is the fail-safe for a stored ranking row
#: written before confidence persistence existed: it is treated as the LOWEST
#: confidence, never as full trust.
SOURCE_VOTES = "votes"
SOURCE_SEED = "seed"
SOURCE_CROSS_FORMAT = "cross_format"
SOURCE_EXPLICIT = "explicit"
SOURCE_LEGACY = "legacy"

#: Rejection reasons.  Stored verbatim in `trade_policy_shadow.reason` and in
#: the snapshot's `policy.rejection_reason`, so they are a stable vocabulary.
REASON_EMPTY_PACKAGE = "empty_package"
REASON_BELOW_FLOOR = "below_effective_floor"
REASON_BELOW_ABSOLUTE = "below_absolute_floor"
REASON_NO_MUTUAL_GAIN = "no_two_sided_gain"
REASON_ROSTER_CHANGED = "roster_changed"
REASON_MARKET_DRIFT = "market_drift"
REASON_EXPIRED = "expired"
REASON_ALREADY_RESOLVED = "already_resolved"

_EPS = 1e-9


# ---------------------------------------------------------------------------
# Config access
# ---------------------------------------------------------------------------

def _c(key: str) -> float:
    """Read a `model_config` knob through `trade_service`.

    Lazy import on purpose (see the module docstring): it avoids the import
    cycle AND it resolves through whatever thread-local `_cfg_override` overlay
    a bake-off arm has entered, so an arm's candidates are judged under the
    arm's own configuration.
    """
    from .trade_service import _c as _ts_c
    return _ts_c(key)


def policy_enabled() -> bool:
    """`trade.personal_market_policy_v1` — does the evaluator GATE and ORDER?"""
    from .feature_flags import is_enabled
    return is_enabled("trade.personal_market_policy_v1")


def telemetry_enabled() -> bool:
    """`trade.valuation_telemetry` — do we snapshot, stamp and shadow-evaluate?"""
    from .feature_flags import is_enabled
    return is_enabled("trade.valuation_telemetry")


def active_policy_variant() -> str:
    """The variant this job is running under.  One value per deck job — a deck
    must never mix variants (brief, Phase 3), which is why this is read once at
    job start and threaded, never re-read per card."""
    return POLICY_V1 if policy_enabled() else POLICY_LEGACY


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def confidence_weight_for(
    comparison_count: Optional[float],
    source: Optional[str] = None,
) -> float:
    """The per-player confidence weight `w` in

        effective_elo = w * personal_elo + (1 - w) * consensus_elo

    Comparison-based evidence keeps the existing shape ``n / (n + n0)`` with
    ``n0 = shrink_pseudocount``.  Other provenances are flat, configurable
    constants — they are experiment settings, not permanent truths, which is
    why none of them is hard-coded here.

    **Fail-safe.** A missing count with no recognised source returns 0.0 —
    "no evidence" prices the player at consensus and buys the trade no floor
    relief.  That is the conservative direction: weak evidence must make the
    engine LESS willing to depart from the market, never more.
    """
    if source == SOURCE_EXPLICIT:
        return _clamp01(_c("conf_source_explicit"))
    if source == SOURCE_CROSS_FORMAT:
        return _clamp01(_c("conf_source_cross_format"))
    if source == SOURCE_SEED:
        return _clamp01(_c("conf_source_seed"))
    # SOURCE_VOTES, SOURCE_LEGACY, None — decided by the count, and a legacy
    # row has none, so it lands at 0.0.
    try:
        n = max(float(comparison_count or 0.0), 0.0)
    except (TypeError, ValueError):
        n = 0.0
    n0 = _c("shrink_pseudocount")
    if n0 <= 0:
        return 1.0 if n > 0 else 0.0
    return _clamp01(n / (n + n0))


def confidence_map(
    comparison_counts: Optional[dict],
    *,
    source: Optional[str] = None,
    weights: Optional[dict] = None,
) -> dict:
    """Build ``{pid: weight}`` from whichever evidence a board carries.

    `weights` (a persisted ``member_rankings.confidence_weight`` column) wins
    when present — it is what the writing session actually computed.  Otherwise
    the counts are converted here.  Both absent ⇒ an empty map, and
    :func:`shrink_board` then prices the whole board at consensus.
    """
    result = {pid: confidence_weight_for(n, source)
              for pid, n in (comparison_counts or {}).items()}
    result.update({pid: _clamp01(w) for pid, w in (weights or {}).items()
                   if w is not None})
    return result


def shrink_board(
    personal_elo: dict,
    seed_elo: dict,
    conf: Optional[dict],
    *,
    placements: Optional[dict] = None,
    default_weight: float = 0.0,
) -> dict:
    """Confidence-shrink ONE board toward consensus.  Symmetric by
    construction: the viewer and the partner call the identical function with
    the identical rule.

    This is deliberately NOT `trade_service._shrink_user_elo`.  That function
    carries two legacy behaviours the policy must not inherit:

    * ``confidence=None`` returns the board **raw** ("no information ⇒ no
      shrinkage").  For a partner board that is precisely backwards — no
      information is exactly when the engine must stay at consensus.
    * ``user_elo_shrink = 0`` (the landability challenger's pin) skips
      shrinkage entirely.  The policy floor's confidence discount would then be
      buying relief from evidence the values never used.

    `placements` (the D-085 tier clamp) is honoured when supplied, so the
    viewer's own placed players are still priced inside the tier they were
    placed in.  Only the viewer has placements; the partner's snapshot carries
    none, and passing None there is correct rather than a gap.
    """
    conf = conf or {}
    n_place = placements if (placements and _c("placement_tier_clamp") > 0) else None
    out: dict = {}
    for pid, elo in personal_elo.items():
        w = conf.get(pid)
        w = default_weight if w is None else _clamp01(float(w))
        seed = seed_elo.get(pid, 1500.0)
        blended = w * elo + (1.0 - w) * seed
        if n_place is not None:
            band = n_place.get(pid)
            if band is not None:
                blended = min(max(blended, band[0]), band[1])
        out[pid] = blended
    return out


def confidence_band(trade_confidence: float) -> str:
    """`high` / `medium` / `low` — the privacy-safe confidence label a card may
    show.  It never reveals the counterparty's counts, only which band the
    WEAKER of the two boards falls in."""
    if trade_confidence >= _c("policy_confidence_band_high"):
        return "high"
    if trade_confidence >= _c("policy_confidence_band_med"):
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Package math
# ---------------------------------------------------------------------------

def _package_pair(give_values: Sequence[float],
                  recv_values: Sequence[float]) -> tuple[float, float]:
    """(give_package, receive_package) in ONE value space, using the trade-wide
    reference asset — the same `package_value_v2` convention every generator
    and the manual calculator use.  Never a plain sum: package discounts,
    crown/stud treatment and the diminishing-returns curve all live in there,
    and the brief is explicit that the policy gate must not implement a second
    simplified sum."""
    from .trade_service import package_value_v2
    if not give_values or not recv_values:
        return (0.0, 0.0)
    v_max = max(list(give_values) + list(recv_values))
    return (
        package_value_v2(list(give_values), v_max,
                         n_other=len(recv_values), other_values=list(recv_values)),
        package_value_v2(list(recv_values), v_max,
                         n_other=len(give_values), other_values=list(give_values)),
    )


def compute_market_ratio(give_ids: Sequence[str], recv_ids: Sequence[str],
                         consensus_value: Callable[[str], float]
                         ) -> tuple[float, float, float]:
    """(consensus_give, consensus_receive, market_ratio).

    Uses `trade_optimizer._consensus_packages`, which is the SAME function the
    manual calculator prices with — acceptance criterion "finder and calculator
    consensus package values remain identical" is satisfied by construction,
    not by a parallel implementation kept in sync by hand.
    """
    if not give_ids or not recv_ids:
        return (0.0, 0.0, 0.0)
    from .trade_optimizer import _consensus_packages
    gv, rv = _consensus_packages(list(give_ids), list(recv_ids), consensus_value)
    if gv <= 0 or rv <= 0:
        return (gv, rv, 0.0)
    return (gv, rv, min(gv, rv) / max(gv, rv))


def compute_package_confidence(ids: Sequence[str],
                               consensus_value: Callable[[str], float],
                               weight_of: Callable[[str], float]) -> float:
    """Consensus-value-weighted mean confidence across a package.

    Value-weighted rather than a plain mean so a 200-point filler cannot drag a
    package built around a well-ranked centrepiece into the "weak evidence"
    band — and, symmetrically, so a well-known filler cannot vouch for a
    centrepiece the manager has never compared.
    """
    ids = list(ids)
    if not ids:
        return 0.0
    total = 0.0
    acc = 0.0
    for pid in ids:
        v = max(float(consensus_value(pid) or 0.0), 0.0)
        total += v
        acc += v * _clamp01(weight_of(pid))
    if total <= _EPS:
        # Every asset priced at zero — no value to weight by, so fall back to a
        # plain mean rather than dividing by zero or claiming full confidence.
        return _clamp01(sum(_clamp01(weight_of(p)) for p in ids) / len(ids))
    return _clamp01(acc / total)


def compute_personal_opportunity(viewer_gain_pct: float,
                                 partner_gain_pct: float) -> float:
    """The WEAKER manager's normalized gain.

    Deliberately `min`, not a mean or a harmonic mean: a trade that is
    excellent for one side and barely positive for the other must rank below a
    trade that is meaningfully positive for both.  The harmonic mutual surplus
    survives as a secondary signal (it is monotone in two-sided benefit) but it
    is no longer what decides the order.
    """
    return min(viewer_gain_pct, partner_gain_pct)


def derive_policy_floor(*, two_board: bool, trade_confidence: float,
                        normalized_strength: float) -> float:
    """The market-ratio floor this trade must clear, before the user's own
    preference is composed in.

    Monotone by construction: both discounts are subtracted, and both inputs
    are clamped to [0, 1], so **increasing** confidence or the weaker side's
    gain can only ever LOWER the floor.  The result is clamped into
    ``[market_floor_absolute, market_floor_two_board_base]`` so no combination
    of knobs can produce a floor below the absolute minimum or above the base.

    **The surplus discount is itself scaled by confidence.**  A large
    two-sided "gain" measured on boards nobody has actually ranked is not
    evidence of anything — it is the arithmetic of two consensus copies
    drifting apart, and letting it buy floor relief would reopen the exact
    hole this design closes: low confidence making the engine *more* willing
    to leave the market.  Without this scaling the brief's own worked example
    contradicts its own test 2 (weak-confidence divergence would reach 0.75,
    not "approximately 0.80"), and the test is the one that matches the
    stated intent.  Monotonicity survives: the product of two non-decreasing
    clamped terms is non-decreasing in each.
    """
    absolute = _c("market_floor_absolute")
    if not two_board:
        return max(_c("market_floor_one_board"), absolute)
    base = _c("market_floor_two_board_base")
    conf = _clamp01(trade_confidence)
    floor = (base
             - _c("market_floor_confidence_discount") * conf
             - _c("market_floor_surplus_discount")
               * _clamp01(normalized_strength) * conf)
    return min(max(floor, absolute), max(base, absolute))


def compose_effective_floor(policy_floor: float,
                            requested_floor: Optional[float]) -> float:
    """``max(policy_floor, user_requested_floor)``.

    This is the correction the brief singles out.  The live divergence path
    composes with ``min(...)``, so a user asking for a stricter 0.75 band was
    handed the looser 0.55 divergence floor — their stated preference made the
    gate *weaker*.  A preference may tighten policy.  It may never loosen it.

    The absolute floor is re-imposed here as well, so this function alone is
    sufficient to guarantee "no finder card below `market_floor_absolute`"
    regardless of what a caller passes in.
    """
    absolute = _c("market_floor_absolute")
    req = 0.0 if requested_floor is None else float(requested_floor)
    return max(policy_floor, req, absolute)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BoardValuation:
    """One manager's view of the trade, in that manager's own value space.

    Direction is VIEWER-CENTERED throughout, for both managers:
    ``gives``/``receives`` always name the *card's* give and receive sides.
    The partner gives the card's receive side, so `partner.gives_*` is the
    partner's valuation of the card's RECEIVE side.  Keeping one direction
    convention across both boards is what makes the reversal test
    (swap the managers, swap the sides ⇒ identical magnitudes) meaningful.
    """
    source: str                       # "personal" | "consensus"
    gives_raw: Optional[float]
    receives_raw: Optional[float]
    gives_effective: Optional[float]
    receives_effective: Optional[float]
    effective_surplus: Optional[float]
    gain_pct: Optional[float]
    package_confidence: Optional[float]

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "gives_raw": _r(self.gives_raw),
            "receives_raw": _r(self.receives_raw),
            "gives_effective": _r(self.gives_effective),
            "receives_effective": _r(self.receives_effective),
            "effective_surplus": _r(self.effective_surplus),
            "gain_pct": _r(self.gain_pct, 4),
            "package_confidence": _r(self.package_confidence, 4),
        }

    @staticmethod
    def consensus_only() -> "BoardValuation":
        """The honest shape for a manager with no real board: `consensus`
        source and NULL personal/confidence fields.  Never a copy of consensus
        dressed as a personal board — the brief forbids manufacturing one, and
        a fabricated board would make a one-board card indistinguishable from a
        proven mutual win in every later query."""
        return BoardValuation(BASIS_CONSENSUS, None, None, None, None,
                              None, None, None)


@dataclass(frozen=True)
class PolicyResult:
    """Immutable verdict + the complete snapshot used for telemetry."""
    eligible: bool
    reason: Optional[str]
    lane: str
    basis: str
    market_ratio: float
    market_gives: float
    market_receives: float
    requested_floor: float
    policy_floor: float
    effective_floor: float
    viewer: BoardValuation
    partner: BoardValuation
    personal_opportunity: Optional[float]
    harmonic_effective_surplus: Optional[float]
    trade_confidence: float
    policy_variant: str
    valuation: dict = field(default_factory=dict)

    # -- ordering -----------------------------------------------------------
    @property
    def rank_key(self) -> tuple:
        """Primary ordering key for eligible cards.

        `personal_opportunity` first (the weaker manager's gain), harmonic
        mutual surplus second, and consensus closeness only as the final
        tie-break INSIDE a lane.  Consensus closeness is deliberately last:
        promoting it would quietly restore the 70/30 blended objective under a
        new name, which is the thing this change exists to stop.
        """
        return (
            -(self.personal_opportunity if self.personal_opportunity is not None else -1e9),
            -(self.harmonic_effective_surplus or 0.0),
            -self.market_ratio,
        )

    def client_payload(self) -> dict:
        """The privacy-safe subset a card may expose.  Carries NO opponent
        values, NO opponent ranking positions and NO counts — only the band the
        weaker board falls in and which lane the card is in."""
        return {
            "market_fairness": round(self.market_ratio, 3),
            "value_basis": self.basis,
            "confidence_band": confidence_band(self.trade_confidence),
            "opportunity_label": self.lane,
        }


# ---------------------------------------------------------------------------
# The evaluator
# ---------------------------------------------------------------------------

def evaluate_trade_policy(
    *,
    give_ids: Sequence[str],
    receive_ids: Sequence[str],
    consensus_value: Callable[[str], float],
    viewer_effective_value: Callable[[str], float],
    partner_effective_value: Optional[Callable[[str], float]] = None,
    viewer_raw_value: Optional[Callable[[str], float]] = None,
    partner_raw_value: Optional[Callable[[str], float]] = None,
    viewer_confidence_of: Optional[Callable[[str], float]] = None,
    partner_confidence_of: Optional[Callable[[str], float]] = None,
    requested_floor: Optional[float] = None,
    scoring_format: str = "1qb_ppr",
    partner_has_board: bool = True,
    relaxed: bool = False,
    model_arm: Optional[str] = None,
    policy_variant: Optional[str] = None,
    value_model_version: str = "package-v2",
    consensus_asof: Optional[str] = None,
    viewer_board_updated_at: Optional[str] = None,
    partner_board_updated_at: Optional[str] = None,
    snapshot_stage: str = "serve",
) -> PolicyResult:
    """Evaluate ONE fully-assembled package.  Every generator and every
    post-generation mutation calls this after its final package exists.

    Generation may still use cheap prefilters — this is not a claim that the
    evaluator is the only check, only that it is the LAST one, and that no card
    reaches a user without having passed it.  That distinction is what makes
    the sweetener and swap paths safe: they change the package, so their
    pre-mutation verdict is void and they must re-ask.
    """
    give_ids = list(give_ids or [])
    receive_ids = list(receive_ids or [])
    variant = policy_variant or active_policy_variant()

    if not give_ids or not receive_ids:
        return _reject_shell(REASON_EMPTY_PACKAGE, variant, scoring_format,
                             give_ids, receive_ids, requested_floor)

    # ---- consensus plausibility ------------------------------------------
    m_gives, m_recvs, ratio = compute_market_ratio(
        give_ids, receive_ids, consensus_value)

    # ---- confidence -------------------------------------------------------
    v_conf_of = viewer_confidence_of or (lambda _pid: 0.0)
    p_conf_of = partner_confidence_of or (lambda _pid: 0.0)
    two_board = bool(partner_has_board and partner_effective_value is not None)

    viewer_pkg_conf = _clamp01(min(
        compute_package_confidence(give_ids, consensus_value, v_conf_of),
        compute_package_confidence(receive_ids, consensus_value, v_conf_of),
    ))
    if two_board:
        partner_pkg_conf = _clamp01(min(
            compute_package_confidence(give_ids, consensus_value, p_conf_of),
            compute_package_confidence(receive_ids, consensus_value, p_conf_of),
        ))
    else:
        partner_pkg_conf = 0.0
    trade_conf = min(viewer_pkg_conf, partner_pkg_conf) if two_board else 0.0

    # ---- both managers' package values -----------------------------------
    waiver = _c("waiver_slot_cost")
    extra = len(receive_ids) - len(give_ids)

    viewer = _board_valuation(
        give_ids, receive_ids, viewer_effective_value, viewer_raw_value,
        viewer_pkg_conf, waiver_on_receives=waiver * extra if extra > 0 else 0.0)

    if two_board:
        # The partner GIVES the card's receive side and RECEIVES its give side,
        # so their waiver cost lands when THEY take on more bodies (extra < 0).
        partner = _board_valuation(
            give_ids, receive_ids, partner_effective_value, partner_raw_value,
            partner_pkg_conf,
            waiver_on_receives=waiver * (-extra) if extra < 0 else 0.0,
            mirrored=True)
    else:
        partner = BoardValuation.consensus_only()

    # ---- two-sided personal opportunity ----------------------------------
    if two_board and viewer.gain_pct is not None and partner.gain_pct is not None:
        opportunity = compute_personal_opportunity(viewer.gain_pct,
                                                   partner.gain_pct)
        harmonic = _harmonic(viewer.effective_surplus or 0.0,
                             partner.effective_surplus or 0.0)
        basis = BASIS_TWO_BOARD
    else:
        opportunity = None
        harmonic = None
        basis = BASIS_ONE_BOARD if viewer.source == "personal" else BASIS_CONSENSUS

    strength = _clamp01((opportunity or 0.0) / max(_c("policy_surplus_norm"), _EPS))

    # ---- floors -----------------------------------------------------------
    policy_floor = derive_policy_floor(two_board=two_board,
                                       trade_confidence=trade_conf,
                                       normalized_strength=strength)
    eff_floor = compose_effective_floor(policy_floor, requested_floor)

    # ---- verdict ----------------------------------------------------------
    # The POINT ratio must clear the floor.  Uncertainty ranges may inform
    # display or secondary ranking, but they may never rescue a point ratio
    # below the hard floor — low confidence has to make the engine more
    # conservative, and the range-overlap path did the opposite.
    #
    # Two-sided personal gain is a CONVICTION requirement, not a blanket
    # eligibility test. The distinction matters and was got wrong first time:
    #
    #  * A Core card (ratio at or above `market_core_ratio`) is market-
    #    plausible on its own terms. It does not need personal evidence to
    #    justify itself, and rejecting it for failing a gain test the
    #    GENERATOR never applied would delete ordinary fair trades.
    #  * A Conviction card is below Core precisely because the market thinks
    #    it is lopsided. The only thing that earns it a slot is two real,
    #    sufficiently confident boards that BOTH gain — so there, a
    #    non-positive two-sided gain is disqualifying.
    #
    # This also keeps the policy from double-gating on two different value
    # bases. The engine's own `min_side_surplus` gate runs on MARGINAL
    # (over-replacement) values when `trade.marginal_value` is on; the policy
    # deliberately runs on raw confidence-shrunk personal values, which are
    # arm-independent and comparable across the bake-off. Applying the
    # policy's basis as a second universal veto would silently re-litigate
    # every card the generator already cleared, under a definition the
    # generator does not use.
    reason: Optional[str] = None
    if ratio < _c("market_floor_absolute") - _EPS:
        reason = REASON_BELOW_ABSOLUTE
    elif ratio < eff_floor - _EPS:
        reason = REASON_BELOW_FLOOR

    is_core = ratio >= _c("market_core_ratio") - _EPS
    if reason is None and two_board and not is_core:
        min_gain = _c("personal_gain_min_frac")
        if opportunity is None or opportunity < min_gain:
            reason = REASON_NO_MUTUAL_GAIN

    eligible = reason is None
    if not eligible:
        lane = "ineligible"
    elif not two_board:
        lane = LANE_FALLBACK
    elif is_core:
        lane = LANE_CORE
    else:
        lane = LANE_CONVICTION

    result = PolicyResult(
        eligible=eligible,
        reason=reason,
        lane=lane,
        basis=basis,
        market_ratio=round(ratio, 4),
        market_gives=round(m_gives, 2),
        market_receives=round(m_recvs, 2),
        requested_floor=float(requested_floor or 0.0),
        policy_floor=round(policy_floor, 4),
        effective_floor=round(eff_floor, 4),
        viewer=viewer,
        partner=partner,
        personal_opportunity=(round(opportunity, 4)
                              if opportunity is not None else None),
        harmonic_effective_surplus=(round(harmonic, 2)
                                    if harmonic is not None else None),
        trade_confidence=round(trade_conf, 4),
        policy_variant=variant,
    )

    snapshot = build_valuation_snapshot(
        result,
        give_ids=give_ids, receive_ids=receive_ids,
        consensus_value=consensus_value,
        viewer_effective_value=viewer_effective_value,
        partner_effective_value=partner_effective_value if two_board else None,
        viewer_raw_value=viewer_raw_value,
        partner_raw_value=partner_raw_value if two_board else None,
        viewer_confidence_of=v_conf_of,
        partner_confidence_of=p_conf_of if two_board else None,
        scoring_format=scoring_format,
        relaxed=relaxed,
        model_arm=model_arm,
        value_model_version=value_model_version,
        consensus_asof=consensus_asof,
        viewer_board_updated_at=viewer_board_updated_at,
        partner_board_updated_at=partner_board_updated_at,
        snapshot_stage=snapshot_stage,
    )
    return _with_snapshot(result, snapshot)


def _board_valuation(give_ids, receive_ids, eff_value, raw_value,
                     pkg_conf, *, waiver_on_receives: float = 0.0,
                     mirrored: bool = False) -> BoardValuation:
    """Price both sides in ONE manager's value space.

    `mirrored=True` is the partner: they give the card's receive side, so their
    surplus is (their value of the give side) − (their value of the receive
    side).  Both boards keep viewer-centered FIELD names — `gives_*` is always
    the card's give side — so the two dicts are directly comparable and the
    reversal test can assert magnitude equality field by field.
    """
    g_eff = [float(eff_value(p)) for p in give_ids]
    r_eff = [float(eff_value(p)) for p in receive_ids]
    g_pkg, r_pkg = _package_pair(g_eff, r_eff)

    if raw_value is not None:
        g_raw_vals = [float(raw_value(p)) for p in give_ids]
        r_raw_vals = [float(raw_value(p)) for p in receive_ids]
        g_raw, r_raw = _package_pair(g_raw_vals, r_raw_vals)
    else:
        g_raw, r_raw = None, None

    if mirrored:
        # The partner receives the GIVE side, so the waiver hit lands there.
        g_pkg = g_pkg - waiver_on_receives
        surplus = g_pkg - r_pkg
        denom = max(r_pkg, _EPS)          # what the partner gives up
    else:
        r_pkg = r_pkg - waiver_on_receives
        surplus = r_pkg - g_pkg
        denom = max(g_pkg, _EPS)          # what the viewer gives up

    return BoardValuation(
        source="personal",
        gives_raw=g_raw,
        receives_raw=r_raw,
        gives_effective=g_pkg,
        receives_effective=r_pkg,
        effective_surplus=surplus,
        gain_pct=surplus / denom,
        package_confidence=pkg_conf,
    )


def _reject_shell(reason: str, variant: str, scoring_format: str,
                  give_ids, receive_ids,
                  requested_floor) -> PolicyResult:
    """A degenerate package (one side empty) can be rejected without pricing
    anything.  Still returns a full PolicyResult so callers never branch on
    None."""
    empty = BoardValuation.consensus_only()
    res = PolicyResult(
        eligible=False, reason=reason, lane="ineligible",
        basis=BASIS_CONSENSUS, market_ratio=0.0, market_gives=0.0,
        market_receives=0.0, requested_floor=float(requested_floor or 0.0),
        policy_floor=_c("market_floor_one_board"),
        effective_floor=compose_effective_floor(_c("market_floor_one_board"),
                                                requested_floor),
        viewer=empty, partner=empty, personal_opportunity=None,
        harmonic_effective_surplus=None, trade_confidence=0.0,
        policy_variant=variant,
    )
    return _with_snapshot(res, {
        "schema_version": VALUATION_SCHEMA_VERSION,
        "scoring_format": scoring_format,
        "basis": BASIS_CONSENSUS,
        "policy": {"policy_version": variant, "rejection_reason": reason,
                   "eligible": False},
        "assets": {"give": list(give_ids), "receive": list(receive_ids)},
    })


def _with_snapshot(result: PolicyResult, snapshot: dict) -> PolicyResult:
    """PolicyResult is frozen; rebuild it with the snapshot attached."""
    return PolicyResult(
        eligible=result.eligible, reason=result.reason, lane=result.lane,
        basis=result.basis, market_ratio=result.market_ratio,
        market_gives=result.market_gives, market_receives=result.market_receives,
        requested_floor=result.requested_floor, policy_floor=result.policy_floor,
        effective_floor=result.effective_floor, viewer=result.viewer,
        partner=result.partner,
        personal_opportunity=result.personal_opportunity,
        harmonic_effective_surplus=result.harmonic_effective_surplus,
        trade_confidence=result.trade_confidence,
        policy_variant=result.policy_variant, valuation=snapshot,
    )


# ---------------------------------------------------------------------------
# Generator seam
# ---------------------------------------------------------------------------

def make_pair_evaluator(*, consensus_value, viewer_effective_value,
                        viewer_raw_value, viewer_confidence_of,
                        opponent, seed_elo, requested_floor,
                        scoring_format="1qb_ppr", model_arm=None,
                        force: bool = False, viewer_elo=None, viewer_counts=None,
                        viewer_placements=None):
    """Bind one (viewer, opponent) pair into a ``fn(give_ids, recv_ids) ->
    PolicyResult`` for use inside a generator's candidate loop.

    Returns **None** when `trade.personal_market_policy_v1` is off (and
    `force` was not passed), which is what lets every caller write

        if _pol is not None and not _pol(g, r).eligible:
            return

    and be byte-identical with the flag off — one `is None` check, no
    evaluation, no allocation.

    The opponent's board is confidence-shrunk HERE, from the `LeagueMember`'s
    persisted `comparison_counts` / `confidence_weights`. That is the whole
    point of the schema change: before it, `_vo` in v2 and `_vo` in v3 both
    read `opponent.elo_ratings` raw, so the engine trusted a league-mate's
    board more than the requesting user's own.

    A member without `has_rankings` gets no partner board at all — not a
    consensus copy. Copying consensus into a "personal" board would make a
    one-board card indistinguishable from a proven mutual win.

    `force=True` builds the evaluator regardless of the flag. Used by shadow
    evaluation and by tests; it never changes what a generator does, because
    the generators only ever call this without it.
    """
    if not (force or policy_enabled()):
        return None

    from .trade_service import elo_to_value

    if viewer_elo is not None:
        v_conf = confidence_map(viewer_counts, source=SOURCE_VOTES)
        v_conf.update({pid: confidence_weight_for(None, SOURCE_EXPLICIT)
                       for pid in viewer_placements or {}})
        v_eff = shrink_board(viewer_elo, seed_elo, v_conf, placements=viewer_placements)
        v_values = {pid: elo_to_value(e) for pid, e in v_eff.items()}
        v_raw = {pid: elo_to_value(e) for pid, e in viewer_elo.items()}
        viewer_effective_value = lambda pid: v_values.get(pid, consensus_value(pid))
        viewer_raw_value = lambda pid: v_raw.get(pid, consensus_value(pid))
        viewer_confidence_of = lambda pid: v_conf.get(pid, 0.)

    has_board = bool(getattr(opponent, "has_rankings", False)
                     and getattr(opponent, "elo_ratings", None))
    if has_board:
        o_conf = confidence_map(
            getattr(opponent, "comparison_counts", None),
            source=getattr(opponent, "confidence_source", None) or SOURCE_VOTES,
            weights=getattr(opponent, "confidence_weights", None))
        o_eff = shrink_board(opponent.elo_ratings, seed_elo, o_conf)
        o_eff_val = {pid: elo_to_value(e) for pid, e in o_eff.items()}
        o_raw_val = {pid: elo_to_value(e)
                     for pid, e in opponent.elo_ratings.items()}

        def _o_eff(pid):
            v = o_eff_val.get(pid)
            return v if v is not None else consensus_value(pid)

        def _o_raw(pid):
            v = o_raw_val.get(pid)
            return v if v is not None else consensus_value(pid)

        def _o_conf_of(pid):
            return o_conf.get(pid, 0.0)
    else:
        _o_eff = _o_raw = _o_conf_of = None

    board_at = getattr(opponent, "board_updated_at", None)

    def _evaluate(give_ids, recv_ids, *, relaxed: bool = False):
        return evaluate_trade_policy(
            give_ids=give_ids, receive_ids=recv_ids,
            consensus_value=consensus_value,
            viewer_effective_value=viewer_effective_value,
            viewer_raw_value=viewer_raw_value,
            viewer_confidence_of=viewer_confidence_of,
            partner_effective_value=_o_eff,
            partner_raw_value=_o_raw,
            partner_confidence_of=_o_conf_of,
            partner_has_board=has_board,
            requested_floor=requested_floor,
            scoring_format=scoring_format,
            relaxed=relaxed,
            model_arm=model_arm,
            partner_board_updated_at=board_at,
        )

    return _evaluate


# ---------------------------------------------------------------------------
# Telemetry snapshot
# ---------------------------------------------------------------------------

def build_valuation_snapshot(
    result: PolicyResult, *,
    give_ids, receive_ids, consensus_value,
    viewer_effective_value, partner_effective_value,
    viewer_raw_value, partner_raw_value,
    viewer_confidence_of, partner_confidence_of,
    scoring_format: str, relaxed: bool, model_arm: Optional[str],
    value_model_version: str, consensus_asof: Optional[str],
    viewer_board_updated_at: Optional[str],
    partner_board_updated_at: Optional[str],
    snapshot_stage: str,
) -> dict:
    """The frozen audit/replay record.

    Built from values ALREADY computed during evaluation — it re-derives
    nothing, so it cannot disagree with the gate that just ran.  Per-asset rows
    are the one exception: they are cheap point lookups on the same accessors,
    and without them a later replay cannot explain WHICH asset moved the
    package.

    Not a replacement for the existing scalar columns.  `fairness_score`,
    `base_score` and friends stay exactly where they are; this is the layer
    that lets an analyst answer "why", which the scalars cannot.
    """
    def _asset_rows(ids):
        rows = []
        for pid in ids:
            row = {
                "id": pid,
                "market_value": _r(_safe(consensus_value, pid)),
                "viewer_raw_value": _r(_safe(viewer_raw_value, pid)),
                "viewer_effective_value": _r(_safe(viewer_effective_value, pid)),
                "viewer_confidence": _r(_safe(viewer_confidence_of, pid), 4),
                "partner_raw_value": _r(_safe(partner_raw_value, pid)),
                "partner_effective_value": _r(_safe(partner_effective_value, pid)),
                "partner_confidence": _r(_safe(partner_confidence_of, pid), 4),
            }
            rows.append(row)
        return rows

    return {
        "schema_version": VALUATION_SCHEMA_VERSION,
        "snapshot_stage": snapshot_stage,
        "scoring_format": scoring_format,
        # `basis` here is the GENERATION basis vocabulary the corpus already
        # uses ("divergence" / "consensus"), so existing readers keep working;
        # `policy.value_basis` carries the finer two_board/one_board/consensus
        # distinction this change introduces.
        "basis": ("divergence" if result.basis == BASIS_TWO_BOARD
                  else "consensus"),
        "market": {
            "viewer_gives": result.market_gives,
            "viewer_receives": result.market_receives,
            "ratio": result.market_ratio,
            "consensus_asof": consensus_asof,
        },
        "viewer_board": dict(result.viewer.as_dict(),
                             board_updated_at=viewer_board_updated_at),
        "partner_board": dict(result.partner.as_dict(),
                              board_updated_at=partner_board_updated_at),
        "mutual": {
            "personal_opportunity": result.personal_opportunity,
            "harmonic_effective_surplus": result.harmonic_effective_surplus,
            "trade_confidence": result.trade_confidence,
        },
        "policy": {
            "policy_version": result.policy_variant,
            "model_arm": model_arm,
            "value_basis": result.basis,
            "requested_floor": result.requested_floor,
            "policy_floor": result.policy_floor,
            "effective_floor": result.effective_floor,
            "eligibility_lane": result.lane,
            "eligible": result.eligible,
            "rejection_reason": result.reason,
            "relaxed": bool(relaxed),
            "value_model_version": value_model_version,
        },
        "assets": {
            "give": _asset_rows(give_ids),
            "receive": _asset_rows(receive_ids),
        },
    }


def snapshot_matches_assets(snapshot: dict, assets_json: dict) -> bool:
    """Acceptance check: the snapshot's asset ids and DIRECTIONS match the
    row's `assets_json` exactly.  Used by the health counter and by tests; a
    mismatch means the snapshot was built from a different package than the one
    served, which is worse than no snapshot at all."""
    try:
        snap_give = [a["id"] for a in snapshot["assets"]["give"]]
        snap_recv = [a["id"] for a in snapshot["assets"]["receive"]]
    except (KeyError, TypeError):
        return False
    return (snap_give == list(assets_json.get("give") or [])
            and snap_recv == list(assets_json.get("receive") or []))


# ---------------------------------------------------------------------------
# Canonical trade-concept identity
# ---------------------------------------------------------------------------

def trade_concept_id(*, league_id: Optional[str],
                     viewer_user_id: Optional[str],
                     partner_user_id: Optional[str],
                     viewer_gives: Sequence[str],
                     viewer_receives: Sequence[str]) -> Optional[str]:
    """A perspective-INDEPENDENT id for one exact package between two managers.

    The existing `trade_hash` is viewer-relative — A's card and B's mirror hash
    differently — so it cannot join the two halves of a mutual match.  This
    can: the participants are sorted, and each side's assets are attributed to
    the sorted user rather than to "the viewer", so both perspectives of the
    same package produce the same string.

    League and BOTH participants are inside the hash so an identical package
    between different managers, or in an unrelated league, never collides.

    `trade_hash` is kept for viewer-relative fatigue and dedup.  The two fields
    answer different questions and neither replaces the other.
    """
    if not (league_id and viewer_user_id and partner_user_id):
        return None
    low, high = sorted([str(viewer_user_id), str(partner_user_id)])
    if str(viewer_user_id) == low:
        low_gives, high_gives = viewer_gives, viewer_receives
    else:
        low_gives, high_gives = viewer_receives, viewer_gives
    payload = "|".join([
        str(CONCEPT_SCHEMA_VERSION),
        str(league_id),
        low, high,
        ",".join(sorted(str(a) for a in set(low_gives or ()))),
        ",".join(sorted(str(a) for a in set(high_gives or ()))),
    ])
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Deck composition
# ---------------------------------------------------------------------------

def compose_deck(entries: list, *, size: Optional[int] = None) -> tuple[list, list]:
    """Apply the Core / Conviction / Fallback composition rules.

    `entries` is ``[(card, PolicyResult), ...]`` already in the caller's
    preferred order.  Returns ``(kept, dropped)`` where `dropped` is
    ``[(card, reason), ...]``.

    Rules, all knob-driven:

    * the first ``deck_core_lead_cards`` positions are Core — trust is built
      before anything unusual is shown;
    * at least ``deck_core_min_share`` of the deck is Core;
    * at most ``min(2, floor(conviction_deck_share * size))`` Conviction cards,
      and they sit after the lead block;
    * Fallback (no opponent board) fills what is left — it never DISPLACES a
      valid divergence card, which is why it is placed last;
    * if safe supply is insufficient the deck comes back SHORTER.  Returning a
      smaller deck is the specified behaviour; weakening the guardrail to fill
      ten slots is not.
    """
    kept: list = []
    dropped: list = []
    core = [e for e in entries if e[1].lane == LANE_CORE]
    conviction = [e for e in entries if e[1].lane == LANE_CONVICTION]
    fallback = [e for e in entries if e[1].lane == LANE_FALLBACK]

    n = int(size) if size is not None else len(entries)
    if n <= 0:
        return ([], [(c, "deck_size_zero") for c, _ in entries])

    lead = min(n, max(0, int(_c("deck_core_lead_cards"))))
    conv_cap = max(0, min(2, int(math.floor(_c("conviction_deck_share") * n))))

    # Lead block: Core only.
    for entry in core[:lead]:
        kept.append(entry)
    rest_core = core[lead:]

    # Conviction sits immediately behind the lead block (positions ~4-6).
    used_conv = conviction[:min(conv_cap, n - len(kept))] if len(core) >= lead else []
    kept.extend(used_conv)

    # Then the remaining Core up to the deck's Core floor and the size cap.
    for entry in rest_core:
        if len(kept) >= n:
            break
        kept.append(entry)

    # Fallback fills only what Core + Conviction could not.
    for entry in fallback:
        if len(kept) >= n:
            break
        kept.append(entry)

    # Enforce the Core share on the deck that actually came out.  The share is
    # measured against the REALIZED length, not the requested `size`: a deck
    # that returned six cards because supply ran out is not thereby allowed a
    # weaker Core share than a full one.  Shortfall is paid by shedding
    # Conviction cards — never by dropping Core, and never by admitting a card
    # the evaluator rejected.
    while True:
        n_core = sum(1 for _c_, r in kept if r.lane == LANE_CORE)
        needed = int(math.ceil(_c("deck_core_min_share") * len(kept))) if kept else 0
        n_conv = sum(1 for _c_, r in kept if r.lane == LANE_CONVICTION)
        allowed_conv = max(0, min(2, int(math.floor(_c("conviction_deck_share") * len(kept)))))
        if n_core >= needed and n_conv <= allowed_conv:
            break
        victim = next((e for e in reversed(kept)
                       if e[1].lane == LANE_CONVICTION), None)
        if victim is None:
            break
        kept.remove(victim)
        dropped.append((victim[0], "core_share_shortfall"))

    kept_ids = {id(c) for c, _ in kept}
    dropped_ids = {id(c) for c, _ in dropped}
    for card, _res in entries:
        if id(card) not in kept_ids and id(card) not in dropped_ids:
            dropped.append((card, "deck_quota"))
    return kept, dropped


# ---------------------------------------------------------------------------
# Shadow-rejection records
# ---------------------------------------------------------------------------

def shadow_row(*, deck_job_id: str, user_id: str, league_id: str,
               trade_hash: Optional[str], concept_id: Optional[str],
               model_arm: Optional[str], result: PolicyResult,
               created_at: str) -> dict:
    """One `trade_policy_shadow` row for a candidate the TREATMENT rejected.

    Without these rows the treatment's discarded candidates vanish from the
    denominator and the policy looks artificially precise: every card it served
    passed, because the ones it killed were never recorded.  The arm is carried
    so a rejection can be attributed to the generator that produced it.
    """
    return {
        "deck_job_id": deck_job_id,
        "user_id": user_id,
        "league_id": league_id,
        "trade_hash": trade_hash,
        "trade_concept_id": concept_id,
        "model_arm": model_arm,
        "policy_variant": result.policy_variant,
        "eligible": 1 if result.eligible else 0,
        "reason": result.reason,
        "market_ratio": result.market_ratio,
        "effective_floor": result.effective_floor,
        "policy_floor": result.policy_floor,
        "personal_opportunity": result.personal_opportunity,
        "trade_confidence": result.trade_confidence,
        "lane": result.lane,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if v != v:                     # NaN
        return 0.0
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _harmonic(a: float, b: float) -> float:
    """Harmonic mean of two surpluses; 0 when either side is non-positive.
    Kept as a SECONDARY signal only — it is monotone in two-sided benefit,
    which is what the brief requires of it, but it no longer orders the deck."""
    if a <= 0 or b <= 0:
        return 0.0
    return 2.0 * a * b / (a + b)


def _safe(fn, pid):
    if fn is None:
        return None
    try:
        return fn(pid)
    except Exception:
        return None


def _r(x, nd: int = 2):
    if x is None:
        return None
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def dumps(snapshot: dict) -> Optional[str]:
    """Serialize a snapshot for storage.  Returns None (and counts a health
    failure) rather than raising: telemetry may never fail a trade job."""
    try:
        return json.dumps(snapshot, separators=(",", ":"))
    except (TypeError, ValueError) as err:
        HEALTH["serialize_failures"] += 1
        log.warning("valuation snapshot serialization failed: %s", err)
        return None


#: Process-local health counters.  Exposed through the admin config surface so
#: an operator can see whether telemetry is silently degrading before trusting
#: a readout built on it.  Never persisted — a restart resets them, which is
#: correct for a "is it working right now" signal.
HEALTH: dict = {
    "serialize_failures": 0,
    "snapshot_failures": 0,
    "asset_mismatches": 0,
    "shadow_write_failures": 0,
    "proposal_write_failures": 0,
}


def reset_health() -> None:
    for k in HEALTH:
        HEALTH[k] = 0
