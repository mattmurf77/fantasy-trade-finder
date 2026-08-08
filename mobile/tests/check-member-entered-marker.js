#!/usr/bin/env node
// Provenance regression test (draft-extensions W3 M-C, D17, flag
// `picks.assign_tradeable`).
//
// WHY THIS EXISTS. Under `picks.assign` a LEAGUEMATE types an ESPN league's
// pick ownership in by hand, and under `picks.assign_tradeable` those
// asserted rows enter trade math at full parity with platform-owned picks
// (operator decision 4). ESPN has no draft object, so nothing will ever
// contradict a wrong grid (plan §6.9.3), and the person a bad assignment
// harms is usually not the person who made it (§6.9.1). The operator
// accepted that risk on ONE stated condition — D17, "provenance is
// inescapable": every surface that renders a PRICE for a `source: 'user'`
// pick shows the registered marker and offers the correction in one action.
//
// That is a STRUCTURAL claim about five specific files, so this is a
// structural test: it parses the real TSX with the project's own TypeScript
// and walks the JSX tree, exactly like `check-mock-mode-marker.js`. A grep
// would pass on a marker that had drifted inside a `cond && …` — which is
// precisely the regression worth catching, because a priced assertion whose
// marker got suppressed is indistinguishable on screen from platform truth.
//
// What is pinned, per priced surface:
//   1. The marker is rendered in the SAME row as the price.
//   2. It is UNCONDITIONAL within that row (the component self-gates on the
//      flag and on `source === 'user'`; a host-side conditional can only
//      subtract).
//   3. It is handed all four things it needs to disclose AND to route:
//      `source`, `pickId`, `season`, `leagueId`.
//   4. No surface hard-codes the copy — one string, one module, three
//      clients (docs/cross-client-invariants.md).
//
// Run: node tests/check-member-entered-marker.js
//   (or: npm run test:member-entered-marker)

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

function tagOf(node) {
  if (ts.isJsxSelfClosingElement(node)) return node.tagName.getText();
  if (ts.isJsxElement(node)) return node.openingElement.tagName.getText();
  return null;
}

function findTag(root, tag) {
  return findAll(root, (n) => tagOf(n) === tag);
}

/** True when `node` sits inside a `cond ? … : …`, `cond && …` or `a ?? b`
 *  anywhere between it and `stopAt`. */
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

/** The attribute names on a JSX element, as a Set. */
function propsOf(node) {
  const opening = ts.isJsxSelfClosingElement(node) ? node : node.openingElement;
  const names = new Set();
  for (const a of opening.attributes.properties) {
    if (ts.isJsxAttribute(a) && a.name) names.add(a.name.getText());
  }
  return names;
}

/** The innermost JSX element ancestor of `node` that ALSO contains a
 *  `.toLocaleString(` call — i.e. the ROW that renders this asset's price.
 *  All five surfaces format their price that way. */
function pricedRowAncestor(node) {
  for (let p = node.parent; p; p = p.parent) {
    if (!ts.isJsxElement(p) && !ts.isJsxFragment(p)) continue;
    const prices = findAll(
      p,
      (n) => ts.isCallExpression(n) && n.expression.getText().endsWith('toLocaleString'),
    );
    if (prices.length > 0) return p;
  }
  return null;
}

// ═══════════════════════════════════════════════════════════════════════
// 0. The shared module — one copy string, one predicate, one flag read
// ═══════════════════════════════════════════════════════════════════════

const MARKER_REL = 'src/components/MemberEnteredMarker.tsx';
const markerSrc = parse(MARKER_REL);
const markerText = read(MARKER_REL);

// The exact registered cross-client copy. Written out here on purpose: this
// file is the second witness, so a "harmless" re-word has to be made twice
// and shows up in review as a cross-client contract change.
const COPY = 'Member-entered — not verified with ESPN';

assert(
  markerText.includes(`export const MEMBER_ENTERED_COPY = '${COPY}';`),
  'MEMBER_ENTERED_COPY is the registered cross-client string',
  'docs/cross-client-invariants.md pins this exact sentence for mobile, web and the extension',
);

