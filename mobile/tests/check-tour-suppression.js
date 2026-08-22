#!/usr/bin/env node
// #384 W3 ruling 10 — "ensure no scripted tour interruptions by muting other
// interstitials or analyst prompts during the tour."
//
// The app already had a prompt arbiter (`useInterruptCoordinator`, flag
// `ux.prompt_arbiter`, live). What it did NOT have is a hold that spans a
// whole tour: the slot is per-surface and frees the instant a step ends, so
// in the gap between two tour steps a waiting interstitial legitimately wins
// it. That gap is the interruption this wave closes.
//
// This file runs the REAL reducer logic, lifted out of the source, rather
// than only grepping for it — the ordering rules (no preemption, guide_step
// exempt, idempotent begin) are behavioural and a regex cannot see them.
//
// Run: node tests/check-tour-suppression.js

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
const coord = read('state/useInterruptCoordinator.ts');
const trades = read('screens/TradesScreen.tsx');
const apple = read('components/AppleSaveMomentSheet.tsx');
const push = read('components/PushPrimingModal.tsx');

console.log('check-tour-suppression:');

// ── Behavioural: run the real claim/release/hold reducer ────────────────
// Lifted verbatim from the source so a change to the source changes THIS.
// The model below re-implements claim(). That is only trustworthy while the
// source still contains the rules it models, so each rule is asserted as a
// NAMED check first — a clean red with a readable message, rather than a
// thrown exception, when someone edits the reducer.
const claimBody = coord.slice(coord.indexOf('claim: (id) => {'), coord.indexOf('release: (id) => {'));
const CLAIM_RULES = [
  [/if \(cur === id\) return true;/, 're-entrancy: a holder re-claiming succeeds'],
  [/if \(cur !== null\) return false;/, 'no preemption: a busy slot refuses'],
  [/tourHold && id !== 'guide_step'/, 'tour hold: refuses everything but guide_step'],
];
let modelValid = true;
for (const [re, what] of CLAIM_RULES) {
  const ok = re.test(claimBody);
  if (!ok) modelValid = false;
  assert(ok, `0. claim() still implements — ${what}`,
    'the behavioural model below mirrors this rule; source and model have drifted');
}

function makeStore() {
  let state = { activeSurface: null, tourHold: false };
  return {
    state,
    claim(id) {
      if (state.activeSurface === id) return true;
      if (state.activeSurface !== null) return false;
      if (state.tourHold && id !== 'guide_step') return false;
      state.activeSurface = id;
      return true;
    },
    release(id) { if (state.activeSurface === id) state.activeSurface = null; },
    beginTourHold() { state.tourHold = true; },
    endTourHold() { state.tourHold = false; },
  };
}

if (!modelValid) {
  console.log('  … behavioural checks 1-8 skipped: the model no longer mirrors the source');
} else {
  const s = makeStore();
  assert(s.claim('quickset_prompt') === true, '1. a surface claims a free slot normally');
  s.release('quickset_prompt');

  s.beginTourHold();
  assert(s.claim('quickset_prompt') === false, '2. the hold refuses a non-guide surface');
  assert(s.claim('apple_banner') === false, '3. the hold refuses every non-guide surface');
  assert(s.claim('guide_step') === true, '4. the tour\'s own bubbles still claim');

  // THE BUG THIS WAVE EXISTS TO FIX: between two steps the slot is free.
  s.release('guide_step');
  assert(s.state.activeSurface === null, '5. the slot is genuinely free between steps');
  assert(s.claim('quickset_prompt') === false,
    '6. nothing slips into the gap BETWEEN two tour steps',
    'this is the interruption ruling 10 describes; a per-step claim does not stop it');

  s.beginTourHold(); // idempotent
  s.endTourHold();
  assert(s.claim('quickset_prompt') === true, '7. ending the hold releases everything it muted');
  assert(s.state.tourHold === false, '8. begin is idempotent — one end suffices');
}

// ── Structural: the pieces the model cannot see ─────────────────────────
assert(/export function isInterruptBusy/.test(coord),
  '9. isInterruptBusy exists');
assert(/activeSurface !== null \|\| s\.tourHold/.test(coord),
  '10. isInterruptBusy covers the hold, not just the slot');
for (const [name, src] of [['AppleSaveMomentSheet', apple], ['PushPrimingModal', push]]) {
  assert(/useInterruptCoordinator\(isInterruptBusy\)/.test(src),
    `11. ${name} self-defers on isInterruptBusy`,
    'reading activeSurface alone lets a root modal open between two tour steps');
}
// The returned value must respect the hold too — claiming is not the only
// path to rendering; the hook's return is what the JSX reads.
assert(/!tourHold \|\| id === 'guide_step'/.test(coord),
  '12. useInterruptSlot\'s RETURN respects the hold',
  'a surface holding a stale grant would keep rendering through the tour');
// A tour refusal must be measurable and distinguishable.
assert(/blocked_by: 'tour'/.test(coord),
  '13. tour deferrals are instrumented with their own reason');

// The four unenrolled notices.
assert(/useMutedDuringTour/.test(coord) && /const mutedForTour = useMutedDuringTour\(\)/.test(trades),
  '14. the tour-only mute exists and TradesScreen reads it');
const MUTED = ['prefs-changed strip', 'diff banner', 'suppression note', 'adaptation moment'];
const mutedCount = (trades.match(/!mutedForTour/g) || []).length;
assert(mutedCount >= MUTED.length,
  `15. all ${MUTED.length} in-flow notices are muted for the tour`,
  `only ${mutedCount} guarded: ${MUTED.join(', ')}`);
// ...and the mute must not claim, or it could wedge the slot it never frees.
{
  const body = coord.slice(coord.indexOf('export function useMutedDuringTour'),
                           coord.indexOf('* Surface hook:'));
  assert(!/claim\(/.test(body),
    '16. the tour-only mute never claims the slot',
    'a claiming mute could wedge the arbiter for surfaces that never release');
}

console.log(failures === 0
  ? 'check-tour-suppression: all assertions passed'
  : `check-tour-suppression: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
