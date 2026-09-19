#!/usr/bin/env node
// `swipe_guard_blocked` structural test.
// Tracking plan: docs/business/analytics/2026-08-18-swipe-guard-blocked.md
// Origin: docs/reviews/2026-08-18-bug-sweep/ticket.md §B4 · D-068 · G-049
//
// WHY THIS EXISTS. On 2026-08-18 a poisoned double-fire guard trapped a user
// on one trade card: every ✕/✓/swipe hit a bare `return` in `advance()`. It
// produced ZERO telemetry, so a human report was the only detector. D-068
// re-armed the guard; this event closes the blind spot. Four properties of
// that instrumentation are invisible to a green Maestro run and each would
// ship a quiet, expensive regression:
//
//   1. THE EMITTER LIVES ON THE EARLY-RETURN PATH. An event that fires
//      anywhere else measures nothing. Both guards report, and each report
//      sits in the block that returns.
//   2. THE NAME IS REGISTERED, WITH EXACTLY THESE PROPS. The taxonomy is
//      default-deny behind a 200: an unregistered name — or a prop the
//      registry omits — is counted and dropped with a success-shaped
//      response and a plausible-looking empty dashboard (G-031).
//   3. VOLUME IS BOUNDED. A stuck user tapping in a loop must not fill the
//      500-event SDK queue and evict real funnel rows. Ladder + session cap.
//   4. IT IS NOT FUNNEL-CRITICAL. Drop-last for this event would invert the
//      priority under exactly the conditions it fires.
//
// Also pins the two things that are easy to "clean up" into silence: the
// guards themselves, and the absence of a device-`platform` prop (the
// NULL-platform incident).
//
// Run: node tests/check-swipe-guard-telemetry.js

'use strict';

const fs = require('fs');
const path = require('path');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const MOBILE = path.join(__dirname, '..');
const REPO = path.join(MOBILE, '..');
const read = (rel, base = MOBILE) => fs.readFileSync(path.join(base, rel), 'utf8');

function parse(rel) {
  const file = path.join(MOBILE, rel);
  return ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
}
function findAll(root, pred) {
  const out = [];
  (function walk(n) {
    if (pred(n)) out.push(n);
    n.forEachChild(walk);
  })(root);
  return out;
}

const EVENT = 'swipe_guard_blocked';
const screenSrc = parse('src/screens/TradesScreen.tsx');
const screenText = read('src/screens/TradesScreen.tsx');
const eventsText = read('src/api/events.ts');
const taxText = read('backend/analytics_taxonomy.py', REPO);

const fns = new Map(
  findAll(screenSrc, (n) => ts.isFunctionDeclaration(n) && n.name).map((n) => [
    n.name.getText(),
    n,
  ]),
);

// ═══════════════════════════════════════════════════════════════════════
// 1. Both guards still exist, and both report from their early return
// ═══════════════════════════════════════════════════════════════════════

const advanceFn = fns.get('advance');
assert(!!advanceFn, 'TradesScreen: advance() exists');
const advanceText = advanceFn ? advanceFn.getText() : '';

assert(
  /reasonBankedIdRef\.current === dispatchRawId/.test(advanceText),
  'TradesScreen: the decline-reasons guard still exists in advance()',
  'the reasonBankedIdRef early-return is one of the two paths this event measures',
);
assert(
  /lastDispositionedRef\.current === dispatchRawId/.test(advanceText),
  'TradesScreen: the swipe-undo guard still exists in advance()',
  'the lastDispositionedRef early-return is the B4 mechanism itself',
);

const reports = advanceFn
  ? findAll(
      advanceFn,
      (n) => ts.isCallExpression(n) && n.expression.getText() === 'reportGuardBlocked',
    )
  : [];
assert(
  reports.length === 2,
  'TradesScreen: advance() reports from exactly two guards',
  `expected 2 reportGuardBlocked() calls, found ${reports.length}`,
);

