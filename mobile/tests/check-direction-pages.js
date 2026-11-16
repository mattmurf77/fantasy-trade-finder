#!/usr/bin/env node
// Improve pages, step 1 (flag `league.direction_pages`; spec
// docs/plans/league-projections/direction-pages/spec.md §3, §8, §10; D-265):
// "Improve Playoff Chances" and "Improve Draft Pick".
//
// EXECUTES src/utils/directionPages.ts (with the real maxPfMoves,
// playoffTargets and playoffOdds modules) under plain node: which branch a
// page shows for every input (P-8, P-12), the two-figure summary (P-6), and
// when the link to the other page shows (P-10, spec §5.3).
//
// SOURCE PINS cover what cannot be executed: both routes registered
// unconditionally with the Standings header (P-1, P-2), one FeedbackFAB each
// (P-3), the one forecast query and no new request (P-4), the existing
// bodies and no second list (P-5), the list open on arrival (P-7), the
// links (P-10), deep links (P-11), the Standings link rows with the flag on
// and today's card with it off (P-13), the league switch (P-14), the flag's
// registration, the spec's copy, and that the deferred pieces (the card's
// button row, cell B, the experiment) are not built.
//
// D-270 (the half sheet ships first): the other-page link reads the
// server's `team_direction.options` when the block is on the read (D12-D15);
// the page logs `direction_page_opened` once per focus with its source and
// state, and the bodies log under the page's route name (group N).
// Run: node tests/check-direction-pages.js
'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const ROOT = path.join(MOBILE, '..');
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
const readRoot = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
// Comments stripped so a pin can never be satisfied by prose.
const strip = (s) => s
  .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^\s*\/\/.*$/gm, '');

const transpile = (src) => ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const run = (rel, requireFn) => {
  const m = { exports: {} };
  new Function('module', 'exports', 'require', transpile(read(rel)))(m, m.exports, requireFn);
  return m.exports;
};
const none = (name) => (r) => { throw new Error(`${name} requires ${r}`); };

const copyMod = run('src/utils/directionPagesCopy.ts', none('directionPagesCopy'));
const oddsMod = run('src/utils/playoffOdds.ts', none('playoffOdds'));
const maxPfCopy = run('src/utils/maxPfMovesCopy.ts', none('maxPfMovesCopy'));
const maxPf = run('src/utils/maxPfMoves.ts', (r) => {
  if (r === './maxPfMovesCopy') return maxPfCopy;
  if (r === './playoffOdds') return oddsMod;
  throw new Error(`maxPfMoves.ts requires ${r}`);
});
const targetsCopy = run('src/utils/playoffTargetsCopy.ts', none('playoffTargetsCopy'));
const targets = run('src/utils/playoffTargets.ts', (r) => {
  if (r === './playoffTargetsCopy') return targetsCopy;
  if (r === './playoffOdds') return oddsMod;
  if (r === './maxPfMoves') return maxPf;
  throw new Error(`playoffTargets.ts requires ${r}`);
});
const u = run('src/utils/directionPages.ts', (r) => {
  if (r === './directionPagesCopy') return copyMod;
  if (r === './playoffOdds') return oddsMod;
  if (r === './maxPfMoves') return maxPf;
  if (r === './playoffTargets') return targets;
  throw new Error(`directionPages.ts must not require ${r} at runtime`);
});
const C = copyMod.DIRECTION_COPY;

const utilSrc = read('src/utils/directionPages.ts');
const copySrc = read('src/utils/directionPagesCopy.ts');
const pageSrc = strip(read('src/components/DirectionPage.tsx'));
const pageRaw = read('src/components/DirectionPage.tsx');
const maxPfBodySrc = read('src/components/MaxPfMovesSection.tsx');
const targetsBodySrc = read('src/components/PlayoffTargetsSection.tsx');
const detailSrc = strip(read('src/components/LeagueProjectionDetail.tsx'));
const standingsSrc = strip(read('src/screens/StandingsScreen.tsx'));
const rootNav = strip(read('src/navigation/RootNav.tsx'));
const linksSrc = strip(read('src/utils/deepLinks.ts'));
const spec = readRoot('docs/plans/league-projections/direction-pages/spec.md');

