#!/usr/bin/env node
// Mock-draft affordance + lifecycle regression test (#291, #292, D-16).
//
// WHY THIS EXISTS. All three defects this file guards were INVISIBLE to the
// suites that already existed, because all three are properties of code SHAPE
// rather than of any value a running test could read:
//
//   #291  The mock's pick path worked end to end — a reviewer drove it and got
//         four turns, every one recorded `by: "user"`. The defect was that the
//         row's trailing "Pick" label rendered only once `selected` was true,
//         so a tappable mock row was pixel-identical to the read-only Draft
//         Room row UNTIL AFTER IT HAD BEEN TAPPED. VoiceOver was told via
//         `accessibilityHint`; sighted users were not. A behavioural test
//         passes on that bug, because the behaviour was never broken.
//
//   #292  Three dead ends, each a branch that renders no way onward: the
//         completed-mock recap whose only dismissal control was hidden once
//         the mock completed, the `errorText` branch with no button in it at
//         all, and `postRefusal` — set once, never cleared, muting the card
//         for the rest of the session. Reaching any of them from a UI test
//         needs fault injection the harness does not have.
//
//   D-16  On an MFL league an owner id is a synthetic `mfl:<league>.f<fid>`.
//         The backend resolves it now, so the client's last-resort fallback
//         no longer fires — which means a test that only checks rendered
//         output would pass with the fallback still printing a raw id.
//
// So this is a structural test: it parses the real TSX with the project's own
// TypeScript and walks the JSX tree. The D-16 half is different — the ladder
// is real logic, so that function is transpiled out of the screen and CALLED,
// rather than pattern-matched.
//
// Run: node tests/check-mock-lifecycle.js
//   (or: npm run test:mock-lifecycle)

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

/** The named function declaration `name`, or undefined. */
function fnNamed(root, name) {
  return findAll(
    root,
    (n) => ts.isFunctionDeclaration(n) && n.name && n.name.getText() === name,
  )[0];
}

/** Attributes named `name` on any element whose tag is `tag`. */
function attrsOn(root, tag, name) {
  const out = [];
  for (const el of findTag(root, tag)) {
    const open = ts.isJsxSelfClosingElement(el) ? el : el.openingElement;
    for (const a of open.attributes.properties) {
      if (ts.isJsxAttribute(a) && a.name.getText() === name) out.push(a);
    }
  }
  return out;
}

/** Return statements belonging to `fn` itself, not to a nested closure. */
function ownReturns(fn) {
  return findAll(fn.body, (n) => ts.isReturnStatement(n)).filter((r) => {
    for (let p = r.parent; p && p !== fn; p = p.parent) {
      if (ts.isFunctionDeclaration(p) || ts.isArrowFunction(p) || ts.isFunctionExpression(p)) {
        return false;
      }
    }
    return true;
  });
}

const roomSrc = parse('src/screens/DraftRoomScreen.tsx');
const mockSrc = parse('src/screens/MockDraftScreen.tsx');
const panelSrc = parse('src/components/draft/MockEntryPanel.tsx');

// ═══════════════════════════════════════════════════════════════════════
// 1. #291 — the affordance is visible BEFORE the tap
// ═══════════════════════════════════════════════════════════════════════

const rowFn = fnNamed(roomSrc, 'UndraftedRowView');
assert(!!rowFn, 'UndraftedRowView found in DraftRoomScreen');

