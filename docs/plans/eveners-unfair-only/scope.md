# Feature Scope — Calculator and deck screenshot fixes: "Recommended to even it" only for unfair trades; asset names and rows never cut off (D-286)

**Date:** 2026-11-25
**Entry point:** direct ask (the owner, reviewing App Store screenshots): (1) "can we hide the 'recommended to even it' section? I want the value bar in that first screenshot"; (2) "Names can't be cutoff in the screenshots".
**Builder:** builder subagent, branch `fix/eveners-only-when-unfair`
**Operator sign-off on waivers:** not needed (waivers below are "nothing to add", not skipped work)

---

## What changes

1. **Eveners only when the trade needs evening.** The two-sided "Recommended to even it" rows render only when the evaluate `verdict` is `'unfair'`. `'fair'` and `'even'` hide them, so the value bar / fairness summary follows the trade window directly. A missing or unknown verdict renders them, as before. One predicate, `evenersWanted(verdict)` in `mobile/src/components/EvenerRows.tsx`, used by both calculators: `InLeagueCalculator` (in league) and `ConsensusVerdictCard` (Real values). The #264 half-built "Trade options" state (one side empty, no gap) is not gated. No server change: the server may still send `eveners`. Narrows #251 (placement is unchanged; the rows just no longer show for fair trades).
2. **Column-mode asset rows never end in "…".** `TradeSide` with `compact` (the merged in-league calculator's YOU SEND / YOU RECEIVE columns): the name has no line clamp and wraps; the meta row (position chip · detail · tier) is `flexWrap: 'wrap'` with no clamp; a pick row prints no detail text (the in-league pick's detail was "PICK · 0 yrs", the duplicate seen cut off); a projected pick's PROJ tag sits beside the PICK chip instead of on its own line. The stacked page (`compact` false) is unchanged. Reverses #411's "one line, wrapping declined" ruling for the name. **Follow-up after the 402 pt simulator run:** the detail ("CAR · 23 yo") is `flexShrink: 0` (it was `flexShrink: 1` + `minWidth: 0`, which squeezed it letter by letter between chip and badge), so the tier badge wraps to line 2 instead; the calculator now says "yo" like the deck card (`PlayerPickerModal` still says "yrs", not changed).
3. **Deck trade card names never cut off.** `PlayerCard` in its `compact` form (the YOU SEND / YOU GET boxes of `TradeCard`, beside lock / swap / remove) no longer clamps the name: `numberOfLines={compact ? undefined : 1}` (was 1, or 2 for a projected pick). Seen at 402 pt: "Tetairoa M…", "Jahmyr Gi…", "2027 1.04 / (from hard…". Buttons, position chip, PROJ tag and the team / age line are unchanged; the box grows. `TradeCard` is the only host of the compact form; its hosts all size the card from content (deck: `onLayout` + the peek clipped to the measured height; Matches: unmeasured rows, no `getItemLayout`; FeaturedTradeWindow; Overhaul review), so none breaks. Tiers, Free agents and League Summary use the `dense` branch, which keeps its one-line name (fixed 60 / 32 pt rows).

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** a render-condition and layout change on existing surfaces; no new action, no new event. Existing calculator events are unchanged.

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none (item 2 only affects the existing `calc.merged_layout` column mode)
- New env vars / `model_config` keys: none. Rollback lever: revert the PR (mobile-only; ships with the next build).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-eveners-unfair-only.js` (`npm run test:eveners-unfair-only`). Executes `evenersWanted` and both calculators' real render conditions (lifted from the source) over fair / even / unfair / missing / one-sided payloads; structural-only pins for item 2 (the detail never shrinks: `flexShrink: 0`, no `minWidth: 0`, no clamp; "yo"; no `numberOfLines={1}` or `ellipsizeMode` in TradeSide, the only clamp left is the compact team-name header, the meta row wraps, no pick detail in column mode, PROJ in the chip slot, stacked tag line kept) and item 3 (§4: compact PlayerCard name unclamped, old 2-line rule gone, TradeCard is the only compact host, found by scanning `src`). Re-specced honestly: `check-calc-merged-layout.js` 17 (detail no longer the yielder), `check-calc-merged-layout.js` 16 / 16b / 17e (the name clamp is gone by ruling), `check-projected-pick-tag.js` 3.3 (TradeSide mounts the tag twice: stacked line + column chip slot) and 4.2b (compact rows unclamped).
- [x] **Unit tests:** none (no backend change).
- [x] **Code-walk proof:** server `backend/server.py` ~20016: `verdict = "even" if point_ratio >= 0.95 else "fair" if fairness is not None else "unfair"`; one-sided reads leave `verdict` null and `gap` null. Client gate: `InLeagueCalculator.tsx` EvenerRows mount `… && evenerAddTo && (!ev.gap?.add_to || evenersWanted(ev.verdict))`; `ConsensusVerdictCard.tsx` `… && evaluation.gap?.add_to && evenersWanted(evaluation.verdict)`.
- [x] **Manual simulator / TestFlight checklist** (the coordinator runs it, 402 pt iPhone 17 Pro):
  1. In league, build a trade the bar reads as a win that the verdict rates fair (e.g. "You win by +463 · an Early 3rd"): no "Recommended to even it" block; the value bar sits under the trade window.
  2. Make it lopsided (verdict unfair): the block returns under the trade window with "add from your roster" / "ask @partner to add".
  3. Clear one side: "Trade options — from …" rows still show.
  4. Real values: fair trade shows no "Recommended to even it — add to Side A/B"; an unfair one does.
  5. Merged in-league columns with Luther Burden, Jahmyr Gibbs, Jaxon Smith-Njigba, a 2nd, a projected 1st ("2027 1.04 (from …)"): no row ends in "…"; names wrap if needed; pick rows show `[PICK]` (+ `PROJ`) and the tier, no "PICK" detail text.
  6. Deck card with "Tetairoa McMillan + 2027 1.04 (from hardcount)" for "Jahmyr Gibbs" (and Jaxon Smith-Njigba if available): no name ends in "…"; the lock / swap / remove buttons, chip, PROJ and the team / age line are as before; the card is taller and the peek card behind it does not poke out. Same on a Matches card.
  7. Calculator columns: "CAR · 23 yo" on one line next to the WR chip, `[2 1STS]` on line 2 when it does not fit.
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
