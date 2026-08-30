#!/usr/bin/env node
// #402 canvas-results (flag `calc.canvas_results`) — structural guard.
// Spec: docs/feedback/items/402-more-offers-shop/canvas-results-spec.md.
//
// WHY THIS EXISTS. The operator ruled that found trade ideas present INSIDE
// the merged calculator canvas as a BROWSE SESSION — deck hidden, pager +
// per-idea editable prefill, the ✕ reusing the existing two-layer
// decline-reason capture as a pass — and nearly every failure mode of that
// design is invisible to tsc:
//
//   • the deck tree could quietly come back under the live host (two result
//     surfaces), or the flag-off gate could rot so the SHIPPED deck page
//     loses its deck (the one claim that makes shipping this safe);
//   • paging could start emitting analytics (browsing is not judging), or
//     the per-fronted-card trade_card_viewed / deck_card_viewed emitters
//     could fire once per paged idea;
//   • the ✕ could grow a parallel pass path — its own POST, its own
//     overlay semantics — instead of routing through the calculator-origin
//     machinery (advance / handleReasonLayer1 / trade_pass_overlay_*), or
//     pass the EDITED package when the signal is about the engine's
//     suggestion;
//   • the per-idea edit map could stop dying with its context (league
//     switch, deck reset, flag kill) and leak edits across sessions;
//   • the audit-Q5 fall-through could come back: a fair sweep returning
//     zero ideas landing on the idle "Hit Find a Trade to start" card;
//   • `onSidesChange` could stop being optional-and-absent for existing
//     hosts, silently changing FeaturedTradeWindow / the pushed page.
//
// Structural where it matters: TradesScreen is parsed with the project's
// own TypeScript and function bodies are walked as AST (the
// check-shop-deck.js pattern), so a comment naming `track` cannot
// false-positive; exact-text pins are used where the TEXT is the contract
// (gates, testIDs, fixture keys).
//
// Run: node tests/check-canvas-results.js   (or: npm run test:canvas-results)

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

const ROOT = path.join(__dirname, '..', '..');
const SRC = path.join(__dirname, '..', 'src');
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const readRoot = (r) => fs.readFileSync(path.join(ROOT, r), 'utf8');
const stripComments = (t) =>
  t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
const count = (t, re) => (t.match(re) || []).length;

let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else {
    failures++;
    console.log(`  ✗ ${name}`);
    if (detail) console.log(`      ${detail}`);
  }
}

const trades = read('screens/TradesScreen.tsx');
const tradesCode = stripComments(trades);
const calc = read('components/InLeagueCalculator.tsx');
const calcCode = stripComments(calc);
const canvas = read('components/TradeBuildCanvas.tsx');
const canvasCode = stripComments(canvas);
const featured = read('components/FeaturedTradeWindow.tsx');
const card = read('components/TradeCard.tsx');
// #410 — the pushed Real-values page, the calculator's OTHER host. It must
// stay byte-identical: no decline cell, no shop slot.
const calcScreen = read('screens/TradeCalculatorScreen.tsx');

// ── AST helpers (check-shop-deck.js pattern) ──────────────────────────────

