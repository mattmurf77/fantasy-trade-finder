#!/usr/bin/env node
// Navigation continuity (D-275, docs/plans/nav-continuity/scope.md): the
// Home tiles' "‹ Home" control (flag `nav.home_return`, R5 / Q1 (a)) and the
// smaller fixes R1-R4, R8, R9, R13 of the 2026-11-12 navigation map (flag
// `nav.continuity`). Also D-276 (docs/plans/home-return-unify/scope.md, flag
// `nav.home_return_unified`): one Home control for the position tile body
// too (A1d-A1f, A2m-A2t, A6, B1, B9), checked in both flag states.
//
// No simulator (D-056). Part A EXECUTES the navigation decisions: the pure
// helpers in src/navigation/navContinuity.ts and the real zustand store in
// src/state/homeReturn.ts, driven through the sequences a user makes (tap a
// tile, land, leave). Part B pins each call site to those helpers, with the
// flag-off branch kept exactly as it was. Assertions read comment-stripped
// code. Each assertion names the regression it catches.
//
// Run: node tests/check-nav-continuity.js   (npm run test:nav-continuity)
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const MOBILE = path.join(__dirname, '..');
const REPO = path.join(MOBILE, '..');
let ts;
try {
  ts = require('typescript');
} catch (e) {
  console.error('FAIL  typescript is not installed (run npm install in mobile/)');
  process.exit(1);
}

