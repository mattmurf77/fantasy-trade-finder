#!/usr/bin/env node
// MFL entry sign-in proof, client half — structural regression test
// (2026-10-26, platforms-eng ESPN/MFL sign-in design §3, the 11-06 binary).
//
// WHY THIS EXISTS. The server's team-claim mint (POST /api/entry/platform)
// is becoming "prove, then sign in": for MFL the proof is the user's MFL
// login, sent inline with the mint. Only the sign-in path holds that login,
// so the client must (1) put it in the mint body, only as a pair, (2) pass
// it from the sheet's sign-in path and NOT from the league-ID path, and
// (3) never let the password reach analytics. The mint also starts
// returning a verified account session, so (4) both entry sheets forward
// `account_only` / `username` from the mint to the host's onEntrySession.
//
//   (a) platformEntry.ts: the `mfl` mint body spreads `username` /
//       `password` behind a both-present condition, and nowhere else in the
//       mint body; the ESPN body carries neither.
//   (b) PlatformLinkSheet.tsx: mflEntryPickLeague (sign-in path) passes
//       `username` + `password` (from entryMflPassRef) to entryPlatformMint;
//       pickTeam (league-ID path) passes neither; the ref is still cleared.
//   (c) platformEntry.ts: no track( or console. call references `password`
//       or forwards `args` wholesale.
//   (d) EspnLinkSheet.tsx + PlatformLinkSheet.tsx: every onEntrySession(...)
//       call forwards `account_only` and `username` from the mint response,
//       and both prop types declare them as optional additions.
//
// Run: node tests/check-mfl-entry-proof.js

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

let failures = 0;
function ok(name) {
  console.log(`PASS  ${name}`);
}
function fail(name, detail) {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
}
function assert(cond, name, detail) {
  if (cond) ok(name);
  else fail(name, detail);
}

function parse(rel) {
  const file = path.join(__dirname, '..', rel);
  return ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
}

function walk(node, visit) {
  visit(node);
  node.forEachChild((c) => walk(c, visit));
}

function findAll(root, pred) {
  const out = [];
  walk(root, (n) => {
    if (pred(n)) out.push(n);
  });
  return out;
}

