#!/usr/bin/env node
// Composite-window guard (#372 starter dynasty value + playoff likelihood +
// down-weighted age, flag `trade.outlook_composite`).
//
// WHY THIS EXISTS. The backend carries 37 tests for the composite, but every
// claim below is about client SHAPE — what the window beat is willing to say,
// and under which condition — which no backend test and no typecheck can see.
// Under D-056 a structural guard is the only automated evidence these get.
//
// What is pinned, and why each is a real regression rather than a style:
//   1. The two new weights are READ off `window.model`, never restated. This
//      is D-101's third outing: the beat once said "age 23 and under" against
//      a `youth_age` of 26, and #372 makes it worse — under the composite
//      `w_vet_share` is 0.40 rather than 1.00, so a hardcoded weight would
//      now print arithmetic that does not add up to the total beside it.
//   2. A term that SCORES is a term that SHOWS. Both new contribution rows
//      are gated on the SAME `applied` flag the backend scored them under.
//   3. The composite is detected from the PAYLOAD (`signals.starters.applied`
//      + `model.composite`), never from a client-held feature flag. The client
//      cannot know whether the backend applied the vector, so inferring it
//      would desynchronise the card from the score.
//   4. `applied` is the gate, never `index !== 0`. A perfectly average
//      starting lineup and a lineup we could not read both index at 0.
//   5. Every degraded provenance is STATED. All three starter values and all
//      four playoff values must produce copy — the operator's ruling was
//      "degrade honestly and say so on the card".
//   6. The "that is the whole model" sentence stays CONDITIONAL. It already
//      says the model "does not read your starting lineup", which becomes a
//      lie the instant this flag is lit.
//   7. Both new blocks and every new model key are OPTIONAL in the type: the
//      flag defaults OFF, so they are absent on essentially every payload.
//
// Run: node tests/check-window-composite.js  (or npm run test:window-composite)
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
// a claim about Window.
function slice(name) {
  const start = s.indexOf(`function ${name}(`);
  if (start < 0) return '';
  const next = s.indexOf('\nfunction ', start + 1);
  return s.slice(start, next < 0 ? s.length : next);
}
const win = slice('Window');
if (!win) bad('0. the Window beat exists', 'no `function Window(` in TeamReviewScreen.tsx');

// 1 — the composite weights are read, never restated
{
  const reads = [
    [/m\?\.w_starter_index/, 'model.w_starter_index'],
    [/m\?\.w_playoff_index/, 'model.w_playoff_index'],
    [/m\?\.composite/, 'model.composite'],
  ].filter(([re]) => !re.test(win)).map(([, n]) => n);
  if (reads.length) {
    bad('1. the composite weights come off window.model',
      `${reads.join(', ')} is never read. Under the composite w_vet_share is `
      + '0.40, not 1.00 — a restated weight prints arithmetic that does not '
      + 'add up to the total beside it (D-101).');
  } else ok('1. every composite weight is read off window.model');

  // No literal composite weight anywhere in the beat.
  const literals = win.match(/[^.\w](0\.40|0\.60|0\.4\b|0\.6\b)[^\d]/g) || [];
  if (literals.length) {
    bad('1b. no composite weight is hardcoded in the beat',
      `found ${literals.map((x) => x.trim()).join(', ')} — the weights live in `
      + '`model`, and a copy of one drifts the day a knob moves.');
  } else ok('1b. no composite weight literal appears in the beat');
}

// 2 — a term that scores is a term that shows
{
  const starterRow = /starterScored[\s\S]{0,400}?wStarter as number/.test(win);
  const playoffRow = /playoffScored[\s\S]{0,400}?wPlayoff as number/.test(win);
  if (!starterRow || !playoffRow) {
    bad('2. both new contribution rows are itemised',
      `${!starterRow ? 'starter' : ''}${!starterRow && !playoffRow ? ' and ' : ''}`
      + `${!playoffRow ? 'playoff' : ''} row missing from the inputs card. A `
      + 'total the card did not itemise is the defect D-101 names.');
  } else ok('2. both new contribution rows are itemised off the payload weight');
}

// 3 — detected from the payload, never from a client-held flag
{
  if (/isEnabled|featureFlags|FLAGS/.test(win)) {
    bad('3. the beat reads no feature flag',
      'the client cannot know whether the backend APPLIED the vector; '
      + 'inferring it desynchronises the card from the score.');
  } else ok('3. the beat holds no feature flag');

  if (!/const composite = [^\n]*st\.applied[^\n]*m\?\.composite/.test(win)) {
    bad('3b. `composite` is derived from BOTH payload markers',
      'expected `signals.starters.applied` AND `model.composite`. Either alone '
      + 'can be true on a payload the other half of is missing.');
  } else ok('3b. `composite` is derived from signals.starters.applied + model.composite');
}

