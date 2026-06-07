# REQ — INIT-01: Decouple splash from network boot legs

- **Initiative / Wave / Scope:** INIT-01 · Wave 1 · [M]
- **Source observations:** OBS-NET-03 (RICE-P 16.0), OBS-CACHE-02 (RICE-P 5.0)
- **Peak RICE-P:** 16.0

## Problem statement

The mobile app splash screen is gated on all four boot promises resolving — including two network calls (`fetchTierConfig` and `warmPlayerCache`) that the first screen does not need. On a cold Render dyno this causes the user to stare at a spinner for the full 30–60 s dyno wake plus an additional ~5 MB upstream Sleeper fetch, even though the local session restore that determines which screen to show (SignIn / LeaguePicker / Main) finishes in milliseconds.

## User stories

- As a dynasty manager, I want the app to show its first screen immediately after opening, so that I can act while the background warm-up completes rather than waiting at a blank spinner.
- As a dynasty manager returning after the dyno sleeps, I want to reach the SignIn or Main shell within local-IO time, so that cold-dyno wake latency does not block my first tap.
- As a developer, I want the splash-gate logic to encode only the local-state prerequisites for routing, so that future network regressions in boot legs cannot silently resurrect the splash stall.

## Functional requirements

- FR-1: `setBooted(true)` must fire only after `bootstrap()` (session/league token restore from AsyncStorage/SecureStore) and the cache-hydrate phase of `loadFlags()` (reading the stored flag map from AsyncStorage) have both resolved — and no later than that.
- FR-2: `fetchTierConfig()` must be launched as a detached fire-and-forget call (no `await`, wrapped in `.catch(() => {})`) so that it cannot delay `setBooted`.
- FR-3: `warmPlayerCache()` must be launched as a detached fire-and-forget call and must never be in the `Promise.all` that gates `setBooted`.
- FR-4: The network half of `loadFlags()` (the `revalidateFlags()` fetch against the backend) must be decoupled from the boot gate; it must run after `setBooted` fires, in the background.
- FR-5: `loadFlags()` must be refactored to expose two separate callables: `loadCachedFlags()` (synchronous-ish AsyncStorage hydrate only) used in the gating set, and `revalidateFlags()` (network fetch + store) used as a detached post-boot call.
- FR-6: `RootNav` routing logic must continue to depend only on `user`, `league`, and `hasToken` — all of which come from `bootstrap()` — and must not read any data produced by the detached legs before routing.
- FR-7: The push-priming gate (currently dependent on `['progress']` resolving at `RootNav.tsx:82–94`) must still fire correctly; it must not be moved ahead of `['progress']` resolving, but it must no longer block the boot gate.
- FR-8: Tier-band UI components that depend on `fetchTierConfig` data must continue to render correctly using the seeded fallback values (`App.tsx:35–42`) for the brief window between `setBooted` and the detached `fetchTierConfig` resolving.

## Acceptance criteria

- [ ] AC-1 — Given a warm dyno and the device has a valid stored session, when the app is cold-launched, then `setBooted` fires within 500 ms of JS context start (measured by a boot-time log timestamp).
- [ ] AC-2 — Given the network is blackholed (all outbound connections blocked), when the app is cold-launched, then the SignIn or Main shell renders and is interactive; the app does not show an infinite splash spinner.
- [ ] AC-3 — Given the network is blackholed, then tier-band-gated UI components render with seeded fallback values (no crash, no blank screen) and update when `fetchTierConfig` resolves after network is restored.
- [ ] AC-4 — Given a cold Render dyno (first request after sleep), when the app is launched, then the splash screen clears and routes to the correct screen without waiting for the dyno-wake + player-cache round-trip to complete.
- [ ] AC-5 — Given the boot gate has fired with cached flags, when `revalidateFlags()` resolves with updated feature-flag values, then flag-gated UI components update to the new values without requiring a restart.
- [ ] AC-6 — Given the user's push-priming state is eligibility-pending, when `['progress']` resolves after `setBooted`, then the push-priming gate fires exactly once (`RootNav.tsx:82–94`) and not before `['progress']` data is available.
- [ ] AC-7 — `App.tsx` contains no `await` on `fetchTierConfig()` or `warmPlayerCache()` in the boot sequence; both calls are preceded by `void` and followed by `.catch(() => {})`.
- [ ] AC-8 — The gating `Promise.all` in `App.tsx` contains exactly two callables: `bootstrap()` and `loadCachedFlags()`; nothing else.

## Related components

- `mobile/App.tsx:47–54` — the `Promise.all([...]).finally(setBooted)` to be split
- `mobile/App.tsx:35–42` — seeded tier-band fallback (invariant, must be preserved)
- `mobile/src/navigation/RootNav.tsx:96–102` — splash indicator gated on `!booted`
- `mobile/src/navigation/RootNav.tsx:108–112` — routing decision reading `user`/`league`/`hasToken`
- `mobile/src/navigation/RootNav.tsx:80` — `refetchOnWindowFocus: true` on `['progress']` (currently a no-op; not changed by this initiative)
- `mobile/src/navigation/RootNav.tsx:82–94` — push-priming gate; must still fire correctly
- `mobile/src/state/useSession.ts:96–113` — `bootstrap()` — local-only, safe to stay in gating set
- `mobile/src/state/useFeatureFlags.ts:27–55` — `loadFlags()` to be split into `loadCachedFlags()` + `revalidateFlags()`
- `mobile/src/api/rankings.ts` (`getTierConfig`) — called by `fetchTierConfig()`
- `mobile/src/api/sleeper.ts:47` — `warmPlayerCache()` — must become fully detached

## Prerequisite components / dependencies

None. This is a client-only change in `mobile/App.tsx` and `mobile/src/state/useFeatureFlags.ts`. Synergistic with INIT-02 (which reduces the cost of the detached `warmPlayerCache()` call) but does not depend on it.

## Non-functional requirements & invariants

- **Performance target:** `setBooted` fires within 500 ms on a warm dyno with a valid stored session; splash clears before any network call completes on a cold dyno.
- **Tier-band cross-client invariant:** tier-band consumers (`utils/tierBands` or equivalent) must tolerate the seeded fallback for the window before `fetchTierConfig` resolves. This is already the documented network-failure path (`App.tsx:35–42`); this initiative must not change the fallback values or the fallback behavior.
- **No ELO / K-factor / enum invariants touched:** this initiative is boot-sequencing only; no ranking math or data-layer changes.
- **Rollback:** the change is additive (splitting one function into two phases); reverting means re-merging `loadCachedFlags()` and `revalidateFlags()` back into `loadFlags()` and restoring the original `Promise.all`. No DB migration required.
- **Risk:** low. The seeded-fallback path already exists and is tested. The only new behavior is that the fallback is briefly visible on every launch (not just network failures); confirm this is acceptable in QA.

## Out of scope

- INIT-05 (wiring `focusManager`/`onlineManager`) — separate initiative; the dead `refetchOnWindowFocus: true` on `['progress']` (`RootNav.tsx:80`) is not fixed here.
- INIT-07 (persisted query cache) — `prefetchQuery` prewarming during the splash is a separate optimization.
- Any changes to the backend, `render.yaml`, or `build.sh`.
- Changing the seeded tier-band fallback values themselves.
- The web client or browser extension boot sequences.
