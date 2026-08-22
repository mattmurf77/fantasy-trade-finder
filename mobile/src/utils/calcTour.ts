// #384 W4/W5 — the merged calculator's guided tour: ordering, the tour hold,
// the deck hand-off, and the two entry points.
//
// The BEATS are data (components/analystScript.ts, n10–n24). This file owns
// only the sequence and its lifecycle, so a copy edit never touches logic and
// a sequencing fix never touches copy.
//
// Two entry points, both operator-specified:
//   * auto-start the moment the user lands on the calculator page, because
//     the first beat is what carries them to the In-league version — but
//     ONCE: a `calc_tour_completed` receipt retires the auto-start for good;
//   * re-entry from the "Show me around" link, top right — the tour is
//     re-runnable, not once-only, so that path resets the per-beat display
//     caps and clears any bubble a previous run left standing.
//
// The hold (ruling 10) is taken for the WHOLE run, not per step. The prompt
// arbiter's slot frees between steps, and in that gap a waiting interstitial
// legitimately wins it — see state/useInterruptCoordinator.ts. While it is
// up, `useGuide.requestStep` refuses every step this runner does not own,
// which is why the id set is REGISTERED into the guide store on start
// (useGuide must never import this module — it is the other way round).
//
// The run spans two screens. n10–n18 are the calculator; n19–n24 are the
// deck, and the deck cannot be narrated until it is actually on screen, so
// the runner PARKS after n18 and waits for `calcTourDeckArrived()`.

import {
  useGuide,
  guidedAvatarActive,
  guideV2Active,
  type GuideCompletionVia,
  type GuideStep,
} from '../state/useGuide';
import { useInterruptCoordinator } from '../state/useInterruptCoordinator';
import { useSession } from '../state/useSession';
import { getOnboardingState, patchOnboardingState } from '../state/useOnboardingState';
import { S as GUIDE, GUIDE_RECEIPTS } from '../components/analystScript';
import { resolveSendPlatform } from './tradeText';
import { track } from '../api/events';

/** The walkthrough, in order. Split by the screen each beat belongs to: the
 *  first seven are the calculator, the rest run on the deck after Find a
 *  Trade. Ids only — the builders resolve at request time so a beat is never
 *  captured stale.
 *
 *  W6-B (D-153) reshaped the calculator half to the operator's own ending:
 *  *"the tour mentions they can add players and we'll find trades with those
 *  players included, and then the user is pushed to find a trade with the calc
 *  empty. That way the tour ends with them in the modeled cards."*
 *
 *  Two beats left with it. **n17** narrated the Include-players toggle, which
 *  no longer exists. **n14** ("Clear wipes the canvas") was only ever in this
 *  list after n16 because Clear is disabled on an empty canvas and n16 used to
 *  be the beat that filled it — with n16 now a TALK beat that adds nothing, n14
 *  would spotlight a 40 %-opacity button, which is the same defect as pointing
 *  at nothing. Both builders were deleted from `analystScript.ts` rather than
 *  left orphaned. */
export const CALC_TOUR_CALCULATOR = [
  'n10', 'n11', 'n12', 'n13', 'n15', 'n16', 'n18',
] as const;
export const CALC_TOUR_DECK = [
  'n19', 'n20', 'n21', 'n22', 'n23', 'n24',
] as const;
export const CALC_TOUR_ORDER = [...CALC_TOUR_CALCULATOR, ...CALC_TOUR_DECK] as const;

type BeatId = (typeof CALC_TOUR_ORDER)[number];

/** Every step id the tour can put on screen. `n23b` is the off-Sleeper
 *  sibling of `n23` (see `beatIdFor`) — it never appears in the order, but
 *  it IS a tour-owned step, so it belongs in the registered set. */
const TOUR_IDS: ReadonlySet<string> = new Set<string>([...CALC_TOUR_ORDER, 'n23b']);

/** How long the runner waits on the deck after Find a Trade before giving
 *  up. Generous — a cold generation can take several seconds — but bounded,
 *  because the hold mutes every interstitial app-wide until it is released. */
const DECK_ARRIVAL_TIMEOUT_MS = 30_000;

