#!/usr/bin/env node
// Anti-divergence test for the pick-anchor rung labels (audit A-16 / P1-7).
//
// WHY THIS EXISTS. The Pick Anchor grid used to carry its OWN label strings,
// authored by hand, next to a `TIER_LABEL` map that says the same eight things
// for the rest of the app. Five of the eight had drifted apart, so a user
// tapped "1 2nd" and read back "2nd" inside a single interaction, and "4 1sts"
// landed in a tier the app calls "4+ 1sts". The fix DERIVES every rung label
// from `TIER_LABEL` through `ANCHOR_TIER`.
//
// A derivation is only permanent if re-typing a string is caught. Without this
// file the next agent "simplifies" one label back to a literal and the bug
// returns with a fresh timestamp — which is precisely how it got here.
//
// A GREP WOULD NOT DO. It passes on a label reconstructed inside a ternary or
// a template literal, which is exactly the regression worth catching. So this
// parses the real TypeScript with the project's own compiler and walks the
// AST, like `check-member-entered-marker.js` and `check-mock-mode-marker.js`.
//
// Five assertions, each independently failing:
//   A-1  No `label` property in anchorRows.ts is a literal of any kind.
//   A-2  ANCHOR_TIER covers the AnchorKey union exactly — no missing, no extra.
//   A-3  Every non-null ANCHOR_TIER value is a real member of TIERS, and
//        `no_value` is null.
//   A-4  BELOW_LADDER_LABEL comes from a TIER_LABEL property access.
//   A-5  Neither host re-implements the null-tier fallback.
//
// Run: node tests/check-anchor-labels.js   (or: npm run test:anchor-labels)

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

