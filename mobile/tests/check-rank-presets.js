#!/usr/bin/env node
// Unit tests for the premium rank-set preset parser
// (src/utils/rankPresets.ts — Connected Rankings addendum §3.2, [D-058]).
//
// Same idiom as check-espn-nav-policy.js: transpile the REAL module with the
// project's typescript and run it under plain node. rankPresets.ts must stay
// import-free — any runtime import throws here, which is the point: the
// parser is pure, so it can be pinned without a simulator.
//
// What these cases exist to prevent (risk R16 in the addendum): DN's CSV
// columns are byte-identical across all four scoring formats AND across its
// Dynasty and Contender value systems. Only the FILENAME differs. A parser
// that guessed from headers would silently seed a dynasty board with win-now
// values, and nothing downstream would notice.
//
// Run: node tests/check-rank-presets.js   (npm run test:rank-presets)

'use strict';

const fs = require('fs');
const path = require('path');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const srcPath = path.join(__dirname, '..', 'src', 'utils', 'rankPresets.ts');
const js = ts.transpileModule(fs.readFileSync(srcPath, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

const shim = { exports: {} };
new Function('module', 'exports', 'require', js)(shim, shim.exports, (name) => {
  throw new Error(
    `rankPresets.ts gained an unexpected runtime import ("${name}") — keep the ` +
      'preset parser pure so this check can run it under plain node.',
  );
});

const {
  parseCsv,
  detectSource,
  parseDnFilename,
  formatForScoring,
  extractRows,
  parsePreset,
  isContender,
  rowsToLines,
  FORBIDDEN_COLUMNS,
} = shim.exports;

let failures = 0;
function eq(name, actual, expected) {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a !== b) {
    failures += 1;
    console.error(`FAIL  ${name}\n      got      ${a}\n      expected ${b}`);
  } else {
    console.log(`ok    ${name}`);
  }
}

// ── Fixtures ────────────────────────────────────────────────────────────
// DN: `Rank, Player, Team, Position, Age, Exp, Value[, Trend, PPG], Pos Rank`
// (research/2026-08-15-dynasty-nerds.md §2).
const DN_CSV = [
  'Rank,Player,Team,Position,Age,Exp,Value,Trend,PPG,Pos Rank',
  "1,Ja'Marr Chase,CIN,WR,25,4,9999,+2,18.4,WR1",
  '2,"Smith, Jr.",PHI,WR,26,3,8500,-1,14.2,WR2',
  '3,Bijan Robinson,ATL,RB,23,2,8400,+1,16.0,RB1',
].join('\n');

// DN without the optional Trend/PPG columns — still a DN file (anchors only).
const DN_CSV_MIN = [
  'Rank,Player,Team,Position,Age,Exp,Value,Pos Rank',
  '1,Malik Nabers,NYG,WR,22,1,9100,WR1',
].join('\n');

// DLF: dynamic header (one column per selected analyst) + consensus `Avg`,
// with the UTF-8 BOM its client-side exporter prepends
// (research/2026-08-15-dlf.md §2).
const DLF_CSV = [
  '﻿Rank,Player,Team,Pos,Avg,Matt T,Patrick M,Wyatt B,Value',
  "1,Ja'Marr Chase,CIN,WR,1.2,1,1,2,9999",
  '2,Malik Nabers,NYG,WR,2.4,3,2,1,9500',
].join('\n');

const UNKNOWN_CSV = ['Rk,Name,Tm', '1,Ja\'Marr Chase,CIN'].join('\n');

// ── CSV reader ──────────────────────────────────────────────────────────
eq('parseCsv keeps quoted commas in one cell',
  parseCsv(DN_CSV)[2][1], 'Smith, Jr.');
eq('parseCsv strips the BOM off the first header cell',
  parseCsv(DLF_CSV)[0][0], 'Rank');
eq('parseCsv drops blank lines',
  parseCsv('a,b\n\n1,2\n').length, 2);
eq('parseCsv handles CRLF',
  parseCsv('a,b\r\n1,2\r\n').length, 2);

// ── Source detection: anchors only, never whole-header equality ─────────
eq('DN detected with optional Trend/PPG present',
  detectSource(parseCsv(DN_CSV)[0]), 'dynasty_nerds');
eq('DN detected with Trend/PPG absent',
  detectSource(parseCsv(DN_CSV_MIN)[0]), 'dynasty_nerds');
eq('DLF detected on Rank+Player+Avg despite a dynamic analyst header',
  detectSource(parseCsv(DLF_CSV)[0]), 'dlf');
eq('DLF still detected when the user deselects analysts',
  detectSource(['Rank', 'Player', 'Avg']), 'dlf');
eq('unknown header signature is NOT guessed at',
  detectSource(parseCsv(UNKNOWN_CSV)[0]), null);
eq('a DN-shaped header missing one anchor is not DN',
  detectSource(['Rank', 'Player', 'Team', 'Position', 'Age', 'Value']), null);

// ── Filename inference (DN) ─────────────────────────────────────────────
eq('plain PPR export', parseDnFilename('dynasty_rankings_ppr.csv'),
  { set: 'dynasty', scoring: 'ppr', positionFilter: null, rookiesOnly: false });
eq('contender + sflextep', parseDnFilename('dynasty_rankings_contender_sflextep.csv'),
  { set: 'contender', scoring: 'sflextep', positionFilter: null, rookiesOnly: false });
eq('positional rookie subset', parseDnFilename('dynasty_rankings_sflex_wr_rookies.csv'),
  { set: 'dynasty', scoring: 'sflex', positionFilter: 'WR', rookiesOnly: true });
eq('full path is tolerated', parseDnFilename('/tmp/x/dynasty_rankings_std.csv').scoring, 'std');
eq('no filename → nothing inferred', parseDnFilename(null),
  { set: null, scoring: null, positionFilter: null, rookiesOnly: false });
eq('an unrelated filename infers nothing', parseDnFilename('rankings.csv').set, null);

// ── Format mapping: exact vs nearest, per addendum §3.2 ─────────────────
eq('PPR → 1qb_ppr exact', formatForScoring('ppr'), { format: '1qb_ppr', match: 'exact' });
eq('SFLEXTEP → sf_tep exact', formatForScoring('sflextep'), { format: 'sf_tep', match: 'exact' });
eq('SFLEX → sf_tep NEAREST', formatForScoring('sflex'), { format: 'sf_tep', match: 'nearest' });
eq('STD → 1qb_ppr NEAREST', formatForScoring('std'), { format: '1qb_ppr', match: 'nearest' });
eq('no scoring token → unknown', formatForScoring(null), { format: null, match: 'unknown' });

// ── Row extraction is ORDER ONLY (risk R14) ─────────────────────────────
{
  const table = parseCsv(DN_CSV);
  const rows = extractRows(table[0], table.slice(1));
  eq('DN rows keep file order', rows.map((r) => r.name),
    ["Ja'Marr Chase", 'Smith, Jr.', 'Bijan Robinson']);
  eq('DN rows carry only name/team/pos', Object.keys(rows[0]).sort(),
    ['name', 'pos', 'team']);
  eq('DN team/pos hints are read', [rows[0].team, rows[0].pos], ['CIN', 'WR']);

  const serialized = JSON.stringify(rows);
  for (const col of ['9999', '8500', '18.4', '+2']) {
    eq(`no premium value (${col}) survives extraction`, serialized.includes(col), false);
  }
  eq('FORBIDDEN_COLUMNS is stated for the structural check',
    [...FORBIDDEN_COLUMNS].sort(), ['ppg', 'trend', 'value']);
}
{
  const table = parseCsv(DLF_CSV);
  const rows = extractRows(table[0], table.slice(1));
  eq('DLF reads Pos (not Position)', rows[0].pos, 'WR');
  eq('DLF consensus order comes from Rank/Player, not a per-analyst column',
    rows.map((r) => r.name), ["Ja'Marr Chase", 'Malik Nabers']);
  eq('DLF Avg is never imported as a field', Object.keys(rows[0]).sort(),
    ['name', 'pos', 'team']);
}

// ── End to end ──────────────────────────────────────────────────────────
{
  const p = parsePreset(DN_CSV, 'dynasty_rankings_contender_sflextep.csv', 'browser');
  eq('contender file parses', p.source, 'dynasty_nerds');
  eq('contender file is flagged as contender', isContender(p), true);
  eq('contender file still maps its format', [p.format, p.formatMatch], ['sf_tep', 'exact']);
  eq('via is carried through', p.via, 'browser');
  eq('rowsToLines is the plain-text fallback payload', rowsToLines(p.rows).length, 3);
}
{
  const p = parsePreset(DN_CSV, 'dynasty_rankings_std.csv', 'file');
  eq('dynasty file is not contender', isContender(p), false);
  eq('STD is imported only as a NEAREST match', p.formatMatch, 'nearest');
}
{
  const p = parsePreset(DLF_CSV, 'Dynasty Rankings-2026-08-15-1204.csv', 'file');
  eq('DLF infers no format from its filename', [p.format, p.formatMatch], [null, 'unknown']);
  eq('DLF infers no value system', p.set, null);
}
eq('unknown signature → null (caller falls back to the paste flow)',
  parsePreset(UNKNOWN_CSV, 'whatever.csv', 'file'), null);
eq('header-only file → null', parsePreset('Rank,Player,Team,Position,Age,Exp,Value', 'x.csv', 'file'), null);
eq('empty text → null', parsePreset('', null, 'file'), null);

if (failures) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll rank-preset parser checks passed.');
