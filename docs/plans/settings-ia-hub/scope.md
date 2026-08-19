# Feature Scope — Settings IA: hub page + second-level pages

**Date:** 2026-08-18
**Entry point:** direct operator ask (review prod Settings; reorganize into a hub + sub-pages; modal → page)
**Builder:** session `session-2026-08-13-notif-ship` (planning only — no code written)
**Operator sign-off on waivers:** **pending** — waivers in §1 and §3 need a yes before build starts
**Operator IA decisions (2026-08-18):** Sign out → Account page · Ranking and Trade values stay two pages · `account.settings_v2` retired in Phase 4

Plan: [`plan.md`](plan.md).

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.**

| Event | What it answers here |
|---|---|
| `screen_viewed {screen, prev_screen, tab}` — emitted for every route change at [RootNav.tsx:395](../../../mobile/src/navigation/RootNav.tsx:395) | Which settings groups users open, which they never find, and the hub→page path they take. New routes (`SettingsAccount`, `SettingsNotifications`, …) produce distinct `screen` values automatically; `analytics_taxonomy.py` puts no allowlist on the value. |
| `notif_denied_settings_tapped` (existing, [SettingsScreen.tsx:1034](../../../mobile/src/screens/SettingsScreen.tsx:1034)) | Denial-recovery funnel, unchanged — the row moves pages, the event does not change. |

**No new events.** Confirm `screen_viewed` stays classified in `analytics_queries.NON_INTENT_EVENTS`
so seven new routes do not inflate intent metrics.

- [ ] **WAIVED:** no per-row `settings_changed` event is being added. Each control's own effect is
  already observable server-side (prefs PUTs, stud-tax/pick-pricing writes, rank-method POST). If the
  operator wants group-level engagement beyond `screen_viewed`, say so before Phase 3.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. No backend change of any kind — this is client IA only.
  → `docs/data-dictionary.md` n/a.
- **New/changed feature flags:**
  - `account.settings_hub` — **default `false`**. Registered in `config/features.json` +
    `backend/feature_flags.py` `FLAG_KEYS` + `docs/config-reference.md`.
    **Graduation criterion:** one operator TestFlight pass against the plan §9 checklist with no P0.
    **Rollback lever — CORRECTED 2026-08-19, the build disproved the original claim.** The flag
    covers the *content* only: flag false mounts `SettingsScreen`'s flat list again, server-side,
    with no deploy and no rebuild (the flat list stays in the binary until Phase 4). It does **not**
    cover the *presentation*. `presentation: 'modal'` was dropped from the `Settings` route
    registration in `RootNav.tsx`, outside the flag, so the sheet→page flip and the loss of
    swipe-down-to-dismiss apply in **both** flag states. Restoring the old gesture requires a code
    change and a new build; the flag cannot do it.
    **Operator decision (2026-08-19): accepted, deliberately.** One navigation topology and one
    testID surface, not two — a flag-conditional `presentation` would mean the modal and the page
    disagree about how `navigateFromSettings` escapes, and `settings.close-btn` would have to live
    on and off depending on flag state, which no structural check can then assert. The reasoning is
    that the presentation bugs are the flat list's bugs too: **F5** (Back from SleeperConnect lands
    on the tabs) exists because the page-sheet forced `navigateFromSettings` to `goBack()` before
    every outbound link, and **F6** (no `FeedbackFAB` on Settings) exists because #188 exempts
    modals and Settings was one. Fixing them only on the flag-on path would leave the shipped
    surface broken for the exact users a rollback is meant to protect.
  - `account.settings_v2` — **retire in Phase 4**. It has been `true` in prod since it shipped; its
    legacy branch at [SettingsScreen.tsx:1509-1549](../../../mobile/src/screens/SettingsScreen.tsx:1508)
    is dead code. Removing it before the split shrinks the surface being refactored.
- **New env vars / `model_config` keys:** none.

## 3. Test scope (mobile test platform)

- [ ] **WAIVED — Maestro.** D-056 (2026-08-15) retired Maestro and the simulator entirely: no flow
  authoring, no flow execution, no `screens/` captures, in any pipeline. This template section
  predates D-056. Replacement evidence below.
