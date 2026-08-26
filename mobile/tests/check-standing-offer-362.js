#!/usr/bin/env node
// Standing offers — feedback #362.
//
// Build contract: docs/feedback/items/362-standing-offer/ (prd.md §8.2).
// Approved design: mockups/standing-offer-362/index.html (honor its §6 dated
// CORRECTION, not the struck-through value-gate row).
//
// WHY THIS EXISTS. #362 puts a user's intent in front of OTHER PEOPLE with
// no further tap from them. Almost every way to get that wrong is silent,
// and three of them are unrecoverable once shipped:
//
//   * PRIVACY. Jon's ask is half exclusion — "a first from any of these
//     rosters but not xyz". A private negative that leaks starts fights in
//     real leagues, and no later patch un-tells a league-mate they were
//     excluded. `team_user_ids` reaching a recipient-facing render path
//     compiles, typechecks, and looks correct.
//   * THE TRIGGER. Eleven conditions gate a prompt on a surface whose whole
//     value is speed. One `setStandingOfferPrompt({...})` added elsewhere
//     bypasses all of them and turns the deck into a nag — and "the prompt
//     became annoying" surfaces two weeks later as churn, not as a bug.
//   * THE YEAR WINDOW. A hardcoded N-year window offers picks in seasons a
//     league does not have. That is the #355 defect exactly; it reached
//     12.8% of served cards and nothing in the client complained.
//
// Two more that fail quietly rather than loudly: a second hardcoded default
// selection in the parent would survive flipping the R-6 constant (so the
// variant switch would silently do nothing), and an analytics event
// registered client-side under a name the backend taxonomy does not carry
// is dropped on ingest with no error.
//
// Every assertion names the sabotage it detects. Assertions of the form "X
// appears nowhere" read COMMENT-STRIPPED source — the comments in these
// files deliberately name the constructs they forbid, which is exactly how
// four earlier tests shipped unfailable (check-league-candidates-300.js).
//
// Run: node tests/check-standing-offer-362.js

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
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const MOBILE = path.join(__dirname, '..');
const REPO = path.join(MOBILE, '..');
function read(abs) {
  return fs.readFileSync(abs, 'utf8');
}
function parse(rel) {
  const abs = path.join(MOBILE, rel);
  return ts.createSourceFile(
    abs,
    read(abs),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
}
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}
function walk(node, visit) {
  visit(node);
  node.forEachChild((c) => walk(c, visit));
}
function findAll(sf, pred) {
  const out = [];
  walk(sf, (n) => {
    if (pred(n)) out.push(n);
  });
  return out;
}
function within(node, container) {
  return node.getStart() >= container.getStart() && node.getEnd() <= container.getEnd();
}
/** The function/arrow declared as `function <name>` or `const <name> = …`. */
function namedFn(sf, name) {
  const fnDecls = findAll(
    sf,
    (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === name,
  );
  if (fnDecls.length === 1) return fnDecls[0];
  const varDecls = findAll(
    sf,
    (n) =>
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.name.text === name &&
      !!n.initializer,
  );
  return varDecls.length === 1 ? varDecls[0].initializer : null;
}
/** Every .ts/.tsx file under mobile/src. */
function srcFiles() {
  const out = [];
  (function rec(dir) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) rec(p);
      else if (/\.tsx?$/.test(e.name)) out.push(p);
    }
  })(path.join(MOBILE, 'src'));
  return out;
}

const SHEET = 'src/components/StandingOfferSheet.tsx';
const DECK = 'src/screens/TradesScreen.tsx';
const CARD = 'src/components/TradeCard.tsx';
const MATCHES = 'src/screens/MatchesScreen.tsx';
const OB = 'src/state/useOnboardingState.ts';

const sheet = parse(SHEET);
const deck = parse(DECK);
const card = parse(CARD);
const matches = parse(MATCHES);
const ob = parse(OB);

console.log('═'.repeat(72));
console.log('1 — the trigger: eleven conditions, and exactly one way in');
console.log('═'.repeat(72));