// ── Fixtures: minimal blocks in each feature's served shape ─────────────
const clone = (o) => JSON.parse(JSON.stringify(o));
const MAXPF = {
  version: 1, state: 'ready', reason: null, viewer_roster_id: 7, captured_at: '2026-11-10T12:00:00Z',
  draft_season: 2027, draft_round: 1, draft_order: { rule: 'maxpf_lowest_first', set_at: null },
  saved_outlook: null, pick_owner: { owns_own_pick: true, owner_roster_id: 7, owner_name: 'Mine' },
  baseline: {
    weeks_remaining: 4, first_week: 11, last_week: 14, weeks_excluded_played: 0, playoff_probability: 0.3112,
    playoff_band: 'rebuilder', pick_if_miss: 4.1, top3_probability: 0.2, label: '1.04', label_slot: 4,
    pick_value: null, pick_value_status: 'not_priced',
  },
  roster_player_ids: [], rows: [], candidates_total: 0, combined: [],
};
const TARGETS = {
  version: 1, state: 'ready', reason: null, viewer_roster_id: 7, captured_at: '2026-11-10T12:00:00Z',
  saved_outlook: null,
  baseline: {
    weeks_remaining: 4, first_week: 11, last_week: 14, weeks_excluded_played: 0, playoff_probability: 0.624,
    playoff_band: 'contender', playoff_clinched: false, playoff_eliminated: false,
  },
  eligible_teams: 5, sellers_changed: false, candidates_total: 8, rows: [],
};
const view = (patch = {}) => Object.assign({ state: 'current', max_pf_moves: clone(MAXPF), playoff_targets: clone(TARGETS) }, patch);
const BASE = { leagueId: 'L1', userId: 'u1', isSleeper: true, projectionsOn: true, featureOn: true, isError: false };

// ═══ A. Copy: the spec's strings ══════════════════════════════════════════
{
  const fromSpec = ['Improve Playoff Chances', 'Improve Draft Pick', 'View projected standings',
    'Improve Draft Pick instead', 'Improve Playoff Chances instead', 'Playoff chance', 'Projected pick'];
  const missingInSpec = fromSpec.filter((s) => !spec.includes(`"${s}"`));
  assert(missingInSpec.length === 0, 'A1. every string pinned here is quoted in the spec', missingInSpec.join(' | '));
  assert(C['TITLE.playoffs'] === 'Improve Playoff Chances' && C['TITLE.draft_pick'] === 'Improve Draft Pick',
    'A2. P-2 titles, verbatim (decision #8 capitalisation)');
  assert(C['SUM.playoff'] === 'Playoff chance' && C['SUM.pick'] === 'Projected pick', 'A3. P-6 summary labels');
  assert(C['LINK.standings'] === 'View projected standings' && C['LINK.other.draft_pick'] === 'Improve Draft Pick instead'
      && C['LINK.other.playoffs'] === 'Improve Playoff Chances instead', 'A4. P-10 link labels');
  assert(!/^\s*import\s/m.test(copySrc), 'A5. the copy module has zero imports');
  assert(!/'[A-Z][a-z]+ [a-z]+[^']*'/.test(pageSrc.replace(/testID=[^ >]+/g, '')) && /DIRECTION_COPY as C/.test(pageSrc),
    'A6. the page renders copy from the module, not inline literals');
  const titlesInNav = ['Improve Playoff Chances', 'Improve Draft Pick'].every((t) =>
    (rootNav.match(new RegExp(`title(: '|=")${t}['"]`, 'g')) || []).length === 2);
  assert(titlesInNav, 'A7. RootNav uses the same two titles for the route and its header');
  assert(maxPfCopy.MAXPF_COPY['C-TITLE'] === 'Max PF moves' && targetsCopy.TARGETS_COPY['C-TITLE'] === 'Playoff targets',
    'A8. P-13 link row labels are the sections\' own titles ("Max PF moves", "Playoff targets")');
}

// ═══ B. Which branch a page shows (P-8, P-12) ════════════════════════════
{
  for (const page of ['draft_pick', 'playoffs']) {
    const v = (patch) => u.pageView(Object.assign({ page, data: view() }, BASE, patch)).kind;
    assert(v({ leagueId: null }) === 'no_league', `B1. ${page}: no league → no_league`);
    assert(v({ isSleeper: false }) === 'unavailable' && v({ projectionsOn: false }) === 'unavailable'
        && v({ featureOn: false }) === 'unavailable' && v({ userId: null }) === 'unavailable',
      `B2. ${page}: non-Sleeper, league.projections off, the feature flag off, or no user → the unavailable card`);
    assert(v({ data: undefined }) === 'loading' && v({ data: undefined, isError: true }) === 'error',
      `B3. ${page}: no read yet → loading; a failed read → error (with Try again)`);
    assert(v({ data: view(), isError: true }) === page, `B4. ${page}: a refetch error keeps the data on screen`);
    const key = page === 'draft_pick' ? 'max_pf_moves' : 'playoff_targets';
    assert(v({ data: view({ [key]: undefined }) }) === 'unavailable',
      `B5. ${page}: no block (server flag off, older server) → the unavailable card, never blank`);
    const base = page === 'draft_pick' ? MAXPF : TARGETS;
    assert(v({ data: view({ [key]: Object.assign(clone(base), { version: 2 }) }) }) === 'unavailable'
        && v({ data: view({ [key]: Object.assign(clone(base), { state: 'brand_new' }) }) }) === 'unavailable',
      `B6. ${page}: an unknown version or state → the unavailable card`);
    const states = page === 'draft_pick'
      ? ['unavailable', 'season_over', 'after_trade_deadline', 'draft_order_not_maxpf', 'no_miss', 'no_moves', 'ready']
      : ['unavailable', 'season_over', 'after_trade_deadline', 'clinched', 'eliminated', 'near_certain', 'no_sellers', 'no_targets', 'ready'];
    const blank = states.filter((s) => v({ data: view({ [key]: Object.assign(clone(base), { state: s }) }) }) !== page);
    assert(blank.length === 0, `B7. ${page}: every server state renders through the body (its existing line)`, blank.join(','));
  }
  // Every known non-list state has a line from the body's own model, so no state is blank.
  const maxLines = ['unavailable', 'season_over', 'after_trade_deadline', 'draft_order_not_maxpf', 'no_miss']
    .filter((s) => !maxPf.deriveSection(Object.assign(clone(MAXPF), { state: s }), null).line);
  const tgtLines = ['unavailable', 'season_over', 'after_trade_deadline', 'clinched', 'eliminated', 'near_certain', 'no_sellers']
    .filter((s) => !targets.deriveSection(Object.assign(clone(TARGETS), { state: s }), null).line);
  assert(maxLines.length === 0 && tgtLines.length === 0, 'B8. every non-list state has its one-line message from the body\'s model',
    `${maxLines.join(',')} ${tgtLines.join(',')}`);
}

