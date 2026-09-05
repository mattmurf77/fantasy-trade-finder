"""Stateless whole-team benefit gate and ordering; no market/roster authority.

See docs/plans/trade-model-activation/mutual-benefit.md. Gains must use the
same normalization and each manager's own receive-minus-give direction.
Confidence describes evidence, never a probability of accepting a trade.
"""
from collections.abc import Mapping
import math
import sys


MIN_GAIN = 0.01
MIN_CONFIDENCE = 0.5
TOLERANCE = 1e-9
# These are conservative evidence caps, not learned or calibrated probabilities.
PREFERENCE_CONFIDENCE_CAPS = {"observed": 1.0, "estimated": 0.5, "unknown": 0.25}
INCOMPLETE_BASES = frozenset(("dynasty_only", "unavailable", "unknown"))
FALLBACK_REASONS = frozenset(("mutual_low_confidence", "mutual_preferences_estimated",
                              "mutual_preferences_unknown"))


def _finite(value) -> float | None:
    # Do not turn strings/bools into apparently measured utility.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def _side(benefit, preference_source, minimum_gain, minimum_confidence, tolerance):
    benefit = benefit if isinstance(benefit, Mapping) else {}
    reasons = []
    basis = benefit.get("basis")
    basis = basis if isinstance(basis, str) and basis.strip() else "unknown"
    ready = benefit.get("ready_for_enforcement") is True and basis not in INCOMPLETE_BASES
    reported_gain = _finite(benefit.get("normalized_gain"))
    # A partial negative dynasty delta cannot establish whole-team harm:
    # missing production could outweigh it. Preserve it only as a diagnostic.
    gain = reported_gain if ready else None
    if not ready:
        gain_status = "unknown"
        reasons.append("mutual_utility_incomplete")
    elif gain is None:
        gain_status = "unknown"
        reasons.append("mutual_gain_unknown" if benefit.get("normalized_gain") is None
                       else "mutual_gain_invalid")
    else:
        if abs(gain) <= tolerance:
            gain = 0.0
        if gain < 0:
            gain_status = "negative"
            reasons.append("mutual_negative_gain")
        elif gain == 0 or gain < minimum_gain - tolerance:
            gain_status = "not_meaningful"
            reasons.append("mutual_gain_below_minimum")
        else:
            gain_status = "meaningful"

    confidence = _finite(benefit.get("confidence"))
    if confidence is None or not 0 <= confidence <= 1:
        reasons.append("mutual_confidence_invalid")
        confidence = 0.0
    if not isinstance(preference_source, str) or preference_source not in PREFERENCE_CONFIDENCE_CAPS:
        reasons.append("mutual_preference_source_invalid")
        preference_source = "unknown"
    if preference_source != "observed":
        reasons.append("mutual_preferences_" + preference_source)
    confidence = min(confidence, PREFERENCE_CONFIDENCE_CAPS[preference_source])
    if gain is None:
        confidence = 0.0
    if confidence < minimum_confidence:
        reasons.append("mutual_low_confidence")

    return {"normalized_gain": gain, "gain_status": gain_status,
            "reported_gain": reported_gain, "ready_for_enforcement": ready,
            "confidence": confidence, "preference_source": preference_source,
            "basis": basis,
            "reasons": sorted(set(reasons))}


