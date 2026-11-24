#!/usr/bin/env node
// Three dead ends from the 2026-11-22 Release sim pass (D, E, F).
//
// WHY THIS EXISTS.
//   D. After acting on the last card, the deck slot swapped the tall card for
//      the short end state and iOS kept the scroll offset, deep in empty
//      space: the user saw a blank screen until they scrolled up.
//   E. Team Review's "Find my trades" (no partner scoped) handed nothing to
//      the deck and returned to the builder; the user had to scroll down and
//      tap Find a Trade. Unscoped now parks the same hand-off the landing's
//      Find a Trade makes with no partner (origin 'calculator', opponent
//      null), which the landing forwards into the pushed results deck.
//   F. Win Now with no projections printed "Source unavailable · timestamp
//      unavailable · Coverage unavailable" and "Source unavailable", and its
//      Refresh gave no feedback. It now shows the Standings line
//      (NO_FORECAST_LINE) and "Checked just now." after a tapped refresh.
//
// What is pinned:
//   1. TradesScreen scrolls back to the deck slot when the fronted card goes
//      away because the index moved past it (not on a reset to 0), only when
//      the user is below the slot.
//   2. TeamReviewScreen's Finish hands off with or without a partner; the
//      unscoped hand-off is the calculator-origin, null-opponent one, and
//      TradesScreen's choke point still auto-runs a calculator-origin
//      hand-off with no partner (the gate this relies on).
//   3. WinNowScreen: no source receipt for an unavailable baseline, the
//      unavailable line is NO_FORECAST_LINE, and a tapped refresh sets the
//      "Checked just now." line.
//
// HONEST LABEL (G-035): presence of exact wirings in source, not runtime.
//
// Run: node tests/check-deck-flow-polish.js   (or npm run test:deck-flow-polish)

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const failures = [];
const passes = [];
const ok = (n) => passes.push(n);
const bad = (n, d) => failures.push(`${n}\n      ${d}`);
const check = (n, cond, d = '') => (cond ? ok(n) : bad(n, d || 'condition false'));
const read = (rel) => {
  const p = path.join(ROOT, rel);
  if (!fs.existsSync(p)) { bad(`exists: ${rel}`, 'missing'); return ''; }
  return fs.readFileSync(p, 'utf8');
};
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

// ── 1 (D). The deck's end state is brought into view ──────────────────────
{
  const s = strip(read('src/screens/TradesScreen.tsx'));
  const eff = /const hadTopCardRef = useRef\(false\);\s*useEffect\(\(\) => \{([\s\S]*?)\}, \[rawTopCard, deckIdx\]\);/.exec(s);
  check('1a. an effect watches the fronted card and the index', !!eff);
  const body = eff ? eff[1] : '';
  check('1b. it fires on card → no card with the index past 0 (a reset to 0 is left alone)',
    /if \(hadTopCardRef\.current && !has && deckIdx > 0\)/.test(body));
  check('1c. it scrolls to the deck slot, only when the user is below it',
    /const y = Math\.max\(deckCardY\.current - space\.md, 0\);/.test(body)
      && /if \(guideScrollYRef\.current > y\) \{\s*mainScrollRef\.current\?\.scrollTo\(\{ y, animated: true \}\);/.test(body));
  check('1d. the offset it compares is tracked on every scroll (not flag-scoped)',
    /guideScrollYRef\.current = e\.nativeEvent\.contentOffset\.y;/.test(s));
}

// ── 2 (E). Find my trades lands on results ────────────────────────────────
{
  const t = strip(read('src/screens/TeamReviewScreen.tsx'));
  const finish = t.slice(t.indexOf('testID="team-review.finish"'), t.indexOf("nav.navigate('TradesHome'"));
  check('2a. Finish hands off unconditionally (not only `if (scoped)`)',
    /useFinderTargets\.getState\(\)\.setHandoff\(\{/.test(finish) && !/if \(scoped\) \{/.test(finish));
  check('2b. unscoped = the landing Find a Trade hand-off (calculator origin, no partner)',
    /\.\.\.\(scoped\s*\?\s*\{ opponent: \{ userId: scoped\.id, name: scoped\.name \} \}\s*:\s*\{ opponent: null, origin: 'calculator' as const \}\)/.test(finish));
  const s = strip(read('src/screens/TradesScreen.tsx'));
  check('2c. the deck still auto-runs a calculator-origin hand-off with no partner',
    /\(scopedOpponent \|\| \(autoRun && autoRunOrigin === 'calculator'\)\)/.test(s));
  check('2d. the landing still forwards a hand-off into the pushed TradeDeck',
    /if \(resultsPushLive && finderHubOn && finderMode\) \{[\s\S]*?navigation\?\.push\?\.\('TradeDeck', \{/.test(s));
}

// ── 3 (F). Win Now's empty state and refresh feedback ─────────────────────
{
  const w = strip(read('src/screens/WinNowScreen.tsx'));
  check('3a. the unavailable line is the Standings line',
    /import \{ NO_FORECAST_LINE \} from '\.\.\/utils\/standingsTable';/.test(w)
      && /baseline\?\.status === 'unavailable' && <Text testID="win-now\.unavailable" style=\{s\.body\}>\{NO_FORECAST_LINE\}<\/Text>/.test(w));
  check('3b. no source receipt for an unavailable baseline',
    /\{baseline && baseline\.status !== 'unavailable' && <Text testID="win-now\.source"/.test(w));
  check('3c. a tapped refresh leaves a "Checked just now." line',
    /setRefreshed\(cause === 'refresh'\)/.test(w)
      && /\{refreshed && !loadError && <Text testID="win-now\.refreshed"[^>]*>Checked just now\.<\/Text>\}/.test(w));
}

for (const p of passes) console.log(`  ✓ ${p}`);
if (failures.length) {
  console.error('\nFAILURES:');
  for (const f of failures) console.error(`  ✗ ${f}`);
  console.error(`\ncheck-deck-flow-polish: ${failures.length} FAILED`);
  process.exit(1);
}
console.log(`\ncheck-deck-flow-polish: all ${passes.length} checks passed`);
