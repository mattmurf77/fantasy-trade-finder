# Feature Scope — Landing platform options (Sleeper · ESPN · MFL at entry)

**Date:** 2026-08-26 (v2 same day — see §V2 at the bottom)
**Entry point:** direct ask — "update the app entry page for new users to offer ESPN and MFL alongside Sleeper as the platforms we offer support for"; v2 follow-up ask — "decouple the Apple account dependency from ESPN and MFL"
**Builder:** Claude session (worktree `app-entry-platform-options-3e16ac`)
**Operator sign-off on waivers:** pending — one waiver (§1c) surfaced in the session summary

---

## What ships

The mobile entry page (`SignInScreen`, `onboarding.landing` layout) gains a
three-chip platform row — **Sleeper · ESPN · MFL** — above the sign-in form.

- **Sleeper selected (default):** today's layout, unchanged to the pixel.
- **ESPN or MFL selected:** the Sleeper username form is replaced by a short
  explainer + the official **Sign in with Apple** button. Apple sign-in is the
  only session mint that doesn't need a Sleeper username (`POST /api/espn/link`
  and `/api/mfl/link` both `_require_session` — verified at
  `backend/server.py:23359` / `:25955`), so the platform choice rides the
  Apple flow as an **intent** and lands on `LeaguePicker` with the matching
  link sheet auto-opened (the existing `espnLink: true` #130 machinery; a new
  symmetric `mflLink: true`).

No backend route changes. No schema changes. Reuses: account-first Apple
sign-in (`auth.accounts`, live), LeaguePicker companion state (P0-5), the
ESPN/MFL link sheets, and the #266 transition-settled sheet auto-open.

Out of scope: Fleaflicker (flag dark), the web landing page, the flags-off
(P2.6 Apple-first) layout — reverting `onboarding.landing` also withdraws the
chip row, which is acceptable because that layout's primary portal is already
Apple and platform-agnostic.

## 1. Analytics scope

- [x] **(b) Existing events cover it** — the pre-auth funnel is unchanged:
  `signin_attempted` / `signin_succeeded` / `signin_failed {method: 'apple'}`
  fire on the Apple flow exactly as today, and `league_selected {platform}`
  already distinguishes the platform on the far side. What they answer: how
  many entries route through Apple and which platform the session lands on.
- [x] **(c) partial WAIVER — no chip-selection event.** A per-chip
  `landing_platform_selected` event would need a new taxonomy entry, and
  `backend/analytics_taxonomy.py` marks new client events/props default-deny
  pending a tracking-plan addendum. Rather than widen the taxonomy inside an
  entry-page change (the NULL-`platform` incident lesson), selection-level
  analytics is deferred; if the operator wants it, it's a one-event follow-up
  with its own tracking-plan row. **Surfaced to operator in the ship summary.**

## 2. Schema & flag scope

- Tables/columns: **none**
- Feature flags: **`landing.platform_options`** (new, client-only gate — no
  backend route reads it) → added to `config/features.json` (with comment) and
  `backend/feature_flags.py` `FLAG_KEYS`; documented in
  `docs/config-reference.md`. **Ships TRUE** — the operator asked for the
  surface directly; the flag is the deploy-free revert lever. Effective only
  while `onboarding.landing` is on. Graduation: delete the flag once the
  chip row survives a TestFlight cycle without complaint.