assert(
  /export function isMemberEntered\([\s\S]*?source === 'user'/.test(markerText),
  'isMemberEntered is THE predicate and tests `source === "user"`',
);
assert(
  /export function usePicksTradeable\(\)[\s\S]*?useFlag\('picks\.assign_tradeable'\)/.test(
    markerText,
  ),
  'usePicksTradeable reads exactly `picks.assign_tradeable`',
);

// The component must refuse to render on BOTH gates. Flag off ⇒ every priced
// surface is byte-identical to the pre-M-C tree; a platform-owned pick is
// never mislabelled as an assertion.
assert(
  /if \(!tradeable \|\| !isMemberEntered\(source\)[\s\S]*?\) return null;/.test(markerText),
  'MemberEnteredMarker self-gates on the flag AND on the provenance',
  'hosts render it unconditionally — the gates have to live here',
);

// The correction is ONE action and carries the whole triple.
const correction = findAll(
  markerSrc,
  (n) => ts.isFunctionDeclaration(n) && n.name && n.name.getText() === 'openPickCorrection',
)[0];
assert(!!correction, 'openPickCorrection exists');
if (correction) {
  const body = correction.getText();
  assert(
    body.includes("navigationRef.navigate('PickAssignment'"),
    'The correction routes to the shipped assignment grid',
  );
  for (const key of ['leagueId', 'season', 'focusPickId']) {
    assert(
      new RegExp(`\\b${key}\\b`).test(body),
      `The correction link carries \`${key}\``,
      'the plan specifies the {leagueId, season, focusPickId} triple',
    );
  }
}

// The marker itself must be the tap target — a label with no fix names a
// problem and hides the answer.
const markerFn = findAll(
  markerSrc,
  (n) => ts.isFunctionDeclaration(n) && n.name && n.name.getText() === 'MemberEnteredMarker',
)[0];
assert(!!markerFn, 'MemberEnteredMarker component found');
if (markerFn) {
  const pressables = findTag(markerFn, 'Pressable');
  assert(
    pressables.length === 1 && propsOf(pressables[0]).has('onPress'),
    'The marker is itself the one-action correction control',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 1. The five priced surfaces (plan §6 M-C / lld §4.5.3)
// ═══════════════════════════════════════════════════════════════════════

const SURFACES = [
  {
    n: 1,
    name: 'trade-away picker',
    rel: 'src/components/PlayerPickerModal.tsx',
  },
  {
    n: 2,
    name: 'swap-suggestions sheet',
    rel: 'src/components/SwapSuggestSheet.tsx',
  },
  {
    n: 3,
    name: 'evener chip',
    rel: 'src/components/EvenerRows.tsx',
  },
  {
    n: 4,
    name: 'calculator pick rows',
    rel: 'src/components/TradeSide.tsx',
  },
  {
    n: 5,
    name: 'power-rankings draft capital',
    rel: 'src/screens/LeagueSummaryScreen.tsx',
  },
];

for (const s of SURFACES) {
  const label = `surface ${s.n}/5 (${s.name})`;
  const src = parse(s.rel);
  const text = read(s.rel);

  // Imported from the ONE module — not re-implemented locally.
  assert(
    /import\s+MemberEnteredMarker[\s\S]{0,160}?from '.*MemberEnteredMarker'/.test(text),
    `${label}: imports the shared MemberEnteredMarker`,
  );

  // Nobody re-types the sentence. Provenance that varies by surface teaches
  // users the marker is decorative.
  assert(
    !text.includes(COPY),
    `${label}: does NOT hard-code the copy string`,
    'it must come from MEMBER_ENTERED_COPY so all three clients say one thing',
  );

  const markers = findTag(src, 'MemberEnteredMarker');
  assert(
    markers.length === 1,
    `${label}: renders exactly one MemberEnteredMarker`,
    `found ${markers.length}`,
  );
  if (markers.length !== 1) continue;
  const marker = markers[0];

  // (1) same row as the price.
  const row = pricedRowAncestor(marker);
  assert(
    !!row,
    `${label}: the marker sits in the row that renders the PRICE`,
    'D17 is scoped to priced surfaces — a marker somewhere else on the screen does not discharge it',
  );

  // (2) unconditional within that row.
  if (row) {
    assert(
      !insideConditional(marker, row),
      `${label}: the marker is UNCONDITIONAL inside the priced row`,
      'a host-side ternary/&& can only suppress it — the flag and provenance gates already live in the component',
    );
  }

  // (3) it can disclose AND route.
  const props = propsOf(marker);
  for (const p of ['source', 'pickId', 'season', 'leagueId']) {
    assert(props.has(p), `${label}: passes \`${p}\` to the marker`);
  }
  assert(props.has('testID'), `${label}: the marker carries a testID`);
}

// ═══════════════════════════════════════════════════════════════════════
// 2. Provenance actually reaches the two CalcPlayer surfaces
// ═══════════════════════════════════════════════════════════════════════
//
// Surfaces 1 and 4 render `CalcPlayer`, not the raw pick payload, so the
// marker is only as honest as the mapping that builds those objects. If the
// In-league calculator ever stops copying `source` off `GET /api/league/
// picks`, both surfaces would silently render an assertion as platform
// truth while every check above still passed.

const calcText = read('src/components/InLeagueCalculator.tsx');
assert(
  /pickSource:\s*p\.source/.test(calcText),
  'InLeagueCalculator copies `source` onto every owned-pick CalcPlayer',
  'without it surfaces 1 and 4 can never mark anything',
);
assert(
  /pickSeason:\s*p\.season/.test(calcText),
  'InLeagueCalculator copies `season` onto every owned-pick CalcPlayer',
);

// ═══════════════════════════════════════════════════════════════════════
// 3. The correction target still accepts the triple
// ═══════════════════════════════════════════════════════════════════════

const navText = read('src/navigation/RootNav.tsx');
assert(
  /PickAssignment:[\s\S]{0,200}?focusPickId\?: string/.test(navText) &&
    /PickAssignment:[\s\S]{0,200}?season\?: number/.test(navText),
  'The PickAssignment route accepts `season` and `focusPickId`',
);
const assignText = read('src/screens/PickAssignmentScreen.tsx');
assert(
  /route\?\.params\?\.focusPickId/.test(assignText),
  'PickAssignmentScreen reads focusPickId (the slot the marker points at)',
);

// ═══════════════════════════════════════════════════════════════════════
// 4. The ESPN Draft Room offers the fix instead of directions
// ═══════════════════════════════════════════════════════════════════════
//
// Operator, 2026-08-08: *"The drafts tab for ESPN leagues tells users to go
// assign draft picks in the league tab. They should just be able to set the
// picks directly from the draft page where that message sits."* Same family
// of failure as an unmarked assertion — a screen that names a problem and
// puts the answer somewhere else. Pinned here because the tempting
// "simplification" is to drop the CTA and let the server's sentence (which
// says "on the League tab") render through the fallback.

const roomText = read('src/screens/DraftRoomScreen.tsx');

assert(
  /onAssignPicks\?\:/.test(roomText),
  'DraftRoomScreen Notice takes an onAssignPicks handler',
);
assert(
  /testID="draft-room\.assign-picks"[\s\S]{0,200}?onPress=\{onAssignPicks\}/.test(roomText),
  'The picks_not_assigned notice carries a CTA that performs the assignment',
  'a notice that only describes where to go is the flow the operator rejected',
);
assert(
  /const goToAssignPicks[\s\S]{0,300}?navigate\?\.\('PickAssignment'/.test(roomText),
  'The CTA pushes the shipped PickAssignment grid from the room itself',
);
assert(
  /cameFromAssignRef\.current = false;[\s\S]{0,200}?invalidateQueries\(\{ queryKey: \['draft-board', leagueId\] \}\)/.test(
    roomText,
  ),
  'Returning from the grid invalidates the board',
  'without it the user lands back on the stale "not assigned" notice they just fixed',
);
assert(
  /testID="draft-room\.assign-progress"[\s\S]{0,300}?onPress=\{goToAssignPicks\}/.test(roomText),
  'The partially-assigned board offers "continue assigning" in place',
  'a half-typed grid renders a real board with rounds missing — that must not be a dead end',
);
assert(
  /useFlag\('picks\.assign'\)/.test(roomText),
  'Both room entry points are gated on `picks.assign`',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All member-entered provenance checks passed.');
