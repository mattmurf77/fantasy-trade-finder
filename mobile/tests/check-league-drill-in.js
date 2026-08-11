#!/usr/bin/env node
// League drill-in regression test — feedback #299 (tile density) + #302
// (back affordance).
//
// WHY THIS EXISTS. Both fixes are STRUCTURAL claims about a shared primitive
// and a navigator slot, and both have a failure mode that looks fine in
// review and is invisible in a screenshot:
//
//   #299 halves the League roster tile by moving the tier badge out of the
//   dense row's line 2 and into the right cluster. `PlayerCard` is shared —
//   the Tiers board's rows are pressable AND drag-liftable (44pt binds) and
//   the Tiers/FreeAgents callers pass a `statsSlot` that line 2 exists to
//   hold. So the change is gated behind an OPT-IN prop, and the thing worth
//   pinning is not the new layout but the BLAST RADIUS: that the shared
//   branch still measures 60pt and that no other caller opts in.
//
//   #302 moves the drill-in exit onto the fixed stack header and registers
//   the Android back handler that never existed. A `setOptions` effect and a
//   `BackHandler` are both easy to "clean up" — and the screen looks
//   identical at scroll 0, which is the only place anyone checks.
//
// A grep is not enough for most of this: the regressions worth catching are
// a prop threaded but never applied, a style declared but never used, a badge
// dropped rather than relocated, and a conditional that inverts. So this
// parses the real TSX with the project's own TypeScript and walks the JSX,
// the same way check-member-entered-marker.js and check-mock-mode-marker.js
// do.
//
// Run: node tests/check-league-drill-in.js

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
function ok(name) {
  console.log(`PASS  ${name}`);
}
function fail(name, detail) {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
}
function assert(cond, name, detail) {
  if (cond) ok(name);
  else fail(name, detail);
}

