# Feature Scope — BL-10: in-app feedback for the public

**Date:** 2026-10-20
**Entry point:** direct ask: `head-product` App Store launch-readiness review (2026-10-20), item BL-10; operator decisions BL-10 ("in app feedback stays") and BL-2 (support address)
**Builder:** `launch-onboarding-pm-1` for `onboarding-pm` (spec only; build later by `onboarding-eng` under `head-eng`, who owns `FeedbackFAB` and `RootNav`)
**Operator sign-off on waivers:** signed 2026-10-22 (operator, in head-product's session; quoted verbatim: "I sign off on #354's waivers."). Covers W-P28-1, W-P28-2, W-BL10-1, W-BL10-2, W-M7-1, W-M7-2 and W-ALL-1 ([prd.md §9](prd.md#9-decisions-needed)). **W-BL10-2 has lapsed:** head-eng confirmed D-2's 403 and Product chose D-2(a), so a pytest is required.

Requirements, verified facts, copy inventory (F1-F18) and acceptance criteria:
[prd.md §6](prd.md#6-bl-10-in-app-feedback-for-the-public). Ownership: the Settings row placement is
`onboarding-pm`'s IA call (P10) with `ux-lead`'s review; words are `marketing-lead`'s; visuals are
`design-lead`'s; `FeedbackFAB` and `RootNav` are `head-eng`'s shared surface.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** —
- [x] **(c) WAIVED — no analytics needed because:** this rewrites words, moves one Settings row and
  keeps the FAB in App Store builds. It adds no new user action. Submissions are already measured
  by the server-fired `feedback_submitted` (`backend/analytics_taxonomy.py:839`, emitted at
  `backend/server.py:11150-11158` with `severity` and `screen` props, for signed-in, non-duplicate
  notes), and visits to the inbox are already visible as `screen_viewed` for the `FeedbackInbox`
  route (emitted on every route change, `mobile/src/navigation/RootNav.tsx:538`). No property or classification changes. (Waiver
  **W-BL10-1**.)

## 2. Schema & flag scope

- New/changed tables or columns: **none.** → `docs/data-dictionary.md` n/a.
- New/changed feature flags: **none. Recommendation, not silence:** ship the row move and the copy
  unflagged.
  - The flag-off state would be today's defect: a count pill on every screen for notes a public
    user can't open (`mobile/src/components/FeedbackFAB.tsx:126`, `:152-156`) and a failure message
    pointing at a section they can't see (`mobile/src/components/FeedbackSheet.tsx:63-64`). A kill
    switch has no safe state to return to.
  - ADR-008's flag-everything rule was scoped to the 2026-07 remediation wave; its exception for
    doc/legal copy (`docs/adr/adr-008-teardown-remediation-wave.md:21-23`) is the closer precedent.
  - Rollback is the next build. The change touches no data, no API, no server state.
  - If `head-product` wants a flag anyway, that is decision **D-4** in prd.md.
- **Existing flags this feature reads, unchanged:** `testing.stage_users` (`false`,
  `config/features.json:206`) keeps gating the Testing hub row
  (`mobile/src/screens/settings/SettingsHubScreen.tsx:333-340`), the flat Testing section
  (`mobile/src/screens/SettingsScreen.tsx:1480`) and the "Test stages" row
  (`settings/sections/TestingSection.tsx:66-81`). `account.settings_hub` (`true`,
  `config/features.json:194`) picks the hub (`mobile/src/navigation/RootNav.tsx:272-275`); the flat
  list is its rollback, so it gets the row too.
- **Planned build-time exclusion retired:** the "S3 PRD-01 item 3" plan to compile the FAB out of
  App Store builds (`FeedbackFAB.tsx:74-80`, `RootNav.tsx:628-632`) is superseded by the operator's
  BL-10 decision. No `EXPO_PUBLIC_*` build-profile gate is added. `head-eng` deletes those plan
  comments in the build (D-5).
- New env vars / `model_config` keys: **none.**
- **API contract unchanged:** `severity` stays `bug | polish | idea` (`backend/server.py:11101-11102`).
  **Exception:** if `head-product` accepts D-2(a) (exempt `/api/feedback` from the verified-write
  gate), the route's `403 verification_required` response goes away for that route. That is an API
  contract change: §4's api-reference row flips to "updated", a pytest is owed, and the change is
  not express-lane.

## 3. Evidence scope

D-056: no simulator, no Maestro, no screen captures, for any part of this change.

- [x] **Structural guard:** new `mobile/tests/check-feedback-public.js`, with
  `"test:feedback-public": "node tests/check-feedback-public.js"` in `mobile/package.json` (beside
  `test:feedback-capture`, `mobile/package.json:45`). Dependency-free beyond the project's own
  TypeScript, which it uses to walk the AST so comments are excluded (the pattern
  `mobile/tests/check-settings-nav.js` uses). CI runs it automatically
  (`.github/workflows/ci.yml:42-48`). It pins:
  1. **No tester vocabulary in user-visible text.** No string literal, template literal or JSX text
     matching `/Testing\s*→|Test feedback|TestFlight|\btesters?\b/i` in `FeedbackSheet.tsx`,
     `FeedbackFAB.tsx`, `FeedbackInboxScreen.tsx`, `state/useFeedback.ts` (the share export),
     `settings/sections/AboutSection.tsx`, the `FeedbackInbox` screen options in `RootNav.tsx`, or
     the feedback row in `SettingsScreen.tsx`'s `aboutSection`. Comments are exempt.
  2. **Row placement.** A navigation to `FeedbackInbox` exists in `settings/sections/AboutSection.tsx`
     and in `SettingsScreen.tsx`'s `aboutSection`; none exists in `settings/sections/TestingSection.tsx`
     or in `SettingsScreen.tsx`'s `testingSection`; and no `FeedbackInbox` navigation sits inside a
     conditional whose test mentions `__DEV__` or `stageUsersEnabled`.
  3. **One support address.** Exactly one string literal equal to `fleecedapp@gmail.com` in
     `mobile/src` (the exported constant), written with U+0040; no U+FF20 anywhere in `mobile/src`;
     `FeedbackSheet.tsx` imports the constant.
  4. **Severity contract.** The sheet's option values are exactly `['bug','polish','idea']`, the
     `FeedbackSeverity` union is unchanged, and the three label maps (`FeedbackSheet.tsx`,
     `FeedbackInboxScreen.tsx`, `useFeedback.ts` export) give the same label for each value.
  5. **FAB stays in release builds.** The `<FeedbackFAB activeScreen={activeScreen} />` mount in
     `RootNav.tsx` is not inside a conditional on `__DEV__` or any `process.env.EXPO_PUBLIC_*`.
  6. **`testID`s kept:** `feedback.fab`, `feedback.note-input`, `feedback.save-btn`,
     `feedback.save-error`, `feedback.char-count`, `feedback.note-error`, the
     `feedback.severity.${value}` template, and `settings.test-stages` still exist.
  7. **Only if D-1(b) is accepted:** `FeedbackFAB`'s mount effect calls `retrySync()` after
     `hydrate()` resolves.
- [x] **Existing suites the build must update** (or CI fails):
  - `mobile/tests/check-settings-ia.js:116` maps the "Test feedback" row to owner
    `TestingSection.tsx` with marker `'>Test feedback<'`. Move it to owner `AboutSection.tsx` with
    the new row's `testID` as marker.
  - `mobile/tests/check-settings-testids.js` keeps the `settings.*` inventory in two lists,
    shipped (`:48-60`) and new (`:74-83`); add the new row's `testID` (proposed
    `settings.feedback-inbox`) where its conventions put a newly added ID.
  - `mobile/tests/check-feedback-capture.js` pins the save path and the 8000-character cap; it pins
    no copy, so the F1 rewrite shouldn't trip it. Re-run it.
- [ ] **Unit tests:** **REQUIRED** (W-BL10-2 lapsed; D-2(a) chosen). Add a pytest: `POST /api/feedback`
  from an unverified session succeeds (201) and is stored unattributed (`user_id` NULL, or whatever
  attribution `head-eng` specifies), while a verified session's note stays attributed.
- [x] **Code-walk proof** (file:line at `678834ab`, the behavior this change starts from; the
  builder appends the same walk against the built files):
  1. **Mount.** The global FAB mounts inside `Main` at `mobile/src/navigation/RootNav.tsx:633`,
     unconditionally for authed users; root-stack pushes mount their own (e.g.
     `settings/SettingsHubScreen.tsx:347`, `settings/SettingsAboutScreen.tsx:42`).
  2. **Open.** `FeedbackFAB.tsx:142` sets `sheetOpen`; the sheet renders at `:160-164` with
     `defaultScreen={activeScreen}`, the current route name (`RootNav.tsx:307-311`).
  3. **Save.** `FeedbackSheet.tsx:123-156` → `useFeedback.add` (`state/useFeedback.ts:152`) persists
     the note to AsyncStorage first, then `_syncOne` (`:96-99`) → `submitFeedback`
     (`api/feedback.ts:41`) → `POST /api/feedback`.
  4. **Server.** `backend/server.py:11066-11067` route + verified-write gate (`:2653-2660`,
     `:2663-2680`) → validation `:11095-11102` (severity must be `bug|polish|idea`) → best-effort
     session lookup `:11112-11122` → `save_feedback` `:11130` → `feedback_submitted` `:11150-11158`.
  5. **Failure.** `saved.synced === false` → `setSaveFailed(true)` (`FeedbackSheet.tsx:141-147`) →
     `SAVE_FAILED_MESSAGE` renders (`:249-252`); the draft stays.
  6. **Retry.** `App.tsx:200-207` calls `retrySync()` on every AppState change to `active`;
     `retrySync` (`useFeedback.ts:236-255`) re-POSTs each unsynced note. The inbox's "Retry sync"
     calls it too (`FeedbackInboxScreen.tsx:77-85`). Cold launch: `hydrate()` (`useFeedback.ts:125-150`)
     and the FAB's mount effect (`FeedbackFAB.tsx:109-112`) don't call it. Hence BL10-R3 and D-1.
  7. **Reachability today.** Hub: About group → `SettingsAbout` (`SettingsHubScreen.tsx:320-328`;
     `RootNav.tsx:699`) renders `GuideSection` + `AboutSection` (`SettingsAboutScreen.tsx:39-40`),
     neither of which opens the inbox. The only hub entry is `TestingSection.tsx:53-65`, reached
     through the Testing row gated at `SettingsHubScreen.tsx:333`. Flat: the inbox row lives in
     `testingSection` (`SettingsScreen.tsx:1018-1053`, navigate at `:1025`), mounted only under
     `__DEV__ || stageUsersEnabled` (`:1480`) in the live `settings_v2` branch.
  8. **Pill.** `FeedbackFAB.tsx:126` → `openFeedbackCount` (`utils/feedbackBadge.ts:30-36`) excludes
     closed notes and the resolved statuses `fixed`/`shipped`/`declined`. The inbox lists every
     non-closed note (`FeedbackInboxScreen.tsx:69`), so a `fixed` note is listed but not counted.
- [x] **Manual TestFlight checklist** (runtime proof matters: this is the first public build of the
  surface). `release-lead` supplies the build number; the operator runs it on a **fresh non-tester
  account** (signed in with Apple, device not on the tester allowlist, so `testing.stage_users` is
  off) and logs the outcome in TEST_LEDGER.
  1. Install build **[build number from release-lead]** from TestFlight; sign in with a fresh Apple
     account. Expected: the FAB floats bottom-right on Home, Rank, Trades and League tabs, and on
     Settings (a root-stack push).
  2. Tap the FAB. Expected: the sheet shows `marketing-lead`'s approved title, subline and labels;
     `fleecedapp@gmail.com` appears with an ordinary `@`; nothing mentions Testing, Test feedback,
     TestFlight or testers.
  3. Turn on airplane mode. Type a note and Save. Expected: the sheet stays open with the draft, and
     the approved "not sent" text says the note is kept and when it will send. No Settings → Testing
     pointer.
  4. Cancel the sheet. Expected: the FAB pill shows **1**.
  5. Turn off airplane mode. Send the app to the background and bring it back (and, if D-1(b) ships,
     also force-quit and relaunch). Wait 10 seconds. Expected: the note sends without any tap.
  6. Open Settings. Expected: no "Testing" row anywhere on the hub.
  7. Tap Help & about. Expected: the feedback row is present with the approved title; tap it.
     Expected: the inbox opens, titled with the approved public name (once, not twice), and the note
     from step 3 shows as sent (no "HTTP" text anywhere).
  8. Compare the pill with the inbox. Expected: pill = number of inbox notes whose status line is
     not "Fixed — in next update".
  9. Deep link `settings/testing` (if D-7 gates it). Expected: no rows are shown.
  10. **Regression, tester device:** on a device with `testing.stage_users` on, Settings shows the
      Testing row and "Test stages"; the feedback row is under Help & about, not under Testing.
- [ ] **WAIVED because:** — (nothing else waived; only W-BL10-1 remains waived, W-BL10-2 has lapsed)
- `testID`s added/renamed: **added** one, the new About row (proposed `settings.feedback-inbox`).
  **Renamed: none.** All IDs in pin 6 stay, because `mobile/scripts/testid-lint.sh` (kept by D-056)
  cross-checks them against the historical flow files under `mobile/.maestro/`, which D-056 keeps
  but never runs.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **update at build (D-2(a))** | D-2(a) is chosen, so the `POST /api/feedback` contract changes (no route is added or removed). Two places change, the rows [prd.md §9](prd.md#9-decisions-needed) D-2 names: the verified-write gate list, which names `feedback` today (`docs/api-reference.md:146`), and the `POST /api/feedback` row (`:984`). |
| `docs/data-dictionary.md` | n/a | No schema change. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | No convention shifts. The one-constant-per-client rule for the support address is recorded in cross-client-invariants, its natural home. |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No module or data-flow change. |
| `living-memory/HLD.md` (architecture genuinely shifted) | n/a | No architecture change. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **update at build** | New "Support contact address" section (value, three homes, ASCII-only rule; owner `head-eng`), added once with P28. The feedback status labels table (`:1131-1144`) changes only if `marketing-lead` renames a chip (F15). |
| `docs/glossary.md` (new domain term) | n/a | No new term. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **update at build** | (1) BL-10 supersedes the FAB production-build exclusion (S3 PRD-01 item 3); (2) the inbox row moves to Help & about, with the rejected alternative (hiding the pill) and why. Next ID = max `D-` + 1 at build time. |
| `mobile/src/screens/CLAUDE.md` | **update at build** | The `FeedbackInboxScreen` row (`:53`) says "Tester feedback inbox ... Reached from Settings → Test feedback"; it becomes the public inbox reached from Settings → Help & about. The `TestStagesScreen` row (`:58`) stays. |
| `mobile/src/navigation/CLAUDE.md` | **check at build** | `:5` describes the global FAB mount; it states no removal plan, so likely no change. Confirm. |
| `mobile/src/components/CLAUDE.md` | **check at build** | `FeedbackFAB` (`:74`) and `FeedbackSheet` (`:75`) rows; update if the support-address constant lives in `components/`. |
| `mobile/src/state/CLAUDE.md` | **update if D-1(b)** | The `useFeedback.ts` row (`:26`) says `retrySync()` re-attempts on foreground; add cold launch if D-1(b) ships. |
| `docs/design/components.md` | **design-lead's call** | Only if the About row or the sheet's support line needs a new variant. The inbox modal's missing #130 close control (`:77`) is `ux-lead`'s (prd.md §6.4). |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (runs `tsc --noEmit` and every
  `mobile/tests/check-*.js`, including the new guard and the updated `check-settings-ia.js` and
  `check-settings-testids.js`) + `web-structure` + `maestro-testid-lint` (testid-lint only), all
  passing on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry with the structural-suite counts,
  the code-walk link, and the TestFlight checklist result with the build number. `githooks/pre-push`
  still checks the retired simulator marker; under D-056 push with `FTF_SKIP_SIM_GATE=1` and name
  this evidence instead.
- **TestFlight verification:** the §3 checklist, run by the operator on a fresh non-tester account,
  outcome logged in TEST_LEDGER **before** the build is submitted for App Store review.
- **Copy and review gates:** `marketing-lead` copy (F1-F18) in place; `design-lead` visuals approved;
  `ux-lead` has reviewed the row move (P10) and D-6/D-7; D-1 and D-2 decided.
- Express lane declared by the operator? **No.** Full gates. If D-2(a) is accepted the change
  touches an API contract and cannot be express-laned without an explicit confirming yes from the
  operator.
