"""The default "fair" threshold: one source of truth (docs/plans/fairness-window/spec.md).

`FAIR_DEFAULT` is today's number and the only literal. Flag `trade.fairness_window_v2`
OFF ⇒ every reader gets `FAIR_DEFAULT` and model_config is not read. ON ⇒ the
`fairness_window_default` model_config knob, served to the app on GET /api/feature-flags
as `fairness_on_threshold` (and only while the flag is on).

Explicit thresholds a caller sends are never rewritten here. The allowed range keeps the
existing order: on (>= 0.55) stays above off (0.50), and the relaxed fallback and the
divergence floor (both 0.55, applied as min(requested, 0.55)) are unchanged for every
allowed value. The engine still clamps every request to `market_floor_absolute` (0.65).
"""
import math

FLAG = "trade.fairness_window_v2"
KNOB = "fairness_window_default"
FAIR_DEFAULT = 0.75
LOWEST, HIGHEST = 0.55, 0.75


def configured_fair_threshold(cfg) -> float:
    """The knob as a float in [LOWEST, HIGHEST]; anything else serves FAIR_DEFAULT."""
    try:
        raw = float((cfg or {}).get(KNOB, FAIR_DEFAULT))
    except Exception:
        return FAIR_DEFAULT
    if isinstance((cfg or {}).get(KNOB), bool) or not math.isfinite(raw) or not LOWEST <= raw <= HIGHEST:
        return FAIR_DEFAULT
    return raw


def window_enabled() -> bool:
    from .feature_flags import is_enabled
    return is_enabled(FLAG)


def default_fair_threshold() -> float:
    """The default "fair" threshold for a request that did not send one."""
    if not window_enabled():
        return FAIR_DEFAULT
    try:
        from .database import get_config
        cfg = get_config()
    except Exception:
        return FAIR_DEFAULT
    return configured_fair_threshold(cfg)


def payload_fields() -> dict:
    """The additive key on GET /api/feature-flags: absent while the flag is off."""
    if not window_enabled():
        return {}
    return {"fairness_on_threshold": default_fair_threshold()}
