#!/usr/bin/env node
// #312 — the "What are you after?" sheet obeys GIVE-LEFT / GET-RIGHT.
//
// THE RULING (#209/#216, operator): what the user SENDS renders left/first,
// what they GET renders right/second, on every surface that shows both sides
// — the player board's AWAY/FOR columns, the idea rows' give→swap→receive
// order, the featured window, and the clipboard text ("I send:" before
// "I get:", tradeText.ts). The DNA sheet's "Specific players" add-button row
// was the app's one violation (get-left/send-right, authored get-first
// because acquire is the sheet's headline motive); #312 swapped it.
//
// WHAT IS PINNED, and the sabotage each assertion detects:
//
//   1  Inside the `addRow` container, `dna.targets.add-send` PRECEDES
//      `dna.targets.add-get` in source order (RN lays a row out in child
//      order, so source order IS screen order for a plain flex row).
//      Sabotage: swap the two Pressables back → red.
//   2  The chips wrap maps `pinnedGive` (SEND chips) BEFORE `pinnedReceive`
//      (GET chips). This half of the invariant was already correct before
//      #312 — pinning it means the fix of one half can never silently flip
//      the other. Sabotage: reorder the two `.map` blocks → red.
//
// Structural, not textual: parses the real TSX with the project's own
// TypeScript and walks the AST (same harness family as
// check-single-pin-actions.js). Maestro cannot assert left/right order of
// two visible elements, so THIS file is the enforceable artifact for #312
// (the Maestro delta is waived in the scope block; the Tier-1 screen
// capture records the visual).
//
// Run: node tests/check-dna-side-order.js

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

const REL = 'src/components/TradeDnaSheet.tsx';
const abs = path.join(__dirname, '..', REL);
const sf = ts.createSourceFile(
  abs,
  fs.readFileSync(abs, 'utf8'),
  ts.ScriptTarget.ES2019,
  /* setParentNodes */ true,
  ts.ScriptKind.TSX,
);

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

function findAll(pred) {
  const out = [];
  walk(sf, (n) => {
    if (pred(n)) out.push(n);
  });
  return out;
}

const isJsxEl = (n) => ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n);

function stringAttr(el, name) {
  if (!isJsxEl(el)) return null;
  const a = el.attributes.properties.find(
    (p) => ts.isJsxAttribute(p) && p.name.getText(sf) === name,
  );
  const init = a && a.initializer;
  return init && ts.isStringLiteral(init) ? init.text : null;
}

/** The full JsxElement (open+children+close) whose opening tag carries an
 *  attribute expression mentioning `styles.<styleName>`. */
function jsxElementWithStyle(styleName) {
  return findAll(
    (n) =>
      ts.isJsxElement(n) &&
      new RegExp(`styles\\s*\\.\\s*${styleName}\\b`).test(
        n.openingElement.attributes.getText(sf),
      ),
  );
}

function elementWithTestId(id) {
  return findAll((n) => isJsxEl(n) && stringAttr(n, 'testID') === id);
}

function within(node, container) {
  return (
    node.getStart(sf) >= container.getStart(sf) && node.getEnd() <= container.getEnd()
  );
}

// ── 1 — add-send precedes add-get inside the addRow container ──────────────

const addRows = jsxElementWithStyle('addRow');
assert(
  addRows.length === 1,
  `1a — exactly one styles.addRow container in ${REL}`,
  `found ${addRows.length}`,
);

if (addRows.length === 1) {
  const row = addRows[0];
  const send = elementWithTestId('dna.targets.add-send').filter((n) => within(n, row));
  const get = elementWithTestId('dna.targets.add-get').filter((n) => within(n, row));
  assert(
    send.length === 1 && get.length === 1,
    '1b — both add buttons live inside the addRow container',
    `add-send: ${send.length}, add-get: ${get.length}`,
  );
  if (send.length === 1 && get.length === 1) {
    assert(
      send[0].getStart(sf) < get[0].getStart(sf),
      '1c — dna.targets.add-send PRECEDES dna.targets.add-get (give-left/get-right)',
      'the add buttons are get-first again — the exact #312 violation',
    );
  }
}

// ── 2 — chips wrap maps pinnedGive before pinnedReceive ────────────────────
// The chip elements carry a shared dynamic testID (dna.targets.chip.<id>),
// so the anchor is the `.map` CALL on each list inside the chipsWrap.

// `styles.chipsWrap` is shared with the #269 team-target chip; the players
// block is the one whose wrap maps `pinnedGive`.
const mapCallOn = (container, listName) =>
  findAll(
    (n) =>
      ts.isCallExpression(n) &&
      ts.isPropertyAccessExpression(n.expression) &&
      n.expression.name.text === 'map' &&
      new RegExp(`\\b${listName}\\s*$`).test(n.expression.expression.getText(sf)),
  ).filter((n) => within(n, container));

const chipsWraps = jsxElementWithStyle('chipsWrap').filter(
  (w) => mapCallOn(w, 'pinnedGive').length > 0,
);
assert(
  chipsWraps.length === 1,
  `2a — exactly one styles.chipsWrap container mapping pinnedGive in ${REL}`,
  `found ${chipsWraps.length}`,
);

if (chipsWraps.length === 1) {
  const wrap = chipsWraps[0];
  const giveMaps = mapCallOn(wrap, 'pinnedGive');
  const recvMaps = mapCallOn(wrap, 'pinnedReceive');
  assert(
    giveMaps.length === 1 && recvMaps.length === 1,
    '2b — chipsWrap maps pinnedGive and pinnedReceive exactly once each',
    `pinnedGive maps: ${giveMaps.length}, pinnedReceive maps: ${recvMaps.length}`,
  );
  if (giveMaps.length === 1 && recvMaps.length === 1) {
    assert(
      giveMaps[0].getStart(sf) < recvMaps[0].getStart(sf),
      '2c — SEND chips (pinnedGive) render before GET chips (pinnedReceive)',
      'the already-correct chip order flipped during the #312 edit',
    );
  }
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All dna-side-order checks passed.');
