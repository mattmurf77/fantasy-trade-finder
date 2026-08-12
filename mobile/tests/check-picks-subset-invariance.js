#!/usr/bin/env node
// #293/#294 — draft-pick value is subset- and filter-independent on
// LeagueRankings, behind `league.picks_always_counted` (default OFF).
//
// WHY THIS EXISTS. The operator ruled that a team's draft-pick contribution
// must never silently drop when the user switches to Starters/Bench or
// filters by position. That reverses a rule this screen documented in eight
// places, and it ships behind a kill switch — which is exactly the shape of
// change that can go half-done and still look right.
//
// The specific hazard, and the reason a screenshot cannot catch it: a bar's
// HEIGHT comes from `active` (activeTotal), while its SEGMENT heights are
// `segValue(p) / segSum` — percentages of their own sum. Gate `activeTotal`
// but not `shownBase`/`segValue` and a Starters bar grows by the team's pick
// value while its four position segments silently stretch to fill the extra
// space. The chart looks plausible and misattributes every point of draft
// capital to the positions. No screenshot diff, no Maestro assertion and no
// type error sees that. This file does.
//
// So the invariant pinned here is ATOMICITY: the flag is read ONCE, and every
// gated expression resolves to that same value within a render. prd.md R-0.2
// listed fourteen gated expressions (G1–G14); TWELVE remain, reached by
// exactly three gating symbols — the component-body identifier, `activeTotal`'s
// required 4th parameter, and `BarColumn`'s required prop — because the latter
// two are module-scope and cannot close over the first.
//
// G4 and G5 — `togglePos`'s rule A (auto-add PICKS on the first position tap)
// and rule B (removing the last core position clears to All) — were REMOVED by
// operator decision on 2026-08-12: "All leagues have picks. They should not be
// selected along with a position filter. Only by explicit user action."
// `togglePos` is therefore flag-INDEPENDENT, and section 3.5 asserts that
// absence in three shapes rather than asserting a gate. Rule B fell with rule
// A: its stated purpose was to keep the user out of a picks-only ranking "they
// never asked for", which only existed because rule A could put PICKS there
// unasked — with A gone, every PICKS is hand-chosen and clearing to All would
// discard the very explicit choice the ruling protects.
//
// Assertions 13 and 14 are not optional garnish: adversarial review found two
// verified escape hatches through which a build could pass every other
// assertion and still ship a half-gated screen.
//   • 13 closes the `activeTotal` call-site hatch — the function has TWO
//     callers (the bars, and the #248 other-basis overlay). Threading only
//     the bars makes the two bases differ by exactly the pick value, flipping
//     `boardsDifferInView` true and drawing a fabricated tick and rank-swing
//     chip on every column: #208's reported symptom, reintroduced by the fix
//     for #293. Assertion 3 never looked, because a call site is not one of
//     the gated expressions.
//   • 14 closes the `BarColumn` prop hatch — a parameter binding inside
//     `BarColumn` is a DIFFERENT symbol from the component-body identifier,
//     so `picksAlwaysCounted={false}` (or `{subset === 'all'}`) satisfies
//     "no useFlag inside BarColumn" and "its gated expressions branch on the
//     prop" while shipping the exact segSum failure above. Assertion 14 is
//     the only mechanical link between the two halves of atomicity.
//
// Structural, not textual: this parses the real TSX with the project's own
// TypeScript and walks the AST, exactly like check-member-entered-marker.js
// and check-mock-mode-marker.js. A grep passes on a guard that merely moved.
// Seed-independent — no simulator, no backend, no pick data required.
//
// Run: node tests/check-picks-subset-invariance.js
//   (or: npm run test:picks-subset-invariance)

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

const REL = 'src/screens/LeagueSummaryScreen.tsx';
const FLAG_KEY = 'league.picks_always_counted';

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

/** Collapse whitespace so multi-line expressions compare as one string. */
function flat(n) {
  return txt(n).replace(/\s+/g, ' ').trim();
}

function fnDecl(name) {
  return findAll(
    src,
    (n) => ts.isFunctionDeclaration(n) && n.name && n.name.getText(src) === name,
  )[0];
}

/** The `const <name> = …` initializer anywhere under `root`. */
function varInit(root, name) {
  const d = findAll(
    root,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.getText(src) === name,
  )[0];
  return d ? d.initializer : undefined;
}

function calls(root, name) {
  return findAll(
    root,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.getText(src) === name,
  );
}

function unparen(n) {
  let cur = n;
  while (cur && ts.isParenthesizedExpression(cur)) cur = cur.expression;
  return cur;
}

