# FB-304 — group canonical folder

- **Status:** built 2026-08-16 (branch `feat/fb304-presentment`, awaiting merge + operator TestFlight checklist) · **Phase:** 2 (build)
- **Group:** G6 — Trade presentment rules (canonical: #304 #336 #339 #340 #341)
- **Batch plan:** [`batch-plan.md`](batch-plan.md)
- **Base:** specs `56856f7` = `origin/main` @ `96f6945` (incl. `3c0541c` suggestion.telemetry ON)
- **Build evidence:** [`build-verification.md`](build-verification.md) (45 pytest + 281 regression; 14/14 sabotages RED-then-green; two-sided band results; DB-4 pick replay) · [`code-walk-proof.md`](code-walk-proof.md) (CW-1)
- **Flag:** `trade.presentment_rules` ships **ON** (Q-G6-3, operator-final); knobs are the per-rule kill switches ([config-reference](../../../config-reference.md))
- **Decision record:** [D-062](../../../../living-memory/DECISIONS.md)
- **Owed before/at ship:** operator-run prod-state deck-eval replay (DB-1/DB-2 full fidelity — build env was blocked from the prod DB) + R-12 pick-knob tuning on it (NEXT.md 2026-08-16 G6 section); operator TestFlight checklist (prd §3.4) on the first build after deploy; `presentment-tripwire` log watch, first week, contender-heavy leagues especially.

## Reported

> The find a trade feature is doing a good job suggesting trades based on value, but I want to add another layer to the logic to focus on position specific needs for both owners. Ultimately for a trade suggestion to really work, it should help address the positional weaknesses of the teams. (Full text + the four rule items and all operator decisions: see batch-plan.md in this folder.)
