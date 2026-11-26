#!/usr/bin/env node
// The monetization copy names no feature cut for launch.
//
// WHY THIS EXISTS. The 2026-11-21 launch feature audit
// (data/review/launch-feature-audit-2026-11-21/launch-feature-audit.md, local
// to the operator's machine) marks features N (cut for launch). The paywall
// still sold some of them ("Proposals sent to Sleeper, ESPN or MFL", "Shop a
// player and Win Now trade targets") and its free line promised others
// ("Calibration, ... trends, ... the Draft Room"). The operator's ruling
// (2026-11-22): "Remove cut features." Failure mode this catches: a cut
// feature's name coming back into a string the paywall, the VerifySheet,
// Settings › Subscription or the Founder welcome can render.
//
// Pinned:
//   (s1) Every StringLiteral, NoSubstitutionTemplateLiteral, template part
//        and JsxText in FILES, parsed as an AST (comments never count; the
//        value of a testID / nativeID attribute and module specifiers are
//        skipped), matched against DENY. A match FAILS.
//   (p)  Positive controls, so the scan can't pass vacuously: every file in
//        FILES exists and yields strings, and the scan visits the paywall's
//        first bullet and its free line.
//
// DENY is a short explicit list of features CUT for launch by the owner's
// final keep/cut calls (data/review/launch-feature-audit-2026-11-21/
// keep-cut-list.md, 2026-11-25), plus features already dark at launch that
// paywall copy could plausibly name (Team Overhaul) — not the whole audit.
// Features the owner KEPT (Send in ESPN, Win Now, the "More offers" shop
// window, standing offers, Usage Trends, free agents, leaderboards,
// contrarian ranks, Max PF moves, Playoff targets, ESPN pick assignment) are
// deliberately absent: this guard does not decide what the paywall sells, it
// only keeps cut features out. When a cut feature returns, drop its entry
// here in the same commit that names it in the copy again.
//
// 2026-11-25: `mon.pay.b3` / `mon.pay.b4` are back to their source text
// ("Proposals sent to Sleeper, ESPN or MFL", "Shop a player and Win Now trade
// targets") on the owner's keep calls for ESPN send and Win Now. Both name
// kept features only, so this guard passes them unchanged; `mon.lock.free`
// stays cut down (Calibration, trends and the Draft Room are still cut).
//
// HONEST LABEL (G-035): this proves the source holds no such string, not what
// renders. Text the server sends (paywall config) is out of its reach.
//
// Run: node tests/check-monetization-cut-features.js
//      (or: npm run test:monetization-cut-features)

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

const SRC = path.join(__dirname, '..', 'src');

// The monetization surfaces: the copy module and the components that render
// subscription copy of their own.
const FILES = [
  'copy/monetization.ts',
  'screens/PaywallScreen.tsx',
  'screens/FounderWelcomeScreen.tsx',
  'components/SubscriptionSection.tsx',
  'components/VerifySheet.tsx',
];

// Cut for launch per the owner's calls of 2026-11-25 (keep-cut-list.md).
const DENY = [
  [/\bteam review\b/i, 'Team Review'],
  [/\bdraft room\b|\brookie draft\b|\blive draft\b/i, 'Draft Room (and its live polling)'],
  [/\bmock drafts?\b/i, 'mock draft'],
  [/\brecord(ing)? picks\b/i, 'record picks'],
  [/\bpick anchors?\b|\banchors\b/i, 'Pick Anchors'],
  [/\brookie/i, 'rookie ranks, rookie board'],
  [/\bcalibration\b|\bblind grading\b/i, 'Calibration tab'],
  // The Rank-stack Trends page (movers vs consensus) is cut; Usage Trends is
  // kept, so "usage trends" is allowed.
  [/(?<!\busage )\b(trends?|movers?|risers?|fallers?)\b/i, 'Trends (risers / fallers)'],
  [/\bmarket pulse\b/i, 'market pulse'],
  [/\bseason outlook\b/i, 'Season outlook section'],
  [/\bredraft\b/i, '"Redraft (soon)" chip'],
  [/\boverhaul\b/i, 'Team Overhaul (dark at launch)'],
];

let failures = 0;
let passes = 0;
function check(name, fn) {
  try {
    fn();
    passes += 1;
    console.log(`  ok   ${name}`);
  } catch (e) {
    failures += 1;
    console.log(`  FAIL ${name}\n       ${e.message.split('\n').join('\n       ')}`);
  }
}

function stringsIn(rel) {
  const file = path.join(SRC, rel);
  const text = fs.readFileSync(file, 'utf8');
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true,
    rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const out = [];
  const skip = (node) => {
    const p = node.parent;
    if (!p) return false;
    if (ts.isImportDeclaration(p) || ts.isExportDeclaration(p)) return true;
    if (ts.isLiteralTypeNode(p)) return true;
    if (ts.isJsxAttribute(p) && /^(testID|nativeID)$/.test(p.name.getText(sf))) return true;
    if (ts.isPropertyAssignment(p) && p.name === node) return true;
    return false;
  };
  const visit = (node) => {
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)
      || ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) && !skip(node)) {
      out.push(node.text);
    } else if (ts.isJsxText(node) && node.text.trim()) {
      out.push(node.text.trim());
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return out;
}

const seen = {};
console.log('check-monetization-cut-features');

check('p. every monetization file exists and yields strings', () => {
  for (const rel of FILES) {
    if (!fs.existsSync(path.join(SRC, rel))) throw new Error(`missing: src/${rel}`);
    seen[rel] = stringsIn(rel);
    if (seen[rel].length === 0) throw new Error(`no strings visited in src/${rel}`);
  }
  const mon = seen['copy/monetization.ts'];
  if (!mon.includes('A trade deck that weighs your board and theirs')) {
    throw new Error('the scan did not visit mon.pay.b1');
  }
  if (!mon.some((s) => s.startsWith('No subscription needed for '))) {
    throw new Error('the scan did not visit mon.lock.free');
  }
});

check('s1. no monetization string names a feature cut for launch', () => {
  const hits = [];
  for (const rel of FILES) {
    for (const s of seen[rel] || []) {
      for (const [re, what] of DENY) {
        if (re.test(s)) hits.push(`src/${rel}: "${s}" names ${what}`);
      }
    }
  }
  if (hits.length) throw new Error(hits.join('\n'));
});

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
