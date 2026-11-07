"""Versioned forecast interpretation, not a provider guarantee of omitted zeros.

The sparse model is admitted only on populated, source-bound offensive rows whose
three published totals reconcile under an observed two-decimal rounding model.
Missing rows, rare events, kicking and IDP omissions remain unknown.
"""
from .core import Unavailable, decimal, digest
from ..season_forecasts import POSITION_BONUSES

CONTRACT = "sleeper_sparse_offense_v1"
OFFENSE = {
    "pass_yd": ".04", "pass_td": "4", "pass_int": "-1", "pass_2pt": "2",
    "rush_yd": ".1", "rush_td": "6", "rush_2pt": "2",
    "rec_yd": ".1", "rec_td": "6", "rec_2pt": "2", "fum_lost": "-2", "rec": "1",
}
ANCHORS = frozenset({"pass_att", "pass_yd", "rush_att", "rush_yd", "rec_tgt", "rec", "rec_yd"})
OFFENSE_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})
# Observed native FB/DB may have offensive fantasy eligibility. Keep their
# primary identity; never map FB→RB or DB→WR for position premiums.
BONUS_PRIMARY_POSITIONS = OFFENSE_POSITIONS | {"FB", "DB"}


def _identity(raw, positions):
    stats = raw.get("stats") or {}
    if raw.get("company") != "rotowire" or raw.get("category") != "proj":
        raise Unavailable("unvalidated_projection_source", state="incomplete_projections")
    if not set(positions) & OFFENSE_POSITIONS or isinstance(stats.get("gp"), bool) or stats.get("gp") != 1 or not ANCHORS.intersection(stats):
        raise Unavailable("sparse_offense_contract_not_applicable", state="incomplete_projections")
    for anchor in ANCHORS.intersection(stats):
        decimal(stats[anchor])
    supplied = {k: decimal(stats[k]) for k in OFFENSE if k in stats}
    identities = []
    for key, reception in (("pts_std", "0"), ("pts_half_ppr", ".5"), ("pts_ppr", "1")):
        if key not in stats:
            raise Unavailable("missing_offense_reconciliation_total", state="incomplete_projections")
        target = decimal(stats[key])
        if any(v != v.quantize(decimal(".01")) for v in [target, *supplied.values()]):
            raise Unavailable("unvalidated_projection_precision", state="incomplete_projections")
        coefficients = {k: decimal(v) for k, v in OFFENSE.items()}
        coefficients["rec"] = decimal(reception)
        estimate = sum((coefficients[k] * v for k, v in supplied.items()), decimal(0))
        bound = decimal(".005") * (1 + sum((abs(coefficients[k]) for k in supplied), decimal(0)))
        residual = abs(estimate - target)
        if residual > bound:
            raise Unavailable("offense_projection_identity_mismatch", state="incomplete_projections")
        identities.append({"total": key, "absolute_residual": str(residual), "rounding_bound": str(bound)})
    return identities


def normalize(raw, required_keys, supported_keys, *, policy, positions, primary_position=None):
    supplied = dict(raw.get("stats") or {})
    supported = set(supported_keys)
    missing_offense = set(required_keys) & set(OFFENSE) - supplied.keys()
    # Reconciliation is required for every row admitted to this model, even if
    # this league happens not to consume one of the row's omitted offense keys.
    identities = _identity(raw, positions) if policy == CONTRACT and set(positions) & OFFENSE_POSITIONS else []
    stats, provenance, missing = {}, {}, []
    def ambiguous_bonus(key):
        # A source may credit an FB/DB through offensive fantasy eligibility.
        # No verified rule lets us derive or contradict that alias premium.
        return primary_position in {"FB", "DB"} and POSITION_BONUSES[key][0] in set(positions)
    for key in sorted(required_keys):
        basis, method, value = "missing", "unsupported_or_unsupplied", None
        if key in supplied and key in supported:
            value, basis, method = decimal(supplied[key]), "direct", "provider_expected_event"
            if key in POSITION_BONUSES and primary_position in BONUS_PRIMARY_POSITIONS and not ambiguous_bonus(key):
                position, event = POSITION_BONUSES[key]
                expected = decimal(0) if primary_position != position else decimal(supplied[event]) if event in supplied else None
                if expected is not None and value != expected:
                    raise Unavailable("inconsistent_position_bonus", state="incomplete_projections")
        elif key == "fgmiss" and "fga" in supplied and "fgm" in supplied:
            value = decimal(supplied["fga"]) - decimal(supplied["fgm"])
            if value < 0:
                raise Unavailable("inconsistent_kicker_projection", state="incomplete_projections")
            basis, method = "derived", "fga_minus_fgm"
        elif policy == CONTRACT and key in POSITION_BONUSES and primary_position in BONUS_PRIMARY_POSITIONS and not ambiguous_bonus(key):
            position, event = POSITION_BONUSES[key]
            if primary_position != position:
                value, basis, method = decimal(0), "inapplicable", "native_primary_position_bonus_v1"
            elif event in supplied:
                value, basis, method = decimal(supplied[event]), "derived", "native_primary_position_bonus_v1:" + event
            elif identities and event in OFFENSE:
                value, basis, method = decimal(0), "model_assumed", CONTRACT + ":position_bonus:" + event
        elif identities and key in missing_offense:
            value, basis, method = decimal(0), "model_assumed", CONTRACT
        if value is None:
            missing.append(key)
        else:
            stats[key] = str(value)
        provenance[key] = {"value": str(value) if value is not None else None, "basis": basis, "method": method}
    return {"stats": stats, "supported_keys": sorted(supported | set(stats)), "stat_provenance": provenance,
            "missing_keys": missing, "scoring_contract": policy, "aggregate_identity": identities,
            "raw_stats_hash": digest(supplied),
            "assumption_note": "Omitted common offense events are modeled as zero; aggregate agreement does not establish predictive accuracy or a per-event error bound." if identities else None}


