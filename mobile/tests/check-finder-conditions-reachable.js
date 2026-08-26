#!/usr/bin/env node
// #376/#379/#394 — the trade finder's conditions must be reachable IN THE
// RULED PLACE: the always-available minimized "Outlook & filters" row
// (trades.outlook-fallback) inside the receipt wrapper on TradesHome, with
// the full TradeDnaSheet behind its Change control — and NOT via the
// top utility-row Filters button #379 ruled out.
//
// WHY THE REWRITE (prd.md §6a, docs/feedback/items/376-finder-filters-
// regression/). The old guard pinned the utility-row Filters button — the
// placement the operator then ruled against — and its blacklist assertions
// could stay green while a variant/flag conjunct re-stranded a cohort (the
// original #394 failure mode). The core assertion here is a WHITELIST:
// the row's render condition must EQUAL
//   consolidateOn && !outlookReceiptShown && !firstRun
// — nothing added, nothing dropped. Any extra conjunct (showInlineHome,
// homeInlineVariant !== 'control', outlookDirectionOn, presentationV2On,
// any derived boolean) turns this red WITHOUT being named, and each of the
// three whitelisted predicates has a verified covering surface when false
// (legacy Controls Card row / the receipt itself / the first-run banner+
// next-mount latch), which is what makes the Filters-button removal safe.
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
// A missing source file is a harness failure, not an assertion failure —
// fail loudly and immediately (exit 2), never "0 failed" on nothing.
const read = (p) => {
  if (!fs.existsSync(p)) {
    console.error(`check-finder-conditions-reachable: missing source file ${path.relative(ROOT, p)}`);
    process.exit(2);
  }
  return fs.readFileSync(p, 'utf8');
};
// Assertions run against comment-stripped source so a commented-out row
// (or a commented-back-in Filters button) can't satisfy/dodge them.
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const row = strip(read(ROW));
const screen = strip(read(SCREEN));

// Balanced-paren span scanner: given the index of an opening '(', returns
// the index just past its matching ')'. Skips string/template literals so
// quoted parens don't unbalance the count. Used to extract JSX branch
// spans by their ANCHOR EXPRESSION, never by line number (this very diff
// shifted the legacy branch's line).
function spanFrom(src, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < src.length; i++) {
    const c = src[i];
    if (c === '"' || c === "'" || c === '`') {
      const q = c;
      i++;
      while (i < src.length && src[i] !== q) {
        if (src[i] === '\\') i++;
        i++;
      }
      continue;
    }
    if (c === '(') depth++;
    else if (c === ')') {
      depth--;
      if (depth === 0) return i + 1;
    }
  }
  return -1;
}

// ── 1. The row exists — boundary-anchored testIDs ─────────────────────
// `trades.outlook-fallback` is a PREFIX of `.change`/`.details`, so each
// match is closing-quote-exact (the #384 /isDemo/ lesson): deleting the
// container while keeping `.change` must go red.
{
  const container = /testID="trades\.outlook-fallback"/.test(screen);
  const change = /testID="trades\.outlook-fallback\.change"/.test(screen);
  if (!container) {
    bad('1. minimized outlook row renders (trades.outlook-fallback)',
      'no closing-quote-exact testID="trades.outlook-fallback" in ' +
      'TradesScreen. The always-available "Outlook & filters" row is the ' +
      'sole in-page sheet entry when the receipt hides — its absence is ' +
      'the #394 defect exactly.');
  } else if (!change) {
    bad('1. minimized outlook row renders (trades.outlook-fallback)',
      'the row container exists but testID="trades.outlook-fallback.change" ' +
      'does not — a row without its Change control reaches nothing.');
  } else ok('1. minimized outlook row + Change control exist (boundary-anchored)');
}

