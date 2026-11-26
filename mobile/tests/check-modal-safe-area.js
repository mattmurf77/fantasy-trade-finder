#!/usr/bin/env node
// Inside a native <Modal>, the top safe area comes from useSafeAreaInsets(),
// never from a SafeAreaView.
//
// WHY THIS EXISTS. The Founders' review page viewer (FounderPageViewer, a
// presentationStyle="fullScreen" Modal) wrapped its content in
// react-native-safe-area-context's SafeAreaView. Inside a native Modal there
// is no SafeAreaProvider in the modal's native view tree, and on an iPhone 17
// Pro (iOS 26.1, 2026-11-22) it measured zero insets: Close, the title and
// the save state drew under the clock and Dynamic Island, taps on Close did
// not register, and the only way out was killing the app. The app's own
// pattern for insets around Modals (TopBar, TradeDnaSheet) is to read
// useSafeAreaInsets() in the component that renders the Modal, where the
// App-level SafeAreaProvider's context is present, and apply it as padding.
// PlayerPickerModal (a full-height sheet whose header and Done sit at the
// top) used SafeAreaView edges={['top']} the same way and was moved to the
// same pattern.
//
// WHAT IT CHECKS (TypeScript AST over every .tsx under src/).
//   A  No SafeAreaView lexically inside a <Modal> covers the top edge (an
//      `edges` list containing 'top', or no `edges` prop, which means all
//      four). Inside a presentationStyle="fullScreen" Modal, no SafeAreaView
//      at all.
//   B  FounderPageViewer and PlayerPickerModal read useSafeAreaInsets() and
//      pad with insets.top / insets.bottom.
//   C  Self-test: the scanner flags FounderPageViewer's pre-fix shape.
//
// NOT COVERED, deliberately. Bottom-only SafeAreaViews in bottom sheets
// (AnchorSheet, ClaimSheet, HelpSheet, PlayerContextMenu, ShopOffersBody,
// SwapPlayerSheet, SwapSuggestSheet, UsageLeagueList, VerifySheet,
// MockSetupSheet, MockTeamSheet, DirectionSheet, UsageTrendsScreen's sheet)
// share the mechanism for the bottom edge but were not observed broken; they
// are left for an on-device check rather than changed blind.
//
// HONEST LABEL (G-035). Code shape only. Whether insets are right on a device
// is the operator's simulator / TestFlight pass; nothing here renders.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const MOBILE = path.join(__dirname, '..');
let passes = 0;
let failures = 0;
const check = (cond, name, why) => {
  if (cond) { passes += 1; console.log(`PASS  ${name}`); }
  else { failures += 1; console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`); }
};

const opening = (n) => (ts.isJsxElement(n) ? n.openingElement : n);
const attr = (n, name) => {
  for (const a of opening(n).attributes.properties) {
    if (ts.isJsxAttribute(a) && a.name.getText() === name) return a.initializer ? a.initializer.getText() : 'true';
  }
  return undefined;
};

function scan(source, rel) {
  const sf = ts.createSourceFile(rel, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const bad = [];
  const visit = (n, modal) => {
    let m = modal;
    if (ts.isJsxElement(n) && n.openingElement.tagName.getText() === 'Modal') {
      m = { fullScreen: attr(n, 'presentationStyle') === '"fullScreen"' };
    }
    if (m && (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n))
      && opening(n).tagName.getText() === 'SafeAreaView') {
      const edges = attr(n, 'edges');
      const line = sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
      if (m.fullScreen) bad.push(`${rel}:${line} SafeAreaView inside a fullScreen Modal`);
      else if (edges === undefined || /'top'|"top"/.test(edges)) bad.push(`${rel}:${line} SafeAreaView covering the top edge inside a Modal (edges=${edges ?? 'all'})`);
    }
    ts.forEachChild(n, (c) => visit(c, m));
  };
  visit(sf, null);
  return bad;
}

// ── A ────────────────────────────────────────────────────────────────────
function walk(dir, out = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, out);
    else if (ent.name.endsWith('.tsx')) out.push(p);
  }
  return out;
}
const files = walk(path.join(MOBILE, 'src'));
const bad = [];
for (const f of files) bad.push(...scan(fs.readFileSync(f, 'utf8'), path.relative(MOBILE, f)));
check(files.length > 50, `A0. scanned ${files.length} .tsx files under src/`);
check(bad.length === 0, 'A1. no SafeAreaView covers the top edge inside a Modal, and none sits in a fullScreen Modal',
  bad.join('\n      '));

// ── B ────────────────────────────────────────────────────────────────────
const viewer = fs.readFileSync(path.join(MOBILE, 'src/components/founder/FounderPageViewer.tsx'), 'utf8');
check(/const insets = useSafeAreaInsets\(\);/.test(viewer)
  && /paddingTop: insets\.top, paddingBottom: insets\.bottom/.test(viewer),
'B1. FounderPageViewer pads its root with insets.top and insets.bottom from useSafeAreaInsets()');
const picker = fs.readFileSync(path.join(MOBILE, 'src/components/PlayerPickerModal.tsx'), 'utf8');
check(/const insets = useSafeAreaInsets\(\);/.test(picker)
  && /\{ paddingTop: insets\.top \}/.test(picker) && /\{ paddingBottom: insets\.bottom \}/.test(picker),
'B2. PlayerPickerModal pads the backdrop with insets.top and the sheet with insets.bottom');

// ── C ────────────────────────────────────────────────────────────────────
const PRE_FIX = `
export default function V() {
  return (
    <Modal visible animationType="slide" presentationStyle="fullScreen">
      <SafeAreaView style={styles.root} edges={['top', 'bottom', 'left', 'right']}>
        <View />
      </SafeAreaView>
    </Modal>
  );
}`;
check(scan(PRE_FIX, 'pre-fix.tsx').length === 1, 'C1. the scanner flags the pre-fix FounderPageViewer shape');
check(scan(PRE_FIX.replace(' presentationStyle="fullScreen"', ' transparent'), 'sheet.tsx').length === 1,
  'C2. the scanner flags a top-edge SafeAreaView in a transparent Modal');
check(scan(PRE_FIX.replace(' presentationStyle="fullScreen"', ' transparent')
  .replace("edges={['top', 'bottom', 'left', 'right']}", "edges={['bottom']}"), 'sheet.tsx').length === 0,
'C3. a bottom-only SafeAreaView in a transparent Modal is not flagged (left for device check)');

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
