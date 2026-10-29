#!/usr/bin/env node
// Every mobile session-init body carries the invite id (referral FR-12 / AC-12,
// launch slice B3).
//
// WHY THIS EXISTS. Token attribution (FR-13) credits an inviter only when the
// invitee's FIRST session init carries `invite_id`. The body is composed in
// several places — two Sleeper bodies plus the ESPN / MFL / Fleaflicker
// builder results, each on two paths (initLeagueSession and
// buildSessionInitBody) — and a path that forgets the field fails silently:
// the invite still "works", the league still opens, and the referral is
// simply never credited. Nothing in tsc sees that (`invite_id` is optional),
// and D-056 left no simulator to notice. So:
//
//   a. ONE POST. Exactly one call in mobile/src passes '/api/session/init',
//      and it sits inside `sessionInit()` in api/auth.ts.
//   b. EVERY BODY. Starting from that POST, every body is traced back
//      through its call sites — variables, `await`, object spreads, the
//      pass-through parameters of sessionInit/submitSessionInit (so their
//      callers anywhere in mobile/src are traced too), and auth.ts functions
//      that return a body — to the object literal where it is COMPOSED.
//      Each composition must spread `...inviteIdField()` exactly once. A body
//      taken straight from another module's builder (api/espn.ts,
//      api/platformLink.ts) is not composed in auth.ts and fails: it must be
//      wrapped as `{ ...(await builder()), ...inviteIdField() }` at the call
//      site. Every auth.ts function DECLARED to return a SessionInitBody is
//      traced too, whether or not anything calls it today.
//      And every `inviteIdField()` call in mobile/src must be one of those
//      compositions: no stray second consumer, no double spread.
//   c. THE HELPER. `inviteIdField` is lifted out of auth.ts, transpiled and
//      EXECUTED against a stub store: it calls `consumeInviteId()` once per
//      call, returns `{ invite_id }` for an id, and returns an object with NO
//      `invite_id` key for null, '' or a failing require (never null or '').
//
// HONEST LABEL (G-035). (a) and (b) prove the composition shape at every
// traced site, not that a request carries the id at runtime; (c) runs the
// real helper. The tracer fails closed: any body expression it cannot follow
// is reported, never assumed fine. Every check was watched failing on a
// mutated copy before it was trusted (G-035/G-050).
//
// FTF_MOBILE_TEST_ROOT can point at a copy of mobile/ (sabotage runs).
// Run: node tests/check-session-init-invite-id.js   (or: npm run test:session-init-invite-id)

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const ROOT = process.env.FTF_MOBILE_TEST_ROOT || path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'src');
const AUTH = 'src/api/auth.ts';
const PATH_LITERAL = '/api/session/init';
const HELPER = 'inviteIdField';

let failures = 0;
const ok   = (n) => console.log(`PASS  ${n}`);
const fail = (n, why) => { failures += 1; console.error(`FAIL  ${n}\n      ${why}`); };

// ── Load every source file under mobile/src ───────────────────────────────
const walk = (dir, out = []) => {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(e.name) && !/\.d\.ts$/.test(e.name)) out.push(p);
  }
  return out;
};
const files = walk(SRC).map((abs) => {
  const rel = path.relative(ROOT, abs).split(path.sep).join('/');
  const kind = abs.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  return ts.createSourceFile(rel, fs.readFileSync(abs, 'utf8'), ts.ScriptTarget.Latest, true, kind);
});
const authSf = files.find((sf) => sf.fileName === AUTH);
if (!authSf) {
  console.error(`FAIL  ${AUTH} exists`);
  process.exit(1);
}

function findAll(root, pred) {
  const out = [];
  const visit = (n) => { if (pred(n)) out.push(n); ts.forEachChild(n, visit); };
  visit(root);
  return out;
}
const isStr = (n) => !!n && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n));
const at = (n) => {
  const sf = n.getSourceFile();
  return `${sf.fileName}:${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1}`;
};
const calleeName = (call) => (ts.isIdentifier(call.expression) ? call.expression.text
  : ts.isPropertyAccessExpression(call.expression) ? call.expression.name.text : null);
