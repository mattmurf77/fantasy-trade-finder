#!/usr/bin/env node
// Static test: D-13, the launch policy-change notice in the what's-new tip
// (#354; docs/plans/launch-support-policy/scope-d13-policy-notice.md §3).
//
// legal-lead ruled the Privacy Policy and Terms change material (R18), so the
// release announces it in the app. The vehicle is useWhatsNew's version-keyed
// inline tip, and the release slot carries the notice, not a feature note
// (D13-R5).
//
// Pins:
//   1. WHATS_NEW has an entry keyed to mobile/app.json expo.version, the key
//      the hook looks up. A version bump that forgets to move the entry goes
//      red here.
//   2. Its route is 'SettingsAbout', a registered RootNav screen (Settings ›
//      Help & about, where the Privacy Policy and Terms rows live).
//   3. Its headline is legal-lead's Part 5.2 text exactly, with no trailing period.
//   4. No other entry remains (D13-R4: the stale 1.9.1 placeholder is gone).
//   5. The hook is gated by ux.whats_new and keyed by Constants.expoConfig.version.
//      The flag's VALUE is not pinned: release-lead holds it off until the new
//      policy pages are live (scope §5).
//   6. No silent expiry (D13-R6, M-a): the hook has no timer and never calls
//      dismiss itself; the only dismiss is the tip's own tap on League home,
//      which also navigates to the entry's route; LeagueScreen is the only
//      screen that mounts the hook.
//   7. The VoiceOver hint tells the truth: CoachMark's default hint is still
//      "Tap to dismiss" (every other caller), and the what's-new tip, whose tap
//      also opens Help & about, passes its own hint that doesn't say dismiss.
//   8. B7 (pre-launch review, 2026-10-27): a launch whose bootstrap restored
//      no signed-in user counts the release as seen, because the sign-in
//      screen's "you agree" line came first. useSession records the boot fact
//      `bootSignedIn` (null initially, set ONLY by bootstrap to `!!user` after
//      the user is restored; sign-out doesn't reset it). useWhatsNew reads
//      `bootSignedIn === false`, hides the entry and stores it seen, and
//      SEEN_KEY is written nowhere else but dismiss. Anything wider would
//      silence the notice for signed-in upgraders (no silent expiry, 6).
//   9. B7's legal premise is on the screen (release-lead #380 QA P2-1): the
//      sign-in screen's "By signing in you agree to the Terms & Privacy
//      Policy" line renders UNCONDITIONALLY in SignInScreen's own JSX (no
//      {…} expression, ternary or && above it), with both links: "Terms" to
//      /terms and "Privacy Policy" to /privacy. Without it, a signed-out boot
//      would skip the notice for someone who was never shown the policies.
//
// FTF_MOBILE_TEST_ROOT can point at a copy of mobile/ (sabotage runs).
// Run: node tests/check-whats-new.js

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
const F = {
  hook:    'src/hooks/useWhatsNew.ts',
  session: 'src/state/useSession.ts',
  signIn:  'src/screens/SignInScreen.tsx',
  league:  'src/screens/LeagueScreen.tsx',
  rootNav: 'src/navigation/RootNav.tsx',
  coach:   'src/components/CoachMark.tsx',
  appJson: 'app.json',
};

// legal-lead, leads/legal-lead-drafts.md Part 5.2 (2026-10-24), verbatim.
// 97 characters. It supersedes R26.1's 67-character text now that the
// policies carry the subscription terms (R28).
const D13_HEADLINE = "We've updated our Privacy Policy and Terms of Use, including subscription terms. Tap to read them";
const D13_ROUTE = 'SettingsAbout';

for (const rel of Object.values(F)) {
  if (!fs.existsSync(path.join(ROOT, rel))) {
    console.error(`no ${rel} — nothing to check (did the file move?)`);
    process.exit(2);
  }
}

