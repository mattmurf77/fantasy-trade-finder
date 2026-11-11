#!/usr/bin/env node
// Roster-first setup for Find a Trade (flag `trades.roster_setup`;
// docs/plans/roster-first-trade-setup/{prd,scope,analytics}.md).
//
// WHY THIS EXISTS. The setup is a first-run interruption pushed over the
// Trades landing, and its failure modes are silent: a second FeedbackFAB on a
// tab-stack screen (#196/#197), an asset-prefs write with a list value the
// engine does not know, a reorder carrying `via:'quickrank'` that quietly
// inflates the Quick Rank funnel, a surface that leaks out with the flag off,
// a Quick Rank chip grid that forks back into two copies, or an emitter whose
// name the default-deny ingest drops behind a 200. None of those shows up as
// a failing screen. This guard pins the six structural checks scope.md §3
// names, plus the scope's testIDs, and it transpiles and EXECUTES
// `src/utils/rosterSetup.ts` (the prefill, Keep guard, pick cap, rank walk,
// new-asset diff, first-pass trigger condition and snooze ladder) under
// plain node. §10 pins the automatic entry the operator amended on
// 2026-11-10: the setup is pushed on the FIRST DECLINED suggestion (a
// committed pass), never on a TradesHome focus.
//
// HONEST LABEL (G-035): checks 1-6 prove the PRESENCE of exact wirings in
// source, not runtime behaviour. The executed section proves the pure
// decisions. Runtime proof is the manual TestFlight checklist in scope.md §3.
//
// Run: npm run test:roster-setup   (or node tests/check-roster-setup.js)
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
// Comments out, so a sentence in a header can never satisfy (or trip) a pin.
const code = (src) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1');

const SCREEN = code(read('src/screens/RosterSetupScreen.tsx'));
const CARD = code(read('src/components/RosterSetupEntryCard.tsx'));
const TRIGGER = code(read('src/hooks/useRosterSetupPassTrigger.ts'));
const QUICK_RANK = code(read('src/screens/QuickRankScreen.tsx'));
const GRID = code(read('src/components/RankChipGrid.tsx'));
const TRADES = code(read('src/screens/TradesScreen.tsx'));
const DNA = code(read('src/components/TradeDnaSheet.tsx'));
const TABNAV = code(read('src/navigation/TabNav.tsx'));
const BUS = code(read('src/state/onboardingBus.ts'));
const LEAGUE_API = code(read('src/api/league.ts'));
const UTIL_SRC = read('src/utils/rosterSetup.ts');

