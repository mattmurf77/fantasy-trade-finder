#!/usr/bin/env node
// #298 — the single-pin trade surface must keep the deck's own controls.
//
// WHY THIS EXISTS. Feedback #298: "All versions should still have the find a
// trade UI and let the user accept / decline the trades as any other
// suggested trade." On v1.12.0, pinning exactly ONE asset flipped `singlePin`
// truthy and two gates of the shape
//
//     {!firstRun && singlePin ? null : (…)}
//
// removed (a) the Find-a-Trade button and (b) the ENTIRE deck wrapper. The
// wrapper is where `SwipableTopCard`'s onLike/onPass, the
// `trades.pass-btn` / `trades.like-btn` row and the top card's VoiceOver
// like/pass actions all live, and all three funnel into `advance()`. So one
// gate silently deleted every way to accept or decline a trade. It fired in
// the `trades_home_inline` experiment's CONTROL group too — the experiment
// was never the cause.
//
// WHY A MAESTRO FLOW IS NOT ENOUGH. flows/smoke/12-trades-single-pin.yaml
// covers this on-device, but it needs a booted simulator, a seeded backend
// and a server-chosen deck that actually contains the pinned asset. This file
// needs none of that: it pins the INVARIANT in source so the regression
// cannot be reintroduced by a refactor that never reaches a QA round. The two
// are complementary — the flow proves it works, this proves it cannot quietly
// stop working.
//
// WHAT IS PINNED, and the sabotage each assertion detects:
//
//   1  No `singlePin ? null` gate may exclude any of the three action
//      testIDs. This is the literal v1.12.0 defect, for all three ids at
//      once. Sabotage: restore either gate.
//   2  `singlePinDeckActive` is keyed on `deck.length`, never on `topCard`.
//      Sabotage: key it on `topCard` — subtler and nastier, because the deck
//      slot then vanishes the moment the last card is swiped and the surface
//      snaps back to the featured window MID-SESSION. No type error, no
//      Maestro assertion (the flow taps like once and stops), no screenshot
//      diff on a full deck.
//   3  `FeaturedTradeWindow` stays gated on `!singlePinDeckActive`. This is
//      #241's invariant — never two trade summaries on the pinned surface —
//      and it is the reason V1 was chosen over "just delete both gates"
//      (V2). Sabotage: drop the `!singlePinDeckActive` term and the read-only
//      featured window renders above the deck card again, which is the
//      "mystery second trade card" #241 removed.
//   4  Both disposition buttons exist AND both dispatch `advance()`. A fix
//      that restored only the accept path, or that rendered cosmetic buttons
//      wired to something else, satisfies every other check here and still
//      fails the reporter's sentence. Sabotage: delete `trades.pass-btn`, or
//      repoint either onPress away from `advance`.
//
// Structural, not textual: this parses the real TSX with the project's own
// TypeScript and walks the AST, like check-picks-subset-invariance.js and
// check-member-entered-marker.js. A grep passes on a guard that merely moved,
// and — the case that matters here — a grep cannot tell an ANCESTOR gate from
// an unrelated mention of the same identifier elsewhere in a 6,000-line file.
// Seed-independent: no simulator, no backend, no flag fixture.
//
// Run: node tests/check-single-pin-actions.js
//   (or: npm run test:single-pin-actions)

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

const REL = 'src/screens/TradesScreen.tsx';

// The controls #298 says must survive a single pin. `trades.card-top` is
// deliberately NOT here: it belongs to SwipableTopCard, which is declared in
// this same file but mounted from inside the deck wrapper, so gating it is
// already covered by the pass/like ids sitting in the same subtree.
const ACTION_IDS = ['trades.find-btn', 'trades.pass-btn', 'trades.like-btn'];

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

const file = path.join(__dirname, '..', REL);
const src = ts.createSourceFile(
  file,
  fs.readFileSync(file, 'utf8'),
  ts.ScriptTarget.ES2019,
  /* setParentNodes */ true,
  ts.ScriptKind.TSX,
);

// ── AST helpers ────────────────────────────────────────────────────────────

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

function txt(n) {
  return n ? n.getText(src) : '';
}

function flat(n) {
  return txt(n).replace(/\s+/g, ' ').trim();
}

function lineOf(n) {
  return src.getLineAndCharacterOfPosition(n.getStart(src)).line + 1;
}

/** Every Identifier with exactly this name inside `root`. Exact-match, so
 *  `singlePin` never matches `singlePinFeatured` / `singlePinDeckActive` —
 *  which is the whole point: the raw predicate is the dangerous one. */
function referencesIdentifier(root, name) {
  return findAll(root, (n) => ts.isIdentifier(n) && n.text === name).length > 0;
}

/** The string value of a JSX `testID="…"` attribute, or null. */
function testIdOf(node) {
  if (!ts.isJsxSelfClosingElement(node) && !ts.isJsxOpeningElement(node)) return null;
  for (const attr of node.attributes.properties) {
    if (!ts.isJsxAttribute(attr) || attr.name.getText(src) !== 'testID') continue;
    const init = attr.initializer;
    if (init && ts.isStringLiteral(init)) return init.text;
  }
  return null;
}

