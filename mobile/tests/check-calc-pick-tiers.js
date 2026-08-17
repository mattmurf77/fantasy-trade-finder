#!/usr/bin/env node
// #320 (D-320-1/D-320-3) — pick rows carry tier badges on calculator
// surfaces; the share image deliberately does not.
//
// WHY THIS EXISTS. The fix threads a SERVER-computed tier (OwnedPick.tier,
// GET /api/league/picks) through the existing tierById → tierOf →
// TierBadge machinery by (a) merging pick tiers into the memo and (b)
// deleting the #263-era `p.pos === 'PICK' ? null` carve-out at all four
// tierOf call sites. A partial fix — picker relabelled, TradeSide rows
// still numeric — renders the EXACT defect #320 reports on the same
// screen, compiles clean, and demos fine in a picker-only look. And the
// invariant that tiers are never derived client-side from a display value
// (docs/cross-client-invariants.md, the #263 scale-confusion bug) only
// holds if the merge reads the server field. Each assertion names the
// sabotage it detects.
//
// Run: node tests/check-calc-pick-tiers.js

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

const calc = stripComments(read('src/components/InLeagueCalculator.tsx'));
const league = stripComments(read('src/api/league.ts'));

// ── The wire type: OwnedPick carries the server tier (absent → fallback).
const ownedPick = league.slice(
  league.indexOf('interface OwnedPick'),
  league.indexOf('interface LeaguePicksResponse'),
);
assert(
  /tier\?:\s*Tier \| null;/.test(ownedPick),
  'OwnedPick models server-computed tier?: Tier | null',
);

// ── The merge: tierById folds pick tiers from the picks payload, reading
// the SERVER field — never deriving from pool_value client-side.
const memoIdx = calc.indexOf('const tierById');
const memoRegion = calc.slice(memoIdx, calc.indexOf('const playerById'));
assert(memoIdx !== -1, 'tierById memo present');
assert(
  memoRegion.includes('picksQ.data?.all_picks'),
  'tierById merges from picksQ all_picks',
);
assert(
  /m\[p\.pick_id\] = p\.tier/.test(memoRegion),
  'pick tier read from the server field p.tier (never derived client-side)',
);

// ── Sabotage "picker-only fix": one surface relabelled, the other left
// nulling picks. All four tierOf call sites must resolve picks and
// players identically through tierById.
const tradeSideSites = calc.match(/tierOf=\{\(p\) => tierById\[p\.id\] \?\? null\}/g) || [];
const pickerSites = calc.match(/tierOf=\{\(p: CalcPlayer\) => tierById\[p\.id\] \?\? null\}/g) || [];
assert(
  tradeSideSites.length === 2,
  'both TradeSide mounts resolve pick tiers',
  `found ${tradeSideSites.length}`,
);
assert(
  pickerSites.length === 2,
  'both PlayerPickerModal mounts resolve pick tiers',
  `found ${pickerSites.length}`,
);

// ── D-320-3: the share image is the ONE surface where picks stay numeric
// (#277/#280 stands). Exactly one 'PICK' → null special case may survive,
// and it must live inside shareAssets.
const pickNulls = [];
let at = -1;
while ((at = calc.indexOf("'PICK' ? null", at + 1)) !== -1) pickNulls.push(at);
assert(
  pickNulls.length === 1,
  "exactly one 'PICK' ? null special case survives (the share card)",
  `found ${pickNulls.length}`,
);
const shareStart = calc.indexOf('const shareAssets');
const shareEnd = calc.indexOf('const bothSides');
assert(
  pickNulls.length === 1 &&
    shareStart !== -1 &&
    pickNulls[0] > shareStart &&
    pickNulls[0] < shareEnd,
  "the surviving 'PICK' ? null lives inside shareAssets (D-320-3)",
);

process.exit(failures ? 1 : 0);
