#!/usr/bin/env node
// Win-now season signal, WI-7: the card's season line, label tags and
// conflict sentence (docs/plans/win-now-season-signal/lld.md §5.2-§5.3,
// prd.md §3, §5.3, §6 rule 3; build-plan.md WI-7).
//
// WHY THIS EXISTS. The server composes a `season_block` (template season-1,
// backend/trade_narrative.py season_block) beside the fit block: one line
// ("Season +2.1 pts/wk · Dynasty cost 3%"), a short tag per labelled asset
// ("Win-now piece" / "Cornerstone" / "Rebuild piece") and, when a saved plan
// conflicts, one sentence. The honesty rules are the server's: every word is
// its template, printed verbatim, and an older server (no block) must leave
// the card exactly as it was. D-056 retired the simulator, so this guard is
// the automated evidence.
//
// What is pinned:
//   1. Wire type: `SeasonBlock` (v 'season-1', every field optional but v)
//      and `season_block?: SeasonBlock` on TradeCard.
//   2. normalizeSeasonBlock, transpiled and EXECUTED: a valid block passes
//      verbatim; an unknown / missing `v` drops the whole block; each
//      malformed or over-long piece is dropped on its own (never truncated);
//      labels are deduped by id and capped at 12; nothing left => undefined.
//   3. normalizeTradeCard reads `raw.season_block` through it and spreads the
//      key only when it returned a block.
//   4. The season line and conflict sentence (the card's own JSX, extracted
//      and EXECUTED): printed verbatim, one line / two lines, their testIDs,
//      and nothing rendered for a block without them or with no block.
//   5. seasonLabelFor + seasonTag (EXECUTED): an asset with a label gets a
//      tag with the label's text and testID trade-card.season-label.<id>;
//      an asset without one, or a card without a block, gets nothing.
//   6. Placement: the season line and conflict sit in the fit block after the
//      You team row; both player columns pass seasonTag(p) as PlayerCard's
//      belowNameSlot, which PlayerCard renders once, directly under the name.
//      The tag is part of the row's VoiceOver label (rowA11y).
//   7. Gate: the block is read as
//      `fitFirstEnabled && !data.edited ? data.season_block : undefined`, and
//      every season read in the card goes through that gated value.
//   8. No client-side composition: no season copy literal in the card, the
//      player card or the normaliser; the card never reads the block's
//      numbers, `label`, `starts_for_you` or `conflict.code`.
//   9. Neutral styles: the season elements reuse the fit block's fitLead /
//      fitTag styles (already pinned neutral by check-fit-first-copy 6); no
//      inline colour.
//  10. A card without a season block renders as before: check-fit-first-copy
//      passes UNMODIFIED (run here as a child process).
//  11. testID lint: the templated label id is allow-listed; the npm script
//      exists.
//
// HONEST LABEL (G-035): 4 and 5 execute the card's own JSX fragments against
// a React stand-in, not a mounted TradeCard; 6, 7 and 9 are structural
// (placement and wiring presence). The 375pt width claims are arithmetic in
// the build report, not measured on a device: the TestFlight checklist is the
// runtime evidence.
//
// Run: node tests/check-season-signal.js   (or: npm run test:season-signal)

'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const CARD = path.join(ROOT, 'src/components/TradeCard.tsx');
const PLAYER = path.join(ROOT, 'src/components/PlayerCard.tsx');
const TYPES = path.join(ROOT, 'src/shared/types.ts');
const API = path.join(ROOT, 'src/api/trades.ts');
const PKG = path.join(ROOT, 'package.json');
const ALLOW = path.join(ROOT, 'scripts/testid-lint-allow.txt');

const failures = [];
const checks = [];
function ok(name) { checks.push(name); }
function fail(name, detail) { failures.push(`${name}\n      ${detail}`); }
function read(p) {
  if (!fs.existsSync(p)) { fail('file exists', `missing: ${path.relative(ROOT, p)}`); return ''; }
  return fs.readFileSync(p, 'utf8');
}
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\{\/\*[\s\S]*?\*\/\}/g, '');
}
function grabFn(src, header) {
  const at = src.indexOf(header);
  return at < 0 ? '' : src.slice(at, at + src.slice(at).indexOf('\n}\n') + 2);
}

