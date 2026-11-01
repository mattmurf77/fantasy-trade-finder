# Free-agent moves (D1): code-walk, client half

> The scope block's §3 code-walk skeleton (`docs/plans/sleeper-fa-write/scope.md` on `plan/fa-moves-launch`), filled for the dark client in the 11-06 binary on `feat/fa-moves-client` (based on #509 @ `d14b7308`). Items 4 and 7 are the server's and are filled by the server PR. The wire is [contract.md](contract.md). Citations are `file:line` on this branch. Written 2026-11-01 by a platforms-eng build worker; evidence is `mobile/tests/check-fa-move.js` (F1–F17) and the TEST_LEDGER entry of the same date.

## Contents

- [Dark-safety: no `move` in the FA response](#dark-safety-no-move-in-the-fa-response)
- [1. Host Add → `move.mode` → sheet, or NO_ADD_REASON](#1-host-add--movemode--sheet-or-no_add_reason)
- [2. `faMoveGate` → connect, verify, consent or submit](#2-famovegate--connect-verify-consent-or-submit)
- [3. Consent GET → step → POST …/move with `consent` (client half)](#3-consent-get--step--post-move-with-consent-client-half)
- [4. Server order of checks](#4-server-order-of-checks)
- [5. Result → held page discarded → Done → FA invalidation](#5-result--held-page-discarded--done--fa-invalidation)
- [6. Withdrawals (Settings)](#6-withdrawals-settings)
- [7. Capability computation per platform](#7-capability-computation-per-platform)
- [Choices the contract and scope left open](#choices-the-contract-and-scope-left-open)

## Dark-safety: no `move` in the FA response

Today's server sends no `move`. Every path below then lands where `d14b7308` does.

- **The gate says legacy.** `faMoveGate` returns `'legacy'` for an absent, malformed or unknown-mode `move`, and for `submit` with no known `league_platform` (`mobile/src/api/faMove.ts:190-195`, `:231`). `faMoveOpensSheet` is then false (`faMove.ts:253-256`).
- **Free Agents routes as before.** `onAdd` opens the sheet iff `faMoveOpensSheet(move, row) || addPlatform === 'sleeper'`, else `explainNoAdd(addPlatform)` (`mobile/src/screens/FreeAgentsScreen.tsx:85-96`). With the first term false, that is `d14b7308`'s `addPlatform === 'sleeper'` test (`d14b7308:mobile/src/screens/FreeAgentsScreen.tsx:78-85`). The Add button's variant uses the same expression (`FreeAgentsScreen.tsx:213`), so it is `secondary` exactly where `canDeepLink` was.
- **Usage Trends routes as before, one read earlier.** `doAdd` keeps `resolveAddPlatform(lgId, isDemo)` → `explainNoAdd(platform)` for non-Sleeper and switch-then-open for Sleeper (`mobile/src/screens/UsageTrendsScreen.tsx:307-335`). **The one difference:** the FA read the sheet used to make right after opening now happens before routing, under the sheet's own query key (`UsageTrendsScreen.tsx:295-305`), in parallel with the 450 ms availability-sheet close, capped at `CAPABILITY_WAIT_MS` = 3 s (`:89`). With no `move` in the answer, or no answer in 3 s, the route is the old one. The sheet then opens with bid and drop already filled instead of filling in after.
- **The sheet renders #509's hand-off.** It starts from the host's capability (`mobile/src/components/ClaimSheet.tsx:223`); with none, `initialView` gives `{step: 'handoff'}` (`:1122-1135`) and `submitLayout` is false (`:264`), so the `if (!submitLayout)` render runs (`:1043-1068`): header, bid, drop, then `handoffBlock` (`:864-870`), which is #509's CTA (`:671-679`; `fa-claim.open-sleeper`, the same label, `onPress={openSleeper}`, `disabled={bidTooHigh}`) and the footer. Same Modal, backdrop, sheet styles and scroll as `d14b7308:ClaimSheet.tsx:152-327`.
- **What differs in that render, and why.**
  - **The footer's words.** `d14b7308`'s "Sleeper doesn't allow apps to submit claims — finish in Sleeper." (`d14b7308:ClaimSheet.tsx:319-321`) becomes the `handoff_footer` slot, whose fallback is "You'll finish this move in Sleeper." (`ClaimSheet.tsx:667`, `faMove.ts:579-613`). The old line is false once `submit` is on anywhere, and this binary outlives the flip (scope §C state 1, ux-lead's state-1 verdict). `check-fa-move.js` pins that the old string is gone from `mobile/src`.
  - **Plumbing with today's values.** Cancel, the backdrop and `onRequestClose` go through `requestClose` (`:411-416`), which is `onClose` while nothing is sending. Cancel, the bid input and the drop rows take `disabled={busy}` / `editable={!busy}`, and `busy` is always false in this render. The header text is `` `Claim ${row.name}` `` (`:663-666`), the same words.
  - **No new request.** The sheet makes no call of its own unless the user acts in the `submit` layout (connect, the named CTA). The hooks it adds (`useNavigation`, `useQueryClient`, a focus listener gated by `awaitingConnectRef`) do nothing here.

## 1. Host Add → `move.mode` → sheet, or NO_ADD_REASON

- **Free Agents.** The capability comes from the same read as the list (`FreeAgentsScreen.tsx:78`). The Add tap routes it first (`:88`), stores the capability as it was at the tap (`:89`) and mounts the sheet with it, plus a `refetch` for the sheet's own re-reads (`:230-231`).
- **Usage Trends.** The tapped league's FA read gives the capability and the player's row (`UsageTrendsScreen.tsx:312-316`). A non-Sleeper league whose capability doesn't open the in-app flow gets `explainNoAdd` (`:317-320`). Otherwise the league is switched and the sheet opens with the row's `move_kind` / `move_mode` / `move_line` and the capability (`:321-335`, `:728-729`).
- **`move.mode` first.** `faMoveOpensSheet` is true for every `submit` step (connect, verify, consent, submit) on any platform, so MFL and ESPN leagues open the sheet in Update 1 with no build (`faMove.ts:253-256`). `unsupported` and `handoff` fall back to `resolveAddPlatform`: `unsupported` on a non-Sleeper league is today's `NO_ADD_REASON` alert, byte for byte (`ClaimSheet.tsx:67-103`, unchanged; `check-sleeper-handoff.js` S9), and `handoff` on a Sleeper league is the sheet in hand-off.
- **Per-row override.** `move_mode: 'handoff'` holds the row in the hand-off with the server's `move_line` (`faMove.ts:238`, `ClaimSheet.tsx:1134`).

## 2. `faMoveGate` → connect, verify, consent or submit

`faMove.ts:223-246`, in order:

1. No usable capability → `legacy` (`:231`).
2. `unsupported` → `unsupported`; `handoff` → `handoff` (`:232-233`).
3. `submit`, not connected, on a platform with no connect screen in this binary (MFL) → `unsupported` (contract §6; `:234-237`).
4. The row is held → `handoff` (`:238`). A `claim` row while `move.claims` isn't true → `handoff`, state 14 before the tap (`:241`).
5. `expired` / `unverified` → `verify`; any other value but `ok` (including `other_account` and unknown values) → `connect` (`:242-243`). So connect and verify beat consent.
6. Consent valid → `submit`; ticked → `submit_with_consent`; otherwise `consent` (`:244-245`). An unticked box never submits.

The sheet's first view follows the gate (`ClaimSheet.tsx:1122-1138`): connect/verify open on that step with the server's line (or `other_account_line`), and every submit step opens on Ready. Consent is asked at the tap, not at open (scope §C state 5).

## 3. Consent GET → step → POST …/move with `consent` (client half)

- **The tap.** The named CTA is `ctaLabel` (`ClaimSheet.tsx:300-305`) from `moveCtaLabel` (`faMove.ts:639-653`): the server's `cta_*` template for the row's `move_kind`, filled with the add, the drop and a claim's `$bid`, else the neutral fallback. It's rendered in the pinned block (`ClaimSheet.tsx:885-894`) and disabled while busy, while a full roster has no drop, or for a claim whose bid is too high.
- **Consent needed.** `onNamedCta` asks the gate with `consent_until` against now (`:498-509`). `consent` → `openConsent(true)` (`:451-472`): `GET /api/platform-write-consent?platform=` (`faMove.ts:158-160`). If the server says `valid`, the tap sends (the capability was stale). If it returns no complete consent block (`readConsentBlock`, `faMove.ts:267-285`) or fails, the sheet goes to the hand-off with `unavailable_line` (`ClaimSheet.tsx:470`, F4). Otherwise `showConsent` (`:474-495`).
- **The step.** Its body is the server's `title`, `body` paragraphs and `this_move` filled with the same `ctaLabel` and the league (`:997-1014`). The pinned block holds the **unticked** box (`:932-945`; ticking only toggles), Make the move with the server's `button_label`, disabled until ticked, with a VoiceOver hint (`:947-955`), Not now (back to Ready, bid and drop as they were, `:957-966`) and Do it in Sleeper instead. `showConsent` unticks every time and adds a "terms changed" line when the `copy_version` differs from the last one shown (F5, `:476`, `:489-493`).
- **The send.** Make the move calls `send(consentEcho(view.block), false)` (`:954`). `consentEcho` returns exactly the received `{copy_version, locale}` (`faMove.ts:288-290`). `send` re-asks the gate and returns unless it says `submit` / `submit_with_consent` (`ClaimSheet.tsx:513-521`), then calls `attemptMove` once (`:525-536`), the only call site.
- **`attemptMove`** (`faMove.ts:515-549`): NetInfo first; offline returns `{sent: false}` with no request, no `attempt_id` and no event (`:520`, F17). Otherwise one `uuidv4()` per tap (`:521`), `fa_move_write_attempted` (`:523-529`), then `submitMove` (`:174-180`): `apiRequest` with `timeoutMs: FA_MOVE_TIMEOUT_MS` = (76 + 15) × 1000 (`:146-154`), through the shared client's per-call timeout (`mobile/src/api/client.ts:482`, `:534`).
- **Connect / Verify** (contract §6). `goConnect` hides the sheet (state kept) and opens `SleeperConnect` or `EspnConnect` after the slide-out (`ClaimSheet.tsx:432-442`). On the host's next focus, `onConnectReturn` re-reads the FA list, adopts the fresh capability and row, and resumes at the gate's step: connect/verify again with "isn't connected" (a cancelled sign-in), the consent step via `openConsent(false)` (which never sends), or Ready (`:355-384`).

## 4. Server order of checks

**Server PR.** Not in this branch.

## 5. Result → held page discarded → Done → FA invalidation

- **The held trade page.** `submitMove` goes through `apiRequest`, whose `_noteWrite` tells the write listener the path when the request is sent and when it settles (`client.ts:483`, `:496`). `devicePageStore` discards every held page for any path `discardsDevicePages` names (`mobile/src/state/devicePageStore.ts:150`), and that now includes the move (`mobile/src/utils/devicePage.ts:256-262`; asserted in `check-device-first-page.js` 1k). The sheet adds no hook of its own.
- **Codes → states.** `classifyMoveError` (`faMove.ts:433-468`) maps by suffix (`^(sleeper|mfl|espn)_…`, `:361-371`) through `STATE_BY_CODE` (`:392-414`); `write_failed` with a `kind` is state 11. No answer, the client timer, status 0 and a 5xx with no usable code are state 12; any other 4xx with an unknown code is the 12-style neutral panel.
- **The sheet** (`applyOutcome`, `ClaimSheet.tsx:548-660`):
  - 200 `complete` / `pending` → the result panel (8 with the chalk check, 9 with no icon), the server's `title` and `lines` (`:557-568`).
  - 1 (`feature_disabled`), 14 (`claims_off`) → the hand-off with the line, bid and drop kept (`:577-579`, `:630-632`).
  - 3, 4 → the connect / verify step with the server's message, and `fa_move_connect_shown` (`:580-591`).
  - 5 → `showConsent` with the 409's block, or the hand-off if it has none (`:592-596`).
  - 10a, 10b, 10d, 10e → inline on Ready: the drop list's `--neg` line and focus; the stale drop cleared and the list refreshed; the bid error against the server's `remaining`; a re-read and a chalk line above the corrected CTA (`:597-629`).
  - 11 → Ready with a `--neg` "nothing was sent" line above the same named CTA; offline at the tap lands here too (`:549-555`, `:633-635`). The retry is a fresh tap and a fresh `attempt_id`. A consent the offline tap carried goes with it.
  - 10c, 10f, 10g, 13, 12-style → the result panel with the server's message in `--neg` (`:636-645`). 13 offers Connect again.
  - 12 → "Check before resending" with the server's words only for its own codes, Open in Sleeper primary, Done, and **no retry** (`:646-658`, `:974-989`).
- **State 7.** The sheet stays busy from the tap until the outcome is shown (`:536-545`). `requestClose` is a no-op while busy, and the backdrop, Cancel and both Modals' `onRequestClose` all go through it (`:411-416`, `:719`, `:1045-1048`, `:1100-1103`). Cancel shows disabled, not hidden. The named CTA uses the Button's `loading` (VoiceOver busy), and "still sending" appears at 8 s (`:326-333`).
- **Done → invalidation.** Every terminal result calls `refreshList`, which invalidates the `['free-agents', leagueId]` prefix (`:401-403`). That covers Free Agents' `['free-agents', leagueId, filter]` and Usage Trends' `['free-agents', leagueId, 'ALL']`, so the list, the drop list, FAAB and the capability refresh together. Done closes the sheet.

## 6. Withdrawals (Settings)

- **Client half: Settings › Leagues.** One `RosterMovesRow` per platform the user has a league on (`mobile/src/screens/settings/SettingsLeaguesScreen.tsx:55-61`, `:82-84`). Each reads `GET /api/platform-write-consent` with `retry: false` (`:111-116`) and renders nothing unless `valid: true` (`:156`), so a 404 or an error shows no row. **Stop roster moves** is one tap, no dialog (`:131-146`): `DELETE`, then the server's `notice` replaces the row verbatim with VoiceOver focus (`:122-129`, `:148-154`), and the consent and FA queries are invalidated so the claim sheet's capability is fresh (`:138-140`). `withdrawConsent` notes the withdrawal so the next consent step reports `withdrawn` (`faMove.ts:162-169`, `:295-297`).
- **Disconnect, expiry, rejection.** Server PR. The client's side of a rejection is state 13 (item 5).

## 7. Capability computation per platform

**Server PR.** Not in this branch.

## Choices the contract and scope left open

- **Usage Trends reads before it routes** (dark-safety above), capped at 3 s.
- **`unsupported` on a Sleeper league** (not a value the server sends) falls back to the legacy hand-off, because `NO_ADD_REASON` has no Sleeper entry. **`handoff` on a non-Sleeper league** (a held MFL/ESPN row in Update 1) shows that platform's `NO_ADD_REASON`; in the sheet, a non-Sleeper hand-off shows its line with no CTA, since this binary has only Sleeper's opener. "Do it in {platform} instead" and the result panels' Open buttons are Sleeper-only for the same reason.
- **A claim while `move.claims` isn't true** is a hand-off before the tap (`faMove.ts:241`), not only after a 422.
- **`{bid}`** is filled as `$N`. An empty FAAB bid on a claim is `$0`. A priority-waiver claim's fallback CTA has no bid.
- **`{date}`** is the window end as a short date ("Nov 8"), with no time.
- **A known placeholder with no value** makes the template fall back rather than show `{drop}`. Unknown placeholders are left as is (contract §7).
- **`open_platform` is not applied.** #509's "Open in Sleeper to claim" label is pinned literally by `check-sleeper-handoff.js` S2, and the contract's example is the same words.
- **"Do it in Sleeper instead"** switches the sheet to the hand-off with bid and drop kept (consent.md §2.1). The result panels' "Open in Sleeper" opens Sleeper directly.
- **The consent step requires a nameable move.** If `this_move` can't be filled, no consent is asked and the sheet goes to the hand-off.
- **`consent_shown.reason`** is read client-side (the contract carries none): a changed `copy_version` → `version`; a Stop roster moves in this app run → `withdrawn`; a known grant no longer valid → `lapsed`; otherwise `first`.
- **A 2xx the client can't read** is state 12 and records `write_failed {unknown, 200}`.
- **testIDs.** The named CTA and the consent step's Make the move are both `fa-claim.make-move` (never on screen together); the result panels' Open in Sleeper reuses `fa-claim.do-in-sleeper`.
- **`attempt_id` survives ingest.** It joins `_HEX_ID_PROPS` in `backend/analytics_ingest.py`, like `search_id`, so a uuid4 with a 16-digit run isn't scrubbed.
