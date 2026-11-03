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
// What it does: scans every string literal and JSX text in mobile/src (AST,
// so comments never count), EXECUTES utils/tradePages.deckEndState over its
// whole input space, and pins the end card's component and wiring by source.
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

// ── 1. No "finding more" / "find more" copy anywhere in the build ─────────
// One reviewed exemption, matched exactly: Team Overhaul's error verb
// ("Finding more ideas" → "Finding more ideas failed…" on its own screen) is
// an error message about a different feature's request, not a deck state.
const EXEMPT = new Set(['screens/OverhaulReviewScreen.tsx::Finding more ideas']);
{
  const hits = [];
  for (const file of walk(SRC)) {
    const rel = path.relative(SRC, file);
    for (const s of strings(file)) {
      if (/find(ing)? more|loading more|more trades (are )?on the way/i.test(s) && !EXEMPT.has(`${rel}::${s}`)) {
        hits.push(`${rel}: "${s.trim().slice(0, 70)}"`);
      }
    }
  }
  check('1a. no "Finding more" / "Find more" / "loading more" copy anywhere in mobile/src', hits.length === 0,
    hits.join('\n      '));
  check('1b. the one exemption still exists (else drop it from EXEMPT)',
    strings(path.join(SRC, 'screens/OverhaulReviewScreen.tsx')).includes('Finding more ideas'));
}

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
  const code = stripComments(read('screens/TradesScreen.tsx'));
  const btns = code.match(/<Button[^>]*?testID="trades\.find-btn"[\s\S]*?\/>/g) || [];
  check('2c. D13: both page CTAs read "Find a Trade" only, and render only while the deck holds no cards',
    btns.length === 2 && btns.every((b) => /label="Find a Trade"/.test(b))
      && (code.match(/\{deck\.length === 0 \? \(\s*<>\s*\{canvasHost !== 'flag' \? \(\s*<Button\s+variant="primary"\s+testID="trades\.find-btn"/g) || []).length === 2,
    `found ${btns.length} find-btn mounts`);
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
  let flagOffEnds = 0;
  for (const status of ['running', 'complete', 'error']) {
    for (const pool of [undefined, false, true]) {
      for (const phase of ['idle', 'loading', 'retrying', 'failed']) {
        for (const online of [true, false]) {
          for (const deckId of [undefined, 'd']) {
            for (const [cursor, total] of [[30, 90], [90, 90], [undefined, undefined]]) {
              const r = deckEndState({ status, deck_id: deckId, pool_exhausted: pool, phase, online, cursor, total_ready: total });
              // head-eng's end rule: with deck_id only pool_exhausted ends the
              // deck; without it, complete + cursor ≥ total_ready. Never while
              // a page is in flight or retrying, never on an errored job.
              const ended = status !== 'error' && phase === 'idle'
                && (pool === true
                  || (deckId === undefined && status === 'complete' && cursor !== undefined && cursor >= total));
              if ((r === 'end') !== ended) bad.push(JSON.stringify({ status, deckId, pool, phase, online, cursor, total, r }));
              if (r === 'end') { ends++; if (deckId === undefined && pool !== true) flagOffEnds++; }
              if (!['end', 'offline', 'error', 'pending'].includes(r)) bad.push(`unknown state ${r}`);
            }
          }
        }
      }
    }
  }
  check('3a. deckEndState is "end" exactly by the end rule (deck_id ⇒ pool_exhausted; else complete + fully paged), never in flight or retrying',
    bad.length === 0 && ends > 0 && flagOffEnds > 0, bad.join('\n      '));
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
  // #393 M2 (engagement-eng; trades-eng adjustment 4): DeckEndCard has ONE
  // explicit variant, the paywall's preview end, rendered only when its
  // `previewEnd` prop is set. It is carved out first, so 4a–4d keep pinning
  // the genuine P30 card byte-for-byte on what is left; 4b2 and 4e pin the
  // variant itself. With no variant in the file, `p30 === fn` and every
  // check below is exactly what it was.
  let previewIf = null;
  let fnNode = null;
  (function visit(n) {
    if (ts.isFunctionDeclaration(n) && n.name?.text === 'DeckEndCard') fnNode = n;
    ts.forEachChild(n, visit);
  })(sf);
  const fnStatements = fnNode && fnNode.body ? fnNode.body.statements : [];
  for (const st of fnStatements) {
    if (ts.isIfStatement(st) && st.expression.getText(sf) === 'previewEnd') previewIf = st;
  }
  const previewBranch = previewIf ? previewIf.getText(sf) : '';
  const p30 = previewBranch ? fn.replace(previewBranch, '') : fn;
  // marketing-lead's copy file, rows p30.* — pinned verbatim.
  check('4a. P30 copy verbatim (p30.head, p30.body)',
    /export const DECK_END_TITLE = "You've seen every trade for now\.";/.test(comp)
      && /export const DECK_END_BODY = 'New ideas show up as rosters and values change\.';/.test(comp)
      && /<Text variant="heading">\{DECK_END_TITLE\}<\/Text>/.test(fn)
      && /<Text variant="bodySm" style=\{styles\.endBody\}>\{DECK_END_BODY\}<\/Text>/.test(fn));
  const buttons = p30.match(/<Button\b/g) || [];
  check('4b. exactly two actions: "Adjust your search" (p30.cta1, Primary) and "Back to Home" (p30.cta2, Secondary) — no third',
    buttons.length === 2
      && /label="Adjust your search"\s*variant="primary"/.test(p30)
      && /label="Back to Home"\s*variant="secondary"/.test(p30),
    `${buttons.length} buttons`);
  if (previewIf) {
    // The variant is the statement right before P30's return, and it returns:
    // the P30 render is reached only when `previewEnd` is unset.
    const at = fnStatements.indexOf(previewIf);
    const last = fnStatements[fnStatements.length - 1];
    check('4b2. #393 M2 preview_end: only when `previewEnd` is set; eyebrow + mon.lock.find; ONE Primary (See plans / Continue), no tally, no Adjust/Home',
      at === fnStatements.length - 2 && ts.isReturnStatement(last)
        && /^if \(previewEnd\) \{\s*return \(/.test(previewBranch)
        && (previewBranch.match(/<Button\b/g) || []).length === 1
        && /<Button\s+testID="deck-end-paywall-cta"\s+label=\{previewEnd\.verify \? MON\['mon\.verify\.continue'\] : MON\['mon\.pay\.see_plans'\]\}\s+variant="primary"\s+onPress=\{previewEnd\.onPress\}/.test(previewBranch)
        && /<Text variant="heading">\{MON\['mon\.preview\.page_end'\]\}<\/Text>/.test(previewBranch)
        && /<Text variant="bodySm" style=\{styles\.endBody\}>\{MON\['mon\.lock\.find'\]\}<\/Text>/.test(previewBranch)
        && !/tally|onAdjust|onHome|DECK_END_|\$\d|price|free/i.test(previewBranch.replace(/MON\['mon\.[a-z_.]+'\]/g, '')),
      'the variant is one if-return before P30, with exactly one Primary and no P30 parts');
  }
  check('4c. no Like/Pass, no count, no "new trades" notice on the end card',
    !/onLike|onPass|disposition|Toast|Badge|newTrades|onSeeNew|count/i.test(fn.replace(/DeckEndCard/g, ''))
      && !/new trade/i.test(fn),
    'the card takes minHeight, tally, onAdjust, onHome — nothing that could announce arrivals');
  check('4d. D14b / p30.tally: one chalk-dim line, "{passed} passed · {liked} liked · {proposed} proposed", Plex Mono numerals, suppressed at 0 · 0 · 0 (P36)',
    /<Text variant="bodySm" testID="trades\.deck-end\.tally" style=\{styles\.endBody\}>\s*<Text style=\{styles\.tallyNum\}>\{tally\.passed\}<\/Text>\s*\{' passed · '\}\s*<Text style=\{styles\.tallyNum\}>\{tally\.liked\}<\/Text>\s*\{' liked · '\}\s*<Text style=\{styles\.tallyNum\}>\{tally\.proposed\}<\/Text>\s*\{' proposed'\}\s*<\/Text>/.test(fn)
      && /tallyNum: \{ fontFamily: fonts\.data, fontVariant: \['tabular-nums'\] \}/.test(comp)
      && /\{tally && \(tally\.passed \|\| tally\.liked \|\| tally\.proposed\) \? \(/.test(fn) && !/tally\.passed \+|passed \+ tally/.test(fn)
      && /P36 \(head-product, 2026-10-23; PRD row 4\): suppressed at 0 · 0 · 0\./.test(fn));
  const code = stripComments(read('screens/TradesScreen.tsx'));
  // #393 M2: besides the one P30 mount, at most ONE preview_end mount, which
  // carries exactly minHeight + previewEnd and renders only from the deck's
  // 402 end (`pagedWithCards && deckGateEnd && (!rawTopCard || showDeckEndCard)`,
  // ahead of P30 so a 402 end never shows P30).
  const previewMounts = code.match(/\) : pagedWithCards && deckGateEnd && \(!rawTopCard \|\| showDeckEndCard\) \? \(\s*<DeckEndCard\s+minHeight=\{topCardH\}\s+previewEnd=\{\{[^}]*\}\}\s*\/>/g) || [];
  check('4e. the screen mounts it once, with exactly those props (plus at most one preview_end mount, only from the 402 end)',
    previewMounts.length <= 1
      && (code.match(/<DeckEndCard\b/g) || []).length === 1 + previewMounts.length
      && (code.match(/previewEnd=/g) || []).length === previewMounts.length
      && /<DeckEndCard\s+minHeight=\{topCardH\}\s+tally=\{replenishmentOn \? sessionTally : null\}\s+onAdjust=\{handleDeckEndAdjust\}\s+onHome=\{homeTabOn \? handleDeckEndHome : undefined\}\s*\/>/.test(code));
  check('4f. it renders only from showDeckEndCard = pagedWithCards && (latched || deckEnd === "end"), latched only on "end"',
    /const showDeckEndCard = pagedWithCards && \(endLatched \|\| deckEnd === 'end'\);/.test(code)
      && /if \(deckEnd === 'end'\) setEndLatched\(true\);/.test(code)
      && (code.match(/setEndLatched\(true\)/g) || []).length === 1);
  const quick = code.indexOf('<QuickSetPromptCard');
  const endAt = code.indexOf(') : showDeckEndCard ? (');
  const topAt = code.indexOf(') : topCard ? (');
  check('4g. D14c: the latched end card precedes the card branch, so later cards wait BEHIND it',
    quick > -1 && endAt > quick && topAt > endAt);
  check('4h. deck_exhausted_viewed fires only when the end card shows (a paged deck is exhausted iff showDeckEndCard; no deck-done summary)',
    /const deckExhausted = pagedWithCards\s*\?\s*showDeckEndCard\s*:/.test(code)
      && /const summaryVisible =\s*!pagedWithCards &&/.test(code)
      && /track\('deck_exhausted_viewed'/.test(code));
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
    /resetDeckForNewTargets\(\);[\s\S]*lastModelRequestRef\.current = model;[\s\S]*handleFindTrades\('end_card_adjust'\);/.test(apply)
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
