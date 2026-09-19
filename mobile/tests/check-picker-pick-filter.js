#!/usr/bin/env node
// B3 (docs/reviews/2026-08-18-bug-sweep/ticket.md) — the picker's PICK
// filter painted a BLANK SHEET.
//
// WHY THIS EXISTS. `build_universal_pool` stamps the 12 generic rungs with
// a FAKE player position (`_PICK_POS = {1:"RB",2:"WR",3:"TE",4:"QB"}`,
// backend/server.py:1464) and marks them as picks by `team == "PICK"`
// alone (:1478). The old one-field predicate `p.pos === posFilter` therefore
// matched ZERO rows under the PICK chip in the calculator's default "Real
// values" mode, and listed draft picks under RB/WR/TE/QB. The fix mirrors
// the canonical backend predicate `trade_service.is_pick_asset`
// (backend/trade_service.py:1138-1147) — `position == "PICK" or team ==
// "PICK"` — and applies it two-sided.
//
// Nothing here fails loudly. A half-fix that only tests `p.pos === 'PICK'`
// compiles clean, works in the demo calculator (mock picks carry
// `pos:'PICK'`) and stays blank in the live mode users actually open. The
// runtime block below runs the REAL predicates lifted out of the source, so
// dropping either field turns this RED. Each assertion names its sabotage.
//
// Run: node tests/check-picker-pick-filter.js

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

const REL = 'src/components/PlayerPickerModal.tsx';
const raw = read(REL);
const src = stripComments(raw);

// ── The magic string is the server's. A comment naming the canonical
// predicate is the only thing stopping a future edit from "simplifying"
// `nflTeam === 'PICK'` away as dead code.
assert(
  /trade_service\.is_pick_asset|is_pick_asset/.test(raw),
  'the predicate cites the canonical backend `trade_service.is_pick_asset`',
);

// ── Sabotage "half the predicate": either field alone leaves a live pick
// family unmatched (generic rungs, or owned picks on a server that stops
// echoing team).
const predMatch = src.match(/const isPickAsset = \(p: CalcPlayer\) => ([^;]+);/);
assert(!!predMatch, 'isPickAsset is a module-scope predicate over CalcPlayer');
const predBody = predMatch ? predMatch[1] : 'false';
assert(/p\.pos === 'PICK'/.test(predBody), "isPickAsset tests p.pos === 'PICK'");
assert(
  /p\.nflTeam === 'PICK'/.test(predBody),
  "isPickAsset tests p.nflTeam === 'PICK' (the generic-rung marker)",
);

// ── Sabotage "leave the old filter in place": the one-field compare is the
// bug itself, and the two-sided rule must be what the list consumes.
assert(
  !/posFilter \? p\.pos === posFilter : true/.test(src),
  'the one-field `p.pos === posFilter` filter is gone',
);
assert(
  /\.filter\(\(p\) => matchesPosFilter\(p, posFilter\)\)/.test(src),
  'the visible list filters through matchesPosFilter',
);

const fnMatch = src.match(
  /const matchesPosFilter = \(p: CalcPlayer, posFilter: CalcPos \| null\) => \{([\s\S]*?)\n\};/,
);
assert(!!fnMatch, 'matchesPosFilter is a module-scope two-arg predicate');
const fnBody = fnMatch ? fnMatch[1] : 'return false;';

// ── Sabotage "PICK chip compares pos again": the PICK branch must go
// through isPickAsset, never `p.pos` on its own.
const pickBranch = (fnBody.match(/posFilter === 'PICK' \?([\s\S]*?):/) || [, ''])[1];
assert(
  /isPickAsset\(p\)/.test(pickBranch) && !/p\.pos/.test(pickBranch),
  'the PICK branch keeps isPickAsset(p) and never tests p.pos alone',
  pickBranch.trim(),
);
// ── Sabotage "one-sided fix": picks must also STOP leaking into RB/WR/TE/QB.
assert(
  /!isPickAsset\(p\)/.test(fnBody),
  'the player-position branch excludes picks (the #222 half of the bug)',
);

