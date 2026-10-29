# Feature Scope addendum — ESPN/MFL send registry (P2-A)

**Date:** 2026-10-29
**Entry point:** release-lead's QA of #527, finding P2-A (and P3-5, the same-frame double tap). head-eng YES for the 11-06 iOS binary, if it is in release-lead's queue by 11-03.
**Builder:** platforms-eng worker, branch `fix/send-registry`, cut from `fix/espn-mfl-client-send-timeout` (#527, head `3ad01072`, which is unchanged).
**Addendum to:** [scope.md](scope.md). Everything there still holds; this covers only the registry.
**Operator sign-off on waivers:** not needed. The one waiver is analytics (c), no new event.

---

## The problem

A send's state lived only in the button's `useState`, and the ESPN/MFL propose routes have no cross-request idempotency. #527 widened the wait from 15 s to 60–91 s, which made two gaps real:

1. Leaving and reopening a trade during the wait remounted the button as an idle **Send in ESPN / Send in MFL**. The user could send the same trade again while the first request was still going.
2. After an unknown outcome ("Check before resending"), the button re-enabled, and the confirm dialog gave no reminder.

## What changes

1. **`mobile/src/api/sendRegistry.ts`**: module state with no React and no imports. It records which trades have a send in flight or an unclear outcome.
   - **Key:** `tradeSendKey(platform, leagueId, theirUserId, giveIds, receiveIds)`. These are the identifiers the propose payload already carries (`league_id`, `their_user_id`, `give_player_ids`, `receive_player_ids`): player ids and FTF pick ids, never names. Each side is sorted, so asset order doesn't matter. The fields are JSON-encoded so they can't run together.
   - **States:**
     - `in_flight`: set by `beginSend(key)`, synchronously, before the request.
     - `unknown` (with its time): the send ended with `isSendOutcomeUnknown(err)`.
     - `sent`: confirmed.
     - A definitive not-sent answer (`*_write_failed`, `*_unavailable`, auth, unmapped assets, `feature_disabled`, …) clears the entry: `settleSend(key, 'not_sent')`.
   - **Why `sent` is recorded:** the button's local `'sent'` state is gone, so the registry has to carry "Proposal sent" for the button that sent the trade. As a result, a remount shows it too, and nothing offers an idle Send for a trade that was just confirmed. `beginSend` refuses `sent` as well as `in_flight`, but only a stale second confirm dialog can reach a refusal: the button itself is disabled in both states.
   - **Lifetime:** in memory, per app run. It survives a remount, **not an app restart**.
   - **Bounded:** at most `SEND_REGISTRY_CAP` = 50 trades. The oldest is dropped first, and a re-recorded trade becomes the newest.
2. **The buttons** (`SendInEspnButton.tsx`, `SendInMflButton.tsx`, same change in each):
   - **Remount:** the label and `disabled` come from `useSyncExternalStore(subscribeSends, () => getSendRecord(sendKey)?.state)` (ESPN `:97-98`, MFL `:95-96`), so a remount, or the same button showing a different trade, reads that trade's state. "Sending…" and "Proposal sent" are the existing labels. The local state keeps only `'idle' | 'checking'`, for the link-status and validate checks.
   - **Double tap (P3-5):** `doPropose`'s first statement is `if (!beginSend(sendKey)) return;` (ESPN `:159`, MFL `:118`), before any await. A same-frame double tap, a second queued confirm dialog, or a second mount sends no second request.
   - **Settle:** the try block calls `settleSend(sendKey, 'sent')` (ESPN `:168`, MFL `:127`). The catch starts with `settleSend(sendKey, isSendOutcomeUnknown(err) ? 'unknown' : 'not_sent')` (ESPN `:182`, MFL `:141`), ahead of #527's unchanged alert ladder.
   - **Reminder:** when this trade's entry is `unknown`, the dialog that gates the send begins with marketing's approved 8e/8f line, `sendOutcomeUnknownMessage(platform)`, then a blank line, then the dialog's existing text (ESPN `:267`, MFL `:220`). This applies to both "Send this trade?" and the warnings dialog ("Send anyway"). The buttons are unchanged. **No new copy.**
3. **Exactly one result alert after a remount.**
   - The `doPropose` call that sent the trade owns the alert.
   - RN's `Alert.alert` is a global native dialog, not part of the component tree. It shows even when the button that started the send has unmounted, and unmounting doesn't cancel the promise, so that call always reaches its alert. That rules out zero alerts.
   - A remount only re-renders from the registry: `subscribeSends` is used only as `useSyncExternalStore`'s store, and has no listener that could alert. That rules out two.
4. **Out of scope:**
   - the server;
   - the overhaul (its plan screen already shows live attempt states);
   - the Sleeper send button.

   The guard checks that none of them imports the registry.

**Behaviour changes worth knowing**
- **After a confirmed send:** reopening the trade in the same app run shows "Proposal sent", disabled, where it used to show an idle Send. The original button already did this while it stayed mounted. Re-sending the identical trade needs an app restart (or the platform itself).
- **A reused button showing a different trade** (the deck's top card, an edited calculator trade) shows that trade's own state. Before, a sent/sending state stuck to the button instance.
- **A stale confirm dialog** for a trade that is in flight or confirmed sent does nothing when you tap Send.

**Known limits**
- **In memory only.** An app restart, or iOS ending the app in the background, during the wait loses the entry. On relaunch the trade shows an idle Send and no reminder, and the lost request's alert never shows. The ESPN/MFL routes still have no server-side idempotency key. That, or a persisted registry, is a separate change.
- **Per device.** Another device knows nothing of this device's sends.
- **The reminder lasts until the next send of that trade settles, or a restart.** The registry can't see that the user revoked the trade on the platform.
- **Pre-existing since #527, not changed here:** if the button unmounted during the wait and the late answer is an auth error, the alert's **Sign in** relies on the unmounted button. For MFL that is `setSignInVisible`; for ESPN it is the focus re-check after `EspnConnect`. So the MFL sign-in sheet does not open, and ESPN's "connected" follow-up alert does not show. **Open ESPN / Open MFL** (Linking) work.

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [ ] (b) Existing events cover it: partly. The timeout itself is still `api_request_failed` (scope.md §1).
- [x] **(c) Waived: no new event.**
  - A refused duplicate makes no request, so no server-side event fires for it.
  - No ESPN/MFL client send events are registered (the buttons carry `surface` unread). Adding one is a taxonomy change, outside this 11-06 fix.

## 2. Schema & flag scope

None. No table, flag, env var or route. Sends stay behind `espn.send` and `trade.send_in_mfl`. Rollback is reverting the client change.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-send-registry.js` (`npm run test:send-registry`), **31 checks**.
  - **What it executes:** the real `api/sendRegistry.ts` and the real `SendInEspnButton` / `SendInMflButton`. They are transpiled and run under a minimal hooks shim (state kept across renders, a fresh state for a remount, `useSyncExternalStore` subscribed per mount), with a fake `Alert` and a scripted propose. It also uses the real `api/client.ts` `ApiError`, `api/sendOutcome.ts` and `utils/sendOutcomeCopy.ts`.
  - **R1, the key:**
    - It is order-insensitive.
    - It is scoped by platform, league and counterparty, and picks count.
    - Different trades don't collide: sides swapped, an asset moved across sides, a comma inside an id, league/counterparty boundaries.
    - Each button keys on exactly the identifiers its propose payload carries (AST).
  - **R2, the send:**
    - `doPropose` starts with the guard.
    - `in_flight` is set synchronously by the press, and the request sees it.
    - Each of these sends **one POST**: a same-frame double press, two queued confirm dialogs (pressed in flight and again after the confirmed send), and a second mount.
  - **R3, a remount:** it renders "Sending…", disabled, and a tap does nothing. The same instance shows another trade as idle, and the first trade as Sending… again.
  - **R4, one alert:** send, unmount, remount, then success / timeout / `write_failed` gives **exactly one** result alert. The remount is notified and shows "Proposal sent" / idle / idle.
  - **R5, outcomes:**
    - Each unknown answer (timeout, dropped connection, `*_outcome_unknown`, `internal_error`, gateway 5xx) records `unknown` with its time.
    - The next "Send this trade?" body is the 8e/8f line **word for word** (a literal in the test), a blank line, then the unchanged body, with buttons Cancel / Send. The warnings dialog does the same.
    - Success records `sent`.
    - Five definitive not-sent answers clear the entry, and the next dialog has no reminder.
    - The catch's first statement and the reminder expression are pinned (AST).
  - **R6, the module:**
    - It is bounded.
    - The API semantics and the listeners are pinned.
    - It has no imports, and its comment states the restart limit.
    - The Sleeper button and the overhaul don't import it.
- [x] **Sabotage**, each red, then restored from a copy:

  | Sabotage | Red |
  |---|---|
  | (a) `in_flight` set after the await (guard removed, `beginSend` after the response), ESPN | 4: R2a, R2b, R2c, R3 |
  | (a) same, MFL | 4: R2a, R2b, R2c, R3 |
  | (b) the button ignores the registry (`useState` in place of `useSyncExternalStore`), ESPN | 7: R2b, R3, R4 ×3, R5c, R5e |
  | (c) unknown not recorded (`settleSend(sendKey, 'not_sent')` always), ESPN | 3: R5a, R5b, R5d |
  | (d) the reminder altered in the button (a literal in place of `sendOutcomeUnknownMessage`), ESPN | 3: R5a, R5b, R5d |
  | (d2) the 8e/8f line altered in `sendOutcomeCopy.ts` | 4 in this suite (R5a, R5b, ESPN + MFL), plus `check-send-timeout.js` C4, C5 |

- [x] **Regression:**
  - every `mobile/tests/check-*.js` passes, 122/122, including `check-send-timeout.js` 24/24 and `check-send-button-platform.js`;
  - `npx tsc --noEmit` exits 0;
  - `mobile/scripts/testid-lint.sh` exits 0 (no testID added).
- [x] **Code walk:** the file:line references in "What changes" above.
- [x] **Manual TestFlight checklist.** It is the only runtime evidence. Every send needs the operator's go at action time.

  **Safety (release-lead QA P3-6, scope.md §3), for every step that sends:**
  - Only use a **sandbox league with a test counterparty**, never a league with real managers. A send under 100% loss can still reach the platform when the network returns.
  - Keep the conditioner, or airplane mode, on for **at least 5 minutes after the alert**.
  - Then check the league's pending trades and **revoke any the test created**.
  - Time from the confirm dialog's **Send**.

  1. iPhone on the 11-06 build, MFL sandbox league linked, MFL sign-in stored. Settings → Developer → Network Link Conditioner, with a 100%-loss profile ready.
  2. Turn the profile on. Open a trade with the test counterparty, tap **Send in MFL**, then **Send**. Within about 30 s, back out of the trade and reopen it.
     - Expected: the button reads **Sending…** and is disabled.
     - Tapping it does nothing.
  3. Wait for the alert (about 60–91 s).
     - Expected: **one** "Check before resending" alert, with OK / Open MFL, whichever screen you are on.
     - The reopened button returns to **Send in MFL**, enabled.
  4. Network still off: tap **Send in MFL** on the reopened trade. The link check and validate can take about 30 s offline.
     - Expected: "Send this trade?" opens with "Couldn't confirm whether this trade reached MFL. Check your league's pending trades on MFL before you send it again." as its first paragraph, then the usual text.
     - The buttons are Cancel / Send.
     - **Tap Cancel.**
  5. Keep the conditioner on for at least 5 minutes after the alert, then turn it off. MFL shows **at most one** pending offer for this trade. **Revoke it.**
  6. In the same app run, open the trade and tap Send. Expected: the reminder is still there, because the registry can't see the revoke. Tap Cancel. Then force-quit and relaunch, open the trade, and tap Send. Expected: no reminder (the in-memory limit). Tap Cancel.
  7. Normal network, a sandbox trade: tap **Send in MFL** twice quickly. If two confirm dialogs appear, tap Send on the first, then on the second.
     - Expected: one "Trade sent".
     - MFL shows **one** pending offer.
     - Back out and reopen the trade: it reads **Proposal sent**, disabled.
     - Revoke the offer.
  8. Repeat steps 2–5 on an ESPN sandbox league with a test counterparty (`espn.send` on). Expected: the ESPN copy and Open ESPN; ESPN shows at most one pending offer, which you then revoke.
  9. Regression, normal network: an MFL send the platform refuses (for example, trades disabled in the sandbox league) gives **Not sent**, as in scope.md. Reopen the trade.
     - Expected: Send in MFL, enabled.
     - The confirm dialog has **no** reminder.
     - Tap Cancel.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route or contract change. |
| `living-memory/LLD.md` | n/a | No schema, route or invariant change. A module store read with `useSyncExternalStore` is an existing mobile pattern (`utils/tapTiming.ts`). |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | No module wiring or data-flow change beyond two buttons. |
| `docs/cross-client-invariants.md` | n/a | Mobile only. The web and the extension have no ESPN/MFL send. |
| `mobile/src/api/CLAUDE.md` | updated | `sendRegistry.ts` row. |
| `mobile/src/components/CLAUDE.md` | updated | The `SendInMflButton` / `SendInEspnButton` rows name the registry. |
| `docs/plans/README.md` | updated | The `client-send-timeout/` row lists this addendum. |

## 5. Ship gate declaration

- **CI green:** `tsc --noEmit`, every `mobile/tests/check-*.js`, testid-lint. Mobile only; `pytest backend/tests` is untouched.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-10-29 entry.
- **TestFlight verification:** §3's checklist, run by the operator on the 11-06 build and logged in TEST_LEDGER. **Unrun.**
- **Express lane declared by the operator?** No. Full gates.
