#!/usr/bin/env node
// Founders' review, use case 2 — "Trade rules", the decline waterfall with a
// note per rule (docs/plans/founder-review/rule-waterfall-{scope,design}.md).
//
// WHY THIS EXISTS. The page is invisible to everyone but the founder, so its
// failure modes are silent: a "Trade rules" choice that shows on a server
// without the route, a table that drops or reorders rules (the operator asked
// for EVERY rule, in the engine's order, readable without memorising them),
// zero-removed rules hidden by default, a "0" printed where the server said a
// step was not measured, liked trades netted into a rule's count, a note field
// that loses its text when another row expands, a Save wired to the wrong
// rule, a note cap that disagrees with the server's, a poll that never stops,
// or a count printed without thousands separators.
//
// HONEST LABEL (G-035): §1-§2 and §5-§9 prove the PRESENCE of exact wirings in
// source; §3-§4 transpile and EXECUTE src/utils/ruleWaterfall.ts under node
// against the server's own catalog (parsed from backend/rule_catalog.py).
// Runtime proof is the manual TestFlight checklist in rule-waterfall-scope.md.
//
// Run: npm run test:founder-rule-waterfall
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
const HOST = code(read('src/components/founder/FounderReview.tsx'));
const PAGE = code(read('src/components/founder/RuleWaterfallReview.tsx'));
const API = code(read('src/api/founder.ts'));
const UTIL_SRC = read('src/utils/ruleWaterfall.ts');
const CATALOG_PY = readRoot('backend/rule_catalog.py');
const DATABASE_PY = readRoot('backend/database.py');
const PKG = JSON.parse(read('package.json'));

// Execute the util (zero runtime imports by contract).
assert(!/^\s*import\s+(?!type\b)/m.test(UTIL_SRC), '0a. utils/ruleWaterfall.ts has no runtime imports');
const js = ts.transpileModule(UTIL_SRC, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 } }).outputText;
const mod = { exports: {} };
new Function('module', 'exports', 'require', js)(mod, mod.exports, () => { throw new Error('no imports'); });
const U = mod.exports;

