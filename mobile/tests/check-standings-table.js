#!/usr/bin/env node
// The Standings page's single table (docs/plans/home-engagement/
// scope-standings-table.md; operator 2026-11-12: "one row. W-L, Projected
// W-L, Playoff Odds %. A pill in the top right of the table to toggle to
// Points summary").
//
// PART A EXECUTES src/utils/standingsTable.ts (and standings.ts's Max PF
// reader) under plain node: sorting for every column in both directions with
// ties and dashes, the heading-tap rule, the number formats ("<1%", "100%",
// "1,498"), the no-forecast dash rules, the open team's stat rows in each
// view, the no-forecast line, and the SoS column (strength of schedule,
// 2026-11-25 display build) against a real league's saved forecast.
//
// PART B PINS THE STRUCTURE of screens/StandingsScreen.tsx: no segments; the
// Record | Points pill; one table with four Record columns; the outlined
// open-team card with StatRow rows; the caption under the table (footers,
// status sentences and "Partial Sleeper data" gone); the sort caret left of
// number headings; the shared forecast query key; no simulation or outlook
// request on open; league-switch behaviour; one FeedbackFAB; the
// LeagueTopBarHeader unchanged; the one analytics emitter; callers no longer
// send `{ segment }`; LeagueProjectionSection gone.
//
// Run: node tests/check-standings-table.js
'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
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
const exists = (rel) => fs.existsSync(path.join(MOBILE, rel));
const load = (rel, deps = {}) => {
  const src = read(rel);
  const js = ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const m = { exports: {} };
  new Function('module', 'exports', 'require', js)(m, m.exports, (name) => {
    if (name in deps) return deps[name];
    throw new Error(`${rel} must not require ${name} at runtime`);
  });
  return { src, mod: m.exports };
};
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ═══ A. The pure table ══════════════════════════════════════════════════
// Its one runtime import is the zero-import playoff-odds rule (D-262).
const { mod: odds } = load('src/utils/playoffOdds.ts');
const { src: utilSrc, mod: u } = load('src/utils/standingsTable.ts', { './playoffOdds': odds });
const { mod: s } = load('src/utils/standings.ts');
assert(!/^\s*import\s+(?!type\b)(?![^;]*from '\.\/playoffOdds')/m.test(utilSrc),
  'A0. standingsTable.ts imports only types and the zero-import playoff-odds rule');

// A1 — standings.ts reads Sleeper's Max PF (ppts) and nothing else for it.
assert(s.maxPointsFor({ ppts: 1721, ppts_decimal: 44 }) === 1721.44, 'A1a. Max PF = ppts + ppts_decimal / 100');
assert(s.maxPointsFor({ fpts: 1500 }) === null && s.maxPointsFor(null) === null,
  'A1b. no ppts ⇒ Max PF unknown (null), never fpts');
{
  const st = s.currentStandings([
    { roster_id: 1, owner_id: 'a', settings: { wins: 1, losses: 0, fpts: 100, ppts: 140, ppts_decimal: 5 } },
    { roster_id: 2, owner_id: 'b', settings: { wins: 0, losses: 1, fpts: 90 } },
  ], [], null);
  assert(st.rows[0].maxPf === 140.05 && st.rows[1].maxPf === null, 'A1c. currentStandings carries maxPf per row');
}

// Fixture: six teams. Standings order (place) is W–L then PF then roster id.
const F = (rid, modal, expected, odds, maxMean, curMax) => ({
  roster_id: rid, modal_record: modal, expected_record: expected, playoff_probability: odds,
  bye_probability: 0.033, maxpf_mean: maxMean, current_maxpf: curMax, weeks: [],
});
const R = (rid, name, place, w, l, t, pf, maxPf) => ({
  rosterId: rid, name, isYou: rid === 4, place, wins: w, losses: l, ties: t,
  winPct: (w + l + t) ? (w + t / 2) / (w + l + t) : 0, pointsFor: pf, maxPf,
});
const standingsRows = [
  R(1, 'Gridiron Owls', 1, 8, 1, 0, 1498.2, 1721.4),
  R(2, 'sunday Scaries', 2, 8, 1, 0, 1466.0, 1689.9),
  R(3, 'Fourth & Long', 3, 6, 3, 0, 1391.7, null), // Sleeper sent no ppts
  R(4, 'Red Zone Rhinos', 4, 5, 4, 0, 1306.0, 1588.6),
  R(5, 'Waiver Wolves', 5, 5, 4, 0, 1306.0, 1588.6), // ties #4 on W–L, PF and Max PF
  R(6, 'Taxi Squad', 6, 1, 8, 0, 1011.5, null), // no ppts and no forecast
];
const forecast = [
  F(1, [12, 2, 0], [11.5, 2.5, 0], 0.9996, 2664, 1721.4),
  F(2, [11, 3, 0], [11.0, 3.0, 0], 0.9996, 2621, 1689.9), // same odds as #1
  F(3, [10, 4, 0], [9.7, 4.3, 0], 0.999, 2548, 1640.2),
  F(4, [8, 6, 0], [8.3, 5.7, 0], 0.958, 2470, 1588.6),
  F(5, [8, 6, 0], [8.3, 5.7, 0], 0.667, 2470, 1588.6), // same Proj. W–L + Proj. Max PF as #4
];
const rows = u.buildTableRows(standingsRows, forecast);
assert(rows.length === 6 && rows.map((r) => r.rosterId).join() === '1,2,3,4,5,6',
  'A2a. buildTableRows keeps standings order, one row per team');
assert(rows[2].maxPf === 1640.2 && rows[5].maxPf === null && rows[0].maxPf === 1721.4,
  "A2b. Max PF: Sleeper's ppts first, the forecast's current_maxpf when Sleeper sent none, else null");
assert(rows[5].forecast === null && rows[0].forecast.roster_id === 1, 'A2c. forecast joined by roster id; missing ⇒ null');

