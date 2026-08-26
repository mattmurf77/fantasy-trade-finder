#!/usr/bin/env node
// Receipts structural guard (docs/plans/receipts/, flags `receipts.grading` /
// `receipts.screen`).
//
// WHY THIS EXISTS. The grader carries 53 backend tests, but every claim below
// is about client SHAPE — registration, mounting, absence, one-payload-ness —
// which no backend test and no typecheck can see. Under D-056 (Maestro and the
// simulator retired) a structural guard plus a written code-walk is the only
// automated evidence these get.
//
// What is pinned, and why each is a real regression rather than a style note:
//   1. ReceiptsScreen is registered as a ROOT-STACK push, exactly once, and
//      never in the tab stack. Registering it in a tab would change which
//      FeedbackFAB rule applies and reintroduce #196/#197.
//   2. It mounts its OWN FeedbackFAB with activeScreen="Receipts" and
//      aboveTabBar={false} — required for a root-stack push (#188) — and
//      RootNav's global mount is untouched.
//   3. The route is registered UNCONDITIONALLY; `receipts.screen` gates the
//      ENTRY POINT only. A flag around the <Stack.Screen> would unmount an
//      in-flight push during flag revalidation.
//   4. All THREE window chips exist and are bound to ONE payload — no chip
//      refetches. This is the anti-cherry-pick guarantee: if a chip could
//      fetch its own window, some surface would eventually fetch only the
//      flattering one.
//   5. No bare `Receipt` component name. `OutlookBiasReceipt.tsx` already owns
//      that noun; two components with one name is how the wrong one gets
//      imported.
//   6. Every testID the evidence plan names is present (also the contract
//      testid-lint checks against flows).
//   7. Both analytics events fire from the screen, and `receipts_opened`
//      carries all four specced props.
//   8. The screen renders BOTH designed states — the maturity/ledger state
//      and the mature state. The ledger state is the launch hero (operator
//      ruling Q-1), not an empty state to be deleted later.
//   9. Best call and worst call are rendered as a PAIR. Showing a best call
//      without a worst call is on the banned-phrasing list (PRD §4.4).
//  10. The screen never renders a bare acquire-side percentage: the swap edge
//      is always shown with both sides' deltas beside it.
//  11. The methodology / disclosure line is rendered, not merely present in
//      the payload — selection disclosure is structural (PLAN §3.6).
//
// Run: node tests/check-receipts.js   (or npm run test:receipts)
// CI picks it up automatically via the tests/check-*.js glob.

'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCREEN = path.join(ROOT, 'src/screens/ReceiptsScreen.tsx');
const API = path.join(ROOT, 'src/api/receipts.ts');
const ROOTNAV = path.join(ROOT, 'src/navigation/RootNav.tsx');
const TABNAV = path.join(ROOT, 'src/navigation/TabNav.tsx');
const UTILROW = path.join(ROOT, 'src/components/TradeHomeUtilityRow.tsx');
const TRADES = path.join(ROOT, 'src/screens/TradesScreen.tsx');

const pass = [], fail = [];
const ok = (n) => pass.push(n);
const bad = (n, d) => fail.push(`${n}\n      ${d}`);
const read = (p) => (fs.existsSync(p)
  ? fs.readFileSync(p, 'utf8')
  : (bad('file exists', `missing ${path.relative(ROOT, p)}`), ''));
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const screenRaw = read(SCREEN);
const s = strip(screenRaw);
const api = strip(read(API));
const rootnav = strip(read(ROOTNAV));
const tabnav = strip(read(TABNAV));
const utilrow = strip(read(UTILROW));
const trades = strip(read(TRADES));

// 1 — root-stack push, registered exactly once
{
  const rootHits = (rootnav.match(/name="Receipts"/g) || []).length;
  const inTab = /name="Receipts"/.test(tabnav);
  if (rootHits !== 1) {
    bad('1. registered exactly once on the root stack',
      `found ${rootHits} <Stack.Screen name="Receipts"> in RootNav.tsx. Two ` +
      'registrations give one screen two entry stacks with different back ' +
      'behavior.');
  } else if (inTab) {
    bad('1. NOT registered in the tab stack',
      'Receipts appears in TabNav.tsx. A tab-stack screen is covered by ' +
      'RootNav\'s global FeedbackFAB, so its own mount (pinned in 2 below) ' +
      'becomes the #196/#197 double-FAB bug.');
  } else ok('1. registered once, root stack only');
}

