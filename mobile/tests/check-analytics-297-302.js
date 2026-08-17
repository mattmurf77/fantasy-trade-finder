#!/usr/bin/env node
/**
 * check-analytics-297-302.js — structural guard for the feedback
 * #297 / #298 / #299 / #302 instrumentation.
 *
 * Tracking plan: docs/feedback/items/297-lineup-impact-single-pin/analytics.md
 *
 * WHY THIS EXISTS AS A CLIENT-SIDE TEST
 * -------------------------------------
 * POST /api/events has TWO silent failure modes (analytics_ingest.py:379-390):
 * an unregistered event NAME is accepted-and-dropped, and an unregistered
 * PROP on a registered name is popped. Neither 4xx's, neither logs on the
 * client. `backend/tests/test_events_api.py` pins the SERVER half — that the
 * registry accepts what we say we send. This file pins the CLIENT half —
 * that what we actually send is what the registry accepts. Together they
 * close the loop; either alone leaves a silent hole, which is exactly how
 * `trade_card_shared`'s `landing` prop has been discarded in production.
 *
 * The §4 cross-check is the load-bearing one: it reads the prop keys out of
 * the real track() call sites AND out of backend/analytics_taxonomy.py, and
 * fails on any asymmetry in either direction.
 *
 * Static/AST-free (regex + a brace matcher) by house convention — see the
 * sibling mobile/tests/check-*.js. No simulator, no backend.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const LEAGUE = path.join(ROOT, 'mobile/src/screens/LeagueSummaryScreen.tsx');
const CALC = path.join(ROOT, 'mobile/src/components/InLeagueCalculator.tsx');
const TRADES = path.join(ROOT, 'mobile/src/screens/TradesScreen.tsx');
const TAXONOMY = path.join(ROOT, 'backend/analytics_taxonomy.py');

const leagueText = fs.readFileSync(LEAGUE, 'utf8');
const calcText = fs.readFileSync(CALC, 'utf8');
const tradesText = fs.readFileSync(TRADES, 'utf8');
const taxText = fs.readFileSync(TAXONOMY, 'utf8');

let failures = 0;
function assert(cond, label, why) {
  if (cond) {
    console.log(`PASS  ${label}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${label}${why ? `: ${why}` : ''}`);
  }
}

// ── helpers ───────────────────────────────────────────────────────────────

/** All top-level key names of the object literal starting at `text[open]`
 *  (which must be a `{`). Nested objects are skipped, not descended. */
function objectKeys(text, open) {
  const keys = [];
  let depth = 0;
  let i = open;
  let topLevelStart = -1;
  for (; i < text.length; i += 1) {
    const c = text[i];
    if (c === '{' || c === '[' || c === '(') {
      depth += 1;
      if (depth === 1) topLevelStart = i + 1;
      continue;
    }
    if (c === '}' || c === ']' || c === ')') {
      depth -= 1;
      if (depth === 0) break;
      continue;
    }
  }
  const body = text.slice(topLevelStart, i);
  // Strip nested braces/brackets/parens so their keys don't leak up.
  let flat = '';
  let d = 0;
  for (const c of body) {
    if (c === '{' || c === '[' || c === '(') d += 1;
    else if (c === '}' || c === ']' || c === ')') d -= 1;
    else if (d === 0) flat += c;
    if (d === 0 && (c === '}' || c === ']' || c === ')')) flat += ',';
  }
  // Drop line comments, then read `key:` and bare shorthand `key`.
  flat = flat.replace(/\/\/[^\n]*/g, '');
  for (const part of flat.split(',')) {
    const m = part.match(/^\s*([A-Za-z_$][\w$]*)\s*(:|$)/);
    if (m) keys.push(m[1]);
  }
  return keys;
}

/** Prop keys of every `track('<name>', { … })` call in `text`.
 *  Returns an array (one entry per call site) of key arrays. `null` marks a
 *  call site whose props are not an inline object literal. */
function trackPropKeys(text, eventName) {
  const out = [];
  const re = new RegExp(`track\\(\\s*'${eventName}'\\s*,`, 'g');
  let m;
  while ((m = re.exec(text)) !== null) {
    const rest = text.slice(m.index + m[0].length);
    const brace = rest.search(/\S/);
    if (rest[brace] !== '{') { out.push(null); continue; }
    out.push(objectKeys(rest, brace));
  }
  return out;
}

