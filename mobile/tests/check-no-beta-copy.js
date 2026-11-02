#!/usr/bin/env node
// No "beta" in the shipping binary's copy (App Review guideline 2.2;
// docs/plans/no-beta-labels/scope.md §3).
//
// WHY THIS EXISTS. Apple's guideline 2.2 says betas belong on TestFlight, and
// reviewers flag the word "beta" in an App Store binary. Three outlook ribbons
// shipped it: the trade card's playoff-impact ribbon ("PROJECTED · BETA"), Team
// review's Playoff outlook ribbon (the same) and League's Season outlook ribbon
// ("Projected · preseason · beta" through week 5). They now read PROJECTED /
// Projected; the `beta` data fields, and `showRecords = !meta.beta`, are
// unchanged. Failure mode this catches: any string that can reach the screen
// (a string literal, a template literal part, JSX text, an accessibilityLabel,
// an app.json display string, an Info.plist value) bringing the word back.
//
// Pinned:
//   (s1) Every .ts / .tsx / .js / .jsx under src/, plus App.tsx,
//        app.config.js and index.ts, parsed as an AST (so comments never
//        count). A StringLiteral, NoSubstitutionTemplateLiteral, template
//        head / middle / tail or JsxText matching /\bbeta\b/i FAILS, except:
//          - the value of a testID / nativeID JSX attribute (never shown);
//          - import / export module specifiers, and require('…') /
//            import('…') arguments;
//          - string-literal types (LiteralTypeNode);
//          - quoted property names (the `name` of a PropertyAssignment);
//          - the ALLOW list below.
//   (s2) Every string value in app.json (display name, permission strings).
//   (s3) Every <string>…</string> value in ios/DTFDynastyTradeFinder/Info.plist
//        (CFBundleDisplayName, usage descriptions), read with a regex over
//        the XML (XML comments stripped first); one matching /\bbeta\b/i
//        FAILS.
//   (a)  ALLOW is a ratchet: each entry must match exactly one string in its
//        file. One that matches none (stale) or several FAILS.
//   (p)  Positive controls, so the scan can't pass vacuously: at least 100
//        files scanned, App.tsx, app.config.js and index.ts among them, each
//        with its strings visited; Info.plist's CFBundleDisplayName value
//        scanned; and the scan itself visits each ribbon's PROJECTED /
//        'Projected' string.
//
// HONEST LABEL (G-035): this proves the source holds no such string, not what
// renders. Out of its reach: strings assembled at runtime ('BE' + 'TA',
// computed keys) and text the server sends (TestFlight checklist: scope.md
// §3). Server messages are covered, for Win Now's `Unavailable` messages
// only, by backend/tests/test_no_beta_user_messages.py.
//
// Run: node tests/check-no-beta-copy.js   (or: npm run test:no-beta-copy)

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

const ROOT = path.join(__dirname, '..');
const BETA = /\bbeta\b/i;

// ── Allowlist. Each entry matches one string exactly (same file, same text).
//    Never add one for copy a user can see.
const ALLOW = [
  { file: 'src/screens/UpdateGateScreen.tsx', text: 'itms-beta://', why: 'URL scheme, never rendered' },
];

const HIDDEN_ATTRS = new Set(['testID', 'nativeID']);

