#!/usr/bin/env node
// Sign in with Apple parity on the launched landing (Product's pre-launch
// review B1, 2026-10-27; App Store guideline 4.8 and Apple's sign-in HIG).
//
// Once ESPN/MFL sign-in mints accounts, those are third-party login services
// under 4.8, so Sign in with Apple must be offered as an equivalent option,
// and the HIG asks for Apple's own button, at least as prominent as the other
// options. The landing used to offer Apple only as the text link "Already have
// an account? Sign in with Apple".
//
// Pins (SignInScreen.tsx, AST):
//   1. Under `landingOn && appleShown`, exactly one AppleAuthenticationButton:
//      buttonType CONTINUE, buttonStyle WHITE_OUTLINE, onPress
//      handleAppleSignIn, testID "signin.apple-continue-btn".
//   2. It comes right under the platform chip row, and before the username
//      field (the username field stays the primary door, below it).
//   3. Its style's height equals the chips' minHeight, so it reads as an
//      equal option.
//   4. The old text link is gone: no "Already have an account? Sign in with
//      Apple", no "signin.apple-link" (comment-stripped source).
//   5. The flags-off layout keeps its own SIGN_IN / WHITE button under
//      `!landingOn && appleShown`.
//   6. handleAppleSignIn's first statement returns while any sign-in is busy.
//
// Run: node tests/check-signin-apple-parity.js

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

const ROOT = process.env.FTF_MOBILE_TEST_ROOT || path.resolve(__dirname, '..');
const REL = 'src/screens/SignInScreen.tsx';
const text = fs.readFileSync(path.join(ROOT, REL), 'utf8');
const sf = ts.createSourceFile(REL, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const stripComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

let failures = 0;
let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`PASS  ${name}`);
  } catch (e) {
    failures += 1;
    console.error(`FAIL  ${name}\n      ${e.message}`);
  }
}
function expect(cond, msg) { if (!cond) throw new Error(msg); }
function findAll(root, pred) {
  const out = [];
  (function walk(n) {
    if (pred(n)) out.push(n);
    ts.forEachChild(n, walk);
  })(root);
  return out;
}
const tagName = (n) => (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)
  ? n.tagName.getText(sf) : null);
const attr = (el, name) => el.attributes.properties.find(
  (a) => ts.isJsxAttribute(a) && a.name.getText(sf) === name);
const attrText = (el, name) => {
  const a = attr(el, name);
  if (!a || !a.initializer) return null;
  return ts.isStringLiteral(a.initializer) ? a.initializer.text
    : a.initializer.expression ? a.initializer.expression.getText(sf) : a.initializer.getText(sf);
};
// The `cond ? (...) : null` that renders `node`, innermost first.
function guardOf(node) {
  for (let p = node.parent; p; p = p.parent) {
    if (ts.isConditionalExpression(p) && node.pos >= p.whenTrue.pos && node.end <= p.whenTrue.end) {
      return p.condition.getText(sf).replace(/\s+/g, ' ');
    }
  }
  return null;
}

const appleButtons = findAll(sf, (n) => tagName(n) === 'AppleAuthentication.AppleAuthenticationButton');
const landingApple = appleButtons.filter((b) => guardOf(b) === 'landingOn && appleShown');
const flagsOffApple = appleButtons.filter((b) => guardOf(b) === '!landingOn && appleShown');

check('1. the landing renders Apple\'s own CONTINUE button (white outline)', () => {
  expect(landingApple.length === 1,
    `${landingApple.length} AppleAuthenticationButton(s) under \`landingOn && appleShown\`, want 1`);
  const b = landingApple[0];
  expect(attrText(b, 'buttonType') === 'AppleAuthentication.AppleAuthenticationButtonType.CONTINUE',
    `buttonType is ${attrText(b, 'buttonType')}`);
  expect(attrText(b, 'buttonStyle') === 'AppleAuthentication.AppleAuthenticationButtonStyle.WHITE_OUTLINE',
    `buttonStyle is ${attrText(b, 'buttonStyle')}`);
  expect(attrText(b, 'onPress') === 'handleAppleSignIn', `onPress is ${attrText(b, 'onPress')}`);
  expect(attrText(b, 'testID') === 'signin.apple-continue-btn', `testID is ${attrText(b, 'testID')}`);
});

