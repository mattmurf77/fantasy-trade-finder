# Feature Scope — Three platform tiles on the sign-in landing

**Date:** 2026-11-01
**Entry point:** direct ask. The operator's design review, 11-01, via head-product → head-eng: "For sign in it should have three tiles. Sleeper espn mfl"
**Builder:** onboarding-eng (spec: design-lead; render: [`signin-three-tiles-render.png`](signin-three-tiles-render.png), design-lead's as-built render of `db5bd224` through react-native-web at SE 375×667, three tiles and two tiles (ESPN off), not a device capture)
**Operator sign-off on waivers:** not needed (no waivers). Open item: the operator's approval of the look (three tiles and the two-tile ESPN-off state). The words are final: marketing-lead's copy §6 addendum 16.

---

## What changes

The landing's platform chips (`SignInScreen.tsx` `platformRow` / `platformChip`) become equal tiles. What each one does is unchanged.
- **Row:** a radiogroup with one tile per **live** platform, from `platformChips` (Sleeper; ESPN on `espn.link && espn.signin`; MFL on `mfl.link`). It shows only under `platformPickerShown`: `onboarding.landing && landing.platform_options`, with at least 2 tiles.
- **Tile:** ink-1, 64pt minimum height, the lineStrong a11y border, `radii.md`. The name is in `type.title`, chalk, with a `type.bodySm` chalk-dim line under it.
- **Selected:** the ice border and a 3×14 ice tick at the top right. The name doesn't change colour.
- **Words** (marketing-lead, copy §6 addendum 16): the dim lines are "Username" / "Sign in" / "Sign in" (an SE tile fits about 10 characters).
- **Accessibility:** each tile is a radio with `selected` state. The labels are "Sleeper, sign in with your username, no password needed" · "ESPN, sign in with your ESPN account or a league ID" · "MyFantasyLeague, sign in with your account or a league ID". The testIDs `signin.platform-${p}` are unchanged.
- **Unchanged:** selecting a tile swaps the form exactly as the chips did (`selectEntryPlatform` → `nonSleeperEntry`). #507's "or" and Continue with Apple stay below.
- **Two fixes from design-lead's as-built render (head-eng, 11-01):**
  - **SE fit:** the session-expired notice's bottom margin is `space.md - 5`, so the returning-user landing is 647pt, the SE's full height: the Terms line no longer needs a scroll.
  - **Explainers claim only what the door does:** ESPN's is now "ESPN dynasty leagues are supported. Sign in to ESPN, or enter a league ID." (ESPN sign-in only works for private-league owners). MFL's drops "— no extra account needed" (some MFL paths go to Apple). Removing a false claim needs no marketing pass.
- **No dead tiles:** a platform that isn't live has no tile, never a disabled or "coming soon" one (design-lead's recommendation). With only Sleeper live, the row is hidden and the landing is the plain username form, as today.

