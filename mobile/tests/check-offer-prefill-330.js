#!/usr/bin/env node
// #330 (G4) — structural suite S-1..S-5 for Offer prefill + auto-run.
//
// Spec: docs/feedback/items/330-offer-prefill/prd.md. Almost nothing #330
// adds fails loudly: a handoff that never re-fires for a same-team repeat
// Offer, an armed auto-run ref surviving a gated-off choke point, a stale
// mutation resurrecting a pre-scope deck, or a zero-result empty state that
// silently relaxes the pin — all compile, demo correctly once, and break
// only the flow the feedback item is about. This file pins the structures
// those behaviors rest on. Assertions read COMMENT-STRIPPED source; every
// assertion names the sabotage it detects.
//
// Run: node tests/check-offer-prefill-330.js

'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const ROOT = path.join(__dirname, '..');
function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), 'utf8');
}
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}
const countOf = (text, needle) => text.split(needle).length - 1;
/** First match of `re` in `text`, or '' — keeps later .test()s null-safe. */
function region(text, re, label) {
  const m = text.match(re);
  assert(!!m, `${label} is findable`, `pattern ${re} matched nothing`);
  return m ? m[0] : '';
}

const tradesCode = stripComments(read('src/screens/TradesScreen.tsx'));
const leagueCode = stripComments(read('src/screens/LeagueSummaryScreen.tsx'));
const storeCode = stripComments(read('src/state/useFinderTargets.ts'));
const taxonomy = read('../backend/analytics_taxonomy.py');

// ═══════════════════════════════════════════════════════════════════════
// R-1 — the store handoff: one-shot shape, store-stamped seq
// ═══════════════════════════════════════════════════════════════════════

assert(
  /setHandoff: \(h\) =>\s*set\(\{ handoff: h \? \{ \.\.\.h, seq: \+\+_handoffSeq \} : null \}\)/.test(storeCode),
  '#330 setHandoff stamps a store-internal monotonic seq',
  'sabotage detected: letting callers supply seq (or dropping it) — a same-team repeat Offer then changes no dep and never re-fires the choke point',
);
assert(
  /clear: \(\) =>\s*set\(\{ pinnedGive: \[\], pinnedReceive: \[\], packageMode: true, handoff: null \}\)/.test(storeCode),
  '#330 clear() nulls the handoff with the pins',
  'sabotage detected: a handoff surviving clear() rides the league-switch GC into the WRONG league',
);
assert(
  /setHandoff: \(h: Omit<FinderHandoff, 'seq'> \| null\) => void;/.test(storeCode),
  '#330 the setHandoff type forbids caller-supplied seq (Omit)',
);

// ═══════════════════════════════════════════════════════════════════════
// S-1 — handleRowAction sets the handoff; dep array gains `selected`
// ═══════════════════════════════════════════════════════════════════════

const actionDecl = region(
  leagueCode,
  /const handleRowAction = React\.useCallback\([\s\S]*?\n  \);/,
  'S-1 handleRowAction',
);
assert(
  /store\.setHandoff\(\{[\s\S]*?userId: selected\.tc\.team\.user_id,/.test(actionDecl),
  'S-1 the handoff scopes to the drilled-in team (selected.tc.team.user_id)',
  'sabotage detected: scoping to the mirror roster or a stale closure team',
);
assert(
  /selected\.tc\.team\.display_name \|\|\s*selected\.tc\.team\.username \|\|\s*selected\.tc\.team\.user_id,/.test(actionDecl),
  'S-1 the opponent name uses the focusedTeamName fallback chain verbatim',
  'sabotage detected: a bare display_name shows "Trading with undefined" for teams without one',
);
assert(
  /autoRun: true,/.test(actionDecl),
  'S-1 the handoff carries autoRun: true',
);
assert(
  /\[navigation, candidatePos, candidateDir, selectedIdx, route\.name, selected\],?\s*\)/.test(actionDecl),
  'S-1 the callback dep array contains `selected`',
  'sabotage detected: dropping it — the closure now READS selected, so a stale drill-in team gets scoped (the missing dep was inert before #330, live after)',
);
assert(
  countOf(leagueCode, 'setHandoff(') === 1,
  'S-1 handleRowAction is the ONLY handoff writer on this screen',
  `saw ${countOf(leagueCode, 'setHandoff(')} call sites`,
);

// ═══════════════════════════════════════════════════════════════════════
// S-2 — TradesScreen consumes exactly once, through the ONE choke point
// ═══════════════════════════════════════════════════════════════════════

const consumeEffect = region(
  tradesCode,
  /const navFocused = useIsFocused\(\);[\s\S]*?\}, \[navFocused, finderHandoff, finderHubOn, finderMode\]\);/,
  'S-2 the focus-gated consume effect',
);
assert(
  /if \(!navFocused \|\| !finderHandoff\) return;/.test(consumeEffect),
  'S-2 consumption is focus-gated and inert on a null handoff',
  'sabotage detected: a raw store subscription consumes while another screen is focused (or loops on null)',
);
assert(
  /useFinderTargets\.getState\(\)\.setHandoff\(null\);/.test(consumeEffect),
  'S-2 the consume site nulls the store handoff (one-shot)',
  'sabotage detected: an un-nulled handoff re-consumes on every refocus — a new deck sweep per tab visit',
);
assert(
  /setSheetOpponent\(finderHandoff\.opponent\);/.test(consumeEffect),
  'S-2 the opponent lands in sheet state (the #269 source scopedOpponent reads)',
  'sabotage detected: writing route params instead — ignored while trades.sheet_targeting is ON',
);
assert(
  /if \(finderHubOn && finderMode\) \{\s*autoRunPendingRef\.current = true;\s*setAutoRunSeq\(finderHandoff\.seq\);\s*\}/.test(consumeEffect),
  'S-2 the ref-arm (and seq bump) is guarded by the SAME finderHubOn && finderMode gate the choke point uses (R-8)',
  'sabotage detected: arming unconditionally leaves a live ref to detonate when the user later enters a finder mode',
);

