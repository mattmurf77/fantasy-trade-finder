#!/usr/bin/env node
// #303 (D-303-1) — Send-in-Sleeper placement on the in-league calculator.
//
// WHY THIS EXISTS. The fix is a pure JSX block move: the send router now
// renders between the evener rows and the LeagueVerdict card instead of at
// the bottom of the screen. Nothing about the move fails loudly — a revert
// compiles, renders, and demos identically on a half-built trade; a
// duplicate mount (new slot added, old slot forgotten) renders TWO send
// buttons only on a fully-built trade with the send flag on, which no
// typecheck sees. Each assertion names the sabotage it detects.
//
// Run: node tests/check-calc-send-placement.js

'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const ROOT = path.join(__dirname, '..');
function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), 'utf8');
}
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}

const src = stripComments(read('src/components/InLeagueCalculator.tsx'));

// ── Sabotage "duplicate mount": the button renders in both the new slot
// and the old bottom actions block → two JSX mounts.
const mounts = src.match(/<SendInSleeperButton/g) || [];
assert(
  mounts.length === 1,
  'exactly one <SendInSleeperButton> mount',
  `found ${mounts.length}`,
);

// ── Sabotage "revert move": the send block sits back below the verdict.
const sendIdx = src.indexOf('<SendInSleeperButton');
const verdictIdx = src.indexOf('<LeagueVerdict');
assert(sendIdx !== -1, '<SendInSleeperButton> present');
assert(verdictIdx !== -1, '<LeagueVerdict> present');
assert(
  sendIdx !== -1 && verdictIdx !== -1 && sendIdx < verdictIdx,
  'send button renders BEFORE the LeagueVerdict block',
  `send at ${sendIdx}, verdict at ${verdictIdx}`,
);

// ── D-303-1's other half: ONLY the send button moved. Share (renders the
// verdict into the PNG) and the destructive Clear stay end-of-flow, i.e.
// after the verdict.
const shareIdx = src.indexOf('<ShareTradeImage');
const clearIdx = src.indexOf('"Clear trade"');
assert(
  shareIdx > verdictIdx,
  'ShareTradeImage stays below the verdict',
  `share at ${shareIdx}, verdict at ${verdictIdx}`,
);
assert(
  clearIdx > verdictIdx,
  'Clear trade stays below the verdict',
  `clear at ${clearIdx}, verdict at ${verdictIdx}`,
);

// ── The moved mount keeps its render condition: send needs BOTH sides and
// a resolved opponent (the old block's exact guard).
const sendRegion = src.slice(Math.max(0, sendIdx - 200), sendIdx);
assert(
  /bothSides && opponentId \?/.test(sendRegion),
  'moved mount keeps the bothSides && opponentId guard',
);

process.exit(failures ? 1 : 0);
