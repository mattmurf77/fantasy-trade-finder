#!/usr/bin/env node
// #346/#381 (D-160) — Quick Set saves HOLD unselected players.
//
// WHY THIS EXISTS. The #161 rule (shipped v1.10.0) made every explicit Quick
// Set rung save DEMOTE all visible-but-unselected players at/above the rung:
// the client computed a `demoted` list, sent it as `demoted_pids` on
// POST /api/tiers/save, and the backend pinned each pid to 1100 elo — below
// the waivers floor, rendering as FA at the bottom of the grid (the #381
// Nabers repro; #346's preseeded "1 1st" values dropping to zero). The
// operator's #381 ruling reversed it: a save touches ONLY the selected and
// cleared players; everyone else keeps their tier. The backend now ignores
// the legacy key (merged first, D-160); this guard pins the CLIENT half —
// the demote list must never be computed or sent again.
//
// WHAT IS PINNED (PRD §6b, docs/feedback/items/346-quickset-tier-drop/):
//
//   A1  QuickSetTiersScreen.tsx has no `demoted` token — no demote
//       computation (the `TIERS.indexOf(cur) <= tierRank` passed-over
//       filter), no `demoted` member in the mutation payload/mutationFn.
//       POSITIVE ANCHOR (reconciliation O-5, so a renamed/gutted file can't
//       green this vacuously): the two-member `mutate({ ids, cleared })`
//       shape must still exist, with `cleared` flowing into `saveTiers`.
//       Sabotage: re-add the demote computation or payload member → RED;
//       delete the mutate call → RED.
//   A2  api/rankings.ts `saveTiers` has no `demotedPids` parameter and its
//       POST body has no `demoted_pids` key — while `cleared_pids` is still
//       present (anti-trivial: proves the guard reads the real body and the
//       R-4 clear path didn't ride along). Sabotage: re-add
//       `demoted_pids: []` to the body → RED.
//   A3  TiersScreen.tsx has no `demoted` token and still calls `saveTiers(`
//       at its 4 sites. (Arity itself is enforced by `tsc --noEmit` — a 5th
//       positional arg to the 4-param `saveTiers` is a type error.)
//       Sabotage: re-add a positional demote arg by name → RED.
//
// Dependency-free plain node; no simulator, no backend, no flag fixture.
//
// Run: node tests/check-quickset-hold.js

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const FILES = {
  qs: 'src/screens/QuickSetTiersScreen.tsx',
  rk: 'src/api/rankings.ts',
  ts: 'src/screens/TiersScreen.tsx',
};

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

/** Slice from `start` (index of an opening-paren caller) to the matching
 *  close paren, by depth scan. `openIdx` is the index of the `(` itself. */
function parenSlice(src, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < src.length; i += 1) {
    if (src[i] === '(') depth += 1;
    else if (src[i] === ')') {
      depth -= 1;
      if (depth === 0) return src.slice(openIdx, i + 1);
    }
  }
  return null;
}

const qs = read(FILES.qs);
const rk = read(FILES.rk);
const tiers = read(FILES.ts);

// ── A1 — QuickSetTiersScreen: no demote, and the HOLD save shape stands ───

assert(
  !/demoted/.test(qs),
  `A1a — ${FILES.qs} contains no \`demoted\` token`,
  'the demote computation / payload member is back — a Quick Set save must ' +
    'touch only selected + cleared pids (D-160)',
);

// The #161 passed-over filter's signature: a tier-ladder index compared with
// `<=` (the "this tier or higher" test). Legit ladder lookups in this file
// use `>=`/`<`; only the demote rule ever needed `<=`.
assert(
  !/TIERS\s*\.\s*indexOf\s*\([^)]*\)\s*<=/.test(qs),
  'A1b — no passed-over demote filter (`TIERS.indexOf(…) <=` comparison)',
  'a tier-rank <= comparison is back — the #161 demote rule\'s shape',
);

// O-5 positive anchor: the two-member mutate shape. Without this, renaming
// or gutting the screen would green A1a/A1b vacuously.
assert(
  /\.mutate\(\s*\{\s*ids\s*,\s*cleared\s*\}\s*\)/.test(qs),
  'A1c — the two-member `mutate({ ids, cleared })` call exists',
  'the save mutate call is missing or its payload shape changed — if that ' +
    'is intentional, update this guard with the new HOLD-conformant shape',
);

assert(
  /mutationFn:\s*\(\s*\{\s*ids\s*,\s*cleared\s*\}/.test(qs),
  'A1d — mutationFn destructures exactly `{ ids, cleared }`',
  'the mutation payload type grew or shrank',
);

// `cleared` must actually flow into saveTiers (not be dropped on the floor).
{
  const callIdx = qs.indexOf('saveTiers(');
  const call = callIdx >= 0 ? parenSlice(qs, callIdx + 'saveTiers'.length) : null;
  assert(
    !!call && /\bcleared\b/.test(call),
    'A1e — `cleared` flows into the `saveTiers` call',
    call ? `saveTiers args: ${call.replace(/\s+/g, ' ').slice(0, 120)}` : 'no saveTiers( call found',
  );
}

// ── A2 — api/rankings.ts: the wire field is gone, cleared_pids is not ──────

{
  const sigStart = rk.indexOf('export async function saveTiers');
  assert(sigStart >= 0, 'A2a — `saveTiers` exists in api/rankings.ts', 'function not found');
  if (sigStart >= 0) {
    const openIdx = rk.indexOf('(', sigStart);
    const sig = parenSlice(rk, openIdx) || '';
    assert(
      !/demotedPids/.test(sig),
      'A2b — `saveTiers` has no `demotedPids` parameter',
      'the demote parameter is back in the signature',
    );
    assert(
      /clearedPids/.test(sig),
      'A2c — `saveTiers` still takes `clearedPids` (anti-trivial: R-4 clear path intact)',
      'the clear parameter vanished — the guard may be reading the wrong function',
    );

    // The POST body: the api.post call inside saveTiers.
    const postIdx = rk.indexOf('api.post', sigStart);
    const body = postIdx >= 0 ? parenSlice(rk, rk.indexOf('(', postIdx)) : null;
    assert(!!body, 'A2d — the `api.post(\'/api/tiers/save\', …)` body is locatable');
    if (body) {
      assert(
        !/demoted_pids/.test(body),
        'A2e — the POST body has no `demoted_pids` key',
        'the legacy wire field is back in the body',
      );
      assert(
        /cleared_pids\s*:/.test(body),
        'A2f — the POST body still carries `cleared_pids` (anti-trivial)',
        'cleared_pids missing — the guard is not reading the real body',
      );
    }
  }
}

// ── A3 — TiersScreen: no demote token, all 4 call sites intact ─────────────

assert(
  !/demoted/.test(tiers),
  `A3a — ${FILES.ts} contains no \`demoted\` token`,
  'a demote argument or reference is back on the Tiers board save paths',
);

{
  const count = (tiers.match(/saveTiers\(/g) || []).length;
  assert(
    count === 4,
    `A3b — ${FILES.ts} calls \`saveTiers(\` at exactly its 4 sites (saw ${count})`,
    'a call site was added or removed — if intentional, update this guard',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All quickset-hold checks passed.');