/** Handlers the SCREEN owns and the runner cannot reach for itself. */
export interface CalcTourHandlers {
  /** n11's CTA: open the Trade DNA sheet so "Set outlook" sets an outlook. */
  openOutlook?: () => void;
}

// Module state: one tour at a time, app-wide. Deliberately not a store —
// nothing renders from it, and a re-render on every beat would be waste.
let running = false;
let cursor = 0;
/** Beats that actually reached the screen. `cursor` is a POSITION and is
 *  reset by endTour before it could be read, which is how `beats_shown`
 *  managed to be 0 on every event it ever fired. */
let beatsShown = 0;
let parked = false;
let parkTimer: ReturnType<typeof setTimeout> | null = null;
/** Set by the Find-a-Trade hand-off so the calculator's blur handler knows
 *  this particular departure is the tour continuing, not the tour ending. */
let handingOffToDeck = false;
/** True only while the runner itself is tearing down a bubble (an abandon,
 *  or a jump to the deck half): the terminal transition that tear-down fires
 *  must not be read as the user completing the beat. */
let tearingDown = false;
let handlers: CalcTourHandlers = {};

export function calcTourRunning(): boolean {
  return running;
}

/** True while a tour is running AND `id` is one of its beats. The guide
 *  store's mute reads its own registered set; this is the same fact for
 *  callers outside the store. */
export function calcTourOwnsStep(id: string): boolean {
  return running && TOUR_IDS.has(id);
}

function clearPark(): void {
  parked = false;
  if (parkTimer) {
    clearTimeout(parkTimer);
    parkTimer = null;
  }
}

/** Take down the bubble the run left standing, if it is one of ours. The
 *  overlay is mounted once in RootNav, so an abandoned beat would otherwise
 *  float over whatever screen the user went to until they ✕ it. */
function dismissActiveTourBubble(): void {
  const active = useGuide.getState().active;
  if (!active || !TOUR_IDS.has(active.id)) return;
  tearingDown = true;
  try {
    useGuide.getState().dismissActiveStep('swipe');
  } finally {
    tearingDown = false;
  }
}

function endTour(reason: 'finished' | 'abandoned'): void {
  if (!running) return;
  running = false;
  clearPark();
  handingOffToDeck = false;
  handlers = {};
  const shown = beatsShown;
  cursor = 0;
  beatsShown = 0;
  dismissActiveTourBubble();
  // Releasing the hold is what un-mutes every deferred interstitial, so it
  // must happen on EVERY exit — finished, skipped, or navigated away from.
  useInterruptCoordinator.getState().endTourHold();
  useGuide.getState().setTourOwnedIds(new Set<string>());
  // The first-visit gate. Only a completed run counts: an abandoned one
  // taught nothing, so re-offering it on the next landing is correct.
  // A run that reached the end of the list without SHOWING a beat (every
  // request refused) taught nothing and must not retire the auto-start.
  if (reason === 'finished' && shown > 0) {
    useGuide.getState().recordGuideReceipt(GUIDE_RECEIPTS.calcTourCompleted);
  }
  track('calc_tour_ended', { reason, beats_shown: shown }, 'TradeCalculator');
}

/** Which builder actually renders for a slot. Only `n23` varies: its
 *  "Passwords never leave your phone" sentence is true on Sleeper and false
 *  on MFL (password POSTed to /api/mfl/auth-link) and ESPN (espn_s2/SWID
 *  stored server-side), so off-Sleeper leagues get `n23b` instead. */
function beatIdFor(id: BeatId): string {
  if (id !== 'n23') return id;
  const s = useSession.getState();
  return resolveSendPlatform(s.league?.league_id, s.leagues) === 'sleeper' ? 'n23' : 'n23b';
}

