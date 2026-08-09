#!/usr/bin/env node
// Regression test for the mutual-match unlock threshold (#265 — League
// home told the operator "two more" members were needed when their league
// only had themselves; the real rule is: the viewing user + ONE other
// ranked leaguemate is enough for trade generation to produce mutual-gain
// matches, per backend/trade_service.py generate_trades():
//   eligible = [m for m in league.members if m.user_id != user_id and m.elo_ratings]
// — a single ranked opponent is eligible, so MATCH_UNLOCK_MATES must be 1,
// not 2 (which was borrowed from the unrelated 3-ranked-members contrarian/
// leaderboards threshold).
//
// Mobile has no jest harness, so this transpiles the REAL module
// (src/utils/leagueUnlocks.ts — pure by design, zero runtime imports) with
// the project's typescript and runs it under plain node — same idiom as
// check-feedback-badge.js / check-session-rerank.js.
//
// Run: node tests/check-league-unlocks.js  (or: npm run test:league-unlocks)

'use strict';

const fs = require('fs');
const path = require('path');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const srcPath = path.join(__dirname, '..', 'src', 'utils', 'leagueUnlocks.ts');
const source = fs.readFileSync(srcPath, 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

const moduleShim = { exports: {} };
new Function('module', 'exports', 'require', js)(moduleShim, moduleShim.exports, (name) => {
  throw new Error(
    `leagueUnlocks.ts gained a runtime import ("${name}") — it must stay pure ` +
      'so this check can run it under plain node.',
  );
});
const { MATCH_UNLOCK_MATES, matchesUnlockRemaining } = moduleShim.exports;

let failures = 0;
function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) {
    failures += 1;
    console.error(`FAIL  ${name}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  } else {
    console.log(`ok    ${name}`);
  }
}

// ── Threshold pin (#265) ─────────────────────────────────────────────────
// One additional ranked leaguemate is sufficient — NOT two.
check('MATCH_UNLOCK_MATES = 1', MATCH_UNLOCK_MATES, 1);

// ── Boundary: user alone in the league (0 ranked leaguemates) ───────────
// LeagueProgressModule renders `${remaining} more ranked leaguemate…` —
// singular/plural is `remaining === 1 ? '' : 's'` in that component, so
// remaining=1 here must read as "1 more ranked leaguemate" (singular).
check('user alone → 1 more ranked leaguemate needed', matchesUnlockRemaining(0), 1);

// ── Boundary: user + 1 ranked leaguemate — matches available ────────────
// remaining=0 ⇒ LeagueProgressModule's `remaining > 0` guard is false and
// the unlock sentence does not render at all (no message).
check('user + 1 ranked leaguemate → matches available (no message)', matchesUnlockRemaining(1), 0);

// ── Above threshold stays at 0, never negative ───────────────────────────
check('user + 2 ranked leaguemates → still 0 (not negative)', matchesUnlockRemaining(2), 0);

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll league-unlock checks passed.');
