#!/usr/bin/env node
// Trios mode hint removed (11-06 binary; marketing §6 addendum 10 item 6).
//
// WHY THIS EXISTS. RankScreen rendered, unconditionally,
// "Trios · tap Rank below for more modes". It has been wrong since
// `ux.rank_tab_destination` went on: the Rank tab now navigates instead of
// opening a mode menu, and the other modes sit under the header's
// "More ways to rank" control on every flag-on rank surface (TabNav.tsx).
// The screen's own prompt, "Tap in order of preference — best first",
// already says what to do. Marketing's call: remove the hint. Pinned:
//   (a) RankScreen.tsx has no "tap Rank below" and no "for more modes";
//   (b) RankScreen.tsx has no `modeHint` style identifier;
// and the three premises that make the removal safe:
//   (c) RankScreen.tsx still shows "Tap in order of preference — best first";
//   (d) config/features.json still has "ux.rank_tab_destination": true;
//   (e) mobile/src/navigation/TabNav.tsx still has "More ways to rank".
// If (c), (d) or (e) breaks, the hint question needs reopening.
//
// HONEST LABEL (G-035): this proves the source text, not runtime behavior.
// The runtime proof is the TestFlight checklist in docs/plans/trios-hint/scope.md.
//
// Dependency-free (fs + string scanning), so it runs without node_modules.
// Run: node tests/check-rank-trios-hint.js
'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
const ok = (name) => console.log(`PASS  ${name}`);
const fail = (name, why) => {
  failures += 1;
  console.error(`FAIL  ${name}\n      ${why}`);
};

const MOBILE = path.join(__dirname, '..');
const stripComments = (text) =>
  text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
const rank = stripComments(fs.readFileSync(path.join(MOBILE, 'src', 'screens', 'RankScreen.tsx'), 'utf8'));
const tabNav = stripComments(fs.readFileSync(path.join(MOBILE, 'src', 'navigation', 'TabNav.tsx'), 'utf8'));
const flags = JSON.parse(fs.readFileSync(path.join(MOBILE, '..', 'config', 'features.json'), 'utf8'));
const REOPEN = 'The Trios hint was removed on this premise (marketing addendum 10 #6); '
  + 'reopen the hint question before changing this guard.';

// (a) the hint copy is gone
const hint = ['tap Rank below', 'for more modes'].filter((s) => rank.includes(s));
if (hint.length) fail('(a) hint copy', `RankScreen.tsx still renders ${hint.map((s) => `"${s}"`).join(' and ')}`);
else ok('(a) no "tap Rank below" / "for more modes" in RankScreen.tsx');

// (b) its styles are gone
const styleRefs = rank.match(/\bmodeHint\w*/g);
if (styleRefs) fail('(b) hint styles', `RankScreen.tsx still has ${[...new Set(styleRefs)].join(', ')}`);
else ok('(b) no modeHint identifier in RankScreen.tsx');

// (c) premise: the screen's own prompt says what to do
if (!rank.includes('Tap in order of preference — best first'))
  fail('(c) premise: prompt', `RankScreen.tsx no longer shows "Tap in order of preference — best first". ${REOPEN}`);
else ok('(c) premise: RankScreen.tsx still shows "Tap in order of preference — best first"');

// (d) premise: the Rank tab navigates (no mode menu)
if (flags['ux.rank_tab_destination'] !== true)
  fail('(d) premise: flag', `config/features.json "ux.rank_tab_destination" is `
    + `${JSON.stringify(flags['ux.rank_tab_destination'])}, not true. ${REOPEN}`);
else ok('(d) premise: config/features.json "ux.rank_tab_destination" is true');

// (e) premise: the other modes sit under the header's "More ways to rank"
if (!tabNav.includes('More ways to rank'))
  fail('(e) premise: More ways to rank', `mobile/src/navigation/TabNav.tsx no longer has "More ways to rank". ${REOPEN}`);
else ok('(e) premise: TabNav.tsx still has "More ways to rank"');

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nall trios hint checks passed');