// 2 — its own FeedbackFAB on EVERY render branch, with the right props
{
  // The screen returns from three branches (loading, error, content).
  // Counting mounts AGAINST branches is the real invariant: a FAB on the
  // happy path only means the user who hit an error — the one most likely to
  // have something to report — has no way to report it.
  const branches = (s.match(/<SafeAreaView[^>]*testID="receipts-screen"/g) || []).length;
  const allMounts = s.match(/<FeedbackFAB[\s\S]*?\/>/g) || [];
  const wrongProps = allMounts.filter((m) =>
    !/activeScreen="Receipts"/.test(m) || !/aboveTabBar=\{false\}/.test(m));
  if (branches === 0 || allMounts.length === 0) {
    bad('2a. mounts its own FeedbackFAB',
      'no <FeedbackFAB> in ReceiptsScreen. Rule #188: a root-stack push is ' +
      'NOT covered by RootNav\'s global mount, so this screen would ship with ' +
      'no way to report a bug about the numbers it publishes.');
  } else if (allMounts.length !== branches) {
    bad('2b. every render branch carries a FeedbackFAB',
      `${branches} render branches but ${allMounts.length} FeedbackFAB ` +
      'mounts. The branch without one is almost always the error state — the ' +
      'user with the most to report and no way to report it.');
  } else if (wrongProps.length) {
    bad('2c. every FeedbackFAB carries the #188 props',
      `${wrongProps.length} mount(s) missing activeScreen="Receipts" or ` +
      'aboveTabBar={false}. A wrong activeScreen misfiles every report from ' +
      'this screen; aboveTabBar={true} floats the FAB over nothing (there is ' +
      'no tab bar under a root push).');
  } else ok('2. a correctly-propped FeedbackFAB on every render branch');
}

// 3 — route registered unconditionally; the FLAG gates the entry point
{
  // Look at what sits immediately BEFORE the <Stack.Screen> tag. A ternary or
  // && there means the element is conditional however the condition is
  // spelled — which is exactly what a "search for the flag name" check misses.
  const idx = rootnav.indexOf('name="Receipts"');
  const tagStart = idx < 0 ? -1 : rootnav.lastIndexOf('<Stack.Screen', idx);
  const before = tagStart < 0
    ? '' : rootnav.slice(Math.max(0, tagStart - 160), tagStart).trimEnd();
  const conditional = /[?]$|&&$|\|\|$/.test(before);
  const entryGated = /receiptsOn/.test(trades) &&
                     /useFlag\('receipts\.screen'\)/.test(trades);
  if (tagStart < 0) {
    bad('3a. the route exists', 'no <Stack.Screen name="Receipts"> in RootNav.');
  } else if (conditional) {
    bad('3b. the route is registered unconditionally',
      'the <Stack.Screen name="Receipts"> is conditional (preceded by ' +
      `"${before.slice(-40)}"). A flag revalidation would then unmount an ` +
      'in-flight push under the user. The house rule is: flag the ENTRY ' +
      'POINT, register the ROUTE always.');
  } else if (!entryGated) {
    bad('3c. the entry point is flag-gated',
      'TradesScreen does not read useFlag(\'receipts.screen\') into receiptsOn. ' +
      'Without that gate the Track-record control ships lit while the backend ' +
      'route still 404s.');
  } else ok('3. route unconditional, entry point flag-gated');
}