def evaluate_mutual_benefit(
    viewer: Mapping | None,
    partner: Mapping | None,
    *,
    viewer_preference_source: str = "unknown",
    partner_preference_source: str = "unknown",
    minimum_gain: float = MIN_GAIN,
    minimum_confidence: float = MIN_CONFIDENCE,
    tolerance: float = TOLERANCE,
) -> dict:
    """Evaluate ONLY the benefit requirement using two outlook utility dicts.

    ``eligible`` requires meaningful gain, observed preference evidence and
    sufficient confidence for BOTH managers. ``blocked`` means at least one
    complete gain is negative/insufficient, even if the other side is unknown.
    Otherwise the result is ``unknown``. Positive estimates can be marked
    ``fallback_candidate`` but are never silently promoted to eligible.

    Explicit preference provenance is separate from utility ``basis``: a
    consensus roster estimate, inferred outlook, or default preference is
    not an observed personal preference. Omission means unknown. The caller
    must retain upstream components/uncertainty in its private evidence; this
    summary intentionally does not copy arbitrary upstream payloads.

    A utility must explicitly declare ``ready_for_enforcement=True`` and a
    complete basis. Missing readiness, dynasty_only, unavailable or unknown
    bases are unknown BEFORE testing sign, even with a negative partial gain.

    Bad measurements yield unknowns; bad threshold configuration raises
    ValueError. No flags, DB, IO, learned acceptance, or input mutation.
    """
    minimum_gain, minimum_confidence, tolerance = (
        _finite(v) for v in (minimum_gain, minimum_confidence, tolerance))
    if (minimum_gain is None or minimum_confidence is None or tolerance is None
            or tolerance < 0 or minimum_gain <= tolerance
            or not 0 < minimum_confidence <= 1):
        raise ValueError("require finite minimum_gain > tolerance >= 0 and 0 < minimum_confidence <= 1")

    sides = {
        "viewer": _side(viewer, viewer_preference_source, minimum_gain, minimum_confidence, tolerance),
        "partner": _side(partner, partner_preference_source, minimum_gain, minimum_confidence, tolerance),
    }
    reasons = sorted({r for side in sides.values() for r in side["reasons"]})
    if "mutual_negative_gain" in reasons:
        status, reason = "blocked", "mutual_negative_gain"
    elif "mutual_gain_below_minimum" in reasons:
        status, reason = "blocked", "mutual_gain_below_minimum"
    elif reasons:
        status, reason = "unknown", "mutual_evidence_incomplete"
    else:
        status, reason = "eligible", "mutual_meaningful_gain"

    gains = [side["normalized_gain"] for side in sides.values()]
    weaker_gain = total_gain = None
    numeric_notes = []
    if all(gain is not None for gain in gains):
        weaker_gain = min(gains)
        total_gain = gains[0] + gains[1]
        if not math.isfinite(total_gain):
            total_gain = math.copysign(sys.float_info.max, total_gain)
            numeric_notes.append("mutual_total_saturated")

    return {
        "schema_version": 1,
        "status": status, "eligible": status == "eligible",
        "reason": reason, "reasons": reasons,
        "fallback_candidate": status == "unknown" and set(reasons) <= FALLBACK_REASONS and all(
            side["gain_status"] == "meaningful" for side in sides.values()),
        "weaker_gain": weaker_gain, "total_gain": total_gain,
        "confidence": min(side["confidence"] for side in sides.values()),
        "sides": sides,
        "thresholds": {"minimum_gain": minimum_gain,
                       "minimum_confidence": minimum_confidence, "tolerance": tolerance},
        "numeric_notes": numeric_notes,
    }


def rank_key(result: Mapping, *, give_count: int, receive_count: int) -> tuple:
    """Ascending key for an unmodified evaluate_mutual_benefit result.

    Evidence bucket, descending weaker gain, descending total gain, ascending
    asset count, ascending imbalance. Every traded asset (including picks)
    counts. Exact ties stay tied; use the existing canonical concept ID last
    if caller input order is not deterministic. Confidence is a gate/bucket,
    never a multiplier that could shrink a negative gain toward a pass.

    This does not filter cards, assign lanes, authorize trades, or check that
    a package is legal. Call only on the final package after the other gates.
    """
    if any(isinstance(n, bool) or not isinstance(n, int) or n <= 0
           for n in (give_count, receive_count)):
        raise ValueError("package counts must be positive integers")
    bucket = {"eligible": 0, "unknown": 2, "blocked": 3}[result["status"]]
    if result["status"] == "unknown" and result["fallback_candidate"]:
        bucket = 1
    return (bucket,
            -(result["weaker_gain"] if result["weaker_gain"] is not None else 0.0),
            -(result["total_gain"] if result["total_gain"] is not None else 0.0),
            give_count + receive_count, abs(give_count - receive_count))
