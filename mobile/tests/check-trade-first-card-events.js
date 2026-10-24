#!/usr/bin/env node
// WHY THIS EXISTS (time to trade suggestion, #339 §4.6 / AC-L1; contract
// docs/business/analytics/2026-10-20-time-to-suggestion-events.md, addendum
// v2 @ 255dd832): AC-L1 is read off three client events, and every way they
// go wrong is silent:
//   - R1 `find_trades_tapped` fires at DISPATCH instead of at the TAP (the
//     clock then starts late), or a table-A control fires none, or two fire
//     for one tap, or the tap's `search_id` is not the one /generate sends;
//   - R2 `trade_first_card_shown` fires in a skeleton/wait branch, or before
//     the card is ≥ 50% visible with Like and Pass enabled (T1), or twice;
//   - R2b `trade_first_card_failed` is missing (so p95 over R2 ∪ R2b drops
//     the slow tail, T2), or a backgrounded search reads as a long R2 (T4);
//   - the timing path reads Date.now() (wall clock) instead of the
//     monotonic performance.now().
// What it does: EXECUTES utils/firstCardEvent.ts and state/tradeSearchTrace.ts
// (requires stubbed) and pins every table-A tap site by source shape.
// HONEST LABEL (G-035): the trace's rules are executed; that the screens call
// them at the right frame is pinned by shape — the TestFlight two-device
// session (§9.6) and the Testing readout are the runtime proof.
//
// Run: node tests/check-trade-first-card-events.js   (or: npm run test:trade-first-card-events)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
let ts;
try { ts = require('typescript'); } catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}
const SRC = path.join(__dirname, '..', 'src');
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const stripComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