function requestAt(i: number): void {
  if (!running) return;
  if (i >= CALC_TOUR_ORDER.length) {
    endTour('finished');
    return;
  }
  cursor = i;
  const slot = CALC_TOUR_ORDER[i] as BeatId;
  let shown = false;
  try {
    const id = beatIdFor(slot);
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
    shown = useGuide.getState().requestStep(build(), {
      // Every talk beat is a cta beat since the 2026-08-22 device pass, but
      // n11 is the only one whose button DOES something beyond advancing —
      // without a handler its "Set outlook" opens nothing. The guide's accept
      // path calls `onAccept?.()` and then advances either way, so passing
      // `undefined` for the Next/Done buttons is exactly right.
      onAccept: id === 'n11' ? handlers.openOutlook : undefined,
      // Chain on the TERMINAL transition, whatever it was — advancing,
      // skipping and timing out all land here exactly once.
      onComplete: (via) => onBeatComplete(i, slot, via),
    });
  } catch {
    // A throwing builder (or a store that throws mid-request) must never
    // leave `running` and the hold up: the hold would mute every
    // interstitial app-wide for the rest of the session.
    endTour('abandoned');
    return;
  }
  if (shown) {
    beatsShown += 1;
    return;
  }
  // Refused (display cap, retirement, another bubble): step over it rather
  // than stalling. Without this a capped beat would end the tour silently.
  requestAt(i + 1);
}

function onBeatComplete(i: number, slot: BeatId, via: GuideCompletionVia): void {
  if (!running || tearingDown) return;
  // n10 is the beat that carries the user into In-league mode, and it
  // advances ONLY from the real switch (`advanceGuideIfActive('n10')` in
  // switchMode). Any other terminal transition means the user ✕-ed it and is
  // still on Real values, where none of n12–n18's targets is mounted — so
  // end the run rather than narrate a page that is not there.
  //
  // `'cta'` counts as progress alongside `'advance'` (2026-08-22 device pass):
  // an in-bubble button is the user moving the tour on, not abandoning it, and
  // every talk beat now carries one. n10 itself has no button today, so this
  // arm is a guard against the abandon rule firing on a future one.
  if (slot === 'n10' && via !== 'advance' && via !== 'cta') {
    endTour('abandoned');
    return;
  }
  // n18 is the last calculator beat: "Now tap Find a Trade." The deck half
  // waits for the deck to say it has arrived.
  if (slot === 'n18') {
    parked = true;
    parkTimer = setTimeout(() => {
      parkTimer = null;
      // The deck never announced itself (generation failed, or the user went
      // somewhere else entirely). Ending releases the hold; leaving it parked
      // would mute the app for the rest of the session.
      endTour('abandoned');
    }, DECK_ARRIVAL_TIMEOUT_MS);
    return;
  }
  requestAt(i + 1);
}

/** The deck screen reached focus while a tour is parked — run the deck half.
 *  Called by TradesScreen on focus when `calcTourRunning()` is true. */
export function calcTourDeckArrived(): void {
  if (!running) return;
  if (!parked) {
    // Already narrating the deck (a refocus) — nothing to resume.
    if (cursor >= CALC_TOUR_CALCULATOR.length) return;
    // The user tapped Find a Trade before n18 asked them to. The beats
    // still queued describe a page that is gone, and the one on screen is
    // floating over the deck; drop it and pick up the deck half.
    dismissActiveTourBubble();
  }
  clearPark();
  handingOffToDeck = false;
  requestAt(CALC_TOUR_CALCULATOR.length);
}

/** The calculator is handing off to the deck (Find a Trade). Tells the blur
 *  handler below that this departure is the tour continuing. */
export function calcTourHandOffToDeck(): void {
  if (!running) return;
  handingOffToDeck = true;
}

/** The calculator screen went away — blurred, or unmounted. Unmount alone is
 *  not enough (a push over the calculator leaves it mounted, and a tour
 *  narrating a screen nobody is looking at holds the mute for nothing), and
 *  blur alone is not enough (the Find-a-Trade `popTo` unmounts it). Both
 *  route here, and the Find-a-Trade hand-off is the one departure that is
 *  the tour continuing rather than ending: the deck half is parked, waiting
 *  for `calcTourDeckArrived()`. */
export function calcTourScreenBlurred(): void {
  if (!running || handingOffToDeck) return;
  endTour('abandoned');
}

/** "Show me around" replays the whole thing, so the per-beat display caps
 *  that bound the AUTOMATIC offer must not bound the explicit ask.
 *  `patchOnboardingState` merges nested records, so zeroing each tour id is
 *  the reset — `resetGuideProgressV2`'s wholesale replace would also wipe
 *  every other beat's history, which this link has no business doing. */
