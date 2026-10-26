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
// Plus #363's timing readout (head-eng ruling 11), on the TypeScript AST so
// comments can't satisfy it: T1 the Testing page mounts TimingReadoutRow
// right after TestingSection, ungated, default testID; T2 the hub's Testing
// row shows on exactly __DEV__ || testing.stage_users || testing.timing_readout
// (in the branch taken when that is true); T3 neither tester flag is a
// launched default (D-166); T4 the readout is mounted nowhere else.
//
// If §4 changes, change the tables below in the same commit. A row added to
// the app and not added here fails as "not in the §4 migration map" — that
// is the check working, not the check being stale.
//
// Run: node tests/check-settings-ia.js   (or: npm run test:settings-ia)

'use strict';

const fs = require('fs');
const path = require('path');

const SETTINGS_DIR = path.join(__dirname, '..', 'src', 'screens', 'settings');
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
  { row: 'Test feedback',                 marker: '>Test feedback<',                    owner: 'TestingSection.tsx' },
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

// ── T. #363's timing readout (head-eng ruling 11), on the TypeScript AST ──
// The readout self-gates on `testing.timing_readout`; the operator's phone
// gets ONLY that flag, so it must also open the hub's Testing row.
{
  let ts;
  try { ts = require('typescript'); } catch {
    console.error('typescript not resolvable — run `npm install` in mobile/ first.');
    process.exit(2);
  }
  const parseFile = (abs) => ts.createSourceFile(abs, fs.readFileSync(abs, 'utf8'), ts.ScriptTarget.Latest, true,
    abs.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const findAll = (root, pred) => {
    const out = [];
    const visit = (n) => { if (pred(n)) out.push(n); ts.forEachChild(n, visit); };
    visit(root);
    return out;
  };
  const isStr = (n) => !!n && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n));
  const jsxOpen = (n) => ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n);
  const byTag = (sf, tag) => findAll(sf, (n) => jsxOpen(n) && n.tagName.getText(sf) === tag);
  const asNode = (el) => (el && ts.isJsxOpeningElement(el) ? el.parent : el);
  const attrStr = (el, name) => {
    const a = el.attributes.properties.find((p) => ts.isJsxAttribute(p) && p.name.getText() === name);
    if (!a || !a.initializer) return null;
    if (isStr(a.initializer)) return a.initializer.text;
    if (ts.isJsxExpression(a.initializer) && isStr(a.initializer.expression)) return a.initializer.expression.text;
    return null;
  };
  const isFnLike = (n) => ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n) || ts.isArrowFunction(n);
  // The innermost ternary / && that renders `el`, inside its component, and
  // whether `el` sits in the branch taken when that condition is TRUE.
  const innermostGuardInfo = (el) => {
    let child = asNode(el);
    for (let p = child.parent; p; child = p, p = p.parent) {
      if (isFnLike(p)) return null;
      if (ts.isConditionalExpression(p) && child !== p.condition) {
        return { cond: p.condition, whenTrue: child === p.whenTrue };
      }
      if (ts.isBinaryExpression(p) && p.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken
          && child === p.right) return { cond: p.left, whenTrue: true };
    }
    return null;
  };
  const innermostGuard = (el) => (innermostGuardInfo(el) || {}).cond || null;

  // T1. The Testing page mounts the readout from components/, once, with no
  //     props (its default testID), under no conditional, as the child
  //     immediately after <TestingSection> (under the "Testing" banner).
  {
    const page = parseFile(path.join(SETTINGS_DIR, 'SettingsTestingScreen.tsx'));
    const imported = page.statements.some((s) => ts.isImportDeclaration(s) && isStr(s.moduleSpecifier)
      && s.moduleSpecifier.text === '../../components/TimingReadoutRow' && s.importClause
      && s.importClause.namedBindings && ts.isNamedImports(s.importClause.namedBindings)
      && s.importClause.namedBindings.elements.some((e) => e.name.text === 'TimingReadoutRow' && !e.propertyName));
    const mounts = byTag(page, 'TimingReadoutRow');
    const m = mounts.length === 1 ? mounts[0] : null;
    const sections = byTag(page, 'TestingSection');
    const node = asNode(m);
    const holder = node && ts.isJsxElement(node.parent) ? node.parent : null;
    const kids = holder ? holder.children.filter((c) => !(ts.isJsxText(c) && !c.text.trim())) : [];
    const prev = kids.indexOf(node) > 0 ? kids[kids.indexOf(node) - 1] : null;
    const guard = m ? innermostGuard(m) : null;
    const problems = [
      [imported, "no `import { TimingReadoutRow } from '../../components/TimingReadoutRow'`"],
      [mounts.length === 1, `found ${mounts.length} <TimingReadoutRow> mounts, want 1`],
      [!m || m.attributes.properties.length === 0,
        m ? `passes props (${m.attributes.getText(page)}); the default testID settings.testing.timing-readout must stand` : ''],
      [!m || !guard, guard ? `gated on \`${guard.getText(page)}\` — the row gates itself` : ''],
      [!m || (sections.length === 1 && prev === asNode(sections[0])),
        `not the child immediately after <TestingSection> (it follows ${prev ? prev.getText(page).slice(0, 40) : 'nothing'})`],
    ].filter(([okay]) => !okay).map(([, why]) => why);
    if (problems.length === 0) {
      const at = page.getLineAndCharacterOfPosition(m.getStart(page)).line + 1;
      ok(`T1. SettingsTestingScreen mounts <TimingReadoutRow /> right after <TestingSection> (:${at}), ungated, default testID`);
    } else {
      fail('T1. SettingsTestingScreen mounts <TimingReadoutRow /> right after <TestingSection>, ungated, with its default testID',
           problems.join('; '));
    }
  }

  // T2. The hub's Testing row shows on exactly `__DEV__ || testing.stage_users
  //     || testing.timing_readout`: an || chain of __DEV__ and flag reads (an
  //     inline useFlag('…') / useTimingReadoutEnabled() call, or a const bound
  //     to one), so a readout-only device reaches the readout. The row must be
  //     in the TRUE branch: `cond ? null : <Row>` would show it to everyone else.
  {
    const hub = parseFile(path.join(SETTINGS_DIR, 'SettingsHubScreen.tsx'));
    const rows = findAll(hub, (n) => jsxOpen(n) && attrStr(n, 'testID') === 'settings.hub.testing');
    const info = rows.length === 1 ? innermostGuardInfo(rows[0]) : null;
    const cond = info ? info.cond : null;
    const flagOf = (e) => {
      while (e && ts.isParenthesizedExpression(e)) e = e.expression;
      if (!e) return null;
      if (ts.isCallExpression(e) && ts.isIdentifier(e.expression)) {
        if (e.expression.text === 'useFlag' && isStr(e.arguments[0])) return e.arguments[0].text;
        if (e.expression.text === 'useTimingReadoutEnabled' && e.arguments.length === 0) return 'testing.timing_readout';
        return null;
      }
      if (ts.isIdentifier(e)) {
        if (e.text === '__DEV__') return '__DEV__';
        const decls = findAll(hub, (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === e.text);
        return decls.length === 1 && decls[0].initializer ? flagOf(decls[0].initializer) : null;
      }
      return null;
    };
    const operands = [];
    const flatten = (e) => {
      while (ts.isParenthesizedExpression(e)) e = e.expression;
      if (ts.isBinaryExpression(e) && e.operatorToken.kind === ts.SyntaxKind.BarBarToken) {
        flatten(e.left); flatten(e.right);
      } else operands.push(e);
    };
    if (cond) flatten(cond);
    const read = operands.map(flagOf);
    const want = ['__DEV__', 'testing.stage_users', 'testing.timing_readout'];
    const exact = read.every(Boolean) && read.length === want.length && want.every((k) => read.includes(k));
    if (rows.length === 1 && cond && info.whenTrue && exact) {
      ok(`T2. the hub's Testing row shows on \`${cond.getText(hub)}\` = __DEV__ || testing.stage_users || testing.timing_readout`);
    } else {
      fail("T2. the hub's Testing row shows on __DEV__ || testing.stage_users || testing.timing_readout",
           rows.length !== 1 ? `found ${rows.length} settings.hub.testing rows`
             : !cond ? 'the row is unconditional — every user would see Testing'
             : !info.whenTrue ? `the row is in the FALSE branch of \`${cond.getText(hub)}\` — every non-tester would see Testing`
             : `gated on \`${cond.getText(hub)}\`, which reads [${read.map((k) => k || '?').join(', ')}]`
               + (read.includes('testing.timing_readout') ? '' : ' — a readout-only device cannot reach the readout'));
    }
  }

  // T3 (D-166). Neither tester flag is a LAUNCHED default. Those baked defaults
  //     apply from first paint, before the first flag fetch, so either key there
  //     would show Testing (and the readout) to every fresh install.
  {
    const flagsFile = path.join(__dirname, '..', 'src', 'state', 'useFeatureFlags.ts');
    const sf = parseFile(flagsFile);
    const decls = findAll(sf, (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name)
      && n.name.text === 'LAUNCHED_FLAG_DEFAULTS');
    const obj = decls.length === 1 && decls[0].initializer
      && ts.isObjectLiteralExpression(decls[0].initializer) ? decls[0].initializer : null;
    const keys = obj ? obj.properties.map((p) => (p.name && (isStr(p.name) || ts.isIdentifier(p.name)) ? p.name.text : null)) : [];
    const banned = ['testing.timing_readout', 'testing.stage_users'].filter((k) => keys.includes(k));
    const opaque = obj ? obj.properties.filter((p) => !p.name).length : 0;
    if (obj && banned.length === 0 && opaque === 0) {
      ok(`T3. LAUNCHED_FLAG_DEFAULTS (${keys.length} keys) holds neither testing.timing_readout nor testing.stage_users`);
    } else {
      fail('T3. LAUNCHED_FLAG_DEFAULTS holds neither testing.timing_readout nor testing.stage_users',
           !obj ? 'LAUNCHED_FLAG_DEFAULTS object literal not found in state/useFeatureFlags.ts'
             : opaque ? `${opaque} spread/computed entr${opaque === 1 ? 'y' : 'ies'}, so its keys can't be checked`
             : `${banned.join(' and ')} would be on for every fresh install until its first flag fetch`);
    }
  }

  // T4. The readout is mounted ONLY on the Testing page: any other mount (the
  //     hub, a tab screen) would escape the Testing row's tester gate.
  {
    const SRC = path.join(__dirname, '..', 'src');
    const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) =>
      d.isDirectory() ? walk(path.join(dir, d.name)) : d.name.endsWith('.tsx') ? [path.join(dir, d.name)] : []);
    const where = [];
    for (const abs of walk(SRC)) {
      if (!fs.readFileSync(abs, 'utf8').includes('TimingReadoutRow')) continue;
      const sf = parseFile(abs);
      for (const el of byTag(sf, 'TimingReadoutRow')) {
        where.push(`${path.relative(SRC, abs)}:${sf.getLineAndCharacterOfPosition(el.getStart(sf)).line + 1}`);
      }
    }
    const only = where.length === 1 && where[0].startsWith(path.join('screens', 'settings', 'SettingsTestingScreen.tsx') + ':');
    if (only) ok(`T4. <TimingReadoutRow /> is mounted only on the Testing page (${where[0]})`);
    else fail('T4. <TimingReadoutRow /> is mounted only on the Testing page', `mounts: ${where.join(', ') || 'none'}`);
  }
}

console.log(failures === 0
  ? `\nAll settings IA checks passed — ${Object.keys(SECTION_OWNER).length} section modules, `
    + `${ROWS.length} rows, each in exactly one place.`
  : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