if (rowFn) {
  // The trailing slot. Exactly one conditional renders `draftRow.rowAction`,
  // and its condition may NOT depend on `selected` — that dependency IS the
  // defect: it withholds the affordance until the affordance has been used.
  const actionTernaries = findAll(
    rowFn,
    (n) =>
      ts.isConditionalExpression(n) && n.whenTrue.getText().includes('draftRow.rowAction'),
  );
  assert(
    actionTernaries.length === 1,
    'UndraftedRowView renders the action label from exactly one branch',
    `found ${actionTernaries.length}`,
  );
  if (actionTernaries.length === 1) {
    const cond = actionTernaries[0].condition.getText().trim();
    assert(
      !/\bselected\b/.test(cond),
      'The action label does NOT wait for `selected`',
      `condition is \`${cond}\` — a mock row gated on \`selected\` is pixel-identical to the read-only room row until it has already been tapped (#291)`,
    );
    assert(
      /\bactionLabel\b/.test(cond),
      'The action label is still gated on `actionLabel`',
      `condition is \`${cond}\` — the room passes no actionLabel and must stay inert`,
    );
  }

  // #277's tier information is RELOCATED, not deleted: the badge still
  // renders when there is no action label, and the label form appears on the
  // meta line for the rows whose trailing slot the action took.
  assert(
    findTag(rowFn, 'TierBadge').length === 1,
    'UndraftedRowView still renders the TierBadge (#277 not deleted)',
  );
  // The trailing slot holds ONE thing. Whatever the action label evicts has
  // to reappear on the meta line, or the affordance fix silently deletes
  // shipped information — #277's tier badge for a valued row, D7's honest
  // "No value" for a row the board cannot price.
  const meta = findAll(
    rowFn,
    (n) =>
      tagOf(n) === 'Text' &&
      ts.isJsxElement(n) &&
      n.openingElement.getText().includes('draftRow.playerMeta'),
  )[0];
  assert(!!meta, 'UndraftedRowView has a meta line');
  if (meta) {
    // LITERALS, not source text. A first cut of this check read
    // `meta.getText()` — and passed with the relocation deleted, because the
    // JSX comment explaining the relocation contains the words "No value".
    // A check satisfied by its own documentation is worse than no check.
    const literals = findAll(
      meta,
      (n) =>
        ts.isStringLiteral(n) ||
        ts.isNoSubstitutionTemplateLiteral(n) ||
        ts.isTemplateHead(n) ||
        ts.isTemplateMiddle(n) ||
        ts.isTemplateTail(n) ||
        ts.isJsxText(n),
    )
      .map((n) => (n.text || '').trim())
      .filter(Boolean)
      .join(' | ');
    assert(
      findAll(
        meta,
        (n) => ts.isElementAccessExpression(n) && n.expression.getText() === 'TIER_LABEL',
      ).length === 1,
      'The tier label is relocated onto the meta line (#277 preserved)',
      'the action label evicts the TierBadge on the user\'s turn; without this, #277\'s information is gone for exactly the rows the user is choosing between',
    );
    assert(
      literals.includes('No value'),
      'The "No value" text is relocated onto the meta line (D7 preserved)',
      `meta literals are \`${literals}\` — an unvalued row otherwise loses its only price statement while the user is on the clock`,
    );
    assert(
      findAll(meta, (n) => ts.isIdentifier(n) && n.getText() === 'actionLabel').length > 0,
      'The relocation happens only when the action label is present',
      'the read-only room row must stay byte-identical',
    );
  }

  // `selected` must still be distinguishable from `selectable`, or the
  // affordance fix has traded one ambiguity for another.
  assert(
    rowFn.getText().includes('draftRow.undraftedRowSelected'),
    'UndraftedRowView keeps a distinct selected style',
  );
}

// The caller gates the label on the turn, so the CPU-turn render is unchanged.
const actionAttrs = attrsOn(mockSrc, 'UndraftedRowView', 'actionLabel');
assert(actionAttrs.length === 1, 'MockDraftScreen passes exactly one actionLabel');
if (actionAttrs.length === 1) {
  const init = actionAttrs[0].initializer ? actionAttrs[0].initializer.getText() : '';
  assert(
    init.includes('isUserTurn'),
    'MockDraftScreen gates actionLabel on `isUserTurn`',
    `initializer is \`${init}\` — an ungated label would mark every row tappable during a CPU turn`,
  );
}

/** Every string a user can actually read in `src`. */
function renderedText(src) {
  return findAll(
    src,
    (n) =>
      ts.isJsxText(n) ||
      ts.isStringLiteral(n) ||
      ts.isNoSubstitutionTemplateLiteral(n) ||
      ts.isTemplateHead(n) ||
      ts.isTemplateMiddle(n) ||
      ts.isTemplateTail(n),
  )
    .map((n) => n.text || '')
    .join(' | ');
}

