#!/usr/bin/env node
// In-app feedback for the public (#354 BL-10, App Store launch).
//
// WHY THIS EXISTS. Until BL-10 the feedback surface was a TestFlight helper:
// the FAB carried a plan to be compiled out of App Store builds, and the only
// way into the inbox was a row in the Testing section, which a public user
// (no `__DEV__`, `testing.stage_users` off) never sees. So a public user got a
// count pill on every screen for notes they could not open. The operator kept
// the feature for launch ("in app feedback stays"), which makes it a set of
// claims about code SHAPE that tsc cannot see and D-056 left no simulator to
// watch:
//
//   1. NO TESTER VOCABULARY. No string literal, template literal or JSX
//      text matching "Testing →", "Test feedback", "TestFlight" or
//      "tester(s)" in the feedback surface: FeedbackSheet, FeedbackFAB,
//      FeedbackInboxScreen, state/useFeedback (the share export),
//      AboutSection, the FeedbackInbox screen options in RootNav, and the
//      flat SettingsScreen `aboutSection` (which holds its feedback row).
//   2. ROW PLACEMENT (D-3). The inbox row lives in Help & about
//      (settings/sections/AboutSection.tsx, plus the flat SettingsScreen
//      `aboutSection` that is the `account.settings_hub` rollback), never in
//      the Testing section, and never behind `__DEV__` / `stageUsersEnabled`.
//   3. ONE SUPPORT ADDRESS (BL10-R7). Across mobile/src exactly one string
//      literal, template literal or JSX text contains fleecedapp@gmail.com,
//      and it is the whole literal of an exported const; no U+FF20 look-alike
//      @ appears anywhere in mobile/src, comments included; and
//      FeedbackSheet.tsx imports that constant from its module and uses it.
//   4. SEVERITY CONTRACT. The sheet sends exactly bug | polish | idea (the
//      /api/feedback contract, the triage vocabulary and the
//      `feedback.severity.<value>` testIDs), the `FeedbackSeverity` union is
//      those three, and the three label copies (sheet, inbox, share export)
//      say the same word for each value.
//   5. THE FAB STAYS IN RELEASE BUILDS (D-5). RootNav's global
//      `<FeedbackFAB activeScreen={activeScreen} />` sits under the `Main`
//      screen with no conditional between them, nothing above it tests
//      `__DEV__` or `process.env.EXPO_PUBLIC_*`, and FeedbackFAB.tsx itself
//      never reads either.
//   6. testIDs KEPT. testid-lint cross-checks the retained (never-run) flows
//      against src, so a rename fails CI; this names the ones BL-10 must keep.
//   7. COLD-LAUNCH RETRY (D-1(b)). FeedbackFAB's mount effect calls
//      `retrySync()` after `hydrate()` resolves. App.tsx only retries on an
//      AppState change to `active`, which a cold launch never fires.
//
// And three from the #354 design/UX reviews (2026-10-23):
//   8. HELP & ABOUT ROW ORDER. Help & FAQ → Your feedback → Privacy Policy →
//      Terms of Use → Credits → Version, in AboutSection's JSX.
//   9. CREDITS IS A PLAIN BLOCK. `settings.credits` is a non-pressable View,
//      one accessible element, no chevron and no link, holding "Credits" and
//      legal's two lines verbatim in order. Nothing in AboutSection opens the
//      nflverse URL.
//  10. ONLY THE ADDRESS IS A LINK. In FeedbackSheet exactly one element has
//      accessibilityRole="link": a Text nested in another Text, hint "Opens
//      Mail", rendering {SUPPORT_EMAIL} and opening 'mailto:' + SUPPORT_EMAIL.
//
// HOW. Every check walks the TypeScript AST (the check-settings-nav.js
// pattern), so comments — which keep history like "Settings → Test feedback"
// — can neither satisfy nor trip a pin. The "is it gated?" checks are
// ABSENCE checks, so walking every ancestor is the conservative direction:
// any enclosing gate hides the row, wherever it sits (contrast G-035, which
// is about PRESENCE checks false-passing on a far ancestor).
//
// HONEST LABEL (G-035). This proves the presence and placement of exact
// wirings, not runtime behavior: pin 7 shows the call is chained after
// hydrate, not that a note actually sends. The TestFlight checklist in
// docs/plans/launch-support-policy/scope-bl10-feedback.md §3 is the runtime
// proof. Every pin was watched failing on a mutated copy before it was
// trusted (G-035/G-050).
//
// FTF_MOBILE_TEST_ROOT can point at a copy of mobile/ (sabotage runs).
// Run: node tests/check-feedback-public.js   (or: npm run test:feedback-public)

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

let failures = 0;
const ok   = (n) => console.log(`PASS  ${n}`);
const fail = (n, why) => { failures += 1; console.error(`FAIL  ${n}\n      ${why}`); };

const F = {
  about:     'src/screens/settings/sections/AboutSection.tsx',
  aboutPage: 'src/screens/settings/SettingsAboutScreen.tsx',
  testing:   'src/screens/settings/sections/TestingSection.tsx',
  flat:      'src/screens/SettingsScreen.tsx',
  sheet:     'src/components/FeedbackSheet.tsx',
  fab:       'src/components/FeedbackFAB.tsx',
  inbox:     'src/screens/FeedbackInboxScreen.tsx',
  store:     'src/state/useFeedback.ts',
  rootNav:   'src/navigation/RootNav.tsx',
};