const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const parsed = {};
function parse(rel) {
  if (!parsed[rel]) {
    parsed[rel] = ts.createSourceFile(rel, read(rel), ts.ScriptTarget.Latest, true,
      rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  }
  return parsed[rel];
}
function findAll(root, pred) {
  const out = [];
  (function walk(n) {
    if (pred(n)) out.push(n);
    ts.forEachChild(n, walk);
  })(root);
  return out;
}
const isCallTo = (n, name) => ts.isCallExpression(n) && ts.isIdentifier(n.expression)
  && n.expression.text === name;
const propName = (p) => (p.name && (ts.isIdentifier(p.name) || ts.isStringLiteral(p.name)
  || ts.isNumericLiteral(p.name)) ? p.name.text : null);

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

// WHATS_NEW as plain data: { version: { headline, route } }. Every value must
// be a string literal, so the pins compare what ships.
function whatsNewMap() {
  const sf = parse(F.hook);
  const decl = findAll(sf, (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name)
    && n.name.text === 'WHATS_NEW')[0];
  expect(decl && decl.initializer && ts.isObjectLiteralExpression(decl.initializer),
    'no `const WHATS_NEW = { ... }` object literal in hooks/useWhatsNew.ts');
  const map = {};
  for (const p of decl.initializer.properties) {
    const key = ts.isPropertyAssignment(p) ? propName(p) : null;
    expect(key != null, `WHATS_NEW has a non-literal member: ${p.getText(sf).slice(0, 60)}`);
    expect(ts.isObjectLiteralExpression(p.initializer), `WHATS_NEW['${key}'] is not an object literal`);
    const entry = {};
    for (const q of p.initializer.properties) {
      const k = ts.isPropertyAssignment(q) ? propName(q) : null;
      expect(k != null && (ts.isStringLiteral(q.initializer)
        || ts.isNoSubstitutionTemplateLiteral(q.initializer)),
        `WHATS_NEW['${key}'] member is not a plain string: ${q.getText(sf).slice(0, 60)}`);
      entry[k] = q.initializer.text;
    }
    map[key] = entry;
  }
  return map;
}

const appVersion = JSON.parse(read(F.appJson)).expo?.version;

// ── 1. keyed to the release version ─────────────────────────────────────────
check(`1. WHATS_NEW has an entry keyed to app.json expo.version (${appVersion})`, () => {
  expect(typeof appVersion === 'string' && appVersion, 'app.json has no expo.version');
  const map = whatsNewMap();
  expect(Object.prototype.hasOwnProperty.call(map, appVersion),
    `no WHATS_NEW['${appVersion}'] (keys: ${JSON.stringify(Object.keys(map))}); a version bump `
    + 'moves the D-13 entry in the same change');
});

// ── 2. the target ───────────────────────────────────────────────────────────
check(`2. the entry's route is '${D13_ROUTE}', a registered RootNav screen`, () => {
  const entry = whatsNewMap()[appVersion] || {};
  expect(entry.route === D13_ROUTE, `route is ${JSON.stringify(entry.route)}`);
  const nav = parse(F.rootNav);
  const screens = findAll(nav, (n) => (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n))
    && n.tagName.getText(nav) === 'Stack.Screen')
    .map((n) => n.attributes.properties.find((a) => ts.isJsxAttribute(a) && a.name.getText(nav) === 'name'))
    .filter((a) => a && a.initializer && ts.isStringLiteral(a.initializer))
    .map((a) => a.initializer.text);
  expect(screens.includes(D13_ROUTE), `RootNav registers no Stack.Screen name="${D13_ROUTE}"`);
});

// ── 3. legal's words ────────────────────────────────────────────────────────
check("3. the headline is legal-lead's Part 5.2 text exactly, no trailing period", () => {
  const entry = whatsNewMap()[appVersion] || {};
  expect(entry.headline === D13_HEADLINE,
    `headline is ${JSON.stringify(entry.headline)}\n      expected ${JSON.stringify(D13_HEADLINE)}`);
  expect(!/[.。]\s*$/.test(entry.headline), 'headline ends in a period (the hook contract is no period)');
});