// The server's catalog, in its order: key, name, stage, kind.
const STAGE = { BUILDING: 'candidate building', BOTH_SIDES: 'both-sides check', DECK: 'deck rules', AFTER: 'after the deck is built' };
const CATALOG = [...CATALOG_PY.matchAll(/Rule\("(\w+)", "([^"]+)",[\s\S]*?\n\s+(BUILDING|BOTH_SIDES|DECK|AFTER), "(\w+)"/g)]
  .map((m) => ({ key: m[1], name: m[2], description: `What ${m[1]} checks.`, stage: STAGE[m[3]], kind: m[4],
    protects: 'both', setting: 'Fixed', live: true, question: null }));
assert(CATALOG.length === 45 && new Set(CATALOG.map((c) => c.key)).size === 45,
  '0b. the server catalog parses to its 45 rules', `parsed ${CATALOG.length}`);
const WATERFALL = CATALOG.filter((c) => c.kind === 'rule' || c.kind === 'search_limit');

// ── 1. The choice appears only when the server has the route ───────────────
assert(/if \(e instanceof ApiError && e\.status === 404\) return null;/.test(API)
  && /\/api\/founder\/rule-waterfall\?league_id=/.test(API),
  '1a. getRuleWaterfall answers null on 404 (an older server, or not a founder)');
assert(/const rulesAvailable = rulesQ\.data != null;/.test(HOST)
  && /if \(!rulesAvailable\) return <FounderLabelReview leagueId=\{leagueId\} \/>;/.test(HOST),
  '1b. without the route the section is the player label review alone (no choice rendered)');
assert(/const showRules = rulesAvailable && useCase === 'rules';/.test(HOST)
  && /testID="founder-review\.use\.labels"/.test(HOST) && /testID="founder-review\.use\.rules"/.test(HOST)
  && />Player labels</.test(HOST) && />Trade rules</.test(HOST),
  '1c. "Player labels | Trade rules" control, Trade rules only when available');
assert(/<FounderReview leagueId=\{leagueId as string\} leagueName=\{league\?\.league_name \?\? null\} \/>/.test(SCREEN)
  && /const showFounder = founder && section === 'founder';/.test(SCREEN),
  '1d. Calibration mounts the founder section (FounderReview) only under the server capability');
for (const [name, src] of [['FounderReview', HOST], ['RuleWaterfallReview', PAGE], ['api/founder', API]]) {
  assert(!/founder\.review|useFlag\(|useFeatureFlags|FOUNDER_ACCOUNTS|tester_allowlist/.test(src),
    `1e. ${name} reads no flag and no local allow-list`);
}

// ── 2. The page renders the table from the server's answer ──────────────────
assert(/const \{ sections, others \} = buildTable\(page\);/.test(PAGE)
  && /sections\.map\(\(section\) =>/.test(PAGE) && /others\.map\(\(row\) => <RuleRow/.test(PAGE),
  '2a. every section and every other rule renders from buildTable(page)');
assert(/<Text variant="title"[^>]*>\{row\.name\}<\/Text>/.test(PAGE)
  && /numberOfLines=\{open \? undefined : 2\}[^>]*>\s*\{row\.description\}/.test(PAGE)
  && /COPY\.more/.test(PAGE),
  '2b. each row shows the rule name and its description (two lines, tap for all of it)');
assert(/<Text variant="label" style=\{styles\.flexText\}>\{section\.title\}<\/Text>/.test(PAGE)
  && /formatCount\(section\.removed\)/.test(PAGE),
  '2c. stage section headers with the stage total');

// ── 3. Every catalog rule, in the server's order (executed) ─────────────────
const rowsFor = (catalog, statuses = {}) => {
  let remaining = 45056;
  return catalog.filter((c) => c.kind === 'rule' || c.kind === 'search_limit').map((c, i) => {
    const removed = statuses[c.key] === undefined ? (i % 3 === 0 ? 0 : 100 + i) : statuses[c.key].removed;
    const status = statuses[c.key] === undefined ? 'measured' : statuses[c.key].status;
    const row = { key: c.key, name: c.name, description: c.description, stage: c.stage, kind: c.kind, status,
      started: remaining, removed, remaining: remaining - removed, share_of_started: removed / 45056,
      share_of_reaching: removed / remaining };
    remaining -= removed;
    return row;
  });
};
const flat = (t) => t.sections.flatMap((s) => s.rows.map((r) => r.key));
const before = U.buildTable({ catalog: CATALOG, waterfall: null });
assert(JSON.stringify(flat(before)) === JSON.stringify(WATERFALL.map((c) => c.key)),
  '3a. before any run: every waterfall rule, in catalog order, from the catalog alone');
assert(before.sections.every((s) => s.removed === null) && before.sections.every((s) => s.rows.every(
  (r) => r.status === 'pending' && r.removed === null && r.remaining === null && r.name && r.description)),
  '3b. before any run: names and descriptions, counts empty');
assert(JSON.stringify(before.others.map((r) => r.key)) === JSON.stringify(
  CATALOG.filter((c) => !WATERFALL.includes(c)).map((c) => c.key)),
  '3c. the other catalog entries are listed too (for their notes)');
const rows = rowsFor(CATALOG, { revised_offer_replaced: { status: 'not_measured', removed: 0 },
  roster_protection: { status: 'not_run', removed: 0 } });
const stages = Object.values(STAGE).map((s) => ({ stage: s, removed: rows.filter((r) => r.stage === s).reduce((n, r) => n + r.removed, 0) }));
const w = { version: 'rule-waterfall-1', generator_version: 'owner-v2-bilateral-2', started_definition: 'Every …',
  teams: 12, started: 45056, served_generated: rows[rows.length - 1].remaining, added: 2,
  served: rows[rows.length - 1].remaining + 2, stages, rows, elapsed_ms: 1 };
const shuffled = [...CATALOG].reverse();     // the table follows the server's rows, not the catalog array
const after = U.buildTable({ catalog: shuffled, waterfall: w });
assert(JSON.stringify(flat(after)) === JSON.stringify(rows.map((r) => r.key)),
  '3d. after a run: one row per waterfall row, in the server\'s order');
assert(JSON.stringify(after.sections.map((s) => s.stage)) === JSON.stringify(Object.values(STAGE))
  && after.sections.every((s) => s.removed === stages.find((x) => x.stage === s.stage).removed),
  '3e. grouped under the four stages with their totals');
const zeros = after.sections.flatMap((s) => s.rows).filter(U.isZero);
assert(zeros.length > 5 && flat(after).length === WATERFALL.length,
  '3f. rules that removed nothing stay in the table (shown by default)');

// ── 4. Words not zeros, additions apart, numbers formatted (executed) ───────
const byKey = Object.fromEntries(after.sections.flatMap((s) => s.rows).map((r) => [r.key, r]));
assert(/Not measured/.test(U.statusWords(byKey.revised_offer_replaced) || '')
  && byKey.revised_offer_replaced.removed === null
  && /Not run/.test(U.statusWords(byKey.roster_protection) || '') && byKey.roster_protection.removed === null
  && U.statusWords(byKey.market_floor) === null,
  '4a. not_measured / not_run rows say so in words and carry no count');
assert(/\{words \? \(/.test(PAGE) && /testID=\{`founder-rules\.row\.\$\{row\.key\}\.status`\}>\{words\}/.test(PAGE),
  '4b. the row renders the words in place of the counts');
assert(U.addedLine(w).startsWith('+2 added after the deck was built') && U.addedLine({ ...w, added: 0 }) === null
  && !after.sections.flatMap((s) => s.rows).some((r) => r.removed === 2 && r.key === 'likes_you_added')
  && after.others.some((r) => r.key === 'likes_you_added' && r.removed === null),
  '4c. additions are their own line, never netted into a rule row');
assert(/testID="founder-rules\.added"/.test(PAGE) && /const added = w \? addedLine\(w\) : null;/.test(PAGE),
  '4d. the page renders the additions as a separate labelled line');
assert(U.formatCount(45056) === '45,056' && U.formatCount(1234567) === '1,234,567' && U.formatCount(215) === '215'
  && U.formatCount(0) === '0' && U.headerLine(w) === `Started with 45,056 candidate trades → ${U.formatCount(w.served)} served`,
  '4e. counts carry thousands separators; the header line is the spec\'s');
assert(!/\{row\.(removed|remaining)\}/.test(PAGE) && !/toLocaleString/.test(PAGE)
  && /formatCount\(row\.removed\)/.test(PAGE) && /formatCount\(row\.remaining\)/.test(PAGE),
  '4f. the page never prints a raw count');
assert(U.rowA11yLabel(byKey.market_floor, false) === `Fair by market value, removed ${U.formatCount(byKey.market_floor.removed)}, remaining ${U.formatCount(byKey.market_floor.remaining)}`
  && U.rowA11yLabel(byKey.revised_offer_replaced, true).endsWith('not measured, has a note')
  && /accessibilityLabel=\{rowA11yLabel\(row, hasNote\)\}/.test(PAGE),
  '4g. VoiceOver reads "rule name, removed N, remaining M" per row');
assert(/headerLine\(w\)/.test(PAGE) && /w\.started_definition/.test(PAGE) && /testID="founder-rules\.league"/.test(PAGE)
  && /relativeTime\(page\.run_at\)/.test(PAGE),
  '4h. header: the line, the server\'s "started with" definition, the league, the run time');

// ── 5. Zero rows: quieter, hideable, shown by default ───────────────────────
assert(/const \[hideZero, setHideZero\] = useState\(false\);/.test(PAGE)
  && /section\.rows\.filter\(\(r\) => !\(hideZero && isZero\(r\)\)\)/.test(PAGE)
  && /testID="founder-rules\.hide-zero"/.test(PAGE) && /quiet: isZero\(row\)/.test(PAGE),
  '5a. zero-removed rows shown by default, quieter, with a hide option');

// ── 6. A note per rule ──────────────────────────────────────────────────────
const backendCap = Number((DATABASE_PY.match(/^FOUNDER_NOTE_MAX_CHARS = (\d+)/m) || [])[1]);
assert(U.NOTE_MAX === backendCap && backendCap === 2000, '6a. the app\'s note cap equals the server\'s', `${U.NOTE_MAX} vs ${backendCap}`);
assert(/testID=\{`founder-rules\.row\.\$\{row\.key\}\.note`\}/.test(PAGE) && /maxLength=\{NOTE_MAX\}/.test(PAGE)
  && /<TextInput[\s\S]{0,400}multiline/.test(PAGE),
  '6b. every row has a multi-line note field capped at the server\'s limit');
assert(U.noteCounter(1799) === null && U.noteCounter(1800) === '1,800 / 2,000' && U.noteCounter(2000) === '2,000 / 2,000'
  && /const counter = noteCounter\(text\.length\);/.test(PAGE),
  '6c. a character counter near the cap');
assert(/mutationFn: \(\{ key, body \}: \{ key: string; body: string \}\) => saveRuleNote\(key, body\)/.test(PAGE)
  && /onSave: \(\) => saveM\.mutate\(\{ key: row\.key, body \}\)/.test(PAGE)
  && /disabled=\{!dirty \|\| saving\}/.test(PAGE) && /`\/api\/founder\/rule-notes\/\$\{encodeURIComponent\(ruleKey\)\}`/.test(API),
  '6d. Save per row sends that rule\'s text to PUT /api/founder/rule-notes/<key>, enabled only when changed');
assert(/testID=\{`founder-rules\.row\.\$\{row\.key\}\.saved`\}/.test(PAGE) && /noteByline\(note, relativeTime\)/.test(PAGE)
  && /testID=\{`founder-rules\.row\.\$\{row\.key\}\.history`\}/.test(PAGE) && /getRuleNoteHistory\(row\.key/.test(PAGE),
  '6e. saved state, last-edited line, and earlier versions on demand');
assert(/testID=\{`founder-rules\.row\.\$\{row\.key\}\.has-note`\}/.test(PAGE)
  && /const hasNote = !!note && note\.versions > 0 && note\.body !== '';/.test(PAGE),
  '6f. a saved note marks the collapsed row');
const savedNotes = U.notesByKey([{ rule_key: 'filler', body: 'Why 450?', versions: 1 }]);
assert(JSON.stringify(U.dirtyKeys({ filler: 'Why 450?  ', pool: 'new', market_floor: '' }, savedNotes)) === '["pool"]'
  && U.earlierVersions({ versions: 3 }) === 2 && U.earlierVersions({ versions: 1 }) === 0,
  '6g. dirty = text differing from the saved note (trimmed); earlier versions count');

// ── 7. Unsaved text survives; leaving asks first ───────────────────────────
assert(/const \[drafts, setDrafts\] = useState<Record<string, string>>\(\{\}\);/.test(PAGE)
  && /onChangeText: \(t: string\) => setDrafts\(\(d\) => \(\{ \.\.\.d, \[row\.key\]: t \}\)\)/.test(PAGE),
  '7a. drafts live in one page-level map keyed by rule (scrolling and expanding keep them)');
const rowFn = PAGE.slice(PAGE.indexOf('function RuleRow('));
assert(rowFn.length > 100 && !/useState<string>/.test(rowFn) && !/useState\(''\)/.test(rowFn),
  '7b. a row holds no text state of its own');
assert(/navigation\.addListener\('beforeRemove'/.test(PAGE) && /e\.preventDefault\(\);/.test(PAGE)
  && /useEffect\(\(\) => \{ unsavedCount = dirty\.length; \}, \[dirty\.length\]\);/.test(PAGE)
  && /export function confirmLeaveNotes\(proceed: \(\) => void\): void \{\s*if \(unsavedCount === 0\) \{/.test(PAGE)
  && /Alert\.alert\(COPY\.leaveTitle/.test(PAGE),
  '7c. leaving with unsaved notes asks first (navigator removal and in-screen switches)');
assert(/onPress=\{\(\) => confirmLeaveNotes\(\(\) => setUseCase\('labels'\)\)\}/.test(HOST)
  && /onPress=\{\(\) => confirmLeaveNotes\(\(\) => setSection\('grading'\)\)\}/.test(SCREEN),
  '7d. Player labels and Grading both go through the guard');

// ── 8. Run and poll ─────────────────────────────────────────────────────────
assert(U.pollInterval('running') === U.POLL_MS && U.POLL_MS === 2000
  && ['complete', 'failed', 'unsupported', 'none', undefined].every((s) => U.pollInterval(s) === false),
  '8a. polls every 2 s while running and stops on complete / failed / unsupported');
assert(/refetchInterval: \(q: [^)]*\) =>\s*pollInterval\(q\.state\.data\?\.status\)/.test(PAGE),
  '8b. the page query polls through pollInterval');
assert(/testID="founder-rules\.run"/.test(PAGE) && /label=\{running \? COPY\.running : COPY\.run\}/.test(PAGE)
  && /disabled=\{running\}/.test(PAGE) && /mutationFn: \(\) => startRuleWaterfall\(leagueId\)/.test(PAGE)
  && /api\.post\('\/api\/founder\/rule-waterfall', \{ league_id: leagueId \}/.test(API),
  '8c. Run for this league posts the run and shows a running state');
assert(/statusMessage\(page\)/.test(PAGE) && /The last run failed\./.test(UTIL_SRC) && /can't be measured/.test(UTIL_SRC)
  && U.statusMessage({ status: 'failed', error: 'The run took longer than 60 seconds and was stopped.' })
    .endsWith('stopped.') && U.statusMessage({ status: 'complete', error: null }) === null
  && /run_in_progress/.test(UTIL_SRC),
  '8d. a failed or unsupported run shows the server\'s reason; a refused start says why');

// ── 9. House rules ──────────────────────────────────────────────────────────
assert(!/<FeedbackFAB\b/.test(PAGE + HOST), '9a. no FeedbackFAB mount (tab-stack screen; RootNav covers it)');
assert(!/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(PAGE + HOST), '9b. no emoji');
assert(!/from 'react-native'[^;]*\bText\b/.test(PAGE.replace(/TextInput/g, '')) && /from '\.\.\/chalkline'/.test(PAGE),
  '9c. text goes through the Chalkline Text primitive');
assert(PKG.scripts['test:founder-rule-waterfall'] === 'node tests/check-founder-rule-waterfall.js',
  '9d. npm run test:founder-rule-waterfall');

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
