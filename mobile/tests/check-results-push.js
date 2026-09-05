#!/usr/bin/env node
// D-171 finder results push (flag `calc.results_push`) — structural guard.
// Spec: docs/plans/finder-results-push/scope.md (2026-08-31 operator
// rulings 1-5, verbatim in DECISIONS.md D-171).
//
// WHY THIS EXISTS. The operator ruled the merged Trades landing is the
// BUILDER only: Find a Trade PUSHES a full-screen classic deck page
// (`TradeDeck` + a `resultsPush` route param), the D-153 fork is preserved
// but both paths land on the pushed deck, "Edit in calculator" POPS back to
// the landing with the trade prefilled, ✓/✕ on the pushed deck are the
// classic swipe paths, and the whole thing ships LIT with this flag as the
// kill switch. Nearly every failure mode is invisible to tsc:
//
//   • the push could stop carrying the fork verdict (anchor/scope) and the
//     pushed deck would re-price the canvas differently than the landing;
//   • the landing could quietly keep consuming its own search (a browse
//     session, or a deck streamed into the retired tree — the QA B-C1
//     invisible-deck shape via the auto-start or a scoped team pick);
//   • the pushed instance could mount the canvas (its mode is 'guided' and
//     the flag is on — only the param suppression prevents a second canvas);
//   • "Edit in calculator" could navigate() instead of popTo() — G-056:
//     navigate PUSHES a second TradesHome, stranding the user's build;
//   • Back to calculator could carry the pin-derived prefill, which on a
//     fair deck is EMPTY and would clear the landing canvas;
//   • the kill switch could rot: flag-off must fall through to the
//     in-place consumption (the calc.canvas_results branch), byte-identical.
//
// Run: node tests/check-results-push.js   (or: npm run test:results-push)

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
const tabNav = read('navigation/TabNav.tsx');