const parsed = {};
function parse(rel) {
  if (parsed[rel]) return parsed[rel];
  const text = fs.readFileSync(path.join(ROOT, rel), 'utf8');
  const kind = rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  parsed[rel] = ts.createSourceFile(rel, text, ts.ScriptTarget.Latest, true, kind);
  return parsed[rel];
}

function findAll(root, pred) {
  const out = [];
  const visit = (n) => { if (pred(n)) out.push(n); ts.forEachChild(n, visit); };
  visit(root);
  return out;
}

const isStr = (n) => !!n && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n));

const varDecl = (root, name) => findAll(root, (n) =>
  ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name);

// A call whose first argument is the literal route name: navigate('FeedbackInbox'),
// navigation.navigate('FeedbackInbox'), navigateFromSettings('FeedbackInbox').
const inboxNavs = (root) => findAll(root, (n) =>
  ts.isCallExpression(n) && n.arguments.length > 0
  && isStr(n.arguments[0]) && n.arguments[0].text === 'FeedbackInbox');

// Every condition that guards `node`, from `node` up to (not past) `stopAt`:
// the test of a ternary it sits in a branch of, the left side of a && / || /
// ?? it is the right side of, and the condition of an if it sits under.
function guardsOf(node, stopAt) {
  const guards = [];
  let child = node;
  let p = node.parent;
  while (p && p !== stopAt) {
    if (ts.isConditionalExpression(p) && child !== p.condition) guards.push(p.condition);
    if (ts.isBinaryExpression(p) && child === p.right) {
      const k = p.operatorToken.kind;
      if (k === ts.SyntaxKind.AmpersandAmpersandToken || k === ts.SyntaxKind.BarBarToken
          || k === ts.SyntaxKind.QuestionQuestionToken) guards.push(p.left);
    }
    if (ts.isIfStatement(p) && child !== p.expression) guards.push(p.expression);
    child = p;
    p = p.parent;
  }
  return guards;
}

// Does this subtree read __DEV__ / stageUsersEnabled / 'testing.stage_users' /
// process.env.EXPO_PUBLIC_*? AST identifiers and literals only, never comments.
function mentions(node, { dev = false, stage = false, expoEnv = false }) {
  const hits = [];
  findAll(node, (n) => {
    if (dev && ts.isIdentifier(n) && n.text === '__DEV__') hits.push('__DEV__');
    if (stage && ts.isIdentifier(n) && n.text === 'stageUsersEnabled') hits.push('stageUsersEnabled');
    if (stage && isStr(n) && n.text === 'testing.stage_users') hits.push("'testing.stage_users'");
    if (expoEnv && ts.isPropertyAccessExpression(n) && ts.isIdentifier(n.name)
        && n.name.text.startsWith('EXPO_PUBLIC_')
        && n.expression.getText() === 'process.env') hits.push(`process.env.${n.name.text}`);
    if (expoEnv && ts.isElementAccessExpression(n) && n.expression.getText() === 'process.env'
        && isStr(n.argumentExpression) && n.argumentExpression.text.startsWith('EXPO_PUBLIC_')) {
      hits.push(`process.env['${n.argumentExpression.text}']`);
    }
    return false;
  });
  return hits;
}

const at = (sf, n) => `${sf.fileName}:${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1}`;

// Every user-visible text node in a subtree: string and template literals
// (head, middles and tail) and JSX text. Comments are trivia, never nodes.
function textNodes(root) {
  const out = [];
  findAll(root, (n) => {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) out.push({ node: n, text: n.text });
    else if (ts.isTemplateExpression(n)) {
      out.push({ node: n, text: [n.head.text, ...n.templateSpans.map((s) => s.literal.text)].join('${}') });
    } else if (ts.isJsxText(n) && n.text.trim()) out.push({ node: n, text: n.text });
    return false;
  });
  // A TemplateExpression's own literal parts are not separate nodes above,
  // and import specifiers are module paths, not copy.
  return out.filter(({ node }) => !(node.parent && ts.isImportDeclaration(node.parent)));
}

// ── 1. No tester vocabulary on the feedback surface ──────────────────────
{
  const TESTER = /Testing\s*→|Test feedback|TestFlight|\btesters?\b/i;
  const scopes = [];
  for (const rel of [F.sheet, F.fab, F.inbox, F.store, F.about]) scopes.push([rel, parse(rel)]);

  const nav = parse(F.rootNav);
  const inboxScreen = findAll(nav, (n) => (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n))
    && n.tagName.getText(nav) === 'Stack.Screen'
    && n.attributes.properties.some((a) => ts.isJsxAttribute(a) && a.name.getText(nav) === 'name'
      && a.initializer && isStr(a.initializer) && a.initializer.text === 'FeedbackInbox'));
  const flat = parse(F.flat);
  const [flatAbout] = varDecl(flat, 'aboutSection');

  const problems = [];
  if (inboxScreen.length !== 1) problems.push(`found ${inboxScreen.length} <Stack.Screen name="FeedbackInbox"> in RootNav (want 1)`);
  else scopes.push([`${F.rootNav} (FeedbackInbox screen options)`, inboxScreen[0]]);
  if (!flatAbout) problems.push(`no aboutSection in ${F.flat}`);
  else scopes.push([`${F.flat} (aboutSection)`, flatAbout]);

  let scanned = 0;
  for (const [, node] of scopes) {
    const sf = node.getSourceFile();
    for (const { node: t, text } of textNodes(node)) {
      scanned += 1;
      const m = text.match(TESTER);
      if (m) problems.push(`${at(sf, t)}: "${m[0]}" in ${JSON.stringify(text.trim().slice(0, 90))}`);
    }
  }
  if (problems.length === 0 && scanned > 0) {
    ok(`1. no tester vocabulary in ${scanned} user-visible strings across the ${scopes.length} feedback-surface scopes`);
  } else {
    fail('1. no tester vocabulary ("Testing →", "Test feedback", "TestFlight", "tester(s)") on the feedback surface',
         problems.length ? problems.join('; ') : 'scanned no strings — the parse below is vacuous');
  }
}

