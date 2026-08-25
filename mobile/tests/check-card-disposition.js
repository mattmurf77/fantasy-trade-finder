#!/usr/bin/env node
// Card-disposition placement regression test (#169, card frame C).
//
// WHY THIS EXISTS. The operator moved the deck's Pass/Like buttons from the
// row BELOW the deck to inside the top card, directly beneath the players
// being traded (above "Edit in calculator" / the value bar). The testIDs
// (`trades.pass-btn` / `trades.like-btn`) moved unchanged — which means a
// regression that moves them back, or renders a second copy from the old
// TradesScreen site, would keep every flow green while shipping the layout
// the operator rejected. Exactly one disposition row may ever exist: the
// deck's TOP card, behind TradeCard's `disposition ?` guard — the peek
// card, match variant, and read-only mounts pass no `disposition` prop.
//
// What is pinned:
//   1. TradeCard.tsx renders both button testIDs AFTER the give/receive
//      split closes and BEFORE the TradeValueBar mount (index order on the
//      source text — the "beneath the players, above the value bar" spec).
//   2. TradesScreen.tsx no longer declares either testID (prop wiring and
//      comments are fine; a testID attribute is the regression).
//   3. Both buttons sit inside a `disposition ?` conditional in TradeCard —
//      the guard is what keeps every non-top-card mount row-free.
//
// Run: node tests/check-card-disposition.js
//   (or: npm run test:card-disposition)

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

// ═══════════════════════════════════════════════════════════════════════
// 1. TradeCard.tsx — the row lives beneath the players, above the bar
// ═══════════════════════════════════════════════════════════════════════

const CARD_REL = 'src/components/TradeCard.tsx';
const cardText = read(CARD_REL);

// Index-order anchors, in required source order. `{keepSlot('receive')}`
// is the split section's last child (the JSX call, not the helper's
// definition); `<TradeValueBar` is the value-bar mount.
const splitClose = cardText.indexOf("{keepSlot('receive')}");
const passIdx = cardText.indexOf('testID="trades.pass-btn"');
const likeIdx = cardText.indexOf('testID="trades.like-btn"');
const barIdx = cardText.indexOf('<TradeValueBar');

assert(splitClose !== -1, 'TradeCard: split-section anchor found');
assert(barIdx !== -1, 'TradeCard: TradeValueBar mount found');
assert(passIdx !== -1, 'TradeCard: declares trades.pass-btn');
assert(likeIdx !== -1, 'TradeCard: declares trades.like-btn');
if (splitClose !== -1 && barIdx !== -1 && passIdx !== -1 && likeIdx !== -1) {
  assert(
    splitClose < passIdx && splitClose < likeIdx,
    'TradeCard: disposition buttons render AFTER the give/receive split',
    'the operator placed them directly beneath the players being traded',
  );
  assert(
    passIdx < barIdx && likeIdx < barIdx,
    'TradeCard: disposition buttons render BEFORE the TradeValueBar mount',
    'the value bar keeps its place below the disposition row (#169 decisions)',
  );
}
assert(
  cardText.indexOf('testID="trades.pass-btn"', passIdx + 1) === -1 &&
    cardText.indexOf('testID="trades.like-btn"', likeIdx + 1) === -1,
  'TradeCard: each button testID is declared exactly once',
);

// ═══════════════════════════════════════════════════════════════════════
// 2. TradesScreen.tsx — the old below-deck row is gone
// ═══════════════════════════════════════════════════════════════════════

const screenText = read('src/screens/TradesScreen.tsx');
assert(
  !/testID=\{?["'`]trades\.(pass|like)-btn/.test(screenText),
  'TradesScreen: declares NEITHER disposition testID',
  'a second declaration would render two rows — top card only, via TradeCard',
);

// ═══════════════════════════════════════════════════════════════════════
// 3. TradeCard.tsx — the row is behind the `disposition ?` guard
// ═══════════════════════════════════════════════════════════════════════
//
// Structural, not a grep: a guard that drifted (`variant === 'swipe' ?`,
// or none at all) would render the row on the peek card / match variant.

const cardSrc = parse(CARD_REL);
const guard = findAll(
  cardSrc,
  (n) =>
    ts.isConditionalExpression(n) && n.condition.getText().trim() === 'disposition',
)[0];
assert(!!guard, 'TradeCard: a `disposition ?` conditional exists');
if (guard) {
  const inGuard = guard.whenTrue.getText();
  assert(
    inGuard.includes('testID="trades.pass-btn"') &&
      inGuard.includes('testID="trades.like-btn"'),
    'TradeCard: BOTH buttons render inside the `disposition ?` guard',
    'outside it, mounts that pass no `disposition` prop would grow a row',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 4. TradeCard.tsx — `trades.card-meter` is a TOP-CARD-only registration
// ═══════════════════════════════════════════════════════════════════════
//
// Wave A (v2 note 17, 2026-08-23) retargeted the tour's fairness beat (n22)
// from `trades.fairness-help` — TradesScreen's ⓘ, which renders inside
// `{!firstRun && …}` and so never mounts for the first-run decks the tour
// runs against — onto the top card's own value meter.
//
// The scoping is the whole risk. The deck renders a peek card behind the
// fronted one, plus match / read-only mounts; `disposition` is what marks the
// ONE card the user is deciding, and `registerGuideTarget` is a last-write-
// wins map, so an unscoped registration would ring whichever card mounted
// last. Same property `trades.pass-btn` and `trades.swap-first` already hold —
// asserted structurally here rather than by grep, so a guard that drifted to
// `variant === 'swipe'` or vanished is caught.

const meterEffect = findAll(
  cardSrc,
  (n) =>
    ts.isCallExpression(n) &&
    n.expression.getText() === 'useEffect' &&
    /registerGuideTarget\('trades\.card-meter'/.test(n.getText()),
)[0];
assert(
  !!meterEffect,
  'TradeCard: trades.card-meter is registered from an effect',
  'registering during render leaks a handle on every re-render',
);
if (meterEffect) {
  const body = meterEffect.arguments[0].getText();
  assert(
    /if \(!cardMeterMounted\) return;/.test(body),
    'TradeCard: the meter registration is gated on cardMeterMounted',
    'an ungated registration is claimed by the peek card too',
  );
  assert(
    /unregisterGuideTarget\('trades\.card-meter'\)/.test(body),
    'TradeCard: …and it unregisters on teardown',
    'a stale handle points at an unmounted node for the rest of the session',
  );
}
assert(
  /const cardMeterMounted = !!disposition && hasValueVerdict && !repricing;/.test(cardText),
  'TradeCard: cardMeterMounted means "top card, with the bar actually rendered"',
  'dropping `!!disposition` un-scopes the id; dropping the bar conditions '
    + 'registers a ref that measures null, which is the bug being fixed',
);
// The wrapper has to survive Android view flattening, or the ref measures
// nothing even on the right card.
{
  const at = cardText.indexOf('testID="trades.card-meter"');
  assert(at !== -1, 'TradeCard: the meter wrapper carries its testID');
  if (at !== -1) {
    const window = cardText.slice(Math.max(0, at - 200), at + 100);
    assert(
      /collapsable=\{false\}/.test(window) && /ref=\{cardMeterRef\}/.test(window),
      'TradeCard: the wrapper is a non-collapsable View holding cardMeterRef',
      'a styleless View is flattened away on Android and measures null',
    );
  }
  assert(
    cardText.indexOf('testID="trades.card-meter"', at + 1) === -1,
    'TradeCard: the meter testID is declared exactly once',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All card-disposition placement checks passed.');
