# Free-agent moves (D1): code-walk, client half

> The scope block's §3 code-walk skeleton (`docs/plans/sleeper-fa-write/scope.md` on `plan/fa-moves-launch`), filled for the dark client in the 11-06 binary on `feat/fa-moves-client` (based on #509 @ `d14b7308`). Items 4 and 7 are the server's and are filled by the server PR. The wire is [contract.md](contract.md) (as of `41c1443e`). Citations are `file:line` on this branch after platforms-eng's review round 10 (release-lead's delta QA of `0168d383`; round 8 was scope §B11, no unchosen $0 claim, contract `a7a2a8f4`) (contract `3248995b`: the consent routes need a verified session; marketing-lead's final fallback copy, addendum 17 §A). Evidence: `mobile/tests/check-fa-move.js` (F1–F17, L1/R1/P1/T7, X1–X12, Y1–Y3, Z1, B1–B3, Q1, P3, round 7's P2A and S1–S5, and round 8's F18 and B11) and the TEST_LEDGER entry of 2026-11-01.
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
- [The merge with #509's sync (`ff175836`)](#the-merge-with-509s-sync-ff175836)
- [§B11: no unchosen $0 claim](#b11-no-unchosen-0-claim)
- [Choices the contract and scope left open](#choices-the-contract-and-scope-left-open)

## Dark-safety: no usable `move` in the FA response

Today's server sends no `move`. Every path below then lands where `d14b7308` does.

- **Nothing of a bad capability is used.** `capabilityOrNull` drops an absent, malformed or unknown-mode `move`, and `submit` with no known `league_platform` (`faMove.ts:214-219`, `:291-293`). With none, `rowMoveFields` drops every row's `move_kind` / `move_mode` / `move_line` (`faMove.ts:297-300`), so `move.copy` and the row's line are never read (review round 2, item 10). The sheet starts from both (`ClaimSheet.tsx:228-229`).
- **The gate says legacy.** `faMoveGate` returns `'legacy'` (`faMove.ts:258`), and `faMoveOpensSheet` is false (`faMove.ts:282-287`).
- **Free Agents routes as before.** `onAdd` opens the sheet iff `faMoveOpensSheet(move, row) || addPlatform === 'sleeper'`, else `explainNoAdd(addPlatform)` (`mobile/src/screens/FreeAgentsScreen.tsx:90-101`). With the first term false, that's `d14b7308`'s test (`d14b7308:mobile/src/screens/FreeAgentsScreen.tsx:78-85`). The Add variant uses the same expression (`FreeAgentsScreen.tsx:218`). Each row's `claimPending` is false: the store behind it is written only from a `submit`-mode pending result (`mobile/src/state/claimsPending.ts:17-32`; `claimSheetPlan.ts:147-160`), so the stats line is the drop line as before (`FreeAgentsScreen.tsx:219`, `:298-302`).
- **Usage Trends routes as before, and never waits.** `doAdd` keeps `resolveAddPlatform(lgId, isDemo)` → `explainNoAdd(platform)` for non-Sleeper and switch-then-open for Sleeper (`mobile/src/screens/UsageTrendsScreen.tsx:321-343`). It reads a league's capability only from the query cache, synchronously, before #509's own awaits (`:329`); nothing is fetched at the tap. The capability is prefetched in the background (below), under its own key, never the sheet's; on today's server it holds `move: null`, so the route is the old one, and the sheet still reads its own list after the switch, as on `d14b7308`. On today's server a visit makes one capability read, the focused league's on mount: the list prefetch waits for a `submit` focus (`faMove.ts:724`).
- **The sheet renders #509's hand-off.** `initialView` gives `{step: 'handoff', line: null}` for `legacy` (`claimSheetPlan.ts:93-114`). `submitLayout` is false (`ClaimSheet.tsx:266`), so the `if (!submitLayout)` render runs (`ClaimSheet.tsx:1109-1134`): header, bid, drop, then `handoffBlock` (`:874-880`), which is #509's CTA (`:664-672`; `fa-claim.open-sleeper`, the same label, `onPress={openSleeper}`, `disabled={bidTooHigh}`) and the footer. Same Modal, backdrop, sheet styles and scroll as `d14b7308:ClaimSheet.tsx:152-327`.
- **What differs in that render, and why.**
  - **The footer's words.** "Sleeper doesn't allow apps to submit claims — finish in Sleeper." (`d14b7308:ClaimSheet.tsx:319-321`) becomes the fallback "You'll finish this move in Sleeper." (`ClaimSheet.tsx:660`), since `move.copy` isn't read without a capability. The old line is false once `submit` is on anywhere; this is specified (scope §C state 1).
  - **Plumbing with today's values.** Cancel, the backdrop and `onRequestClose` go through `requestClose` (`ClaimSheet.tsx:434-439`), which is `onClose` while nothing is sending. Cancel, the bid input and the drop rows take `disabled={busy}` / `editable={!busy}`, always false here. The header text is `` `Claim ${row.name}` `` (`:656-659`). `dropListShown` is #509's expression when no drop has been required (`claimSheetPlan.ts:389-392`). A selected drop that leaves the candidates is cleared (`ClaimSheet.tsx:337`); in the hand-off that's invisible.
  - **No new request.** The sheet makes no call of its own unless the user acts in the `submit` layout.

## 1. Host Add → `move.mode` → sheet, or NO_ADD_REASON

- **Free Agents.** The capability comes from the list's own read (`FreeAgentsScreen.tsx:80`). The tap routes it first (`:93`), keeps the capability as it was at the tap (`:94`) and mounts the sheet with it and a `refetch` (`:236-237`).
- **Usage Trends.** Two background prefetches fill the query cache under `['fa-move-capability', leagueId]`, both through `prefetchLeagueCapability` (`faMove.ts:703-710`: a 60 s staleTime and `retry: false`, so a failure costs one read where the app's default would retry once):
  - **On mount**, and when the focused league changes, the focused league's, for a real Sleeper league session only (`UsageTrendsScreen.tsx:156-159`).
  - **When an availability list opens** (the sheet, or a Version B row expanding), `prefetchCapabilities` (`UsageTrendsScreen.tsx:316-319`, `:435`, `:455`) calls `prefetchListCapabilities` (`faMove.ts:716-729`). It reads nothing unless the focused league's cached capability is `submit` (`:724`), so a dark server, or moves turned off, costs no list reads. Then it asks for at most six of the free-agent leagues, Sleeper first (`:726`).
  - **Deliberate (QA P3-1):** a session focused on an ESPN or MFL league never gets the in-app route on Usage Trends, even for its Sleeper leagues. The mount prefetch is Sleeper-only, so that focus has no cached capability, and the list gate needs a `submit` focus (`:723-724`). This keeps the dark fan-out at one read. Free Agents reads its own list, so it isn't affected.
  - **A failed read isn't cached (QA P3-2).** A prefetch that fails leaves no data in its entry, so the next list open reads that league again: up to the cap of six reads per open, each read once (no retry).

  The cache keeps only `move` and the rows' move_* fields (`readLeagueCapability`, `faMove.ts:681-698`). At the tap, `capabilityAtTap` (`faMove.ts:734-739`) hands back a cached capability only if it's under 5 minutes old and hasn't been invalidated since (Stop roster moves, a terminal sheet result, or moves or claims going off, item 5). That one routes by `move.mode` first; anything else routes the legacy way at once (`UsageTrendsScreen.tsx:329-334`; `capabilityForRow`, `faMove.ts:750-756`). Then it switches league and opens the sheet with the row's fields, the capability and the tapped league's name (`UsageTrendsScreen.tsx:335-342`, `:740-742`). There's no busy wait and no spinner.
- **`move.mode` first.** In `submit` mode every step opens the sheet on any platform except MFL without a connection (`faMoveOpensSheet`, `faMove.ts:282-287`), so MFL and ESPN open it in Update 1 with no build. A **held row** (`move_mode: 'handoff'`) opens it too, also on ESPN/MFL, where it shows the server's `move_line` (fallback: "This move can't be made from Fleeced right now. Check ESPN.") rather than `NO_ADD_REASON`'s read-only text (`claimSheetPlan.ts:107-110`). `unsupported` on a non-Sleeper league is today's `NO_ADD_REASON` alert, byte for byte (`ClaimSheet.tsx:125-158`, unchanged; `check-sleeper-handoff.js` S9).

## 2. `faMoveGate` → connect, verify, consent or submit

`faMove.ts:250-275`, in order:

1. No usable capability → `legacy` (`:258`).
2. `unsupported` → `unsupported`; `handoff` → `handoff` (`:259-260`).
3. `submit`, not connected, on a platform with no connect screen in this binary (MFL) → `unsupported` (contract §6; `:262-264`).
4. A held row (any `move_mode`) → `handoff` (`:267`). A `claim` row while `move.claims` isn't true → `handoff`, state 14 before the tap (`:270`).
5. `expired` / `unverified` → `verify`; anything else but `ok`, including `other_account` and unknown values → `connect` (`:271-272`). Connect and verify beat consent.
6. Consent valid → `submit`; ticked → `submit_with_consent`; otherwise `consent` (`:273-274`). An unticked box never submits.

The sheet's first view follows the gate (`initialView`, `claimSheetPlan.ts:93-114`): connect/verify with the server's line, Ready for every submit step (consent is asked at the tap), MFL's `unsupported` as that platform's `NO_ADD_REASON` inside the sheet (`claimSheetPlan.ts:103-106`; rendered at `ClaimSheet.tsx:1066-1079` with only Done, `:1019-1020`). Back from the connect screen, `connectReturnStep` picks where to resume (`claimSheetPlan.ts:316-328`). A failed sign-in returns to the same step. Consent comes next only when the gate says consent and no bid is missing. Otherwise the sheet goes to Ready, where a FAAB claim with an empty bid shows rule 1's line (§B11 below).

## 3. Consent GET → step → POST …/move with `consent` (client half)

- **The selection.** `moveSelection` is the one source for the named CTA, the waiver lines and the request: the drop only while it's still in the candidates, and a claim's bid (what was typed, `0` included; **none for an empty field**, so no `faab_bid` is sent and the CTA is disabled, §B11 below; none in a priority-waiver league) (`claimSheetPlan.ts:350-385`; `ClaimSheet.tsx:298-309`). The CTA comes from `moveCtaLabel` with contract §7's no-bid claim slots (`faMove.ts:966-983`), and a claim's lines from `waiverLines`: `waiver_line` with a drop, `waiver_line_no_drop` without, then `bid_line` only with a bid (`faMove.ts:987-995`; `ClaimSheet.tsx:915`).
- **The league, named (R28.26, D10(a)).** The ready step always shows the server's `league_line` or, with it absent, "In {league}" beside the named CTA, in every state that shows the CTA (6, and 10a/10b/10d/10e/11 inline) (`ClaimSheet.tsx:892-893`). The name comes from the host first (`leagueName` prop: Free Agents' session league, `mobile/src/screens/FreeAgentsScreen.tsx:238`; the tapped league in Usage Trends, `mobile/src/screens/UsageTrendsScreen.tsx:742`), then the session's league list (`ClaimSheet.tsx:218`). A move whose league can't be named gets no named CTA: the hand-off instead.
- **One consent read at a time.** `openConsent` is guarded by a ref, so a same-frame double tap (before `busy` renders) can't fire two consent GETs, or two sends after them (`ClaimSheet.tsx:489`); `send` has its own ref (`sendingRef`).
- **The tap.** `onNamedCta` asks the gate with `consent_until` against now (`ClaimSheet.tsx:548-560`). `consent` → `openConsent(true)` (`:486-520`), which reads through `fetchConsentStep` (`faMove.ts:377-393`): **NetInfo first**, so offline sends no GET; offline, or a GET that fails at the network level (status 0, the timer), is state 11 with nothing sent (`planNotSent`, `claimSheetPlan.ts:142-144`, whose line names no platform, since it's Fleeced's server that wasn't reached: the server's `offline_line` slot when the capability carries one, else "Couldn't connect right now, so nothing was sent.", `faMove.ts:913`); `valid` sends (the capability was stale); a block shows the step; a 403 `verification_required` (the route needs a verified session, contract §2) is state 4, Verify, through the same `planFailure` as the move route's 403 (`ClaimSheet.tsx:507-509`); any other server failure, a 404 or an incomplete block is F4's hand-off with `unavailable_line`.
- **The step.** `showConsent` (`ClaimSheet.tsx:522-545`) unticks every time, shows "terms changed" when the block's `reason` is `version` or this sheet showed another `copy_version` (`termsChanged`, `faMove.ts:417-419`; `ClaimSheet.tsx:525`), reports the block's own `reason` when it sends one (`consentShownReason`, `faMove.ts:465-471`; `ClaimSheet.tsx:527`, `:544`), and refuses to ask consent for a move it can't name (`:535`). The body is the server's `title`, paragraphs and `this_move` filled with the same `ctaLabel` (`:1048-1065`). The pinned block holds the **unticked** box (`:964`), Make the move with the server's `button_label`, disabled until ticked, with a VoiceOver hint (`:980`), Not now (`:991`), Do it in Sleeper instead, and legal's links row: the block's `links` (https only), else the app's Terms and Privacy built from `getBaseUrl()` like PaywallScreen's `openLegal` (`consentLinks`, `faMove.ts:349-361`; `ClaimSheet.tsx:1001-1016`), each opened through `openPlatform` with no catch (`:451-453`).
- **The send.** `send` re-asks the gate and returns unless it says `submit` / `submit_with_consent` (`ClaimSheet.tsx:564-572`), then calls `attemptMove` once with `...sel.request` and the echo (`:578-585`). `attemptMove` (`faMove.ts:814-848`) reads NetInfo first (offline: no request, no id, no event, `:819`), mints one id per tap (`:820`; `newAttemptId`, `faMove.ts:787-799`: `crypto.getRandomValues` when present, else `Math.random`, always v4-shaped, since Hermes has no Web Crypto), records `fa_move_write_attempted`, and sends `surface` with the body. `submitMove` (`faMove.ts:198-204`) goes through `apiRequest` with `timeoutMs: FA_MOVE_TIMEOUT_MS` = (76 + 15) × 1000 (`faMove.ts:167-175`; `mobile/src/api/client.ts:660`, `:712`).
- **Connect / Verify** (contract §6). `goConnect` hides the sheet (state kept) and opens `SleeperConnect`, or `EspnConnect` with no `reason: 'send'` (its send copy is about trades), after the slide-out (`ClaimSheet.tsx:462-473`). On the host's next focus (`:413`), `onConnectReturn` (`:386-412`) re-reads the list, bounded at 5 s (`refetchSafe`, `:421-423`; `withTimeout`, `faMove.ts:640-654`), and resumes through `resumeAfterConnect` (`claimSheetPlan.ts:332-343`): a failed re-read goes on as connected (consent or Ready; the server's 409s are the net). It never sends by itself.

## 4. Server order of checks

**Server PR.** Not in this branch.

## 5. Result → held page discarded → Done → FA invalidation

- **The held trade page.** `submitMove` goes through `apiRequest`, whose `_noteWrite` reports the path when the request is sent and when it settles (`client.ts:661`, `:674`). `devicePageStore` discards every held page for any path `discardsDevicePages` names (`mobile/src/state/devicePageStore.ts:150`), which includes the move (`mobile/src/utils/devicePage.ts:256-261`; `check-device-first-page.js` 1k, which also pins devicePage's `FA_MOVE_PATH` equal to `faMove.ts`'s, since importing across them would cycle through `client.ts`; `docs/cross-client-invariants.md` lists it with the other discard triggers). The sheet adds no hook.
- **Codes → states.** `classifyMoveError` (`faMove.ts:589-624`) maps by suffix (`^(sleeper|mfl|espn)_…`, `:517-527`) through `STATE_BY_CODE` (`:548-570`); `write_failed` with a `kind` is state 11. No answer, the timer, status 0 and a 5xx with no usable code are state 12; any other 4xx with an unknown code is the 12-style neutral panel.
- **The sheet** (`applyOutcome`, `ClaimSheet.tsx:597-631`, applying each plan in one place, `apply`, `:634-653`). The plans are pure (`claimSheetPlan.ts`):
  - 200 `complete` / `pending` → the result panel with the server's `title` and `lines` (`planResponse`, `claimSheetPlan.ts:147-160`). A pending claim also marks the Free Agents row "Claim pending" for the app session (`ClaimSheet.tsx:648`; `FreeAgentsScreen.tsx:219`, `:298-302`).
  - `planFailure` (`claimSheetPlan.ts:163-255`):
    - 1 (`feature_disabled`), 14 (`claims_off`) → the hand-off with a line, bid and drop kept (`:180`, `:211`).
    - 3, 4 → the connect / verify step with the server's message, and `fa_move_connect_shown` (`:182-189`). **MFL** (no connect screen) → that platform's `NO_ADD_REASON` in the sheet, for connect, verify and rejected alike, never a Connect button that does nothing.
    - 5 → the consent step with the 409's block, or the hand-off if it has none (`:190`).
    - 10a → the drop list shows **whenever a drop is required**, even when the client saw open slots (`dropListShown`, `:389-392`), with the server's message (focused) and a list refresh (`:194`). 10b clears the stale pick and refreshes (`:201`). 10d recomputes the bid error against the server's `remaining` (`:207`). 10e re-reads the list (bounded) and names the corrected kind with a chalk line, which an add that became a claim on a FAAB league puts directly above the empty bid field (§B11 below) (`:209`; `planKindChanged`, `:263-296`).
    - 11 → Ready with a `--neg` "nothing was sent" line above the same named CTA (`:213`; offline is `planNotSent`, `:142-144`). The retry is a fresh tap with a fresh id; a consent the offline tap carried goes with it.
    - 400 / an unrecognised 4xx → contract §4's **neutral** panel: the server's own words, dim, no "wasn't made" refusal title, no retry (`claimSheetPlan.ts:219`). The one exception is a 400 `bad_request` to a FAAB claim sent without `faab_bid`, which returns to Ready (§B11 rule 5, below).
    - 10c, 10f, 10g, 13 → the result panel with the server's message in `--neg` (`:215-239`). 13 offers Connect again (not on MFL).
    - 12 → "Check before resending", the server's words only for its own codes, Open in Sleeper primary, Done, and **no retry** (`:240-253`; `ClaimSheet.tsx:1021-1043`).
- **State 7.** Busy from the tap until the outcome is shown (`ClaimSheet.tsx:564-595`). `requestClose` is a no-op while busy, and the backdrop, Cancel and both Modals' `onRequestClose` go through it (`:434-439`, `:712`, `:1111`, `:1173`). The named CTA and Make the move take `loading={busy}`, never `disabled` for busy (`:907`, `:982`): #364's busy rule, with its Button ported (`mobile/src/components/chalkline/Button.tsx:80`, only `disabled` dims), so a working button keeps full brightness with its spinner, takes no tap and reads busy to VoiceOver; `onNamedCta` and `send` also ignore taps while busy. "Still sending" appears at 8 s (`ClaimSheet.tsx:346`).
- **Accessibility.** "Still sending…" is announced when it appears (`ClaimSheet.tsx:349`); the window line's **Turn off** is its own button, not nested text, and dims while sending like Cancel and "Do it in Sleeper instead" (`:929-936`, at the chalkline Button's disabled opacity, `:1358`); on 10d the bid error takes VoiceOver focus each time the server's budget answer changes it (`:367`, `:753`). Settings announces the failed-DELETE line (`SettingsLeaguesScreen.tsx:151`), since iOS ignores `accessibilityLiveRegion`.
- **The pinned block** measures its content (`blockContent`, the same width and height in both parents) and asks `actionBlockPinned`, which adds the pinned chrome back and has hysteresis, so it never flips back and forth at the threshold (`ClaimSheet.tsx:1141-1154`; `claimSheetPlan.ts:397-409`).
- **"Nothing was sent" only when provable (R28.27, G15).** Only state 11 says it: `offline_line` (offline at the tap, a consent GET with no answer: Fleeced wasn't reached) and `not_sent_line` ("Couldn't reach {platform}…", the server's 502 with a `kind`) are the only fallbacks with those words. 10f (the platform refused) and 13 (connection rejected) never do, since the platform received the request: their fallback title is "This move wasn't made" and their lines are the server's own. `check-fa-move` B3 checks every failure state's fallback text.
- **Done → invalidation.** Every terminal plan carries `refresh`, which invalidates the `['free-agents', leagueId]` prefix (`ClaimSheet.tsx:429-432`, `:644`). That covers both hosts' keys, so the list, the drop list, FAAB and the capability refresh together. It also invalidates Usage Trends' `['fa-move-capability']` prefix (`:431`; `invalidateCapabilities`, `faMove.ts:744-746`). That only marks the entries stale and re-reads nothing, so the next Add there routes the legacy way until a prefetch reads them again. Some outcomes mean moves or claims went off server-side, and they invalidate the same prefix without refreshing the list (`staleCapability`; QA P3-3):
  - a 404 `feature_disabled` (`claimSheetPlan.ts:181`);
  - state 14's 422 `waiver_claim_unsupported` (`:212`);
  - a 10e whose re-read lands on the hand-off: a claim while claims are off, or a held row (`:295`).

  The sheet applies them at `ClaimSheet.tsx:646` and `:629`.

## 6. Withdrawals (Settings)

- **Client half: Settings › Leagues.** One `RosterMovesRow` per platform the user has a league on (`mobile/src/screens/settings/SettingsLeaguesScreen.tsx:61-67`, `:88-90`). Each reads `readConsentStatus` (`faMove.ts:402-413`): 200 `valid: false` when there's no grant (contract §2), and a 404 (an older server) or a 403 `verification_required` (the route needs a verified session) read the same way: no row. It uses `retry: false` (`SettingsLeaguesScreen.tsx:114-119`) and renders nothing unless `valid: true` (`:165`). The read opts into the shared client's `quietStatuses: [403, 404]` (`faMove.ts:397`; `mobile/src/api/client.ts:666`), so those routine answers on a dark or unverified visit emit no `api_request_failed`; a 500 still does.
- **Stop roster moves** is one tap, no dialog (`SettingsLeaguesScreen.tsx:135-155`): `DELETE`, then the server's `notice` replaces the row verbatim with VoiceOver focus, and the consent and FA queries are invalidated, along with Usage Trends' `['fa-move-capability']` prefix (`:147`; nothing on a failed DELETE). **A failed DELETE, a 403 `verification_required` included, keeps the row** (the grant stays in force) with "Couldn't turn off roster moves. Try again." (marketing A3.9) (`:149`, `:181-185`).
- **Disconnect, expiry, rejection.** Server PR. The client's side of a rejection is state 13 (item 5).

## 7. Capability computation per platform

**Server PR.** Not in this branch.

## The merge with #509's sync (`ff175836`)

#509's sync brought #528, #379 and `main` @ `fd5390ac` into this branch. Two of its rules touch D1:

- **The paywall gate's `background` option.** A user-initiated call's 402 or 403 can open the paywall or the VerifySheet. A call with `background: true` opens nothing: its caller gets the rejection as before (`mobile/src/api/client.ts:558`, `:671`, `:394`). D1's two reads that no tap makes both pass it:
  - Settings' roster-moves consent read (`readConsentStatus`, `faMove.ts:406`, beside its `quietStatuses`);
  - the capability prefetch (`readLeagueCapability`, `faMove.ts:686`).

  `check-paywall-gate` 8b's `BACKGROUND_SET` lists both, and a third `background: true` anywhere in `mobile/src` fails it. The quiet guard in `apiRequest`'s catch is one guarded `_reportApiFailure` call (`client.ts:666-667`), the shape main's 2a pins; `check-fa-move` Q1 follows it.
- **9g's placeholder ban, narrowed.** `check-paywall-gate` 9g bans a raw `{inviter}` or `{league}` anywhere in `mobile/src`, so the invitee template can't leak. `api/faMove.ts` fills its own contract §7 templates, whose vocabulary includes `{league}` (`league_line`, `other_account_line`). 9g exempts `{league}` in that one file only; the invitee template and `{inviter}` stay banned there too (platforms-eng's sabotage: an `{inviter}` in `faMove.ts` turns 9g red).

## §B11: no unchosen $0 claim

Scope §B11 on `plan/fa-moves-launch` @ `973f8854` (head-product's view, ux-lead's edits; pending the operator's approval), contract `a7a2a8f4`. The app never submits a $0 claim the user didn't choose. Evidence: `check-fa-move` F18 ×6 and B11 ×3, executed against `claimSheetPlan`, with 16 sabotages (TEST_LEDGER).

- **Rule 6, the source.**
  - `moveSelection` reads an empty field as **no bid**: `bid: null` and no `faab_bid` (`mobile/src/utils/claimSheetPlan.ts:371`). A typed `0` is a bid. An add, or a priority-waiver claim, never has a bid.
  - The CTA gate is `needsBid = kind === 'claim' && faab && bid === null` (`:376`).
  - The request is built from the same selection (`mobile/src/components/ClaimSheet.tsx:579-585`), so an empty field never sends `faab_bid`.
  - `has_bid` is `body.faab_bid != null` (`mobile/src/api/faMove.ts:825`): false for an empty field, and no bid amount is ever logged.
- **Rule 1, any FAAB claim with an empty field.**
  - The named CTA is disabled (`ClaimSheet.tsx:908`), and so is the consent step's Make the move (`:983`, a backstop: consent is never entered without a bid, below). `onNamedCta` also returns first while a bid is needed (`:550`).
  - `send` returns before `attemptMove` while `needsBid` (`:574`), a second guard behind the disabled buttons.
  - The label is `moveCtaLabel`'s no-amount slot, "Claim A" / "Claim A, drop B", because `{bid}` has no value (`faMove.ts:966-983`). Typing re-renders it: "Claim A for $0" at `0`.
  - The CTA's VoiceOver hint is "Enter a bid to claim" (`bid_hint`, G26, `faMove.ts:928`; `ClaimSheet.tsx:909`). The Button has no live region.
  - A visible line sits under the field **on Ready**: the server's `bid_needed_line`, else "Enter a bid. $0 is allowed." (G25, `faMove.ts:897`). Both strings are marked PENDING MARKETING.
    - `bidLineShown` decides it (`claimSheetPlan.ts:306-308`; `ClaimSheet.tsx:314`, `:760-764`).
    - It never shows on the consent step, because that step's body replaces the bid field.
    - It lives only in the FAAB branch of the bid section, never the priority-waiver one (release-lead's P3-1).
  - **The consent step is only ever reached with a bid in hand** (release-lead's P2-B). The likely path for a first FAAB claim: not linked, empty bid → Connect → sign in → back.
    - The connect return asks `connectReturnStep` (`claimSheetPlan.ts:316-328`; `ClaimSheet.tsx:401-411`). A FAAB claim with an empty field resumes at **Ready** with the line, not consent (`:326`).
    - Once a bid is typed, the enabled named CTA opens consent as usual.
    - The only other way into consent is that named CTA, after its bid guard. The consent 409 comes only after a send, and a send needs a bid.
  - A spent budget needs nothing special: `bidTooHigh` is `bid > remaining`, so $0 of $0 is allowed (`ClaimSheet.tsx:280`).
- **Rule 2, 10e add → claim.**
  - `planKindChanged` returns Ready with the 10e line as `bidNotice` when the corrected kind is a claim on a FAAB league (`claimSheetPlan.ts:286-293`). Otherwise the line stays above the CTA, so a priority-waiver league is unchanged (rule 4).
  - The field shows because a claim shows it (`bidApplies`, `ClaimSheet.tsx:292`). It is empty after an add, since nothing on the 10e path sets the bid.
  - The line renders directly above the field, after the section label (`ClaimSheet.tsx:721-732`). `show` bumps `viewSeq`, and the step's focus effect calls `setAccessibilityFocus` on it (`:356-360`).
  - The field is in the scrolling body and the CTA is in the pinned block after it, so the reading order is the line, the field, then the CTA.
  - The bid `TextInput` has no `ref` and no `autoFocus`, and ClaimSheet calls no `.focus()`, so the number pad never covers the CTA.
- **Rule 3, 10e claim → add.**
  - `bidApplies` is false, so the field hides; its value stays in `bid` state, which only the field's own `onChangeText` writes (`ClaimSheet.tsx:737`).
  - `moveSelection` names "Add A" and sends no `faab_bid`. A flip back restores the typed bid in both the label and the request.
- **Rule 5, the server's 400.**
  - `send` judges the request it actually sent with `faabClaimWithoutBid` (`claimSheetPlan.ts:164-166`; `ClaimSheet.tsx:590`), and `applyOutcome` passes it to `planFailure` (`:610`).
  - A 400 `bad_request` to such a claim returns `{step: 'ready', bidNeededFocus: true}` (`claimSheetPlan.ts:224-226`). That means claim mode, the empty field, rule 1's line with focus and the disabled CTA. There is no refresh, no retry button and no error screen.
  - Every other 400 is still the neutral panel. It should be unreachable, since the client never sends that claim.
- **Known limits** (left as is, release-lead's QA of `0168d383`):
  - **P3-2:** the bid field's digits-only filter is #509's (`ClaimSheet.tsx:737`), and the number pad can't type "." or "-", so a fractional or negative bid can't be entered.
  - **P3-3:** rule 5 needs the client to know the league is FAAB (`faab`, from the host's `waivers`). A FAAB league the client read as priority-waiver would get the neutral panel for that 400 instead of Ready. That's rare, and the request is still never sent with a $0 the user didn't choose.

## Choices the contract and scope left open

- **Usage Trends routes from the cache only** (release-lead's QA, round 6): a capability prefetched when an availability list opened, or the focused league's, prefetched once on mount and on a focus change for a real Sleeper league session (never demo, local or no league; round 6b, `mobile/src/screens/UsageTrendsScreen.tsx:156-159`). An Add on a league whose read hasn't come back yet gets the #509 hand-off or alert at once. So does one whose cached entry is over 5 minutes old or invalidated (round 7). The list prefetch is gated and capped (round 7, release-lead's P2-A). Unbounded, one opened list made a read per free-agent league (13 for 14 leagues, each a live Sleeper rosters GET on the server), retried once on failure. Now nothing is read until the focused league is `submit`, then at most six leagues, Sleeper first, with no retry. Six is release-lead's number. Its availability sheet's footer reads "Add opens a quick check before the move. Trade opens the trade finder in that league." (marketing A1).
- **The fallback copy is marketing's final** (addendum 17 §A): the finality, waiver and bid lines are legal's with `{platform}` filled ("Final on {platform}. Fleeced can't undo it."; "This places a waiver claim for {add} (dropping {drop} if it clears). {platform} processes it on its waiver schedule."; "Bid: {bid}"); the window line reads "Roster moves: on until {date}"; the added-result title is "Done". `check-fa-move` Z1 pins every changed string verbatim.
- **`unsupported` on a Sleeper league** (not a value the server sends) keeps the legacy hand-off, because `NO_ADD_REASON` has no Sleeper entry.
- **In-sheet `unsupported`** (MFL's connect / verify / rejected, MFL not connected at open) shows that platform's `NO_ADD_REASON` with only Done. "Do it in {platform} instead" and the result panels' Open buttons are Sleeper-only, since this binary has only Sleeper's opener.
- **Any per-row `move_mode`** (not only exactly `'handoff'`, e.g. `'HANDOFF'`) holds the row in hand-off (`faMove.ts:267`): the conservative reading. A `consent_until` that isn't an ISO string (a number, say) is not a grant (`faMove.ts:303`).
- **Legal's links are per link:** Terms and Privacy are always both present, the server's valid one where it sent one, else the app's own (`consentLinks`, `faMove.ts:349`). A server link takes Fleeced's slot only by its exact label, "Terms" or "Privacy", trimmed and in any case (`:357`; round 7). A "Sleeper terms" link, or a URL that merely contains `/terms`, follows them as an extra link.
- **`open_platform` is reserved and unread** in this binary; the hand-off CTA keeps #509's approved literal (pinned by `check-sleeper-handoff.js` S2).
- **A claim while `move.claims` isn't true** is a hand-off before the tap (`faMove.ts:270`), not only after a 422.
- **A priority-waiver claim has no bid**, so it uses `cta_claim_no_bid` / `cta_claim_drop_no_bid` and no `bid_line`. `{bid}` groups thousands ("$1,000"), like the sheet's budget line.
- **"Do it in Sleeper instead"** switches the sheet to the hand-off with bid and drop kept (consent.md §2.1). The result panels' "Open in Sleeper" opens Sleeper directly.
- **The consent step requires a nameable move.** If `this_move` can't be filled, no consent is asked and the sheet goes to the hand-off.
- **`connect_shown.reason`** is `unknown` for a `connect` value outside the closed set (analytics-lead, round 3; `connectShownReason`, `faMove.ts:438-442`; `ClaimSheet.tsx:1194-1196`); the UI still shows the plain connect step.
- **`consent_shown.reason` when the block has none** is read client-side: a changed `copy_version` → `version`; a Stop roster moves in this app run → `withdrawn`; a known grant no longer valid → `lapsed`; otherwise `first`. An unknown server value is dropped.
- **Legal's links:** a link without a label or an `https://` URL is dropped; Terms and Privacy are then filled per link from the app's own pages, labelled "Terms" and "Privacy".
- **A connect return whose re-read fails** goes on as connected; a wrong guess is caught by the server's 409 not_linked / expired.
- **"Claim pending" is Free Agents only.** Usage Trends' rows are two components (`UsageTrendCard`'s text button and `UsageStatsTable`'s icon-only cell, kept text-free by `check-usage-trends` 2o), so showing it there is a layout call for design-lead. The store is keyed by league + player, so a Usage Trends claim still marks the Free Agents row.
- **A 2xx the client can't read** is state 12 and records `write_failed {unknown, 200}` (left as is; platforms-eng is telling analytics-lead).
- **testIDs.** The named CTA and the consent step's Make the move are both `fa-claim.make-move` (never on screen together); the result panels' Open in Sleeper reuses `fa-claim.do-in-sleeper`; the in-sheet `NO_ADD_REASON` title reuses `fa-claim.result`.
- **`attempt_id` survives ingest.** It joins `_HEX_ID_PROPS` in `backend/analytics_ingest.py`, like `search_id`, so an id with a 16-digit run isn't scrubbed.
