#!/usr/bin/env node
// Trios error state (B6, rankings-pm review 2026-10-27; P2-1, release-lead QA 2026-10-28).
//
// WHY THIS EXISTS. RankScreen's card area is one ternary chain.
//   * B6. It tested the skeleton condition `trioQuery.isLoading || !trio`
//     BEFORE `trioQuery.isError`. A failed /api/trio (5xx, timeout, 403) leaves
//     `trio` undefined, so the skeleton matched first and showed forever. The
//     error branch with its Retry could never render.
//   * P2-1. The first fix guarded the error branch with `&& !trio`. When the
//     next-trio fetch failed right after a successful submit, the cached trio
//     was still held, so the JUST-RANKED trio came back enabled with no
//     message. Ranking it again sent a duplicate /api/rank3, which the server
//     double-counts.
//
// So the error branch is plain `trioQuery.isError`. Every Trios refetch replaces
// the trio, so a failed one shows the error view, never a stale rankable trio.
// Pinned:
//   (a) the RookieScopeEmpty branch stays first, and the error condition comes
//       BEFORE the `isLoading || !trio` skeleton condition;
//   (b) the error branch renders a pressable (chalkline Button / Pressable)
//       whose onPress calls `trioQuery.refetch`;
//   (c) the error branch references no `error` identifier and no `.message`
//       at all, and shows the fixed string "Could not load next trio";
//   (d) the error condition is exactly `trioQuery.isError`: no `!trio` /
//       `!trioQuery.data` (or any other) conjunct;
//   (e) nothing ABOVE the error branch renders a skeleton or tests `!trio`,
//       `isLoading` or `isFetching`;
//   (f) the error branch's Button keeps `label="Try again"`.
//
// HONEST LABEL (G-035): this proves the presence and order of exact wirings in
// the source, not runtime behavior. The runtime proof is the TestFlight
// checklist in docs/plans/trios-error-state/scope.md.
//
// Dependency-free (fs + string scanning), so it runs without node_modules.
// Run: node tests/check-rank-trios-error.js
'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
const ok = (name) => console.log(`PASS  ${name}`);
const fail = (name, why) => {
  failures += 1;
  console.error(`FAIL  ${name}\n      ${why}`);
};

const file = path.join(__dirname, '..', 'src', 'screens', 'RankScreen.tsx');
const src = fs.readFileSync(file, 'utf8');
const stripComments = (text) =>
  text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

// The card-area chain starts at `{trioEmpty ? (`.
const chainStart = src.indexOf('{trioEmpty ? (');
if (chainStart < 0) {
  fail('locate chain', 'no `{trioEmpty ? (` in RankScreen.tsx: the card chain moved; update this guard');
  process.exit(1);
}
const chain = stripComments(src.slice(chainStart));

const errorCond = /\)\s*:\s*trioQuery\.isError\b([^?]*)\?\s*\(/.exec(chain);
const skeletonCond = /\)\s*:\s*trioQuery\.isLoading\s*\|\|\s*!trio\s*\?\s*\(/.exec(chain);
const rookieEmpty = chain.indexOf('<RookieScopeEmpty');

// Body of a `? ( … )` branch: from its opening paren to the matching close.
function branchBody(match) {
  const open = match.index + match[0].length - 1;          // the `(` after `?`
  let depth = 0;
  for (let i = open; i < chain.length; i += 1) {
    if (chain[i] === '(') depth += 1;
    else if (chain[i] === ')') {
      depth -= 1;
      if (depth === 0) return chain.slice(open + 1, i);
    }
  }
  return null;
}

// (a) order
if (!errorCond) fail('(a) order', 'no `) : trioQuery.isError … ? (` branch in the card chain');
else if (!skeletonCond) fail('(a) order', 'no `) : trioQuery.isLoading || !trio ? (` skeleton branch');
else if (rookieEmpty < 0 || rookieEmpty > errorCond.index)
  fail('(a) order', 'the RookieScopeEmpty branch must stay first in the chain');
else if (errorCond.index > skeletonCond.index)
  fail('(a) order', 'the isError branch comes AFTER the `isLoading || !trio` skeleton, '
    + 'so a failed fetch shows the skeleton forever');
else ok('(a) error branch precedes the skeleton (RookieScopeEmpty still first)');

const body = errorCond ? branchBody(errorCond) : null;

// (b) Retry pressable
if (!body) fail('(b) retry', 'could not read the error branch body');
else {
  const pressable = /<(Button|Pressable)\b[^>]*?onPress=\{[^}]*trioQuery\.refetch\(/s.test(body);
  if (pressable) ok('(b) the error branch renders a pressable calling trioQuery.refetch');
  else fail('(b) retry', 'the error branch has no <Button>/<Pressable> whose onPress calls trioQuery.refetch()');
}

// (c) fixed copy; no error identifier, no .message
if (!body) fail('(c) copy', 'could not read the error branch body');
else {
  const errorRef = body.match(/\berror\b|\.message\b/g);
  if (errorRef)
    fail('(c) copy', `the error branch references ${[...new Set(errorRef)].join(', ')}; `
      + 'it must show only the fixed string');
  else if (!body.includes('Could not load next trio'))
    fail('(c) copy', 'the error branch must show the existing string "Could not load next trio"');
  else ok('(c) the error branch shows "Could not load next trio" and references no error/.message');
}

// (d) the condition is exactly trioQuery.isError
if (!errorCond) fail('(d) plain isError', 'no isError branch');
else if (errorCond[1].trim() !== '')
  fail('(d) plain isError', `the error condition has a conjunct \`${errorCond[1].trim()}\`; it must be `
    + 'exactly `trioQuery.isError` (P2-1: `&& !trio` hands back the just-ranked trio after a failed refetch)');
else ok('(d) the error condition is exactly trioQuery.isError');

// (e) nothing above the error branch shadows it
if (!errorCond) fail('(e) nothing above', 'no isError branch');
else {
  const above = chain.slice(0, errorCond.index);
  const shadows = [
    [/!trio\b/, '`!trio`'],
    [/!trioQuery\.data\b/, '`!trioQuery.data`'],
    [/\bisFetching\b/, '`isFetching`'],
    [/\bisLoading\b/, '`isLoading`'],
    [/skeleton/i, 'a skeleton'],
  ].filter(([re]) => re.test(above)).map(([, what]) => what);
  if (shadows.length)
    fail('(e) nothing above', `above the error branch: ${shadows.join(', ')}; a failed fetch would never reach it`);
  else ok('(e) no skeleton / !trio / isLoading / isFetching branch above the error branch');
}

// (f) Try again label
if (!body) fail('(f) label', 'could not read the error branch body');
else if (!/<(Button|Pressable)\b[^>]*?\blabel="Try again"/s.test(body))
  fail('(f) label', 'the error branch\'s Button must keep label="Try again"');
else ok('(f) the error branch\'s Button keeps label="Try again"');

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nall trios error-state checks passed');
