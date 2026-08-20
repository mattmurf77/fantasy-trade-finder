#!/usr/bin/env node
// Team Review DEPTH beat structural guard — feedback #366.
// Flags: `trade.position_tiers`, `trade.rb_handcuff` (both default OFF).
// Scope: docs/feedback/items/366-tier-ladder/scope.md
//
// WHY THIS EXISTS, SEPARATELY FROM check-team-review.js.
// That guard pins the SCREEN's placement facts (registered once, no local FAB,
// not a mode chip). This one pins the depth beat's BACK-COMPAT contract, which
// is a different kind of claim and a different kind of regression:
//
// The backend now emits `replacement` as an ALIAS of `bench` — both keys, not
// a rename — precisely so a shipped client keeps parsing. That only helps if
// the client actually reads the pair correctly. Two symmetrical ways to get it
// wrong, both of which typecheck and both of which a backend unit test is
// blind to:
//   * read `replacement` alone  -> a flag-OFF payload renders a hole
//   * declare `replacement` required in the type -> the flag-OFF payload stops
//     being assignable and the next `?? 0` papers over it
// And one honesty claim: `handcuff_rb` ABSENT means "we did not perform the
// read", which is NOT "you own zero handcuffs". Defaulting it with `?? 0` would
// make the card assert a fact about the user's roster that nobody checked.
//
// Run: node tests/check-team-review-depth.js  (or npm run test:team-review-depth)
// CI picks it up automatically via the tests/check-*.js glob.

'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCREEN = path.join(ROOT, 'src/screens/TeamReviewScreen.tsx');
const API = path.join(ROOT, 'src/api/teamReview.ts');

const pass = [];
const fail = [];
const ok = (n) => pass.push(n);
const bad = (n, d) => fail.push(`${n}\n      ${d}`);
const read = (p) => (fs.existsSync(p)
  ? fs.readFileSync(p, 'utf8')
  : (bad('file exists', `missing ${path.relative(ROOT, p)}`), ''));
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const screen = strip(read(SCREEN));
const api = strip(read(API));

// Isolate the Depth component so a match elsewhere in a 2k-line screen cannot
// satisfy an assertion about this beat.
function depthBlock(src) {
  const start = src.indexOf('function Depth(');
  if (start < 0) return '';
  const next = src.indexOf('\nfunction ', start + 1);
  return src.slice(start, next < 0 ? src.length : next);
}
const depth = depthBlock(screen);

// 1 — the component exists at all (every later assertion depends on it)
{
  if (!depth) {
    bad('1. Depth component found',
      'no `function Depth(` in TeamReviewScreen.tsx — the beat this guard '
      + 'pins has been renamed or removed; update this file in the same commit');
  } else ok('1. Depth component found');
}

// 2 — reads `replacement ?? bench`, never `replacement` alone
{
  const usesAlias = /\breplacement\s*\?\?\s*[\w.]*\bbench\b/.test(depth);
  const mentionsReplacement = /\breplacement\b/.test(depth);
  if (!mentionsReplacement) {
    bad('2. renders the Replacement layer',
      'the Depth beat never mentions `replacement`. Feedback #366 asked for '
      + 'Elite / Starter / Replacement as three visible layers; the third bin '
      + 'has always been computed and never rendered.');
  } else if (!usesAlias) {
    bad('2. reads `replacement ?? bench`',
      'the Depth beat reads `replacement` without falling back to `bench`. '
      + '`replacement` is emitted ONLY when the backend flag trade.position_tiers '
      + 'is on; with it off (the default, and every backend older than #366) the '
      + 'key is absent and this row renders a hole. The backend ships BOTH keys '
      + 'so the client can read the pair — read the pair.');
  } else ok('2. reads `replacement ?? bench`');
}

