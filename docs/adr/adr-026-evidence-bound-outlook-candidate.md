# ADR-026 — Versioned outlook policy requires actual evidence

**Date:** 2026-11-06
**Status:** accepted for default-dark implementation; activation withheld

## Context

The prior owner revision treated QB28 and WR/TE26 as worse rebuilding assets by
birthday, while a personal top-tier RB could receive favorable long-window fit
regardless of age. The owner input path lacks qualified production histories,
observed starting jobs and compatible future forecasts. Other forecast/usage
subsystems exist but do not supply qualified owner evidence.

## Decision

Introduce separately reversible `owner-v2-bilateral-3`. Player production fit
stays neutral/Unknown; no youth, market tier or personal preference becomes a
production fact. Picks retain future-capital direction for rebuilders. Known
age/position and provisional window endpoints remain diagnostics. Preserve shared
market pricing and remove only the second lineup age multiplier.

A rebuilding RB acquisition needs incoming-specific desire. Incidental lower-value
RBs need that desire or an independent desired non-RB / net-capital pick headliner
plus required price consideration. Both managers are evaluated. This restriction
is an explicit position/window uncertainty policy, not an age ban or empirical
forecast. Current roster proxy is small and downside-only for rebuilding teams.

Use explicit private evidence kwargs and version-fenced immutable proofs;
retain old constructors, budgets, owner authority and full final gates. No tap-time
provider fetch or production activation. See [complete contract](../plans/outlook-evidence-rules/architecture.md).

## Consequences

This removes unsupported outlook claims but does not complete contender/rebuilder
forecasting. Proven/developing/fragile QB classes remain unknown until a real
qualified production/role adapter exists. The model can honor a manager who
explicitly desires an older RB without claiming that preference proves longevity.
Independent output evaluation and full CI remain activation prerequisites. Old
proofs are immutable, and the default0 selector restores revision2.