- Env vars / `model_config`: **none**

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-landing-platform-options.js`
      (+ `npm run test:landing-platform-options`) — pins:
      1. chip row gated on `onboarding.landing` AND `landing.platform_options`;
      2. ESPN/MFL chips individually gated on `espn.link` / `mfl.link`, with a
         fallback that resets a de-flagged selection to Sleeper;
      3. Apple success branches forward the platform intent to BOTH
         `onSignedIn` and `onAccountSignedIn`;
      4. selecting a non-Sleeper chip advances guide step `s0.2` (the Analyst
         spotlight targets the username field the chip hides);
      5. RootNav maps intent → `{espnLink}` / `{mflLink}` params for both
         callbacks;
      6. LeaguePicker's MFL auto-open mirrors the #266 transition-settled
         deferral and the league-autoskip guard blocks on `autoOpenMflLink`.
- [x] **Unit tests:** none added — no backend behavior changed (flag-registry
      addition only; existing `backend/tests` cover flag loading generically).
- [x] **Code-walk proof:** in this doc's companion `code-walk.md` (written at
      build end, file:line-cited).
- [x] **Manual TestFlight checklist** (runtime proof matters — sheet
      presentation over a fresh navigation stack is exactly the #266 class):
      1. Fresh install (or sign out) → entry page shows **Sleeper · ESPN · MFL**
         chips above the username field; Sleeper selected; form identical to
         current build.
      2. Tap **ESPN** → username field/hint/button replaced by explainer +
         Sign in with Apple; no Analyst spotlight left floating.
      3. Complete Apple sign-in → lands on the league list with the **ESPN
         link sheet already open** (not wedged, not absent — #266 regression
         check). Cancel the sheet → normal picker/companion state beneath.
      4. Back on entry (sign out), tap **MFL** → same flow, **MFL sheet** opens.
      5. Tap **Sleeper**, type a valid username → sign-in works exactly as
         the current build (no chip interference).
      6. With one Sleeper league on the account, run step 4 again → the MFL
         sheet must open **instead of** the single-league auto-skip.
- `testID`s added: `signin.platform-sleeper|espn|mfl` (template
  `signin.platform-${p}`), `signin.platform-panel`, `signin.platform-apple-btn`,
  `signin.platform-unavailable`. None referenced by retained flows → no
  allowlist entries needed; `testid-lint.sh` run before ship.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/changed |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifted — new nav param follows the existing #130 `espnLink` convention |
| `docs/architecture.md` | n/a | no module wiring change; SignIn → LeaguePicker edge already exists |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constants/enums/colors added; chip labels reuse existing platform names |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` | updated | new D-entry: platform choice at entry rides Apple sign-in as an intent param (not a platform-native auth at entry) |
| `docs/config-reference.md` | updated | `landing.platform_options` flag row |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` + `npx tsc --noEmit` + `testid-lint.sh`
  run locally before push; CI on the PR sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry at ship.
- **TestFlight verification:** checklist in §3 — operator runs it on the next
  build that carries this change; outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **No** — full gates.

---

# V2 — Decouple Apple: sessionless platform entry (2026-08-26, D-164)

**Operator ask:** "Can't we decouple the Apple account dependency from ESPN and
MFL? If so, let's do that now."

## What changes

The v1 ESPN/MFL panels replaced the form with *Sign in with Apple* because the
link routes `_require_session`. V2 removes that dependency: the panels open the
**existing link sheets** directly on the entry page, and the session is minted
**at the team-claim step** — the same trust model as Sleeper entry (claim your
username, no password): claim your team, no account.

- **New route `POST /api/entry/platform`** (sessionless; gated on
  `landing.platform_options` + the platform's own `espn.link`/`mfl.link`):
  - *Preview* (no `team_id`): same fetch/crosswalk internals and the exact
    same `choose_team` wire shapes as `/api/espn/link` / `/api/mfl/link`, so
    the sheets parse it unchanged. ESPN cookies come from the body only (no
    stored-credential fallback — there is no user yet); a private league
    without cookies gets the same 403 `espn_auth_required` the sheet already
    self-serves via the ESPN WebView sign-in (which runs fully signed-out).
  - *Mint* (`team_id` present): validates the team, runs the #321
    wrong-account SWID assertion when cookies are in hand, derives a
    **deterministic user id** — `entry:espn:<canonical SWID>` (else
    `entry:espn:<league>.t<team>`) / `entry:mfl:<league>.f<franchise>` — and
    mints the session via the existing `_extension_build_session` (which also
    creates the users row). Returns an `extension_auth`-shaped payload.
    The `entry:` namespace is deliberately distinct from the `espn:`/`mfl:`
    placeholder member ids, which are documented as never-routable.
- **The canonical import stays canonical:** after the mint the sheet calls the
  normal `/api/espn/link` / `/api/mfl/link` import with the fresh token (the
  unverified-write grace path admits it), binding the claimed team to the
  entry user and persisting league/members/credentials exactly as today. No
  import logic is duplicated server-side.
- **Sheets get an `entry` mode** (prop, default off — linked-flow byte-identical):
  preview goes to the entry route; `pickTeam` mints first, hands the user to
  the host via `onEntrySession`, then runs the existing import; the
  session-requiring nice-to-haves are suppressed (`espn.league_picker`
  my-leagues list, `mfl.auth_link` username/password path).
- **SignInScreen panels v2:** primary button opens the sheet ("Link your ESPN
  league →" / MFL); Apple leaves the panel entirely. The quiet
  "Already have an account? Sign in with Apple" re-entry link is restored in
  all chip states (it still carries the v1 `platformIntent`). After
  `onEntrySession` the host `setUser({...account_only: true})` and on
  `onLinked` routes to LeaguePicker, where the shipped platform-league merge +
  single-league auto-skip carries the user into Main — no new activation code.
- **Deterministic identity = durable identity:** re-claiming the same team
  re-mints the same user id, recovering the same boards — exactly what a
  Sleeper username re-claim does.

## Analytics (v2)

`signin_attempted` / `signin_succeeded` / `signin_failed` gain the **method
values** `espn` and `mfl`, fired from the entry mint call (attempt = the user
claimed a team). Value-only addition on an already-whitelisted prop — no new
event, no new prop, no registry change; the tracking plan's value list gets a
dated addendum line. The §1c waiver (no chip-selection event) stands.

## Schema & flag scope (v2 delta)

- Tables/columns: **none** (the `entry:` ids ride the existing `users` PK
  keyspace; no uniqueness hazard — PK only).
- `landing.platform_options` is **no longer client-only**: the entry route
  reads it server-side. `docs/config-reference.md` row updated.
- New route → `docs/api-reference.md` updated.

## Evidence scope (v2 delta)

- **Backend pytest:** `backend/tests/test_entry_platform_route.py` — flag
  gating (feature + per-platform), bad platform, MFL preview persists nothing
  and mints nothing, MFL mint returns a registered token + deterministic
  `entry:mfl:` id + users row (idempotent re-claim → same id, fresh token),
  bad team 400, ESPN mint id forms (SWID and ownerless), #321 wrong-account
  403, and the integration proof: the minted token drives the real
  `/api/mfl/link` import, binding the claimed franchise to the entry user in
  `league_members`.
- **Structural guard:** `check-landing-platform-options.js` extended — panel
  opens the sheets (no Apple in the panel), sheets' entry mode mints before
  import and suppresses the session-dependent paths, host sets an
  `account_only` entry user, backend route exists with both flag gates.
- **Code-walk:** `code-walk.md` §V2.
- **Manual TestFlight checklist (v2, replaces v1 §3 steps 2–4):**
  1. Fresh install → ESPN chip → "Link your ESPN league" → enter a **public**
     ESPN league id → team list appears → tap your team → import summary →
     Open league → you land in the app on that league. No Apple prompt at any
     point.
  2. Same with a **private** ESPN league: entering the id shows the private
     copy → Sign in to ESPN (WebView) → back in the sheet, preview loads →
     claim team → in. Apple never appears.
  3. MFL chip → league id + year → franchise list → claim → in.
  4. Kill the app, relaunch: still signed in on the claimed league.
  5. Sleeper chip flow unchanged; "Already have an account? Sign in with
     Apple" link present under every chip.
  6. Settings → sign out → redo step 1 with the same team: your board from
     step 1 is back (deterministic identity).

## Consequences / accepted limits (v2)

- Entry sessions are **unverified** → not server-persisted; recovery is the
  client Keychain token, then re-claim (cheap, deterministic). If
  `auth.enforce_verified_writes` is ever turned on, entry users lose the
  write-grace path — flagged as a consequence in D-164.
- Two humans claiming the same team share an identity — identical to two
  humans claiming the same Sleeper username. Accepted trust model.
- The `espn.league_picker` my-leagues list doesn't render in entry mode
  (it reads *stored* credentials); manual league id + WebView sign-in covers
  entry. Possible later polish, not in scope.

---

# V2.1 — "Log in" as a first-class entry option (2026-08-26, same day)

**Operator ask:** the live entry flow leads with league IDs; users should have
the **option to log in** to ESPN/MFL instead. Implemented by an Opus subagent,
reviewed line-by-line and shipped by the lead session.

- **Route:** `POST /api/entry/platform` gains two sessionless account-discovery
  actions, mutually exclusive with the mint: ESPN `my_leagues` (fan-profile
  list for the supplied cookie pair; byte-identical shape to
  `GET /api/espn/my-leagues`; gated `espn.league_picker`) and MFL
  `auth_leagues` (the same login+myleagues pair `/api/mfl/auth-link` uses;
  gated `mfl.auth_link`). **Both store nothing** — no credential row, no
  user, no session; the MFL password is transient and never logged.
- **ESPN entry UX:** "Sign in to ESPN" is a first-class button on the input
  step (same `espn.webview_capture` WebView, which runs signed-out); a capture
  with no league id typed feeds the sessionless my-leagues action and the
  existing picker list renders — the user never needs a league id. Failures
  are soft: the league-id field stays usable.
- **MFL entry UX:** "Sign in with MFL" appears above the league-id field;
  login lists the account's leagues **with the user's own franchise_id**, so
  a single tap mints directly (no team-claim step) → canonical import → a
  best-effort credential re-store under the fresh session (so Send-in-MFL
  works later; password held in a ref, dropped before that one call, cleared
  on every exit path).
- **Evidence:** `test_entry_platform_route.py` 13→23 (incl. a
  stored-nothing assertion helper on users/credentials/leagues/sessions);
  structural guard 36→61 assertions (one V2 claim — "entry suppresses the MFL
  password path" — deliberately superseded); tsc, testid-lint, full suite
  green. Sabotage-proven both ways by the subagent (flag-gate drop and
  `!entry` restore each turned exactly the expected tests red).
- **TestFlight checklist (v2.1, additive to V2's):**
  1. ESPN chip → "Sign in to ESPN" (no league id typed) → ESPN login → back
     in the sheet, **your leagues are listed** → tap one → team list → claim
     → in. No league id ever typed, no Apple prompt.
  2. MFL chip → "Sign in with MFL" → username/password → league list shows
     your franchise per league → tap one → **straight to the import summary**
     (no team-claim step) → in. Then Trades → a send-in-MFL surface should
     find the credential already stored.
  3. Both league-ID paths from the V2 checklist still work unchanged.

---

# V3 — Web landing mirror: Sleeper · ESPN · MFL on `web/index.html` (2026-09-03)

**Date:** 2026-09-03
**Entry point:** direct ask — "update the landing page on web to mimic the mobile app with ESPN and MFL options"
**Builder:** Claude session (worktree `compassionate-jones-ea8a0e`, branch `claude/landing-page-espn-mfl-a5a85a`)
**Operator sign-off on waivers:** not needed — no waivers

## What changes

The web landing (`web/index.html` hero) gains the same three-chip platform
row — **Sleeper · ESPN · MFL** — above the sign-in form, driven by the same
flags and the same backend route as mobile (D-164):

- **Sleeper (default):** today's username door, untouched. The smart-start
  CTA + username row now sit inside a `#entry-sleeper` wrapper solely so
  the panel swap can hide them.
