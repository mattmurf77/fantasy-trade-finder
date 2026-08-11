# P0-5 — Apple account-only sign-in strands users with no league

> Plan for the mobile-UX-audit P0-5 remediation. Source: `docs/business/product/2026-08-09-mobile-ux-audit/`
> (`04-priority-backlog.md` §P0-5, `06-resolutions.md` §P0-5, `07-build-handoff-prompt.md` §P0-5).
> Worktree: `ftf-p0-remediation`, branch `p0-remediation-2026-08-10`, base `origin/main @ ab9368f`.
> **Acceptance:** a brand-new Apple sign-in reaches a platform/league choice without visiting Settings.

## Contents

- [1. Verified current state](#1-verified-current-state)
- [2. Design](#2-design)
- [3. Exact change list](#3-exact-change-list)
- [4. Surface changes](#4-surface-changes)
- [5. Maestro delta](#5-maestro-delta)
- [6. Docs impact](#6-docs-impact)
- [7. Test plan](#7-test-plan)
- [8. Risks and open questions](#8-risks-and-open-questions)

---

## 1. Verified current state

Every line number below was re-read in **this worktree** on 2026-08-10. The audit's numbers have
drifted (the audit cited `server.py:17913`, `RootNav.tsx:398`, `/api/espn/link` at `:18493`,
`/api/mfl/link` at `:20119`); the drift is naming only — the behaviour is unchanged.

### The stranding path

| Step | File:line (this worktree) | Behaviour |
|---|---|---|
| Server mints the branch | `backend/server.py:18039-18075` `_mint_account_only_session()` | Brand-new provider identity, no session, no bound Sleeper id → mints a **real session token** under the synthetic key `acct_<account_id>`, sets `verified=True`, `verified_via="apple"`, calls `mark_user_verified`, persists the session, and returns `account_only: true` plus `league_id=ACCOUNT_NO_LEAGUE_ID`, `league_name=ACCOUNT_NO_LEAGUE_NAME`. |
| Sentinel constants | `backend/server.py:17956-17957` | `ACCOUNT_NO_LEAGUE_ID = "no_league"`, `ACCOUNT_NO_LEAGUE_NAME = "No league linked"`. |
| Entry to that branch | `backend/server.py:18153-18155` | The `else` arm of `_provider_auth_response` — "brand-new identity, no session, no bound Sleeper source". |
| Client consumes it | `mobile/src/screens/SignInScreen.tsx:167-185` | `setUser({… account_only: true})`, `setLeague({league_id: res.league_id \|\| NO_LEAGUE_ID, …})`, `track('signin_succeeded', {method:'apple'})`, then `(onAccountSignedIn ?? onSignedIn)()`. |
| Routing | `mobile/src/navigation/RootNav.tsx:410` | `onAccountSignedIn={() => navigation.replace('Main')}` — **the bug**. Compare `:404` (`onSignedIn` → `LeaguePicker`) and `:407` (demo → `Main`, correct, the demo league is real). |
| Relaunch routing | `mobile/src/navigation/RootNav.tsx:297-301` | `!user ? 'SignIn' : !league \|\| !hasToken ? 'LeaguePicker' : 'Main'`. The sentinel league **is** a league and `hasToken` is true, so a cold start after the bad first run also lands on `Main`. **The audit did not note this; the routing fix alone does not cover relaunch.** |
| Sentinel client constant | `mobile/src/state/useSession.ts:56` | `export const NO_LEAGUE_ID = 'no_league'`. |

### How the `no_league` sentinel is read today

It is read in exactly three places, and **only** to suppress Sleeper-side work — no league-scoped
screen keys off it, which is why every league surface silently renders empty rather than explaining
itself:

- `useSession.ts:246` — `revalidateSession()` early-returns for `account_only` or sentinel league.
- `useSession.ts:408` — `connectLeague()` refuses for `account_only` users.
- `useSession.ts:553` — the 401 Apple-reauth hook only arms for `account_only` sessions.
- `SettingsScreen.tsx:659-666, 1071, 1198, 1210, 1258` — Settings' account-only affordances.
- Backend: `server.py:18070, 18094` (emit), `backend/tests/test_account_first.py:216, 490` (assert).

### The only escape hatch today (Settings)

- `SettingsScreen.tsx:785-790` — "Link an ESPN league" row → `navigateFromSettings('LeaguePicker', { espnLink: true })`.
- `SettingsScreen.tsx:802-808` — MFL/Fleaflicker chooser row → `navigateFromSettings('LeaguePicker')`.
- `SettingsScreen.tsx:1210-1236` — the account-only "Link your Sleeper username" card
  (`testID="settings.link-sleeper-input"`), handler `handleLinkSleeper` at `:423-472`, which calls
  `linkSleeperUsername()` (`mobile/src/api/auth.ts:132-144` → `POST /api/account/link-sleeper`),
  handles the 409 `merge_choice_required` two-boards Alert and the `sleeper_already_claimed` case,
  then `setUser(...)`, `setLeague(null)`, `navigation.replace('LeaguePicker')`.

**Consequence worth stating plainly:** Settings' three escape hatches all end at `LeaguePicker` —
so the picker is *already* the designated destination for this user. It just doesn't know how to
receive them.

### LeaguePicker's current states

`mobile/src/screens/LeaguePickerScreen.tsx` (492 lines):

- `refresh()` `:152-203` — **unconditionally** calls `getLeagues(user.user_id)`
  (`mobile/src/api/sleeper.ts:10-28` → `GET /api/sleeper/leagues/<user_id>`), then merges ESPN
  (`getEspnLeagues()`, flag `espn.link`) and MFL/Fleaflicker (`getPlatformLeagues`) results.
- States rendered `:299-381`: **loading** (`:299`, with a 4s "waking up" escalation),
  **error** (`:308`, red text + "Try again"), **empty** (`:313-318`, the bare sentence
  *"No 2026 NFL leagues found for this account."* — no testID, no action), **list** (`:320`).
- Footer `:386-421` — flag-gated link buttons, rendered in **every non-loading state**:
  `leagues.link-espn` (`espn.link`, ON in release), `leagues.link-mfl` (`mfl.link`, ON in release),
  `leagues.link-fleaflicker` (`fleaflicker.link`, **OFF** in release). Sheets: `EspnLinkSheet`
  `:423-427`, `PlatformLinkSheet` `:428-435`.
- Post-link `onLeagueLinked` `:208-225` → merges the row into `leagues` → `pickLeague(summary)`.
- `pickLeague` `:227-287` → `track('league_selected', …)` → `buildSessionInitBody` →
  `setLeague({league_id, league_name})` → `onLeaguePicked()` → background `submitSessionInit`.

**Newly found defect (not in the audit): sending an account-only user to today's picker produces a
false error, not an empty state.** `refresh()` calls `GET /api/sleeper/leagues/acct_<id>`, which
proxies `https://api.sleeper.app/v1/user/acct_<id>/leagues/nfl/2026` (`server.py:13960-13991`).
Under the Maestro/VCR harness a fixture miss raises `HTTPError 599` (`server.py:533-536`), so
`sleeper_failed=True` with no local leagues → **503 `sleeper_unavailable`** → the picker paints
*"Couldn't reach Sleeper — try again shortly."* Live, Sleeper returns `null` for an unknown user,
which lands on the empty-state sentence instead. Either way the screen blames Sleeper or the user
for a situation that is neither. **The account-only branch must not call Sleeper at all.**

### Link flows to reuse, not rebuild (audit grades A−/B+)

- **ESPN:** `EspnLinkSheet` (opened from the picker footer, or auto-opened via the `espnLink: true`
  param, `:87-107`, transition-settled per #266). WebView cookie capture is `EspnConnectScreen`
  behind `espn.webview_capture`; league-list selection behind `espn.league_picker`. Both ON.
- **MFL / Fleaflicker:** `PlatformLinkSheet` with `platform` prop — zero-auth, league-id entry.
- **Sleeper (verification, *not* linking):** `SleeperConnectScreen`, reached from
  `VerifyAccountBanner` (`RootNav.tsx:437`) and Settings `:1258-1272`. **Explicitly hidden for
  account-only users** — their Apple sign-in *is* the verification. It is not the thing to reuse
  here; the Sleeper *identity link* is `POST /api/account/link-sleeper`.

### Backend confirmations (the operator's answered question, re-verified)

- `POST /api/espn/link` — `server.py:18619-18641`. Gate order: `is_enabled("espn.link")` → 404 dark;
  `@_gate_unverified_write` (`:2392-2409`, passes because account-only sessions carry
  `verified=True`); `_require_session()` at `:18640`; `user_id = sess["user_id"]`. On import
  (`:18728-18733`) the chosen team's member row is written with `user_id = <session user>` — i.e.
  the acct_ key. **No Sleeper identity required.**
- `POST /api/mfl/link` — `server.py:20270-20281`, identical shape (`_require_session()` at `:20279`).
- Therefore: **a post-Apple platform selector needs zero backend work**, and **landing-page
  selection before any account is impossible as built** — both routes 401 without a session.
  Confirmed as the audit stated.
- **Post-link session continuity holds.** `pickLeague` → `submitSessionInit` →
  `/api/session/init` (`server.py:14270`). Because the client sends the existing
  `X-Session-Token`, `existing_sess` is found and the **same token is reused**
  (`:14626-14638`); `user_changed` is false (same acct_ key), so `verified`/`verified_via`
  survive. Without that, the P2.5 read gate would 403 the user out of their own board the moment
  they linked a league (`users.verified_via='apple'` is already set). Verified, not assumed.
- `buildEspnSessionInitBody` (`mobile/src/api/espn.ts:169-197`) finds "my" roster by
  `m.user_id === user.user_id` — the acct_ key the import wrote. Works unchanged.

### Flag states in `release` (`backend/tests/fixtures/flags/release.json`, mirrors `config/features.json`)

`auth.accounts: true` · `espn.link: true` · `mfl.link: true` · `fleaflicker.link: false` ·
`auth.persistent_sessions: true` · `onboarding.v2: true` but `onboarding.landing: false`.

`onboarding.landing: false` matters: with it off, `SignInScreen.tsx:381-399` renders the **official
Apple button as the primary control**, which is what makes this branch high-traffic and validates
the audit's load-bearing assumption. With `onboarding.landing` ON (P0-9 territory) the Apple entry
degrades to a text link at `:515-540` framed *"Already have an account?"* — see §8.

---

## 2. Design

### 2.1 Chosen approach: routing fix + picker companion state

The resolutions doc offers two options. Committing to the **routing fix**, per its own preference:

| | Routing fix (chosen) | Non-dismissible sheet over `Main` |
|---|---|---|
| Where the choice lives | `LeaguePicker`, which already owns league selection, already hosts both link sheets, and is already where all three Settings escape hatches land | A new modal component with its own presentation lifecycle |
| New surface area | One prop change + one branch inside an existing screen | A new always-mounted component in the `Main` subtree, plus a "can't dismiss" rule to enforce and unwind later |
| Interaction with tabs | None — the user never reaches empty tabs | Mounts *over* five empty tabs; every tab's empty state is still wrong underneath, and iOS RN modal stacking is a known hazard in this codebase (`LeaguePickerScreen.tsx:73-86` documents a wedge caused by exactly this) |
| Reversibility | Two lines revert it | A component to delete |
| Cost of being wrong | User sees a picker one screen early | User sees a modal they cannot escape — the worst possible failure mode for a first run |

**Decision: routing fix.** The sheet-over-`Main` alternative is rejected: it puts a non-dismissible
modal in front of a first-time user, over a tab bar whose emptiness it does not fix, using the
exact RN modal-stacking mechanism that has already wedged this screen once.

### 2.2 The four moving parts

**(a) Route account-only sign-ins to the picker.**
`RootNav.tsx:410` — `onAccountSignedIn={() => navigation.replace('LeaguePicker')}`. `replace`, not
`navigate`: there must be no back edge to a `SignIn` screen whose session is already spent.

**(b) Make the relaunch predicate sentinel-aware.**
`RootNav.tsx:297-301` — treat the sentinel as "no league":

```
const hasRealLeague = !!league && league.league_id !== NO_LEAGUE_ID;
const initialRoute = !user ? 'SignIn' : (!hasRealLeague || !hasToken) ? 'LeaguePicker' : 'Main';
```

Key off **`league.league_id === NO_LEAGUE_ID`, never `user.account_only`.** `account_only` stays
true for an Apple user who links an ESPN league (it is cleared only by linking a *Sleeper username*,
`SettingsScreen.tsx:432-437`), so an `account_only` predicate would trap a perfectly well-provisioned
user in the picker forever. The sentinel is the honest signal, and `setLeague` overwrites it the
moment a real league is picked.

Without (b), the fix covers first sign-in only: kill and relaunch, and the user is stranded again
(and every existing account-only user on TestFlight stays stranded). (b) is what makes the fix
retroactive.

**(c) Picker companion state — platform-first, for session-holders with zero leagues.**

Two changes inside `LeaguePickerScreen`:

1. **Do not ask Sleeper about a synthetic id.** In `refresh()`, skip the `getLeagues()` call when
   `user.account_only` is true; start from `[]` and merge only the platform lists. This removes the
   false 503/"no leagues found for this account" and one pointless round-trip. (The ESPN/MFL/Flea
   fetches are session-scoped and correct for these users — they must still run, because an
   account-only user who already linked an ESPN league from Settings has leagues to list.)
2. **A dedicated zero-league state that leads with the choice.** Replace the bare
   `cached.length === 0` sentence when `user.account_only` with:

   - Header (existing header component, copy swapped): **"Connect your league"**, sub-line
     *"Leagues for <display_name>"* stays.
   - Body: **"Connect Sleeper, ESPN or MFL to see your leagues."** — the handoff's copy verbatim.
   - Three primary actions, in that order, each with a testID:
     `leagues.empty.link-sleeper` · `leagues.empty.link-espn` · `leagues.empty.link-mfl`
     (+ `leagues.empty.link-fleaflicker` when its flag is on).
   - The ESPN / MFL / Fleaflicker buttons call the **same handlers as the footer**
     (`setEspnOpen(true)` / `setPlatformOpen('mfl')`), opening the **same** `EspnLinkSheet` /
     `PlatformLinkSheet`. Nothing about either flow changes.
   - The footer (`:386-421`) is **suppressed in this state only** — otherwise the same three
     buttons render twice on one screen. It keeps rendering unchanged in the loading-done, error,
     and list states, so no existing capture or flow moves.
   - Non-account-only users keep today's exact empty state (`capture/leagues@fresh.yaml` asserts
     its literal sentence — it must not move).

**(d) The Sleeper option.** The handoff's copy names Sleeper first, but Sleeper is *not* in the
footer today — it is a Settings-only form. Sending the user to Settings for the option the copy
lists first would re-create the exact dead end this finding is about.

**Extract `mobile/src/components/LinkSleeperSheet.tsx`** from `SettingsScreen.tsx:1210-1236` +
`:423-472`, moving the username field, `linkSleeperUsername()` call, the 409
`merge_choice_required` two-boards Alert, and the `sleeper_already_claimed` message **verbatim**,
with an `onLinked(res)` callback. Consumed in two places:

- `SettingsScreen` — replaces the inline card; its `onLinked` keeps today's behaviour exactly
  (`setUser`, `setLeague(null)`, invalidate `['account']`, `replace('LeaguePicker')`).
- `LeaguePickerScreen` — the `leagues.empty.link-sleeper` button opens it; `onLinked` does
  `setUser(...)` + `setLeague(null)` + invalidate, and **stays on the picker**.

This is the one place the plan spends more than the minimum, and it is deliberate: the alternative
is either duplicating ~60 lines of merge-conflict handling (which will drift) or shipping copy that
offers Sleeper and then routes to Settings. Extraction is the smaller long-term cost. *(If the
operator prefers zero refactor, the fallback is a `leagues.empty.link-sleeper` button that
navigates to Settings' account section — see §8 OQ-1.)*

### 2.3 Post-link refresh — what happens after a successful link

**ESPN / MFL / Fleaflicker:** nothing new is needed. `EspnLinkSheet`/`PlatformLinkSheet` →
`onLeagueLinked` (`:208-225`) → merges the row → `pickLeague()` → `buildSessionInitBody` (ESPN/MFL
branch, no Sleeper) → `setLeague({real league})` → `onLeaguePicked()` → `replace('Main')`. The
sentinel is gone, the tabs are populated, `submitSessionInit` runs in the background on the **same
session token**. The user never sees the picker re-render — they go straight to a working app.
*Verified end-to-end above; no code change required for this leg.*

**Sleeper username:** `onLinked` swaps the user to the real Sleeper id and clears the league. The
existing `useEffect` on `[user?.user_id]` (`:142-150`) fires, `cached.length` is 0, so `refresh()`
runs — and now `user.account_only` is falsy, so the Sleeper fetch happens and the real league list
paints in place. **The picker refreshes itself with no new wiring**; this is a property of the
existing effect, and the test plan asserts it rather than trusting it.

**Link failure:** unchanged — each sheet owns its own error surface; the picker stays in the
companion state with all options still offered.

### 2.4 Back-navigation story

- **Can they skip?** No skip affordance is added. The screen's existing header **"Sign out"**
  (`:296`) is the deliberate and only exit, and it is the honest one: an account with no league has
  nothing to show. Adding a "Skip for now" would rebuild the stranding this finding removes, one
  tap further in.
- **Can they go back?** No. Both entries are `replace` (`RootNav.tsx:410` post-fix, and Settings'
  existing `replace('LeaguePicker')`), so there is no back edge, and iOS swipe-back has no target.
- **What if they force their way to `Main`?** After (b), the sentinel routes them back to the picker
  at every cold start, so the only remaining doors are (i) the capture harness's `FTFTestRoute`
  launch argument, which is `testMode`-gated and cannot exist in a production bundle
  (`mobile/src/utils/testRouteEntry.ts:51-56`), and (ii) a notification tap
  (`utils/deepLinks.ts:routeNotificationTap`) — unreachable in practice, since every push this app
  sends is league- or match-scoped and an account-only user has neither. **Deliberately not
  hardening (ii):** a guard there would be dead code with no way to test it. If P0-3's deep-link
  work lands a URL that can reach `Main` directly, that guard becomes real — flagged in §8.
- **What an account-only user sees in `Main` if they somehow arrive:** unchanged by this plan
  (empty league surfaces). Fixing the tabs' empty states is out of scope; the routing change means
  no user reaches them by any normal path.

---

## 3. Exact change list

| # | File | Change | Est. |
|---|---|---|---|
| 1 | `mobile/src/navigation/RootNav.tsx:410` | `onAccountSignedIn` → `navigation.replace('LeaguePicker')`; update the adjacent comment (it currently *explains* the bug: "account-only sessions have no leagues to pick"). | 2 lines |
| 2 | `mobile/src/navigation/RootNav.tsx:297-301` | Sentinel-aware `initialRoute` via `hasRealLeague`; import `NO_LEAGUE_ID` from `../state/useSession`. | ~5 lines |
| 3 | `mobile/src/screens/LeaguePickerScreen.tsx:152-203` | `refresh()`: skip `getLeagues()` when `user.account_only`; keep all platform merges. | ~6 lines |
| 4 | `mobile/src/screens/LeaguePickerScreen.tsx:313-318` | New `accountOnlyEmpty` branch: heading, "Connect Sleeper, ESPN or MFL to see your leagues", and the flag-gated Sleeper/ESPN/MFL(/Flea) buttons reusing the existing handlers. Non-account-only empty state untouched. | ~45 lines |
| 5 | `mobile/src/screens/LeaguePickerScreen.tsx:386` | Suppress the footer while the companion state is showing (`&& !accountOnlyEmpty`). | 1 line |
| 6 | `mobile/src/screens/LeaguePickerScreen.tsx:289-297` | Header copy: "Connect a League" when `accountOnlyEmpty`, else today's "Choose a League". | ~3 lines |
| 7 | `mobile/src/screens/LeaguePickerScreen.tsx` (new) | Mount `<LinkSleeperSheet>`; `onLinked` → `setUser` + `setLeague(null)` + invalidate `['account']`. | ~15 lines |
| 8 | `mobile/src/components/LinkSleeperSheet.tsx` **(new)** | Extracted verbatim from `SettingsScreen.tsx:423-472` + `:1210-1236`: input, `linkSleeperUsername`, 409 merge Alert, `sleeper_already_claimed`, busy state. Props: `visible`, `onClose`, `onLinked(res)`. | ~110 lines (moved) |
| 9 | `mobile/src/screens/SettingsScreen.tsx:423-472, 1210-1236` | Replace the inline form with `<LinkSleeperSheet>`; behaviour identical (`replace('LeaguePicker')` on success). Keep `testID="settings.link-sleeper-input"` **on the extracted input** so the id survives the move. | net −60 lines |
| 10 | `mobile/.maestro/flows/p0-5-account-only-picker.yaml` **(new)** | See §5. | new flow |
| 11 | Harness seam (backend + client) | See §5 — required to make (10) runnable. | ~25 lines, test-gated |

**No backend product code changes.** Items 11's backend half is `FTF_TEST_MODE`-only.

**Files another agent may also touch — coordinate before editing:** `RootNav.tsx` and
`utils/deepLinks.ts` are P0-3's primary surface. This plan touches `RootNav.tsx` in two small,
well-separated places (`:297-301`, `:410`); P0-3's route-table work is at `:303-325`. Land P0-5
first (smaller), or have P0-3 rebase.

---

## 4. Surface changes

**Server-side: none.** Confirmed by reading the routes, not by assumption:

- No new/changed API routes. `/api/espn/link`, `/api/mfl/link`, `/api/account/link-sleeper`,
  `/api/session/init` are all called with their **existing** contracts from **existing** call sites.
- No schema change. No `config/features.json` change.
- No response-shape change to `/api/auth/apple` — the client already receives everything it needs
  (`account_only`, `session_token`, `league_id`, `league_name`).

**No new feature flag, and that is a deliberate call.** The change is a *bug fix on a branch that is
currently broken for 100% of its users*: there is no working behaviour to preserve behind an off
switch, so a flag would only add a way to ship the bug back. The blast radius is bounded to sessions
where `account_only === true` or `league_id === 'no_league'` — no Sleeper-keyed or demo session can
enter any new branch. The existing `espn.link` / `mfl.link` / `fleaflicker.link` flags still gate
each platform button individually, so the rollback lever for any *platform* remains where it is.
*(If the operator wants a kill switch anyway, the honest shape is `auth.account_only_picker`,
default ON, gating items 1+2 only — that is the only pair with a coherent "old behaviour".)*

**New client analytics events: none.** Per the handoff's own trap list, the taxonomy
(`backend/analytics_taxonomy.py`, `ALLOWED_CLIENT_EVENTS`) is default-deny and a new name would be
silently dropped unless registered first. The funnel is already bracketed by existing events:
`signin_succeeded {method:'apple'}` (`SignInScreen.tsx:183`) and `league_selected`
(`LeaguePickerScreen.tsx:232-250`, which fires for imported leagues too, via
`onLeagueLinked` → `pickLeague`). The gap between those two counts is exactly the
"stranded" population, before and after. See §8 OQ-3 for the one event worth adding later.

**New testIDs** (must pass `mobile/scripts/testid-lint.sh`; all static string literals, no allow-list
entry needed): `leagues.empty.link-sleeper`, `leagues.empty.link-espn`, `leagues.empty.link-mfl`,
`leagues.empty.link-fleaflicker`, `leagues.empty.body`.

---

## 5. Maestro delta

### The problem: the harness cannot perform a real Apple sign-in

`AppleAuthentication.signInAsync` raises a system sheet requiring a real Apple ID and password —
undrivable by Maestro and off-limits to automate — and `/api/auth/apple` verifies the identity token
against Apple's live JWKS (`backend/accounts.py:214-221`). The pytest suite gets around this by
signing its own token with a monkeypatched JWKS (`backend/tests/test_account_first.py:60-83`), which
is a fixture-level trick unavailable to an on-simulator flow. **There is no existing account-only
seam in the sim harness** — `backend/test_support.py` exposes `pin/*`, `fail_next`, `latency`,
`reset`, `whoami` and nothing auth-shaped, and no seeder profile
(`backend/tests/fixtures/profiles/*.json`) produces an account-only user.

### The seam (item 11), following existing harness precedent

Two halves, each gated by an existing, audited production kill:

1. **Backend** (`backend/server.py`, inside `auth_apple`): when `FTF_TEST_MODE=1` — the same env var
   that mounts the whole `/__test__` blueprint (`server.py:2015`) and is never set in Render — accept
   an identity token of the form `ftf-test-apple:<sub>` and synthesise `{"sub": "<sub>"}` instead of
   calling `verify_apple_token`. Everything downstream (`_provider_auth_response`,
   `_mint_account_only_session`) is the **real production path**, unmodified.
2. **Client** (`mobile/src/screens/SignInScreen.tsx`): gate **only** the SDK call. When
   `IS_TEST_BUILD` (the build-time `extra.testMode` constant already used by
   `mobile/src/utils/testRouteEntry.ts:51-56`, produced solely by `mobile/scripts/sim-build.sh` and
   `false` in every EAS bundle) **and** the launch argument `FTFTestAppleSub` is present, substitute
   `{identityToken: 'ftf-test-apple:' + sub}` for `AppleAuthentication.signInAsync()`, and render
   the Apple button even when `isAvailableAsync()` is false. **Every line after that — the
   `account_only` branch at `:167-185`, `setUser`, `setLeague`, `onAccountSignedIn` — is production
   code under test.**

This is the minimum that lets the flow exercise the actual fix. Stubbing further up (e.g. seeding
`useSession` directly) would test the harness instead of the branch.

### New flow — `mobile/.maestro/flows/p0-5-account-only-picker.yaml`

```
# tc: TC-P05-01
# profile: fresh
# flags: release
```

1. `launchApp: {clearState: true, clearKeychain: true, stopApp: true, arguments: {FTFTestAppleSub: qa-apple-p05}}`
2. `extendedWaitUntil` `signin.apple-btn` (15 000 ms) → `tapOn` it.
3. `extendedWaitUntil` `leagues.empty.link-espn` (30 000 ms) — **proves the acceptance criterion**:
   the picker's platform choice, reached from a brand-new Apple sign-in, with no Settings visit.
4. `assertVisible` `leagues.empty.link-sleeper`, `leagues.empty.link-mfl`,
   `text: ".*Connect Sleeper, ESPN or MFL.*"` (law 1 — full-match regex, wrap in `.*`).
5. `assertNotVisible` `id: "leagues.row.*"` and `assertNotVisible` `text: ".*No 2026 NFL leagues found.*"`
   — pins the state from both sides (the pattern `capture/leagues@fresh.yaml:20-26` established),
   and proves the false-error path is gone.
6. `assertNotVisible` `tab.trades` — proves it did **not** route to `Main`.
7. `takeScreenshot: p0-5-account-only-picker` (shot immediately, per law 5 — no
   `waitForAnimationToEnd` near a spinner).
8. **Relaunch leg** (covers design part (b)): `launchApp: {clearState: false, stopApp: true}` →
   `extendedWaitUntil` `leagues.empty.link-espn` → `assertNotVisible` `tab.trades`. This is the
   half the audit's one-line fix would have missed.
9. **Link leg:** `tapOn: leagues.empty.link-mfl` → assert the `PlatformLinkSheet` painted. Stop
   there: completing an MFL import needs live MFL egress, which the hermetic harness forbids
   (`sim-run` rails audit) and no MFL fixture exists. Full link→`Main` is covered by the manual
   TestFlight pass in §7 and by the existing ESPN-link flows for Sleeper-keyed users.

**Extended flow:** `mobile/.maestro/capture/leagues@fresh.yaml` — **unchanged**, and that is a
required assertion: it signs in as `qa_no_leagues` (a Sleeper-keyed user with an empty league list)
and asserts the literal *"No 2026 NFL leagues found for this account."*. It must still pass, proving
the companion state did not leak into the non-account-only empty state.

**Capture delta:** new `mobile/.maestro/capture/leagues@account-only.yaml` for the screen library
(one screenshot, same launch-argument entry), since this is a new visual state of an existing
screen. Existing `leagues*` captures are unaffected.

---

## 6. Docs impact

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. The `FTF_TEST_MODE` token seam in `/api/auth/apple` is harness-only and never reachable in any deployed build — noted in the runbook instead. |
| `living-memory/LLD.md` | **yes** | New convention: **post-auth routing keys off the `no_league` sentinel, never off `user.account_only`** (the latter stays true after an ESPN/MFL link). Plus: `LinkSleeperSheet` is the single owner of the Sleeper-identity-link form. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change; one prop value and one branch inside an existing screen. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow — an existing flow is being connected to an existing screen. |
| `docs/cross-client-invariants.md` | **yes (small)** | `no_league` is a shared string constant emitted by `server.py:17956` and consumed by `useSession.ts:56` and now by RootNav's routing predicate. It is currently documented nowhere. Add it to the shared-enum table. |
| `docs/glossary.md` | **yes** | Add **account-only session** — Apple/Google identity with no bound Sleeper source; working key `acct_<account_id>`; sentinel league `no_league`. The term appears throughout the code and in no glossary. |
| `docs/runbook.md` | **yes** | Under the mobile UI-test harness section: the `FTFTestAppleSub` launch argument + `ftf-test-apple:<sub>` token seam, with the explicit statement of both production gates. |
| ADR / `DECISIONS.md` | **yes — `D-011`** | "Account-only sessions route to LeaguePicker; the sentinel league, not the `account_only` flag, is the routing predicate." Records the rejected sheet-over-`Main` alternative and the no-new-flag call. |
| `living-memory/CHANGELOG.md` | **yes, at ship** | Dated H2. |
| `living-memory/TEST_LEDGER.md` | **yes, at ship** | Sim-run tier + result. |

---

## 7. Test plan

**Automated — backend (`python3 -m pytest backend/tests/ -q`):**
1. `backend/tests/test_account_first.py` — must stay green untouched; it is the contract for
   `account_only`, the sentinel, and `verified_via` persistence.
2. New: with `FTF_TEST_MODE` unset, `POST /api/auth/apple` with `identity_token="ftf-test-apple:x"`
   returns **401 `invalid_token`** — the production gate on the harness seam, asserted, not assumed.
3. New: an account-only session can `POST /api/espn/link` (preview leg) without a Sleeper identity —
   the claim this whole design rests on, pinned as a test.
4. New: `/api/session/init` posted with an `acct_` user id and the existing token **reuses the token
   and preserves `verified`/`verified_via`** — the regression that would silently 403 these users
   out of their own board after linking.

**Automated — mobile:** `cd mobile && npx tsc --noEmit`; `mobile/scripts/testid-lint.sh`.

**Automated — Maestro (hermetic, seeded backend):**
5. `flows/p0-5-account-only-picker.yaml` — new, §5.
6. `capture/leagues@fresh.yaml` — unchanged, must pass (non-regression of the Sleeper-keyed empty state).
7. `flows/smoke/01-signin.yaml` + `02-league-pick.yaml` — the Sleeper sign-in → picker → `Main`
   path, unchanged; these are the guard on change #2 (`initialRoute`).
8. `flows/smoke/*` (11 flows) — Tier-1 change class (navigation + screen), so the full suite runs.
9. `capture/settings.yaml` — Settings still renders after the `LinkSleeperSheet` extraction.

**Manual (TestFlight / device, the legs the hermetic harness structurally cannot cover):**
10. **The acceptance criterion, unstubbed:** real Apple sign-in on a brand-new Apple ID → lands on
    the picker with the three platform options. No Settings visit.
11. Tap **Connect ESPN** → real link → lands in `Main` with the ESPN league active, tabs populated,
    board writable (proves the `verified` survival of #4 in the real world).
12. Force-quit and relaunch **before** linking → back on the picker, not on empty tabs.
13. Force-quit and relaunch **after** linking → `Main`, with the linked league. (Guards against
    over-broad predicate — an `account_only`-keyed predicate would fail exactly here.)
14. **Link Sleeper username** from the picker's companion state → picker repaints with real Sleeper
    leagues in place, no navigation flicker.
15. Two-boards merge conflict (409) from the **picker** entry — the Alert must appear and both
    choices must work, identically to Settings. This is the extraction's only real risk.
16. Settings → "Link an ESPN league" and → MFL chooser, for an account-only user: both still land on
    the picker, which now shows the companion state rather than a Sleeper error.

**Ship gate:** Tier 1 (mobile screen + navigation change) — full smoke suite + the new flow, plus
`screen-capture.sh --screen leagues` and `--screen settings`. Evidence in `TEST_LEDGER.md` and
`qa/sim-runs/last-sim-run.json`.

---

## 8. Risks and open questions

### OQ-1 — The Sleeper option: extract, or route to Settings? *(operator call, decision needed before build)*
§2.2(d) commits to extracting `LinkSleeperSheet`. It is the only part of this plan that touches a
file the finding does not mention (`SettingsScreen.tsx`) and the only part that is more than
surgical. The fallback — a Sleeper button that navigates to Settings' account card — is ~5 lines and
zero refactor, but ships copy that offers Sleeper and then bounces the user to the screen this
finding is about. **Recommendation: extract.** Flagging because it is the one place where
"surgical changes" and the acceptance criterion pull in opposite directions.

### OQ-2 — **P0-3 intersection: the invited account-only Apple user.** *(must be resolved jointly, before either lands)*
P0-3 is adding `/app/league/join/<leagueId>?ref=<user>`, which **pins an invited league as active
once auth completes**. The intersection case:

> A user with no FTF account taps an invite link → installs → signs in with **Apple** → the server
> returns `account_only` with the **`no_league` sentinel**, and P0-5 routes them to the picker.

Three things collide, and they must be reconciled explicitly rather than discovered on-device:

1. **Ordering.** If P0-3's post-auth pin runs *after* P0-5's `replace('LeaguePicker')`, the user is
   sitting on "Connect your league" while the app already knows exactly which league they were
   invited to — the worst outcome available, because it asks a question it has the answer to.
2. **Predicate coupling.** P0-5's relaunch guard (`league_id === NO_LEAGUE_ID` → picker) will fight
   any P0-3 code that pins an invited league *without* clearing the sentinel — and will send the
   user back to the picker on next launch. **P0-3 must set the real league via `setLeague()`, which
   overwrites the sentinel; it must not carry the invite in a parallel field.**
3. **The harder half nobody has scoped.** An invited league is a *Sleeper* league. An account-only
   user has **no Sleeper user id**, so they are not a member of it — `buildSessionInitBody`'s Sleeper
   branch (`api/auth.ts:453-471`) would find no roster for `acct_<id>` and produce an empty
   `user_player_ids`. Pinning an invited Sleeper league for an account-only user is **not currently
   possible as built**. The correct behaviour is probably: keep the invite in
   `useSession.setInvitedBy` (which already survives, `useSession.ts:158-162`, and is consumed by
   `session_init`), route to the picker, and have the companion state *name the inviter and league*
   ("Ryan invited you to Dynasty Warriors — connect Sleeper to join"). That turns the intersection
   from a conflict into the strongest copy on the screen.

**Recommendation for the HLD:** treat "invited + account-only" as a first-class case owned by P0-3,
with P0-5's companion state as its landing surface, and land P0-5 first so P0-3 has a real
destination to pin against. **Do not let either agent assume the other handled it.**

### R-1 — Cold-start route flip for existing TestFlight account-only users
Change #2 is retroactive by design: anyone currently sitting on empty tabs with a sentinel league
will find themselves on the picker at next launch. That is the fix working, but it is a visible
change for existing testers. Worth a line in the release notes.

### R-2 — `LinkSleeperSheet` extraction regression risk
The 409 merge-conflict Alert is the highest-consequence code being moved (its failure mode is
*deleting the wrong ranking board*). Mitigations: move verbatim, keep
`testID="settings.link-sleeper-input"` on the extracted input so `capture/settings.yaml` and the
lint keep pointing at it, and manual test 15 exercises the conflict from the new entry point.

### R-3 — `RootNav.tsx` is contended
P0-3 owns the linking/route table in the same file. Sequence the merges; do not parallelise edits.

### C-1 — Contradiction with the audit's evidence: line numbers
The audit's citations (`server.py:17913`, `RootNav.tsx:398`, `/api/espn/link:18493`,
`/api/mfl/link:20119`) have all drifted by 100–160 lines in this worktree. Every one was re-located
and the **behaviour is exactly as described**. Noting it because the handoff warns that the working
tree mutates under concurrent sessions — re-verify before editing, do not trust these numbers either.

### C-2 — Contradiction with the audit's load-bearing assumption *(conditional, worth the operator's attention)*
The audit's assumption is *"new users will choose Apple — reasonable, since it's the primary
button."* **True under `release` flags** (`onboarding.landing: false` → the official Apple button
renders as primary, `SignInScreen.tsx:381-399`). But if `onboarding.landing` is ever flipped on —
which is live P0-9 territory — the Apple entry becomes a **text link reading "Already have an
account? Sign in with Apple"** (`:515-540`), explicitly framed for returning users. The fix in this
plan stays correct either way, but the *finding's severity* is flag-dependent in a way the audit
did not record. If the operator turns on `onboarding.landing`, the account-only branch becomes rarer
for new users and simultaneously *harder to discover* for the returning ones who need it.

### C-3 — Something the audit missed, and it changes the fix
The audit prescribes a one-line routing change. That fixes the *first* sign-in only: because
`initialRoute` (`RootNav.tsx:297-301`) counts the sentinel as a real league, the second launch
strands the user again. **The relaunch predicate is part of the fix, not a nicety.** Similarly, the
audit did not surface that today's picker produces a **false Sleeper error** for account-only users
(§1) — routing them there without change #3 would trade "empty tabs" for "Couldn't reach Sleeper".

### OQ-3 — Deferred instrumentation
The stranded population is measurable today as the gap between `signin_succeeded {method:'apple'}`
and `league_selected`, so nothing is added now. If P0-7 proceeds, the event worth registering is
`platform_link_started {platform, entry:'picker_empty'|'settings'}` — it would separate "never saw
the choice" from "saw it and declined", which the gap metric cannot. **Register the name in
`backend/analytics_taxonomy.py` before wiring any call.**
