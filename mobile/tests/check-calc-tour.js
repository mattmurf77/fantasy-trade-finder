#!/usr/bin/env node
// #384 W4 — the merged calculator tour: sequence, lifecycle, and the two
// entry points.
//
// The BEATS are already policed by check-guide-script.js (copy budget, the
// v2 eligibility contract, degrade honesty). This file covers what that one
// cannot see: the ORDER, the tour hold's lifecycle, and the property that
// every beat the runner names actually exists and is argument-free.
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

console.log('check-calc-tour:');

// ── 1: every beat the runner names exists, and takes no arguments ────────
const order = [...tour.matchAll(/'(n1\d|n2[0-4])'/g)].map((m) => m[1]);
const unique = [...new Set(order)];
assert(unique.length === 15, '1. the runner names 15 beats', `found ${unique.length}: ${unique}`);
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
assert(/if \(!shown\) requestAt\(i \+ 1\)/.test(tour),
  '9. a refused beat steps over rather than stalling the tour',
  'a display-capped beat would silently end the run');
assert(/onComplete: \(\) => requestAt\(i \+ 1\)/.test(tour),
  '10. beats chain on the TERMINAL transition, not on advance alone');
assert(/i >= CALC_TOUR_ORDER\.length/.test(tour),
  '11. the runner terminates at the end of the list');

// ── 12: entry points ─────────────────────────────────────────────────────
assert(/startCalcTour\('auto'\)/.test(screen), '12. auto-start on landing exists');
assert(/startCalcTour\('show_me_around'\)/.test(screen), '13. re-entry from the link exists');
{
  const at = screen.indexOf("startCalcTour('auto')");
  const before = screen.slice(Math.max(0, at - 500), at);
  assert(/!calcMergedOn \|\| prefill/.test(before),
    '14. auto-start is gated on the merged flag AND skipped for a prefilled arrival',
    'a deck hand-off ("Edit in calculator") must not be hijacked by a tour');
  const after = screen.slice(at, at + 300);
  assert(/stopCalcTour\(\)/.test(after),
    '15. leaving the screen abandons the run',
    'otherwise the hold outlives the tour and mutes every interstitial app-wide');
}
assert(/guidedAvatarActive\(\) \?/.test(screen),
  '16. the "Show me around" handler is omitted when the guided experience is off',
  'the component renders no link without a handler — so it cannot render a dead one');

// ── 17: spotlight targets resolve to registered, attached refs ───────────
const TARGETS = [
  ['calc.mode-tab.league', screen],
  ['calc.trade-columns', ilc],
  ['calc.action.find-a-trade', ilc],
  ['calc.action.clear', ilc],
  ['calc.action.confirm', ilc],
  ['calc.action.include-players', ilc],
  ['calc.league-give-add', ilc],
];
for (const [id, src] of TARGETS) {
  assert(new RegExp(`registerGuideTarget\\('${id.replace(/\./g, '\\.')}'`).test(src)
      || new RegExp(`'${id.replace(/\./g, '\\.')}', \\w+Ref`).test(src),
    `17. ${id} is registered as a guide target`,
    'a beat targeting an unregistered node degrades on every run');
}
// Every registered ref must be ATTACHED somewhere, or it measures null
// forever — the exact defect that got script step s7.1 cut.
for (const refName of ['columnsRef', 'findBtnRef', 'clearBtnRef', 'confirmBtnRef', 'includeBtnRef', 'giveAddRef']) {
  const uses = (ilc.match(new RegExp(`\\b${refName}\\b`, 'g')) || []).length;
  assert(uses >= 3, `18. ${refName} is declared, registered AND attached`,
    `only ${uses} references — an unattached ref measures null forever`);
}

console.log(failures === 0
  ? 'check-calc-tour: all assertions passed'
  : `check-calc-tour: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
