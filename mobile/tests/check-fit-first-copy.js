#!/usr/bin/env node
// WS4b fit block guard (docs/plans/offer-learnings/scope-fit-block-v3.md;
// replaces the WS4 fit-line checks, scope-fit-first-copy.md).
//
// WHY THIS EXISTS. The server composes a per-team fit block (`fit_block`,
// backend/trade_narrative.py fit_block, template fit-2) behind the default-off
// flag `trade.fit_first_copy`: an outlook tag, one lead phrase and the team's
// league rank moves, the other team first. The operator chose the mockup's
// version 3 (mockups/fit-copy/) with these honesty rules: losses as plain as
// gains, direction by arrow and numbers never by colour, at most two lines
// per team, above the player rows. D-056 retired the simulator, so the shape
// is pinned here instead.
//
// What is pinned:
//   1. TradeCard reads the flag `trade.fit_first_copy` and hides the block on
//      an edited card (it describes the original package).
//   2. The block sits directly under the header: before the standing-offer
//      line, the consensus note, Match strength, the player sides, the value
//      bar and the bottom reasons list.
//   3. The other team's row comes before the viewer's row; both testIDs exist,
//      and each renders its own team's tag, lead and ranks.
//   4. Server text only: no `code` read anywhere in the card except
//      fitLeadShown (check 13); the only literal copy in the block is the
//      label row, the two team labels and the Before / After header.
//   5. Two lines per team: the lead and the ranks are single-line
//      (numberOfLines={1}); ranks in the mono face (type.data).
//   6. No colour carries direction: the fit styles use neutral chalk/ink
//      tokens only (no semantic / ice / flare / position colour, no hex).
//   7. The rank text: fitRankOrdinal and fitRanksText, executed here.
//   8. The wire type declares `fit_block` optional; `fit_lines` is gone.
//   9. The normalizer accepts only `v === 'fit-2'`, validates side, lead,
//      tag and ranks, adds the key only when a team passes, and never reads
//      `fit_lines` (a stored fit-1 line is dropped).
//  10. `npm run test:fit-first-copy` exists.
//
// The before/after table (operator, TestFlight 2026-11-11: "a simple
// before/after table is a better fit for the positions involved"). The
// server adds `positions` per team (held + moved, QB/RB/WR/TE order) and
// keeps v/lead/ranks/tag as they were, so builds 184/185 are unchanged:
//  11. A team with non-empty `positions` renders FitRankRows in place of
//      the rank text; absent or empty falls back to fitRanksText(ranks)
//      exactly as before. One Before / After header for the block, shown
//      only when a team has a table.
//  12. FitRankRows, transpiled and executed: one row per position (held and
//      moved alike, none filtered), three cells (position, ordinal before,
//      ordinal after) in the mono face with fixed widths, a templated testID
//      `trade-card.fit-rank.<side>.<pos>` and a VoiceOver label
//      "Them, RB, 5th before, 5th after"; no style depends on direction.
//  13. fitLeadShown, executed: with a table, `holds.*` / `shifts.*` leads hide
//      and `plan_*` / `need.*` (and anything else) stay; with `positions`
//      missing or empty every lead shows (today's rendering).
//  14. The normalizer validates `positions` like `ranks` (at most 4) and
//      yields [] when the server sent none.
//
// The rank-free block (operator, TestFlight 186, 2026-11-11: "remove the
// value change content"; server flag trade.fit_position_ranks off). The
// server sends `ranks: []`, `positions: []`, reason leads only, and omits a
// team without one, so installed builds change without an update:
//  15. The normalizer and the block JSX, transpiled and run on that payload
//      (two teams, one team, no tag): every team kept with its tag and lead;
//      no Before / After header, no FitRankRows, no rank text, no empty
//      text node; an omitted team draws no row. The flag-on shape is the
//      control (it must draw the header and the table). The label row reads
//      "Team fit" on the rank-free block and today's label on the control.
//  16. The label's predicate, run: "Team fit" when no team has `ranks` or
//      `positions` rows, "League rank · position value" when either does.
//
// Run: node tests/check-fit-first-copy.js   (or: npm run test:fit-first-copy)

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const CARD = path.join(ROOT, 'src/components/TradeCard.tsx');
const TYPES = path.join(ROOT, 'src/shared/types.ts');
const API = path.join(ROOT, 'src/api/trades.ts');
const PKG = path.join(ROOT, 'package.json');

