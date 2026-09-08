#!/usr/bin/env node
// G-423 structural guard — #424 "Outlook · Not set" with a saved outlook, and
// #423 team review completion that never showed on TradesHome.
//
// WHY THIS EXISTS. Both bugs were SHAPE, not logic: a row rendered a literal
// string with no data source behind it (#424), and a marker was written on
// one button and read once per mount under a screen that never remounts
// (#423). No backend test sees either; under D-056 a structural guard is the
// only automated evidence they get. Every assertion below is one the planner
// proved RED by sabotage (docs/feedback/items/423-team-review-not-registering/
// prd.md §5) — restore the literal, delete the query, hand-copy the table,
// drop the savePrefs invalidation, drop the plan-beat write, revert the card
// to a mount-only read.
//
//   1. The merged calculator's `calc.outlook-fallback` text derives from the
//      saved `team_outlook` via `outlookDisplayName`; 'Not set' is ONLY a
//      null fallback (`?? 'Not set'` / `: 'Not set'`), never the whole line.
//   2. InLeagueCalculator carries the shared ['league-prefs', leagueId] query
//      (`getLeaguePreferences`) that every preference writer invalidates.
//   3. ONE display-name table: `outlookDisplayName` is exported from
//      OutlookBiasReceipt (which owns LEAN — exactly the four directional
//      values, `not_sure` → "Not sure" alongside) and imported by the
//      calculator; neither the calculator nor TradesScreen hand-copies it.
//   4. Every file that calls `saveLeaguePreferences(` also invalidates
//      ['league-prefs'; in TeamReviewScreen the invalidation sits INSIDE
//      `savePrefs` (between its declaration and its dependency array), so the
//      window and depth beats invalidate too, not just the plan beat.
//   5. TeamReviewScreen records completion when the `plan` beat becomes
//      current AND still from the `team-review.finish` handler.
//   6. TeamReviewEntryCard derives `completed` from the
//      `useTeamReviewCompletion` store — no mount-time read of the done key —
//      and `markTeamReviewCompleted` marks the store before anything touches
//      AsyncStorage; the store itself sets memory before it persists.
//
// Run: node tests/check-outlook-row-source.js   (or npm run test:outlook-row-source)
// CI picks it up automatically via the tests/check-*.js glob.

'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const CALC = path.join(ROOT, 'src/components/InLeagueCalculator.tsx');
const RECEIPT = path.join(ROOT, 'src/components/OutlookBiasReceipt.tsx');
const CARD = path.join(ROOT, 'src/components/TeamReviewEntryCard.tsx');
const SCREEN = path.join(ROOT, 'src/screens/TeamReviewScreen.tsx');
const TRADES = path.join(ROOT, 'src/screens/TradesScreen.tsx');
const STORE = path.join(ROOT, 'src/state/teamReviewCompletion.ts');
const API = path.join(ROOT, 'src/api/league.ts');

const pass = [], fail = [];
const ok = (n) => pass.push(n);
const bad = (n, d) => fail.push(`${n}\n      ${d}`);
const read = (p) => (fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : (bad('file exists', `missing ${path.relative(ROOT, p)}`), ''));
// Comments carry the OLD copy as history; only code may satisfy or trip a claim.
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\{\/\*[\s\S]*?\*\/\}/g, '');
const between = (src, from, to) => {
  const i = src.indexOf(from);
  if (i === -1) return '';
  const j = src.indexOf(to, i + from.length);
  return j === -1 ? src.slice(i) : src.slice(i, j);
};

const calc = strip(read(CALC));
const receipt = strip(read(RECEIPT));
const card = strip(read(CARD));
const screen = strip(read(SCREEN));
const trades = strip(read(TRADES));
const store = strip(read(STORE));

