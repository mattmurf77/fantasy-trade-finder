#!/usr/bin/env node
// Playoff-outlook band invariant guard (#169; flag `outlook.odds`).
//
// WHY THIS EXISTS. `outlook.odds` was flipped to TRUE on 2026-08-19 by
// operator override (D-094, reversing D-093). Until that moment every rule
// in `docs/cross-client-invariants.md` § "Playoff outlook bands" was
// protected by the flag being dark — nothing rendered, so nothing could
// render wrongly. Lighting the flag removes that protection and makes the
// invariant load-bearing for the first time, on a surface no runtime test
// covers: D-056 retired Maestro and the simulator, and the operator
// explicitly waived the Maestro flow this lighting used to owe. This file is
// what replaces it.
//
// The two rules it guards are NOT style preferences:
//
//   • `title_pct` is unrenderable at any week, in any form, banded or
//     numeric. That is an absence of demonstrated skill, not a calibration
//     judgement — pooled skill +4.2%, 90% CI [-13.1%, +20.0%]; 3 of 6
//     backtested league-seasons score worse than climatology; 8 predictions
//     above 0.4 contain one champion between them
//     (docs/feedback/items/169-outlook-league-summary/
//      calibration-combined-2026-08-10.md §9).
//
//   • `playoff_pct` renders ONLY as the three-band chip. The engine is
//     over-confident at the extremes — a 95% preseason call realizes 78% —
//     so three bands are the finest granularity the evidence supports (§7).
//
// What is pinned:
//   1. The two band thresholds are exactly 0.65 and 0.35.
//   2. The band→color map uses the pos/warn/neg SEMANTIC tokens (never tier
//      or position hexes), and every band ships a text label beside the
//      color (color alone fails a color-blind read).
//   3. `playoffBand` buckets top-down, so a boundary value belongs to the
//      HIGHER band (exactly 0.65 is `likely`, exactly 0.35 is `tossup`).
//   4. No client source file reads `title_pct` for display. The field may be
//      declared in the API type (it IS served) but must never be rendered.
//   5. `OUTLOOK_WEEK6_PERCENT_ENABLED` is still `false` — lighting the flag
//      is not lighting the bare percentage, which is a separate operator
//      risk call on pooled, non-week-stratified calibration.
//
// Run: node tests/check-outlook-bands.js
//   (or: npm run test:outlook-bands)
//
// NOTE: CI picks this file up automatically — `.github/workflows/ci.yml`'s
// mobile-typecheck job globs `tests/check-*.js`. No CI edit is needed.

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCREEN = path.join(ROOT, 'src/screens/LeagueSummaryScreen.tsx');
const API = path.join(ROOT, 'src/api/league.ts');

const failures = [];
const checks = [];

function ok(name) { checks.push(name); }
function fail(name, detail) { failures.push(`${name}\n      ${detail}`); }

function read(p) {
  if (!fs.existsSync(p)) {
    fail('file exists', `missing: ${path.relative(ROOT, p)}`);
    return '';
  }
  return fs.readFileSync(p, 'utf8');
}

const screen = read(SCREEN);
const api = read(API);

// ── 1. Thresholds ─────────────────────────────────────────────────────────
{
  const likely = screen.match(/PLAYOFF_BAND_LIKELY_MIN\s*=\s*([0-9.]+)/);
  const unlikely = screen.match(/PLAYOFF_BAND_UNLIKELY_MAX\s*=\s*([0-9.]+)/);
  if (!likely || !unlikely) {
    fail('1. thresholds declared',
      'PLAYOFF_BAND_LIKELY_MIN / PLAYOFF_BAND_UNLIKELY_MAX not found in LeagueSummaryScreen.tsx');
  } else if (likely[1] !== '0.65' || unlikely[1] !== '0.35') {
    fail('1. thresholds are 0.65 / 0.35',
      `found LIKELY_MIN=${likely[1]}, UNLIKELY_MAX=${unlikely[1]} — ` +
      'these are a cross-client invariant; changing them requires updating ' +
      'docs/cross-client-invariants.md and every client mirror in the same commit');
  } else {
    ok('1. band thresholds are 0.65 / 0.35');
  }
}

