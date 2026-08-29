#!/usr/bin/env node
// D-158 / Wave B0 — "the guided tab becomes the merged In-league page".
//
// What this guard is for: the whole wave ships DARK behind `calc.inline_home`,
// and the ONE claim that makes shipping it dark safe is that with the flag
// false every surface renders exactly as it did. That claim is a property of
// the SHAPE of the code (one flag read, one gated branch per site), so it is
// checkable without a device — which matters, because under D-056 the only
// runtime proof mobile gets is a manual TestFlight pass.
//
// Run: node tests/check-inline-home.js

'use strict';

const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..', '..');
const SRC = path.join(__dirname, '..', 'src');
let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}`); if (detail) console.log(`      ${detail}`); }
}
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const readRoot = (r) => fs.readFileSync(path.join(ROOT, r), 'utf8');
const count = (s, re) => (s.match(re) || []).length;
// Several assertions below are "this name appears NOWHERE in this file" —
// which the file's own explanatory comments would otherwise falsify. Same
// helper `check-offer-prefill-330.js` uses, for the same reason.
const stripComments = (t) =>
  t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

const trades = read('screens/TradesScreen.tsx');
const calcScreen = read('screens/TradeCalculatorScreen.tsx');
const canvas = read('components/TradeBuildCanvas.tsx');
const modeBar = read('components/TradeFinderModeBar.tsx');
const fork = read('utils/canvasSearch.ts');
const queueUtil = read('utils/queueCalcTrade.ts');
const tradesCode = stripComments(trades);
const calcCode = stripComments(calcScreen);
const canvasCode = stripComments(canvas);

console.log('check-inline-home:');

// ═══════════════════════════════════════════════════════════════════════
// 1 — the flag exists, is LIT, and is mirrored everywhere it must be
//     (shipped dark 2026-08-24; LIT 2026-08-28 by operator ruling — "I'm
//     good merging the combined UI without the tour" — with
//     onboarding.guide_v2 turned false in the same commit, so the
//     "unfinished tour story" the dark pin guarded against cannot render.
//     TRUE is now the pinned contract; a flip back to false is a
//     deliberate revert and must change these lines with it.)
// ═══════════════════════════════════════════════════════════════════════
{
  const features = JSON.parse(readRoot('config/features.json'));
  assert(features['calc.inline_home'] === true,
    '1. calc.inline_home is LIT in config/features.json (2026-08-28 ruling)',
    'the operator lit the merge tour-free; a false here is an unledgered revert');
  assert(typeof features['_comment_inline_home'] === 'string'
    && /D-158/.test(features['_comment_inline_home'])
    && /kill switch/i.test(features['_comment_inline_home']),
    '1a. …with a comment naming D-158 and the kill switch');
  // The exact-mirror test (backend/tests/test_seed_ui_test_db.py) only covers
  // release.json; the other two profiles are what the onboarding and
  // profile-seeded suites boot from, and a key missing there is a flag that
  // silently reads `undefined` in a test that thinks it is exercising release.
  for (const f of ['release', 'onboarding-v2', 'profiles-on']) {
    const j = JSON.parse(readRoot(`backend/tests/fixtures/flags/${f}.json`));
    assert(j['calc.inline_home'] === true,
      `1b. backend/tests/fixtures/flags/${f}.json mirrors it true`);
  }
  assert(/"calc\.inline_home",/.test(readRoot('backend/feature_flags.py')),
    '1c. the key is registered in backend DEFAULT_FLAGS',
    'an unregistered key fails test_features_json_keys_known and never ships to clients');
}

// ═══════════════════════════════════════════════════════════════════════
// 2 — ONE canvas mount, and flag-off it is the #270 experiment's or nothing
// ═══════════════════════════════════════════════════════════════════════
{
  assert(count(tradesCode, /<TradeBuildCanvas/g) === 1,
    '2. TradesScreen mounts the canvas exactly once',
    'two mounts is two live drafts of the same trade — the flag path and the '
    + 'experiment variant must resolve to ONE host, not two branches');
  assert(/const canvasHost: 'flag' \| 'experiment' \| null =/.test(trades),
    '2a. the host is resolved once, into a named three-state value');
  const at = trades.indexOf("const canvasHost: 'flag' | 'experiment' | null =");
  const seg = trades.slice(at, at + 500);
  // Precedence: the FLAG arm is first, so a unit holding both the flag and the
  // #270 assignment renders the layout, not the experiment.
  assert(/inlineHomeOn && finderMode === 'guided' && leagueId\s*\n?\s*\? 'flag'/.test(seg),
    '2b. the flag path wins when both would render',
    'the experiment overlay must not outrank the shipped layout');
  assert(/homeInlineVariant === 'canvas' &&[\s\S]{0,200}?\? 'experiment'/.test(seg),
    "2c. the 'experiment' arm still requires the #270 variant",
    'flag off, the ONLY way a canvas renders is an assigned experiment unit');
  assert(/!firstRun &&[\s\S]{0,80}?!singlePin/.test(seg),
    "2d. the experiment arm keeps its original first-run / single-pin exclusions",
    'the experiment path must be byte-identical for its assigned units');
  assert(/const inlineHomeOn = useFlag\('calc\.inline_home'\);/.test(trades)
    && count(tradesCode, /useFlag\('calc\.inline_home'\)/g) === 1,
    '2e. TradesScreen reads the flag exactly once');
}

// ═══════════════════════════════════════════════════════════════════════
// 3 — what the flag path changes about the canvas, and nothing else
// ═══════════════════════════════════════════════════════════════════════
{
  const at = trades.indexOf('<TradeBuildCanvas');
  const seg = trades.slice(at, at + 900);
  assert(/showSuggestionRail=\{canvasHost === 'experiment'\}/.test(seg),
    "3. the rail dies on the flag path and survives on the experiment's",
    'the deck below IS the rail (plan §3b); the experiment keeps its strip');
  assert(/showSuggestionRail\?: boolean/.test(canvas)
    && /showSuggestionRail = true/.test(canvas),
    '3a. …and the prop DEFAULTS to today\'s behavior',
    'a default of false would silently delete the experiment variant\'s rail');
  assert(/\{showSuggestionRail && suggestions\.length > 0 \?/.test(canvas),
    '3b. the rail render is gated on it');
  assert(/onFindATrade=\{\s*canvasHost === 'flag' \? handleInlineFindATrade : undefined\s*\}/.test(seg),
    '3c. the flag path wires Find a Trade; the experiment path does not');
  assert(/onLikeTrade=\{\s*canvasHost === 'flag' \? handleInlineLikeTrade : undefined\s*\}/.test(seg),
    '3d. …and the ✓ cell, same gate');
  // Wave B0 explicitly ships WITHOUT the tour: beat n10 ("Tap In league")
  // points at the tab this wave deletes. Passing an opener would offer a walk
  // whose first beat cannot advance.
  assert(!/onShowMeAround/.test(canvasCode) && !/onShowMeAround/.test(seg),
    '3e. the inline canvas is mounted with NO Show-me-around',
    'the tour is Wave B; an opener here starts a runner that cannot clear n10');
}

// ═══════════════════════════════════════════════════════════════════════
// 4 — the tour is suppressed on the pushed page while the flag is on
// ═══════════════════════════════════════════════════════════════════════
{
  assert(/const inlineHomeOn = useFlag\('calc\.inline_home'\);/.test(calcScreen)
    && count(calcCode, /useFlag\('calc\.inline_home'\)/g) === 1,
    '4. TradeCalculatorScreen reads the flag exactly once');
  assert(/if \(!calcMergedOn \|\| prefill \|\| !hasLeague \|\| inlineHomeOn\) return;/.test(calcScreen),
    '4a. the auto-start refuses under the flag',
    'suppressing at the START is the whole suppression — no runner, no hold, no beat');
  assert(/\}, \[calcMergedOn, prefill, hasLeague, inlineHomeOn, navigation\]\);/.test(calcScreen),
    '4b. …and the guard is a dep, so it is not frozen at first render');
  assert(/onShowMeAround=\{\s*!inlineHomeOn && guidedAvatarActive\(\) && guideV2Active\(\)/.test(calcScreen),
    '4c. the "Show me around" re-entry refuses under the flag too',
    'auto-start and re-entry are two doors into the same dead first beat');
  // Wave A owns the tour files; this wave must not have touched them.
  assert(!/calc\.inline_home/.test(read('utils/calcTour.ts')),
    '4d. the tour RUNNER is untouched — suppression lives in the screen gating');
}

// ═══════════════════════════════════════════════════════════════════════
// 5 — the pushed page is Real values only under the flag
// ═══════════════════════════════════════════════════════════════════════
{
  assert(/\{inlineHomeOn \? null : \(\s*\n?\s*<View style=\{styles\.modeRow\}>/.test(calcScreen),
    '5. the mode-tab row is gone under the flag');
  assert(/\{!inlineHomeOn && mode === 'league' && league && user \?/.test(calcScreen),
    '5a. the In-league branch cannot render under the flag');
  assert(/prefill && !inlineHomeOn \? 'league' : 'live'/.test(calcScreen),
    '5b. a prefilled arrival no longer lands in In-league mode under the flag',
    'the deck prefills the INLINE canvas now; this page has no league mode to land in');
  assert(/if \(prefillKey && !inlineHomeOn\) setMode\('league'\);/.test(calcScreen),
    '5c. …and the re-assert on a second prefill is gated the same way');
}

// ═══════════════════════════════════════════════════════════════════════
// 6 — the fork is SHARED: one function, two callers, no second emitter
// ═══════════════════════════════════════════════════════════════════════
{
  assert(count(fork, /export function forkCanvasSearch/g) === 1,
    '6. forkCanvasSearch is defined exactly once');
  assert(/const fair = giveIds\.length > 0;/.test(fork),
    '6a. the fork is still decided by the GIVE side alone (D-153)');
  assert(/forkCanvasSearch\(/.test(calcScreen) && /forkCanvasSearch\(/.test(trades),
    '6b. BOTH hosts call it — the pushed page and the inline landing');
  assert(count(fork, /track\(\s*\n?\s*'calc_find_a_trade_tapped'/g) === 1,
    '6c. exactly one calc_find_a_trade_tapped emitter, and it is the shared fork');
  assert(!/calc_find_a_trade_tapped/.test(calcCode)
    && !/calc_find_a_trade_tapped/.test(tradesCode),
    '6d. neither host emits it inline',
    'a second emitter is a second fork decision in disguise');
  // Same rule for the ✓ queue (D-152).
  assert(count(queueUtil, /export async function queueCalcTrade/g) === 1,
    '6e. queueCalcTrade is defined exactly once');
  assert(/queueCalcTrade\(\{/.test(calcScreen) && /queueCalcTrade\(\{/.test(trades),
    '6f. both hosts call it');
  assert(!/queueTradeForOpponent\(/.test(calcCode) && !/queueTradeForOpponent\(/.test(tradesCode),
    '6g. neither host calls the queue route directly');
  // NO NEW EVENTS is a scope commitment, not a preference: the wave adds no
  // taxonomy row, so any `track('…')` name introduced on these surfaces would
  // be silently stripped by ingest behind a 200.
  assert(!/inline_home/.test(readRoot('backend/analytics_taxonomy.py')),
    '6h. no new analytics event was registered for this wave');
}

// ═══════════════════════════════════════════════════════════════════════
// 7 — in-place Find a Trade: no navigation, no handoff, ONE dispatch site
// ═══════════════════════════════════════════════════════════════════════
{
  const at = trades.indexOf('function handleInlineFindATrade(');
  assert(at > -1, '7. the inline Find a Trade handler exists');
  const seg = trades.slice(at, at + 1600);
  assert(!/navigation/.test(seg),
    '7a. it does not navigate',
    'the canvas and the deck are on ONE screen now — a push is the retired flow');
  assert(!/setHandoff\(/.test(seg),
    '7b. it writes no FinderHandoff',
    'the store lane, the consume-once dance and the G-056 popTo trap all retire here');
  assert(/setDeckOrigin\('calculator'\)/.test(seg),
    "7c. it stamps the deck's origin as the calculator",
    'this is what keeps the ✕→overlay and the calculator-first end-of-deck exits '
    + 'legal on an inline-built deck (#384 review #7)');
  assert(/fairAnchorRef\.current = fork\.anchor;/.test(seg)
    && /autoRunPendingRef\.current = !fork\.anchor;/.test(seg),
    '7d. it arms exactly the refs a calculator hand-off arrived with',
    'the two arms stay mutually exclusive at the source');
  assert(/setCanvasRunSeq\(\(n\) => n \+ 1\);/.test(seg),
    '7e. …and triggers the ONE #330 choke point rather than dispatching itself');
  // Re-keyed 2026-08-29 (canvas-results QA round): the 8 dispatch sites now
  // route through the ONE dispatchGenerate helper so the browse-session
  // lifecycle rides every dispatch (check-canvas-results §12 census). The
  // no-new-site invariant is unchanged — it just counts the helper's calls.
  assert(count(tradesCode, /generateMutation\.mutate\(/g) === 1
    && count(tradesCode, /dispatchGenerate\(/g) === 9,
    '7f. no new generate dispatch site was added (1 raw mutate in the helper; 8 routed sites + definition)',
    'a second site is a second search per tap waiting to happen');
  assert(/\}, \[finderMode, scopedOpponent, autoRunSeq, canvasRunSeq\]\);/.test(trades),
    '7g. the choke point lists the inline trigger as a dep');
  assert(count(tradesCode, /setAutoRunSeq\(/g) === 1,
    '7h. the store-driven seq still has exactly one writer',
    'the inline path uses its OWN seq so a bump here cannot collide with a handoff seq');
}

// ═══════════════════════════════════════════════════════════════════════
// 8 — the anchor receipt, and what it replaces
// ═══════════════════════════════════════════════════════════════════════
{
  assert(/testID="trades\.anchor-receipt"/.test(trades),
    '8. the receipt exists');
  assert(/testID="trades\.anchor-receipt\.change"/.test(trades)
    && /testID="trades\.anchor-receipt\.clear"/.test(trades),
    '8a. …with both actions');
  assert(/const inlineAnchorShown = canvasHost === 'flag' && fairDeck && !!inlineAnchor;/
    .test(trades),
    '8b. it renders only for a flag-path, anchored deck',
    'gated on `fairDeck`, which every path that starts or invalidates a model '
    + 'search already clears — so the label cannot outlive its deck');
  {
    // RE-KEYED by #402 canvas-results (spec §2, ruling 1): under a LIVE
    // browse session Clear ENDS the session (handleBrowseClear → the blank
    // canvas), it no longer runs the model — while the flag-off / no-session
    // arm must still be the fair deck's own Search-all handler, verbatim.
    // Both halves pinned so neither semantics can silently absorb the other.
    const at = trades.indexOf('testID="trades.anchor-receipt.clear"');
    const seg = trades.slice(at, at + 900);
    assert(/onPress=\{canvasResultsLive \? handleBrowseClear : handleSearchAllTrades\}/.test(seg),
      '8c. Clear: browse sessions end (handleBrowseClear); otherwise the fair deck\'s own Search-all handler, verbatim',
      'a second "drop the anchor" implementation is a second set of semantics — '
      + 'and a session Clear that still model-searches ignores ruling 1');
  }
  // RE-KEYED by #402 canvas-results: while a session is live the canvas holds
  // the browsed IDEA, so Change forks to handleBrowseAnchorChange (end the
  // session, hand the ANCHOR build back to the canvas); the flag-off arm
  // keeps the shipped scroll-to-canvas behavior byte-identically.
  assert(/onPress=\{canvasResultsLive \? handleBrowseAnchorChange : handleAnchorChange\}/.test(trades)
    && /mainScrollRef\.current\?\.scrollTo\(\{ y: canvasY\.current, animated: true \}\)/
      .test(trades),
    '8d. Change: browse sessions restore the anchor build; otherwise the shipped scroll to the canvas that still holds the assets');
  // The receipt REPLACES the end-of-deck exit for an inline-anchored deck —
  // the same action twice on one screen is what this stands aside for.
  assert(/calcMergedOn && fairDeck && !inlineAnchorShown \?/.test(trades),
    '8e. the deck-summary "Search all trades" steps aside for the receipt');
  assert(/\{fairDeck && !inlineAnchorShown \?/.test(trades),
    '8f. …and so does the deck-exhausted one');
  assert(/backgroundColor: flare\.base/.test(
      trades.slice(trades.indexOf('anchorTick:'), trades.indexOf('anchorTick:') + 120)),
    '8g. the receipt uses the OutlookBiasReceipt flare tick — tokens, no literals');
}

// ═══════════════════════════════════════════════════════════════════════
// 9 — the three prefill hand-offs load the inline canvas under the flag
// ═══════════════════════════════════════════════════════════════════════
{
  assert(count(tradesCode, /navigation\?\.navigate\?\.\('TradeCalculator', \{/g) === 3,
    '9. all three prefill navigations survive for the flag-off path',
    'deleting one would change flag-off behavior, which this wave may not do');
  assert(count(tradesCode, /if \(inlineHomeOn\) \{\s*\n\s*loadCanvasPrefill\(\{/g) === 3,
    '9a. …and each is preceded by a flag-gated inline load',
    'handleOpenAssetIdea, handleBackToCalculator and handleEditInCalculator');
  assert(count(tradesCode, /function loadCanvasPrefill\(/g) === 1,
    '9b. one loader, three callers');
  assert(/prefillSeq === undefined \|\| !hostPrefill/.test(canvas),
    '9c. the canvas ignores host prefills when the host passes no seq',
    'the #270 experiment path passes neither — it must be unaffected');
  // Review finding B1: MatchesScreen is the FOURTH prefill site — cross-tab,
  // so it rides a route param instead of calling the loader directly.
  const matchesCode = read('screens/MatchesScreen.tsx');
  assert(/if \(inlineHomeOn\) \{[\s\S]{0,400}?screen: 'TradesHome',[\s\S]{0,400}?canvasPrefill:/.test(matchesCode),
    '9d. MatchesScreen routes its edit-in-calculator to the guided landing when the flag is on',
    'flag-on, the pushed page has no In-league mode: the package was silently dropped (review B1)');
  assert(/navigation\.navigate\('Trades', \{\s*screen: 'TradeCalculator'/.test(matchesCode),
    '9e. …and the flag-off navigate to the pushed page survives verbatim');
  assert(/route\?\.params\?\.canvasPrefill[\s\S]{0,300}?loadCanvasPrefill\(p\)/.test(tradesCode),
    '9f. TradesScreen consumes the param into the one loader',
    'a param nobody consumes is the same silent drop moved one screen over');
}

// ═══════════════════════════════════════════════════════════════════════
// 10 — the mode-bar chip relabel
// ═══════════════════════════════════════════════════════════════════════
{
  assert(/\{ key: 'calc', label: 'Calc' \}/.test(modeBar),
    "10. the chip table still says 'Calc'",
    'the relabel is a render-time swap, so the array\'s identity and order '
    + 'are unchanged in both flag states');
  assert(/c\.key === 'calc' && inlineHomeOn \? 'Real values' : c\.label/.test(modeBar),
    "10a. …and reads 'Real values' under the flag");
  assert(/accessibilityLabel=\{label\}/.test(modeBar),
    '10b. the spoken label follows the visible one');
}

// ═══════════════════════════════════════════════════════════════════════
// 11 — the merged-view trim (T-1..T-3, operator ruling 2026-08-28)
// ═══════════════════════════════════════════════════════════════════════
// docs/feedback/items/402-more-offers-shop/merged-view-trim-2026-08-28.md:
// looking at the LIVE merged page, the operator ruled out the duplicate
// outlook bar (T-1), the page-level Find a Trade bar (T-2) and the
// scoring-format chips (T-3). All three are scoped to the flag path's
// canvas host (`canvasHost === 'flag'`), never the bare flag — flag-on
// team/player deck modes mount no calculator and must keep their surfaces —
// so flag-off stays byte-identical by construction.
{
  // T-1 — TradesScreen's minimized outlook row steps aside for the hosted
  // calculator's own outlook section. The full gate equality (nothing
  // added, nothing dropped) is check-finder-conditions-reachable.js
  // assertion 2; pinned here is the trim's own conjunct, so a "cleanup"
  // that drops it goes red in the wave's own suite too.
  {
    const at = trades.indexOf('testID="trades.outlook-fallback"');
    const gate = trades.slice(trades.lastIndexOf('{', at) - 260, at);
    assert(at > -1 && /canvasHost !== 'flag'/.test(gate),
      "11. T-1: the minimized outlook row is suppressed when the flag path hosts the canvas",
      'the operator\'s "duplicate outlook bar": the hosted calculator\'s '
      + 'calc.outlook-row (receipt or fallback twin, own Change control) is '
      + 'the one survivor on the merged page');
  }
  // T-2 — BOTH page-level Find a Trade bars are host-gated, and both still
  // exist (the flag-off page keeps its CTA — deleting one changes flag-off
  // behavior, which this wave may not do).
  {
    const mounts = [...tradesCode.matchAll(/testID="trades\.find-btn"/g)];
    assert(mounts.length === 2,
      '11a. T-2: both trades.find-btn mounts survive for the flag-off page',
      `found ${mounts.length} — the bar must still render whenever the canvas does not`);
    const gated = mounts.filter((m) => {
      const before = tradesCode.slice(Math.max(0, m.index - 400), m.index);
      return /\{canvasHost !== 'flag' \? \(\s*<Button/.test(before);
    });
    assert(gated.length === 2,
      "11b. T-2: …and each is gated on `canvasHost !== 'flag'`",
      'an ungated copy re-renders the second primary the ruling removed — '
      + "the canvas action row's Find a Trade covers both search paths "
      + '(fair sweep with a give side, model deck on empty canvas, D-153)');
    // The deck-summary copy quotes the CTA's label verbatim (#316); with
    // the bar gone on the merged view it must quote the canvas cell's
    // fixed "Find a Trade" instead — and keep the flag-off quote.
    assert(/canvasHost === 'flag'\s*\n?\s*\? 'Fresh ideas land every week — or tap Find a Trade to search again now\.'/.test(trades)
      && /: 'Fresh ideas land every week — or tap Find more trades to search again now\.'/.test(trades),
      '11c. T-2: the deck-summary copy quotes whichever control renders',
      'copy naming a control that is not on the page is a #316-class lie');
  }
  // T-3 — the format chips leave the merged header when hosted inline, via
  // a HOST prop threaded TradesScreen → TradeBuildCanvas →
  // InLeagueCalculator (never a flag read inside the component — the
  // pushed page must keep its chips; see check-calc-merged-layout.js 13c/d
  // for the component-side gate).
  {
    const at = trades.indexOf('<TradeBuildCanvas');
    const seg = trades.slice(at, at + 1100);
    assert(/hideFormatChips=\{canvasHost === 'flag'\}/.test(seg),
      "11d. T-3: the mount passes hideFormatChips on the flag path only",
      'the #270 experiment path must keep today\'s chips');
    assert(/hideFormatChips\?: boolean/.test(canvas)
      && /hideFormatChips = false/.test(canvas)
      && /hideFormatChips=\{hideFormatChips\}/.test(canvas),
      '11e. T-3: TradeBuildCanvas threads the prop, defaulting to false',
      'a default of true (or a dropped pass-through) strips the chips from '
      + 'the experiment variant or leaves the flag path with chips');
    const calcComp = read('components/InLeagueCalculator.tsx');
    assert(!/useFlag\(\s*['"]calc\.inline_home['"]\s*\)/.test(calcComp),
      '11f. T-3: InLeagueCalculator reads NO inline-home flag',
      'the contract mechanism is a host prop; a flag read inside the '
      + 'component would also strip the pushed page\'s chips');
  }
}

console.log(failures === 0
  ? 'check-inline-home: all assertions passed'
  : `check-inline-home: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
