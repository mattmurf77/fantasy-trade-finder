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
  // Re-keyed 2026-09-03 (#417): 9 → 8. The legacy CTA arm now routes through
  // handleFindTrades instead of dispatching itself, so the deck lost a site;
  // the push still adds none.
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

// ═══════════════════════════════════════════════════════════════════════
// 8 — FB-417 (2026-09-03): a SECOND search cannot start from, or merge
//     into, the pushed anchored deck
//
// The operator built a give-side canvas, tapped Find a Trade, and the
// pushed deck's own always-mounted "Find a Trade" primary took a tap ~1s
// later (prod event stream: `find_trades_tapped {mode: deck}` with no
// `source`, 1s after the push, before the first card was viewed). That tap
// dispatched the UNANCHORED model job; its cards APPENDED to the fair deck
// and — fairness toggle off — sorted ABOVE it (fair cards carry
// `match_score: 0`), so the top card stopped being about his player while
// the "Built around X" receipt still said it was. Three structural facts
// close it, and none of them is visible to tsc:
//
//   • the anchored pushed deck renders NO page-level primary (its search
//     controls are the receipt's Change/Clear and the end-of-deck exits);
//   • every model dispatch that can start from a fair deck resets the deck
//     FIRST — anchored and model cards can never share one deck;
//   • the jobless fair sweep has an in-flight flag, because neither
//     `generateMutation.isPending` nor `job.status` is true while it runs.
//
// QA round 1 (2026-09-03) widened three of these and added two:
//   • the CTA is hidden for the WHOLE anchored lifecycle (B-5) — the sweep
//     window included — and the in-progress card fills that second (8, 8r);
//   • the deck-done card quotes a control that renders on THIS page (B-1,
//     the #316 rule) (8s);
//   • EVERY epoch bump disarms the in-flight flag, not just the reset (B-2,
//     the QuickSet-regen bump bypasses the reset on purpose) (8t);
//   • the anchored page's failure retry re-runs the ANCHORED search (B-3)
//     (8u);
//   • the fair-deck reset in handleFindTrades stays CONDITIONAL — a second,
//     unconditional one would make model "Find more trades" replace instead
//     of append (QA-A F-1) (8v).
// ═══════════════════════════════════════════════════════════════════════
{
  const flat = tradesCode.replace(/[ \t]+/g, ' ');

  // (a) the CTA is withheld on an ANCHORED pushed deck — both arms, one
  //     derivation, so the legacy and consolidated copies cannot drift.
  assert(/const findCtaHiddenForAnchoredDeck =\s*isResultsPushed && \(fairDeck \|\| fairSweepPending\);/
      .test(tradesCode)
    && count(tradesCode, /const findCtaHiddenForAnchoredDeck =/g) === 1,
    '8. ONE derivation of the anchored-deck CTA suppression, over the WHOLE anchored '
      + 'lifecycle (isResultsPushed && (fairDeck || fairSweepPending))',
    'a per-arm predicate is how the two copies of this button drift apart; and dropping '
    + 'the fairSweepPending disjunct (QA B-5) puts a greyed "Find a Trade" back under '
    + 'the card for the second the sweep takes — an invitation the page cannot honor');
  const gated = count(flat,
    /\{canvasHost !== 'flag' && !findCtaHiddenForAnchoredDeck \? \(\n?\s*<Button/g);
  assert(gated === 2,
    '8a. BOTH trades.find-btn arms are gated off on the anchored pushed deck',
    `saw ${gated} of 2 — an ungated arm re-opens the unanchored second search`);
  assert(count(tradesCode, /testID="trades\.find-btn"/g) === 2,
    '8b. …and both mounts still EXIST (this is a render gate, not a deletion)',
    'deleting an arm changes the flag-off page, which #417 may not do');
  // The controls that REPLACE it on that page must still be there: the
  // receipt's Change/Clear (Clear IS handleSearchAllTrades) and the
  // end-of-deck exits. A gate with nothing behind it strands the user.
  for (const id of ['trades.anchor-receipt.change', 'trades.anchor-receipt.clear',
                    'trades.deck-exhausted.back-to-calc',
                    'trades.deck-summary.search-all',
                    'trades.deck-exhausted.search-all',
                    'trades.deck-summary.back-to-calc']) {
    assert(trades.includes(`testID="${id}"`),
      `8c. the anchored deck's own search control survives: ${id}`,
      'hiding the CTA is only legal because these are the page\'s search controls');
  }

  // (b) a model dispatch that STARTS from a fair deck resets first.
  const hft = functionNamed(host, 'handleFindTrades');
  const hftText = hft ? stripComments(hft.getText()) : '';
  assert(/if \(fairDeck\) resetDeckForNewTargets\(\);/.test(hftText),
    '8d. handleFindTrades resets the deck when the current deck is a FAIR deck',
    'setFairDeck(false) alone drops the receipt and LEAVES the anchored cards — '
    + 'the model cards then append to them and outrank them (match_score 0)');
  const resetAt = hftText.indexOf('if (fairDeck) resetDeckForNewTargets();');
  const dispAt = hftText.indexOf('dispatchGenerate(');
  assert(resetAt > -1 && dispAt > resetAt,
    '8e. …BEFORE the dispatch (the reset opens the epoch the dispatch is stamped with)',
    'resetting after dispatchGenerate would kill the search it just started');
  // Stated explicitly because #417's reset is now on the manual search path:
  // the reset is DECK state only. Pins are the user's targets, and the very
  // next dispatch reads them out of the store (mutationFn) — clearing them
  // here would silently widen the search the user just asked for.
  const rstEarly = functionNamed(host, 'resetDeckForNewTargets');
  assert(!!rstEarly && !referencesIdentifier(host, rstEarly, 'useFinderTargets'),
    '8f. …and the reset does NOT touch the pin store (pins are targets, not deck state)',
    'a store clear inside the reset drops the targets the next search must honor');
  // The fair deck's own exit rides the same entry point, so "Search all
  // trades" / the receipt's Clear inherit the reset.
  const sat = functionNamed(host, 'handleSearchAllTrades');
  assert(!!sat && /handleFindTrades\(/.test(stripComments(sat.getText()))
    && !/dispatchGenerate\(/.test(stripComments(sat.getText())),
    '8g. handleSearchAllTrades still dispatches THROUGH handleFindTrades — so it resets too',
    'a private dispatch would merge the model deck into the anchored one again');

  // (c) the legacy arm cannot drift: it calls the shared entry point.
  const armAt = tradesCode.indexOf('testID="trades.find-btn"');
  const arm = tradesCode.slice(armAt, armAt + 700);
  assert(/onPress=\{\(\) => handleFindTrades\(\)\}/.test(arm) && !/dispatchGenerate\(/.test(arm),
    '8h. the legacy !consolidateOn arm dispatches through handleFindTrades, not a bare dispatchGenerate',
    'its own dispatch skipped setFairDeck(false), the #257 nudge clear AND the #417 reset');
  assert(count(tradesCode, /onPress=\{\(\) => handleFindTrades\(\)\}/g) === 2,
    '8i. …exactly as the consolidated arm does (one onPress shape for both)');

  // (d) the jobless sweep's in-flight flag, owned by the sweep.
  const rfp = functionNamed(host, 'runFairPackages');
  const rfpText = rfp ? stripComments(rfp.getText()) : '';
  assert(/if \(!leagueId\) return;\s*const epoch = deckEpochRef\.current;\s*setFairSweepPending\(true\);/
      .test(rfpText),
    '8j. runFairPackages marks itself in flight at ENTRY — after the leagueId early '
      + 'return, beside the epoch capture',
    'without it neither generateMutation.isPending nor job.status is true during the sweep '
    + '— every Find-a-Trade control stays live for the second it takes. Arming ABOVE the '
    + 'early return (QA-A F-2) strands the flag true with no sweep to clear it: no request '
    + 'was made, so neither exit runs, and every control stays disabled until a reset');
  assert(/setFairDeck\(true\);\s*setFairSweepPending\(false\);/.test(rfpText),
    '8k. …clears it on the success exit (after the #330 epoch guard)');
  assert(/setFairDeck\(false\);\s*setFairSweepPending\(false\);/.test(rfpText),
    '8l. …and on the failure exit (after the same guard)');
  assert(count(rfpText, /setFairSweepPending\(false\)/g) === 2
    && count(rfpText, /setFairSweepPending\(true\)/g) === 1,
    '8m. …exactly one arm and two disarms — a superseded sweep returns before both',
    'a disarm ahead of the epoch guard lets a dead sweep re-enable the controls of a live one');
  const rst = functionNamed(host, 'resetDeckForNewTargets');
  assert(!!rst && /setFairSweepPending\(false\);/.test(stripComments(rst.getText())),
    '8n. a deck reset also disarms the flag — a superseded sweep can never strand a disabled control',
    'the reset bumps the epoch, so that sweep will return without clearing the flag itself');

  // (e)/(f) the flag is actually read by the controls it exists for.
  const disabled = count(flat,
    /disabled=\{\n?\s*!leagueId \|\|\n?\s*generateMutation\.isPending \|\|\n?\s*job\?\.status === 'running' \|\|\n?\s*fairSweepPending\n?\s*\}/g);
  assert(disabled === 2,
    '8o. both CTA arms include fairSweepPending in `disabled` (the double-tap guard)',
    `saw ${disabled} of 2 — the window this closes is the ~1s between the push and the first card`);
  assert(/onFindATrade=\{\s*canvasHost === 'flag' && !fairSweepPending\s*\?\s*handleInlineFindATrade\s*:\s*undefined\s*\}/.test(trades),
    '8p. the landing canvas cell withholds its handler while a sweep is in flight',
    'InLeagueCalculator gates that cell on `!onFindATrade` — this IS its disabled state');

  // R-5 — #417 ships no flag of its own; `calc.results_push` (§1) stays the
  // only kill switch for this whole surface.
  assert(!/fairSweepPending|findCtaHiddenForAnchoredDeck/.test(readRoot('config/features.json')),
    '8q. #417 introduced no feature flag — calc.results_push remains the kill switch');

  // ── QA round 1 (2026-09-03) ────────────────────────────────────────────
  const squash = tradesCode.replace(/\s+/g, ' ');

  // (g) B-5 — the second the CTA is now hidden for is NARRATED, not blank.
  //     Without this the pushed page falls through the whole deck-tree
  //     ternary to the never-searched card and tells a user who just
  //     searched to search.
  assert(/generateMutation\.isPending \|\| job\?\.status === 'running' \|\| \(isResultsPushed && fairSweepPending\) \? \(/
      .test(squash)
    && /testID="trades\.empty-text"/.test(tradesCode),
    '8r. the pushed page renders the in-progress card while the jobless sweep runs',
    'the fair sweep has no job, so both signals above it are false — the deck tree '
    + 'falls through to \'Hit "Find a Trade" to start\', which is now not even a '
    + 'reachable instruction (the CTA is hidden). The never-searched card must SURVIVE '
    + 'for every other host, hence the second half');

  // (h) B-1 — #316: the deck-done card quotes a control, so on this page it
  //     must quote one that renders here. Both legacy sentences byte-identical.
  const anchoredDone = [
    'Fresh ideas land every week — or tap Clear on the receipt to search all trades.',
    'Fresh ideas land every week — or tap Search all trades to widen the search.',
  ];
  assert(/\{findCtaHiddenForAnchoredDeck \? inlineAnchorShown \?/.test(squash)
    && anchoredDone.every((c) => trades.includes(c))
    && anchoredDone.every((c) => !/Find a Trade|Find more trades/.test(c))
    && trades.includes('Fresh ideas land every week — or tap Find a Trade to search again now.')
    && trades.includes('Fresh ideas land every week — or tap Find more trades to search again now.'),
    '8s. the deck-done card names a control that RENDERS on the anchored pushed deck',
    'the receipt\'s Clear while the receipt is up, this card\'s own "Search all trades" '
    + 'when there is none — never the CTA #417 hides (#316: the copy follows whichever '
    + 'control actually renders). The landing and legacy sentences stay byte-identical');

  // (i) B-2 — the in-flight flag's invariant is "every epoch bump disarms".
  //     One of the two bump sites bypasses resetDeckForNewTargets on purpose.
  const bumps = [];
  for (let i = tradesCode.indexOf('deckEpochRef.current += 1;'); i > -1;
       i = tradesCode.indexOf('deckEpochRef.current += 1;', i + 1)) bumps.push(i);
  assert(bumps.length === 2
    && bumps.every((i) => /setFairSweepPending\(false\)/.test(tradesCode.slice(i, i + 400))),
    '8t. EVERY epoch bump disarms the in-flight flag — both sites, not just the reset',
    `saw ${bumps.length} bump site(s); a bump that skips the disarm supersedes the sweep, `
    + 'which then returns at its epoch guard WITHOUT clearing the flag — both CTA arms '
    + 'stay disabled for the life of the page (QA B-2: the QuickSet-regen focus effect)');

  // (j) B-3 — the anchored page's failure retry re-runs the ANCHORED search.
  const retryAt = squash.indexOf('testID="trades.deck-error.retry"');
  const retryBtn = retryAt > -1 ? squash.slice(retryAt, retryAt + 400) : '';
  assert(/onPress=\{\(\) => isResultsPushed && inlineAnchor \? void runFairPackages\(\{ giveIds: inlineAnchor\.giveIds, receiveIds: inlineAnchor\.receiveIds, \}\) : handleFindTrades\('deck_error_retry'\) \}/
      .test(retryBtn),
    '8u. a failed sweep\'s "Try again" retries the ANCHORED search on the pushed page',
    'handleFindTrades runs the UNANCHORED model job: the user asked for trades around '
    + 'his player, the network failed, and the retry would quietly answer a different '
    + 'question. Every other host keeps the model retry (the fallback arm)');

  // (k) QA-A F-1 — the fair-deck reset stays CONDITIONAL. An unconditional
  //     second one passes 8d/8e and silently breaks model "Find more trades".
  assert(count(hftText, /resetDeckForNewTargets\(/g) === 1,
    '8v. …and handleFindTrades resets EXACTLY ONCE, behind the `if (fairDeck)` guard',
    'a second, unconditional reset makes every "Find more trades" tap on a MODEL deck '
    + 'REPLACE the deck instead of appending to it — the one behavior R-2 promises not '
    + 'to touch, and invisible to 8d/8e');
}

console.log(failures === 0
  ? 'check-results-push: all assertions passed'
  : `check-results-push: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
