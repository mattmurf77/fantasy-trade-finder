#!/usr/bin/env node
// Mode-marking regression test (draft-extensions W2, flag `draft.mock`).
//
// WHY THIS EXISTS. The design pass recommended placement option B and
// argued AGAINST option C on one serious ground: the Draft Room prints its
// own no-platform-writes guarantee ("Picks are made on the platform —
// Fantasy Trade Finder never drafts for you") on itself, and a mode switch
// above that sentence makes it ambiguous on the one screen where mistaking
// a simulation for the real draft costs a real pick. The operator chose C.
// The obligations that answer the objection are therefore not polish, and a
// future refactor must not be able to quietly undo them:
//
//   1. `MockRail` renders in EVERY mock sub-state, at every scroll
//      position — i.e. OUTSIDE the ScrollView and OUTSIDE every conditional.
//   2. The platform deep link and the D9 guarantee text are UNREACHABLE in
//      mock mode.
//   3. The mock entry is gated on the `draft.mock` flag.
//
// These are structural claims, so this is a structural test: it parses the
// real TSX with the project's own TypeScript and walks the JSX tree. A
// string grep would pass on a rail that had been moved inside a branch,
// which is exactly the failure mode worth catching.
//
// Run: node tests/check-mock-mode-marker.js
//   (or: npm run test:mock-mode-marker)

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
    ts.ScriptKind.TSX,
  );
}

/** Every node in the tree, depth-first. */
function walk(node, visit) {
  visit(node);
  node.forEachChild((c) => walk(c, visit));
}

/** The JSX tag name of an opening/self-closing element, or null. */
function tagOf(node) {
  if (ts.isJsxSelfClosingElement(node)) return node.tagName.getText();
  if (ts.isJsxElement(node)) return node.openingElement.tagName.getText();
  return null;
}

function findAll(root, pred) {
  const out = [];
  walk(root, (n) => {
    if (pred(n)) out.push(n);
  });
  return out;
}

function findTag(root, tag) {
  return findAll(root, (n) => tagOf(n) === tag);
}

function ancestors(node) {
  const out = [];
  for (let p = node.parent; p; p = p.parent) out.push(p);
  return out;
}

/** True when `node` sits inside a `cond ? … : …` or `cond && …`. */
function insideConditional(node, stopAt) {
  for (let p = node.parent; p && p !== stopAt; p = p.parent) {
    if (ts.isConditionalExpression(p)) return true;
    if (
      ts.isBinaryExpression(p) &&
      (p.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken ||
        p.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken)
    ) {
      return true;
    }
  }
  return false;
}

// ═══════════════════════════════════════════════════════════════════════
// 1. MockDraftScreen — the session
// ═══════════════════════════════════════════════════════════════════════

const mockSrc = parse('src/screens/MockDraftScreen.tsx');

const mockFn = findAll(mockSrc, (n) =>
  ts.isFunctionDeclaration(n) && n.name && n.name.getText() === 'MockDraftScreen',
)[0];
assert(!!mockFn, 'MockDraftScreen component found');

