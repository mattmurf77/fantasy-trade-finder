# mobile/src/state/

Context-based state. Each file exports a hook + provider.

- `useSession.ts` — current Sleeper user / selected league
- `useFeatureFlags.ts` — flags fetched from `/api/flags`; onboarding.* features MUST be read via `useOnboardingFeature()` / `onboardingEnabled()` (master `onboarding.v2` AND individual flag)
- `useOnboardingState.ts` — persisted `ftf_onboarding_state` (first-run, prompt snooze, Apple ask policy, coach marks) — onboarding plan item 4 scaffold; teardown adds push-primer backoff fields (`pushPrimerDeclines`/`pushPrimerLastDeclineSession`, flag `ux.prompt_arbiter`) + `ratingPromptShownVersion` (flag `growth.rating_prompt`)
- `useInterruptCoordinator.ts` — teardown S4 PRD-04 (flag `ux.prompt_arbiter`): one-surface prompt arbiter — `useInterruptSlot(id, wants)` claims the single `activeSurface` slot (priority quickset prompt > coach mark > apple banner > outlook banner, no preemption); root modals (PushPrimingModal/AppleSaveMomentSheet) self-defer while any slot is claimed; flag off = passthrough
- `usePushPriming.ts` — push-primer coordination; with `ux.prompt_arbiter` on, "Maybe later" declines persist and re-prime only after 3+ sessions or a want-it moment (`wantItMoment()`, fired by MatchesScreen's first mutual match)
- `quicksetProgress.ts` — #244 per-position quick-tiers completion for Rank-tab launch routing: AsyncStorage cache of `/api/tiers/status` `saved` (format-tagged; hydrated in the App.tsx boot gate, refreshed fire-and-forget after `revalidateSession`) union'd with `useOnboardingState.quicksetCompletedPositions`; `nextQuicksetPosition()` = next unset position in QB→RB→WR→TE order (null = all done → TabNav defaults the Rank stack to Trios). Sync read, cache-optimistic — stale answers converge next launch, never a mid-session reroute
- `onboardingBus.ts` — session-scoped module mailbox: QuickSetTiers (onboarding mode) posts a pending deck-regen position; TradesScreen consumes it on focus (item 7 cross-stack handoff)
- `useNotifications.ts` — in-app notification inbox state
- `useFinderTargets.ts` — #156/#174 finder pin lists (zustand, like `useTradeQueue`): `pinnedGive`/`pinnedReceive` + the #174 `packageMode` toggle. Session-only, never persisted; self-clears on league switch via a `useSession` subscription (works with the deck screen unmounted). TradesScreen owns add/remove; the hub reads live counts

No Redux/Zustand — keep it Context until pain demands more.
- `useGuide.ts` — The Analyst guided-tour engine (flag `onboarding.guided_avatar`): one-bubble-at-a-time step store, `guidedAvatarActive()` gate (supersedes passive guided-layer surfaces), guide_* analytics; #187 adds `enableTour()` (Settings toggle re-enable — full-replay: clears `guideDismissed` + `guideSeen` + `guideTourCompleted` via `resetGuideProgress()` in useOnboardingState)
- `guideTargets.ts` — spotlight target registry: screens register views by testID, the overlay measures at show time (missing target → bubble-only, never a blank cutout)