// ── 4. the release slot carries nothing else ────────────────────────────────
check('4. no other WHATS_NEW entry remains (the 1.9.1 placeholder is gone)', () => {
  const keys = Object.keys(whatsNewMap());
  expect(keys.length === 1 && keys[0] === appVersion, `WHATS_NEW keys: ${JSON.stringify(keys)}`);
});

// ── 5. gate and key ─────────────────────────────────────────────────────────
check('5. the hook reads ux.whats_new and keys by Constants.expoConfig.version', () => {
  const sf = parse(F.hook);
  const fn = findAll(sf, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === 'useWhatsNew')[0];
  expect(fn, 'no function useWhatsNew in hooks/useWhatsNew.ts');
  const flagReads = findAll(fn, (n) => isCallTo(n, 'useFlag'))
    .map((c) => c.arguments[0] && ts.isStringLiteral(c.arguments[0]) ? c.arguments[0].text : '?');
  expect(flagReads.length === 1 && flagReads[0] === 'ux.whats_new',
    `useWhatsNew reads flags ${JSON.stringify(flagReads)}, expected exactly ['ux.whats_new']`);
  const ver = findAll(sf, (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name)
    && n.name.text === 'APP_VERSION')[0];
  expect(ver && ver.initializer && /Constants\.expoConfig\??\.version/.test(ver.initializer.getText(sf)),
    `APP_VERSION is ${ver && ver.initializer ? ver.initializer.getText(sf) : 'missing'}`);
  const lookups = findAll(fn, (n) => ts.isElementAccessExpression(n)
    && n.expression.getText(sf) === 'WHATS_NEW');
  expect(lookups.length === 1 && lookups[0].argumentExpression.getText(sf) === 'APP_VERSION',
    `WHATS_NEW lookups: ${JSON.stringify(lookups.map((l) => l.getText(sf)))}`);
});

// ── 6. no silent expiry (M-a) ───────────────────────────────────────────────
check('6. the only dismiss is the tip\'s tap on League home, which also opens the route', () => {
  const hook = parse(F.hook);
  const timers = findAll(hook, (n) => ts.isIdentifier(n)
    && /^(setTimeout|setInterval|requestAnimationFrame|InteractionManager)$/.test(n.text));
  expect(timers.length === 0, `useWhatsNew.ts uses ${timers.map((t) => t.text).join(', ')}`);
  expect(findAll(hook, (n) => isCallTo(n, 'dismiss')).length === 0, 'useWhatsNew.ts calls dismiss() itself');

  // LeagueScreen is the only mount (walk src/ for useWhatsNew() calls).
  const mounts = [];
  (function walk(dir) {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const abs = path.join(dir, ent.name);
      if (ent.isDirectory()) walk(abs);
      else if (/\.tsx?$/.test(ent.name)) {
        const rel = path.relative(ROOT, abs).split(path.sep).join('/');
        if (rel !== F.hook && /\buseWhatsNew\s*\(/.test(fs.readFileSync(abs, 'utf8'))) mounts.push(rel);
      }
    }
  })(path.join(ROOT, 'src'));
  expect(mounts.length === 1 && mounts[0] === F.league, `useWhatsNew() is mounted in ${JSON.stringify(mounts)}`);

  const sf = parse(F.league);
  const mount = findAll(sf, (n) => ts.isVariableDeclaration(n) && n.initializer
    && isCallTo(n.initializer, 'useWhatsNew'))[0];
  expect(mount && ts.isObjectBindingPattern(mount.name), 'LeagueScreen does not destructure useWhatsNew()');
  const alias = (prop) => {
    const el = mount.name.elements.find((e) => (e.propertyName || e.name).getText(sf) === prop);
    return el ? el.name.getText(sf) : null;
  };
  const entryName = alias('entry');
  const dismissName = alias('dismiss');
  expect(entryName && dismissName, 'LeagueScreen does not take entry and dismiss from useWhatsNew()');

  const tips = findAll(sf, (n) => (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n))
    && n.tagName.getText(sf) === 'CoachMark'
    && n.attributes.properties.some((a) => ts.isJsxAttribute(a) && a.name.getText(sf) === 'testID'
      && a.initializer && ts.isStringLiteral(a.initializer) && a.initializer.text === 'league.whats-new'));
  expect(tips.length === 1, `LeagueScreen has ${tips.length} CoachMark testID="league.whats-new"`);
  const tip = tips[0];
  const text = tip.attributes.properties.find((a) => ts.isJsxAttribute(a) && a.name.getText(sf) === 'text');
  expect(text && text.initializer && text.initializer.getText(sf) === `{${entryName}.headline}`,
    `the tip's text is ${text && text.initializer ? text.initializer.getText(sf) : 'missing'}`);
  const onDismiss = tip.attributes.properties.find((a) => ts.isJsxAttribute(a) && a.name.getText(sf) === 'onDismiss');
  expect(onDismiss && onDismiss.initializer, 'the tip has no onDismiss');
  const handler = onDismiss.initializer;

  const dismissCalls = findAll(sf, (n) => isCallTo(n, dismissName));
  expect(dismissCalls.length === 1, `LeagueScreen calls ${dismissName}() ${dismissCalls.length} times, expected once`);
  expect(dismissCalls[0].pos >= handler.pos && dismissCalls[0].end <= handler.end,
    `${dismissName}() is called outside the tip's onDismiss`);
  const navigates = findAll(handler, (n) => ts.isCallExpression(n)
    && /(^|\.)navigate$/.test(n.expression.getText(sf))
    && n.arguments[0] && n.arguments[0].getText(sf) === `${entryName}.route`);
  expect(navigates.length === 1, `the tip's onDismiss does not navigate to ${entryName}.route`);
});

