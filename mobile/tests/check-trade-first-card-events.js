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
    ...(o.requires ?? {}),
  }, { performance: { now: () => now } });
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
  check('4a. dispatchGenerate sends the claimed tap id as /generate\'s search_id (else a fresh one for untapped dispatches)',
    /generateMutation\.mutate\(\{ \.\.\.vars, searchId: claimPendingSearch\(\) \?\? uuidv4\(\) \}, mutateOpts\);/.test(trades));
  check('4b. the landing\'s page-1 request uses the canvas tap\'s id; the adopting deck claims it; a cancelled push drops it',
    /generateTrades\(request, \{ searchId: fork\.searchId \}\)/.test(trades)
      && /claimSearch\(adopted\?\.snapshot\.search_id\);/.test(trades)
      && /dropPendingSearch\(fork\.searchId\);/.test(trades));
  check('4c. the fair sweep claims its tap\'s search; only an untapped sweep begins one',
    /if \(!claimPendingSearch\(\)\) \{\s*beginTradeSearch\(\{ source, mode: deckMode, searchType: 'fair_sweep', screen: 'Trades' \}\);/.test(trades));
}

console.log(failures ? `check-trade-first-card-events: ${failures} FAILED` : 'check-trade-first-card-events: all passed');
process.exit(failures ? 1 : 0);