const mockText = renderedText(mockSrc);
assert(
  mockText.includes('Tap to draft'),
  'MockDraftScreen renders the "Tap to draft" header',
  'this exact string is the Maestro acceptance for #291 — Maestro can assert on text and cannot assert on a style',
);
assert(
  mockText.includes('Tap a rookie below, then confirm.'),
  'OnTheClockCard carries the one-line instruction',
);
// The room's platform guarantee must NOT be imported to make the row read as
// tappable — over a board that takes taps it reads as a promise about THIS
// board. (`check-mock-mode-marker.js` owns the "never drafts" half.)
assert(
  !mockText.includes('Picks are made on the platform'),
  'MockDraftScreen does NOT import the real room\'s platform copy',
);

// ═══════════════════════════════════════════════════════════════════════
// 2. #292 dead-end 1 — a completed mock can be dismissed, and the way
//    onward is the primary
// ═══════════════════════════════════════════════════════════════════════

const headerEffect = findAll(
  mockSrc,
  (n) =>
    ts.isCallExpression(n) &&
    n.expression.getText() === 'useLayoutEffect' &&
    n.getText().includes('headerRight'),
)[0];
assert(!!headerEffect, 'MockDraftScreen sets a headerRight');
if (headerEffect) {
  // The GUARD, not the effect body. A first cut of this check asserted only
  // that `'complete'` appeared somewhere in the effect — and it passed with
  // the guard reverted to `status === 'active'`, because the local `done`
  // that feeds the label was still declared. A check that passes on the bug
  // it names is not evidence, so the condition is resolved through its local
  // consts and asserted on its own.
  const locals = new Map();
  for (const d of findAll(headerEffect, (n) => ts.isVariableDeclaration(n))) {
    if (d.name && ts.isIdentifier(d.name) && d.initializer) {
      locals.set(d.name.getText(), d.initializer.getText());
    }
  }
  const guard = findAll(
    headerEffect,
    (n) => ts.isConditionalExpression(n) && n.whenTrue.getText().includes('mock-draft.end'),
  )[0];
  assert(!!guard, 'The dismissal control is rendered from a guarded branch');
  if (guard) {
    let cond = guard.condition.getText();
    for (const [name, init] of locals) {
      cond = cond.replace(new RegExp(`\\b${name}\\b`, 'g'), `(${init})`);
    }
    assert(
      cond.includes("'complete'"),
      'The header dismissal is reachable on a COMPLETE mock',
      `guard resolves to \`${cond}\` — shipped, the only abandon control rendered while \`status === "active"\`, so a finished mock had no way out at all (#292 dead-end 1)`,
    );
    assert(
      cond.includes("'active'"),
      'The header dismissal is still reachable mid-mock',
      `guard resolves to \`${cond}\``,
    );
  }
  assert(
    headerEffect.getText().includes('mock-draft.end'),
    'The dismissal reuses the `mock-draft.end` testID',
    'a renamed id orphans every existing flow',
  );
}

const endMockDecl = findAll(
  mockSrc,
  (n) => ts.isVariableDeclaration(n) && n.name.getText() === 'endMock',
)[0];
assert(!!endMockDecl, 'MockDraftScreen declares endMock');
if (endMockDecl) {
  const t = endMockDecl.getText();
  assert(
    t.includes('Clear this recap?'),
    'The confirm copy branches for a completed mock',
    '"End this mock?" over a finished board describes something that already happened',
  );
  assert(
    t.includes('abandonMockDraft'),
    'Both paths go through the same abandon call',
  );
}