const failures = [];
const checks = [];
function ok(name) { checks.push(name); }
function fail(name, detail) { failures.push(`${name}\n      ${detail}`); }
function read(p) {
  if (!fs.existsSync(p)) { fail('file exists', `missing: ${path.relative(ROOT, p)}`); return ''; }
  return fs.readFileSync(p, 'utf8');
}
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}
function balanced(src, openIdx, open, close) {
  if (src[openIdx] !== open) return '';
  let depth = 0;
  for (let i = openIdx; i < src.length; i++) {
    if (src[i] === open) depth++;
    else if (src[i] === close) { depth--; if (depth === 0) return src.slice(openIdx, i + 1); }
  }
  return '';
}

const card = stripComments(read(CARD));
const types = stripComments(read(TYPES));
const api = stripComments(read(API));

// 1. Flag read + edited gate.
{
  const name = '1. card reads trade.fit_first_copy and hides the block on an edited card';
  if (!/useFlag\(\s*'trade\.fit_first_copy'\s*\)/.test(card)) {
    fail(name, "no useFlag('trade.fit_first_copy') in TradeCard.tsx");
  } else if (!/fitFirstEnabled\s*&&\s*!data\.edited\s*\?\s*data\.fit_block\s*:\s*undefined/.test(card)) {
    fail(name, 'the block must be read as `fitFirstEnabled && !data.edited ? data.fit_block : undefined`');
  } else if (!/fitBlockShown\?\.teams\.find\(\(t\)\s*=>\s*t\.side\s*===\s*'them'\)/.test(card)
             || !/fitBlockShown\?\.teams\.find\(\(t\)\s*=>\s*t\.side\s*===\s*'you'\)/.test(card)) {
    fail(name, 'fitThem / fitYou must be the them / you team of the gated block');
  } else ok(name);
}

// Locate the block.
const BLOCK_ID = 'testID="trade-card.fit-block"';
const blockAt = card.indexOf(BLOCK_ID);
let block = '';
{
  const gate = card.lastIndexOf('{fitThem || fitYou ? (', blockAt);
  if (blockAt >= 0 && gate >= 0) block = balanced(card, card.indexOf('(', gate + 1), '(', ')');
}

// 2. Order: the block leads.
{
  const name = '2. fit block renders under the header, before every value surface';
  const header = card.indexOf('style={styles.header}');
  const later = [
    ['standing-offer line', 'testID="trade-card.standing-offer-reason"'],
    ['consensus note', 'testID="trade-card.consensus-note"'],
    ['Match strength', '<StrengthBar'],
    ['player sides', '<TickLabel>YOU SEND</TickLabel>'],
    ['value bar', '<TradeValueBar'],
    ['reasons list', '{showReasons && ('],
  ];
  if (blockAt < 0 || !block) fail(name, `no ${BLOCK_ID} block gated on \`{fitThem || fitYou ? (\``);
  else if (header < 0 || header > blockAt) fail(name, 'the fit block must come after the header');
  else {
    const bad = later.filter(([, needle]) => { const i = card.indexOf(needle); return i < 0 || i < blockAt; });
    if (bad.length) fail(name, `these must exist and come after the fit block: ${bad.map((b) => b[0]).join(', ')}`);
    else ok(name);
  }
}

// 3. Them before you, each row rendering its own team.
const themAt = block.indexOf('testID="trade-card.fit-team.them"');
const youAt = block.indexOf('testID="trade-card.fit-team.you"');
const themRow = themAt >= 0 && youAt > themAt ? block.slice(themAt, youAt) : '';
const youRow = youAt >= 0 ? block.slice(youAt) : '';
{
  const name = "3. the other team's row precedes the viewer's row and renders its own team";
  const own = (row, who) => [`{fit${who}.tag.text}`, `{fit${who}.lead.text}`, `fitRanksText(fit${who}.ranks)`]
    .every((needle) => row.includes(needle));
  if (themAt < 0 || youAt < 0) fail(name, 'both trade-card.fit-team.them and trade-card.fit-team.you must be in the block');
  else if (themAt > youAt) fail(name, 'them row must come first');
  else if (!own(themRow, 'Them') || /fitYou\./.test(themRow)) fail(name, 'the them row must render fitThem tag/lead/ranks only');
  else if (!own(youRow, 'You') || /fitThem\./.test(youRow)) fail(name, 'the you row must render fitYou tag/lead/ranks only');
  else ok(name);
}

