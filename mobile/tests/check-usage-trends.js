#!/usr/bin/env node
// Usage Trends (flag `usage_trends.enabled`, docs/plans/usage-trends/scope.md).
//
// WHY THIS EXISTS. D-056 retired the simulator, so what a sim capture used to
// prove about this screen is pinned here instead:
//   1. The pure readers in src/utils/usageTrends.ts — league status, the
//      list filter (server order, never re-sorted), the plain-language
//      headline, the stats-table cells, the availability label — RUN under
//      plain node against fixtures.
//   2. The wiring: route + deep link, the flag-gated entry points, one
//      FeedbackFAB, Trade = finder pins + handoff, Add = the shared
//      ClaimSheet, Re-rank = QuickSetTiers with positionSeq (which the walk
//      honours on an already-mounted screen), the two views behind one pill,
//      and the Version B table's icon-only actions.
//   3. Analytics: every usage_trends_* name and prop the client emits is
//      registered in backend/analytics_taxonomy.py.
//   4. Flag parity across features.json, the release fixture and FLAG_KEYS.
//
// Run: node tests/check-usage-trends.js
'use strict';

const fs = require('fs');
const path = require('path');
let ts;
try {
  ts = require('typescript');
} catch {
  console.error('check-usage-trends: typescript not installed — run npm ci in mobile/');
  process.exit(1);
}

