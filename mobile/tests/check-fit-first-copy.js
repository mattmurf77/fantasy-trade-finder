#!/usr/bin/env node
// WS4 fit-first card copy guard (docs/plans/offer-learnings/scope-fit-first-copy.md).
//
// WHY THIS EXISTS. The server composes at most one fit line per side
// (`fit_lines`, backend/trade_narrative.py fit_lines) behind the default-off
// flag `trade.fit_first_copy`. The card has to LEAD with them: the operator's
// ask was "card copy opens with why the trade suits the other team and the
// viewer's team, and puts the value line second". D-056 retired the simulator,
// so the order and the gates are pinned here instead.
//
// What is pinned:
//   1. TradeCard reads the flag `trade.fit_first_copy` and hides the lines on
//      an edited card (they describe the original package).
//   2. The fit block sits directly under the header: before the standing-offer
//      line, the consensus note, Match strength, the player sides, the value
//      bar and the bottom reasons list.
//   3. The other team's row comes before the viewer's row; both testIDs exist.
//   4. The block renders the server text only: no `code` read, no copy of its
//      own (no string literal between the tags).
//   5. The new styles are token-based (no hex literal).
//   6. The wire type declares `fit_lines` optional with side/code/text.
//   7. The normalizer validates each line and adds the key only when at least
//      one line passes (absent otherwise, so legacy payloads are unchanged).
//   8. `npm run test:fit-first-copy` exists.
//
// Run: node tests/check-fit-first-copy.js   (or: npm run test:fit-first-copy)

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const CARD = path.join(ROOT, 'src/components/TradeCard.tsx');
const TYPES = path.join(ROOT, 'src/shared/types.ts');
const API = path.join(ROOT, 'src/api/trades.ts');
const PKG = path.join(ROOT, 'package.json');

const failures = [];
const checks = [];
function ok(name) { checks.push(name); }
function fail(name, detail) { failures.push(`${name}\n      ${detail}`); }
function read(p) {
  if (!fs.existsSync(p)) { fail('file exists', `missing: ${path.relative(ROOT, p)}`); return ''; }
  return fs.readFileSync(p, 'utf8');
}
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}
function balanced(src, openIdx, open, close) {
  if (src[openIdx] !== open) return '';
  let depth = 0;
  for (let i = openIdx; i < src.length; i++) {
    if (src[i] === open) depth++;
    else if (src[i] === close) { depth--; if (depth === 0) return src.slice(openIdx, i + 1); }
  }
  return '';
}

const card = stripComments(read(CARD));
const types = stripComments(read(TYPES));
const api = stripComments(read(API));

// 1. Flag read + edited gate.
{
  const name = '1. card reads trade.fit_first_copy and hides lines on an edited card';
  if (!/useFlag\(\s*'trade\.fit_first_copy'\s*\)/.test(card)) {
    fail(name, "no useFlag('trade.fit_first_copy') in TradeCard.tsx");
  } else if (!/fitFirstEnabled\s*&&\s*!data\.edited\s*\?\s*data\.fit_lines\s*:\s*undefined/.test(card)) {
    fail(name, 'fit lines must be read as `fitFirstEnabled && !data.edited ? data.fit_lines : undefined`');
  } else ok(name);
}

// Locate the block.
const BLOCK_ID = 'testID="trade-card.fit-lines"';
const blockAt = card.indexOf(BLOCK_ID);
let block = '';
{
  const gate = card.lastIndexOf('{fitThem || fitYou ? (', blockAt);
  if (blockAt >= 0 && gate >= 0) block = balanced(card, card.indexOf('(', gate + 1), '(', ')');
}

// 2. Order: fit block leads.
{
  const name = '2. fit block renders under the header, before every value surface';
  const header = card.indexOf('style={styles.header}');
  const later = [
    ['standing-offer line', 'testID="trade-card.standing-offer-reason"'],
    ['consensus note', 'testID="trade-card.consensus-note"'],
    ['Match strength', '<StrengthBar'],
    ['player sides', '<TickLabel>YOU SEND</TickLabel>'],
    ['value bar', '<TradeValueBar'],
    ['reasons list', '{showReasons && ('],
  ];
  if (blockAt < 0 || !block) fail(name, `no ${BLOCK_ID} block gated on \`{fitThem || fitYou ? (\``);
  else if (header < 0 || header > blockAt) fail(name, 'the fit block must come after the header');
  else {
    const bad = later.filter(([, needle]) => { const i = card.indexOf(needle); return i < 0 || i < blockAt; });
    if (bad.length) fail(name, `these must exist and come after the fit block: ${bad.map((b) => b[0]).join(', ')}`);
    else ok(name);
  }
}

