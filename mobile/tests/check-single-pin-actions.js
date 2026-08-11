#!/usr/bin/env node
// #298 — a single pin must not strip the user's ability to accept or decline.
//
// WHY THIS EXISTS. Feedback #298: "All versions should still have the find a
// trade UI and let the user accept / decline the trades as any other
// suggested trade." On v1.12.0, pinning exactly ONE asset flipped `singlePin`
// truthy and two gates of the shape
//
//     {!firstRun && singlePin ? null : (…)}
//
// removed (a) the Find-a-Trade button and (b) the ENTIRE deck wrapper — and
// with it every way to disposition a trade. It fired in the
// `trades_home_inline` experiment's CONTROL group too; the experiment was
// never the cause.
//
// WHY THIS FILE WAS REWRITTEN (2026-08-11, integration round). #169 moved the
// Pass/Like row OUT of TradesScreen.tsx and INTO TradeCard.tsx (card frame C).
// The behaviour was fine — the buttons simply moved one file over — but the
// first version of this test asserted the two testIDs existed *in
// TradesScreen.tsx*, so it went red on a correct build.
//
// The tempting repair is to repoint the ids at TradeCard.tsx. That would be a
// quiet WEAKENING, because co-location was never the claim. Two buttons can
// exist in TradeCard.tsx, render perfectly, and be wired to nothing at all —
// and the old assertions would have passed. So the claim is pinned where it
// actually lives now: the CHAIN, end to end.
//
//     TradesScreen  onLike={() => advance('like')}      ← host wires
//          │        onPass={() => advance('pass')}
//          ▼
//     SwipableTopCard  disposition={{ onPass, onLike }} ← host threads
//          │
//          ▼
//     TradeCard    testID="trades.like-btn"             ← card renders
//                  onPress={disposition.onLike}
//
// …plus the VoiceOver custom actions, which are the third disposition path
// and ride the same two callbacks.
//
// WHAT IS PINNED, and the sabotage each assertion detects:
//
//   1  The two controls exist SOMEWHERE under mobile/src. File-agnostic on
//      purpose: #169 already moved them once, and a future move is not a
//      regression. Sabotage: delete either button.
//   2  Each button dispatches ITS OWN callback and not the other one.
//      Sabotage: cross them — `trades.pass-btn` wired to `onLike`. Silent
//      catastrophe: the X button likes the trade. tsc cannot see it (both
//      are `() => void`), and a Maestro flow that taps like and asserts the
//      deck advanced cannot see it either.
//   3  The host actually THREADS the callbacks into the card. Sabotage: drop
//      the `disposition` prop — the buttons then never render (the card
//      gates on it), or in a variant where they do, they do nothing.
//   4  The host maps those callbacks to `advance()`, UNCROSSED. Sabotage:
//      point `onLike` at `advance('pass')`. Every other check here passes;
//      the app records the opposite of what the user chose.
//   5  The VoiceOver custom actions are uncrossed too. Sabotage: cross them.
//      No automated flow covers VoiceOver, so nothing else would catch it.
//   6  The deck's card mount is not enclosed by a raw-`singlePin` null gate,
//      and neither is `trades.find-btn`. Sabotage: restore either v1.12.0
//      gate. THIS is the actual #298 regression — assertions 1–5 can all pass
//      on a build where the whole surface is unreachable when a pin is set.
//   7  `singlePinDeckActive` is keyed on `deck.length`, never `topCard`.
//      Sabotage: key it on `topCard` — the deck slot then vanishes the moment
//      the last card is swiped and the surface snaps back to the featured
//      window MID-SESSION. No type error, no screenshot diff on a full deck,
//      and the Maestro flow taps like once so it never reaches the state.
//   8  `FeaturedTradeWindow` stays gated on `!singlePinDeckActive` — #241's
//      invariant, never two trade summaries on the pinned surface. It is why
//      V1 was chosen over "just delete both gates" (V2). Sabotage: drop the
//      term and the "mystery second trade card" returns.
//
// Structural, not textual: parses the real TSX with the project's own
// TypeScript and walks the AST, like check-picks-subset-invariance.js. A grep
// passes on a guard that merely moved, and — the case that matters here — a
// grep cannot tell an ANCESTOR gate from an unrelated mention of the same
// identifier elsewhere in a 6,000-line file. Seed-independent: no simulator,
// no backend, no flag fixture.
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

const SRC_DIR = path.join(__dirname, '..', 'src');
// The host: the screen that owns the deck, wires the callbacks, and carries
// the `singlePin` gates #298 is about. This one IS file-specific, because the
// gates and `advance()` are the screen's own responsibility.
const HOST_REL = 'src/screens/TradesScreen.tsx';

