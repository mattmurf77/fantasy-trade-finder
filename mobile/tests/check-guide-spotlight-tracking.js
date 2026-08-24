#!/usr/bin/env node
// B1 — the Analyst spotlight must TRACK its target while the host scrolls.
//
// WHY THIS EXISTS. Operator report, 2026-08-18: the guided-onboarding
// highlight box stays at a fixed screen position while the page scrolls
// underneath it. The frame came from a one-shot `measureInWindow()` taken
// when the step activated and never again — and `measureInWindow` returns
// absolute WINDOW coordinates, so the cached frame is stale the instant the
// host ScrollView moves. There was no scroll listener anywhere in the guide
// path.
//
// The fix is small, but three of its parts exist only to stop the repair
// from being worse than the bug, and all three are invisible to `tsc`, to a
// screenshot, and to any flow that does not scroll mid-tour. That is what
// this file pins.
//
// WHAT IS PINNED, and the sabotage each assertion detects:
//
//   1  The host↔guide seam: `guideTargets.ts` exports a subscribe/notify
//      pair over a Set, so a host announces movement without importing guide
//      internals and an unguided screen pays an empty-Set walk. Sabotage:
//      make `notifyGuideTargetsMoved` reach into the guide store directly,
//      or drop the unsubscribe from the subscribe return → a listener leak
//      that re-measures a dead step forever.
//   2  The overlay actually subscribes, from an effect, and TEARS DOWN: the
//      unsubscribe runs and the pending frame is cancelled. Sabotage: drop
//      the cleanup — every step change stacks another live subscriber.
//   3  The handler re-measures through `measureGuideTarget` and holds a
//      frame handle it cancels. Sabotage: measure synchronously on every
//      scroll event (16 ms) with no coalescing.
//   4  **A null re-measure KEEPS the last good frame.** `measureGuideTarget`
//      resolves `null` on its 250 ms timeout and for an unmounted node, both
//      of which happen mid-fling. Sabotage: `.then(setLocalFrame)` with no
//      guard — the spotlight blinks out mid-scroll, and on the v2 path the
//      step re-enters the degrade branch and re-fires `guide_step_shown`,
//      double-counting a step the user saw once. Nothing else catches an
//      analytics double-emit.
//   5  The tracking effect touches NO spotlight-outcome API — no store
//      `setState`, no `spotlight` transition, no `track()`. Sabotage: "fix"
//      a failed re-measure by degrading, i.e. assertion 4 wearing a
//      different hat.
//   6  `useGuide.trackSpotlightFrame` is frame-ONLY: it writes
//      `spotlightFrame` and nothing else. Sabotage: have it also set
//      `spotlight` or call `commitShown` — same double-emit, one file over.
//   7  **The band placement is LATCHED per step.** `targetInBottomBand`
//      re-solves every render; once the frame tracks scroll, the avatar and
//      bubble would flip between the top band and the bottom band mid-fling.
//      Sabotage: `const atTop = targetInBottomBand` (the pre-fix line). Also
//      pinned: the latch is written only once a frame RESOLVED — latching on
//      the first render would freeze the pre-measure `false` and park the
//      bubble on top of a bottom-band cutout — and it is reset per step.
//   8  **The cutout math is RUN, not described.** Two failures, one block:
//      a target FULLY out of the viewport must render no cutout at all
//      (sabotage: restore `cutout = frame ? {…} : null` — inert before the
//      fix, a ring smeared against y=0 after it), and a target PARTIALLY out
//      must have its SPAN clamped by the same delta its ORIGIN was clamped
//      by (sabotage: `height: frame.height + 16` — the origin sticks at 0
//      while the height stays full, freezing an oversized ring against the
//      edge for the whole transit). The offscreen predicate and the cutout
//      expression are lifted from the source and evaluated over frames at
//      every edge, so neither is pinned by shape alone — shape is what let
//      the raw-span version through the first time.
//   9  Every host that announces movement does it from an `onScroll` on an
//      element that also sets `scrollEventThrottle`, and neither is gated on
//      a flag. Without the throttle RN fires onScroll about once per second
//      and the spotlight lurches; behind a flag it tracks for some users
//      only. Sabotage: fold the notifier into TradesScreen's existing
//      `declineReasonsOn ? … : undefined` pair. File-agnostic over
//      `src/screens`, so a host added later is covered.
//
//  11  **The band is ADJACENT to its cutout, and the solver is RUN.** Added
//      2026-08-22 from the device pass: the shipped rule put the band at a
//      fixed `top: 54` whenever the target's bottom edge fell below 60 % of
//      the window, which is every calculator beat after the outlook — the
//      operator saw five correct rings with no Analyst beside any of them, and
//      the avatar reappeared on the header-less deck. `solveBandPlacement` is
//      lifted out of the source, transpiled and executed over a sweep of ring
//      positions and band heights; the invariants are that the band never
//      overlaps its ring and a top-anchored band always clears the top inset.
//      Sabotage: `{ top: 54 }` in the style, or a solver that ignores
//      `insets.top` → red. Assertion 7's latch moved with it: it now holds the
//      whole `{from, offset}` placement, so 7a–7f are RE-POINTED at `place`,
//      not deleted.
//  12  The calculator announces movement from `onLayout` and
//      `onContentSizeChange` as well as `onScroll` — its content grows after
//      first paint (rosters land, the outlook receipt swaps with its fallback)
//      and that moves every target below it with no scroll event at all.
//  13  Scroll-into-view: the `registerGuideScroller` seam exists, the overlay
//      asks for a scroller from an effect (never during render), and it does
//      so at most ONCE per step. Sabotage: drop the `scrolledForRef` latch and
//      the scroll notifies → re-measures → re-scrolls for the life of the step.
//
// Structural, not textual: parses the shipped source with the project's own
// TypeScript and walks the AST, like check-single-pin-actions.js — a grep
// cannot tell a guarded setter from an unguarded one, and that distinction
// (assertion 4) is the whole risk of this change. Seed-independent: no
// simulator, no backend, no flag fixture.
//
// Run: node tests/check-guide-spotlight-tracking.js

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

const ROOT = path.join(__dirname, '..');
const TARGETS_REL = 'src/state/guideTargets.ts';
const OVERLAY_REL = 'src/components/AnalystGuide.tsx';
const STORE_REL = 'src/state/useGuide.ts';
const SCREENS_DIR = path.join(ROOT, 'src', 'screens');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}
function fail(name, detail) {
  assert(false, name, detail);
}

// ── Parsing ────────────────────────────────────────────────────────────────