// ── 2. WHITELIST: the row's gate EQUALS the pinned expression ─────────
// Locate the JSX conditional whose true-branch opens with the row's
// container, extract the condition, and require token-equality with
// `consolidateOn && !outlookReceiptShown && !firstRun` (whitespace/paren-
// tolerant). A blacklist can be beaten by an alias; equality cannot.
let rowSpan = null; // saved for assertion 4
{
  const m = screen.match(/\{([^{}?]+)\?\s*\(\s*<View\s+testID="trades\.outlook-fallback"/);
  if (!m) {
    bad('2. row gate equals the whitelist',
      'could not locate `{<condition> ? (<View testID="trades.outlook-fallback"` ' +
      'in TradesScreen — the row is missing, unconditionally rendered, or ' +
      'gated through an intermediate variable. All three are red: the gate ' +
      'must be the literal inline conditional so it stays auditable.');
  } else {
    const norm = m[1].replace(/[()\s]+/g, '');
    const want = 'consolidateOn&&!outlookReceiptShown&&!firstRun';
    if (norm !== want) {
      bad('2. row gate equals the whitelist',
        `row condition is \`${m[1].trim()}\` — the gate must EQUAL ` +
        '`consolidateOn && !outlookReceiptShown && !firstRun`, nothing ' +
        'added, nothing dropped. An added conjunct (showInlineHome, ' +
        "homeInlineVariant !== 'control', outlookDirectionOn, or any " +
        'derived boolean) re-strands a cohort with the Filters button ' +
        'already deleted; a dropped one double-renders or hits first-run.');
    } else {
      ok('2. row gate equals `consolidateOn && !outlookReceiptShown && !firstRun`');
      // Extract the true-branch span (the row's JSX) for assertion 4.
      const openIdx = screen.indexOf('(', m.index + m[0].indexOf('?'));
      const end = spanFrom(screen, openIdx);
      if (end > 0) rowSpan = screen.slice(openIdx, end);
    }
  }
}

// ── 3. The row sits OUTSIDE the `!consolidateOn` legacy branch ────────
// Located by anchor expression + balanced-paren matching, never by line
// number. Inside that branch the row would render only for the classic
// flag-off home — the exact cohort that already has the Controls Card.
{
  const iRow = screen.indexOf('testID="trades.outlook-fallback"');
  if (iRow < 0) {
    bad('3. row is outside the legacy !consolidateOn branch', 'row not found');
  } else {
    let inside = false;
    const anchor = /\{\s*!consolidateOn\s*\?\s*\(/g;
    let a;
    while ((a = anchor.exec(screen)) !== null) {
      const openIdx = screen.indexOf('(', a.index + a[0].length - 1);
      const end = spanFrom(screen, openIdx);
      if (end > 0 && iRow > openIdx && iRow < end) inside = true;
    }
    if (inside) {
      bad('3. row is outside the legacy !consolidateOn branch',
        'trades.outlook-fallback is rendered inside a `{!consolidateOn ? (` ' +
        'branch — dead for every finder-mode user, which is the original ' +
        '#394 stranding.');
    } else ok('3. row is outside the legacy !consolidateOn branch');
  }
}

// ── 4. Within the row's extracted span, Change opens the FULL sheet ───
// Scoped to the span, not file-global: `setDnaSheetOpen(true)` appears at
// several other call sites and would self-satisfy.
{
  if (!rowSpan) {
    if (!fail.some((f) => f.startsWith('2.'))) {
      bad('4. row Change opens the full sheet', 'row span not extracted');
    } else ok('4. skipped (assertion 2 already red — fix the gate first)');
  } else if (!/setDnaSheetOpen\(true\)/.test(rowSpan)) {
    bad('4. row Change opens the full sheet',
      'the row\'s span contains no setDnaSheetOpen(true) — Change must open ' +
      'the full TradeDnaSheet (outlook, Chasing/Shopping, fairness, lanes, ' +
      'targeting, untouchables, intent).');
  } else if (/setOutlookOpen/.test(rowSpan)) {
    bad('4. row Change opens the full sheet',
      'the row\'s span calls setOutlookOpen — that is the legacy DNA-only ' +
      'OutlookSheet, not "the filters" this row claims to reach.');
  } else ok('4. row Change calls setDnaSheetOpen(true), not setOutlookOpen');
}

// ── 5. The utility-row Filters button stays REMOVED (#379) ────────────
// Absence is now the invariant: the operator ruled the top-row placement
// out, in the same change that added the in-page row above.
{
  if (/trades\.home-utility\.conditions/.test(row)) {
    bad('5. utility-row Filters button stays removed',
      'testID trades.home-utility.conditions is back in TradeHomeUtilityRow ' +
      '— #379 ruled this placement out; the in-page "Outlook & filters" row ' +
      'is the entry.');
  } else if (/onConditions/.test(row) || /onConditions/.test(screen)) {
    bad('5. utility-row Filters button stays removed',
      'an onConditions prop/pass survives in TradeHomeUtilityRow or ' +
      'TradesScreen — the #379 removal must be total.');
  } else ok('5. utility-row Filters button and onConditions stay removed');
}

// ── 6. Mode bar keeps its targeting guard (carried #269 invariant) ────
{
  if (!/hideTeamAndPlayer=\{sheetTargetingOn && consolidateOn\}/.test(screen)) {
    bad('6. mode bar still guards its own targeting entry',
      'the #269 guard `hideTeamAndPlayer={sheetTargetingOn && consolidateOn}` ' +
      'is gone. Its whole purpose is that the chips only disappear when the ' +
      'sheet that replaced them exists.');
  } else ok('6. mode bar keeps its targeting guard');
}

const label = 'check-finder-conditions-reachable';
if (fail.length) {
  console.error(`${label}: ${pass.length} passed, ${fail.length} failed\n`);
  fail.forEach((f) => console.error(`  ✗ ${f}`));
  process.exit(1);
}
console.log(`${label}: ${pass.length} passed, 0 failed`);
pass.forEach((p) => console.log(`  ✓ ${p}`));
