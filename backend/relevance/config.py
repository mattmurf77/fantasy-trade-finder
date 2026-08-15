"""The D10 config resolver — the only legal read path for relevance knobs.

Precedence (HLD D10, LLD §2.1), highest wins:

    per-user setting  >  experiment variant overlay (REGISTERED knobs only)
                      >  model_config row  >  code default

Plus `valve()`, the deliberate exception: operational valves
(`cron.pass_disabled.*`, `ingest.daily_budget`) read `model_config` raw, with
no overlay and no per-user tier, because an experiment must never be able to
resurrect a killed pass or raise the ingest budget (HLD §2.1).

T-28 lints that no other module in `backend/relevance/` reads `model_config`
directly. That is the point of this file: one read path, one place to reason
about precedence.

No Flask imports (D12).
"""

from __future__ import annotations

import threading
import time
from typing import Callable

__all__ = ["resolve", "valve", "KNOB_EXPERIMENTS", "USER_SETTING_PROVIDERS"]


# ---------------------------------------------------------------------------
# Tier 2 registry — the overlay discovery mechanism
# ---------------------------------------------------------------------------
# knob key → experiment key. EMPTY AT P0: no relevance knob is experiment-driven
# yet. The mechanism exists (and is tested) so that P1+ can register one knob
# without re-litigating precedence.
#
# Why a registry instead of merging every running experiment's overlay:
# `variant_overlay(unit_id, exp_key)` requires a *specific* experiment key —
# the sole production precedent hardcodes "trade.aggression"
# (trade_service.py:3189). Merging all running experiments would let any
# experiment silently override any relevance knob. resolve() therefore consults
# the overlay ONLY for keys registered here; unregistered knobs skip the tier.
KNOB_EXPERIMENTS: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Tier 1 registry — per-user settings
# ---------------------------------------------------------------------------
# knob key → callable(user_id) -> float | None  (None = "user has no override").
# EMPTY AT P0. There is no generic numeric per-user knob store in this schema:
# D10's "per-user setting" slot means *existing* prefs (the `stud_tax_mode` /
# `pick_pricing_mode` shape — columns on `users`, read by a purpose-built
# getter), not a new key-value table. A provider registry keeps the tier real
# and testable without inventing schema, and keeps this module free of any
# knowledge of where a given pref happens to live.
#
# Providers must be cheap and must never raise; resolve() defends anyway.
USER_SETTING_PROVIDERS: dict[str, Callable[[str], float | None]] = {}

# ---------------------------------------------------------------------------
# Operational valves (resolver-EXEMPT)
# ---------------------------------------------------------------------------
_VALVE_PREFIXES: tuple[str, ...] = ("cron.pass_disabled.",)
_VALVE_KEYS: frozenset[str] = frozenset({"ingest.daily_budget"})


def is_valve_key(key: str) -> bool:
    """True for the whitelisted operational-valve keys (HLD §2.1)."""
    return key in _VALVE_KEYS or key.startswith(_VALVE_PREFIXES)


# ---------------------------------------------------------------------------
# model_config snapshot (tier 3)
# ---------------------------------------------------------------------------
# `resolve()` can be called several times per deck card, so the model_config
# tier reads the whole table once and holds it for a few seconds — the same
# whole-table read `database.get_config()` already does, with the TTL-cache
# shape `experiments._load_cache` already uses.
#
# `valve()` deliberately does NOT use this cache: HLD §2.1 leans on a valve
# write being *immediate* ("model_config is a live DB write, so killing a pass
# is immediate"). A cache would put a staleness window between the operator
# hitting the kill switch and the pass stopping.
_CACHE_TTL_S = 5.0
_cache_lock = threading.Lock()
_cache: dict[str, float] = {}
_cache_at: float = 0.0