const order = (column, dir, input = rows) => u.sortRows(input, { column, dir }).map((r) => r.rosterId).join(',');
const SORTS = [
  // [column, dir, expected, why]
  ['wl', 'desc', '1,2,3,4,5,6', 'W–L best first; PF breaks the 8–1 tie; a full tie keeps standings order'],
  ['wl', 'asc', '6,4,5,3,2,1', 'W–L reversed; a full tie (#4/#5) still keeps standings order'],
  ['projWl', 'desc', '1,2,3,4,5,6', 'Proj. W–L best first; the identical #4/#5 keep standings order; no forecast last'],
  ['projWl', 'asc', '4,5,3,2,1,6', 'Proj. W–L reversed; the dash (#6) is still last'],
  ['playoffs', 'desc', '1,2,3,4,5,6', 'Playoffs highest first; the equal #1/#2 keep standings order; dash last'],
  ['playoffs', 'asc', '5,4,3,1,2,6', 'Playoffs lowest first; ties keep standings order; dash last'],
  ['pf', 'desc', '1,2,3,4,5,6', 'PF most first; equal PF keeps standings order'],
  ['pf', 'asc', '6,4,5,3,2,1', 'PF least first'],
  ['maxPf', 'desc', '1,2,3,4,5,6', 'Max PF most first (#3 uses the forecast fallback); equal #4/#5 keep standings order; unknown (#6) last'],
  ['maxPf', 'asc', '4,5,3,2,1,6', 'Max PF least first; unknown still last'],
  ['projMaxPf', 'desc', '1,2,3,4,5,6', 'Proj. Max PF most first; dash last'],
  ['projMaxPf', 'asc', '4,5,3,2,1,6', 'Proj. Max PF least first; dash last'],
  ['team', 'asc', '3,1,4,2,6,5', 'Team A–Z, case-insensitive'],
  ['team', 'desc', '5,6,2,4,1,3', 'Team Z–A'],
];
for (const [column, dir, want, why] of SORTS) {
  const got = order(column, dir);
  assert(got === want, `A3. sort ${column} ${dir}: ${why}`, `got ${got}, want ${want}`);
}
{
  // #5 before #4 on input: their full tie must still come out in standings order.
  const shuffled = [rows[5], rows[4], rows[0], rows[3], rows[2], rows[1]];
  assert(order('wl', 'desc', shuffled) === '1,2,3,4,5,6' && order('maxPf', 'asc', shuffled) === '4,5,3,2,1,6' &&
      shuffled[0].rosterId === 6,
    'A3o. sortRows ignores input order (standings place is the tiebreak) and returns a copy');
  const noFc = u.buildTableRows(standingsRows, null);
  assert(order('playoffs', 'desc', noFc) === '1,2,3,4,5,6' && order('projWl', 'asc', noFc) === '1,2,3,4,5,6',
    'A3p. with no forecast at all, forecast columns sort as all-dash: standings order in both directions');
}

// A4 — heading taps.
assert(eq(u.nextSort({ column: 'wl', dir: 'desc' }, 'wl'), { column: 'wl', dir: 'asc' }) &&
    eq(u.nextSort({ column: 'wl', dir: 'asc' }, 'wl'), { column: 'wl', dir: 'desc' }),
  'A4a. tapping the active heading reverses it');
assert(eq(u.nextSort({ column: 'wl', dir: 'asc' }, 'playoffs'), { column: 'playoffs', dir: 'desc' }) &&
    eq(u.nextSort({ column: 'pf', dir: 'desc' }, 'team'), { column: 'team', dir: 'asc' }),
  'A4b. a new heading starts best / biggest first; Team starts A–Z');
assert(eq(u.DEFAULT_SORT, { record: { column: 'wl', dir: 'desc' }, points: { column: 'pf', dir: 'desc' } }),
  'A4c. Record opens on W–L best first, Points on PF most first');
assert(eq(u.VIEW_COLUMNS, { record: ['wl', 'projWl', 'playoffs', 'sos'], points: ['pf', 'maxPf', 'projMaxPf'] }),
  'A4d. Record = W–L · Proj. W–L · Playoffs · SoS; Points = PF · Max PF · Proj. Max PF');
assert(u.COLUMN_LABEL.projMaxPf === 'Proj.\nMax PF' && u.COLUMN_LABEL.projWl === 'Proj. W–L' &&
    u.COLUMN_LABEL.playoffs === 'Play\noffs' && u.COLUMN_LABEL.sos === 'SoS',
  'A4e. headings: Proj. Max PF breaks after "Proj.", Playoffs stacks "Play" over "offs", SoS keeps its lowercase o');
assert(u.COLUMN_SPOKEN.sos === 'strength of schedule' && u.COLUMN_SPOKEN.playoffs === 'playoff odds',
  'A4f. VoiceOver names: "strength of schedule", "playoff odds"');

// A5 — number formats.
// D-262: 100% only with a proven clinch, 0% only with a proven elimination.
const CL = { playoff_clinched: true }, EL = { playoff_eliminated: true };
const ODDS = [[0, null, '<1%'], [0.001, null, '<1%'], [0.00499, null, '<1%'], [0.005, null, '1%'], [0.0149, null, '1%'],
  [0.4, null, '40%'], [0.958, null, '96%'], [0.9949, null, '99%'], [0.995, null, '>99%'], [0.9995, null, '>99%'],
  [1, null, '>99%'], [1, {}, '>99%'], [1, CL, '100%'], [0, EL, '0%'], [0.004, EL, '0%'], [0.4, CL, '40%']];
const badOdds = ODDS.filter(([p, proof, want]) => u.oddsText(p, proof) !== want);
assert(badOdds.length === 0, 'A5a. playoff odds: whole percent; "100%" / "0%" only when proven, else ">99%" / "<1%"',
  badOdds.map(([p, pr, w]) => `${p} ${JSON.stringify(pr)} → ${u.oddsText(p, pr)} (want ${w})`).join('; '));
{
  // Sort: equal probability, the proven clinch ranks above the unproven ">99%",
  // the proven elimination below the unproven "<1%".
  const mk = (rid, place, p, proof) => ({ rosterId: rid, name: `T${rid}`, isYou: false, place, wins: 0, losses: 0, ties: 0,
    winPct: 0, pointsFor: 0, maxPf: null, forecast: { roster_id: rid, modal_record: [0, 0, 0], expected_record: [0, 0, 0],
      playoff_probability: p, bye_probability: 0, maxpf_mean: 0, current_maxpf: 0, ...proof } });
  const rs = [mk(1, 1, 1, {}), mk(2, 2, 1, CL), mk(3, 3, 0, EL), mk(4, 4, 0, {})];
  const ord = (dir) => u.sortRows(rs, { column: 'playoffs', dir }).map((r) => r.rosterId).join(',');
  assert(ord('desc') === '2,1,4,3' && ord('asc') === '3,4,1,2',
    'A5f. playoffs sort: proven 100% above unproven >99%; proven 0% below unproven <1%', `${ord('desc')} / ${ord('asc')}`);
  assert(u.cellText(rs[0], 'playoffs') === '>99%' && u.cellText(rs[1], 'playoffs') === '100%'
      && u.cellText(rs[2], 'playoffs') === '0%' && u.cellText(rs[3], 'playoffs') === '<1%'
      && u.openTeamStats('points', rs[0], 0).some((x) => x.label === 'Playoff odds' && x.value === '>99%'),
    'A5g. the cell and the open team\'s stat row pass the team\'s proof');
}
const PTS = [[1498.2, '1,498'], [999.6, '1,000'], [12345.4, '12,345'], [0, '0'], [87.5, '88']];
assert(PTS.every(([n, w]) => u.pointsText(n) === w), 'A5b. points: whole, thousands commas, no toLocaleString',
  PTS.map(([n]) => u.pointsText(n)).join(' '));
