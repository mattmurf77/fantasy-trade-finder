#!/usr/bin/env node
// "Avoiding" positions — feedback #360 / #361.
//
// Build contract: docs/feedback/items/360-avoiding-positions/ (prd.md §7.2,
// lld-delta.md §5). Assertion ids below are the PRD's A-1 … A-9.
//
// WHY THIS EXISTS. Almost every way to get this feature wrong is silent.
//
//   * The three-way toggle. Chasing ⊕ Avoiding are mutually exclusive;
//     Shopping + Avoiding are NOT — "I'm selling my QB and I don't want
//     another one back" is the modal real usage. The obvious
//     implementation ("make all three exclusive like the existing two")
//     compiles, looks right, and makes the headline use case
//     unexpressible. Nothing else in the tree can catch that. §3 is worth
//     the whole file.
//   * The autosave payload. Six sites carry the four preference lists. Miss
//     `avoid` on any ONE of them and a tap that CLEARS an avoided position
//     silently fails to persist — the backend leaves the stored value
//     untouched when the key is absent (and echoes `[]` back, which is not
//     authoritative), so the row and the DB diverge and the next sheet open
//     re-seeds the stale value. No error, no toast, no crash.
//   * The legacy variant. Omitting `full` is what keeps the #257 flag-off
//     path byte-identical, so that branch is LIVE. A row shipped only into
//     the `full` variant vanishes for every DNA-only entry point.
//   * The glyph. `DnaToggle`'s own comment says the check is the primary
//     state cue, never color alone. A check meaning "avoided" inverts it,
//     and renders identically to a correct build in a screenshot.
//
// NOT ASSERTED, deliberately: the PRD's A-10 wanted `trade.avoid_positions`
// present in BOTH config/features.json and LAUNCHED_FLAG_DEFAULTS. The
// orchestrator overruled that after the PRD was written. That map FAILS
// OPEN (see its own #115 comment) — a first-ever boot or a failed
// revalidate keeps every LISTED feature on. For a flag whose only job is to
// be a kill switch, listing it would keep the Avoiding row rendering after
// the operator killed the flag, so the UI would accept a preference the
// engine had stopped honoring. The key is deliberately ABSENT from that
// map, the one-frame pop-in is the accepted cost, and asserting presence
// here would pin the bug in place.
//
// Every assertion below names the sabotage it detects. Assertions of the
// form "X appears nowhere" read COMMENT-STRIPPED source — the comments in
// these files deliberately name the constructs they forbid, which is
// exactly how a previous round shipped four tests that could not fail.
//
// Run: node tests/check-avoid-positions.js

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
function assert(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const ROOT = path.join(__dirname, '..');
function parse(rel) {
  const abs = path.join(ROOT, rel);
  return ts.createSourceFile(
    abs,
    fs.readFileSync(abs, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
}
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}

const SHEET = 'src/components/TradeDnaSheet.tsx';
const DECK = 'src/screens/TradesScreen.tsx';
const sheet = parse(SHEET);
const deck = parse(DECK);

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
const isJsxEl = (n) => ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n);

/** Attribute text for `name` on a JSX element — string literal contents, or
 *  the raw source of an expression container (template literals included). */
function attrText(sf, el, name) {
  if (!isJsxEl(el)) return null;
  const a = el.attributes.properties.find(
    (p) => ts.isJsxAttribute(p) && p.name.getText(sf) === name,
  );
  if (!a || !a.initializer) return a ? '' : null;
  if (ts.isStringLiteral(a.initializer)) return a.initializer.text;
  return a.initializer.getText(sf);
}
function hasAttr(sf, el, name) {
  return (
    isJsxEl(el) &&
    el.attributes.properties.some(
      (p) => ts.isJsxAttribute(p) && p.name.getText(sf) === name,
    )
  );
}
function within(node, container) {
  return node.getStart() >= container.getStart() && node.getEnd() <= container.getEnd();
}
/** Nearest ancestor satisfying `pred`, or null. */
function ancestor(node, pred) {
  let n = node.parent;
  while (n) {
    if (pred(n)) return n;
    n = n.parent;
  }
  return null;
}
/** The JsxElement (open+children+close) whose opening tag references
 *  `styles.<styleName>`. */
function jsxElementsWithStyle(sf, styleName) {
  return findAll(
    sf,
    (n) =>
      ts.isJsxElement(n) &&
      new RegExp(`styles\\s*\\.\\s*${styleName}\\b`).test(
        n.openingElement.attributes.getText(sf),
      ),
  );
}
/** Every <DnaToggle …> element in the sheet. */
function dnaToggles() {
  return findAll(sheet, (n) => isJsxEl(n) && n.tagName.getText(sheet) === 'DnaToggle');
}
/** The named function/arrow bound to `const <name> = …` in `sf`. */
function namedFn(sf, name) {
  const decls = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === name &&
      !!n.initializer,
  );
  return decls.length === 1 ? decls[0].initializer : null;
}

