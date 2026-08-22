import { create } from 'zustand';
import Constants from 'expo-constants';
import { onboardingEnabled } from './useFeatureFlags';
import {
  getOnboardingState,
  patchOnboardingState,
  resetGuideProgress,
  resetGuideProgressV2,
} from './useOnboardingState';
import { useInterruptCoordinator } from './useInterruptCoordinator';
import { measureGuideTarget, type TargetFrame } from './guideTargets';
import { track } from '../api/events';

// The Analyst guided tour — engine state (guided-avatar-script.md).
// Flag: onboarding.guided_avatar (master onboarding.v2 AND itself). When on,
// the tour SUPERSEDES the passive guided-layer surfaces (swipe hint, coach
// marks, prompt card, celebrations, diff banner) — screens gate those with
// !guidedAvatarActive(). Binding principles (script §1): never trap (every
// bubble dismissible, Skip tour is permanent), one bubble at a time, system
// modals win, talk steps advance on tap, action steps advance only on the
// real user action.
//
// ── Guided Onboarding v2 eligibility layer (flag onboarding.guide_v2) ──────
// PRD docs/plans/guided-onboarding-v2/PRD.md §5.0/§5.1. With guide_v2 ON,
// `requestStep` stops being "gate on `once` and hope" and evaluates a
// declarative eligibility contract carried on the step itself:
//
//   maxDisplayCount  hard lifetime display cap (persisted counts)
//   invalidateOn     receipt ids that permanently kill the step
//   retireAfter      {event, count} behavioral death, or justified 'never'
//   degrade          'suppress' → refuse rather than point at nothing
//   lifetimeMs       cta-step lifetime; expiry is a terminal transition
//
// Retirement reads CLIENT receipts only (`recordGuideReceipt`) — a condition
// wired to a server-fired event never fires and is worse than none.
// Every refusal is measured (`guide_step_suppressed`), the spotlight outcome
// rides on `guide_step_shown.spotlight`, and the step claims the interrupt
// arbiter's slot for its lifetime so no root modal opens over a bubble.
//
// With guide_v2 OFF every new field is inert and this engine is
// byte-identical to v1: no claim, no suppression event, no spotlight prop,
// no persisted counts/receipts, v1 `enableTour()` semantics.

export type GuidePose =
  | 'neutral' | 'point' | 'celebrate' | 'computing' | 'thinking' | 'oops';

export interface GuideCta {
  label: string;
  kind: 'primary' | 'ghost';
  action: 'accept' | 'dismiss';
}

/** Behavioral death condition (FR-E3). `'never'` is legal but the script
 *  lint requires a stated reason in a comment at the step. */
export type GuideRetirement = { event: string; count: number } | 'never';

/** Spotlight outcome for the active step — rides on `guide_step_shown`. */
export type GuideSpotlight = 'measured' | 'degraded' | 'none';

/** How a step ended. Every terminal transition invokes `onComplete` once. */
export type GuideCompletionVia =
  | 'advance'   // tap / real action / auto-advance
  | 'cta'       // in-bubble button
  | 'skip'      // "Skip the tour" (and the late degrade-suppress retraction)
  | 'x'         // per-step ✕
  | 'swipe'     // screen-owned swipe-away
  | 'timeout';  // `lifetimeMs` expiry

/** `guide_step_suppressed.blocked_by` — low-cardinality by contract. */
export type GuideBlockedBy =
  | 'guide_active'    // another bubble is on screen
  | 'slot_busy'       // another interrupt surface holds the arbiter slot
  | 'seen'            // once:true and already seen
  | 'display_cap'     // maxDisplayCount exhausted
  | 'invalidated'     // an invalidateOn receipt has fired
  | 'retired'         // retireAfter threshold reached
  | 'degrade'         // spotlight unmeasurable and degrade:'suppress'
  | 'v1_release_cap'  // v1 upgrader already spent this release's one v2 beat
  | 'matched';        // consumed by a call site (markGuideStepConsumed)

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

  // ── v2 eligibility contract (inert unless onboarding.guide_v2) ──────────
  /** FR-E3 — behavioral death: refuse once `count` receipts for `event`
   *  have been recorded, or `'never'` for a step that cannot outlive its
   *  trigger. Receipts come from `recordGuideReceipt` (client-observable
   *  only — never a server-fired event name). */
  retireAfter?: GuideRetirement;
  /** FR-E2 — lifetime display cap. Absent = no cap beyond `once`. */
  maxDisplayCount?: number;
  /** FR-E2 — receipt ids that permanently kill the step (first occurrence). */
  invalidateOn?: string[];
  /** FR-E3 — the downstream event this beat claims to cause. Declarative:
   *  read by the script lint and the analysis, not by the engine. */
  adoptionEvent?: string;
  /** FR-E6 — copy to render when the spotlight cannot be measured. */
  degradeLine?: string;
  /** FR-E6 — purely deictic lines set `'suppress'`: rather than point at
   *  nothing, the step refuses (and is measured as such). */
  degrade?: 'suppress';
  /** Auto-dismiss a `cta` step after this long. Expiry marks the step seen
   *  and reports `via: 'timeout'` (a terminal transition, not a skip). */
  lifetimeMs?: number;
}

