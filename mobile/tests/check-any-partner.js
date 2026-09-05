#!/usr/bin/env node
// FB-406 — "Any league mate" partner scope on the merged calculator, plus
// the R-10 seed-prefill fix (FB-407 QA-B-1). Fifteen assertions (A-1…A-15,
// incl. A-11b), each mapped to a named sabotage in
// docs/feedback/items/406-target-any-leaguemate/prd.md §E-1.
//
// Run: node tests/check-any-partner.js

'use strict';

const fs = require('fs');
const path = require('path');
const SRC = path.join(__dirname, '..', 'src');
let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}`); if (detail) console.log(`      ${detail}`); }
}
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const calc = read('components/InLeagueCalculator.tsx');
const canvas = read('components/TradeBuildCanvas.tsx');
const trades = read('screens/TradesScreen.tsx');
const fork = read('utils/canvasSearch.ts');

const norm = (s) => s.replace(/\s+/g, ' ');
const lineOf = (src, idx) => src.slice(0, idx).split('\n').length;
function indicesOf(src, needle) {
  const out = [];
  for (let i = src.indexOf(needle); i >= 0; i = src.indexOf(needle, i + 1)) out.push(i);
  return out;
}

console.log('check-any-partner:');

// ── A-1 — the Anyone row lives inside the team-sheet Modal, above the
// member rows (sabotage S-1 revert-row: delete the row).
const sheetAt = calc.indexOf('testID="calc.team-sheet"');
const sheetEnd = calc.indexOf('</Modal>', sheetAt);
const anyAt = calc.indexOf('testID="calc.team-sheet.any"');
const sheetMapAt = calc.indexOf('opponents.map(', sheetAt);
assert(sheetAt > 0 && sheetEnd > sheetAt, 'A-1. the merged team sheet region is locatable');
assert(anyAt > sheetAt && anyAt < sheetEnd,
  'A-1. calc.team-sheet.any renders inside the team-sheet Modal region',
  'the Anyone row is gone (or moved out of the sheet) — the members-only sheet is back');
assert(sheetMapAt > 0 && anyAt < sheetMapAt,
  'A-1. …ABOVE the opponents.map member loop, outside it',
  'a row inside the loop would collide with member ids and render per member');

// ── A-2 — the Anyone tap is all three writes (sabotage S-2 half-state:
// drop setOpponentId(null) and the old partner keeps feeding evaluate).
{
  const start = calc.indexOf('onPress={() => {', anyAt);
  const body = start > 0 ? calc.slice(start, calc.indexOf('}}', start)) : '';
  for (const w of ['setPartnerAny(true)', 'setOpponentId(null)', 'setTeamPickerOpen(false)']) {
    assert(body.includes(w), `A-2. the Anyone onPress contains ${w}`,
      'the flag flips without the rest — a half-entered unscoped state');
  }
}

// ── A-3 — the default-to-first effect is guarded on the unscoped state
// (sabotage S-3 unguarded-default: the default re-selects the moment
// Anyone nulls the id).
{
  const at = calc.indexOf('setOpponentId(opponents[0].user_id)');
  assert(at > 0, 'A-3. the default-opponent effect still exists');
  const seg = calc.slice(Math.max(0, at - 300), at + 300);
  assert(/if \(!partnerAny && !opponentId && opponents\.length\)/.test(seg),
    'A-3. the default effect is guarded on !partnerAny',
    'unguarded, the unscoped state is unreachable: the default re-selects instantly');
  assert(/\}, \[opponents, opponentId, partnerAny\]\);/.test(seg),
    'A-3. …and lists partnerAny in its deps');
}

// ── A-4 — the FB-407 payload gate is intact (sabotage S-4 pass-through:
// unconditional `opponent ? {…} : null`). Cross-suite belt with
// check-calc-merged-behavior 20d — a regressing PR can edit one suite.
assert(/opponent: opponent && \(opponentChosenRef\.current \|\| receiveIds\.length > 0\)/.test(calc),
  'A-4. the find-a-trade payload keeps the chosen-or-receive-side gate',
  'ungated, the auto-default scopes every fresh canvas again (the FB-407 bug)');

// ── A-5 — the ✓ cell's disabled rule, verbatim and exactly once
// (sabotage S-5 broadened-cell: `|| partnerAny`, or dropping `!opponent`).
{
  const hits = indicesOf(calc, 'disabled={!onLikeTrade || !bothSides || !opponent || queueing}');
  assert(hits.length === 1,
    'A-5. the ✓ disabled expression appears verbatim, exactly once',
    `found ${hits.length} — anything broader re-creates the permanently-dead control; `
    + 'anything narrower lets a partnerless queue through');
}

// ── A-6 — evaluate never fires without a resolved partner id
// (sabotage S-6 unpartnered-eval: sides-only `enabled`).
{
  const at = calc.indexOf('const evalQ = useQuery');
  const seg = calc.slice(at, at + 900);
  assert(/enabled: !!opponentId &&/.test(seg),
    'A-6. evalQ.enabled requires a resolved opponentId',
    'relaxed, the query fires with a null (or sentinel) partner on the wire');
}

// ── A-7 — one partner-gated evaluate derivation; `evalQ.data` occurs
// exactly once (sabotage S-7 stale-verdict: render raw evalQ.data and the
// placeholderData leak shows the old partner's verdict under "Anyone").
{
  assert(/const ev = opponentId \? evalQ\.data : undefined;/.test(calc),
    'A-7. the ev derivation is gated on opponentId');
  const uses = indicesOf(calc, 'evalQ.data');
  assert(uses.length === 1,
    'A-7. evalQ.data is consumed exactly once (the gated derivation)',
    `found ${uses.length} — a second read bypasses the gate and can render the `
    + 'previous partner\'s placeholder data');
}

// ── A-8 — no sentinel partner id, anywhere (sabotage S-8 sentinel-swap:
// `setOpponentId('any')` reaching keys, args and request bodies).
// Best-effort by design (PRD N-6): a different sentinel string escapes
// these greps — the real guards are tsc (the opponent union has no string
// member) and A-6/A-7's opponentId-gating. Never trust A-8 for more.
assert(!/setOpponentId\(\s*['"]/.test(calc),
  'A-8. setOpponentId is never called with a string literal',
  'a sentinel id would flow into evaluate keys/args and request bodies');
assert(!/[=!]==\s*['"]any['"]/.test(calc) && !/['"]any['"]\s*[=!]==/.test(calc),
  'A-8. nothing compares against an \'any\' literal');
assert(!/opponent_user_id:\s*['"]any['"]/.test(calc) && !/opponent_user_id:\s*['"]any['"]/.test(trades),
  'A-8. no request body carries opponent_user_id: \'any\'');
assert(/opponent: \{ userId: string; name: string \} \| null;/.test(fork),
  'A-8. canvasSearch still types the fork opponent as {userId; name} | null',
  'an \'any\' union member would let a sentinel ride the wire with tsc\'s blessing');

// ── A-9 — the dropdown tells the truth in all three states (sabotage S-9
// lying-label: under Anyone the dropdown claims nothing is selected).
{
  const at = calc.indexOf('testID="calc.team-dropdown"');
  const seg = calc.slice(at, at + 1600);
  assert(/partnerAny\s*\?\s*'Anyone'/.test(seg),
    'A-9. the dropdown value has a partnerAny branch yielding \'Anyone\'');
  assert(/partnerAny\s*\n?\s*\?\s*'Team: Anyone — offers from every team\. Change team'/.test(seg),
    'A-9. the dropdown accessibilityLabel has the matching Anyone branch',
    'a sighted-only label leaves VoiceOver claiming no team is selected');
}

// ── A-10 — the scope-truth note renders on the EXACT complement of the
// payload gate (sabotages S-10a anyone-only-note and S-10b
// conjunction-flip — token presence is NOT enough, critic B-2).
{
  const noteAt = calc.indexOf('testID="calc.search-scope-note"');
  assert(noteAt > 0, 'A-10. calc.search-scope-note exists');
  const before = norm(calc.slice(Math.max(0, noteAt - 900), noteAt));
  assert(before.includes('partnerAny || (!partnerChosen && receiveIds.length === 0) ? ('),
    'A-10. the note\'s render predicate is the exact pinned form',
    'any other predicate desynchronizes the note from the payload gate — '
    + 'S-10a hides the OQ-1 honesty on the untouched default, S-10b hides it everywhere');
  const actionRowAt = calc.indexOf('testID="calc.action-row"');
  assert(actionRowAt > 0 && noteAt > actionRowAt
    && !calc.slice(actionRowAt, noteAt).includes(': null}'),
    'A-10. the note sits under the action row, inside the same merged branch',
    'the note escaping the merged branch would render on the stacked page');
}

// ── A-11 / A-11b — the ref↔state mirror cannot drift (sabotages S-11
// drifting-mirror and S-11b initializer-drift).
{
  const refWrites = indicesOf(calc, 'opponentChosenRef.current = true');
  const stateWrites = indicesOf(calc, 'setPartnerChosen(true)');
  assert(refWrites.length === stateWrites.length && refWrites.length > 0,
    'A-11. every ref write has a setPartnerChosen(true) twin (count equality)',
    `ref writes: ${refWrites.length}, state writes: ${stateWrites.length}`);
  const refLines = refWrites.map((i) => lineOf(calc, i));
  const stateLines = stateWrites.map((i) => lineOf(calc, i));
  for (const rl of refLines) {
    assert(stateLines.some((sl) => Math.abs(sl - rl) <= 3),
      `A-11. the ref write at line ${rl} has its mirror within ±3 lines`,
      'an unmirrored tap site scopes the payload while the note claims league-wide');
  }
  for (const sl of stateLines) {
    assert(refLines.some((rl) => Math.abs(sl - rl) <= 3),
      `A-11. the setPartnerChosen(true) at line ${sl} is adjacent to a ref write`,
      'setPartnerChosen(true) from anywhere else (e.g. the default effect) '
      + 'hides the note while the payload stays unscoped');
  }
  const refInit = calc.match(/const opponentChosenRef = useRef\((.+)\);/);
  const stateInit = calc.match(/const \[partnerChosen, setPartnerChosen\] = useState\((.+)\);/);
  assert(!!refInit && !!stateInit && refInit[1] === stateInit[1],
    'A-11b. the pair\'s initializer expressions are textually identical',
    `ref: ${refInit && refInit[1]} vs state: ${stateInit && stateInit[1]} — `
    + 'drift desynchronizes the pair at mount on every prefill');
}

// ── A-12 — the receive-side Add never opens an empty picker under Anyone
// (sabotage S-12 dead-end-add), and the hint explains the state.
{
  const at = calc.indexOf('addTestID="calc.league-receive-add"');
  assert(at > 0, 'A-12. the receive-side TradeSide mount is locatable');
  const seg = calc.slice(at, at + 900);
  assert(/onAdd=\{\(\) => \{\s*\n?\s*if \(partnerAny\) setTeamPickerOpen\(true\);\s*\n?\s*else setPicker\('receive'\);/.test(seg),
    'A-12. the receive onAdd branches on partnerAny to the team sheet',
    'unconditional setPicker(\'receive\') opens an empty picker — a dead end');
  const hintAt = calc.indexOf('testID="calc.receive-any-hint"');
  assert(hintAt > 0 && /partnerAny \? \(/.test(calc.slice(Math.max(0, hintAt - 200), hintAt)),
    'A-12. calc.receive-any-hint exists with a partnerAny-gated render');
}

// ── A-13 — the member-row tap fully exits Anyone (sabotage S-13
// sticky-anyone: dropping setPartnerAny(false) inverts every honesty
// surface at once — dropdown reads "Anyone", note renders, wire targets
// one team; critic B-3).
{
  const idx = calc.indexOf('setOpponentId(o.user_id)', sheetAt);
  assert(idx > sheetAt && idx < sheetEnd, 'A-13. the sheet member-row tap is locatable');
  const start = calc.lastIndexOf('onPress={() => {', idx);
  const body = start > 0 ? calc.slice(start, calc.indexOf('}}', start)) : '';
  for (const w of ['setPartnerAny(false)', 'opponentChosenRef.current = true',
                   'setPartnerChosen(true)', 'setOpponentId(o.user_id)']) {
    assert(body.includes(w), `A-13. the member-row onPress contains ${w}`,
      'nothing else pins the Anyone → member reset');
  }
}

// ── A-14 — ONLY the browse seeding effect marks its prefill as seeded
// (sabotage S-14 unmarked-seed: the QA-B-1 bug returns; or a tap site
// marked seeded stops scoping a chosen prefill).
{
  const seedAt = trades.indexOf('opponentId: rawTopCard.opponent_user_id');
  assert(seedAt > 0, 'A-14. the browse seeding write is locatable');
  assert(/seeded: true/.test(trades.slice(seedAt, seedAt + 200)),
    'A-14. the seeding effect\'s setCanvasPrefill carries seeded: true',
    'unmarked, a seeded remount counts as chosen — Clear-after-browse silently scopes');
  assert(indicesOf(trades, 'seeded: true').length === 1,
    'A-14. no other prefill site is marked seeded',
    'a tap/handoff/restore marked seeded stops counting a CHOSEN partner as chosen');
  assert(/seededPrefill=\{!!activePrefill\?\.seeded\}/.test(canvas)
      && /const activePrefill = sameLeague\s*\? reconcileCanvasScope\([^;]+\)\s*: null;/.test(canvas),
    'A-14. TradeBuildCanvas forwards the current league prefill marker as seededPrefill');
  assert(/seeded\?: boolean;/.test(canvas),
    'A-14. CanvasPrefill declares the optional seeded field');
}

// ── A-15 — both chosen-ness initializers negate the seed (sabotage S-15
// chosen-seed: revert the ref initializer and every seeded remount counts
// as chosen again). Redundant with A-11b only when one of them holds —
// the pair pins presence AND sameness.
assert(/const opponentChosenRef = useRef\(!!initialOpponentId && !seededPrefill\);/.test(calc),
  'A-15. the ref initializer negates seededPrefill');
assert(/const \[partnerChosen, setPartnerChosen\] = useState\(!!initialOpponentId && !seededPrefill\);/.test(calc),
  'A-15. the partnerChosen initializer negates seededPrefill');

console.log(failures === 0
  ? 'check-any-partner: all assertions passed'
  : `check-any-partner: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