// The two controls, and the callback each must dispatch. Order matters: the
// pairing is exactly what assertions 2 and 4 refuse to let anyone cross.
const CONTROLS = [
  { id: 'trades.pass-btn', cb: 'onPass', other: 'onLike', decision: 'pass' },
  { id: 'trades.like-btn', cb: 'onLike', other: 'onPass', decision: 'like' },
];

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

// ── Parsing ────────────────────────────────────────────────────────────────

const _cache = new Map();
function parse(rel) {
  if (_cache.has(rel)) return _cache.get(rel);
  const abs = path.join(__dirname, '..', rel);
  const sf = ts.createSourceFile(
    abs,
    fs.readFileSync(abs, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
  _cache.set(rel, sf);
  return sf;
}

/** Every .tsx under mobile/src whose raw text contains `needle`. Cheap
 *  prefilter so we only pay to parse files that can possibly match — and it
 *  is what makes assertions 1 and 2 file-agnostic. */
function tsxFilesContaining(needle) {
  const out = [];
  (function walkDir(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walkDir(p);
      else if (entry.name.endsWith('.tsx') && fs.readFileSync(p, 'utf8').includes(needle)) {
        out.push(path.relative(path.join(__dirname, '..'), p));
      }
    }
  })(SRC_DIR);
  return out;
}

// ── AST helpers ────────────────────────────────────────────────────────────

function walk(node, visit) {
  visit(node);
  node.forEachChild((c) => walk(c, visit));
}

function findAll(sf, pred) {
  const out = [];
  walk(sf, (n) => {
    if (pred(n)) out.push(n);
  });
  return out;
}

function txt(sf, n) {
  return n ? n.getText(sf) : '';
}

function flat(sf, n) {
  return txt(sf, n).replace(/\s+/g, ' ').trim();
}

function where(sf, n) {
  const rel = path.relative(path.join(__dirname, '..'), sf.fileName);
  return `${rel}:${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1}`;
}

/** Identifiers with exactly this name. Exact-match, so `singlePin` never
 *  matches `singlePinFeatured` / `singlePinDeckActive` — which is the whole
 *  point: the raw predicate is the dangerous one. Member names count
 *  (`disposition.onPass` contains the identifier `onPass`). */
function referencesIdentifier(sf, root, name) {
  return findAll(sf, (n) => ts.isIdentifier(n) && n.text === name)
    .some((n) => n.getStart(sf) >= root.getStart(sf) && n.getEnd() <= root.getEnd());
}

const isJsxEl = (n) => ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n);

function attr(sf, el, name) {
  if (!isJsxEl(el)) return undefined;
  return el.attributes.properties.find(
    (a) => ts.isJsxAttribute(a) && a.name.getText(sf) === name,
  );
}

function stringAttr(sf, el, name) {
  const a = attr(sf, el, name);
  const init = a && a.initializer;
  return init && ts.isStringLiteral(init) ? init.text : null;
}

/** EVERY element carrying this testID — plural on purpose. `trades.find-btn`
 *  appears TWICE in the host, once in each arm of the
 *  `{!consolidateOn ? (…) : (…)}` ternary (the legacy Controls-Card layout
 *  and the #257 consolidated one). They are mutually exclusive at runtime, so
 *  this is not a duplicate-id bug — but it does mean a check that looked at
 *  only the first occurrence would pass while the OTHER layout still shipped
 *  the #298 defect. That is not hypothetical: the first draft of this file
 *  used `[0]`, and the sabotage run that reintroduced the gate on the
 *  consolidated arm came back green. */
function elementsWithTestId(sf, id) {
  return findAll(sf, (n) => isJsxEl(n) && stringAttr(sf, n, 'testID') === id);
}

/** Walk up collecting every enclosing ConditionalExpression and which arm we
 *  are in. */
function enclosingConditionals(node) {
  const out = [];
  let child = node;
  let cur = node.parent;
  while (cur) {
    if (ts.isConditionalExpression(cur)) {
      const inTrue =
        child.getStart() >= cur.whenTrue.getStart() &&
        child.getEnd() <= cur.whenTrue.getEnd();
      out.push({ node: cur, branch: inTrue ? 'whenTrue' : 'whenFalse' });
    }
    child = cur;
    cur = cur.parent;
  }
  return out;
}

const isNullLiteral = (n) => n && n.kind === ts.SyntaxKind.NullKeyword;

/** The #298 defect shape, generalised: an enclosing conditional whose
 *  condition mentions the bare `singlePin` predicate and whose OTHER arm is
 *  `null`. Direction-agnostic — `singlePin ? null : (…)` and
 *  `!singlePin ? (…) : null` are the same bug. */
