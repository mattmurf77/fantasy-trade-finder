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
// The roster-changed title names players and picks apart (operator 2026-11-12).
const titleIds = (n, prefix) => Array.from({ length: n }, (_, i) => `${prefix}${i}`);
for (const [players, picks, want] of [
  [1, 0, '1 new player on your roster'],
  [15, 0, '15 new players on your roster'],
  [0, 1, '1 new pick on your roster'],
  [0, 3, '3 new picks on your roster'],
  [1, 1, '1 new player and 1 new pick on your roster'],
  [12, 3, '12 new players and 3 new picks on your roster'],
]) {
  const got = u.newOnRosterTitle([...titleIds(players, 'pl'), ...titleIds(picks, 'pk')], [...titleIds(picks, 'pk'), 'pk_old']);
  assert(got === want, `9i2. roster-changed title: ${players} player(s), ${picks} pick(s) → "${want}"`, got);
}
assert(
  CARD.includes(": newOnRosterTitle(newIds, roster.picks.map((p) => p.pick_id));")
    && !/new on your roster/.test(CARD)
    && CARD.includes('accessibilityLabel={title}') && CARD.includes('{title}</ChalkText>')
    && CARD.includes('`${title}. Set them so your trades use them.`'),
  '9i3. the card title, collapsed row, its label and the body all use newOnRosterTitle over the card\'s own picks',
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

// ── 11. Step 2 as one-page tier placement (flag `trades.roster_tier_rank`;
// scope-tier-rank.md §6 structural guard 1-5 + the 2026-11-11 operator
// decisions: no picks on the page, market label only when it differs, a
// moved player at the edge of his new tier) ─────────────────────────────
const BOARD = code(read('src/components/RosterTierBoard.tsx'));
const CHIPS = code(read('src/components/TierTargetChips.tsx'));
const RANK_API = code(read('src/api/rankings.ts'));

// 11a (scope guard 1) — every saveTiers call is the roster-scoped save.
const tierSaveCalls = SCREEN.match(/saveTiers\([\s\S]*?\);/g) || [];
assert(tierSaveCalls.length === 1, '11a. exactly one saveTiers call site in the screen', `found ${tierSaveCalls.length}`);
assert(
  tierSaveCalls.every((c) => /\{\s*scope:\s*'roster',\s*via:\s*'roster_setup'\s*\}\s*\)/.test(c)),
  "11a2. every saveTiers call passes { scope: 'roster', via: 'roster_setup' }",
  tierSaveCalls.join(' | '),
);
assert(
  /scope\?: RankScopeParam \| 'roster';/.test(RANK_API) && /\| 'roster_setup';/.test(RANK_API)
    && /export type RankScopeParam = 'rookie';/.test(RANK_API),
  "11a3. api saveTiers accepts scope 'roster' + via 'roster_setup'; the read-side RankScopeParam is not widened",
);

