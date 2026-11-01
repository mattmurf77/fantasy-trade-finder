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
- **The League "Works right now" example** (`LeagueScreen.tsx` `EXAMPLE_GAP`, every user with no matches sees it) was the clients' only static gap. It said "a Mid 2nd (≈ 0.6 firsts)" at 380, which with the new tick fills far past it. It's now what the server would send for a Mid 2nd gap: 607, 0.29 firsts, pick value 606.5 (release-lead's #567 QA P2-1).
- **What this doesn't cover:**
  - **A live prod `elo_value_k` change** moves the server's values, and so #564's share-card bar and its snapshots, but not the app's constant or the web miniature, with CI green: the pin reads the code's seeds and curve, not prod's `model_config`. If `elo_value_k` is ever changed live, this constant must follow by hand.
  - **Label crowding:** the ±2nd labels sit in a frame inset 30pt from each end while the ticks span the whole track, so each label sits about 8.6pt inboard of its tick. With the ticks closer to "Even", "−2nd" and "+2nd" overlap "Even" from text scale 1.21 at 283pt of bar (the League example on a 375pt phone) and from 1.29 at 298pt. Deck cards are clear. Moving the labels into the ticks' frame is a follow-up for design.

## 1. Analytics scope
- [x] **(c) WAIVED. No analytics needed:** no event is added or changed.

## 2. Schema & flag scope
- **New/changed tables, columns, flags, env vars or `model_config` keys:** none.

## 3. Evidence scope
- [x] **Unit tests:** `backend/tests/test_value_bar_scale.py`.
  - It pins the app's `SECOND_IN_FIRSTS` to the seeds' ratio (±0.005), and the web miniature's four landmark positions to it (±0.1%).
  - It pins the League example's `EXAMPLE_GAP` to a Mid 2nd at today's values: its label, pick value, value and `firsts`.
  - **Main's 0.57 fails it, and so does main's 380 / 0.6 example.**
- [x] **Before/after renders**, for the operator's design review: `renders/before-after-317.png` (a calculator or deck card on a 375pt phone) and `renders/before-after-283.png` (the League example card).
  - `renders/render.py` draws `TradeValueBar` from its own styles, collapsed as every mount starts: the app's tokens and fonts, the 14pt `ink3` rail with `ink.line` ticks, the fill in `semantic.pos` / `semantic.warn`, and the scale labels in chalk.faint Plex Mono in their inset frame.
  - Each case's copy and fill come from the server's own `_pick_gap_equivalent`. They're mocks, not device captures (D-056).
  - The first render (release-lead's #567 QA P2-2) was a geometry sketch: the wrong colours and fonts, bright ticks, and a "+1,840 · ≈ a Late 1st" reading the server would call a Mid 1st. Redrawn.
- [x] **Manual TestFlight checklist** (operator, 11-06 binary). The cue for steps 1–3: each ±2nd tick sits about a third of the way from Even to the end of the bar. The old build had it past halfway.
  1. **Calculator**, a trade whose gap reads "an Early 2nd" (0.35–0.56 firsts): the fill ends clearly past the +2nd (or −2nd) tick. The old build stopped short of it.
  2. **A trade reading "a Mid 2nd":** the fill ends at about the 2nd tick.
  3. **A "They win" trade:** the fill grows left, in amber, against the −2nd tick the same way. And **a deck card's value bar** shows the ticks in the same place.
  4. **League tab, "Works right now" example card** (shown with no matches): it reads "You win by +607 · a Mid 2nd (≈ 0.3 firsts)", and the fill ends on the +2nd tick.
  5. **iPhone Settings → Accessibility → Display & Text Size → Larger Text at its largest standard size**, back on the League example: the bar and its labels still render. The ±2nd labels may crowd "Even"; that's the known label-frame follow-up above, not a regression of this change.
  - **Web, not TestFlight** (it ships with the Render deploy): the landing page's step 03 view, "Real offers", shows the miniature's ±2nd ticks about a third of the way from Even.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route or payload change |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | no wiring change |
| `docs/cross-client-invariants.md` | updated | "Trade value-verdict shape": the ±2nd landmark, its source and the pin. #564 adds a line saying the app still uses 0.57: whichever of #564 and #567 lands second drops it |
| `docs/design/components.md` | updated | TradeValueBar's "≈0.57" and the web miniature's "21.5%/78.5%" (release-lead's #567 QA P3) |
| `docs/glossary.md` / ADR / `DECISIONS.md` | n/a | no new term or decision; a stale constant corrected |

## 5. Ship gate declaration
- **CI green:** `backend-tests`, `mobile-typecheck`, `testid-lint`, `web-structure`.
- **Evidence recorded:** TEST_LEDGER.
- **TestFlight verification:** the checklist above.
- Express lane declared by the operator? No.
