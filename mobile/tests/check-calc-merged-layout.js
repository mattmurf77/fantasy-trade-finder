#!/usr/bin/env node
// #384 W1 — the merged calculator layout, and the properties that make it
// safe to ship behind a flag.
//
// WHAT THIS PINS, and why each one is worth a test:
//
//  * The flag exists on BOTH sides of the wire. A client reading a flag the
//    backend never serves gets `undefined` — falsy — so the feature would be
//    silently unreachable and look "not working" rather than "off".
//  * Every merged-only surface is gated. An ungated one leaks into the
//    shipped stacked page, which is the whole risk of a flagged rewrite.
//  * The value/tier is MOVED in column mode, never dropped. A narrower row
//    that silently stops pricing an asset is worse than a wrapped one, and
//    it is the easiest thing to "fix" a layout overflow with.
//  * Tap targets and the type floor survive the 15% cells. This is the
//    operator-flagged risk in plan.md §2.
//
// Run: node tests/check-calc-merged-layout.js

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const SRC = path.join(__dirname, '..', 'src');
let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}`); if (detail) console.log(`      ${detail}`); }
}
const read = (p) => fs.readFileSync(p, 'utf8');
const calc = read(path.join(SRC, 'components/InLeagueCalculator.tsx'));
const side = read(path.join(SRC, 'components/TradeSide.tsx'));

console.log('check-calc-merged-layout:');

const FLAG = 'calc.merged_layout';

// 1 — the flag is registered on both sides of the wire.
const features = JSON.parse(read(path.join(ROOT, 'config/features.json')));
assert(Object.prototype.hasOwnProperty.call(features, FLAG),
  '1. flag is declared in config/features.json',
  `${FLAG} missing — the client would read undefined and the layout would be unreachable`);
assert(read(path.join(ROOT, 'backend/feature_flags.py')).includes(`"${FLAG}"`),
  '2. flag is in the backend FLAG_KEYS allowlist',
  `${FLAG} missing from backend/feature_flags.py — /api/feature-flags would not serve it`);
const release = JSON.parse(read(path.join(ROOT, 'backend/tests/fixtures/flags/release.json')));
assert(Object.prototype.hasOwnProperty.call(release, FLAG),
  '3. flag is mirrored in the release fixture');

// 4 — the client reads it.
assert(/useFlag\(\s*['"]calc\.merged_layout['"]\s*\)/.test(calc),
  '4. InLeagueCalculator reads the flag');

// 5 — every merged-only surface is gated behind the flag.
//
// NOT a proximity heuristic. An earlier draft of this check looked backwards
// for the nearest `{merged ?` and passed when the action row's own gate was
// replaced with `{true ?` — it simply found the header's gate instead. That
// assertion was unfalsifiable, so it was replaced with this:
//
//   excise every flag-gated region by BRACE BALANCING, then assert that no
//   merged-only testID survives in what is left.
//
// What is left is, by construction, exactly the code that renders when the
// flag is off. If an id is still in there, it leaks onto the shipped page.
function exciseGatedRegions(src) {
  const OPENERS = [/\{merged \? \(/g, /if \(merged\) \{/g];
  let out = src;
  for (const re of OPENERS) {
    for (;;) {
      re.lastIndex = 0;
      const m = re.exec(out);
      if (!m) break;
      // Balance from the opener's final bracket to its partner.
      const openChar = m[0].endsWith('{') ? '{' : '(';
      const closeChar = openChar === '{' ? '}' : ')';
      let i = m.index + m[0].length - 1;
      let depth = 0;
      for (; i < out.length; i++) {
        if (out[i] === openChar) depth++;
        else if (out[i] === closeChar) { depth--; if (depth === 0) break; }
      }
      if (i >= out.length) break; // unbalanced — leave it, assertion below will speak
      out = out.slice(0, m.index) + out.slice(i + 1);
    }
  }
  return out;
}
const flagOffSource = exciseGatedRegions(calc);
// Sanity: the excision must actually remove something, or every assertion
// below it is vacuous. This is the guard on the guard.
assert(flagOffSource.length < calc.length - 2000,
  '5a. the gate-excision actually removed the merged regions',
  `only ${calc.length - flagOffSource.length} chars removed — the matcher missed`);

const MERGED_ONLY = [
  'calc.action-row', 'calc.action.find-a-trade', 'calc.action.include-players',
  'calc.action.clear', 'calc.action.confirm', 'calc.league-dropdown',
  'calc.team-dropdown', 'calc.trade-columns', 'calc.team-sheet',
];
for (const id of MERGED_ONLY) {
  assert(calc.includes(`testID="${id}"`) && !flagOffSource.includes(`testID="${id}"`),
    `5. ${id} renders only behind the flag`,
    calc.includes(`testID="${id}"`)
      ? 'this control survives with the flag OFF — it would render on the shipped stacked page'
      : 'testID not found at all');
}

// 6 — the price is moved, not dropped, in column mode.
assert(/compact\s*\?\s*\(\(\) => \{[\s\S]{0,400}?TierBadge/.test(side),
  '6. column mode still renders a tier/value for each row',
  'TradeSide compact dropped the price column instead of re-flowing it');
assert(/compactMetaLine/.test(side) && /valueOf\(p\)\.toLocaleString\(\)/.test(side),
  '7. column mode keeps the numeric fallback when there is no tier');

// 8 — no type shrinking to win space in the MERGED styles.
//
// Scoped to the #384 style block on purpose. The file already carries one
// pre-existing floor violation — `lineupHeadText` at fontSize 10, present on
// origin/main since #297 — and this change did not introduce it and does not
// fix it (that would be an unrelated edit to a shipped surface). It is
// reported to the operator rather than silently absorbed or silently
// tolerated: widening this assertion to the whole file would fail on someone
// else's line, and deleting the assertion would lose the guarantee that
// matters here, which is that the narrow cells were not paid for in type size.
const mergedStyles = calc.slice(
  calc.indexOf('// ── #384 merged layout'),
  calc.indexOf('teamRow: {'),
);
const fontSizes = [...mergedStyles.matchAll(/fontSize:\s*(\d+)/g)].map((m) => Number(m[1]));
assert(fontSizes.length > 0 && fontSizes.every((n) => n >= 11),
  '8. no #384 font size below the Chalkline 11pt floor',
  `found ${fontSizes.filter((n) => n < 11).join(', ') || '(no sizes scanned — slice missed)'}`);

// 9 — the narrow cells keep a real tap target.
assert(/actionBtn:\s*\{[^}]*minHeight:\s*44/.test(calc),
  '9. action-row buttons hold a 44pt tap height',
  'the 15% cells are ~53pt wide; losing the height too would put them under the floor');

// 10 — the two icon-only cells are labelled. Icon-only + unlabelled is a
// screen-reader dead end, and these two are the destructive + confirm pair.
for (const id of ['calc.action.clear', 'calc.action.confirm']) {
  const at = calc.indexOf(`testID="${id}"`);
  const window = calc.slice(at, at + 500);
  assert(/accessibilityLabel=/.test(window), `10. ${id} carries an accessibilityLabel`);
}

// 11 — no emoji as icons (Chalkline forbids it; the report specced "✅").
assert(!/[\u{1F300}-\u{1FAFF}\u{2700}-\u{27BF}\u{2B00}-\u{2BFF}\u{2705}\u{274C}]/u.test(calc),
  '11. no emoji used as an icon in the merged layout',
  'the report specced ✅; Chalkline requires a real icon (name="check")');

// 12 — Clear exists exactly once in the merged layout. Two controls for one
// destructive action on one screen is a defect, not a convenience.
assert(/merged \? null : <Button label="Clear trade"/.test(calc),
  '12. the legacy Clear button is suppressed in the merged layout',
  'both the action-row Clear and the ghost Clear would render');

console.log(failures === 0
  ? 'check-calc-merged-layout: all assertions passed'
  : `check-calc-merged-layout: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