function rawSinglePinNullGates(sf, el) {
  const out = [];
  for (const { node, branch } of enclosingConditionals(el)) {
    if (!referencesIdentifier(sf, node.condition, 'singlePin')) continue;
    const otherArm = branch === 'whenTrue' ? node.whenFalse : node.whenTrue;
    if (isNullLiteral(otherArm)) out.push(node);
  }
  return out;
}

// ═══════════════════════════════════════════════════════════════════════════
// 1 + 2 — the controls exist (anywhere), and each dispatches its OWN callback
// ═══════════════════════════════════════════════════════════════════════════

for (const { id, cb, other } of CONTROLS) {
  const mounts = [];
  for (const rel of tsxFilesContaining(id)) {
    const sf = parse(rel);
    for (const el of elementsWithTestId(sf, id)) mounts.push({ sf, el });
  }

  assert(
    mounts.length > 0,
    `1 — ${id} exists somewhere under mobile/src`,
    'no element carries this testID in any .tsx — the control is gone',
  );
  if (mounts.length === 0) continue;

  // 2 — every mount, not just the first.
  const bad = [];
  for (const { sf, el } of mounts) {
    const onPress = attr(sf, el, 'onPress');
    if (!onPress || !onPress.initializer) {
      bad.push({ sf, el, why: 'no onPress attribute' });
      continue;
    }
    const dispatchesOwn = referencesIdentifier(sf, onPress.initializer, cb);
    const dispatchesOther = referencesIdentifier(sf, onPress.initializer, other);
    if (!dispatchesOwn || dispatchesOther) {
      bad.push({
        sf,
        el,
        why: `onPress=${flat(sf, onPress.initializer)}` +
          (dispatchesOther ? ` — references \`${other}\`, the OTHER decision` : ''),
      });
    }
  }
  assert(
    bad.length === 0,
    `2 — every ${id} mount (${mounts.length}) dispatches \`${cb}\` and not \`${other}\`` +
      ` [${mounts.map(({ sf, el }) => where(sf, el)).join(', ')}]`,
    bad.length ? `${where(bad[0].sf, bad[0].el)}: ${bad[0].why}` : undefined,
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// The host — wiring, threading, and reachability
// ═══════════════════════════════════════════════════════════════════════════

const host = parse(HOST_REL);

// ── 3 — the host threads BOTH callbacks into the card ──────────────────────
// Located by the `disposition=` prop rather than by component name: the prop
// is the contract TradeCard actually gates its Pass/Like row on
// (`{disposition ? (…) : null}`), so its absence means no buttons at all.

const dispositionProps = findAll(
  host,
  (n) => isJsxEl(n) && !!attr(host, n, 'disposition'),
).map((el) => ({ el, a: attr(host, el, 'disposition') }));

assert(
  dispositionProps.length > 0,
  '3a — the host threads a `disposition` prop into a trade card',
  'no JSX element in ' + HOST_REL + ' passes `disposition=` — the card renders ' +
    'no Pass/Like row at all (TradeCard gates the row on this prop)',
);

for (const { el, a } of dispositionProps) {
  const init = a.initializer;
  const hasBoth =
    !!init &&
    referencesIdentifier(host, init, 'onPass') &&
    referencesIdentifier(host, init, 'onLike');
  assert(
    hasBoth,
    `3b — the \`disposition\` prop at ${where(host, el)} carries both callbacks`,
    `saw: disposition=${init ? flat(host, init) : '(no initializer)'}`,
  );
}

// ── 4 — the host maps those callbacks to advance(), UNCROSSED ──────────────
// Located by shape — any element supplying both `onLike` and `onPass` — not
// by component name, so a rename of SwipableTopCard does not blind the check.

const dispositionMounts = findAll(
  host,
  (n) => isJsxEl(n) && !!attr(host, n, 'onLike') && !!attr(host, n, 'onPass'),
);

assert(
  dispositionMounts.length > 0,
  '4a — the host mounts a card supplying both `onLike` and `onPass`',
  'no JSX element carries both props — the disposition chain has no source',
);

for (const el of dispositionMounts) {
  for (const { cb, decision } of [
    { cb: 'onLike', decision: 'like' },
    { cb: 'onPass', decision: 'pass' },
  ]) {
    const otherDecision = decision === 'like' ? 'pass' : 'like';
    const body = flat(host, attr(host, el, cb).initializer);
    const right = new RegExp(`advance\\(\\s*['"]${decision}['"]\\s*\\)`).test(body);
    const crossed = new RegExp(`advance\\(\\s*['"]${otherDecision}['"]\\s*\\)`).test(body);
    assert(
      right && !crossed,
      `4b — ${where(host, el)} \`${cb}\` dispatches advance('${decision}')` +
        `, not advance('${otherDecision}')`,
      `saw: ${cb}={${body}}`,
    );
  }
}

// ── 5 — the VoiceOver custom actions are uncrossed too ─────────────────────
// The third disposition path (#298 named all three). Nothing else covers it:
// there is no VoiceOver in the Maestro harness. Text-shape check on one small
// handler — it requires the decision literal and its callback to sit within
// the same short clause, in either order, and refuses the crossed pairing.

const a11yHandlers = findAll(
  host,
  (n) => ts.isJsxAttribute(n) && n.name.getText(host) === 'onAccessibilityAction',
);

assert(
  a11yHandlers.length > 0,
  '5a — the host handles VoiceOver like/pass actions',
  'no `onAccessibilityAction` — the screen-reader disposition path is gone',
);

for (const h of a11yHandlers) {
  const body = flat(host, h.initializer);
  const near = (lit, fn) => new RegExp(`(['"])${lit}\\1[^;]{0,60}?${fn}\\(`).test(body);
  const okShape =
    near('like', 'onLike') &&
    near('pass', 'onPass') &&
    !near('like', 'onPass') &&
    !near('pass', 'onLike');
  assert(
    okShape,
    `5b — VoiceOver 'like'→onLike and 'pass'→onPass, uncrossed (${where(host, h)})`,
    `saw: ${body}`,
  );
}

// ── 6 — reachability: no raw-`singlePin` null gate over the deck or the CTA ─
// THE actual #298 regression. Anchored on the deck's card mount (found by
// shape above) rather than on the buttons, which no longer live in this file.

for (const el of dispositionMounts) {
  const gates = rawSinglePinNullGates(host, el);
  assert(
    gates.length === 0,
    `6a — the deck's card mount at ${where(host, el)} is not gated out by the ` +
      'raw `singlePin` predicate',
    gates.length
      ? `gated at ${where(host, gates[0])}: ${flat(host, gates[0].condition)} ? … : …`
      : undefined,
  );
}

const findBtns = elementsWithTestId(host, 'trades.find-btn');
assert(
  findBtns.length > 0,
  '6b — trades.find-btn exists in the host',
  'element not found at all',
);
const gatedCtas = findBtns
  .map((el) => ({ el, gates: rawSinglePinNullGates(host, el) }))
  .filter((x) => x.gates.length > 0);
assert(
  gatedCtas.length === 0,
  `6c — trades.find-btn (${findBtns.length} mount${findBtns.length === 1 ? '' : 's'}) ` +
    'is not gated out by the raw `singlePin` predicate',
  gatedCtas.length
    ? `${where(host, gatedCtas[0].el)} gated at ${where(host, gatedCtas[0].gates[0])}: ` +
      `${flat(host, gatedCtas[0].gates[0].condition)} ? … : …`
    : undefined,
);

// ── 7 — singlePinDeckActive is keyed on deck.length, not topCard ───────────

const deckActiveDecl = findAll(
  host,
  (n) =>
    ts.isVariableDeclaration(n) &&
    ts.isIdentifier(n.name) &&
    n.name.text === 'singlePinDeckActive',
)[0];

if (!deckActiveDecl || !deckActiveDecl.initializer) {
  fail('7 — `singlePinDeckActive` is declared', 'declaration not found');
} else {
  const init = deckActiveDecl.initializer;
  assert(
    /\bdeck\s*\.\s*length\b/.test(flat(host, init)),
    '7a — `singlePinDeckActive` is keyed on `deck.length`',
    `saw: ${flat(host, init)}`,
  );
  assert(
    !referencesIdentifier(host, init, 'topCard'),
    '7b — `singlePinDeckActive` does NOT depend on `topCard`',
    'keying on topCard makes the pinned deck slot vanish on the last swipe ' +
      'and snaps the surface back to the featured window mid-session',
  );
}

// ── 8 — #241 stays fixed: FeaturedTradeWindow yields to the deck ───────────

const featured = findAll(
  host,
  (n) => isJsxEl(n) && txt(host, n.tagName) === 'FeaturedTradeWindow',
)[0];

if (!featured) {
  fail('8 — `FeaturedTradeWindow` is mounted', 'element not found');
} else {
  assert(
    enclosingConditionals(featured).some(({ node }) =>
      referencesIdentifier(host, node.condition, 'singlePinDeckActive'),
    ),
    '8 — `FeaturedTradeWindow` is gated on `singlePinDeckActive`',
    'without it the read-only featured window and the deck card render ' +
      'together — the "mystery second trade card" #241 removed',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All single-pin-actions checks passed.');
