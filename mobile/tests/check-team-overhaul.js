#!/usr/bin/env node
// Team overhaul structural guard (flag `overhaul.enabled`).
// Contract: docs/plans/team-overhaul/BUILD-CONTRACT.md §9, last paragraph.
//
// WHY THIS EXISTS. The overhaul surface is eight Trades-stack screens, an
// entry card, and one API module, and every claim below is about client
// SHAPE — registration, placement, absence, isolation — which no backend
// test and no typecheck can see. Under D-056 a structural guard is the only
// automated evidence these get.
//
// What is pinned, and why each one is a real regression rather than a style:
//   1. Every overhaul screen is registered exactly once, in the TRADES stack,
//      and nowhere in RootNav. A second registration gives a screen two entry
//      stacks with different back behavior.
//   2. No overhaul screen references FeedbackFAB. They are tab-stack screens,
//      already covered by RootNav's single global mount — a local one is the
//      #196/#197 double-FAB bug.
//   3. The entry card renders in TradesScreen directly AFTER
//      TeamReviewEntryCard (D9) and is gated on `useFlag('overhaul.enabled')`
//      or an active overhaul — never unconditionally.
//   4. Preference isolation + no taste learning (PRODUCT-SPEC invariants 2, 3;
//      BUILD-CONTRACT §7 decisions): no overhaul file touches
//      saveLeaguePreferences, /api/league/preferences, /api/tiers/save, or
//      swipeTrade. Likes here are assembly input, not Elo signal.
//   5. The priorities screen uses react-native-draggable-flatlist (the
//      sanctioned Tiers recipe) AND defines accessibilityActions (the no-drag
//      Move path, R7.7).
//   6. The summary renders the first-come race warning keyed by package_id —
//      on the affected package, not as a generic banner (R8.5).
//   7. Every member of the AttemptState union has a label in
//      ATTEMPT_STATE_LABEL, and the plan screen renders through that map, so a
//      new state cannot ship unlabeled.
//   8. Every testID family in §9 appears literally in overhaul source, so a
//      renamed id cannot silently lose its harness hook.
//   9. Sends are platform-agnostic (2026-09-07: Sleeper, MFL and ESPN all
//      send). The summary handles the ESPN pick blocker and the
//      reconnect_required blocker, and never gates the send CTA on a literal
//      Sleeper platform check — that gate is what used to hide Send on MFL/ESPN.
//  10. Offer cards are normalized at the fetch boundary (TestFlight 1.17.2
//      build 153: empty chips on review, crashes on "Build roadmaps" and
//      "Set priorities"). The server's `Offer.card` is the RAW
//      trade_card_to_dict dict (`give`/`receive`/`target_user_id`/
//      `fairness_score`), and the client TradeCard type is not. So:
//      api/overhaul.ts imports the deck's `normalizeTradeCard` and every
//      fetcher returning an Offer / RoadmapView / OverhaulView passes its
//      result through a normalize* call; no screen re-shapes the card
//      (`toCardData`) or reads the raw keys; and every screen that reads a
//      card's players in render guards the array (`receive_players ?? []`).
//
// Comment-stripped before matching, dependency-free, exits 1 on any failure.

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'src');
const SCREENS = [
  'OverhaulOutlook',
  'OverhaulAssets',
  'OverhaulTargets',
  'OverhaulReview',
  'OverhaulRoadmaps',
  'OverhaulPriorities',
  'OverhaulSummary',
  'OverhaulPlan',
];
const screenPath = (r) => path.join(SRC, 'screens', `${r}Screen.tsx`);
const API = path.join(SRC, 'api/overhaul.ts');
const ENTRY = path.join(SRC, 'components/OverhaulEntryCard.tsx');
const TABNAV = path.join(SRC, 'navigation/TabNav.tsx');
const ROOTNAV = path.join(SRC, 'navigation/RootNav.tsx');
const TRADES = path.join(SRC, 'screens/TradesScreen.tsx');

const pass = [], fail = [];
const ok = (n) => pass.push(n);
const bad = (n, d) => fail.push(`${n}\n      ${d}`);
const exists = (p) => fs.existsSync(p);
const read = (p) => (exists(p) ? fs.readFileSync(p, 'utf8') : (bad('file exists', `missing ${path.relative(ROOT, p)}`), ''));
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
const count = (s, re) => (s.match(re) || []).length;