assert(!/\.toLocaleString\(/.test(utilSrc), 'A5c. the util never calls toLocaleString');
assert(u.recordText([8, 6, 0]) === '8–6' && u.recordText([8, 5, 1]) === '8–5–1' && u.recordText([8, 6]) === '8–6',
  'A5d. records: en dash, a tie column only when there is a tie');
assert(u.averageRecordText([8.26, 5.74, 0]) === '8.3–5.7' && u.averageRecordText([8.2, 5.6, 0.2]) === '8.2–5.6–0.2',
  'A5e. average record to one decimal');

// A6 — cells and dash rules.
const cells = (r, view) => u.VIEW_COLUMNS[view].map((c) => u.cellText(r, c));
assert(eq(cells(rows[3], 'record'), ['5–4', '8–6', '96%', '—']) && eq(cells(rows[3], 'points'), ['1,306', '1,589', '2,470']),
  'A6a. a forecast team fills the forecast columns (SoS is a dash: this fixture has no weeks)');
assert(eq(cells(rows[5], 'record'), ['1–8', '—', '—', '—']) && eq(cells(rows[5], 'points'), ['1,012', '—', '—']),
  'A6b. no forecast: W–L and PF still show; Proj. W–L, Playoffs, SoS, Proj. Max PF are a dash; unknown Max PF is a dash');
assert(u.cellText(rows[2], 'maxPf') === '1,640', "A6c. Max PF from the forecast when Sleeper sent no ppts");
{
  const noFc = u.buildTableRows(standingsRows, null);
  assert(u.cellText(noFc[0], 'maxPf') === '1,721' && u.cellText(noFc[2], 'maxPf') === '—',
    "A6d. with no forecast at all, Max PF still shows from Sleeper's ppts (dash only where Sleeper sent none)");
}

// A7 — the open team: one stat per row — what the current view leaves out, then the average.
{
  const S = (view, row, byes) => u.openTeamStats(view, row, byes).map((x) => `${x.label}=${x.value}`).join(' | ');
  const cases = [
    ['record', 3, 1, 'Points for=1306.0 | Max PF=1,589 | Projected Max PF=2,470 | Average final record=8.3–5.7 | Bye odds=3.3%',
      'A7a. Record view, forecast, byes: points for, Max PF, projected Max PF, average record, bye odds'],
    ['record', 3, 0, 'Points for=1306.0 | Max PF=1,589 | Projected Max PF=2,470 | Average final record=8.3–5.7',
      'A7b. no byes in the league ⇒ no Bye odds row'],
    ['points', 3, 1, 'Record=5–4 | Projected=8–6 | Playoff odds=96% | Average final record=8.3–5.7 | Bye odds=3.3%',
      'A7c. Points view, forecast, byes: record, projected record, playoff odds, average record, bye odds'],
    ['points', 3, 0, 'Record=5–4 | Projected=8–6 | Playoff odds=96% | Average final record=8.3–5.7',
      'A7d. Points view, no byes'],
    ['record', 5, 1, 'Points for=1011.5', 'A7e. Record view, no forecast and no Sleeper Max PF: points for only (no forecast rows, no bye row)'],
    ['points', 5, 1, 'Record=1–8', 'A7f. Points view, no forecast: the record only'],
    ['record', 2, 1, 'Points for=1391.7 | Max PF=1,640 | Projected Max PF=2,548 | Average final record=9.7–4.3 | Bye odds=3.3%',
      'A7g. Max PF row from the forecast fallback when Sleeper sent none'],
  ];
  for (const [view, i, byes, want, why] of cases) {
    const got = S(view, rows[i], byes);
    assert(got === want, why, `got ${got}`);
  }
  const noFc = u.buildTableRows(standingsRows, null);
  assert(S('record', noFc[0], 1) === 'Points for=1498.2 | Max PF=1,721',
    'A7h. no forecast at all: Sleeper Max PF still shows; no forecast-only rows');
  assert(u.openTeamStats('record', rows[3], 1).every((x) => !/[.:]$/.test(x.value) && !/ · /.test(x.value)),
    'A7i. values are bare numbers, no sentences or dot-joined lines');
  assert(typeof u.openTeamLines === 'undefined', 'A7j. the old string-joining openTeamLines is gone');
}

// A8 — the no-forecast line and the status words.
{
  const L = 'Projections aren’t available for this league yet.';
  const cases = [
    [{ enabled: false, isLoading: false, isError: false, state: undefined }, L, 'flag off: the plain line'],
    [{ enabled: true, isLoading: true, isError: false, state: undefined }, 'Loading projections…', 'loading'],
    [{ enabled: true, isLoading: false, isError: true, state: undefined }, `${L} Couldn’t check for an update.`, 'read failed'],
    [{ enabled: true, isLoading: false, isError: false, state: 'no_run' }, `${L} Waiting for the first weekly forecast.`, 'no run yet'],
    [{ enabled: true, isLoading: false, isError: false, state: undefined }, `${L} Waiting for the first weekly forecast.`, 'no state = no run'],
    [{ enabled: true, isLoading: false, isError: false, state: 'stale' }, `${L} Weekly update due.`, 'update due'],
    [{ enabled: true, isLoading: false, isError: false, state: 'unsupported_policy' }, `${L} This league’s rules aren’t supported yet.`, 'rules not supported'],
    [{ enabled: true, isLoading: false, isError: false, state: 'current' }, L, 'current state, no result: the plain line'],
    [{ enabled: true, isLoading: false, isError: false, state: 'mystery' }, `${L} Projection unavailable.`, 'unknown state'],
  ];
  const bad = cases.filter(([q, want]) => u.noForecastLine(q) !== want);
  assert(bad.length === 0, 'A8a. the no-forecast line uses the existing status words where a state applies',
    bad.map(([q, , why]) => `${why}: ${u.noForecastLine(q)}`).join(' | '));
  assert(u.forecastStatusText({ isLoading: false, isError: false, state: 'current' }) === '' &&
      u.forecastStatusText({ isLoading: false, isError: false, state: 'stale' }) === 'Weekly update due.',
    'A8b. a current forecast adds no status sentence; a stale one says so');
}

// A9 — SoS (strength of schedule) against a real league: "Fantasy Football
// Version 3", saved forecast captured 2026-11-24, week 11 completed, weeks
// 12–14 left (the display-mockups' values.json; each team's modeled_score_mean
// per remaining week, its opponent, and the expected mean / rank / band).
{
  const LEAGUE = [
    // [rid, name, w, l, pf, [[week, opponent, own modeled_score_mean]…], sos mean, rank, band]
    [1, 'Team 1', 7, 4, 1612.48, [[12, 5, 137.4], [13, 3, 148.0], [14, 4, 147.6]], 135.0, 5, 'average'],
    [2, 'Team 2', 3, 8, 1299.7, [[12, 10, 122.0], [13, 4, 121.7], [14, 9, 128.7]], 138.4, 4, 'hard'],
    [3, 'Team 3', 6, 5, 1557.2, [[12, 4, 153.4], [13, 1, 143.2], [14, 6, 139.2]], 143.0, 1, 'hard'],
    [4, 'Team 4', 7, 4, 1661.86, [[12, 3, 147.2], [13, 2, 149.5], [14, 1, 150.8]], 140.9, 2, 'hard'],
    [5, 'Team 5', 5, 6, 1196.52, [[12, 1, 111.0], [13, 6, 108.2], [14, 8, 113.0]], 140.2, 3, 'hard'],
    [6, 'Team 6', 6, 5, 1415.44, [[12, 7, 137.5], [13, 5, 133.8], [14, 3, 133.7]], 122.3, 11, 'easy'],
    [7, 'Team 7', 2, 9, 1317.36, [[12, 6, 119.6], [13, 8, 110.5], [14, 11, 118.7]], 128.9, 8, 'average'],
    [8, 'Team 8', 9, 2, 1572.92, [[12, 12, 143.6], [13, 7, 142.5], [14, 5, 149.5]], 122.7, 10, 'easy'],
    [9, 'Team 9', 9, 2, 1654.84, [[12, 11, 142.2], [13, 10, 131.0], [14, 2, 133.1]], 119.9, 12, 'easy'],
    [10, 'Team 10', 6, 5, 1349.0, [[12, 2, 132.7], [13, 9, 123.9], [14, 12, 135.5]], 131.4, 7, 'average'],
    [11, 'Team 11', 1, 10, 1174.76, [[12, 9, 107.1], [13, 12, 98.6], [14, 7, 106.6]], 131.8, 6, 'average'],
    [12, 'Team 12', 5, 6, 1408.46, [[12, 8, 144.7], [13, 11, 134.6], [14, 10, 141.3]], 125.9, 9, 'easy'],
  ];
  const byPlace = [...LEAGUE].sort((a, b) => (b[2] / 11 - a[2] / 11) || (b[4] - a[4]) || (a[0] - b[0]));
  const place = new Map(byPlace.map((t, i) => [t[0], i + 1]));
  const sRows = LEAGUE.map(([rid, name, w, l, pf]) => R(rid, name, place.get(rid), w, l, 0, pf, null));
  // Week 11 is played: a huge observed score that must not count. Opponent 99 is unknown.
  const fTeam = ([rid, , , , , weeks]) => ({
    ...F(rid, [9, 5, 0], [9, 5, 0], 0.5, 2000, 1500),
    weeks: [{ week: 11, opponent_roster_id: rid === 1 ? 2 : 1, modeled_score_mean: 999, actual_score_observed: true },
      ...weeks.map(([week, opp, mean]) => ({ week, opponent_roster_id: opp, modeled_score_mean: mean, actual_score_observed: false }))],
  });
  const fc = LEAGUE.map(fTeam);
  const lr = u.buildTableRows(sRows, fc);
  const bad = LEAGUE.filter(([rid, , , , , , mean, rank, band]) => {
    const r = lr.find((x) => x.rosterId === rid);
    return !r.sos || r.sos.mean.toFixed(1) !== mean.toFixed(1) || r.sos.rank !== rank ||
      r.sos.band !== (band === 'average' ? null : band) || u.cellText(r, 'sos') !== u.ordinal(rank);
  });
  assert(bad.length === 0, 'A9a. SoS = mean of each opponent\'s projected score that week over remaining weeks; ranks and hard / easy thirds match the review build',
    bad.map((t) => `${t[1]}: ${JSON.stringify(lr.find((x) => x.rosterId === t[0]).sos)}`).join('; '));
  assert(u.cellText(lr.find((r) => r.rosterId === 3), 'sos') === '1st' && u.cellText(lr.find((r) => r.rosterId === 9), 'sos') === '12th' &&
      ['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '111th'].join() === [1, 2, 3, 4, 11, 12, 13, 21, 22, 111].map(u.ordinal).join(),
    'A9b. the cell is an ordinal ("1st", "12th")');
  const ord = (dir, input = lr) => u.sortRows(input, { column: 'sos', dir }).map((r) => r.rosterId).join(',');
  assert(ord('desc') === '3,4,5,2,1,11,10,7,12,8,6,9' && ord('asc') === '9,6,8,12,7,10,11,1,2,5,4,3',
    'A9c. SoS sorts toughest first, then reversed', `${ord('desc')} / ${ord('asc')}`);
  assert(eq(u.nextSort(u.DEFAULT_SORT.record, 'sos'), { column: 'sos', dir: 'desc' }) && u.DEFAULT_SORT.record.column === 'wl',
    'A9d. the first tap on SoS sorts toughest first; Record still opens on W–L');

  // Dash cases: no forecast; no remaining weeks; an unknown opponent; the opponent's week missing.
  const fc2 = fc.map((t) => {
    if (t.roster_id === 1) return { ...t, weeks: t.weeks.map((w) => ({ ...w, actual_score_observed: true })) };
    if (t.roster_id === 2) return { ...t, weeks: t.weeks.map((w) => (w.week === 13 ? { ...w, opponent_roster_id: 99 } : w)) };
    if (t.roster_id === 4) return { ...t, weeks: t.weeks.filter((w) => w.week !== 12) }; // team 3 plays team 4 in week 12
    return t;
  }).filter((t) => t.roster_id !== 7);
  const dr = u.buildTableRows(sRows, fc2);
  const dash = (rid) => u.cellText(dr.find((r) => r.rosterId === rid), 'sos') === '—' && dr.find((r) => r.rosterId === rid).sos === null;
  assert(dash(7), 'A9e. no forecast for the team ⇒ dash');
  assert(dash(6) && dash(8) && dash(11), "A9e2. a team whose opponent has no forecast ⇒ dash (6, 8 and 11 play 7)");
  assert(dash(1), 'A9f. no remaining weeks (every week observed) ⇒ dash');
  assert(dash(2), 'A9g. an opponent missing from the forecast ⇒ dash');
  assert(dash(3), "A9h. the opponent's week missing ⇒ dash");
  assert(u.remainingScheduleMean({ ...fc[0], weeks: [] }, new Map()) === null, 'A9i. a team with no weeks has no SoS');
  {
    const ranked = dr.filter((r) => r.sos).sort((a, b) => a.sos.rank - b.sos.rank).map((r) => r.rosterId).join(',');
    const placeOf = (rid) => dr.find((r) => r.rosterId === rid).place;
    const dashes = dr.filter((r) => !r.sos).map((r) => r.rosterId).sort((a, b) => placeOf(a) - placeOf(b)).join(',');
    assert(ord('desc', dr) === `${ranked},${dashes}`, 'A9j. SoS desc: ranked teams toughest first, dashes last in standings order',
      `${ord('desc', dr)} vs ${ranked},${dashes}`);
    const rev = ranked.split(',').reverse().join(',');
    assert(ord('asc', dr) === `${rev},${dashes}`, 'A9k. SoS asc: easiest first, dashes still last in standings order', ord('asc', dr));
    assert(dr.filter((r) => !r.sos).length === 7 && dr.filter((r) => r.sos).map((r) => r.sos.rank).sort((a, b) => a - b).join() === '1,2,3,4,5',
      'A9l. teams with a dash take no rank; the rest rank 1..n');
    assert(dr.filter((r) => r.sos && r.sos.rank <= 4).every((r) => r.sos.band === 'hard') &&
        dr.filter((r) => r.sos && r.sos.rank > 8).length === 0 && dr.filter((r) => r.sos && r.sos.band === 'easy').length === 0,
      "A9m. thirds are of the league's team count (12): ranks 1–4 hard, 9–12 easy");
  }
  {
    // An exact tie: the lower roster id takes the higher rank (compute.py's order).
    const tie = u.buildTableRows([R(1, 'A', 2, 1, 0, 0, 10, null), R(2, 'B', 1, 1, 0, 0, 20, null)], [
      { ...F(1, [1, 0, 0], [1, 0, 0], 0.5, 0, 0), weeks: [{ week: 5, opponent_roster_id: 2, modeled_score_mean: 100 }] },
      { ...F(2, [1, 0, 0], [1, 0, 0], 0.5, 0, 0), weeks: [{ week: 5, opponent_roster_id: 1, modeled_score_mean: 100 }] },
    ]);
    assert(tie[0].sos.rank === 1 && tie[1].sos.rank === 2, 'A9n. an exact SoS tie ranks the lower roster id first');
  }
}

// ═══ B. The screen ══════════════════════════════════════════════════════
const ST_REL = 'src/screens/StandingsScreen.tsx';
const stRaw = read(ST_REL);
// Comments stripped, so prose about the old page cannot satisfy or trip a pin.
const st = stRaw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\{\s*\}/g, '{}');
const count = (hay, needle) => hay.split(needle).length - 1;
const styleBlock = (name) => (new RegExp(`\\n  ${name}: \\{[^\\n]*\\},`).exec(st) || new RegExp(`\\n  ${name}: \\{\\n[\\s\\S]*?\\n  \\},`).exec(st) || [''])[0];

// B1 — no segments.
assert(!/standings\.segment\./.test(st) && !/\bSegmentBtn\b/.test(st) && !/useState<Segment>/.test(st) &&
    !/\bsegment ===/.test(st), 'B1a. no Current | Projected segments, no segment state');
assert(!/useRoute|route\.params/.test(st), 'B1b. the screen never reads the route params (segment is accepted, not read)');

// B2 — the pill, on the caption line.
assert(/<ViewSeg label="Record" active=\{view === 'record'\} onPress=\{\(\) => selectView\('record'\)\} testID="standings\.view\.record" \/>/.test(st) &&
    /<ViewSeg label="Points" active=\{view === 'points'\} onPress=\{\(\) => selectView\('points'\)\} testID="standings\.view\.points" \/>/.test(st),
  'B2a. Record | Points pill: two segments, both through selectView');
assert(/useState<StandingsView>\('record'\)/.test(st), 'B2b. Record is the default view');
{
  const cap = st.indexOf('style={styles.captionRow}');
  const pill = st.indexOf('testID="standings.view-pill"');
  const table = st.indexOf('testID="standings.table"');
  assert(cap > 0 && pill > cap && table > pill, 'B2c. the pill sits on the caption line, above the table');
  assert(/borderRadius: radii\.pill/.test(styleBlock('pill')) && /borderColor: ice\.base/.test(styleBlock('segOn')),
    'B2d. specced pill construction: radii.pill outline, active segment ice-bordered');
}

// B3 — one table; headings sort through the util; per-view sort memory.
assert(count(st, 'testID="standings.table"') === 1 && !/standings\.current\.table/.test(st),
  'B3a. exactly one table');
assert(/testID=\{`standings\.sort\.\$\{column\}`\}/.test(st) && /<HeadCell column="team"/.test(st) &&
    /cols\.map\(\(c\) => \(\s*<HeadCell key=\{c\} column=\{c\}/.test(st),
  'B3b. every heading (Team included) is a sort button');
assert(/const \[sorts, setSorts\] = useState\(DEFAULT_SORT\);/.test(st) &&
    /setSorts\(\(s\) => \(\{ \.\.\.s, \[view\]: nextSort\(s\[view\], column\) \}\)\)/.test(st) &&
    /const sorted = useMemo\(\(\) => sortRows\(rows, sort\), \[rows, sort\]\);/.test(st),
  'B3c. each view keeps its own sort; tapping goes through nextSort; rows through sortRows');
assert(!/\.sort\(/.test(st), 'B3d. no local sorting arithmetic in the screen');
assert(/styles\.headActive/.test(st) && /headActive: \{ color: ice\.base \}/.test(st) &&
    /Icon name=\{sort\.dir === 'asc' \? 'chevron-up' : 'chevron-down'\} size=\{10\} color=\{ice\.base\}/.test(st),
  'B3e. the active heading is ice with an arrow');
assert(/numberOfLines=\{1\}>\s*\{r\.name\}/.test(st) && /num: \{ \.\.\.type\.data, textAlign: 'right', flexShrink: 0 \}/.test(st) &&
    !/<Text[^>]*numberOfLines[^>]*>\s*\{text\}/.test(st),
  'B3f. team names truncate (one line); number cells never shrink or truncate');
assert(/\{ width: COL_WIDTH\[column\], justifyContent: 'flex-end' \}/.test(st) && /\{ minWidth: COL_WIDTH\[c\] \}/.test(st),
  'B3g. headings are exactly the column width (long ones wrap); number cells are at least that wide');
{
  // Layout arithmetic, from the screen's own numbers. Record has five 4pt
  // gaps (team, four numbers, chevron), Points four.
  const W = Function(`return (${(/const COL_WIDTH: Record<StandingsColumn, number> = (\{[\s\S]*?\});/.exec(st) || ['', 'null'])[1]});`)();
  const chev = Number((/const CHEVRON = (\d+);/.exec(st) || [])[1]);
  const pad = /scroll: \{ padding: space\.lg,/.test(st) ? 16 : NaN; // space.lg
  const rowPad = /row: \{ paddingHorizontal: space\.xs,/.test(st) ? 4 : NaN; // space.xs
  const gap = /rowHead: \{ flexDirection: 'row', alignItems: 'center', gap: space\.xs,/.test(st) ? 4 : NaN;
  const team = (screen, v) => screen - 2 * pad - 2 * rowPad - chev - (u.VIEW_COLUMNS[v].length + 1) * gap
    - u.VIEW_COLUMNS[v].reduce((n, c) => n + W[c], 0);
  assert(chev === 16 && /chevronCol: \{ width: CHEVRON,/.test(st) && /size=\{CHEVRON\}/.test(st), 'B3h. the chevron column is 16pt');
  assert(eq([W.pf, W.maxPf, W.projMaxPf], [48, 60, 60]) && team(375, 'points') === 135,
    'B3i. Points view columns unchanged (48 / 60 / 60): the team keeps 135pt at 375pt');
  // Measured (Archivo 600 11pt +0.88 tracking, uppercase; Plex Mono 13pt = 7.8pt a character):
  // "W–L" 24.9, "PROJ." 38.0, "PLAY" 32.4, "OFFS" 32.9, "SoS" 23.9; caret 10 + 2.
  // Cells: "8–5–1" 39.0, "22–6" 31.2, ">99%" / "100%" 31.2, "12th" 31.2, "easy" 23.2.
  const need = { wl: Math.max(24.9 + 12, 5 * 7.8), projWl: Math.max(38.0 + 12, 5 * 7.8), playoffs: Math.max(32.9 + 12, 4 * 7.8), sos: Math.max(23.9 + 12, 4 * 7.8, 23.2) };
  const tight = Object.keys(need).filter((c) => W[c] < need[c] || W[c] > Math.ceil(need[c]) + 1);
  assert(tight.length === 0, 'B3j. each Record column is its widest cell or heading + caret, whichever is larger (≤ 1pt over)',
    tight.map((c) => `${c} ${W[c]} vs ${need[c]}`).join('; '));
  assert(team(375, 'record') === 125 && team(390, 'record') === 140 && team(393, 'record') === 143,
    'B3k. Record team column: 125pt at 375, 140 at 390, 143 at 393 (today 123 at 375 with three columns)',
    `${team(375, 'record')} / ${team(390, 'record')} / ${team(393, 'record')}`);
  // A 16-character name measured 102.4pt in body 14 (open, semi-bold: 106.9): it fits 125.
  assert(team(375, 'record') >= 107, 'B3l. a 16-character name (about 107pt open) fits at 375pt');
}

// B4 — the open team: one at a time, an outlined card.
{
  const card = styleBlock('rowOpen');
  assert(/borderWidth: 1,/.test(card) && /borderColor: ice\.base,/.test(card) && /borderBottomColor: ice\.base,/.test(card) &&
      /borderRadius: radii\.md,/.test(card) && /backgroundColor: ink\.ink2,/.test(card) && /marginVertical: space\.sm,/.test(card),
    'B4a. outlined card: 1pt ice border (the you row cannot override its bottom), radius 8, ink-2, a gap above and below', card);
  assert(!/shadow|elevation/i.test(st), 'B4b. no shadow anywhere on the page');
  assert(/isOpen && styles\.nameOpen/.test(st) && /nameOpen: \{ fontFamily: fonts\.uiSemi \}/.test(st) &&
      /color=\{isOpen \? ice\.base : chalk\.dim\}/.test(st),
    'B4c. the open team name is semi-bold and its chevron ice');
  assert(/const \[open, setOpen\] = useState<\{ leagueId: string; rosterId: number \} \| null>\(null\);/.test(st) &&
      /const openRosterId = open && open\.leagueId === leagueId \? open\.rosterId : null;/.test(st),
    'B4d. one open team, remembered with its league (a league switch closes it without an effect)');
  assert(/setOpen\(openRosterId === rosterId \|\| !leagueId \? null : \{ leagueId, rosterId \}\)/.test(st),
    'B4e. tapping the open team closes it; tapping another opens that one instead');
  const sel = (/const selectView = [\s\S]*?\n  \};/.exec(st) || [''])[0];
  assert(/setOpen\(null\);/.test(sel), 'B4f. switching view closes the open team');
  assert(/openTeamStats\(view, r, result\?\.playoff_byes \?\? 0\)/.test(st) &&
      /testID="standings\.open\.stats">\s*\{stats\.map\(\(x\) => <StatRow key=\{x\.label\} label=\{x\.label\} value=\{x\.value\} \/>\)\}/.test(st) &&
      !/openTeamLines|standings\.open\.(left-out|average)/.test(st) &&
      // Max PF moves (2026-11-12) adds the `maxPf` inputs; check-max-pf-moves.js pins them.
      // Playoff targets (2026-11-14) adds the `targets` inputs; check-playoff-targets.js pins them.
      // Improve pages (direction-pages spec P-13) add `pageLinks`; check-direction-pages.js pins it.
      /\{r\.forecast && result \? <ProjectionTeamDetail team=\{r\.forecast\} result=\{result\} maxPf=\{\{[^}]*\}\} targets=\{\{[^}]*\}\} pageLinks=\{pageLinks\} \/> : null\}/.test(st),
    'B4g. the open team shows one StatRow per util stat, then the moved forecast sub-sections');
  assert(/stats: \{ marginRight: space\.xs \+ CHEVRON \}/.test(st),
    "B4i. stat values end under the last number column (the chevron and its gap are kept clear)");
  assert(/paddingHorizontal: space\.xs - 1,/.test(card) && /row: \{ paddingHorizontal: space\.xs,/.test(st),
    "B4h. card border + padding = the closed row's padding, so columns do not move");
}

// B5 — under the table: the caption with its tags, the tiebreak note; footers and status sentences gone.
{
  const status = st.slice(st.indexOf('testID="standings.forecast-status"'), st.indexOf('testID="standings.no-forecast"'));
  assert(/lastSaved \? `Last saved: \$\{date\(result\.captured_at\)\}` : 'Weekly estimate'/.test(status) &&
      /incomplete \? 'Incomplete' : null/.test(status) && /result\.provisional \? 'Provisional' : null/.test(status),
    'B5a. the caption keeps Weekly estimate / Last saved with its Incomplete and Provisional tags');
  assert(count(status, '<Text') === 1, 'B5a2. with a forecast the caption is the only line (no status or incomplete sentence)');
  const GONE = ['Partial Sleeper data', 'VIEW_FOOT', 'Projected W–L is the most likely final record',
    'Odds don’t confirm a playoff spot', 'Max PF is the season so far', 'Projected Max PF is the forecast for the full regular season',
    'incompleteSentence', 'league-projections.incomplete', 'forecastStatusText'];
  const left = GONE.filter((g) => stRaw.includes(g));
  assert(left.length === 0, 'B5a3. removed: "Partial Sleeper data", the view footers, the status and incomplete sentences', left.join(', '));
  assert(st.includes('Your league’s own tiebreakers and divisions may order tied records differently.'),
    'B5a4. the tiebreak line stays');
  assert(st.includes("const lastSaved = !!result && (forecastQuery.isError || state !== 'current' || data?.model_current === false);"),
    'B5b. an older-model or failed-refresh run reads as last saved');
  assert(st.indexOf('testID="standings.forecast-status"') > st.indexOf('testID="standings.table"'),
    'B5c. the status line sits directly under the table');
  assert(!/Sort teams|Non-playoff picks|ProjectionToggle/.test(st), 'B5d. the Sort teams disclosure and Playoffs | Non-playoff picks toggle are gone');
  assert(/noForecastLine\(\{ enabled: forecastEnabled,/.test(st) && /testID="league-projections\.check"/.test(st),
    'B5e. no forecast: the util line under the table, plus Check for update (a re-read)');
}

// B6 — one shared forecast read; nothing on this page simulates.
assert(count(st, "queryKey: ['league-projection-batch', userId, leagueId]") === 1 &&
    /queryFn: \(\) => getLeagueProjectionBatch\(leagueId!\)/.test(st),
  "B6a. the forecast query keeps the shared key ['league-projection-batch', userId, leagueId]");
assert(/const forecastEnabled = batchProjections && isSleeper && !!leagueId && !!userId;/.test(st) &&
    /enabled: forecastEnabled,/.test(st) && /const batchProjections = useFlag\('league\.projections'\);/.test(st),
  'B6b. the read is gated on league.projections + Sleeper + league + user');
assert(!/getOutlook|league-outlook|outlook\.odds|SeasonOutlookSection|useMutation|api\.post|simulat/i.test(st.replace(/Stored batch reads only\. Opening standings never generates a forecast\./, '')),
  'B6c. no outlook (10,000-sim) request, no mutation, no simulation call on this page');
{
  const api = read('src/api/leagueProjections.ts');
  assert(!/api\.post|useMutation/.test(api) && /api\.get<ProjectionView>/.test(api),
    'B6d. the forecast client only reads (GET)');
  const banner = read('src/components/home/HomePlayoffBanner.tsx');
  assert(banner.includes("queryKey: ['league-projection-batch', userId, leagueId]"),
    "B6e. Home's / League rankings' tile reads the same key, so the three share one read");
}

// B7 — league switch.
assert(/const leagueId = useSession\(\(s\) => s\.league\?\.league_id\) \|\| null;/.test(st) &&
    /queryKey: \['league-rosters', leagueId\]/.test(st) && /queryKey: \['league-users', leagueId\]/.test(st),
  'B7a. every query is keyed by the session league (a switch reloads the table)');
assert(!/useEffect|useFocusEffect|useLayoutEffect/.test(st) && !/<ScrollView[^>]*\bkey=/.test(st),
  'B7b. no effect and no keyed remount: view and sort survive a league switch');

// B8 — FAB and header.
assert(count(st, '<FeedbackFAB') === 1 && /<FeedbackFAB activeScreen="Standings" aboveTabBar=\{false\} \/>/.test(st),
  'B8a. exactly one FeedbackFAB, activeScreen Standings, aboveTabBar false');
{
  const nav = read('src/navigation/RootNav.tsx');
  const block = (/<Stack\.Screen\s+name="Standings"[\s\S]*?\n        \/>/.exec(nav) || [''])[0];
  assert(/component=\{StandingsScreen\}/.test(block) && /<LeagueTopBarHeader\s+title="Standings"/.test(block) &&
      /<HeaderBack\s+testID="standings\.back-btn"/.test(block) &&
      /navigation\.canGoBack\(\)\s*\? navigation\.goBack\(\)\s*: navigation\.navigate\('Main'\)/.test(block),
    'B8b. the header is unchanged: LeagueTopBarHeader + HeaderBack standings.back-btn');
}

// B9 — analytics: the pill reuses standings_segment_changed; nothing else emits.
{
  const tracks = st.match(/\btrack\(/g) || [];
  const sel = (/const selectView = [\s\S]*?\n  \};/.exec(st) || [''])[0];
  assert(tracks.length === 1 && sel.includes("track('standings_segment_changed', { segment: next }, 'Standings');"),
    'B9a. exactly one emitter, in selectView, props {segment} on screen Standings');
  assert(sel.indexOf('if (next === view) return;') >= 0 &&
      sel.indexOf('if (next === view) return;') < sel.indexOf("track('standings_segment_changed'"),
    'B9b. a re-tap of the active view emits nothing');
  const tax = fs.readFileSync(path.join(MOBILE, '..', 'backend', 'analytics_taxonomy.py'), 'utf8');
  assert(/"standings_segment_changed":\s+frozenset\(\{"segment"\}\)/.test(tax) && /record \| points/.test(tax),
    'B9c. the taxonomy row is unchanged ({segment}) and registers the record | points values');
}

// B10 — callers no longer send { segment }; the route still accepts it.
{
  const callers = ['src/components/home/HomeHub.tsx', 'src/screens/LeagueSummaryScreen.tsx'];
  const sending = callers.filter((f) => /navigate\('Standings',/.test(read(f)));
  assert(sending.length === 0, 'B10a. no caller passes params to Standings', sending.join(', '));
  assert(/Standings: \{ segment\?: 'projected' \} \| undefined;/.test(read('src/navigation/RootNav.tsx')),
    "B10b. RootStackParamList still accepts the optional segment (installed builds, deep links)");
}

// B11 — LeagueProjectionSection is gone; its detail moved, its text unchanged.
{
  assert(!exists('src/components/LeagueProjectionSection.tsx'), 'B11a. LeagueProjectionSection.tsx is deleted');
  const srcFiles = [];
  const walk = (d) => fs.readdirSync(path.join(MOBILE, d), { withFileTypes: true }).forEach((e) =>
    e.isDirectory() ? walk(path.join(d, e.name)) : /\.tsx?$/.test(e.name) && srcFiles.push(path.join(d, e.name)));
  walk('src');
  const importers = srcFiles.filter((f) => /from '[./]*components\/LeagueProjectionSection'|from '\.\/LeagueProjectionSection'/.test(read(f)));
  assert(importers.length === 0, 'B11b. nothing imports it', importers.join(', '));
  const detail = read('src/components/LeagueProjectionDetail.tsx');
  // The middle section (Remaining schedule, replacing Weekly projections) is pinned by check-league-projections.js.
  assert(['label="Final record odds"', 'label="Draft pick odds"', 'label="Pick odds and range"']
    .every((l) => detail.includes(l)), 'B11c. the open team mounts Final record odds and Draft pick odds (with Pick odds and range)');
  assert(!/useQuery|useSession|useFlag/.test(detail), 'B11d. the detail reads nothing (the screen owns the one query)');
  assert(/disclosure: \{borderTopWidth: 1, borderTopColor: ink\.ink3\}/.test(detail) && /sections: \{paddingLeft: space\.md\}/.test(detail),
    'B11e. sub-sections are indented with a quieter separator');
}

// B12 — Chalkline.
assert(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(st), 'B12a. no hex or rgba literals');
assert(!/borderRadius: (?!radii\.(md|pill)\b)/.test(st), 'B12b. radii only md (8) and the specced pill');
assert(!/gradient|blur/i.test(st), 'B12c. no gradients or blur');
assert(/import Text from '\.\.\/components\/chalkline\/Text';/.test(st) && !/import \{[^}]*\bText\b[^}]*\} from 'react-native'/.test(st),
  'B12d. text goes through chalkline Text');
assert(!/styles\.odds\b/.test(st), 'B12e. numbers are not ice (ice is for interactive and selected states only)');

// B13 — package script + testIDs.
{
  const pkg = JSON.parse(read('package.json'));
  assert(pkg.scripts['test:standings-table'] === 'node tests/check-standings-table.js', 'B13a. npm run test:standings-table');
  for (const id of ['standings.screen', 'standings.view-pill', 'standings.view.record', 'standings.view.points',
    'standings.table', 'standings.forecast-status', 'standings.no-forecast', 'standings.current.unavailable']) {
    assert(stRaw.includes(`testID="${id}"`), `B13b. testID ${id} is a static literal`);
  }
}

// B14 — the SoS column and the heading caret.
{
  const head = (/function HeadCell[\s\S]*?\n\}\n/.exec(st) || [''])[0];
  assert(/\{isTeam \? null : caret\}\s*<Text/.test(head) && /<\/Text>\s*\{isTeam \? caret : null\}/.test(head),
    'B14a. number headings draw the caret LEFT of the text (text keeps the cells\' right edge); Team keeps it on the right');
  assert(/column === 'sos' && styles\.asWritten/.test(head) && /asWritten: \{ textTransform: 'none' \}/.test(st),
    'B14b. "SoS" is exempt from the label style\'s uppercase (never "SOS")');
  assert(/column === 'sos'\s*\? \(sort\.dir === 'desc' \? 'toughest first' : 'easiest first'\)/.test(head),
    'B14c. VoiceOver: the SoS sort says toughest / easiest first');
  assert(/if \(c === 'sos' && r\.sos\) \{/.test(st) && /\{r\.sos\.band \? <Text scale="dense" style=\{styles\.band\}>\{r\.sos\.band\}<\/Text> : null\}/.test(st) &&
      /band: \{ \.\.\.type\.bodySm, fontSize: type\.label\.fontSize, lineHeight: type\.label\.lineHeight, textAlign: 'right' \}/.test(st),
    'B14d. the SoS cell: the ordinal in the number style, "hard" / "easy" under it in small muted text');
  assert(!/sos[^\n]*(semantic|flare|ice\.)/.test(st), 'B14e. no colour coding on SoS');
  assert(/\$\{c === 'sos' && r\.sos\?\.band \? `, \$\{r\.sos\.band\}` : ''\}/.test(st), 'B14f. the row\'s spoken label includes the band');
  assert(/rowHead: \{ flexDirection: 'row', alignItems: 'center', gap: space\.xs, minHeight: 44 \}/.test(st), 'B14g. rows stay 44pt');
}

// B15 — StatRow (shared with LeagueProjectionDetail).
{
  const sr = read('src/components/StatRow.tsx');
  assert(/export function StatRow\(\{ label, value, mono = true, testID \}: \{\s*label: string;\s*value: string;\s*mono\?: boolean;\s*testID\?: string;\s*\}\)/.test(sr),
    'B15a. StatRow({label, value, mono = true, testID}) — the agreed signature');
  assert(/minHeight: 28,/.test(sr) && /borderTopColor: ink\.ink3,/.test(sr), 'B15b. 28pt minimum, the open card\'s quiet ink-3 separator');
  assert(/variant="bodySm" numberOfLines=\{1\} style=\{styles\.label\}/.test(sr) && /label: \{ flex: 1, minWidth: 0, color: chalk\.dim \}/.test(sr),
    'B15c. label: muted body-sm, one line, truncates');
  assert(/numberOfLines=\{1\} style=\{\[mono \? styles\.mono : styles\.text, styles\.value\]\}/.test(sr) && /value: \{ flexShrink: 0, textAlign: 'right' \}/.test(sr) &&
      /mono: \{ \.\.\.type\.data \}/.test(sr), 'B15d. value: right-aligned, never shrinks or wraps; Plex Mono unless mono={false}');
  assert(!/#[0-9a-fA-F]{3,8}\b|rgba?\(|borderRadius/.test(sr), 'B15e. tokens only');
}

console.log(failures ? `\n${failures} standings-table check(s) FAILED, ${passes} passed.` : `\nAll standings-table checks passed (${passes}).`);
process.exit(failures ? 1 : 0);
