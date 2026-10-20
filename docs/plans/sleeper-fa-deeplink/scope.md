# Feature Scope — Sleeper: direct add/drop with 7-day consent, and the `sleeper://` hand-off (FA add + send a trade)

> Feature-scope block for the operator's top priority of 2026-10-15: FTF's Sleeper links go through Safari first and then open Sleeper on its home screen. On the same day the operator clarified that the send-a-trade feature is the path they reproduced, so it is in scope alongside the FA claim sheet.
> - Copied from [`docs/templates/feature-scope.md`](../../templates/feature-scope.md). Every section is answered or waived with a reason.
> - The spec is [prd.md](prd.md). The evidence base is [feasibility.md](feasibility.md): F1–F9, device tests 1–16, decisions D1–D4.
> - **2026-10-20:** the operator decided D1: FTF performs Sleeper add/drops and waiver claims itself, behind a 7-day consent checkbox. The spec is [consent.md](consent.md). The operator also decided D2: an in-app message when Sleeper isn't installed.
> - **Inputs folded in on 2026-10-20** (review notes held outside the repo, cited by role and section): `legal-lead` R15 and LEG-L12, ux-lead K-F1 to K-F7, `design-lead`'s #351 consent and D2 review, and `head-product` P31.
> - This file plans the work and changes no code.