const card = stripComments(read(CARD));
const player = stripComments(read(PLAYER));
const types = stripComments(read(TYPES));
const apiRaw = read(API);
const api = stripComments(apiRaw);

let ts = null;
try { ts = require('typescript'); } catch (e) { /* reported below */ }
function run(src, names, scope) {
  const js = ts.transpileModule(src, {
    compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.None },
  }).outputText;
  const keys = Object.keys(scope);
  // eslint-disable-next-line no-new-func
  return new Function(...keys, `${js}\nreturn [${names.join(', ')}];`)(...keys.map((k) => scope[k]));
}
const h = (type, props, ...children) => ({ type, props: props || {}, children: children.flat() });
const React = { createElement: h, Fragment: 'Fragment' };
const textOf = (n) => (n == null || typeof n === 'boolean' ? '' : typeof n !== 'object' ? String(n)
  : n.children.map(textOf).join(''));
const nodes = (n) => (n == null || typeof n !== 'object' ? [] : [n, ...n.children.flatMap(nodes)]);
const J = (x) => JSON.stringify(x);
// Theme names a sabotaged fragment might reach for, so it renders and the
// style check (9) is what reports it, not a ReferenceError.
const TOKENS = { flare: { base: 'flare' }, ice: { base: 'ice' }, semantic: { neg: 'neg' }, chalk: { dim: 'dim', base: 'base' } };

// 1. Wire type.
{
  const name = '1. wire type: SeasonBlock (v season-1) and TradeCard.season_block?';
  const block = types.match(/export interface SeasonBlock \{([\s\S]*?)\n\}/);
  const label = types.match(/export interface SeasonLabel \{([\s\S]*?)\n\}/);
  if (!block || !/v: 'season-1';/.test(block[1])) fail(name, "SeasonBlock must declare `v: 'season-1'`");
  else if (!['line?: string;', 'labels?: SeasonLabel[];', 'conflict?: { code: string; text: string };']
    .every((f) => block[1].includes(f))) fail(name, 'SeasonBlock needs optional line, labels and conflict');
  else if (!label || !['id: string;', 'text: string;', 'starts_for_you: boolean;'].every((f) => label[1].includes(f))) {
    fail(name, 'SeasonLabel needs id, text, starts_for_you');
  } else if (!/season_block\?:\s*SeasonBlock;/.test(types)) fail(name, 'TradeCard needs `season_block?: SeasonBlock;`');
  else ok(name);
}