export interface GuideHandlers {
  onAccept?: () => void;
  onDismiss?: () => void;
  /** Invoked exactly once on the step's terminal transition, whatever it
   *  was. Use this for chained beats instead of guessing from advance(). */
  onComplete?: (via: GuideCompletionVia) => void;
}

interface GuideStore {
  active: GuideStep | null;
  /** CTA callbacks for the ACTIVE step, supplied by the requesting screen. */
  onAccept: (() => void) | null;
  onDismissCta: (() => void) | null;
  onComplete: ((via: GuideCompletionVia) => void) | null;
  /** Spotlight outcome for the active step. `'pending'` only while the
   *  measure is in flight (guide_v2 only; v1 never leaves `'none'`). */
  spotlight: GuideSpotlight | 'pending';
  /** Measured target frame (guide_v2 only — v1's overlay measures itself). */
  spotlightFrame: TargetFrame | null;
  /** B1 — the target moved (host scrolled) and was re-measured: swap the
   *  frame ONLY. Never touches `spotlight`, never emits `guide_step_shown`;
   *  a re-measure is a new position, not a new outcome. */
  trackSpotlightFrame: (frame: TargetFrame) => void;
  stepsSeenCount: number;
  /** Gate + show. Returns true if the step became active. */
  requestStep: (step: GuideStep, handlers?: GuideHandlers) => boolean;
  /** Advance the active step (tap / real action / cta / auto). */
  advance: (via: 'tap' | 'action' | 'cta' | 'auto' | 'timeout') => void;
  /** ✕ on the bubble — skips this step only. */
  skipStep: () => void;
  /** Screen-owned dismissal of the active step: swiped away, or a cta
   *  step's `lifetimeMs` expiring. Both are terminal transitions. */
  dismissActiveStep: (via: 'swipe' | 'timeout') => void;
  /** "Skip tour" — permanent opt-out, falls back to passive surfaces. */
  dismissTour: () => void;
  /** #187 — Settings toggle re-enable. Full-replay semantics: clears the
   *  opt-out AND seen/completed memory so the tour restarts from its first
   *  step (a resume-only re-enable would be a silent no-op for users who
   *  had already seen every step — the toggle would look broken). With
   *  guide_v2 on, behaviorally-retired steps are exempt (FR-E10). */
  enableTour: () => void;
  /** S8 — tour completed; guide goes reactive-only. */
  completeTour: () => void;
  /** FR-E3 — record a client-observed receipt (the input to retireAfter /
   *  invalidateOn). Screens and emitters call this at the real moment. */
  recordGuideReceipt: (event: string) => void;
  /** A call site decided this step's teaching has already happened (e.g.
   *  the N6.1 matched branch): mark it seen + retired and measure the
   *  suppression, without ever showing a bubble. */
  markGuideStepConsumed: (id: string, blockedBy: GuideBlockedBy) => void;
  /** #384 — ids a running scripted tour owns. Registered by the tour runner
   *  (utils/calcTour.ts) on start and cleared on end. It is a REGISTRATION,
   *  not an import: calcTour imports this module, so this module must never
   *  import calcTour. Two consequences while a tour holds the floor:
   *  everything outside the set is refused silently, and the FR-E9 v1
   *  release cap does not apply to what is inside it (a walkthrough the
   *  user asked for is not release drip). */
  tourOwnedIds: ReadonlySet<string>;
  setTourOwnedIds: (ids: ReadonlySet<string>) => void;
}

/** True when the guided-avatar experience owns the onboarding surfaces. */
export function guidedAvatarActive(): boolean {
  return (
    onboardingEnabled('onboarding.guided_avatar') &&
    !getOnboardingState().guideDismissed
  );
}

/** True when the v2 eligibility layer is live. Every new behavior in this
 *  module hangs off this — off ⇒ byte-identical to v1. */
