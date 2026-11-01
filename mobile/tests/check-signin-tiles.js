#!/usr/bin/env node
// The landing's three platform tiles (operator 2026-11-01: "For sign in it
// should have three tiles. Sleeper espn mfl"; design-lead's spec). The chip
// row became equal tiles; what each one does is unchanged.
//
// Pins (SignInScreen.tsx, AST):
//   1. One row, `styles.platformRow` with accessibilityRole "radiogroup",
//      rendered only under `platformPickerShown`, and its only children are
//      `platformChips.map(...)`: a tile exists only for a live platform (the
//      list's flags are pinned by check-landing-platform-options §2 and
//      check-espn-signin-flag), so there's no dead or "coming soon" tile.
//   2. Each tile is a Pressable with testID `signin.platform-${p}`,
//      accessibilityRole "radio", accessibilityState { selected: on },
//      accessibilityLabel tile.a11y, disabled while any sign-in or the demo is
//      busy, and onPress exactly `() => selectEntryPlatform(p)`.
//   3. PLATFORM_TILE has exactly sleeper / espn / mfl, each with a non-empty
//      name, line and a11y label, and no "soon" / "coming" / "unavailable".
//   4. The tile's styles match the spec: flex 1, minHeight 64, ink-1, the
//      lineStrongA11y border, radii.md; selected adds only the ice border;
//      the tick is 3×14 ice at top 8 / right 8; the name is type.title chalk,
//      the line type.bodySm chalk-dim. Ice appears only on the selected
//      border and the tick.
//   5. The tick renders only on the selected tile.
//   6. The ESPN/MFL door mints only through platformEntry.ts, whose every
//      route is POST /api/entry/platform (#430 makes it prove ownership and
//      mint a verified acct_* account). SignInScreen calls no /api/entry
//      route itself.
//
// Run: node tests/check-signin-tiles.js

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

const ROOT = process.env.FTF_MOBILE_TEST_ROOT || path.resolve(__dirname, '..');
const REL = 'src/screens/SignInScreen.tsx';
const text = fs.readFileSync(path.join(ROOT, REL), 'utf8');
const entryApi = fs.readFileSync(path.join(ROOT, 'src/api/platformEntry.ts'), 'utf8');
const sf = ts.createSourceFile(REL, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const stripComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

let failures = 0;
let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`PASS  ${name}`);
  } catch (e) {
    failures += 1;
    console.error(`FAIL  ${name}\n      ${e.message}`);
  }
}
function expect(cond, msg) { if (!cond) throw new Error(msg); }
function findAll(root, pred) {
  const out = [];
  (function walk(n) {
    if (pred(n)) out.push(n);
    ts.forEachChild(n, walk);
  })(root);
  return out;
}
const squash = (s) => s.replace(/\s+/g, ' ').trim();
const tagName = (n) => (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)
  ? n.tagName.getText(sf) : null);
const attr = (el, name) => el.attributes.properties.find(
  (a) => ts.isJsxAttribute(a) && a.name.getText(sf) === name);
const attrText = (el, name) => {
  const a = attr(el, name);
  if (!a || !a.initializer) return null;
  return ts.isStringLiteral(a.initializer) ? a.initializer.text
    : a.initializer.expression ? squash(a.initializer.expression.getText(sf)) : a.initializer.getText(sf);
};
const styleDecl = (name) => findAll(sf, (n) => ts.isPropertyAssignment(n) && n.name.getText(sf) === name
  && ts.isObjectLiteralExpression(n.initializer))[0];
