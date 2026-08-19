#!/usr/bin/env node
// B3 follow-up (2026-08-18) — the picker reads SERVER-SUPPLIED pick identity,
// and keeps its fallback.
//
// WHY THIS EXISTS. `/api/trade/values` now serves `is_pick`, derived from the
// canonical backend predicate `trade_service.is_pick_asset`
// (backend/trade_service.py:1138-1147) — see
// backend/tests/test_trade_values_is_pick.py and
// docs/cross-client-invariants.md § "Pick identity on the wire". This is the
// first client migrated off the `team === 'PICK'` magic string. Two halves
// must hold together, and each fails silently on its own:
//
//   1. PREFER the server field. If the picker ignores it, the migration is
//      cosmetic and the next `_PICK_POS`-shaped surprise lands the same way
//      it did for feedback #222 and the B3 sweep.
//   2. KEEP the fallback, and take only an EXPLICIT boolean as authoritative.
//      `is_pick` is additive: absent on older servers, absent on responses
//      cached under `stale-while-revalidate` from before the deploy, and
//      absent by construction on the pick shapes that never come from that
//      endpoint (owned league picks from `/api/league/picks`, the demo
//      calculator's mock picks). A mapper wired against an older server hands
//      over `isPick: undefined` — reading that as `false` reproduces the bug
//      under a new name, which is why a bare `p.isPick ? … : …` is not enough.
//
// The runtime block below runs the REAL predicate lifted out of the source,
// so dropping either half turns this RED. Each assertion names its sabotage.
//
// Sibling: tests/check-picker-pick-filter.js pins the two-sided position
// filter this predicate feeds. Run: node tests/check-picker-server-pick-flag.js

'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const REL = 'src/components/PlayerPickerModal.tsx';
const raw = fs.readFileSync(path.join(__dirname, '..', REL), 'utf8');
const src = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

// ── The comment trail is load-bearing. A future reader who cannot see why a
// second, redundant-looking check survives will delete it as dead code.
assert(
  /is_pick_asset/.test(raw),
  'the predicate still cites the canonical backend `trade_service.is_pick_asset`',
);
assert(
  /is_pick\b/.test(raw) && /trade\/values/.test(raw),
  'the comment names the wire field `is_pick` and the route that serves it',
);
assert(
  /FALLBACK STAYS|fallback stays/i.test(raw),
  'the comment states, in words, that the fallback is deliberate — not dead code',
);
assert(
  /#222|B3/.test(raw),
  'the comment cites the shipped bug(s) the fallback protects against',
);
assert(
  /cached|stale-while/i.test(raw) && /older server|servers? older/i.test(raw),
  'the comment names BOTH absence cases (old servers, cached responses)',
);

// ── Structure: one module-scope predicate, lifted the same way its sibling
// suite lifts it (same regex — the two must not drift apart).
const predMatch = src.match(/const isPickAsset = \(p: CalcPlayer\) => ([^;]+);/);
assert(!!predMatch, 'isPickAsset is a module-scope predicate over CalcPlayer');
const predBody = predMatch ? predMatch[1] : 'false';

assert(/\bisPick\b/.test(predBody), 'the predicate consults the server field `isPick`');
// Sabotage "drop the fallback": both magic-string arms must survive.
assert(/p\.pos === 'PICK'/.test(predBody), "the fallback still tests p.pos === 'PICK'");
assert(
  /p\.nflTeam === 'PICK'/.test(predBody),
  "the fallback still tests p.nflTeam === 'PICK' (the generic-rung marker)",
);
// Sabotage "truthiness is good enough": `p.isPick ? a : b` silently reads an
// undefined field as absent-but-false and never reaches the fallback.
assert(
  /typeof p\.isPick === 'boolean'/.test(predBody),
  'only an EXPLICIT boolean is treated as authoritative (typeof guard, not truthiness)',
  predBody.trim(),
);

// ── Runtime: the REAL predicate, over every shape that reaches this modal.
const js = (text) => text.replace(/: CalcPlayer/g, '');
// eslint-disable-next-line no-new-func
const isPickAsset = new Function('p', `return ${js(predBody)};`);

// 1. Server field present and true — the migrated path.
assert(
  isPickAsset({ id: 'rung', pos: 'RB', nflTeam: 'PICK', isPick: true }) === true,
  'a rung the server flags is a pick',
);
// 2. Server field WINS over the local inference, both directions. This is the
//    proof of "prefers": a predicate that ORs the server field onto the old
//    check passes case 1 and fails these two.
assert(
  isPickAsset({ id: 'srv-says-pick', pos: 'RB', nflTeam: 'ATL', isPick: true }) === true,
  'the server field alone is enough — no magic string required',
);
assert(
  isPickAsset({ id: 'srv-says-player', pos: 'PICK', nflTeam: 'PICK', isPick: false }) === false,
  'an explicit `false` from the server overrides the magic string',
);
// 3. Field ABSENT (old server / pre-deploy cached response) — fallback.
assert(
  isPickAsset({ id: 'rung', pos: 'RB', nflTeam: 'PICK' }) === true,
  'FALLBACK: a generic rung with a FAKE position still matches on nflTeam alone',
);
assert(
  isPickAsset({ id: 'own-2027-1st', pos: 'PICK', nflTeam: 'PICK' }) === true,
  'FALLBACK: an owned league pick (never served by /api/trade/values) matches',
);
assert(
  isPickAsset({ id: 'demo1', pos: 'PICK', nflTeam: '—' }) === true,
  'FALLBACK: a demo mock pick (nflTeam "—") matches',
);
assert(
  isPickAsset({ id: 'brobinson', pos: 'RB', nflTeam: 'ATL' }) === false,
  'FALLBACK: a real player is still not a pick',
);
// 4. Field present but UNDEFINED — a mapper wired against an older server.
//    This must fall THROUGH to the fallback, not read as false.
assert(
  isPickAsset({ id: 'rung', pos: 'RB', nflTeam: 'PICK', isPick: undefined }) === true,
  '`isPick: undefined` falls through to the fallback (never read as false)',
);
assert(
  isPickAsset({ id: 'brobinson', pos: 'RB', nflTeam: 'ATL', isPick: undefined }) === false,
  '`isPick: undefined` on a real player still resolves false',
);
// 5. Non-boolean junk (a mapper that forwards a raw string) is not trusted.
assert(
  isPickAsset({ id: 'rung', pos: 'RB', nflTeam: 'PICK', isPick: 'false' }) === true,
  'a non-boolean `isPick` is ignored in favour of the fallback',
);

process.exit(failures ? 1 : 0);
