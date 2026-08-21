#!/usr/bin/env node
// #376 — the trade finder's conditions must be reachable from WHATEVER row is
// standing in for TradeFinderModeBar.
//
// WHY THIS EXISTS. The operator reported "the latest update removed the
// filters/conditions of the trade finder". No update removed them. The
// `trades_home_inline` experiment has run at 100% `strip` on the tester
// allowlist since 2026-08-09, and in that variant `TradeHomeUtilityRow`
// REPLACES `TradeFinderModeBar` — but it was built with Draft / Free agents /
// Manual calc and no conditions entry. The filters survived only behind
// OutlookBiasReceipt's "Change" link.
//
// The failure is structural and silent: an experiment swaps one component for
// another, and an affordance the first one carried simply ceases to exist for
// the enrolled cohort. No typecheck and no backend test can see it. This guard
// pins the invariant that `onTodaysTrade`'s own source comment had already
// stated in prose and nobody had encoded.
//
// Run: node tests/check-finder-conditions-reachable.js
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const ROW = path.join(ROOT, 'src/components/TradeHomeUtilityRow.tsx');
const SCREEN = path.join(ROOT, 'src/screens/TradesScreen.tsx');

const pass = [], fail = [];
const ok = (n) => pass.push(n);
const bad = (n, d) => fail.push(`${n}\n      ${d}`);
const read = (p) => (fs.existsSync(p) ? fs.readFileSync(p, 'utf8')
  : (bad('file exists', `missing ${path.relative(ROOT, p)}`), ''));
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const rowRaw = read(ROW), screenRaw = read(SCREEN);
const row = strip(rowRaw), screen = strip(screenRaw);

// 1 — the stand-in row accepts a conditions handler
{
  if (!/onConditions\?\s*:\s*\(\)\s*=>\s*void/.test(row)) {
    bad('1. utility row accepts onConditions',
      'TradeHomeUtilityRow has no `onConditions?: () => void` prop. This row ' +
      'replaces TradeFinderModeBar for the trades_home_inline cohort, so an ' +
      'entry the mode bar carried must exist here too (#376).');
  } else ok('1. utility row accepts onConditions');
}

// 2 — and actually renders a control for it
{
  if (!/testID="trades\.home-utility\.conditions"/.test(row)) {
    bad('2. utility row renders the conditions control',
      'no testID="trades.home-utility.conditions" in TradeHomeUtilityRow. ' +
      'Accepting the prop without rendering it is the #376 defect exactly.');
  } else ok('2. utility row renders the conditions control');
}

// 3 — it LEADS the row. Last place reproduces the discoverability failure.
{
  const iCond = row.indexOf('trades.home-utility.conditions');
  const others = ['trades.home-utility.todays-trade', 'trades.home-utility.draft',
                  'trades.home-utility.free-agents', 'trades.home-utility.manual']
    .map((t) => row.indexOf(t)).filter((i) => i >= 0);
  if (iCond < 0) bad('3. conditions leads the row', 'control not found');
  else if (others.some((i) => i < iCond)) {
    bad('3. conditions leads the row',
      'another utility button is rendered before the conditions control. It ' +
      'was reported MISSING; burying it repeats the failure.');
  } else ok('3. conditions leads the row');
}

// 4 — the screen wires it to the sheet that actually holds the filters
{
  const m = screen.match(/onConditions=\{[^}]*\}/);
  if (!m) {
    bad('4. TradesScreen passes onConditions',
      'TradeHomeUtilityRow is rendered without onConditions, so the cohort ' +
      'that sees this row still has no filters entry.');
  } else if (!/setDnaSheetOpen\(true\)/.test(m[0])) {
    bad('4. onConditions opens the finder sheet',
      `wired to something other than setDnaSheetOpen(true): ${m[0]}`);
  } else if (!/consolidateOn/.test(m[0])) {
    bad('4. onConditions is gated on consolidateOn',
      'consolidateOn is what makes the FULL sheet exist (fairness, lanes, ' +
      'targeting). Without that gate the button opens a DNA-only sheet and ' +
      'is not "the filters" it claims to be.');
  } else ok('4. TradesScreen wires onConditions to the full sheet');
}

// 5 — the mode bar itself must keep a route to the same sheet, so neither
//     branch of the experiment can lose it.
{
  if (!/hideTeamAndPlayer=\{sheetTargetingOn && consolidateOn\}/.test(screen)) {
    bad('5. mode bar still guards its own targeting entry',
      'the #269 guard `hideTeamAndPlayer={sheetTargetingOn && consolidateOn}` ' +
      'is gone. Its whole purpose is that the chips only disappear when the ' +
      'sheet that replaced them exists.');
  } else ok('5. mode bar keeps its targeting guard');
}

const label = 'check-finder-conditions-reachable';
if (fail.length) {
  console.error(`${label}: ${pass.length} passed, ${fail.length} failed\n`);
  fail.forEach((f) => console.error(`  ✗ ${f}`));
  process.exit(1);
}
console.log(`${label}: ${pass.length} passed, 0 failed`);
pass.forEach((p) => console.log(`  ✓ ${p}`));
