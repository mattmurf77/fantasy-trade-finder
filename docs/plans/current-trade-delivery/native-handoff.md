# Native Usage Trends handoff recovery

Date: 2026-11-06. Scope: recover the unpushed mobile continuation of PR #604.
This does not establish the 200 ms target or enable preparation in production.

## Behavior and code walk

- `mobile/src/screens/UsageTrendsScreen.tsx:314` begins the original search
  trace at the Trade tap, before dismissal or league initialization. An
  unresolved roster owner still opens the builder without a false search tap.
- `UsageTrendsScreen.tsx:297` keeps the availability sheet mounted while making
  it invisible. Its close promise completes from the real dismissal callback.
  `mobile/src/components/UsageLeagueList.tsx:134` uses the iOS native callback
  or the committed hidden modal on Android, with Trade's closing animation
  disabled. The separate Add/Alert path retains its existing 450 ms wait.
- `UsageTrendsScreen.tsx:339` starts dismissal and the authorized league switch
  together. Neither a failed/no-op switch nor a changed account, token revision,
  current league, focus or newer action may write pins or navigate. Blur and
  unmount abandon the pending trace and settle the dismissal waiter (line 120).
- After both operations complete, receive-player and opponent pins plus the
  **same** search ID reach Finder. This does not pre-evaluate the selected trade.
- `mobile/src/state/tradeSearchTrace.ts:139` emits `cross_league_handoff` only for
  a Usage Trade that starts in another league. `mobile/src/api/events.ts:196`
  gives this explicit scenario priority over an earlier input-change marker;
  it does not attach that unrelated change's age. No new event or private field.

## Executed evidence

`mobile/tests/check-usage-trade-handoff.js` executes actual screen handlers and
sheet rendering with controlled session/dismissal promises: **23 checks pass**.
These cover parallel starts, real callback gating, account/token/focus/new-action
changes, failed or uncommitted switches, unchanged search ID, no-owner arrival,
no-sheet entry, and scenario precedence. Eight in-memory source mutations
(account, token, action, focus, league, switch, scenario and native callback
fences) all fail the suite. Neither test execution nor mutation controls alter
native builds or production state.

Focused existing suites passed: Usage Trends, first-card events, instant trade
handoff (28), device page, prewarm (20), results push, entry session identity,
and session seed. After the dependency install, full `tsc --noEmit` and the fa-move regression
(115 passed, 0 failed) also passed; all ten focused suites were rerun with the
installed dependencies. These are code-contract checks, not measurements of
native rendering or iOS dismissal behavior on a physical phone.

The independent backend/native request review also found a local page alias:
`devicePageScope` rounded .746 to .75. It now admits only finite 0–1 thresholds
exactly representable at hundredths, matching the strict server. Unknown filters
and malformed package modes cannot borrow an organic page. A follow-up runtime
type check also declines malformed known fields (pin objects/non-string elements,
non-boolean force, empty/non-string optional scope fields, non-string league ID),
so untrusted parsed input cannot bypass the strict API through the local cache. The executed device
page regression checks the alias, precision boundaries, range, and new filters;
actual .50 and .75 callers remain unchanged.

## Physical TestFlight checklist

On the exact candidate build, in both Simple availability sheet and expanded
Raw stats row:

1. Trade a rostered player in the current league, then in another linked
   league. Verify the right league, player and opponent, no duplicate search,
   no stuck sheet, and first-card timing measured from the original Trade tap.
2. Repeat both directions immediately after league and preference changes on
   Wi-Fi and cellular. Count every wait, timeout and missing card. A loading
   screen or empty state is not a passing visible trade.
3. Leave Usage while switching, or sign out before a slow switch finishes.
   No late navigation/pins may cross that boundary. A failure must be attributed
   to the original search, never replaced by a fresh clock at Finder entry.
4. Verify Add still opens its claim sheet or unsupported-platform explanation
   cleanly after availability dismissal. Verify ordinary close/reopen still works.

## Remaining latency limits

The current prewarm hook covers only the active organic league/format. New
preferences invalidate its page, and passive refresh is debounced/bounded.
Pinned players, opponents and fair packages require their exact current solve.
Cross-league session initialization still depends on the network. Removing a
450 ms UI floor does not make any of these paths a guaranteed 200 ms response.
