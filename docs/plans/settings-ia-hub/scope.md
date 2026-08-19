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
    **Rollback lever:** flip the flag false server-side; no deploy, no rebuild — the flat v2 list
    stays in the binary until Phase 4.
  - `account.settings_v2` — **retire in Phase 4**. It has been `true` in prod since it shipped; its
    legacy branch at [SettingsScreen.tsx:1509-1549](../../../mobile/src/screens/SettingsScreen.tsx:1508)
    is dead code. Removing it before the split shrinks the surface being refactored.
- **New env vars / `model_config` keys:** none.

## 3. Test scope (mobile test platform)

- [ ] **WAIVED — Maestro.** D-056 (2026-08-15) retired Maestro and the simulator entirely: no flow
  authoring, no flow execution, no `screens/` captures, in any pipeline. This template section
  predates D-056. Replacement evidence below.
- **Structural checks** (`mobile/tests/check-*.js` + `npm run` scripts, matching the 22 existing):
  - `check-settings-ia.js` — every row in plan §4's migration map lands in exactly one page module;
    nothing orphaned or duplicated. This is the check that catches a silently lost setting.
  - `check-settings-nav.js` — `Settings` + all second-level routes register without
    `presentation: 'modal'`, each carries a `HeaderBack`, each page mounts `FeedbackFAB` (#188).
  - `check-settings-testids.js` — the full `settings.*` inventory still resolves;
    `settings.close-btn` is gone everywhere.
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

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. Every endpoint the settings pages call already exists and is already documented. |
| `living-memory/LLD.md` | **yes, at build** | Settings route-naming convention (`Settings*` sub-routes, `settings/<group>` deep-link paths) + the per-page query-ownership rule that replaces the single hoisted-state screen. |
| `docs/architecture.md` | **n/a** | Client IA only; no backend module wiring or data-flow change. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow — an existing screen splits into screens within the existing root stack. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum, or color changes. Stud-tax and pick-pricing enum strings are carried verbatim. |
| `docs/glossary.md` | **n/a** | No new domain term. |
| ADR / `DECISIONS.md` | **yes, at build** | New D-: Settings moves from `presentation: 'modal'` to a pushed page, and feedback #130's header ✕ is **removed rather than reverted** — record so a later session does not re-add a modal citing #130. Also note ADR-008's standing rejection of native inset-grouped list styling still holds (this stays Chalkline). |
| `docs/design/components.md` | **yes, before ship** | § Navigation gains the hub nav-row spec (title + preview subtitle + chevron); § Sheets/modals must stop naming Settings as its modal-screen example. |
| `docs/config-reference.md` | **yes, at build** | `account.settings_hub` added; `account.settings_v2` marked for Phase-4 retirement. |
| `mobile/src/navigation/CLAUDE.md`, `mobile/src/screens/CLAUDE.md` | **yes, at build** | Route list + the new `screens/settings/` subtree. |

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
