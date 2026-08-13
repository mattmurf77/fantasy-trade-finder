#!/usr/bin/env node
// #307 structural pins on LeagueScreen.tsx (plain-node source grep). HONEST
// LABEL (G-035): presence proofs, not behavior — the end-to-end scoped
// landing is the Maestro flow league/07-matches-tile-scoped.yaml's job
// (which also needs the Matches group's §4.3 receiver).
//
//   S7 — a tile's navigate drops `leagueId` (ships the half-fix: "Mutual
//        matches" scopes, "Awaiting them" quietly doesn't — the exact way
//        this item would come back as next wave's report) or drops `at`
//        (re-taps stop re-firing the param effect, FB-91 regression).
//   S8 — a tile loses its testID, breaking the flow silently at its entry.
//
// Comments are stripped before matching so a param that survives only in
// prose cannot pass.
//
// Run: node tests/check-matches-tile-league-param.js

'use strict';

const fs = require('fs');
const path = require('path');

const srcPath = path.join(__dirname, '..', 'src', 'screens', 'LeagueScreen.tsx');
const raw = fs.readFileSync(srcPath, 'utf8');
const code = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

// ── S7: BOTH Matches navigations carry the full §4.3 param shape ─────────
// Every navigate('Matches', {…}) in this file must send segment + leagueId
// + at. Matching all call sites (not two hand-picked ones) means a THIRD
// tile added later without the league param fails here too.
const navCalls = [...code.matchAll(/navigate\(\s*'Matches'\s*,\s*\{([^}]*)\}/g)];
assert(
  navCalls.length === 2,
  `S7 exactly two navigate('Matches', …) call sites (found ${navCalls.length})`,
  'a tile was removed, or a new Matches navigation appeared — re-pin deliberately',
);
for (const m of navCalls) {
  const params = m[1];
  const seg = (params.match(/segment:\s*'(\w+)'/) || [])[1] || '<none>';
  assert(
    /segment:/.test(params) && /\bleagueId\b/.test(params) && /\bat:/.test(params),
    `S7 navigate('Matches', {segment: '${seg}', …}) carries segment + leagueId + at`,
    `params were: {${params.trim()}}`,
  );
}
const segments = navCalls.map((m) => (m[1].match(/segment:\s*'(\w+)'/) || [])[1]).sort();
assert(
  JSON.stringify(segments) === JSON.stringify(['awaiting', 'mutual']),
  "S7 the two call sites are the 'mutual' and 'awaiting' tiles",
  `segments seen: ${JSON.stringify(segments)}`,
);

// ── S8: both tiles carry the testIDs the Maestro flow enters through ─────
for (const id of ['league.matches-mutual-tile', 'league.matches-awaiting-tile']) {
  assert(
    code.includes(`testID="${id}"`),
    `S8 tile testID present: ${id}`,
    'flows/league/07-matches-tile-scoped.yaml taps this id',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All matches-tile-league-param checks passed.');
