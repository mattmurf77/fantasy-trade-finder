#!/usr/bin/env node
// Trios error state (B6, rankings-pm review 2026-10-27).
//
// WHY THIS EXISTS. RankScreen's card area is one ternary chain. It tested the
// skeleton condition `trioQuery.isLoading || !trio` BEFORE `trioQuery.isError`.
// A failed /api/trio (5xx, timeout, 403) leaves `trio` undefined, so the
// skeleton matched first and showed forever, and the error branch with its
// Retry could never render. The user was stuck on three grey boxes.
//
// This pins the fixed order and the error branch's contents:
//   (a) the RookieScopeEmpty branch stays first, and the error condition comes
//       BEFORE the `isLoading || !trio` skeleton condition;
//   (b) the error branch renders a pressable (chalkline Button / Pressable)
//       whose onPress calls `trioQuery.refetch`;
//   (c) the error branch shows the app's fixed string "Could not load next
//       trio" and never renders `error.message`;
//   (d) the error condition also requires `!trio`, so a failed BACKGROUND
//       refetch that still holds a trio keeps showing the cards.
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

// The card-area chain starts at `{trioEmpty ? (`.
const chainStart = src.indexOf('{trioEmpty ? (');
if (chainStart < 0) {
  fail('locate chain', 'no `{trioEmpty ? (` in RankScreen.tsx: the card chain moved; update this guard');
  process.exit(1);
}
const chain = src.slice(chainStart);

const errorCond = /\)\s*:\s*trioQuery\.isError\b([^?]*)\?\s*\(/.exec(chain);
const skeletonCond = /\)\s*:\s*trioQuery\.isLoading\s*\|\|\s*!trio\s*\?\s*\(/.exec(chain);
const rookieEmpty = chain.indexOf('<RookieScopeEmpty');

// Body of a `? ( … )` branch: from its opening paren to the matching close,
// with comments removed (a comment may mention error.message by name).
function branchBody(match) {
  const open = match.index + match[0].length - 1;          // the `(` after `?`
  let depth = 0;
  for (let i = open; i < chain.length; i += 1) {
    if (chain[i] === '(') depth += 1;
    else if (chain[i] === ')') {
      depth -= 1;
      if (depth === 0) {
        return chain.slice(open + 1, i)
          .replace(/\/\*[\s\S]*?\*\//g, '')
          .replace(/(^|[^:])\/\/.*$/gm, '$1');
      }
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

// (c) fixed copy, never error.message
if (!body) fail('(c) copy', 'could not read the error branch body');
else if (/\berror\.message\b/.test(body))
  fail('(c) copy', 'the error branch renders error.message; it must show the fixed string');
else if (!body.includes('Could not load next trio'))
  fail('(c) copy', 'the error branch must show the existing string "Could not load next trio"');
else ok('(c) the error branch shows "Could not load next trio", never error.message');

// (d) cached data wins over a failed background refetch
if (!errorCond) fail('(d) cached trio', 'no isError branch');
else if (!/&&\s*!trio\b/.test(errorCond[1]))
  fail('(d) cached trio', 'the error condition must be `trioQuery.isError && !trio`, so a held trio keeps showing');
else ok('(d) the error condition requires !trio (a cached trio survives a failed refetch)');

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nall trios error-state checks passed');
