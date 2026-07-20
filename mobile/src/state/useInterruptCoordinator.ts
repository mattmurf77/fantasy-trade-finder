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
// Priority (highest first): quickset prompt > coach mark > apple banner >
// outlook banner. There is NO preemption — a visible surface is never
// yanked mid-display; priority is realized by claim order (call
// `useInterruptSlot` in priority order within a screen) plus the ordering
// below for documentation and analytics.
//
// Root modals (PushPrimingModal, AppleSaveMomentSheet) are not surfaces —
// they self-defer while ANY surface holds the slot (read `activeSurface`
// directly), so a modal never presents over an open banner/prompt.
//
// Flag off: `useInterruptSlot` is a passthrough (returns `wants`, never
// claims, never tracks) — byte-identical behavior.

export type InterruptSurface =
  | 'quickset_prompt'
  | 'coach_mark'
  | 'apple_banner'
  | 'outlook_banner';

/** Lower number = higher priority. Exported for documentation/tests. */
export const SURFACE_PRIORITY: Record<InterruptSurface, number> = {
  quickset_prompt: 0,
  coach_mark: 1,
  apple_banner: 2,
  outlook_banner: 3,
};

interface CoordinatorState {
  activeSurface: InterruptSurface | null;
  /** Claim the slot. Returns true when granted (or already held by `id`). */
  claim: (id: InterruptSurface) => boolean;
  /** Release the slot iff held by `id`. */
  release: (id: InterruptSurface) => void;
}

export const useInterruptCoordinator = create<CoordinatorState>((set, get) => ({
  activeSurface: null,
  claim: (id) => {
    const cur = get().activeSurface;
    if (cur === id) return true;
    if (cur !== null) return false; // no preemption — defer
    set({ activeSurface: id });
    return true;
  },
  release: (id) => {
    if (get().activeSurface === id) set({ activeSurface: null });
  },
}));

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
  const wasGrantedRef = useRef(false);
  const deferTrackedRef = useRef(false);

  useEffect(() => {
    if (!arbiterOn) return;
    const store = useInterruptCoordinator.getState();
    if (wants) {
      const granted = store.claim(id);
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
  }, [arbiterOn, wants, id, active, screen]);

  // Release on unmount so a navigated-away surface can't wedge the slot.
  useEffect(
    () => () => {
      useInterruptCoordinator.getState().release(id);
    },
    [id],
  );

  return arbiterOn ? wants && active === id : wants;
}