export function guideV2Active(): boolean {
  return onboardingEnabled('onboarding.guide_v2');
}

const GUIDE_SURFACE = 'guide_step' as const;

function appVersion(): string {
  return Constants.expoConfig?.version ?? 'unknown';
}

/** v2-new beats use `n`-prefixed script ids (PRD §5.3: N1, N2, N4, N6.1 …);
 *  retained v1 steps keep their `s` ids (FR-E9). A step may override. */
export function isV2NewStepId(id: string): boolean {
  return /^n\d/i.test(id);
}

/** FR-E9 — a device that finished the v1 tour before v2 shipped. Such users
 *  get at most one v2 beat per release and never the opening. */
export function isReturningV1User(): boolean {
  const ob = getOnboardingState();
  if (ob.guideScriptVersion < 2) return ob.guideTourCompleted;
  return ob.guideV1Upgrader;
}

/** First launch under guide_v2: stamp the script version and freeze the
 *  upgrader verdict. Never clears seen-state. */
function ensureScriptVersion(): void {
  const ob = getOnboardingState();
  if (ob.guideScriptVersion >= 2) return;
  patchOnboardingState({
    guideScriptVersion: 2,
    guideV1Upgrader: ob.guideTourCompleted,
  });
}

// ── Suppression episodes (FR-E5) ───────────────────────────────────────────
// `guide_step_suppressed` fires once per deferral EPISODE, not once per
// request: call sites re-request from effects that re-run on every render.
// An episode is (step id, reason); it closes when the step finally shows.
// Module scope, session-lifetime — the same shape `useInterruptSlot` uses
// for `prompt_deferred`.
const suppressionEpisodes = new Map<string, GuideBlockedBy>();

function noteSuppressed(
  stepId: string,
  blockedBy: GuideBlockedBy,
  screen?: string,
): void {
  if (!guideV2Active()) return;
  if (suppressionEpisodes.get(stepId) === blockedBy) return;
  suppressionEpisodes.set(stepId, blockedBy);
  track('guide_step_suppressed', { step: stepId, blocked_by: blockedBy }, screen);
}

function retireStep(id: string): void {
  patchOnboardingState({ guideRetired: { [id]: true } });
}

// ── Deferred `guide_step_shown` (FR-E6) ────────────────────────────────────
// The spotlight outcome is only known after `measureGuideTarget` resolves
// (≤250 ms), so a targeted step's `shown` emit waits for it. `token` guards
// against a step ending mid-measure; the emit is flushed on that terminal
// transition instead, so the event is deferred, never dropped.
let showToken = 0;
let pendingShow: { token: number; step: GuideStep } | null = null;

function commitShown(step: GuideStep, spotlight: GuideSpotlight): void {
  pendingShow = null;
  const ob = getOnboardingState();
  const patch: Parameters<typeof patchOnboardingState>[0] = {
    guideDisplayCounts: { [step.id]: (ob.guideDisplayCounts[step.id] ?? 0) + 1 },
  };
  // FR-E9 — a v1 upgrader spends their single v2 beat for this release.
  if (isReturningV1User() && isV2NewStepId(step.id)) {
    patch.guideV2BeatShownVersion = appVersion();
  }
  patchOnboardingState(patch);
  track(
    'guide_step_shown',
    { step: step.id, pose: step.pose, screen: step.screen, spotlight },
    step.screen,
  );
}

function flushPendingShow(): void {
  if (!pendingShow) return;
  // Ended before the measure came back — it was on screen, so report it,
  // with the honest "we never resolved a frame" value.
  commitShown(pendingShow.step, 'degraded');
}

