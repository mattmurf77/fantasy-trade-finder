#!/usr/bin/env node
// Home's next move (flag `league.next_move`; docs/plans/home-next-move/
// scope.md, D-278).
//
// EXECUTES utils/homeNextMove (with the real utils/maxPfMoves,
// utils/playoffTargets, utils/playoffOdds and the copy tables it runs), and
// RENDERS the real components/home/HomeNextMove against host stubs:
//   A. which block the row honours (flag, version, state, shape);
//   B. a sell: the line, and the live-roster check (the player still on it);
//   C. a buy: the line, the seller's live roster and owner;
//   D. nothing: every `none` block, flag off, no rosters ⇒ no row at all;
//   E. the tap is the list row's own "Find trades": same pins, same event,
//      same destination and params as the Improve page row's hand-off;
//   F. HomeHub: track → "‹ Home" arm (Trades) → navigate, mounted directly
//      under the playoff card; the tile value;
//   G. the copy table equals the scope's §7 table, both directions;
//   H. the component: renders the line, nothing when the util says nothing;
//   I. the flag: shipped true, client default true, mirrored in fixtures.
// No simulator, network or account write (D-056).
//
// Run: node tests/check-home-next-move.js
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const readRoot = (rel) => fs.readFileSync(path.join(MOBILE, '..', rel), 'utf8');
const strip = (s) => s.replace(/\{\/\*[\s\S]*?\*\/\}/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

function load(rel, requireFn, jsx = false) {
  const m = { exports: {} };
  const out = ts.transpileModule(read(rel), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, ...(jsx ? { jsx: ts.JsxEmit.React } : {}),
  } }).outputText;
  vm.runInNewContext(out, { exports: m.exports, module: m, require: requireFn, Date, Math, JSON, Number, String, Array, Object, Set });
  return m.exports;
}
const noImports = (name) => (r) => { throw new Error(`${name} has no imports, asked for ${r}`); };
const playoffOdds = load('src/utils/playoffOdds.ts', noImports('playoffOdds'));
const maxPfCopy = load('src/utils/maxPfMovesCopy.ts', noImports('maxPfMovesCopy'));
const targetsCopy = load('src/utils/playoffTargetsCopy.ts', noImports('playoffTargetsCopy'));
const copy = load('src/utils/homeNextMoveCopy.ts', noImports('homeNextMoveCopy'));
const maxPf = load('src/utils/maxPfMoves.ts', (r) => ({ './maxPfMovesCopy': maxPfCopy, './playoffOdds': playoffOdds }[r]
  ?? (() => { throw new Error(`maxPfMoves asked for ${r}`); })()));
const targets = load('src/utils/playoffTargets.ts', (r) => ({ './playoffTargetsCopy': targetsCopy, './maxPfMoves': maxPf,
  './playoffOdds': playoffOdds }[r] ?? (() => { throw new Error(`playoffTargets asked for ${r}`); })()));
const u = load('src/utils/homeNextMove.ts', (r) => ({ './homeNextMoveCopy': copy, './maxPfMoves': maxPf,
  './playoffTargets': targets, './playoffOdds': playoffOdds }[r] ?? (() => { throw new Error(`homeNextMove must not require ${r}`); })()));
const nc = load('src/navigation/navContinuity.ts', noImports('navContinuity'));

