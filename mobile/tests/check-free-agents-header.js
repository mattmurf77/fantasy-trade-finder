#!/usr/bin/env node
// Free Agents header (docs/plans/free-agents-header-rank/scope.md).
//
// WHY THIS EXISTS. Operator, 2026-11-12: "The free agents page breaks the
// behavior of other pages where the league selector stays as a header." The
// page was a root-stack push with a plain native header, so it had no league
// selector. D-056 retired the simulator, so the shape of the fix is pinned
// here instead:
//   1. RootNav renders FreeAgents' header as LeagueTopBarHeader: the global
//      TopBar (league cluster + LeagueSwitcherSheet) over a sub-header that
//      keeps the #151 JS back control (free-agents.back-btn) — no native
//      back button, which is dead on iOS 26 (RNS#3294).
//   2. The selector is REUSED: TopBar's own cluster and sheet, never a second
//      selector in the screen.
//   3. The screen keeps its one FeedbackFAB and lets TopBar own the top inset.
//   4. A league switch refetches the list (league id in the query key) and
//      drops an open claim so a row is never claimed in another league.
//
// Run: node tests/check-free-agents-header.js
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
const topBar = strip(read('src/components/TopBar.tsx'));
const fa = strip(read('src/screens/FreeAgentsScreen.tsx'));

// ── 1. RootNav: the FreeAgents registration ──────────────────────────────
const faRegStart = rootNav.indexOf('name="FreeAgents"');
const faRegEnd = rootNav.indexOf('<Stack.Screen', faRegStart);
const faReg = faRegStart >= 0 ? rootNav.slice(faRegStart, faRegEnd < 0 ? undefined : faRegEnd) : '';
assert(faReg.length > 0, '1a. RootNav registers the FreeAgents route');
assert(/component=\{FreeAgentsScreen\}/.test(faReg), '1b. FreeAgents renders FreeAgentsScreen');
assert(/header:\s*\(\)\s*=>\s*\(\s*<LeagueTopBarHeader\b/.test(faReg),
  '1c. FreeAgents header is LeagueTopBarHeader (custom header: the league selector stays as the header)',
  'expected `header: () => (<LeagueTopBarHeader ...` inside the FreeAgents options');
assert(/<HeaderBack\s+testID="free-agents\.back-btn"/.test(faReg),
  '1d. the FreeAgents header carries the JS back control free-agents.back-btn');
assert(/navigation\.canGoBack\(\)\s*\?\s*navigation\.goBack\(\)\s*:\s*navigation\.navigate\('Main'\)/.test(faReg),
  '1e. back = canGoBack ? goBack : navigate(Main) (cold-start deep link still has a way out)');
assert(!/headerLeft\s*:/.test(faReg) && !/headerBackVisible\s*:\s*true/.test(faReg),
  '1f. no native headerLeft / native back button on FreeAgents (RNS#3294)');

// ── 2. LeagueTopBarHeader = the global TopBar + sub-header ───────────────
const hdrStart = rootNav.indexOf('function LeagueTopBarHeader(');
const hdrEnd = rootNav.indexOf('\n}\n', hdrStart);
const hdr = hdrStart >= 0 ? rootNav.slice(hdrStart, hdrEnd) : '';
assert(hdr.length > 0, '2a. RootNav defines LeagueTopBarHeader');
assert(/import TopBar from '\.\.\/components\/TopBar';/.test(rootNav),
  '2b. RootNav imports the shared TopBar');
assert(/return\s*\(\s*<View[^>]*>\s*<TopBar \/>/.test(hdr),
  '2c. LeagueTopBarHeader renders <TopBar /> first and unconditionally');
assert(/\{back\}/.test(hdr) && /<HeaderTitle>\{title\}<\/HeaderTitle>/.test(hdr),
  '2d. LeagueTopBarHeader renders the back control and the page title below TopBar');
assert(/pointerEvents="none"/.test(hdr),
  '2e. the centred title layer never swallows the back control tap');

// ── 3. The selector is TopBar's own, not a second one ────────────────────
assert(/testID="topbar\.league"[\s\S]{0,120}onPress=\{\(\) => setSwitcherOpen\(true\)\}/.test(topBar),
  '3a. TopBar league cluster (topbar.league) opens the switcher');
assert(/<LeagueSwitcherSheet\b[\s\S]{0,80}visible=\{switcherOpen\}/.test(topBar),
  '3b. TopBar mounts LeagueSwitcherSheet bound to its cluster');
assert(!/LeagueSwitcherSheet|<TopBar\b/.test(fa),
  '3c. FreeAgentsScreen builds no second selector and no second TopBar');

// ── 4. FeedbackFAB + safe area ──────────────────────────────────────────
const fabs = fa.match(/<FeedbackFAB\b[^>]*\/>/g) || [];
assert(fabs.length === 1 && /activeScreen="FreeAgents"/.test(fabs[0]) && /aboveTabBar=\{false\}/.test(fabs[0]),
  '4a. FreeAgentsScreen mounts exactly one <FeedbackFAB activeScreen="FreeAgents" aboveTabBar={false} />',
  JSON.stringify(fabs));
assert(/<SafeAreaView style=\{styles\.safe\} edges=\{\['bottom'\]\}>/.test(fa),
  "4b. the screen pads only the bottom inset (TopBar owns the top, no double pad)");

// ── 5. League switch ─────────────────────────────────────────────────────
assert(/const leagueId = useSession\(\(s\) => s\.league\?\.league_id\);/.test(fa),
  '5a. leagueId is the ACTIVE league from the session (what the header switches)');
assert(/queryKey: \['free-agents', leagueId, filter\]/.test(fa)
  && /queryFn: \(\) => getFreeAgents\(leagueId as string, filter\)/.test(fa),
  '5b. the list query is keyed and fetched by leagueId, so a switch refetches for the new league');
assert(/useEffect\(\(\) => \{\s*setClaimTarget\(null\);\s*setClaimMove\(null\);\s*setClaimLeagueId\(null\);\s*\}, \[leagueId\]\);/.test(fa),
  '5c. a league switch drops any open claim (target, capability, league)');
assert(/setClaimLeagueId\(leagueId\);\s*setClaimTarget\(row\);/.test(fa),
  '5d. a claim records the league it was opened in');
assert(/\{claimTarget && leagueId && claimLeagueId === leagueId \? \(\s*<ClaimSheet\b/.test(fa),
  '5e. the ClaimSheet mounts only while the claim league is the active league');
assert(/isClaimPending\(pendingClaims, leagueId, item\.player_id\)/.test(fa),
  '5f. "Claim pending" stays keyed by (league, player)');

// ── 6. The rank is the server's, unrenumbered ───────────────────────────
assert(/posRank=\{`\$\{row\.position\}\$\{row\.pos_rank\}`\}/.test(fa),
  '6a. the row renders the server pos_rank as-is (overall rank at the position)');

if (failures) {
  console.error(`\ncheck-free-agents-header: ${failures} failure(s)`);
  process.exit(1);
}
console.log('\ncheck-free-agents-header: all checks passed');
