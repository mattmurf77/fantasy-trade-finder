# Mobile ownership recovery — 2026-09-04

Status: native build **1.16.16 (145)** and TestFlight submission completed on 2026-09-05. Physical-device and live credential checks remain outstanding. [Release evidence](deployment.md).

## Code-walk proof

- `mobile/src/components/SleeperLoginCapture.tsx:36` rejects messages outside HTTPS Sleeper origins before parsing a token. The shared WebView is incognito (`:54`), with one delivery per mount and no cookie sharing. The existing connection screen and source-link form use the same capture.
- `mobile/src/components/LinkSleeperSheet.tsx:92` supplies the captured token to the source-link request. Merge-choice callbacks retain that token in a component ref; cancel, terminal failures, successful linking, and unmount (`:69`) clear it. Passwords are never read or stored by the form.
- `mobile/src/components/LinkSleeperSheet.tsx:105` persists the optional send credential only after source binding succeeds and its separate credential-link response explicitly says `verified === true`. Failure of optional credential retention does not undo a successful identity binding or block the host's success path.
- Capture renders inside the existing form/card/sheet (`mobile/src/components/LinkSleeperSheet.tsx:162`). No second native modal is introduced. Closing the sheet unmounts the form, disposing transient proof.
- `mobile/src/screens/LeaguePickerScreen.tsx:453` awaits protected initialization before `setLeague` and navigation. A verification rejection updates the stored verification state and leaves the picker usable; `:492` opens the existing `SleeperConnect` route. Successful capture returns to the picker, where choosing the league retries initialization.
- `mobile/src/navigation/RootNav.tsx:1035` supplies an explicit close button on the existing capture modal. The screen cancels its success timer on unmount to avoid a delayed extra navigation pop.
- `mobile/src/api/auth.ts:139` pins source linking to the starting session and rejects a late result if the session changed. `:248` does the same for initialization and never persists the echoed init token. This closes the reproduced stale-response session resurrection bug.
- `mobile/src/components/LinkSleeperSheet.tsx:93` and `mobile/src/screens/SleeperConnectScreen.tsx:45` check both mounted state and the starting user after asynchronous proof work. A closed form or switched account cannot adopt that late result or navigate on its behalf.

## Automated evidence

- Full TypeScript check: `mobile/node_modules/.bin/tsc --noEmit`.
- `node mobile/tests/check-sleeper-ownership.js`: executes the real capture/form/API modules using stubbed React/native boundaries. Covers wrong-origin and malformed messages, single delivery, explicit board choice with the same proof, no persistence before success, no persistence after an unverified credential result, cancel proof disposal, no nested capture modal, and protected-init navigation ordering. Deferred responses additionally cover init/link after a session switch, proof after a user switch, and callbacks after unmount. The new race cases were demonstrated failing before the fixes and passing afterward.
- **All 91 `mobile/tests/check-*.js` guards passed**, including the new ownership check and existing session/settings/ESPN checks.
- `bash mobile/scripts/testid-lint.sh`: passed.
- Sabotage `persist-unverified-proof`: in-memory test loader replaces the persistence condition with `if (true)`; the ownership guard fails (`1 !== 0`). Production files unchanged by sabotage.
- Expo iOS Hermes JavaScript export passed (9.35 MB bundle); this does not compile or run the native app. Full TypeScript and testID checks also passed on the final mobile sources. [Reproduction commands](validation-tools/README.md).

Logs: `/private/tmp/ftf-mobile-all-guards.log`, `/private/tmp/ftf-typescript-followup.log`, `/private/tmp/ftf-testid-followup.log`, `/private/tmp/ftf-ios-export.log`.

## Manual TestFlight checklist

1. Fresh Apple account, no linked Sleeper source: open Connect Sleeper in the league picker. Enter a username; confirm sign-in opens inside that same sheet. Cancel capture/back out and reopen: no previous account is restored automatically.
2. Sign in to a different Sleeper account than the entered username. Confirm a recoverable mismatch message, no source binding, and a fresh sign-in on retry. Correct the username and finish; verify the correct leagues appear.
3. Repeat linking from Settings → Account & data. Confirm the embedded capture is usable with the keyboard dismissed, and success follows the existing league-picker navigation. Check the smallest supported phone and enlarged text for clipping.
4. With rankings in both account and Sleeper boards, complete capture. Cancel the board-choice alert: neither board changes. Retry and choose each strategy on separate disposable fixtures; verify only the explicitly chosen board survives.
5. Deny/fail the optional send-credential link after successful source binding. Confirm the account still links and reaches its leagues; later Settings → Connect Sleeper can establish trade sending.
6. Legacy username-only sign-in: in the league picker tap Verify Sleeper account, complete the existing capture, and choose the league. Confirm initialization succeeds before tabs open. Decline/cancel capture: picker remains available with sign-out and retry.
7. Simulate initialization returning `403 verification_required`. Confirm the picker stays visible with readable recovery guidance and the verify action, even if cached verification previously said true. Complete verification and choose the league again.
8. Close SleeperConnect manually immediately after success appears. Confirm no delayed timer pops a second route. Retry after a wrong-account login and verify fresh capture works.
9. Cold-start a verified linked session and an account-only session; verify replay precedes init, and account-only/ESPN/MFL league use remains available. Demo still uses its separate demo bootstrap.
10. Delay source linking or initialization, then sign out or switch accounts before the response arrives. Confirm the new account/session remains active, no old bearer is restored, and the previous league is not opened. Repeat with the proof screen and source-link sheet closed before their responses arrive.
11. On disposable accounts, start trade generation, delete the account, and relaunch. Confirm sign-in is required, private data does not return, and a drain-timeout error leaves the account usable for a retry. Repeat with account aliases and with a co-owned Sleeper league.

## Compatibility limits

The picker now waits for server initialization rather than navigating optimistically; this makes ownership and membership errors recoverable before Main mounts. Existing loading indicators cover that wait. Server-side membership and authoritative roster fetching can add upstream latency.

Web/extension recovery is now implemented and covered separately in [browser evidence](browser-evidence.md). Browser ESPN/MFL entry directs users to mobile verification.

Manual native runtime checks above remain outstanding. The physical-device probe (`xcrun devicectl list devices --timeout 20`) reported no devices. Build 145 was subsequently built and submitted successfully; no simulator was used. Incognito WebView, real provider login, Keychain behavior and native navigation still require the checklist on a physical iPhone.