// 11b (scope guard 2) — the tier page renders only behind the new flag;
// flag off = the old rank step (5e still pins its RankChipGrid).
assert(
  /const tierRankOn = useFlag\('trades\.roster_tier_rank'\);/.test(SCREEN),
  "11b. the screen reads useFlag('trades.roster_tier_rank')",
);
const continueBody = (SCREEN.match(/const onContinue = useCallback\([\s\S]*?\n {2}\}, \[/) || [''])[0];
assert(
  /if \(tierRankOn\) \{[\s\S]*?setStep\('tiers'\);[\s\S]*?\} else if \(rankPositions\.length === 0\) goDone\(\);\s*else \{\s*setRankIdx\(0\);\s*setClicked\(\[\]\);\s*setStep\('rank'\);\s*\}/.test(continueBody)
    && (SCREEN.match(/setStep\('tiers'\)/g) || []).length === 1,
  "11b2. Continue forks on tierRankOn: on → setStep('tiers') (its only site), off → the unchanged rank walk",
);
assert(
  (SCREEN.match(/<RosterTierBoard\b/g) || []).length === 1
    && /\} else if \(step === 'tiers' && tierBoard\) \{[\s\S]*?<RosterTierBoard/.test(SCREEN),
  "11b3. RosterTierBoard renders once, only in the step === 'tiers' branch",
);
assert(
  /\} else if \(step === 'rank' && rankPos\) \{[\s\S]*?<RankChipGrid/.test(SCREEN) && /reorderRankings\(rankPos, ids\)/.test(SCREEN),
  '11b4. the flag-off rank step still renders RankChipGrid and still saves with reorderRankings(rankPos, ids)',
);

// 11c (scope guard 4) — footer + FAB rules hold on the tier page too.
const tierBranch = (SCREEN.match(/\} else if \(step === 'tiers' && tierBoard\) \{[\s\S]*?\n {2}\} else \{/) || [''])[0];
assert(/onLayout=\{onFooterLayout\}/.test(tierBranch) && /bottomInset=\{footerH\}/.test(tierBranch),
  "11c. the tier page's pinned footer reports its height and the board pads under it");
assert(!/FeedbackFAB/.test(BOARD), '11c2. RosterTierBoard mounts no FeedbackFAB');

// 11d (operator decision 3) — picks are NOT on the tier page.
const tierMemo = (SCREEN.match(/const tierPlayers = useMemo\([\s\S]*?\n {2}\}, \[/) || [''])[0];
assert(/for \(const a of assets\) \{\s*if \(a\.isPick\) continue;/.test(tierMemo),
  '11d. the tier page model skips every pick');
assert(
  !/isPick|PICK|pick_id|OwnedPick|picks/i.test(BOARD.replace(/selected|onPick/g, '')),
  '11d2. RosterTierBoard has no pick concept (no picks strip)',
);
assert(
  !fs.readdirSync(path.join(MOBILE, 'src'), { recursive: true })
    .filter((f) => /\.tsx?$/.test(String(f)))
    .some((f) => fs.readFileSync(path.join(MOBILE, 'src', String(f)), 'utf8').includes('roster-setup.tiers.picks')),
  '11d3. no roster-setup.tiers.picks testID anywhere in mobile/src',
);

// 11e — the board is prop-driven: no fetching, no api import.
assert(!/useQuery|useQueries|from '\.\.\/api\//.test(BOARD), '11e. RosterTierBoard fetches nothing');

// 11f (operator decisions 5) — the market micro-label goes through the
// one tested rule; the "was" marker compares against the save baseline
// (the tier the server holds the player in — the pre-fill until a save).
assert(
  /const mkt = marketTierShown\(current, marketTier\[id\]\);/.test(BOARD)
    && /\{mkt \? \([\s\S]*?`mkt: \$\{TIER_LABEL\[mkt\]\}`/.test(BOARD),
  '11f. the market label renders only through marketTierShown(current, market)',
);
assert(/prefillTier\[id\] !== current/.test(BOARD) && /`was \$\{TIER_LABEL\[was\]\}`/.test(BOARD),
  '11f2. the "was <tier>" marker shows only for a chip off its baseline tier');
assert(/const prefillTierById = useMemo\(\(\) => \(tierBase \? tierOfMap\(tierBase\) : \{\}\), \[tierBase\]\);/.test(SCREEN),
  '11f3. the "was" reference is the save baseline (tierBase), not the original pre-fill');

// 11g — interaction: tap players, then a tier (no drag), VoiceOver path.
assert(!/DraggableFlatList|onLongPress|drag\(/.test(BOARD), '11g. no drag on the tier board (operator decision 1)');
assert(
  /accessibilityActions=\{TIERS\.filter\(\(t\) => t !== current\)\.map/.test(BOARD)
    && /label: `Move to \$\{TIER_LABEL\[t\]\}`/.test(BOARD) && /onMove\(\[id\], t\)/.test(BOARD),
  '11g2. every selectable chip carries VoiceOver "Move to <tier>" actions',
);
assert(
  /setTierBoard\(\(b\) => \(b \? applyTierMove\(b, tierBase, ids, t\) : b\)\);/.test(SCREEN),
  '11g3. a move applies the edge rule locally through applyTierMove, judged against the save baseline (decision 6)',
);
assert(
  /testID=\{testIDPrefix \? `\$\{testIDPrefix\}\.\$\{t\}` : undefined\}/.test(CHIPS)
    && /testIDPrefix="roster-setup\.tiers\.move"/.test(tierBranch),
  '11g4. the footer reuses TierTargetChips with roster-setup.tiers.move.<tier> ids (Tiers mount passes none)',
);

// 11h — skip / discard / save semantics (scope §2.2).
const tierSkipBody = (SCREEN.match(/const onTierSkip = useCallback\([\s\S]*?\n {2}\}, \[/) || [''])[0];
assert(
  /stage: 'toggles' \| 'rank' \| 'tiers'/.test(SCREEN)
    && (SCREEN.match(/trackSkipped\('tiers'\)/g) || []).length === 3
    && /finalizeDone\(\);\s*trackSkipped\('tiers'\);\s*leave\(\);/.test(tierSkipBody),
  "11h. Skip, back, and back-after-Discard on the tier page all fire roster_setup_skipped {stage:'tiers'}",
);
assert(
  /Alert\.alert\('Discard your tier changes\?', undefined, \[\s*\{ text: 'Keep editing', style: 'cancel' \},\s*\{ text: 'Discard', style: 'destructive', onPress: onDiscard \},/.test(SCREEN)
    && /if \(stepRef\.current === 'tiers' && tierDirtyRef\.current\) \{\s*e\?\.preventDefault\?\.\(\);\s*confirmDiscardTiers\(/.test(SCREEN),
  '11h2. back with unsaved moves holds the pop behind "Discard your tier changes?" (Discard / Keep editing)',
);
assert(
  /const all = tierSavePayloads\(tierBoard, tierBase, tierPlayers\.positionOf\);\s*const payloads = only \? all\.filter\(\(p\) => only\.includes\(p\.position\)\) : all;/.test(SCREEN)
    && /onPress=\{\(\) => void saveTierMoves\(tierFailed\)\}/.test(tierBranch)
    && /base = tierRebase\(base, p\);/.test(SCREEN),
  '11h3. Save posts tierSavePayloads; Retry re-posts only the failed positions; a saved position is rebased out',
);
assert(
  /label=\{dirty \? 'Save tiers' : 'Done'\}/.test(tierBranch),
  '11h4. the primary reads Save tiers, or Done when nothing has moved (no POST then)',
);
assert(/\$\{reTiered\} re-tiered/.test(SCREEN), '11h5. the done summary says "N re-tiered" on the tier path');
assert(
  /\|\| tierSavedPositionsRef\.current\.size > 0,/.test(SCREEN)
    && /ranked_positions: rankedRef\.current\.length \+ tierSavedPositionsRef\.current\.size,/.test(SCREEN),
  '11h6. only a SAVED tier move counts as a change (regen) and as a ranked position',
);

// 11h7 (review fix 1) — leaving while a save is in flight. The back
// listener holds the pop with NO prompt and no bookkeeping, and it is the
// FIRST tier branch (before the dirty "Discard?" branch, which would
// otherwise finalize under the in-flight saves).
const exitBody = (SCREEN.match(/implicitExitRef\.current = \(e: any\) => \{[\s\S]*?\n {2}\};/) || [''])[0];
const inFlight = (exitBody.match(/if \(stepRef\.current === 'tiers' && tierSavingRef\.current\) \{([\s\S]*?)\}/) || [])[1];
assert(
  inFlight != null && /^\s*e\?\.preventDefault\?\.\(\);\s*return;\s*$/.test(inFlight)
    && exitBody.indexOf('tierSavingRef.current') < exitBody.indexOf('tierDirtyRef.current'),
  '11h7. a beforeRemove during an in-flight tier save is prevented with no prompt, no finalizeDone, no skipped event',
  inFlight,
);
const saveBody = (SCREEN.match(/const saveTierMoves = useCallback\([\s\S]*?\n {2}\}, \[/) || [''])[0];
assert(
  /^\s*const saveTierMoves = useCallback\(async \(only\?: readonly Position\[\]\) => \{\s*if \([^\n]*\btierSavingRef\.current\b[^\n]*\) return;/.test(saveBody)
    && /tierSavingRef\.current = true;\s*try \{\s*for \(const p of payloads\)/.test(saveBody)
    && /\} finally \{\s*tierSavingRef\.current = false;\s*\}/.test(saveBody),
  '11h8. Save/Retry is ref-guarded: a second tap while one is in flight is a no-op; the ref clears in a finally',
);

// 11i (scope guard 5) — roster_setup_tiers_saved registered, intent,
// emitted with exactly the specced props.
const TIERS_EVENT = 'roster_setup_tiers_saved';
const TIER_PROPS = ['league_id', 'entry', 'moved_count', 'moved_up_count', 'moved_down_count',
  'players_total', 'positions_saved', 'duration_ms'];
assert(new RegExp(`"${TIERS_EVENT}"`).test(allowedBlock), `11i. ${TIERS_EVENT} is in ALLOWED_CLIENT_EVENTS`);
const propsRow = (propsBlock.match(new RegExp(`"${TIERS_EVENT}":\\s*frozenset\\(\\{[\\s\\S]*?\\}\\)`)) || [''])[0];
assert(TIER_PROPS.every((k) => propsRow.includes(`"${k}"`)), `11i2. ${TIERS_EVENT} CLIENT_EVENT_PROPS carries the §4 props`, propsRow);
assert(!new RegExp(`"${TIERS_EVENT}"`).test(nonIntent), `11i3. ${TIERS_EVENT} is NOT in NON_INTENT_EVENTS (intent)`);
const tierTrack = (SCREEN.match(new RegExp(`track\\('${TIERS_EVENT}', \\{[\\s\\S]*?\\}, 'RosterSetup'\\)`)) || [''])[0];
const emitted = (tierTrack.match(/^\s*\w+(?=[:,])/gm) || []).map((k) => k.trim());
assert(
  tierTrack && emitted.slice().sort().join(',') === TIER_PROPS.slice().sort().join(','),
  `11i4. the screen emits ${TIERS_EVENT} with exactly the §4 props`,
  emitted.join(','),
);
assert(/"tiers"|\btiers\b/.test((TAX.match(/stage\s+∈[^\n]*/) || [''])[0]), "11i5. the taxonomy's stage enum names tiers");

// 11j — the scope testIDs (picks id deliberately absent, decision 3).
for (const [src, id] of [
  [BOARD, 'testID="roster-setup.tiers.board"'],
  [BOARD, 'testID={`roster-setup.tiers.chip.${id}`}'],
  [BOARD, 'testID={`roster-setup.tiers.header.${t}`}'],
  [SCREEN, 'testID="roster-setup.tiers.save"'],
  [SCREEN, 'testID="roster-setup.tiers.retry"'],
]) assert(src.includes(id), `11j. ${id}`);
const ALLOW = read('scripts/testid-lint-allow.txt');
assert(
  ['roster-setup.tiers.chip.*', 'roster-setup.tiers.header.*', 'roster-setup.tiers.move.*'].every((g) => ALLOW.includes(g)),
  '11j2. the templated tier ids are in testid-lint-allow.txt',
);

// ── 12. Execute the tier helpers ─────────────────────────────────────────
const T = u.TIER_LADDER;
assert(T.join(',') === 'firsts_4plus,firsts_3,firsts_2,first_1,second,third,fourth,waivers',
  '12a. TIER_LADDER mirrors utils/tierBands TIERS');
const P = [
  { id: 'r1', position: 'RB', elo: 1700, tier: 'first_1' },
  { id: 'w1', position: 'WR', elo: 1650, tier: 'first_1' },
  { id: 'r2', position: 'RB', elo: 1600, tier: 'first_1' },
  { id: 'w2', position: 'WR', elo: 1500, tier: 'second' },
  { id: 'q1', position: 'QB', elo: 1450, tier: 'second' },
  { id: 't1', position: 'TE', elo: 1300, tier: 'third' },
];
const pos = Object.fromEntries(P.map((p) => [p.id, p.position]));
const pre0 = u.tierPrefill(P.slice().reverse());
assert(
  pre0.first_1.join(',') === 'r1,w1,r2' && pre0.second.join(',') === 'w2,q1' && pre0.third.join(',') === 't1'
    && pre0.firsts_2.length === 0 && pre0.waivers.length === 0,
  '12b. pre-fill: each player in his board tier, Elo descending across positions, empty tiers present',
  JSON.stringify(pre0),
);
assert(u.tierSavePayloads(pre0, pre0, pos).length === 0, '12c. nothing moved ⇒ nothing posted (Done writes nothing)');
// Up: q1 (second) → first_1 lands at the BOTTOM; down: r1 (first_1) → second lands at the TOP.
let b = u.applyTierMove(pre0, pre0, ['q1'], 'first_1');
assert(b.first_1.join(',') === 'r1,w1,r2,q1' && b.second.join(',') === 'w2',
  '12d. moved UP ⇒ bottom of the new tier (operator decision 6)', JSON.stringify(b));
b = u.applyTierMove(b, pre0, ['r1'], 'second');
assert(b.second.join(',') === 'r1,w2' && b.first_1.join(',') === 'w1,r2,q1',
  '12e. moved DOWN ⇒ top of the new tier', JSON.stringify(b));
const pay = u.tierSavePayloads(b, pre0, pos);
assert(
  JSON.stringify(pay) === JSON.stringify([
    { position: 'QB', tiers: { first_1: ['q1'] } },
    { position: 'RB', tiers: { second: ['r1'] } },
  ]),
  '12f. payloads: moved players only, split by position QB→TE, nobody unmoved posted',
  JSON.stringify(pay),
);
// Move back: r1 returns to first_1 in his pre-fill slot and posts nothing.
const back = u.applyTierMove(b, pre0, ['r1'], 'first_1');
assert(back.first_1.join(',') === 'r1,w1,r2,q1', '12g. moved back ⇒ his pre-fill slot again', JSON.stringify(back));
assert(
  JSON.stringify(u.tierSavePayloads(back, pre0, pos)) === JSON.stringify([{ position: 'QB', tiers: { first_1: ['q1'] } }]),
  '12g2. move-then-move-back posts nothing for that player',
);
// Several at once keep page order; posted order = page order.
const multi = u.applyTierMove(pre0, pre0, ['t1', 'w2', 'q1'], 'first_1');
assert(multi.first_1.join(',') === 'r1,w1,r2,w2,q1,t1', '12h. a batched move keeps page order at the edge', multi.first_1.join(','));
const multiPay = u.tierSavePayloads(multi, pre0, pos);
assert(
  JSON.stringify(multiPay.find((p) => p.position === 'WR')) === JSON.stringify({ position: 'WR', tiers: { first_1: ['w2'] } })
    && multiPay.map((p) => p.position).join(',') === 'QB,WR,TE',
  '12h2. batched move: one payload per position that moved',
  JSON.stringify(multiPay),
);
const pageOrder = u.applyTierMove(
  u.applyTierMove(pre0, pre0, ['w2'], 'first_1'), pre0, ['w1', 'r2'], 'second');
const wrPay = u.tierSavePayloads(
  u.applyTierMove(pre0, pre0, ['r1', 'r2'], 'third'), pre0, pos).find((p) => p.position === 'RB');
assert(
  pageOrder.second.join(',') === 'w1,r2,q1' && wrPay && wrPay.tiers.third.join(',') === 'r1,r2',
  '12h3. within a tier the posted ids follow page order',
  `${pageOrder.second.join(',')} | ${JSON.stringify(wrPay)}`,
);
// Picks and off-board players never reach a payload, even if one leaked onto a board.
const leaked = { ...pre0, first_1: [...pre0.first_1, 'PICK_2027_1'], second: [...pre0.second, 'offboard9'] };
assert(
  u.applyTierMove(pre0, pre0, ['PICK_2027_1'], 'firsts_4plus') === pre0
    && u.tierSavePayloads(leaked, pre0, pos).length === 0
    && u.tierSavePayloads(leaked, { ...leaked }, { ...pos, PICK_2027_1: 'PICK' }).length === 0
    // Even with a pre-fill that (wrongly) holds them, no core position ⇒ never posted.
    && u.tierSavePayloads(leaked, { ...pre0, firsts_2: ['PICK_2027_1', 'offboard9'] }, pos).length === 0,
  '12i. picks and off-board ids are never moved or posted',
);
// Rebase: a saved position is never re-posted; the rest still is.
const reb = u.tierRebase(pre0, pay[0]);
assert(
  JSON.stringify(u.tierSavePayloads(b, reb, pos)) === JSON.stringify([{ position: 'RB', tiers: { second: ['r1'] } }]),
  '12j. after QB saves, a Retry posts only RB',
);
// Review fix 2 — after a partial save, direction is judged against the
// BASELINE (where the server has the player), not the original pre-fill.
// t1 (TE, pre-fill third) was saved into first_1; the RB save failed.
const teSaved = u.applyTierMove(pre0, pre0, ['t1'], 'first_1');
const base1 = u.tierRebase(pre0, u.tierSavePayloads(teSaved, pre0, pos).find((p) => p.position === 'TE'));
assert(base1.first_1.join(',') === 'r1,w1,r2,t1' && base1.third.length === 0,
  '12m. rebase: a saved up-mover sits at the bottom of his saved tier in the baseline', JSON.stringify(base1));
const down1 = u.applyTierMove(teSaved, base1, ['t1'], 'second');
assert(down1.second.join(',') === 't1,w2,q1',
  '12m2. saved first_1 → second is a DOWN move vs the baseline ⇒ TOP of second (the server\'s edge)', down1.second.join(','));
const backToBase = u.applyTierMove(down1, base1, ['t1'], 'first_1');
assert(backToBase.first_1.join(',') === 'r1,w1,r2,t1' && u.tierSavePayloads(backToBase, base1, pos).length === 0,
  '12m3. moved back to his BASELINE tier ⇒ his baseline slot, nothing posted', JSON.stringify(backToBase.first_1));
const backToPre = u.applyTierMove(teSaved, base1, ['t1'], 'third');
assert(
  backToPre.third.join(',') === 't1'
    && JSON.stringify(u.tierSavePayloads(backToPre, base1, pos)) === JSON.stringify([{ position: 'TE', tiers: { third: ['t1'] } }])
    && u.applyTierMove(u.applyTierMove(teSaved, base1, ['w2'], 'third'), base1, ['t1'], 'third').third.join(',') === 't1,w2',
  '12m4. moved back to his PRE-FILL tier after a save elsewhere ⇒ a real move: posted, at the top edge (down from first_1)',
  JSON.stringify(backToPre.third),
);
const rDown = u.applyTierMove(pre0, pre0, ['r1'], 'second');
const base2 = u.tierRebase(pre0, u.tierSavePayloads(rDown, pre0, pos).find((p) => p.position === 'RB'));
assert(base2.second.join(',') === 'r1,w2,q1',
  '12m5. rebase: a saved down-mover sits at the top of his saved tier in the baseline', JSON.stringify(base2.second));
const mc = u.tierMoveCounts(b, pre0);
assert(mc.moved === 2 && mc.up === 1 && mc.down === 1, '12k. move counts: moved / up / down vs the pre-fill', JSON.stringify(mc));
assert(
  u.marketTierShown('second', 'second') === null && u.marketTierShown('second', 'first_1') === 'first_1'
    && u.marketTierShown('second', null) === null && u.marketTierShown('second', undefined) === null,
  '12l. market label only when the consensus tier differs from the page tier (operator decision 5)',
);

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