// ── 7. the VoiceOver hint ───────────────────────────────────────────────────
check('7. CoachMark keeps its "Tap to dismiss" default; the what\'s-new tip passes a non-dismiss hint', () => {
  const cm = parse(F.coach);
  const fn = findAll(cm, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === 'CoachMark')[0];
  expect(fn && fn.parameters[0] && ts.isObjectBindingPattern(fn.parameters[0].name),
    'CoachMark does not destructure its props');
  const el = fn.parameters[0].name.elements.find((e) => (e.propertyName || e.name).getText(cm) === 'accessibilityHint');
  expect(el && el.initializer && ts.isStringLiteral(el.initializer) && el.initializer.text === 'Tap to dismiss',
    `CoachMark's accessibilityHint default is ${el && el.initializer ? el.initializer.getText(cm) : 'missing'}`);
  const pressHints = findAll(fn, (n) => ts.isJsxAttribute(n) && n.name.getText(cm) === 'accessibilityHint');
  expect(pressHints.length === 1 && pressHints[0].initializer
    && pressHints[0].initializer.getText(cm) === `{${el.name.getText(cm)}}`,
    `CoachMark renders accessibilityHint ${JSON.stringify(pressHints.map((h) => h.getText(cm)))}, not the prop`);

  const sf = parse(F.league);
  const tip = findAll(sf, (n) => (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n))
    && n.tagName.getText(sf) === 'CoachMark'
    && n.attributes.properties.some((a) => ts.isJsxAttribute(a) && a.name.getText(sf) === 'testID'
      && a.initializer && ts.isStringLiteral(a.initializer) && a.initializer.text === 'league.whats-new'))[0];
  expect(tip, 'no CoachMark testID="league.whats-new" in LeagueScreen');
  const hint = tip.attributes.properties.find((a) => ts.isJsxAttribute(a) && a.name.getText(sf) === 'accessibilityHint');
  expect(hint && hint.initializer && ts.isStringLiteral(hint.initializer) && hint.initializer.text.trim(),
    `the what's-new tip passes no literal accessibilityHint (${hint ? hint.getText(sf) : 'missing'})`);
  expect(!/dismiss/i.test(hint.initializer.text),
    `the what's-new tip's hint says dismiss: ${JSON.stringify(hint.initializer.text)}`);
});

