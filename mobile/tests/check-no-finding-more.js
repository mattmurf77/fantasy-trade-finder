#!/usr/bin/env node
// WHY THIS EXISTS (operator, 2026-10-20, on a "finding more trades" card:
// "This should never happen."; AC-L4; ux-lead U3; head-eng rulings 13 —
// D13 + D14): the deck never ends while more trades are coming, so the build
// must contain no waiting-for-more state at all, and its one honest ending —
// Product's P30 end card — may show only when the SERVER says the pool is
// exhausted. Failure modes this catches:
//   - a "Finding more…" / "Find more trades" / keep-going card or button is
//     (re)introduced anywhere in mobile/src;
//   - the end card renders on a client guess (an empty buffer, a slow page,
//     a fetch in flight or retrying) instead of `pool_exhausted`;
//   - the end card grows a third action, a "new trades" notice, a count, or
//     Like/Pass; or it swaps away when later cards arrive (D14c);
//   - "Adjust what I'm looking for" navigates instead of searching in place
//     (D14a), or loses its AC-L1 clock-start boundary for the M pass.
// What it does: scans the Trades surfaces' strings (AST, so comments never
// count), EXECUTES utils/tradePages.deckEndState over its whole input space,
// and pins the end card's component and wiring by source.
// HONEST LABEL (G-035): the scan and the state matrix are exhaustive; the
// rendering pins prove wiring, not pixels (TestFlight checklist: the U3
// three-page run ends on this card).
//
// Run: node tests/check-no-finding-more.js   (or: npm run test:no-finding-more)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
let ts;
try { ts = require('typescript'); } catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}
const SRC = path.join(__dirname, '..', 'src');
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const stripComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

