#!/usr/bin/env node
// Session-init cache seed — unit + structural checks.
//
// initLeagueSession / buildSessionInitBody fetch this league's Sleeper
// rosters + users to build the /api/session/init body. They run on every
// cold start and foreground resume (useSession.revalidateSession), on
// league switch and on connect. Four surfaces then re-request the identical
// two endpoints. `state/queryClient.seedLeagueSessionCaches` hands the
// already-fetched arrays to the cache so they don't.
//
// Mobile has no jest harness (D-056), so U-1..U-4 transpile the REAL
// src/state/queryClient.ts with the project's typescript and run it under
// plain node against a stub QueryClient that records setQueryData — the
// check-offer-prefill-330-unit.js idiom. S-1..S-3 are structural: they pin
// the wiring (every initLeagueSession caller seeds) and the staleTime that
// makes a seed survive to the consumer's mount, neither of which a unit
// test on the helper alone can see.
//
// Every check names the sabotage that turns it red:
//   U-1: setQueryData called with the wrong key shape
//   U-2: the Array.isArray guards dropped (a non-Sleeper league would seed
//        `undefined`, poisoning the cache with a permanent empty answer)
//   U-3: leagueId dropped from the key (league switch would cross-serve)
//   S-1: a seedLeagueSessionCaches call removed from a useSession path
//   S-2: a consumer's staleTime lowered/removed ⇒ refetchOnMount refetches
//        anyway and the seed buys nothing
//
// Run: node tests/check-session-seed.js

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

const ROOT = path.join(__dirname, '..');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), 'utf8');
}

function load(rel, requireShim) {
  const source = read(rel);
  const out = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const moduleShim = { exports: {} };
  new Function('module', 'exports', 'require', out)(
    moduleShim,
    moduleShim.exports,
    requireShim,
  );
  return moduleShim.exports;
}

// ── Stub QueryClient: records every setQueryData(key, data) ─────────────
const writes = [];
class StubQueryClient {
  setQueryData(key, data) {
    writes.push({ key, data });
  }
}

const { seedLeagueSessionCaches } = load('src/state/queryClient.ts', (name) => {
  if (name === '@tanstack/react-query') return { QueryClient: StubQueryClient };
  throw new Error(
    `queryClient.ts gained an unexpected runtime import ("${name}") — extend the ` +
      'shim deliberately, do not let it pass silently.',
  );
});

const ROSTERS = [
  { owner_id: 'u1', roster_id: 1, players: ['p1', 'p2'] },
  { owner_id: 'u2', roster_id: 2, players: ['p3'] },
];
const USERS = [
  { user_id: 'u1', username: 'one', display_name: 'One' },
  { user_id: 'u2', username: 'two', display_name: 'Two' },
];

// ═══════════════════════════════════════════════════════════════════════
// U-1 — a Sleeper seed writes both keys, with the fetched arrays verbatim
// ═══════════════════════════════════════════════════════════════════════
writes.length = 0;
seedLeagueSessionCaches('L1', { rosters: ROSTERS, leagueUsers: USERS });

assert(writes.length === 2, 'U-1a a Sleeper seed writes exactly two cache entries',
  `got ${writes.length}`);

const rosterWrite = writes.find((w) => w.key[0] === 'league-rosters');
const usersWrite = writes.find((w) => w.key[0] === 'league-users');

assert(
  !!rosterWrite && rosterWrite.key.length === 2 && rosterWrite.key[1] === 'L1',
  "U-1b rosters land on ['league-rosters', leagueId] — the consumers' key",
  `got ${JSON.stringify(rosterWrite && rosterWrite.key)}`,
);
assert(
  !!usersWrite && usersWrite.key.length === 2 && usersWrite.key[1] === 'L1',
  "U-1c users land on ['league-users', leagueId]",
  `got ${JSON.stringify(usersWrite && usersWrite.key)}`,
);
// Shape identity: the consumers' queryFns are bare getLeagueRosters /
// getLeagueUsers with no post-processing, so the seeded value must be the
// SAME reference the fetch returned — anything reshaped here would serve a
// different object than a real fetch would.
assert(
  rosterWrite && rosterWrite.data === ROSTERS && usersWrite && usersWrite.data === USERS,
  'U-1d the fetched arrays are seeded verbatim (same reference, no reshaping)',
);

// ═══════════════════════════════════════════════════════════════════════
// U-2 — a non-Sleeper league (ESPN/MFL/Fleaflicker) seeds NOTHING
// ═══════════════════════════════════════════════════════════════════════
writes.length = 0;
seedLeagueSessionCaches('L2', {});
assert(writes.length === 0, 'U-2a an empty seed (ESPN/MFL/Fleaflicker) writes nothing',
  `got ${JSON.stringify(writes)}`);

seedLeagueSessionCaches('L2', { rosters: undefined, leagueUsers: undefined });
assert(writes.length === 0, 'U-2b explicit undefined members write nothing — never seed undefined');

