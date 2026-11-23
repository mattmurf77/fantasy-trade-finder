#!/usr/bin/env node
// A "They're interested" card never reads as an unranked, zero-strength idea
// (sim pass B).
//
// WHY THIS EXISTS. Release simulator pass, 2026-11-22: a deck card showed the
// "THEY'RE INTERESTED" badge together with "FAIR-VALUE IDEA — This
// league-mate hasn't ranked players yet — this is a balanced trade by
// consensus value." and "MATCH STRENGTH 0". The other owner had a full board,
// and the match the card formed showed strength 100.
//
// ROOT CAUSE (server payload, read literally by the client). When the
// counterparty has liked a package the deck did not generate itself, the
// likes-you injector SYNTHESIZES the mirror card
// (backend/server.py `_inject_likes_you_cards_impl`, and its standing-offer
// branch) with `basis="consensus"` and `mismatch_score=0.0`: it was never
// built from two boards, so there is no divergence basis and no strength.
// The mobile normalizer maps mismatch_score 0 to match_score 0, and
// TradeCard rendered the consensus note on `basis === 'consensus'` alone and
// the StrengthBar unconditionally. The fix is in TradeCard: a likes-you card
// with the consensus basis (the synthesized mirror) shows neither the
// unranked framing nor the uncomputed strength; the badge and the value bar
// carry it. Organic cards (divergence basis, or consensus without the badge)
// are untouched.
//
// What is pinned (TradeCard.tsx):
//   1. `likesYouMirror` is exactly `likesYou && isConsensus`.
//   2. The consensus note's gate excludes it.
//   3. The StrengthBar's gate excludes it.
//   4. The server still synthesizes likes-you mirrors as basis "consensus"
//      with mismatch 0 (if that changes, this client rule must be revisited,
//      not silently kept).
//
// HONEST LABEL (G-035): presence of exact wirings in source, not a render.
//
// Run: node tests/check-likes-you-card.js   (or npm run test:likes-you-card)

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const REPO = path.resolve(ROOT, '..');
const failures = [];
const passes = [];
const ok = (n) => passes.push(n);
const bad = (n, d) => failures.push(`${n}\n      ${d}`);
const check = (n, cond, d = '') => (cond ? ok(n) : bad(n, d || 'condition false'));
const read = (p) => (fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : (bad(`exists: ${p}`, 'missing'), ''));
// Comments carry the history and quote the old gates verbatim; strip them so
// a pin can only be satisfied by code.
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

const card = strip(read(path.join(ROOT, 'src/components/TradeCard.tsx')));

check('1. likesYouMirror = likesYou && isConsensus',
  /const likesYouMirror = likesYou && isConsensus;/.test(card)
    && /const isConsensus = data\.basis === 'consensus';/.test(card)
    && /const likesYou = data\.likesYou === true;/.test(card));

const noteGate = /\{(isConsensus[^\n]*?)\s*&&\s*\(\s*<View style=\{styles\.consensusNote\} testID="trade-card\.consensus-note">/.exec(card);
check('2. the "hasn\'t ranked players yet" note is not rendered on a likes-you mirror',
  !!noteGate && /!likesYouMirror/.test(noteGate[1]),
  noteGate ? `gate is {${noteGate[1]} && ...}` : 'consensus-note mount not found');

const strengthGate = /\{([^{}\n]*?)\s*&&\s*\(\s*<StrengthBar value=\{matchPct\} label="Match strength"/.exec(card);
check('3. "Match strength" is not rendered on a likes-you mirror',
  !!strengthGate && /!likesYouMirror/.test(strengthGate[1]),
  strengthGate ? `gate is {${strengthGate[1]} && ...}` : 'StrengthBar mount not found');

const server = read(path.join(REPO, 'backend/server.py'));
const inj = server.slice(server.indexOf('def _inject_likes_you_cards_impl('));
const synth = /trade_id\s*=\s*f"likesyou_[\s\S]*?mismatch_score\s*=\s*0\.0,[\s\S]*?basis\s*=\s*"consensus",\s*likes_you\s*=\s*True,/.test(inj);
check('4. the server still synthesizes likes-you mirrors as consensus + mismatch 0 (the case §1–3 key on)',
  synth, 'the synthesized likes-you card shape changed: revisit TradeCard\'s likesYouMirror rule');

for (const p of passes) console.log(`  ✓ ${p}`);
if (failures.length) {
  console.error('\nFAILURES:');
  for (const f of failures) console.error(`  ✗ ${f}`);
  console.error(`\ncheck-likes-you-card: ${failures.length} FAILED`);
  process.exit(1);
}
console.log(`\ncheck-likes-you-card: all ${passes.length} checks passed`);
