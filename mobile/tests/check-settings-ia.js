#!/usr/bin/env node
// Settings IA — the anti-lost-setting check (settings-ia-hub, 2026-08-18).
//
// WHY THIS EXISTS. The settings split takes a 1,712-line SettingsScreen with
// ~25 controls behind ten conditional flags and fans it out across twelve
// section modules and eight pages. Nothing in the type system says a row
// survived the move: a section module that no page imports still compiles,
// still type-checks, still passes testid-lint (its testIDs are in the tree,
// just unreachable), and simply never renders. D-056 retired the simulator,
// so there is no runtime pass that would notice. Risk R3 in the plan.
//
// This test IS the §4 migration map, executable:
//   docs/plans/settings-ia-hub/plan.md § 4 "Row-by-row migration map"
//
// Three layers, from coarse to fine:
//   1. every section module is imported by EXACTLY ONE page (no orphan,
//      no duplicate) and by the page §4 assigns it;
//   2. every ROW that exists in prod today resolves to exactly one section
//      module — module ownership alone would not catch a row deleted from
//      inside a surviving module;
//   3. the four moves §4 actually makes, asserted individually, plus the
//      ordering the operator fixed on 2026-08-18.
//
// Plus two #354 review items (ux-lead, 2026-10-23), walked on the TypeScript
// AST so comments can't satisfy them:
//   5. D-7 — ONE tester-surface predicate. `useTesterSurface()` is defined once
//      (settings/useTesterSurface.ts) and EXECUTED here over a flag truth
//      table: true for __DEV__, `testing.stage_users` or
//      `testing.timing_readout`, false otherwise. The hub's Testing row and
//      the Testing page body are each gated by it directly, and the page's
//      other branch is the honest unavailable line, never an empty page.
//      5e: #363's TimingReadoutRow sits right after TestingSection, imported
//      from components/, default testID, under no gate but that predicate.
//   6. D-6 — FeedbackSheet renders no Screen field (its only TextInput is the
//      note) but still submits `screen`, falling back to 'Unknown'.
//
// If §4 changes, change the tables below in the same commit. A row added to
// the app and not added here fails as "not in the §4 migration map" — that
// is the check working, not the check being stale.
//
// FTF_MOBILE_TEST_ROOT can point at a copy of mobile/ (sabotage runs).
// Run: node tests/check-settings-ia.js   (or: npm run test:settings-ia)

'use strict';

const fs = require('fs');
const path = require('path');

const MOBILE_ROOT = process.env.FTF_MOBILE_TEST_ROOT || path.join(__dirname, '..');
const SETTINGS_DIR = path.join(MOBILE_ROOT, 'src', 'screens', 'settings');
const SECTIONS_DIR = path.join(SETTINGS_DIR, 'sections');

let failures = 0;
const ok   = (n) => console.log(`PASS  ${n}`);
const fail = (n, why) => { failures += 1; console.error(`FAIL  ${n}\n      ${why}`); };

// Full-line comments are stripped before row markers are searched. Every
// section module carries a long "why" banner that names its neighbours'
// rows ("Sign out lives on Account & data", "shipped navigation.replace"),
// and a marker that matched a comment would report a row as living in two
// places at once. Code-line matches only.
const stripComments = (text) =>
  text
    .split('\n')
    .filter((l) => {
      const t = l.trim();
      return !(t.startsWith('//') || t.startsWith('*') || t.startsWith('/*'));
    })
    .join('\n');

// ── The §4 map, as code ───────────────────────────────────────────────────
// section module  →  the ONE page that owns it.
const SECTION_OWNER = {
  'LeaguesSection.tsx':           'SettingsLeaguesScreen.tsx',
  'PlatformLinkSection.tsx':      'SettingsLeaguesScreen.tsx',
  // §4 MOVE: the three disconnects came from Account (fixes F2).
  'PlatformDisconnectSection.tsx': 'SettingsLeaguesScreen.tsx',
  'RankingSection.tsx':           'SettingsRankingScreen.tsx',
  'TradeValuesSection.tsx':       'SettingsTradeValuesScreen.tsx',
  'NotificationsSection.tsx':     'SettingsNotificationsScreen.tsx',
  'AccountIdentitySection.tsx':   'SettingsAccountScreen.tsx',
  // §4 MOVE: Sign out came off the hub (operator decision 2026-08-18).
  'SignOutRow.tsx':               'SettingsAccountScreen.tsx',
  'AccountDataSection.tsx':       'SettingsAccountScreen.tsx',
  // §4 MOVE: The Analyst came from its own "Guided tour" group.
  'GuideSection.tsx':             'SettingsAboutScreen.tsx',
  'AboutSection.tsx':             'SettingsAboutScreen.tsx',
  'TestingSection.tsx':           'SettingsTestingScreen.tsx',
};