// 4 — `applied` is the gate, never a zero index
//
// REWRITTEN AFTER ITS OWN SABOTAGE FAILED TO TRIP IT. The first version read
//   /starters[\s\S]{0,80}index\s*[!=]==?\s*0/
// which required the literal word "starters" within 80 characters of the
// comparison — and the real gate is written `st.index`, so replacing
// `composite &&` with `st.index !== 0` sailed straight past. Match the
// COMPARISON itself, wherever it appears in the beat: equality against 0 on
// any `.index` is the mistake, and the `>` / `<` comparisons the copy uses to
// pick a phrase are deliberately not equality.
{
  const zeroGates = win.match(/\.index\s*[!=]==?\s*0(?!\.\d)/g) || [];
  if (zeroGates.length) {
    bad('4. neither term is gated on `index !== 0`',
      `found ${zeroGates.map((x) => x.trim()).join(', ')}. An exactly average `
      + 'starting lineup and a lineup we could not read both index at 0 — '
      + '`applied` is the only correct test.');
  } else ok('4. neither term is gated on a zero index');

  // The positive half: both `Scored` flags must actually consult `applied`.
  if (!/const starterScored = composite/.test(win)
      || !/const playoffScored = composite && !!po && po\.applied/.test(win)) {
    bad('4b. both `Scored` flags derive from `applied`',
      'starterScored must derive from `composite` (which is `st.applied`) and '
      + 'playoffScored from `po.applied` — nothing else says the backend '
      + 'actually scored the term.');
  } else ok('4b. both `Scored` flags derive from `applied`');

  // 4c — the starter CARD reports the measurement, the arithmetic ROW reports
  // what scored. The cap binds on real rosters, so printing `index` in the
  // "% above average" sentence understates a lopsided team by whatever the cap
  // withheld — D-101 from a new angle.
  if (!/index_raw > 0\.02/.test(win) || !/pct\(st\.index_raw\)/.test(win)) {
    bad('4c. the starter card reports `index_raw`, not the capped `index`',
      'the cap binds on real rosters (FFV3 measures +0.82 and scores +0.50), so '
      + 'the "% above average" sentence must read the MEASURED index.');
  } else ok('4c. the starter card reports the measured index');
  if (!/st\.index !== st\.index_raw/.test(win)) {
    bad('4d. the beat names the cap when it bit',
      'showing a measurement the model did not fully use, without saying so, is '
      + 'the defect from the other direction.');
  } else ok('4d. the beat names the cap when it bit');
}

// 5 — every degraded provenance is stated
{
  const starterProv = ['observed', 'lineup_unknown'];
  const playoffProv = ['observed', 'preseason', 'odds_unavailable'];
  const missing = [...starterProv, ...playoffProv]
    .filter((p) => !win.includes(`'${p}'`));
  if (missing.length) {
    bad('5. every provenance produces copy',
      `${missing.join(', ')} is never branched on. A refused signal rendered as `
      + 'a silent zero reads as a real signal — degrade honestly and say so.');
  } else ok('5. every starter and playoff provenance is branched on');

  // The `absent` / `odds_disabled` tails are the else-branches, so they are
  // pinned by the presence of a fallback rather than by their own literal.
  const starterCard = win.includes("testID=\"team-review.window.starters\"");
  const playoffCard = win.includes("testID=\"team-review.window.playoff\"");
  if (!starterCard || !playoffCard) {
    bad('5b. both new cards carry a testID',
      `${!starterCard ? 'team-review.window.starters ' : ''}`
      + `${!playoffCard ? 'team-review.window.playoff' : ''} missing.`);
  } else ok('5b. both new cards carry a testID');
}

// 6 — the "whole model" sentence stays conditional
{
  const stale = /That is the whole model — roster age and pick capital\./;
  const guardless = stale.test(win) && !/composite \?/.test(win);
  if (guardless) {
    bad('6. the "whole model" sentence branches on the composite',
      'the fixed copy claims the model "does not read your starting lineup", '
      + 'which is a lie the instant this flag is lit.');
  } else ok('6. the "whole model" sentence branches on the composite');
}

// 7 — the type keeps every new field optional
{
  const m = api.match(/export interface TeamReviewWindow \{[\s\S]*?\n\}/);
  if (!m) bad('7. TeamReviewWindow is declared', 'no interface in api/teamReview.ts');
  else {
    const t = m[0];
    const required = [
      [/\bstarters\?:/, 'signals.starters'],
      [/\bindex_raw: number;/, 'signals.starters.index_raw'],
      [/\bplayoff\?:/, 'signals.playoff'],
      [/\bcomposite\?:/, 'model.composite'],
      [/\bw_starter_index\?:/, 'model.w_starter_index'],
      [/\bstarter_index_cap\?:/, 'model.starter_index_cap'],
      [/\bw_playoff_index\?:/, 'model.w_playoff_index'],
      [/\bplayoff_center\?:/, 'model.playoff_center'],
      [/\bplayoff_index_cap\?:/, 'model.playoff_index_cap'],
    ].filter(([re]) => !re.test(t)).map(([, n]) => n);
    if (required.length) {
      bad('7. every flag-gated field is OPTIONAL in the type',
        `${required.join(', ')} is not optional. The flag defaults OFF, so these `
        + 'fields are absent on essentially every payload; a required field '
        + 'makes the type lie and invites an undefined read.');
    } else ok('7. all eight new fields are optional in the type');
  }
  if (!/'composite'/.test(t_source())) {
    bad('7b. `source` admits the composite',
      "TeamReviewWindow.source must include 'composite' — that is how the card "
      + 'knows the band was scored rather than obeyed.');
  } else ok("7b. `source` admits 'composite'");
  function t_source() {
    const mm = api.match(/source\?: [^\n;]+/);
    return mm ? mm[0] : '';
  }
}

console.log(`\ncheck-window-composite: ${pass.length} passed, ${fail.length} failed`);
for (const p of pass) console.log(`  ✓ ${p}`);
if (fail.length) {
  console.error('\nFAILURES:');
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.error('\nThese pin D-101 (a client reads an encoding, it never restates one) '
    + 'and D-140. If a change is genuinely intended, update DECISIONS.md in the '
    + 'SAME commit.\n');
  process.exit(1);
}
console.log('');
