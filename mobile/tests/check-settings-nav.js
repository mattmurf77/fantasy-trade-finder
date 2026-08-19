#!/usr/bin/env node
// Settings IA — the presentation contract (settings-ia-hub, 2026-08-18).
//
// WHY THIS EXISTS. Plan §5 turns Settings from an iOS page-sheet
// (`presentation: 'modal'`) into a plain pushed page, and that single option
// is load-bearing for four separate things:
//
//   • F5 — a modal strands anything pushed on top of it, which is why
//     `navigateFromSettings` dismissed Settings before every outbound link
//     and why Back from SleeperConnect landed on the tabs instead of on
//     Settings. Re-adding `presentation: 'modal'` silently restores that bug.
//   • F6 / #188 — modals are exempt from the FeedbackFAB rule; pushed pages
//     are not. Each settings page must mount its own FAB.
//   • #151 / RNS#3294 — the native back control is dead on iOS 26 when the
//     previous screen runs `headerShown: false`, which `Main` does. Every
//     pushed settings page therefore needs an explicit `HeaderBack`, or it
//     ships with no way out at all.
//   • Deep links — `settings/notifications` needs a real route to land on.
//
// None of that is visible to `tsc`: `presentation: 'modal'` type-checks
// perfectly, and a page with no back control renders fine. D-056 retired the
// simulator, so this file is the only automated thing standing between the
// plan and a settings screen you cannot leave.
//
// HOW THE MODAL PARSE IS SCOPED. RootNav registers ~25 screens and TWO of
// them are legitimately modals (FeedbackInbox, SleeperConnect). A naive
// `text.includes("presentation: 'modal'")` would pass or fail for reasons
// having nothing to do with Settings. So this walks the real TypeScript AST,
// takes each `<Stack.Screen>` element individually, reads only ITS `options`
// attribute, and follows a shared options helper (`settingsPageOptions(...)`)
// into its declaration when one is used. A "parse self-test" then asserts the
// detector still flags the two known modals — a checker that reports "no
// modals found" because its parse broke would otherwise pass forever.
//
// Run: node tests/check-settings-nav.js   (or: npm run test:settings-nav)

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
const ok   = (n) => console.log(`PASS  ${n}`);
const fail = (n, why) => { failures += 1; console.error(`FAIL  ${n}\n      ${why}`); };

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');

// The eight registrations plan §3/§5 requires: the hub route plus seven
// second-level pages. `SettingsTesting` is registered unconditionally on
// purpose — `__DEV__ || testing.stage_users` gates the hub ROW, not the
// route (the RootNav convention).
const ROUTES = [
  'Settings',
  'SettingsLeagues',
  'SettingsRanking',
  'SettingsTradeValues',
  'SettingsNotifications',
  'SettingsAccount',
  'SettingsAbout',
  'SettingsTesting',
];

// Screen module → the `activeScreen` its FeedbackFAB must report. The hub
// renders on the `Settings` route, so it files as "Settings".
const PAGE_MODULES = {
  'SettingsHubScreen.tsx':           'Settings',
  'SettingsLeaguesScreen.tsx':       'SettingsLeagues',
  'SettingsRankingScreen.tsx':       'SettingsRanking',
  'SettingsTradeValuesScreen.tsx':   'SettingsTradeValues',
  'SettingsNotificationsScreen.tsx': 'SettingsNotifications',
  'SettingsAccountScreen.tsx':       'SettingsAccount',
  'SettingsAboutScreen.tsx':         'SettingsAbout',
  'SettingsTestingScreen.tsx':       'SettingsTesting',
};

// Screens that ARE modals today and must stay detectable — the self-test
// that proves the parse below is doing real work.
const KNOWN_MODALS = ['FeedbackInbox', 'SleeperConnect'];

const DEEP_LINKS = {
  Settings:              'settings',
  SettingsLeagues:       'settings/leagues',
  SettingsRanking:       'settings/ranking',
  SettingsTradeValues:   'settings/trade-values',
  SettingsNotifications: 'settings/notifications',
  SettingsAccount:       'settings/account',
  SettingsAbout:         'settings/about',
  SettingsTesting:       'settings/testing',
};

