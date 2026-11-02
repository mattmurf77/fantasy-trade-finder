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
- The bar's fill, copy and `gap.firsts` are unchanged; only where the ±2nd ticks and labels sit moves. The B2 rule below is the one exception.
- **The B2 rule** (Product P112, 11-02; head-eng round 3b; the share image does the same in #564, league-eng):
  - The "≈ N mid 1sts" form shows only at a gap of **at least one first**.
  - A null `pick_equivalent` below that is the server's negligible floor (under half the smallest generic pick, 0.058 firsts today), so the bar reads **Even**: the centred nub, the "Even" headline, "Within a rounding error — N apart", and the even "Why?". Before, it read "You win by +40 · ≈ 0.0 mid 1sts" with a sliver.
  - A lean **with** a pick label is unchanged, however small, and so is a no-pick gap of one first or more ("≈ 1.8 mid 1sts").
  - It is one condition in `TradeValueBar.tsx` (`negligible = !pick && firsts < 1`, folded into `even`), so every mount gets it: deck cards, the calculator, Matches, the League example and Shop.
  - **Not changed, for design:** the Even line's existing "(≈ 0.0 firsts)" tail, which the Even state already showed whenever `gap.firsts` was non-zero.
- **The League "Works right now" example** (`LeagueScreen.tsx` `EXAMPLE_GAP`, every user with no matches sees it) was the clients' only static gap. It said "a Mid 2nd (≈ 0.6 firsts)" at 380, which with the new tick fills far past it. It's now what the server would send for a Mid 2nd gap: 607, 0.29 firsts, pick value 606.5 (release-lead's #567 QA P2-1).
- **What this doesn't cover:**
  - **A live prod `elo_value_k` change** moves the server's values, and so #564's share-card bar and its snapshots, but not the app's constant or the web miniature, with CI green: the pin reads the code's seeds and curve, not prod's `model_config`. If `elo_value_k` is ever changed live, this constant must follow by hand.
  - **Label crowding:** the ±2nd labels sit in a frame inset 30pt from each end while the ticks span the whole track, so each label sits about 8.6pt inboard of its tick. **It's a regression of this change:** with the ticks closer to "Even", "−2nd" and "+2nd" overlap "Even" from text scale 1.21 at 283pt of bar (the League example on a 375pt phone; it was 2.41 before) and from 1.29 at 298pt. Deck cards are clear at default sizes. Moving the labels into the ticks' frame is a follow-up for design.

## 1. Analytics scope
- [x] **(c) WAIVED. No analytics needed:** no event is added or changed.

## 2. Schema & flag scope
- **New/changed tables, columns, flags, env vars or `model_config` keys:** none.

## 3. Evidence scope
- [x] **Unit tests:** `backend/tests/test_value_bar_scale.py`.
  - It pins the app's `SECOND_IN_FIRSTS` to the seeds' ratio (±0.005), and the web miniature's four landmark positions to it (±0.1%).
  - It pins the League example's `EXAMPLE_GAP` to a Mid 2nd at today's values: its label, the top-level `value` and `firsts` (read at their own indent, so the nested pick's `value` can't stand in for them: release-lead's #567 delta QA P2), and `pick_equivalent.value`. A top-level 380 or 9999, or `firsts` 0.6, fails it.
  - **Main's 0.57 fails it, and so does main's 380 / 0.6 example.**
- [x] **Before/after renders**, for the operator's design review: `renders/before-after-317.png` (a deck card on a 375pt phone, 317pt of bar, the partner's handle as the "they" label; the calculator's 309pt bar draws the same) and `renders/before-after-283.png` (the League example card: `ink0`, 12pt padding, the bar under a hairline). The 317 sheet adds an Even case, the centred nub.
  - `renders/render.py` draws `TradeValueBar` from its own styles, collapsed as every mount starts: the app's tokens and fonts, the 14pt `ink3` rail with `ink.line` ticks, the fill in `semantic.pos` / `semantic.warn`, and the scale labels in chalk.faint Plex Mono in their inset frame.
  - Each case's copy and fill come from the server's own `_pick_gap_equivalent`. They're mocks, not device captures (D-056).
  - The first render (release-lead's #567 QA P2-2) was a geometry sketch: the wrong colours and fonts, bright ticks, and a "+1,840 · ≈ a Late 1st" reading the server would call a Mid 1st. Redrawn.
  - The second (delta QA R1–R4) skipped the wrap's 8pt gap before the scale row and the end row (16pt short), drew the middle scale labels level with "±1st" (they sit 3pt lower: the 12pt middle row is centred in the 18pt row), put the League bar on `ink1` with 16pt padding, and gave the deck card "They win". Fixed against release-lead's react-native-web measurements.
- [x] **The B2 guard:** `mobile/tests/check-value-bar-b2.js` (`npm run test:value-bar-b2`), 21 checks since release-lead's B2 QA. It **executes** `TradeValueBar.tsx`'s own `valueBarIsEven` on 9 cases (now including 0.7 firsts with no pick). It pins each consumer (winner label, fill colour, headline, margin line, end labels, Why?) to `even`, and `favors` to the props, the predicate and `youWin` only. It pins the deck card's VoiceOver summary to the same predicate (P2-1). Before that, it ran the component's decision lines on 8 cases: a 40-point lean with no pick reads Even; a negative lean under one first reads Even; exactly one first and 1.4 firsts with no pick lean; a lean with a pick label leans, even a small one; `favors` even or null reads Even. It also pins "mid 1sts" as `worth`'s only no-pick fallback, and the nub for Even. It fails 9 on #567's previous head `e70ad147`.
- [x] **The B2 before/after**, for the operator's design review: `renders/before-after-b2-317.png`, drawn by the same `render.py` (now with a `b2` switch; the two earlier sheets regenerate byte-identically). Three cases at 317pt: a 40-point no-pick lean (before "You win by +40 · ≈ 0.0 mid 1sts" with a sliver; after Even with the nub); a 1.8-firsts no-pick gap, unchanged; a Mid 2nd, unchanged.
- [x] **Manual TestFlight checklist** (operator, 11-06 binary). The cue for steps 1–3: each ±2nd tick sits about a third of the way from Even to the end of the bar. The old build had it past halfway.
  1. **Calculator**, a trade whose gap reads "an Early 2nd" (0.35–0.56 firsts): the fill ends clearly past the +2nd (or −2nd) tick. The old build stopped short of it.
  2. **A trade reading "a Mid 2nd":** the fill ends at about the 2nd tick.
  3. **A "They win" trade:** the fill grows left, in amber, against the −2nd tick the same way. And **a deck card's value bar** shows the ticks in the same place.
  4. **League tab, "Works right now" example card.** It shows only in a league with 0 mutual and 0 awaiting matches; switch to one first (or a fresh league). It reads "You win by +607 · a Mid 2nd (≈ 0.3 firsts)", and the fill ends on the +2nd tick.
  5. **iPhone Settings → Accessibility → Display & Text Size → Larger Text at its largest standard size**, back on the same League example (same league as step 4): the bar and its labels still render. "−2nd" and "+2nd" will crowd or overlap "Even" at this size: a **known regression of this change** (it started at 2.41 before, 1.21 now), with the label-frame fix as a design follow-up above. Note how bad it looks for design.
  6. **B2: a near-even trade with no pick label.** In the calculator, build a 1-for-1 between two low-value players whose totals are both **under about 2,400**, differ by **more than 5%** (so the old build leaned) and are **less than about 120 apart** (under half the smallest pick), e.g. about **300 vs 250**. The bar's line shows the two values, so you can check them there. Expect:
     - the bar reads **Even**, with the centred nub and "Within a rounding error — N apart (≈ 0.0 firsts)". The "(≈ 0.0 firsts)" tail is the Even line's existing wording and expected;
     - it never says "≈ 0.0 mid 1sts", and VoiceOver on a deck card like this says "Even.", never "You win.";
     - a gap of a Mid 2nd still leans, and a very lopsided trade (over 1.25 Early 1sts) still reads "≈ N mid 1sts".
  - **Web, not TestFlight** (it ships with the Render deploy): the landing page's step 03 view, "Real offers", shows the miniature's ±2nd ticks about a third of the way from Even.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route or payload change |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | no wiring change |
| `docs/cross-client-invariants.md` | updated | "Trade value-verdict shape": the ±2nd landmark, its source and the pin |
| `docs/design/components.md` | updated | TradeValueBar's "≈0.57" and the web miniature's "21.5%/78.5%" (release-lead's #567 QA P3) |
| `docs/glossary.md` / ADR / `DECISIONS.md` | n/a | no new term or decision; a stale constant corrected |

## 5. Ship gate declaration
- **CI green:** `backend-tests`, `mobile-typecheck`, `testid-lint`, `web-structure`.
- **Evidence recorded:** TEST_LEDGER.
- **TestFlight verification:** the checklist above.
- Express lane declared by the operator? No.
