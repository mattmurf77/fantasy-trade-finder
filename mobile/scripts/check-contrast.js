#!/usr/bin/env node
/*
 * Token-contrast guard (teardown remediation, PRD 08/prd-03).
 * Parses hex tokens out of src/theme/chalkline.ts and asserts WCAG 2.x
 * contrast floors for the pairs the design system commits to
 * (docs/design/design-system.md). Exits non-zero if any pair drops
 * below its floor. Run: `npm run test:contrast`.
 *
 * Deliberately dependency-free (no jest harness in this project).
 */
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '..', 'src', 'theme', 'chalkline.ts'), 'utf8');

// Collect uniquely-named `name: '#rrggbb'` tokens (ink0-3, line*, dim, faint,
// pos/neg/warn are unique). `base`/`on`/`press` collide across chalk/ice/flare,
// so those are resolved by their trailing comment below rather than last-write-wins.
const tok = {};
for (const m of src.matchAll(/([A-Za-z0-9_]+)\s*:\s*'(#[0-9a-fA-F]{6})'/g)) {
  if (['base', 'on', 'press'].includes(m[1])) continue; // ambiguous — resolved by comment
  tok[m[1]] = m[2];
}
// Resolve the colliding names by their design-system comments.
const byComment = (re, fallback) => (src.match(re) || [, fallback])[1];
const chalkBase = byComment(/base:\s*'(#[0-9a-fA-F]{6})',\s*\/\/ primary text/, '#ECEFF4');
const iceBase = byComment(/base:\s*'(#[0-9a-fA-F]{6})',\s*\/\/ primary CTA/, '#56D9EC');
const iceOn = byComment(/on:\s*'(#[0-9a-fA-F]{6})',\s*\/\/ text\/icons on ice fill/, '#071013');

function lum(hex) {
  const c = hex.replace('#', '');
  const ch = [0, 2, 4].map((i) => {
    let v = parseInt(c.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}
function ratio(a, b) {
  const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

// [foreground, background, floor, label]
// Floors: 4.5:1 body text; 3:1 large/bold text and non-text (borders, essential UI).
const CHECKS = [
  [chalkBase, tok.ink0, 4.5, 'chalk.base on ink0'],
  [chalkBase, tok.ink1, 4.5, 'chalk.base on ink1'],
  [chalkBase, tok.ink2, 4.5, 'chalk.base on ink2'],
  [tok.dim, tok.ink0, 4.5, 'chalk.dim on ink0'],
  [tok.dim, tok.ink1, 4.5, 'chalk.dim on ink1'],
  [tok.dim, tok.ink2, 4.5, 'chalk.dim on ink2'],
  [iceBase, tok.ink0, 3.0, 'ice.base on ink0 (non-text/large)'],
  [iceOn, iceBase, 4.5, 'on-ice text on ice fill'],
  [tok.lineStrongA11y, tok.ink0, 3.0, 'lineStrongA11y border on ink0 (non-text)'],
  [tok.lineStrongA11y, tok.ink1, 3.0, 'lineStrongA11y border on ink1 (non-text)'],
  [tok.pos, tok.ink1, 3.0, 'pos on ink1 (non-text/large)'],
  [tok.neg, tok.ink1, 3.0, 'neg on ink1 (non-text/large)'],
  [tok.warn, tok.ink1, 3.0, 'warn on ink1 (non-text/large)'],
];

let failed = 0;
console.log('Chalkline token contrast (floors from docs/design/design-system.md):\n');
for (const [fg, bg, floor, label] of CHECKS) {
  if (!fg || !bg) {
    console.log(`  ??  ${label}: token missing (fg=${fg} bg=${bg})`);
    failed++;
    continue;
  }
  const r = ratio(fg, bg);
  const ok = r >= floor - 1e-9;
  if (!ok) failed++;
  console.log(`  ${ok ? 'ok ' : 'XX '} ${r.toFixed(2)}:1  (floor ${floor}:1)  ${label}  [${fg} on ${bg}]`);
}
console.log('');
if (failed) {
  console.error(`FAIL: ${failed} contrast pair(s) below floor.`);
  process.exit(1);
}
console.log('PASS: all token-contrast floors met.');