// 4. Server text only.
{
  const name = '4. block renders server text only (no code read; only the label copy)';
  const literals = (block.match(/>\s*([A-Za-z][^<>{}]*?)\s*</g) || [])
    .map((m) => m.replace(/^>\s*|\s*<$/g, ''));
  // The label row is the one string expression: the rank label or "Team fit"
  // (check 16 runs it).
  const label = block.match(/>\{fitRanked \? '([^']+)' : '([^']+)'\}</);
  if (label) literals.push(label[1], label[2]);
  const allowed = ['League rank · position value', 'Team fit', 'Them', 'You', 'Before', 'After'];
  const extra = literals.filter((l) => !allowed.includes(l));
  // The one exception: fitLeadShown hides a rank-fact lead the table restates.
  const leadFn = card.indexOf('export function fitLeadShown(');
  const leadEnd = leadFn < 0 ? -1 : card.indexOf('\n}\n', leadFn);
  const outside = leadFn < 0 ? card : card.slice(0, leadFn) + card.slice(leadEnd);
  if (/\.code\b/.test(outside)) fail(name, 'TradeCard must never read a fit `code` outside fitLeadShown');
  else if (extra.length) fail(name, `literal copy in the block: ${extra.join(' | ')}`);
  else if (allowed.some((a) => !literals.includes(a))) fail(name, `the block must carry the labels ${allowed.join(', ')}`);
  else ok(name);
}

// 5. Two lines per team, ranks in mono.
{
  const name = '5. lead and ranks are single-line; ranks in the mono face';
  const singleLine = (row, who) =>
    new RegExp(`numberOfLines=\\{1\\}>\\{fit${who}\\.lead\\.text\\}`).test(row)
    && new RegExp(`numberOfLines=\\{1\\}>\\{fitRanksText\\(fit${who}\\.ranks\\)\\}`).test(row);
  const ranksStyle = card.match(/fitRanks:\s*\{[^}]*\}/);
  if (!singleLine(themRow, 'Them') || !singleLine(youRow, 'You')) {
    fail(name, 'each lead and ranks Text needs numberOfLines={1} (truncate, never wrap)');
  } else if (!ranksStyle || !/\.\.\.type\.data\b/.test(ranksStyle[0])) {
    fail(name, 'styles.fitRanks must spread type.data (IBM Plex Mono)');
  } else ok(name);
}

