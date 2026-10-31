#!/usr/bin/env node
// C2: a shared trade states no verdict, win, board read, ratio or totals
// (head-bizops, under the launch-roadmap approval; privacy §3 "Your raw
// ranking list is never shown to other users"). The in-league share lines
// ("Wins by my board — @opp likely disagrees", "@opp wins this one by their
// board") published a read of the partner's board to whoever received the
// share; the calculator's ("Verdict: fair", "(ratio N%)") and the image's
// TOTAL rows were the raw consensus read. Every state now says the existing
// "Package value" (SHARE_VALUE_LINE), on the image and in the text.
//
// Scoped to the share code: the share image component, each
// <ShareTradeImage … /> element (its verdictLine and its fallback text) and
// the calculator's shareTrade text. The in-app verdict (LeagueVerdict, the
// calculator's verdict card) is unchanged and not checked here.
//
// Run: node tests/check-share-text.js
//   (or: npm run test:share-text)

'use strict';

const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'src');
const read = (f) => fs.readFileSync(path.join(SRC, f), 'utf8');

const image = read('components/ShareTradeImage.tsx');
const calc = read('screens/TradeCalculatorScreen.tsx');
const league = read('components/InLeagueCalculator.tsx');

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

const elements = (src) => src.match(/<ShareTradeImage[\s\S]*?\n\s*\/>/g) || [];
function region(src, start, end) {
  const i = src.indexOf(start);
  const j = i < 0 ? -1 : src.indexOf(end, i);
  return i < 0 || j < 0 ? '' : src.slice(i, j);
}

const BANNED = [
  '(ratio ', 'Verdict: ', 'Win–win by both boards', 'Wins by my board',
  'wins this one by their board', 'Roughly even by both boards',
  'Consensus verdict', 'Consensus read', 'Consensus: ', 'sends more',
  'liveVerdictLine', 'shareVerdictLine', 'sendTotal', 'receiveTotal',
];

console.log('check-share-text: C2, shares state "Package value" only');

check('SHARE_VALUE_LINE is the existing "Package value" label',
  /export const SHARE_VALUE_LINE = 'Package value';/.test(image));

// The share image: no TOTAL row and no total props.
check('the share image has no TOTAL row', !/>TOTAL</.test(image) && !/styles\.totalRow/.test(image));
check('the share image takes no totals', !/sendTotal|receiveTotal/.test(image));

const shareCode = [
  ['the calculator\'s share image', elements(calc)],
  ['the in-league share image', elements(league)],
  ['the calculator\'s text share', [region(calc, 'const shareTrade = async', 'const liveReady')]],
];
for (const [where, regions] of shareCode) {
  check(`${where} is found`, regions.length > 0 && regions.every((r) => r.length > 0),
    'the region moved: update this check');
  for (const r of regions) {
    for (const banned of BANNED) {
      check(`${where} has no "${banned}"`, !r.includes(banned));
    }
    check(`${where} states SHARE_VALUE_LINE`, r.includes('SHARE_VALUE_LINE'));
  }
}
for (const [where, regions] of shareCode.slice(0, 2)) {
  for (const r of regions) {
    check(`${where} passes verdictLine={SHARE_VALUE_LINE}`, r.includes('verdictLine={SHARE_VALUE_LINE}'));
  }
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