// ── 1. the fallback row's text has a data source ────────────────────────────
{
  const block = between(calc, 'testID="calc.outlook-fallback"', 'testID="calc.outlook-fallback.change"');
  if (!block) {
    bad('1a. calc.outlook-fallback block exists', 'no testID="calc.outlook-fallback" in InLeagueCalculator.tsx');
  } else if (!/outlookDisplayName\(/.test(block) || !/team_outlook/.test(block)) {
    bad('1a. fallback text derives from the saved team_outlook',
      'the calc.outlook-fallback block does not render outlookDisplayName(<prefs>.team_outlook). ' +
      '#424: the row read no preference at all and showed "Not set" to every user on the merged landing.');
  } else ok('1a. fallback text derives from team_outlook via outlookDisplayName');

  if (/Outlook · Not set/.test(calc)) {
    bad('1b. no literal "Outlook · Not set" line',
      'InLeagueCalculator renders the whole line as a literal again — that is #424 verbatim. ' +
      '"Not set" may only be the null branch of the saved value.');
  } else ok('1b. no literal "Outlook · Not set" line');

  const offenders = calc.split('\n')
    .map((line, n) => ({ line, n: n + 1 }))
    .filter(({ line }) => /'Not set'/.test(line))
    .filter(({ line }) => !/(\?\?|:)\s*'Not set'/.test(line));
  if (offenders.length) {
    bad('1c. "Not set" appears only as a null fallback',
      `'Not set' on line(s) ${offenders.map((o) => o.n).join(', ')} is not a \`?? 'Not set'\` / \`: 'Not set'\` fallback`);
  } else ok('1c. "Not set" appears only as a null fallback');
}

// ── 2. the calculator carries the shared prefs query ────────────────────────
{
  const hasKey = /queryKey:\s*\['league-prefs',\s*leagueId\]/.test(calc);
  const hasFn = /queryFn:\s*\(\)\s*=>\s*getLeaguePreferences\(leagueId\)/.test(calc);
  const imported = /import \{[^}]*\bgetLeaguePreferences\b[^}]*\} from '\.\.\/api\/league'/.test(calc);
  if (!hasKey || !hasFn || !imported) {
    bad("2. InLeagueCalculator queries ['league-prefs', leagueId] via getLeaguePreferences",
      `queryKey ${hasKey ? 'ok' : 'MISSING'}, queryFn ${hasFn ? 'ok' : 'MISSING'}, import ${imported ? 'ok' : 'MISSING'}. ` +
      'The row must read the SAME key the writers invalidate (TradeDnaSheet, TradesScreen, ' +
      'TradeFinderHubScreen, TeamReviewScreen) or it can disagree with all of them.');
  } else ok("2. InLeagueCalculator queries ['league-prefs', leagueId] via getLeaguePreferences");
}

// ── 3. one display-name table ───────────────────────────────────────────────
{
  const exported = /export function outlookDisplayName\(/.test(receipt);
  const imports = /import OutlookBiasReceipt, \{[^}]*\boutlookDisplayName\b[^}]*\} from '\.\/OutlookBiasReceipt'/.test(calc);
  if (!exported) bad('3a. outlookDisplayName is exported from OutlookBiasReceipt', 'no `export function outlookDisplayName(` — the receipt owns LEAN, so it owns the names');
  else if (!imports) bad('3a. InLeagueCalculator imports outlookDisplayName from ./OutlookBiasReceipt', 'the calculator does not import the helper — a second table is a second vocabulary');
  else ok('3a. outlookDisplayName exported by the receipt, imported by the calculator');

  const lean = between(receipt, 'const LEAN', '};');
  const keys = [...lean.matchAll(/^\s*([a-z_]+):\s*\{/gm)].map((m) => m[1]);
  const want = ['championship', 'contender', 'rebuilder', 'jets'];
  if (keys.length !== 4 || want.some((k) => !keys.includes(k))) {
    bad('3b. LEAN maps exactly the four directional values',
      `LEAN keys: [${keys.join(', ')}]; expected exactly ${want.join('/')}. not_sure belongs in the display table, not the lean table (no bias ⇒ no receipt).`);
  } else ok('3b. LEAN maps exactly the four directional values');

  if (!/not_sure:\s*'Not sure'/.test(receipt)) {
    bad('3c. the helper handles not_sure → "Not sure"',
      "no `not_sure: 'Not sure'` in OutlookBiasReceipt — not_sure IS a declared value and must never read \"Not set\" (#394 ruling).");
  } else ok('3c. not_sure → "Not sure" lives in the receipt');

  const copied = (src, name) => /championship:\s*'All-in'|rebuilder:\s*'Rebuilding'/.test(src) ? name : null;
  const dupes = [copied(calc, 'InLeagueCalculator'), copied(trades, 'TradesScreen')].filter(Boolean);
  if (dupes.length) {
    bad('3d. no hand-copied outlook name table outside the receipt',
      `${dupes.join(', ')} carries its own championship/rebuilder → name literals. Alias the export instead (#424 was two tables drifting).`);
  } else if (!/\bOUTLOOK_DISPLAY_NAME\b/.test(trades) || !/from '\.\.\/components\/OutlookBiasReceipt'/.test(trades)) {
    bad('3e. TradesScreen aliases the exported table',
      'TradesScreen no longer reads OUTLOOK_DISPLAY_NAME from OutlookBiasReceipt (orchestrator ruling Q2, 2026-09-08).');
  } else ok('3d/e. no hand-copied table; TradesScreen aliases the export');
}

