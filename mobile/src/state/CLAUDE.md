# mobile/src/state/

Context-based state. Each file exports a hook + provider.

- `useSession.ts` — current Sleeper user / selected league
- `useFeatureFlags.ts` — flags fetched from `/api/flags`; onboarding.* features MUST be read via `useOnboardingFeature()` / `onboardingEnabled()` (master `onboarding.v2` AND individual flag)
- `useOnboardingState.ts` — persisted `ftf_onboarding_state` (first-run, prompt snooze, Apple ask policy, coach marks) — onboarding plan item 4 scaffold
- `onboardingBus.ts` — session-scoped module mailbox: QuickSetTiers (onboarding mode) posts a pending deck-regen position; TradesScreen consumes it on focus (item 7 cross-stack handoff)
- `useNotifications.ts` — in-app notification inbox state

No Redux/Zustand — keep it Context until pain demands more.
- `useGuide.ts` — The Analyst guided-tour engine (flag `onboarding.guided_avatar`): one-bubble-at-a-time step store, `guidedAvatarActive()` gate (supersedes passive guided-layer surfaces), guide_* analytics
- `guideTargets.ts` — spotlight target registry: screens register views by testID, the overlay measures at show time (missing target → bubble-only, never a blank cutout)