function findFunction(root, name) {
  return findAll(
    root,
    (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === name,
  )[0];
}

// Calls whose callee text is `name` (or `name?.` for optional calls).
function callsTo(root, name) {
  return findAll(
    root,
    (n) =>
      ts.isCallExpression(n) &&
      n.expression.getText().replace(/\?\.$/, '') === name,
  );
}

function propNames(obj) {
  return obj.properties
    .filter((p) => ts.isPropertyAssignment(p) || ts.isShorthandPropertyAssignment(p))
    .map((p) => p.name.getText());
}

function prop(obj, name) {
  return obj.properties.find(
    (p) =>
      (ts.isPropertyAssignment(p) || ts.isShorthandPropertyAssignment(p)) &&
      p.name.getText() === name,
  );
}

// The object literal carrying `platform: '<p>'` inside a node.
function bodyFor(root, platform) {
  return findAll(
    root,
    (n) =>
      ts.isObjectLiteralExpression(n) &&
      n.properties.some(
        (p) =>
          ts.isPropertyAssignment(p) &&
          p.name.getText() === 'platform' &&
          p.initializer.getText() === `'${platform}'`,
      ),
  )[0];
}

// ── (a) the mint body ─────────────────────────────────────────────────────

const entry = parse('src/api/platformEntry.ts');
const mint = findFunction(entry, 'entryPlatformMint');
assert(!!mint, 'platformEntry.ts declares entryPlatformMint');

if (mint) {
  // The mfl variant of `args` declares the optional pair.
  const param = mint.parameters[0];
  const mflArgs = param
    ? findAll(
        param,
        (n) =>
          ts.isTypeLiteralNode(n) &&
          /platform:\s*'mfl'/.test(n.getText()),
      )[0]
    : null;
  assert(
    !!mflArgs &&
      /username\?:\s*string/.test(mflArgs.getText()) &&
      /password\?:\s*string/.test(mflArgs.getText()),
    "mfl args variant declares optional username?/password?",
  );

  const mflBody = bodyFor(mint, 'mfl');
  const espnBody = bodyFor(mint, 'espn');
  assert(!!mflBody, "mint builds an object literal with platform: 'mfl'");
  assert(!!espnBody, "mint builds an object literal with platform: 'espn'");

  if (mflBody) {
    // No bare username/password properties on the mfl body itself — they
    // may only arrive through the guarded spread.
    const bare = propNames(mflBody).filter((n) => n === 'username' || n === 'password');
    assert(
      bare.length === 0,
      'mfl mint body has no unguarded username/password property',
      bare.join(', '),
    );

    const guarded = mflBody.properties.filter((p) => {
      if (!ts.isSpreadAssignment(p)) return false;
      let e = p.expression;
      while (ts.isParenthesizedExpression(e)) e = e.expression;
      if (!ts.isConditionalExpression(e)) return false;
      const cond = e.condition.getText().replace(/\s+/g, ' ');
      const bothPresent =
        /^args\.username && args\.password$/.test(cond) ||
        /^args\.password && args\.username$/.test(cond);
      let whenTrue = e.whenTrue;
      while (ts.isParenthesizedExpression(whenTrue)) whenTrue = whenTrue.expression;
      let whenFalse = e.whenFalse;
      while (ts.isParenthesizedExpression(whenFalse)) whenFalse = whenFalse.expression;
      return (
        bothPresent &&
        ts.isObjectLiteralExpression(whenTrue) &&
        prop(whenTrue, 'username') &&
        prop(whenTrue, 'password') &&
        prop(whenTrue, 'username').initializer &&
        prop(whenTrue, 'username').initializer.getText() === 'args.username' &&
        prop(whenTrue, 'password').initializer.getText() === 'args.password' &&
        ts.isObjectLiteralExpression(whenFalse) &&
        whenFalse.properties.length === 0
      );
    });
    assert(
      guarded.length === 1,
      'mfl mint body spreads { username, password } behind args.username && args.password',
      `found ${guarded.length}`,
    );
  }

  if (espnBody) {
    assert(
      !/\b(username|password)\b/.test(espnBody.getText()),
      'espn mint body carries no username/password (ESPN variant unchanged)',
    );
  }
}

// ── (c) no analytics / console call sees the password ─────────────────────

const sinkCalls = findAll(
  entry,
  (n) =>
    ts.isCallExpression(n) &&
    (n.expression.getText() === 'track' ||
      /^console\.\w+$/.test(n.expression.getText())),
);
assert(
  sinkCalls.filter((c) => c.expression.getText() === 'track').length >= 3,
  'platformEntry.ts still fires the signin_* track() calls',
  String(sinkCalls.length),
);
const leaky = sinkCalls.filter((c) =>
  c.arguments.some((a) => {
    const t = a.getText();
    return /password/i.test(t) || /^args$/.test(t) || /\.\.\.\s*args\b/.test(t);
  }),
);
assert(
  leaky.length === 0,
  'no track( / console. call in platformEntry.ts references password or forwards args',
  leaky.map((c) => c.getText().slice(0, 80)).join(' | '),
);

// ── (b) the sheet passes the login on the sign-in path only ───────────────

const sheet = parse('src/components/PlatformLinkSheet.tsx');
const pick = findFunction(sheet, 'mflEntryPickLeague');
assert(!!pick, 'PlatformLinkSheet declares mflEntryPickLeague');
if (pick) {
  const mints = callsTo(pick, 'entryPlatformMint');
  assert(mints.length === 1, 'mflEntryPickLeague calls entryPlatformMint once', String(mints.length));
  const arg = mints[0] && mints[0].arguments[0];
  const isObj = arg && ts.isObjectLiteralExpression(arg);
  const user = isObj && prop(arg, 'username');
  const pass = isObj && prop(arg, 'password');
  assert(
    !!user && /mflUser/.test(user.getText()),
    'mflEntryPickLeague passes username (from mflUser) to the mint',
  );
  assert(
    !!pass && /entryMflPassRef\.current/.test(pass.getText()),
    'mflEntryPickLeague passes password (from entryMflPassRef) to the mint',
  );
  // The ref is still dropped in this function (lifetime unchanged).
  assert(
    /entryMflPassRef\.current\s*=\s*''/.test(pick.getText()),
    'mflEntryPickLeague still clears entryMflPassRef',
  );
}

const leagueIdPick = findFunction(sheet, 'pickTeam');
assert(!!leagueIdPick, 'PlatformLinkSheet declares pickTeam (league-ID path)');
if (leagueIdPick) {
  const mints = callsTo(leagueIdPick, 'entryPlatformMint');
  assert(mints.length === 1, 'pickTeam calls entryPlatformMint once', String(mints.length));
  assert(
    mints.every((c) => !/\b(username|password)\b/.test(c.getText())),
    'pickTeam (league-ID path) passes no username/password to the mint',
  );
}

// ── (d) both sheets forward account_only / username ───────────────────────

for (const rel of ['src/components/PlatformLinkSheet.tsx', 'src/components/EspnLinkSheet.tsx']) {
  const sf = rel === 'src/components/PlatformLinkSheet.tsx' ? sheet : parse(rel);
  const label = path.basename(rel);

  const propType = findAll(
    sf,
    (n) =>
      ts.isPropertySignature(n) &&
      n.name.getText() === 'onEntrySession',
  )[0];
  const typeText = propType ? propType.getText().replace(/\s+/g, ' ') : '';
  assert(
    /user_id: string;/.test(typeText) &&
      /display_name: string;/.test(typeText) &&
      /account_only\?: boolean;/.test(typeText) &&
      /username\?: string;/.test(typeText),
    `${label}: onEntrySession type adds optional account_only/username to user_id/display_name`,
    typeText,
  );

  const calls = callsTo(sf, 'onEntrySession');
  assert(calls.length >= 1, `${label}: calls onEntrySession`, String(calls.length));
  const missing = calls.filter((c) => {
    const a = c.arguments[0];
    if (!a || !ts.isObjectLiteralExpression(a)) return true;
    const ao = prop(a, 'account_only');
    const un = prop(a, 'username');
    return !(
      ao && ao.initializer && ao.initializer.getText() === 'minted.account_only' &&
      un && un.initializer && un.initializer.getText() === 'minted.username'
    );
  });
  assert(
    missing.length === 0,
    `${label}: every onEntrySession call forwards minted.account_only and minted.username`,
    `${missing.length} of ${calls.length} do not`,
  );
}

process.exit(failures ? 1 : 0);
