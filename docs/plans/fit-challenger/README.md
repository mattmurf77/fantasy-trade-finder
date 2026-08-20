# Fit challenger

New bake-off generator: **thin knockouts** (shape, pick-churn, both lineups startable, G6 R1/R2/R3/R5) then **0–100 per team** (board / vs-consensus / consensus), present by **sum**. Preferences filter after scoring.

**Status:** built, not rostered · 2026-08-19
**Code:** `backend/trade_gen_fit.py`, bake-off arm `fit` (`bakeoff_include_fit=0`)
**PRD:** [PRD.md](PRD.md)
**Build order:** [PLAN.md](PLAN.md)
**Gate:** [scope.md](scope.md)

Arm id: `fit`. Default **off** the bake-off roster (`bakeoff_include_fit=0`). Organic serving stays live Arm B.

## Tickets

| ID | Title | Est | Depends |
|---|---|---:|---|
| F1 | Knockout wrappers (K1–K7) | 1d | — |
| F2 | Enumerator + caps | 2d | F1 |
| F3 | Dual 0–100 scorer | 1.5d | F2 |
| F4 | Post-score preference / R4 / C4 filters | 0.5d | F3 |
| F5 | Bake-off arm `fit` | 1d | F3 |
| F6 | Tests | 1d | F1–F4 |
| F7 | Dualize R5 (not v1) | — | operator |

## Do not

- Route `_generate_trades_impl` through this module.
- Treat this as a `MODEL_*_PROFILE` override of live (that’s landability-challenger).
- Kill on surplus, `rv ≥ gv`, #108, filler, Elo gap, or divergence prune.
- Inject likes-you.
- Brute-force `C(25,3)²` — pool cap is mandatory.

## Knockouts (one line)

K0 roster physics · K1 1–3 a side including 3-for-1 · K2 live pick-swap C3 · K3 both startable · K4 R1 · K5 R2 · K6 R3 · K7 R5 live (viewer-only).