// ── 3. One support address, ASCII @, imported by the sheet ───────────────
{
  const ADDRESS = 'fleecedapp@gmail.com';
  const walk = (dir, out = []) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p, out);
      else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
    }
    return out;
  };
  const srcFiles = walk(path.join(ROOT, 'src')).map((abs) => path.relative(ROOT, abs).split(path.sep).join('/'));

  const fullWidth = [];
  const hits = [];
  for (const rel of srcFiles) {
    const raw = fs.readFileSync(path.join(ROOT, rel), 'utf8');
    raw.split('\n').forEach((line, i) => { if (line.includes('＠')) fullWidth.push(`${rel}:${i + 1}`); });
    if (!raw.toLowerCase().includes('fleecedapp')) continue;
    const sf = parse(rel);
    for (const { node, text } of textNodes(sf)) {
      if (text.toLowerCase().includes('fleecedapp')) hits.push({ sf, node, text });
    }
  }

  // 3a. Exactly one literal holds the address, and it is an exported const.
  let constName = null;
  let constFile = null;
  const only = hits.length === 1 ? hits[0] : null;
  const decl = only && ts.isStringLiteral(only.node) && only.node.parent
    && ts.isVariableDeclaration(only.node.parent) ? only.node.parent : null;
  const exported = !!(decl && decl.parent && decl.parent.parent && ts.isVariableStatement(decl.parent.parent)
    && (decl.parent.parent.modifiers || []).some((m) => m.kind === ts.SyntaxKind.ExportKeyword)
    && (decl.parent.flags & ts.NodeFlags.Const));
  if (only && only.text === ADDRESS && decl && exported && ts.isIdentifier(decl.name)) {
    constName = decl.name.text;
    constFile = only.sf.fileName;
    ok(`3a. exactly one literal in mobile/src holds the support address: export const ${constName} (${at(only.sf, only.node)})`);
  } else {
    fail(`3a. exactly one literal in mobile/src holds ${ADDRESS}, the exported const`,
         hits.length === 0 ? 'no literal holds the address'
           : hits.length > 1 ? `${hits.length} literals hold it: ${hits.map((h) => at(h.sf, h.node)).join(', ')} — import the constant instead`
           : `${at(only.sf, only.node)} is ${JSON.stringify(only.text)}, `
             + (only.text !== ADDRESS ? 'not exactly the address' : 'not the initializer of an exported const'));
  }

  // 3b. No full-width @ anywhere, comments included.
  if (fullWidth.length === 0) ok('3b. no U+FF20 (full-width @) anywhere in mobile/src');
  else fail('3b. no U+FF20 (full-width @) anywhere in mobile/src', `found at ${fullWidth.join(', ')}`);

  // 3c. FeedbackSheet imports the constant from its module and uses it.
  if (constName) {
    const sheet = parse(F.sheet);
    const imp = sheet.statements.find((s) => ts.isImportDeclaration(s) && isStr(s.moduleSpecifier)
      && s.importClause && s.importClause.namedBindings && ts.isNamedImports(s.importClause.namedBindings)
      && s.importClause.namedBindings.elements.some((e) => (e.propertyName || e.name).text === constName)
      && path.posix.normalize(path.posix.join(path.posix.dirname(F.sheet), s.moduleSpecifier.text))
           === constFile.replace(/\.tsx?$/, ''));
    const local = imp && imp.importClause.namedBindings.elements.find((e) => (e.propertyName || e.name).text === constName).name.text;
    const uses = local ? findAll(sheet, (n) => ts.isIdentifier(n) && n.text === local
      && !(n.parent && (ts.isImportSpecifier(n.parent)))).length : 0;
    if (imp && uses > 0) ok(`3c. FeedbackSheet.tsx imports ${constName} from ${imp.moduleSpecifier.text} and uses it (${uses}×)`);
    else fail(`3c. FeedbackSheet.tsx imports and uses ${constName}`,
              !imp ? `no import of ${constName} from ${constFile}` : 'imported but never used');
  }
}