if (mockFn) {
  // ── ONE return. Multiple returns are how a rail-less branch appears.
  const ownReturns = findAll(mockFn.body, (n) => ts.isReturnStatement(n)).filter((r) => {
    // Skip returns that belong to a nested function/arrow inside the body.
    for (let p = r.parent; p && p !== mockFn; p = p.parent) {
      if (
        ts.isFunctionDeclaration(p) ||
        ts.isArrowFunction(p) ||
        ts.isFunctionExpression(p)
      ) {
        return false;
      }
    }
    return true;
  });
  assert(
    ownReturns.length === 1,
    'MockDraftScreen has exactly ONE top-level return',
    `found ${ownReturns.length} — an early return can render a mock sub-state with no mode marker`,
  );

  const rails = findTag(mockFn, 'MockRail');
  assert(rails.length === 1, 'MockDraftScreen renders exactly one MockRail', `found ${rails.length}`);

  if (rails.length === 1 && ownReturns.length === 1) {
    const rail = rails[0];
    const root = ownReturns[0].expression;

    assert(
      !insideConditional(rail, root),
      'MockDraftScreen MockRail is UNCONDITIONAL',
      'the rail sits inside a ternary or && — some sub-state would render without it',
    );

    // The rail must precede the ScrollView in document order: pinned above
    // the scroll, not scrolled away with the content.
    const scrolls = findTag(mockFn, 'ScrollView');
    assert(scrolls.length >= 1, 'MockDraftScreen has a ScrollView');
    if (scrolls.length) {
      assert(
        rail.getStart() < scrolls[0].getStart(),
        'MockDraftScreen MockRail renders BEFORE the ScrollView',
        'a rail inside/after the scroll is not visible at every scroll position',
      );
      assert(
        !ancestors(rail).some((a) => tagOf(a) === 'ScrollView'),
        'MockDraftScreen MockRail is OUTSIDE the ScrollView',
      );
    }
  }

  // Each designed sub-state is present and, by the two checks above,
  // necessarily under the rail. Listed explicitly so deleting a state is a
  // deliberate edit to this file rather than a silent regression.
  const body = mockSrc.getFullText();
  for (const marker of [
    'mock-draft.empty-text',   // no league
    'mock-draft.error-text',   // load failure
    'mock-draft.empty.',       // typed-empty refusals
    'mock-draft.on-the-clock', // live board
    'mock-draft.confirm',      // your-pick confirm
    'mock-draft.recap',        // recap
  ]) {
    assert(body.includes(marker), `MockDraftScreen sub-state present: ${marker}`);
  }

  // The mock surface must not PRINT the room's platform guarantee. Checked
  // against rendered text only — prose about the rule belongs in comments,
  // and a comment is not a thing a user can misread on a board.
  const rendered = findAll(
    mockSrc,
    (n) =>
      ts.isJsxText(n) ||
      ts.isStringLiteral(n) ||
      ts.isNoSubstitutionTemplateLiteral(n) ||
      ts.isTemplateHead(n) ||
      ts.isTemplateMiddle(n) ||
      ts.isTemplateTail(n),
  )
    .map((n) => n.text || '')
    .join(' ');
  assert(
    !rendered.includes('never drafts'),
    'MockDraftScreen does NOT print the "never drafts for you" guarantee',
    'that sentence is about the real room; above a board that takes picks it reads as a promise about THIS board',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 2. DraftRoomScreen — the entry (placement option C)
// ═══════════════════════════════════════════════════════════════════════

const roomSrc = parse('src/screens/DraftRoomScreen.tsx');
const roomText = roomSrc.getFullText();

const roomFn = findAll(roomSrc, (n) =>
  ts.isFunctionDeclaration(n) && n.name && n.name.getText() === 'DraftRoomScreen',
)[0];
assert(!!roomFn, 'DraftRoomScreen component found');

const roomRails = findTag(roomSrc, 'MockRail');
assert(roomRails.length === 1, 'DraftRoomScreen renders exactly one MockRail', `found ${roomRails.length}`);

if (roomRails.length === 1) {
  const rail = roomRails[0];

  // Pinned: the rail is passed through the Shell's `header` prop, which
  // renders above the ScrollView — not as a child of it.
  const inHeaderProp = ancestors(rail).some(
    (a) => ts.isJsxAttribute(a) && a.name.getText() === 'header',
  );
  assert(
    inHeaderProp,
    'DraftRoomScreen MockRail rides the pinned `header` prop',
    'a rail in `children` scrolls away — the marker must survive any scroll position',
  );
  assert(
    !ancestors(rail).some((a) => tagOf(a) === 'ScrollView'),
    'DraftRoomScreen MockRail is OUTSIDE the ScrollView',
  );

  // Gated on the mock MODE (which is itself gated on the flag).
  const guards = ancestors(rail)
    .filter((a) => ts.isConditionalExpression(a))
    .map((a) => a.condition.getText());
  assert(
    guards.some((g) => g.includes('mockMode')),
    'DraftRoomScreen MockRail renders only in Mock mode',
    `guards seen: ${JSON.stringify(guards)}`,
  );
}

// The `mockMode` derivation must include the flag, so flag-off is
// structurally byte-identical rather than merely untested.
assert(
  /const\s+mockMode\s*=\s*mockOn\s*&&/.test(roomText),
  'DraftRoomScreen mockMode requires the `draft.mock` flag',
);
assert(
  /useFlag\(['"]draft\.mock['"]\)/.test(roomText),
  'DraftRoomScreen reads the `draft.mock` flag',
);

// The toggle itself is flag-gated.
const toggles = findTag(roomSrc, 'DraftModeToggle');
assert(toggles.length === 1, 'DraftRoomScreen renders exactly one DraftModeToggle');
if (toggles.length === 1) {
  const guards = ancestors(toggles[0])
    .filter(
      (a) =>
        ts.isConditionalExpression(a) ||
        (ts.isBinaryExpression(a) &&
          a.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken),
    )
    .map((a) => (ts.isConditionalExpression(a) ? a.condition.getText() : a.left.getText()));
  assert(
    guards.some((g) => g.includes('mockOn')),
    'DraftRoomScreen mode toggle is gated on `mockOn`',
    `guards seen: ${JSON.stringify(guards)}`,
  );
}

// ── The subtraction: the deep link + D9 guarantee live ONLY in Real mode.
const modeTernaries = findAll(
  roomSrc,
  (n) => ts.isConditionalExpression(n) && n.condition.getText().trim() === 'mockMode',
);
assert(
  modeTernaries.length >= 1,
  'DraftRoomScreen branches its body on `mockMode`',
);
const bodyTernary = modeTernaries.find((t) =>
  t.whenFalse.getText().includes('draft-room.deep-link'),
);
assert(
  !!bodyTernary,
  'The platform deep link lives in the REAL-mode branch',
  'the deep-link CTA must be unreachable while the Mock side is selected',
);
if (bodyTernary) {
  assert(
    !bodyTernary.whenTrue.getText().includes('never drafts'),
    'The D9 guarantee text is NOT rendered in Mock mode',
  );
  assert(
    bodyTernary.whenFalse.getText().includes('never drafts'),
    'The D9 guarantee text IS still rendered in Real mode',
  );
  assert(
    !bodyTernary.whenTrue.getText().includes('StatusBar'),
    'The real draft StatusBar/Refresh is NOT rendered in Mock mode',
    'it describes the platform draft; over a simulation it would be a lie',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All mock mode-marker checks passed.');
