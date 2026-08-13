#!/usr/bin/env node
// T-295-10 — the `user_not_in_draft` refusal surfaces (#295/#296/#305).
//
// WHY THIS EXISTS. The mock draft's root defect (#295) was a SILENT
// exclusion: the user was never in their own mock and no surface said so.
// The repair adds a fourth refusal rung, and this file pins the client half
// of the vocabulary — the typed-empty copy arm, the blocked entry card, and
// the pre-POST probe consumption — so the next silent exclusion is a loud
// refusal on every screen that can meet it.
//
// House rules honoured here:
//   · AST, never raw-source grep — string literals in the TypeScript AST
//     cannot be satisfied by comments naming the construct.
//   · The copy arm is transpiled and CALLED (`emptyCopy` is real logic);
//     a pattern match would pass on an arm that returned the default.
//   · Constructed to fail on the pre-build tree: every assertion below was
//     run against the shipped files first and failed there.
//
// Run: node tests/check-mock-user-not-in-draft.js
//   (or: npm run test:mock-user-not-in-draft)

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
const ok = (name) => console.log(`PASS  ${name}`);
const fail = (name, detail) => {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
};
const assert = (cond, name, detail) => (cond ? ok(name) : fail(name, detail));

function parse(rel) {
  const file = path.join(__dirname, '..', rel);
  return ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.ES2020,
    true,
    ts.ScriptKind.TSX,
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

const apiSrc = parse('src/api/mockDraft.ts');
const mockSrc = parse('src/screens/MockDraftScreen.tsx');
const roomSrc = parse('src/screens/DraftRoomScreen.tsx');

// ═══════════════════════════════════════════════════════════════════════
// 1. The reason enum admits the new value (and stays OPEN)
// ═══════════════════════════════════════════════════════════════════════

const reasonAlias = findAll(
  apiSrc,
  (n) => ts.isTypeAliasDeclaration(n) && n.name.getText() === 'MockEmptyReason',
)[0];
assert(!!reasonAlias, 'mockDraft.ts declares MockEmptyReason');
if (reasonAlias) {
  // LiteralType members of the union — comments cannot produce these.
  const members = findAll(reasonAlias, (n) => ts.isLiteralTypeNode(n))
    .map((n) => (ts.isStringLiteral(n.literal) ? n.literal.text : null))
    .filter(Boolean);
  assert(
    members.includes('user_not_in_draft'),
    "MockEmptyReason admits 'user_not_in_draft'",
    `union literals are [${members.join(', ')}]`,
  );
  assert(
    /string\s*&/.test(reasonAlias.getText()),
    'MockEmptyReason stays OPEN ((string & {}) arm intact)',
    'the open arm is what lets the NEXT refusal degrade instead of crashing (D10)',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 2. emptyCopy — transpiled and CALLED; the arm must not be the default
// ═══════════════════════════════════════════════════════════════════════

const emptyCopyFn = findAll(
  mockSrc,
  (n) => ts.isFunctionDeclaration(n) && n.name && n.name.getText() === 'emptyCopy',
)[0];
assert(!!emptyCopyFn, 'MockDraftScreen declares emptyCopy');
if (emptyCopyFn) {
  const js = ts.transpileModule(`${emptyCopyFn.getText()}\nreturn emptyCopy;`, {
    compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None },
  }).outputText;
  let emptyCopy;
  try {
    // eslint-disable-next-line no-new-func
    emptyCopy = new Function(js)();
  } catch (e) {
    fail('emptyCopy is evaluable in isolation', String(e));
  }
  if (typeof emptyCopy === 'function') {
    const arm = emptyCopy('user_not_in_draft');
    const dflt = emptyCopy('some_future_reason_nobody_registered');
    assert(
      arm !== dflt,
      "emptyCopy('user_not_in_draft') is not the default string",
      `both answered ${JSON.stringify(arm)} — the refusal would render as generic copy (T-295-10)`,
    );
    assert(
      arm ===
        'We couldn’t find your team in this league’s draft, so there’s no seat for you to draft from.',
      'The typed-empty copy is the PRD string, byte-exact (curly apostrophes)',
      `got ${JSON.stringify(arm)}`,
    );
    // The shipped arms must survive the addition.
    assert(
      emptyCopy('class_not_loaded') !== dflt && emptyCopy('cpu_model_unvalidated') !== dflt,
      'The shipped emptyCopy arms are untouched',
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 3. DraftRoomScreen — the blocked arm, keyed on BOTH triggers
// ═══════════════════════════════════════════════════════════════════════

// The arm is the if-statement whose return carries the new testID literal.
const blockedArm = findAll(
  roomSrc,
  (n) =>
    ts.isIfStatement(n) &&
    findAll(n.thenStatement, (m) =>
      ts.isStringLiteral(m) && m.text === 'mock-entry.blocked.user_not_in_draft',
    ).length > 0,
)[0];
assert(!!blockedArm, 'DraftRoomScreen has the mock-entry.blocked.user_not_in_draft arm');
if (blockedArm) {
  const cond = blockedArm.expression.getText();
  assert(
    /postRefusal\s*===\s*'user_not_in_draft'/.test(cond),
    'The arm is keyed on postRefusal (POST answer)',
    `condition is \`${cond}\``,
  );
  assert(
    /probeReason\s*===\s*'user_not_in_draft'/.test(cond),
    'The arm is keyed on probeReason too (pre-POST GET probe)',
    `condition is \`${cond}\` — without the probe key the card renders one tap late (HLD §3.3)`,
  );
  const body = blockedArm.thenStatement.getText();
  assert(
    body.includes(
      "We couldn't find your team in this league's draft, so there's no seat for you to draft from.",
    ),
    'Blocked-card body is the PRD string, byte-exact (straight apostrophes)',
  );
  assert(
    body.includes("Your team isn't in this draft"),
    'Blocked-card cta is the PRD string, byte-exact',
  );
}

// Placement: after the class_not_loaded arm (server-answer group), before
// the board-derived startup arm.
{
  const posOf = (lit) => {
    const n = findAll(roomSrc, (m) => ts.isStringLiteral(m) && m.text === lit)[0];
    return n ? n.getStart() : -1;
  };
  const cls = posOf('mock-entry.blocked.class_not_loaded');
  const usr = posOf('mock-entry.blocked.user_not_in_draft');
  const startup = posOf('mock-entry.blocked.startup_draft');
  assert(
    cls > -1 && usr > cls && startup > usr,
    'The new arm sits after class_not_loaded and before the board-derived arms',
    `positions: class_not_loaded=${cls}, user_not_in_draft=${usr}, startup=${startup}`,
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 4. The probe is consumed — capability typed and read (R9 / LLD §11.4)
// ═══════════════════════════════════════════════════════════════════════

const capIface = findAll(
  apiSrc,
  (n) => ts.isInterfaceDeclaration(n) && n.name.getText() === 'MockCapability',
)[0];
assert(!!capIface, 'mockDraft.ts declares MockCapability');
if (capIface) {
  const props = capIface.members.map((m) => m.name && m.name.getText()).filter(Boolean);
  const want = [
    'can_start', 'reason', 'teams', 'min_teams',
    'rounds_default', 'rounds_max', 'type', 'order_source',
  ];
  assert(
    want.every((w) => props.includes(w)) && props.length === want.length,
    'MockCapability carries exactly the frozen §5.6 fields',
    `fields are [${props.join(', ')}]`,
  );
}

const emptyIface = findAll(
  apiSrc,
  (n) => ts.isInterfaceDeclaration(n) && n.name.getText() === 'MockDraftEmpty',
)[0];
assert(
  !!emptyIface &&
    emptyIface.members.some(
      (m) => m.name && m.name.getText() === 'capability' && !!m.questionToken,
    ),
  'MockDraftEmpty gains optional `capability` (POST empties stay three keys)',
);

const probeDecl = findAll(
  roomSrc,
  (n) => ts.isVariableDeclaration(n) && n.name.getText() === 'probeReason',
)[0];
assert(!!probeDecl, 'DraftRoomScreen derives probeReason');
if (probeDecl) {
  const t = probeDecl.initializer ? probeDecl.initializer.getText() : '';
  assert(
    t.includes('capability') && t.includes("'no_active_mock'"),
    "probeReason reads capability.reason off a 'no_active_mock' empty only",
    `initializer is \`${t}\``,
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All user_not_in_draft surface checks passed.');