// 2. Normaliser, executed.
const VALID = {
  v: 'season-1',
  line: 'Season -12.3 pts/wk · Dynasty cost 12%',
  season_pts_week: -12.3, dynasty_pct: 12, dynasty_dir: 'cost',
  weeks: 14, as_of: '2026-09-01',
  labels: [
    { id: '4866', label: 'win_now', text: 'Win-now piece', starts_for_you: true },
    { id: '9493', label: 'rebuild', text: 'Rebuild piece', starts_for_you: false },
  ],
  conflict: { code: 'conflict.board.above', text: 'You rank Bucky Irving above market, but this moves away from All-in' },
};
const clone = (x) => JSON.parse(JSON.stringify(x));
let norm = null;
{
  const name = '2. normalizeSeasonBlock: valid passes verbatim; unknown v ignored; each malformed piece dropped; caps';
  const consts = (apiRaw.match(/^export const SEASON_[A-Z_]+ = \d+;$/gm) || []).map((l) => l.replace(/^export /, '')).join('\n');
  const fn = grabFn(apiRaw, 'export function normalizeSeasonBlock(').replace(/^export /, '');
  if (!ts) fail(name, 'typescript is not installed (npm ci)');
  else if (!fn) fail(name, 'no export function normalizeSeasonBlock in src/api/trades.ts');
  else {
    try { [norm] = run(`${consts}\n${fn}`, ['normalizeSeasonBlock'], {}); } catch (e) { fail(name, `could not run: ${e.message}`); }
  }
  if (norm) {
    const wrong = [];
    const t = (label, got, want) => { if (J(got) !== J(want)) wrong.push(`${label}: got ${J(got)}`); };
    t('valid block', norm(clone(VALID)), VALID);
    t('as_of null kept', norm({ ...clone(VALID), as_of: null }).as_of, null);
    for (const v of ['season-2', 'fit-2', undefined, 1]) t(`v=${v}`, norm({ ...clone(VALID), v }), undefined);
    for (const raw of [undefined, null, 'season-1', [], 7]) t(`raw=${J(raw)}`, norm(raw), undefined);
    // Each malformed piece on its own: the rest survive.
    const drop = (label, edit, key) => {
      const raw = clone(VALID); edit(raw);
      const got = norm(raw);
      if (!got) { wrong.push(`${label}: whole block dropped`); return; }
      if (key in got) wrong.push(`${label}: ${key} kept as ${J(got[key])}`);
      const rest = Object.keys(VALID).filter((k) => k !== key);
      const lost = rest.filter((k) => J(got[k]) !== J(VALID[k]));
      if (lost.length) wrong.push(`${label}: also lost ${lost.join(', ')}`);
    };
    drop('line number', (r) => { r.line = 2.1; }, 'line');
    drop('line empty', (r) => { r.line = ''; }, 'line');
    drop('line over 80', (r) => { r.line = 'S'.repeat(81); }, 'line');
    drop('pts NaN', (r) => { r.season_pts_week = NaN; }, 'season_pts_week');
    drop('pts string', (r) => { r.season_pts_week = '2.1'; }, 'season_pts_week');
    drop('pct negative', (r) => { r.dynasty_pct = -3; }, 'dynasty_pct');
    drop('pct Infinity', (r) => { r.dynasty_pct = Infinity; }, 'dynasty_pct');
    drop('dir unknown', (r) => { r.dynasty_dir = 'loss'; }, 'dynasty_dir');
    drop('weeks float', (r) => { r.weeks = 1.5; }, 'weeks');
    drop('weeks negative', (r) => { r.weeks = -1; }, 'weeks');
    drop('as_of not a date', (r) => { r.as_of = 'yesterday'; }, 'as_of');
    drop('labels not an array', (r) => { r.labels = { id: '1' }; }, 'labels');
    drop('labels all malformed', (r) => { r.labels = [{ id: '', label: 'x', text: 'y' }, null]; }, 'labels');
    drop('conflict no code', (r) => { delete r.conflict.code; }, 'conflict');
    drop('conflict text empty', (r) => { r.conflict.text = ''; }, 'conflict');
    drop('conflict text over 200', (r) => { r.conflict.text = 'x'.repeat(201); }, 'conflict');
    drop('conflict null', (r) => { r.conflict = null; }, 'conflict');
    // One bad label among good ones: only it goes.
    const lab = (edit) => { const r = clone(VALID); edit(r.labels); return (norm(r) || {}).labels; };
    t('label id missing', lab((l) => { delete l[0].id; }), [VALID.labels[1]]);
    t('label id not a string', lab((l) => { l[0].id = 4866; }), [VALID.labels[1]]);
    t('label text over 24', lab((l) => { l[0].text = 'W'.repeat(25); }), [VALID.labels[1]]);
    t('label text missing', lab((l) => { delete l[0].text; }), [VALID.labels[1]]);
    t('label kind missing', lab((l) => { delete l[0].label; }), [VALID.labels[1]]);
    t('label duplicate id', lab((l) => { l[1].id = '4866'; }), [VALID.labels[0]]);
    t('label null entry', lab((l) => { l.unshift(null); }), VALID.labels);
    t('starts_for_you not boolean', lab((l) => { l[0].starts_for_you = 'yes'; }),
      [{ ...VALID.labels[0], starts_for_you: false }, VALID.labels[1]]);
    t('extra label key dropped', lab((l) => { l[0].colour = 'red'; }), VALID.labels);
    const many = Array.from({ length: 20 }, (_, i) => ({ id: `p${i}`, label: 'rebuild', text: 'Rebuild piece', starts_for_you: false }));
    t('labels capped at 12', (norm({ v: 'season-1', labels: many }) || {}).labels, many.slice(0, 12));
    // Nothing to show: undefined (the server never sends an empty block).
    t('only numbers', norm({ v: 'season-1', season_pts_week: 2.1, weeks: 3, as_of: null }), undefined);
    t('everything malformed', norm({ v: 'season-1', line: 3, labels: [{}], conflict: { text: 'x' } }), undefined);
    t('conflict alone', norm({ v: 'season-1', conflict: VALID.conflict }), { v: 'season-1', conflict: VALID.conflict });
    if (wrong.length) fail(name, wrong.join('\n      '));
    else ok(name);
  }
}

