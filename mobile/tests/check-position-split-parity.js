#!/usr/bin/env node
// Position split parity (Home hub, flag `nav.home_hub`;
// docs/plans/home-engagement/scope.md W4).
//
// WHY THIS EXISTS. Home says "RB · 2nd /12 · Seller" and its Buy/Sell buttons
// land on League rankings filtered to RB, where the user sees the SAME teams
// with Seller/Buyer badges either side of a median line. If Home and League
// rankings disagree about who is a Seller, the feature lies on its front door.
// The operator approved DUPLICATING the arithmetic into
// src/utils/positionSplit.ts rather than extracting it out of
// LeagueSummaryScreen.tsx, because tests/check-league-candidates-300.js pins
// the screen's inline source text. Duplication is only safe with a guard that
// fails the moment the two copies diverge. This is that guard.
//
// HOW. It does not pattern-match the screen. It EXECUTES the screen's own
// code: the TypeScript AST yields LeagueSummaryScreen's real `computeSubset`,
// `activeTotal`, `CORE_POSITIONS`, and the bodies of `ranked`, `cutAfter`,
// `bandSize` and `bandFor`; they are transpiled and run beside the util over
// ~2,000 seeded random leagues (ties, missing positions, odd/even counts,
// absent and off-centre medians) plus named fixtures. Every team's order,
// the cut, the band size and every band must match exactly.
//
// Sabotage-proven 2026-10-10, each reverted: the util's `>=` → `>` fails §1e
// and §2; the screen's `idx < bandSize` → `<=` fails §2; the screen's `0.33`
// → `0.34` fails §2 (it only bites above 24 teams, hence the 32-team range).
//
// Dependency-free apart from the TypeScript compiler already in node_modules.
// Run: node tests/check-position-split-parity.js
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
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`);
  }
};
const pass = (name) => console.log(`PASS  ${name}`);

const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const transpile = (src) =>
  ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;

// ── load the util ─────────────────────────────────────────────────────────
const UTIL_REL = 'src/utils/positionSplit.ts';
const utilSrc = read(UTIL_REL);
assert(
  !/^\s*import\s+(?!type\b)/m.test(utilSrc),
  '0a. positionSplit.ts has zero runtime imports',
  'a runtime import breaks plain-node execution of this guard',
);
const util = (() => {
  const m = { exports: {} };
  new Function('module', 'exports', 'require', transpile(utilSrc))(m, m.exports, () => {
    throw new Error('positionSplit.ts must not require anything at runtime');
  });
  return m.exports;
})();

// ── extract LeagueSummaryScreen's inline arithmetic ──────────────────────
const SCREEN_REL = 'src/screens/LeagueSummaryScreen.tsx';
const screenText = read(SCREEN_REL);
const sf = ts.createSourceFile(SCREEN_REL, screenText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function find(pred) {
  let hit = null;
  (function walk(n) {
    if (hit) return;
    if (pred(n)) {
      hit = n;
      return;
    }
    ts.forEachChild(n, walk);
  })(sf);
  return hit;
}
const fnDecl = (name) => find((n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === name);
const varDecl = (name) => find((n) => ts.isVariableDeclaration(n) && n.name.getText() === name);
/** First argument of `useMemo(...)` in `const <name> = useMemo(() => {...}, deps)`. */
function memoArrow(name) {
  const d = varDecl(name);
  if (!d || !d.initializer || !ts.isCallExpression(d.initializer)) return null;
  const arg = d.initializer.arguments[0];
  return arg && ts.isArrowFunction(arg) ? arg.getText() : null;
}

const extracted = {
  coreDecl: varDecl('CORE_POSITIONS'),
  computeSubset: fnDecl('computeSubset'),
  activeTotal: fnDecl('activeTotal'),
  rankedArrow: memoArrow('ranked'),
  cutAfterArrow: memoArrow('cutAfter'),
  bandSizeInit: varDecl('bandSize') && varDecl('bandSize').initializer
    ? varDecl('bandSize').initializer.getText()
    : null,
  bandForInit: varDecl('bandFor') && varDecl('bandFor').initializer
    ? varDecl('bandFor').initializer.getText()
    : null,
};
for (const [k, v] of Object.entries(extracted)) {
  assert(!!v, `0b. LeagueSummaryScreen.${k} is findable`, 'renamed or restructured — re-point this guard AND check-league-candidates-300.js');
}
if (failures) {
  console.error(`\n${failures} failure(s) — cannot extract the screen's arithmetic`);
  process.exit(1);
}

// The screen's module-level helpers, verbatim, as one JS module.
const screenHelpers = (() => {
  const src = [
    `const ${extracted.coreDecl.getText()};`,
    extracted.computeSubset.getText(),
    extracted.activeTotal.getText(),
    'module.exports = { CORE_POSITIONS, computeSubset, activeTotal };',
  ].join('\n');
  const m = { exports: {} };
  new Function('module', 'exports', transpile(src))(m, m.exports);
  return m.exports;
})();
const evalArrow = (params, arrowText) =>
  new Function(...params, `return (${transpile(`(${arrowText})`).trim().replace(/;$/, '')});`);