export const useGuide = create<GuideStore>((set, get) => {
  const releaseSlot = (): void => {
    // No-op unless the guide holds it, so this is safe with the flag off.
    useInterruptCoordinator.getState().release(GUIDE_SURFACE);
  };

  /** Clear the active step and fire `onComplete` exactly once. */
  const terminate = (via: GuideCompletionVia): void => {
    const cb = get().onComplete;
    releaseSlot();
    set({
      active: null,
      onAccept: null,
      onDismissCta: null,
      onComplete: null,
      spotlight: 'none',
      spotlightFrame: null,
    });
    cb?.(via);
  };

  /** Resolve the spotlight for a just-activated targeted step (v2 only).
   *
   *  Timing note: v1 measured from the overlay's effect, i.e. one commit
   *  after the step activated. Measuring straight out of `requestStep`
   *  would be strictly earlier and would turn "the target mounts in the
   *  same commit" into a false degrade, so the first attempt is deferred to
   *  the next tick and a null gets one retry before we call it degraded. */
  const resolveSpotlight = (step: GuideStep, token: number, retriesLeft = 1): void => {
    measureGuideTarget(step.target as string).then((frame) => {
      const cur = get().active;
      if (!cur || cur.id !== step.id || pendingShow?.token !== token) return;
      if (!frame && retriesLeft > 0) {
        setTimeout(() => resolveSpotlight(step, token, retriesLeft - 1), 150);
        return;
      }
      if (frame) {
        set({ spotlight: 'measured', spotlightFrame: frame });
        commitShown(step, 'measured');
        return;
      }
      if (step.degrade === 'suppress') {
        // A purely deictic line with nothing to point at: retract rather
        // than ship the incoherence (§2.1's live `s7.1` is the exhibit).
        // The request already returned true, so `onComplete` still fires —
        // chained call sites must not stall on a step that never rendered.
        pendingShow = null;
        set({ stepsSeenCount: Math.max(0, get().stepsSeenCount - 1) });
        noteSuppressed(step.id, 'degrade', step.screen);
        terminate('skip');
        return;
      }
      set({ spotlight: 'degraded' });
      commitShown(step, 'degraded');
    });
  };

  return {
    active: null,
    onAccept: null,
    onDismissCta: null,
    onComplete: null,
    spotlight: 'none',
    spotlightFrame: null,
    stepsSeenCount: 0,
    tourOwnedIds: new Set<string>(),

    requestStep: (step, handlers) => {
      if (!guidedAvatarActive()) return false;
      // #384 review §20 — a scripted tour owns the floor for its whole run.
      // A beat that is not the tour's is refused with NO side effects: no
      // retirement, no suppression episode, no `seen` mark. The step was
      // never eligible-and-lost, it was asked at the wrong moment, and
      // recording it as blocked would spend a beat the user never saw.
      if (
        useInterruptCoordinator.getState().tourHold &&
        !get().tourOwnedIds.has(step.id)
      ) {
        return false;
      }
      const v2 = guideV2Active();
      const ob = getOnboardingState();
      if (step.once && ob.guideSeen[step.id]) {
        noteSuppressed(step.id, 'seen', step.screen);
        return false;
      }

      if (v2) {
        ensureScriptVersion();
        const obv = getOnboardingState();
        if (
          step.maxDisplayCount != null &&
          (obv.guideDisplayCounts[step.id] ?? 0) >= step.maxDisplayCount
        ) {
          retireStep(step.id);
          noteSuppressed(step.id, 'display_cap', step.screen);
          return false;
        }
        if (step.invalidateOn?.some((e) => (obv.guideReceipts[e] ?? 0) > 0)) {
          retireStep(step.id);
          noteSuppressed(step.id, 'invalidated', step.screen);
          return false;
        }
        if (
          step.retireAfter &&
          step.retireAfter !== 'never' &&
          (obv.guideReceipts[step.retireAfter.event] ?? 0) >= step.retireAfter.count
        ) {
          retireStep(step.id);
          noteSuppressed(step.id, 'retired', step.screen);
          return false;
        }
        // FR-E9's one-beat-per-release drip is for beats the app volunteers.
        // A tour beat is neither volunteered nor drip-fed: the user landed on
        // the page or tapped "Show me around", and a walkthrough that stops
        // after its first beat teaches nothing. Tour-owned ids are therefore
        // exempt — the display cap still bounds them.
        if (
          isReturningV1User() &&
          isV2NewStepId(step.id) &&
          !get().tourOwnedIds.has(step.id) &&
          obv.guideV2BeatShownVersion === appVersion()
        ) {
          noteSuppressed(step.id, 'v1_release_cap', step.screen);
          return false;
        }
      }

      // One bubble at a time — an active step is never preempted.
      if (get().active) {
        noteSuppressed(step.id, 'guide_active', step.screen);
        return false;
      }

      // FR-E4 mechanism (a): claim the arbiter slot synchronously, here,
      // which is what puts the guide ahead of every screen-level effect.
      if (v2 && !useInterruptCoordinator.getState().claim(GUIDE_SURFACE)) {
        noteSuppressed(step.id, 'slot_busy', step.screen);
        return false;
      }

      const targeted = v2 && !!step.target;
      set({
        active: step,
        onAccept: handlers?.onAccept ?? null,
        onDismissCta: handlers?.onDismiss ?? null,
        onComplete: handlers?.onComplete ?? null,
        spotlight: targeted ? 'pending' : 'none',
        spotlightFrame: null,
        stepsSeenCount: get().stepsSeenCount + 1,
      });
      suppressionEpisodes.delete(step.id);

      if (!v2) {
        track(
          'guide_step_shown',
          { step: step.id, pose: step.pose, screen: step.screen },
          step.screen,
        );
        return true;
      }
      if (targeted) {
        showToken += 1;
        pendingShow = { token: showToken, step };
        const t = showToken;
        setTimeout(() => resolveSpotlight(step, t), 0);
      } else {
        commitShown(step, 'none');
      }
      return true;
    },

    trackSpotlightFrame: (frame) => {
      // Only a step whose spotlight already RESOLVED can track: this must
      // never resolve the first frame (that is `resolveSpotlight`, which
      // owns the outcome and the deferred `guide_step_shown`) and never
      // rescue a degraded one.
      if (!get().active || get().spotlight !== 'measured') return;
      set({ spotlightFrame: frame });
    },

    advance: (via) => {
      const step = get().active;
      if (!step) return;
      flushPendingShow();
      if (step.once) {
        patchOnboardingState({ guideSeen: { [step.id]: true } });
      }
      track('guide_step_advanced', { step: step.id, via }, step.screen);
      terminate(via === 'cta' ? 'cta' : 'advance');
    },

    skipStep: () => {
      const step = get().active;
      if (!step) return;
      flushPendingShow();
      if (step.once) {
        patchOnboardingState({ guideSeen: { [step.id]: true } });
      }
      track('guide_step_skipped', { step: step.id }, step.screen);
      terminate('x');
    },

    dismissActiveStep: (via) => {
      const step = get().active;
      if (!step) return;
      flushPendingShow();
      // A timed-out beat is spent whether or not it was declared `once` —
      // re-teaching a line the user already ignored is the help-abuse case.
      if (step.once || via === 'timeout') {
        patchOnboardingState({ guideSeen: { [step.id]: true } });
      }
      if (via === 'timeout') {
        track('guide_step_advanced', { step: step.id, via: 'timeout' }, step.screen);
      } else {
        track('guide_step_skipped', { step: step.id }, step.screen);
      }
      terminate(via);
    },

    dismissTour: () => {
      const step = get().active;
      flushPendingShow();
      patchOnboardingState({ guideDismissed: true });
      track('guide_tour_dismissed', { at_step: step?.id ?? 'none' }, step?.screen);
      terminate('skip');
    },

    enableTour: () => {
      if (guideV2Active()) resetGuideProgressV2();
      else resetGuideProgress();
      suppressionEpisodes.clear();
      track('guide_tour_reenabled', {});
    },

    completeTour: () => {
      flushPendingShow();
      patchOnboardingState({ guideTourCompleted: true });
      track('guide_tour_completed', { steps_seen: get().stepsSeenCount });
      terminate('advance');
    },

    recordGuideReceipt: (event) => {
      if (!guideV2Active()) return;
      const cur = getOnboardingState().guideReceipts[event] ?? 0;
      patchOnboardingState({ guideReceipts: { [event]: cur + 1 } });
    },

    markGuideStepConsumed: (id, blockedBy) => {
      if (!guideV2Active()) return;
      patchOnboardingState({ guideSeen: { [id]: true }, guideRetired: { [id]: true } });
      noteSuppressed(id, blockedBy);
    },

    setTourOwnedIds: (ids) => set({ tourOwnedIds: ids }),
  };
});

/** Imperative helpers for non-component call sites. */
export function requestGuideStep(
  step: GuideStep,
  handlers?: GuideHandlers,
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

/** Screen-owned dismissal of whatever bubble is up (swipe-away, or a cta
 *  step's lifetime expiring). No-op when nothing is active. */
export function dismissActiveGuideStep(via: 'swipe' | 'timeout'): void {
  useGuide.getState().dismissActiveStep(via);
}

/** FR-E3 — record a client-observed receipt for retirement bookkeeping.
 *  Call this at the real moment (the save landed, the pin was recorded),
 *  NOT off a server-fired analytics event. */
export function recordGuideReceipt(event: string): void {
  useGuide.getState().recordGuideReceipt(event);
}

/** Consume a step without showing it — the teaching already happened by
 *  other means. Marks it seen + retired and measures the suppression. */
export function markGuideStepConsumed(id: string, blockedBy: GuideBlockedBy): void {
  useGuide.getState().markGuideStepConsumed(id, blockedBy);
}