console.log('═'.repeat(72));
console.log('1 — the Avoiding row exists in BOTH sheet variants, below Shopping');
console.log('═'.repeat(72));

// A-1 — the `full` variant lays out three styles.posLine blocks, in source
// order Chasing → Shopping → Avoiding. RN lays a column out in child order,
// so source order IS screen order.
const posLines = jsxElementsWithStyle(sheet, 'posLine');
assert(
  posLines.length === 3,
  'A-1a — the full variant has exactly three styles.posLine rows',
  `found ${posLines.length} — the Avoiding row is missing, or a fourth crept in`,
);
if (posLines.length === 3) {
  const labelOf = (row) => {
    const texts = findAll(row, (n) => ts.isJsxText(n)).map((n) => n.getText(sheet).trim());
    return ['Chasing', 'Shopping', 'Avoiding'].find((l) => texts.includes(l)) ?? '?';
  };
  const order = posLines.map(labelOf);
  assert(
    order.join(' → ') === 'Chasing → Shopping → Avoiding',
    'A-1b — posLine source order is Chasing → Shopping → Avoiding',
    `got ${order.join(' → ')} — RN renders in child order, so this IS the on-screen order`,
  );
}

// A-2 — the LEGACY variant carries the row too. Both variants map
// DNA_POSITIONS into `dna.avoid.<tid>` toggles; the full-variant one lives
// inside a posLine, the legacy one does not.
const avoidToggles = dnaToggles().filter((el) =>
  (attrText(sheet, el, 'testID') || '').includes('dna.avoid.'),
);
assert(
  avoidToggles.length === 2,
  'A-2a — exactly two dna.avoid.* DnaToggle sites (full + legacy variants)',
  `found ${avoidToggles.length}`,
);
const avoidInPosLine = avoidToggles.filter((el) =>
  posLines.some((row) => within(el, row)),
);
assert(
  avoidToggles.length === 2 &&
    avoidInPosLine.length === 1 &&
    avoidToggles.length - avoidInPosLine.length === 1,
  'A-2b — one Avoiding block in the full variant, one in the LEGACY variant',
  'the legacy half-sheet is live (omitting `full` is what keeps flag-off ' +
    'byte-identical) — a row shipped only into `full` silently vanishes there',
);

console.log('');
console.log('═'.repeat(72));
console.log('2 — the glyph inverts, and only on the Avoiding row');
console.log('═'.repeat(72));

// A-9 — Avoiding selects with ✕; Chasing and Shopping pass no glyph at all
// (so they keep DnaToggle's `check` default and stay untouched).
assert(
  avoidToggles.length > 0 &&
    avoidToggles.every((el) => attrText(sheet, el, 'glyph') === 'x'),
  'A-9a — every Avoiding DnaToggle passes glyph="x"',
  'reusing `check` for "avoided" inverts the state cue DnaToggle\'s own ' +
    'construction rests on, and looks identical in a screenshot',
);
const chaseShopToggles = dnaToggles().filter((el) => {
  const t = attrText(sheet, el, 'testID') || '';
  return t.includes('dna.chase.') || t.includes('dna.shop.');
});
assert(
  chaseShopToggles.length === 4 &&
    chaseShopToggles.every((el) => !hasAttr(sheet, el, 'glyph')),
  'A-9b — the Chasing and Shopping rows pass NO glyph prop',
  `found ${chaseShopToggles.length} chase/shop toggles, ` +
    `${chaseShopToggles.filter((el) => hasAttr(sheet, el, 'glyph')).length} carrying a glyph`,
);