// ── 4. every writer invalidates; TeamReviewScreen's does so inside savePrefs ─
{
  const SRC = path.join(ROOT, 'src');
  const walk = (dir, out = []) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p, out);
      else if (/\.tsx?$/.test(e.name)) out.push(p);
    }
    return out;
  };
  const writers = walk(SRC)
    .filter((p) => p !== API)
    .filter((p) => /saveLeaguePreferences\(/.test(strip(fs.readFileSync(p, 'utf8'))));
  const missing = writers.filter((p) => !/invalidateQueries\(\{\s*queryKey:\s*\['league-prefs'/.test(strip(fs.readFileSync(p, 'utf8'))));
  if (!writers.length) bad('4a. preference writers found', 'no file calls saveLeaguePreferences( — the walk is broken');
  else if (missing.length) {
    bad("4a. every saveLeaguePreferences( caller invalidates ['league-prefs'",
      `missing in: ${missing.map((p) => path.relative(ROOT, p)).join(', ')}. A write that does not invalidate leaves every reader of the shared key stale for up to 5 minutes.`);
  } else ok(`4a. all ${writers.length} preference writers invalidate ['league-prefs'`);

  const decl = screen.indexOf('const savePrefs = useCallback(');
  const deps = decl === -1 ? -1 : screen.indexOf('}, [', decl);
  const body = decl === -1 || deps === -1 ? '' : screen.slice(decl, deps);
  if (!body) bad('4b. savePrefs is a useCallback with a dependency array', 'could not isolate `const savePrefs = useCallback(` … `}, [` in TeamReviewScreen');
  else if (!/saveLeaguePreferences\(/.test(body)) bad('4b. savePrefs is the write site', 'saveLeaguePreferences( is not inside savePrefs');
  else if (!/invalidateQueries\(\{\s*queryKey:\s*\['league-prefs',\s*leagueId\]\s*\}\)/.test(body)) {
    bad("4b. TeamReviewScreen invalidates ['league-prefs', leagueId] INSIDE savePrefs",
      'the invalidation is not between `const savePrefs` and its dependency array. Only the plan beat invalidated before; ' +
      'the window and depth beats left the landing row stale (#424 latent half).');
  } else ok("4b. TeamReviewScreen invalidates ['league-prefs', leagueId] inside savePrefs");
}

// ── 5. completion is recorded on reaching the plan beat, and on finish ───────
{
  const lines = screen.split('\n');
  const planCtx = lines.some((line, i) =>
    /===\s*'plan'/.test(line)
    && lines.slice(i, i + 4).some((l) => /markTeamReviewCompleted\(/.test(l)));
  if (!planCtx) {
    bad("5a. markTeamReviewCompleted fires in a beat === 'plan' context",
      "no markTeamReviewCompleted( within 3 lines of a `=== 'plan'` test. Completion = reaching the plan beat " +
      '(operator ruling 2026-09-08); a button-only write misses back/header/tab exits — #423.');
  } else ok("5a. markTeamReviewCompleted fires when the plan beat is current");

  const finish = between(screen, 'testID="team-review.finish"', 'testID="');
  if (!finish) bad('5b. team-review.finish handler exists', 'no testID="team-review.finish" in TeamReviewScreen');
  else if (!/markTeamReviewCompleted\(/.test(finish)) {
    bad('5b. the finish handler still records completion',
      'team-review.finish no longer calls markTeamReviewCompleted — the store is idempotent, keep both writers');
  } else ok('5b. the finish handler still records completion');
}

// ── 6. the card reads the store; the marker writes memory first ─────────────
{
  const comp = card.slice(card.indexOf('export default function TeamReviewEntryCard'));
  if (!comp) bad('6a. TeamReviewEntryCard component found', 'no `export default function TeamReviewEntryCard`');
  else if (!/useTeamReviewCompletion\(\s*\(s\)\s*=>/.test(comp) || !/\bcompleted\b/.test(comp)) {
    bad('6a. TeamReviewEntryCard derives `completed` from useTeamReviewCompletion',
      'the component does not subscribe to the store. TradesHome stays mounted under the pushed review, ' +
      'so a mount-time read can never show "done" until relaunch (#423).');
  } else if (/ftf_team_review_completed|DONE_KEY|readMap\(DONE_KEY/.test(comp)) {
    bad('6a. no mount-time read of the done key in the component',
      'the component body still reads the completion key from AsyncStorage — that is the read half of #423 coming back');
  } else if (!/collapsed\s*\|\|\s*completed/.test(comp)) {
    bad('6a. minimized = collapsed OR completed', 'the minimized branch no longer ORs `completed` in — a done review would render the full card');
  } else ok('6a. TeamReviewEntryCard derives completed from the store, no mount-time done read');

  const marker = between(card, 'export function markTeamReviewCompleted', '\n}');
  const markAt = marker.search(/\.mark\(/);
  const setAt = marker.search(/setItem\(/);
  if (!marker) bad('6b. markTeamReviewCompleted exists in TeamReviewEntryCard', 'the import site TeamReviewScreen uses is gone');
  else if (markAt === -1 || (setAt !== -1 && setAt < markAt)) {
    bad("6b. markTeamReviewCompleted calls the store's mark before any AsyncStorage.setItem",
      'the marker no longer updates the store first — a disk-first write races the pop back to TradesHome');
  } else ok("6b. markTeamReviewCompleted marks the store first");

  const mark = between(store, 'mark: (leagueId) =>', '\n  },');
  const sAt = mark.search(/\bset\(/);
  const pAt = mark.search(/setItem\(/);
  if (!/export const useTeamReviewCompletion = create</.test(store)) bad('6c. teamReviewCompletion store exists', 'no `export const useTeamReviewCompletion = create<` in src/state/teamReviewCompletion.ts');
  else if (!/'ftf_team_review_completed'/.test(store)) bad('6c. the store mirrors the SAME device key', "the store no longer persists to 'ftf_team_review_completed' — a completed league on an updated device would forget it");
  else if (sAt === -1 || pAt === -1 || pAt < sAt) {
    bad('6c. store.mark sets memory synchronously before persisting',
      `in mark: set( at ${sAt}, setItem( at ${pAt} — memory must be updated first so the card sees it on the very next render`);
  } else ok('6c. store.mark sets memory before it persists, same device key');
}

console.log(`\ncheck-outlook-row-source: ${pass.length} passed, ${fail.length} failed`);
for (const p of pass) console.log(`  ✓ ${p}`);
if (fail.length) {
  console.error('\nFAILURES:');
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.error('\nThese pin the G-423 fix (docs/feedback/items/423-team-review-not-registering/prd.md §3/§5). ' +
    'If a change is genuinely intended, update the PRD and DECISIONS.md in the SAME commit.\n');
  process.exit(1);
}
console.log('');
