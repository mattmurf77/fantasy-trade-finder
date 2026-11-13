#!/usr/bin/env node
// Max PF moves — the app side (flag `league.max_pf_moves`; contract
// docs/plans/league-projections/max-pf-trade-away/contract.md).
//
// EXECUTES src/utils/maxPfMoves.ts + src/utils/maxPfMovesCopy.ts under plain
// node against the contract's own §5 example payloads (parsed out of the
// contract file, so a payload edit there re-tests the app) and variants of
// them: every server state and `unavailable` reason renders its §10 string;
// default open / collapsed at 0.45 and by outlook; the pick-owner gate; the
// roster-changed drop; threshold filtering and 5-then-Show-all; Keep rows;
// §11 formatting; the mount rule; the hand-off calls; the four events'
// properties; the draft-order POST path and body.
//
// The copy table is compared with the contract's §10 table IN BOTH
// DIRECTIONS (every backticked string there is in the module, every module
// string is in the contract), so copy cannot drift from the contract.
//
// v1.1 (D-261, group O): every row listed in ready AND no_moves, C-NONE-ALONE
// exactly when nothing listed passes, the combined lines' strings, roster
// dropping and Keep, no Find trades on a combined line, an old block (no
// `combined`) rendering as before, and the two new viewed props.
//
// SOURCE PINS cover what cannot be executed: StandingsScreen's flag read and
// props, the detail mounting the section after Draft pick odds on the own
// card only, no extra request on open, the component's track calls, the
// popTo hand-off, testIDs, 44pt rows, mono numbers, Chalkline.
//
// Run: node tests/check-max-pf-moves.js
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
const show = (v) => JSON.stringify(v);

const transpile = (src) => ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const run = (rel, requireFn) => {
  const m = { exports: {} };
  new Function('module', 'exports', 'require', transpile(read(rel)))(m, m.exports, requireFn);
  return m.exports;
};
const copySrc = read('src/utils/maxPfMovesCopy.ts');
const utilSrc = read('src/utils/maxPfMoves.ts');
const copyMod = run('src/utils/maxPfMovesCopy.ts', (r) => { throw new Error(`copy module requires ${r}`); });
const u = run('src/utils/maxPfMoves.ts', (r) => {
  if (r === './maxPfMovesCopy') return copyMod;
  throw new Error(`maxPfMoves.ts must not require ${r} at runtime`);
});
const C = copyMod.MAXPF_COPY;

const contract = fs.readFileSync(path.join(ROOT, 'docs/plans/league-projections/max-pf-trade-away/contract.md'), 'utf8');
const section = (head, next) => contract.slice(contract.indexOf(head), contract.indexOf(next));

// ── Fixtures: the contract's §5 example payloads, parsed from the file ──
const examples = [...section('## 5. Example payloads', '## 6.').matchAll(/```json\n([\s\S]*?)```/g)]
  .map((m) => JSON.parse(m[1]).max_pf_moves);
const [READY, UNAVAILABLE, NOT_MAXPF, NO_MISS] = examples;
const clone = (o) => JSON.parse(JSON.stringify(o));
const withBlock = (base, patch) => Object.assign(clone(base), patch);
const R1 = READY.rows[0];
const R2 = READY.rows[1];
const R3 = READY.rows[2];

// ═══ A. Copy: verbatim with the contract, never "tank" ═══════════════════
{
  assert(examples.length === 4 && READY.state === 'ready' && UNAVAILABLE.state === 'unavailable'
      && NOT_MAXPF.state === 'draft_order_not_maxpf' && NO_MISS.state === 'no_miss',
    'A0. the four §5 example payloads parse from the contract');
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
  // Worked examples in the contract are checked as OUTPUTS (group H), not templates.
  const EXAMPLES = ['An empty spot starts instead (1 week).'];
  const values = new Set(Object.values(C));
  const missing = [...contractStrings].filter((s) => !values.has(s) && !EXAMPLES.includes(s));
  assert(rows.length === 48 && missing.length === 0, 'A1. every §10 string is in the copy module verbatim', missing.join(' | '));
  const extra = [...values].filter((s) => !contractStrings.has(s));
  assert(extra.length === 0, 'A2. every copy-module string is a §10 string', extra.join(' | '));
  const sources = [copySrc, utilSrc, read('src/components/MaxPfMovesSection.tsx')];
  assert(sources.every((s) => !/tank/i.test(s)), 'A3. the word "tank" appears nowhere in the copy, util or component');
  assert(!/^\s*import\s/m.test(copySrc), 'A4. the copy module has zero imports');
  assert(!/^\s*import\s+(?!type\b)(?![^;]*from '\.\/maxPfMovesCopy')/m.test(utilSrc),
    'A5. maxPfMoves.ts imports only types and the copy module');
  assert(!/'(Max PF moves|Show all|Show anyway|Show moves|Keep|Change)'/.test(read('src/components/MaxPfMovesSection.tsx'))
      && /MAXPF_COPY\['C-TITLE'\]/.test(read('src/components/LeagueProjectionDetail.tsx')),
    'A6. the component and detail render copy from the module, not inline literals');
}