function resetTourDisplayCounts(): void {
  const zeroed: Record<string, number> = {};
  for (const id of TOUR_IDS) zeroed[id] = 0;
  patchOnboardingState({ guideDisplayCounts: zeroed });
}

/**
 * Start (or restart) the tour.
 *
 * Returns false when the tour cannot be honoured — the caller should not
 * render a "Show me around" affordance that would do nothing.
 */
export function startCalcTour(
  source: 'auto' | 'show_me_around',
  tourHandlers: CalcTourHandlers = {},
): boolean {
  // Both flags, not one. With `onboarding.guide_v2` OFF the whole v2 layer is
  // inert: no spotlights (`targeted = v2 && !!step.target`), no degrade
  // lines, no display caps, and the guide never claims the arbiter slot. Every
  // deictic beat here ("This is your canvas", "Tap the meter…") would render
  // as a floating bubble pointing at nothing, which is exactly the
  // incoherence the degrade contract exists to prevent. So the tour does not
  // run, and its affordance does not render, without it.
  if (!guidedAvatarActive() || !guideV2Active()) return false;
  // First-visit gate: the auto-start is an offer, and an offer the user has
  // already taken all the way through is not re-made. "Show me around" is a
  // deliberate ask and ignores this.
  if (source === 'auto') {
    const ob = getOnboardingState();
    if ((ob.guideReceipts[GUIDE_RECEIPTS.calcTourCompleted] ?? 0) > 0) return false;
    // The offer is also bounded by n10's display cap — and it is n10's cap
    // that bounds it, not each beat's own. The runner steps over a refused
    // beat, so once n10 (and n11) had hit `maxDisplayCount` an auto-start
    // opened on n12's DEGRADE line with the page still on Real values
    // (simulator, 2026-08-22: "Both rosters sit side by side here…" in the
    // bottom band, no ring, nothing to tap). A tour is a sequence; a sequence
    // that cannot show its first beat is not offered. "Show me around" resets
    // the caps below, so the explicit ask is unaffected.
    const first = GUIDE.n10();
    if (
      first.maxDisplayCount != null &&
      (ob.guideDisplayCounts[first.id] ?? 0) >= first.maxDisplayCount
    ) {
      return false;
    }
  }
  // Re-entry restarts from the top: "Show me around" is a deliberate ask to
  // see the whole thing, not to resume wherever a previous run stopped.
  if (running) endTour('abandoned');
  // …and WHATEVER bubble is standing has to go. One bubble at a time is
  // `requestStep`'s first rule, so an active beat refuses every beat of the
  // new run — the runner steps over each refusal and ends a run in which
  // nothing was shown. Reproduced in the simulator 2026-08-22: the deck's
  // "Reading the league rosters…" beat followed the user onto the calculator
  // and the auto-tour died silently behind it. A non-tour bubble is not
  // skipped (that would spend its `once`); it is dismissed, the way a swipe
  // would — the scripted tour owns the floor for its run (ruling 10).
  if (source === 'show_me_around') resetTourDisplayCounts();
  handlers = tourHandlers;
  running = true;
  cursor = 0;
  beatsShown = 0;
  useGuide.getState().setTourOwnedIds(TOUR_IDS);
  useInterruptCoordinator.getState().beginTourHold();
  // Tear the stale bubble down only AFTER the hold is up and the tour's ids
  // are registered: dismissing a screen's beat lets that screen request its
  // NEXT beat synchronously from the terminal callback (the deck's s2.wait →
  // N2 did exactly this, simulator 2026-08-22), and with the hold already
  // held that request is refused as a non-tour beat instead of taking the
  // slot n10 is about to ask for.
  const stale = useGuide.getState().active;
  if (stale) {
    tearingDown = true;
    try {
      if (TOUR_IDS.has(stale.id)) useGuide.getState().skipStep();
      else useGuide.getState().dismissActiveStep('swipe');
    } finally {
      tearingDown = false;
    }
  }
  track('calc_tour_started', { source }, 'TradeCalculator');
  requestAt(0);
  return true;
}