/** The prop frozenset registered for `eventName` in analytics_taxonomy.py. */
function taxonomyProps(eventName) {
  const re = new RegExp(
    `"${eventName}"\\s*:\\s*frozenset\\(\\{([^}]*)\\}\\)`,
  );
  const m = taxText.match(re);
  if (!m) return null;
  return m[1].match(/"([^"]+)"/g)?.map((q) => q.slice(1, -1)) ?? [];
}

const countOf = (text, needle) => text.split(needle).length - 1;
const countRe = (text, re) => (text.match(re) || []).length;

/** Source with `//` line comments and block comments removed. Required for
 *  any "this construct appears nowhere" assertion — the comments in these
 *  files deliberately NAME the constructs they forbid, so scanning raw text
 *  makes such an assertion permanently red. */
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}
const leagueCode = stripComments(leagueText);
const calcCode = stripComments(calcText);
const tradesCode = stripComments(tradesText);

// ══ 1. #299/#302 — the drill-in EXIT, and NO duplicate enter event ════════
//
// The premise the previous round got wrong: `league_team_opened` shipped in
// the P0-7 remediation batch and already covers the ENTER half. Minting a
// second "focused" name would be two sources of truth for one interaction —
// the exact bug #208/#248/#293 are a catalog of on this screen.

