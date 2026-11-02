#!/usr/bin/env node
// B2 rule for TradeValueBar (Product P112, 11-02; head-eng round 3b): the
// "≈ N mid 1sts" form shows only at a gap of at least one first. A null
// pick_equivalent below that is the server's negligible floor (under half the
// smallest generic pick), so the bar reads Even (the centred nub, "Within a
// rounding error"), never "≈ 0.0 mid 1sts". The share image does the same
// (#564, league-eng), so the app and the image never disagree.
//
// The Even predicate, `valueBarIsEven`, is EXECUTED from TradeValueBar.tsx's
// own source, not re-implemented here. Every consumer of the Even state in the
// bar reads it (never raw `favors`), and so does the deck card's VoiceOver
// summary (release-lead's #567 B2 QA P2-1).
//
// Run: node tests/check-value-bar-b2.js
//   (or: npm run test:value-bar-b2)

'use strict';

const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'components', 'TradeValueBar.tsx'), 'utf8');
const screen = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'screens', 'TradesScreen.tsx'), 'utf8');

let passed = 0;
let failed = 0;
function check(name, ok, detail) {
  if (ok) {
    passed += 1;
    console.log(`  ok   ${name}`);
  } else {
    failed += 1;
    console.log(`  FAIL ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

console.log('check-value-bar-b2: under one first with no pick label reads Even');

// The predicate's body: between its signature's `): boolean {` and the
// closing brace at column 0.
const sig = src.indexOf('export function valueBarIsEven(');
const open = sig >= 0 ? src.indexOf('): boolean {', sig) : -1;
const close = open >= 0 ? src.indexOf('\n}\n', open) : -1;
const body = open >= 0 && close > open ? src.slice(open + '): boolean {'.length, close) : '';
check('valueBarIsEven is exported and found', body.includes('return'));

let decide = null;
try {
  // eslint-disable-next-line no-new-func
  const fn = new Function('favors', 'gap', body);
  decide = (gap, favors) => ({ even: fn(favors, gap) });
} catch (e) {
  check('valueBarIsEven evaluates', false, e.message);
}

const MID_2ND = { label: 'Mid 2nd Round Pick', value: 606.5 };
const cases = [
  ['a 40-point lean with no pick label reads Even', 'receive', { firsts: 0.02, pick_equivalent: null }, true],
  ['a negative lean under 1 first with no pick label reads Even', 'give', { firsts: -0.4, pick_equivalent: null }, true],
  ['0.7 firsts with no pick label reads Even (between 0.5 and 1)', 'receive', { firsts: 0.7, pick_equivalent: null }, true],
  ['exactly 1 first with no pick label leans (≈ 1.0 mid 1sts)', 'receive', { firsts: 1.0, pick_equivalent: null }, false],
  ['1.4 firsts with no pick label leans (≈ 1.4 mid 1sts)', 'give', { firsts: -1.4, pick_equivalent: null }, false],
  ['a lean with a pick label leans (a Mid 2nd)', 'receive', { firsts: 0.29, pick_equivalent: MID_2ND }, false],
  ['a small lean WITH a pick label still leans', 'give', { firsts: -0.06, pick_equivalent: MID_2ND }, false],
  ["favors 'even' reads Even", 'even', { firsts: 0.1, pick_equivalent: MID_2ND }, true],
  ['favors null reads Even', null, { firsts: 0, pick_equivalent: null }, true],
];
for (const [name, favors, gap, wantEven] of cases) {
  let got;
  try {
    got = decide ? decide(gap, favors).even : undefined;
  } catch (e) {
    got = `threw ${e.message}`;
  }
  check(name, got === wantEven, `even=${got}`);
}

// The "mid 1sts" form is the only no-pick wording, and it's reachable only
// off the even branch (the margin and the verdict both test `even` first).
check('"mid 1sts" is written once, as the no-pick fallback of `worth`',
  (src.match(/mid 1sts`/g) || []).length === 1 &&
  /const worth = pick \? shortPick\(pick\.label\) : `≈ \$\{firsts\.toFixed\(1\)\} mid 1sts`;/.test(src));
check('an Even bar draws the centred nub, not a sliver', /const frac = even \? 0 :/.test(src));

// Every consumer reads `even`. In the component, `favors` is read only by the
// predicate call and `youWin` (which every consumer gates behind !even).
const comp = src.slice(src.indexOf('export default function TradeValueBar('));
check('the component takes its Even state from the predicate',
  /const even = valueBarIsEven\(favors, gap\);/.test(comp));
const code = comp.replace(/\/\/[^\n]*/g, '');          // line comments aside
const favorsReads = (code.match(/\bfavors\b/g) || []).length;
check('`favors` is read only in the props, the predicate call and youWin', favorsReads === 3,
  `found ${favorsReads}`);
const consumers = {
  'the winner label': /const winner = even \? null :/,
  'the fill colour': /const fillColor = even \? ice\.base :/,
  'the headline': /\{even \? 'Even' : `\$\{winner\} win`\}/,
  'the margin line': /\{even \? \(\s*<Text style=\{styles\.margin\}>\s*Within a rounding error/,
  "the end labels' colour": /!even && !youWin && \{ color: fillColor \}[\s\S]*?!even && youWin && \{ color: fillColor \}/,
  'the Why? sheet': /\{!whyOpen \? null : even \? \(/,
};
for (const [name, re] of Object.entries(consumers)) check(`${name} reads \`even\``, re.test(comp));

// The deck card's VoiceOver summary says what the bar shows.
check("TradesScreen's VoiceOver summary reads the bar's predicate",
  /import \{ valueBarIsEven \} from '\.\.\/components\/TradeValueBar';/.test(screen) &&
  /const verdict = card\.gap && valueBarIsEven\(card\.favors, card\.gap\) \? ' Even\.'/.test(screen));

console.log(`\n${passed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