const isFnLike = (n) => ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n)
  || ts.isArrowFunction(n) || ts.isMethodDeclaration(n);
const enclosingFn = (n) => { for (let p = n.parent; p; p = p.parent) if (isFnLike(p)) return p; return null; };
const fnName = (fn) => {
  if (!fn) return null;
  if (fn.name && ts.isIdentifier(fn.name)) return fn.name.text;
  if (fn.parent && ts.isVariableDeclaration(fn.parent) && ts.isIdentifier(fn.parent.name)) return fn.parent.name.text;
  return null;
};
// The nearest enclosing function that has a name (the POST itself sits in an
// arrow handed to control.submit).
const namedFn = (n) => { for (let f = enclosingFn(n); f; f = enclosingFn(f)) if (fnName(f)) return fnName(f); return null; };
const isHelperCall = (n) => ts.isCallExpression(n) && ts.isIdentifier(n.expression)
  && n.expression.text === HELPER && n.arguments.length === 0;

// Top-level function declarations, by file, for builder resolution.
const fnDecls = new Map();   // fileName → Map(name → FunctionDeclaration)
for (const sf of files) {
  const m = new Map();
  for (const st of sf.statements) if (ts.isFunctionDeclaration(st) && st.name) m.set(st.name.text, st);
  fnDecls.set(sf.fileName, m);
}
const resolveFn = (sf, name) => fnDecls.get(sf.fileName).get(name)
  || (fnDecls.get(AUTH).get(name) || null);

// `return` statements belonging to fn itself (not to nested functions).
const ownReturns = (fn) => findAll(fn.body, (n) => ts.isReturnStatement(n) && enclosingFn(n) === fn);

// Resolve an identifier use to its variable initializer or a parameter.
function resolveIdent(id) {
  const fn = enclosingFn(id);
  for (let scope = fn; scope; scope = enclosingFn(scope)) {
    const pIdx = scope.parameters.findIndex((p) => ts.isIdentifier(p.name) && p.name.text === id.text);
    const decls = findAll(scope.body || scope, (n) => ts.isVariableDeclaration(n)
      && ts.isIdentifier(n.name) && n.name.text === id.text && n.initializer
      && n.getStart() < id.getStart());
    if (decls.length) return { kind: 'var', init: decls[decls.length - 1].initializer };
    if (pIdx >= 0) return { kind: 'param', fn: scope, index: pIdx };
  }
  return null;
}

// ── The tracer ────────────────────────────────────────────────────────────
const compositions = new Set();   // ObjectLiteralExpression nodes that spread the helper
const problems = [];
const sinkQueue = [];             // [functionName, paramIndex]
const sinkSeen = new Set();
const builderSeen = new Set();

