#!/usr/bin/env node
// The Standings page's single table (docs/plans/home-engagement/
// scope-standings-table.md; operator 2026-11-12: "one row. W-L, Projected
// W-L, Playoff Odds %. A pill in the top right of the table to toggle to
// Points summary").
//
// PART A EXECUTES src/utils/standingsTable.ts (and standings.ts's Max PF
// reader) under plain node: sorting for every column in both directions with
// ties and dashes, the heading-tap rule, the number formats ("<1%", "100%",
// "1,498"), the no-forecast dash rules, which lines the open team shows in
// each view, and the no-forecast line.
//
// PART B PINS THE STRUCTURE of screens/StandingsScreen.tsx: no segments; the
// Record | Points pill; one table; the outlined open-team card; the old
// Projected status line still on the page; the shared forecast query key; no
// simulation or outlook request on open; league-switch behaviour; one
// FeedbackFAB; the LeagueTopBarHeader unchanged; the one analytics emitter;
// callers no longer send `{ segment }`; LeagueProjectionSection gone.
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
const load = (rel) => {
  const src = read(rel);
  const js = ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const m = { exports: {} };
  new Function('module', 'exports', 'require', js)(m, m.exports, () => {
    throw new Error(`${rel} must not require anything at runtime`);
  });
  return { src, mod: m.exports };
};
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ═══ A. The pure table ══════════════════════════════════════════════════
const { src: utilSrc, mod: u } = load('src/utils/standingsTable.ts');
const { mod: s } = load('src/utils/standings.ts');
assert(!/^\s*import\s+(?!type\b)/m.test(utilSrc), 'A0. standingsTable.ts has zero runtime imports');

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
  bye_probability: 0.033, maxpf_mean: maxMean, current_maxpf: curMax,
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
assert(eq(u.VIEW_COLUMNS, { record: ['wl', 'projWl', 'playoffs'], points: ['pf', 'maxPf', 'projMaxPf'] }),
  'A4d. Record = W–L · Proj. W–L · Playoffs; Points = PF · Max PF · Proj. Max PF');
assert(u.COLUMN_LABEL.projMaxPf === 'Proj.\nMax PF' && u.COLUMN_LABEL.projWl === 'Proj. W–L' &&
    u.COLUMN_LABEL.playoffs === 'Playoffs', 'A4e. headings; Proj. Max PF breaks after "Proj."');

// A5 — number formats.
const ODDS = [[0, '<1%'], [0.001, '<1%'], [0.00499, '<1%'], [0.005, '1%'], [0.0149, '1%'], [0.4, '40%'],
  [0.958, '96%'], [0.995, '99%'], [0.99949, '99%'], [0.9995, '100%'], [1, '100%']];
const badOdds = ODDS.filter(([p, want]) => u.oddsText(p) !== want);
assert(badOdds.length === 0, 'A5a. playoff odds: whole percent, under 0.5% "<1%", 99.95% and up "100%", else 1–99',
  badOdds.map(([p, w]) => `${p} → ${u.oddsText(p)} (want ${w})`).join('; '));
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
assert(eq(cells(rows[3], 'record'), ['5–4', '8–6', '96%']) && eq(cells(rows[3], 'points'), ['1,306', '1,589', '2,470']),
  'A6a. a forecast team fills all six columns');
assert(eq(cells(rows[5], 'record'), ['1–8', '—', '—']) && eq(cells(rows[5], 'points'), ['1,012', '—', '—']),
  'A6b. no forecast: W–L and PF still show; Proj. W–L, Playoffs, Proj. Max PF are a dash; unknown Max PF is a dash');
assert(u.cellText(rows[2], 'maxPf') === '1,640', "A6c. Max PF from the forecast when Sleeper sent no ppts");
{
  const noFc = u.buildTableRows(standingsRows, null);
  assert(u.cellText(noFc[0], 'maxPf') === '1,721' && u.cellText(noFc[2], 'maxPf') === '—',
    "A6d. with no forecast at all, Max PF still shows from Sleeper's ppts (dash only where Sleeper sent none)");
}