function read(rel) {
  return fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');
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

/** The initializer of `export const <name> = …`, or null. */
function exportedConst(root, name) {
  const decl = findAll(
    root,
    (n) =>
      ts.isVariableDeclaration(n) &&
      n.name &&
      ts.isIdentifier(n.name) &&
      n.name.text === name,
  )[0];
  return decl ? decl.initializer || null : null;
}

/** Property name as written, with quotes stripped. */
function propName(p) {
  if (!p.name) return null;
  if (ts.isIdentifier(p.name) || ts.isStringLiteral(p.name)) return p.name.text;
  return p.name.getText().replace(/^['"]|['"]$/g, '');
}

const ROWS_REL = 'src/utils/anchorRows.ts';
const BANDS_REL = 'src/utils/tierBands.ts';
const API_REL = 'src/api/rankings.ts';
const HOSTS = [
  { name: 'PickAnchorScreen', rel: 'src/screens/PickAnchorScreen.tsx' },
  { name: 'AnchorSheet', rel: 'src/components/AnchorSheet.tsx' },
];

const rowsSrc = parse(ROWS_REL);
const rowsText = read(ROWS_REL);

// ═══════════════════════════════════════════════════════════════════════
// A-1 — no rung label is authored as a literal
// ═══════════════════════════════════════════════════════════════════════
//
// Catches the original defect, re-created: someone types `label: '1 2nd'`.
// Template literals and template EXPRESSIONS are rejected too, because
// `label: `${n} 2nd`` is the same divergence wearing a disguise.

const labelProps = findAll(
  rowsSrc,
  (n) => ts.isPropertyAssignment(n) && propName(n) === 'label',
);

assert(
  labelProps.length > 0,
  'A-1 setup: anchorRows.ts still assigns a `label` somewhere',
  'if the shape changed, this whole test needs re-pointing rather than deleting',
);

// Look ANYWHERE inside the initializer, not just at its root. A first cut of
// this test only inspected the top-level node and was defeated in one line by
//     label: key === '1_second' ? '1 2nd' : anchorLabel(key)
// which is the divergence wearing a ternary — the very case that makes an AST
// walk worth writing instead of a grep. Check the whole subtree.
const literalLabels = labelProps.filter(
  (p) =>
    findAll(
      p.initializer,
      (n) =>
        ts.isStringLiteral(n) ||
        ts.isNoSubstitutionTemplateLiteral(n) ||
        ts.isTemplateExpression(n),
    ).length > 0,
);

assert(
  literalLabels.length === 0,
  'A-1: no rung `label` contains an authored string literal, at any depth',
  literalLabels.length
    ? `found ${literalLabels.length}: ${literalLabels
        .map((p) => p.initializer.getText())
        .join(' | ')} — labels must come from anchorLabel()/TIER_LABEL`
    : undefined,
);

// …and the labels that ARE there must BE the derivation, not merely mention
// it. A whitelist of two exact shapes, so anything cleverer has to be
// deliberately added here and therefore reviewed.
const derivedLabels = labelProps.filter((p) => {
  const init = p.initializer;
  if (ts.isIdentifier(init) && init.text === 'label') return true;
  return (
    ts.isCallExpression(init) &&
    ts.isIdentifier(init.expression) &&
    init.expression.text === 'anchorLabel'
  );
});
assert(
  derivedLabels.length === labelProps.length,
  'A-1b: every rung `label` IS a call to anchorLabel() (or the binding it produced)',
  `${labelProps.length - derivedLabels.length} of ${labelProps.length} are some other expression — a new, unreviewed source of truth`,
);

// ═══════════════════════════════════════════════════════════════════════
// A-2 — ANCHOR_TIER covers the AnchorKey union exactly
// ═══════════════════════════════════════════════════════════════════════
//
// A ninth rung, or a renamed key, would fall through `anchorLabel` to
// BELOW_LADDER_LABEL and silently price as FA — a mis-valuation rendered as
// a normal-looking button.

const apiSrc = parse(API_REL);
const anchorKeyDecl = findAll(
  apiSrc,
  (n) => ts.isTypeAliasDeclaration(n) && n.name.text === 'AnchorKey',
)[0];

assert(!!anchorKeyDecl, 'A-2 setup: the AnchorKey union is where expected', API_REL);

let unionKeys = [];
if (anchorKeyDecl && ts.isUnionTypeNode(anchorKeyDecl.type)) {
  unionKeys = anchorKeyDecl.type.types
    .filter((t) => ts.isLiteralTypeNode(t) && ts.isStringLiteral(t.literal))
    .map((t) => t.literal.text);
}
assert(
  unionKeys.length === 8,
  'A-2 setup: AnchorKey is an 8-member string union',
  `found ${unionKeys.length}`,
);

const anchorTierInit = exportedConst(rowsSrc, 'ANCHOR_TIER');
assert(
  !!anchorTierInit && ts.isObjectLiteralExpression(anchorTierInit),
  'A-2 setup: ANCHOR_TIER is an object literal',
);

let tierEntries = [];
if (anchorTierInit && ts.isObjectLiteralExpression(anchorTierInit)) {
  tierEntries = anchorTierInit.properties
    .filter((p) => ts.isPropertyAssignment(p))
    .map((p) => [propName(p), p.initializer]);
}
const tierKeys = tierEntries.map(([k]) => k);

const missing = unionKeys.filter((k) => !tierKeys.includes(k));
const extra = tierKeys.filter((k) => !unionKeys.includes(k));
assert(
  missing.length === 0 && extra.length === 0,
  'A-2: ANCHOR_TIER has exactly the eight AnchorKey members',
  [
    missing.length ? `missing ${missing.join(', ')}` : '',
    extra.length ? `unknown ${extra.join(', ')}` : '',
  ]
    .filter(Boolean)
    .join('; ') || undefined,
);

// ═══════════════════════════════════════════════════════════════════════
// A-3 — every mapped tier is real, and no_value is null
// ═══════════════════════════════════════════════════════════════════════
//
// A typo'd tier key ('first1') survives a loose read and yields `undefined`
// at runtime — a blank button.

const bandsSrc = parse(BANDS_REL);
const tiersInit = exportedConst(bandsSrc, 'TIERS');
let tierNames = [];
if (tiersInit) {
  const arr = ts.isAsExpression(tiersInit) ? tiersInit.expression : tiersInit;
  if (ts.isArrayLiteralExpression(arr)) {
    tierNames = arr.elements
      .filter((e) => ts.isStringLiteral(e))
      .map((e) => e.text);
  }
}
assert(
  tierNames.length === 8,
  'A-3 setup: TIERS lists the eight ladder tiers',
  `found ${tierNames.length}`,
);

const badTiers = tierEntries.filter(([key, init]) => {
  if (key === 'no_value') return false;
  return !(ts.isStringLiteral(init) && tierNames.includes(init.text));
});
assert(
  badTiers.length === 0,
  'A-3: every non-null ANCHOR_TIER value is a member of TIERS',
  badTiers.length
    ? badTiers.map(([k, i]) => `${k} -> ${i.getText()}`).join(', ')
    : undefined,
);

const noValue = tierEntries.find(([k]) => k === 'no_value');
assert(
  !!noValue && noValue[1].kind === ts.SyntaxKind.NullKeyword,
  'A-3b: ANCHOR_TIER.no_value is null',
  'the server pins no_value BELOW every band and answers tier:null — mapping it to `waivers` would assert an equivalence the backend does not make',
);

// ═══════════════════════════════════════════════════════════════════════
// A-4 — BELOW_LADDER_LABEL is borrowed, not typed
// ═══════════════════════════════════════════════════════════════════════
//
// Catches "simplifying" `TIER_LABEL.waivers` to `'FA'`, which re-forks the
// vocabulary while every other assertion here still passes.

assert(
  /import\s*\{[^}]*\bTIER_LABEL\b[^}]*\}\s*from\s*'\.\/tierBands'/.test(rowsText),
  'A-4: anchorRows.ts imports TIER_LABEL from ./tierBands',
);

const belowInit = exportedConst(rowsSrc, 'BELOW_LADDER_LABEL');
assert(
  !!belowInit &&
    ts.isPropertyAccessExpression(belowInit) &&
    belowInit.expression.getText() === 'TIER_LABEL',
  'A-4b: BELOW_LADDER_LABEL is a TIER_LABEL property access',
  belowInit ? `found \`${belowInit.getText()}\`` : 'not exported',
);

// ═══════════════════════════════════════════════════════════════════════
// A-5 — neither host re-implements the null-tier fallback
// ═══════════════════════════════════════════════════════════════════════
//
// The pre-fix bug's exact shape: the wizard's confirmation line said
// "No value" while the button said something else and the Tiers board
// badged the same player "FA".

for (const host of HOSTS) {
  const text = read(host.rel);
  assert(
    !/['"`]No value['"`]/.test(text),
    `A-5 (${host.name}): does not hard-code a "No value" fallback`,
    'the null-tier string is BELOW_LADDER_LABEL, so the rung and its confirmation cannot disagree',
  );
  assert(
    /\bBELOW_LADDER_LABEL\b/.test(text),
    `A-5b (${host.name}): renders BELOW_LADDER_LABEL`,
  );
  assert(
    /import\s*\{[^}]*\bBELOW_LADDER_LABEL\b[^}]*\}\s*from\s*'[^']*anchorRows'/.test(
      text,
    ),
    `A-5c (${host.name}): imports it from the shared module`,
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Sanity: the derivation actually produces the ladder's strings
// ═══════════════════════════════════════════════════════════════════════
//
// The five checks above are structural; this one is the outcome they exist
// to protect. Read TIER_LABEL out of tierBands.ts and confirm the eight rungs
// resolve to it — so a change to the LADDER's vocabulary flows through here
// automatically (which is the point) while a change to the RUNG's mapping
// gets caught.

const labelInit = exportedConst(bandsSrc, 'TIER_LABEL');
const tierLabel = {};
if (labelInit && ts.isObjectLiteralExpression(labelInit)) {
  for (const p of labelInit.properties) {
    if (ts.isPropertyAssignment(p) && ts.isStringLiteral(p.initializer)) {
      tierLabel[propName(p)] = p.initializer.text;
    }
  }
}
assert(
  Object.keys(tierLabel).length === 8,
  'sanity setup: TIER_LABEL has eight entries',
  `found ${Object.keys(tierLabel).length}`,
);

const unresolved = tierEntries.filter(([key, init]) => {
  if (key === 'no_value') return !tierLabel.waivers;
  return !(ts.isStringLiteral(init) && tierLabel[init.text]);
});
assert(
  unresolved.length === 0,
  'sanity: all eight rungs resolve to a TIER_LABEL string',
  unresolved.map(([k]) => k).join(', ') || undefined,
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All anchor-label derivation checks passed.');
