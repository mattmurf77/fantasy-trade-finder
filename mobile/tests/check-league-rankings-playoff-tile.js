'use strict';
// League Rankings shows Home's playoff tile (2026-11-12, operator ask): under
// `league.projections` the page mounts the SAME `HomePlayoffBanner` Home does,
// in place of the inline `LeagueProjectionSection`; the full projected
// standings render only on the Standings page (Projected segment).
//   T1  League Rankings mounts the tile, no longer the section; Standings does
//   T2  the mount: keyed by user + league, roster id the way Home finds it,
//       on the shared `['league-rosters', id]` key; the `outlook.odds` strip
//       path (batch projections off) is unchanged
//   T3  the handlers, EXECUTED for both routes: View / percentage → Standings
//       on Projected; Review outlook → the Trade DNA sheet with the
//       suggestion (tab root: Home's navigate; legacy root push: popTo Main)
//   T4  analytics: Home's events and tile values, screen = route.name
//   T5  one component, one query key, one util; Home's mount unchanged;
//       a league switch re-keys the tile; Back from Standings is goBack
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const ROOT = path.join(__dirname, '..', '..');
const read = rel => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const ls = read('mobile/src/screens/LeagueSummaryScreen.tsx');
const standings = read('mobile/src/screens/StandingsScreen.tsx');
const hub = read('mobile/src/components/home/HomeHub.tsx');
const banner = read('mobile/src/components/home/HomePlayoffBanner.tsx');
const rootNav = read('mobile/src/navigation/RootNav.tsx');
const taxonomy = read('backend/analytics_taxonomy.py');
const count = (s, sub) => s.split(sub).length - 1;

// ── T1 ────────────────────────────────────────────────────────────────────
assert(ls.includes("import HomePlayoffBanner from '../components/home/HomePlayoffBanner';"),
  'T1a League Rankings imports Home\'s tile component');
assert.equal(count(ls, '<HomePlayoffBanner'), 1, 'T1b exactly one tile mount on League Rankings');
assert(!ls.includes('LeagueProjectionSection'), 'T1c League Rankings no longer imports or mounts LeagueProjectionSection');
assert(/import LeagueProjectionSection from '\.\.\/components\/LeagueProjectionSection';/.test(standings)
  && /<LeagueProjectionSection key=\{leagueId \?\? ''\} \/>/.test(standings),
  'T1d Standings still mounts the full section');
assert(standings.includes("route.params?.segment === 'projected' ? 'projected' : 'current'"),
  'T1e Standings opens on Projected from the { segment } param');

// ── T2 ────────────────────────────────────────────────────────────────────
const slot = (/\{batchProjections \? \([\s\S]*?\) : oddsEnabled \? \(\s*outlookSupported \? \(\s*<OutlookStripAndSection query=\{outlookQuery\} leagueId=\{leagueId\} \/>\s*\) : \(\s*<OutlookUnsupportedRow \/>\s*\)\s*\) : null\}/.exec(ls) || [''])[0];
assert(slot, 'T2a the slot is `batchProjections ? tile : oddsEnabled ? strip : null`, strip path unchanged');
const mount = (/<HomePlayoffBanner[\s\S]*?\/>/.exec(slot) || [''])[0];
assert(mount.includes('key={`${tileUserId}:${leagueId}`}'), 'T2b keyed by user + league, as on Home');
assert(mount.includes("rosterId={findMyRoster(tileRostersQuery.data, tileUserId ?? '')?.roster_id ?? null}"),
  'T2c roster id via findMyRoster over the league rosters, as on Home');
assert(mount.includes('onDetails={onTileDetails}') && mount.includes('onReviewOutlook={onTileReviewOutlook}'),
  'T2d both callbacks wired');
assert(/const tileRostersQuery = useQuery\(\{\s*queryKey: \['league-rosters', leagueId\],\s*queryFn: \(\) => getLeagueRosters\(leagueId!\),\s*enabled: batchProjections && outlookSupported && !!leagueId,\s*staleTime: 5 \* 60_000,\s*\}\);/.test(ls),
  'T2e rosters on the shared key, Sleeper + flag gated, session-seed staleTime');
assert(ls.includes('const tileUserId = useSession((s) => s.user?.user_id);'), 'T2f the user id comes from the session');
assert(ls.includes('enabled: !batchProjections && oddsEnabled && outlookSupported && !!leagueId,'),
  'T2g the outlook strip query is unchanged');