// ═══ C. The two-figure summary (P-6) ═════════════════════════════════════
{
  assert(eq(u.summary('draft_pick', view()), { playoff: '31%', pick: '1.04' }),
    'C1. draft-pick page: playoff chance from max_pf_moves.baseline, projected pick = its D-257 label', JSON.stringify(u.summary('draft_pick', view())));
  assert(eq(u.summary('playoffs', view()), { playoff: '62%', pick: '1.04' }),
    'C2. playoff page: playoff chance from playoff_targets.baseline (the list\'s own block)', JSON.stringify(u.summary('playoffs', view())));
  const high = view({ playoff_targets: Object.assign(clone(TARGETS), { baseline: Object.assign(clone(TARGETS.baseline), { playoff_probability: 0.9991 }) }) });
  const proven = view({ playoff_targets: Object.assign(clone(TARGETS), { baseline: Object.assign(clone(TARGETS.baseline), { playoff_probability: 1, playoff_clinched: true }) }) });
  assert(u.summary('playoffs', high).playoff === '>99%' && u.summary('playoffs', proven).playoff === '100%',
    'C3. the D-262 rule: an unproven 100% prints ">99%", a proven clinch "100%"');
  for (const rule of ['reverse_standings', 'lottery_or_other']) {
    const v = view({ max_pf_moves: Object.assign(clone(MAXPF), { draft_order: { rule, set_at: null } }) });
    assert(u.summary('draft_pick', v).pick === null && u.summary('playoffs', v).pick === null,
      `C4. draft order ${rule}: the projected pick is hidden (spec H-5 / §7.2)`);
  }
  assert(u.summary('playoffs', view({ max_pf_moves: undefined })).pick === null
      && u.summary('playoffs', view({ max_pf_moves: undefined })).playoff === '62%',
    'C5. no max_pf_moves block: the playoff page shows the playoff chance only');
  const noBase = view({ max_pf_moves: Object.assign(clone(MAXPF), { baseline: null }) });
  assert(u.summary('draft_pick', noBase) === null, 'C6. no baseline and no label: no summary');
  assert(!/Math\.(round|floor|ceil)|\* ?100|toFixed/.test(utilSrc) && /playoffOddsText\(baseline\.playoff_probability, baseline, 1\)/.test(utilSrc),
    'C7. the page computes no number: the playoff chance goes through utils/playoffOdds, the pick label is the server\'s');
}

// ═══ D. When the other page is offered (P-10, spec §5.3) ══════════════════
{
  const flags = { maxPfOn: true, targetsOn: true };
  assert(u.offered('draft_pick', view(), flags) && u.offered('playoffs', view(), flags), 'D1. both ready, own pick, flags on → both offered');
  for (const s of ['no_moves', 'no_miss', 'draft_order_not_maxpf', 'season_over', 'after_trade_deadline', 'unavailable']) {
    assert(!u.offered('draft_pick', view({ max_pf_moves: Object.assign(clone(MAXPF), { state: s }) }), flags), `D2. draft pick ${s} → not offered`);
  }
  for (const s of ['no_targets', 'clinched', 'eliminated', 'near_certain', 'no_sellers', 'season_over', 'after_trade_deadline', 'unavailable']) {
    assert(!u.offered('playoffs', view({ playoff_targets: Object.assign(clone(TARGETS), { state: s }) }), flags), `D3. playoffs ${s} → not offered`);
  }
  const owned = view({ max_pf_moves: Object.assign(clone(MAXPF), { pick_owner: { owns_own_pick: false, owner_roster_id: 3, owner_name: 'X' } }) });
  assert(!u.offered('draft_pick', owned, flags), 'D4. a pick owned by another team → draft pick not offered');
  assert(!u.offered('draft_pick', view(), { maxPfOn: false, targetsOn: true }) && !u.offered('playoffs', view(), { maxPfOn: true, targetsOn: false }),
    'D5. a feature flag off → that direction is not offered');
  assert(!u.offered('draft_pick', view({ max_pf_moves: undefined }), flags) && !u.offered('playoffs', view({ playoff_targets: undefined }), flags),
    'D6. no block → not offered');
  const on = Object.assign({ directionPagesOn: true }, flags);
  const L = (page, v, f = on) => u.pageLinks(page, v, f);
  assert(eq(L('draft_pick', view()).other, { label: 'Improve Playoff Chances instead', route: 'ImprovePlayoffChances', page: 'playoffs' })
      && eq(L('playoffs', view()).other, { label: 'Improve Draft Pick instead', route: 'ImproveDraftPick', page: 'draft_pick' }),
    'D7. each page links to the other when the other is offered');
  assert(L('playoffs', owned).other === null && L('draft_pick', view({ playoff_targets: Object.assign(clone(TARGETS), { state: 'clinched' }) })).other === null,
    'D8. no link to a page with nothing to offer');
  assert(L('draft_pick', view(), Object.assign({}, on, { directionPagesOn: false })).other === null,
    'D9. league.direction_pages off (a deep link): no link to the other page (the flag gates every entry point)');
  assert(eq(L('draft_pick', view({ max_pf_moves: undefined, playoff_targets: undefined })).standings, { label: 'View projected standings', route: 'Standings' }),
    'D10. "View projected standings" always shows');
  assert(!/playoff_probability\s*[<>]=?|0\.35|0\.65|0\.45/.test(utilSrc), 'D11. the page never classifies a probability (the server\'s state decides)');
}

