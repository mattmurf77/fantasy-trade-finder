#!/usr/bin/env node
// Home position tile body tap (flag `nav.home_position_roster`, D-269;
// docs/plans/position-tile-tap/scope.md).
//
// Tapping the BODY of a Home hub position tile opens League rankings with
// the filter at exactly that position (Consensus, All, no banner) and the
// user's OWN team drilled in, landing so their players at that position are
// on screen, with a header "Home" control back for that arrival only.
//
// No simulator (D-056): this file is the structural guard and executes the
// pure pieces (the tile's VoiceOver label, the landing offset). Each section
// names the regression it catches. Assertions read COMMENT-STRIPPED code.
//
// Run: node tests/check-position-tile-tap.js   (npm run test:position-tile-tap)
'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const REPO = path.join(MOBILE, '..');
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
const isJsxEl = (n) => ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n);
const opening = (n) => (ts.isJsxElement(n) ? n.openingElement : n);
const tagOf = (sf, n) => opening(n).tagName.getText(sf);
const attrText = (sf, n, name) => {
  const a = opening(n).attributes.properties.find(
    (p) => ts.isJsxAttribute(p) && p.name.getText() === name,
  );
  if (!a || !a.initializer) return null;
  const init = a.initializer;
  return ts.isJsxExpression(init) && init.expression ? flat(sf, init.expression) : flat(sf, init);
};
function ancestors(node) {
  const out = [];
  for (let p = node.parent; p; p = p.parent) out.push(p);
  return out;
}
const declOf = (sf, name) =>
  findAll(sf, (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name)[0];
const fnDecl = (sf, name) =>
  findAll(sf, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === name)[0];
/** Transpile a TS snippet to CommonJS JS and evaluate it with `scope`. */
function run(src, scope, ret) {
  const js = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 } }).outputText;
  // eslint-disable-next-line no-new-func
  return new Function(...Object.keys(scope), `${js}\nreturn (${ret});`)(...Object.values(scope));
}

const TILE_REL = 'src/components/home/PositionTile.tsx';
const HUB_REL = 'src/components/home/HomeHub.tsx';
const LS_REL = 'src/screens/LeagueSummaryScreen.tsx';
const INTENT_REL = 'src/state/leagueSummaryIntent.ts';

const tile = parse(TILE_REL);
const tileCode = code(tile);
const hub = parse(HUB_REL);
const hubCode = code(hub);
const ls = parse(LS_REL);
const lsCode = code(ls);
const intentCode = code(parse(INTENT_REL)).replace(/\s+/g, ' ');

// ═══ 1. The intent ═════════════════════════════════════════════════════════
// Sabotage caught: the body tap riding the 'split' kind (a Buy/Sell banner
// and a list landing nobody asked for).
assert(/\{ kind: 'roster'; leagueId: string; position: SplitPos; seq: number; \}/.test(intentCode) &&
    /\{ kind: 'roster'; leagueId: string; position: SplitPos; \}/.test(intentCode),
  "1a. the intent store has a 'roster' kind {leagueId, position} (+ store-stamped seq)");
