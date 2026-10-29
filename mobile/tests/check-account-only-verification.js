#!/usr/bin/env node
// Account-only sessions get `verification` (head-eng 2026-10-28).
//
// An account-only session (Apple-first, no league) pins the NO_LEAGUE_ID
// sentinel, so it never reaches session/init, until now the only source of
// useSession.verification. It stayed null for good, so #495's Restore row
// couldn't be strict (render nothing while unknown) without hiding Restore
// from exactly the accounts App Review creates. GET /api/session/ping now
// returns the same `verification` field, and the client asks it.
//
// Pins (AST):
//   1. api/auth.ts exports refreshVerification(): it calls sessionPing(), and
//      records res.verification only when the answer's user_id is the user it
//      asked for AND that user is still signed in; a failure is swallowed.
//   2. sessionPing()'s declared result carries `verification`.
//   3. useSession.revalidateSession's NO_LEAGUE_ID branch fires
//      refreshVerification() without awaiting it, then returns (never
//      initLeagueSession): callers chain foreground work on revalidateSession
//      (release-lead #524 QA P3-2).
//   4. SignInScreen's account-only Apple branch calls refreshVerification()
//      after it pins the sentinel league.
//   5. useSession.setUser resets `verification` to null whenever the user_id
//      changes, in the same set() that stores the new user, so the previous
//      user's answer never carries over (release-lead #524 QA, an expiry then
//      a different user's sign-in).
//
// Run: node tests/check-account-only-verification.js

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

const ROOT = process.env.FTF_MOBILE_TEST_ROOT || path.resolve(__dirname, '..');
const parse = (rel) => ts.createSourceFile(rel, fs.readFileSync(path.join(ROOT, rel), 'utf8'),
  ts.ScriptTarget.Latest, true, rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);

let failures = 0;
let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`PASS  ${name}`);
  } catch (e) {
    failures += 1;
    console.error(`FAIL  ${name}\n      ${e.message}`);
  }
}
function expect(cond, msg) { if (!cond) throw new Error(msg); }
function findAll(root, pred) {
  const out = [];
  (function walk(n) {
    if (pred(n)) out.push(n);
    ts.forEachChild(n, walk);
  })(root);
  return out;
}
const flat = (n, sf) => n.getText(sf).replace(/\s+/g, ' ');
const isCallTo = (n, name) => ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === name;

const auth = parse('src/api/auth.ts');
const session = parse('src/state/useSession.ts');
const signIn = parse('src/screens/SignInScreen.tsx');

check('1. refreshVerification asks ping, and records only for the same, still-signed-in user', () => {
  const fn = findAll(auth, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === 'refreshVerification')[0];
  expect(fn && fn.modifiers && fn.modifiers.some((m) => m.kind === ts.SyntaxKind.ExportKeyword),
    'api/auth.ts exports no refreshVerification()');
  const body = flat(fn.body, auth);
  expect(/const askedFor = useSession\.getState\(\)\.user\?\.user_id \?\? null;/.test(body),
    'it does not capture the user it asks for');
  expect(findAll(fn, (n) => isCallTo(n, 'sessionPing')).length === 1, 'it does not call sessionPing() once');
  const set = body.indexOf('setVerification(res.verification)');
  const sameAnswer = body.indexOf('res.user_id !== askedFor) return;');
  const stillSigned = body.indexOf('useSession.getState().user?.user_id !== askedFor) return;');
  expect(set > -1, 'it never records res.verification');
  expect(sameAnswer > -1 && sameAnswer < set, 'it records without checking the answer is for the user it asked for');
  expect(stillSigned > -1 && stillSigned < set, 'it records without checking that user is still signed in');
  const tries = findAll(fn, ts.isTryStatement);
  expect(tries.length === 1 && tries[0].catchClause && flat(tries[0].tryBlock, auth).includes('sessionPing()'),
    'the ping is not inside a try with a catch (a failure must keep the current state)');
});

check('2. sessionPing declares `verification` in its result', () => {
  const fn = findAll(auth, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === 'sessionPing')[0];
  expect(fn && fn.type && /verification\?: SessionVerification/.test(flat(fn.type, auth)),
    `sessionPing's result type is ${fn && fn.type ? flat(fn.type, auth) : 'missing'}`);
});

check('3. revalidateSession\'s sentinel branch fires refreshVerification unawaited, then returns', () => {
  const prop = findAll(session, (n) => ts.isPropertyAssignment(n) && n.name.getText(session) === 'revalidateSession')[0];
  expect(prop, 'no revalidateSession');
  const ifs = findAll(prop, (n) => ts.isIfStatement(n)
    && flat(n.expression, session) === 'league.league_id === NO_LEAGUE_ID');
  expect(ifs.length === 1, `${ifs.length} NO_LEAGUE_ID branch(es) in revalidateSession, want 1`);
  const then = ifs[0].thenStatement;
  expect(ts.isBlock(then) && then.statements.length === 2, 'the sentinel branch is not { void refreshVerification(); return; }');
  expect(flat(then.statements[0], session) === 'void refreshVerification();', `its first statement is: ${flat(then.statements[0], session)}`);
  expect(ts.isReturnStatement(then.statements[1]), 'it does not return after refreshing');
  const init = findAll(prop, (n) => isCallTo(n, 'initializeLeagueSession'))[0];
  expect(init && init.pos > ifs[0].end, 'initializeLeagueSession runs before the sentinel branch');
});

check('4. the account-only Apple sign-in asks for verification after pinning the sentinel', () => {
  const branch = findAll(signIn, (n) => ts.isIfStatement(n)
    && flat(n.expression, signIn) === 'res.account_only && res.user_id && res.session_token')[0];
  expect(branch, 'no account-only branch in SignInScreen');
  const block = branch.thenStatement;
  const pin = findAll(block, (n) => isCallTo(n, 'setLeague'))[0];
  const refresh = findAll(block, (n) => isCallTo(n, 'refreshVerification'));
  expect(refresh.length === 1, `${refresh.length} refreshVerification() call(s) in the branch, want 1`);
  expect(pin && refresh[0].pos > pin.end, 'refreshVerification() runs before the sentinel league is pinned');
});

check('5. setUser resets verification when the user_id changes', () => {
  const prop = findAll(session, (n) => ts.isPropertyAssignment(n) && n.name.getText(session) === 'setUser')[0];
  expect(prop, 'no setUser');
  const conds = findAll(prop, (n) => ts.isConditionalExpression(n)
    && flat(n.condition, session) === 'previous?.user_id === u?.user_id');
  expect(conds.length === 1, `${conds.length} \`previous?.user_id === u?.user_id\` choice(s) in setUser, want 1`);
  const sets = findAll(prop, (n) => isCallTo(n, 'set'));
  expect(sets.length === 1 && sets[0].arguments[0] === conds[0],
    'the user is not stored by exactly one set() whose argument is that choice');
  const same = flat(conds[0].whenTrue, session);
  const changed = flat(conds[0].whenFalse, session);
  expect(!/verification/.test(same), `the same-user branch touches verification: ${same}`);
  expect(/^\{user: u, switching: false, verification: null\}$/.test(changed),
    `the changed-user branch is ${changed}, want {user: u, switching: false, verification: null}`);
  const getUser = findAll(prop, (n) => ts.isVariableDeclaration(n) && n.name.getText(session) === 'previous')[0];
  expect(getUser && flat(getUser.initializer, session) === 'get().user' && getUser.end < sets[0].pos,
    '`previous` is not get().user read before the set()');
});

console.log(failures === 0
  ? `\nAll account-only verification checks passed (${passed}).`
  : `\n${failures} account-only verification check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
