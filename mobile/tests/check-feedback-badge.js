#!/usr/bin/env node
// Regression test for the FeedbackFAB badge math (#184).
//
// The badge must count only notes still awaiting action:
//   • no status yet (unsynced / statuses never fetched)  → counts
//   • new / planned / in_progress                        → counts
//   • fixed / shipped / declined (RESOLVED)              → excluded
//   • closed (hidden from the inbox list)                → excluded
//
// Mobile has no jest harness, so this transpiles the REAL module
// (src/utils/feedbackBadge.ts — pure by design, type-only imports) with the
// project's typescript and runs it under plain node.
//
// Run: node tests/check-feedback-badge.js   (or: npm run test:feedback-badge)
// Needs mobile/node_modules (for the typescript package) — `npm install`
// or the temporary node_modules symlink used for tsc checks.

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

const srcPath = path.join(__dirname, '..', 'src', 'utils', 'feedbackBadge.ts');
const source = fs.readFileSync(srcPath, 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

// CommonJS-style eval shim. feedbackBadge.ts must stay free of runtime
// imports; fail loudly if someone adds one.
const moduleShim = { exports: {} };
new Function('module', 'exports', 'require', js)(moduleShim, moduleShim.exports, (name) => {
  throw new Error(
    `feedbackBadge.ts gained a runtime import ("${name}") — it must stay pure ` +
      'so this check can run it under plain node.',
  );
});
const { openFeedbackCount, RESOLVED_FEEDBACK_STATUSES } = moduleShim.exports;

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

// ── Vocabulary pin ──────────────────────────────────────────────────────
check(
  'RESOLVED_FEEDBACK_STATUSES is exactly fixed/shipped/declined',
  [...RESOLVED_FEEDBACK_STATUSES].sort(),
  ['declined', 'fixed', 'shipped'],
);

// ── Counting rules ──────────────────────────────────────────────────────
check('empty inbox → 0', openFeedbackCount([]), 0);

check(
  'statusless (unsynced / never refreshed) notes count',
  openFeedbackCount([{}, { status: undefined }]),
  2,
);

check(
  'open statuses count',
  openFeedbackCount([{ status: 'new' }, { status: 'planned' }, { status: 'in_progress' }]),
  3,
);

check(
  'resolved statuses are excluded — including fixed (visible in the list, not the badge)',
  openFeedbackCount([{ status: 'fixed' }, { status: 'shipped' }, { status: 'declined' }]),
  0,
);

check(
  'closed notes are excluded even without a merged status',
  openFeedbackCount([{ closed: true }, { closed: true, status: 'new' }]),
  0,
);

check(
  'mixed inbox counts only actionable notes',
  openFeedbackCount([
    { status: 'new' },                 // counts
    { status: 'planned' },             // counts
    {},                                // counts (pending sync)
    { status: 'fixed' },               // badge-excluded, list-visible
    { status: 'shipped', closed: true }, // closed
    { status: 'declined', closed: true }, // closed
    { closed: true },                  // absent from /mine → closed
  ]),
  3,
);

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll feedback-badge checks passed.');
