#!/usr/bin/env node
// Relaxed-pass deck disclosure regression test (#189 client half).
//
// WHY THIS EXISTS. The #189 relaxed fallback (targeted job, zero cards under
// the normal gates → fairness band widened, surplus floors dropped) stamps
// `relaxed: true` + `relaxed_reason` on every card it emits, and the #189
// convention is that clients label those cards honestly. The mobile deck
// silently dropped the field for months: the normalizer discarded it and
// TradeCard rendered relaxed cards indistinguishably from ordinary ones —
// only AssetIdeasPanel disclosed. This suite pins the whole chain so no
// single link can silently regress again:
//
//   1. shared/types.ts — TradeCard carries `relaxed` / `relaxed_reason`.
//   2. api/trades.ts — normalizeTradeCard passes both through, EXECUTED as
//      a unit test (transpiled with a stubbed './client'): `relaxed: true`
//      survives, absent/malformed values degrade to undefined.
//   3. TradeCard.tsx — the `trade-card.relaxed-chip` testID renders exactly
//      once, inside a `data.relaxed === true` guard, with the stretch label.
//   4. Wording stays consistent with AssetIdeasPanel's existing disclosure
//      ("Stretch — outside your fairness band").
//   5. TradesScreen.tsx declares no copy of the chip (single owner:
//      TradeCard — also what keeps this change out of G4's file).
//
// Run: node tests/check-relaxed-disclosure.js
//   (or: npm run test:relaxed-disclosure)

'use strict';

const fs = require('fs');
const path = require('path');
const Module = require('module');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

let failures = 0;
function ok(name) {
  console.log(`PASS  ${name}`);
}
function fail(name, detail) {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
}
function assert(cond, name, detail) {
  if (cond) ok(name);
  else fail(name, detail);
}

function read(rel) {
  return fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');
}

const STRETCH_SENTENCE = 'Stretch — outside your fairness band';
const STRETCH_LABEL = 'STRETCH — OUTSIDE YOUR FAIRNESS BAND';

// ═══════════════════════════════════════════════════════════════════════
// 1. shared/types.ts — the TradeCard wire type carries the fields
// ═══════════════════════════════════════════════════════════════════════

const typesText = read('src/shared/types.ts');
const cardIface = typesText.slice(
  typesText.indexOf('export interface TradeCard {'),
  typesText.indexOf('export interface TradeMatch'),
);
assert(
  /relaxed\?:\s*boolean/.test(cardIface),
  'types.ts: TradeCard declares relaxed?: boolean',
);
assert(
  /relaxed_reason\?:\s*string/.test(cardIface),
  'types.ts: TradeCard declares relaxed_reason?: string',
);

// ═══════════════════════════════════════════════════════════════════════
// 2. api/trades.ts — normalizeTradeCard passes the fields through (unit)
// ═══════════════════════════════════════════════════════════════════════
//
// Executed, not grepped: transpile trades.ts to CommonJS with './client'
// stubbed, then run real payloads through getTradeStatus (the deck's own
// path — generate/status share normalizeJobSnapshot → normalizeTradeCard).

function loadTradesModule(stubResponse) {
  const src = read('src/api/trades.ts');
  const js = ts.transpileModule(src, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2019,
    },
  }).outputText;
  const m = new Module('trades-under-test');
  m._compile = Module.prototype._compile;
  const sandboxRequire = (spec) => {
    if (spec === './client') {
      return {
        api: {
          get: async () => stubResponse,
          post: async () => stubResponse,
        },
      };
    }
    // Type-only imports ('../shared/types', './calc') are erased by the
    // transpile; anything else reaching here is an unexpected new runtime
    // dependency — surface it loudly instead of stubbing blind.
    throw new Error(`unexpected runtime import in trades.ts: ${spec}`);
  };
  const exports = {};
  const fn = new Function('require', 'module', 'exports', js);
  fn(sandboxRequire, { exports }, exports);
  return exports;
}

const baseCard = {
  trade_id: 't1',
  league_id: 'l1',
  opponent_user_id: 'u2',
  opponent_username: 'opp',
  give_players: [],
  receive_players: [],
  mismatch_score: 120,
  fairness_score: 0.8,
};

