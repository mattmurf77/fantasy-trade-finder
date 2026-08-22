import { useEffect, useRef } from 'react';
import { create } from 'zustand';
import { useFlag } from './useFeatureFlags';
import { track } from '../api/events';

// Screen-level prompt arbiter (teardown S4 PRD-04, flag `ux.prompt_arbiter`).
//
// One instructional/promotional surface at a time, app-wide. Surfaces claim
// the single `activeSurface` slot before rendering; losers stay hidden and
// re-try when the slot frees (their trigger state persists, so they show at
// the next free moment — "defer to the next mount" per the PRD).
//
// Priority (highest first): guide step > quickset prompt > coach mark >
// apple banner > outlook banner. There is NO preemption — a visible surface
// is never yanked mid-display; priority is realized by claim order (call
// `useInterruptSlot` in priority order within a screen) plus the ordering
// below for documentation and analytics.
//
// `guide_step` is the one surface that does NOT go through
// `useInterruptSlot` (guided-onboarding-v2 PRD FR-E4, mechanism (a)):
// `useGuide.requestStep` claims it IMPERATIVELY and synchronously, which is
// what puts it ahead of every screen-level effect, and releases it on the
// step's terminal transition. It is therefore also the one surface whose
// claim does not depend on `ux.prompt_arbiter` — it is gated on
// `onboarding.guide_v2` instead, and with that flag off the guide never
// claims and this file behaves exactly as before.
//
// Root modals (PushPrimingModal, AppleSaveMomentSheet) are not surfaces —
// they self-defer while ANY surface holds the slot (read `activeSurface`
// directly), so a modal never presents over an open banner/prompt — and,
// via the guide's claim, never over an open guide bubble either.
//
// ── Tour hold (#384 ruling 10, 2026-08-22) ───────────────────────────────
//
// The slot above is per-SURFACE and frees the moment a surface releases it.
// A scripted tour is many steps with gaps between them, and in those gaps
// any waiting interstitial legitimately wins the free slot — which is
// exactly the interruption the operator asked to eliminate ("ensure no
// scripted tour interruptions by muting other interstitials or analyst
// prompts during the tour").
//
// So a tour takes a HOLD that spans the whole run, not a per-step claim.
// While the hold is up:
//   * every `useInterruptSlot` surface except `guide_step` is refused, and
//     the refusal is measured as `blocked_by: 'tour'` like any other;
//   * `isInterruptBusy()` reads true even between steps, so the root modals
//     that self-defer on it stay deferred across the gaps too.
//
// The hold is NOT the slot. `guide_step` still claims and releases normally
// inside it — the tour's own bubbles are the thing being protected, and
// leaving them on the ordinary path keeps their analytics unchanged.
//
// Flag off: `useInterruptSlot` is a passthrough (returns `wants`, never
// claims, never tracks) — byte-identical behavior. The tour hold rides the
// same flag, so `ux.prompt_arbiter` off means no hold either.

export type InterruptSurface =
  | 'guide_step'
  | 'quickset_prompt'
  | 'coach_mark'
  | 'apple_banner'
  | 'outlook_banner';

/** Lower number = higher priority. Exported for documentation/tests. */
export const SURFACE_PRIORITY: Record<InterruptSurface, number> = {
  guide_step: 0,
  quickset_prompt: 1,
  coach_mark: 2,
  apple_banner: 3,
  outlook_banner: 4,
};

interface CoordinatorState {
  activeSurface: InterruptSurface | null;
  /** #384 — a scripted tour is running; everything but `guide_step` waits. */
  tourHold: boolean;
  /** Claim the slot. Returns true when granted (or already held by `id`). */
  claim: (id: InterruptSurface) => boolean;
  /** Release the slot iff held by `id`. */
  release: (id: InterruptSurface) => void;
  /** Take/drop the tour-long hold. Idempotent — a re-entered tour that
   *  begins twice must not need two ends. */
  beginTourHold: () => void;
  endTourHold: () => void;
}