const trigger = namedFn(deck, 'maybeShowStandingOfferPrompt');
assert(!!trigger, '#362 SC-1a — maybeShowStandingOfferPrompt exists in TradesScreen');

if (trigger) {
  const body = stripComments(trigger.getText(deck));
  // SC-1 — every condition class is present. Named individually so a
  // dropped one names itself in the failure, rather than a count going 11→10.
  const conditions = [
    ['flags (standing_offers + likes_you + picks_in_pool)', /standingOfferReady/],
    ['one prompt per app session', /standingOfferPromptShownThisSession/],
    ['not the first like', /firstLike/],
    ['no competing surface', /quicksetPromptVisible|adaptationMoment|guideActiveStepId|appleAskEligible/],
    ['not a demo deck', /isDemo/],
    ['not pinned / opponent-scoped', /pinnedGive|pinnedReceive|scopedOpponent/],
    ['persisted snooze ladder', /standingOfferPromptRetired|standingOfferPromptSnoozed/],
    ['a strict 1-for-1', /give_players\.length !== 1|receive_players\.length !== 1/],
    ['the received asset is an OWNED league pick', /position !== 'PICK'|startsWith\(/],
    ['picks_supported for this league', /picks_supported/],
    ['the pick resolves in all_picks at round 1', /all_picks|sourcePick/],
    ['no live offer already covers (player, round)', /alreadyLive|revoked_at/],
  ];
  for (const [label, re] of conditions) {
    assert(re.test(body), `#362 SC-1 — the gate still tests: ${label}`,
      'dropping a condition here widens the prompt onto swipes it was never ' +
      'meant to interrupt, and nothing else in the tree notices');
  }
  assert(
    !/return\s+true/.test(body),
    '#362 SC-1b — the gate has no early `return true`',
    'a short-circuit that declares the prompt eligible before the remaining ' +
      'conditions run is the classic way eleven checks become three',
  );

  // SC-12 (R-18, FB-46) — the trigger reads ONLY fields a RECONSTRUCTED card
  // also carries. A reconstructed card zeroes scores and drops lane_shift,
  // so keying off them makes the prompt fire, or not, depending on how the
  // card reached the client.
  const cardReads = new Set(
    findAll(
      trigger,
      (n) =>
        ts.isPropertyAccessExpression(n) &&
        ts.isIdentifier(n.expression) &&
        n.expression.text === 'card',
    ).map((n) => n.name.text),
  );
  const allowed = new Set([
    'give_players',
    'receive_players',
    'opponent_user_id',
    'trade_id',
  ]);
  const illegal = [...cardReads].filter((k) => !allowed.has(k));
  assert(
    illegal.length === 0,
    '#362 SC-12 — the trigger reads only give/receive/opponent_user_id/trade_id off the card',
    `also reads: ${illegal.join(', ')} — a reconstructed card (FB-46) zeroes ` +
      'composite_score / fairness / basis and never sets likes_you',
  );
}

// SC-2 — the sheet's visibility is SET in exactly one place. Clearing it
// (null) is unrestricted; opening it is not.
const setPromptCalls = findAll(
  deck,
  (n) =>
    ts.isCallExpression(n) &&
    ts.isIdentifier(n.expression) &&
    n.expression.text === 'setStandingOfferPrompt',
);
const openCalls = setPromptCalls.filter(
  (c) => c.arguments[0] && ts.isObjectLiteralExpression(c.arguments[0]),
);
assert(
  openCalls.length === 1,
  '#362 SC-2a — exactly ONE call site opens the standing-offer sheet',
  `found ${openCalls.length} — a second one skips all eleven trigger conditions`,
);
assert(
  openCalls.length === 1 && !!trigger && within(openCalls[0], trigger),
  '#362 SC-2b — that call site is inside maybeShowStandingOfferPrompt',
  'the gate and the open must be the same function, or the gate is advisory',
);

console.log('');
console.log('═'.repeat(72));
console.log('2 — the dismissal ladder is PERSISTED, not a session counter');
console.log('═'.repeat(72));

// SC-3 — the four keys exist in the store's DEFAULTS and move through the
// store's own read/write API. A module-scoped `let shown = false` resets on
// every cold start, so a user who says no is asked again forever.
const obSrc = stripComments(read(path.join(MOBILE, OB)));
const OB_KEYS = [
  'standingOfferPromptShows',
  'standingOfferPromptSnoozed',
  'standingOfferPromptSession2Shown',
  'standingOfferPromptRetired',
];
const defaults = findAll(
  ob,
  (n) =>
    ts.isVariableDeclaration(n) &&
    ts.isIdentifier(n.name) &&
    n.name.text === 'DEFAULTS' &&
    !!n.initializer,
)[0];
const defaultNames = defaults
  ? defaults.initializer.properties.map((p) => (p.name ? p.name.getText(ob) : ''))
  : [];
for (const k of OB_KEYS) {
  assert(
    obSrc.includes(k) && defaultNames.includes(k),
    `#362 SC-3a — ${k} is declared AND defaulted in useOnboardingState`,
    'a key present on the interface but missing from DEFAULTS reads undefined ' +
      'on a fresh install, and `undefined < 2` is false — the ladder skips a rung',
  );
}
if (trigger) {
  const body = stripComments(trigger.getText(deck));
  assert(
    /getOnboardingState\(\)/.test(body) && /patchOnboardingState\(/.test(body),
    '#362 SC-3b — the trigger reads and writes the ladder through the persisted store',
    'a module-scoped boolean as the ONLY gate resets on every cold start',
  );
}
const skipFn = namedFn(deck, 'skipStandingOfferPrompt');
assert(!!skipFn, '#362 SC-3c — skipStandingOfferPrompt exists');
if (skipFn) {
  const body = stripComments(skipFn.getText(deck));
  // The terminal branch must match quickset's: snoozing the session-2
  // re-offer retires the prompt for good.
  assert(
    /standingOfferPromptSnoozed\s*&&\s*ob\.standingOfferPromptSession2Shown/.test(body) &&
      /standingOfferPromptRetired:\s*true/.test(body),
    '#362 SC-3d — the retire branch matches quickset\'s (snooze of the session-2 re-offer retires)',
    'without the terminal rung, "no" never becomes permanent',
  );
  assert(
    /track\(\s*'standing_offer_skipped'/.test(body),
    '#362 SC-3e — the skip fires standing_offer_skipped',
  );
}

console.log('');
console.log('═'.repeat(72));
console.log('3 — the year pills are DERIVED, never a window (the #355 class)');
console.log('═'.repeat(72));

// SC-4 — no year literal, no fixed window length, anywhere in the sheet.
const sheetSrc = stripComments(read(path.join(MOBILE, SHEET)));
const yearLiterals = sheetSrc.match(/\b20[2-9][0-9]\b/g) || [];
assert(
  yearLiterals.length === 0,
  '#362 SC-4a — no 4-digit season literal appears in the sheet',
  `found ${[...new Set(yearLiterals)].join(', ')} — a hardcoded year offers ` +
    'picks in seasons a league does not have (#355 / D-091)',
);
assert(
  !/\.slice\(\s*0\s*,\s*\d+\s*\)/.test(sheetSrc),
  '#362 SC-4b — no fixed-length window slice in the sheet',
  'a `slice(0, 3)` is the same defect with the literal moved one level out',
);
// The pills come from the caller's all_picks-derived prop, and that prop is
// derived from all_picks in TradesScreen — both halves, or the chain is
// only half pinned.
assert(
  /availableSeasons/.test(sheetSrc) && /seasonPills/.test(sheetSrc),
  '#362 SC-4c — the pill set is the availableSeasons prop, not a local constant',
);
const seasonsMemo = namedFn(deck, 'standingOfferSeasons');
assert(
  !!seasonsMemo && /all_picks/.test(stripComments(seasonsMemo.getText(deck))),
  '#362 SC-4d — TradesScreen derives availableSeasons from all_picks',
  'D-091 made all_picks horizon-correct AT THE WRITER, so reading it is ' +
    'correct by construction — anything else re-opens #355',
);

console.log('');
console.log('═'.repeat(72));
console.log('4 — members and picks are two sources, never conflated');
console.log('═'.repeat(72));

// SC-5 — the rows come from the members endpoint; the trailing annotation
// from all_picks. Sourcing rows from all_picks would silently DROP the teams
// that own no first — exactly the rows the user needs to see own none.
const membersMemo = namedFn(deck, 'standingOfferMembers');
const firstsMemo = namedFn(deck, 'standingOfferFirstsByOwner');
assert(
  !!membersMemo && /leagueMembersQuery/.test(membersMemo.getText(deck)),
  '#362 SC-5a — the team rows come from the league MEMBERS query',
  'sourcing them from all_picks hides every team that owns no first',
);
assert(
  !!membersMemo && !/all_picks/.test(stripComments(membersMemo.getText(deck))),
  '#362 SC-5b — the member list does NOT read all_picks',
);
assert(
  !!firstsMemo && /all_picks/.test(stripComments(firstsMemo.getText(deck))),
  '#362 SC-5c — the ownership annotation comes from all_picks',
);

console.log('');
console.log('═'.repeat(72));
console.log('5 — one named constant owns the default selection');
console.log('═'.repeat(72));

// SC-6 — flipping STANDING_OFFER_DEFAULT_SELECTION must be the ENTIRE change
// for variant (b). A second hardcoded default anywhere would survive the flip
// and make the switch silently do nothing.
const constDecl = findAll(
  sheet,
  (n) =>
    ts.isVariableDeclaration(n) &&
    ts.isIdentifier(n.name) &&
    n.name.text === 'STANDING_OFFER_DEFAULT_SELECTION',
)[0];
assert(!!constDecl, '#362 SC-6a — STANDING_OFFER_DEFAULT_SELECTION is declared');
assert(
  !!constDecl && /'source-only'/.test(constDecl.getText(sheet)),
  "#362 SC-6b — the shipped default is 'source-only'",
  'variant (b) pre-checks every team; an accidental confirm then broadcasts ' +
    'to the whole league instead of reproducing a plain like',
);
const defaultParam = findAll(
  sheet,
  (n) =>
    ts.isBindingElement(n) &&
    ts.isIdentifier(n.name) &&
    n.name.text === 'defaultSelection',
)[0];
assert(
  !!defaultParam &&
    !!defaultParam.initializer &&
    defaultParam.initializer.getText(sheet) === 'STANDING_OFFER_DEFAULT_SELECTION',
  '#362 SC-6c — the prop defaults to the constant, not to a repeated literal',
);
// Exactly one comparison reads the variant.
const variantReads = findAll(
  sheet,
  (n) =>
    ts.isBinaryExpression(n) &&
    /defaultSelection/.test(n.left.getText(sheet)),
);
assert(
  variantReads.length === 1,
  '#362 SC-6d — exactly one comparison branches on the variant',
  `found ${variantReads.length} — every extra one is a place variant (b) can ` +
    'be half-applied',
);
// Neither literal appears loose anywhere else in the file. Three legal
// homes, and only three: the type alias, the constant's initializer, and
// the single SC-6d comparison. Any fourth occurrence is a place variant (b)
// can be half-applied.
const legalHomes = [
  constDecl,
  findAll(
    sheet,
    (n) => ts.isTypeAliasDeclaration(n) && n.name.text === 'StandingOfferDefaultSelection',
  )[0],
  ...variantReads,
].filter(Boolean);
const strayLiterals = findAll(
  sheet,
  (n) =>
    ts.isStringLiteral(n) &&
    (n.text === 'source-only' || n.text === 'all') &&
    !legalHomes.some((h) => within(n, h)),
);
assert(
  strayLiterals.length === 0,
  '#362 SC-6e — no bare variant literal outside the type alias, the constant and the one comparison',
  `found ${strayLiterals.length} — a second hardcoded default survives the flip`,
);

console.log('');
console.log('═'.repeat(72));
console.log('6 — the sheet can never cost the user their like');
console.log('═'.repeat(72));

// SC-7a — the deck advance is not inside any standing-offer branch, and it
// happens BEFORE the prompt can be raised. The like is banked by then, so
// dismissing is byte-identical to today's behavior.
const advanceFn = namedFn(deck, 'advance');
assert(!!advanceFn, '#362 SC-7a0 — advance() found');
if (advanceFn && trigger) {
  const advSrc = advanceFn.getText(deck);
  const idxAdvance = advSrc.indexOf('setDeckIdx((i) => i + 1)');
  const idxPrompt = advSrc.indexOf('maybeShowStandingOfferPrompt(');
  assert(
    idxAdvance >= 0 && idxPrompt > idxAdvance,
    '#362 SC-7a — the deck advances BEFORE the standing-offer prompt is raised',
    `advance@${idxAdvance} prompt@${idxPrompt} — the sheet must render over ` +
      'the NEXT card and must never gate the advance',
  );
  assert(
    !/setDeckIdx/.test(trigger.getText(deck)),
    '#362 SC-7b — the trigger never touches the deck index',
  );
}

// SC-7c — season and team selection are independent (R-7). Toggling one
// must never read or write the other's state.
const toggleSeason = namedFn(sheet, 'toggleSeason');
const toggleTeam = namedFn(sheet, 'toggleTeam');
assert(!!toggleSeason && !!toggleTeam, '#362 SC-7c0 — both toggles found');
if (toggleSeason && toggleTeam) {
  const idents = (fn) =>
    new Set(findAll(fn, (n) => ts.isIdentifier(n)).map((n) => n.text));
  const sIds = idents(toggleSeason);
  const tIds = idents(toggleTeam);
  assert(
    !sIds.has('teams') && !sIds.has('setTeams'),
    '#362 SC-7c — toggling a season never touches team state',
    'a season toggle that unchecks teams turns two flat multi-selects into a ' +
      'matrix, which is the shape the operator ruled out',
  );
  assert(
    !tIds.has('seasons') && !tIds.has('setSeasons'),
    '#362 SC-7d — toggling a team never touches season state',
  );
}

console.log('');
console.log('═'.repeat(72));
console.log('7 — the confirmation count comes from the SERVER');
console.log('═'.repeat(72));

// SC-8 — the toast quotes `team_count` off the POST response, not a
// client-side array length: the server is the authority on what it stored,
// and a client length can disagree with it after normalization/dedupe.
const onPosted = findAll(
  deck,
  (n) => ts.isJsxAttribute(n) && n.name.getText(deck) === 'onPosted',
)[0];
assert(!!onPosted, '#362 SC-8a — the sheet mount supplies onPosted');
if (onPosted) {
  const src = stripComments(onPosted.getText(deck));
  assert(
    /offer\.team_count/.test(src),
    '#362 SC-8b — the toast reads offer.team_count from the POST response',
    'a client-side `teams.length` can disagree with what the server actually ' +
      'stored, and the user is told the wrong reach for their own broadcast',
  );
  assert(
    !/teams\.length/.test(src),
    '#362 SC-8c — the toast does NOT quote a client-side length',
  );
}

console.log('');
console.log('═'.repeat(72));
console.log('8 — PRIVACY: the private negative never leaves the sender');
console.log('═'.repeat(72));

// SC-13 — `team_user_ids` may appear ONLY in the API layer (the type + the
// normalizer) and in the sender's own sheet (the POST body). Anywhere else
// in mobile/src is a recipient-facing render path.
const SENDER_OWNED = new Set([
  path.join(MOBILE, 'src/api/trades.ts'),
  path.join(MOBILE, SHEET),
]);
const leaks = srcFiles().filter(
  (f) => !SENDER_OWNED.has(f) && /team_user_ids/.test(stripComments(read(f))),
);
assert(
  leaks.length === 0,
  '#362 SC-13 — team_user_ids appears in NO recipient-facing path',
  `leaked into: ${leaks.map((f) => path.relative(MOBILE, f)).join(', ')} — ` +
    'the recipient learns THEY were selected, never who else was and never ' +
    'who was excluded; "but not xyz" is a private negative',
);

// SC-9 — no PLAYER-level badge reads standing-offer state. A permanent
// "open to 1sts" marker on the player outlives the intent that created it
// and leaks the offer to league-mates who were deliberately excluded.
const CHIP_OWNERS = new Set([
  path.join(MOBILE, 'src/api/trades.ts'),
  path.join(MOBILE, 'src/shared/types.ts'),
  path.join(MOBILE, CARD),
]);
const badgeLeaks = srcFiles().filter(
  (f) =>
    !CHIP_OWNERS.has(f) &&
    /standingOfferMine|standing_offer_mine/.test(stripComments(read(f))),
);
assert(
  badgeLeaks.length === 0,
  '#362 SC-9 — standing-offer chip state is read only by the trade card',
  `also read by: ${badgeLeaks.map((f) => path.relative(MOBILE, f)).join(', ')} — ` +
    'a player-level badge is permanent, and the offer is not',
);

console.log('');
console.log('═'.repeat(72));
console.log('9 — the recipient card is the SHIPPED likes-you card');
console.log('═'.repeat(72));

// SC-11 — the recipient side gains a text line, not a component. The flare
// "They're interested" pill is reused as-is; the whole reason this item is
// small is that the receiving experience already exists.
const cardSrc = stripComments(read(path.join(MOBILE, CARD)));
assert(
  /data\.standingOfferReason/.test(cardSrc),
  '#362 SC-11a — TradeCard renders standingOfferReason',
);
assert(
  /styles\.likesYouPill/.test(cardSrc),
  '#362 SC-11b — the flare "They\'re interested" pill is still the recipient treatment',
  'replacing it with a bespoke standing-offer pill forks a shipped surface ' +
    'for no new information',
);
// The reason line must be rendered verbatim from the server string — never
// assembled client-side, which is how a count or a team name creeps in.
const reasonBlocks = findAll(
  card,
  (n) =>
    ts.isJsxExpression(n) &&
    /standingOfferReason/.test(n.getText(card)) &&
    ts.isJsxElement(n.parent),
);
assert(
  reasonBlocks.length > 0 &&
    !/standingOfferReason\s*[+`]|\$\{[^}]*standingOfferReason/.test(cardSrc),
  '#362 SC-11c — the reason string is rendered verbatim, never concatenated',
  'the server composes it from (sender, player, round, seasons) ALONE; any ' +
    'client-side assembly is a place a count or a team name gets appended',
);

console.log('');
console.log('═'.repeat(72));
console.log('10 — the manage surface: three segments, revoke only');
console.log('═'.repeat(72));

// SC-10 — Edit and Repost (mockup §5) are deliberately out of v1.
const segAlias = findAll(
  matches,
  (n) => ts.isTypeAliasDeclaration(n) && n.name.text === 'Segment',
)[0];
assert(!!segAlias, '#362 SC-10a — the Segment union is declared');
if (segAlias) {
  const members = (segAlias.type.types || []).map((t) => t.getText(matches).replace(/'/g, ''));
  assert(
    members.length === 3 && members.includes('standing'),
    "#362 SC-10b — Segment has exactly three members, including 'standing'",
    `got [${members.join(', ')}]`,
  );
}
const matchesSrc = stripComments(read(path.join(MOBILE, MATCHES)));
assert(
  /revokeStandingOffer/.test(matchesSrc) && /matches\.standing-revoke\./.test(matchesSrc),
  '#362 SC-10c — the standing segment offers Revoke',
  'a broadcast with no revoke is a thing users are afraid to use',
);
assert(
  !/label="Edit"/.test(matchesSrc) && !/label="Repost"/.test(matchesSrc),
  '#362 SC-10d — no Edit or Repost control (out of v1)',
  'either would need a fourth route and a second entry point into the ' +
    'post-like sheet; revoke-then-repost already covers both',
);
// The screen must NOT mount its own FeedbackFAB — the RootNav tab-stack
// mount already covers it (CLAUDE.md #188).
assert(
  !/FeedbackFAB/.test(matchesSrc),
  '#362 SC-10e — MatchesScreen mounts no FeedbackFAB of its own',
  'the RootNav tab-stack mount already covers this screen; a second one ' +
    'double-stacks the button',
);

console.log('');
console.log('═'.repeat(72));
console.log('11 — the flag is DARK, and says so in both places');
console.log('═'.repeat(72));

// SC-14 — `trade.standing_offers` GRADUATED to lit on 2026-08-26 (operator
// ruling, D-164). This assertion previously pinned the flag OFF, on the
// reasoning that "graduation is an operator action after a TestFlight pass on
// a real league". Recording honestly what changed: the operator graduated it
// WITHOUT that pass — the #362 TestFlight checklist is still unrun, and the
// accepted trade-off is written up in D-164. The flag is still a kill switch:
// flipping it back to false, or setting model_config standing_offer_inject_cap
// to 0, disables the feature deploy-free.
//
// SC-14b below is the invariant that holds in BOTH states and is the one that
// must never be relaxed (D-163): the client flag map fails OPEN, so listing
// this flag there would light the feature on a first boot or a failed
// revalidate — for a lit flag that breaks the kill switch, and for a dark one
// it lights a feature the operator never enabled.
const featuresJson = JSON.parse(read(path.join(REPO, 'config/features.json')));
assert(
  featuresJson['trade.standing_offers'] === true,
  '#362 SC-14a — config/features.json ships trade.standing_offers LIT (D-164)',
  'graduated 2026-08-26 by operator ruling; flip to false to kill deploy-free',
);
const flagStoreSrc = read(path.join(MOBILE, 'src/state/useFeatureFlags.ts'));
const launchedBlock = flagStoreSrc.slice(
  flagStoreSrc.indexOf('const LAUNCHED_FLAG_DEFAULTS'),
  flagStoreSrc.indexOf('};', flagStoreSrc.indexOf('const LAUNCHED_FLAG_DEFAULTS')),
);
assert(
  !/trade\.standing_offers/.test(launchedBlock),
  '#362 SC-14b — the dark flag is ABSENT from LAUNCHED_FLAG_DEFAULTS',
  'that map fails OPEN — listing a dark flag lights the feature on a first ' +
    'boot or a failed revalidate',
);

console.log('');
console.log('═'.repeat(72));
console.log('12 — every client event exists in the backend taxonomy');
console.log('═'.repeat(72));

// SC-15 — an event name the taxonomy does not carry is dropped on ingest
// with no client-side error. Cross-check the literals the client actually
// emits against backend/analytics_taxonomy.py.
const taxonomySrc = read(path.join(REPO, 'backend/analytics_taxonomy.py'));
const emitted = new Set();
for (const f of srcFiles()) {
  const src = stripComments(read(f));
  for (const m of src.matchAll(/track\(\s*'(standing_offer_[a-z_]+)'/g)) {
    emitted.add(m[1]);
  }
}
assert(
  emitted.size >= 3,
  '#362 SC-15a — the client emits the standing-offer events',
  `found ${[...emitted].join(', ') || 'none'}`,
);
for (const name of [...emitted].sort()) {
  assert(
    new RegExp(`"${name}"`).test(taxonomySrc),
    `#362 SC-15b — '${name}' is registered in backend/analytics_taxonomy.py`,
    'an unregistered client event is dropped on ingest, silently, and the ' +
      'health metric it was added for reads zero forever',
  );
}
// The server-fired one must NOT be emitted by the client.
assert(
  !emitted.has('standing_offer_card_shown'),
  '#362 SC-15c — the client does not emit the SERVER-fired card_shown event',
  'double-firing it inflates the impression count by exactly one per card',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All standing-offer (#362) checks passed.');
