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
  assert(/\}, \[calcMergedOn, prefill, hasLeague, navigation\]\);/.test(after),
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
  assert(/InteractionManager\.runAfterInteractions\(begin\)/.test(beforeStart + after),
    '15c. …with an InteractionManager fallback for a presentation that emits no transition',
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
    && /source === 'auto' &&/.test(tour),
  '27. a finished run records the receipt, and the auto-start reads it',
  'without the gate the tour restarts on every landing');
assert(/resetTourDisplayCounts\(\)/.test(tour),
  '28. "Show me around" resets the per-beat display caps',
  'after three landings every beat is refused and the link does nothing');
{
  const start = tour.slice(tour.indexOf('export function startCalcTour'));
  assert(/TOUR_IDS\.has\(stale\)\) useGuide\.getState\(\)\.skipStep\(\)/.test(start),
    '29. re-entry dismisses the bubble a previous run left standing',
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

console.log(failures === 0
  ? 'check-calc-tour: all assertions passed'
  : `check-calc-tour: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
