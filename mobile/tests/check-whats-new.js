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

console.log(failures === 0
  ? `\nAll what's-new (D-13) checks passed (${passed}).`
  : `\n${failures} what's-new (D-13) check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