BEST_AVAILABLE = "sleeper_best_available_v1"


def best_available(raw, coefficients, supported_keys, *, positions, primary_position=None):
    """Score available contributions; never relabel an unknown event as confirmed 0.

    The validated sparse offense convention can still contribute explicit model
    assumptions. Failed aggregate diagnostics do not discard usable direct stats.
    Missing penalties mean this subtotal is not a lower bound on the full score.
    """
    supplied = dict((raw or {}).get("stats") or {})
    required = {key for key, value in coefficients.items() if decimal(value)}
    supported = set(supported_keys)
    populated = bool(set(supplied) & (supported | ANCHORS | {"fga", "fgm"}))
    prior, warnings = {}, []
    try:
        if populated:
            prior = normalize(raw or {}, required, supported, policy=CONTRACT,
                              positions=positions, primary_position=primary_position)
    except Unavailable as exc:
        warnings.append(exc.reason)
    stats, provenance = {}, {}
    for key in sorted(required):
        value, basis, method = None, "missing", "event_not_available"
        if key in supplied and key in supported:
            value, basis, method = decimal(supplied[key]), "direct", "provider_expected_event"
        elif key in prior.get("stats", {}):
            value = decimal(prior["stats"][key])
            basis, method = (prior["stat_provenance"][key][k] for k in ("basis", "method"))
        elif key == "fgmiss" and "fga" in supplied and "fgm" in supplied:
            derived = decimal(supplied["fga"]) - decimal(supplied["fgm"])
            if derived >= 0:
                value, basis, method = derived, "derived", "fga_minus_fgm"
            else:
                warnings.append("inconsistent_kicker_projection")
        elif populated and key in POSITION_BONUSES and primary_position in BONUS_PRIMARY_POSITIONS:
            position, event = POSITION_BONUSES[key]
            ambiguous = primary_position in {"FB", "DB"} and position in set(positions)
            if not ambiguous and primary_position != position:
                value, basis, method = decimal(0), "inapplicable", "native_primary_position_bonus_v1"
            elif not ambiguous and event in supplied:
                value, basis, method = decimal(supplied[event]), "derived", "native_primary_position_bonus_v1:" + event
        if value is not None:
            stats[key] = str(value)
        provenance[key] = {"value": None if value is None else str(value), "basis": basis, "method": method}
    missing = sorted(required - stats.keys())
    # A zero subtotal with explicit consumed fields is usable. No matched fields
    # is absent coverage, even if some unrelated forecast stats exist.
    subtotal = sum((decimal(coefficients[k]) * decimal(v) for k, v in stats.items()), decimal(0)) if stats or not required else None
    return {"stats": stats, "supported_keys": sorted(supported | stats.keys()), "stat_provenance": provenance,
            "missing_keys": missing, "missing_negative_keys": [k for k in missing if decimal(coefficients[k]) < 0],
            "known_points_subtotal": None if subtotal is None else str(subtotal),
            "projection_status": "unpriced" if subtotal is None else "partial" if missing else "available",
            "scoring_contract": BEST_AVAILABLE, "aggregate_identity": prior.get("aggregate_identity", []),
            "raw_stats_hash": digest(supplied), "coverage_warnings": sorted(set(warnings)),
            "assumption_note": "Available contributions only; omitted events may raise or lower the full score." if missing else prior.get("assumption_note")}