// ═══ B. Every server state and unavailable reason → its §10 line ═════════
{
  const lineFor = (state, reason = null) => u.stateLine(withBlock(READY, { state, reason }));
  assert(lineFor('season_over') === C['C-SEASON-OVER'] && lineFor('after_trade_deadline') === C['C-DEADLINE']
      && lineFor('draft_order_not_maxpf') === C['C-NOT-MAXPF'] && lineFor('no_miss') === C['C-NO-MISS'],
    'B1. season_over / after_trade_deadline / draft_order_not_maxpf / no_miss render their lines');
  assert(lineFor('ready') === null && lineFor('no_moves') === null, 'B2. ready / no_moves have no one-line state');
  const reasons = ['no_forecast', 'update_pending', 'refresh_failed', 'stale', 'old_model', 'incomplete',
    'team_not_found', 'unsupported', 'missing_projections', 'read_failed', 'not_computed'];
  const bad = reasons.filter((r) => lineFor('unavailable', r) !== C[`C-U-${r}`]);
  assert(bad.length === 0, 'B3. each of the 11 unavailable reasons renders its C-U line', bad.join(', '));
  assert(lineFor('unavailable', 'brand_new_reason') === C['C-U-other'] && lineFor('unavailable', null) === C['C-U-other']
      && lineFor('unavailable', 'toString') === C['C-U-other'],
    'B4. an unknown or null reason uses the generic line (open set)');
  assert(u.stateLine(UNAVAILABLE) === 'The saved forecast is from an earlier week. Max PF moves return after the next weekly update.',
    'B5. §5.2 (stale) renders its exact sentence');
  const m = u.deriveSection(NOT_MAXPF, null);
  assert(m.line === C['C-NOT-MAXPF'] && eq(m.order, { text: null, link: 'Change answer' }) && m.baseline === null
      && m.listed.length === 0 && !m.isList, 'B6. §5.3 shows its line + "Change answer" and no list');
  const nm = u.deriveSection(NO_MISS, null);
  assert(nm.line === C['C-NO-MISS'] && nm.baseline === null && nm.listed.length === 0 && !nm.ownerGate,
    'B7. §5.4 no_miss shows one line and no list (the owner gate is not a no_miss state)');
  const un = u.deriveSection(UNAVAILABLE, null);
  assert(un.order === null && un.baseline === null && !un.questionEligible, 'B8. unavailable: no order link, no baseline, no question');
}

// ═══ C. Default open / collapsed (§6.1) ══════════════════════════════════
{
  const at = (p, outlook) => withBlock(READY, { saved_outlook: outlook,
    baseline: Object.assign(clone(READY.baseline), { playoff_probability: p }) });
  assert(u.defaultOpen(at(0.45, null)) === true && u.initialOpen(at(0.45, null)) === true,
    'C1. playoff chance exactly 0.45 ⇒ open (inclusive)');
  assert(u.defaultOpen(at(0.4500001, null)) === false && u.initialOpen(at(0.4500001, 'contender')) === false,
    'C2. just above 0.45 with no / contender outlook ⇒ collapsed');
  assert(u.defaultOpen(at(0.9, 'rebuilder')) && u.defaultOpen(at(0.9, 'jets'))
      && !u.defaultOpen(at(0.9, 'championship')) && !u.defaultOpen(at(0.9, 'not_sure')),
    'C3. saved outlook rebuilder / jets ⇒ open regardless of chance; others do not');
  const col = u.deriveSection(at(0.62, 'contender'), null);
  assert(col.collapsedLine === 'Your team makes the playoffs in 62% of simulations. Moving these players lowers that.'
      && C['C-COLLAPSED.button'] === 'Show moves', 'C4. collapsed shows C-COLLAPSED with the playoff % and Show moves');
  assert(u.initialOpen(withBlock(NO_MISS, { pick_owner: { owns_own_pick: true, owner_roster_id: 3, owner_name: 'x' } })) === false
      && u.deriveSection(READY, null).collapsedLine === null, 'C5. only ready / no_moves start open; an open section has no collapsed line');
}

// ═══ D. Pick owned by another team (§6.2) ════════════════════════════════
{
  const owned = withBlock(READY, { pick_owner: { owns_own_pick: false, owner_roster_id: 9, owner_name: 'Saltmarsh Owls' } });
  const m = u.deriveSection(owned, null);
  assert(m.ownerGate === true && m.initialOpen === false && m.defaultOpen === true,
    'D1. owns_own_pick false on ready ⇒ gated and starts closed even when default-open');
  assert(m.ownerLine === 'Saltmarsh Owls owns your 2027 1st, so lowering your max PF improves their pick.'
      && C['C-OWNER.button'] === 'Show anyway', 'D2. C-OWNER names the owner and season, with Show anyway');
  assert(u.ownerGateActive(withBlock(owned, { state: 'no_moves' })) && !u.ownerGateActive(NO_MISS),
    'D3. the gate applies to no_moves too, never to other states');
  const comp = read('src/components/MaxPfMovesSection.tsx');
  assert(/const gated = model\.isList && !revealed && \(model\.ownerGate \|\| !model\.defaultOpen\);/.test(comp)
      && /model\.ownerGate \? model\.ownerLine : model\.collapsedLine/.test(comp),
    'D4. the body shows the owner line before the collapsed line, and the list only after the tap');
}

// ═══ E. Roster changed since the forecast (§6.3) ═════════════════════════
{
  const saved = READY.roster_player_ids;
  assert(u.rosterChanged(READY, [...saved].reverse()) === false && u.rosterChanged(READY, null) === false,
    'E1. same roster (any order) or no live roster yet ⇒ no notice');
  const live = saved.filter((id) => id !== '8150').concat('99999');
  const m = u.deriveSection(READY, live);
  assert(m.rosterChanged && m.rosterLine === C['C-ROSTER'] && eq(m.listed.map((r) => r.rank), [2, 3]),
    'E2. a traded-away player drops his row and C-ROSTER shows; the others stay', show(m.listed.map((r) => r.rank)));
  assert(m.listed[0].maxpf_change === -28 && m.listed[0].pick_if_miss.after === 3.3887,
    'E3. numbers on the remaining rows are shown unchanged');
  const gone = u.deriveSection(READY, saved.filter((id) => id !== '8150' && id !== '6130' && id !== '11233'));
  assert(gone.listed.length === 0 && gone.rosterLine === C['C-ROSTER'] && gone.noMovesLine === null
      && gone.noneAloneLine === null && gone.combined.length === 0
      && gone.head === null && gone.foot === null, 'E4. every row dropped ⇒ C-ROSTER only');
  assert(u.rosterChanged(withBlock(READY, { state: 'no_miss' }), ['1']) === false,
    'E5. the check applies to ready / no_moves only');
  const st = read('src/screens/StandingsScreen.tsx');
  assert(/findMyRoster\(rosters, userId\)\?\.players \?\? null/.test(st) && /\[rostersQuery\.data, userId\]/.test(st),
    "E6. the live roster is the page's existing ['league-rosters'] query (no new request)");
}

