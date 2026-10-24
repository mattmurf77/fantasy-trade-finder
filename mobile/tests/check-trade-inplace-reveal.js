#!/usr/bin/env node
// WHY THIS EXISTS (ux-lead "U1: the in-place reveal", design-lead "U1: the
// first card, revealed in place", AC-L1/AC-L2): Find a trade must land on the
// complete first card in its FIRST frame, with no animated push and no frame
// of idle card, "Looking for trades…", progress strip or skeleton in between.
// Every one of those regressions is invisible to a type check and to a
// passing UI test that only looks at the settled screen:
//   - the TradeDeck route regains its default slide (AC-L2);
//   - the landing pushes BEFORE page 1 is in hand, so the deck mounts empty;
//   - the pushed instance's mount effects (the league reset, the #330 choke
//     point) wipe the page it was handed, one frame after showing it;
//   - a wait state is ordered ahead of the card, or the progress strip stays
//     mounted above cards that are already in hand (pushing the card down);
//   - VoiceOver focus stays on the Find a Trade control.
// What it does: pins the route option and the deck chain's order by source,
// and EXECUTES the adoption predicate (adoptablePage / adoptedFirstPage)
// lifted from TradesScreen. HONEST LABEL (G-035): this proves the first
// render is built from the handed-over page and that the mount resets skip
// it; the frame timing itself is the TestFlight checklist's (40 taps / cell).
//
// Run: node tests/check-trade-inplace-reveal.js   (or: npm run test:trade-inplace-reveal)
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

const tabNav = stripComments(read('navigation/TabNav.tsx'));
const trades = read('screens/TradesScreen.tsx');
const code = stripComments(trades);
const card = read('components/TradeCard.tsx');

console.log('check-trade-inplace-reveal:');

// ── 1. The instant route ──────────────────────────────────────────────────
{
  const at = tabNav.indexOf('name="TradeDeck"');
  const el = at > -1 ? tabNav.slice(at, tabNav.indexOf('/>', at)) : '';
  check("1a. the TradeDeck route has animation: 'none' (push AND pop: native-stack applies it both ways)",
    /animation: 'none'/.test(el), 'the Find a trade push must not animate (AC-L2)');
  check('1b. …on both header arms (the resultsPush deck and the deep-link deck)',
    /\(\{\s*\.\.\.\(\(route\.params as any\)\?\.resultsPush[\s\S]*?: \{ headerShown: false \}\),\s*animation: 'none',\s*\}\)/.test(el),
    'animation must sit outside the header ternary');
}

