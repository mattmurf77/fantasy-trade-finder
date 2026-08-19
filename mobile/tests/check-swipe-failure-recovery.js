#!/usr/bin/env node
// Swipe-failure recovery structural test.
// Ticket: docs/reviews/2026-08-18-bug-sweep/ticket.md § B4
//
// WHY THIS EXISTS. A pass that failed server-side rewound the deck to
// re-front the card but never cleared the double-fire guard
// (`lastDispositionedRef`), so every later ✕/✓/swipe on that card was a
// silent `return`: a permanent stall with no error and no visual change.
// Nothing about it is visible to a green flow run — the deck looks fine, the
// taps just do nothing — and the six OTHER clear sites all looked correct.
//
// Four properties are pinned here:
//
//   1. THE INVARIANT. Every `setDeckIdx` that is NOT a forward advance
//      re-fronts a card the user may already have dispositioned, so the
//      function that does it must ALSO clear the guard. Sites that replace
//      the whole deck (`setDeck([])` in the same block) are exempt: there is
//      no card left to re-front. This is the assertion that would have caught
//      the bug — `swipeMutation.onError` was simply not among the clear sites.
//   2. THE CLEAR IS KEYED ON THE **RAW** id. Edited cards (player swap,
//      feedback #86) carry a derived `<raw>::edited` trade_id, while the deck
//      and the double-fire guard both speak raw ids. Keying the clear on
//      `ctx.tradeId` instead of `ctx.rawId` silently restores the whole bug
//      for exactly the edited/swapped cards `EDITED_SUFFIX` exists for — and
//      a containment check over the enclosing function cannot see the
//      difference, which is why this is pinned structurally.
//   3. FAILURE IS VISIBLE AND ACTIONABLE — WITHOUT A RETRY BUTTON. The toast
//      must outlast the 1.5s default (`SWIPE_ERROR_HOLD_MS`), and it must
//      carry NO action. A Retry button was considered and dropped: with the
//      guard cleared (1+2) the card's own ✕/✓ re-POSTs *and* advances the
//      deck, which strictly dominates a Retry that re-POSTs while leaving the
//      card fronted — inviting a second, duplicate pass. That is not cosmetic:
//      `save_trade_decision` (backend/database.py:4794) is a plain INSERT with
//      no upsert and no unique constraint, so a duplicate writes a second row
//      and replays `trade_k_pass` twice. The copy therefore points at the
//      card ("Tap again"), which is now a real, working recovery.
//   4. THE 403 IS ITS OWN COPY. `verification_required` is a standing gate,
//      not a blip; retrying can never clear it, so it says so.
//
// Plus the second live strand: once a pass is banked, re-tapping the open
// layer-1 tile must not collapse layer 2 — the ✓ is disabled and swipe is
// inert on that card, so a collapse leaves nothing to tap.
//
// Run: node tests/check-swipe-failure-recovery.js

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
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');

function parse(rel) {
  const file = path.join(MOBILE, rel);
  return ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
}
function findAll(root, pred) {
  const out = [];
  (function walk(n) {
    if (pred(n)) out.push(n);
    n.forEachChild(walk);
  })(root);
  return out;
}
function ancestor(node, pred) {
  for (let n = node.parent; n; n = n.parent) if (pred(n)) return n;
  return null;
}
const isFunctionLike = (n) =>
  ts.isFunctionDeclaration(n) ||
  ts.isArrowFunction(n) ||
  ts.isFunctionExpression(n) ||
  ts.isMethodDeclaration(n);

const screenSrc = parse('src/screens/TradesScreen.tsx');
const screenText = read('src/screens/TradesScreen.tsx');
const panelText = read('src/components/DeclineReasonPanel.tsx');
const toastText = read('src/components/Toast.tsx');

const CLEAR = 'lastDispositionedRef.current = null';
const lineOf = (n) =>
  screenSrc.getLineAndCharacterOfPosition(n.getStart(screenSrc)).line + 1;

// ═══════════════════════════════════════════════════════════════════════
// 1. THE INVARIANT — every deck rewind re-arms the double-fire guard
// ═══════════════════════════════════════════════════════════════════════

// A forward advance can never re-front a dispositioned card.
const ADVANCE = /^\(\s*\w+\s*\)\s*=>\s*\w+\s*\+\s*1$/;

