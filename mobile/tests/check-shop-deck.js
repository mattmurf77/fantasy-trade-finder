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
//     taps — lld-delta.md §8);
//   • (W2, section j) the Same-value position chips could leak into the tier
//     modes (a filter the server never applies there — R-11), offer PICK
//     (the server 400s it — R-12) or DROP the pin's own position (ruling
//     R-2026-08-28-B inverted the original exclusion: the own-position chip
//     IS offered so "WR laterals plus RB laterals" is expressible; empty
//     selection still means same-position swaps), send `swap_positions` on
//     an empty selection (breaking the byte-identical wire state), leak the
//     selected SET into `shop_positions_selected` (count only — lld §8),
//     drop the Clear-positions escape from the filtered empty state, or
//     bypass the held-dismiss flush on a selection change;
//   • (QA round 1, sections k–m) the deck could hold still for the PAN only
//     while the #169 buttons / VoiceOver actions / decline-reason tiles /
//     bad-trade flag still disposition the card under an open strip (B-1);
//     the shop state could survive a deck wipe (resetDeckForNewTargets), a
//     pin clear's snapshot restore, a top-card change, or the
//     `trade.shop_asset` kill switch, or leak internal strip state across
//     assets without the asset-keyed remount (B-2 + Reviewer A's
//     stale-selection trap); an EARLY commit of the held dismiss could
//     leave the "Dismissed · Undo" toast on screen with a dead Undo button
//     (B-4 — the retract-by-reference contract).
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

// ── (h4) P-3 (rulings 2026-08-28) — shop_opened has exactly ONE emitter ──
// The rule: an event fires once, where the thing it names happens. The one
// place a strip opens is openShopStrip, so the one emit lives there —
// direct 1-asset entry emits once, a chooser pick emits once (at pick
// time, with the picked asset's position), a chooser Cancel emits nothing.
// Round 1 had TWO emitters (the handleKeepSide fork + the chooser's
// onPick), which double-fired chooser entries and phantom-fired Cancels.

