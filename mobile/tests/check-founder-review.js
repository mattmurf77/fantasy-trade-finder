#!/usr/bin/env node
// Founders' review — the founder-only player label review in Calibration
// (docs/plans/founder-review/{scope,design}.md).
//
// WHY THIS EXISTS. The page is invisible to everyone but the founder, so its
// failure modes are silent: a section that renders off a local flag or list
// instead of the server's answer, a band order or label vocabulary that drifts
// from the server's (backend/founder_review.py), a chip or player the client
// still locks (amended 2026-11-12: any label for any player, the unlabelled
// band and mixed selections included), a Save that sends every row instead of
// the changed ones, a Reset that leaves edits behind (or cannot return an
// unlabelled player to No label), or an empty state that hides why there are
// no labels.
//
// HONEST LABEL (G-035): §1-§3 and §8 prove the PRESENCE of exact wirings in
// source; §4-§7 transpile and EXECUTE src/utils/founderReview.ts under node.
// Runtime proof is the manual TestFlight checklist in scope.md §3.
//
// Run: npm run test:founder-review   (or node tests/check-founder-review.js)
'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const ROOT = path.join(MOBILE, '..');
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
const readRoot = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const code = (src) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1');

const SCREEN = code(read('src/screens/CalibrationScreen.tsx'));
const REVIEW = code(read('src/components/founder/FounderLabelReview.tsx'));
const BOARD = code(read('src/components/founder/LabelBandBoard.tsx'));
const API = code(read('src/api/founder.ts'));
const UTIL_SRC = read('src/utils/founderReview.ts');
const SERVER_REVIEW = readRoot('backend/founder_review.py');
const SEASON_VALUE = readRoot('backend/season_value.py');
const PKG = JSON.parse(read('package.json'));

// Execute the util (zero runtime imports by contract).
assert(!/^\s*import\s+(?!type\b)/m.test(UTIL_SRC), '0a. utils/founderReview.ts has no runtime imports');
const js = ts.transpileModule(UTIL_SRC, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 } }).outputText;
const mod = { exports: {} };
new Function('module', 'exports', 'require', js)(mod, mod.exports, () => { throw new Error('no imports'); });
const U = mod.exports;

// ── 1. Shown only on the server capability ───────────────────────────────
assert(/getFounderCapability/.test(SCREEN) && /from '\.\.\/api\/founder'/.test(SCREEN),
  '1a. Calibration asks the server (GET /api/founder/capability) through api/founder');
assert(/const founder = founderQ\.data === true;/.test(SCREEN),
  '1b. founder = the capability answer exactly true');
