#!/usr/bin/env node
// Card impact-block placement + odds honesty guard (#357).
//
// WHY THIS EXISTS. D-025 (operator, #169 frame decisions) fixed the deck
// card's vertical order and wrote a clause that was VACUOUS at the time:
//
//   "the disposition pair sits directly beneath the player tiles, TradeValueBar
//    sits below the pair, and any future card odds block mounts below the bar"
//
// There was no card odds block then — the operator had just dropped card frame
// D on its backend cost. #357 is that block, so the clause stops being vacuous
// and starts being binding. Nothing else in the tree enforces it: the existing
// check-card-disposition.js pins the pair against the tiles and the value bar,
// but knows nothing about a block below them.
//
// The odds assertions are the same class as check-outlook-bands.js, applied to
// the card: bands are the rendering, never a bare percentage, and `title_pct`
// is unrenderable at any week on an absence of demonstrated skill.
//
// What is pinned:
//   1. CardImpactBlock is mounted in TradeCard.tsx AFTER TradeValueBar
//      (source order = render order for sibling JSX).
//   2. It is host-fed via a `cardImpact` prop — TradeCard does not fetch.
//      Self-fetching would fire once per rendered card, including peek cards,
//      which is exactly the eager cost the lazy design exists to avoid.
//   3. Only SwipableTopCard passes it in TradesScreen — the peek-card mount
//      must not.
//   4. CardImpactBlock never references title_pct.
//   5. CardImpactBlock renders BAND labels, and its only percentage-shaped
//      output is the signed whole-point delta (`signedPoints`).
//   6. The rank chip renders "WR #3", never "WR3" (R-6, #395) — a bare
//      positional rank beside the slot labels reads as a lineup slot. Anchored
//      to the rank template literal itself, not a bare `#${` over the file.
//
// Run: node tests/check-card-impact-order.js   (or npm run test:card-impact)
// CI picks it up automatically via the tests/check-*.js glob in ci.yml.

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const CARD = path.join(ROOT, 'src/components/TradeCard.tsx');
const BLOCK = path.join(ROOT, 'src/components/CardImpactBlock.tsx');
const SCREEN = path.join(ROOT, 'src/screens/TradesScreen.tsx');

const failures = [];
const passes = [];
const ok = (n) => passes.push(n);
const bad = (n, d) => failures.push(`${n}\n      ${d}`);

function read(p) {
  if (!fs.existsSync(p)) {
    bad('file exists', `missing: ${path.relative(ROOT, p)}`);
    return '';
  }
  return fs.readFileSync(p, 'utf8');
}

const card = read(CARD);
const block = read(BLOCK);
const screen = read(SCREEN);

