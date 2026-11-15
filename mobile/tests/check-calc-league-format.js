#!/usr/bin/env node
// D-268 (docs/plans/league-format-source/spec.md) — the in-league
// calculator defaults to the LEAGUE's stored scoring format.
//
// WHY THIS EXISTS. The calculator used to default to the app-wide format
// (useSession.activeFormat), which the Tiers/Trios SF/1QB toggle can hold on
// the other format, so a one-QB league opened the calculator on superflex
// values. It now reads the league's own format (GET /api/league/format-stats
// `default_scoring`, the same ['league-format', leagueId] query RootNav's
// useLeagueFormatDefault reads) and only falls back to the app-wide format
// while that is unknown. A chip tap still overrides locally. Each assertion
// names the sabotage it detects.
//
// Run: node tests/check-calc-league-format.js

'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
function assert(cond, name) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}`);
  }
}

const ROOT = path.join(__dirname, '..');
const stripComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
const calc = stripComments(fs.readFileSync(
  path.join(ROOT, 'src/components/InLeagueCalculator.tsx'), 'utf8'));
const hook = stripComments(fs.readFileSync(
  path.join(ROOT, 'src/hooks/useScoringFormat.ts'), 'utf8'));

// Sabotage: default back to the session format first.
assert(/const format: ScoringFormat = formatChoice \?\? leagueFormat \?\? sessionFormat \?\? '1qb_ppr';/.test(calc),
  'format precedence is chip choice, then league format, then app-wide format');

// Sabotage: a different key would not share RootNav's cached read.
assert(/queryKey: \['league-format', leagueId\],\s*queryFn: \(\) => getLeagueFormatStats\(leagueId\)/.test(calc),
  "league format comes from the ['league-format', leagueId] format-stats query");
assert(/queryKey: \['league-format', leagueId\],\s*queryFn: \(\) => getLeagueFormatStats\(leagueId!\)/.test(hook),
  'RootNav useLeagueFormatDefault reads the same key and endpoint');

// Sabotage: trusting an unknown string as a format.
assert(/storedLeagueFormat === '1qb_ppr' \|\| storedLeagueFormat === 'sf_tep' \? storedLeagueFormat : null/.test(calc),
  'only the two known formats are accepted from the server');

// The chip override is unchanged: still local state.
assert(/const \[formatChoice, setFormatChoice\] = useState<ScoringFormat \| null>\(null\);/.test(calc),
  'chip override stays local to the calculator');

if (failures) {
  console.error(`check-calc-league-format: ${failures} failed`);
  process.exit(1);
}
console.log('check-calc-league-format: all assertions passed');
