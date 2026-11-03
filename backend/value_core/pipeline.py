"""One-call composition of the value core: core -> ranking -> deck.

docs/plans/value-core-engine/lld.md section 6. `core`, `ranking` and `deck`
are imported INSIDE `run`, never at module level, so the serving plumbing can
be exercised (with `run` stubbed) without them. No logging, no I/O, no
exception handling: errors propagate to the caller.
"""
from __future__ import annotations

import time

from .types import CoreConfig, LeagueSnapshot, PipelineResult, RankConfig, Request


def run(snapshot: LeagueSnapshot, request: Request, core_cfg: CoreConfig, rank_cfg: RankConfig, *,
        safety_ceiling_s: float | None = None) -> PipelineResult:   # None => core.SAFETY_CEILING_S
    """core.find_fair_trades -> ranking.score_trades -> deck.assemble_deck.
    `from . import core, ranking, deck` happens INSIDE this function (never at module
    level). safety_ceiling_s is passed through to the core (None => core.SAFETY_CEILING_S).
    elapsed_ms is wall time for the three steps. No logging, no I/O, no
    exception handling: errors propagate to the caller."""
    from . import core, deck, ranking
    started = time.monotonic()
    ceiling = core.SAFETY_CEILING_S if safety_ceiling_s is None else safety_ceiling_s
    trades, diag = core.find_fair_trades(snapshot, request, core_cfg, safety_ceiling_s=ceiling)
    scored = ranking.score_trades(snapshot, request, trades, rank_cfg)
    entries = deck.assemble_deck(scored, rank_cfg, snapshot=snapshot, request=request)
    return PipelineResult(entries, diag, int((time.monotonic() - started) * 1000))
