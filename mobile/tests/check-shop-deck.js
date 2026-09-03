#!/usr/bin/env node
// #402/#403 — "More offers" = shop a player (rev-3 structural guard: the
// PUSHED WINDOW, rev3-spec.md §1/§2 + §4a, superseding the inline strip).
//
// WHY THIS EXISTS. The operator ruled #402 and #403 one experience, and the
// rev-3 rulings (docs/feedback/items/402-more-offers-shop/
// rulings-2026-08-28b.md) re-shaped it: the deck card's give-side "More
// offers" control NAVIGATES to a pushed `ShopAssetScreen` (back returns to
// the untouched deck), the position filter row applies to ALL THREE modes
// with one shared selection, and Same value runs on `lateral_scope:"tier"`
// with an auto-widen-on-zero default (§4a operator ruling). Nearly every
// failure mode of that design is invisible to tsc:
//
//   • the fork could lose its give-side or flag guard (receive side, or a
//     flag-off user, silently loses the shipped pin path — R-1′/R-17), or
//     stop navigating and quietly rebuild inline state;
//   • the route could get flag-gated (the house rule is the flag gates the
//     ENTRY, not the route), or lose `gestureEnabled: false` and reopen
//     the iOS edge-drag vs pager fight rev-1 D-1 closed;
//   • the screen could lose its FeedbackFAB (#188 — a root-stack push
//     mounts its own), or the body could grow a second one (#196/#197);
//   • TradesScreen could re-grow an inline mount / shopAsset state — the
//     machinery rev3-spec §1 explicitly DELETES;
//   • the pager could be rebuilt on Gesture.Pan / PanResponder (HLD D-2
//     held even inline: a plain FlatList, no gesture arbitration);
//   • SHOP_MODE_GROUP could silently cross tier_up ↔ tier_down — all three
//     values are string literals of one union, so tsc cannot tell them
//     apart (R-3): it is EXECUTED here, not pattern-matched;
//   • the `1 / X` counter could read a different list than the pager
//     renders and lie after a dismiss (R-5);
//   • the ✓ and ✕ could get crossed (both are () => void — dismissing
//     would queue a real offer to a league-mate), or the dismiss could
//     POST immediately and make the "Undo" copy a lie (R-6/R-8/R-9);
//   • the filter row could get re-scoped to Same value only (rev-3 §2 puts
//     it on every mode), grow a per-mode selection (it is ONE shared
//     state), offer PICK (server 400s it — R-12), DROP the pin's own
//     position (ruling R-2026-08-28-B), send `swap_positions` on an empty
//     selection (breaking each mode's byte-identical default request), or
//     drop `lateral_scope:"tier"` (silently reverting Same value to the
//     ±band the operator ruled out);
//   • the auto-widen could fire against an explicit selection (user
//     selections always win), widen the TIER modes (only the lateral group
//     widens), or widen SILENTLY (the notice line is the ruling's
//     honest-notice half);
//   • the four client events could go unregistered, land in
//     NON_INTENT_EVENTS, double-emit shop_opened (P-3: one emitter, at the
//     navigate call site), or mislabel their screens (the window's events
//     say 'ShopAsset'; shop_opened names the TAP on Trades — the taxonomy
//     comment and the emit sites agree on that split);
//   • a committed dismiss could be resurrected by a cache tick (Fix A: the
//     suppression set has exactly two gates — a committed dismiss and a
//     queued ✓ like, #418 — and is never cleared by data), or an early
//     commit could leave a dead "Undo" button on screen (B-4 —
//     retract-by-reference, now wired on the SCREEN's toast mount).
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
const BODY_REL = 'src/components/ShopOffersBody.tsx';
const SCREEN_REL = 'src/screens/ShopAssetScreen.tsx';
const NAV_REL = 'src/navigation/RootNav.tsx';
const MODE_REL = 'src/utils/shopMode.ts';
const CARD_REL = 'src/components/TradeCard.tsx';
const API_REL = 'src/api/trades.ts';
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

/** testID attr containing `tid` → the owning JSX element's opening tag. */
function elementByTestId(sf, tid) {
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
  return el || null;
}

/** testID attr → owning element's onPress text (the (i)/(j) helper). */
function jsxHandler(sf, tid) {
  const el = elementByTestId(sf, tid);
  if (!el) return null;
  const onPress = el.attributes.properties.find(
    (p) => ts.isJsxAttribute(p) && p.name.getText(sf) === 'onPress',
  );
  return onPress ? txt(sf, onPress) : null;
}

/** All track('<eventName>', …) calls in a file. */
function trackCallsFor(sf, eventName) {
  return findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'track' &&
      n.arguments.length > 0 &&
      ts.isStringLiteral(n.arguments[0]) &&
      n.arguments[0].text === eventName,
  );
}