// 3 — the API type declares `replacement` OPTIONAL and `bench` REQUIRED
{
  const m = api.match(/tier_depth:\s*Record<\s*string\s*,\s*\{([\s\S]*?)\}\s*>/);
  if (!m) {
    bad('3. tier_depth value type is declared',
      'could not find the tier_depth Record<> value type in api/teamReview.ts');
  } else {
    const body = m[1];
    const replOptional = /\breplacement\s*\?\s*:/.test(body);
    const benchRequired = /\bbench\s*:/.test(body);
    if (!replOptional) {
      bad('3a. `replacement` is optional',
        'TeamReviewDepth declares `replacement` as required. It is present only '
        + 'when trade.position_tiers is on, so a required declaration makes the '
        + 'flag-OFF payload unassignable and invites a `?? 0` that hides the gap.');
    } else ok('3a. `replacement` is optional');
    if (!benchRequired) {
      bad('3b. `bench` is still required',
        'TeamReviewDepth no longer requires `bench`. The backend emits it at '
        + 'EVERY flag setting — it is the alias\'s anchor. Dropping it from the '
        + 'type removes the only key the fallback in assertion 2 can land on.');
    } else ok('3b. `bench` is still required');
  }
}

// 4 — `handcuff_rb` renders on PRESENCE, never defaulted to 0
{
  if (!/handcuff_rb/.test(depth)) {
    bad('4. renders the RB handcuff count',
      'the Depth beat never reads `handcuff_rb`. #366 asked for a Handcuff '
      + 'layer on RB, and it is real data — Sleeper\'s own depth_chart_order, '
      + 'ingested since database.py:8769.');
  } else if (/handcuff_rb\s*\?\?/.test(depth) || /handcuff_rb\s*\|\|/.test(depth)) {
    bad('4. `handcuff_rb` is never defaulted',
      'the Depth beat defaults `handcuff_rb` with ?? or ||. ABSENT means the '
      + 'backend flag trade.rb_handcuff is OFF and NOBODY LOOKED; 0 means we '
      + 'looked and you own none. Collapsing the first into the second makes '
      + 'the card state a fact about the roster that was never checked.');
  } else if (!/handcuff_rb\s*!==\s*undefined/.test(depth)) {
    bad('4. `handcuff_rb` is gated on presence',
      'expected an explicit `d.handcuff_rb !== undefined` presence check. A '
      + 'truthiness check would also swallow a legitimate 0.');
  } else ok('4. `handcuff_rb` renders on presence, never defaulted');
}

// 5 — the user-facing word is "Replacement", and "bench" is not shown to them
{
  if (!/>[^<]*Replacement/.test(depth) && !/Replacement<\/|Replacement`|Replacement /.test(depth)) {
    bad('5a. the label reads "Replacement"',
      'the beat does not render the word Replacement. That is the word the '
      + 'report used, and the reason the wire alias exists at all.');
  } else ok('5a. the label reads "Replacement"');

  // The wire key `bench` is fine; the rendered STRING "bench"/"Bench" is not.
  // Single-line literals only — a multi-line match just walks from one JSX
  // attribute quote to the next and swallows the `bench: 0` object key on the
  // way, which is a wire key and entirely legitimate.
  const shown = depth.match(/(['"`])[^'"`\n]*\b[Bb]ench\b[^'"`\n]*\1/g) || [];
  if (shown.length) {
    bad('5b. the word "bench" is not shown to the user',
      `found user-facing string(s) containing "bench": ${shown.join(', ')}. `
      + 'The wire KEY stays `bench` for back-compat; the LABEL is Replacement.');
  } else ok('5b. the word "bench" is not shown to the user');
}

// 6 — no new color literal (Chalkline: ice/flare only; tier hexes are governed
//     by docs/cross-client-invariants.md and are never invented in a screen)
{
  const hexes = depth.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
  if (hexes.length) {
    bad('6. no raw color literals in the Depth beat',
      `found ${hexes.join(', ')}. Chalkline (ADR-004/005) allows ice for actions `
      + 'and flare for informational highlights, through tokens; position and '
      + 'tier hexes are data encodings governed by docs/cross-client-invariants.md '
      + 'and must never be re-declared in a screen.');
  } else ok('6. no raw color literals in the Depth beat');
}

console.log(`\ncheck-team-review-depth: ${pass.length} passed, ${fail.length} failed`);
for (const p of pass) console.log(`  ✓ ${p}`);
if (fail.length) {
  console.error('\nFAILURES:');
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.error('\nThese pin the #366 wire-alias back-compat contract and the '
    + 'absent-vs-zero honesty rule. If a change is genuinely intended, update '
    + 'docs/cross-client-invariants.md and DECISIONS.md in the SAME commit.\n');
  process.exit(1);
}
console.log('');
