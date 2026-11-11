#!/usr/bin/env node
// Pass-reason cadence (flag `trade.pass_reason_cadence`, offer-learnings WS3).
// Scope: docs/plans/offer-learnings/scope-pass-reason-cadence.md
//
// WHY THIS EXISTS. The operator wants a reason only "once every few passes",
// and a deck that never waits. Four properties would each regress silently:
//   1. THE CADENCE — ask after N consecutive passes, then quiet for M passes;
//      a like resets the run. Executed here against the real module.
//   2. FLAG OFF NEVER CHANGES ANYTHING — the state never moves, the card's
//      reasons object is returned untouched, the hook adds no props.
//   3. ONE TAP — a chip is the pass and the reason in one write and the deck
//      advances at once (no layer-2 deferral, no undo hold that would let an
//      Undo rewind a pass the reason write already committed).
//   4. THE CHIPS — the operator's six phrases, each on a code the API knows.
// Not runtime proof: the TestFlight checklist in the scope block is.
//
// Run: node tests/check-pass-reason-cadence.js  (npm run test:pass-reason-cadence)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
let ts;
try { ts = require('typescript'); } catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const root = path.join(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
let passed = 0;
let failed = 0;
function check(name, fn) {
  try { fn(); passed++; console.log(`PASS  ${name}`); }
  catch (e) { failed++; console.error(`FAIL  ${name}: ${e.message}`); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg || 'assertion failed'); }
function eq(a, b, msg) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${msg || 'not equal'}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`);
  }
}

// ── Execute the real module ────────────────────────────────────────────────
const src = read('src/utils/passReasonCadence.ts');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(src, { compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
} }).outputText, { module: mod, exports: mod.exports, require: () => ({}) });
const C = mod.exports;

/** Feed a sequence of 'p'/'l' and return, per card, whether it was asked. */
function run(on, seq, cfg = C.DEFAULT_CADENCE) {
  let s = C.INITIAL_CADENCE;
  const asked = [];
  for (const ch of seq) {
    asked.push(C.shouldAsk(on, s, cfg));
    s = C.recordDisposition(on, s, ch === 'l' ? 'like' : 'pass', cfg);
  }
  return asked.map((a) => (a ? 'A' : '.')).join('');
}

check('1a. defaults are the operator starting values (N=3, M=5)', () => {
  eq(C.DEFAULT_CADENCE, { askAfter: 3, quietFor: 5 });
});
check('1b. asks on the card after N consecutive passes, not before', () => {
  eq(run(true, 'pppp'), '...A');
});
check('1c. quiet for exactly M passes after the ask, then asks again', () => {
  // card 4 asked; cards 5–9 are the five quiet passes; card 10 asks (run is 5 ≥ 3).
  eq(run(true, 'pppppppppppppppp'), '...A.....A.....A');
});
check('1d. quiet shorter than N: the run of N still has to rebuild', () => {
  eq(run(true, 'pppppppp', { askAfter: 3, quietFor: 1 }), '...A...A');
});
check('1e. a like resets the run of passes', () => {
  eq(run(true, 'pplpppp'), '......A');
});
check('1f. a like during the quiet period does not shorten it', () => {
  // ask at 4; pass(quiet 4) like pass×3 (quiet 3,2,1) → still quiet; 1 more pass ends it
  // the five quiet passes are cards 5, 7, 8, 9, 10 (card 6 is the like); card 11 asks.
  eq(run(true, 'pppp' + 'p' + 'l' + 'ppp' + 'p' + 'p'), '...A' + '.' + '.' + '...' + '.' + 'A');
});
check('1g. a like ON the asked card ends that ask without a quiet period', () => {
  eq(run(true, 'ppplppp' + 'p'), '...A...A');
});
check('1h. the asked pass starts a new run (N=1, M=0 asks every other card)', () => {
  eq(run(true, 'pppppp', { askAfter: 1, quietFor: 0 }), '.A.A.A');
});

check('2a. flag off: never asks, however long the run', () => {
  eq(run(false, 'p'.repeat(40)), '.'.repeat(40));
});
check('2b. flag off: the state object never moves', () => {
  const s = { consecutivePasses: 7, quietRemaining: 2 };
  ok(C.recordDisposition(false, s, 'pass', C.DEFAULT_CADENCE) === s, 'pass moved the state');
  ok(C.recordDisposition(false, s, 'like', C.DEFAULT_CADENCE) === s, 'like moved the state');
});
check('2b2. flag killed mid-run: a ripe state still never asks', () => {
  ok(!C.shouldAsk(false, { consecutivePasses: 9, quietRemaining: 0 }, C.DEFAULT_CADENCE),
    'asked with the flag off');
});
check('2c. no cadence field: the reasons object is returned untouched', () => {
  const r = { onLayer1() {} };
  ok(C.cadenceCardReasons(r) === r, 'reasons object replaced');
  ok(C.cadenceCardReasons(undefined) === undefined, 'undefined not preserved');
});
check('2d. quiet card gets no reasons (plain ✓/✕); asking card keeps them', () => {
  ok(C.cadenceCardReasons({ cadence: { mode: 'quiet' } }) === undefined, 'quiet kept reasons');
  const ask = { cadence: { mode: 'ask' } };
  ok(C.cadenceCardReasons(ask) === ask, 'ask lost reasons');
});

check('3a. server config: valid values pass through', () => {
  eq(C.normalizeCadence({ ask_after: 4, quiet_for: 0 }), { askAfter: 4, quietFor: 0 });
});
check('3b. server config: missing or malformed falls back per field', () => {
  for (const bad of [undefined, null, 'x', {}, { ask_after: 0, quiet_for: -1 },
    { ask_after: 2.5, quiet_for: '5' }, { ask_after: NaN, quiet_for: Infinity }]) {
    eq(C.normalizeCadence(bad), { askAfter: 3, quietFor: 5 }, `for ${JSON.stringify(bad)}`);
  }
});

// ── The chips ──────────────────────────────────────────────────────────────
const api = read('src/api/declineReasons.ts').replace(/\/\/.*$/gm, '');
const layer2 = (api.match(/export type Layer2Code =([\s\S]*?);/) || [])[1] || '';
const codes = [...layer2.matchAll(/'([a-z_]+)'/g)].map((m) => m[1]);
check('4a. the six operator phrases, in order', () => {
  eq(C.PASS_REASON_CHIPS.map((c) => c.label), [
    'Not moving that player', 'Keeping my picks', 'Wrong direction for my team',
    "Don't rate what I'd get", 'Waiting on something', 'Value too low',
  ]);
});
check('4b. every chip is a known Layer2Code under its own parent', () => {
  for (const c of C.PASS_REASON_CHIPS) {
    ok(codes.includes(c.detail), `${c.detail} not in Layer2Code`);
    ok(c.detail.startsWith(`${c.reason}_`), `${c.detail} not under ${c.reason}`);
  }
});
check('4c. mapping onto existing codes; only the two missing ones are new', () => {
  eq(C.PASS_REASON_CHIPS.map((c) => c.detail), [
    'other_player_keep', 'other_picks_keep', 'fit_outlook',
    'other_player_avoid', 'other_waiting', 'value_giving',
  ]);
});

// ── Wiring ────────────────────────────────────────────────────────────────
const screen = read('src/screens/TradesScreen.tsx');
const sf = ts.createSourceFile('TradesScreen.tsx', screen, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function fnText(name) {
  let out = '';
  const visit = (n) => {
    if (ts.isFunctionDeclaration(n) && n.name && n.name.text === name) out = n.getText(sf);
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}
const adv = fnText('advance');
const l1 = fnText('handleReasonLayer1');
check('5a. advance() records every disposition exactly once, after both guards', () => {
  const hits = adv.split('passCadence.record(decision)').length - 1;
  eq(hits, 1, 'record calls in advance');
  const g = adv.indexOf('guardBlockRef.current.key = null');
  ok(g > 0 && adv.indexOf('passCadence.record(decision)') > g, 'record runs before the guards');
  eq(screen.split('passCadence.record(').length - 1, 1, 'record calls in the screen');
});
check('5b. a reasoned pass (passAttempt supplied) never enters the undo hold', () => {
  ok(/if \(swipeUndoOn && decision === 'pass' && !declineReasonsOn && !opts\?\.passAttempt && passAttempt\)/.test(adv),
    'undo hold condition lost its !opts?.passAttempt');
});
check('5c. a chip (detail) advances at once: one POST, no deferral, no banking', () => {
  ok(/\.\.\.\(detail \? \{ detail \} : \{\}\)/.test(l1), 'detail not in the layer-1 POST');
  const i = l1.indexOf("if (detail) return advance('pass', { passAttempt: attempt });");
  ok(i > 0, 'chip advance missing');
  ok(i < l1.indexOf('reasonBankedIdRef.current = rawId'), 'chip path banks the card first');
  ok(/if \(detail\) track\('trade_pass_layer2', \{ reason, detail, has_free_text: false, \.\.\.reasonEventProps\(\) \}/.test(l1),
    'chip answer does not fire trade_pass_layer2');
  eq((l1.match(/postDeclineReason\(/g) || []).length, 1, 'layer-1 POST count');
});
check('5d. the deck card gets the cadence-filtered reasons and never the overlay while asking', () => {
  ok(screen.includes('reasons: cadenceCardReasons(declineReasons),'), 'card reasons not filtered');
  ok(screen.includes('reasonsAsOverlay={reasonsAsOverlay && !declineReasons?.cadence}'), 'overlay not suppressed');
});
check('5e. reason props: built when either flag is on, cadence props spread in', () => {
  ok(/declineReasonProps: DispositionReasons \| undefined = declineReasonsOn \|\| passCadence\.on\s*\?\s*\{\s*\.\.\.passCadence\.cardProps,/.test(screen),
    'declineReasonProps definition');
});
check('5f. the screen footprint stays small', () => {
  const lines = screen.split('\n').filter((l) => /passCadence|cadenceCardReasons|usePassReasonCadence/.test(l));
  ok(lines.length <= 9, `${lines.length} cadence lines in TradesScreen`);
});

const hook = read('src/hooks/usePassReasonCadence.ts');
check('6a. hook: flag off adds no props and never moves state', () => {
  ok(hook.includes("useFlag('trade.pass_reason_cadence')"), 'flag key');
  ok(/if \(!on\) return \{ on, record, cardProps: \{\} \};/.test(hook), 'flag-off cardProps not {}');
  ok(/const record = useCallback\(\s*\(decision: 'like' \| 'pass'\) => \{\s*if \(!on\) return;/.test(hook), 'record not inert when off');
});
check('6b. hook: N and M come from the server payload', () => {
  ok((hook.match(/normalizeCadence\(fetchedPassReasonCadence\(\)\)/g) || []).length === 2, 'config source');
  const flags = read('src/api/flags.ts');
  ok(/_passReasonCadence = res\?\.pass_reason_cadence;/.test(flags), 'flags.ts does not capture pass_reason_cadence');
});
check('6c. hook: prompt events are the two registered names', () => {
  ok(hook.includes("'pass_reason_prompt_shown'") && hook.includes("'pass_reason_prompt_dismissed'"), 'event names');
});

const card = read('src/components/TradeCard.tsx');
check('7a. TradeCard: chips take precedence over the tile panel', () => {
  const chips = card.indexOf('disposition.reasons?.cadence ? (');
  const panel = card.indexOf('<DeclineReasonPanel {...disposition.reasons} />');
  ok(chips > 0 && panel > chips, 'chips branch must come first');
});
check('7b. TradeCard: a chip is onLayer1 with its detail; Just pass is the plain pass', () => {
  ok(card.includes("onChip={(r, d) => disposition.reasons!.onLayer1(r, 'none', d)}"), 'chip wiring');
  ok(/onSkip=\{\(\) => \{\s*disposition\.reasons!\.cadence!\.onDismissed\(data\.trade_id\);\s*disposition\.onPass\(\);\s*\}\}/.test(card),
    'Just pass wiring');
});
const chipsSrc = read('src/components/PassReasonChips.tsx');
check('7c. chips: no truncation, 44pt floor, radius ≤ 8, no emoji', () => {
  ok(!/numberOfLines\s*=/.test(chipsSrc), 'truncates');
  ok(/minHeight: 44/.test(chipsSrc), 'touch floor');
  ok(!/borderRadius:\s*(9|[1-9]\d)/.test(chipsSrc), 'radius > 8');
  ok(!/[\u{1F300}-\u{1FAFF}]/u.test(chipsSrc), 'emoji');
});

console.log(`\ncheck-pass-reason-cadence: ${passed} passed, ${failed} failed`);
if (failed) process.exitCode = 1;