console.log('');
console.log('═'.repeat(72));
console.log('3 — toggleDnaPos: Chasing ⊕ Avoiding move; Shopping + Avoiding CO-EXIST');
console.log('═'.repeat(72));
// A-3 — THE assertion this file exists for. AST-level, per branch.

const toggleFn = namedFn(sheet, 'toggleDnaPos');
assert(!!toggleFn, 'A-3a — toggleDnaPos is a single named arrow function');

if (toggleFn) {
  const ifs = findAll(toggleFn, (n) => ts.isIfStatement(n) && within(n, toggleFn));
  const outer = ifs[0];
  assert(
    !!outer && /side\s*===\s*'chase'/.test(outer.expression.getText(sheet)),
    "A-3b — the first branch tests side === 'chase'",
  );
  const chaseBranch = outer && outer.thenStatement;
  const elseIf = outer && outer.elseStatement;
  const isElseIf = elseIf && ts.isIfStatement(elseIf);
  assert(
    !!isElseIf && /side\s*===\s*'shop'/.test(elseIf.expression.getText(sheet)),
    "A-3c — the second branch tests side === 'shop'",
    'the three-way move collapsed back to a two-way if/else',
  );
  const shopBranch = isElseIf ? elseIf.thenStatement : null;
  const avoidBranch = isElseIf ? elseIf.elseStatement : null;

  /** Text of `let <target> = …` / `<target> = …` inside a branch. */
  const rhsOf = (branch, target) => {
    if (!branch) return null;
    const hits = findAll(
      branch,
      (n) =>
        ts.isBinaryExpression(n) &&
        n.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
        ts.isIdentifier(n.left) &&
        n.left.text === target,
    );
    return hits.length ? hits[hits.length - 1].right : null;
  };
  const isFilterOn = (node, list) =>
    !!node &&
    ts.isCallExpression(node) &&
    ts.isPropertyAccessExpression(node.expression) &&
    node.expression.name.text === 'filter' &&
    node.expression.expression.getText(sheet) === list;
  const isPlainRef = (node, list) =>
    !!node && ts.isIdentifier(node) && node.text === list;

  // chase clears BOTH other rows.
  assert(
    isFilterOn(rhsOf(chaseBranch, 'nextShopping'), 'draftShopping') &&
      isFilterOn(rhsOf(chaseBranch, 'nextAvoiding'), 'draftAvoiding'),
    "A-3d — tapping 'chase' REMOVES the position from Shopping AND Avoiding",
    'chasing and avoiding the same position contradict; chasing and shopping ' +
      'it already did',
  );

  // shop clears chase, LEAVES avoid.
  assert(
    isFilterOn(rhsOf(shopBranch, 'nextChasing'), 'draftChasing'),
    "A-3e — tapping 'shop' removes the position from Chasing",
  );
  assert(
    isPlainRef(rhsOf(shopBranch, 'nextAvoiding'), 'draftAvoiding'),
    "A-3f — tapping 'shop' LEAVES Avoiding UNCHANGED (D-094)",
    'filtering draftAvoiding here makes Shopping and Avoiding mutually ' +
      'exclusive, which destroys the headline use case: "I am selling my QB ' +
      'and I do not want another one back"',
  );

  // avoid clears chase, LEAVES shop.
  assert(
    isFilterOn(rhsOf(avoidBranch, 'nextChasing'), 'draftChasing'),
    "A-3g — tapping 'avoid' removes the position from Chasing",
  );
  assert(
    isPlainRef(rhsOf(avoidBranch, 'nextShopping'), 'draftShopping'),
    "A-3h — tapping 'avoid' LEAVES Shopping UNCHANGED (D-094)",
    'the mirror of A-3f — same use case, tapped from the other row',
  );
}

console.log('');
console.log('═'.repeat(72));
console.log('4 — all six autosave payload sites carry the fourth list');
console.log('═'.repeat(72));
// A-4 — a miss on ANY ONE of these fails silently: the clear never persists
// and the next sheet open re-seeds the stale value.