const lsRankedFactory = evalArrow(
  ['computed', 'activeTotal', 'subset', 'posFilter', 'picksAlwaysCounted'],
  extracted.rankedArrow,
);
const lsCutAfterFactory = evalArrow(['candidatePos', 'medianAtPos', 'ranked'], extracted.cutAfterArrow);
const lsBandSize = evalArrow(['cutAfter', 'ranked'], extracted.bandSizeInit);
const lsBandForFactory = evalArrow(['bandSize', 'ranked'], extracted.bandForInit);

/** League rankings' view of one position, computed by the SCREEN's code. */
function screenSplit(payload, pos, picksAlwaysCounted) {
  const computed = payload.teams.map((t) => screenHelpers.computeSubset(t, 'all'));
  const ranked = lsRankedFactory(
    computed,
    screenHelpers.activeTotal,
    'all',
    new Set([pos]),
    picksAlwaysCounted,
  )();
  const m = payload.medians && payload.medians[pos];
  const medianAtPos = m == null ? null : m;
  const cutAfter = lsCutAfterFactory(pos, medianAtPos, ranked)();
  const bandSize = lsBandSize(cutAfter, ranked);
  const bandFor = lsBandForFactory(bandSize, ranked);
  return {
    order: ranked.map((r) => r.tc.team.user_id),
    cutAfter,
    bandSize,
    bands: ranked.map((_, i) => bandFor(i)),
  };
}

// ── fixtures ─────────────────────────────────────────────────────────────
function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const POS = ['QB', 'RB', 'WR', 'TE'];
/** The server's `_position_medians`: mean of the middle two for even n, 1 dp. */
function serverMedian(values) {
  if (!values.length) return null;
  const v = [...values].sort((a, b) => a - b);
  const mid = Math.floor(v.length / 2);
  const med = v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
  return Math.round(med * 10) / 10;
}
function randomLeague(rand) {
  // 1–32 teams: Sleeper allows up to 32, and round(n * 0.33) only separates
  // from nearby factors above 24 teams, so a 16-team ceiling would let a
  // band-factor drift through unseen.
  const n = 1 + Math.floor(rand() * 32);
  const youIdx = rand() < 0.85 ? Math.floor(rand() * n) : -1;
  const teams = [];
  for (let i = 0; i < n; i += 1) {
    const positions = {};
    for (const p of POS) {
      const r = rand();
      if (r < 0.07) continue; // position missing entirely
      // Coarse values so ties are common; occasional zero.
      positions[p] = { value: r < 0.15 ? 0 : Math.floor(rand() * 9) * 450 + (rand() < 0.2 ? 0.5 : 0) };
    }
    teams.push({
      user_id: `u${Math.floor(rand() * 1e6).toString(36)}${i}`,
      display_name: `Team ${i}`,
      is_you: i === youIdx,
      positions,
    });
  }
  const medians = {};
  for (const p of POS) {
    const r = rand();
    if (r < 0.1) continue; // absent (old server)
    const vals = teams.map((t) => (t.positions[p] ? t.positions[p].value : 0));
    medians[p] = {
      value: r < 0.2 ? Math.floor(rand() * 9) * 450 : serverMedian(vals),
      value_label: '≈1 firsts',
    };
  }
  return { teams, medians };
}

