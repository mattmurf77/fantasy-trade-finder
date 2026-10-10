#!/usr/bin/env node
// Home hub (flag `nav.home_hub`, Direction D) — the M-Home half.
// Spec: docs/plans/home-engagement/scope.md §6.3 "M-Home guard must pin".
//
// WHY THIS EXISTS. Under D-056 there is no simulator, and the hub's riskiest
// properties are claims about code SHAPE that regress silently:
//   * the flag fork must leave the flag-off Home byte-identical (the kill
//     switch is only a kill switch if "off" is today's screen);
//   * Home's Buyer/Seller band must be the band League rankings draws, which
//     holds only while Home does NO split arithmetic of its own (the shared
//     utils/positionSplit is parity-guarded against LeagueSummaryScreen);
//   * `home_tile_tapped` is default-deny at ingest: a tile value outside the
//     closed vocabulary, or a prop on the wrong tile, is silently dropped;
//   * the roster/user queries ride session init's seed only while they keep
//     the 5-minute staleTime (check-session-seed.js S-2's rule, for Home).
//
// Sections 1–12 are the twelve items of §6.3, in order.
//
// Dependency-free: text assertions over comment-stripped source.
// Run: node tests/check-home-hub.js
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const MOBILE = path.join(__dirname, '..');
const SRC = path.join(MOBILE, 'src');
const HOME_DIR = path.join(SRC, 'components', 'home');

let failures = 0;
const assert = (cond, name, why) => {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`);
  }
};

const read = (rel) => fs.readFileSync(path.join(SRC, rel), 'utf8');
// Block comments, JSX comments and whole-line `//` comments (as
// check-home-tab.js). Trailing `//` comments are left alone.
const stripComments = (s) =>
  s
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const count = (hay, needle) => hay.split(needle).length - 1;

const walk = (dir, out = []) => {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(ent.name)) out.push(p);
  }
  return out;
};

const homeFiles = fs.existsSync(HOME_DIR) ? walk(HOME_DIR) : [];
const homeSrc = homeFiles.map((p) => ({
  rel: path.relative(SRC, p),
  code: stripComments(fs.readFileSync(p, 'utf8')),
}));
const homeAll = homeSrc.map((f) => f.code).join('\n');
const hub = stripComments(read('components/home/HomeHub.tsx'));
const tile = stripComments(read('components/home/PositionTile.tsx'));
const screenRaw = read('screens/HomeScreen.tsx');
const screen = stripComments(screenRaw);

// The body of `const <name> = (…) => { … };` — handlers are flat, so the
// first `\n  };` after the arrow closes it.
const handler = (name) => {
  const at = hub.indexOf(`const ${name} = (`);
  if (at < 0) return '';
  const end = hub.indexOf('\n  };', at);
  return end < 0 ? '' : hub.slice(at, end);
};