function read(rel) {
  return fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');
}
function parse(rel) {
  const file = path.join(__dirname, '..', rel);
  return ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
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
function propsOf(node) {
  const opening = ts.isJsxSelfClosingElement(node) ? node : node.openingElement;
  const names = new Set();
  for (const a of opening.attributes.properties) {
    if (ts.isJsxAttribute(a) && a.name) names.add(a.name.getText());
  }
  return names;
}
/** The condition of the INNERMOST conditional (`? :` or `&&`) that wraps
 *  `node` — and only that one.
 *
 *  This deliberately does NOT accumulate ancestor conditions. An earlier
 *  version walked six parents and concatenated them, and it FALSE-PASSED the
 *  sabotage that makes the relocated tier badge unconditional: the badge sits
 *  inside the cluster's own `posRank || (denseSingleLine && tier) ? …`
 *  ternary, so the ancestor text contained "denseSingleLine" no matter what
 *  the badge's own gate said. A gate assertion has to read the gate. */
function nearestConditionText(node) {
  for (let p = node.parent; p; p = p.parent) {
    if (ts.isConditionalExpression(p)) return p.condition.getText();
    if (
      ts.isBinaryExpression(p) &&
      p.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken
    ) {
      return p.left.getText();
    }
    // Don't escape the enclosing element: if we reach a JSX element boundary
    // without finding a conditional, this node is unconditional.
    if (ts.isJsxElement(p) || ts.isJsxFragment(p)) return '';
  }
  return '';
}

const CARD_REL = 'src/components/PlayerCard.tsx';
const SCREEN_REL = 'src/screens/LeagueSummaryScreen.tsx';
const cardSrc = parse(CARD_REL);
const cardText = read(CARD_REL);
const screenSrc = parse(SCREEN_REL);
const screenText = read(SCREEN_REL);

// ═══════════════════════════════════════════════════════════════════════
// #299 — 1. The opt-in prop exists and is actually wired to the height
// ═══════════════════════════════════════════════════════════════════════

assert(
  /denseSingleLine\?: boolean;/.test(cardText),
  '#299 PlayerCard declares the `denseSingleLine` prop',
);

// The decided geometry: 60pt → 32pt. 32 is derived, not taste — the tallest
// thing on the row is the TierChalkBadge (Badge at type.label lineHeight 14 +
// paddingVertical 2×2 + borderWidth 1×2 = 20pt) plus 6pt above and below.
assert(
  /cardDenseSingle:\s*\{[^}]*height:\s*32\b/.test(cardText),
  '#299 `cardDenseSingle` is height 32',
  'the operator decided 32pt (−47%); 30pt was rejected because it forks the shared Badge primitive',
);

// A prop that is threaded but never applied reads as wired in review and
// leaves the tile at 60pt on screen. Pin the application, not just the style.
assert(
  /styles\.cardDense,\s*\n\s*denseSingleLine && styles\.cardDenseSingle,/.test(cardText),
  '#299 `cardDenseSingle` is applied in the dense branch style array',
  'declared-but-unused would leave every League tile at 60pt with the prop passed',
);

// ═══════════════════════════════════════════════════════════════════════
// #299 — 2. BLAST RADIUS: the shared dense row is untouched
// ═══════════════════════════════════════════════════════════════════════
//
// This is the check that matters. The tempting "simplification" is to drop
// the prop and shrink `cardDense` itself. That would halve the Tiers board's
// rows — which ARE pressable and drag-liftable, so the 44pt touch minimum
// binds — and squeeze out the `statsSlot` those callers pass.

assert(
  /cardDense:\s*\{\s*\n\s*height:\s*60,/.test(cardText),
  '#299 the shared dense row is STILL 60pt',
  'shrinking cardDense itself breaks the Tiers board (44pt touch target) and the FA list (statsSlot)',
);

for (const rel of ['src/screens/TiersScreen.tsx', 'src/screens/FreeAgentsScreen.tsx']) {
  const other = read(rel);
  assert(
    other.includes('dense'),
    `#299 ${rel} is still a dense PlayerCard caller (guard is meaningful)`,
  );
  assert(
    !other.includes('denseSingleLine'),
    `#299 ${rel} does NOT opt in to the single-line row`,
    'these rows are pressable/draggable and pass a statsSlot — the 32pt row has no line 2 to hold it',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// #299 — 3. Nothing is dropped: line 2 goes away, the tier badge RELOCATES
// ═══════════════════════════════════════════════════════════════════════

const line2 = findAll(
  cardSrc,
  (n) =>
    tagOf(n) === 'View' &&
    /styles\.denseLine2/.test((ts.isJsxElement(n) ? n.openingElement : n).getText()),
)[0];
assert(!!line2, '#299 the dense line-2 View is findable');
if (line2) {
  assert(
    /denseSingleLine/.test(nearestConditionText(line2)),
    '#299 line 2 renders only when NOT in single-line mode',
    'an unconditional line 2 inside a 32pt box clips the tier badge',
  );
}

// The badge must reappear in the right cluster. If it does not, the fix
// silently DELETES the tier value — the one thing the operator's spec says
// must survive.
const cluster = findAll(
  cardSrc,
  (n) =>
    tagOf(n) === 'View' &&
    /styles\.denseNumsRow/.test((ts.isJsxElement(n) ? n.openingElement : n).getText()),
)[0];
assert(
  !!cluster,
  '#299 the right cluster has a single-line (row) variant',
  'styles.denseNumsRow lays the cluster out horizontally so the badge can sit beside posRank',
);
if (cluster) {
  const badges = findTag(cluster, 'TierChalkBadge');
  assert(
    badges.length === 1,
    '#299 the tier badge is rendered INSIDE the right cluster',
    'dropping line 2 without relocating the badge deletes the tier value from the screen',
  );
  if (badges.length === 1) {
    assert(
      /denseSingleLine/.test(nearestConditionText(badges[0])),
      '#299 the relocated badge is gated on `denseSingleLine`',
      'unconditional would double-render the badge for Tiers/FA rows, which still have it on line 2',
    );
    // The operator's words: "presenting it to the left of the position".
    const posRank = findAll(
      cluster,
      (n) =>
        tagOf(n) === 'Text' &&
        /styles\.densePosRank/.test((ts.isJsxElement(n) ? n.openingElement : n).getText()),
    )[0];
    assert(!!posRank, '#299 posRank is rendered inside the right cluster');
    if (posRank) {
      assert(
        badges[0].getStart() < posRank.getStart(),
        '#299 the tier badge is LEFT of the positional rank',
        'the operator asked for the tier value "to the left of the position"',
      );
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════
// #299 — 4. The League screen opts in; the picks rows keep proportion
// ═══════════════════════════════════════════════════════════════════════

const rosterCards = findTag(screenSrc, 'PlayerCard');
assert(
  rosterCards.length === 1,
  '#299 LeagueSummaryScreen renders exactly one PlayerCard site',
  `found ${rosterCards.length}`,
);
if (rosterCards.length === 1) {
  const props = propsOf(rosterCards[0]);
  assert(props.has('dense'), '#299 the League roster tile is a dense PlayerCard');
  assert(
    props.has('denseSingleLine'),
    '#299 the League roster tile opts in to the 32pt single-line row',
  );
}

// Draft-capital rows are NOT PlayerCards, so they do not shrink with the
// tiles. Left at 40 they read as conspicuously tall beside a 32pt roster.
assert(
  /pickRow:\s*\{[^}]*minHeight:\s*32\b/.test(screenText),
  '#299 the draft-capital rows are in proportion with the new tile (minHeight 32)',
  'they were 40 — a 25% taller row sitting directly under the shrunken roster',
);

// ═══════════════════════════════════════════════════════════════════════
// #302 — 5. The exit lives on the FIXED header, not in the scrolling card
// ═══════════════════════════════════════════════════════════════════════

assert(
  /headerLeft:\s*\(\)\s*=>\s*\(\s*\n\s*<Pressable\s*\n\s*testID="league-summary\.roster-close"/.test(
    screenText,
  ),
  '#302 the back control is mounted as the stack header\'s `headerLeft`',
  'in the chart card it sat above 1,600pt of roster and scrolled away — that IS the bug',
);
assert(
  /headerTitle:\s*\(\)\s*=>\s*<StackHeaderTitle>\{focusedTeamName\}<\/StackHeaderTitle>/.test(
    screenText,
  ),
  '#302 the header title swaps to the focused team name',
  'answers "which team am I looking at?" at any scroll depth',
);
assert(
  /headerLeft:\s*undefined/.test(screenText),
  '#302 clearing focus restores the bare tab-root header',
  'a stale "All teams" control on the all-teams view is a back button to nowhere',
);

// The header swap must NOT run on the legacy root-stack registration, whose
// headerLeft is the explicit JS back control that exists because native back
// is dead over headerShown:false (RNS#3294). Overwriting it strips that
// screen's only exit and it cannot be restored from here.
const setOptionsCall = findAll(
  screenSrc,
  (n) =>
    ts.isCallExpression(n) && n.expression.getText() === 'navigation.setOptions',
)[0];
assert(!!setOptionsCall, '#302 a navigation.setOptions call exists');
if (setOptionsCall) {
  let fn = setOptionsCall;
  while (fn && !ts.isArrowFunction(fn) && !ts.isFunctionExpression(fn)) fn = fn.parent;
  assert(
    !!fn && /if \(!isTabRoot\) return;/.test(fn.getText()),
    '#302 the header swap is scoped to the TAB ROOT registration',
    'the root-stack push (RootNav) owns its own headerLeft — overwriting it removes that screen\'s back control',
  );
}

// Exactly one back control on screen: the in-card link survives only on the
// registration that does NOT get the header swap.
const inCardBack = findAll(
  screenSrc,
  (n) =>
    tagOf(n) === 'Pressable' &&
    /styles\.backLink/.test((ts.isJsxElement(n) ? n.openingElement : n).getText()),
)[0];
assert(!!inCardBack, '#302 the in-card back link still exists for the root-stack push');
if (inCardBack) {
  assert(
    /!isTabRoot/.test(nearestConditionText(inCardBack)),
    '#302 the in-card back link does NOT render on the tab root',
    'it would be a second, duplicate back control — and a duplicate testID on screen',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// #302 — 6. Android back, and the tab re-tap, actually leave the drill-in
// ═══════════════════════════════════════════════════════════════════════
//
// There were ZERO BackHandler registrations in this file. The drill-in is
// component state, not a stack push, so Android's back gesture left the tab
// (or the app) instead of returning to all teams.

assert(
  /BackHandler\.addEventListener\('hardwareBackPress'/.test(screenText),
  '#302 an Android hardware-back handler is registered',
);
// #299/#302 analytics (2026-08-11): the four exit controls no longer call
// setSelectedId(null) directly — they route through the single `closeTeam`
// choke point, which emits league_team_closed AND clears the selection. The
// second half of that chain (closeTeam ⇒ setSelectedId(null), exactly one
// bare clear in the file) is pinned by check-analytics-297-302.js; this file
// keeps pinning that each CONTROL reaches it.
assert(
  /BackHandler\.addEventListener\('hardwareBackPress',\s*\(\)\s*=>\s*\{\s*\n\s*closeTeam\('hardware_back'\);\s*\n\s*return true;/.test(
    screenText,
  ),
  '#302 hardware back clears the focused team and CONSUMES the event',
  'returning false falls through to the navigator and leaves the tab — the current behaviour',
);
assert(
  /if \(!selectedId\) return;\s*\n\s*const sub = BackHandler\.addEventListener/.test(screenText),
  '#302 the handler is registered ONLY while a team is focused',
  'always-on would swallow back on the all-teams view too',
);
assert(
  /registerScrollToTop\('League', \(\) => \{[\s\S]{0,600}?closeTeam\('tab_retap'\);/.test(screenText),
  '#302 re-tapping the active League tab also clears the focused team',
  'scroll-to-top alone is half a reset — the user stays inside the drill-in',
);

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All League drill-in checks passed (#299 + #302).');
