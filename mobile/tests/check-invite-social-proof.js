#!/usr/bin/env node
// P1-5 (audit A-14) — regression test for the invite social-proof formatter.
//
// This one function decides BOTH whether an invite CTA renders and what it
// says, on three surfaces (League Home card, Matches empty state, the
// inline-link suppression) plus the invite_cta_shown impression guard. If a
// branch here is wrong, either a CTA appears asking a user to invite people
// who already joined, or the impression denominator counts screens that
// never showed a CTA. Both are silent failures.
//
// Mobile has no jest harness, so this transpiles the REAL module
// (src/utils/inviteSocialProof.ts — pure by design, zero runtime imports)
// with the project's typescript and runs it under plain node — same idiom
// as check-league-unlocks.js / check-feedback-badge.js.
//
// Run: node tests/check-invite-social-proof.js

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

const srcPath = path.join(__dirname, '..', 'src', 'utils', 'inviteSocialProof.ts');
const source = fs.readFileSync(srcPath, 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

const moduleShim = { exports: {} };
new Function('module', 'exports', 'require', js)(moduleShim, moduleShim.exports, (name) => {
  throw new Error(
    `inviteSocialProof.ts gained a runtime import ("${name}") — it must stay pure ` +
      'so this check can run it under plain node.',
  );
});
const { inviteSocialProof, INVITE_RATIONALE } = moduleShim.exports;

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

// ── C7 — the ordinary case, plural ──────────────────────────────────────
// 11 leaguemates, 2 joined ⇒ 9 have not. The number is DERIVED from the
// /api/league/summary aggregate, never fabricated.
check(
  '11 total / 2 joined → plural sentence',
  inviteSocialProof(11, 2),
  "9 of your 11 leaguemates haven't joined yet",
);

// ── C6 — singular verb. "1 … haven't" is the classic off-by-one tell ────
check(
  '11 total / 10 joined → singular verb',
  inviteSocialProof(11, 10),
  "1 of your 11 leaguemates hasn't joined yet",
);

// ── C5 — a two-person league. "1 of your 1 leaguemates" reads as a bug ──
check(
  '1 total / 0 joined → single-leaguemate phrasing',
  inviteSocialProof(1, 0),
  "Your leaguemate hasn't joined yet",
);

// ── C4 — everyone joined ⇒ NO card, NO event (D-P1-13 · PR-10) ──────────
check('everyone joined → null (card absent, not congratulatory)', inviteSocialProof(11, 11), null);

// ── C2 — solo / unknown league ──────────────────────────────────────────
check('0 leaguemates → null', inviteSocialProof(0, 0), null);
check('negative total → null', inviteSocialProof(-1, 0), null);

// ── C1 — non-finite input is never guessed at ───────────────────────────
check('NaN total → null', inviteSocialProof(NaN, 2), null);
check('NaN joined → null', inviteSocialProof(11, NaN), null);
check('Infinity → null', inviteSocialProof(Infinity, 2), null);

// ── C3 — impossible inputs are defended, not rendered ───────────────────
check('joined > total → null', inviteSocialProof(5, 9), null);
check('negative joined → null', inviteSocialProof(11, -1), null);

// ── Trailing punctuation stays OUT of the returned string ───────────────
// Maestro `text:` matchers are full-match regex and `.` is a wildcard, so a
// sentence-final period inside the literal quietly weakens every assertion
// written against it.
check(
  'no trailing period',
  /[.!?]$/.test(inviteSocialProof(11, 2)),
  false,
);

// ── The rationale is the user's OWN incentive, not an appeal to altruism
// (D-P1-13 · PR-5 operator copy direction) and never names an individual.
check('rationale is a non-empty string', typeof INVITE_RATIONALE === 'string' && INVITE_RATIONALE.length > 0, true);

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll invite social-proof checks passed.');