// 3. Wiring into normalizeTradeCard.
{
  const name = '3. normalizeTradeCard reads raw.season_block through the normaliser; key only when present';
  const body = grabFn(api, 'export function normalizeTradeCard(');
  if (!/const seasonBlock = normalizeSeasonBlock\(raw\?\.season_block\);/.test(body)) {
    fail(name, 'normalizeTradeCard must call normalizeSeasonBlock(raw?.season_block)');
  } else if (!/\.\.\.\(seasonBlock \? \{ season_block: seasonBlock \} : \{\}\)/.test(body)) {
    fail(name, 'season_block must be spread in only when the normaliser returned a block');
  } else if ((api.match(/season_block/g) || []).length !== 2) {
    fail(name, 'season_block must be read once and written once in trades.ts');
  } else ok(name);
}

// The fit block (for placement) and the season JSX inside it.
const BLOCK_ID = 'testID="trade-card.fit-block"';
const blockAt = card.indexOf(BLOCK_ID);
const blockEnd = card.indexOf('\n      ) : null}\n', blockAt);
const fitBlock = blockAt >= 0 && blockEnd > blockAt ? card.slice(blockAt, blockEnd) : '';
const lineStart = card.indexOf('{seasonShown?.line ? (');
const conflictId = card.indexOf('testID="trade-card.season-conflict"');
const seasonJsx = lineStart >= 0 && conflictId > lineStart
  ? card.slice(lineStart, card.indexOf(') : null}', conflictId) + ') : null}'.length) : '';

// 4. Season line + conflict, executed.
{
  const name = '4. season line (1 line) and conflict (2 lines) render the server text verbatim, only when present';
  if (!ts) fail(name, 'typescript is not installed (npm ci)');
  else if (!seasonJsx) fail(name, 'no `{seasonShown?.line ? (` … trade-card.season-conflict fragment in TradeCard.tsx');
  else {
    let Rows;
    try {
      [Rows] = run(`function Rows(seasonShown) { return (<>${seasonJsx}</>); }`, ['Rows'],
        { React, ChalklineText: 'ChalklineText', styles: { fitLead: { lead: 1 }, fitTag: { tag: 1 } }, ...TOKENS });
    } catch (e) { fail(name, `could not run the fragment: ${e.message}`); }
    if (Rows) {
      const wrong = [];
      const render = (b) => { try { return Rows(b); } catch (e) { wrong.push(`threw: ${e.message}`); return null; } };
      const texts = (b) => nodes(render(b)).filter((n) => n.type === 'ChalklineText')
        .map((n) => ({ id: n.props.testID, lines: n.props.numberOfLines, text: textOf(n) }));
      const want = [
        { id: 'trade-card.season-line', lines: 1, text: VALID.line },
        { id: 'trade-card.season-conflict', lines: 2, text: VALID.conflict.text },
      ];
      if (J(texts(VALID)) !== J(want)) wrong.push(`full block: ${J(texts(VALID))}`);
      const { conflict, ...noConflict } = VALID;
      if (J(texts(noConflict)) !== J([want[0]])) wrong.push(`no conflict: ${J(texts(noConflict))}`);
      const { line, ...noLine } = VALID;
      if (J(texts(noLine)) !== J([want[1]])) wrong.push(`no line: ${J(texts(noLine))}`);
      if (texts({ v: 'season-1', labels: VALID.labels }).length) wrong.push('labels-only block rendered a line');
      if (texts(undefined).length) wrong.push('no block rendered something');
      if (wrong.length) fail(name, wrong.join('; '));
      else ok(name);
    }
  }
}