function trace(expr, how) {
  let e = expr;
  while (e && (ts.isParenthesizedExpression(e) || ts.isAwaitExpression(e) || ts.isAsExpression(e)
         || ts.isNonNullExpression(e) || (ts.isSatisfiesExpression && ts.isSatisfiesExpression(e)))) {
    e = e.expression;
  }
  if (!e) { problems.push(`${how}: empty body expression`); return; }
  if (ts.isObjectLiteralExpression(e)) {
    const helperSpreads = e.properties.filter((p) => ts.isSpreadAssignment(p) && isHelperCall(p.expression));
    if (helperSpreads.length === 1) { compositions.add(e); return; }
    if (helperSpreads.length > 1) {
      problems.push(`${at(e)} (${how}): spreads ${HELPER}() ${helperSpreads.length}× — the id is consumed twice for one body`);
      return;
    }
    // Not composed here: follow what it spreads (e.g. sessionInit's
    // `{ ...body, trade_fairness_threshold }`). Nothing to follow ⇒ a body
    // composed without the helper.
    const spreads = e.properties.filter(ts.isSpreadAssignment);
    if (spreads.length === 0) {
      problems.push(`${at(e)} (${how}): a session-init body composed without ...${HELPER}()`);
      return;
    }
    for (const s of spreads) trace(s.expression, `${how} → spread at ${at(s)}`);
    return;
  }
  if (ts.isIdentifier(e)) {
    const r = resolveIdent(e);
    if (!r) { problems.push(`${at(e)} (${how}): cannot resolve \`${e.text}\``); return; }
    if (r.kind === 'var') { trace(r.init, `${how} → ${e.text}`); return; }
    const name = fnName(r.fn);
    if (!name) { problems.push(`${at(e)} (${how}): \`${e.text}\` is a parameter of an anonymous function`); return; }
    addSink(name, r.index);
    return;
  }
  if (ts.isCallExpression(e) && ts.isIdentifier(e.expression)) {
    const target = resolveFn(e.getSourceFile(), e.expression.text);
    if (target && target.getSourceFile().fileName === AUTH) {
      if (builderSeen.has(target)) return;
      builderSeen.add(target);
      const rets = ownReturns(target);
      if (rets.length === 0) problems.push(`${at(target)}: ${e.expression.text}() returns no body to trace`);
      for (const r of rets) trace(r.expression, `${e.expression.text}() return at ${at(r)}`);
      return;
    }
    problems.push(`${at(e)} (${how}): the body comes straight from ${e.expression.text}() `
      + `(${target ? target.getSourceFile().fileName : 'another module'}) — compose it here as `
      + `{ ...(await ${e.expression.text}(…)), ...${HELPER}() }`);
    return;
  }
  problems.push(`${at(e)} (${how}): cannot trace a ${ts.SyntaxKind[e.kind]} body expression`);
}

function addSink(name, index) {
  const key = `${name}#${index}`;
  if (sinkSeen.has(key)) return;
  sinkSeen.add(key);
  sinkQueue.push([name, index]);
}

// ── a. Exactly one POST, inside sessionInit() ─────────────────────────────
const posts = files.flatMap((sf) => findAll(sf, (n) => ts.isCallExpression(n)
  && n.arguments.some((a) => isStr(a) && a.text === PATH_LITERAL)));
let post = null;
if (posts.length === 1 && posts[0].getSourceFile().fileName === AUTH
    && namedFn(posts[0]) === 'sessionInit') {
  post = posts[0];
  ok(`a. exactly one '${PATH_LITERAL}' call in mobile/src, inside sessionInit() (${at(post)})`);
} else {
  fail(`a. exactly one '${PATH_LITERAL}' call in mobile/src, inside sessionInit()`,
       posts.length === 0 ? 'none found'
         : posts.map((p) => `${at(p)} in ${namedFn(p) || '(anonymous)'}()`).join('; ')
           + ' — a second POST site would need its own invite_id trace');
}

