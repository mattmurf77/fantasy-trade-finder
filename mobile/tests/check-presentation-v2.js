#!/usr/bin/env node
// Trade-suggestion presentation v2 (flag `trades.presentation_v2`).
// Scope block: docs/plans/trade-presentation-v2/scope.md.
// Approved lab: mockups/trade-suggestion-redesign/ (states 01/03/04/07/09).
//
// WHY THIS EXISTS. Four things here fail silently, and none of them is
// visible to a typecheck or to a screenshot of the flag-ON build:
//
//   1. FLAG-OFF BYTE-IDENTITY. The whole promise of this branch is that a
//      user without the flag sees today's Acquire tab exactly. That promise
//      lives in ONE property: the entry handlers are OPTIONAL props, and the
//      chip/button only exists when the handler is passed. A well-meaning
//      "simplify" that renders the chip unconditionally and no-ops the
//      handler compiles, typechecks, and ships a new tab to every user.
//      §1 and §2 assert the conditional shape at both call sites and inside
//      both components.
//
//   2. INSTRUMENTATION PARITY. A card dismissed on the new surface must
//      write the SAME rows as one dismissed on the deck — that data is what
//      the deck-impressions -> outcomes -> re-ranker programme runs on. A
//      hand-rolled fetch here, or a renamed event, silently forks the
//      dataset and nothing breaks until someone queries it months later.
//      §4 asserts reuse of the exact shared functions and event names.
//
//   3. THE CACHE-SLOT AGREEMENT. The server keys its job cache on
//      `fairness_threshold`. If this surface derived its own value it would
//      kick a second full generation AND serve a different card set (and so
//      different impressions) than the deck for the same user. §3 asserts
//      the shared helper is the only source.
//
//   4. THE DESIGN LAWS. "No winner needle", "counterparty gets a statement
//      only", "browse is uncapped", "no two-digit percentage" are the whole
//      point of the redesign and every one of them is a plausible, friendly
//      "improvement" for a future session to make. §5 pins them, and §6 runs
//      the real pure module to prove the derivations behave.
//
// Run: node tests/check-presentation-v2.js

'use strict';

