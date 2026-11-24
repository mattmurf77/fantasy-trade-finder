#!/usr/bin/env node
// The feedback FAB never sits on top of a screen's last content or its
// pinned primary button.
//
// WHY THIS EXISTS. A Release simulator pass (2026-11-22, iPhone 17 Pro) found
// the FAB (52pt, bottom right, ~y 720-770) covering: Team Review's pinned
// Next / Find my trades, the last Add on Free agents, a tier label on the
// Tiers board, a player card in Quick set, Trios' Confirm ranking, the Rank
// landing's footer line and the trade builder's "You receive" column. The
// FAB already had one mechanism (setPinnedBottomBarHeight: a pinned bar lifts
// it); what was missing was the other half — scroll content reserving the
// FAB's footprint — and Team Review never reported its footer.
//
// Pinned:
//   (c1-c2, ARITHMETIC) FeedbackFAB exports FEEDBACK_FAB_CLEARANCE, and it
//        covers the FAB's real footprint for both mounts, computed from the
//        file's own constants: root-stack pushes (bottom inset + 16 + 52)
//        and tab screens (inset + 64 + 52, over the UIKit tab bar whose
//        height is read from @react-navigation/bottom-tabs), plus a gap.
//   (s1) Each screen in the report pads its scroll content by it: Free
//        agents, Trios, Rank landing, the calculator / trade builder, Team
//        Review. Screens with an ABSOLUTE pinned bar (Tiers save + multi-
//        select bars, Quick set footer) pad bar height + clearance, and
//        Tiers pads by the same height it reports to the FAB.
//   (s2) Matches' lists and the Trades home (inline builder) already pad
//        ≥ the clearance (96pt): read and compared, not changed.
//   (t1) Team Review reports its pinned footer: onLayout → footerH →
//        setPinnedBottomBarHeight('team_review', …) only while focused and
//        while the footer is shown, cleared on unmount; and it still mounts
//        no FAB of its own (#196/#197).
//
// HONEST LABEL (G-035): this proves the wiring and the numbers in source, not
// pixels on a device. A floating button still passes over rows in the MIDDLE
// of a list while scrolling; this guarantees the LAST row and the pinned
// buttons can always be reached clear of it.
//
// Run: node tests/check-fab-clearance.js   (or: npm run test:fab-clearance)

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:"'`])\/\/[^\n]*/g, '$1');
let failures = 0;
const assert = (cond, name, detail) => {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
};

// ── c: the constant and the footprint ─────────────────────────────────────
const FAB = strip(read('src/components/FeedbackFAB.tsx'));
const constOf = (name) => {
  const m = FAB.match(new RegExp(`const ${name} = (\\d+);`));
  return m ? Number(m[1]) : NaN;
};
const SIZE = constOf('FAB_SIZE');
const TABS = constOf('FAB_BOTTOM_TABS');
const STACK = constOf('FAB_BOTTOM_STACK');
const GAP = constOf('FAB_GAP');
const exported = /export const FEEDBACK_FAB_CLEARANCE = FAB_BOTTOM_STACK \+ FAB_SIZE \+ FAB_GAP;/.test(FAB);
const CLEAR = STACK + SIZE + GAP;
let TABBAR = 49;
try {
  const bt = fs.readFileSync(path.join(MOBILE,
    'node_modules/@react-navigation/bottom-tabs/src/views/BottomTabBar.tsx'), 'utf8');
  const m = bt.match(/const TABBAR_HEIGHT_UIKIT = (\d+);/);
  if (m) TABBAR = Number(m[1]);
} catch { /* fall back to UIKit's 49 */ }
assert(exported && [SIZE, TABS, STACK, GAP].every(Number.isFinite),
  `c1. FeedbackFAB exports FEEDBACK_FAB_CLEARANCE = FAB_BOTTOM_STACK + FAB_SIZE + FAB_GAP (= ${CLEAR})`);
assert(
  /bottom: insets\.bottom \+ \(aboveTabBar \? FAB_BOTTOM_TABS : FAB_BOTTOM_STACK\) \+ extraOffset/.test(FAB)
    && /width: FAB_SIZE,\s*height: FAB_SIZE,/.test(FAB),
  'c1b. the FAB is placed and sized from those same constants',
);
{
  const needStack = STACK + SIZE; // above the bottom inset, content ends at the inset
  const needTabs = TABS + SIZE - TABBAR; // above the tab bar's top edge
  assert(CLEAR > needStack && CLEAR > needTabs,
    `c2. clearance ${CLEAR}pt clears the FAB's top edge on a root push (${needStack}pt) and over the ${TABBAR}pt tab bar (${needTabs}pt)`);
}