- **ESPN:** explainer + league ID / URL field → `POST /api/entry/platform`
  preview → team list → claim (mint) → canonical `POST /api/espn/link`
  import. The web has no WebView, so private leagues use the **cookie
  paste** (`espn_s2` + `SWID`) that is mobile's fallback; a 403
  `espn_auth_required` auto-opens that section (mobile's self-serve
  pattern). With a pasted pair, "Find my leagues" runs the v2.1 sessionless
  `my_leagues` action (gated `espn.league_picker`) and lists the account's
  leagues.
- **MFL:** "Sign in & find my leagues" (v2.1 sessionless `auth_leagues`,
  gated `mfl.auth_link`) lists the account's leagues with the user's own
  franchise → one click mints + imports, then a best-effort
  `POST /api/mfl/auth-link` re-store so Send-in-MFL works later (the
  password leaves the field the moment the lookup returns and is held in a
  module variable only until that one call, cleared on every exit). Or
  league ID / URL + season year → preview → franchise claim.
- **After the claim** the ordinary web league flow takes over with ONE new
  routing rule: a saved user whose id starts with `entry:` reads leagues
  and rosters from `GET /api/{espn,mfl}/leagues` (the imported snapshot)
  instead of Sleeper's roster proxies — in `showLeagueScreen` (with
  mobile's single-league auto-skip), `selectLeague`, `initSession` (page
  reload), `switchToLeague`, the boot-time switcher fill and the FB-47
  leaguemate pool. The session body comes from `buildPlatformRosterData`,
  the snapshot twin of `buildRosterData` (same output shape).