// Every row in §4's left-hand column, keyed to a marker that identifies it
// in source, and to the section module §4 sends it to. `new: true` marks
// the two additions §4 declares (version row is the only new *row*).
const ROWS = [
  { row: 'League switch rows',            marker: 'Currently active league',            owner: 'LeaguesSection.tsx' },
  { row: 'Connect league card',           marker: 'Paste a Sleeper league URL',         owner: 'LeaguesSection.tsx' },
  { row: 'Link an ESPN league',           marker: 'settings.link-espn',                 owner: 'PlatformLinkSection.tsx' },
  { row: 'Link an MFL league',            marker: 'settings.link-platform',             owner: 'PlatformLinkSection.tsx' },
  { row: 'Disconnect Sleeper sending',    marker: 'settings.sleeper-disconnect',        owner: 'PlatformDisconnectSection.tsx', moved: 'Account' },
  { row: 'Disconnect ESPN account',       marker: 'settings.espn-disconnect',           owner: 'PlatformDisconnectSection.tsx', moved: 'Account' },
  { row: 'Disconnect MFL sign-in',        marker: 'settings.mfl-disconnect',            owner: 'PlatformDisconnectSection.tsx', moved: 'Account' },
  { row: 'SteerSlider + hint',            marker: '<SteerSlider',                       owner: 'RankingSection.tsx' },
  { row: 'Stud tax segmented',            marker: 'settings.stud-tax.',                 owner: 'TradeValuesSection.tsx' },
  // 'Pick pricing segmented' was the row below Stud tax. REMOVED 2026-08-21
  // (D-144): the operator ruled market pick pricing "not an opt-in or even an
  // option to flip", so the control is deleted rather than moved, and §4's
  // left-hand column is one row shorter. `check-settings-testids.js` holds the
  // inverse assertion (settings.pick-pricing.* generates nothing).
  { row: 'The Analyst toggle',            marker: 'settings.guided-tour-toggle',        owner: 'GuideSection.tsx', moved: 'Guided tour' },
  { row: 'Denied-permission banner',      marker: 'settings.notif-denied-banner',       owner: 'NotificationsSection.tsx' },
  { row: 'Trade matches toggle',          marker: 'title="Trade matches"',              owner: 'NotificationsSection.tsx' },
  { row: 'Weekly digest toggle',          marker: 'title="Weekly digest"',              owner: 'NotificationsSection.tsx' },
  { row: 'Stay in the game toggle',       marker: 'title="Stay in the game"',           owner: 'NotificationsSection.tsx' },
  { row: 'Pause overnight toggle',        marker: 'Pause overnight',                    owner: 'NotificationsSection.tsx' },
  { row: 'Time zone + footnote',          marker: 'Detected from this device',          owner: 'NotificationsSection.tsx' },
  { row: 'Demo session row',              marker: '>Demo session<',                     owner: 'AccountIdentitySection.tsx' },
  { row: 'Identity rows (Apple/Google)',  marker: 'Signed in with Apple',               owner: 'AccountIdentitySection.tsx' },
  { row: 'Link Apple card',               marker: 'settings.link-apple-btn',            owner: 'AccountIdentitySection.tsx' },
  { row: 'Sleeper @username row',         marker: '>Sleeper<',                          owner: 'AccountIdentitySection.tsx' },
  { row: 'LinkSleeperForm (account-only)', marker: '<LinkSleeperForm',                  owner: 'AccountIdentitySection.tsx' },
  { row: 'Verification row + explainer',  marker: "'Not verified'",                     owner: 'AccountIdentitySection.tsx' },
  { row: 'Verify account CTA',            marker: '>Verify account<',                   owner: 'AccountIdentitySection.tsx' },
  { row: 'Public profile toggle (dark)',  marker: 'title="Public profile"',             owner: 'AccountDataSection.tsx' },
  { row: 'Download my data',              marker: 'settings.export-data',               owner: 'AccountDataSection.tsx' },
  { row: 'Delete account',                marker: "'Delete account?'",                  owner: 'AccountDataSection.tsx' },
  { row: 'Sign out',                      marker: 'styles.signOutText',                 owner: 'SignOutRow.tsx', moved: 'hub' },
  { row: 'Help & FAQ',                    marker: 'settings.help-faq',                  owner: 'AboutSection.tsx' },
  { row: 'Privacy Policy',                marker: '>Privacy Policy<',                   owner: 'AboutSection.tsx' },
  { row: 'Terms of Use',                  marker: '>Terms of Use<',                     owner: 'AboutSection.tsx' },
  { row: 'Version + build',               marker: 'settings.version',                   owner: 'AboutSection.tsx', new: true },
  // #354 BL-10 (D-3): the feedback inbox row moved Testing → Help & about and
  // was retitled "Your feedback"; its new testID is the marker.
  { row: 'Your feedback (inbox)',         marker: 'settings.feedback-inbox',            owner: 'AboutSection.tsx', moved: 'Testing' },
  { row: 'Test stages',                   marker: 'settings.test-stages',               owner: 'TestingSection.tsx' },
];