let passes = 0;
let failures = 0;
function check(cond, name, why) {
  if (cond) { passes += 1; console.log(`PASS  ${name}`); } else { failures += 1; console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`); }
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ── Fixtures: blocks as backend/league_projections/next_move.py serves them ──
function sell(patch = {}) {
  return Object.assign({
    version: 1, state: 'ready', reason: null, direction: 'draft_pick', action: 'sell',
    player: { player_id: '101', name: 'Rhett Sato', short_name: 'R. Sato', position: 'WR' },
    rank: 1, seller: null, captured_at: '2026-11-17T14:00:00Z',
    playoff_probability: { now: 0.30, after: 0.22 },
    playoff_proof: { playoff_clinched: false, playoff_eliminated: false },
    pick: { now: '1.06', after: '1.04' }, most_likely_pick: null,
    top3_probability: { now: 0.20, after: 0.31 },
  }, patch);
}
function buy(patch = {}) {
  return Object.assign({
    version: 1, state: 'ready', reason: null, direction: 'playoffs', action: 'buy',
    player: { player_id: '201', name: 'Dax Ortega', short_name: 'D. Ortega', position: 'RB' },
    rank: 1, seller: { roster_id: 4, name: 'Sellers FC' }, captured_at: '2026-11-17T14:00:00Z',
    playoff_probability: { now: 0.55, after: 0.63 },
    playoff_proof: { playoff_clinched: false, playoff_eliminated: false },
    pick: null, most_likely_pick: null, top3_probability: null,
  }, patch);
}
const none = (reason, direction = null) => Object.assign(sell(), { state: 'none', reason, direction, action: null,
  player: null, rank: null, playoff_probability: null, pick: null, top3_probability: null });
const view = (b) => ({ state: 'current', next_move: b });
const MINE = ['103', '101', '102'];
const ROSTERS = [
  { roster_id: 1, owner_id: 'viewer', players: MINE },
  { roster_id: 4, owner_id: 'owner4', players: ['201', '205'] },
];

// ═══ A. Which block the row honours ═══════════════════════════════════════
{
  check(u.NEXT_MOVE_FLAG === 'league.next_move' && u.NEXT_MOVE_TILE === 'next_move' && u.SCREEN === 'Home',
    'A1. flag key, tile value and screen');
  check(u.honouredBlock(view(sell()), false) === null, 'A2. flag off: nothing, whatever the read holds');
  check(u.honouredBlock(undefined, true) === null && u.honouredBlock({ state: 'current' }, true) === null,
    'A3. no read, or no block (older server): nothing');
  check(u.honouredBlock(view(sell({ version: 2 })), true) === null, 'A4. an unknown version: nothing');
  check(u.honouredBlock(view(sell({ action: 'hold' })), true) === null
    && u.honouredBlock(view(sell({ player: { player_id: '101', name: 'x', short_name: '', position: 'WR' } })), true) === null
    && u.honouredBlock(view(sell({ playoff_probability: { now: 0.3, after: 1.4 } })), true) === null
    && u.honouredBlock(view(buy({ seller: null })), true) === null,
    'A5. a block of a shape this build does not know: nothing');
  check(u.honouredBlock(view(sell()), true) !== null && u.honouredBlock(view(buy()), true) !== null, 'A6. ready blocks are honoured');
}

// ═══ B. A sell ═══════════════════════════════════════════════════════════
{
  const v = u.nextMoveView(view(sell()), true, ROSTERS, MINE);
  check(v && v.action === 'sell' && v.line === 'Sell R. Sato (WR): projected pick 1.06 → 1.04',
    'B1. sell: action, player, position and the projected pick now → after', v && v.line);
  check(v && v.label === 'Next move' && v.actionLabel === 'Find trades' && v.opponentId === null,
    'B2. the label, the action label, no partner');
  check(v && v.accessibilityLabel === 'Next move. Sell R. Sato (WR): projected pick 1.06 → 1.04. Find trades for R. Sato.',
    'B3. one spoken label naming the tap', v && v.accessibilityLabel);
  check(u.nextMoveView(view(sell()), true, ROSTERS, null) === null, 'B4. the live roster not loaded: nothing (the check always runs)');
  check(u.nextMoveView(view(sell()), true, ROSTERS, [...MINE, '104']) !== null
    && u.nextMoveView(view(sell()), true, ROSTERS, ['101', '109']) !== null,
    'B5. other adds and drops since the forecast: the row still shows (only the named player matters)');
  check(u.nextMoveView(view(sell()), true, ROSTERS, ['102', '103']) === null
    && u.nextMoveView(view(sell()), true, ROSTERS, ['102', '103', '109']) === null,
    'B6. the named player traded away (or swapped): nothing, never the next row');
  const top3 = u.nextMoveView(view(sell({ pick: { now: '1.06', after: '1.06' } })), true, ROSTERS, MINE);
  check(top3 && top3.line === 'Sell R. Sato (WR): top-3 pick chance 20% → 31%', 'B7. pick unchanged: the top-3 pick chance', top3 && top3.line);
  const odds = u.nextMoveView(view(sell({ pick: { now: null, after: null }, top3_probability: { now: 0.2, after: 0.2 } })), true, ROSTERS, MINE);
  check(odds && odds.line === 'Sell R. Sato (WR): playoff chance 30% → 22%', 'B8. neither moves visibly: the playoff chance', odds && odds.line);
  const proof = u.nextMoveView(view(sell({ pick: null, top3_probability: null, playoff_probability: { now: 0.002, after: 0.001 },
    playoff_proof: { playoff_clinched: false, playoff_eliminated: false } })), true, ROSTERS, MINE);
  check(proof && proof.line.endsWith('playoff chance <1% → <1%'), 'B9. D-262: 0% only with a proof (playoffOddsText)', proof && proof.line);
}

// ═══ C. A buy ════════════════════════════════════════════════════════════
{
  const v = u.nextMoveView(view(buy()), true, ROSTERS, MINE);
  check(v && v.action === 'buy' && v.line === 'Buy D. Ortega (RB) from Sellers FC: playoff chance 55% → 63%',
    'C1. buy: action, player, position, team and the playoff chance now → after', v && v.line);
  check(v && v.opponentId === 'owner4', 'C2. the partner is the team\'s live owner');
  check(u.nextMoveView(view(buy()), true, null, MINE) === null, 'C3. the live rosters not loaded: nothing (no partner, no button on the list either)');
  check(u.nextMoveView(view(buy()), true, [ROSTERS[0], { roster_id: 4, owner_id: 'owner4', players: ['205'] }], MINE) === null,
    'C4. he left that team: nothing, never the next row');
  check(u.nextMoveView(view(buy()), true, [ROSTERS[0], { roster_id: 4, owner_id: null, players: ['201'] }], MINE) === null,
    'C5. the team has no live owner: nothing');
  check(u.nextMoveView(view(buy()), true, ROSTERS, null) !== null, 'C6. a buy does not need the viewer\'s own roster');
}

// ═══ D. Nothing ══════════════════════════════════════════════════════════
{
  const reasons = ['direction_off', 'unavailable', 'no_direction', 'not_offered', 'no_moves', 'pick_owned_elsewhere',
    'draft_order_unanswered', 'collapsed', 'settled', 'keep', 'below_threshold', 'no_targets', 'read_failed'];
  check(reasons.every((r) => u.nextMoveView(view(none(r)), true, ROSTERS, MINE) === null),
    'D1. every `none` block, whatever its reason: no row');
  check(u.nextMoveView(view(sell()), false, ROSTERS, MINE) === null && u.nextMoveView(view(buy()), false, ROSTERS, MINE) === null,
    'D2. flag off: no row');
}

// ═══ E. The tap is the list row's own "Find trades" ═══════════════════════
function deps(log) {
  return {
    setSide: (side, players) => log.push(['setSide', side, players]),
    track: (event, props, screen) => log.push(['track', event, props, screen]),
    navigate: (params) => log.push(['navigate', params]),
    now: () => 42,
  };
}
{
  const v = u.nextMoveView(view(sell()), true, ROSTERS, MINE);
  const mine = [];
  check(u.nextMoveTap(v, deps(mine)) === true, 'E1. sell: the hand-off runs');
  // The Improve Draft Pick page row's own hand-off, for the same player.
  const row = { keep: false, player_id: '101', name: 'Rhett Sato', position: 'WR' };
  const pageLog = [];
  maxPf.handOffToFinder(row, Object.assign(deps(pageLog), { screen: 'ImproveDraftPick' }));
  const sameExceptScreen = (a, b) => a.length === b.length && a.every((e, i) => (e[0] === 'track'
    ? same(e.slice(0, 3), b[i].slice(0, 3)) && e[3] === 'Home' : same(e, b[i])));
  check(sameExceptScreen(mine, pageLog), 'E2. sell: the same pins, event and navigation as the page row\'s Find trades (screen Home)',
    JSON.stringify(mine));
  check(same(mine[0], ['setSide', 'give', [{ id: '101', name: 'Rhett Sato', position: 'WR' }]]) && same(mine[1], ['setSide', 'receive', []])
    && same(mine[2], ['track', 'finder_target_pinned', { side: 'give', source: 'maxpf_moves' }, 'Home']),
    'E3. sell: the player on the give side, receive cleared, finder_target_pinned (give, maxpf_moves) under Home');
  check(same(mine[3], ['navigate', { screen: 'Trades', params: { screen: 'TradesHome',
    params: { canvasPrefill: { give: ['101'], receive: [] }, canvasPrefillSeq: 42 }, pop: true } }]),
    'E4. sell: Trades › TradesHome with the canvas prefill, pop: true (maxPfMoves.finderNavParams)');

  const b = u.nextMoveView(view(buy()), true, ROSTERS, MINE);
  const theirs = [];
  check(u.nextMoveTap(b, deps(theirs)) === true, 'E5. buy: the hand-off runs');
  const pageBuy = [];
  targets.handOffToFinder({ player_id: '201', name: 'Dax Ortega', position: 'RB' }, 'owner4',
    Object.assign(deps(pageBuy), { screen: 'ImprovePlayoffChances' }));
  check(sameExceptScreen(theirs, pageBuy), 'E6. buy: the same pins, event and navigation as the page row\'s Find trades (screen Home)',
    JSON.stringify(theirs));
  check(same(theirs[0], ['setSide', 'receive', [{ id: '201', name: 'Dax Ortega', position: 'RB' }]]) && same(theirs[1], ['setSide', 'give', []])
    && same(theirs[2], ['track', 'finder_target_pinned', { side: 'receive', source: 'playoff_targets' }, 'Home'])
    && same(theirs[3], ['navigate', { screen: 'Trades', params: { screen: 'TradesHome',
      params: { canvasPrefill: { opponentId: 'owner4', give: [], receive: ['201'] }, canvasPrefillSeq: 42 }, pop: true } }]),
    'E7. buy: receive side, give cleared, finder_target_pinned (receive, playoff_targets), Trades with the partner on the canvas');
  check(nc.homeReturnTabFor('next_move') === 'Trades' && nc.homeReturnTabFor('next_move', true) === 'Trades',
    'E8. the tap arms "‹ Home" for the Trades tab (both modes), as the Find a trade tile does');
}

// ═══ F. HomeHub owns the tap and mounts the row under the card ═══════════
{
  const hub = strip(read('src/components/home/HomeHub.tsx'));
  const body = (hub.match(/const onNextMove = \(view: NextMoveView\) => \{[\s\S]*?\n  \};/) || [''])[0];
  const iTrack = body.indexOf("track('home_tile_tapped', { tile: 'next_move' }, 'Home');");
  const iArm = body.indexOf("armReturn('next_move');");
  const iTap = body.indexOf('nextMoveTap(view, {');
  check(iTrack > 0 && iArm > iTrack && iTap > iArm, 'F1. track home_tile_tapped {tile: next_move}, then arm "‹ Home", then the hand-off');
  check(/navigate: \(p\) => navigation\.navigate\(p\.screen, p\.params\),/.test(body)
    && /setSide: \(side, players\) => useFinderTargets\.getState\(\)\.setSide\(side, players\),/.test(body)
    && /\n      track,\n/.test(body) && /now: Date\.now,/.test(body),
    'F2. the hand-off navigates to the params it is given (Home is a tab: navigate, not popTo), with the finder store, track and the clock');
  check((hub.match(/<HomeNextMove /g) || []).length === 1
    && /onDirectionTap=\{onDirectionTap\} \/>\s*<HomeNextMove rosters=\{rostersQuery\.data\}\s*liveIds=\{findMyRoster\(rostersQuery\.data, user\?\.user_id \?\? ''\)\?\.players \?\? null\}\s*onPress=\{onNextMove\} \/>/.test(hub),
    'F3. one row, mounted directly under the playoff card, on the shared rosters query');
  const ls = strip(read('src/screens/LeagueSummaryScreen.tsx'));
  check(!/HomeNextMove|homeNextMove/.test(ls), 'F4. League rankings (the card\'s other host) is unchanged');
  const banner = strip(read('src/components/home/HomePlayoffBanner.tsx'));
  check(!/next_move|NextMove/.test(banner), 'F5. the playoff card itself is unchanged');
}

// ═══ G. The copy is the scope's §7 table, both directions ═════════════════
{
  const scope = readRoot('docs/plans/home-next-move/scope.md');
  const section = scope.slice(scope.indexOf('## 7.'), scope.indexOf('## 8.'));
  const rows = {};
  for (const m of section.matchAll(/^\| `(NM-[A-Z0-9.]+[a-z0-9]*)` \| (.+?) \|/gm)) rows[m[1]] = m[2].replace(/^"|"$/g, '');
  const table = copy.NEXT_MOVE_COPY;
  const missing = Object.keys(table).filter((k) => rows[k] !== table[k]);
  const extra = Object.keys(rows).filter((k) => !(k in table));
  check(Object.keys(table).length === 7 && missing.length === 0 && extra.length === 0,
    'G1. every string in the copy table is in the scope\'s §7 table verbatim, and nothing else is',
    `differs: ${missing.join(', ') || '—'}; only in scope: ${extra.join(', ') || '—'}`);
}

// ═══ H. The component renders what the util says, or nothing ══════════════
{
  const state = { flags: {}, data: undefined, active: { user: { user_id: 'viewer' }, league: { league_id: 'league-a' },
    leagues: [{ league_id: 'league-a', platform: 'sleeper' }], hasToken: true, switching: false }, queries: [] };
  const React = { Fragment: 'Fragment', createElement: (type, props, ...children) => ({ type, props: props || {}, children }) };
  const token = new Proxy({}, { get: (_, key) => new Proxy({}, { get: (__, inner) => `${String(key)}.${String(inner)}` }) });
  const modules = {
    react: { __esModule: true, default: React },
    'react-native': { Pressable: 'Pressable', StyleSheet: { create: (v) => v }, View: 'View' },
    '@tanstack/react-query': { useQuery: (o) => { state.queries.push(o); return { data: state.data }; } },
    '../chalkline': { Text: 'Text' },
    '../../theme/chalkline': token,
    '../../api/leagueProjections': { getLeagueProjectionBatch: () => { throw new Error('render must not fetch'); } },
    '../../state/useSession': { NO_LEAGUE_ID: 'no_league', useSession: (select) => select(state.active) },
    '../../state/useFeatureFlags': { useFlag: (name) => { assert(name in state.flags, `unexpected flag ${name}`); return state.flags[name]; } },
    '../../utils/homeNextMove': u,
    './StatusRow': { RowAction: 'RowAction' },
  };
  const component = load('src/components/home/HomeNextMove.tsx', (name) => {
    assert(name in modules, `unexpected component dependency: ${name}`);
    return modules[name];
  }, true);
  const nodes = (n) => (Array.isArray(n) ? n.flatMap(nodes) : n && typeof n === 'object' ? [n, ...nodes(n.children)] : []);
  const words = (n) => (Array.isArray(n) ? n.flatMap(words) : typeof n === 'string' ? [n] : n && typeof n === 'object' ? words(n.children) : []);
  const pressed = [];
  const render = (data, flags) => {
    state.data = data; state.flags = Object.assign({ 'league.projections': true, 'league.next_move': true }, flags); state.queries = [];
    return component.default({ rosters: ROSTERS, liveIds: MINE, onPress: (v) => pressed.push(v) });
  };
  const tree = render(view(sell()));
  check(tree && tree.props.testID === 'home.next-move' && tree.props.accessibilityRole === 'button'
    && words(tree).includes('Next move') && words(tree).includes('Sell R. Sato (WR): projected pick 1.06 → 1.04'),
    'H1. renders the label and the one line as one button');
  check(nodes(tree).some((n) => n.type === 'RowAction' && n.props.label === 'Find trades'), 'H2. the action reads "Find trades ›"');
  tree.props.onPress();
  check(pressed.length === 1 && pressed[0].action === 'sell' && pressed[0].move.player.player_id === '101', 'H3. a tap hands the view to the host');
  const q = state.queries[0];
  check(q && same(q.queryKey, ['league-projection-batch', 'viewer', 'league-a']) && q.staleTime === 60_000 && q.enabled === true,
    'H4. the card\'s own cached read: same key and staleTime, no new request');
  check(render(view(none('collapsed'))) === null && render(undefined) === null, 'H5. a none block or no data: renders nothing');
  check(render(view(sell()), { 'league.next_move': false }) === null && state.queries[0].enabled === false,
    'H6. flag off: renders nothing and the query stays off (Home as before)');
  check(render(view(sell()), { 'league.projections': false }) === null, 'H7. forecasts off: nothing');
  state.active.leagues = [{ league_id: 'league-a', platform: 'espn' }];
  check(render(view(sell())) === null, 'H8. a non-Sleeper league: nothing');
  state.active.leagues = [{ league_id: 'league-a', platform: 'sleeper' }];
}

// ═══ I. The flag ═════════════════════════════════════════════════════════
{
  const cfg = JSON.parse(readRoot('config/features.json'));
  const flags = read('src/state/useFeatureFlags.ts');
  check(cfg['league.next_move'] === true && /\n    "league\.next_move",\n/.test(readRoot('backend/feature_flags.py')),
    'I1. registered (code default False) and shipped true');
  check(flags.includes("  'league.next_move': true,\n"), 'I2. the client\'s compiled default matches config');
  check(['release', 'onboarding-v2', 'profiles-on'].every((fx) => JSON.parse(readRoot(`backend/tests/fixtures/flags/${fx}.json`))['league.next_move'] === true),
    'I3. mirrored in the three flag fixtures');
}

console.log('');
if (failures) { console.error(`${failures} home next move check(s) FAILED (${passes} passed).`); process.exit(1); }
console.log(`All home next move checks passed (${passes}).`);