// ── s1: the screens in the report ─────────────────────────────────────────
function styleBody(src, name) {
  const i = src.indexOf(`  ${name}: {`);
  return i === -1 ? '' : src.slice(i, src.indexOf('}', i));
}
const imports = (src) => /import\s+(?:FeedbackFAB,\s*)?\{[^}]*\bFEEDBACK_FAB_CLEARANCE\b[^}]*\}\s+from '\.\.(?:\/\.\.)?\/components\/FeedbackFAB'/.test(src);
const padded = [
  ['src/screens/FreeAgentsScreen.tsx', 'listContent', 'Free agents list'],
  ['src/screens/RankScreen.tsx', 'scroll', 'Trios (Confirm ranking / Skip)'],
  ['src/screens/RankHomeScreen.tsx', 'body', 'Rank landing'],
  ['src/screens/TradeCalculatorScreen.tsx', 'scroll', 'Calculator / trade builder'],
  ['src/screens/TeamReviewScreen.tsx', 'body', 'Team Review'],
];
for (const [file, style, label] of padded) {
  const src = strip(read(file));
  assert(imports(src) && /paddingBottom: FEEDBACK_FAB_CLEARANCE\b/.test(styleBody(src, style))
    && new RegExp(`contentContainerStyle=\\{styles\\.${style}\\}`).test(src),
  `s1. ${label}: styles.${style} is the scroll content and pads FEEDBACK_FAB_CLEARANCE`, file);
}
{
  const src = strip(read('src/screens/QuickSetTiersScreen.tsx'));
  assert(imports(src)
    && /contentContainerStyle=\{\[\s*styles\.grid,\s*\{ paddingBottom: Math\.max\(96, footerH \+ FEEDBACK_FAB_CLEARANCE\) \},?\s*\]\}/.test(src)
    && /setPinnedBottomBarHeight\('quickset', isFocused \? footerH : 0\)/.test(src),
  's1. Quick set: the grid pads the reported footer height + FEEDBACK_FAB_CLEARANCE');
}
{
  const src = strip(read('src/screens/TiersScreen.tsx'));
  assert(imports(src)
    && /setPinnedBottomBarHeight\('tiers', isFocused \? barOccupied : 0\)/.test(src)
    && /touchPolish && \{ paddingBottom: Math\.max\(96, barOccupied \+ FEEDBACK_FAB_CLEARANCE\) \}/.test(src)
    && /const barOccupied = Math\.max\(\s*saveBarH,\s*actionBarVisible \? ACTION_BAR_BOTTOM \+ actionBarH : 0,?\s*\);/.test(src),
  's1. Tiers: the board pads the SAME bar height it reports (save bar or multi-select bar) + FEEDBACK_FAB_CLEARANCE');
}

// ── s2: already sufficient, read not changed ──────────────────────────────
for (const [file, style, label] of [
  ['src/screens/MatchesScreen.tsx', 'list', 'Matches lists'],
  ['src/screens/TradesScreen.tsx', 'scroll', 'Trades home (inline builder)'],
]) {
  const m = styleBody(strip(read(file)), style).match(/paddingBottom: (\d+)/);
  const v = m ? Number(m[1]) : NaN;
  assert(v >= CLEAR, `s2. ${label}: styles.${style} paddingBottom ${v} ≥ ${CLEAR}`);
}

// ── t1: Team Review's pinned footer lifts the FAB ─────────────────────────
{
  const src = strip(read('src/screens/TeamReviewScreen.tsx'));
  assert(
    /const isFocused = useIsFocused\(\);/.test(src)
      && /setPinnedBottomBarHeight\('team_review', isFocused && beat \? footerH : 0\);/.test(src)
      && /useEffect\(\(\) => \(\) => setPinnedBottomBarHeight\('team_review', 0\), \[\]\);/.test(src)
      && /<View\s+style=\{styles\.footer\}\s+onLayout=\{\(e\) => setFooterH\(e\.nativeEvent\.layout\.height\)\}/.test(src),
    't1. Team Review reports its pinned footer (focused, shown) and clears it on unmount',
  );
  assert(!/<FeedbackFAB\b/.test(src) && !/import\s+FeedbackFAB\b/.test(src),
    't1b. Team Review still mounts no FAB of its own (#196/#197)');
}

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll fab-clearance checks passed.');
