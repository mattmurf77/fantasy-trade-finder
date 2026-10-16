# Feature Scope — Sleeper hand-off: open the Sleeper app directly (FA add + send a trade)

> Feature-scope block for the operator's top priority of 2026-10-15: FTF's Sleeper links go through Safari first and then open Sleeper on its home screen. On the same day the operator clarified that the send-a-trade feature is the path they reproduced, so it is in scope alongside the FA claim sheet.
> - Copied from [`docs/templates/feature-scope.md`](../../templates/feature-scope.md). Every section is answered or waived with a reason.
> - The spec is [prd.md](prd.md). The evidence base is [feasibility.md](feasibility.md): F1–F9, device tests 1–16, decisions D1–D4.
> - This file plans the work and changes no code.

**Date:** 2026-10-15 (amended the same day for the send-a-trade scope change)
**Entry point:** direct ask, the operator's top priority (2026-10-15), routed through `platforms-pm` to a spec worker. Clarification relayed by `head-product`: "It opens from the send a trade feature. That's the one we tested it on. Have an eng research all external links to compare differences to ensure a consistent experience"
**Builder:** not assigned yet. `platforms-eng` / `eng-mobile`, once R0, device tests 1–12 and T1–T4 are recorded and D2 is decided (see [prd.md § Sequencing](prd.md#9-sequencing-and-dependencies))
**Operator sign-off on waivers:** not needed (no waivers). The open operator calls are D1–D4 in [prd.md § Decisions needed](prd.md#10-decisions-needed), plus running the pre-build device tests.
**Pending:** `head-eng` has an engineer inventorying **all** external links in the app to recommend one consistent pattern. That recommendation folds into this PR through `head-product` when it lands, and the helper's shape is kept open for it ([prd.md § 8](prd.md#8-reviews-needed)).

---

## 1. Analytics scope

**What exists today.** I ran `git grep -n` over `backend/analytics_taxonomy.py` for `fa_`, `claim`, `handoff`, `hand_off`, `open_in_sleeper`, `sleeper_open`, `free_agent` and every `"*sleeper*"` event name. There is **no hand-off or claim event**:
- `ClaimSheet.tsx` and `FreeAgentsScreen.tsx` emit nothing (`git grep -n "track("` finds no hits in either file).
- `usage_trends_action {action:'add'}` (`UsageTrendsScreen.tsx:208-221`, fired at `:271`) fires on the Usage Trends **Add** tap, which opens the sheet. It does not fire on the sheet's CTA.
- `sleeper_send_attempted {has_target:false}` (`SendInSleeperButton.tsx:393-399`) fires just before the `openInSleeper()` hand-off. Its props can't tell whether Sleeper opened.
- The trade queue's Send All (`useTradeQueue.sendAll`) emits nothing.

So nothing records whether a hand-off reached the Sleeper app or hit the not-installed path. Apart from the operator's checklist, that is the one runtime signal that the scheme works on testers' phones.

- [x] **(a) New events specced.** Needs an `analytics-lead` grant before build; the name, props and classification are theirs to change.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `sleeper_handoff_resolved` | `surface` ∈ `free_agents` \| `usage_trends` \| `send_button` \| `trade_queue` (closed enum) · `target` ∈ `add` \| `trade` · `rung` ∈ the proven-rung enum from [prd.md § 4.1](prd.md#41-the-target-ladder) (`add` \| `player` \| `players_tab` \| `trade` \| `trades_tab` \| `league` \| `bare`) · `outcome` ∈ `app` \| `not_installed` · `has_drop` (bool; claim-sheet surfaces only, `null` otherwise) | Once per hand-off, when the `sleeper://` open settles: resolved → `app`, rejected → `not_installed`, fired before the D2 fallback shows. One emitter, inside the shared helper. A Send All of N queued trades is one hand-off and one event. | mobile only |

  What it answers:
  - Does the scheme reach the app on real devices (`outcome`)?
  - Which surface drives Sleeper hand-offs (`surface`)? `send_button` rows can be read next to `sleeper_send_attempted {has_target:false}`.
  - How often is the roster full at hand-off (`has_drop`)? That evidence decides whether D1, the add/drop write path, is worth a spike.

  The event carries no player id, no player name and no free text.
  Proposed classification: **INTENT**. It is the outcome these surfaces exist for, the same reasoning as `usage_trends_action`. The final call is `analytics-lead`'s.
  Follow-through, in the same commit as the emitter:
  - register in `ALLOWED_CLIENT_EVENTS` and `CLIENT_EVENT_PROPS` (`backend/analytics_taxonomy.py`);
  - classify in `analytics_queries` (INTENT, so absent from `NON_INTENT_EVENTS`);
  - add `backend/tests/test_analytics_taxonomy_sleeper_handoff.py` (precedent: `test_analytics_taxonomy_home_hub.py`);
  - add a dated addendum in `docs/business/analytics/`.

  `docs/data-dictionary.md`: n/a, because it is a `user_events` row with no new column.
- [ ] **(b) Existing events cover it.** This is the fallback **only if the grant is refused**. The only signals would then be `usage_trends_action {action:'add'}`, `sleeper_send_attempted {has_target:false}` and `screen_viewed`. These stay unanswerable: CTA taps from Free Agents, Send All usage, installed vs not installed, and the roster-full rate. In that case ClaimSheet gains no `surface` prop and the helper takes none.
- [ ] **(c) WAIVED:** not chosen.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. Client-side, `QueuedTrade` (`mobile/src/shared/types.ts:432-440`) loses `sleeper_url` and gains an optional `opponent_username` ([prd.md § 4.3](prd.md#43-send-a-trade-stand-in-clipboard--steps-before-the-open)). That is local AsyncStorage (`ftf_trade_queue_<user_id>`), not a server schema. Persisted entries that still carry `sleeper_url` are read and that field is ignored, so no migration is needed.
- **New/changed feature flags: none.** `trades.queue_2k` stays as it is (`false`, `config/features.json:14`); lighting it is `trades-pm`'s call. No new flag, because:
  1. **Turning it off would restore a known-broken flow.** Every behavior being replaced is verified broken (feasibility F1, F3, F5): Safari, then Sleeper's home screen or the App Store, with every param dropped. A kill switch earns its keep when its off state is safe and useful. Here the off state is the bug the operator reported.
  2. **The main failure mode is already handled in code.** If no app handles `sleeper://`, `Linking.openURL` rejects (F8, `RCTLinkingManager.mm:90-115`) and the helper runs the D2 fallback.
  3. **The remaining risk is retired before build.** The risk is that the scheme opens Sleeper on an unhelpful screen. Device tests 3–10 and T1–T4 fix each target's rung before any code. The floor, bare `sleeper://`, lands no worse than today: the same home screen, minus the Safari hop.
  4. **What we give up.** FTF has no OTA channel (below), so a client-read flag would be the only rollback that needs no build. We are giving that up knowingly, for reason 1. If the operator wants one anyway, it would be a new client-read key (for example `sleeper.app_handoff`, default `true`) in `config/features.json`, `FLAG_KEYS`, the mobile launched defaults and `docs/config-reference.md`. The 30-minute flag revalidate throttle bounds how fast it takes effect. It is a flag surface, so it should not be added quietly.
- **Revert path: the next EAS build. There is no OTA.** Verified 2026-10-15:
  - `expo-updates` has zero occurrences in `mobile/package.json` and `mobile/app.json`.
  - `mobile/eas.json` has no `channel`.
  - `mobile/ios/DTFDynastyTradeFinder/Supporting/Expo.plist` sets `EXUpdatesEnabled` to `false`.
  - This matches the OI-9 memo (`docs/plans/device-side-platform-auth-oi9-expo-updates-memo-2026-08-13.md` §1).

  Rollback is `git revert` of the build commit, then an EAS build, then TestFlight. Current version: `mobile/app.json` 1.21.3 (build 2). Feasibility's "OTA-eligible" means **no native change is needed**. It does not mean an OTA path exists.
- **New env vars / `model_config` keys:** none.
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
- [x] **Unit tests:** backend pytest only if the §1 event is granted: `backend/tests/test_analytics_taxonomy_sleeper_handoff.py`. Otherwise none, because there is no backend change. Mobile has no jest harness, so the mobile unit-level tests are the executed sections of the guard.
- [x] **Code-walk proof:**
  - **Done in the spec:** the send-a-trade walk. It lists every Sleeper link the feature can open and the UI state that reaches each one ([prd.md § 3.1](prd.md#31-send-a-trade-code-walk-every-sleeper-link-and-the-state-that-reaches-it)). Likely operator path: `SendInSleeperButton.openInSleeper` (`:208-212` via `:405-407`). That is likely, not proven, because no deterministic trigger exists on `main`; R0 settles it.
  - **Filled in by the builder:** a file:line trace per surface after the change, from the skeleton in [prd.md § 7.2](prd.md#72-code-walk-proof-skeleton), written to `docs/plans/sleeper-fa-deeplink/code-walk.md`.
- [x] **Manual TestFlight checklist.** Two parts, in [prd.md § 7.3](prd.md#73-device-checklist):
  - **Pre-build gate.** Run by the operator or app-manager, with results in `docs/plans/sleeper-fa-deeplink/device-results.md`:
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

  No ESPN, MFL or Fleaflicker step is needed: those paths don't change, and S9 plus `check-send-button-platform.js` pin them. There is no queue step while `trades.queue_2k` is dark; S11, S12 and S15 cover it.
- [ ] **WAIVED because:** not waived.
- **`testID`s added/renamed:**
  - Add `fa-claim.steps` (static).
  - `fa-claim.open-sleeper`, `trades.send-sleeper-btn`, `send-in-sleeper.copy` and `send-in-sleeper.unavailable` are **unchanged**.
  - Historical Maestro flows (never run) reference `send-in-sleeper.copy`, `send-in-sleeper.unavailable` and `trades.send-sleeper-btn` (`mobile/.maestro/flows/trade-send/mfl-send-gating.yaml:104`). All of those IDs are kept, so `testid-lint.sh` is unaffected.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a | No route changes. Client-only hand-offs. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **updated (by the build)** | § Code Conventions → Specific patterns gets one bullet: "Hand-offs into a platform's app go through that platform's one helper (`utils/sleeperHandoff.ts` for Sleeper). Try the custom scheme first with `Linking.openURL`. Never use `canOpenURL` without an `LSApplicationQueriesSchemes` entry, and never pass `https://sleeper.com/leagues/...`, which Sleeper's AASA doesn't claim (feasibility F1/F3)." Reword it if `head-eng`'s inventory sets a cross-platform pattern. |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No backend module or data flow changes. One client util replaces four inline `Linking` calls. |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | n/a | Not an architecture shift. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | The rung constant is mobile-only. Web's bare `sleeper://` nudge (`web/js/app.js:6189-6205`) and web trade link (`:4281-4320`) are unchanged and share no constant. |
| `docs/glossary.md` (new domain term) | n/a | "Claim sheet", "hand-off" and "trade queue" are existing terms. The rung ladder is spec vocabulary, defined in prd.md. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **updated (by the build)** | A new D-entry (next id = max + 1 at build time) recording: the scheme-first hand-off; no flag; clipboard + steps as the prefill stand-in on both paths; Send All as one hand-off; the D2 fallback chosen; and each target's rung from device-results.md. |
| `docs/integrations/sleeper.md:77-79` (Deep-link rows) | **updated (by the build), required** | Replace all three rows with the current call sites and their `sleeper://` targets: trade row `:77` → `useTradeQueue.sendAll` + `SendInSleeperButton.openInSleeper`, target `trade`; `:78` → `openInSleeper`; `:79` → `ClaimSheet`, target `add`. Record F1/F3/F5. |
| `docs/feedback/items/179-fa-add-button/status.md:35-36, :98-99` | **updated (by the build)** | It says the CTA "opens the league's players page (app or web via universal link)", which is false on iPhone. Add a dated correction pointing to this folder. |
| `mobile/src/utils/CLAUDE.md` + `README.md` | **updated (by the build)** | Add the `sleeperHandoff.ts` entry. It is impure: react-native `Linking`/`Alert`, `./clipboard`, plus `../api/events` if §1 is granted. |
| `mobile/src/state/CLAUDE.md:27` | **updated (by the build)** | The `useTradeQueue.ts` line says Send All "opens each Sleeper propose URL with a 500 ms stagger". It becomes one hand-off through the helper. |
| `mobile/src/components/CLAUDE.md:16, :38` | **updated (by the build)** | The `ClaimSheet` row (steps block, helper) and the `SendInSleeperButton` row (the no-target hand-off confirm). |
| `mobile/tests/README.md` | **updated (by the build)** | Add the `check-sleeper-handoff` row and bump the guard count (88 → 89). |
| `docs/business/analytics/` addendum | **updated if §1 is granted** | A dated event addendum, written by `analytics-lead`. |
| Platform risk register (`.claude/skills/pm-partnerships/references/platform-risk-register.md`, PR #345, not merged) | **route to `platforms-pm`** | Its Sleeper "Pre-planned response" names the trade deep link as the fallback that remains if writes go off. That link is broken on iPhone (F3), and after this build it no longer exists in mobile. This is `platforms-pm`'s document, so it isn't edited here. |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (which runs every `check-*.js`, including the new guard) and `maestro-testid-lint`, all passing on the pushed sha.
- **Pre-build gate (specific to this feature):** R0, device tests 1–12 and T1–T4 recorded in `device-results.md` before any code. The rung constant is set from that file.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the guard (S1–S16, with each sabotage applied and reverted), the code-walk, the device-results file, and `FTF_SKIP_SIM_GATE=1` as the standing D-056 posture.
- **TestFlight verification:** the operator runs steps 13–20 on the build that carries the change, and the outcome is logged in TEST_LEDGER.
- **Express lane declared by the operator?** No. The operator said full gates apply (2026-10-15).

## 6. Platform scope

| Platform | Reads | Writes | Behavior in this change |
|---|---|---|---|
| **Sleeper** | unchanged | **None added.** The only Sleeper write is still `propose_trade` behind `trade.send_in_sleeper`, and it is untouched | **This change.** The claim-sheet CTA (Free Agents, Usage Trends), the Send-in-Sleeper no-target hand-off and the trade queue's Send All all open the Sleeper app with `sleeper://…` (scheme first, no Safari). They put the free agent's name or the trade summary on the clipboard and show the steps. When Sleeper isn't installed, they show the D2 fallback. |
| **ESPN** | unchanged | unchanged | **n/a.** The claim Add keeps `NO_ADD_REASON.espn` (`ClaimSheet.tsx:67-74`, via `explainNoAdd` `:100-103`) byte for byte. `SendInEspnButton` is unchanged; its `fantasy.espn.com` link (`:89`) goes to the `head-eng` inventory. Noted for `platforms-pm`, not in scope: community evidence (C3) says ESPN's AASA claims `/*/players/add`. That is unverified and would be a separate item. |
| **MFL** | unchanged | unchanged | **n/a.** Keeps `NO_ADD_REASON.mfl` (`:75-81`) byte for byte. `SendInMflButton` is unchanged; its `myfantasyleague.com` link (`:86`) goes to the `head-eng` inventory. |
| **Fleaflicker** | unchanged | unchanged | **n/a.** Dark (`fleaflicker.link` false). Keeps `NO_ADD_REASON.fleaflicker` (`:82-88`) and the send copy fallback, both byte for byte. |
| local / demo | n/a | n/a | Keeps `NO_ADD_REASON.local` (`:89-94`) byte for byte. |

**Clients:** iOS only. It is the only shipped client (TestFlight). Web is unchanged:
- it has no FA hand-off;
- its trade link and Send All (`web/js/app.js:4281-4320`, behind the same dark flag) and its bare-scheme share nudge (`:6189-6205`) go to the `head-eng` inventory.

The extension is n/a.
