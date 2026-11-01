# Free-agent moves (D1): code-walk, client half

> The scope block's §3 code-walk skeleton (`docs/plans/sleeper-fa-write/scope.md` on `plan/fa-moves-launch`), filled for the dark client in the 11-06 binary on `feat/fa-moves-client` (based on #509 @ `d14b7308`). Items 4 and 7 are the server's and are filled by the server PR. The wire is [contract.md](contract.md) (as of `41c1443e`). Citations are `file:line` on this branch after platforms-eng's review round 3 (contract `3248995b`: the consent routes need a verified session). Evidence: `mobile/tests/check-fa-move.js` (F1–F17, L1/R1/P1/T7, X1–X12, Y1–Y3) and the TEST_LEDGER entry of 2026-11-01.
>
> Paths: `faMove.ts` is `mobile/src/api/faMove.ts`; `claimSheetPlan.ts` is `mobile/src/utils/claimSheetPlan.ts` (the sheet's decisions as pure functions, which the suite executes); `ClaimSheet.tsx` is `mobile/src/components/ClaimSheet.tsx`, which renders those decisions and runs their effects.

## Contents

- [Dark-safety: no usable `move` in the FA response](#dark-safety-no-usable-move-in-the-fa-response)
- [1. Host Add → `move.mode` → sheet, or NO_ADD_REASON](#1-host-add--movemode--sheet-or-no_add_reason)
- [2. `faMoveGate` → connect, verify, consent or submit](#2-famovegate--connect-verify-consent-or-submit)
- [3. Consent GET → step → POST …/move with `consent` (client half)](#3-consent-get--step--post-move-with-consent-client-half)
- [4. Server order of checks](#4-server-order-of-checks)
- [5. Result → held page discarded → Done → FA invalidation](#5-result--held-page-discarded--done--fa-invalidation)
- [6. Withdrawals (Settings)](#6-withdrawals-settings)
- [7. Capability computation per platform](#7-capability-computation-per-platform)
- [Choices the contract and scope left open](#choices-the-contract-and-scope-left-open)

## Dark-safety: no usable `move` in the FA response

Today's server sends no `move`. Every path below then lands where `d14b7308` does.

- **Nothing of a bad capability is used.** `capabilityOrNull` drops an absent, malformed or unknown-mode `move`, and `submit` with no known `league_platform` (`faMove.ts:205-210`, `:280-282`). With none, `rowMoveFields` drops every row's `move_kind` / `move_mode` / `move_line` (`faMove.ts:286-289`), so `move.copy` and the row's line are never read (review round 2, item 10). The sheet starts from both (`ClaimSheet.tsx:222-223`).
- **The gate says legacy.** `faMoveGate` returns `'legacy'` (`faMove.ts:249`), and `faMoveOpensSheet` is false (`faMove.ts:271-276`).
- **Free Agents routes as before.** `onAdd` opens the sheet iff `faMoveOpensSheet(move, row) || addPlatform === 'sleeper'`, else `explainNoAdd(addPlatform)` (`mobile/src/screens/FreeAgentsScreen.tsx:89-100`). With the first term false, that's `d14b7308`'s test (`d14b7308:mobile/src/screens/FreeAgentsScreen.tsx:78-85`). The Add variant uses the same expression (`FreeAgentsScreen.tsx:217`). Each row's `claimPending` is false: the store behind it is written only from a `submit`-mode pending result (`mobile/src/state/claimsPending.ts:17-32`; `claimSheetPlan.ts:137-150`), so the stats line is the drop line as before (`FreeAgentsScreen.tsx:218`, `:296-300`).
- **Usage Trends routes as before, one read earlier.** `doAdd` keeps `resolveAddPlatform(lgId, isDemo)` → `explainNoAdd(platform)` for non-Sleeper and switch-then-open for Sleeper (`mobile/src/screens/UsageTrendsScreen.tsx:289-316`). The one difference: a plain FA read for the capability runs before routing, bounded at 3 s (`readMoveCapability`, `faMove.ts:639-648`), with the tapped Add shown busy meanwhile (`UsageTrendsScreen.tsx:297-305`). It's outside the query cache, so the sheet still reads its own list after the switch, as on `d14b7308`. With no `move` in the answer (or none in 3 s) the route is the old one.
- **The sheet renders #509's hand-off.** `initialView` gives `{step: 'handoff', line: null}` for `legacy` (`claimSheetPlan.ts:89-110`). `submitLayout` is false (`ClaimSheet.tsx:256`), so the `if (!submitLayout)` render runs (`ClaimSheet.tsx:1023-1048`): header, bid, drop, then `handoffBlock` (`:808-814`), which is #509's CTA (`:615-623`; `fa-claim.open-sleeper`, the same label, `onPress={openSleeper}`, `disabled={bidTooHigh}`) and the footer. Same Modal, backdrop, sheet styles and scroll as `d14b7308:ClaimSheet.tsx:152-327`.
- **What differs in that render, and why.**
  - **The footer's words.** "Sleeper doesn't allow apps to submit claims — finish in Sleeper." (`d14b7308:ClaimSheet.tsx:319-321`) becomes the fallback "You'll finish this move in Sleeper." (`ClaimSheet.tsx:611`), since `move.copy` isn't read without a capability. The old line is false once `submit` is on anywhere; this is specified (scope §C state 1).
  - **Plumbing with today's values.** Cancel, the backdrop and `onRequestClose` go through `requestClose` (`ClaimSheet.tsx:400-405`), which is `onClose` while nothing is sending. Cancel, the bid input and the drop rows take `disabled={busy}` / `editable={!busy}`, always false here. The header text is `` `Claim ${row.name}` `` (`:607-610`). `dropListShown` is #509's expression when no drop has been required (`claimSheetPlan.ts:295-298`). A selected drop that leaves the candidates is cleared (`ClaimSheet.tsx:322`); in the hand-off that's invisible.
  - **No new request.** The sheet makes no call of its own unless the user acts in the `submit` layout.

## 1. Host Add → `move.mode` → sheet, or NO_ADD_REASON

- **Free Agents.** The capability comes from the list's own read (`FreeAgentsScreen.tsx:79`). The tap routes it first (`:92`), keeps the capability as it was at the tap (`:93`) and mounts the sheet with it and a `refetch` (`:235-236`).
- **Usage Trends.** `readMoveCapability` returns only `move` and the tapped row's move_* fields (`faMove.ts:639-648`). A non-Sleeper league whose capability doesn't open the sheet gets `explainNoAdd` (`UsageTrendsScreen.tsx:306-309`); otherwise it switches league and opens the sheet with those fields and the capability (`:310-315`, `:712-713`). While the read runs, the row's Add (and the expanded list's Add for that league) is disabled with a spinner (`:404`, `:434-435`; `mobile/src/components/UsageTrendCard.tsx`, `UsageStatsTable.tsx`, `UsageLeagueList.tsx`).
- **`move.mode` first.** In `submit` mode every step opens the sheet on any platform except MFL without a connection (`faMoveOpensSheet`, `faMove.ts:271-276`), so MFL and ESPN open it in Update 1 with no build. A **held row** (`move_mode: 'handoff'`) opens it too, also on ESPN/MFL, where it shows the server's `move_line` (fallback: "This move can't be made from Fleeced right now. Check ESPN.") rather than `NO_ADD_REASON`'s read-only text (`claimSheetPlan.ts:103-106`). `unsupported` on a non-Sleeper league is today's `NO_ADD_REASON` alert, byte for byte (`ClaimSheet.tsx:121-157`, unchanged; `check-sleeper-handoff.js` S9).

## 2. `faMoveGate` → connect, verify, consent or submit

`faMove.ts:241-264`, in order:

1. No usable capability → `legacy` (`:249`).
2. `unsupported` → `unsupported`; `handoff` → `handoff` (`:250-251`).
3. `submit`, not connected, on a platform with no connect screen in this binary (MFL) → `unsupported` (contract §6; `:253-255`).
4. A held row → `handoff` (`:256`). A `claim` row while `move.claims` isn't true → `handoff`, state 14 before the tap (`:259`).
5. `expired` / `unverified` → `verify`; anything else but `ok`, including `other_account` and unknown values → `connect` (`:260-261`). Connect and verify beat consent.
6. Consent valid → `submit`; ticked → `submit_with_consent`; otherwise `consent` (`:262-263`). An unticked box never submits.

The sheet's first view follows the gate (`initialView`, `claimSheetPlan.ts:89-110`): connect/verify with the server's line, Ready for every submit step (consent is asked at the tap), MFL's `unsupported` as that platform's `NO_ADD_REASON` inside the sheet (`claimSheetPlan.ts:99-102`; rendered at `ClaimSheet.tsx:981-994` with only Done, `:934-935`).

## 3. Consent GET → step → POST …/move with `consent` (client half)

- **The selection.** `moveSelection` is the one source for the named CTA, the waiver lines and the request: the drop only while it's still in the candidates, and a claim's bid ($0 for an empty FAAB bid; none in a priority-waiver league) (`claimSheetPlan.ts:260-291`; `ClaimSheet.tsx:288-299`). The CTA comes from `moveCtaLabel` with contract §7's no-bid claim slots (`faMove.ts:843-860`), and a claim's lines from `waiverLines`: `waiver_line` with a drop, `waiver_line_no_drop` without, then `bid_line` only with a bid (`faMove.ts:864-872`; `ClaimSheet.tsx:840`).
- **The tap.** `onNamedCta` asks the gate with `consent_until` against now (`ClaimSheet.tsx:506-517`). `consent` → `openConsent(true)` (`:451-478`), which reads through `fetchConsentStep` (`faMove.ts:360-376`): **NetInfo first**, so offline sends no GET; offline, or a GET that fails at the network level (status 0, the timer), is state 11 with nothing sent (`planNotSent`); `valid` sends (the capability was stale); a block shows the step; a 403 `verification_required` (the route needs a verified session, contract §2) is state 4, Verify, through the same `planFailure` as the move route's 403 (`ClaimSheet.tsx:468-470`); any other server failure, a 404 or an incomplete block is F4's hand-off with `unavailable_line`.
- **The step.** `showConsent` (`ClaimSheet.tsx:480-503`) unticks every time, shows "terms changed" when the block's `reason` is `version` or this sheet showed another `copy_version` (`termsChanged`, `faMove.ts:394-396`; `ClaimSheet.tsx:483`), reports the block's own `reason` when it sends one (`consentShownReason`, `faMove.ts:442-448`; `ClaimSheet.tsx:485`, `:502`), and refuses to ask consent for a move it can't name (`:493`). The body is the server's `title`, paragraphs and `this_move` filled with the same `ctaLabel` (`:963-980`). The pinned block holds the **unticked** box (`:881`), Make the move with the server's `button_label`, disabled until ticked, with a VoiceOver hint (`:897`), Not now (`:906`), Do it in Sleeper instead, and legal's links row: the block's `links` (https only), else the app's Terms and Privacy built from `getBaseUrl()` like PaywallScreen's `openLegal` (`consentLinks`, `faMove.ts:337-344`; `ClaimSheet.tsx:916-931`), each opened through `openPlatform` with no catch (`:416-418`).
- **The send.** `send` re-asks the gate and returns unless it says `submit` / `submit_with_consent` (`ClaimSheet.tsx:521-529`), then calls `attemptMove` once with `...sel.request` and the echo (`:533-541`). `attemptMove` (`faMove.ts:706-740`) reads NetInfo first (offline: no request, no id, no event, `:711`), mints one id per tap (`:712`; `newAttemptId`, `faMove.ts:679-691`: `crypto.getRandomValues` when present, else `Math.random`, always v4-shaped, since Hermes has no Web Crypto), records `fa_move_write_attempted`, and sends `surface` with the body. `submitMove` (`faMove.ts:189-195`) goes through `apiRequest` with `timeoutMs: FA_MOVE_TIMEOUT_MS` = (76 + 15) × 1000 (`faMove.ts:161-169`; `mobile/src/api/client.ts:482`, `:534`).
- **Connect / Verify** (contract §6). `goConnect` hides the sheet (state kept) and opens `SleeperConnect`, or `EspnConnect` with no `reason: 'send'` (its send copy is about trades), after the slide-out (`ClaimSheet.tsx:427-438`). On the host's next focus (`:382`), `onConnectReturn` (`:356-381`) re-reads the list, bounded at 5 s (`refetchSafe`, `:390-392`; `withTimeout`, `faMove.ts:619-633`), and resumes through `resumeAfterConnect` (`claimSheetPlan.ts:245-256`): a failed re-read goes on as connected (consent or Ready; the server's 409s are the net). It never sends by itself.

## 4. Server order of checks

**Server PR.** Not in this branch.

## 5. Result → held page discarded → Done → FA invalidation

- **The held trade page.** `submitMove` goes through `apiRequest`, whose `_noteWrite` reports the path when the request is sent and when it settles (`client.ts:483`, `:496`). `devicePageStore` discards every held page for any path `discardsDevicePages` names (`mobile/src/state/devicePageStore.ts:150`), which includes the move (`mobile/src/utils/devicePage.ts:256-261`; `check-device-first-page.js` 1k, which also pins devicePage's `FA_MOVE_PATH` equal to `faMove.ts`'s, since importing across them would cycle through `client.ts`; `docs/cross-client-invariants.md` lists it with the other discard triggers). The sheet adds no hook.
- **Codes → states.** `classifyMoveError` (`faMove.ts:566-601`) maps by suffix (`^(sleeper|mfl|espn)_…`, `:494-504`) through `STATE_BY_CODE` (`:525-547`); `write_failed` with a `kind` is state 11. No answer, the timer, status 0 and a 5xx with no usable code are state 12; any other 4xx with an unknown code is the 12-style neutral panel.
- **The sheet** (`applyOutcome`, `ClaimSheet.tsx:555-587`, applying each plan in one place, `apply`, `:590-604`). The plans are pure (`claimSheetPlan.ts`):
  - 200 `complete` / `pending` → the result panel with the server's `title` and `lines` (`planResponse`, `claimSheetPlan.ts:137-150`). A pending claim also marks the Free Agents row "Claim pending" for the app session (`ClaimSheet.tsx:599`; `FreeAgentsScreen.tsx:218`, `:296-300`).
  - `planFailure` (`claimSheetPlan.ts:153-220`):
    - 1 (`feature_disabled`), 14 (`claims_off`) → the hand-off with a line, bid and drop kept (`:163`, `:194`).
    - 3, 4 → the connect / verify step with the server's message, and `fa_move_connect_shown` (`:165-172`). **MFL** (no connect screen) → that platform's `NO_ADD_REASON` in the sheet, for connect, verify and rejected alike, never a Connect button that does nothing.
    - 5 → the consent step with the 409's block, or the hand-off if it has none (`:173`).
    - 10a → the drop list shows **whenever a drop is required**, even when the client saw open slots (`dropListShown`, `:295-298`), with the server's message (focused) and a list refresh (`:177`). 10b clears the stale pick and refreshes (`:184`). 10d recomputes the bid error against the server's `remaining` (`:190`). 10e re-reads the list (bounded) and names the corrected kind with a chalk line (`:192`; `planKindChanged`, `:225-241`).
    - 11 → Ready with a `--neg` "nothing was sent" line above the same named CTA (`:196`; offline is `planNotSent`, `:132-134`). The retry is a fresh tap with a fresh id; a consent the offline tap carried goes with it.
    - 10c, 10f, 10g, 13, 12-style → the result panel with the server's message in `--neg` (`:198-204`). 13 offers Connect again (not on MFL).
    - 12 → "Check before resending", the server's words only for its own codes, Open in Sleeper primary, Done, and **no retry** (`:205-218`; `ClaimSheet.tsx:936-958`).
- **State 7.** Busy from the tap until the outcome is shown (`ClaimSheet.tsx:521-553`). `requestClose` is a no-op while busy, and the backdrop, Cancel and both Modals' `onRequestClose` go through it (`:400-405`, `:663`, `:1025`, `:1087`). The named CTA uses the Button's `loading` (VoiceOver busy), and "still sending" appears at 8 s (`:331`).
- **The pinned block** measures its content (`blockContent`, the same width and height in both parents) and asks `actionBlockPinned`, which adds the pinned chrome back and has hysteresis, so it never flips back and forth at the threshold (`ClaimSheet.tsx:1055-1068`; `claimSheetPlan.ts:303-315`).
- **Done → invalidation.** Every terminal plan carries `refresh`, which invalidates the `['free-agents', leagueId]` prefix (`ClaimSheet.tsx:396-398`, `:597`). That covers both hosts' keys, so the list, the drop list, FAAB and the capability refresh together.

## 6. Withdrawals (Settings)

- **Client half: Settings › Leagues.** One `RosterMovesRow` per platform the user has a league on (`mobile/src/screens/settings/SettingsLeaguesScreen.tsx:55-61`, `:82-84`). Each reads `readConsentStatus` (`faMove.ts:381-390`): 200 `valid: false` when there's no grant (contract §2), and a 404 (an older server) or a 403 `verification_required` (the route needs a verified session) read the same way: no row. It uses `retry: false` (`SettingsLeaguesScreen.tsx:107-112`) and renders nothing unless `valid: true` (`:154`). This client has no request option that keeps that 404 out of `api_request_failed`.
- **Stop roster moves** is one tap, no dialog (`:128-144`): `DELETE`, then the server's `notice` replaces the row verbatim with VoiceOver focus, and the consent and FA queries are invalidated. **A failed DELETE, a 403 `verification_required` included, keeps the row** (the grant stays in force) with "Couldn't turn it off. Try again." (`:140`, `:170-174`).
- **Disconnect, expiry, rejection.** Server PR. The client's side of a rejection is state 13 (item 5).

## 7. Capability computation per platform

**Server PR.** Not in this branch.

## Choices the contract and scope left open

- **Usage Trends reads before it routes**, capped at 3 s, with a busy Add. The read is a plain call outside the cache.
- **`unsupported` on a Sleeper league** (not a value the server sends) keeps the legacy hand-off, because `NO_ADD_REASON` has no Sleeper entry.
- **In-sheet `unsupported`** (MFL's connect / verify / rejected, MFL not connected at open) shows that platform's `NO_ADD_REASON` with only Done. "Do it in {platform} instead" and the result panels' Open buttons are Sleeper-only, since this binary has only Sleeper's opener.
- **A claim while `move.claims` isn't true** is a hand-off before the tap (`faMove.ts:259`), not only after a 422.
- **A priority-waiver claim has no bid**, so it uses `cta_claim_no_bid` / `cta_claim_drop_no_bid` and no `bid_line`. `{bid}` groups thousands ("$1,000"), like the sheet's budget line.
- **`open_platform` is not applied.** #509's "Open in Sleeper to claim" label is pinned literally by `check-sleeper-handoff.js` S2, and the contract's example is the same words.
- **"Do it in Sleeper instead"** switches the sheet to the hand-off with bid and drop kept (consent.md §2.1). The result panels' "Open in Sleeper" opens Sleeper directly.
- **The consent step requires a nameable move.** If `this_move` can't be filled, no consent is asked and the sheet goes to the hand-off.
- **`connect_shown.reason`** is `unknown` for a `connect` value outside the closed set (analytics-lead, round 3; `connectShownReason`, `faMove.ts:415-419`; `ClaimSheet.tsx:1108-1110`); the UI still shows the plain connect step.
- **`consent_shown.reason` when the block has none** is read client-side: a changed `copy_version` → `version`; a Stop roster moves in this app run → `withdrawn`; a known grant no longer valid → `lapsed`; otherwise `first`. An unknown server value is dropped.
- **Legal's links:** a link without a label or an `https://` URL is dropped; with none left, the app's own pages, labelled "Terms" and "Privacy".
- **A connect return whose re-read fails** goes on as connected; a wrong guess is caught by the server's 409 not_linked / expired.
- **"Claim pending" is Free Agents only.** Usage Trends' rows are two components (`UsageTrendCard`'s text button and `UsageStatsTable`'s icon-only cell, kept text-free by `check-usage-trends` 2o), so showing it there is a layout call for design-lead. The store is keyed by league + player, so a Usage Trends claim still marks the Free Agents row.
- **A 2xx the client can't read** is state 12 and records `write_failed {unknown, 200}` (left as is; platforms-eng is telling analytics-lead).
- **testIDs.** The named CTA and the consent step's Make the move are both `fa-claim.make-move` (never on screen together); the result panels' Open in Sleeper reuses `fa-claim.do-in-sleeper`; the in-sheet `NO_ADD_REASON` title reuses `fa-claim.result`.
- **`attempt_id` survives ingest.** It joins `_HEX_ID_PROPS` in `backend/analytics_ingest.py`, like `search_id`, so an id with a 16-digit run isn't scrubbed.
