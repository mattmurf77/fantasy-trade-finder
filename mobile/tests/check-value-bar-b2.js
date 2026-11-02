#!/usr/bin/env node
// B2 rule for TradeValueBar (Product P112, 11-02; head-eng round 3b): the
// "≈ N mid 1sts" form shows only at a gap of at least one first. A null
// pick_equivalent below that is the server's negligible floor (under half the
// smallest generic pick), so the bar reads Even (the centred nub, "Within a
// rounding error"), never "≈ 0.0 mid 1sts". The share image does the same
// (#564, league-eng), so the app and the image never disagree.
//
// The decision lines are EXECUTED from TradeValueBar.tsx's own source, not
// re-implemented here.
//
// Run: node tests/check-value-bar-b2.js
//   (or: npm run test:value-bar-b2)

'use strict';

const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'components', 'TradeValueBar.tsx'), 'utf8');

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

// The component's decision block: from `const firsts` up to `const youWin`.
const start = src.indexOf('  const firsts = Math.abs(gap.firsts);');
const end = src.indexOf('  const youWin =', start);
const block = start >= 0 && end > start ? src.slice(start, end) : '';
check('the decision block is found (firsts … even)', block.includes('const even ='));

let decide = null;
try {
  // eslint-disable-next-line no-new-func
  decide = new Function('gap', 'favors', `${block}\nreturn { even };`);
} catch (e) {
  check('the decision block evaluates', false, e.message);
}

const MID_2ND = { label: 'Mid 2nd Round Pick', value: 606.5 };
const cases = [
  ['a 40-point lean with no pick label reads Even', 'receive', { firsts: 0.02, pick_equivalent: null }, true],
  ['a negative lean under 1 first with no pick label reads Even', 'give', { firsts: -0.4, pick_equivalent: null }, true],
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

console.log(`\n${passed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