seedLeagueSessionCaches('L2', null);
seedLeagueSessionCaches('L2', undefined);
assert(writes.length === 0, 'U-2c a null/undefined seed writes nothing');

seedLeagueSessionCaches('', { rosters: ROSTERS, leagueUsers: USERS });
seedLeagueSessionCaches(null, { rosters: ROSTERS, leagueUsers: USERS });
assert(writes.length === 0, 'U-2d a missing leagueId writes nothing (no keyless seed)');

// ═══════════════════════════════════════════════════════════════════════
// U-3 — a rosters-only seed writes only that key; the id is per-league
// ═══════════════════════════════════════════════════════════════════════
writes.length = 0;
seedLeagueSessionCaches('L3', { rosters: ROSTERS });
assert(
  writes.length === 1 && writes[0].key[0] === 'league-rosters' && writes[0].key[1] === 'L3',
  'U-3a a partial seed writes only the half that was fetched, keyed by ITS league',
  `got ${JSON.stringify(writes.map((w) => w.key))}`,
);

// ═══════════════════════════════════════════════════════════════════════
// S-1 — every initLeagueSession caller in the state layer seeds
// ═══════════════════════════════════════════════════════════════════════
const useSessionSrc = read('src/state/useSession.ts');
const initCalls = (useSessionSrc.match(/initLeagueSession\(/g) || []).length;
const seedCalls = (useSessionSrc.match(/seedLeagueSessionCaches\(/g) || []).length;
assert(
  initCalls > 0 && seedCalls >= initCalls,
  'S-1a every useSession initLeagueSession call is paired with a seed',
  `${initCalls} initLeagueSession call(s), ${seedCalls} seed call(s)`,
);
assert(
  /revalidateSession[\s\S]{0,1200}?seedLeagueSessionCaches\(/.test(useSessionSrc),
  'S-1b revalidateSession seeds — the cold-start / foreground-resume path',
);

const pickerSrc = read('src/screens/LeaguePickerScreen.tsx');
assert(
  /buildSessionInitBody\([^)]*seed\)/.test(pickerSrc)
    && /seedLeagueSessionCaches\(/.test(pickerSrc),
  'S-1c LeaguePicker passes the seedOut to buildSessionInitBody and seeds it',
);

// ═══════════════════════════════════════════════════════════════════════
// S-2 — the consumers keep a staleTime long enough to honor a fresh seed.
//       With staleTime 0 (or the 30s client default) refetchOnMount fires
//       anyway and the seed buys nothing.
// ═══════════════════════════════════════════════════════════════════════
const CONSUMERS = [
  ['src/screens/TradesScreen.tsx', 'league-rosters'],
  ['src/screens/TradesScreen.tsx', 'league-users'],
  ['src/components/InLeagueCalculator.tsx', 'league-rosters'],
  ['src/components/TradeDnaSheet.tsx', 'league-rosters'],
  ['src/screens/TradeFinderHubScreen.tsx', 'league-users'],
];
for (const [rel, key] of CONSUMERS) {
  const src = read(rel);
  // The useQuery options block from the queryKey to its closing `});`.
  const block = new RegExp(
    `queryKey: \\['${key}', leagueId\\][\\s\\S]{0,400}?\\n  \\}\\);`,
  ).exec(src);
  const staleOk = !!block && /staleTime:\s*5\s*\*\s*60_000/.test(block[0]);
  assert(
    staleOk,
    `S-2 ${path.basename(rel)} ['${key}'] keeps staleTime: 5 * 60_000 so a seed survives to mount`,
    block ? 'options block found but staleTime is not 5 * 60_000' : 'query options block not found',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// S-3 — the layering rule: api/* must not reach the QueryClient. The seed
//       type lives in api/auth.ts; the WRITE lives in state/queryClient.ts.
// ═══════════════════════════════════════════════════════════════════════
const authSrc = read('src/api/auth.ts');
assert(
  /export interface SessionInitSeed/.test(authSrc),
  'S-3a api/auth.ts exports SessionInitSeed',
);
// Import statements only — the prose comments naming the helper are fine.
const authImports = (authSrc.match(/^import[\s\S]*?;$/gm) || []).join('\n');
assert(
  !/queryClient|@tanstack\/react-query/.test(authImports),
  'S-3b api/auth.ts still imports no QueryClient (api layer may not reach state)',
  authImports.split('\n').filter((l) => /queryClient|tanstack/.test(l)).join(' | '),
);
// The seed must not ride the POSTed body — SessionInitBody is sent verbatim.
assert(
  !/rosters:\s*rosters[\s\S]{0,80}?league_id:/.test(authSrc)
    && !/user_player_ids[\s\S]{0,400}?leagueUsers:/.test(authSrc),
  'S-3c the seed is not folded into the POSTed SessionInitBody',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All session-init cache-seed checks passed.');