let failures = 0;
function check(name, cond, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}${detail ? `\n      ${detail}` : ''}`); }
}
function load(rel, requireMap, extra = {}) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(read(rel), { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS } }).outputText,
  { module, exports: module.exports, Set, Map, Math, Number, Array, Object, JSON,
    require: (name) => {
      if (!(name in requireMap)) throw new Error(`${rel}: unexpected require ${name}`);
      return requireMap[name];
    }, ...extra });
  return module.exports;
}

const pure = load('utils/firstCardEvent.ts', {});
const trades = stripComments(read('screens/TradesScreen.tsx'));
const traceSrc = read('state/tradeSearchTrace.ts');
const traceCode = stripComments(traceSrc);

// A fresh copy of the trace module per scenario, with a scripted clock.
function freshTrace(o = {}) {
  const events = [];
  let now = 1000;
  let sessionDone = !!o.sessionDone;
  let n = 0;
  const mod = load('state/tradeSearchTrace.ts', {
    '../api/events': { track: (type, props, screen) => events.push({ type, props: JSON.parse(JSON.stringify(props ?? {})), screen }) },
    '../api/_queue': { uuidv4: () => `s${++n}` },
    '../api/auth': { sessionInitCompletedThisProcess: () => sessionDone },
    './useFeatureFlags': {
      useFeatureFlags: { getState: () => ({ flags: o.flags ?? {} }) },
      onboardingEnabled: () => false,
    },
    './useOnboardingState': { useOnboardingState: { getState: () => ({ hydrated: true, ob: { firstSwipeDone: true } }) } },
    '../utils/firstCardEvent': pure,
    '../utils/tapTiming': { recordTapTiming: () => {} },
    'react-native': { AppState: { addEventListener: () => {} } },
    '@react-native-community/netinfo': { __esModule: true, default: { addEventListener: () => {} } },
    ...(o.requires ?? {}),
  }, { performance: { now: () => now }, setTimeout: () => null, clearTimeout: () => {} });
  return { mod, events, tick: (ms) => { now += ms; }, setSession: (v) => { sessionDone = v; } };
}

console.log('check-trade-first-card-events:');

// ── 1. R1 at the tap, with a client search id ─────────────────────────────
{
  const t = freshTrace();
  const id = t.mod.beginTradeSearch({ source: 'league_offer', mode: 'single_pin', searchType: 'pinned', screen: 'LeagueRankings' });
  const r1 = t.events.find((e) => e.type === 'find_trades_tapped');
  check('1a. EXECUTED: the tap emits find_trades_tapped {source, mode, search_id} at once',
    !!r1 && JSON.stringify(r1.props) === JSON.stringify({ source: 'league_offer', mode: 'single_pin', search_id: id }));
  check('1b. the deck that dispatches claims that id exactly once',
    t.mod.claimPendingSearch() === id && t.mod.claimPendingSearch() === null);
  const t2 = freshTrace();
  t2.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' });
  check('1c. the deck\'s own Find a Trade sends no `source` key at all',
    t2.events[0] && !('source' in t2.events[0].props) && t2.events[0].props.mode === 'deck');
  check('1d. the trace stamps the tap with performance.now(), never Date (no Date anywhere in the module)',
    /tapAt: monotonicNow\(\)/.test(traceCode) && /\.performance\.now\(\)/.test(traceCode) && !/\bDate\b/.test(traceCode));
}

// ── 2. EXECUTED: the values R2/R2b will carry ─────────────────────────────
{
  check('2a. search_type: fair sweep; organic only with no pin, partner or intent; else pinned',
    pure.searchTypeOf({ fair: true }) === 'fair_sweep'
      && pure.searchTypeOf({}) === 'organic'
      && pure.searchTypeOf({ receiveIds: ['p'] }) === 'pinned'
      && pure.searchTypeOf({ opponentId: 'u' }) === 'pinned'
      && pure.searchTypeOf({ intent: 'tier_up' }) === 'pinned');
  check('2b. launch_state: cold_launch before session-init, then first_tap, then repeat_tap',
    pure.launchStateFor({ sessionInitDone: false, priorSearches: 3 }) === 'cold_launch'
      && pure.launchStateFor({ sessionInitDone: true, priorSearches: 0 }) === 'first_tap'
      && pure.launchStateFor({ sessionInitDone: true, priorSearches: 1 }) === 'repeat_tap');
  check('2c. network_type from NetInfo: wifi | cellular | offline (none / not connected) | unknown',
    pure.networkTypeOf({ type: 'wifi', isConnected: true }) === 'wifi'
      && pure.networkTypeOf({ type: 'cellular', isConnected: true }) === 'cellular'
      && pure.networkTypeOf({ type: 'none', isConnected: false }) === 'offline'
      && pure.networkTypeOf({ type: 'wifi', isConnected: false }) === 'offline'
      && pure.networkTypeOf({ type: 'ethernet', isConnected: true }) === 'unknown'
      && pure.networkTypeOf(null) === 'unknown');
  // A tap before session-init is cold_launch (its own T3 row); the process's
  // first search is first_tap only when it comes after init; every later
  // search — including one after a cold-launch search — is repeat_tap.
  const t = freshTrace();
  const a = t.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' });
  t.setSession(true);
  const b = t.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' });
  const w = freshTrace({ sessionDone: true });
  const f = w.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' });
  const r = w.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' });
  check('2d. EXECUTED: launch_state is decided AT THE TAP (cold_launch; first_tap; repeat_tap)',
    t.mod.traceFor(a).launchState === 'cold_launch' && t.mod.traceFor(b).launchState === 'repeat_tap'
      && w.mod.traceFor(f).launchState === 'first_tap' && w.mod.traceFor(r).launchState === 'repeat_tap');
  check('2e. hand-off mode follows the deck it lands on (one pin + targeting + asset ideas ⇒ single_pin)',
    pure.deckModeForPins({ pinCount: 1, targeting: true, assetIdeas: true, firstRun: false }) === 'single_pin'
      && pure.deckModeForPins({ pinCount: 1, targeting: true, assetIdeas: false, firstRun: false }) === 'deck'
      && pure.deckModeForPins({ pinCount: 1, targeting: true, assetIdeas: true, firstRun: true }) === 'deck');
}

// ── 3. Every #339 table-A control begins its search AT THE TAP ────────────
{
  const canvas = stripComments(read('utils/canvasSearch.ts'));
  const forkAt = canvas.indexOf('export function forkCanvasSearch(');
  const fork = canvas.slice(forkAt);
  check('3a. canvas Find a Trade (calculator): forkCanvasSearch begins the search before calc_find_a_trade_tapped, which carries the same search_id',
    /const searchId = beginTradeSearch\(\{\s*source: 'calculator',/.test(fork)
      && fork.indexOf('beginTradeSearch(') < fork.indexOf("'calc_find_a_trade_tapped'")
      && /has_partner: !!opts\.opponent,\s*search_id: searchId,/.test(fork)
      && /\n    searchId,\n  \};/.test(fork));
  const hft = trades.slice(trades.indexOf('function handleFindTrades('), trades.indexOf('function handleToggleFairness('));
  check('3b. handleFindTrades (every in-deck control) begins the search before it dispatches',
    /beginTradeSearch\(\{/.test(hft) && hft.indexOf('beginTradeSearch(') < hft.indexOf('dispatchGenerate(')
      && hft.indexOf('beginTradeSearch(') < hft.indexOf('runFairPackages('));
  const sources = {
    deck_error_retry: /onPress=\{\(\) => handleFindTrades\('deck_error_retry'\)\}/,
    prefs_changed_strip: /onPress=\{\(\) => handleFindTrades\('prefs_changed_strip'\)\}/,
    deck_summary_unpin: /function handleUnpinRetry\(\) \{[\s\S]*?handleFindTrades\('deck_summary_unpin'\);/,
    deck_search_all: /function handleSearchAllTrades\(\) \{[\s\S]*?handleFindTrades\('deck_search_all'\);/,
    end_card_adjust: /function applyDeckEndAdjust\(\) \{[\s\S]*?handleFindTrades\('end_card_adjust'\);/,
    deep_link: /source: source \?\? \(isDeepLinkDeck \? 'deep_link' : undefined\)/,
  };
  const missing = Object.entries(sources).filter(([, re]) => !re.test(trades)).map(([k]) => k);
  check('3c. in-deck controls pass their exact addendum source (deck_error_retry, prefs_changed_strip, deck_summary_unpin, deck_search_all, end_card_adjust, deep_link)',
    missing.length === 0, `missing: ${missing.join(', ')}`);
  const league = stripComments(read('screens/LeagueSummaryScreen.tsx'));
  check('3d. League Summary Offer/Target: league_offer / league_target, at the tap, before the hand-off',
    /beginTradeSearch\(\{\s*source: verb === 'offer' \? 'league_offer' : 'league_target',/.test(league)
      && league.indexOf('beginTradeSearch(') < league.indexOf('store.setHandoff('));
  const usage = stripComments(read('screens/UsageTrendsScreen.tsx'));
  const doTrade = usage.slice(usage.indexOf('const doTrade = async'), usage.indexOf('const doAdd = async'));
  check('3e. Usage Trends Trade: usage_trends at the tap (before the sheet and league switch), only when the hand-off will search',
    /beginTradeSearch\(\{\s*source: 'usage_trends',/.test(doTrade)
      && doTrade.indexOf('beginTradeSearch(') < doTrade.indexOf('await closeSheetFirst()')
      && /ownerKey && !ownerKey\.startsWith\('roster:'\)\s*\?\s*beginTradeSearch/.test(doTrade)
      && /if \(searchId\) dropPendingSearch\(searchId\);/.test(doTrade));
  check('3f. no find_trades_tapped is emitted at dispatch anywhere in TradesScreen (one tap, one R1)',
    !/track\(\s*'find_trades_tapped'/.test(trades));
  const r1Sources = ['deck_error_retry', 'prefs_changed_strip', 'deck_summary_unpin', 'deck_search_all', 'calculator',
    'league_offer', 'league_target', 'usage_trends', 'deep_link', 'end_card_adjust'];
  const union = read('utils/firstCardEvent.ts');
  check('3g. R1Source is exactly the addendum\'s source list',
    r1Sources.every((v) => union.includes(`'${v}'`))
      && (union.slice(union.indexOf('export type R1Source'), union.indexOf('export type SearchType')).match(/'[a-z_]+'/g) || []).length === r1Sources.length);
}

// ── 4. The request carries the tap's id ───────────────────────────────────
{
  check('4a. dispatchGenerate sends the claimed tap id as /generate\'s search_id (else a fresh one for untapped dispatches), and the deck now answers that search',
    /const claimed = claimPendingSearch\(\);\s*deckSearchRef\.current = claimed \? \{ id: claimed, keys: new Set\(\) \} : null;\s*generateMutation\.mutate\(\{ \.\.\.vars, searchId: claimed \?\? uuidv4\(\) \}, mutateOpts\);/.test(trades));
  check('4b. the landing\'s page-1 request uses the canvas tap\'s id; the adopting deck claims it; a cancelled push drops it',
    /generateTrades\(request, \{ searchId: fork\.searchId \}\)/.test(trades)
      && /claimSearch\(adopted\?\.snapshot\.search_id\);/.test(trades)
      && /dropPendingSearch\(fork\.searchId\);/.test(trades));
  check('4c. the fair sweep claims its tap\'s search; only an untapped sweep begins one',
    /let claimedFair = claimPendingSearch\(\);\s*if \(!claimedFair\) \{\s*beginTradeSearch\(\{ source, mode: deckMode, searchType: 'fair_sweep', screen: 'Trades' \}\);/.test(trades));
}

// ── 5. EXECUTED: exactly one R2/R2b per search_id ─────────────────────────
const tapTiming = load('utils/tapTiming.ts', {});
function freshTraceWithTimers() {
  const pending = [];
  const h = (() => {
    const events = [];
    let now = 1000;
    let n = 0;
    let appListener = null;
    let netListener = null;
    const mod = load('state/tradeSearchTrace.ts', {
      '../api/events': { track: (type, props) => events.push({ type, props: JSON.parse(JSON.stringify(props ?? {})) }) },
      '../api/_queue': { uuidv4: () => `s${++n}` },
      '../api/auth': { sessionInitCompletedThisProcess: () => true },
      './useFeatureFlags': { useFeatureFlags: { getState: () => ({ flags: {} }) }, onboardingEnabled: () => false },
      './useOnboardingState': { useOnboardingState: { getState: () => ({ hydrated: true, ob: { firstSwipeDone: true } }) } },
      '../utils/firstCardEvent': pure,
      '../utils/tapTiming': tapTiming,
      'react-native': { AppState: { addEventListener: (_e, fn) => { appListener = fn; } } },
      '@react-native-community/netinfo': { __esModule: true, default: { addEventListener: (fn) => { netListener = fn; } } },
    }, {
      performance: { now: () => now },
      setTimeout: (fn, ms) => { const h = { fn, at: now + ms, live: true }; pending.push(h); return h; },
      clearTimeout: (h) => { if (h) h.live = false; },
    });
    return {
      mod, events,
      tick: (ms) => {
        now += ms;
        for (const h of pending) if (h.live && h.at <= now) { h.live = false; h.fn(); }
      },
      app: (s) => appListener && appListener(s),
      net: (s) => netListener && netListener(s),
    };
  })();
  return h;
}
{
  const h = freshTraceWithTimers();
  h.net({ type: 'wifi', isConnected: true });
  const id = h.mod.beginTradeSearch({ source: 'calculator', mode: 'deck', searchType: 'organic', screen: 'Trades' });
  h.mod.noteFirstResponse(id, { serve_source: 'page', freshness_state: 'fresh', status: 'complete', cardCount: 30, job_id: 'j1' });
  h.tick(180);
  h.mod.reportFirstCardShown(id, { cardIndex: 0 });
  h.mod.reportFirstCardShown(id, { cardIndex: 0 });
  h.mod.failFirstCard(id, 'error');
  h.tick(20000);
  const r2 = h.events.filter((e) => e.type === 'trade_first_card_shown');
  const r2b = h.events.filter((e) => e.type === 'trade_first_card_failed');
  check('5a. one R2 per search_id; a second report, a later failure and the 10 s timer add nothing',
    r2.length === 1 && r2b.length === 0);
  check('5b. R2 carries exactly the addendum props, ms_from_tap the monotonic tap delta',
    r2[0] && JSON.stringify(Object.keys(r2[0].props).sort()) === JSON.stringify(['card_index', 'entry_point', 'freshness_state',
      'job_id', 'launch_state', 'ms_from_tap', 'network_type', 'search_id', 'search_type', 'serve_source'])
      && r2[0].props.ms_from_tap === 180 && r2[0].props.entry_point === 'calculator'
      && r2[0].props.network_type === 'wifi' && r2[0].props.serve_source === 'page'
      && r2[0].props.launch_state === 'first_tap' && r2[0].props.job_id === 'j1' && r2[0].props.search_id === id);
}
{
  const h = freshTraceWithTimers();
  const id = h.mod.beginTradeSearch({ source: 'league_target', mode: 'deck', searchType: 'pinned', screen: 'X' });
  h.tick(9999);
  const before = h.events.filter((e) => e.type === 'trade_first_card_failed').length;
  h.tick(1);
  h.mod.reportFirstCardShown(id, { cardIndex: 0 });
  const r2b = h.events.filter((e) => e.type === 'trade_first_card_failed');
  check('5c. timeout = 10,000 ms from the tap with no card: one R2b {reason: timeout}, and no R2 after it',
    before === 0 && r2b.length === 1 && r2b[0].props.reason === 'timeout' && r2b[0].props.ms_from_tap === 10000
      && !h.events.some((e) => e.type === 'trade_first_card_shown'));
  check('5d. R2b carries exactly the addendum props',
    JSON.stringify(Object.keys(r2b[0].props).sort()) === JSON.stringify(['entry_point', 'launch_state', 'ms_from_tap',
      'network_type', 'reason', 'search_id', 'search_type']) /* serve_source absent: no response yet */);
}
{
  const h = freshTraceWithTimers();
  const id = h.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' });
  h.tick(300);
  h.app('background');
  h.app('active');
  h.mod.reportFirstCardShown(id, { cardIndex: 0 });
  const r2b = h.events.filter((e) => e.type === 'trade_first_card_failed');
  check('5e. T4: the app leaving `active` before a card ends the search as abandoned — never a long R2',
    r2b.length === 1 && r2b[0].props.reason === 'abandoned' && !h.events.some((e) => e.type === 'trade_first_card_shown'));
  const a = h.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' });
  h.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' });
  const fa = h.events.filter((e) => e.type === 'trade_first_card_failed' && e.props.search_id === a);
  check('5f. a newer tap supersedes an open search: it ends abandoned (one R2b), never left open',
    fa.length === 1 && fa[0].props.reason === 'abandoned');
  const d = h.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' });
  h.mod.dropPendingSearch(d);
  check('5g. a tap whose search never runs (dropped) ends abandoned, and is no longer claimable',
    h.events.some((e) => e.type === 'trade_first_card_failed' && e.props.search_id === d && e.props.reason === 'abandoned')
      && h.mod.claimPendingSearch() === null);
}
{
  check('5h. serve_source: the server value wins; else cached (complete) / joined (running with cards) / fresh',
    pure.inferServeSource({ serve_source: 'page', status: 'running', cardCount: 0 }) === 'page'
      && pure.inferServeSource({ status: 'complete', cardCount: 3 }) === 'cached'
      && pure.inferServeSource({ status: 'running', cardCount: 3 }) === 'joined'
      && pure.inferServeSource({ status: 'running', cardCount: 0 }) === 'fresh');
  check('5i. T1 visibility: ≥ 50% of the card inside the window',
    pure.visibleFraction(0, 400, 0, 800) === 1 && pure.visibleFraction(600, 400, 0, 800) === 0.5
      && pure.visibleFraction(700, 400, 0, 800) === 0.25 && pure.visibleFraction(0, 0, 0, 800) === 0
      && pure.FIRST_CARD_MIN_VISIBLE === 0.5 && pure.FIRST_CARD_TIMEOUT_MS === 10000);
}

// ── 6. R2 only on the enabled-and-visible path (T1), never a wait branch ─
{
  const fnAt = trades.indexOf('function checkFirstCardShown(');
  const fn = trades.slice(fnAt, trades.indexOf('\n  }\n', fnAt));
  check('6a. the first card must be one THIS search delivered, with Like and Pass enabled (the card\'s own predicate)',
    /if \(!s\.keys\.has\(deckCardKey\(rawTopCard\)\)\) return;/.test(fn)
      && /if \(swipeMutation\.isPending \|\| \(declineReasonsOn && reasonBankedId === rawTopCard\.trade_id\)\) return;/.test(fn));
  check('6b. measured in window coordinates, ≥ FIRST_CARD_MIN_VISIBLE, then reported on the next frame (one rAF)',
    /node\.measureInWindow\(/.test(fn)
      && /visibleFraction\(y, h, 0, Dimensions\.get\('window'\)\.height\) < FIRST_CARD_MIN_VISIBLE\) return;/.test(fn)
      && /requestAnimationFrame\(\(\) => reportFirstCardShown\(id, \{ cardIndex \}\)\)/.test(fn));
  const cardBranch = trades.slice(trades.indexOf(') : topCard ? ('), trades.indexOf(') : pagedWithCards && deckEnd ? ('));
  check('6c. the measured view exists only inside the real card (SwipableTopCard in the topCard branch) — never a skeleton, Looking, withdrawn or end card',
    (trades.match(/measureRef=\{topCardMeasureRef\}/g) || []).length === 1
      && /measureRef=\{topCardMeasureRef\}/.test(cardBranch)
      && /<View ref=\{measureRef\} collapsable=\{false\}>\s*<TradeCardComp/.test(trades));
  check('6d. R2 has one reporter in the deck (checkFirstCardShown), run on the card\'s layout, on scroll and on deck changes',
    (trades.match(/reportFirstCardShown\(/g) || []).length === 1
      && /setTopCardH\(e\.nativeEvent\.layout\.height\);\s*checkFirstCardShown\(\);/.test(trades)
      && /if \(deckSearchRef\.current\) checkFirstCardShown\(\);/.test(trades)
      && /checkFirstCardShown\(\);\s*\}, \[rawTopCard\?\.trade_id, deck\.length, swipeMutation\.isPending\]\);/.test(trades));
  check('6e. no Date in the timing path (trace, pure helpers, the T1 check)',
    !/\bDate\b/.test(traceCode) && !/\bDate\b/.test(stripComments(read('utils/firstCardEvent.ts'))) && !/\bDate\b/.test(fn));
}

// ── 7. R2b from the deck: empty, error, abandoned on blur / unmount ───────
{
  check('7a. abandoned when the owning deck BLURS (a focus transition, not the mount) or unmounts',
    /if \(wasFocusedRef\.current && !navFocused\) failDeckSearch\('abandoned'\);/.test(trades)
      && /useEffect\(\(\) => \(\) => failDeckSearch\('abandoned'\), \[\]\);/.test(trades));
  check('7b. error whenever the search lands in deckFailure (generate, poll, job, fair sweep)',
    /if \(deckFailure\) failDeckSearch\('error'\);/.test(trades));
  check('7c. empty where each answer lands: generate, the legacy poll, a fully delivered paged deck, the fair sweep',
    /if \(snapshot\.status === 'complete' && snapshot\.cards\.length === 0\) failFirstCard\(ds\.id, 'empty'\);/.test(trades)
      && /if \(next\.status === 'complete' && deckSearchRef\.current\?\.keys\.size === 0\) failDeckSearch\('empty'\);/.test(trades)
      && /if \(deckFullyDelivered\(next\) && next\.status !== 'error' && deckSearchRef\.current\?\.keys\.size === 0\) \{\s*failDeckSearch\('empty'\);/.test(trades)
      && /if \(claimedFair && res\.ideas\.length === 0\) failFirstCard\(claimedFair, 'empty'\);/.test(trades));
}

{
  check('5j. the Testing readout\'s store holds R2\'s last ms_from_tap and its cell (in memory)',
    tapTiming.lastTapTiming() && tapTiming.lastTapTiming().msFromTap === 180
      && tapTiming.lastTapTiming().networkType === 'wifi' && tapTiming.lastTapTiming().launchState === 'first_tap');
}

// ── 8. deck_buffer_empty: once per search, when the buffer runs dry ─────
{
  const h = freshTraceWithTimers();
  h.net({ type: 'cellular', isConnected: true });
  const id = h.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' });
  h.tick(150);
  h.mod.reportFirstCardShown(id, { cardIndex: 0 });
  h.tick(4000);
  h.mod.reportDeckBufferEmpty(id, { deckId: 'd1', cardsSeen: 12 });
  h.mod.reportDeckBufferEmpty(id, { deckId: 'd1', cardsSeen: 13 });
  const e = h.events.filter((x) => x.type === 'deck_buffer_empty');
  check('8a. EXECUTED: at most once per search_id, with exactly the addendum props',
    e.length === 1 && JSON.stringify(Object.keys(e[0].props).sort())
      === JSON.stringify(['cards_seen', 'deck_id', 'ms_since_first_card', 'network_type', 'search_id'])
      && e[0].props.ms_since_first_card === 4000 && e[0].props.cards_seen === 12
      && e[0].props.network_type === 'cellular' && e[0].props.deck_id === 'd1');
  const eff = trades.slice(trades.indexOf('reportDeckBufferEmpty(searchId'), trades.length).slice(0, 400);
  const effAt = trades.indexOf('if (!pagedWithCards || !rawTopCard || !job || unseen > 0 || deckFullyDelivered(job)) return;');
  check('8b. the deck reports it only at the last ready card (nothing unseen) of a paged deck still to be delivered',
    effAt > -1 && trades.indexOf('reportDeckBufferEmpty(searchId', effAt) > effAt
      && /reportDeckBufferEmpty\(searchId, \{ deckId: job\.deck_id \?\? job\.job_id, cardsSeen: deckIdx \+ 1 \}\);/.test(trades)
      && eff.length > 0);
}

// ── 9. The trace's module state is bounded ───────────────────────────────
{
  const h = freshTraceWithTimers();
  const ids = [];
  for (let i = 0; i < 30; i += 1) ids.push(h.mod.beginTradeSearch({ mode: 'deck', searchType: 'organic', screen: 'Trades' }));
  // ids[29] is open; ids[28] was still open when the 30th tap pruned, then
  // superseded — so only settled ones were ever dropped, oldest first.
  const kept = ids.filter((id) => h.mod.traceFor(id));
  check('9a. EXECUTED: each tap drops the oldest SETTLED traces beyond the 20 most recent; the open one stays',
    !h.mod.traceFor(ids[0]) && !!h.mod.traceFor(ids[29]) && h.mod.isSearchOpen(ids[29])
      && kept.length <= 22 && kept[kept.length - 1] === ids[29] && kept.every((id, i) => i === 0 || ids.indexOf(id) > ids.indexOf(kept[i - 1])));
  check('9b. the prune never touches an unsettled trace and drops its deck_buffer_empty mark with it',
    /function pruneSettledTraces\(\): void \{[\s\S]*?if \(!t\.settled\) continue;\s*traces\.delete\(id\);\s*bufferEmptyReported\.delete\(id\);/.test(traceCode)
      && /\}\): string \{\s*pruneSettledTraces\(\);/.test(traceCode));
}

console.log(failures ? `check-trade-first-card-events: ${failures} FAILED` : 'check-trade-first-card-events: all passed');
process.exit(failures ? 1 : 0);
