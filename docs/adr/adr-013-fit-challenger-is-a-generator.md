# ADR-013 — The fit challenger is a generator, not a config profile of the live engine

**Date:** 2026-08-20
**Status:** Accepted
**Author:** worktree session `claude/trade-suggestions-review-69c9eb`
(scope blocks: [`../plans/fit-challenger/scope.md`](../plans/fit-challenger/scope.md),
[`scope-measurement.md`](../plans/fit-challenger/scope-measurement.md),
[`scope-serving.md`](../plans/fit-challenger/scope-serving.md); operator PRD
[`../plans/fit-challenger/PRD.md`](../plans/fit-challenger/PRD.md) §3 knockouts CLOSED)

## Context

The bake-off holds two prior kinds of challenger. Arm D (`challenger`,
[D-095](../../living-memory/DECISIONS.md)) is a **profile**: the live v1/v3 engine under a
thread-local `_cfg_override`, testing knob values on unchanged machinery. Arm C
(`gen_v2`) is a **module**: a separate pipeline invoked directly by the runner.

The fit challenger inverts the live engine's structure — value knockouts become dual
0–100 scores, preferences move from search-shrinking to post-score filters, package
shapes widen past `|give − receive| ≤ 1`. The 2026-08-19 arm-B audit measured why a
profile cannot express this: the consensus `rv ≥ gv` sign test, the divergence prune, and
the dual-surplus floor are code paths, not knob values; no `_cfg_override` reaches them.

## Decision

`backend/trade_gen_fit.py` is a standalone generator on the arm-C pattern: invoked only
by `bakeoff_runner.gen_fit_cards`, never routed through `_generate_trades_impl`, arm id
`fit` **outside** `ENGINE_ARMS` (no basis-split groups, `fairness_threshold = None` — the
honest answer, since its bar is the score stack, not a fairness floor). Live predicates
(K2–K7) are **called through the module namespace** (`ts.overpay_ok(...)`), never bound by
name and never forked — a knob or bug-fix in `trade_service` propagates to both arms
(the import-time-binding trap that produced a measured no-op in the audit).

## Consequences

- Organic serving is byte-identical with `trade.bakeoff` off; `test_organic_never_imports_fit`
  greps the organic branch and a fixture generate proves it.
- The arm costs one extra generation per bake-off job (measured 1.8 s at the 5,000
  package cap on the fixture league); kill switches are `bakeoff_include_fit = 0`
  (roster) and `bakeoff_serve_fit = 0` (serve-bit), both deploy-free.
- G6 knob changes move arm B **and** fit together by design; per-run isolation comes from
  `bakeoff_runs.config_json` snapshots, not forked predicates.
- Every `fit_*` knob carries an arm-A disposition sentence (the knob-inventory guard
  fails by name otherwise) — 17 keys as of this ADR.
