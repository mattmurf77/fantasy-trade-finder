#!/usr/bin/env node
// Decline-reason capture structural test.
// Spec: docs/plans/decline-reason-capture/SPEC.md
//
// WHY THIS EXISTS. Three properties of this feature are invisible to a
// green Maestro run and would each ship a quiet, expensive regression:
//
//   1. FLAG OFF IS BYTE-IDENTICAL (SPEC §5). The ✕ is not deleted — it is
//      conditioned on `disposition.reasons`. A refactor that drops the
//      condition removes Pass from every build; one that drops the guard
//      renders BOTH the ✕ and the tiles.
//   2. EVERY TAP COMMITS (SPEC §3). The load-bearing requirement is that
//      nothing waits for a submit: layer 1 writes the disposition AND the
//      reason, "Other" banks its code before the box opens, and the deck
//      advance is DEFERRED so layer 2 lands on the same card. A batching
//      refactor keeps every flow green and loses the partial answers the
//      whole feature exists to collect.
//   3. FREE TEXT IS NEVER AN ANALYTICS PROPERTY (SPEC §3.4/§6). It goes on
//      the row; the events carry the `has_free_text` boolean only.
//
// Also pins the taxonomy codes (SPEC §2) against the spec table itself, so
// an "improved" label or code fails here instead of silently splitting the
// dataset in two.
//
// Run: node tests/check-decline-reasons.js
//   (or: npm run test:decline-reasons)

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

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const MOBILE = path.join(__dirname, '..');
const REPO = path.join(MOBILE, '..');
const read = (rel, base = MOBILE) => fs.readFileSync(path.join(base, rel), 'utf8');

function parse(rel) {
  const file = path.join(MOBILE, rel);
  return ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
}
function findAll(root, pred) {
  const out = [];
  (function walk(n) {
    if (pred(n)) out.push(n);
    n.forEachChild(walk);
  })(root);
  return out;
}

const panelText = read('src/components/DeclineReasonPanel.tsx');
const cardText = read('src/components/TradeCard.tsx');
const screenText = read('src/screens/TradesScreen.tsx');
const apiText = read('src/api/declineReasons.ts');

// ═══════════════════════════════════════════════════════════════════════
// 1. Flag off is byte-identical — the ✕ is CONDITIONED, not deleted
// ═══════════════════════════════════════════════════════════════════════

