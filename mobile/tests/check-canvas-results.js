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

// ── AST helpers (check-shop-deck.js pattern) ──────────────────────────────

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
    'trades.canvas-results.pass',
  ]) {
    assert(trades.includes(`testID="${id}"`), `3. ${id} exists`);
  }
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
  assert(/declineReasonProps && reasonsAsOverlay/.test(passText)
    && /handleReasonOverlayOpened\(\)/.test(passText),
    '4a. the ✕ opens the reason capture through the SAME gate and the SAME opened-event emitter the deck uses',
    'a private overlay-open would fork trade_pass_overlay_opened semantics');
  assert(/advance\('pass', \{ deferDeckAdvance: true \}\)/.test(passText)
    && /flushPendingPass\(\)/.test(passText)
    && /removeBrowsedIdea\(rawTopCard\.trade_id\)/.test(passText),
    '4b. the reasons-off fallback is a plain deck pass (advance + immediate commit) plus the set removal');
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
  // The pass control lives with the pager — never in the D-157 action row.
  assert(!/canvas-results/.test(calcCode),
    '4l. InLeagueCalculator carries NO canvas-results surface — the action row\'s 50/30/20 is untouched (D-157)');
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
  assert(count(tradesCode, /setBrowseSession\(\{ origin: 'model', passed: 0, edits: \{\} \}\)/g) === 1,
    '8a. the choke point\'s model dispatch creates a model-origin session (exactly once)');
  assert(count(tradesCode, /generateMutation\.mutate\(/g) === 8,
    '8b. no new generate dispatch site was added (the check-inline-home 7f census holds)');
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

console.log(failures === 0
  ? 'check-canvas-results: all assertions passed'
  : `check-canvas-results: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