function isLogical(n) {
  return (
    ts.isBinaryExpression(n) &&
    (n.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken ||
      n.operatorToken.kind === ts.SyntaxKind.BarBarToken)
  );
}

/**
 * Identifier names that appear in a CONDITION position under `root`:
 * a ternary's condition, an `if`'s expression, or an operand of `&&` / `||`.
 * This is what "branches on X" means for assertion 3 — an identifier merely
 * mentioned in a branch body does not gate anything.
 */
function condIdents(root) {
  const names = new Set();
  const collect = (n) => {
    if (!n) return;
    for (const id of findAll(n, (x) => ts.isIdentifier(x))) names.add(id.getText(src));
  };
  walk(root, (n) => {
    if (ts.isConditionalExpression(n)) collect(n.condition);
    else if (ts.isIfStatement(n)) collect(n.expression);
    else if (isLogical(n)) {
      collect(n.left);
      collect(n.right);
    }
  });
  return names;
}

/** Ternaries under `root` whose condition is EXACTLY the identifier `name`. */
function flagTernaries(root, name) {
  return findAll(
    root,
    (n) =>
      ts.isConditionalExpression(n) &&
      ts.isIdentifier(unparen(n.condition)) &&
      unparen(n.condition).getText(src) === name,
  );
}

/** True when `n` is `!<name>` (allowing parens). */
function isNegationOf(n, name) {
  const u = unparen(n);
  return (
    u &&
    ts.isPrefixUnaryExpression(u) &&
    u.operator === ts.SyntaxKind.ExclamationToken &&
    ts.isIdentifier(unparen(u.operand)) &&
    unparen(u.operand).getText(src) === name
  );
}

/** Does `root` contain `!<name>` anywhere? */
function hasNegation(root, name) {
  return findAll(root, (n) => isNegationOf(n, name)).length > 0;
}

function jsxTag(n) {
  if (ts.isJsxSelfClosingElement(n)) return n.tagName.getText(src);
  if (ts.isJsxElement(n)) return n.openingElement.tagName.getText(src);
  return null;
}

function jsxAttr(n, name) {
  const opening = ts.isJsxSelfClosingElement(n) ? n : n.openingElement;
  for (const a of opening.attributes.properties) {
    if (ts.isJsxAttribute(a) && a.name && a.name.getText(src) === name) return a;
  }
  return null;
}

// ── The three scopes ───────────────────────────────────────────────────────

const componentFn = fnDecl('LeagueSummaryScreen');
const activeTotalFn = fnDecl('activeTotal');
const barColumnFn = fnDecl('BarColumn');

assert(!!componentFn, 'LeagueSummaryScreen component found');
assert(!!activeTotalFn, 'activeTotal declaration found');
assert(!!barColumnFn, 'BarColumn declaration found');
if (!componentFn || !activeTotalFn || !barColumnFn) {
  console.error('\nCannot continue without all three scopes.');
  process.exit(1);
}

// ═══════════════════════════════════════════════════════════════════════════
// 1 — exactly ONE read site for the flag
// ═══════════════════════════════════════════════════════════════════════════

const flagReads = findAll(
  src,
  (n) =>
    ts.isCallExpression(n) &&
    ts.isIdentifier(n.expression) &&
    n.expression.getText(src) === 'useFlag' &&
    n.arguments.length === 1 &&
    ts.isStringLiteral(n.arguments[0]) &&
    n.arguments[0].text === FLAG_KEY,
);
assert(
  flagReads.length === 1,
  `1 — exactly one useFlag('${FLAG_KEY}') call site`,
  `found ${flagReads.length}; R-0.2 requires the flag be read once into a single boolean`,
);
if (flagReads.length !== 1) {
  console.error('\nCannot continue without the single flag read.');
  process.exit(1);
}

// The identifier every component-body gated expression must branch on.
let FLAG_ID = null;
for (let p = flagReads[0].parent; p; p = p.parent) {
  if (ts.isVariableDeclaration(p) && ts.isIdentifier(p.name)) {
    FLAG_ID = p.name.getText(src);
    break;
  }
}
assert(
  !!FLAG_ID,
  '1b — the flag read is bound to a named const',
  'a bare useFlag() call cannot gate anything',
);
if (!FLAG_ID) process.exit(1);

assert(
  componentFn.getStart(src) <= flagReads[0].getStart(src) &&
    flagReads[0].getEnd() <= componentFn.getEnd(),
  '1c — the read lives in the component body',
  'module-scope consumers take it as a parameter/prop instead',
);

// ═══════════════════════════════════════════════════════════════════════════
// 2 — no second useFlag inside BarColumn or activeTotal
// ═══════════════════════════════════════════════════════════════════════════

