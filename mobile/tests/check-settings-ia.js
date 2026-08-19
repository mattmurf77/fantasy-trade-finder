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
  { row: 'Pick pricing segmented',        marker: 'settings.pick-pricing.',             owner: 'TradeValuesSection.tsx' },
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

console.log(failures === 0
  ? `\nAll settings IA checks passed — ${Object.keys(SECTION_OWNER).length} section modules, `
    + `${ROWS.length} rows, each in exactly one place.`
  : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
