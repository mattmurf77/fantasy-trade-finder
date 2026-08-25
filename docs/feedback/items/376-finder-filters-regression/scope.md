# Feature Scope — #376/#379/#394 minimized "Outlook & filters" row on TradesHome

**Date:** 2026-08-24
**Entry point:** feedback #394 (canonical defect) + #379 (placement ruling) + #376 (history); 2026-08-24 feedback wave, Group A
**Builder:** Group A author agent → build agent, branch `claude/new-user-feedback-55320e`
**Operator sign-off on waivers:** pending — one waiver in §1(c-adjacent) is surfaced below; everything else answered

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — verified against `backend/analytics_taxonomy.py` and the emitting sources:
  - **The new row's tap emits no new event, matching every existing sibling entry.** Neither `OutlookBiasReceipt`'s "Change" (`OutlookBiasReceipt.tsx:114-126`), the calculator's `calc.outlook-fallback.change` (`InLeagueCalculator.tsx:726-741`), nor the utility-row Filters button being removed (`TradeHomeUtilityRow.tsx:72-86` — haptics + handler only) emits an open event today; no `dna_sheet_opened` or utility-row tap event exists in the taxonomy. The behavioral signal is the existing **`outlook_saved {source}`** (`backend/analytics_taxonomy.py:412,1290`), fired by `TradeDnaSheet` on save (`TradeDnaSheet.tsx:454`) with `source` from the screen's `dnaOpenSource` state (`TradesScreen.tsx:748`) — the new row leaves it at its default `'sheet'`, the same value the receipt's Change and the removed Filters button produced. Question it answers: "are users reaching and using the outlook/filters editor?" — continuous across this change, with no source-value migration.
  - **Removing the Filters button kills no emitter** — checked: `TradeHomeUtilityRow.tsx` contains no `track(`/analytics call, and no `trades.home-utility.*` event is registered in `analytics_taxonomy.py`. Nothing to deregister, no NULL-property risk.
  - **Explicit waiver (surfaced, not silent):** a distinct open-source value (e.g. `source:'fallback_row'` on `outlook_saved`, or a new open event) would let us distinguish row-opened sheets from receipt-opened ones. Deliberately not added: it would be the only open-instrumented entry among four peers, and taxonomy additions are a bright-line pairing (register + `NON_INTENT_EVENTS` classification in the same commit) that this fast-track fix doesn't need. If the operator wants the distinction, it is a two-line follow-up.

## 2. Schema & flag scope

- New/changed tables or columns: **none** (client-only; reads the existing `['league-prefs', leagueId]` query).
- New/changed feature flags: **none.** The row's gate is composed entirely of existing predicates (`consolidateOn` = `trades.edit_full_sheet` × finder mode, `outlookReceiptShown`, `firstRun`). No flags flipped: `trade.outlook_direction` stays false; `trades_home_inline` experiment untouched. Honest confirmation: no schema, API, flag, or analytics-event surface changes — verified, not assumed (grep of the diff plan against `config/features.json`, `backend/server.py` routes, `analytics_taxonomy.py`).
- New env vars / `model_config` keys: **none.** Rollback lever = revert the commit (self-contained: two source files + one guard).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-finder-conditions-reachable.js` — **rewritten** (filename + `npm run test:finder-conditions` kept). Pins: the `trades.outlook-fallback` row exists with its Change control wired to `setDnaSheetOpen(true)`; its gate references `consolidateOn` + `outlookReceiptShown` and sits outside the `!consolidateOn` legacy branch; the gate is independent of `trade.outlook_direction` and `showInlineHome`; `trades.home-utility.conditions` is **absent** (inverts three old assertions — same commit as the code or CI reds); the #269 `hideTeamAndPlayer` guard survives. Full assertion/sabotage matrix: [prd.md](prd.md) §6a. `check-trades-banner-region.js` verified unaffected — no edit (prd.md §6b).
- [ ] **Unit tests:** none — no backend change; `pytest backend/tests` runs unchanged as the regression gate.
- [x] **Code-walk proof:** variant × flag × outlook-state truth table proving exactly one persistent outlook surface per cell and sheet reachability from each — outline in prd.md §6c; builder produces the final file:line-cited version against the merged diff.
- [x] **Manual TestFlight checklist:** prd.md §6d — 7 steps covering strip-variant declared/undeclared, Filters-button absence, sheet round-trip → row reflects the change, control variant, and first-run.
- `testID`s added/renamed: added `trades.outlook-fallback`, `trades.outlook-fallback.change`, `trades.outlook-fallback.details`; removed `trades.home-utility.conditions` (its control is deleted; no retained Maestro flow gains a dangling reference the lint would flag — `scripts/testid-lint.sh` run in the gate confirms both directions).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/removed/contract-changed (client-only) |
| `living-memory/LLD.md` | n/a | no schema/route/invariant *convention* shifts — the row reuses the #254 complement-predicate convention already recorded |
| `docs/architecture.md` | n/a | no backend module wiring or data-flow change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | outlook mode enums read, not extended; no tier/position hexes; no new cross-client enum or color (verified in prd.md §4 — ink/chalk/ice tokens only) |
| `docs/glossary.md` | n/a | no new domain term ("outlook", "Trade DNA" already present) |
| ADR or `DECISIONS.md` entry | build session | one DECISIONS.md entry: fallback-row pattern promoted from the calculator to TradesHome + the #379 removal arbitration (provisional A1/A2 per prd.md §8) |
| `mobile/src/components/CLAUDE.md` | build session | `TradeHomeUtilityRow` row: drop the #376 conditions-entry description |
| `mobile/src/screens/CLAUDE.md` | build session | `TradesScreen` row: note the always-available minimized outlook/filters row |
| `screens/` capture library | n/a | frozen at 2026-08-11 (D-056); its CLAUDE.md forbids new captures — no update |
| `mockups/` | n/a | no mockup produced; design mirrors the shipped `calc.outlook-fallback` row |
| `docs/config-reference.md` | n/a | no flag/env/model_config change |
| `docs/data-dictionary.md` | n/a | no schema change |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (runs every `mobile/tests/check-*.js`, incl. the rewritten guard) + `maestro-testid-lint` — all on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming: guard rewrite + sabotage-matrix run (every named sabotage in prd.md §6a — including the whitelist's aliasing sabotage — observed red, then reverted), tsc, testid-lint, code-walk link, checklist handed to operator.
- **TestFlight verification:** checklist in prd.md §6d — operator runs post-build; outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **No** — full gates (this scope block is gate 1).
