#!/usr/bin/env node
// check-projected-pick-tag.js — the PROJECTED tag on projected-slot picks.
//
// WHY THIS EXISTS. The server now prices next season's first-round picks by
// the original team's projected draft slot (docs/plans/pick-value-projected-
// slot/). The operator asked that every place a pick's name prints say so:
// the slot name ("2027 1.02") with a flare PROJECTED tag, so a user can see
// why a "2027 1st" is worth what it is. The wire carries `proj_slot` +
// `proj_name` beside the ordinary name. Three ways this goes wrong quietly,
// each invisible on an old server and in a passing typecheck:
//   - a tag with no slot name (or the slot name with no tag) — the screen
//     makes a claim it can't back;
//   - the app parsing or composing the strings instead of printing
//     `proj_name` verbatim;
//   - an old server's pick (neither field) rendering differently from today.
// There is no simulator (D-056), so this guard is the evidence.
//
// WHAT IS EXECUTED: `utils/projectedPick.ts` (the one validator) over good,
// malformed-slot, one-field, over-long and non-string inputs; the
// `ProjectedPickTag` component under a stub React (label, flare token,
// colorText); InLeagueCalculator's own two spread expressions that copy the
// fields onto a calculator asset.
// HONEST LABEL (G-035): everything about the SURFACES (PlayerCard, TradeCard,
// TradeSide, PlayerPickerModal, LeagueSummaryScreen) is a structural check —
// it proves the exact wirings are present (tag only inside a `proj ?`
// consequent, the printed name is `proj.name`, the a11y clause is wired, the
// old path is the old expression), not runtime rendering.
//
// Run: node tests/check-projected-pick-tag.js
//   (or: npm run test:projected-pick-tag)

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
function load(rel, shims) {
  const js = ts.transpileModule(read(rel), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2019,
      jsx: ts.JsxEmit.React,
    },
  }).outputText;
  const m = { exports: {} };
  new Function('module', 'exports', 'require', js)(m, m.exports, (name) => {
    if (shims && name in shims) return shims[name];
    throw new Error(`${rel}: unexpected require ${name}`);
  });
  return m.exports;
}
const count = (s, needle) => s.split(needle).length - 1;

// ── 1. The validator, executed ──────────────────────────────────────────
console.log('check-projected-pick-tag: §1 utils/projectedPick (executed)');
let U = null;
try {
  U = load('utils/projectedPick.ts', {});
} catch (e) {
  assert(false, '1.0 utils/projectedPick.ts loads with zero runtime imports', e.message);
}
if (U) {
  const P = U.projectedPick;
  const good = { name: '2027 1.02 (from dondags) · projected', proj_slot: '1.02', proj_name: '2027 1.02 (from dondags)' };
  const r = P(good);
  assert(r && r.slot === '1.02' && r.name === '2027 1.02 (from dondags)',
    '1.1 a good pair returns {slot, name} with proj_name VERBATIM', JSON.stringify(r));
  for (const bad of ['1.2', '10.02', '1.023', '1.02 ', ' 1.02', '1-02', 'a.02', '']) {
    assert(P({ proj_slot: bad, proj_name: '2027 1.02' }) === null,
      `1.2 malformed slot ${JSON.stringify(bad)} ⇒ null (no tag, no slot name)`);
  }
  assert(P({ proj_slot: 102, proj_name: '2027 1.02' }) === null, '1.3 a numeric slot ⇒ null');
  assert(P({ proj_slot: '1.02', proj_name: 2027 }) === null, '1.3b a non-string name ⇒ null');
  assert(P({ proj_slot: '1.02' }) === null, '1.4 slot without name ⇒ null');
  assert(P({ proj_name: '2027 1.02' }) === null, '1.4b name without slot ⇒ null');
  assert(P({ proj_slot: '1.02', proj_name: 'x'.repeat(61) }) === null, '1.5 a 61-char name ⇒ null');
  assert(P({ proj_slot: '1.02', proj_name: 'x'.repeat(60) }) !== null, '1.5b a 60-char name is accepted');
  assert(P({ proj_slot: '1.02', proj_name: '' }) === null, '1.5c an empty name ⇒ null');
  assert(P(null) === null && P(undefined) === null && P('1.02') === null, '1.6 non-objects ⇒ null');
  assert(P({ name: '2027 1st', position: 'PICK' }) === null, '1.7 an old-server pick (neither field) ⇒ null');
  assert(U.pickDisplayName({ name: 'x' }, '2027 1st') === '2027 1st'
    && U.pickDisplayName(good, 'ignored') === '2027 1.02 (from dondags)',
    '1.8 pickDisplayName: ordinary name untouched when absent, proj_name when valid');
  assert(U.projectedPickA11y({ slot: '1.02', name: 'n' }) === 'projected draft slot 1.02',
    '1.9 the a11y clause reads "projected draft slot 1.02"');
  assert(U.PROJECTED_TAG_LABEL === 'PROJECTED' && U.PROJECTED_TAG_LABEL_SHORT === 'PROJ',
    '1.10 tag labels are PROJECTED / PROJ (upper case, like the other badges)');
}