{
  const trackCallsFor = (sf, eventName) =>
    findAll(
      sf,
      (n) =>
        ts.isCallExpression(n) &&
        ts.isIdentifier(n.expression) &&
        n.expression.text === 'track' &&
        n.arguments.length > 0 &&
        ts.isStringLiteral(n.arguments[0]) &&
        n.arguments[0].text === eventName,
    );

  const host = parse(HOST_REL);
  const emits = trackCallsFor(host, 'shop_opened');
  assert(
    emits.length === 1,
    'h4a: shop_opened is emitted from exactly ONE call site in TradesScreen',
    `found ${emits.length} emitter(s) — the round-1 double-emit is back`,
  );
  const fnOpen = functionNamed(host, 'openShopStrip');
  assert(
    emits.length === 1 &&
      !!fnOpen &&
      emits[0].getStart(host) >= fnOpen.getStart(host) &&
      emits[0].getEnd() <= fnOpen.getEnd(),
    'h4b: the one emitter sits inside openShopStrip (the single strip-open path)',
    'the emit must live where the strip actually opens, not in an entry fork',
  );
  // Neither entry re-emits: handleKeepSide and the chooser onPick reach the
  // event only THROUGH openShopStrip.
  const fnKeep = functionNamed(host, 'handleKeepSide');
  assert(
    !!fnKeep &&
      !findAll(
        host,
        (n) =>
          ts.isStringLiteral(n) &&
          n.text === 'shop_opened' &&
          n.getStart(host) >= fnKeep.getStart(host) &&
          n.getEnd() <= fnKeep.getEnd(),
      ).length,
    'h4c: handleKeepSide carries no shop_opened emit of its own',
  );
  const strip = parse(STRIP_REL);
  assert(
    trackCallsFor(strip, 'shop_opened').length === 0,
    'h4d: the strip/chooser file emits no shop_opened (the host path owns it)',
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

// ── (j) W2 — position multi-select in the Same-value pane ────────────────
// R-10/R-11/R-12 client half: chips render ONLY in same_value mode; the
// domain excludes PICK (server 400s it) and the pin's own position ("leave
// all clear" = same-position swaps); an empty selection OMITS swap_positions
// from the request body (byte-identical wire state); the analytics event
// carries a count, never the set; the filtered empty state offers the
// Clear-positions escape; and a selection change flushes the held dismiss.

const API_REL = 'src/api/trades.ts';

// The (i) helper, re-scoped: testID attr → owning element's onPress text.
function jsxHandler(sf, tid) {
  const attr = findAll(
    sf,
    (n) =>
      ts.isJsxAttribute(n) &&
      n.name.getText(sf) === 'testID' &&
      txt(sf, n).includes(tid),
  )[0];
  if (!attr) return null;
  let el = attr.parent;
  while (el && !ts.isJsxSelfClosingElement(el) && !ts.isJsxOpeningElement(el)) {
    el = el.parent;
  }
  if (!el) return null;
  const onPress = el.attributes.properties.find(
    (p) => ts.isJsxAttribute(p) && p.name.getText(sf) === 'onPress',
  );
  return onPress ? txt(sf, onPress) : null;
}

function nearestAncestor(node, pred) {
  let cur = node.parent;
  while (cur) {
    if (pred(cur)) return cur;
    cur = cur.parent;
  }
  return null;
}

function unwrapAs(n) {
  while (n && (ts.isAsExpression(n) || ts.isParenthesizedExpression(n))) {
    n = n.expression;
  }
  return n;
}

// j0 — the API layer: fetchAssetIdeas takes an OPTIONAL swap_positions.
{
  const sf = parse(API_REL);
  const fn = functionNamed(sf, 'fetchAssetIdeas');
  assert(!!fn, 'j0a: fetchAssetIdeas exists in api/trades.ts');
  if (fn) {
    const sig = findAll(
      sf,
      (n) =>
        ts.isPropertySignature(n) &&
        n.name.getText(sf) === 'swap_positions' &&
        n.getStart(sf) >= fn.getStart(sf) &&
        n.getEnd() <= fn.getEnd(),
    )[0];
    assert(
      !!sig && !!sig.questionToken,
      'j0b: fetchAssetIdeas body type has swap_positions?: (optional)',
      sig ? 'present but REQUIRED — every W1 caller would have to send it' : 'missing',
    );
  }
}

{
  const sf = parse(STRIP_REL);

  // j1 — the picker mounts ONLY inside a same_value guard.
  const pickerAttr = findAll(
    sf,
    (n) =>
      ts.isJsxAttribute(n) &&
      n.name.getText(sf) === 'testID' &&
      txt(sf, n).includes('shop.picker'),
  )[0];
  assert(!!pickerAttr, 'j1a: the picker container (shop.picker) exists');
  let pickerGuard = null;
  if (pickerAttr) {
    pickerGuard = nearestAncestor(
      pickerAttr,
      (n) =>
        ts.isConditionalExpression(n) &&
        /mode\s*===\s*'same_value'/.test(txt(sf, n.condition)),
    );
    assert(
      !!pickerGuard,
      "j1b: the picker is guarded by mode === 'same_value' (chips never render in tier modes)",
      'no enclosing conditional tests same_value',
    );
  }

  // j2 — the chip domain: exactly {QB,RB,WR,TE}, minus the pin's position.
  const domainDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'SWAP_POSITIONS' &&
      n.initializer,
  )[0];
  const domainArr = domainDecl ? unwrapAs(domainDecl.initializer) : null;
  const domain =
    domainArr && ts.isArrayLiteralExpression(domainArr)
      ? domainArr.elements.filter(ts.isStringLiteral).map((e) => e.text)
      : null;
  assert(
    !!domain &&
      domain.length === 4 &&
      ['QB', 'RB', 'WR', 'TE'].every((p) => domain.includes(p)),
    'j2a: SWAP_POSITIONS is exactly {QB,RB,WR,TE}',
    domain ? domain.join(',') : 'SWAP_POSITIONS array not found',
  );
  assert(
    findAll(sf, (n) => ts.isStringLiteral(n) && n.text === 'PICK').length === 0,
    "j2b: no 'PICK' string literal anywhere in the strip (server 400s it — R-12)",
  );
  const offeredDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'offeredPositions' &&
      n.initializer,
  )[0];
  // INVERTED 2026-08-28 (ruling R-2026-08-28-B, "Offer it"): this assertion
  // used to PIN the own-position exclusion; it now pins the INCLUSION. The
  // only legal filter over the domain is the #360 avoided-set — a pinPos
  // term in the filter would silently re-remove the ruled-in chip.
  assert(
    !!offeredDecl &&
      referencesIdentifier(sf, offeredDecl.initializer, 'SWAP_POSITIONS') &&
      referencesIdentifier(sf, offeredDecl.initializer, 'avoided') &&
      !referencesIdentifier(sf, offeredDecl.initializer, 'pinPos'),
    "j2c: offeredPositions offers the pin's OWN position (filters only by avoided — ruling R-2026-08-28-B)",
    'the own-position chip must render; only #360 avoided positions are omitted',
  );
  const pinDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'pinPos' &&
      n.initializer,
  )[0];
  assert(
    !!pinDecl && /asset\s*\.\s*position/.test(txt(sf, pinDecl.initializer)),
    "j2d: pinPos reads asset.position (the shopped player's real position)",
  );
  assert(
    !!pickerGuard && referencesIdentifier(sf, pickerGuard, 'offeredPositions'),
    'j2e: the picker renders offeredPositions (the filtered domain, not the raw one)',
  );
  // The shop.pos testID template exists exactly once — inside SwapPosChip —
  // so no second, unfiltered chip row can exist.
  const posTids = findAll(
    sf,
    (n) => ts.isTemplateExpression(n) && txt(sf, n).includes('shop.pos.'),
  );
  const chipFn = functionNamed(sf, 'SwapPosChip');
  assert(
    posTids.length === 1 &&
      !!chipFn &&
      posTids[0].getStart(sf) >= chipFn.getStart(sf) &&
      posTids[0].getEnd() <= chipFn.getEnd(),
    'j2f: shop.pos.<POS> is minted exactly once, inside SwapPosChip',
    `found ${posTids.length} template(s)`,
  );

  // j3 — an empty selection OMITS the field from the request body.
  const swapProps = findAll(
    sf,
    (n) =>
      (ts.isPropertyAssignment(n) || ts.isShorthandPropertyAssignment(n)) &&
      n.name.getText(sf) === 'swap_positions',
  );
  assert(
    swapProps.length === 1,
    'j3a: swap_positions is assigned in exactly one place in the strip',
    `found ${swapProps.length}`,
  );
  if (swapProps.length === 1) {
    const cond = nearestAncestor(swapProps[0], ts.isConditionalExpression);
    const whenFalse = cond ? unwrapAs(cond.whenFalse) : null;
    assert(
      !!cond &&
        !!whenFalse &&
        ts.isObjectLiteralExpression(whenFalse) &&
        whenFalse.properties.length === 0,
      'j3b: the assignment sits in a conditional whose false arm is {} (key OMITTED, not undefined/[])',
      cond ? `false arm: ${txt(sf, cond.whenFalse)}` : 'no enclosing conditional',
    );
    assert(
      !!cond && referencesIdentifier(sf, cond.condition, 'debouncedSwapKey'),
      'j3c: the guard is the SETTLED selection (debouncedSwapKey), so the wire state tracks what settled',
    );
    assert(
      !!cond && !!nearestAncestor(cond, ts.isSpreadAssignment),
      'j3d: the conditional is spread into the body (no swap_positions key survives the empty arm)',
    );
  }

  // j4 — shop_positions_selected carries a COUNT (n), never the set.
  const posTracks = findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'track' &&
      n.arguments.length > 0 &&
      ts.isStringLiteral(n.arguments[0]) &&
      n.arguments[0].text === 'shop_positions_selected',
  );
  assert(
    posTracks.length === 1,
    'j4a: shop_positions_selected is emitted from exactly one call site',
    `found ${posTracks.length}`,
  );
  if (posTracks.length === 1) {
    const props = posTracks[0].arguments[1];
    const isObj = props && ts.isObjectLiteralExpression(props);
    assert(
      isObj &&
        props.properties.length === 1 &&
        !props.properties.some(ts.isSpreadAssignment) &&
        props.properties[0].name &&
        props.properties[0].name.getText(sf) === 'n',
      'j4b: the props object is exactly { n } — count only, no set, no spread',
      isObj ? txt(sf, props) : 'second arg is not an object literal',
    );
    // Resolve what n IS: shorthand → its local declaration; assignment →
    // the initializer. Either way it must be a count (.length/.size), so a
    // saboteur passing the selection itself (a string/array) is caught.
    let countExpr = null;
    const prop = isObj ? props.properties[0] : null;
    if (prop && ts.isShorthandPropertyAssignment(prop)) {
      const enclosing = nearestAncestor(
        posTracks[0],
        (x) =>
          ts.isArrowFunction(x) || ts.isFunctionDeclaration(x) || ts.isFunctionExpression(x),
      );
      const decl =
        enclosing &&
        findAll(
          sf,
          (x) =>
            ts.isVariableDeclaration(x) &&
            ts.isIdentifier(x.name) &&
            x.name.text === 'n' &&
            x.getStart(sf) >= enclosing.getStart(sf) &&
            x.getEnd() <= enclosing.getEnd(),
        )[0];
      countExpr = decl && decl.initializer ? txt(sf, decl.initializer) : null;
    } else if (prop && ts.isPropertyAssignment(prop)) {
      countExpr = txt(sf, prop.initializer);
    }
    assert(
      !!countExpr && /\.(length|size)\b/.test(countExpr),
      'j4c: n is a count (.length/.size), never the selection itself',
      countExpr || 'could not resolve what n is bound to',
    );
  }

  // j5 — the filtered empty state's Clear-positions escape.
  const clearPress = jsxHandler(sf, 'shop.clear-positions');
  assert(
    !!clearPress && /clearPositions/.test(clearPress),
    'j5a: shop.clear-positions exists and dispatches clearPositions',
    clearPress || 'button or onPress not found',
  );
  const fnClear = functionNamed(sf, 'clearPositions');
  assert(
    !!fnClear &&
      referencesIdentifier(sf, fnClear, 'setPositions') &&
      /new Set\(\)/.test(txt(sf, fnClear)),
    'j5b: clearPositions resets the selection to empty (back to shipped same-position laterals)',
  );
  assert(
    !!fnClear && referencesIdentifier(sf, fnClear, 'flushPendingDismiss'),
    'j5c: clearPositions flushes the held dismiss (its refetch is a payload change — R-9)',
  );

  // j6 — a selection change goes through the dismiss-flush contract.
  const fnToggle = functionNamed(sf, 'handleTogglePosition');
  assert(
    !!fnToggle &&
      referencesIdentifier(sf, fnToggle, 'flushPendingDismiss') &&
      referencesIdentifier(sf, fnToggle, 'setPositions'),
    'j6: handleTogglePosition flushes the held dismiss before mutating the selection',
  );
}