def _snapshot() -> dict[str, float]:
    """All model_config rows, cached ~5s. Empty dict on any failure (fail to
    the code default, never raise into a serving path)."""
    global _cache, _cache_at
    now = time.monotonic()
    with _cache_lock:
        if _cache_at and (now - _cache_at) < _CACHE_TTL_S:
            return _cache
    try:
        from .. import database as db
        from sqlalchemy import select
        with db.engine.connect() as conn:
            rows = conn.execute(select(db.model_config_table)).fetchall()
        fresh = {r.key: r.value for r in rows if r.value is not None}
    except Exception as e:            # missing table, locked DB, no DB at all
        print(f"[relevance.config] model_config snapshot failed: {e}")
        fresh = {}
    with _cache_lock:
        _cache, _cache_at = fresh, now
    return fresh


def _reset_cache() -> None:
    """Drop the snapshot. For tests and for callers that just wrote a knob."""
    global _cache, _cache_at
    with _cache_lock:
        _cache, _cache_at = {}, 0.0


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------

def resolve(key: str, default: float, *, user_id: str | None = None) -> float:
    """Resolve a relevance knob under the D10 precedence order.

    per-user setting > variant_overlay(user_id, KNOB_EXPERIMENTS[key])[key]
    when the knob is registered > model_config row > `default`.

    THE only legal read path for relevance knobs (T-28 enforces). Every tier
    fails open to the next one: a broken provider, a malformed overlay, or an
    unreachable DB degrades to the code default rather than breaking serving.

    Raises ValueError for an operational-valve key — those are resolver-exempt
    by design and must go through `valve()`, so that no per-user setting and no
    experiment can reach them (HLD §2.1).
    """
    if is_valve_key(key):
        raise ValueError(
            f"resolve() refused operational valve {key!r}: valves are "
            "resolver-exempt (HLD §2.1) — call valve() instead."
        )

    # Tier 1 — per-user setting.
    if user_id:
        provider = USER_SETTING_PROVIDERS.get(key)
        if provider is not None:
            try:
                v = provider(user_id)
                if v is not None:
                    return float(v)
            except Exception as e:
                print(f"[relevance.config] user provider for {key!r} failed: {e}")

    # Tier 2 — experiment variant overlay, REGISTERED knobs only.
    exp_key = KNOB_EXPERIMENTS.get(key)
    if exp_key and user_id:
        try:
            from .. import experiments as X
            _variant, overlay = X.variant_overlay(user_id, exp_key)
            if isinstance(overlay, dict) and overlay.get(key) is not None:
                return float(overlay[key])
        except Exception as e:
            print(f"[relevance.config] overlay for {key!r} failed: {e}")

    # Tier 3 — model_config row.
    try:
        v = _snapshot().get(key)
        if v is not None:
            return float(v)
    except Exception:
        pass

    # Tier 4 — code default.
    return float(default)


def valve(key: str, default: float = 0.0) -> float:
    """Read an operational valve straight from `model_config`. No overlay.

    Operational valves ONLY (`cron.pass_disabled.*`, `ingest.daily_budget`):
    a raw single-key read with no per-user tier and no experiment tier, so an
    experiment can never resurrect a killed pass or raise the ingest budget
    (HLD §2.1). Uncached, because a kill switch must bite immediately.

    Absent key ⇒ `default` (0.0), which is the inverted-polarity fail-safe:
    a missing or fat-fingered `cron.pass_disabled.<name>` row means the pass
    RUNS, never that it silently stops.

    Raises ValueError for a non-valve key — the whitelist is the mechanism
    (T-28 lints callers on top of this).
    """
    if not is_valve_key(key):
        raise ValueError(
            f"valve() refused {key!r}: not an operational valve. Whitelist is "
            f"{sorted(_VALVE_KEYS)} + prefixes {list(_VALVE_PREFIXES)}; "
            "ordinary knobs go through resolve()."
        )
    try:
        from .. import database as db
        from sqlalchemy import select
        with db.engine.connect() as conn:
            row = conn.execute(
                select(db.model_config_table.c.value)
                .where(db.model_config_table.c.key == key)
            ).first()
        if row and row[0] is not None:
            return float(row[0])
    except Exception as e:
        print(f"[relevance.config] valve read {key!r} failed: {e}")
    return float(default)
