#!/usr/bin/env node
// The playoff card's half sheet (flag `league.direction_view_sheet`, cell C;
// spec docs/plans/league-projections/direction-pages/spec.md §5.6, §7.3, §9,
// §10.1; D-265, D-270: the first Home update to ship).
//
// RENDERS the real HomePlayoffBanner against host stubs (tests/
// direction-card-harness.js) and EXECUTES utils/directionCard and both
// hosts' tap handlers: no button row while the sheet is on (S-1); "View"
// opens the sheet and the percentage still opens Standings (S-2); the row
// order (S-3); enabled, disabled and unlisted rows with the spec's own
// reason lines (S-4 to S-6); every way of closing (S-7); the sheet pattern
// (S-8); it reads nothing (S-9); it opens with nothing offered (S-10); and
// where each row goes, with `home_tile_tapped {tile, via}`.
//
// Run: node tests/check-direction-sheet.js
'use strict';

const ts = require('typescript');
const h = require('./direction-card-harness');
const { check, mount, render, byId, byType, words, block, forecast, state, cardUtil: u, cardCopy, props, read, readRoot, strip } = h;

const K = cardCopy.DIRECTION_CARD_COPY;
const sheetRaw = read('src/components/home/DirectionSheet.tsx');
const sheetSrc = strip(sheetRaw);
const bannerSrc = strip(read('src/components/home/HomePlayoffBanner.tsx'));
const hub = read('src/components/home/HomeHub.tsx');
const spec = readRoot('docs/plans/league-projections/direction-pages/spec.md');
const view = (b, p, st) => Object.assign(forecast(p, st), { team_direction: b });
const sheetNode = (tree) => byType(tree, 'DirectionSheet')[0];
const keys = (rows) => rows.map((r) => r.key).join(',');
const NOT = (reason) => ({ offered: false, reason });
const YES = { offered: true, reason: null };

// ═══ S-1. No button row while the sheet is on ══════════════════════════════
for (const band of ['low', 'middle', 'high', null]) {
  for (const primary of ['playoffs', 'draft_pick', null]) {
    const tree = mount(view(block({ band, primary })));
    check(byType(tree, 'Button').length === 0 && !words(tree).some((w) => /Improve/.test(w)),
      `S-1. band ${band}, primary ${primary}: no button row on the card`);
  }
}
check(!/direction_both_middle/.test(bannerSrc + read('src/utils/directionCard.ts')), 'S-1b. league.direction_both_middle is not read (deferred, D-270)');

// ═══ S-2. "View" opens the sheet; the percentage still opens Standings ═════
{
  let tree = mount(view(block()));
  const v = byId(tree, 'home.playoff.view');
  check(sheetNode(tree) && sheetNode(tree).props.visible === false, 'S-2a. the sheet is mounted closed');
  check(v.props.onPress !== props.onDetails && v.props.accessibilityRole === 'button' && v.props.accessibilityLabel === K['SHEET.label'],
    'S-2b. "View" is a button that opens the sheet, not the Standings link');
  v.props.onPress(); tree = render();
  check(sheetNode(tree).props.visible === true, 'S-2c. tapping "View" opens the sheet');
  check(JSON.stringify(state.calls) === JSON.stringify([{ tile: 'playoff_options', via: 'card' }]),
    'S-2d. the tap that opens it is home_tile_tapped playoff_options, via card; nothing navigates');
  state.calls.length = 0;
  byId(tree, 'home.playoff.details').props.onPress();
  check(JSON.stringify(state.calls) === '["details"]', 'S-2e. the percentage still opens Standings directly');
  // The sheet also needs the pages flag (its rows open the pages) and the card flag.
  for (const off of ['league.direction_pages', 'league.direction_card', 'league.direction_view_sheet']) {
    tree = mount(view(block()), { [off]: false });
    check(byId(tree, 'home.playoff.view').props.onPress === props.onDetails && !sheetNode(tree),
      `S-2f. ${off} off: "View" opens Standings as today, no sheet`);
  }
}