// ── 2. Row placement (D-3) ────────────────────────────────────────────────
{
  const GATE = { dev: true, stage: true };
  const gated = (n, stopAt) => guardsOf(n, stopAt).flatMap((g) => mentions(g, GATE));

  // 2a. AboutSection opens the inbox, ungated, and the module never reads the
  //     tester gate at all (an early `if (__DEV__) return null` is not an
  //     ancestor of the row, so it is checked as a module-wide read).
  const about = parse(F.about);
  const aboutNavs = inboxNavs(about);
  const aboutGated = aboutNavs.flatMap((n) => gated(n, about).map((g) => `${at(about, n)} under ${g}`));
  const aboutReads = mentions(about, GATE);
  if (aboutNavs.length === 1 && aboutGated.length === 0 && aboutReads.length === 0) {
    ok(`2a. AboutSection.tsx opens FeedbackInbox (${at(about, aboutNavs[0])}), ungated`);
  } else {
    fail('2a. AboutSection.tsx opens FeedbackInbox exactly once, ungated',
         aboutNavs.length !== 1 ? `found ${aboutNavs.length} FeedbackInbox navigations (want 1)`
           : aboutGated.length ? `gated: ${aboutGated.join('; ')}`
           : `the module reads the tester gate: ${aboutReads.join(', ')}`);
  }

  // 2b. ...and its host page mounts it ungated, handing it `navigate` (the
  //     row's only way to push the inbox).
  const aboutMounts = (sf, root) => findAll(root, (n) =>
    (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) && n.tagName.getText(sf) === 'AboutSection');
  const hasNavigate = (el) => el.attributes.properties.some((a) =>
    ts.isJsxAttribute(a) && a.name.getText() === 'navigate' && a.initializer);
  const page = parse(F.aboutPage);
  const mounts = aboutMounts(page, page);
  const mountGated = mounts.flatMap((n) => gated(n, page));
  if (mounts.length === 1 && mountGated.length === 0 && hasNavigate(mounts[0])) {
    ok('2b. SettingsAboutScreen.tsx mounts <AboutSection navigate={…} /> ungated');
  } else {
    fail('2b. SettingsAboutScreen.tsx mounts <AboutSection navigate={…} /> once, ungated',
         mounts.length !== 1 ? `found ${mounts.length} mounts`
           : mountGated.length ? `gated on ${mountGated.join(', ')}` : 'no navigate prop passed');
  }

  // 2c. TestingSection never opens the inbox.
  const testing = parse(F.testing);
  const testingNavs = inboxNavs(testing);
  if (testingNavs.length === 0) ok('2c. TestingSection.tsx has no FeedbackInbox navigation');
  else fail('2c. TestingSection.tsx has no FeedbackInbox navigation',
            `still at ${testingNavs.map((n) => at(testing, n)).join(', ')} — the row is tester-only again`);

  // 2d-2f. The flat SettingsScreen: aboutSection renders the same AboutSection
  //        (so the row comes from 2a's module), testingSection has no inbox
  //        row, and every place `{aboutSection}` is mounted is ungated.
  const flat = parse(F.flat);
  const [aboutDecl, ...aboutExtra] = varDecl(flat, 'aboutSection');
  const [testingDecl, ...testingExtra] = varDecl(flat, 'testingSection');
  if (!aboutDecl || aboutExtra.length || !testingDecl || testingExtra.length) {
    fail('2d. SettingsScreen.tsx declares aboutSection and testingSection once each',
         `aboutSection: ${aboutExtra.length + (aboutDecl ? 1 : 0)}, testingSection: `
           + `${testingExtra.length + (testingDecl ? 1 : 0)} — the parse below would be vacuous`);
  } else {
    const flatMounts = aboutMounts(flat, aboutDecl);
    const flatGated = flatMounts.flatMap((n) => gated(n, aboutDecl).map((g) => `${at(flat, n)} under ${g}`));
    const inlineNavs = inboxNavs(aboutDecl);
    if (flatMounts.length === 1 && flatGated.length === 0 && hasNavigate(flatMounts[0]) && inlineNavs.length === 0) {
      ok(`2d. SettingsScreen.tsx aboutSection renders <AboutSection navigate={…} /> (${at(flat, flatMounts[0])}), ungated`);
    } else {
      fail('2d. SettingsScreen.tsx aboutSection renders <AboutSection navigate={…} /> once, ungated',
           flatMounts.length !== 1 ? `found ${flatMounts.length} AboutSection mounts`
             : flatGated.length ? flatGated.join('; ')
             : !hasNavigate(flatMounts[0]) ? 'no navigate prop passed'
             : `an inline FeedbackInbox row too (${inlineNavs.map((n) => at(flat, n)).join(', ')}) — it would render twice`);
    }

    const tNavs = inboxNavs(testingDecl);
    if (tNavs.length === 0) ok('2e. SettingsScreen.tsx testingSection has no FeedbackInbox navigation');
    else fail('2e. SettingsScreen.tsx testingSection has no FeedbackInbox navigation',
              `still at ${tNavs.map((n) => at(flat, n)).join(', ')}`);

    // Every reference except the declaration's own name, wherever it sits —
    // `{__DEV__ ? aboutSection : null}` must count as a (gated) mount, not be
    // skipped for not being a bare `{aboutSection}`. Two: one per settings_v2
    // branch (v2 live + legacy), as the flat list has today.
    const uses = findAll(flat, (n) => ts.isIdentifier(n) && n.text === 'aboutSection'
      && n !== aboutDecl.name);
    const useGated = uses.flatMap((n) => gated(n, flat).map((g) => `${at(flat, n)} under ${g}`));
    if (uses.length >= 2 && useGated.length === 0) {
      ok(`2f. every aboutSection mount in SettingsScreen.tsx is ungated (${uses.length} found, both settings_v2 branches)`);
    } else {
      fail('2f. aboutSection is mounted in both settings_v2 branches of SettingsScreen.tsx, ungated',
           uses.length < 2 ? `only ${uses.length} mount(s) found` : useGated.join('; '));
    }
  }
}