// 5. Label tags, executed.
{
  const name = '5. seasonLabelFor / seasonTag: a labelled asset gets its server text and id; others get nothing';
  const fnSrc = grabFn(card, 'export function seasonLabelFor(').replace(/^export /, '');
  const tagAt = card.indexOf('const seasonTag = (p: Player) => {');
  const tagSrc = tagAt < 0 ? '' : card.slice(tagAt, card.indexOf('\n  };\n', tagAt) + 5);
  if (!ts) fail(name, 'typescript is not installed (npm ci)');
  else if (!fnSrc || !tagSrc) fail(name, 'need `export function seasonLabelFor(` and `const seasonTag = (p: Player) => {` in TradeCard.tsx');
  else {
    let make;
    try {
      [make] = run(`${fnSrc}\nfunction make(seasonShown) { ${tagSrc}\n return seasonTag; }`, ['make'],
        { React, ChalklineText: 'ChalklineText', styles: { fitTag: { tag: 1 } }, ...TOKENS });
    } catch (e) { fail(name, `could not run seasonTag: ${e.message}`); }
    if (make) {
      const wrong = [];
      const tag = make(VALID);
      const a = tag({ id: '4866' });
      const b = tag({ id: '9493' });
      if (!a || a.props.testID !== 'trade-card.season-label.4866' || textOf(a) !== 'Win-now piece'
          || a.props.numberOfLines !== 1 || J(a.props.style) !== '{"tag":1}') wrong.push(`4866: ${J(a)}`);
      if (!b || textOf(b) !== 'Rebuild piece') wrong.push(`9493: ${J(b)}`);
      if (tag({ id: '1234' }) !== undefined) wrong.push('an unlabelled asset got a tag');
      if (make(undefined)({ id: '4866' }) !== undefined) wrong.push('a card without a block got a tag');
      // starts_for_you is not shown (the plan does not say how): flipping it changes nothing.
      const flipped = clone(VALID); flipped.labels[0].starts_for_you = false;
      if (J(make(flipped)({ id: '4866' })) !== J(a)) wrong.push('starts_for_you changed the tag');
      if (wrong.length) fail(name, wrong.join('; '));
      else ok(name);
    }
  }
}

// 6. Placement.
{
  const name = '6. line + conflict in the fit block after the You row; tag under the name in both columns; tag in the row label';
  const youAt = fitBlock.indexOf('testID="trade-card.fit-team.you"');
  const lineAt = fitBlock.indexOf('testID="trade-card.season-line"');
  const conflictAt = fitBlock.indexOf('testID="trade-card.season-conflict"');
  const slots = card.match(/belowNameSlot=\{seasonTag\(p\)\}/g) || [];
  const give = card.indexOf('<TickLabel>YOU SEND</TickLabel>');
  const get = card.indexOf('<TickLabel>YOU GET</TickLabel>');
  const slotAt = [...card.matchAll(/belowNameSlot=\{seasonTag\(p\)\}/g)].map((m) => m.index);
  const renders = player.match(/\{belowNameSlot\}/g) || [];
  const rowA11y = card.slice(card.indexOf('const rowA11y = '), card.indexOf('const rowA11y = ') + 2000);
  if (!fitBlock || youAt < 0 || lineAt < youAt || conflictAt < lineAt) {
    fail(name, 'the season line, then the conflict, must sit inside trade-card.fit-block after trade-card.fit-team.you');
  } else if (slots.length !== 2 || !(slotAt[0] > give && slotAt[0] < get && slotAt[1] > get)) {
    fail(name, 'YOU SEND and YOU GET PlayerCards must each pass belowNameSlot={seasonTag(p)}');
  } else if (renders.length !== 1
             || !/\{(?:player\.name|displayName)\}\s*<\/Text>\s*\{belowNameSlot\}\s*<View style=\{styles\.meta\}>/.test(player)) {
    fail(name, 'PlayerCard must render {belowNameSlot} once, directly under the name and above the meta line');
  } else if (!/p\.on_block \? 'on the block' : null,\s*seasonLabelFor\(seasonShown, p\.id\) \?\? null,/.test(rowA11y)) {
    fail(name, "rowA11y must add seasonLabelFor(seasonShown, p.id) to the row's accessibilityLabel");
  } else ok(name);
}