const guardsSeen = new Set();
for (const call of reports) {
  const guardArg = (call.arguments[0]?.getText() ?? '').replace(/'/g, '');
  guardsSeen.add(guardArg);
  assert(
    (call.arguments[1]?.getText() ?? '') === 'decision',
    `TradesScreen: ${guardArg} report carries the attempted decision`,
    'a like on a card already passed is the escape attempt — that is the trap signature',
  );
  assert(
    (call.arguments[2]?.getText() ?? '') === 'dispatchRawId',
    `TradesScreen: ${guardArg} report carries the RAW deck id`,
    'the derived id of an edited card would not match the poisoned ref',
  );
  // The load-bearing structural claim: the report sits in the block that
  // early-returns, not somewhere else in advance().
  let block = call.parent;
  while (block && !ts.isBlock(block)) block = block.parent;
  const stmts = block ? block.statements : [];
  const last = stmts[stmts.length - 1];
  assert(
    !!last && ts.isReturnStatement(last) && !last.expression,
    `TradesScreen: the ${guardArg} report is on the early-return path`,
    'an event fired anywhere but the swallowed disposition measures nothing',
  );
}
assert(
  guardsSeen.has('swipe_undo') && guardsSeen.has('decline_reasons'),
  'TradesScreen: both guards are distinguished by name',
  `found [${[...guardsSeen].sort().join(', ')}] — one event, two guards, told apart by the prop`,
);

// ═══════════════════════════════════════════════════════════════════════
// 2. The emitter uses the house track() path, with the specced props
// ═══════════════════════════════════════════════════════════════════════

const reporterFn = fns.get('reportGuardBlocked');
assert(!!reporterFn, 'TradesScreen: reportGuardBlocked() exists');

const trackCalls = findAll(
  reporterFn ?? screenSrc,
  (n) =>
    ts.isCallExpression(n) &&
    n.expression.getText() === 'track' &&
    (n.arguments[0]?.getText() ?? '').includes(EVENT),
);
assert(
  trackCalls.length === 1,
  `TradesScreen: exactly one ${EVENT} emitter`,
  `found ${trackCalls.length} — a second call site would double-count the ladder`,
);

let emittedProps = new Set();
if (trackCalls[0]) {
  const call = trackCalls[0];
  assert(
    (call.arguments[2]?.getText() ?? '') === "'Trades'",
    'TradesScreen: the emitter names the Trades screen',
    'the house track(event, props, screen) shape — not a new mechanism',
  );
  const propsArg = call.arguments[1];
  assert(
    !!propsArg && ts.isObjectLiteralExpression(propsArg),
    'TradesScreen: the emitter passes an object literal of props',
  );
  if (propsArg && ts.isObjectLiteralExpression(propsArg)) {
    emittedProps = new Set(
      propsArg.properties.map((p) => (p.name ? p.name.getText() : '')).filter(Boolean),
    );
  }
}

const eventsImport = findAll(
  screenSrc,
  (n) => ts.isImportDeclaration(n) && /\/api\/events'$/.test(n.moduleSpecifier.getText()),
)[0];
assert(
  !!eventsImport &&
    (eventsImport.importClause?.namedBindings?.elements ?? []).some(
      (e) => e.name.getText() === 'track',
    ),
  'TradesScreen: track() is the named import from the shared SDK (api/events)',
  'no bespoke emission mechanism, and no local shadow of the name',
);

// ═══════════════════════════════════════════════════════════════════════
// 3. Taxonomy registration — name + prop row, exactly (default-deny)
// ═══════════════════════════════════════════════════════════════════════

const clientStart = taxText.indexOf('ALLOWED_CLIENT_EVENTS: frozenset[str] = frozenset({');
const serverStart = taxText.indexOf('SERVER_FIRED_EVENTS: frozenset[str] = frozenset({');
const funnelStart = taxText.indexOf('FUNNEL_CRITICAL: frozenset[str] = frozenset({');
const propsStart = taxText.indexOf('CLIENT_EVENT_PROPS: dict[str, frozenset[str]] = {');
assert(
  clientStart >= 0 && serverStart > clientStart && funnelStart > serverStart && propsStart > funnelStart,
  'taxonomy: the four registries are all present and in the expected order',
);
const clientBlock = taxText.slice(clientStart, serverStart);
const serverBlock = taxText.slice(serverStart, funnelStart);
const funnelBlock = taxText.slice(funnelStart, taxText.indexOf('})', funnelStart));

assert(
  new RegExp(`^\\s*"${EVENT}",`, 'm').test(clientBlock),
  `taxonomy: ${EVENT} is in ALLOWED_CLIENT_EVENTS`,
  'the registry is default-deny BEHIND A 200 — an unregistered name is silent data loss',
);
assert(
  !serverBlock.includes(`"${EVENT}"`),
  `taxonomy: ${EVENT} is not server-fired`,
  'the import-time disjointness assert would crash the app at boot',
);

const propRow = taxText
  .slice(propsStart)
  .match(new RegExp(`"${EVENT}":\\s*frozenset\\(\\{([\\s\\S]*?)\\}\\)`));
assert(
  !!propRow,
  `taxonomy: ${EVENT} has a CLIENT_EVENT_PROPS row`,
  'an allowlisted event with no prop row raises at IMPORT — the app would not boot',
);
const registeredProps = new Set(
  propRow ? (propRow[1].match(/"([a-z_]+)"/g) || []).map((s) => s.replace(/"/g, '')) : [],
);

const missing = [...emittedProps].filter((p) => !registeredProps.has(p));
assert(
  missing.length === 0,
  'taxonomy: every prop the client sends is registered',
  `unregistered (silently STRIPPED at ingest): ${missing.join(', ')}`,
);
const unused = [...registeredProps].filter((p) => !emittedProps.has(p));
assert(
  unused.length === 0,
  'taxonomy: the prop row registers nothing the client does not send',
  `registered but never emitted: ${unused.join(', ')}`,
);
for (const required of ['guard', 'decision', 'trade_id', 'blocked_n']) {
  assert(
    emittedProps.has(required),
    `props: ${required} is sent`,
    'trade id + which guard fired are the minimum a diagnosis needs',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 4. No PII, and no device-`platform` prop (the NULL-platform incident)
// ═══════════════════════════════════════════════════════════════════════

const BANNED = ['platform', 'player_id', 'player_name', 'user_id', 'username',
                'league_id', 'text', 'free_text', 'partner_id', 'email'];
for (const prop of BANNED) {
  assert(
    !emittedProps.has(prop) && !registeredProps.has(prop),
    `props: no \`${prop}\` prop`,
    prop === 'platform'
      ? 'device platform is a user_events COLUMN derived server-side, never a prop'
      : 'this event identifies a card and a guard — never a person',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 5. Volume is bounded — ladder + session cap, both consulted
// ═══════════════════════════════════════════════════════════════════════

const ladder = screenText.match(/const GUARD_BLOCK_LADDER = \[([\d, ]+)\];/);
assert(!!ladder, 'TradesScreen: GUARD_BLOCK_LADDER is declared');
if (ladder) {
  const rungs = ladder[1].split(',').map((n) => Number(n.trim()));
  assert(
    rungs[0] === 1,
    'volume: the ladder starts at 1',
    'the FIRST block must be visible — a benign double-fire is the baseline to compare against',
  );
  assert(
    rungs.length >= 3 && rungs.includes(3),
    'volume: the ladder reaches 3',
    'a tap/gesture race cannot produce three consecutive blocks — 3 is where "trapped" becomes provable',
  );
  assert(
    rungs.every((n, i) => i === 0 || n > rungs[i - 1]),
    'volume: the ladder is strictly increasing',
    `found [${rungs.join(', ')}]`,
  );
  assert(
    rungs.length <= 8,
    'volume: the ladder is bounded per card',
    `${rungs.length} rungs — a trapped card must not be able to flood the SDK queue`,
  );
}
const cap = screenText.match(/const GUARD_BLOCK_SESSION_CAP = (\d+);/);
assert(!!cap, 'TradesScreen: GUARD_BLOCK_SESSION_CAP is declared');
assert(
  cap && Number(cap[1]) > 0 && Number(cap[1]) <= 100,
  'volume: the session cap is a real, small bound',
  'unbounded emission across a session is the failure mode the cap exists to prevent',
);

const reporterText = reporterFn ? reporterFn.getText() : '';
assert(
  reporterText.includes('GUARD_BLOCK_LADDER') && reporterText.includes('GUARD_BLOCK_SESSION_CAP'),
  'volume: the emitter consults BOTH the ladder and the session cap',
  'a declared-but-unused constant is a bound that does not exist',
);
assert(
  /if \(st\.key !== key\)/.test(reporterText) || /st\.key !== key/.test(reporterText),
  'volume: the counter resets on a new (card, guard) pair',
  'blocked_n must count CONSECUTIVE blocks on one predicament, not a session tally',
);
assert(
  /guardBlockRef\.current\.key = null;/.test(advanceText),
  'TradesScreen: a disposition that gets past both guards ends the streak',
  'otherwise blocked_n accumulates across unrelated attempts and stops meaning "trapped"',
);

// ═══════════════════════════════════════════════════════════════════════
// 6. NOT funnel-critical — in either registry
// ═══════════════════════════════════════════════════════════════════════

assert(
  !funnelBlock.includes(EVENT),
  `taxonomy: ${EVENT} is not in FUNNEL_CRITICAL`,
  'drop-LAST for this event would let a trapped user evict signin_* under queue pressure',
);
const sdkMirror = eventsText.match(/const FUNNEL_CRITICAL = new Set<string>\(\[([\s\S]*?)\]\)/);
assert(!!sdkMirror, 'events.ts: the FUNNEL_CRITICAL mirror is still present');
assert(
  sdkMirror && !sdkMirror[1].includes(EVENT),
  `events.ts: ${EVENT} is not in the SDK mirror either`,
  'the mirror is hand-maintained; the two must agree',
);

// ═══════════════════════════════════════════════════════════════════════
// 7. The tracking-plan addendum exists (the taxonomy docstring demands it)
// ═══════════════════════════════════════════════════════════════════════

const addendum = path.join(REPO, 'docs/business/analytics/2026-08-18-swipe-guard-blocked.md');
assert(
  fs.existsSync(addendum),
  'docs: the tracking-plan addendum exists',
  'analytics_taxonomy.py: "New client event types require a tracking-plan addendum first"',
);
if (fs.existsSync(addendum)) {
  const doc = fs.readFileSync(addendum, 'utf8');
  for (const prop of emittedProps) {
    assert(
      doc.includes(`\`${prop}\``),
      `docs: the addendum specifies \`${prop}\``,
      'every prop is documented with its type and its purpose, or it is not shipped',
    );
  }
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All swipe-guard telemetry checks passed.');