// 6. Neutral colours only.
{
  const name = '6. fit styles are neutral tokens: no colour carries direction';
  const names = ['fitBlock', 'fitTeam', 'fitWho', 'fitTag', 'fitBody', 'fitLead', 'fitRanks',
                 'fitRankRow', 'fitRankPos', 'fitRankCol', 'fitRankNum'];
  const bodies = names.map((n) => { const m = card.match(new RegExp(`\\b${n}:\\s*\\{[^}]*\\}`)); return m ? m[0] : null; });
  if (bodies.some((b) => b === null)) fail(name, `missing styles: ${names.filter((_, i) => !bodies[i]).join(', ')}`);
  else {
    const all = bodies.join('\n');
    if (/#[0-9a-fA-F]{3,8}\b/.test(all)) fail(name, 'hex literal in fit styles');
    else if (/\b(semantic|ice|flare|posColor|POSITION_COLORS)\b/.test(all)) fail(name, 'a coloured token in fit styles');
    else if (/\bstyle=\{[^}]*(semantic|ice|flare)/.test(block)) fail(name, 'a coloured inline style in the block');
    else ok(name);
  }
}

// 7. Rank text, executed.
{
  const name = '7. fitRankOrdinal / fitRanksText format ranks as ordinals with an arrow';
  const raw = read(CARD);
  const grab = (fn) => {
    const at = raw.indexOf(`export function ${fn}(`);
    return at < 0 ? '' : raw.slice(at, at + raw.slice(at).indexOf('\n}\n') + 2);
  };
  const src = [grab('fitRankOrdinal'), grab('fitRanksText')]
    .map((s) => s.replace(/^export /, '').replace(/\(n: number\): string/, '(n)')
      .replace(/\(ranks: FitBlockTeam\['ranks'\]\): string/, '(ranks)')
      .replace(/ as Record<number, string>/, ''))
    .join('\n');
  let ordinal, ranks;
  try {
    // eslint-disable-next-line no-new-func
    [ordinal, ranks] = new Function(`${src}\nreturn [fitRankOrdinal, fitRanksText];`)();
  } catch (e) { fail(name, `could not evaluate the helpers: ${e.message}`); }
  if (ordinal) {
    const cases = { 1: '1st', 2: '2nd', 3: '3rd', 4: '4th', 9: '9th', 10: '10th', 11: '11th',
                    12: '12th', 13: '13th', 14: '14th', 21: '21st', 22: '22nd', 23: '23rd', 111: '111th' };
    const wrong = Object.entries(cases).filter(([n, want]) => ordinal(Number(n)) !== want);
    const text = ranks([{ pos: 'WR', before: 9, after: 7 }, { pos: 'RB', before: 2, after: 4 }]);
    if (wrong.length) fail(name, `ordinal wrong for ${wrong.map(([n]) => n).join(', ')}`);
    else if (text !== 'WR 9th → 7th · RB 2nd → 4th') fail(name, `ranks text was "${text}"`);
    else ok(name);
  }
}

// The table helpers' source (comments kept out; JSX intact).
function grabFn(src, header) {
  const at = src.indexOf(header);
  return at < 0 ? '' : src.slice(at, at + src.slice(at).indexOf('\n}\n') + 2);
}
const rowsSrc = grabFn(card, 'function FitRankRows(');

// 11. Table in place of the rank text; one header.
{
  const name = '11. positions render as a table in place of the rank text; absent/empty falls back';
  const branch = (who, side) => new RegExp(
    `\\{fit${who}\\.positions\\?\\.length \\? \\(\\s*<FitRankRows side="${side}" who="${who}" positions=\\{fit${who}\\.positions\\} />\\s*\\)`
    + ` : fit${who}\\.ranks\\.length \\? \\(\\s*<ChalklineText style=\\{styles\\.fitRanks\\} numberOfLines=\\{1\\}>`
    + `\\{fitRanksText\\(fit${who}\\.ranks\\)\\}</ChalklineText>\\s*\\) : null\\}`);
  const leadGate = (who) => new RegExp(`\\{fitLeadShown\\(fit${who}\\) \\? \\(\\s*<ChalklineText style=\\{styles\\.fitLead\\} numberOfLines=\\{1\\}>\\{fit${who}\\.lead\\.text\\}`);
  const heads = (card.match(/>Before</g) || []).length + (card.match(/>After</g) || []).length;
  const headAt = block.indexOf('testID="trade-card.fit-rank-head"');
  if (!branch('Them', 'them').test(themRow) || !branch('You', 'you').test(youRow)) {
    fail(name, 'each team must render `positions?.length ? <FitRankRows …/> : ranks.length ? fitRanksText(ranks) : null`');
  } else if (!leadGate('Them').test(themRow) || !leadGate('You').test(youRow)) {
    fail(name, 'each lead must be gated on fitLeadShown(team)');
  } else if (heads !== 2 || headAt < 0 || headAt > themAt) {
    fail(name, 'one Before and one After header, in trade-card.fit-rank-head, above the team rows');
  } else if (!/const fitTable = !!\(fitThem\?\.positions\?\.length \|\| fitYou\?\.positions\?\.length\)/.test(card)
             || !/\{fitTable \? \(\s*<View\s+style=\{styles\.fitTeam\}\s+testID="trade-card\.fit-rank-head"/.test(block)) {
    fail(name, 'the header must render only when a team has a non-empty positions list (fitTable)');
  } else ok(name);
}

// Transpile + run a TSX snippet against a tiny React stand-in.
let ts = null;
try { ts = require('typescript'); } catch (e) { /* reported below */ }
function run(src, names, scope) {
  const js = ts.transpileModule(src, {
    compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None },
  }).outputText;
  const keys = Object.keys(scope);
  // eslint-disable-next-line no-new-func
  return new Function(...keys, `${js}\nreturn [${names.join(', ')}];`)(...keys.map((k) => scope[k]));
}
const h = (type, props, ...children) => ({ type, props: props || {}, children: children.flat() });
const React = { createElement: h, Fragment: 'Fragment' };
const textOf = (n) => (n == null || typeof n === 'boolean' ? '' : typeof n !== 'object' ? String(n)
  : n.children.map(textOf).join(''));
const ordinalSrc = grabFn(read(CARD), 'export function fitRankOrdinal(').replace(/^export /, '');

// 12. FitRankRows, executed.
{
  const name = '12. FitRankRows: one row per position (held and moved), ordinals, ids, VoiceOver label, mono, no direction colour';
  if (!ts) fail(name, 'typescript is not installed (npm ci)');
  else if (!rowsSrc) fail(name, 'no function FitRankRows in TradeCard.tsx');
  else {
    const styles = { fitRankRow: { r: 1 }, fitRankNum: { n: 1 }, fitRankPos: { p: 1 }, fitRankCol: { c: 1 } };
    let FitRankRows;
    try {
      [FitRankRows] = run(`${ordinalSrc}\n${rowsSrc}`, ['FitRankRows'],
        { React, View: 'View', ChalklineText: 'ChalklineText', styles });
    } catch (e) { fail(name, `could not run FitRankRows: ${e.message}`); }
    if (FitRankRows) {
      const tree = FitRankRows({ side: 'them', who: 'Them', positions: [
        { pos: 'RB', before: 5, after: 5 }, { pos: 'WR', before: 6, after: 12 }] });
      const rows = tree.children.filter((c) => c && c.type === 'View');
      const cells = rows.map((r) => r.children.filter((c) => c && c.type === 'ChalklineText').map(textOf));
      const ids = rows.map((r) => r.props.testID);
      const labels = rows.map((r) => r.props.accessibilityLabel);
      const cellStyles = rows.flatMap((r) => r.children.filter((c) => c && c.type === 'ChalklineText')
        .map((c) => JSON.stringify(c.props.style)));
      if (JSON.stringify(cells) !== JSON.stringify([['RB', '5th', '5th'], ['WR', '6th', '12th']])) {
        fail(name, `cells were ${JSON.stringify(cells)}`);
      } else if (JSON.stringify(ids) !== JSON.stringify(['trade-card.fit-rank.them.RB', 'trade-card.fit-rank.them.WR'])) {
        fail(name, `testIDs were ${JSON.stringify(ids)}`);
      } else if (JSON.stringify(labels) !== JSON.stringify(
        ['Them, RB, 5th before, 5th after', 'Them, WR, 6th before, 12th after'])
        || !rows.every((r) => r.props.accessible === true)) {
        fail(name, `each row must be one accessible element; labels were ${JSON.stringify(labels)}`);
      } else if (new Set(cellStyles).size !== 2
        || !cellStyles.every((st) => st.includes('"n":1'))
        || rows.some((r) => JSON.stringify(r.props.style) !== '{"r":1}')) {
        // Two fixed shapes only (position cell, rank cell), both the mono face,
        // the same for a held and a moved row: nothing depends on direction.
        fail(name, `cell styles must not vary by row: ${JSON.stringify(cellStyles)}`);
      } else if (/before\s*[<>]|after\s*[<>]|semantic|ice|flare/.test(rowsSrc)) {
        fail(name, 'FitRankRows must not compare ranks or use a coloured token');
      } else {
        const mono = card.match(/fitRankNum:\s*\{[^}]*\}/);
        const pos = card.match(/fitRankPos:\s*\{\s*width:\s*(\d+)\s*\}/);
        const col = card.match(/fitRankCol:\s*\{\s*width:\s*(\d+)\s*\}/);
        // The widest occupant at the 1.35 dense cap: "12th" is 4 Plex Mono
        // cells (0.6 em) at 13pt; the BEFORE header is ~46pt of Archivo 11pt
        // caps plus tracking.
        const widest = Math.ceil(Math.max(4 * 0.6 * 13, 46) * 1.35);
        if (!mono || !/\.\.\.type\.data\b/.test(mono[0])) fail(name, 'fitRankNum must spread type.data');
        else if (!pos || !col || Number(col[1]) < widest || Number(pos[1]) < Math.ceil(2 * 0.6 * 13)) {
          fail(name, `fixed cell widths needed: rank cell >= ${widest}pt (BEFORE / "12th" at the 1.35 cap)`);
        } else ok(name);
      }
    }
  }
}

// 13. fitLeadShown, executed.
{
  const name = '13. fitLeadShown: rank-fact leads hide only when the table shows';
  const src = grabFn(read(CARD), 'export function fitLeadShown(').replace(/^export /, '');
  let shown;
  try { [shown] = run(src, ['fitLeadShown'], {}); } catch (e) { fail(name, `could not run fitLeadShown: ${e.message}`); }
  if (shown) {
    const table = [{ pos: 'RB', before: 5, after: 5 }];
    const t = (code, positions) => shown({ side: 'you', lead: { code, text: 'x' }, ranks: [], ...(positions === undefined ? {} : { positions }) });
    const wrong = [];
    for (const code of ['holds.you', 'holds.them', 'shifts.you', 'shifts.them']) if (t(code, table)) wrong.push(`${code} shown with a table`);
    for (const code of ['plan_rebuild.you', 'plan_win_now.you_roster', 'plan_rebuild.them', 'need.you', 'need.them', 'flat.you', 'none.them']) {
      if (!t(code, table)) wrong.push(`${code} hidden with a table`);
    }
    for (const code of ['holds.you', 'shifts.them', 'plan_rebuild.you', 'need.you', 'flat.you', 'none.them']) {
      if (!t(code, undefined)) wrong.push(`${code} hidden with positions absent`);
      if (!t(code, [])) wrong.push(`${code} hidden with positions empty`);
    }
    if (wrong.length) fail(name, wrong.join('; '));
    else ok(name);
  }
}

// 14. Normalizer: positions.
{
  const name = '14. normalizer validates positions like ranks (max 4) and defaults to []';
  if (!/positions: Array\.isArray\(t\.positions\)\s*\? t\.positions\.filter\(\(r: any\) =>\s*\['QB', 'RB', 'WR', 'TE'\]\.includes\(r\?\.pos\)\s*&& Number\.isInteger\(r\?\.before\) && r\.before >= 1\s*&& Number\.isInteger\(r\?\.after\) && r\.after >= 1\)\s*\.map\(\(r: any\) => \(\{ pos: r\.pos, before: r\.before, after: r\.after \}\)\)\s*\.slice\(0, 4\)\s*: \[\]/.test(api)) {
    fail(name, 'normalizeTradeCard must validate positions (pos, integer before/after >= 1), cap at 4, and default to []');
  } else if (!/positions\?:\s*\{ pos: FitRankPos; before: number; after: number \}\[\];/.test(types)) {
    fail(name, 'FitBlockTeam needs `positions?: { pos: FitRankPos; before: number; after: number }[]`');
  } else ok(name);
}

// 15. The rank-free block, end to end (server flag trade.fit_position_ranks
// off, 2026-11-11: every team `ranks: []`, `positions: []`, a reason lead,
// teams without one omitted). The normalizer and the block's JSX are
// transpiled and RUN on that payload: each team keeps its tag and lead, and
// nothing rank-shaped renders (no Before / After header, no FitRankRows, no
// rank text, no empty text node). The flag-on shape is run as a control so
// the check can see a table when there is one.
{
  const name = '15. a rank-free block renders tag + lead only: no header, no table, no rank text, no blank text';
  const rawApi = read(API);
  const normAt = rawApi.indexOf('const fitTeams: FitBlockTeam[] =');
  const normEnd = normAt < 0 ? -1 : rawApi.indexOf('\n      : [];', normAt);
  const tableExpr = (card.match(/const fitTable = (!!\(fitThem\?\.positions\?\.length \|\| fitYou\?\.positions\?\.length\));/) || [])[1];
  const rankedExpr = (card.match(/const fitRanked = ([^;]+);/) || [])[1];
  if (!ts) fail(name, 'typescript is not installed (npm ci)');
  else if (normAt < 0 || normEnd < 0 || !block || !tableExpr || !rankedExpr) fail(name, 'could not locate the normalizer, the block, fitTable or fitRanked');
  else {
    const normSrc = `function norm(raw: any) {\n${rawApi.slice(normAt, normEnd)}\n      : [];\nreturn fitTeams;\n}`;
    const leadSrc = grabFn(read(CARD), 'export function fitLeadShown(').replace(/^export /, '');
    const RowsMarker = function FitRankRows() { return null; };
    const ranksMarker = (r) => `RANKS:${JSON.stringify(r)}`;
    const styleProxy = new Proxy({}, { get: (_, k) => ({ style: String(k) }) });
    let norm, render;
    try {
      [norm] = run(normSrc, ['norm'], {});
      [render] = run(`${leadSrc}\nfunction render(fitThem: any, fitYou: any) {\n`
        + `const fitTable = ${tableExpr};\nconst fitRanked = ${rankedExpr};\nreturn ${block};\n}`, ['render'],
        { React, View: 'View', ChalklineText: 'ChalklineText', styles: styleProxy, type: styleProxy,
          FitRankRows: RowsMarker, fitRanksText: ranksMarker });
    } catch (e) { fail(name, `could not run the normalizer / block: ${e.message}`); }
    if (norm && render) {
      const nodes = (n, acc = []) => {
        if (n && typeof n === 'object') { acc.push(n); n.children.forEach((c) => nodes(c, acc)); }
        return acc;
      };
      const draw = (payload) => {
        const teams = (norm({ fit_block: payload }) || []);
        const them = teams.find((t) => t.side === 'them');
        const you = teams.find((t) => t.side === 'you');
        return { teams, tree: them || you ? render(them, you) : null };
      };
      const team = (side, lead, tag, extra = {}) => ({
        side, lead: { code: lead[0], text: lead[1] }, ranks: [], positions: [],
        ...(tag ? { tag: { code: tag[0], source: tag[1], text: tag[2] } } : {}), ...extra });
      const cases = [
        ['both teams', [team('them', ['plan_rebuild.them', 'Rebuild-leaning: adds Eli Brandt, 23'], ['rebuilder', 'roster', 'Looks rebuilding']),
                        team('you', ['need.you', 'Upgrades WR: adds Lars Quill'], ['contender', 'declared', 'Contending'])]],
        ['you only', [team('you', ['plan_win_now.you', 'Win-now: adds Lars Quill, 30'], ['contender', 'declared', 'Contending'])]],
        ['them only, no tag', [team('them', ['need.them', 'Upgrades RB: adds Otto Vail'], null)]],
      ];
      const wrong = [];
      for (const [label, teams] of cases) {
        const { teams: kept, tree } = draw({ v: 'fit-2', teams });
        const all = nodes(tree);
        const texts = all.filter((n) => n.type === 'ChalklineText').map(textOf);
        const tags = teams.filter((t) => t.tag).map((t) => t.tag.text);
        if (kept.length !== teams.length) wrong.push(`${label}: the normalizer kept ${kept.length} of ${teams.length} teams`);
        if (!tree || !all.some((n) => n.props.testID === 'trade-card.fit-block')) wrong.push(`${label}: no block rendered`);
        for (const t of teams) {
          if (!all.some((n) => n.props.testID === `trade-card.fit-team.${t.side}`)) wrong.push(`${label}: no ${t.side} row`);
          if (!texts.includes(t.lead.text)) wrong.push(`${label}: ${t.side} lead missing`);
        }
        for (const side of ['them', 'you']) {
          if (!teams.some((t) => t.side === side) && all.some((n) => n.props.testID === `trade-card.fit-team.${side}`)) {
            wrong.push(`${label}: an omitted ${side} team rendered a row`);
          }
        }
        if (tags.some((tg) => !texts.includes(tg))) wrong.push(`${label}: a tag was dropped`);
        if (all.some((n) => n.props.testID === 'trade-card.fit-rank-head') || texts.includes('Before') || texts.includes('After')) {
          wrong.push(`${label}: the Before / After header rendered`);
        }
        if (all.some((n) => n.type === RowsMarker)) wrong.push(`${label}: FitRankRows rendered`);
        if (texts.some((tx) => tx.startsWith('RANKS:'))) wrong.push(`${label}: rank text rendered`);
        if (texts.some((tx) => !tx.trim())) wrong.push(`${label}: an empty text node rendered`);
        if (!texts.includes('Team fit') || texts.includes('League rank · position value')) {
          wrong.push(`${label}: the label must read "Team fit"`);
        }
      }
      // Control: the flag-on shape draws the header and the table.
      const on = draw({ v: 'fit-2', teams: [team('you', ['holds.you', 'TE stays 4th'], null,
        { positions: [{ pos: 'TE', before: 4, after: 4 }] })] });
      const onNodes = nodes(on.tree);
      if (!onNodes.some((n) => n.props.testID === 'trade-card.fit-rank-head') || !onNodes.some((n) => n.type === RowsMarker)) {
        wrong.push('control: a team with positions must draw the header and FitRankRows');
      }
      if (!onNodes.filter((n) => n.type === 'ChalklineText').map(textOf).includes('League rank · position value')) {
        wrong.push('control: the flag-on block keeps the label "League rank · position value"');
      }
      // No block at all: the normalizer adds nothing to render.
      if (draw({ v: 'fit-2', teams: [] }).tree !== null) wrong.push('an empty teams list must render nothing');
      if (wrong.length) fail(name, wrong.join('; '));
      else ok(name);
    }
  }
}

// 16. The label row, run: "Team fit" when no team carries a rank (the
// flag-off payload), today's "League rank · position value" when a team has
// rank moves or a table (the flag-on payload). Same style, no testID.
{
  const name = '16. label row: "Team fit" without ranks, "League rank · position value" with ranks or a table';
  const labelExpr = (card.match(/const fitRanked = ([^;]+);/) || [])[1];
  const tableExpr = (card.match(/const fitTable = ([^;]+);/) || [])[1];
  const labelNode = block.match(/<ChalklineText style=\{type\.label\} numberOfLines=\{1\}>\{fitRanked \? 'League rank · position value' : 'Team fit'\}<\/ChalklineText>/);
  if (!labelExpr || !tableExpr || !labelNode) {
    fail(name, "the label must be `<ChalklineText style={type.label} numberOfLines={1}>{fitRanked ? 'League rank · position value' : 'Team fit'}</ChalklineText>` with a `const fitRanked`");
  } else {
    let pick;
    try {
      // eslint-disable-next-line no-new-func
      pick = new Function('fitThem', 'fitYou',
        `const fitTable = ${tableExpr};\nconst fitRanked = ${labelExpr};\nreturn fitRanked ? 'League rank · position value' : 'Team fit';`);
    } catch (e) { fail(name, `could not evaluate fitRanked: ${e.message}`); }
    if (pick) {
      const t = (ranks, positions) => ({ side: 'you', lead: { code: 'x', text: 'x' }, ranks, ...(positions ? { positions } : {}) });
      const row = [{ pos: 'RB', before: 3, after: 1 }];
      const cases = [
        ['flag off, both teams', t([], []), t([], []), 'Team fit'],
        ['flag off, one team', undefined, t([], []), 'Team fit'],
        ['older server, no positions key, no moves', t([], undefined), undefined, 'Team fit'],
        ['flag on, table only (held ranks)', t([], [{ pos: 'TE', before: 4, after: 4 }]), t([], []), 'League rank · position value'],
        ['flag on, moves only (184/185 shape)', undefined, t(row, undefined), 'League rank · position value'],
        ['flag on, moves and table', t(row, row), t(row, row), 'League rank · position value'],
      ];
      const wrong = cases.filter(([, them, you, want]) => pick(them, you) !== want)
        .map(([label, them, you, want]) => `${label}: "${pick(them, you)}" (want "${want}")`);
      if (wrong.length) fail(name, wrong.join('; '));
      else ok(name);
    }
  }
}

// 8. Wire type.
{
  const name = '8. wire type declares fit_block optional; fit_lines is gone';
  if (!/fit_block\?:\s*FitBlock;/.test(types)) fail(name, 'TradeCard type needs `fit_block?: FitBlock;`');
  else if (!/export interface FitBlock\s*\{\s*v:\s*'fit-2';\s*teams:\s*FitBlockTeam\[\];\s*\}/.test(types)) {
    fail(name, "FitBlock must be `{ v: 'fit-2'; teams: FitBlockTeam[] }`");
  } else if (/fit_lines/.test(types)) fail(name, 'fit_lines must be removed from the wire type');
  else ok(name);
}

// 9. Normalizer.
{
  const name = '9. normalizer validates the block and omits the key when nothing passes';
  if (!/raw\?\.fit_block\?\.v === 'fit-2' && Array\.isArray\(raw\.fit_block\.teams\)/.test(api)) {
    fail(name, "normalizeTradeCard must accept only fit_block.v === 'fit-2' with a teams array");
  } else if (!/t\?\.side === 'them' \|\| t\?\.side === 'you'/.test(api)
             || !/typeof t\?\.lead\?\.text === 'string' && t\.lead\.text\.length > 0/.test(api)
             || !/Number\.isInteger\(r\?\.before\) && r\.before >= 1/.test(api)
             || !/\['QB', 'RB', 'WR', 'TE'\]\.includes\(r\?\.pos\)/.test(api)) {
    fail(name, 'side, lead text, rank positions and rank integers must be validated');
  } else if (!/\.\.\.\(fitTeams\.length \? \{ fit_block: \{ v: 'fit-2' as const, teams: fitTeams \} \} : \{\}\)/.test(api)) {
    fail(name, 'fit_block must be spread in only when a team passes');
  } else if (/raw\?\.fit_lines|raw\.fit_lines/.test(api)) {
    fail(name, 'the normalizer must not read fit_lines');
  } else ok(name);
}

// 10. npm script.
{
  const name = '10. npm run test:fit-first-copy exists';
  const pkg = JSON.parse(read(PKG) || '{}');
  if ((pkg.scripts || {})['test:fit-first-copy'] !== 'node tests/check-fit-first-copy.js') {
    fail(name, 'add "test:fit-first-copy": "node tests/check-fit-first-copy.js" to mobile/package.json');
  } else ok(name);
}

for (const c of checks) console.log(`  ok  ${c}`);
if (failures.length) {
  for (const f of failures) console.error(`  FAIL ${f}`);
  console.error(`\ncheck-fit-first-copy: ${failures.length} failed, ${checks.length} passed`);
  process.exit(1);
}
console.log(`\ncheck-fit-first-copy: all ${checks.length} checks passed`);
