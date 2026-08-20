#!/usr/bin/env node
// Window-beat signal guard (#365 net firsts, #371 playoff-odds window).
//
// WHY THIS EXISTS. The backend carries 40 tests for these two signals, but
// every claim below is about client SHAPE — what the window beat is willing to
// say, and under which condition — which no backend test and no typecheck can
// see. Under D-056 a structural guard is the only automated evidence these get.
//
// What is pinned, and why each is a real regression rather than a style:
//   1. The beat restates NO knob. D-101 exists because the screen shipped
//      saying "Value age 23 and under" while `youth_age` had been 26 — the
//      threshold the user read was never the threshold the inference applied.
//      Every weight, cut and age in the arithmetic must come off `window.model`.
//   2. A term that SCORES is a term that SHOWS. The net-firsts contribution row
//      is rendered off the same `model.w_net_firsts` the backend used, so the
//      card can never display a total it did not itemise.
//   3. The "we do not read which picks you have already traded away" sentence
//      is CONDITIONAL. It is true today and becomes a lie the moment
//      `trade.outlook_net_firsts` is lit, so it may not be fixed copy.
//   4. The degraded case is STATED. `provenance` other than `observed` must
//      produce a reason on screen — the operator's ruling was "degrade honestly
//      and say so on the card", and a silent zero reads as a real signal.
//   5. Both features render off the PAYLOAD, never off a client-held flag.
//      The client has no way to know whether the backend applied a term, so
//      inferring it would desynchronise the card from the score.
//
// Run: node tests/check-window-signals.js   (or npm run test:window-signals)
// CI picks it up automatically via the tests/check-*.js glob.

'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCREEN = path.join(ROOT, 'src/screens/TeamReviewScreen.tsx');
const API = path.join(ROOT, 'src/api/teamReview.ts');

const pass = [], fail = [];
const ok = (n) => pass.push(n);
const bad = (n, d) => fail.push(`${n}\n      ${d}`);
const read = (p) => (fs.existsSync(p)
  ? fs.readFileSync(p, 'utf8')
  : (bad('file exists', `missing ${path.relative(ROOT, p)}`), ''));
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const s = strip(read(SCREEN));
const api = read(API);

// The window beat's own source, so a match in Depth or Partners cannot satisfy
// a claim about Window. Bounded by the next top-level `function ` declaration.
function slice(name) {
  const start = s.indexOf(`function ${name}(`);
  if (start < 0) return '';
  const next = s.indexOf('\nfunction ', start + 1);
  return s.slice(start, next < 0 ? s.length : next);
}
const win = slice('Window');
if (!win) bad('0. the Window beat exists', 'no `function Window(` in TeamReviewScreen.tsx');

// 1 — no restated knob
{
  // Any bare number attached to a model concept. The knobs live in
  // window.model; a literal here is the #365 defect class returning.
  const literals = [
    [/age\s+\d+\s+and\s+(over|under)/i, 'a hardcoded age threshold'],
    [/\bContending at [+\-−]?\d/i, 'a hardcoded contender cut'],
    [/rebuilding at [+\-−]?\d/i, 'a hardcoded rebuilder cut'],
    [/×\s*−?\d+(\.\d+)?\b/, 'a hardcoded weight in the arithmetic'],
  ];
  const hits = literals.filter(([re]) => re.test(win)).map(([, d]) => d);
  if (hits.length) {
    bad('1. the beat restates no knob',
      `${hits.join('; ')} in the Window beat. Every threshold, weight and cut `
      + 'must be read from window.model — the screen shipped saying "age 23 and '
      + 'under" against a youth_age of 26 (D-101).');
  } else if (!/\bm\.vet_age\b/.test(win) || !/\bm\.contender_cut\b/.test(win)) {
    bad('1. the beat reads the knobs it renders',
      'the Window beat does not reference m.vet_age / m.contender_cut, so it is '
      + 'not reading the model block it is supposed to render');
  } else ok('1. every knob rendered is read from window.model');
}

// 2 — a term that scores is a term that shows
{
  const rendersLedger = /signals\.firsts/.test(win);
  const rendersTerm = /w_net_firsts/.test(win);
  if (!rendersLedger) {
    bad('2. the net-firsts ledger is rendered',
      'the Window beat never reads window.signals.firsts, so the #365 signal is '
      + 'computed by the backend and never shown');
  } else if (!rendersTerm) {
    bad('2. the net-firsts CONTRIBUTION is itemised',
      'the beat reads signals.firsts but never model.w_net_firsts, so it shows '
      + 'the ledger without showing what the ledger did to the score. That is '
      + 'exactly the defect D-101 was written to prevent.');
  } else ok('2. the ledger and its contribution are both rendered');
}

