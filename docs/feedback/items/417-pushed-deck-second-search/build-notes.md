# FB-417 — build notes

**Branch:** `feat/fb417-pushed-deck-research` (off `c529abc8`) · **Date:** 2026-09-03
Requirements: [prd.md](prd.md) R-1…R-5. Gate block: [scope.md](scope.md).

## 1. What changed

### `mobile/src/screens/TradesScreen.tsx` (the only source file)

| Post-change line(s) | Change | Requirement |
|---|---|---|
| :776 | New state `const [fairSweepPending, setFairSweepPending] = useState(false);` — the jobless fair sweep's in-flight marker (neither `generateMutation.isPending` nor `job?.status` is true while it runs) | R-3 |
| :1130 | `handleFindTrades`: `if (fairDeck) resetDeckForNewTargets();` — inserted **before** `setFairDeck(false)` (:1131) and `dispatchGenerate({})` (:1134), so the reset's epoch bump precedes the dispatch it stamps | R-2 |
| :2906 | `resetDeckForNewTargets`: `setFairSweepPending(false);` — a reset supersedes any sweep in flight, and that sweep (epoch-guarded) will not disarm the flag itself | R-3 |
| :3552 | `runFairPackages`: `setFairSweepPending(true);` at entry, beside `const epoch = deckEpochRef.current;` | R-3 |
| :3584 | …disarmed on the success exit, after the `#330` epoch guard (:3572), beside `setFairDeck(true)` | R-3 |
| :3594 | …disarmed on the failure exit, after the same guard (:3586), beside `setFairDeck(false)` | R-3 |
| :5820 | New derivation `const findCtaHiddenForAnchoredDeck = isResultsPushed && fairDeck;`, next to `inlineAnchorShown` (:5807) — one predicate read by both CTA arms so they cannot drift | R-1 |
| :7229 | Legacy `!consolidateOn` arm gate: `canvasHost !== 'flag' && !findCtaHiddenForAnchoredDeck` | R-1 |
| :7238-7243 | …its `disabled` gains `\|\| fairSweepPending` | R-3 |
| :7251 | …its `onPress` becomes `() => handleFindTrades()` (was `track(…) + setPinIdeaResumed(false) + dispatchGenerate({})`) | R-2, R-4 |
| :7443 | Consolidated arm gate: same conjunct | R-1 |
| :7452-7457 | …its `disabled` gains `\|\| fairSweepPending` | R-3 |
| :7667 | `TradeBuildCanvas` mount: `onFindATrade={canvasHost === 'flag' && !fairSweepPending ? handleInlineFindATrade : undefined}` — `InLeagueCalculator:1297` renders that cell `disabled={!onFindATrade}`, so withholding the handler IS its disabled state (no prop added, `InLeagueCalculator.tsx` untouched) | R-3 |

Not changed: any copy string, style token, `testID`, flag, route, event name or payload shape.
`resetDeckForNewTargets` still does not touch the pin store — pins are the user's targets and
the next dispatch reads them out of it (assertion 8f pins this explicitly).

### `mobile/tests/check-results-push.js`

New **§ 8** (18 assertions, `8` and `8a`–`8q`) — see the sabotage table below. One re-spec
inside the existing § 4 (`4f`, dispatch census).

## 2. Declared re-specs (existing pins that encoded the old behavior)

All four are consequences of routing the legacy CTA arm through `handleFindTrades`, plus two
window widths. Each is annotated in place with a dated `#417` note.

| File | Pin | Was → is | Why it is not a weakening |
|---|---|---|---|
| `check-canvas-results.js` | `12a` dispatch census | `dispatchGenerate(` count `9` → `8` (7 routed + definition) | The legacy arm no longer dispatches for itself; it calls `handleFindTrades`, already one of the routed sites. A **new** site still breaks the count |
| `check-results-push.js` | `4f` same census | `9` → `8` | Same; the raw `generateMutation.mutate(` count stays pinned at 1 |
| `check-offer-prefill-330.js` | `S-2` same census | `9` → `8` | Same |
| `check-inline-home.js` | `7f` same census | `9` → `8` | Same |
| `check-analytics-297-302.js` | `#298` emitter census | `find_trades_tapped` call sites `4` → `3` | The legacy arm's inline emitter is gone; its row is now `handleFindTrades`'s no-`source` branch — same name, same `{mode: deckMode}` shape (pinned by the assertion directly above it). A new emitter still breaks the count |
| `check-analytics-297-302.js` | `#298 the legacy-layout CTA sends mode too` | Rewritten to pin the arm's `onPress={() => handleFindTrades()}` **and** the absence of `dispatchGenerate(` in it | The intent — "the legacy CTA's tap still produces a `{mode}` row" — is preserved and strengthened: routing through the entry point is also what gives that arm the #417 reset |
| `check-inline-home.js` | `11b` T-2 CTA gate regex | Accepts an optional `&& !findCtaHiddenForAnchoredDeck` conjunct | `canvasHost !== 'flag'` is still required and still the FIRST conjunct, which is all T-2 was about; `check-results-push.js` § 8a owns the new one |
| `check-inline-home.js` | `3c` `onFindATrade` wiring | Regex updated for the `&& !fairSweepPending` conjunct | The host gate is unchanged and still first |
| `check-inline-home.js` | `3` / `11d` mount slice widths | `900` → `1800`, `1100` → `2000` chars | Mechanical: the mount's prop list grew a comment block and `onLikeTrade` / `hideFormatChips` fell outside the old windows. The assertions themselves are byte-identical |