check('2. it sits right under the platform chip row, above the username field', () => {
  const b = landingApple[0];
  expect(b, 'no landing Apple button');
  const row = findAll(sf, (n) => tagName(n) === 'View'
    && attrText(n, 'style') === 'styles.platformRow')[0];
  const username = findAll(sf, (n) => tagName(n) === 'TextInput'
    && attrText(n, 'testID') === 'signin.username-input')[0];
  expect(row && username, 'the chip row or the username field is missing');
  expect(row.pos < b.pos && b.pos < username.pos,
    'the Apple button is not between the chip row and the username field');
  // Nothing else renders between the chip row's block and the Apple block.
  const rowBlock = row.parent.parent;           // <View …>…</View> → the ?: whenTrue
  const between = text.slice(rowBlock.end, b.pos);
  expect(!/<(?!\/)(?!>)(?!AppleAuthentication)[A-Za-z]/.test(stripComments(between).replace(/\)\s*:\s*null\s*\}\s*\{\s*landingOn\s*&&\s*appleShown\s*\?\s*\(\s*<>/, '')),
    'another element renders between the chip row and the Apple button');
});

check('3. its height is the chips\' height', () => {
  const styleDecl = findAll(sf, (n) => ts.isPropertyAssignment(n) && n.name.getText(sf) === 'appleContinueButton')[0];
  const chipDecl = findAll(sf, (n) => ts.isPropertyAssignment(n) && n.name.getText(sf) === 'platformChip')[0];
  expect(attrText(landingApple[0], 'style') === 'styles.appleContinueButton',
    `the button's style is ${attrText(landingApple[0], 'style')}`);
  expect(styleDecl && chipDecl, 'appleContinueButton or platformChip style missing');
  const num = (decl, key) => {
    const p = decl.initializer.properties.find((q) => q.name && q.name.getText(sf) === key);
    return p && ts.isNumericLiteral(p.initializer) ? Number(p.initializer.text) : NaN;
  };
  const h = num(styleDecl, 'height');
  const chip = num(chipDecl, 'minHeight');
  expect(Number.isFinite(h) && h === chip, `button height ${h}, chip minHeight ${chip}`);
});

check('4. the old "Already have an account?" text link is gone', () => {
  const code = stripComments(text);
  expect(!/Already have an account\? Sign in with Apple/.test(code), 'the text link copy is still rendered');
  expect(!/signin\.apple-link/.test(code), 'testID "signin.apple-link" is still in the code');
});

check('5. the flags-off layout keeps its SIGN_IN / WHITE Apple button', () => {
  expect(flagsOffApple.length === 1,
    `${flagsOffApple.length} AppleAuthenticationButton(s) under \`!landingOn && appleShown\`, want 1`);
  const b = flagsOffApple[0];
  expect(attrText(b, 'buttonType') === 'AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN'
    && attrText(b, 'buttonStyle') === 'AppleAuthentication.AppleAuthenticationButtonStyle.WHITE',
    `the flags-off button is ${attrText(b, 'buttonType')} / ${attrText(b, 'buttonStyle')}`);
  expect(appleButtons.length === 2, `${appleButtons.length} Apple buttons in the screen, want 2`);
});

check('6. a tap while any sign-in is busy does nothing', () => {
  const fn = findAll(sf, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === 'handleAppleSignIn')[0];
  expect(fn && fn.body.statements.length, 'no handleAppleSignIn');
  const first = fn.body.statements[0].getText(sf).replace(/\s+/g, ' ');
  expect(first === 'if (busy || demoBusy || appleBusy) return;', `its first statement is: ${first}`);
});

console.log(failures === 0
  ? `\nAll Sign in with Apple parity checks passed (${passed}).`
  : `\n${failures} Sign in with Apple parity check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