// ═══ F. Threshold filtering and 5-then-Show-all (§6.5) ═══════════════════
{
  const m = u.deriveSection(READY, READY.roster_player_ids);
  assert(eq(m.listed.map((r) => r.rank), [1, 2, 3]), 'F1. v1.1: §5.1 lists every row, passing or not (rank 3 fails the threshold)');
  const many = withBlock(READY, { rows: Array.from({ length: 8 }, (_, i) =>
    Object.assign(clone(R1), { rank: 8 - i, player_id: `p${i}`, passes_threshold: true })) });
  const listed = u.listedRows(many, null);
  assert(eq(listed.map((r) => r.rank), [1, 2, 3, 4, 5, 6, 7, 8]), 'F2. listed rows are in rank order');
  const first = u.visibleRows(listed, false);
  const all = u.visibleRows(listed, true);
  assert(first.rows.length === 5 && first.showAllButton && all.rows.length === 8 && !all.showAllButton,
    'F3. 8 passing rows ⇒ 5 shown + Show all; Show all reveals all 8');
  const five = u.visibleRows(listed.slice(0, 5), false);
  assert(five.rows.length === 5 && !five.showAllButton && C['C-SHOWALL'] === 'Show all', 'F4. exactly 5 ⇒ no Show all');
  const nm = u.deriveSection(withBlock(READY, { state: 'no_moves', rows: [], combined: [] }), null);
  assert(nm.listed.length === 0 && nm.noMovesLine === C['C-NO-MOVES'] && nm.baseline !== null && nm.head === null
      && nm.noneAloneLine === null, 'F5. a list state with zero rows: baseline + C-NO-MOVES, no list');
  assert(eq(u.listedRows(withBlock(READY, { state: 'no_moves' }), null).map((r) => r.rank), [1, 2, 3]),
    'F6. v1.1: no_moves lists its rows too');
  assert(m.head === 'Max PF change over the remaining 5 weeks' && m.foot === C['C-FOOT'], 'F7. a listed row brings C-HEAD and C-FOOT');
}