/** EVERY element carrying this testID — plural on purpose. `trades.find-btn`
 *  and the progress strip each appear TWICE in this file, once in each arm of
 *  the `{!consolidateOn ? (…) : (…)}` ternary (the legacy Controls-Card
 *  layout and the #257 consolidated one). They are mutually exclusive at
 *  runtime, so this is not a duplicate-id bug — but it does mean a check that
 *  looked at only the first occurrence would pass while the OTHER layout
 *  still shipped the #298 defect. That is not hypothetical: the first draft
 *  of this file used `[0]`, and the sabotage run that reintroduced the gate
 *  on the consolidated arm came back green. */
function elementsWithTestId(id) {
  return findAll(
    src,
    (n) =>
      (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
      testIdOf(n) === id,
  );
}

/** Walk up from `node` collecting every enclosing ConditionalExpression,
 *  along with which branch `node` sits in. */
function enclosingConditionals(node) {
  const out = [];
  let child = node;
  let cur = node.parent;
  while (cur) {
    if (ts.isConditionalExpression(cur)) {
      // Which arm contains us? Compare by source span — robust to the
      // JsxExpression / ParenthesizedExpression wrappers TSX inserts.
      const inTrue =
        child.getStart(src) >= cur.whenTrue.getStart(src) &&
        child.getEnd() <= cur.whenTrue.getEnd();
      out.push({ node: cur, branch: inTrue ? 'whenTrue' : 'whenFalse' });
    }
    child = cur;
    cur = cur.parent;
  }
  return out;
}

const isNullLiteral = (n) => n && n.kind === ts.SyntaxKind.NullKeyword;

// ── 1. No raw-`singlePin` gate may exclude an action control ───────────────
//
// The defect shape, generalised: a ConditionalExpression whose condition
// mentions the bare `singlePin` predicate, whose OTHER arm is `null`, and
// which encloses one of the action testIDs. Direction-agnostic on purpose —
// `singlePin ? null : (…)` and `!singlePin ? (…) : null` are the same bug.

for (const id of ACTION_IDS) {
  const els = elementsWithTestId(id);
  if (els.length === 0) {
    fail(`1 — ${id} exists in ${REL}`, 'element not found at all');
    continue;
  }
  // EVERY occurrence, not just the first — see elementsWithTestId's note.
  const offenders = [];
  for (const el of els) {
    for (const { node, branch } of enclosingConditionals(el)) {
      if (!referencesIdentifier(node.condition, 'singlePin')) continue;
      const otherArm = branch === 'whenTrue' ? node.whenFalse : node.whenTrue;
      if (isNullLiteral(otherArm)) offenders.push({ el, node });
    }
  }
  assert(
    offenders.length === 0,
    `1 — ${id} (${els.length} mount${els.length === 1 ? '' : 's'}) is not gated out by the raw \`singlePin\` predicate`,
    offenders.length
      ? `element at line ${lineOf(offenders[0].el)} gated at line ` +
        `${lineOf(offenders[0].node)}: ${flat(offenders[0].node.condition)} ? … : …`
      : undefined,
  );
}

// ── 2. singlePinDeckActive is keyed on deck.length, not topCard ────────────

const deckActiveDecl = findAll(
  src,
  (n) =>
    ts.isVariableDeclaration(n) &&
    ts.isIdentifier(n.name) &&
    n.name.text === 'singlePinDeckActive',
)[0];

if (!deckActiveDecl || !deckActiveDecl.initializer) {
  fail('2 — `singlePinDeckActive` is declared', 'declaration not found');
} else {
  const init = deckActiveDecl.initializer;
  assert(
    /\bdeck\s*\.\s*length\b/.test(flat(init)),
    '2a — `singlePinDeckActive` is keyed on `deck.length`',
    `saw: ${flat(init)}`,
  );
  assert(
    !referencesIdentifier(init, 'topCard'),
    '2b — `singlePinDeckActive` does NOT depend on `topCard`',
    'keying on topCard makes the pinned deck slot vanish on the last swipe ' +
      'and snaps the surface back to the featured window mid-session',
  );
}

// ── 3. #241 stays fixed: FeaturedTradeWindow yields to the deck ────────────

const featured = findAll(
  src,
  (n) =>
    (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
    txt(n.tagName) === 'FeaturedTradeWindow',
)[0];

if (!featured) {
  fail('3 — `FeaturedTradeWindow` is mounted', 'element not found');
} else {
  const gatedByDeckActive = enclosingConditionals(featured).some(({ node }) =>
    referencesIdentifier(node.condition, 'singlePinDeckActive'),
  );
  assert(
    gatedByDeckActive,
    '3 — `FeaturedTradeWindow` is gated on `singlePinDeckActive`',
    'without it the read-only featured window and the deck card render ' +
      'together — the "mystery second trade card" #241 removed',
  );
}

// ── 4. Both disposition buttons exist and both dispatch advance() ──────────

for (const [id, decision] of [
  ['trades.pass-btn', 'pass'],
  ['trades.like-btn', 'like'],
]) {
  const els = elementsWithTestId(id);
  if (els.length === 0) {
    fail(`4 — ${id} exists`, 'element not found');
    continue;
  }
  const re = new RegExp(`advance\\(\\s*['"]${decision}['"]\\s*\\)`);
  const bad = els.filter((el) => {
    const onPress = el.attributes.properties.find(
      (a) => ts.isJsxAttribute(a) && a.name.getText(src) === 'onPress',
    );
    return !onPress || !re.test(flat(onPress.initializer));
  });
  assert(
    bad.length === 0,
    `4 — every ${id} mount dispatches advance('${decision}')`,
    bad.length ? `line ${lineOf(bad[0])} does not` : undefined,
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All single-pin-actions checks passed.');