const chokeEffect = region(
  tradesCode,
  /const finderScopeSeen = useRef\(false\);[\s\S]*?\}, \[finderMode, scopedOpponent, autoRunSeq\]\);/,
  'S-2 the scoped-opponent choke-point effect',
);
assert(
  /\}, \[finderMode, scopedOpponent, autoRunSeq\]\);/.test(chokeEffect),
  'S-2 the choke-point deps contain autoRunSeq (B-1)',
  'sabotage detected: dropping it — a repeat Offer to the SAME team changes no dep, the second handoff lands its pin on the stale deck silently (the original #330 symptom reborn)',
);
assert(
  /if \(\(finderScopeSeen\.current \|\| autoRun\) && scopedOpponent\) \{/.test(chokeEffect),
  'S-2 an armed handoff widens the fresh-mount gate (generate on first observation)',
  'sabotage detected: keeping the bare finderScopeSeen gate makes the cold-mount handoff a prefill with no search',
);
assert(
  /autoRunPendingRef\.current = false;/.test(chokeEffect),
  'S-2 the ref is cleared inside the dispatch branch — one generation per handoff',
);
assert(
  countOf(tradesCode, 'generateMutation.mutate(') === 8,
  'S-2 the count of generateMutation.mutate call sites does not increase over base (8)',
  `saw ${countOf(tradesCode, 'generateMutation.mutate(')} — a new dispatch site is a second generation per handoff waiting to happen`,
);
assert(
  countOf(tradesCode, 'setAutoRunSeq(') === 1,
  'S-2 exactly one autoRunSeq writer (the consume site)',
);

// ═══════════════════════════════════════════════════════════════════════
// S-3 — analytics: the auto-run emits find_trades_tapped source:'league_offer'
// ═══════════════════════════════════════════════════════════════════════

assert(
  /if \(autoRun\) \{\s*track\('find_trades_tapped', \{ source: 'league_offer', mode: deckMode \}, 'Trades'\);\s*\}/.test(chokeEffect),
  "S-3 the auto-run dispatch emits find_trades_tapped {source:'league_offer', mode}",
  'sabotage detected: dropping the emit makes handoff adoption unmeasurable; emitting outside the autoRun branch double-counts in-place team picks',
);
// Source-of-truth cross-check (the check-league-candidates-300.js pattern):
// the props must be REGISTERED — an unregistered prop is stripped by ingest
// behind a 200, with no 4xx and no client log.
const propsRow = (taxonomy.match(/"find_trades_tapped":\s*frozenset\(\{([^}]*)\}\)/) || [])[1];
assert(
  !!propsRow && /"source"/.test(propsRow) && /"mode"/.test(propsRow),
  'S-3 find_trades_tapped registers {source, mode} in backend/analytics_taxonomy.py',
  `sabotage detected: prop-name-level ingest would silently strip the new value (row: ${propsRow})`,
);
assert(
  /"find_trades_tapped",/.test(taxonomy),
  'S-3 find_trades_tapped is an allowed client event',
);

// ═══════════════════════════════════════════════════════════════════════
// S-4 — the honest scoped empty state: scope-based trigger, never relaxes
// ═══════════════════════════════════════════════════════════════════════