// ── §1 named fixtures against the util ───────────────────────────────────
function league(values, medianValue, youIndex = 1) {
  return {
    teams: values.map((v, i) => ({
      user_id: `t${String(i).padStart(2, '0')}`,
      display_name: `T${i}`,
      is_you: i === youIndex,
      positions: { RB: { value: v } },
    })),
    medians: medianValue == null ? {} : { RB: { value: medianValue, value_label: '≈2.5 firsts' } },
  };
}
function bandsOf(split) {
  return split.rows.map((r) => (r.band ? r.band[0] : '-')).join('');
}
const desc = (n) => Array.from({ length: n }, (_, i) => (n - i) * 100);
{
  const s12 = util.positionSplit(league(desc(12), serverMedian(desc(12))), 'RB');
  assert(bandsOf(s12) === 'SSSS----BBBB' && s12.state === 'shown', '1a. 12 teams ⇒ 4 / 4 / 4');
  const s10 = util.positionSplit(league(desc(10), serverMedian(desc(10))), 'RB');
  assert(bandsOf(s10) === 'SSS----BBB', '1b. 10 teams ⇒ 3 / 4 / 3');
  const s14 = util.positionSplit(league(desc(14), serverMedian(desc(14))), 'RB');
  assert(bandsOf(s14) === 'SSSSS----BBBBB', '1c. 14 teams ⇒ 5 / 4 / 5');
  const s8 = util.positionSplit(league(desc(8), serverMedian(desc(8))), 'RB');
  assert(bandsOf(s8) === 'SSS--BBB', '1d. 8 teams ⇒ 3 / 2 / 3');
  const odd = util.positionSplit(league(desc(9), serverMedian(desc(9))), 'RB');
  assert(odd.cutAfter === 5 && odd.rows[4].aboveLine === true, '1e. odd count: the team ON the median sits above the line (>=)');
  const flat = util.positionSplit(league([300, 300, 300, 300], 300), 'RB');
  assert(flat.state === 'no_split' && flat.cutAfter === null && bandsOf(flat) === '----', '1f. flat league ⇒ no_split, no bands');
  const none = util.positionSplit(league(desc(6), null), 'RB');
  assert(none.state === 'no_median' && none.cutAfter === null && bandsOf(none) === '------', '1g. no median on the wire ⇒ no_median, no line');
  const tie = util.positionSplit(league([500, 500, 100], 500, -1), 'RB');
  assert(tie.rows.map((r) => r.userId).join(',') === 't00,t01,t02', '1h. equal values order by user_id ascending');
  const you = util.positionSplit(league(desc(12), serverMedian(desc(12)), 1), 'RB');
  assert(you.you && you.you.rank === 2 && you.you.band === 'Seller', '1i. `you` is the is_you row with its rank and band');
  const nobody = util.positionSplit(league(desc(6), 350, -1), 'RB');
  assert(nobody.you === null, '1j. no is_you team ⇒ you === null');
  assert(util.canSplit(league(desc(3), 200)) === true, '1k. canSplit: 3 teams + a median');
  assert(util.canSplit(league(desc(2), 150)) === false, '1l. canSplit: fewer than 3 teams ⇒ false');
  assert(util.canSplit(league(desc(5), null)) === false, '1m. canSplit: no median anywhere ⇒ false');
  assert(
    util.suggestedSide('Seller') === 'sell' && util.suggestedSide('Buyer') === 'buy' && util.suggestedSide(null) === null,
    '1n. suggestedSide: Seller ⇒ sell, Buyer ⇒ buy, none ⇒ null',
  );
  assert(
    util.rankPercentile(1, 12) === 1 && Math.abs(util.rankPercentile(12, 12) - 1 / 12) < 1e-9 && util.rankPercentile(1, 0) === 0,
    '1o. rankPercentile: 1st ⇒ 1, last ⇒ 1/n, empty league ⇒ 0',
  );
  assert(
    ['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '111th']
      .join() === [1, 2, 3, 4, 11, 12, 13, 21, 22, 111].map(util.ordinal).join(),
    '1p. ordinal matches LeagueSummaryScreen (11th–13th, 21st, 111th)',
  );
  {
    // emphasizedSides: every banded position (uncapped by operator decision), mid-pack never.
    const mk = (pos, rank, band, n = 12, state = 'shown') => ({
      position: pos, state, teamCount: n, you: { rank, band },
    });
    const all4 = [mk('QB', 3, 'Seller'), mk('RB', 1, 'Seller'), mk('WR', 11, 'Buyer'), mk('TE', 12, 'Buyer')];
    const e = util.emphasizedSides(all4);
    assert(
      Object.keys(e).sort().join() === 'QB,RB,TE,WR'
        && e.QB === 'sell' && e.RB === 'sell' && e.WR === 'buy' && e.TE === 'buy',
      '1q. emphasizedSides: four banded ⇒ all four, each on its own side (no two-tile cap)',
    );
    const mixed = util.emphasizedSides([mk('QB', 6, null), mk('RB', 2, 'Seller'), mk('WR', 4, 'Seller', 12, 'no_split')]);
    assert(
      Object.keys(mixed).join() === 'RB' && mixed.RB === 'sell',
      '1r. emphasizedSides: mid-pack and no-line positions are never emphasized',
    );
  }
  if (!failures) pass('§1 named fixtures (18 assertions)');
}

// ── §2 executable parity: the util vs the screen's own code ──────────────
{
  const before = failures;
  const rand = mulberry32(20261010);
  let compared = 0;
  for (let i = 0; i < 2000; i += 1) {
    const lg = randomLeague(rand);
    for (const p of POS) {
      for (const pac of [true, false]) {
        const s = screenSplit(lg, p, pac);
        const u = util.positionSplit(lg, p);
        const same =
          s.order.join() === u.rows.map((r) => r.userId).join() &&
          s.cutAfter === u.cutAfter &&
          s.bandSize === u.bandSize &&
          s.bands.join() === u.rows.map((r) => r.band).join();
        compared += 1;
        if (!same) {
          assert(false, `2. parity at league #${i} ${p} (picksAlwaysCounted=${pac})`,
            `screen ${JSON.stringify(s)}\n      util   ${JSON.stringify({
              order: u.rows.map((r) => r.userId), cutAfter: u.cutAfter, bandSize: u.bandSize,
              bands: u.rows.map((r) => r.band),
            })}`);
          break;
        }
      }
      if (failures > before) break;
    }
    if (failures > before) break;
  }
  if (failures === before) {
    passes += 1;
    pass(`§2 util === LeagueSummaryScreen's inline arithmetic over ${compared} randomised position views`);
  }
}

if (failures) {
  console.error(`\n${failures} failure(s), ${passes} passed`);
  process.exit(1);
}
console.log(`\nAll position-split parity checks passed (${passes}).`);