// (1) saveOutlook's mutation vars type + the POST body it builds.
const saveCalls = findAll(
  sheet,
  (n) =>
    ts.isCallExpression(n) &&
    ts.isIdentifier(n.expression) &&
    n.expression.text === 'saveLeaguePreferences',
);
assert(saveCalls.length === 1, 'A-4 (1a) — one saveLeaguePreferences call in the sheet');
const bodyObj = saveCalls[0] && saveCalls[0].arguments[1];
assert(
  !!bodyObj &&
    ts.isObjectLiteralExpression(bodyObj) &&
    bodyObj.properties.some(
      (p) => p.name && p.name.getText(sheet) === 'avoid_positions',
    ),
  'A-4 (1b) — the POST body carries avoid_positions',
  'the backend leaves the stored value untouched when the key is absent, and ' +
    'echoes [] back — the echo is not authoritative, so the miss is invisible',
);

// The three type literals that describe the payload: saveOutlook vars,
// dnaDesired's ref shape, queueDnaSave's parameter.
const payloadTypeLiterals = findAll(sheet, (n) => {
  if (!ts.isTypeLiteralNode(n)) return false;
  const names = n.members
    .map((m) => (m.name ? m.name.getText(sheet) : ''))
    .filter(Boolean);
  return names.includes('outlook') && names.includes('acquire') && names.includes('shed');
});
assert(
  payloadTypeLiterals.length === 3,
  'A-4 (2a/4a) — three payload type literals (saveOutlook vars, dnaDesired, queueDnaSave param)',
  `found ${payloadTypeLiterals.length}`,
);
assert(
  payloadTypeLiterals.length === 3 &&
    payloadTypeLiterals.every((n) =>
      n.members.some((m) => m.name && m.name.getText(sheet) === 'avoid'),
    ),
  'A-4 (2b/4b) — every payload type literal declares `avoid`',
  'dropping it from any one of them makes the omission a compile-time no-op ' +
    'instead of an error',
);

