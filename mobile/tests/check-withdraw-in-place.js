#!/usr/bin/env node
// WHY THIS EXISTS (U2 / AC-L5; design-lead #339 §5.4 and U1.7; ux-lead U3
// VoiceOver rules): when the server stops serving a trade the user is looking
// at (I-1 — an asset changed hands — or a disposition), the card must be
// WITHDRAWN IN PLACE: it keeps its slot, says why in one line, and the user
// moves on. And the "Updating" label that shows while a page is rebuilt is
// information only — it must never disable Like or Pass. Failure modes:
//   - the fronted card silently vanishes or is swapped under the thumb;
//   - a withdrawn card keeps its Like/Pass (liking a trade that no longer
//     exists), or loses its slot height (the layout jumps);
//   - someone wires the Updating/freshness state into `dispositionDisabled`
//     or the swipe gesture, freezing the deck on every stale tap;
//   - the label is inserted as a new row ABOVE the card (moves the swipe
//     target mid-gesture).
// What it does: EXECUTES utils/tradePages.mergeDeckPage for the withdraw
// cases and pins the screen + component wiring by source. HONEST LABEL
// (G-035): the merge is executed; the render path is pinned, not rendered
// (TestFlight checklist: the U2 roster-change run).
//
// Run: node tests/check-withdraw-in-place.js   (or: npm run test:withdraw-in-place)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
let ts;
try { ts = require('typescript'); } catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}
const SRC = path.join(__dirname, '..', 'src');
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const stripComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