const fs = require('fs');
const path = require('path');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm ci` in mobile/ first.');
  process.exit(2);
}

const ROOT = path.join(__dirname, '..');
const REPO = path.join(ROOT, '..');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}
function read(rel, base = ROOT) {
  return fs.readFileSync(path.join(base, rel), 'utf8');
}
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}

const modeBar = read('src/components/TradeFinderModeBar.tsx');
const utilityRow = read('src/components/TradeHomeUtilityRow.tsx');
const tradesScreen = read('src/screens/TradesScreen.tsx');
const tabNav = read('src/navigation/TabNav.tsx');
const signals = read('src/hooks/usePresentationSignals.ts');
const deckHook = read('src/hooks/usePresentationDeck.ts');
const hero = read('src/components/presentation/EndorsedTradeCard.tsx');
const browse = read('src/screens/TradeBrowseAllScreen.tsx');
const landing = read('src/screens/TodaysTradeScreen.tsx');
const band = read('src/components/presentation/FairnessRangeBand.tsx');
const confidence = read('src/components/presentation/ConfidenceChip.tsx');

// ═══════════════════════════════════════════════════════════════════════
// 1. Flag-off byte-identity — the ENTRY POINTS
// ═══════════════════════════════════════════════════════════════════════
// Sabotage: someone renders the chip unconditionally and no-ops the press.
// Both hosts must pass `undefined` when the flag is off, and both components
// must build their control list FROM the handler's presence.

const screenNoComments = stripComments(tradesScreen);

assert(
  /const presentationV2On = useFlag\('trades\.presentation_v2'\)/.test(screenNoComments),
  'TradesScreen reads the flag through useFlag',
);

// Every onTodaysTrade the screen passes must be a ternary on the flag —
// never a bare arrow function.
const passSites = screenNoComments.match(/onTodaysTrade=\{[\s\S]{0,180}?\}\n/g) || [];
assert(
  passSites.length === 2,
  'TradesScreen passes onTodaysTrade at exactly the two host sites (mode bar + utility row)',
  `found ${passSites.length}`,
);
assert(
  passSites.length > 0 && passSites.every((b) => /presentationV2On\s*\n?\s*\?/.test(b)),
  'every onTodaysTrade pass site is gated on presentationV2On',
  'an ungated pass ships the new tab to every user',
);
assert(
  passSites.every((b) => /:\s*undefined/.test(b)),
  'flag-off passes undefined (not a no-op handler)',
  'a no-op handler still RENDERS the chip — that is the whole failure mode',
);

// ═══════════════════════════════════════════════════════════════════════
// 2. Flag-off byte-identity — the COMPONENTS
// ═══════════════════════════════════════════════════════════════════════
const barNoComments = stripComments(modeBar);
assert(
  /onTodaysTrade\?\s*:/.test(barNoComments),
  'TradeFinderModeBar.onTodaysTrade is OPTIONAL',
  'a required prop forces every caller to pass one, which defeats the gate',
);
assert(
  /const chips = onTodaysTrade \? \[TODAY_CHIP, \.\.\.withDraft\] : withDraft;/.test(barNoComments),
  'TradeFinderModeBar: the Today chip exists only when the handler is passed',
  'handler absent must yield the pre-existing array, same objects, same order',
);
assert(
  !/CHIPS\s*=\s*\[[^\]]*'today'/.test(barNoComments),
  "TradeFinderModeBar: 'today' is NOT in the static CHIPS array",
  'putting it in CHIPS makes it unconditional — the exact regression this guards',
);

const rowNoComments = stripComments(utilityRow);
assert(
  /onTodaysTrade\?\s*:/.test(rowNoComments),
  'TradeHomeUtilityRow.onTodaysTrade is OPTIONAL',
);
assert(
  /\{onTodaysTrade \?/.test(rowNoComments),
  'TradeHomeUtilityRow renders its control only when the handler is passed',
);

// The routes register unconditionally (house rule: the flag gates the entry
// point, not the navigator entry) — but they must NOT be wrapped in a flag.
const navNoComments = stripComments(tabNav);
assert(
  /name="TodaysTrade"/.test(navNoComments) && /name="TradeBrowseAll"/.test(navNoComments),
  'both presentation routes are registered in the Trades stack',
);
assert(
  !/presentation_v2[\s\S]{0,200}TradesStack\.Screen/.test(navNoComments),
  'the presentation routes are NOT flag-wrapped in the navigator',
  'gating the route breaks a stored deep link on flag revalidation',
);

// ═══════════════════════════════════════════════════════════════════════
// 3. The server cache-slot agreement
// ═══════════════════════════════════════════════════════════════════════
const deckNoComments = stripComments(deckHook);
assert(
  /fairnessOnFromPref/.test(deckNoComments) && /fairnessThresholdFor/.test(deckNoComments),
  'usePresentationDeck resolves the threshold through the SHARED helpers',
);
assert(
  !/FAIRNESS_(ON|OFF)_THRESHOLD/.test(deckNoComments),
  'usePresentationDeck never re-derives the threshold from raw constants',
  'a local literal lands in a different server cache slot than the deck',
);
assert(
  !/force:\s*true/.test(deckNoComments),
  'usePresentationDeck never sends force:true',
  'forcing would invalidate a deck the user may be mid-triage on',
);

// ═══════════════════════════════════════════════════════════════════════
// 4. Instrumentation parity with the existing deck
// ═══════════════════════════════════════════════════════════════════════
const sigNoComments = stripComments(signals);

assert(
  /import \{ swipeTrade, type SwipeSignal \} from '\.\.\/api\/trades'/.test(sigNoComments),
  'signals hook imports swipeTrade AND the SwipeSignal type from api/trades',
  'a redeclared signal type silently drops any field added upstream',
);
assert(
  /swipeTrade\(card, decision, signal\)/.test(sigNoComments),
  'dispositions ride swipeTrade(card, decision, signal) — the deck\'s own call',
);
assert(
  /postDeclineReason/.test(sigNoComments),
  'decline reasons ride postDeclineReason (api/declineReasons)',
);
assert(
  !/api\.post\(/.test(sigNoComments) && !/api\.get\(/.test(sigNoComments),
  'the signals hook never hand-rolls an HTTP call',
  'a bespoke POST is how the two surfaces silently fork the dataset',
);

// The four signal fields, byte-for-byte as the deck sends them.
for (const field of ['impression_id', 'dwell_ms', 'detail_expanded', 'calc_opened']) {
  assert(
    new RegExp(`${field}:`).test(sigNoComments),
    `signal carries ${field}`,
  );
}
// The gate is the same two-part gate the deck uses.
assert(
  /if \(!signalV2On \|\| !card\?\.impression_id\) return undefined;/.test(sigNoComments),
  'signalForCard gates on deck.signal_v2 AND a served impression_id',
  'without an id the POST body must stay byte-identical to the pre-F1 shape',
);

// Event names must match the deck's exactly.
for (const evt of ['deck_card_viewed', 'trade_pass_layer1', 'trade_pass_layer2']) {
  assert(
    new RegExp(`'${evt}'`).test(sigNoComments),
    `emits '${evt}' (same name as the deck)`,
  );
  assert(
    new RegExp(`'${evt}'`).test(stripComments(tradesScreen)),
    `'${evt}' still exists on TradesScreen (parity anchor)`,
  );
}
assert(
  /has_free_text: freeText\.length > 0/.test(sigNoComments),
  'free text is reported as a BOOLEAN property, never the text itself',
  'SPEC 3.4 — the text lives on the row only',
);
assert(
  /platform:/.test(sigNoComments) && /Platform\.OS === 'android'/.test(sigNoComments),
  'platform is set EXPLICITLY at the emitter',
  'the NULL-platform incident is why this is never inferred downstream',
);
// The two duplicated constants must match TradesScreen's literals.
const viewedMinScreen = /VIEWED_MIN_MS\s*=\s*(\d+)/.exec(stripComments(tradesScreen));
const dwellCapScreen = /DWELL_CAP_MS\s*=\s*([\d_]+)/.exec(stripComments(tradesScreen));
const viewedMinHook = /VIEWED_MIN_MS\s*=\s*(\d+)/.exec(sigNoComments);
const dwellCapHook = /DWELL_CAP_MS\s*=\s*([\d_]+)/.exec(sigNoComments);
assert(
  viewedMinScreen && viewedMinHook && viewedMinScreen[1] === viewedMinHook[1],
  'VIEWED_MIN_MS matches TradesScreen',
  `screen=${viewedMinScreen && viewedMinScreen[1]} hook=${viewedMinHook && viewedMinHook[1]}`,
);
assert(
  dwellCapScreen && dwellCapHook && dwellCapScreen[1] === dwellCapHook[1],
  'DWELL_CAP_MS matches TradesScreen',
  `screen=${dwellCapScreen && dwellCapScreen[1]} hook=${dwellCapHook && dwellCapHook[1]}`,
);

// Both surfaces mount the SAME decline panel, so the taxonomy cannot drift.
assert(
  /DeclineReasonPanel/.test(stripComments(hero)),
  'the hero card mounts the shared DeclineReasonPanel',
  'a second reason UI would fork the taxonomy',
);
assert(
  /onLayer1:/.test(stripComments(landing)) && /onLayer2Bank:/.test(stripComments(landing)),
  'the landing wires all the progressive commit moments, including the bank',
);

// ═══════════════════════════════════════════════════════════════════════
// 5. The design laws
// ═══════════════════════════════════════════════════════════════════════
const presentationDir = path.join(ROOT, 'src/components/presentation');
const presentationSrc = fs
  .readdirSync(presentationDir)
  .filter((f) => f.endsWith('.tsx'))
  .map((f) => stripComments(read(path.join('src/components/presentation', f))))
  .join('\n');
const surfaceSrc = [presentationSrc, stripComments(landing), stripComments(browse)].join('\n');

// P3 — no winner needle anywhere on this surface.
assert(
  !/TradeValueBar/.test(surfaceSrc),
  'no TradeValueBar on the presentation surface',
  'it literally renders "You win" / "They win" — banned here (P3)',
);
assert(
  !/fairnessColor/.test(surfaceSrc) && !/<Meter\b/.test(surfaceSrc),
  'no fairness Meter / fairnessColor on the presentation surface',
  'the Meter fill colour IS a verdict — banned here (P3)',
);
assert(
  /withinNormal/.test(stripComments(band)) && !/favors/.test(stripComments(band)),
  'FairnessRangeBand has no notion of who the trade favours',
);

// P2 — the counterparty half exposes nothing about their board.
const heroNoComments = stripComments(hero);
assert(
  /counterpartyStatement\(card\)/.test(heroNoComments),
  'the hero renders the counterparty half through counterpartyStatement()',
);
assert(
  !/opponent_surplus/.test(surfaceSrc),
  'the surface never renders match_context.opponent_surplus',
  "that is the other manager's roster read — never exposed (P2)",
);
assert(
  !/partner_fit/.test(surfaceSrc),
  'the surface never renders partner_fit',
  'a counterparty fit NUMBER is exactly what the confidence statement replaces',
);

// P5 — no two-digit confidence percentage.
assert(
  !/match_score/.test(surfaceSrc),
  'the surface never renders match_score',
  'a 0-100 score on thin data is the miscalibration failure this design avoids',
);
assert(
  !/showPercent/.test(surfaceSrc),
  'no percent readout on the presentation surface',
);
assert(
  /band === 'strong'/.test(stripComments(confidence)),
  'ConfidenceChip switches on the band ENUM, not on a number',
);

// P1 — browse is uncapped.
const browseNoComments = stripComments(browse);
assert(
  !/\.slice\(/.test(browseNoComments),
  'TradeBrowseAllScreen never slices its list',
  'every view and dismiss is training signal — capping discovery deletes it',
);
assert(
  /dismissedIds\.has\(item\.trade_id\)/.test(browseNoComments),
  'dismissed rows stay in the list, rendered in their dismissed state',
  'filtering them out deletes the acknowledgement the design exists to show',
);
assert(
  /onUndo/.test(browseNoComments),
  'the dismissed state offers Undo',
);

// A11y: the row controls are reachable and labelled.
const rowSrc = stripComments(read('src/components/presentation/TradeIdeaRow.tsx'));
assert(
  /hitSlop=\{\{ top: 8, bottom: 8, left: 8, right: 8 \}\}/.test(rowSrc),
  'the 28pt dismiss control is padded to a 44pt effective target',
);
assert(
  /accessibilityLabel=\{dismissed \?/.test(rowSrc),
  'the dismiss control announces which state it is in',
);
assert(
  !/numberOfLines/.test(surfaceSrc),
  'no numberOfLines anywhere on the surface',
  'OS text scaling must WRAP this copy, never truncate it',
);

// ═══════════════════════════════════════════════════════════════════════
// 6. The pure module, actually executed
// ═══════════════════════════════════════════════════════════════════════
function load(rel) {
  const source = read(rel);
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const shim = { exports: {} };
  new Function('module', 'exports', 'require', js)(shim, shim.exports, (name) => {
    throw new Error(
      `tradePresentation.ts gained an unexpected runtime import ("${name}") — ` +
        'it must stay pure (no React, no state, no network).',
    );
  });
  return shim.exports;
}

const P = load('src/utils/tradePresentation.ts');

// Confidence bands read the provenance fields, not an invented score.
assert(
  P.confidenceBand({ basis: 'divergence', real_opponent: true }) === 'strong',
  'both boards real -> strong',
);
assert(
  P.confidenceBand({ basis: 'consensus', real_opponent: true }) === 'moderate',
  'consensus basis but a real counterparty -> moderate',
);
assert(
  P.confidenceBand({ basis: 'divergence', real_opponent: false }) === 'moderate',
  'real disagreement but an estimated counterparty -> moderate',
);
assert(
  P.confidenceBand({ basis: 'consensus', real_opponent: false }) === 'early',
  'consensus-only and estimated -> early signal',
);
assert(
  P.confidenceBand({ basis: 'consensus', real_opponent: false, likesYou: true }) === 'strong',
  'a reciprocated like promotes to strong regardless of provenance',
);
assert(
  P.isEndorsable({ basis: 'divergence', real_opponent: true }) === true &&
    P.isEndorsable({ basis: 'consensus', real_opponent: false }) === false,
  'only a strong card is endorsable (binary badge, no ladder)',
);

// No band label may contain a digit — the "never a percentage" law, enforced
// on the strings themselves rather than on the call sites.
assert(
  Object.values(P.BAND_LABEL).every((l) => !/\d/.test(l)),
  'no band label contains a number',
);

// Fairness: a range, with no side.
const fb = P.fairnessBand(0.9);
assert(fb && fb.withinNormal === true, '0.90 reads as within league-normal');
assert(
  P.fairnessBand(0.6).withinNormal === false,
  '0.60 reads as outside league-normal',
);
assert(
  fb && !('favors' in fb) && !('winner' in fb) && !('margin' in fb),
  'the fairness band exposes no winner and no margin',
);
assert(P.fairnessBand(undefined) === null, 'missing fairness hides the band entirely');

// The asymmetry.
const card = {
  trade_id: 't1',
  league_id: 'L',
  opponent_username: 'Brett',
  basis: 'divergence',
  real_opponent: true,
  lane: 'window',
  give_players: [{ id: 'g1', name: 'DeVonta Smith' }],
  receive_players: [{ id: 'r1', name: 'James Cook' }],
  match_context: { user_needs: ['RB'], opponent_surplus: ['WR'] },
};
const bullets = P.userSideBullets(card);
assert(bullets.length > 0 && bullets.length <= P.MAX_USER_BULLETS, 'user side gets 1..3 bullets');
assert(
  bullets.join(' ').includes('James Cook'),
  'the user-side bullets name a concrete asset from THIS card',
);
assert(
  !bullets.join(' ').includes('WR'),
  'the user-side bullets never leak opponent_surplus',
);
const statement = P.counterpartyStatement(card);
assert(typeof statement === 'string', 'the counterparty half is a single string');
assert(!/\d/.test(statement), 'the counterparty statement contains no number');
assert(statement.includes('Brett'), 'the counterparty statement names the manager');

// The pyramid.
const mk = (id, strong) => ({
  trade_id: id,
  basis: strong ? 'divergence' : 'consensus',
  real_opponent: strong,
  give_players: [],
  receive_players: [],
});
const deck = [mk('a', false), mk('b', true), mk('c', true), mk('d', false), mk('e', false),
  mk('f', false), mk('g', false), mk('h', false)];
const part = P.partitionDeck(deck);
assert(part.hero && part.hero.trade_id === 'b', 'the hero is the first ENDORSABLE card, not the first card');
assert(part.featured.length <= P.FEATURED_CAP, 'the Featured tier is capped');
assert(part.all.length === deck.length, 'browse keeps every card — uncapped');
const noneStrong = P.partitionDeck([mk('x', false), mk('y', false)]);
assert(
  noneStrong.hero === null,
  'no endorsable card -> NO hero (the honest empty state, not a promoted moderate)',
);
const withDismissed = P.partitionDeck(deck, new Set(['b']));
assert(
  withDismissed.hero && withDismissed.hero.trade_id === 'c',
  'a dismissed card cannot be the hero',
);
assert(
  withDismissed.all.some((c) => c.trade_id === 'b'),
  'a dismissed card is still present in the browse list',
);

// The confidence cap.
assert(P.confidenceCap('strong', { total_completed: 1, total_required: 100 }) === null,
  'a strong band is never capped');
const cap = P.confidenceCap('moderate', { total_completed: 34, total_required: 60 });
assert(cap && !/%/.test(cap.headline), 'the cap headline carries no percentage');
assert(cap && cap.coverage > 0.56 && cap.coverage < 0.57, 'coverage is the real ratio');
const capNoData = P.confidenceCap('early', undefined);
assert(capNoData && capNoData.coverage === null, 'missing progress hides the coverage track');

// The honest empty state.
const e = P.emptyStateCopy({ rostersChecked: 11, fairnessThreshold: 0.75, suppressedCount: 2 });
assert(e.body.includes('11 rosters'), 'the empty state reports the REAL roster count');
assert(e.canWidenFairness === true, 'a 0.75 threshold offers the widen lever');
assert(
  P.emptyStateCopy({ fairnessThreshold: 0.5 }).canWidenFairness === false,
  'an already-wide net offers no widen lever',
);
assert(
  P.emptyStateCopy({ rostersChecked: 0 }).body.length > 0 &&
    !P.emptyStateCopy({ rostersChecked: 0 }).body.includes('0 rosters'),
  'an unknown roster count is omitted, never rendered as zero',
);
assert(e.suppressionNote !== null, 'a real suppression count is reported');
assert(
  P.emptyStateCopy({}).suppressionNote === null,
  'no suppression data -> no suppression claim',
);

// ═══════════════════════════════════════════════════════════════════════
// 7. Flag registration
// ═══════════════════════════════════════════════════════════════════════
const featuresJson = JSON.parse(read('config/features.json', REPO));
assert(
  Object.prototype.hasOwnProperty.call(featuresJson, 'trades.presentation_v2'),
  'trades.presentation_v2 exists in config/features.json',
);
assert(
  featuresJson['trades.presentation_v2'] === true,
  'trades.presentation_v2 ships ON',
  'operator lit it 2026-08-19 for the 1.15.0 TestFlight build; set false to go dark again',
);
assert(
  /"trades\.presentation_v2",/.test(read('backend/feature_flags.py', REPO)),
  'trades.presentation_v2 is registered in backend FLAG_KEYS',
  'an unregistered key is dropped by the JSON loader with a typo warning',
);
const launchedDefaults = read('src/state/useFeatureFlags.ts');
assert(
  !/'trades\.presentation_v2'/.test(launchedDefaults),
  'trades.presentation_v2 is ABSENT from LAUNCHED_FLAG_DEFAULTS',
  'a dark flag listed there would paint the chip for one frame before flipping',
);

// ═══════════════════════════════════════════════════════════════════════
// 8. Surface attribution — each screen reports its OWN user_events.screen
// ═══════════════════════════════════════════════════════════════════════
// `screen` (the track() third arg) is a real column, already populated on
// 100% of client-fired trade events with 12+ distinct values in prod. The
// original build hardcoded `'Trades'` — the value TradesScreen itself
// reports — which merged this surface, Browse All, and the deck into ONE
// bucket and made per-surface comparison look impossible when the mechanism
// was there all along. These assertions exist so that cannot come back.
const signalsSrc = read('src/hooks/usePresentationSignals.ts');
assert(
  !/const\s+SCREEN\s*=\s*'Trades'/.test(signalsSrc),
  "the hook does NOT hardcode screen as 'Trades'",
  'that value collides with TradesScreen and silently merges the buckets',
);
assert(
  /usePresentationSignals\(\s*screen:\s*PresentationScreen\s*\)/.test(signalsSrc),
  'the hook takes its surface as a parameter',
);
for (const [file, value] of [
  ['src/screens/TodaysTradeScreen.tsx', 'TodaysTrade'],
  ['src/screens/TradeBrowseAllScreen.tsx', 'TradeBrowseAll'],
]) {
  assert(
    new RegExp(`usePresentationSignals\\('${value}'\\)`).test(read(file)),
    `${file.split('/').pop()} reports screen='${value}'`,
    'each surface must be separable from the other AND from the deck',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All presentation-v2 checks passed.');
