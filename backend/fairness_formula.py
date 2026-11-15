"""The deck's admission formula (docs/plans/fairness-formula/spec.md, D-267).

Flag `trade.fairness_formula_v2` OFF ⇒ `active()` returns None without reading any knob,
and every deck generator runs today's code path. ON ⇒ the four model_config knobs below
pick the formula; at their defaults (today's math) `active()` is still None.

A formula only changes what the deck generators (`trade_gen_owner._Search` and its
subclasses) admit and the ratio a card carries. The overpay ceiling, the bilateral support
scores, the serving policy, calculator / evaluate verdicts and `market_floor_absolute`
(0.65, applied to the active formula's ratio) are unchanged.

`override(...)` pins a formula on this thread regardless of the flag. Only offline tools
(the replay) use it; production never does.
"""
from contextlib import contextmanager
import math
import threading

FLAG = "trade.fairness_formula_v2"
PACKAGE, EXPONENT, RAW, THRESHOLD_POWER = (
    "fairness_formula_package_math", "fairness_formula_exponent",
    "fairness_formula_raw", "fairness_formula_threshold_power")
KNOBS = (PACKAGE, EXPONENT, RAW, THRESHOLD_POWER)
DEFAULTS = {PACKAGE: 1.0, EXPONENT: 1.0, RAW: 0.0, THRESHOLD_POWER: 1.0}

_local = threading.local()
_UNSET = object()


def _valid(key, value):
    if isinstance(value, bool):
        return False
    try:
        value = float(value)
    except Exception:
        return False
    if not math.isfinite(value):
        return False
    if key in (PACKAGE, RAW):
        return value in (0.0, 1.0)
    return 0.0 < value <= 1.0


def configured(cfg) -> dict:
    """The four knobs from a config mapping; a missing or invalid value is its default."""
    cfg = cfg or {}
    return {k: float(cfg[k]) if k in cfg and _valid(k, cfg[k]) else DEFAULTS[k] for k in KNOBS}


def enabled() -> bool:
    from .feature_flags import is_enabled
    return is_enabled(FLAG)


def active(cfg):
    """The formula a generator should use, or None for today's math.

    A thread pin from `override` wins. Otherwise flag OFF ⇒ None before the knobs are read."""
    pinned = getattr(_local, "formula", _UNSET)
    if pinned is not _UNSET:
        return pinned
    if not enabled():
        return None
    knobs = configured(cfg)
    return None if knobs == DEFAULTS else knobs


@contextmanager
def override(knobs):
    """Pin a formula on this thread (None = today's math). Offline tools only."""
    prev = getattr(_local, "formula", _UNSET)
    _local.formula = None if knobs is None or configured(knobs) == DEFAULTS else configured(knobs)
    try:
        yield
    finally:
        if prev is _UNSET:
            del _local.formula
        else:
            _local.formula = prev


def floor(knobs, requested, absolute):
    """The admission floor: the requested threshold raised to the threshold power,
    never under `market_floor_absolute`."""
    return max(float(requested) ** knobs[THRESHOLD_POWER], absolute)


def side_value(knobs, values, raw_values=None):
    """Σ v ** exponent over a side (plain sum, no package discount). `raw_values`
    replaces `values` when the raw knob is on."""
    use = raw_values if knobs[RAW] == 1.0 else values
    return sum(v ** knobs[EXPONENT] for v in use)


def raw_value(ts, seed, player):
    """The app's per-asset value without the linear map's constant (data_loader
    SEED_VALUE_FLOOR), age preference kept. Exact under the default curve constants."""
    from .data_loader import SEED_VALUE_FLOOR
    return ts.age_pref_value(max(ts.elo_to_value(seed) - SEED_VALUE_FLOOR, 0.0), player)
