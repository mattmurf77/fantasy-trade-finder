# FB-407 — Code-walk proof (post-fix)

**Date:** 2026-08-30 · **State walked:** working tree on `claude/new-user-feedback-5fa613`
(base d2a0b0bb = origin/main tip e89eebb0 + Phase-1 specs) with the FB-407 fix applied to
`mobile/src/components/InLeagueCalculator.tsx` and the FB-407 section added to
`mobile/tests/check-calc-merged-behavior.js`. All line numbers below are at that state;
files other than those two are byte-identical to e89eebb0.

This executes the mini-PRD's 7-step outline (mini-prd.md §"Code-walk proof outline"),
replacing the simulator capture per D-056.

## The fix, in three pieces

- `InLeagueCalculator.tsx:351` — `const opponentChosenRef = useRef(!!initialOpponentId);`
  A partner counts as *chosen* only when a user gesture (or a deliberate
  `initialOpponentId`) picked them.
- `InLeagueCalculator.tsx:1074` (partner chip row) and `:1485` (team-picker sheet row) —
  each user-tap `setOpponentId(o.user_id)` is now preceded by
  `opponentChosenRef.current = true`.
- `InLeagueCalculator.tsx:1229-1231` — the Find a Trade payload gates the partner:
  `opponent: opponent && (opponentChosenRef.current || receiveIds.length > 0) ? { userId: …, name: … } : null`.

## Step 1 — fresh mount, no user pick: the default is not a choice

On mount with no prefill, `opponentId` starts null (`:344`, `initialOpponentId ?? null`)
and `opponentChosenRef.current` starts `false` (`:351`, `!!undefined`). Once the
coverage list loads, the default-opponent effect fires —
`InLeagueCalculator.tsx:545-548`: `if (!opponentId && opponents.length)
setOpponentId(opponents[0].user_id);` — setting the calculator's internal partner (the
evaluate UX needs a roster) but **never touching `opponentChosenRef`**. The effect body
contains no ref write (pinned by suite assertion 20b-bis). State after step 1:
`opponent` = first leaguemate, `opponentChosenRef.current === false`.

## Step 2 — Find a Trade tap, empty canvas: payload `opponent: null`

The `calc.action.find-a-trade` press (`:1213-1233`) builds the payload. With an empty
canvas, `receiveIds.length === 0`, and with no tap ever made,
`opponentChosenRef.current === false` — so the gate at `:1229`
(`opponent && (opponentChosenRef.current || receiveIds.length > 0)`) evaluates false and
the payload carries `opponent: null` (`:1231`), despite the calculator's internal
`opponent` being the auto-default. Pre-fix this line (`opponent: opponent ? … : null`)
passed the default through unconditionally — the root cause.

## Step 3 — the fork carries the null through, and analytics turn honest

Both hosts route the payload through `forkCanvasSearch`
(`mobile/src/utils/canvasSearch.ts:48-69`, one definition — suite 13c). With empty
sides: `fair = giveIds.length > 0` is false (`:51`), so `path: 'model'` (`:63`),
`anchor: null` (`:67`), and `opponent: opts.opponent` = **null** (`:66`). The
`calc_find_a_trade_tapped` row emits `has_partner: !!opts.opponent` = `false` (`:58`) —
now accurately reporting that no partner was chosen (scope.md §1's "more honest" claim).

## Step 4 — the inline handler clears the scope instead of adopting the default

`handleInlineFindATrade` (`mobile/src/screens/TradesScreen.tsx:3046-3073`) calls
`setSheetOpponent(fork.opponent)` at `:3055` — with `fork.opponent === null` this
**clears** the sheet scope. `scopedOpponent` (`:832-836`, `trades.sheet_targeting` true)
is `sheetOpponent?.userId` → `undefined`. It also sets `fairAnchorRef.current = null`
(`:3066`), `autoRunPendingRef.current = true` (`:3067`), and
`autoRunOriginRef.current = 'calculator'` (`:3068`).

## Step 5 — the choke point dispatches an all-teams sweep

The auto-run choke point fires for a calculator arrival even with no scope —
`TradesScreen.tsx:2998-3000`: `(finderScopeSeen.current || autoRun) &&
(scopedOpponent || (autoRun && autoRunOrigin === 'calculator'))` — the second disjunct
is exactly the "#384 review #3/#9" partnerless-calculator branch. It reaches
`dispatchGenerate({})` (suite 17b), whose request body sends
`opponent_user_id: scopedOpponent || undefined` (`TradesScreen.tsx:1850`) — **omitted**.
Server-side, a falsy `opponent_user_id` keeps the job on the untargeted all-teams path:
`backend/server.py:6090-6096` (`explore_active` requires `not opponent_user_id`) and
`:6258-6261` (likes-you injection, same predicate) — the cache-eligible full-league
sweep, exactly as the pre-merge Find a Trade behaved.

## Step 6 — counter-case: an explicit pick still scopes (#384 checklist item 23)

A tap on a partner chip (`InLeagueCalculator.tsx:1072-1076`) or a team-sheet row
(`:1483-1488`) sets `opponentChosenRef.current = true` before `setOpponentId`. The next
Find a Trade tap's gate (`:1229`) now passes, the payload carries
`{ userId, name }`, `forkCanvasSearch` forwards it (`canvasSearch.ts:66`,
`has_partner: true`), `setSheetOpponent(fork.opponent)` (`TradesScreen.tsx:3055`) adopts
it, `scopedOpponent` resolves (`:832-836`), and the dispatch sends it — model path
`opponent_user_id: scopedOpponent || undefined` (`:1850`), fair path
`...(scopedOpponent ? { opponent_user_id: scopedOpponent } : {})` (`:3353` in
`runFairPackages`, `:3336`). Single-team scoping for a deliberate pick is preserved.
Likewise the built-trade case: receive-side assets (drawn from the partner's roster
picker) make `receiveIds.length > 0`, so the gate passes without any dropdown tap and
the fair sweep stays addressed to that partner.

## Step 7 — loop check: no pin-back into the dropdown

With `scopedOpponent === undefined`, `TradesScreen.tsx:7431` passes
`opponentUserId={scopedOpponent ?? null}` = null into `TradeBuildCanvas`, so
`effectiveOpponentId = prefill?.opponentId ?? opponentUserId ?? undefined` = undefined
(`TradeBuildCanvas.tsx:152`) — the canvas keys/remounts with
`initialOpponentId: undefined` (`:168`, `:172`). No forced team is written back into the
Team dropdown, and (closing the loop with step 1) that remount's
`opponentChosenRef` re-initializes to `false`, so the re-fired auto-default still never
scopes. When a prefill or a real scope IS present, `initialOpponentId` is truthy and
`opponentChosenRef` initializes `true` (`:351`) — an idea's counterparty still
addresses its search, as the mini-PRD requires.

## Untouched contracts (checked, not changed)

- The ✓ queue cell and the evaluate query keep using the internal `opponent`
  (`InLeagueCalculator.tsx` confirm cell, suite 19a-19b) — they need a roster and are
  disabled without a partner; the fix only gates the *search payload*.
- `TradesScreen.tsx`, `TradeBuildCanvas.tsx`, `canvasSearch.ts`, `backend/server.py`:
  zero diff (verified `git status` — only the two owned files modified).
- The pushed `TradeCalculatorScreen` host mounts the same component and hands the same
  payload to the same `forkCanvasSearch`, so it is fixed identically.

## Structural guard

`mobile/tests/check-calc-merged-behavior.js` FB-407 section (assertions 20a-20d), each
sabotage-verified red→green — cycles recorded in [status.md](status.md).
