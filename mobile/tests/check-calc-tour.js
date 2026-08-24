#!/usr/bin/env node
// #384 W4 — the merged calculator tour: sequence, lifecycle, and the two
// entry points.
//
// The BEATS are already policed by check-guide-script.js (copy budget, the
// v2 eligibility contract, degrade honesty). This file covers what that one
// cannot see: the ORDER, the tour hold's lifecycle, and the property that
// every beat the runner names actually exists and is argument-free.
//
// Sections 39–41 were added from the 2026-08-22 device pass (build 1.16.0
// (126)), which found four beats pointing at nothing and a first-landing
// spotlight measured mid-transition. They pin: no #384 beat advances on a
// screen tap (report 6 — and a tap beat's full-screen catcher is what ate the
// deck's scroll, report 5); n11/n20/n23/n23b carry targets and those targets
// are registered by the file that owns the node (reports 2/4/5); the
// auto-start waits for `transitionEnd` (report 1); and both screens the tour
// runs on register a guide scroller under the exact screen name their beats
// declare.
//
// Run: node tests/check-calc-tour.js

'use strict';

const fs = require('fs');
const path = require('path');
const SRC = path.join(__dirname, '..', 'src');
let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}`); if (detail) console.log(`      ${detail}`); }
}
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const tour = read('utils/calcTour.ts');
const script = read('components/analystScript.ts');
const screen = read('screens/TradeCalculatorScreen.tsx');
const ilc = read('components/InLeagueCalculator.tsx');
const guide = read('state/useGuide.ts');

console.log('check-calc-tour:');

// ── 1: every beat the runner names exists, and takes no arguments ────────
const order = [...tour.matchAll(/'(n1\d|n2[0-4])'/g)].map((m) => m[1]);
const unique = [...new Set(order)];
// 13, not 15: W6-B (D-153) deleted n14 (Clear) and n17 (Include players) with
// the controls and the sequencing they existed for. Their BUILDERS are gone
// from analystScript.ts too, so a runner that named one would fail assertion 2
// rather than silently skipping a beat at runtime.
assert(unique.length === 13, '1. the runner names 13 beats', `found ${unique.length}: ${unique}`);
assert(!unique.includes('n14') && !unique.includes('n17'),
  '1a. the retired beats are not named anywhere in the runner',
  'n14 spotlights a Clear that is disabled on the empty canvas the tour now '
  + 'ends with; n17 spotlights a toggle that no longer exists');
assert(!/\bn14:|\bn17:/.test(script),
  '1b. …and their builders are deleted, not orphaned',
  'a builder no runner names is dead data the next reader has to disprove');
for (const id of unique) {
  // Builder present…
  const re = new RegExp(`\\n  ${id}: \\(([^)]*)\\): GuideStep =>`);
  const m = script.match(re);
  assert(!!m, `2. ${id} has a builder in the script`);
  // …and argument-free, which is what makes the runner's zero-arg call legal.
  if (m) assert(m[1].trim() === '', `3. ${id} takes no arguments`,
    `signature is (${m[1]}) — the runner calls it with none`);
}

// ── 4: the split matches the screens the beats declare ───────────────────
const calcList = tour.slice(tour.indexOf('CALC_TOUR_CALCULATOR'), tour.indexOf('CALC_TOUR_DECK'));
const deckList = tour.slice(tour.indexOf('export const CALC_TOUR_DECK'), tour.indexOf('CALC_TOUR_ORDER'));
for (const id of [...calcList.matchAll(/'(n\d+)'/g)].map((m) => m[1])) {
  const at = script.indexOf(`id: '${id}',`);
  assert(at >= 0 && /screen: 'TradeCalculator'/.test(script.slice(at, at + 120)),
    `4. ${id} is a calculator beat and declares screen TradeCalculator`,
    'a beat in the calculator list that declares another screen will spotlight nothing');
}
for (const id of [...deckList.matchAll(/'(n\d+)'/g)].map((m) => m[1])) {
  const at = script.indexOf(`id: '${id}',`);
  assert(at >= 0 && /screen: 'Trades'/.test(script.slice(at, at + 120)),
    `5. ${id} is a deck beat and declares screen Trades`);
}

// ── 6: lifecycle — the hold is taken once and released on EVERY exit ─────
assert(/beginTourHold\(\)/.test(tour), '6. the runner takes the tour hold');
{
  // endTour is the single release point, and start/stop/finish all route
  // through it. A second release path is how a hold leaks.
  const releases = (tour.match(/endTourHold\(\)/g) || []).length;
  assert(releases === 1, '7. exactly one release site (inside endTour)',
    `${releases} sites — a leaked hold mutes every interstitial app-wide`);
  const endBody = tour.slice(tour.indexOf('function endTour'), tour.indexOf('function requestAt'));
  assert(/running = false/.test(endBody) && /endTourHold\(\)/.test(endBody),
    '8. endTour clears the running flag AND releases the hold');
}
assert(/if \(shown\) \{\s*beatsShown \+= 1;\s*return;\s*\}\s*[\s\S]{0,200}?requestAt\(i \+ 1\);/.test(tour),
  '9. a refused beat steps over rather than stalling the tour',
  'a display-capped beat would silently end the run');
assert(/onComplete: \(via\) => onBeatComplete\(i, slot, via\)/.test(tour),
  '10. beats chain on the TERMINAL transition, not on advance alone');
assert(/i >= CALC_TOUR_ORDER\.length/.test(tour),
  '11. the runner terminates at the end of the list');

// ── 12: entry points ─────────────────────────────────────────────────────
assert(/startCalcTour\('auto'/.test(screen), '12. auto-start on landing exists');
assert(/startCalcTour\('show_me_around'/.test(screen), '13. re-entry from the link exists');
{
  const at = screen.indexOf("startCalcTour('auto'");
  const before = screen.slice(Math.max(0, at - 600), at);
  assert(/!calcMergedOn \|\| prefill \|\| !hasLeague/.test(before),
    '14. auto-start is gated on the merged flag, a prefilled arrival AND a league',
    'a deck hand-off must not be hijacked, and a league-less user has no In-league page to be carried to');
  const after = screen.slice(at, at + 1200);
  assert(/return \(\) => \{[\s\S]{0,240}?calcTourScreenBlurred\(\);/.test(after),
    '15. leaving the screen abandons the run — through the hand-off-aware exit',
    'an unconditional stop here kills the parked deck half, because Find a Trade unmounts this screen too');
  // …and the effect has to RE-RUN when its guards resolve. `hasLeague` is
  // false on the first render of a cold start (the session league hydrates
  // asynchronously) and `calcMergedOn` is false until the flags land, so an
  // empty dep array means the tour never starts for the users it is for —
  // and never re-evaluates when a prefilled arrival is replaced. Verified
  // green against the old assertions, which only looked for the call.
  // D-158 (Wave B0, 2026-08-24) — a FIFTH guard joined the four: with
  // `calc.inline_home` on the tour does not run on this screen at all (n10
  // points at the In-league tab this wave deletes), so `inlineHomeOn` is both
  // an early-return condition and a dep. Same rule as the others: a guard
  // that is not a dep is frozen at its first-render value.
  assert(/\}, \[calcMergedOn, prefill, hasLeague, inlineHomeOn, navigation\]\);/.test(after),
    '15a. the auto-start effect declares all its guards as deps',
    'deps `[]` freeze the guards at their first-render values — usually all false');
  // 2026-08-22 device feedback, report 1: "Box was in the wrong spot when I
  // first navigated to the page… after the tour, 'Show me around' worked."
  // `measureInWindow` is ABSOLUTE window coordinates, and a native-stack push
  // measures mid-slide. The auto-start must wait for a settled layout.
  const beforeStart = screen.slice(Math.max(0, at - 1000), at);
  assert(/addListener\('transitionEnd', begin\)/.test(beforeStart + after),
    "15b. the auto-start waits for the push transition to end",
    'starting from the bare mount effect measures the target mid-slide, and '
    + 'nothing re-measures afterwards — the first-landing spotlight lands wrong');
  // A TIMER fallback, never InteractionManager: runAfterInteractions fires the
  // moment no touch is in flight — before the push ends and before the native
  // header lays out — and the first beat measured ~44 pt high (2026-08-22).
  assert(/const fallback = setTimeout\(begin, \d+\)/.test(beforeStart + after)
      && !/runAfterInteractions/.test(beforeStart + after),
    '15c. …with a TIMER fallback (never InteractionManager) for a presentation that emits no transition',
    'a replace or a cold deep link onto this route fires no transitionEnd');
  assert(/if \(started\) return;/.test(beforeStart + after),
    '15d. …and whichever lands first starts the tour exactly once');
}
assert(/guidedAvatarActive\(\) && guideV2Active\(\)/.test(screen),
  '16. the "Show me around" handler needs guided-avatar AND guide_v2',
  'with guide_v2 off there are no spotlights, caps or degrade lines — every deictic beat points at nothing');
assert(/if \(!guidedAvatarActive\(\) \|\| !guideV2Active\(\)\) return false;/.test(tour),
  '16b. startCalcTour refuses on the same pair, so the link can never outrun the runner');

// ── 17: spotlight targets resolve to registered, attached refs ───────────
const TARGETS = [
  ['calc.mode-tab.league', screen],
  ['calc.trade-columns', ilc],
  ['calc.action.find-a-trade', ilc],
  ['calc.action.clear', ilc],
  ['calc.action.confirm', ilc],
  ['calc.league-give-add', ilc],
  // 2026-08-22 device feedback, report 2 — n11 opened the sheet and
  // highlighted nothing. The wrapper spans the receipt AND its fallback.
  ['calc.outlook-row', ilc],
];
for (const [id, src] of TARGETS) {
  // `\b` matters: without it `unregisterGuideTarget('x')` satisfies a check for
  // `registerGuideTarget('x')`, so deleting the registration reads as green.
  assert(new RegExp(`\\bregisterGuideTarget\\('${id.replace(/\./g, '\\.')}'`).test(src)
      || new RegExp(`'${id.replace(/\./g, '\\.')}', \\w+Ref`).test(src),
    `17. ${id} is registered as a guide target`,
    'a beat targeting an unregistered node degrades on every run');
}
// Every registered ref must be ATTACHED somewhere, or it measures null
// forever — the exact defect that got script step s7.1 cut.
for (const refName of ['columnsRef', 'findBtnRef', 'clearBtnRef', 'confirmBtnRef',
                       'giveAddRef', 'outlookRowRef']) {
  const uses = (ilc.match(new RegExp(`\\b${refName}\\b`, 'g')) || []).length;
  assert(uses >= 3, `18. ${refName} is declared, registered AND attached`,
    `only ${uses} references — an unattached ref measures null forever`);
}

// ── 19: every action beat has a real call site ───────────────────────────
//
// THE defect this file missed the first time. An `advance: 'action'` beat
// moves only when something calls `advanceGuideIfActive('<id>')`; tap-anywhere
// is off for it (AnalystGuide). With no call site the bubble sits there until
// the user ✕-es it, and the tour is over.
//
// W6-B (D-153): n16 is now a TAP beat and therefore has NO call site — the
// loop below only demands one of beats that declare `advance: 'action'`, so it
// follows the script rather than a hand-kept list. The complementary
// assertion is 19a: a tap beat must NOT be wired, because a stray
// `advanceGuideIfActive('n16')` would advance it on the very pick the reshape
// exists to stop requiring.
{
  const wired = new Set(
    [...(screen + ilc).matchAll(/advanceGuideIfActive\('(n\d+[a-z]?)'/g)].map((m) => m[1]),
  );
  for (const id of unique) {
    const at = script.indexOf(`id: '${id}',`);
    // ONE beat object: stop at its closing `}),` so a neighbour's `advance`
    // can never be read as this beat's.
    const end = script.indexOf('\n  }),', at);
    const body = script.slice(at, end);
    if (!/advance: 'action'/.test(body)) continue;
    assert(wired.has(id), `19. ${id} is an action beat and has an advanceGuideIfActive call site`,
      'an action beat with no call site can never advance — the tour stalls on it');
  }
  assert(!wired.has('n16'),
    '19a. n16 is a TAP beat and has NO advanceGuideIfActive call site',
    're-wiring it makes the beat demand a real pick, which is the canvas state '
    + 'the W6-B reshape exists to avoid — the tour must reach the MODELED deck');
}

// ── 20: the lifecycle properties the review found missing ────────────────
assert(/beats_shown: shown/.test(tour) && /beatsShown \+= 1/.test(tour),
  '20. beats_shown reports beats that actually rendered',
  'reading the cursor after endTour reset it is how this was always 0');
assert(/\} catch \{[\s\S]{0,400}?endTour\('abandoned'\)/.test(tour),
  '21. a throwing builder ends the tour instead of wedging running/tourHold',
  'a stuck hold mutes every interstitial app-wide for the rest of the session');
assert(/export function calcTourDeckArrived/.test(tour)
    && /requestAt\(CALC_TOUR_CALCULATOR\.length\)/.test(tour),
  '22. the runner parks after the calculator half and resumes on deck arrival');
assert(/DECK_ARRIVAL_TIMEOUT_MS/.test(tour) && /parkTimer = setTimeout/.test(tour),
  '23. the park is time-bounded — a deck that never arrives still releases the hold');
assert(/export function calcTourScreenBlurred/.test(tour)
    && /handingOffToDeck/.test(tour),
  '24. blur abandons the run, except when it is the Find-a-Trade hand-off');
assert(/addListener\('blur'/.test(screen) && /calcTourScreenBlurred\(\)/.test(screen),
  '25. the calculator screen actually subscribes to blur',
  'a push over this screen leaves it mounted — unmount alone never fires');
assert(/calcTourHandOffToDeck\(\)/.test(screen),
  '26. Find a Trade marks the hand-off so the blur handler parks instead of abandoning');
assert(!/stopCalcTour/.test(tour) && !/stopCalcTour/.test(screen),
  '26b. there is no unconditional stop for the calculator to reach for',
  'one existed and the unmount from Find a Trade used it, ending the tour before the deck half could start');
assert(/recordGuideReceipt\(GUIDE_RECEIPTS\.calcTourCompleted\)/.test(tour)
    && /if \(source === 'auto'\) \{[\s\S]*?guideReceipts\[GUIDE_RECEIPTS\.calcTourCompleted\][\s\S]*?return false;/.test(tour),
  '27. a finished run records the receipt, and the auto-start reads it',
  'without the gate the tour restarts on every landing');
assert(/resetTourDisplayCounts\(\)/.test(tour),
  '28. "Show me around" resets the per-beat display caps',
  'after three landings every beat is refused and the link does nothing');
{
  const start = tour.slice(tour.indexOf('export function startCalcTour'));
  // A stale bubble of ANY kind is torn down before the new run requests its
  // first beat: a tour-owned one is skipped (its cap already counted), any
  // other is dismissed like a swipe. Reproduced 2026-08-22: the deck's
  // s2.wait bubble followed the user onto the calculator and every beat of
  // the auto-tour was refused behind it.
  assert(/const stale = useGuide\.getState\(\)\.active;/.test(start)
      && /TOUR_IDS\.has\(stale\.id\)\) useGuide\.getState\(\)\.skipStep\(\)/.test(start)
      && /else useGuide\.getState\(\)\.dismissActiveStep\('swipe'\)/.test(start),
    '29. re-entry tears down WHATEVER bubble is standing (tour beat skipped, any other dismissed)',
    'one-bubble-at-a-time would otherwise refuse every beat of the new run');
  // "Show me around" RESTARTS. A re-entry that leaves `cursor` where the last
  // run stopped resumes mid-tour — and `requestAt(0)` below would then be the
  // only thing disagreeing with it, because `cursor` is what every subsequent
  // `requestAt(i + 1)` chains off. Dropping the reset was green before this.
  assert(/running = true;\s*\n\s*cursor = 0;\s*\n\s*beatsShown = 0;/.test(start),
    '29a. re-entry resets the cursor and the shown counter before requesting',
    'without `cursor = 0` the run resumes where the last one stopped, and '
    + 'beats_shown accumulates across runs');
  assert(/requestAt\(0\);/.test(start),
    '29b. …and the first request is the top of the list');
}
assert(/export function calcTourOwnsStep/.test(tour),
  '30. the runner exposes calcTourOwnsStep for callers outside the guide store');

// ── 31: the tour-owned mute is a REGISTRATION, not an import ─────────────
// useGuide must never import calcTour (calcTour imports useGuide), so the
// id set travels through the store.
assert(!/from '\.\.\/utils\/calcTour'/.test(guide),
  '31. useGuide does not import calcTour (that would be a cycle)');
assert(/setTourOwnedIds\(TOUR_IDS\)/.test(tour) && /setTourOwnedIds\(new Set<string>\(\)\)/.test(tour),
  '32. the runner registers its ids on start and clears them on end');
{
  const from = guide.indexOf('requestStep: (step, handlers) =>');
  const req = guide.slice(from, guide.indexOf('trackSpotlightFrame: (frame)', from));
  const gate = req.indexOf('tourHold');
  assert(gate >= 0 && gate < req.indexOf('noteSuppressed'),
    '33. the tour mute refuses BEFORE any side effect (no retire, no suppression episode)',
    'a beat refused during a tour was never eligible-and-lost — recording it spends a beat the user never saw');
}

// ── 34: no bubble outlives the run, and running ahead lands on the deck ───
{
  // The overlay is mounted once in RootNav: an abandoned beat would float
  // over whatever screen the user went to. endTour must take it down itself,
  // and must do so as a TEAR-DOWN — the terminal transition it fires is not
  // the user completing the beat.
  const endBody = tour.slice(tour.indexOf('function endTour'), tour.indexOf('function beatIdFor'));
  assert(/dismissActiveTourBubble\(\)/.test(endBody),
    '34. endTour dismisses a tour-owned bubble left standing',
    'an abandoned beat would float over the next screen until the user ✕ it');
  const dismissBody = tour.slice(
    tour.indexOf('function dismissActiveTourBubble'),
    tour.indexOf('function endTour'),
  );
  assert(/tearingDown = true/.test(dismissBody) && /dismissActiveStep\('swipe'\)/.test(dismissBody),
    '35. the tear-down is flagged so its terminal transition is not read as progress');
  assert(/if \(!running \|\| tearingDown\) return;/.test(tour),
    '36. onBeatComplete ignores the tear-down transition');
  // Find a Trade tapped BEFORE n18: the runner is not parked, the queued
  // calculator beats describe a page that is gone, and the bubble on screen
  // is over the deck. Arrival must drop it and run the deck half anyway.
  const arrive = tour.slice(
    tour.indexOf('export function calcTourDeckArrived'),
    tour.indexOf('export function calcTourHandOffToDeck'),
  );
  assert(/if \(!parked\) \{[\s\S]*?dismissActiveTourBubble\(\)/.test(arrive)
      && /cursor >= CALC_TOUR_CALCULATOR\.length\) return;/.test(arrive),
    '37. a run-ahead arrival drops the calculator bubble and starts the deck half',
    'otherwise the hold stays up with a calculator beat floating over the deck');
  // And "arrived" means a card is on screen, not merely that the route is
  // focused — n19 spotlights the top card's ✕.
  const trades = read('screens/TradesScreen.tsx');
  const arrival = trades.slice(trades.indexOf('const calcTourArrivalRef'), trades.indexOf('calcTourDeckArrived();') + 40);
  assert(/const hasTopCard = !!topCard;/.test(arrival) && /!hasTopCard \|\| !calcTourRunning\(\)/.test(arrival),
    '38. the deck announces arrival only once a top card exists',
    'announcing on focus alone makes n19 degrade against a ✕ that is not mounted yet');
}

// ── 39: the 2026-08-22 device pass ───────────────────────────────────────
//
// Six operator reports off build 1.16.0 (126). Four of them are properties of
// THIS tour rather than of the overlay, and none of them is visible to tsc:
//
//   report 6  every talk beat carries a Next/Done button. A tap beat also
//             mounts the overlay's full-screen catcher, which is what ate the
//             deck's scroll gesture (report 5) — so this one assertion covers
//             both. `advance: 'tap'` stays legal in the engine for older
//             beats; no #384 beat may use it.
//   report 2  n11 (outlook) had no target and highlighted nothing.
//   report 4  n20 (swap) had no target and the avatar pointed at nothing.
//   report 5  n23/n23b (send) had no target and the button was below the fold.
{
  const trades = read('screens/TradesScreen.tsx');
  const card = read('components/TradeCard.tsx');
  const bodyOf = (id) => {
    const at = script.indexOf(`id: '${id}',`);
    return at < 0 ? '' : script.slice(at, script.indexOf('\n  }),', at));
  };

  for (const id of [...unique, 'n23b']) {
    const body = bodyOf(id);
    assert(!/advance: 'tap'/.test(body),
      `39. ${id} does not advance on a screen tap`,
      "the operator asked for a Next button on every beat they are not expected "
      + 'to act on, and a tap beat mounts a full-screen catcher that swallows scroll');
    if (/advance: 'cta'/.test(body)) {
      assert(/ctas: \[(NEXT|DONE)\]|ctas: \[\{/.test(body),
        `39a. ${id} is a cta beat and declares its buttons`);
    }
  }
  assert(/ctas: \[DONE\]/.test(bodyOf('n24')),
    '39b. the closing beat says Done, not Next',
    'a "Next" on the last beat promises a beat that does not exist');

  // The four beats that shipped pointing at nothing now carry a target, and
  // the target is registered by the file that owns the node.
  const NEW_TARGETS = [
    ['n11', 'calc.outlook-row', ilc, 'InLeagueCalculator'],
    ['n20', 'trades.swap-first', card, 'TradeCard'],
    // Wave A (v2 note 17): n22 moved off `trades.fairness-help`, which lives
    // inside TradesScreen's `{!firstRun && …}` block and therefore never
    // mounts for the first-run decks the tour actually runs against.
    ['n22', 'trades.card-meter', card, 'TradeCard'],
    ['n23', 'trades.send-btn', trades, 'TradesScreen'],
    ['n23b', 'trades.send-btn', trades, 'TradesScreen'],
  ];
  for (const [id, target, src, owner] of NEW_TARGETS) {
    const body = bodyOf(id);
    assert(new RegExp(`target: '${target.replace(/\./g, '\\.')}'`).test(body),
      `40. ${id} targets ${target}`,
      'the device pass found this beat with an avatar and nothing highlighted');
    assert(/degradeLine:/.test(body),
      `40a. ${id} carries a degradeLine now that it has a spotlight to lose`);
    assert(new RegExp(`\\bregisterGuideTarget\\('${target.replace(/\./g, '\\.')}'`).test(src)
        || new RegExp(`'${target.replace(/\./g, '\\.')}', \\w+Ref`).test(src),
      `40b. ${target} is registered in ${owner}`,
      'a beat targeting an unregistered node degrades on every run');
  }
  // Both new registrations are SCOPED — an id claimed by more than one mounted
  // node measures whichever won the race. The deck's top card is the only card
  // given `disposition`, which is what makes the swap registration singular.
  assert(/swapFirstMounted = !!disposition/.test(card),
    '40c. trades.swap-first registers only on a card with a disposition',
    'every peek/match/featured card would otherwise claim the same id');
  assert(/cardMeterMounted = !!disposition/.test(card),
    '40d. trades.card-meter registers only on a card with a disposition',
    'the deck renders a peek card behind the top one; both would claim the id '
    + 'and the spotlight would ring whichever registration won');
  // …and it must NOT be registered while the bar is hidden: an id pointing at
  // an unmounted node measures null forever, which is the defect the retarget
  // exists to fix.
  assert(/cardMeterMounted = !!disposition && hasValueVerdict && !repricing/.test(card),
    '40e. …and only while the value bar is actually rendered',
    'the bar hides on a legacy card (no give/receive values) and mid-reprice; '
    + 'registering there re-creates the "bubble with no ring" bug one file over');
  // The beat n22 vacated stays wired for its OTHER consumers. Deleting it
  // would be a drive-by removal of a control's spotlight registration.
  assert(/registerGuideTarget\('trades\.fairness-help'/.test(trades),
    '40f. trades.fairness-help is still registered (n22 just no longer uses it)',
    'the retarget moves one beat; it does not retire the ⓘ');

  // Scroll-into-view needs a producer on both screens the tour runs on. The
  // key is the SCREEN NAME the beats declare, so a typo here is a silent
  // "no scroller registered" — which degrades to today's behaviour.
  assert(/registerGuideScroller\('TradeCalculator'/.test(screen),
    '41. the calculator registers a guide scroller under its own screen name');
  assert(/registerGuideScroller\('Trades'/.test(trades),
    '41a. the deck registers a guide scroller under its own screen name');
  for (const [src, name] of [[screen, 'TradeCalculator'], [trades, 'TradesScreen']]) {
    assert(new RegExp('unregisterGuideScroller\\(').test(src),
      `41b. ${name} unregisters its scroller on unmount`,
      'a stale handle points at an unmounted ScrollView for the rest of the session');
  }
  // The screen names the scrollers are keyed by must be the ones the beats
  // actually declare, or the lookup misses and nothing ever scrolls.
  for (const [id, key] of [['n11', 'TradeCalculator'], ['n23', 'Trades']]) {
    assert(new RegExp(`screen: '${key}'`).test(bodyOf(id)),
      `41c. ${id} declares screen ${key}, which is the scroller key`);
  }
}

// ── 41: a run that showed nothing is not a completed tour ─────────────────
assert(/if \(reason === 'finished' && shown > 0\)/.test(tour),
  '41. the first-visit receipt is recorded only when at least one beat was SHOWN',
  'a run refused beat-by-beat would otherwise retire the auto-start forever');
assert(/if \(m === 'league'\) advanceGuideIfActive\('n10', 'action'\);\s*if \(m === mode\) return;/.test(screen),
  '42. tapping the In-league tab advances n10 even when it is already selected',
  '"Show me around" is offered on the In-league tab; a re-run must get past its first beat');

// ── 43: the hold goes up BEFORE the stale bubble comes down ──────────────
{
  const start = tour.slice(tour.indexOf('export function startCalcTour'));
  const hold = start.indexOf('beginTourHold()');
  const own = start.indexOf('setTourOwnedIds(TOUR_IDS)');
  const tear = start.indexOf('const stale = useGuide.getState().active;');
  assert(hold >= 0 && own >= 0 && tear >= 0 && hold < tear && own < tear,
    '43. startCalcTour takes the hold and registers its ids BEFORE tearing down a stale bubble',
    'dismissing a screen beat lets that screen request its next beat synchronously; without the hold it takes the slot n10 needs');
}

// ── 44: an auto-start that cannot show n10 is not offered at all ──────────
// The runner steps over a refused beat, so with n10 at its display cap an
// auto-start opened on n12's degrade line with the page still on Real values.
{
  const start = tour.slice(tour.indexOf('export function startCalcTour'));
  const gate = start.indexOf("if (source === 'auto') {");
  const capCheck = /const first = GUIDE\.n10\(\);[\s\S]*?guideDisplayCounts\[first\.id\][\s\S]*?>= first\.maxDisplayCount[\s\S]*?return false;/;
  const run = start.indexOf('running = true;');
  const m = capCheck.exec(start);
  assert(gate >= 0 && m !== null && m.index > gate && m.index < run,
    '44. an auto-start refuses BEFORE taking the hold when n10 has hit its display cap',
    'a sequence that cannot show its first beat must not open on a later beat\'s degrade line');
  assert(/if \(source === 'show_me_around'\) resetTourDisplayCounts\(\);/.test(start),
    '44a. "Show me around" still resets the caps, so the explicit ask is unaffected by 44');
}

// ── 45: Wave A — the two mid-calculator parks ────────────────────────────
//
// Both fix a beat that "pops but highlights nothing" on build 128, and both
// are invisible to tsc and to every other suite here:
//
//   n10 → n11  the In-league content is still "Loading your league…" when the
//              tab tap advances n10, so `calc.outlook-row` does not exist and
//              the spotlight's single 150 ms retry loses the race. The runner
//              waits for the content to announce itself instead.
//   n11 → n12  n11's CTA opens an RN Modal AND advances the beat, and the
//              guide overlay is mounted below Modals, so n12 drew BEHIND the
//              sheet the user was still editing.
//
// Three properties per park, because each is a way the repair could be worse
// than the bug: the park exists at the right seam, it is TIME-BOUNDED (an
// unbounded park holds the interrupt hold and mutes every interstitial
// app-wide), and the resume is wired end to end — screen prop → runner export.
{
  const complete = tour.slice(
    tour.indexOf('function onBeatComplete'),
    tour.indexOf('export function calcTourInLeagueReady'),
  );
  assert(complete.length > 0, '45. the park block is where the assertions look');

  // ---- the In-league park (after n10) ----
  assert(/if \(slot === 'n10'\) \{[\s\S]{0,900}?inLeaguePark = \{ at: i \+ 1 \};/.test(complete),
    '45a. the runner parks after n10 instead of requesting n11 immediately',
    'requesting n11 in the same turn as the tab tap is the race itself');
  assert(/inLeagueParkTimer = setTimeout\([\s\S]{0,400}?endTour\('abandoned'\)[\s\S]{0,80}?IN_LEAGUE_READY_TIMEOUT_MS/.test(complete)
      && /const IN_LEAGUE_READY_TIMEOUT_MS = /.test(tour),
    '45b. …bounded, and expiry ENDS the tour rather than wedging the hold',
    'a park with no timer mutes every interstitial app-wide for the session');
  // LEVEL, not edge. The re-run case ("Show me around" on a page whose league
  // already loaded) has no announcement still to come; without this check the
  // park would burn its whole timeout and end a tour the user just asked for.
  assert(/if \(slot === 'n10'\) \{\s*if \(inLeagueReady\) \{\s*requestAt\(i \+ 1\);\s*return;\s*\}/.test(complete),
    '45c. …and an ALREADY-ready page proceeds immediately (level, not edge)',
    'the ready signal is a flag about state, not a one-shot event');
  assert(/export function calcTourInLeagueReady\(\): void \{\s*inLeagueReady = true;/.test(tour),
    '45d. the ready signal records the LEVEL before it looks for a waiter',
    'setting the flag only when parked makes the re-run case unreachable');
  // …and the level is cleared when the CONTENT unmounts — NOT on blur. A tab
  // switch blurs the screen while the In-league content stays mounted and
  // measurable; clearing there stranded the next re-run in a park whose
  // announcement had already been spent (review A1). The unmount clear lives
  // in `calcTourInLeagueGone`, fired by the component effect's cleanup.
  {
    const blur = tour.slice(
      tour.indexOf('export function calcTourScreenBlurred'),
      tour.indexOf('function resetTourDisplayCounts'),
    );
    assert(!/inLeagueReady = false;/.test(blur),
      '45e. blur does NOT clear the level (a tab switch leaves the content mounted)',
      'clearing on blur re-creates the A1 hang: re-run after a tab switch parks forever');
    assert(/export function calcTourInLeagueGone\(\): void \{\s*inLeagueReady = false;\s*\}/.test(tour),
      '45e-ii. the level is cleared by calcTourInLeagueGone, the unmount signal',
      'without an unmount clear, a stale true requests n11 against an unmounted target (A3)');
  }

  // ---- the outlook park (after n11) ----
  assert(/if \(slot === 'n11' && via === 'cta' && !!handlers\.openOutlook\) \{[\s\S]{0,200}?outlookPark = \{ at: i \+ 1 \};/.test(complete),
    '45f. the runner parks after n11 ONLY when the accept actually opened a sheet',
    'a ✕, a timeout or a host with no opener leaves no sheet to wait for — '
    + 'parking there would stall the tour until the timeout');
  assert(/outlookParkTimer = setTimeout\([\s\S]{0,300}?endTour\('abandoned'\)[\s\S]{0,80}?OUTLOOK_CLOSE_TIMEOUT_MS/.test(complete)
      && /const OUTLOOK_CLOSE_TIMEOUT_MS = /.test(tour),
    '45g. …bounded the same way, ending the run rather than holding the mute');
  {
    const m = /const OUTLOOK_CLOSE_TIMEOUT_MS = ([0-9_]+);/.exec(tour);
    assert(m !== null && Number(m[1].replace(/_/g, '')) >= 60_000,
      '45g-ii. the outlook bound gives a HUMAN editing time (>= 60 s)',
      'a 10 s bound ended the tour while the user was using the sheet n11 opened (review A2)');
  }
  assert(/export function calcTourOutlookClosed\(\): void \{\s*if \(!running \|\| !outlookPark\) return;/.test(tour),
    '45h. the close signal is a no-op when nothing parked for it',
    'the outlook sheet is reachable outside the tour too');

  // ---- both timers die with the run ----
  {
    const cp = tour.slice(tour.indexOf('function clearPark'), tour.indexOf('/** Take down the bubble'));
    assert(/inLeagueParkTimer\)/.test(cp) && /outlookParkTimer\)/.test(cp),
      '45i. clearPark clears BOTH new timers as well as the deck one',
      'a surviving timer ends a LATER run abandoned out of nowhere');
  }

  // ---- the wiring, end to end ----
  assert(/onInLeagueReady=\{calcTourInLeagueReady\}/.test(screen)
      && /onOutlookClosed=\{calcTourOutlookClosed\}/.test(screen),
    '45j. the calculator screen hands both signals to the runner',
    'an export nobody calls is a park that never resumes');
  assert(/onInLeagueReady\?\.\(\)/.test(ilc) && /onOutlookClosed\?\.\(\)/.test(ilc),
    '45k. …and InLeagueCalculator actually fires them');
  // The ready predicate must be the negation of the two early returns, or the
  // component announces readiness while still rendering the loading card.
  assert(/const inLeagueReady =\s*merged && !rostersQ\.isLoading && !coverageQ\.isLoading && opponents\.length > 0;/.test(ilc),
    '45l. "ready" means the loading and no-leaguemates returns are both past',
    'announcing on mount points the runner at a target that is not there yet');
  assert(/if \(rostersQ\.isLoading \|\| coverageQ\.isLoading\)/.test(ilc)
      && /if \(opponents\.length === 0\)/.test(ilc),
    '45m. …and those two early returns still read exactly those conditions',
    'if a return changes and the predicate does not, 45l is measuring nothing');
  // Rise announces, fall/unmount retracts — the effect's cleanup is the
  // retraction, so the pairing is structural: the same effect that calls
  // ready returns the cleanup that calls gone.
  assert(/if \(!inLeagueReady\) return;\s*onInLeagueReady\?\.\(\);\s*return \(\) => \{\s*onInLeagueGone\?\.\(\);\s*\};/.test(ilc),
    '45n. the ready effect announces on RISE and retracts via its own cleanup',
    'an announce without the paired retraction leaves the level stale after unmount (A1/A3)');
  assert(/onInLeagueGone=\{calcTourInLeagueGone\}/.test(screen),
    '45n-ii. the screen wires the retraction to the runner');
}

console.log(failures === 0
  ? 'check-calc-tour: all assertions passed'
  : `check-calc-tour: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
