#!/usr/bin/env node
// Team Review structural guard (#357/#358/#359, flag `trades.team_review`).
//
// WHY THIS EXISTS. Team Review carries 15 backend tests, but every claim below
// is about client SHAPE — placement, absence, registration — which no backend
// test and no typecheck can see. Under D-056 a structural guard is the only
// automated evidence these get.
//
// What is pinned, and why each one is a real regression rather than a style:
//   1. TeamReviewScreen is registered in the TRADES stack and NOWHERE else.
//      A second registration would give it two entry stacks with different
//      back behavior.
//   2. It mounts NO FeedbackFAB. It is a tab-stack screen, already covered by
//      RootNav's single global mount — a local one is the #196/#197 double-FAB
//      bug, which shipped twice before.
//   3. The entry is NOT a TradeFinderModeBar chip. That component's own
//      measurement says its chips already exceed the usable width, so an
//      appended chip is invisible; this is D-092's entry-point decision.
//   4. Every beat id in the API type has a matching `team-review.beat.<id>`
//      testID, so a renamed beat cannot silently lose its guard.
//   5. The screen never renders a bare playoff percentage and never reads
//      title_pct — the same honesty rules as the card and League Summary.
//   6. The `plan` beat reads SAVED preferences, not the payload's mount-time
//      snapshot — "where you stand" has to mean now.
//   7. The `plan` beat gates nothing on `done.current`. That session ref is
//      what reduced it to one row (#369).
//   8. Every lever in the #369 inventory is present on the beat.
//   9. It READS asset_preferences and never writes them — one writer, the deck.
//  10. The single preference write always carries `team_outlook`, because the
//      route 400s without it and the client swallows the throw.
//  11. A scoped partner is handed to the #330 store and still consumed there.
//  12. The playoff forecast's outlook suggestion marks a chip; it never writes.
//  13. The `team_outlook` backfill on a non-outlook save (savePrefs, the plan
//      beat's positions taps) goes through `backfillOutlook`, which under
//      `source: 'projection'` returns the roster verdict, never the suggestion.
//
// Run: node tests/check-team-review.js   (or npm run test:team-review)
// CI picks it up automatically via the tests/check-*.js glob.

'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCREEN = path.join(ROOT, 'src/screens/TeamReviewScreen.tsx');
const API = path.join(ROOT, 'src/api/teamReview.ts');
const TABNAV = path.join(ROOT, 'src/navigation/TabNav.tsx');
const ROOTNAV = path.join(ROOT, 'src/navigation/RootNav.tsx');
const MODEBAR = path.join(ROOT, 'src/components/TradeFinderModeBar.tsx');

const pass = [], fail = [];
const ok = (n) => pass.push(n);
const bad = (n, d) => fail.push(`${n}\n      ${d}`);
const read = (p) => (fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : (bad('file exists', `missing ${path.relative(ROOT, p)}`), ''));
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const screen = read(SCREEN), api = read(API);
const tabnav = strip(read(TABNAV)), rootnav = strip(read(ROOTNAV)), modebar = strip(read(MODEBAR));
const s = strip(screen);

// 1 — registered once, in the Trades stack
{
  const inTab = /name="TeamReview"/.test(tabnav);
  const inRoot = /name="TeamReview"/.test(rootnav);
  if (!inTab) bad('1. registered in the Trades stack', 'no name="TeamReview" in TabNav.tsx');
  else if (inRoot) bad('1. registered ONLY in the Trades stack',
    'TeamReview also appears in RootNav.tsx — two stacks means two back behaviors');
  else ok('1. registered once, in the Trades stack');
}

// 2 — no local FeedbackFAB
{
  if (/FeedbackFAB/.test(s)) {
    bad('2. no local FeedbackFAB',
      'TeamReviewScreen references FeedbackFAB. It is a TAB-STACK screen and is ' +
      'already covered by RootNav\'s global mount (#188). A second FAB is the ' +
      '#196/#197 double-FAB bug.');
  } else ok('2. no local FeedbackFAB');
}