const _cache = new Map();
function parse(rel) {
  if (_cache.has(rel)) return _cache.get(rel);
  const abs = path.join(ROOT, rel);
  const sf = ts.createSourceFile(
    abs,
    fs.readFileSync(abs, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  _cache.set(rel, sf);
  return sf;
}

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

function txt(sf, n) {
  return n ? n.getText(sf) : '';
}

function flat(sf, n) {
  return txt(sf, n).replace(/\s+/g, ' ').trim();
}

function where(sf, n) {
  const rel = path.relative(ROOT, sf.fileName);
  return `${rel}:${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1}`;
}

/** Nearest enclosing node satisfying `pred`. */
function enclosing(node, pred) {
  let cur = node.parent;
  while (cur) {
    if (pred(cur)) return cur;
    cur = cur.parent;
  }
  return null;
}

/** Exact-name identifiers anywhere under `root`. Exact-match on purpose:
 *  `spotlight` must never match `spotlightTarget`. */
function referencesIdentifier(sf, root, name) {
  return findAll(root, (n) => ts.isIdentifier(n) && n.text === name).length > 0;
}

const isCallTo = (n, name) =>
  ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === name;

function callsTo(root, name) {
  return findAll(root, (n) => isCallTo(n, name));
}

/** The variable declaration named `name`, anywhere in the file. */
function declOf(sf, name) {
  return findAll(
    sf,
    (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name,
  )[0];
}

const isJsxEl = (n) => ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n);

function attr(sf, el, name) {
  if (!isJsxEl(el)) return undefined;
  return el.attributes.properties.find(
    (a) => ts.isJsxAttribute(a) && a.name.getText(sf) === name,
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 1 — the seam: subscribe/notify over a Set in guideTargets.ts
// ═══════════════════════════════════════════════════════════════════════════

const targetsSf = parse(TARGETS_REL);

const exportedFns = new Map(
  findAll(
    targetsSf,
    (n) =>
      ts.isFunctionDeclaration(n) &&
      !!n.name &&
      !!n.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword),
  ).map((n) => [n.name.text, n]),
);

const subscribeFn = exportedFns.get('subscribeGuideTargetsMoved');
const notifyFn = exportedFns.get('notifyGuideTargetsMoved');

assert(
  !!subscribeFn && !!notifyFn,
  '1a — guideTargets exports subscribeGuideTargetsMoved + notifyGuideTargetsMoved',
  'the host↔guide seam is gone; hosts would have to import guide internals',
);

if (subscribeFn && notifyFn) {
  // The listener Set — the "no subscriber ⇒ no-op" guarantee.
  const setDecl = findAll(
    targetsSf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      !!n.initializer &&
      /^new Set\b/.test(flat(targetsSf, n.initializer)),
  )[0];

  assert(
    !!setDecl,
    '1b — the listeners live in a module-level Set (no subscriber ⇒ empty walk)',
    'no `new Set(...)` binding in ' + TARGETS_REL,
  );

  if (setDecl) {
    const setName = setDecl.name.text;
    assert(
      /\.add\(/.test(flat(targetsSf, subscribeFn)) &&
        referencesIdentifier(targetsSf, subscribeFn, setName),
      `1c — subscribe adds to \`${setName}\``,
      flat(targetsSf, subscribeFn),
    );
    // The returned unsubscribe: without it a step change leaks a listener
    // that keeps re-measuring a target nobody is pointing at.
    const ret = findAll(subscribeFn, (n) => ts.isReturnStatement(n))[0];
    const retIsFn =
      !!ret && !!ret.expression &&
      (ts.isArrowFunction(ret.expression) || ts.isFunctionExpression(ret.expression));
    assert(
      retIsFn && /\.delete\(/.test(flat(targetsSf, ret.expression)),
      '1d — subscribe returns an unsubscribe that deletes the listener',
      ret ? `returns: ${flat(targetsSf, ret.expression)}` : 'no return statement',
    );
    assert(
      referencesIdentifier(targetsSf, notifyFn, setName) &&
        targetsSf.statements.length > 0,
      `1e — notify iterates \`${setName}\` and nothing else`,
      flat(targetsSf, notifyFn),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 2 + 3 — the overlay subscribes from an effect, coalesces, and tears down
// ═══════════════════════════════════════════════════════════════════════════

const overlay = parse(OVERLAY_REL);

const subCalls = callsTo(overlay, 'subscribeGuideTargetsMoved');
assert(
  subCalls.length === 1,
  '2a — AnalystGuide subscribes to the move notifier exactly once',
  `${subCalls.length} call(s) to subscribeGuideTargetsMoved — the overlay is ` +
    'the only thing that knows which target is active',
);

const trackingEffect =
  subCalls.length === 1
    ? enclosing(subCalls[0], (n) => isCallTo(n, 'useEffect'))
    : null;

assert(
  !!trackingEffect,
  '2b — the subscription is owned by a useEffect (so it can be cleaned up)',
  'subscribeGuideTargetsMoved is called outside any useEffect — a subscription ' +
    'created during render is never torn down',
);

if (trackingEffect) {
  const effectFn = trackingEffect.arguments[0];
  const cleanup = findAll(effectFn, (n) => ts.isReturnStatement(n))
    .map((r) => r.expression)
    .find((e) => e && (ts.isArrowFunction(e) || ts.isFunctionExpression(e)));

  // The binding that holds the unsubscribe.
  const unsubDecl = findAll(
    effectFn,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      !!n.initializer &&
      isCallTo(n.initializer, 'subscribeGuideTargetsMoved'),
  )[0];

  assert(
    !!cleanup && !!unsubDecl && referencesIdentifier(overlay, cleanup, unsubDecl.name.text),
    '2c — the effect cleanup calls the unsubscribe',
    cleanup ? `cleanup: ${flat(overlay, cleanup)}` : 'the effect returns no cleanup',
  );

  assert(
    !!cleanup && referencesIdentifier(overlay, cleanup, 'cancelAnimationFrame'),
    '2d — the cleanup cancels a pending re-measure frame',
    'an in-flight rAF that fires after teardown re-measures a step that ended',
  );

  assert(
    referencesIdentifier(overlay, effectFn, 'requestAnimationFrame'),
    '3a — the re-measure is coalesced onto an animation frame',
    'measuring straight off every onScroll event is a measure every 16 ms',
  );

  assert(
    callsTo(effectFn, 'measureGuideTarget').length > 0,
    '3b — the handler re-measures through measureGuideTarget',
    'the notifier must trigger a real re-measure, not a cached recompute',
  );

  // ── 4 — a null re-measure keeps the last good frame ─────────────────────
  // The `.then` on the re-measure: its callback must bail on a falsy frame
  // BEFORE it reaches any frame setter.
  const thenCb = findAll(
    effectFn,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isPropertyAccessExpression(n.expression) &&
      n.expression.name.text === 'then' &&
      isCallTo(n.expression.expression, 'measureGuideTarget'),
  )
    .map((n) => n.arguments[0])
    .find((a) => a && ts.isArrowFunction(a));

  if (!thenCb) {
    fail(
      '4 — the re-measure resolution is a `.then` on measureGuideTarget',
      'could not locate the resolution callback; if the shape changed, this ' +
        'assertion must be re-pointed, NOT deleted — it is the analytics guard',
    );
  } else {
    const param = thenCb.parameters[0] && ts.isIdentifier(thenCb.parameters[0].name)
      ? thenCb.parameters[0].name.text
      : null;
    const setters = findAll(
      thenCb,
      (n) => isCallTo(n, 'setLocalFrame') || isCallTo(n, 'trackSpotlightFrame'),
    );
    assert(
      setters.length > 0,
      '4a — the resolution writes the tracked frame',
      'nothing updates the frame — the spotlight still does not move',
    );
    const firstSetter = setters.length
      ? Math.min(...setters.map((n) => n.getStart(overlay)))
      : Infinity;
    // The property is "a falsy frame never reaches a setter". Two shapes
    // satisfy it and both are pinned: an early `if (!f) return;` before every
    // setter, or every setter nested inside a positive `if (f) { … }`.
    // Asserting only the first shape would fail a correct refactor.
    const falsyBail = findAll(thenCb, (n) => ts.isIfStatement(n)).find(
      (n) =>
        !!param &&
        new RegExp(`!\\s*${param}\\b|${param}\\s*===?\\s*null`).test(
          flat(overlay, n.expression),
        ) &&
        /\breturn\b/.test(flat(overlay, n.thenStatement)) &&
        n.getStart(overlay) < firstSetter,
    );
    const POSITIVE = param
      ? new RegExp(`^(!!)?${param}$|^${param}\\s*!==?\\s*null$`)
      : /$^/;
    const insidePositiveGuard = (setter) => {
      for (let n = setter; n && n !== thenCb; n = n.parent) {
        const p = n.parent;
        if (p && ts.isIfStatement(p) && p.thenStatement === n) {
          if (POSITIVE.test(flat(overlay, p.expression))) return true;
        }
      }
      return false;
    };
    assert(
      !!falsyBail || (setters.length > 0 && setters.every(insidePositiveGuard)),
      `4b — a null re-measure KEEPS the last good frame (no setter is ` +
        `reachable with a falsy frame)`,
      'measureGuideTarget resolves null on its 250 ms timeout and for an ' +
        'unmounted node; writing that null blanks a live spotlight and, on the ' +
        'v2 path, re-fires guide_step_shown as degraded',
    );
  }

  // ── 5 — the tracking effect touches no spotlight-outcome API ────────────
  const FORBIDDEN = [
    'spotlight',
    'setSpotlight',
    'commitShown',
    'setState',
    'track',
    'dismissActiveStep',
    'advance',
    'skipStep',
  ];
  const seen = FORBIDDEN.filter((id) => referencesIdentifier(overlay, effectFn, id));
  assert(
    seen.length === 0,
    '5 — the tracking effect makes no spotlight-state or analytics call',
    `references ${seen.join(', ')} — a re-measure is a new POSITION, never a ` +
      'new outcome; degrading from here double-counts guide_step_shown',
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 6 — useGuide.trackSpotlightFrame is frame-ONLY (the v2 path)
// ═══════════════════════════════════════════════════════════════════════════

const store = parse(STORE_REL);

const trackImpl = findAll(
  store,
  (n) =>
    ts.isPropertyAssignment(n) &&
    ts.isIdentifier(n.name) &&
    n.name.text === 'trackSpotlightFrame',
)[0];

if (!trackImpl) {
  fail(
    '6 — useGuide implements `trackSpotlightFrame`',
    'the v2 engine frame has no frame-only setter, so the v2 path either does ' +
      'not track or tracks through the outcome-owning API',
  );
} else {
  const setCalls = callsTo(trackImpl.initializer, 'set');
  assert(
    setCalls.length > 0,
    '6a — trackSpotlightFrame writes store state',
    flat(store, trackImpl.initializer),
  );
  const keys = [];
  for (const c of setCalls) {
    const arg = c.arguments[0];
    if (arg && ts.isObjectLiteralExpression(arg)) {
      for (const p of arg.properties) if (p.name) keys.push(p.name.getText(store));
    } else {
      keys.push(`(non-literal: ${flat(store, arg)})`);
    }
  }
  assert(
    keys.length > 0 && keys.every((k) => k === 'spotlightFrame'),
    '6b — it sets `spotlightFrame` and NOTHING else',
    `sets: ${keys.join(', ')} — touching \`spotlight\` here re-runs the outcome ` +
      'contract for a step that already reported one',
  );
  const bad = ['commitShown', 'track', 'patchOnboardingState', 'terminate', 'noteSuppressed']
    .filter((id) => referencesIdentifier(store, trackImpl.initializer, id));
  assert(
    bad.length === 0,
    '6c — it emits nothing and mutates no onboarding memory',
    `references ${bad.join(', ')}`,
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// 7 — the band placement is latched per step
// ═══════════════════════════════════════════════════════════════════════════

// 2026-08-22 (#384 device report 3): the latched value is no longer a
// boolean band choice but the whole PLACEMENT — `{from, offset}` — because the
// band is now sited adjacent to its cutout rather than parked at a fixed
// `top: 54`. The latch property is unchanged and is what these assertions are
// for; they are re-pointed at `place`, not deleted.
const placeDecl = declOf(overlay, 'place');

{
  const atTopDecl = declOf(overlay, 'atTop');
  assert(
    !!atTopDecl && !!atTopDecl.initializer &&
      flat(overlay, atTopDecl.initializer) !== 'targetInBottomBand',
    '7a — `atTop` is not the bare re-solving predicate',
    'const atTop = targetInBottomBand — this is the pre-fix line: with a ' +
      'tracking frame the avatar and bubble flip bands mid-fling',
  );
  // The 60 %-of-the-window rule IS the report-3 defect: it is what sent every
  // calculator beat after the outlook to `top: 54`, on a screen with a native
  // header, far from the ring it was explaining.
  assert(
    !declOf(overlay, 'targetInBottomBand'),
    '7a2 — the 60 %-of-the-window band predicate is gone entirely',
    'restoring it re-creates the fixed-band placement the device pass rejected',
  );
}

if (!placeDecl || !placeDecl.initializer) {
  fail('7 — `place` is declared in the overlay', 'declaration not found');
} else {
  const init = placeDecl.initializer;
  const initText = flat(overlay, init);

  // The latch itself: a ref read from `place`'s initializer — or, since the
  // live-offset change (2026-08-22, the band must FOLLOW a ring that
  // re-measures after the push transition), from the `latched` declaration
  // that `place` derives from. Either way the side comes from a ref.
  const latchedDecl = declOf(overlay, 'latched');
  const refRead =
    findAll(init, (n) => ts.isPropertyAccessExpression(n) && n.name.text === 'current')[0] ||
    (latchedDecl && latchedDecl.initializer &&
      referencesIdentifier(overlay, init, 'latched') &&
      findAll(latchedDecl.initializer,
        (n) => ts.isPropertyAccessExpression(n) && n.name.text === 'current')[0]);
  assert(
    !!refRead,
    '7b — `place` reads a latch ref',
    `saw: ${initText}`,
  );

  if (refRead) {
    const refName = flat(overlay, refRead.expression).replace(/[?.].*$/, '');
    const writes = findAll(
      overlay,
      (n) =>
        ts.isBinaryExpression(n) &&
        n.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
        /\.current$/.test(flat(overlay, n.left)) &&
        flat(overlay, n.left).startsWith(refName),
    );
    const latchWrite = writes.find((n) => ts.isObjectLiteralExpression(n.right));
    assert(
      !!latchWrite,
      `7c — \`${refName}.current\` is latched to a value object`,
      'no object write — nothing is being held across renders',
    );
    if (latchWrite) {
      // Guarded on a resolved frame: latching on the first render would
      // freeze the pre-measure `false` and leave the bubble over the cutout.
      const guard = enclosing(latchWrite, (n) => ts.isIfStatement(n));
      assert(
        !!guard && referencesIdentifier(overlay, guard.expression, 'frame'),
        '7d — the latch is written only once a frame RESOLVED',
        guard
          ? `guard: ${flat(overlay, guard.expression)}`
          : 'the write is unguarded — it captures the pre-measure placement',
      );
      // Keyed on the step, so a re-shown step does not inherit a stale band.
      assert(
        /\bid\b/.test(flat(overlay, latchWrite.right)),
        '7e — the latch is keyed on the step id',
        `saw: ${flat(overlay, latchWrite.right)}`,
      );
      // And only on an ON-SCREEN cutout: the first frame of a step can
      // resolve while the push transition still has the screen off to the
      // right, which solves to the bottom band — latching that pins the
      // wrong SIDE for the life of the step (simulator, 2026-08-22).
      assert(
        !!guard && referencesIdentifier(overlay, guard.expression, 'cutout'),
        '7h — the latch is written only once the cutout is ON-screen',
        guard ? `guard: ${flat(overlay, guard.expression)}` : 'no guard',
      );
      // The OFFSET is live whenever the solver agrees on the side — the band
      // must follow a ring that re-measures (post-transition, scroll).
      assert(
        /latched\.from === solved\.from \? solved/.test(flat(overlay, placeDecl.initializer)),
        '7g — the placement offset is live when the latched side agrees with the solver',
        `saw: ${flat(overlay, placeDecl.initializer)}`,
      );
    }
    assert(
      writes.some((n) => n.right.kind === ts.SyntaxKind.NullKeyword),
      `7f — \`${refName}.current\` is reset on step change`,
      'without a reset the next step inherits the previous step\'s band',
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 8 — the cutout: full exit drops the scrim, partial exit clamps the SPAN
// ═══════════════════════════════════════════════════════════════════════════
//
// Two distinct failures live here, and the first version of this check saw
// neither of them properly. It asserted only that the cutout conditional
// negated *some* predicate mentioning `frame`, `winH` and `winW` — a shape,
// not the math — and it was written against a version that clamped the ORIGIN
// (`Math.max(0, …)` on x/y) while passing the SPAN through raw
// (`height: frame.height + 16`). That combination is the artifact it was
// supposed to prevent: a target mid-transit past the top edge keeps its full
// height while its top sticks at 0, so the ring freezes oversized and glued
// to the edge for the whole transit — the dominant case, scrolling past a
// full-height deck card. So the arithmetic is now EXECUTED: the offscreen
// predicate and the cutout expression are lifted out of the real TSX and run
// over frames at every edge.

const cutoutDecl = declOf(overlay, 'cutout');

if (!cutoutDecl || !cutoutDecl.initializer || !ts.isConditionalExpression(cutoutDecl.initializer)) {
  fail(
    '8 — `cutout` is a conditional on the frame',
    'declaration not found or no longer a conditional expression',
  );
} else {
  const cond = cutoutDecl.initializer.condition;
  // The condition must NEGATE a predicate that is itself derived from the
  // frame and BOTH window dimensions — i.e. a real viewport test, not a
  // rename of `frame`.
  const negatedNames = findAll(
    cond,
    (n) =>
      ts.isPrefixUnaryExpression(n) &&
      n.operator === ts.SyntaxKind.ExclamationToken &&
      ts.isIdentifier(n.operand),
  ).map((n) => n.operand.text);

  const offscreen = negatedNames
    .map((name) => ({ name, decl: declOf(overlay, name) }))
    .find(({ decl }) => {
      if (!decl || !decl.initializer) return false;
      const t = flat(overlay, decl.initializer);
      return (
        referencesIdentifier(overlay, decl.initializer, 'frame') &&
        /\bwinH\b/.test(t) &&
        /\bwinW\b/.test(t)
      );
    });

  assert(
    !!offscreen,
    '8a — the scrim/ring is dropped when the tracked frame leaves the viewport',
    `cutout condition is \`${flat(overlay, cond)}\` — no negated viewport ` +
      'predicate over the frame and both window dimensions. Clamping instead ' +
      '(Math.max(0, …) on x/y, nothing on width/height) smears the ring flat ' +
      'against the screen edge once the frame tracks scroll',
  );

  // ── 8b+ — run the real arithmetic ───────────────────────────────────────
  // Lift the offscreen predicate and the cutout expression out of the source
  // and evaluate them with `frame`, `winW`, `winH` injected. Plain JS: no type
  // annotations in either expression, so no transpile step is needed.
  let computeCutout = null;
  if (offscreen && offscreen.decl && offscreen.decl.initializer) {
    try {
      // eslint-disable-next-line no-new-func
      computeCutout = new Function(
        'frame',
        'winW',
        'winH',
        `const ${offscreen.name} = ${offscreen.decl.initializer.getText(overlay)};\n` +
          `return ${cutoutDecl.initializer.getText(overlay)};`,
      );
    } catch (e) {
      computeCutout = null;
      fail('8b — the cutout math is liftable and runnable', String(e && e.message));
    }
  }

  if (computeCutout) {
    const W = 390;
    const H = 844;
    // If the cutout ever depends on something beyond the frame and the window
    // dimensions (a safe-area inset, say), the lift throws — fail loudly with
    // the reason instead of a bare stack trace, and re-point the lift rather
    // than deleting these assertions.
    let liftBroke = null;
    const run = (frame) => {
      try {
        return computeCutout(frame, W, H);
      } catch (e) {
        liftBroke = liftBroke || String((e && e.message) || e);
        return undefined;
      }
    };
    const PAD = 8; // the source's half-padding; the box is inset 8 on each side

    // Fully on screen: a plain 8pt-inset box, nothing clamped.
    {
      const f = { x: 40, y: 200, width: 300, height: 100 };
      const c = run(f);
      assert(
        !!c &&
          c.left === f.x - PAD &&
          c.top === f.y - PAD &&
          c.width === f.width + 2 * PAD &&
          c.height === f.height + 2 * PAD,
        '8b — an on-screen frame gets the full padded box',
        JSON.stringify(c),
      );
    }

    // THE REGRESSION. Mid-transit past the TOP: the origin clamps to 0, so the
    // span must shrink by the same delta — otherwise the ring keeps its full
    // height with its top pinned at 0 and hangs there, oversized, for the
    // whole transit. Expressed as the invariant the naive version breaks: the
    // cutout's BOTTOM edge still tracks the target's bottom edge.
    {
      const f = { x: 40, y: -50, width: 300, height: 100 };
      const c = run(f);
      assert(!!c, '8c — a partially-visible frame still gets a cutout', JSON.stringify(c));
      assert(
        !!c && c.top === 0,
        '8d — the origin is clamped to the top edge',
        JSON.stringify(c),
      );
      assert(
        !!c && c.top + c.height === f.y + f.height + PAD,
        '8e — the SPAN is reduced by the origin-clamp delta (height, top edge)',
        `top=${c && c.top} height=${c && c.height}; the cutout's bottom edge must ` +
          `stay at ${f.y + f.height + PAD}. Passing \`frame.height + 16\` through raw ` +
          `gives ${f.height + 2 * PAD} — a full-height ring frozen against y=0`,
      );
      assert(
        !!c && c.height < f.height + 2 * PAD,
        '8f — the clamped height is strictly smaller than the unclamped span',
        JSON.stringify(c),
      );
    }

    // Same rule on the horizontal axis — the left/width pair must not be the
    // half that got fixed.
    {
      const f = { x: -30, y: 200, width: 300, height: 100 };
      const c = run(f);
      assert(
        !!c && c.left === 0 && c.left + c.width === f.x + f.width + PAD,
        '8g — the SPAN is reduced by the origin-clamp delta (width, left edge)',
        `left=${c && c.left} width=${c && c.width}; expected right edge ` +
          `${f.x + f.width + PAD}`,
      );
    }

    // A frame larger than the window, or hanging off the far edges, must stay
    // inside the viewport and never go negative — the scrim panels are laid
    // out from these numbers.
    {
      const cases = [
        { x: 300, y: 800, width: 300, height: 300 }, // off the right + bottom
        { x: -20, y: -20, width: 2000, height: 2000 }, // bigger than the window
      ];
      for (const f of cases) {
        const c = run(f);
        const ok =
          !!c &&
          c.left >= 0 &&
          c.top >= 0 &&
          c.width >= 0 &&
          c.height >= 0 &&
          c.left + c.width <= W &&
          c.top + c.height <= H;
        assert(
          ok,
          `8h — the cutout stays inside the viewport and non-negative (${JSON.stringify(f)})`,
          JSON.stringify(c),
        );
      }
    }

    // FULL EXIT still drops the scrim entirely — the other half of the fix,
    // now proven by outcome rather than by the shape of the condition.
    {
      const exits = {
        'above the viewport': { x: 40, y: -200, width: 300, height: 100 },
        'below the viewport': { x: 40, y: H + 10, width: 300, height: 100 },
        'left of the viewport': { x: -400, y: 200, width: 300, height: 100 },
        'right of the viewport': { x: W + 10, y: 200, width: 300, height: 100 },
      };
      for (const [label, f] of Object.entries(exits)) {
        assert(
          run(f) === null,
          `8i — a frame ${label} renders NO cutout`,
          `got ${JSON.stringify(run(f))} — a clamped-to-zero box still paints ` +
            'four scrim panels and a ring against the edge',
        );
      }
      assert(run(null) === null, '8j — no frame, no cutout');
    }

    assert(
      liftBroke === null,
      '8k — the cutout math still depends only on the frame and the window',
      `${liftBroke} — the lift needs re-pointing (a new free variable), NOT ` +
        'deleting: 8b-8j are the only things that execute this arithmetic',
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 9 — hosts announce movement from a throttled onScroll
// ═══════════════════════════════════════════════════════════════════════════

const hostRels = fs
  .readdirSync(SCREENS_DIR)
  .filter((f) => f.endsWith('.tsx'))
  .map((f) => path.join('src', 'screens', f))
  .filter((rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8').includes('notifyGuideTargetsMoved'));

assert(
  hostRels.length > 0,
  '9a — at least one screen announces target movement',
  'nothing calls notifyGuideTargetsMoved — the notifier has no producer and ' +
    'the spotlight never tracks anything',
);

for (const rel of hostRels) {
  const sf = parse(rel);
  const wired = findAll(sf, (n) => {
    if (!isJsxEl(n)) return false;
    const onScroll = attr(sf, n, 'onScroll');
    return (
      !!onScroll &&
      !!onScroll.initializer &&
      referencesIdentifier(sf, onScroll.initializer, 'notifyGuideTargetsMoved')
    );
  });
  assert(
    wired.length > 0,
    `9b — ${rel} calls the notifier from an onScroll handler`,
    'the import is there but no scroll container is wired to it',
  );
  for (const el of wired) {
    const throttle = attr(sf, el, 'scrollEventThrottle');
    assert(
      !!throttle,
      `9c — ${where(sf, el)} sets scrollEventThrottle alongside onScroll`,
      'without it iOS fires onScroll roughly once per second and the ' +
        'spotlight lurches instead of tracking',
    );
    // Neither the handler nor the throttle may fall back to `undefined` on
    // some other flag. TradesScreen's pre-existing pair is gated on
    // `declineReasonsOn`; folding the notifier INTO that ternary would ship
    // a guide that tracks only for users in an unrelated experiment.
    const gated = [attr(sf, el, 'onScroll'), throttle]
      .filter((a) => a && a.initializer && /\bundefined\b/.test(flat(sf, a.initializer)));
    assert(
      gated.length === 0,
      `9d — ${where(sf, el)} wires the notifier unconditionally`,
      gated.length
        ? `${gated[0].name.getText(sf)}=${flat(sf, gated[0].initializer)} — falls ` +
          'back to undefined, so the guide hears no scroll for anyone off that flag'
        : undefined,
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 10 — every scrolling guide HOST announces movement
// ═══════════════════════════════════════════════════════════════════════════
//
// Assertion 9 checks the hosts that already opted in. This one finds the ones
// that SHOULD have: any file under src/ that registers a guide target AND owns
// a ScrollView is a page whose spotlight can go stale under a scroll, and the
// #384 calculator was exactly that file — it registered six targets, scrolled,
// and never announced, so every beat below the fold pointed at the wrong place
// the moment the user moved the page.
//
// The rule is deliberately mechanical (register + ScrollView ⇒ notify) rather
// than a hand-kept list, so a screen added later is covered on the day it is
// written. Exceptions are ENUMERATED here with a reason, never by weakening
// the predicate — a rule with a silent hole is worse than no rule.

const SCROLL_HOST_EXCEPTIONS = {
  // The ONLY ScrollView in this file is inside the team-picker `Modal`
  // (`calc.team-sheet`) — a bottom sheet with no guide target in it, mounted
  // over a page that is not scrolling while it is open. The page's own scroll
  // container lives in TradeCalculatorScreen, which does announce.
  'src/components/InLeagueCalculator.tsx':
    'its only ScrollView is inside the team-picker Modal and contains no guide target',
};

function walkTsFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkTsFiles(abs));
    else if (/\.tsx?$/.test(entry.name)) out.push(abs);
  }
  return out;
}

{
  const SRC = path.join(ROOT, 'src');
  const shouldNotify = walkTsFiles(SRC)
    .map((abs) => path.relative(ROOT, abs))
    .filter((rel) => {
      const text = fs.readFileSync(path.join(ROOT, rel), 'utf8');
      return text.includes('registerGuideTarget(') && text.includes('<ScrollView');
    });

  assert(
    shouldNotify.length > 0,
    '10a — the register+scroll scan found files to check',
    'a renamed API would make this rule vacuous',
  );

  for (const rel of shouldNotify) {
    const excuse = SCROLL_HOST_EXCEPTIONS[rel];
    const text = fs.readFileSync(path.join(ROOT, rel), 'utf8');
    const notifies = text.includes('notifyGuideTargetsMoved');
    if (excuse) {
      assert(
        !notifies,
        `10b — ${rel} is listed as an exception and still does not announce`,
        `it now calls notifyGuideTargetsMoved — delete its exception entry (${excuse})`,
      );
      continue;
    }
    assert(
      notifies,
      `10c — ${rel} registers a guide target, owns a ScrollView, and announces movement`,
      'the spotlight caches an ABSOLUTE window frame; without an onScroll '
        + 'notifier every target below the fold is highlighted at its stale '
        + 'position the moment the page moves. Add onScroll + '
        + 'scrollEventThrottle, or add a reasoned entry to '
        + 'SCROLL_HOST_EXCEPTIONS',
    );
  }

  // The two shipped hosts must stay in the set — if either stops registering
  // targets or stops scrolling, this rule quietly covers one file instead of
  // three and nobody finds out.
  for (const rel of ['src/screens/TradesScreen.tsx',
                     'src/screens/LeagueSummaryScreen.tsx',
                     'src/screens/TradeCalculatorScreen.tsx']) {
    assert(
      shouldNotify.includes(rel),
      `10d — ${rel} is still in scope for the register+scroll rule`,
      'it no longer registers a guide target or no longer owns a ScrollView — '
        + 'confirm that is intended before accepting this',
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 11 — the band is ADJACENT to its cutout (#384 device report 3)
// ═══════════════════════════════════════════════════════════════════════════
//
// WHY. Operator report, 2026-08-22, build 1.16.0 (126): five consecutive
// calculator beats drew a correct spotlight ring with no Analyst beside it,
// and the avatar reappeared the moment the tour reached the deck. The shipped
// solver parked the band at a fixed `top: 54` whenever the target's bottom
// edge fell below 60 % of the window — which is every calculator beat after
// the outlook, on the one screen in the pair that carries a native-stack
// header. Adjacency deletes the whole class: the band is next to the ring, or
// it is the bottom band, and it is never in the top inset.
//
// The solver is EXECUTED, not described — same posture as section 8, and for
// the same reason: a shape assertion cannot tell a clamp from a placement.
// Sabotage: return `{from:'top', offset: 54}` unconditionally → red.

{
  const fnDecl = findAll(
    overlay,
    (n) => ts.isFunctionDeclaration(n) && !!n.name && n.name.text === 'solveBandPlacement',
  )[0];

  if (!fnDecl) {
    fail(
      '11a — the overlay exports a `solveBandPlacement` solver',
      'the adjacency solver is gone; the band is placed inline again and ' +
        'nothing here can execute it',
    );
  } else {
    const consts = ['BAND_GAP', 'BAND_EDGE', 'BAND_BOTTOM']
      .map((name) => {
        const d = declOf(overlay, name);
        return d && d.initializer ? `const ${name} = ${d.initializer.getText(overlay)};` : '';
      })
      .join('\n');
    assert(
      /BAND_GAP/.test(consts) && /BAND_EDGE/.test(consts) && /BAND_BOTTOM/.test(consts),
      '11b — the solver\'s three constants are module-level and liftable',
      consts,
    );

    let solve = null;
    try {
      const tsSrc = `${consts}\n${fnDecl.getText(overlay).replace(/^export\s+/, '')}`;
      const js = ts.transpileModule(tsSrc, {
        compilerOptions: { module: ts.ModuleKind.None, target: ts.ScriptTarget.ES2019 },
      }).outputText;
      // eslint-disable-next-line no-new-func
      solve = new Function(`${js}\nreturn solveBandPlacement;`)();
    } catch (e) {
      fail('11c — the solver is liftable and runnable', String(e && e.message));
    }

    if (solve) {
      const H = 844;
      const INSETS = { top: 59, bottom: 34 };
      const BAND = 180;
      const GAP = Number((consts.match(/BAND_GAP = (\d+)/) || [])[1]);
      const EDGE = Number((consts.match(/BAND_EDGE = (\d+)/) || [])[1]);
      const BOTTOM = Number((consts.match(/BAND_BOTTOM = (\d+)/) || [])[1]);

      // Preferred: ABOVE the ring, and the band's bottom edge stops one gap
      // short of it.
      {
        const c = { top: 500, height: 80 };
        const p = solve(c, BAND, H, INSETS);
        assert(
          p.from === 'top' && p.offset === c.top - BAND - GAP,
          '11d — a ring with room above it gets the band directly above',
          JSON.stringify(p),
        );
      }
      // No room above (a ring near the top): BELOW, one gap under the ring.
      {
        const c = { top: 100, height: 60 };
        const p = solve(c, BAND, H, INSETS);
        assert(
          p.from === 'top' && p.offset === c.top + c.height + GAP,
          '11e — a ring too near the top puts the band below it',
          JSON.stringify(p),
        );
      }
      // Neither fits (a ring taller than the space around it): the old bottom
      // band, which is the only honest fallback.
      {
        const p = solve({ top: 80, height: 700 }, BAND, H, INSETS);
        assert(
          p.from === 'bottom' && p.offset === BOTTOM,
          '11f — a ring with room on neither side falls back to the bottom band',
          JSON.stringify(p),
        );
      }
      assert(
        solve(null, BAND, H, INSETS).from === 'bottom',
        '11g — an untargeted step (no cutout) uses the bottom band',
      );
      assert(
        solve({ top: 500, height: 80 }, 0, H, INSETS).from === 'bottom',
        '11h — an UNMEASURED band cannot be placed adjacent and uses the fallback',
        'placing before onLayout would site the band by a height of zero',
      );

      // The two invariants, swept over every ring position and a range of band
      // heights. `top: 54` — the pre-fix constant — violates both.
      let overlaps = null;
      let inInset = null;
      for (let bandH = 80; bandH <= 320; bandH += 40) {
        for (let top = -40; top <= H + 40; top += 17) {
          for (const height of [40, 120, 400]) {
            const c = { top, height };
            const p = solve(c, bandH, H, INSETS);
            if (p.from !== 'top') continue;
            const above = p.offset + bandH <= c.top;
            const below = p.offset >= c.top + c.height;
            if (!above && !below) {
              overlaps = overlaps || { c, bandH, p };
            }
            if (p.offset < INSETS.top + EDGE) {
              inInset = inInset || { c, bandH, p };
            }
          }
        }
      }
      assert(
        overlaps === null,
        '11i — the band never overlaps the ring it is explaining',
        `first overlap: ${JSON.stringify(overlaps)}`,
      );
      assert(
        inInset === null,
        '11j — a top-anchored band always clears the top safe-area inset',
        `first violation: ${JSON.stringify(inInset)} — a fixed offset (the ` +
          'shipped `top: 54`) lands under the status bar and, on a sub-screen, ' +
          'under the native header',
      );

      // #397/#398 — the per-step pin: an opt-in 5th argument overrides
      // adjacency with the top of the window. EXECUTED like 11d–11j; the
      // 4-arg cases above are the mechanical proof the un-pinned path did
      // not move.
      {
        // The exact tall-ring input 11f bottom-bands — pinned, it tops.
        const p = solve({ top: 80, height: 700 }, BAND, H, INSETS, 'top');
        assert(
          p.from === 'top' && p.offset === INSETS.top + EDGE,
          "11n — a pinned step ('top') tops the band even when adjacency would bottom-band it",
          JSON.stringify(p),
        );
      }
      {
        // The pin PRECEDES the null-cutout/unmeasured early return: a
        // degraded or not-yet-measured pinned step still honors the ask.
        const p = solve(null, 0, H, INSETS, 'top');
        assert(
          p.from === 'top' && p.offset === INSETS.top + EDGE,
          '11o — the pin precedes the null-cutout / unmeasured-band early return',
          JSON.stringify(p),
        );
      }
    }
  }

  // The band's own style must READ the solved offset. A numeric literal here
  // is the exact regression: the placement is computed and then ignored.
  const litTop = findAll(
    overlay,
    (n) =>
      ts.isConditionalExpression(n) &&
      ts.isObjectLiteralExpression(n.whenTrue) &&
      n.whenTrue.properties.some((p) => p.name && p.name.getText(overlay) === 'top'),
  )[0];
  assert(
    !!litTop,
    '11k — the band style still picks its anchor with a conditional',
    'the top/bottom conditional is gone; re-point this assertion',
  );
  if (litTop) {
    const topProp = litTop.whenTrue.properties.find(
      (p) => p.name && p.name.getText(overlay) === 'top',
    );
    assert(
      !!topProp && !ts.isNumericLiteral(topProp.initializer),
      '11l — the top anchor is the SOLVED offset, not a fixed number',
      `saw: ${flat(overlay, litTop.whenTrue)} — \`{ top: 54 }\` is the shipped bug`,
    );
  }

  // The band's height has to come from a real measurement, or the solver runs
  // on a guess and every placement is off by the difference.
  const bandLayout = findAll(overlay, (n) => {
    if (!isJsxEl(n)) return false;
    const a = attr(overlay, n, 'onLayout');
    return !!a && !!a.initializer && referencesIdentifier(overlay, a.initializer, 'setBandH');
  });
  assert(
    bandLayout.length === 1,
    '11m — the band measures its own height from onLayout',
    `${bandLayout.length} onLayout handlers write the band height`,
  );

  // #397/#398 — the pin's two structural links. Executing the solver (11n/11o)
  // proves the pin WORKS; these prove it is WIRED: the s2_2 builder declares
  // it, and the overlay's solver call actually forwards it.
  {
    // 11p — bound to the s2_2 builder's own returned object literal via the
    // AST: a comment, or `band: 'top'` on any OTHER builder, cannot satisfy it.
    const scriptSf = parse('src/components/analystScript.ts');
    const s22Builder = findAll(
      scriptSf,
      (n) =>
        ts.isPropertyAssignment(n) &&
        n.name.getText(scriptSf) === 's2_2' &&
        ts.isArrowFunction(n.initializer),
    )[0];
    let s22Band = null;
    if (s22Builder) {
      const body = s22Builder.initializer.body;
      const obj = ts.isParenthesizedExpression(body) ? body.expression : body;
      if (ts.isObjectLiteralExpression(obj)) {
        s22Band =
          obj.properties.find(
            (p) => ts.isPropertyAssignment(p) && p.name.getText(scriptSf) === 'band',
          ) || null;
      }
    }
    assert(
      !!s22Band &&
        ts.isStringLiteral(s22Band.initializer) &&
        s22Band.initializer.text === 'top',
      "11p — the s2_2 builder declares `band: 'top'` (the swipe beat pins to the top)",
      s22Band
        ? `saw: ${flat(scriptSf, s22Band)}`
        : 'no `band` property on the s2_2 builder\'s returned object literal',
    );

    // 11q — the 5th argument INSIDE the solveBandPlacement CallExpression is
    // `active.band`. The assertion walks the call's own arguments — a bare
    // `active.band` token elsewhere in the file must not satisfy it.
    const solveCalls = callsTo(overlay, 'solveBandPlacement');
    const fifth = solveCalls.length === 1 ? solveCalls[0].arguments[4] : undefined;
    assert(
      solveCalls.length === 1 &&
        !!fifth &&
        ts.isPropertyAccessExpression(fifth) &&
        ts.isIdentifier(fifth.expression) &&
        fifth.expression.text === 'active' &&
        fifth.name.text === 'band',
      '11q — the overlay forwards `active.band` as the solver call\'s 5th argument',
      solveCalls.length === 1
        ? `call args: ${flat(overlay, solveCalls[0])}`
        : `${solveCalls.length} call(s) to solveBandPlacement`,
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 12 — a growing page moves targets without ever scrolling (#384 report 1)
// ═══════════════════════════════════════════════════════════════════════════
//
// The calculator's content GROWS after first paint — the rosters land and the
// outlook receipt swaps with its fallback — which shifts every target below it
// with no scroll event at all. `onScroll` alone cannot see that, which is half
// of why the first-landing spotlight was wrong. #386 added a second host with
// the same defect class: LeagueSummaryScreen's Season outlook section
// mounts/toggles after first paint (AsyncStorage hydration, outlook-query
// resolution, the strip tap), shifting the position pills under an already-
// measured n5 spotlight. Every host below is asserted independently, and a
// host whose wired `onScroll` cannot be found fails LOUDLY — it is never
// skipped, so silently dropping a host from parsing cannot green the suite.
// Sabotage: drop either callback from either host → red.

{
  const GROWING_HOSTS_REL = [
    'src/screens/TradeCalculatorScreen.tsx',
    'src/screens/LeagueSummaryScreen.tsx', // #386 — outlook section shifts the pills
  ];
  for (const rel of GROWING_HOSTS_REL) {
    const sf = parse(rel);
    const scroller = findAll(sf, (n) => {
      if (!isJsxEl(n)) return false;
      const a = attr(sf, n, 'onScroll');
      return !!a && !!a.initializer && referencesIdentifier(sf, a.initializer, 'notifyGuideTargetsMoved');
    })[0];

    if (!scroller) {
      fail(`12a — ${rel}'s page ScrollView announces movement`, 'no wired onScroll found');
    } else {
      for (const name of ['onLayout', 'onContentSizeChange']) {
        const a = attr(sf, scroller, name);
        assert(
          !!a && !!a.initializer && referencesIdentifier(sf, a.initializer, 'notifyGuideTargetsMoved'),
          `12b — ${where(sf, scroller)} also announces from ${name}`,
          `${rel}: content that grows under a settled scroll offset moves ` +
            'every target below it and fires no scroll event',
        );
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 13 — scroll-into-view: the seam, and the once-per-step guard
// ═══════════════════════════════════════════════════════════════════════════
//
// The overlay owns no scroll container, so hosts register a handle keyed by
// the screen name their steps declare. The re-entrancy guard is the load-
// bearing part: scrolling notifies, the notify re-measures, and a re-measure
// that re-entered the scroll would chase its own tail for as long as the step
// is up. Sabotage: drop the `scrolledForRef` guard → red.

{
  const scrollerFns = ['registerGuideScroller', 'unregisterGuideScroller', 'getGuideScroller'];
  for (const name of scrollerFns) {
    assert(
      exportedFns.has(name),
      `13a — guideTargets exports ${name}`,
      'the host↔overlay scroll seam is incomplete',
    );
  }
  const askCalls = callsTo(overlay, 'getGuideScroller');
  assert(
    askCalls.length === 1,
    '13b — the overlay asks for a scroller exactly once',
    `${askCalls.length} call(s)`,
  );
  const scrollEffect = askCalls.length === 1
    ? enclosing(askCalls[0], (n) => isCallTo(n, 'useEffect'))
    : null;
  assert(
    !!scrollEffect,
    '13c — the scroll-into-view lives in a useEffect (never in render)',
    'scrolling a host during render is a side effect in the render phase',
  );
  if (scrollEffect) {
    const fn = scrollEffect.arguments[0];
    const guard = findAll(fn, (n) => ts.isIfStatement(n)).find(
      (n) => /scrolledForRef\.current === active\.id/.test(flat(overlay, n.expression)),
    );
    assert(
      !!guard,
      '13d — a step scrolls its target into view at most ONCE',
      'without the latch the scroll notifies, the notify re-measures, and the ' +
        'effect re-enters for the life of the step',
    );
    assert(
      referencesIdentifier(overlay, fn, 'bandMeasured') || referencesIdentifier(overlay, fn, 'bandH'),
      '13e — the scroll reserves room for the MEASURED band',
      'scrolling to an edge without accounting for the band lands the target ' +
        'exactly where the band has to go',
    );
    const FORBIDDEN = ['commitShown', 'track', 'dismissActiveStep', 'skipStep'];
    const seen = FORBIDDEN.filter((id) => referencesIdentifier(overlay, fn, id));
    assert(
      seen.length === 0,
      '13f — the scroll-into-view emits nothing and ends no step',
      `references ${seen.join(', ')}`,
    );
  }
}

// ── 14: the entry slide runs against a MOUNTED band ───────────────────────
//
// Operator device report 2026-08-22 (builds 126 and 127), reproduced in the
// simulator on the sign-in username beat: a TARGETED beat that follows another
// beat drew its ring and no avatar/bubble. The overlay returns null while a
// targeted step's spotlight is pending, so the band UNMOUNTS; the entry
// spring used to start on step activation — i.e. against the unmounted band —
// with the native driver, and the remounted band initialised from the stale
// JS-side value (0) and never received another native frame. Two properties
// pin the fix: the spring is keyed on the band rendering (`spotlightPending`
// in its deps and its guard), and it is JS-driven.
{
  const springs = findAll(
    overlay,
    (n) =>
      ts.isCallExpression(n) &&
      ts.isPropertyAccessExpression(n.expression) &&
      flat(overlay, n.expression) === 'Animated.spring',
  );
  assert(springs.length === 1, '14a — exactly one entry spring', `${springs.length} found`);
  if (springs.length === 1) {
    const spring = springs[0];
    const cfg = spring.arguments[1];
    assert(
      !!cfg && /useNativeDriver:\s*false/.test(flat(overlay, cfg)),
      '14b — the entry spring is JS-driven (useNativeDriver: false)',
      'a native-driven value on a band that unmounts and remounts initialises ' +
        'the remounted view from the stale JS value and never updates it',
    );
    const effect = enclosing(spring, (n) => isCallTo(n, 'useEffect'));
    assert(!!effect, '14c — the entry spring lives in a useEffect');
    if (effect) {
      const deps = effect.arguments[1] ? flat(overlay, effect.arguments[1]) : '';
      assert(
        /spotlightPending/.test(deps),
        '14d — the spring effect is keyed on spotlightPending (the band RENDERING), not only the step id',
        `deps are ${deps || '(none)'} — keyed on activation alone, the spring runs against an unmounted band`,
      );
      const fn = effect.arguments[0];
      const guard = findAll(fn, (n) => ts.isIfStatement(n)).find((n) =>
        /spotlightPending/.test(flat(overlay, n.expression)),
      );
      assert(
        !!guard,
        '14e — the spring effect bails while the spotlight is pending',
        'without the guard the spring still starts on the pending (null) render',
      );
    }
  }
  // And the activation effect must NOT start the spring any more.
  const activation = findAll(
    overlay,
    (n) => isCallTo(n, 'useEffect') && /\[active\?\.id\]/.test(flat(overlay, n.arguments[1] || n)),
  );
  assert(
    activation.length >= 1 && activation.every((e) => !referencesIdentifier(overlay, e.arguments[0], 'spring')),
    '14f — the [active?.id] activation effect does not animate the band',
    'the regression is exactly a spring started on activation',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All guide-spotlight-tracking checks passed.');
