#!/usr/bin/env node
// #334/#335 (G9, 2026-08-16) — MatchesScreen derivations and counts.
//
// Two halves:
//   U-1…U-5 — EXECUTED unit tests: transpile the real pure module
//     (src/utils/matchesDerive.ts — zero runtime imports by design) with the
//     project's typescript and run it under plain node. Same idiom as
//     check-trade-text.js / check-session-rerank.js (mobile has no jest).
//   S-11a…f — structural pins on MatchesScreen.tsx: count-fabrication and
//     Chalkline-construction guards.
//
// Named sabotages (each proven RED during authoring, QA notes in
// docs/feedback/items/334-matches-dismiss-latency/qa-notes.md):
//   U-1: drop the hiddenKeys test from filterVisible → hidden rows render.
//   U-2: latch hidden keys permanently (module-level memo) → undo can't
//        restore the row.
//   U-3-count: return 0/{} for undefined input → fabricated 0 before the
//        first fetch resolves.
//   U-4: derive counts from the raw array (screen side: use
//        matchesQuery.data.length) → count and list disagree mid-dismiss.
//   U-5: ignore the league filter (swap the inputs) → pill counts stop
//        respecting the active chip.
//
// Run: node tests/check-matches-counts.js

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

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const stripComments = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, '$1');