const completionEffect = region(
  tradesCode,
  /useEffect\(\(\) => \{\s*if \(job\?\.status !== 'complete'\) return;[\s\S]*?\}, \[job\?\.job_id, job\?\.status, job\?\.cards\.length\]\);/,
  'S-4 the zero-card completion effect',
);
assert(
  /if \(!pinned \|\| !scopedOpponent\) return;/.test(completionEffect),
  'S-4 the trigger is pin-present AND opponent-scoped — never handoff origin',
  'sabotage detected: keying on the handoff makes a manual re-run of the same scoped search fall back to the old toast (B-3 dishonesty)',
);
assert(
  !/finderHandoff|autoRun/.test(completionEffect),
  'S-4 the completion effect never reads handoff/auto-run state (origin-independent)',
);
assert(
  /\}, \[job\?\.job_id, job\?\.status, job\?\.cards\.length\]\);/.test(completionEffect),
  'S-4 the effect keys on job_id too',
  'sabotage detected: without it a second zero-card completion (same status, same length) never re-fires after handleFindTrades cleared the card',
);
assert(
  /const \{ pinnedGive: pg, pinnedReceive: pr \} = useFinderTargets\.getState\(\);/.test(completionEffect),
  'S-4 pins are read from the store at completion time, not a render closure',
);

// The toast is suppressed under EXACTLY the card's trigger condition.
const zeroToastBlock = region(
  tradesCode,
  /if \(snapshot\.status === 'complete' && snapshot\.cards\.length === 0\) \{[\s\S]*?tone: 'warn',\s*\}\);\s*\}/,
  'S-4 the onSuccess zero-card block',
);
assert(
  /if \(pg\.length \+ pr\.length > 0 && scopedOpponent\) return;/.test(zeroToastBlock),
  'S-4 the generic zero-result toast is suppressed when pinned + scoped (the card is the single surface)',
  'sabotage detected: toast and card both firing, or the toast surviving as the only surface',
);

// The card itself: honest copy naming the relaxed pass, and the way back.
assert(
  /testID="trades\.scoped-empty\.back"/.test(tradesCode) &&
    /label="Back to league rankings"/.test(tradesCode),
  "S-4 the empty card's action carries testID trades.scoped-empty.back",
);
const scopedEmptyCard = region(
  tradesCode,
  /: scopedEmpty \? \([\s\S]*?<\/Card>\s*\) : \(/,
  'S-4 the scopedEmpty deck-slot branch',
);
assert(
  /navigation\.navigate\('League', \{ screen: 'LeagueRankings' \}\)/.test(scopedEmptyCard),
  'S-4 the link returns to the League tab root (LeagueRankings)',
  'sabotage detected: navigating to an unregistered route or the legacy root-stack push',
);
assert(
  countOf(scopedEmptyCard, 'even after stretching the fairness band') === 2 &&
    /No trade found/.test(scopedEmptyCard),
  'S-4 both copy bodies claim the relaxed pass ALREADY ran (N-1 honesty — do not "fix" back to "under your current settings")',
);
assert(
  /Your player and team stayed locked\./.test(scopedEmptyCard) &&
    /Your target and team stayed locked\./.test(scopedEmptyCard),
  'S-4 the copy states the never-relax guarantee for both verbs',
);

// Never-relax (R-7): no zero-card handler mutates pin or scope state. The
// two zero-card regions must be free of every relaxing call.
for (const [label, text] of [
  ['completion effect', completionEffect],
  ['onSuccess zero-card block', zeroToastBlock],
  ['scopedEmpty card', scopedEmptyCard],
]) {
  assert(
    !/setSide\(|\.clear\(\)|removeGive\(|removeReceive\(|setSheetOpponent\(null\)/.test(text),
    `S-4 never-relax: the ${label} touches no pin or scope state`,
    'sabotage detected: a zero-card handler silently dropping the pin or the scope — the operator decision this feature exists to honor',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// S-5 — the generation epoch (R-10)
// ═══════════════════════════════════════════════════════════════════════

const resetFn = region(
  tradesCode,
  /function resetDeckForNewTargets\(\) \{[\s\S]*?\n  \}/,
  'S-5 resetDeckForNewTargets',
);
assert(
  /deckEpochRef\.current \+= 1;/.test(resetFn),
  'S-5 every reset opens a new generation epoch',
  'sabotage detected: without the increment the guard compares equal forever and the B-2 race returns',
);
assert(
  /setScopedEmpty\(null\);/.test(resetFn),
  'S-5 a reset also clears the scoped zero-result card',
);
assert(
  /onMutate: \(\) => \(\{ epoch: deckEpochRef\.current \}\)/.test(tradesCode),
  'S-5 every dispatch stamps the current epoch into the mutation context',
);
assert(
  /import \{ applyJobResult \} from '\.\.\/utils\/applyJobResult';/.test(tradesCode),
  'S-5 result application goes through the pure R-10 helper',
);
assert(
  countOf(tradesCode, 'applyJobResult(') >= 3,
  'S-5 the helper guards onSuccess, onError, AND the polling attach',
  `saw ${countOf(tradesCode, 'applyJobResult(')} call sites — expected at least 3`,
);
const pollGuard = /if \(applyJobResult\(next, tickEpoch, deckEpochRef\.current\) === null\) return;/.test(tradesCode);
assert(
  pollGuard,
  'S-5 the poll tick drops results from a superseded epoch',
  'sabotage detected: an in-flight status fetch racing the reset cleanup writes a stale snapshot',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All #330 offer-prefill structural checks passed.');