const cardSrc = parse('src/components/TradeCard.tsx');
const guard = findAll(
  cardSrc,
  (n) => ts.isConditionalExpression(n) && n.condition.getText().trim() === 'disposition',
)[0];
assert(!!guard, 'TradeCard: the `disposition ?` guard still exists');
if (guard) {
  const inGuard = guard.whenTrue.getText();
  assert(
    inGuard.includes('testID="trades.pass-btn"'),
    'TradeCard: the ✕ still exists inside the disposition guard',
    'flag OFF must render the shipped ✓/✕ row — the ✕ is conditioned, never removed',
  );
  assert(
    /disposition\.reasons\s*\?\s*null\s*:\s*\(/.test(inGuard),
    'TradeCard: the ✕ renders only when `disposition.reasons` is absent',
    'without this condition a flag-ON build shows the ✕ AND the tiles',
  );
  assert(
    /disposition\.reasons\s*\?\s*\(?\s*<DeclineReasonPanel/.test(inGuard),
    'TradeCard: the panel renders only when `disposition.reasons` is present',
    'an unconditional mount would grow a tile row on every deck card',
  );
}
assert(
  /reasons\?:\s*DeclineReasonPanelProps/.test(cardText),
  'TradeCard: `disposition.reasons` is optional',
  'a required prop would force every caller to supply it — match/peek mounts must not',
);

// ═══════════════════════════════════════════════════════════════════════
// 2. Progressive writes — three commit moments, none batched (SPEC §3)
// ═══════════════════════════════════════════════════════════════════════

const COMMITS = [
  ['handleReasonLayer1', 'layer 1 — the tile tap'],
  ['handleReasonLayer2Select', 'layer 2 — a fixed option'],
  ['handleReasonLayer2Bank', 'layer 2 — "Other", banked before the box opens'],
  ['handleReasonLayer2Send', 'layer 2 — the free-text send'],
];
const screenSrc = parse('src/screens/TradesScreen.tsx');
const fns = new Map(
  findAll(screenSrc, (n) => ts.isFunctionDeclaration(n) && n.name).map((n) => [
    n.name.getText(),
    n.getText(),
  ]),
);
for (const [fn, what] of COMMITS) {
  const body = fns.get(fn);
  assert(!!body, `TradesScreen: ${fn} exists (${what})`);
  if (body) {
    assert(
      body.includes('postDeclineReason('),
      `TradesScreen: ${fn} writes immediately`,
      'SPEC §3 — every tap commits; nothing waits for a submit',
    );
  }
}

const l1 = fns.get('handleReasonLayer1') || '';
assert(
  l1.includes("advance('pass'") && /deferDeckAdvance:\s*true/.test(l1),
  'TradesScreen: the layer-1 tile tap fires the pass disposition, deck advance deferred',
  'SPEC §3.1 — the tile tap IS the pass; layer 2 must land on the SAME card',
);
const bank = fns.get('handleReasonLayer2Bank') || '';
assert(
  !bank.includes('commitReasonAdvance'),
  'TradesScreen: the "Other" bank does NOT advance the deck',
  'SPEC §3.3 — the code banks, then the box opens; the send advances',
);
for (const fn of ['handleReasonLayer2Select', 'handleReasonLayer2Send']) {
  assert(
    (fns.get(fn) || '').includes('commitReasonAdvance()'),
    `TradesScreen: ${fn} advances to the next trade`,
    'SPEC §1 — there is no receipt; the next trade is the confirmation',
  );
}
assert(
  !/setToast\(/.test(l1),
  'TradesScreen: the layer-1 tap shows no receipt toast',
  'SPEC §1 — no receipt screen, and no receipt toast standing in for one',
);

// ═══════════════════════════════════════════════════════════════════════
// 3. Free text never leaves as an analytics property (SPEC §3.4 / §6)
// ═══════════════════════════════════════════════════════════════════════

const trackCalls = findAll(
  screenSrc,
  (n) =>
    ts.isCallExpression(n) &&
    n.expression.getText() === 'track' &&
    /trade_pass_layer[12]/.test(n.arguments[0]?.getText() ?? ''),
);
assert(
  trackCalls.length === 3,
  'TradesScreen: exactly three decline-reason track() calls',
  `SPEC §6 — one layer-1 emitter, two layer-2 emitters; found ${trackCalls.length}`,
);
for (const call of trackCalls) {
  const props = call.arguments[1]?.getText() ?? '';
  assert(
    !/free_?[Tt]ext\s*[,:]/.test(props.replace(/has_free_text/g, '')),
    `TradesScreen: ${call.arguments[0].getText()} carries no free text`,
    'SPEC §3.4 — free text is stored on the row, never sent as an event property',
  );
  assert(
    /platform:/.test(props) || /reasonEventProps\(\)/.test(props),
    `TradesScreen: ${call.arguments[0].getText()} sets platform explicitly`,
    'the NULL-platform incident is why §6 enumerates it',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 4. Taxonomy matches SPEC §2, code for code
// ═══════════════════════════════════════════════════════════════════════

// The 8 codes, transcribed from SPEC §2. Held here rather than parsed out of
// the spec because SPEC.md is not on this branch (the plan folder lands with
// the backend half) — but when it IS present, the two are cross-checked below
// so the transcription can never quietly diverge from the spec it copies.
const SPEC_CODES = [
  'value_giving',
  'value_getting',
  'value_other',
  'fit_outlook',
  'fit_new_weakness',
  'fit_duplicate',
  'fit_other',
  'other_text',
];
const specPath = path.join(REPO, 'docs/plans/decline-reason-capture/SPEC.md');
if (fs.existsSync(specPath)) {
  const spec = fs.readFileSync(specPath, 'utf8');
  const inSpec = new Set(
    (spec.match(/`(value_[a-z]+|fit_[a-z_]+|other_text)`/g) || []).map((m) =>
      m.replace(/`/g, ''),
    ),
  );
  assert(
    inSpec.size === SPEC_CODES.length && SPEC_CODES.every((c) => inSpec.has(c)),
    'taxonomy: the transcribed codes still match SPEC §2',
    `spec has [${[...inSpec].sort().join(', ')}]`,
  );
} else {
  console.log('SKIP  taxonomy: SPEC.md not on this branch — codes checked against the transcription only');
}
for (const code of SPEC_CODES) {
  assert(
    panelText.includes(`'${code}'`) || apiText.includes(`| '${code}'`),
    `taxonomy: ${code} is implemented`,
    'SPEC §2 says do not improvise labels — and do not drop codes either',
  );
}
for (const l1code of ['value', 'fit', 'other']) {
  assert(
    new RegExp(`key:\\s*'${l1code}'`).test(panelText),
    `taxonomy: layer-1 code '${l1code}' is a tile`,
  );
}
assert(
  /'value'\s*\|\s*'fit'\s*\|\s*'other'/.test(apiText),
  'api/declineReasons: Layer1Code is exactly value|fit|other',
);

// ═══════════════════════════════════════════════════════════════════════
// 5. Touch targets + no truncation (SPEC-adjacent a11y requirements)
// ═══════════════════════════════════════════════════════════════════════

assert(
  // The attribute, not the word — the file's own comment says it avoids it.
  !/numberOfLines\s*=/.test(panelText) && !/ellipsizeMode\s*=/.test(panelText),
  'DeclineReasonPanel: nothing truncates',
  'option rows and tiles must WRAP under Dynamic Type, never ellipsize',
);
const minHeights = [...panelText.matchAll(/minHeight:\s*(\d+)/g)].map((m) => Number(m[1]));
assert(
  minHeights.length >= 3 && minHeights.every((h) => h >= 44),
  'DeclineReasonPanel: every tappable row clears the 44pt touch floor',
  `found minHeights: ${minHeights.join(', ')}`,
);
assert(
  /accessibilityState=\{\{\s*expanded/.test(panelText) &&
    /accessibilityState=\{\{\s*selected/.test(panelText),
  'DeclineReasonPanel: tiles report expanded, options report selected',
  'screen readers need the layer-1/layer-2 state, not just the label',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All decline-reason capture checks passed.');
