import { create } from 'zustand';
import { useFeatureFlags } from './useFeatureFlags';
import { getOnboardingState, patchOnboardingState } from './useOnboardingState';
import { track } from '../api/events';

// Tiny store coordinating the iOS "Allow notifications?" prompt.
// usePushNotifications flips `pending=true` when permission is still
// `undetermined` and the user has hit the trigger event (rankings unlocked
// → first match imminent). PushPrimingModal listens on `pending`, renders
// the in-app priming sheet, and on Accept calls the registered handler
// (which performs Notifications.requestPermissionsAsync + token register).
//
// Primer backoff (teardown S4 PRD-04, flag `ux.prompt_arbiter`): after a
// "Maybe later", the primer must NOT re-arm every session. Declines are
// persisted in the onboarding store (pushPrimerDeclines +
// pushPrimerLastDeclineSession); a suppressed request parks its handler in
// `deferredHandler` and re-primes only when either
//   • 3+ sessions have passed since the last decline, or
//   • a want-it moment fires (`wantItMoment()` — MatchesScreen calls it
//     when the user first sees a mutual match this session).
// Flag off → exact legacy behavior: request() always shows, dismiss()
// records nothing, wantItMoment() is a no-op.

const REPRIME_SESSION_GAP = 3;

function arbiterOn(): boolean {
  try {
    return useFeatureFlags.getState().flags['ux.prompt_arbiter'] === true;
  } catch {
    return false;
  }
}

interface PrimingState {
  pending: boolean;
  // Set by the hook so the modal's Accept tap can re-enter the registration
  // flow without us re-mounting the hook.
  acceptHandler: (() => Promise<void>) | null;
  // Backoff-suppressed handler, promotable by a want-it moment this session.
  deferredHandler: (() => Promise<void>) | null;

  request(handler: () => Promise<void>): void;
  /** A genuine want-it moment (first mutual match seen this session) —
   *  surface a backoff-suppressed primer now. No-op unless one is parked. */
  wantItMoment(): void;
  dismiss(): void;
  clear(): void;
}

export const usePushPriming = create<PrimingState>((set, get) => ({
  pending: false,
  acceptHandler: null,
  deferredHandler: null,

  request(handler) {
    if (arbiterOn()) {
      const ob = getOnboardingState();
      const inBackoff =
        ob.pushPrimerDeclines > 0 &&
        ob.sessionCount < ob.pushPrimerLastDeclineSession + REPRIME_SESSION_GAP;
      if (inBackoff) {
        // Park it — a want-it moment this session may still surface it.
        set({ deferredHandler: handler });
        return;
      }
      track('push_primer_shown', { trigger: 'session' });
    }
    set({ pending: true, acceptHandler: handler, deferredHandler: null });
  },
  wantItMoment() {
    if (!arbiterOn()) return;
    const { deferredHandler, pending } = get();
    if (!deferredHandler || pending) return;
    track('push_primer_shown', { trigger: 'want_it' });
    set({ pending: true, acceptHandler: deferredHandler, deferredHandler: null });
  },
  dismiss() {
    if (arbiterOn() && get().pending) {
      const ob = getOnboardingState();
      patchOnboardingState({
        pushPrimerDeclines: ob.pushPrimerDeclines + 1,
        pushPrimerLastDeclineSession: ob.sessionCount,
      });
      track('push_primer_dismissed', { declines: ob.pushPrimerDeclines + 1 });
    }
    set({ pending: false, acceptHandler: null, deferredHandler: null });
  },
  clear() {
    set({ pending: false, acceptHandler: null, deferredHandler: null });
  },
}));