// ═══ D12-D15. The server's options, where the block is on the read (D-270) ═
{
  const flags = { maxPfOn: true, targetsOn: true };
  const td = (options, version = 1) => ({ version, state: 'ready', reason: null, options });
  const no = { offered: false, reason: 'none_found' };
  const yes = { offered: true, reason: null };
  assert(!u.offered('draft_pick', view({ team_direction: td({ draft_pick: no, playoffs: yes }) }), flags)
      && u.offered('playoffs', view({ team_direction: td({ draft_pick: no, playoffs: yes }) }), flags),
    'D12. with team_direction on the read its options decide, even where the blocks alone would offer');
  const blocksSayNo = view({ max_pf_moves: Object.assign(clone(MAXPF), { state: 'no_moves' }), team_direction: td({ draft_pick: yes, playoffs: no }) });
  assert(u.offered('draft_pick', blocksSayNo, flags), 'D13. one rule: the server\'s answer, not a second one on the device');
  assert(u.offered('draft_pick', view({ team_direction: td({ draft_pick: no, playoffs: no }, 2) }), flags)
      && u.offered('draft_pick', view({ team_direction: undefined }), flags),
    'D14. no block (flag off, older server) or an unknown version: the step-1 rule over the blocks');
  const on = Object.assign({ directionPagesOn: true }, flags);
  assert(u.pageLinks('playoffs', view({ team_direction: td({ draft_pick: no, playoffs: yes }) }), on).other === null
      && eq(u.pageLinks('draft_pick', view({ team_direction: td({ draft_pick: no, playoffs: yes }) }), on).other,
        { label: 'Improve Playoff Chances instead', route: 'ImprovePlayoffChances', page: 'playoffs' }),
    'D15. the other-page link follows the server\'s options');
}

