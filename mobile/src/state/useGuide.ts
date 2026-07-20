import { create } from 'zustand';
import { onboardingEnabled } from './useFeatureFlags';
import { getOnboardingState, patchOnboardingState } from './useOnboardingState';
import { track } from '../api/events';

// The Analyst guided tour — engine state (guided-avatar-script.md).
// Flag: onboarding.guided_avatar (master onboarding.v2 AND itself). When on,
// the tour SUPERSEDES the passive guided-layer surfaces (swipe hint, coach
// marks, prompt card, celebrations, diff banner) — screens gate those with
// !guidedAvatarActive(). Binding principles (script §1): never trap (every
// bubble dismissible, Skip tour is permanent), one bubble at a time, system
// modals win, talk steps advance on tap, action steps advance only on the
// real user action.

export type GuidePose =
  | 'neutral' | 'point' | 'celebrate' | 'computing' | 'thinking' | 'oops';

export interface GuideCta {
  label: string;
  kind: 'primary' | 'ghost';
  action: 'accept' | 'dismiss';
}

export interface GuideStep {
  id: string;                       // script id, e.g. 's3.2'
  line: string;                     // resolved dialogue text
  pose: GuidePose;
  flip?: boolean;                   // mirror the pose (point left)
  /** testID of the spotlight target (resolved via guideTargets registry). */
  target?: string;
  /** 'tap' = tap-anywhere advances; 'action' = a real user action elsewhere
   *  advances (the wiring calls advance()); 'cta' = in-bubble buttons;
   *  'auto' = auto-advance after autoMs. */
  advance: 'tap' | 'action' | 'cta' | 'auto';
  autoMs?: number;
  ctas?: GuideCta[];
  /** Persist as seen-once (never re-shown) when advanced or skipped. */
  once?: boolean;
  /** Avatar side; default 'left'. Placement solver may override to avoid
   *  covering the target (script §2). */
  side?: 'left' | 'right';
  screen: string;                   // for the guide_step_shown event
}

interface GuideStore {
  active: GuideStep | null;
  /** CTA callbacks for the ACTIVE step, supplied by the requesting screen. */
  onAccept: (() => void) | null;
  onDismissCta: (() => void) | null;
  stepsSeenCount: number;
  /** Gate + show. Returns true if the step became active. */
  requestStep: (
    step: GuideStep,
    handlers?: { onAccept?: () => void; onDismiss?: () => void },
  ) => boolean;
  /** Advance the active step (tap / real action / cta / auto). */
  advance: (via: 'tap' | 'action' | 'cta' | 'auto' | 'timeout') => void;
  /** ✕ on the bubble — skips this step only. */
  skipStep: () => void;
  /** "Skip tour" — permanent opt-out, falls back to passive surfaces. */
  dismissTour: () => void;
  /** S8 — tour completed; guide goes reactive-only. */
  completeTour: () => void;
}

/** True when the guided-avatar experience owns the onboarding surfaces. */
export function guidedAvatarActive(): boolean {
  return (
    onboardingEnabled('onboarding.guided_avatar') &&
    !getOnboardingState().guideDismissed
  );
}

export const useGuide = create<GuideStore>((set, get) => ({
  active: null,
  onAccept: null,
  onDismissCta: null,
  stepsSeenCount: 0,

  requestStep: (step, handlers) => {
    if (!guidedAvatarActive()) return false;
    const ob = getOnboardingState();
    if (step.once && ob.guideSeen[step.id]) return false;
    // One bubble at a time — an active step is never preempted.
    if (get().active) return false;
    set({
      active: step,
      onAccept: handlers?.onAccept ?? null,
      onDismissCta: handlers?.onDismiss ?? null,
      stepsSeenCount: get().stepsSeenCount + 1,
    });
    track('guide_step_shown', { step: step.id, pose: step.pose, screen: step.screen }, step.screen);
    return true;
  },

  advance: (via) => {
    const step = get().active;
    if (!step) return;
    if (step.once) {
      patchOnboardingState({ guideSeen: { [step.id]: true } });
    }
    track('guide_step_advanced', { step: step.id, via }, step.screen);
    set({ active: null, onAccept: null, onDismissCta: null });
  },

  skipStep: () => {
    const step = get().active;
    if (!step) return;
    if (step.once) {
      patchOnboardingState({ guideSeen: { [step.id]: true } });
    }
    track('guide_step_skipped', { step: step.id }, step.screen);
    set({ active: null, onAccept: null, onDismissCta: null });
  },

  dismissTour: () => {
    const step = get().active;
    patchOnboardingState({ guideDismissed: true });
    track('guide_tour_dismissed', { at_step: step?.id ?? 'none' }, step?.screen);
    set({ active: null, onAccept: null, onDismissCta: null });
  },

  completeTour: () => {
    patchOnboardingState({ guideTourCompleted: true });
    track('guide_tour_completed', { steps_seen: get().stepsSeenCount });
    set({ active: null, onAccept: null, onDismissCta: null });
  },
}));

/** Imperative helpers for non-component call sites. */
export function requestGuideStep(
  step: GuideStep,
  handlers?: { onAccept?: () => void; onDismiss?: () => void },
): boolean {
  return useGuide.getState().requestStep(step, handlers);
}

export function advanceGuideIfActive(stepId: string, via: 'action' | 'cta' = 'action'): void {
  const s = useGuide.getState();
  if (s.active?.id === stepId) s.advance(via);
}

export function guideActiveStepId(): string | null {
  return useGuide.getState().active?.id ?? null;
}
