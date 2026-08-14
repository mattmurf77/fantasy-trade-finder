#!/usr/bin/env node
// #319 — Matches value disclosure: the lazy evaluate fetch, the TradeCard
// footer slot, the honesty caveat, and the no-fork rule.
//
// Named sabotages (plan docs/feedback/items/318-awaiting-dismiss/plan-2026-08-13.md):
//   S-1 lazy-fetch:  set the evaluate query to `enabled: true` (or drop
//       `enabled`) → the disclosure prices every row on scroll. tsc can't
//       see it; a Maestro expand-flow still passes.
//   S-2 footer-leak: render TradeCard's `footer` unconditionally inside the
//       deck/disposition branch, make the prop required, or render it twice
//       → deck cards grow a Matches-only UI. Pins that the footer is the
//       card's FINAL block and that no deck mount passes one.
//   S-3 honesty:     delete the dropped_player_ids caveat branch → a trade
//       with unvalued assets renders a confident verdict that excludes them,
//       silently.
//   S-4 reuse:       fork the bar (local "Dynasty value swing" markup in
//       MatchValueSection) → inbox and deck can disagree about the same
//       package. Comment-stripped before the absence assertion — a comment
//       mentioning the string must not mask a real fork, and a fork must
//       not hide behind "it's just a comment".
//
// Structural/textual over the real sources; comment-strip before every
// ABSENCE assertion. Seed-independent: no simulator, no backend.
//
// Run: node tests/check-match-value-section.js

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');

// Strip /* */ blocks and // line comments (protecting URLs like https://)
// so absence assertions can't be fooled by prose.
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`])\/\/[^\n]*/g, '$1');
}

let failures = 0;
const ok = (name) => console.log(`PASS  ${name}`);
const fail = (name, detail) => {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
};
const assert = (cond, name, detail) => (cond ? ok(name) : fail(name, detail));

const MVS = read('src/components/MatchValueSection.tsx');
const MVS_CODE = stripComments(MVS);
const TC = read('src/components/TradeCard.tsx');
const TC_CODE = stripComments(TC);
const SCREEN = read('src/screens/MatchesScreen.tsx');
const TRADES = stripComments(read('src/screens/TradesScreen.tsx'));

// ── S-1: the evaluate query is disclosure-gated ────────────────────────────
assert(/useQuery\(/.test(MVS_CODE), '1. MatchValueSection uses useQuery');
assert(
  /queryFn:[^,]*evaluateTrade/.test(MVS_CODE.replace(/\s+/g, ' ')),
  '2. queryFn calls evaluateTrade',
);
{
  // The options object must carry `enabled:` whose value is exactly the
  // disclosure state — `enabled: expanded`. `enabled: true`, a dropped
  // `enabled`, or any other expression fails.
  const m = MVS_CODE.match(/enabled:\s*([A-Za-z0-9_.!]+)\s*,/);
  assert(
    !!m && m[1] === 'expanded',
    '3. S-1 — evaluate query gated on `enabled: expanded`',
    m ? `enabled is \`${m[1]}\`` : 'no `enabled:` key on the query',
  );
}

// ── S-2: TradeCard footer slot — optional, once, last, never on the deck ───
assert(
  /footer\?:\s*React\.ReactNode/.test(TC_CODE),
  '4. S-2 — TradeCard `footer` prop is OPTIONAL (footer?: React.ReactNode)',
);
{
  const renders = TC_CODE.match(/\{footer \?\? null\}/g) || [];
  assert(
    renders.length === 1,
    '5. S-2 — footer rendered exactly once',
    `${renders.length} render site(s)`,
  );
  // Final block: the single render site sits after the match/awaiting
  // actions ternary (the last SendInSleeperButton mount) and immediately
  // before the card's closing </View>.
  const idx = TC_CODE.indexOf('{footer ?? null}');
  const lastSend = TC_CODE.lastIndexOf('surface="awaiting"');
  assert(
    idx > -1 && lastSend > -1 && idx > lastSend,
    '6. S-2 — footer renders AFTER the actions/send rows',
  );
  assert(
    /\{footer \?\? null\}\s*<\/View>\s*\)\s*;/.test(TC_CODE),
    '7. S-2 — footer is the card\'s FINAL block (only the card\'s closing </View> follows)',
  );
  // Not gated on / leaked into the deck branch: `footer` must not appear
  // inside the disposition row, and no deck mount passes it.
  const dispositionBlock = TC_CODE.slice(
    TC_CODE.indexOf('{disposition ?'),
    TC_CODE.indexOf('#190') > -1 ? TC_CODE.indexOf('{variant === \'swipe\' && onEditInCalculator') : idx,
  );
  assert(
    !/\bfooter\b/.test(dispositionBlock),
    '8. S-2 — footer not rendered inside the deck disposition branch',
  );
}
assert(
  !/footer\s*=/.test(TRADES),
  '9. S-2 — TradesScreen (the deck) passes NO footer',
);

// ── S-3: honesty caveat on dropped assets ──────────────────────────────────
assert(
  /dropped_player_ids/.test(MVS_CODE),
  '10. S-3 — MatchValueSection reads dropped_player_ids',
);
assert(
  /couldn't be valued/.test(MVS_CODE),
  '11. S-3 — caveat copy present ("couldn\'t be valued")',
);
assert(
  /droppedCount > 0 \?/.test(MVS_CODE.replace(/\s+/g, ' ')),
  '12. S-3 — caveat is CONDITIONAL on a non-empty dropped list',
);

// ── S-4: TradeValueBar verbatim — no fork ──────────────────────────────────
assert(
  /import TradeValueBar from '\.\/TradeValueBar'/.test(MVS_CODE),
  '13. S-4 — imports the real TradeValueBar',
);
assert(
  /<TradeValueBar/.test(MVS_CODE),
  '14. S-4 — renders <TradeValueBar>',
);
assert(
  !/Dynasty value swing/.test(MVS_CODE),
  '15. S-4 — no local bar markup (comment-stripped source never authors "Dynasty value swing")',
);

// ── Wiring: both segments mount the section; match_opened on mutual only ───
{
  const mounts = (stripComments(SCREEN).match(/<MatchValueSection/g) || []).length;
  assert(mounts >= 2, '16. screen mounts MatchValueSection on BOTH segments', `${mounts} mount(s)`);
  const matchIdPasses = (stripComments(SCREEN).match(/matchId=\{/g) || []).length;
  assert(
    matchIdPasses === 1,
    '17. matchId passed on exactly one mount (mutual only — awaiting is waived)',
    `${matchIdPasses} matchId pass(es)`,
  );
}
assert(
  /openedFiredRef/.test(MVS_CODE)
    && /track\('match_opened',\s*\{ match_id: matchId \},\s*'Matches'\)/.test(
      MVS_CODE.replace(/\s+/g, ' '),
    ),
  '18. match_opened fires ref-guarded, with match_id, screen Matches',
);
assert(
  /testID="matches\.open-in-calc"/.test(MVS_CODE)
    && /testID="matches\.value-details"/.test(MVS_CODE),
  '19. testIDs matches.value-details + matches.open-in-calc present',
);

console.log(failures ? `\n${failures} FAILURE(S)` : '\nALL CHECKS PASSED (19)');
process.exit(failures ? 1 : 0);
