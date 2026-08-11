# P0-3 — The invite loop is broken at both ends

> Build plan for audit finding P0-3 (`docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md` §P0-3).
> Branch `p0-remediation-2026-08-10`, worktree `ftf-p0-remediation` @ `ab9368f`.
> **Full feature gates apply** — this adds a deep-link route (route surface) plus a
> server route and an API route. Operator confirmed full gates for this build.

## Table of contents

- [Verified current state](#verified-current-state)
- [Design](#design)
- [Exact change list](#exact-change-list)
- [Surface changes](#surface-changes)
- [Maestro delta](#maestro-delta)
- [Docs impact table](#docs-impact-table)
- [Test plan](#test-plan)
- [Risks and open questions](#risks-and-open-questions)

---

## Verified current state

Every line below was re-read in this worktree on 2026-08-10. Where the audit's
citation has drifted, the drift is noted.

### The emitter

| Fact | Evidence |
|---|---|
| `buildInviteUrl` emits `<base>/?league=<id>&ref=<user>` — query only, no path | `mobile/src/components/InviteLeaguematesBanner.tsx:27-31` |
| `ref` is omitted when the username is unknown, so `league` can travel alone | same, `:29` |
| Call site 1 — the cold-start banner on Trades | `mobile/src/components/InviteLeaguematesBanner.tsx:40` |
| Call site 2 — the League tab's "Invite leaguemates" module | `mobile/src/screens/LeagueScreen.tsx:373` (import at `:65`) |
| Both share the same message body: `Join me on Dynasty Trade Finder to find trades in <league> → <url>` | `InviteLeaguematesBanner.tsx:44`, `LeagueScreen.tsx:376-378` |
| The banner's own comment asserts the URL "already IS the landing page … no URL change needed", "verified against utils/deepLinks + web captureReferralFromUrl" | `InviteLeaguematesBanner.tsx:34-37` — **half true**: verified for web, false for mobile. See [Contradictions](#contradictions-found-against-audit-and-code-comments). |
| `growth.share_landing` (ON in `config/features.json` and in `backend/tests/fixtures/flags/release.json`) gates **only** the `invite_shared` track call, not the URL | `InviteLeaguematesBanner.tsx:38, 46-48` |

### The receiver (mobile)

| Fact | Evidence |
|---|---|
| `?ref=` is captured in both router modes and stashed via `setInvitedBy` | `mobile/src/utils/deepLinks.ts:344-348` |
| **`?league=` has no reader anywhere in `mobile/src`** | `grep -rn "queryParams" mobile/src` → only `deepLinks.ts`; no `league` read |
| The bare-path short-circuit the audit cited is still there, at **`deepLinks.ts:352-354`** (audit said `:301-302` — the file grew; the code is unchanged) | `if (!path) return;` under comment *"Bare open / referral-only URL (no path) — nothing to route, no toast."* |
| `V2_SCREENS` route table — no join/invite entry | `deepLinks.ts:95-178` |
| Universal-link path aliases (`/s/trade/*`, `/s/p/*`) are rewritten outside the table | `deepLinks.ts:193-202` (`rewriteUniversalPath`) |
| Both cold-start (`getInitialURL`) and warm (`url` event) funnel through `handleDeepLink` | `mobile/App.tsx:161-173` |
| Cold-start links ALSO resolve through react-navigation's `linking` config | `RootNav.tsx:313` → `getLinkingV2()` (`deepLinks.ts:205-212`) |
| `ux.deeplink_router_v2` is **ON** in defaults and in the release fixture, so the v2 branch is the live path | `config/features.json`, `backend/tests/fixtures/flags/release.json` |

### State flow through auth

| Fact | Evidence |
|---|---|
| `invitedBy` is **in-memory only**, explicitly documented as such | `mobile/src/state/useSession.ts:108-110`, setter `:366-370`, `consumeInvitedBy` `:369-373` |
| It is consumed on the two session-init paths and forwarded as `invited_by` | `mobile/src/api/auth.ts:389-392, 406` and `:473-476, 490` |
| Backend records `invited_by` on INSERT only, so re-sends are harmless | `mobile/src/api/auth.ts:386-388` (comment), matches web's note at `web/js/app.js:936-938` |
| There is **no** league counterpart to `invitedBy` in the store | `useSession.ts` — `invitedLeagueId` does not exist |

### Routing table (RootNav)

| Fact | Evidence |
|---|---|
| Initial route: no user → `SignIn`; user without league/token → `LeaguePicker`; else `Main` | `RootNav.tsx:294-301` |
| All root screens are registered unconditionally; `initialRouteName` picks the entry | `RootNav.tsx:397-421` |
| `onSignedIn` → `replace('LeaguePicker')` | `RootNav.tsx:404` |
| `onAccountSignedIn` → `replace('Main')` — **the line P0-5 changes** | `RootNav.tsx:410` |
| `LeaguePicker` → `onLeaguePicked` → `replace('Main')` | `RootNav.tsx:417` |
| `pickLeague(lg, { auto: true })` already exists as a proven programmatic pin (used by `onboarding.league_autoskip`) | `LeaguePickerScreen.tsx:227` (signature), `:120-129` (auto-skip precedent) |
| The league list effect re-runs on `user.user_id`; `cached` comes from `useSession.leagues` | `LeaguePickerScreen.tsx:133-141`, `:53` |

### Universal-link configuration

| Fact | Evidence |
|---|---|
| Entitlement present (audit said `app.json:52`; it is now **`mobile/app.json:21`**) | `"associatedDomains": ["applinks:fantasy-trade-finder.onrender.com"]` |
| AASA route lives at **`backend/server.py:8076-8109`** (audit said `~8075-8108` — same block) | claims `components` `/u/*`, `/s/*`, `/` + `?ref`, `/` + `?league`; legacy `paths` `/u/*`, `/s/*` |
| **AASA does not claim any `/app/*` path** — a new path is invisible to iOS until AASA ships and Apple's CDN refreshes | `server.py:8100-8107`; documented in `docs/api-reference.md:587` |
| AASA is CDN-cached, up to ~24h, and must be deployed **before** the build that depends on it is installed | `docs/runbook.md:410-412` |
| Flask serves `web/` as static root; `/` returns `index.html`; **nothing serves `/app/...`** (a 404 today) | `backend/server.py:2003`, `:8053-8055` |

### The web answer (the audit's open question) — **web already completes the journey**

This is the finding that changes the shape of the fix.

| Fact | Evidence |
|---|---|
| `captureReferralFromUrl()` parses **both** `ref` and `league` | `web/js/app.js:5835-5848` |
| Stored as `ftf_invited_by` / `ftf_invited_league` in `localStorage`, then the params are stripped from the URL bar | `web/js/app.js:5832-5833, 5839-5843` |
| An "Invited by @&lt;ref&gt;" banner is appended to the auth card | `web/js/app.js:5853-5867` (`showInvitedBanner`) |
| Called unconditionally at boot | `web/js/app.js:6168` |
| **The league is auto-selected** once the user's Sleeper league list loads — findIndex on `ftf_invited_league`, `selectLeague(idx)`, and the intent is consumed | `web/js/app.js:589-601` |
| `invited_by` is forwarded on `/api/session/init` | `web/js/app.js:940` |
| Smart-start ("paste a league URL") reuses the same key to auto-select afterwards | `web/js/app.js:1271` |

**Consequence.** The invite URL is a *working* web landing page and a *dead* mobile
deep link. So this is not "give the invite a path" — it is "give the invite a path
**without breaking the one half that works**". Any URL change must keep `/?league=&ref=`
parsed forever (links already shared in Sleeper chats), and must land somewhere sensible
in `web/` for recipients who don't have the app (universal links fall through to Safari).

### Analytics reality check

`invite_shared` (`InviteLeaguematesBanner.tsx:47`) is **not** in
`ALLOWED_CLIENT_EVENTS` (`backend/analytics_taxonomy.py:34-99`). The ingest path is
default-deny (`backend/analytics_ingest.py:376`), so **the only invite event in the
product is being dropped on the floor today**. Any measurement of this fix starts by
registering names server-side first.

### Test-harness reality check

| Fact | Evidence |
|---|---|
| Deep links are unusable in Maestro — `openLink` raises an undismissable SpringBoard confirm on iOS 18 | `mobile/.maestro/README.md:140-146` (law 17), `mobile/src/utils/testRouteEntry.ts:14-18` |
| The supported substitute is launch-argument entry: `launchApp: arguments: { FTFTestRoute: <Route>, FTFTestRouteParams: 'k=v&k=v' }` (query string, never JSON) | `README.md:141-146`, `testRouteEntry.ts:104-128` |
| Root-stack route names pass through verbatim — no allowlist edit needed for a new root screen | `testRouteEntry.ts:60-62` |
| **But** the entry is only applied when the boot landed authed | `RootNav.tsx:341` — `if (initialRoute === 'Main') applyTestRouteEntry(navigationRef)` |
| The gate is a build-time constant (`FTF_ENV=test`), inert in every TestFlight/App Store bundle | `testRouteEntry.ts:33-56` |
| No jest in `mobile/` — mobile verification is `tsc --noEmit` + Maestro + manual | `mobile/package.json` has no test script |

---

## Design

### 1. URL scheme

Emit, per the handoff:

```
https://fantasy-trade-finder.onrender.com/app/league/join/<leagueId>?ref=<username>
```

`ref` stays optional (unknown username ⇒ omitted), exactly as today.

Three properties this must preserve, all of which drive the rest of the design:

1. **Legacy links keep working, on both clients, forever.** `/?league=&ref=` is already
   in people's Sleeper chats and iMessage threads. Both the mobile parser and web keep
   handling it. The new path is additive.
2. **A recipient without the app must land somewhere real.** The server 302s
   `/app/league/join/<id>?ref=x` → `/?league=<id>&ref=x`, i.e. straight into the web
   journey that already works (banner + auto-select). No new web page, no new web JS,
   no risk to a funnel that currently converts.
3. **iOS must know the path exists.** AASA gains `/app/league/join/*`.

Flagged rollout: the *emitter* is gated on a new default-OFF flag
`growth.invite_join_link`. Flag OFF ⇒ byte-identical legacy URL. The *parsers* (mobile
route entry, legacy `?league=` reader, server redirect, AASA claim) ship unflagged
because they are strictly additive and must be live **before** any new-format link
exists in the wild — including the AASA entry, which needs its ~24h CDN lead
(`docs/runbook.md:410-412`).

> **Note.** Reading `?league=` on the legacy bare-path URL is, on its own, a complete
> fix for the reported bug and works on every link ever shared. The path exists to give
> the invite a real destination screen (and thus a place to name the inviter and the
> league) — not because it is required to route.

### 2. Routing entry

`V2_SCREENS` (`deepLinks.ts:95-178`) gains one line:

```ts
LeagueJoin: 'app/league/join/:leagueId',
```

registered as a **root-stack** screen in `RootNav` alongside `Profile` / `Settings` /
`LeagueSummary`. Root-stack matters: the invitee is usually signed out, and a route that
resolved inside `Main` would drop a session-less user into the tabs (the same class of
failure P0-5 is fixing). `LeagueJoinScreen` is an interstitial that renders in any auth
state and decides where to go.

Legacy `?league=` handling goes in `handleDeepLink` **above** the bare-path
short-circuit at `deepLinks.ts:352-354`, next to the existing `?ref=` capture, so it is
captured in both router modes.

### 3. State flow through auth

New store slice in `useSession`, mirroring `invitedBy`:

```ts
invitedLeagueId: string | null;
setInvitedLeague(id: string): void;
consumeInvitedLeague(): string | null;
```

**Persistence change (deliberate, differs from `invitedBy` today).** Both values persist
to `AsyncStorage` under one key `ftf_invite_intent` = `{ leagueId, invitedBy, ts }` with
a **14-day TTL**, hydrated in `bootstrap()`, cleared on consume and on `signOut`. Reasons:

- Web already persists (`localStorage`, `web/js/app.js:5839-5840`) — parity.
- The invitee's path is often *tap link → app opens → they close it → come back later*,
  and today that loses the whole intent.
- The account-only branch (P0-5) can leave a user league-less for several launches; the
  intent has to outlive them.

TTL and consume-on-pin bound the staleness risk. `invited_by` is INSERT-only server-side
(`api/auth.ts:386-388`), so a late attribution cannot overwrite an existing one.

Flow:

```
tap link
  └─ handleDeepLink / linking config
       ├─ setInvitedBy(ref)            (existing)
       └─ setInvitedLeague(leagueId)   (new; from path or from legacy ?league=)
  └─ LeagueJoinScreen (only for the /app/league/join path)
       ├─ no user                → replace('SignIn')      → invite banner renders
       ├─ user, league in list   → pickLeague(auto:true)  → replace('Main')
       ├─ user, league NOT in list → replace('LeaguePicker') with notice
       └─ user, already active   → replace('Main') + toast "You're already in <League>"
  └─ SignIn → (Sleeper) LeaguePicker → auto-pin effect fires → Main
           └─ (Apple account-only, post-P0-5) LeaguePicker companion state → link a
              platform → league list populates → auto-pin effect fires → Main
```

The auto-pin effect in `LeaguePickerScreen` is the workhorse and mirrors web
`app.js:589-601` one-for-one: when `invitedLeagueId` is set and appears in `cached`,
call the existing `pickLeague(lg, { auto: true })` and consume the intent. It keys on
`cached`, so it re-fires whenever the list changes — which is exactly what makes the
account-only path (P0-5) work without either fix knowing about the other.

### 4. Sign-in personalization (the additive half)

`SignInScreen` renders an `InvitedByBanner` above the form (next to the existing
`reauthNotice`, `SignInScreen.tsx:376-380`) whenever `invitedBy || invitedLeagueId`:

> **@matt invited you to Lakeview Dynasty**
> Sign in and we'll take you straight there.

It must render in **both** SignIn variants (`landingOn` on/off — `SignInScreen.tsx:79,
381`), because the onboarding-v2 landing hides the Apple block.

League-name resolution: new public `GET /api/league/invite-meta?league_id=<id>` returning
`{ league_id, league_name, platform }`. Implementation reuses `_fetch_sleeper_league_meta`
(`backend/server.py:673`, already used by the unauthenticated `POST /api/league/parse-url`
at `:17388`). **Sleeper ids only** — resolved from Sleeper's public API, never from our
`leagues` table, so linked ESPN/MFL league names are not enumerable by id. Anything else
returns `{ league_name: null }` and the banner degrades to "**@matt** invited you to their
league" — the acceptance criterion ("with the inviter named") is met without the endpoint
at all; the endpoint only upgrades "their league" to the real name.

### 5. Web fallback for recipients without the app

`GET /app/league/join/<league_id>` → `302` to `/?league=<id>&ref=<ref>` (query preserved).

Chosen over the alternative (serve `index.html` at the deep path and teach `web/js/app.js`
to read the league id out of `location.pathname`) because:

- zero change to a web funnel that demonstrably works today;
- no risk around asset resolution (assets are absolute — `web/index.html:10, 1065-1066` —
  so the alternative would work, but it buys nothing);
- iOS resolves universal links against AASA **before** any HTTP request, so the redirect
  cannot interfere with app-open behaviour on installed devices.

**Not solved, and honestly out of reach:** a recipient with no app who installs from the
App Store loses the intent entirely — iOS has no deferred deep linking without a
third-party attribution SDK. The 302 covers "taps the link in Safari and signs in on the
web", which is the case web already converts.

---

## Exact change list

### Mobile

| # | File | Change |
|---|---|---|
| M1 | `mobile/src/components/InviteLeaguematesBanner.tsx:27-31` | `buildInviteUrl` takes a flag-resolved format; ON ⇒ `/app/league/join/<id>?ref=<u>`, OFF ⇒ today's string. Update the stale comment at `:9-18, 34-37`. |
| M2 | `mobile/src/components/InviteLeaguematesBanner.tsx:38, 46-48` | Read the new flag `growth.invite_join_link` alongside `growth.share_landing`; keep the `invite_shared` call (now that the name is registered, B4). |
| M3 | `mobile/src/screens/LeagueScreen.tsx:373` | Same call site update — it must not keep emitting the legacy format while the banner emits the new one. |
| M4 | `mobile/src/utils/deepLinks.ts:95-178` | Add `LeagueJoin: 'app/league/join/:leagueId'` to `V2_SCREENS`, with a comment explaining root-stack placement (signed-out invitees). |
| M5 | `mobile/src/utils/deepLinks.ts:344-354` | Capture `?league=` next to `?ref=`, **before** the bare-path return, in both router modes. This is the legacy-link fix. |
| M6 | `mobile/src/state/useSession.ts:108-110, 193, 366-373, 482` + `bootstrap()` `:199-225` + `signOut` | Add `invitedLeagueId`, `setInvitedLeague`, `consumeInvitedLeague`; persist `{leagueId, invitedBy, ts}` to `AsyncStorage` under `ftf_invite_intent` with a 14-day TTL; hydrate in `bootstrap`; clear on consume/sign-out. `setInvitedBy` also writes the blob. |
| M7 | `mobile/src/screens/LeagueJoinScreen.tsx` (**new**) | Interstitial per §3. Renders a Chalkline "Joining <League>…" card with a spinner and an honest error state; never a dead end. `testID`s: `leaguejoin.root`, `leaguejoin.title`, `leaguejoin.not-member`, `leaguejoin.cta`. |
| M8 | `mobile/src/navigation/RootNav.tsx:397-421` | Register `<Stack.Screen name="LeagueJoin">`; add `LeagueJoin: { leagueId: string; ref?: string }` to the `AuthStack` param list (`:53` neighbourhood). **Coordinate with P0-5 — same file.** |
| M9 | `mobile/src/screens/LeaguePickerScreen.tsx` (after the auto-skip effect, `:120-129`) | Auto-pin effect: `invitedLeagueId` present && found in `cached` ⇒ `pickLeague(lg, { auto: true })` + consume; not found && list non-empty ⇒ set a notice row. Keys on `cached` so it re-fires after a platform link. **Coordinate with P0-5 — same file.** |
| M10 | `mobile/src/screens/SignInScreen.tsx:376-380` | `InvitedByBanner` in both `landingOn` variants; `testID="signin.invited-banner"`. Fetches `/api/league/invite-meta` once, tolerates failure silently. |
| M11 | `mobile/src/api/leagues.ts` (or the nearest existing client module) | Thin `fetchInviteMeta(leagueId)` — unauthenticated GET, short timeout, never throws. |
| M12 | `mobile/src/utils/testRouteEntry.ts` + `RootNav.tsx:341` | **Harness only, operator-visible:** allow the launch-arg entry to apply when `initialRoute === 'SignIn'` for the single route `LeagueJoin`, so Maestro can exercise the signed-out invite landing. Still inside `IS_TEST_BUILD`. See [Maestro delta](#maestro-delta) for the alternative if the operator declines. |

### Backend

| # | File | Change |
|---|---|---|
| B1 | `backend/server.py:8094-8108` | AASA: add `{"/": "/app/league/join/*"}` to `components` and `"/app/league/join/*"` to legacy `paths`. Nothing else changes; do not broaden to `/app/*`. |
| B2 | `backend/server.py` (near `:8053-8067`, the other static page routes) | `GET /app/league/join/<league_id>` → `302` `/?league=<id>&ref=<ref>` preserving `ref` when present. Unflagged. |
| B3 | `backend/server.py` (near `:17353` `parse-url`) | `GET /api/league/invite-meta?league_id=<id>` → `{league_id, league_name, platform}`; Sleeper public meta only; `league_name: null` for non-Sleeper ids; no session required; no DB read. |
| B4 | `backend/analytics_taxonomy.py:34-99` | Register `invite_shared` (already fired and currently dropped), plus `invite_link_opened`, `invite_league_pinned`, `invite_pin_failed`. Props per the scope block. |
| B5 | `backend/feature_flags.py` `FLAG_KEYS` (`:47`+, growth block near `:230, 272`) | Add `growth.invite_join_link`. |
| B6 | `config/features.json` + `backend/tests/fixtures/flags/release.json` | `growth.invite_join_link: false` (default OFF) with a `_comment_` explaining the graduation criterion. |
| B7 | `backend/tests/test_invite_links.py` (**new**) | See [Test plan](#test-plan). |

### Web

No change. The 302 hands off to the existing, working path
(`web/js/app.js:5835-5848, 589-601`). Recorded as a deliberate decision, not an oversight.

---

## Surface changes

### Route surface: **YES** — enumerated

| Surface | Entry | Kind |
|---|---|---|
| Deep-link route (mobile) | `app/league/join/:leagueId` → `LeagueJoin` screen | **New**, in `V2_SCREENS` and the react-navigation `linking` config (both flow from the same table) |
| Navigation route (mobile) | Root-stack `LeagueJoin` screen | **New** |
| Universal-link claim (iOS) | AASA `components` + `paths` gain `/app/league/join/*` | **New**, unflagged, must deploy ≥24h before the build |
| Web/server route | `GET /app/league/join/<league_id>` → 302 | **New**, unflagged |
| API route | `GET /api/league/invite-meta` | **New**, public, read-only |
| Query-param contract | `?league=` now *read* on mobile (already emitted, already read on web) | **Behaviour change**, no contract change |
| Analytics names | `invite_shared` (fixing a silent drop) + 3 new | **New taxonomy entries** — register before the client fires them |
| Feature flag | `growth.invite_join_link`, default OFF | **New flag surface** |

### `docs/api-reference.md` impact

- New row for `GET /api/league/invite-meta` in the league section.
- New row for `GET /app/league/join/<league_id>` in the static/share-page section
  (alongside `/s/trade/<match_id>` at `:545`).
- **Edit the AASA row at `:587`** — the claimed-path list is enumerated there and would
  otherwise become wrong the moment B1 lands.

### Server changes

B1–B4 above. No schema change, no migration, no write path — B2 and B3 are read-only,
`invite-meta` performs one cached Sleeper meta lookup.

---

## Maestro delta

Constraint first: **`openLink` cannot be used** (README law 17, `mobile/.maestro/README.md:140-146`).
Deep-link entry in this harness is launch arguments only, and the existing gate applies
launch-arg routing only on an authed boot (`RootNav.tsx:341`).

**New flow — `mobile/.maestro/flows/league/invite-join.yaml`** (`# flags: release`), three
blocks:

1. **Authed pin, member of the league.** Normal sign-in launch, then relaunch with
   `clearState: false, stopApp: true, arguments: { FTFTestRoute: LeagueJoin, FTFTestRouteParams: 'leagueId=<seeded-league>&ref=qa_inviter' }`.
   Assert `leaguejoin.root`, then landing in the tabs with the seeded league active
   (assert the league name in the top bar / League tab).
2. **Authed, not a member.** Same entry with a league id absent from the seeded list.
   Assert `leagues.row.*` list visible plus `leaguepicker.invite-notice` — the honest
   "you're not in that league yet" state, never a spinner that never ends.
3. **Signed-out landing (needs M12).** Fresh state, launch with the same arguments.
   Assert `signin.invited-banner` contains the inviter handle.

Block 3 depends on the harness change M12. **If the operator declines M12**, block 3 is
waived in the scope block and the signed-out banner is verified by (a) a screen-library
capture of `SignIn` under a seeded invite intent and (b) manual TestFlight QA — recorded
as a test-coverage gap, not silently dropped.

`testID`s added (must pass `mobile/scripts/testid-lint.sh`): `leaguejoin.root`,
`leaguejoin.title`, `leaguejoin.not-member`, `leaguejoin.cta`, `signin.invited-banner`,
`leaguepicker.invite-notice`.

Smoke impact: `flows/smoke/01..11` cross `SignIn` and `LeaguePicker`. The new banner and
notice render only when an invite intent exists, which no smoke flow creates, so all 11
should be unaffected — asserted, not assumed, by running the full suite (tier 1).

---

## Docs impact table

| Doc | Update |
|---|---|
| `docs/api-reference.md` | **Required.** New rows for `/api/league/invite-meta` and `/app/league/join/<id>`; **amend the AASA row at `:587`** with the new claimed path. |
| `docs/config-reference.md` | New flag `growth.invite_join_link` — default, what it gates, graduation criterion. |
| `docs/cross-client-invariants.md` | The invite-URL format is now a two-client contract (mobile emits, web + mobile parse) — record both accepted formats and the rule that the legacy format is parsed forever. |
| `docs/runbook.md` | Extend the AASA section (`:410-412`) with the operational ordering: deploy AASA → wait for CDN → then ship the build → only then flip `growth.invite_join_link`. |
| `living-memory/LLD.md` | Convention shift: deep-link destinations that a signed-out user can reach belong on the **root** stack, not inside `Main`. |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a — no module wiring change. |
| `docs/data-dictionary.md` | n/a — no schema change (`ftf_invite_intent` is client-side AsyncStorage). |
| `docs/glossary.md` | Add "invite intent" if the term lands in code as designed. |
| `DECISIONS.md` | New entry: why the legacy `/?league=` format stays parsed forever, and why web gets a 302 rather than a new landing page. |
| Analytics tracking plan (`docs/business/analytics/`) | Addendum for the four invite events, including the note that `invite_shared` was firing into a default-deny wall since it shipped. |

---

## Test plan

**Backend (`backend/tests/test_invite_links.py`)**

1. AASA payload contains `/app/league/join/*` in both `components` and `paths`, still
   claims the four existing patterns, and still never claims `/` unqualified.
2. `GET /app/league/join/123?ref=matt` → 302, `Location == /?league=123&ref=matt`.
3. `GET /app/league/join/123` (no ref) → 302 → `/?league=123`.
4. Path traversal / junk league ids are URL-encoded into the redirect, not reflected raw.
5. `invite-meta` with a Sleeper id (mocked meta) returns the name; with a non-numeric or
   linked-platform id returns `league_name: null`; never touches the `leagues` table;
   requires no session.
6. Taxonomy: the four invite event names are in `ALLOWED_CLIENT_EVENTS` and accepted by
   `POST /api/events` (this is the regression guard for the silent-drop class of bug).
7. Flag `growth.invite_join_link` is present in `FLAG_KEYS` and defaults false
   (the existing features-json-keys-known guard covers the config side).

**Mobile (`npx tsc --noEmit` + Maestro)**

8. Typecheck clean.
9. Maestro `flows/league/invite-join.yaml` blocks 1–3 (3 conditional on M12).
10. Full smoke suite (11 flows) — tier 1 change class.

**Manual / simulator, both URL formats**

11. Legacy `/?league=<id>&ref=<u>`: cold start and warm — league pinned, inviter named.
    *(This is the one that proves every already-shared link is fixed.)*
12. New `/app/league/join/<id>?ref=<u>`: cold start and warm, signed out and signed in.
13. Non-member league id → LeaguePicker with the notice; then join the league on Sleeper
    and relaunch within the TTL → auto-pin fires.
14. Web fallback: open the new URL in Safari on a device **without** the app → 302 →
    "Invited by @x" banner → sign in → league auto-selected (`web/js/app.js:589-601`).
15. Demo session active → invite intent ignored, no pin, no crash.
16. Post-P0-5 account-only: Apple sign-in → LeaguePicker companion state → link Sleeper →
    invited league auto-pins.

**Ship gate:** tier 1 (navigation + screen change) — full smoke + the new flow + capture
refresh for `SignIn` and `LeaguePicker`; log in `TEST_LEDGER.md`; write
`qa/sim-runs/last-sim-run.json`.

---

## Risks and open questions

### Interaction with P0-5 (flag explicitly for HLD reconciliation)

**Both fixes edit the same two files.**

- `RootNav.tsx` — P0-5 rewrites `onAccountSignedIn` at `:410` (`Main` → `LeaguePicker`);
  P0-3 registers `LeagueJoin` in the same `Stack.Navigator` block at `:397-421` and (M12)
  touches the launch-arg gate at `:341`.
- `LeaguePickerScreen.tsx` — P0-5 adds the companion/empty state for league-less accounts;
  P0-3 adds the auto-pin effect after `:129` and an invite notice row.

**Recommended sequencing: P0-5 first, P0-3 rebases onto it.** P0-5's change is smaller and
its routing decision is a precondition for P0-3's account-only path being reachable at all.
Alternative: one agent owns both files for the wave.

**Semantic interaction, and why it resolves cleanly.** An invited user who signs in with
Apple and has no Sleeper identity currently lands in the tabs (P0-5's bug) and can never
pin the invited league. After P0-5 they land on `LeaguePicker` with zero leagues. P0-3's
auto-pin effect keys on `cached`, so the moment a platform link populates the list, the pin
fires. Neither fix needs to know about the other — **provided** P0-5 does not short-circuit
`LeaguePicker` for account-only sessions with a bespoke screen that skips the list, and
**provided** the invite intent is persisted (M6). Both conditions belong in the HLD.

Open conflict for the HLD to settle: should `LeagueJoin` on an account-only session route
to P0-5's new companion state directly with invite context ("**@matt** invited you to
Lakeview Dynasty — connect Sleeper to join"), instead of the generic picker? That is a
better experience and a tighter coupling. Recommended, but it is a joint decision.

### Other risks

| Risk | Mitigation |
|---|---|
| **AASA CDN lag (up to 24h).** Ship the new URL before AASA propagates and every invite opens Safari instead of the app — a *worse* loop than today. | Deploy B1 first, verify with an AASA validator, wait, ship the build, and only then flip `growth.invite_join_link`. Encoded in the runbook update and the flag's graduation criterion. |
| **Invite intent staleness.** Persisting the intent means a user could be pinned into a league they were invited to two weeks ago. | 14-day TTL, consumed on first successful pin, cleared on sign-out. `invited_by` is INSERT-only server-side, so attribution cannot be overwritten. |
| **Analytics silently dropped** (the trap the handoff names, and already live for `invite_shared`). | B4 lands and deploys **before** any client `track()` call ships. Test 6 is the regression guard. |
| **Two emitters drift** — `LeagueScreen.tsx:373` and the banner. | Single flag read inside `buildInviteUrl`; both call sites stay one-liners. Add a comment naming both. |
| **Signed-out cold-start routing.** A future route registered inside `Main` would drop a session-less user into empty tabs. | `LeagueJoin` is root-stack; recorded as an LLD convention. |
| **Non-Sleeper invites.** An ESPN/MFL league's invitee gets `league_name: null` and, if their Sleeper list doesn't contain the id, the not-member notice. | Honest copy, no dead end. Cross-platform invites are out of scope for P0-3 — flagged, not solved. |
| **Redirect loop / open-redirect.** | The redirect target is constructed server-side from a path segment; no user-supplied absolute URL is ever reflected. Test 4. |

### Open questions for the operator

1. **M12 (harness change).** Extend the test-route entry to a signed-out boot for
   `LeagueJoin` only, so Maestro can cover the invite landing? Still test-build-gated.
   Declining means block 3 is a manual-QA-only path.
2. **Persisting the invite intent** changes `invitedBy` from in-memory to 14-day
   persistent. Accept the attribution-staleness trade for parity with web?
3. **`growth.referral` is OFF** (`backend/feature_flags.py:230`) — the give-get referral
   program. Nothing in this plan reads it, but if invites are meant to graduate into that
   program, the event names should be chosen with it in mind.
4. **Flag or no flag?** The emitter flag adds a moving part to a fix whose whole point is
   that the loop converts zero today. Shipping the new URL unflagged (after AASA lands) is
   defensible. Recommendation: keep the flag for the AASA-ordering safety it buys, and
   graduate it in the same session once verified on device.

### Contradictions found against audit and code comments

1. **The audit's open question is now answered, and the answer inverts part of the
   framing.** `web/` *does* parse `?league=` and *does* complete the journey
   (`web/js/app.js:5835-5848`, `:589-601`). The loop is broken on mobile only — "broken at
   both ends" is true of the *mobile* ends (emit and receive), not of the product. The
   practical consequence is that the URL change is the risky half of this fix, and the
   valuable half (`?league=` reading, `deepLinks.ts:352`) needs no URL change at all.
2. **`InviteLeaguematesBanner.tsx:34-37` asserts the opposite of the truth**: "verified
   against utils/deepLinks + web captureReferralFromUrl — no URL change needed". Verified
   for web; false for `utils/deepLinks`, which has no `?league=` reader. Same
   comment-over-code failure class as the withdrawn P0-4 / finding A-33.
3. **`invite_shared` has been firing into a default-deny wall** since it shipped
   (`InviteLeaguematesBanner.tsx:47` vs `analytics_taxonomy.py:34-99`). Not in the audit;
   it means there is no telemetry whatsoever on the invite loop, including for the
   "converts zero" claim.
4. **Line drift (harmless, but the plan uses the current numbers):**
   `deepLinks.ts:301-302` → `:352-354`; `app.json:52` → `mobile/app.json:21`.
