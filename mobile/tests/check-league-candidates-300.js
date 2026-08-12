#!/usr/bin/env node
// League position trade candidates — feedback #300.
//
// Frozen design: docs/feedback/items/300-league-rankings-trade-candidates/
// operator-answers-2026-08-12.md. Mockups: mockups/candidates-300-v2/.
//
// WHY THIS EXISTS. Almost nothing #300 adds fails loudly. The divider is a
// hairline and a caption: drawn one row off, drawn against the wrong sort,
// or drawn with the Buyer and Seller labels transposed, it looks exactly as
// correct as the right version and a screenshot cannot tell them apart. The
// handoff is worse — a route-param preselection compiles, demos correctly
// with `trades.sheet_targeting` off, and silently no-ops in production,
// which is the shipped configuration. And the 44pt treatment is a claim
// about hit-testing through ancestors that no static tool can measure, so
// what this file pins is the STRUCTURE the claim rests on: outermost
// Pressable, no nested control, non-overlapping slop.
//
// Every assertion below names the sabotage it detects. Assertions of the
// form "X appears nowhere" read COMMENT-STRIPPED source — the comments in
// LeagueSummaryScreen.tsx deliberately name the constructs they forbid
// (route params, nested controls, raw numerics), which is exactly how a
// previous round shipped four tests that could not fail.
//
// Run: node tests/check-league-candidates-300.js

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