// ── (a) the handleKeepSide fork — entry navigates, flag-off arm intact ────

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
      // Re-keyed 2026-08-29 (canvas-results QA round B-C4): the 1-vs-many
      // fork moved into openShopForCard so the browse pager's "More offers"
      // shares the EXACT entry (no parallel path). The branch reaches
      // navigate-vs-chooser through it; the helper's own shape is pinned
      // below and by check-canvas-results §12i.
      assert(
        referencesIdentifier(sf, fork, 'openShopForCard'),
        'a4: the shop branch routes through openShopForCard (navigate 1 give / chooser several)',
      );
      const forkFn = functionNamed(sf, 'openShopForCard');
      assert(
        !!forkFn &&
          referencesIdentifier(sf, forkFn, 'openShopWindow') &&
          referencesIdentifier(sf, forkFn, 'setShopChooserCard'),
        'a4b: openShopForCard navigates (1 give) or opens the chooser (several)',
      );
      // The flag-off arm still carries the shipped pin path: every one of
      // these must appear in handleKeepSide but OUTSIDE the shop branch.
      for (const id of [
        'preSinglePinSnapshotRef',
        'setSide',
        'resetDeckForNewTargets',
        // Re-keyed 2026-08-29: the flag-off arm dispatches through
        // dispatchGenerate (the QA round's session-lifecycle helper) — the
        // same single generateMutation underneath.
        'dispatchGenerate',
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
  // a7 — the entry NAVIGATES: openShopWindow calls navigation.navigate with
  // the 'ShopAsset' route literal (rev3-spec §1).
  const fnOpen = functionNamed(sf, 'openShopWindow');
  const navCall =
    fnOpen &&
    findAll(
      sf,
      (n) =>
        ts.isCallExpression(n) &&
        ts.isPropertyAccessExpression(n.expression) &&
        n.expression.name.text === 'navigate' &&
        n.getStart(sf) >= fnOpen.getStart(sf) &&
        n.getEnd() <= fnOpen.getEnd() &&
        n.arguments.length > 0 &&
        ts.isStringLiteral(n.arguments[0]) &&
        n.arguments[0].text === 'ShopAsset',
    )[0];
  assert(
    !!navCall,
    "a7: openShopWindow navigates to 'ShopAsset' (the window, not inline state)",
    fnOpen ? 'no navigate(\'ShopAsset\', …) inside openShopWindow' : 'openShopWindow not found',
  );
}

// ── (b) no pan machinery in the body or the mode map (AST, not text) ──────

for (const rel of [BODY_REL, MODE_REL]) {
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

// ── (c) rev-3 §1 — the route: registered unconditionally, gesture off ─────

{
  const sf = parse(NAV_REL);
  // The <Stack.Screen name="ShopAsset" …> element.
  const nameAttr = findAll(
    sf,
    (n) =>
      ts.isJsxAttribute(n) &&
      n.name.getText(sf) === 'name' &&
      n.initializer &&
      ts.isStringLiteral(n.initializer) &&
      n.initializer.text === 'ShopAsset',
  )[0];
  assert(!!nameAttr, 'c1: RootNav registers a Stack.Screen named "ShopAsset"');
  if (nameAttr) {
    let el = nameAttr.parent;
    while (el && !ts.isJsxSelfClosingElement(el) && !ts.isJsxOpeningElement(el)) {
      el = el.parent;
    }
    const elFull = el && ts.isJsxOpeningElement(el) ? el.parent : el;
    // c2 — UNCONDITIONAL: no conditional or && ancestor between the element
    // and the navigator (the house rule: the flag gates the entry point,
    // not the route). Every registration in RootNav is a flat child today,
    // so ANY conditional wrapper is a regression.
    const conditionalWrap =
      elFull &&
      nearestAncestor(
        elFull,
        (n) =>
          ts.isConditionalExpression(n) ||
          (ts.isBinaryExpression(n) &&
            n.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken),
      );
    assert(
      !!elFull && !conditionalWrap,
      'c2: the ShopAsset registration is UNCONDITIONAL (no flag/conditional wrapper)',
      conditionalWrap ? `wrapped by: ${txt(sf, conditionalWrap).slice(0, 80)}…` : 'element not resolved',
    );
    // c3 — gestureEnabled: false inside THIS element's options (rev-1 D-1:
    // the iOS interactive-pop edge drag would fight the FlatList pager).
    const gestureOff =
      elFull &&
      findAll(
        sf,
        (n) =>
          ts.isPropertyAssignment(n) &&
          n.name.getText(sf) === 'gestureEnabled' &&
          n.initializer.kind === ts.SyntaxKind.FalseKeyword &&
          n.getStart(sf) >= elFull.getStart(sf) &&
          n.getEnd() <= elFull.getEnd(),
      )[0];
    assert(
      !!gestureOff,
      'c3: the ShopAsset screen options set gestureEnabled: false',
      'the interactive pop would fight the horizontal pager (rev-1 D-1)',
    );
  }
}

// ── (s) rev-3 §1 — the screen: FAB, body, screen-owned toast ─────────────

{
  const sf = parse(SCREEN_REL);
  // s1 — exactly one FeedbackFAB, activeScreen="ShopAsset",
  // aboveTabBar={false} (#188: root-stack push mounts its own).
  const fabs = findAll(
    sf,
    (n) =>
      (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
      n.tagName.getText(sf) === 'FeedbackFAB',
  );
  assert(fabs.length === 1, 's1a: ShopAssetScreen mounts exactly one FeedbackFAB', `found ${fabs.length}`);
  if (fabs.length === 1) {
    const attrs = fabs[0].attributes.properties.filter(ts.isJsxAttribute);
    const active = attrs.find((a) => a.name.getText(sf) === 'activeScreen');
    const above = attrs.find((a) => a.name.getText(sf) === 'aboveTabBar');
    assert(
      !!active &&
        ts.isStringLiteral(active.initializer) &&
        active.initializer.text === 'ShopAsset',
      's1b: the FAB reports activeScreen="ShopAsset"',
      active ? txt(sf, active) : 'activeScreen attr missing',
    );
    assert(
      !!above && /false/.test(txt(sf, above)),
      's1c: the FAB is mounted aboveTabBar={false} (no tab bar under a root push)',
      above ? txt(sf, above) : 'aboveTabBar attr missing',
    );
  }
  // s2 — the screen mounts the body component.
  const body = findAll(
    sf,
    (n) =>
      (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
      n.tagName.getText(sf) === 'ShopOffersBody',
  );
  assert(body.length === 1, 's2: ShopAssetScreen mounts ShopOffersBody (the re-hosted internals)');
  // s3 — the screen owns the Toast mount and retracts BY REFERENCE (QA
  // B-4, relocated from the inline host — rev3-spec §1: "the window owns
  // its own Toast mount now — same retraction semantics").
  const toastEl = findAll(
    sf,
    (n) =>
      (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
      n.tagName.getText(sf) === 'Toast',
  );
  assert(toastEl.length === 1, 's3a: ShopAssetScreen mounts its own Toast');
  const retractAttr = findAll(
    sf,
    (n) => ts.isJsxAttribute(n) && n.name.getText(sf) === 'onToastRetract',
  );
  assert(
    retractAttr.length === 1 &&
      referencesIdentifier(sf, retractAttr[0], 'setToast') &&
      /===/.test(txt(sf, retractAttr[0])),
    's3b: the screen retracts by reference (setToast keeps any newer toast in the slot)',
    retractAttr.length
      ? `attr: ${txt(sf, retractAttr[0]).replace(/\s+/g, ' ')}`
      : 'onToastRetract not passed at the mount',
  );
}

// ── (del) rev3-spec §1's delete list — the inline machinery is GONE ──────

{
  const sf = parse(HOST_REL);
  const bodyMounts = findAll(
    sf,
    (n) =>
      (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
      /^ShopOffers(Strip|Body)$/.test(n.tagName.getText(sf)),
  );
  assert(
    bodyMounts.length === 0,
    'del1: TradesScreen mounts NO shop strip/body (the window replaced the inline mount)',
    `found ${bodyMounts.length} mount(s)`,
  );
  for (const id of ['setShopAsset', 'shopOpen']) {
    assert(
      findAll(sf, (n) => ts.isIdentifier(n) && n.text === id).length === 0,
      `del2: no '${id}' identifier survives in TradesScreen (inline shop state deleted)`,
    );
  }
  // The chooser is the ONE inline piece that stays (a Modal sheet over the
  // mounted deck; its pick navigates).
  const chooser = findAll(
    sf,
    (n) =>
      (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
      n.tagName.getText(sf) === 'ShopWhichPlayerSheet',
  );
  assert(chooser.length === 1, 'del3: the ShopWhichPlayerSheet chooser stays mounted on TradesScreen');
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
  const sf = parse(BODY_REL);
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

// ── (g) no FeedbackFAB in the body (the SCREEN owns the one FAB) ─────────

{
  const sf = parse(BODY_REL);
  assert(
    findAll(sf, (n) => ts.isIdentifier(n) && n.text === 'FeedbackFAB').length === 0,
    'g: ShopOffersBody mounts no FeedbackFAB (ShopAssetScreen owns the single mount — #188)',
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
  // h3 — ENTRIES, not prose: a comment may legitimately mention a shop
  // event (the QA-B F4 comment fix in analytics_queries does, in
  // backticks); what must never appear is a QUOTED shop_* string — the
  // only form that would enroll one in NON_INTENT_EVENTS.
  assert(
    !/["']shop_\w+["']/.test(queries),
    'h3: no shop_* event is an entry in analytics_queries (all four stay INTENT by default)',
    'NON_INTENT_EVENTS must not name them — each is a deliberate tap',
  );
}

// ── (h4) P-3 — shop_opened has exactly ONE emitter, at the navigate site ──
// The rule: an event fires once, where the thing it names happens. The one
// place the window opens is openShopWindow (the navigate call site), so the
// one emit lives there — direct 1-asset entry emits once, a chooser pick
// emits once (at pick time, with the picked asset's position), a chooser
// Cancel emits nothing. Round 1 had TWO emitters, which double-fired
// chooser entries and phantom-fired Cancels.

{
  const host = parse(HOST_REL);
  const emits = trackCallsFor(host, 'shop_opened');
  assert(
    emits.length === 1,
    'h4a: shop_opened is emitted from exactly ONE call site in TradesScreen',
    `found ${emits.length} emitter(s) — the round-1 double-emit is back`,
  );
  const fnOpen = functionNamed(host, 'openShopWindow');
  assert(
    emits.length === 1 &&
      !!fnOpen &&
      emits[0].getStart(host) >= fnOpen.getStart(host) &&
      emits[0].getEnd() <= fnOpen.getEnd(),
    'h4b: the one emitter sits inside openShopWindow (the single window-open path)',
    'the emit must live where the window actually opens, not in an entry fork',
  );
  // Neither entry re-emits: handleKeepSide and the chooser onPick reach the
  // event only THROUGH openShopWindow.
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
  for (const rel of [BODY_REL, SCREEN_REL]) {
    const sf = parse(rel);
    assert(
      trackCallsFor(sf, 'shop_opened').length === 0,
      `h4d: ${path.basename(rel)} emits no shop_opened (the host's navigate path owns it)`,
    );
  }
}

// ── (h5) rev-3 §1 — the screen labels: emit sites and taxonomy AGREE ─────
// shop_opened names the "More offers" TAP (a control tap on the Trades
// deck), so its screen stays 'Trades' — exactly what the taxonomy comment
// says. The window's own events say where THEY happen: 'ShopAsset'.

{
  const host = parse(HOST_REL);
  const opened = trackCallsFor(host, 'shop_opened')[0];
  assert(
    !!opened &&
      opened.arguments.length >= 3 &&
      ts.isStringLiteral(opened.arguments[2]) &&
      opened.arguments[2].text === 'Trades',
    "h5a: shop_opened fires with screen 'Trades' (it names the tap, per the taxonomy comment)",
    opened ? `third arg: ${txt(host, opened.arguments[2])}` : 'no emitter found',
  );
  const taxonomy = fs.readFileSync(TAXONOMY_ABS, 'utf8');
  assert(
    /shop_opened[\s\S]{0,400}screen\s*\n?\s*#\s*'Trades'|names the TAP[\s\S]{0,200}'Trades'/.test(taxonomy),
    "h5b: the taxonomy comment states the 'Trades' screen choice for shop_opened",
    'emit site and taxonomy comment must agree (rev3-spec §1)',
  );
  const body = parse(BODY_REL);
  for (const ev of ['shop_mode_selected', 'shop_positions_selected', 'shop_dismiss_undone']) {
    const calls = trackCallsFor(body, ev);
    assert(
      calls.length === 1 &&
        calls[0].arguments.length >= 3 &&
        ts.isStringLiteral(calls[0].arguments[2]) &&
        calls[0].arguments[2].text === 'ShopAsset',
      `h5c: ${ev} fires once from the body with screen 'ShopAsset'`,
      calls.length !== 1
        ? `found ${calls.length} emitter(s)`
        : `third arg: ${txt(body, calls[0].arguments[2])}`,
    );
  }
  // The ✓'s calc_trade_queued rides queueCalcTrade's screen arg — honest
  // about where the tap happened.
  const fnLike = functionNamed(body, 'handleLike');
  const screenProp =
    fnLike &&
    findAll(
      body,
      (n) =>
        ts.isPropertyAssignment(n) &&
        n.name.getText(body) === 'screen' &&
        ts.isStringLiteral(n.initializer) &&
        n.initializer.text === 'ShopAsset' &&
        n.getStart(body) >= fnLike.getStart(body) &&
        n.getEnd() <= fnLike.getEnd(),
    )[0];
  assert(
    !!screenProp,
    "h5d: the like's queueCalcTrade call reports screen 'ShopAsset'",
    'calc_trade_queued would otherwise claim a screen the user is not on',
  );
}

// ── (i) uncrossed ✓/✕, and the dismiss is HELD (the copy stays true) ─────

{
  const sf = parse(BODY_REL);
  const like = jsxHandler(sf, 'shop.like-btn');
  const dismiss = jsxHandler(sf, 'shop.dismiss-btn');
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

// ── (k) #418 — a queued like leaves the pager (the second suppression gate)
// "Send this offer" queued the trade but left the tile in place; the fix
// gives handleLike the committed-removal half commitDismiss already has.
// Pinned here: the write goes to the COMMITTED set (never the pending one —
// there is no un-queue route, so "Undo" would be the dishonest copy R-9 was
// written to prevent); the pager index is REQUESTED before the write (P-1);
// the write is conditional on `res.queued`, inside the then-branch, after
// the await (never optimistic — a refused queue leaves the tile); an
// already-queued idea is still queued and still leaves (R-b); the like
// never flushes the pending dismiss (D-1); busyKey still releases in
// `finally` (R-8); the write is a copy-and-ADD of the prior set, never a
// replacement or a no-op (k9); the request carries the tap-time `index`
// (k3b); and the three "one gate" comments carry the item number, each at
// its own named site (k8).

{
  const sf = parse(BODY_REL);
  const fnLike = functionNamed(sf, 'handleLike');
  const inside = (n, root) =>
    !!root && n.getStart(sf) >= root.getStart(sf) && n.getEnd() <= root.getEnd();

  // k1 — the like writes the COMMITTED set.
  assert(
    !!fnLike && referencesIdentifier(sf, fnLike, 'setSuppressed'),
    'k1: handleLike writes the suppression set (a queued like is committed by the call itself)',
  );
  // k2 — …and never the pending one (no undo route exists for a sent offer).
  assert(
    !!fnLike &&
      !referencesIdentifier(sf, fnLike, 'setLocallyRemoved') &&
      !referencesIdentifier(sf, fnLike, 'locallyRemoved'),
    'k2: handleLike never touches locallyRemoved (a like has no pending state)',
  );
  // k3 — P-1: the index is REQUESTED before the data write. A missing
  // identifier on either side is a fail, not a vacuous pass.
  const reqIds = findAll(
    sf,
    (n) => ts.isIdentifier(n) && n.text === 'requestPagerScroll' && inside(n, fnLike),
  );
  const supIds = findAll(
    sf,
    (n) => ts.isIdentifier(n) && n.text === 'setSuppressed' && inside(n, fnLike),
  );
  assert(
    reqIds.length > 0 && supIds.length > 0 && reqIds[0].getStart(sf) < supIds[0].getStart(sf),
    'k3: handleLike requests the pager index BEFORE writing the suppression set (P-1)',
    `requestPagerScroll ×${reqIds.length}, setSuppressed ×${supIds.length}`,
  );
  // k4 — the write is gated on `res.queued`, in the THEN branch, with no
  // negation in the condition (the inverted-branch hole: `if (res.queued)
  // {toast} else {suppress}` would remove the tile on a refusal).
  const supCall = findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'setSuppressed' &&
      inside(n, fnLike),
  )[0];
  const gate = supCall && nearestAncestor(supCall, ts.isIfStatement);
  assert(
    !!supCall &&
      !!gate &&
      inside(gate, fnLike) &&
      referencesIdentifier(sf, gate.expression, 'queued') &&
      !/!/.test(txt(sf, gate.expression)) &&
      inside(supCall, gate.thenStatement),
    'k4: the suppression write sits in the then-branch of an un-negated `queued` check (a refused queue writes nothing)',
    !supCall
      ? 'no setSuppressed call in handleLike'
      : !gate
        ? 'setSuppressed is not inside an if statement'
        : `if (${txt(sf, gate.expression)}) — in then-branch: ${inside(supCall, gate.thenStatement)}`,
  );
  // k3b (D-2) — the request carries the tap-time `index`: `0` would rewind
  // the pager on every send, `index + 1` would skip a tile. Read from the
  // queued branch so it is the same call k3 ordered and k4 gated (hence
  // placed after k4, which finds that branch).
  const reqCall = findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'requestPagerScroll' &&
      !!gate &&
      inside(n, gate.thenStatement),
  )[0];
  assert(
    !!reqCall && reqCall.arguments.length === 1 && txt(sf, reqCall.arguments[0]) === 'index',
    'k3b: the queued branch requests the tap-time `index` (not 0, not index ± n — D-2)',
    reqCall
      ? `requestPagerScroll(${reqCall.arguments.map((a) => txt(sf, a)).join(', ')})`
      : 'no requestPagerScroll call in the queued branch',
  );
  // k5 — an already-queued idea is still queued and still leaves.
  assert(
    !!fnLike && !referencesIdentifier(sf, fnLike, 'alreadyQueued'),
    'k5: handleLike never branches on alreadyQueued (already queued IS queued — the tile leaves either way)',
  );
  // k6 (D-1) — the like is not a flush trigger for the pending dismiss.
  assert(
    !!fnLike &&
      !referencesIdentifier(sf, fnLike, 'flushPendingDismiss') &&
      !referencesIdentifier(sf, fnLike, 'flushPendingDismissRef'),
    'k6: handleLike never flushes the pending dismiss (D-1 — a like creates no second pending state)',
  );
  // k7 (R-8) — busyKey releases in `finally`; the write lives inside the
  // `try`, AFTER the await (post-resolution, never optimistic).
  const tryStmt = findAll(sf, (n) => ts.isTryStatement(n) && inside(n, fnLike))[0];
  const awaitExpr = findAll(sf, (n) => ts.isAwaitExpression(n) && inside(n, fnLike))[0];
  assert(
    !!tryStmt &&
      !!tryStmt.finallyBlock &&
      referencesIdentifier(sf, tryStmt.finallyBlock, 'setBusyKey') &&
      !!supCall &&
      !!awaitExpr &&
      inside(supCall, tryStmt.tryBlock) &&
      supCall.getStart(sf) > awaitExpr.getStart(sf),
    'k7: busyKey is released in finally, and the suppression write sits inside the try AFTER the await',
    !tryStmt
      ? 'no try statement in handleLike'
      : !tryStmt.finallyBlock
        ? 'try has no finally block'
        : !referencesIdentifier(sf, tryStmt.finallyBlock, 'setBusyKey')
          ? 'finally does not release busyKey'
          : 'the write is outside the try block or precedes the await',
  );
  // k8 (R-9) — textual tripwire, not a proof: three NAMED comment sites
  // each carry the item number — the header's "✓ like" bullet, the
  // `suppressed` declaration's comment block, and commitDismiss's body.
  // Named sites, not a count: the fix's own comment in handleLike must not
  // be able to stand in for a clause deleted elsewhere. A comment block is
  // the leading trivia of the statement it precedes (fullStart → start).
  const src = sf.text;
  const leading = (stmt) => (stmt ? src.slice(stmt.getFullStart(), stmt.getStart(sf)) : '');
  const hdrLead = leading(sf.statements.find((st) => leading(st).includes('✓ like')));
  const bStart = hdrLead.indexOf('✓ like');
  const bEnd = hdrLead.indexOf('✕ dismiss', Math.max(bStart, 0));
  const hdrBullet = bStart >= 0 && bEnd > bStart ? hdrLead.slice(bStart, bEnd) : '';
  const supDecl = findAll(
    sf,
    (n) => ts.isVariableDeclaration(n) && txt(sf, n.name) === '[suppressed, setSuppressed]',
  )[0];
  const supBlock = supDecl ? leading(nearestAncestor(supDecl, ts.isVariableStatement)) : '';
  const fnCommit = functionNamed(sf, 'commitDismiss');
  const sites = {
    'header ✓-like bullet': hdrBullet.includes('#418'),
    'suppressed comment block': supBlock.includes('#418'),
    'commitDismiss': !!fnCommit && txt(sf, fnCommit).includes('#418'),
  };
  assert(
    Object.values(sites).every(Boolean),
    'k8: the header ✓-like bullet, the `suppressed` comment block, and commitDismiss each name the second gate (#418)',
    `missing: ${Object.keys(sites).filter((k) => !sites[k]).join(', ') || 'none'}`,
  );
  // k9 — the write is a copy-and-ADD of the prior set: an updater arrow
  // whose body names `key` and calls `.add(`. `setSuppressed(new Set([key]))`
  // would resurrect every earlier committed ✕ and sent offer of the session
  // (Fix A broken by replacement); `(s) => new Set(s)` would be the #418
  // bug back with k1–k8 green.
  const supArg = supCall && supCall.arguments.length === 1 ? supCall.arguments[0] : null;
  assert(
    !!supArg &&
      ts.isArrowFunction(supArg) &&
      referencesIdentifier(sf, supArg.body, 'key') &&
      txt(sf, supArg.body).includes('.add('),
    'k9: the suppression write is an updater that copies the prior set and ADDS the key (never a replacement, never a no-op)',
    supCall
      ? `setSuppressed(${supCall.arguments.map((a) => txt(sf, a)).join(', ')})`
      : 'no setSuppressed call in handleLike',
  );
  // k10 (D-178 QA-B B-5) — the send also marks the `shop-ideas` cache rows
  // stale. Without it the fix was time-boxed, not made: `suppressed` dies
  // with this screen instance while the cache row lives 60 s, so reopening
  // the window inside that minute re-rendered the idea just sent. Three
  // clauses, each load-bearing: the call sits in the SAME queued branch (a
  // refused queue must invalidate nothing), the key is the `shop-ideas`
  // prefix (every position selection owns its own row), and
  // `refetchType: 'none'` — a refetch here would rebuild the open pager
  // under the user's thumb, which is the P-1 rule this fix must not break.
  const invCall = findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isPropertyAccessExpression(n.expression) &&
      n.expression.name.text === 'invalidateQueries' &&
      !!gate &&
      inside(n, gate.thenStatement),
  )[0];
  const invArg = invCall && invCall.arguments.length === 1 ? invCall.arguments[0] : null;
  const invTxt = invArg ? txt(sf, invArg) : '';
  assert(
    !!invArg &&
      ts.isObjectLiteralExpression(invArg) &&
      /queryKey\s*:\s*\[\s*'shop-ideas'/.test(invTxt) &&
      /refetchType\s*:\s*'none'/.test(invTxt),
    "k10: the queued branch invalidates the ['shop-ideas', …] rows with refetchType 'none' (the next mount refetches; the open pager does not)",
    invCall ? `invalidateQueries(${invTxt})` : 'no invalidateQueries call in the queued branch',
  );
}

// ── (j) rev-3 §2 — the position filter row, on ALL modes ─────────────────
// One shared multi-select at the top of the window: domain excludes PICK
// (server 400s it) and includes the pin's own position (R-2026-08-28-B);
// an empty selection OMITS swap_positions from the BASE request (each
// mode's default request stays byte-identical); the analytics event carries
// a count, never the set; the filtered empty state offers the
// Clear-positions escape; and a selection change flushes the held dismiss.

// j0 — the API layer: optional swap_positions AND optional lateral_scope.
{
  const sf = parse(API_REL);
  const fn = functionNamed(sf, 'fetchAssetIdeas');
  assert(!!fn, 'j0a: fetchAssetIdeas exists in api/trades.ts');
  if (fn) {
    for (const [field, label] of [
      ['swap_positions', 'j0b'],
      ['lateral_scope', 'j0c'],
    ]) {
      const sig = findAll(
        sf,
        (n) =>
          ts.isPropertySignature(n) &&
          n.name.getText(sf) === field &&
          n.getStart(sf) >= fn.getStart(sf) &&
          n.getEnd() <= fn.getEnd(),
      )[0];
      assert(
        !!sig && !!sig.questionToken,
        `${label}: fetchAssetIdeas body type has ${field}?: (optional)`,
        sig ? 'present but REQUIRED — every pre-rev-3 caller would have to send it' : 'missing',
      );
    }
  }
}

{
  const sf = parse(BODY_REL);

  // j1 — the picker is SHARED across modes: it renders at the top, gated
  // only by pickerApplies (real-position pin), NEVER by the active mode.
  // (Rev-3 §2 inverts the rev-2 same-value-only mount — R-10 superseded.)
  const pickerEl = elementByTestId(sf, 'shop.picker');
  assert(!!pickerEl, 'j1a: the picker container (shop.picker) exists');
  if (pickerEl) {
    const modeGuard = nearestAncestor(
      pickerEl,
      (n) =>
        ts.isConditionalExpression(n) && /mode\s*===/.test(txt(sf, n.condition)),
    );
    assert(
      !modeGuard,
      'j1b: NO mode guard wraps the picker (the row applies to every mode — rev3 §2)',
      modeGuard ? `guard: ${txt(sf, modeGuard.condition).replace(/\s+/g, ' ')}` : undefined,
    );
    const applyGuard = nearestAncestor(
      pickerEl,
      (n) =>
        ts.isConditionalExpression(n) &&
        referencesIdentifier(sf, n.condition, 'pickerApplies'),
    );
    assert(
      !!applyGuard,
      'j1c: the picker is gated on pickerApplies only (no dead chips for a pick pin)',
    );
  }
  // j1d — ONE shared selection state, kept across mode switches: a single
  // `positions` useState, and handleSelectMode never writes it.
  const posStates = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isArrayBindingPattern(n.name) &&
      /\bpositions\b/.test(txt(sf, n.name)) &&
      /setPositions/.test(txt(sf, n.name)) &&
      n.initializer &&
      /useState/.test(txt(sf, n.initializer)),
  );
  assert(
    posStates.length === 1,
    'j1d: exactly one [positions, setPositions] state (one selection shared across modes)',
    `found ${posStates.length}`,
  );
  const fnMode = functionNamed(sf, 'handleSelectMode');
  assert(
    !!fnMode && !referencesIdentifier(sf, fnMode, 'setPositions'),
    'j1e: handleSelectMode never touches the selection (switching modes keeps it)',
  );

  // j2 — the chip domain: exactly {QB,RB,WR,TE}; own position INCLUDED;
  // only the #360 avoided-set filters it.
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
    "j2b: no 'PICK' string literal anywhere in the body (server 400s it — R-12)",
  );
  const offeredDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'offeredPositions' &&
      n.initializer,
  )[0];
  assert(
    !!offeredDecl &&
      referencesIdentifier(sf, offeredDecl.initializer, 'SWAP_POSITIONS') &&
      referencesIdentifier(sf, offeredDecl.initializer, 'avoided') &&
      !referencesIdentifier(sf, offeredDecl.initializer, 'pinPos'),
    "j2c: offeredPositions offers the pin's OWN position (filters only by avoided — R-2026-08-28-B)",
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
    'j2e: shop.pos.<POS> is minted exactly once, inside SwapPosChip',
    `found ${posTids.length} template(s)`,
  );

  // j3 — the request layer. TWO swap_positions writers exist by design in
  // rev-3: the BASE query's conditional spread (empty selection ⇒ key
  // OMITTED — byte-identical default request) and the auto-widen re-request
  // (which sends the full offerable set EXPLICITLY — rev3 §2/§4a).
  const swapProps = findAll(
    sf,
    (n) =>
      (ts.isPropertyAssignment(n) || ts.isShorthandPropertyAssignment(n)) &&
      n.name.getText(sf) === 'swap_positions',
  );
  assert(
    swapProps.length === 2,
    'j3a: swap_positions is assigned in exactly two places (base conditional + widened re-request)',
    `found ${swapProps.length}`,
  );
  const baseProp = swapProps.find((p) =>
    referencesIdentifier(sf, p, 'debouncedSwapKey'),
  );
  const widenProp = swapProps.find((p) => referencesIdentifier(sf, p, 'widenKey'));
  assert(
    !!baseProp && !!widenProp,
    'j3b: one writer reads the settled selection, the other the widen set',
    `base: ${!!baseProp}, widen: ${!!widenProp}`,
  );
  if (baseProp) {
    const cond = nearestAncestor(baseProp, ts.isConditionalExpression);
    const whenFalse = cond ? unwrapAs(cond.whenFalse) : null;
    assert(
      !!cond &&
        !!whenFalse &&
        ts.isObjectLiteralExpression(whenFalse) &&
        whenFalse.properties.length === 0,
      'j3c: the base assignment sits in a conditional whose false arm is {} (key OMITTED, not undefined/[])',
      cond ? `false arm: ${txt(sf, cond.whenFalse)}` : 'no enclosing conditional',
    );
    assert(
      !!cond && referencesIdentifier(sf, cond.condition, 'debouncedSwapKey'),
      'j3d: the guard is the SETTLED selection (debouncedSwapKey), so the wire state tracks what settled',
    );
    assert(
      !!cond && !!nearestAncestor(cond, ts.isSpreadAssignment),
      'j3e: the conditional is spread into the body (no swap_positions key survives the empty arm)',
    );
  }

  // j3f — lateral_scope: "tier" is sent by EVERY fetchAssetIdeas call in
  // the body, unconditionally (rev3 §3: the shop client always sends it;
  // "band" stays the wire default for every other caller by omission).
  const ideaCalls = findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'fetchAssetIdeas',
  );
  assert(ideaCalls.length >= 1, 'j3f-pre: the body calls fetchAssetIdeas', 'no calls found');
  for (const call of ideaCalls) {
    const scopeProp = findAll(
      sf,
      (n) =>
        ts.isPropertyAssignment(n) &&
        n.name.getText(sf) === 'lateral_scope' &&
        ts.isStringLiteral(n.initializer) &&
        n.initializer.text === 'tier' &&
        n.getStart(sf) >= call.getStart(sf) &&
        n.getEnd() <= call.getEnd(),
    )[0];
    const conditionalWrap =
      scopeProp &&
      (() => {
        let cur = scopeProp.parent;
        while (cur && cur !== call) {
          if (ts.isConditionalExpression(cur) || ts.isSpreadAssignment(cur)) return cur;
          cur = cur.parent;
        }
        return null;
      })();
    assert(
      !!scopeProp && !conditionalWrap,
      `j3g: fetchAssetIdeas call at offset ${call.getStart(sf)} sends lateral_scope: 'tier' unconditionally`,
      scopeProp ? 'present but conditionally' : 'lateral_scope missing from the call body',
    );
  }

  // j4 — shop_positions_selected carries a COUNT (n), never the set.
  const posTracks = trackCallsFor(sf, 'shop_positions_selected');
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
    "j5b: clearPositions resets the selection to empty (back to each mode's default)",
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

// ── (w) rev-3 §2/§4a — auto-widen on zero (OPERATOR-RULED 2026-08-28) ────
// Empty selection + the own-position tier sweep answers ZERO laterals ⇒
// the client re-requests with ALL offerable positions and SAYS SO (the
// honest-notice pattern). Explicit selections always win; only the lateral
// group widens; the notice renders only while widened results are showing.

{
  const sf = parse(BODY_REL);

  // w1 — the eligibility gate: settled selection EMPTY + server's raw
  // lateral answer zero. (The explicit-selection immunity IS the
  // `debouncedSwapKey === ''` term.)
  const eligDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'widenEligible' &&
      n.initializer,
  )[0];
  const eligText = eligDecl ? txt(sf, eligDecl.initializer) : '';
  assert(
    !!eligDecl &&
      /debouncedSwapKey\s*===\s*''/.test(eligText) &&
      /lateral/.test(eligText) &&
      /\.length/.test(eligText),
    "w1a: widenEligible requires the settled selection to be EMPTY and the raw lateral group to be zero",
    eligText ? eligText.replace(/\s+/g, ' ').slice(0, 120) : 'widenEligible not found',
  );
  // w2 — the re-request is gated on that eligibility (enabled:), and its
  // swap_positions come from the offerable set.
  const widenQueryDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'widenedQuery' &&
      n.initializer,
  )[0];
  const enabledProp =
    widenQueryDecl &&
    findAll(
      sf,
      (n) =>
        ts.isPropertyAssignment(n) &&
        n.name.getText(sf) === 'enabled' &&
        n.getStart(sf) >= widenQueryDecl.getStart(sf) &&
        n.getEnd() <= widenQueryDecl.getEnd(),
    )[0];
  assert(
    !!enabledProp && referencesIdentifier(sf, enabledProp.initializer, 'widenEligible'),
    'w2a: the widened query is enabled ONLY by widenEligible (never fires against an explicit selection)',
    enabledProp ? `enabled: ${txt(sf, enabledProp.initializer)}` : 'widenedQuery or its enabled gate not found',
  );
  const widenKeyDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'widenKey' &&
      n.initializer,
  )[0];
  assert(
    !!widenKeyDecl && referencesIdentifier(sf, widenKeyDecl.initializer, 'offeredPositions'),
    'w2b: the widened set is the OFFERABLE positions (#360 avoided stays out even when widening)',
  );

  // w3 — only the LATERAL group widens, and the widen seam is ONE
  // snapshot (QA-B p6): a single `rendered` derivation carries both the
  // composed groups AND the widenShowing flag, so the notice and the
  // tiles it describes can never come from independently-derived state.
  const renderedDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'rendered' &&
      n.initializer &&
      referencesIdentifier(sf, n.initializer, 'widenEligible'),
  )[0];
  assert(
    !!renderedDecl,
    'w3a: ONE composed derivation (rendered) exists, keyed on widenEligible — groups and widenShowing are fields of a single snapshot (QA-B p6)',
  );
  if (renderedDecl) {
    const lateralProp = findAll(
      sf,
      (n) =>
        ts.isPropertyAssignment(n) &&
        n.name.getText(sf) === 'lateral' &&
        n.getStart(sf) >= renderedDecl.getStart(sf) &&
        n.getEnd() <= renderedDecl.getEnd(),
    )[0];
    assert(
      !!lateralProp && referencesIdentifier(sf, lateralProp.initializer, 'widenedQuery'),
      'w3b: the widened payload replaces the lateral group',
    );
    for (const other of ['upgrade', 'downgrade']) {
      const prop = findAll(
        sf,
        (n) =>
          ts.isPropertyAssignment(n) &&
          n.name.getText(sf) === other &&
          n.getStart(sf) >= renderedDecl.getStart(sf) &&
          n.getEnd() <= renderedDecl.getEnd(),
      );
      assert(
        prop.length === 0,
        `w3c: the ${other} group is never rebuilt from the widened payload (spread of the base only)`,
        `found an explicit ${other}: assignment in the composed groups`,
      );
    }
    // w3d — both consumers read OFF the snapshot: `groups` and
    // `widenShowing` are projections of `rendered`, never re-derived
    // independently (re-deriving either reopens the p6 seam).
    for (const field of ['groups', 'widenShowing']) {
      const proj = findAll(
        sf,
        (n) =>
          ts.isVariableDeclaration(n) &&
          ts.isIdentifier(n.name) &&
          n.name.text === field &&
          n.initializer &&
          referencesIdentifier(sf, n.initializer, 'rendered'),
      );
      assert(
        proj.length === 1,
        `w3d: '${field}' is a projection of the rendered snapshot (exactly one decl, reading \`rendered\`)`,
        `found ${proj.length} qualifying declaration(s)`,
      );
    }
  }

  // w4 — the visible notice: renders ONLY in the widened state, in the
  // Same value results area. Never silent, never on the tier modes, never
  // for an explicit selection (widenShowing ⊆ widenEligible ⊆ empty key).
  const noticeEl = elementByTestId(sf, 'shop.widen-notice');
  assert(!!noticeEl, 'w4a: the widen notice (shop.widen-notice) exists');
  if (noticeEl) {
    const guard = nearestAncestor(
      noticeEl,
      (n) =>
        ts.isConditionalExpression(n) &&
        referencesIdentifier(sf, n.condition, 'widenShowing'),
    );
    assert(
      !!guard && /mode\s*===\s*'same_value'/.test(txt(sf, guard.condition)),
      "w4b: the notice is guarded by widenShowing AND mode === 'same_value'",
      guard ? `guard: ${txt(sf, guard.condition).replace(/\s+/g, ' ')}` : 'no widenShowing guard',
    );
  }

  // w5 (QA-B finding 2) — RENDERED-MODE TICK DISCIPLINE: the flush/rewind
  // tick (`ideasUpdatedAt`) derives from the query actually feeding the
  // rendered tiles. Base alone in the tier modes and in unwidened Same
  // value; the widened tick participates ONLY while the widened row is
  // what the pager renders. Re-coupling this to an unconditional
  // Math.max(base, widened) is exactly the reviewer-B defect: the widen
  // probe fires in every mode, so a widened payload landing 0.5–2 s after
  // a tier-mode dismiss would commit it early (Undo toast retracted
  // mid-window) and rewind the pager under the user.
  const tickDecl = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === 'ideasUpdatedAt' &&
      n.initializer,
  )[0];
  const tickInit = tickDecl && unwrapAs(tickDecl.initializer);
  assert(
    !!tickInit &&
      ts.isConditionalExpression(tickInit) &&
      referencesIdentifier(sf, tickInit.condition, 'widenShowing') &&
      /mode\s*===\s*'same_value'/.test(txt(sf, tickInit.condition)) &&
      referencesIdentifier(sf, tickInit.whenTrue, 'widenedQuery') &&
      referencesIdentifier(sf, tickInit.whenFalse, 'ideasQuery') &&
      !referencesIdentifier(sf, tickInit.whenFalse, 'widenedQuery'),
    "w5a: ideasUpdatedAt is conditional on the rendered mode — same_value+widenShowing ? max(base, widened) : base ALONE (the widened tick never drives flush/rewind in the tier modes)",
    tickDecl
      ? txt(sf, tickDecl.initializer).replace(/\s+/g, ' ').slice(0, 160)
      : 'ideasUpdatedAt declaration not found',
  );
}

// ── (m) QA B-4 — an early commit retracts the Undo toast (body half) ─────
// The held dismiss's "Dismissed · Undo" toast must never outlive the undo
// window as a dead button: every early flush retracts it BY REFERENCE (a
// newer toast that already replaced it is left alone), and only the natural
// UNDO_HOLD_MS expiry — whose toast dismisses itself — skips the retract.
// (The host half — the reference-equality setToast — is asserted on the
// SCREEN in s3b: rev3-spec §1 moved the Toast mount there.)

{
  const sf = parse(BODY_REL);

  const propsSig = findAll(
    sf,
    (n) => ts.isPropertySignature(n) && n.name.getText(sf) === 'onToastRetract',
  );
  assert(
    propsSig.length === 1 && !propsSig[0].questionToken,
    'm1: the body contract has a REQUIRED onToastRetract prop',
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
    'm4a: handleDismiss stores the undo-toast descriptor it hands the screen',
  );
  const fnUndo = functionNamed(sf, 'undoDismiss');
  assert(
    !!fnUndo && referencesIdentifier(sf, fnUndo, 'undoToastRef'),
    'm4b: undoDismiss drops the descriptor (the toast dismissed itself — nothing to retract later)',
  );
}

// ── (n) the three universal rules + Chalkline + label source ─────────────
// R-A/Fix A: a COMMITTED dismissal is client-authoritative for the shop
// session (one suppression set, added to only at commit, never cleared by
// data ticks — B-3 + P-2). R-C/P-1: the pager position derives from the
// rendered data — scrolls react to data changes, never race them.
// R-C/P-4: the entry is gated on every flag its actions require.

{
  const sf = parse(BODY_REL);

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
    'n2a: a [suppressed, setSuppressed] useState pair exists in the body',
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
      n.name.text === 'baselineModeCount' &&
      n.initializer,
  )[0];
  assert(
    !!baseDecl &&
      referencesIdentifier(sf, baseDecl.initializer, 'suppressed') &&
      referencesIdentifier(sf, baseDecl.initializer, 'locallyRemoved'),
    'n2f: baselineModeCount runs the same filter (the Clear-positions label never counts a dismissed tile)',
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

  // n4 — Chalkline scan over the body AND the new screen: no emoji in
  // rendered copy, no gradient/blur, every corner radius ≤ 8 (ADR-004 —
  // no specced pill exists on these surfaces, so radii.pill is illegal).
  const emojiRe = /\p{Extended_Pictographic}/u;
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
  for (const rel of [BODY_REL, SCREEN_REL]) {
    const scanSf = parse(rel);
    const base = path.basename(rel);
    const renderedText = [];
    walk(scanSf, (n) => {
      if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) {
        renderedText.push(n.text);
      } else if (ts.isTemplateExpression(n)) {
        renderedText.push(n.head.text);
        for (const s of n.templateSpans) renderedText.push(s.literal.text);
      } else if (n.kind === ts.SyntaxKind.JsxText) {
        renderedText.push(n.getText(scanSf));
      }
    });
    const emojiHits = renderedText.filter((t) => emojiRe.test(t));
    assert(
      emojiHits.length === 0,
      `n4a: no emoji anywhere in ${base} strings/copy (Chalkline: never emoji as icons)`,
      emojiHits.slice(0, 3).join(' | '),
    );
    const gradientIds = findAll(
      scanSf,
      (n) => ts.isIdentifier(n) && /gradient/i.test(n.text),
    );
    const blurProps = findAll(
      scanSf,
      (n) =>
        (ts.isPropertyAssignment(n) || ts.isJsxAttribute(n)) &&
        /blur/i.test(n.name.getText(scanSf)),
    );
    assert(
      gradientIds.length === 0 && blurProps.length === 0,
      `n4b: no gradient identifiers and no blur props in ${base} (Chalkline: no gradients, no glassmorphism)`,
      `${gradientIds.length} gradient id(s), ${blurProps.length} blur prop(s)`,
    );
    const CORNER = /^border(TopLeft|TopRight|BottomLeft|BottomRight)?Radius$/;
    const badRadii = [];
    walk(scanSf, (n) => {
      if (!ts.isPropertyAssignment(n) || !CORNER.test(n.name.getText(scanSf))) return;
      const init = unwrapAs(n.initializer);
      if (ts.isNumericLiteral(init)) {
        if (Number(init.text) > 8) badRadii.push(txt(scanSf, n));
      } else if (
        ts.isPropertyAccessExpression(init) &&
        ts.isIdentifier(init.expression) &&
        init.expression.text === 'radii'
      ) {
        const v = radiiVals[init.name.text];
        if (!(typeof v === 'number' && v <= 8)) badRadii.push(txt(scanSf, n));
      } else {
        badRadii.push(txt(scanSf, n)); // unresolvable radius — must be auditable
      }
    });
    assert(
      Object.keys(radiiVals).length > 0 && badRadii.length === 0,
      `n4c: every corner radius in ${base} resolves to ≤ 8 (Chalkline radius rule; no pill on this surface)`,
      badRadii.join(' | ') || 'could not resolve radii tokens from the theme',
    );
  }

  // n5 (reviewer A pin) — label sources: the two tier labels READ the
  // shipped TRADE_INTENT_LABEL constant (the DNA sheet and the window can
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

// ── (cs) QA-B plausible 5 — chooser staleness guards on the HOST ─────────
// `shopChooserCard` holds a whole TradeCard in TradesScreen state. Three
// ways it goes stale, each with its own clear (asserted individually so
// dropping any ONE goes red): an async league switch while the Modal is up
// (a pick would navigate with the NEW leagueId + the OLD league's asset),
// a deck reset for new targets (the card belongs to a deck that no longer
// exists), and a flag kill (the sheet's `visible` conjunction only HIDES
// it — a later re-light must not pop a days-old chooser).

{
  const sf = parse(HOST_REL);
  const effects = findAll(
    sf,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === 'useEffect' &&
      n.arguments.length === 2,
  );

  // cs1 — the league-switch effect (deps exactly [leagueId], the one that
  // also drops the deck) clears the chooser.
  const leagueSwitch = effects.find(
    (e) =>
      ts.isArrayLiteralExpression(e.arguments[1]) &&
      txt(sf, e.arguments[1]).replace(/\s+/g, '') === '[leagueId]' &&
      referencesIdentifier(sf, e.arguments[0], 'setDeck'),
  );
  assert(
    !!leagueSwitch &&
      referencesIdentifier(sf, leagueSwitch.arguments[0], 'setShopChooserCard'),
    "cs1: the league-switch effect clears shopChooserCard (a pick can never pair the new leagueId with the old league's asset)",
    leagueSwitch ? 'league-switch effect found but it does not clear the chooser' : 'no [leagueId]-keyed deck-reset effect found',
  );

  // cs2 — resetDeckForNewTargets clears the chooser with the rest of the
  // deck state (the rev-2 shop-state clear, restored for the chooser).
  const fnReset = functionNamed(sf, 'resetDeckForNewTargets');
  assert(
    !!fnReset && referencesIdentifier(sf, fnReset, 'setShopChooserCard'),
    'cs2: resetDeckForNewTargets clears shopChooserCard (a stale card cannot outlive its deck)',
  );

  // cs3 — the flag kill CLEARS, it doesn't just hide: an effect keyed on
  // shopEnabled nulls the card when the conjunction dies.
  const killEffect = effects.find(
    (e) =>
      referencesIdentifier(sf, e.arguments[1], 'shopEnabled') &&
      referencesIdentifier(sf, e.arguments[0], 'setShopChooserCard') &&
      /!shopEnabled/.test(txt(sf, e.arguments[0])),
  );
  assert(
    !!killEffect,
    'cs3: a !shopEnabled effect CLEARS the chooser card (the visible conjunction only hides; a re-light must never resurrect a stale chooser)',
    'no useEffect keyed on shopEnabled clears shopChooserCard on !shopEnabled',
  );
}

// ── t: the scoped tour gate (#402/#403 rev-3 / D-158, rev3-spec §6) ───────
//
// Operator ruling 2026-08-27: with `calc.inline_home` on, NO guided or tour
// beat runs on the merged Trades page — so `onboarding.guide_v2` can flip
// back true globally without re-lighting guidance there. The gate lives in
// `useGuide.requestStep` (the one choke point every Trades-beat path funnels
// through: TradesScreen's auto-start/chain effects, spine arrivals, and the
// calc-tour runner's deck half). This section lives HERE rather than in
// check-guide-script.js because the gate is a property of the rev-3 merged
// page, not of the beat data that suite polices — and it EXECUTES the real
// engine (the check-tour-suppression.js pattern): a sabotage that empties
// the gate must go red because the store ran, not because a regex matched.
{
  const guideSrc = fs.readFileSync(
    path.join(__dirname, '..', 'src/state/useGuide.ts'), 'utf8');
  const tourSrc = fs.readFileSync(
    path.join(__dirname, '..', 'src/utils/calcTour.ts'), 'utf8');
  const scriptSrc = fs.readFileSync(
    path.join(__dirname, '..', 'src/components/analystScript.ts'), 'utf8');

  // -- behavioural: run the real requestStep under a controllable flag map --
  function makeZustandCreate() {
    return function create(initializer) {
      let state;
      const setState = (partial) => {
        const next = typeof partial === 'function' ? partial(state) : partial;
        state = Object.assign({}, state, next);
      };
      const getState = () => state;
      state = initializer(setState, getState, { setState, getState });
      const hook = (selector) => (selector ? selector(state) : state);
      hook.getState = getState;
      hook.setState = setState;
      return hook;
    };
  }

  const flags = {
    'onboarding.v2': true,
    'onboarding.guided_avatar': true,
    'onboarding.guide_v2': true,
    'calc.inline_home': true,
  };
  const ob = {
    guideDismissed: false,
    guideTourCompleted: false,
    guideScriptVersion: 2,
    guideV1Upgrader: false,
    guideSeen: {},
    guideDisplayCounts: {},
    guideReceipts: {},
    guideRetired: {},
  };
  const patches = [];
  const events = [];
  const coordState = {
    tourHold: false,
    claim: () => true,
    release: () => {},
  };

  let guideMod = null;
  try {
    const js = ts.transpileModule(guideSrc, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
    }).outputText;
    const shim = { exports: {} };
    const stubs = {
      zustand: { create: makeZustandCreate() },
      'expo-constants': { default: { expoConfig: { version: 'test' } } },
      './useFeatureFlags': {
        useFeatureFlags: { getState: () => ({ flags }) },
        onboardingEnabled: (key) => !!flags['onboarding.v2'] && !!flags[key],
      },
      './useOnboardingState': {
        getOnboardingState: () => ob,
        patchOnboardingState: (p) => {
          patches.push(p);
          for (const [k, v] of Object.entries(p)) {
            if (v && typeof v === 'object' && ob[k] && typeof ob[k] === 'object') {
              Object.assign(ob[k], v);
            } else ob[k] = v;
          }
        },
        resetGuideProgress: () => {},
        resetGuideProgressV2: () => {},
      },
      './useInterruptCoordinator': {
        useInterruptCoordinator: { getState: () => coordState },
      },
      './guideTargets': { measureGuideTarget: () => Promise.resolve(null) },
      '../api/events': { track: (name, props, screen) => events.push({ name, props, screen }) },
    };
    new Function('module', 'exports', 'require', js)(shim, shim.exports, (name) => {
      if (name in stubs) return stubs[name];
      throw new Error(
        `useGuide gained an unexpected runtime import ("${name}") — ` +
          'add a stub deliberately; do not let the behavioural section skip.',
      );
    });
    guideMod = shim.exports;
  } catch (e) {
    fail('t0: useGuide.ts transpiles and executes', String(e && e.message));
  }

  if (guideMod) {
    const store = guideMod.useGuide;
    const mkStep = (id, screen) => ({
      id, screen, line: 'x', pose: 'neutral', advance: 'tap',
    });

    // t1 — START suppressed: flag on, a Trades beat is refused before it
    // begins — no active bubble, no guide_step_shown, and NO side effects
    // (no seen mark / retirement / display count), so re-lighting guide_v2
    // finds every Trades beat unspent.
    const r1 = store.getState().requestStep(mkStep('s2.1', 'Trades'));
    assert(
      r1 === false && store.getState().active === null,
      't1: with calc.inline_home on, a Trades-screen beat never begins (refused at the START)',
      `returned ${r1}, active=${JSON.stringify(store.getState().active)}`,
    );
    assert(
      events.length === 0 && patches.length === 0,
      't1a: …and the refusal is SILENT — no event, no persisted state (the beat is unspent)',
      `events=${JSON.stringify(events)} patches=${JSON.stringify(patches)}`,
    );

    // t2 — scope: the gate covers Trades ONLY. A beat on any other screen
    // still shows under the same flag map (the re-lit guide_v2 must restore
    // guidance everywhere except the merged page).
    const r2 = store.getState().requestStep(mkStep('n9', 'Matches'));
    assert(
      r2 === true && store.getState().active?.id === 'n9' &&
        events.some((e) => e.name === 'guide_step_shown' && e.props.screen === 'Matches'),
      't2: the gate is scoped — a Matches beat still shows with calc.inline_home on',
      `returned ${r2}, active=${JSON.stringify(store.getState().active)}`,
    );
    store.getState().advance('tap'); // clean the slot for the next scenario

    // t3 — the cross-screen ARRIVAL path: a running calc tour that hands off
    // to the deck (`calcTourDeckArrived` → `requestAt`) requests its deck
    // beats as TOUR-OWNED steps under the tour hold. The gate must refuse
    // those too — it sits above the tour-owned exemption — and the runner's
    // own step-over + endTour then close the run without a stranded overlay
    // (pinned structurally in t7/t8).
    coordState.tourHold = true;
    store.getState().setTourOwnedIds(new Set(['n19']));
    const r3 = store.getState().requestStep(mkStep('n19', 'Trades'));
    assert(
      r3 === false && store.getState().active === null,
      't3: a tour-owned deck beat arriving cross-screen is refused too (the arrival path is gated)',
      `returned ${r3}`,
    );
    coordState.tourHold = false;
    store.getState().setTourOwnedIds(new Set());

    // t4 — the re-light plan: flag off, the same Trades beat shows again.
    // This is what makes the gate the SCOPED replacement for the temporary
    // global guide_v2 kill.
    flags['calc.inline_home'] = false;
    const r4 = store.getState().requestStep(mkStep('s2.1', 'Trades'));
    assert(
      r4 === true && store.getState().active?.id === 's2.1',
      't4: with calc.inline_home off, Trades beats run again (nothing was spent while gated)',
      `returned ${r4}`,
    );
    store.getState().advance('tap');
    flags['calc.inline_home'] = true;
  }

  // -- structural: the pieces the executed model cannot see ----------------

  // t5 — the choke point reads THE flag, by name, through a bare flag read
  // (deliberately not onboardingEnabled: killing the onboarding master must
  // not un-suppress the merged page).
  assert(
    /function inlineHomeTradesTourFree\(\)/.test(guideSrc) &&
      /flags\['calc\.inline_home'\] === true/.test(guideSrc) &&
      /if \(step\.screen === 'Trades' && inlineHomeTradesTourFree\(\)\) return false;/.test(guideSrc),
    "t5: requestStep's gate references calc.inline_home and compares exactly screen 'Trades'",
  );

  // t6 — placement: the gate refuses BEFORE the tour-owned exemption and
  // before any side-effect path inside requestStep, mirroring the #384 §20
  // no-side-effect refusal it sits beside.
  {
    const req = guideSrc.slice(
      guideSrc.indexOf('requestStep: (step, handlers) =>'),
      guideSrc.indexOf('trackSpotlightFrame: (frame)'),
    );
    const gate = req.indexOf('inlineHomeTradesTourFree()');
    assert(
      gate >= 0 && gate < req.indexOf('tourHold') && gate < req.indexOf('noteSuppressed('),
      't6: the gate sits above the tour-owned exemption and every side effect',
      'below the tourHold block a tour-owned deck beat would slip past; below a side effect the refusal spends the beat',
    );
  }

  // t7 — the arrival path funnels through the choke: every beat the runner's
  // deck half can request declares screen 'Trades' in the script, so t3's
  // refusal covers the whole `calcTourDeckArrived` sequence (n23b rides via
  // beatIdFor). A deck beat redeclared to another screen would tunnel under
  // the gate.
  {
    const deckList = tourSrc.slice(
      tourSrc.indexOf('export const CALC_TOUR_DECK'),
      tourSrc.indexOf('CALC_TOUR_ORDER'),
    );
    const deckIds = [...deckList.matchAll(/'(n\d+)'/g)].map((m) => m[1]).concat('n23b');
    let allTrades = deckIds.length >= 6;
    for (const id of deckIds) {
      const at = scriptSrc.indexOf(`id: '${id}',`);
      if (at < 0 || !/screen: 'Trades'/.test(scriptSrc.slice(at, at + 120))) allTrades = false;
    }
    assert(
      allTrades,
      "t7: every deck-half beat (incl. n23b) declares screen 'Trades' — the arrival path cannot tunnel under the gate",
      `deck ids: ${deckIds.join(', ')}`,
    );
  }

  // t8 — the refusal degrades CLEANLY at the runner: a refused beat is
  // stepped over (never a stall), and endTour both tears down any standing
  // bubble and releases the hold — so a run that crosses into gated
  // territory ends, it does not strand a half-open overlay or a mute.
  assert(
    /if \(shown\) \{\s*beatsShown \+= 1;\s*return;\s*\}\s*[\s\S]{0,200}?requestAt\(i \+ 1\);/.test(tourSrc) &&
      /dismissActiveTourBubble\(\);[\s\S]{0,400}?endTourHold\(\)/.test(
        tourSrc.slice(tourSrc.indexOf('function endTour'), tourSrc.indexOf('function beatIdFor')),
      ),
    't8: the runner steps over refused beats and endTour tears down + releases — no stranded overlay',
  );
}

// ── verdict ───────────────────────────────────────────────────────────────

if (failures > 0) {
  console.error(`\n${failures} assertion(s) failed.`);
  process.exit(1);
}
console.log('\nAll shop-deck assertions passed.');
