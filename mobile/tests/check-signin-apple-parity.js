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
//   1. Exactly one AppleAuthenticationButton whose ONLY conditions (every
//      ternary / && above it, not just the nearest) are `landingOn &&
//      appleShown`: buttonType CONTINUE, buttonStyle WHITE (Apple's style for
//      dark backgrounds; release-lead #507 QA P2-b), onPress
//      handleAppleSignIn, testID "signin.apple-continue-btn".
//   2. It comes right under the platform chip row, and before the username
//      field (the username field stays the primary door, below it).
//   3. Its style is as tall as the landing's other sign-in buttons
//      (styles.button.height, at least 44; release-lead #507 QA P2-a), and
//      carries only alignSelf / height / marginBottom (no margin, position or
//      transform push).
//   4. The old text link is gone: no element's rendered text (its JSX text
//      and string children, joined and normalized) says "Already have an
//      account", and no "signin.apple-link" (comment-stripped source).
//   5. The flags-off layout keeps its own SIGN_IN / WHITE button under
//      `!landingOn && appleShown`.
//   6. handleAppleSignIn's first statement returns while any sign-in is busy,
//      and handleSubmit's returns while an Apple sign-in is in flight.
//   7. Nothing else can hide it: `appleShown` is exactly `appleAvailable ||
//      TEST_APPLE_SUB !== null`, and the availability effect's early return is
//      exactly `!accountsEnabled || Platform.OS !== 'ios'`.
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
// EVERY condition above `node` up to its function: ternaries it sits in, and
// the left side of any && / || it is the right side of.
function allGuards(node) {
  const out = [];
  for (let p = node.parent; p; p = p.parent) {
    if (ts.isFunctionDeclaration(p) || ts.isArrowFunction(p) || ts.isFunctionExpression(p)) break;
    if (ts.isConditionalExpression(p) && node.pos >= p.whenTrue.pos && node.end <= p.whenTrue.end) {
      out.push(p.condition.getText(sf).replace(/\s+/g, ' '));
    } else if (ts.isConditionalExpression(p) && node.pos >= p.whenFalse.pos && node.end <= p.whenFalse.end) {
      out.push('!(' + p.condition.getText(sf).replace(/\s+/g, ' ') + ')');
    } else if (ts.isBinaryExpression(p) && [ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken]
      .includes(p.operatorToken.kind) && node.pos >= p.right.pos) {
      out.push(p.left.getText(sf).replace(/\s+/g, ' '));
    }
  }
  return out;
}

const appleButtons = findAll(sf, (n) => tagName(n) === 'AppleAuthentication.AppleAuthenticationButton');
const landingApple = appleButtons.filter((b) => guardOf(b) === 'landingOn && appleShown');
const flagsOffApple = appleButtons.filter((b) => guardOf(b) === '!landingOn && appleShown');

check('1. the landing renders Apple\'s own CONTINUE button (WHITE), behind landingOn && appleShown only', () => {
  expect(landingApple.length === 1,
    `${landingApple.length} AppleAuthenticationButton(s) under \`landingOn && appleShown\`, want 1`);
  const b = landingApple[0];
  const guards = allGuards(b);
  expect(guards.length === 1 && guards[0] === 'landingOn && appleShown',
    `the button's conditions are ${JSON.stringify(guards)}, want only "landingOn && appleShown"`);
  expect(attrText(b, 'buttonType') === 'AppleAuthentication.AppleAuthenticationButtonType.CONTINUE',
    `buttonType is ${attrText(b, 'buttonType')}`);
  expect(attrText(b, 'buttonStyle') === 'AppleAuthentication.AppleAuthenticationButtonStyle.WHITE',
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

check('3. it is as tall as the other sign-in buttons (>= 44), with no layout push', () => {
  const styleDecl = findAll(sf, (n) => ts.isPropertyAssignment(n) && n.name.getText(sf) === 'appleContinueButton')[0];
  const buttonDecl = findAll(sf, (n) => ts.isPropertyAssignment(n) && n.name.getText(sf) === 'button'
    && ts.isObjectLiteralExpression(n.initializer))[0];
  expect(attrText(landingApple[0], 'style') === 'styles.appleContinueButton',
    `the button's style is ${attrText(landingApple[0], 'style')}`);
  expect(styleDecl && buttonDecl, 'appleContinueButton or button style missing');
  const num = (decl, key) => {
    const p = decl.initializer.properties.find((q) => q.name && q.name.getText(sf) === key);
    return p && ts.isNumericLiteral(p.initializer) ? Number(p.initializer.text) : NaN;
  };
  const h = num(styleDecl, 'height');
  const other = num(buttonDecl, 'height');
  expect(Number.isFinite(h) && h === other && h >= 44, `button height ${h}, styles.button height ${other} (want equal, >= 44)`);
  const keys = styleDecl.initializer.properties.map((q) => q.name && q.name.getText(sf)).sort();
  expect(JSON.stringify(keys) === JSON.stringify(['alignSelf', 'height', 'marginBottom']),
    `appleContinueButton keys are ${JSON.stringify(keys)}, want alignSelf / height / marginBottom only`);
});

check('4. the old "Already have an account?" text link is gone', () => {
  const code = stripComments(text);
  expect(!/signin\.apple-link/.test(code), 'testID "signin.apple-link" is still in the code');
  // An element's rendered text: its JSX text and its string-literal children
  // ({'…'} / {"…"}), joined and normalized, so split copy can't hide it.
  const rendered = (el) => el.children.map((c) => {
    if (ts.isJsxText(c)) return c.getText(sf);
    if (ts.isJsxExpression(c) && c.expression && (ts.isStringLiteral(c.expression)
      || ts.isNoSubstitutionTemplateLiteral(c.expression))) return c.expression.text;
    if (ts.isJsxElement(c)) return rendered(c);
    return ' ';
  }).join('');
  const hits = findAll(sf, ts.isJsxElement)
    .filter((el) => /already\s+have\s+an\s+account/i.test(rendered(el).replace(/\s+/g, ' ')));
  expect(hits.length === 0, `"Already have an account" is still rendered: ${hits.map((h) => rendered(h).replace(/\s+/g, ' ').trim().slice(0, 60))}`);
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
  const sub = findAll(sf, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === 'handleSubmit')[0];
  const subFirst = sub && sub.body.statements[0].getText(sf).replace(/\s+/g, ' ');
  expect(subFirst === 'if (busy || appleBusy) return;', `handleSubmit's first statement is: ${subFirst}`);
});

check('7. nothing else can hide it: appleShown and the availability effect are as shipped', () => {
  const decl = findAll(sf, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === 'appleShown')[0];
  expect(decl && decl.initializer.getText(sf).replace(/\s+/g, ' ') === 'appleAvailable || TEST_APPLE_SUB !== null',
    `appleShown is ${decl ? decl.initializer.getText(sf) : 'missing'}`);
  const effects = findAll(sf, (n) => ts.isCallExpression(n) && n.expression.getText(sf) === 'useEffect'
    && n.arguments[0] && n.arguments[0].getText(sf).includes('AppleAuthentication.isAvailableAsync()'));
  expect(effects.length === 1, `${effects.length} availability effect(s), want 1`);
  const first = effects[0].arguments[0].body.statements[0].getText(sf).replace(/\s+/g, ' ');
  expect(first === "if (!accountsEnabled || Platform.OS !== 'ios') return;", `the effect's guard is: ${first}`);
});

console.log(failures === 0
  ? `\nAll Sign in with Apple parity checks passed (${passed}).`
  : `\n${failures} Sign in with Apple parity check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
