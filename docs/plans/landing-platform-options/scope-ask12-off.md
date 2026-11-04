# Feature Scope — `landing.platform_options` OFF until verified ESPN/MFL sign-in (operator ask 12)

**Date:** 2026-11-02
**Entry point:** direct ask. The operator said yes to ask 12 in head-eng's session (11-02): switch the old sessionless ESPN/MFL entry off before the 11-06 binary.
**Builder:** onboarding-eng (relayed by head-eng)
**Operator sign-off on waivers:** not needed (no waivers)

---

## What changes

`config/features.json` sets `landing.platform_options` to **false**, so `main` matches prod after release-lead's ask-12 flip. Merging deploys the same value, so either order ends in the same state.
- **Why:** `POST /api/entry/platform` mints unverified `entry:*` accounts (legal M11) until #430's proof-based sign-in is deployed. Off stops new ones. It's also step 1 of the entry purge (runbook, `scripts/purge_entry_users.py`).
- **When it comes back on:** only after #430 (+ #477, #478, #518) is deployed and the purge has run. Then ask 16 turns it back on, with `espn.signin` only if the operator's R1 check is PAIR_BOUND.
- **What users see while it's off:**
  - the app's landing is the plain Sleeper username form, with no chip or tile row (`SignInScreen.tsx` `platformPickerShown` needs this flag, and at least 2 live platforms);
  - Continue with Apple stays below it;
  - the entry route 404s;
  - Settings › link an ESPN or MFL league is unaffected (it uses `/api/espn/link` and `/api/mfl/*`, not this flag);
  - the web never read this flag (`WEB_PLATFORM_ENTRY = false`).

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** this turns a surface off. `signin_attempted` / `signin_failed` with `method` = `espn` / `mfl` simply stop arriving from the landing; there's nothing new to measure.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- Changed feature flag: **`landing.platform_options` true → false.**
  - Updated: `config/features.json` (value and `_comment_`), `docs/config-reference.md` (default, why, and when it comes back), and the release-derived fixtures that mirror it (`backend/tests/fixtures/flags/release.json`, `onboarding-v2.json`, `profiles-on.json`; their mirror tests require them to match release except for each one's own key).
  - Already in `FLAG_KEYS`. Not baked into mobile first paint (`check-onboarding-flag-defaults.js` pin 4), so the binary follows the server.
  - **Graduation:** back on at ask 16, then delete after one clean TestFlight cycle.
- New env vars / `model_config` keys: none. Rollback lever: the flag itself (true again, via config or `FTF_FLAGS` + `POST /api/feature-flags/reload`), but only on the conditions above.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-landing-platform-options.js` §7 now checks the flag is **registered** (true or false), not that it's true; the value is the operator's. Everything else it pins (the row's dual gate, the per-platform flags, the de-flag fallback to Sleeper) is unchanged and is what makes "off = no row" true. All 136 `check-*.js` pass.
- [x] **Unit tests:** no new test. The flag-touching backend tests run green with the flipped fixtures (TEST_LEDGER). `test_entry_platform_route.py` patches its own flags, so it covers the route both ways.
- [x] **Code-walk proof** (off = the plain form and a 404, nothing else):
  1. The app reads the flag from the server (`useFlag('landing.platform_options')`, `SignInScreen.tsx`). It isn't baked, so first paint and every refresh see `false`.
  2. `platformPickerShown = landingOn && platformOptionsFlag && platformChips.length >= 2`. With the flag false it's false, so no chip or tile row renders and `nonSleeperEntry` is false. The username form shows, and the de-flag fallback resets any selected platform to Sleeper.
  3. The ESPN/MFL entry sheets open only from that row's panel (`signin.platform-link-btn`), so nothing reaches `entryPlatformMint`.
  4. `server.py` `entry_platform` returns 404 first thing when `is_enabled("landing.platform_options")` is false, so an old binary can't mint either.
- [x] **Manual TestFlight checklist** (operator, any binary, after the flip is live):
  1. Fresh install. Expect the Sleeper username form with no Sleeper / ESPN / MFL chips or tiles above it, and Continue with Apple below it.
  2. Settings › Leagues › link an ESPN or MFL league. Expect it to work as before (it doesn't use this flag).
- testIDs added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | `/api/entry/platform`'s row already says it 404s while the flag is off; no contract change |
| `docs/config-reference.md` | updated | the `landing.platform_options` row: false, why, and when it comes back |
| `living-memory/LLD.md` | n/a | no convention change |
| `docs/architecture.md` | n/a | no wiring change |
| `living-memory/HLD.md` | n/a | no new module or flow |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | n/a | no new term |
| ADR or `DECISIONS.md` entry | n/a | the operator's decision (ask 12), recorded in the flag comment and the config reference |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with the `check-*.js` suites) + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-11-02 entry.
- **Merge:** on the operator's go, in release-lead's session. The prod flip itself (config or `FTF_FLAGS` + reload, then the restart that sets the purge `--cutoff`) is release-lead's, per the runbook's entry-purge steps.
- Express lane declared by the operator? No.