// ── Load the tree ─────────────────────────────────────────────────────────
if (!fs.existsSync(SECTIONS_DIR)) {
  console.error(`FAIL  settings subtree exists\n      ${SECTIONS_DIR} not found — Phase 0 (section extraction) has not landed.`);
  process.exit(1);
}

// Section modules = every .tsx under sections/. `types.ts` and any other
// .ts are shared plumbing, not renderable sections, so they are excluded.
const sectionFiles = fs.readdirSync(SECTIONS_DIR).filter((f) => f.endsWith('.tsx')).sort();
const pageFiles = fs.readdirSync(SETTINGS_DIR)
  .filter((f) => /^Settings.*Screen\.tsx$/.test(f))
  .sort();

const sectionText = {};
for (const f of sectionFiles) {
  sectionText[f] = stripComments(fs.readFileSync(path.join(SECTIONS_DIR, f), 'utf8'));
}

// page → [section module basenames it imports], in import order.
const pageImports = {};
for (const p of pageFiles) {
  const text = fs.readFileSync(path.join(SETTINGS_DIR, p), 'utf8');
  const found = [];
  for (const m of text.matchAll(/^\s*import\s+(?:type\s+)?[^;]*?from\s+'\.\/sections\/([A-Za-z0-9_]+)'/gm)) {
    found.push(`${m[1]}.tsx`);
  }
  pageImports[p] = found;
}

console.log(`Settings tree: ${pageFiles.length} page module(s), ${sectionFiles.length} section module(s).\n`);

// ── 1. Ownership: exactly one page per section, and the RIGHT page ────────
{
  const owners = {};                       // section → [pages importing it]
  for (const f of sectionFiles) owners[f] = [];
  for (const [p, imps] of Object.entries(pageImports)) {
    for (const s of imps) {
      if (!(s in owners)) owners[s] = [];   // an import of a file that isn't there
      owners[s].push(p);
    }
  }

  // 1a. no orphans, no duplicates
  const orphans = sectionFiles.filter((f) => owners[f].length === 0);
  const dupes   = sectionFiles.filter((f) => owners[f].length > 1);
  if (orphans.length === 0) ok(`no orphaned section modules (all ${sectionFiles.length} are imported by a page)`);
  else fail('no orphaned section modules',
            `imported by ZERO pages, so they never render — a lost setting: ${orphans.join(', ')}`);

  if (dupes.length === 0) ok('no duplicated section modules (none imported by 2+ pages)');
  else fail('no duplicated section modules',
            dupes.map((d) => `${d} → ${owners[d].join(' + ')}`).join('; ')
              + ' — the same rows would render on two pages');

  // 1b. imports that resolve to nothing on disk
  const missing = Object.keys(owners).filter((s) => !sectionFiles.includes(s));
  if (missing.length === 0) ok('every ./sections/* import resolves to a real module');
  else fail('every ./sections/* import resolves to a real module', missing.join(', '));

  // 1c. the §4 assignment itself
  let placed = 0;
  for (const [section, expectedPage] of Object.entries(SECTION_OWNER)) {
    if (!sectionFiles.includes(section)) {
      fail(`§4 map: ${section} exists`, `declared in the migration map but not on disk`);
      continue;
    }
    const actual = owners[section];
    if (actual.length === 1 && actual[0] === expectedPage) { placed += 1; continue; }
    fail(`§4 map: ${section} → ${expectedPage}`,
         actual.length === 0
           ? 'imported by no page at all'
           : `imported by ${actual.join(' + ')}`);
  }
  if (placed === Object.keys(SECTION_OWNER).length) {
    ok(`§4 map: all ${placed} section modules sit on the page the plan assigns`);
  }

  // 1d. a section module the map has never heard of
  const unmapped = sectionFiles.filter((f) => !(f in SECTION_OWNER));
  if (unmapped.length === 0) ok('no section module outside the §4 migration map');
  else fail('no section module outside the §4 migration map',
            `${unmapped.join(', ')} — add it to SECTION_OWNER here and to plan §4, or delete it`);
}