// ── (k) QA B-1 — the deck holds still through ALL disposition paths ──────
// The pan gate (section c) was never the whole story: the #169 in-card
// Pass/Like row, the VoiceOver custom actions, the decline-reason layer-1
// tiles and the bad-trade flag can all disposition the fronted card too.
// Every one of them must reference the shop-open state.

{
  const sf = parse(HOST_REL);

  // The JSX attribute named `name`, asserted unique, returned whole.
  const soleJsxAttr = (name) => {
    const attrs = findAll(
      sf,
      (n) => ts.isJsxAttribute(n) && n.name.getText(sf) === name,
    );
    return attrs.length === 1 ? attrs[0] : null;
  };

  const dispAttr = soleJsxAttr('dispositionDisabled');
  assert(
    !!dispAttr && referencesIdentifier(sf, dispAttr, 'shopOpen'),
    'k1: the dispositionDisabled expression references shopOpen (#169 row inert while shopping)',
    dispAttr ? 'attribute found but no shopOpen term' : 'expected exactly one dispositionDisabled attribute',
  );

  const actionsAttr = soleJsxAttr('accessibilityActions');
  assert(
    !!actionsAttr && referencesIdentifier(sf, actionsAttr, 'shopOpen'),
    'k2: the VoiceOver custom-action LIST is gated on shopOpen (delisted while shopping)',
    actionsAttr ? 'attribute found but no shopOpen term' : 'expected exactly one accessibilityActions attribute',
  );

  const handlerAttr = soleJsxAttr('onAccessibilityAction');
  assert(
    !!handlerAttr && referencesIdentifier(sf, handlerAttr, 'shopOpen'),
    'k3: the VoiceOver action HANDLER is gated on shopOpen (a11y path matches the sighted path)',
    handlerAttr ? 'attribute found but no shopOpen term' : 'expected exactly one onAccessibilityAction attribute',
  );

  // An if whose condition references `id` and whose branch returns, inside fn.
  const guardedReturn = (fn, id) =>
    !!fn &&
    findAll(
      sf,
      (n) =>
        ts.isIfStatement(n) &&
        n.getStart(sf) >= fn.getStart(sf) &&
        n.getEnd() <= fn.getEnd() &&
        referencesIdentifier(sf, n.expression, id) &&
        findAll(sf, ts.isReturnStatement).some(
          (r) => r.getStart(sf) >= n.getStart(sf) && r.getEnd() <= n.getEnd(),
        ),
    ).length > 0;

  assert(
    guardedReturn(functionNamed(sf, 'handleReasonLayer1'), 'shopOpen'),
    'k4: handleReasonLayer1 early-returns on shopOpen (layer-1 tile banks a pass — a disposition)',
    'no shopOpen-guarded return in handleReasonLayer1',
  );

  // The bad-trade flag button: its Pressable's disabled prop must carry
  // shopOpen (flagging advances the deck like a pass).
  const flagPress = findAll(
    sf,
    (n) =>
      ts.isJsxAttribute(n) &&
      n.name.getText(sf) === 'onPress' &&
      txt(sf, n).includes('handleFlagBadTrade'),
  )[0];
  let flagDisabled = null;
  if (flagPress) {
    let el = flagPress.parent;
    while (el && !ts.isJsxSelfClosingElement(el) && !ts.isJsxOpeningElement(el)) {
      el = el.parent;
    }
    flagDisabled =
      el &&
      el.attributes.properties.find(
        (p) => ts.isJsxAttribute(p) && p.name.getText(sf) === 'disabled',
      );
  }
  assert(
    !!flagDisabled && referencesIdentifier(sf, flagDisabled, 'shopOpen'),
    'k5: the bad-trade flag button is disabled while shopping (it advances the deck like a pass)',
    flagDisabled ? 'disabled prop found but no shopOpen term' : 'flag button or its disabled prop not found',
  );
}