// ═══ G. Keep rows ════════════════════════════════════════════════════════
{
  const d2 = u.rowDetail(R2);
  assert(R2.keep === true && d2.button === null
      && d2.keepNote === 'You marked D. Okafor Keep, so Find trades is off for this player.',
    'G1. a Keep row has no Find trades button and shows C-KEEP-NOTE');
  const d1 = u.rowDetail(R1);
  assert(d1.button === 'Find trades for R. Sato' && d1.keepNote === null, 'G2. a non-Keep row has the button');
  const calls = [];
  const did = u.handOffToFinder(R2, { setSide: () => calls.push('s'), track: () => calls.push('t'), navigate: () => calls.push('n'), now: () => calls.push('c') });
  assert(did === false && calls.length === 0, 'G3. the hand-off refuses a Keep row (no pin, no event, no prefill, no navigation)');
  const comp = read('src/components/MaxPfMovesSection.tsx');
  assert(/\{row\.keep \? <Badge label=\{C\['C-KEEP'\]\} \/> : null\}/.test(comp)
      && /\{d\.button \? <Button/.test(comp) && /\{d\.keepNote \?/.test(comp),
    'G4. the row shows the Keep tag; the opened row renders the button or the note from rowDetail');
}

// ═══ H. Formatting (§11) ═════════════════════════════════════════════════
{
  const M = '−';
  assert(u.formatPoints(-31) === `${M}31` && u.formatPoints(0) === '0' && u.formatPoints(-4) === `${M}4`,
    'H1. row change: whole number, U+2212, 0 as 0');
  assert(u.formatWeekChange(-7) === `${M}7.0` && u.formatWeekChange(-4.2) === `${M}4.2`,
    'H2. week change: one decimal, U+2212');
  assert(u.formatWeekChange(3.2) === '+3.2' && u.formatWeekChange(0.04) === '0' && u.formatWeekChange(0) === '0'
      && u.formatWeekChange(-0.04) === '0', 'H2b. a positive week change is "+3.2"; exactly 0 (one decimal) is "0"');
  assert(u.formatPoints(3) === '+3' && u.formatPoints(12.6) === '+13' && u.formatPoints(0) === '0',
    'H2c. a positive row change (e.g. lineup_change) is "+n"; 0 is "0"');
  const posWeek = u.weekLines(Object.assign(clone(R1), { weeks: [{ week: 12, status: 'changed', maxpf_change: 3.2, lineup_change: 3.2,
    replaced_by: [{ player_id: '20391', name: 'Ike Brennan', short_name: 'I. Brennan', free_agent: true }] }] }));
  assert(eq(posWeek, ['Week 12: +3.2, Ike Brennan (free agent) instead']), 'H2d. C-WEEK reads "Week 12: +3.2, Name instead" for a positive week', show(posWeek));
  assert(u.baselineLine(READY).indexOf('+') === -1 && u.rowLine2(R1, false).indexOf('+') === -1
      && u.formatPick(3.7) === '3.7' && u.formatValue(2480) === '2,480',
    'H2e. levels (pick if you miss, baseline value, percentages) never gain a "+"');
  assert(u.formatPick(3.6912) === '3.7' && u.formatPick(3.3604) === '3.4' && u.formatPick(null) === '—',
    'H3. pick if you miss: one decimal; null ⇒ —');
  const pct = [[0.4583, '46%'], [0.6177, '62%'], [0.0271, '3%'], [0.0122, '1%'], [0.004, '<1%'], [0.005, '1%'],
    [0.285, '29%'], [0.125, '13%'], [0.995, '>99%'], [0.9949, '99%'], [0, '0%'], [1, '100%'], [0.9997, '>99%']];
  const badPct = pct.filter(([p, s]) => u.formatPct(p) !== s).map(([p, s]) => `${p}→${u.formatPct(p)} (want ${s})`);
  assert(badPct.length === 0, 'H4. percent: whole, half up, <1%, >99%, exact 0% / 100%', badPct.join(', '));
  assert(u.formatValue(2480.4) === '2,480' && u.formatValue(1214) === '1,214' && u.formatValue(999.5) === '1,000',
    'H5. baseline value: whole number with thousands separator');
  assert(u.formatValueChange(169.2) === '+169' && u.formatValueChange(-12.6) === `${M}13` && u.formatValueChange(1234.5) === '+1,235',
    'H6. value change: leading + or −, thousands separator');
  assert(u.formatValueChange(0) === '0' && u.formatValueChange(0.4) === '0' && u.formatValueChange(-0.4) === '0'
      && u.formatPoints(-0.4) === '0', 'H6b. a change of exactly 0 (after rounding) is "0", never "+0" or "−0"');
  assert(u.ARROW === ' → ', 'H7. arrows are " → " (U+2192 with spaces)');
  const base = u.baselineLine(READY);
  assert(base === 'Your 2027 1st today: 1.02 projected. If you miss the playoffs, pick 3.7 on average. 46% chance of a top-3 pick. Value 2,480.',
    'H8. C-BASE for §5.1, priced', base);
  const unpriced = withBlock(READY, { baseline: Object.assign(clone(READY.baseline), { pick_value: null, pick_value_status: 'not_priced' }) });
  assert(u.baselineLine(unpriced) === 'Your 2027 1st today: 1.02 projected. If you miss the playoffs, pick 3.7 on average. 46% chance of a top-3 pick.'
      && !u.deriveSection(unpriced, null).priced, 'H9. not_priced hides the baseline value');
  const nolabel = withBlock(READY, { baseline: Object.assign(clone(READY.baseline), { label: null }) });
  assert(u.baselineLine(nolabel) === 'Your 2027 1st: If you miss the playoffs, pick 3.7 on average. 46% chance of a top-3 pick. Value 2,480.',
    'H10. label null ⇒ "Your {season} 1st:" and the rest unchanged', u.baselineLine(nolabel));
  assert(u.rowLine1(R1) === `R. Sato  RB  ${M}31` && u.rowLine2(R1, true) === 'Pick if you miss 3.7 → 3.4 · Value +169'
      && u.rowLine2(R1, false) === 'Pick if you miss 3.7 → 3.4', 'H11. C-ROW-1 / C-ROW-2 (value only when priced)');
  const noAfter = Object.assign(clone(R1), { pick_if_miss: { now: 3.6912, after: null }, pick_value: null });
  assert(u.rowLine2(noAfter, true) === 'Pick if you miss 3.7 → —', 'H12. after null ⇒ — ; a null row value is hidden');
  const d1 = u.rowDetail(R1);
  assert(d1.top3 === 'Top-3 chance 46% → 62%' && d1.playoff === 'Playoff chance 3% → 1%'
      && d1.label === 'Projected pick 1.02, unchanged', 'H13. opened row: top-3, playoff, unchanged label');
  const moved = Object.assign(clone(R1), { label: { now: '1.04', after: '1.02' } });
  assert(u.rowDetail(moved).label === 'Projected pick 1.04 → 1.02'
      && u.rowDetail(Object.assign(clone(R1), { label: { now: '1.04', after: null } })).label === null,
    'H14. label pair when changed; no label line when one is null');
  assert(d1.replacement === 'Cal Mercer starts instead (4 weeks), Ezra Quill (1 week).',
    'H15. several replacements: weeks per name, "1 week" singular', d1.replacement);
  assert(u.rowDetail(R2).replacement === 'Cal Mercer starts instead. Bye in week 12.',
    'H16. one replacement every affected week ⇒ C-REPL-1, then the bye', u.rowDetail(R2).replacement);
  assert(u.rowDetail(R3).replacement === 'Ike Brennan (free agent) starts instead.', 'H17. a free agent is marked');
  const empty = Object.assign(clone(R3), { weeks_affected: 2, replacements: [{ player_id: null, name: null, short_name: null, free_agent: false, weeks: 1 }] });
  assert(u.replacementLine(empty) === 'An empty spot starts instead (1 week).', 'H18. empty spot, capitalised first (the contract example)');
  const more = Object.assign(clone(R1), {
    replacements: [
      { player_id: '1', name: 'Ann Ash', short_name: 'A. Ash', free_agent: false, weeks: 2 },
      { player_id: null, name: null, short_name: null, free_agent: false, weeks: 1 },
      { player_id: '3', name: 'Cy Cole', short_name: 'C. Cole', free_agent: true, weeks: 1 },
    ], replacements_more: 2 });
  assert(u.replacementLine(more) === 'Ann Ash starts instead (2 weeks), an empty spot (1 week), Cy Cole (free agent) (1 week) and 2 more.',
    'H19. up to 3 names then " and k more."', u.replacementLine(more));
  const byes = (ws) => u.byeLine(Object.assign(clone(R1), { weeks: ws.map((w) => ({ week: w, status: 'bye', maxpf_change: 0, lineup_change: 0, replaced_by: [] })) }));
  assert(byes([12]) === 'Bye in week 12.' && byes([5, 9]) === 'Byes in weeks 5 and 9.' && byes([5, 9, 12]) === 'Byes in weeks 5, 9 and 12.'
      && byes([]) === null, 'H20. byes: singular, two, three');
  const wl = u.weekLines(Object.assign(clone(R3), { weeks: R3.weeks.concat([
    { week: 15, status: 'played', maxpf_change: 0, lineup_change: 0, replaced_by: [] },
    { week: 16, status: 'bye', maxpf_change: 0, lineup_change: 0, replaced_by: [] },
    { week: 17, status: 'not_projected', maxpf_change: 0, lineup_change: 0, replaced_by: [] }]) }));
  assert(eq(wl, ['Week 10: no change', `Week 11: ${M}4.2, Ike Brennan (free agent) instead`, 'Week 12: no change',
    'Week 13: no change', 'Week 14: no change', 'Week 15: already played', 'Week 16: bye']),
  'H21. C-WEEK for changed / no change / already played / bye; reserved not_projected is skipped', show(wl));
  const one = withBlock(READY, { baseline: Object.assign(clone(READY.baseline), { weeks_remaining: 1 }) });
  assert(u.headLine(one) === 'Max PF change over the final week', 'H22. one week left ⇒ "over the final week"');
}

// ═══ I. The mount rule: own card, flag AND block (§4.3, §8) ══════════════
{
  const ok = { block: READY, flagOn: true, isSleeper: true, ownCard: true };
  assert(u.sectionMounts(ok) === true, 'I1. flag on + block + Sleeper + own card ⇒ mounts');
  const offs = [
    ['flag off', { flagOn: false }], ['no block', { block: undefined }], ['other team', { ownCard: false }],
    ['not Sleeper', { isSleeper: false }], ['unknown version', { block: withBlock(READY, { version: 2 }) }],
    ['unknown state', { block: withBlock(READY, { state: 'brand_new' }) }]];
  const leaked = offs.filter(([, p]) => u.sectionMounts(Object.assign({}, ok, p))).map(([n]) => n);
  assert(leaked.length === 0, 'I2. any one missing ⇒ nothing renders', leaked.join(', '));
  assert(u.isOwnCard(7, 7, READY) && !u.isOwnCard(3, 7, READY) && u.isOwnCard(7, undefined, READY) && !u.isOwnCard(7, null, null),
    "I3. own card = team.roster_id === result.viewer_roster_id (block's id as fallback)");
  const st = read('src/screens/StandingsScreen.tsx');
  assert(/const maxPfMovesOn = useFlag\('league\.max_pf_moves'\);/.test(st)
      && /maxPf=\{\{\s*block: data\?\.max_pf_moves, flagOn: maxPfMovesOn, isSleeper, liveRosterIds, leagueId, userId,\s*\}\}/.test(st),
    "I4. Standings reads the flag the app's way (useFlag) and passes the block from the one forecast read");
  const det = read('src/components/LeagueProjectionDetail.tsx');
  const draftIdx = det.indexOf('label="Draft pick odds"');
  const movesIdx = det.indexOf("{moves ? <Disclosure label={MAXPF_COPY['C-TITLE']}");
  assert(draftIdx > 0 && movesIdx > draftIdx && /ownCard: isOwnCard\(team\.roster_id, result\.viewer_roster_id, maxPf\.block\)/.test(det)
      && /initialOpen=\{moves\.model\.initialOpen\}/.test(det),
    'I5. the detail mounts "Max PF moves" after Draft pick odds, only through sectionMounts with the own-card rule');
  assert(/function Disclosure\(\{label, children, testID, initialOpen = false\}/.test(det) && /useState\(initialOpen\)/.test(det),
    'I6. the existing Disclosure is reused; it gains initialOpen (default closed, others unchanged)');
}

// ═══ J. The Find trades hand-off (§12) ═══════════════════════════════════
{
  const calls = [];
  const did = u.handOffToFinder(R1, {
    setSide: (side, players) => calls.push(['setSide', side, players]),
    track: (e, p, s) => calls.push(['track', e, p, s]),
    navigate: (params) => calls.push(['navigate', params]),
    now: () => 1731430000000,
  });
  const NAV = { screen: 'Trades', params: { screen: 'TradesHome',
    params: { canvasPrefill: { give: ['8150'], receive: [] }, canvasPrefillSeq: 1731430000000 }, pop: true } };
  assert(did === true && eq(calls, [
    ['setSide', 'give', [{ id: '8150', name: 'Rhett Sato', position: 'RB' }]],
    ['setSide', 'receive', []],
    ['track', 'finder_target_pinned', { side: 'give', source: 'maxpf_moves' }, 'Standings'],
    ['navigate', NAV],
  ]), 'J1. give := [player], receive := [], finder_target_pinned {side, source}, then navigate with the canvas prefill', show(calls));
  const p = calls[3] && calls[3][1] && calls[3][1].params;
  assert(p && p.screen === 'TradesHome' && p.pop === true && eq(p.params.canvasPrefill, { give: ['8150'], receive: [] })
      && !('opponentId' in p.params.canvasPrefill) && typeof p.params.canvasPrefillSeq === 'number',
    'J1b. canvasPrefill = {give: [player id], receive: []} (ids, no partner), a fresh canvasPrefillSeq, pop back to TradesHome');
  const comp = read('src/components/MaxPfMovesSection.tsx');
  assert(/setSide: \(side, players\) => useFinderTargets\.getState\(\)\.setSide\(side, players\)/.test(comp)
      && /navigate: \(params\) => navigation\.popTo\('Main', params\),\s*now: Date\.now,/.test(comp),
    'J2. the component wires the store and pops to Main with the util-built params (Standings is a root push)');
  assert(!/setHandoff|autoRun|beginTradeSearch/.test(comp + utilSrc), 'J3. no hand-off object, no auto-run, no R1 search start');
  const trades = read('src/screens/TradesScreen.tsx');
  assert(/const p = route\?\.params\?\.canvasPrefill as CanvasPrefill \| undefined;\s*if \(!inlineHomeOn \|\| !p\) return;\s*loadCanvasPrefill\(p\);\s*navigation\?\.setParams\?\.\(\{ canvasPrefill: undefined, canvasPrefillSeq: undefined \}\);[\s\S]{0,120}\}, \[route\?\.params\?\.canvasPrefillSeq\]\);/.test(trades)
      && /export interface CanvasPrefill \{\s*opponentId\?: string;\s*give: string\[\];\s*receive: string\[\];/.test(read('src/components/TradeBuildCanvas.tsx')),
    'J4. the receiving side is unchanged: TradesScreen consumes canvasPrefill once per canvasPrefillSeq and clears it; CanvasPrefill takes id lists');
}

// ═══ K. Analytics (§9) ═══════════════════════════════════════════════════
{
  const m = u.deriveSection(READY, null);
  assert(eq(u.viewedProps(READY, m), { state: 'ready', n_moves: 2, band: 'jets', n_listed: 3, any_pass: true }),
    'K1. maxpf_moves_viewed {state, n_moves (passing, v1 meaning), band, n_listed, any_pass} for §5.1');
  assert(eq(u.viewedProps(NO_MISS, u.deriveSection(NO_MISS, null)), { state: 'no_miss', n_moves: 0, band: 'championship', n_listed: 0, any_pass: false })
      && eq(u.viewedProps(UNAVAILABLE, u.deriveSection(UNAVAILABLE, null)), { state: 'unavailable', n_moves: 0, band: 'none', n_listed: 0, any_pass: false }),
    'K2. n_moves is 0 unless ready; band is "none" with no baseline');
  const live = READY.roster_player_ids.filter((id) => id !== '8150');
  assert(u.viewedProps(READY, u.deriveSection(READY, live)).n_moves === 1, 'K3. n_moves counts rows after the roster drop');
  assert(eq(u.expandedProps(R1), { position: 'RB', rank: 1 }) && eq(u.answeredProps('not_sure', 'change'), { answer: 'not_sure', source: 'change' })
      && eq(u.PINNED_PROPS, { side: 'give', source: 'maxpf_moves' }), 'K4. maxpf_move_expanded / draft_order_rule_answered / finder_target_pinned property names');
  const allProps = JSON.stringify([u.viewedProps(READY, m), u.expandedProps(R1), u.PINNED_PROPS]);
  assert(!/8150|Rhett|Sato/.test(allProps), 'K5. no player id or name in any property');
  assert(eq(u.MAXPF_EVENTS, { viewed: 'maxpf_moves_viewed', expanded: 'maxpf_move_expanded', pinned: 'finder_target_pinned', answered: 'draft_order_rule_answered' }),
    'K6. the four event names');
  const comp = read('src/components/MaxPfMovesSection.tsx');
  const tracks = comp.match(/\btrack\(/g) || [];
  assert(tracks.length === 4 && /if \(opening\) track\(MAXPF_EVENTS\.expanded, combinedExpandedProps\(entry\), SCREEN\)/.test(comp)
      && /track\(MAXPF_EVENTS\.viewed, viewedProps\(block, model\), SCREEN\)/.test(comp)
      && /if \(opening\) track\(MAXPF_EVENTS\.expanded, expandedProps\(row\), SCREEN\)/.test(comp)
      && /track\(MAXPF_EVENTS\.answered, answeredProps\(rule, questionSource\), SCREEN\)/.test(comp),
    'K7. the component emits viewed (on body mount), expanded (on open only), answered (after the POST); pinned rides the hand-off');
  assert(/if \(viewedRef\.current\) return;\s*viewedRef\.current = true;/.test(comp)
      && /const maxPfViewed = useRef\(false\);/.test(read('src/components/LeagueProjectionDetail.tsx')),
    'K8. viewed fires once per opening of the own card (ref held by the card)');
  const answerBody = (/const answer = async[\s\S]*?\n  \};/.exec(comp) || [''])[0];
  assert(answerBody.indexOf('await setDraftOrderRule') >= 0 && answerBody.indexOf('await setDraftOrderRule') < answerBody.indexOf('track(')
      && answerBody.indexOf('catch') > answerBody.indexOf('track('), 'K9. draft_order_rule_answered fires only after the POST resolves');
  assert(read('src/screens/StandingsScreen.tsx').match(/\btrack\(/g).length === 1, 'K10. Standings itself still has its one emitter');
}

// ═══ L. Draft-order question and POST (§6.4, §7.2) ═══════════════════════
{
  assert(eq(u.draftOrderRequest('lg 1', 'reverse_standings'), { path: '/api/leagues/lg%201/draft-order-rule', body: { rule: 'reverse_standings' } }),
    'L1. POST /api/leagues/<id>/draft-order-rule with exactly {rule}');
  assert(eq(u.DRAFT_ORDER_ANSWERS, ['maxpf_lowest_first', 'reverse_standings', 'lottery_or_other', 'not_sure'])
      && eq(u.DRAFT_ORDER_ANSWERS.map(u.answerLabel), ['Lowest max PF', 'Reverse standings', 'Lottery or other', 'Not sure']),
    'L2. the four answers, in order, labelled C-Q-OPTS');
  assert(u.questionEligible(READY) && u.questionEligible(NO_MISS) && u.questionEligible(withBlock(READY, { state: 'no_moves' }))
      && !u.questionEligible(UNAVAILABLE) && !u.questionEligible(withBlock(READY, { draft_order: { rule: 'maxpf_lowest_first', set_at: 'x' } })),
    'L3. asked only with no stored answer, in ready / no_moves / no_miss');
  assert(u.questionAutoShown(READY, false) && !u.questionAutoShown(READY, true), 'L4. once per league per device');
  assert(u.RULES_NOTE_KEY === 'maxpf.rulesNoteShown' && u.draftOrderAskedKey('123') === 'maxpf.draftOrderAsked.123',
    'L5. device keys per §6.4');
  assert(eq(u.orderLine(READY), { text: C['C-ORDER-ASSUMED'], link: 'Change' })
      && eq(u.orderLine(withBlock(READY, { draft_order: { rule: 'maxpf_lowest_first', set_at: 'x' } })), { text: C['C-ORDER-MAXPF'], link: 'Change' })
      && eq(u.orderLine(NO_MISS), { text: C['C-ORDER-ASSUMED'], link: 'Change' }) && u.orderLine(UNAVAILABLE) === null,
    'L6. the assumption / Max PF line + Change link');
  const apiSrc = read('src/api/draftOrderRule.ts');
  assert(/const \{ path, body \} = draftOrderRequest\(leagueId, rule\);\s*return api\.post<\{ draft_order: DraftOrder \}>\(path, body\);/.test(apiSrc),
    'L7. setDraftOrderRule posts the util-built path and body through api.post');
  const comp = read('src/components/MaxPfMovesSection.tsx');
  assert(/markDraftOrderAsked\(leagueId\);/.test(comp) && /queryClient\.invalidateQueries\(\{ queryKey: \['league-projection-batch', userId, leagueId\] \}\)/.test(comp)
      && /setPostError\(true\)/.test(comp) && /\{C\['C-Q-ERR'\]\}/.test(comp),
    'L8. a 200 records the device key and refetches the forecast read; a failure shows C-Q-ERR');
  assert(/onPress=\{\(\) => \{ setPostError\(false\); setQuestion\('change'\); \}\}/.test(comp),
    'L9. "Change" re-opens the question with source change');
  const prompts = read('src/state/maxPfMovesPrompts.ts');
  assert(/AsyncStorage\.getItem\(RULES_NOTE_KEY\)/.test(prompts) && /AsyncStorage\.setItem\(draftOrderAskedKey\(leagueId\), '1'\)/.test(prompts),
    'L10. the prompts module stores under the util keys');
  assert(/const showRulesNote = listOpen && !!model\.baseline && !!prompts\?\.rulesNote;/.test(comp)
      && /if \(showRulesNote\) markRulesNoteShown\(\);/.test(comp), 'L11. C-RULES shows once per device under the baseline, written then');
}

// ═══ M. No extra request on open (D-254) and structure ═══════════════════
{
  const comp = read('src/components/MaxPfMovesSection.tsx');
  assert(!/useQuery\b|useMutation|fetch\(|api\.(get|post)|getLeagueProjectionBatch|simulat/i.test(comp.replace(/useQueryClient/g, '')),
    'M1. the section starts no query, fetch or simulation; its one request is setDraftOrderRule after a tap');
  const det = read('src/components/LeagueProjectionDetail.tsx');
  assert(!/useQuery|useSession|useFlag/.test(det), 'M2. the detail still reads nothing (the screen owns the queries and the flag)');
  const projApi = read('src/api/leagueProjections.ts');
  assert(!/api\.post/.test(projApi) && /max_pf_moves\?: MaxPfMoves;/.test(projApi), 'M3. the forecast client still only reads; the block is optional on ProjectionView');
  assert(/testID="standings\.maxpf\.toggle"/.test(det), 'M4a. testID on the disclosure');
  for (const id of ['standings.maxpf.body', 'standings.maxpf.show-all', 'standings.maxpf.order-change', 'standings.maxpf.show-anyway',
    'standings.maxpf.show-moves', 'standings.maxpf.question']) {
    assert(comp.includes(`'${id}'`) || comp.includes(`"${id}"`), `M4b. testID ${id}`);
  }
  assert(/testID=\{`standings\.maxpf\.row\.\$\{row\.rank\}`\}/.test(comp) && /testID=\{`standings\.maxpf\.find\.\$\{row\.rank\}`\}/.test(comp)
      && /testID=\{`standings\.maxpf\.answer\.\$\{a\}`\}/.test(comp), 'M4c. per-row, per-button and per-answer testIDs');
  assert(/rowHead: \{ minHeight: 44,/.test(comp) && /link: \{ minHeight: 44,/.test(comp), 'M5. rows and links are at least 44pt');
  assert(/num: \{ \.\.\.type\.data,/.test(comp) && /numberOfLines=\{1\}>\{p\.name\}/.test(comp) && /name: \{ flexShrink: 1, minWidth: 0 \}/.test(comp),
    'M6. numbers use the Standings mono style; long names truncate and give way at large text sizes');
  assert(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(comp) && !/gradient|blur|borderRadius/i.test(comp) && !/flare/.test(comp)
      && !/[\u{1F300}-\u{1FAFF}☀-➿]/u.test(comp), 'M7. Chalkline: no literals, gradients, blur, radius, flare or emoji');
  assert(/linkText: \{ color: ice\.base \}/.test(comp) && (comp.match(/ice\.base/g) || []).length === 1,
    'M8. ice only on the tappable links');
  assert(!/from 'react-native';[\s\S]*\bText\b[\s\S]*from 'react-native'/.test(comp) && /import \{ Badge, Button, Icon, Text \} from '\.\/chalkline';/.test(comp),
    'M9. text goes through chalkline Text');
  const pkg = JSON.parse(read('package.json'));
  assert(pkg.scripts['test:max-pf-moves'] === 'node tests/check-max-pf-moves.js', 'M10. npm run test:max-pf-moves');
}

// ═══ N. Values hidden when not priced (§6.6) ═════════════════════════════
{
  const unpriced = withBlock(READY, { baseline: Object.assign(clone(READY.baseline), { pick_value: null, pick_value_status: 'not_priced' }) });
  const m = u.deriveSection(unpriced, null);
  assert(m.priced === false && !/Value/.test(m.baseline) && !/Value/.test(u.rowLine2(R1, m.priced)),
    'N1. not_priced hides the baseline value and every row value');
  const comp = read('src/components/MaxPfMovesSection.tsx');
  assert(/rowLine2\(row, priced\)/.test(comp) && /priced=\{model\.priced\}/.test(comp), 'N2. the row renders rowLine2 with the model\'s priced flag');
}

// ═══ O. v1.1 (D-261): every row listed, the none-alone sentence, combined lines ═
{
  const M = '−';
  const fail = (r) => Object.assign(clone(r), { passes_threshold: false });
  const NOPASS = withBlock(READY, { state: 'no_moves', rows: READY.rows.map(fail), combined: READY.combined.map(fail) });
  const COMB = READY.combined;
  const C2 = COMB[0];
  const C3 = COMB[1];
  // O1. all rows listed in both list states
  const np = u.deriveSection(NOPASS, null);
  assert(eq(np.listed.map((r) => r.rank), [1, 2, 3]) && eq(u.deriveSection(READY, null).listed.map((r) => r.rank), [1, 2, 3])
      && np.baseline !== null && np.head === 'Max PF change over the remaining 5 weeks' && np.foot === C['C-FOOT'],
    'O1. every row is listed, rank order, in ready AND no_moves (with head and foot)');
  const eight = withBlock(NOPASS, { rows: Array.from({ length: 8 }, (_, i) => Object.assign(fail(R1), { rank: 8 - i, player_id: `q${i}` })) });
  const v = u.visibleRows(u.deriveSection(eight, null).listed, false);
  assert(v.rows.length === 5 && v.showAllButton && eq(v.rows.map((r) => r.rank), [1, 2, 3, 4, 5]),
    'O1b. 8 non-passing rows ⇒ 5 shown, largest drop first, then Show all');
  // O2. the sentence exactly when nothing listed passes
  assert(np.noneAloneLine === 'None of these changes your projected pick on its own.' && np.noMovesLine === null,
    'O2a. nothing passes ⇒ C-NONE-ALONE above the list (not C-NO-MOVES)');
  assert(u.deriveSection(READY, null).noneAloneLine === null, 'O2b. some rows pass ⇒ no sentence');
  const combOnly = withBlock(NOPASS, { combined: [clone(C2)] });
  assert(u.deriveSection(combOnly, null).noneAloneLine === null, 'O2c. only a combined entry passes ⇒ no sentence');
  const oneRow = withBlock(NOPASS, { rows: [clone(R3), Object.assign(clone(R1), { passes_threshold: true })], combined: [] });
  assert(u.deriveSection(oneRow, null).noneAloneLine === null, 'O2d. one passing row among failing ones ⇒ no sentence, no badge');
  assert(u.deriveSection(withBlock(NOPASS, { rows: [], combined: [] }), null).noneAloneLine === null
      && u.deriveSection(NO_MISS, null).noneAloneLine === null && u.deriveSection(UNAVAILABLE, null).noneAloneLine === null,
    'O2e. no sentence without a list (zero rows, other states)');
  // O3. combined lines: strings and formatting
  assert(u.combinedLine1(C2) === `Top 2 together: R. Sato and D. Okafor  ${M}55`
      && u.combinedLine1(C3) === `Top 3 together: R. Sato, D. Okafor and B. Halvorsen  ${M}59`,
    'O3a. C-COMB-1 names joined "A and B" / "A, B and C", change with U+2212', u.combinedLine1(C3));
  assert(u.combinedLine2(C2, true) === 'Pick if you miss 3.7 → 3.1 · Value +282' && u.combinedLine2(C2, false) === 'Pick if you miss 3.7 → 3.1',
    'O3b. C-COMB-2 = C-ROW-2 rules: value only when priced', u.combinedLine2(C2, true));
  assert(eq(u.combinedDetail(C2), { top3: 'Top-3 chance 46% → 70%', playoff: 'Playoff chance 3% → 1%' }),
    'O3c. an opened combined line shows top-3 and playoff chance only', show(u.combinedDetail(C2)));
  const odd = Object.assign(clone(C2), { maxpf_change: 0, pick_if_miss: { now: 3.6912, after: null }, pick_value: { now: 1, after: 1, change: 0.3 } });
  assert(u.combinedLine1(odd).endsWith('  0') && u.combinedLine2(odd, true) === 'Pick if you miss 3.7 → — · Value 0',
    'O3d. §11 on combined: 0 as "0", null after as "—", a zero value change as "0"', u.combinedLine2(odd, true));
  const unpriced = withBlock(READY, { baseline: Object.assign(clone(READY.baseline), { pick_value: null, pick_value_status: 'not_priced' }) });
  assert(!/Value/.test(u.combinedLine2(C2, u.deriveSection(unpriced, null).priced)), 'O3e. not_priced hides the combined value');
  assert(u.combinedLine1(Object.assign(clone(C2), { maxpf_change: 4 })).endsWith('  +4'), 'O3f. a positive combined change is "+n"');
  // O4. roster-change dropping
  const live = READY.roster_player_ids.filter((id) => id !== '11233');
  const rc = u.deriveSection(READY, live);
  assert(eq(rc.combined.map((c) => c.size), [2]) && eq(rc.listed.map((r) => r.rank), [1, 2]),
    'O4a. a member off the roster drops that combined entry (size 3), keeps the other');
  assert(u.deriveSection(READY, READY.roster_player_ids.filter((id) => id !== '6130')).combined.length === 0,
    'O4b. a player in both entries leaving drops both');
  assert(eq(u.deriveSection(READY, [...READY.roster_player_ids].reverse()).combined.map((c) => c.size), [2, 3]),
    'O4c. an unchanged roster keeps both, smallest first');
  // O5. no Find trades on combined
  const comp = read('src/components/MaxPfMovesSection.tsx');
  const combBody = (/function CombinedLine\([\s\S]*?\n\}\n/.exec(comp) || [''])[0];
  assert(combBody.length > 0 && !/Button|handOff|onFindTrades|find\./.test(combBody) && eq(Object.keys(u.combinedDetail(C2)), ['top3', 'playoff'])
      && !/combined/.test((/export function handOffToFinder[\s\S]*?\n\}/.exec(utilSrc) || [''])[0]),
    'O5. a combined line has no Find trades button, no hand-off, no week detail');
  assert(/\{entry\.keep \? <Badge label=\{C\['C-KEEP'\]\} \/> : null\}/.test(combBody) && C2.keep === true,
    'O5b. a combined entry with a Keep member shows the Keep tag');
  // O6. old-shape block (no combined key) renders as before
  const old = clone(READY);
  delete old.combined;
  const om = u.deriveSection(old, null);
  const nm = u.deriveSection(withBlock(READY, { combined: [] }), null);
  assert(eq(om.combined, []) && eq(om, nm) && om.baseline === u.deriveSection(READY, null).baseline,
    'O6. a block without `combined` (pre-v1.1 server) renders exactly as one with none');
  // O7. events
  assert(eq(u.combinedExpandedProps(C3), { position: 'combined', rank: 'combined_3' }), 'O7a. combined expand props');
  assert(eq(u.viewedProps(NOPASS, np), { state: 'no_moves', n_moves: 0, band: 'jets', n_listed: 3, any_pass: false })
      && u.viewedProps(combOnly, u.deriveSection(combOnly, null)).any_pass === true,
    'O7b. viewed carries n_listed and any_pass (combined counts)');
  // O8. gates and placement
  const listOpenBlock = (/\{listOpen \? <>[\s\S]*?<\/> : null\}/.exec(comp) || [''])[0];
  assert(/model\.combined\.map\(\(entry\) => <CombinedLine/.test(listOpenBlock)
      && listOpenBlock.indexOf('model.noneAloneLine') > 0
      && listOpenBlock.indexOf('model.noneAloneLine') < listOpenBlock.indexOf('rows.map(')
      && listOpenBlock.indexOf('showAllButton ?') < listOpenBlock.indexOf('model.combined.map'),
    'O8a. the sentence sits above the rows, combined lines under the rows and Show all, all inside the gated list');
  const owned = withBlock(NOPASS, { pick_owner: { owns_own_pick: false, owner_roster_id: 9, owner_name: 'Saltmarsh Owls' } });
  const collapsed = withBlock(NOPASS, { saved_outlook: 'contender', baseline: Object.assign(clone(READY.baseline), { playoff_probability: 0.6 }) });
  assert(u.deriveSection(owned, null).ownerGate && !u.deriveSection(collapsed, null).defaultOpen
      && u.deriveSection(collapsed, null).collapsedLine !== null, 'O8b. owner and collapsed gates apply to a no_moves list');
  assert(eq(u.deriveSection(NO_MISS, null).combined, []) && eq(u.deriveSection(NOT_MAXPF, null).combined, [])
      && u.listedCombined(withBlock(READY, { state: 'no_miss' }), null).length === 0,
    'O8c. no combined lines outside ready / no_moves');
  assert(/testID=\{`standings\.maxpf\.combined\.\$\{entry\.size\}`\}/.test(comp) && /testID="standings\.maxpf\.none-alone"/.test(comp)
      && /rowHead/.test(combBody), 'O8d. testIDs and the 44pt row construction');
}

console.log(failures ? `\n${failures} max-pf-moves check(s) FAILED, ${passes} passed.` : `\nAll max-pf-moves checks passed (${passes}).`);
process.exit(failures ? 1 : 0);