// ── 4. Severity contract ──────────────────────────────────────────────────
{
  const VALUES = ['bug', 'polish', 'idea'];
  const maps = {};   // source → { value: label }

  // 4a. The union.
  const store = parse(F.store);
  const [alias] = findAll(store, (n) => ts.isTypeAliasDeclaration(n) && n.name.text === 'FeedbackSeverity');
  const members = alias && ts.isUnionTypeNode(alias.type)
    ? alias.type.types.map((t) => (ts.isLiteralTypeNode(t) && isStr(t.literal) ? t.literal.text : t.getText(store)))
    : null;
  if (members && members.length === 3 && VALUES.every((v) => members.includes(v))) {
    ok(`4a. FeedbackSeverity is exactly ${VALUES.map((v) => `'${v}'`).join(' | ')}`);
  } else {
    fail('4a. FeedbackSeverity is exactly bug | polish | idea',
         members ? `union is ${members.join(' | ')}` : 'type alias FeedbackSeverity not found as a union');
  }

  // 4b. The sheet's options: values in order, plus their labels.
  const sheet = parse(F.sheet);
  const [optsDecl] = varDecl(sheet, 'SEVERITY_OPTIONS');
  const prop = (obj, name) => {
    const p = obj.properties.find((q) => ts.isPropertyAssignment(q) && q.name.getText(sheet) === name);
    return p && isStr(p.initializer) ? p.initializer.text : null;
  };
  if (optsDecl && optsDecl.initializer && ts.isArrayLiteralExpression(optsDecl.initializer)) {
    const opts = optsDecl.initializer.elements.filter(ts.isObjectLiteralExpression)
      .map((o) => ({ value: prop(o, 'value'), label: prop(o, 'label') }));
    const values = opts.map((o) => o.value);
    if (JSON.stringify(values) === JSON.stringify(VALUES)
        && opts.length === optsDecl.initializer.elements.length) {
      ok(`4b. FeedbackSheet SEVERITY_OPTIONS values are exactly ${JSON.stringify(VALUES)}`);
    } else {
      fail('4b. FeedbackSheet SEVERITY_OPTIONS values are exactly bug, polish, idea',
           `values are ${JSON.stringify(values)} — the /api/feedback contract and the `
             + 'feedback.severity.<value> testIDs depend on these three');
    }
    maps['FeedbackSheet SEVERITY_OPTIONS'] = Object.fromEntries(opts.map((o) => [o.value, o.label]));
  } else {
    fail('4b. FeedbackSheet SEVERITY_OPTIONS found', 'no array-literal SEVERITY_OPTIONS in FeedbackSheet.tsx');
  }

  // 4c. The inbox's SEV_LABEL record.
  const inbox = parse(F.inbox);
  const [labelDecl] = varDecl(inbox, 'SEV_LABEL');
  if (labelDecl && labelDecl.initializer && ts.isObjectLiteralExpression(labelDecl.initializer)) {
    maps['FeedbackInboxScreen SEV_LABEL'] = Object.fromEntries(labelDecl.initializer.properties
      .filter(ts.isPropertyAssignment)
      .map((p) => [ts.isIdentifier(p.name) || isStr(p.name) ? p.name.text : p.name.getText(inbox),
                   isStr(p.initializer) ? p.initializer.text : null]));
  } else {
    fail('4c. FeedbackInboxScreen SEV_LABEL found', 'no object-literal SEV_LABEL in FeedbackInboxScreen.tsx');
  }

  // 4d. The share export's `sev` ternary chain in formatFeedbackAsMarkdown:
  //     `x.severity === 'bug' ? 'Bug' : x.severity === 'polish' ? 'Polish' : 'Idea'`.
  //     The final else belongs to whichever single value no branch named.
  const [fmt] = findAll(store, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === 'formatFeedbackAsMarkdown');
  const [sevDecl] = fmt ? varDecl(fmt, 'sev') : [];
  const chain = {};
  let node = sevDecl && sevDecl.initializer;
  while (node && ts.isParenthesizedExpression(node)) node = node.expression;
  let chainOk = !!node;
  while (node && ts.isConditionalExpression(node)) {
    const c = node.condition;
    if (ts.isBinaryExpression(c) && c.operatorToken.kind === ts.SyntaxKind.EqualsEqualsEqualsToken
        && isStr(c.right) && isStr(node.whenTrue)) {
      chain[c.right.text] = node.whenTrue.text;
    } else { chainOk = false; break; }
    node = node.whenFalse;
    while (node && ts.isParenthesizedExpression(node)) node = node.expression;
  }
  const rest = VALUES.filter((v) => !(v in chain));
  if (chainOk && isStr(node) && rest.length === 1) chain[rest[0]] = node.text;
  else chainOk = false;
  if (chainOk) maps['useFeedback formatFeedbackAsMarkdown'] = chain;
  else fail('4d. useFeedback share-export severity labels parse',
            'formatFeedbackAsMarkdown `sev` is not a `severity === <value> ? <label> : …` chain '
              + 'covering bug, polish and idea — the parse below would be vacuous');

  // 4e. Same label per value, in all three.
  const sources = Object.keys(maps);
  if (sources.length === 3) {
    const problems = [];
    for (const [src, m] of Object.entries(maps)) {
      const keys = Object.keys(m).sort();
      if (JSON.stringify(keys) !== JSON.stringify([...VALUES].sort())) {
        problems.push(`${src} keys are ${JSON.stringify(keys)}`);
      }
    }
    for (const v of VALUES) {
      const labels = sources.map((s) => maps[s][v]);
      if (new Set(labels).size !== 1 || labels.some((l) => !l)) {
        problems.push(`'${v}' → ${sources.map((s) => `${s}: ${JSON.stringify(maps[s][v])}`).join(', ')}`);
      }
    }
    if (problems.length === 0) {
      ok(`4e. the three severity label copies agree (${VALUES.map((v) => `${v} → ${maps[sources[0]][v]}`).join(', ')})`);
    } else {
      fail('4e. the three severity label copies agree', problems.join('; '));
    }
  }
}