// ═══════════════════════════════════════════════════════════════════════
// 1 — the flag is read once (useRef), never via useFlag.
// ═══════════════════════════════════════════════════════════════════════
{
  const decl = "const hubOn = useRef(!!useFeatureFlags.getState().flags['nav.home_hub']).current;";
  const fork = 'if (hubOn) return <HomeHub />;';
  assert(count(screen, decl) === 1,
    '1a. HomeScreen reads nav.home_hub imperatively, once per mount, into a useRef',
    `expected exactly: ${decl}`);
  assert(count(screen, fork) === 1 && screen.indexOf(decl) < screen.indexOf(fork),
    '1b. …and forks on it before today\'s JSX');
  assert((screen.match(/useRef\(/g) || []).length === 1 && !/\bhubOn\s*=[^=]/.test(screen.replace(decl, '')),
    '1c. the decision has one source and nothing reassigns it');
  const offenders = walk(SRC).filter((p) =>
    /use(Flag|OnboardingFeature)\(\s*['"]nav\.home_hub['"]/.test(fs.readFileSync(p, 'utf8')));
  assert(offenders.length === 0,
    '1d. nav.home_hub is never read through useFlag / useOnboardingFeature',
    `reactive read in: ${offenders.map((p) => path.relative(SRC, p)).join(', ')} — a flag revalidation would swap Home under the user`);
}

// ═══════════════════════════════════════════════════════════════════════
// 2 — the flag-off body is byte-identical; check-home-tab.js still passes.
// ═══════════════════════════════════════════════════════════════════════
{
  const OPTIONS = [
    'const OPTIONS = [',
    "  { label: 'Rank', tab: 'Rank', testID: 'home.option.rank' },",
    "  { label: 'Find a Trade', tab: 'Trades', testID: 'home.option.trades' },",
    "  { label: 'See Matches', tab: 'Matches', testID: 'home.option.matches' },",
    "  { label: 'View my Leagues', tab: 'League', testID: 'home.option.league' },",
    '] as const;',
  ].join('\n');
  assert(screenRaw.includes(OPTIONS), '2a. the OPTIONS table is byte-identical');
  const BODY = [
    '  if (hubOn) return <HomeHub />;',
    '  return (',
    "    // No `top` safe-area edge: TabNav's TopBar owns the top inset.",
    '    <View style={styles.root} testID="home.screen">',
    '      <Text variant="heading" style={styles.heading}>',
    '        What would you like to do today?',
    '      </Text>',
    '      {OPTIONS.map((o) => (',
    '        <Pressable',
    '          key={o.tab}',
    '          testID={o.testID}',
    '          accessibilityRole="button"',
    '          accessibilityLabel={o.label}',
    '          onPress={() => navigation.navigate(o.tab)}',
    '          style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}',
    '        >',
    '          <Text variant="title">{o.label}</Text>',
    '        </Pressable>',
    '      ))}',
    '    </View>',
    '  );',
    '}',
  ].join('\n');
  assert(screenRaw.includes(BODY), "2b. today's heading + rows JSX follows the fork byte-identical");
  const STYLES = [
    'const styles = StyleSheet.create({',
    '  root: { flex: 1, backgroundColor: ink.ink0, paddingHorizontal: space.lg },',
    '  // Sentence case on purpose: the heading token uppercases, and this line is',
    '  // a question put to the user, not a section label.',
    "  heading: { ...type.heading, textTransform: 'none', marginTop: space.xl, marginBottom: space.md },",
    '  row: {',
    '    minHeight: 56,',
    "    justifyContent: 'center',",
    '    borderBottomWidth: StyleSheet.hairlineWidth,',
    '    borderBottomColor: ink.line,',
    '  },',
    '  rowPressed: { backgroundColor: ink.ink3 },',
    '});',
  ].join('\n');
  assert(screenRaw.includes(STYLES), "2c. today's styles are byte-identical");
  const run = spawnSync(process.execPath, [path.join(__dirname, 'check-home-tab.js')], { encoding: 'utf8' });
  assert(run.status === 0, '2d. check-home-tab.js (the flag-off regression net) passes unmodified',
    (run.stderr || run.stdout || '').trim().split('\n').filter((l) => /FAIL/.test(l)).join('\n      '));
}

// ═══════════════════════════════════════════════════════════════════════
// 3 — components/home uses positionSplit / standings and does no band,
//     median or ordering arithmetic of its own.
// ═══════════════════════════════════════════════════════════════════════
{
  assert(/from '\.\.\/\.\.\/utils\/positionSplit';/.test(hub) && /from '\.\.\/\.\.\/utils\/standings';/.test(hub),
    '3a. HomeHub imports utils/positionSplit and utils/standings');
  // The ice side is emphasizedSides' pick (≤2 tiles, for the ≤3 ice ration),
  // handed to each tile as `emphasis`; the tile never derives it itself.
  assert(['canSplit(', 'positionSplits(', 'emphasizedSides(', 'currentStandings(', 'standingsSummary(', 'ordinal('].every((f) => hub.includes(f))
    && ['rankPercentile(', 'ordinal('].every((f) => tile.includes(f))
    && !tile.includes('suggestedSide('),
    '3b. the split, band, meter, ordinal and standings all come from the foundation utils');
  const banned = [
    ['0.33', /0\.33/],
    ['medians[ / medians?.[', /medians\s*(\?\.)?\[/],
    ['.sort(', /\.sort\(/],
    ['>= median', />=\s*median/],
  ];
  for (const [label, re] of banned) {
    const hits = homeSrc.filter((f) => re.test(f.code)).map((f) => f.rel);
    assert(hits.length === 0, `3c. no \`${label}\` under components/home`,
      `found in ${hits.join(', ')} — Home's band must be League rankings' band (parity-guarded util), never a re-derivation`);
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 4 — the position tiles render only with league.pos_candidates on AND canSplit.
// ═══════════════════════════════════════════════════════════════════════
{
  assert(count(hub, "const posCandidatesOn = useFlag('league.pos_candidates');") === 1,
    '4a. HomeHub reads league.pos_candidates');
  assert(count(hub, 'const splits = rankings && canSplit(rankings) ? positionSplits(rankings) : null;') === 1
    && count(homeAll, 'positionSplits(') === 1,
    '4b. the splits exist only when canSplit holds (the one positionSplits call)');
  const open = hub.indexOf('{posCandidatesOn && positions ? (');
  const close = open >= 0 ? hub.indexOf(') : null}', open) : -1;
  const at = hub.indexOf('{positions}');
  assert(open >= 0 && count(hub, '{positions}') === 1 && at > open && at < close,
    '4c. the positions section mounts only under posCandidatesOn');
  const tiles = hub.match(/<PositionTile\b[\s\S]*?\/>/g) || [];
  const loading = tiles.filter((t) => /split=\{null\}/.test(t));
  const real = tiles.filter((t) => /split=\{s\}/.test(t));
  assert(tiles.length === 2 && loading.length === 1 && real.length === 1
    && /splits\.map\(\(s\) => \(\s*<PositionTile/.test(hub)
    && /SPLIT_POSITIONS\.map\(\(p\) => <PositionTile key=\{p\} pos=\{p\} split=\{null\} \/>\)/.test(hub),
    '4d. a tile gets real data only from `splits` (else it is the split={null} skeleton)');
  const importers = walk(SRC).filter((p) => !p.startsWith(HOME_DIR)
    && /from '[./]*components\/home\/PositionTile'/.test(fs.readFileSync(p, 'utf8')));
  assert(importers.length === 0, '4e. PositionTile is mounted nowhere outside the hub');
}

// ═══════════════════════════════════════════════════════════════════════
// 5 — Buy / Sell write the split intent and open League rankings.
// ═══════════════════════════════════════════════════════════════════════
{
  const NAV = "navigation.navigate('League', { screen: 'LeagueRankings' });";
  for (const [name, side] of [['onBuy', 'buy'], ['onSell', 'sell'], ['onRanking', 'buy']]) {
    const body = handler(name);
    const req = `requestLeagueSummarySplit(leagueId!, s.position, '${side}');`;
    assert(body.includes(req) && body.includes(NAV) && body.indexOf(req) < body.indexOf(NAV),
      `5a. ${name} → requestLeagueSummarySplit(…, '${side}') → navigate League › LeagueRankings`);
  }
  assert(/onBuy=\{\(\) => onBuy\(s\)\}/.test(hub) && /onSell=\{\(\) => onSell\(s\)\}/.test(hub)
    && /onRanking=\{\(\) => onRanking\(s\)\}/.test(hub),
    '5b. the hub hands each real tile its own split\'s handlers');
  const side = (id) => (tile.match(new RegExp(`<SideButton[^>]*?testID=\\{ids\\.${id}\\}[\\s\\S]*?\\/>`)) || [''])[0];
  assert(/onPress=\{onBuy\}/.test(side('buy')) && /onPress=\{onSell\}/.test(side('sell'))
    && /onPress=\{onRanking\}/.test(side('ranking')),
    '5c. PositionTile wires Buy → onBuy, Sell → onSell, See P ranking → onRanking');
  assert(/disabled=\{split == null\}/.test(side('buy')) && /disabled=\{split == null\}/.test(side('sell')),
    '5d. Buy / Sell are disabled until the bands exist');
  const rank = handler('onOverallRank');
  assert(rank.includes('requestLeagueSummaryAll(leagueId!);') && rank.includes(NAV),
    "5e. Overall rank → requestLeagueSummaryAll → League rankings (scope §6.2)");
}

// ═══════════════════════════════════════════════════════════════════════
// 6 — exactly one `track('home_tile_tapped'` per tile kind, closed
//     vocabulary, position/band only on buy/sell/position_ranking.
// ═══════════════════════════════════════════════════════════════════════
{
  const VOCAB = ['outlook', 'standings', 'overall_rank', 'buy', 'sell', 'position_ranking',
    'find_trade', 'rank', 'matches', 'trends', 'usage_rates', 'free_agents', 'link_league', 'retry'];
  const WITH_POS = new Set(['buy', 'sell', 'position_ranking']);
  const re = /track\('home_tile_tapped', \{ ([^}]*) \}, 'Home'\);/g;
  const calls = [];
  for (const f of homeSrc) {
    let m;
    while ((m = re.exec(f.code))) calls.push({ rel: f.rel, props: m[1], index: m.index, code: f.code });
  }
  assert(calls.length === count(homeAll, "track('home_tile_tapped'"),
    "6a. every home_tile_tapped call has the `{ … }, 'Home'` shape");
  const tiles = calls.map((c) => (/^tile: '([a-z_]+)'/.exec(c.props) || [])[1]);
  const seen = {};
  for (const t of tiles) seen[t] = (seen[t] || 0) + 1;
  const missing = VOCAB.filter((v) => seen[v] !== 1);
  const extra = Object.keys(seen).filter((t) => !VOCAB.includes(t));
  assert(missing.length === 0 && extra.length === 0 && calls.length === VOCAB.length,
    '6b. exactly one call site per tile kind, and only the closed vocabulary',
    `not exactly once: ${missing.join(', ') || '—'}; outside the vocabulary: ${extra.join(', ') || '—'}`);
  const badProps = calls.filter((c, i) => {
    const keys = c.props.split(',').map((p) => p.trim().split(':')[0]);
    return WITH_POS.has(tiles[i])
      ? keys.join(',') !== 'tile,position,band' || !/position: s\.position, band: bandProp\(s\)$/.test(c.props)
      : keys.join(',') !== 'tile';
  });
  assert(badProps.length === 0, '6c. position + band ride on buy / sell / position_ranking only',
    badProps.map((c) => `{ ${c.props} }`).join('; '));
  const navBefore = calls.filter((c) => {
    const start = c.code.lastIndexOf('=> {', c.index);
    const lead = start >= 0 ? c.code.slice(start, c.index) : '';
    return /navigate\(|requestLeagueSummary|refetch\(/.test(lead);
  });
  assert(navBefore.length === 0, '6d. each tap is tracked BEFORE it navigates (or refetches)');
  assert(!/\btrack\('(?!home_tile_tapped')/.test(homeAll),
    '6e. the hub emits no other client event (screen_viewed / tab_selected stay where they are)');
  assert(/function bandProp\(s: PositionSplit\): 'seller' \| 'buyer' \| 'mid'/.test(hub),
    '6f. `band` is typed to the closed seller | buyer | mid set');
}

// ═══════════════════════════════════════════════════════════════════════
// 7 — the Standings row is CURRENT standings only.
// ═══════════════════════════════════════════════════════════════════════
{
  const hits = homeSrc.filter((f) => /getOutlook|league-outlook/.test(f.code)).map((f) => f.rel);
  assert(hits.length === 0, '7. no getOutlook / league-outlook anywhere under components/home',
    `found in ${hits.join(', ')} — projections live on the Standings page, behind its Projected tab (R4)`);
}

// ═══════════════════════════════════════════════════════════════════════
// 8 — the roster/user queries keep the seed alive and are Sleeper-gated.
// ═══════════════════════════════════════════════════════════════════════
{
  assert(count(hub, "useSession((s) => s.leagues.find((l) => l.league_id === leagueId)?.platform) ?? 'sleeper';") === 1
    && count(hub, "const isSleeper = platform === 'sleeper';") === 1,
    "8a. isSleeper is LeagueSummary's rule (unknown resolves to Sleeper)");
  for (const [key, fetcher] of [['league-rosters', 'getLeagueRosters'], ['league-users', 'getLeagueUsers']]) {
    const block = (new RegExp(`queryKey: \\['${key}', leagueId\\][\\s\\S]{0,300}?\\n  \\}\\);`).exec(hub) || [''])[0];
    assert(/staleTime:\s*5\s*\*\s*60_000/.test(block)
      && block.includes(`queryFn: () => ${fetcher}(leagueId!),`)
      && /enabled: hasLeague && isSleeper,/.test(block),
      `8b. ['${key}'] — bare ${fetcher}, staleTime 5 * 60_000, enabled only for Sleeper`,
      block ? block.replace(/\s+/g, ' ') : 'query options block not found');
  }
  const pr = (/queryKey: \['league-power-rankings', leagueId, 'consensus'\][\s\S]{0,300}?\n  \}\);/.exec(hub) || [''])[0];
  assert(pr.includes("queryFn: () => getPowerRankings(leagueId!, 'consensus'),")
    && /staleTime: 60_000,/.test(pr) && /placeholderData: \(prev\) => prev,/.test(pr),
    "8c. the tiles + Overall rank share League rankings' consensus key and options (§6.2)");
}

// ═══════════════════════════════════════════════════════════════════════
// 9 — no FeedbackFAB: Home is a tab screen, covered by RootNav's mount.
// ═══════════════════════════════════════════════════════════════════════
{
  const hits = homeSrc.filter((f) => /FeedbackFAB/.test(f.code)).map((f) => f.rel);
  assert(hits.length === 0 && !/FeedbackFAB/.test(screen),
    '9. no FeedbackFAB under components/home or in HomeScreen',
    `found in ${hits.join(', ') || 'HomeScreen.tsx'} — a second FAB on a tab screen is the #196/#197 bug`);
}

// ═══════════════════════════════════════════════════════════════════════
// 10 — tokens only: no hex or rgba literals.
// ═══════════════════════════════════════════════════════════════════════
{
  const hits = homeSrc.filter((f) => /#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(f.code)).map((f) => f.rel);
  assert(hits.length === 0, '10. no hex / rgba( literals under components/home',
    `found in ${hits.join(', ')} — colours come from theme/chalkline.ts, position hexes from theme/colors.ts`);
}

// ═══════════════════════════════════════════════════════════════════════
// 11 — every specced testID is present, as a static literal.
// ═══════════════════════════════════════════════════════════════════════
{
  const IDS = ['home.hub', 'home.status.outlook', 'home.status.standings', 'home.status.rank'];
  for (const p of ['qb', 'rb', 'wr', 'te']) {
    IDS.push(`home.position.${p}`, `home.position.${p}.buy`, `home.position.${p}.sell`, `home.position.${p}.ranking`);
  }
  IDS.push('home.tile.find-trade', 'home.tile.rank', 'home.tile.matches', 'home.tile.trends',
    'home.tile.usage-rates', 'home.tile.free-agents', 'home.positions.error', 'home.positions.retry',
    'home.link-league');
  // Usage Rates (docs/plans/usage-trends/): its own tile, gated on its own
  // flag, pushing the root-stack UsageTrends screen — never the Rank-stack
  // Trends screen "Check trends" opens.
  {
    const t = (/<TaskTile\s+testID="home\.tile\.usage-rates"[\s\S]*?\/>/.exec(hub) || [''])[0];
    assert(/const usageOn = useFlag\('usage_trends\.enabled'\);/.test(hub)
      && /\{usageOn \? \(\s*<TaskTile\s+testID="home\.tile\.usage-rates"/.test(hub)
      && /title="Usage Rates"/.test(t) && /navigation\.navigate\('UsageTrends'\);/.test(t),
      '11c. the Usage Rates tile shows only with usage_trends.enabled and opens UsageTrends');
  }
  const missing = IDS.filter((id) => !new RegExp(`(["'])${esc(id)}\\1`).test(homeAll));
  assert(missing.length === 0, `11a. all ${IDS.length} specced testIDs are present as literals`,
    `missing: ${missing.join(', ')}`);
  assert(!/testID=\{`/.test(homeAll) && !/(["'`])home\.[a-z.-]*\$\{/.test(homeAll),
    '11b. no template-literal testIDs (testid-lint cannot see them)');
}

// ═══════════════════════════════════════════════════════════════════════
// 12 — Team outlook opens the Trade DNA sheet via the existing param.
// ═══════════════════════════════════════════════════════════════════════
{
  const body = handler('onOutlook');
  assert(body.includes("navigation.navigate('Trades', { screen: 'TradesHome', params: { mode: 'guided', editDna: true } });"),
    "12a. onOutlook navigates to TradesHome with { mode: 'guided', editDna: true }");
  const row = (/<StatusRow\s+testID="home\.status\.outlook"[\s\S]*?\/>/.exec(hub) || [''])[0];
  assert(/onPress=\{onOutlook\}/.test(row), '12b. the Team outlook row presses onOutlook');
}

{
  const pkg = JSON.parse(fs.readFileSync(path.join(MOBILE, 'package.json'), 'utf8'));
  assert(pkg.scripts['test:home-hub'] === 'node tests/check-home-hub.js',
    'npm run test:home-hub runs this suite');
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nhome-hub: all checks passed');
