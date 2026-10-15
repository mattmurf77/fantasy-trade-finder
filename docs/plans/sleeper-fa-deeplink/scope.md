# Feature Scope — Sleeper FA hand-off: open the Sleeper app directly

> Feature-scope block for the operator's top priority of 2026-10-15: the "add free agent in Sleeper" links go through Safari first and then open Sleeper on its home screen. Copied from [`docs/templates/feature-scope.md`](../../templates/feature-scope.md). Every section is answered or waived with a reason. The spec is [prd.md](prd.md). The evidence base is [feasibility.md](feasibility.md) (F1–F9, device tests 1–16, decisions D1–D4). This file plans the work; it changes no code.

**Date:** 2026-10-15
**Entry point:** direct ask. Operator top priority (2026-10-15), routed through `platforms-pm` to a spec worker
**Builder:** not assigned yet. `platforms-eng` / `eng-mobile`, once device tests 1–12 are recorded and D2 is decided (see [prd.md § Sequencing](prd.md#9-sequencing-and-dependencies))
**Operator sign-off on waivers:** not needed (no waivers). The open operator calls are D1–D4 in [prd.md § Decisions needed](prd.md#10-decisions-needed), plus running the pre-build device tests.

---

## 1. Analytics scope

**What exists today.** I ran `git grep -n` over `backend/analytics_taxonomy.py` for `fa_`, `claim`, `handoff`, `hand_off`, `open_in_sleeper`, `sleeper_open`, `free_agent` and every `"*sleeper*"` event name. There is **no FA hand-off or claim event**. Specifically:
- `ClaimSheet.tsx` and `FreeAgentsScreen.tsx` emit nothing (`git grep -n "track("` returns no hits in either file).
- `usage_trends_action {action:'add'}` (`UsageTrendsScreen.tsx:208-221`, fired at `:271`) fires on the Usage Trends **Add** tap, which opens the sheet. It does not fire on the sheet's CTA.
- `sleeper_send_attempted {has_target:false}` (`SendInSleeperButton.tsx:393-399`) fires just before the `openInSleeper()` hand-off. Its props cannot tell whether Sleeper opened.

Nothing records whether a hand-off reached the Sleeper app or hit the not-installed path. That is the one runtime signal, besides the operator's checklist, that the scheme works on testers' phones.

- [x] **(a) New events specced** (**needs an `analytics-lead` grant** before build; name, props and classification are theirs to change):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `sleeper_handoff_resolved` | `surface` ∈ `free_agents` \| `usage_trends` \| `send_button` (closed enum) · `rung` ∈ the proven-rung enum from [prd.md § 4.1](prd.md#41-the-target-ladder) (`add` \| `player` \| `players_tab` \| `league` \| `bare`) · `outcome` ∈ `app` \| `not_installed` · `has_drop` (bool; claim-sheet surfaces only, `null` for `send_button`) | Once per CTA tap, when the `sleeper://` open settles: resolved → `app`, rejected → `not_installed` (fired before the D2 fallback shows). One emitter, inside the shared helper | mobile only |

  Questions it answers: does the scheme reach the app on real devices (`outcome`)? Which surface drives Sleeper adds (`surface`)? How often is the roster full at hand-off (`has_drop`)? The last one is the evidence that decides whether D1, the add/drop write path, is worth a spike. No player id, no player name, no free text.
  Proposed classification: **INTENT**. It is the outcome these surfaces exist for, the same reasoning as `usage_trends_action`. The final call is `analytics-lead`'s.
  Follow-through (build, same commit as the emitter): register in `ALLOWED_CLIENT_EVENTS` and `CLIENT_EVENT_PROPS` (`backend/analytics_taxonomy.py`), classify in `analytics_queries` (INTENT, so absent from `NON_INTENT_EVENTS`), add `backend/tests/test_analytics_taxonomy_sleeper_handoff.py` (precedent: `test_analytics_taxonomy_home_hub.py`), and a dated addendum in `docs/business/analytics/` (precedent: `2026-10-10-usage-trends-events.md`). `docs/data-dictionary.md`: n/a, because it is a `user_events` row with no new column.
- [ ] **(b) Existing events cover it.** This is the fallback **only if the grant is refused**. Then `usage_trends_action {action:'add'}`, `sleeper_send_attempted {has_target:false}` and `screen_viewed {screen:'FreeAgents'}` stay the only signals, and these stay unanswerable: CTA taps from Free Agents, installed vs not installed, and the roster-full rate. In that case ClaimSheet gains no `surface` prop and the helper takes none.
- [ ] **(c) WAIVED:** not chosen.

## 2. Schema & flag scope

- **New/changed tables or columns:** none.
- **New/changed feature flags: none.** Reasons:
  1. **Turning it off would restore a known-broken flow.** The behavior being replaced is verified broken (feasibility F1, F3): Safari, then Sleeper's home screen, or the App Store. A kill switch is worth having when its off state is safe and useful. Here the off state is the bug the operator reported.
  2. **The main failure mode is handled in code.** If no app handles `sleeper://`, `Linking.openURL` rejects (F8, `RCTLinkingManager.mm:90-115`) and the helper runs the D2 fallback. A flag adds nothing to that.
  3. **The remaining risk is retired before build.** That risk is that the scheme opens Sleeper on an unhelpful screen. Device tests 3–10 fix the rung before any code is written. The floor, bare `sleeper://`, lands no worse than today: the same home screen, without the Safari hop.
  4. **What we give up.** FTF has no OTA channel (below), so a client-read flag would be the only rollback that needs no build. We are giving that up knowingly, for reason 1. If the operator wants one anyway, it would be a new client-read key (for example `sleeper.app_handoff`, default `true`). That means `config/features.json`, `FLAG_KEYS`, the mobile launched defaults and `docs/config-reference.md`. The flag revalidate throttle (30 minutes, per the platform risk register in PR #345) bounds how fast it bites. It is a flag surface, so it is not something to add quietly.
- **Revert path: the next EAS build. There is no OTA.** Verified 2026-10-15:
  - `expo-updates` has zero occurrences in `mobile/package.json` and `mobile/app.json`.
  - `mobile/eas.json` has no `channel`.
  - `mobile/ios/DTFDynastyTradeFinder/Supporting/Expo.plist` sets `EXUpdatesEnabled` to `false`.
  - This matches the OI-9 memo `docs/plans/device-side-platform-auth-oi9-expo-updates-memo-2026-08-13.md` §1.

  So rollback is `git revert` of the build commit, then an EAS build, then TestFlight. Current shipping version: `mobile/app.json` 1.21.3 (build 2).
  Feasibility's "OTA-eligible" means **no native change is needed**. It does not mean an OTA path exists.
- **New env vars / `model_config` keys:** none.
- **Native config:** none. No `LSApplicationQueriesSchemes`, no `Info.plist` edit, no entitlement change, and no `app.json` change beyond the routine release version/build-number bump. `Linking.openURL` on a custom scheme is not limited by `LSApplicationQueriesSchemes` (F7). The helper must never call `canOpenURL` (F8); guard S5 pins that.

## 3. Evidence scope

<!-- D-056: no Maestro, no simulator, no captures. -->

- [x] **Structural guard:** new `mobile/tests/check-sleeper-handoff.js` plus `npm run test:sleeper-handoff`. CI's `mobile-typecheck` job already runs every `tests/check-*.js` (`.github/workflows/ci.yml:42-48`), so the guard gates CI as soon as the file exists. CLAUDE.md's "gate nothing yet" is out of date on this point. The guard pins:
  - S1: no `sleeper.com/leagues` reaches `Linking.openURL` from the hand-off surfaces.
  - S2: one shared helper.
  - S3: the scheme is tried first.
  - S4: fallback on rejection.
  - S5: no `canOpenURL`.
  - S6: the clipboard is written before the open.
  - S7: the URL builder's ladder and its numeric-league check.
  - S8: the steps block names the add and the drop.
  - S9: ESPN / MFL / Fleaflicker / local copy stays byte-identical.
  - S10: the shipped rung was proven on a device.

  S3–S7 transpile and **execute** the real helper under plain node with a stubbed `react-native` (the `check-offer-prefill-330-unit.js` idiom). Each assertion names its sabotage: [prd.md § 7.1](prd.md#71-structural-guard-mobiletestscheck-sleeper-handoffjs).
- [x] **Unit tests:** backend pytest only if the §1 event is granted: `backend/tests/test_analytics_taxonomy_sleeper_handoff.py` (registration, props, classification). Otherwise none, because there is no backend change. The mobile unit-level tests are the executed sections of the guard above, since mobile has no jest harness.
- [x] **Code-walk proof:** a file:line trace per surface (Free Agents, Usage Trends, Send-in-Sleeper hand-off), plus a non-Sleeper invariance walk. The skeleton is in [prd.md § 7.2](prd.md#72-code-walk-proof-skeleton). The builder fills it in, in `docs/plans/sleeper-fa-deeplink/code-walk.md`.
- [x] **Manual TestFlight checklist:** two parts, in [prd.md § 7.3](prd.md#73-device-checklist):
  - **Pre-build gate.** Device tests 1–12 from feasibility, run by the operator or app-manager. Results go in `docs/plans/sleeper-fa-deeplink/device-results.md`. Test 3 is go/no-go. The results fix the rung.
  - **Post-ship.** TestFlight steps 13–16.

  No ESPN, MFL or Fleaflicker step is needed: those paths do not change, and S9 pins their copy byte for byte. The Send-in-Sleeper hand-off has no TestFlight step, because no deterministic UI trigger exists for it (prd § 7.3).
- [ ] **WAIVED because:** not waived.
- **`testID`s added/renamed:**
  - Add `fa-claim.steps` (static) to the steps block.
  - `fa-claim.open-sleeper` is **unchanged**, even if design-lead changes its label.
  - No Maestro flow references either ID (`git grep` of `mobile/.maestro`, 2026-10-15), so `testid-lint.sh` is unaffected.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a | No route changes. Client-only hand-off. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **updated (by the build)** | § Code Conventions → Specific patterns: one bullet. "Hand-offs into a platform's app go through that platform's one helper (`utils/sleeperHandoff.ts` for Sleeper). Try the custom scheme first with `Linking.openURL`, never `canOpenURL` without an `LSApplicationQueriesSchemes` entry, and never pass `https://sleeper.com/leagues/...` (Sleeper's AASA doesn't claim it; see feasibility F1/F3)." |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No backend module or data flow changes. One client util replaces three inline `Linking.openURL` calls. |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | n/a | Not an architecture shift. Same clients, same flow, a different outbound URL. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | The rung constant is mobile-only. Web's bare `sleeper://` nudge (`web/js/app.js:6189-6205`) is a separate, unchanged surface with no shared constant. |
| `docs/glossary.md` (new domain term) | n/a | "Claim sheet" and "hand-off" are already used in the code and #179 docs. The rung ladder is spec vocabulary, defined in prd.md. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **updated (by the build)** | New D-entry (next id = max + 1 at build time): scheme-first hand-off, no flag (reasons above), clipboard + steps as the prefill stand-in, the D2 fallback chosen, and the rung recorded from device-results.md. |
| `docs/integrations/sleeper.md:77-79` (Deep-link rows) | **updated (by the build), required** | Replace the three rows with the current call sites and the `sleeper://` URL. Record F1/F3: the AASA claims chat paths only, and the iPhone redirect to `go.slpr.link` drops league, path and query. The trade row (`:77`) changes only to fix its stale line refs and to flag "broken on iPhone, see trades-pm handoff". It does not get a new URL. |
| `docs/feedback/items/179-fa-add-button/status.md:35-36, :98-99` | **updated (by the build)** | Says the CTA "opens the league's players page (app or web via universal link)". That is false on iPhone. Add a dated correction that points to this folder. |
| `mobile/src/utils/CLAUDE.md` + `README.md` | **updated (by the build)** | Add the `sleeperHandoff.ts` entry. It is impure (react-native `Linking`/`Alert`, `./clipboard`, plus `../api/events` if §1 is granted). |
| `mobile/tests/README.md` | **updated (by the build)** | Add the `check-sleeper-handoff` row and bump the guard count (88 → 89). |
| `docs/business/analytics/` addendum | **updated if §1 is granted** | Dated event addendum, written by `analytics-lead`. |
| Platform risk register (`.claude/skills/pm-partnerships/references/platform-risk-register.md`, PR #345, not merged) | **route to `platforms-pm`** | Its Sleeper "Pre-planned response" row names the trade deep link as the fallback that remains if writes go off. Feasibility F3/F5 shows that link is broken on iPhone and very likely on desktop. This is `platforms-pm`'s document, so it is not edited here. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (which runs every `check-*.js`, including the new guard) + `maestro-testid-lint`, all passing on the pushed sha.
- **Pre-build gate (specific to this feature):** device tests 1–12 recorded in `device-results.md` before any code. The rung constant is set from that file.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the guard (S1–S10 plus each sabotage applied and reverted), the code-walk, the device-results file, and `FTF_SKIP_SIM_GATE=1` as the standing D-056 posture.
- **TestFlight verification:** the operator runs steps 13–16 on the build that carries the change, with the outcome logged in TEST_LEDGER.
- **Express lane declared by the operator?** No. The operator said full gates apply (2026-10-15).

## 6. Platform scope

| Platform | Reads | Writes | Behavior in this change |
|---|---|---|---|
| **Sleeper** | unchanged | **none added**. FTF still prepares the claim and the user executes it in Sleeper. The only Sleeper write remains `propose_trade` behind `trade.send_in_sleeper` | **This change.** The claim-sheet CTA (Free Agents and Usage Trends) and the Send-in-Sleeper no-target hand-off open the Sleeper app with `sleeper://…` (scheme first, no Safari), copy the FA's name, and show the add/drop steps. When Sleeper isn't installed, they show the D2 fallback. |
| **ESPN** | unchanged | unchanged | **n/a.** The Add tap keeps its existing `NO_ADD_REASON.espn` alert (`ClaimSheet.tsx:67-74`, via `explainNoAdd` at `:100-103`), byte-identical. Not in scope, noted for `platforms-pm`: community evidence (feasibility C3) says ESPN's AASA claims `/*/players/add`, so an ESPN waiver-screen link may be reachable. That is unverified by us and would be a separate item. |
| **MFL** | unchanged | unchanged | **n/a.** Keeps `NO_ADD_REASON.mfl` (`:75-81`), byte-identical. |
| **Fleaflicker** | unchanged | unchanged | **n/a.** Dark (`fleaflicker.link` false). Keeps `NO_ADD_REASON.fleaflicker` (`:82-88`), byte-identical. |
| local / demo | n/a | n/a | Keeps `NO_ADD_REASON.local` (`:89-94`), byte-identical. |

Clients: **iOS only.** iOS is the only shipped client (TestFlight). Web has no FA hand-off; its only Sleeper links are the trade link (`web/js/app.js:4281-4295`, a trades-pm handoff) and the bare-scheme share nudge (`:6189-6205`, unchanged). The extension: n/a.