// ── 2. Rows: every prod row resolves to exactly one section module ────────
{
  let clean = 0;
  for (const spec of ROWS) {
    const hits = sectionFiles.filter((f) => sectionText[f].includes(spec.marker));
    if (hits.length === 1 && hits[0] === spec.owner) {
      clean += 1;
      continue;
    }
    if (hits.length === 0) {
      fail(`row "${spec.row}"`,
           `marker ${JSON.stringify(spec.marker)} found in NO section module — `
             + `the row was dropped in the split (expected ${spec.owner})`);
    } else if (hits.length > 1) {
      fail(`row "${spec.row}"`,
           `marker ${JSON.stringify(spec.marker)} found in ${hits.length} modules `
             + `(${hits.join(', ')}) — the row renders twice`);
    } else {
      fail(`row "${spec.row}"`,
           `lives in ${hits[0]}, but §4 sends it to ${spec.owner}`);
    }
  }
  if (clean === ROWS.length) {
    const moves = ROWS.filter((r) => r.moved).length;
    ok(`all ${ROWS.length} §4 rows resolve to exactly one section module `
       + `(${moves} of them moved section, 1 new)`);
  }
}

// ── 3. The four moves §4 actually makes, called out one by one ────────────
{
  const on = (page, section) => (pageImports[page] || []).includes(section);

  // 3a. platform disconnects: Leagues, not Account (F2)
  if (on('SettingsLeaguesScreen.tsx', 'PlatformDisconnectSection.tsx')
      && !on('SettingsAccountScreen.tsx', 'PlatformDisconnectSection.tsx')) {
    ok('MOVE: the three platform disconnect rows are on Leagues, not Account (F2)');
  } else {
    fail('MOVE: platform disconnects on Leagues, not Account',
         `Leagues imports it: ${on('SettingsLeaguesScreen.tsx', 'PlatformDisconnectSection.tsx')}; `
           + `Account imports it: ${on('SettingsAccountScreen.tsx', 'PlatformDisconnectSection.tsx')}`);
  }

  // 3b. The Analyst: About, not its own group
  const guidePages = pageFiles.filter((p) => on(p, 'GuideSection.tsx'));
  if (guidePages.length === 1 && guidePages[0] === 'SettingsAboutScreen.tsx') {
    ok('MOVE: GuideSection (The Analyst) is on About, not its own group');
  } else {
    fail('MOVE: GuideSection on About',
         `imported by: ${guidePages.join(', ') || '(nobody)'}`);
  }

  // 3c. Sign out: Account, not the hub
  const signOutPages = pageFiles.filter((p) => on(p, 'SignOutRow.tsx'));
  if (signOutPages.length === 1 && signOutPages[0] === 'SettingsAccountScreen.tsx') {
    ok('MOVE: SignOutRow is on Account, not the hub (operator decision 2026-08-18)');
  } else {
    fail('MOVE: SignOutRow on Account',
         `imported by: ${signOutPages.join(', ') || '(nobody)'}`);
  }

  // 3d. ordering: Sign out under identity, Delete account last. The two
  // destructive controls must stay at opposite ends of the page — stacking
  // them adjacent invites a mis-tap on the irreversible one (plan §3.4).
  const accText = fs.readFileSync(path.join(SETTINGS_DIR, 'SettingsAccountScreen.tsx'), 'utf8');
  const idxImp = (s) => accText.search(new RegExp(`^\\s*import[^;]*?from\\s+'\\./sections/${s}'`, 'm'));
  const iSignOutImp = idxImp('SignOutRow');
  const iDataImp    = idxImp('AccountDataSection');
  if (iSignOutImp >= 0 && iDataImp > iSignOutImp) {
    ok('ORDER: AccountDataSection is imported after SignOutRow on the Account page');
  } else {
    fail('ORDER: AccountDataSection imported after SignOutRow',
         iSignOutImp < 0 ? 'SignOutRow is not imported by SettingsAccountScreen.tsx'
                         : 'AccountDataSection (ends in Delete account) is imported BEFORE SignOutRow');
  }

  // Import order is the operator's stated contract, but render order is what
  // a user's thumb meets. Assert both.
  const iSignOutJsx = accText.indexOf('<SignOutRow');
  const iDataJsx    = accText.indexOf('<AccountDataSection');
  if (iSignOutJsx >= 0 && iDataJsx > iSignOutJsx) {
    ok('ORDER: <SignOutRow> renders above <AccountDataSection> (Delete account stays last)');
  } else {
    fail('ORDER: <SignOutRow> renders above <AccountDataSection>',
         iSignOutJsx < 0 ? 'no <SignOutRow> in the Account page JSX'
                         : 'Delete account would render above Sign out — the two destructive '
                           + 'controls end up adjacent, which plan §3.4 forbids');
  }
}

