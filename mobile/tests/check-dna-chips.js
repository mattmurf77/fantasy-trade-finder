#!/usr/bin/env node
// #193 regression test — Trade DNA Chasing/Shopping chip de-conflict
// (src/utils/dnaChips.ts, used by TradeFinderHubScreen's DNA panel).
//
// Pins:
//   • THE invariant: no position ever appears in both the chasing and the
//     shopping chip lists (the operator bug: explicitly shopping QB while the
//     roster profile recommended chasing it rendered QB on both sides)
//   • precedence: explicit prefs beat recommendations on BOTH sides;
//     acquire beats shed (explicit∩explicit); need beats deep (rec∩rec)
//   • ordering convention: explicit chips first, then rec chips, posOrder
//     within each run
//
// Mobile has no jest harness, so this transpiles the REAL module (pure by
// design, zero runtime imports) with the project's typescript and runs it
// under plain node — same idiom as check-session-rerank.js.
//
// Run: node tests/check-dna-chips.js  (or: npm run test:dna-chips)

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

const srcPath = path.join(__dirname, '..', 'src', 'utils', 'dnaChips.ts');
const source = fs.readFileSync(srcPath, 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

const moduleShim = { exports: {} };
new Function('module', 'exports', 'require', js)(moduleShim, moduleShim.exports, (name) => {
  throw new Error(
    `dnaChips.ts gained a runtime import ("${name}") — it must stay pure ` +
      'so this check can run it under plain node.',
  );
});
const { splitDnaChips } = moduleShim.exports;

const POS = ['QB', 'RB', 'WR', 'TE'];

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

const split = (acquire, shed, needs, surplus) =>
  splitDnaChips({ acquire, shed, needs, surplus, posOrder: POS });
const posesOf = (chips) => chips.map((c) => c.pos);

// ── The operator repro (#193): explicitly shopping QB, profile says thin
//    at QB → QB must render on the Shopping side ONLY (explicit wins).
const repro = split([], ['QB'], ['QB', 'WR'], []);
check('repro: QB shopping only (explicit)', posesOf(repro.shopping), ['QB']);
check('repro: chasing keeps the non-conflicted need', posesOf(repro.chasing), ['WR']);
check('repro: QB not chased', repro.chasing.some((c) => c.pos === 'QB'), false);

// Mirror image: explicitly chasing RB while the profile says deep at RB.
const mirror = split(['RB'], [], [], ['RB', 'TE']);
check('mirror: RB chasing only (explicit)', posesOf(mirror.chasing), ['RB']);
check('mirror: shopping keeps the non-conflicted deep', posesOf(mirror.shopping), ['TE']);

// ── Tiebreaks ───────────────────────────────────────────────────────────
// explicit∩explicit: acquire wins, chip renders under Chasing only.
const ee = split(['WR'], ['WR'], [], []);
check('acquire beats shed', [posesOf(ee.chasing), posesOf(ee.shopping)], [['WR'], []]);
// rec∩rec (impossible with current analyzer thresholds; defensive): need wins.
const rr = split([], [], ['TE'], ['TE']);
check('need beats deep', [posesOf(rr.chasing), posesOf(rr.shopping)], [['TE'], []]);
check('need chip tagged', rr.chasing[0], { pos: 'TE', rec: true, tag: 'need' });

// ── Ordering convention: explicit run first, then rec run, posOrder each.
const ord = split(['WR'], ['TE'], ['QB'], ['RB']);
check('chasing = explicit then rec', ord.chasing, [
  { pos: 'WR', rec: false },
  { pos: 'QB', rec: true, tag: 'need' },
]);
check('shopping = explicit then rec', ord.shopping, [
  { pos: 'TE', rec: false },
  { pos: 'RB', rec: true, tag: 'deep' },
]);

// ── Empty in, empty out (panel's "Nothing set" state) ───────────────────
check('all empty', split([], [], [], []), { chasing: [], shopping: [] });

// ── THE invariant, exhaustively: every membership combination of QB across
//    the four input lists (and each pos across a scattered fixture) yields
//    disjoint sides.
let disjointViolations = 0;
for (let mask = 0; mask < 16; mask += 1) {
  const inputs = [
    mask & 1 ? ['QB'] : [],
    mask & 2 ? ['QB'] : [],
    mask & 4 ? ['QB'] : [],
    mask & 8 ? ['QB'] : [],
  ];
  const out = split(...inputs);
  const both = posesOf(out.chasing).filter((p) => posesOf(out.shopping).includes(p));
  if (both.length > 0) {
    disjointViolations += 1;
    console.error(`FAIL  invariant: mask ${mask} put ${both} on both sides`);
  }
  // A pos present in ANY input must land on exactly one side (never dropped).
  if (mask !== 0 && posesOf(out.chasing).length + posesOf(out.shopping).length !== 1) {
    disjointViolations += 1;
    console.error(`FAIL  invariant: mask ${mask} dropped or duplicated QB`);
  }
}
check('invariant sweep: 16/16 combos disjoint + lossless', disjointViolations, 0);

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll dna-chips checks passed.');
