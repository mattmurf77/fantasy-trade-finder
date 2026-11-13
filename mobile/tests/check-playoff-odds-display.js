#!/usr/bin/env node
// Playoff odds: 100% and 0% need a proof (D-262; operator 2026-11-13: "There
// should only be 100% probability if there's absolutely 0 possibility they
// miss the playoffs"). docs/cross-client-invariants.md § "Playoff odds: 100%
// and 0% need a proof".
//
// A EXECUTES src/utils/playoffOdds.ts and web/js/playoff-odds.js under plain
//   node over the same boundary table the backend pins for
//   clinch.odds_text (backend/tests/test_playoff_clinch.py): one decimal,
//   whole percents, 5-point steps, the miss-playoffs mirror, the sort key.
// B PINS every surface that prints a playoff chance to the helper, and sweeps
//   mobile/src + web/js for a playoff chance formatted any other way.
//
// Run: node tests/check-playoff-odds-display.js
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const ts = require('typescript');

const MOBILE = path.join(__dirname, '..');
const ROOT = path.join(MOBILE, '..');
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
let passes = 0;
let failures = 0;
const assert = (cond, name, why) => {
  if (cond) { passes += 1; console.log(`PASS  ${name}`); }
  else { failures += 1; console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`); }
};

// ═══ A. The rule, executed ══════════════════════════════════════════════
const helperSrc = read('mobile/src/utils/playoffOdds.ts');
const app = {};
new Function('exports', 'require', ts.transpileModule(helperSrc, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText)(app, (r) => { throw new Error(`playoffOdds.ts must not require ${r}`); });
const webWindow = {};
vm.runInNewContext(read('web/js/playoff-odds.js'), { window: webWindow });
const web = webWindow.FTFPlayoffOdds;

assert(!/^\s*import\s/m.test(helperSrc), 'A0. playoffOdds.ts has zero imports');
const CL = { playoff_clinched: true };
const EL = { playoff_eliminated: true };
// [percent, proof, one decimal, whole percents] — the backend table, verbatim.
const TABLE = [
  [99.94, null, '99.9%', '>99%'],
  [99.95, null, '>99.9%', '>99%'],
  [99.99, null, '>99.9%', '>99%'],
  [100, null, '>99.9%', '>99%'],
  [100, {}, '>99.9%', '>99%'],
  [100, { playoff_clinched: false }, '>99.9%', '>99%'],
  [100, CL, '100.0%', '100%'],
  [50, null, '50.0%', '50%'],
  [0.05, null, '0.1%', '<1%'],
  [0.04, null, '<0.1%', '<1%'],
  [0, null, '<0.1%', '<1%'],
  [0, EL, '0.0%', '0%'],
  [0.04, EL, '0.0%', '0%'],
  [100, EL, '>99.9%', '>99%'],
  [0, CL, '<0.1%', '<1%'],
];
for (const [label, fn] of [['app', app.playoffOddsText], ['web', (p, proof, step) => web.text(p, proof, step)]]) {
  const bad = [];
  for (const [pc, proof, one, whole] of TABLE) {
    const p = pc / 100;
    if (fn(p, proof, 0.1) !== one) bad.push(`${pc} ${JSON.stringify(proof)} @0.1 → ${fn(p, proof, 0.1)} (want ${one})`);
    if (fn(p, proof, 1) !== whole) bad.push(`${pc} ${JSON.stringify(proof)} @1 → ${fn(p, proof, 1)} (want ${whole})`);
  }
  assert(bad.length === 0, `A1. ${label}: 100% only when clinched, 0% only when eliminated, both precisions`, bad.join('; '));
}
{
  const S5 = [[1, null, '>95%'], [0.975, null, '>95%'], [0.974, null, '95%'], [0.73, null, '75%'], [0.024, null, '<5%'],
    [0, null, '<5%'], [1, CL, '100%'], [0, EL, '0%']];
  const bad = S5.filter(([p, pr, w]) => app.playoffOddsText(p, pr, 5) !== w);
  assert(bad.length === 0, 'A2. 5-point steps (outlook.odds percent chip): ">95%" / "<5%" without a proof',
    bad.map(([p, pr, w]) => `${p} → ${app.playoffOddsText(p, pr, 5)} (want ${w})`).join('; '));
}
assert(app.missOddsText(0, CL, 0.1) === '0.0%' && app.missOddsText(0, null, 0.1) === '<0.1%'
    && app.missOddsText(1, EL, 0.1) === '100.0%' && app.missOddsText(1, null, 0.1) === '>99.9%'
    && app.missOddsText(0, EL, 0.1) === '<0.1%'
    && web.miss(0, CL, 0.1) === '0.0%' && web.miss(1, null, 0.1) === '>99.9%',
  'A3. miss-playoffs mirror: 0% needs a clinch, 100% an elimination (app and web)');
assert(JSON.stringify(app.playoffSortKey(1, CL)) === '[1,1]' && JSON.stringify(app.playoffSortKey(1, null)) === '[1,0]'
    && JSON.stringify(app.playoffSortKey(0, EL)) === '[0,-1]' && JSON.stringify(app.playoffSortKey(0.5, {})) === '[0.5,0]'
    && web.rank(CL) === 1 && web.rank(EL) === -1 && web.rank(undefined) === 0,
  'A4. sort: probability first; at an equal probability a proven clinch ranks above, a proven elimination below');
assert(app.playoffOddsText(NaN, null, 0.1) === '<0.1%' && app.playoffOddsText(1.5, null, 1) === '>99%',
  'A5. out-of-range input is clamped, never printed raw');

// ═══ B. Every surface routes through the helper ═════════════════════════
const pins = [
  ['mobile/src/utils/standingsTable.ts', [/return playoffOddsText\(probability, proof, 1\);/,
    /case 'playoffs': return f \? oddsText\(f\.playoff_probability, f\) : DASH;/,
    /`Playoff odds \$\{oddsText\(f\.playoff_probability, f\)\}`/,
    /case 'playoffs': return f \? playoffSortKey\(f\.playoff_probability, f\) : null;/], 'Standings table cell, open line, sort'],
  ['mobile/src/components/LeagueProjectionDetail.tsx', [/Miss playoffs: \{missOddsText\(team\.nonplayoff_probability, team, 0\.1\)\}/],
    'team card "Miss playoffs"'],
  ['mobile/src/utils/homePlayoffBanner.ts', [/playoff_clinched: team\.playoff_clinched === true, playoff_eliminated: team\.playoff_eliminated === true/],
    'Home tile model carries the team proof'],
  ['mobile/src/components/home/HomePlayoffBanner.tsx', [/playoffOddsText\(view\.probability, view\.proof, 0\.1\)/,
    /\$\{playoffOddsText\(recommendation\.probability, view\.proof, 1\)\} playoff chance/], 'Home tile percent and "Consider" label'],
  ['mobile/src/utils/maxPfMoves.ts', [/playoffOddsText\(p, proof, 1\)/,
    /playoff: playoffPct\(block\.baseline\?\.playoff_probability \?\? 0, block\.baseline\)/,
    /now: playoffPct\(row\.playoff_probability\.now, proof\), after: playoffPct\(row\.playoff_probability\.after, proof\)/,
    /now: playoffPct\(entry\.playoff_probability\.now, proof\), after: playoffPct\(entry\.playoff_probability\.after, proof\)/],
    'Max PF moves collapsed sentence, opened rows, combined lines'],
  ['mobile/src/components/MaxPfMovesSection.tsx', [/rowDetail\(row, proof\)/, /combinedDetail\(entry, proof\)/],
    'Max PF moves component passes the baseline proof'],
  ['mobile/src/screens/TeamReviewScreen.tsx', [/percent: playoffOddsText\(chance\.playoff_probability, chance, 0\.1\)/,
    /\$\{playoffOddsText\(pr\.playoff_probability, pr, 0\.1\)\} playoff chance/,
    /Playoff odds \$\{playoffOddsText\(po\.playoff_pct, null, 1\)\}/], 'Team Review standing, window, odds a11y'],
  ['mobile/src/screens/LeagueSummaryScreen.tsx', [/return playoffOddsText\(frac \?\? 0, null, 5\);/], 'League rankings outlook percent chip'],
  ['mobile/src/utils/winNow.ts', [/export const playoffChance = .*playoffOddsText\(n, null, 0\.1\)/], 'Win Now playoff formatter'],
  ['mobile/src/screens/WinNowScreen.tsx', [/Make playoffs: \{playoffChance\(before\.playoff_probability\)\} → \{playoffChance\(after\.playoff_probability\)\}/,
    /Playoffs \{playoffChance\(team\.playoff_probability\)\}/], 'Win Now screen'],
  ['web/js/league-projections.js', [/odds\.miss\(team\.nonplayoff_probability,team,0\.1\):odds\.text\(team\.playoff_probability,team,0\.1\)/,
    /\$\{odds\.text\(rec\.playoff_probability, rec, 1\)\} playoff chance/,
    /b\.playoff_probability-a\.playoff_probability \|\| odds\.rank\(b\)-odds\.rank\(a\)/], 'web Projected standings + outlook prompt + sort'],
  ['web/js/win-now.js', [/const playoffPct = .*FTFPlayoffOdds\.text\(n, null, 0\.1\)/,
    /\['Make playoffs', 'playoff_probability', true, playoffPct\]/, /, playoffPct\(team\.playoff_probability\),/], 'web Win Now'],
];
for (const [file, patterns, what] of pins) {
  const src = read(file);
  const missing = patterns.filter((re) => !re.test(src)).map(String);
  assert(missing.length === 0, `B1. ${what} (${file})`, missing.join(' | '));
}
{
  const html = read('web/index.html');
  const at = (name) => html.indexOf(`/js/${name}`);
  assert(at('playoff-odds.js') > 0 && at('playoff-odds.js') < at('win-now.js') && at('playoff-odds.js') < at('league-projections.js'),
    'B2. web/index.html loads playoff-odds.js before win-now.js and league-projections.js');
}
{
  // Sweep: a playoff chance never formatted any other way. A line that names a
  // playoff probability AND formats a percent must go through the helper.
  const files = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(path.join(ROOT, dir), { withFileTypes: true })) {
      const rel = `${dir}/${e.name}`;
      if (e.isDirectory()) walk(rel);
      else if (/\.(ts|tsx|js)$/.test(e.name)) files.push(rel);
    }
  };
  walk('mobile/src');
  walk('web/js');
  const FIELD = /\b(non)?playoff_(probability|pct)\b/;
  const FORMAT = /\*\s*100|toFixed\(|\bpct\(|\bprobability\(|Math\.round\(|formatPct\(/;
  const HELPER = /playoffOddsText|missOddsText|playoffChance\(|playoffPct\(|odds\.(text|miss)\(|oddsText\(|roundedPct\(/;
  const offenders = [];
  for (const rel of files) {
    if (/playoffOdds\.ts$|playoff-odds\.js$/.test(rel)) continue;
    read(rel).split('\n').forEach((line, i) => {
      if (FIELD.test(line) && FORMAT.test(line) && !HELPER.test(line)) offenders.push(`${rel}:${i + 1}: ${line.trim().slice(0, 120)}`);
    });
  }
  // Known, deliberately left: Win Now deltas in percentage points (not a chance).
  const allowed = [/impact\(before\.playoff_probability, after\.playoff_probability, true\)/];
  const left = offenders.filter((o) => !allowed.some((re) => re.test(o)));
  assert(left.length === 0, 'B3. no playoff chance is formatted outside the helper (mobile/src, web/js)', left.join('\n      '));
}

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
