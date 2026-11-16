# Feature Scope — Fairness window (default "fair" threshold behind a flag)

**Date:** 2026-11-14
**Entry point:** direct ask (operator-approved spec, [spec.md](spec.md))
**Builder:** builder subagent on `feat/fairness-window`
**Operator sign-off on waivers:** the operator signed off the §1 analytics waiver on 2026-11-15 (PR #691 was merged on that sign-off).

---

## 1. Analytics scope

- [x] **(c) WAIVED, no new events needed because:** the served threshold is already recorded per card (`deck_impressions.fairness_threshold`, the bar the card had to clear), so decks built with the flag on can be told apart from flag-off decks without a new event.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: `trade.fairness_window_v2`, default **false** in `backend/feature_flags.py`, `config/features.json` and the three flag fixtures (`release`, `onboarding-v2`, `profiles-on`). Not in `FTF_FLAGS`. Graduation criterion: the replay rule in the spec adopts a candidate, the operator turns the flag on and sets the knob, and served-deck like rates do not fall.
- New `model_config` key: `fairness_window_default` (0.75, allowed 0.55–0.75). Rollback lever: flag off + `POST /api/feature-flags/reload`, or knob back to 0.75. No deploy either way.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-fairness-default.js` (extended) runs the real `tradePregen` module. It pins served value → ON threshold, absent or invalid → 0.75, OFF never moves, the constant never moves, and that `api/flags.ts` writes the value on the success path only.
- [x] **Unit tests:** `backend/tests/test_fairness_window.py`: registration, the single constant, knob validation, flag off never reads config, the payload key off and on, `/api/trades/generate` resolution (off, on, explicit, pinned), flag-off deck identical to an explicit 0.75 deck, cache keys per threshold, the replay tool on a synthetic fixture, and the decision rule. Every new test was sabotage-checked (TEST_LEDGER).
- [x] **Code-walk proof** (flag off = today):
  - `server.py` `/api/trades/generate`: `default_fairness = 0.50 if _any_pinned else _fairness_window.default_fair_threshold()`. With the flag off, `fairness_window.default_fair_threshold` returns `FAIR_DEFAULT` (0.75) before any config read.
  - `feature_flags_route` spreads `_fairness_window.payload_fields()`, which is `{}` with the flag off, so the payload is byte-identical.
  - Mobile `flags.ts` calls `setServedFairnessOnThreshold(undefined)` when the key is absent, so `fairnessThresholdFor(true)` returns `FAIRNESS_ON_THRESHOLD` (0.75), as today.
  - Session init (`auth.ts:305`) and prewarm/presentation (`useTradePagePrewarm.ts:43`, `usePresentationDeck.ts:75`) all go through that helper, so first, prepared, paged and presentation decks send the same number as today.
  - Signature defaults (`_kickoff_trade_job`, `TradeService._generate_trades_impl`, `_generate_for_pair`) are `FAIR_DEFAULT` = 0.75.
  - The consensus note (`consensusNote.ts`, `NORMAL_LOW`) and the swap sheet (a ±15% band, no threshold read) are untouched.
- [x] **Manual TestFlight checklist** (only after the operator turns the flag on and sets the knob to X):
  1. Cold start, open Trades, turn **Balanced trades** on. The deck loads. No card shows a market ratio below X (or below 0.65, whichever is higher).
  2. A consensus card whose ratio is between X and 0.75 shows "This league-mate hasn't ranked players yet." without "balanced".
  3. Turn the flag off and `POST /api/feature-flags/reload`, then background the app for 30+ minutes or cold start. Balanced trades again shows only cards at 0.75 or above.
- testIDs added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `GET /api/feature-flags` (`fairness_on_threshold`), `POST /api/trades/generate` (default threshold) |
| `living-memory/LLD.md` | n/a because | no schema, route or invariant convention shifted (an additive payload key follows the existing `pass_reason_cadence` pattern) |
| `docs/architecture.md` | n/a because | no module wiring or data flow change beyond one helper module |
| `living-memory/HLD.md` | n/a because | no architecture shift |
| `docs/cross-client-invariants.md` | updated | § Consensus balance claim: the 0.75 bar does not follow the window |
| `docs/glossary.md` | n/a because | no new domain term ("fairness threshold" already exists) |
| ADR or `DECISIONS.md` | updated | D-266 |
| `docs/config-reference.md` | updated | flag row + `fairness_window_default` knob row |

## 5. Ship gate declaration

- **CI green:** backend-tests, mobile-typecheck, testid-lint, on the pushed sha (main session).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-11-14 fairness-window entry.
- **TestFlight verification:** only after the flag is turned on (checklist above).
- Express lane declared by the operator? no.

## Copy that states "75%" (listed, not changed — spec §5)

- `web/index.html` fairness slider: initial value 75, label text "75%" (the web slider is the user's own explicit choice; unchanged).
- Mobile: no user-visible text states 75%. The toggle reads "Balanced trades" / "Ranked by mismatch". The consensus note says "balanced" only at ≥ 0.75 (by design, D-266).
