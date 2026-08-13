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
const {
  MATCH_UNLOCK_MATES,
  matchesUnlockRemaining,
  CONTRARIAN_UNLOCK_USERS,
  contrarianFoldLine,
} = moduleShim.exports;

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

// ═══ #308 — contrarianFoldLine (leaderboards/contrarian fold copy) ═══════
// The /api/league/contrarian gate counts users with stored rankings in the
// ACTIVE scoring format, caller INCLUDED. The shipped static copy ("…once 3
// leaguemates have ranked.") lied twice: wrong population word (the gate
// counts the caller — "members", matching the bar's "(you)" label) and no
// format clause (a mate ranked only in the other format doesn't count —
// the ffv3 report). These checks pin the three honesty properties.

function checkTruthy(name, cond, detail) {
  if (!cond) {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  } else {
    console.log(`ok    ${name}`);
  }
}

const sf1 = contrarianFoldLine(1, 'sf_tep');
const sf2 = contrarianFoldLine(2, 'sf_tep');
const qb1 = contrarianFoldLine(1, '1qb_ppr');
const nf1 = contrarianFoldLine(1, null);
const nn  = contrarianFoldLine(null, null);
const met = contrarianFoldLine(0, 'sf_tep');

// ── S1: not the shipped static string — live count + honest population ───
checkTruthy('S1 (1, sf_tep) names the live remaining count', sf1.includes('1 more to go'), sf1);
checkTruthy('S1 (1, sf_tep) says "members" (gate counts the caller)', sf1.includes('members'), sf1);
checkTruthy('S1 (1, sf_tep) does NOT say "leaguemates"', !sf1.includes('leaguemates'), sf1);

// ── S2: `needed` is consumed — different counts read differently ─────────
checkTruthy('S2 needed=1 and needed=2 produce different sentences', sf1 !== sf2, sf1);
checkTruthy('S2 needed=2 names its own count', sf2.includes('2 more to go'), sf2);

// ── S3: the format clause is present when known, absent when not ─────────
checkTruthy('S3 (1, sf_tep) names "SF TEP"', sf1.includes('SF TEP'), sf1);
checkTruthy('S3 (1, 1qb_ppr) names "1QB"', qb1.includes('1QB'), qb1);
checkTruthy(
  'S3 (1, null) names neither format label',
  !nf1.includes('SF TEP') && !nf1.includes('1QB'),
  nf1,
);
checkTruthy(
  'S3 (1, null) still parses as a sentence (ends "to go.")',
  nf1.endsWith('to go.'),
  nf1,
);
checkTruthy(
  'S3 (null, null) fallback still parses as a sentence (ends "ranked.")',
  nn.endsWith('ranked.'),
  nn,
);
checkTruthy(
  'S3 unknown format key degrades to no clause, not "in undefined"',
  !contrarianFoldLine(1, 'best_ball_2027').includes('undefined'),
  contrarianFoldLine(1, 'best_ball_2027'),
);

// ── S4: threshold pinned to the server's 3 ───────────────────────────────
check('S4 CONTRARIAN_UNLOCK_USERS = 3', CONTRARIAN_UNLOCK_USERS, 3);
for (const [label, s] of [['(1,sf_tep)', sf1], ['(null,null)', nn], ['(0,sf_tep)', met]]) {
  checkTruthy(`S4 output ${label} names the threshold 3`, s.includes('3 members'), s);
}

// ── Boundary: threshold met / stale-shape inputs never show a count ──────
checkTruthy('needed=0 (met) drops the remaining clause', !met.includes('more to go'), met);
checkTruthy('needed=null (stale shape) drops the remaining clause', !nn.includes('more to go'), nn);

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll league-unlock checks passed.');
