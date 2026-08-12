#!/usr/bin/env node
/**
 * check-analytics-300.js — structural guard for the feedback #300
 * instrumentation (League rankings → positional trade candidates).
 *
 * Tracking plan:
 * docs/feedback/items/300-league-rankings-trade-candidates/analytics.md
 *
 * WHY THIS EXISTS
 * ---------------
 * #300 shipped LIT with the pre-ship simulator gate and the Maestro run
 * BOTH waived by the operator, so these two events are the only evidence
 * that will ever exist that the feature works in the wild. Every failure
 * mode in the way is silent:
 *
 *   · an unregistered event NAME is counted-and-DROPPED behind a 200
 *     (analytics_ingest.py) — the emitter looks live and records nothing;
 *   · an unregistered PROP on a registered name is POPPED, same 200 —
 *     `trade_card_shared`'s `landing` is the live in-tree example;
 *   · a name added to ALLOWED_CLIENT_EVENTS and nowhere else becomes an
 *     INTENT event by subtraction and step-changes DAU/WAU permanently;
 *   · and an exposure emit gate that drifts LOOSE from the render gate
 *     over-counts massively while still looking correct — every
 *     multi-position and every Starters/Bench view would read as an
 *     exposure. #294's rule A came and went inside three days, so this is
 *     not hypothetical.
 *
 * backend/tests/test_events_api.py pins the SERVER half (the registry
 * accepts what we say we send). This pins the CLIENT half (what we send is
 * what the registry accepts, and it fires where the feature actually
 * renders). Either alone leaves a silent hole.
 *
 * Assertions of the form "X appears nowhere" read COMMENT-STRIPPED source:
 * the comments in LeagueSummaryScreen.tsx deliberately name the constructs
 * they forbid, which is how an earlier round shipped tests that could not
 * fail.
 *
 * Run: node mobile/tests/check-analytics-300.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const LEAGUE = path.join(ROOT, 'mobile/src/screens/LeagueSummaryScreen.tsx');
const TAXONOMY = path.join(ROOT, 'backend/analytics_taxonomy.py');
const QUERIES = path.join(ROOT, 'backend/analytics_queries.py');

const leagueText = fs.readFileSync(LEAGUE, 'utf8');
const taxText = fs.readFileSync(TAXONOMY, 'utf8');
const queriesText = fs.readFileSync(QUERIES, 'utf8');

let failures = 0;
function assert(cond, label, why) {
  if (cond) {
    console.log(`PASS  ${label}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${label}${why ? `: ${why}` : ''}`);
  }
}

// ── helpers (same shapes as check-analytics-297-302.js) ───────────────────

function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}
const leagueCode = stripComments(leagueText);
const countRe = (text, re) => (text.match(re) || []).length;

/** Top-level key names of the object literal starting at `text[open]`. */
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
  let flat = '';
  let d = 0;
  for (const c of body) {
    if (c === '{' || c === '[' || c === '(') d += 1;
    else if (c === '}' || c === ']' || c === ')') d -= 1;
    else if (d === 0) flat += c;
    if (d === 0 && (c === '}' || c === ']' || c === ')')) flat += ',';
  }
  flat = flat.replace(/\/\/[^\n]*/g, '');
  for (const part of flat.split(',')) {
    const m = part.match(/^\s*([A-Za-z_$][\w$]*)\s*(:|$)/);
    if (m) keys.push(m[1]);
  }
  return keys;
}

/** The full `track('<name>', { … })` call source, per call site. */
function trackCalls(text, eventName) {
  const out = [];
  const re = new RegExp(`track\\(\\s*'${eventName}'\\s*,`, 'g');
  let m;
  while ((m = re.exec(text)) !== null) {
    const rest = text.slice(m.index + m[0].length);
    const brace = rest.search(/\S/);
    out.push({
      keys: rest[brace] === '{' ? objectKeys(rest, brace) : null,
      // Enough source to read the VALUE expressions, not just the keys.
      src: text.slice(m.index, m.index + m[0].length + 420),
    });
  }
  return out;
}

/** The prop frozenset registered for `eventName` in analytics_taxonomy.py. */
function taxonomyProps(eventName) {
  const m = taxText.match(
    new RegExp(`"${eventName}"\\s*:\\s*frozenset\\(\\{([^}]*)\\}\\)`),
  );
  if (!m) return null;
  return m[1].match(/"([^"]+)"/g)?.map((q) => q.slice(1, -1)) ?? [];
}