// 3. Them before you.
{
  const name = "3. the other team's row precedes the viewer's row";
  const them = block.indexOf('testID="trade-card.fit-line.them"');
  const you = block.indexOf('testID="trade-card.fit-line.you"');
  if (them < 0 || you < 0) fail(name, 'both trade-card.fit-line.them and trade-card.fit-line.you must be in the block');
  else if (them > you) fail(name, 'them row must come first');
  else if (!/\{fitThem\}/.test(block.slice(them, you)) || !/\{fitYou\}/.test(block.slice(you))) {
    fail(name, 'the them row must render {fitThem} and the you row {fitYou}');
  } else ok(name);
}

// 4. Server text only.
{
  const name = '4. block renders server text only (no code read, no own copy)';
  const textBetweenTags = block.match(/>\s*([A-Za-z][^<>{}]*?)\s*</g) || [];
  if (/\.code\b/.test(card)) fail(name, 'TradeCard must never read a fit line `code`');
  else if (textBetweenTags.length) fail(name, `literal copy in the block: ${textBetweenTags.join(' ')}`);
  else if (!/\.find\(\(l\)\s*=>\s*l\.side\s*===\s*'them'\)\?\.text/.test(card)
           || !/\.find\(\(l\)\s*=>\s*l\.side\s*===\s*'you'\)\?\.text/.test(card)) {
    fail(name, 'fitThem/fitYou must be the `text` of the them/you line');
  } else ok(name);
}

// 5. Token styles.
{
  const name = '5. fit styles are token-based';
  const m = card.match(/fitLines:\s*\{[^}]*\},\s*fitLineText:\s*\{[^}]*\}/);
  if (!m) fail(name, 'styles.fitLines / styles.fitLineText not found');
  else if (/#[0-9a-fA-F]{3,8}\b/.test(m[0])) fail(name, 'hex literal in fit styles');
  else ok(name);
}

// 6. Wire type.
{
  const name = '6. wire type declares fit_lines optional';
  if (!/fit_lines\?:\s*\{\s*side:\s*'them'\s*\|\s*'you';\s*code:\s*string;\s*text:\s*string\s*\}\[\];/.test(types)) {
    fail(name, "TradeCard type needs `fit_lines?: { side: 'them' | 'you'; code: string; text: string }[];`");
  } else ok(name);
}

// 7. Normalizer.
{
  const name = '7. normalizer validates lines and omits the key when none pass';
  if (!/Array\.isArray\(raw\?\.fit_lines\)/.test(api)
      || !/l\?\.side === 'them' \|\| l\?\.side === 'you'/.test(api)
      || !/typeof l\?\.text === 'string' && l\.text\.length > 0/.test(api)) {
    fail(name, 'normalizeTradeCard must validate raw.fit_lines side/code/text');
  } else if (!/\.\.\.\(fitLines\.length \? \{ fit_lines: fitLines \} : \{\}\)/.test(api)) {
    fail(name, 'fit_lines must be spread in only when non-empty');
  } else ok(name);
}

// 8. npm script.
{
  const name = '8. npm run test:fit-first-copy exists';
  const pkg = JSON.parse(read(PKG) || '{}');
  if ((pkg.scripts || {})['test:fit-first-copy'] !== 'node tests/check-fit-first-copy.js') {
    fail(name, 'add "test:fit-first-copy": "node tests/check-fit-first-copy.js" to mobile/package.json');
  } else ok(name);
}

for (const c of checks) console.log(`  ok  ${c}`);
if (failures.length) {
  for (const f of failures) console.error(`  FAIL ${f}`);
  console.error(`\ncheck-fit-first-copy: ${failures.length} failed, ${checks.length} passed`);
  process.exit(1);
}
console.log(`\ncheck-fit-first-copy: all ${checks.length} checks passed`);
