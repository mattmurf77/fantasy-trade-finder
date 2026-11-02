#!/usr/bin/env node
// Entry-mint identity — structural guard (SignInScreen.handleEntrySession).
//
// The sessionless ESPN/MFL entry mint (POST /api/entry/platform) returns the
// user it minted. For a bare platform identity that is an `acct_*` account
// with no Sleeper username, and the host pins it `account_only: true` so
// LeaguePicker skips the Sleeper league fetch. But an identity that is BOUND
// to a Sleeper user comes back `account_only: false` with the Sleeper
// username (server #430; both sheets forward the fields on #421). A host that
// hard-codes `account_only: true` / `username: ''` pins that user as
// account-only anyway, and LeaguePicker (`user.account_only ? [] : await
// getLeagues(...)`) then never loads their Sleeper leagues.
//
//   1. The handler's parameter type accepts the optional `account_only` and
//      `username` — without them TypeScript rejects reading the fields, and
//      the optional params keep this compiling before the sheets' prop type
//      declares them.
//   2. The handler pins `u.account_only ?? true` and `u.username ?? ''` —
//      the minted values win, and a mint that omits them (older server, or a
//      bare platform identity) keeps today's account-only default.
//   3. No literal `account_only: true` / `username: ''` is left in the
//      handler: that is the bug this guard exists for.
//   4. Both entry sheets are still wired to the handler, and LeaguePicker
//      still keys its Sleeper fetch on `user.account_only` (the coupling that
//      makes (2) load-bearing).
//
// Run: node tests/check-entry-session-identity.js
//   (or: npm run test:entry-session-identity)

'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}
function read(rel) {
  return fs.readFileSync(path.join(__dirname, '..', 'src', rel), 'utf8');
}

const signIn = read('screens/SignInScreen.tsx');
const picker = read('screens/LeaguePickerScreen.tsx');

const fn = signIn.match(
  /async function handleEntrySession\(([\s\S]*?)\) \{\n([\s\S]*?)\n  \}\n/,
);
assert(!!fn, 'handleEntrySession is parseable');
const params = fn ? fn[1] : '';
const body = fn ? fn[2] : '';

// ── 1. parameter type ────────────────────────────────────────────────────
assert(
  /\baccount_only\?: boolean;/.test(params) && /\busername\?: string;/.test(params),
  '1. the parameter type gains optional account_only and username',
  params.replace(/\s+/g, ' ').trim(),
);

// ── 2. the minted values win; omission keeps the account-only default ────
assert(
  /\baccount_only: u\.account_only \?\? true,/.test(body),
  '2. pins account_only: u.account_only ?? true',
);
assert(
  /\busername: u\.username \?\? '',/.test(body),
  "2. pins username: u.username ?? ''",
);

// ── 3. no hard-coded pin survives ────────────────────────────────────────
assert(
  !/\baccount_only: true\b/.test(body),
  '3. no literal `account_only: true` left in the handler',
);
assert(
  !/\busername: ''/.test(body),
  "3. no literal `username: ''` left in the handler",
);

// ── 4. wiring + the consumer that makes this load-bearing ────────────────
assert(
  (signIn.match(/onEntrySession=\{handleEntrySession\}/g) || []).length === 2,
  '4. both entry sheets (ESPN, MFL) deliver the mint to handleEntrySession',
);
assert(
  /user\.account_only \? \[\] : await getLeagues\(user\.user_id\)/.test(picker),
  "4. LeaguePicker still skips the Sleeper fetch only for an account_only user",
);

if (failures) {
  console.error(`\n${failures} failure(s)`);
  process.exit(1);
}
console.log('\nOK');
