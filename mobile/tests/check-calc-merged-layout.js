#!/usr/bin/env node
// #384 W1 — the merged calculator layout, and the properties that make it
// safe to ship behind a flag.
//
// WHAT THIS PINS, and why each one is worth a test:
//
//  * The flag exists on BOTH sides of the wire. A client reading a flag the
//    backend never serves gets `undefined` — falsy — so the feature would be
//    silently unreachable and look "not working" rather than "off".
//  * Every merged-only surface is gated. An ungated one leaks into the
//    shipped stacked page, which is the whole risk of a flagged rewrite.
//  * The value/tier is MOVED in column mode, never dropped. A narrower row
//    that silently stops pricing an asset is worse than a wrapped one, and
//    it is the easiest thing to "fix" a layout overflow with.
//  * Tap targets and the type floor survive the 15% cells. This is the
//    operator-flagged risk in plan.md §2.
//
// Run: node tests/check-calc-merged-layout.js

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const SRC = path.join(__dirname, '..', 'src');
let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}`); if (detail) console.log(`      ${detail}`); }
}
const read = (p) => fs.readFileSync(p, 'utf8');
const calc = read(path.join(SRC, 'components/InLeagueCalculator.tsx'));
const side = read(path.join(SRC, 'components/TradeSide.tsx'));
const screen = read(path.join(SRC, 'screens/TradeCalculatorScreen.tsx'));

console.log('check-calc-merged-layout:');

const FLAG = 'calc.merged_layout';

// 1 — the flag is registered on both sides of the wire.
const features = JSON.parse(read(path.join(ROOT, 'config/features.json')));
assert(Object.prototype.hasOwnProperty.call(features, FLAG),
  '1. flag is declared in config/features.json',
  `${FLAG} missing — the client would read undefined and the layout would be unreachable`);
assert(read(path.join(ROOT, 'backend/feature_flags.py')).includes(`"${FLAG}"`),
  '2. flag is in the backend FLAG_KEYS allowlist',
  `${FLAG} missing from backend/feature_flags.py — /api/feature-flags would not serve it`);
const release = JSON.parse(read(path.join(ROOT, 'backend/tests/fixtures/flags/release.json')));
assert(Object.prototype.hasOwnProperty.call(release, FLAG),
  '3. flag is mirrored in the release fixture');

// 4 — the client reads it, and reads it STRAIGHT.
//
// Anchored on the whole statement, terminator included. The loose form this
// replaced (`/useFlag\('calc\.merged_layout'\)/`) matched
// `const merged = useFlag('calc.merged_layout') || true;` — which renders the
// merged page to every user with the flag OFF — and matched
// `!useFlag(...)`, which inverts the whole feature. Both were verified green
// against the loose form. There is exactly ONE read, and it is this one.
assert(/\n  const merged = useFlag\('calc\.merged_layout'\);\n/.test(calc),
  '4. InLeagueCalculator reads the flag, unmodified',
  'the flag read must be the bare statement — no `|| true`, no `!`, no default');
assert((calc.match(/useFlag\(\s*['"]calc\.merged_layout['"]\s*\)/g) || []).length === 1,
  '4a. exactly one flag read in the component',
  'a second read is a second gate that can disagree with the first');

// 4b — the column re-flow is the flag, not a constant. `compact` always-on
// re-flows the SHIPPED stacked page (narrow rows, moved price) with the flag
// off, which is the byte-identity promise broken in the quietest possible way.
{
  const compactProps = [...calc.matchAll(/\bcompact=\{([^}]*)\}/g)].map((m) => m[1].trim());
  assert(compactProps.length === 2 && compactProps.every((v) => v === 'merged'),
    '4b. both TradeSide columns take `compact` FROM the flag',
    `found [${compactProps.join(', ')}] — compact must be exactly \`merged\` at both mounts`);
}

// 4c — the spotlight-target registration is gated on the flag too. With the
// flag off none of those nodes is mounted, and a registered ref to an
// unmounted node measures null: every beat would DEGRADE (pointing at
// nothing) rather than simply not running.
{
  const at = calc.indexOf("['calc.trade-columns', columnsRef]");
  assert(at > 0, '4c. the guide-target registration table exists');
  const start = calc.lastIndexOf('useEffect(() => {', at);
  assert(start > 0 && /if \(!merged\) return;/.test(calc.slice(start, at)),
    '4c. the target registration bails out when the flag is off',
    'registering refs to unmounted nodes degrades every beat instead of not running the tour');
  assert(/\}, \[merged\]\);/.test(calc.slice(at, at + 900)),
    '4d. the registration effect re-runs when the flag resolves',
    'deps that omit `merged` freeze the registration at its first-render value');
}