let failures = 0;
function assert(cond, name, details) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}`);
    for (const d of [].concat(details || [])) console.error(`        ${d}`);
  }
}

function listSources(dir) {
  const out = [];
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) out.push(...listSources(p));
    else if (/\.(ts|tsx|js|jsx)$/.test(ent.name)) out.push(p);
  }
  return out;
}

function scriptKind(file) {
  if (file.endsWith('.tsx')) return ts.ScriptKind.TSX;
  if (file.endsWith('.jsx')) return ts.ScriptKind.JSX;
  if (file.endsWith('.js')) return ts.ScriptKind.JS;
  return ts.ScriptKind.TS;
}

const isStringish = (n) =>
  ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateHead(n)
  || ts.isTemplateMiddle(n) || ts.isTemplateTail(n) || ts.isJsxText(n);

// The value of a testID / nativeID attribute: the nearest JsxAttribute above
// the node decides, and a nested element in between means it's that
// element's content, not the attribute's value.
function inHiddenAttr(n) {
  for (let p = n.parent; p; p = p.parent) {
    if (ts.isJsxAttribute(p)) return HIDDEN_ATTRS.has(p.name.getText());
    if (ts.isJsxElement(p) || ts.isJsxSelfClosingElement(p) || ts.isJsxFragment(p)) return false;
  }
  return false;
}

function excluded(n) {
  const p = n.parent;
  if (!p) return false;
  // import / export module specifiers
  if ((ts.isImportDeclaration(p) || ts.isExportDeclaration(p)) && p.moduleSpecifier === n) return true;
  if (ts.isExternalModuleReference(p)) return true;
  // require('…') and import('…') arguments
  if (ts.isCallExpression(p) && p.arguments[0] === n
      && (p.expression.kind === ts.SyntaxKind.ImportKeyword
        || (ts.isIdentifier(p.expression) && p.expression.text === 'require'))) return true;
  // string-literal types
  if (ts.isLiteralTypeNode(p)) return true;
  // quoted property names
  if (ts.isPropertyAssignment(p) && p.name === n) return true;
  // testID / nativeID values
  return inHiddenAttr(n);
}

// ── Scan ──────────────────────────────────────────────────────────────────
const ROOT_SOURCES = ['App.tsx', 'app.config.js', 'index.ts'];
const files = [...listSources(path.join(ROOT, 'src')), ...ROOT_SOURCES.map((f) => path.join(ROOT, f))];
const seen = new Map(); // rel → [{ node, text }] for every string the scan visited
const hits = [];
const allowHits = ALLOW.map(() => 0);

for (const abs of files) {
  const rel = path.relative(ROOT, abs).split(path.sep).join('/');
  const sf = ts.createSourceFile(abs, fs.readFileSync(abs, 'utf8'), ts.ScriptTarget.Latest, true,
    scriptKind(abs));
  const visited = [];
  const visit = (node) => {
    if (isStringish(node)) {
      visited.push({ node, text: node.text });
      if (BETA.test(node.text) && !excluded(node)) {
        const i = ALLOW.findIndex((e) => e.file === rel && e.text === node.text);
        if (i !== -1) allowHits[i] += 1;
        else {
          const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
          hits.push(`${rel}:${line} ${JSON.stringify(node.text.trim().slice(0, 80))}`);
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  seen.set(rel, visited);
}

assert(
  hits.length === 0,
  `s1 no string literal, template part or JSX text in src/, App.tsx, app.config.js or index.ts matches /\\bbeta\\b/i (${hits.length} hit(s))`,
  hits,
);

// ── app.json ──────────────────────────────────────────────────────────────
{
  const jsonHits = [];
  let values = 0;
  const walkJson = (v, at) => {
    if (typeof v === 'string') {
      values += 1;
      if (BETA.test(v)) jsonHits.push(`${at} ${JSON.stringify(v)}`);
    } else if (Array.isArray(v)) v.forEach((x, i) => walkJson(x, `${at}[${i}]`));
    else if (v && typeof v === 'object') for (const k of Object.keys(v)) walkJson(v[k], at ? `${at}.${k}` : k);
  };
  walkJson(JSON.parse(fs.readFileSync(path.join(ROOT, 'app.json'), 'utf8')), '');
  assert(
    values > 0 && jsonHits.length === 0,
    `s2 no string value in app.json matches /\\bbeta\\b/i (${values} values scanned)`,
    jsonHits,
  );
}

// ── Info.plist ────────────────────────────────────────────────────────────
const PLIST = 'ios/DTFDynastyTradeFinder/Info.plist';
const plistValues = [];
{
  const xml = fs.readFileSync(path.join(ROOT, PLIST), 'utf8').replace(/<!--[\s\S]*?-->/g, '');
  for (const m of xml.matchAll(/<string>([\s\S]*?)<\/string>/g)) plistValues.push(m[1]);
  const plistHits = plistValues.filter((v) => BETA.test(v)).map((v) => JSON.stringify(v));
  assert(
    plistValues.length > 0 && plistHits.length === 0,
    `s3 no <string> value in ${PLIST} matches /\\bbeta\\b/i (${plistValues.length} values scanned)`,
    plistHits,
  );
}

// ── Allowlist ratchet ─────────────────────────────────────────────────────
ALLOW.forEach((e, i) => {
  assert(
    allowHits[i] === 1,
    `a1 allowlist: ${e.file} ${JSON.stringify(e.text)} (${e.why}) matches exactly once`,
    allowHits[i] === 0
      ? 'it matches none — if the string is gone, delete this entry'
      : `it matches ${allowHits[i]} strings; a second one can't share an entry`,
  );
});