// 4 — three chips, ONE payload, no per-window fetch
{
  const chips = [14, 28, 56].every((w) =>
    new RegExp(`receipts-window-chip-\\$\\{w\\}|receipts-window-chip-${w}`).test(s) ||
    /receipts-window-chip-\$\{w\}/.test(s));
  const fetches = (s.match(/getLeagueReceipts\(/g) || []).length;
  const queries = (s.match(/useQuery\(/g) || []).length;
  if (!chips) {
    bad('4a. all three window chips exist',
      'expected testIDs receipts-window-chip-14/28/56 (they are generated ' +
      'from RECEIPTS_WINDOWS). A missing window is a hidden window.');
  } else if (queries !== 1 || fetches !== 1) {
    bad('4b. one payload, one fetch',
      `found ${queries} useQuery / ${fetches} getLeagueReceipts calls. The ` +
      'windows must come from a SINGLE payload: a per-window fetch is exactly ' +
      'the mechanism that lets a surface request only the flattering window, ' +
      'which the whole design exists to make impossible.');
  } else if (!/window_days.*14.*28.*56|RECEIPTS_WINDOWS/.test(api)) {
    bad('4c. the API module declares all three windows',
      'RECEIPTS_WINDOWS is missing from src/api/receipts.ts.');
  } else ok('4. three chips bound to one payload, no per-window refetch');
}

// 5 — no bare `Receipt` component name (collision guard)
{
  const bare = /\b(?:function|const)\s+Receipt\b(?!s)/.test(s);
  if (bare) {
    bad('5. no bare `Receipt` component',
      'ReceiptsScreen declares a component literally named `Receipt`. ' +
      'src/components/OutlookBiasReceipt.tsx already owns that noun — two ' +
      'components with one name is how the wrong one gets imported.');
  } else ok('5. no bare `Receipt` component name');
}

// 6 — the testIDs the evidence plan names
{
  const required = ['receipts-screen', 'receipts-row', 'receipts-maturity'];
  const missing = required.filter((id) => !screenRaw.includes(id));
  if (missing.length) {
    bad('6. required testIDs present', `missing: ${missing.join(', ')}`);
  } else ok('6. required testIDs present');
}

// 7 — both analytics events, with the specced props
{
  const opened = /track\(\s*'receipts_opened'/.test(s);
  const changed = /track\(\s*'receipts_window_changed'/.test(s);
  const props = ['league_id', 'status', 'n_graded_28d', 'headline_bucket']
    .every((p) => new RegExp(`${p}\\s*:`).test(s));
  if (!opened || !changed) {
    bad('7a. both analytics events fire',
      `receipts_opened: ${opened}, receipts_window_changed: ${changed}. Both ` +
      'are registered in backend/analytics_taxonomy.py; a registered name with ' +
      'no emitter is a permanently empty series.');
  } else if (!props) {
    bad('7b. receipts_opened carries its four props',
      'expected league_id, status, n_graded_28d, headline_bucket (PRD DR-9). ' +
      'A prop absent from the emitter is stripped-by-omission, not an error.');
  } else ok('7. both events fire; receipts_opened carries all four props');
}

// 8 — both designed states exist
{
  const ledger = /receipts-maturity/.test(s) && /tracked_n/.test(s);
  const mature = /win_share/.test(s) && /median_edge_pct/.test(s);
  if (!ledger) {
    bad('8a. the maturity/ledger state is rendered',
      'no receipts-maturity block reading tracked_n. Operator ruling Q-1: the ' +
      'ledger state is the LAUNCH HERO — the honest empty state IS the trust ' +
      'pitch, not an apology to be deleted once numbers exist.');
  } else if (!mature) {
    bad('8b. the mature state is rendered',
      'the screen never reads win_share/median_edge_pct, so it can only ever ' +
      'show the ledger.');
  } else ok('8. both designed states rendered (ledger + mature)');
}

// 9 — best call and worst call are a PAIR
{
  const best = /best_call_impression_id/.test(s);
  const worst = /worst_call_impression_id/.test(s);
  if (best !== worst) {
    bad('9. best call and worst call render as a pair',
      `best: ${best}, worst: ${worst}. Showing a best call without a worst ` +
      'call is on the banned-phrasing list (PRD §4.4) — it converts a track ' +
      'record into a highlight reel.');
  } else if (!best) {
    bad('9. best/worst call markers exist',
      'neither marker is rendered; the payload computes them symmetrically ' +
      'and the screen drops both.');
  } else ok('9. best call and worst call render as a pair');
}

// 10 — never a standalone acquire-side number
{
  // Assert the RENDERED values, not merely that the field names appear
  // somewhere: `give_delta` survives inside a style callback even when the
  // number itself has been deleted from the row.
  const showsGive = /\{signed\(w\?\.give_delta\)\}/.test(s);
  const showsReceive = /\{signed\(w\?\.receive_delta\)\}/.test(s);
  const showsEdge = /signed\(w\.edge\)/.test(s);
  if (!(showsGive && showsReceive && showsEdge)) {
    bad('10. both sides render beside the edge',
      `give_delta rendered: ${showsGive}, receive_delta: ${showsReceive}, ` +
      `edge: ${showsEdge}. A standalone acquire-side number measures the ` +
      'MARKET, not the engine — it is the canonical banned phrasing (PRD ' +
      '§4.4), and the give side is the control that makes the metric mean ' +
      'anything at all.');
  } else ok('10. both sides render beside the swap edge');
}

// 11 — disclosure is rendered, not just fetched
{
  const rendered = /disclosure\.methodology/.test(s) &&
                   /disclosure\.gradeable_share|gradeable_share/.test(s);
  if (!rendered) {
    bad('11. the disclosure block is rendered',
      'methodology and gradeable_share are in the payload but not on screen. ' +
      'Selection disclosure is STRUCTURAL (PLAN §3.6): it sits with the ' +
      'numbers, not in a footnote a redesign can drop.');
  } else ok('11. methodology + gradeable share rendered with the numbers');
}

// 12 — the entry point exists on the utility row
{
  if (!/onTrackRecord/.test(utilrow) ||
      !/trades\.home-utility\.track-record/.test(utilrow)) {
    bad('12. the utility row carries the entry point',
      'TradeHomeUtilityRow has no onTrackRecord control. That row REPLACES ' +
      'TradeFinderModeBar for everyone in the trades_home_inline experiment ' +
      '(100% strip on the tester allowlist), so an entry point missing here ' +
      'is missing for every tester.');
  } else ok('12. Track-record entry point on the trades utility row');
}

console.log(`\ncheck-receipts: ${pass.length} passed, ${fail.length} failed`);
for (const p of pass) console.log(`  ✓ ${p}`);
if (fail.length) {
  console.error('\nFAILURES:');
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.error('\nThese pin the honesty rules of a trust feature (PLAN §3, ' +
    'PRD §4.4) and the #188 FeedbackFAB contract. If a change is genuinely ' +
    'intended, update docs/plans/receipts/ in the SAME commit.\n');
  process.exit(1);
}
console.log('');