let failures = 0;
const ok = (name) => console.log(`PASS  ${name}`);
const fail = (name, detail) => {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
};
const assert = (cond, name, detail) => (cond ? ok(name) : fail(name, detail));
const eq = (name, actual, expected) =>
  assert(
    JSON.stringify(actual) === JSON.stringify(expected),
    name,
    `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
  );

// ── Load the real pure module under plain node ─────────────────────────────
const js = ts.transpileModule(read('src/utils/matchesDerive.ts'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const moduleShim = { exports: {} };
new Function('module', 'exports', 'require', js)(moduleShim, moduleShim.exports, (name) => {
  throw new Error(
    `matchesDerive.ts gained a runtime import ("${name}") — it must stay pure ` +
      'so this check can run it under plain node.',
  );
});
const {
  filterVisible,
  countsByLeague,
  matchHiddenKey,
  awaitingHiddenKey,
  matchRowKey,
  awaitingRowKey,
} = moduleShim.exports;

// Fixtures — the two row shapes the screen feeds through the helpers.
const M = (league, id) => ({ league_id: league, match_id: id });
const A = (league, trade) => ({ league_id: league, trade_id: trade });
const matches = [M('L1', 'm1'), M('L1', 'm2'), M('L1', 'm3'), M('L2', 'm4'), M('L2', 'm5')];
const awaiting = [A('L1', 't1'), A('L1', 't2'), A('L2', 't3')];
const none = new Set();

// ── Key shapes (prefixed keyExtractor forms — no cross-kind collisions) ────
eq('0a  matchHiddenKey shape', matchHiddenKey('m1'), 'match:m1');
eq('0b  awaitingHiddenKey shape', awaitingHiddenKey('L1', 't1'), 'awaiting:L1:t1');
eq('0c  row adapters agree with the primitive forms', [matchRowKey(matches[0]), awaitingRowKey(awaiting[0])], ['match:m1', 'awaiting:L1:t1']);

// ── U-1 — hidden-key exclusion, both key shapes ────────────────────────────
eq('U-1a hidden match row is absent from filterVisible output',
  filterVisible(matches, 'all', new Set(['match:m2']), matchRowKey).map((m) => m.match_id),
  ['m1', 'm3', 'm4', 'm5']);
eq('U-1b hidden awaiting row is absent (composite key shape)',
  filterVisible(awaiting, 'all', new Set(['awaiting:L1:t1']), awaitingRowKey).map((a) => a.trade_id),
  ['t2', 't3']);

// ── U-2 — hide/unhide round-trip (undo path) ───────────────────────────────
{
  const hidden = new Set(['match:m2']);
  const during = filterVisible(matches, 'all', hidden, matchRowKey);
  hidden.delete('match:m2');
  const after = filterVisible(matches, 'all', hidden, matchRowKey);
  eq('U-2  removing the key restores the row (no latching)',
    [during.length, after.length, after.some((m) => m.match_id === 'm2')],
    [4, 5, true]);
}

// ── U-3 — league scoping + the R-10 no-fabrication sentinel ────────────────
eq("U-3a 'all' passes every league", filterVisible(matches, 'all', none, matchRowKey).length, 5);
eq('U-3b a league id narrows to that league',
  filterVisible(matches, 'L2', none, matchRowKey).map((m) => m.match_id),
  ['m4', 'm5']);
eq('U-3-count  undefined data → null sentinel, NEVER a zero/empty fabrication',
  countsByLeague(undefined), null);
eq('U-3-count2 resolved-but-empty list → honest {} (lookups read 0)',
  countsByLeague([]), {});

// ── U-4 — count/list agreement while a key is hidden ───────────────────────
{
  const hidden = new Set(['match:m1']);
  const visible = filterVisible(matches, 'all', hidden, matchRowKey);
  const counts = countsByLeague(visible);
  eq('U-4a per-league counts equal the visible array per-league lengths mid-hide',
    counts,
    { L1: visible.filter((m) => m.league_id === 'L1').length,
      L2: visible.filter((m) => m.league_id === 'L2').length });
  eq('U-4b hidden row is excluded from its league count (L1: 3 → 2)', counts.L1, 2);
  eq('U-4c totals agree', Object.values(counts).reduce((a, b) => a + b, 0), visible.length);
}

// ── U-5 — pill vs chip scoping ─────────────────────────────────────────────
{
  const hidden = new Set(['awaiting:L1:t2']);
  // Pill count = rows under the ACTIVE league filter (hidden-aware).
  eq('U-5a pill count respects the league filter',
    filterVisible(awaiting, 'L1', hidden, awaitingRowKey).length, 1);
  // Chip counts = the segment array they are fed — matches vs awaiting give
  // different answers for the same league, and neither leaks into the other.
  eq('U-5b chip counts follow the segment array fed (matches vs awaiting)',
    [countsByLeague(filterVisible(matches, 'all', none, matchRowKey)).L1,
      countsByLeague(filterVisible(awaiting, 'all', hidden, awaitingRowKey)).L1],
    [3, 1]);
}

// ── S-11 — structural pins on MatchesScreen.tsx ────────────────────────────
const SCREEN = stripComments(read('src/screens/MatchesScreen.tsx'));
const flat = SCREEN.replace(/\s+/g, ' ');

// S-11a — counts derive from the shared hidden-aware helpers; no raw
// query-data length ever renders.
assert(
  !/matchesQuery\.data\.length/.test(SCREEN)
    && !/awaitingQuery\.data\.length/.test(SCREEN)
    && /countsByLeague\(hiddenAwareMatches/.test(flat)
    && /countsByLeague\(hiddenAwareAwaiting/.test(flat)
    && /hiddenAwareMatches === null \? null : visibleMatches\.length/.test(flat)
    && /hiddenAwareAwaiting === null \? null : visibleAwaiting\.length/.test(flat),
  'S-11a counts derive from the hidden-aware helper family — no raw data.length render sites',
);

// S-11b — awaiting list fetches on mount (no segment-tied enabled) and keeps
// placeholderData parity with matchesQuery.
{
  const q = flat.slice(
    flat.indexOf('const awaitingQuery = useQuery({'),
    flat.indexOf('});', flat.indexOf('const awaitingQuery = useQuery({')),
  );
  assert(
    q.length > 0 && !/enabled:/.test(q) && /placeholderData: \(prev\) => prev/.test(q),
    'S-11b awaitingQuery mount-fetches (no segment-gated enabled) and has placeholderData',
    q ? `block: ${q}` : 'awaitingQuery block not found',
  );
}

// S-11c — the R-10 sentinel branches exist: undefined data renders no count.
assert(
  /matchesQuery\.data === undefined \? null/.test(flat)
    && /awaitingQuery\.data === undefined \? null/.test(flat)
    && /typeof count === 'number' \?/.test(flat)
    && /typeof chipCount === 'number' \?/.test(flat),
  'S-11c undefined-data sentinel present — no fabricated 0 before first resolve',
);

// S-11d — Chalkline construction: bare Plex Mono numeral via fonts.data;
// no CountBadge (its --neg fill is the notification-urgency encoding), no
// nonexistent fonts.mono, no new hex literal on this screen.
{
  const segStyle = flat.slice(flat.indexOf('segmentCount: {'), flat.indexOf('}', flat.indexOf('segmentCount: {')));
  const chipStyle = flat.slice(flat.indexOf('chipCount: {'), flat.indexOf('}', flat.indexOf('chipCount: {')));
  assert(
    !/CountBadge/.test(SCREEN)
      && !/fonts\.mono/.test(SCREEN)
      && !/#[0-9a-fA-F]{3,8}\b/.test(SCREEN)
      && /fontFamily: fonts\.data/.test(segStyle)
      && /fontFamily: fonts\.data/.test(chipStyle)
      && !/semantic\.neg/.test(segStyle)
      && !/semantic\.neg/.test(chipStyle),
    'S-11d counts are bare fonts.data numerals — no CountBadge, no fonts.mono, no hex literals',
  );
}

// S-11e — the 11px type floor holds for both count numerals.
{
  const sizes = [];
  const re = /(segmentCount|chipCount): \{[^}]*fontSize: (\d+)/g;
  let m;
  while ((m = re.exec(flat)) !== null) sizes.push([m[1], Number(m[2])]);
  assert(
    sizes.length === 2 && sizes.every(([, n]) => n >= 11),
    'S-11e count numeral fontSize >= 11 (type floor)',
    JSON.stringify(sizes),
  );
}

// S-11f — no testID changes: the three existing id families survive.
assert(
  /matches\.segment\.mutual/.test(SCREEN)
    && /matches\.segment\.awaiting/.test(SCREEN)
    && /matches\.league-chip\./.test(SCREEN),
  'S-11f matches.segment.mutual / matches.segment.awaiting / matches.league-chip.* all present',
);

console.log(failures ? `\n${failures} FAILURE(S)` : '\nALL CHECKS PASSED');
process.exit(failures ? 1 : 0);
