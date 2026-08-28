#!/usr/bin/env node
// #402/#403 — "More offers" = shop a player (W1 structural guard).
//
// WHY THIS EXISTS. The operator ruled #402 and #403 one experience
// (docs/feedback/items/402-more-offers-shop/rulings-2026-08-27.md): the deck
// card's give-side "More offers" control opens an inline shop strip below the
// top card instead of the pin + regenerate path. Nearly every failure mode of
// that design is invisible to tsc:
//
//   • the fork could lose its give-side or flag guard (receive side, or a
//     flag-off user, silently loses the shipped pin path — R-1′/R-17);
//   • the flag-off arm could lose the pin/regenerate/#288-snapshot calls it
//     must keep byte-identical;
//   • the strip's pager could be rebuilt on a Gesture.Pan / PanResponder and
//     reopen the deck-pan arbitration the design removed (HLD D-2, R-4);
//   • the deck pan's `.enabled()` could stop referencing the shop-open state
//     (the deck must hold still while the strip is open — R-2′);
//   • SHOP_MODE_GROUP could silently cross tier_up ↔ tier_down — all three
//     values are string literals of one union, so tsc cannot tell them apart
//     (R-3): it is EXECUTED here, not pattern-matched;
//   • the `1 / X` counter could read a different list than the pager renders
//     and lie after a dismiss (R-5);
//   • the ✓ and ✕ could get crossed (both are () => void — dismissing would
//     queue a real offer to a league-mate), or the dismiss could POST
//     immediately and make the "Undo" copy a lie (R-6/R-8/R-9);
//   • TradeCard's give-side label fork could drift from the exact shipped
//     flag-off literal (R-1′);
//   • the strip could mount its own FeedbackFAB (the #196/#197 double-FAB
//     bug — TradesScreen is a tab screen covered by the global mount);
//   • the four client events could go unregistered (props silently dropped
//     behind a 200), or land in NON_INTENT_EVENTS (they are all deliberate
//     taps — lld-delta.md §8).
//
// Structural, not textual where it matters: parses the real TSX with the
// project's own TypeScript and walks the AST (the check-single-pin-actions.js
// pattern), so comments mentioning "Gesture.Pan" don't false-positive and an
// ancestor guard can't be confused with an unrelated mention. shopMode.ts is
// transpiled and RUN (the ideaToCard.ts convention).
//
// Run: node tests/check-shop-deck.js   (or: npm run test:shop-deck)

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

const HOST_REL = 'src/screens/TradesScreen.tsx';
const STRIP_REL = 'src/components/ShopOffersStrip.tsx';
const MODE_REL = 'src/utils/shopMode.ts';
const CARD_REL = 'src/components/TradeCard.tsx';
const TAXONOMY_ABS = path.join(__dirname, '..', '..', 'backend', 'analytics_taxonomy.py');
const QUERIES_ABS = path.join(__dirname, '..', '..', 'backend', 'analytics_queries.py');

const SHOP_EVENTS = [
  'shop_opened',
  'shop_mode_selected',
  'shop_positions_selected',
  'shop_dismiss_undone',
];

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

// ── Parsing helpers (check-single-pin-actions.js pattern) ─────────────────