// ── 2. Page 1 is in hand before the push ─────────────────────────────────
{
  const inline = code.slice(code.indexOf('function handleInlineFindATrade('), code.indexOf('async function handleInlineLikeTrade('));
  const arm = inline.slice(inline.indexOf('if (resultsPushLive) {'));
  check('2a. the canvas Find a Trade hands its push to pushWithFirstPage instead of pushing at once',
    /const pushDeck = \(firstPage\?: FirstPageHandoff\) =>\s*navigation\?\.push\?\.\('TradeDeck'/.test(arm)
      && /\.\.\.\(firstPage \? \{ firstPage \} : \{\}\)/.test(arm)
      && /pushWithFirstPage\(fork, pushDeck\);\s*return;/.test(arm));
  const helper = code.slice(code.indexOf('function pushWithFirstPage('), code.indexOf('function handleInlineFindATrade('));
  check('2b. pushWithFirstPage requests page 1 (paged, client search id) and pushes from its result',
    /generateTrades\(request, \{ searchId: uuidv4\(\) \}\)\s*\.then\(\(snapshot\) => go\(adoptablePage\(snapshot\) \? \{ request, snapshot \} : undefined\)\)/.test(helper));
  check('2c. …with a bounded wait: past the deadline (or on failure) it pushes without the page',
    /setTimeout\(\(\) => go\(\), FIRST_PAGE_PUSH_DEADLINE_MS\)/.test(helper) && /\.catch\(\(\) => go\(\)\)/.test(helper)
      && /if \(pushed\) return;/.test(helper));
  check('2d. a fair (anchored) search keeps its immediate push (no stored page to wait for)',
    /if \(fork\.anchor \|\| !fairnessReady\) \{\s*pushDeck\(\);\s*return;\s*\}/.test(helper));
}

// ── 3. EXECUTED: which pages the pushed deck adopts ───────────────────────
{
  const sf = ts.createSourceFile('T.tsx', trades, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const fns = [];
  (function visit(n) {
    if (ts.isFunctionDeclaration(n) && ['adoptablePage', 'adoptedFirstPage'].includes(n.name?.text)) fns.push(n.getText(sf));
    ts.forEachChild(n, visit);
  })(sf);
  const pages = fs.readFileSync(path.join(SRC, 'utils/tradePages.ts'), 'utf8');
  const src = `${pages}\n${fns.join('\n')}\nmodule.exports.adoptedFirstPage = adoptedFirstPage;`;
  const module = { exports: {} };
  let adopted = null;
  try {
    vm.runInNewContext(ts.transpileModule(src, { compilerOptions: {
      target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS } }).outputText,
    { module, exports: module.exports, Set, Map, Math });
    adopted = module.exports.adoptedFirstPage;
  } catch (e) { /* reported below */ }
  check('3a. adoptablePage + adoptedFirstPage lift and run', typeof adopted === 'function' && fns.length === 2);
  if (typeof adopted === 'function') {
    const route = (snapshot) => ({ params: { resultsPush: { firstPage: { request: {}, snapshot } } } });
    const c = [{ trade_id: 'a' }];
    check('3b. a paged page WITH cards is adopted (first frame = the card)',
      !!adopted(route({ status: 'complete', cursor: 1, cards: c })));
    check('3c. a paged page with no cards yet, job still building, is adopted (one job, honest wait)',
      !!adopted(route({ status: 'running', cursor: 0, cards: [] })));
    check('3d. never adopted: errored, finished-empty, legacy (no cursor), or no param',
      !adopted(route({ status: 'error', cursor: 0, cards: c }))
        && !adopted(route({ status: 'complete', cursor: 0, cards: [] }))
        && !adopted(route({ status: 'complete', cards: c }))
        && !adopted({ params: {} }) && !adopted(undefined));
  }
}

// ── 4. The pushed instance renders from the page and keeps it ──────────────
{
  check('4a. deck and job are INITIALIZED from the adopted page (first render, no effect hop)',
    /const \[adopted\] = useState\(\(\) => adoptedFirstPage\(route\)\);/.test(code)
      && /const \[deck, setDeck\] = useState<PagedTradeCard\[\]>\(\(\) => adopted\?\.snapshot\.cards \?\? \[\]\);/.test(code)
      && /const \[job, setJob\] = useState<PagedTradeJobSnapshot \| null>\(\(\) => adopted\?\.snapshot \?\? null\);/.test(code));
  check('4b. …and the scope/origin the card renders with are initialized too (no second-frame change)',
    />\(\(\) => \(adopted \? route\?\.params\?\.resultsPush\?\.opponent \?\? null : null\)\);/.test(code)
      && /\(\) => \(adopted && route\?\.params\?\.resultsPush\?\.origin === 'calculator' \? 'calculator' : null\)/.test(code));
  const league = code.slice(code.indexOf('const keepAdoptedPage = adoptedMountRef.current.league;'));
  check("4c. the league effect's MOUNT run keeps the adopted deck and job",
    /if \(!keepAdoptedPage\) \{\s*setDeck\(\[\]\);\s*setDeckIdx\(0\);\s*\}/.test(league.slice(0, 2500))
      && /if \(!keepAdoptedPage\) setJob\(null\);/.test(league.slice(0, 2500)));
  const chokeAt = code.indexOf('const adoptedRun = adoptedMountRef.current.choke;');
  const choke = chokeAt > -1 ? code.slice(chokeAt, chokeAt + 6000) : '';
  check('4d. the #330 choke point neither resets nor re-dispatches the adopted search (once)',
    /adoptedMountRef\.current\.choke = false;\s*if \(!adoptedRun\) resetDeckForNewTargets\(\);/.test(choke)
      && /if \(adoptedRun\) lastModelRequestRef\.current = adopted\?\.request \?\? null;\s*else dispatchGenerate\(\{\}\);/.test(choke));
}

// ── 5. No wait state ahead of cards in hand ──────────────────────────────
{
  const deckAt = code.indexOf('style={styles.deckWrap}');
  const deckEnd = code.indexOf('{!landingDeckRetired && singlePinDeckActive ? assetIdeasPanel : null}');
  const chain = deckAt > -1 && deckEnd > deckAt ? code.slice(deckAt, deckEnd) : '';
  const topAt = chain.indexOf(') : topCard ? (');
  const skelAt = chain.indexOf('<SkeletonTradeCard />');
  const lookAt = chain.indexOf('Looking for trades…');
  const idleAt = chain.indexOf('Hit "Find a Trade" to start');
  check('5a. the card branch precedes the skeleton, "Looking for trades…" and idle branches in the deck slot',
    topAt > -1 && skelAt > topAt && lookAt > topAt && idleAt > topAt,
    `topCard@${topAt} skeleton@${skelAt} looking@${lookAt} idle@${idleAt}`);
  const pagedAt = chain.indexOf(') : pagedWithCards && deckEnd ? (');
  check('5b. past the last card of a paged deck, its own states precede every wait card',
    pagedAt > topAt && pagedAt < skelAt && pagedAt < lookAt);
  check('5c. the skeleton is first-run with NO cards only',
    /firstRun &&\s*!fairDeck &&\s*deck\.length === 0 &&/.test(chain));
  const strips = code.match(/\{!pagedWithCards && job\?\.status === 'running' && !landingDeckRetired && \(\s*<View testID="trades\.progress-strip"/g) || [];
  const allStrips = code.match(/testID="trades\.progress-strip"/g) || [];
  check('5d. both progress strips stand aside once a paged deck holds cards (nothing mounts above the card)',
    strips.length === 2 && allStrips.length === 2, `gated ${strips.length} of ${allStrips.length}`);
}

// ── 6. VoiceOver: focus moves to the first card ──────────────────────────
{
  check('6a. a reveal (deck empty → first card) moves focus to the card header once',
    /if \(revealedRef\.current \|\| !rawTopCard\) return;\s*revealedRef\.current = true;/.test(code)
      && /AccessibilityInfo\.setAccessibilityFocus\(node\)/.test(code)
      && /a11ySummaryRef=\{revealFocusRef\}/.test(code));
  check('6b. the card header carries the summarizing label (partner, give, get, verdict)',
    /a11ySummary=\{tradeA11ySummary\(topCard\)\}/.test(code)
      && /ref=\{a11ySummaryRef\}\s*accessible=\{a11ySummary \? true : undefined\}\s*accessibilityLabel=\{a11ySummary\}/.test(card)
      && /`Trade with \$\{card\.opponent_username\}\. You give \$\{names\(card\.give_players\)\}\.`/.test(code));
}

console.log(failures ? `check-trade-inplace-reveal: ${failures} FAILED` : 'check-trade-inplace-reveal: all passed');
process.exit(failures ? 1 : 0);
