"""Max PF moves: which of the viewer's players lower max PF most, and what that does to the pick.

Contract: docs/plans/league-projections/max-pf-trade-away/contract.md. Flag
`league.max_pf_moves` (callers check it; nothing here reads a flag).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# The same file `batch.settings()` reads; not imported from batch so this
# module stays free of database and flag imports (the backtest imports it).
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "league_projections.json"

SETTINGS_KEYS = {
    # key: (type, low, high)
    "simulations_per_candidate": (int, 100, 250000),
    "candidates": (int, 1, 20),
    "min_drop_points": ((int, float), 0, 1000),
    "min_pick_change": ((int, float), 0, 32),
    "min_top3_change": ((int, float), 0, 1),
    "time_budget_seconds": ((int, float), 1, 400),
}


def parse_settings(raw):
    """Validated `max_pf_moves` settings. Raises ValueError on a missing,
    unknown or out-of-range key (booleans are never numbers here)."""
    if not isinstance(raw, dict) or set(raw) != set(SETTINGS_KEYS):
        raise ValueError("invalid_max_pf_moves_configuration")
    out = {}
    for key, (kind, low, high) in SETTINGS_KEYS.items():
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, kind) or not low <= value <= high:
            raise ValueError("invalid_max_pf_moves_configuration")
        out[key] = value
    return out


def settings():
    """The `max_pf_moves` object of `config/league_projections.json`. Read only
    while the flag is on; `batch.settings()` never looks at it."""
    return parse_settings(json.loads(CONFIG_PATH.read_text()).get("max_pf_moves"))


def settings_hash(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