const _cache = new Map();
function parse(rel) {
  if (_cache.has(rel)) return _cache.get(rel);
  const abs = path.join(__dirname, '..', rel);
  const sf = ts.createSourceFile(
    abs,
    fs.readFileSync(abs, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
  _cache.set(rel, sf);
  return sf;
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

function txt(sf, n) {
  return n ? n.getText(sf) : '';
}

/** Identifiers with exactly this name inside `root` (member names count). */
function referencesIdentifier(sf, root, name) {
  return findAll(sf, (n) => ts.isIdentifier(n) && n.text === name).some(
    (n) => n.getStart(sf) >= root.getStart(sf) && n.getEnd() <= root.getEnd(),
  );
}

function functionNamed(sf, name) {
  return findAll(
    sf,
    (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === name,
  )[0];
}

// ── (a) the handleKeepSide fork ───────────────────────────────────────────

{
  const sf = parse(HOST_REL);
  const fn = functionNamed(sf, 'handleKeepSide');
  assert(!!fn, 'a1: handleKeepSide exists in TradesScreen');
  if (fn) {
    // The fork: an if whose condition tests BOTH the give side and the flag
    // conjunction, and whose branch returns (flag-off falls through).
    const fork = findAll(
      sf,
      (n) =>
        ts.isIfStatement(n) &&
        n.getStart(sf) >= fn.getStart(sf) &&
        n.getEnd() <= fn.getEnd() &&
        /side\s*===\s*'give'/.test(txt(sf, n.expression)) &&
        referencesIdentifier(sf, n.expression, 'shopEnabled'),
    )[0];
    assert(
      !!fork,
      "a2: fork condition tests side === 'give' AND shopEnabled",
      'no if statement in handleKeepSide matches both terms',
    );
    if (fork) {
      assert(
        findAll(sf, ts.isReturnStatement).some(
          (r) => r.getStart(sf) >= fork.getStart(sf) && r.getEnd() <= fork.getEnd(),
        ),
        'a3: the shop branch returns early (flag-off arm untouched below it)',
      );
      assert(
        referencesIdentifier(sf, fork, 'openShopStrip') &&
          referencesIdentifier(sf, fork, 'setShopChooserCard'),
        'a4: the shop branch opens the strip (1 give) or the chooser (several)',
      );
      // The flag-off arm still carries the shipped pin path: every one of
      // these must appear in handleKeepSide but OUTSIDE the shop branch.
      for (const id of [
        'preSinglePinSnapshotRef',
        'setSide',
        'resetDeckForNewTargets',
        'generateMutation',
      ]) {
        const inFn = findAll(
          sf,
          (n) =>
            ts.isIdentifier(n) &&
            n.text === id &&
            n.getStart(sf) >= fn.getStart(sf) &&
            n.getEnd() <= fn.getEnd(),
        );
        const outsideFork = inFn.filter(
          (n) => n.getStart(sf) < fork.getStart(sf) || n.getEnd() > fork.getEnd(),
        );
        assert(
          outsideFork.length > 0,
          `a5: flag-off arm still reaches ${id}`,
          'the shipped pin/regenerate path lost a call',
        );
        assert(
          inFn.length === outsideFork.length,
          `a6: ${id} is not called from inside the shop branch`,
          'the shop branch must not pin, snapshot, or regenerate',
        );
      }
    }
  }
}

// ── (b) no pan machinery in the strip or the mode map (AST, not text) ─────

for (const rel of [STRIP_REL, MODE_REL]) {
  const sf = parse(rel);
  const badImport = findAll(
    sf,
    (n) =>
      ts.isImportDeclaration(n) &&
      /react-native-gesture-handler/.test(txt(sf, n.moduleSpecifier)),
  );
  const panResponder = findAll(sf, (n) => ts.isIdentifier(n) && n.text === 'PanResponder');
  const gesturePan = findAll(
    sf,
    (n) =>
      ts.isPropertyAccessExpression(n) &&
      n.name.text === 'Pan' &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'Gesture',
  );
  assert(
    badImport.length === 0 && panResponder.length === 0 && gesturePan.length === 0,
    `b: ${path.basename(rel)} has no gesture-handler import, no PanResponder, no Gesture.Pan`,
    'the pager must be a plain FlatList (HLD D-2)',
  );
}

// ── (c) the deck pan is gated on the shop-open state ──────────────────────

{
  const sf = parse(HOST_REL);
  const enabledCalls = findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isPropertyAccessExpression(n.expression) &&
      n.expression.name.text === 'enabled' &&
      /Gesture\s*\.\s*Pan\s*\(/.test(txt(sf, n)),
  );
  assert(
    enabledCalls.length > 0 &&
      enabledCalls.every((c) => referencesIdentifier(sf, c.arguments[0], 'shopOpen')),
    "c: the top-card pan chain's .enabled() references shopOpen",
    'the deck must hold still while the strip is open (R-2 prime)',
  );
}

// ── (d) SHOP_MODE_GROUP is executed, not pattern-matched ──────────────────

{
  const abs = path.join(__dirname, '..', MODE_REL);
  const js = ts.transpileModule(fs.readFileSync(abs, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const moduleShim = { exports: {} };
  let runtimeImport = null;
  try {
    new Function('module', 'exports', 'require', js)(
      moduleShim,
      moduleShim.exports,
      (spec) => {
        runtimeImport = spec;
        throw new Error(`shopMode.ts must have zero runtime imports (tried ${spec})`);
      },
    );
  } catch (e) {
    fail('d1: shopMode.ts executes under plain node', e.message);
  }
  assert(
    runtimeImport === null,
    'd2: shopMode.ts has zero runtime imports (type-only imports erase)',
  );
  const g = moduleShim.exports.SHOP_MODE_GROUP;
  assert(
    !!g &&
      g.tier_up === 'upgrade' &&
      g.tier_down === 'downgrade' &&
      g.same_value === 'lateral',
    "d3: SHOP_MODE_GROUP maps tier_up→upgrade, tier_down→downgrade, same_value→lateral",
    g ? JSON.stringify(g) : 'SHOP_MODE_GROUP not exported',
  );
  assert(
    !!g && new Set([g.tier_up, g.tier_down, g.same_value]).size === 3,
    'd4: the three group values are distinct',
  );
}

// ── (e) the 1/X counter and the pager render the SAME list ────────────────

{
  const sf = parse(STRIP_REL);
  // The FlatList's data prop — must be a bare identifier so the counter can
  // be proven to read the very same binding.
  const dataAttr = findAll(
    sf,
    (n) =>
      ts.isJsxAttribute(n) &&
      n.name.getText(sf) === 'data' &&
      n.initializer &&
      ts.isJsxExpression(n.initializer),
  )[0];
  assert(!!dataAttr, 'e1: the pager has a data={…} prop');
  let dataId = null;
  if (dataAttr) {
    const expr = dataAttr.initializer.expression;
    if (expr && ts.isIdentifier(expr)) dataId = expr.text;
    assert(
      !!dataId,
      'e2: the data prop is a bare identifier (auditable single source)',
      `got: ${txt(sf, dataAttr)}`,
    );
  }
  // The counter: a template literal of the shape `${…} / ${X.length}`.
  const counters = findAll(
    sf,
    (n) =>
      ts.isTemplateExpression(n) &&
      /\.length/.test(txt(sf, n)) &&
      / \/ /.test(txt(sf, n)),
  );
  assert(counters.length > 0, 'e3: a `N / X` counter template exists');
  if (dataId && counters.length > 0) {
    const good = counters.some((c) =>
      findAll(sf, (n) => ts.isPropertyAccessExpression(n) && n.name.text === 'length').some(
        (p) =>
          p.getStart(sf) >= c.getStart(sf) &&
          p.getEnd() <= c.getEnd() &&
          ts.isIdentifier(p.expression) &&
          p.expression.text === dataId,
      ),
    );
    assert(
      good,
      `e4: the counter's X is ${dataId}.length — the pager's own data array`,
      'the counter reads a different list than the pager renders (it can lie)',
    );
  }
}

// ── (f) TradeCard's give-side label fork ──────────────────────────────────

{
  const sf = parse(CARD_REL);
  const forks = findAll(
    sf,
    (n) =>
      ts.isConditionalExpression(n) &&
      ts.isStringLiteral(n.whenTrue) &&
      n.whenTrue.text === 'More offers' &&
      ts.isStringLiteral(n.whenFalse) &&
      n.whenFalse.text === 'Keep · more offers',
  );
  assert(
    forks.length === 1,
    "f1: the keep-chip label forks 'More offers' vs exactly 'Keep · more offers'",
    `found ${forks.length} matching conditionals`,
  );
  // The fork must be guarded by BOTH the give side and the host-threaded
  // prop — resolve the condition through the shopFork helper if used.
  if (forks.length === 1) {
    const cond = forks[0].condition;
    let guardText = txt(sf, cond);
    if (referencesIdentifier(sf, cond, 'shopFork')) {
      const helper = findAll(
        sf,
        (n) =>
          ts.isVariableDeclaration(n) &&
          ts.isIdentifier(n.name) &&
          n.name.text === 'shopFork' &&
          n.initializer,
      )[0];
      guardText += helper ? ` ${txt(sf, helper.initializer)}` : '';
    }
    assert(
      /'give'/.test(guardText) && /shopGiveEntry/.test(guardText),
      'f2: the fork is give-side + prop gated (receive side never forks)',
      `guard: ${guardText.replace(/\s+/g, ' ')}`,
    );
  }
  // The shipped literal appears exactly once in the file — as the fork's
  // flag-off arm — so no second, unforked copy can drift.
  const literals = findAll(
    sf,
    (n) => ts.isStringLiteral(n) && n.text === 'Keep · more offers',
  );
  assert(
    literals.length === 1,
    "f3: 'Keep · more offers' appears exactly once (the flag-off arm)",
    `found ${literals.length}`,
  );
}

// ── (g) no FeedbackFAB in the strip (tab screen — #196/#197) ─────────────

{
  const sf = parse(STRIP_REL);
  assert(
    findAll(sf, (n) => ts.isIdentifier(n) && n.text === 'FeedbackFAB').length === 0,
    'g: ShopOffersStrip mounts no FeedbackFAB (global tab mount covers it)',
  );
}

// ── (h) the four client events are registered, and stay INTENT ────────────

{
  const taxonomy = fs.readFileSync(TAXONOMY_ABS, 'utf8');
  const queries = fs.readFileSync(QUERIES_ABS, 'utf8');
  // The ASSIGNMENTS, not the docstring mentions of the same names.
  const allowedStart = taxonomy.indexOf('ALLOWED_CLIENT_EVENTS: frozenset');
  const propsStart = taxonomy.indexOf('CLIENT_EVENT_PROPS: dict');
  for (const ev of SHOP_EVENTS) {
    assert(
      allowedStart >= 0 &&
        propsStart > allowedStart &&
        taxonomy.slice(allowedStart, propsStart).includes(`"${ev}"`),
      `h1: ${ev} is in ALLOWED_CLIENT_EVENTS`,
    );
    assert(
      propsStart >= 0 && taxonomy.slice(propsStart).includes(`"${ev}":`),
      `h2: ${ev} has a CLIENT_EVENT_PROPS row`,
    );
  }
  assert(
    !/shop_/.test(queries),
    'h3: no shop_* event in analytics_queries (all four stay INTENT by default)',
    'NON_INTENT_EVENTS must not name them — each is a deliberate tap',
  );
}

// ── (i) uncrossed ✓/✕, and the dismiss is HELD (the copy stays true) ─────

{
  const sf = parse(STRIP_REL);
  const btnHandler = (tid) => {
    const attr = findAll(
      sf,
      (n) =>
        ts.isJsxAttribute(n) &&
        n.name.getText(sf) === 'testID' &&
        /^["'`{]*/.test(txt(sf, n)) &&
        txt(sf, n).includes(tid),
    )[0];
    if (!attr) return null;
    // The owning JSX element's opening tag.
    let el = attr.parent;
    while (el && !ts.isJsxSelfClosingElement(el) && !ts.isJsxOpeningElement(el)) {
      el = el.parent;
    }
    if (!el) return null;
    const onPress = el.attributes.properties.find(
      (p) => ts.isJsxAttribute(p) && p.name.getText(sf) === 'onPress',
    );
    return onPress ? txt(sf, onPress) : null;
  };
  const like = btnHandler('shop.like-btn');
  const dismiss = btnHandler('shop.dismiss-btn');
  assert(
    !!like && /handleLike/.test(like) && !/handleDismiss/.test(like),
    'i1: shop.like-btn dispatches handleLike',
    like || 'button or onPress not found',
  );
  assert(
    !!dismiss && /handleDismiss/.test(dismiss) && !/handleLike/.test(dismiss),
    'i2: shop.dismiss-btn dispatches handleDismiss (uncrossed)',
    dismiss || 'button or onPress not found',
  );
  const fnLike = functionNamed(sf, 'handleLike');
  assert(
    !!fnLike &&
      referencesIdentifier(sf, fnLike, 'queueCalcTrade') &&
      !referencesIdentifier(sf, fnLike, 'swipeTrade'),
    'i3: the like reaches queueCalcTrade (never swipeTrade)',
  );
  // The real POST lives in commitDismiss, with the literal 'pass'.
  const fnCommit = functionNamed(sf, 'commitDismiss');
  assert(
    !!fnCommit &&
      referencesIdentifier(sf, fnCommit, 'swipeTrade') &&
      findAll(sf, (n) => ts.isStringLiteral(n) && n.text === 'pass').some(
        (n) => n.getStart(sf) >= fnCommit.getStart(sf) && n.getEnd() <= fnCommit.getEnd(),
      ) &&
      !referencesIdentifier(sf, fnCommit, 'queueCalcTrade'),
    "i4: the dismiss commit reaches swipeTrade with decision 'pass'",
  );
  // Held, not sent: handleDismiss arms a setTimeout referencing
  // UNDO_HOLD_MS and never touches the network path directly …
  const fnDismiss = functionNamed(sf, 'handleDismiss');
  assert(
    !!fnDismiss &&
      referencesIdentifier(sf, fnDismiss, 'setTimeout') &&
      referencesIdentifier(sf, fnDismiss, 'UNDO_HOLD_MS') &&
      !referencesIdentifier(sf, fnDismiss, 'swipeTrade') &&
      !referencesIdentifier(sf, fnDismiss, 'commitDismiss'),
    'i5: handleDismiss arms a held timer (UNDO_HOLD_MS) and makes no direct POST',
  );
  // … and the undo is a pure cancel: clearTimeout, no network call at all.
  const fnUndo = functionNamed(sf, 'undoDismiss');
  assert(
    !!fnUndo &&
      referencesIdentifier(sf, fnUndo, 'clearTimeout') &&
      !referencesIdentifier(sf, fnUndo, 'swipeTrade') &&
      !referencesIdentifier(sf, fnUndo, 'commitDismiss') &&
      !referencesIdentifier(sf, fnUndo, 'flushPendingDismiss'),
    'i6: undo cancels the timer — the request is never sent (the copy is true)',
  );
}

// ── verdict ───────────────────────────────────────────────────────────────

if (failures > 0) {
  console.error(`\n${failures} assertion(s) failed.`);
  process.exit(1);
}
console.log('\nAll shop-deck assertions passed.');