// ── (l) QA B-2 — the shop state dies with its context ────────────────────

{
  const sf = parse(HOST_REL);

  for (const fnName of ['resetDeckForNewTargets', 'handleClearPin']) {
    const fn = functionNamed(sf, fnName);
    assert(
      !!fn &&
        referencesIdentifier(sf, fn, 'setShopAsset') &&
        referencesIdentifier(sf, fn, 'setShopChooserCard'),
      `l1: ${fnName} clears the shop state (strip AND chooser)`,
      fn ? 'function found but a setShop* call is missing' : `${fnName} not found`,
    );
  }

  // The strip mount: guarded by shopEnabled (kill switch closes an open
  // strip) and keyed on the shopped asset (remount = full internal reset;
  // the old instance's unmount cleanup flushes its held dismiss).
  const stripEl = findAll(
    sf,
    (n) =>
      (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
      n.tagName.getText(sf) === 'ShopOffersStrip',
  )[0];
  assert(!!stripEl, 'l2a: TradesScreen mounts ShopOffersStrip');
  if (stripEl) {
    const guard = nearestAncestor(
      stripEl,
      (n) =>
        ts.isConditionalExpression(n) &&
        referencesIdentifier(sf, n.condition, 'shopAsset'),
    );
    assert(
      !!guard && referencesIdentifier(sf, guard.condition, 'shopEnabled'),
      'l2b: the strip mount condition references shopEnabled (kill switch closes an open strip)',
      guard ? `guard: ${txt(sf, guard.condition).replace(/\s+/g, ' ')}` : 'no enclosing conditional tests shopAsset',
    );
    const keyAttr = stripEl.attributes.properties.find(
      (p) => ts.isJsxAttribute(p) && p.name.getText(sf) === 'key',
    );
    assert(
      !!keyAttr && referencesIdentifier(sf, keyAttr, 'shopAsset'),
      'l2c: the strip mount is keyed on the shopped asset (internal state resets per asset)',
      keyAttr ? `key: ${txt(sf, keyAttr)}` : 'no key attribute on the mount',
    );
  }

  // The catch-all: a useEffect keyed on the raw top-card id clears both
  // shop-state slots, so any path that changes or removes the fronted card
  // (undo rewind, swipe-error rewind, lane filter, a deck wipe that skips
  // resetDeckForNewTargets) closes the strip instead of stranding it.
  const closeEffect = findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'useEffect' &&
      n.arguments.length === 2 &&
      referencesIdentifier(sf, n.arguments[0], 'setShopAsset') &&
      referencesIdentifier(sf, n.arguments[0], 'setShopChooserCard') &&
      referencesIdentifier(sf, n.arguments[1], 'topRawId'),
  );
  assert(
    closeEffect.length === 1,
    'l3: a topRawId-keyed effect closes the shop when the fronted card changes or leaves',
    `found ${closeEffect.length} matching effects`,
  );
}

