# Feature Scope — B2: the launched onboarding flags in first-paint defaults

**Date:** 2026-10-27
**Entry point:** direct ask (head-eng → onboarding-eng 2026-10-27, from Product's pre-launch review `docs/plans/org-bringup/reviews/2026-10-27-prelaunch/README.md` B2; onboarding-pm finding 2). Due in release-lead's queue by 11-03, for the 11-06 binary.
**Builder:** onboarding-eng
**Operator sign-off on waivers:** none needed beyond §1 (c) and §3's TestFlight row, surfaced in the PR description and through head-eng.

**What changes.** `mobile/src/state/useFeatureFlags.ts` `LAUNCHED_FLAG_DEFAULTS` gains `onboarding.v2`, `onboarding.landing`, `mfl.link` and `account.settings_hub`, each `true` as in `config/features.json`.
- **`landing.platform_options` is deliberately NOT baked** (release-lead QA round 1, P1-1). While the server holds it off (the entry-purge window, ask 12), a baked `true` would paint ESPN/MFL chips whose entry sheet dead-ends, because the entry route 404s. Under the planned order the 11-06 binary would bake `false` anyway.
- It's baked in the PR that turns the proof-based sign-in on (ask 16), in both files. Before this, a first-ever boot (no cached map) and an offline first open painted the old Apple-first sign-in and the flat Settings, and stayed there until a revalidate. `espn.signin` is NOT baked: it waits for ask 15, and the guard keeps the two files together when it lands. The server stays authoritative both ways (a cached or fetched `false` overrides a baked key).

## 1. Analytics scope
- [ ] (a) New events: none.
- [ ] (b) Existing events cover it: n/a.
- [x] **(c) WAIVED:** no analytics needed. It changes which already-launched surfaces paint before the first flag fetch, and fires and records nothing new.

## 2. Schema & flag scope
- Tables/columns: none.
- Feature flags: **no new flag and no value change.** Four existing launched flags are added to the client's baked first-paint defaults; `landing.platform_options` is deliberately left out. `docs/config-reference.md`'s rows say so.
- Env / `model_config`: none. **Rollback:** the server flags still kill-switch each surface at the next revalidate; reverting the PR removes the baked keys.

## 3. Evidence scope
- [x] **Structural guard:** `mobile/tests/check-onboarding-flag-defaults.js` (`npm run test:onboarding-flag-defaults`). Pins:
  1. each of the four keys is baked;
  2. with `config/features.json`'s value;
  3. `espn.signin` is baked only once `features.json` carries it true (ask 15);
  4. `landing.platform_options` is not baked;
  5. a server or cached `false` still wins: the store starts from the defaults, a cached map spreads over them, and a fetch replaces the whole map.

  It's dependency-free and comment-stripped. **Sabotage 10/10 red,** each restored byte-identical:
  - round 1's 6: a key left out; a value that differs; `espn.signin` baked early; a key listed twice; a key only in a comment; `features.json` flipped without the defaults;
  - round 2's 4: the store starting empty; the cache merge reversed; the defaults merged under the fetch; the chips flag baked again.
- [ ] Unit tests: none; no backend change.
- [x] **Code-walk:**
  - `useFeatureFlags` starts with `flags: { ...LAUNCHED_FLAG_DEFAULTS }` (`useFeatureFlags.ts`, the `create<FlagState>` initializer).
  - `loadCachedFlags` merges a cached map over these; `revalidateFlags` replaces the map.
  - So a first-ever or offline boot now reads `true` for the four keys from first paint, and any server `false` wins at the next revalidate (pin 5).
- [x] **Manual TestFlight checklist (operator, on the 11-06 build; release-lead QA P3-4):**
  1. **Fresh install, online:** delete the app, reinstall and open it. The username landing shows (not the Apple-first screen). The ESPN/MFL chips appear only if the server has the chips flag on.
  2. **Fresh install, offline:** delete and reinstall, then turn Airplane Mode on before the first open. The same username landing shows, with **no** platform chips (that flag isn't baked).
  3. **Warm launch:** turn Airplane Mode off and relaunch. The landing still shows and matches the server's flags.
  4. **Server false:** during the entry-purge window, while release-lead holds the chips flag off, a fresh install shows no ESPN/MFL chips at any point.
  5. **Settings:** sign in and open Settings. It's the Settings hub (grouped rows), not the flat list.
  6. **Kill switch:** if release-lead ever turns one of the four flags off on the server, the next launch after a successful fetch shows the old surface (pin 5).
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
| `docs/config-reference.md` | **updated** | the four baked flags' rows note the first-paint default; `landing.platform_options`'s row says it's deliberately not baked |

## 5. Ship gate declaration
- **CI green:** `backend-tests`, `mobile-typecheck` (with the `check-*.js` loop), testid-lint and `web-structure`.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** the operator runs §3's checklist on the 11-06 build.
- Express lane declared by the operator? No.