(async () => {
  try {
    // Case A: relaxed card — both fields survive normalization.
    const relaxedMod = loadTradesModule({
      job_id: 'j1',
      status: 'complete',
      cards: [{ ...baseCard, relaxed: true, relaxed_reason: 'fairness_band' }],
    });
    const relaxedSnap = await relaxedMod.getTradeStatus('j1');
    const rc = relaxedSnap.cards[0];
    assert(
      rc && rc.relaxed === true,
      'normalizer: relaxed: true survives normalization',
    );
    assert(
      rc && rc.relaxed_reason === 'fairness_band',
      'normalizer: relaxed_reason string survives normalization',
    );

    // Case B: ordinary card — both fields absent, exactly as before.
    const plainMod = loadTradesModule({
      job_id: 'j2',
      status: 'complete',
      cards: [{ ...baseCard }],
    });
    const pc = (await plainMod.getTradeStatus('j2')).cards[0];
    assert(
      pc && pc.relaxed === undefined && pc.relaxed_reason === undefined,
      'normalizer: absent fields stay undefined (ordinary cards unchanged)',
    );

    // Case C: malformed payload degrades — truthy-but-not-true relaxed is
    // rejected; a non-string reason is dropped even when relaxed is real.
    const malformedMod = loadTradesModule({
      job_id: 'j3',
      status: 'complete',
      cards: [
        { ...baseCard, relaxed: 'yes', relaxed_reason: 'fairness_band' },
        { ...baseCard, relaxed: true, relaxed_reason: 42 },
      ],
    });
    const [mc1, mc2] = (await malformedMod.getTradeStatus('j3')).cards;
    assert(
      mc1 && mc1.relaxed === undefined && mc1.relaxed_reason === undefined,
      "normalizer: relaxed: 'yes' (non-boolean) degrades to undefined",
    );
    assert(
      mc2 && mc2.relaxed === true && mc2.relaxed_reason === undefined,
      'normalizer: non-string relaxed_reason drops while relaxed survives',
    );
  } catch (e) {
    fail('normalizer unit tests executed', e && e.message);
  }

  // ═════════════════════════════════════════════════════════════════════
  // 3. TradeCard.tsx — the chip renders once, guarded, correctly worded
  // ═════════════════════════════════════════════════════════════════════

  const cardText = read('src/components/TradeCard.tsx');
  const chipIdx = cardText.indexOf('testID="trade-card.relaxed-chip"');
  assert(chipIdx !== -1, 'TradeCard: declares trade-card.relaxed-chip');
  assert(
    cardText.indexOf('testID="trade-card.relaxed-chip"', chipIdx + 1) === -1,
    'TradeCard: the chip testID is declared exactly once',
  );
  // The guard: the chip's JSX must sit inside a `data.relaxed === true &&`
  // conditional — strict-true, mirroring the wildcard chip, so a malformed
  // truthy value that slipped past the normalizer still renders nothing.
  const guardIdx = cardText.indexOf('{data.relaxed === true && (');
  assert(
    guardIdx !== -1 && guardIdx < chipIdx,
    'TradeCard: chip is guarded by `data.relaxed === true`',
    'a loosened guard (truthy check / no guard) would label ordinary cards',
  );
  assert(
    cardText.includes(STRETCH_LABEL),
    `TradeCard: chip label is "${STRETCH_LABEL}"`,
  );
  assert(
    cardText.includes(`accessibilityLabel="${STRETCH_SENTENCE}"`),
    'TradeCard: chip carries the sentence-case accessibility label',
  );

  // ═════════════════════════════════════════════════════════════════════
  // 4. AssetIdeasPanel.tsx — wording stays consistent across surfaces
  // ═════════════════════════════════════════════════════════════════════

  assert(
    read('src/components/AssetIdeasPanel.tsx').includes(STRETCH_SENTENCE),
    'AssetIdeasPanel: still discloses with the same stretch wording',
    'the two relaxed disclosures must not drift apart',
  );

  // ═════════════════════════════════════════════════════════════════════
  // 5. TradesScreen.tsx — no second declaration (TradeCard is the owner)
  // ═════════════════════════════════════════════════════════════════════

  assert(
    !read('src/screens/TradesScreen.tsx').includes('trade-card.relaxed-chip'),
    'TradesScreen: declares no copy of the relaxed chip',
  );

  console.log('');
  if (failures) {
    console.error(`${failures} check(s) failed.`);
    process.exit(1);
  }
  console.log('All relaxed-disclosure checks passed.');
})();
