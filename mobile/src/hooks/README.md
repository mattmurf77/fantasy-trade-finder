# mobile/src/hooks/

Six cross-cutting React hooks. What each one does, and the non-obvious reasons behind them, is in [CLAUDE.md](CLAUDE.md) — read that first.

| File | One line |
|---|---|
| `usePushNotifications.ts` | Expo push token registration + foreground/background/cold-start tap routing |
| `useScoringFormat.ts` | SF/1QB format — league-driven default applier + explicit toggle |
| `useRecoverOnResume.ts` | Refetches a query that 401'd during session revalidation, or on foreground resume |
| `useReducedMotionSafe.ts` | Flag-gated Reanimated reduced-motion read (flag off ⇒ always false) |
| `useAppActive.ts` | `true` while `AppState === 'active'`; `'inactive'` counts as not active |
| `useWhatsNew.ts` | Version-keyed what's-new entry, shown once per app version |

## What belongs here

A hook used by **two or more screens**, or one that owns a subscription with a lifecycle (AppState, Expo notifications, Reanimated).

## What does not

- Screen-local hooks — keep those in the screen file.
- Anything that owns cross-screen *state*; that's a store in [`../state/`](../state/CLAUDE.md).
- Pure math — that's [`../utils/`](../utils/CLAUDE.md), where a `tests/check-*.js` guard can reach it.
- Network calls — that's [`../api/`](../api/CLAUDE.md).

## Adding one

Name it `useThing.ts`, export the hook as a named export, and add a bullet to [CLAUDE.md](CLAUDE.md) stating what it does *and* the sharp edge that justified it. If it is flag-gated, the flag-off path must be a clean passthrough — that pattern is why `useReducedMotionSafe` exists as its own file rather than an inline check.

`useLeagueFormatDefault` (from `useScoringFormat.ts`) is mounted in `RootNav`; hooks that must run app-wide go there, not in a screen.
