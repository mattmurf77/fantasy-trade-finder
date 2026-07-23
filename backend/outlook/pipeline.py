"""Thin pipeline that wires the five phases from config via the registries.

Nothing here imports a concrete provider by name to *use* it — every phase is
resolved through its factory (`get_*`), so a provider swap is a registry line +
a config value and this file never changes.

Two entry points keep the network-touching part (Phase 1) separable from the
pure computation (Phases 2-5), which makes the pure core unit-testable without
any I/O:
  - build_league_state(...)  → Phase 1 (may hit the platform API)
  - run_outlook(state, ...)  → Phases 2-5 (pure)
"""

from __future__ import annotations

from typing import Callable

from . import config as _cfg
from .league_state import LeagueState, get_league_state_provider
from .playoff_format import get_playoff_format
from .serialize import get_serializer
from .simulator import get_simulator
from .strength import (
    StrengthContext,
    get_strength_provider,
    resolve_strength_source,
)


def build_league_state(league_id: str, platform: str = "sleeper",
                       fetch: Callable[[str], object] | None = None) -> LeagueState:
    """Phase 1: resolve the platform provider and load the league facts."""
    provider = get_league_state_provider(platform)
    # Sleeper provider accepts an injected fetch; others ignore it.
    if fetch is not None and hasattr(provider, "_fetch"):
        provider._fetch = fetch  # type: ignore[attr-defined]
    return provider.load(league_id)


def run_outlook(
    state: LeagueState,
    *,
    player_value: dict[str, float],
    player_pos: dict[str, str],
    model_cfg: dict[str, float],
    basis: str = "consensus",
    scoring_format: str | None = None,
    source_override: str | None = None,
    you_user_id: str = "",
    n_sims: int | None = None,
    format_key: str = "standard",
) -> dict:
    """Phases 2-5: strength → simulate → seed/bracket → serialize. Pure."""
    if scoring_format is not None:
        # attach for the serializer (LeagueState has no such field by default)
        setattr(state, "scoring_format", scoring_format)

    # Phase 2 — strength (the swap seam)
    configured = _cfg.get_strength_source(source_override)
    source_key = resolve_strength_source(configured, state, model_cfg)
    provider = get_strength_provider(source_key)
    ctx = StrengthContext(player_value=player_value, player_pos=player_pos,
                          cfg=model_cfg)
    strengths = provider.estimate(state, ctx)

    # Phase 4 — format (built before Phase 3 because the simulator consumes it)
    fmt = get_playoff_format("standard" if format_key is None else format_key,
                             state.playoff_slots, state.num_byes,
                             state.num_divisions)

    # Phase 3 — simulate
    sims = n_sims if n_sims is not None else _cfg.sim_count(model_cfg)
    simulator = get_simulator()
    result = simulator.run(state, strengths, fmt, n_sims=sims,
                           config_seed=_cfg.config_seed(model_cfg))

    # Phase 5 — serialize
    serializer = get_serializer()
    return serializer.serialize(
        state, result, strengths,
        strength_source=source_key, basis=basis, you_user_id=you_user_id,
    )