// (3) the error-revert in flushDnaSave.
const flushFn = namedFn(sheet, 'flushDnaSave');
assert(
  !!flushFn && /setDraftAvoiding\s*\(/.test(flushFn.getText(sheet)),
  'A-4 (3) — flushDnaSave reverts draftAvoiding on a failed save',
  'without it a failed POST leaves the Avoiding row showing state the server ' +
    'rejected, while Chasing and Shopping honestly roll back',
);

// (5)/(6) both queueDnaSave call sites pass `avoid`.
const queueCalls = findAll(
  sheet,
  (n) =>
    ts.isCallExpression(n) &&
    ts.isIdentifier(n.expression) &&
    n.expression.text === 'queueDnaSave',
);
assert(
  queueCalls.length === 2,
  'A-4 (5a/6a) — exactly two queueDnaSave call sites (pickOutlook, toggleDnaPos)',
  `found ${queueCalls.length}`,
);
assert(
  queueCalls.length === 2 &&
    queueCalls.every(
      (c) =>
        c.arguments[0] &&
        ts.isObjectLiteralExpression(c.arguments[0]) &&
        c.arguments[0].properties.some(
          (p) => p.name && p.name.getText(sheet) === 'avoid',
        ),
    ),
  'A-4 (5b/6b) — every queueDnaSave call passes `avoid`',
  'an outlook tap that omits it re-POSTs a stale (or empty) avoid list, ' +
    'silently reverting the user\'s last Avoiding edit',
);

// The seeding effect — without it the row opens empty on every sheet open.
assert(
  /setDraftAvoiding\(\s*prefs\?\.avoid_positions/.test(sheet.getFullText()),
  'A-4 (7) — the seeding effect reads prefs.avoid_positions',
  'the row would open empty and the first tap would POST a list of one, ' +
    'wiping everything else the user had avoided',
);

console.log('');
console.log('═'.repeat(72));
console.log('5 — flag gating: every Avoiding RENDER site sits behind the kill switch');
console.log('═'.repeat(72));

// A-7 — the render is gated; the state, the seeding and the payload are NOT
// (so a flag flip in either direction preserves the user's saved set).
assert(
  /useFlag\(\s*'trade\.avoid_positions'\s*\)/.test(sheet.getFullText()),
  "A-7a — the sheet reads useFlag('trade.avoid_positions')",
);
assert(
  avoidToggles.length === 2 &&
    avoidToggles.every(
      (el) =>
        !!ancestor(
          el,
          (n) =>
            ts.isConditionalExpression(n) &&
            /\bavoidOn\b/.test(n.condition.getText(sheet)),
        ),
    ),
  'A-7b — every dna.avoid.* render site has an `avoidOn` conditional ancestor',
  'rendering it unconditionally means flag-off is no longer byte-identical, ' +
    'and the sheet keeps accepting a preference the engine has stopped honoring',
);

console.log('');
console.log('═'.repeat(72));
console.log('6 — the legacy hint states the THREE-way rule when the row is live');
console.log('═'.repeat(72));

// A-8 — the shipped-on hint must not still claim two-way exclusion. It is a
// flag-conditional: with the row hidden the ORIGINAL sentence stays verbatim
// (flag-off byte-identity), so the assertion targets the flag-ON branch.
//
// Deviation from PRD A-10's sibling wording, recorded on purpose: the PRD
// asked for "the string appears nowhere in the file". That is incompatible
// with flag-off byte-identity, which R-11 also requires. Pinning the ON
// branch is the assertion that actually protects the user.
const hintTexts = jsxElementsWithStyle(sheet, 'dnaHint');
assert(hintTexts.length === 1, 'A-8a — exactly one styles.dnaHint block');
if (hintTexts.length === 1) {
  const cond = findAll(
    hintTexts[0],
    (n) => ts.isConditionalExpression(n) && /\bavoidOn\b/.test(n.condition.getText(sheet)),
  )[0];
  assert(!!cond, 'A-8b — the hint copy is conditional on avoidOn');
  if (cond) {
    const onBranch = stripComments(cond.whenTrue.getText(sheet));
    assert(
      !/both chased and shopped/.test(onBranch),
      'A-8c — the flag-ON hint no longer claims two-way exclusion',
      'a hint still saying "can\'t be both chased and shopped" after the ' +
        'three-way move ships is actively wrong documentation in the product',
    );
    assert(
      /avoid/i.test(onBranch) && /Shopping and avoiding/i.test(onBranch),
      'A-8d — the flag-ON hint states the Shopping + Avoiding exception',
      'the exception IS the feature; a hint that omits it teaches the user ' +
        'the headline use case is impossible',
    );
  }
}

console.log('');
console.log('═'.repeat(72));
console.log('7 — the deck surfaces Avoiding, above and after an empty result');
console.log('═'.repeat(72));

// A-5 — the receipt banner names Avoiding, ordered after Shopping. This is
// what keeps "an exclusion beats a pin" honest instead of silent.
const receipt = namedFn(deck, 'receiptDetails');
assert(!!receipt, 'A-5a — receiptDetails is a single named memo');
if (receipt) {
  const src = receipt.getText(deck);
  assert(
    /avoid_positions/.test(stripComments(src)),
    'A-5b — receiptDetails reads avoid_positions',
    'without it the deck never says the promise is in force, and an empty ' +
      'result from a pinned-but-avoided target reads as a bug',
  );
  const idx = (label) => src.indexOf('`' + label + ' ${');
  assert(
    idx('Chasing') >= 0 && idx('Shopping') > idx('Chasing') && idx('Avoiding') > idx('Shopping'),
    'A-5c — the receipt order is Chasing · Shopping · Avoiding',
    `Chasing@${idx('Chasing')} Shopping@${idx('Shopping')} Avoiding@${idx('Avoiding')}`,
  );
}

// A-6 — the empty-state toast names Avoiding as the cause. The server-side
// avoid-beats-chase guard and this copy ship together or neither is done.
const intentCopyDecl = findAll(
  deck,
  (n) =>
    ts.isVariableDeclaration(n) &&
    ts.isIdentifier(n.name) &&
    n.name.text === 'intentCopy',
)[0];
assert(!!intentCopyDecl, 'A-6a — the intent-aware empty-state ladder is still present');
if (intentCopyDecl) {
  const block = ancestor(intentCopyDecl, (n) => ts.isBlock(n));
  const src = stripComments(block.getText(deck));
  assert(
    /avoid_positions/.test(src),
    'A-6b — the empty-state branch reads avoid_positions',
    'shipping the server-side avoid-beats-chase guard without this copy ' +
      'leaves the user staring at "no trades found" with no idea why',
  );
  assert(
    /Try un-avoiding one\./.test(src),
    'A-6c — the empty-state copy names the way out',
    'copy that states the cause but not the remedy is half an answer',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All avoid-positions (#360/#361) checks passed.');