// ── (m) QA B-4 — an early commit retracts the Undo toast ─────────────────
// The held dismiss's "Dismissed · Undo" toast must never outlive the undo
// window as a dead button: every early flush retracts it BY REFERENCE (a
// newer toast that already replaced it is left alone), and only the natural
// UNDO_HOLD_MS expiry — whose toast dismisses itself — skips the retract.

{
  const sf = parse(STRIP_REL);

  const propsSig = findAll(
    sf,
    (n) => ts.isPropertySignature(n) && n.name.getText(sf) === 'onToastRetract',
  );
  assert(
    propsSig.length === 1 && !propsSig[0].questionToken,
    'm1: the strip contract has a REQUIRED onToastRetract prop',
    propsSig.length ? 'present but optional' : 'missing from Props',
  );

  const fnFlush = functionNamed(sf, 'flushPendingDismiss');
  const retractIf =
    fnFlush &&
    findAll(
      sf,
      (n) =>
        ts.isIfStatement(n) &&
        n.getStart(sf) >= fnFlush.getStart(sf) &&
        n.getEnd() <= fnFlush.getEnd() &&
        /expired/.test(txt(sf, n.expression)) &&
        referencesIdentifier(sf, n.expression, 'undoToastRef') &&
        referencesIdentifier(sf, n, 'onToastRetract'),
    )[0];
  assert(
    !!retractIf,
    'm2: flushPendingDismiss retracts the undo toast on every non-expired flush',
    'no if in flushPendingDismiss gating onToastRetract on the expired opt + undoToastRef',
  );

  // The natural expiry is the ONE caller that passes expired: true.
  const fnDismiss = functionNamed(sf, 'handleDismiss');
  const expiredArgs = findAll(
    sf,
    (n) =>
      ts.isPropertyAssignment(n) &&
      n.name.getText(sf) === 'expired' &&
      n.initializer.kind === ts.SyntaxKind.TrueKeyword,
  );
  const inTimer =
    expiredArgs.length === 1 &&
    !!nearestAncestor(
      expiredArgs[0],
      (n) =>
        ts.isCallExpression(n) &&
        ts.isIdentifier(n.expression) &&
        n.expression.text === 'setTimeout',
    );
  assert(
    expiredArgs.length === 1 &&
      !!fnDismiss &&
      expiredArgs[0].getStart(sf) >= fnDismiss.getStart(sf) &&
      expiredArgs[0].getEnd() <= fnDismiss.getEnd() &&
      inTimer,
    'm3: exactly one flush passes expired: true — the UNDO_HOLD_MS timer in handleDismiss',
    `found ${expiredArgs.length} expired: true site(s)${
      expiredArgs.length === 1 && !inTimer ? ' (not inside a setTimeout)' : ''
    }`,
  );
  assert(
    !!fnDismiss && referencesIdentifier(sf, fnDismiss, 'undoToastRef'),
    'm4a: handleDismiss stores the undo-toast descriptor it hands the host',
  );
  const fnUndo = functionNamed(sf, 'undoDismiss');
  assert(
    !!fnUndo && referencesIdentifier(sf, fnUndo, 'undoToastRef'),
    'm4b: undoDismiss drops the descriptor (the toast dismissed itself — nothing to retract later)',
  );

  // Host half: the mount wires onToastRetract into the toast slot with the
  // reference-equality guard (retract only OUR toast; never a newer one).
  const host = parse(HOST_REL);
  const retractAttr = findAll(
    host,
    (n) => ts.isJsxAttribute(n) && n.name.getText(host) === 'onToastRetract',
  );
  assert(
    retractAttr.length === 1 &&
      referencesIdentifier(host, retractAttr[0], 'setToast') &&
      /===/.test(txt(host, retractAttr[0])),
    'm5: the host retracts by reference (setToast keeps any newer toast in the slot)',
    retractAttr.length ? `attr: ${txt(host, retractAttr[0]).replace(/\s+/g, ' ')}` : 'onToastRetract not passed at the mount',
  );
}