// ── Positive controls ─────────────────────────────────────────────────────
assert(
  files.length >= 100 && ROOT_SOURCES.every((f) => seen.has(f)),
  `p1 the scan visited at least 100 files (${files.length}), ${ROOT_SOURCES.join(', ')} among them`,
);

const within = (node, ancestor) => {
  for (let p = node; p; p = p.parent) if (p === ancestor) return true;
  return false;
};
const attrText = (opening, name) => {
  const a = opening.attributes.properties.find((x) => ts.isJsxAttribute(x) && x.name.getText() === name);
  return a && a.initializer ? a.initializer.getText() : null;
};
// The one element in `rel` whose opening tag carries style={styles.ribbon}
// (and `testID`, when given). Returns the scanned strings inside it.
function ribbonStrings(rel, testID) {
  const visited = seen.get(rel) || [];
  const sf = visited.length ? visited[0].node.getSourceFile() : null;
  const ribbons = [];
  const find = (n) => {
    if (ts.isJsxElement(n) && attrText(n.openingElement, 'style') === '{styles.ribbon}'
        && (!testID || attrText(n.openingElement, 'testID') === testID)) ribbons.push(n);
    ts.forEachChild(n, find);
  };
  if (sf) find(sf);
  if (ribbons.length !== 1) return { count: ribbons.length, texts: [] };
  return { count: 1, texts: visited.filter((s) => within(s.node, ribbons[0])).map((s) => s.text.trim()) };
}

{
  const r = ribbonStrings('src/components/CardImpactBlock.tsx', '{`${testID}.odds.ribbon`}');
  assert(
    r.count === 1 && r.texts.includes('PROJECTED'),
    'p2 CardImpactBlock: the scan visits PROJECTED inside the ${testID}.odds.ribbon element',
    `ribbon elements found: ${r.count}; strings inside: ${JSON.stringify(r.texts)}`,
  );
}
{
  const r = ribbonStrings('src/screens/TeamReviewScreen.tsx');
  assert(
    r.count === 1 && r.texts.includes('PROJECTED'),
    'p3 TeamReviewScreen: the scan visits PROJECTED inside the Playoff outlook ribbon element',
    `ribbon elements found: ${r.count}; strings inside: ${JSON.stringify(r.texts)}`,
  );
}
{
  const visited = seen.get('src/screens/LeagueSummaryScreen.tsx') || [];
  const fn = visited.length
    ? visited[0].node.getSourceFile().statements.find((s) => ts.isFunctionDeclaration(s)
      && s.name && s.name.text === 'betaRibbonLabel')
    : null;
  const texts = fn ? visited.filter((s) => within(s.node, fn)).map((s) => s.text) : [];
  assert(
    !!fn && texts.includes('Projected'),
    "p4 LeagueSummaryScreen: the scan visits 'Projected' inside betaRibbonLabel",
    fn ? `strings inside: ${JSON.stringify(texts)}` : 'function betaRibbonLabel not found',
  );
}
for (const f of ROOT_SOURCES) {
  const n = (seen.get(f) || []).length;
  assert(n > 0, `p5 ${f}: the scan parsed it and visited its strings (${n})`);
}
{
  const m = fs.readFileSync(path.join(ROOT, PLIST), 'utf8')
    .match(/<key>CFBundleDisplayName<\/key>\s*<string>([\s\S]*?)<\/string>/);
  assert(
    !!m && plistValues.includes(m[1]),
    `p6 Info.plist: the scan read the CFBundleDisplayName value (${m ? JSON.stringify(m[1]) : 'not found'})`,
  );
}

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll no-beta-copy checks passed.');
