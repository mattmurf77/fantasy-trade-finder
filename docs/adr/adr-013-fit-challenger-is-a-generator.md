# ADR-013: The Fit Challenger Is a Generator, Not a Profile

Date: 2026-08-19
Status: Accepted
Related: [D-098](../../living-memory/DECISIONS.md), [PRD](../plans/fit-challenger/PRD.md)

## Context

The operator wants a bake-off arm that knocks out only roster physics, package shape, pick-churn, dual startable lineups, and G6 R1/R2/R3/R5, then scores every survivor 0–100 per team. Live generation kills on surplus, `rv ≥ gv`, #108, filler, Elo gap, and divergence prune. Those are "would they like this?" dressed as construction gates.

Two existing bake-off patterns were available:

1. **Profile overlay** (arm D, `challenger`, D-095) — same `_generate_trades_impl`, thread-local knob values.
2. **Direct generator** (arm C, `gen_v2`) — a separate module, invoked by the runner, never routed from organic serving.

A profile cannot drop `rv ≥ gv`, dual surplus, divergence prune, or package-shape `|n−m| ≤ 1` without forking the live predicates or wrapping every call site. Those are the volume unlock.

## Decision

Build arm `fit` as a **new generator** (`backend/trade_gen_fit.py`), invoked the same way as `gen_v2`: `bakeoff_runner.gen_fit_cards` calls `generate_league_suggestions` directly. `_generate_trades_impl` never imports the module. `bakeoff_include_fit` defaults to 0.

Knockouts wrap live predicates (`overpay_ok`, `pos_net_ok`, `pick_gap_ok`, `need_gate_ok`, `pick_swap_ok`, `_feasible_after`) rather than copying their bodies. Scoring is a signed tanh of board / vs-consensus / consensus surplus; rank by sum. Preferences filter after scoring.

## Alternatives considered

- **`_cfg_override` the live engine** (landability-challenger pattern): rejected — the live knockouts we need to *drop* are not knob-shaped (divergence prune, `|n−m| ≤ 1`, dual surplus as a kill). A profile that leaves them in is a different experiment.
- **Route organic serving through the new module behind a flag:** rejected — organic decks must stay byte-identical. The bake-off flag already exists; this arm rides it dark.
- **Brute-force C(25,3)²:** rejected — pool cap 15 + 1-for-1-then-expand + `fit_max_packages_per_pair` (20_000) is the bound.

## Consequences

- Five arms exist. Default roster is unchanged (`current`, `challenger`, `gen_v2`). Lighting `fit` is one config value and one extra sequential generation per bake-off job.
- `TradeCard.fit` is additive JSON; organic cards omit it.
- Dualizing R5 (partner need) is F7, not this ADR.
- Naming is load-bearing: `model_arm = 'fit'` is a stored column. Never reuse `challenger` or `gen_v2`.
