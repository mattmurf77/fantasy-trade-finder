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
//       pickTeam (league-ID path) passes neither.
//   (c) platformEntry.ts, PlatformLinkSheet.tsx, EspnLinkSheet.tsx: no
//       track( / console.*( / AsyncStorage.*( / SecureStore.*( /
//       captureException( / Sentry.*( call has an argument mentioning
//       password, mflPass, pass, entryMflPassRef, espnS2, espn_s2, swid,
//       body, session_token, minted or res, or forwards the mint `args`
//       wholesale (release-lead P2, 2026-10-26). The guard is textual, so
//       sinks may only be CALLED directly: no alias, destructure, bind or
//       hand-off of a sink, and no globalThis / window / global / self route
//       to one (QA delta, 2026-10-26). Computed members (console['log'],
//       console[`log`]) are normalised before matching, and since variable
//       indirection can't be followed, console / AsyncStorage / SecureStore /
//       Sentry / captureException are banned outright in these files; only
//       track( remains, under the argument rule (second QA delta).
//   (d) EspnLinkSheet.tsx + PlatformLinkSheet.tsx: every onEntrySession(...)
//       call forwards `account_only` and `username` from the mint response,
//       and both prop types declare them as optional additions.
//   (e) Private MFL leagues (2026-10-26 follow-up): with a verified session
//       the entry sign-in path imports like the non-entry flow.
//       mflEntryPickLeague calls mint → mflAuthLink → mflAuthImport([this
//       league]), never the zero-auth linkPlatformLeague; mflAuthLink is
//       required (no swallowed catch); the password ref is cleared only
//       right after mflAuthLink succeeds (or when an expired sign-in sends
//       the flow back to input); each step is skipped on a retry once it has
//       succeeded; clearEntryMflSignIn drops the password and both progress
//       refs, and reset() calls it. release-lead P3s: the catch maps
//       isVerificationRequired to pickTeam's copy before the e.message
//       fallback, and a 200 whose `imported` lacks the tapped league shows
//       failed[].message and returns before setAuthResult / auth-done.
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

// ── (c) no analytics / log / storage / crash-report call sees a secret ────
//
// Sinks: track(, console.*(, AsyncStorage.*(, SecureStore.*(,
// captureException(, Sentry.*(. A sink call is flagged when any argument's
// text mentions a credential or a request body. No allow-list is needed
// today: the only sink calls in these files are platformEntry's three
// signin_* track() calls, which carry `method` / `error_code` only.

const SINK_CALLEE = /^(track|captureException|(console|AsyncStorage|SecureStore|Sentry)\.\w+)$/;
const SINK_ROOTS = new Set(['track', 'captureException', 'console', 'AsyncStorage', 'SecureStore', 'Sentry']);
const GLOBAL_OBJECTS = new Set(['globalThis', 'window', 'global', 'self']);
const LEAK_TERMS = [
  /password/i,
  /mflPass/,
  /\bpass\b/,
  /entryMflPassRef/,
  /espnS2/i,
  /espn_s2/i,
  /swid/i,
  /\bbody\b/,
  /^args$/, // the whole mint args object (carries the password)
  /\.\.\.\s*args\b/,
  // The mint response carries the session token (2026-10-26 QA delta).
  /session_token/i,
  /\bminted\b/,
  /\bres\b/,
];

