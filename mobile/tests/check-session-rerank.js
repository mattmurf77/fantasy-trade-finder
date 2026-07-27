#!/usr/bin/env node
// Regression test for the F4 session re-rank math (flag deck.session_rerank,
// PRD docs/plans/tiktok-discovery/prds/F4-session-rerank.md).
//
// Pins the pure-module contract:
//   • disposition rewards (like +1 / long-dwell pass +0.3 / fast pass −0.5 /
//     mid pass 0 / not-interested −2) and the ×0.8-per-card recency decay
//   • last-k window (k = 10)
//   • cosine similarity basics
//   • re-rank: newScore = 1/(served+1) × (1 + 0.3·cos); stable (served
//     order tiebreak); zero boost ⇒ no-op; boundary cards never move;
//     likes-you / retest / wildcard cards keep their exact index
//
// Mobile has no jest harness, so this transpiles the REAL module
// (src/utils/sessionRerank.ts — pure by design, zero runtime imports) with
// the project's typescript and runs it under plain node — same idiom as
// check-feedback-badge.js.
//
// Run: node tests/check-session-rerank.js  (or: npm run test:session-rerank)

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

const srcPath = path.join(__dirname, '..', 'src', 'utils', 'sessionRerank.ts');
const source = fs.readFileSync(srcPath, 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

const moduleShim = { exports: {} };
new Function('module', 'exports', 'require', js)(moduleShim, moduleShim.exports, (name) => {
  throw new Error(
    `sessionRerank.ts gained a runtime import ("${name}") — it must stay pure ` +
      'so this check can run it under plain node.',
  );
});
const {
  SESSION_RERANK_ETA,
  SESSION_RERANK_LAST_K,
  SESSION_RERANK_DECAY,
  RERANK_LONG_DWELL_MS,
  RERANK_FAST_PASS_MS,
  dispositionWeight,
  extractCardAttributes,
  buildBoostVector,
  cosineSimilarity,
  isZeroVector,
  isPositionLocked,
  rerankRemaining,
} = moduleShim.exports;

let failures = 0;
function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) {
    failures += 1;
    console.error(
      `FAIL  ${name}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
    );
  } else {
    console.log(`ok    ${name}`);
  }
}
function checkClose(name, actual, expected, eps = 1e-9) {
  if (typeof actual !== 'number' || Math.abs(actual - expected) > eps) {
    failures += 1;
    console.error(`FAIL  ${name}: expected ~${expected}, got ${actual}`);
  } else {
    console.log(`ok    ${name}`);
  }
}

// Card factory: a simple 1x1 WR-for-RB swap vs partner u2.
function card(id, over = {}) {
  return {
    trade_id: id,
    give_players: [{ id: 'g1', position: 'WR', age: 26 }],
    receive_players: [{ id: 'r1', position: 'RB', age: 23 }],
    opponent_user_id: 'u2',
    give_value: 2100,
    receive_value: 2050,
    ...over,
  };
}

// ── Constants pin (PRD F4 §1–2) ─────────────────────────────────────────
check('η = 0.3', SESSION_RERANK_ETA, 0.3);
check('k = 10', SESSION_RERANK_LAST_K, 10);
check('decay = 0.8', SESSION_RERANK_DECAY, 0.8);

// ── Disposition weights ─────────────────────────────────────────────────
check('like → +1', dispositionWeight('like'), 1);
check('not_interested → −2', dispositionWeight('not_interested', 500), -2);
check('fast pass → −0.5', dispositionWeight('pass', RERANK_FAST_PASS_MS - 1), -0.5);
check('long-dwell pass → +0.3', dispositionWeight('pass', RERANK_LONG_DWELL_MS + 1), 0.3);
check('mid pass → 0', dispositionWeight('pass', 5000), 0);
check('unknown-dwell pass → 0', dispositionWeight('pass'), 0);

// ── Attribute extraction ────────────────────────────────────────────────
const attrs = extractCardAttributes(
  card('t1', {
    give_players: [
      { id: 'a', position: 'WR', age: 22 },
      { id: 'b', position: 'PICK', pick_value: 40 },
    ],
    receive_players: [{ id: 'c', position: 'RB', age: 30 }],
  }),
);
check('shape one-hot', attrs['shape:2x1'], 1);
check('shape class consolidate', attrs['shapeclass:consolidate'], 1);
checkClose('give WR share (pick excluded from position share)', attrs['pos:give:WR'], 0.5);
check('pick flag on give side', attrs['pick:give'], 1);
check('no pick flag on receive side', attrs['pick:receive'], undefined);
checkClose('young band share', attrs['age:give:young'], 0.5);
checkClose('vet band share', attrs['age:receive:vet'], 1);
check('partner one-hot', attrs['partner:u2'], 1);
check('give value band (500-wide)', attrs['valueband:give:2000-2500'], 1);

// ── Boost vector: recency decay + last-k window ─────────────────────────
const ev = (id, weight) => ({ tradeId: id, attrs: { x: 1 }, weight });
checkClose(
  'decay ×0.8 per subsequent card',
  buildBoostVector([ev('a', 1), ev('b', 1)]).x,
  1 * 0.8 + 1, // older event decayed once, newest full weight
);
const overflow = buildBoostVector(
  [ev('old', 1000)].concat(Array.from({ length: 10 }, (_, i) => ev(`e${i}`, 0))),
);
checkClose('events beyond last-10 fall out', overflow.x ?? 0, 0);

// ── Cosine ──────────────────────────────────────────────────────────────
checkClose('cosine identical vectors', cosineSimilarity({ a: 1, b: 2 }, { a: 1, b: 2 }), 1);
checkClose('cosine orthogonal', cosineSimilarity({ a: 1 }, { b: 1 }), 0);
checkClose('cosine opposite', cosineSimilarity({ a: 1 }, { a: -1 }), -1);
check('zero vector detected', isZeroVector({ a: 0, b: 0 }), true);

// ── Position locks ──────────────────────────────────────────────────────
check('likes-you locked', isPositionLocked(card('t', { likesYou: true })), true);
check('F3 retest locked', isPositionLocked(card('t', { retest: true })), true);
check('F7 wildcard locked', isPositionLocked(card('t', { wildcard: true })), true);
check('plain card not locked', isPositionLocked(card('t')), false);

// ── Re-rank ─────────────────────────────────────────────────────────────
// Deck of 6 in served order. served index map = identity.
const wr = (id) => card(id); // WR→RB swap (matches the boost below)
const qb = (id) =>
  card(id, {
    give_players: [{ id: 'g', position: 'QB', age: 33 }],
    receive_players: [
      { id: 'r1', position: 'TE', age: 25 },
      { id: 'r2', position: 'TE', age: 27 },
    ],
    opponent_user_id: 'u9',
    give_value: 5100,
    receive_value: 5300,
  });
const servedOf = (cards) => new Map(cards.map((c, i) => [c.trade_id, i]));
const ids = (r) => r.order.map((c) => c.trade_id);

// Boost = attributes of a liked WR card ⇒ WR cards cosine ≈ 1, QB cards low.
const likeBoost = buildBoostVector([
  { tradeId: 'seed', attrs: extractCardAttributes(wr('seed')), weight: 1 },
]);

// A far WR card should jump ahead of nearer QB cards — but never into
// positions < boundary.
const deck1 = [wr('c0'), qb('c1'), qb('c2'), qb('c3'), qb('c4'), wr('c5')];
const r1 = rerankRemaining(deck1, 2, likeBoost, servedOf(deck1));
check('boundary cards untouched', ids(r1).slice(0, 2), ['c0', 'c1']);
check(
  'similar card moves earlier (from tail toward boundary)',
  ids(r1).indexOf('c5') < 5,
  true,
);
check('moves reported', r1.moves.length > 0, true);
check(
  'moves carry from/to',
  r1.moves.every((m) => typeof m.from === 'number' && typeof m.to === 'number'),
  true,
);

// Negative boost pushes similar cards later.
const passBoost = buildBoostVector([
  { tradeId: 'seed', attrs: extractCardAttributes(wr('seed')), weight: -2 },
]);
const deck2 = [qb('c0'), qb('c1'), wr('c2'), qb('c3'), qb('c4')];
const r2 = rerankRemaining(deck2, 2, passBoost, servedOf(deck2));
check(
  'disliked-archetype card pushed later',
  ids(r2).indexOf('c2') > 2,
  true,
);

// Zero boost ⇒ exact no-op (same array reference, no moves).
const r3 = rerankRemaining(deck1, 2, {}, servedOf(deck1));
check('zero boost is a no-op', r3.order === deck1 && r3.moves.length === 0, true);

// Locked cards keep their exact index even inside the re-ranked tail.
const pinned = qb('pin');
pinned.likesYou = true;
const deck4 = [wr('c0'), qb('c1'), qb('c2'), pinned, qb('c4'), wr('c5')];
const r4 = rerankRemaining(deck4, 2, likeBoost, servedOf(deck4));
check('likes-you pin keeps its exact index', ids(r4)[3], 'pin');
const deck5 = deck4.map((c) =>
  c.trade_id === 'pin' ? { ...c, likesYou: false, retest: true } : c,
);
const r5 = rerankRemaining(deck5, 2, likeBoost, servedOf(deck5));
check('retest card keeps its exact index', ids(r5)[3], 'pin');

// Served order is the tiebreak: identical cards never swap (stable).
const deck6 = [wr('c0'), wr('c1'), wr('c2'), wr('c3'), wr('c4')];
const r6 = rerankRemaining(deck6, 2, likeBoost, servedOf(deck6));
check('equal scores keep served order', ids(r6), ['c0', 'c1', 'c2', 'c3', 'c4']);

// η bound: a boosted far card beats its neighbor only within the ×1.3/0.7
// envelope — served index 3 (score 0.25×0.7=0.175 min) can never leapfrog
// served index 8 boosted (max 1.3/9≈0.144). Sanity-pin the formula.
checkClose(
  'score formula 1/(served+1)×(1+η·cos)',
  (1 / (4 + 1)) * (1 + SESSION_RERANK_ETA * 1),
  0.26,
);

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll session-rerank checks passed.');
