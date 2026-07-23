"""Config-driven source selection for the outlook pipeline.

The numeric knobs (calibration means, sigmas, sim count, seed) live in the
`model_config` DB table (Float-typed). The one STRING knob — which
StrengthProvider to use — cannot live in that Float table, so it is read from
the `FTF_OUTLOOK_STRENGTH_SOURCE` environment variable (default 'auto'). This
keeps source selection genuinely config-driven and swappable via ONE value,
with no concrete provider imported anywhere downstream.

FLAGGED FOR OPERATOR: if you'd prefer this string live alongside the other
model_config keys, model_config would need a text-valued companion column (a
schema change deliberately avoided here for surgical scope).
"""

from __future__ import annotations

import os

DEFAULT_STRENGTH_SOURCE = "auto"


def get_strength_source(override: str | None = None) -> str:
    """Resolve the configured strength source.

    Precedence: explicit override arg → FTF_OUTLOOK_STRENGTH_SOURCE env →
    'auto'. The returned value is still passed through
    strength.resolve_strength_source() to turn 'auto' into a concrete key."""
    if override:
        return override
    return os.environ.get("FTF_OUTLOOK_STRENGTH_SOURCE", DEFAULT_STRENGTH_SOURCE)


def sim_count(cfg: dict[str, float]) -> int:
    val = cfg.get("outlook_sim_count")
    return int(val) if val else 10000


def config_seed(cfg: dict[str, float]) -> int:
    val = cfg.get("outlook_seed")
    return int(val) if val else 0
