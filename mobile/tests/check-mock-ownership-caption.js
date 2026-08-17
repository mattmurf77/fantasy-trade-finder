#!/usr/bin/env node
// #328 — mock-draft ownership-provenance caption (S-1).
//
// Pins, per docs/feedback/items/328-mock-draft-pick-assignment/lld-delta.md §7:
//   (a) `ownershipCaption` is pure over `settings_echo.ownership_source` —
//       the exported helper reads ONLY its parameter, and both mounts feed it
//       from `settings_echo.ownership_source`;
//   (b) the four known strings, and the render-nothing default for
//       null / undefined / unknown future values (CALLED, not
//       pattern-matched);
//   (c) both mounts' testIDs are present
//       (`mock-draft.ownership-caption`, `mock-draft.recap.ownership-caption`);
//   (d) `MockSettingsEcho.ownership_source` is typed, and the
//       `MockOwnershipSource` set is OPEN + the field nullable.
//
// Run: node tests/check-mock-ownership-caption.js

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

function findAll(node, pred, out = []) {
  if (pred(node)) out.push(node);
  // NOTE: forEachChild STOPS on a truthy callback return — the recursion
  // must not leak `out` back into it.
  node.forEachChild((c) => {
    findAll(c, pred, out);
  });
  return out;
}

const screenSrc = parse('src/screens/MockDraftScreen.tsx');
const apiSrc = parse('src/api/mockDraft.ts');
const screenText = screenSrc.getText();

// ── (a) + (b): the helper, CALLED ──────────────────────────────────────────

const helperNode = findAll(
  screenSrc,
  (n) => ts.isFunctionDeclaration(n) && n.name?.getText() === 'ownershipCaption',
)[0];
assert(!!helperNode, 'ownershipCaption is declared in MockDraftScreen.tsx');

if (helperNode) {
  assert(
    !!helperNode.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword),
    'ownershipCaption is exported (this check calls it)',
  );

  // Purity: the body references nothing beyond its own parameter — no state,
  // no store, no second settings key can leak into the caption.
  const paramName = helperNode.parameters[0]?.name.getText();
  const foreign = findAll(
    helperNode.body,
    (n) => ts.isIdentifier(n) && n.text !== paramName && !ts.isStringLiteral(n),
  ).filter((n) => {
    // Property-access NAMES (`x.foo`) and type refs are not value reads.
    const p = n.parent;
    if (ts.isPropertyAccessExpression(p) && p.name === n) return false;
    if (ts.isTypeReferenceNode(p) || ts.isTypeNode(p)) return false;
    return true;
  });
  assert(
    foreign.length === 0,
    'ownershipCaption reads ONLY its parameter (settings_echo.ownership_source)',
    `foreign identifiers: ${foreign.map((n) => n.text).join(', ')}`,
  );

  // Transpile and CALL it — the four strings and the render-nothing default.
  const js = ts.transpileModule(helperNode.getText().replace(/^export\s+/, ''), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  // eslint-disable-next-line no-new-func
  const caption = new Function(`${js}; return ownershipCaption;`)();
  const CASES = [
    ['platform', 'Real pick ownership applied'],
    ['user', 'Real pick ownership applied · entered by your league'],
    ['partial', 'Some real pick ownership applied — other slots use draft order'],
    ['none', 'Traded picks unavailable — each team drafts its own slot'],
  ];
  for (const [src, want] of CASES) {
    assert(caption(src) === want, `caption('${src}') is the pinned copy`,
      `got ${JSON.stringify(caption(src))}`);
  }
  for (const unknown of [null, undefined, 'espn_beta_v2', '']) {
    assert(
      caption(unknown) === null,
      `caption(${JSON.stringify(unknown)}) renders NOTHING (null = unknown, never "none")`,
      `got ${JSON.stringify(caption(unknown))}`,
    );
  }
}

// ── (c): both mounts, gated on the helper ──────────────────────────────────

for (const id of ['mock-draft.ownership-caption', 'mock-draft.recap.ownership-caption']) {
  const attr = findAll(
    screenSrc,
    (n) =>
      ts.isJsxAttribute(n) &&
      n.name.getText() === 'testID' &&
      !!n.initializer &&
      ts.isStringLiteral(n.initializer) &&
      n.initializer.text === id,
  )[0];
  assert(!!attr, `mount testID "${id}" is present`);
}
assert(
  (screenText.match(/ownershipCaption\(/g) || []).length >= 4,
  'both mounts render THROUGH ownershipCaption (guard + child on each)',
  'a mount hand-rolling its copy would fork the vocabulary',
);
assert(
  /settings_echo\?\.ownership_source/.test(screenText),
  'the caption input is settings_echo.ownership_source (never inferred)',
);

// ── (d): the API typing ────────────────────────────────────────────────────

const echoIface = findAll(
  apiSrc,
  (n) => ts.isInterfaceDeclaration(n) && n.name.getText() === 'MockSettingsEcho',
)[0];
assert(!!echoIface, 'MockSettingsEcho interface exists');
if (echoIface) {
  const member = echoIface.members.find((m) => m.name?.getText() === 'ownership_source');
  assert(!!member, 'MockSettingsEcho.ownership_source is typed');
  assert(
    !!member && /MockOwnershipSource\s*\|\s*null/.test(member.type.getText()),
    'ownership_source is nullable (pre-#328 rows echo null = UNKNOWN)',
    member ? member.type.getText() : 'no member',
  );
}

const srcType = findAll(
  apiSrc,
  (n) => ts.isTypeAliasDeclaration(n) && n.name.getText() === 'MockOwnershipSource',
)[0];
assert(!!srcType, 'MockOwnershipSource type alias exists');
if (srcType) {
  const t = srcType.type.getText();
  for (const v of ['platform', 'user', 'partial', 'none']) {
    assert(t.includes(`'${v}'`), `MockOwnershipSource admits '${v}'`);
  }
  assert(
    /string\s*&\s*\{\s*\}/.test(t),
    'MockOwnershipSource is OPEN (server may grow the vocabulary)',
  );
}

if (failures) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll #328 ownership-caption checks passed.');
