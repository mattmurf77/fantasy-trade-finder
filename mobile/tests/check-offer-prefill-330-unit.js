#!/usr/bin/env node
// #330 (G4) — unit tests U-1..U-4 for the Offer/Target handoff + epoch guard.
//
// Mobile has no jest harness (D-056), so this transpiles the REAL modules
// with the project's typescript and runs them under plain node — the
// check-session-rerank.js idiom:
//   • src/state/useFinderTargets.ts — with the real zustand and a stubbed
//     ./useSession (a tiny subscribable), so the league-switch subscription
//     is exercised for real;
//   • src/utils/applyJobResult.ts — pure by contract, zero runtime imports.
//
// Every test names the sabotage that turns it red (each was applied and
// reverted during the build — see the item folder's status.md):
//   U-1: seq stamping removed / made non-monotonic in setHandoff
//   U-2: `handoff` dropped from clear()'s reset object
//   U-3: setSide made additive (dedupeAdd) instead of REPLACE
//   U-4: applyJobResult returns the result regardless of epoch
//
// Run: node tests/check-offer-prefill-330-unit.js

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

function transpile(rel) {
  const source = fs.readFileSync(path.join(ROOT, rel), 'utf8');
  return ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
}

function load(rel, requireShim) {
  const moduleShim = { exports: {} };
  new Function('module', 'exports', 'require', transpile(rel))(
    moduleShim,
    moduleShim.exports,
    requireShim,
  );
  return moduleShim.exports;
}

// ── Stub useSession: a minimal subscribable the store's league-switch GC
//    subscription attaches to. Mirrors zustand's subscribe(listener) shape.
const sessionListeners = [];
let sessionState = { league: null };
const useSessionStub = {
  subscribe: (fn) => {
    sessionListeners.push(fn);
    return () => {};
  },
};
function setSessionLeague(league) {
  sessionState = { league };
  for (const fn of sessionListeners) fn(sessionState);
}

const finderModule = load('src/state/useFinderTargets.ts', (name) => {
  if (name === 'zustand') return require(path.join(ROOT, 'node_modules', 'zustand'));
  if (name === './useSession') return { useSession: useSessionStub };
  throw new Error(
    `useFinderTargets.ts gained an unexpected runtime import ("${name}") — ` +
      'extend the shim deliberately, do not let it pass silently.',
  );
});
const { useFinderTargets } = finderModule;

const { applyJobResult } = load('src/utils/applyJobResult.ts', (name) => {
  throw new Error(
    `applyJobResult.ts gained a runtime import ("${name}") — it must stay pure ` +
      'so this check can run it under plain node.',
  );
});

const P = (id) => ({ id, name: `P${id}`, position: 'WR', team: 'TST', age: 25 });
const OPP = { userId: 'u9', name: 'Team Nine' };

// The store's league subscription treats its FIRST observation as baseline —
// establish it so later switches actually invalidate.
setSessionLeague({ league_id: 'L1' });

// ═══════════════════════════════════════════════════════════════════════
// U-1 — setHandoff stores the object and stamps a strictly increasing seq
// ═══════════════════════════════════════════════════════════════════════

assert(
  useFinderTargets.getState().handoff === null,
  'U-1a initial handoff is null',
);

useFinderTargets.getState().setHandoff({ opponent: OPP, autoRun: true });
const first = useFinderTargets.getState().handoff;
assert(
  !!first && first.opponent.userId === 'u9' && first.opponent.name === 'Team Nine'
    && first.autoRun === true,
  'U-1b setHandoff stores opponent + autoRun',
  `got ${JSON.stringify(first)}`,
);
assert(
  !!first && typeof first.seq === 'number' && Number.isFinite(first.seq),
  'U-1c setHandoff stamps a numeric seq (callers never supply it)',
);

// Same payload twice ⇒ DIFFERENT, strictly increasing seqs — the whole point
// of the nonce (a repeat Offer to the same team must still re-fire the
// choke-point effect).
useFinderTargets.getState().setHandoff({ opponent: OPP, autoRun: true });
const second = useFinderTargets.getState().handoff;
assert(
  !!first && !!second && second.seq > first.seq,
  'U-1d identical payloads get strictly increasing seqs',
  `sabotage detected: seq stamping removed or non-monotonic (${first && first.seq} → ${second && second.seq})`,
);