let failures = 0;
let passes = 0;
const assert = (cond, name, why) => {
  if (cond) {
    passes += 1;
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`);
  }
};

const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const readRoot = (rel) => fs.readFileSync(path.join(REPO, rel), 'utf8');
// Comment strip: block comments (JSX ones included) and whole-line `//`
// comments. Good enough for code shapes; strings with `//` stay intact.
const strip = (src) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
const src = (rel) => strip(read(rel));

function load(rel, requireFn) {
  const m = { exports: {} };
  const out = ts.transpileModule(read(rel), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(out, { exports: m.exports, module: m, require: requireFn, Object, Array, String, Number, JSON });
  return m.exports;
}

const nc = load('src/navigation/navContinuity.ts', (r) => {
  throw new Error(`navContinuity.ts must stay import-free (asked for ${r})`);
});

// ═══════════════════════════════════════════════════════════════════════
// A1 — which Home taps arm the "‹ Home" control, and for which tab.
// ═══════════════════════════════════════════════════════════════════════
const ARMS = {
  outlook: 'Trades',
  review_outlook: 'Trades',
  find_trade: 'Trades',
  next_move: 'Trades',              // Home's next move (D-278): Find a Trade, as find_trade
  overall_rank: 'League',
  buy: 'League',
  sell: 'League',
  position_ranking: 'League',
  matches: 'Matches',
};
const NO_ARM = [
  'rank', 'trends',                 // rank pages: 2026-08-16 one-exit ruling (Q5 not taken)
  'position_roster',                // D-269's own header control
  'standings', 'direction', 'usage_rates', 'free_agents', 'link_league', // pushes with a Back
];
{
  for (const [tap, tab] of Object.entries(ARMS)) {
    assert(nc.homeReturnTabFor(tap) === tab, `A1a. ${tap} arms the control on ${tab}`);
  }
  for (const tap of NO_ARM) {
    assert(nc.homeReturnTabFor(tap) === null, `A1b. ${tap} arms nothing`);
  }
  assert(nc.HOME_RETURN_FLAG === 'nav.home_return' && nc.CONTINUITY_FLAG === 'nav.continuity',
    'A1c. the two flag keys');
  // D-276: unified mode changes exactly one tap, and only both flags on.
  assert(nc.HOME_RETURN_UNIFIED_FLAG === 'nav.home_return_unified', 'A1d. the unified flag key');
  assert(nc.homeReturnUnifiedOn(true, true) === true && nc.homeReturnUnifiedOn(true, false) === false
    && nc.homeReturnUnifiedOn(false, true) === false && nc.homeReturnUnifiedOn(false, false) === false,
    'A1e. unified only when BOTH nav.home_return and nav.home_return_unified are on');
  const ALL_TAPS = [...Object.keys(ARMS), ...NO_ARM];
  const changed = ALL_TAPS.filter((t) => nc.homeReturnTabFor(t, true) !== nc.homeReturnTabFor(t, false));
  assert(changed.length === 1 && changed[0] === 'position_roster' && nc.homeReturnTabFor('position_roster', true) === 'League'
    && nc.homeReturnTabFor('rank', true) === null && nc.homeReturnTabFor('trends', true) === null,
    'A1f. unified: the position tile body arms League; every other tap (rank pages included) is unchanged',
    `changed: ${changed.join(', ')}`);
}

// ═══════════════════════════════════════════════════════════════════════
// A2 — "for that visit only": the real store, driven like the app drives it
//      (HomeHub arms, TabNav reports every tab focus, the bar reads it).
// ═══════════════════════════════════════════════════════════════════════
{
  const zustand = require(path.join(MOBILE, 'node_modules/zustand'));
  const store = load('src/state/homeReturn.ts', (r) => {
    if (r === 'zustand') return zustand;
    if (r === '../navigation/navContinuity') return nc;
    throw new Error(`homeReturn.ts asked for ${r}`);
  });
  const s = store.useHomeReturn;
  const visible = (flag = true) => nc.homeReturnVisible(s.getState(), s.getState().focusedTab, flag);

  s.getState().noteTabFocus('Home');
  assert(!visible(), 'A2a. on Home, nothing armed: no control');
  store.armHomeReturn('buy');
  assert(!visible(), 'A2b. armed but still on Home: not drawn on Home');
  s.getState().noteTabFocus('League');
  assert(visible(), 'A2c. Buy → League rankings: the control shows');
  assert(!visible(false), 'A2d. flag off: never shows, whatever is armed');
  s.getState().noteTabFocus('Matches');
  assert(!visible() && s.getState().tab === null, 'A2e. leaving the tab by the tab bar ends the visit');
  s.getState().noteTabFocus('League');
  assert(!visible(), 'A2f. coming back to League later on one\'s own: no stray control');

  s.getState().noteTabFocus('Home');
  store.armHomeReturn('find_trade');
  s.getState().noteTabFocus('Trades');
  assert(visible(), 'A2g. Find a trade → Acquire: the control shows');
  s.getState().noteTabFocus('Home');
  assert(!visible() && s.getState().tab === null, 'A2h. the control (or the Home tab) returns Home and ends it');

  store.armHomeReturn('matches');
  s.getState().noteTabFocus('League');
  assert(!visible() && s.getState().tab === null, 'A2i. armed for Matches but League focused (a different arrival): disarmed');

  store.armHomeReturn('trends');
  s.getState().noteTabFocus('Rank');
  assert(!visible(), 'A2j. Check trends → a rank page: no control (rank-page ruling stands)');
  store.armHomeReturn('rank');
  s.getState().noteTabFocus('Rank');
  assert(!visible(), 'A2k. Rank players → a rank page: no control');
  store.armHomeReturn('position_roster');
  s.getState().noteTabFocus('League');
  assert(!visible(), 'A2l. the position tile body (D-269) arms no bar: no second Home control');

  // D-276 unified mode, the same store.
  s.getState().noteTabFocus('Home');
  store.armHomeReturn('position_roster', false);
  s.getState().noteTabFocus('League');
  assert(!visible(), 'A2m. unified off: the position tile body still arms no bar (D-269 control instead)');
  s.getState().noteTabFocus('Home');
  store.armHomeReturn('position_roster', true);
  s.getState().noteTabFocus('League');
  assert(visible(), 'A2n. unified: position tile body → League rankings: the "‹ Home" bar shows');
  s.getState().noteTabFocus('League');
  assert(visible(), 'A2o. unified: it stays for the visit, whatever happens on the page (not only while the team is open)');
  const seq0 = s.getState().returned.seq;
  s.getState().requestReturn();
  assert(s.getState().returned.seq === seq0 + 1 && s.getState().returned.tab === 'League',
    'A2p. a "‹ Home" tap raises one new signal, naming the armed tab (League)');
  s.getState().noteTabFocus('Home');
  assert(!visible() && s.getState().tab === null && s.getState().returned.seq === seq0 + 1,
    'A2q. landing on Home ends the visit; no second signal is raised by the tab change');
  store.armHomeReturn('buy', true);
  s.getState().noteTabFocus('League');
  s.getState().requestReturn();
  assert(s.getState().returned.seq === seq0 + 2 && s.getState().returned.tab === 'League',
    'A2r. each tap is its own signal (seq grows), so a listener acts once per tap');
  s.getState().noteTabFocus('Home');
  store.armHomeReturn('position_roster', true);
  s.getState().noteTabFocus('Matches');
  assert(!visible() && s.getState().tab === null, 'A2s. unified: leaving League another way ends the visit');
  s.getState().noteTabFocus('League');
  assert(!visible(), 'A2t. unified: coming back to League on one\'s own shows no stray bar');
}

// ═══════════════════════════════════════════════════════════════════════
// A6 — D-276: the League rankings side of one Home control (the header
//      control's show rule and the bar-tap close rule), executed, then the
//      tap → close sequence driven through the real store with a listener
//      shaped like LeagueSummaryScreen's (B9 pins the screen to it).
// ═══════════════════════════════════════════════════════════════════════
{
  const H = nc.rosterHeaderHomeVisible;
  // Unified off: exactly D-269's rule, `isTabRoot && homeBackId != null && selectedId === homeBackId`.
  let same = true;
  for (const root of [true, false]) for (const arr of ['t1', null]) for (const sel of ['t1', 't2', null]) {
    const d269 = root && arr != null && sel === arr;
    if (H(root, arr, sel, false) !== d269) same = false;
  }
  assert(same, 'A6a. unified off: the header "Home" control follows D-269\'s rule exactly');
  let none = true;
  for (const root of [true, false]) for (const arr of ['t1', null]) for (const sel of ['t1', 't2', null]) {
    if (H(root, arr, sel, true)) none = false;
  }
  assert(none, 'A6b. unified: the header "Home" control never shows (no second control, ever)');

  const C = nc.rosterClosesOnHomeReturn;
  const sig = (tab) => ({ seq: 1, tab });
  assert(C(true, sig('League'), true, 't1', 't1') === true, 'A6c. unified, bar tapped on League, the arrival team still open: close it');
  assert(C(true, sig('League'), true, 't1', 't2') === false, 'A6d. another team open now: left alone (no home_back)');
  assert(C(true, sig('League'), true, 't1', null) === false, 'A6e. drill-in already closed ("All teams"): nothing to close, no event');
  assert(C(true, sig('League'), true, null, 't1') === false, 'A6f. a team the user opened themselves (no arrival): left alone');
  assert(C(true, sig('Trades'), true, 't1', 't1') === false, 'A6g. a tap armed for another tab: League does nothing');
  assert(C(true, sig('League'), false, 't1', 't1') === false, 'A6h. the legacy root-stack League page never reacts');
  assert(C(false, sig('League'), true, 't1', 't1') === false, 'A6i. unified off: the bar tap closes nothing (today\'s bar)');

  // The sequence: tile arrival → drill-in open → "‹ Home" → exactly one
  // league_team_closed{home_back}, closed BEFORE the navigate.
  const zustand = require(path.join(MOBILE, 'node_modules/zustand'));
  const store = load('src/state/homeReturn.ts', (r) => {
    if (r === 'zustand') return zustand;
    if (r === '../navigation/navContinuity') return nc;
    throw new Error(`homeReturn.ts asked for ${r}`);
  });
  const s = store.useHomeReturn;
  const log = [];
  const run = (unified, { openOther = false } = {}) => {
    log.length = 0;
    const page = { arrival: null, selected: null, focus: null };
    const closeTeam = (via) => {
      // LeagueSummaryScreen's emitTeamClosed: no-op when nothing is focused.
      if (page.focus) log.push(`league_team_closed:${via}`);
      page.focus = null;
      page.selected = null;
    };
    const unsub = unified
      ? s.subscribe((state, prev) => {
          if (state.returned.seq === prev.returned.seq) return;
          if (nc.rosterClosesOnHomeReturn(unified, state.returned, true, page.arrival, page.selected)) closeTeam('home_back');
        })
      : () => {};
    s.getState().noteTabFocus('Home');
    store.armHomeReturn('position_roster', unified);
    s.getState().noteTabFocus('League');
    page.arrival = 't1'; page.selected = 't1'; page.focus = 't1';
    if (openOther) { page.selected = 't2'; page.focus = 't2'; }
    const barShown = nc.homeReturnVisible(s.getState(), s.getState().focusedTab, true);
    if (barShown) {
      s.getState().requestReturn();
      log.push('navigate:Home');
      s.getState().noteTabFocus('Home');
    }
    unsub();
    return { barShown, header: nc.rosterHeaderHomeVisible(true, page.arrival, page.selected, unified) };
  };
  const on = run(true);
  assert(on.barShown && log.join(' > ') === 'league_team_closed:home_back > navigate:Home',
    'A6j. unified: "‹ Home" closes the arrival\'s drill-in with ONE home_back, then goes Home', log.join(' > '));
  run(true, { openOther: true });
  assert(log.join(' > ') === 'navigate:Home', 'A6k. unified, another team open: no home_back, just Home', log.join(' > '));
  const off = run(false);
  assert(!off.barShown && off.header === true && log.length === 0,
    'A6l. unified off: no bar for the arrival, D-269\'s header control shows instead');
}

// ═══════════════════════════════════════════════════════════════════════
// A3 — R4: the Back-or-fallback decision tests the page's OWN stack.
// ═══════════════════════════════════════════════════════════════════════
{
  // First page of its tab: own stack index 0, but canGoBack() is true
  // because the tabs can go back to Home (finding C1).
  assert(nc.backOrFallback({ index: 0 }, true, true) === 'fallback',
    'A3a. flag on, first page of the tab: the coded fallback, not Home');
  assert(nc.backOrFallback({ index: 0 }, true, false) === 'back',
    'A3b. flag off: today\'s canGoBack() result (back, i.e. Home)');
  assert(nc.backOrFallback({ index: 2 }, true, true) === 'back', 'A3c. a page underneath: Back pops');
  assert(nc.backOrFallback(undefined, false, true) === 'fallback' && nc.backOrFallback(null, false, false) === 'fallback',
    'A3d. no state: the fallback');
}

// ═══════════════════════════════════════════════════════════════════════
// A4 — R1 / R2: the league picker opened inside the app.
// ═══════════════════════════════════════════════════════════════════════
{
  const st = (...names) => ({ routes: names.map((n, i) => ({ key: `${n}-${i}`, name: n })) });
  const atSignIn = st('LeaguePicker');                       // SignIn replaced
  const fromSwitcher = st('Main', 'LeaguePicker');
  const fromSettings = st('Main', 'Settings', 'SettingsLeagues', 'LeaguePicker');
  const replacedSettings = st('Main', 'LeaguePicker');       // Settings → replace
  const verifyReset = st('LeaguePicker');                    // VerifySheet reset
  assert(!nc.pickerOpenedInApp(atSignIn, 'LeaguePicker-0'), 'A4a. at sign-in the picker is not in-app');
  assert(!nc.pickerOpenedInApp(verifyReset, 'LeaguePicker-0'), 'A4b. after a reset to the picker it is not in-app');
  assert(nc.pickerOpenedInApp(fromSwitcher, 'LeaguePicker-1'), 'A4c. from the league switcher: in-app');
  assert(nc.pickerOpenedInApp(fromSettings, 'LeaguePicker-3'), 'A4d. from Settings: in-app');
  assert(nc.pickerOpenedInApp(replacedSettings, 'LeaguePicker-1'), 'A4e. replaced over Settings: in-app');
  assert(!nc.pickerOpenedInApp(fromSwitcher, 'missing'), 'A4f. an unknown key: not in-app');
  assert(nc.pickerExit(true, true) === 'popTo' && nc.pickerExit(false, true) === 'replace'
    && nc.pickerExit(true, false) === 'replace',
    'A4g. a pick returns to the tabs underneath only in-app with the flag; else replace (today)');
  assert(!nc.pickerAutoSkipAllowed(true, true) && nc.pickerAutoSkipAllowed(false, true)
    && nc.pickerAutoSkipAllowed(true, false),
    'A4h. the one-league auto-forward is suppressed only for an in-app opening with the flag');
}

// ═══════════════════════════════════════════════════════════════════════
// A5 — R3 / R8 / R13 decisions.
// ═══════════════════════════════════════════════════════════════════════
{
  assert(nc.returnOptions(false) === undefined && nc.returnOptions(false, true) === undefined,
    'A5a. flag off: no navigate options (today\'s push)');
  const o = nc.returnOptions(true);
  assert(o && o.pop === true && !('merge' in o), 'A5b. flag on: { pop: true }');
  const om = nc.returnOptions(true, true);
  assert(om && om.pop === true && om.merge === true, 'A5c. the rank chooser keeps the page\'s params: { pop, merge }');
  const r = nc.signInReset();
  assert(r.index === 0 && r.routes.length === 1 && r.routes[0].name === 'SignIn',
    'A5d. sign-out / deletion / expiry leave SignIn alone on the stack');
  assert(nc.tiersLeavePrompts(true, false, true), 'A5e. unsaved Tiers moves: leaving asks');
  assert(!nc.tiersLeavePrompts(false, false, true), 'A5f. nothing unsaved: no prompt');
  assert(!nc.tiersLeavePrompts(true, true, true), 'A5g. a save in flight: no prompt');
  assert(!nc.tiersLeavePrompts(true, false, false), 'A5h. flag off: no prompt (today)');
  assert(nc.tiersLeavePrompts(true, false, true, 'POP') && nc.tiersLeavePrompts(true, false, true, 'POP_TO_TOP')
    && nc.tiersLeavePrompts(true, false, true, 'NAVIGATE'),
    'A5i. a pop, a Rank re-tap (popToTop) or a navigate-with-pop past Tiers asks');
  assert(!nc.tiersLeavePrompts(true, false, true, 'RESET'),
    'A5j. a stack RESET (sign-out, deletion, expiry) never asks: the session is already gone');
}

// ═══════════════════════════════════════════════════════════════════════
// B1 — R5 call sites: HomeHub arms exactly the taps A1 says, after the
//      track and before the navigate; the bar is mounted once.
// ═══════════════════════════════════════════════════════════════════════
{
  const hub = src('src/components/home/HomeHub.tsx');
  assert(/const homeReturnOn = useFlag\(HOME_RETURN_FLAG\);/.test(hub)
    && /const unifiedOn = useFlag\(HOME_RETURN_UNIFIED_FLAG\);/.test(hub)
    && /const homeReturnUnified = homeReturnUnifiedOn\(homeReturnOn, unifiedOn\);/.test(hub)
    && /const armReturn = \(tap: HomeTileTap\) => \{\s*if \(homeReturnOn\) armHomeReturn\(tap, homeReturnUnified\);\s*\};/.test(hub),
    'B1a. HomeHub arms only while `nav.home_return` is on, telling the store whether unified mode is on');
  const armed = [...hub.matchAll(/armReturn\('([a-z_]+)'\)/g)].map((m) => m[1]);
  const EXPECT_ARMED = [...Object.keys(ARMS), 'position_roster'];
  assert(armed.length === EXPECT_ARMED.length && EXPECT_ARMED.every((t) => armed.includes(t)),
    'B1b. every tab-crossing tile arms, once each (the position tile body too, D-276)', `armed: ${armed.join(', ')}`);
  assert(armed.every((t) => nc.homeReturnTabFor(t, true) !== null), 'B1c. nothing arms a tap that has no tab (unified)');
  // Order inside each arming body: track → armReturn → navigate.
  const ordered = armed.every((t) => {
    const i = hub.indexOf(`armReturn('${t}')`);
    const before = hub.lastIndexOf("track('home_tile_tapped'", i);
    const nav = hub.indexOf('navigation.navigate(', i);
    const nextTrack = hub.indexOf("track('home_tile_tapped'", i);
    return before >= 0 && before > hub.lastIndexOf('=> {', i) - 200 && nav > i && (nextTrack < 0 || nav < nextTrack);
  });
  assert(ordered, 'B1d. each arm comes after its track and before its navigate');
  // Rank-page tiles untouched.
  const rankTile = (hub.match(/testID="home\.tile\.rank"[\s\S]*?\/>/) || [''])[0];
  const trendsTile = (hub.match(/testID="home\.tile\.trends"[\s\S]*?\/>/) || [''])[0];
  assert(/navigation\.navigate\('Rank'\);/.test(rankTile) && !/armReturn/.test(rankTile)
    && /navigation\.navigate\('Rank', \{ screen: 'Trends' \}\);/.test(trendsTile) && !/armReturn/.test(trendsTile),
    'B1e. Rank players and Check trends are exactly as before (rank pages, no control)');
  const roster = (hub.match(/const onOpenRoster = [\s\S]*?\n  \};/) || [''])[0];
  assert(roster && /\n    if \(homeReturnUnified\) armReturn\('position_roster'\);\n/.test(roster)
    && (roster.match(/armReturn/g) || []).length === 1,
    'B1f. the D-269 roster arrival arms the bar ONLY in unified mode (off: exactly as before, no arm call)');

  const tab = src('src/navigation/TabNav.tsx');
  const top = tab.indexOf('<TopBar />');
  const bar = tab.indexOf('<HomeReturnBar />');
  const nav = tab.indexOf('<Tab.Navigator');
  assert(top >= 0 && bar > top && nav > bar && (tab.match(/<HomeReturnBar \/>/g) || []).length === 1,
    'B1g. the control is mounted once, between the top bar and the tabs');
  assert(/screenListeners=\{\(\{ route \}\) => \(\{\s*focus: \(\) => useHomeReturn\.getState\(\)\.noteTabFocus\(route\.name\),\s*\}\)\}/.test(tab),
    'B1h. every tab focus is reported (the visit ends when the tab changes)');

  const hb = src('src/components/HomeReturnBar.tsx');
  assert(/const flagOn = useFlag\(HOME_RETURN_FLAG\);/.test(hb)
    && /homeReturnVisible\(s, s\.focusedTab, flagOn\)/.test(hb) && /if \(!visible\) return null;/.test(hb),
    'B1i. the bar draws nothing unless flag on, armed and on the armed tab');
  assert(/testID="home-return\.back"/.test(hb) && /accessibilityLabel="Back to Home"/.test(hb)
    && /navigation\.navigate\('Main', \{ screen: 'Home' \}\)/.test(hb) && /<Text style=\{styles\.backText\}>Home<\/Text>/.test(hb),
    'B1j. "‹ Home" returns to the Home tab');
  const iSig = hb.indexOf('useHomeReturn.getState().requestReturn();');
  assert(iSig >= 0 && iSig < hb.indexOf("navigation.navigate('Main', { screen: 'Home' })")
    && (hb.match(/requestReturn\(/g) || []).length === 1,
    'B1k. the bar raises its tap signal once, BEFORE it navigates (so the page underneath still has focus)');
  assert(!/League|closeTeam|home_back|LeagueSummary|selectedId/.test(hb),
    'B1l. the bar holds no League rankings knowledge');
}

// ═══════════════════════════════════════════════════════════════════════
// B9 — D-276 call site in League rankings: the header control and the bar
//      listener go through A6's helpers; either flag off ⇒ no listener.
// ═══════════════════════════════════════════════════════════════════════
{
  const ls = src('src/screens/LeagueSummaryScreen.tsx');
  assert(/const homeReturnUnified = homeReturnUnifiedOn\(\s*useFlag\(HOME_RETURN_FLAG\),\s*useFlag\(HOME_RETURN_UNIFIED_FLAG\),\s*\);/.test(ls),
    'B9a. League rankings reads BOTH flags into one unified switch');
  assert(/const showHomeBack = rosterHeaderHomeVisible\(isTabRoot, homeBackId, selectedId, homeReturnUnified\);/.test(ls),
    'B9b. the header "Home" control shows through rosterHeaderHomeVisible (hidden in unified mode)');
  const eff = (ls.match(/useEffect\(\(\) => \{\s*if \(!homeReturnUnified \|\| !isTabRoot\) return;[\s\S]*?\n  \}, \[[^\]]*\]\);/) || [''])[0];
  assert(!!eff, 'B9c. the bar listener is only subscribed in unified mode, on the tab root');
  assert(/return useHomeReturn\.subscribe\(\(state, prev\) => \{/.test(eff)
    && /if \(state\.returned\.seq === prev\.returned\.seq\) return;/.test(eff),
    'B9d. it subscribes (and unsubscribes by returning) and reacts only to a NEW tap signal');
  assert(/if \(rosterClosesOnHomeReturn\(homeReturnUnified, state\.returned, isTabRoot, homeBackId, selectedId\)\) \{\s*closeTeam\('home_back'\);\s*\}/.test(eff)
    && (eff.match(/closeTeam\(/g) || []).length === 1,
    "B9e. the close goes through rosterClosesOnHomeReturn and the one exit path, closeTeam('home_back')");
  assert(/\}, \[homeReturnUnified, isTabRoot, homeBackId, selectedId, closeTeam\]\);/.test(eff),
    'B9f. it re-subscribes when the arrival or the open team changes (no stale ids)');
  assert((ls.match(/closeTeam\('home_back'\)/g) || []).length === 2,
    "B9g. 'home_back' has exactly two emitters: D-269's header control and the bar listener (never both shown)");
}

// ═══════════════════════════════════════════════════════════════════════
// B2 — R1 / R2: the picker's Close, the auto-forward, the pick's exit.
// ═══════════════════════════════════════════════════════════════════════
{
  const rn = src('src/navigation/RootNav.tsx');
  assert(/const continuityOn = useFlag\(CONTINUITY_FLAG\);/.test(rn), 'B2a. RootNav reads `nav.continuity`');
  assert(/const inApp = continuityOn && pickerOpenedInApp\(navigation\.getState\(\), route\.key\);/.test(rn),
    'B2b. in-app = flag on AND the tabs are under the picker');
  assert(/if \(pickerExit\(pickerOpenedInApp\(navigation\.getState\(\), route\.key\), continuityOn\) === 'popTo'\) \{\s*refreshAfterLeagueChange\(\);\s*navigation\.popTo\('Main'\);\s*\} else \{\s*navigation\.replace\('Main'\);\s*\}/.test(rn),
    'B2c. a pick returns to the existing tabs in-app (after the league-change refresh), else replace (today)');
  {
    // The tabs stay mounted on the popTo path, so the pick must refresh what
    // the in-place switch refreshes: one shared function, used by both.
    const us2 = src('src/state/useSession.ts');
    const fn = (us2.match(/export function refreshAfterLeagueChange\(\): void \{([\s\S]*?)\n\}/) || [])[1] || '';
    assert(/noteTradeInputChange\('after_league_switch'\)/.test(fn)
      && ['portfolio', 'rankings', 'progress', 'streak', 'tiers-status', 'awaiting-trades'].every((k) => fn.includes("['" + k + "']"))
      && fn.includes("['matches', 'all']"),
      'B2c2. refreshAfterLeagueChange tells the trade inputs and invalidates the league-agnostic caches');
    const swStart = us2.indexOf('switchLeague: async');
    const sw = us2.slice(swStart, us2.indexOf('setInvitedBy: (username) =>', swStart));
    assert(swStart > 0 && sw.length > 200, 'B2c3-pre. switchLeague located');
    assert(/refreshAfterLeagueChange\(\);/.test(sw) && !/invalidateQueries/.test(sw),
      'B2c3. the in-place switch uses the same function (no second copy to drift)');
  }
  assert(/onClose=\{inApp \? \(\) => navigation\.goBack\(\) : undefined\}/.test(rn) && /openedInApp=\{inApp\}/.test(rn),
    'B2d. Close (back to where it was opened) only in-app');
  const lp = src('src/screens/LeaguePickerScreen.tsx');
  assert(/\{onClose \? \([\s\S]*?testID="leagues\.close" label="Close"[\s\S]*?onPress=\{onClose\}[\s\S]*?\) : \(\s*<Button label="Sign out" variant="ghost" compact onPress=\{onSignOut\} \/>\s*\)\}/.test(lp),
    'B2e. the picker draws Close only when given one; otherwise its header is unchanged');
  const skip = (lp.match(/const autoSkipTried = useRef\(false\);[\s\S]*?\}, \[[^\]]*\]\);/) || [''])[0];
  assert(/if \(openedInApp\) return;/.test(skip) && skip.indexOf('if (openedInApp) return;') < skip.indexOf('pickLeague(cached[0]'),
    'B2f. the one-league auto-forward returns early for an in-app opening');
}