/** The body of a `useEffect(() => { … })` whose source contains `needle`. */
function effectContaining(text, needle) {
  const at = text.indexOf(needle);
  if (at < 0) return null;
  const start = text.lastIndexOf('useEffect(', at);
  if (start < 0) return null;
  let depth = 0;
  for (let i = start + 'useEffect'.length; i < text.length; i += 1) {
    const c = text[i];
    if (c === '(') depth += 1;
    else if (c === ')') {
      depth -= 1;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return null;
}

const EXPOSURE = 'league_pos_candidates_viewed';
const PINNED = 'league_candidate_pinned';

// ══ 1. Both names exist at all — the registration half ════════════════════
//
// The mobile build agent shipped the row action with ZERO analytics on
// purpose, recorded in status-mobile.md §3.4: firing an unregistered name
// would have been an emitter that looks live and records nothing. This is
// that gap being closed, so the first thing to pin is that BOTH halves
// landed — an emitter without a registry entry is the same silent nothing.

const allowlist = (taxText.match(
  /ALLOWED_CLIENT_EVENTS: frozenset\[str\] = frozenset\(\{([\s\S]*?)\n\}\)/,
) || [])[1];
assert(!!allowlist, 'ALLOWED_CLIENT_EVENTS block is findable');
for (const name of [EXPOSURE, PINNED]) {
  assert(
    !!allowlist && new RegExp(`"${name}"`).test(allowlist),
    `#300 '${name}' is in ALLOWED_CLIENT_EVENTS`,
    'unregistered names are counted and DROPPED behind a 200 — never a 4xx, never a client log',
  );
  assert(
    taxonomyProps(name) !== null,
    `#300 '${name}' has a CLIENT_EVENT_PROPS entry`,
    'a missing entry strips EVERY prop of the event (import-time guard catches absence, not emptiness)',
  );
  assert(
    countRe(leagueCode, new RegExp(`track\\(\\s*'${name}'`, 'g')) === 1,
    `#300 '${name}' has exactly one emitter in LeagueSummaryScreen`,
    'two emitters for one moment is the #208/#248/#293 two-sources-of-truth bug',
  );
}

// ══ 2. CLIENT ↔ TAXONOMY prop cross-check, BOTH directions ════════════════
//
// The load-bearing one. Asserting the NAME is not enough: a registered name
// whose props are unregistered lands hollowed out, and a registered prop
// nobody sends documents a field that will read as all-NULL forever.

for (const name of [EXPOSURE, PINNED]) {
  const registered = taxonomyProps(name) || [];
  const calls = trackCalls(leagueCode, name);
  assert(
    calls.length === 1 && Array.isArray(calls[0].keys),
    `#300 ${name}: props are an inline object literal the cross-check can read`,
    'a props variable would make the check below vacuous',
  );
  const sent = new Set((calls[0] && calls[0].keys) || []);
  const unregistered = [...sent].filter((k) => !registered.includes(k));
  assert(
    sent.size > 0 && unregistered.length === 0,
    `#300 ${name}: every prop the client sends is registered`,
    `silently stripped at ingest: ${unregistered.join(', ')}`,
  );
  const unsent = registered.filter((k) => !sent.has(k));
  assert(
    unsent.length === 0,
    `#300 ${name}: every registered prop is actually sent`,
    `registered but never emitted: ${unsent.join(', ')}`,
  );
}

// The exact prop sets, spelled out — so a rename on either side is caught
// even if the two sides are renamed to agree with each other.
assert(
  JSON.stringify((taxonomyProps(EXPOSURE) || []).slice().sort()) ===
    JSON.stringify(['divider', 'position']),
  `#300 ${EXPOSURE} registers exactly {position, divider}`,
);
assert(
  JSON.stringify((taxonomyProps(PINNED) || []).slice().sort()) ===
    JSON.stringify(['position', 'rank', 'side', 'verb']),
  `#300 ${PINNED} registers exactly {verb, position, rank, side}`,
);

// ══ 3. THE OVER-COUNT TRAP — the exposure gate is `candidatePos` itself ═══
//
// The divider renders only when FOUR clauses hold together: the flag is on,
// the subset is 'all', PICKS is absent, and exactly one core position is
// selected. `candidatePos` is the single memo that computes that conjunction
// and the render gate reads it. A second copy in the emitter would drift the
// moment one clause moves — and a copy that drifted LOOSE would count every
// multi-position and every Starters/Bench view as an exposure.
//
// So: the emitter's effect must READ `candidatePos`, and must NOT re-derive
// any of the four clauses itself.

const exposureEffect = effectContaining(leagueCode, `track('${EXPOSURE}'`);
assert(!!exposureEffect, `#300 ${EXPOSURE} fires from a useEffect`);
assert(
  !!exposureEffect && /if\s*\(\s*!candidatePos\s*\)/.test(exposureEffect),
  '#300 the exposure emitter is gated on `candidatePos` itself',
  'a re-derived gate drifts from the render gate and over-counts',
);
for (const [re, clause] of [
  [/posFilter\s*\.\s*has\s*\(\s*'PICKS'/, 'the PICKS clause'],
  [/subset\s*!==\s*'all'/, "the subset==='all' clause"],
  [/CORE_POSITIONS\s*\.\s*filter/, 'the exactly-one-core-position clause'],
  [/posCandidatesOn/, 'the flag clause'],
]) {
  assert(
    !!exposureEffect && !re.test(exposureEffect),
    `#300 the exposure emitter does not re-derive ${clause}`,
    'it must read candidatePos, not recompute the render gate beside it',
  );
}
// The three `divider` values come off the SAME memos the render reads.
assert(
  !!exposureEffect &&
    /medianAtPos/.test(exposureEffect) &&
    /cutAfter/.test(exposureEffect),
  '#300 the `divider` outcome is read off medianAtPos + cutAfter',
  'any other source is a second opinion about what the user saw',
);
assert(
  !!exposureEffect &&
    ['shown', 'no_median', 'no_split'].every((v) =>
      new RegExp(`'${v}'`).test(exposureEffect)),
  '#300 `divider` carries all three outcomes (shown | no_median | no_split)',
  'a shown-only event cannot tell "nobody found it" from "the payload lost `medians`"',
);
// …and each outcome is bound to the RIGHT condition. All three strings being
// present says nothing about which is which, and a transposed pair reads as
// a broken rollout when the league is merely flat (or the reverse).
assert(
  !!exposureEffect && /!medianAtPos\s*\?\s*'no_median'/.test(exposureEffect),
  '#300 `no_median` is the missing-payload case, not the flat-league one',
  'transposed, an incomplete rollout is invisible and a flat league looks like one',
);
assert(
  !!exposureEffect && /cutAfter\s*==\s*null\s*\?\s*'no_split'/.test(exposureEffect),
  '#300 `no_split` is the line-marks-no-boundary case',
);
// Deduped in a ref, and settled before it speaks.
assert(
  !!exposureEffect &&
    /if\s*\(\s*candidateViewRef\.current\s*===\s*candidatePos\s*\)\s*return/
      .test(exposureEffect),
  '#300 the exposure early-returns on an already-emitted position',
  'without the guard the effect re-fires on every dependency change and over-counts',
);
assert(
  !!exposureEffect && /candidateViewRef\.current\s*=\s*candidatePos/.test(exposureEffect),
  '#300 the exposure records the position it emitted for',
);
assert(
  !!exposureEffect && /candidateViewRef\.current\s*=\s*null/.test(exposureEffect),
  '#300 leaving the candidate view RESETS the dedup ref',
  'a sticky ref makes a genuine re-entry invisible',
);
assert(
  !!exposureEffect && /query\.isFetched/.test(exposureEffect),
  '#300 the exposure waits for the first fetch to resolve',
  'emitting mid-flight reports `no_median` for a request that has not answered yet',
);
assert(
  !!exposureEffect && /\[[^\]]*candidatePos[^\]]*\]\s*\)\s*;?\s*$/.test(
    exposureEffect.trim()),
  '#300 the exposure effect lists candidatePos in its dep array',
  'a stale closure would emit the previous position',
);

