#!/usr/bin/env node
// The web calculator's verdict label reads `favors` the way the app's value bar
// does: 'receive' = you get more back ("Favors you"), 'give' = they do
// ("Favors them"), 'even' or absent = "Even both ways". From #263 until this
// fix the web page had 'give' and 'receive' swapped, while its own gap line
// ("add to their side") and the app ("They win") read them right (found in
// #567's QA; head-eng round 4).
//
// The label expression is EXECUTED from web/calculator.html's own source.
//
// Run: node tests/check-web-calc-favors.js
//   (or: npm run test:web-calc-favors)

'use strict';

const fs = require('fs');
const path = require('path');

const REPO = path.join(__dirname, '..', '..');
const page = fs.readFileSync(path.join(REPO, 'web', 'calculator.html'), 'utf8');
const bar = fs.readFileSync(path.join(REPO, 'mobile', 'src', 'components', 'TradeValueBar.tsx'), 'utf8');

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

console.log("check-web-calc-favors: the web verdict label reads favors as the app does");

const m = page.match(/var favorsTxt = ([\s\S]*?);\n/);
check('the label expression is found', !!m);
let label = null;
try {
  // eslint-disable-next-line no-new-func
  label = new Function('d', `return (${m ? m[1] : 'null'});`);
} catch (e) {
  check('the label expression evaluates', false, e.message);
}

const cases = [
  ["favors 'receive' (you get more) reads Favors you", 'receive', 'Favors you'],
  ["favors 'give' (they get more) reads Favors them", 'give', 'Favors them'],
  ["favors 'even' reads Even both ways", 'even', 'Even both ways'],
  ['no favors reads Even both ways', null, 'Even both ways'],
];
for (const [name, favors, want] of cases) {
  let got;
  try {
    got = label ? label({ favors }) : undefined;
  } catch (e) {
    got = `threw ${e.message}`;
  }
  check(name, got === want, `got ${JSON.stringify(got)}`);
}

// The same reading as the app's bar and the page's own gap line.
check("the app's bar reads 'receive' as you winning",
  /const youWin = favors === 'receive';/.test(bar));
check("the page's gap line sends the sweetener to your side when add_to is 'give'",
  /var who = d\.gap\.add_to === 'give' \? 'your side' : 'their side';/.test(page));

console.log(`\n${passed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