const ROOT = path.join(__dirname, '..');
function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), 'utf8');
}
function parse(rel) {
  const file = path.join(ROOT, rel);
  return ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
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
function findAll(root, pred) {
  const out = [];
  walk(root, (n) => {
    if (pred(n)) out.push(n);
  });
  return out;
}
function tagOf(node) {
  if (ts.isJsxSelfClosingElement(node)) return node.tagName.getText();
  if (ts.isJsxElement(node)) return node.openingElement.tagName.getText();
  return null;
}
function findTag(root, tag) {
  return findAll(root, (n) => tagOf(n) === tag);
}
/** The initializer text of `const <name> = …`, comments stripped. */
function declText(src, name) {
  const d = findAll(
    src,
    (n) => ts.isVariableDeclaration(n) && n.name.getText() === name,
  )[0];
  return d ? stripComments(d.getText()) : null;
}
/** The JSX attribute node named `attr` on `node`, or null. */
function propNode(node, attr) {
  const opening = ts.isJsxSelfClosingElement(node) ? node : node.openingElement;
  for (const a of opening.attributes.properties) {
    if (ts.isJsxAttribute(a) && a.name && a.name.getText() === attr) return a;
  }
  return null;
}
function propText(node, attr) {
  const a = propNode(node, attr);
  return a ? stripComments(a.getText()) : null;
}
const countOf = (text, needle) => text.split(needle).length - 1;

const SCREEN_REL = 'src/screens/LeagueSummaryScreen.tsx';
const CARD_REL = 'src/components/PlayerCard.tsx';
const FLAGS_REL = 'src/state/useFeatureFlags.ts';
const API_REL = 'src/api/league.ts';

const screenSrc = parse(SCREEN_REL);
const screenText = read(SCREEN_REL);
const screenCode = stripComments(screenText);
const cardText = read(CARD_REL);
const cardCode = stripComments(cardText);
const flagsCode = stripComments(read(FLAGS_REL));
const apiText = read(API_REL);

// ═══════════════════════════════════════════════════════════════════════
// 1. The two flags exist in BOTH places, and are DARK in both
// ═══════════════════════════════════════════════════════════════════════
//
// `revalidateFlags` replaces the whole map (`set({ flags })`), so a key that
// lives in only one of client-defaults / server-config disagrees with itself
// across the first two paints. Registering both, false, is what makes the
// dark launch actually dark at every moment of the boot.

const defaultsBlock = (flagsCode.match(
  /const LAUNCHED_FLAG_DEFAULTS: FlagMap = \{([\s\S]*?)\n\};/,
) || [])[1];
assert(!!defaultsBlock, 'LAUNCHED_FLAG_DEFAULTS is findable');
for (const key of ['league.pos_candidates', 'league.player_trade_handoff']) {
  assert(
    !!defaultsBlock && new RegExp(`'${key.replace('.', '\\.')}': false`).test(defaultsBlock),
    `#300 '${key}' is registered FALSE in LAUNCHED_FLAG_DEFAULTS`,
    'sabotage detected: flipping it to true, or deleting the line and letting the key exist server-side only',
  );
}
assert(
  !!defaultsBlock &&
    !/'league\.(pos_candidates|player_trade_handoff)': true/.test(defaultsBlock),
  '#300 neither #300 flag is baked ON',
  'sabotage detected: a dark feature that paints for one frame before the server says no',
);

// ═══════════════════════════════════════════════════════════════════════
// 2. `medians` is OPTIONAL, and the divider refuses to draw without it
// ═══════════════════════════════════════════════════════════════════════
//
// The client can compute the median VALUE exactly — every team's
// positions[P].value is on the wire — but not its pick-tier LABEL, and a raw
// numeric is not an allowed fallback on this screen. So the field is a
// precondition, not a hint.

assert(
  /medians\?: Partial<[\s\S]{0,200}?value_label\?: string/.test(apiText),
  '#300 `medians` is optional on PowerRankingsResponse, with an optional value_label',
  'a required field would make every pre-#300 server payload a type error, and the client must degrade, not throw',
);

const medianDecl = declText(screenSrc, 'medianAtPos');
assert(
  !!medianDecl && /query\.data\?\.medians\?\.\[candidatePos\] \?\? null/.test(medianDecl),
  '#300 the median comes from the SERVER payload only',
  'sabotage detected: computing a client-side median so the line always draws — the position would be right and the label fabricated',
);

const cutDecl = declText(screenSrc, 'cutAfter');
assert(
  !!cutDecl && /if \(!candidatePos \|\| !medianAtPos\) return null;/.test(cutDecl),
  '#300 no median on the wire ⇒ no divider',
  'sabotage detected: dropping the guard draws a line at a boundary nothing on the wire defines',
);

// ═══════════════════════════════════════════════════════════════════════
// 3. The divider only draws where the list is SORTED by what it measures
// ═══════════════════════════════════════════════════════════════════════
//
// This is the assertion that stops the line from being confidently wrong. A
// median line across a ranked list is only true if the ranking is by the same
// quantity. Three conditions make that so and each has its own silent failure.

const candidatePosDecl = declText(screenSrc, 'candidatePos');
assert(!!candidatePosDecl, '#300 `candidatePos` is findable');
assert(
  !!candidatePosDecl && /if \(!posCandidatesOn\) return null;/.test(candidatePosDecl),
  '#300 the divider is gated on `league.pos_candidates`',
  'sabotage detected: dropping the flag read ships a dark feature to everyone',
);
assert(
  !!candidatePosDecl && /if \(subset !== 'all'\) return null;/.test(candidatePosDecl),
  '#300 no divider outside the All subset',
  "sabotage detected: starters/bench RE-DERIVE posValues[P] from part of the roster while the server's median is over the whole one — the line would compare two different populations",
);
assert(
  !!candidatePosDecl && /if \(posFilter\.has\('PICKS'\)\) return null;/.test(candidatePosDecl),
  '#300 no divider while draft capital is in the filter',
  "sabotage detected: `activeTotal` ADDS picks.value when PICKS is selected, so the list would be ranked by WR+capital while the median measures WR alone. This is the ROUTINE state under league.picks_always_counted's auto-add rule — the most reachable wrong line there is",
);
assert(
  !!candidatePosDecl && /return core\.length === 1 \? core\[0\] : null;/.test(candidatePosDecl),
  '#300 exactly ONE core position, never a multi-select',
  'sabotage detected: `core.length >= 1` draws a line for "WR + TE", which is a median of nothing anyone trades for (operator decision 5)',
);

// The at-median team lands on the SELLER side — it is a seller by arithmetic
// (nothing is above it that it is not), and mock D2-b draws the line below it.
assert(
  !!cutDecl && /posValues\[candidatePos\] >= medianAtPos\.value/.test(cutDecl),
  '#300 an exactly-at-median team sits ABOVE the line (`>=`, not `>`)',
  'sabotage detected: `>` moves the odd-count median team to the buyer side, contradicting the drawn design',
);
assert(
  !!cutDecl && /return n > 0 && n < ranked\.length \? n : null;/.test(cutDecl),
  '#300 the divider refuses to draw at either end of the list',
  'sabotage detected: dropping the bound draws a caption below the last row of a perfectly flat league, marking no boundary at all',
);

// ═══════════════════════════════════════════════════════════════════════
// 4. Bands: round(count * 0.33), and NOT transposed
// ═══════════════════════════════════════════════════════════════════════
//
// Resolved sizes the operator signed off (buyers / unlabelled / sellers):
// 8 → 3/2/3 · 10 → 3/4/3 · 12 → 4/4/4 · 14 → 5/4/5.

const bandSizeDecl = declText(screenSrc, 'bandSize');
assert(
  !!bandSizeDecl && /Math\.round\(ranked\.length \* 0\.33\)/.test(bandSizeDecl),
  '#300 the band is `Math.round(count * 0.33)`',
  'sabotage detected: 0.25 (the superseded round-1 figure) gives 2/4/2 · 3/4/3 · 3/6/3 · 4/6/4; Math.floor gives 2/4/2 on a 8-team league',
);
// Independent arithmetic check of the sizes the operator actually enumerated,
// so the constant above is pinned to its CONSEQUENCES and not just its digits.
for (const [teams, expected] of [[8, 3], [10, 3], [12, 4], [14, 5]]) {
  assert(
    Math.round(teams * 0.33) === expected,
    `#300 a ${teams}-team league bands ${expected}/${teams - 2 * expected}/${expected}`,
  );
}

const bandForDecl = declText(screenSrc, 'bandFor');
assert(!!bandForDecl, '#300 `bandFor` is findable');
assert(
  !!bandForDecl && /if \(idx < bandSize\) return 'Seller';/.test(bandForDecl),
  '#300 the TOP of the list is labelled Seller',
  "sabotage detected: transposing the two labels. This is the catastrophic silent bug — the league's richest team at the position reads 'Buyer', the screenshot looks perfect, and every user acts on the inverse of the truth",
);
assert(
  !!bandForDecl && /if \(idx >= ranked\.length - bandSize\) return 'Buyer';/.test(bandForDecl),
  '#300 the BOTTOM of the list is labelled Buyer',
  'sabotage detected: as above, in the other direction',
);
assert(
  !!bandForDecl && /if \(bandSize <= 0 \|\| bandSize \* 2 > ranked\.length\) return null;/.test(bandForDecl),
  '#300 the two bands can never overlap',
  'sabotage detected: on a tiny league the two ranges would intersect and a row would be both a Buyer and a Seller',
);

// ═══════════════════════════════════════════════════════════════════════
// 5. THE LABELS DRIVE NO BEHAVIOUR — the LINE is the direction rule
// ═══════════════════════════════════════════════════════════════════════
//
// Operator decision 8 + still-open item 5, resolved as option (a): the median
// line is the direction rule for EVERY team including the unlabelled middle,
// and the Buyer/Seller labels are emphasis layered on top. The moment any
// behaviour reads a band, the middle third silently becomes inert — which is
// the option the operator explicitly did not take.

const bandForUses = countOf(screenCode, 'bandFor(');
assert(
  bandForUses === 1,
  '#300 `bandFor` is consumed exactly once',
  `saw ${bandForUses} — sabotage detected: a second consumer is behaviour reading a label that is documented as carrying none`,
);
assert(
  /band=\{bandFor\(idx\)\}/.test(screenCode),
  "#300 `bandFor`'s single consumer is the TeamRow caption prop",
  'sabotage detected: routing it anywhere else',
);

const dirDecl = declText(screenSrc, 'candidateDir');
assert(!!dirDecl, '#300 `candidateDir` is findable');
assert(
  !!dirDecl && /selectedIdx < cutAfter/.test(dirDecl) && !/bandFor|bandSize/.test(dirDecl),
  '#300 the drill-in direction is decided by the LINE, never by a band',
  'sabotage detected: gating direction on Buyer/Seller leaves the unlabelled middle with no direction and no drill-in — 4 teams in every common league size',
);
assert(
  !!dirDecl && /!selected\.tc\.team\.is_you/.test(dirDecl),
  "#300 the caller's OWN row never enters candidate mode",
  'sabotage detected: dropping it offers the user their own players to themselves',
);
assert(
  !!dirDecl && /myEntry &&/.test(dirDecl),
  '#300 no direction when the caller has no team in this league',
  'sabotage detected: "offer yours" with no `yours` renders an empty roster under an instruction to tap it',
);
assert(
  !!dirDecl && /candidateHandoffOn &&/.test(dirDecl),
  '#300 the drill-in handoff needs BOTH flags',
  'sabotage detected: `player_trade_handoff` alone has no line to take a direction from',
);

// ═══════════════════════════════════════════════════════════════════════
// 6. The handoff: the PIN STORE, replacing, and never route params
// ═══════════════════════════════════════════════════════════════════════

const actionDecl = declText(screenSrc, 'handleRowAction');
assert(!!actionDecl, '#300 `handleRowAction` is findable');
assert(
  /store\.setSide\('give', verb === 'offer' \? \[player\] : \[\]\);/.test(actionDecl || '') &&
    /store\.setSide\('receive', verb === 'target' \? \[player\] : \[\]\);/.test(actionDecl || ''),
  '#300 BOTH pin sides are replaced on every action',
  'sabotage detected: setting only the acting side lets a stale pin from earlier in the session ride into the generated deck, which is a trade the user never asked for',
);
assert(
  !/addGive|addReceive/.test(screenCode),
  '#300 the handoff REPLACES pins, it does not add to them',
  'sabotage detected: addGive/addReceive accumulate — the operator asked for replace',
);
assert(
  /navigation\.navigate\('Trades', \{ screen: 'TradesHome' \}\)/.test(actionDecl || ''),
  '#300 the handoff routes to the shipped Trades landing',
  'sabotage detected: navigating to an unrouted or mode-scoped destination',
);
// The failure the orchestrator called out by name: a params-based handoff
// compiles, demos correctly with flags off, and silently no-ops in production
// because `trades.sheet_targeting` is ON and TradesScreen reads sheet-local
// state, not route.params.
assert(
  !/(pinned|prefill|targets|playerId|player_id)\s*:/.test(
    (actionDecl || '').replace(/const player: Player = \{[\s\S]*?\};/, ''),
  ),
  '#300 nothing is preselected through route params',
  'sabotage detected: handing the player off as a nav param — it type-checks, it demos, and it does nothing in the shipped flag configuration',
);

// ═══════════════════════════════════════════════════════════════════════
// 7. The 44pt treatment: one focusable, unclipped slop, non-overlapping rows
// ═══════════════════════════════════════════════════════════════════════
//
// NOT PROVEN, PINNED. RN hit-testing through non-clipping ancestors has not
// been exercised on a simulator for this surface (see the QA checklist). What
// is testable is the structure the claim depends on, and every part of it has
// a plausible "cleanup" that quietly removes it.

assert(
  /const ROW_HIT_SLOP = \{ top: 6, bottom: 6, left: 6, right: 6 \} as const;/.test(screenText),
  '#300 the slop is 6pt on each vertical edge (32 + 6 + 6 = 44)',
  'sabotage detected: shrinking it leaves a sub-44pt target that no screenshot shows',
);
assert(
  /rosterRowActionable: \{ marginBottom: 12 \}/.test(screenText),
  '#300 actionable rows sit on a 12pt margin so slop regions do not overlap',
  "sabotage detected: reverting to the shipped 4pt makes adjacent rows' touch areas overlap by 8pt, and taps near a boundary fire the WRONG player — invisible in every screenshot and in every Maestro id-tap",
);
assert(
  /rosterRow: \{ marginBottom: space\.xs \}/.test(screenText),
  '#300 INERT rows keep the shipped 4pt margin',
  'sabotage detected: applying 12 unconditionally re-inflates the drill-in #299 just compacted, for rows that need no touch target',
);

const screenCards = findTag(screenSrc, 'PlayerCard');
assert(screenCards.length === 1, '#300 still exactly one PlayerCard site on this screen');
if (screenCards.length === 1) {
  const card = screenCards[0];
  assert(
    /hitSlop=\{sec\.verb \? ROW_HIT_SLOP : undefined\}/.test(propText(card, 'hitSlop') || ''),
    '#300 slop is applied only to rows that actually do something',
  );
  assert(
    /onPress=\{\s*sec\.verb \? \(\) => handleRowAction\(r, sec\.verb!\) : undefined\s*\}/.test(
      (propText(card, 'onPress') || '').replace(/\s+/g, ' ').replace(/ \}/g, ' }'),
    ) || /sec\.verb \? \(\) => handleRowAction\(r, sec\.verb!\) : undefined/.test(propText(card, 'onPress') || ''),
    '#300 the row press is the handoff, and only on actionable rows',
    'sabotage detected: an unconditional onPress makes the inert drill-in tappable at 32pt, reversing #299',
  );
  assert(
    /denseMicroTags=\{!sec\.verb\}/.test(propText(card, 'denseMicroTags') || ''),
    '#300 Variant D applies ONLY to rows carrying the verb',
    'sabotage detected: dropping the tags unconditionally pays the information price on the inert drill-in, which has no label to fit',
  );
  // The whole row is the button. A nested control cannot work here:
  // styles.card has overflow:'hidden' so a child's hit area is clipped, and
  // the dense Pressable's accessible:true hides a child from VoiceOver AND
  // from Maestro id-selectors (flow-authoring law 3).
  const slot = propNode(card, 'rightSlot');
  assert(
    !!slot && findTag(slot, 'Pressable').length === 0 &&
      findTag(slot, 'TouchableOpacity').length === 0,
    '#300 the row affordance is DECORATION, not a nested control',
    "sabotage detected: making 'Offer' its own Pressable. Its hit area is clipped by the parent's overflow:'hidden' so it can never reach 44pt, and the tile's accessible:true hides it from VoiceOver and from Maestro",
  );
}

