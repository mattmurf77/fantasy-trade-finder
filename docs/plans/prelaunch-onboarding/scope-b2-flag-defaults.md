# Feature Scope — B2: the launched onboarding flags in first-paint defaults

**Date:** 2026-10-27
**Entry point:** direct ask (head-eng → onboarding-eng 2026-10-27, from Product's pre-launch review `docs/plans/org-bringup/reviews/2026-10-27-prelaunch/README.md` B2; onboarding-pm finding 2). Due in release-lead's queue by 11-03, for the 11-06 binary.
**Builder:** onboarding-eng
**Operator sign-off on waivers:** none needed beyond §1 (c) and §3's TestFlight row, surfaced in the PR description and through head-eng.

**What changes.** `mobile/src/state/useFeatureFlags.ts` `LAUNCHED_FLAG_DEFAULTS` gains `onboarding.v2`, `onboarding.landing`, `landing.platform_options`, `mfl.link` and `account.settings_hub`, each `true` as in `config/features.json`. Before this, a first-ever boot (no cached map) and an offline first open painted the old Apple-first sign-in and the flat Settings, and stayed there until a revalidate. `espn.signin` is NOT baked: it waits for ask 15, and the guard keeps the two files together when it lands. The server stays authoritative both ways (a cached or fetched `false` overrides a baked key).

## 1. Analytics scope
- [ ] (a) New events: none.
- [ ] (b) Existing events cover it: n/a.
- [x] **(c) WAIVED:** no analytics needed. It changes which already-launched surfaces paint before the first flag fetch, and fires and records nothing new.

## 2. Schema & flag scope
- Tables/columns: none.
- Feature flags: **no new flag and no value change.** Five existing launched flags are added to the client's baked first-paint defaults. `docs/config-reference.md`'s five rows say so.
- Env / `model_config`: none. **Rollback:** the server flags still kill-switch each surface at the next revalidate; reverting the PR removes the baked keys.

## 3. Evidence scope
- [x] **Structural guard:** `mobile/tests/check-onboarding-flag-defaults.js` (`npm run test:onboarding-flag-defaults`). Pins:
  1. each of the five keys is baked;
  2. with `config/features.json`'s value;
  3. `espn.signin` is baked only once `features.json` carries it true (ask 15).

  It's dependency-free and comment-stripped. **Sabotage 6/6 red,** each restored byte-identical: a key left out; a value that differs; `espn.signin` baked early; a key listed twice; a key only in a comment; `features.json` flipped without the defaults.
- [ ] Unit tests: none; no backend change.
- [x] **Code-walk:**
  - `useFeatureFlags` starts with `flags: { ...LAUNCHED_FLAG_DEFAULTS }` (`useFeatureFlags.ts`, the `create<FlagState>` initializer).
  - `loadCachedFlags` merges a cached map over these; `revalidateFlags` replaces the map.
  - So a first-ever or offline boot now reads `true` for the five keys from first paint, and any server `false` wins at the next revalidate.
- [x] **Manual TestFlight checklist (operator, on the 11-06 build):**
  1. Delete the app and reinstall it. Turn on Airplane Mode before the first open, then open it. The landing shows the username field with the Sleeper · ESPN · MFL chips, not the Apple-first screen.
  2. Turn Airplane Mode off and relaunch. The same landing shows.
  3. Sign in and open Settings: it's the Settings hub (grouped rows), not the flat list.
- `testID`s: none added.

## 4. Docs scope
| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change |
| `living-memory/LLD.md` | n/a | the "launched features fail open" rule already exists (`useFeatureFlags.ts` header); this applies it |
| `docs/architecture.md` | n/a | no module wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant changes; flag values stay in `features.json` |
| `docs/glossary.md` | n/a | no new term |
| ADR / `DECISIONS.md` | n/a | it follows the existing #115 fail-open rule |
| `docs/config-reference.md` | **updated** | the five flags' rows note the baked first-paint default |

## 5. Ship gate declaration
- **CI green:** `backend-tests`, `mobile-typecheck` (with the `check-*.js` loop), testid-lint and `web-structure`.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** the operator runs §3's checklist on the 11-06 build.
- Express lane declared by the operator? No.