assert(/export function requestLeagueSummaryRoster\(leagueId: string, position: SplitPos\): void \{\s*useLeagueSummaryIntent\.getState\(\)\.set\(\{ kind: 'roster', leagueId, position \}\);/.test(intentCode),
  "1b. requestLeagueSummaryRoster writes kind 'roster'");

// ═══ 2. The tile ═══════════════════════════════════════════════════════════
// Sabotage caught: wrapping Buy/Sell inside the pressable (a nested control
// VoiceOver cannot reach); a pressable body while loading; a template testID
// testid-lint cannot see; the body pressable rendered with the flag off.
{
  const opens = findAll(tile, (n) => isJsxEl(n) && attrText(tile, n, 'testID') === 'ids.open');
  assert(opens.length === 1 && tagOf(tile, opens[0]) === 'Pressable',
    '2a. exactly one body Pressable, testID={ids.open}');
  const open = opens[0];
  const inner = open ? findAll(open, (n) => isJsxEl(n) && tagOf(tile, n) === 'SideButton') : [];
  assert(!!open && inner.length === 0, '2b. no Buy / Sell / See P ranking button inside the body pressable');
  const actions = findAll(tile, (n) => isJsxEl(n) && attrText(tile, n, 'style') === 'styles.actions')[0];
  assert(!!open && !!actions && !ancestors(actions).includes(open) && !ancestors(open).includes(actions),
    '2c. the body pressable and the actions row are siblings, neither inside the other');
  const gate = open && ancestors(open).find((a) => ts.isConditionalExpression(a));
  assert(!!gate && flat(tile, gate.condition) === 'onOpen && split != null' &&
      flat(tile, gate.whenFalse).replace(/[()\s]/g, '') === 'body',
    '2d. pressable only with onOpen AND a loaded split; otherwise the same body, unwrapped');
  const tileText = read(TILE_REL);
  for (const p of ['qb', 'rb', 'wr', 'te']) {
    assert(tileText.includes(`open: 'home.position.${p}.open',`), `2e. static literal testID home.position.${p}.open`);
  }
  assert(open && attrText(tile, open, 'accessibilityRole') === '"button"' &&
      attrText(tile, open, 'accessibilityLabel') === 'openLabel(pos, split)' &&
      attrText(tile, open, 'onPress') === 'onOpen',
    '2f. role button, label openLabel(pos, split), onPress onOpen');
  assert(open && attrText(tile, open, 'style') === '({ pressed }) => [styles.body, pressed && styles.bodyPressed]' &&
      /bodyPressed: \{ backgroundColor: ink\.ink3 \}/.test(tileCode),
    '2g. pressed state is the Chalkline --ink-3 fill');
  // 44pt: the body holds the label row, rank, value, median and meter; its
  // style reaches into the tile padding so the press area is the full top.
  assert(/marginTop: -\(space\.md - RAIL\)/.test(tileCode) && /paddingTop: space\.md - RAIL/.test(tileCode) &&
      /marginHorizontal: -space\.sm/.test(tileCode),
    '2h. the body reaches the tile edges and starts below the rail (content unmoved)');
  // Execute the label.
  const lbl = fnDecl(tile, 'openLabel');
  let f = null;
  try {
    f = lbl && run(lbl.getText(tile), { ordinal: (n) => `${n}${n === 1 ? 'st' : n === 2 ? 'nd' : n === 3 ? 'rd' : 'th'}` }, 'openLabel');
  } catch (e) { /* reported below */ }
  const shown = f && f('QB', { state: 'shown', teamCount: 12, you: { rank: 3 } });
  const noSplit = f && f('TE', { state: 'no_split', teamCount: 12, you: { rank: 5 } });
  assert(shown === 'Your QBs, 3rd of 12. Opens your roster in League rankings.',
    '2i. label for a shown tile: "Your QBs, 3rd of 12. Opens your roster in League rankings."', `got ${shown}`);
  assert(noSplit === 'Your TEs. Opens your roster in League rankings.',
    '2j. a "No clear split" tile states no rank (it shows none)', `got ${noSplit}`);
}

// ═══ 3. The hub ════════════════════════════════════════════════════════════
// Sabotage caught: the flag not read (no kill switch); tracking after the
// navigate; the loading grid getting a handler.
{
  assert(/const tileRosterOn = useFlag\('nav\.home_position_roster'\);/.test(hubCode),
    "3a. the hub reads useFlag('nav.home_position_roster')");
  assert(/onOpen=\{tileRosterOn \? \(\) => onOpenRoster\(s\) : undefined\}/.test(hubCode),
    '3b. each loaded tile gets onOpen only while the flag is on (off ⇒ undefined ⇒ tile unchanged)');
  assert(/<PositionTile key=\{p\} pos=\{p\} split=\{null\}\s*\/>/.test(hubCode),
    '3c. the loading grid passes no onOpen');
  const h = declOf(hub, 'onOpenRoster');
  const t = h ? flat(hub, h.initializer) : '';
  const iTrack = t.indexOf("track('home_tile_tapped', { tile: 'position_roster', position: s.position, band: bandProp(s), split: s.state }, 'Home');");
  const iReq = t.indexOf('requestLeagueSummaryRoster(leagueId!, s.position);');
  const iNav = t.indexOf("navigation.navigate('League', { screen: 'LeagueRankings' });");
  assert(iTrack >= 0 && iTrack < iReq && iReq < iNav,
    "3d. onOpenRoster: track position_roster (position, band, split) → roster intent → League rankings");
  assert(!/requestLeagueSummaryRoster/.test(t.replace('requestLeagueSummaryRoster(leagueId!, s.position);', '')) &&
      (hubCode.match(/requestLeagueSummaryRoster\(/g) || []).length === 1,
    '3e. exactly one roster-intent writer');
  assert(/onBuy=\{\(\) => onBuy\(s\)\}/.test(hubCode) && /onSell=\{\(\) => onSell\(s\)\}/.test(hubCode) &&
      /requestLeagueSummarySplit\(leagueId!, s\.position, 'buy'\)/.test(hubCode) &&
      /requestLeagueSummarySplit\(leagueId!, s\.position, 'sell'\)/.test(hubCode),
    '3f. Buy / Sell keep their split arrivals');
}

// ═══ 4. The consume ════════════════════════════════════════════════════════
// Sabotage caught: the roster kind showing the Buy/Sell banner or arming a
// list landing; the consume selecting a team itself (no league_team_opened).
const consume = callsTo(ls, 'takeLeagueSummaryIntent')[0];
const consumeFn = consume && ancestors(consume).find((a) => ts.isArrowFunction(a));
const consumeText = consumeFn ? flat(ls, consumeFn) : '';
{
  const branch = findAll(ls, (n) => ts.isIfStatement(n) && flat(ls, n.expression) === "intent.kind === 'roster'")[0];
  const b = branch ? flat(ls, branch.thenStatement) : '';
  assert(!!branch && consumeFn && ancestors(branch).includes(consumeFn),
    "4a. the consume has an `intent.kind === 'roster'` branch");
  assert(/setPosFilter\(new Set<FilterKey>\(\[intent\.position\]\)\);/.test(b) &&
      /setArrival\(null\);/.test(b) && /arrivalScrollRef\.current = null;/.test(b) &&
      /setOwnArrival\(intent\.seq\);/.test(b),
    '4b. roster: filter {position}, no banner, no list landing, own-team open queued by seq');
  assert(/setBasis\('consensus'\);/.test(consumeText) && /setSubset\('all'\);/.test(consumeText) &&
      consumeText.indexOf('filterSigRef.current = ') < consumeText.indexOf("intent.kind === 'roster'"),
    "4c. the shared reset (auto-exit re-armed, Consensus, All) runs before the roster branch");
  assert(!/setSelectedId|openTeam\(|track\(/.test(consumeText),
    '4d. the consume opens nothing and emits nothing itself');
}

// ═══ 5. The own-team open ══════════════════════════════════════════════════
// Sabotage caught: a bare setSelectedId (no league_team_opened); opening
// before the data lands; opening some other team; declaring the open before
// the filter auto-exit (the same commit would eject the new drill-in); a
// crash or a phantom drill-in when the user's team is not ranked.
{
  const eff = callsTo(ls, 'useEffect').find((c) => /if \(ownArrival == null\) return;/.test(flat(ls, c.arguments[0])));
  const t = eff ? flat(ls, eff.arguments[0]) : '';
  assert(!!eff, '5a. one effect owns the own-team open');
  const iWait = t.indexOf('if (!query.isFetched && !query.isError) return;');
  const iClear = t.indexOf('setOwnArrival(null);');
  const iNone = t.indexOf('if (!myEntry) { scrollRef.current?.scrollTo({ y: 0, animated: false }); return; }');
  const iOpen = t.indexOf("openTeam(id, 'home_tile', ranked.indexOf(myEntry) + 1);");
  assert(iWait > 0 && iWait < iClear && iClear < iNone && iNone < iOpen,
    "5b. waits for data, consumes once, no own team ⇒ filtered list at the top with no drill-in, else openTeam(own id, 'home_tile', on-screen rank)");
  assert(/const id = myEntry\.tc\.team\.user_id;/.test(t) && /setHomeBackId\(id\);/.test(t) && /ownLandRef\.current = true;/.test(t),
    '5c. the opened team is the is_you row; it arms the landing and the Home control');
  const me = declOf(ls, 'myEntry');
  assert(!!me && /ranked\.find\(\(r\) => r\.tc\.team\.is_you\) \?\? null/.test(flat(ls, me.initializer)),
    '5d. "own team" is the screen\'s existing myEntry (is_you)');
  const sigEff = callsTo(ls, 'useEffect').find((c) => /closeTeam\('filter_change'\)/.test(flat(ls, c.arguments[0])));
  assert(!!sigEff && !!eff && sigEff.getStart(ls) < eff.getStart(ls),
    '5e. declared AFTER the filter auto-exit (an older drill-in closes first, this one survives)');
  assert(/const openTeam = \(id: string, via: 'bar' \| 'row' \| 'home_tile', rank: number\) =>/.test(lsCode),
    "5f. openTeam's via admits 'home_tile' (league_team_opened.via)");
  assert((lsCode.match(/setSelectedId\(/g) || []).length === 2 && (lsCode.match(/setSelectedId\(null\)/g) || []).length === 1,
    '5g. still only openTeam and closeTeam set the selection (no new setSelectedId)');
}

// ═══ 6. The landing ════════════════════════════════════════════════════════
// Sabotage caught: scrolling past the roster panel's top (the All control
// and the position header leave the screen); never releasing on a drag;
// not measuring the panel.
{
  const a = declOf(ls, 'applyOwnLanding');
  const t = a ? flat(ls, a.initializer) : '';
  assert(/if \(!ownLandRef\.current \|\| !selected\) return;/.test(t) &&
      /const rosterBottom = panelY \+ list\.y \+ list\.h;/.test(t) &&
      /const y = Math\.max\(0, Math\.min\(panelY, rosterBottom - viewH\)\);/.test(t),
    '6a. the landing: no scroll when the roster fits, else just enough, never past the panel top');
  // Execute the offset rule.
  const land = (panelY, listY, listH, viewH) => Math.max(0, Math.min(panelY, panelY + listY + listH - viewH));
  assert(land(500, 110, 120, 800) === 0, '6b. three QB rows that fit on a large phone ⇒ no scroll');
  assert(land(560, 110, 120, 600) === 190, '6c. a small phone ⇒ scrolls just enough to end on the roster');
  assert(land(560, 110, 900, 600) === 560, '6d. a long roster ⇒ the panel top (All control + header) is the top');
  const page = findAll(ls, (n) => isJsxEl(n) && tagOf(ls, n) === 'ScrollView' && attrText(ls, n, 'onScroll') === 'notifyGuideTargetsMoved')[0];
  const lay = page ? attrText(ls, page, 'onLayout') : '';
  const csc = page ? attrText(ls, page, 'onContentSizeChange') : '';
  const drag = page ? attrText(ls, page, 'onScrollBeginDrag') : '';
  assert(/viewportHRef\.current = e\.nativeEvent\.layout\.height;/.test(lay) && /applyOwnLanding\(\)/.test(lay) &&
      /applyOwnLanding\(\)/.test(csc) && /notifyGuideTargetsMoved\(\)/.test(lay) && /notifyGuideTargetsMoved\(\)/.test(csc),
    '6e. the page measures its viewport and re-lands on layout / content changes (guide notify kept)');
  assert(/ownLandRef\.current = false/.test(drag || '') && /arrivalScrollRef\.current = null/.test(drag || ''),
    "6f. the user's drag releases both landings");
  const panel = findAll(ls, (n) => isJsxEl(n) && attrText(ls, n, 'style') === 'styles.drillPanel')[0];
  const list = findAll(ls, (n) => isJsxEl(n) && attrText(ls, n, 'style') === 'styles.drillList')[0];
  assert(!!panel && /drillPanelYRef\.current = e\.nativeEvent\.layout\.y;/.test(attrText(ls, panel, 'onLayout') || '') &&
      !!list && /drillListRef\.current = \{ y: e\.nativeEvent\.layout\.y, h: e\.nativeEvent\.layout\.height, \};?/.test(attrText(ls, list, 'onLayout') || ''),
    '6g. the drill panel and its roster list report their layout');
}

// ═══ 7. The Home control ═══════════════════════════════════════════════════
// Sabotage caught: the control on a normal League visit; surviving a blur
// or "All teams"; a second back control on the legacy root push; leaving
// without the close event.
{
  const show = declOf(ls, 'showHomeBack');
  assert(!!show && flat(ls, show.initializer) === 'isTabRoot && homeBackId != null && selectedId === homeBackId',
    '7a. shown only on the tab root, for the drill-in the tile arrival opened');
  const sets = callsTo(ls, 'setHomeBackId');
  const nonNull = sets.filter((c) => flat(ls, c.arguments[0]) !== 'null');
  assert(nonNull.length === 1 && flat(ls, nonNull[0].arguments[0]) === 'id',
    '7b. set in exactly one place (the arrival open), so a normal League visit never shows it');
  const clr = callsTo(ls, 'useEffect').find((c) => c.arguments[1] && flat(ls, c.arguments[1]) === '[homeBackId, selectedId]');
  assert(!!clr && /if \(homeBackId && selectedId !== homeBackId\) \{ setHomeBackId\(null\);/.test(flat(ls, clr.arguments[0])),
    '7c. cleared once the drill-in it opened ends (All teams, filter change, other team, re-tap)');
  const blur = callsTo(ls, 'useFocusEffect').find((c) => /setHomeBackId\(null\)/.test(flat(ls, c.arguments[0])));
  const bfn = blur && blur.arguments[0].arguments[0];
  assert(!!bfn && ts.isArrowFunction(bfn) && ts.isArrowFunction(bfn.body),
    '7d. cleared on blur (a useFocusEffect cleanup): coming back to League on your own shows none');
  const back = declOf(ls, 'backToHome');
  const bt = back ? flat(ls, back.initializer) : '';
  assert(bt.indexOf("closeTeam('home_back');") >= 0 && bt.indexOf("closeTeam('home_back');") < bt.indexOf("navigation.navigate('Home');"),
    "7e. one tap: closeTeam('home_back') (league_team_closed) then the Home tab");
  assert(/\| 'home_back'/.test(lsCode) && /\|\s*'filter_change';/.test(read(LS_REL)),
    "7f. 'home_back' is a CloseVia value ('filter_change' stays last)");
  const ctl = findAll(ls, (n) => isJsxEl(n) && attrText(ls, n, 'testID') === '"league-summary.back-home"');
  assert(ctl.length === 1 && attrText(ls, ctl[0], 'onPress') === 'backToHome' &&
      attrText(ls, ctl[0], 'accessibilityLabel') === '"Back to Home"' &&
      attrText(ls, ctl[0], 'accessibilityRole') === '"button"',
    '7g. one static-testID control, league-summary.back-home, label "Back to Home"');
  assert(ctl.length === 1 && attrText(ls, ctl[0], 'style') === '({ pressed }) => [styles.headerBack, pressed && { opacity: 0.6 }]' &&
      /<Text style=\{styles\.headerBackText\}>Home<\/Text>/.test(flat(ls, ctl[0])),
    '7h. it reuses the header back construction (styles.headerBack / headerBackText), visible text "Home"');
  const cond = ctl[0] && ancestors(ctl[0]).find((a) => ts.isConditionalExpression(a));
  const prop = ctl[0] && ancestors(ctl[0]).find((a) => ts.isPropertyAssignment(a));
  assert(!!cond && flat(ls, cond.condition) === 'showHomeBack' && !!prop && prop.name.getText(ls) === 'headerRight',
    '7i. it is the header RIGHT, only under showHomeBack (the left stays "All teams")');
  assert(/headerLeft: undefined,\s+headerRight: undefined,/.test(lsCode),
    '7j. the unfocused header clears headerRight too');
  assert(/testID="league-summary\.roster-close"\s+onPress=\{\(\) => closeTeam\('header_back'\)\}/.test(read(LS_REL)),
    '7k. "All teams" is unchanged');
}

// ═══ 8. Flag + analytics registration ══════════════════════════════════════
{
  const cfg = JSON.parse(fs.readFileSync(path.join(REPO, 'config/features.json'), 'utf8'));
  assert(cfg['nav.home_position_roster'] === true, '8a. config/features.json ships the flag true');
  const flags = read('src/state/useFeatureFlags.ts');
  assert(/'nav\.home_position_roster': true,/.test(flags), '8b. the compiled default matches config (true)');
  const ffPy = fs.readFileSync(path.join(REPO, 'backend/feature_flags.py'), 'utf8');
  assert(/\n    "nav\.home_position_roster",\n/.test(ffPy), '8c. registered in backend FLAG_KEYS (code default False)');
  const tax = fs.readFileSync(path.join(REPO, 'backend/analytics_taxonomy.py'), 'utf8');
  assert(/"home_tile_tapped":\s+frozenset\(\{"tile", "position", "band", "split"\}\)/.test(tax),
    '8d. home_tile_tapped admits `split`');
}

console.log(`\ncheck-position-tile-tap: ${passes} passed, ${failures} failed`);
if (failures) process.exit(1);
console.log('All position-tile-tap checks passed.');
