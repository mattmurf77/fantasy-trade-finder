// #384 W4 — the merged calculator's guided tour: ordering, the tour hold,
// and the two entry points.
//
// The BEATS are data (components/analystScript.ts, n10–n24). This file owns
// only the sequence and its lifecycle, so a copy edit never touches logic and
// a sequencing fix never touches copy.
//
// Two entry points, both operator-specified:
//   * auto-start the moment the user lands on the calculator page, because
//     the first beat is what carries them to the In-league version;
//   * re-entry from the "Show me around" link, top right — the tour is
//     re-runnable, not once-only.
//
// The hold (ruling 10) is taken for the WHOLE run, not per step. The prompt
// arbiter's slot frees between steps, and in that gap a waiting interstitial
// legitimately wins it — see state/useInterruptCoordinator.ts.

import { useGuide, guidedAvatarActive, type GuideStep } from '../state/useGuide';
import { useInterruptCoordinator } from '../state/useInterruptCoordinator';
import { S as GUIDE } from '../components/analystScript';
import { track } from '../api/events';

/** The walkthrough, in order. Split by the screen each beat belongs to: the
 *  first nine are the calculator, the rest run on the deck after Find a
 *  Trade. Ids only — the builders resolve at request time so a beat is never
 *  captured stale. */
export const CALC_TOUR_CALCULATOR = [
  'n10', 'n11', 'n12', 'n13', 'n14', 'n15', 'n16', 'n17', 'n18',
] as const;
export const CALC_TOUR_DECK = [
  'n19', 'n20', 'n21', 'n22', 'n23', 'n24',
] as const;
export const CALC_TOUR_ORDER = [...CALC_TOUR_CALCULATOR, ...CALC_TOUR_DECK] as const;

type BeatId = (typeof CALC_TOUR_ORDER)[number];

/** Module state: one tour at a time, app-wide. Deliberately not a store —
 *  nothing renders from it, and a re-render on every beat would be waste. */
let running = false;
let cursor = 0;

export function calcTourRunning(): boolean {
  return running;
}

function endTour(reason: 'finished' | 'abandoned'): void {
  if (!running) return;
  running = false;
  cursor = 0;
  // Releasing the hold is what un-mutes every deferred interstitial, so it
  // must happen on EVERY exit — finished, skipped, or navigated away from.
  useInterruptCoordinator.getState().endTourHold();
  track('calc_tour_ended', { reason, beats_shown: cursor }, 'TradeCalculator');
}

function requestAt(i: number): void {
  if (!running) return;
  if (i >= CALC_TOUR_ORDER.length) {
    endTour('finished');
    return;
  }
  cursor = i;
  const id = CALC_TOUR_ORDER[i] as BeatId;
  // The script table also holds builders that TAKE arguments (s2_wait, s3_2
  // …), so it is not assignable to a zero-arg record. Every #384 beat is
  // argument-free by construction — pinned by check-calc-tour.js — and this
  // narrows to that fact rather than widening the table's type.
  const build = (GUIDE as unknown as Record<string, undefined | (() => GuideStep)>)[id];
  if (!build) {
    // A beat was renamed or removed. Skip it rather than wedging the tour —
    // and never silently: a hole in the sequence is a script defect.
    track('calc_tour_beat_missing', { beat: id }, 'TradeCalculator');
    requestAt(i + 1);
    return;
  }
  const shown = useGuide.getState().requestStep(build(), {
    // Chain on the TERMINAL transition, whatever it was — advancing,
    // skipping and timing out all land here exactly once.
    onComplete: () => requestAt(i + 1),
  });
  // Refused (display cap, retirement, another bubble): step over it rather
  // than stalling. Without this a capped beat would end the tour silently.
  if (!shown) requestAt(i + 1);
}

/**
 * Start (or restart) the tour.
 *
 * Returns false when the guided experience is off — the caller should not
 * render a "Show me around" affordance it cannot honour.
 */
export function startCalcTour(source: 'auto' | 'show_me_around'): boolean {
  if (!guidedAvatarActive()) return false;
  // Re-entry restarts from the top: "Show me around" is a deliberate ask to
  // see the whole thing, not to resume wherever a previous run stopped.
  if (running) endTour('abandoned');
  running = true;
  cursor = 0;
  useInterruptCoordinator.getState().beginTourHold();
  track('calc_tour_started', { source }, 'TradeCalculator');
  requestAt(0);
  return true;
}

/** Abandon the tour — navigating away, or the screen unmounting. Safe to
 *  call when no tour is running. */
export function stopCalcTour(): void {
  endTour('abandoned');
}
