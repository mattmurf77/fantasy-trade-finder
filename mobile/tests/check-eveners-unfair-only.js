#!/usr/bin/env node
// check-eveners-unfair-only.js — [D-286], two items from the owner's App
// Store screenshot review (2026-11-25).
//
// ITEM 1 — "Recommended to even it" only when the trade needs evening.
// A trade the app itself rates fair ("You win by +463 · an Early 3rd")
// still showed "Recommended to even it — add from your roster": it offered
// to give more away while already ahead, and pushed the value bar off the
// first screen. The rule: the two-sided "Recommended" rows render only when
// the evaluate `verdict` is not 'fair' / 'even' (i.e. 'unfair'); a missing
// or unknown verdict behaves as before (rows render). One predicate,
// `evenersWanted` in components/EvenerRows.tsx, used by BOTH calculators
// (InLeagueCalculator, ConsensusVerdictCard). The #264 half-built "Trade
// options" state (one side empty, no gap) is not gated.
//
// ITEM 2 — nothing in a column-mode (merged calculator) asset row ends in
// "…". TradeSide `compact`: the name wraps (no numberOfLines), the meta row
// (chip · detail · tier) wraps instead of clamping, a pick row prints no
// duplicate "PICK" detail beside the PICK chip, and the PROJ tag sits in
// the chip slot rather than on a line of its own.
//
// WHAT IS EXECUTED: `evenersWanted` (transpiled from the real file), and the
// two calculators' REAL render-condition expressions, lifted out of the
// source and evaluated over fair / even / unfair / missing / one-sided
// payloads. HONEST LABEL (G-035): item 2 is structural only. It proves the
// clamps are gone and the row is allowed to wrap; it cannot prove what Yoga
// lays out at 402pt (that is the simulator check the coordinator runs).
//
// Run: node tests/check-eveners-unfair-only.js
//   (or: npm run test:eveners-unfair-only)

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