// ═══════════════════════════════════════════════════════════════════════
// U-2 — clear() nulls handoff; league switch GCs it together with the pins
// ═══════════════════════════════════════════════════════════════════════

useFinderTargets.getState().clear();
assert(
  useFinderTargets.getState().handoff === null,
  'U-2a clear() nulls the handoff',
  'sabotage detected: handoff dropped from clear()',
);

useFinderTargets.getState().addGive(P('g1'));
useFinderTargets.getState().setHandoff({ opponent: OPP, autoRun: true });
setSessionLeague({ league_id: 'L2' }); // league switch
{
  const s = useFinderTargets.getState();
  assert(
    s.handoff === null && s.pinnedGive.length === 0 && s.pinnedReceive.length === 0,
    'U-2b league switch clears handoff AND pins together',
    `sabotage detected: subscription bypasses clear() (handoff=${JSON.stringify(s.handoff)}, pins=${s.pinnedGive.length}/${s.pinnedReceive.length})`,
  );
}

// The seq counter survives clear(): monotonic for the session, so a consumer
// can never see a "new" handoff carrying an already-seen seq.
useFinderTargets.getState().setHandoff({ opponent: OPP, autoRun: true });
{
  const third = useFinderTargets.getState().handoff;
  assert(
    !!second && !!third && third.seq > second.seq,
    'U-2c seq stays monotonic across clear()',
    'sabotage detected: counter reset inside clear() re-issues seen seqs',
  );
  useFinderTargets.getState().setHandoff(null);
}

// ═══════════════════════════════════════════════════════════════════════
// U-3 — setSide REPLACE semantics and packageMode default are unchanged
// ═══════════════════════════════════════════════════════════════════════

useFinderTargets.getState().clear();
assert(
  useFinderTargets.getState().packageMode === true,
  'U-3a packageMode still defaults ON after clear()',
);

useFinderTargets.getState().addGive(P('a'));
useFinderTargets.getState().addGive(P('b'));
useFinderTargets.getState().setSide('give', [P('c')]);
{
  const g = useFinderTargets.getState().pinnedGive;
  assert(
    g.length === 1 && g[0].id === 'c',
    'U-3b setSide REPLACES the give side wholesale',
    `sabotage detected: additive setSide (got [${g.map((p) => p.id)}])`,
  );
}
useFinderTargets.getState().setSide('receive', [P('r1')]);
useFinderTargets.getState().setSide('receive', []);
assert(
  useFinderTargets.getState().pinnedReceive.length === 0,
  'U-3c setSide with [] empties the receive side (the #300 both-sides replace)',
);
useFinderTargets.getState().setPackageMode(false);
useFinderTargets.getState().setHandoff({ opponent: OPP, autoRun: true });
assert(
  useFinderTargets.getState().packageMode === false,
  'U-3d setHandoff never touches packageMode',
);
useFinderTargets.getState().clear();

// ═══════════════════════════════════════════════════════════════════════
// U-4 — the epoch guard drops mismatched results (fails without the guard)
// ═══════════════════════════════════════════════════════════════════════

const snapshot = { job_id: 'j1', status: 'complete', cards: [{ trade_id: 't1' }] };
assert(
  applyJobResult(snapshot, 3, 3) === snapshot,
  'U-4a equal epochs ⇒ the result is applied (same reference back)',
);
assert(
  applyJobResult(snapshot, 2, 3) === null,
  'U-4b a stale dispatch epoch ⇒ the result is DROPPED entirely',
  'sabotage detected: guard removed — a pre-scope snapshot would resurrect over the scoped run',
);
assert(
  applyJobResult(null, 5, 5) === null && applyJobResult(0, 1, 2) === null,
  'U-4c falsy results round-trip consistently (null stays null; stale falsy still dropped)',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All #330 handoff/epoch unit tests passed.');