// ── 8. B7: a signed-out boot counts the release as seen ────────────────────
check('8. only a launch that booted signed out counts the release as seen (B7)', () => {
  const sf = parse(F.session);
  const assigns = findAll(sf, (n) => ts.isPropertyAssignment(n) && propName(n) === 'bootSignedIn');
  expect(assigns.length === 2, `bootSignedIn is assigned ${assigns.length} times in useSession.ts, want 2`);
  const boot = findAll(sf, (n) => ts.isPropertyAssignment(n) && propName(n) === 'bootstrap')[0];
  expect(boot, 'useSession has no bootstrap');
  const inBoot = assigns.filter((a) => a.pos >= boot.pos && a.end <= boot.end);
  const outside = assigns.filter((a) => !(a.pos >= boot.pos && a.end <= boot.end));
  expect(inBoot.length === 1 && inBoot[0].initializer.getText(sf).replace(/\s+/g, '') === '!!user',
    `bootstrap sets bootSignedIn to ${inBoot.map((a) => a.initializer.getText(sf))}, want !!user`);
  expect(outside.length === 1 && outside[0].initializer.kind === ts.SyntaxKind.NullKeyword,
    `outside bootstrap, bootSignedIn is ${outside.map((a) => a.initializer.getText(sf))}, want the initial null only`);
  const restore = findAll(boot, (n) => ts.isBinaryExpression(n)
    && n.left.getText(sf) === 'user' && n.operatorToken.kind === ts.SyntaxKind.EqualsToken
    && /JSON\.parse\(\s*userRaw\s*\)/.test(n.right.getText(sf)));
  expect(restore.length === 1 && inBoot[0].pos > restore[0].pos,
    'bootSignedIn is set before `user = JSON.parse(userRaw)` restores the signed-in user');
  const elsewhere = [];
  (function walk(dir) {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const abs = path.join(dir, ent.name);
      if (ent.isDirectory()) walk(abs);
      else if (/\.tsx?$/.test(ent.name)) {
        const rel = path.relative(ROOT, abs).split(path.sep).join('/');
        if (rel !== F.session && /bootSignedIn\s*:/.test(fs.readFileSync(abs, 'utf8'))) elsewhere.push(rel);
      }
    }
  })(path.join(ROOT, 'src'));
  expect(elsewhere.length === 0, `bootSignedIn is set outside useSession.ts: ${JSON.stringify(elsewhere)}`);

  const hook = parse(F.hook);
  const read = findAll(hook, (n) => ts.isVariableDeclaration(n) && n.name.getText(hook) === 'agreedThisLaunch')[0];
  expect(read && read.initializer.getText(hook).replace(/\s+/g, '') === 'useSession((s)=>s.bootSignedIn===false)',
    `agreedThisLaunch is ${read ? read.initializer.getText(hook) : 'missing'}`);
  const entryDecl = findAll(hook, (n) => ts.isVariableDeclaration(n) && n.name.getText(hook) === 'entry')[0];
  expect(entryDecl && /!agreedThisLaunch\b/.test(entryDecl.initializer.getText(hook)),
    'the entry does not require !agreedThisLaunch');
  const writes = findAll(hook, (n) => ts.isCallExpression(n)
    && n.expression.getText(hook) === 'AsyncStorage.setItem'
    && n.arguments[0] && n.arguments[0].getText(hook) === 'SEEN_KEY');
  expect(writes.length === 2, `SEEN_KEY is written ${writes.length} times in useWhatsNew.ts, want 2 (dismiss + B7)`);
  const dismissFn = findAll(hook, (n) => ts.isVariableDeclaration(n) && n.name.getText(hook) === 'dismiss')[0];
  const b7 = writes.filter((w) => !(dismissFn && w.pos >= dismissFn.pos && w.end <= dismissFn.end));
  expect(b7.length === 1, 'the B7 write is missing, or a second write sits outside dismiss');
  let eff = b7[0].parent;
  while (eff && !(ts.isCallExpression(eff) && eff.expression.getText(hook) === 'useEffect')) eff = eff.parent;
  expect(eff, 'the B7 write is not inside a useEffect');
  const firstStmt = eff.arguments[0].body.statements[0].getText(hook).replace(/\s+/g, ' ');
  expect(firstStmt === 'if (!enabled || !agreedThisLaunch || !APP_VERSION) return;',
    `the B7 effect's guard is: ${firstStmt}`);
});