const host = ts.createSourceFile(
  'TradesScreen.tsx',
  trades,
  ts.ScriptTarget.ES2019,
  /* setParentNodes */ true,
  ts.ScriptKind.TSX,
);
// #410 — the calculator is parsed too: §4m asks what the middle cell's two
// BRANCHES each contain, and "does the decline branch also call clear()" is a
// question about a subtree, not about text near a string.
const calcSf = ts.createSourceFile(
  'InLeagueCalculator.tsx',
  calc,
  ts.ScriptTarget.ES2019,
  /* setParentNodes */ true,
  ts.ScriptKind.TSX,
);

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
function functionNamed(sf, name) {
  return findAll(
    sf,
    (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === name,
  )[0];
}
function referencesIdentifier(sf, root, name) {
  return findAll(sf, (n) => ts.isIdentifier(n) && n.text === name).some(
    (n) => n.getStart(sf) >= root.getStart(sf) && n.getEnd() <= root.getEnd(),
  );
}

console.log('check-canvas-results:');

// ═══════════════════════════════════════════════════════════════════════
// 1 — the flag: four-place registration, LIT, comment names the contract
// ═══════════════════════════════════════════════════════════════════════
{
  const features = JSON.parse(readRoot('config/features.json'));
  assert(features['calc.canvas_results'] === true,
    '1. calc.canvas_results is LIT in config/features.json (operator cadence)');
  assert(typeof features['_comment_canvas_results'] === 'string'
    && /canvas-results-spec\.md/.test(features['_comment_canvas_results'])
    && /kill switch/i.test(features['_comment_canvas_results'])
    && /calc\.inline_home/.test(features['_comment_canvas_results'])
    && /calc\.merged_layout/.test(features['_comment_canvas_results']),
    '1a. …with a comment naming the spec, the kill switch and both prerequisites');
  for (const f of ['release', 'onboarding-v2', 'profiles-on']) {
    const j = JSON.parse(readRoot(`backend/tests/fixtures/flags/${f}.json`));
    assert(j['calc.canvas_results'] === true,
      `1b. backend/tests/fixtures/flags/${f}.json mirrors it true`);
  }
  assert(/"calc\.canvas_results",/.test(readRoot('backend/feature_flags.py')),
    '1c. the key is registered in backend FLAG_KEYS',
    'an unregistered key fails test_features_json_keys_known and never ships to clients');
}

// ═══════════════════════════════════════════════════════════════════════
// 2 — host gating: one flag read, one live conjunction, deck retired ONLY
//     on the live host — and present, byte-identically, everywhere else
// ═══════════════════════════════════════════════════════════════════════
{
  assert(/const canvasResultsOn = useFlag\('calc\.canvas_results'\);/.test(trades)
    && count(tradesCode, /useFlag\('calc\.canvas_results'\)/g) === 1,
    '2. TradesScreen reads the flag exactly once');
  assert(/const canvasResultsLive = canvasResultsOn && canvasHost === 'flag';/.test(trades)
    && count(tradesCode, /const canvasResultsLive =/g) === 1,
    '2a. ONE live gate: the flag AND the flag-hosted canvas — never the bare flag',
    'a bare-flag gate would strip the deck from flag-on team/player modes (spec §1)');
  assert(count(tradesCode, /const browseLive = canvasResultsLive && browseSession !== null;/g) === 1,
    '2b. ONE session-liveness derivation');
  // The deck tree: the NEW gate wraps the OLD gate verbatim — flag-off (and
  // every non-canvas host) falls through to exactly the shipped expression.
  assert(/\{canvasResultsLive \? null : singlePinFeatured && !singlePinDeckActive \? null : \(/.test(trades),
    '2c. the deck tree is gated off the live host, with the shipped gate as the fallback arm',
    'the whole deck render tree must survive verbatim for flag-off');
  assert(/\{!canvasResultsLive && singlePinFeatured \? \(/.test(trades),
    '2d. the single-pin featured region retires on the live host (a second calculator otherwise)');
  assert(/\{!canvasResultsLive && singlePinDeckActive \? assetIdeasPanel : null\}/.test(trades),
    '2e. …and so does the alternates panel second mount');
  assert(count(tradesCode, /job\?\.status === 'running' && !canvasResultsLive && \(/g) === 2,
    '2f. BOTH pre-canvas progress strips stand aside on the live host',
    'their narration moves into the canvas-results area (spec §2)');
  assert(/\{!firstRun && deckHasLanes && !canvasResultsLive && \(/.test(trades),
    '2g. the lane pills (deck-only chrome) do not render on the live host');
}

// ═══════════════════════════════════════════════════════════════════════
// 3 — the pager: browsing is not judging
// ═══════════════════════════════════════════════════════════════════════
{
  for (const id of [
    'trades.canvas-results.pager',
    'trades.canvas-results.prev',
    'trades.canvas-results.next',
  ]) {
    assert(trades.includes(`testID="${id}"`), `3. ${id} exists`);
  }
  // #410 / D-169 — the decline control MOVED to the canvas action row's
  // middle cell (`calc.action.decline`, §4m below). The pager itself is
  // unchanged; what is pinned here is the ABSENCE, so the old ✕ cannot be
  // re-added beside the new one and leave the report's "replace" unhonored.
  assert(!trades.includes('testID="trades.canvas-results.pass"'),
    '3-bis. the pager no longer carries a pass control — exactly one is mounted (D-169)',
    'a second ✕ here means the action-row cell ADDED a decline instead of replacing one');
  assert(/\{browseLive && sortedDeck\.length > 0 \? \(/.test(trades),
    '3a. the pager renders only while the session actually holds ideas');
  const step = functionNamed(host, 'handleBrowseStep');
  assert(!!step, '3b. handleBrowseStep exists');
  assert(!!step && !referencesIdentifier(host, step, 'track'),
    '3c. paging emits NOTHING — no track() anywhere in the step handler',
    'the spec is explicit: browsing is not judging');
  assert(!!step && /Math\.min\(Math\.max\(/.test(step.getText())
    && /sortedDeck\.length - 1/.test(step.getText()),
    '3d. the cursor clamps at both ends — reaching an end stops, never wraps');
  assert(/disabled=\{deckIdx === 0\}/.test(trades)
    && /disabled=\{deckIdx >= sortedDeck\.length - 1\}/.test(trades),
    '3e. the chevrons disable at the ends');
  assert(/\{`\$\{deckIdx \+ 1\} \/ \$\{sortedDeck\.length\}`\}/.test(trades),
    '3f. the `N / X` TickLabel reads the same list the pager steps',
    'a counter on a different list lies after a pass decrements X');
  // The per-fronted-card analytics emitters are suppressed while browsing —
  // otherwise every page step fires a "viewed" row.
  const viewedGuards = count(tradesCode, /if \(browseLive\) return;/g);
  assert(viewedGuards === 2,
    '3g. trade_card_viewed AND deck_card_viewed are suppressed under a live session',
    `expected the 2 emitter guards, found ${viewedGuards}`);
}

// ═══════════════════════════════════════════════════════════════════════
// 4 — the ✕: the EXISTING reason machinery, no parallel pass path
// ═══════════════════════════════════════════════════════════════════════
{
  const pass = functionNamed(host, 'handleBrowsePass');
  assert(!!pass, '4. handleBrowsePass exists');
  const passText = pass ? pass.getText() : '';
  // QA round A-D3 + B-P7 (re-keyed 2026-08-29; was: overlay only for
  // `declineReasonProps && reasonsAsOverlay`, with a bare-advance fallback).
  // The operator's ruling 2 is UNQUALIFIED — the ✕ IS the decline flow on
  // every browse session — so the deckOrigin/reasonsAsOverlay gate and the
  // fallback branch (whose "Passed — Undo" toast lied: the immediate flush
  // made Undo a no-op) are both gone.
  assert(/setBrowseReasonOpen\(true\)/.test(passText)
    && /handleReasonOverlayOpened\(\)/.test(passText)
    && !/reasonsAsOverlay/.test(stripComments(passText)),
    '4a. the ✕ ALWAYS opens the reason capture — no deckOrigin/reasonsAsOverlay gate (ruling 2, unqualified)',
    'a re-grown origin gate silently drops reason capture on auto-start/model sessions');
  assert(!!pass && !referencesIdentifier(host, pass, 'advance')
    && !referencesIdentifier(host, pass, 'flushPendingPass')
    && !referencesIdentifier(host, pass, 'removeBrowsedIdea')
    && !referencesIdentifier(host, pass, 'setToast'),
    '4b. the bare-advance fallback (and its no-op-Undo toast) stays deleted',
    'the only removal paths are the reason machinery\'s own commit and dismiss handlers');
  // 4b2 re-specced by #410/D-169: the kill-switch rule is unchanged, but its
  // home moved from the pager's own `{declineReasonProps ? (` wrapper to the
  // `browseDecline` prop expression. Gating on `browseLive && sortedDeck` ALONE
  // would render a ✕ that `handleBrowsePass` early-returns out of — a dead
  // control, which is exactly what the pager wrapper existed to prevent.
  {
    const at = tradesCode.indexOf('browseDecline={');
    const seg = at > -1 ? tradesCode.slice(at, at + 220).replace(/\s+/g, ' ') : '';
    assert(/^browseDecline=\{ browseLive && sortedDeck\.length > 0 && declineReasonProps \? \{ onPress: handleBrowsePass \} : null \}/
      .test(seg),
      '4b2. the decline cell renders only while the reason machinery exists (decline_reasons kill switch ⇒ the cell falls back to Clear)',
      'an ✕ with no machinery would be a dead control — or worse, a re-grown fallback');
  }
  // 4b3 — and the handler it reaches has exactly ONE caller. Leaving the
  // pager ✕ in place beside the new cell would give the page two decline
  // controls and leave the ✕ the report asked to REPLACE still standing.
  assert(count(tradesCode, /handleBrowsePass/g) === 2,
    '4b3. handleBrowsePass is defined once and called from exactly one place',
    'the definition + one reference; a third occurrence is a second decline control');
  assert(!/\.edits/.test(passText),
    '4c. the pass never touches the edit map — the ORIGINAL idea is what gets passed',
    'the pass signal is about the engine\'s suggestion, not the user\'s edit');
  // commitReasonAdvance: browse splice AND the shipped deck advance.
  const commit = functionNamed(host, 'commitReasonAdvance');
  assert(!!commit && /if \(browseLive && rawId\) \{\s*removeBrowsedIdea\(rawId\);\s*return;\s*\}/.test(commit.getText())
    && /setDeckIdx\(\(i\) => i \+ 1\)/.test(commit.getText()),
    '4d. commitReasonAdvance splices in a session and still advances the deck everywhere else',
    'the layer-2 commit is the ONE place a reasoned pass leaves the working set');
  // No parallel write path: the four progressive-write POST sites are the
  // reason handlers' own — the browse surface adds ZERO.
  assert(count(tradesCode, /postDeclineReason\(/g) === 4,
    '4e. exactly the four shipped postDeclineReason sites — the browse ✕ added none',
    'a fifth site is a parallel pass path in disguise');
  // The overlay mirror: same shell contract as TradeCard's (which
  // check-calc-merged-behavior pins on the card side).
  const at = trades.indexOf('testID="trades.canvas-results.reason-overlay"');
  assert(at > 0, '4f. the browse reason overlay exists');
  const sheetRegion = trades.slice(Math.max(0, at - 900), at + 1600);
  assert(/<KeyboardAvoidingView/.test(sheetRegion)
    && /behavior=\{Platform\.OS === 'ios' \? 'padding' : undefined\}/.test(sheetRegion),
    '4g. the sheet sits in a KeyboardAvoidingView (padding on iOS) — the "Other" composer opens below its box');
  const panelAt = trades.indexOf('<DeclineReasonPanel', at);
  const panelRegion = trades.slice(panelAt, panelAt + 900);
  assert(/onLayer1=\{\(r, from\) => declineReasonProps\.onLayer1\(r, from\)\}/.test(panelRegion),
    '4h. onLayer1 banks through the deck\'s own handler and does NOT close the sheet',
    'closing on layer 1 strands the idea: pass banked, layer 2 unreachable');
  assert(!/onLayer1=\{[^}]*setBrowseReasonOpen\(false\)/.test(panelRegion),
    '4i. …verified as an absence too');
  for (const cb of ['onLayer2Select', 'onLayer2Send']) {
    const re = new RegExp(
      `${cb}=\\{\\(r, d(?:, t)?\\) => \\{\\s*setBrowseReasonOpen\\(false\\);\\s*declineReasonProps\\.${cb}\\(r, d(?:, t)?\\);`,
    );
    assert(re.test(panelRegion),
      `4j. ${cb} closes the sheet before committing through the deck's handler`);
  }
  assert(/function dismissBrowseReasonOverlay\(\)[\s\S]{0,700}?handleReasonOverlayDismissed\(banked\)/.test(trades)
    && /reasonBankedIdRef\.current === rawTopCard\.trade_id/.test(trades),
    '4k. a backdrop dismiss reports banked-ness through the deck\'s own dismissed handler',
    'dismiss-after-bank must commit the deferred advance; dismiss-without-answering must do nothing');
  // 4l — the assertion is unchanged; only the sentence it advertised was
  // overturned. D-169 moved the decline control INTO the action row's middle
  // cell, but it arrives as a PROP: this component still reads no
  // canvas-results flag, which is what makes the two-host contract hold (the
  // pushed page and FeaturedTradeWindow mount the same file).
  assert(!/canvas-results/.test(calcCode),
    '4l. InLeagueCalculator reads no canvas-results flag — the decline cell arrives as a PROP (D-169 amends the placement clause; the 50/30/20 is still untouched)');
  assert(/browseDecline\?: \{ onPress: \(\) => void \} \| null;/.test(calc)
    && /browseDecline\?: \{ onPress: \(\) => void \} \| null;/.test(canvas),
    '4l2. …and it is declared OPTIONAL in both the component and the canvas it is threaded through',
    'a required prop forces every other host to pass something, breaking byte-identity');
  assert(!/browseDecline/.test(featured) && !/browseDecline/.test(calcScreen),
    '4l3. …and is absent at FeaturedTradeWindow and the pushed Real-values page',
    'those two mounts must stay byte-identical — Clear, never a decline cell');

  // ── 4m — the action row's middle cell (#410 / D-169) ──────────────────
  //
  // The cell FORKS on the host's declaration. Everything here exists because
  // the tempting wrong builds all typecheck: a local pass path with its own
  // analytics, a single Pressable with conditional props, a shared `disabled`
  // that kills the decline on an emptied canvas, and — the one that quietly
  // re-opens the data-loss defect — a decline branch that "tidies up" by
  // calling clear() too.
  {
    const fork = findAll(calcSf, (n) =>
      ts.isConditionalExpression(n)
      && ts.isIdentifier(n.condition)
      && n.condition.text === 'browseDecline')[0];
    assert(!!fork,
      '4m. the middle cell is a two-branch fork on the host prop',
      'no fork means the cell was disabled-in-place instead of replaced (the report asked for a replacement)');
    // JSX branches arrive wrapped in parentheses; unwrap so "is this branch a
    // Pressable of its own?" asks about the element, not the punctuation.
    const unwrap = (n) =>
      n && ts.isParenthesizedExpression(n) ? unwrap(n.expression) : n;
    const declineArm = fork ? stripComments(unwrap(fork.whenTrue).getText()) : '';
    const clearArm = fork ? stripComments(unwrap(fork.whenFalse).getText()) : '';

    // T-1 — the decline branch reaches the HOST's handler and nothing else.
    assert(/onPress=\{browseDecline\.onPress\}/.test(declineArm),
      '4m1. the decline branch presses straight through to the host prop',
      'a locally-defined pass function is a SECOND pass implementation, with events the taxonomy never classified');
    assert(!!fork && !referencesIdentifier(calcSf, fork.whenTrue, 'track'),
      '4m1b. …and emits nothing of its own');
    for (const p of ['onLikeTrade', 'onFindATrade', 'onSidesChange']) {
      assert(!!fork && !referencesIdentifier(calcSf, fork.whenTrue, p),
        `4m1c. …and invokes no other host prop (${p})`);
    }

    // T-2 — THE data-loss guard. `clear()` empties both sides, which fires
    // onSidesChange with ([], []) and snapshots {give: [], receive: []} into
    // the browsed idea's edit map: paging back then restores a WIPED idea.
    // The decline branch must never reach it.
    assert(!!fork && !referencesIdentifier(calcSf, fork.whenTrue, 'clear'),
      '4m2. the decline branch never calls clear() — the browse-session data-loss defect stays closed',
      'clear() during a session writes {give: [], receive: []} into the idea\'s edit map (PRD R-6)');
    assert(!!fork && referencesIdentifier(calcSf, fork.whenFalse, 'clear'),
      '4m2b. …while the Clear branch still does — the D-157 control is intact');
    assert(count(calcCode, /onPress=\{clear\}/g) === 2,
      '4m2c. clear() is reachable from exactly two controls: the action row\'s Clear branch and the stacked page\'s ghost button',
      'a third site is a new way to wipe a browsed idea');

    // T-3 — two Pressables, two static literal ids. One shared cell breaks
    // testid-lint's static-literal contract and is the shape that produces
    // the shared-`disabled` and no-decline-branch failures for free.
    assert(/^<Pressable/.test(declineArm.trim()) && /^<Pressable/.test(clearArm.trim()),
      '4m3. each branch is its own Pressable');
    assert(/testID="calc\.action\.decline"/.test(declineArm)
      && /testID="calc\.action\.clear"/.test(clearArm),
      '4m3b. …each carrying its own static literal testID');
    assert(!/testID=\{/.test(declineArm) && !/testID=\{/.test(clearArm),
      '4m3c. …and neither id is built by an expression',
      'testid-lint reads literals; a conditional id also makes calc.action.clear ambiguous in the retained flows');

    // T-4 — `disabled` belongs to Clear alone. Hoisting it kills the decline
    // on a canvas the user emptied row-by-row mid-session.
    assert(!/disabled=/.test(declineArm),
      '4m4. the decline branch carries no `disabled`',
      '`!anySide` would make it dead on an emptied canvas — a state R-6 leaves reachable via per-row removes');
    assert(/disabled=\{!anySide\}/.test(clearArm),
      '4m4b. …and the Clear branch keeps its own');

    // T-8 — one warning haptic per tap. `clear()` fires it at :843; the
    // branch used to fire a second before calling it.
    assert(!/haptics\./.test(clearArm),
      '4m5. the Clear branch fires no haptic of its own — clear() owns it',
      'both firing is the double warning-haptic R-8 resolves in place');
    assert(!/haptics\./.test(declineArm),
      '4m5b. …and neither does the decline branch — handleBrowsePass owns the selection haptic');

    // R-2 — the glyph, and the a11y verb the glyph does not carry.
    assert(/<Icon name="x" size=\{16\} color=\{semantic\.neg\} \/>/.test(declineArm),
      '4m6. the decline cell is the same bare cross the pager ✕ used (16pt, semantic.neg)');
    assert(/accessibilityLabel="Pass on this trade idea"/.test(declineArm),
      '4m6b. …with the pager\'s verbatim label, so VoiceOver still says "pass"');
    assert(/styles\.actionClear, styles\.actionBtn/.test(declineArm)
      && !/actionPrimary/.test(declineArm),
      '4m6c. …in the Clear cell\'s neutral chrome — ice stays rationed to Find a Trade and the ✓');

    // R-3 — the D-157 proportions. The whole narrow reading that lets D-169
    // amend the spec clause rests on these being untouched.
    assert(/actionFind: \{ flex: 50 \},/.test(calc)
      && /actionClear: \{ flex: 30 \},/.test(calc)
      && /actionSmall: \{ flex: 20 \},/.test(calc),
      '4m7. the action row is still 50/30/20 — the cell\'s CONTENT forked, not its flex (D-157 survives D-169)');
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 5 — per-idea edits: exist, attributed, and mortal
// ═══════════════════════════════════════════════════════════════════════
{
  assert(/edits: Record<string, \{ give: string\[\]; receive: string\[\] \}>;/.test(trades),
    '5. the session carries the per-idea edit map, keyed by the idea\'s stable id');
  const sides = functionNamed(host, 'handleBrowseSidesChange');
  assert(!!sides && /browseSeededIdRef\.current/.test(sides.getText()),
    '5a. edits are attributed to the idea the canvas was SEEDED with, not a render-time guess');
  assert(!!sides && !referencesIdentifier(host, sides, 'track'),
    '5b. edit capture emits nothing');
  // Mortality: reset, league switch, flag/host kill.
  const reset = functionNamed(host, 'resetDeckForNewTargets');
  assert(!!reset && /setBrowseSession\(null\)/.test(reset.getText()),
    '5c. every deck reset kills the session (regenerate-context death, rev-3 hygiene)');
  assert(count(tradesCode, /setBrowseSession\(null\);/g) >= 3,
    '5d. the league-switch and flag-kill paths kill it too',
    'reset + league effect + host-loss effect — fewer means one context death leaks state');
  assert(/if \(!canvasResultsLive && browseSession\) \{/.test(trades),
    '5e. the flag-kill / host-loss effect exists');
  // The seeding effect replays the edited version and remounts per idea.
  assert(/browseSession\?\.edits\[rawTopCard\.trade_id\]/.test(trades)
    && /setCanvasPrefillSeq\(\(n\) => n \+ 1\)/.test(trades),
    '5f. paging reseeds the canvas through the existing prefill/prefillSeq remount (the #287 technique, generalized)');
  assert(/\}, \[browseLive, browseCurrentId\]\);/.test(trades),
    '5g. …keyed on the fronted idea\'s identity only — an in-place edit never remounts the canvas mid-typing');
}

// ═══════════════════════════════════════════════════════════════════════
// 6 — onSidesChange: additive, optional, absent for every existing host
// ═══════════════════════════════════════════════════════════════════════
{
  assert(/onSidesChange\?: \(give: string\[\], receive: string\[\]\) => void;/.test(calc),
    '6. InLeagueCalculator declares onSidesChange as OPTIONAL');
  assert(/const sidesAnnouncedRef = useRef\(false\);/.test(calc),
    '6a. the initial seed is silent — only post-mount CHANGES announce',
    'announcing the seed would record every idea as "edited" the moment it fronts');
  assert(!/useFlag\(\s*['"]calc\.canvas_results['"]\s*\)/.test(calc),
    '6b. the component reads NO flag for it — a host prop, like hideFormatChips (T-3 precedent)');
  assert(!/onSidesChange/.test(stripComments(featured)),
    '6c. FeaturedTradeWindow does not pass it — the #287 host is byte-identical');
  assert(/onSidesChange\?: \(give: string\[\], receive: string\[\]\) => void;/.test(canvas)
    && /onSidesChange=\{onSidesChange\}/.test(canvasCode),
    '6d. TradeBuildCanvas threads it through verbatim');
  assert(/onSidesChange=\{browseLive \? handleBrowseSidesChange : undefined\}/.test(trades),
    '6e. the TradesScreen mount passes it ONLY while a session is live',
    'undefined everywhere else keeps the component byte-identical (spec §3)');
  assert(!/onSidesChange/.test(stripComments(read('screens/TradeCalculatorScreen.tsx'))),
    '6f. the pushed page does not pass it either');
}

// ═══════════════════════════════════════════════════════════════════════
// 7 — honest empties, and the audit-Q5 fall-through dies here
// ═══════════════════════════════════════════════════════════════════════
{
  const at = trades.indexOf('testID="trades.canvas-results"');
  assert(at > 0, '7. the results area exists');
  const endAt = trades.indexOf('{/* #216/#209 (flag trade.asset_ideas)', at);
  const area = trades.slice(at, endAt > at ? endAt : at + 9000);
  assert(/testID="trades\.canvas-results\.fair-zero"/.test(area)
    && /No fair package for this canvas/.test(area),
    '7a. fair-zero has its own honest card — the audit-Q5 fix');
  assert(!/Hit "Find a Trade" to start/.test(area),
    '7b. the idle card CANNOT render in the results area',
    'the Q5 latent bug was exactly this fall-through — it must not be inherited');
  // …and the idle card that still exists for flag-off lives INSIDE the
  // gated deck tree, after the gate that removes it from the live host.
  const idleAt = trades.indexOf('Hit "Find a Trade" to start');
  const gateAt = trades.indexOf(
    '{canvasResultsLive ? null : singlePinFeatured && !singlePinDeckActive ? null : (',
  );
  assert(idleAt > gateAt && gateAt > 0,
    '7c. the flag-off idle card sits inside the gated deck tree',
    'structurally unreachable on the live host — the other half of the Q5 fix');
  assert(/testID="trades\.canvas-results\.model-zero"/.test(area)
    && /\{modelZeroCopy\(\)\}/.test(area),
    '7d. model-zero renders the EXISTING zero copy (one source: modelZeroCopy)');
  assert(/function modelZeroCopy\(\): string/.test(trades)
    && /if \(!canvasResultsLive\) \{\s*setToast\(\{\s*msg: modelZeroCopy\(\),/.test(trades),
    '7e. the flag-off toast reads the SAME copy source and stands aside under a live session');
  assert(/testID="trades\.canvas-results\.exhausted"/.test(area)
    && /You've been through every idea/.test(area)
    && /Find a Trade/.test(area),
    '7f. a set exhausted by passes says so, with the Find a Trade cell as the restart');
  assert(/testID="trades\.canvas-results\.progress"/.test(area)
    && /<Meter/.test(area) && /opponents/.test(area),
    '7g. the model job narrates progress IN the results area — existing vocabulary, never a bare spinner');
  assert(/testID="trades\.canvas-results\.error"/.test(area)
    && /Search failed/.test(area),
    '7h. a failed search says so (the P0-2 rule follows the results surface)');
  assert(/testID="trades\.canvas-results\.scoped-empty"/.test(area)
    && /even after stretching the fairness band/.test(area),
    '7i. the #330 scoped-zero card follows too — its deck slot is retired on this host');
}

// ═══════════════════════════════════════════════════════════════════════
// 8 — both search paths feed the session; Clear ends it
// ═══════════════════════════════════════════════════════════════════════
{
  assert(/setBrowseSession\(\{ origin: 'fair', passed: 0, edits: \{\} \}\);\s*\}\s*runFairPackages\(fairAnchor\);/.test(trades),
    '8. the fair sweep creates a fair-origin session at its single dispatch site');
  // QA round B-C1/B-C2/B-P6 (re-keyed 2026-08-29; was: the choke point's
  // own literal + a count of 8 raw mutate sites). Session lifecycle now
  // rides EVERY dispatch through dispatchGenerate — the model-origin
  // adopt-or-create updater lives there, once.
  const dispatch = functionNamed(host, 'dispatchGenerate');
  assert(!!dispatch
    && /s \? \{ \.\.\.s, origin: 'model' \} : \{ origin: 'model', passed: 0, edits: \{\} \}/.test(dispatch.getText())
    && count(tradesCode, /origin: 'model', passed: 0, edits: \{\}/g) === 1,
    '8a. dispatchGenerate adopts-or-creates the model-origin session — the ONE model session-creation site',
    'a second creation literal is a census bypass');
  assert(count(tradesCode, /generateMutation\.mutate\(/g) === 1
    && !!dispatch && referencesIdentifier(host, dispatch, 'canvasResultsLive'),
    '8b. exactly ONE raw generateMutation.mutate — inside dispatchGenerate, gated on the live host',
    'every dispatch site must route through the helper (census in its header comment)');
  assert(/onPress=\{canvasResultsLive \? handleBrowseClear : handleSearchAllTrades\}/.test(trades),
    '8c. the anchor receipt\'s Clear ends a live session (ruling 1) and keeps its shipped handler otherwise');
  assert(/onPress=\{canvasResultsLive \? handleBrowseAnchorChange : handleAnchorChange\}/.test(trades),
    '8d. …and Change hands the anchor build back instead of scrolling to a canvas that no longer holds it');
  assert(/testID="trades\.canvas-results\.clear"/.test(trades)
    && /\{browseSession\?\.origin === 'model' \? \(/.test(trades),
    '8e. model-path sessions get the matching Clear on the pager (they have no receipt)');
  const end = functionNamed(host, 'endBrowseSession');
  assert(!!end && /resetDeckForNewTargets\(\)/.test(end.getText()),
    '8f. ending a session reuses the ONE reset (epoch bump kills in-flight results) — no parallel teardown');
  for (const fn of ['handleBrowseClear', 'endBrowseSession', 'removeBrowsedIdea']) {
    const f = functionNamed(host, fn);
    assert(!!f && !referencesIdentifier(host, f, 'track'),
      `8g. ${fn} emits nothing — no existing event honestly fits, and the spec forbids new ones`);
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 9 — analytics scope: reuse only, nothing new registered
// ═══════════════════════════════════════════════════════════════════════
{
  assert(!/canvas_results/.test(readRoot('backend/analytics_taxonomy.py')),
    '9. no new analytics event was registered for this feature',
    'the spec reuses find_trades_tapped / calc_trade_queued / trade_pass_overlay_* / pass-reason events');
  // The double-fire guard invariant holds on the new cursor moves.
  const step = functionNamed(host, 'handleBrowseStep');
  const rm = functionNamed(host, 'removeBrowsedIdea');
  assert(!!step && /lastDispositionedRef\.current = null/.test(step.getText())
    && !!rm && /lastDispositionedRef\.current = null/.test(rm.getText()),
    '9a. both browse cursor moves re-arm the double-fire guard',
    'fairpk_ ids are deterministic — a stale guard would no-op the ✕ on a re-served idea');
}


// ═══════════════════════════════════════════════════════════════════════
// 10 — trades-landing (nav.trades_landing, operator ruling 2026-08-28):
//      the launch tab is Trades for all users; flag-off is today's logic.
// ═══════════════════════════════════════════════════════════════════════
{
  const tabNav = fs.readFileSync(path.join(SRC, 'navigation/TabNav.tsx'), 'utf8');
  const at = tabNav.indexOf('const [initialTab]');
  const seg = at >= 0 ? tabNav.slice(at, at + 400) : '';
  assert(/useFeatureFlags\.getState\(\)\.flags\['nav\.trades_landing'\]/.test(seg),
    '10a. initialTab reads nav.trades_landing imperatively (decide-once)',
    'a useFlag read here could rewrite the launch tab mid-session');
  assert(/onboardingEnabled\('onboarding\.trades_first'\)/.test(seg)
    && /firstSwipeDone/.test(seg) && /'Rank'/.test(seg),
    "10b. the flag-off arm keeps today's trades_first/Rank logic verbatim");
  const features = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/features.json'), 'utf8'));
  assert(features['nav.trades_landing'] === true
    && typeof features['_comment_nav_trades_landing'] === 'string',
    '10c. nav.trades_landing is true in features.json with a house comment');
  for (const f of ['release', 'onboarding-v2', 'profiles-on']) {
    const j = JSON.parse(fs.readFileSync(
      path.join(ROOT, `backend/tests/fixtures/flags/${f}.json`), 'utf8'));
    assert(j['nav.trades_landing'] === true, `10d. ${f}.json mirrors it true`);
  }
  assert(/"nav\.trades_landing",/.test(
      fs.readFileSync(path.join(ROOT, 'backend/feature_flags.py'), 'utf8')),
    '10e. registered in FLAG_KEYS');
}

// ═══════════════════════════════════════════════════════════════════════
// 11 — G22: the activation moments follow the results surface. Three
//      moments fired off deck behavior (the Apple save-moment ask off the
//      first like, the Quick-Set prompt off swipe counts, the F9
//      adaptation moment off disposition tallies inside advance()); the
//      deck does not render on the live host, so each is re-triggered off
//      the canvas-era equivalent — by feeding the EXISTING counters and
//      chains, never a fork — and re-homed host-gated in the page flow.
// ═══════════════════════════════════════════════════════════════════════
{
  // The queue-success hook: a real first queue on the live host is the like.
  const rec = functionNamed(host, 'recordCanvasQueueLike');
  assert(!!rec, '11. recordCanvasQueueLike exists');
  const like = functionNamed(host, 'handleInlineLikeTrade');
  assert(!!like
    && /if \(queued && !alreadyQueued && canvasResultsLive\) recordCanvasQueueLike\(\);/.test(like.getText()),
    '11a. the ✓ queue-success path reaches it — host-gated, refusals and already-queued repeats excluded',
    'a refused queue is not a like; a re-✓ of the same package is not a second one');
  assert(/alreadyQueued\?: boolean/.test(stripComments(read('utils/queueCalcTrade.ts'))),
    '11b. queueCalcTrade surfaces the server\'s own idempotence signal for that exclusion');
  // The save moment: the SAME two arms advance()'s like branch runs.
  assert(!!rec && referencesIdentifier(host, rec, 'v2RunLikeChain')
    && referencesIdentifier(host, rec, 'maybeAskApple')
    && referencesIdentifier(host, rec, 'guidedAvatarActive'),
    '11c. the Apple save-moment chain is reachable from queue success (guided s6.2 chain / direct ask)',
    'this is the account-creation moment — losing it on the merged landing is the G22 launch blocker');
  // The counters: browse ✓ feeds the SAME persisted swipe counter the deck
  // swipes feed (advance()\'s patch, verbatim — twice in the file, no third
  // counter and no fork).
  assert(count(tradesCode, /totalSwipes: getOnboardingState\(\)\.totalSwipes \+ 1,/g) === 2
    && !!rec && referencesIdentifier(host, rec, 'patchOnboardingState')
    && /firstSwipeDone: true/.test(rec.getText()),
    '11d. the queue-success path bumps the SAME onboarding swipe counter advance() bumps',
    'items 7 (Quick-Set prompt) and 8 (session-2 Apple banner) read totalSwipes');
  assert(!!rec && referencesIdentifier(host, rec, 'maybeShowQuicksetPrompt'),
    '11e. …and runs the existing item-7 Quick-Set prompt trigger (a queue is a like disposition)');
  // The F9 tally is shared, not twinned: ONE push site, called from both
  // like paths, with the same first-deck gate and ordinal bump.
  const fsLike = functionNamed(host, 'recordFirstSessionLike');
  const adv = functionNamed(host, 'advance');
  assert(!!fsLike && count(tradesCode, /fsLikesRef\.current\.push\(/g) === 1,
    '11f. exactly ONE first-session like tally site (recordFirstSessionLike)',
    'a second push site is a parallel tally that can drift from the deck\'s');
  assert(!!adv && referencesIdentifier(host, adv, 'recordFirstSessionLike')
    && !!rec && referencesIdentifier(host, rec, 'recordFirstSessionLike')
    && /firstSessionOn && job\?\.first_deck/.test(rec.getText())
    && /fsDispositionsRef\.current \+= 1;/.test(rec.getText()),
    '11g. BOTH like paths feed it — same refs, same first-deck gate, same disposition ordinal');
  // The adaptation moment: one trigger, fired from advance() OUTSIDE the
  // deferDeckAdvance fork (browse passes defer the deck advance but are
  // still dispositions) and from the queue-success like path.
  const adapt = functionNamed(host, 'maybeShowAdaptationMoment');
  assert(!!adapt && count(tradesCode, /adaptationMomentShownThisSession = true;/g) === 1
    && /FIRST_SESSION_MIN_DISPOSITIONS/.test(adapt.getText())
    && /FIRST_SESSION_MIN_SHARED_LIKES/.test(adapt.getText()),
    '11h. ONE adaptation trigger with the shipped thresholds (maybeShowAdaptationMoment)');
  assert(!!adv && referencesIdentifier(host, adv, 'maybeShowAdaptationMoment')
    && count(stripComments(adv.getText()), /deferDeckAdvance/g) === 3,
    '11i. advance() fires it on EVERY disposition — the deferDeckAdvance fork must not grow a guard around it',
    'exactly 3 deferDeckAdvance mentions in advance(): the param, the reason guard, the deck-advance line — a 4th means the browse-pass path was forked out');
  assert(!!rec && referencesIdentifier(host, rec, 'maybeShowAdaptationMoment'),
    '11j. …and the queue-success like path fires it too');
  // Render homes on the live host — shipped gates plus the host, the deck
  // slot\'s components/copy untouched, and the deck-slot originals intact.
  assert(/\{canvasResultsLive && quicksetPromptShown \? \(/.test(trades)
    && count(trades, /<QuickSetPromptCard/g) === 2,
    '11k. the Quick-Set prompt card has a host-gated mount above the canvas (deck-slot mount intact)',
    'the deck tree is nulled on this host, so exactly one of the two can ever render');
  assert(/: canvasResultsLive && adaptationMoment && topCard && !mutedForTour \? \(/.test(trades)
    && count(trades, /testID="trades\.adaptation-moment"/g) === 2,
    '11l. the adaptation moment has a host-gated mount with the shipped gate verbatim (plus the host)');
  // The Apple surfaces were already page-level — they must STAY ungated by
  // the host (the sheet is a root modal; the banner rides the page strip).
  assert(/\{appleBannerShown \? \(/.test(trades)
    && /<AppleSaveMomentSheet\s[\s\S]{0,200}?visible=\{!!appleAsk\}/.test(trades),
    '11m. the session-2 Apple banner and the save-moment sheet render page-level, host or not');
  // Reuse-only still holds: the hook fires no event of its own.
  assert(!!rec && !referencesIdentifier(host, rec, 'track'),
    '11n. recordCanvasQueueLike emits nothing itself — every event it causes is an existing moment\'s own');
}

// ═══════════════════════════════════════════════════════════════════════
// 12 — QA round (2026-08-29): session lifecycle at every dispatch,
//      inline-reset census, arrival adoption, prefill-ends-session, the
//      shop entry, frozen order, streaming narration, partner lock, baked
//      defaults. Each pin names the sabotage it would catch.
// ═══════════════════════════════════════════════════════════════════════
{
  // (a) DISPATCH CENSUS — 8 call sites + the definition, nothing raw.
  const calls = count(tradesCode, /dispatchGenerate\(/g);
  assert(calls === 9,
    '12a. dispatchGenerate: 8 routed dispatch sites + 1 definition (census pinned)',
    `saw ${calls} — a new site must be added to the helper's census table AND this count`);
  // (b) the first-run auto-start is the P0: it must create a session.
  assert(/autoGenRef\.current = 'kicked';[\s\S]{0,500}?dispatchGenerate\(\{ auto: true \}\)/.test(tradesCode),
    '12b. the first-run AUTO-START routes through dispatchGenerate (the B-C1 P0)',
    'a raw mutate here streams every new user\'s first deck into an invisible tree');
  assert(/autoRetryTimer\.current = null;\s*dispatchGenerate\(\{ auto: true \}\)/.test(tradesCode),
    '12c. …and so does its silent retry');
  // (d) the QuickSet regen kills the stale session BEFORE its inline clear.
  {
    const at = tradesCode.indexOf('consumePendingQuicksetRegen()');
    const seg = tradesCode.slice(at, at + 1600);
    const kill = seg.indexOf('setBrowseSession(null)');
    const clear = seg.indexOf('setDeck([])');
    const disp = seg.indexOf('dispatchGenerate(');
    assert(at > 0 && kill > -1 && clear > -1 && disp > -1 && kill < clear && clear < disp,
      '12d. QuickSet regen: session killed → deck cleared → dispatch (a stale session never adopts the regen deck)',
      'order matters: kill before clear before dispatch');
  }
  // (e) INLINE-RESET CENSUS — every setDeck([]) accounted for.
  assert(count(tradesCode, /setDeck\(\[\]\)/g) === 5,
    '12e. exactly 5 setDeck([]) sites (fairness toggle, league switch, clear-pin, QuickSet regen, the reset fn)',
    'a 6th inline reset shipped un-audited — add it to the census and kill the session there');
  for (const fn of ['handleToggleFairness', 'handleClearPin']) {
    const f = functionNamed(host, fn);
    assert(!!f && /setBrowseSession\(null\)/.test(f.getText())
      && /browseSeededIdRef\.current = null/.test(f.getText()),
      `12f. ${fn}'s inline reset explicitly kills the session (+ seeded-id ref)`);
  }
  // (g) A-D2 — the ARRIVAL direction adopts, never orphans.
  assert(/if \(canvasResultsLive && !browseSession && \(deck\.length > 0 \|\| !!job\)\) \{/.test(tradesCode)
    && /origin: fairDeck \? 'fair' : 'model',/.test(tradesCode),
    '12g. flag/host ARRIVAL over an existing deck (or live job) adopts it into a session',
    'without this the flag flipping true orphans a visible deck — the P0 shape again');
  // (h) B-C3 — a prefill over a live session ends the session first.
  {
    const f = functionNamed(host, 'loadCanvasPrefill');
    assert(!!f && /if \(browseLive\) \{\s*endBrowseSession\(p\);/.test(f.getText()),
      '12h. loadCanvasPrefill ends a live session (via the ONE reset) before seeding the canvas',
      'otherwise ✕/edits/✓ address a different trade than the canvas shows');
  }
  // (i) B-C4 — the shop entry on the browsed idea, one fork, one emitter.
  // #412 re-spec: the entry MOVED out of the pager row into the give column,
  // under its "Add player" button. Both halves are pinned — the old id is
  // gone (one entry, one placement) and the new one exists exactly once.
  assert(!trades.includes('testID="trades.canvas-results.more-offers"'),
    '12i. the pager no longer carries the "More offers" entry — it moved to the give column (#412)');
  assert(count(trades, /testID="calc\.give\.more-offers"/g) === 1,
    '12i-bis. …and the give-column entry exists exactly once',
    'two mounts is the double-entry the move was supposed to end');
  {
    const canvasAt = trades.indexOf('<TradeBuildCanvas');
    const moreAt = trades.indexOf('testID="calc.give.more-offers"');
    assert(canvasAt > 0 && moreAt > canvasAt,
      '12i2. …handed to the canvas as a prop, not rendered in the pager row');
    // The GATE is the rule's real content: absent with no session, because a
    // canvas-only page has no idea to shop (the deck chip stays the flag-off
    // entry). Whitespace-normalized — this is a multi-line prop expression.
    const gateAt = tradesCode.indexOf('giveBelowAdd={');
    const gate = gateAt > -1
      ? tradesCode.slice(gateAt, gateAt + 200).replace(/\s+/g, ' ')
      : '';
    assert(/^giveBelowAdd=\{ shopEnabled && browseLive && sortedDeck\.length > 0 && rawTopCard && rawTopCard\.give_players\.length > 0 \?/
      .test(gate),
      '12i2b. …still gated on the shop flags, a live session holding ideas, and a non-empty give side',
      'dropping the browse terms puts a "More offers" under Add player on every canvas, with no idea behind it');
    // T-13 — one column only. Shopping is a give-side verb (rev-3 §1); a
    // symmetric slot produces a meaningless receive-side entry.
    assert(count(calcCode, /belowAdd=/g) === 1,
      '12i2c. InLeagueCalculator hands the slot to exactly ONE TradeSide');
    const belowAt = calcCode.indexOf('belowAdd=');
    assert(belowAt > calcCode.indexOf('const give = (')
      && belowAt < calcCode.indexOf('const receive = ('),
      '12i2d. …and it is the GIVE column',
      'shop is a give-side verb — a receive-side "More offers" shops nothing');
    const fork = functionNamed(host, 'openShopForCard');
    assert(!!fork && referencesIdentifier(host, fork, 'openShopWindow')
      && referencesIdentifier(host, fork, 'setShopChooserCard')
      && !referencesIdentifier(host, fork, 'track'),
      '12i3. openShopForCard is the ONE entry fork (navigate vs chooser) and emits nothing itself');
    const keep = functionNamed(host, 'handleKeepSide');
    assert(!!keep && referencesIdentifier(host, keep, 'openShopForCard'),
      '12i4. the deck chip routes through the SAME fork — no parallel entry path');
    assert(count(tradesCode, /openShopForCard\(/g) === 3,
      '12i5. exactly two fork callers (deck chip + browse entry) + the definition',
      'shop_opened stays a single emitter inside openShopWindow (P-3; check-shop-deck h4)');
  }
  // (j) B-P5 — frozen order under browse.
  assert(/if \(canvasResultsOn && browseSession\) return pool;/.test(tradesCode),
    '12j. sortedDeck freezes to deck order while a session exists (appends land at the END, likes-you pinning stands down)',
    'a background re-sort remounts the canvas onto a DIFFERENT idea');
  {
    const f = functionNamed(host, 'applySessionRerank');
    assert(!!f && /if \(!fairnessOn \|\| laneFilter \|\| browseLive\) return;/.test(f.getText()),
      '12j2. session_rerank never reorders the browsed set (vector still accumulates)');
  }
  // (k) A-D4 — streaming narration while ideas already browse.
  {
    const at = trades.indexOf('testID="trades.canvas-results.streaming"');
    const seg = trades.slice(Math.max(0, at - 900), at + 600);
    assert(at > 0
      && /browseSession\?\.origin === 'model'/.test(seg)
      && /job\?\.status === 'running'/.test(seg)
      && /Searching… /.test(seg) && /opponents/.test(seg),
      '12k. a running model job with ideas on screen narrates ("Searching… N/M") beside the pager',
      'the X must never silently grow with no narration');
  }
  // (l) A-D5 — the partner is fixed while an idea is shown.
  assert(/partnerLocked=\{browseLive\}/.test(tradesCode),
    '12l. the host locks the partner exactly while browsing');
  assert(/partnerLocked\?: boolean;/.test(canvas) && /partnerLocked=\{partnerLocked\}/.test(canvasCode),
    '12l2. TradeBuildCanvas threads partnerLocked through (optional — every other host byte-identical)');
  assert(/partnerLocked\?: boolean;/.test(calc)
    && /testID="calc\.team-dropdown"[\s\S]{0,700}?disabled=\{partnerLocked\}/.test(calc)
    && /testID="calc\.partner-change"[\s\S]{0,700}?disabled=\{partnerLocked\}/.test(calc),
    '12l3. both partner controls go INERT (disabled), dimmed not hidden, under the lock',
    'this also kills the corrupted {give, receive: []} edit snapshot on partner change');
  // (m) QA-B nit — same-batch-safe browse removal.
  {
    const f = functionNamed(host, 'removeBrowsedIdea');
    assert(!!f && /browseDeckSyncRef\.current/.test(f.getText())
      && /setDeck\(\(prev\) => prev\.filter/.test(f.getText()),
      '12m. removeBrowsedIdea derives `remaining` from the synchronous mirror + functional setDeck',
      'a same-batch double-✕ against the render closure clamps the cursor one high');
  }
  // (n) #362 QA nit — the standing-offer prompt reaches browse likes.
  {
    const f = functionNamed(host, 'recordCanvasQueueLike');
    assert(!!f && referencesIdentifier(host, f, 'maybeShowStandingOfferPrompt'),
      '12n. queue success re-triggers the standing-offer ladder (its sheet mounts page-level)');
  }
  // (o) A-D1 — the launched pair is BAKED into the mobile defaults.
  {
    const flagsStore = read('state/useFeatureFlags.ts');
    const seg = flagsStore.slice(
      flagsStore.indexOf('LAUNCHED_FLAG_DEFAULTS'),
      flagsStore.indexOf('export const useFeatureFlags'),
    );
    assert(/'nav\.trades_landing': true,/.test(seg),
      '12o. nav.trades_landing baked true — the first-ever cold launch honors trades-landing',
      'the #115 convention: launched flags fail OPEN on fresh-install first boot / stale-cache first paint');
    assert(/'calc\.canvas_results': true,/.test(seg),
      '12o2. calc.canvas_results baked true — no deck-layout paint flip on first boot');
  }
}

console.log(failures === 0
  ? 'check-canvas-results: all assertions passed'
  : `check-canvas-results: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