// ══ 4. The conversion moment fires from the single row-action choke point ═
//
// `handleRowAction` is the only thing wired to the drill-in rows' onPress.
// If the emitter ever moves out of it — or a second onPress path appears —
// the feature's only conversion number goes quietly wrong.

const handlerAt = leagueCode.indexOf('const handleRowAction');
assert(handlerAt >= 0, '#300 handleRowAction is findable');
const pinAt = leagueCode.indexOf(`track('${PINNED}'`);
const navAt = leagueCode.indexOf("navigation.navigate('Trades'", handlerAt);
assert(
  handlerAt >= 0 && pinAt > handlerAt && navAt > pinAt,
  '#300 the pin event fires inside handleRowAction, before the navigate',
  'outside the handler it is a different moment; after the navigate it can be lost to the transition',
);
assert(
  countRe(leagueCode, /handleRowAction\(/g) === 1 &&
    countRe(leagueCode, /const handleRowAction/g) === 1,
  '#300 handleRowAction has exactly one definition and one invocation',
  'a second invocation is a conversion path that is easy to leave un-instrumented',
);

// `side` must come from `candidateDir` — the same memo that decides which
// roster the drill-in shows. Re-deriving it from selectedIdx/cutAfter beside
// the emitter is how the event and the UI end up disagreeing about which
// side of the line the user was on.
const pinCall = trackCalls(leagueCode, PINNED)[0];
assert(
  !!pinCall && /side:\s*candidateDir\s*===\s*'target'/.test(pinCall.src),
  '#300 `side` is derived from candidateDir, not re-derived from the index',
  'a second derivation can disagree with the roster the user was actually shown',
);
assert(
  !!pinCall && !/selectedIdx\s*<\s*cutAfter/.test(pinCall.src),
  '#300 the pin emitter does not recompute the side from selectedIdx < cutAfter',
);
assert(
  !!pinCall && /rank:\s*selectedIdx\s*\+\s*1/.test(pinCall.src),
  '#300 `rank` is the live selectedIdx+1, the same value the drill-in prints',
  'a rank from a different snapshot than `side` describes two different lists',
);
assert(
  !!pinCall && /position:\s*candidatePos/.test(pinCall.src),
  '#300 `position` is candidatePos, the filtered core position',
);
assert(
  !!pinCall && /verb,/.test(pinCall.src),
  '#300 `verb` is the verb the tapped row carried',
);
// The callback closes over four values; a missing dep is a stale event.
const handlerTail = leagueCode.slice(handlerAt, handlerAt + 2200);
const deps = (handlerTail.match(/\[navigation[^\]]*\]/) || [''])[0];
for (const d of ['candidatePos', 'candidateDir', 'selectedIdx']) {
  assert(
    deps.includes(d),
    `#300 handleRowAction lists ${d} in its dep array`,
    'a stale closure reports the previously focused team',
  );
}

