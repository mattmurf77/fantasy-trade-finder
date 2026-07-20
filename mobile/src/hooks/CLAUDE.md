# mobile/src/hooks/

Custom React hooks. Currently:

- `usePushNotifications.ts` — registers Expo push token, wires foreground/background handlers; with flag `notif.tap_routing_v2` also consumes `useLastNotificationResponse` for cold-start taps (deduped vs. the live listener) and routes kinds via `utils/deepLinks.resolveNotificationTarget` (adds `bundle_summary`, passes `match_id`) — flag off = legacy inline kind sets exactly (teardown S5 PRD-02)
- `useScoringFormat.ts` — SF/1QB scoring format: league-driven default applier (`useLeagueFormatDefault`, mounted in RootNav) + explicit toggle hook (`useScoringFormat`, used by Tiers/Trios)
- `useRecoverOnResume.ts` — refetches an errored query once app-resume session revalidation mints a fresh token (zustand `hasToken` set) or on foreground resume; fixes queries that 401 during the revalidation race and would otherwise stick in error (staleTime: Infinity screens, e.g. Anchors — #121/#125)
- `useReducedMotionSafe.ts` — `useFlag('a11y.reduce_motion') && Reanimated useReducedMotion()`; flag off → always false (teardown S2 PRD-02)
- `useWhatsNew.ts` — flag `ux.whats_new`: version-keyed what's-new entry (Constants.expoConfig.version → in-file `WHATS_NEW` map), shown once per version (AsyncStorage `ftf_whats_new_seen_version`); anchor = ONE CoachMark-style inline tip in LeagueScreen, never a modal. Adding a release note = one map entry alongside the app.json version bump (teardown S7 PRD-04)
