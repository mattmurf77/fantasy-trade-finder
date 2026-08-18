#!/usr/bin/env node
// B2 (2026-08-18 bug sweep) — a player pushed DOWN a tier must land at the
// TOP of the destination, not the bottom.
//
// WHY THIS EXISTS. Three non-drag paths move a player between tiers on the
// Tiers board, and only ONE of them was direction-aware:
//
//   moveTierByOne      "Tier up / Tier down" bar   ✅ already correct
//   moveSelectedToTier tier-target chips ("3rd")   ❌ unconditional append
//   movePlayerToTier   VoiceOver "Move to <tier>"  ❌ unconditional append
//
// The chips row sits ABOVE the up/down buttons in the multi-select bar and is
// the more obvious "send this player to that tier" affordance, so the two
// broken paths were the ones users actually hit. A player demoted out of the
// 2nd-round tier landed dead last in 3rd — below every player the user had
// already judged worse than him — and the only repair was dragging him back
// up by hand.
//
// The placement rule, shared by all three paths and documented on
// moveTierByOne: minimum displacement. `TIERS` runs best → worst, so a
// SOURCE INDEX BELOW THE TARGET INDEX means moving DOWN the board: you are
// the destination's STRONGEST new member, so you go on top. A source index
// above the target means moving UP: you are its WEAKEST, so you go on the
// bottom. A source EQUAL to the target is a no-op — a repeat tap must not
// teleport a player from the top of a tier to its bottom. "Up" was never
// reported broken and is deliberately unchanged.
//
// HOW THIS IS TESTED, and why it changed (2026-08-18 adversarial review).
// The first version of this file asserted SHAPE only: that each handler
// branched on *some* relational comparison between *two* tier-ladder
// indices. That is polarity-blind. A reviewer flipped BOTH guards (`<` → `>`)
// — shipping the exact inverse of the requested behaviour — and all twelve
// assertions stayed green, because `a < b` and `a > b` are the same shape.
// The header claimed assertion 4 caught "getting the direction wrong". It
// did not.
//
// So the placement rule is now executed, not described. There is no unit
// harness around TiersScreen.tsx — these handlers are closures inside a
// 6,000-line screen component, reachable only through React state — so the
// `setBuckets` updater bodies are LIFTED out of the real TSX with the
// project's own TypeScript (parse → transpile → `new Function`, the way
// check-picker-pick-filter.js lifts its predicates), their free variables
// (`TIERS`, `emptyBuckets`, `selectedIds`, `target`, `player`) injected, and
// run over a fixture board. `TIERS` and `emptyBuckets` are lifted from the
// source too, so adding a tier cannot silently desync the fixture.
//
// WHAT IS PINNED, and the sabotage each assertion detects:
//
//   A. STRUCTURE (cheap, names the file/line when the shape moves)
//     1  Both handlers still exist and still assign the destination tier.
//        Sabotage: rename or delete one — the check goes red rather than
//        silently pinning nothing (the failure mode of a grep-based test).
//     2  Neither placement is an UNCONDITIONAL APPEND — an array literal
//        leading with `...next[target]`, which is exactly the shipped bug.
//     3  Each handler has a real PREPEND path: some array literal spreads
//        the destination's existing members at a position AFTER something
//        else, so a mover can land above them.
//     4  Each handler branches on a comparison between two tier-ladder
//        indices at all (NOT a polarity claim — B owns polarity). Sabotage:
//        branch on a hardcoded tier name or a selection-size test.
//
//   B. BEHAVIOUR (the real contract — polarity included)
//        The lifted updaters are run over a fixture board. A mover from a
//        BETTER tier must land at index 0 of the destination; a mover from a
//        WORSE tier must land last; a mover already IN the destination must
//        not move at all; no player may be lost or duplicated. Sabotage:
//        flip either `<` to `>` — B goes red on both handlers. Drop the
//        same-tier guard — the no-op cases go red (that regression was real:
//        a double-tap used to teleport a player from the top of a tier to
//        its bottom).
//
//   C. THE PATH THAT WAS ALREADY CORRECT
//     5  `moveTierByOne` keeps BOTH shapes: an append (up) and a prepend
//        (down). The ticket's decision was to leave it untouched; this
//        catches a well-meaning "unify the three handlers" refactor that
//        flattens it in either direction.
//
// Seed-independent: no simulator, no backend, no flag fixture.
//
// Run: node tests/check-tier-move-placement.js

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