let failures = 0;
function check(name, cond, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}${detail ? `\n      ${detail}` : ''}`); }
}

const P = (() => {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(read('utils/tradePages.ts'), { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS } }).outputText,
  { module, exports: module.exports, Set, Map, Math });
  return module.exports;
})();
const c = (id, h) => ({ trade_id: id, trade_hash: h });
const code = stripComments(read('screens/TradesScreen.tsx'));
const comp = read('components/TradeDeckStates.tsx');

console.log('check-withdraw-in-place:');

// ── 1. EXECUTED: who is withdrawn, who is dropped ─────────────────────────
{
  const held = [c('seen', 'hs'), c('front', 'hf'), c('b1', 'hb1'), c('b2', 'hb2')];
  const whole = [c('b2x', 'hb2'), c('new', 'hn')]; // the server no longer serves hf or hb1
  const r = P.mergeDeckPage(held, whole, 'hf', true);
  check('1a. a fronted card missing from the whole current deck is flagged for withdrawal', r.withdrawFront === true);
  check('1b. …and KEEPS its slot: same object, same index; the seen card before it untouched',
    r.cards[1] === held[1] && r.cards[0] === held[0]);
  check('1c. behind-cards the server dropped are removed silently; what it serves follows in its order',
    JSON.stringify(r.cards.map((x) => x.trade_id)) === JSON.stringify(['seen', 'front', 'b2x', 'new']));
  const still = P.mergeDeckPage(held, [c('f2', 'hf'), c('b1', 'hb1')], 'hf', true);
  check('1d. a fronted card the server still serves is never withdrawn', still.withdrawFront === false);
  const partial = P.mergeDeckPage(held, [c('x', 'hx')], 'hf', false);
  check('1e. an append page or a rebased first page of a longer deck withdraws nothing',
    partial.withdrawFront === false && partial.cards.length === 5
      && P.isWholeDeck({ status: 'complete', rebased: true, cursor: 30, total_ready: 90 }) === false);
}

// ── 2. The screen withdraws in place ─────────────────────────────────────
{
  check('2a. applyPage records the withdrawn fronted card by its raw trade_id',
    /if \(merged\.withdrawFront && front\) \{\s*setWithdrawnIds\(\(s\) => new Set\(s\)\.add\(front\.trade_id\)\);/.test(code));
  const withdrawnAt = code.indexOf(') : topCard && topCardWithdrawn ? (');
  const topAt = code.indexOf(') : topCard ? (');
  check('2b. the withdrawn branch sits in the card slot, right ahead of the live card branch',
    withdrawnAt > -1 && topAt > withdrawnAt
      && /\) : topCard && topCardWithdrawn \? \(\s*<WithdrawnTradeCard minHeight=\{topCardH\} onNext=\{handleWithdrawnNext\} \/>\s*\) : topCard \? \(/.test(code));
  check('2c. moving on advances the cursor by one, with no disposition',
    /function handleWithdrawnNext\(\) \{\s*haptics\.selection\(\);\s*setDeckIdx\(\(i\) => i \+ 1\);\s*\}/.test(code));
}

// ── 3. The withdrawn card: one reason line, its slot's height, no Like/Pass ─
{
  const sf = ts.createSourceFile('S.tsx', comp, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let fn = '';
  (function visit(n) {
    if (ts.isFunctionDeclaration(n) && n.name?.text === 'WithdrawnTradeCard') fn = n.getText(sf);
    ts.forEachChild(n, visit);
  })(sf);
  check('3a. one chalk-dim reason line (bodySm) with the x icon in chalk-dim — no red, no amber',
    /<Icon name="x" size=\{16\} color=\{chalk\.dim\} \/>/.test(fn)
      && /<Text variant="bodySm" testID="trades\.withdrawn\.reason"/.test(fn)
      && !/semantic|neg|warn|flare/.test(fn));
  check('3b. it keeps the slot height (minHeight = the measured card height)',
    /<Card style=\{minHeight \? \{ minHeight \} : undefined\}>/.test(fn));
  check('3c. no Like or Pass on a trade that no longer exists; one way on: Next trade',
    !/onLike|onPass|disposition|SwipableTopCard/.test(fn) && /label="Next trade"/.test(fn)
      && (fn.match(/<Button\b/g) || []).length === 1);
  check('3d. VoiceOver: focus stays on the card, whose label is the reason',
    /useFocusOnMount\(bodyRef\)/.test(fn) && /accessibilityLabel=\{WITHDRAWN_REASON\}/.test(fn));
}

// ── 4. "Updating" never disables Like or Pass ─────────────────────────────
{
  const dd = code.slice(code.indexOf('dispositionDisabled={'), code.indexOf('declineReasons={declineReasonProps}'));
  check('4a. dispositionDisabled reads nothing about freshness, paging or Updating',
    dd.length > 0 && !/deckUpdating|freshness|pagePhase|pagedDeck|deckEnd/.test(dd));
  const uses = code.match(/\bdeckUpdating\b/g) || [];
  check('4b. deckUpdating is read only to SHOW the label (declaration + header + inline)', uses.length === 4,
    `${uses.length} references — a new reader could be gating something`);
  check('4c. it is derived from the server\'s freshness_state on a paged deck only',
    /const deckUpdating = pagedDeck && job\?\.freshness_state === 'updating';/.test(code));
  check('4d. the label takes no props (it cannot reach the deck\'s controls)',
    /export function DeckUpdatingLabel\(\) \{/.test(comp));
  check('4e. placement never inserts a row above the card: the pushed deck\'s header, else under the card',
    /headerRight: deckUpdating \? \(\) => <DeckUpdatingLabel \/> : undefined/.test(code)
      && /Swipe right to like · Swipe left to pass\s*<\/Text>\s*(\{\s*\}\s*)?\{deckUpdating && !isResultsPushed \? \(/.test(code));
  check('4f. reduced motion: the spinner drops to the static word',
    /\{reduceMotion \? null : <ActivityIndicator/.test(comp) && /<Text variant="bodySm">Updating<\/Text>/.test(comp));
}

console.log(failures ? `check-withdraw-in-place: ${failures} FAILED` : 'check-withdraw-in-place: all passed');
process.exit(failures ? 1 : 0);
