#!/usr/bin/env node
// League selector as the header on four more pushed pages
// (docs/plans/free-agents-header-rank/scope.md, addendum 2026-11-12b).
//
// WHY THIS EXISTS. Operator, 2026-11-12, after Free Agents got the global
// TopBar as its header: "Yes add the selector to the recommended pages" —
// Standings, Usage Trends, Track record (Receipts) and Win Now. D-056 retired
// the simulator, so the shape is pinned here:
//   1. Each registers through RootNav's LeagueTopBarHeader (TopBar + the #151
//      JS back control, a literal testID, canGoBack ? goBack : Main) and has
//      no native headerLeft (RNS#3294).
//   2. Usage Trends keeps its info button: the header has a right slot and
//      the registration feeds it the screen's setOptions headerRight.
//   3. Each screen keeps exactly one root-stack FeedbackFAB and pads only the
//      bottom inset (TopBar owns the top).
//   4. A league switch is correct on each screen: the league is in every
//      query key, and league-bound local state is dropped.
//
// Run: node tests/check-league-header-pages.js
'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
// Comments stripped so a pin can never be satisfied by prose.
const strip = (s) => s
  .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^\s*\/\/.*$/gm, '');

let failures = 0;
const assert = (cond, name, why) => {
  if (cond) console.log(`PASS  ${name}`);
  else { failures += 1; console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`); }
};

const rootNav = strip(read('src/navigation/RootNav.tsx'));
const registration = (route) => {
  const start = rootNav.indexOf(`name="${route}"`);
  if (start < 0) return '';
  const end = rootNav.indexOf('<Stack.Screen', start);
  return rootNav.slice(start, end < 0 ? undefined : end);
};

// ── 1. Registrations ─────────────────────────────────────────────────────
const PAGES = [
  { route: 'Standings', component: 'StandingsScreen', title: 'Standings', back: 'standings.back-btn', file: 'src/screens/StandingsScreen.tsx' },
  { route: 'UsageTrends', component: 'UsageTrendsScreen', title: 'Usage Trends', back: 'usage-trends.back-btn', file: 'src/screens/UsageTrendsScreen.tsx' },
  { route: 'Receipts', component: 'ReceiptsScreen', title: 'Track record', back: 'receipts.back-btn', file: 'src/screens/ReceiptsScreen.tsx' },
  { route: 'WinNow', component: 'WinNowScreen', title: 'Win Now', back: 'win-now.back-btn', file: 'src/screens/WinNowScreen.tsx' },
];
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

for (const p of PAGES) {
  const reg = registration(p.route);
  assert(reg.length > 0 && new RegExp(`component=\\{${p.component}\\}`).test(reg),
    `1a. ${p.route}: RootNav registers ${p.component}`);
  assert(new RegExp(`header: \\((\\{ options \\})?\\) => \\(\\s*<LeagueTopBarHeader\\s+title="${esc(p.title)}"`).test(reg),
    `1b. ${p.route}: header is LeagueTopBarHeader titled "${p.title}"`);
  assert(new RegExp(`<HeaderBack\\s+testID="${esc(p.back)}"`).test(reg),
    `1c. ${p.route}: JS back control ${p.back} as a literal testID`);
  assert(/navigation\.canGoBack\(\)\s*\?\s*navigation\.goBack\(\)\s*:\s*navigation\.navigate\('Main'\)/.test(reg),
    `1d. ${p.route}: back = canGoBack ? goBack : navigate(Main)`);
  assert(!/headerLeft\s*:/.test(reg) && !/headerBackVisible\s*:\s*true/.test(reg),
    `1e. ${p.route}: no native headerLeft / native back button (RNS#3294)`);
}

// ── 2. Right slot (Usage Trends' info button) ────────────────────────────
const hdrStart = rootNav.indexOf('function LeagueTopBarHeader(');
const hdr = hdrStart >= 0 ? rootNav.slice(hdrStart, rootNav.indexOf('\n}\n', hdrStart)) : '';
assert(/right\?: React\.ReactNode;/.test(hdr)
  && /\{right \? <View style=\{styles\.leagueSubHeaderRight\}>\{right\}<\/View> : null\}/.test(hdr),
  '2a. LeagueTopBarHeader has an optional right slot, rendered after the title layer');
assert(/right=\{options\.headerRight\?\.\(\{ canGoBack: navigation\.canGoBack\(\) \}\)\}/.test(registration('UsageTrends')),
  "2b. UsageTrends feeds the screen's headerRight into the right slot");
const ut = strip(read('src/screens/UsageTrendsScreen.tsx'));
assert(/navigation\.setOptions\(\{\s*headerRight: \(\) => \(\s*<Pressable\s+testID="usage-trends\.info"/.test(ut),
  '2c. Usage Trends still sets its info button (usage-trends.info) as headerRight');

// ── 3. FeedbackFAB + bottom-only safe area ───────────────────────────────
for (const p of PAGES) {
  const src = strip(read(p.file));
  const fabs = src.match(/<FeedbackFAB\b[^>]*\/>/g) || [];
  const right = fabs.length > 0 && fabs.every((f) =>
    f.includes(`activeScreen="${p.route}"`) && /aboveTabBar=\{false\}/.test(f));
  // Receipts returns three branches (loading / error / content), each with one.
  const expected = p.route === 'Receipts' ? 3 : 1;
  assert(right && fabs.length === expected,
    `3a. ${p.route}: ${expected} root-stack FeedbackFAB mount(s), activeScreen="${p.route}" aboveTabBar={false}`,
    JSON.stringify(fabs));
  const safes = src.match(/<SafeAreaView\b[^>]*>/g) || [];
  const outer = safes.filter((s) => !/sheetContent/.test(s));
  assert(outer.length > 0 && outer.every((s) => /edges=\{\['bottom'\]\}/.test(s)),
    `3b. ${p.route}: the screen pads only the bottom inset (TopBar owns the top)`, JSON.stringify(outer));
}

// ── 4. League switch ─────────────────────────────────────────────────────
const st = strip(read('src/screens/StandingsScreen.tsx'));
assert(/const leagueId = useSession\(\(s\) => s\.league\?\.league_id\) \|\| null;/.test(st)
  && /queryKey: \['league-rosters', leagueId\]/.test(st)
  && /queryKey: \['league-users', leagueId\]/.test(st)
  && /queryKey: \['league-projection-batch', userId, leagueId\]/.test(st),
  '4a. Standings: every query is keyed by the session league');
assert(/useSession\(\(s\) => s\.leagues\.find\(\(l\) => l\.league_id === leagueId\)\?\.platform\)/.test(st),
  "4b. Standings: the platform (and so the ESPN/MFL unavailable card) follows the switched league");
assert(/const openRosterId = open && open\.leagueId === leagueId \? open\.rosterId : null;/.test(st),
  "4b2. Standings: the open team is remembered with its league, so a switch closes it (a roster id repeats across leagues)");

const rc = strip(read('src/screens/ReceiptsScreen.tsx'));
assert(/const leagueId = useSession\(\(s\) => s\.league\?\.league_id\);/.test(rc)
  && /queryKey: \['receipts', leagueId\]/.test(rc)
  && /queryFn: \(\) => getLeagueReceipts\(leagueId as string\)/.test(rc),
  '4c. Receipts: the payload is keyed and fetched by the session league');
assert(/track\('receipts_opened', \{\s*league_id: leagueId,/.test(rc)
  && /track\('receipts_window_changed', \{ league_id: leagueId,/.test(rc),
  '4d. Receipts: both events carry the current league_id');

const wn = strip(read('src/screens/WinNowScreen.tsx'));
assert(/const leagueId = useSession\(state => state\.league\?\.league_id\);/.test(wn)
  && /return <WinNowContent key=\{`\$\{userId\}:\$\{leagueId\}`\} leagueId=\{leagueId\} \/>;/.test(wn),
  '4e. Win Now: the content remounts per league, dropping results, editor, protected assets and in-flight work');

assert(/const focusId = leagueId && leagueId !== NO_LEAGUE_ID \? leagueId : undefined;/.test(ut)
  && /queryKey: \['usage-trends', focusId,/.test(ut),
  '4f. Usage Trends: the list is keyed by the session league');
assert(/placeholderData: \(prev, prevQuery\) => \(prevQuery\?\.queryKey\[1\] === focusId \? prev : undefined\)/.test(ut)
  && !/keepPreviousData/.test(ut),
  "4g. Usage Trends: the previous list is a placeholder within one league only — never the old league's players after a switch");
assert(/useEffect\(\(\) => \{\s*setExpanded\(null\);\s*setClaim\(\(c\) => \(c && c\.leagueId !== focusId \? null : c\)\);\s*if \(!sheetDismissal\.current\) setSheetPlayer\(null\);\s*\}, \[focusId\]\);/.test(ut),
  '4h. Usage Trends: a switch drops the expanded row, the availability sheet and a claim from another league (a claim for the new league stays)');
assert(/<FlatList\s+key=\{focusId\}\s+testID="usage-trends\.list"/.test(ut),
  '4i. Usage Trends: the list is keyed by league, so a switch starts at the top');
assert(/track\('usage_trends_view_changed', \{\s*league_id: focusId,/.test(ut),
  '4j. Usage Trends: view events carry the current league_id');

// ── 5. Redundant league-name line removed from Usage Trends ──────────────
assert(!/subLeague/.test(ut) && /testID="usage-trends\.weeks-label"/.test(ut),
  "5a. Usage Trends: no league-name line under the header; the weeks label stays");

if (failures) {
  console.error(`\ncheck-league-header-pages: ${failures} failure(s)`);
  process.exit(1);
}
console.log('\ncheck-league-header-pages: all checks passed');
