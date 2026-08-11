# LLD-4 — P0-5: account-only sign-in reaches a platform/league choice

> Code-level design for build agent **`W1-P05`** (wave 1, commits **6** and **7**).
> Binding parent: [`hld.md`](hld.md) — §1.2 Spine A, §2 S-19…S-22, §3 commits 6-7, §4
> Wave 1 `W1-P05`, §5 (client half of the unified harness seam), §6 rows 2/3/13, §7,
> §8 R8/R10, §9 LLD-4. Source plan: [`plan-p0-5.md`](plan-p0-5.md); scope block:
> [`scope-p0-5.md`](scope-p0-5.md). Companion PRD: [`prd-p0-5.md`](prd-p0-5.md).
>
> **Where this document and a source plan disagree, the HLD is the authority and this
> LLD follows it.** Every deviation from the HLD is listed in §14 — there are three,
> all cosmetic or presentational, none touching a settled decision.
>
> Worktree `ftf-p0-remediation`, branch `p0-remediation-2026-08-10`, base
> `origin/main @ ab9368f`. All line numbers below were re-read in this worktree on
> 2026-08-11 and are **stale by construction** (HLD §8 R1) — every edit is specified
> against a **grep anchor**, and the line number is context only.

## Contents

- [1. Ownership, commits, and what this LLD may not do](#1-ownership-commits-and-what-this-lld-may-not-do)
- [2. Anchor discipline](#2-anchor-discipline)
- [3. Change A — `RootNav.tsx` `onAccountSignedIn`](#3-change-a--rootnavtsx-onaccountsignedin)
- [4. Change B — `RootNav.tsx` sentinel-aware `initialRoute`](#4-change-b--rootnavtsx-sentinel-aware-initialroute)
- [5. Change C — `LeaguePickerScreen` companion state](#5-change-c--leaguepickerscreen-companion-state)
- [6. Change D — `LinkSleeperSheet` extraction](#6-change-d--linksleepersheet-extraction)
- [7. Post-link flow verification](#7-post-link-flow-verification)
- [8. Back-navigation and skip](#8-back-navigation-and-skip)
- [9. Change E — the harness seam, client half](#9-change-e--the-harness-seam-client-half)
- [10. Backend pytests specified here, built by W1-BE](#10-backend-pytests-specified-here-built-by-w1-be)
- [11. Maestro delta](#11-maestro-delta)
- [12. Docs rows supplied to W3-DOCS](#12-docs-rows-supplied-to-w3-docs)
- [13. Verification checklist for the build agent](#13-verification-checklist-for-the-build-agent)
- [14. Deviations from the HLD](#14-deviations-from-the-hld)

---

## 1. Ownership, commits, and what this LLD may not do

**Files owned by `W1-P05` in wave 1** (HLD §4). No other agent opens them this wave;
`RootNav.tsx`, `LeaguePickerScreen.tsx` and `SignInScreen.tsx` hand over to `W2-P03`
in wave 2.

| File | Commit | Change |
|---|---|---|
| `mobile/src/utils/testRouteEntry.ts` | 6 | export the gate, `testLaunchArg()`, `SIGNED_OUT_ENTRY_ROUTES`, `applyTestRouteEntry(ref, {authed})` |
| `mobile/src/navigation/RootNav.tsx` | 6 | the `applyTestRouteEntry` call-site shape only |
| `mobile/src/screens/SignInScreen.tsx` | 6 | `IS_TEST_BUILD` + `FTFTestAppleSub` credential substitution; Apple-button render gate |
| `mobile/src/navigation/RootNav.tsx` | 7 | `onAccountSignedIn` → `LeaguePicker`; sentinel-aware `initialRoute`; `AuthStack.LeaguePicker` param widening; pass invite context through |
| `mobile/src/screens/LeaguePickerScreen.tsx` | 7 | skip the Sleeper fetch for `account_only`; companion state; footer suppression; header copy; mount `LinkSleeperSheet`; optional `invitedBy`/`invitedLeagueName` |
| `mobile/src/components/LinkSleeperSheet.tsx` **(new)** | 7 | verbatim extraction incl. the 409 `merge_choice_required` Alert |
| `mobile/src/screens/SettingsScreen.tsx` | 7 | replace the inline form with the extracted component |
| `mobile/.maestro/flows/p0-5-account-only-picker.yaml` **(new)** | 7 | §11.1 |
| `mobile/.maestro/capture/leagues@account-only.yaml` **(new)** | 7 | §11.2 |

**Two commits, not one, and in this order.** Commit 6 is the harness seam and is
independently green because `LeagueJoin` is not yet a registered route (the signed-out
allowance is inert until commit 12) and `TEST_APPLE_SUB` is `null` in every non-test
bundle. Commit 7 is the fix. Splitting them keeps a harness-only revert available
without reverting the user-visible fix.

**Must not** (HLD §9 LLD-4):
- add a skip affordance to the picker;
- key any predicate off `user.account_only`;
- change the non-`account_only` empty state — `capture/leagues@fresh.yaml` asserts its
  literal sentence *"No 2026 NFL leagues found for this account."* and is a
  must-pass-unmodified control (HLD §6 row 13);
- add a feature flag (S-04-analogue: scope §2, waiver **W-3**) or a client analytics
  event (the taxonomy is default-deny and commit 1 registers nothing for P0-5);
- edit `backend/server.py` (W1-BE owns it for the whole build), `useSession.ts`
  (W2-P03), `docs/**` or `living-memory/**` (W3-DOCS);
- extend `backend/tests/test_account_first.py` — HLD §10.5 routes the new cases to a
  **new** file owned by W1-BE (§10 below).

---

## 2. Anchor discipline

The audit's line numbers had already drifted 100-160 lines by the time the plans were
written, and the plans' numbers have drifted again (the HLD cites
`RootNav.tsx:341` for `applyTestRouteEntry`; it is `:344` today). **Before each edit,
re-locate by anchor:**

| Edit | `grep -n` anchor (exact substring) |
|---|---|
| A | `onAccountSignedIn={() => navigation.replace(` |
| B | `const initialRoute: keyof AuthStack = !user` |
| B (types) | `LeaguePicker: { espnLink?: boolean } \| undefined;` |
| C1 | `const lgs = await getLeagues(user.user_id);` |
| C2 | `No 2026 NFL leagues found for this account.` |
| C3 | `{!loading && (espnEnabled || mflEnabled || fleaflickerEnabled) ? (` |
| C4 | `>Choose a League</Text>` |
| D (handler) | `async function handleLinkSleeper(strategy?:` |
| D (card) | `testID="settings.link-sleeper-input"` |
| E1 | `const IS_TEST_BUILD =` |
| E2 | `if (initialRoute === 'Main') applyTestRouteEntry(navigationRef);` |
| E3 | `const cred = await AppleAuthentication.signInAsync({` |
| E4 | `{!landingOn && appleAvailable ? (` and `{landingOn && appleAvailable ? (` |

---

## 3. Change A — `RootNav.tsx` `onAccountSignedIn`

**Current** (`mobile/src/navigation/RootNav.tsx:401-413`, verbatim):

```tsx
        <Stack.Screen name="SignIn">
          {({ navigation }) => (
            <SignInScreen
              onSignedIn={() => navigation.replace('LeaguePicker')}
              // Demo flow already pinned a synthetic league + token in
              // useSession.startDemoSession, so we jump straight to Main.
              onDemoStarted={() => navigation.replace('Main')}
              // Account-first (P2.6): account-only sessions have no leagues
              // to pick — the sentinel league is already pinned.
              onAccountSignedIn={() => navigation.replace('Main')}
            />
          )}
        </Stack.Screen>
```

The comment is not incidental — it *states the bug as the design*. It must be rewritten
in the same edit, or the next reader restores the behaviour.

**After:**

```tsx
              // Account-first (P2.6) + P0-5: an account-only session holds the
              // `no_league` sentinel, NOT a league — it has nothing to show in
              // the tabs. Route to the picker, whose companion state leads with
              // "Connect Sleeper, ESPN or MFL". `replace`, not `navigate`: the
              // SignIn screen's session is spent and must not stay on the stack.
              onAccountSignedIn={() => navigation.replace('LeaguePicker')}
```

`onDemoStarted` stays `replace('Main')` — the demo league is a real pinned league, not
the sentinel — and `onSignedIn` is untouched.

---

## 4. Change B — `RootNav.tsx` sentinel-aware `initialRoute`

### 4.1 The predicate

**Current** (`:293-301`, verbatim):

```tsx
  // Decide initial stop based on what's persisted.
  // - No user  → SignIn
  // - User + no league (or no token) → LeaguePicker
  // - User + league + token → Main tabs
  const initialRoute: keyof AuthStack = !user
    ? 'SignIn'
    : !league || !hasToken
    ? 'LeaguePicker'
    : 'Main';
```

The sentinel **is** a league object (`{league_id: 'no_league', league_name: 'No league
linked'}`, pinned by `SignInScreen`'s account-only branch) and `hasToken` is true
(`useSession.setLeague` sets `hasToken: !!lg`), so `!league || !hasToken` is false and a
cold start after the first bad run lands on `Main` again. **Change A alone fixes only
the first sign-in.** This is the half the audit missed (plan §8 C-3) and it is what
makes the fix retroactive for testers already stranded on TestFlight (HLD §8 R10).

**After:**

```tsx
  // Decide initial stop based on what's persisted.
  // - No user  → SignIn
  // - User + no REAL league (or no token) → LeaguePicker
  // - User + real league + token → Main tabs
  //
  // P0-5: an account-only session pins the `no_league` SENTINEL, which is a
  // league object and therefore passed the old `!league` test — so relaunch
  // stranded the user on empty tabs even after the sign-in route was fixed.
  // Key off the sentinel, NEVER off `user.account_only`: account_only stays
  // true after an ESPN/MFL link (it is cleared only by linking a Sleeper
  // username, SettingsScreen's handleLinkSleeper), so an account_only
  // predicate would trap a well-provisioned user in the picker forever.
  // `setLeague(real)` overwrites the sentinel, which is what ends this state.
  const hasRealLeague = !!league && league.league_id !== NO_LEAGUE_ID;
  const initialRoute: keyof AuthStack = !user
    ? 'SignIn'
    : !hasRealLeague || !hasToken
    ? 'LeaguePicker'
    : 'Main';
```

**Import:** `NO_LEAGUE_ID` joins the existing `useSession` import at
`RootNav.tsx:13` — `import { useSession, NO_LEAGUE_ID } from '../state/useSession';`
(`NO_LEAGUE_ID` is already exported at `useSession.ts:56`; this is a read of an existing
export, which is why HLD §4's contention table leaves `useSession.ts` wholly to W2-P03).

This is the S-22 rule stated in code. Quoting the decision of record verbatim so the
build agent cannot re-derive it wrongly:

> **S-22 | P0-5 | Routing predicate keys off `league.league_id === NO_LEAGUE_ID`, never
> `user.account_only`. | `account_only` stays true after an ESPN/MFL link, so that
> predicate would trap a well-provisioned user in the picker forever.**

### 4.2 Blast radius of the predicate change

`initialRoute` has exactly two consumers: `Stack.Navigator initialRouteName` (`:399`)
and the harness gate at `:344` (§9.3). For every non-account-only session
`hasRealLeague === !!league`, so the expression is **behaviour-identical** — this is
what keeps `flows/smoke/01-signin.yaml` and `02-league-pick.yaml` green unmodified. The
only sessions whose routing changes are those holding the sentinel, which is exactly the
`account_only` population and no one else. Demo sessions pin a real synthetic league id
(`useSession.startDemoSession`), not the sentinel, and are unaffected.

### 4.3 Param-list widening (the P0-3 seam)

**Current** (`:52-53`):

```tsx
  // #130 — `espnLink: true` auto-opens the ESPN link sheet (Settings CTA).
  LeaguePicker: { espnLink?: boolean } | undefined;
```

**After:**

```tsx
  // #130 — `espnLink: true` auto-opens the ESPN link sheet (Settings CTA).
  // P0-5/P0-3 — optional invite context. When an invited user arrives with
  // an account-only session, LeagueJoinScreen (P0-3, commit 12) replaces into
  // this screen carrying the inviter + league name; the picker's companion
  // state renders them as its lead copy. Nothing supplies them in wave 1 and
  // the companion state renders its generic copy when they are absent.
  LeaguePicker:
    | { espnLink?: boolean; invitedBy?: string; invitedLeagueName?: string }
    | undefined;
```

and the `LeaguePicker` `Stack.Screen` element (`:414-427`) gains two pass-throughs
beside the existing `autoOpenEspnLink={route.params?.espnLink === true}`:

```tsx
              invitedBy={route.params?.invitedBy ?? null}
              invitedLeagueName={route.params?.invitedLeagueName ?? null}
```

Both are optional on the screen's `Props` (§5.5), so this compiles and renders exactly
as today while nothing sets them. **This is the whole of P0-3's wiring cost:**
`replace('LeaguePicker', { invitedBy, invitedLeagueName })`.

---

## 5. Change C — `LeaguePickerScreen` companion state

### 5.1 Detection condition

One derived boolean, computed after the existing state hooks and before the render:

```tsx
  // P0-5 — the companion state: a session-holder with no league to pick and no
  // Sleeper identity to look one up with. Detected from DATA (account_only +
  // an empty list), not from a navigation param, so it is equally correct on a
  // first sign-in, a cold relaunch, and an arrival from Settings.
  const canLink = sleeperLinkEnabled || espnEnabled || mflEnabled || fleaflickerEnabled;
  const accountOnlyEmpty = !!user?.account_only && cached.length === 0 && canLink;
```

`sleeperLinkEnabled` is `useFlag('auth.accounts')` — the same flag that must be ON for
an account-only session to exist at all, added beside the three existing platform flags
(`LeaguePickerScreen.tsx:62-64`) so the Sleeper button is gated symmetrically with the
others.

`canLink` is a deliberate floor: with every link flag off, the companion state would
render a heading, a sentence, and nothing to press. In that (release-impossible)
configuration the screen falls through to today's empty sentence, which is no worse than
today. It is also what keeps the flag-gating story honest — scope §2's claim that
"existing flags remain the per-platform rollback lever" is only true if turning them all
off returns the old screen.

**Ladder position** (existing render ladder at `:299-381`):

```
loading  →  accountOnlyEmpty  →  error  →  cached.length === 0  →  list
```

`accountOnlyEmpty` is placed **above** `error` on purpose. After C2 an account-only
refresh performs no Sleeper call, so the only reachable `error` is a local persistence
failure whose "Try again" button would retry nothing the user needs; the three link
buttons are the only actionable content on that screen. It is placed **below**
`loading` so the state never flashes before the platform merges resolve.

### 5.2 C1 — skip the Sleeper fetch (the false 503)

**Current** (`refresh()`, `:152-160`):

```tsx
  async function refresh() {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const lgs = await getLeagues(user.user_id);
```

**After** — one conditional, everything downstream untouched:

```tsx
  async function refresh() {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      // P0-5 — NEVER ask Sleeper about a synthetic id. An account-only user's
      // user_id is `acct_<account_id>`; GET /api/sleeper/leagues/acct_… proxies
      // that key to Sleeper, which returns null live (→ the "No 2026 NFL
      // leagues found" sentence) and raises a fixture-miss 599 under the VCR
      // harness (→ 503 sleeper_unavailable → "Couldn't reach Sleeper"). Both
      // blame Sleeper or the user for a situation that is neither. The platform
      // merges below are session-scoped and MUST still run: an account-only
      // user who already linked ESPN from Settings has leagues to list.
      const lgs = user.account_only ? [] : await getLeagues(user.user_id);
```

Everything from `const merged: LeagueSummary[] = [...lgs];` onward is unchanged, so the
ESPN / MFL / Fleaflicker merges, the `seen` de-dupe, `setLeagues(merged)` and the
`catch`/`finally` all keep their current behaviour. **The skip is what makes the false
error unrenderable** — not a swallow at the render layer, but the absence of the call.

### 5.3 C2 — the companion branch

Replaces nothing; it is inserted as a new ladder rung immediately above the existing
`error` rung. The existing `cached.length === 0` rung (`:313-318`) is left byte-identical
so `capture/leagues@fresh.yaml` keeps passing.

```tsx
      ) : accountOnlyEmpty ? (
        <View style={styles.centered}>
          <Text testID="leagues.empty.body" style={styles.emptyBody}>
            {invitedBy
              ? `@${invitedBy} invited you to ${invitedLeagueName || 'their league'}. ` +
                'Connect Sleeper, ESPN or MFL to join.'
              : 'Connect Sleeper, ESPN or MFL to see your leagues.'}
          </Text>
          {sleeperLinkEnabled ? (
            <Button
              testID="leagues.empty.link-sleeper"
              label="Connect Sleeper"
              onPress={() => setSleeperOpen(true)}
            />
          ) : null}
          {espnEnabled ? (
            <Button
              testID="leagues.empty.link-espn"
              label="Connect ESPN"
              variant="secondary"
              onPress={() => setEspnOpen(true)}
            />
          ) : null}
          {mflEnabled ? (
            <Button
              testID="leagues.empty.link-mfl"
              label="Connect MFL"
              variant="secondary"
              onPress={() => setPlatformOpen('mfl')}
            />
          ) : null}
          {fleaflickerEnabled ? (
            <Button
              testID="leagues.empty.link-fleaflicker"
              label="Connect Fleaflicker"
              variant="secondary"
              onPress={() => setPlatformOpen('fleaflicker')}
            />
          ) : null}
        </View>
      ) : error ? (
```

Notes that are load-bearing:

- **The handlers are the footer's handlers, verbatim** — `setEspnOpen(true)` and
  `setPlatformOpen('mfl' | 'fleaflicker')` open the *same* `EspnLinkSheet` /
  `PlatformLinkSheet` instances already mounted at `:423-435`. Nothing about either
  link flow changes; both are audit-graded A−/B+ and are reused, not rebuilt.
- **Copy.** The invite fork is two sentences, not an em-dash clause, so that **one**
  Maestro matcher — `text: ".*Connect Sleeper, ESPN or MFL.*"` — is a full-match regex
  hit in *both* variants (law 1). See §14 D-3.
- **Sleeper is first and is the only primary button**; ESPN/MFL/Fleaflicker are
  `secondary`. That mirrors the handoff copy's ordering and the Chalkline rule that a
  screen has one primary action.
- `styles.emptyBody` is a new style: `{ ...type.body, textAlign: 'center' }`. The
  existing `styles.error` is `semantic.neg` (red) and must not be reused for
  non-error copy.
- `disabled={!!selectingId}` is **not** needed here: `selectingId` is only non-null
  during `pickLeague`, which cannot run while `cached.length === 0`.

### 5.4 C3 / C4 — footer suppression and header copy

Footer (`:386`), one added conjunct — scoped to this state only, so the loading-done,
error and list states keep rendering it exactly as today:

```tsx
      {!loading && !accountOnlyEmpty && (espnEnabled || mflEnabled || fleaflickerEnabled) ? (
```

Its comment gains one sentence: *"Suppressed in the P0-5 companion state, which offers
the same platforms as full-width primary actions — rendering both would show every
button twice."*

Header (`:293`):

```tsx
          <Text style={styles.title} accessibilityRole="header">
            {accountOnlyEmpty ? 'Connect a League' : 'Choose a League'}
          </Text>
```

The sub-line `Leagues for {user?.display_name || '…'}` is unchanged (it reads
"Leagues for Manager" for a fresh Apple account, which is honest and matches every other
surface's treatment of the account display name).

### 5.5 C5 — props, sheet state, and the `LinkSleeperSheet` mount

Props (`:38-44`) gain two optional fields — **the P0-3 hand-off contract**:

```tsx
interface Props {
  onLeaguePicked: () => void;
  onSignOut: () => void;
  /** #130 — open the ESPN link sheet on mount (Settings CTA). Honored only
   *  while the `espn.link` flag is on. */
  autoOpenEspnLink?: boolean;
  /** P0-3 (commit 12) — invite context for an account-only arrival via
   *  LeagueJoin. Optional and unset in wave 1; when present the companion
   *  state names the inviter and league instead of its generic copy. Never
   *  used to PIN a league: an acct_ user has no Sleeper roster in an invited
   *  Sleeper league (see hld.md §1.3). */
  invitedBy?: string | null;
  invitedLeagueName?: string | null;
}
```

New local state beside `espnOpen` / `platformOpen`:

```tsx
  const [sleeperOpen, setSleeperOpen] = useState(false);
```

Mount, **conditionally**, beside the existing sheets:

```tsx
      {sleeperOpen ? (
        <LinkSleeperSheet
          visible
          onClose={() => setSleeperOpen(false)}
          onLinked={onSleeperLinked}
        />
      ) : null}
```

The conditional mount mirrors `PlatformLinkSheet`'s (`:428-435`) and is deliberate: this
screen already carries a 14-line comment (`:73-86`) about an iOS RN sibling-modal wedge
in which a half-presented `<Modal>` blocked its sibling from ever presenting. A third
always-mounted `<Modal>` on this screen re-opens that hazard for no benefit.

Handler:

```tsx
  // The Sleeper *identity* link (not league linking): the session stops being
  // account-only and becomes keyed to a real Sleeper user. Drop the sentinel
  // league and let the existing [user?.user_id] effect re-run refresh() — with
  // account_only now falsy, the Sleeper fetch happens and the real list paints
  // IN PLACE. No navigation: the user asked for their leagues and this screen
  // is where leagues live. (Settings' copy of this handler navigates because
  // it is not the picker; see LinkSleeperSheet's header.)
  async function onSleeperLinked(res: LinkSleeperResponse) {
    setSleeperOpen(false);
    await setUser({
      user_id:      res.sleeper_user_id,
      username:     res.username,
      display_name: res.display_name || res.username,
      avatar_id:    res.avatar ?? null,
    });
    await setLeague(null);
    queryClient.invalidateQueries({ queryKey: ['account'] });
  }
```

Requires two new imports in this screen: `useQueryClient` from `@tanstack/react-query`
(`const queryClient = useQueryClient();`) and the `LinkSleeperResponse` type from
`../api/auth` (which the screen already imports `buildSessionInitBody`/
`submitSessionInit` from). `setUser` is already selected from the store? — **no**: the
screen currently selects `user`, `leagues`, `setLeagues`, `setLeague` (`:52-55`); add
`const setUser = useSession((s) => s.setUser);`.

Ordering matters and is copied from Settings: `setUser` **then** `setLeague(null)`. The
`[user?.user_id]` effect (`:142-150`) fires on the user change; `cached.length` is 0 at
that moment, so it calls `refresh()`.

---

## 6. Change D — `LinkSleeperSheet` extraction

Approved by **S-20**. This is the only part of P0-5 that touches a file the finding does
not mention, and HLD §8 **R8** rates it the highest-consequence code being moved: the 409
`merge_choice_required` Alert's failure mode is *deleting the wrong ranking board*.

### 6.1 What moves, exactly

From `mobile/src/screens/SettingsScreen.tsx`:

| Region | Anchor | Disposition |
|---|---|---|
| `:415-421` — the section comment + `linkUsername` / `linkBusy` state | `// ── Link Sleeper username (account-first P2.6)` | **moves** (state becomes the component's own) |
| `:423-473` — `handleLinkSleeper`, incl. the 409 Alert and the `sleeper_already_claimed` branch | `async function handleLinkSleeper(strategy?:` | **moves verbatim**, except the four post-success lines (below) |
| `:1210-1235` — the `<Card>` body: help text, `TextInput`, `Button` | `testID="settings.link-sleeper-input"` | **moves**; Settings keeps the `<Card>` wrapper and the `accountQuery.data?.account_only` condition |
| `:1573-1574`, `:1591` — `connectBody` / `connectHelp` / `connectInput` styles | `connectBody: { gap: space.md },` | **copied, not moved** — three other Settings cards (`:757`, `:1171`) use the same styles; deleting them breaks unrelated UI |

The four post-success lines **do not move** — they are the caller's, and they differ
between the two mount points:

```tsx
      await setUser({ … });
      await setLeague(null);
      queryClient.invalidateQueries({ queryKey: ['account'] });
      navigation.replace?.('LeaguePicker');     // Settings only
```

Everything else in `handleLinkSleeper` — the trim/guard, `setLinkBusy`, the
`linkSleeperUsername(uname, strategy)` call, the `ApiError` body read, the whole
`Alert.alert('Two boards found', …)` block with its `keep_account` / `keep_sleeper`
recursion, `sleeper_already_claimed`, the generic failure, and `finally` — moves
character-for-character. **Do not reformat it.** The reviewer's job on this hunk is a
byte diff, and any tidy-up destroys that.

`SettingsScreen` also drops the now-unused `linkSleeperUsername` from its `../api/auth`
import (`:27`) — `appleSignIn`, `deleteAccount`, `getAccount` stay.

### 6.2 The shared component

New file `mobile/src/components/LinkSleeperSheet.tsx`, two exports:

```tsx
export interface LinkSleeperFormProps {
  /** Fired after /api/account/link-sleeper succeeds. The caller owns every
   *  session mutation (setUser / setLeague / invalidate) and any navigation —
   *  Settings replaces into LeaguePicker, the picker stays put. */
  onLinked: (res: LinkSleeperResponse) => void | Promise<void>;
  /** Non-Alert failure surface. Settings passes its Toast; when omitted the
   *  form renders the message inline (testID `link-sleeper.error`). The 409
   *  two-boards case is ALWAYS an Alert and never routed here. */
  onNotice?: (msg: string, tone: 'warn') => void;
}

/** The form body only — no chrome. Settings renders it inside its existing
 *  <Card>; the sheet below wraps it in a Modal. */
export function LinkSleeperForm(props: LinkSleeperFormProps): JSX.Element

export interface LinkSleeperSheetProps extends LinkSleeperFormProps {
  visible: boolean;
  onClose: () => void;
}

/** Modal presentation for surfaces that have no card to host the form
 *  (LeaguePicker's companion state). */
export default function LinkSleeperSheet(props: LinkSleeperSheetProps): JSX.Element
```

`LinkSleeperSheet` is a thin shell — `<Modal visible transparent animationType="slide"
onRequestClose={onClose}>` + backdrop `Pressable` + `KeyboardAvoidingView` + a sheet
`View` with a grabber, the heading **"Link your Sleeper username"**, `<LinkSleeperForm
{...rest} />`, and a Cancel `Button` — structurally the same shell as
`PlatformLinkSheet.tsx:322-336`, so the two sheets on this screen look like siblings.
`onClose` is refused while `linkBusy` (same rule `PlatformLinkSheet.close()` applies),
so a modal can never be dismissed out from under an in-flight merge decision.

**All logic lives in `LinkSleeperForm`.** The sheet holds no state. That is what makes
"one owner of the Sleeper-identity-link form" true rather than aspirational.

`testID="settings.link-sleeper-input"` **travels with the `TextInput`, unrenamed.** Note
the factual correction to plan §8 R-2 and HLD §8 R8: **no Maestro flow references this
id today** (`grep -rn link-sleeper mobile/.maestro mobile/scripts` → no matches), so
`testid-lint.sh` and `capture/settings.yaml` are not in fact pointing at it. The id is
kept anyway — it is the only handle QA has on that field, and renaming it during an
extraction would be a second change wearing the first one's clothes.

### 6.3 The two mount points

**Settings** — the `<Card>` and its `accountQuery.data?.account_only` gate stay; only
the body changes:

```tsx
          {accountQuery.data?.account_only ? (
            <Card>
              <LinkSleeperForm
                onNotice={(msg, tone) => setToast({ msg, tone })}
                onLinked={async (res) => {
                  await setUser({
                    user_id:      res.sleeper_user_id,
                    username:     res.username,
                    display_name: res.display_name || res.username,
                    avatar_id:    res.avatar ?? null,
                  });
                  await setLeague(null);
                  queryClient.invalidateQueries({ queryKey: ['account'] });
                  navigation.replace?.('LeaguePicker');
                }}
              />
            </Card>
          ) : null}
```

Post-extraction Settings behaviour is **identical**, including the toast wording, the
Alert, and the `replace('LeaguePicker')` destination — which, after change A/B/C, is now
a screen that receives these users properly instead of showing them a Sleeper error.

**LeaguePicker** — §5.5.

---

## 7. Post-link flow verification

Nothing in this section is new code. It is the existing wiring the design depends on,
quoted so the build agent verifies rather than assumes (and so QA knows what to watch).

### 7.1 ESPN / MFL / Fleaflicker — straight to `Main`, no new code

`onLeagueLinked` (`LeaguePickerScreen.tsx:208-225`) is already the sheets' `onLinked`
for both mounts and already ends in `pickLeague(summary)`:

```tsx
    const merged = [
      ...cached.filter((x) => x.league_id !== lg.league_id),
      summary,
    ];
    await setLeagues(merged);
    await pickLeague(summary);
```

and `pickLeague` (`:257-262`):

```tsx
      const body = await buildSessionInitBody(user, { league_id: lg.league_id, name: lg.name });

      // Persist the league so RootNav gates to 'Main' immediately and the
      // user sees their tabs while the backend is still processing.
      await setLeague({ league_id: lg.league_id, league_name: lg.name });
      onLeaguePicked();
```

`setLeague({real})` **overwrites the sentinel** in the store and in AsyncStorage, which
(a) sends `onLeaguePicked()` → `RootNav`'s `navigation.replace('Main')` (`:417`) and
(b) makes §4's `hasRealLeague` true on every subsequent cold start. Both halves of the
fix retire themselves the moment the user has a league. `buildEspnSessionInitBody`
(`mobile/src/api/espn.ts`) finds "my" roster by `m.user_id === user.user_id` — the
`acct_` key the ESPN import wrote — so it works unchanged for these users.

### 7.2 Sleeper username — the picker repaints itself

The effect this depends on (`:142-150`, verbatim):

```tsx
  useEffect(() => {
    if (!user) return;
    if (cached.length > 0) {
      setLoading(false);
      return;
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id]);
```

After `onSleeperLinked` (§5.5) sets a real Sleeper `user_id`, this effect fires,
`cached.length` is still 0, `refresh()` runs, and `user.account_only` is now falsy — so
C1's conditional takes the real branch and `getLeagues(<real id>)` populates the list in
place. **No navigation, no remount, no flicker.** The test plan asserts this (manual 14)
rather than trusting it.

### 7.3 The session survives the link — why the 403 test exists

`pickLeague`'s phase 2 posts `/api/session/init` with the existing `X-Session-Token`.
`backend/server.py:14624-14641` (the plan cites `:14626-14638`; it has drifted two
lines):

```python
    user_changed = bool(existing_sess
                        and existing_sess.get("user_id") != user_id)
    with _sessions_lock:
        if existing_sess:
            token = incoming_token
            # Verified state (account-auth P1) survives a same-user re-init
            # (league switch, revalidate) — the Sleeper-JWT proof bound the
            # SESSION to the user, not to a league. It must NOT survive the
            # token being re-pointed at a different user_id.
            if user_changed:
                existing_sess.pop("verified", None)
                existing_sess.pop("verified_via", None)
```

For an account-only user linking ESPN/MFL, `user_id` is still `acct_<id>`, so
`user_changed` is **false**, the incoming token is **reused**, and `verified` /
`verified_via='apple'` **survive**. That is the entire reason this design is safe:
`_mint_account_only_session` already called `mark_user_verified(acct_uid, 'apple')`
(`server.py:18059-18063`), so the users row has a verified controller. If a future edit
ever rotated the token or dropped `verified` on this path, the P1/P2.5 write gates would
403 the user out of their own board **at the exact moment they linked their first
league** — a latent failure invisible to every existing test. §10.4 pins it.

---

## 8. Back-navigation and skip

- **No skip affordance is added** (HLD §9 LLD-4 "must not"). The header's existing
  **"Sign out"** button (`:296`) is the only exit and is the honest one — an account
  with no league has nothing to show. A "Skip for now" would rebuild the stranding this
  finding removes, one tap further in.
- **No back edge exists.** Both entries are `replace` — change A, and Settings'
  pre-existing `replace('LeaguePicker')` — so the native-stack has no previous card and
  iOS swipe-back has no target.
- **Forcing a way to `Main`** after change B: a cold start re-routes to the picker every
  time. The remaining doors are (i) the capture harness's `FTFTestRoute` launch argument,
  which cannot exist in a production bundle (`testRouteEntry.ts` build-time gate), and
  (ii) a notification tap (`utils/deepLinks.routeNotificationTap`) — unreachable in
  practice, because every push this app sends is league- or match-scoped and an
  account-only user has neither. **Deliberately not hardened:** a guard there would be
  dead code with no way to test it.
- **P0-3 note (wave 2):** if `LeagueJoinScreen` ever routes an account-only session
  anywhere but `LeaguePicker`, door (ii) becomes real. HLD §1.3 case D forecloses it —
  `LeagueJoin` on an account-only session **replaces into the companion state**.
- **An account-only user who somehow reaches `Main`** sees the same empty league
  surfaces as today. Fixing those is out of scope; the routing change means no user
  reaches them by any normal path.

---

## 9. Change E — the harness seam, client half

Conforms to **HLD §5** exactly. **Two gates, both pre-existing** (`FTF_TEST_MODE`
server-side, owned by W1-BE; `IS_TEST_BUILD` client-side, mine). **No third gate, no new
`/__test__` route, no new feature flag, no new env var.** Approved as **S-21 / waiver
W-1**.

### 9.1 `testRouteEntry.ts` — three additions, all inside the existing gate

**1. Export the gate.** `const IS_TEST_BUILD =` → `export const IS_TEST_BUILD =`
(`:52-54`). One definition of the production kill, greppable in one place; the 40-line
"PRODUCTION GATE — review this constant in isolation" comment above it stays and gains
one line naming `SignInScreen` as the second consumer.

**2. One accessor for every harness launch argument:**

```ts
/**
 * A launch-argument value, or null. Null in every production build (see the
 * gate above), on non-iOS, and whenever the argument is absent or blank.
 *
 * Naming convention for anything added later: `FTFTest<Thing>`, query-string
 * values only, NEVER JSON — NSUserDefaults' argument-domain parser treats a
 * leading `{` as an old-style plist and the value never reaches the app
 * (observed live; see readTestRouteIntent's params note).
 */
export function testLaunchArg(name: string): string | null {
  if (!IS_TEST_BUILD) return null;
  if (Platform.OS !== 'ios') return null;
  let raw: unknown;
  try {
    raw = Settings.get(name);
  } catch {
    return null;
  }
  if (typeof raw !== 'string') return null;
  const v = raw.trim();
  return v ? v : null;
}
```

`readTestRouteIntent()` is refactored to call it for `ARG_ROUTE` (its first four lines
collapse into `const route = testLaunchArg(ARG_ROUTE); if (!route) return null;`) and
for `ARG_PARAMS`. Behaviour is identical — same gate, same platform check, same
try/catch, same blank handling.

**3. A signed-out entry allowlist:**

```ts
/**
 * Root-stack routes the harness may enter on a SIGNED-OUT boot. A set, not a
 * predicate: adding a second name later is a deliberate one-line decision,
 * not an accident. Every member MUST be a root-stack route — a signed-out
 * boot has no Main subtree, so tab-nested names are meaningless here.
 */
const SIGNED_OUT_ENTRY_ROUTES = new Set<string>(['LeagueJoin']);
```

and `applyTestRouteEntry` takes the auth state instead of the caller deciding:

```ts
export function applyTestRouteEntry(
  nav: { isReady: () => boolean; navigate: (...args: never[]) => void },
  opts: { authed: boolean },
): boolean {
  const intent = readTestRouteIntent();
  if (!intent) return false;
  if (!nav.isReady()) return false;
  // Signed out: only the allowlist, and always as a ROOT-stack route.
  if (!opts.authed) {
    if (!SIGNED_OUT_ENTRY_ROUTES.has(intent.route)) return false;
    try {
      (nav.navigate as unknown as (n: string, p?: object) => void)(
        intent.route, intent.params,
      );
    } catch {
      return false;
    }
    return true;
  }
  …unchanged authed body (TAB_OF / TAB_NAMES / root-stack)…
}
```

`opts` is **required**, not optional: there is exactly one call site, so a required
parameter costs nothing and makes "who decides the policy" un-guessable. The doc comment
at `:144-151` ("Callers must only invoke this once the authed tree is the live root
(RootNav gates on `initialRoute === 'Main'`)") is rewritten — that sentence describes the
policy that just moved into this function.

Until commit 12 registers `LeagueJoin`, the signed-out branch's `navigate` is a no-op
against an unregistered name (react-navigation warns; the `try/catch` and the `false`
return keep it inert). **That is why commit 6 is independently green.**

### 9.2 `SignInScreen.tsx` — substitute the SDK call, nothing else

Module scope, next to the existing imports:

```ts
import { testLaunchArg } from '../utils/testRouteEntry';

// Maestro seam (hld.md §5). `null` in every production bundle: testLaunchArg
// returns null unless the build-time `extra.testMode` constant is true, which
// only mobile/scripts/sim-build.sh produces. Read once at module load — the
// argument domain is volatile and cannot be set at runtime.
const TEST_APPLE_SUB = testLaunchArg('FTFTestAppleSub');
```

Inside `handleAppleSignIn` (`:136-142`), the **only** gated line:

```tsx
      // Everything AFTER this line — the account_only branch, setUser,
      // setLeague, onAccountSignedIn — is production code under test. Stubbing
      // further up (seeding useSession directly) would test the harness.
      const cred: {
        identityToken: string | null;
        fullName?: { givenName?: string | null; familyName?: string | null } | null;
      } = TEST_APPLE_SUB
        ? { identityToken: `ftf-test-apple:${TEST_APPLE_SUB}`, fullName: null }
        : await AppleAuthentication.signInAsync({
            requestedScopes: [
              AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
              AppleAuthentication.AppleAuthenticationScope.EMAIL,
            ],
          });
```

The explicit structural annotation is required for `tsc`: an object literal is not an
`AppleAuthenticationCredential`. The two downstream reads — `cred.identityToken` (`:143`)
and `cred.fullName?.givenName / familyName` (`:146-148`) — are satisfied by it, and no
other member of the credential is used.

Render gate — the Apple button is hidden when `isAvailableAsync()` is false, which it is
on a simulator without an iCloud account. One derived constant, used at **exactly two**
sites:

```tsx
  // Test builds show the Apple entry even when the simulator reports Apple
  // sign-in unavailable — the credential is substituted, so availability is
  // irrelevant. Identical to `appleAvailable` in production (TEST_APPLE_SUB
  // is null there).
  const appleShown = appleAvailable || TEST_APPLE_SUB !== null;
```

`{!landingOn && appleAvailable ? (` (`:381`) → `{!landingOn && appleShown ? (`, and
`{landingOn && appleAvailable ? (` (`:519`) → `{landingOn && appleShown ? (`. The four
*styling* reads of `appleAvailable` (`:474`, `:482`, `:484`, `:487`, which pick the
Sleeper button's primary/secondary treatment) are **left alone** — they are cosmetic, and
narrowing the edit to the two render gates keeps the production diff provably empty.

Under `release` flags `onboarding.landing` is `false`, so `:381` is the live path and
`signin.apple-btn` is the id the new flow taps.

### 9.3 `RootNav.tsx` — the call site

**Current** (`:336-344`, tail):

```tsx
        if (initialRoute === 'Main') applyTestRouteEntry(navigationRef);
```

**After:**

```tsx
        applyTestRouteEntry(navigationRef, { authed: initialRoute === 'Main' });
```

with the comment above it extended by: *"A signed-out boot is no longer a blanket
refusal — `testRouteEntry` owns the policy and allows only the names on its
`SIGNED_OUT_ENTRY_ROUTES` allowlist (P0-3's `LeagueJoin`). Behaviour for every existing
flow is unchanged."* Behaviour **is** byte-identical today: with the allowlist's one
member unregistered, a non-authed boot still enters nothing.

### 9.4 What the seam does not do (HLD §5.5)

It does not create an account-only seeder profile (the seam mints a *real* account-only
session through the production path); it does not cover the link→`Main` completion leg
(live ESPN/MFL egress, forbidden by the hermetic rails audit — **waiver W-2**, covered by
manual TestFlight); and it reads no pasteboard and asserts no SpringBoard alert.

---

## 10. Backend pytests specified here, built by W1-BE

**File: `backend/tests/test_account_only_harness.py` (new).** HLD §4 assigns the file to
`W1-BE` (commit 4) and HLD §10.5 forbids extending `test_account_first.py` — that file is
P0-5's stated must-stay-green-untouched contract. **W1-P05 writes no Python.** The four
cases below are P0-5's requirements on that file, with sketches precise enough to
implement without re-deriving them.

Harness to copy: `test_account_first.py`'s `client` fixture (in-memory SQLite, patched
`is_enabled`, `_fake_account_builder`, JWKS mock, `_post_apple` helper) and, for T-4,
`test_verified_sessions.py`'s `init_client` fixture (tiny universal pool, no Sleeper
network, `_SelectiveThread` inerting only the `session-init-bg-writes` daemon).

**T-1 — `test_apple_harness_token_401s_when_test_mode_unset`** *(the production gate,
asserted not assumed)*

```python
def test_apple_harness_token_401s_when_test_mode_unset(client):
    c, _, _ = client
    r = c.post("/api/auth/apple",
               data=json.dumps({"identity_token": "ftf-test-apple:qa-apple-p05"}),
               headers={"Content-Type": "application/json"})
    assert r.status_code == 401
    assert r.get_json()["error"] == "invalid_token"
```

No monkeypatching of any kind — the suite runs with `FTF_TEST_MODE` unset, which is the
condition under test. This is the test HLD §3 commit 4 calls out by name.

**T-2 — `test_apple_harness_token_mints_real_account_only_session_in_test_mode`**

`monkeypatch.setattr(server, "_TEST_MODE", True)` — **not** `monkeypatch.setenv`.
`_TEST_MODE` is a module constant evaluated once at import (`server.py:484`), so an env
change after import has no effect; W1-BE's `_test_mode_identity()` must read the module
constant for the same reason. Then `POST /api/auth/apple {"identity_token":
"ftf-test-apple:qa-apple-p05"}` → 200 with `account_only is True`,
`user_id == accounts.account_user_id(body["account_id"])`,
`league_id == server.ACCOUNT_NO_LEAGUE_ID`, `verified_via == "apple"`, and
`server._sessions[body["session_token"]]["verified"] is True`. This proves the seam runs
the **production** mint path (`_provider_auth_response` → `_mint_account_only_session`),
which is the whole justification for W-1.

**T-3 — `test_account_only_session_can_post_espn_link`** *(the claim the design rests
on)*

Follow `test_espn_link_route.py`: inject a session directly
(`{"user_id": "acct_<id>", "verified": True, "verified_via": "apple", …}`), patch
`espn_service.fetch_league` / `get_crosswalk` with that file's fixtures, flags
`{"espn.link", "auth.accounts"}` on. `POST /api/espn/link {"espn_league_id": "987654321"}`
with the session token → **not** 401 and **not** 403; the preview payload comes back.
What is being pinned is gate composition, not ESPN behaviour: `@_gate_unverified_write`
(`server.py:2392-2409`) passes because account-only sessions carry `verified=True`, and
`_require_session()` yields the `acct_` key as `user_id`. **No Sleeper identity is
required to link a league** — if that ever changes, this design's escape hatch closes and
this test is the alarm.

**T-4 — `test_session_init_reuses_token_and_preserves_verified_for_account_user`** *(the
latent 403)*

Using `init_client`, with the session's `user_id` an `acct_` key,
`_sess(token)["verified"] = True` / `["verified_via"] = "apple"` and
`accounts.mark_user_verified(acct_uid, "apple")`:

```python
    r = c.post("/api/session/init", headers=_h(token), data=_init_body(user_id=ACCT_UID))
    assert r.status_code == 200
    body = r.get_json()
    assert body["token"] == token                      # SAME token, not rotated
    v = body["verification"]
    assert v["session_verified"] is True
    assert v["user_verified"] is True and v["verified_via"] == "apple"
```

The behaviour under test is quoted in §7.3: `user_changed` is false for a same-`acct_`
re-init, so `token = incoming_token` and the `verified` pop is skipped. Without this,
the P2.5 read/write gates would 403 an account-only user out of their own board the
moment they linked their first league — a failure that would look like "ESPN linking is
broken" and be debugged nowhere near this code. `test_verified_sessions.py` already
covers the Sleeper-keyed carryover; the `acct_` case is untested today.

---

## 11. Maestro delta

Two new files, one asserted-unchanged control. Both new files carry `# flags: release`
(law 16 — a resolved fixture name under `backend/tests/fixtures/flags/`) and
`# profile: fresh`. All new ids are plain string literals, so `testid-lint.sh` finds them
by source grep and no `testid-lint-allow.txt` entry is needed (law 4).

**New testIDs:** `leagues.empty.body`, `leagues.empty.link-sleeper`,
`leagues.empty.link-espn`, `leagues.empty.link-mfl`, `leagues.empty.link-fleaflicker`.
(`leagues.empty.link-fleaflicker` is referenced by no flow — its flag is OFF in
`release` — but is registered in the docs row.)

### 11.1 `mobile/.maestro/flows/p0-5-account-only-picker.yaml`

```
appId: com.fantasytradefinder.app
# tc: TC-P05-01
# profile: fresh
# flags: release
tags: [p0, signin, leagues]
```

Header comment must state: the seam (`FTFTestAppleSub` → `ftf-test-apple:<sub>` →
`FTF_TEST_MODE` server branch), that everything after the credential substitution is
production code, and that leg 4 deliberately keeps `clearState: false` because
persistence is what it tests (law 6).

| Leg | Steps | Proves |
|---|---|---|
| 1. fresh Apple sign-in | `launchApp: {clearState: true, clearKeychain: true, stopApp: true, arguments: {FTFTestAppleSub: qa-apple-p05}}` → `extendedWaitUntil id: signin.apple-btn` (15 000) → `tapOn id: signin.apple-btn` | the account-only branch is entered through the real screen |
| 2. the acceptance criterion | `extendedWaitUntil id: leagues.empty.link-espn` (30 000) → `assertVisible` `leagues.empty.link-sleeper`, `leagues.empty.link-mfl`, `text: ".*Connect Sleeper, ESPN or MFL.*"` | **a brand-new Apple sign-in reaches a platform/league choice with no Settings visit** |
| 3. pinned from both sides | `assertNotVisible id: "leagues.row.*"` · `assertNotVisible text: ".*No 2026 NFL leagues found.*"` · `assertNotVisible text: ".*Couldn't reach Sleeper.*"` · `assertNotVisible id: tab.trades` · `takeScreenshot: p0-5-account-only-picker` | the state is the companion state, the false 503/empty copy is gone, and it did **not** route to `Main` |
| 4. relaunch | `launchApp: {clearState: false, stopApp: true}` → `extendedWaitUntil id: leagues.empty.link-espn` (30 000) → `assertNotVisible id: tab.trades` | design part (b) — the sentinel-aware predicate, i.e. the half a one-line routing fix misses |
| 5. link entry | `tapOn id: leagues.empty.link-mfl` → `extendedWaitUntil id: platform-link.input` | the reused `PlatformLinkSheet` actually opens from the new buttons |

Screenshot is taken immediately after the assertions, never after a
`waitForAnimationToEnd` near a spinner (law 5). No `openLink` anywhere (law 17). No tab
taps (law 8 is moot — the flow never touches the tab bar). Nothing is typed, so law 10
does not apply.

**Leg 5 stops at "sheet opened"** — completing an MFL import needs live MFL egress, which
the hermetic rails audit forbids and for which no fixture exists (**waiver W-2**).
Completion is manual TestFlight tests 11 and 14.

### 11.2 `mobile/.maestro/capture/leagues@account-only.yaml`

```
appId: com.fantasytradefinder.app
# tc: TC-CAP-LEAGUES-ACCOUNT-ONLY
# profile: fresh
# flags: release
# captures: account-only
# source: mobile/src/screens/LeaguePickerScreen.tsx
tags: [capture, leagues, fresh]
```

Same launch-argument entry as leg 1, one shutter: `takeScreenshot: leagues__account-only`
(the file's `<screen>@<variant>.yaml` name resolves the screen to `leagues`, and
`screen-capture.sh` files the frame at `screens/mobile/leagues/account-only.png`). Anchor
on `leagues.empty.link-espn` before the shutter, `waitForAnimationToEnd`, then shoot —
this screen's only animation is the arrival transition, not a spinner, so law 5 is
satisfied.

### 11.3 Controls that must pass **unmodified**

- `mobile/.maestro/capture/leagues@fresh.yaml` (HLD §6 row 13) — signs in as the
  Sleeper-keyed `qa_no_leagues` and asserts the literal *"No 2026 NFL leagues found for
  this account."* It is the proof the companion state did not leak into the
  non-account-only empty state. **Do not edit it.**
- `mobile/.maestro/flows/smoke/01-signin.yaml` and `02-league-pick.yaml` — the guard on
  change B (`initialRoute`).
- `mobile/.maestro/capture/settings.yaml` — the guard on the `LinkSleeperSheet`
  extraction (it anchors `settings.link-espn` and `settings.export-data`, both of which
  render below the extracted card).

---

## 12. Docs rows supplied to W3-DOCS

No build agent edits `docs/**` or `living-memory/**` (HLD §4 wave 3). P0-5 supplies:

| Doc | Row |
|---|---|
| `docs/cross-client-invariants.md` | **`no_league` is a cross-client constant.** Emitted by `backend/server.py` `ACCOUNT_NO_LEAGUE_ID` (with `ACCOUNT_NO_LEAGUE_NAME = "No league linked"`), consumed by `mobile/src/state/useSession.ts` `NO_LEAGUE_ID` and now **load-bearing in RootNav's routing predicate**. Documented nowhere today. |
| `docs/glossary.md` | **account-only session** — an Apple/Google identity with no bound Sleeper source; working key `acct_<account_id>`; sentinel league `no_league`; `verified_via='apple'`; `account_only` stays true after an ESPN/MFL link and is cleared only by linking a Sleeper username. |
| `docs/runbook.md` (mobile UI-test harness) | The `FTFTestAppleSub` launch argument + `ftf-test-apple:<sub>` token seam, naming **both** production gates explicitly (`FTF_TEST_MODE` unset in Render; `extra.testMode` false in every EAS bundle) and pointing at `backend/tests/test_account_only_harness.py::test_apple_harness_token_401s_when_test_mode_unset` as the standing assertion. |
| `living-memory/LLD.md` | (1) **Post-auth routing keys off the `no_league` sentinel, never off `user.account_only`.** (2) `LinkSleeperSheet` is the single owner of the Sleeper-identity-link form; Settings and LeaguePicker consume it and own their own post-link session mutations. |
| `living-memory/DECISIONS.md` | **D-029** (HLD §7 — *not* `D-011`; root `CLAUDE.md`'s next-id column is stale per HLD §10.4): sentinel-not-flag routing predicate, `LinkSleeperSheet` extraction, no new flag. Records the rejected non-dismissible-sheet-over-`Main` alternative. |
| `living-memory/GOTCHAS.md` | Candidate: `GET /api/sleeper/leagues/acct_<id>` proxies a synthetic id to Sleeper — 503 `sleeper_unavailable` under the VCR harness, `null` (→ "No 2026 NFL leagues found") live. An account-only session must never trigger the Sleeper league fetch. *(W3-DOCS allocates the id; HLD §7 assigns G-029…G-031 to other findings, so this one is additive or folded into the LLD.md row at W3-DOCS' discretion.)* |
| `screens/CLAUDE.md` | New `leagues@account-only` capture + frame. |
| `mobile/src/components/CLAUDE.md` | New `LinkSleeperSheet` row (form + sheet exports, the 409 Alert lives here, `settings.link-sleeper-input` is its input's id). New testID registry entries: the five `leagues.empty.*` ids. |
| `docs/api-reference.md` | **n/a** — no route added, renamed, removed or contract-changed. The `FTF_TEST_MODE` seam inside `/api/auth/apple` is harness-only and unreachable in any deployed build → runbook, not the public reference. |
| `docs/architecture.md` / `living-memory/HLD.md` | **n/a** — no module wiring or data-flow change. |
| `docs/data-dictionary.md` / `docs/config-reference.md` / `living-memory/DEPENDENCIES.md` | **n/a** — no schema, no flag, no dependency. |
| `living-memory/CHANGELOG.md` | At ship: account-only testers move from empty tabs to the league picker **at next launch** (retroactive by design — HLD §8 R10). |

---

## 13. Verification checklist for the build agent

Per commit: `python3 -m pytest backend/tests/ -q` · `cd mobile && npx tsc --noEmit` ·
`bash mobile/scripts/testid-lint.sh` (commit 7 adds ids and flows). **Never run
`npm install` — `mobile/node_modules` is a symlink.**

1. `grep -rn "account_only" mobile/src/navigation/RootNav.tsx` → **no hits.** The
   predicate keys off the sentinel (S-22).
2. `grep -rn "getLeagues(" mobile/src/screens/LeaguePickerScreen.tsx` → exactly one call
   site, guarded by `user.account_only ? [] :`.
3. `git diff` on `capture/leagues@fresh.yaml`, `flows/smoke/01-signin.yaml`,
   `flows/smoke/02-league-pick.yaml`, `capture/settings.yaml` → **empty**.
4. The `handleLinkSleeper` hunk in `LinkSleeperSheet.tsx` diffs against the deleted
   `SettingsScreen` region with **only** the four caller lines removed (§6.1).
5. `grep -rn "settings.link-sleeper-input" mobile/src` → exactly one hit, in
   `LinkSleeperSheet.tsx`.
6. `grep -rn "connectBody\|connectHelp\|connectInput" mobile/src/screens/SettingsScreen.tsx`
   → still present (three other cards use them).
7. `grep -rn "track(" mobile/src/screens/LeaguePickerScreen.tsx` → only the pre-existing
   `league_selected`. P0-5 adds **no** analytics event (the taxonomy is default-deny and
   commit 1 registers nothing for this finding).
8. `grep -rn "IS_TEST_BUILD\|testLaunchArg" mobile/src` → the definition plus exactly two
   consumers (`RootNav` indirectly via `applyTestRouteEntry`, `SignInScreen` directly).
9. Sim gate: **tier 1** (mobile screen + navigation) — full 11-flow smoke suite + the new
   flow, plus `screen-capture.sh --screen leagues` and `--screen settings`. Evidence into
   `TEST_LEDGER.md` + `qa/sim-runs/last-sim-run.json` (W3-QA runs it once for the batch).
10. Manual TestFlight legs that the hermetic harness structurally cannot cover: real
    Apple sign-in on a brand-new Apple ID → picker (no Settings visit); Connect ESPN →
    real link → `Main` with a writable board (proves §7.3 in the real world); relaunch
    before linking → picker; relaunch **after** linking → `Main` (this is the leg an
    `account_only` predicate would fail); Sleeper link from the picker → list repaints in
    place; **the 409 two-boards Alert from the picker entry point** (R8's only real
    exposure — both choices must work identically to Settings); Settings' ESPN and MFL
    rows for an account-only user → both land on the companion state, not a Sleeper
    error.

---

## 14. Deviations from the HLD

Three, all presentational. None touches a settled decision (S-19…S-22), the wave
partition, or §5's seam design.

**D-1 — `LinkSleeperSheet.tsx` exports a form *and* a sheet; Settings mounts the form.**
HLD §4 says Settings "replace[s] the inline form with `<LinkSleeperSheet>`". Settings'
surface today is an **inline `<Card>`, not a modal**; mounting a `<Modal>` there would
change a shipped screen's presentation inside an extraction commit and put
`capture/settings.yaml` at risk for no benefit — the opposite of R8's "move verbatim"
mitigation. The file path, the single-owner property, and the moved `testID` are exactly
as specified; only the element name in Settings differs (`<LinkSleeperForm>`). All logic
lives in the form, so there is still one owner of the 409 Alert.

**D-2 — the companion branch sits above `error` in the render ladder.** The HLD
specifies the state but not its ladder position. Rationale in §5.1: after the Sleeper
skip, a residual error on this branch is not actionable and its "Try again" retries
nothing the user needs.

**D-3 — invite copy is two sentences, not the HLD §1.3 em-dash clause.**
"`@matt` invited you to Lakeview Dynasty. **C**onnect Sleeper, ESPN or MFL to join."
instead of "… — **c**onnect Sleeper, ESPN or MFL to join." Maestro text matchers are
full-match regex (law 1) and case-sensitive; the capitalised form lets **one** matcher —
`".*Connect Sleeper, ESPN or MFL.*"` — assert both the generic and the invited variant,
so P0-3's flow and P0-5's flow can share it. The §1.3 wording is diagram prose; the
meaning is preserved exactly.
