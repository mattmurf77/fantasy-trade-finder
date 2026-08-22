#!/usr/bin/env node
// #384 — the demo CALCULATOR is gone; the demo SESSION is not.
//
// WHY THIS EXISTS. "Demo" names two unrelated systems in this codebase, and
// they share nothing but the word:
//
//   1. The demo CALCULATOR mode — a seeded mock dual-board league
//      (`data/tradeCalcMock.ts`, `CalcMode = 'demo'`). REMOVED 2026-08-22 on
//      the operator's call ("it's pointless").
//   2. The demo SESSION — `/api/session/demo`, `useSession.isDemo`, the
//      SignIn "try before you sync" path, `onboarding.demo_bridge`. This is
//      OPEN-ACCESS ONBOARDING and is load-bearing.
//
// A `git grep demo` returns both. The removal touched sixteen files, and the
// failure mode this file exists to prevent is a future change — human or
// agent — reading "remove the demo calc" and deleting the try-before-signin
// path, which would look locally reasonable and break acquisition silently.
//
// So this guard is TWO-SIDED on purpose. A one-sided "the mock is gone"
// assertion would stay green through exactly the mistake worth catching.
//
// Run: node tests/check-demo-calc-removed.js

'use strict';

const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'src');
let failures = 0;

function assert(cond, name, detail) {
  if (cond) {
    console.log(`  ✓ ${name}`);
  } else {
    failures++;
    console.log(`  ✗ ${name}`);
    if (detail) console.log(`      ${detail}`);
  }
}
const read = (rel) => fs.readFileSync(path.join(SRC, rel), 'utf8');
const exists = (rel) => fs.existsSync(path.join(SRC, rel));

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}
const ALL = walk(SRC);

console.log('check-demo-calc-removed:');

// ── Side A: the demo CALCULATOR is gone ─────────────────────────────────

// Sabotage: restore data/tradeCalcMock.ts → red.
assert(!exists('data/tradeCalcMock.ts'),
  '1. the mock league fixture is deleted',
  'src/data/tradeCalcMock.ts is back; the demo calculator was removed in #384');