// ── b. Every body handed to it is composed with ...inviteIdField() ───────
if (post) {
  const idx = post.arguments.findIndex((a) => isStr(a) && a.text === PATH_LITERAL);
  const bodyArg = post.arguments[idx + 1];
  if (!bodyArg) problems.push(`${at(post)}: the POST passes no body after the path`);
  else trace(bodyArg, `POST body at ${at(post)}`);

  while (sinkQueue.length) {
    const [name, index] = sinkQueue.shift();
    const calls = files.flatMap((sf) => findAll(sf, (n) => ts.isCallExpression(n) && calleeName(n) === name));
    if (calls.length === 0) continue;   // e.g. an exported entry point nothing calls yet
    for (const c of calls) {
      const a = c.arguments[index];
      if (!a) { problems.push(`${at(c)}: ${name}() called without its body argument`); continue; }
      trace(a, `${name}() call at ${at(c)}`);
    }
  }

  // Every auth.ts function declared to return a body, called or not.
  for (const [name, fn] of fnDecls.get(AUTH)) {
    if (!fn.type || !/\bSessionInitBody\b/.test(fn.type.getText(authSf))) continue;
    if (builderSeen.has(fn)) continue;
    builderSeen.add(fn);
    const rets = ownReturns(fn);
    if (rets.length === 0) problems.push(`${at(fn)}: ${name}() returns no body to trace`);
    for (const r of rets) trace(r.expression, `${name}() return at ${at(r)}`);
  }

  // Every helper call in mobile/src must be one of the compositions found.
  const helperCalls = files.flatMap((sf) => findAll(sf, isHelperCall));
  const stray = helperCalls.filter((c) => !(ts.isSpreadAssignment(c.parent) && compositions.has(c.parent.parent)));
  for (const c of stray) {
    problems.push(`${at(c)}: ${HELPER}() called outside a traced session-init composition — `
      + 'a second consumer would spend the id on a body that is never sent');
  }

  const fnsCovered = new Set([...compositions].map((o) => namedFn(o)));
  const selfTest = ['initLeagueSession', 'buildSessionInitBody'].filter((f) => !fnsCovered.has(f));
  if (selfTest.length) {
    problems.push(`tracer self-test: no composition found in ${selfTest.join(', ')} — the trace is not reaching the builders`);
  }

  if (problems.length === 0) {
    ok(`b. all ${compositions.size} session-init bodies are composed with ...${HELPER}() exactly once `
       + `(sinks: ${[...sinkSeen].join(', ')})`);
    for (const o of compositions) console.log(`      ${at(o).padEnd(26)} in ${namedFn(o)}()`);
  } else {
    fail(`b. every session-init body is composed with ...${HELPER}() exactly once`, problems.join('\n      '));
  }
}

// ── c. The helper consumes the id and omits the key without one ──────────
{
  const decls = files.flatMap((sf) => findAll(sf, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === HELPER));
  if (decls.length !== 1 || decls[0].getSourceFile().fileName !== AUTH) {
    fail(`c. ${HELPER} is defined once, in ${AUTH}`,
         `found ${decls.length}${decls.length ? ` (${decls.map(at).join(', ')})` : ''}`);
  } else {
    const fnSrc = decls[0].getText(authSf);
    const js = ts.transpileModule(fnSrc, {
      compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.CommonJS },
    }).outputText;
    const run = (stub) => {
      const calls = { consume: 0, requires: [] };
      const sandbox = {
        require: (name) => {
          calls.requires.push(name);
          if (stub === 'throws') throw new Error('require unavailable');
          return { useSession: { getState: () => ({
            consumeInviteId: () => { calls.consume += 1; return stub; },
            inviteId: stub,
          }) } };
        },
      };
      vm.runInNewContext(`${js}\n;__out = ${HELPER}();`, sandbox);
      return { out: sandbox.__out, calls };
    };
    const issues = [];
    const id = 'invT0ken_123';
    const withId = run(id);
    if (!withId.out || withId.out.invite_id !== id || Object.keys(withId.out).length !== 1) {
      issues.push(`an id returned ${JSON.stringify(withId.out)}, want {"invite_id":"${id}"}`);
    }
    if (withId.calls.consume !== 1) issues.push(`consumeInviteId() called ${withId.calls.consume}× per helper call, want 1`);
    if (!withId.calls.requires.includes('../state/useSession')) {
      issues.push(`the helper does not load ../state/useSession (required: ${JSON.stringify(withId.calls.requires)})`);
    }
    for (const [label, stub] of [['null', null], ["''", ''], ['a failing require', 'throws']]) {
      const r = run(stub);
      if (!r.out || typeof r.out !== 'object' || Object.prototype.hasOwnProperty.call(r.out, 'invite_id')
          || Object.keys(r.out).length !== 0) {
        issues.push(`${label} returned ${JSON.stringify(r.out)} — want {} with no invite_id key (never null or '')`);
      }
    }
    if (issues.length === 0) {
      ok(`c. ${HELPER} (executed): consumes the id once and returns {invite_id}; null, '' and a failing require return {}`);
    } else {
      fail(`c. ${HELPER} consumes the id and omits the key without one`, issues.join('; '));
    }
  }
}

console.log(failures === 0
  ? '\nAll session-init invite_id checks passed (AC-12).'
  : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
