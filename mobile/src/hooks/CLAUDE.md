# mobile/src/hooks/

Custom React hooks. Currently:

- `usePushNotifications.ts` — registers Expo push token, wires foreground/background handlers
- `useScoringFormat.ts` — SF/1QB scoring format: league-driven default applier (`useLeagueFormatDefault`, mounted in RootNav) + explicit toggle hook (`useScoringFormat`, used by Tiers/Trios)
- `useRecoverOnResume.ts` — refetches an errored query once app-resume session revalidation mints a fresh token (zustand `hasToken` set) or on foreground resume; fixes queries that 401 during the revalidation race and would otherwise stick in error (staleTime: Infinity screens, e.g. Anchors — #121/#125)
