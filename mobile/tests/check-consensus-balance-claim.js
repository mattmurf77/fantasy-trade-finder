#!/usr/bin/env node
// The consensus card must not claim "balanced" below the app's own bar.
//
// THE DEFECT THIS PINS (arm-B engine audit, 2026-08-19, bug 2). TradeCard.tsx
// rendered "…this is a balanced trade by consensus value." gated on
// `basis === 'consensus'` alone — no fairness check of any kind. The app's own
// bar for balanced is 0.75, but the mobile fairness default flipped OFF on
// 2026-08-17 so the live generation floor is 0.50 and cards ship down to
// 0.501. Measured read-only against prod `deck_impressions`: 805 of 7,293
// served consensus cards (11.0%) carried that sentence while sitting below
// the app's own definition of balanced.
//
// THE SHAPE OF THE FIX (operator, 2026-08-19): the claim is REMOVED, not
// replaced. Below the bar the sub-line truncates to its true half — "This
// league-mate hasn't ranked players yet." — and stops. There is deliberately
// no prose about value there, because the card already renders TradeValueBar
// with favors/gap, which says direction and magnitude better than a sentence
// could. Two strings, not three.
//
// FIVE THINGS FAIL SILENTLY HERE, and none is visible to `tsc` or to any
// runtime check that survives D-056 (there is no simulator to screenshot):
//
//   1. THE GATE ITSELF. `consensusNote()` is a pure function; a future
//      "simplify" that returns one string for all cards compiles, typechecks,
//      and re-ships the false claim to 11% of consensus cards. §1 runs the
//      real module at the band edges.
//   2. THE FAIL-SAFE DIRECTION. Unknown fairness must fall to the TRUNCATED
//      string, never to "balanced". §1 pins it.
//   3. RE-ADDED PROSE. Someone "helpfully" restoring a value clause below the
//      bar re-creates the duplication the operator struck. §1 asserts the
//      sub-threshold string ENDS at the true half.
//   4. THRESHOLD DRIFT. The number lives in three TS spots (NORMAL_LOW,
//      FAIRNESS_ON_THRESHOLD, CONSENSUS_BALANCED_MIN) and one JS literal in
//      web. Moving one and leaving the copy asserting the old band is silent.
//      §2 pins all four to each other.
//   5. CLIENT DIVERGENCE. A string fixed in mobile and stale in web is WORSE
//      than not fixing it — the two surfaces then disagree about the same
//      card. §3 RECONSTRUCTS both web strings from web source and compares
//      them byte for byte against the module's own output. It does not look
//      for remembered wording, so it cannot pass vacuously when the wording
//      changes.
//
// The module is loaded and RUN (the check-fairness-default.js idiom:
// transpile the real TS, shim its imports) so §1 is behavioural, not a grep.
//
// Run: node tests/check-consensus-balance-claim.js
//   (or: npm run test:consensus-balance-claim)

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
const REPO = path.join(ROOT, '..');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}
function read(rel, base = ROOT) {
  return fs.readFileSync(path.join(base, rel), 'utf8');
}
function load(rel, requireShim) {
  const js = ts.transpileModule(read(rel), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const moduleShim = { exports: {} };
  new Function('module', 'exports', 'require', js)(
    moduleShim,
    moduleShim.exports,
    requireShim,
  );
  return moduleShim.exports;
}

// tradePresentation.ts is pure (one type-only import, erased by transpile),
// so it loads with a shim that refuses anything unexpected rather than
// silently returning undefined.
const presentation = load('src/utils/tradePresentation.ts', (name) => {
  throw new Error(
    `tradePresentation.ts gained an unexpected runtime import ("${name}") — ` +
      'extend the shim deliberately, do not let it pass silently.',
  );
});
const noteMod = load('src/utils/consensusNote.ts', (name) => {
  if (name === './tradePresentation') return presentation;
  throw new Error(
    `consensusNote.ts gained an unexpected runtime import ("${name}") — ` +
      'extend the shim deliberately, do not let it pass silently.',
  );
});

const { consensusNote, CONSENSUS_BALANCED_MIN } = noteMod;

const PREFIX    = "This league-mate hasn't ranked players yet";
const BALANCED  = `${PREFIX} — this is a balanced trade by consensus value.`;
const TRUNCATED = `${PREFIX}.`;

// ═══════════════════════════════════════════════════════════════════════
// 1. The gate, run for real at the band edges
// ═══════════════════════════════════════════════════════════════════════

assert(
  typeof consensusNote === 'function',
  'consensusNote is exported and callable',
);

assert(
  consensusNote(0.75).body === BALANCED && consensusNote(0.75).balanced === true,
  'exactly at the bar (0.75) → balanced claim',
  JSON.stringify(consensusNote(0.75)),
);
assert(
  consensusNote(1.0).body === BALANCED && consensusNote(0.86).body === BALANCED,
  'above the bar (0.86 = prod p50, 1.0 = dead even) → balanced claim',
);

// The whole point. 0.7499 and 0.501 are inside the live served band: prod
// min is 0.5010 and p10 is 0.7302, so BOTH of these are real cards.
assert(
  consensusNote(0.7499).body === TRUNCATED && consensusNote(0.7499).balanced === false,
  'just below the bar (0.7499) → truncated, no balance claim',
  JSON.stringify(consensusNote(0.7499)),
);
assert(
  consensusNote(0.501).body === TRUNCATED && consensusNote(0.55).body === TRUNCATED,
  'deep below the bar (0.501 = prod min, 0.55) → truncated',
);
assert(
  consensusNote(0.7302).body === TRUNCATED,
  'prod p10 (0.7302) → truncated',
  'the 805/7,293 population is exactly this band — a revert shows up here first',
);

// Fail-safe direction: absent/garbage fairness must never mint the claim.
for (const bad of [undefined, null, NaN, Infinity, -Infinity]) {
  const got = consensusNote(bad);
  assert(
    got.body === TRUNCATED && got.balanced === false,
    `unknown fairness (${String(bad)}) → truncated, never "balanced"`,
    JSON.stringify(got),
  );
}

// Exactly two distinct strings exist, and only one carries the claim.
const bodies = [0.9, 0.6, undefined, null, 1.0, 0.5].map((f) => consensusNote(f).body);
assert(
  new Set(bodies).size === 2,
  'the function yields exactly TWO distinct strings',
  JSON.stringify([...new Set(bodies)]),
);
assert(
  bodies.filter((b) => /balanced/i.test(b)).length === 2,
  'only the at-or-above-bar cards contain the word "balanced"',
  JSON.stringify(bodies),
);

// The explanation half is never dropped — "this league-mate hasn't ranked
// players yet" is TRUE of every consensus card and is real information that
// NOTHING ELSE on the card conveys (it says why this is a fair-value idea
// rather than a divergence card). Hiding the line would silently lose it.
assert(
  bodies.every((b) => b.startsWith(PREFIX)),
  'every state keeps the "hasn\'t ranked players yet" explanation',
  'the fix removes the claim — it does not hide the line',
);

// No re-added prose below the bar. The sub-threshold string ENDS at the true
// half; the TradeValueBar (favors/gap) is what conveys value, and duplicating
// it in words is what the operator struck on 2026-08-19.
assert(
  consensusNote(0.6).body === `${PREFIX}.`,
  'the sub-threshold string ends at the true half — no value clause re-added',
  JSON.stringify(consensusNote(0.6).body),
);
assert(
  !/priced from public values|even split|leans/i.test(bodies.join(' ')),
  'no "priced from public values" / "even split" / "leans" prose anywhere',
  'the value verdict belongs to TradeValueBar, not to this sentence',
);

// Symmetric field, so the copy must not pick a winner (design law P3).
assert(
  bodies.every((b) => !/\byou\b|\byour\b|worse|better|against you|in your favou?r/i.test(b)),
  'no state names a winner (fairness is a symmetric min/max ratio)',
  JSON.stringify([...new Set(bodies)]),
);

// ═══════════════════════════════════════════════════════════════════════
// 2. Threshold agreement — four spellings of 0.75, pinned to each other
// ═══════════════════════════════════════════════════════════════════════

const pregenSrc = read('src/api/tradePregen.ts');
const onThresholdMatch = pregenSrc.match(/export const FAIRNESS_ON_THRESHOLD\s*=\s*([\d.]+)/);
const FAIRNESS_ON_THRESHOLD = onThresholdMatch ? Number(onThresholdMatch[1]) : NaN;

assert(
  CONSENSUS_BALANCED_MIN === 0.75,
  'CONSENSUS_BALANCED_MIN is 0.75',
  String(CONSENSUS_BALANCED_MIN),
);
assert(
  presentation.NORMAL_LOW === CONSENSUS_BALANCED_MIN,
  'CONSENSUS_BALANCED_MIN === tradePresentation.NORMAL_LOW',
  `${presentation.NORMAL_LOW} vs ${CONSENSUS_BALANCED_MIN}`,
);
assert(
  FAIRNESS_ON_THRESHOLD === CONSENSUS_BALANCED_MIN,
  'CONSENSUS_BALANCED_MIN === api/tradePregen.FAIRNESS_ON_THRESHOLD',
  `${FAIRNESS_ON_THRESHOLD} vs ${CONSENSUS_BALANCED_MIN}`,
);

// consensusNote must RE-EXPORT the constant, not redeclare a fourth literal.
const noteSrc = read('src/utils/consensusNote.ts');
assert(
  /import\s*\{\s*NORMAL_LOW\s*\}\s*from\s*'\.\/tradePresentation'/.test(noteSrc)
    && /export const CONSENSUS_BALANCED_MIN = NORMAL_LOW;/.test(noteSrc),
  'consensusNote re-exports NORMAL_LOW rather than hardcoding 0.75',
  'a private literal here is how the band silently forks',
);
assert(
  /Number\.isFinite\(fairness\)/.test(noteSrc),
  'consensusNote uses Number.isFinite (not the coercing global isFinite)',
);

// ═══════════════════════════════════════════════════════════════════════
// 3. Both clients, byte-identical strings, same constant
// ═══════════════════════════════════════════════════════════════════════

const card = read('src/components/TradeCard.tsx');
const web = read('web/js/app.js', REPO);

// Mobile renders the derived copy, not a literal.
assert(
  /const note = consensusNote\(data\.fairness\)/.test(card),
  'TradeCard derives the note from consensusNote(data.fairness)',
);
assert(
  /<Text style=\{type\.label\}>\{note\.label\}<\/Text>/.test(card)
    && /\{note\.body\}/.test(card),
  'TradeCard renders note.label and note.body (no inline string)',
);
assert(
  !card.includes('balanced trade by consensus value'),
  'the pre-fix literal is GONE from TradeCard.tsx',
  'an inline copy of the claim defeats the gate entirely',
);

// Web gates on the shared constant and the non-coercing guard.
assert(
  /const FAIRNESS_BALANCED_MIN = 0\.75;/.test(web),
  'web declares FAIRNESS_BALANCED_MIN = 0.75',
);
assert(
  /f >= FAIRNESS_BALANCED_MIN/.test(web),
  'web gates the consensus tooltip on FAIRNESS_BALANCED_MIN',
  'a bare 0.75 here is drift waiting to happen',
);
assert(
  /const f = card\.fairness_score;/.test(web),
  'web reads card.fairness_score for the gate',
);
assert(
  /typeof f === 'number' && Number\.isFinite\(f\)/.test(web),
  'web uses Number.isFinite (not the coercing global isFinite)',
);

// ── BYTE PARITY, reconstructed rather than remembered ──────────────────
// Pull web's prefix literal and both tooltip templates out of source, expand
// them, and compare to what the MODULE actually returns. This is what makes
// sabotage S3 (fix mobile, leave web stale) fail: it compares the two clients
// to each other, not either one to a string typed into this test.
const webPrefix = (web.match(/const prefix = "([^"]+)";/) || [])[1];
assert(
  typeof webPrefix === 'string' && webPrefix.length > 0,
  'web declares a `prefix` literal the check can extract',
  'if this shape changed, update the extraction — do not delete the parity check',
);

const webTemplates = (
  web.match(/const tip = balanced\s*\n\s*\?\s*`([^`]*)`\s*\n\s*:\s*`([^`]*)`;/) || []
).slice(1);
assert(
  webTemplates.length === 2,
  'web builds exactly TWO tooltip templates from a `balanced` ternary',
  `found ${webTemplates.length}`,
);

// Deliberately NOT wrapped in `if (extraction succeeded)`. A failed extraction
// means web no longer has the shape this parity depends on, which is exactly
// the divergence being guarded against — so it must FAIL these assertions, not
// skip them. Skipping is how a cross-client guard silently stops guarding.
const expand = (tpl) =>
  typeof webPrefix === 'string' && typeof tpl === 'string'
    ? tpl.replace(/\$\{prefix\}/g, webPrefix)
    : null;
const webBalanced  = expand(webTemplates[0]);
const webTruncated = expand(webTemplates[1]);

assert(
  webBalanced === consensusNote(0.9).body,
  'web balanced tooltip is BYTE-IDENTICAL to mobile consensusNote(>=0.75)',
  `web: ${JSON.stringify(webBalanced)} vs mobile: ${JSON.stringify(consensusNote(0.9).body)}`,
);
assert(
  webTruncated === consensusNote(0.6).body,
  'web sub-threshold tooltip is BYTE-IDENTICAL to mobile consensusNote(<0.75)',
  `web: ${JSON.stringify(webTruncated)} vs mobile: ${JSON.stringify(consensusNote(0.6).body)}`,
);
assert(
  webTruncated === consensusNote(undefined).body,
  'web sub-threshold tooltip also covers the unknown-fairness case',
);
assert(
  webBalanced !== null && webTruncated !== null && webBalanced !== webTruncated,
  'web actually renders two DIFFERENT strings (the gate is not cosmetic)',
);

assert(
  !/title="This league-mate hasn't ranked players yet — this is a balanced trade/.test(web),
  'the pre-fix unconditional web tooltip is GONE',
);

// ═══════════════════════════════════════════════════════════════════════
process.exit(failures === 0 ? 0 : 1);
