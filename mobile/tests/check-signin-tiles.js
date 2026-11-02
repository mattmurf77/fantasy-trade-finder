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
//   3. PLATFORM_TILE has exactly sleeper / espn / mfl, word for word as
//      marketing-lead's copy §6 addendum 16 (the dim lines and the VoiceOver
//      labels), and no "soon" / "coming" / "unavailable".
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
//   7. The ESPN/MFL panel explainers claim nothing the door can't keep
//      (marketing addendum 16 row 3, 11-02): exactly "… Sign in to ESPN." and
//      "… Sign in to MFL.". No "league ID" (the verified sign-in refuses an ID
//      alone), no "we'll find", and nothing on the screen says "no extra
//      account" (some MFL paths go to Apple).
//   8. The returning-user landing fits an iPhone SE with the tiles: the
//      session-expired notice's marginBottom is space.md - 5 (652 → 647pt).
//   9. The entry sheets a tile opens (EspnLinkSheet / PlatformLinkSheet in
//      entry mode) don't offer "or … league ID" in any wording either (marketing
//      addendum 16, 11-02): the verified sign-in refuses an ID alone. Both
//      clauses were entry-only; Settings' link mode never showed them.
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
const PLATFORM_TILE_LABELS = () => {
  const decl = findAll(sf, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === 'PLATFORM_TILE')[0];
  return Object.fromEntries((decl ? decl.initializer.properties : []).map((p) => [p.name.getText(sf),
    p.initializer.properties.map((q) => (ts.isStringLiteral(q.initializer) ? q.initializer.text : '')).join(' | ')]));
};

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

check('3. PLATFORM_TILE: sleeper, espn and mfl, word for word as marketing\'s addendum 16', () => {
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
  }
  // marketing-lead copy §6 addendum 16 (#570; labels revised 11-02): an SE
  // tile's line fits about 10 characters; VoiceOver has no width limit.
  const FINAL = {
    sleeper: { name: 'Sleeper', line: 'Username', a11y: 'Sleeper, sign in with your username, no password needed' },
    espn: { name: 'ESPN', line: 'Sign in', a11y: 'ESPN, sign in with your ESPN account' },
    mfl: { name: 'MFL', line: 'Sign in', a11y: 'MyFantasyLeague, sign in with your MFL account' },
  };
  for (const [k, v] of entries) {
    expect(same(v, FINAL[k]), `PLATFORM_TILE.${k} is ${JSON.stringify(v)}, want ${JSON.stringify(FINAL[k])}`);
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

check('7. the ESPN/MFL explainers claim only what the door does', () => {
  const ESPN = 'ESPN dynasty leagues are supported. Sign in to ESPN.';
  const MFL = 'MyFantasyLeague dynasty leagues are supported. Sign in to MFL.';
  const panel = findAll(sf, (n) => ts.isJsxOpeningElement(n) && attrText(n, 'testID') === 'signin.platform-panel')[0];
  expect(panel, 'no signin.platform-panel');
  const cond = findAll(panel.parent, (n) => ts.isConditionalExpression(n)
    && n.condition.getText(sf) === "entryPlatform === 'espn'")[0];
  expect(cond && ts.isStringLiteral(cond.whenTrue) && ts.isStringLiteral(cond.whenFalse),
    "the explainer is not `entryPlatform === 'espn' ? '…' : '…'`");
  expect(cond.whenTrue.text === ESPN, `the ESPN explainer is "${cond.whenTrue.text}", want "${ESPN}"`);
  expect(cond.whenFalse.text === MFL, `the MFL explainer is "${cond.whenFalse.text}", want "${MFL}"`);
  const strings = findAll(sf, (n) => ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)).map((n) => n.text);
  expect(!strings.some((t) => /no extra account/i.test(t)), 'a string still says "no extra account"');
  const tiles = Object.values(PLATFORM_TILE_LABELS());
  expect(![cond.whenTrue.text, cond.whenFalse.text, ...tiles].some((t) => /league ID|we(’|')ll find/i.test(t)),
    'an explainer or tile label still offers a league ID or says "we\'ll find"');
});

check('8. the session-expired notice leaves the returning-user landing on one SE screen', () => {
  const n = styleProps('reauthNotice');
  expect(n && n.marginBottom === 'space.md - 5',
    `styles.reauthNotice.marginBottom is ${n && n.marginBottom}, want space.md - 5`);
});

check('9. the entry sheets the tiles open offer no "or … league ID" alternative', () => {
  // Any "or" offering a league ID, reworded or not ("or enter a league ID",
  // "Or use a league ID"; release-lead #570 QA P3-1). Link mode's own labels
  // ("MFL league ID or league URL") put the "or" after the ID, so they pass.
  const OR_ID = /\bor\b[^.\n<>{}'"`]{0,40}\bleague ID\b/i;
  for (const rel of ['src/components/EspnLinkSheet.tsx', 'src/components/PlatformLinkSheet.tsx']) {
    const src = stripComments(fs.readFileSync(path.join(ROOT, rel), 'utf8'));
    const m = src.match(OR_ID);
    expect(!m, `${rel} still offers a league ID as an alternative: "${m && m[0]}"`);
  }
});

console.log(failures === 0
  ? `\nAll sign-in tile checks passed (${passed}).`
  : `\n${failures} sign-in tile check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
