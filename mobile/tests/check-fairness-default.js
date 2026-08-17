#!/usr/bin/env node
// Fairness-preference default test (operator decision 2026-08-17: unset ⇒ OFF).
//
// WHY THIS EXISTS. Two separate things can silently break here, and neither
// shows up in a UI test:
//
//   1. THE DEFAULT ITSELF. An unset preference must resolve to OFF (the wide
//      0.5 net). The old reading was `raw === 'off' ? OFF : ON`, so a
//      well-meaning revert to that shape flips every unset user back to
//      balanced-only without touching a line of visible UI. Explicit choices
//      must survive: 'on' stays on, 'off' stays off, and NOTHING rewrites the
//      stored key.
//   2. THE TWO READ SITES AGREEING. `maybePregenTrades` (session init) and
//      TradesScreen's own generate both send `fairness_threshold`, and the
//      server's `_trade_job_is_fresh` keys the job cache on that value. If
//      they disagree, the pregen warms a slot the screen never reads and the
//      user waits for a second full generation. The defence is that both
//      derive from ONE helper — so this file asserts the screen re-uses it
//      rather than re-deriving the boolean or the threshold locally.
//
// The helper is loaded and RUN (the check-offer-prefill-330-unit.js idiom:
// transpile the real module, shim its runtime imports) so these are real
// behavioural assertions, not greps.
//
// Run: node tests/check-fairness-default.js
//   (or: npm run test:fairness-default)

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

const ROOT = path.join(__dirname, '..');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

function load(rel, requireShim) {
  const source = fs.readFileSync(path.join(ROOT, rel), 'utf8');
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const moduleShim = { exports: {} };
  new Function('module', 'exports', 'require', js)(
    moduleShim,
    moduleShim.exports,
    requireShim,
  );
  return moduleShim.exports;
}

// ── Load the real tradePregen module ─────────────────────────────────────
// The AsyncStorage shim records every key touched, which is how "we never
// write the pref back" below is proven rather than asserted.
const storage = { data: new Map(), writes: [] };
const AsyncStorageStub = {
  getItem: async (k) => (storage.data.has(k) ? storage.data.get(k) : null),
  setItem: async (k, v) => {
    storage.writes.push([k, v]);
    storage.data.set(k, v);
  },
  removeItem: async (k) => {
    storage.writes.push([k, null]);
    storage.data.delete(k);
  },
};
const generateCalls = [];
const pregen = load('src/api/tradePregen.ts', (name) => {
  if (name === '@react-native-async-storage/async-storage') {
    return { __esModule: true, default: AsyncStorageStub };
  }
  if (name === '../state/useFeatureFlags') return { onboardingEnabled: () => true };
  if (name === './trades') {
    return {
      generateTrades: async (body) => {
        generateCalls.push(body);
        return {};
      },
    };
  }
  throw new Error(
    `tradePregen.ts gained an unexpected runtime import ("${name}") — extend ` +
      'the shim deliberately, do not let it pass silently.',
  );
});

const {
  FAIRNESS_PREF_KEY,
  FAIRNESS_ON_THRESHOLD,
  FAIRNESS_OFF_THRESHOLD,
  fairnessOnFromPref,
  fairnessThresholdFor,
  maybePregenTrades,
} = pregen;

// ═══════════════════════════════════════════════════════════════════════
// 1. The default and the explicit choices
// ═══════════════════════════════════════════════════════════════════════

assert(
  fairnessOnFromPref(null) === false,
  'unset (null) → OFF',
  'the 2026-08-17 default — a revert to `raw === "off" ? OFF : ON` fails here',
);
assert(fairnessOnFromPref(undefined) === false, 'unset (undefined) → OFF');
assert(fairnessOnFromPref('') === false, 'empty string → OFF');
assert(
  fairnessOnFromPref('on') === true,
  "explicit 'on' → ON",
  'a user who deliberately turned balancing on must keep it',
);
assert(fairnessOnFromPref('off') === false, "explicit 'off' → OFF");
assert(
  fairnessOnFromPref('ON') === false && fairnessOnFromPref('true') === false,
  'any other stored value → OFF (only the exact string "on" opts in)',
);