// 3 — not a mode chip
{
  if (/team[_-]?review/i.test(modebar)) {
    bad('3. entry is not a TradeFinderModeBar chip',
      'TradeFinderModeBar references team review. Its own source says the shipped ' +
      'chips already measure ~402pt against ~361pt usable, so an appended chip ' +
      'sits off-screen and is never seen (D-092 entry-point decision).');
  } else ok('3. entry is not a mode chip');
}

// 4 — every beat id has a testID
{
  const m = api.match(/export type BeatId\s*=([\s\S]*?);/);
  if (!m) bad('4. BeatId union is declared', 'no `export type BeatId` in api/teamReview.ts');
  else {
    const ids = [...m[1].matchAll(/'([a-z_]+)'/g)].map((x) => x[1]);
    const missing = ids.filter((id) => !s.includes(`team-review.beat.${id}`));
    if (!ids.length) bad('4. BeatId union has members', 'parsed zero beat ids');
    else if (missing.length) bad('4. every beat has a testID',
      `missing team-review.beat.<id> for: ${missing.join(', ')}`);
    else ok(`4. all ${ids.length} beats carry a testID`);
  }
}

// 5 — odds honesty
{
  if (/title_pct/.test(s)) {
    bad('5a. never reads title_pct',
      'title_pct is unrenderable at any week — an absence of demonstrated skill.');
  } else ok('5a. never reads title_pct');

  // #369 — REWRITTEN, and the rewrite is the point. The original read
  //   /\{[^}]*playoff_pct[^}]*\}/.test(s) && !/accessibilityLabel/.test(s)
  // — a whole-FILE escape hatch. The screen happened to contain zero
  // `accessibilityLabel` when it shipped, so the clause held; the moment any
  // unrelated control gained one (the plan beat's chips did) the assertion
  // could never fail again and would have kept passing while proving nothing.
  // Per-OCCURRENCE now: every `playoff_pct` must sit on a line that is itself
  // an accessibility label. Zero occurrences today, which is also fine.
  {
    const offenders = s.split('\n')
      .map((line, i) => ({ line, n: i + 1 }))
      .filter(({ line }) => /\bplayoff_pct\b/.test(line))
      .filter(({ line }) => !/accessibilityLabel/.test(line));
    if (offenders.length) {
      bad('5b. never renders a bare playoff percentage',
        `playoff_pct may feed a VoiceOver label ONLY; the visible surface is the ` +
        `band. Offending line(s): ${offenders.map((o) => o.n).join(', ')}`);
    } else ok('5b. never renders a bare playoff percentage');
  }

  if (!/BAND_LABEL/.test(s)) {
    bad('5c. renders the band, not a number',
      'no BAND_LABEL in the screen — the band is the only permitted odds rendering');
  } else ok('5c. renders the band');
}

// ── #369 — the plan beat is a STANDING SUMMARY, not a session receipt ──────
//
// The beat shipped rendering only what the user changed in THIS mount, gated on
// a `done.current` ref. Two things made that show one row: `positions_set` could
// never be true (the write 400'd — see 10 below), and skipping a beat left its
// lever invisible. 6-11 pin the rebuild. All six are structural claims about
// client shape and data source, which no backend test and no typecheck can see.

// Isolate the Plan component body, so a claim about the plan beat cannot be
// satisfied by an identical string somewhere else in a 900-line screen.
const planStart = s.indexOf('function Plan(');
const planBody = planStart === -1
  ? ''
  : (() => {
    const rest = s.slice(planStart + 1);
    const end = rest.search(/\nfunction \w/);
    return end === -1 ? rest : rest.slice(0, end);
  })();

