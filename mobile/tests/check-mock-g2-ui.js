#!/usr/bin/env node
// G2 (#322–#327) — mock draft room UI: ticker window, tier chips, 3-across
// grid, team sheet, position filter + pool search.
// Spec: docs/feedback/items/322-mock-draft-room-ui/prd.md §5.2 (T-U1/T-U2)
// + §5.3 (T-S1…T-S10). Unit half transpiles and CALLS the real pure helpers
// (the check-session-rerank idiom); structural half is AST over the real
// TSX with the project's typescript (the check-mock-lifecycle idiom).
//
// Run: node tests/check-mock-g2-ui.js  (or: npm run test:mock-g2-ui)

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
const eq = (name, actual, expected) =>
  assert(
    JSON.stringify(actual) === JSON.stringify(expected),
    name,
    `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
  );

function loadPure(rel, importGuardName) {
  const file = path.join(__dirname, '..', rel);
  const js = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const moduleShim = { exports: {} };
  new Function('module', 'exports', 'require', js)(moduleShim, moduleShim.exports, (name) => {
    throw new Error(
      `${importGuardName} gained a runtime import ("${name}") — it must stay pure ` +
        'so this check can run it under plain node.',
    );
  });
  return moduleShim.exports;
}

// ═══════════════════════════════════════════════════════════════════════════
// T-U1 — tickerWindow: ascending window, growth phase, fixed depth,
// firstNewIndex at every boundary, defensive sort.
// ═══════════════════════════════════════════════════════════════════════════

const { tickerWindow } = loadPure('src/utils/tickerWindow.ts', 'tickerWindow.ts');

const mkPicks = (n) => Array.from({ length: n }, (_, i) => ({ pick_no: i + 1 }));
const nos = (r) => r.rows.map((p) => p.pick_no);

for (const [n, newest, wantRows, wantFNI] of [
  // 0 picks — nothing rendered, boundary degenerate.
  [0, 0, [], 0],
  [0, 2, [], 0],
  // 3 picks (growth phase): exactly min(n, 8) rows, ascending from 1.
  [3, 0, [1, 2, 3], 3], // newest = 0 ⇒ firstNewIndex = rows.length ⇒ no tint
  [3, 2, [1, 2, 3], 1],
  [3, 9, [1, 2, 3], 0], // newest > rows.length ⇒ all tinted
  // 8 picks: the full window, nothing dropped yet.
  [8, 0, [1, 2, 3, 4, 5, 6, 7, 8], 8],
  [8, 2, [1, 2, 3, 4, 5, 6, 7, 8], 6],
  [8, 9, [1, 2, 3, 4, 5, 6, 7, 8], 0],
  // 20 picks (steady state): last 8 ascending — earliest fell off the TOP.
  [20, 0, [13, 14, 15, 16, 17, 18, 19, 20], 8],
  [20, 2, [13, 14, 15, 16, 17, 18, 19, 20], 6],
  [20, 9, [13, 14, 15, 16, 17, 18, 19, 20], 0],
]) {
  const r = tickerWindow(mkPicks(n), 8, newest);
  eq(`T-U1 rows(n=${n}, newest=${newest}) ascending window`, nos(r), wantRows);
  eq(`T-U1 firstNewIndex(n=${n}, newest=${newest})`, r.firstNewIndex, wantFNI);
}

// Deliberately shuffled input ⇒ rows still ascending (the R-1 DEFENSIVE
// sort — `picks[]` order is not pinned server-side). SABOTAGE: drop the
// sort in the helper — this case must go red.
const shuffled = [5, 2, 9, 1, 7, 3, 8, 6, 4].map((pick_no) => ({ pick_no }));
eq('T-U1 shuffled input still ascending (defensive sort)',
  nos(tickerWindow(shuffled, 8, 0)), [2, 3, 4, 5, 6, 7, 8, 9]);
// Negative `newest` never over-tints.
eq('T-U1 negative newest clamps to no tint',
  tickerWindow(mkPicks(5), 8, -3).firstNewIndex, 5);

// ═══════════════════════════════════════════════════════════════════════════
// T-U2 — filterPool: position filter FIRST, then search scoped to the
// subset (operator decision — a QB-only name under an RB filter finds
// nothing). SABOTAGE: compose the search over the full pool instead.
// ═══════════════════════════════════════════════════════════════════════════

const { filterPool } = loadPure('src/utils/mockPool.ts', 'mockPool.ts');

const POOL = [
  { player_id: 'q1', name: 'Caleb Downs', position: 'QB' },
  { player_id: 'r1', name: 'Ashton Jeanty', position: 'RB' },
  { player_id: 'r2', name: 'Omarion Hampton', position: 'RB' },
  { player_id: 'w1', name: 'Luther Burden', position: 'WR' },
  { player_id: 't1', name: 'Colston Loveland', position: 'TE' },
  { player_id: 'k1', name: 'Odd Kicker', position: 'K' }, // outside the four
];
const ids = (rows) => rows.map((r) => r.player_id);

eq('T-U2 RB filter + QB-only name ⇒ empty (search scopes to the subset)',
  ids(filterPool(POOL, 'RB', 'Downs')), []);
eq('T-U2 All + same name ⇒ found',
  ids(filterPool(POOL, 'ALL', 'Downs')), ['q1']);
eq('T-U2 case-insensitive substring',
  ids(filterPool(POOL, 'RB', 'jeAnT')), ['r1']);
eq('T-U2 empty query ⇒ filter subset unchanged',
  ids(filterPool(POOL, 'RB', '')), ['r1', 'r2']);
eq('T-U2 whitespace query ⇒ filter subset unchanged',
  ids(filterPool(POOL, 'WR', '   ')), ['w1']);
eq('T-U2 out-of-four position appears only under All',
  [ids(filterPool(POOL, 'ALL', 'kicker')), ids(filterPool(POOL, 'QB', 'kicker'))],
  [['k1'], []]);

// ═══════════════════════════════════════════════════════════════════════════
// Structural half — AST over the real sources.
// ═══════════════════════════════════════════════════════════════════════════

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
  node.forEachChild((c) => {
    findAll(c, pred, out);
  });
  return out;
}

const screenSrc = parse('src/screens/MockDraftScreen.tsx');
const sheetSrc = parse('src/components/draft/MockTeamSheet.tsx');
const apiSrc = parse('src/api/mockDraft.ts');
const screenText = screenSrc.getText();
const sheetText = sheetSrc.getText();

const fnNamed = (src, name) =>
  findAll(src, (n) => ts.isFunctionDeclaration(n) && n.name?.getText() === name)[0];

const hasTestId = (src, id) =>
  findAll(
    src,
    (n) =>
      ts.isJsxAttribute(n) &&
      n.name.getText() === 'testID' &&
      !!n.initializer &&
      ts.isStringLiteral(n.initializer) &&
      n.initializer.text === id,
  ).length > 0;

// ── T-S1: the ticker renders THROUGH tickerWindow; no reverse, no slice ────
{
  const ticker = fnNamed(screenSrc, 'PickTicker');
  assert(!!ticker, 'T-S1 PickTicker exists');
  if (ticker) {
    const t = ticker.getText();
    assert(/\btickerWindow\s*\(/.test(t), 'T-S1 PickTicker derives rows via tickerWindow(...)');
    assert(/\brows\s*\.map\s*\(/.test(t), 'T-S1 the row map iterates the helper output (rows.map)');
    assert(!t.includes('.reverse('), 'T-S1 no .reverse() in the ticker path');
    assert(!/\.slice\s*\(\s*0\s*,/.test(t), 'T-S1 no slice(0, …) over picks in the ticker path');
  }
}

// ── T-S2: the tint boundary is the helper's firstNewIndex ─────────────────
{
  const ticker = fnNamed(screenSrc, 'PickTicker');
  const t = ticker ? ticker.getText() : '';
  assert(
    /tickerRowNew/.test(t) && /firstNewIndex/.test(t),
    'T-S2 tickerRowNew application references firstNewIndex',
  );
  const newLine = t
    .split('\n')
    .find((l) => l.includes('tickerRowNew'));
  assert(
    !!newLine && newLine.includes('firstNewIndex'),
    'T-S2 the tint predicate keys on firstNewIndex on the same line',
    newLine,
  );
  assert(!/i\s*<\s*newest/.test(screenText), 'T-S2 no inline `i < newest` predicate survives');
}

// ── T-S3: chip tier is pick.tier through TierBadge; never client-derived ──
{
  const badges = findAll(
    screenSrc,
    (n) =>
      (ts.isJsxSelfClosingElement(n) && n.tagName.getText() === 'TierBadge') ||
      (ts.isJsxOpeningElement(n) && n.tagName.getText() === 'TierBadge'),
  );
  assert(badges.length >= 1, 'T-S3 the my-pick chip subtree renders a TierBadge');
  const tierProp = badges.some((b) =>
    b.attributes.properties.some(
      (p) =>
        ts.isJsxAttribute(p) &&
        p.name.getText() === 'tier' &&
        !!p.initializer &&
        /pick\s*\.\s*tier/.test(p.initializer.getText()),
    ),
  );
  assert(tierProp, 'T-S3 TierBadge.tier is a member read of pick.tier (server value)');
  assert(!screenText.includes('tierForElo'), 'T-S3 no tierForElo call in the screen');
  assert(
    !/from\s+['"].*utils\/tierBands['"]/.test(screenText),
    'T-S3 no import from utils/tierBands (tier is never client-derived)',
  );
  const chipRegion = screenText.slice(
    screenText.indexOf('myPickSlots.map'),
    screenText.indexOf('Tap to draft'),
  );
  assert(
    /positionOf\s*\(\s*pick\.position\s*\)/.test(chipRegion),
    'T-S3 the chip meta line renders position through positionOf',
  );
  const mockPick = findAll(
    apiSrc,
    (n) => ts.isInterfaceDeclaration(n) && n.name.getText() === 'MockPick',
  )[0];
  const tierMember = mockPick?.members.find((m) => m.name?.getText() === 'tier');
  assert(!!tierMember, 'T-S3 MockPick declares `tier` in mobile/src/api/mockDraft.ts');
  assert(
    !!tierMember && /Tier\s*\|\s*null/.test(tierMember.type.getText()),
    'T-S3 MockPick.tier is Tier | null (absent/old-server-safe)',
  );
}

// ── T-S4: three-across flexBasis grid; no nested scrollable ───────────────
{
  const chipStyle = screenText.slice(
    screenText.indexOf('myPickChip: {'),
    screenText.indexOf('myPickLabel:'),
  );
  assert(/flexBasis/.test(chipStyle), 'T-S4 myPickChip is a flexBasis three-across construction');
  assert(/minHeight:\s*44/.test(chipStyle), 'T-S4 myPickChip keeps minHeight 44 (vertical rhythm)');
  assert(!screenText.includes('<FlatList'), 'T-S4 no FlatList in the screen (no nested scroll)');
  const scrollViews = (screenText.match(/<ScrollView/g) || []).length;
  eq('T-S4 exactly ONE ScrollView (the screen root — chips wrap, never scroll)', scrollViews, 1);
  assert(!sheetText.includes('<ScrollView') && !sheetText.includes('<FlatList'),
    'T-S4 the team sheet list is a SectionList, no extra scrollable wrappers');
}

// ── T-S5: the team sheet — Modal-based, sibling after the ScrollView ──────
{
  assert(hasTestId(screenSrc, 'mock-draft.view-team'), 'T-S5 mock-draft.view-team exists');
  const clockCard = fnNamed(screenSrc, 'OnTheClockCard');
  assert(
    !!clockCard && clockCard.getText().includes('mock-draft.view-team'),
    'T-S5 the view-team entry lives on the OnTheClockCard subtree',
  );
  assert(hasTestId(sheetSrc, 'mock-draft.team-sheet'), 'T-S5 mock-draft.team-sheet exists on the sheet');
  assert(/<Modal\b/.test(sheetText), 'T-S5 MockTeamSheet is Modal-based (a sheet, never navigation)');
  const closeScroll = screenText.indexOf('</ScrollView>');
  const sheetMount = screenText.indexOf('<MockTeamSheet');
  const safeClose = screenText.indexOf('</SafeAreaView>');
  assert(
    closeScroll !== -1 && sheetMount > closeScroll && sheetMount < safeClose,
    'T-S5 MockTeamSheet mounts as a sibling AFTER the ScrollView, inside the single return',
  );
}

// ── T-S6: the undrafted list renders filterPool output only ───────────────
{
  assert(
    /filterPool\s*\(\s*state\?\.\s*undrafted/.test(screenText) ||
      /filterPool\s*\(\s*state\.undrafted/.test(screenText),
    'T-S6 the render source is filterPool(state.undrafted, …)',
  );
  assert(/visiblePool\.map\s*\(/.test(screenText), 'T-S6 the list iterates the filterPool output');
  assert(
    !/state\.undrafted\.map\s*\(/.test(screenText),
    'T-S6 no direct map over state.undrafted survives',
  );
  assert(
    !/undrafted\s*\.\s*filter\s*\(/.test(screenText),
    'T-S6 the screen applies no inline position/search predicate over the pool',
  );
  assert(
    screenText.includes('mock-draft.pos-filter.${'),
    'T-S6 pos-filter testIDs are constructed (mock-draft.pos-filter.<all|qb|rb|wr|te>)',
  );
  assert(
    screenText.includes("'ALL', ...POOL_POSITIONS"),
    'T-S6 the chip row is All + the canonical four (POOL_POSITIONS)',
  );
  assert(hasTestId(screenSrc, 'mock-draft.pool-search'), 'T-S6 mock-draft.pool-search exists');
}

// ── T-S7: reset-on-turn-advance effect ────────────────────────────────────
{
  const effects = findAll(
    screenSrc,
    (n) =>
      ts.isCallExpression(n) &&
      n.expression.getText() === 'useEffect' &&
      n.arguments.length === 2,
  );
  const reset = effects.find((e) => {
    const deps = e.arguments[1].getText();
    const body = e.arguments[0].getText();
    return (
      /on_the_clock\??\.\s*pick_no/.test(deps) &&
      /setPosFilter\(\s*'ALL'\s*\)/.test(body) &&
      /setPoolQuery\(\s*''\s*\)/.test(body)
    );
  });
  assert(
    !!reset,
    'T-S7 a useEffect keyed on on_the_clock.pick_no resets BOTH the filter and the search',
  );
}

// ── T-S8: the three R-15 events are tracked (operator-approved) ───────────
for (const evt of ['mock_team_sheet_opened', 'mock_pool_filtered', 'mock_pool_searched']) {
  assert(
    new RegExp(`track\\(\\s*\\n?\\s*'${evt}'`).test(screenText),
    `T-S8 the screen tracks '${evt}'`,
  );
}

// ── T-S9: G2's "mine" predicates key on the owner id, never `by` ──────────
// SCOPE (PRD reconciliation B-2): only the predicates G2 adds or changes —
// ticker mine-tint, chip source (myPickSlots), team-sheet logic.
// `sinceUserPick` keeps its `by === 'user'` keying BY DESIGN (R-4) and this
// suite must not flag it.
{
  const ticker = fnNamed(screenSrc, 'PickTicker');
  const mineDecl = ticker
    ? findAll(
        ticker,
        (n) => ts.isVariableDeclaration(n) && n.name.getText() === 'mine',
      )[0]
    : null;
  assert(
    !!mineDecl && /picked_by_user_id/.test(mineDecl.getText()),
    'T-S9 ticker mine-tint keys on picked_by_user_id vs userOwnerId',
  );
  assert(
    !!mineDecl && !/\bby\s*===/.test(mineDecl.getText()),
    'T-S9 ticker mine-tint has no `by ===` comparison',
  );
  const slotsDecl = findAll(
    screenSrc,
    (n) => ts.isVariableDeclaration(n) && n.name.getText() === 'myPickSlots',
  )[0];
  assert(
    !!slotsDecl &&
      /userOwnerId/.test(slotsDecl.getText()) &&
      !/\bby\s*===/.test(slotsDecl.getText()),
    'T-S9 the chip source (myPickSlots) keys on userOwnerId, never `by`',
  );
  assert(
    /resolveUserOwnerId/.test(screenText),
    'T-S9 the owner id resolves through resolveUserOwnerId (settings_echo.user_owner_id first)',
  );
  assert(
    !/\bby\s*===/.test(sheetText) && !/\.by\b\s*==/.test(sheetText),
    'T-S9 the team sheet holds no `by` comparison (my_picks + is_you only)',
  );
  // The R-4 carve-out, pinned in BOTH directions: sinceUserPick keeps its
  // deliberate `by === 'user'` read and the suite does not flag it.
  const sinceDecl = findAll(
    screenSrc,
    (n) => ts.isVariableDeclaration(n) && n.name.getText() === 'sinceUserPick',
  )[0];
  assert(
    !!sinceDecl && /by\s*===\s*'user'/.test(sinceDecl.getText()),
    'T-S9 sinceUserPick keeps its by === \'user\' keying (untouched per R-4)',
  );
}

// ── T-S10: no gesture-capture class imports ───────────────────────────────
for (const [label, text] of [
  ['MockDraftScreen', screenText],
  ['MockTeamSheet', sheetText],
]) {
  assert(!text.includes('PanResponder'), `T-S10 ${label} imports no PanResponder`);
  assert(
    !text.includes('react-native-gesture-handler'),
    `T-S10 ${label} imports no react-native-gesture-handler`,
  );
}

if (failures) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll G2 mock-room-UI checks passed.');