// ── 4. The hub is navigation only ─────────────────────────────────────────
{
  const hubPath = path.join(SETTINGS_DIR, 'SettingsHubScreen.tsx');
  if (!fs.existsSync(hubPath)) {
    fail('hub: SettingsHubScreen.tsx exists', 'Phase 3 (the hub) has not landed');
  } else {
    const hubSections = pageImports['SettingsHubScreen.tsx'] || [];
    if (hubSections.length === 0) ok('hub: imports no section module (navigation only)');
    else fail('hub: imports no section module',
              `imports ${hubSections.join(', ')} — the hub is a list of nav rows, not a settings page`);

    // Sign out is the one control the operator explicitly took off the hub
    // on 2026-08-18. What is forbidden is the MECHANISM, not the word: the
    // Account row's preview subtitle legitimately reads "… · Sign out" to
    // tell the user what is behind the row (a true statement, so it passes
    // plan §6's never-guess rule). So this asserts the hub cannot actually
    // sign anyone out — no SignOutRow, no signOut() call, no
    // replace('SignIn'), no sign-out testID — rather than grepping for a
    // string that is allowed to appear. Comments are stripped first; the
    // hub's own banner says "Sign out is NOT here" and must not read as a
    // violation of itself.
    const hubCode = stripComments(fs.readFileSync(hubPath, 'utf8'));
    const mechanisms = [
      [/<\s*SignOutRow/,                 'renders <SignOutRow>'],
      [/\bsignOut\s*\(/,                 'calls signOut()'],
      [/\breplace\s*\(\s*['"]SignIn['"]/, "calls replace('SignIn')"],
      [/testID\s*=\s*[{"'][^}"']*sign-?out/i, 'has a sign-out testID'],
    ].filter(([re]) => re.test(hubCode)).map(([, why]) => why);

    if (mechanisms.length === 0) {
      const mentions = /['"][^'"]*Sign out[^'"]*['"]/.test(hubCode);
      ok('hub: no sign-out control — it lives on Account & data'
         + (mentions ? ' (the Account row preview names it, which is allowed: a true preview, not a control)' : ''));
    } else {
      fail('hub: no sign-out control',
           `SettingsHubScreen.tsx ${mechanisms.join(' and ')} — the operator moved sign-out `
             + 'to the Account page on 2026-08-18; the hub is navigation only');
    }
  }
}

// ── 5 + 6. #354 review items, on the TypeScript AST ──────────────────────
{
  let ts;
  try { ts = require('typescript'); } catch {
    console.error('typescript not resolvable — run `npm install` in mobile/ first.');
    process.exit(2);
  }
  const vm = require('vm');
  const SRC = path.join(MOBILE_ROOT, 'src');
  const parseFile = (abs) => ts.createSourceFile(abs, fs.readFileSync(abs, 'utf8'), ts.ScriptTarget.Latest, true,
    abs.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const findAll = (root, pred) => {
    const out = [];
    const visit = (n) => { if (pred(n)) out.push(n); ts.forEachChild(n, visit); };
    visit(root);
    return out;
  };
  const isStr = (n) => !!n && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n));
  const line = (sf, n) => `${path.relative(MOBILE_ROOT, sf.fileName)}:${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1}`;
  const attr = (el, name) => el.attributes.properties.find((a) => ts.isJsxAttribute(a) && a.name.getText() === name);
  const attrStr = (el, name) => {
    const a = attr(el, name);
    if (!a || !a.initializer) return null;
    if (isStr(a.initializer)) return a.initializer.text;
    if (ts.isJsxExpression(a.initializer) && isStr(a.initializer.expression)) return a.initializer.expression.text;
    return null;
  };
  const jsxOpen = (n) => (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n));
  const byTestId = (sf, id) => findAll(sf, (n) => jsxOpen(n) && attrStr(n, 'testID') === id);
  const byTag = (sf, tag) => findAll(sf, (n) => jsxOpen(n) && n.tagName.getText(sf) === tag);
  // The INNERMOST conditional that renders this element (G-035: read the
  // nearest one only, never a concatenation of every ancestor's): the first
  // ternary / && ancestor whose branch holds it, walking out through wrapper
  // elements (a ScrollView around the section) but not out of the component.
  const isFnLike = (n) => ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n) || ts.isArrowFunction(n);
  const innermostGuard = (el) => {
    let child = ts.isJsxOpeningElement(el) ? el.parent : el;
    for (let p = child.parent; p; child = p, p = p.parent) {
      if (isFnLike(p)) return null;
      if (ts.isConditionalExpression(p) && child !== p.condition) {
        return { test: p.condition, other: child === p.whenTrue ? p.whenFalse : p.whenTrue, inTrue: child === p.whenTrue };
      }
      if (ts.isBinaryExpression(p) && p.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken && child === p.right) {
        return { test: p.left, other: null, inTrue: true };
      }
    }
    return null;
  };
  // Is `test` the predicate itself: `useTesterSurface()`, or a const bound to it?
  const isPredicate = (sf, test) => {
    let t = test;
    while (ts.isParenthesizedExpression(t)) t = t.expression;
    const isCall = (n) => n && ts.isCallExpression(n) && ts.isIdentifier(n.expression)
      && n.expression.text === 'useTesterSurface' && n.arguments.length === 0;
    if (isCall(t)) return true;
    if (!ts.isIdentifier(t)) return false;
    const decls = findAll(sf, (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === t.text);
    return decls.length === 1 && isCall(decls[0].initializer);
  };
  const importsPredicate = (sf) => sf.statements.some((s) => ts.isImportDeclaration(s) && isStr(s.moduleSpecifier)
    && s.moduleSpecifier.text === './useTesterSurface' && s.importClause && s.importClause.namedBindings
    && ts.isNamedImports(s.importClause.namedBindings)
    && s.importClause.namedBindings.elements.some((e) => e.name.text === 'useTesterSurface' && !e.propertyName));

  // 5a. Defined exactly once in mobile/src, in settings/useTesterSurface.ts.
  const PRED_FILE = path.join(SETTINGS_DIR, 'useTesterSurface.ts');
  const walkSrc = (dir, out = []) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walkSrc(p, out);
      else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
    }
    return out;
  };
  const defs = [];
  for (const abs of walkSrc(SRC)) {
    if (!fs.readFileSync(abs, 'utf8').includes('useTesterSurface')) continue;
    const sf = parseFile(abs);
    for (const d of findAll(sf, (n) => (ts.isFunctionDeclaration(n) && n.name && n.name.text === 'useTesterSurface')
      || (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === 'useTesterSurface'))) {
      defs.push({ sf, d });
    }
  }
  if (defs.length === 1 && defs[0].sf.fileName === PRED_FILE) {
    ok('5a. useTesterSurface() is defined once, in settings/useTesterSurface.ts');
  } else {
    fail('5a. useTesterSurface() is defined once, in settings/useTesterSurface.ts',
         defs.length === 0 ? 'no definition found'
           : defs.map(({ sf, d }) => line(sf, d)).join(', ') + ' — two predicates can drift apart');
  }

  // 5b. EXECUTE it over a flag truth table (G-050: run it, don't pattern-match).
  if (fs.existsSync(PRED_FILE)) {
    const js = ts.transpileModule(fs.readFileSync(PRED_FILE, 'utf8'), {
      compilerOptions: { target: ts.ScriptTarget.ES2019, module: ts.ModuleKind.CommonJS },
    }).outputText;
    const run = (dev, on) => {
      const asked = [];
      const mod = { exports: {} };
      vm.runInNewContext(js, {
        module: mod, exports: mod.exports, __DEV__: dev,
        require: (name) => {
          if (name !== '../../state/useFeatureFlags') throw new Error(`unexpected import ${name}`);
          return { useFlag: (k) => { asked.push(k); return on.includes(k); } };
        },
      });
      return { value: mod.exports.useTesterSurface(), asked };
    };
    const table = [
      [false, [], false],
      [true, [], true],
      [false, ['testing.stage_users'], true],
      [false, ['testing.timing_readout'], true],
      [false, ['testing.stage_users', 'testing.timing_readout'], true],
      [false, ['ux.help_surface'], false],
    ];
    const wrong = [];
    let askedKeys = new Set();
    for (const [dev, on, want] of table) {
      try {
        const r = run(dev, on);
        r.asked.forEach((k) => askedKeys.add(k));
        if (r.value !== want) wrong.push(`__DEV__=${dev}, flags=[${on.join(', ')}] → ${r.value}, want ${want}`);
      } catch (e) { wrong.push(`threw: ${e.message}`); }
    }
    for (const k of ['testing.stage_users', 'testing.timing_readout']) {
      if (!askedKeys.has(k)) wrong.push(`never reads ${k}`);
    }
    if (wrong.length === 0) {
      ok('5b. useTesterSurface() (executed) = __DEV__ || testing.stage_users || testing.timing_readout');
    } else {
      fail('5b. useTesterSurface() = __DEV__ || testing.stage_users || testing.timing_readout', wrong.join('; '));
    }
  }

  // 5c. The hub's Testing row is gated by the predicate, imported from its module.
  {
    const hub = parseFile(path.join(SETTINGS_DIR, 'SettingsHubScreen.tsx'));
    const rows = byTestId(hub, 'settings.hub.testing');
    const g = rows.length === 1 ? innermostGuard(rows[0]) : null;
    if (rows.length === 1 && g && g.inTrue && isPredicate(hub, g.test) && importsPredicate(hub)) {
      ok(`5c. the hub's Testing row (${line(hub, rows[0])}) renders only under useTesterSurface()`);
    } else {
      fail("5c. the hub's Testing row renders only under useTesterSurface()",
           rows.length !== 1 ? `found ${rows.length} settings.hub.testing rows`
             : !g ? 'the row is unconditional — every user would see Testing'
             : !importsPredicate(hub) ? "the hub doesn't import useTesterSurface from './useTesterSurface'"
             : `gated on \`${g.test.getText(hub)}\`, not the shared predicate`);
    }
  }

  // 5d. The page body: TestingSection only under the predicate, and the other
  //     branch is the unavailable line.
  {
    const page = parseFile(path.join(SETTINGS_DIR, 'SettingsTestingScreen.tsx'));
    const mounts = byTag(page, 'TestingSection');
    const g = mounts.length === 1 ? innermostGuard(mounts[0]) : null;
    const otherHasUnavailable = !!(g && g.other
      && findAll(g.other, (n) => jsxOpen(n) && attrStr(n, 'testID') === 'settings.testing-unavailable').length);
    if (mounts.length === 1 && g && g.inTrue && isPredicate(page, g.test) && importsPredicate(page) && otherHasUnavailable) {
      ok('5d. SettingsTestingScreen renders TestingSection only under useTesterSurface(), else settings.testing-unavailable');
    } else {
      fail('5d. SettingsTestingScreen renders TestingSection only under useTesterSurface(), else the unavailable line',
           mounts.length !== 1 ? `found ${mounts.length} TestingSection mounts`
             : !g ? 'TestingSection renders unconditionally — a non-tester deep link sees an empty Testing page'
             : !isPredicate(page, g.test) ? `gated on \`${g.test.getText(page)}\`, not the shared predicate`
             : !importsPredicate(page) ? "the page doesn't import useTesterSurface from './useTesterSurface'"
             : 'the false branch is not the settings.testing-unavailable line');
    }
  }

  // 5e. #363's TimingReadoutRow (head-eng ruling 11) is mounted directly
  //     AFTER <TestingSection> on the Testing page (under its "Testing"
  //     banner), imported from the components path, with its default testID
  //     (no props) and no gate of its own: the component self-gates on
  //     `testing.timing_readout`, so the only conditional around it is the
  //     page's shared D-7 predicate, the same one TestingSection sits under.
  {
    const page = parseFile(path.join(SETTINGS_DIR, 'SettingsTestingScreen.tsx'));
    const imported = page.statements.some((s) => ts.isImportDeclaration(s) && isStr(s.moduleSpecifier)
      && s.moduleSpecifier.text === '../../components/TimingReadoutRow' && s.importClause
      && s.importClause.namedBindings && ts.isNamedImports(s.importClause.namedBindings)
      && s.importClause.namedBindings.elements.some((e) => e.name.text === 'TimingReadoutRow' && !e.propertyName));
    const mounts = byTag(page, 'TimingReadoutRow');
    const m = mounts.length === 1 ? mounts[0] : null;
    const g = m ? innermostGuard(m) : null;
    const sections = byTag(page, 'TestingSection');
    const sg = sections.length === 1 ? innermostGuard(sections[0]) : null;
    const asNode = (el) => (el && ts.isJsxOpeningElement(el) ? el.parent : el);
    const node = asNode(m);
    const sectionNode = sections.length === 1 ? asNode(sections[0]) : null;
    const holder = node && ts.isJsxElement(node.parent) ? node.parent : null;
    const kids = holder ? holder.children.filter((c) => !(ts.isJsxText(c) && !c.text.trim())) : [];
    const at = kids.indexOf(node);
    const prev = at > 0 ? kids[at - 1] : null;
    const problems = [
      [imported, "no `import { TimingReadoutRow } from '../../components/TimingReadoutRow'`"],
      [mounts.length === 1, `found ${mounts.length} <TimingReadoutRow> mounts, want 1`],
      [!m || m.attributes.properties.length === 0,
        m ? `passes props (${m.attributes.getText(page)}); the default testID settings.testing.timing-readout must stand` : ''],
      [!m || (g && sg && g.inTrue && g.test === sg.test && isPredicate(page, g.test)),
        !g ? 'renders outside the useTesterSurface() branch'
          : `gated on \`${g.test.getText(page)}\`, not only the page's shared predicate — the row gates itself`],
      [!m || (!!sectionNode && prev === sectionNode),
        `not the child immediately after <TestingSection> (it follows ${prev ? prev.getText(page).slice(0, 40) : 'nothing'})`],
    ].filter(([okay]) => !okay).map(([, why]) => why);
    if (problems.length === 0) {
      ok(`5e. SettingsTestingScreen mounts <TimingReadoutRow /> right after <TestingSection> (${line(page, m)}), ungated, default testID`);
    } else {
      fail('5e. SettingsTestingScreen mounts <TimingReadoutRow /> right after <TestingSection>, ungated, with its default testID',
           problems.join('; '));
    }
  }

  // 6. D-6: no Screen field in the sheet, but `screen` is still submitted.
  {
    const sheet = parseFile(path.join(MOBILE_ROOT, 'src', 'components', 'FeedbackSheet.tsx'));
    const inputs = byTag(sheet, 'TextInput');
    const extra = inputs.filter((n) => attrStr(n, 'testID') !== 'feedback.note-input');
    const screenLabel = findAll(sheet, (n) => (ts.isJsxText(n) && n.text.trim() === 'Screen')
      || (jsxOpen(n) && attrStr(n, 'accessibilityLabel') === 'Screen'));
    if (inputs.length === 1 && extra.length === 0 && screenLabel.length === 0) {
      ok('6a. FeedbackSheet renders no Screen field — its only TextInput is feedback.note-input');
    } else {
      fail('6a. FeedbackSheet renders no Screen field',
           [...extra.map((n) => `extra TextInput at ${line(sheet, n)}`),
            ...screenLabel.map((n) => `"Screen" label at ${line(sheet, n)}`),
            ...(inputs.length === 0 ? ['no note TextInput found — the parse is vacuous'] : [])].join('; '));
    }

    const adds = findAll(sheet, (n) => ts.isCallExpression(n) && ts.isIdentifier(n.expression)
      && n.expression.text === 'add' && n.arguments[0] && ts.isObjectLiteralExpression(n.arguments[0]));
    const screenProp = adds.length === 1 ? adds[0].arguments[0].properties.find((p) =>
      ts.isPropertyAssignment(p) && p.name.getText(sheet) === 'screen') : null;
    let init = screenProp && screenProp.initializer;
    const fallsBack = !!(init && ts.isBinaryExpression(init) && init.operatorToken.kind === ts.SyntaxKind.BarBarToken
      && isStr(init.right) && init.right.text === 'Unknown'
      && findAll(init.left, (n) => ts.isIdentifier(n) && n.text === 'screen').length > 0);
    if (fallsBack) ok("6b. FeedbackSheet still submits `screen` (screen … || 'Unknown') in its add() call");
    else fail("6b. FeedbackSheet still submits `screen`, falling back to 'Unknown'",
              adds.length !== 1 ? `found ${adds.length} add({...}) calls`
                : !screenProp ? 'the add() body has no screen property — the API needs a non-empty screen'
                : `screen: ${screenProp.initializer.getText(sheet)} — want the state value with an 'Unknown' fallback`);
  }
}

console.log(failures === 0
  ? `\nAll settings IA checks passed — ${Object.keys(SECTION_OWNER).length} section modules, `
    + `${ROWS.length} rows, each in exactly one place.`
  : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
