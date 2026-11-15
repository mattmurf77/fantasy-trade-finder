#!/usr/bin/env node
// Playoff targets — the app side (flag `league.playoff_targets`; contract
// docs/plans/league-projections/playoff-targets/contract.md). The mirror of
// check-max-pf-moves.js.
//
// EXECUTES src/utils/playoffTargets.ts + src/utils/playoffTargetsCopy.ts
// under plain node against the contract's own §5 example payloads (parsed
// out of the contract file) and variants of them: every server state and
// `unavailable` reason renders its §10 string; the default-open rule is the
// exact complement of Max PF moves'; the live-roster drop; 5 then Show all;
// §11 formatting; the mount rule; the hand-off calls; the events' properties.
//
// The copy table is compared with the contract's §10 table IN BOTH
// DIRECTIONS, so copy cannot drift from the contract.
//
// SOURCE PINS cover what cannot be executed: StandingsScreen's flag read and
// props, the detail mounting the section after Max PF moves on the own card
// only, no request from the component, its track calls, the popTo hand-off,
// testIDs, 44pt rows, mono numbers, Chalkline tokens, and that the app never
// decides which teams are selling.
//
// Run: node tests/check-playoff-targets.js
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
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const transpile = (src) => ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const run = (rel, requireFn) => {
  const m = { exports: {} };
  new Function('module', 'exports', 'require', transpile(read(rel)))(m, m.exports, requireFn);
  return m.exports;
};
const none = (name) => (r) => { throw new Error(`${name} requires ${r}`); };
const copySrc = read('src/utils/playoffTargetsCopy.ts');
const utilSrc = read('src/utils/playoffTargets.ts');
const bodySrc = read('src/components/PlayoffTargetsSection.tsx');
const detailSrc = read('src/components/LeagueProjectionDetail.tsx');
const screenSrc = read('src/screens/StandingsScreen.tsx');
const copyMod = run('src/utils/playoffTargetsCopy.ts', none('the copy module'));
const oddsMod = run('src/utils/playoffOdds.ts', none('playoffOdds'));
const maxPfCopy = run('src/utils/maxPfMovesCopy.ts', none('maxPfMovesCopy'));
const maxPf = run('src/utils/maxPfMoves.ts', (r) => {
  if (r === './maxPfMovesCopy') return maxPfCopy;
  if (r === './playoffOdds') return oddsMod;
  throw new Error(`maxPfMoves.ts requires ${r}`);
});
const u = run('src/utils/playoffTargets.ts', (r) => {
  if (r === './playoffTargetsCopy') return copyMod;
  if (r === './playoffOdds') return oddsMod;
  if (r === './maxPfMoves') return maxPf;
  throw new Error(`playoffTargets.ts must not require ${r} at runtime`);
});
const C = copyMod.TARGETS_COPY;

const contract = fs.readFileSync(path.join(ROOT, 'docs/plans/league-projections/playoff-targets/contract.md'), 'utf8');
const section = (head, next) => contract.slice(contract.indexOf(head), contract.indexOf(next));

// ── Fixtures: the contract's §5 example payloads, parsed from the file ──
const examples = [...section('## 5. Example payloads', '## 6.').matchAll(/```json\n([\s\S]*?)```/g)]
  .map((m) => JSON.parse(m[1]).playoff_targets);
const [READY, UNAVAILABLE, NEAR_CERTAIN] = examples;
const clone = (o) => JSON.parse(JSON.stringify(o));
const withBlock = (base, patch) => Object.assign(clone(base), patch);
const R1 = READY.rows[0];
const R2 = READY.rows[1];
// Live rosters: Sato on roster 3 (owner "u3"), Okafor on roster 9 (owner "u9").
const LIVE = [
  { roster_id: 7, owner_id: 'me', players: ['1', '2'] },
  { roster_id: 3, owner_id: 'u3', players: ['9001', '77'] },
  { roster_id: 9, owner_id: 'u9', players: ['9002'] },
];
const manyRows = (n) => Array.from({ length: n }, (_, i) => Object.assign(clone(R1), {
  rank: i + 1, player_id: `p${i + 1}`, passes_threshold: i < 2,
}));