const rewinds = findAll(
  screenSrc,
  (n) => ts.isCallExpression(n) && n.expression.getText() === 'setDeckIdx',
)
  .filter((n) => !ADVANCE.test((n.arguments[0]?.getText() ?? '').trim()))
  // NO `setDeck([])` EXEMPTION. It used to exempt any rewind whose block
  // replaced the deck wholesale, reasoning that no dispositioned card
  // survives to be re-fronted. That reasoning is unsound: the guard is a
  // REF that outlives the deck, and the replacement deck can carry the same
  // trade_ids — the server hands back a still-running job verbatim even
  // under `force`, so the old job's poller can refill the emptied deck with
  // the exact card just dispositioned. Every genuinely-safe site already
  // clears the guard anyway, so the exemption's only real effect was to let
  // the one site that forgot (the QuickSet regen handoff) pass. Removing it
  // is why that site now carries the clear.
  .map((n) => ({ node: n, line: lineOf(n), fn: ancestor(n, isFunctionLike) }));

assert(
  rewinds.length >= 5,
  'TradesScreen: the rewind scan still finds deck rewinds to check',
  `found ${rewinds.length} — a renamed setter would make this test vacuous`,
);
for (const r of rewinds) {
  assert(
    !!r.fn && r.fn.getText().includes(CLEAR),
    `TradesScreen: the deck rewind at line ${r.line} re-arms the double-fire guard`,
    `its function must contain \`${CLEAR}\` — without it every later ✕/✓/swipe on the re-fronted card is a silent no-op`,
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 2. The regression itself — swipeMutation.onError is one of those sites
// ═══════════════════════════════════════════════════════════════════════

const onError = findAll(
  screenSrc,
  (n) =>
    ts.isPropertyAssignment(n) &&
    n.name.getText() === 'onError' &&
    n.getText().includes("Swipe didn't save"),
)[0];
assert(!!onError, "TradesScreen: the swipe mutation's onError is identifiable");
const onErrorText = onError ? onError.getText() : '';

assert(
  onErrorText.includes(CLEAR),
  'TradesScreen: swipeMutation.onError clears the double-fire guard',
  'B4 — the failed swipe re-fronts the card it just dispositioned',
);
assert(
  rewinds.some((r) => r.fn && r.fn.getText().includes("Swipe didn't save")),
  'TradesScreen: onError is covered by the rewind scan above',
  'the generic invariant must actually reach the site that regressed',
);
assert(
  /return cur - 1/.test(onErrorText),
  'TradesScreen: onError still rewinds the deck to re-front the failed card',
  'the clear only matters because the card comes back',
);

// ═══════════════════════════════════════════════════════════════════════
// 2b. The clear is keyed on the RAW id, and onMutate still supplies one
// ═══════════════════════════════════════════════════════════════════════
//
// `onErrorText.includes(CLEAR)` above is plain containment over the enclosing
// function: it would stay green if the clear were keyed on `ctx.tradeId` (the
// `<raw>::edited` id) instead of `ctx.rawId`. `lastDispositionedRef` is
// stamped with the RAW id at disposition time, so an edited card would never
// match, never clear, and stall exactly as before — the bug back, invisible,
// for the swapped cards `EDITED_SUFFIX` exists to serve.

const clearAssign = findAll(
  onError || screenSrc,
  (n) =>
    ts.isBinaryExpression(n) &&
    n.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
    n.left.getText() === 'lastDispositionedRef.current' &&
    n.right.kind === ts.SyntaxKind.NullKeyword,
)[0];
assert(!!clearAssign, 'TradesScreen: the guard clear in onError is locatable');

const clearGuard = clearAssign ? ancestor(clearAssign, ts.isIfStatement) : null;
assert(
  !!clearGuard,
  'TradesScreen: the clear is guarded on the poisoned id (not fired blind)',
  'clearing unconditionally would wipe a guard stamped by a DIFFERENT card',
);

// Whatever the guard compares `lastDispositionedRef.current` to must be the
// context's RAW id.
const RAW_ID = /^ctx\??\.rawId$/;
const idCompare = clearGuard
  ? findAll(
      clearGuard.expression,
      (n) =>
        ts.isBinaryExpression(n) &&
        (n.operatorToken.kind === ts.SyntaxKind.EqualsEqualsEqualsToken ||
          n.operatorToken.kind === ts.SyntaxKind.EqualsEqualsToken) &&
        [n.left, n.right].some((s) => s.getText() === 'lastDispositionedRef.current'),
    )[0]
  : null;
const otherSide = idCompare
  ? [idCompare.left, idCompare.right]
      .map((s) => s.getText().replace(/\s+/g, ''))
      .find((t) => t !== 'lastDispositionedRef.current')
  : null;
assert(
  !!otherSide && RAW_ID.test(otherSide),
  'TradesScreen: the clear compares the guard against `ctx.rawId`',
  `compares against \`${otherSide ?? '(nothing)'}\` — the guard holds the RAW ` +
    'trade_id, so keying this on `ctx.tradeId` (the `::edited` id) never ' +
    'matches for a swapped card and the stall comes straight back',
);

// …and the context has to still carry a raw id derived by stripping the
// suffix. If onMutate stops deriving it, the assertion above is comparing
// against `undefined` and passes vacuously.
const mutationOpts = onError ? onError.parent : null;
const onMutate =
  mutationOpts && ts.isObjectLiteralExpression(mutationOpts)
    ? mutationOpts.properties.find(
        (p) => ts.isPropertyAssignment(p) && p.name.getText() === 'onMutate',
      )
    : null;
assert(
  !!onMutate,
  'TradesScreen: the swipe mutation still has an onMutate beside that onError',
  'the error context is built there — without it `ctx.rawId` is undefined and ' +
    'the clear silently never fires',
);

const rawIdDecl = onMutate
  ? findAll(
      onMutate,
      (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === 'rawId',
    )[0]
  : null;
const rawIdInit = rawIdDecl && rawIdDecl.initializer ? rawIdDecl.initializer.getText() : '';
assert(
  !!rawIdDecl && /EDITED_SUFFIX/.test(rawIdInit) && /\.slice\(/.test(rawIdInit),
  'TradesScreen: onMutate derives `rawId` by stripping EDITED_SUFFIX',
  `rawId = ${rawIdInit || '(not declared)'} — an edited card\'s trade_id is ` +
    '`<raw>::edited`; without the strip the deck lookup, the rewind and the ' +
    'guard clear all miss',
);
const returnsRawId = onMutate
  ? findAll(onMutate, (n) => ts.isObjectLiteralExpression(n)).some((o) =>
      o.properties.some((p) => p.name && p.name.getText() === 'rawId'),
    )
  : false;
assert(
  returnsRawId,
  'TradesScreen: onMutate returns `rawId` in the error context',
  'onError reads `ctx.rawId` for both the rewind compare and the guard clear',
);
assert(
  /const EDITED_SUFFIX = '::edited';/.test(screenText),
  "TradesScreen: EDITED_SUFFIX is still the '::edited' marker being stripped",
  'pins the premise the raw/edited distinction rests on',
);

// ═══════════════════════════════════════════════════════════════════════
// 3. The failure is visible and actionable — and offers NO Retry
// ═══════════════════════════════════════════════════════════════════════
//
// A Retry action was built, reviewed, and removed. With the guard cleared,
// the card's own ✕/✓ re-POSTs *and* advances the deck; a Retry button would
// re-POST while leaving the card fronted, so a user who then taps ✕ files the
// same pass twice. `save_trade_decision` (backend/database.py:4794) is a
// plain INSERT — no upsert, no unique constraint — so the duplicate lands as
// a second row and replays `trade_k_pass` twice. The toast therefore points
// at the card instead of duplicating it.

const toastCalls = findAll(
  onError || screenSrc,
  (n) => ts.isCallExpression(n) && n.expression.getText() === 'setToast',
);
assert(
  toastCalls.length === 1,
  'TradesScreen: onError raises exactly ONE toast',
  `found ${toastCalls.length} — two toasts means one branch can fall back to ` +
    'the 1.5s default, or two stack on a single failure',
);
const toastArg = toastCalls[0] && toastCalls[0].arguments[0];
const toastObj =
  toastArg && ts.isObjectLiteralExpression(toastArg) ? toastArg : null;
const toastProp = (name) =>
  toastObj
    ? toastObj.properties.find((p) => p.name && p.name.getText() === name)
    : undefined;

assert(!!toastObj, 'TradesScreen: the failure toast is an object literal we can inspect');

// No action slot anywhere in onError — not on the toast, not smuggled into a
// nested branch.
const actionProps = findAll(
  onError || screenSrc,
  (n) => ts.isPropertyAssignment(n) && n.name.getText() === 'action',
);
assert(
  actionProps.length === 0,
  'TradesScreen: the failure toast carries NO action',
  `found ${actionProps.length} \`action\` propert(y|ies) — a Retry re-POSTs ` +
    'while leaving the card fronted, and `save_trade_decision` is a plain ' +
    'INSERT, so the follow-up ✕ writes a duplicate pass row',
);

const holdConst = /const SWIPE_ERROR_HOLD_MS = (\d+);/.exec(screenText);
assert(
  !!holdConst && Number(holdConst[1]) >= 5000,
  'TradesScreen: the failure toast holds long enough to read and act on',
  `found ${holdConst ? holdConst[1] : 'no constant'} — the 1.5s default flashed past the user`,
);
const holdProp = toastProp('holdMs');
assert(
  !!holdProp && /SWIPE_ERROR_HOLD_MS/.test(holdProp.getText()),
  'TradesScreen: the failure toast uses that hold',
  `holdMs = ${holdProp ? holdProp.getText() : '(absent)'} — a swipe failure ` +
    'must never fall back to the 1.5s default',
);

// The copy has to name the recovery that actually exists now: the card is
// back on top and its own controls work again.
const msgProp = toastProp('msg');
const msgText = msgProp ? msgProp.getText() : '';
assert(
  /Tap again/i.test(msgText),
  'TradesScreen: the failure copy tells the user to tap the card again',
  `msg = ${msgText || '(absent)'} — with no Retry button, the copy IS the ` +
    'recovery instruction; "try again" with no target is the old dead advice',
);

// ═══════════════════════════════════════════════════════════════════════
// 4. verification_required gets its own copy
// ═══════════════════════════════════════════════════════════════════════

assert(
  /err instanceof ApiError && err\.isVerificationRequired/.test(onErrorText),
  'TradesScreen: onError branches the copy on the verification 403',
  'ApiError.isVerificationRequired exists — a 403 is a standing gate, and ' +
    '"tap again to retry" is wrong advice for it',
);
const msgCond =
  msgProp && ts.isPropertyAssignment(msgProp) && ts.isConditionalExpression(msgProp.initializer)
    ? msgProp.initializer
    : null;
assert(
  !!msgCond && /isVerificationRequired/.test(msgCond.condition.getText()),
  'TradesScreen: the toast copy itself is the thing that branches',
  'one toast, two messages — the 403 must not share the "tap again" copy',
);
assert(
  !!msgCond && /Verify your account/.test(msgCond.whenTrue.getText()),
  'TradesScreen: the verification branch says verify',
  msgCond ? msgCond.whenTrue.getText() : undefined,
);
assert(
  !!msgCond && /Tap again/i.test(msgCond.whenFalse.getText()),
  'TradesScreen: the transient branch points back at the card',
  msgCond ? msgCond.whenFalse.getText() : undefined,
);

// The Toast primitive still has an action slot (Undo uses it). Pinned so a
// future "add Retry back" lands as a deliberate edit to THIS file, not as a
// silent re-introduction under a still-green suite.
assert(
  /action\?:\s*\{\s*label:\s*string;\s*onPress:\s*\(\)\s*=>\s*void\s*\}/.test(toastText),
  'Toast: the trailing-action slot still exists (Undo rides on it)',
);
assert(
  /action=\{toast\?\.action\}/.test(screenText),
  'TradesScreen: the Toast is wired to the action slot',
);

// ═══════════════════════════════════════════════════════════════════════
// 5. Second strand — a banked pass can never collapse layer 2
// ═══════════════════════════════════════════════════════════════════════

const panelSrc = parse('src/components/DeclineReasonPanel.tsx');
const tapTile = findAll(
  panelSrc,
  (n) => ts.isFunctionDeclaration(n) && n.name && n.name.getText() === 'tapTile',
)[0];
assert(!!tapTile, 'DeclineReasonPanel: tapTile exists');
const tapTileText = tapTile ? tapTile.getText() : '';
assert(
  /if\s*\(\s*open === key && banked\s*\)\s*return;/.test(tapTileText),
  'DeclineReasonPanel: re-tapping the open tile after banking does not collapse layer 2',
  'the pass is already banked — ✓ is disabled and swipe is inert, so a collapse strands the user',
);
assert(
  tapTileText.indexOf('open === key && banked') < tapTileText.indexOf('setOpen('),
  'DeclineReasonPanel: the no-op guard runs BEFORE any state is written',
  'falling through would re-fire onLayer1 and re-post the same reason row',
);
assert(
  /reasonBankedId === rawTopCard\?\.trade_id/.test(screenText),
  'TradesScreen: the ✓ is still disabled once the pass is banked',
  'pins the premise the collapse guard exists for',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All swipe-failure recovery checks passed.');