const styleProps = (name) => {
  const d = styleDecl(name);
  return d ? Object.fromEntries(d.initializer.properties
    .map((q) => (ts.isSpreadAssignment(q) ? [`...${q.expression.getText(sf)}`, '']
      : [q.name.getText(sf), ts.isPropertyAssignment(q) ? q.initializer.getText(sf) : '...']))) : null;
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const rows = findAll(sf, (n) => ts.isJsxOpeningElement(n) && tagName(n) === 'View'
  && attrText(n, 'style') === 'styles.platformRow');
const tiles = findAll(sf, (n) => ts.isJsxOpeningElement(n) && tagName(n) === 'Pressable'
  && /^`signin\.platform-\$\{p\}`$/.test(attrText(n, 'testID') || ''));

check('1. one radiogroup row, under platformPickerShown, mapping only platformChips', () => {
  expect(rows.length === 1, `${rows.length} platformRow View(s), want 1`);
  const row = rows[0];
  expect(attrText(row, 'accessibilityRole') === 'radiogroup',
    `the row's accessibilityRole is ${attrText(row, 'accessibilityRole')}, want radiogroup`);
  const cond = findAll(sf, (n) => ts.isConditionalExpression(n)
    && n.whenTrue.pos <= row.pos && row.end <= n.whenTrue.end);
  const inner = cond.sort((a, b) => (b.pos - a.pos))[0];
  expect(inner && inner.condition.getText(sf) === 'platformPickerShown',
    `the row renders under ${inner ? inner.condition.getText(sf) : 'nothing'}, want platformPickerShown`);
  const el = row.parent;
  const kids = el.children.filter((c) => !(ts.isJsxText(c) && !c.text.trim()));
  expect(kids.length === 1 && ts.isJsxExpression(kids[0])
    && /^platformChips\.map\(\(p\) =>/.test(kids[0].expression.getText(sf)),
    `the row's children are ${kids.map((k) => squash(k.getText(sf)).slice(0, 40)).join(' | ')}, want only platformChips.map((p) => …)`);
});

check('2. each tile is a radio with its label, state, testID, busy guard and one handler', () => {
  expect(tiles.length === 1, `${tiles.length} tile Pressable(s), want 1 (inside the map)`);
  const t = tiles[0];
  expect(rows[0] && t.pos > rows[0].pos && t.end < rows[0].parent.end, 'the tile is not inside the row');
  const want = {
    accessibilityRole: 'radio',
    accessibilityLabel: 'tile.a11y',
    accessibilityState: '{ selected: on }',
    disabled: 'busy || demoBusy || appleBusy',
    onPress: '() => selectEntryPlatform(p)',
  };
  for (const [k, v] of Object.entries(want)) {
    expect(attrText(t, k) === v, `the tile's ${k} is ${attrText(t, k)}, want ${v}`);
  }
  expect(/const on = entryPlatform === p;/.test(text) && /const tile = PLATFORM_TILE\[p\];/.test(text),
    '`on` must be entryPlatform === p and `tile` PLATFORM_TILE[p]');
});

check('3. PLATFORM_TILE: sleeper, espn and mfl, each fully worded, nothing "coming soon"', () => {
  const decl = findAll(sf, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === 'PLATFORM_TILE')[0];
  expect(decl && ts.isObjectLiteralExpression(decl.initializer), 'no PLATFORM_TILE object literal');
  const entries = decl.initializer.properties.map((p) => [p.name.getText(sf),
    Object.fromEntries(p.initializer.properties.map((q) => [q.name.getText(sf),
      ts.isStringLiteral(q.initializer) ? q.initializer.text : null]))]);
  expect(same(entries.map(([k]) => k), ['sleeper', 'espn', 'mfl']),
    `PLATFORM_TILE keys are ${entries.map(([k]) => k)}, want sleeper, espn, mfl`);
  for (const [k, v] of entries) {
    expect(same(Object.keys(v), ['name', 'line', 'a11y']) && Object.values(v).every((s) => s && s.trim()),
      `PLATFORM_TILE.${k} is ${JSON.stringify(v)}, want non-empty name, line and a11y strings`);
    expect(!/soon|coming|unavailable|not available/i.test(Object.values(v).join(' ')),
      `PLATFORM_TILE.${k} promises a later platform: ${JSON.stringify(v)}`);
    expect(v.a11y.startsWith(v.name + ','), `PLATFORM_TILE.${k}.a11y should start with its name: ${v.a11y}`);
  }
});

check('4. tile styles follow the spec; ice only on the selected border and the tick', () => {
  const want = {
    platformTile: {
      flex: '1', minHeight: '64', paddingVertical: '10', paddingHorizontal: 'space.md',
      justifyContent: "'center'", gap: '2', backgroundColor: 'ink.ink1', borderWidth: '1',
      borderColor: 'ink.lineStrongA11y', borderRadius: 'radii.md',
    },
    platformTileOn: { borderColor: 'ice.base' },
    platformTilePressed: { backgroundColor: 'ink.ink3' },
    platformTileTick: {
      position: "'absolute'", top: '8', right: '8', width: '3', height: '14', backgroundColor: 'ice.base',
    },
    platformTileName: { '...type.title': '', color: 'chalk.base' },
    platformTileLine: { '...type.bodySm': '', color: 'chalk.dim' },
  };
  for (const [name, props] of Object.entries(want)) {
    expect(same(styleProps(name), props), `styles.${name} is ${JSON.stringify(styleProps(name))}, want ${JSON.stringify(props)}`);
  }
  const t = tiles[0];
  const el = t.parent;
  const iceStyles = new Set(findAll(el, (n) => ts.isPropertyAccessExpression(n)
    && n.expression.getText(sf) === 'styles').map((n) => n.name.getText(sf))
    .filter((s) => Object.values(styleProps(s) || {}).some((v) => /\bice\./.test(v))));
  expect(same([...iceStyles].sort(), ['platformTileOn', 'platformTileTick']),
    `ice-bearing styles in the tile: ${[...iceStyles].sort()}, want platformTileOn and platformTileTick`);
  expect(!/\bice\./.test(stripComments(el.getText(sf))), 'the tile markup names an ice token directly');
  expect(/on && styles\.platformTileOn/.test(attrText(t, 'style') || ''), 'the ice border is not tied to `on`');
});

check('5. the tick renders only on the selected tile', () => {
  const ticks = findAll(sf, (n) => (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n))
    && attrText(n, 'style') === 'styles.platformTileTick');
  expect(ticks.length === 1, `${ticks.length} tick element(s), want 1`);
  const cond = findAll(sf, (n) => ts.isConditionalExpression(n)
    && n.whenTrue.pos <= ticks[0].pos && ticks[0].end <= n.whenTrue.end)
    .sort((a, b) => b.pos - a.pos)[0];
  expect(cond && cond.condition.getText(sf) === 'on' && cond.whenFalse.getText(sf) === 'null',
    `the tick renders under ${cond ? cond.condition.getText(sf) : 'nothing'}, want \`on ? … : null\``);
});

check('6. the ESPN/MFL door mints only through POST /api/entry/platform', () => {
  const routes = [...stripComments(entryApi).matchAll(/['`](\/api\/[^'`]+)['`]/g)].map((m) => m[1]);
  expect(routes.length > 0 && routes.every((r) => r === '/api/entry/platform'),
    `platformEntry.ts calls ${[...new Set(routes)].join(', ')}, want only /api/entry/platform`);
  expect(!/\/api\/entry/.test(stripComments(text)), 'SignInScreen calls an /api/entry route itself');
});

console.log(failures === 0
  ? `\nAll sign-in tile checks passed (${passed}).`
  : `\n${failures} sign-in tile check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