const HOST_REL = 'src/screens/TiersScreen.tsx';
const LADDER_REL = 'src/utils/tierBands.ts';
const ROOT = path.join(__dirname, '..');
const ABS = path.join(ROOT, HOST_REL);

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const sf = ts.createSourceFile(
  ABS,
  fs.readFileSync(ABS, 'utf8'),
  ts.ScriptTarget.ES2019,
  /* setParentNodes */ true,
  ts.ScriptKind.TSX,
);

// ── AST helpers ────────────────────────────────────────────────────────────

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

function flat(n) {
  return n ? n.getText(sf).replace(/\s+/g, ' ').trim() : '';
}

function where(n) {
  return `${HOST_REL}:${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1}`;
}

/** The body of a top-level `const <name> = …` (useCallback wrapper included)
 *  or of a `function <name>(…)`. Both shapes appear in this file. */
function handlerNamed(name) {
  const decl = findAll(
    sf,
    (n) =>
      (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name) ||
      (ts.isFunctionDeclaration(n) && n.name && n.name.text === name),
  )[0];
  return decl || null;
}

/** `<obj>[<key>] = <rhs>` assignments inside `root`, for a given key text. */
function assignmentsToElement(root, objName, keyText) {
  return findAll(
    root,
    (n) =>
      ts.isBinaryExpression(n) &&
      n.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      ts.isElementAccessExpression(n.left) &&
      flat(n.left.expression) === objName &&
      flat(n.left.argumentExpression) === keyText,
  );
}

/** Array literals under `node` that spread `<obj>[<key>]`, paired with the
 *  index at which that spread sits. Index 0 ⇒ the destination's existing
 *  members come first ⇒ everything else is an APPEND. */
function spreadPositions(node, spreadText) {
  const out = [];
  for (const lit of findAll(node, (n) => ts.isArrayLiteralExpression(n))) {
    lit.elements.forEach((el, i) => {
      if (ts.isSpreadElement(el) && flat(el.expression) === spreadText) {
        out.push({ lit, index: i });
      }
    });
  }
  return out;
}

/** Locals in `root` initialised from a tier-ladder index lookup. These are
 *  what a legitimate direction test compares. */
function tierIndexLocals(root) {
  const names = new Set();
  for (const d of findAll(root, (n) => ts.isVariableDeclaration(n))) {
    if (ts.isIdentifier(d.name) && d.initializer && isTierIndexExpr(d.initializer)) {
      names.add(d.name.text);
    }
  }
  return names;
}