- **Copy:** `<meta description>` / `og:description` now read "Works with
  Sleeper, ESPN, and MyFantasyLeague." ("How it works" step 1 already did).
- **Drive-by fix inside the restructured function:** `selectLeague`'s
  "Roster loaded" toast referenced an undefined `userPlayerIds` — a
  `ReferenceError` thrown after every league pick since the first commit
  (the league was saved, so a reload recovered, but the method screen /
  main app never mounted in that pass). It reads `rosterData.userPlayerIds`
  now.

No backend route changes. No schema changes. No new flags — the web reads
the existing `landing.platform_options`, `espn.link`, `mfl.link`,
`mfl.auth_link`, `espn.league_picker` from `/api/feature-flags`, so the one
revert lever stays the one revert lever (flag off ⇒ the row never renders
and the landing is today's Sleeper page).

Out of scope: the in-app "Connect another league" modal (its ESPN/MFL paste
still says "on the roadmap" — a NEXT follow-up now that the link routes are
reachable from web), Fleaflicker (dark), the Sleeper smart-start / demo
affordances (unchanged).

## Analytics (v3)

- [x] **(b) Existing events cover it.** The web now emits the pre-auth
  funnel mobile already emits: `signin_attempted` / `signin_succeeded` /
  `signin_failed {method, error_code}` with `method ∈ {sleeper, espn, mfl}`
  (`screen: 'SignIn'`). The Sleeper door gains them too (it emitted nothing
  before), so the web funnel is symmetric across platforms. All three events
  and props are registered in `backend/analytics_taxonomy.py`; `espn`/`mfl`
  are the documented value-only additions (addendum
  `docs/business/analytics/2026-08-26-entry-method-values.md`, web rows
  added). `league_selected` is not emitted by web today and stays that way.

## Schema & flag scope (v3 delta)

- Tables/columns: **none**
- Flags: **none new**; the `docs/config-reference.md` row for
  `landing.platform_options` now names the web surface too.
- Env vars / `model_config`: **none**

## Evidence scope (v3)

- [x] **Structural guard:** `qa/web/check_web_structure.py` — **175/175**
  (tokens, no emoji, radius ≤ 8px, fonts, SEO meta, a11y landmarks/h1,
  hygiene). Web has no `check-*.js`; this script is its CI gate.
- [x] **Unit tests:** `backend/tests/test_entry_platform_route.py` +2
  (23 → 25): `test_mfl_entry_leagues_snapshot_carries_the_claimed_franchise`,
  `test_espn_entry_leagues_snapshot_carries_the_claimed_team` — pin the
  contract the web's `buildPlatformRosterData` relies on (the snapshot lists
  the claimed league under the entry token; the claimed team's member row
  carries the ENTRY user id with a non-empty roster; every other member is a
  synthetic `espn:`/`mfl:` id).