- **Structural checks — BUILT AND PASSING** (2026-08-19; 59/59 assertions green):
  - `mobile/tests/check-settings-ia.js` (`npm run test:settings-ia`) — all 34 rows of plan §4's
    migration map resolve to exactly one page module; nothing orphaned, nothing duplicated, and the
    four moves asserted by name. This is the check that catches a silently lost setting.
  - `mobile/tests/check-settings-nav.js` (`npm run test:settings-nav`) — no settings route carries
    `presentation: 'modal'`; each registers a `HeaderBack`; every page mounts `FeedbackFAB` (#188).
  - `mobile/tests/check-settings-testids.js` (`npm run test:settings-testids`) — the full
    `settings.*` inventory still resolves; `settings.close-btn` is gone from `mobile/src` **and**
    from the two Maestro capture flows that anchored on it.
  - **Verified by mutation, not by reading.** Each check was proven to fail with an accurate message
    against a deliberate regression: restoring `presentation: 'modal'` on the `Settings` route,
    swapping the Sign out / Delete account order on the Account page, and renaming a shipped
    `settings.*` testID. A check that has never gone red is not evidence.
  - **Caveat:** like the other 56 `check-*.js` suites these are `npm run`-only and gate nothing in
    CI (the standing open item in `NEXT.md`). They have to be run by hand or by an agent.
- **Code-walk proof** (file:line-cited, written into the Phase-2 build doc): `confirmDeleteAccount`,
  sign-out `navigation.replace('SignIn')`, account-only `navigation.replace('LeaguePicker')`, and the
  three `confirmDisconnect*` handlers traced through the new push stack.
- **Manual TestFlight checklist:** 10 items, plan §9. Covers the swipe-gesture change, back-stack
  behavior after Verify account, hub preview freshness, and the disconnect rows' new home.
- **`testID`s added/renamed:** added `settings.hub.<group>`, `settings.hub.identity`,
  `settings.account.sign-out`; **removed** `settings.close-btn`; all other `settings.*` IDs move with
  their row unchanged. Gated by `mobile/scripts/testid-lint.sh` in CI.
- **Capture delta:** none possible — `screens/` is frozen at 2026-08-11 per D-056.
- **Backend pytest:** none. No backend code changes.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

**Filled in 2026-08-19, after the build.** "Done" means the file is changed on
`feat/settings-ia-hub`; nothing here is merged to `main`.

| Doc | Status | What happened |
|---|---|---|
| `docs/api-reference.md` | **n/a — confirmed** | No route added, renamed, removed, or contract-changed. `git diff origin/main...HEAD` touches no `backend/server.py` route; the only backend files in the diff are `feature_flags.py` (one `FLAG_KEYS` entry) and the flags fixture. |
| `living-memory/LLD.md` | **NOT DONE — still owed** | The settings route-naming convention (`Settings*` sub-routes, `settings/<group>` deep-link paths in `mobile/src/utils/deepLinks.ts`) and the per-page query-ownership rule that replaces the single hoisted-state screen are unrecorded. Carry into the merge. |
| `docs/architecture.md` | **n/a — confirmed** | Client IA only; no backend module wiring or data-flow change. |
| `living-memory/HLD.md` | **n/a — confirmed** | No new module, client, or major flow — one existing screen split into screens inside the existing root stack. |
| `docs/cross-client-invariants.md` | **n/a — confirmed** | No shared constant, enum, or color changed. Stud-tax and pick-pricing enum strings were carried verbatim into `sections/TradeValuesSection.tsx`. |
| `docs/glossary.md` | **n/a — confirmed** | No new domain term. |
| `living-memory/DECISIONS.md` | **done 2026-08-19** | **D-079** — Settings moves from `presentation: 'modal'` to a pushed page; #130's ✕ is removed rather than reverted; the flip is deliberately outside the flag; ADR-008's rejection of native inset-grouped list styling still stands. No formal ADR filed — this is an IA/presentation change inside one existing surface, not an architecture decision. |
| `docs/design/components.md` | **done 2026-08-19** | § Navigation gains the **SettingsNavRow** spec (56pt row, `type.title` sentence-case title over a `bodySm` preview, 16px chevron, the honest-empty `navPreviewNone` variant, and the identity block + `verifyChip`), with the reason the title is 16px rather than the 11px `type.label` every other settings row key uses. § Sheets/modals no longer names Settings; the #130 rule is restated as binding the presentation, and the two routes still on `presentation: 'modal'` (`FeedbackInbox`, `SleeperConnect`) are recorded as **not** carrying the control — an open #130 gap, not a satisfied spec. |
| `docs/config-reference.md` | **done — phase 0** (`4ea6895`) | `account.settings_hub` registered, default `false`; `account.settings_v2` marked "slated for retirement in Phase 4". **One stale line to fix at merge:** the `account.settings_hub` row still reads "Rollback: flip false server-side, no deploy needed", which §2 above now corrects — the flag does not restore the modal presentation. |
| `mobile/src/navigation/CLAUDE.md` | **done — phase 1** (`0e07f96`) | Records that Settings is a push, not a modal, that `settings.close-btn` is gone, and why re-introducing the modal re-introduces the `navigateFromSettings` hack. The seven second-level routes are **not** individually listed — minor gap. |
| `mobile/src/screens/CLAUDE.md` | **NOT DONE — still owed** | The new `mobile/src/screens/settings/` subtree (hub + 7 pages + 12 section modules + `Row.tsx` + `styles.ts`) is undocumented there. Carry into the merge. |
| `screens/CLAUDE.md` | **done 2026-08-19** (not in the original table) | The `settings` index row now says the surface is a tree, and that the 2026-08-10 captures predate both the ESPN/MFL disconnect rows (`3293f4a`) and this IA change. |

## 5. Ship gate declaration

- **Simulator-gate tier:** **n/a under D-056** — the tier matrix in `docs/runbook.md` §
  "Pre-ship simulator gate" is history. `FTF_SKIP_SIM_GATE=1` is the standing posture; `githooks/pre-push`
  still checks the retired marker.
- **Evidence at merge:** CI green (`pytest backend/tests`, `tsc --noEmit`,
  `mobile/scripts/testid-lint.sh`) + the three structural checks run + the code-walk proof filed, all
  logged in `living-memory/TEST_LEDGER.md` with the `FTF_SKIP_SIM_GATE=1` note.
- **Operator deviation:** none requested. This is **not** an express-lane change — it touches
  feature-flag surface and every account/data-rights control on the app, so the full gates apply
  unless the operator declares otherwise.

## 6. Bright-line check

Per CLAUDE.md § Conventions: a change touching **feature-flag surfaces** is not a quick fix. This adds
`account.settings_hub` and retires `account.settings_v2`, and it relocates the delete-account and
platform-credential controls. Full gates apply.
