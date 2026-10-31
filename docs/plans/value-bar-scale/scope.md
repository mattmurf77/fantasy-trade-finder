# Feature Scope — The value bar's ±2nd landmark at today's Mid 2nd / Mid 1st (0.57 → 0.287)

**Date:** 2026-10-31
**Entry point:** direct ask. head-eng routed it for the 11-06 binary, after league-eng's share card (#564) used current values.
**Builder:** trades-eng
**Operator sign-off on waivers:** not needed. The waivers below are for things this change doesn't touch.

**Why:**
- The bar spans ±1 Mid 1st, and its inner ticks mark ±2nd at the Mid 2nd / Mid 1st value ratio. The app's constant, `TradeValueBar.tsx` `SECOND_IN_FIRSTS = 0.57`, had drifted: over today's `GENERIC_PICK_SEEDS` the ratio is **0.287**.
- At 0.57, a fill reading "≈ a Late 1st" (0.6 firsts; a Late 1st is 0.705) ended on the "2nd" tick.
- **The change:**
  - the constant becomes 0.287;
  - the web landing miniature's ticks move from 21.5 / 78.5% to 35.65 / 64.35%;
  - a backend test pins both to `elo_to_value(Mid 2nd) / elo_to_value(Mid 1st)`, the same source the share card's bar computes from server-side (#564).
- **Not the API route:** adding `second_in_firsts` to every served `gap` would change every card's JSON and the byte-identical goldens, for a static tick.
- The bar's fill, copy and `gap.firsts` are unchanged; only where the ±2nd ticks and labels sit moves.

## 1. Analytics scope
- [x] **(c) WAIVED. No analytics needed:** no event is added or changed.

## 2. Schema & flag scope
- **New/changed tables, columns, flags, env vars or `model_config` keys:** none.

## 3. Evidence scope
- [x] **Unit tests:** `backend/tests/test_value_bar_scale.py`.
  - It pins the app's `SECOND_IN_FIRSTS` to the seeds' ratio (±0.005), and the web miniature's four landmark positions to it (±0.1%).
  - **Main's 0.57 fails it.**
- [x] **Before/after render:** `docs/plans/value-bar-scale/renders/before-after.png`. It's a Pillow mock of the bar's geometry, not a device capture (D-056), for the operator's parallel design review.
- [x] **Manual TestFlight checklist** (operator, 11-06 binary):
  1. Calculator, a trade whose gap reads "≈ a Late 1st": the fill ends past the "+2nd" / "−2nd" tick, not on it.
  2. A trade reading "≈ a Mid 2nd": the fill ends at about the 2nd tick.
  3. A deck card's value bar shows the same tick positions.
  4. The web landing page's miniature shows its ticks at the same place.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route or payload change |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | no wiring change |
| `docs/cross-client-invariants.md` | updated | "Trade value-verdict shape": the ±2nd landmark, its source and the pin |
| `docs/glossary.md` / ADR / `DECISIONS.md` | n/a | no new term or decision; a stale constant corrected |

## 5. Ship gate declaration
- **CI green:** `backend-tests`, `mobile-typecheck`, `testid-lint`, `web-structure`.
- **Evidence recorded:** TEST_LEDGER.
- **TestFlight verification:** the checklist above.
- Express lane declared by the operator? No.
