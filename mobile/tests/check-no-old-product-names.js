#!/usr/bin/env node
// No pre-rename product names in copy a user can see (D-057: the app ships
// as "Fleeced: Dynasty Trade Finder"; the short name is Fleeced).
//
// WHY THIS EXISTS. A Release simulator pass (2026-11-22) found the calculator
// saying "Live consensus values from the FTF engine" and the data export
// downloading as "fantasy-trade-finder-export.json". A sweep found more:
// "FTF community value", "Fantasy Trade Finder never drafts…", "FTF can send
// trades…", "DTF Trade Calculator" in the share text. The repo, the Render
// host, the bundle id, storage keys, header names and the iOS project keep the
// old names ON PURPOSE (D-057), so a blanket rename is wrong; this guard pins
// the copy only.
//
// Pinned:
//   (s1) Every .ts / .tsx / .js / .jsx under src/, plus App.tsx, parsed as an
//        AST (comments never count). A StringLiteral, template part or
//        JsxText matching OLD (below) FAILS, after the full product name
//        "Fleeced: Dynasty Trade Finder" is removed from it, except:
//          - testID / nativeID values, module specifiers, string-literal
//            types, quoted property names (as check-no-beta-copy);
//          - URLs (the string contains "://" or starts with "https") — the
//            Render host is `fantasy-trade-finder.onrender.com` and stays;
//          - the ALLOW list below (each entry says why it is never shown).
//   (s2) The export filename, on both ends: the two mobile writers name the
//        file `fleeced-export.json`, and backend/server.py's
//        Content-Disposition names the same file.
//   (a)  ALLOW is a ratchet: each entry must match exactly one string.
//   (p)  Positive controls: at least 100 files scanned, and the scan visits
//        the calculator's "Live consensus values" line.
//
// HONEST LABEL (G-035): this proves the source holds no such string, not what
// renders. Out of reach: strings built at runtime and text the server sends.
//
// Run: node tests/check-no-old-product-names.js   (or: npm run test:no-old-product-names)

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
const REPO = path.join(ROOT, '..');
// Upper-case acronyms only: lower-case `ftf.` / `ftf:` are storage keys and
// must never be renamed (they would orphan stored data).
const OLD = /\bFTF\b|\bDTF\b|[Ff]antasy[ -][Tt]rade[ -][Ff]inder|[Dd]ynasty[ -][Tt]rade[ -][Ff]inder/;
const PRODUCT = /Fleeced: Dynasty Trade Finder/g;

// Each entry matches one string exactly (same file, same text). Never add one
// for copy a user can see.
// (Header names such as 'X-FTF-Prewarm' are quoted property names, so the
// AST rule above already skips them; storage keys are lower case.)
const ALLOW = [];

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
  if ((ts.isImportDeclaration(p) || ts.isExportDeclaration(p)) && p.moduleSpecifier === n) return true;
  if (ts.isExternalModuleReference(p)) return true;
  if (ts.isCallExpression(p) && p.arguments[0] === n
      && (p.expression.kind === ts.SyntaxKind.ImportKeyword
        || (ts.isIdentifier(p.expression) && p.expression.text === 'require'))) return true;
  if (ts.isLiteralTypeNode(p)) return true;
  if (ts.isPropertyAssignment(p) && p.name === n) return true;
  return inHiddenAttr(n);
}

const isUrl = (s) => s.includes('://') || /^\s*https?:/.test(s);

// ── Scan ──────────────────────────────────────────────────────────────────
const ROOT_SOURCES = ['App.tsx'];
const files = [...listSources(path.join(ROOT, 'src')), ...ROOT_SOURCES.map((f) => path.join(ROOT, f))];
const seen = new Map();
const hits = [];
const allowHits = ALLOW.map(() => 0);

for (const abs of files) {
  const rel = path.relative(ROOT, abs).split(path.sep).join('/');
  const sf = ts.createSourceFile(abs, fs.readFileSync(abs, 'utf8'), ts.ScriptTarget.Latest, true,
    scriptKind(abs));
  const visited = [];
  const visit = (node) => {
    if (isStringish(node)) {
      visited.push(node.text);
      const t = node.text.replace(PRODUCT, '');
      if (OLD.test(t) && !excluded(node) && !isUrl(node.text)) {
        const i = ALLOW.findIndex((e) => e.file === rel && e.text === node.text);
        if (i !== -1) allowHits[i] += 1;
        else {
          const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
          hits.push(`${rel}:${line} ${JSON.stringify(node.text.trim().slice(0, 90))}`);
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
  `s1 no string or JSX text in src/ or App.tsx names the product FTF / DTF / Fantasy Trade Finder / Dynasty Trade Finder (${hits.length} hit(s))`,
  hits,
);

// ── Export filename, client and server ────────────────────────────────────
{
  const writers = ['src/screens/SettingsScreen.tsx', 'src/screens/settings/sections/AccountDataSection.tsx'];
  const bad = writers.filter((f) => {
    const src = fs.readFileSync(path.join(ROOT, f), 'utf8');
    return !src.includes('}fleeced-export.json`') || /trade-finder-export/.test(src);
  });
  assert(bad.length === 0, 's2a both mobile export writers save the file as fleeced-export.json', bad);
  const server = fs.readFileSync(path.join(REPO, 'backend', 'server.py'), 'utf8');
  assert(
    /attachment; filename=fleeced-export\.json/.test(server) && !/trade-finder-export/.test(server),
    "s2b backend/server.py's export Content-Disposition names fleeced-export.json",
  );
}

// ── Allowlist ratchet ─────────────────────────────────────────────────────
ALLOW.forEach((e, i) => {
  assert(
    allowHits[i] === e.count,
    `a1 allowlist: ${e.file} ${JSON.stringify(e.text)} (${e.why}) matches exactly ${e.count}`,
    `it matches ${allowHits[i]}`,
  );
});

// ── Positive controls ─────────────────────────────────────────────────────
assert(files.length >= 100, `p1 the scan visited at least 100 files (${files.length})`);
assert(
  (seen.get('src/screens/TradeCalculatorScreen.tsx') || []).some((t) => /Live consensus values/.test(t)),
  'p2 the scan visits the calculator\'s "Live consensus values" line',
);

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll no-old-product-names checks passed.');
