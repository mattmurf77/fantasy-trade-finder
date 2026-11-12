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
//   5. The screen never renders the simulator's bare `playoff_pct` and never
//      reads title_pct — the same honesty rules as the card and League
//      Summary. (The saved forecast's percentage is §14 and §12e.)
//   6. The `plan` beat reads SAVED preferences, not the payload's mount-time
//      snapshot — "where you stand" has to mean now.
//   7. The `plan` beat gates nothing on `done.current`. That session ref is
//      what reduced it to one row (#369).
//   8. Every lever in the #369 inventory is present on the beat.
//   9. It READS asset_preferences and never writes them — one writer, the deck.
//  10. The single preference write sends exactly what the user chose: no
//      `team_outlook` backfill (2026-11-12 fix 5 — the backfill saved the
//      roster read as an outlook the user never picked; the route now takes a
//      positions-only body).
//  11. A scoped partner is handed to the #330 store and still consumed there.
//  12. The playoff forecast's outlook suggestion marks a chip; it never writes.
//  13. No backfill exists any more: a positions save (savePrefs, the plan
//      beat's positions taps) carries no `team_outlook` unless one is saved.
//  14-20. docs/feedback/items/357-team-review/2026-11-12-current-data-fixes.md:
//      the saved forecast on the standing beat (14), the shared outlook names
//      and the catalog's outlook rules (15), refetch after a save (16), the
//      plan beat's player rules card (18), the window's save-state line (19),
//      and the "Preferences changed" hand-back to Find a Trade (20).
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
    'label="Keep"', 'label="Move"', 'Targeting', 'Not interested in',
    'Trade with', 'Trade fairness', 'Trade idea', 'Focus', 'Specific players',
  ];
  const missing = LEVERS.filter((l) => !planBody.includes(l));
  if (missing.length) {
    bad(`8. all ${LEVERS.length} finder levers appear on the plan beat`,
      `missing: ${missing.join(', ')}. The operator asked for "the full set of ` +
      'adjustments a user can make with the trade finder" — a lever dropped ' +
      'from this page is the whole of #369 coming back.');
  } else if (/Never trade away|every dial/.test(planBody)) {
    bad('8. the plan beat names Keep "Keep" and claims no "every dial"',
      'found "Never trade away" or "every dial" in the plan beat (2026-11-12 fix 6)');
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

// 10 — the single preference write sends exactly what the user chose
{
  const calls = (s.match(/saveLeaguePreferences\(/g) || []).length;
  const saveBody = (/const savePrefs = useCallback\(async \([\s\S]*?\n  \}, \[[^\]]*\]\);/.exec(s) || [''])[0];
  if (calls !== 1) {
    bad('10. exactly one preference write site',
      `found ${calls} saveLeaguePreferences( call sites; expected 1 (the savePrefs helper)`);
  } else if (!/await saveLeaguePreferences\(leagueId, patch as any\);/.test(saveBody)) {
    bad('10. the write sends the patch as given',
      'expected `await saveLeaguePreferences(leagueId, patch as any);` inside savePrefs');
  } else if (/team_outlook/.test(saveBody)) {
    bad('10. savePrefs adds no team_outlook of its own',
      'savePrefs names team_outlook: a positions save would again write an outlook the user never chose ' +
      '(2026-11-12 fix 5). Only the window Confirm and the plan beat\'s outlook chips send one.');
  } else ok('10. the single preference write sends exactly what the user chose (no team_outlook backfill)');
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
  // `playoffChanceLine` (§14) formats the STANDING beat's saved-forecast
  // chance; it is the one place outside the beat allowed to read a
  // probability — and only that: nothing else in it is exempt.
  const chanceSrc = (/\nfunction playoffChanceLine\([\s\S]*?\n\}\n/.exec(outsideWin) || [''])[0];
  const outside = outsideWin.replace(chanceSrc, chanceSrc.replace(/\bplayoff_probability\b/g, 'p'));
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
  } else ok('12b. the projection block is read inside the window beat only; the preselected chip is unchanged');

  // ── 13 — a write that is NOT an outlook choice saves no outlook at all ──
  // 2026-11-12 fix 5: there is no backfill. Under `source: 'projection'`
  // `window.inferred` IS the forecast's suggestion, and under any source it is
  // a read, never a choice — so neither it nor the roster verdict is ever
  // posted on a positions save. The plan beat's draft outlook is the SAVED
  // one or null, and its commit sends `team_outlook` only when there is one.
  if (/backfillOutlook/.test(s)) {
    bad('13a. no outlook backfill helper remains', 'backfillOutlook is still referenced in the screen');
  } else ok('13a. no outlook backfill helper remains');
  if (!/outlook: saved\.team_outlook \?\? null,/.test(planBody)) {
    bad('13b. the plan beat\'s draft outlook is the saved one or null',
      'expected `outlook: saved.team_outlook ?? null,` — a fallback here is posted by the next positions tap');
  } else ok('13b. the plan beat\'s draft outlook is the saved one or null');
  if (!/\.\.\.\(next\.outlook \? \{ team_outlook: next\.outlook \} : \{\}\),/.test(planBody)
    || /team_outlook: next\.outlook,/.test(planBody)) {
    bad('13c. a plan-beat positions tap sends team_outlook only when one is set',
      'expected `...(next.outlook ? { team_outlook: next.outlook } : {}),` in commit');
  } else ok('13c. a plan-beat positions tap sends team_outlook only when one is set');
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
  if (count(s, 'playoff_probability') !== count(block, 'playoff_probability') + count(chanceSrc, 'playoff_probability')
    || !count(block, 'playoff_probability') || !count(chanceSrc, 'playoff_probability')) {
    bad('12e. the forecast percentage renders in the projection line and the standing chance only',
      'playoff_probability is read outside the team-review.window.projection block and playoffChanceLine');
  } else if (!/\{pr\.suggestion \? \(\s*<ChalkText style=\{styles\.read\}>\{pr\.suggestion\}<\/ChalkText>/.test(block)
    || !/\{!fromProjection && pr\?\.status === 'unavailable' && pr\.explanation \? \(\s*<ChalkText style=\{styles\.dim\}>\{pr\.explanation\}<\/ChalkText>/.test(winBody)) {
    bad('12e. the server\'s sentences are rendered as given',
      'expected {pr.suggestion} inside the projection line and {pr.explanation} as the dim note when unavailable');
  } else ok('12e. the forecast percentage lives in the projection line and the standing chance only; server copy is rendered as given');

  if (!/source\?: 'roster' \| 'odds' \| 'composite' \| 'projection';/.test(api)
    || !/projection\?: OutlookRecommendation;/.test(api)) {
    bad('12f. the wire type carries the optional projection block', "expected `source?: … | 'projection'` and `projection?: OutlookRecommendation` on TeamReviewWindow");
  } else ok('12f. TeamReviewWindow types the optional projection block');
}

// ── 14-20 — 2026-11-12 current-data fixes ──────────────────────────────────
// docs/feedback/items/357-team-review/2026-11-12-current-data-fixes.md. Pure
// helpers are EXECUTED (transpiled from the screen source); placement and
// wiring are matched per component body.
{
  const ts = require('typescript');
  const count = (hay, needle) => hay.split(needle).length - 1;
  const fnSrc = (src, name) => (new RegExp(`\\nfunction ${name}\\([\\s\\S]*?\\n\\}\\n`).exec(src) || [''])[0];
  const load = (src, names) => {
    const lib = {};
    new Function('exports', ts.transpileModule(
      `${src}\n${names.map((n) => `exports.${n} = ${n};`).join('\n')}`,
      { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } },
    ).outputText)(lib);
    return lib;
  };
  const body = (name) => {
    const i = s.indexOf(`function ${name}(`);
    if (i === -1) return '';
    const rest = s.slice(i + 1);
    const end = rest.search(/\nfunction \w/);
    return end === -1 ? rest : rest.slice(0, end);
  };
  const standing = body('Standing'), win = body('Window'), plan = body('Plan');
  const saveBody = (/const savePrefs = useCallback\(async \([\s\S]*?\n  \}, \[[^\]]*\]\);/.exec(s) || [''])[0];

  // 14 — fix 2: the standing beat shows the SAVED forecast, never the old band
  {
    const src = fnSrc(s, 'playoffChanceLine');
    let wrong = 'playoffChanceLine not found';
    if (src) {
      const f = load(src, ['playoffChanceLine']).playoffChanceLine;
      const cases = [
        [{ playoff_probability: 0.4567, captured_at: 'x', current: true }, 'Nov 10',
          { percent: '45.7%', note: 'From the forecast saved Nov 10.' }],
        [{ playoff_probability: 0.05, captured_at: 'x', current: false }, 'Nov 3',
          { percent: '5.0%', note: 'Last saved Nov 3.' }],
      ];
      const bads = cases.filter(([c, d, want]) => JSON.stringify(f(c, d)) !== JSON.stringify(want));
      wrong = bads.length ? bads.map(([c, d]) => `${JSON.stringify(c)} → ${JSON.stringify(f(c, d))}`).join('; ') : '';
    }
    const standingType = (/export interface TeamReviewStanding \{[\s\S]*?\n\}/.exec(api) || [''])[0];
    if (wrong) bad('14a. playoffChanceLine words the chance like Home (executed)', wrong);
    else ok('14a. playoffChanceLine: one decimal; "last saved" when not current (executed)');
    if (/s\.outlook|\.band\b|Playoff outlook|PROJECTED/.test(standing)) {
      bad('14b. the standing beat never renders the old outlook.odds band',
        'Standing reads s.outlook / a band / "Playoff outlook" — the band contradicted the saved forecast');
    } else if (!/const chance = s\.playoff_chance;/.test(standing)
      || !/testID="team-review\.standing\.playoff-chance"/.test(standing)
      || !/\{chance && line \? \(/.test(standing)) {
      bad('14b. the standing beat renders s.playoff_chance, and nothing without it',
        'expected `const chance = s.playoff_chance;` rendered under `{chance && line ? (` in team-review.standing.playoff-chance');
    } else ok('14b. the standing beat renders the saved forecast\'s chance, nothing without it, never the old band');
    if (!/playoff_chance\?: \{/.test(standingType) || /\boutlook\?: \{/.test(standingType)) {
      bad('14c. TeamReviewStanding types playoff_chance and no longer types the band',
        'expected `playoff_chance?: {` and no `outlook?: {` in TeamReviewStanding');
    } else ok('14c. TeamReviewStanding types playoff_chance and not the old band');
  }

  // 15 — fix 3: one outlook vocabulary; the catalog's outlook rules
  {
    const receipt = read(path.join(ROOT, 'src/components/OutlookBiasReceipt.tsx'));
    if (!/const OUTLOOK_LABEL: Readonly<Record<string, string>> = OUTLOOK_DISPLAY_NAME;/.test(s)
      || !/import \{ OUTLOOK_DISPLAY_NAME \} from '\.\.\/components\/OutlookBiasReceipt';/.test(s)) {
      bad('15a. Team Review names outlooks from the shared table',
        'expected OUTLOOK_LABEL = OUTLOOK_DISPLAY_NAME, imported from OutlookBiasReceipt');
    } else if (/'Contender'|'Rebuilder'|Full teardown/.test(s)) {
      bad('15a. no private outlook names remain', "found 'Contender' / 'Rebuilder' / 'Full teardown' in the screen");
    } else if (!/jets: \{ lean: '[^']*', name: 'Tanking' \}/.test(receipt)) {
      bad('15a. the shared table still says Tanking', 'OutlookBiasReceipt LEAN.jets.name is not Tanking');
    } else ok('15a. Team Review names every outlook from OUTLOOK_DISPLAY_NAME (no private table)');
    const src = fnSrc(s, 'outlookRuleLines');
    if (!src) bad('15b. outlookRuleLines exists', 'no module-level function outlookRuleLines');
    else {
      const f = load(src, ['outlookRuleLines']).outlookRuleLines;
      const labels = { championship: 'All-in', contender: 'Contending', rebuilder: 'Rebuilding', jets: 'Tanking', not_sure: 'Not sure' };
      const opts = ['championship', 'contender', 'rebuilder', 'jets', 'not_sure'];
      const got = f(opts, { jets: ['Tanking teams keep next pick', 'Tanking teams skip older RBs'] }, labels);
      const want = ['Choosing Tanking switches on: Tanking teams keep next pick; Tanking teams skip older RBs.'];
      if (JSON.stringify(got) !== JSON.stringify(want) || f(opts, undefined, labels).length !== 0
        || f(opts, { championship: [] }, labels).length !== 0) {
        bad('15b. outlookRuleLines: one line per outlook with rules, in the catalog\'s names (executed)', JSON.stringify(got));
      } else if (!/outlookRuleLines\(w\.options, w\.outlook_rules, OUTLOOK_LABEL\)/.test(win)
        || !/outlook_rules\?: Partial<Record<OutlookOption, string\[\]>>;/.test(api)) {
        bad('15b. the window beat renders the server\'s outlook_rules', 'expected outlookRuleLines(w.options, w.outlook_rules, OUTLOOK_LABEL) in Window and the typed field');
      } else ok('15b. the window beat lists, per outlook, the rules it switches on in the catalog\'s names (executed)');
    }
  }

  // 16 — fix 4: a save refetches the review without a spinner
  {
    if (!/qc\.invalidateQueries\(\{ queryKey: \['team-review', leagueId\] \}\);/.test(saveBody)) {
      bad('16. a save refetches the team-review payload',
        "savePrefs does not invalidate ['team-review', leagueId] — later beats keep the first fetch (fix 4)");
    } else if (!/if \(q\.isLoading \|\| !data\) \{/.test(s) || /q\.isFetching/.test(s)) {
      bad('16. the refetch keeps the current beat on screen',
        'the loading branch must stay `q.isLoading || !data` (isLoading is first load only); isFetching would blank the beat');
    } else ok('16. every save refetches the review in the background; the beat on screen stays');
  }

  // 18 — fix 6: the plan beat's player rules card
  {
    const rosterFlag = /const rosterSetupOn = useFlag\('trades\.roster_setup'\);/.test(plan);
    const move = /\{rosterSetupOn \? \(\s*<Row\s+label="Move"\s+value=\{countLabel\(assets \? \(assets\.trade_block \?\? \[\]\)\.length : undefined, 'asset'\)\}/.test(plan);
    const link = /testID="team-review\.plan\.roster-setup"[\s\S]{0,200}onPress=\{onOpenRosterSetup\}/.test(plan);
    const route = /onOpenRosterSetup=\{\(\) => nav\.navigate\('RosterSetup', \{ entry: 'manual_dna' \}\)\}/.test(s);
    const notInterested = /Not interested makes a player less likely to be offered to you\. It\s+does not block him\./.test(plan);
    if (!rosterFlag || !move) bad('18a. Move counts the trade block, behind trades.roster_setup', 'Move row or its flag gate is missing');
    else if (!/label="Keep"\s+value=\{countLabel\(assets\?\.untouchables\?\.length, 'player'\)\}/.test(plan)) {
      bad('18a. Keep is called "Keep"', 'expected label="Keep" over the untouchables count');
    } else ok('18a. Keep and Move (trade block, behind trades.roster_setup) are counted');
    if (!link || !route) bad('18b. a link opens Roster setup with the DNA row\'s route and params',
      "expected team-review.plan.roster-setup → onOpenRosterSetup → nav.navigate('RosterSetup', { entry: 'manual_dna' })");
    else ok('18b. "Set Keep and Move in Roster setup" opens the Trade DNA row\'s route and params');
    if (!notInterested) bad('18c. Not interested is described truthfully', 'expected the "less likely … does not block him" line');
    else ok('18c. Not interested reads as a preference, not a block');
  }

  // 19 — fix 7: the window line says what the engine uses right now
  {
    const src = fnSrc(s, 'windowSaveLine');
    if (!src) bad('19. windowSaveLine exists', 'no module-level function windowSaveLine');
    else {
      const f = load(src, ['windowSaveLine']).windowSaveLine;
      const saved = f('Rebuilding', true), sugg = f(null, true), roster = f(null, false);
      const okLines = /saved outlook is Rebuilding\. Every trade we show you uses it\./.test(saved)
        && /Nothing is saved yet/.test(sugg) && /suggestion/.test(sugg) && /until you tap Confirm/.test(sugg)
        && /read of your roster/.test(sugg)
        && /Nothing is saved yet/.test(roster) && !/suggestion/.test(roster) && /read of your roster/.test(roster)
        && !/steers every trade/.test(saved + sugg + roster);
      if (!okLines) bad('19. windowSaveLine is true in each state (executed)', JSON.stringify([saved, sugg, roster]));
      else if (!/windowSaveLine\(w\.declared \? OUTLOOK_LABEL\[w\.declared\] : null, fromProjection\)/.test(win)
        || /This steers every trade we show you/.test(win)) {
        bad('19. the window beat renders windowSaveLine from the SAVED outlook', 'expected windowSaveLine(w.declared ? … : null, fromProjection) and no old line');
      } else ok('19. the window line is true when saved, when only suggested, and on the roster read alone (executed)');
    }
  }

  // 20 — fix 8: a Team Review save gets the Trade DNA "Preferences changed" return
  {
    const BUS = path.join(ROOT, 'src/state/teamReviewSaveBus.ts');
    const busSrc = read(BUS);
    const trades = strip(read(path.join(ROOT, 'src/screens/TradesScreen.tsx')));
    if (/^import /m.test(busSrc)) bad('20a. the bus has no runtime imports', 'teamReviewSaveBus.ts imports something');
    else {
      const b = load(busSrc.replace(/^export /gm, ''), ['noteTeamReviewSave', 'clearTeamReviewSave', 'consumeTeamReviewSave', 'prefsChangedStripVisible']);
      const seq = [];
      seq.push(b.consumeTeamReviewSave('L1'));                      // nothing posted
      b.noteTeamReviewSave('L1'); seq.push(b.consumeTeamReviewSave('L1')); seq.push(b.consumeTeamReviewSave('L1'));
      b.noteTeamReviewSave('L1'); seq.push(b.consumeTeamReviewSave('L2')); seq.push(b.consumeTeamReviewSave('L1'));
      b.noteTeamReviewSave('L1'); b.clearTeamReviewSave(); seq.push(b.consumeTeamReviewSave('L1'));
      const table = [
        b.prefsChangedStripVisible(true, 3, 'complete'), b.prefsChangedStripVisible(true, 3, null),
        b.prefsChangedStripVisible(true, 0, 'complete'), b.prefsChangedStripVisible(true, 3, 'running'),
        b.prefsChangedStripVisible(false, 3, 'complete'),
      ];
      if (JSON.stringify(seq) !== JSON.stringify([false, true, false, false, false, false])) {
        bad('20a. the mailbox is consume-once and league-scoped (executed)', JSON.stringify(seq));
      } else if (JSON.stringify(table) !== JSON.stringify([true, true, false, false, false])) {
        bad('20a. prefsChangedStripVisible is the Trade DNA rule (executed)', JSON.stringify(table));
      } else ok('20a. the mailbox is consume-once and league-scoped; the strip rule is the Trade DNA one (executed)');
    }
    const afterAwait = saveBody.indexOf('await saveLeaguePreferences(');
    const noted = saveBody.indexOf('noteTeamReviewSave(leagueId);');
    const finish = (/testID="team-review\.finish"[\s\S]*?nav\.navigate\('TradesHome'\);/.exec(s) || [''])[0];
    if (afterAwait === -1 || noted < afterAwait) {
      bad('20b. Team Review posts only after a save landed', 'noteTeamReviewSave must follow the awaited write inside savePrefs');
    } else if (count(s, 'noteTeamReviewSave(') !== 1) {
      bad('20b. one post site', `found ${count(s, 'noteTeamReviewSave(')} noteTeamReviewSave( calls; expected 1, in savePrefs`);
    } else if (!/if \(scoped\) \{\s*(?:\/\/[^\n]*\n\s*)*clearTeamReviewSave\(\);/.test(read(SCREEN))
      || !finish.includes('clearTeamReviewSave();')) {
      bad('20b. a scoped Finish drops the note', 'expected clearTeamReviewSave() at the top of `if (scoped) {` in the finish handler');
    } else ok('20b. Team Review posts after a landed save and drops it when Finish runs a scoped search');
    const focus = /useFocusEffect\(\s*useCallback\(\(\) => \{\s*if \(!consumeTeamReviewSave\(leagueId\)\) return;\s*prefsChangedSinceGenerateRef\.current = true;\s*if \(prefsChangedStripVisible\(consolidateOn, deck\.length, job\?\.status\)\) \{\s*setShowPrefsChangedStrip\(true\);/.test(trades);
    const dna = /prefsChangedSinceGenerateRef\.current &&\s*prefsChangedStripVisible\(consolidateOn, deck\.length, job\?\.status\)/.test(trades);
    if (!focus) bad('20c. Find a Trade consumes the note on focus and marks the deck stale', 'the useFocusEffect consuming consumeTeamReviewSave is missing or changed');
    else if (!dna) bad('20c. the Trade DNA close uses the same strip rule', 'handleEditSheetClose does not call prefsChangedStripVisible');
    else if (/consumeTeamReviewSave[\s\S]{0,400}dispatchGenerate/.test(trades)) {
      bad('20c. a Team Review return never regenerates by itself', 'found a dispatchGenerate right after consumeTeamReviewSave');
    } else ok('20c. Find a Trade turns the note into the Trade DNA "Preferences changed" state, never a regeneration');
  }
}

// ── 21 — #681: the banner's one-tap Confirm saves the outlook ONLY ─────────
// Operator 2026-11-12 ("Yes. Stop clearing"), reversing Q-033. The inferred-
// outlook banner's Confirm used to send three empty position arrays, which
// wiped Chasing / Shopping / Avoiding saved without an outlook (Team Review
// can do that since fix 5). `saveLeagueOutlook` is EXECUTED with a stubbed
// transport (its result lands before the report, which waits a macrotask);
// the mutation is matched in TradesScreen's source.
{
  const ts = require('typescript');
  const leagueSrc = read(path.join(ROOT, 'src/api/league.ts'));
  const fn = (/\nexport async function saveLeagueOutlook\([\s\S]*?\n\}\n/.exec(leagueSrc) || [''])[0];
  if (!fn) bad('21a. saveLeagueOutlook exists', 'no `export async function saveLeagueOutlook(` in api/league.ts');
  else {
    const calls = [], notes = [];
    const lib = {};
    new Function('exports', 'api', 'noteTradeInputChange', ts.transpileModule(
      `${fn.replace('export async function', 'async function')}\nexports.f = saveLeagueOutlook;`,
      { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } },
    ).outputText)(lib, { post: async (url, body) => { calls.push([url, body]); return { ok: true }; } },
      (why) => notes.push(why));
    lib.f('L1', 'rebuilder').then(() => {
      const want = JSON.stringify([['/api/league/preferences', { league_id: 'L1', team_outlook: 'rebuilder' }]]);
      if (JSON.stringify(calls) !== want) {
        bad('21a. saveLeagueOutlook posts league_id + team_outlook and nothing else (executed)', `got ${JSON.stringify(calls)}`);
      } else if (JSON.stringify(notes) !== JSON.stringify(['after_preferences_change'])) {
        bad('21a. saveLeagueOutlook notes the preference change like saveLeaguePreferences', `got ${JSON.stringify(notes)}`);
      } else ok('21a. saveLeagueOutlook posts only league_id + team_outlook, and notes the change (executed)');
    }, (e) => bad('21a. saveLeagueOutlook runs', String(e)));
  }
  const trades = strip(read(path.join(ROOT, 'src/screens/TradesScreen.tsx')));
  const mut = (/const confirmOutlookMutation = useMutation\(\{[\s\S]*?\n  \}\);/.exec(trades) || [''])[0];
  if (!mut) bad('21b. the banner Confirm mutation exists', 'no `const confirmOutlookMutation = useMutation({` in TradesScreen');
  else if (!/mutationFn: \(outlook: NonNullable<Outlook>\) =>\s*saveLeagueOutlook\(leagueId!, outlook\),/.test(mut)
    || /_positions|saveLeaguePreferences/.test(mut)) {
    bad('21b. the banner Confirm sends no position lists',
      'confirmOutlookMutation must call saveLeagueOutlook(leagueId!, outlook) and name no *_positions key (#681)');
  } else ok('21b. the banner Confirm calls saveLeagueOutlook and sends no position list');
}

setImmediate(() => {
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
});
