#!/usr/bin/env node
// Matches' segment control and League rankings' basis chips fit a 375pt
// screen without clipping.
//
// WHY THIS EXISTS. Release simulator pass (2026-11-22, 402pt): Matches'
// "MUTUAL MATCHES 3 / AWAITING THEM 2 / STANDING OFFERS 0" ran edge to edge
// and the third was cut off mid-count — three flex:1 segments with
// overflow:hidden, each label wider than its third. On League rankings the
// basis chips read "CONSENSUS SORTS / MY BOARD SORTS / REDRAFT (S…" for one
// account and "CONSENSUS / MY BOARD / REDRAFT (SOON)" for another: the
// "… sorts" wording appears only when both boards are loaded and differ
// (#248, `boardsDiffer`), and the content-sized chips in a no-wrap row ran
// off the right edge.
//
// Pinned (layout ARITHMETIC over the source, plus structure):
//   (m1) Each Matches <SegmentBtn label="…"> with a two-digit count, set in
//        the `type.label` token read from theme/chalkline.ts (size, letter
//        spacing, uppercase), fits its third of a 375pt screen less the
//        row's margins, border and the segment's own horizontal padding.
//   (m2) VoiceOver still hears the full names (a11yName).
//   (l1) League's basis row: if the three chips, at their WIDEST labels
//        (the "… sorts" set), don't fit one 375pt line, `basisRow` must wrap.
//
// HONEST LABEL (G-035): widths are an ESTIMATE, not a measurement. Glyph
// advances are conservative per-class constants (upper-case 0.70em, digits
// 0.62em, space 0.28em, parentheses 0.34em) — wider than Archivo SemiBold's
// real average — so a pass means "fits with margin", and a label this check
// calls too wide may in fact squeeze in. The runtime proof is the simulator
// at 375pt (iPhone SE / 13 mini class) and at the largest Dynamic Type.
//
// Run: node tests/check-segment-labels-fit.js   (or: npm run test:segment-labels-fit)

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
let failures = 0;
const assert = (cond, name, detail) => {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
};

const SCREEN_W = 375;
const THEME = read('src/theme/chalkline.ts');
const num = (src, re, what) => {
  const m = src.match(re);
  if (!m) throw new Error(`could not read ${what}`);
  return Number(m[1]);
};
const spaceTok = (k) => num(THEME, new RegExp(`\\n\\s*${k}: (\\d+),`), `space.${k}`);
const labelBlock = THEME.slice(THEME.indexOf('  label: {'), THEME.indexOf('}', THEME.indexOf('  label: {')));
const LABEL_SIZE = num(labelBlock, /fontSize: (\d+)/, 'type.label fontSize');
const LABEL_TRACK = num(labelBlock, /letterSpacing: ([\d.]+)/, 'type.label letterSpacing');
const UPPER = /textTransform: 'uppercase'/.test(labelBlock);

function textWidth(s, size, track) {
  let w = 0;
  for (const ch of s) {
    let em;
    if (/[0-9]/.test(ch)) em = 0.62;
    else if (ch === ' ') em = 0.28;
    else if (ch === '(' || ch === ')') em = 0.34;
    else em = 0.70;
    w += em * size + track;
  }
  return w;
}
const resolveSpace = (expr) => {
  const m = String(expr).match(/^space\.(\w+)$/);
  return m ? spaceTok(m[1]) : Number(expr);
};
function styleProp(src, styleName, prop) {
  const i = src.indexOf(`  ${styleName}: {`);
  if (i === -1) return undefined;
  const body = src.slice(i, src.indexOf('}', i));
  const m = body.match(new RegExp(`\\b${prop}: ([^,\\n]+)`));
  return m ? m[1].trim() : undefined;
}

// ── Matches ───────────────────────────────────────────────────────────────
{
  const SRC = read('src/screens/MatchesScreen.tsx');
  const labels = [...SRC.matchAll(/<SegmentBtn\s+label="([^"]+)"/g)].map((m) => m[1]);
  assert(labels.length === 3, 'm0. Matches renders three SegmentBtn labels', JSON.stringify(labels));
  const rowMargin = resolveSpace(styleProp(SRC, 'segmentRow', 'marginHorizontal') || 0);
  const rowBorder = Number(styleProp(SRC, 'segmentRow', 'borderWidth') || 0);
  const pad = resolveSpace(styleProp(SRC, 'segmentBtn', 'paddingHorizontal') || 0);
  const gap = resolveSpace(styleProp(SRC, 'segmentInner', 'gap') || 0);
  const countSize = Number(styleProp(SRC, 'segmentCount', 'fontSize') || LABEL_SIZE);
  const third = (SCREEN_W - 2 * rowMargin - 2 * rowBorder) / 3 - 2 * pad;
  for (const label of labels) {
    const shown = UPPER ? label.toUpperCase() : label;
    const w = textWidth(shown, LABEL_SIZE, LABEL_TRACK) + gap + textWidth('12', countSize, 0);
    assert(w <= third,
      `m1. "${shown} 12" fits a third of ${SCREEN_W}pt (${w.toFixed(1)} ≤ ${third.toFixed(1)}pt)`);
  }
  const names = [...SRC.matchAll(/<SegmentBtn\s+label="[^"]+"\s+a11yName="([^"]+)"/g)].map((m) => m[1]);
  assert(
    JSON.stringify(names) === JSON.stringify(['Mutual matches', 'Awaiting them', 'Standing offers'])
      && /\$\{a11yName \?\? label\}, \$\{count\}/.test(SRC),
    'm2. VoiceOver keeps the full names (a11yName → accessibilityLabel)',
    JSON.stringify(names),
  );
}

// ── League rankings basis chips ───────────────────────────────────────────
{
  const SRC = read('src/screens/LeagueSummaryScreen.tsx');
  const widest = [];
  for (const id of ['consensus', 'personal', 'redraft']) {
    const i = SRC.indexOf(`testID="league-summary.basis.${id}"`);
    const tail = SRC.slice(i, SRC.indexOf('/>', i));
    const lits = [...tail.matchAll(/'([^']+)'|label="([^"]+)"/g)].map((m) => m[1] || m[2]);
    widest.push(lits.sort((a, b) => b.length - a.length)[0] || '');
  }
  const chipPad = resolveSpace(styleProp(SRC, 'basisChip', 'paddingHorizontal') || 0);
  const chipBorder = Number(styleProp(SRC, 'basisChip', 'borderWidth') || 0);
  const rowGap = resolveSpace(styleProp(SRC, 'basisRow', 'gap') || 0);
  const scrollPad = resolveSpace(styleProp(SRC, 'scroll', 'padding') || 0);
  const total = widest
    .map((l) => textWidth(UPPER ? l.toUpperCase() : l, LABEL_SIZE, LABEL_TRACK) + 2 * chipPad + 2 * chipBorder)
    .reduce((a, b) => a + b, 0) + 2 * rowGap;
  const avail = SCREEN_W - 2 * scrollPad;
  const wraps = /^'wrap'$/.test(styleProp(SRC, 'basisRow', 'flexWrap') || '');
  assert(widest.every(Boolean), 'l0. read the three basis chip labels', JSON.stringify(widest));
  assert(total <= avail || wraps,
    `l1. basis chips at their widest (${widest.join(' / ')}) need ${total.toFixed(0)}pt of ${avail}pt: `
      + (total <= avail ? 'they fit one line' : 'so the row must wrap'),
    wraps ? '' : 'basisRow has no flexWrap: \'wrap\', so the third chip clips off the right edge');
}

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll segment-labels-fit checks passed.');