// 6 — the beat reads SAVED preferences, not a mount-time snapshot
{
  if (!planBody) {
    bad('6. plan beat reads saved preferences', 'no `function Plan(` in the screen');
  } else {
    const reads = /getLeaguePreferences/.test(planBody)
      && /'league-prefs'/.test(planBody)
      && /refetchOnMount/.test(planBody);
    const stale = /data\.depth\.(acquire|trade_away)_positions/.test(planBody);
    if (!reads) {
      bad('6. plan beat reads saved preferences',
        'the plan beat must query GET /api/league/preferences on the ' +
        "['league-prefs', leagueId] key with refetchOnMount — the operator asked " +
        'for where you STAND, which is the saved row, not session state.');
    } else if (stale) {
      bad('6. plan beat reads saved preferences, not the stale payload snapshot',
        'the plan beat reads data.depth.*_positions — that is the team-review ' +
        "payload's 60s-stale snapshot, taken at screen mount BEFORE this " +
        "session's own writes. Read the prefs query.");
    } else ok('6. plan beat reads saved preferences (not the payload snapshot)');
  }
}

// 7 — no lever is gated on the session action ref
{
  if (!planBody) bad('7. plan beat is not a session receipt', 'no Plan body found');
  else if (/done\.current/.test(planBody)) {
    bad('7. plan beat is not a session receipt',
      'the plan beat references done.current. That ref is what made it show ' +
      'only the window: skip a beat and its lever vanished (#369). The beat is ' +
      'a standing summary of every lever — it must not gate on what happened ' +
      'this mount.');
  } else ok('7. plan beat is not a session receipt');
}

// 8 — every lever in the inventory is actually on the page
{
  // docs/feedback/items/369-plan-beat/scope.md §0.1. `trade.avoid_positions` is
  // deliberately ABSENT: it is not on origin/main (it lives on
  // feat/jon-360-362), so the beat takes no dependency on it. When that branch
  // lands, add 'Avoiding' here in the same commit as the row.
  const LEVERS = [
    'Window', 'Chasing', 'Shopping',
    'Never trade away', 'Targeting', 'Not interested in',
    'Trade with', 'Trade fairness', 'Trade idea', 'Focus', 'Specific players',
  ];
  const missing = LEVERS.filter((l) => !planBody.includes(l));
  if (missing.length) {
    bad(`8. all ${LEVERS.length} finder levers appear on the plan beat`,
      `missing: ${missing.join(', ')}. The operator asked for "the full set of ` +
      'adjustments a user can make with the trade finder" — a lever dropped ' +
      'from this page is the whole of #369 coming back.');
  } else ok(`8. all ${LEVERS.length} finder levers appear on the plan beat`);
}

// 9 — the beat shows the asset lists; it does not become a second writer
{
  if (/setAssetPref/.test(s)) {
    bad('9. no second asset_preferences writer',
      'TeamReviewScreen references setAssetPref. Untouchable/target/' +
      'not-interested are written from the deck; a second writer here means ' +
      'two surfaces racing one table for no gain (D-131).');
  } else if (!/getAssetPrefs/.test(planBody)) {
    bad('9. the plan beat reads the asset lists',
      'no getAssetPrefs in the plan beat — the player rules are three of the ' +
      'levers the summary claims to cover.');
  } else ok('9. reads asset prefs, never writes them');
}

