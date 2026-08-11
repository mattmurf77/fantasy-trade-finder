#!/usr/bin/env node
// Regression test for the P0-6 send-platform resolution and copy-trade text
// (docs/plans/audit-p0-remediation/lld-p0-6.md §7).
//
// This is the COMPENSATING COVERAGE for the MFL/Fleaflicker simulator waiver:
// neither platform has a harness profile, and after the P0-6 refactor the
// entire platform-specific behaviour of the fix is three pure exports — the
// component only decides which branch renders. So the waiver is honest exactly
// to the extent that this file is thorough.
//
// Pins:
//   • resolveSendPlatform over all four platforms + the FAIL-OPEN invariant
//     (unknown/missing league id ⇒ 'sleeper', i.e. keep the Send button)
//   • NO_SEND_REASON's exhaustive keys and its #179 "name the platform" rule
//   • SEND_SURFACES — the exact dimension values P0-7 registers
//   • formatTradeForClipboard: the five-line template, per-line drop rules,
//     per-INDEX id fallback, no URL, never empty
//
// Mobile has no jest harness, so this transpiles the REAL module
// (src/utils/tradeText.ts — pure by design, zero runtime imports) with the
// project's typescript and runs it under plain node — same idiom as
// check-session-rerank.js.
//
// Run: node tests/check-trade-text.js  (or: npm run test:trade-text)

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

