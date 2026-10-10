#!/usr/bin/env node
// Home hub destinations — everything Home navigates INTO (flag
// `nav.home_hub`; docs/plans/home-engagement/scope.md §6.4, "M-Dest guard
// must pin").
//
// WHY THIS EXISTS. D-056 retired the simulator, so nothing but this file and
// a TestFlight checklist witnesses the arrival. And almost nothing here fails
// loudly: an intent consumed by the legacy root-stack push, a drill-in left
// open under the new filter, a Sell that lands on the chart instead of the
// shortest teams, a banner that scrolls away, an outlook simulation fired on
// page open, or a segment event emitted from an effect all LOOK right in a
// demo. Each section below names the regression it catches.
//
// Pins (scope §6.4, items 1-10, plus testIDs and Chalkline):
//   1. the consume is tab-root only and one-shot (takeLeagueSummaryIntent);
//   2. it resets consensus / all / filter, closing a drill-in through the
//      EXISTING auto-exit, with no new setSelectedId(null);
//   3. the banner is outside the ScrollView, split only, and clears on
//      filter/subset change, blur and its close control;
//   4. Sell → scrollToEnd, Buy → the list container's onLayout top;
//   5. Standings is a root-stack route registered unconditionally with
//      HeaderBack, and the screen mounts exactly one FeedbackFAB
//      aboveTabBar={false};
//   6. the outlook query is enabled only on Projected;
//   7. standings_segment_changed sits in a tap handler, never an effect;
//   8. the deep link exists;
//   9. the Season-outlook calibration rules hold where the renderer lives
//      (it stays in LeagueSummaryScreen and Standings imports it);
//  10. the roster/user queries keep staleTime 5 * 60_000 and are
//      Sleeper-gated.
//
// Assertions of the form "X appears nowhere" read COMMENT-STRIPPED code: the
// comments deliberately name the constructs they forbid.
//
// Run: node tests/check-home-destinations.js   (npm run test:home-destinations)
'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
let ts;
try {
  ts = require('typescript');
} catch (e) {
  console.error('FAIL  typescript is not installed (run npm install in mobile/)');
  process.exit(1);
}

