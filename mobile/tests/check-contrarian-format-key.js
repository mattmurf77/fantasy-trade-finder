#!/usr/bin/env node
// #308 structural pins on LeagueScreen.tsx (plain-node source grep, same
// class as the other check-*.js pins). HONEST LABEL (G-035): these prove
// PRESENCE of exact wirings, not behavior — behavior is check-league-unlocks
// S1-S4's job. Two regressions each of these makes loud:
//
//   S5 — the contrarian queryKey loses `activeFormat`, re-introducing the
//        latent stale-verdict bug: the /api/league/contrarian response
//        varies with the session's active scoring format, so a key without
//        it serves the OTHER format's verdict for up to 5 minutes after a
//        format toggle (the sibling `progress` key already carries it).
//   S6 — LeagueScreen stops passing foldNeeded/foldFormat from the
//        contrarian payload, silently reverting the fold line to the
//        format-blind fallback copy while everything still typechecks
//        (both props are optional on LeagueProgressModule).
//
// Comments are stripped before matching so a wiring that survives only in
// prose cannot pass, and a deleted wiring cannot hide behind its comment.
//
// Run: node tests/check-contrarian-format-key.js

'use strict';

const fs = require('fs');
const path = require('path');

const srcPath = path.join(__dirname, '..', 'src', 'screens', 'LeagueScreen.tsx');
const raw = fs.readFileSync(srcPath, 'utf8');

// Strip /* … */ and // … comments. Crude (doesn't tokenize strings), but
// none of the pinned patterns can legally appear inside a string literal in
// this file, and false stripping only makes the checks STRICTER.
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

// ── S5: the contrarian queryKey carries the active format ────────────────
assert(
  /queryKey:\s*\['league-contrarian',\s*leagueId,\s*activeFormat\]/.test(code),
  "S5 contrarian queryKey is ['league-contrarian', leagueId, activeFormat]",
  'the key lost activeFormat — a format toggle now serves the other format\'s cached verdict',
);

// ── S6: the fold props are wired from the contrarian payload ─────────────
assert(
  /foldNeeded=\{contrarianQuery\.data\?\.needed\s*\?\?\s*null\}/.test(code),
  'S6 foldNeeded is wired from contrarianQuery.data?.needed',
  'the fold line silently reverts to the format-blind fallback copy',
);
assert(
  /foldFormat=\{contrarianQuery\.data\?\.format\s*\?\?\s*null\}/.test(code),
  'S6 foldFormat is wired from contrarianQuery.data?.format',
  'the fold line loses its format clause — the ffv3 contradiction returns',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All contrarian-format-key checks passed.');