const MOBILE = path.join(__dirname, '..');
const ROOT = path.join(MOBILE, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const readRoot = (rel) => { try { return fs.readFileSync(path.join(ROOT, rel), 'utf8'); } catch { return ''; } };
const strip = (s) => s.replace(/\{\/\*[\s\S]*?\*\/\}/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

let failures = 0;
const assert = (cond, name, why) => {
  if (cond) console.log(`PASS  ${name}`);
  else { failures += 1; console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`); }
};
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ═══════════════════════════════════════════════════════════════════════
// 1 — the pure module, executed.
// ═══════════════════════════════════════════════════════════════════════
const js = ts.transpileModule(read('src/utils/usageTrends.ts'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const mod = { exports: {} };
new Function('module', 'exports', 'require', js)(mod, mod.exports, (name) => {
  throw new Error(`usageTrends.ts gained a runtime import ("${name}") — it must stay pure.`);
});
const U = mod.exports;

const blk = (o) => ({ counts: [0, 0, 0, 0], shares: [0, 0, 0, 0], avg: null, avg_share: null, signal: null, rank: 1, ...o });
const P = (id, pos, ranks, extra = {}) => ({
  player_id: id, name: `First ${id}`, position: pos, team: 'PHI', status: ['played', 'played', 'played', 'played'],
  snaps: blk({ rank: ranks[0] }), carries: blk({ rank: ranks[1] }), targets: blk({ rank: ranks[2] }), ...extra,
});
const focus = { league_id: 'L1', ok: true, me: 'me', owners: { opp: 'gdubs10' }, rosters: { a: 'me', b: 'opp', c: 'roster:3' } };
const players = [P('a', 'RB', [3, 1, 2]), P('b', 'WR', [1, 3, 3]), P('c', 'TE', [2, 2, 1]), P('d', 'WR', [4, 4, 4])];
{
  assert(U.statusIn(focus, 'a') === 'mine' && U.statusIn(focus, 'b') === 'rostered'
    && U.statusIn(focus, 'c') === 'rostered' && U.statusIn(focus, 'd') === 'free_agent',
    '1a. statusIn: mine / rostered / orphan roster is rostered (never FA) / absent is FA');
  assert(U.statusIn({ ...focus, ok: false }, 'd') === 'unknown' && U.statusIn(undefined, 'd') === 'unknown',
    '1b. an unreadable league is unknown, never "free agent"');
  assert(U.ownerName(focus, 'b') === 'gdubs10' && U.ownerName(focus, 'c') === null && U.ownerName(focus, 'd') === null,
    '1c. ownerName resolves only named owners');
  const ids = (xs) => xs.map((p) => p.player_id);
  assert(eq(ids(U.visiblePlayers(players, focus, 'snaps', 'all')), ['b', 'c', 'a', 'd'])
    && eq(ids(U.visiblePlayers(players, focus, 'targets', 'all')), ['c', 'a', 'b', 'd']),
    '1d. the list follows the server rank of the SELECTED metric');
  assert(eq(ids(U.visiblePlayers(players, focus, 'snaps', 'free_agents')), ['d'])
    && eq(ids(U.visiblePlayers(players, focus, 'snaps', 'rostered')), ['b', 'c', 'a']),
    '1e. Free agents = on no roster; Rostered = on any roster, yours included');
  assert(eq(ids(U.visiblePlayers(players, focus, 'snaps', 'all', 'WR')), ['b', 'd']),
    '1f. the position filter narrows without reordering');
  assert(eq(ids(U.visiblePlayers(players, { ...focus, ok: false }, 'snaps', 'free_agents')), []),
    '1g. unknown status matches only All');
  const other = { league_id: 'L2', ok: true, me: 'me2', owners: {}, rosters: { d: 'me2' } };
  assert(eq(U.availabilitySummary([focus, other, { ...focus, ok: false }], 'd'), { known: 2, freeAgent: 1, mine: 1 }),
    '1h. availabilitySummary counts known leagues only');
  assert(U.availabilityLabel({ known: 3, freeAgent: 2 }) === 'FA 2/3'
    && U.availabilityLabel({ known: 7, freeAgent: 2 }) === 'FA in 2 of 7',
    '1i. pips label up to five leagues, words above');
}
{
  const p = { team: 'PHI', status: ['played', 'played', 'played', 'played'] };
  const spike4 = blk({ counts: [8, 31, 5, 55], shares: [14.5, 40.8, 10, 90.2],
    signal: { kind: 'spike', week: 4, count: 55, share: 90.2, prev_share: 10 } });
  assert(U.headline(p, 'snaps', spike4, 4) === 'Jumped to 90% of Eagles plays',
    '1j. a newest-week jump reads exactly like the approved mock', U.headline(p, 'snaps', spike4, 4));
  assert(U.headline(p, 'snaps', { ...spike4, signal: { ...spike4.signal, week: 3 } }, 4)
    === 'Jumped to 90% of Eagles plays in Week 3', '1k. an older jump names its week');
  assert(U.headline(p, 'targets', spike4, 4, 'count') === 'Jumped to 55 targets', '1l. count unit speaks in counts');
  assert(U.headline({ team: 'LAR', status: ['played', 'out', 'out', 'played'] }, 'snaps',
    blk({ signal: { kind: 'return', week: 4, share: 90.5, count: 76, missed: 2 } }), 4)
    === 'Back in the lineup: 91% of Rams plays', '1m. return');
  assert(U.headline(p, 'snaps', blk({ signal: { kind: 'out', week: 4 } }), 4) === "Didn't play in Week 4", '1n. out');
  assert(U.headline(p, 'carries', blk({ avg_share: 47.7, avg: 8.2 }), 4) === 'Steady at 48% of Eagles carries',
    '1o. no signal reads as steady at the average share');
  assert(!/\bpp\b|baseline|rolling|delta/i.test(read('src/utils/usageTrends.ts').split('export function headline')[1].split('export function isNewsWeek')[0]),
    '1p. the headline vocabulary has no jargon (pp / baseline / rolling / delta)');
  const ps = { status: ['played', 'out', 'bye', 'played'] };
  const b = blk({ counts: [10, null, null, 20], shares: [12.4, null, null, 25.5], avg_share: 19.1 });
  assert(eq([0, 1, 2, 3].map((i) => U.weekCell(ps, b, i, 'count')), ['10', 'OUT', 'BYE', '20'])
    && U.weekCell(ps, b, 3, 'share') === '26%', '1q. table cells: counts, OUT, BYE, %');
  assert(U.lastColumn(b, 'count') === '30' && U.lastColumn(b, 'share') === '19%',
    '1r. right-hand column: TOTAL of played weeks for counts, average for % of team');
  assert(U.shortName('Darius Cooper') === 'D. Cooper' && U.shortName('Marquez Valdes-Scantling') === 'M. Valdes-Scantling'
    && U.shortName('Puka') === 'Puka', '1s. shortName');
  const news = [P('x', 'WR', [1, 1, 1]), P('y', 'WR', [2, 2, 2]), P('z', 'WR', [3, 3, 3])];
  news[0].snaps.signal = { kind: 'spike', week: 4 };
  news[1].snaps.signal = { kind: 'new', week: 4 };
  news[2].snaps.signal = { kind: 'spike', week: 3 };
  assert(U.newsCount(news, 'snaps', 4) === 2, '1t. "Biggest jumps last week" holds only newest-week news');
  assert(U.leagueFormatLine({ total_rosters: 12, settings_type: 2 }) === '12-Team Dynasty'
    && U.leagueFormatLine({}) === null, '1u. league format line from what the league list carries');
}
{
  // Version B column sort (operator, 2026-10-10).
  const row = (id, name, counts, status, shares) => ({
    player_id: id, name, position: 'WR', team: 'PHI', status,
    snaps: blk({ counts, shares, avg_share: shares.filter((x) => x != null).reduce((a, b) => a + b, 0) / 2 }),
    carries: blk(), targets: blk(),
  });
  const P4 = ['played', 'played', 'played', 'played'];
  const rows = [
    row('a', 'Zed Able', [10, 10, 10, 30], P4, [10, 10, 10, 50]),
    row('b', 'Amy Best', [10, 10, 10, 50], P4, [10, 10, 10, 40]),
    row('c', 'Cal Out', [10, 10, 10, null], ['played', 'played', 'played', 'out'], [10, 10, 10, null]),
    row('d', 'Dee Tie', [10, 10, 10, 30], P4, [10, 10, 10, 30]),
  ];
  const ids = (xs) => xs.map((p) => p.player_id).join('');
  assert(ids(U.sortStatsRows(rows, 'snaps', 'count', null)) === 'abcd', '1v. no sort = server order untouched');
  assert(ids(U.sortStatsRows(rows, 'snaps', 'count', { key: 3, dir: 'desc' })) === 'badc',
    '1w. week column, biggest first; ties keep server order; OUT sorts last');
  assert(ids(U.sortStatsRows(rows, 'snaps', 'count', { key: 3, dir: 'asc' })) === 'adbc',
    '1x. reversed — and OUT still sorts last');
  assert(ids(U.sortStatsRows(rows, 'snaps', 'share', { key: 3, dir: 'desc' })) === 'abdc',
    '1y. the % view sorts by % of team, not counts');
  assert(ids(U.sortStatsRows(rows, 'snaps', 'count', { key: 'total', dir: 'desc' })) === 'badc'
    && ids(U.sortStatsRows(rows, 'snaps', 'count', { key: 'player', dir: 'asc' })) === 'bcda',
    '1z. Total (sum of played weeks) and Player (A–Z) sort');
  const a = U.nextSort(null, 3), b = U.nextSort(a, 3), c = U.nextSort(b, 3);
  assert(eq(a, { key: 3, dir: 'desc' }) && eq(b, { key: 3, dir: 'asc' }) && c === null
    && eq(U.nextSort(null, 'player'), { key: 'player', dir: 'asc' })
    && eq(U.nextSort(a, 'total'), { key: 'total', dir: 'desc' }),
    '1aa. header taps: biggest first (A–Z for Player) → reversed → default');
  assert(U.sortLabel(null, [1, 2, 3, 4]) === 'default' && U.sortLabel({ key: 3, dir: 'desc' }, [1, 2, 3, 4]) === 'w4_desc',
    '1ab. analytics sort label');
}
{
  // The user picks which weeks are included (operator, 2026-10-10).
  assert(U.weeksLabel([4]) === 'Week 4' && U.weeksLabel([1, 2, 3, 4]) === 'Weeks 1–4'
    && U.weeksLabel([8, 1, 2, 3, 5, 7]) === 'Weeks 1–3, 5, 7–8', '1ac. selection label collapses runs');
  const avail = [1, 2, 3, 4, 5, 6];
  assert(U.presetWeeks('last4', avail) === null && eq(U.presetWeeks('last2', avail), [5, 6])
    && eq(U.presetWeeks('season', avail), avail), '1ad. presets: Last 4 = the server default, Last 2, All season');
  assert(eq(U.toggleWeek([2, 6], 4), [2, 4, 6]) && eq(U.toggleWeek([2, 4, 6], 4), [2, 6])
    && eq(U.toggleWeek([6], 6), [6]), '1ae. toggling a week; the last one cannot be removed');
  assert(U.weeksParam(null) === 'default' && U.weeksParam([2, 6]) === '2,6', '1af. selection param');
}

// ═══════════════════════════════════════════════════════════════════════
// 2 — wiring.
// ═══════════════════════════════════════════════════════════════════════
const screen = strip(read('src/screens/UsageTrendsScreen.tsx'));
const rootNav = strip(read('src/navigation/RootNav.tsx'));
const links = strip(read('src/utils/deepLinks.ts'));
const fa = strip(read('src/screens/FreeAgentsScreen.tsx'));
const qs = strip(read('src/screens/QuickSetTiersScreen.tsx'));
const table = strip(read('src/components/UsageStatsTable.tsx'));
const card = strip(read('src/components/UsageTrendCard.tsx'));
const icons = strip(read('src/components/chalkline/Icon.tsx'));
{
  assert(/name="UsageTrends"\s+component=\{UsageTrendsScreen\}/.test(rootNav) && /testID="usage-trends\.back-btn"/.test(rootNav),
    '2a. UsageTrends is a root-stack route with the #151 explicit back control');
  assert(/UsageTrends: 'app\/league\/usage-trends'/.test(links), '2b. deep link app/league/usage-trends');
  assert(/const usageTrendsOn = useFlag\('usage_trends\.enabled'\);/.test(fa)
    && /\{usageTrendsOn \? \(\s*<Pressable\s+testID="free-agents\.usage-trends-link"/.test(fa)
    && /navigation\.navigate\('UsageTrends', \{ ownership: 'free_agents' \}\)/.test(fa),
    '2c. Free Agents link: flag-gated, opens pre-filtered to free agents');
  assert((screen.match(/<FeedbackFAB/g) || []).length === 1
    && /<FeedbackFAB activeScreen="UsageTrends" aboveTabBar=\{false\} \/>/.test(screen),
    '2d. exactly one FeedbackFAB, root-stack form (#188)');
  assert(!/\.sort\(/.test(screen), '2e. the screen never sorts itself — server rank via visiblePlayers, column sort via the tested helper');
  {
    const simpleBranch = screen.slice(screen.indexOf("const items: ListItem[] = useMemo"), screen.indexOf('const renderItem'));
    assert(/if \(view !== 'simple'\) \{\s*return sortStatsRows\(list, metric, unit, statsSort\)/.test(simpleBranch)
      && (screen.match(/sortStatsRows\(/g) || []).length === 1,
      '2e2. only Version B applies the column sort; Version A keeps the server order');
    assert(/testID=\{`usage-trends\.sort\.\$\{testKey\}`\}/.test(table) && /onSort\(key\)/.test(table)
      && /sort=\{statsSort\}/.test(screen) && /nextSort\(statsSort, key\)/.test(screen),
      '2e3. every Version B column header is a sort button');
  }
  assert(/useFlag\('usage_trends\.enabled'\)/.test(screen) && /enabled: enabled && !!focusId/.test(screen),
    '2f. no request while the flag is off or there is no league');
  assert(/setSide\('receive', \[\{ id: p\.player_id/.test(screen) && /setHandoff\(\{/.test(screen)
    && /navigation\.navigate\('Main', \{ screen: 'Trades', params: \{ screen: 'TradesHome' \} \}\)/.test(screen),
    '2g. Trade = receive-side pin + opponent handoff + Find a Trade');
  assert(screen.indexOf("if (!(await switchTo(lgId))) return;\n    const store = useFinderTargets.getState();") > 0,
    '2h. pins are written AFTER any league switch (a switch clears them)');
  assert(/from '\.\.\/components\/ClaimSheet'/.test(screen) && /<ClaimSheet/.test(screen)
    && /resolveAddPlatform\(lgId, isDemo\)/.test(screen) && /explainNoAdd\(platform\)/.test(screen),
    '2i. Add reuses the shared claim sheet and the honest no-write-path explanation');
  assert(/from '\.\.\/components\/ClaimSheet'/.test(fa) && !/function ClaimSheet/.test(fa),
    '2j. Free Agents uses the same ClaimSheet (one implementation)');
  assert(/screen: 'Rank',\s*params: \{ screen: 'QuickSetTiers', params: \{ position: p\.position, positionSeq: Date\.now\(\) \} \}/.test(screen),
    '2k. Re-rank opens Quick Set on the player\'s position');
  assert(/const positionSeq = route\.params\?\.positionSeq;/.test(qs)
    && /if \(positionSeq != null && route\.params\?\.position\) onPosition\(route\.params\.position\);/.test(qs),
    '2l. Quick Set switches position on a re-push into a mounted walk');
  assert(/testID=\{`usage-trends\.view\.\$\{v\}`\}/.test(screen) && /\['simple', 'stats'\] as const/.test(screen)
    && /<UsageTrendCard/.test(screen) && /<UsageStatsRow/.test(screen),
    '2m. one pill flips Version A (cards) and Version B (table)');
  assert(/name="plus"/.test(table) && /name="trade"/.test(table) && /name="podium"/.test(table)
    && /name=\{expanded \? 'chevron-down' : 'chevron-right'\}/.test(table),
    '2n. Version B actions: + add, ⇄ trade, podium Re-rank, chevron expander');
  assert(!/>\s*(Add|Trade|Re-rank)\s*</.test(table), '2o. Version B action buttons carry no text');
  assert(/<UsageLeagueList[^>]*compact/.test(table), '2p. the expanded row lists the other leagues');
  assert(/getUsageTrends\(focusId as string, otherIds, selectedWeeks\)/.test(screen)
    && /queryKey: \['usage-trends', focusId, otherIds\.join\(','\), weeksParam\(selectedWeeks\)\]/.test(screen)
    && /placeholderData: keepPreviousData/.test(screen),
    '2p2. the week selection reaches the server and keys the cache; the old list stays up while it loads');
  assert(/<TickLabel>WEEKS<\/TickLabel>/.test(screen) && /testID=\{`usage-trends\.week\.\$\{w\}`\}/.test(screen)
    && /setDraft\(toggleWeek\(shown, w\)\)/.test(screen) && /available=\{data\?\.available_weeks \?\? \[\]\}/.test(screen),
    '2p3. Filters offers every completed week (server-provided) as a toggle, plus presets');
  assert(/const close = \(\) => onClose\(/.test(screen) && /setSelectedWeeks\(nextWeeks\)/.test(screen),
    '2p4. weeks commit once, when the sheet closes (one refetch per change)');
  assert(/export function statsTableWidth/.test(table) && /<ScrollView\s+horizontal/.test(screen)
    && /<UsageStatsHeader/.test(screen.slice(screen.indexOf('const table = ('))),
    '2p5. more than four weeks: the table (header + rows together) swipes sideways');
  assert(/name="podium"/.test(card) && />Re-rank</.test(card) && /<StatusPip/.test(card),
    '2q. Version A keeps the mock: podium Re-rank text button and league pips');
  assert(/\|\s*'podium'/.test(icons) && /^\s*podium: </m.test(icons) && /\|\s*'info'/.test(icons),
    '2r. the podium and info glyphs are in the icon set');
}

// ═══════════════════════════════════════════════════════════════════════
// 3 — analytics registration.
// ═══════════════════════════════════════════════════════════════════════
{
  const tax = readRoot('backend/analytics_taxonomy.py');
  const nonIntent = readRoot('backend/analytics_queries.py');
  const src = [screen].join('\n');
  const calls = [...src.matchAll(/track\('(usage_trends_[a-z_]+)', \{([\s\S]*?)\}, 'UsageTrends'\)/g)];
  const names = new Set(calls.map((m) => m[1]));
  const allowAt = tax.indexOf('ALLOWED_CLIENT_EVENTS: frozenset[str] = frozenset({');
  const allowBlock = allowAt >= 0 ? tax.slice(allowAt, tax.indexOf('\n})', allowAt)) : '';
  assert(eq([...names].sort(), ['usage_trends_action', 'usage_trends_availability_opened', 'usage_trends_view_changed']),
    '3a. the screen emits exactly the three registered names', [...names].join(', '));
  for (const [, name, body] of calls) {
    const props = [...body.matchAll(/^\s*([a-z_]+)(?::|,|$)/gm)].map((m) => m[1]);
    const decl = new RegExp(`"${name}":\\s*frozenset\\(\\{([^}]*)\\}\\)`).exec(tax);
    const allowed = decl ? [...decl[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]) : [];
    const extra = props.filter((p) => !allowed.includes(p));
    assert(new RegExp(`"${name}"`).test(allowBlock) && decl && extra.length === 0,
      `3b. ${name}: in ALLOWED_CLIENT_EVENTS, every prop registered`, extra.length ? `unregistered: ${extra}` : '');
  }
  assert(/"usage_trends_availability_opened",/.test(nonIntent) && /"usage_trends_view_changed",/.test(nonIntent)
    && !/^\s*"usage_trends_action",/m.test(nonIntent), '3c. action is INTENT; the other two are NON_INTENT');
}

// ═══════════════════════════════════════════════════════════════════════
// 4 — flag parity.
// ═══════════════════════════════════════════════════════════════════════
{
  const features = JSON.parse(readRoot('config/features.json') || '{}');
  const release = JSON.parse(readRoot('backend/tests/fixtures/flags/release.json') || '{}');
  assert(features['usage_trends.enabled'] === false && typeof features._comment_usage_trends_enabled === 'string',
    '4a. ships false in config/features.json with a house comment');
  assert(release['usage_trends.enabled'] === false, '4b. release fixture mirrors it');
  for (const f of ['onboarding-v2', 'profiles-on']) {
    const j = JSON.parse(readRoot(`backend/tests/fixtures/flags/${f}.json`) || '{}');
    assert(j['usage_trends.enabled'] === false, `4b. ${f}.json mirrors it`);
  }
  assert(/"usage_trends\.enabled",/.test(readRoot('backend/feature_flags.py')), '4c. registered in FLAG_KEYS');
  const pkg = JSON.parse(read('package.json'));
  assert(pkg.scripts['test:usage-trends'] === 'node tests/check-usage-trends.js', '4d. npm run test:usage-trends');
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nusage-trends: all checks passed');
