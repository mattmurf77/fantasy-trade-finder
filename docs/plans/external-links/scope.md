# Feature Scope — Shared external-link helper + Sleeper "not installed" message (D2)

**Date:** 2026-10-20
**Entry point:** direct ask. head-eng's external-links inventory (`1eaa9d8a:docs/plans/sleeper-fa-deeplink/eng-external-links.md` §4, recommendation B), Phase 2 for platforms-eng, plus #351's PRD (`origin/plan/sleeper-fa-deeplink:docs/plans/sleeper-fa-deeplink/prd.md` §3.2, §4.4, §7.1) and the operator's D2 call ("In app message", 2026-10-20).
**Builder:** eng-mobile worker for platforms-eng, branch `build/open-external-helper` (base `678834ab`)
**Operator sign-off on waivers:** pending. Waivers to surface: §4 LLD / DECISIONS rows (handed to the coordinator, shared living-memory docs). §1 analytics is no longer waived: analytics-lead granted `sleeper_handoff_resolved`, and it lands on the stacked `feat/sleeper-handoff-resolved` (§1).

## Contents

- [What ships](#what-ships)
- [1. Analytics scope](#1-analytics-scope)
- [2. Schema & flag scope](#2-schema--flag-scope)
- [3. Evidence scope](#3-evidence-scope)
- [4. Docs scope](#4-docs-scope-mandatory--hld--lld--api)
- [5. Ship gate declaration](#5-ship-gate-declaration)
- [Copy for design-lead](#copy-for-design-lead)
- [Deferred to other leads](#deferred-to-other-leads)

---

## What ships

| Piece | File | What it does |
|---|---|---|
| Generic helper | `mobile/src/utils/openExternal.ts` | `openPlatform(target)` → `'app' \| 'web' \| 'fallback' \| 'failed'`. Copy → `schemeUrl` → `httpsUrl`. "Not installed" = `Linking.openURL` rejects (#351 F8); never `canOpenURL`. `appMissing: 'alert'` shows the D2 alert. Nothing opens → failure alert. One open at a time: re-taps get the in-flight promise until it settles or 2 s pass. |
| Sleeper builder | `mobile/src/utils/sleeperHandoff.ts` | PRD §3.2 names: `SleeperTarget`, `SleeperRung`, `SLEEPER_PROVEN_RUNGS`, `sleeperAppUrl`, `openInSleeperApp`. One module (no `sleeperLinks.ts`; the split didn't earn its keep). `SLEEPER_PROVEN_RUNGS` ships **`bare` only** for every target: the device tests aren't recorded. Changing it is the one config choice, gated by guard S10. |
| Send in Sleeper | `SendInSleeperButton.tsx:212-214` | The no-target hand-off now calls `openInSleeperApp({ target: 'trade', leagueId, surface: 'send_button' })`: Sleeper **app** (`sleeper://`), not `sleeper.com` in Safari. Not installed → D2 alert. |
| Send in ESPN / MFL | `SendInEspnButton.tsx:89-96`, `SendInMflButton.tsx:88-95` | Same https URLs as before, through `openPlatform`. Changes only error handling (an alert instead of `.catch(() => {})`) and adds the re-tap lock. |
| Stale comments | `SendInSleeperButton.tsx:41-43`, `:463-465`; `SendInEspnButton.tsx:22-23` | They said `espn.send` is OFF and absent from config. It graduated ON on 2026-08-12 (`7315d8c6`, `config/features.json:115`). |
| Guards | `mobile/tests/check-external-links.js`, `mobile/tests/check-sleeper-handoff.js` | See §3. |

No native change, no `Info.plist` key, no `app.json`/`eas.json` change, no flag, no route. No event on #379 itself: `sleeper_handoff_resolved` lands on the stacked `feat/sleeper-handoff-resolved` (§1).

## 1. Analytics scope

- [x] **(a) New event: `sleeper_handoff_resolved`, granted, INTENT.** analytics-lead granted it on 2026-10-20 (G1–G7, widened @ `8b63ef10`). It is emitted on the stacked branch `feat/sleeper-handoff-resolved`, not on #379 itself; this section was updated there. Addendum: [`docs/business/analytics/2026-10-28-sleeper-handoff-events.md`](../../business/analytics/2026-10-28-sleeper-handoff-events.md).
  - **Props, exact:**
    - `surface` ∈ `free_agents` | `usage_trends` | `send_button` | `trade_queue`;
    - `target` ∈ `add` | `trade`;
    - `rung` ∈ `add` | `player` | `players_tab` | `league` | `bare` | `trade` | `trades_tab`, the rung actually opened;
    - `outcome` ∈ `app` | `not_installed`, where `not_installed` means `openURL` rejected (G4);
    - `has_drop` (bool) only on a `target=add` row off `send_button`; omitted, never `null`, on `send_button` and every `target=trade` row (G2).
    - No player id, name or league id (G5).
  - **INTENT.** Registered in `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` (`backend/analytics_taxonomy.py`) in the same commit as the emitter, with **no** `analytics_queries.NON_INTENT_EVENTS` row. Not a WAT event.
  - **Where it fires:** inside the helper, so no call site changes.
    - `openPlatform` gains an optional `onSchemeSettled(opened)` callback. It runs synchronously when the scheme open settles, before any fallback (`openExternal.ts:92-98`).
    - `openInSleeperApp` passes one that calls `trackHandoff` (`sleeperHandoff.ts:119`, `:132-149`).
    - So it fires once per hand-off, before the D2 alert, with no further `await` (G3). A re-tap while the open is in flight adds nothing.
    - ESPN, MFL, `surface: 'unspecified'` and `target: 'league'` (outside the granted `target` set) emit nothing.
  - **`openInSleeperApp` gains `hasDrop?: boolean`.** It reaches the event only on an add hand-off off `send_button`. The claim sheet passes it (league-eng, #509).
  - **`external_link_opened` is not granted** and isn't built.
  - **Evidence:**
    - `mobile/tests/check-sleeper-handoff-event.js` (E1–E11; `npm run test:sleeper-handoff-event`) executes the helper with stubbed `Linking` and `track`;
    - `backend/tests/test_analytics_taxonomy_sleeper_handoff.py` covers the allowlist, the exact prop row, the INTENT split and an ingest round trip;
    - results and sabotage counts are in `living-memory/TEST_LEDGER.md` (2026-10-28).
- [x] **(b) Existing events cover part of it:** `sleeper_send_attempted {has_target:false}` still fires in `SendInSleeperButton.onPress` before the hand-off (unchanged). It counts hand-off attempts. It can't say whether the app opened or the D2 alert showed; `sleeper_handoff_resolved.outcome` now does.
- [x] **(c) Superseded.** This section first waived the event pending analytics-lead's grant, and assumed a `NON_INTENT_EVENTS` row. Both were stale: the grant (2026-10-20) is INTENT, with no `NON_INTENT_EVENTS` row. See (a).

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **none**. Per #351 PRD §10 ("Confirm: no feature flag"), rollback is revert + EAS build; there's no OTA.
- New env vars / `model_config` keys: **none**
- Native config: **none**. Detection is by `openURL` rejection (feasibility F7/F8; RN 0.81.5 `RCTLinkingManager.mm:90-112` rejects "Unable to open URL"). No `LSApplicationQueriesSchemes`.

## 3. Evidence scope

- [x] **Structural guards** (both live in CI through the `tests/check-*.js` glob; `npm run test:external-links`, `npm run test:sleeper-handoff`):
  - `check-external-links.js` pins:
    - (a)/(b) via the AST, so comments don't count: every `Linking.openURL` in `src/` is in `utils/openExternal.ts`; no `canOpenURL` outside the LEGACY allowlist; never `canOpenURL` in the helper. The allowlist is a **ratchet**: each entry must match exactly one call site (same file, call and argument text). An entry that matches none fails, so a migration must delete its entry.
    - (c) **executes** `openPlatform` with stubbed `Linking` / `Alert` / clipboard / timers: C1 app, C2 web, C3 D2 alert + Get Sleeper → `https://apps.apple.com/app/id987367543` (https never tried; Cancel opens nothing; a failed App Store open still alerts), C4 failed + alert, C5 re-tap lock, C6 2 s release, C7 copy before open, C8 `canOpenURL` never touched.
    - (d) The S10 rule lives once, in `check-sleeper-handoff.js`.
  - `check-sleeper-handoff.js`: PRD S2 (SendInSleeperButton half), S3, S4, S5, S6, S7, S10, S13, S16. S3–S7, S10 and S13 execute the real modules. S10 reads `docs/plans/sleeper-fa-deeplink/device-results.md`; it's absent, so only `bare` may ship.
  - **Sabotage run** (applied, guard run, reverted; both guards green after):

    | Sabotage | Guard(s) red |
    |---|---|
    | Hand-off opens `https://sleeper.com/leagues/<id>` instead of the scheme (S3) | sleeper-handoff |
    | `opened()` swallows rejection as success (S4, the `.catch(() => {})` analogue) | both |
    | `await Linking.canOpenURL(url)` added to the helper (S5) | both |
    | `copyText` moved after the open (S6/C7) | both |
    | `/^\d+$/` league check dropped (S7) | sleeper-handoff |
    | `trade: ['trades_tab','bare']` with no PASS row (S10) | sleeper-handoff |
    | `trade` mapped onto the add ladder (S13) | sleeper-handoff |
    | `openInSleeper` inlines `Linking.openURL('sleeper://')` (S2) | both |
    | `Linking.openURL` in `doPropose`'s success branch (S16) | both |
    | failure alert removed (C4) | external-links |
    | in-flight lock removed (C5) | external-links |
    | 2 s release removed (C6) | external-links |
    | a LEGACY entry deleted from the guard (a1) | external-links |
    | a stale LEGACY entry added (a2 ratchet) | external-links |
    | `SendInEspnButton` re-gains a raw `Linking.openURL` (a1) | external-links |
- [x] **Unit tests:** no backend pytest. Nothing in `backend/` changed.
- [x] **Code-walk proof** (file:line at the branch tip):

  **A. Outcome `app`: Sleeper installed, Send in Sleeper with no target**
  1. `SendInSleeperButton.tsx:382-408` `onPress` → `sleeper_send_attempted {has_target:false}` (unchanged) → `:406-407` `!leagueId || !theirUserId` → `openInSleeper()`.
  2. `:212-214` → `openInSleeperApp({ target: 'trade', leagueId, surface: 'send_button' })`.
  3. `sleeperHandoff.ts:95-105` → `sleeperAppUrl(t)` `:79-90`. `:83` keeps L only if numeric. `:85-86` walks `SLEEPER_PROVEN_RUNGS.trade` (`:38-42`, `['bare']`) inside `SLEEPER_RUNG_LADDER.trade`. `rungUrl('bare')` `:71-72` → `sleeper://`. `:103` sets `appMissing: 'alert'`.
  4. `openExternal.ts:70-80` `openPlatform`: `:71` no open in flight; `:72` `attempt`; `:78` 2 s release timer; `:79` release on settle.
  5. `attempt` `:83-95`: `:84` no clipboard; `:86` `opened('sleeper://')` → `:100-106` → `:102` `await Linking.openURL`.
  6. RN 0.81.5 `RCTLinkingManager.mm:90-99` resolves `@YES` → `opened` true → `'app'` → `openInSleeperApp` returns `'app'` (`sleeperHandoff.ts:105`). No alert. Sleeper opens on its last-viewed screen (bare rung).

  **B. Outcome `fallback` (the D2 alert): Sleeper not installed**
  - From A5: `RCTLinkingManager.mm:107`/`:111` rejects "Unable to open URL".
  - `opened` catches → `false` (`openExternal.ts:104-105`).
  - `:87` `APP_STORE.sleeper` (`:65`) → `appMissing === 'alert'` → `:89` `showAppMissing`, `:110-127`:
    - title "Sleeper isn’t installed";
    - body "Get the Sleeper app to finish this in your league.";
    - buttons **Cancel** · **Get Sleeper**.
  - `:90` returns `'fallback'` → `'not_installed'`. https (`sleeper.com`) is never tried.
  - **Get Sleeper** → `:119` `opened('https://apps.apple.com/app/id987367543')`. If that rejects too → `:120` `showOpenFailed`. Never silent.

  **C. Outcome `web` / `failed`: ESPN and MFL opens**
  - ESPN triggers: `SendInEspnButton.tsx:271-272` (no target), or `:211-219` (`espn_write_failed` alert → **Open ESPN**). Both call `openEspn` `:89-96` → `openPlatform({ platform: 'espn', httpsUrl: 'https://fantasy.espn.com', appMissing: 'https' })`.
  - MFL triggers: `SendInMflButton.tsx:234-235`, or `:166-174` → `openMfl` `:88-95`, the same shape with `https://www.myfantasyleague.com`.
  - `attempt`: no `schemeUrl` → `:93` `opened(httpsUrl)`. If it resolves → `'web'` (Safari, exactly as before). If it rejects → `:94` "Couldn’t open that link" → `'failed'`. Before this change, that rejection was `.catch(() => {})`.

  **D. Re-tap.** `openExternal.ts:71` returns the in-flight promise, so nothing opens a second time. The lock clears at `:79` (settled) or `:78` (2 s, for an app switch that suspends JS before `openURL` settles).

  **E. The send path opens nothing, before or after.**
  - `doPropose`, `confirmSend` and `goConnect` contain no `Linking`, and the file no longer imports it (S16).
  - The success alert (`SendInSleeperButton.tsx:244-246`) is still OK-only, per PRD AC-18. No "Open in Sleeper" was added there: that would break AC-18 / S16.
- [x] **Manual TestFlight checklist** (for the operator, on the build that carries this branch). One caveat up front: the only Sleeper call site on this branch is #351's state A, "Send in Sleeper on a card with no league or opponent id". #351 §3.1 found **no deterministic UI trigger** for it. Steps 3–5 are therefore best-effort; mark them n/a with that reason if state A won't reproduce. The first deterministic device proof of `openInSleeperApp` arrives with league-eng's claim-sheet migration (Free agents → Add → CTA; PRD TestFlight 13–16).

  | # | Sleeper app | Steps | Expected |
  |---|---|---|---|
  | 1 | installed, **connected** | Deck → **Send in Sleeper** → Send | Unchanged: "Trade sent" alert with **OK only**. No Safari, no app switch; the offer is pending in Sleeper. |
  | 2 | installed, **not connected** | Deck → Send in Sleeper → **Connect** | Unchanged: Sleeper's login appears **inside FTF**. Nothing opens Safari or the Sleeper app. |
  | 3 | installed | Reach state A (#351 R0's path) → **Send in Sleeper** | The **Sleeper app** opens directly: no Safari, no "Open in Sleeper?" prompt. It lands on whatever Sleeper last showed (bare rung). If state A won't reproduce: n/a, "no deterministic trigger (#351 §3.1 row A)". |
  | 4 | **not installed** (Settings → General → iPhone Storage → Sleeper → Offload App) | Same as 3 | Alert "Sleeper isn’t installed" with **Cancel** / **Get Sleeper**. **Get Sleeper** opens the **App Store app** on Sleeper's listing, with no Safari. **Cancel** returns to FTF and opens nothing. **Never a silent no-op.** n/a rule as in 3. |
  | 5 | installed | State A → double-tap **Send in Sleeper** fast | Exactly **one** app switch. Run it offloaded too: exactly one alert. n/a rule as in 3. |
  | 6 | — | ESPN league, a send ESPN rejects (`espn_write_failed`) → **Open ESPN** | Safari opens `fantasy.espn.com`, unchanged. If it can't be provoked: n/a, "needs an ESPN-side write rejection". |
  | 7 | — | MFL league, a send MFL rejects (`mfl_write_failed`) → **Open MFL** | Safari opens `www.myfantasyleague.com`, unchanged. Same n/a rule. |
  | 8 | — | ESPN and MFL leagues: a normal **Send in ESPN** / **Send in MFL** | Unchanged send flow, with no link opened. |

- [ ] **WAIVED because:** n/a, not waived.
- `testID`s added/renamed: **none**. `bash scripts/testid-lint.sh` → `testid-lint OK`.

**Commands run (all PASS):**

| Command (from `mobile/`) | Result |
|---|---|
| `npx tsc --noEmit` | exit 0 |
| `node tests/check-external-links.js` | 51 PASS, 0 FAIL |
| `node tests/check-sleeper-handoff.js` | 42 PASS, 0 FAIL |
| `node tests/check-send-button-platform.js` | all passed (no assertion pinned the old `openInSleeper` text; none needed updating) |
| `for f in tests/check-*.js; do node "$f" \|\| exit 1; done` | 108/108 pass |
| `bash scripts/testid-lint.sh` | OK |

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed or changed. |
| `living-memory/LLD.md` | **pending, handed to the coordinator** | This is a mobile convention shift: every outside link goes through `utils/openExternal`, and the guard enforces it. LLD.md is a shared living-memory doc, with a single owner per wave (G-022), so this worker didn't edit it. Proposed section, "External links: one opener, never silent (2026-10-20)": `openPlatform` order, detection by rejection, D2, the re-tap lock, and the LEGACY ratchet. The convention is already recorded in `mobile/src/utils/CLAUDE.md`. |
| `docs/architecture.md` | n/a | No backend module or data-flow change. |
| `living-memory/HLD.md` | n/a | No new client, service or major flow; this is one mobile util. |
| `docs/cross-client-invariants.md` | n/a | No shared constant. The App Store id and `sleeper://` are mobile-only. Web's `sleeper://` (`app.js:6200`) is a separate use, not a contract. |
| `docs/glossary.md` | n/a | No new UI term. "Rung" is #351's planning vocabulary and already used in `utils/shareLinks.ts`. |
| ADR or `DECISIONS.md` | **pending, handed to the coordinator** | Three non-obvious choices: a generic helper over Sleeper-only (head-eng D5 = B); one app-wide lock, not per target; detection by rejection with no plist (D2 = A). #351 §11 asks the builder for the D-entry, but DECISIONS.md is a shared living-memory doc (G-022). |
| `docs/integrations/sleeper.md` | **updated** | §1.3 "Client-side, non-API (mobile)": the new app hand-off row, plus corrected cites for the WebView, ClaimSheet, queue and draft rows (all were stale per eng-external-links §3.6). |
| `mobile/src/utils/CLAUDE.md`, `mobile/src/utils/README.md`, `mobile/tests/README.md` | **updated** | Entries for the two modules and two guards (PRD §3.2 asks for the utils entries). |

## 5. Ship gate declaration

- **CI green:** local equivalents all pass (table above). Not pushed; CI hasn't run on the branch.
- **Evidence recorded:** this file. A `living-memory/TEST_LEDGER.md` entry (guards, the sabotage run, the TestFlight outcome) is **pending for the coordinator** (shared doc, G-022). It's required before merge.
- **TestFlight verification:** checklist in §3. The operator runs it on the build; the outcome goes in TEST_LEDGER.
- **Merge gate (not a build gate):** #351 device tests 1–12 and T1–T4 (test 3, `sleeper://` registered, is go/no-go for the whole scheme approach) recorded in `docs/plans/sleeper-fa-deeplink/device-results.md`.
- Express lane declared by the operator? **No.** Full gates.

## Copy for design-lead

No existing visible copy changed; "Send in Sleeper" is still true. New copy, to review:

1. **D2 alert:** "Sleeper isn’t installed" / "Get the Sleeper app to finish this in your league." / **Cancel** · **Get Sleeper**. #351 PRD §4.4 (ii) verbatim; the PRD marks it design-lead's. Curly apostrophe to match the other send alerts. Generated from the platform name in `openExternal.ts:110-127`.
2. **Failure alert:** "Couldn’t open that link" (title only). Reused from RootNav's deep-link toast as a placeholder. Today only ESPN/MFL can reach it, and only if iOS refuses an https URL.
3. **Deferred:** the Send-in-Sleeper steps confirm (PRD §4.3: "Finish in Sleeper" … Cancel / Open Sleeper), which also needs ux-lead. Not built.

## Deferred to other leads

| PRD check / work | Owner | Why not here |
|---|---|---|
| S1, S2 (ClaimSheet half), S8, S9; `ClaimSheet` → `openInSleeperApp({ target: 'add', … })`, the steps block, `leagueName` from Free Agents | league-eng | `ClaimSheet.tsx`, `FreeAgentsScreen.tsx` not ours. **Built in #509 (B3), stacked on this PR** (adds H1/H2 for the hosts) |
| S1 for `UsageTrendsScreen.tsx`; its `leagueName` prop | rankings-eng | not ours. **Built in #509 (B3), stacked on this PR** |
| S11, S12, S15; `useTradeQueue.sendAll` one hand-off; `buildSleeperUrl` removal | trades-eng | `TradesScreen.tsx`, `useTradeQueue.ts` not ours |
| S14 / AC-16; the steps confirm + `clipboardText: formatTradeForClipboard(…)` on `openInSleeper` | platforms-eng follow-up | needs design-lead / ux-lead copy first; silent copying without the disclosure is out |
| `DraftRoomScreen.tsx:827` → `openPlatform` | draft-eng | not ours |
| Settings / About / Sign-in / Connect "Learn more" / Paywall / HelpSheet links | app-shell, unassigned (eng-external-links rows 21–25) | not ours |
| `SleeperLoginCapture.tsx:55` nav policy | platforms-eng follow-up | independent of this helper (eng-external-links §6) |

When one of these migrates, its LEGACY entry in `check-external-links.js` must be deleted in the same change: the ratchet fails until it is.