const screens = Object.fromEntries(SCREENS.map((r) => [r, strip(read(screenPath(r)))]));
const api = strip(read(API));
const entry = strip(read(ENTRY));
const tabnav = strip(read(TABNAV));
const rootnav = strip(read(ROOTNAV));
const trades = strip(read(TRADES));
const overhaulFiles = { ...screens, OverhaulEntryCard: entry, 'api/overhaul': api };

// 1 — registered once, in the Trades stack, never in RootNav
{
  for (const r of SCREENS) {
    const inTab = count(tabnav, new RegExp(`name="${r}"`, 'g'));
    const inRoot = count(rootnav, new RegExp(`name="${r}"`, 'g'));
    if (inTab !== 1) bad(`1. ${r} registered exactly once in TabNav`, `found ${inTab} name="${r}" in TabNav.tsx`);
    else if (inRoot) bad(`1. ${r} registered ONLY in the Trades stack`, `${r} also appears in RootNav.tsx — two stacks means two back behaviors`);
    else if (!new RegExp(`import ${r}Screen from '\\.\\./screens/${r}Screen'`).test(tabnav)) {
      bad(`1. ${r} imported from its own screen file`, `TabNav does not import ${r}Screen from ../screens/${r}Screen`);
    } else ok(`1. ${r} registered once, in the Trades stack`);
  }
}

// 2 — no FeedbackFAB in any overhaul screen
{
  const offenders = SCREENS.filter((r) => /FeedbackFAB/.test(screens[r]));
  if (offenders.length) {
    bad('2. no FeedbackFAB in any overhaul screen',
      `${offenders.join(', ')} reference FeedbackFAB. They are TAB-STACK screens covered by ` +
      'RootNav\'s global mount (#188); a second FAB is the #196/#197 double-FAB bug.');
  } else ok('2. no overhaul screen references FeedbackFAB');
}

