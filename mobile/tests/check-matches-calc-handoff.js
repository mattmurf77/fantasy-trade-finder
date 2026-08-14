#!/usr/bin/env node
// #319 — Matches → calculator handoff. Matches is a CROSS-LEAGUE inbox but
// TradeCalculatorScreen hard-wires In-league mode to the ACTIVE session
// league, so a cross-league row must switch the active league FIRST.
//
// Named sabotage (plan 2026-08-13):
//   S-5 wrong-league: remove the `league_id !== activeLeagueId` branch and
//       navigate directly → the calculator silently opens the row against
//       the WRONG league's rosters/opponent. No type error; a same-league
//       Maestro flow stays green.
//
// Also pinned (uncrossed prefill): giveIds ← my_side_player_ids and
// receiveIds ← their_side_player_ids. Crossing them inverts the trade in
// the calculator — the same silent-catastrophe class as crossed Pass/Like.
//
// Run: node tests/check-matches-calc-handoff.js

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const stripComments = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, '$1');

const SRC = stripComments(
  fs.readFileSync(path.join(MOBILE, 'src/screens/MatchesScreen.tsx'), 'utf8'),
);

let failures = 0;
const ok = (name) => console.log(`PASS  ${name}`);
const fail = (name, detail) => {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
};
const assert = (cond, name, detail) => (cond ? ok(name) : fail(name, detail));

// Isolate the handler body: from its declaration to the next top-level
// function/const at the same rough position (the next `\n  function ` or
// the renderer's `return (`).
const declIdx = SRC.indexOf('async function handleOpenInCalc');
assert(declIdx > -1, '1. handleOpenInCalc exists (async)');
const afterDecl = SRC.slice(declIdx);
const endIdx = afterDecl.indexOf('\n  const ') > -1
  ? Math.min(
      ...['\n  function ', '\n  const ', '\n  return (']
        .map((m) => afterDecl.indexOf(m, 10))
        .filter((i) => i > -1),
    )
  : afterDecl.length;
const BODY = afterDecl.slice(0, endIdx).replace(/\s+/g, ' ');

// ── S-5: cross-league branch switches leagues before navigating ────────────
assert(
  /if \(row\.league_id !== activeLeagueId\)/.test(BODY),
  '2. S-5 — cross-league conditional present (row.league_id !== activeLeagueId)',
);
{
  const branchStart = BODY.indexOf('if (row.league_id !== activeLeagueId)');
  const navIdx = BODY.indexOf("navigation.navigate('Trades'");
  const switchIdx = BODY.indexOf('switchLeague');
  assert(switchIdx > -1, '3. S-5 — switchLeague is the switch machinery (re-inits the backend league session)');
  assert(
    /await useSession\.getState\(\)\.switchLeague\(/.test(BODY),
    '4. S-5 — switchLeague is AWAITED before navigation',
  );
  assert(
    branchStart > -1 && switchIdx > branchStart && navIdx > switchIdx,
    '5. S-5 — navigate happens AFTER the switch branch, never before',
  );
}
assert(
  /if \(!target\) \{ setToast\(\{ msg: 'Switch to that league to open the calculator'.*?\); return; \}/.test(BODY),
  '6. S-5 — unknown/stale league toasts honestly and RETURNS (never navigates wrong)',
);
assert(
  /catch \{ setToast\(\{ msg: 'Could not switch leagues — try again'.*?\); return; \}/.test(BODY),
  '7. S-5 — a failed switch surfaces a toast and RETURNS (no wrong-league navigate)',
);

// ── Uncrossed prefill mapping ──────────────────────────────────────────────
assert(
  /giveIds: row\.my_side_player_ids/.test(BODY),
  '8. prefill.giveIds ← my_side_player_ids (uncrossed)',
);
assert(
  /receiveIds: row\.their_side_player_ids/.test(BODY),
  '9. prefill.receiveIds ← their_side_player_ids (uncrossed)',
);
assert(
  /opponentUserId: row\.counterparty_user_id/.test(BODY),
  '10. prefill.opponentUserId ← counterparty_user_id',
);

// ── Nested navigate + analytics convention ─────────────────────────────────
assert(
  /navigation\.navigate\('Trades', \{ screen: 'TradeCalculator'/.test(BODY),
  '11. navigate is NESTED (Trades → TradeCalculator) — a bare navigate is unreachable from the Matches tab',
);
assert(
  /track\('trade_edit_in_calculator_tapped', undefined, 'Matches'\)/.test(BODY),
  '12. fires the app-wide trade_edit_in_calculator_tapped convention, screen Matches',
);

console.log(failures ? `\n${failures} FAILURE(S)` : '\nALL CHECKS PASSED (12)');
process.exit(failures ? 1 : 0);