assert(/\{founder \? \(\s*<View style=\{styles\.sectionRow\}>/.test(SCREEN),
  '1c. the Grading | Founders’ review control renders only when founder');
assert(/const showFounder = founder && section === 'founder';/.test(SCREEN)
  && /\{showFounder \? \(/.test(SCREEN) && (SCREEN.match(/<FounderReview\b/g) || []).length === 1
  && !/<FounderLabelReview\b/.test(SCREEN),
  '1d. the founder section (FounderReview, which hosts FounderLabelReview) mounts once, only under showFounder');
for (const [name, src] of [['CalibrationScreen', SCREEN], ['FounderLabelReview', REVIEW], ['LabelBandBoard', BOARD], ['api/founder', API]]) {
  assert(!/founder\.review|useFlag\(|useFeatureFlags|FOUNDER_ACCOUNTS|tester_allowlist/.test(src),
    `1e. ${name} reads no flag and no local allow-list`);
}
assert(/'\/api\/founder\/capability'/.test(API) && /e\.status === 404\) return false/.test(API)
  && /quietStatuses: \[404\]/.test(API),
  '1f. the capability probe reads a 404 as "not a founder" and reports nothing');

// ── 2. Band order and vocabulary equal the server's ──────────────────────
const tupleOf = (src, name) => {
  const m = src.match(new RegExp(`^${name}\\s*=\\s*\\(([^)]*)\\)`, 'm'));
  return m ? [...m[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]) : null;
};
const serverLabels = tupleOf(SEASON_VALUE, 'OVERRIDE_LABELS');
const serverBands = tupleOf(SERVER_REVIEW, 'BANDS');
assert(/^LABELS = OVERRIDE_LABELS/m.test(SERVER_REVIEW), '2a. server: founder_review.LABELS is season_value.OVERRIDE_LABELS');
assert(JSON.stringify(U.LABELS) === JSON.stringify(serverLabels),
  '2b. app LABELS equal the server vocabulary', `app ${JSON.stringify(U.LABELS)} server ${JSON.stringify(serverLabels)}`);
assert(JSON.stringify(U.BANDS) === JSON.stringify(serverBands)
  && JSON.stringify(U.BANDS) === JSON.stringify(['cornerstone', 'win_now', 'rebuild', 'depth', 'none']),
  '2c. app BANDS equal the server band order: Cornerstone, Win-now piece, Rebuild piece, Depth, No label',
  `app ${JSON.stringify(U.BANDS)} server ${JSON.stringify(serverBands)}`);
assert(U.BAND_LABEL.cornerstone === 'Cornerstone' && U.BAND_LABEL.win_now === 'Win-now piece'
  && U.BAND_LABEL.rebuild === 'Rebuild piece' && U.BAND_LABEL.depth === 'Depth' && U.BAND_LABEL.none === 'No label',
  '2d. band names are the engine’s display names');
const chips = [...REVIEW.matchAll(/\{ label: '([a-z_]+)', testID: 'founder-review\.move\.([a-z_]+)' \}/g)];
assert(JSON.stringify(chips.map((c) => c[1])) === JSON.stringify(U.LABELS) && chips.every((c) => c[1] === c[2]),
  '2e. the footer’s Move-to chips are exactly the vocabulary, in band order');
assert(/BANDS\.map\(\(b\) =>/.test(BOARD), '2f. the board renders every band from BANDS (empty bands included)');

// ── 3. Tap-then-band wiring (the tier board's interaction) ───────────────
assert(/onPress=\{\(\) => onToggle\(row\.id\)\}/.test(BOARD), '3a. tapping a chip toggles its selection');
assert(!/readOnly/.test(BOARD) && (BOARD.match(/<Pressable\b/g) || []).length === 1
  && /accessibilityActions=\{LABELS\.filter\(\(l\) => l !== band\)/.test(BOARD),
  '3b. every chip (No label included) is a button with a VoiceOver "Move to" action for each other label');
assert(/const targets = targetsFor\(posRows, selected\);/.test(REVIEW)
  && /const enabled = targets\.includes\(c\.label\);/.test(REVIEW) && /disabled=\{!enabled\}/.test(REVIEW),
  '3c. a Move-to chip is enabled from targetsFor (all four once anyone is selected)');
for (const [name, src] of [['utils/founderReview', code(UTIL_SRC).replace(/movable_to: FounderLabel\[\];/, '')],
  ['LabelBandBoard', BOARD], ['FounderLabelReview', REVIEW]]) {
  assert(!/movable_to/.test(src), `3e. ${name} does not read the server's movable_to (the rule is the client's own)`);
}
assert(/onPress=\{\(\) => moveTo\(selected, c\.label\)\}/.test(REVIEW)
  && /setDraft\(\(d\) => applyMove\(d, rows, ids, label\)\);/.test(REVIEW),
  '3d. tapping a chip moves the selection through applyMove');

// ── 4. Executed: targets and moves ───────────────────────────────────────
// movable_to as the OLD server sent it: the client must not be limited by it.
const row = (id, label, startable, extra = {}) => ({
  id, name: id, position: 'RB', team: 'AAA', age: 25, ppg: 10, line: 9, value: 1000, future: 0,
  startable, label, engine_label: label, override: null, why_unlabelled: label ? null : 'borderline',
  movable_to: label == null || startable == null ? [] : startable ? ['cornerstone', 'win_now'] : ['rebuild', 'depth'],
  ...extra,
});
const rows = [row('s1', 'win_now', true), row('s2', 'cornerstone', true), row('b1', 'depth', false), row('n1', null, null)];
const ALL = JSON.stringify(['cornerstone', 'win_now', 'rebuild', 'depth']);
assert(JSON.stringify(U.targetsFor(rows, ['s1', 's2'])) === ALL && JSON.stringify(U.targetsFor(rows, ['b1'])) === ALL,
  '4a. a starter may be given any label, and so may a bench player');
assert(JSON.stringify(U.targetsFor(rows, ['s1', 'b1', 'n1'])) === ALL, '4b. a mixed selection (starter + bench + unlabelled) may be moved together');
assert(JSON.stringify(U.targetsFor(rows, ['n1'])) === ALL && U.targetsFor(rows, []).length === 0,
  '4c. an unlabelled player may be given any label; no selection: no target');
let draft = U.applyMove({}, rows, ['s1'], 'cornerstone');
assert(draft.s1 === 'cornerstone' && U.bandOf(rows[0], draft) === 'cornerstone', '4d. a move places the player in the band');
assert(U.engineNote(rows[0], draft) === 'engine: Win-now piece', '4e. a moved player shows "engine: <label>"');
const mixed = U.applyMove({}, rows, ['s1', 'b1', 'n1'], 'rebuild');
assert(JSON.stringify(mixed) === JSON.stringify({ s1: 'rebuild', b1: 'rebuild', n1: 'rebuild' })
  && U.engineNote(rows[3], mixed) === 'engine: No label' && U.bandOf(rows[3], mixed) === 'rebuild',
  '4f. starter -> Rebuild, bench -> Rebuild, unlabelled -> Rebuild in one move; the unlabelled one notes "engine: No label"');
assert(JSON.stringify(U.savePayload('L1', rows, mixed)) === JSON.stringify(
  { league_id: 'L1', set: { s1: 'rebuild', b1: 'rebuild', n1: 'rebuild' }, clear: [] }),
  '4h. those moves save as sets');
assert(Object.keys(U.applyMove(draft, rows, ['s1'], 'win_now')).length === 0, '4g. moving back to the server label drops the edit');

// ── 5. Changed count and Save sends only changed players ─────────────────
assert(/const changed = changedIds\(rows, draft\);/.test(REVIEW)
  && /testID="founder-review\.changed">\{COPY\.changed\(changed\.length\)\}/.test(REVIEW),
  '5a. the footer’s count is changedIds(rows, draft)');
assert(/mutationFn: \(\) => saveFounderLabels\(savePayload\(leagueId, rows, draft\)\)/.test(REVIEW)
  && /disabled=\{changed\.length === 0 \|\| saveM\.isPending\}/.test(REVIEW),
  '5b. Save posts savePayload (changed only) and is disabled with nothing changed');
const withOverride = [...rows, row('s3', 'cornerstone', true, { engine_label: 'win_now', override: 'cornerstone' })];
draft = U.applyMove(U.applyMove({}, withOverride, ['s1'], 'cornerstone'), withOverride, ['s3'], 'win_now');
assert(JSON.stringify(U.changedIds(withOverride, draft)) === JSON.stringify(['s1', 's3']), '5c. changedIds lists the two moves');
const body = U.savePayload('L1', withOverride, draft);
assert(body.league_id === 'L1' && JSON.stringify(body.set) === JSON.stringify({ s1: 'cornerstone' })
  && JSON.stringify(body.clear) === JSON.stringify(['s3']),
  '5d. Save sends only changed players: a new call is set, a move back to the engine label is clear',
  JSON.stringify(body));

// ── 6. Reset to engine ───────────────────────────────────────────────────
assert(/const reset = \(\) => \{ setDraft\(\(d\) => resetToEngine\(d, rows, position\)\);/.test(REVIEW)
  && /testID="founder-review\.reset"[\s\S]{0,80}onPress=\{reset\}/.test(REVIEW),
  '6a. Reset to engine runs resetToEngine for the visible position');
const reset = U.resetToEngine(draft, withOverride, 'RB');
assert(U.bandOf(withOverride[0], reset) === 'win_now' && U.bandOf(withOverride[4], reset) === 'win_now'
  && JSON.stringify(U.savePayload('L1', withOverride, reset)) === JSON.stringify({ league_id: 'L1', set: {}, clear: ['s3'] }),
  '6b. reset puts every row back on the engine label (a stored override becomes a clear)');
const fresh = U.resetToEngine(U.applyMove({}, rows, ['s1'], 'cornerstone'), rows, 'RB');
assert(U.changedIds(rows, fresh).length === 0, '6c. reset clears unsaved moves (0 changed)');
assert(Object.keys(U.resetToEngine(draft, withOverride, 'QB')).length === Object.keys(draft).length,
  '6d. reset touches only the visible position');
// An unlabelled player with a saved label (engine: none, server label: depth).
const unl = [row('u1', 'depth', null, { engine_label: null, override: 'depth', why_unlabelled: 'unprojected' })];
const back = U.resetToEngine({}, unl, 'RB');
assert(U.bandOf(unl[0], back) === 'none' && JSON.stringify(U.changedIds(unl, back)) === JSON.stringify(['u1'])
  && JSON.stringify(U.savePayload('L1', unl, back)) === JSON.stringify({ league_id: 'L1', set: {}, clear: ['u1'] }),
  '6e. reset returns an unlabelled player to No label, and Save clears his override');
assert(U.engineNote(unl[0], {}) === 'engine: No label' && U.engineNote(unl[0], back) === null
  && U.unlabelledWhy(unl[0]) === 'no projection',
  '6f. his note reads "engine: No label" until he is back in No label, which says why');
assert(U.changedIds(rows, U.resetToEngine(U.applyMove({}, rows, ['n1'], 'win_now'), rows, 'RB')).length === 0,
  '6g. reset drops an unsaved move of an unlabelled player (0 changed)');

// ── 7. Empty state names the server's reason ─────────────────────────────
assert(/testID="founder-review\.empty"[\s\S]{0,160}emptyReason\(pageQ\.data\?\.evidence\?\.reason\)/.test(REVIEW),
  '7a. no rows: the empty state renders emptyReason(evidence.reason)');
const reasons = [...(SEASON_VALUE.match(/REASONS = frozenset\(\{([^}]*)\}\)/) || ['', ''])[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
const fallback = U.emptyReason('made_up');
assert(reasons.length === 8 && reasons.filter((r) => r !== 'read_failed').every((r) => U.emptyReason(r) !== fallback),
  '7b. every server reason (but read_failed) has its own sentence', JSON.stringify(reasons));

// ── 8. Scope, FAB, testIDs, script ───────────────────────────────────────
assert(/position === 'QB' \? \(\s*<View style=\{styles\.scope\} testID="founder-review\.qb-scope">\s*<Text variant="title">\{scopeHeading\(pageQ\.data!\.qb_scope\)\}/.test(REVIEW),
  '8a. the QB segment names the format being edited (from the server’s qb_scope)');
assert(U.scopeHeading('superflex') === 'QB labels · Superflex leagues' && U.scopeHeading('single_qb') === 'QB labels · 1-QB leagues',
  '8b. scope headings');
assert(!/<FeedbackFAB\b/.test(REVIEW + SCREEN + BOARD), '8c. no FeedbackFAB mount (tab-stack screen; RootNav covers it)');
assert(/setPinnedBottomBarHeight\('founder_review', isFocused && hasRows \? footerH : 0\)/.test(REVIEW)
  && /setPinnedBottomBarHeight\('founder_review', 0\)/.test(REVIEW),
  '8d. the pinned footer reports its height while focused and clears on unmount');
for (const id of ['calibration.segment.grading', 'calibration.segment.founder']) {
  assert(SCREEN.includes(`testID="${id}"`), `8e. testID ${id}`);
}
for (const id of ['founder-review.save', 'founder-review.reset', 'founder-review.changed', 'founder-review.empty', 'founder-review.retry']) {
  assert(REVIEW.includes(`testID="${id}"`), `8f. testID ${id}`);
}
assert(PKG.scripts['test:founder-review'] === 'node tests/check-founder-review.js', '8g. npm run test:founder-review');

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
