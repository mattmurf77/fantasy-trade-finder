#!/usr/bin/env node
// #307 (frozen Matches-side contract, wave-league @ 6368e31 §4.3) — the
// league-scoped deep link into the Matches inbox.
//
// Named sabotage (per §4.3's explicit ask):
//   S-10 re-tap: key the FB-91 effect's dep array on `leagueId` only (drop
//        `route.params?.at`) → the FIRST tap demos perfectly, but
//        tile → manually flip the chip to "All" → tap the SAME tile again
//        silently does nothing (identical leagueId, no re-run). Pinned: the
//        effect reads route.params?.leagueId AND its dep array includes
//        route.params?.at.
//
// Also pinned: the lenient consumer (absent/empty leagueId leaves the
// filter untouched — push-tap routing and plain tab presses unaffected by
// construction) and the frozen chip testIDs the LeagueHome group's Maestro
// flow asserts.
//
// Run: node tests/check-matches-league-param.js

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const stripComments = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, '$1');

const SCREEN = stripComments(
  fs.readFileSync(path.join(MOBILE, 'src/screens/MatchesScreen.tsx'), 'utf8'),
);
const flat = SCREEN.replace(/\s+/g, ' ');

let failures = 0;
const ok = (name) => console.log(`PASS  ${name}`);
const fail = (name, detail) => {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
};
const assert = (cond, name, detail) => (cond ? ok(name) : fail(name, detail));

// Isolate the FB-91 effect: the useEffect whose body reads route.params.
const effIdx = flat.indexOf('useEffect(() => { const s = route.params?.segment;');
assert(effIdx > -1, '1. the FB-91 route-params effect exists');
const effEnd = flat.indexOf(']);', effIdx);
const EFF = flat.slice(effIdx, effEnd + 3);

assert(
  /const lid = route\.params\?\.leagueId;/.test(EFF),
  '2. effect reads route.params?.leagueId (frozen §4.3 param contract)',
);
assert(
  /if \(typeof lid === 'string' && lid\) setFilterLeagueId\(lid\);/.test(EFF),
  '3. lenient consumer — only a non-empty string rescopes; absent param leaves the filter untouched',
);
{
  const depsMatch = EFF.match(/\}, \[([^\]]*)\]\);/);
  const deps = depsMatch ? depsMatch[1] : '';
  assert(
    /route\.params\?\.leagueId/.test(deps),
    '4. dep array includes route.params?.leagueId',
    `deps: [${deps}]`,
  );
  assert(
    /route\.params\?\.at/.test(deps),
    '5. S-10 — dep array includes route.params?.at (the re-tap contract)',
    `deps: [${deps}]`,
  );
  assert(
    /route\.params\?\.segment/.test(deps),
    '6. dep array keeps route.params?.segment (FB-91 unbroken)',
    `deps: [${deps}]`,
  );
}

// ── Frozen chip testIDs (asserted by wave-league's Maestro flow) ───────────
assert(
  /testID=\{c\.id === 'all' \? 'matches\.league-chip\.all' : `matches\.league-chip\.\$\{c\.id\}`\}/.test(flat),
  '7. chip testIDs — matches.league-chip.all / matches.league-chip.<league_id> (frozen grammar)',
);
assert(
  /accessibilityState=\{\{ selected: isActive \}\}/.test(flat),
  '8. chip selection stays asserted via accessibilityState (frozen §4.3)',
);
{
  // Template-literal IDs are lint-invisible — the allow-list must carry the
  // glob or wave-league's flow trips testid-lint at merge.
  const allow = fs.readFileSync(
    path.join(MOBILE, 'scripts/testid-lint-allow.txt'),
    'utf8',
  );
  assert(
    allow.split('\n').some((l) => l.trim() === 'matches.league-chip.*'),
    '9. testid-lint-allow.txt carries matches.league-chip.* (template-literal id)',
  );
}

console.log(failures ? `\n${failures} FAILURE(S)` : '\nALL CHECKS PASSED (9)');
process.exit(failures ? 1 : 0);