const SRC = path.join(__dirname, '..', 'src');
let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}
const read = (rel) => fs.readFileSync(path.join(SRC, rel), 'utf8');
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
const tsToJs = (code) =>
  ts.transpileModule(code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;

const rows = read('components/EvenerRows.tsx');
const calc = read('components/InLeagueCalculator.tsx');
const card = read('components/ConsensusVerdictCard.tsx');
const side = read('components/TradeSide.tsx');

// ── 1. The predicate, executed ───────────────────────────────────────────
console.log('check-eveners-unfair-only: §1 evenersWanted (executed)');
let wanted = null;
{
  const m = rows.match(/export function evenersWanted\([\s\S]*?\n\}/);
  assert(!!m, '1.0 EvenerRows exports evenersWanted');
  if (m) {
    const js = tsToJs(m[0].replace(/^export /, ''));
    wanted = new Function(`${js}; return evenersWanted;`)();
  }
}
if (wanted) {
  assert(wanted('unfair') === true, "1.1 'unfair' ⇒ rows render");
  assert(wanted('fair') === false, "1.2 'fair' ⇒ rows hidden");
  assert(wanted('even') === false, "1.3 'even' ⇒ rows hidden");
  assert(wanted(null) === true && wanted(undefined) === true,
    '1.4 missing verdict (null / undefined) ⇒ rows render, as before (fail safe)');
  assert(wanted('something-new') === true, '1.5 an unknown verdict ⇒ rows render (fail safe)');
}

// ── 2. The two calculators' real render conditions, executed ─────────────
console.log('§2 render conditions (executed from source)');
function liftCondition(src, label) {
  // The JSX expression `{<condition> ? (` that opens the <EvenerRows mount:
  // the last line-leading `{` (not a `{/*` comment) before its `? (`.
  const at = src.indexOf('<EvenerRows');
  const q = at < 0 ? -1 : src.lastIndexOf('? (', at);
  let start = -1;
  for (const m of src.slice(0, q).matchAll(/\n[ \t]*\{(?!\/\*)/g)) start = m.index + m[0].length;
  if (q < 0 || start < 0) {
    assert(false, `2.0 ${label}: could not lift the EvenerRows render condition`);
    return null;
  }
  return src.slice(start, q).trim();
}
const ev = (o) => ({ eveners: [{ id: 'x' }], per_player: [], ...o });
const twoSided = (verdict) => ev({ verdict, gap: { add_to: 'give', value: 400 }, favors: 'receive' });
const oneSided = ev({ verdict: null, gap: null, favors: null });
{
  const cond = liftCondition(calc, 'InLeagueCalculator');
  assert(!!cond && /evenersWanted\(ev\.verdict\)/.test(cond),
    '2.1 InLeagueCalculator gates the mount on evenersWanted(ev.verdict)', cond);
  if (cond && wanted) {
    const f = new Function('anySide', 'ev', 'evenerAddTo', 'evenersWanted', `return !!(${cond});`);
    const run = (e, addTo) => f(true, e, addTo, wanted);
    assert(run(twoSided('unfair'), 'give') === true, '2.2 in-league: unfair two-sided ⇒ "Recommended" rows render');
    assert(run(twoSided('fair'), 'give') === false, '2.3 in-league: FAIR two-sided ⇒ hidden (the screenshot case)');
    assert(run(twoSided('even'), 'receive') === false, '2.4 in-league: even two-sided ⇒ hidden');
    assert(run(twoSided(undefined), 'give') === true && run(twoSided(null), 'give') === true,
      '2.5 in-league: two-sided with the verdict missing ⇒ renders, as before');
    assert(run(oneSided, 'receive') === true,
      '2.6 in-league: the #264 half-built "Trade options" state (no gap, verdict null) still renders');
    assert(f(false, twoSided('unfair'), 'give', wanted) === false
      && run(ev({ verdict: 'unfair', gap: { add_to: 'give' }, eveners: [] }), 'give') === false
      && run(twoSided('unfair'), null) === false,
      '2.7 in-league: the pre-existing conditions (anySide, non-empty eveners, a target side) still hold');
  }
  // The half-built labels survive in the same mount.
  const mountAt = calc.indexOf('<EvenerRows');
  const mount = calc.slice(mountAt, mountAt + 1400);
  assert(/'Trade options — from your roster'/.test(mount)
    && /Trade options — from @\$\{opponent\?\.username \?\? 'them'\}'s roster/.test(mount),
    '2.8 in-league: both #264 "Trade options" titles are still in the mount');
  assert(/'Recommended to even it — add from your roster'/.test(mount)
    && /Recommended to even it — ask @/.test(mount),
    '2.9 in-league: both "Recommended to even it" titles are unchanged');
  assert((calc.match(/<EvenerRows/g) || []).length === 1,
    '2.10 in-league: still ONE EvenerRows block (#264: one block, two labels)');
}
{
  const cond = liftCondition(card, 'ConsensusVerdictCard');
  assert(!!cond && /evenersWanted\(evaluation\.verdict\)/.test(cond),
    '2.11 ConsensusVerdictCard (Real values) gates on the SAME evenersWanted', cond);
  if (cond && wanted) {
    const f = new Function('onAddEvener', 'evaluation', 'evenersWanted', `return !!(${cond});`);
    const add = () => {};
    assert(f(add, twoSided('unfair'), wanted) === true, '2.12 Real values: unfair ⇒ renders');
    assert(f(add, twoSided('fair'), wanted) === false && f(add, twoSided('even'), wanted) === false,
      '2.13 Real values: fair / even ⇒ hidden');
    assert(f(add, twoSided(undefined), wanted) === true, '2.14 Real values: missing verdict ⇒ renders, as before');
    assert(f(undefined, twoSided('unfair'), wanted) === false,
      '2.15 Real values: no onAddEvener host ⇒ nothing, as before');
  }
}
{
  // No calculator re-implements the rule inline (that is how the two drift).
  for (const [rel, s] of [['InLeagueCalculator', calc], ['ConsensusVerdictCard', card]]) {
    assert(/import EvenerRows, \{ evenersWanted \} from '\.\/EvenerRows';/.test(s),
      `2.16 ${rel} imports evenersWanted from EvenerRows`);
  }
}

// ── 3. TradeSide column-mode rows never ellipsize (structural, G-035) ────
console.log('§3 TradeSide column-mode rows (structural only)');
{
  const code = strip(side);
  assert(!/numberOfLines=\{1\}/.test(code),
    '3.1 no bare numberOfLines={1} in TradeSide (the compact name wraps)');
  assert(!/ellipsizeMode/.test(code), '3.2 no ellipsizeMode anywhere in TradeSide');
  const clamps = code.match(/numberOfLines=\{[^}]*\}/g) || [];
  assert(clamps.length === 1 && /numberOfLines=\{compact \? 1 : undefined\}>\{teamName\}/.test(code),
    '3.3 the only clamp left is the compact team-name header (not an asset row)', clamps.join(', '));
  assert(/compactName: \{[^}]*\}/.test(code) && !/compactName: \{[^}]*numberOfLines/.test(code),
    '3.4 the compact name style carries no clamp');
  assert(/compactMetaLine: \{[^}]*flexWrap: 'wrap'[^}]*\}/.test(code),
    "3.5 the compact meta row is allowed to wrap (flexWrap: 'wrap')");
  assert(/\{compact && \(p\.pick \|\| p\.pos === 'PICK'\) \? null : \(/.test(code),
    '3.6 a column-mode pick row prints no detail text next to its PICK chip');
  const slotAt = code.indexOf('<View style={styles.compactChipSlot}>');
  const slot = slotAt > -1 ? code.slice(slotAt, slotAt + 220) : '';
  assert(/<PositionChip position=\{p\.pos\} size="sm" \/>\s*\{proj \? <ProjectedPickTag short \/> : null\}/.test(slot),
    '3.7 the column-mode PROJ tag rides in the chip slot beside the PICK chip');
  assert(/compactChipSlot: \{[^}]*flexDirection: 'row'[^}]*\}/.test(code),
    '3.8 the chip slot lays chip + tag out in a row');
  // The stacked page is unchanged: tag on its own line, full label.
  assert(/\{proj \? <ProjectedPickTag \/> : null\}/.test(code),
    '3.9 the stacked page keeps its PROJECTED tag line');
  for (const id of ['calc.member-entered.${p.id}']) {
    assert(side.includes(id), `3.10 testID ${id} kept`);
  }
}

if (failures) {
  console.error(`\ncheck-eveners-unfair-only: ${failures} FAILED`);
  process.exit(1);
}
console.log('\ncheck-eveners-unfair-only: all passed');