const isTierIndexExpr = (n) => /^TIERS\s*\.\s*(indexOf|findIndex)\s*\(/.test(flat(n));

/** A relational comparison whose BOTH sides are tier-ladder indices. Requiring
 *  both sides is what rules out `fromIdx !== -1` and friends passing as the
 *  direction test. NOTE: shape only — `a < b` and `a > b` are indistinguishable
 *  here, which is why section B exists. */
function directionComparisons(root) {
  const locals = tierIndexLocals(root);
  const isIndexSide = (n) =>
    isTierIndexExpr(n) || (ts.isIdentifier(n) && locals.has(n.text));
  const RELATIONAL = new Set([
    ts.SyntaxKind.LessThanToken,
    ts.SyntaxKind.GreaterThanToken,
    ts.SyntaxKind.LessThanEqualsToken,
    ts.SyntaxKind.GreaterThanEqualsToken,
  ]);
  return findAll(
    root,
    (n) =>
      ts.isBinaryExpression(n) &&
      RELATIONAL.has(n.operatorToken.kind) &&
      isIndexSide(n.left) &&
      isIndexSide(n.right),
  );
}

// ── Lifting helpers: real source → runnable JS ─────────────────────────────

const COMPILER_OPTIONS = {
  target: ts.ScriptTarget.ES2019,
  module: ts.ModuleKind.ESNext,
};

/** Transpile a TS snippet to plain JS (type annotations stripped). */
function toJs(snippet) {
  return ts.transpileModule(snippet, { compilerOptions: COMPILER_OPTIONS }).outputText;
}

/** Evaluate a lifted TS *expression* with the given free variables bound. */
function liftExpression(exprText, freeVars) {
  const names = Object.keys(freeVars);
  const body = `${toJs(`const __lifted = ${exprText};`)}\nreturn __lifted;`;
  // eslint-disable-next-line no-new-func
  return new Function(...names, body)(...names.map((n) => freeVars[n]));
}

/** Evaluate a lifted TS *function declaration* and return the function. */
function liftFunctionDecl(declText, name) {
  const body = `${toJs(declText)}\nreturn ${name};`;
  // eslint-disable-next-line no-new-func
  return new Function(body)();
}

/** The `setBuckets((prev) => …)` updater inside a handler, as a live function
 *  of `prev` with the handler's closure variables injected. */
function liftBucketsUpdater(handlerDecl, freeVars) {
  const call = findAll(
    handlerDecl,
    (n) => ts.isCallExpression(n) && flat(n.expression) === 'setBuckets',
  )[0];
  if (!call || !call.arguments[0]) return null;
  return liftExpression(call.arguments[0].getText(sf), freeVars);
}

// ═══════════════════════════════════════════════════════════════════════════
// A. STRUCTURE — 1-4, the two handlers the B2 fix repaired
// ═══════════════════════════════════════════════════════════════════════════

const HANDLERS = [
  { name: 'moveSelectedToTier', surface: 'tier-target chips (FB4-62)' },
  { name: 'movePlayerToTier', surface: 'VoiceOver "Move to <tier>" action' },
];

for (const { name, surface } of HANDLERS) {
  const fn = handlerNamed(name);
  assert(!!fn, `1a — \`${name}\` exists (${surface})`, 'declaration not found');
  if (!fn) continue;

  const writes = assignmentsToElement(fn, 'next', 'target');
  assert(
    writes.length > 0,
    `1b — \`${name}\` assigns \`next[target]\` (${writes.length} site${writes.length === 1 ? '' : 's'})`,
    'no assignment to the destination tier — placement moved somewhere this ' +
      'check no longer sees',
  );
  if (writes.length === 0) continue;

  // 2 — no unconditional append. The RHS itself being an array literal that
  // LEADS with `...next[target]` is precisely the shipped defect. (A
  // conditional RHS is fine here — assertions 3, 4 and section B police it.)
  const appends = writes.filter((w) => {
    const rhs = w.right;
    if (!ts.isArrayLiteralExpression(rhs)) return false;
    const first = rhs.elements[0];
    return (
      !!first && ts.isSpreadElement(first) && flat(first.expression) === 'next[target]'
    );
  });
  assert(
    appends.length === 0,
    `2 — \`${name}\` has no unconditional append to \`next[target]\``,
    appends.length
      ? `${where(appends[0])}: ${flat(appends[0])} — movers coming DOWN land ` +
        'below every existing member of the destination tier'
      : undefined,
  );

  // 3 — a prepend path exists: somewhere the destination's members are not
  // first, so a mover can land above them.
  const prepends = writes
    .flatMap((w) => spreadPositions(w.right, 'next[target]'))
    .filter((s) => s.index > 0);
  assert(
    prepends.length > 0,
    `3 — \`${name}\` can place a mover ABOVE the destination's existing members`,
    'every array literal spreads `next[target]` first — the handler branches ' +
      'but both arms append, which is the bug wearing a direction test',
  );

  // 4 — the branch compares two ladder indices (shape only; B owns polarity).
  const cmps = directionComparisons(fn);
  assert(
    cmps.length > 0,
    `4 — \`${name}\` branches on a tier-ladder index comparison` +
      (cmps.length ? ` (${flat(cmps[0])})` : ''),
    'no relational comparison between two TIERS.indexOf/findIndex values — ' +
      'the placement is branching on something that is not direction of travel',
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// B. BEHAVIOUR — the lifted updaters run over a fixture board
// ═══════════════════════════════════════════════════════════════════════════

// The ladder and the empty-board factory come from the source, so a new tier
// (or a reordered ladder) moves the fixture with it instead of desyncing.
const ladderSf = ts.createSourceFile(
  path.join(ROOT, LADDER_REL),
  fs.readFileSync(path.join(ROOT, LADDER_REL), 'utf8'),
  ts.ScriptTarget.ES2019,
  /* setParentNodes */ true,
  ts.ScriptKind.TS,
);
const tiersDecl = findAll(
  ladderSf,
  (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === 'TIERS',
)[0];
const emptyBucketsDecl = findAll(
  sf,
  (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === 'emptyBuckets',
)[0];

assert(!!tiersDecl && !!tiersDecl.initializer, `B0a — \`TIERS\` is liftable from ${LADDER_REL}`);
assert(!!emptyBucketsDecl, `B0b — \`emptyBuckets\` is liftable from ${HOST_REL}`);

let TIERS = null;
let emptyBuckets = null;
if (tiersDecl && tiersDecl.initializer && emptyBucketsDecl) {
  TIERS = liftExpression(tiersDecl.initializer.getText(ladderSf), {});
  emptyBuckets = liftFunctionDecl(emptyBucketsDecl.getText(sf), 'emptyBuckets');
}

// A ladder short enough to have no "two tiers above" case would make the
// non-adjacent assertions vacuous.
assert(
  Array.isArray(TIERS) && TIERS.length >= 5,
  'B0c — the lifted ladder is long enough for non-adjacent jumps',
  `TIERS = ${JSON.stringify(TIERS)}`,
);

if (TIERS && emptyBuckets && TIERS.length >= 5) {
  const BETTER_FAR = TIERS[0]; // two-plus tiers above the target
  const BETTER = TIERS[1];
  const TARGET = TIERS[2];
  const WORSE = TIERS[3];
  const WORSE_FAR = TIERS[4];

  const P = (id) => ({ id, name: id });
  const ids = (arr) => (arr || []).map((p) => p.id);

  /** A fresh board: two players in each of five zones, so every assertion
   *  can see order preserved within a group as well as between groups. */
  function board() {
    const b = emptyBuckets();
    b.unassigned = [P('u1'), P('u2')];
    b[BETTER_FAR] = [P('ff1'), P('ff2')];
    b[BETTER] = [P('a1'), P('a2')];
    b[TARGET] = [P('t1'), P('t2')];
    b[WORSE] = [P('b1'), P('b2')];
    b[WORSE_FAR] = [P('ww1'), P('ww2')];
    return b;
  }

  /** Every id on the board, sorted — a placement must never lose or clone. */
  function census(b) {
    return Object.keys(b)
      .flatMap((z) => ids(b[z]))
      .sort()
      .join(',');
  }
  const CENSUS = census(board());

  // ── B1 — moveSelectedToTier (tier-target chips) ─────────────────────────
  const selectedDecl = handlerNamed('moveSelectedToTier');
  const runSelected = selectedDecl
    ? (selected, target) => {
        const updater = liftBucketsUpdater(selectedDecl, {
          TIERS,
          emptyBuckets,
          selectedIds: new Set(selected),
          target,
        });
        const prev = board();
        return { prev, next: updater(prev) };
      }
    : null;

  assert(!!runSelected, 'B1a — `moveSelectedToTier`\'s setBuckets updater is liftable');

  if (runSelected) {
    // Moving DOWN the board (source index < target index) → TOP of target.
    // This is the assertion the polarity flip fails.
    {
      const { next } = runSelected(['a1'], TARGET);
      assert(
        ids(next[TARGET])[0] === 'a1',
        'B1b — a mover from a BETTER tier lands at index 0 of the destination',
        `${TARGET} = [${ids(next[TARGET])}] — a mover coming DOWN must be the ` +
          "destination's strongest member, not its weakest (`<` flipped to `>`?)",
      );
      assert(
        ids(next[TARGET]).join(',') === 'a1,t1,t2',
        'B1c — the destination\'s existing order is otherwise untouched',
        `${TARGET} = [${ids(next[TARGET])}]`,
      );
      assert(ids(next[BETTER]).join(',') === 'a2', 'B1d — the source tier keeps its non-movers');
      assert(census(next) === CENSUS, 'B1e — no player is lost or duplicated');
    }

    // Moving UP the board (source index > target index) → BOTTOM of target.
    {
      const { next } = runSelected(['b1'], TARGET);
      assert(
        ids(next[TARGET]).join(',') === 't1,t2,b1',
        'B1f — a mover from a WORSE tier lands last in the destination',
        `${TARGET} = [${ids(next[TARGET])}]`,
      );
    }

    // A selection spanning both sides splits around the existing members.
    {
      const { next } = runSelected(['a1', 'a2', 'b1', 'b2'], TARGET);
      assert(
        ids(next[TARGET]).join(',') === 'a1,a2,t1,t2,b1,b2',
        'B1g — a two-sided selection splits around the destination, order kept',
        `${TARGET} = [${ids(next[TARGET])}]`,
      );
    }

    // Non-adjacent jumps obey the same rule (the ticket's decision: direction-
    // aware for ALL jumps, not just adjacent ones).
    {
      const { next } = runSelected(['ff1', 'ww1'], TARGET);
      assert(
        ids(next[TARGET]).join(',') === 'ff1,t1,t2,ww1',
        'B1h — non-adjacent jumps are direction-aware too',
        `${TARGET} = [${ids(next[TARGET])}]`,
      );
    }

    // ── The same-tier no-op. A repeat chip tap on the tier you are already
    // in must change nothing; the pre-fix behaviour re-stripped and appended,
    // which sent a double-tap from the top of a tier straight to its bottom.
    {
      const { prev, next } = runSelected(['t1'], TARGET);
      assert(
        next === prev,
        'B1i — selecting only players ALREADY in the destination is a no-op',
        `${TARGET} = [${ids(next[TARGET])}] — a double-tap must not re-place`,
      );
    }
    {
      // …and a mixed selection moves the others while leaving the
      // destination's own members exactly where they are.
      const { next } = runSelected(['a1', 't1'], TARGET);
      assert(
        ids(next[TARGET]).join(',') === 'a1,t1,t2',
        'B1j — a destination member in the selection keeps its position',
        `${TARGET} = [${ids(next[TARGET])}] — t1 must not be restripped to the bottom`,
      );
    }

    // The pool is not a chip source (mirrors bulkMove; documented on the
    // handler). Selecting only pool players is a no-op.
    {
      const { prev, next } = runSelected(['u1'], TARGET);
      assert(
        next === prev,
        'B1k — `unassigned` is untouched by the tier chips',
        `${TARGET} = [${ids(next[TARGET])}], unassigned = [${ids(next.unassigned)}]`,
      );
    }
  }

  // ── B2 — movePlayerToTier (VoiceOver custom action) ─────────────────────
  const singleDecl = handlerNamed('movePlayerToTier');
  const runSingle = singleDecl
    ? (playerId, target) => {
        const prev = board();
        const player =
          Object.keys(prev)
            .flatMap((z) => prev[z])
            .find((p) => p.id === playerId) || P(playerId);
        const updater = liftBucketsUpdater(singleDecl, {
          TIERS,
          emptyBuckets,
          player,
          target,
        });
        return { prev, next: updater(prev) };
      }
    : null;

  assert(!!runSingle, 'B2a — `movePlayerToTier`\'s setBuckets updater is liftable');

  if (runSingle) {
    {
      const { next } = runSingle('a1', TARGET);
      assert(
        ids(next[TARGET]).join(',') === 'a1,t1,t2',
        'B2b — a player from a BETTER tier lands at index 0 of the destination',
        `${TARGET} = [${ids(next[TARGET])}] — coming DOWN means top (`
          + '`fromIdx < targetIdx` flipped?)',
      );
      assert(census(next) === CENSUS, 'B2c — no player is lost or duplicated');
    }
    {
      const { next } = runSingle('b1', TARGET);
      assert(
        ids(next[TARGET]).join(',') === 't1,t2,b1',
        'B2d — a player from a WORSE tier lands last in the destination',
        `${TARGET} = [${ids(next[TARGET])}]`,
      );
    }
    {
      const { next } = runSingle('ff1', TARGET);
      assert(
        ids(next[TARGET])[0] === 'ff1',
        'B2e — a non-adjacent jump downwards still lands on top',
        `${TARGET} = [${ids(next[TARGET])}]`,
      );
    }
    {
      const { next } = runSingle('ww1', TARGET);
      assert(
        ids(next[TARGET]).slice(-1)[0] === 'ww1',
        'B2f — a non-adjacent jump upwards still lands last',
        `${TARGET} = [${ids(next[TARGET])}]`,
      );
    }
    // The same-tier no-op — the regression a repeat VoiceOver activation hit.
    {
      const { prev, next } = runSingle('t1', TARGET);
      assert(
        next === prev,
        'B2g — moving a player to the tier it is already in is a no-op',
        `${TARGET} = [${ids(next[TARGET])}] — a repeat activation must not send ` +
          'the player to the bottom of the tier it was just moved to the top of',
      );
    }
    // A pool source has no ladder index (findIndex → -1) and keeps the append.
    {
      const { next } = runSingle('u1', TARGET);
      assert(
        ids(next[TARGET]).join(',') === 't1,t2,u1',
        'B2h — a pool (unassigned) source appends, as the drag path does',
        `${TARGET} = [${ids(next[TARGET])}]`,
      );
      assert(
        ids(next.unassigned).join(',') === 'u2',
        'B2i — the pool loses exactly the moved player',
        `unassigned = [${ids(next.unassigned)}]`,
      );
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// C. 5 — moveTierByOne stays untouched: it keeps BOTH an append and a prepend
// ═══════════════════════════════════════════════════════════════════════════

const byOne = handlerNamed('moveTierByOne');
assert(!!byOne, '5a — `moveTierByOne` exists (Tier up / Tier down bar)', 'not found');

if (byOne) {
  // Its destination key is `to`, not `target`.
  const writes = assignmentsToElement(byOne, 'next', 'to');
  const spreads = writes.flatMap((w) => spreadPositions(w.right, 'next[to]'));
  const hasAppend = spreads.some((s) => s.index === 0); // up → bottom
  const hasPrepend = spreads.some((s) => s.index > 0); // down → top
  assert(
    hasAppend && hasPrepend,
    '5b — `moveTierByOne` keeps both placements: append for up, prepend for down',
    `saw ${spreads.length} \`next[to]\` spread(s), ` +
      `append=${hasAppend} prepend=${hasPrepend} — the one already-correct path ` +
      'has been flattened in one direction',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All tier-move-placement checks passed.');