- [x] **Browser E2E (runtime — the web's equivalent of the TestFlight
  checklist):** see [`code-walk.md` §V3](code-walk.md). Run against the
  real Flask app with only the ESPN/MFL fetchers patched to the fixture
  leagues (the same seams the route tests patch) on a scratch SQLite DB.
  Both platforms: chip → preview → claim → mint → import → league
  auto-select → `/api/session/init` → ranking-method screen → main app with
  the claimed 8-player roster and the franchise name in the account chip;
  page reload restores the entry session through `boot()`; the leaguemate
  pool populates from the snapshot (16 players, 2 owners); live-API error
  paths (unknown MFL id, private ESPN league) render the right copy and
  auto-open the cookie section. Console clean throughout.
- [x] **Code-walk proof:** [`code-walk.md` §V3](code-walk.md).
- `testID`s: n/a (web).

## Docs scope (v3)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added, renamed or contract-changed — the web calls existing routes with their documented bodies |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifted; the `entry:` routing rule lives here + in the code comments |
| `docs/architecture.md` | n/a | no module wiring change — web stays vanilla JS over existing routes |
| `living-memory/HLD.md` | n/a | no new module, client or major flow — web reuses the D-164 flow |
| `docs/cross-client-invariants.md` | n/a | nothing shared added; chips use existing tokens |
| `docs/glossary.md` | n/a | no new term |
| `DECISIONS.md` | updated | D-177 |
| `docs/config-reference.md` | updated | `landing.platform_options` row names the web chip row |
| `docs/design/components.md` | updated | PlatformChips row (mobile + web construction) |
| `docs/business/analytics/2026-08-26-entry-method-values.md` | updated | web emitter rows |
| `web/CLAUDE.md` | updated | `index.html` row mentions the platform entry |

## Manual check for the operator (prod, after deploy)

1. Load `/` signed out → the chip row shows **Sleeper · ESPN · MFL**; Sleeper
   is selected and the username door is unchanged.
2. **MFL** chip → a real league ID + year → Continue → your franchises list →
   pick yours → the ranking-method screen with your roster; the account chip
   shows your franchise name. Reload → straight back into the app.
3. **ESPN** chip → a public league ID → Continue → teams → pick yours → same
   landing. A private league ID → the cookie section opens with the "This
   league is private" line; paste `espn_s2` / `SWID` → Continue → teams.