// Sabotage: re-add the import anywhere → red.
//
// Matches IMPORT STATEMENTS, not the bare word: several files carry comments
// naming `tradeCalcMock` as the thing that was removed and why, and that
// provenance is worth keeping. A guard that banned the word would pressure
// the next author to delete the explanation.
const IMPORT_RE = /(?:from\s*['"][^'"]*tradeCalcMock['"]|require\(\s*['"][^'"]*tradeCalcMock['"])/;
const importers = ALL.filter((f) => IMPORT_RE.test(fs.readFileSync(f, 'utf8')));
assert(importers.length === 0,
  '2. nothing imports the mock fixture',
  importers.map((f) => path.relative(SRC, f)).join(', '));

// Sabotage: put 'demo' back in the CalcMode union → red.
const calc = read('screens/TradeCalculatorScreen.tsx');
const modeUnion = calc.match(/type CalcMode = ([^;]+);/);
assert(modeUnion && !/'demo'/.test(modeUnion[1]),
  "3. CalcMode has no 'demo' member",
  modeUnion ? modeUnion[1].trim() : 'CalcMode union not found');

// Sabotage: re-add the mode tab → red. Distinct from 3 because a tab whose
// key is a string literal would survive a union that no longer allows it
// only if someone also widened the type — this catches the tab itself.
assert(!/key:\s*'demo'/.test(calc),
  '4. no Demo league tab is offered',
  "a modeTabs entry with key 'demo' is back in TradeCalculatorScreen");

// Sabotage: the shared types must NOT come back via the deleted module.
assert(exists('data/calcTypes.ts'),
  '5. the shared calculator types survived the removal',
  'src/data/calcTypes.ts is missing — CalcPlayer/CalcPos are used by the '
  + 'live calculator, InLeagueCalculator, the deck picker and tradeCalcMath');

// ── Side B: the demo SESSION is untouched. THIS is the half that matters ──

// Anchors are WORD-BOUNDED on purpose. A substring match (/isDemo/) stays
// green when the symbol is renamed — verified by sabotage: renaming isDemo →
// isDemoRenamed left the loose form passing, which made the assertion
// unfalsifiable and therefore worthless. Each entry names a real symbol.
const SESSION_ANCHORS = [
  ['state/useSession.ts',        /\bisDemo\b/,        'useSession.isDemo'],
  ['state/useSession.ts',        /session\/demo/,     'the /api/session/demo bootstrap'],
  // `startDemoSession` is the store action that actually boots the session,
  // and `landing.try_before_sync` is the flag that exposes the affordance —
  // both load-bearing, neither a substring of something else. An earlier
  // draft anchored on /onDemo/, which matched `onDemoStarted` and survived
  // the sabotage that renamed it. Sabotage-verified in both forms.
  ['screens/SignInScreen.tsx',   /\bstartDemoSession\b/,
                                                      "SignIn's demo-session bootstrap"],
  ['screens/SignInScreen.tsx',   /landing\.try_before_sync/,
                                                      'the try-before-you-sync flag gate'],
  ['utils/shareLinks.ts',        /\bisDemo\b/,        'the share mint\'s demo-session refusal'],
  ['api/calc.ts',                /\bdemo_session\b/,  'the 400 demo_session narrowing'],
];
for (const [rel, re, what] of SESSION_ANCHORS) {
  assert(exists(rel) && re.test(read(rel)),
    `6. demo SESSION intact — ${what}`,
    `${rel} no longer mentions it. The demo SESSION is open-access onboarding `
    + `and is NOT the demo calculator. Removing it is the #384 conflation trap.`);
}

// Sabotage: delete the demo-bridge surface from TradesScreen → red.
//
// The old form counted FILES mentioning `demo_bridge` and passed at ≥2. Two
// of the "files" it counted were a comment in TradeCalculatorScreen and the
// surface itself, so the threshold was carrying the guarantee rather than the
// anchors — and a threshold can be satisfied by prose. The surface is three
// named things in ONE file; each is asserted on its own.
{
  const tradesScreen = read('screens/TradesScreen.tsx');
  const BRIDGE_ANCHORS = [
    [/useOnboardingFeature\('onboarding\.demo_bridge'\)/, 'the flag read'],
    [/testID="trades\.demo-bridge"/, 'the surface itself'],
    [/track\('demo_bridge_tapped'/, 'the conversion event'],
  ];
  for (const [re, what] of BRIDGE_ANCHORS) {
    assert(re.test(tradesScreen),
      `7. the demo→real conversion bridge still exists — ${what}`,
      'TradesScreen no longer carries it. The bridge converts demo SESSIONS to '
      + 'real accounts and has nothing to do with the removed demo calculator.');
  }
}

// ── Side C: no demo CALCULATOR copy survives ────────────────────────────
//
// The removal left an instruction behind ("Retry, or switch to the demo
// league") on the calculator's error state — a dead instruction naming a tab
// that no longer exists. Copy is not covered by the union/tab assertions
// above, which is how it survived W0. The word `demo` is still legal here:
// the file carries provenance comments and the demo-SESSION reference, and
// banning it would pressure the next author to delete the explanation. So the
// COMMENTS are stripped and only the code that ships is scanned.
{
  const code = calc.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
  const offenders = [...code.matchAll(/.{0,60}\bdemo\s+(?:league|calculator|mode|board|values)\b.{0,20}/gi)]
    .map((m) => m[0].replace(/\s+/g, ' ').trim());
  assert(offenders.length === 0,
    '8. no demo-CALCULATOR instruction copy survives in TradeCalculatorScreen',
    `found: ${offenders.map((s) => `"…${s}…"`).join(' · ')} — the tab it names is gone`);
}

console.log(
  failures === 0
    ? `check-demo-calc-removed: all assertions passed`
    : `check-demo-calc-removed: ${failures} FAILED`,
);
process.exit(failures === 0 ? 0 : 1);