// A7 — the open team: what the current view leaves out, then the average.
{
  const rec = u.openTeamLines('record', rows[3], 1);
  assert(rec.leftOut === 'Points for 1306.0 · Max PF 1,589 · Projected Max PF 2,470',
    'A7a. Record view opens on what it leaves out: points for, Max PF, projected Max PF', rec.leftOut);
  assert(rec.average === 'Average final record: 8.3–5.7 · Bye odds: 3.3%',
    'A7b. then the exact average record (expected_record) and bye odds where the league has byes', rec.average);
  const pts = u.openTeamLines('points', rows[3], 0);
  assert(pts.leftOut === 'Record 5–4 · Projected 8–6 · Playoff odds 96%',
    'A7c. Points view opens on record, projected record and playoff odds', pts.leftOut);
  assert(pts.average === 'Average final record: 8.3–5.7', 'A7d. no byes ⇒ no bye odds', pts.average);
  const none = u.openTeamLines('record', rows[5], 1);
  assert(none.leftOut === 'Points for 1011.5' && none.average === null,
    'A7e. no forecast: only the current numbers that exist, and no average line', JSON.stringify(none));
  const nonePts = u.openTeamLines('points', rows[5], 1);
  assert(nonePts.leftOut === 'Record 1–8' && nonePts.average === null, 'A7f. Points view with no forecast: the record only');
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
  // Layout arithmetic for a 375pt phone, from the screen's own numbers.
  const W = Function(`return (${(/const COL_WIDTH: Record<StandingsColumn, number> = (\{[\s\S]*?\});/.exec(st) || ['', 'null'])[1]});`)();
  const pad = /scroll: \{ padding: space\.lg,/.test(st) ? 16 : NaN; // space.lg
  const rowPad = /row: \{ paddingHorizontal: space\.xs,/.test(st) ? 4 : NaN; // space.xs
  const gap = /rowHead: \{ flexDirection: 'row', alignItems: 'center', gap: space\.xs,/.test(st) ? 4 : NaN;
  const avail = 375 - 2 * pad - 2 * rowPad - 16 - 4 * gap;
  const team = (v) => avail - u.VIEW_COLUMNS[v].reduce((n, c) => n + W[c], 0);
  assert(avail === 303 && team('record') === 123 && team('points') === 135,
    'B3h. 375pt: 303pt for team + numbers; the team column keeps 123pt (Record) / 135pt (Points)',
    `avail ${avail}, record ${team('record')}, points ${team('points')}`);
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
  assert(/openTeamLines\(view, r, result\?\.playoff_byes \?\? 0\)/.test(st) &&
      /testID="standings\.open\.left-out">\{lines\.leftOut\}/.test(st) &&
      /\{r\.forecast && result \? <ProjectionTeamDetail team=\{r\.forecast\} result=\{result\} \/> : null\}/.test(st),
    'B4g. the open team shows the util lines, then the moved forecast sub-sections');
  assert(/paddingHorizontal: space\.xs - 1,/.test(card) && /row: \{ paddingHorizontal: space\.xs,/.test(st),
    "B4h. card border + padding = the closed row's padding, so columns do not move");
}

// B5 — the old Projected status line, still on the page.
{
  const status = st.slice(st.indexOf('testID="standings.forecast-status"'), st.indexOf('testID="standings.no-forecast"'));
  assert(/lastSaved \? `Last saved: \$\{date\(result\.captured_at\)\}` : 'Weekly estimate'/.test(status) &&
      /incomplete \? 'Incomplete' : null/.test(status) &&
      /result\.coverage\?\.estimated \? 'Partial Sleeper data' : null/.test(status) &&
      /result\.provisional \? 'Provisional' : null/.test(status) &&
      /testID="league-projections\.incomplete">\{incompleteSentence\(missingSlots\)\}/.test(status),
    'B5a. Weekly estimate / Last saved / Incomplete / Partial Sleeper data / Provisional + the incomplete sentence render with a forecast');
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
  assert(['label="Final record odds"', 'label="Weekly projections"', 'label="Draft pick odds"', 'label="Pick odds and range"']
    .every((l) => detail.includes(l)), 'B11c. the open team mounts Final record odds, Weekly projections, Draft pick odds');
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

console.log(failures ? `\n${failures} standings-table check(s) FAILED, ${passes} passed.` : `\nAll standings-table checks passed (${passes}).`);
process.exit(failures ? 1 : 0);