// ══ 5. The DAU guard — decided per event, in the same change ══════════════
//
// INTENT_EVENTS = (SERVER_FIRED | ALLOWED_CLIENT) - NON_INTENT_EVENTS, so
// taxonomy growth is intent-BY-DEFAULT and a passive event registered
// without the guard step-changes DAU/WAU with no error and no log. The
// Python truth is asserted in backend/tests/test_events_api.py; this asserts
// the same split is visible in the file a mobile reviewer opens.

const nonIntent = (queriesText.match(
  /NON_INTENT_EVENTS = frozenset\(\{([\s\S]*?)\n\}\)/,
) || [])[1];
assert(!!nonIntent, 'NON_INTENT_EVENTS block is findable');
assert(
  !!nonIntent && new RegExp(`"${EXPOSURE}"`).test(nonIntent),
  `#300 ${EXPOSURE} is NON-INTENT`,
  'a passive exposure in INTENT promotes every idle position-pill tap to a user-day',
);
assert(
  !!nonIntent && !new RegExp(`"${PINNED}"`).test(nonIntent),
  `#300 ${PINNED} STAYS intent`,
  'an asset chosen and the finder entered is a real value moment',
);

// ══ 6. What was deliberately NOT minted ═══════════════════════════════════
//
// The drill-in enter/exit already belong to league_team_opened /
// league_team_closed. #300 adds an exposure and an action and must not
// re-mint either half, and must not mint a name for the Buyer/Seller band
// labels — which drive no behaviour by operator ruling and are a pure
// function of `rank` and league_view.team_count.

for (const minted of ['league_candidate_opened', 'league_divider_shown',
  'league_band_shown', 'league_candidate_action', 'league_team_focused']) {
  assert(
    !new RegExp(minted).test(leagueText) && !new RegExp(minted).test(taxText),
    `#300 no '${minted}' name was minted`,
  );
}
// `band` is not a prop on either event — see the tracking plan's
// deliberately-not-instrumented section.
assert(
  !(taxonomyProps(PINNED) || []).includes('band'),
  '#300 no `band` prop on the pin event',
  'the band labels drive no behaviour and are recoverable from rank + league_view.team_count',
);
// #300's only change to a SHIPPED event is a new `via` VALUE, not a new key
// — so nothing on league_team_closed is at risk of being stripped.
assert(
  /filter_change/.test(leagueCode) &&
    JSON.stringify((taxonomyProps('league_team_closed') || []).slice().sort()) ===
      JSON.stringify(['dwell_ms', 'rank', 'via']),
  "#300's auto-return adds a `via` VALUE, not a prop key",
  'a new key on league_team_closed would need its own registration',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All #300 analytics checks passed.');
