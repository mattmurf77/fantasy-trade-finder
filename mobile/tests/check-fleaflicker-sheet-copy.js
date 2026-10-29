#!/usr/bin/env node
// Fleaflicker link-sheet copy (legal R27.5) — structural guard.
//
// PlatformLinkSheet serves MFL AND Fleaflicker. MFL has a send path, so the
// shared "Nothing is posted to {LABEL[platform]} unless you sign in and send a
// trade you approve." line is true for it. Fleaflicker has NO send path (the
// platform is dark today, `fleaflicker.link` false), so on Fleaflicker that
// line promises a send the app cannot make. Legal's text must be in place
// before the flag is ever turned on; this guard pins that it stays there.
//
//   1. The two Fleaflicker strings are legal's text VERBATIM — curly
//      apostrophe in "can’t" (U+2019), nothing paraphrased.
//   2. The intro is the done step's FIRST and LAST sentences (legal's rule),
//      so the two can't drift apart.
//   3. Each string renders only inside a `platform === 'fleaflicker'` branch
//      of the intro / done-step <Text>, and each constant is used exactly
//      once. Dropping the branch is the regression: Fleaflicker would fall
//      through to the MFL promise.
//   4. MFL's strings are unchanged: the else-branch of each ternary, and the
//      MFL-only sign-in done step, read exactly as on #385.
//   5. "Nothing is posted" appears exactly three times in the sheet (the two
//      shared MFL branches pinned in 4, plus the MFL-only auth step). A new
//      shared string making the send promise has to be reviewed, not slipped
//      in around the Fleaflicker branch.
//
// Run: node tests/check-fleaflicker-sheet-copy.js
//   (or: npm run test:fleaflicker-sheet-copy)

'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const src = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'components', 'PlatformLinkSheet.tsx'),
  'utf8',
);
// JSX text wraps across lines; compare with whitespace collapsed.
const flat = src.replace(/\s+/g, ' ');

// Legal R27.5, verbatim.
const LEGAL_DONE =
  'Fleaflicker leagues import team names and rosters. Rankings, tiers, trios and trade ideas all work. Trades can’t be sent to Fleaflicker from the app, so nothing is posted there.';
const LEGAL_INTRO =
  'Fleaflicker leagues import team names and rosters. Trades can’t be sent to Fleaflicker from the app, so nothing is posted there.';

function constant(name) {
  const m = new RegExp(`const ${name} =\\s*'([^']*)';`).exec(src);
  return m ? m[1] : null;
}
const intro = constant('FLEAFLICKER_INTRO');
const done = constant('FLEAFLICKER_DONE');

// ── 1. Verbatim ────────────────────────────────────────────────────────
assert(intro === LEGAL_INTRO, '1a Fleaflicker intro is legal\'s text verbatim',
  `got: ${JSON.stringify(intro)}`);
assert(done === LEGAL_DONE, '1b Fleaflicker done-step note is legal\'s text verbatim',
  `got: ${JSON.stringify(done)}`);
assert(
  /can’t/.test(intro || '') && /can’t/.test(done || '') && !/can't/.test(`${intro}${done}`),
  '1c both use the curly apostrophe in "can’t" (U+2019), never a straight one',
);

// ── 2. Intro = first + last sentence of the done step ──────────────────
{
  const sentences = (done || '').split(/(?<=\.) /);
  const derived = sentences.length >= 3
    ? `${sentences[0]} ${sentences[sentences.length - 1]}`
    : null;
  assert(
    derived !== null && derived === intro,
    '2 intro is exactly the done step\'s first and last sentences',
    `derived: ${JSON.stringify(derived)}`,
  );
}

// ── 3. Gated on platform === 'fleaflicker', each used once ─────────────
function usedOnce(constName) {
  return (src.match(new RegExp(`\\b${constName}\\b`, 'g')) || []).length === 2; // decl + 1 use
}
assert(usedOnce('FLEAFLICKER_INTRO') && usedOnce('FLEAFLICKER_DONE'),
  '3a each Fleaflicker constant is declared once and rendered once');

const INTRO_BRANCH =
  "{platform === 'fleaflicker' ? ( <Text style={[type.bodySm, styles.sub]}>{FLEAFLICKER_INTRO}</Text> ) : ( <Text style={[type.bodySm, styles.sub]}> ";
const DONE_BRANCH =
  "{platform === 'fleaflicker' ? ( <Text style={[type.bodySm, styles.readOnlyNote]}>{FLEAFLICKER_DONE}</Text> ) : ( <Text style={[type.bodySm, styles.readOnlyNote]}> ";
assert(flat.includes(INTRO_BRANCH),
  "3b intro: FLEAFLICKER_INTRO renders only in the platform === 'fleaflicker' branch");
assert(flat.includes(DONE_BRANCH),
  "3c done step: FLEAFLICKER_DONE renders only in the platform === 'fleaflicker' branch");

// ── 4. MFL strings unchanged (the else-branches, #385's text) ──────────
assert(
  flat.includes(
    `${INTRO_BRANCH}Imports team names and rosters. Nothing is posted to {LABEL[platform]} unless you sign in and send a trade you approve. </Text> )}`,
  ),
  '4a MFL intro unchanged (else-branch of the Fleaflicker ternary)',
);
assert(
  flat.includes(
    `${DONE_BRANCH}{LABEL[platform]} leagues import team names and rosters. Rankings, tiers, trios and trade ideas all work. Nothing is posted to {LABEL[platform]} unless you sign in and send a trade you approve. {platform === 'mfl' && summary.future_picks_stored ? ' Future draft picks were saved, so trades can include them.' : ''} </Text> )}`,
  ),
  '4b MFL done step unchanged, incl. the future-picks suffix',
);
assert(
  flat.includes(
    'MFL leagues import team names and rosters. Rankings, tiers, trios and trade ideas all work. Nothing is posted to MFL unless you sign in and send a trade you approve. </Text>',
  ),
  '4c MFL-only sign-in done step unchanged',
);

// ── 5. No other copy makes the send promise ────────────────────────────
assert(
  (flat.match(/Nothing is posted/g) || []).length === 3,
  '5 "Nothing is posted" appears exactly 3 times (2 MFL branches + MFL auth step)',
  `found ${(flat.match(/Nothing is posted/g) || []).length}`,
);

if (failures) {
  console.error(`\n${failures} assertion(s) failed`);
  process.exit(1);
}
console.log('\nAll Fleaflicker link-sheet copy assertions passed');