**Date:** 2026-10-15. Amended 2026-10-15 (send-a-trade scope) and 2026-10-20 (D1 direct write + consent, D2 in-app message).
**Entry point:** direct ask, the operator's top priority (2026-10-15), routed through `platforms-pm` to a spec worker. Clarification relayed by `head-product`: "It opens from the send a trade feature. That's the one we tested it on. Have an eng research all external links to compare differences to ensure a consistent experience"
**Builder:** not assigned yet; the build stays with `head-eng` (`platforms-eng` / `eng-mobile`).
- **The hand-off** can start now (P31). R0, device tests 1–12 and T1–T4 gate its **merge**.
- **The direct write** waits for the spike in `docs/plans/sleeper-fa-write/` (being opened by `platforms-eng`; not on origin/main yet). Its flag turns on only under D6 (§5). See [prd.md § Sequencing](prd.md#9-sequencing-and-dependencies).
**Operator sign-off on waivers:** not needed (no waivers). D1 and D2 are decided.
- **Decided by `head-product` (P34, 2026-10-20):** D6 (the flag goes on only after three conditions, §5), D9 (consent is its own step) and D11 (consent per account). D10 (no per-move dialog) is decided by Product **pending `legal-lead`**.
- **Pending `legal-lead` via `head-bizops`:** D5 and D12, plus the confirmations of D10 and D11.
- **Pending `marketing-lead` via `head-bizops`:** the secondary button's words.
- **Open for the operator:** D3, D4, and the no-flag confirmation for the hand-off.

All of these are in [prd.md § Decisions needed](prd.md#10-decisions-needed).
- The operator also approves every live write when it runs: the spike captures, TestFlight 23–25 and 29, and the flag flip.
**Pending:** `platforms-eng` (under `head-eng`) is inventorying **all** external links in the app to recommend one consistent pattern. The inventory feeds the shared hand-off helper. Its recommendation folds into this PR through `head-product` when it lands, and the helper's shape is kept open for it ([prd.md § 8](prd.md#8-reviews-needed)).

---

## 1. Analytics scope

**What exists today.** I ran `git grep -n` over `backend/analytics_taxonomy.py` for `fa_`, `claim`, `handoff`, `hand_off`, `open_in_sleeper`, `sleeper_open`, `free_agent` and every `"*sleeper*"` event name. There is **no hand-off or claim event**:
- `ClaimSheet.tsx` and `FreeAgentsScreen.tsx` emit nothing (`git grep -n "track("` finds no hits in either file).
- `usage_trends_action {action:'add'}` (`UsageTrendsScreen.tsx:208-221`, fired at `:271`) fires on the Usage Trends **Add** tap, which opens the sheet. It does not fire on the sheet's CTA.
- `sleeper_send_attempted {has_target:false}` (`SendInSleeperButton.tsx:393-399`) fires just before the `openInSleeper()` hand-off. Its props can't tell whether Sleeper opened.
- The trade queue's Send All (`useTradeQueue.sendAll`) emits nothing.

So nothing records whether a hand-off reached the Sleeper app or hit the not-installed path. Apart from the operator's checklist, that is the one runtime signal that the scheme works on testers' phones.

- [x] **(a) New events specced.** `sleeper_handoff_resolved` is **GRANTED** by `analytics-lead` (2026-10-20).

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `sleeper_handoff_resolved` | `surface` ∈ `free_agents` \| `usage_trends` \| `send_button` \| `trade_queue` (closed enum) · `target` ∈ `add` \| `trade` · `rung` ∈ the proven-rung enum from [prd.md § 4.1](prd.md#41-the-target-ladder) (`add` \| `player` \| `players_tab` \| `trade` \| `trades_tab` \| `league` \| `bare`) · `outcome` ∈ `app` \| `not_installed` · `has_drop` (bool; claim-sheet surfaces only, `null` otherwise) | Once per hand-off, when the `sleeper://` open settles: resolved → `app`, rejected → `not_installed`, fired before the D2 fallback shows. One emitter, inside the shared helper. A Send All of N queued trades is one hand-off and one event. | mobile only |

  What it answers:
  - Does the scheme reach the app on real devices (`outcome`)?
  - Which surface drives Sleeper hand-offs (`surface`)? `send_button` rows can be read next to `sleeper_send_attempted {has_target:false}`.
  - How often is the roster full at hand-off (`has_drop`)? That evidence decides whether D1, the add/drop write path, is worth a spike.

  The event carries no player id, no player name and no free text.
  Classification: as `analytics-lead` set it in the grant. We proposed **INTENT**, the same reasoning as `usage_trends_action`.
  Follow-through, in the same commit as the emitter:
  - register in `ALLOWED_CLIENT_EVENTS` and `CLIENT_EVENT_PROPS` (`backend/analytics_taxonomy.py`);
  - classify in `analytics_queries` (INTENT, so absent from `NON_INTENT_EVENTS`);
  - add `backend/tests/test_analytics_taxonomy_sleeper_handoff.py` (precedent: `test_analytics_taxonomy_home_hub.py`);
  - add a dated addendum in `docs/business/analytics/`.

  `docs/data-dictionary.md`: n/a, because it is a `user_events` row with no new column.
  **Direct write (D1): seven more events, all PENDING an `analytics-lead` grant.** R15.3 applies: no token, no free text. Full table in [consent.md § 6](consent.md#6-analytics):

  | Event | Fired by | Props | Classification |
  |---|---|---|---|
  | `sleeper_fa_connect_shown` | client | `surface`, `reason` | NON_INTENT. Sizes K-F1 |
  | `sleeper_fa_consent_shown` | client | `surface`, `reason` | NON_INTENT |
  | `sleeper_fa_consent_recorded` | server | `surface`, `copy_version` | INTENT |
  | `sleeper_fa_consent_withdrawn` | server | `via` | INTENT |
  | `sleeper_fa_write_attempted` | client | `surface`, `has_drop`, `has_bid`, `consent_ticked` | INTENT |
  | `sleeper_fa_write_succeeded` | server | `mode`, `has_drop`, `has_bid`, `result`, `transaction_id` | INTENT |
  | `sleeper_fa_write_failed` | client | `surface`, `error_code` (closed enum), `status` | INTENT |

  They follow the P0-7 send split: attempts and failures come from the client; successes, consent records and withdrawals come from the server.
  **App Privacy labels:** no change. Per `legal-lead` R15.6, the data falls under categories already declared, and there's no tracking. Re-check only if a new data type is added. Each is registered and classified in the same commit as its emitter. The tests are `backend/tests/test_analytics_taxonomy_sleeper_fa_write.py`, plus an addendum.
- [ ] **(b) Existing events cover it.** Not used, because `sleeper_handoff_resolved` was granted.
- [ ] **(c) WAIVED:** not chosen.

## 2. Schema & flag scope

- **New tables, two of them, both append-only.** These hold the `legal-lead` R15.3 evidence. Columns, reasons and evidence are in [consent.md § 4.3](consent.md#43-evidence-two-append-only-tables-r153).
  - **`platform_write_consents`:** grant and withdrawal rows. A withdrawal is a new row, never an update.
    - **Keyed by user, not by league (D11: consent is per account).**
    - Lookups use FTF user + Sleeper user.
    - `league_scope` is always `'all_linked'`; it stays only because R15.3 lists it.
  - **`platform_write_moves`:** one row per move, including Sleeper's result.
  - Both are created by `metadata.create_all`, and each gets a `docs/data-dictionary.md` row.
  - **Same change:** both join `delete_user_data` / `export_user_data` through `accounts._ADDITIONAL_PRIVATE_TABLES` (`accounts.py:652-658`), which `test_account_deletion_coverage.py:48` already parametrizes.
  - **Why new tables:** nothing existing fits. `accounts.email_consent_at` is email-only, `sleeper_credentials` is deleted on expiry or refusal, and `user_events` is analytics.
  - **Retention** after account deletion is H6 [PRO]. The default is to delete with the account.
- **Client-side shape change:** `QueuedTrade` (`mobile/src/shared/types.ts:432-440`) loses `sleeper_url` and gains an optional `opponent_username` ([prd.md § 4.3](prd.md#43-send-a-trade-stand-in-clipboard--steps-before-the-open)). That is local AsyncStorage (`ftf_trade_queue_<user_id>`), not a server schema. Persisted entries that still carry `sleeper_url` are read and that field is ignored, so no migration is needed.
- **New feature flag: `sleeper.fa_write`**, default **`false`** (D1 direct write; [consent.md § 3](consent.md#3-what-the-write-route-must-do-implemented-in-sleeper-fa-write)).
  - It gates the write route and the two consent routes (they 404 when it's off, immediately and with no deploy). On the client it gates the connect, consent and direct-write UI and the Settings row. Off means hand-off mode.
  - It goes in `FLAG_KEYS`, the flag fixtures and `docs/config-reference.md`, and stays out of `LAUNCHED_FLAG_DEFAULTS`.
  - **Turning it on (D6, decided by `head-product` P34).** The flag goes on only after **all three** of these:
    - LEG-L12 is done;
    - the P31 device tests have passed;
    - the `platforms-eng` spike has captured the mutation shapes.

    **The flip itself is the operator's.** After that it stays as a permanent kill switch.
  - **It is the write's deploy-free rollback lever.**
- **The `sleeper://` hand-off itself gets no flag.** `trades.queue_2k` stays as it is (`false`, `config/features.json:14`); lighting it is `trades-pm`'s call. No hand-off flag, because:
  1. **Turning it off would restore a known-broken flow.** Every behavior being replaced is verified broken (feasibility F1, F3, F5): Safari, then Sleeper's home screen or the App Store, with every param dropped. A kill switch earns its keep when its off state is safe and useful. Here the off state is the bug the operator reported.
  2. **The main failure mode is already handled in code.** If no app handles `sleeper://`, `Linking.openURL` rejects (F8, `RCTLinkingManager.mm:90-115`) and the helper runs the D2 fallback.
  3. **The remaining risk is retired before merge.** The risk is that the scheme opens Sleeper on an unhelpful screen. Device tests 3–10 and T1–T4 fix each target's rung before the hand-off merges (P31: they gate the merge, not the start of the build). The floor, bare `sleeper://`, lands no worse than today: the same home screen, minus the Safari hop.
  4. **What we give up.** FTF has no OTA channel (below), so a client-read flag would be the only rollback that needs no build. We are giving that up knowingly, for reason 1. If the operator wants one anyway, it would be a new client-read key (for example `sleeper.app_handoff`, default `true`) in `config/features.json`, `FLAG_KEYS`, the mobile launched defaults and `docs/config-reference.md`. The 30-minute flag revalidate throttle bounds how fast it takes effect. It is a flag surface, so it should not be added quietly.
- **Revert path: the next EAS build. There is no OTA.** Verified 2026-10-15:
  - `expo-updates` has zero occurrences in `mobile/package.json` and `mobile/app.json`.
  - `mobile/eas.json` has no `channel`.
  - `mobile/ios/DTFDynastyTradeFinder/Supporting/Expo.plist` sets `EXUpdatesEnabled` to `false`.
  - This matches the OI-9 memo (`docs/plans/device-side-platform-auth-oi9-expo-updates-memo-2026-08-13.md` §1).

  Rollback is `git revert` of the build commit, then an EAS build, then TestFlight. Current version: `mobile/app.json` 1.21.3 (build 2). Feasibility's "OTA-eligible" means **no native change is needed**. It does not mean an OTA path exists.
- **New env vars / `model_config` keys:** none. The 7-day window is a code constant set by the operator's decision, not a knob. The consent copy version is a constant shared by the server and the client (guard S19, plus a `docs/cross-client-invariants.md` row).
- **New routes:**
  - `GET` and `DELETE /api/sleeper/write-consent` (consent.md §4.4).
  - The write route, `POST /api/league/free-agents/add`. Its implementation is owned by `docs/plans/sleeper-fa-write/` (being opened by `platforms-eng`; not on origin/main yet); consent.md §3 holds the product requirements on it.
  - `DELETE /api/sleeper/link`, and every credential deletion (expiry, refusal), now also append a consent withdrawal.

  All of these go in `docs/api-reference.md`.
- **Native config:** none. No `LSApplicationQueriesSchemes`, no `Info.plist` edit, no entitlement change, and no `app.json` change beyond the routine release version/build-number bump. `Linking.openURL` on a custom scheme is not limited by `LSApplicationQueriesSchemes` (F7). Neither the helper nor `sendAll` may call `canOpenURL` (F8); guards S5 and S12 pin that.

## 3. Evidence scope

<!-- D-056: no Maestro, no simulator, no captures. -->

- [x] **Structural guard:** new `mobile/tests/check-sleeper-handoff.js`, plus `npm run test:sleeper-handoff`. CI's `mobile-typecheck` job already runs every `tests/check-*.js` (`.github/workflows/ci.yml:42-48`), so the guard gates CI as soon as the file exists. CLAUDE.md's "gate nothing yet" is out of date on this point. The guard pins:
  - S1: no `sleeper.com/leagues` reaches `Linking.openURL` from the claim surfaces.
  - S2: one shared helper.
  - S3: the scheme is tried first.
  - S4: the fallback runs on rejection.
  - S5: the helper never calls `canOpenURL`.
  - S6: the clipboard is written before the open.
  - S7: the add ladder, and its numeric-league check.
  - S8: the claim steps block names the add and the drop.
  - S9: the ESPN / MFL / Fleaflicker / local copy is byte-identical.
  - S10: each shipped rung was proven on a device.
  - **S11:** no `sleeper.com/leagues`, `buildSleeperUrl` or `sleeper_url` reaches `Linking.openURL` from `TradesScreen.tsx` or `useTradeQueue.ts`.
  - **S12:** no `canOpenURL` in `useTradeQueue.ts`.
  - **S13:** the trade ladder never resolves to an add path.
  - **S14:** the Send-in-Sleeper hand-off shows a steps confirm and copies `formatTradeForClipboard` output.
  - **S15:** Send All makes exactly one hand-off and never opens a persisted `sleeper_url`.
  - **S16:** the linked send path, connect flow and alerts have no `Linking` call.

  S3–S7, S13 and S15 transpile and **execute** real code under plain node with a stubbed `react-native` (the `check-offer-prefill-330-unit.js` idiom). Each assertion names its sabotage: [prd.md § 7.1](prd.md#71-structural-guard-mobiletestscheck-sleeper-handoffjs).
- [x] **Direct-write guards S17–S27** (same file; [consent.md § 8.2](consent.md#82-guard-additions-mobiletestscheck-sleeper-handoffjs)):
  - S17 runs the `faWriteGate` truth table: connect comes before consent, and an unticked box in a lapsed window never yields a write.
  - S18: the write API has exactly one call site, behind the gate.
  - S19: the client and server copy versions match.
  - S20: fallback refusals route to the hand-off.
  - S21: the box is never pre-ticked, and there is no double send.
  - S22: v1's text is pinned by hash.
  - S23: connecting keeps the sheet's bid and drop, and never auto-sends.
  - S24: the steps block shows only in hand-off mode.
  - S25: no stacked confirmation.
  - S26: claim vs add result copy.
  - S27: the Settings row.
- [x] **Unit tests (backend; Sleeper mocked through `sleeper_write._opener`, never a live write):**
  - `backend/tests/test_sleeper_fa_write_route.py` (new). Includes `test_fa_write_no_consent_never_calls_opener`, the source-order `test_fa_write_consent_check_precedes_write_structural`, and `test_move_record_written_per_attempt`.
  - `backend/tests/test_sleeper_write_consent.py` (new). Includes `test_consent_grant_records_r15_fields` and `test_consent_withdrawals_append_only`.
  - `backend/tests/test_sleeper_write.py` (extended with golden bodies from the spike).
  - The flag-parity test (extended).
  - `test_account_deletion_coverage.py` (covers both new tables automatically).
  - `backend/tests/test_analytics_taxonomy_sleeper_handoff.py` (event granted), and `…_sleeper_fa_write.py` once those events are granted.

  The full list is in [consent.md § 8.1](consent.md#81-backend-tests). Mobile has no jest harness, so its unit-level tests are the executed guard sections.
- [x] **Code-walk proof:**
  - **Done in the spec:** the send-a-trade walk. It lists every Sleeper link the feature can open and the UI state that reaches each one ([prd.md § 3.1](prd.md#31-send-a-trade-code-walk-every-sleeper-link-and-the-state-that-reaches-it)). Likely operator path: `SendInSleeperButton.openInSleeper` (`:208-212` via `:405-407`). That is likely, not proven, because no deterministic trigger exists on `main`; R0 settles it.
  - **Filled in by the builder:** a file:line trace per surface after the change, from the skeleton in [prd.md § 7.2](prd.md#72-code-walk-proof-skeleton) (A–F), plus G, the direct write ([consent.md § 8.3](consent.md#83-code-walk-skeleton)), written to `docs/plans/sleeper-fa-deeplink/code-walk.md`.
- [x] **Manual TestFlight checklist.** Two parts, in [prd.md § 7.3](prd.md#73-device-checklist):
  - **Pre-merge gate (P31; the build may start now).** Run by the operator or app-manager, with results in `docs/plans/sleeper-fa-deeplink/device-results.md`:
    - **R0**, a repro of the operator's exact send-a-trade tap: build number, Safari vs in-FTF login, landing screen;
    - device tests 1–12 from feasibility (plus 12c);
    - the new trade-rung tests **T1–T4**: `sleeper://leagues/L/trades`, `sleeper://leagues/L/trade`, a trade-param probe, and the https trade-link baseline.

    Test 3 is go/no-go. The results fix each target's rung.
  - **Post-ship.** TestFlight steps 13–16 (claim sheet) and **17–20** (send a trade):
    - 17: a linked send is unchanged;
    - 18: the connect flow is unchanged;
    - 19: the R0 path with Sleeper installed;
    - 20: the R0 path with Sleeper not installed.

    If R0's path has no on-demand trigger, step 19/20 is marked n/a with the reason, and guard S2 and S11–S16 plus the code-walk carry it.
  - **Direct write (D1).**
    - **Before the write merges:** the mutation spike in `docs/plans/sleeper-fa-write/` (being opened by `platforms-eng`; not on origin/main yet), captured from Sleeper's own web client. Any FTF replay is a live write probe.
    - **Post-ship:** TestFlight **21–29**, which folds in ux-lead's K1–K7:
      - connect, and connect cancelled;
      - consent;
      - inside the window;
      - add+drop and a FAAB claim;
      - declining to the hand-off;
      - withdrawing in Settings;
      - refusals;
      - the FA list and trade deck refreshed after a move.
    - **Every real add, drop or claim is a production platform write.** It needs the operator's approval at the time, in the operator's test league, and is reversed afterwards (release the player or cancel the claim). Turning the flag on for these steps is itself operator-approved.

  No ESPN, MFL or Fleaflicker step is needed: those paths don't change, and S9 plus `check-send-button-platform.js` pin them. There is no queue step while `trades.queue_2k` is dark; S11, S12 and S15 cover it.
- [ ] **WAIVED because:** not waived.
- **`testID`s added/renamed:**
  - Add `fa-claim.steps` (static; it renders in hand-off mode only).
  - Add these for the direct write (D1):
    - `fa-claim.connect`
    - `fa-claim.consent`
    - `fa-claim.consent.box`
    - `fa-claim.make-move`
    - `fa-claim.do-in-sleeper`
    - `fa-claim.result`
    - `settings.roster-moves.status`
    - `settings.roster-moves.stop`

    All are static strings, so they pass `testid-lint.sh`.
  - `fa-claim.open-sleeper`, `trades.send-sleeper-btn`, `send-in-sleeper.copy` and `send-in-sleeper.unavailable` are **unchanged**.
  - Historical Maestro flows (never run) reference `send-in-sleeper.copy`, `send-in-sleeper.unavailable` and `trades.send-sleeper-btn` (`mobile/.maestro/flows/trade-send/mfl-send-gating.yaml:104`). All of those IDs are kept, so `testid-lint.sh` is unaffected.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **updated (by the build)** | `GET` and `DELETE /api/sleeper/write-consent`, plus the write route (implementation per `docs/plans/sleeper-fa-write/` (being opened by `platforms-eng`; not on origin/main yet)), with the refusal contract in consent.md §3. `DELETE /api/sleeper/link` now also appends a consent withdrawal. The hand-off adds no routes. |
| `docs/data-dictionary.md` | **updated (by the build)** | New tables `platform_write_consents` and `platform_write_moves` (consent.md §4.3, R15.3). |
| `docs/config-reference.md` | **updated (by the build)** | New flag `sleeper.fa_write`: default false, and what it gates. It goes on only under D6: LEG-L12 done, the P31 device tests passed, and the spike's mutation shapes captured. The flip is the operator's. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **updated (by the build)** | § Code Conventions → Specific patterns gets two bullets. (1) **On-behalf platform writes need a server-enforced, versioned, time-boxed consent record checked before the write call**; the client gate alone is never enough. (2) "Hand-offs into a platform's app go through that platform's one helper (`utils/sleeperHandoff.ts` for Sleeper). Try the custom scheme first with `Linking.openURL`. Never use `canOpenURL` without an `LSApplicationQueriesSchemes` entry, and never pass `https://sleeper.com/leagues/...`, which Sleeper's AASA doesn't claim (feasibility F1/F3)." Reword it if `head-eng`'s inventory sets a cross-platform pattern. |
| `docs/architecture.md` (module wiring / data flow changed) | **updated (by the build)** | The `sleeper_write.py` module row gains the add/drop and claim mutations. Route wiring: the FA add route → the consent check → `sleeper_write`. (The hand-off itself is a client util that replaces four inline `Linking` calls.) |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | n/a | A new write that follows the existing `propose_trade` pattern (same adapter, credential and route shape) is not an architecture shift. The consent store is a new table, not a new module. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **updated (by the build)** | The consent copy version (`sleeper-roster-moves-v1`), held by both server and client (guard S19). The hand-off's rung constant is mobile-only. Web's bare `sleeper://` nudge (`web/js/app.js:6189-6205`) and web trade link (`:4281-4320`) are unchanged and share no constant. |
| `docs/glossary.md` (new domain term) | **updated (by the build)** | **Write consent**: the 7-day, versioned authorization for FTF to make roster moves the user taps in Sleeper. "Claim sheet", "hand-off" and "trade queue" already exist. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **updated (by the build)** | An **ADR** (`eng-architect` decides ADR vs D-entry) for the on-behalf write and consent model: server-enforced consent, a new table, the rolling window and what clears it. Plus a new D-entry (next id = max + 1 at build time) recording: the scheme-first hand-off; no flag; clipboard + steps as the prefill stand-in on both paths; Send All as one hand-off; the D2 fallback chosen; and each target's rung from device-results.md. |
| `docs/integrations/sleeper.md` §1.2 / §3.3 / §4 | **updated (by the build)** | The new GraphQL mutations (spike-recorded shapes), the new error modes, and the consent gate. |
| `docs/runbook.md` | **updated (by the build)** | How to kill the FA write (flip `sleeper.fa_write`, then reload flags) and what users see afterwards (the hand-off). |
| **Privacy policy `web/privacy.html`** (docs/legal dependency, **LEG-L12, MUST before the add/drop build ships**) | **updated (by the build, wording by `legal-lead`)** | Per R15.4: (1) the Sleeper-connection-token paragraph (`:150-165`) adds roster moves the user starts and confirms, after authorizing in the last 7 days; (2) §4 Sleeper (`:205`) covers trade proposals **and roster moves**; (3) a new collected-data item for authorization and roster-move records; (4) retention (§5) and deletion (§6) follow R15.3; (5) export includes the records. |
| **Terms `web/terms.html` §5** (same dependency, LEG-L12) | **updated (by the build, wording by `legal-lead`; [PRO] lines reviewed)** | Per R15.5: the heading becomes "Sending trades and roster moves to Sleeper" (drop "beta"). Extend the unofficial-interface and account-restriction lines (`:106-107`) to roster moves [PRO]. Add the two new paragraphs: user-started moves with a 7-day authorization, withdrawable in Settings; and moves are final, Sleeper decides processing, plus the liability line [PRO]. Keep `:109`. |
| **Settings › Leagues: the "Roster moves" row** (`mobile/src/screens/settings/sections/PlatformDisconnectSection.tsx`, near the Sleeper-sending row) | **updated (by the build)** | New row per consent.md §4.4 (R15.2.6, H5c, K-F7): status "Roster moves: on until {date}", the **Stop roster moves** control, R15.2.6's withdrawal notice, behind `sleeper.fa_write`. Update the section's header comment and `SettingsLeaguesScreen.tsx`'s section list. Reviewed by `design-lead`, `legal-lead` and ux-lead (prd §8). |
| `docs/design/components.md` (Forms) | **updated by `design-lead`** | The Checkbox component row (consent.md §2.3), which `design-lead` owes, plus the Step list row. |
| `docs/integrations/sleeper.md:77-79` (Deep-link rows) | **updated (by the build), required** | Replace all three rows with the current call sites and their `sleeper://` targets: trade row `:77` → `useTradeQueue.sendAll` + `SendInSleeperButton.openInSleeper`, target `trade`; `:78` → `openInSleeper`; `:79` → `ClaimSheet`, target `add`. Record F1/F3/F5. |
| `docs/feedback/items/179-fa-add-button/status.md:35-36, :98-99` | **updated (by the build)** | It says the CTA "opens the league's players page (app or web via universal link)", which is false on iPhone. Add a dated correction pointing to this folder. |
| `mobile/src/utils/CLAUDE.md` + `README.md` | **updated (by the build)** | Add the `sleeperHandoff.ts` entry. It is impure: react-native `Linking`/`Alert`, `./clipboard`, plus `../api/events`, since the §1 event is granted. |
| `mobile/src/state/CLAUDE.md:27` | **updated (by the build)** | The `useTradeQueue.ts` line says Send All "opens each Sleeper propose URL with a 500 ms stagger". It becomes one hand-off through the helper. |
| `mobile/src/components/CLAUDE.md:16, :38` | **updated (by the build)** | The `ClaimSheet` row (steps block, helper) and the `SendInSleeperButton` row (the no-target hand-off confirm). |
| `mobile/tests/README.md` | **updated (by the build)** | Add the `check-sleeper-handoff` row and bump the guard count (88 → 89). |
| `docs/business/analytics/` addendum | **updated** | Dated event addenda, written by `analytics-lead`: one now for the granted `sleeper_handoff_resolved`, and one for the `sleeper_fa_*` events once they are granted. |
| Platform risk register (`.claude/skills/pm-partnerships/references/platform-risk-register.md`, PR #345, not merged) | **route to `platforms-pm`** | Add the new write (add/drop/claim, consent, `sleeper.fa_write`) to the Sleeper row's writes and kill switches, and record the write-feature-gate pass. Separately, its Sleeper "Pre-planned response" names the trade deep link as the fallback that remains if writes go off. That link is broken on iPhone (F3), and after this build it no longer exists in mobile. This is `platforms-pm`'s document, so it isn't edited here. |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (which runs every `check-*.js`, including the new guard) and `maestro-testid-lint`, all passing on the pushed sha.
- **Pre-merge gate (`head-product` P31: device tests gate the merge, not the start of the build; `platforms-eng` may start the shared helper now):**
  - **Hand-off:** R0, device tests 1–12 and T1–T4 recorded in `device-results.md` before the hand-off merges. The rung constant is set from that file, and guard S10 checks it.
  - **Direct write:** the mutation shapes recorded in `docs/plans/sleeper-fa-write/` (being opened by `platforms-eng`; not on origin/main yet) (AC-19) before any write code merges.
- **LEG-L12 [PRO]: MUST before the add/drop build ships** (`legal-lead`). It requires all of R15:
  - the R15.1 consent copy, verbatim (consent.md §4.1);
  - the R15.3 evidence tables;
  - the R15.4 privacy-policy changes and the R15.5 terms §5 changes (docs/legal row in §4);
  - the R15.6 label check (no change);
  - professional review of R15.7(a)–(e).
- **`sleeper.fa_write` goes on (D6, decided by `head-product` P34).** It requires all three of:
  - LEG-L12 done;
  - the P31 device tests passed;
  - the `platforms-eng` spike's mutation shapes captured.

  **The flip itself is the operator's.** `platforms-pm`'s write-feature-gate pass, from the risk register, also stands. Straight after the flip, TestFlight 21–29 run in the test league. Each real write is approved when it runs and reversed afterwards, and the flag goes back off if any step fails.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the guard (S1–S27, with each sabotage applied and reverted), the backend tests, the code-walk, the device-results file, and `FTF_SKIP_SIM_GATE=1` as the standing D-056 posture.
- **TestFlight verification:** the operator runs steps 13–20 on the build that carries the change, and 21–29 when the write lands. Each real write in 23–25 and 29 is approved when it runs, done in the test league and reversed. Outcomes go in TEST_LEDGER.
- **Express lane declared by the operator?** No. The operator said full gates apply (2026-10-15).

## 6. Platform scope

| Platform | Reads | Writes | Behavior in this change |
|---|---|---|---|
| **Sleeper** | Unchanged. The pre-write checks reuse the public reads the FA route already makes | **Added (D1):** add, add+drop and waiver claim through Sleeper's private GraphQL. Each one is user-tapped, behind `sleeper.fa_write`, needs a valid 7-day consent, and uses the stored JWT the way `propose_trade` does. `propose_trade` is untouched | **This change.** The claim-sheet CTA performs the direct write when the flag is on, the user is linked and consent is valid or ticked. Otherwise, and on a Sleeper refusal, it falls back to the hand-off. The hand-off covers the claim sheet's fallback, the Send-in-Sleeper no-target hand-off and the trade queue's Send All. All three open the Sleeper app with `sleeper://…` (scheme first, no Safari). They put the free agent's name or the trade summary on the clipboard and show the steps. When Sleeper isn't installed, they show the D2 in-app message, never a web hop. |
| **ESPN** | unchanged | unchanged | **n/a.** The claim Add keeps `NO_ADD_REASON.espn` (`ClaimSheet.tsx:67-74`, via `explainNoAdd` `:100-103`) byte for byte. `SendInEspnButton` is unchanged; its `fantasy.espn.com` link (`:89`) goes to the `head-eng` inventory. Noted for `platforms-pm`, not in scope: community evidence (C3) says ESPN's AASA claims `/*/players/add`. That is unverified and would be a separate item. |
| **MFL** | unchanged | unchanged | **n/a.** Keeps `NO_ADD_REASON.mfl` (`:75-81`) byte for byte. `SendInMflButton` is unchanged; its `myfantasyleague.com` link (`:86`) goes to the `head-eng` inventory. |
| **Fleaflicker** | unchanged | unchanged | **n/a.** Dark (`fleaflicker.link` false). Keeps `NO_ADD_REASON.fleaflicker` (`:82-88`) and the send copy fallback, both byte for byte. |
| local / demo | n/a | n/a | Keeps `NO_ADD_REASON.local` (`:89-94`) byte for byte. |

**Clients:** iOS only. It is the only shipped client (TestFlight). Web is unchanged:
- it has no FA hand-off;
- its trade link and Send All (`web/js/app.js:4281-4320`, behind the same dark flag) and its bare-scheme share nudge (`:6189-6205`) go to the `head-eng` inventory.

The extension is n/a.
