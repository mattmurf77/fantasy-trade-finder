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
// This file TRANSPILES AND EXECUTES the real store, the way
// check-presentation-v2.js executes `tradePresentation.ts` — it does not
// re-implement it. The earlier draft modelled `claim()` in this file, and a
// model is only ever as honest as the sabotage that tests it: emptying
// `endTourHold: () => {}` in the source left this suite fully green, because
// nothing here ever ran the source's version. `beginTourHold: () => {}` was
// green for the same reason. Both are red now.
//
// The module imports react / zustand / useFeatureFlags / api-events, so the
// loader below supplies exactly those four — a minimal zustand `create`, and
// throwing stubs for anything else, so a new runtime import is a loud failure
// rather than a silent skip.
//
// Run: node tests/check-tour-suppression.js

'use strict';

const fs = require('fs');
const path = require('path');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

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

// ── Behavioural: run the REAL claim/release/hold reducer ────────────────
//
// A hand-rolled zustand: `create(initializer)` calls the initializer with
// (set, get) and returns a callable store carrying getState/setState. That is
// the whole surface this module uses, so the store below IS the shipped one —
// its `claim`, its `beginTourHold`, its `endTourHold`.
function makeZustandCreate() {
  return function create(initializer) {
    let state;
    const setState = (partial) => {
      const next = typeof partial === 'function' ? partial(state) : partial;
      state = Object.assign({}, state, next);
    };
    const getState = () => state;
    state = initializer(setState, getState, { setState, getState });
    const hook = (selector) => (selector ? selector(state) : state);
    hook.getState = getState;
    hook.setState = setState;
    return hook;
  };
}

function loadCoordinator() {
  const js = ts.transpileModule(coord, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const shim = { exports: {} };
  const stubs = {
    react: { useEffect: () => {}, useRef: () => ({ current: false }) },
    zustand: { create: makeZustandCreate() },
    './useFeatureFlags': { useFlag: () => true },
    '../api/events': { track: () => {} },
  };
  new Function('module', 'exports', 'require', js)(shim, shim.exports, (name) => {
    if (name in stubs) return stubs[name];
    throw new Error(
      `useInterruptCoordinator gained an unexpected runtime import ("${name}") — ` +
        'add a stub here deliberately, do not let the behavioural suite skip.',
    );
  });
  return shim.exports;
}

let coordMod = null;
try {
  coordMod = loadCoordinator();
} catch (e) {
  assert(false, '0. useInterruptCoordinator transpiles and executes', String(e && e.message));
}

if (coordMod) {
  const store = coordMod.useInterruptCoordinator;
  assert(typeof store === 'function' && typeof store.getState === 'function',
    '0. the coordinator store is exported and constructed');
  const s = store.getState();
  const st = () => store.getState();

  assert(s.claim('quickset_prompt') === true, '1. a surface claims a free slot normally');
  assert(s.claim('apple_banner') === false, '1a. no preemption — a busy slot refuses');
  assert(s.claim('quickset_prompt') === true, '1b. the holder re-claiming is re-entrant');
  s.release('quickset_prompt');
  assert(st().activeSurface === null, '1c. release frees the slot');

  s.beginTourHold();
  assert(st().tourHold === true, '2a. beginTourHold actually raises the hold',
    'an empty beginTourHold body leaves every interstitial live through the tour');
  assert(s.claim('quickset_prompt') === false, '2. the hold refuses a non-guide surface');
  assert(s.claim('apple_banner') === false, '3. the hold refuses every non-guide surface');
  assert(s.claim('guide_step') === true, '4. the tour\'s own bubbles still claim');

  // THE BUG THIS WAVE EXISTS TO FIX: between two steps the slot is free.
  s.release('guide_step');
  assert(st().activeSurface === null, '5. the slot is genuinely free between steps');
  assert(s.claim('quickset_prompt') === false,
    '6. nothing slips into the gap BETWEEN two tour steps',
    'this is the interruption ruling 10 describes; a per-step claim does not stop it');

  s.beginTourHold(); // idempotent
  s.endTourHold();
  assert(st().tourHold === false, '8. begin is idempotent — one end suffices',
    'an empty endTourHold body leaks the hold and mutes the app for the session');
  assert(s.claim('quickset_prompt') === true, '7. ending the hold releases everything it muted');
  s.release('quickset_prompt');

  // isInterruptBusy is what the ROOT MODALS read; run it, do not grep it.
  s.beginTourHold();
  assert(coordMod.isInterruptBusy(st()) === true,
    '8a. isInterruptBusy reads true from the hold alone, with the slot free');
  s.endTourHold();
  assert(coordMod.isInterruptBusy(st()) === false, '8b. …and false once nothing is up');
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
// A tour refusal must be measurable and distinguishable. Anchored on the CALL,
// not the phrase: the file's header comment says "measured as `blocked_by:
// 'tour'`", so the loose form stayed green with the track() call deleted.
assert(/track\('prompt_deferred', \{ surface: id, blocked_by: 'tour' \}/.test(coord),
  '13. tour deferrals are instrumented with their own reason',
  'the doc comment names this string too — the emitter itself must be present');

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