// ── The blank sheet had no explanation of its own. ESPN in-league
// (`picks_supported:false`) and the TradesScreen target picker legitimately
// hold no picks, so the empty state is load-bearing there, not a fallback.
assert(/ListEmptyComponent=/.test(src), 'the FlatList has a ListEmptyComponent');
assert(
  raw.includes('No draft picks available here.') && raw.includes('No players match.'),
  'the empty state is scoped: pick copy under PICK, player copy otherwise',
);
assert(
  /posFilter === 'PICK'\s*\?\s*'No draft picks available here\.'/.test(src),
  'the pick copy is gated on the PICK filter',
);

// ── The chips had no testID, which is why no Maestro flow could reach them.
// They must also be LOWERCASE. Two reasons, and the second is the sharp one:
//   1. Every sibling lowercases deliberately — FreeAgentsScreen.tsx:166
//      `free-agents.pos-tab.${f.toLowerCase()}`, PickAnchorScreen.tsx:324.
//   2. scripts/testid-lint.sh:50 extracts flow ids with the LOWERCASE-ONLY
//      class `[a-z0-9.*-]+`. An id like `calc.picker.filter.PICK` is
//      silently TRUNCATED at the uppercase run, so the lint checks a
//      prefix and passes by accident — it cannot verify these ids at all.
assert(
  /testID=\{`calc\.picker\.filter\.\$\{pos\.toLowerCase\(\)\}`\}/.test(src),
  'filter chips carry a LOWERCASED testID calc.picker.filter.<pos>',
);
assert(
  !/testID=\{`calc\.picker\.filter\.\$\{pos\}`\}/.test(src),
  'the raw `${pos}` template is gone (it emitted QB/RB/WR/TE/PICK uppercase)',
);
// Sabotage "lowercase is just cosmetic": prove the emitted ids only survive
// testid-lint.sh's extractor once lowercased.
const LINT_CLASS = /^[a-z0-9.*-]+$/; // scripts/testid-lint.sh:50, verbatim
const POSITIONS = ((src.match(/const POSITIONS: CalcPos\[\] = \[([^\]]+)\]/) || [, ''])[1])
  .split(',')
  .map((t) => t.trim().replace(/'/g, ''))
  .filter(Boolean);
assert(POSITIONS.length === 5, 'POSITIONS is the five calculator chips', POSITIONS.join('|'));
assert(
  POSITIONS.every((pos) => LINT_CLASS.test(`calc.picker.filter.${pos.toLowerCase()}`)) &&
    !POSITIONS.every((pos) => LINT_CLASS.test(`calc.picker.filter.${pos}`)),
  "lowercasing is what makes these ids visible to testid-lint.sh's [a-z0-9.*-] extractor",
);

// ── REGRESSION GUARD: the empty state must not LIE DURING LOAD ──────────
// Adding ListEmptyComponent turned a blank area into an assertion, and an
// assertion can be wrong. `filtered === []` while the pool's queries are in
// flight is UNKNOWN, not empty. This is live, not theoretical: TradesScreen
// enables the target picker's two queries ON OPEN —
//   TradesScreen.tsx:2199  enabled: deck.length > 0 || targetPickerOpen,
//   TradesScreen.tsx:2205  enabled: !!leagueId && (deck.length > 0 || targetPickerOpen),
// so on a cold Trades home with an empty deck, opening the sheet starts both
// fetches from zero and the sheet would assert "No players match." until they
// land. The house fix is a `loading` prop — SwapPlayerSheet.tsx:72/82/169,
// mounted at TradesScreen.tsx:6423; web does the same (web/js/app.js:3176).
assert(/\bloading\?: boolean;/.test(src), 'PlayerPickerModal declares an optional `loading` prop');
assert(
  /\bloading = false,/.test(src),
  'loading defaults to false, so static-pool callers (the demo calculator) are unchanged',
);

// The empty prop runs to `renderItem=`, which follows it directly.
const emptyBlock = (src.match(/ListEmptyComponent=\{([\s\S]*?)renderItem=/) || [, ''])[1];
assert(!!emptyBlock.trim(), 'ListEmptyComponent is still wired ahead of renderItem');
// Sabotage "render the empty copy anyway while loading": `loading` has to be
// the OUTER branch, not a detail nested under the posFilter ternary.
assert(
  /^\s*loading\s*\?/.test(emptyBlock),
  'ListEmptyComponent branches on `loading` first',
  emptyBlock.trim().slice(0, 80),
);
// First `) : (` is the top-level split — the loading branch holds no ternary.
const splitAt = emptyBlock.search(/\)\s*:\s*\(/);
assert(splitAt > 0, 'the loading branch has a not-loading alternative');
const loadingBranch = emptyBlock.slice(0, splitAt);
const settledBranch = emptyBlock.slice(splitAt);
// Sabotage "keep the copy in both branches": the whole point is that a
// pending pool never claims to be an empty one.
assert(
  !/No players match\.|No draft picks available here\./.test(loadingBranch),
  'the loading branch never asserts the pool is empty',
  loadingBranch.trim(),
);
assert(
  /No players match\./.test(settledBranch) &&
    /No draft picks available here\./.test(settledBranch),
  'both empty copies live in the not-loading branch (the B3 empty state survives)',
);
// The loading branch has to actually say something — a `null` here restores
// the pre-fix blank sheet under a different name.
assert(
  /ActivityIndicator/.test(loadingBranch) && /Loading/.test(loadingBranch),
  'the loading branch shows a spinner + copy (house pattern: SwapPlayerSheet.loadingRow)',
  loadingBranch.trim(),
);

// ── Sabotage "add the prop, never pass it": a defaulted prop nobody wires
// is the same bug with extra steps. Every mount in the files this fix owns
// must pass it.
// TradesScreen is the mount that actually exhibited the bug: its pool queries
// are enabled BY the picker opening, so a cold deck starts them from zero.
for (const [rel, expected] of [
  ['src/screens/TradeCalculatorScreen.tsx', 2],
  ['src/components/InLeagueCalculator.tsx', 2],
  ['src/screens/TradesScreen.tsx', 1],
]) {
  const mounts = stripComments(read(rel))
    .split('<PlayerPickerModal')
    .slice(1)
    .map((chunk) => chunk.split('/>')[0]);
  assert(mounts.length === expected, `${rel} mounts PlayerPickerModal ${expected}×`, `${mounts.length}`);
  mounts.forEach((m, i) => {
    assert(/\bloading=\{/.test(m), `${rel} mount #${i + 1} passes loading=`);
  });
}

// ── Runtime: the REAL predicates, lifted from the source and stripped of
// their type annotations, over a pool holding all three pick shapes.
const js = (text) => text.replace(/: CalcPlayer/g, '').replace(/: CalcPos \| null/g, '');
// eslint-disable-next-line no-new-func
const isPickAsset = new Function('p', `return ${js(predBody)};`);
// eslint-disable-next-line no-new-func
const matchesPosFilter = new Function('p', 'posFilter', 'isPickAsset', js(fnBody));
const run = (pool, posFilter) =>
  pool.filter((p) => matchesPosFilter(p, posFilter, isPickAsset));

const pool = [
  { id: 'rung-early-1st', pos: 'RB', nflTeam: 'PICK' }, // generic rung, fake pos
  { id: 'own-2027-1st', pos: 'PICK', nflTeam: 'PICK' }, // owned league pick
  { id: 'brobinson', pos: 'RB', nflTeam: 'ATL' }, // a real RB
];
assert(run(pool, 'PICK').length === 2, 'PICK keeps both pick shapes', `${run(pool, 'PICK').length}`);
assert(run(pool, 'RB').length === 1, 'RB keeps only the real RB', `${run(pool, 'RB').length}`);
assert(run(pool, 'RB')[0]?.id === 'brobinson', 'the RB row survives, the rung does not');
assert(run(pool, null).length === 3, 'no filter keeps every row (nothing disappears from ALL)');
assert(run(pool, 'QB').length === 0, 'an unrepresented position is legitimately empty');
// Picks authored as pos 'PICK' / nflTeam '—' still match. (This shape came
// from the removed demo board; live rows carry the server's is_pick.)
assert(
  run([{ id: 'demo1', pos: 'PICK', nflTeam: '—' }], 'PICK').length === 1,
  'demo picks (nflTeam "—") still match the PICK chip',
);

process.exit(failures ? 1 : 0);