// 7. Gate.
{
  const name = '7. one gated read: fitFirstEnabled && !data.edited ? data.season_block : undefined';
  const reads = card.match(/season_block/g) || [];
  const uses = card.match(/seasonShown\b[^,;)]*/g) || [];
  const ungated = card.match(/\bseasonShown(?!\?\.|,|\s*=|\.line\}|\.conflict\.text\})/g) || [];
  if (!/const seasonShown = fitFirstEnabled && !data\.edited \? data\.season_block : undefined;/.test(card)) {
    fail(name, 'the block must be read as `fitFirstEnabled && !data.edited ? data.season_block : undefined`');
  } else if (reads.length !== 1) fail(name, `data.season_block read ${reads.length} times; only the gated read may touch it`);
  else if (ungated.length || uses.length < 5) fail(name, `every use of seasonShown must be optional or inside its own gate (${ungated.length} not)`);
  else ok(name);
}

// 8. No client composition.
{
  const name = '8. no client-side season copy; the card never reads numbers, label kind, starts_for_you or conflict.code';
  const copy = /pts\/wk|Dynasty (cost|gain|even)|Season (no change|[+-])|Win-now piece|Cornerstone|Rebuild piece|moves away from|above market|below market/;
  const literals = (src) => (src.match(/'[^'\n]*'|"[^"\n]*"|`[^`]*`|>[^<>{}]+</g) || []).filter((l) => copy.test(l));
  const hits = [['TradeCard', card], ['PlayerCard', player], ['trades.ts', api]]
    .flatMap(([f, s]) => literals(s).map((l) => `${f}: ${l}`));
  const reads = card.match(/\.(season_pts_week|dynasty_pct|dynasty_dir|starts_for_you|weeks|as_of)\b|conflict\??\.code\b|\bl\.label\b|\.labels\??\.(map|filter)/g) || [];
  if (hits.length) fail(name, `season copy literal(s): ${hits.join(' | ')}`);
  else if (reads.length) fail(name, `the card reads ${reads.join(', ')}`);
  else ok(name);
}

// 9. Neutral styles.
{
  const name = '9. season elements reuse fitLead / fitTag; no inline colour';
  const tagAt = card.indexOf('const seasonTag = (p: Player) => {');
  const tagSrc = tagAt < 0 ? '' : card.slice(tagAt, card.indexOf('\n  };\n', tagAt));
  const all = `${seasonJsx}\n${tagSrc}`;
  const styleProps = all.match(/style=\{[^}]*\}/g) || [];
  if (styleProps.length !== 3 || !styleProps.every((s) => s === 'style={styles.fitLead}' || s === 'style={styles.fitTag}')) {
    fail(name, `season styles were ${styleProps.join(' ')}`);
  } else if (/semantic|ice\.|flare|#[0-9a-fA-F]{3,8}\b|posColor/.test(all)) fail(name, 'a coloured token in the season elements');
  else ok(name);
}

// 10. Today's card unchanged: the fit guard, unmodified.
{
  const name = '10. a card without season_block renders as before: check-fit-first-copy passes unmodified';
  const r = spawnSync(process.execPath, [path.join(__dirname, 'check-fit-first-copy.js')], { encoding: 'utf8' });
  if (r.status !== 0) fail(name, `check-fit-first-copy failed:\n${(r.stderr || r.stdout).trim()}`);
  else ok(name);
}

// 11. Lint allow-list + npm script.
{
  const name = '11. trade-card.season-label.* allow-listed; npm run test:season-signal exists';
  const allow = read(ALLOW).split('\n').map((l) => l.trim());
  const pkg = JSON.parse(read(PKG) || '{}');
  if (!allow.includes('trade-card.season-label.*')) fail(name, 'add trade-card.season-label.* to scripts/testid-lint-allow.txt');
  else if ((pkg.scripts || {})['test:season-signal'] !== 'node tests/check-season-signal.js') {
    fail(name, 'add "test:season-signal": "node tests/check-season-signal.js" to mobile/package.json');
  } else ok(name);
}

for (const c of checks) console.log(`  ok  ${c}`);
if (failures.length) {
  for (const f of failures) console.error(`  FAIL ${f}`);
  console.error(`\ncheck-season-signal: ${failures.length} failed, ${checks.length} passed`);
  process.exit(1);
}
console.log(`\ncheck-season-signal: all ${checks.length} checks passed`);