// ═══════════════════════════════════════════════════════════════════════
// B3 — R2: no second copy of the tabs.
// ═══════════════════════════════════════════════════════════════════════
{
  const ut = src('src/screens/UsageTrendsScreen.tsx');
  assert(/if \(continuityOn\) navigation\.popTo\('Main', \{ screen: 'Trades', params: \{ screen: 'TradesHome', pop: true \} \}\);\s*else navigation\.navigate\('Main', \{ screen: 'Trades', params: \{ screen: 'TradesHome' \} \}\);/.test(ut),
    'B3a. Usage Trends\' Trade: popTo Main (flag) / today\'s navigate');
  assert(/if \(continuityOn\) navigation\.popTo\('Main', to\);\s*else navigation\.navigate\('Main', to\);/.test(ut),
    'B3b. Usage Trends\' Re-rank: popTo Main (flag) / today\'s navigate');
  const dr = src('src/screens/DraftRoomScreen.tsx');
  assert(/if \(continuityOn\) \{\s*navigation\?\.popTo\?\.\('Main', \{[\s\S]*?returnInTabs: inTabs[\s\S]*?\}\);\s*return;\s*\}\s*navigation\?\.navigate\?\.\('Main', \{/.test(dr),
    'B3c. the Draft Room\'s Rank the rookies: popTo Main (flag) / today\'s navigate');
  const rr = src('src/screens/RookieRanksScreen.tsx');
  assert(/const returnInTabs: boolean = route\?\.params\?\.returnInTabs === true;/.test(rr)
    && /returnInTabs\s*\?\s*navigation\?\.navigate\?\.\('Draft'\)\s*:\s*navigation\?\.navigate\?\.\(\s*'DraftRoom',/.test(rr),
    'B3d. "Back to the draft room" returns to the Draft tab when it came from there');
}

// ═══════════════════════════════════════════════════════════════════════
// B4 — R3: return to the page already underneath (G-056).
// ═══════════════════════════════════════════════════════════════════════
{
  const tr = src('src/screens/TeamReviewScreen.tsx');
  assert(/nav\.navigate\('TradesHome', undefined, returnOptions\(continuityOn\)\);/.test(tr),
    'B4a. Team review\'s Find my trades returns to the landing');
  const lg = src('src/screens/LeagueScreen.tsx');
  assert(/navigation\.navigate\('Trades', continuityOn \? \{ screen: 'TradesHome', pop: true \} : \{ screen: 'TradesHome' \}\);/.test(lg),
    'B4b. League home\'s Find a trade returns to the landing');
  assert(/navigation\.navigate\('LeagueRankings', undefined, returnOptions\(continuityOn\)\);/.test(lg),
    'B4c. League home\'s Rankings returns to League rankings underneath');
  const mt = src('src/screens/MatchesScreen.tsx');
  assert(/navigation\.navigate\('Trades', continuityOn \? \{ screen: 'TradesHome', pop: true \} : \{ screen: 'TradesHome' \}\)/.test(mt)
    && /canvasPrefillSeq: Date\.now\(\),\s*\},\s*\.\.\.\(continuityOn \? \{ pop: true \} : \{\}\),/.test(mt),
    'B4d. Matches\' Find a trade and Open in calculator return to the landing');
  const ls = src('src/screens/LeagueSummaryScreen.tsx');
  assert(/navigation\.navigate\('Trades', continuityOn \? \{ screen: 'TradesHome', pop: true \} : \{ screen: 'TradesHome' \}\);/.test(ls),
    'B4e. League rankings\' Offer / Target hand-off returns to the landing (not a Home origin: no "‹ Home")');
  const rh = src('src/screens/RankHomeScreen.tsx');
  assert(/if \(continuityOn\) navigation\.navigate\(m\.route, undefined, returnOptions\(true, true\)\);\s*else navigation\.navigate\(m\.route\);/.test(rh),
    'B4f. the chooser\'s method cards return to the page underneath (navigate, never replace)');
  assert(!/navigation\.replace\(m\.route/.test(rh), 'B4g. the chooser never replaces (#162/#165)');
  const tab = src('src/navigation/TabNav.tsx');
  const mw = (tab.match(/function MoreWaysButton[\s\S]*?\n\}/) || [''])[0];
  assert(/continuityOn\s*\?\s*navigation\.navigate\('RankHome', undefined, returnOptions\(true\)\)\s*:\s*navigation\.navigate\('RankHome'\)/.test(mw)
    && /testID="rank\.more-ways"/.test(mw),
    'B4h. "More ways to rank" returns to the chooser when it is underneath; still the one exit');
}

// ═══════════════════════════════════════════════════════════════════════
// B5 — R4: own-stack fallbacks.
// ═══════════════════════════════════════════════════════════════════════
{
  const tab = src('src/navigation/TabNav.tsx');
  const hb = (tab.match(/function HeaderBack[\s\S]*?\n\}/) || [''])[0];
  assert(/backOrFallback\(navigation\.getState\?\.\(\), navigation\.canGoBack\(\), continuityOn\) === 'back'\s*\?\s*navigation\.goBack\(\)\s*:\s*navigation\.navigate\(fallback\)/.test(hb),
    'B5a. the shared tab-stack Back tests its own stack');
  for (const [file, fallback] of [
    ['src/screens/QuickSetTiersScreen.tsx', 'Tiers'],
    ['src/screens/QuickRankScreen.tsx', 'Tiers'],
    ['src/screens/RosterSetupScreen.tsx', 'TradesHome'],
  ]) {
    const s = src(file);
    const re = new RegExp(`if \\(backOrFallback\\(navigation\\.getState\\?\\.\\(\\), navigation\\.canGoBack\\(\\), continuityOn\\) === 'back'\\) navigation\\.goBack\\(\\);\\s*else navigation\\.navigate\\('${fallback}'\\);`);
    assert(re.test(s) && !/if \(navigation\.canGoBack\(\)\) navigation\.goBack\(\);/.test(s),
      `B5b. ${path.basename(file)}: own-stack test, fallback ${fallback}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════
// B6' — R8's stack reset must not be held by a page's leave prompt.
// ═══════════════════════════════════════════════════════════════════════
{
  const rs = src('src/screens/RosterSetupScreen.tsx');
  const imp = (rs.match(/implicitExitRef\.current = \(e: any\) => \{[\s\S]*?\n  \};/) || [''])[0];
  const resetAt = imp.indexOf("if (continuityOn && e?.data?.action?.type === 'RESET') {");
  assert(resetAt > 0 && resetAt < imp.indexOf('e?.preventDefault?.()'),
    'B6\'a. Roster setup lets a RESET (sign-out) through before any prompt or skip bookkeeping');
}

// ═══════════════════════════════════════════════════════════════════════
// B6 — R8: sign-out, deletion and expiry reset the stack.
// ═══════════════════════════════════════════════════════════════════════
{
  const sa = src('src/screens/settings/SettingsAccountScreen.tsx');
  assert(/continuityOn \? navigation\.reset\(signInReset\(\)\) : navigation\.replace\('SignIn'\)/.test(sa)
    && /<SignOutRow onSignedOut=\{toSignIn\} \/>/.test(sa) && /onAccountDeleted=\{toSignIn\}/.test(sa),
    'B6a. Settings › Account: sign-out and deletion reset (flag) / replace (today)');
  const ss = src('src/screens/SettingsScreen.tsx');
  assert(/continuityOn \? navigation\.reset\?\.\(signInReset\(\)\) : navigation\.replace\?\.\('SignIn'\)/.test(ss)
    && (ss.match(/toSignIn\(\);/g) || []).length === 2 && (ss.match(/navigation\.replace\?\.\('SignIn'\)/g) || []).length === 1,
    'B6b. the flat Settings list: both sign-out and deletion go through the reset');
  const rn = src('src/navigation/RootNav.tsx');
  assert(/if \(continuityOn\) navigation\.reset\(signInReset\(\)\);\s*else navigation\.replace\('SignIn'\);/.test(rn),
    'B6c. the picker\'s Sign out resets');
  const us = src('src/state/useSession.ts');
  assert(/if \(useFeatureFlags\.getState\(\)\.flags\['nav\.continuity'\]\) \{\s*navigationRef\.reset\(\{ index: 0, routes: \[\{ name: 'SignIn' as never \}\] \}\);\s*\} else \{\s*navigationRef\.navigate\('SignIn' as never\);\s*\}/.test(us),
    'B6d. session expiry resets to SignIn (flag) / pushes it (today)');
}

// ═══════════════════════════════════════════════════════════════════════
// B7 — R9: Portfolio's Back; See liked → Matches › Awaiting.
// ═══════════════════════════════════════════════════════════════════════
{
  const tab = src('src/navigation/TabNav.tsx');
  assert(/name="Portfolio"\s*component=\{PortfolioScreen\}\s*options=\{continuityOn \? subScreenOptions\('Portfolio', 'TradesHome'\) : chalklineHeader\('Portfolio'\)\}/.test(tab),
    'B7a. Portfolio: the app\'s Back (flag) / the plain header (today)');
  const tsx = src('src/screens/TradesScreen.tsx');
  const see = (tsx.match(/testID="trades\.deck-summary\.see-liked"[\s\S]*?\/>/) || [''])[0];
  assert(/continuityOn\s*\?\s*navigation\.navigate\('Matches', \{\s*segment: 'awaiting',/.test(see)
    && /:\s*navigation\.navigate\('Portfolio'\)\}/.test(see) && /label="See liked"/.test(see),
    'B7b. See liked opens Matches › Awaiting (flag) / Portfolio (today), label unchanged');
}

// ═══════════════════════════════════════════════════════════════════════
// B8 — R13: the three sentences are links; Tiers asks before dropping moves.
// ═══════════════════════════════════════════════════════════════════════
{
  const rs = src('src/screens/RosterSetupScreen.tsx');
  assert(/testID="roster-setup\.done\.dna-link"[\s\S]{0,200}accessibilityRole="link"[\s\S]{0,200}onPress=\{\(\) => void onOpenTradeDna\(\)\}[\s\S]{0,40}>\s*Trade DNA › Your roster\s*<\/Text>/.test(rs)
    && /\) : \(\s*<Text style=\{styles\.doneHint\}>Change any of this later in Trade DNA › Your roster\.<\/Text>\s*\)\}/.test(rs),
    'B8a. Roster setup: "Trade DNA › Your roster" is a link (flag); the sentence is unchanged (off)');
  assert(/navigation\.navigate\('TradesHome', \{ editDna: true \}, returnOptions\(true\)\);/.test(rs)
    && /await drain\(\);\s*exitHandledRef\.current = true;/.test(rs),
    'B8b. the link drains writes, then returns to the landing with Trade DNA open');
  const rh = src('src/screens/RankHomeScreen.tsx');
  assert(/testID="rank-home\.settings-link"[\s\S]{0,300}navigation\.navigate\(settingsHubOn \? 'SettingsRanking' : 'Settings'\)[\s\S]{0,40}>\s*Settings\s*<\/Text>/.test(rh),
    'B8c. Rank chooser: "Settings" is a link to the ranking-method setting');
  const tsx = src('src/screens/TradesScreen.tsx');
  assert(/\+ 'Standing offers\.',\s*tone: 'success',\s*\.\.\.\(continuityOn\s*\?\s*\{\s*holdMs: 5000,\s*action: \{\s*label: 'Standing offers',\s*onPress: \(\) => navigation\.navigate\('Matches', \{ segment: 'standing', at: Date\.now\(\) \}\),/.test(tsx),
    'B8d. the standing-offer toast links to Matches › Standing offers (sentence unchanged)');
  const mt = src('src/screens/MatchesScreen.tsx');
  assert(/else if \(s === 'standing' && continuityOn && standingOffersOn\) setSegment\('standing'\);/.test(mt),
    'B8e. Matches opens the Standing offers segment for that link, only while it exists');
  const tiers = src('src/screens/TiersScreen.tsx');
  const eff = (tiers.match(/const continuityOn = useFlag\(CONTINUITY_FLAG\);[\s\S]*?\}, \[continuityOn, navigation, tiersSaving\]\);/) || [''])[0];
  assert(/if \(!continuityOn\) return;/.test(eff) && /navigation\.addListener\('beforeRemove'/.test(eff)
    && /if \(!tiersLeavePrompts\(bucketsDirtyRef\.current, tiersSaving, true, e\?\.data\?\.action\?\.type\)\) return;\s*e\.preventDefault\(\);/.test(eff)
    && /Alert\.alert\('Discard your tier changes\?'/.test(eff) && /navigation\.dispatch\(e\.data\.action\)/.test(eff),
    'B8f. Tiers: leaving with unsaved moves asks first (Roster setup\'s wording)');
}

// ═══════════════════════════════════════════════════════════════════════
// C — the flags: code default False, shipped true, mirrored, client agrees.
// ═══════════════════════════════════════════════════════════════════════
{
  const cfg = JSON.parse(readRoot('config/features.json'));
  const ffPy = readRoot('backend/feature_flags.py');
  const flags = read('src/state/useFeatureFlags.ts');
  for (const f of ['nav.home_return', 'nav.continuity', 'nav.home_return_unified']) {
    assert(cfg[f] === true, `C1. config/features.json ships ${f} true`);
    assert(new RegExp(`\\n    "${f.replace('.', '\\.')}",\\n`).test(ffPy), `C2. ${f} registered in FLAG_KEYS (code default False)`);
    assert(flags.includes(`  '${f}': true,\n`), `C3. the client's compiled default for ${f} matches config`);
    for (const fx of ['release', 'onboarding-v2', 'profiles-on']) {
      const j = JSON.parse(readRoot(`backend/tests/fixtures/flags/${fx}.json`));
      assert(j[f] === true, `C4. ${fx} fixture mirrors ${f}`);
    }
  }
}

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