assert(
  fairnessThresholdFor(true) === FAIRNESS_ON_THRESHOLD && FAIRNESS_ON_THRESHOLD === 0.75,
  'ON maps to the 0.75 threshold',
);
assert(
  fairnessThresholdFor(false) === FAIRNESS_OFF_THRESHOLD && FAIRNESS_OFF_THRESHOLD === 0.5,
  'OFF maps to the 0.5 threshold (a value, not a dropped field — cache key)',
);

// ═══════════════════════════════════════════════════════════════════════
// 2. The pregen read site, end to end
// ═══════════════════════════════════════════════════════════════════════

async function pregenThresholdFor(stored, leagueId) {
  storage.data.clear();
  storage.writes.length = 0;
  generateCalls.length = 0;
  if (stored !== null) storage.data.set(FAIRNESS_PREF_KEY, stored);
  maybePregenTrades(leagueId);
  // maybePregenTrades is fire-and-forget; let its async IIFE settle.
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
  return generateCalls[0];
}

(async () => {
  const unset = await pregenThresholdFor(null, 'L-unset');
  assert(
    unset && unset.fairness_threshold === FAIRNESS_OFF_THRESHOLD,
    'pregen: unset preference kicks the job at 0.5',
    `sent ${unset && unset.fairness_threshold}`,
  );
  assert(
    storage.writes.length === 0,
    'pregen: reading the preference never writes it back',
    `writes: ${JSON.stringify(storage.writes)}`,
  );

  const on = await pregenThresholdFor('on', 'L-on');
  assert(
    on && on.fairness_threshold === FAIRNESS_ON_THRESHOLD,
    "pregen: explicit 'on' kicks the job at 0.75",
  );
  const off = await pregenThresholdFor('off', 'L-off');
  assert(
    off && off.fairness_threshold === FAIRNESS_OFF_THRESHOLD,
    "pregen: explicit 'off' kicks the job at 0.5",
  );

  // ═════════════════════════════════════════════════════════════════════
  // 3. The screen read site derives from the SAME helper
  // ═════════════════════════════════════════════════════════════════════

  const screen = fs.readFileSync(
    path.join(ROOT, 'src/screens/TradesScreen.tsx'),
    'utf8',
  );
  assert(
    /fairnessOnFromPref,/.test(screen) && /fairnessThresholdFor,/.test(screen),
    'TradesScreen imports both helpers from api/tradePregen',
  );
  assert(
    /useState\(fairnessOnFromPref\(null\)\)/.test(screen),
    'TradesScreen: the toggle initialises from the helper, not a literal',
    'a hard-coded `useState(true)` paints ON while 0.5 is being sent',
  );
  assert(
    /setFairnessOn\(fairnessOnFromPref\(raw\)\)/.test(screen),
    'TradesScreen: the hydrate resolves the stored value through the helper',
  );
  assert(
    /const effectiveFairness = fairnessThresholdFor\(fairnessOn\)/.test(screen),
    'TradesScreen: the threshold comes from the helper',
    'a local ternary is exactly how the two read sites drift apart',
  );
  assert(
    !/FAIRNESS_(ON|OFF)_THRESHOLD/.test(screen),
    'TradesScreen: no longer re-derives the threshold from the raw constants',
  );
  // The toggle writes 'on'/'off' explicitly — that is what makes an explicit
  // choice distinguishable from unset in the first place.
  assert(
    /setItem\(FAIRNESS_PREF_KEY, next \? 'on' : 'off'\)/.test(screen),
    "TradesScreen: the toggle persists the explicit 'on'/'off' strings",
  );

  console.log('');
  if (failures) {
    console.error(`${failures} check(s) failed.`);
    process.exit(1);
  }
  console.log('All fairness-default checks passed.');
})();