// PlayerCard's half of the contract: the slop must land on the tile's OWN
// outermost Pressable — that is the only position from which it extends into
// unclipped ancestors instead of trying to escape a clipped parent.
assert(
  /delayLongPress=\{commandLongPressMs\}\s*\n\s*hitSlop=\{hitSlop\}\s*\n\s*\{\.\.\.a11yProps\}\s*\n\s*style=\{\(\{ pressed \}\) => \[\s*\n\s*styles\.card,\s*\n\s*styles\.cardDense,/
    .test(cardText),
  '#300 PlayerCard applies `hitSlop` to the dense branch OUTERMOST Pressable',
  'sabotage detected: threading it to an inner View — the slop is then clipped by styles.card and buys nothing',
);

// ═══════════════════════════════════════════════════════════════════════
// 8. Variant D is VISUAL ONLY — VoiceOver keeps both facts
// ═══════════════════════════════════════════════════════════════════════
//
// The operator overrode the lab to fit a visible verb. The override is a
// LAYOUT trade on a 32pt row; the a11y utterance has no width, so there is no
// reason to pay the price twice.

assert(
  /denseMicroTags = true,/.test(cardText),
  '#300 `denseMicroTags` defaults TRUE',
  'sabotage detected: defaulting false silently strips the tags from the Tiers board and the FA list, which never asked for Variant D',
);
assert(
  /\{isRookie && denseMicroTags &&/.test(cardText) &&
    /\{injury && denseMicroTags \?/.test(cardText),
  '#300 the prop gates BOTH micro-tags',
  'sabotage detected: gating one leaves the row wider than measured and the verb truncates the name it was meant to save',
);
const labelDecl = (cardCode.match(/const composedLabel =[\s\S]*?\.join\(', '\);/) || [])[0];
assert(
  !!labelDecl &&
    /isRookie \? 'rookie' : null/.test(labelDecl) &&
    /injury \? `injury \$\{injCode \?\? injury\}` : null/.test(labelDecl) &&
    !/denseMicroTags/.test(labelDecl),
  '#300 the composed a11y label still speaks rookie and injury',
  'sabotage detected: gating the utterance on the visual prop turns a measured layout trade into an accessibility regression nobody asked for',
);

// ═══════════════════════════════════════════════════════════════════════
// 9. Pick tiers, never numbers — on the line and on the rows
// ═══════════════════════════════════════════════════════════════════════

const captionDecl = declText(screenSrc, 'medianCaption');
assert(!!captionDecl, '#300 `medianCaption` is findable');
assert(
  !!captionDecl &&
    /medianAtPos\?\.value_label/.test(captionDecl) &&
    !/toLocaleString|fmtK|Math\.round|medianAtPos\.value\b/.test(captionDecl),
  '#300 the divider carries a PICK-TIER label and never a number',
  'sabotage detected: falling back to the numeric median. The value is right there on the payload, which is exactly why this needs pinning — #277/#279 removed numeric values from this screen',
);
assert(
  !!captionDecl && /: 'League median'/.test(captionDecl),
  '#300 no `value_label` ⇒ the bare "League median" line, not a hidden divider',
  "sabotage detected: hiding the line for everyone outside the aggregate_tier_labels experiment. The line's POSITION is computable; only its value is not",
);

// Operator decision 6 — the filtered views were falling back to a raw numeric,
// which contradicts the no-numeric-values ruling. The single-position case is
// exactly describable by a label already on the wire.
const labelFnDecl = declText(screenSrc, 'activeValueLabel');
assert(!!labelFnDecl, '#300 `activeValueLabel` is findable');
assert(
  !!labelFnDecl &&
    /if \(subset === 'all' && posFilter\.size === 0\) return tc\.team\.total_value_label;/.test(labelFnDecl),
  '#300 the unfiltered view keeps its shipped total label',
);
assert(
  !!labelFnDecl &&
    /if \(posCandidatesOn && candidatePos\) \{/.test(labelFnDecl) &&
    /return tc\.team\.positions\?\.\[candidatePos\]\?\.value_label;/.test(labelFnDecl),
  "#300 a single-position filter now shows THAT position's pick-tier label",
  'sabotage detected: reverting leaves every filtered row on the raw numeric — the exact contradiction operator decision 6 was raised to fix',
);
assert(
  countOf(screenCode, 'activeValueLabel(') === 2,
  '#300 both value surfaces read the SAME label derivation',
  `saw ${countOf(screenCode, 'activeValueLabel(')} call sites — expected the ranked row and the drill-in subline. Two derivations is how a row and its own drill-in come to disagree`,
);
assert(
  /totalLabel=\{activeValueLabel\(r\.tc\)\}/.test(screenCode) &&
    /activeValueLabel\(selected\.tc\) \|\|/.test(screenCode),
  '#300 the two call sites are the ranked row and the drill-in subline',
  'sabotage detected: leaving either one on its old inline expression',
);

// ═══════════════════════════════════════════════════════════════════════
// 10. The divider is the SHIPPED cutline construction — zero new patterns
// ═══════════════════════════════════════════════════════════════════════

const divider = findAll(
  screenSrc,
  (n) =>
    tagOf(n) === 'View' &&
    /testID="league-summary\.median-divider"/.test(
      (ts.isJsxElement(n) ? n.openingElement : n).getText(),
    ),
)[0];
assert(!!divider, '#300 the median divider element is findable by its testID');
if (divider) {
  const inner = divider.getText();
  assert(
    countOf(inner, 'styles.oddsCutRule') === 2 && /styles\.oddsCutText/.test(inner),
    '#300 the divider reuses the playoff cutline\'s rule + label styles verbatim',
    'sabotage detected: inventing a parallel rule/label pair. The playoff cutline is already this screen\'s way of marking a threshold across a ranked list; a second construction is a second thing to keep in sync',
  );
  assert(
    /accessibilityLabel=/.test(inner),
    '#300 the divider is announced to VoiceOver',
    'sabotage detected: a rule-label-rule band reads as three unrelated fragments without one',
  );
}
assert(
  /\{cutAfter === idx \+ 1 \? \(/.test(screenCode),
  '#300 the divider is placed by `cutAfter`, inline in the ranked list',
  'sabotage detected: rendering it above or below the whole list, where it marks nothing',
);

// ═══════════════════════════════════════════════════════════════════════
// 11. The auto-return uses the ONE exit choke point
// ═══════════════════════════════════════════════════════════════════════
//
// mobile/tests/check-analytics-297-302.js pins that exactly one bare
// setSelectedId(null) exists and that it lives inside closeTeam. #300 adds a
// sixth way to leave the drill-in, and it is the first AUTOMATIC one — the
// tempting shortcut is to clear focus directly and skip the event.

assert(
  countOf(screenCode, "closeTeam('filter_change')") === 1,
  "#300 the filter-change ejection routes through closeTeam exactly once",
  'sabotage detected: a bare setSelectedId(null) — the exit disappears from analytics while the UI keeps working',
);
assert(
  countOf(screenCode, 'setSelectedId(null)') === 1,
  '#300 there is still exactly ONE bare setSelectedId(null) in the file',
);
assert(
  /\|\s*'filter_change';/.test(screenText),
  "#300 'filter_change' is a distinct CloseVia value",
  "sabotage detected: reusing 'header_back'. One is a choice and one is an ejection; a funnel that cannot tell them apart reads every filter tap as the user giving up on the team",
);
assert(
  /AccessibilityInfo\.announceForAccessibility/.test(screenCode),
  '#300 the automatic return is announced',
  'sabotage detected: clearing focus silently moves VoiceOver to a different screen with no explanation',
);
const sigEffect = (screenCode.match(
  /const sig = `\$\{subset\}\|[\s\S]*?\}, \[subset, posFilter, posCandidatesOn, closeTeam\]\);/,
) || [])[0];
assert(
  !!sigEffect && /if \(prev === null \|\| prev === sig\) return;/.test(sigEffect),
  '#300 the auto-return fires on a real CHANGE, never on mount',
  'sabotage detected: dropping the first-observation guard ejects a user who lands already focused',
);
assert(
  !!sigEffect && /if \(!posCandidatesOn\) return;/.test(sigEffect),
  '#300 the auto-return is behind the flag',
  'sabotage detected: an unflagged behaviour change on the shipped screen',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All #300 league trade-candidate checks passed.');