// ── 5. The FAB stays in release builds (D-5) ──────────────────────────────
{
  const nav = parse(F.rootNav);
  const fabs = findAll(nav, (n) => (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n))
    && n.tagName.getText(nav) === 'FeedbackFAB');
  const global = fabs.filter((n) => n.attributes.properties.some((a) =>
    ts.isJsxAttribute(a) && a.name.getText(nav) === 'activeScreen'
    && a.initializer && ts.isJsxExpression(a.initializer)
    && a.initializer.expression && a.initializer.expression.getText(nav) === 'activeScreen'));

  if (global.length !== 1) {
    fail('5a. RootNav mounts the global <FeedbackFAB activeScreen={activeScreen} /> exactly once',
         `found ${global.length} — the parse below would be vacuous`);
  } else {
    const fab = global[0];
    // The enclosing <Stack.Screen name="Main">.
    let mainEl = null;
    for (let p = fab.parent; p; p = p.parent) {
      if (ts.isJsxElement(p) && p.openingElement.tagName.getText(nav) === 'Stack.Screen') {
        const nameAttr = p.openingElement.attributes.properties.find((a) =>
          ts.isJsxAttribute(a) && a.name.getText(nav) === 'name');
        if (nameAttr && isStr(nameAttr.initializer) && nameAttr.initializer.text === 'Main') { mainEl = p; break; }
      }
    }
    if (!mainEl) {
      fail('5a. the global FeedbackFAB sits under <Stack.Screen name="Main">', `${at(nav, fab)} is not inside it`);
    } else {
      const inner = guardsOf(fab, mainEl);
      if (inner.length === 0) ok(`5a. the global FeedbackFAB (${at(nav, fab)}) renders unconditionally inside Main`);
      else fail('5a. the global FeedbackFAB renders unconditionally inside Main',
                `conditional on ${inner.map((g) => g.getText(nav)).join(' / ')}`);
    }
    const buildGates = guardsOf(fab, nav).flatMap((g) => mentions(g, { dev: true, expoEnv: true }));
    if (buildGates.length === 0) ok('5b. nothing above the global FeedbackFAB tests __DEV__ or process.env.EXPO_PUBLIC_*');
    else fail('5b. nothing above the global FeedbackFAB tests __DEV__ or process.env.EXPO_PUBLIC_*',
              `gated on ${buildGates.join(', ')} — App Store builds would compile the FAB out (D-5 retired that plan)`);
  }

  const fabSrc = parse(F.fab);
  const reads = mentions(fabSrc, { dev: true, expoEnv: true });
  if (reads.length === 0) ok('5c. FeedbackFAB.tsx never reads __DEV__ or process.env.EXPO_PUBLIC_*');
  else fail('5c. FeedbackFAB.tsx never reads __DEV__ or process.env.EXPO_PUBLIC_*',
            `reads ${reads.join(', ')} — a build gate inside the component hides it just as well`);
}

// ── 6. testIDs kept ───────────────────────────────────────────────────────
{
  const idsIn = (rel) => {
    const sf = parse(rel);
    const out = { plain: new Set(), templates: new Set() };
    findAll(sf, (n) => ts.isJsxAttribute(n) && n.name.getText(sf) === 'testID').forEach((a) => {
      let v = a.initializer;
      if (v && ts.isJsxExpression(v)) v = v.expression;
      if (isStr(v)) out.plain.add(v.text);
      else if (v && ts.isTemplateExpression(v) && v.templateSpans.length === 1
               && v.templateSpans[0].literal.text === '') out.templates.add(`${v.head.text}\${}`);
    });
    return out;
  };
  const WANT = [
    [F.fab,     'feedback.fab'],
    [F.sheet,   'feedback.note-input'],
    [F.sheet,   'feedback.save-btn'],
    [F.sheet,   'feedback.save-error'],
    [F.sheet,   'feedback.char-count'],
    [F.sheet,   'feedback.note-error'],
    [F.sheet,   'feedback.severity.${}', true],
    [F.testing, 'settings.test-stages'],
  ];
  const cache = {};
  const missing = WANT.filter(([rel, id, tpl]) => {
    cache[rel] = cache[rel] || idsIn(rel);
    return !(tpl ? cache[rel].templates : cache[rel].plain).has(id);
  });
  if (missing.length === 0) ok(`6. all ${WANT.length} BL-10 testIDs still exist (incl. the feedback.severity.\${value} template)`);
  else fail('6. BL-10 testIDs still exist',
            missing.map(([rel, id]) => `${id} gone from ${rel}`).join('; ')
              + ' — renamed or dropped (testid-lint would also fail on the retained flows)');
}