const srcPath = path.join(__dirname, '..', 'src', 'utils', 'tradeText.ts');
const source = fs.readFileSync(srcPath, 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

const moduleShim = { exports: {} };
new Function('module', 'exports', 'require', js)(moduleShim, moduleShim.exports, (name) => {
  throw new Error(
    `tradeText.ts gained a runtime import ("${name}") — it must stay pure ` +
      'so this check can run it under plain node.',
  );
});
const {
  resolveSendPlatform,
  NO_SEND_REASON,
  SEND_SURFACES,
  formatTradeForClipboard,
} = moduleShim.exports;

let failures = 0;
function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) {
    failures += 1;
    console.error(
      `FAIL  ${name}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
    );
  } else {
    console.log(`ok    ${name}`);
  }
}

// ── resolveSendPlatform ─────────────────────────────────────────────────
// 1–4: every platform value resolves to itself.
check('1  sleeper league → sleeper',
  resolveSendPlatform('L1', [{ league_id: 'L1', platform: 'sleeper' }]), 'sleeper');
check('2  espn league → espn',
  resolveSendPlatform('L1', [{ league_id: 'L1', platform: 'espn' }]), 'espn');
check('3  mfl league → mfl',
  resolveSendPlatform('L1', [{ league_id: 'L1', platform: 'mfl' }]), 'mfl');
check('4  fleaflicker league → fleaflicker',
  resolveSendPlatform('L1', [{ league_id: 'L1', platform: 'fleaflicker' }]), 'fleaflicker');

// 5: THE fail-open invariant — the single most load-bearing property here.
// A league id absent from the session cache (demo league, stale cache, an
// entry that skipped the picker) must keep the Send button, not hide it.
check('5  id absent from the cached list → sleeper (FAIL-OPEN)',
  resolveSendPlatform('L9', [{ league_id: 'L1', platform: 'espn' }]), 'sleeper');
check('6  empty league list → sleeper',
  resolveSendPlatform('L1', []), 'sleeper');
check('7  row present, platform undefined → sleeper',
  resolveSendPlatform('L1', [{ league_id: 'L1' }]), 'sleeper');
// 8: fail-open is by ALLOW-list, not deny-list — an unknown future platform
// keeps the send rather than rendering a reason for a platform we can't name.
check('8  unknown platform value → sleeper (allow-list, not deny-list)',
  resolveSendPlatform('L1', [{ league_id: 'L1', platform: 'yahoo' }]), 'sleeper');
check('9a undefined leagueId → sleeper',
  resolveSendPlatform(undefined, [{ league_id: 'L1', platform: 'espn' }]), 'sleeper');
check('9b empty-string leagueId → sleeper',
  resolveSendPlatform('', [{ league_id: 'L1', platform: 'espn' }]), 'sleeper');
// 10: first match wins, matching the old some() semantics.
check('10 duplicate ids → first row wins',
  resolveSendPlatform('L1', [
    { league_id: 'L1', platform: 'espn' },
    { league_id: 'L1', platform: 'sleeper' },
  ]), 'espn');
// 11: the canSend contract the component derives — platform !== 'sleeper'
// is exactly "not sendable", for every value of the union.
check('11 canSend contract holds for all four platforms',
  ['sleeper', 'espn', 'mfl', 'fleaflicker'].map(
    (p) => resolveSendPlatform('L1', [{ league_id: 'L1', platform: p }]) === 'sleeper',
  ),
  [true, false, false, false]);

// ── NO_SEND_REASON ──────────────────────────────────────────────────────
check('12 keys are exactly the three non-Sleeper platforms',
  Object.keys(NO_SEND_REASON).sort(), ['espn', 'fleaflicker', 'mfl']);
check('13 every reason is a non-empty string',
  Object.values(NO_SEND_REASON).every((v) => typeof v === 'string' && v.trim().length > 0), true);
// 14: the #179 honesty rule — never "this league type". Catches a copy-paste
// that leaves all three saying "ESPN".
check('14 every reason NAMES its platform',
  [
    /ESPN/.test(NO_SEND_REASON.espn),
    /MyFantasyLeague/.test(NO_SEND_REASON.mfl),
    /Fleaflicker/.test(NO_SEND_REASON.fleaflicker),
  ], [true, true, true]);
check('15 every reason carries the shared "Sleeper-only" explanation',
  Object.values(NO_SEND_REASON).every((v) => v.includes('Sleeper-only')), true);

// ── SEND_SURFACES ───────────────────────────────────────────────────────
// 16: pins the dimension values P0-7 registers in the analytics taxonomy.
check('16 surfaces are exactly deck/match/awaiting/calculator',
  SEND_SURFACES, ['deck', 'match', 'awaiting', 'calculator']);

// ── formatTradeForClipboard ─────────────────────────────────────────────
const FULL = {
  giveNames: ['Justin Jefferson', '2027 1st'],
  giveIds: ['4034', 'pick:2027:1'],
  receiveNames: ["Ja'Marr Chase", 'Jaxon Smith-Njigba'],
  receiveIds: ['6794', '9221'],
  opponentUsername: 'tdickens',
  leagueName: 'QA ESPN League',
};

check('17 all fields present → the exact five-line block',
  formatTradeForClipboard(FULL),
  'Trade proposal — QA ESPN League\n' +
  'To: @tdickens\n' +
  "I send: Justin Jefferson, 2027 1st\n" +
  "I get: Ja'Marr Chase, Jaxon Smith-Njigba\n" +
  '(Built with Fantasy Trade Finder)');

check('18 leagueName absent → bare "Trade proposal", no dash, no trailing space',
  formatTradeForClipboard({ ...FULL, leagueName: undefined }).split('\n')[0],
  'Trade proposal');
check('19 whitespace-only leagueName → same as absent',
  formatTradeForClipboard({ ...FULL, leagueName: '   ' }).split('\n')[0],
  'Trade proposal');

check('20 opponentUsername absent → no "To:" line, other four survive',
  formatTradeForClipboard({ ...FULL, opponentUsername: undefined }),
  'Trade proposal — QA ESPN League\n' +
  "I send: Justin Jefferson, 2027 1st\n" +
  "I get: Ja'Marr Chase, Jaxon Smith-Njigba\n" +
  '(Built with Fantasy Trade Finder)');

// 21–23: the id fallback. Ids in the paste are ugly but correct and
// actionable; an empty side is neither.
check('21 names absent, ids present → ids reach the clipboard',
  formatTradeForClipboard({ giveIds: ['4034', '6794'] }).split('\n')[1],
  'I send: 4034, 6794');
check('22 names PARTIALLY present → per-INDEX fallback, kept names survive',
  formatTradeForClipboard({
    giveNames: ['Justin Jefferson', undefined],
    giveIds: ['4034', '6794'],
  }).split('\n')[1],
  'I send: Justin Jefferson, 6794');
check('23 whitespace-only name falls through to its id',
  formatTradeForClipboard({
    giveNames: ['  ', 'Bijan Robinson'],
    giveIds: ['4034', '6794'],
  }).split('\n')[1],
  'I send: 4034, Bijan Robinson');

check('24 multi-asset join is ", " with no trailing comma',
  formatTradeForClipboard({ giveIds: ['a', 'b', 'c'] }).split('\n')[1],
  'I send: a, b, c');

// 25: both sides empty ⇒ the lines drop, never blank — a paste is never
// zero-length. No mount can reach this today; the helper is total anyway.
check('25 both sides empty → 3 lines, never an empty string',
  formatTradeForClipboard({ opponentUsername: 'tdickens' }),
  'Trade proposal\nTo: @tdickens\n(Built with Fantasy Trade Finder)');

// 26–28: shape invariants over a spread of inputs.
const SAMPLES = [
  FULL,
  {},
  { giveIds: ['4034'] },
  { leagueName: '  ', opponentUsername: '', receiveNames: ['', ' '] },
  { giveNames: ['A'], receiveNames: ['B'], opponentUsername: 'x', leagueName: 'L' },
];
check('26 no leading/trailing whitespace and no blank lines, ever',
  SAMPLES.every((s) => {
    const out = formatTradeForClipboard(s);
    return out === out.trim() && !out.includes('\n\n');
  }), true);
// 27: pins the no-URL rule so a future edit cannot quietly widen the
// growth.share_landing attribution surface through this payload.
check('27 never contains a URL',
  SAMPLES.every((s) => !/https?:\/\//.test(formatTradeForClipboard(s))), true);
check('28 always opens "Trade proposal" and closes with the footer',
  SAMPLES.every((s) => {
    const lines = formatTradeForClipboard(s).split('\n');
    return lines[0].startsWith('Trade proposal')
      && lines[lines.length - 1] === '(Built with Fantasy Trade Finder)';
  }), true);

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll trade-text checks passed.');