const host = ts.createSourceFile(
  'TradesScreen.tsx',
  trades,
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

console.log('check-results-push:');

// ═══════════════════════════════════════════════════════════════════════
// 1 — the flag: registered everywhere, LIT (ruling 5 — explicit operator
//     override of the dark-flag recommendation), baked into the defaults
// ═══════════════════════════════════════════════════════════════════════
{
  const features = JSON.parse(readRoot('config/features.json'));
  assert(features['calc.results_push'] === true,
    '1. calc.results_push is LIT in config/features.json (ruling 5, D-171)');
  assert(typeof features['_comment_results_push'] === 'string'
    && /finder-results-push\/scope\.md/.test(features['_comment_results_push'])
    && /KILL SWITCH/i.test(features['_comment_results_push'])
    && /calc\.inline_home/.test(features['_comment_results_push'])
    && /calc\.merged_layout/.test(features['_comment_results_push']),
    '1a. …with a comment naming the spec, the kill switch and both prerequisites');
  for (const f of ['release', 'onboarding-v2', 'profiles-on']) {
    const j = JSON.parse(readRoot(`backend/tests/fixtures/flags/${f}.json`));
    assert(j['calc.results_push'] === true,
      `1b. backend/tests/fixtures/flags/${f}.json mirrors it true (G-062 four-file flip)`);
  }
  assert(/"calc\.results_push",/.test(readRoot('backend/feature_flags.py')),
    '1c. the key is registered in backend FLAG_KEYS',
    'an unregistered key fails test_features_json_keys_known and never ships to clients');
  const flagsStore = read('state/useFeatureFlags.ts');
  const seg = flagsStore.slice(
    flagsStore.indexOf('LAUNCHED_FLAG_DEFAULTS'),
    flagsStore.indexOf('export const useFeatureFlags'),
  );
  assert(/'calc\.results_push': true,/.test(seg),
    '1d. baked true in LAUNCHED_FLAG_DEFAULTS — no in-place-search paint flip on first boot (#115 convention)');
}

// ═══════════════════════════════════════════════════════════════════════
// 2 — gating: one flag read, host-scoped live gates, never the bare flag
// ═══════════════════════════════════════════════════════════════════════
{
  assert(/const resultsPushOn = useFlag\('calc\.results_push'\);/.test(trades)
    && count(tradesCode, /useFlag\('calc\.results_push'\)/g) === 1,
    '2. TradesScreen reads the flag exactly once');
  assert(/const resultsPushLive = resultsPushOn && canvasHost === 'flag';/.test(trades)
    && count(tradesCode, /const resultsPushLive =/g) === 1,
    '2a. ONE live gate: the flag AND the flag-hosted landing — never the bare flag',
    'a bare-flag gate would leak push behavior onto team/player modes and the pushed instance');
  assert(/const landingDeckRetired = canvasResultsLive \|\| resultsPushLive;/.test(trades),
    '2b. the landing-retire derivation includes the push posture (ruling 1: builder only)');
  // The kill-switch fallback: canvasResultsLive derivation untouched, so
  // results_push:false + canvas_results:true restores in-canvas browsing.
  assert(/const canvasResultsLive = canvasResultsOn && canvasHost === 'flag';/.test(trades),
    '2c. the in-canvas restore path is intact (canvasResultsLive derivation unchanged)',
    'kill switch = calc.results_push false (+ calc.canvas_results true) — the old gate must survive');
}

// ═══════════════════════════════════════════════════════════════════════
// 3 — the push carries the FORK: verdict, anchor, scope, origin, label
// ═══════════════════════════════════════════════════════════════════════
{
  const fn = functionNamed(host, 'handleInlineFindATrade');
  assert(!!fn, '3. handleInlineFindATrade exists');
  const text = fn ? stripComments(fn.getText()) : '';
  // The shared D-153 fork still decides (and emits) BEFORE the push fork.
  const forkAt = text.indexOf('forkCanvasSearch(');
  const pushAt = text.indexOf("navigation?.push?.('TradeDeck'");
  assert(forkAt > -1 && pushAt > forkAt,
    '3a. forkCanvasSearch runs first — the D-153 verdict (and its one calc_find_a_trade_tapped row) is decided before the push',
    'pushing before forking would lose the shared pricing decision and the analytics');
  assert(/if \(resultsPushLive\) \{/.test(text)
    && /return;/.test(text.slice(text.indexOf('if (resultsPushLive) {'), pushAt + 900)),
    '3b. the push arm is gated on resultsPushLive and RETURNS — the landing never also consumes the search');
  const payload = text.slice(pushAt, pushAt + 500).replace(/\s+/g, ' ');
  assert(/mode: 'guided'/.test(payload),
    '3c. the push lands in guided mode');
  for (const k of ['seq:', 'opponent: fork.opponent', "origin: 'calculator'", 'fairAnchor: fork.anchor', 'anchorLabel:']) {
    assert(payload.includes(k),
      `3d. the resultsPush payload carries ${k.replace(/:.*/, '')} (${k})`,
      'the pushed deck re-prices nothing: verdict, anchor and scope all ride the param');
  }
  assert(!!fn && !referencesIdentifier(host, fn, 'track'),
    '3e. the handler emits nothing of its own — forkCanvasSearch owns the row (both postures)');
  // The kill-switch arm: the in-place consumption survives verbatim below
  // the fork (origin stamp, ref arming, the choke-point trigger).
  assert(/setDeckOrigin\('calculator'\)/.test(text)
    && /fairAnchorRef\.current = fork\.anchor;/.test(text)
    && /autoRunPendingRef\.current = !fork\.anchor;/.test(text)
    && /setCanvasRunSeq\(\(n\) => n \+ 1\);/.test(text),
    '3f. the in-place arm survives below the fork — flag off falls through to it byte-identically');
  // A store handoff (league-rankings Offer, flag-off calculator page)
  // FORWARDS into the same push instead of dispatching into the retired tree.
  const fwdAt = tradesCode.indexOf('if (resultsPushLive && finderHubOn && finderMode) {');
  const fwd = fwdAt > -1 ? tradesCode.slice(fwdAt, fwdAt + 800).replace(/\s+/g, ' ') : '';
  assert(fwdAt > -1
    && /navigation\?\.push\?\.\('TradeDeck', \{/.test(fwd)
    && /opponent: finderHandoff\.opponent/.test(fwd)
    && /fairAnchor: fwdFair/.test(fwd),
    '3g. a consumed store handoff forwards into the push on the retired landing',
    'consuming it in place streams a deck into a tree the landing no longer renders (the B-C1 shape)');
}

// ═══════════════════════════════════════════════════════════════════════
// 4 — the pushed instance: no canvas, one consumption, one dispatch path
// ═══════════════════════════════════════════════════════════════════════
{
  // Param presence (not the flag) suppresses the canvas host, first arm.
  const at = trades.indexOf("const canvasHost: 'flag' | 'experiment' | null =");
  const seg = trades.slice(at, at + 900);
  assert(/isResultsPushed\s*\n?\s*\? null/.test(seg),
    '4. the pushed instance mounts NO canvas — param presence nulls canvasHost ahead of both arms (ruling 2)',
    'a guided pushed instance with the flag on would otherwise mount a second canvas');
  assert(/const isResultsPushed = finderHubOn && !!resultsPushParam;/.test(trades),
    '4a. pushed-ness is derived from the route param, once');
  // The consumption: seq-guarded one-shot into the calculator-arrival refs,
  // triggering the ONE #330 choke point — no new dispatch site.
  assert(/consumedResultsPushSeqRef\.current === rp\.seq/.test(tradesCode),
    '4b. consumption is seq-guarded (the param is deliberately never cleared — clearing would remount the canvas)');
  assert(!/resultsPush: undefined/.test(tradesCode),
    '4c. …and nothing clears the param',
    'setParams({resultsPush: undefined}) would flip canvasHost back to flag mid-session');
  const consumeAt = tradesCode.indexOf('consumedResultsPushSeqRef.current = rp.seq;');
  const consume = consumeAt > -1 ? tradesCode.slice(consumeAt, consumeAt + 1200) : '';
  assert(/setDeckOrigin\(rp\.origin === 'calculator' \? 'calculator' : null\)/.test(consume),
    '4d. deck origin follows the param — calculator pushes keep the overlay/exits, forwarded offers keep tiles (ruling 4)');
  assert(/fairAnchorRef\.current = anchor;/.test(consume)
    && /autoRunPendingRef\.current = !anchor;/.test(consume)
    && /setCanvasRunSeq\(\(n\) => n \+ 1\);/.test(consume),
    '4e. it arms exactly the calculator-arrival refs and triggers the ONE choke point',
    'the D-153 fork (fair sweep vs model job) is taken at the same single dispatch site as ever');
  assert(count(tradesCode, /generateMutation\.mutate\(/g) === 1
    && count(tradesCode, /dispatchGenerate\(/g) === 8,
    '4f. no new generate dispatch site — the push added zero mutate paths');
  assert(/setInlineAnchor\(/.test(consume) && /anchorLabel/.test(consume),
    '4g. the anchor receipt is seeded from the param — "Built around X" tops the pushed deck (ruling 2)');
  // The receipt renders on the pushed deck too.
  assert(/const inlineAnchorShown =\s*\n?\s*\(canvasHost === 'flag' \|\| isResultsPushed\) && fairDeck && !!inlineAnchor;/.test(trades),
    '4h. inlineAnchorShown includes the pushed arm');
  // The header: pushed TradeDeck gets the always-on back control; the
  // deep-link (param-less) instance keeps its historical headerless render.
  assert(/name="TradeDeck"/.test(tabNav)
    && /route\.params as any\)\?\.resultsPush\s*\n?\s*\? subScreenOptions\('Trade ideas', 'TradesHome'\)/.test(tabNav)
    && /: \{ headerShown: false \}/.test(tabNav),
    '4i. TabNav forks the TradeDeck header on the param — back control for the pushed deck, headerless deep link');
}

// ═══════════════════════════════════════════════════════════════════════
// 5 — the pops: Edit-in-calculator carries the prefill; Back doesn't;
//     both use popTo (G-056 — navigate would push a second TradesHome)
// ═══════════════════════════════════════════════════════════════════════
{
  const pop = functionNamed(host, 'popToLanding');
  assert(!!pop, '5. popToLanding exists');
  const popText = pop ? stripComments(pop.getText()) : '';
  assert(/navigation\?\.popTo\?\.\(\s*'TradesHome',/.test(popText),
    '5a. it pops (POP_TO, routers 7.5.3 StackRouter:349-421) — never navigate (G-056)');
  assert(!!pop && !referencesIdentifier(host, pop, 'navigate')
    && !referencesIdentifier(host, pop, 'push'),
    '5b. …and reaches for no other navigation verb');
  assert(/canvasPrefill: prefill, canvasPrefillSeq: Date\.now\(\)/.test(popText),
    '5c. a prefill rides the MatchesScreen route-param bridge (canvasPrefill/canvasPrefillSeq)',
    'the landing already consumes exactly this shape into loadCanvasPrefill');
  // Edit-in-calculator (and every canvas load) on the pushed instance pops
  // WITH the package: the loader itself forks, so all its callers are covered.
  const loader = functionNamed(host, 'loadCanvasPrefill');
  const loaderText = loader ? stripComments(loader.getText()) : '';
  assert(/if \(isResultsPushed\) \{\s*popToLanding\(p\);\s*return;\s*\}/.test(loaderText),
    '5d. loadCanvasPrefill forks FIRST on the pushed instance — every edit-in-calculator hand-off pops with the prefill (ruling 3)',
    'the pushed instance mounts no canvas; seeding local state there would silently drop the package');
  // Back to calculator: a PLAIN pop. The pin-derived prefill on a fair deck
  // is empty and would clear the landing canvas.
  const back = functionNamed(host, 'handleBackToCalculator');
  const backText = back ? stripComments(back.getText()) : '';
  assert(/if \(isResultsPushed\) \{\s*popToLanding\(\);\s*return;\s*\}/.test(backText),
    '5e. Back to calculator pops WITHOUT a prefill (ruling 4 — the landing canvas still holds the build)');
  // The receipt's Change on the pushed deck is the same plain pop.
  const change = functionNamed(host, 'handlePushedAnchorChange');
  assert(!!change && /popToLanding\(\);/.test(change.getText()),
    '5f. the receipt\'s Change pops back to the canvas that still holds the anchor');
  assert(/onPress=\{\s*canvasResultsLive\s*\?\s*handleBrowseAnchorChange\s*:\s*isResultsPushed\s*\?\s*handlePushedAnchorChange\s*:\s*handleAnchorChange\s*\}/.test(trades),
    '5g. …wired as the receipt\'s pushed arm');
  assert(/onPress=\{canvasResultsLive \? handleBrowseClear : handleSearchAllTrades\}/.test(trades),
    '5h. the receipt\'s Clear on the pushed deck stays handleSearchAllTrades — drop the anchor, model-search in place');
}

// ═══════════════════════════════════════════════════════════════════════
// 6 — the landing is the BUILDER only: no browse session, no dispatches
// ═══════════════════════════════════════════════════════════════════════
{
  // No browse session can start: the only session-creation sites are the
  // choke point's fair branch and dispatchGenerate, both behind
  // canvasResultsLive — dark — and the landing dispatches neither anyway.
  const chokeGuardAt = tradesCode.indexOf('if (resultsPushLive) {\n      fairAnchorRef.current = null;');
  const chokeGuard = chokeGuardAt > -1 ? tradesCode.slice(chokeGuardAt, chokeGuardAt + 400) : '';
  assert(chokeGuardAt > -1
    && /autoRunPendingRef\.current = false;/.test(chokeGuard)
    && /finderScopeSeen\.current = true;/.test(chokeGuard)
    && /return;/.test(chokeGuard),
    '6. the choke point returns before ANY dispatch on the push-posture landing (refs cleared defensively)',
    'a scoped team pick would otherwise stream a deck into the retired tree');
  // Position matters: the guard must sit between the reset and the fair
  // fork, so the reset still runs and the dispatches never do.
  const fairForkAt = tradesCode.indexOf('const fairAnchor = fairAnchorRef.current;');
  assert(chokeGuardAt > -1 && fairForkAt > chokeGuardAt,
    '6a. …and it sits BEFORE the fair fork / model gate');
  assert(/if \(resultsPushLive \|\| isResultsPushed\) return;/.test(tradesCode),
    '6b. the first-run auto-start refuses on both surfaces (builder-only landing; the pushed deck brings its own search)');
  assert(/if \(queued && !alreadyQueued && landingDeckRetired\) recordCanvasQueueLike\(\);/.test(tradesCode),
    '6c. the landing ✓ keeps its G22 like moment under the push posture (current queue behavior preserved)');
}

// ═══════════════════════════════════════════════════════════════════════
// 7 — analytics scope: reuse only
// ═══════════════════════════════════════════════════════════════════════
{
  assert(!/results_push/.test(readRoot('backend/analytics_taxonomy.py')),
    '7. no new analytics event was registered — calc_find_a_trade_tapped / find_trades_tapped and the deck\'s own events cover it');
}

console.log(failures === 0
  ? 'check-results-push: all assertions passed'
  : `check-results-push: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
