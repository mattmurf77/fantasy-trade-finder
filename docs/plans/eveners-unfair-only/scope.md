# Feature Scope — Calculator screenshot fixes: "Recommended to even it" only for unfair trades; column-mode asset rows never cut off (D-286)

**Date:** 2026-11-25
**Entry point:** direct ask (the owner, reviewing App Store screenshots): (1) "can we hide the 'recommended to even it' section? I want the value bar in that first screenshot"; (2) "Names can't be cutoff in the screenshots".
**Builder:** builder subagent, branch `fix/eveners-only-when-unfair`
**Operator sign-off on waivers:** not needed (waivers below are "nothing to add", not skipped work)

---

## What changes

1. **Eveners only when the trade needs evening.** The two-sided "Recommended to even it" rows render only when the evaluate `verdict` is `'unfair'`. `'fair'` and `'even'` hide them, so the value bar / fairness summary follows the trade window directly. A missing or unknown verdict renders them, as before. One predicate, `evenersWanted(verdict)` in `mobile/src/components/EvenerRows.tsx`, used by both calculators: `InLeagueCalculator` (in league) and `ConsensusVerdictCard` (Real values). The #264 half-built "Trade options" state (one side empty, no gap) is not gated. No server change: the server may still send `eveners`. Narrows #251 (placement is unchanged; the rows just no longer show for fair trades).
2. **Column-mode asset rows never end in "…".** `TradeSide` with `compact` (the merged in-league calculator's YOU SEND / YOU RECEIVE columns): the name has no line clamp and wraps; the meta row (position chip · detail · tier) is `flexWrap: 'wrap'` with no clamp; a pick row prints no detail text (the in-league pick's detail was "PICK · 0 yrs", the duplicate seen cut off); a projected pick's PROJ tag sits beside the PICK chip instead of on its own line. The stacked page (`compact` false) is unchanged. Reverses #411's "one line, wrapping declined" ruling for the name. The deck's `TradeCard` / `PlayerCard` are not touched (they clamp names the same way; reported to the owner).

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** a render-condition and layout change on existing surfaces; no new action, no new event. Existing calculator events are unchanged.

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none (item 2 only affects the existing `calc.merged_layout` column mode)
- New env vars / `model_config` keys: none. Rollback lever: revert the PR (mobile-only; ships with the next build).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-eveners-unfair-only.js` (`npm run test:eveners-unfair-only`). Executes `evenersWanted` and both calculators' real render conditions (lifted from the source) over fair / even / unfair / missing / one-sided payloads; structural-only pins for item 2 (no `numberOfLines={1}` or `ellipsizeMode` in TradeSide, the only clamp left is the compact team-name header, the meta row wraps, no pick detail in column mode, PROJ in the chip slot, stacked tag line kept). Re-specced honestly: `check-calc-merged-layout.js` 16 / 16b / 17e (the name clamp is gone by ruling), `check-projected-pick-tag.js` 3.3 (TradeSide mounts the tag twice: stacked line + column chip slot).
- [x] **Unit tests:** none (no backend change).
- [x] **Code-walk proof:** server `backend/server.py` ~20016: `verdict = "even" if point_ratio >= 0.95 else "fair" if fairness is not None else "unfair"`; one-sided reads leave `verdict` null and `gap` null. Client gate: `InLeagueCalculator.tsx` EvenerRows mount `… && evenerAddTo && (!ev.gap?.add_to || evenersWanted(ev.verdict))`; `ConsensusVerdictCard.tsx` `… && evaluation.gap?.add_to && evenersWanted(evaluation.verdict)`.
- [x] **Manual simulator / TestFlight checklist** (the coordinator runs it, 402 pt iPhone 17 Pro):
  1. In league, build a trade the bar reads as a win that the verdict rates fair (e.g. "You win by +463 · an Early 3rd"): no "Recommended to even it" block; the value bar sits under the trade window.
  2. Make it lopsided (verdict unfair): the block returns under the trade window with "add from your roster" / "ask @partner to add".
  3. Clear one side: "Trade options — from …" rows still show.
  4. Real values: fair trade shows no "Recommended to even it — add to Side A/B"; an unfair one does.
  5. Merged in-league columns with Luther Burden, Jahmyr Gibbs, Jaxon Smith-Njigba, a 2nd, a projected 1st ("2027 1.04 (from …)"): no row ends in "…"; names wrap if needed; pick rows show `[PICK]` (+ `PROJ`) and the tier, no "PICK" detail text.
- `testID`s added/renamed: none (testid-lint OK).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route or contract change |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` | n/a | no wiring change |
| `living-memory/HLD.md` | n/a | no architecture change |
| `docs/cross-client-invariants.md` | n/a | position / tier encodings unchanged and still never shrink |
| `docs/glossary.md` | n/a | no new term |
| ADR or `DECISIONS.md` entry | updated | D-286 |
| `mobile/src/components/CLAUDE.md` | updated | `EvenerRows`, `TradeSide` rows |

## 5. Ship gate declaration

- **CI green:** expected on the pushed sha; locally `tsc --noEmit` clean, all `mobile/tests/check-*.js` green, testid-lint OK (counts in TEST_LEDGER).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-11-25 entry.
- **Simulator check:** run by the coordinator on a throwaway branch; not run by the builder.
- Express lane declared by the operator? no