4. Flip `landing.platform_options` off (+ `POST /api/feature-flags/reload`)
   → the row is gone and the landing is today's Sleeper page.

---

# V3.1 — ESPN entry leads with sign-in, not the league ID (2026-09-03)

**Date:** 2026-09-03
**Entry point:** operator, on the shipped V3 landing — "ESPN option is missing the log in prompt as primary"
**Builder:** Claude session (worktree `compassionate-jones-ea8a0e`, branch `claude/espn-signin-primary`)
**Operator sign-off on waivers:** not needed — no waivers

## What changes

V3 shipped the ESPN panel league-ID-first, with the credential path demoted to
a "Private league? Paste your ESPN cookies" link. That inverted mobile, where
`EspnLinkSheet` in entry mode makes signing in **first-class** and the league
ID the other path (`mobile/src/components/EspnLinkSheet.tsx:459-476`: the
sign-in button, then "We'll find your leagues — no league ID needed", then
"or enter a league ID"). MFL already matched; only ESPN was inverted.

The web ESPN panel is now, in order: read-only explainer → **primary "Sign in
to ESPN" button** → "We'll find your leagues — no league ID needed. We never
see your password." → the cookie block it expands (with a "Find my leagues"
primary running the v2.1 `my_leagues` action) → **"or enter a league ID"**
divider → the league-ID row.

**Why the web's "sign in" is a cookie paste.** Mobile's primary is one button
because its WebView captures `espn_s2`/`SWID` from the native cookie store. A
browser cannot read espn.com's cookies cross-origin, and ESPN publishes no
OAuth, so the honest web equivalent is the paste that is *already* mobile's
own fallback. The expanded block says so plainly and links to espn.com. No
ESPN password is ever requested — the app has no ESPN password path.

**Flag-driven layout.** The primary block's whole promise ("we'll find your
leagues") is the `my_leagues` action, which 404s without `espn.league_picker`.
That flag therefore chooses the layout, mirroring how mobile gates its entry
sign-in on `espn.webview_capture`:

| `espn.league_picker` | Layout |
|---|---|
| **on** (ships true) | sign-in primary + hint + "or enter a league ID" divider; the cookie block carries "Find my leagues" |
| **off** | no promise we can keep — league ID is primary and the cookie fields sit behind the secondary "Private league?" link, exactly where V3 had them |

One set of cookie inputs serves both layouts; only the controls around them
move, so there is no duplicate-id hazard.

**Copy fix found by testing.** Both `#espn-error` and `#mfl-error` render
*after* the cookie block **and** after the league-ID row, so every
directional word in four error strings pointed the wrong way. "paste your
espn_s2 and SWID cookies **below**" was wrong even in V3 — it came from
mobile, whose sheet genuinely does put that section under the error. All four
are now direction-free ("Paste your espn_s2 and SWID cookies to continue.",
"Try a league ID instead."), which cannot rot when the layout moves again.

## Analytics (v3.1)

- [x] **(b) Existing events cover it.** No new events. `signin_*` still fires
  once per claim with `method: 'espn'`; expanding the sign-in block is not a
  claim and deliberately emits nothing, matching mobile's rule that opening
  the sheet or previewing a league is not an attempt.

## Schema & flag scope (v3.1 delta)

- Tables/columns: **none**. New flags: **none** — `espn.league_picker` is
  existing and now additionally selects the web ESPN layout (documented in
  `docs/config-reference.md`).

## Evidence scope (v3.1)

- [x] **Structural guard:** `qa/web/check_web_structure.py` — **175/175**.
- [x] **Unit tests:** none added; the change is client-side only and
  `backend/tests/test_entry_platform_route.py` still passes **25/25**
  (the route contract is unchanged).
- [x] **Browser E2E** (fixture-stubbed app, ESPN fan-profile lookup stubbed
  too so the `my_leagues` path is exercised end to end) — table in
  [`code-walk.md` §V3.1](code-walk.md).
- [x] **Code-walk proof:** [`code-walk.md` §V3.1](code-walk.md).

## Docs scope (v3.1)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route touched |
| `living-memory/LLD.md` / `docs/architecture.md` / `living-memory/HLD.md` | n/a | presentation-order change inside one existing panel |
| `docs/design/components.md` | updated | PlatformChips row notes the ESPN sign-in-primary hierarchy + its flag |
| `docs/config-reference.md` | updated | `espn.league_picker` row notes it selects the web ESPN layout |
| `DECISIONS.md` | updated | D-179 |