// ── 7. Cold-launch retry (D-1(b)) ─────────────────────────────────────────
{
  const sf = parse(F.fab);
  const [comp] = findAll(sf, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === 'FeedbackFAB');
  const callee = (n) => (ts.isCallExpression(n) && ts.isIdentifier(n.expression) ? n.expression.text : null);

  // `retrySync` must be the store's action, not some local stand-in.
  const [rsDecl] = comp ? varDecl(comp, 'retrySync') : [];
  const fromStore = !!(rsDecl && rsDecl.initializer && ts.isCallExpression(rsDecl.initializer)
    && rsDecl.initializer.expression.getText(sf) === 'useFeedback'
    && /\.retrySync\b/.test(rsDecl.initializer.arguments.map((a) => a.getText(sf)).join(' ')));

  // The mount effect = the useEffect whose callback calls hydrate().
  const effects = comp ? findAll(comp, (n) => callee(n) === 'useEffect') : [];
  const mountEffect = effects.find((e) => e.arguments[0] && findAll(e.arguments[0], (n) => callee(n) === 'hydrate').length > 0);

  let afterHydrate = false;
  if (mountEffect) {
    for (const h of findAll(mountEffect.arguments[0], (n) => callee(n) === 'hydrate')) {
      // Form A: hydrate().then(cb)[.then(cb)…] — retrySync() inside any of the callbacks.
      let call = h;
      while (call.parent && ts.isPropertyAccessExpression(call.parent) && call.parent.name.text === 'then'
             && call.parent.parent && ts.isCallExpression(call.parent.parent)) {
        const cb = call.parent.parent.arguments[0];
        if (cb && findAll(cb, (n) => callee(n) === 'retrySync').length > 0) afterHydrate = true;
        call = call.parent.parent;
      }
      // Form B: `await hydrate();` then a later statement in the same block calls retrySync().
      const stmt = h.parent && ts.isAwaitExpression(h.parent) ? h.parent.parent : null;
      if (stmt && ts.isExpressionStatement(stmt) && stmt.parent && ts.isBlock(stmt.parent)) {
        const later = stmt.parent.statements.slice(stmt.parent.statements.indexOf(stmt) + 1);
        if (later.some((s) => findAll(s, (n) => callee(n) === 'retrySync').length > 0)) afterHydrate = true;
      }
    }
  }
  if (fromStore && mountEffect && afterHydrate) {
    ok(`7. FeedbackFAB's mount effect (${at(sf, mountEffect)}) calls the store's retrySync() after hydrate() resolves`);
  } else {
    fail("7. FeedbackFAB's mount effect calls retrySync() after hydrate() resolves",
         !fromStore ? '`retrySync` is not read from useFeedback((s) => s.retrySync) in FeedbackFAB'
           : !mountEffect ? 'no useEffect in FeedbackFAB calls hydrate()'
           : 'retrySync() is not chained after hydrate() — a cold launch never re-sends an unsent '
             + 'note (App.tsx only retries on an AppState change to active)');
  }
}

// ── Shared JSX helpers for 8–10 ──────────────────────────────────────────
const jsxOpen = (n) => ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n);
const attrOf = (el, name) => el.attributes.properties.find((a) => ts.isJsxAttribute(a) && a.name.getText() === name);
const attrStr = (el, name) => {
  const a = attrOf(el, name);
  if (!a || !a.initializer) return null;
  if (isStr(a.initializer)) return a.initializer.text;
  if (ts.isJsxExpression(a.initializer) && isStr(a.initializer.expression)) return a.initializer.expression.text;
  return null;
};
const elementOf = (open) => (ts.isJsxOpeningElement(open) ? open.parent : open);

// ── 8. Help & about row order ─────────────────────────────────────────────
{
  const sf = parse(F.about);
  const posOf = (label, pred) => {
    const hits = findAll(sf, pred);
    return { label, hits, pos: hits.length === 1 ? hits[0].getStart(sf) : null };
  };
  const byId = (id) => (n) => jsxOpen(n) && attrStr(n, 'testID') === id;
  const byText = (t) => (n) => ts.isJsxText(n) && n.text.trim() === t;
  const order = [
    posOf('Help & FAQ', byId('settings.help-faq')),
    posOf('Your feedback', byId('settings.feedback-inbox')),
    posOf('Privacy Policy', byText('Privacy Policy')),
    posOf('Terms of Use', byText('Terms of Use')),
    posOf('Credits', byId('settings.credits')),
    posOf('Version', byId('settings.version')),
  ];
  const missing = order.filter((o) => o.pos === null);
  const ascending = missing.length === 0 && order.every((o, i) => i === 0 || o.pos > order[i - 1].pos);
  if (ascending) ok(`8. Help & about row order: ${order.map((o) => o.label).join(' → ')}`);
  else fail('8. Help & about row order is Help & FAQ → Your feedback → Privacy → Terms → Credits → Version',
            missing.length ? missing.map((o) => `${o.label}: ${o.hits.length} matches`).join('; ')
              : `found ${[...order].sort((a, b) => a.pos - b.pos).map((o) => o.label).join(' → ')}`);
}