// 10 — every preference write carries team_outlook
{
  const calls = (s.match(/saveLeaguePreferences\(/g) || []).length;
  const backfilled = /saveLeaguePreferences\(\s*leagueId,\s*\{\s*team_outlook:/.test(s);
  if (calls !== 1) {
    bad('10. exactly one preference write site',
      `found ${calls} saveLeaguePreferences( call sites; expected 1. Every beat ` +
      'writes through the single savePrefs helper so the team_outlook backfill ' +
      'below cannot be bypassed.');
  } else if (!backfilled) {
    bad('10. every preference write carries team_outlook',
      'POST /api/league/preferences 400s on a body without team_outlook ' +
      '(backend/server.py:15788) and apiRequest throws on non-2xx ' +
      '(api/client.ts:553). The depth beat posted a positions-only body, so its ' +
      'write threw EVERY time, done.current.add("positions_set") never ran, the ' +
      'catch swallowed it and no analytics fired — which is why the plan beat ' +
      'could only ever show the window (#369). The literal must lead with ' +
      'team_outlook, with ...patch spread AFTER it so an explicit value wins.');
  } else ok('10. the single preference write always carries team_outlook');
}

// 11 — the scoped partner is actually applied on exit
{
  const tradesScreen = strip(read(path.join(ROOT, 'src/screens/TradesScreen.tsx')));
  if (!/setHandoff\(\{/.test(s)) {
    bad('11. the scoped partner reaches the deck',
      'the plan beat\'s finish action does not call setHandoff. The partners ' +
      'beat recorded a manager in local state and nothing applied it, so ' +
      '"I\'ve already pointed the finder at it" was false and the "Trade with" ' +
      'row was decoration. LLD §4 specifies the #330 handoff store.');
  } else if (!/setHandoff\(null\)/.test(tradesScreen)) {
    bad('11. the deck still consumes the handoff',
      'TradesScreen no longer consumes the #330 handoff (setHandoff(null) is ' +
      'gone), so the plan beat now hands the scoped partner to nobody.');
  } else ok('11. the scoped partner is handed to the deck and consumed there');
}

// ── 12 — the playoff forecast's outlook suggestion marks, it never writes ──
//
// `window.projection` (flag `league.projection_outlook`) can name any of the
// four outlooks, including the two extremes the roster models never claim. The
// beat shows it, marks its chip, and stops: the saved outlook changes only
// through Confirm / a chip tap, exactly as before. A suggestion that reached
// `savePrefs` from an effect would rewrite a saved outlook because a forecast
// moved. With no `projection` key none of this renders.
{
  const winStart = s.indexOf('function Window(');
  const winBody = winStart === -1 ? '' : (() => {
    const rest = s.slice(winStart + 1);
    const end = rest.search(/\nfunction \w/);
    return end === -1 ? rest : rest.slice(0, end);
  })();
  const outsideWin = winStart === -1 ? s : s.replace(winBody, '');
  // `backfillOutlook` (§13) is the one place outside the beat allowed to name
  // the 'projection' source — it exists to keep the suggestion OUT of writes.
  const helperSrc = (/\nfunction backfillOutlook\([\s\S]*?\n\}\n/.exec(outsideWin) || [''])[0];
  const outside = outsideWin.replace(helperSrc, '\n');
  const count = (hay, needle) => hay.split(needle).length - 1;

  if (!winBody) bad('12a. the Window beat exists', 'no `function Window(` in the screen');
  else if (/savePrefs|saveLeaguePreferences|onSave|useEffect|useMutation|useQuery/.test(winBody)) {
    bad('12a. the window beat holds no write, effect or query',
      'function Window references savePrefs / saveLeaguePreferences / onSave / an effect / a query. ' +
      'The beat only DISPLAYS the suggestion; the write is the footer Confirm.');
  } else if (count(winBody, 'onSelect(') !== 1 || !winBody.includes('onPress={() => onSelect(o)}')) {
    bad('12a. the only thing the window beat can do is select a chip, on a press',
      `found ${count(winBody, 'onSelect(')} onSelect( call(s); expected exactly \`onPress={() => onSelect(o)}\``);
  } else ok('12a. the window beat only selects a chip on a press — no write, effect or query');

  if (/\bprojection\b|recommended_outlook|playoff_probability/.test(outside)) {
    bad('12b. the projection block is read inside the window beat only',
      'window.projection / recommended_outlook / playoff_probability is referenced outside function Window. ' +
      'The screen\'s selection and write logic must not branch on the suggestion.');
  } else if (!outside.includes('const declared = outlook ?? data.window.declared ?? data.window.inferred;')) {
    bad('12b. the preselected chip is unchanged',
      'expected `const declared = outlook ?? data.window.declared ?? data.window.inferred;` (saved outlook first, else the server\'s inferred — the chip the user sees and Confirms)');
  } else ok('12b. the projection block is read inside the window beat (and backfillOutlook) only; the preselected chip is unchanged');

  // ── 13 — a write that is NOT an outlook choice never saves the suggestion ──
  // Under `source: 'projection'`, `window.inferred` IS the forecast's
  // suggestion. `savePrefs` and the plan beat's positions taps must send a
  // `team_outlook` (the route 400s without one); when nothing is saved and
  // nothing was picked, that backfill is the ROSTER verdict, never the
  // suggestion. Any other source: `inferred`, exactly as before.
  if (!helperSrc) {
    bad('13a. backfillOutlook exists', 'no module-level `function backfillOutlook(` in the screen');
  } else {
    const ts = require('typescript');
    const lib = {};
    new Function('exports', ts.transpileModule(`${helperSrc}\nexports.f = backfillOutlook;`, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    }).outputText)(lib);
    const f = lib.f;
    const cases = [
      [{ source: 'projection', inferred: 'championship', roster_inferred: 'rebuilder' }, 'rebuilder'],
      [{ source: 'projection', inferred: 'jets', roster_inferred: 'contender' }, 'contender'],
      [{ source: 'projection', inferred: 'contender' }, 'not_sure'],
      [{ source: 'odds', inferred: 'contender', roster_inferred: 'rebuilder' }, 'contender'],
      [{ source: 'composite', inferred: 'rebuilder', roster_inferred: 'rebuilder' }, 'rebuilder'],
      [{ source: 'roster', inferred: 'not_sure' }, 'not_sure'],
      [{ inferred: 'contender' }, 'contender'],
      [undefined, 'not_sure'],
    ];
    const wrong = cases.filter(([w, want]) => f(w) !== want);
    if (wrong.length) {
      bad('13a. backfillOutlook never returns the projection suggestion',
        wrong.map(([w, want]) => `${JSON.stringify(w)} → ${JSON.stringify(f(w))}, expected ${want}`).join('; '));
    } else ok('13a. backfillOutlook: projection → roster_inferred ?? not_sure; any other source → inferred (executed)');
  }
  if (!/const fallbackOutlook: OutlookOption =\s*outlook \?\? data\?\.window\.declared \?\? backfillOutlook\(data\?\.window\);/.test(outside)) {
    bad('13b. savePrefs backfills through backfillOutlook',
      'expected `outlook ?? data?.window.declared ?? backfillOutlook(data?.window)` — a positions save must not write the suggestion');
  } else ok('13b. savePrefs backfills team_outlook through backfillOutlook');
  if (!/outlook: saved\.team_outlook \?\? data\.window\.declared \?\? backfillOutlook\(data\.window\),/.test(planBody)) {
    bad('13c. the plan beat\'s draft outlook backfills through backfillOutlook',
      'expected `saved.team_outlook ?? data.window.declared ?? backfillOutlook(data.window)` — a positions tap posts it as team_outlook');
  } else ok('13c. the plan beat\'s draft outlook (posted on a positions tap) backfills through backfillOutlook');
  // Every other read of `window.inferred` outside the beat is display-only.
  const reads = (outside.match(/[^\n]*window\??\.inferred[^\n]*/g) || []).map((l) => l.trim());
  const allowed = [
    'const declared = outlook ?? data.window.declared ?? data.window.inferred;',
    'const mine = data.window.declared ?? data.window.inferred;',
  ];
  const stray = reads.filter((l) => !allowed.includes(l));
  if (stray.length || reads.length !== allowed.length) {
    bad('13d. no other path reads window.inferred outside the window beat',
      `unexpected reads: ${JSON.stringify(stray)} (found ${reads.length}, expected the window-beat preselection + the partners heading)`);
  } else ok('13d. window.inferred outside the beat: the visible preselection and the partners heading only');

  const calls = [...outside.matchAll(/savePrefs\(/g)].length;
  const pressed = [...outside.matchAll(/onPress=\{async \(\) => \{\s*await savePrefs\(/g)].length;
  const effects = outside.match(/useEffect\(\(\) => \{[\s\S]*?\n  \}, \[[^\]]*\]\);/g) || [];
  const writing = effects.filter((e) => /savePrefs|saveLeaguePreferences|onSave\(|commit\(/.test(e));
  if (count(s, 'saveLeaguePreferences(') !== 1) {
    bad('12c. one preferences write', `found ${count(s, 'saveLeaguePreferences(')} saveLeaguePreferences( calls; expected the one inside savePrefs`);
  } else if (calls !== 2 || pressed !== 2) {
    bad('12c. savePrefs runs only from a press',
      `found ${calls} savePrefs( call(s), ${pressed} of them the first statement of an onPress handler; expected 2 and 2 ` +
      '(the window Confirm and the depth Save & continue)');
  } else if (!effects.length || writing.length) {
    bad('12c. no effect writes a preference', `${writing.length} effect(s) reach savePrefs / onSave / commit`);
  } else ok('12c. the preferences write runs only from a press (Confirm / Save & continue / the plan beat\'s chips)');

  const gate = /const recommended = w\.source === 'projection' && pr\?\.status === 'available'\s*\? pr\.recommended_outlook : null;/.test(winBody)
    && winBody.includes('const fromProjection = !!pr && !!recommended;');
  const line = /\{fromProjection && pr\.differs \? \(\s*<View testID="team-review\.window\.projection">/.test(winBody);
  const chip = /const suggested = fromProjection && recommended === o;/.test(winBody)
    && /\{suggested \? \(\s*<View testID="team-review\.outlook\.suggested">\s*<Badge label="Suggested" color=\{flare\.base\} colorText \/>/.test(winBody);
  const selected = winBody.includes('selected === o && styles.chipSel');
  if (!gate) bad('12d. the suggestion needs source "projection" AND status "available"', 'the `recommended` / `fromProjection` gate is missing or changed');
  else if (!line) bad('12d. the "Consider" line shows only when the recommendation differs', 'expected `{fromProjection && pr.differs ? (` around team-review.window.projection');
  else if (!chip || !selected) bad('12d. the recommended chip is marked, not selected', 'expected the flare "Suggested" badge under `suggested`, with selection still `selected === o`');
  else ok('12d. available + differs shows the line; the recommended chip is marked, never selected');

  // 5b's rule (the band, never a percentage) has ONE sanctioned exception: the
  // forecast's own probability, inside the projection line.
  const block = (/<View testID="team-review\.window\.projection">[\s\S]*?<\/View>/.exec(winBody) || [''])[0];
  if (count(s, 'playoff_probability') !== count(block, 'playoff_probability') || !count(block, 'playoff_probability')) {
    bad('12e. the forecast percentage renders in the projection line only',
      'playoff_probability is read outside the team-review.window.projection block');
  } else if (!/\{pr\.suggestion \? \(\s*<ChalkText style=\{styles\.read\}>\{pr\.suggestion\}<\/ChalkText>/.test(block)
    || !/\{!fromProjection && pr\?\.status === 'unavailable' && pr\.explanation \? \(\s*<ChalkText style=\{styles\.dim\}>\{pr\.explanation\}<\/ChalkText>/.test(winBody)) {
    bad('12e. the server\'s sentences are rendered as given',
      'expected {pr.suggestion} inside the projection line and {pr.explanation} as the dim note when unavailable');
  } else ok('12e. the percentage lives in the projection line only; server copy is rendered as given');

  if (!/source\?: 'roster' \| 'odds' \| 'composite' \| 'projection';/.test(api)
    || !/projection\?: OutlookRecommendation;/.test(api)) {
    bad('12f. the wire type carries the optional projection block', "expected `source?: … | 'projection'` and `projection?: OutlookRecommendation` on TeamReviewWindow");
  } else ok('12f. TeamReviewWindow types the optional projection block');
}

console.log(`\ncheck-team-review: ${pass.length} passed, ${fail.length} failed`);
for (const p of pass) console.log(`  ✓ ${p}`);
if (fail.length) {
  console.error('\nFAILURES:');
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.error('\nThese pin operator decisions (D-092) and cross-client invariants. ' +
    'If a change is genuinely intended, update DECISIONS.md / cross-client-invariants.md ' +
    'in the SAME commit.\n');
  process.exit(1);
}
console.log('');
