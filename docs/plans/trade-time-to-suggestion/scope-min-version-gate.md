# Feature Scope — Minimum-version gate (B8)

**Date:** 2026-10-24
**Entry point:** direct ask — head-eng ruling 35 (the approved design) plus the analytics-lead B8 event grant, assigned by trades-eng
**Builder:** trades-eng worker (branch `feat/min-version-gate`)
**Operator sign-off on waivers:** not needed. Two template rows are waived with reasons (§3 waiver row, §4 ADR row); nothing user-visible is waived.

---

## 0. What it is, and the decisions it rests on

A server-controlled kill switch that forces an app update. While the `model_config` key `app_min_version` is above a build's own version, that build shows one full-screen "Update required" screen with one Update button, and nothing else in the app is reachable. The button opens TestFlight before the App Store release (2026-11-18) and the App Store listing from then on. Raising or lowering the key needs no deploy.

| Decision | Ruling | By |
|---|---|---|
| Lever | `model_config` int `app_min_version`, **0 = off**, seeded 0 insert-if-absent | head-eng ruling 35 |
| Encoding | `major*10000 + minor*100 + patch` (1.22.0 = 12200). Minor and patch are 0–99; anything else is unparseable | head-eng ruling 35 |
| Transport | One additive top-level field `app_min_version` on `GET /api/feature-flags`, which every build already fetches at boot and on foreground. Read defensively: missing, bad or negative → 0 | head-eng ruling 35 |
| App version source | `Constants.expoConfig?.version`, the same source `api/client.ts` sends as `X-App-Version` | head-eng ruling 35 |
| Block predicate | Block only when the fetch resolved, `app_min_version > 0`, the app's int is known, and app int < min. Equal never blocks | head-eng ruling 35 |
| Fail open | A fetch error, timeout, missing or invalid field, or unparseable app version means no gate, ever | head-eng ruling 35 |
| Lift | A later fetch returning a lower or zero min lifts the gate | head-eng ruling 35 |
| Placement | `App.tsx` renders the gate **in place of** `RootNav`. Nothing beneath is mounted, so no screen, modal or deep link can reach around it | builder |
| Failed refetch while gated | Keeps the last **resolved** value. A failed fetch can never raise the gate (cold start reads 0, and the value is never cached), and it does not lower it either, so airplane mode is not a bypass. Flagged to trades-eng for review | builder |
| Foreground refetch while gated | Unthrottled, so a lift lands on the next foreground instead of up to 30 min later. Ungated builds keep the ≥30-min throttle | builder |
| Update target | The same 1.22.0 binary serves TestFlight testers first and App Store users from 2026-11-18. **Date switch, not install detection.** Nothing installed can tell a TestFlight install from an App Store one: `expo-constants` `executionEnvironment` reads `bare`/`standalone` for both, and `expo-application` is not a dependency (only a transitive copy in `node_modules`, so it is not autolinked). The ruling forbids adding one. So `APP_STORE_LIVE_FROM = '2026-11-18'` (local midnight) decides: before it, `itms-beta://` (the TestFlight app; the repo has no public TestFlight link); from it, `https://apps.apple.com/app/id6771488431` (`ascAppId` in `mobile/eas.json`). A failed open leaves the gate up. Move the constant if the release date moves | trades-eng (fallback branch of the target ruling) |
| Copy | Final, from marketing-lead via head-eng. Title "Update required" and button "Update" are the b8.* rows. Body is option (B), "This version of the app is out of date. Update to keep using it.", in one named constant marked `// COPY: option (B), operator pick A8 due 11-03`. If the operator picks A, trades-eng sends the replacement | marketing-lead / head-eng |
| FeedbackFAB | None. A blocking gate is in the modal/onboarding exception class (root CLAUDE.md #188) | head-eng ruling 35 |

**Reach.** Only builds that contain this code can be gated. 1.21.4 and older ignore the field. The first gate-aware binary is the next one shipped (1.22.0 = 12200, the 11-06 binary). Raising the min to 12200 therefore gates nobody until a newer build exists, and it then gates gate-aware builds below it.

## 1. Analytics scope

- [x] **(a) New events specced** — granted by analytics-lead (B8 grant). Both are client-fired from mobile, registered in `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`) and classified in `backend/analytics_queries.NON_INTENT_EVENTS`, all in the same commit as the emitter.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `update_gate_shown` (NON_INTENT) | `min_version` (int, the served min), `app_version_int` (int, this build) | Once per gate show: the screen mounts only after a resolved fetch raised the gate, and a mount-once effect fires it | mobile |
  | `update_gate_tapped` (NON_INTENT) | same two | The Update tap, before the TestFlight / App Store hand-off | mobile |

  No version string, no device platform (a `user_events` column, never a prop), no ids. NON_INTENT because the first is a server-forced impression (the `paywall_viewed` class) and the second leaves the app for the store. As intent, raising the knob would mint a user-day for every blocked device.

  **Delivery check (`track()` pre-auth).** `track()` queues only while the fetched `analytics.client_events` is true (`mobile/src/api/events.ts:114`, `:194`). The gate's `set()` writes the fetched flags and the min together (`mobile/src/state/useFeatureFlags.ts:172`), so the gate mounts with the fetched map in place. The batch always carries `X-Device-Id` and adds `X-Session-Token` only when one is stored (`events.ts:287-289`). The server accepts a missing or dead token and files the row under `device:<id>` (`backend/server.py:11461`, `backend/analytics_ingest.py:346`). Both are live in `config/features.json` (`analytics.client_events`, `analytics.ingest` true). Pinned end to end by `test_gate_events_land_pre_auth_with_both_props[no-session|dead-token]`. The queue's flush triggers (the 10 s interval and flush-on-background, started by `initAnalytics()` in `App.tsx`'s boot effect) do not live under `RootNav`, so they keep running while the gate replaces it. The row goes out within about 10 s, or when the user leaves for the App Store.

  Follow-through: `docs/cross-client-invariants.md` § App version int (the client-event contract lives there per `docs/data-dictionary.md` § user_events). No separate tracking-plan addendum was written in-repo; the grant is analytics-lead's.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** One new `model_config` row (data, not schema).
- New/changed feature flags: **none.** The kill switch is a `model_config` knob, not a flag. `config/features.json` and `FLAG_KEYS` are untouched.
- New env vars / `model_config` keys: **`app_min_version`**, default **0 (off)**.
  - Seeded in `backend/database.py` `_MODEL_CONFIG_DEFAULTS`, insert-if-absent, so a deploy never resets a raised value.
  - Documented in `docs/config-reference.md` § Minimum-version gate (B8).
  - **Ship-the-knob:** the knob *is* the deploy-free lever. Raise: `PUT /api/admin/config/app_min_version` (or `scripts/set_knob.py app_min_version 12200`). **Rollback: set it to 0.** Every gated device lifts on its next foreground.
  - Side effect: like every `model_config` row, it is part of `_trade_request_signature`, so the new row and each later change miss the in-process deck cache once.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-update-gate.js` (`npm run test:update-gate`; CI's check-*.js loop). It pins:
  - **Executed:** `versionInt`, `minVersionOrOff`, `shouldBlockForUpdate` and `appStoreLive` over 70 cases. These cover equal, older, newer, 0 = off, null/garbage/fractional/NaN/Infinity/negative/unsafe mins, and null/garbage app versions, all open. They also cover the release-date boundary (the last ms before local midnight → TestFlight; midnight → App Store; an unparseable date → App Store), and the composition App.tsx uses.
  - **Fail-open wiring:**
    - the min is written on the fetch's success path only, normalized, and never in the catch;
    - the store starts at 0, is set once in the same `set()` as the fetched flags, is untouched by the failed-fetch branch, and is never hydrated or persisted;
    - there is one decision site and one mount, in `App.tsx`;
    - the gate replaces `RootNav`;
    - foreground refetches unthrottled while gated;
    - the version comes from `Constants.expoConfig?.version`.
  - **Events:** each fires from exactly one place with exactly the two props, and is cross-checked against the backend registries.
  - **Screen:** static testIDs, no FeedbackFAB, Chalkline only.
  - **Copy:** all three final strings, exactly, each in one named constant, with the body's A8 marker and no placeholder marker.
  - **Target:** `APP_STORE_LIVE_FROM = '2026-11-18'`, `TESTFLIGHT_URL = 'itms-beta://'`, the App Store URL derived from `eas.json` `ascAppId`, and the exact choice line. A failed open (sync throw or rejection) is swallowed, and the handler changes no gate state.
  - **Version parity (G-012):** app.json == Info.plist `CFBundleShortVersionString` == every `MARKETING_VERSION`.
  - **Settings untouched:** no Settings file references the gate. A branch-scoped diff check skips where `origin/main` is unavailable.
  - **Sabotage:** five in-memory mutants (equal blocks; garbage min accepted; unparseable app version blocks; 3-digit patch parses; release-day midnight still TestFlight), each of which must be caught.
- [x] **Unit tests:** `backend/tests/test_min_version_gate.py` (27 cases):
  - the seed row is 0;
  - `_migrate_db` seeds 0 and a re-run keeps a raised value;
  - the route serves the seeded 0 and a raised value as a JSON int;
  - the rest of the response is unchanged;
  - missing/None/negative/fractional/NaN/±inf/garbage values and a read error serve 0;
  - valid values pass through;
  - both events are allowlisted with `==` prop rows, carry no platform or version-string prop, and are NON_INTENT;
  - both land through `POST /api/events` with no session and with a dead token.
- [x] **Code-walk proof** (file:line, on this branch):
  1. Seed `("app_min_version", 0, …)`: `backend/database.py:3323`, inserted by the existing insert-if-absent loop.
  2. Route: `feature_flags_route` (`backend/server.py:26580`) adds `"app_min_version": _app_min_version()` (`:26645`). `_app_min_version` (`:26649`) reads `get_config()` inside try (read error → 0, `:26659`) and returns 0 unless finite, ≥ 0 and integral (`:26662`).
  3. Mobile fetch: `loadFeatureFlags` types the field `unknown` (`mobile/src/api/flags.ts:54`). It sets `_appMinVersion = minVersionOrOff(res?.app_min_version)` only after the awaited fetch, before the success return (`:83`). The module value starts 0 (`:37`). The catch path never writes it.
  4. Store: `appMinVersion: 0` initial (`mobile/src/state/useFeatureFlags.ts:142`). On a resolved revalidate, `set({ flags, loaded: true, appMinVersion: fetchedAppMinVersion() })` (`:172`). The failure branch is `set({ loaded: true })` (`:181`), and the persisted payload is `flags` only (`:174`).
  5. Decision: `utils/appVersion.ts`. `versionInt` (`:19`, strict regex `:21`); `minVersionOrOff` (`:28`, positive safe integer else 0); `shouldBlockForUpdate` (`:34`) returns false on min 0 or a non-integer app int, and otherwise `appVersionInt < min` (`:38`).
  6. Render: `App.tsx:88-89` computes `updateRequired`. `:290-293` renders `<UpdateGateScreen …/>` **instead of** `<RootNav …/>` when `updateRequired && fontsSettled`. A later resolved fetch with a lower or zero min flips `updateRequired` false and RootNav remounts.
  7. Lift latency: the foreground handler calls `revalidateFlags()` (unthrottled) while blocked, else `maybeRevalidateFlags()` (`App.tsx:226-229`; throttle at `useFeatureFlags.ts:185`).
  8. Screen: `APP_VERSION_INT = versionInt(Constants.expoConfig?.version)` (`mobile/src/screens/UpdateGateScreen.tsx:26`). `update_gate_shown` comes from a mount-once effect (`:65-66`). The Update tap fires `update_gate_tapped` (`:73`), picks `appStoreLive(APP_STORE_LIVE_FROM, new Date()) ? APP_STORE_URL : TESTFLIGHT_URL` (`:74`; constants `:38`, `:42`, `:47`; boundary `utils/appVersion.ts:47-51`), and opens it inside try plus `.catch` (`:75-79`), so a failed open leaves the gate mounted. Copy constants are at `:50-53`, and testIDs at `:83` / `:91`.
- [x] **Manual TestFlight checklist** (the only runtime evidence; run on the first gate-aware build, called **B** below, e.g. 1.22.0 = 12200). Set the knob with `scripts/set_knob.py app_min_version <N>` against prod, and read it back with `GET /api/feature-flags` → `app_min_version`. Use one test device signed in, and one fresh install not signed in.
  1. **Off (baseline).** Knob 0. Cold launch B → the normal app (Home/Trades). No gate.
  2. **Above the build.** Set B+1 (e.g. 12201). Kill and cold-launch B → within a second of the network fetch, the full-screen "Update required", the line "This version of the app is out of date. Update to keep using it.", and one "Update" button. No tab bar, no feedback button, and swipe-back/deep links do nothing. Repeat on the not-signed-in install → same gate (it shows before sign-in).
  3. **Update button, before 2026-11-18.** Tap Update → the **TestFlight app** opens. Return to the app → still gated (no crash, no blank screen).
  4. **Equal to the build.** Set exactly B (12200). Background, then foreground → the gate lifts and the normal app returns. Cold launch → no gate.
  5. **Below the build.** Set B−1 (12199). Cold launch → no gate.
  6. **Lift.** Set B+1, cold launch (gated), then set 0. Background, then foreground once → the gate lifts **on that foreground**, not 30 min later.
  7. **Airplane mode.** (a) Set B+1, enable airplane mode, cold launch → **no gate** (fails open); the app shows its usual offline states. Disable airplane mode, background, then foreground → the gate appears. (b) While gated, enable airplane mode, background, then foreground → the gate **stays** (last resolved answer).
  8. **Malformed value.** `scripts/set_knob.py app_min_version 12201.5`, then `… -1`; read back `GET /api/feature-flags` → `app_min_version: 0` both times. Cold launch → no gate. Set back to 0.
  9. **Update button, from 2026-11-18.** On or after release day (or with the device date set to 2026-11-18 or later), tap Update → the **App Store** opens on the Fleeced listing. Return → still gated. If the release date moves, `APP_STORE_LIVE_FROM` has to move with it before the old date, or testers are sent to a listing that is not live yet.
  10. **Analytics.** After items 2–3, `update_gate_shown` and `update_gate_tapped` rows exist for the test device with `props = {min_version: 12201, app_version_int: 12200}`. The not-signed-in install's rows land under `device:<id>`.
  11. **Older builds.** Install 1.21.4 (pre-gate) with the knob at B+1 → no gate (the field is ignored). Set the knob back to **0** when done.
- [ ] **WAIVED because:** n/a. Nothing in this section is waived; the row is unused.
- `testID`s added: `update-gate.screen`, `update-gate.update` (static literals; `mobile/scripts/testid-lint.sh` passes).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | Feature flags table, the `GET /api/feature-flags` row gains `app_min_version` |
| `living-memory/LLD.md` | n/a | No schema/route/invariant *convention* shifted. One additive field on an existing route, and one knob in the existing `model_config` pattern |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. The value rides the existing flags fetch |
| `living-memory/HLD.md` | n/a | No new module, client or major flow |
| `docs/cross-client-invariants.md` | updated | New § "App version int — the minimum-version gate (B8)": encoding, both sides' parse rules, the G-012 version-source rule, and the two events |
| `docs/glossary.md` | n/a | No new domain term; "minimum-version gate" is self-describing and documented in config-reference |
| ADR or `DECISIONS.md` entry | waived | The design is head-eng ruling 35. The two builder calls (keep the last resolved value on a failed refetch; unthrottled foreground refetch while gated) are recorded in §0 for trades-eng to accept, or to log as a D- entry at ship |
| `docs/config-reference.md` | updated | § `model_config` keys → Minimum-version gate (B8), with TOC entry |
| `mobile/tests/README.md`, `mobile/src/screens/CLAUDE.md`, `mobile/src/utils/CLAUDE.md` | updated | Guard row, screen row, util line |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (tsc + every `check-*.js`) + `maestro-testid-lint`, on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry at ship by trades-eng, naming:
  - `test_min_version_gate.py` (27 passed);
  - `check-update-gate.js`, including three on-disk sabotages (each red, then restored byte-identical): the predicate `<` → `<=`, a changed body string (5c), and the swapped TestFlight/App Store ternary (5d3); plus the in-memory mutants;
  - the backend sabotages S-B1 (drop the negative/integral guard → 3 red) and S-B2 (unclassify `update_gate_shown` → 1 red);
  - the guards run against the changed files;
  - testid-lint;
  - tsc.
- **TestFlight verification:** the §3 checklist, run by the operator on the first gate-aware build, outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **no.**
- Pre-push hook: `FTF_SKIP_SIM_GATE=1` standing posture (D-056); the evidence above replaces it.