// ── 2. The tag component, executed ──────────────────────────────────────
console.log('§2 ProjectedPickTag (executed under a stub React)');
const theme = read('theme/chalkline.ts');
const flareHex = (theme.match(/export const flare = \{[^}]*base:\s*'(#[0-9A-Fa-f]{6})'/) || [])[1];
const iceHex = (theme.match(/export const ice = \{[^}]*base:\s*'(#[0-9A-Fa-f]{6})'/) || [])[1];
assert(!!flareHex && !!iceHex, '2.0 flare.base and ice.base read from theme/chalkline.ts', `${flareHex} ${iceHex}`);
const tagSrc = read('components/ProjectedPickTag.tsx');
let Tag = null;
try {
  Tag = load('components/ProjectedPickTag.tsx', {
    react: (() => {
      const R = { createElement: (type, props) => ({ type, props: props || {} }) };
      return { ...R, default: R, __esModule: true };
    })(),
    './chalkline': { Badge: 'Badge' },
    '../theme/chalkline': { flare: { base: flareHex } },
    '../utils/projectedPick': U,
  }).default;
} catch (e) {
  assert(false, '2.1 ProjectedPickTag loads', e.message);
}
if (Tag) {
  let full = { props: {} };
  let short = { props: {} };
  try {
    full = Tag({});
    short = Tag({ short: true });
  } catch (e) {
    assert(false, '2.1 ProjectedPickTag renders', e.message);
  }
  assert(full.type === 'Badge' && full.props.label === 'PROJECTED',
    '2.1 default renders the chalkline Badge labelled PROJECTED', JSON.stringify(full));
  assert(short.props.label === 'PROJ', '2.2 short renders PROJ');
  assert(full.props.color === flareHex && full.props.colorText === true,
    '2.3 border AND text are flare.base (informational highlight, ADR-005)');
  assert(full.props.color !== iceHex, '2.4 never ice (ice = actions)');
}
assert(!/\bice\b|\bsemantic\b|#[0-9A-Fa-f]{6}/.test(tagSrc.replace(/\/\/.*$/gm, '')),
  '2.5 the tag file names no ice / semantic token and no hex literal');