// ── 9. Credits is a plain block with legal's text ────────────────────────
{
  const sf = parse(F.about);
  const LINES = [
    'Credits',
    'Consensus values from DynastyProcess and other published sources.',
    'Data by nflverse (https://github.com/nflverse/nfldata), CC-BY.',
  ];
  const opens = findAll(sf, (n) => jsxOpen(n) && attrStr(n, 'testID') === 'settings.credits');
  const problems = [];
  if (opens.length !== 1) problems.push(`found ${opens.length} settings.credits elements`);
  else {
    const open = opens[0];
    const el = elementOf(open);
    if (open.tagName.getText(sf) !== 'View') problems.push(`it is a <${open.tagName.getText(sf)}>, not a plain View`);
    const acc = attrOf(open, 'accessible');
    if (!acc || (acc.initializer && acc.initializer.getText(sf) !== '{true}')) problems.push('not marked accessible (one element for VoiceOver)');
    for (const a of ['onPress', 'onLongPress', 'accessibilityRole']) if (attrOf(open, a)) problems.push(`has ${a}`);
    for (let p = el.parent; p; p = p.parent) {
      if (ts.isJsxElement(p) && /Pressable|Touchable|Button/.test(p.openingElement.tagName.getText(sf))) {
        problems.push(`sits inside a <${p.openingElement.tagName.getText(sf)}>`);
        break;
      }
    }
    const inner = findAll(el, (n) => jsxOpen(n) && n !== open).map((n) => n.tagName.getText(sf));
    const stray = inner.filter((t) => t !== 'View' && t !== 'Text');
    if (stray.length) problems.push(`contains ${stray.map((t) => `<${t}>`).join(', ')} (no chevron, no control)`);
    const texts = findAll(el, (n) => ts.isJsxText(n) && n.text.trim()).map((n) => n.text.trim().replace(/\s+/g, ' '));
    if (JSON.stringify(texts) !== JSON.stringify(LINES)) {
      problems.push(`text is ${JSON.stringify(texts)}, want ${JSON.stringify(LINES)} (legal's wording, in order)`);
    }
  }
  const nflLinks = findAll(sf, (n) => ts.isCallExpression(n) && /Linking\.openURL/.test(n.expression.getText(sf))
    && n.arguments.some((a) => /nflverse/.test(a.getText(sf))));
  if (nflLinks.length) problems.push(`AboutSection still opens the nflverse URL at ${nflLinks.map((n) => at(sf, n)).join(', ')}`);
  if (problems.length === 0) ok('9. Credits is a non-pressable, single accessible block with legal\'s two lines, in order');
  else fail('9. Credits is a non-pressable, single accessible block with legal\'s two lines', problems.join('; '));
}

// ── 10. Only the support address is a link, and it opens Mail ────────────
{
  const sf = parse(F.sheet);
  const links = findAll(sf, (n) => jsxOpen(n) && attrStr(n, 'accessibilityRole') === 'link');
  const problems = [];
  if (links.length !== 1) problems.push(`found ${links.length} accessibilityRole="link" elements (want exactly the address)`);
  else {
    const open = links[0];
    const el = elementOf(open);
    if (open.tagName.getText(sf) !== 'Text') problems.push(`the link is a <${open.tagName.getText(sf)}>, not a nested Text`);
    if (!(ts.isJsxElement(el.parent) && el.parent.openingElement.tagName.getText(sf) === 'Text')) {
      problems.push('the link is not nested inside the support line\'s Text');
    } else {
      const lineText = findAll(el.parent, (n) => ts.isJsxText(n) && n.parent === el.parent)
        .map((n) => n.text).join(' ').replace(/\s+/g, ' ');
      if (!lineText.includes('Settings › Help & about › Your feedback')) {
        problems.push('the path "Settings › Help & about › Your feedback" is not plain text in the same line');
      }
    }
    if (attrStr(open, 'accessibilityHint') !== 'Opens Mail') problems.push('accessibilityHint is not "Opens Mail"');
    const kids = ts.isJsxElement(el) ? el.children.filter((c) => !(ts.isJsxText(c) && !c.text.trim())) : [];
    if (!(kids.length === 1 && ts.isJsxExpression(kids[0]) && kids[0].expression
          && ts.isIdentifier(kids[0].expression) && kids[0].expression.text === 'SUPPORT_EMAIL')) {
      problems.push('the link does not render exactly {SUPPORT_EMAIL}');
    }
    const press = attrOf(open, 'onPress');
    const opensMail = press && findAll(press, (n) => ts.isCallExpression(n)
      && n.expression.getText(sf) === 'Linking.openURL' && n.arguments.length === 1
      && ((ts.isBinaryExpression(n.arguments[0]) && isStr(n.arguments[0].left) && n.arguments[0].left.text === 'mailto:'
           && ts.isIdentifier(n.arguments[0].right) && n.arguments[0].right.text === 'SUPPORT_EMAIL')
          || (ts.isTemplateExpression(n.arguments[0]) && n.arguments[0].head.text === 'mailto:'
              && n.arguments[0].templateSpans.length === 1
              && n.arguments[0].templateSpans[0].expression.getText(sf) === 'SUPPORT_EMAIL'
              && n.arguments[0].templateSpans[0].literal.text === ''))).length > 0;
    if (!opensMail) problems.push("onPress does not call Linking.openURL('mailto:' + SUPPORT_EMAIL)");
  }
  if (problems.length === 0) ok('10. only the support address is a link: a nested Text, "Opens Mail", mailto:SUPPORT_EMAIL');
  else fail('10. only the support address is a link, and it opens Mail', problems.join('; '));
}

console.log(failures === 0
  ? '\nAll feedback-public checks passed (pins 1-10).'
  : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