// ── 1. No FeedbackFAB mount (tab stack, #188) + pinned footer reports ────
assert(!/<FeedbackFAB\b/.test(SCREEN), '1a. RosterSetupScreen renders no <FeedbackFAB>');
assert(
  !/import\s+FeedbackFAB\b/.test(SCREEN),
  '1b. RosterSetupScreen imports no default FeedbackFAB (only setPinnedBottomBarHeight)',
);
assert(
  /setPinnedBottomBarHeight\(\s*'roster_setup',\s*isFocused\s*&&/.test(SCREEN)
    && /setPinnedBottomBarHeight\(\s*'roster_setup',\s*0\s*\)/.test(SCREEN),
  '1c. the pinned footer reports its height while focused and clears on unmount (AC-12)',
);
assert(
  /name="RosterSetup"[\s\S]{0,80}component=\{RosterSetupScreen\}/.test(TABNAV)
    && /function TradesStackNav\(\)[\s\S]*name="RosterSetup"[\s\S]*function /.test(TABNAV),
  '1d. RosterSetup is registered in the Trades stack (a tab-stack screen)',
);

// ── 2. Asset-prefs writes pass only trade_block | untouchable | none ────
const prefWrites = SCREEN.match(/setAssetPref\(/g) || [];
assert(prefWrites.length === 1, '2a. exactly one setAssetPref call site in the screen', `found ${prefWrites.length}`);
assert(
  /setAssetPref\(\s*leagueId\s*,\s*id\s*,\s*listForState\(\s*desired\s*\)\s*\)/.test(SCREEN),
  "2b. the screen's only write passes listForState(...) as the list",
);
assert(!/setAssetPref\(/.test(CARD), '2c. the TradesHome card writes no asset prefs');
assert(
  /'trade_block'/.test((LEAGUE_API.match(/export type AssetPrefList[\s\S]*?;/) || [''])[0])
    && /trade_block\?:\s*string\[\]/.test(LEAGUE_API),
  '2d. api/league.ts AssetPrefList + AssetPrefs carry trade_block',
);

// ── 3. The reorder call passes no `via` ─────────────────────────────────
const reorderCalls = SCREEN.match(/reorderRankings\([^)]*\)/g) || [];
assert(reorderCalls.length === 1, '3a. exactly one reorderRankings call in the screen', `found ${reorderCalls.length}`);
assert(
  reorderCalls.every((c) => c.split(',').length === 2),
  '3b. reorderRankings is called with (position, ids) only — no via',
  reorderCalls.join(' | '),
);
assert(!/quickrank/.test(SCREEN), "3c. the screen never names 'quickrank'");

// ── 4. Everything renders only behind useFlag('trades.roster_setup') ────
assert(
  /const rosterSetupOn = useFlag\('trades\.roster_setup'\);/.test(SCREEN)
    && /if \(!rosterSetupOn\) \{\s*return /.test(SCREEN),
  '4a. the screen reads the flag and renders nothing but its shell when off',
);
assert(
  /const rosterSetupOn = useFlag\('trades\.roster_setup'\);/.test(TRADES),
  '4b. TradesScreen reads the flag',
);
assert(
  /\{rosterSetupOn && leagueId && !isDemo && route\?\.name === 'TradesHome' \? \(\s*<RosterSetupEntryCard/.test(TRADES)
    && (TRADES.match(/<RosterSetupEntryCard/g) || []).length === 1,
  '4c. the return card mount exists once, behind the flag, landing-only, never demo',
);
assert(
  /rosterSetup: rosterSetupOn && leagueId && !isDemo\s*\?/.test(TRADES),
  '4d. the Trade DNA "Your roster" row is passed only behind the flag',
);
assert(
  /\{full\?\.rosterSetup \? \([\s\S]*?testID="dna\.roster-setup"/.test(DNA),
  '4e. TradeDnaSheet renders dna.roster-setup only when the host passed rosterSetup',
);
const pushSites = [
  ['RosterSetupEntryCard', CARD],
  ['useRosterSetupPassTrigger', TRIGGER],
  ['TradesScreen', TRADES],
  ['TradeDnaSheet', DNA],
  ['QuickRankScreen', QUICK_RANK],
].flatMap(([n, s]) => (s.match(/navigate\(\s*'RosterSetup'/g) || []).map(() => n));
assert(
  pushSites.filter((n) => n === 'TradesScreen').length === 1
    && pushSites.filter((n) => n === 'RosterSetupEntryCard').length === 1
    && pushSites.filter((n) => n === 'useRosterSetupPassTrigger').length === 1
    && !pushSites.includes('TradeDnaSheet'),
  '4f. RosterSetup is pushed only from the card tap, the first-pass trigger and the flag-gated DNA onEdit',
  pushSites.join(', '),
);

// ── 5. Quick Rank and the setup share ONE chip grid ─────────────────────
const gridImport = /import RankChipGrid from '\.\.\/components\/RankChipGrid';/;
assert(gridImport.test(QUICK_RANK) && gridImport.test(SCREEN), '5a. both screens import components/RankChipGrid');
assert(/<RankChipGrid[\s\S]*?testID="quick-rank\.chip"/.test(QUICK_RANK), '5b. QuickRank renders the grid with its quick-rank.chip ids');
assert(
  !/renderItem=/.test(QUICK_RANK) && !/\bFlatList\b/.test(QUICK_RANK) && !/rankBadge/.test(QUICK_RANK),
  '5c. QuickRankScreen keeps no private chip renderer (the extraction stays shared)',
);
assert(
  /testID=\{`\$\{testID\}\.\$\{item\.id\}`\}/.test(GRID) && /numColumns=\{3\}/.test(GRID),
  "5d. RankChipGrid owns the chip render and Quick Rank's 3-column grid",
);
assert(
  /<RankChipGrid[\s\S]*?testID=\{`roster-setup\.rank\.\$\{rankPos\}\.chip`\}/.test(SCREEN),
  '5e. the setup rank step renders the shared grid with roster-setup.rank.<pos>.chip ids',
);

// ── 6. All six events are registered (same commit as the emitters) ──────
const EVENTS = [
  'roster_setup_shown', 'roster_setup_toggles_done', 'roster_setup_rank_saved',
  'roster_setup_completed', 'roster_setup_skipped', 'roster_setup_prompt_tapped',
];
const TAX = readRoot('backend/analytics_taxonomy.py');
const QUERIES = readRoot('backend/analytics_queries.py');
const allowedBlock = (TAX.match(/ALLOWED_CLIENT_EVENTS: frozenset\[str\] = frozenset\(\{[\s\S]*?\n\}\)/) || [''])[0];
const propsBlock = (TAX.match(/CLIENT_EVENT_PROPS: dict\[str, frozenset\[str\]\] = \{[\s\S]*?\n\}/) || [''])[0];
const nonIntent = (QUERIES.match(/NON_INTENT_EVENTS = frozenset\(\{[\s\S]*?\n\}\)/) || [''])[0];
const MOBILE_SRC = [SCREEN, CARD, TRADES].join('\n');
for (const e of EVENTS) {
  assert(new RegExp(`"${e}"`).test(allowedBlock), `6a. ${e} is in ALLOWED_CLIENT_EVENTS`);
  assert(new RegExp(`"${e}":\\s*frozenset`).test(propsBlock), `6b. ${e} has a CLIENT_EVENT_PROPS row`);
  assert(new RegExp(`track\\(\\s*'${e}'`).test(MOBILE_SRC), `6c. ${e} has a mobile emitter`);
}
assert(
  /"roster_setup_shown"/.test(nonIntent) && /"roster_setup_skipped"/.test(nonIntent)
    && !/"roster_setup_(toggles_done|rank_saved|completed|prompt_tapped)"/.test(nonIntent),
  '6d. shown + skipped are NON_INTENT; the other four are intent',
);
assert(
  /track\('prompt_shown', \{ surface: 'roster_setup_card' \}/.test(CARD) && /roster_setup_card/.test(TAX),
  '6e. the card impression rides prompt_shown{surface:roster_setup_card}, documented in the taxonomy',
);

// ── 7. scope.md §3 testIDs ───────────────────────────────────────────────
const ids = [
  [SCREEN, 'testID="roster-setup.screen"'],
  [SCREEN, 'testID="roster-setup.counter"'],
  [SCREEN, 'testID={`roster-setup.row.${assetId}.${s.key}`}'],
  [SCREEN, 'testID="roster-setup.continue"'],
  [SCREEN, 'testID="roster-setup.skip"'],
  [SCREEN, 'testID={`roster-setup.rank.${rankPos}.chip`}'],
  [SCREEN, 'testID="roster-setup.rank.save"'],
  [SCREEN, 'testID="roster-setup.rank.done"'],
  [SCREEN, 'testID="roster-setup.done.cta"'],
  [CARD, 'testID="trades.roster-setup-card"'],
  [CARD, 'testID="trades.roster-setup-card.dismiss"'],
  [DNA, 'testID="dna.roster-setup"'],
];
for (const [src, id] of ids) assert(src.includes(id), `7. ${id}`);
assert(/key: 'move'[\s\S]*key: 'open'[\s\S]*key: 'keep'/.test(SCREEN), '7b. the row segments are move | open | keep');

// ── 8. Regen bus: generalised source, posted only on change ─────────────
assert(/GuidedRegenSource = 'quickset' \| 'trios' \| 'import' \| 'roster_setup'/.test(BUS), "8a. onboardingBus accepts 'roster_setup'");
assert(
  /if \(changedRef\.current\) setPendingGuidedRegen\('roster_setup'\);/.test(SCREEN)
    && (SCREEN.match(/setPendingGuidedRegen\(/g) || []).length === 1,
  '8b. the screen posts the regen marker once, only when something changed (AC-8)',
);

// ── 9. Execute utils/rosterSetup.ts ──────────────────────────────────────
assert(!/^\s*import\s+(?!type\b)/m.test(UTIL_SRC), '9a. utils/rosterSetup.ts has zero runtime imports');
const u = (() => {
  const js = ts.transpileModule(UTIL_SRC, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const m = { exports: {} };
  new Function('module', 'exports', 'require', js)(m, m.exports, () => {
    throw new Error('rosterSetup.ts must not require anything at runtime');
  });
  return m.exports;
})();

assert(
  ['move', 'keep', 'open'].map(u.listForState).join(',') === 'trade_block,untouchable,none',
  '9b. listForState maps move/keep/open → trade_block/untouchable/none and nothing else',
);
const pre = u.prefillStates(['a', 'b', 'c', 'd'], { untouchables: ['a'], trade_block: ['b'], targets: ['c'] });
assert(
  pre.a === 'keep' && pre.b === 'move' && pre.c === 'open' && pre.d === 'open',
  '9c. prefill: untouchable → keep, trade_block → move, anything else → open (AC-2)',
  JSON.stringify(pre),
);
const assets27 = Array.from({ length: 27 }, (_, i) => ({ id: `p${i}`, isPick: false }))
  .concat([{ id: 'k1', isPick: true }]);
const st = {};
assets27.forEach((a, i) => { st[a.id] = i < 14 ? 'keep' : 'open'; });
const c = u.countStates(assets27, st);
assert(
  u.keepGuardNote(c) === 'Keeping 14 of 27. Fewer trades will fit.',
  '9d. Keep guard fires above 40% of non-pick assets with the prd copy',
  String(u.keepGuardNote(c)),
);
assert(u.keepGuardNote({ playerKeep: 10, playerTotal: 27 }) === null, '9e. Keep guard silent at or under 40%');
const beyond = u.picksBeyondCap([
  ...Array.from({ length: 7 }, (_, i) => ({ pick_id: `pk${i}`, pool_value: 100 - i })),
  { pick_id: 'zero', pool_value: 0 },
]);
assert(
  beyond.has('pk6') && beyond.has('zero') && !beyond.has('pk0') && !beyond.has('pk5') && beyond.size === 2,
  '9f. picks beyond the top-6 priced (or priced ≤ 0) are marked not in trade search (AC-4)',
  [...beyond].join(','),
);
assert(
  u.rankSteps({ QB: 1, RB: 7, WR: 2, TE: 0 }).join(',') === 'RB,WR'
    && u.rankSteps({ QB: 3, RB: 7, WR: 2, TE: 2 }, new Set(['TE'])).join(',') === 'TE',
  '9g. rank walk: QB→TE order, <2 players skipped, roster-changed entry limited to gained positions',
);
assert(
  u.orderedIdsForSave(['c', 'a'], ['a', 'b', 'c', 'd']).join(',') === 'c,a,b,d',
  '9h. save order: clicked first, unclicked appended in current order',
);
assert(
  u.newAssetIds(['a', 'b', 'c'], ['a', 'x']).join(',') === 'b,c' && u.newAssetIds(['a'], ['a', 'b']).length === 0,
  '9i. new assets = current minus seen; removals never prompt (AC-10)',
);
const base = {
  flagOn: true, leagueId: 'L1', isDemo: false, hydrated: true, hasRecord: false,
  assetCount: 5, alreadyPushedThisSession: false,
};
assert(u.shouldPushSetupOnPass(base), '9j. first-pass push when every prd §3.1 condition holds');
assert(u.shouldAutoPush === undefined, '9j2. the focus-era shouldAutoPush helper is gone');
for (const [k, v] of [
  ['flagOn', false], ['leagueId', 'league_demo'], ['isDemo', true], ['hydrated', false],
  ['hasRecord', true], ['assetCount', 0], ['assetCount', null], ['alreadyPushedThisSession', true],
]) {
  assert(!u.shouldPushSetupOnPass({ ...base, [k]: v }), `9k. no first-pass push when ${k}=${JSON.stringify(v)}`);
}
// Snooze ladder: full → Not now → collapsed this session → one re-offer
// in a later session → Not now → retired (collapsed for good).
let L = null;
assert(u.cardView(L, 'entry', 3) === 'full', '9l. a fresh card shows full');
L = u.ladderOnSnooze(L, 'entry', 3);
assert(u.cardView(L, 'entry', 3) === 'collapsed', '9m. Not now collapses it for the rest of the session');
assert(u.cardView(L, 'entry', 4) === 'full', '9n. re-offered in a later session');
L = u.ladderOnShow(L, 'entry', 4) || L;
assert(L.reofferSession === 4 && u.cardView(L, 'entry', 5) === 'collapsed', '9o. the re-offer is shown in one session only');
L = u.ladderOnSnooze(L, 'entry', 4);
assert(L.retired && u.cardView(L, 'entry', 9) === 'collapsed', '9p. Not now on the re-offer retires it');
assert(u.cardView(L, 'roster_changed', 9) === 'full', '9q. a ladder for another card kind does not apply');

// ── 10. The automatic entry is the first COMMITTED PASS (2026-11-10) ────
assert(
  !/useIsFocused|useFocusEffect/.test(CARD) && !/entry: 'first_pass'/.test(CARD),
  '10a. the TradesHome card has no focus-based push (return card only)',
);
assert(
  /navigate\('RosterSetup', \{ entry: 'first_pass' \}\)/.test(TRIGGER)
    && /shouldPushSetupOnPass\(\{/.test(TRIGGER)
    && /hasRecord: !!useRosterSetup\.getState\(\)\.byLeague\[l\.leagueId\]/.test(TRIGGER)
    && /pushedThisSession\.add\(l\.leagueId\)/.test(TRIGGER),
  '10b. the trigger pushes {entry:first_pass} only through shouldPushSetupOnPass (record read at call time, once per league per session)',
);
assert(
  /const rosterSetupOnPass = useRosterSetupPassTrigger\(\{\s*enabled: rosterSetupOn && !isDemo,/.test(TRADES),
  '10c. TradesScreen arms the trigger only with the flag on and outside demo',
);
const triggerCalls = (TRADES.match(/rosterSetupOnPass\(\);/g) || []).length;
assert(triggerCalls === 5, '10d. exactly five committed-pass call sites in TradesScreen', `found ${triggerCalls}`);
const advanceBody = (TRADES.match(/  function advance\([\s\S]*?\n  \}\n/) || [''])[0];
const iMutate = advanceBody.indexOf('swipeMutation.mutate({ card: topCard, decision');
const iAdvance = advanceBody.indexOf('if (!opts?.deferDeckAdvance) setDeckIdx((i) => i + 1);');
const iPlain = advanceBody.search(/if \(decision === 'pass' && !heldPass && reasonBankedIdRef\.current !== dispatchRawId\) \{\s*rosterSetupOnPass\(\);/);
assert(
  iMutate > 0 && iAdvance > iMutate && iPlain > iAdvance,
  '10e. plain pass: the trigger runs AFTER the unchanged swipe write and the deck advance; never for a held or reason-deferred pass',
);
assert(
  /timer: setTimeout\(\(\) => \{\s*flushPendingPassRef\.current\(\);\s*rosterSetupOnPass\(\);\s*\}, UNDO_HOLD_MS\)/.test(advanceBody),
  '10f. undo-held pass: the trigger runs only when the undo window expires, after the held write flushes (Undo cancels it)',
);
const fnBody = (name) => (TRADES.match(new RegExp(`  function ${name}\\([\\s\\S]*?\\n  \\}\\n`)) || [''])[0];
assert(
  /commitReasonAdvance\(\);\s*rosterSetupOnPass\(\);/.test(fnBody('handleReasonLayer2Select'))
    && /commitReasonAdvance\(\);\s*rosterSetupOnPass\(\);/.test(fnBody('handleReasonLayer2Send'))
    && /if \(banked\) commitReasonAdvance\(\);\s*if \(banked\) rosterSetupOnPass\(\);/.test(fnBody('handleReasonOverlayDismissed')),
  '10g. reasoned pass: the trigger runs right after commitReasonAdvance at its three callers — layer 2 answered, sent, or a banked overlay closed (deck and browse)',
);
assert(
  ['handleReasonLayer1', 'handleReasonLayer2Bank', 'flushPendingPass', 'undoPass', 'commitReasonAdvance']
    .every((n) => fnBody(n) && !/rosterSetupOnPass/.test(fnBody(n))),
  '10h. never at layer 1 or the "Other" bank (capture still open), in flushPendingPass (resets/unmount flush it), on Undo, or inside commitReasonAdvance (its shape is pinned elsewhere)',
);
const ENTRY_SRC = [SCREEN, CARD, TRIGGER, UTIL_SRC, readRoot('backend/analytics_taxonomy.py'),
  readRoot('docs/business/analytics/2026-11-10-roster-setup-events.md')].join('\n');
assert(
  !/first_use/.test(ENTRY_SRC)
    && /type Entry = 'first_pass' \| 'roster_changed' \| 'manual_dna' \| 'entry_card';/.test(SCREEN)
    && /entry\s+∈ first_pass \| roster_changed \| manual_dna \| entry_card/.test(readRoot('backend/analytics_taxonomy.py')),
  "10i. the entry enum is first_pass (never first_use) in the screen, trigger, taxonomy and addendum",
);

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
