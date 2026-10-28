#!/usr/bin/env node
// Pick-assignment season guard (C5, flag `picks.assign`).
//
// WHY THIS EXISTS. The ESPN pick-assignment screen used to infer the league's
// season from `data.seasons[0]`, because the GET always started at the
// current season. Under C5 that stops being true: once the league's rookie
// draft reads drafted, the server hides the spent class and `seasons[]`
// starts at season + 1. Inferring "current" from the first tab would then:
//   * label the 2027 tab with draft POSITIONS ("1.08"), which #273 forbids
//     for any future class (ESPN never ran that draft, so a slot number
//     there is fiction); and
//   * once labels are fixed, hide the order/rounds "change" link on EVERY
//     tab, because #273 gated it on "not a future tab". That link is the
//     only way back into setup once a board is seeded, and re-saving setup
//     is how a drafted grid seeds its 4th class.
//
// So three wirings are pinned:
//   1. `api/pickAssignment.ts` declares `current_season` on the GET payload.
//   2. The screen's `currentSeason` reads `data.current_season` FIRST, with
//      `seasons[0]` only as the fallback for an older server.
//   3. The edit-order link's gate keys on the FIRST VISIBLE tab
//      (`data.seasons[0]`), never on `isFutureSeasonTab`.
//
// HONEST LABEL (G-035): this proves the PRESENCE of those exact wirings in
// source text (comments stripped). It does not render the screen or prove
// runtime behavior; the TestFlight checklist in
// docs/plans/draft-extensions/scope-espn-grid-drafted-class.md covers that.
//
// Dependency-free: plain node + fs + regex.
// Run: node tests/check-pick-assignment-season.js
//   (or: npm run test:pick-assignment-season)

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

/** Source with block and line comments removed, so a comment can neither
 *  satisfy nor break a check. Keeps `https://` (a `:` before `//`). */
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}
const squash = (s) => s.replace(/\s+/g, ' ').trim();

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

// ── 1. The payload type declares `current_season`. ─────────────────────────
const api = stripComments(read('src/api/pickAssignment.ts'));
const iface = api.match(/export interface PickAssignments \{([\s\S]*?)\n\}/);
assert(!!iface, 'pickAssignment.ts exports interface PickAssignments');
assert(
  !!iface && /\bcurrent_season\?\s*:\s*number\s*;/.test(iface[1]),
  'PickAssignments declares `current_season?: number`',
);

// ── 2. The screen reads the league season from the payload first. ──────────
const screen = stripComments(read('src/screens/PickAssignmentScreen.tsx'));
const decls = screen.match(/const currentSeason\s*=[^;]*;/g) || [];
assert(decls.length === 1, 'exactly one `const currentSeason` declaration',
  `found ${decls.length}`);
assert(
  decls.length === 1 &&
    /^const currentSeason\s*=\s*data\.current_season\s*\?\?/.test(decls[0]),
  'currentSeason reads `data.current_season` first',
  decls[0] ? squash(decls[0]) : 'missing',
);

// ── 3. The edit-order gate keys on the first visible tab. ───────────────────
const gate = screen.match(
  /\{\s*([^{}]*?)\s*\?\s*\(\s*<Pressable\s+testID="pick-assignment\.edit-order"/,
);
assert(!!gate, 'edit-order link sits behind one `cond ? (...)` gate');
const cond = gate ? squash(gate[1]) : '';
assert(
  cond === 'season?.season === data.seasons[0]?.season',
  'edit-order gate is `season?.season === data.seasons[0]?.season`',
  cond || 'missing',
);
assert(
  !!gate && !/isFutureSeasonTab/.test(cond),
  'edit-order gate does not key on isFutureSeasonTab',
  cond || 'missing',
);

if (failures) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll pick-assignment season checks passed.');
