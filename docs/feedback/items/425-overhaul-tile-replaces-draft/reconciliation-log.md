
## Orchestrator rulings 2026-09-08 (Phase 1 exit)

- Q1 colour: **ice** via the single `HERO_TONE` constant; "true red" surfaced to the operator in the ship summary (needs a design-system token decision, ADR-004/005). Q2 keep the control cohort's mode-bar Draft chip. Q3 hero renders wherever the card rendered (parity now). Q4 Draft cell stays removed when `overhaul.enabled` is off. Fast path: single planner, no blocking objections.

## Phase 3 round 1 — 2026-09-08

QA-A PASS (0 findings, 14/14 sabotages RED), QA-B PASS (0 findings, 13/13). Observation O-1 (Find a Trade is ice-outlined, not ice-filled; ≤3 rule holds with margin) — PRD wording noted, no change. **Group ship-ready.** Operator question outstanding: true red for the hero requires a design-system token (ADR-004/005); shipped in ice via the single `HERO_TONE` constant.