// ── 2. Semantic colors + a label per band ─────────────────────────────────
{
  const colorBlock = screen.match(/PLAYOFF_BAND_COLOR[^=]*=\s*{([\s\S]*?)}/);
  const labelBlock = screen.match(/PLAYOFF_BAND_LABEL[^=]*=\s*{([\s\S]*?)}/);
  if (!colorBlock || !labelBlock) {
    fail('2. band color + label maps exist',
      'PLAYOFF_BAND_COLOR / PLAYOFF_BAND_LABEL not found');
  } else {
    const body = colorBlock[1];
    const usesSemantic =
      /semantic\.pos/.test(body) && /semantic\.warn/.test(body) && /semantic\.neg/.test(body);
    if (!usesSemantic) {
      fail('2. bands use semantic pos/warn/neg tokens',
        'PLAYOFF_BAND_COLOR must map likely→semantic.pos, tossup→semantic.warn, ' +
        'unlikely→semantic.neg — not tier or position hexes, and not raw hex literals');
    } else {
      ok('2a. band colors are the semantic tokens');
    }
    const bands = ['likely', 'tossup', 'unlikely'];
    const missing = bands.filter((b) => !new RegExp(`\\b${b}\\b`).test(labelBlock[1]));
    if (missing.length) {
      fail('2b. every band ships a text label',
        `PLAYOFF_BAND_LABEL missing: ${missing.join(', ')} — the label always ships ` +
        'beside the color; color alone fails a color-blind read');
    } else {
      ok('2b. every band ships a text label');
    }
  }
}

// ── 3. Top-down bucketing (boundaries belong to the higher band) ──────────
{
  const fn = screen.match(/function\s+playoffBand\s*\([\s\S]*?\n}/);
  if (!fn) {
    fail('3. playoffBand exists', 'function playoffBand(...) not found');
  } else {
    const body = fn[0];
    const likelyGte = />=\s*PLAYOFF_BAND_LIKELY_MIN/.test(body);
    const unlikelyLt = /<\s*PLAYOFF_BAND_UNLIKELY_MAX/.test(body);
    if (!likelyGte || !unlikelyLt) {
      fail('3. boundaries belong to the higher band',
        'playoffBand must test `>= PLAYOFF_BAND_LIKELY_MIN` and `< PLAYOFF_BAND_UNLIKELY_MAX` ' +
        'so exactly 0.65 is `likely` and exactly 0.35 is `tossup`. ' +
        'Flipping either comparison silently moves every boundary case one band.');
    } else {
      ok('3. boundaries belong to the higher band');
    }
  }
}

// ── 4. title_pct is never rendered ────────────────────────────────────────
{
  // The field is legitimately DECLARED in the API type (it is served) and
  // discussed in comments. What must never exist is a read of it in client
  // code. Strip comments and the type declaration, then look for any use.
  const stripped = screen
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
  const hits = [];
  const re = /title_pct/g;
  let m;
  while ((m = re.exec(stripped)) !== null) {
    const line = stripped.slice(0, m.index).split('\n').length;
    hits.push(line);
  }
  if (hits.length) {
    fail('4. title_pct is never read by the screen',
      `found ${hits.length} non-comment reference(s) in LeagueSummaryScreen.tsx. ` +
      'title_pct is unrenderable at any week in any form — banded or numeric — ' +
      'because the model has no demonstrated skill (CI spans zero). ' +
      'It is served so the backend need not special-case it, never to be shown.');
  } else {
    ok('4. title_pct is never read by the screen');
  }

  // The API type may declare it; assert it is at least documented as unrenderable
  // so the next reader does not "fix" its absence from the UI.
  if (api && /title_pct/.test(api) && !/UNRENDERABLE|never shown|never be shown/i.test(api)) {
    fail('4b. api/league.ts warns that title_pct is unrenderable',
      'league.ts declares title_pct without a comment saying it must never be rendered — ' +
      'that comment is the only thing standing between the field and a well-meaning UI change');
  } else {
    ok('4b. api/league.ts warns that title_pct is unrenderable');
  }
}

// ── 5. The week-6 bare percentage stays off ───────────────────────────────
{
  const m = screen.match(/OUTLOOK_WEEK6_PERCENT_ENABLED\s*=\s*(true|false)/);
  if (!m) {
    fail('5. OUTLOOK_WEEK6_PERCENT_ENABLED declared',
      'constant not found — it is the switch that keeps bare percentages off');
  } else if (m[1] !== 'false') {
    fail('5. OUTLOOK_WEEK6_PERCENT_ENABLED is false',
      'set to true. Lighting `outlook.odds` is NOT lighting the bare percentage: ' +
      'that is a separate operator risk call on pooled, non-week-stratified ' +
      'calibration. If the operator has taken it, update this guard in the same commit.');
  } else {
    ok('5. OUTLOOK_WEEK6_PERCENT_ENABLED is false');
  }
}

// ── Report ────────────────────────────────────────────────────────────────
console.log(`\ncheck-outlook-bands: ${checks.length} passed, ${failures.length} failed`);
for (const c of checks) console.log(`  ✓ ${c}`);
if (failures.length) {
  console.error('\nFAILURES:');
  for (const f of failures) console.error(`  ✗ ${f}`);
  console.error(
    '\nThese are cross-client invariants (docs/cross-client-invariants.md ' +
    '§ "Playoff outlook bands"), not preferences. If a change here is ' +
    'genuinely intended, update the invariant doc, every client mirror, and ' +
    'this guard in the SAME commit.\n');
  process.exit(1);
}
console.log('');