export const useInterruptCoordinator = create<CoordinatorState>((set, get) => ({
  activeSurface: null,
  tourHold: false,
  claim: (id) => {
    const cur = get().activeSurface;
    if (cur === id) return true;
    if (cur !== null) return false; // no preemption — defer
    // The tour's own bubbles still claim; nothing else may, even when the
    // slot itself is free between steps.
    if (get().tourHold && id !== 'guide_step') return false;
    set({ activeSurface: id });
    return true;
  },
  release: (id) => {
    if (get().activeSurface === id) set({ activeSurface: null });
  },
  beginTourHold: () => set({ tourHold: true }),
  endTourHold: () => set({ tourHold: false }),
}));

/** True while ANY interrupt surface is up, or a tour holds the floor.
 *
 *  The root modals (PushPrimingModal, AppleSaveMomentSheet) self-defer on
 *  this rather than on `activeSurface !== null` — otherwise a modal would
 *  slip through in the gap between two tour steps, which is precisely the
 *  interruption the hold exists to prevent. */
export function isInterruptBusy(s: CoordinatorState): boolean {
  return s.activeSurface !== null || s.tourHold;
}

/**
 * #384 ruling 10 — tour-only mute for surfaces that are NOT enrolled in
 * general arbitration.
 *
 * Several passive interstitials (the deck's diff banner, adaptation moment,
 * suppression note, prefs-changed strip) never claimed a slot: they are
 * in-flow notices rather than modal interrupts, and enrolling them now would
 * change shipped behaviour by making them defer to each other in ordinary
 * use — a much larger change than the operator asked for.
 *
 * This hook gives them exactly the asked-for behaviour and nothing else:
 * hidden while a scripted tour holds the floor, byte-identical otherwise.
 * It deliberately does NOT claim, so it cannot wedge the slot.
 */
export function useMutedDuringTour(): boolean {
  const arbiterOn = useFlag('ux.prompt_arbiter');
  const tourHold = useInterruptCoordinator((s) => s.tourHold);
  return arbiterOn && tourHold;
}

/**
 * Surface hook: `id` wants to show iff `wants`. Returns whether it may
 * render right now.
 *
 * - Flag `ux.prompt_arbiter` OFF → returns `wants` unchanged (passthrough).
 * - Flag ON → claims/releases the shared slot; instruments `prompt_shown`
 *   on grant and `prompt_deferred` (once per deferral episode) on loss.
 *
 * Call sites within one screen should be ordered highest-priority first —
 * effect execution order is how simultaneous claims resolve.
 */
export function useInterruptSlot(
  id: InterruptSurface,
  wants: boolean,
  screen?: string,
): boolean {
  const arbiterOn = useFlag('ux.prompt_arbiter');
  const active = useInterruptCoordinator((s) => s.activeSurface);
  const tourHold = useInterruptCoordinator((s) => s.tourHold);
  const wasGrantedRef = useRef(false);
  const deferTrackedRef = useRef(false);

  useEffect(() => {
    if (!arbiterOn) return;
    const store = useInterruptCoordinator.getState();
    if (wants) {
      const granted = store.claim(id);
      // A tour refusal is measured like any other deferral, with its own
      // low-cardinality reason so "the tour ate my prompt" is legible in
      // the funnel rather than looking like ordinary slot contention.
      if (!granted && store.tourHold && id !== 'guide_step') {
        if (!deferTrackedRef.current) {
          deferTrackedRef.current = true;
          track('prompt_deferred', { surface: id, blocked_by: 'tour' }, screen);
        }
        return;
      }
      if (granted) {
        if (!wasGrantedRef.current) {
          wasGrantedRef.current = true;
          track('prompt_shown', { surface: id }, screen);
        }
        deferTrackedRef.current = false;
      } else if (!deferTrackedRef.current) {
        deferTrackedRef.current = true;
        track(
          'prompt_deferred',
          { surface: id, blocked_by: store.activeSurface },
          screen,
        );
      }
    } else {
      wasGrantedRef.current = false;
      store.release(id);
    }
    // `active` in deps: when the slot frees, waiting surfaces re-claim.
    // `tourHold` too: when the tour ends, everything it muted re-tries.
  }, [arbiterOn, wants, id, active, tourHold, screen]);

  // Release on unmount so a navigated-away surface can't wedge the slot.
  useEffect(
    () => () => {
      useInterruptCoordinator.getState().release(id);
    },
    [id],
  );

  return arbiterOn ? wants && active === id && (!tourHold || id === 'guide_step') : wants;
}