// 5 — every merged-only surface is gated behind the flag.
//
// NOT a proximity heuristic. An earlier draft of this check looked backwards
// for the nearest `{merged ?` and passed when the action row's own gate was
// replaced with `{true ?` — it simply found the header's gate instead. That
// assertion was unfalsifiable, so it was replaced with this:
//
//   excise every flag-gated region by BRACE BALANCING, then assert that no
//   merged-only testID survives in what is left.
//
// What is left is, by construction, exactly the code that renders when the
// flag is off. If an id is still in there, it leaks onto the shipped page.
function exciseGatedRegions(src) {
  const OPENERS = [/\{merged \? \(/g, /if \(merged\) \{/g];
  let out = src;
  for (const re of OPENERS) {
    for (;;) {
      re.lastIndex = 0;
      const m = re.exec(out);
      if (!m) break;
      // Balance from the opener's final bracket to its partner.
      const openChar = m[0].endsWith('{') ? '{' : '(';
      const closeChar = openChar === '{' ? '}' : ')';
      let i = m.index + m[0].length - 1;
      let depth = 0;
      for (; i < out.length; i++) {
        if (out[i] === openChar) depth++;
        else if (out[i] === closeChar) { depth--; if (depth === 0) break; }
      }
      if (i >= out.length) break; // unbalanced — leave it, assertion below will speak
      out = out.slice(0, m.index) + out.slice(i + 1);
    }
  }
  return out;
}
const flagOffSource = exciseGatedRegions(calc);
// Sanity: the excision must actually remove something, or every assertion
// below it is vacuous. This is the guard on the guard.
assert(flagOffSource.length < calc.length - 2000,
  '5a. the gate-excision actually removed the merged regions',
  `only ${calc.length - flagOffSource.length} chars removed — the matcher missed`);

const MERGED_ONLY = [
  'calc.action-row', 'calc.action.find-a-trade',
  'calc.action.clear', 'calc.action.confirm', 'calc.league-dropdown',
  'calc.team-dropdown', 'calc.trade-columns', 'calc.team-sheet',
  'calc.outlook-fallback', 'calc.outlook-fallback.change',
];

// W6-B (D-153) — the Include-players toggle is GONE, not merely flag-gated.
// The operator's ruling ("C works") made the canvas the permanent anchor, so
// the only state the control could honestly show was "on". Asserted as an
// ABSENCE because a flag-gated leftover would still be a control the tour no
// longer describes and the hand-off no longer reads.
assert(!calc.includes('calc.action.include-players'),
  '5b. the Include-players toggle does not exist in either flag state',
  'the toggle was removed with its ruling, not hidden — a surviving one is a '
  + 'control with no contract behind it');
assert(!/actionInclude|setIncludePlayers|includeBtnRef/.test(calc),
  '5c. …and neither do its state, style or guide ref');
for (const id of MERGED_ONLY) {
  assert(calc.includes(`testID="${id}"`) && !flagOffSource.includes(`testID="${id}"`),
    `5. ${id} renders only behind the flag`,
    calc.includes(`testID="${id}"`)
      ? 'this control survives with the flag OFF — it would render on the shipped stacked page'
      : 'testID not found at all');
}

// 6 — the price is moved, not dropped, in column mode.
assert(/compact\s*\?\s*\(\(\) => \{[\s\S]{0,400}?TierBadge/.test(side),
  '6. column mode still renders a tier/value for each row',
  'TradeSide compact dropped the price column instead of re-flowing it');
assert(/compactMetaLine/.test(side) && /valueOf\(p\)\.toLocaleString\(\)/.test(side),
  '7. column mode keeps the numeric fallback when there is no tier');

// 8 — no type shrinking to win space in the MERGED styles.
//
// Scoped to the #384 style block on purpose. The file already carries one
// pre-existing floor violation — `lineupHeadText` at fontSize 10, present on
// origin/main since #297 — and this change did not introduce it and does not
// fix it (that would be an unrelated edit to a shipped surface). It is
// reported to the operator rather than silently absorbed or silently
// tolerated: widening this assertion to the whole file would fail on someone
// else's line, and deleting the assertion would lose the guarantee that
// matters here, which is that the narrow cells were not paid for in type size.
const mergedStyles = calc.slice(
  calc.indexOf('// ── #384 merged layout'),
  calc.indexOf('teamRow: {'),
);
const fontSizes = [...mergedStyles.matchAll(/fontSize:\s*(\d+)/g)].map((m) => Number(m[1]));
assert(fontSizes.length > 0 && fontSizes.every((n) => n >= 11),
  '8. no #384 font size below the Chalkline 11pt floor',
  `found ${fontSizes.filter((n) => n < 11).join(', ') || '(no sizes scanned — slice missed)'}`);

// 9 — the narrow cells keep a real tap target.
assert(/actionBtn:\s*\{[^}]*minHeight:\s*44/.test(calc),
  '9. action-row buttons hold a 44pt tap height',
  'the 15% cells are ~53pt wide; losing the height too would put them under the floor');

// 10 — the two icon-only cells are labelled. Icon-only + unlabelled is a
// screen-reader dead end, and these two are the destructive + confirm pair.
for (const id of ['calc.action.clear', 'calc.action.confirm']) {
  const at = calc.indexOf(`testID="${id}"`);
  const window = calc.slice(at, at + 500);
  assert(/accessibilityLabel=/.test(window), `10. ${id} carries an accessibilityLabel`);
}

// 11 — no emoji as icons (Chalkline forbids it; the report specced "✅").
assert(!/[\u{1F300}-\u{1FAFF}\u{2700}-\u{27BF}\u{2B00}-\u{2BFF}\u{2705}\u{274C}]/u.test(calc),
  '11. no emoji used as an icon in the merged layout',
  'the report specced ✅; Chalkline requires a real icon (name="check")');

// 12 — Clear exists exactly once in the merged layout. Two controls for one
// destructive action on one screen is a defect, not a convenience.
assert(/merged \? null : <Button label="Clear trade"/.test(calc),
  '12. the legacy Clear button is suppressed in the merged layout',
  'both the action-row Clear and the ghost Clear would render');

// 13 — the scoring-format control survived the merge. The #166/#167 session
// override is the one thing on this page that changes what every value MEANS;
// dropping it silently is a worse regression than any layout shift.
assert(/calc\.merged-format\./.test(calc) && /setFormatChoice\(f\.key\)/.test(calc),
  '13. the merged header renders the scoring-format chips',
  'the merged branch dropped them entirely — no way to override the detected format');
{
  const at = calc.indexOf('calc.merged-format.');
  assert(at >= 0 && !flagOffSource.includes('calc.merged-format.'),
    '13b. the merged format chips render only behind the flag');
}
assert(/values converted to \{FORMAT_LABEL\[format\]\}/.test(calc),
  '14. the #191 cross-format conversion note is kept in the merged layout',
  'a converted board presented as a ranked one is a silent honesty defect');

// 15 — the outlook section is never a silent gap. OutlookBiasReceipt renders
// null under two independent conditions (flag off, or no directional
// outlook); the merged page mirrors TradesScreen's fallback instead.
assert(/onHiddenChange=\{setOutlookHidden\}/.test(calc),
  '15. the merged page learns when the outlook receipt rendered nothing');
assert(/onHiddenChange\?:/.test(read(path.join(SRC, 'components/OutlookBiasReceipt.tsx'))),
  '15b. the receipt reports it — and the prop is OPTIONAL, so every other caller is unchanged');

// 16 — column mode's clamping is column-only. `numberOfLines={1}` in BOTH
// modes reaches the shipped stacked page behind the flag, where a long
// "@username" used to wrap and would now ellipsize.
{
  // The ONE bare clamp left is the compact-only name line — it lives inside
  // the `compact ? (…) : (…)` branch, so it cannot reach the stacked page.
  const bare = [...side.matchAll(/numberOfLines=\{1\}/g)].map((m) =>
    side.slice(Math.max(0, m.index - 120), m.index),
  );
  assert(bare.length === 1 && /styles\.compactName/.test(bare[0]),
    '16. TradeSide adds no line clamp that reaches the stacked page',
    'flag-off must stay byte-identical — a shared row clamps on `compact` only');
}
assert((side.match(/numberOfLines=\{compact \? 1 : undefined\}/g) || []).length === 2,
  '16b. both clamped lines are gated on compact');
assert(/compactMetaText: \{ flexShrink: 1 \}/.test(side),
  '17. the compact meta line yields before the tier badge',
  'without flexShrink the badge is pushed out of ~97pt of info width — the price disappears');

// 18 — the calculator remounts on a league switch. Its canvas is LOCAL
// state; without this the new league renders the old league's players and
// evaluates the old opponent id against it.
assert(/`manual-\$\{league\.league_id\}`/.test(screen),
  '18. InLeagueCalculator is keyed on the league');

// 19 — one Find-a-Trade entry on the merged page. The #213 text link
// navigates without touching pins, so it bypasses Include players.
assert(/calcMergedOn && mode === 'league' \? null : \(/.test(screen),
  '19. the #213 link steps aside on the merged In-league page');
assert(!/navigation\.navigate\('TradesHome'\)/.test(screen),
  '20. no plain navigate to TradesHome',
  "without `pop` and with no getId, routers 7.5.3 PUSHES a second TradesHome and leaves this screen mounted");
assert((screen.match(/navigation\.popTo\('TradesHome'\)/g) || []).length === 2,
  '20b. both exits use popTo');

// 21 — the re-entry link is a real control, not a 34pt line of text.
assert(/showMeAroundTap: \{ minHeight: 44/.test(calc),
  '21. "Show me around" clears the 44pt touch floor',
  'hitSlop widens the touch area but not the control');

// 22 — the partner TEAM-SHAPE summary survived the merge.
//
// This is a shipped regression, found by the 2026-08-27 calc-vs-guided
// parity audit (row 24) and fixed here. The stacked page has carried a
// per-partner QB/RB/WR/TE + picks line under each partner chip since the DTF
// teardown (2026-07-27); #384 W1 replaced that chip row with a Team dropdown
// and a sheet, and the sheet shipped with a handle and an R-badge only. It
// was an omission, not a ruling — the #384 rulings that removed things
// (6, 7: utility row, subnav) never touched the partner shape.
//
// Same failure class as 13/14 above: the merged branch silently dropping
// evidence the stacked page shows. The sabotage each assertion detects is
// named on the line.
{
  // 22a — ONE implementation. A hand-copied block in the sheet is how the
  // a11y/label drift that check-calc-partner-labels.js guards against gets
  // reintroduced on one surface only.
  assert((calc.match(/calc\.partner-summary\./g) || []).length === 1,
    '22a. exactly one partner-summary implementation (the shared PartnerSummaryLine)',
    'a second literal testID means a hand-copied block that can drift from the first');
  assert(/function PartnerSummaryLine\(/.test(calc),
    '22b. the shared line component exists');

  // 22c — the MERGED team sheet mounts it. Scoped to the sheet region by
  // slicing between its two testIDs, so deleting the mount from the sheet
  // fails here even though the stacked page still has one.
  const sheetAt = calc.indexOf('testID="calc.team-sheet"');
  const sheetEnd = calc.indexOf('</Modal>', sheetAt);
  assert(sheetAt > 0 && sheetEnd > sheetAt, '22c. the merged team sheet region is locatable');
  const sheet = calc.slice(sheetAt, sheetEnd);
  assert(/<PartnerSummaryLine\s/.test(sheet),
    '22d. the merged team sheet renders the partner shape line',
    'the merged layout is back to handle + R-badge only — the regression this fixed');
  assert(/partnerSummaries\[o\.user_id\]/.test(sheet),
    '22e. …fed from the same partnerSummaries memo as the stacked page');
  assert(/partnerSummarySpoken\(summary\)/.test(sheet),
    '22f. …and the sheet row SPEAKS the shape too',
    'a sighted-only restore leaves VoiceOver on handle + rank state alone');

  // 22g — the row had to become a two-line stack; without a shrinking main
  // column the shape line pushes the R-badge off the sheet.
  assert(/teamRowMain: \{[^}]*minWidth: 0/.test(calc),
    '22g. the sheet row main column can shrink, so the badge is never pushed out');

  // 22h — and the stacked page did not lose it in the extraction.
  assert(/<PartnerSummaryLine\s/.test(flagOffSource),
    '22h. the stacked (flag-off) partner chips still render the shape line',
    'the rollback path must keep what it always had');
}

console.log(failures === 0
  ? 'check-calc-merged-layout: all assertions passed'
  : `check-calc-merged-layout: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
