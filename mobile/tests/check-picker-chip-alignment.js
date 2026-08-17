#!/usr/bin/env node
// #320 (defect A) — left-alignment of pick vs player rows on the
// calculator's picker and TradeSide lists.
//
// WHY THIS EXISTS. PositionChip self-sizes to its text, so a PICK chip
// (4 chars) is wider than QB/RB/WR/TE (2) and pushed pick rows' name
// column right. The fix wraps the chip in a fixed-width slot (chipCol) in
// BOTH row layouts. Nothing here fails loudly: dropping the width from one
// file re-opens the exact reported misalignment on one surface only, and
// the "obvious" alternative — giving the shared PositionChip itself a
// default width — is a drive-by that reshapes Tiers, Trades, and Matches
// rows (coding guideline 3). Each assertion names the sabotage it detects.
//
// Run: node tests/check-picker-chip-alignment.js

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

const FILES = {
  'src/components/PlayerPickerModal.tsx': stripComments(
    read('src/components/PlayerPickerModal.tsx'),
  ),
  'src/components/TradeSide.tsx': stripComments(read('src/components/TradeSide.tsx')),
};

const widths = {};
for (const [rel, src] of Object.entries(FILES)) {
  // The row must render the chip INSIDE the fixed slot.
  assert(
    /styles\.chipCol\}>\s*<PositionChip/.test(src),
    `${rel}: PositionChip wrapped in the chipCol slot`,
  );
  // ── Sabotage "remove the width": chipCol without a numeric width
  // collapses back to self-sizing.
  const m = src.match(/chipCol:\s*\{\s*width:\s*(\d+)\s*,\s*alignItems:\s*'flex-start'\s*\}/);
  assert(!!m, `${rel}: chipCol style carries a numeric width + flex-start`);
  if (m) widths[rel] = Number(m[1]);
}

// The two surfaces share one screen — the slot must be the SAME constant
// in both files or the "one x for every row" claim silently splits.
const vals = Object.values(widths);
assert(
  vals.length === 2 && vals[0] === vals[1],
  'chipCol width identical in both files',
  JSON.stringify(widths),
);

// ── Sabotage "resize the shared chip instead": a width inside
// PositionChip's own styles would fix alignment here by breaking every
// other mount (Tiers/Trades/Matches). The shared chip stays untouched.
const chip = stripComments(read('src/components/PositionChip.tsx'));
const chipStyles = chip.slice(chip.indexOf('StyleSheet.create'));
assert(
  !/\bwidth:/.test(chipStyles),
  'PositionChip.tsx styles carry no width (no drive-by on the shared chip)',
);

process.exit(failures ? 1 : 0);