// ═══ A. Copy: verbatim with the contract ═════════════════════════════════
{
  assert(examples.length === 3 && READY.state === 'ready' && UNAVAILABLE.state === 'unavailable'
      && NEAR_CERTAIN.state === 'near_certain',
    'A0. the three §5 example payloads parse from the contract');
  const rows = section('## 10. Copy', '## 11.').split('\n').filter((l) => l.startsWith('| C-'));
  const contractStrings = new Set();
  for (const row of rows) {
    const cell = row.split('|')[3] || '';
    for (const m of cell.matchAll(/`([^`]*)`/g)) {
      const s = m[1];
      if (/^[a-z_]+$/.test(s) || /^\{[a-z_]+\}$/.test(s)) continue; // field names, a lone fill
      contractStrings.add(s);
    }
  }
  const values = new Set(Object.values(C));
  const missing = [...contractStrings].filter((s) => !values.has(s));
  assert(rows.length === 37 && missing.length === 0, 'A1. every §10 string is in the copy module verbatim',
    `${rows.length} rows; missing: ${missing.join(' | ')}`);
  const extra = [...values].filter((s) => !contractStrings.has(s));
  assert(extra.length === 0, 'A2. every copy-module string is a §10 string', extra.join(' | '));
  assert(!/^\s*import\s/m.test(copySrc), 'A3. the copy module has zero imports');
  assert(!/^\s*import\s+(?!type\b)(?![^;]*from '\.\/(playoffTargetsCopy|playoffOdds|maxPfMoves)')/m.test(utilSrc),
    'A4. playoffTargets.ts imports only types, its copy module, the playoff-odds rule and Max PF moves\' formatters');
  assert(!/'(Playoff targets|Show all|Find trades)/.test(bodySrc) && /TARGETS_COPY\['C-TITLE'\]/.test(detailSrc),
    'A5. the component and detail render copy from the module, not inline literals');
  assert(/does not|not start|no starter back/.test(C['C-FOOT']) && /usually smaller/.test(C['C-FOOT']),
    'A6. the footer says what the number assumes and that the true gain is usually smaller');
  assert(/under 50%/.test(C['C-ELIGIBLE']) && /Rebuilding or Tanking/.test(C['C-ELIGIBLE']),
    'A7. the eligibility sentence states the operator\'s rule');
}

// ═══ B. Every server state and unavailable reason → its §10 line ═════════
{
  const lineFor = (state, reason = null) => u.stateLine(withBlock(READY, { state, reason }));
  assert(lineFor('season_over') === C['C-SEASON-OVER'] && lineFor('after_trade_deadline') === C['C-DEADLINE']
      && lineFor('clinched') === C['C-CLINCHED'] && lineFor('eliminated') === C['C-ELIMINATED']
      && lineFor('no_sellers') === C['C-NO-SELLERS'],
    'B1. season_over / after_trade_deadline / clinched / eliminated / no_sellers render their lines');
  assert(lineFor('ready') === null && lineFor('no_targets') === null, 'B2. ready / no_targets have no one-line state');
  const reasons = ['no_forecast', 'update_pending', 'refresh_failed', 'stale', 'old_model', 'incomplete',
    'team_not_found', 'unsupported', 'missing_projections', 'read_failed', 'not_computed'];
  const bad = reasons.filter((r) => lineFor('unavailable', r) !== C[`C-U-${r}`]);
  assert(bad.length === 0, 'B3. each of the 11 unavailable reasons renders its C-U line', bad.join(', '));
  assert(lineFor('unavailable', 'brand_new_reason') === C['C-U-other'] && lineFor('unavailable', null) === C['C-U-other']
      && lineFor('unavailable', 'toString') === C['C-U-other'],
    'B4. an unknown or null reason uses the generic line (open set)');
  assert(u.stateLine(UNAVAILABLE) === 'The saved forecast is from an earlier week. Playoff targets return after the next weekly update.',
    'B5. §5.2 (stale) renders its exact sentence');
  assert(u.stateLine(NEAR_CERTAIN) === 'Your team makes the playoffs in >99% of simulations, so no trade raises that by a visible amount.',
    'B6. §5.3 (near_certain, 99.72%, not clinched) prints ">99%", never 100%');
  const m = u.deriveSection(NEAR_CERTAIN, LIVE);
  assert(m.isList === false && m.listed.length === 0 && m.baseline === null && m.foot === null && m.eligible === null
      && m.initialOpen === false, 'B7. a one-line state shows no baseline, no list and no footer, and starts closed');
  const states = ['unavailable', 'season_over', 'after_trade_deadline', 'clinched', 'eliminated', 'near_certain',
    'no_sellers', 'no_targets', 'ready'];
  const fromContract = [...section('### 4.1', '### 4.2').matchAll(/^\| \d \| `([a-z_]+)`/gm)].map((x) => x[1]);
  assert(eq(fromContract, states), 'B8. the nine server states are the contract §4.1 list, in order', fromContract.join(','));
  const mounts = (state) => u.sectionMounts({ block: withBlock(READY, { state }), flagOn: true, isSleeper: true, ownCard: true });
  assert(states.every(mounts) && !mounts('brand_new_state'), 'B9. every known state mounts; an unknown state renders nothing');
}

// ═══ C. The mount rule ════════════════════════════════════════════════════
{
  const base = { block: READY, flagOn: true, isSleeper: true, ownCard: true };
  assert(u.sectionMounts(base), 'C1. flag on + block + Sleeper + own card mounts');
  assert(!u.sectionMounts({ ...base, flagOn: false }), 'C2. flag off never mounts, even with a block');
  assert(!u.sectionMounts({ ...base, block: undefined }) && !u.sectionMounts({ ...base, block: null }),
    'C3. no block (flag off on the server, or an older server) never mounts');
  assert(!u.sectionMounts({ ...base, ownCard: false }), 'C4. another team\'s card never mounts');
  assert(!u.sectionMounts({ ...base, isSleeper: false }), 'C5. a non-Sleeper league never mounts');
  assert(!u.sectionMounts({ ...base, block: withBlock(READY, { version: 2 }) }), 'C6. an unknown version renders nothing');
}

// ═══ D. Open or closed by default: the complement of Max PF moves ════════
{
  const at = (p, outlook) => withBlock(READY, { saved_outlook: outlook, baseline: { ...READY.baseline, playoff_probability: p } });
  assert(u.startsOpen(at(0.62, 'contender')) && u.startsOpen(at(0.4501, null)) && u.startsOpen(at(0.9, 'not_sure')),
    'D1. above 45% with no selling outlook starts open');
  assert(!u.startsOpen(at(0.45, null)) && !u.startsOpen(at(0.1, 'contender')),
    'D2. at or below 45% starts closed (0.45 itself is Max PF moves\' side)');
  assert(!u.startsOpen(at(0.9, 'rebuilder')) && !u.startsOpen(at(0.9, 'jets')),
    'D3. a saved Rebuilding or Tanking outlook starts closed at any chance');
  assert(!u.startsOpen(withBlock(NEAR_CERTAIN, {})) && !u.startsOpen(UNAVAILABLE),
    'D4. a one-line state never starts open');
  // The same inputs through Max PF moves' own rule: exactly one of the two is open.
  const maxPfBlock = (p, outlook) => ({ state: 'ready', saved_outlook: outlook, baseline: { playoff_probability: p } });
  const grid = [];
  for (const p of [0, 0.1, 0.44, 0.45, 0.4501, 0.5, 0.75, 0.99]) {
    for (const o of [null, 'championship', 'contender', 'rebuilder', 'jets', 'not_sure']) grid.push([p, o]);
  }
  const clash = grid.filter(([p, o]) => u.startsOpen(at(p, o)) === maxPf.defaultOpen(maxPfBlock(p, o)));
  assert(clash.length === 0, 'D5. over a grid of chances and outlooks, exactly one of the two sections starts open',
    JSON.stringify(clash));
  assert(/DEFAULT_OPEN_MAX_PLAYOFF/.test(utilSrc) && !/0\.45/.test(utilSrc),
    'D6. the 45% cut is Max PF moves\' constant, imported, not a second literal');
}

// ═══ E. Rows listed: live rosters, order, 5 then Show all ════════════════
{
  const m = u.deriveSection(READY, LIVE);
  assert(m.isList && eq(m.listed.map((r) => r.rank), [1, 2]) && m.rosterLine === null && m.noTargetsLine === null
      && m.noneAloneLine === null && m.changedLine === null,
    'E1. ready lists every served row in rank order, passing or not, with no notice');
  assert(m.baseline === 'Your playoff chance today: 62%.' && m.head === 'Lineup points added over the remaining 4 weeks'
      && m.foot === C['C-FOOT'] && m.eligible === C['C-ELIGIBLE'],
    'E2. baseline, head, footer and the eligibility sentence render');
  assert(eq(u.deriveSection(READY, null).listed.map((r) => r.rank), [1, 2]) && u.deriveSection(READY, undefined).rosterLine === null,
    'E3. live rosters not loaded: no check, every row listed, no notice');
  const moved = [LIVE[0], { roster_id: 3, owner_id: 'u3', players: ['77'] }, LIVE[2]];
  const dropped = u.deriveSection(READY, moved);
  assert(eq(dropped.listed.map((r) => r.player_id), ['9002']) && dropped.rosterLine === C['C-ROSTER'],
    'E4. a player no longer on his team\'s live roster is dropped and C-ROSTER shows');
  const gone = u.deriveSection(READY, [LIVE[0]]);
  assert(gone.listed.length === 0 && gone.rosterLine === C['C-ROSTER'] && gone.noTargetsLine === null && gone.head === null
      && gone.foot === null, 'E5. every row dropped: C-ROSTER alone (no C-NO-TARGETS, no head, no footer)');
  const none = u.deriveSection(withBlock(READY, { state: 'no_targets', rows: [] }), LIVE);
  assert(none.noTargetsLine === C['C-NO-TARGETS'] && none.listed.length === 0 && none.eligible === C['C-ELIGIBLE'],
    'E6. no_targets with no rows shows C-NO-TARGETS and still states the rule');
  const noPass = u.deriveSection(withBlock(READY, { state: 'no_targets', rows: [R2] }), LIVE);
  assert(noPass.listed.length === 1 && noPass.noneAloneLine === C['C-NONE-ALONE'] && noPass.noTargetsLine === null,
    'E7. no_targets with rows lists them under C-NONE-ALONE');
  assert(u.deriveSection(withBlock(READY, { sellers_changed: true }), LIVE).changedLine === C['C-CHANGED']
      && u.deriveSection(withBlock(NEAR_CERTAIN, { sellers_changed: true }), LIVE).changedLine === null,
    'E8. sellers_changed shows C-CHANGED on a list state only');
  const eight = manyRows(8).reverse();
  const listed = u.listedRows(withBlock(READY, { rows: eight }), null).rows;
  assert(eq(listed.map((r) => r.rank), [1, 2, 3, 4, 5, 6, 7, 8]), 'E9. rows are listed by rank whatever order they arrive in');
  const first = u.visibleRows(listed, false);
  const all = u.visibleRows(listed, true);
  assert(first.rows.length === 5 && first.showAllButton && all.rows.length === 8 && !all.showAllButton
      && !u.visibleRows(listed.slice(0, 5), false).showAllButton,
    'E10. the first 5 show, Show all reveals the rest, and 5 rows show no button');
  const head1 = u.headLine(withBlock(READY, { baseline: { ...READY.baseline, weeks_remaining: 1 } }));
  assert(head1 === 'Lineup points added over the final week', 'E11. one week left reads "over the final week"', head1);
}

// ═══ F. Row lines and formatting (contract §10, §11) ═════════════════════
{
  assert(u.rowLine1(R1) === 'R. Sato  RB  +31' && eq(u.rowLine1Parts(R1), { name: 'R. Sato', position: 'RB', gain: '+31' }),
    'F1. line 1: short name, position, the lineup gain with a leading +', u.rowLine1(R1));
  assert(u.rowLine2(R1, READY) === 'Playoff chance 62% → 71%', 'F2. line 2: the playoff chance now → after', u.rowLine2(R1, READY));
  assert(u.rowLine3(R1) === 'Harbor Kings · 12% playoff chance' && u.rowLine3(R2) === 'Team 9 · 66% playoff chance',
    'F3. line 3: the team and its playoff chance in the forecast', u.rowLine3(R1));
  const high = Object.assign(clone(R1), { playoff_probability: { now: 0.62, after: 0.9991 } });
  assert(u.rowLine2(high, READY) === 'Playoff chance 62% → >99%', 'F4. an unproven 100% prints ">99%" (D-262)', u.rowLine2(high, READY));
  const dead = Object.assign(clone(R1), { seller: { ...R1.seller, playoff_probability: 0, playoff_eliminated: true } });
  const nearDead = Object.assign(clone(R1), { seller: { ...R1.seller, playoff_probability: 0.001 } });
  assert(u.rowLine3(dead) === 'Harbor Kings · 0% playoff chance' && u.rowLine3(nearDead) === 'Harbor Kings · <1% playoff chance',
    'F5. a team\'s 0% needs its own elimination proof; otherwise "<1%"');
  assert(u.rowLine1(Object.assign(clone(R1), { lineup_gain: 0 })) === 'R. Sato  RB  0', 'F6. a gain of exactly 0 prints 0');
  const d1 = u.rowDetail(R1, READY, 'u3');
  assert(d1.weeks === 'Starts for you in 4 of the remaining 4 weeks.' && d1.replaces === 'Starts over Cal Mercer (3 weeks).'
      && d1.openSpot === 'Fills an open lineup spot (1 week).' && d1.button === 'Find trades for R. Sato',
    'F7. opened row: weeks, who he starts over, the open spot, the button', JSON.stringify(d1));
  const d2 = u.rowDetail(R2, READY, 'u9');
  assert(d2.weeks === 'Starts for you in 2 of the remaining 4 weeks.' && d2.replaces === 'Starts over Ezra Quill (free agent).'
      && d2.openSpot === null, 'F8. one replaced player in every affected week reads "Starts over X."; a free agent is marked',
    JSON.stringify(d2));
  const many = Object.assign(clone(R1), {
    weeks_affected: 9, replaces_more: 2,
    replaces: [
      { player_id: 'a', name: 'Al One', short_name: 'A. One', free_agent: false, weeks: 5 },
      { player_id: 'b', name: 'Bo Two', short_name: 'B. Two', free_agent: false, weeks: 3 },
      { player_id: 'c', name: 'Cy Three', short_name: 'C. Three', free_agent: true, weeks: 1 },
    ],
  });
  assert(u.replacesLine(many) === 'Starts over Al One (5 weeks), Bo Two (3 weeks), Cy Three (free agent) (1 week) and 2 more.',
    'F9. several replaced players: weeks each, "1 week" singular, then "and N more."', u.replacesLine(many));
  const last = withBlock(READY, { baseline: { ...READY.baseline, weeks_remaining: 1 } });
  assert(u.rowDetail(R1, last, 'u3').weeks === 'Starts for you in the final week.', 'F10. one week left: the final-week sentence');
  assert(u.rowDetail(R1, READY, null).button === null, 'F11. no resolved partner: no Find trades button');
  assert(u.replacesLine(Object.assign(clone(R1), { replaces: [], replaces_more: 0 })) === null, 'F12. nobody replaced: no sentence');
}

// ═══ G. The Find trades hand-off (contract §12) ══════════════════════════
{
  const m = u.deriveSection(READY, LIVE);
  assert(eq(m.opponents, { 1: 'u3', 2: 'u9' }), 'G1. the canvas partner is the live owner of the row\'s team');
  assert(eq(u.deriveSection(READY, null).opponents, { 1: null, 2: null })
      && u.deriveSection(READY, [LIVE[0], { roster_id: 3, owner_id: null, players: ['9001'] }, LIVE[2]]).opponents[1] === null,
    'G2. rosters not loaded, or a roster with no owner: no partner');
  const calls = [];
  const deps = {
    setSide: (side, players) => calls.push(['setSide', side, players]),
    track: (event, props, screen) => calls.push(['track', event, props, screen]),
    navigate: (params) => calls.push(['navigate', params]),
    now: () => 4242,
  };
  const went = u.handOffToFinder(R1, 'u3', deps);
  assert(went === true && eq(calls, [
    ['setSide', 'receive', [{ id: '9001', name: 'Rhett Sato', position: 'RB' }]],
    ['setSide', 'give', []],
    ['track', 'finder_target_pinned', { side: 'receive', source: 'playoff_targets' }, 'Standings'],
    ['navigate', { screen: 'Trades', params: { screen: 'TradesHome',
      params: { canvasPrefill: { opponentId: 'u3', give: [], receive: ['9001'] }, canvasPrefillSeq: 4242 }, pop: true } }],
  ]), 'G3. the hand-off pins receive, clears give, logs, then opens the canvas with his team as partner', JSON.stringify(calls));
  calls.length = 0;
  assert(u.handOffToFinder(R1, null, deps) === false && calls.length === 0, 'G4. without a partner the hand-off does nothing');
  assert(/navigation\.popTo\('Main', params\)/.test(bodySrc) && !/navigation\.navigate\(/.test(bodySrc),
    'G5. the component navigates with popTo(\'Main\', …) (Standings is a root-stack push)');
  assert(/useFinderTargets\.getState\(\)\.setSide/.test(bodySrc) && !/setHandoff/.test(bodySrc + utilSrc),
    'G6. pins go through the finder-targets store; no hand-off object, no auto-run');
}

// ═══ H. Events (contract §9): exact props, never a player id or name ═════
{
  const m = u.deriveSection(READY, LIVE);
  assert(eq(u.viewedProps(READY, m), { state: 'ready', n_listed: 2, any_pass: true, n_sellers: 5, band: 'contender' }),
    'H1. playoff_targets_viewed props for §5.1', JSON.stringify(u.viewedProps(READY, m)));
  assert(eq(u.viewedProps(UNAVAILABLE, u.deriveSection(UNAVAILABLE, LIVE)),
    { state: 'unavailable', n_listed: 0, any_pass: false, n_sellers: 0, band: 'none' }), 'H2. no baseline ⇒ band "none"');
  assert(eq(u.expandedProps(R1), { position: 'RB', rank: 1 }), 'H3. playoff_target_expanded props');
  assert(eq(u.PINNED_PROPS, { side: 'receive', source: 'playoff_targets' })
      && eq(u.TARGETS_EVENTS, { viewed: 'playoff_targets_viewed', expanded: 'playoff_target_expanded', pinned: 'finder_target_pinned' }),
    'H4. the event names and the pin props');
  const props = JSON.stringify([u.viewedProps(READY, m), u.expandedProps(R1), u.PINNED_PROPS]);
  assert(!/9001|Sato|Harbor/.test(props), 'H5. no player id, player name or team name in any event property');
  assert((bodySrc.match(/track\(TARGETS_EVENTS\.viewed/g) || []).length === 1 && /viewedRef\.current = true/.test(bodySrc)
      && /track\(TARGETS_EVENTS\.expanded, expandedProps\(row\), SCREEN\)/.test(bodySrc),
    'H6. the component fires viewed once per card opening and expanded on opening a row');
  const taxonomy = fs.readFileSync(path.join(ROOT, 'backend/analytics_taxonomy.py'), 'utf8');
  const queries = fs.readFileSync(path.join(ROOT, 'backend/analytics_queries.py'), 'utf8');
  assert(/"playoff_targets_viewed":\s+frozenset\(\{"state", "n_listed", "any_pass", "n_sellers", "band"\}\)/.test(taxonomy)
      && /"playoff_target_expanded":\s+frozenset\(\{"position", "rank"\}\)/.test(taxonomy),
    'H7. both events are registered in the backend taxonomy with exactly these props');
  const nonIntent = queries.slice(queries.indexOf('NON_INTENT_EVENTS'));
  assert(/"playoff_targets_viewed"/.test(nonIntent) && !/"playoff_target_expanded"/.test(queries),
    'H8. the impression is classified non-intent; the row-open is not');
}

// ═══ I. Source pins: mounting, flag, no request, the server decides ══════
{
  assert(/const playoffTargetsOn = useFlag\('league\.playoff_targets'\);/.test(screenSrc),
    'I1. StandingsScreen reads flag league.playoff_targets');
  assert(/targets=\{\{\s*block: data\?\.playoff_targets, flagOn: playoffTargetsOn, isSleeper,\s*liveRosters: rostersQuery\.data \?\? null,\s*\}\}/.test(screenSrc),
    'I2. it passes the block from the one forecast read and the page\'s own roster query');
  assert((screenSrc.match(/useQuery\(/g) || []).length === 3, 'I3. the screen still makes exactly three queries (no new request)');
  const maxAt = detailSrc.indexOf('testID="standings.maxpf.toggle"');
  const mineAt = detailSrc.indexOf('testID="standings.targets.toggle"');
  assert(maxAt > 0 && mineAt > maxAt, 'I4. the Playoff targets disclosure mounts after Max PF moves');
  assert(/targetsMount\(\{\s*block: targets\.block, flagOn: targets\.flagOn, isSleeper: targets\.isSleeper,\s*ownCard: isOwnCard\(team\.roster_id, result\.viewer_roster_id \?\? targets\.block\.viewer_roster_id\),/.test(detailSrc),
    'I5. the detail mounts it through the mount rule, on the viewer\'s own card only');
  assert(/initialOpen=\{playoffTargets\.model\.initialOpen\}/.test(detailSrc), 'I6. the disclosure starts open by the §7.1 rule');
  assert(!/useQuery|useMutation|api\.(get|post)|fetch\(/.test(bodySrc + utilSrc), 'I7. the section makes no request of any kind');
  assert(!/is_seller|isSeller|< ?0\.5|SELLING/.test(bodySrc + utilSrc) && !/'rebuilder'|'jets'/.test(bodySrc),
    'I8. the app never decides which teams are selling (the server does, contract §2)');
  assert(!/Math\.(round|floor|ceil)|\* ?100|\/ ?100|toFixed/.test(bodySrc + utilSrc),
    'I9. the section computes no number: every figure is read from the block and formatted by shared helpers');
  const ids = ['standings.targets.body', 'standings.targets.line', 'standings.targets.baseline', 'standings.targets.changed',
    'standings.targets.roster-changed', 'standings.targets.no-targets', 'standings.targets.none-alone',
    'standings.targets.show-all'];
  const missing = ids.filter((id) => !bodySrc.includes(`testID="${id}"`));
  assert(missing.length === 0 && /testID=\{`standings\.targets\.row\.\$\{row\.rank\}`\}/.test(bodySrc)
      && /testID=\{`standings\.targets\.detail\.\$\{row\.rank\}`\}/.test(bodySrc)
      && /testID=\{`standings\.targets\.find\.\$\{row\.rank\}`\}/.test(bodySrc),
    'I10. every testID in the scope block is on the component', missing.join(', '));
}

// ═══ J. Chalkline: tokens only ════════════════════════════════════════════
{
  assert(!/#[0-9a-fA-F]{3,8}\b/.test(bodySrc) && !/rgba?\(/.test(bodySrc), 'J1. no hex or rgb colour literals');
  assert(!/gradient|blur|shadow|borderRadius/i.test(bodySrc), 'J2. no gradient, blur, shadow or radius');
  assert(!/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(bodySrc + copySrc), 'J3. no emoji in the component or the copy');
  assert(/rowHead: \{ minHeight: 44/.test(bodySrc) && /link: \{ minHeight: 44/.test(bodySrc), 'J4. rows and the link are 44pt targets');
  assert(/num: \{ \.\.\.type\.data/.test(bodySrc), 'J5. the number uses the mono data type');
  assert(/linkText: \{ color: ice\.base \}/.test(bodySrc) && (bodySrc.match(/ice\./g) || []).length === 1,
    'J6. ice appears once, on the tappable link (an action)');
  assert(/from '\.\/chalkline'/.test(bodySrc) && /from '\.\.\/theme\/chalkline'/.test(bodySrc),
    'J7. the component uses Chalkline components and theme tokens');
  assert(!/FeedbackFAB/.test(bodySrc), 'J8. no FeedbackFAB (a section, not a screen)');
}

console.log('');
if (failures) {
  console.error(`${failures} playoff-targets check(s) FAILED (${passes} passed).`);
  process.exit(1);
}
console.log(`All playoff-targets checks passed (${passes}).`);
