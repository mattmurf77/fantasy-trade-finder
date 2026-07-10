# mobile/src/hooks/

Custom React hooks. Currently:

- `usePushNotifications.ts` — registers Expo push token, wires foreground/background handlers
- `useScoringFormat.ts` — SF/1QB scoring format: league-driven default applier (`useLeagueFormatDefault`, mounted in RootNav) + explicit toggle hook (`useScoringFormat`, used by Tiers/Trios)