// ═══ S-3. Three rows, the same order for every team ═══════════════════════
{
  let ok = true;
  for (const band of ['low', 'middle', 'high']) {
    for (const primary of ['playoffs', 'draft_pick', null]) {
      ok = ok && keys(u.sheetRows(block({ band, primary }))) === 'standings,playoffs,draft_pick';
    }
  }
  check(ok && JSON.stringify(u.SHEET_ORDER) === '["standings","playoffs","draft_pick"]', 'S-3a. standings, playoffs, draft pick, for every band and primary');
  const rows = u.sheetRows(block());
  check(rows.map((r) => r.label).join(' | ') === 'View projected standings | Improve Playoff Chances | Improve Draft Pick'
      && ['View projected standings', 'Improve Playoff Chances', 'Improve Draft Pick'].every((s) => spec.includes(`"${s}"`)),
    'S-3b. the spec\'s three labels, shared with the pages\' copy');
  const tree = mount(view(block()));
  check(sheetNode(tree).props.rows.map((r) => r.key).join(',') === 'standings,playoffs,draft_pick', 'S-3c. the card hands the sheet those rows');
}

// ═══ S-4 to S-6. Enabled, disabled and unlisted rows ══════════════════════
{
  const both = u.sheetRows(block());
  check(both.every((r) => r.enabled && r.note === null), 'S-4/S-5. offered directions and standings: enabled, no line');
  // The spec's §7.3 table, parsed: every disabled line is the spec's own.
  const table = {};
  for (const m of spec.matchAll(/^\| `([a-z_]+)` \| [^|]+ \| "([^"]+)" \|$/gm)) table[m[1]] = m[2];
  const reasons = Object.keys(table);
  check(reasons.length === 11 && /`feature_off` \| either \| \(row not listed\)/.test(spec), 'S-6a. the spec lists eleven reason lines and feature_off');
  for (const reason of reasons) {
    const b = block({ projected_pick: { label: '1.04', slot: 4, owns_own_pick: false, owner_name: '[Team]' },
      options: { playoffs: NOT(reason), draft_pick: NOT(reason) } });
    const rows = u.sheetRows(b);
    check(rows.length === 3 && !rows[1].enabled && !rows[2].enabled && rows[1].note === table[reason] && rows[2].note === table[reason],
      `S-6b. ${reason}: disabled, "${table[reason]}"`, `${rows[1].note}`);
  }
  const named = u.sheetRows(block({ projected_pick: { label: '1.04', slot: 4, owns_own_pick: false, owner_name: 'Rivals FC' },
    options: { playoffs: YES, draft_pick: NOT('pick_owned_elsewhere') } }));
  check(named[2].note === 'Rivals FC owns your first-round pick.', 'S-6c. the owner\'s name fills the line');
  check(u.sheetRows(block({ options: { playoffs: NOT('brand_new_reason'), draft_pick: NOT(null) } })).slice(1).every((r) => r.note === 'Not available right now.')
      && spec.includes('An unknown reason uses "Not available right now."'), 'S-6d. an unknown or missing reason: "Not available right now."');
  check(keys(u.sheetRows(block({ options: { playoffs: NOT('feature_off'), draft_pick: YES } }))) === 'standings,draft_pick'
      && keys(u.sheetRows(block({ options: { playoffs: YES, draft_pick: NOT('feature_off') } }))) === 'standings,playoffs'
      && keys(u.sheetRows(block({ options: { playoffs: NOT('feature_off'), draft_pick: NOT('feature_off') } }))) === 'standings',
    'S-6e. a direction whose feature flag is off is not listed');
  check(!/useFlag|max_pf_moves|playoff_targets/.test(read('src/utils/directionCard.ts').replace(/^\s*\/\/.*$/gm, '')),
    'S-6f. the rows come from the server\'s options alone: no flag or feature block is read');
  // The rendered rows: a disabled row is a disabled button that says why.
  const rowSrc = (/\{rows\.map\(\(row, i\) => \([\s\S]*?\n {10}\)\)\}/.exec(sheetSrc) || [''])[0];
  check(/disabled=\{!row\.enabled\}/.test(rowSrc) && /accessibilityState=\{\{ disabled: !row\.enabled \}\}/.test(rowSrc)
      && /accessibilityLabel=\{row\.note \? `\$\{row\.label\}\. \$\{row\.note\}` : row\.label\}/.test(rowSrc)
      && /\{row\.note \? <Text testID=\{NOTE_ID\[row\.key\]\}/.test(rowSrc), 'S-6g. disabled rows cannot be pressed, are announced disabled, and show their line');
}

// ═══ S-7. Closing ══════════════════════════════════════════════════════════
{
  let tree = mount(view(block()));
  byId(tree, 'home.playoff.view').props.onPress(); tree = render();
  state.calls.length = 0;
  sheetNode(tree).props.onClose(); tree = render();
  check(sheetNode(tree).props.visible === false && state.calls.length === 0, 'S-7a. closing without choosing changes nothing');
  byId(tree, 'home.playoff.view').props.onPress(); tree = render();
  state.calls.length = 0;
  const pickRow = sheetNode(tree).props.rows.find((r) => r.key === 'draft_pick');
  sheetNode(tree).props.onChoose(pickRow); tree = render();
  check(sheetNode(tree).props.visible === false && JSON.stringify(state.calls) === JSON.stringify([{ tile: 'improve_pick', via: 'sheet' }]),
    'S-7b. a row tap closes the sheet, then hands the tap on (improve_pick, via sheet)');
  check(/onRequestClose=\{onClose\}/.test(sheetSrc), 'S-7c. the system back gesture (Android back) closes it');
  check(/testID="home\.playoff\.sheet\.scrim" style=\{styles\.backdrop\} onPress=\{onClose\}/.test(sheetSrc), 'S-7d. a tap outside it (the scrim) closes it');
  check(/onAccessibilityEscape=\{onClose\}/.test(sheetSrc), 'S-7e. the VoiceOver escape gesture closes it');
  // The drag: execute the responder config with a stubbed PanResponder.
  const rn = { PanResponder: { create: (cfg) => ({ cfg, panHandlers: {} }) } };
  const dragSrc = (/const drag = useMemo\(\(\) => (PanResponder\.create\(\{[\s\S]*?\}\)), \[\]\);/.exec(sheetRaw) || [])[1];
  let closed = 0;
  const cfg = dragSrc && new Function('PanResponder', 'closeRef', 'DRAG_CLOSE_DY', `return ${ts.transpileModule(dragSrc, {}).outputText}`)(
    rn.PanResponder, { current: () => { closed += 1; } }, 48).cfg;
  check(cfg && cfg.onMoveShouldSetPanResponder(null, { dy: 20, dx: 2 }) === true && cfg.onMoveShouldSetPanResponder(null, { dy: 2, dx: 20 }) === false
      && cfg.onMoveShouldSetPanResponder(null, { dy: -20, dx: 0 }) === false, 'S-7f. a mostly downward drag is the sheet\'s; a tap or sideways move is not');
  cfg.onPanResponderRelease(null, { dy: 47 }); const before = closed;
  cfg.onPanResponderRelease(null, { dy: 48 });
  check(before === 0 && closed === 1 && /export const DRAG_CLOSE_DY = 48;/.test(sheetSrc), 'S-7g. a downward drag past 48pt closes it; a shorter one does not');
}

// ═══ S-8. The existing sheet pattern ═══════════════════════════════════════
{
  check(/<Modal visible=\{visible\} transparent animationType=\{reduceMotion \? 'fade' : 'slide'\}/.test(sheetSrc)
      && /const reduceMotion = useReducedMotionSafe\(\);/.test(sheetSrc), 'S-8a. a Modal over a scrim; slide, or fade under Reduce Motion');
  check(/<SafeAreaView edges=\{\['bottom'\]\}>/.test(sheetSrc), 'S-8b. bottom safe-area padding');
  check(/accessibilityViewIsModal/.test(sheetSrc) && /AccessibilityInfo\.setAccessibilityFocus\(node\)/.test(sheetSrc)
      && /ref=\{i === 0 \? firstRef : undefined\}/.test(sheetSrc), 'S-8c. a modal region; VoiceOver focus moves to the first row on open');
  check(/row: \{ minHeight: 44,/.test(sheetSrc) && /accessibilityRole="button"/.test(sheetSrc), 'S-8d. each row a 44pt button');
  check(/backgroundColor: scrim/.test(sheetSrc) && /backgroundColor: ink\.ink2, borderTopLeftRadius: radii\.md, borderTopRightRadius: radii\.md/.test(sheetSrc)
      && /\.\.\.shadowSheet/.test(sheetSrc), 'S-8e. AnchorSheet\'s construction: scrim token, ink-2 panel, radius md, the one sheet shadow');
  check(!/FeedbackFAB/.test(sheetSrc), 'S-8f. a sheet mounts no feedback button');
  check(!/#[0-9a-fA-F]{3,8}\b|rgba?\(|flare|gradient|blur/.test(sheetSrc) && /label: \{ \.\.\.type\.body, color: ice\.base \}/.test(sheetSrc)
      && (sheetSrc.match(/ice\.base/g) || []).length === 1, 'S-8g. Chalkline: tokens only; ice only on the enabled rows (actions)');
}

// ═══ S-9. The sheet reads nothing ══════════════════════════════════════════
check(!/useQuery|useSession|useFlag|fetch\(|api\.|track\(|navigation/.test(sheetSrc) && /rows: SheetRow\[\];/.test(sheetSrc)
    && /<DirectionSheet visible=\{sheetOpen\} rows=\{sheetRows\(direction!\)\}/.test(bannerSrc),
  'S-9. the sheet reads no data, flag or navigation of its own: it renders the rows the card builds from its block');

// ═══ S-10. "View" opens the sheet whenever the card holds a block ═════════
{
  const b = block({ state: 'unavailable', reason: 'stale', band: null, primary: null,
    options: { playoffs: NOT('unavailable'), draft_pick: NOT('unavailable') } });
  let tree = mount(view(b, 0.5, 'stale'));
  byId(tree, 'home.playoff.view').props.onPress(); tree = render();
  const rows = sheetNode(tree).props.rows;
  check(sheetNode(tree).props.visible && keys(rows) === 'standings,playoffs,draft_pick' && rows[0].enabled && !rows[1].enabled && !rows[2].enabled,
    'S-10. nothing offered: the sheet still opens, with "View projected standings" and the two disabled rows');
}

// ═══ Where each tap goes (spec §9: home_tile_tapped + via) ═════════════════
{
  const dest = (tap) => JSON.stringify(u.tapDestination(tap));
  check(dest({ tile: 'playoff_options', via: 'card' }) === 'null'
      && dest({ tile: 'standings', via: 'sheet' }) === '{"route":"Standings"}'
      && dest({ tile: 'improve_playoffs', via: 'sheet' }) === '{"route":"ImprovePlayoffChances","params":{"source":"sheet"}}'
      && dest({ tile: 'improve_pick', via: 'sheet' }) === '{"route":"ImproveDraftPick","params":{"source":"sheet"}}',
    'T1. playoff_options goes nowhere (the card opens its sheet); a row opens Standings or a page told it came from the sheet');
  // Execute Home's handler.
  const at = hub.indexOf('const onDirectionTap = (');
  const src = hub.slice(at, hub.indexOf('\n  };', at) + 5);
  const js = ts.transpileModule(`${src}\nreturn onDirectionTap;`, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
  const calls = [];
  const fn = new Function('track', 'navigation', 'tapDestination', js)((...a) => calls.push(['track', ...a]),
    { navigate: (...a) => calls.push(['navigate', ...a]) }, u.tapDestination);
  fn({ tile: 'improve_playoffs', via: 'sheet' });
  fn({ tile: 'playoff_options', via: 'card' });
  check(JSON.stringify(calls) === JSON.stringify([
    ['track', 'home_tile_tapped', { tile: 'improve_playoffs', via: 'sheet' }, 'Home'],
    ['navigate', 'ImprovePlayoffChances', { source: 'sheet' }],
    ['track', 'home_tile_tapped', { tile: 'playoff_options', via: 'card' }, 'Home'],
  ]), 'T2. Home tracks home_tile_tapped {tile, via} BEFORE navigating; the sheet-opening tap only tracks');
  const tax = readRoot('backend/analytics_taxonomy.py');
  check(/"home_tile_tapped":\s+frozenset\(\{"tile", "position", "band", "split", "via"\}\)/.test(tax)
      && /playoff_options/.test(tax) && /improve_playoffs \| improve_pick/.test(tax), 'T3. `via` and the three new tile values are registered');
  // League Rankings' handler is executed for both routes in check-league-rankings-playoff-tile.js (T3e).
}

// ═══ testIDs and registration ══════════════════════════════════════════════
{
  check(!/testID=\{`/.test(sheetRaw) && ['home.playoff.sheet', 'home.playoff.sheet.scrim', 'home.playoff.sheet.standings',
    'home.playoff.sheet.improve-playoffs', 'home.playoff.sheet.improve-pick'].every((id) => sheetRaw.includes(`'${id}'`) || sheetRaw.includes(`"${id}"`)),
  'R1. static literal testIDs (testid-lint can read them)');
  const features = JSON.parse(readRoot('config/features.json'));
  check(features['league.direction_view_sheet'] === true && /"league\.direction_view_sheet",/.test(readRoot('backend/feature_flags.py'))
      && ['release', 'onboarding-v2', 'profiles-on'].every((n) => JSON.parse(readRoot(`backend/tests/fixtures/flags/${n}.json`))['league.direction_view_sheet'] === true),
  'R2. league.direction_view_sheet: registered, true (ON from 2026-11-15, D-271), mirrored in the three fixtures');
  check(JSON.parse(read('package.json')).scripts['test:direction-sheet'] === 'node tests/check-direction-sheet.js', 'R3. npm run test:direction-sheet');
}

h.finish('direction-sheet');