let failures = 0;
let passes = 0;
const assert = (cond, name, why) => {
  if (cond) {
    passes += 1;
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`);
  }
};

const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const parse = (rel) =>
  ts.createSourceFile(rel, read(rel), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const printer = ts.createPrinter({ removeComments: true });
/** Comment-free, whitespace-collapsed source of a node. */
const flat = (sf, node) =>
  printer.printNode(ts.EmitHint.Unspecified, node, sf).replace(/\s+/g, ' ');
const code = (sf) => printer.printFile(sf);

function findAll(root, pred) {
  const out = [];
  (function walk(n) {
    if (pred(n)) out.push(n);
    ts.forEachChild(n, walk);
  })(root);
  return out;
}
const isCallTo = (n, name) =>
  ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === name;
const callsTo = (root, name) => findAll(root, (n) => isCallTo(n, name));
const count = (text, needle) => text.split(needle).length - 1;
function ancestors(node) {
  const out = [];
  for (let p = node.parent; p; p = p.parent) out.push(p);
  return out;
}
const isJsxEl = (n) => ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n);
const opening = (n) => (ts.isJsxElement(n) ? n.openingElement : n);
const tagOf = (sf, n) => opening(n).tagName.getText(sf);
function attr(n, name) {
  return opening(n).attributes.properties.find(
    (p) => ts.isJsxAttribute(p) && p.name.getText() === name,
  );
}
/** An attribute's value: string literals keep their quotes, `{expr}` loses its braces. */
const attrText = (sf, n, name) => {
  const a = attr(n, name);
  if (!a || !a.initializer) return null;
  const init = a.initializer;
  return ts.isJsxExpression(init) && init.expression ? flat(sf, init.expression) : flat(sf, init);
};
const byTestId = (sf, id) =>
  findAll(sf, (n) => isJsxEl(n) && attrText(sf, n, 'testID') === `"${id}"`);
/** The variable declaration named `name`, anywhere in the file. */
const declOf = (sf, name) =>
  findAll(sf, (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name)[0];
/** A useEffect/useFocusEffect/useLayoutEffect call enclosing `node`, if any. */
const enclosingEffect = (node) =>
  ancestors(node).find(
    (a) =>
      isCallTo(a, 'useEffect') || isCallTo(a, 'useFocusEffect') || isCallTo(a, 'useLayoutEffect'),
  );

const LS_REL = 'src/screens/LeagueSummaryScreen.tsx';
const ST_REL = 'src/screens/StandingsScreen.tsx';
const NAV_REL = 'src/navigation/RootNav.tsx';
const DL_REL = 'src/utils/deepLinks.ts';

const ls = parse(LS_REL);
const lsCode = code(ls);
const st = parse(ST_REL);
const stCode = code(st);
const nav = parse(NAV_REL);
const navCode = code(nav);
const dlText = read(DL_REL);

// ═══ 1. The consume: tab root only, one-shot ═══════════════════════════════
// Sabotage caught: dropping the isTabRoot gate lets the legacy root-stack
// LeagueSummary push (deep link app/league/summary) steal the tab's intent;
// reading `pending` instead of `take` replays the arrival on every focus.
const takes = callsTo(ls, 'takeLeagueSummaryIntent');
assert(takes.length === 1, '1a. exactly one takeLeagueSummaryIntent( call in LeagueSummaryScreen',
  `found ${takes.length}`);
assert(callsTo(st, 'takeLeagueSummaryIntent').length === 0,
  '1b. StandingsScreen never consumes the League-rankings intent');
const consumeEffect = takes[0] && enclosingEffect(takes[0]);
assert(!!consumeEffect && isCallTo(consumeEffect, 'useFocusEffect'),
  '1c. the take runs inside a useFocusEffect (consumed on focus, not on render)');
const consumeCb =
  consumeEffect && consumeEffect.arguments[0] && isCallTo(consumeEffect.arguments[0], 'useCallback')
    ? consumeEffect.arguments[0]
    : null;
const consumeFn = consumeCb ? consumeCb.arguments[0] : null;
const consumeBody = consumeFn && ts.isBlock(consumeFn.body) ? consumeFn.body : null;
const consumeText = consumeBody ? flat(ls, consumeBody) : '';
{
  const first = consumeBody ? consumeBody.statements[0] : null;
  assert(!!first && flat(ls, first) === 'if (!isTabRoot) return;',
    '1d. the consume\'s FIRST statement is `if (!isTabRoot) return;` (tab root only)',
    first ? `saw: ${flat(ls, first)}` : 'consume body not found');
  const deps = consumeCb && consumeCb.arguments[1];
  assert(!!deps && ts.isArrayLiteralExpression(deps) &&
      deps.elements.some((e) => e.getText(ls) === 'intentSeq'),
    '1e. the consume is keyed on the intent seq (a repeat Home tap re-fires)');
  const seqDecl = declOf(ls, 'intentSeq');
  assert(!!seqDecl && /^useLeagueSummaryIntent\(\(s\) => s\.pending\?\.seq\)$/.test(flat(ls, seqDecl.initializer)),
    '1f. intentSeq = useLeagueSummaryIntent((s) => s.pending?.seq)');
  assert(callsTo(ls, 'useLeagueSummaryIntent').length === 1 &&
      !/useLeagueSummaryIntent\.getState\(\)/.test(lsCode) &&
      !/\.take\(/.test(lsCode),
    '1g. the store is read ONLY through the seq selector and takeLeagueSummaryIntent (one-shot)');
}

// ═══ 2. The W2 reset, and the drill-in close ═══════════════════════════════
// Sabotage caught: a bare setSelectedId(null) (the exit vanishes from
// analytics); routing the reset through changeBasis/switchSubset (a lens
// event nobody chose); a second closeTeam('filter_change') call site.
assert(/setBasis\('consensus'\);/.test(consumeText) && /setSubset\('all'\);/.test(consumeText),
  "2a. the consume sets basis 'consensus' and subset 'all'");
assert(/setPosFilter\(new Set<FilterKey>\(\[intent\.position\]\)\);/.test(consumeText) &&
    /setPosFilter\(new Set<FilterKey>\(\)\);/.test(consumeText),
  '2b. the filter becomes exactly {position} (split) or empty (all)');
assert(consumeText.length > 0 &&
    !/setSelectedId|closeTeam\(|changeBasis\(|switchSubset\(|track\(/.test(consumeText),
  '2c. the consume sets no selection, calls no exit control and emits nothing itself');
assert(count(lsCode, 'setSelectedId(null)') === 1,
  '2d. still exactly ONE setSelectedId(null) in LeagueSummaryScreen (inside closeTeam)');
assert(count(lsCode, "closeTeam('filter_change')") === 1,
  "2e. the drill-in close is the existing auto-exit — one closeTeam('filter_change') call site");
{
  const sigIdx = consumeText.indexOf('filterSigRef.current = ');
  const setIdx = consumeText.indexOf('setPosFilter(');
  assert(sigIdx >= 0 && sigIdx < setIdx,
    '2f. the consume re-arms the auto-exit\'s signature before setting the filter',
    'without it an open RB drill-in survives Home → Sell RB (the filter does not change)');
}

// ═══ 3. The pinned banner ══════════════════════════════════════════════════
// Sabotage caught: moving the banner into the ScrollView (it scrolls away at
// the Sell landing); showing it for kind 'all' or a no-split position;
// dropping any of its three clears.
const banners = byTestId(ls, 'league-summary.arrival-banner');
const pageScroll = findAll(ls, (n) => isJsxEl(n) && tagOf(ls, n) === 'ScrollView' &&
  attrText(ls, n, 'onScroll') === 'notifyGuideTargetsMoved')[0];
{
  const b = banners[0];
  const anc = b ? ancestors(b) : [];
  assert(banners.length === 1 && !anc.some((a) => isJsxEl(a) && tagOf(ls, a) === 'ScrollView') &&
      anc.some((a) => isJsxEl(a) && tagOf(ls, a) === 'SafeAreaView'),
    '3a. the banner renders OUTSIDE every ScrollView, inside the page SafeAreaView');
  assert(!!b && !!pageScroll && b.getStart(ls) < pageScroll.getStart(ls),
    '3b. the banner sits ABOVE the page ScrollView (between the stack header and the page)');
  const gate = anc.find((a) => ts.isConditionalExpression(a));
  assert(!!gate && flat(ls, gate.condition) === 'arrivalBanner',
    '3c. the banner renders only under `arrivalBanner ?`');
  const d = declOf(ls, 'arrivalBanner');
  assert(!!d && flat(ls, d.initializer) ===
      'arrival && candidatePos === arrival.position && cutAfter != null ? arrival : null',
    '3d. arrivalBanner = the arrival, only while that position\'s split is `shown` (candidatePos + cutAfter)');
  const setters = callsTo(ls, 'setArrival').filter((c) => c.arguments[0] && !/^null$/.test(flat(ls, c.arguments[0])));
  const inSplit = setters[0] && ancestors(setters[0]).find((a) => ts.isIfStatement(a));
  assert(setters.length === 1 && !!inSplit && flat(ls, inSplit.expression) === "intent.kind === 'split'",
    "3e. a banner is set in exactly one place — the `intent.kind === 'split'` branch");
  const clearEffect = callsTo(ls, 'useEffect').find((c) => {
    const deps = c.arguments[1];
    return deps && flat(ls, deps) === '[arrival, subset, posFilter]';
  });
  assert(!!clearEffect && /setArrival\(null\)/.test(flat(ls, clearEffect.arguments[0])),
    '3f. a filter or subset change clears the banner (effect on [arrival, subset, posFilter])');
  const blurClear = callsTo(ls, 'useFocusEffect').find((c) => {
    const cb = c.arguments[0];
    const fn = cb && isCallTo(cb, 'useCallback') ? cb.arguments[0] : null;
    return fn && ts.isArrowFunction(fn) && ts.isArrowFunction(fn.body) &&
      /setArrival\(null\)/.test(flat(ls, fn.body));
  });
  assert(!!blurClear, '3g. blur clears the banner (a useFocusEffect cleanup)');
  const close = byTestId(ls, 'league-summary.arrival-banner.close')[0];
  assert(!!close && attrText(ls, close, 'onPress') === '() => setArrival(null)',
    '3h. the ghost close control clears the banner');
  assert(/Teams above the line are deepest at \$\{arrivalBanner\.position\}\. Tap one to target their players\./.test(read(LS_REL)) &&
      /Teams below the line are shortest at \$\{arrivalBanner\.position\}, shortest last\. Tap one to offer them your players\./.test(read(LS_REL)) &&
      /'Buying' : 'Selling'/.test(read(LS_REL)),
    '3i. the banner copy is verbatim (scope §6.4)');
}

// ═══ 4. The landing scroll ═════════════════════════════════════════════════
// Sabotage caught: Sell and Buy swapped; Buy measuring the page top instead
// of the list; the notifyGuideTargetsMoved wiring lost while adding the
// arrival hook (check-guide-spotlight-tracking rule 12 pins it too).
assert(/arrivalScrollRef\.current = intent\.side === 'sell' \? 'end' : 'list';/.test(consumeText),
  "4a. Sell arms 'end', Buy arms 'list'");
{
  const apply = declOf(ls, 'applyArrivalScroll');
  const t = apply ? flat(ls, apply.initializer) : '';
  assert(/if \(target === 'end'\) \{ scrollRef\.current\?\.scrollToEnd\(/.test(t),
    '4b. Sell → scrollRef.current?.scrollToEnd()');
  assert(/scrollRef\.current\?\.scrollTo\(\{ y: listTopRef\.current/.test(t),
    '4c. Buy → scrollTo({ y: listTop })');
  assert(/selected \|\| ranked\.length === 0\) return;/.test(t),
    '4d. the landing waits for the list (data in, no drill-in open)');
  const list = findAll(ls, (n) => isJsxEl(n) && attrText(ls, n, 'style') === 'styles.list')[0];
  const onLayout = list ? attrText(ls, list, 'onLayout') : '';
  assert(!!onLayout && /listTopRef\.current = e\.nativeEvent\.layout\.y;/.test(onLayout) &&
      /applyArrivalScroll\(\)/.test(onLayout),
    '4e. listTop comes from ONE onLayout on the list container, which also lands a pending Buy');
  const csc = pageScroll ? attrText(ls, pageScroll, 'onContentSizeChange') : '';
  const lay = pageScroll ? attrText(ls, pageScroll, 'onLayout') : '';
  assert(/notifyGuideTargetsMoved\(\)/.test(csc) && /applyArrivalScroll\(\)/.test(csc) &&
      /notifyGuideTargetsMoved\(\)/.test(lay),
    '4f. onContentSizeChange lands a pending Sell AND keeps notifyGuideTargetsMoved');
  assert(/arrivalScrollRef\.current = null/.test(pageScroll ? attrText(ls, pageScroll, 'onScrollBeginDrag') || '' : ''),
    "4g. the user's own drag releases the landing");
  assert(/arrivalScrollRef\.current = null; scrollRef\.current\?\.scrollTo\(\{ y: 0, animated: false \}\);/.test(consumeText),
    "4h. kind 'all' lands on the top and arms nothing");
}

// ═══ 5. The Standings route ════════════════════════════════════════════════
// Sabotage caught: registering under a flag (an in-flight push unmounts on
// revalidation); dropping HeaderBack (native back is dead, RNS#3294); a
// missing or tab-bar-offset FAB, or a second one.
{
  const screens = findAll(nav, (n) => isJsxEl(n) && tagOf(nav, n) === 'Stack.Screen' &&
    attrText(nav, n, 'name') === '"Standings"');
  assert(screens.length === 1 && attrText(nav, screens[0], 'component') === 'StandingsScreen',
    '5a. exactly one root Stack.Screen name="Standings" component={StandingsScreen}');
  assert(/import StandingsScreen from '\.\.\/screens\/StandingsScreen';/.test(navCode),
    '5b. RootNav imports the screen');
  const s = screens[0];
  const chain = [];
  for (let p = s && s.parent; p; p = p.parent) {
    if (isJsxEl(p) && tagOf(nav, p) === 'Stack.Navigator') break;
    chain.push(p);
  }
  assert(!!s && chain.every((p) => !ts.isConditionalExpression(p) &&
      !(ts.isBinaryExpression(p) && [ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken]
        .includes(p.operatorToken.kind))),
    '5c. the route is registered UNCONDITIONALLY (no flag ternary or && around it)');
  const opts = s ? attrText(nav, s, 'options') : '';
  assert(/headerShown: true/.test(opts) && /headerBackVisible: false/.test(opts) &&
      /<HeaderTitle>Standings<\/HeaderTitle>/.test(opts) &&
      /<HeaderBack testID="standings\.back-btn"/.test(opts) &&
      /navigation\.canGoBack\(\) \? navigation\.goBack\(\) : navigation\.navigate\('Main'\)/.test(opts),
    '5d. FreeAgents-style options: explicit HeaderBack standings.back-btn, canGoBack ? goBack : Main');
  assert(/Standings: undefined;/.test(read(NAV_REL)), '5e. RootStackParamList declares Standings (no params)');
  const fabs = findAll(st, (n) => isJsxEl(n) && tagOf(st, n) === 'FeedbackFAB');
  assert(fabs.length === 1 && attrText(st, fabs[0], 'activeScreen') === '"Standings"' &&
      attrText(st, fabs[0], 'aboveTabBar') === 'false',
    '5f. StandingsScreen mounts exactly one <FeedbackFAB activeScreen="Standings" aboveTabBar={false} />');
  assert(fabs.length === 1 && !ancestors(fabs[0]).some((a) => ts.isConditionalExpression(a) ||
      (ts.isBinaryExpression(a) && a.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken)),
    '5g. the FAB sits outside every branch (one mount in every state)');
}

// ═══ 6. The outlook query runs only on Projected ═══════════════════════════
// Sabotage caught: `enabled` losing the segment clause fires the 10,000-sim
// request on every Standings open.
{
  const outlook = callsTo(st, 'useQuery').find((c) =>
    /queryKey: \['league-outlook', leagueId, 'consensus'\]/.test(flat(st, c)));
  const t = outlook ? flat(st, outlook) : '';
  assert(callsTo(st, 'getOutlook').length === 1 && /queryFn: \(\) => getOutlook\(leagueId!, 'consensus'\)/.test(t),
    "6a. one outlook query, on the shared ['league-outlook', leagueId, 'consensus'] key");
  assert(/enabled: segment === 'projected' && oddsEnabled && isSleeper && !!leagueId,/.test(t),
    "6b. enabled = segment === 'projected' && outlook.odds && Sleeper && league");
  // (the printer normalises 60_000 to 60000)
  assert(/staleTime: 60_?000\b/.test(t), '6c. staleTime 60_000');
  const odds = declOf(st, 'oddsEnabled');
  assert(!!odds && flat(st, odds.initializer) === "useFlag('outlook.odds')", "6d. oddsEnabled = useFlag('outlook.odds')");
  assert(/useState<Segment>\('current'\)/.test(stCode), '6e. Current is the default segment');
}

// ═══ 7. standings_segment_changed: a changing tap only ═════════════════════
// Sabotage caught: emitting from an effect (fires on mount and on any
// re-render), or without the no-change guard (re-tap of the active segment).
{
  const tracks = findAll(st, (n) => isCallTo(n, 'track') && n.arguments[0] &&
    ts.isStringLiteral(n.arguments[0]) && n.arguments[0].text === 'standings_segment_changed');
  assert(tracks.length === 1, '7a. exactly one standings_segment_changed emitter');
  const tr = tracks[0];
  assert(!!tr && !enclosingEffect(tr), '7b. the emitter is not inside any effect');
  const fnDecl = tr && ancestors(tr).find((a) => ts.isVariableDeclaration(a));
  assert(!!fnDecl && fnDecl.name.getText(st) === 'selectSegment',
    '7c. the emitter lives in the selectSegment tap handler');
  const body = fnDecl ? flat(st, fnDecl.initializer) : '';
  assert(body.indexOf('if (next === segment) return;') >= 0 &&
      body.indexOf('if (next === segment) return;') < body.indexOf("track('standings_segment_changed'"),
    '7d. a re-tap of the active segment emits nothing');
  assert(!!tr && flat(st, tr) === "track('standings_segment_changed', { segment: next }, 'Standings')",
    "7e. props are exactly {segment} on screen 'Standings' (the taxonomy row)");
  const cur = byTestId(st, 'standings.segment.current')[0];
  const proj = byTestId(st, 'standings.segment.projected')[0];
  assert(!!cur && !!proj && attrText(st, cur, 'onPress') === "() => selectSegment('current')" &&
      attrText(st, proj, 'onPress') === "() => selectSegment('projected')",
    '7f. both segment buttons route through selectSegment');
  assert(!/standings_segment_changed/.test(lsCode), '7g. no other screen emits it');
}

// ═══ 8. Deep link ══════════════════════════════════════════════════════════
{
  const at = dlText.indexOf("Standings: 'app/league/standings',");
  const main = dlText.indexOf('Main: {');
  assert(at > 0 && at < main,
    "8a. deepLinks.ts maps Standings → 'app/league/standings' at the ROOT of the table (not under Main)");
}

// ═══ 9. Season-outlook calibration, wherever the renderer lives ════════════
// The renderer stays in LeagueSummaryScreen (check-outlook-bands.js pins
// playoffBand + its thresholds THERE); Standings imports it rather than
// re-drawing it. Sabotage caught: a local copy in Standings that renders a
// percentage, title odds, or records during beta.
{
  assert(/import \{ SeasonOutlookSection, OutlookUnsupportedRow \} from '\.\/LeagueSummaryScreen';/.test(stCode),
    '9a. StandingsScreen imports SeasonOutlookSection + OutlookUnsupportedRow from LeagueSummaryScreen');
  const localCopy = findAll(st, (n) => ts.isFunctionDeclaration(n) && n.name &&
    /^(SeasonOutlookSection|OutlookRow|OutlookUnsupportedRow|OutlookStrip|playoffBand|orderOutlookTeams|roundedPct)$/.test(n.name.text));
  assert(localCopy.length === 0 && findAll(st, (n) => isJsxEl(n) && tagOf(st, n) === 'SeasonOutlookSection').length === 1 &&
      findAll(st, (n) => isJsxEl(n) && tagOf(st, n) === 'OutlookUnsupportedRow').length === 1,
    '9b. Standings renders the shared section and unsupported row, and defines no outlook renderer of its own');
  assert(!/title_pct|playoff_pct|projected_wins|projected_seed/.test(stCode),
    '9c. StandingsScreen reads no odds field itself');
  const pctLits = findAll(st, (n) => (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) ||
    ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n) || ts.isJsxText(n)) && /%/.test(n.text));
  assert(pctLits.length === 0, '9d. StandingsScreen renders no percentage');
  assert(/export function SeasonOutlookSection\(/.test(lsCode) && /export function OutlookUnsupportedRow\(/.test(lsCode),
    '9e. the shared renderers are exported from LeagueSummaryScreen');
  const fn = (name) => findAll(ls, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === name)[0];
  const section = fn('SeasonOutlookSection');
  const row = fn('OutlookRow');
  assert(!!section && /const showRecords = !meta\.beta;/.test(flat(ls, section)),
    '9f. records show only once meta.beta clears (showRecords = !meta.beta)');
  assert(!!row && /const asPercent = OUTLOOK_WEEK6_PERCENT_ENABLED && showRecord;/.test(flat(ls, row)) &&
      /\{showRecord \? \(/.test(flat(ls, row)),
    '9g. OutlookRow gates records on showRecord and the percentage on the off switch AND showRecord');
  assert(/const OUTLOOK_WEEK6_PERCENT_ENABLED = false;/.test(lsCode), '9h. the week-6 percentage stays OFF');
  assert(!/title_pct/.test(lsCode), '9i. no title odds read anywhere in LeagueSummaryScreen');
  const rendererPct = [section, row, fn('OutlookUnsupportedRow')].filter(Boolean).some((f) =>
    findAll(f, (n) => (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) ||
      ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n) || ts.isJsxText(n)) &&
      /%/.test(n.text)).length > 0);
  assert(!rendererPct, '9j. no % literal inside the shared renderers (bands, not percentages)');
  const ids = ['league-summary.odds.section', 'league-summary.odds.beta-ribbon', 'league-summary.odds.source',
    'league-summary.odds.cutline', 'league-summary.odds.coverage-note', 'league-summary.odds.unsupported'];
  const lsText = read(LS_REL);
  assert(ids.every((id) => lsText.includes(`testID="${id}"`)) &&
      lsText.includes('testID={`league-summary.odds.row.${team.roster_id}`}') &&
      lsText.includes('testID={`league-summary.odds.band.${team.roster_id}`}'),
    '9k. the league-summary.odds.* testIDs are unchanged');
}

// ═══ 10. Roster / user queries ═════════════════════════════════════════════
// Same S-2 rule check-session-seed.js applies to the other consumers: below
// 5 minutes, refetchOnMount discards the session-init seed.
{
  const stText = read(ST_REL);
  for (const [key, fetcher] of [['league-rosters', 'getLeagueRosters'], ['league-users', 'getLeagueUsers']]) {
    const block = new RegExp(`queryKey: \\['${key}', leagueId\\][\\s\\S]{0,400}?\\n  \\}\\);`).exec(stText);
    const b = block ? block[0] : '';
    assert(/staleTime:\s*5\s*\*\s*60_000/.test(b), `10a. ['${key}'] keeps staleTime: 5 * 60_000`);
    assert(new RegExp(`queryFn: \\(\\) => ${fetcher}\\(leagueId!\\),`).test(b), `10b. ['${key}'] uses the bare ${fetcher} fetcher`);
    assert(/enabled: isSleeper && !!leagueId,/.test(b), `10c. ['${key}'] is Sleeper-gated`);
  }
  const plat = declOf(st, 'platform');
  const sl = declOf(st, 'isSleeper');
  assert(!!plat && /\?\? 'sleeper'$/.test(flat(st, plat.initializer)) && /s\.leagues\.find\(\(l\) => l\.league_id === leagueId\)\?\.platform/.test(flat(st, plat.initializer)) &&
      !!sl && flat(st, sl.initializer) === "platform === 'sleeper'",
    "10d. isSleeper is League Summary's rule (unknown platform resolves to Sleeper)");
  assert(/findMyRoster\(rosters, userId\)\?\.roster_id/.test(stCode) && !/owner_id ===|co_owners/.test(stCode),
    '10e. "you" comes from findMyRoster (the co-owner rule is not re-implemented)');
  assert(/currentStandings\(/.test(stCode) && !/\.sort\(/.test(stCode),
    '10f. standings come from utils/standings (no local ordering arithmetic)');
}

// ═══ 11. testIDs + Chalkline ═══════════════════════════════════════════════
{
  const stText = read(ST_REL);
  for (const id of ['standings.screen', 'standings.segment.current', 'standings.segment.projected',
    'standings.current.table', 'standings.current.unavailable']) {
    assert(stText.includes(`testID="${id}"`), `11a. testID ${id} is a static literal in StandingsScreen`);
  }
  assert(read(NAV_REL).includes('testID="standings.back-btn"'), '11b. testID standings.back-btn in RootNav');
  assert(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(stCode), '11c. StandingsScreen has no hex or rgba literals');
  assert(/import Text from '\.\.\/components\/chalkline\/Text';/.test(stCode) &&
      !/import \{[^}]*\bText\b[^}]*\} from 'react-native'/.test(stCode),
    '11d. StandingsScreen text goes through chalkline Text');
  const bannerStyles = (read(LS_REL).match(/arrivalPin: \{[\s\S]*?arrivalClose: \{[\s\S]*?\n  \},/) || [''])[0];
  assert(!!bannerStyles && !/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(bannerStyles) && !/borderRadius: (?!radii\.)/.test(bannerStyles),
    '11e. the banner styles use tokens only (no hex, radii from the scale)');
}

console.log(`\ncheck-home-destinations: ${passes} passed, ${failures} failed`);
if (failures) process.exit(1);
console.log('All home-destinations checks passed.');
