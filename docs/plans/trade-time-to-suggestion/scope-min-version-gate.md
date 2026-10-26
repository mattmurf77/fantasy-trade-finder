# Feature Scope — Minimum-version gate (B8)

**Date:** 2026-10-24 (QA fixes 2026-10-26)
**Entry point:** direct ask — head-eng ruling 35 (the approved design) plus the analytics-lead B8 event grant, assigned by trades-eng; release-lead QA of #404 (GO-with-notes, three P2s) fixed under trades-eng's design calls
**Builder:** trades-eng worker (branch `feat/min-version-gate`)
**Operator sign-off on waivers:** not needed. Two template rows are waived with reasons (§3 waiver row, §4 ADR row); nothing user-visible is waived.

---

## 0. What it is, and the decisions it rests on

A server-controlled kill switch that forces an app update. While the `model_config` key `app_min_version` is above a build's own version, that build shows one full-screen "Update required" screen with one Update button, and nothing else in the app is reachable. The button opens TestFlight or the App Store, chosen by the server knob `app_store_live` when it is set, and otherwise by a compiled UTC instant (2026-11-18T08:00:00Z). Raising or lowering either key needs no deploy.

| Decision | Ruling | By |
|---|---|---|
| Lever | `model_config` int `app_min_version`, **0 = off**, seeded 0 insert-if-absent | head-eng ruling 35 |
| Encoding | `major*10000 + minor*100 + patch` (1.22.0 = 12200). Minor and patch are 0–99; anything else is unparseable | head-eng ruling 35 |
| Transport | One additive top-level field `app_min_version` on `GET /api/feature-flags`, which every build already fetches at boot and on foreground. Read defensively: missing, bad or negative → 0 | head-eng ruling 35 |
| Write guard (QA P2-1) | A typo (122000) or an unreleased version (12400 while `main` is on 1.22.0) would lock out every gate-aware build, because the client is deliberately permissive. One shared validator, `backend/app_version_policy.validate_app_min_version`, refuses writes unless the value is 0, or decodes as x.y.z, is ≤ 99999, and is ≤ the next minor above `mobile/app.json` (read at call time; if unreadable, the first two rules only). Used by the admin PUT (400 + reason) and by `scripts/set_knob.py` (refuses before writing, `--local` and remote). The read side and the client stay permissive; the server write path is the guard | trades-eng |
| App version source | `Constants.expoConfig?.version`, the same source `api/client.ts` sends as `X-App-Version` | head-eng ruling 35 |
| Block predicate | Block only when the fetch resolved, `app_min_version > 0`, the app's int is known, and app int < min. Equal never blocks | head-eng ruling 35 |
| Fail open | A fetch error, timeout, missing or invalid field, or unparseable app version means no gate, ever | head-eng ruling 35 |
| Lift | A later fetch returning a lower or zero min lifts the gate | head-eng ruling 35 |
| Placement | `App.tsx` renders the gate **in place of** `RootNav`. Nothing beneath is mounted, so no screen, modal or deep link can reach around it | builder |
| Failed refetch while gated | Keeps the last **resolved** value. A failed fetch can never raise the gate (cold start reads 0, and the value is never cached), and it does not lower it either, so airplane mode is not a bypass | builder (accepted by trades-eng) |
| Foreground refetch while gated | Unthrottled, so a lift lands on the next foreground instead of up to 30 min later. Ungated builds keep the ≥30-min throttle | builder (accepted by trades-eng) |
| Update target (QA P2-2) | The same 1.22.0 binary serves TestFlight testers first and App Store users from the public release, and nothing installed can tell the two installs apart. (`expo-constants` `executionEnvironment` reads `bare`/`standalone` for both. `expo-application` is not a dependency, only a transitive copy that is not autolinked, and adding one is ruled out.) So: **server first.** `model_config` `app_store_live` (seeded -1) is served as an int, and 1 → App Store, 0 → TestFlight. On -1 or anything else, the **compiled fallback** decides: `APP_STORE_LIVE_FROM_UTC = '2026-11-18T08:00:00Z'` (midnight Pacific), TestFlight before it, App Store from it. The targets are `itms-beta://` (the repo has no public TestFlight link) and `https://apps.apple.com/app/id6771488431` (`ascAppId` in `mobile/eas.json`). A failed open leaves the gate up | trades-eng |
| Copy | Final, from marketing-lead via head-eng. Title "Update required" and button "Update" are the b8.* rows. Body is option (B), "This version of the app is out of date. Update to keep using it.", in one named constant marked `// COPY: option (B), operator pick A8 due 11-03`. If the operator picks A, trades-eng sends the replacement | marketing-lead / head-eng |
| FeedbackFAB | None. A blocking gate is in the modal/onboarding exception class (root CLAUDE.md #188) | head-eng ruling 35 |

**Reach, and choosing a kill value.** Only builds that contain this code can be gated. 1.21.4 and older ignore the field. The first gate-aware binary is 1.22.0 = 12200, the 11-06 binary.
- **12200 blocks nobody at launch**: no gate-aware build is below it.
- **After launch, the useful lever** is the first good version above the oldest bad one. If 1.22.0 is bad and 1.22.1 fixes it, set **12201** once 1.22.1 is live. The write guard refuses anything above the next minor of `mobile/app.json`, so the fix's version bump has to be on `main` (and deployed) first.

## 1. Analytics scope

- [x] **(a) New events specced** — granted by analytics-lead (B8 grant). Both are client-fired from mobile, registered in `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`) and classified in `backend/analytics_queries.NON_INTENT_EVENTS`, all in the same commit as the emitter.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `update_gate_shown` (NON_INTENT) | `min_version` (int, the served min), `app_version_int` (int, this build) | Once per gate show: the screen mounts only after a resolved fetch raised the gate, and a mount-once effect fires it | mobile |
  | `update_gate_tapped` (NON_INTENT) | same two | The Update tap, before the TestFlight / App Store hand-off | mobile |

  No version string, no device platform (a `user_events` column, never a prop), no ids. NON_INTENT because the first is a server-forced impression (the `paywall_viewed` class) and the second leaves the app for the store. As intent, raising the knob would mint a user-day for every blocked device.

  **Delivery check (`track()` pre-auth).** `track()` queues only while the fetched `analytics.client_events` is true (`mobile/src/api/events.ts:114`, `:194`). The gate's `set()` writes the fetched flags and the min together (`mobile/src/state/useFeatureFlags.ts:182-187`), so the gate mounts with the fetched map in place. The batch always carries `X-Device-Id` and adds `X-Session-Token` only when one is stored (`events.ts:287-289`). The server accepts a missing or dead token and files the row under `device:<id>` (`backend/server.py:11461`, `backend/analytics_ingest.py:346`). Both are live in `config/features.json` (`analytics.client_events`, `analytics.ingest` true). Pinned end to end by `test_gate_events_land_pre_auth_with_both_props[no-session|dead-token]`. The queue's flush triggers (the 10 s interval and flush-on-background, started by `initAnalytics()` in `App.tsx`'s boot effect) do not live under `RootNav`, so they keep running while the gate replaces it. The row goes out within about 10 s, or when the user leaves for the store.

  Follow-through: `docs/cross-client-invariants.md` § App version int (the client-event contract lives there per `docs/data-dictionary.md` § user_events). No separate tracking-plan addendum was written in-repo; the grant is analytics-lead's.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** Two new `model_config` rows (data, not schema).
- New/changed feature flags: **none.** Both levers are `model_config` knobs, not flags. `config/features.json` and `FLAG_KEYS` are untouched.
- New env vars / `model_config` keys: **`app_min_version`** (default **0**, off) and **`app_store_live`** (default **-1**, unset).
  - Both seeded in `backend/database.py` `_MODEL_CONFIG_DEFAULTS`, insert-if-absent, so a deploy never resets a set value.
  - Documented in `docs/config-reference.md` § Minimum-version gate (B8).
  - **Ship-the-knob:** `app_min_version` *is* the deploy-free lever. Raise it with `scripts/set_knob.py app_min_version <N>` (e.g. 12201 after a bad 1.22.0, once 1.22.1 is live); the write guard refuses implausible values. **Rollback: set it to 0** (never refused). Every gated device lifts on its next foreground.
  - `app_store_live`: leave -1 while the release is 2026-11-18. If it moves, set 0 until the listing is live, then 1.
  - Side effect: like every `model_config` row, both are part of `_trade_request_signature`, so the new rows and each later change miss the in-process deck cache once.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-update-gate.js` (`npm run test:update-gate`; CI's check-*.js loop). It pins:
  - **Executed** (91 cases): `versionInt`, `minVersionOrOff`, `shouldBlockForUpdate`, `updateGoesToAppStore` and `appStoreLiveOrUnset`.
    - Min/app-version cases: equal, older, newer, 0 = off, null/garbage/fractional/NaN/Infinity/negative/unsafe mins, and null/garbage app versions, all open.
    - Target cases: served 1 → App Store even before the date; served 0 → TestFlight even after it; unset → the UTC instant, exact at the last ms before 08:00Z, at 08:00Z itself, and at 07:00Z on Nov 18 (still TestFlight); any garbage served value → the fallback; an unparseable fallback → App Store.
    - The composition App.tsx uses.
  - **Fail-open wiring:**
    - the min and the served target are each written on the fetch's success path only, normalized, and never in the catch;
    - the store starts at 0 / -1, sets both once in the same `set()` as the fetched flags, leaves both untouched in the failed-fetch branch, and never hydrates or persists either;
    - there is one decision site and one mount, in `App.tsx`;
    - the gate replaces `RootNav`;
    - foreground refetches unthrottled while gated;
    - the version comes from `Constants.expoConfig?.version`.
  - **Events:** each fires from exactly one place with exactly the two props, and is cross-checked against the backend registries.
  - **Screen:** static testIDs, no FeedbackFAB, Chalkline only.
  - **Copy:** all three final strings, exactly, each in one named constant, with the body's A8 marker and no placeholder marker.
  - **Target:**
    - `APP_STORE_LIVE_FROM_UTC = '2026-11-18T08:00:00Z'`, with no local-midnight date left;
    - `TESTFLIGHT_URL = 'itms-beta://'`;
    - the App Store URL derived from `eas.json` `ascAppId`;
    - the screen reads the store's `appStoreLive`, and the exact choice line goes through `updateGoesToAppStore`;
    - a failed open (sync throw or rejection) is swallowed, and the handler changes no gate state.
  - **Version parity (G-012):** app.json == Info.plist `CFBundleShortVersionString` == every `MARKETING_VERSION`.
  - **Settings untouched:** no Settings file references the gate. A branch-scoped diff check skips where `origin/main` is unavailable.
  - **Sabotage:** eight in-memory mutants, each of which must be caught: equal blocks; garbage min accepted; unparseable app version blocks; 3-digit patch parses; release instant still TestFlight; served 1 ignored; served 0 ignored; served garbage honoured.
- [x] **Unit tests:** `backend/tests/test_min_version_gate.py` (85 cases):
  - **Seed:** the seed rows are 0 and -1; `_migrate_db` seeds 0, and a re-run keeps a raised value.
  - **Route:** serves the seeded 0 / -1 and a raised value as JSON ints. The rest of the response is unchanged (keys `flags`, `experiments`, `configs`, `app_min_version`, `app_store_live`). Missing/None/negative/fractional/NaN/±inf/garbage mins and a read error serve 0. `app_store_live` serves 1/0/-1 as given and anything else as -1.
  - **Write policy** (`app_version_policy`), with a temporary app.json:
    - refuses 122000, 99999+1, 12300 at 1.21.4, 12400 at 1.22.0, 12201 at 1.21.4, -1, fractional, NaN, inf, garbage and None;
    - accepts 0 (with and without app.json), 12104 and 12200 at 1.21.4, 12200 and 12300 at 1.22.0, 12300 at 1.22.7, 12150 (decodes as 1.21.50), 99999 without app.json, 50000 with an unparseable app.json version, and 20000 at 1.99.3 (carry);
    - reads the real `mobile/app.json`, resolved per call.
  - **Admin PUT:** refused values return 400 with the reason and write no row and no change log; plausible values (12200, 12300, 12201, 0) write; the check is scoped to `app_min_version`.
  - **`set_knob.py`:** refuses 122000, 12400, -1 and 12200.5 before either write path (`set_config` and `urlopen` never called), on `--local` and remote; writes 12300 on both.
  - **Events:** allowlisted with `==` prop rows, no platform or version-string prop, NON_INTENT; both land through `POST /api/events` with no session and with a dead token.
- [x] **Code-walk proof** (file:line, on this branch):
  1. **Seeds:** `("app_min_version", 0, …)` at `backend/database.py:3323` and `("app_store_live", -1, …)` at `:3328`, inserted by the existing insert-if-absent loop.
  2. **Route:** `feature_flags_route` (`backend/server.py:26589`) spreads `**_update_gate_fields()` (`:26654`). That helper (`:26658`) reads `get_config()` once; a read error yields `{}`.
     - `_app_min_version(cfg)` (`:26671`) returns 0 unless the value is finite, ≥ 0 and integral (`:26680-26683`).
     - `_app_store_live(cfg)` (`:26688`) returns the value only if it is exactly 0 or 1, else -1 (`:26696`).
  3. **Write guard:** `backend/app_version_policy.py`. `validate_app_min_version` (`:71`) accepts 0 (`:81`), refuses > 99999 (`:83`), and refuses above `next_minor_cap` of the app.json version read per call (`:86-89`; `APP_JSON` at `:33`). The admin PUT calls it for `app_min_version` and returns 400 before `set_config` (`backend/server.py:22271-22275`). `scripts/set_knob.py:74-82` calls it before either write path.
  4. **Mobile fetch:** `loadFeatureFlags` types both fields `unknown` (`mobile/src/api/flags.ts:60-61`). It sets `_appMinVersion = minVersionOrOff(…)` and `_appStoreLive = appStoreLiveOrUnset(…)` only after the awaited fetch, before the success return (`:90-91`). They start at 0 (`:37`) and -1 (`:43`); the catch never writes them.
  5. **Store:** `appMinVersion: 0`, `appStoreLive: -1` (`mobile/src/state/useFeatureFlags.ts:151-152`). On a resolved revalidate, one `set({ flags, loaded: true, appMinVersion, appStoreLive })` (`:182-187`). The failure branch is `set({ loaded: true })` (`:196`), and the persisted payload is `flags` only (`:189`).
  6. **Decision:** `mobile/src/utils/appVersion.ts`.
     - `versionInt` (`:19`); `minVersionOrOff` (`:28`).
     - `shouldBlockForUpdate` (`:34`) returns `appVersionInt < min` (`:38`) after the fail-open checks.
     - `appStoreLiveOrUnset` (`:43`).
     - `updateGoesToAppStore` (`:57`): served 1 → true and 0 → false (`:58-59`); else the UTC instant (`:65`).
  7. **Render:** `App.tsx:88-89` computes `updateRequired`. `:290-293` renders `<UpdateGateScreen …/>` **instead of** `<RootNav …/>`. A later resolved fetch with a lower or zero min flips it back.
  8. **Lift latency:** the foreground handler calls `revalidateFlags()` (unthrottled) while blocked, else `maybeRevalidateFlags()` (`App.tsx:226-229`; throttle at `useFeatureFlags.ts:200`).
  9. **Screen:** `mobile/src/screens/UpdateGateScreen.tsx`.
     - `APP_VERSION_INT` (`:27`); constants at `:40` (UTC fallback), `:44` (TestFlight) and `:49` (App Store).
     - Copy at `:52-55`.
     - `servedTarget` from the store (`:67`).
     - `update_gate_shown` from a mount-once effect (`:71-72`).
     - The tap fires `update_gate_tapped` (`:79`), picks the URL via `updateGoesToAppStore(servedTarget, new Date(), APP_STORE_LIVE_FROM_UTC)` (`:80`), and opens it inside try plus `.catch` (`:84`), so a failed open leaves the gate mounted.
     - testIDs at `:91` / `:99`.
- [x] **Manual TestFlight checklist** (the only runtime evidence; run on the first gate-aware build, called **B** below: 1.22.0 = 12200).

  > **Warning: this writes the PROD knob.** `app_min_version` at B+1 (12201) on prod blocks **every 1.22.0 device in the field**, testers included, for as long as it stays set.
  > - Run items 2–9 **only before 2026-11-18**, while the only 1.22.0 devices are TestFlight testers.
  > - Keep each B+1 window to a few minutes, and set it back to **0** at the end of every window.
  > - **Always end the session at 0** and confirm `GET /api/feature-flags` → `app_min_version: 0`.
  > - Never touch `app_store_live` for this checklist.
  > - Run `scripts/set_knob.py` from a `main` checkout whose `mobile/app.json` is 1.22.0. Against 1.21.x the write guard refuses 12201, which is correct, since no 1.22.1 exists then.
  >
  > Use one signed-in test device and one fresh install that is not signed in.

  1. **Off (baseline).** Knob 0. Cold launch B → the normal app (Home/Trades). No gate.
  2. **Window A opens: set 12201.** Kill and cold-launch B → within a second of the network fetch, the full-screen gate appears:
     - the title "Update required";
     - the line "This version of the app is out of date. Update to keep using it.";
     - one "Update" button.

     There is no tab bar and no feedback button, and swipe-back and deep links do nothing. Repeat on the not-signed-in install → same gate (it shows before sign-in). Still in the window, launch a 1.21.4 install → no gate (pre-gate builds ignore the field).
  3. **Update → TestFlight** (window A). Tap Update → the **TestFlight app** opens. Return to the app → still gated (no crash, no blank screen).
  4. **Lift; window A closes.** Set 0. Background, then foreground once → the gate lifts **on that foreground**, not 30 min later.
  5. **Equal to the build.** Set 12200 (blocks no gate-aware build). Background, then foreground → no gate; cold launch → no gate. Set 0.
  6. **Below the build.** Set 12199. Cold launch → no gate. Set 0.
  7. **Airplane mode (window B: set 12201).**
     - (a) Enable airplane mode and cold launch → **no gate** (fails open); the app shows its usual offline states. Disable airplane mode, then background and foreground → the gate appears.
     - (b) While gated, enable airplane mode, then background and foreground → the gate **stays** (last resolved answer).

     Set 0, disable airplane mode, then foreground → the gate lifts. Window B closes.
  8. **Write guard (no window).** Run `scripts/set_knob.py app_min_version` with 122000, then 12201.5, then -1, then 12400. Each prints `refusing: app_min_version …` and writes nothing. `GET /api/feature-flags` still shows `app_min_version: 0`.
  9. **App Store target, by device date only (window C: set 12201).** Leave `app_store_live` at -1. On the test device, turn off automatic date and time and set the date to **2026-11-19**. Cold launch → gated. Tap Update → the **App Store** opens on the Fleeced listing. Return → still gated. Restore automatic date and time, set 0, and window C closes.
  10. **Analytics.** After items 2–3, `update_gate_shown` and `update_gate_tapped` rows exist for the test device with `props = {min_version: 12201, app_version_int: 12200}`. The not-signed-in install's rows land under `device:<id>`.
  11. **End.** Confirm `app_min_version` is **0** and `app_store_live` is **-1**.

  **Release-day step (ops, not a test).**
  - If the App Store release is 2026-11-18, leave `app_store_live` at **-1**; the compiled fallback flips the button to the App Store at 08:00Z (midnight Pacific).
  - If the date moves earlier or later, set `app_store_live` **0** before 2026-11-18T08:00Z, then **1** on the actual release day (`scripts/set_knob.py app_store_live 1`).
  - After launch, kill a bad build by setting `app_min_version` to the first good version above the oldest bad one (§0).
- [ ] **WAIVED because:** n/a. Nothing in this section is waived; the row is unused.
- `testID`s added: `update-gate.screen`, `update-gate.update` (static literals; `mobile/scripts/testid-lint.sh` passes).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | The `GET /api/feature-flags` row gains `app_min_version` and `app_store_live`. The `PUT /api/admin/config/<key>` row gains the `app_min_version` 400 |
| `living-memory/LLD.md` | n/a | No schema/route/invariant *convention* shifted. Two additive fields on an existing route, two knobs in the existing `model_config` pattern, and one key-scoped write check |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. The values ride the existing flags fetch; `app_version_policy.py` is a stdlib leaf |
| `living-memory/HLD.md` | n/a | No new module, client or major flow |
| `docs/cross-client-invariants.md` | updated | § "App version int — the minimum-version gate (B8)": encoding, both sides' parse rules, the write guard, the `app_store_live` 1/0/-1 contract, the G-012 version-source rule, and the two events |
| `docs/glossary.md` | n/a | No new domain term; "minimum-version gate" is self-describing and documented in config-reference |
| ADR or `DECISIONS.md` entry | waived (trades-eng logs D-entries) | The design is head-eng ruling 35 plus trades-eng's QA design calls. The builder calls are recorded in §0 |
| `docs/config-reference.md` | updated | § `model_config` keys → Minimum-version gate (B8): `app_min_version` (write guard, choosing a kill value) and `app_store_live` (ops), with TOC entry |
| `mobile/tests/README.md`, `mobile/src/screens/CLAUDE.md`, `mobile/src/utils/CLAUDE.md` | updated | Guard row, screen row, util line |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (tsc + every `check-*.js`) + `maestro-testid-lint`, on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry at ship by trades-eng, naming:
  - `test_min_version_gate.py` (85 passed);
  - `check-update-gate.js` (91 executed cases, 8 in-memory mutants), with four on-disk sabotages, each red and then restored byte-identical:
    - the predicate `<` → `<=`;
    - a changed body string (5c);
    - the swapped TestFlight/App Store ternary (5d3);
    - served 0 → App Store (the 1–2 case table);
  - backend sabotages:
    - S-B1: drop the negative/integral read guard → 3 red;
    - S-B2: unclassify `update_gate_shown` → 1 red;
    - S-B3: disable the next-minor cap → 7 red;
    - S-B4: serve `app_store_live` 2 → 1 red;
  - the admin-PUT suites (`test_model_config_log.py`, `test_launch_qa_fixes.py`);
  - the guards run against the changed files;
  - testid-lint;
  - tsc.
- **TestFlight verification:** the §3 checklist, run by the operator on the first gate-aware build **before 2026-11-18**, outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **no.**
- Pre-push hook: `FTF_SKIP_SIM_GATE=1` standing posture (D-056); the evidence above replaces it.
