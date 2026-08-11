# Status — #297 lineup-impact honest copy · #298 single-pin trade recovery

> Build agent status for feedback **#297** and **#298** (group owned by the lowest ID).
> Branch `feedback-build-trades-297-298`, based on `origin/main` @ `ab9368f`.
> Design contract: `mockups/polish-lab-2026-08-11/OPERATOR-DECISIONS.md` (#298 → **V1**;
> buttons named **Pass / Like**) + `trades-single-pin-recovery.html`.
> **Not shipped. Not merged. Not pushed. No simulator or Maestro run** — verification
> here is static only, by instruction.

## Table of Contents

- [1. What changed, at file:line](#1-what-changed-at-fileline)
- [2. The flag decision](#2-the-flag-decision)
- [3. Verification — actual output](#3-verification--actual-output)
- [4. Tests and the sabotage each detects](#4-tests-and-the-sabotage-each-detects)
- [5. Proposed edits to files I do not own](#5-proposed-edits-to-files-i-do-not-own)
- [6. QA checklist for the QA round](#6-qa-checklist-for-the-qa-round)
- [7. Out-of-scope follow-ups, named](#7-out-of-scope-follow-ups-named)
- [8. Where the decisions doc was wrong](#8-where-the-decisions-doc-was-wrong)

---

## 1. What changed, at file:line

Two files, both mine: `mobile/src/screens/TradesScreen.tsx`,
`mobile/src/components/InLeagueCalculator.tsx`. Plus one new Maestro flow.
No `backend/` file, no shared doc, none of the parallel agent's three files.

### #298 — the single-pin surface keeps the deck's actions (V1)

| # | `file:line` | Change |
|---|---|---|
| 1 | `TradesScreen.tsx:1058-1059` | New derived state. `singlePinFeatured = !firstRun && !!singlePin` is the old `!firstRun && singlePin` predicate, named once. `singlePinDeckActive = singlePinFeatured && deck.length > 0` is the new idea: **in single-pin mode, once a deck exists it takes the lead slot.** Keyed on `deck.length`, not `topCard`, so the deck keeps the slot through the swiped-out and deck-summary states instead of snapping back to the featured window mid-session. |
| 2 | `TradesScreen.tsx:4106-4120` | **Legacy (`!consolidateOn`) layout's Find-a-Trade CTA — gate removed.** Was `{!firstRun && singlePin ? null : (…)}`. Label now reads "Find more trades" when `singlePinFeatured`, per the V1 mock's "CTA relabelled for the pinned context". |
| 3 | `TradesScreen.tsx:4127` | Same layout's progress strip — gate removed (`{!(!firstRun && singlePin) && job?.status === 'running' && …}` → `{job?.status === 'running' && …}`). A generate in single-pin mode now has to narrate itself. |
| 4 | `TradesScreen.tsx:4291-4302` | **The reported CTA** — consolidated (`consolidateOn`) layout's copy of the same button, same two changes. This is the one that renders under the release flag set. |
| 5 | `TradesScreen.tsx:4304` | Same layout's progress strip — gate removed. |
| 6 | `TradesScreen.tsx:3351-3363` | `assetIdeasPanel` extracted to a single JSX const so the Upgrade/Lateral/Downgrade rail can mount at one of **two** positions without being duplicated. |
| 7 | `TradesScreen.tsx:4376-4394` | Featured block: `FeaturedTradeWindow` now also requires `!singlePinDeckActive`, and the rail renders here only when no deck is up. **This is how #241 stays fixed** — the featured window and a deck card can never be on screen together, so the "mystery second trade card" cannot come back. |
| 8 | `TradesScreen.tsx:4635` | **The load-bearing one.** Deck-wrapper gate narrowed from `{!firstRun && singlePin ? null : (…)}` to `{singlePinFeatured && !singlePinDeckActive ? null : (…)}`. The deck — and with it `SwipableTopCard onLike/onPass`, the `trades.pass-btn`/`trades.like-btn` row and the VoiceOver like/pass actions, all of which funnel into `advance()` — renders in single-pin mode again, but only once it has cards. With no cards the block still stays out, so the pinned surface never shows "Hit Find a Trade to start" underneath a featured trade it is already displaying. |
| 9 | `TradesScreen.tsx:4645-4656` | New position counter, single-pin only: `Featured trade · <n> of <m>` (`testID="trades.single-pin-deck-count"`), from the V1 mock. Uses `sortedDeck.length`, not `deck.length`, so a lane filter cannot make it lie; guarded on `topCard` so it cannot read "7 of 6" after the last swipe. `TickLabel` (`type.label`, 11px — at the floor, not under it), no new style. |
| 10 | `TradesScreen.tsx:5000-5004` | Second mount point for the same `assetIdeasPanel`, below the deck, so the actionable card leads and the alternates read as "more trades" beneath it. |

**Why V1 and not "just delete both gates" (V2).** V2 is a smaller diff but puts two trade
summaries on one screen — the featured calculator's trade is not the deck's top card, which
is a real "which one am I looking at?" hazard and is precisely what #241 removed. V1 keeps
one card in the lead slot at all times.

### #298b — picking a team no longer silently empties the deck

| # | `file:line` | Change |
|---|---|---|
| 11 | `TradesScreen.tsx:1932-1958` | The `scopedOpponent` effect's regenerate condition widened from `finderScopeSeen.current && finderMode === 'team' && scopedOpponent` to `finderScopeSeen.current && scopedOpponent`. Since #269 the opponent's *source* moved to sheet-local state and the #270 strip's "Trading with" pill scopes one **without leaving `'guided'`** — so the old condition never matched, `resetDeckForNewTargets()` ran alone, and the user was dropped to "Hit Find a Trade to start" with no explanation. The new condition is what the branch always meant. |
| 12 | `TradesScreen.tsx:1951-1954` | After the auto-regenerate, clear `prefsChangedSinceGenerateRef` and `showPrefsChangedStrip` — mirroring `handleFindTrades` (`:736-737` in `handleFindTrades`). Without this, the pick that *caused* the sweep would leave the #257 "Preferences changed — tap to refresh" nudge armed against the very sweep it triggered. |

**Blast radius of #11, checked:** legacy team mode is unchanged (there, scoping *is* the
mode, so both the old and new conditions are true). With `trades.sheet_targeting` **off**,
`scopedOpponent` can only come from team mode's route params (`:519-523`), so the new
condition is provably identical to the old one — the change is inert with that flag off.
**Clearing** an opponent still only resets and does not regenerate: broadening a search is
not a request for a new sweep, and it matches how pin add/remove already behaves
(`resetDeckForNewTargets`'s own comment: "Deliberately NOT auto-firing a job per chip change").

### #297 — the silent `null` becomes an honest row

| # | `file:line` | Change |
|---|---|---|
| 13 | `InLeagueCalculator.tsx:953-964` | The third branch of the `starter_impact` guard was a bare `null`. Now `: both ? <LineupImpactUnavailable /> : null`. Gated on `both` (`InLeagueCalculator.tsx:866`, both sides carry players) so it cannot fire on the half-built "Add a player to each side for a verdict" state. |
| 14 | `InLeagueCalculator.tsx:1011-1032` | New local `LineupImpactUnavailable`. Renders in `styles.lineupMod` — the same bordered-top block the table would have occupied — with `TickLabel` "Starting lineup" and one line of `type.bodySm` (13px). One `accessible` element with a combined `accessibilityLabel`, matching how `LineupImpactTable` voices its `note`. `testID="calc.lineup-impact-unavailable"`. |
| 15 | `InLeagueCalculator.tsx:1202` | `styles.lineupUnavailable` — `type.bodySm` + `chalk.dim`. One new style. |

**The copy, and why it is worded that way:**

> **Starting lineup**
> Lineup impact isn't available here — reading it needs a Sleeper starting-slot template
> and both teams' rosters.

`_starter_impact` (`backend/server.py:1121`) returns `None` on **two** distinct conditions:
no slot template (`:1152` — `_sleeper_lineup_slots` returns `None` for any non-numeric
league id, i.e. every ESPN/MFL/Fleaflicker/demo league, `:19058-19079`), **or** either
roster missing from `league_members` (`:1160-1161`). The mock's illustrative copy
("this league is on MFL, so FTF can't read its starting-slot template") diagnoses only the
first, and would be a false statement in the second case — on a perfectly good Sleeper
league. So the shipped copy **names the requirement rather than the cause**: true in both
cases, no platform inference, no promise of a future. Chalkline: no emoji, no gradient,
no blur, ≥11px, `chalk.faint` tick (neutral — not a new accent).

### New file

`mobile/.maestro/flows/smoke/12-trades-single-pin.yaml` — see §4.

---

## 2. The flag decision

**Decision: no new feature flag. This is a deliberate deviation from the
"default to a kill-switch flag" instruction, argued from source.** Full text in
`scope.md` §2; the three findings in brief:

1. **A client-only flag is not merely incomplete, it is harmful.**
   `useFeatureFlags.revalidateFlags` does `set({ flags })` — a whole-map **replace**. A key
   present only in `LAUNCHED_FLAG_DEFAULTS` is `true` at first paint and `false` after the
   first successful fetch. That is FB-115 inverted: a flickering feature, worse than a
   hidden one.
2. **Registering it properly needs `backend/feature_flags.py`, which I was told not to
   touch.** `_load_from_json` (`:653-659`) drops unknown keys with
   `ignoring unknown key`, so `config/features.json` alone is a no-op.
3. **A real kill switch already covers 100% of this diff.** `singlePin`
   (`TradesScreen.tsx:1038-1045`) requires `trade.asset_ideas`. Set it `false` →
   `singlePin` is `null` → `singlePinFeatured` and `singlePinDeckActive` are both false →
   every changed line falls back to the unconditional CTA + deck. Server-side,
   deploy-free, already live.

The exact five-file diff to add a dedicated flag anyway is in §5.6 below, ready to apply
if the orchestrator or operator overrules this.

---

## 3. Verification — actual output

Static only, by instruction (no simulator, no Maestro — parallel agents contending for one
sim and one harness Flask reseed each other's DBs).

```
$ cd mobile && npx tsc --noEmit > /tmp/tsc297.log 2>&1; echo "TSC_EXIT=$?"; cat /tmp/tsc297.log
TSC_EXIT=0
```
(no output — clean)

```
$ bash mobile/scripts/testid-lint.sh; echo "LINT_EXIT=$?"
testid-lint OK
LINT_EXIT=0
```

```
$ cd mobile && node tests/check-single-pin-actions.js; echo "EXIT=$?"
PASS  1 — trades.find-btn (2 mounts) is not gated out by the raw `singlePin` predicate
PASS  1 — trades.pass-btn (1 mount) is not gated out by the raw `singlePin` predicate
PASS  1 — trades.like-btn (1 mount) is not gated out by the raw `singlePin` predicate
PASS  2a — `singlePinDeckActive` is keyed on `deck.length`
PASS  2b — `singlePinDeckActive` does NOT depend on `topCard`
PASS  3 — `FeaturedTradeWindow` is gated on `singlePinDeckActive`
PASS  4 — every trades.pass-btn mount dispatches advance('pass')
PASS  4 — every trades.like-btn mount dispatches advance('like')

All single-pin-actions checks passed.
EXIT=0
```
(also `npm run test:single-pin-actions` → exit 0. Five sabotage runs, each proven to fail
— full output in §4a.)

**pytest: not run — no Python file was touched.** `git diff origin/main --stat` covers
`mobile/` only.

**Targeted greps used as structural proof:**

- `grep -n 'testID="trades.find-btn"'` → **two** hits, `:4108` and `:4293`. Confirmed
  **not** a runtime duplicate: `:4108` is inside the `{!consolidateOn ? (<>…</>)` arm
  opened at `:3680`/closed at `:4168`, `:4293` is inside the `) : (<>…</>)` arm opened at
  `:4169`/closed at `:4339-4340`. Two arms of one ternary — never mounted together.
  (Structure verified by listing every 8-space-indent structural line between `:3650` and
  `:5010`; the outer `{gateState ? (` at `:3655` is what `</>` `)}` at `:5005-5006` closes.)
- `grep -n singlePin TradesScreen.tsx` → the only remaining raw `singlePin` gates are
  `:3682` (pin-summary card) and `:3733` (pin-edit header), both legitimately
  single-pin-only UI, and `:4354` (`!singlePin` on `TradeBuildCanvas`, the `canvas`
  experiment arm — see §7).

---

## 4. Tests and the sabotage each detects

Two tests, one of which I could actually execute — including its sabotages.

### 4a. `mobile/tests/check-single-pin-actions.js` — structural, **sabotage-proven for real**

A TypeScript-AST check in the house `mobile/tests/check-*.js` style. No simulator, no
backend, no seed — so unlike the Maestro flow, **I ran it, and I ran every sabotage.**
Registered as `npm run test:single-pin-actions`.

#### Rewritten 2026-08-11 (integration round) — and deliberately made stronger, not green

**#169 (`f27c0f5`) moved `trades.pass-btn` / `trades.like-btn` out of `TradesScreen.tsx`
and into `TradeCard.tsx`** (`:538`, `:555`), wired as `onPress={disposition.onPass|onLike}`.
The behaviour is correct and complementary to #298 — the deck is ungated, so the card
renders, and the card now carries the controls. But this test asserted the two ids existed
*in `TradesScreen.tsx`*, so it went **4 PASS / 4 FAIL on a good build**.

**Repointing the ids at `TradeCard.tsx` would have been a quiet weakening.** Co-location
was never the claim. Two buttons can exist in `TradeCard.tsx`, render perfectly, and be
wired to nothing at all — and every one of the old assertions would have passed. On the
new base the claim spans two files, so the test now pins the **chain**:

```
TradesScreen  onLike={() => advance('like')}       ← host wires        (:4836)
     │        onPass={() => advance('pass')}
     ▼
SwipableTopCard  disposition={{ onPass, onLike }}  ← host threads      (:5638)
     │
     ▼
TradeCard    testID="trades.like-btn"              ← card renders      (:555)
             onPress={disposition.onLike}
```

Mounts are located by **shape**, never by component name: the `disposition` prop (which is
what `TradeCard` gates its Pass/Like row on), and "any JSX element carrying both `onLike`
and `onPass`". A rename of `SwipableTopCard` therefore cannot blind the check, and the
existence assertions scan every `.tsx` under `mobile/src` rather than one hard-coded path —
#169 already moved these controls once, and moving them is not a regression.

| Assertion | What it pins | Stronger than what it replaced because… |
|---|---|---|
| **1** | the controls exist *somewhere* under `mobile/src` | the old check hard-coded `TradesScreen.tsx` and went red on a correct refactor. This one survives relocation and still fails on deletion. |
| **2** | each button dispatches **its own** callback and not the other | **new.** The old test only checked `advance('like'\|'pass')` inside the screen. It could not see a crossed wire at the card — an X button that likes the trade. `tsc` cannot either (both are `() => void`), and a Maestro flow that taps like and asserts the deck advanced would pass. |
| **3a/3b** | the host actually **threads** `disposition` into the card, carrying both callbacks | **new.** This is the seam #169 created. Drop the prop and `TradeCard`'s `{disposition ? … : null}` renders no row at all — buttons gone, with the old test none the wiser. |
| **4a/4b** | the host maps those callbacks to `advance()`, **uncrossed** | strengthened: the old version checked only that `advance('x')` appeared in the button's own `onPress`. It had no notion of "and not the opposite", so a crossed host wire was invisible. |
| **5a/5b** | the **VoiceOver** custom actions are uncrossed | **new.** The third disposition path #298 named. Nothing else covers it — there is no VoiceOver in the Maestro harness. |
| **6a/6b/6c** | neither the deck's card mount nor `trades.find-btn` is enclosed by a raw-`singlePin` null gate | **this is the actual #298 regression**, and it is now anchored on the *card mount* rather than on buttons that no longer live in this file. Assertions 1–5 can all pass on a build where the entire surface is unreachable the moment a pin is set; only 6 sees that. |
| **7a/7b** | `singlePinDeckActive` keyed on `deck.length`, never `topCard` | unchanged — still the subtle one (see sabotage C). |
| **8** | `FeaturedTradeWindow` still yields to the deck | unchanged — #241's no-two-cards invariant. |

Clean tree, current base:

```
$ node tests/check-single-pin-actions.js
PASS  1 — trades.pass-btn exists somewhere under mobile/src
PASS  2 — every trades.pass-btn mount (1) dispatches `onPass` and not `onLike` [src/components/TradeCard.tsx:538]
PASS  1 — trades.like-btn exists somewhere under mobile/src
PASS  2 — every trades.like-btn mount (1) dispatches `onLike` and not `onPass` [src/components/TradeCard.tsx:555]
PASS  3a — the host threads a `disposition` prop into a trade card
PASS  3b — the `disposition` prop at src/screens/TradesScreen.tsx:5638 carries both callbacks
PASS  4a — the host mounts a card supplying both `onLike` and `onPass`
PASS  4b — src/screens/TradesScreen.tsx:4836 `onLike` dispatches advance('like'), not advance('pass')
PASS  4b — src/screens/TradesScreen.tsx:4836 `onPass` dispatches advance('pass'), not advance('like')
PASS  5a — the host handles VoiceOver like/pass actions
PASS  5b — VoiceOver 'like'→onLike and 'pass'→onPass, uncrossed (src/screens/TradesScreen.tsx:5633)
PASS  6a — the deck's card mount at src/screens/TradesScreen.tsx:4836 is not gated out by the raw `singlePin` predicate
PASS  6b — trades.find-btn exists in the host
PASS  6c — trades.find-btn (2 mounts) is not gated out by the raw `singlePin` predicate
PASS  7a — `singlePinDeckActive` is keyed on `deck.length`
PASS  7b — `singlePinDeckActive` does NOT depend on `topCard`
PASS  8 — `FeaturedTradeWindow` is gated on `singlePinDeckActive`

All single-pin-actions checks passed.
EXIT=0
```

#### Sabotage suite — nine, all re-run on the new base

Applied one at a time to a clean tree, each reverted with `git checkout --` before the
next. **Actual output**, abridged to the FAIL lines:

| # | Sabotage | Edit | Result |
|---|---|---|---|
| **A** | the literal v1.12.0 deck defect | `:4758` gate → `{!firstRun && singlePin ? null : (…)}` | `exit=1` · `FAIL 6a — the deck's card mount at …:4836 …: gated at …:4758: !firstRun && singlePin ? … : …` |
| **B** | the literal v1.12.0 CTA defect, **consolidated arm only** | wrap the consolidated `<Button testID="trades.find-btn">` in the same gate | `exit=1` · `FAIL 6c — trades.find-btn (2 mounts) …: …:4415 gated at …:4414` |
| **C** | the subtle one | `singlePinDeckActive = singlePinFeatured && !!topCard` | `exit=1` · `FAIL 7a …: saw: singlePinFeatured && !!topCard` · `FAIL 7b — … does NOT depend on topCard` |
| **D** | #241 comes back | drop `&& !singlePinDeckActive` from the `FeaturedTradeWindow` gate | `exit=1` · `FAIL 8 — FeaturedTradeWindow is gated on singlePinDeckActive` |
| **E** | a control disappears | `testID="trades.like-btn"` → `"trades.like-btn-GONE"` | `exit=1` · `FAIL 1 — trades.like-btn exists somewhere under mobile/src: no element carries this testID in any .tsx — the control is gone` |
| **F** ★new seam | **card-side crossing** | `TradeCard.tsx` pass button → `onPress={disposition.onLike}` | `exit=1` · `FAIL 2 — every trades.pass-btn mount (1) …: …:538: onPress={disposition.onLike} — references `onLike`, the OTHER decision` |
| **G** ★new seam | **host-side crossing** | `onLike={() => advance('pass')}` | `exit=1` · `FAIL 4b — …:4836 `onLike` dispatches advance('like'), not advance('pass'): saw: onLike={() => advance('pass')}` |
| **H** ★new seam | **prop dropped** — the card's buttons wired to nothing | delete the `disposition={{ onPass, onLike, … }}` line | `exit=1` · `FAIL 3a — the host threads a `disposition` prop into a trade card: no JSX element in src/screens/TradesScreen.tsx passes `disposition=` — the card renders no Pass/Like row at all` |
| **I** ★new seam | **VoiceOver crossed** | swap `onLike()`/`onPass()` in `onAccessibilityAction` | `exit=1` · `FAIL 5b — VoiceOver 'like'→onLike and 'pass'→onPass, uncrossed (…:5633)` |
| — | **control** | clean tree | `exit=0`, no FAIL lines |

**H is the sabotage that justifies the rewrite.** It is the exact failure mode a
"repoint the ids at `TradeCard.tsx`" repair would have shipped blind: both buttons present,
both correctly wired to `disposition.onPass` / `disposition.onLike`, assertions 1 and 2
green — and no `disposition` prop reaching them, so the row never renders. A test that
passes when the card's buttons are wired to nothing is worse than no test.

**Historical note, kept because it is the reason this section exists.** The first version
of this file used `elementWithTestId(id)[0]` — the *first* element per testID. Sabotage B
reintroduced the reported defect on the consolidated layout's CTA and the test **came back
green**, because it was still looking at the legacy arm's copy. Same failure mode as the
prior batch's three tests that passed on the defect they were meant to catch. Reasoning
about a sabotage is not running one.

### 4b. `mobile/.maestro/flows/smoke/12-trades-single-pin.yaml` — behavioural, **NOT executed**

**Honest caveat: I did not run this flow, and I did not run it against a sabotaged
build.** Running Maestro was explicitly forbidden for this agent (parallel agents
contending for one simulator and one harness Flask reseed each other's DBs). What follows
is the sabotage each assertion detects *by construction*. **The QA round must actually
execute the sabotage column before this flow is trusted** (§6 step 7) — 4a above is the
proof that "reasoned about" and "verified" are not the same thing.

| Assertion (flow step) | Sabotage it detects | Why it fails, by construction |
|---|---|---|
| `assertVisible: trades.find-btn` after the pin | Restore the gate at `TradesScreen.tsx:4291` (or `:4106`) | With exactly one pin, `singlePin` is non-null and `firstRun` is false (`onboarding.trades_first: false` in the release fixture), so the gate evaluates `null` and no element carries that testID. **This is the literal v1.12.0 defect.** |
| `extendedWaitUntil: trades.card-top` | Restore the deck-wrapper gate at `:4635` | `SwipableTopCard` (which owns `testID="trades.card-top"`) lives inside that wrapper. Gate restored ⇒ the wrapper is `null` ⇒ generated cards render nowhere. This is the other v1.12.0 defect, the one that took accept/decline with it. |
| `assertVisible: trades.single-pin-deck-count` | Delete `:4645-4656`, **or** apply sabotage C | Direct assertion on the new element. Under C the counter and the whole deck slot vanish the moment the deck is exhausted — which this flow, tapping like once, would still miss. **4a covers C; this flow does not.** |
| `assertVisible: trades.pass-btn` **and** `trades.like-btn` | Restore `:4635`, or delete the disposition row | Both ids exist only inside the deck wrapper. Asserting **both** (not just the one tapped) is deliberate: a fix restoring only the accept path would satisfy a like-only test while still failing the reporter's sentence, which names both. |
| `tapOn: trades.like-btn` → `extendedWaitUntil: trades.find-btn` | Sabotage E — buttons that render but do not dispatch | `advance()` dispositions the card, fires `swipe`, and fronts the next one. A cosmetic button leaves the deck frozen; the CTA assertion afterwards is the liveness check that the screen survived the tap. |
| Reaching the board (`trades.board.add-away`) | — | Not an assertion about the fix; it is the flow's precondition. If it fails, the flow is wrong, not the code. Fallback in §6. |

### What neither test covers — stated so the QA round knows the gaps

- **The swipe gesture.** Both the button path and the gesture share `advance()`, and 4a
  pins the button wiring, but no test drives the actual pan gesture on `SwipableTopCard`.
- **The VoiceOver custom actions** (`SwipableTopCard`'s `accessibilityActions`,
  `:5509-5516`) — no VoiceOver in the harness. Manual, §6 step 8.
- **#298b entirely.** The team-pill regenerate needs the strip variant and a second
  opponent; it is a manual check, §6 step 5.
- **#297's row entirely.** It needs a league whose id is non-numeric, which the `standard`
  fixture does not have. Manual, §6 step 6. There is no structural test for it either —
  the invariant ("never render a bare `null` here") is a judgement about copy, not a shape
  an AST check can pin without becoming a change-detector.

## 5. Proposed edits to files I do not own

**I did not apply any of these.** Orchestrator-owned; text is final and ready to paste.

### 5.1 `docs/cross-client-invariants.md` — settle the Pass / Like naming

> ### Trade disposition control names
>
> The two deck controls are named **Pass** and **Like** (operator decision, 2026-08-11,
> taken on the #169 thread and reaffirmed for #298 — it is the same control). Not
> "Accept/Decline", not "Send offer". Every client uses this vocabulary in copy, in
> accessibility labels and in analytics:
>
> | Concept | testID | a11y label | Glyph / colour |
> |---|---|---|---|
> | Pass | `trades.pass-btn` | "Pass on this trade" | `x`, `semantic.neg` |
> | Like | `trades.like-btn` | "Accept this trade" | `check`, `semantic.pos` |
> | Third option | — | "Queue this trade" | `plus` / `check` when queued |
>
> Swipe right = Like, swipe left = Pass; the hint string is
> "Swipe right to like · Swipe left to pass". The VoiceOver custom actions on the top card
> mirror the two buttons exactly and share their `advance()` handler — a change to one is a
> change to all three, and any surface that shows a trade card must carry all three or none.
>
> **Note the a11y-label asymmetry is intentional and pre-existing:** the Like button's
> label is "Accept this trade" while its visible name is "Like". Do not "fix" one without
> the other — `docs/design/components.md` and the Maestro flows both depend on the
> current strings.

### 5.2 `docs/glossary.md` — define single-pin mode

> **Single-pin mode** — the state of TradesHome when exactly **one** asset is pinned in the
> finder-target board, in either direction (`TradesScreen.tsx:1038-1045`; requires
> `trade.finder_targeting` **and** `trade.asset_ideas`). It replaces the ordinary "generate
> and swipe" landing with an asset-centric surface: a featured trade for the pinned player
> plus an Upgrade / Lateral / Downgrade alternates rail. Zero pins or two-or-more pins are
> **not** single-pin mode and behave exactly as the classic deck does. Since #298 the
> pinned surface also keeps the deck's own controls — the Find-a-Trade CTA, the Pass/Like
> row and the swipe — and the deck card takes the lead slot from the featured window as
> soon as one is generated.

### 5.3 `living-memory/DECISIONS.md` — two entries (renumber to `max+1` at apply time)

> ## D-0NN — #298 single-pin recovery: the deck takes the lead slot, it does not stack
>
> **Date:** 2026-08-11 · **Context:** feedback #298, variant V1 (operator-decided).
>
> Pinning one asset removed the Find-a-Trade CTA and the entire deck wrapper, and with it
> every accept/decline path. The obvious fix — delete both `singlePin` null-gates — was
> rejected (that is variant V2): it puts the featured window's calculator trade and the
> deck's top card on screen together, which is exactly the confusion #241 removed.
>
> **Decision:** in single-pin mode the deck renders **only once it has cards**
> (`singlePinDeckActive`), and `FeaturedTradeWindow` hides while it does. One trade card in
> the lead slot at all times: featured window before a generate, deck card after. The
> alternates rail follows whichever is leading. #241's invariant — never two trade cards on
> the pinned surface — is preserved, not reverted.
>
> **Consequence:** `deck.length`, not `topCard`, is the switch, so the surface does not snap
> back to the featured window when the deck is swiped out mid-session.
>
> ## D-0NN+1 — #298 ships without a new feature flag
>
> **Date:** 2026-08-11 · **Context:** the default for a behaviour change on a live surface
> is a kill-switch flag. This one is a documented exception.
>
> **Decision:** no new flag. (1) `useFeatureFlags.revalidateFlags` **replaces** the flag map
> rather than merging it, so a key living only in `LAUNCHED_FLAG_DEFAULTS` is `true` at first
> paint and `false` a second later — a flickering feature, worse than FB-115's hidden one.
> (2) Registering it properly requires `backend/feature_flags.py`, which the build agent was
> scoped out of; `config/features.json` alone is a no-op because `_load_from_json` drops
> unknown keys. (3) `trade.asset_ideas` is already a real, server-side, deploy-free kill
> switch for 100% of this diff: with it off, `singlePin` is `null` and every changed line
> falls back to the unconditional CTA + deck.
>
> **Rollback lever:** `trade.asset_ideas → false`.
>
> **Generalisable lesson:** "add a kill-switch flag" is not free in this codebase. It is a
> five-file change spanning `backend/`, and a half-registered flag is a live footgun because
> of the map-replace semantics above. Check both before promising one.

### 5.4 `living-memory/CHANGELOG.md` + `TEST_LEDGER.md` (at ship, not before)

> **CHANGELOG:**
> ### 2026-08-11 — #297/#298: single-pin trade surface keeps its actions; honest lineup copy
> - **#298** — pinning one asset no longer removes the Find-a-Trade CTA or the deck. The
>   deck card takes the featured window's slot once generated, restoring swipe, Pass/Like
>   and the VoiceOver actions on the existing `advance()` path (variant V1). The
>   `trades_home_inline` experiment was **not** the cause and was not touched — the defect
>   reproduced in the control group.
> - **#298b** — picking a team from the "Trading with" strip pill emptied the deck and
>   regenerated nothing (the regenerate condition still tested `finderMode === 'team'`
>   after #269 moved the opponent's source to sheet-local state). Now regenerates whenever
>   an opponent is scoped.
> - **#297** — was **not** a regression: the lineup table has never been mounted on a deck
>   or featured card, and `git log -S` shows only additive commits. The real defect was a
>   silent `null` when the server omits `starter_impact`; it now renders an honest row
>   naming the requirement (Sleeper slot template + both rosters).
> - No new flag — see DECISIONS. Rollback lever: `trade.asset_ideas → false`.
>
> **TEST_LEDGER:** `tsc --noEmit` clean, `testid-lint.sh` OK on the build branch (static
> only, agent ran no simulator). Tier-2 sim gate owed at ship:
> `12-trades-single-pin.yaml` + `05-trades-render.yaml` + `06-trades-deck.yaml`, with the
> §4 sabotage column executed before the new flow is trusted.

### 5.5 `.github/workflows/ci.yml` — make the structural tests actually gate

**Pre-existing gap, not caused by this change, but it now has a victim.** CI runs pytest,
`npx tsc --noEmit` and `mobile/scripts/testid-lint.sh` — and **none** of the eight
`mobile/tests/check-*.js` invariant tests. They are all `npm run`-only, so every one of
them (including `check-picks-subset-invariance.js`, written for exactly this reason) is a
test nothing executes unless a human remembers. I did not edit `ci.yml`: it is a shared
file three agents could touch this batch. Proposed addition to the mobile job, after the
`testid-lint.sh` step:

```yaml
      - name: mobile invariant checks
        working-directory: mobile
        run: |
          for t in tests/check-*.js; do
            echo "── $t"
            node "$t" || exit 1
          done
```

A loop rather than eight named steps so the next `check-*.js` is wired up by existing.

### 5.6 If a dedicated flag is wanted after all — the exact five touches

Name: `trades.single_pin_deck_actions`. Default **true** (a kill switch, not a dark launch
— default-false would ship the bug).

1. `backend/feature_flags.py` — add `"trades.single_pin_deck_actions",` to `FLAG_KEYS` and
   `"trades.single_pin_deck_actions": True,` to `DEFAULT_FLAGS`.
2. `config/features.json` — `"trades.single_pin_deck_actions": true,` + a `_comment_` key
   in the house style.
3. `backend/tests/fixtures/flags/release.json` — same pair.
4. `docs/config-reference.md` — one row.
5. `mobile/src/state/useFeatureFlags.ts` — add to `LAUNCHED_FLAG_DEFAULTS`
   (**required**, not optional: without it the feature is off on first-ever boot until the
   first successful fetch).

Then in `TradesScreen.tsx`, one line — `:1058` becomes:

```ts
const singlePinDeckOn = useFlag('trades.single_pin_deck_actions');
const singlePinFeatured = !firstRun && !!singlePin;
const singlePinDeckActive = singlePinDeckOn && singlePinFeatured && deck.length > 0;
```

…and the two CTA gates (`:4106`, `:4291`) and the deck gate (`:4635`) each regain a
`singlePinDeckOn ? … : <old expression>` wrapper. Note this is genuinely five files and a
three-branch client change — which is the point made in D-0NN+1.

---

## 6. QA checklist for the QA round

Run on the `standard` profile with the `release` flag fixture unless noted.
**Nothing below has been executed by me.**

1. **Static re-check on the merged branch** — `npx tsc --noEmit` (expect exit 0),
   `mobile/scripts/testid-lint.sh` (expect `testid-lint OK`), and
   `npm run test:single-pin-actions` (expect 8 PASS, exit 0). All three were clean in
   isolation; re-run after the parallel agent's work merges. **Note the third does not run
   in CI today** — see the proposed `ci.yml` wiring in §5.5.
2. **New flow** — `maestro test .maestro/flows/smoke/12-trades-single-pin.yaml`.
   Law 23: **eyeball `smoke-12-trades-single-pin.png`**, do not trust the green. The frame
   must show one trade card with the `Featured trade · n of m` label above it and the
   Pass/Like row below — **not** a featured-window calculator, and **not** two cards.
3. **Smoke regression** — `05-trades-render.yaml` and `06-trades-deck.yaml`. Both run with
   zero pins, where every branch added here is inert; a failure means the change leaked out
   of single-pin mode.
4. **Manual, #298 main path (the reporter's own journey):** Trades → generate a deck → on a
   card tap **"Keep · more offers"** for a one-player side → confirm the pinned surface now
   shows the CTA and, after the auto-generate that `handleKeepSide` already fires
   (`:2005-2006`), a deck card with Pass/Like. **Note this path already generated cards
   before the fix — they simply had nowhere to render.** Then tap the pin row's clear/back
   and confirm the original deck is restored unchanged (`handleClearPin`, `:2017`).
5. **Manual, #298b:** with the `strip` variant of `trades_home_inline`, tap the "Trading
   with" pill → pick a league-mate. **Expect a sweep to start on its own** (progress strip
   appears, deck refills). Pre-fix this silently emptied the deck to "Hit Find a Trade to
   start". Then tap the same manager again to clear: expect the deck to reset and **no**
   auto-sweep, and confirm no spurious "Preferences changed" strip after either action.
6. **Manual, #297 — needs a non-Sleeper league, which `standard` does not have.** Options,
   cheapest first: (a) the operator's own MFL or ESPN league on a dev build; (b) a seeded
   league with a non-numeric `league_id` (that alone is sufficient —
   `_sleeper_lineup_slots` returns `None` on `not str(league_id).isdigit()`,
   `server.py:19068`). Open the in-league calculator, build a two-sided trade, and confirm
   the **Starting lineup** row appears with the explanatory sentence instead of nothing.
   Then confirm the **negative**: on a Sleeper league the real `LineupImpactTable` still
   renders and the new row does **not**. Also confirm the row is absent while only one side
   has players.
7. **Sabotage verification (§4) — do this before trusting the new flow.** Restore the gate
   at `TradesScreen.tsx:4635` to `{!firstRun && singlePin ? null : (…)}`, re-run
   `12-trades-single-pin.yaml`, and confirm it **fails** at `trades.card-top`. Revert. Repeat
   for `:4291` and confirm failure at `trades.find-btn`.
8. **Accessibility** — VoiceOver on the pinned deck card: the like/pass custom actions must
   be present (they ride inside the restored wrapper). And on the calculator: the new
   unavailable row must read as **one** sentence, not two nodes.
9. **Capture** — `mobile/scripts/screen-capture.sh --screen trades --state single-pin`.
   There is currently **no** single-pin capture in `screens/manifest.json`, so every
   "current" frame for these two items is a reconstruction rather than a traced screenshot.

---

## 7. Out-of-scope follow-ups, named

Real work, deliberately not built here.

1. **Compute `starter_impact` for MFL / ESPN / Fleaflicker.** `_sleeper_lineup_slots`
   (`server.py:19058`) is Sleeper-only by construction. Each platform would need its own
   slot-template reader. Backend, and the honest row above is the correct interim answer.
2. **Mount the lineup table on deck and featured trade cards.** The genuine phase-2 item
   #238 deferred, and what #297's reporter may actually want. Needs, in order: batched
   `_starter_impact` across the deck sweep (it currently runs `optimal_starters` twice per
   trade and the sweep generates many candidates per opponent — hoist
   `_sleeper_lineup_slots` and the roster fetch out of the loop, memoize the caller's
   "before" lineup once per sweep since it is constant); serialization in
   `trade_card_to_dict` (`:9352`) so it survives into `_public_job`; a mirror in
   `/api/trades/asset-ideas`; a new flag (e.g. `trade.deck_lineup_impact`); lifting
   `LineupImpactTable` out of `InLeagueCalculator.tsx` into its own component file (it is
   unexported and closes over module-local `styles`, `slotShortLabel`, `posRankLabel`,
   `SLOT_SHORT`); and `starter_impact` on the `TradeCard` type in
   `mobile/src/shared/types.ts`. **Schema + API contract + flag ⇒ by the CLAUDE.md bright
   line this is not a quick fix and cannot go express without an explicit confirming yes.**
   #169's approved lab also argues for a one-line tier framing ("TE: 4th → 1 1st") on card
   real estate rather than the full table.
3. **`TradeBuildCanvas` in single-pin deck mode.** `:4354` still excludes the canvas
   variant when `singlePin` is set, on the reasoning that the pinned surface "already IS a
   build-canvas-like surface". With V1 that is no longer strictly true once a deck card
   leads. Not touched: it is a different experiment arm and changing it needs its own
   decision.
4. **Feedback payload should record the active league and its platform.** #297 cost a
   database query to answer a question the report could have carried. The FAB records
   `platform: ios` — the *device*. Candidate for the FAB's captured context, and it would
   have made this item a five-second triage.
5. **Screen-library capture gaps** — no single-pin capture for `trades`, no drill-in
   capture for `league-summary`. Every `trades` capture also used the `release` fixture,
   i.e. the experiment's **control** variant.

---

## 8. Where the decisions doc was wrong

Recorded because the orchestrator asked, and because two of these changed what I built.

1. **`OPERATOR-DECISIONS.md` §2 says #297 is blocked and "must not be built from this
   lab"**, on the finding that all four of the operator's leagues carry numeric Sleeper
   ids. My build instruction says the opposite — that the operator has **MFL and ESPN**
   leagues linked, which is what makes the silent-`null` path their case. **I built to the
   instruction** (the narrow honest-copy fix), which is also what the lab's own
   Recommendation table advises ("Ship the honest row first… if it is non-Sleeper, that row
   *is* the fix"). Worth reconciling before ship: if the operator's leagues really are all
   numeric-Sleeper, the row is still correct and still cheap, but #297's *root cause* is
   then unexplained and the runtime repro the lab asked for is still owed.
2. **The mock's #297 copy diagnoses a cause the client cannot know.** "this league is on
   MFL, so FTF can't read its starting-slot template" is false whenever the field is absent
   for the *other* reason — a roster missing from `league_members` on a Sleeper league
   (`server.py:1160-1161`). Shipped copy names the requirement instead. Flagging because it
   is a deliberate deviation from the mock's literal words, not an oversight.
3. **The "one-line fix" estimate for #298b was low.** Widening the condition alone leaves
   the #257 "Preferences changed" nudge armed against the sweep its own trigger started —
   `handleFindTrades` clears that state (`:736-737` in `handleFindTrades`) and the auto-regenerate path bypasses
   it. Two lines, not one.
4. **The mock's V1 frame keeps the utility row (Draft / Free agents / Calculator) "below
   the fold" and shows the strip above the pin row.** I did not move either: reordering
   the pinned layout is a separate change from restoring its controls, and every element
   between them belongs to other flagged surfaces. The V1 frame's *actions* are all
   present; its *vertical ordering* of unrelated chrome is not reproduced. Calling it out
   rather than letting QA discover it.
5. **A correction to a mid-flight orchestrator note, for the record:** the two
   `testID="trades.find-btn"` occurrences (`:4108`, `:4293`) are **not** a runtime
   duplicate — they are the two arms of the `!consolidateOn` ternary and can never mount
   together. Deleting either would have removed the CTA from one whole layout. What *was*
   genuinely wrong is that I had only ungated the consolidated arm; the legacy arm still
   carried the #241 gate, so #298 was half-fixed. Both arms are now ungated.
