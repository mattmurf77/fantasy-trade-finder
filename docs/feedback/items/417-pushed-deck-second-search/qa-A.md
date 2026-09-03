# FB-417 — QA A (independent static QA)

**Date:** 2026-09-03 · **Tree:** `claude/new-user-feedback-06dabd` @ `f6adea8b` (merge of `6cd5c490`, diff base `c529abc8`)
**Contract:** [prd.md](prd.md) R-1…R-5 · [scope.md](scope.md) · [build-notes.md](build-notes.md) (re-verified, not trusted) · [investigation.md](investigation.md)
**Sabotage worktree:** `qa417-a` off `f6adea8b`, removed and branch deleted at the end of this pass.

## Verdict: PASS

No BLOCKING finding. Every changed source line traces to a requirement; every requirement has lines; none of the four re-specced guard suites was loosened. All eight builder sabotages I re-ran reproduce red on the named assertions. Two plausible wrong implementations of my own design pass every suite (F-1, F-2) — guard gaps, not defects in the shipped code — and the `dispatchGenerate` census comment in the source was left stale (F-3).

## Findings

| id | severity | file:line | description | proof |
|---|---|---|---|---|
| F-1 | NON-BLOCKING | `mobile/tests/check-results-push.js` §8 (8d/8e) | **Guard gap — R-2's "non-fair decks are untouched" has no pin.** An extra *unconditional* `resetDeckForNewTargets();` anywhere in `handleFindTrades` (the guarded `if (fairDeck)` line left intact) makes every "Find more trades" tap on a **model** deck REPLACE the deck instead of appending — the exact behavior code-walk (4) and checklist step 7 say must not change — and all 32 TradesScreen suites stay green. Fix: pin `count(hftText, /resetDeckForNewTargets\(/g) === 1` next to 8d. | Sabotage QA-A2 below: 0 red across 32 suites |
| F-2 | NON-BLOCKING | `mobile/tests/check-results-push.js` §8 (8j/8m); `TradesScreen.tsx:3547-3552` | **Guard gap — arm-after-early-return is not pinned.** Reordering `runFairPackages` to `const epoch…; setFairSweepPending(true); if (!leagueId) return;` passes 8j (regex only requires `const epoch…;\s*setFairSweepPending(true);`) and 8m (still one arm, two disarms). With `leagueId` null the flag is stranded `true` until some reset — CTA and landing cell disabled. Runtime exposure is low (the choke point only runs `runFairPackages` when the instance already has a league), so NON-BLOCKING, but the assertion's stated intent ("at ENTRY") is not what it checks. Fix: anchor 8j on `if \(!leagueId\) return;\s*const epoch = deckEpochRef\.current;\s*setFairSweepPending\(true\);`. | Sabotage QA-A1b below: 0 red across 32 suites |
| F-3 | NON-BLOCKING | `mobile/src/screens/TradesScreen.tsx:1999-2006`; `:1684-1686`; `mobile/tests/check-offer-prefill-330.js:190` | **Stale census comments after the 9→8 re-key.** The `dispatchGenerate` DISPATCH CENSUS header still enumerates 8 routed sites and its item 8 is "legacy `!consolidateOn` CTA — routed anyway" — that site no longer calls `dispatchGenerate` (it calls `handleFindTrades()`, site 1). `check-canvas-results.js` 12a's own failure text says a change "must be added to the helper's census table AND this count" — the count was re-keyed in four suites, the table was not. Likewise `:1684` still says "Two find_trades_tapped emitters exist below (… the legacy `!consolidateOn` arm's inline track)" — that emitter was deleted by this change. `check-offer-prefill-330.js:190` still says "check-canvas-results §12 owns the 8-site census". Comment-only; no behavior. | `git grep -n "8\. legacy !consolidateOn\|8-site" mobile/` |
| F-4 | NOTE | `mobile/tests/check-results-push.js` 8q | **Near-vacuous assertion.** 8q asserts `config/features.json` does not contain the *identifier strings* `fairSweepPending` / `findCtaHiddenForAnchoredDeck`. A flag under any other key (e.g. `calc.anchored_deck_cta`) passes. S17 went red only because that sabotage used the identifier as the key. R-5 is still true in the code (verified: `git diff c529abc8 6cd5c490 -- config/` is empty) — the pin just does not defend it. | `git diff c529abc8 6cd5c490 --stat -- config/ backend/` → nothing |
| F-5 | NOTE | `mobile/tests/check-results-push.js` 8c | **Survival-only check.** 8c asserts the six replacement testIDs exist in the file; it does not check they *render* on the anchored pushed deck (the `calcMergedOn && fairDeck && !inlineAnchorShown` stand-aside at :8597/:8691, or `inlineAnchorShown` at :7753). Those gates are pre-existing and pinned by the D-158/D-171 suites (`5f`–`5h` here), so this is honest but weak, and the PRD's R-1 table carries the real proof. | Code-walk (1) below |
| F-6 | NOTE | `TradesScreen.tsx:3009-3030` (store-handoff forward, `anchorLabel: null`) → `:5807`, `:7229/:7443`, `:8597/:8691` | **Null-label anchored pushed deck has no mid-deck search control.** When a `FinderHandoff` with a `fairAnchor` is forwarded into the push (flag-off calculator page's Find a Trade), `inlineAnchor` is null → no receipt; `findCtaHiddenForAnchoredDeck` is true → no CTA; the "Search all trades" / "Back to calculator" exits render **only at deck exhaustion** and only under `calcMergedOn`. Mid-deck the only exit is the TabNav back control (4i). This is consistent with D-171 ruling 1 (landing = builder) and strictly better than pre-fix (the mid-deck control WAS the bug), but the PRD table row "Without one … this renders" should say "at the end of the deck". Design-accepted; flag for the operator's awareness. | Read of the gates cited |
| F-7 | NOTE | `mobile/tests/check-inline-home.js` 11b | The optional `( && !findCtaHiddenForAnchoredDeck)?` conjunct means 11b alone would accept an arm that lost the #417 gate. Ownership is explicitly delegated to `check-results-push` 8a, which counts exactly 2 gated arms and went red on S2. Legitimate re-spec, not a loosening. | S2 → 8a red |
| F-8 | NOTE | `TradesScreen.tsx:3157-3183` (consumption effect) → `:3056` (choke reset) → `:3552` | **The sub-frame before `fairSweepPending` arms is closed by React, not by #417.** The pushed instance's first commit renders the CTA enabled (`fairDeck` false, `fairSweepPending` false) until the consumption effect bumps `canvasRunSeq` → re-render → choke point arms the flag. React flushes pending passive effects before dispatching a discrete event, so a tap cannot land there; and if one did, the choke point's `resetDeckForNewTargets()` (:3056) bumps the epoch *after* that tap's `onMutate` stamp, so the model result is dropped as stale. Not a defect. | Read; `deckEpochRef` :1857-1863, `onMutate` :1908 |
| F-9 | NOTE | `TradesScreen.tsx:1130` under `canvasResultsLive` (flag-dormant) | On the `calc.canvas_results` in-place posture (kill-switch restore), `handleFindTrades` from a fair deck now `setBrowseSession(null)` via the reset, then `dispatchGenerate` recreates `{origin:'model'}` — a fresh model session instead of an adopted fair one. Arguably more correct; flag dormant; out of #417's scope. | Read :2013-2017 |
| F-10 | NOTE | `TradesScreen.tsx:1108` callers other than the CTA | The prefs-changed strip and deck-error retry reach `handleFindTrades` without a `fairSweepPending` gate. Both are practically unreachable inside the ~1 s window (the fair fork clears the strip at :3128-3129 and `runFairPackages` clears `deckFailure` at :3553), and a dispatch there shares the sweep's epoch (pre-existing last-write-wins, documented at :1861). Pre-existing; not a #417 regression. | Read |

## 1. Diff review — every line vs R-1…R-5

`git diff c529abc8 6cd5c490 -- mobile/` = `TradesScreen.tsx` +86/−? and five test files. Source lines (post-fix numbers verified in this tree):

| Line(s) | Change | Req | Traceable? |
|---|---|---|---|
| :766-776 | `fairSweepPending` state + comment | R-3 | yes |
| :1120-1130 | `if (fairDeck) resetDeckForNewTargets();` in `handleFindTrades`, before `setFairDeck(false)` (:1131) and `dispatchGenerate({})` (:1134) | R-2 | yes |
| :2902-2906 | `setFairSweepPending(false)` in `resetDeckForNewTargets` | R-3 | yes |
| :3549-3552 | arm at `runFairPackages` entry, after `if (!leagueId) return;` (:3547) and beside `const epoch` (:3548) | R-3 | yes |
| :3584, :3594 | disarms after the two `#330` epoch guards (:3572, :3586) | R-3 | yes |
| :5808-5820 | `findCtaHiddenForAnchoredDeck = isResultsPushed && fairDeck` | R-1 | yes |
| :7229, :7443 | both arms' gate gains `&& !findCtaHiddenForAnchoredDeck` | R-1 | yes |
| :7238-7243, :7452-7457 | both arms' `disabled` gains `fairSweepPending` | R-3 | yes |
| :7244-7251 | legacy arm `onPress={() => handleFindTrades()}` (was inline `track` + `setPinIdeaResumed(false)` + `dispatchGenerate({})`) | R-2, R-4 | yes — the removed `track` is re-emitted by `handleFindTrades`'s no-`source` branch (:1114-1116) with the identical `{ mode: deckMode }` payload |
| :7660-7670 | `onFindATrade={canvasHost === 'flag' && !fairSweepPending ? … : undefined}`; `InLeagueCalculator.tsx:1297` is `disabled={!onFindATrade}`, :1299 early-returns, :1318 applies `actionBtnDisabled` (verified) | R-3 | yes |

No orphan lines. No requirement without lines. R-5: `git diff c529abc8 6cd5c490 -- config/ backend/` is empty. The chalkline `Button` (`components/chalkline/Button.tsx:50-57`) maps `disabled` onto the Pressable's `disabled` and `accessibilityState`, so R-3's `disabled` is load-bearing, not cosmetic.

### The four re-specced suites — superseded or loosened?

| Suite / pin | Was → is | Verdict |
|---|---|---|
| `check-analytics-297-302.js` `#298` emitter census | 4 → 3 | **Superseded.** Counted myself: pre-fix code emitters at `:1103, :3088, :3528, :7195`; post-fix `:1114, :3115, :3559`. The removed one is the legacy arm's inline track; its row is now `handleFindTrades`'s no-`source` branch, same name, same shape (pinned by the assertion directly above at `/source \? \{ source, mode: deckMode \} : \{ mode: deckMode \}/`). A new emitter still breaks 3 |
| `check-analytics-297-302.js` "legacy-layout CTA sends mode too" | exact-string count of the inline track → regex on the arm's `onPress={() => handleFindTrades()}` AND no `dispatchGenerate(` within 700 chars of the first `testID="trades.find-btn"` | **Strengthened.** The old pin could not exist (the string is gone); the new one pins the routing that both preserves the row and delivers R-2's reset. Red on S9 |
| `check-canvas-results.js` 12a / `check-results-push.js` 4f / `check-offer-prefill-330.js` S-2 / `check-inline-home.js` 7f — `dispatchGenerate(` census | 9 → 8 | **Superseded.** Counted myself: pre 9, post 8 (`:1134 :1959 :2007def :2258 :3126 :3493 :3689 :4599`). Raw `generateMutation.mutate(` stays 1 in comment-stripped code. S9 (re-adding the private dispatch) turns 4f red, so the tighter count is live |
| `check-inline-home.js` 3c | regex now REQUIRES `&& !fairSweepPending` | **Stricter**, not looser |
| `check-inline-home.js` 11b | optional `( && !findCtaHiddenForAnchoredDeck)?` | **Legitimate** — host gate still required and first; new conjunct owned by results-push 8a (F-7) |
| `check-inline-home.js` 3 / 11d window widths | 900→1800, 1100→2000 | **Mechanical.** The assertions inside are byte-identical in the diff; the mount grew a 6-line comment |

## 2. Command results (session tree, read-only)

| Command | Result |
|---|---|
| `cd mobile && npx tsc --noEmit` | exit 0, clean (7.5 s) |
| `npm run test:results-push` | `check-results-push: all assertions passed` — **70 ✓**; §8 prints **23 lines / 18 distinct ids** (8, 8a–8q; 8c × 6) — matches build-notes |
| all 32 `tests/check-*.js` mentioning `TradesScreen` (`grep -l TradesScreen tests/check-*.js`) | **32/32 exit 0**, each final line a pass banner (incl. `check-analytics-297-302`, `check-canvas-results`, `check-inline-home`, `check-offer-prefill-330`, `check-shop-deck` untouched) |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK`, exit 0 |

## 3. Sabotage table (my worktree `qa417-a` @ `f6adea8b`, `mobile/node_modules` symlinked; `git checkout -- .` between runs, 0 dirty files after each)

| # | Sabotage (exact edit) | Red assertions | Restored |
|---|---|---|---|
| S2 | `:7443` → `{canvasHost !== 'flag' ? (` | 8a | yes |
| S5 | delete `:1130` | 8d, 8e | yes |
| S6 | move `if (fairDeck) resetDeckForNewTargets();` after `dispatchGenerate({})` | 8e | yes |
| S9 | legacy arm back to inline `track` + `setPinIdeaResumed(false)` + `dispatchGenerate({})` | **4f**, 8h, 8i (builder listed 8h, 8i; 4f also fires) | yes |
| S10 | delete `:3552` arm | 8j, 8m | yes |
| S11 | delete `:3584` success disarm | 8k, 8m | yes |
| S14 | delete `:2906` reset disarm | 8n | yes |
| S15 | consolidated `disabled` back to the single pre-#417 line | 8o | yes |
| **QA-A1b** (mine) | `runFairPackages`: `const epoch…; setFairSweepPending(true); if (!leagueId) return;` (arm before the early return) | **none — 0 red in all 32 suites** → F-2 | yes |
| **QA-A2** (mine) | add unconditional `resetDeckForNewTargets();` after `setPinIdeaResumed(false)` in `handleFindTrades` (guarded line kept) | **none — 0 red in all 32 suites** → F-1 | yes |
| QA-A3 (task-suggested) | `findCtaHiddenForAnchoredDeck = fairDeck;` | 8 | yes |
| QA-A4 (task-suggested) | success disarm moved ahead of the epoch guard | 8k | yes |
| (stale-closure variant — `if (fairDeckRef.current)`) | not run: 8d's exact-string match `if \(fairDeck\) resetDeckForNewTargets\(\);` cannot pass it | — | — |

A first attempt at QA-A1 left two arms in place and `8m` caught the malformed edit; QA-A1b is the corrected single-arm reorder and is the result reported.

## 4. Code-walk proof (post-fix line numbers, this tree)

**(1) Pushed fair deck → no `trades.find-btn`, and what does render.** `handleInlineFindATrade` (:3196) forks via `forkCanvasSearch`; under `resultsPushLive` (:5839 = `resultsPushOn && canvasHost === 'flag'`) it `push`es `TradeDeck` with `resultsPush.{fairAnchor, anchorLabel}` (:3213-3222). On the pushed instance `resultsPushParam` is set → `isResultsPushed` true (:857) → `canvasHost` is `null` by param presence (:5785-5790), so the pre-#417 gate `canvasHost !== 'flag'` would have rendered the CTA on both arms. The consumption effect (:3157-3183) seeds `inlineAnchor` (label + ids, :3170-3178), arms `fairAnchorRef` (:3178), bumps `canvasRunSeq`; the choke point (:3054-3131) resets (:3056), takes the fair fork (:3081-3095) and calls `runFairPackages` (:3546). Its success exit sets `fairDeck` true (:3583). Now `findCtaHiddenForAnchoredDeck = isResultsPushed && fairDeck` (:5820) is true and both gates `canvasHost !== 'flag' && !findCtaHiddenForAnchoredDeck` (:7229, :7443) are false → **neither Button mounts**. What renders: the receipt — `inlineAnchorShown = (canvasHost === 'flag' || isResultsPushed) && fairDeck && !!inlineAnchor` (:5807-5808) → `<View testID="trades.anchor-receipt">` (:7753) with Change (:7760, `onPress` = `handlePushedAnchorChange` on the pushed arm, :7775-7781) and Clear (:7786, `onPress={canvasResultsLive ? handleBrowseClear : handleSearchAllTrades}` :7793 — `canvasResultsLive` is false here since `canvasHost` is null, so it IS `handleSearchAllTrades`). End of deck: "Back to calculator" (:8564, :8672) gated `calcMergedOn` only; "Search all trades" (:8597, :8691) gated `fairDeck && !inlineAnchorShown` — **stands aside while the receipt is up** (D-158 comment :8590-8592). **Null-`anchorLabel` case** (store-handoff forward, :3009-3030 sets `anchorLabel: null`): `inlineAnchor` is null (:3170-3177) → no receipt → `!inlineAnchorShown` true → the end-of-deck search-all renders (under `calcMergedOn`). Mid-deck that instance has only the header back control — F-6.

**(2) Pushed fair deck → "Search all trades" / receipt Clear → clean model deck.** Both press `handleSearchAllTrades` (:3670): `deck_search_all_tapped`, `setSummaryDismissed(true)`, `handleFindTrades('deck_search_all')` (:3674). In `handleFindTrades` (:1108) the closure's `fairDeck` is true → `resetDeckForNewTargets()` (:1130 → :2890): `deckEpochRef.current += 1` (:2893, synchronous), `setDeck([])` (:2897), `setDeckIdx(0)`, `setJob(null)`, `setFairDeck(false)` (:2900), `setFairSweepPending(false)` (:2906), `setBrowseSession(null)`. Then `setFairDeck(false)` (:1131, idempotent), `pendingScrollToDeckRef` (:1133), `dispatchGenerate({})` (:1134 → :2007 → `generateMutation.mutate` :2018). Next render: `fairDeck` false → `inlineAnchorShown` false → receipt gone; `findCtaHiddenForAnchoredDeck` false → CTA back. The streaming effect (:2160-2166) appends `job.cards` into `prev`, which is now `[]` — model cards only, no fair card survives.

**(3) The 1-second window from the event trace.** Push (22:03:06) → pushed instance mounts → consumption effect → choke point: `resetDeckForNewTargets()` (:3056, disarms) then `runFairPackages` → `setFairSweepPending(true)` (:3552) in the same effect tick, so the committed value is `true`. During the `await getFairPackages` (:3561) `fairDeck` is still false → `findCtaHiddenForAnchoredDeck` false → **the CTA renders** (label "Find a Trade": `deck.length` 0) **but `disabled`** via the fourth disjunct (:7242 / :7456), which chalkline `Button` passes to its Pressable (`Button.tsx:54`). The 22:03:07 tap is inert. On arrival, the epoch guard (:3572) passes, `setDeck`/`setFairDeck(true)`/`setFairSweepPending(false)` (:3580-3584) commit together → `fairDeck` true → CTA **unmounts** (gate false) — it never becomes enabled again on this deck. Landing side (in-place posture only): `onFindATrade` withheld (:7667) → `InLeagueCalculator:1297` `disabled={!onFindATrade}`; under the push posture the landing never runs a sweep (D-171 ruling 1, :3060-3070), so that guard is inert there.

**(4) Pushed MODEL deck → "Find more trades" appends unchanged.** Empty canvas → `fork.anchor` null → push with `fairAnchor: null` (:3213-3222) → consumption effect: `inlineAnchor` null, `fairAnchorRef` null, `autoRunPendingRef` true (:3179) → choke point takes the model arm (:3103-3126) → `dispatchGenerate({})` (:3126); `fairDeck` never set. `findCtaHiddenForAnchoredDeck` false → CTA renders; label flips to "Find more trades" once `deck.length > 0 && job?.status === 'complete'` (:7235-7237 / :7449-7451, untouched). Tap → `handleFindTrades()` → `if (fairDeck)` false → **no reset** → `dispatchGenerate({})` → streaming effect appends fresh `trade_id`s onto the existing `deck` (:2160-2166). Byte-identical to `c529abc8` except that the legacy arm now also clears `fairDeck`/the #257 nudge (already false/cleared on this path). Not structurally pinned — F-1.

**(5) A superseded sweep cannot strand `fairSweepPending`.** Sweep A arms at :3552 with `epoch = N`. Any reset (choke point :3056, `handleFindTrades` :1130, league switch, QuickSet :4586 bumps the epoch directly but is followed by a reset path) sets `deckEpochRef = N+1` and `setFairSweepPending(false)` (:2906). When A's `await` returns, `deckEpochRef.current !== epoch` (:3572 or :3586) → `return` **before** either disarm (:3584/:3594) — so A neither re-enables controls for a live sweep B (B armed after the reset) nor leaves the flag `true` (the reset already cleared it). If a new sweep B is running, B's own exit disarms. 8m pins exactly one arm and two disarms so no disarm can be added ahead of the guard (QA-A4 confirms 8k catches the move).

## 5. Epoch / #330 audit

`handleFindTrades` orders `if (fairDeck) resetDeckForNewTargets();` (:1130) → `dispatchGenerate({})` (:1134). The bump (`:2893`) is a synchronous ref write in the same call stack; `onMutate: () => ({ epoch: deckEpochRef.current })` (:1908) runs inside `mutate`'s execute and nothing else bumps the ref between, so the mutation is stamped with the **new** epoch and `applyJobResult` (:1910-1914) accepts its result. Reverse order (S6) would stamp `N` then bump to `N+1` and drop the search it started — 8e is red on that. No path introduced by #417 drops a live model result: the only epoch bumps are the pre-existing reset sites (choke point, league switch, QuickSet regen, keep-side, suppression undo), which supersede on purpose. Two manual taps without an intervening reset still share an epoch (:1861-1863, pre-existing, out of scope).

## 6. Fixture honesty

- Census re-specs are honest: emitters 4→3 and dispatch sites 9→8 counted independently against `git show c529abc8:…` and the working tree (§1 table). The raw `generateMutation.mutate(` count is 3 in the raw file and 1 in comment-stripped code — the suites use `tradesCode` (stripped), so the "1 raw mutate" pin is correct.
- No §8 assertion passes on a shape the code never produces: 8a/8o/8p/8j/8k/8l regexes match the actual post-fix text (each went red under the matching sabotage). 8f uses the AST (`referencesIdentifier(host, rst, 'useFinderTargets')`) and is red on S7 per build-notes (not re-run here; the helper is sound — it scopes identifier hits to the function's span).
- Weak but not vacuous: 8c (F-5) and 8q (F-4).
- Gaps (missing pins, not false pins): F-1, F-2.

## 7. Cleanup

`git worktree remove --force <scratchpad>/wt-qa417-a` and `git branch -D qa417-a` executed; `git worktree list` shows no `qa417` entry and the branch is gone. Nothing committed; no source edited in the session tree. Only this file was written.