// ── 9. B7's premise: the "you agree" line, unconditional, both links ────────
check('9. the sign-in screen always shows "By signing in you agree to the Terms & Privacy Policy" (B7)', () => {
  const sf = parse(F.signIn);
  const lines = findAll(sf, (n) => ts.isJsxElement(n)
    && n.openingElement.tagName.getText(sf) === 'Text'
    && n.openingElement.attributes.properties.some((a) => ts.isJsxAttribute(a)
      && a.name.getText(sf) === 'style' && a.initializer && a.initializer.getText(sf) === '{styles.legalLine}'));
  expect(lines.length === 1, `${lines.length} <Text style={styles.legalLine}> in SignInScreen, want 1`);
  const line = lines[0];
  const lead = line.children.filter(ts.isJsxText).map((t) => t.getText(sf)).join(' ').replace(/\s+/g, ' ');
  expect(/^\s*By signing in you agree to the\b/.test(lead), `the line reads: ${JSON.stringify(lead.trim())}`);
  const links = line.children.filter((c) => ts.isJsxElement(c) && c.openingElement.tagName.getText(sf) === 'Text');
  const target = (el) => {
    const onPress = el.openingElement.attributes.properties.find((a) => ts.isJsxAttribute(a) && a.name.getText(sf) === 'onPress');
    const call = onPress && findAll(onPress, (n) => ts.isCallExpression(n) && n.expression.getText(sf) === 'Linking.openURL')[0];
    return call && call.arguments[0] && ts.isStringLiteral(call.arguments[0]) ? call.arguments[0].text : null;
  };
  const label = (el) => el.children.map((c) => c.getText(sf)).join('').trim();
  const terms = links.find((l) => label(l) === 'Terms');
  const privacy = links.find((l) => label(l) === 'Privacy Policy');
  expect(terms && /\/terms$/.test(target(terms) || ''), `the Terms link opens ${terms ? target(terms) : 'nothing'}`);
  expect(privacy && /\/privacy$/.test(target(privacy) || ''), `the Privacy Policy link opens ${privacy ? target(privacy) : 'nothing'}`);
  let fn = null;
  for (let p = line.parent; p; p = p.parent) {
    if (ts.isJsxExpression(p) || ts.isConditionalExpression(p)
      || (ts.isBinaryExpression(p) && [ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken,
        ts.SyntaxKind.QuestionQuestionToken].includes(p.operatorToken.kind))) {
      throw new Error(`the line renders inside a condition: ${p.getText(sf).slice(0, 80).replace(/\s+/g, ' ')}…`);
    }
    if (ts.isFunctionDeclaration(p) || ts.isArrowFunction(p) || ts.isFunctionExpression(p)) { fn = p; break; }
  }
  expect(fn && ts.isFunctionDeclaration(fn) && fn.name && fn.name.text === 'SignInScreen',
    `the line renders in ${fn && fn.name ? fn.name.text : 'a nested function'}, not SignInScreen's own JSX`);
});

console.log(failures === 0
  ? `\nAll what's-new (D-13) checks passed (${passed}).`
  : `\n${failures} what's-new (D-13) check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
