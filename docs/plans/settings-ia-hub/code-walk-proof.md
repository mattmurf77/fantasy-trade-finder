# Code-walk proof — Settings IA hub

> **Purpose:** the D-056 replacement for a simulator capture. Under D-056 (2026-08-15) there is no
> simulator and no Maestro run, so behavior that would once have been proven by a capture is proven
> here by a file:line-cited trace instead. Companion evidence: three structural checks
> (`mobile/tests/check-settings-*.js`) and the operator TestFlight checklist in
> [`plan.md`](plan.md) §9, which is **unrun**.
>
> **Date:** 2026-08-19 · **Branch:** `feat/settings-ia-hub` · **Base:** `origin/main` @ `ecdbcb3`

---

## Table of contents
- [What this proves and what it does not](#what-this-proves-and-what-it-does-not)
- [1. Destructive paths keep their confirmations](#1-destructive-paths-keep-their-confirmations)
- [2. Terminal stack operations still land where they did](#2-terminal-stack-operations-still-land-where-they-did)
- [3. The navigation hack is gone and Back now works](#3-the-navigation-hack-is-gone-and-back-now-works)
- [4. Nothing was lost in the split](#4-nothing-was-lost-in-the-split)
- [5. The hub fires no settings queries](#5-the-hub-fires-no-settings-queries)
- [6. What is NOT proven here](#6-what-is-not-proven-here)

---

## What this proves and what it does not

This is a static trace. It proves the code says what it should say. It does **not** prove the app
runs — nothing in this change has been executed on a device or a simulator. §6 is the honest list of
what remains unproven, and it is not short.

Method: every claim below was checked by extracting function bodies with **brace matching** (not a
fixed line window — an earlier fixed-window attempt bled into adjacent functions and produced false
drift reports) from `git show origin/main:mobile/src/screens/SettingsScreen.tsx` and from the new
modules, then comparing the extracted user-facing string literals.

---

## 1. Destructive paths keep their confirmations

The risk in splitting a 1,712-line screen is that a confirmation dialog quietly loses a step or a
sentence. Six functions carry destructive or data-rights copy. All six were extracted from both trees
and compared:

| Function | New home | Shared user-facing strings | Lost |
|---|---|---|---|
| `confirmDisconnectSleeper` | `sections/PlatformDisconnectSection.tsx:104` | 4 | none |
| `confirmDisconnectEspn` | `sections/PlatformDisconnectSection.tsx:141` | 5 | none |
| `confirmDisconnectMfl` | `sections/PlatformDisconnectSection.tsx:173` | 5 | none |
| `confirmDeleteAccount` | `sections/AccountDataSection.tsx:163` | 10 | none |
| `handleExportData` | `sections/AccountDataSection.tsx` | 3 | none¹ |
| `performDeleteAccount` | `sections/AccountDataSection.tsx` | 2 | none¹ |

¹ The comparison initially flagged these two as drift. It was an artifact of the extractor splitting
on the apostrophe inside `"Couldn't export your data — try again."`. Checked directly: `origin/main`
`SettingsScreen.tsx:488` and `:625` versus `AccountDataSection.tsx:135` and `:156` — byte-identical.
Recorded because a proof that hides its own false positives is not a proof.

**Delete account keeps both steps.** The shipped flow is a two-stage `Alert`: "Delete account?" →
Continue (destructive) → "Are you absolutely sure?" → "Delete everything" (destructive). Both stages,
both `style: 'destructive'` markers, and both cancel labels ("Cancel", "Keep my account") survive at
`AccountDataSection.tsx:163-192`. The full data-deletion sentence — rankings, comparison history,
trade activity, notifications, push tokens, stored Sleeper connection, and the leaguemate
anonymization clause — is present verbatim.

**Accessibility props on Delete account survive.** `accessibilityRole="button"`,
`accessibilityLabel="Delete account"`, and the destructive hint were added to satisfy audit finding
S8 PRD-02; they are carried on the row in `AccountDataSection.tsx`.

---

## 2. Terminal stack operations still land where they did

Three call sites end a session or rebase the stack. They cannot go through the shared `navigate`
prop, which is a plain `navigation.navigate`, so each is passed explicitly by the host page:

| Shipped call | Shipped site | Now |
|---|---|---|
| `navigation.replace('SignIn')` after `signOut()` | `SettingsScreen.tsx:1470` | `SignOutRow.onSignedOut` → `SettingsAccountScreen.tsx:62` |
| `navigation.replace('SignIn')` after delete | `SettingsScreen.tsx:616` | `AccountDataSection.onAccountDeleted` → `SettingsAccountScreen.tsx:66` |
| `navigation.replace('LeaguePicker')` after account-only link | `SettingsScreen.tsx:1338` | `AccountIdentitySection.onSleeperLinked` → `SettingsAccountScreen.tsx:60` |

`replace` rather than `navigate` is load-bearing in all three: it prevents Back from returning to a
Settings page belonging to a session that no longer exists. A grep for `navigation.replace` across
`mobile/src/screens/settings/` returns exactly these three call sites and no others.

**Operation order is preserved.** `performDeleteAccount` runs `deleteAccount()` → `signOut()` →
`onAccountDeleted()`, matching the shipped `deleteAccount()` → `signOut()` →
`navigation.replace('SignIn')`. The account is deleted server-side before the local session is torn
down; reversing these would sign the user out of the credentials the delete call needs.

---

## 3. The navigation hack is gone and Back now works

Shipped (`SettingsScreen.tsx:227` on `origin/main`; `:228` on this branch after the FeedbackFAB import shifted it):

```ts
const navigateFromSettings = (route: string, params?: object) => {
  if (settingsV2) { navigation.goBack?.(); navigation.navigate?.(route, params); }
  else { navigation.navigate?.(route, params); }
};
```

Now:

```ts
const navigateFromSettings = (route: string, params?: object) => {
  navigation.navigate?.(route, params);
};
```

The `goBack()`-first branch existed only because a modal cannot host a push without stranding the
user. On a pushed page it is actively wrong: it pops Settings off the stack, so Back from the
destination lands on the tabs rather than on Settings. Removing it is what makes plan §9 checklist
item 4 (Account → Verify account → SleeperConnect → Back returns to **Account**) true.

`settingsV2` remains referenced at four other sites, so no unused-variable fallout.

---

## 4. Nothing was lost in the split

Proven by `mobile/tests/check-settings-ia.js`, which encodes plan §4's migration map as two tables:
12 section modules → their owning page, and 34 rows → their owning module. It asserts no module is
orphaned (0 importers) or duplicated (2+), and that all 34 rows resolve to exactly one module — the
second layer catches a row deleted from *inside* a surviving module, which module-ownership alone
would miss.

**The checks were verified by mutation, not by reading.** Independently re-run at orchestration:

| Mutation | Result |
|---|---|
| `presentation: 'modal'` restored on the `Settings` route | FAIL, with the F5/F6 consequence named |
| `<SignOutRow>` / `<AccountDataSection>` render order swapped | FAIL on render order (import-order assertion alone passed — hence both layers) |
| `settings.espn-disconnect` renamed in `PlatformDisconnectSection` | FAIL, and correctly identified that the id still existed in the legacy screen |

The modal parse walks the TypeScript AST per `<Stack.Screen>` element rather than substring-matching
the file, and carries a self-test asserting `presentation: 'modal'` is still *detected* on
`FeedbackInbox` and `SleeperConnect` — so a broken walk fails loudly instead of passing forever.

---

## 5. The hub fires no settings queries

`SettingsHubScreen.tsx` contains no `useQuery`, no `useMutation`, no `useEffect`, and no direct API
call. Its only cache access is two non-reactive `useQueryClient().getQueryData()` reads
(`['notif-prefs']`, `['account']`), which return resident data or `undefined` and never trigger a
fetch or a subscription. Everything else is zustand (`useSession`), the flag store, and
`expo-constants`.

This is the fix for F4 **on the hub path only**. The flag-off flat list still carries the
full-screen `if (prefsQuery.isLoading || !local)` gate at `SettingsScreen.tsx:746`, unchanged — phase
0 created the section modules as new files and deliberately left the legacy screen alone. That gate
dies with the legacy branch in phase 4. An earlier commit message on this branch overstated this as
"the gate is gone"; it is corrected in the phase-1 commit message and here.

The hub does mount `FeedbackFAB`, which performs its own status refresh. That is an app-wide concern
present on every pushed screen, not a settings query — the claim is "no settings queries of its
own", and it is stated that way rather than as "no network".

---

## 6. What is NOT proven here

Everything in this document is static. None of the following has been executed:

- **That the app launches at all** with these routes registered. `tsc --noEmit` exits 0 and 59/59
  structural checks pass, but neither runs React Native.
- **That the pushed presentation looks right** — header height, back-chevron placement, safe-area
  insets at the top edge where the modal's card inset used to be.
- **The swipe-gesture change.** Testers dismiss Settings by swiping down today; a pushed page swipes
  right. This is the change most likely to generate complaints and it has zero evidence behind it.
- **That hub previews render and refresh** — that "2 of 3 on" is correct for a real prefs payload,
  and that returning from the Notifications page updates it.
- **That the honest-empty cases appear** rather than blank rows: "Not chosen yet" for an unset
  ranking preference, and the deliberately absent Trade values preview.
- **That deep links resolve.** The seven `settings/<slug>` paths are mapped and point at registered
  routes; no link has been opened.
- **Anything about the flag-on path in prod**, since `account.settings_hub` is default false and has
  never been flipped anywhere.

Every one of these is an item in plan §9's TestFlight checklist, which is the only runtime evidence
this change can get under D-056. **The checklist is unrun.** This branch should not be treated as
verified until an operator works it.