// ═══ E. Routes, header, FeedbackFAB (P-1, P-2, P-3) ══════════════════════
const registration = (route) => {
  const start = rootNav.indexOf(`name="${route}"`);
  if (start < 0) return '';
  const end = rootNav.indexOf('<Stack.Screen', start);
  return rootNav.slice(start, end < 0 ? undefined : end);
};
const PAGES = [
  { route: 'ImprovePlayoffChances', page: 'playoffs', title: 'Improve Playoff Chances', id: 'improve-playoffs', file: 'src/screens/ImprovePlayoffChancesScreen.tsx' },
  { route: 'ImproveDraftPick', page: 'draft_pick', title: 'Improve Draft Pick', id: 'improve-pick', file: 'src/screens/ImproveDraftPickScreen.tsx' },
];
for (const p of PAGES) {
  const reg = registration(p.route);
  assert(reg && new RegExp(`component=\\{${p.route}Screen\\}`).test(reg)
      && new RegExp(`import ${p.route}Screen from '\\.\\./screens/${p.route}Screen';`).test(rootNav),
    `E1. ${p.route}: registered on the root stack`);
  const before = rootNav.slice(Math.max(0, rootNav.indexOf(`name="${p.route}"`) - 200), rootNav.indexOf(`name="${p.route}"`));
  assert(!/&&\s*\(?\s*<Stack\.Screen\s*$/.test(before) && !/\?\s*\(?\s*<Stack\.Screen\s*$/.test(before),
    `E2. ${p.route}: registered unconditionally (no flag around the Stack.Screen)`);
  assert(new RegExp(`header: \\(\\) => \\(\\s*<LeagueTopBarHeader\\s+title="${p.title}"`).test(reg)
      && new RegExp(`<HeaderBack\\s+testID="${p.id}\\.back-btn"`).test(reg)
      && /navigation\.canGoBack\(\)\s*\?\s*navigation\.goBack\(\)\s*:\s*navigation\.navigate\('Main'\)/.test(reg)
      && !/headerLeft\s*:/.test(reg),
    `E3. ${p.route}: the Standings header pattern (league selector header, title, JS back, no native back)`);
  assert(new RegExp(`${p.route}: \\{ source\\?: DirectionSource \\} \\| undefined;`).test(rootNav),
    `E4. ${p.route}: in the root param list (one optional param, the source, D-270)`);
  const src = strip(read(p.file));
  const fabs = src.match(/<FeedbackFAB\b[^>]*\/>/g) || [];
  assert(fabs.length === 1 && fabs[0].includes(`activeScreen="${p.route}"`) && /aboveTabBar=\{false\}/.test(fabs[0]),
    `E5. ${p.route}: exactly one root-stack FeedbackFAB (#188)`, JSON.stringify(fabs));
  assert(/<SafeAreaView style=\{styles\.safe\} edges=\{\['bottom'\]\}/.test(src) && new RegExp(`<DirectionPage page="${p.page}" />`).test(src),
    `E6. ${p.route}: pads the bottom inset only and renders DirectionPage page="${p.page}"`);
  assert(u.PAGE_ROUTE[p.page] === p.route && u.PAGE_TESTID[p.page] === p.id && u.pageTitle(p.page) === p.title,
    `E7. ${p.route}: the util's route, testID prefix and title agree`);
}
assert(!/direction_pages/.test(rootNav), 'E8. RootNav reads no flag for the pages');

// ═══ F. One forecast read, no new request (P-4) ═══════════════════════════
{
  const queries = pageSrc.match(/useQuery\(\{[\s\S]*?\}\);/g) || [];
  const forecast = queries.find((q) => /league-projection-batch/.test(q)) || '';
  const rosters = queries.find((q) => /league-rosters/.test(q)) || '';
  assert(queries.length === 2, 'F1. the page makes exactly two queries', String(queries.length));
  assert(/queryKey: \['league-projection-batch', userId, leagueId\]/.test(forecast)
      && /queryFn: \(\) => getLeagueProjectionBatch\(leagueId!\)/.test(forecast) && /staleTime: 60_000/.test(forecast)
      && /queryKey: \['league-projection-batch', userId, leagueId\]/.test(standingsSrc)
      && /staleTime: 60_000/.test(standingsSrc),
    'F2. the forecast is Standings\' query: same key, fetcher and staleTime');
  assert(/queryKey: \['league-rosters', leagueId\]/.test(rosters) && /queryFn: \(\) => getLeagueRosters\(leagueId!\)/.test(rosters)
      && /staleTime: 5 \* 60_000/.test(rosters), 'F3. the live rosters are Standings\' session-seeded roster query');
  assert(!/(?<!re)fetch\(|api\.(get|post)|useMutation|simulat|projection-runs/i.test(pageSrc), 'F4. no other request, and no forecast is started');
}

// ═══ G. The existing body, no second list (P-5), open on arrival (P-7) ════
{
  assert((pageSrc.match(/<MaxPfMovesBody\b/g) || []).length === 1 && (pageSrc.match(/<PlayoffTargetsBody\b/g) || []).length === 1,
    'G1. each page mounts the existing body component, once');
  assert(/import \{ MaxPfMovesBody \} from '\.\/MaxPfMovesSection';/.test(pageSrc)
      && /import \{ PlayoffTargetsBody \} from '\.\/PlayoffTargetsSection';/.test(pageSrc), 'G2. the bodies are imported from their sections');
  // GUARD: a page that renders rows any other way fails here.
  assert(!/\.rows\b|\.listed\b|\.map\(|rowLine|rowDetail|visibleRows|FlatList|SectionList|MAXPF_COPY|TARGETS_COPY/.test(pageSrc),
    'G3. GUARD: the page renders no rows, list or row copy of its own');
  assert(!/<Disclosure\b|initialOpen/.test(pageSrc), 'G4. the body is rendered directly, not inside a collapsed Disclosure');
  assert(/<MaxPfMovesBody block=\{view\.block\} model=\{deriveMaxPf\(view\.block, liveRosterIds\)\} leagueId=\{leagueId!\}\s+userId=\{userId\} viewedRef=\{viewedRef\} openOnArrival screen=\{PAGE_ROUTE\[page\]\} \/>/.test(pageSrc),
    'G5. the draft-pick page passes openOnArrival (the one new prop)');
  assert(/openOnArrival\?: boolean;/.test(maxPfBodySrc) && /viewedRef, openOnArrival = false, screen = SCREEN \}: Props\)/.test(maxPfBodySrc)
      && /const gated = model\.isList && !revealed && \(model\.ownerGate \|\| \(!model\.defaultOpen && !openOnArrival\)\);/.test(maxPfBodySrc),
    'G6. openOnArrival (default false) skips only the collapsed "Show moves" step; the "Show anyway" owner gate still applies');
  // Execute the gate expression with the real model for the cases that matter.
  const gate = (model, revealed, openOnArrival) => model.isList && !revealed && (model.ownerGate || (!model.defaultOpen && !openOnArrival));
  const collapsed = maxPf.deriveSection(Object.assign(clone(MAXPF), { baseline: Object.assign(clone(MAXPF.baseline), { playoff_probability: 0.8 }) }), null);
  const ownedModel = maxPf.deriveSection(Object.assign(clone(MAXPF), { pick_owner: { owns_own_pick: false, owner_roster_id: 3, owner_name: 'X' } }), null);
  assert(collapsed.defaultOpen === false && gate(collapsed, false, false) === true && gate(collapsed, false, true) === false,
    'G7. a team Standings would collapse (80%): gated on Standings, open on the page');
  assert(ownedModel.ownerGate === true && gate(ownedModel, false, true) === true,
    'G8. a pick owned by another team: "Show anyway" still shows on the page');
  assert(!/revealed|Show moves|collapsed/i.test(strip(targetsBodySrc)),
    'G9. PlayoffTargetsBody has no collapsed step of its own: rendered directly, its list is open (no prop needed)');
  assert(/<PlayoffTargetsBody block=\{view\.block\} model=\{deriveTargets\(view\.block, rostersQuery\.data \?\? null\)\}\s+viewedRef=\{viewedRef\} screen=\{PAGE_ROUTE\[page\]\} \/>/.test(pageSrc),
    'G10. the playoff page passes the body the props Standings does, plus its route name as the events\' screen (D-270)');
  assert(/navigation\.popTo\('Main', params\)/.test(maxPfBodySrc) && /navigation\.popTo\('Main', params\)/.test(targetsBodySrc),
    'G11. P-9: Find trades is the bodies\' own hand-off (popTo Main), unchanged on the pages');
}

// ═══ H. Summary, links and branches in the page (P-6, P-8, P-10, P-12) ═══
{
  const ids = ['summary', 'summary.playoff', 'summary.pick', 'link.standings', 'link.other', 'no-league', 'unavailable',
    'loading', 'error', 'retry', 'content'];
  const missing = ids.filter((id) => !pageRaw.includes('testID={`${id}.' + id + '`}'));
  assert(missing.length === 0, 'H1. every page testID is set (prefix improve-playoffs / improve-pick)', missing.join(', '));
  assert(pageSrc.indexOf('testID={`${id}.summary`}') < pageSrc.indexOf('<MaxPfMovesBody')
      && pageSrc.indexOf('<PlayoffTargetsBody') < pageSrc.indexOf('testID={`${id}.link.standings`}'),
    'H2. the summary sits above the list, the links under it');
  assert(/onPress=\{\(\) => navigation\.popTo\(links\.standings\.route\)\}/.test(pageSrc)
      && /onPress=\{\(\) => navigation\.popTo\(links\.other!\.route, \{ source: 'other_page' \}\)\}/.test(pageSrc) && /\{links\.other \?/.test(pageSrc),
    'H3. the links use popTo (back to the page below, or replace this one) and the other-page link is conditional');
  assert(/link: \{ minHeight: 44/.test(pageSrc), 'H4. the links are 44pt targets');
  assert(/variant="dataLg"/.test(pageSrc) && /flexWrap: 'wrap'/.test(pageSrc), 'H5. the figures use the mono data type and wrap at large text sizes');
}

// ═══ I. League switch (P-14) ══════════════════════════════════════════════
assert(/<DirectionPageContent key=\{`\$\{userId\}:\$\{leagueId\}`\}/.test(pageSrc)
    && /const leagueId = useSession\(\(s\) => s\.league\?\.league_id\) \|\| null;/.test(pageSrc),
  'I1. the content is keyed by the session league: a switch drops all local state, and both queries are keyed by the league');
assert(!/placeholderData|keepPreviousData/.test(pageSrc), 'I2. no previous-league data is kept as a placeholder');

// ═══ J. Deep links (P-11) ════════════════════════════════════════════════
{
  const mainAt = linksSrc.indexOf('Main: {');
  const a = linksSrc.indexOf("ImprovePlayoffChances: 'app/league/improve-playoffs',");
  const b = linksSrc.indexOf("ImproveDraftPick: 'app/league/improve-pick',");
  assert(a > 0 && b > 0 && a < mainAt && b < mainAt, 'J1. app/league/improve-playoffs and app/league/improve-pick at the root of the table (root stack, like Standings)');
}

// ═══ K. Standings (P-13): link rows with the flag on, today's card off ════
{
  assert(/const directionPagesOn = useFlag\('league\.direction_pages'\);/.test(standingsSrc)
      && /const pageLinks = directionPagesOn \? \{\s*draftPick: \(\) => navigation\.navigate\('ImproveDraftPick', \{ source: 'standings' \}\),\s*playoffs: \(\) => navigation\.navigate\('ImprovePlayoffChances', \{ source: 'standings' \}\),\s*\} : undefined;/.test(standingsSrc)
      && /pageLinks=\{pageLinks\} \/>/.test(standingsSrc),
    'K1. Standings reads league.direction_pages and passes pageLinks only while it is on (undefined off)');
  assert((standingsSrc.match(/useQuery\(/g) || []).length === 3, 'K2. Standings still makes exactly three queries');
  assert(/const moves = pageLinks \? null : movesMounted;/.test(detailSrc) && /const playoffTargets = pageLinks \? null : targetsMounted;/.test(detailSrc),
    'K3. flag off (pageLinks undefined): moves / playoffTargets are exactly the mounted sections, as before');
  assert(/\{moves \? <Disclosure label=\{MAXPF_COPY\['C-TITLE'\]\} testID="standings\.maxpf\.toggle" initialOpen=\{moves\.model\.initialOpen\}>/.test(detailSrc)
      && /\{playoffTargets \? <Disclosure label=\{TARGETS_COPY\['C-TITLE'\]\} testID="standings\.targets\.toggle" initialOpen=\{playoffTargets\.model\.initialOpen\}>/.test(detailSrc),
    'K4. the two inline sections render exactly as before when not linking');
  assert(/\{movesMounted && pageLinks \? <PageLink label=\{MAXPF_COPY\['C-TITLE'\]\}[^>]*onPress=\{pageLinks\.draftPick\} testID="standings\.maxpf\.link" \/> : null\}/.test(detailSrc)
      && /\{targetsMounted && pageLinks \? <PageLink label=\{TARGETS_COPY\['C-TITLE'\]\}[^>]*onPress=\{pageLinks\.playoffs\} testID="standings\.targets\.link" \/> : null\}/.test(detailSrc),
    'K5. flag on: each section becomes one row that opens its page, under the same mount rule (own card, flag, block, Sleeper)');
  assert(/<Icon name="chevron-right" size=\{16\} color=\{chalk\.base\} \/>/.test(detailSrc) && /style=\{styles\.toggle\}/.test(detailSrc.slice(detailSrc.indexOf('function PageLink'))),
    'K6. the link row is the Disclosure row shape (44pt toggle style) with a › chevron');
  assert(!/useQuery|useSession|useFlag|useNavigation/.test(detailSrc), 'K7. the detail still reads nothing (the screen owns the flag and navigation)');
  // Flag-off equivalence by execution: with pageLinks undefined both expressions reduce to the mounted value.
  const pick = (pageLinks, mounted) => (pageLinks ? null : mounted);
  assert(pick(undefined, 'm') === 'm' && pick({}, 'm') === null, 'K8. pageLinks undefined leaves the section; set, it removes it');
}

// ═══ L. The flag, and nothing from steps 2 and 3 ═════════════════════════
{
  const features = JSON.parse(readRoot('config/features.json'));
  const flagsPy = readRoot('backend/feature_flags.py');
  assert(features['league.direction_pages'] === true && /"league\.direction_pages",/.test(flagsPy),
    'L1. league.direction_pages is registered in feature_flags.py and true in config/features.json (ON from 2026-11-15, D-271)');
  for (const name of ['release', 'onboarding-v2', 'profiles-on']) {
    assert(JSON.parse(readRoot(`backend/tests/fixtures/flags/${name}.json`))['league.direction_pages'] === true,
      `L2. fixture ${name}.json mirrors it (true)`);
  }
  const srcFiles = [];
  const walk = (d) => fs.readdirSync(path.join(MOBILE, d), { withFileTypes: true }).forEach((e) =>
    e.isDirectory() ? walk(path.join(d, e.name)) : /\.tsx?$/.test(e.name) && srcFiles.push(path.join(d, e.name)));
  walk('src');
  const all = srcFiles.map((f) => read(f)).join('\n');
  // D-270: the half sheet ships first; the card's button row (cells A and
  // B), `league.direction_both_middle` and the experiment are deferred.
  const experiments = readRoot('backend/experiments.py');
  assert(!/direction_both_middle/.test(all + flagsPy + JSON.stringify(features)) && !/direction_/.test(experiments),
    'L3. deferred (D-270): no league.direction_both_middle anywhere, no experiment definition');
  const banner = strip(read('src/components/home/HomePlayoffBanner.tsx'));
  assert(!/<Button\b|improve_playoffs|improve_pick/.test(banner) && /shown: 'none' as const/.test(read('src/utils/directionCard.ts')),
    'L4. the Home card draws no button row (direction_card_shown.shown is always none)');
  const pkg = JSON.parse(read('package.json'));
  assert(pkg.scripts['test:direction-pages'] === 'node tests/check-direction-pages.js', 'L5. npm run test:direction-pages');
}

// ═══ N. direction_page_opened and the bodies' screen (spec §9, D-270) ═════
{
  assert(u.pageSource(undefined) === 'deep_link' && u.pageSource({}) === 'deep_link' && u.pageSource({ source: 'x' }) === 'deep_link'
      && ['card', 'sheet', 'standings', 'other_page', 'deep_link'].every((x) => u.pageSource({ source: x }) === x),
    'N1. source: the route param when it is one of the five, otherwise deep_link (a deep link carries none)');
  const pv = (patch) => u.pageView(Object.assign({ page: 'draft_pick', data: view() }, BASE, patch));
  assert(u.openedState(pv({ data: undefined })) === null && u.openedState(pv({})) === 'ready'
      && u.openedState(pv({ data: view({ max_pf_moves: Object.assign(clone(MAXPF), { state: 'no_miss' }) }) })) === 'no_miss'
      && u.openedState(pv({ isSleeper: false })) === 'unavailable' && u.openedState(pv({ data: undefined, isError: true })) === 'error'
      && u.openedState(pv({ leagueId: null })) === 'no_league',
    'N2. state: the block\'s server state on a list, else the branch shown; null while loading (the event waits)');
  assert(eq(u.openedProps('playoffs', 'sheet', 'ready'), { page: 'playoffs', source: 'sheet', state: 'ready' })
      && u.PAGE_EVENTS.opened === 'direction_page_opened', 'N3. the event name and its three props');
  assert(/const route = useRoute\(\);/.test(pageSrc) && /const focused = useIsFocused\(\);/.test(pageSrc)
      && /const source = pageSource\(route\.params\);/.test(pageSrc) && /const state = openedState\(view\);/.test(pageSrc)
      && /if \(!focused\) \{ openedRef\.current = false; return; \}\s*if \(openedRef\.current \|\| state == null\) return;\s*openedRef\.current = true;\s*track\(PAGE_EVENTS\.opened, openedProps\(page, source, state\), PAGE_ROUTE\[page\]\);/.test(pageSrc)
      && (pageSrc.match(/\btrack\(/g) || []).length === 1,
    'N4. the page logs once per focus, once its branch is known, under its route name; a blur re-arms it');
  assert(/navigation\.navigate\('ImproveDraftPick', \{ source: 'standings' \}\)/.test(standingsSrc)
      && /navigation\.popTo\(links\.other!\.route, \{ source: 'other_page' \}\)/.test(pageSrc)
      && /params: \{ source: tap\.via \}/.test(read('src/utils/directionCard.ts')),
    'N5. every entry point names itself: Standings, the other page, the card\'s sheet');
  const tax = readRoot('backend/analytics_taxonomy.py');
  const queries = readRoot('backend/analytics_queries.py');
  const nonIntent = (queries.match(/NON_INTENT_EVENTS[^=]*=[\s\S]*?\n\}\)/) || [''])[0];
  assert(/"direction_page_opened":\s+frozenset\(\{"page", "source", "state"\}\)/.test(tax)
      && /"direction_card_shown", "direction_page_opened",/.test(tax)
      && !/"direction_page_opened"/.test(nonIntent),
    'N6. direction_page_opened is registered with exactly its props and is intent (not in NON_INTENT_EVENTS)');
  // The bodies log under the page's route name on a page; Standings is unchanged.
  for (const [mod, side] of [[maxPf, 'give'], [targets, 'receive']]) {
    const logs = [];
    const deps = (screen) => ({ setSide: () => {}, track: (...a) => logs.push(a), navigate: () => {}, now: () => 1, screen });
    const row = { player_id: 'p', name: 'N', position: 'RB', keep: false, rank: 1 };
    const args = mod === maxPf ? [row] : [row, 'opp'];
    mod.handOffToFinder(...args, deps(undefined));
    mod.handOffToFinder(...args, deps('ImproveDraftPick'));
    assert(logs.length === 2 && logs[0][2] === 'Standings' && logs[1][2] === 'ImproveDraftPick' && logs[0][1].side === side,
      `N7. finder_target_pinned (${side}): Standings by default, the page's route name when the page passes it`);
  }
  assert(maxPf.SCREEN === 'Standings' && targets.SCREEN === 'Standings', 'N8. Standings still logs as Standings');
}

// ═══ M. Chalkline ═════════════════════════════════════════════════════════
{
  const ui = pageSrc + detailSrc;
  assert(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(ui), 'M1. no hex or rgb colour literals');
  assert(!/gradient|blur|shadow/i.test(ui) && !/borderRadius: (?!radii\.md\b)/.test(pageSrc), 'M2. no gradient, blur or shadow; radius md only');
  assert(!/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(ui + copySrc), 'M3. no emoji');
  assert(!/flare/.test(pageSrc) && (pageSrc.match(/ice\.base/g) || []).length === 2 && /linkText: \{ color: ice\.base \}/.test(pageSrc),
    'M4. ice only on the links (and the activity indicator); no flare');
  assert(/from '\.\/chalkline'/.test(pageSrc) && /from '\.\.\/theme\/chalkline'/.test(pageSrc), 'M5. Chalkline components and tokens');
}

console.log('');
if (failures) {
  console.error(`${failures} direction-pages check(s) FAILED (${passes} passed).`);
  process.exit(1);
}
console.log(`All direction-pages checks passed (${passes}).`);
