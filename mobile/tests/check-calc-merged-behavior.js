#!/usr/bin/env node
// #384 W2 — the behaviour rulings, and the properties that keep each one
// honest when the flag is off.
//
// Run: node tests/check-calc-merged-behavior.js

'use strict';

const fs = require('fs');
const path = require('path');
const SRC = path.join(__dirname, '..', 'src');
let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}`); if (detail) console.log(`      ${detail}`); }
}
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const card = read('components/TradeCard.tsx');
const trades = read('screens/TradesScreen.tsx');
const screen = read('screens/TradeCalculatorScreen.tsx');

console.log('check-calc-merged-behavior:');

// ── Ruling 1: the ✕ survives and pops an overlay; inline tiles stay OFF-path
assert(/reasonsAsOverlay\s*=\s*useFlag\(\s*['"]calc\.merged_layout['"]\s*\)/.test(card),
  '1. the overlay form is gated on calc.merged_layout',
  'ungated, this would change the shipped deck for every user');

// The ✕ must be RESTORED in overlay mode — the shipped form deletes it.
assert(/disposition\.reasons\s*&&\s*!reasonsAsOverlay\s*\?\s*null\s*:\s*\(/.test(card),
  '2. overlay mode keeps the single ✕ button',
  'the pass button is still suppressed whenever reasons are wired');

// Exactly one presentation at a time. Both mounted = two reason panels.
assert(/disposition\.reasons\s*&&\s*!reasonsAsOverlay\s*\?\s*\(\s*<DeclineReasonPanel/.test(card),
  '3. the inline panel is suppressed in overlay mode');
assert(/disposition\.reasons\s*&&\s*reasonsAsOverlay\s*\?\s*\(\s*<Modal/.test(card),
  '4. the overlay panel mounts only in overlay mode');

// The host advances the deck on commit; a sheet left open would strand over
// the NEXT card. Every advancing callback must close first.
// Each callback's own expression only. An earlier draft used a fixed 160/260
// char window, which let assertion 6 read the NEXT prop's body and fail on a
// close that wasn't its own — a window, not the code, was being tested.
function propBody(src, name) {
  const at = src.indexOf(`${name}={(`);
  if (at < 0) return null;
  // Balance braces from the prop's opening `{` to its partner.
  let i = src.indexOf('{', at + name.length);
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(i, j + 1); }
  }
  return null;
}
for (const cb of ['onLayer1', 'onLayer2Select', 'onLayer2Send']) {
  const body = propBody(card, cb);
  assert(!!body && /setReasonOverlayOpen\(false\)/.test(body),
    `5. ${cb} closes the overlay before committing`,
    body ? 'the sheet would stay up over the next card' : 'prop not found');
}
// ...and onLayer2Bank must NOT close: it banks a code and opens a text box.
{
  const body = propBody(card, 'onLayer2Bank');
  assert(!!body && !/setReasonOverlayOpen\(false\)/.test(body),
    '6. onLayer2Bank does NOT close the overlay',
    'banking opens the free-text composer — closing would destroy the input');
}

// ── Ruling 8: the two end-of-deck exits, both gated
assert(/calcMergedOn\s*=\s*useFlag\(\s*['"]calc\.merged_layout['"]\s*\)/.test(trades),
  '7. TradesScreen reads the merged flag');
for (const id of ['trades.deck-summary.back-to-calc', 'trades.deck-summary.unpin-retry']) {
  const at = trades.indexOf(`testID="${id}"`);
  assert(at >= 0, `8. ${id} exists`);
  const before = trades.slice(Math.max(0, at - 700), at);
  assert(/calcMergedOn/.test(before), `8. ${id} is gated on the merged flag`,
    'it would appear on the shipped deck, where there is no calculator-first flow');
}
// The unpin exit must reuse handleClearPin — it restores the pre-pin deck
// snapshot and fires trade_pin_cleared. A hand-rolled unpin would do neither.
{
  const at = trades.indexOf('testID="trades.deck-summary.unpin-retry"');
  const seg = trades.slice(at, at + 700);
  assert(/handleClearPin\(\)/.test(seg),
    '9. the unpin exit reuses handleClearPin',
    'a second unpin path would skip the snapshot restore and the analytics event');
  assert(/singlePin/.test(trades.slice(Math.max(0, at - 400), at)),
    '10. the unpin exit only shows when exactly one asset is pinned');
}

// ── Ruling 2: Include players writes the SHIPPED pin store, not a new param
assert(/useFinderTargets/.test(screen),
  '11. the finder hand-off goes through useFinderTargets');
assert(!/requireAssets/.test(screen),
  '12. no parallel requireAssets route param survives',
  'an invented param nothing reads would silently do nothing');
{
  const at = screen.indexOf('onFindATrade={(');
  const seg = screen.slice(at, at + 1400);
  assert(/setSide\('give'/.test(seg) && /setSide\('receive'/.test(seg),
    '13. include-ON pins both sides of the canvas');
  assert(/setPackageMode\(true\)/.test(seg),
    '14. include-ON sets packageMode — the contract that makes "must include" literal');
  assert(/t\.clear\(\)/.test(seg),
    '15. include-OFF clears stale pins',
    'a leftover pin would re-apply the constraint the user just switched off');
}

console.log(failures === 0
  ? 'check-calc-merged-behavior: all assertions passed'
  : `check-calc-merged-behavior: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