// 3 — entry card placement + gate
{
  const tr = trades.indexOf('<TeamReviewEntryCard');
  const ov = trades.indexOf('<OverhaulEntryCard');
  if (ov < 0) bad('3a. OverhaulEntryCard rendered in TradesScreen', 'no <OverhaulEntryCard in TradesScreen.tsx');
  else if (tr < 0) bad('3a. TeamReviewEntryCard still rendered', 'no <TeamReviewEntryCard to anchor the overhaul card below');
  else if (ov < tr) bad('3a. entry card directly after Team Review', '<OverhaulEntryCard renders BEFORE <TeamReviewEntryCard (D9 says directly below)');
  else {
    const between = trades.slice(tr, ov);
    // Only the Team Review card's own JSX may sit between the two mounts.
    if (/<[A-Z][A-Za-z]+/.test(between.replace(/<TeamReviewEntryCard/, ''))) {
      bad('3a. entry card DIRECTLY after Team Review', 'another component renders between TeamReviewEntryCard and OverhaulEntryCard');
    } else ok('3a. OverhaulEntryCard renders directly after TeamReviewEntryCard');
  }
  if (!/useFlag\('overhaul\.enabled'\)/.test(trades)) {
    bad('3b. entry gated on the flag', "TradesScreen has no useFlag('overhaul.enabled')");
  } else {
    // The mount must sit inside a conditional that names the flag value or
    // the active overhaul — find the nearest `{... ? (` before the mount.
    const before = trades.slice(Math.max(0, ov - 400), ov);
    const gate = before.match(/\{([^{}]*)\?\s*\(\s*$/);
    const cond = gate ? gate[1] : '';
    if (!gate) bad('3b. entry mount is conditional', 'no `{cond ? (` immediately before <OverhaulEntryCard');
    else if (!/overhaulOn|overhaul\.enabled/.test(cond) || !/activeOverhaul/.test(cond)) {
      bad('3b. entry gated on the flag OR an active overhaul', `gate is \`${cond.trim()}\` — must reference the flag and the active-overhaul probe`);
    } else ok('3b. entry card gated on `overhaul.enabled` or an active overhaul');
  }
}

// 4 — preference isolation, no taste learning
{
  const banned = ['saveLeaguePreferences', '/api/league/preferences', '/api/tiers/save', 'swipeTrade'];
  const hits = [];
  for (const [name, src] of Object.entries(overhaulFiles)) {
    for (const b of banned) if (src.includes(b)) hits.push(`${name} → ${b}`);
  }
  if (hits.length) {
    bad('4. no overhaul file writes preferences, tiers, or swipe learning',
      `${hits.join('; ')}. PRODUCT-SPEC invariants 2 (preference isolation) and 3 (likes are not Elo signal).`);
  } else ok('4. no overhaul file references saveLeaguePreferences / league preferences / tiers save / swipeTrade');
}

// 5 — priorities screen: drag recipe + accessible Move
{
  const s = screens.OverhaulPriorities;
  if (!/from 'react-native-draggable-flatlist'/.test(s)) {
    bad('5a. priorities uses react-native-draggable-flatlist', 'no import from react-native-draggable-flatlist (the sanctioned Tiers recipe)');
  } else ok('5a. priorities screen imports react-native-draggable-flatlist');
  if (!/accessibilityActions=/.test(s) || !/onAccessibilityAction=/.test(s)) {
    bad('5b. priorities defines accessibilityActions', 'no accessibilityActions/onAccessibilityAction — the drag-free Move path (R7.7) is missing');
  } else ok('5b. priorities screen defines accessibilityActions + handler');
}

// 6 — summary races keyed by package_id
{
  const s = screens.OverhaulSummary;
  const line = s.split('\n').find((l) => /\braces\b/.test(l) && /package_id/.test(l));
  if (!line) bad('6a. race warning keyed by package_id', 'no line in OverhaulSummaryScreen reads `races` together with `package_id`');
  else ok('6a. summary keys races by package_id');
  if (!/first come, first served/i.test(s)) bad('6b. race copy names first come, first served', 'R8.4 copy missing');
  else ok('6b. summary race copy says first come, first served');
}

// 7 — AttemptState union ↔ ATTEMPT_STATE_LABEL ↔ plan screen
{
  const m = api.match(/export type AttemptState\s*=([\s\S]*?);/);
  const map = api.match(/export const ATTEMPT_STATE_LABEL[^{]*\{([\s\S]*?)\};/);
  if (!m) bad('7. AttemptState union declared', 'no `export type AttemptState` in api/overhaul.ts');
  else if (!map) bad('7. ATTEMPT_STATE_LABEL declared', 'no `export const ATTEMPT_STATE_LABEL` in api/overhaul.ts');
  else {
    const states = [...m[1].matchAll(/'([a-z_]+)'/g)].map((x) => x[1]);
    const keys = [...map[1].matchAll(/^\s*([a-z_]+)\s*:/gm)].map((x) => x[1]);
    const missing = states.filter((st) => !keys.includes(st));
    if (!states.length) bad('7. AttemptState has members', 'parsed zero states');
    else if (missing.length) bad('7. every AttemptState has a label', `ATTEMPT_STATE_LABEL is missing: ${missing.join(', ')}`);
    else if (!/ATTEMPT_STATE_LABEL\[/.test(screens.OverhaulPlan)) {
      bad('7. plan screen renders through ATTEMPT_STATE_LABEL', 'OverhaulPlanScreen never indexes ATTEMPT_STATE_LABEL[...]');
    } else ok(`7. all ${states.length} attempt states labeled and rendered by the plan screen`);
  }
}

// 8 — testID families appear literally
{
  const families = [
    'overhaul.entry-card', 'overhaul.entry-start', 'overhaul.entry-resume',
    'overhaul.outlook.', 'overhaul.asset.', 'overhaul.continue',
    'overhaul.review.like', 'overhaul.review.pass', 'overhaul.review.build',
    'overhaul.roadmap.', 'overhaul.priority.list', 'overhaul.priority.move.',
    'overhaul.summary.send-all', 'overhaul.summary.copy',
    'overhaul.plan.refresh', 'overhaul.plan.send-next',
  ];
  const all = Object.values(overhaulFiles).join('\n');
  const missing = families.filter((f) => !all.includes(f));
  if (missing.length) bad('8. every §9 testID family appears literally', `missing: ${missing.join(', ')}`);
  else ok(`8. all ${families.length} testID families present`);
}

// 9 — all-platform sends: no Sleeper-literal gating, new blockers handled
{
  const s = screens.OverhaulSummary;
  if (!/can_propose_picks|pick_unsupported_on_platform/.test(s)) {
    bad('9a. summary handles the ESPN pick blocker', 'OverhaulSummaryScreen references neither can_propose_picks nor the pick_unsupported_on_platform code');
  } else ok('9a. summary references can_propose_picks / pick_unsupported_on_platform');
  if (/platform\s*[!=]==\s*'sleeper'/.test(s)) {
    bad('9b. send CTA not gated on a Sleeper platform check', "OverhaulSummaryScreen contains `platform === 'sleeper'` / `platform !== 'sleeper'` — sends go to Sleeper, MFL and ESPN; gate on handoff.mode and auth_state instead");
  } else ok('9b. summary has no `platform === \'sleeper\'` / `platform !== \'sleeper\'` gate');
  if (!/reconnect_required/.test(s)) bad('9c. summary handles reconnect_required', 'OverhaulSummaryScreen never references reconnect_required');
  else ok('9c. summary handles reconnect_required');
}

// 10 — offer cards normalized at the fetch boundary; screens read guarded TradeCards
{
  // (a) api/overhaul.ts imports normalizeTradeCard from ./trades and uses it
  if (!/import \{[^}]*\bnormalizeTradeCard\b[^}]*\} from '\.\/trades'/.test(api)) {
    bad('10a. api/overhaul.ts imports normalizeTradeCard from ./trades', "no `import { normalizeTradeCard } from './trades'` in api/overhaul.ts");
  } else if (!/normalizeTradeCard\(/.test(api)) {
    bad('10a. api/overhaul.ts calls normalizeTradeCard', 'imported but never called');
  } else ok('10a. api/overhaul.ts imports and calls normalizeTradeCard');

  // (b) every fetcher that returns an Offer / RoadmapView / OverhaulView normalizes
  const fetchers = [
    'getActiveOverhaul', 'getOverhaul', 'createOverhaul', 'updateOverhaulSettings',
    'generateOffers', 'getOffers', 'assembleRoadmaps', 'selectRoadmap', 'savePriorities',
    'refreshOverhaul',
  ];
  // A fetcher body runs from its `export async function` to the next
  // top-level `export` (param type literals may close with `}` at column 0).
  const unnormalized = [];
  for (const fn of fetchers) {
    const start = api.search(new RegExp(`^export async function ${fn}\\b`, 'm'));
    if (start < 0) { unnormalized.push(`${fn} (not found)`); continue; }
    const rest = api.slice(start + 1);
    const nextExport = rest.search(/^export /m);
    const body = nextExport < 0 ? rest : rest.slice(0, nextExport);
    if (!/\bnormalize(Offer|Roadmap|OverhaulView)\b/.test(body)) unnormalized.push(fn);
  }
  if (unnormalized.length) {
    bad('10b. every Offer/RoadmapView/OverhaulView fetcher normalizes its result',
      `no normalize* call in: ${unnormalized.join(', ')} — the raw server dict would reach a screen`);
  } else ok(`10b. all ${fetchers.length} Offer/RoadmapView/OverhaulView fetchers normalize`);

  // (c) no screen re-shapes the card or reads the raw server keys
  const rawReads = [];
  for (const r of SCREENS) {
    const src = screens[r];
    if (/\btoCardData\b/.test(src)) rawReads.push(`${r}: toCardData`);
    if (/\.card\??\.(give|receive)\b/.test(src)) rawReads.push(`${r}: .card.give/.receive`);
    if (/\btarget_user(name|_id)\b/.test(src)) rawReads.push(`${r}: target_user_*`);
  }
  if (rawReads.length) {
    bad('10c. no overhaul screen re-shapes the card or reads raw server keys',
      `${rawReads.join('; ')} — normalization lives in api/overhaul.ts, screens read TradeCard fields only`);
  } else ok('10c. no overhaul screen defines toCardData or reads .card.give/.receive/target_user_*');

  // (d) every screen that renders a card's players guards the array
  const readers = ['OverhaulRoadmaps', 'OverhaulPriorities', 'OverhaulSummary', 'OverhaulPlan'];
  const unguarded = readers.filter((r) => !/receive_players\s*\?\?\s*\[\]/.test(screens[r]));
  if (unguarded.length) {
    bad('10d. card player arrays guarded in render', `${unguarded.join(', ')} read receive_players without \`?? []\``);
  } else ok(`10d. ${readers.length} screens guard receive_players with \`?? []\``);
  const pr = screens.OverhaulPriorities;
  if (/\.fairness\s*\*/.test(pr) || !/Number\.isFinite\(/.test(pr)) {
    bad('10e. priorities guards card.fairness', 'OverhaulPrioritiesScreen does arithmetic on card.fairness directly / has no Number.isFinite guard — a missing score must render as —, not NaN or a throw');
  } else ok('10e. priorities screen guards card.fairness with Number.isFinite (no raw `.fairness *`)');
}

console.log(`\ncheck-team-overhaul: ${pass.length} passed, ${fail.length} failed`);
for (const p of pass) console.log(`  ✓ ${p}`);
if (fail.length) {
  console.error('\nFAILURES:');
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.error('\nThese pin BUILD-CONTRACT §9 and PRODUCT-SPEC invariants. ' +
    'If a change is genuinely intended, update the contract in the SAME commit.\n');
  process.exit(1);
}
console.log('');