// A sink root may only be CALLED directly: `track(…)` or `console.log(…)` /
// `console?.log(…)` / `console['log'](…)`. Any other expression use is an
// alias or a hand-off that the argument scan can't follow, e.g.
// `const l = console.log`, `const { log } = console`, `= console[…]`,
// `= track`, `= AsyncStorage`, `{ track }`, `.bind(console)`,
// `setTimeout(console.log, …)`. Declaration names, import specifiers,
// property names (`x.track`, `{ track: 1 }`) and type positions are not uses.
function isDirectSinkCall(id) {
  const p = id.parent;
  if (ts.isCallExpression(p) && p.expression === id) return true;
  if (
    (ts.isPropertyAccessExpression(p) || ts.isElementAccessExpression(p)) &&
    p.expression === id &&
    ts.isCallExpression(p.parent) &&
    p.parent.expression === p
  ) {
    return true;
  }
  return false;
}
function isNonUsePosition(id) {
  const p = id.parent;
  if (ts.isShorthandPropertyAssignment(p)) return false; // `{ track }` passes the value
  if (p && p.name === id) return true; // declarations, x.track, { track: … }, imports
  if (p && ts.isBindingElement(p) && p.propertyName === id) return true;
  for (let a = p; a; a = a.parent) {
    if (ts.isImportDeclaration(a) || ts.isTypeNode(a)) return true;
  }
  return false;
}
function sinkMisuses(sf) {
  return findAll(
    sf,
    (n) =>
      ts.isIdentifier(n) &&
      SINK_ROOTS.has(n.text) &&
      !isNonUsePosition(n) &&
      !isDirectSinkCall(n),
  );
}
// Variable indirection can't be followed syntactically
// (`const c = entryMflPassRef.current; console.log(c)` passes every textual
// argument rule), so the only safe rule is that these three files never use
// the log / storage / crash-report sinks at all — none do today. `track(`
// stays allowed: it is the analytics funnel, held to the argument rule.
const BANNED_ROOTS = new Set(['console', 'AsyncStorage', 'SecureStore', 'Sentry', 'captureException']);
function bannedSinkUses(sf) {
  return findAll(
    sf,
    (n) => ts.isIdentifier(n) && BANNED_ROOTS.has(n.text) && !isNonUsePosition(n),
  );
}
// Computed members read like dotted ones for SINK_CALLEE:
// console['log'] / console[`log`] / console?.['log'] → console.log.
function calleeText(call) {
  return call.expression
    .getText()
    .replace(/\?\.(?=\s*\[)/g, '')
    .replace(/\[\s*(['"`])(\w+)\1\s*\]/g, '.$2')
    .replace(/\?\./g, '.');
}
// `globalThis.console`, `window.console`, `globalThis['console']`, … — reach
// a sink through the global object, past the root-identifier rule.
function globalSinkAccess(sf) {
  return findAll(sf, (n) => {
    if (ts.isPropertyAccessExpression(n)) {
      return (
        ts.isIdentifier(n.expression) &&
        GLOBAL_OBJECTS.has(n.expression.text) &&
        SINK_ROOTS.has(n.name.text)
      );
    }
    if (ts.isElementAccessExpression(n)) {
      return (
        ts.isIdentifier(n.expression) &&
        GLOBAL_OBJECTS.has(n.expression.text) &&
        ts.isStringLiteralLike(n.argumentExpression) &&
        SINK_ROOTS.has(n.argumentExpression.text)
      );
    }
    return false;
  });
}

const sinkFiles = {
  'src/api/platformEntry.ts': entry,
  'src/components/PlatformLinkSheet.tsx': parse('src/components/PlatformLinkSheet.tsx'),
  'src/components/EspnLinkSheet.tsx': parse('src/components/EspnLinkSheet.tsx'),
};
const entryTracks = callsTo(entry, 'track');
assert(
  entryTracks.length >= 3,
  'platformEntry.ts still fires the signin_* track() calls',
  String(entryTracks.length),
);
for (const [rel, sf] of Object.entries(sinkFiles)) {
  const sinks = findAll(
    sf,
    (n) => ts.isCallExpression(n) && SINK_CALLEE.test(calleeText(n)),
  );
  const leaky = sinks.filter((c) =>
    c.arguments.some((a) => LEAK_TERMS.some((re) => re.test(a.getText()))),
  );
  assert(
    leaky.length === 0,
    `${path.basename(rel)}: no track/console/storage/crash-report call mentions a credential, a body or the mint response`,
    leaky.map((c) => c.getText().slice(0, 80)).join(' | '),
  );
  const misuses = sinkMisuses(sf);
  assert(
    misuses.length === 0,
    `${path.basename(rel)}: sinks are only called directly, never aliased, destructured or passed on`,
    misuses.map((n) => n.parent.getText().slice(0, 80)).join(' | '),
  );
  const globals = globalSinkAccess(sf);
  assert(
    globals.length === 0,
    `${path.basename(rel)}: no sink reached through globalThis / window / global / self`,
    globals.map((n) => n.getText().slice(0, 80)).join(' | '),
  );
  const banned = bannedSinkUses(sf);
  assert(
    banned.length === 0,
    `${path.basename(rel)}: never uses console / AsyncStorage / SecureStore / Sentry / captureException (indirection can't be followed)`,
    banned.map((n) => n.parent.getText().slice(0, 80)).join(' | '),
  );
}

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
}

// ── (e) the entry sign-in path: mint → auth-link → auth-import, retry-safe ──

// The statement of `block` that contains `node` (null if none does).
function stmtIn(block, node) {
  let n = node;
  while (n && n.parent !== block) n = n.parent;
  return n || null;
}
function enclosingIf(node, stop) {
  let n = node.parent;
  while (n && n !== stop) {
    if (ts.isIfStatement(n)) return n;
    n = n.parent;
  }
  return null;
}
function isAssign(n, left, right) {
  return (
    ts.isBinaryExpression(n) &&
    n.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
    n.left.getText() === left &&
    (right === undefined || n.right.getText() === right)
  );
}
// `if (!<flag>) { …<call>…; <flag> = true; … }` — the call is skipped on a
// retry once it has succeeded, and the flag is set only after it.
function gatedByFlag(call, flag, stop) {
  const ifs = call && enclosingIf(call, stop);
  if (!ifs || ifs.expression.getText() !== `!${flag}`) return false;
  const block = ifs.thenStatement;
  if (!ts.isBlock(block)) return false;
  const callIdx = block.statements.indexOf(stmtIn(block, call));
  const setIdx = block.statements.findIndex(
    (s) => ts.isExpressionStatement(s) && isAssign(s.expression, flag, 'true'),
  );
  return callIdx >= 0 && setIdx > callIdx;
}

if (pick) {
  const mint = callsTo(pick, 'entryPlatformMint')[0];
  const links = callsTo(pick, 'mflAuthLink');
  const imports = callsTo(pick, 'mflAuthImport');
  assert(
    callsTo(pick, 'linkPlatformLeague').length === 0,
    'mflEntryPickLeague never imports through the zero-auth linkPlatformLeague',
  );
  assert(
    links.length === 1 && imports.length === 1,
    'mflEntryPickLeague calls mflAuthLink once and mflAuthImport once',
    `${links.length} / ${imports.length}`,
  );
  const link = links[0];
  const imp = imports[0];
  assert(
    !!mint && !!link && !!imp && mint.pos < link.pos && link.pos < imp.pos,
    'the order is mint → mflAuthLink → mflAuthImport',
  );
  assert(
    !!imp && imp.arguments[0] && imp.arguments[0].getText() === '[lg.league_id]',
    'mflAuthImport imports exactly the tapped league ([lg.league_id])',
    imp && imp.arguments[0] ? imp.arguments[0].getText() : 'no argument',
  );
  assert(
    !!link && ts.isAwaitExpression(link.parent) &&
      findAll(pick, (n) => ts.isTryStatement(n)).length === 1,
    'mflAuthLink is awaited and not wrapped in its own (best-effort) try',
  );

  // Password lifetime: every direct clear sits right after the awaited
  // mflAuthLink, in the same block; the only other clear is the
  // mfl_auth_expired branch sending the flow back to input.
  const clears = findAll(pick, (n) => isAssign(n, 'entryMflPassRef.current', "''"));
  const linkStmt = link && link.parent && link.parent.parent;
  assert(
    clears.length === 1 &&
      !!linkStmt &&
      ts.isExpressionStatement(linkStmt) &&
      clears[0].parent.parent === linkStmt.parent &&
      clears[0].pos > linkStmt.pos,
    'entryMflPassRef is cleared only after mflAuthLink succeeds (same block, after the await)',
    `${clears.length} direct clear(s)`,
  );
  const helperCalls = callsTo(pick, 'clearEntryMflSignIn');
  // In the THEN branch: an else-branch call has the same nearest IfStatement.
  assert(
    helperCalls.every((c) => {
      const ifs = enclosingIf(c, pick);
      return (
        !!ifs &&
        /mfl_auth_expired/.test(ifs.expression.getText()) &&
        c.pos >= ifs.thenStatement.pos &&
        c.end <= ifs.thenStatement.end
      );
    }),
    'clearEntryMflSignIn is called only on the mfl_auth_expired branch',
  );
  const expired = findAll(
    pick,
    (n) => ts.isIfStatement(n) && /'mfl_auth_expired'/.test(n.expression.getText()),
  )[0];
  assert(
    !!expired &&
      ts.isCatchClause(expired.parent.parent) &&
      /clearEntryMflSignIn\(\)/.test(expired.thenStatement.getText()) &&
      /setStep\('input'\)/.test(expired.thenStatement.getText()) &&
      /Your MFL sign-in expired — sign in again\./.test(expired.thenStatement.getText()) &&
      expired.elseStatement &&
      /setError\(e\?\.message/.test(expired.elseStatement.getText()),
    "catch: mfl_auth_expired → back to input with the sign-in-expired copy, else e.message",
  );

  // release-lead P3: a message-less verification_required 403 maps to the
  // same friendly copy pickTeam uses, checked BEFORE the e.message fallback.
  const verify = expired && expired.elseStatement;
  const pickTeamFn = findFunction(sheet, 'pickTeam');
  const pickTeamCopy =
    pickTeamFn &&
    (pickTeamFn.getText().match(/isVerificationRequired\)\s*\{\s*setError\(('[^']+')\)/) || [])[1];
  assert(
    !!verify &&
      ts.isIfStatement(verify) &&
      verify.expression.getText().replace(/\s+/g, ' ') ===
        'e instanceof ApiError && e.isVerificationRequired' &&
      !!pickTeamCopy &&
      new RegExp(`setError\\(${pickTeamCopy.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\)`).test(
        verify.thenStatement.getText(),
      ) &&
      !!verify.elseStatement &&
      /setError\(e\?\.message/.test(verify.elseStatement.getText()),
    "catch: isVerificationRequired → pickTeam's copy, before the e.message fallback",
    pickTeamCopy || 'pickTeam copy not found',
  );

  // release-lead P3: a 200 whose `imported` lacks the tapped league is a
  // FAILURE — show its failed[].message, stay on the list (return before
  // any step change), and only otherwise reach setAuthResult / auth-done.
  const guard = findAll(
    pick,
    (n) => ts.isIfStatement(n) && /res\.imported/.test(n.expression.getText()),
  )[0];
  const guardThen = guard && ts.isBlock(guard.thenStatement) ? guard.thenStatement : null;
  const setAuth = callsTo(pick, 'setAuthResult');
  const toDone = findAll(
    pick,
    (n) => ts.isCallExpression(n) && n.getText() === "setStep('auth-done')",
  );
  assert(
    !!guard && !!guardThen && !!imp &&
      /^!res\.imported\.some\(/.test(guard.expression.getText()) &&
      /lg\.league_id/.test(guard.expression.getText()) &&
      guard.pos > imp.pos &&
      !guard.elseStatement &&
      /res\.failed\.find\([\s\S]*lg\.league_id/.test(guardThen.getText()) &&
      /setError\([^)]*\.message/.test(guardThen.getText()) &&
      ts.isReturnStatement(guardThen.statements[guardThen.statements.length - 1]) &&
      !/setStep|setAuthResult|clearEntryMflSignIn/.test(guardThen.getText()),
    'a 200 without the tapped league in `imported` shows failed.message and stays on the list',
  );
  assert(
    !!guard && setAuth.length === 1 && toDone.length === 1 &&
      setAuth[0].getStart() > guard.end && toDone[0].getStart() > guard.end,
    'setAuthResult / auth-done come only after the per-league failure guard',
  );

  // Retry safety.
  assert(
    gatedByFlag(mint, 'entryMflMintedRef.current', pick),
    'the mint runs only while entryMflMintedRef is false, and sets it after',
  );
  assert(
    gatedByFlag(link, 'entryMflAuthLinkedRef.current', pick),
    'mflAuthLink runs only while entryMflAuthLinkedRef is false, and sets it after',
  );
  assert(
    !!imp && !enclosingIf(imp, pick),
    'mflAuthImport is not gated, so a retry re-runs only the import',
  );
}

const clearFn = findFunction(sheet, 'clearEntryMflSignIn');
assert(
  !!clearFn &&
    ['entryMflPassRef.current', 'entryMflMintedRef.current', 'entryMflAuthLinkedRef.current'].every(
      (ref) =>
        findAll(clearFn, (n) => isAssign(n, ref, ref === 'entryMflPassRef.current' ? "''" : 'false'))
          .length === 1,
    ),
  'clearEntryMflSignIn drops the password and both progress refs',
);
const resetFn = findFunction(sheet, 'reset');
assert(
  !!resetFn && callsTo(resetFn, 'clearEntryMflSignIn').length === 1,
  'reset() calls clearEntryMflSignIn',
);

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