**Launch gating (platforms-eng's sizing, 11-01; head-eng's hard rule):** the ESPN and MFL tiles must sit on #430's verified `acct_*` claim, never on today's mint of unverified `entry:*` sessions (M11).
- The lever is `landing.platform_options`, OFF in prod (operator ask 12) until #430 (+ #477, #478, #518) is deployed and the purge (ask 17) has run.
- Then ask 16 turns it ON, with `espn.signin` only if the operator's R1 check (ask 15) is PAIR_BOUND.
- The MFL tile also needs #421 (MFL entry sign-in, client half) in the 11-06 binary; without it, MFL sign-in is dead.
- This build adds no flag.

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `signin_attempted` / `signin_succeeded` / `signin_failed` with `method` = `sleeper` / `espn` / `mfl` already fire around each door's sign-in (`api/auth.ts`, `api/platformEntry.ts`). They answer which door was used and whether it worked. Selecting a chip was never tracked, and a tile changes nothing there.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: none. The tiles read the chips' existing flags: `landing.platform_options`, `espn.link`, `espn.signin`, `mfl.link`.
- New env vars / `model_config` keys: none. Rollback lever: `landing.platform_options` OFF hides every tile with no deploy (the landing falls back to the username form).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-signin-tiles.js` (`npm run test:signin-tiles`), AST pins:
  1. one radiogroup row, under `platformPickerShown`, whose only child is `platformChips.map(...)` (no hard-coded or dead tile);
  2. each tile is a radio with `tile.a11y`, `{ selected: on }`, testID `signin.platform-${p}`, disabled while `busy || demoBusy || appleBusy`, and `onPress` exactly `() => selectEntryPlatform(p)`;
  3. `PLATFORM_TILE` has exactly sleeper / espn / mfl, word for word as marketing's addendum 16, with no "soon" / "coming" / "unavailable";
  4. the tile styles match the spec, and ice appears only on the selected border and the tick;
  5. the tick renders only on the selected tile;
  6. the ESPN/MFL door mints only through `platformEntry.ts`, whose every route is `POST /api/entry/platform`. SignInScreen calls no `/api/entry` route itself;
  7. the ESPN and MFL explainers are exactly the trimmed strings, and no string on the screen says "no extra account";
  8. the session-expired notice's `marginBottom` is `space.md - 5`.

  Sabotage 26/26 red (15 on the structure, 5 on the words, 6 on the two fixes). The guards already on this screen stay green: `check-landing-platform-options` (the row's gates and per-platform flags), `check-espn-signin-flag`, `check-signin-apple-parity` (9), `check-guide-script` and `check-signin-identity-labels`. #421's `platformEntry.ts` keeps every route on `/api/entry/platform`, so pin 6 holds after it merges.
- [x] **Unit tests:** none. No backend change.
- [x] **Code-walk proof** (no tile reaches any mint but `/api/entry/platform`, and none renders when its flag is off):
  1. The tiles are `platformChips.map` (`SignInScreen.tsx:673`) inside the radiogroup row (`:672`), rendered only under `platformPickerShown` (`:670`).
  2. `platformChips` (`:142-146`) holds Sleeper, plus ESPN only on `espnLinkOn && espnSignInOn` and MFL only on `mflLinkOn`. `platformPickerShown` (`:148-149`) needs `landingOn && platformOptionsFlag` and at least 2 tiles. So with `landing.platform_options` OFF (ask 12) no tile renders.
  3. A tile's only action is `selectEntryPlatform(p)` (`:683` → `:196`). That sets `entryPlatform`, so `nonSleeperEntry` (`:150`) swaps the username form for the platform panel (`signin.platform-panel`, `:724`).
  4. The panel's button (`signin.platform-link-btn`, `:736`) opens the platform's sheet in entry mode: `EspnLinkSheet entry` (`:938`) or `PlatformLinkSheet entry platform="mfl"` (`:946`).
  5. The sheets mint only through `entryPlatformMint` (`EspnLinkSheet.tsx:365`, `PlatformLinkSheet.tsx:255`, `:370`) → `POST /api/entry/platform` (`platformEntry.ts:155`). Every other call in that file goes to the same route (`:42`, `:57`, `:81`, `:105`).
  6. On the server that route is 404 while `landing.platform_options` or the platform's link flag is off (`server.py` `entry_platform`, the `is_enabled("landing.platform_options")` check). #430 makes it prove ownership and mint a verified `acct_*` account (its `check-landing-platform-options` V2.6 pins "the mint never creates an `entry:*` id").
  7. The tiles change none of steps 2 to 6: the diff touches only the row's markup and styles, and `PLATFORM_TILE`.
- [x] **Manual TestFlight checklist** (8 steps; operator, on an iPhone SE, on the binary carrying this, in a test window with `landing.platform_options` on; `espn.signin` on for steps 2 and 4):
  1. Fresh install. Expect three equal tiles, Sleeper, ESPN and MFL, each with its name and a dim line. Sleeper is selected (ice border and a short ice tick at the top right), and the username form is below.
  2. Tap ESPN. Expect the ice border and tick to move to ESPN, the username form to be replaced by the ESPN explainer and "Link your ESPN league →", and "or" plus Continue with Apple to still be below.
  3. Tap MFL. Expect the same, with the MFL panel. Tap Sleeper. Expect the username form back.
  4. VoiceOver on. Swipe across the tiles. Expect each to read as a radio button with its label ("Sleeper, sign in with your username, no password needed"; "ESPN, sign in with your ESPN account or a league ID"; "MyFantasyLeague, sign in with your account or a league ID"), with the selected one announced as selected and the others not.
  5. With `espn.signin` off (or not sent). Expect two equal tiles, Sleeper and MFL, and no ESPN tile at all (not greyed out).
  6. With `landing.platform_options` off. Expect no tiles: the plain username form, as on main before this.
  7. Sign out with an expired session (the returning-user notice showing). Expect the whole landing, down to "By signing in you agree to the Terms…", on one SE screen without scrolling.
  8. Select ESPN, then MFL. Expect "ESPN dynasty leagues are supported. Sign in to ESPN, or enter a league ID." and an MFL line ending "…or enter a league ID.", with no "no extra account needed" in either.
- testIDs added/renamed: none (`signin.platform-sleeper|espn|mfl` kept). `testid-lint` OK.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added or changed |
| `living-memory/LLD.md` | n/a | no schema, route or invariant convention shifted |
| `docs/architecture.md` | n/a | no module wiring or data flow change |
| `living-memory/HLD.md` | n/a | no new module, client or flow; the entry flow is unchanged |
| `docs/cross-client-invariants.md` | n/a | mobile-only styling; no shared constant, enum or colour |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` entry | n/a | the design call is design-lead's spec (this file), on the operator's ask; no architectural choice |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (runs the `check-*.js` suites) + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-11-01 entry.
- **TestFlight verification:** the operator runs §3's checklist on the 11-06 binary in the 11-07 TF window, before ask 16; the outcome is logged in TEST_LEDGER.
- Express lane declared by the operator? No.