// ── (n) QA round 2 (rulings 2026-08-28) — the three universal rules ──────
// R-A/Fix A: a COMMITTED dismissal is client-authoritative for the strip
// session (one suppression set, added to only at commit, never cleared by
// data ticks — B-3 + P-2). R-C/P-1: the pager position derives from the
// rendered data — scrolls react to data changes, never race them.
// R-C/P-4: the entry is gated on every flag its actions require.

{
  const sf = parse(STRIP_REL);

  // n1 (P-4) — shopEnabled is the FULL conjunction: the feature key, the
  // data route's flag, and the ✓'s queue-route flag.
  const host = parse(HOST_REL);
  const shopEnabledDecl = findAll(
    host,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'shopEnabled' &&
      n.initializer,
  )[0];
  assert(
    !!shopEnabledDecl &&
      ['shopAssetOn', 'assetIdeasOn', 'calcMergedOn'].every((id) =>
        referencesIdentifier(host, shopEnabledDecl.initializer, id),
      ),
    'n1a: shopEnabled = shopAssetOn && assetIdeasOn && calcMergedOn (the full prerequisite chain — P-4)',
    shopEnabledDecl
      ? `initializer: ${txt(host, shopEnabledDecl.initializer)}`
      : 'shopEnabled declaration not found',
  );
  const mergedDecl = findAll(
    host,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'calcMergedOn' &&
      n.initializer &&
      /useFlag\(\s*'calc\.merged_layout'\s*\)/.test(txt(host, n.initializer)),
  );
  assert(
    mergedDecl.length === 1,
    "n1b: calcMergedOn reads useFlag('calc.merged_layout')",
    `found ${mergedDecl.length} matching declarations`,
  );

  // n2 (Fix A) — the suppression set: commit-only additions, no data-tick
  // clears, filtered everywhere counts are derived.
  const suppDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isArrayBindingPattern(n.name) &&
      /suppressed/.test(txt(sf, n.name)) &&
      /setSuppressed/.test(txt(sf, n.name)) &&
      n.initializer &&
      /useState/.test(txt(sf, n.initializer)),
  );
  assert(
    suppDecl.length === 1,
    'n2a: a [suppressed, setSuppressed] useState pair exists in the strip',
    `found ${suppDecl.length}`,
  );
  const fnCommit2 = functionNamed(sf, 'commitDismiss');
  const fnDismiss2 = functionNamed(sf, 'handleDismiss');
  const fnUndo2 = functionNamed(sf, 'undoDismiss');
  assert(
    !!fnCommit2 && referencesIdentifier(sf, fnCommit2, 'setSuppressed'),
    'n2b: commitDismiss is the gate into the suppression set (commit ⇒ suppressed)',
  );
  assert(
    !!fnDismiss2 &&
      !referencesIdentifier(sf, fnDismiss2, 'setSuppressed') &&
      !!fnUndo2 &&
      !referencesIdentifier(sf, fnUndo2, 'setSuppressed'),
    'n2c: neither handleDismiss nor undoDismiss touches the suppression set (pending never enters; an undone key never entered)',
  );
  // No useEffect keyed on ideasUpdatedAt may clear either removal set —
  // the round-1 dataUpdatedAt reset is exactly the B-3/P-2 defect.
  const updatedAtEffects = findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'useEffect' &&
      n.arguments.length === 2 &&
      referencesIdentifier(sf, n.arguments[1], 'ideasUpdatedAt'),
  );
  assert(
    updatedAtEffects.length > 0 &&
      updatedAtEffects.every(
        (e) =>
          !referencesIdentifier(sf, e.arguments[0], 'setSuppressed') &&
          !referencesIdentifier(sf, e.arguments[0], 'setLocallyRemoved'),
      ),
    'n2d: no ideasUpdatedAt-keyed effect clears the removal or suppression sets (a data tick can never resurrect a committed dismiss)',
    updatedAtEffects.length === 0
      ? 'no ideasUpdatedAt-keyed effect found'
      : 'an effect keyed on ideasUpdatedAt writes a removal set — the B-3 reset is back',
  );
  const visDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'visibleByMode' &&
      n.initializer,
  )[0];
  assert(
    !!visDecl &&
      referencesIdentifier(sf, visDecl.initializer, 'suppressed') &&
      referencesIdentifier(sf, visDecl.initializer, 'locallyRemoved'),
    'n2e: visibleByMode filters through BOTH sets (pager, counter, and chip counts all agree)',
  );
  const baseDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'baselineLateralCount' &&
      n.initializer,
  )[0];
  assert(
    !!baseDecl &&
      referencesIdentifier(sf, baseDecl.initializer, 'suppressed') &&
      referencesIdentifier(sf, baseDecl.initializer, 'locallyRemoved'),
    'n2f: baselineLateralCount runs the same filter (the Clear-positions label never counts a dismissed tile)',
  );

  // n3 (P-1) — one reactive scroll: scrollToOffset exists exactly once,
  // inside a useEffect whose deps derive from the rendered data; the
  // movers only REQUEST an index.
  const scrolls = findAll(
    sf,
    (n) => ts.isIdentifier(n) && n.text === 'scrollToOffset',
  );
  const scrollEffect = findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'useEffect' &&
      n.arguments.length === 2 &&
      referencesIdentifier(sf, n.arguments[1], 'visibleIdeas') &&
      referencesIdentifier(sf, n.arguments[0], 'scrollToOffset'),
  )[0];
  assert(
    scrolls.length === 1 &&
      !!scrollEffect &&
      scrolls[0].getStart(sf) >= scrollEffect.getStart(sf) &&
      scrolls[0].getEnd() <= scrollEffect.getEnd(),
    'n3a: scrollToOffset is called exactly once — inside the visibleIdeas-keyed effect (scrolls react to data, never race it)',
    `found ${scrolls.length} scrollToOffset reference(s)${scrollEffect ? '' : '; no qualifying effect'}`,
  );
  for (const [fn, name] of [
    [fnUndo2, 'undoDismiss'],
    [fnDismiss2, 'handleDismiss'],
    [functionNamed(sf, 'handleSelectMode'), 'handleSelectMode'],
  ]) {
    assert(
      !!fn && referencesIdentifier(sf, fn, 'requestPagerScroll'),
      `n3b: ${name} moves the pager only by REQUESTING an index (requestPagerScroll)`,
    );
  }

  // n4 (reviewer A pin) — Chalkline scan over the strip: no emoji in
  // rendered copy, no gradient/blur, every corner radius ≤ 8 (ADR-004 —
  // no specced pill exists on this surface, so radii.pill is illegal too).
  const emojiRe = /\p{Extended_Pictographic}/u;
  const renderedText = [];
  walk(sf, (n) => {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) {
      renderedText.push(n.text);
    } else if (ts.isTemplateExpression(n)) {
      renderedText.push(n.head.text);
      for (const s of n.templateSpans) renderedText.push(s.literal.text);
    } else if (n.kind === ts.SyntaxKind.JsxText) {
      renderedText.push(n.getText(sf));
    }
  });
  const emojiHits = renderedText.filter((t) => emojiRe.test(t));
  assert(
    emojiHits.length === 0,
    'n4a: no emoji anywhere in the strip strings/copy (Chalkline: never emoji as icons)',
    emojiHits.slice(0, 3).join(' | '),
  );
  const gradientIds = findAll(
    sf,
    (n) => ts.isIdentifier(n) && /gradient/i.test(n.text),
  );
  const blurProps = findAll(
    sf,
    (n) =>
      (ts.isPropertyAssignment(n) || ts.isJsxAttribute(n)) &&
      /blur/i.test(n.name.getText(sf)),
  );
  assert(
    gradientIds.length === 0 && blurProps.length === 0,
    'n4b: no gradient identifiers and no blur props (Chalkline: no gradients, no glassmorphism)',
    `${gradientIds.length} gradient id(s), ${blurProps.length} blur prop(s)`,
  );
  const CORNER = /^border(TopLeft|TopRight|BottomLeft|BottomRight)?Radius$/;
  const radiiTheme = fs.readFileSync(
    path.join(__dirname, '..', 'src/theme/chalkline.ts'),
    'utf8',
  );
  const radiiBlock = /export const radii = \{([^}]*)\}/.exec(radiiTheme);
  const radiiVals = {};
  if (radiiBlock) {
    for (const m of radiiBlock[1].matchAll(/(\w+):\s*(\d+)/g)) {
      radiiVals[m[1]] = Number(m[2]);
    }
  }
  const badRadii = [];
  walk(sf, (n) => {
    if (!ts.isPropertyAssignment(n) || !CORNER.test(n.name.getText(sf))) return;
    const init = unwrapAs(n.initializer);
    if (ts.isNumericLiteral(init)) {
      if (Number(init.text) > 8) badRadii.push(txt(sf, n));
    } else if (
      ts.isPropertyAccessExpression(init) &&
      ts.isIdentifier(init.expression) &&
      init.expression.text === 'radii'
    ) {
      const v = radiiVals[init.name.text];
      if (!(typeof v === 'number' && v <= 8)) badRadii.push(txt(sf, n));
    } else {
      badRadii.push(txt(sf, n)); // unresolvable radius — must be auditable
    }
  });
  assert(
    Object.keys(radiiVals).length > 0 && badRadii.length === 0,
    'n4c: every corner radius in the strip resolves to ≤ 8 (Chalkline radius rule; no pill on this surface)',
    badRadii.join(' | ') || 'could not resolve radii tokens from the theme',
  );

  // n5 (reviewer A pin) — label sources: the two tier labels READ the
  // shipped TRADE_INTENT_LABEL constant (the DNA sheet and the strip can
  // never diverge), and each mode label exists exactly once — 'Same value'
  // as the one new literal, the tier labels never re-hardcoded.
  const modeLabelDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'MODE_LABEL' &&
      n.initializer,
  )[0];
  const modeLabelObj =
    modeLabelDecl && unwrapAs(modeLabelDecl.initializer);
  const labelProps =
    modeLabelObj && ts.isObjectLiteralExpression(modeLabelObj)
      ? modeLabelObj.properties.filter(ts.isPropertyAssignment)
      : [];
  const labelFor = (key) =>
    labelProps.find((p) => p.name.getText(sf) === key);
  const readsIntentLabel = (key) => {
    const p = labelFor(key);
    if (!p) return false;
    const init = unwrapAs(p.initializer);
    return (
      ts.isPropertyAccessExpression(init) &&
      ts.isIdentifier(init.expression) &&
      init.expression.text === 'TRADE_INTENT_LABEL' &&
      init.name.text === key
    );
  };
  assert(
    labelProps.length === 3 &&
      readsIntentLabel('tier_up') &&
      readsIntentLabel('tier_down') &&
      !!labelFor('same_value'),
    'n5a: MODE_LABEL has exactly the three modes and reads both tier labels from TRADE_INTENT_LABEL',
    modeLabelDecl ? txt(sf, modeLabelDecl).replace(/\s+/g, ' ') : 'MODE_LABEL not found',
  );
  const literalCount = (text) =>
    findAll(sf, (n) => ts.isStringLiteral(n) && n.text === text).length;
  assert(
    literalCount('Same value') === 1 &&
      literalCount('Tier up') === 0 &&
      literalCount('Tier down') === 0,
    "n5b: 'Same value' appears exactly once; 'Tier up'/'Tier down' are never re-hardcoded (single label source)",
    `Same value ×${literalCount('Same value')}, Tier up ×${literalCount('Tier up')}, Tier down ×${literalCount('Tier down')}`,
  );
}

// ── verdict ───────────────────────────────────────────────────────────────

if (failures > 0) {
  console.error(`\n${failures} assertion(s) failed.`);
  process.exit(1);
}
console.log('\nAll shop-deck assertions passed.');
