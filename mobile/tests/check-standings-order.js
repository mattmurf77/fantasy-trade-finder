#!/usr/bin/env node
// Current standings ordering (Home hub, flag `nav.home_hub`;
// docs/plans/home-engagement/scope.md).
//
// WHY THIS EXISTS. Home's Standings row ("5–1 · 2nd of 12") and the new
// Standings page's Current tab both come from src/utils/standings.ts, which
// turns Sleeper rosters' `settings.{wins,losses,ties,fpts,fpts_decimal}` into
// a computed place (Sleeper exposes no standings rank). A wrong tiebreak or a
// dropped tie shows a user a place they don't hold, on the screen they open
// most. This transpiles and EXECUTES the util under plain node.
//
// Pins: win % with a tie as half a win, then points for, then roster_id;
// points for = fpts + fpts_decimal / 100; the en-dash record format with an
// optional tie; the "you" row from the caller's roster id; the before-week-1
// and non-Sleeper (no `settings`) summaries; zero runtime imports; and that
// api/sleeper.ts RosterRow still declares the `settings` it reads.
//
// Run: node tests/check-standings-order.js
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

const UTIL_REL = 'src/utils/standings.ts';
const src = read(UTIL_REL);
assert(!/^\s*import\s+(?!type\b)/m.test(src), '0a. standings.ts has zero runtime imports');
const s = (() => {
  const js = ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const m = { exports: {} };
  new Function('module', 'exports', 'require', js)(m, m.exports, () => {
    throw new Error('standings.ts must not require anything at runtime');
  });
  return m.exports;
})();

const sleeperSrc = read('src/api/sleeper.ts');
const rosterRow = (sleeperSrc.match(/export interface RosterRow \{[\s\S]*?\n\}/) || [''])[0];
assert(
  /settings\?:\s*\{[\s\S]*wins\?[\s\S]*losses\?[\s\S]*ties\?[\s\S]*fpts\?[\s\S]*fpts_decimal\?/.test(rosterRow),
  '0b. api/sleeper.ts RosterRow declares settings.{wins,losses,ties,fpts,fpts_decimal}',
);

const roster = (id, owner, w, l, t, fpts, dec) => ({
  roster_id: id,
  owner_id: owner,
  settings: { wins: w, losses: l, ties: t, fpts, fpts_decimal: dec },
});
const users = [
  { user_id: 'a', display_name: 'Alpha' },
  { user_id: 'b', display_name: null, username: 'bravo_u' },
  { user_id: 'c', display_name: 'Charlie' },
  { user_id: 'd', display_name: 'Delta' },
  { user_id: 'e', display_name: 'Echo' },
];

// 1. ordering
{
  const st = s.currentStandings(
    [
      roster(1, 'a', 4, 2, 0, 800, 0),  // .667
      roster(2, 'b', 4, 1, 1, 700, 0),  // .750 (tie = half a win) ⇒ ahead of 4–2
      roster(3, 'c', 4, 2, 0, 810, 50), // .667, more PF than roster 1
      roster(4, 'd', 4, 2, 0, 800, 0),  // .667, same PF as roster 1 ⇒ roster_id
      roster(5, 'e', 0, 6, 0, 900, 0),  // .000 despite the most PF
    ],
    users,
    1,
  );
  assert(st.rows.map((r) => r.rosterId).join() === '2,3,1,4,5', '1a. win % (tie = ½ win), then points for, then roster_id');
  assert(st.rows.map((r) => r.place).join() === '1,2,3,4,5', '1b. places are 1..n, unique');
  assert(st.rows[1].pointsFor === 810.5, '1c. points for = fpts + fpts_decimal / 100');
  assert(st.rows[0].name === 'bravo_u' && st.rows[1].name === 'Charlie', '1d. name = display_name, else username');
  assert(st.you && st.you.rosterId === 1 && st.you.place === 3 && st.rows.filter((r) => r.isYou).length === 1,
    '1e. exactly one "you" row, from the caller\'s roster id');
  assert(st.gamesPlayed === true && st.hasRecords === true && st.teamCount === 5, '1f. gamesPlayed / hasRecords / teamCount');
}

// 2. formatting + summary
{
  assert(s.formatRecord(5, 1, 0) === '5–1' && s.formatRecord(5, 0, 1) === '5–0–1',
    '2a. record format: en dash, tie appended only when non-zero');
  const st = s.currentStandings([roster(1, 'a', 5, 1, 0, 790, 20), roster(2, 'b', 6, 0, 0, 812, 40), roster(3, 'c', 3, 3, 0, 700, 0)], users, 1);
  const sum = s.standingsSummary(st);
  assert(sum.kind === 'record' && sum.record === '5–1' && sum.place === 2 && sum.teamCount === 3,
    '2b. summary = your record, your place, team count (format the place with positionSplit.ordinal)');
  const pre = s.currentStandings([roster(1, 'a', 0, 0, 0, 0, 0), roster(2, 'b', 0, 0, 0, 0, 0)], users, 1);
  assert(pre.gamesPlayed === false && s.standingsSummary(pre).kind === 'no_games',
    '2c. before week 1 (every record 0–0) ⇒ no_games, not a ranked 0–0 tie');
  const espn = s.currentStandings([{ roster_id: 1, owner_id: 'a', players: [] }, { roster_id: 2, owner_id: 'b', players: [] }], users, 1);
  assert(espn.hasRecords === false && s.standingsSummary(espn).kind === 'unavailable',
    '2d. rows without `settings` (ESPN/MFL DB snapshot) ⇒ unavailable, never a fabricated 0–0');
  const noYou = s.currentStandings([roster(1, 'a', 1, 0, 0, 100, 0)], users, null);
  assert(noYou.you === null && s.standingsSummary(noYou).kind === 'unavailable', '2e. no roster of yours ⇒ unavailable');
  assert(s.winPct(0, 0, 0) === 0 && s.pointsFor(null) === 0, '2f. empty inputs are 0, never NaN');
  const unknownOwner = s.currentStandings([roster(7, null, 1, 0, 0, 100, 0)], users, 7);
  assert(unknownOwner.rows[0].name === 'Team 7', '2g. an ownerless roster is named "Team <roster_id>"');
}

if (failures) {
  console.error(`\n${failures} failure(s), ${passes} passed`);
  process.exit(1);
}
console.log(`\nAll standings-order checks passed (${passes}).`);
