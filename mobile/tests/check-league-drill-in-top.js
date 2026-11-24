#!/usr/bin/env node
// League rankings › tap a team: the roster drill-in opens at the top.
//
// WHY THIS EXISTS. The drill-in is not a new page: LeagueSummaryScreen swaps
// the ranked list for the team's roster panel INSIDE the same ScrollView. A
// tap on a row halfway down the list therefore opened the roster at the
// list's offset, with the team header and the first players scrolled off
// (Release simulator pass, 2026-11-22).
//
// Pinned (EXECUTED): `openTeam` is cut out of the screen, transpiled and run
// against stub state. A 'row' or 'bar' open calls scrollTo({ y: 0 }) on the
// page's ScrollView; a 'home_tile' open does not (D-269's own landing,
// `applyOwnLanding`, places that one). The open still selects the team and
// still emits `league_team_opened` first.
//
// HONEST LABEL (G-035): this runs the real handler, not the ScrollView; that
// the ref is the page's ScrollView is a wiring check (ref={scrollRef}).
//
// Run: node tests/check-league-drill-in-top.js   (or: npm run test:league-drill-in-top)

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

const SRC = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'screens', 'LeagueSummaryScreen.tsx'), 'utf8');

let failures = 0;
const assert = (cond, name, detail) => {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
};

// Cut `const openTeam = (…) => { … };` by brace balance.
function cutOpenTeam(src) {
  const start = src.indexOf('const openTeam = (');
  if (start === -1) return null;
  const open = src.indexOf('{', src.indexOf('=>', start));
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1;
    else if (src[i] === '}') {
      depth -= 1;
      if (depth === 0) return src.slice(start, i + 1) + ';';
    }
  }
  return null;
}

const fnSrc = cutOpenTeam(SRC);
assert(!!fnSrc, '0. openTeam found in LeagueSummaryScreen.tsx');
if (!fnSrc) process.exit(1);

const js = ts.transpileModule(`${fnSrc}\nmodule.exports = openTeam;`, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

function run(via, prior) {
  const log = [];
  const env = {
    focusRef: { current: prior },
    emitTeamClosed: (why) => log.push(['closed', why]),
    track: (name) => log.push(['track', name]),
    basis: 'consensus',
    subset: 'all',
    posFilter: new Set(),
    route: { name: 'LeagueRankings' },
    setSelectedId: (id) => log.push(['select', id]),
    scrollRef: { current: { scrollTo: (o) => log.push(['scrollTo', o]) } },
  };
  const mod = { exports: {} };
  const names = Object.keys(env);
  // eslint-disable-next-line no-new-func
  new Function('module', 'exports', ...names, js)(mod, mod.exports, ...names.map((k) => env[k]));
  mod.exports('team-9', via, 7);
  return log;
}

for (const via of ['row', 'bar']) {
  const log = run(via, null);
  const scroll = log.find((e) => e[0] === 'scrollTo');
  assert(
    !!scroll && scroll[1].y === 0,
    `1. a '${via}' open scrolls the page to y 0`,
    JSON.stringify(log),
  );
  const iTrack = log.findIndex((e) => e[0] === 'track');
  const iSelect = log.findIndex((e) => e[0] === 'select' && e[1] === 'team-9');
  assert(iTrack !== -1 && iSelect > iTrack,
    `2. a '${via}' open still emits league_team_opened, then selects the team`, JSON.stringify(log));
}
{
  const log = run('row', { id: 'team-2', at: 1, rank: 2 });
  assert(log.some((e) => e[0] === 'closed' && e[1] === 'refocus')
    && log.some((e) => e[0] === 'scrollTo' && e[1].y === 0),
  '3. jumping from another open team: refocus close, then the new team opens at the top', JSON.stringify(log));
}
{
  const log = run('home_tile', null);
  assert(!log.some((e) => e[0] === 'scrollTo'),
    "4. a 'home_tile' open does not scroll (applyOwnLanding places it)", JSON.stringify(log));
}
assert(/<ScrollView\s+ref=\{scrollRef\}/.test(SRC),
  '5. scrollRef is the page ScrollView the drill-in renders in (wiring)');

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll league-drill-in-top checks passed.');