const entryFn = fnNamed(roomSrc, 'mockEntryContent');
assert(!!entryFn, 'DraftRoomScreen declares mockEntryContent');
if (entryFn) {
  const completeReturn = ownReturns(entryFn)
    .map((r) => r.getText())
    .find((t) => t.includes('Mock complete'));
  assert(!!completeReturn, 'mockEntryContent has a complete-state branch');
  if (completeReturn) {
    const primary = /primary:\s*\{[^}]*\}/.exec(completeReturn);
    const secondary = /secondary:\s*\{[^}]*\}/.exec(completeReturn);
    assert(
      !!primary && primary[0].includes('onStart'),
      'The complete state\'s PRIMARY is the way onward',
      `primary is \`${primary ? primary[0] : 'absent'}\` — shipped it was "View recap", with starting another demoted to a ghost, so the room read as a terminus (#292)`,
    );
    assert(
      !!secondary && secondary[0].includes('onResume'),
      'The recap is demoted to secondary, not removed',
    );
    // The ids are bound to the ACTION, never the position — otherwise this
    // swap silently re-points every flow that taps them.
    assert(
      !!primary && primary[0].includes('mock-entry.run-it-back'),
      'testID `mock-entry.run-it-back` still means start-another',
    );
    assert(
      !!secondary && secondary[0].includes('mock-entry.recap'),
      'testID `mock-entry.recap` still means the recap',
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 3. #292 dead-end 2 — no reachable card state renders zero controls
// ═══════════════════════════════════════════════════════════════════════

const panelFn = fnNamed(panelSrc, 'MockEntryPanel');
assert(!!panelFn, 'MockEntryPanel component found');

if (panelFn) {
  const branches = ownReturns(panelFn).map((r) => r.getText());
  assert(branches.length >= 4, 'MockEntryPanel has its four branches', `found ${branches.length}`);

  const errorBranch = branches.find((t) => t.includes('mock-entry.error'));
  assert(!!errorBranch, 'MockEntryPanel has an errorText branch');
  assert(
    !!errorBranch && errorBranch.includes('<Button'),
    'The errorText branch renders a control',
    'shipped it rendered a bare <Text> — one failed create replaced the card with a BUTTONLESS view, and react-query holds `isError` until the next mutate/reset (#292 dead-end 2)',
  );

  const blockBranch = branches.find((t) => t.includes('block.testID'));
  assert(!!blockBranch, 'MockEntryPanel has a block branch');
  assert(
    !!blockBranch && blockBranch.includes('<Button'),
    'The block branch still states its refusal on a (dead) CTA',
    'a block is an honest refusal; the control stays disabled but the card is never blank',
  );

  // Exactly one branch may be control-free, and it must be the transient
  // loading spinner. A fifth branch added without a control fails here.
  const controlFree = branches.filter((t) => !t.includes('<Button'));
  assert(
    controlFree.length === 1 && controlFree[0].includes('mock-entry.loading'),
    'The ONLY control-free branch is the transient loading spinner',
    `control-free branches: ${controlFree.length} — every terminal state of this card must offer a way onward (#292 R-15)`,
  );
}

const retryAttrs = attrsOn(roomSrc, 'MockEntryPanel', 'retry');
assert(retryAttrs.length === 1, 'DraftRoomScreen wires the retry control');
if (retryAttrs.length === 1) {
  const t = retryAttrs[0].getText();
  assert(
    t.includes('createMock.reset()'),
    'Retry clears the sticky mutation error',
    'without `reset()` the create half of `errorText` survives the retry and the card re-renders as the same error',
  );
  assert(
    t.includes('refetch'),
    'Retry re-answers the query half of the error',
  );
  assert(
    t.includes('mock-entry.retry'),
    'Retry carries the `mock-entry.retry` testID',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 4. #292 dead-end 3 — a transient refusal cannot mute the card for the
//    session
// ═══════════════════════════════════════════════════════════════════════

const onModeAttrs = attrsOn(roomSrc, 'DraftModeToggle', 'onMode');
assert(onModeAttrs.length === 1, 'DraftRoomScreen wires exactly one onMode');
if (onModeAttrs.length === 1) {
  assert(
    onModeAttrs[0].getText().includes('setPostRefusal(null)'),
    'Re-entering Mock mode clears `postRefusal`',
    '`postRefusal` was set once and never cleared, so a single typed-empty refusal muted the Mock card for the rest of the session (#292 dead-end 3)',
  );
}

const entryCall = findAll(
  roomSrc,
  (n) => ts.isCallExpression(n) && n.expression.getText() === 'mockEntryContent',
)[0];
assert(!!entryCall, 'DraftRoomScreen calls mockEntryContent');
if (entryCall) {
  const arg = entryCall.arguments[0];
  const onStart =
    arg && ts.isObjectLiteralExpression(arg)
      ? arg.properties.find((p) => p.name && p.name.getText() === 'onStart')
      : null;
  assert(!!onStart, 'mockEntryContent receives an onStart handler');
  if (onStart) {
    const t = onStart.getText();
    assert(
      t.includes('setPostRefusal(null)'),
      'Opening the setup sheet clears `postRefusal`',
      'the user tapping Start IS the user asking again; a stale refusal must not answer for them',
    );
    assert(
      t.includes('createMock.reset()'),
      'Opening the setup sheet clears a stale create error',
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 5. D-16 — an owner is never rendered as a machine id
// ═══════════════════════════════════════════════════════════════════════
//
// Behavioural, not structural: the ladder is real logic, so it is lifted out
// of the screen, transpiled and CALLED. A pattern match here would pass on a
// ladder that returned the id unchanged.

const ownerFn = fnNamed(mockSrc, 'ownerNameOf');
const mflRe = findAll(
  mockSrc,
  (n) => ts.isVariableDeclaration(n) && n.name.getText() === 'MFL_MEMBER_RE',
)[0];
assert(!!ownerFn && !!mflRe, 'MockDraftScreen declares the owner-name ladder');

if (ownerFn && mflRe) {
  const snippet = `const ${mflRe.getText()};\n${ownerFn.getText()}\nreturn ownerNameOf;`;
  const js = ts.transpileModule(snippet, {
    compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None },
  }).outputText;
  let ownerNameOf;
  try {
    // eslint-disable-next-line no-new-func
    ownerNameOf = new Function(js)();
  } catch (e) {
    fail('ownerNameOf is evaluable in isolation', String(e));
  }
  if (typeof ownerNameOf === 'function') {
    const cases = [
      // [username, ownerId, expected, why]
      ['mattmurf77', 'mfl:62846.f0001', 'mattmurf77', 'a resolved name wins outright'],
      [null, 'mfl:62846.f0003', 'Team 0003', 'the backend omitted the key — never print the synthetic id'],
      ['', 'mfl:62846.f0003', 'Team 0003', 'an empty name is not a name'],
      ['   ', 'mfl:62846.f0012', 'Team 0012', 'whitespace is not a name'],
      [undefined, 'mfl:62846.f0003', 'Team 0003', 'undefined behaves as absent'],
      ['mfl:62846.f0003', 'mfl:62846.f0003', 'Team 0003', 'a session username that IS the raw id is filtered, not trusted'],
      [null, '867530912', '867530912', 'a Sleeper roster id keeps the shipped fallback — D-16 is the MFL half'],
    ];
    let bad = [];
    for (const [name, id, want, why] of cases) {
      let got;
      try {
        got = ownerNameOf(name, id);
      } catch (e) {
        got = `threw ${e}`;
      }
      if (got !== want) bad.push(`ownerNameOf(${JSON.stringify(name)}, ${JSON.stringify(id)}) = ${JSON.stringify(got)}, want ${JSON.stringify(want)} — ${why}`);
    }
    assert(bad.length === 0, 'ownerNameOf resolves the D-16 ladder', bad.join(' ; '));

    // The single property that matters, stated on its own so the failure
    // message names the bug rather than a table row.
    assert(
      !String(ownerNameOf(null, 'mfl:62846.f0003')).includes('mfl:'),
      'No owner render can emit a string containing "mfl:"',
      'this is the #289/D-16 defect verbatim: adjacent surfaces naming one franchise two ways, one of them a machine id',
    );
    // Zero-padding is part of the contract — the backend pads the same way,
    // and "Team 3" beside "Team 0003" is the disagreement all over again.
    assert(
      ownerNameOf(null, 'mfl:62846.f0003') === 'Team 0003',
      'The fid keeps the zero-padding it has in the id',
    );
  }
}

// Both owner-render sites go through the ladder. Fixing only the clock would
// leave a finished MFL mock printing raw ids down every round of the recap —
// the same one-site-of-two miss the backend lane found at `server.py:11474`.
const ownerCalls = findAll(
  mockSrc,
  (n) => ts.isCallExpression(n) && n.expression.getText() === 'ownerNameOf',
);
assert(
  ownerCalls.length === 2,
  'Both owner-render sites use the ladder (on-the-clock card + recap rail)',
  `found ${ownerCalls.length} call(s)`,
);
assert(
  !/owner_username\s*\?\?/.test(mockSrc.getFullText()),
  'No owner render falls back to a raw id',
  '`owner_username ?? <id>` is the raw-id path D-16 exists to close',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All mock affordance + lifecycle checks passed.');
