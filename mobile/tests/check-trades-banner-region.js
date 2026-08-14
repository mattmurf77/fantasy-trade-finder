#!/usr/bin/env node
// #314 + #315 — the "change" banner region on the guided TradesHome.
//
// #314 (verbatim: "More [Move] the team and player filters below the
// 'change' banner"): the TradingWithStrip (League / "Trading with" pills —
// the on-page team-scope filters) moves BELOW OutlookBiasReceipt (the
// "Leaning … Change" banner) and OUT of the measured `modeBarWrap`. The
// planned third "Players" pill is HELD for an operator decision — the strip
// still renders exactly two pills, and assertion 4 pins their wiring
// uncrossed (the seam for the third pill is documented in
// TradingWithStrip.tsx).
//
// #315 (verbatim: "the banner can spill to two rows to present those other
// configurations"): OutlookBiasReceipt gains an optional host-composed
// `details` second row.
//
// WHAT IS PINNED, and the sabotage each assertion detects:
//
//   1  In TradesScreen.tsx, the TradingWithStrip element is NOT a
//      descendant of the `modeBarWrap` View, and its source position is
//      AFTER OutlookBiasReceipt's mount (source order is render order in
//      the same ScrollView). Sabotage: move the strip back above the
//      banner → red.
//   2  OutlookBiasReceipt receives a `details` prop at its mount.
//      Sabotage: drop the prop — row 2 silently never renders on any
//      deck; red.
//   3  In OutlookBiasReceipt.tsx, the `trades.outlook-receipt.details`
//      element is gated by an enclosing conditional referencing the
//      `details` value. Sabotage: render it unconditionally → an empty
//      second row on every deck; red.
//   4  In TradingWithStrip.tsx, the strip renders exactly its two pills
//      (league + team — the Players pill is held), and each pill
//      dispatches ITS OWN callback: league → onOpenLeaguePicker, team →
//      onOpenTeamPicker, uncrossed. Sabotage: cross the handlers — the
//      "Trading with" pill opens the league picker; red.
//
// Structural, not textual: parses the real TSX with the project's own
// TypeScript and walks the AST (same harness family as
// check-single-pin-actions.js). Maestro cannot assert the vertical order
// of two visible elements, so assertion 1 is the enforceable artifact for
// the #314 move; the flow trades-banner-region.yaml covers the #315
// details row end-to-end.
//
// Run: node tests/check-trades-banner-region.js

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

