# #187 — Users can dismiss/disable The Analyst avatar

**Status:** Built (this worktree, branch `teardown-remediation`). Backend untouched.

**Operator ask:** "Users should be able to dismiss/disable the avatar. This option should be presented on the avatar pop ups and from the settings menu."

## What existed already

`useGuide.ts` already had the permanent opt-out primitive: `dismissTour()` sets
`guideDismissed` in the persisted `ftf_onboarding_state`, and
`guidedAvatarActive()` respects it. The overlay (`AnalystGuide.tsx`) already
rendered a "Skip the tour" link on **every** bubble (never-trap principle), so
the popup-side opt-out existed — but under testID `guide.skip-tour`, with no
accessibility label/hint, and with no way to ever turn the guide back on.

## What changed

1. **Popup affordance** (`mobile/src/components/AnalystGuide.tsx`)
   - Permanent opt-out link renamed to testID **`guide.dismiss-tour`**
     (was `guide.skip-tour`; no Maestro flow referenced the old id — repo-wide
     grep — registry in `mobile/src/components/CLAUDE.md` updated).
   - Copy clarified: "Skip the tour — don't show again".
   - Accessibility: `accessibilityLabel="Turn off the guided tour"`,
     hint "Stops The Analyst from appearing. You can turn it back on in
     Settings." The per-step ✕ (`guide.step-x`, "Skip this step") is unchanged
     and remains distinct.

2. **Settings toggle** (`mobile/src/screens/SettingsScreen.tsx`)
   - New "Guided tour" section with a Switch row **"The Analyst"**, testID
     **`settings.guided-tour-toggle`** (Row got an optional `testID` prop,
     passed to the Switch; Row already pairs `accessibilityLabel`/`Hint` with
     the visible title/sub copy).
   - Rendered only when `onboarding.guided_avatar` is enabled (via
     `useOnboardingFeature`, per the onboarding-flag rule); value =
     `!guideDismissed` (reactive read from `useOnboardingState`).
   - Both directions work:
     - **Off** → `useGuide.getState().dismissTour()` — same code path as the
       bubble link, so it also clears any active bubble and fires the existing
       `guide_tour_dismissed` event.
     - **On** → new `useGuide.enableTour()` — fires `guide_tour_reenabled`.

## Re-enable semantics (decision)

**Full replay.** `enableTour()` calls the new
`resetGuideProgress()` (`mobile/src/state/useOnboardingState.ts`), which in one
persisted write sets `guideDismissed: false`, `guideSeen: {}` and
`guideTourCompleted: false` — the tour restarts from its first step on the
relevant screens.

Why not resume-only (clear `guideDismissed` alone)?
- `guideSeen` marks once-ever steps as permanently seen and
  `guideTourCompleted` puts the guide in reactive-only mode. For a user who
  dismissed late (or completed the tour), a resume-style re-enable would be a
  **silent no-op**: the toggle flips on and nothing ever appears — it reads as
  broken. The toggle's sub-copy says so explicitly: "Turning this on restarts
  the guided tour from the beginning."
- A dedicated reset function was required regardless: `patchOnboarding` merges
  nested `guideSeen` one level deep and can never *clear* keys.
- Note: `resetGuideProgress` intentionally does NOT touch the passive-layer
  state (`coachMarksShown`, `celebrationsShown`) — re-enabling the avatar tour
  doesn't replay unrelated one-time surfaces.

## Files

- `mobile/src/components/AnalystGuide.tsx` — dismiss affordance rename + a11y
- `mobile/src/state/useGuide.ts` — `enableTour()` + `guide_tour_reenabled`
- `mobile/src/state/useOnboardingState.ts` — `resetGuideProgress()`
- `mobile/src/screens/SettingsScreen.tsx` — Guided tour section + Row testID
- `mobile/src/components/CLAUDE.md`, `mobile/src/state/CLAUDE.md` — registry/docs

## Verification

- `cd mobile && npx tsc --noEmit` — clean.
- No backend change; backend suite still green (1089 passed, 1 skipped).
- Manual QA suggested: bubble link → guide gone everywhere → Settings toggle
  shows Off → flip On → tour restarts at S0/S1 surfaces.