// ── T3 / T4: execute both handlers for both routes ────────────────────────
function handler(name) {
  const at = ls.indexOf(`const ${name} = (`);
  assert(at >= 0, `${name} exists`);
  return ls.slice(at, ls.indexOf('\n  };', at) + 5);
}
const js = ts.transpileModule(`${handler('onTileDetails')}\n${handler('onTileReviewOutlook')}\nreturn { onTileDetails, onTileReviewOutlook };`,
  { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
const PARAMS = { mode: 'guided', editDna: true, suggestOutlook: 'contender' };
for (const [routeName, isTabRoot] of [['LeagueRankings', true], ['LeagueSummary', false]]) {
  const calls = [];
  const navigation = {
    navigate: (...a) => calls.push(['navigate', ...a]),
    popTo: (...a) => calls.push(['popTo', ...a]),
  };
  const track = (...a) => calls.push(['track', ...a]);
  const h = new Function('track', 'navigation', 'route', 'isTabRoot', js)(track, navigation, { name: routeName }, isTabRoot);
  h.onTileDetails();
  assert.deepEqual(calls, [
    ['track', 'home_tile_tapped', { tile: 'standings' }, routeName],
    ['navigate', 'Standings', { segment: 'projected' }],
  ], `T3a/T4a ${routeName}: track, then Standings on Projected`);
  calls.length = 0;
  h.onTileReviewOutlook('contender');
  assert.deepEqual(calls, [
    ['track', 'home_tile_tapped', { tile: 'outlook' }, routeName],
    isTabRoot
      ? ['navigate', 'Trades', { screen: 'TradesHome', params: PARAMS }]
      : ['popTo', 'Main', { screen: 'Trades', params: { screen: 'TradesHome', params: PARAMS } }],
  ], `T3b/T4b ${routeName}: track, then the Trade DNA sheet with the suggestion`);
}
// Home's own destination is the same selector with the same params.
assert(hub.includes("navigation.navigate('Trades', { screen: 'TradesHome', params: { mode: 'guided', editDna: true, suggestOutlook: recommended } });"),
  'T3c Home\'s Review outlook opens the same selector with the same params');
assert(hub.includes("navigation.navigate('Standings', { segment: 'projected' });"), 'T3d Home\'s View opens the same page');
// T4 — existing event, existing props and tile values; no new name.
assert(/"home_tile_tapped":\s+frozenset\(\{"tile", "position", "band"\}\)/.test(taxonomy)
  && /#   outlook \| standings \| overall_rank/.test(taxonomy),
  'T4c home_tile_tapped already carries `tile` with outlook / standings');
assert.equal(count(ls, "track('home_tile_tapped'"), 2, 'T4d exactly the two tile taps emit on League Rankings');

// ── T5 ────────────────────────────────────────────────────────────────────
assert.equal(count(banner, "queryKey: ['league-projection-batch', userId, leagueId]"), 1, 'T5a the tile holds the one query key');
assert(banner.includes("import { homePlayoffBanner } from '../../utils/homePlayoffBanner';"), 'T5b the tile uses the one util');
assert(hub.includes("import HomePlayoffBanner from './HomePlayoffBanner';"), 'T5c Home imports the same component');
const homeMount = (/<HomePlayoffBanner[\s\S]*?\/>/.exec(hub) || [''])[0];
assert.equal(homeMount, "<HomePlayoffBanner key={`${user?.user_id}:${leagueId}`}\n"
  + "            rosterId={findMyRoster(rostersQuery.data, user?.user_id ?? '')?.roster_id ?? null}\n"
  + '            onDetails={onProjections}\n'
  + '            onReviewOutlook={onReviewOutlook} />', 'T5d Home\'s mount is unchanged');
assert(banner.includes('const leagueId = useSession(s => s.league?.league_id);') && banner.includes('!switching'),
  'T5e the tile reads the active league and hides while switching, so a switch re-queries');
assert(/testID="standings\.back-btn"\s*onPress=\{\(\) =>\s*navigation\.canGoBack\(\)\s*\? navigation\.goBack\(\)/.test(rootNav),
  'T5f Back from Standings pops to the page that pushed it');

const pkg = JSON.parse(read('mobile/package.json'));
assert.equal(pkg.scripts['test:league-rankings-playoff-tile'], 'node tests/check-league-rankings-playoff-tile.js');
console.log('League rankings playoff tile: mount, handlers on both routes, analytics, shared key and Home parity checks passed');