// Strip comments so prose about ordering cannot satisfy an ordering assertion.
function strip(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

// ── 1. Mounted below the value bar ────────────────────────────────────────
{
  const s = strip(card);
  const bar = s.indexOf('<TradeValueBar');
  const impact = s.indexOf('<CardImpactBlock');
  if (bar === -1) {
    bad('1. TradeValueBar is mounted', 'no <TradeValueBar in TradeCard.tsx');
  } else if (impact === -1) {
    bad('1. CardImpactBlock is mounted', 'no <CardImpactBlock in TradeCard.tsx');
  } else if (impact < bar) {
    bad('1. impact block mounts BELOW TradeValueBar',
      'CardImpactBlock appears BEFORE TradeValueBar in source order. D-025 ' +
      'fixed this order: disposition pair -> TradeValueBar -> odds block. ' +
      'Reordering it needs a new operator decision, not a refactor.');
  } else {
    ok('1. impact block mounts below TradeValueBar (D-025 order)');
  }
}

// ── 2. Prop-driven, not self-fetching ─────────────────────────────────────
{
  const s = strip(card);
  if (!/cardImpact/.test(s)) {
    bad('2. TradeCard takes a cardImpact prop', 'prop not found');
  } else if (/useCardImpact\s*\(/.test(s) || /evaluateTradeInLeague\s*\(/.test(s)) {
    bad('2. TradeCard does NOT fetch its own impact',
      'TradeCard calls the fetch directly. It renders for peek cards too, so ' +
      'self-fetching would restore the eager cost the lazy design avoids.');
  } else {
    ok('2. TradeCard is prop-driven, does not fetch');
  }
}

// ── 3. Only the fronted card gets one ─────────────────────────────────────
{
  const s = strip(screen);
  const n = (s.match(/cardImpact=\{/g) || []).length;
  if (!/useCardImpact\s*\(/.test(s)) {
    bad('3. the host fetches impact', 'TradesScreen does not call useCardImpact');
  } else if (n === 0) {
    bad('3. the host passes impact down', 'no cardImpact={...} in TradesScreen');
  } else if (n > 2) {
    // Expected exactly two: the <SwipableTopCard> call site and the inner
    // pass-through to TradeCardComp. A third means a peek card is being fed.
    bad('3. only the FRONTED card receives impact',
      `found ${n} cardImpact={...} sites in TradesScreen (expected 2: the ` +
      'SwipableTopCard call and its pass-through). A peek-card mount would ' +
      'fetch for cards nobody is looking at.');
  } else {
    ok('3. only the fronted card receives impact');
  }
}

// ── 4. title_pct is never referenced ──────────────────────────────────────
{
  const s = strip(block);
  if (/title_pct/.test(s)) {
    bad('4. CardImpactBlock never reads title_pct',
      'title_pct is unrenderable at any week, in any form — an absence of ' +
      'demonstrated skill (CI spans zero), not a calibration judgement. The ' +
      'server does not even serialize it here.');
  } else {
    ok('4. CardImpactBlock never reads title_pct');
  }
}

// ── 5. Bands are the rendering ────────────────────────────────────────────
{
  const s = strip(block);
  const hasBands = /before_band/.test(s) && /after_band/.test(s);
  const rendersRawPct = /\{[^}]*\b(before_pct|after_pct)\b[^}]*\}/.test(s);
  if (!hasBands) {
    bad('5a. bands drive the odds rendering',
      'CardImpactBlock does not read before_band/after_band — the band ' +
      'vocabulary is a cross-client encoding and must be read, never re-derived');
  } else {
    ok('5a. bands drive the odds rendering');
  }
  if (rendersRawPct) {
    bad('5b. raw before_pct/after_pct are never rendered',
      'a bare playoff percentage is forbidden; only the signed WHOLE-point ' +
      'delta may accompany the band movement');
  } else {
    ok('5b. raw before_pct/after_pct are never rendered');
  }
  if (!/signedPoints/.test(s)) {
    bad('5c. the delta is rounded to whole points',
      'signedPoints() is the only permitted numeric odds output');
  } else {
    ok('5c. the delta is rounded to whole points');
  }
}

// ── 6. Rank chip is a rank, not a slot (R-6, #395) ────────────────────────
{
  // Anchored to the rank template literal itself (per the #395 PRD): a bare
  // /#\$\{/ over the file would be satisfiable by any future unrelated `#${`
  // and prove nothing about THIS chip.
  const s = strip(block);
  const beforeAnchor = "position ?? ''} #${beforeRank}";
  const afterAnchor = "position ?? ''} #${afterRank}";
  if (!s.includes(beforeAnchor)) {
    bad('6a. rank chip before-half is "#"-prefixed ("WR #3", not "WR3")',
      `expected the rank template literal to contain \`${beforeAnchor}\`. ` +
      'Without the "# " separator a positional rank ("WR3") sitting beside ' +
      'the slot labels reads as a lineup slot (#395). The chip stays a ' +
      'positional rank (#169) — only the format is pinned.');
  } else {
    ok('6a. rank chip before-half is "#"-prefixed ("WR #3", not "WR3")');
  }
  if (!s.includes(afterAnchor)) {
    bad('6b. rank chip after-half is "#"-prefixed ("WR #12", not "WR12")',
      `expected the rank template literal to contain \`${afterAnchor}\`. ` +
      'Both halves of the before/after chip carry the "#" prefix (R-6).');
  } else {
    ok('6b. rank chip after-half is "#"-prefixed ("WR #12", not "WR12")');
  }
}

// ── Report ────────────────────────────────────────────────────────────────
console.log(`\ncheck-card-impact-order: ${passes.length} passed, ${failures.length} failed`);
for (const p of passes) console.log(`  ✓ ${p}`);
if (failures.length) {
  console.error('\nFAILURES:');
  for (const f of failures) console.error(`  ✗ ${f}`);
  console.error(
    '\nPlacement is an operator decision (D-025) and the odds rules are ' +
    'cross-client invariants — neither is a style preference. If a change ' +
    'here is genuinely intended, update living-memory/DECISIONS.md and ' +
    'docs/cross-client-invariants.md in the SAME commit.\n');
  process.exit(1);
}
console.log('');