function parse(rel) {
  const abs = path.join(__dirname, '..', rel);
  return ts.createSourceFile(
    abs,
    fs.readFileSync(abs, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
}

let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

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

function tagged(sf, tagName) {
  return findAll(sf, (n) => isJsxEl(n) && n.tagName.getText(sf) === tagName);
}

function referencesIdentifier(sf, root, name) {
  return findAll(sf, (n) => ts.isIdentifier(n) && n.text === name).some(
    (n) => n.getStart(sf) >= root.getStart(sf) && n.getEnd() <= root.getEnd(),
  );
}

// ═══ 1 — the strip sits below the banner, outside modeBarWrap ══════════════

const host = parse('src/screens/TradesScreen.tsx');

const strips = tagged(host, 'TradingWithStrip');
const receipts = tagged(host, 'OutlookBiasReceipt');
assert(
  strips.length === 1 && receipts.length === 1,
  '1a — host mounts exactly one TradingWithStrip and one OutlookBiasReceipt',
  `strips: ${strips.length}, receipts: ${receipts.length}`,
);

if (strips.length === 1 && receipts.length === 1) {
  const strip = strips[0];
  const receipt = receipts[0];

  // The measured wrapper: the full JsxElement styled `styles.modeBarWrap`.
  const wraps = findAll(
    host,
    (n) =>
      ts.isJsxElement(n) &&
      /styles\s*\.\s*modeBarWrap\b/.test(n.openingElement.attributes.getText(host)),
  );
  assert(
    wraps.length === 1,
    '1b — exactly one styles.modeBarWrap container',
    `found ${wraps.length}`,
  );
  if (wraps.length === 1) {
    const inWrap =
      strip.getStart(host) >= wraps[0].getStart(host) &&
      strip.getEnd() <= wraps[0].getEnd();
    assert(
      !inWrap,
      '1c — TradingWithStrip is NOT a descendant of modeBarWrap',
      'the strip moved back inside the measured mode-bar wrapper (pre-#314 layout)',
    );
  }
  assert(
    strip.getStart(host) > receipt.getStart(host),
    "1d — TradingWithStrip renders AFTER OutlookBiasReceipt (filters below the banner)",
    'the strip is above the banner again — the exact #314 complaint',
  );
}

// ═══ 2 — the receipt mount carries the details prop ════════════════════════

if (receipts.length === 1) {
  assert(
    !!attr(host, receipts[0], 'details'),
    '2 — OutlookBiasReceipt receives a `details` prop at the mount',
    'no details prop — the #315 second row can never render',
  );
}

// ═══ 3 — the details row is gated on the details value ═════════════════════

const receiptSf = parse('src/components/OutlookBiasReceipt.tsx');
const detailEls = findAll(
  receiptSf,
  (n) => isJsxEl(n) && stringAttr(receiptSf, n, 'testID') === 'trades.outlook-receipt.details',
);
assert(
  detailEls.length === 1,
  '3a — trades.outlook-receipt.details exists in OutlookBiasReceipt.tsx',
  `found ${detailEls.length}`,
);
if (detailEls.length === 1) {
  // Walk up from the element looking for an enclosing conditional
  // (ternary or &&) whose condition references `details`.
  let gated = false;
  let cur = detailEls[0].parent;
  while (cur) {
    if (ts.isConditionalExpression(cur) &&
        referencesIdentifier(receiptSf, cur.condition, 'details')) {
      gated = true;
      break;
    }
    if (
      ts.isBinaryExpression(cur) &&
      cur.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken &&
      referencesIdentifier(receiptSf, cur.left, 'details')
    ) {
      gated = true;
      break;
    }
    cur = cur.parent;
  }
  assert(
    gated,
    '3b — the details row is inside a conditional referencing `details`',
    'rendered unconditionally — an empty second row on every deck',
  );
}

// ═══ 4 — the strip: two pills, handlers uncrossed ══════════════════════════

const stripSf = parse('src/components/TradingWithStrip.tsx');
const pills = findAll(
  stripSf,
  (n) => {
    if (!isJsxEl(n)) return false;
    const id = stringAttr(stripSf, n, 'testID');
    return !!id && id.startsWith('trades.trading-with-strip.');
  },
);
assert(
  pills.length === 2 &&
    pills.some((p) => stringAttr(stripSf, p, 'testID') === 'trades.trading-with-strip.league') &&
    pills.some((p) => stringAttr(stripSf, p, 'testID') === 'trades.trading-with-strip.team'),
  '4a — the strip renders exactly its two pills (league + team; Players pill HELD)',
  `pills: ${pills.map((p) => stringAttr(stripSf, p, 'testID')).join(', ')}`,
);

const PILLS = [
  { id: 'trades.trading-with-strip.league', cb: 'onOpenLeaguePicker', other: 'onOpenTeamPicker' },
  { id: 'trades.trading-with-strip.team', cb: 'onOpenTeamPicker', other: 'onOpenLeaguePicker' },
];
for (const { id, cb, other } of PILLS) {
  const el = pills.find((p) => stringAttr(stripSf, p, 'testID') === id);
  if (!el) continue; // 4a already failed
  const onPress = attr(stripSf, el, 'onPress');
  const init = onPress && onPress.initializer;
  const own = !!init && referencesIdentifier(stripSf, init, cb);
  const crossed = !!init && referencesIdentifier(stripSf, init, other);
  assert(
    own && !crossed,
    `4b — ${id} dispatches \`${cb}\` and not \`${other}\``,
    init ? `saw: onPress=${init.getText(stripSf).replace(/\s+/g, ' ')}` : 'no onPress',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All trades-banner-region checks passed.');