// ── 3. Surfaces: the tag only inside a `proj ?` consequent ──────────────
console.log('§3 surfaces (structural, G-035)');
const SURFACES = {
  'components/PlayerCard.tsx': 2,          // dense + classic branch
  'components/TradeSide.tsx': 1,
  'components/PlayerPickerModal.tsx': 1,
  'screens/LeagueSummaryScreen.tsx': 1,
};
// Innermost unclosed `{` before `idx`, skipping over balanced (), {}, [].
function enclosingBrace(src, idx) {
  let depth = 0;
  for (let i = idx - 1; i >= 0; i--) {
    const c = src[i];
    if (c === '}' || c === ')' || c === ']') depth++;
    else if (c === '{' || c === '(' || c === '[') {
      if (depth === 0) {
        if (c === '{') return i;
      } else depth--;
    }
  }
  return -1;
}
// The text between the container's `{` and the tag must be `proj ? …` with
// no depth-0 `:` (i.e. the tag sits in the consequent, never the else).
function tagGuarded(src, idx) {
  const open = enclosingBrace(src, idx);
  if (open < 0) return false;
  const head = src.slice(open + 1, idx);
  if (!/^\s*proj\s*\?/.test(head)) return false;
  let depth = 0;
  const afterQ = head.slice(head.indexOf('?') + 1);
  for (const c of afterQ) {
    if ('({['.includes(c)) depth++;
    else if (')}]'.includes(c)) depth--;
    else if (c === ':' && depth === 0) return false;
  }
  return true;
}
for (const [rel, n] of Object.entries(SURFACES)) {
  const s = read(rel);
  assert(/import \{ projectedPick, projectedPickA11y \} from '\.\.\/utils\/projectedPick';/.test(s),
    `3.1 ${rel} validates through utils/projectedPick`);
  assert(/const proj = projectedPick\(\w+\);/.test(s), `3.2 ${rel} derives \`proj\` from projectedPick(asset)`);
  const idxs = [];
  for (let i = s.indexOf('<ProjectedPickTag'); i >= 0; i = s.indexOf('<ProjectedPickTag', i + 1)) idxs.push(i);
  assert(idxs.length === n, `3.3 ${rel} mounts the tag ${n}×`, `found ${idxs.length}`);
  assert(idxs.length > 0 && idxs.every((i) => tagGuarded(s, i)),
    `3.4 ${rel}: every tag sits in the consequent of \`proj ? …\``);
  assert(s.includes('projectedPickA11y(proj)'), `3.5 ${rel} speaks "projected draft slot X"`);
  assert(!/\bproj_slot\b|\bproj_name\b/.test(s.replace(/\/\/.*$/gm, ''))
      && !/proj\.(name|slot)\s*\.\s*\w+\s*\(/.test(s)
      // the server's name suffix " · projected" (string-final); the playoff
      // copy "· projected 3rd of 12" on LeagueSummary is unrelated.
      && !/·\s*projected['"`]/i.test(s),
    `3.6 ${rel}: never reads the raw fields, never parses proj.name/slot, never composes "· projected"`);
}

// ── 4. The printed name is proj_name verbatim; absent ⇒ today's name ────
console.log('§4 printed name (structural, G-035)');
{
  const s = read('components/PlayerCard.tsx');
  assert(s.includes('const displayName = proj ? proj.name : player.name;'),
    '4.1 PlayerCard: displayName = proj ? proj.name : player.name');
  assert(count(s, '{displayName}') === 2 && !/>\s*\{player\.name\}\s*</.test(s),
    '4.2 PlayerCard: both name Texts print {displayName}; no bare {player.name} child left');
  assert(s.includes('numberOfLines={proj && compact ? 2 : 1}'),
    '4.2b PlayerCard: only a projected pick in a compact row gets 2 lines (slot never ellipsized); every other row keeps 1');
  assert(/\[\s*displayName,/.test(s) && s.includes('proj ? projectedPickA11y(proj) : null,'),
    '4.3 PlayerCard composed a11y: leads with displayName, clause is null (filtered) when absent');
}
{
  const s = read('components/TradeCard.tsx');
  assert(/const proj = projectedPick\(p\);[\s\S]{0,200}accessibilityLabel: \[\s*proj \? proj\.name : p\.name,/.test(s),
    '4.4 TradeCard rowA11y: the row speaks the printed name');
  assert(s.includes('proj ? projectedPickA11y(proj) : null,'),
    '4.5 TradeCard rowA11y: clause null (filtered) when absent');
}
{
  const s = read('components/TradeSide.tsx');
  assert(count(s, '{proj ? proj.name : p.name}') === 2 && !/>\s*\{p\.name\}\s*</.test(s),
    '4.6 TradeSide: both name Texts (column + stacked) print proj ? proj.name : p.name');
  assert(count(s, 'accessibilityLabel={proj ? `${proj.name}, ${projectedPickA11y(proj)}` : undefined}') === 2,
    '4.7 TradeSide: a11y label only when proj, undefined (default) otherwise');
}
{
  const s = read('components/PlayerPickerModal.tsx');
  assert(s.includes('<Text style={type.title}>{proj ? proj.name : item.name}</Text>'),
    '4.8 PlayerPickerModal: row prints proj ? proj.name : item.name');
  assert(s.includes("${proj ? `, ${projectedPickA11y(proj)}` : ''}"),
    "4.9 PlayerPickerModal: a11y clause is '' when absent (label string unchanged)");
}
{
  const s = read('screens/LeagueSummaryScreen.tsx');
  assert(/\{proj \? \([\s\S]{0,600}\{proj\.name\}[\s\S]{0,80}<ProjectedPickTag \/>[\s\S]{0,60}\) : \(\s*<Text style=\{type\.title\} numberOfLines=\{1\}>\{p\.label\}<\/Text>\s*\)\}/.test(s),
    '4.10 LeagueSummary draft capital: proj branch prints proj.name + tag; else is the original {p.label} Text');
}

// ── 5. Calculator asset carries the fields only when sent (executed) ────
console.log('§5 InLeagueCalculator pick → CalcPlayer');
{
  const s = read('components/InLeagueCalculator.tsx');
  const a = s.match(/\.\.\.\(p\.proj_slot !== undefined \? \{ proj_slot: p\.proj_slot \} : \{\}\),/);
  const b = s.match(/\.\.\.\(p\.proj_name !== undefined \? \{ proj_name: p\.proj_name \} : \{\}\),/);
  assert(!!a && !!b, '5.1 the two conditional spreads are present in pickById');
  if (a && b) {
    // eslint-disable-next-line no-new-func
    const build = new Function('p', `return { id: p.pick_id, name: p.label, ${a[0]} ${b[0]} };`);
    const old = build({ pick_id: 'x', label: '2027 1st' });
    assert(JSON.stringify(Object.keys(old)) === '["id","name"]',
      '5.2 old server: no proj keys are added to the asset (executed)', JSON.stringify(old));
    const neu = build({ pick_id: 'x', label: 'L', proj_slot: '1.02', proj_name: '2027 1.02' });
    assert(neu.proj_slot === '1.02' && neu.proj_name === '2027 1.02',
      '5.3 new server: both copied verbatim (executed)');
    assert(U && U.projectedPick(neu) && !U.projectedPick(old),
      '5.4 the copied asset validates exactly like the wire row');
  }
}

console.log(failures === 0 ? '\ncheck-projected-pick-tag: all passed' : `\ncheck-projected-pick-tag: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