## 3. Sabotage table — every new assertion proven red, then restored (build round)

Harness: apply the sabotage to the working tree, run `node tests/check-results-push.js`, record
which `8*` ids fail, restore the file, re-run and confirm zero failures. Every sabotage restored
green and both mutated files were byte-compared to their originals at the end.

| # | Sabotage | Assertions that went red | Restored green |
|---|---|---|---|
| S1 | per-arm predicates: delete the shared derivation and inline it in both gates | 8, 8a | yes |
| S2 | pre-#417 gate on the consolidated arm (CTA renders on the anchored deck) | 8a | yes |
| S3 | delete the legacy arm's mount instead of gating it | 8b | yes |
| S4 | the receipt's Clear (the anchored deck's search control) is removed | 8c | yes |
| S5 | pre-#417 `handleFindTrades`: no reset on a fair deck | 8d, 8e | yes |
| S6 | the reset runs AFTER the dispatch (epoch kills the search it started) | 8e | yes |
| S7 | the reset also clears the pin store (drops the user's targets) | 8f | yes |
| S8 | `handleSearchAllTrades` dispatches privately instead of through `handleFindTrades` | 8g | yes |
| S9 | the legacy arm goes back to its own `track` + `dispatchGenerate` | 8h, 8i | yes |
| S10 | the sweep never arms the in-flight flag | 8j, 8m | yes |
| S11 | the success exit never disarms (controls stay dead after a good sweep) | 8k, 8m | yes |
| S12 | the failure exit never disarms (a failed sweep bricks the CTA) | 8l, 8m | yes |
| S13 | a third disarm placed AHEAD of the `#330` epoch guard (a dead sweep re-enables a live one's controls) | 8m | yes |
| S14 | a deck reset no longer disarms the flag (a superseded sweep strands a disabled control) | 8n | yes |
| S15 | pre-#417 `disabled` on the consolidated arm (no jobless-sweep guard) | 8o | yes |
| S16 | pre-#417 landing canvas wiring (cell stays live during the sweep) | 8p | yes |
| S17 | #417 grows a feature flag of its own | 8q | yes |

Every id in `{8, 8a…8q}` appears in at least one red column, so no assertion is asleep.
Two assertions were rewritten during authoring after self-review found them tautological
(a `/^[\s\S]*$/` conjunct and an `|| true` tail) — both were replaced with real predicates
(8f now asserts `resetDeckForNewTargets` references no `useFinderTargets`; 8q asserts the
absence of an #417 key in `config/features.json`) and are proven red by S7 and S17.

## 4. Command results (all from the worktree)

| Command | Result |
|---|---|
| `cd mobile && npx tsc --noEmit` | clean, exit 0 |
| `cd mobile && npm run test:results-push` | **70 assertions, all passed** — 23 of them printed by the new § 8 (18 distinct ids; `8c` prints one line per replacement control) |
| all 89 `mobile/tests/check-*.js` suites | **0 red** — including the 32 that mention `TradesScreen`: `check-analytics-297-302` (37 PASS), `check-canvas-results` (151 ✓), `check-inline-home` (71 ✓), `check-offer-prefill-330` (48 PASS), `check-calc-merged-behavior`, `check-single-pin-actions`, `check-shop-deck` (untouched), … |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK` |

`backend/tests` not run — no backend file was touched; CI covers it on push.

## 5. QA round 1 resolution — 2026-09-03

Both QA verdicts were **PASS**; this section is the resolution of the non-blocking findings
they raised (qa-B B-1/B-2/B-3/B-5, qa-A F-1/F-2/F-3). No requirement was reopened; R-6 is new.
Line numbers below are post-resolution.

### 5.1 Source changes (`mobile/src/screens/TradesScreen.tsx`)

| Line(s) | Change | Finding | Requirement |
|---|---|---|---|
| :768-780 | `fairSweepPending`'s declaration comment now claims what is true: cleared by **every** epoch bump, and it names the two bump sites | qa-B B-2 | R-3 |
| :4596-4603 | The QuickSet-regen focus effect's inline `deckEpochRef.current += 1` gains `setFairSweepPending(false)` beside it. That site bypasses `resetDeckForNewTargets` on purpose (it must not clear pins/lane state) and had bypassed the disarm with it: a sweep superseded by it returns at its epoch guard without disarming, so both CTA arms stayed disabled for the life of the page | qa-B B-2 | R-3 |
| :5836-5844 | `findCtaHiddenForAnchoredDeck = isResultsPushed && (fairDeck \|\| fairSweepPending)` — the gate now covers the whole anchored lifecycle, not just the part after the cards land | qa-B B-5 | R-1 |
| :8533-8535 | The deck tree's in-progress branch gains `\|\| (isResultsPushed && fairSweepPending)`, so the pushed page shows "Looking for trades…" for the second the jobless sweep takes instead of falling through to `Hit "Find a Trade" to start` | qa-B B-5/B-1(b) | R-1 |
| :8580-8598 | The deck-done card's body gains a third copy branch keyed on `findCtaHiddenForAnchoredDeck`: with the receipt up it names the receipt's **Clear** (which IS `handleSearchAllTrades`), without one (a push whose `anchorLabel` is null) it names this card's own **Search all trades**. The two pre-existing sentences are byte-identical | qa-B B-1(a), qa-A F-6 | R-1 |
| :8763-8784 | The deck-failure card's "Try again" forks on `isResultsPushed && inlineAnchor` to `runFairPackages(inlineAnchor)`; every other host keeps `handleFindTrades('deck_error_retry')` verbatim | qa-B B-3 | **R-6** |
| :1689-1695 | `deckMode`'s comment: the emitter census is 3, not "two below (… the legacy arm's inline track)" — that emitter was deleted by this change | qa-A F-3 | R-4 |
| :1995-2006 | The `dispatchGenerate` DISPATCH CENSUS: the dead "8. legacy !consolidateOn CTA" row is gone and the header states SEVEN routed sites (8 `dispatchGenerate(` occurrences with the definition), re-keyed and dated | qa-A F-3 | R-2 |

`mobile/tests/check-offer-prefill-330.js:190` — the prose "check-canvas-results §12 owns the
8-site census" now reads "the dispatch-site census" (the number lives in the assertion below it,
which was already re-keyed). Comment-only.

**qa-A F-2** needed no source change: `setFairSweepPending(true)` was already **below**
`if (!leagueId) return;`. The gap was in the guard — 8j's regex could not tell the two orders
apart — and is closed by the re-anchor in 5.2.

### 5.2 Guard changes (`mobile/tests/check-results-push.js` § 8)

Two assertions changed, five added; every one proven red by a named sabotage and restored.
Harness identical to §3 (apply, `node tests/check-results-push.js`, record the red ids, restore
from a byte-compared backup). After the last restore the file is byte-identical to its pre-
sabotage state and § 8 prints **28 lines / 23 distinct ids** (`8`, `8a`–`8v`; `8c` × 6).

| # | Sabotage | Assertion | Red | Restored |
|---|---|---|---|---|
| S18 | derivation back to `isResultsPushed && fairDeck` (drops the B-5 disjunct) | `8` (CHANGED) | 8 | yes |
| S19 | `runFairPackages` arms **above** `if (!leagueId) return;` | `8j` (CHANGED) | 8j | yes |
| S20 | the in-progress branch loses `(isResultsPushed && fairSweepPending)` | `8r` (NEW) | 8r | yes |
| S21 | the deck-done copy reverts to the two-branch version quoting the hidden CTA | `8s` (NEW) | 8s | yes |
| S22 | the QuickSet-regen epoch bump stops disarming the flag | `8t` (NEW) | 8t | yes |
| S23 | the deck-error retry goes back to the unanchored model job | `8u` (NEW) | 8u | yes |
| S24 | a second, **unconditional** `resetDeckForNewTargets()` in `handleFindTrades` | `8v` (NEW) | 8v | yes |

What each new id pins:

- **8r** — the pushed page narrates the sweep (`Looking for trades…`) **and** the never-searched
  `trades.empty-text` card still exists for every other host.
- **8s** — the deck-done body names a control that renders here, neither anchored sentence
  contains "Find a Trade"/"Find more trades", and both legacy sentences stay byte-identical
  (#316: the copy follows whichever control actually renders).
- **8t** — there are exactly **two** `deckEpochRef.current += 1` sites and **both** disarm
  within 400 chars. A third bump site that skips the disarm fails it.
- **8u** — the `trades.deck-error.retry` button's exact `onPress` fork (sliced from its testID,
  so it cannot be satisfied by a different button).
- **8v** — `count(handleFindTrades text, /resetDeckForNewTargets\(/g) === 1`. qa-A F-1's
  sabotage (an extra unconditional reset, guarded line kept) passed all 32 suites before this.

S24 reproduces qa-A's QA-A2; S19 reproduces qa-A's QA-A1b. Both are now red.

### 5.3 Commands after the resolution (session tree, `mobile/`)

| Command | Result |
|---|---|
| `npx tsc --noEmit` | clean, exit 0 |
| `npm run test:results-push` | **75 assertions, all passed** (§8: 28 printed lines, 23 ids) |
| every suite in `grep -l TradesScreen tests/check-*.js` | **32/32 exit 0** |
| `bash scripts/testid-lint.sh` | `testid-lint OK` |

`mobile/src/components/ShopOffersBody.tsx` and `mobile/tests/check-shop-deck.js` untouched
(owned by #418).
