# Feature Scope — TradesHome wave 2026-08-13 (#309 · #312 · #314 · #315 · #316 · #317)

**Date:** 2026-08-13
**Entry point:** feedback #309/#312/#314/#315/#316/#317 (multi-ID fix filed under lowest ID)
**Builder:** wave-trades build agent (worktree `wave-trades`, base `origin/main` @ `60fccc7`, plan `plan-2026-08-13.md` @ `9387898`)
**Operator sign-off on waivers:** pending — waivers below are surfaced for the wave's QA/operator pass (plan §9 lists the four operator confirmations; the #314 Players pill is additionally HELD and was not built)

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** all six items are copy,
  layout, or reachability fixes with zero new behavior to measure (plan §8):
  - **#309** copy-only; the fallback surface fires no events by design (P0-6;
    `SEND_SURFACES` is registered for P0-7).
  - **#312** pure layout reorder; the add buttons carry no events.
  - **#314/#315** presentation/re-order; the Change tap and pickers keep
    their existing wiring. (Players-pill usage measurement would be a
    taxonomy addition → separate ask; the pill is HELD anyway.)
  - **#316** copy swap; `deck_summary_viewed` fires unchanged.
  - **#317** restores an existing surface's reachability; `deck_summary_viewed`,
    `find_trades_tapped`/`trade_card_viewed` (`mode: 'single_pin'`) fire
    unchanged — #298's own precedent: no new names for a WHERE-controls-render
    regression (no baseline).

  No event payloads are touched anywhere in the wave (the NULL-`platform`
  class of risk is not in play).

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **none** (two new *test fixtures* under
  `backend/tests/fixtures/flags/`: `release-espn-send-off.json` = release
  minus `espn.send`. NOT a flag-surface change — no `config/features.json`,
  no `FLAG_KEYS` edits. The plan's second fixture, `release-inline-strip.json`,
  was NOT created — see the plan defect in `status-2026-08-13.md` §5.)
- New env vars / `model_config` keys: **none**

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/trades-banner-region.yaml` — #315
  end-to-end (declare outlook + chasing WR through the full sheet → receipt
  renders WITH the `details` row). Runs under `release` — the plan's
  `release-inline-strip.json` fixture is unrepresentable on this harness
  (experiment overlay, not a `FLAG_KEYS` flag; defect reported), so the flow
  does not assert the strip's presence.
- [x] **Extended flow:** `mobile/.maestro/flows/smoke/12-trades-single-pin.yaml`
  — bounded pass loop to deck-done → `trades.deck-summary` +
  `".*Fresh ideas land.*"` (#316) → tile tap → summary notVisible +
  `featured-trade.window` visible (#317).
- [x] **Repointed flow:** `mobile/.maestro/flows/p0-6-espn-copy-trade.yaml`
  — was stale-on-arrival (asserted the pre-#309 string under a fixture where
  the fallback is unreachable); now runs under `release-espn-send-off` and
  asserts `".*Sending isn.t available.*"`.
- [x] **WAIVED (#312 Maestro delta):** Maestro cannot assert the left/right
  order of two visible elements. Enforceable artifact:
  `mobile/tests/check-dna-side-order.js`; the Tier-1 `screen-capture.sh` pass
  records the visual. (Plan §2, waiver surfaced per gate 2.)
- [x] **WAIVED (#314 strip-position Maestro assert):** same
  order-not-assertable limitation PLUS the fixture gap above. Enforceable
  artifact: `mobile/tests/check-trades-banner-region.js` assertion 1.
- `testID`s added: `trades.outlook-receipt.details` (static, registered in
  `mobile/src/components/CLAUDE.md`). Allow-list additions (template-literal
  ids now referenced by flows): `dna.outlook.*`, `dna.chase.*`,
  `featured-trade.idea.*`. `testid-lint.sh` passes.
- **Capture delta:** `trades` (TradesHome — banner region + deck-done) and
  `sheets/trade-dna` (add-button order) at ship.
- Smoke-suite impact: smoke/12 extended (above); no other smoke flow crosses
  the changed surfaces. Unit suites all green — counts in
  `status-2026-08-13.md` §3.
- Backend pytest: none — zero backend code changes (fixture JSON only; the
  all-bool fixture validator covers it).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | zero route changes (mobile-client-only wave) |
| `living-memory/LLD.md` | n/a | no convention shift — #298's convention is refined, and the refinement lives in the proposed invariants row (plan §7) |
| `docs/architecture.md` | n/a | no module wiring / data-flow change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | **proposed, not edited** (shared doc — house constraint) | two proposed rows in `status-2026-08-13.md` §6: "Trade side order — give-left/get-right everywhere" + the `NO_SEND_REASON` copy-shape update |
| `docs/glossary.md` | **proposed, not edited** | proposed note: "waivers" is a tier key + FA concept only, never user-facing copy for the weekly deck refresh (#316) |
| `docs/design/components.md` | **proposed, not edited** | proposed spec updates in `status-2026-08-13.md` §6 (receipt two-row spec, strip position + held third pill, deck-done resume note) |
| ADR / `DECISIONS.md` | n/a | no non-obvious choice beyond the plan's own rulings; in-footprint maps updated (`mobile/src/components/CLAUDE.md` rows for SendInSleeperButton, OutlookBiasReceipt, TradingWithStrip, AssetIdeasPanel) |

## 5. Ship gate declaration

- **Simulator-gate tier:** Tier 1 (plan §6) — full smoke suite (incl.
  extended 12) + `p0-6-espn-copy-trade` + `trades-banner-region` +
  `screen-capture.sh` for TradesHome + the DNA sheet. `trade-send/mfl-send-gating`
  remains BLOCKED (no `qa_mfl` profile — pre-existing waiver, unchanged).
- Evidence: TEST_LEDGER entry + `qa/sim-runs/last-sim-run.json` to be written
  after the wave's sim run (this build session ran the static battery only —
  outputs in `status-2026-08-13.md` §3).
- Operator deviation from the matrix: none declared.