// ── Parse RootNav ─────────────────────────────────────────────────────────
const navText = read('src/navigation/RootNav.tsx');
const sf = ts.createSourceFile('RootNav.tsx', navText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

// Top-level `const X = ...` bodies, so an `options={helper(...)}` reference
// can be resolved to the object it actually returns.
const topLevelConsts = {};
for (const stmt of sf.statements) {
  if (ts.isVariableStatement(stmt)) {
    for (const d of stmt.declarationList.declarations) {
      if (ts.isIdentifier(d.name) && d.initializer) {
        topLevelConsts[d.name.text] = d.initializer.getText(sf);
      }
    }
  }
}

// name → { optionsText, elementText }. optionsText is THIS screen's options
// attribute only (plus any helper it calls), never a neighbour's.
const screens = new Map();
const attrOf = (attributes, want) => {
  for (const a of attributes.properties) {
    if (ts.isJsxAttribute(a) && a.name.getText(sf) === want) return a;
  }
  return null;
};

const visit = (node) => {
  const opening = ts.isJsxSelfClosingElement(node) ? node
    : ts.isJsxElement(node) ? node.openingElement
    : null;
  if (opening && opening.tagName.getText(sf) === 'Stack.Screen') {
    const nameAttr = attrOf(opening.attributes, 'name');
    const literal = nameAttr && nameAttr.initializer
      && ts.isStringLiteral(nameAttr.initializer) ? nameAttr.initializer.text : null;
    if (literal) {
      const optAttr = attrOf(opening.attributes, 'options');
      let optionsText = '';
      if (optAttr && optAttr.initializer) {
        optionsText = optAttr.initializer.getText(sf);
        // One level of helper resolution: `options={settingsPageOptions(...)}`
        // puts the header (and any presentation key) in the helper's body.
        for (const id of optionsText.matchAll(/\b([A-Za-z_$][\w$]*)\s*\(/g)) {
          if (topLevelConsts[id[1]]) optionsText += '\n' + topLevelConsts[id[1]];
        }
      }
      screens.set(literal, { optionsText, elementText: node.getText(sf) });
    }
  }
  ts.forEachChild(node, visit);
};
visit(sf);

const isModal = (name) => /presentation\s*:\s*['"]modal['"]/.test((screens.get(name) || {}).optionsText || '');

console.log(`RootNav.tsx: ${screens.size} <Stack.Screen> registrations parsed.\n`);

// ── 0. Parse self-test ────────────────────────────────────────────────────
// A parse that silently matched nothing would report every screen as a
// non-modal and pass this file forever. Prove the detector fires.
{
  if (screens.size >= 15) ok(`parse self-test: ${screens.size} screens found (a broken walk would find ~0)`);
  else fail('parse self-test: screens found',
            `only ${screens.size} <Stack.Screen> elements parsed — the AST walk is not seeing RootNav`);

  const detected = KNOWN_MODALS.filter((n) => screens.has(n) && isModal(n));
  if (detected.length === KNOWN_MODALS.length) {
    ok(`parse self-test: presentation:'modal' still detected on ${detected.join(' + ')} `
       + '(so a modal on Settings would be caught)');
  } else {
    fail("parse self-test: presentation:'modal' detector fires",
         `expected ${KNOWN_MODALS.join(' + ')} to parse as modals, detected: ${detected.join(', ') || 'none'}. `
           + 'Either those screens stopped being modals (update KNOWN_MODALS) or the options '
           + 'scoping is broken and the Settings assertions below are vacuous.');
  }
}

// ── 1. All eight routes registered ────────────────────────────────────────
{
  const missing = ROUTES.filter((r) => !screens.has(r));
  if (missing.length === 0) ok(`all ${ROUTES.length} settings routes registered in RootNav`);
  else fail('all settings routes registered',
            `not registered: ${missing.join(', ')} — the hub row / deep link would throw`);
}

// ── 2. None of the eight is a modal (plan §5) ─────────────────────────────
{
  const present = ROUTES.filter((r) => screens.has(r));
  const modals = present.filter(isModal);
  if (present.length > 0 && modals.length === 0) {
    ok(`none of the ${present.length} settings routes carries presentation:'modal' `
       + '(pushed pages — F5/F6 stay fixed)');
  } else if (modals.length > 0) {
    fail("no settings route carries presentation:'modal'",
         `${modals.join(', ')} registered as a modal — this re-strands outbound pushes (F5) `
           + 'and re-exempts the page from the #188 FeedbackFAB rule (F6)');
  }
}

// ── 3. Each of the eight has an explicit HeaderBack (#151 / RNS#3294) ─────
{
  const present = ROUTES.filter((r) => screens.has(r));
  const noBack = present.filter((r) => !/HeaderBack/.test(screens.get(r).optionsText));
  if (present.length > 0 && noBack.length === 0) {
    ok(`all ${present.length} settings routes supply an explicit HeaderBack`);
  } else if (noBack.length > 0) {
    fail('every settings route supplies a HeaderBack',
         `${noBack.join(', ')} has no HeaderBack — the native back control is dead on iOS 26 `
           + 'over a headerShown:false parent (RNS#3294), so the page has no exit');
  }
}

// ── 4. Every page module mounts FeedbackFAB (#188, F6) ────────────────────
{
  const dir = path.join(MOBILE, 'src', 'screens', 'settings');
  let good = 0;
  for (const [file, activeScreen] of Object.entries(PAGE_MODULES)) {
    const p = path.join(dir, file);
    if (!fs.existsSync(p)) { fail(`FeedbackFAB: ${file}`, 'module does not exist'); continue; }
    const text = fs.readFileSync(p, 'utf8');
    const m = text.match(/<FeedbackFAB\b[^>]*\/>/);
    if (!m) {
      fail(`FeedbackFAB: ${file}`,
           'no <FeedbackFAB /> — #188 exempts modals/sheets, and these are pushed pages');
      continue;
    }
    const tag = m[0];
    if (!/aboveTabBar\s*=\s*\{\s*false\s*\}/.test(tag)) {
      fail(`FeedbackFAB: ${file}`,
           `mounted without aboveTabBar={false} — root-stack pushes cover the tab bar, so the `
             + `FAB would float at a tab-bar offset over nothing. Got: ${tag}`);
      continue;
    }
    if (!new RegExp(`activeScreen\\s*=\\s*["']${activeScreen}["']`).test(tag)) {
      fail(`FeedbackFAB: ${file}`,
           `activeScreen must be "${activeScreen}" so feedback files against the right screen. Got: ${tag}`);
      continue;
    }
    good += 1;
  }
  if (good === Object.keys(PAGE_MODULES).length) {
    ok(`all ${good} settings page modules mount <FeedbackFAB aboveTabBar={false}> with the right activeScreen`);
  }
}

// ── 5. Deep links (plan §8) ───────────────────────────────────────────────
{
  const dl = read('src/utils/deepLinks.ts');
  const m = dl.match(/const\s+V2_SCREENS\s*=\s*\{/);
  if (!m) {
    fail('deepLinks: V2_SCREENS found', 'no V2_SCREENS object literal in deepLinks.ts — did it move?');
  } else {
    // Brace-match the object so a path defined in some other table cannot
    // count for it.
    let i = dl.indexOf('{', m.index), depth = 0, end = i;
    for (; end < dl.length; end++) {
      if (dl[end] === '{') depth += 1;
      else if (dl[end] === '}') { depth -= 1; if (depth === 0) break; }
    }
    const body = dl.slice(i, end + 1);

    const bad = [];
    for (const [route, url] of Object.entries(DEEP_LINKS)) {
      const rm = body.match(new RegExp(`\\b${route}\\s*:\\s*['"]([^'"]*)['"]`));
      if (!rm) bad.push(`${route}: not mapped`);
      else if (rm[1] !== url) bad.push(`${route}: '${rm[1]}' (expected '${url}')`);
    }
    if (bad.length === 0) {
      ok(`deepLinks: all ${Object.keys(DEEP_LINKS).length} settings paths mapped `
         + "(bare 'settings' still resolves to the hub, so the TopBar gear and every existing link are unaffected)");
    } else {
      fail('deepLinks: settings paths mapped', bad.join('; '));
    }

    // Routes must exist in RootNav, or the link resolves to nothing.
    const unregistered = Object.keys(DEEP_LINKS).filter((r) => !screens.has(r));
    if (unregistered.length === 0) ok('deepLinks: every mapped settings route is registered in RootNav');
    else fail('deepLinks: every mapped settings route is registered',
              `${unregistered.join(', ')} — a link that resolves to an unregistered route is a dead link`);
  }
}

console.log(failures === 0
  ? '\nAll settings navigation checks passed.'
  : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