// 3 — the "does not read traded picks" sentence is conditional
{
  const CLAIM = /which picks you have already traded/i;
  if (!CLAIM.test(win)) {
    ok('3. the "we ignore traded picks" claim is gone (or reworded)');
  } else {
    // It must sit inside a conditional branch keyed on the term being live —
    // i.e. the file also carries the opposite copy for the scored case.
    const hasScoredCopy = /the firsts you\s*\n?\s*have moved|and the firsts you/i.test(win);
    if (!hasScoredCopy) {
      bad('3. the "we ignore traded picks" claim is conditional',
        'the beat states it does not read which picks you have traded away, but '
        + 'carries no alternative copy for when trade.outlook_net_firsts IS on. '
        + 'That sentence becomes a lie the moment the flag is lit.');
    } else ok('3. the "we ignore traded picks" claim is conditional');
  }
}

// 4 — the degraded case is stated, not silent
{
  const namesNoneTraded = /none_traded/.test(win);
  const namesAbsent = /provenance/.test(win);
  if (!namesAbsent) {
    bad('4. the degraded ledger is explained',
      'the beat never reads firsts.provenance, so a league whose pick history '
      + 'predates capture renders a confident zero. Operator ruling: degrade '
      + 'honestly and say so on the card.');
  } else if (!namesNoneTraded) {
    bad('4. the none_traded case is distinguished from absent',
      'the beat reads provenance but never branches on none_traded — "no first '
      + 'has moved" and "we have no pick records" are different sentences.');
  } else ok('4. both degraded provenances are explained on the card');
}

// 5a — rendered off the payload, never off a client-held flag
{
  if (/isEnabled|useFlag|FLAGS\[/.test(win)) {
    bad('5a. the beat gates on the payload, not on a flag',
      'the Window beat reads a feature flag directly. The client cannot know '
      + 'whether the backend APPLIED a term; only the payload knows. Gate on '
      + 'signals.firsts / window.source instead.');
  } else ok('5a. gated on the payload, not on a client-held flag');
}

// 5b — `applied` is read, not re-derived
{
  if (!/\.applied\b/.test(win)) {
    bad('5b. the beat reads firsts.applied',
      'the beat never reads firsts.applied, so it must be inferring whether the '
      + 'term scored — from provenance, or worse from net_share === 0, which is '
      + 'indistinguishable from a genuine net of zero.');
  } else ok('5b. firsts.applied is read, not re-derived');
}

// 6 — #371: the source is read, and the heuristic's verdict survives
{
  if (!/window\.source|w\.source/.test(win)) {
    bad('6a. the beat reports which model drove',
      'no read of window.source, so an odds-driven verdict is presented as if it '
      + 'came from roster shape');
  } else ok('6a. the beat reports which model drove');

  if (!/roster_inferred/.test(win)) {
    bad('6b. the heuristic verdict survives an odds override',
      'no read of window.roster_inferred — the payload carries both definitions '
      + 'of "contender" precisely so the card can show both');
  } else ok('6b. the heuristic verdict is still shown');

  if (!/odds_reason/.test(win)) {
    bad('6c. a refused band names its reason',
      'no read of window.odds_reason, so preseason refusal and "no odds at all" '
      + 'render identically — as silence');
  } else ok('6c. a refused band names its reason');
}

// 7 — the API type keeps the new blocks OPTIONAL
{
  const m = api.match(/export interface TeamReviewWindow \{[\s\S]*?\n\}/);
  if (!m) bad('7. TeamReviewWindow is declared', 'no interface in api/teamReview.ts');
  else {
    const t = m[0];
    const required = [
      [/\bfirsts\?:/, 'signals.firsts'],
      [/\bsource\?:/, 'source'],
      [/\broster_inferred\?:/, 'roster_inferred'],
      [/\bodds\?:/, 'odds'],
      [/\bodds_reason\?:/, 'odds_reason'],
      [/\bw_net_firsts\?:/, 'model.w_net_firsts'],
    ].filter(([re]) => !re.test(t)).map(([, n]) => n);
    if (required.length) {
      bad('7. every flag-gated field is OPTIONAL in the type',
        `${required.join(', ')} is not optional. Both flags default OFF, so `
        + 'these fields are absent on most payloads; a required field makes the '
        + 'type lie and invites an undefined read.');
    } else ok('7. all six flag-gated fields are optional in the type');
  }
}

console.log(`\ncheck-window-signals: ${pass.length} passed, ${fail.length} failed`);
for (const p of pass) console.log(`  ✓ ${p}`);
if (fail.length) {
  console.error('\nFAILURES:');
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.error('\nThese pin D-101 (a client reads an encoding, it never restates one), '
    + 'D-110 and D-111. If a change is genuinely intended, update DECISIONS.md in the '
    + 'SAME commit.\n');
  process.exit(1);
}
console.log('');
