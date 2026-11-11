#!/usr/bin/env node
// WS8 revised-offer card guard (docs/plans/offer-learnings/scope-revised-offer-cards.md).
//
// WHY THIS EXISTS. When Sleeper shows the user's own offer declined (or their
// declined counter), the server leads the deck with one revised card carrying
// `revised_offer: {kind, line}` (flag `trade.next_move`). The card must say so
// plainly, first, in the server's words. D-056 retired the simulator, so the
// shape is pinned here:
//   1. The wire type declares `revised_offer` optional with kind
//      ('revision' | 'middle_ground') and line.
//   2. The normalizer validates it and adds the key only when valid (absent
//      otherwise, so legacy payloads are unchanged).
//   3. TradeCard double-gates on `trade.next_move` and hides the line on an
//      edited card (it describes the original package).
//   4. The block renders the server's line only (no client copy, no `kind`
//      read for text).
//   5. It sits under the header and before the fit lines and every value
//      surface.
//   6. Token-only styles (no hex literal); testIDs exist.
//   7. `npm run test:revised-offer-card` exists.
//
// Run: node tests/check-revised-offer-card.js

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const CARD = path.join(ROOT, 'src/components/TradeCard.tsx');
const TYPES = path.join(ROOT, 'src/shared/types.ts');
const API = path.join(ROOT, 'src/api/trades.ts');
const PKG = path.join(ROOT, 'package.json');

const failures = [];
let passed = 0;
function check(name, cond, detail) {
  if (cond) passed++;
  else failures.push(`${name}${detail ? `\n      ${detail}` : ''}`);
}
function read(p) {
  if (!fs.existsSync(p)) { failures.push(`missing: ${path.relative(ROOT, p)}`); return ''; }
  return fs.readFileSync(p, 'utf8');
}
function stripComments(src) {
  return src.replace(/\{\/\*[\s\S]*?\*\/\}/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

const card = stripComments(read(CARD));
const types = stripComments(read(TYPES));
const api = stripComments(read(API));
const pkg = JSON.parse(read(PKG) || '{}');

// 1. wire type
check('1 wire type', /revised_offer\?:\s*\{\s*kind:\s*'revision'\s*\|\s*'middle_ground';\s*line:\s*string;?\s*\}/.test(types));

// 2. normalizer
check('2a normalizer validates kind and line',
  /raw\?\.revised_offer\?\.kind\s*===\s*'revision'\s*\|\|\s*raw\?\.revised_offer\?\.kind\s*===\s*'middle_ground'/.test(api)
  && /typeof raw\?\.revised_offer\?\.line\s*===\s*'string'/.test(api));
check('2b key only when valid', /\.\.\.\(revisedOffer\s*\?\s*\{\s*revised_offer:\s*revisedOffer\s*\}\s*:\s*\{\}\)/.test(api));

// 3. gates
check('3a flag read', /useFlag\(\s*'trade\.next_move'\s*\)/.test(card));
check('3b hidden on an edited card', /revisedOfferEnabled\s*&&\s*!data\.edited\s*\?\s*data\.revised_offer\?\.line/.test(card));

// 4/5. block, placement
const blockAt = card.indexOf('testID="trade-card.revised-offer"');
check('4a block exists gated on the line', /\{revisedLine\s*\?\s*\(/.test(card) && blockAt > 0);
const block = blockAt > 0 ? card.slice(blockAt, card.indexOf(') : null}', blockAt)) : '';
check('4b renders the server line', /\{revisedLine\}/.test(block));
check('4c no client copy in the block', !/>[^<{}]*[A-Za-z]{3,}[^<{}]*</.test(block.replace(/\{revisedLine\}/, '')));
const header = card.indexOf('style={styles.header}');
const fit = card.indexOf('testID="trade-card.fit-block"');   // WS4b: the version-3 fit block
const value = card.indexOf('<TradeValueBar');
check('5 under the header, before the fit block and the value bar',
  header > 0 && blockAt > header && fit > blockAt && value > blockAt);

// 6. tokens and testIDs
const styleBlock = (card.match(/revisedOffer:\s*\{[^}]*\}/) || [''])[0];
check('6a token-only style', styleBlock.length > 0 && !/#[0-9a-fA-F]{3,8}/.test(styleBlock));
check('6b line testID', /testID="trade-card\.revised-offer\.line"/.test(card));

// 7. script
check('7 npm script', (pkg.scripts || {})['test:revised-offer-card'] === 'node tests/check-revised-offer-card.js');

if (failures.length) {
  console.error(`check-revised-offer-card: ${failures.length} FAILED, ${passed} passed`);
  for (const f of failures) console.error(`  ✗ ${f}`);
  process.exit(1);
}
console.log(`check-revised-offer-card: all ${passed} checks passed`);