for (const [name, fn] of [
  ['BarColumn', barColumnFn],
  ['activeTotal', activeTotalFn],
]) {
  assert(
    calls(fn, 'useFlag').length === 0,
    `2 — no useFlag call inside ${name}`,
    'a second read is a second source of truth and can disagree mid-render',
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 3 — every gated expression branches on its CORRECT gating symbol
// ═══════════════════════════════════════════════════════════════════════════
//
// Three symbols, per R-0.2: the component-body identifier (G3–G7, G9, G11,
// G14), activeTotal's 4th parameter (G1, G2), BarColumn's prop (G12, G13).
// G8/G10 gate transitively through `picksInView`, which is itself G7.

const atParams = activeTotalFn.parameters;
assert(
  atParams.length === 4,
  '3a — activeTotal declares a 4th parameter',
  `found ${atParams.length}`,
);
const AT_FLAG_PARAM = atParams.length === 4 ? atParams[3].name.getText(src) : null;

const bcParam = barColumnFn.parameters[0];
let BC_FLAG_PROP = null;
if (bcParam && ts.isObjectBindingPattern(bcParam.name)) {
  for (const el of bcParam.name.elements) {
    const propName = el.propertyName
      ? el.propertyName.getText(src)
      : el.name.getText(src);
    if (propName === 'picksAlwaysCounted') {
      BC_FLAG_PROP = el.name.getText(src);
      assert(
        el.initializer === undefined,
        '3b — BarColumn destructures picksAlwaysCounted with NO default',
        'a default lets an omitted prop compile and silently behave as OFF',
      );
    }
  }
}
assert(
  !!BC_FLAG_PROP,
  '3c — BarColumn destructures a picksAlwaysCounted prop',
  'it is module-scope and cannot close over the component identifier',
);

// G3, G7 — component-body initializers.
const showPicksKeyInit = varInit(componentFn, 'showPicksKey');
const picksInViewInit = varInit(componentFn, 'picksInView');
// G6 — component-body function body. (G4/G5 — #294's togglePos rules A and B
// — were REMOVED on 2026-08-12; section 3.5 below pins their absence.)
const togglePosInit = varInit(componentFn, 'togglePos');
const switchSubsetInit = varInit(componentFn, 'switchSubset');

// G9 — the filtered hint branch (the one string gated on the RAW flag).
// Locate the innermost template carrying the sentence, then the flag ternary
// inside it — the ENCLOSING template also contains the sentence, so "smallest
// match wins" matters here.
const hintHost = findAll(
  componentFn,
  (n) => ts.isTemplateExpression(n) && txt(n).includes('value only — chart reordered.'),
).sort((a, b) => a.getWidth(src) - b.getWidth(src))[0];
const hintTernary = hintHost ? flagTernaries(hintHost, FLAG_ID)[0] : null;

// G11 — the drill-in Draft-capital group's JSX condition. Found by walking UP
// from the group's own element: several outer ternaries (the drill panel vs
// the ranked list, for one) also CONTAIN this testID, and a pre-order search
// would silently pick one of those and assert nothing.
const drillGroupEl = findAll(
  componentFn,
  (n) => jsxTag(n) !== null && !!jsxAttr(n, 'testID') &&
    flat(jsxAttr(n, 'testID').initializer) === '"league-summary.roster-picks"',
)[0];
let drillGroupTernary = null;
for (let p = drillGroupEl ? drillGroupEl.parent : null; p; p = p.parent) {
  if (ts.isConditionalExpression(p)) {
    drillGroupTernary = p;
    break;
  }
}

// G14 — the ON→OFF reconciliation effect.
const reconcileEffect = calls(componentFn, 'useEffect').filter((c) =>
  flat(c).includes("delete('PICKS')"),
)[0];

const bodyGated = [
  ['G3 showPicksKey', showPicksKeyInit],
  ['G6 switchSubset', switchSubsetInit],
  ['G7 picksInView', picksInViewInit],
  ['G9 filtered hint branch', hintTernary],
  ['G11 drill Draft-capital condition', drillGroupTernary ? drillGroupTernary.condition : null],
  ['G14 reconciliation effect', reconcileEffect],
];
for (const [label, node] of bodyGated) {
  assert(
    !!node && condIdents(node).has(FLAG_ID),
    `3 — ${label} branches on \`${FLAG_ID}\``,
    node ? 'the identifier is not in a condition position' : 'expression not found',
  );
}

for (const [label, node, sym] of [
  ['G1/G2 activeTotal', activeTotalFn, AT_FLAG_PARAM],
  ['G12 shownBase', varInit(barColumnFn, 'shownBase'), BC_FLAG_PROP],
  ['G13 segValue', varInit(barColumnFn, 'segValue'), BC_FLAG_PROP],
]) {
  assert(
    !!node && !!sym && condIdents(node).has(sym),
    `3 — ${label} branches on its own \`${sym}\` binding`,
    'a module-scope function must gate on its parameter/prop, not a free name',
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 3.5 — togglePos is a PLAIN toggle: #294's rules A and B are GONE
// ═══════════════════════════════════════════════════════════════════════════
//
// Operator decision, 2026-08-12: "All leagues have picks. They should not be
// selected along with a position filter. Only by explicit user action."
// So the two rules #294 added here (G4 auto-add, G5 exit-to-All) are removed,
// and `togglePos` is flag-INDEPENDENT. That is the one gated expression in
// R-0.2's G1–G14 that is deliberately no longer gated, which makes it the one
// place where "the flag is not mentioned" is the assertion rather than the
// bug. The three checks below are the exact inverse of the old
// `3 — G4/G5 togglePos branches on the flag` row, and between them they close
// every shape rule A or rule B could come back in:
//
//   3e  no reference to the flag identifier at all — a re-added rule needs it
//       (both rules lived under `if (picksAlwaysCounted && …)`);
//   3f  no 'PICKS' literal — rule A's payload was `next.add('PICKS')`, and
//       any auto-add must name the key it adds;
//   3g/h exactly one empty `new Set()`, and it is the `pos === 'ALL'` branch —
//       rule B's payload was a SECOND `return new Set()` on a different
//       condition. Counting alone would not say WHICH one survived, so 3h
//       pins the survivor to the ALL clear.
//
// AST-level, not textual: identifiers and string literals are nodes, so the
// history comment above `togglePos` — which necessarily names both
// `picksAlwaysCounted` and 'PICKS' — cannot satisfy or defeat any of them.

const toggleFlagIds = togglePosInit
  ? findAll(togglePosInit, (n) => ts.isIdentifier(n) && n.getText(src) === FLAG_ID)
  : [];
assert(
  !!togglePosInit && toggleFlagIds.length === 0,
  `3e — togglePos does not reference \`${FLAG_ID}\``,
  togglePosInit
    ? `found ${toggleFlagIds.length}; the pill toggle is flag-independent since the 2026-08-12 reversal`
    : 'togglePos not found',
);

const togglePicksLits = togglePosInit
  ? findAll(togglePosInit, (n) => ts.isStringLiteral(n) && n.text === 'PICKS')
  : [];
assert(
  !!togglePosInit && togglePicksLits.length === 0,
  "3f — togglePos contains no 'PICKS' literal (rule A's auto-add is gone)",
  `found ${togglePicksLits.length}; pick value is an explicit pill tap, never a side effect of tapping a position`,
);

const toggleEmptySets = togglePosInit
  ? findAll(
      togglePosInit,
      (n) =>
        ts.isNewExpression(n) &&
        n.expression.getText(src) === 'Set' &&
        (!n.arguments || n.arguments.length === 0),
    )
  : [];
assert(
  toggleEmptySets.length === 1,
  '3g — togglePos constructs exactly ONE empty `new Set()`',
  `found ${toggleEmptySets.length}; a second one is rule B (exit-to-All), which would discard a hand-chosen PICKS`,
);
let toggleAllGate = null;
if (toggleEmptySets.length === 1) {
  for (let p = toggleEmptySets[0].parent; p && p !== togglePosInit; p = p.parent) {
    if (ts.isIfStatement(p)) {
      toggleAllGate = p.expression;
      break;
    }
  }
}
assert(
  !!toggleAllGate && /pos === 'ALL'/.test(flat(toggleAllGate)),
  "3h — that empty Set is the `pos === 'ALL'` branch",
  toggleAllGate
    ? `guarded by \`${flat(toggleAllGate)}\` instead`
    : 'no enclosing if — the clear must be the All pill, not a derived rule',
);

// ═══════════════════════════════════════════════════════════════════════════
// 4 / 5 — activeTotal's two arms, ON and OFF
// ═══════════════════════════════════════════════════════════════════════════

const atTernaries = AT_FLAG_PARAM ? flagTernaries(activeTotalFn, AT_FLAG_PARAM) : [];
assert(
  atTernaries.length === 2,
  '4a — activeTotal has exactly two flag-conditioned arms (G1, G2)',
  `found ${atTernaries.length}`,
);

const emptyArm = atTernaries.find((t) => /^tc\.coreTotal$/.test(flat(t.whenFalse)));
assert(
  !!emptyArm,
  '4b — G1 flag-OFF arm returns bare `tc.coreTotal`',
  'flag OFF must be byte-identical to origin/main: no `+ picks`',
);
if (emptyArm) {
  const on = flat(emptyArm.whenTrue);
  assert(
    on.includes('coreTotal') && /picks/.test(on),
    '4c — G1 flag-ON arm adds the team pick value to coreTotal',
    `saw: ${on}`,
  );
}

const picksArm = atTernaries.find((t) => flat(t.whenFalse).includes("subset === 'all'"));
assert(
  !!picksArm,
  "5a — G2 flag-OFF arm keeps `subset === 'all' ? … : 0`",
  'the literal 0 outside All is the shipped behavior the kill switch restores',
);
if (picksArm) {
  assert(
    /:\s*0\s*$/.test(flat(picksArm.whenFalse)),
    '5b — G2 flag-OFF arm still contributes a literal 0 outside All',
    `saw: ${flat(picksArm.whenFalse)}`,
  );
  const on = flat(picksArm.whenTrue);
  assert(
    !on.includes('subset') && /picks/.test(on),
    '5c — G2 flag-ON arm has NO subset ternary and returns the pick value',
    `saw: ${on}`,
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 6 — showPicksKey
// ═══════════════════════════════════════════════════════════════════════════

const spkTernary =
  showPicksKeyInit && ts.isConditionalExpression(unparen(showPicksKeyInit))
    ? unparen(showPicksKeyInit)
    : null;
assert(
  !!spkTernary && flat(spkTernary.condition) === FLAG_ID,
  '6a — showPicksKey is a ternary on the flag identifier',
);
if (spkTernary) {
  assert(
    flat(spkTernary.whenTrue) === 'hasPicks',
    '6b — showPicksKey flag-ON arm is bare `hasPicks`',
    `saw: ${flat(spkTernary.whenTrue)} — the pill and legend must render in every subset`,
  );
  assert(
    flat(spkTernary.whenFalse).includes("subset === 'all'"),
    "6c — showPicksKey flag-OFF arm keeps `&& subset === 'all'`",
    `saw: ${flat(spkTernary.whenFalse)}`,
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 7 — BarColumn's segment composition (the segSum hazard)
// ═══════════════════════════════════════════════════════════════════════════

const segValueInit = varInit(barColumnFn, 'segValue');
const segTernary = BC_FLAG_PROP ? flagTernaries(segValueInit || barColumnFn, BC_FLAG_PROP)[0] : null;
assert(
  !!segTernary,
  '7a — segValue has a flag-conditioned PICKS arm',
  'without it the bar grows by the pick value while its segments stretch to fill',
);
if (segTernary) {
  assert(
    !flat(segTernary.whenTrue).includes('subset'),
    '7b — segValue flag-ON PICKS arm has no `subset` ternary',
    `saw: ${flat(segTernary.whenTrue)}`,
  );
  assert(
    flat(segTernary.whenFalse).includes("subset === 'all'"),
    '7c — segValue flag-OFF PICKS arm keeps the All-subset guard',
  );
}

const shownBaseInit = varInit(barColumnFn, 'shownBase');
// The unfiltered branch: `filter.size > 0 ? [...filter] : <inner>`.
const shownOuter =
  shownBaseInit && ts.isConditionalExpression(unparen(shownBaseInit))
    ? unparen(shownBaseInit)
    : null;
const shownInner = shownOuter ? unparen(shownOuter.whenFalse) : null;
assert(
  !!shownInner && ts.isConditionalExpression(shownInner),
  '7d — shownBase branches for the unfiltered case',
);
if (shownInner && ts.isConditionalExpression(shownInner)) {
  const cond = unparen(shownInner.condition);
  const flagIsLeftOfOr =
    isLogical(cond) &&
    cond.operatorToken.kind === ts.SyntaxKind.BarBarToken &&
    ts.isIdentifier(unparen(cond.left)) &&
    unparen(cond.left).getText(src) === BC_FLAG_PROP;
  assert(
    flagIsLeftOfOr,
    '7e — shownBase\'s unfiltered condition is `<flag prop> || subset === \'all\'`',
    `saw: ${flat(cond)} — flag ON must include PICKS regardless of subset`,
  );
  assert(
    flat(shownInner.whenTrue).includes("'PICKS'"),
    '7f — shownBase flag-ON unfiltered branch includes PICKS in every subset',
    `saw: ${flat(shownInner.whenTrue)}`,
  );
  assert(
    !flat(shownInner.whenFalse).includes("'PICKS'"),
    '7g — shownBase flag-OFF non-All branch still omits PICKS',
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 8 — switchSubset mutates the filter only on the flag-OFF path
// ═══════════════════════════════════════════════════════════════════════════

const setPosFilterInSwitch = switchSubsetInit ? calls(switchSubsetInit, 'setPosFilter') : [];
assert(
  setPosFilterInSwitch.length === 1,
  '8a — switchSubset still carries exactly one setPosFilter call',
  `found ${setPosFilterInSwitch.length}; the synchronous OFF-path strip must NOT be deleted ` +
    'in favour of the R-0.4 effect — the effect runs a render later',
);
for (const c of setPosFilterInSwitch) {
  let guarded = false;
  for (let p = c.parent; p && p !== switchSubsetInit; p = p.parent) {
    if (ts.isIfStatement(p) && hasNegation(p.expression, FLAG_ID)) {
      guarded = true;
      break;
    }
  }
  assert(
    guarded,
    `8b — switchSubset calls setPosFilter only under \`!${FLAG_ID}\``,
    'flag ON, switching subset must never mutate the filter (R-5)',
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 9 — the drill Draft-capital group's `subset === 'all'` is OFF-branch only
// ═══════════════════════════════════════════════════════════════════════════

assert(!!drillGroupTernary, '9a — the drill Draft-capital group condition was found');
if (drillGroupTernary) {
  const cond = drillGroupTernary.condition;
  const subsetChecks = findAll(
    cond,
    (n) => ts.isBinaryExpression(n) && flat(n) === "subset === 'all'",
  );
  assert(
    subsetChecks.length >= 1,
    "9b — the flag-OFF branch still requires `subset === 'all'`",
    'the kill switch must restore All-subset-only rendering',
  );
  for (const sc of subsetChecks) {
    let offBranch = false;
    for (let p = sc.parent, child = sc; p && p !== cond.parent; child = p, p = p.parent) {
      // `<flag> || subset === 'all'` — the right operand is the OFF branch.
      if (
        isLogical(p) &&
        p.operatorToken.kind === ts.SyntaxKind.BarBarToken &&
        ts.isIdentifier(unparen(p.left)) &&
        unparen(p.left).getText(src) === FLAG_ID &&
        p.right === child
      ) {
        offBranch = true;
        break;
      }
      // `<flag> ? … : subset === 'all'` — whenFalse is the OFF branch.
      if (
        ts.isConditionalExpression(p) &&
        ts.isIdentifier(unparen(p.condition)) &&
        unparen(p.condition).getText(src) === FLAG_ID &&
        p.whenFalse === child
      ) {
        offBranch = true;
        break;
      }
    }
    assert(
      offBranch,
      "9c — every `subset === 'all'` in the drill group condition sits on the flag-OFF branch",
      'flag ON, the Draft-capital group must render under Starters and Bench too (R-7)',
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 10 — picksInView is itself flag-gated
// ═══════════════════════════════════════════════════════════════════════════

assert(
  !!picksInViewInit && condIdents(picksInViewInit).has(FLAG_ID),
  '10a — picksInView\'s initializer references the flag identifier',
  'ungated, the copy would change while the arithmetic did not (R-0.1)',
);
assert(
  !!picksInViewInit && /hasPicks/.test(flat(picksInViewInit)),
  '10b — picksInView is also gated on hasPicks',
  'no-picks leagues must be byte-identical in both flag states (R-11)',
);

// ═══════════════════════════════════════════════════════════════════════════
// 11 — teamPosRank stays picks-free
// ═══════════════════════════════════════════════════════════════════════════

const teamPosRankInit = varInit(componentFn, 'teamPosRank');
assert(
  !!teamPosRankInit && !/picks/i.test(txt(teamPosRankInit)),
  '11 — teamPosRank contains no `picks` reference',
  '"your RB room is 3rd of 12" must never be inflated by draft capital (R-10)',
);

// ═══════════════════════════════════════════════════════════════════════════
// 12 — the #279/#285 total_value_label gate is NOT widened
// ═══════════════════════════════════════════════════════════════════════════

// #300 (commit 1c3471a) folded the screen's TWO inline `total_value_label`
// render sites into ONE shared helper (`activeValueLabel`), and moved its gate
// from a JSX `&&`/ternary into an `if (…) return …` statement. The invariant
// this section defends is unchanged — the label may only describe the
// unfiltered All view, and may never ride the picks flag — but the two shape
// assumptions baked into the old checks (a count of 2, and a gate that is
// always an EXPRESSION) both broke, which is why 12a–12c were failing on this
// branch before the 2026-08-12 rule-A removal touched anything. Re-pinned to
// the current shape, deliberately no weaker: one render path (12a), still
// gated on `subset === 'all' && posFilter.size === 0` whether that gate is an
// expression or an `if` (12b), and now flag-free across the WHOLE helper
// rather than just the gate expression (12c) — a helper with one label branch
// has room for a flag-dependent second branch that a gate-only check misses.
const labelSites = findAll(
  componentFn,
  (n) => ts.isPropertyAccessExpression(n) && n.name.getText(src) === 'total_value_label',
);
assert(
  labelSites.length === 1,
  '12a — total_value_label has exactly ONE render path (`activeValueLabel`)',
  `found ${labelSites.length}; every extra site is an unguarded copy of the gate`,
);
for (let i = 0; i < labelSites.length; i += 1) {
  let gate = null;
  for (let p = labelSites[i].parent; p; p = p.parent) {
    const cond = ts.isIfStatement(p)
      ? p.expression
      : isLogical(p) || ts.isConditionalExpression(p)
        ? p
        : null;
    if (cond && flat(cond).includes('posFilter.size === 0')) {
      gate = cond;
      break;
    }
  }
  assert(
    !!gate && flat(gate).includes("subset === 'all' && posFilter.size === 0"),
    `12b — total_value_label site ${i + 1} keeps the unfiltered-All gate`,
    'there is no server-side starters/bench pick-count decomposition — widening it fabricates',
  );
  let host = labelSites[i].parent;
  while (host && !ts.isArrowFunction(host) && !ts.isFunctionExpression(host)) host = host.parent;
  // AST-level, never `flat().includes()`: a "the flag appears nowhere here"
  // check run on raw source is satisfied — or defeated — by a comment naming
  // the very thing it forbids.
  assert(
    !!gate &&
      !!host &&
      findAll(host, (n) => ts.isIdentifier(n) && n.getText(src) === FLAG_ID).length === 0,
    `12c — total_value_label site ${i + 1} and its whole host function are flag-free`,
    'the #279/#285 label gate is independent of `league.picks_always_counted` and must stay so',
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 13 — BOTH activeTotal call sites are threaded; the param has no default
// ═══════════════════════════════════════════════════════════════════════════
//
// Escape hatch 1. `activeTotal` feeds the bars (`ranked`) AND the #248
// other-basis overlay (`otherByTeam`). Thread only the bars and every
// picks-holding team's two values differ by exactly the pick value, so
// `boardsDifferInView` — a pure difference comparison — flips true and draws
// a fabricated tick + rank-swing chip on every column. That is #208's
// reported symptom, reintroduced by the fix for #293.

const atCalls = calls(src, 'activeTotal');
assert(
  atCalls.length === 2,
  '13a — activeTotal has exactly two call sites',
  `found ${atCalls.length}; if a third appeared it must be threaded too`,
);
for (let i = 0; i < atCalls.length; i += 1) {
  const args = atCalls[i].arguments;
  assert(
    args.length === 4 &&
      ts.isIdentifier(args[3]) &&
      args[3].getText(src) === FLAG_ID,
    `13b — activeTotal call site ${i + 1} passes \`${FLAG_ID}\` as its 4th argument`,
    `saw: ${flat(atCalls[i])}`,
  );
}
if (AT_FLAG_PARAM) {
  const p = atParams[3];
  assert(
    p.initializer === undefined && p.questionToken === undefined,
    '13c — activeTotal\'s 4th parameter has NO default and is not optional',
    'a default lets an unthreaded call site compile and silently behave as OFF',
  );
  assert(
    txt(p.type) === 'boolean',
    '13d — activeTotal\'s 4th parameter is typed boolean',
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 14 — <BarColumn> receives the flag as a BARE IDENTIFIER, prop required
// ═══════════════════════════════════════════════════════════════════════════
//
// Escape hatch 2. A parameter binding inside BarColumn is a different symbol
// from the component-body identifier, so `picksAlwaysCounted={false}` — or
// `{subset === 'all'}` — passes assertions 1, 2 and 3 while shipping the
// exact segSum failure this file exists to prevent. This is the ONLY
// mechanical link between the two halves of the atomicity invariant.

const barUses = findAll(src, (n) => jsxTag(n) === 'BarColumn');
assert(
  barUses.length === 1,
  '14a — BarColumn is instantiated exactly once',
  `found ${barUses.length}`,
);
for (const use of barUses) {
  const attr = jsxAttr(use, 'picksAlwaysCounted');
  assert(!!attr, '14b — the <BarColumn> element passes picksAlwaysCounted');
  if (attr) {
    const init = attr.initializer;
    const expr =
      init && ts.isJsxExpression(init) && init.expression
        ? unparen(init.expression)
        : null;
    assert(
      !!expr && ts.isIdentifier(expr) && expr.getText(src) === FLAG_ID,
      `14c — <BarColumn picksAlwaysCounted={${FLAG_ID}}> is a BARE identifier`,
      `saw: ${init ? flat(init) : '(no initializer)'} — a literal or expression here ` +
        'silently half-gates the bar while every other assertion passes',
    );
  }
}

const bcType = bcParam ? bcParam.type : null;
let bcProp = null;
if (bcType && ts.isTypeLiteralNode(bcType)) {
  bcProp = bcType.members.find(
    (m) => ts.isPropertySignature(m) && m.name && m.name.getText(src) === 'picksAlwaysCounted',
  );
}
assert(!!bcProp, '14d — BarColumn\'s prop type declares picksAlwaysCounted');
if (bcProp) {
  assert(
    bcProp.questionToken === undefined,
    '14e — BarColumn\'s picksAlwaysCounted prop is REQUIRED (no `?`)',
    'omitting it must be a tsc error, not a silent OFF',
  );
  assert(
    txt(bcProp.type) === 'boolean',
    '14f — BarColumn\'s picksAlwaysCounted prop is typed boolean',
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 15 — the filtered hint gates on the RAW flag, never on picksInView
// ═══════════════════════════════════════════════════════════════════════════
//
// R-8.2 is a casing + ordering fix that must apply whenever the flag is ON,
// INCLUDING when the user has deselected Picks. With filter {WR, RB} tapped
// in that order `picksInView` is false, so a picksInView gate falls through
// to the raw join and prints "WR + RB" where the canonical QB→RB→WR→TE order
// requires "RB + WR". Flag OFF must still print the raw enum in tap order.

assert(!!hintTernary, '15a — the filtered hint expression was found');
if (hintTernary) {
  assert(
    flat(hintTernary.condition) === FLAG_ID,
    `15b — the filtered hint gates on the raw \`${FLAG_ID}\``,
    `saw: ${flat(hintTernary.condition)}`,
  );
  assert(
    flat(hintTernary.whenTrue) === 'filterPosLabel',
    '15c — the filtered hint flag-ON arm is `filterPosLabel`',
    `saw: ${flat(hintTernary.whenTrue)}`,
  );
  assert(
    flat(hintTernary.whenFalse) === "[...posFilter].join(' + ')",
    "15d — the filtered hint flag-OFF arm is exactly `[...posFilter].join(' + ')`",
    `saw: ${flat(hintTernary.whenFalse)}`,
  );
  assert(
    !flat(hintTernary).includes('picksInView'),
    '15e — the filtered hint does NOT reference picksInView',
    'that gate would print tap order whenever Picks is deselected',
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 16 — the ON→OFF reconciliation effect (R-0.4, the kill-switch drill)
// ═══════════════════════════════════════════════════════════════════════════

assert(
  !!reconcileEffect,
  '16a — a useEffect deleting PICKS from posFilter exists',
  'without it, pulling the kill switch mid-session strands an invisible, ' +
    'unremovable PICKS member that silently zeroes the view',
);
if (reconcileEffect) {
  const cb = reconcileEffect.arguments[0];
  const guards = findAll(
    cb,
    (n) => ts.isIfStatement(n) && hasNegation(n.expression, FLAG_ID),
  );
  assert(
    guards.length === 1,
    `16b — the effect body runs only under \`!${FLAG_ID}\``,
    'with the flag ON, PICKS in Starters is the CORRECT state (R-2) — the effect must no-op',
  );
  if (guards.length === 1) {
    const g = flat(guards[0].expression);
    assert(
      g.includes("subset !== 'all'") && g.includes("posFilter.has('PICKS')"),
      '16c — the effect fires only for a stranded PICKS in a non-All subset',
      `saw: ${g}`,
    );
    assert(
      calls(guards[0], 'setPosFilter').length === 1 &&
        flat(guards[0]).includes("delete('PICKS')"),
      '16d — the effect deletes PICKS from posFilter',
    );
  }
  const deps = reconcileEffect.arguments[1];
  assert(
    !!deps &&
      ts.isArrayLiteralExpression(deps) &&
      deps.elements.some((e) => ts.isIdentifier(e) && e.getText(src) === FLAG_ID),
    '16e — the effect re-runs when the flag changes',
    'the whole point is catching a mid-session ON→OFF transition',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All picks-subset-invariance checks passed.');