assert(
  !/league_team_focused|league_team_unfocused/.test(leagueText) &&
    !/league_team_focused|league_team_unfocused/.test(taxText),
  '#299/#302 no parallel focused/unfocused enter event was minted',
  'league_team_opened already covers the drill-in enter — a second name is two sources of truth',
);
assert(
  countRe(leagueCode, /track\(\s*'league_team_opened'/g) === 1,
  '#299/#302 the ENTER half is still exactly one league_team_opened emitter',
);
assert(
  countRe(leagueCode, /track\(\s*'league_team_closed'/g) === 1,
  '#299/#302 the EXIT half is exactly one league_team_closed emitter',
  'a second emitter would double-count exits and break dwell',
);

// The emitter must live inside `emitTeamClosed`, whose only source of dwell
// is the ref — never state, because two of the five controls are registered
// in effects whose deps exclude selectedId.
assert(
  /const emitTeamClosed = React\.useCallback\(\s*\n\s*\(via: CloseVia\) => \{\s*\n\s*const f = focusRef\.current;\s*\n\s*focusRef\.current = null;\s*\n\s*if \(!f\) return;\s*\n\s*track\(\s*\n?\s*'league_team_closed',/
    .test(leagueText),
  '#302 league_team_closed is emitted from the ref-backed emitTeamClosed helper',
  'a state closure would report the focus live when the handler was REGISTERED, not when it fired',
);
assert(
  /dwell_ms: Date\.now\(\) - f\.at/.test(leagueText) &&
    /rank: f\.rank/.test(leagueText),
  '#302 dwell_ms and rank are read from the focus ref captured at OPEN',
  'reading rank at close time would break the join to league_team_opened.rank after a basis change',
);

// Every exit control routes through the choke point. If any control went
// back to a bare setSelectedId(null), its exit would vanish from the data
// while the UI kept working — a silent hole, not a visible bug.
for (const [via, label] of [
  ['header_back', 'the #302 fixed stack-header control'],
  ['in_card_link', 'the #243 in-card link (root-stack push)'],
  ['tab_retap', 'the active-tab re-tap'],
]) {
  assert(
    countOf(leagueCode, `closeTeam('${via}')`) === 1,
    `#302 exit control '${via}' routes through closeTeam exactly once`,
    `${label} must not clear focus directly`,
  );
}
// `hardware_back` is the fifth `via` value and has NO emitter: #302's Android
// BackHandler was built and withdrawn before ship (operator, 2026-08-11 —
// unverifiable on an iOS-only release). The name stays registered on purpose,
// so re-enabling the handler is one effect rather than a taxonomy migration
// (the `sleeper_send_*` precedent, D-031). Pin BOTH halves: the value is still
// allowed by the taxonomy, and nothing in the client emits it yet — otherwise
// the reservation silently rots into either a dropped prop value or an
// unnoticed live emitter.
assert(
  countOf(leagueCode, "closeTeam('hardware_back')") === 0,
  "#302 'hardware_back' has no emitter while the Android handler is withdrawn",
  'an emitter here means the withdrawn BackHandler came back — restore it and this assertion together',
);
assert(
  /hardware_back/.test(taxText),
  "#302 'hardware_back' stays RESERVED in the server-side via enum",
  'dropping it means a future Android release ships a value the ingest strips silently',
);

assert(
  countOf(leagueCode, "emitTeamClosed('refocus')") === 1 &&
    /const same = focusRef\.current\?\.id === id;\s*\n\s*if \(focusRef\.current && !same\) emitTeamClosed\('refocus'\);/
      .test(leagueText),
  "#302 jumping team-to-team terminates the first focus as via='refocus'",
  'without this the first interval silently absorbs the next team\'s dwell',
);
assert(
  /at: focusRef\.current\?\.at \?\? Date\.now\(\)/.test(leagueText),
  '#302 re-tapping the SAME team keeps the original open timestamp',
  'restarting `at` on a no-op re-tap would under-report dwell',
);

// Exactly ONE bare `setSelectedId(null)` may exist, and it must be the one
// inside closeTeam. This is what makes "five controls, five vias" airtight.
assert(
  countOf(leagueCode, 'setSelectedId(null)') === 1 &&
    /const closeTeam = React\.useCallback\(\s*\n\s*\(via: CloseVia\) => \{\s*\n\s*emitTeamClosed\(via\);\s*\n\s*setSelectedId\(null\);/
      .test(leagueText),
  '#302 the ONLY setSelectedId(null) in the file is inside closeTeam',
  'any other clear is an exit path that fires no event',
);

// ══ 2. #297 — the honest-empty lineup row impression ══════════════════════

assert(
  countRe(calcCode, /track\(\s*'lineup_impact_unavailable'/g) === 1,
  '#297 exactly one lineup_impact_unavailable emitter',
);
assert(
  /const lineupUnavailable = both && !ev\.starter_impact;/.test(calcText),
  '#297 the emitter is gated on the SAME condition that renders the row',
  'both sides populated AND starter_impact absent — anything else counts impressions that never happened',
);
assert(
  /\}, \[lineupUnavailable, ev, leagueId\]\);/.test(calcText),
  '#297 the effect is keyed on `ev`, so it is one event per EVALUATION',
  'an empty dep array would fire once per mount and under-count; omitting `ev` would miss re-evaluations',
);
// The false-pass trap this project already hit once: a platform check that
// passes on a sabotage leaving the lookup line in place but swapping the
// RETURNED value. So pin the expression that is actually bound to the prop.
assert(
  /const platform =\s*\n\s*useSession\.getState\(\)\.leagues\.find\(\(lg\) => lg\.league_id === leagueId\)\s*\n\s*\?\.platform \?\? 'unknown';/
    .test(calcText),
  '#297 `platform` is bound to the session league-cache lookup, not merely near one',
  'the previous round had a platform test that survived swapping the returned value',
);
assert(
  !/isdigit|\/\^\\d\+\$\/|\.test\(leagueId\)|Number\(leagueId\)/.test(calcCode),
  '#297 platform is NOT inferred from the league id\'s shape',
  'ESPN and MFL league ids can be numeric (a live MFL id in this project is 990062846) — an isdigit read labels them sleeper',
);

// ══ 3. #298 — a property on events that already fire, not a new name ══════

const findTapped = trackPropKeys(tradesText, 'find_trades_tapped');
assert(
  findTapped.length === 3,
  '#298 all find_trades_tapped call sites are accounted for',
  `expected 3 (handleFindTrades + the legacy !consolidateOn arm + the #330 auto-run emit in the choke-point effect), saw ${findTapped.length}`,
);
assert(
  countOf(
    tradesCode,
    "track('find_trades_tapped', { source: 'league_offer', mode: deckMode }, 'Trades')",
  ) === 1,
  "#330 the third emitter is the auto-run's source:'league_offer' dispatch, reading the same deckMode",
  'a third emitter with its own mode derivation is how the arms come to disagree; details pinned by check-offer-prefill-330.js S-3',
);
assert(
  /source \? \{ source, mode: deckMode \} : \{ mode: deckMode \}/.test(tradesText),
  '#298 handleFindTrades sends `mode` with or without a `source`',
);
assert(
  countOf(tradesCode, "track('find_trades_tapped', { mode: deckMode }, 'Trades')") === 1,
  '#298 the legacy-layout CTA sends `mode` too',
  'an emitter without mode makes the single-pin count silently incomplete',
);
assert(
  countOf(
    tradesCode,
    "const deckMode: 'single_pin' | 'deck' = singlePinFeatured ? 'single_pin' : 'deck';",
  ) === 1,
  '#298 `mode` has exactly ONE derivation feeding every emitter',
  'two derivations is how the two CTA arms come to disagree',
);
assert(
  /trade_id: topTradeId,[\s\S]{0,600}?mode: deckMode,\s*\n\s*\};[\s\S]{0,400}?track\('trade_card_viewed', props, 'Trades'\);/
    .test(tradesText),
  '#298 trade_card_viewed carries `mode` in the props it actually sends',
);
assert(
  !/track\('(single_pin|trade_single_pin)[a-z_]*'/.test(tradesCode),
  '#298 introduced NO new event name',
  'a new name has no pre-fix baseline and cannot answer "does the existing event still fire here"',
);

// ══ 4. CLIENT ↔ TAXONOMY cross-check (the load-bearing one) ═══════════════
//
// Every prop key a client emitter sends must be registered, or ingest pops
// it silently. And every registered prop for the two NEW names must actually
// be sent, or the registry documents a field nobody produces.

const CROSS = [
  ['league_team_closed', leagueText, true],
  ['lineup_impact_unavailable', calcText, true],
  ['find_trades_tapped', tradesText, false],
];
for (const [name, text, exact] of CROSS) {
  const registered = taxonomyProps(name);
  assert(
    registered !== null,
    `taxonomy registers a prop set for ${name}`,
    'CLIENT_EVENT_PROPS entry missing — every prop would be stripped',
  );
  if (!registered) continue;
  const sent = new Set(trackPropKeys(text, name).flat().filter(Boolean));
  const unregistered = [...sent].filter((k) => !registered.includes(k));
  assert(
    unregistered.length === 0,
    `${name}: every prop the client sends is registered`,
    `unregistered (silently stripped at ingest): ${unregistered.join(', ')}`,
  );
  if (exact) {
    const unsent = registered.filter((k) => !sent.has(k));
    assert(
      unsent.length === 0,
      `${name}: every registered prop is actually sent`,
      `registered but never emitted: ${unsent.join(', ')}`,
    );
  }
}
// trade_card_viewed builds its props in a variable, so the generic scan
// cannot read them — pin `mode`'s registration directly.
assert(
  (taxonomyProps('trade_card_viewed') || []).includes('mode'),
  'trade_card_viewed: `mode` is registered',
  'unregistered — the prop would be popped and #298 would be unmeasurable',
);

// ══ 5. DAU guard mirrored on the client side of the contract ══════════════
//
// INTENT_EVENTS is a DENY-list, so taxonomy growth is intent-by-default.
// backend/tests/test_events_api.py asserts the Python truth; this asserts the
// same two names are visibly guarded in the file a mobile reviewer reads.
const queriesText = fs.readFileSync(
  path.join(ROOT, 'backend/analytics_queries.py'), 'utf8');
const nonIntentBlock = queriesText.match(
  /NON_INTENT_EVENTS = frozenset\(\{([\s\S]*?)\n\}\)/,
);
assert(
  !!nonIntentBlock &&
    /"lineup_impact_unavailable"/.test(nonIntentBlock[1]) &&
    /"league_team_closed"/.test(nonIntentBlock[1]),
  'both new names are inside NON_INTENT_EVENTS',
  'registering a passive/terminator event without this step-changes DAU/WAU with no error and no log',
);
assert(
  !!nonIntentBlock && !/"league_team_opened"/.test(nonIntentBlock[1]),
  'league_team_opened STAYS intent',
  'the enter half is a real value moment and already counts the user once',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All #297/#298/#299/#302 analytics checks passed.');
