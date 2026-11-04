# Feature Scope — The web calculator's "Favors you / them" label reads `favors` the right way round

**Date:** 2026-11-03
**Entry point:** direct ask. head-eng (round 4), from #567's QA: a web-only bug on main since #263 (`1eb520bd`).
**Builder:** trades-eng
**Operator sign-off on waivers:** not needed. The waivers are for things this change doesn't touch.

**The bug:** `web/calculator.html` labelled `favors: 'give'` as "Favors you". `favors` means who the value leans to: `receive` = you get more back, so you win; `give` = they do (cross-client-invariants § Trade value-verdict shape; the app's `TradeValueBar` `youWin = favors === 'receive'`). The page's own gap line read it right ("add to their side"), so the label contradicted it.

**The change:** `receive` → "Favors you", `give` → "Favors them". `even` / absent → "Even both ways", unchanged. It's web only (Render deploy), so there's no binary dependency.

**Not in this change:** whether the web calculator should follow the app's B2 Even rule. That's head-product's call, and held.

## 1. Analytics scope
- [x] **(c) WAIVED:** no event or prop changes; a label's wording only.

## 2. Schema & flag scope
- No tables, flags, env vars or `model_config` keys.

## 3. Evidence scope
- [x] **Structural guard:** `mobile/tests/check-web-calc-favors.js` (`npm run test:web-calc-favors`), 7 checks. It **executes** the page's own `favorsTxt` expression on `receive`, `give`, `even` and absent. It also pins the app's reading (`youWin = favors === 'receive'`) and the page's gap line. It fails 2 on main.
- [x] **Browser check: not run.** `renderVerdict` sits inside the page's closure and needs a running backend with player values. The guard executes the changed expression itself.
- **Design change, for the operator** (a word on one label): before, a trade where you send more read "Favors you"; after, it reads "Favors them". A trade where you get more back is the reverse.
- [x] **Manual check** (web, after deploy): `/calculator.html`, a trade where you get clearly more value back reads "Favors you", with the gap line saying "add to your side". Swap the sides: "Favors them", "add to their side".

## 4. Docs scope
| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | no wiring change |
| `docs/cross-client-invariants.md` | n/a | already states the reading; the web page now follows it |
| `docs/glossary.md` | n/a | no new term |

## 5. Ship gate declaration
- **CI green:** `backend-tests`, `mobile-typecheck` (runs the check suites), `testid-lint`.
- **Evidence recorded:** TEST_LEDGER.
- **Ships with the Render deploy, on the operator's merge go.** The operator's review of the wording change runs alongside.
- Express lane declared by the operator? No.