let failures = 0;
function check(name, cond, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}${detail ? `\n      ${detail}` : ''}`); }
}

// Every user-facing string: string literals, template pieces and JSX text.
function strings(file) {
  const text = fs.readFileSync(file, 'utf8');
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true,
    file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const out = [];
  (function visit(n) {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)
        || ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n) || ts.isJsxText(n)) {
      out.push(n.text);
    }
    ts.forEachChild(n, visit);
  })(sf);
  return out;
}
function walk(dir, acc = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, acc);
    else if (/\.tsx?$/.test(ent.name)) acc.push(p);
  }
  return acc;
}

console.log('check-no-finding-more:');

// ── 2. …and no keep-going copy or state on the Trades surfaces ────────────
{
  const files = ['screens/TradesScreen.tsx', 'components/TradeDeckStates.tsx', 'components/TradeCard.tsx',
    'utils/tradePages.ts', 'api/trades.ts'];
  const copy = [];
  const state = [];
  for (const rel of files) {
    for (const s of strings(path.join(SRC, rel))) {
      if (/keep going|still looking|more on the way|hang tight|fetching more/i.test(s)) copy.push(`${rel}: "${s.trim()}"`);
    }
    const code = stripComments(read(rel));
    const m = code.match(/\b(findingMore|keepGoing|loadingMore|fetchingMore|moreLoading|isFindingMore)\b/g);
    if (m) state.push(`${rel}: ${[...new Set(m)].join(', ')}`);
  }
  check('2a. no keep-going copy on the deck', copy.length === 0, copy.join('\n      '));
  check('2b. no waiting-for-more state variable on the deck', state.length === 0, state.join('\n      '));
}

// ── 3. EXECUTED: the end card only on the server's pool_exhausted ─────────
{
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(read('utils/tradePages.ts'), { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS } }).outputText,
  { module, exports: module.exports, Set, Map, Math });
  const { deckEndState } = module.exports;
  const bad = [];
  let ends = 0;
  for (const status of ['running', 'complete', 'error']) {
    for (const pool of [undefined, false, true]) {
      for (const phase of ['idle', 'loading', 'retrying', 'failed']) {
        for (const online of [true, false]) {
          for (const [cursor, total] of [[30, 90], [90, 90], [undefined, undefined]]) {
            const r = deckEndState({ status, pool_exhausted: pool, phase, online, cursor, total_ready: total });
            if (r === 'end') {
              ends++;
              if (pool !== true || phase !== 'idle') bad.push(JSON.stringify({ status, pool, phase, online, cursor }));
            }
            if (!['end', 'offline', 'error', 'legacy', 'pending'].includes(r)) bad.push(`unknown state ${r}`);
          }
        }
      }
    }
  }
  check('3a. deckEndState is "end" ONLY with pool_exhausted: true and nothing in flight or retrying',
    bad.length === 0 && ends > 0, bad.join('\n      '));
  check('3b. offline past the last card is the Offline state, never the end, while pages may still come',
    deckEndState({ status: 'running', pool_exhausted: false, phase: 'idle', online: false, cursor: 30, total_ready: 30 }) === 'offline');
  check('3c. a page in flight past the last card renders nothing (no spinner, no copy)',
    deckEndState({ status: 'running', pool_exhausted: false, phase: 'loading', online: true, cursor: 30, total_ready: 60 }) === 'pending');
}

// ── 4. The end card: P30's copy, two actions, nothing else (D14) ──────────
{
  const comp = read('components/TradeDeckStates.tsx');
  const sf = ts.createSourceFile('S.tsx', comp, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let fn = '';
  (function visit(n) {
    if (ts.isFunctionDeclaration(n) && n.name?.text === 'DeckEndCard') fn = n.getText(sf);
    ts.forEachChild(n, visit);
  })(sf);
  check('4a. P30 copy verbatim', /export const DECK_END_TITLE = "You've seen every trade we have for now\.";/.test(comp)
    && /export const DECK_END_BODY = 'New ideas show up as rosters and values change\.';/.test(comp));
  const buttons = fn.match(/<Button\b/g) || [];
  check('4b. exactly two actions: "Adjust what I\'m looking for" (Primary) and "Back to Home" (Secondary) — no third',
    buttons.length === 2
      && /label="Adjust what I'm looking for"\s*variant="primary"/.test(fn)
      && /label="Back to Home"\s*variant="secondary"/.test(fn),
    `${buttons.length} buttons`);
  check('4c. no Like/Pass, no count, no "new trades" notice on the end card',
    !/onLike|onPass|disposition|Toast|Badge|newTrades|onSeeNew|count/i.test(fn.replace(/DeckEndCard/g, ''))
      && !/new trade/i.test(fn),
    'the card takes minHeight, tally, onAdjust, onHome — nothing that could announce arrivals');
  check('4d. D14b: the D-171 tally is one chalk-dim line (bodySm)',
    /<Text variant="bodySm" testID="trades\.deck-end\.tally"/.test(fn));
  const code = stripComments(read('screens/TradesScreen.tsx'));
  check('4e. the screen mounts it once, with exactly those props',
    (code.match(/<DeckEndCard\b/g) || []).length === 1
      && /<DeckEndCard\s+minHeight=\{topCardH\}\s+tally=\{[\s\S]*?\}\s+onAdjust=\{handleDeckEndAdjust\}\s+onHome=\{homeTabOn \? handleDeckEndHome : undefined\}\s*\/>/.test(code));
  check('4f. it renders only from showDeckEndCard = pagedWithCards && (latched || deckEnd === "end"), latched only on "end"',
    /const showDeckEndCard = pagedWithCards && \(endLatched \|\| deckEnd === 'end'\);/.test(code)
      && /if \(deckEnd === 'end'\) setEndLatched\(true\);/.test(code)
      && (code.match(/setEndLatched\(true\)/g) || []).length === 1);
  const quick = code.indexOf('<QuickSetPromptCard');
  const endAt = code.indexOf(') : showDeckEndCard ? (');
  const topAt = code.indexOf(') : topCard ? (');
  check('4g. D14c: the latched end card precedes the card branch, so later cards wait BEHIND it',
    quick > -1 && endAt > quick && topAt > endAt);
}

// ── 5. D14a: Adjust searches IN PLACE; the AC-L1 boundary is marked ───────
{
  const code = stripComments(read('screens/TradesScreen.tsx'));
  const raw = read('screens/TradesScreen.tsx');
  const fnText = (name) => {
    const at = code.indexOf(`function ${name}(`);
    return at > -1 ? code.slice(at, code.indexOf('\n  }\n', at)) : '';
  };
  const adjust = fnText('handleDeckEndAdjust');
  const apply = fnText('applyDeckEndAdjust');
  check('5a. Adjust opens the deck\'s own preferences (DNA sheet, else outlook sheet) — no navigation',
    /if \(consolidateOn\) setDnaSheetOpen\(true\);\s*else setOutlookOpen\(true\);/.test(adjust) && !/navigat/.test(adjust));
  check('5b. applying runs the search in place: reset + the saved request repeated, no navigation',
    /resetDeckForNewTargets\(\);[\s\S]*lastModelRequestRef\.current = model;[\s\S]*handleFindTrades\(\);/.test(apply)
      && !/navigat/.test(apply));
  check('5c. the apply tap reaches it from both sheets (DNA close with a change; outlook submit)',
    /if \(endAdjust && \(prefsChangedSinceGenerateRef\.current \|\| endAdjust\.fairnessOn !== fairnessOn\)\) \{\s*applyDeckEndAdjust\(\);/.test(code)
      && /if \(endAdjustRef\.current\) \{\s*endAdjustRef\.current = null;\s*applyDeckEndAdjust\(\);/.test(code));
  check('5d. the AC-L1 clock-start marker sits on that function boundary (for the M pass)',
    /AC-L1 CLOCK START \(M pass\)[\s\S]{0,400}?\n  function applyDeckEndAdjust\(\)/.test(raw));
  check('5e. Back to Home switches to the Home tab', /navigation\?\.navigate\?\.\('Home'\)/.test(fnText('handleDeckEndHome')));
}

console.log(failures ? `check-no-finding-more: ${failures} FAILED` : 'check-no-finding-more: all passed');
process.exit(failures ? 1 : 0);
