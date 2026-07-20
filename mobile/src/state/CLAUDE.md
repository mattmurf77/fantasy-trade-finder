# mobile/src/state/

Context-based state. Each file exports a hook + provider.

- `useSession.ts` — current Sleeper user / selected league
- `useFeatureFlags.ts` — flags fetched from `/api/flags`; onboarding.* features MUST be read via `useOnboardingFeature()` / `onboardingEnabled()` (master `onboarding.v2` AND individual flag)
- `useOnboardingState.ts` — persisted `ftf_onboarding_state` (first-run, prompt snooze, Apple ask policy, coach marks) — onboarding plan item 4 scaffold; teardown adds push-primer backoff fields (`pushPrimerDeclines`/`pushPrimerLastDeclineSession`, flag `ux.prompt_arbiter`) + `ratingPromptShownVersion` (flag `growth.rating_prompt`)
- `useInterruptCoordinator.ts` — teardown S4 PRD-04 (flag `ux.prompt_arbiter`): one-surface prompt arbiter — `useInterruptSlot(id, wants)` claims the single `activeSurface` slot (priority quickset prompt > coach mark > apple banner > outlook banner, no preemption); root modals (PushPrimingModal/AppleSaveMomentSheet) self-defer while any slot is claimed; flag off = passthrough
- `usePushPriming.ts` — push-primer coordination; with `ux.prompt_arbiter` on, "Maybe later" declines persist and re-prime only after 3+ sessions or a want-it moment (`wantItMoment()`, fired by MatchesScreen's first mutual match)
- `onboardingBus.ts` — session-scoped module mailbox: QuickSetTiers (onboarding mode) posts a pending deck-regen position; TradesScreen consumes it on focus (item 7 cross-stack handoff)
- `useNotifications.ts` — in-app notification inbox state

No Redux/Zustand — keep it Context until pain demands more.
- `useGuide.ts` — The Analyst guided-tour engine (flag `onboarding.guided_avatar`): one-bubble-at-a-time step store, `guidedAvatarActive()` gate (supersedes passive guided-layer surfaces), guide_* analytics
- `guideTargets.ts` — spotlight target registry: screens register views by testID, the overlay measures at show time (missing target → bubble-only, never a blank cutout)
