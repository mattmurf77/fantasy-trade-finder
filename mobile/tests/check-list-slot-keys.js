#!/usr/bin/env node
// Sibling lists in one conditional slot carry distinct keys.
//
// WHY THIS EXISTS. The Matches tab crashed (2026-11-22, a fatal in release
// builds, 2 of 2 on an iOS 26.1 simulator) on a switch from Mutual to
// Awaiting. MatchesScreen's body is one ternary over `segment`; the Mutual
// branch rendered `<FlatList … viewabilityConfig onViewableItemsChanged>` and
// the Awaiting branch a `<FlatList>` without them. Neither had a `key` and
// both sat in the same JSX slot, so React kept ONE FlatList instance across
// the switch and handed it the other branch's props. FlatList's
// componentDidUpdate (react-native/Libraries/Lists/FlatList.js) then threw
// "Changing onViewableItemsChanged nullability on the fly is not supported".
// The same invariant guards numColumns, viewabilityConfig and
// viewabilityConfigCallbackPairs. The cure is a distinct `key` per branch,
// which makes React mount a fresh list instead of updating the old one.
//
// WHAT IT CHECKS (TypeScript AST over every .tsx under src/).
//   A  For every conditional chain (`a ? X : b ? Y : Z`, through parentheses
//      and `&&` / `||` / `??` right-hand sides), the JSX elements it can
//      render into its slot are collected. Any two of them that React would
//      reconcile as the same instance (same tag, same-or-no key) are aligned
//      child by child, the way React does, and every pair of FlatLists
//      (Animated.FlatList, DraggableFlatList) met that way must agree on
//      onViewableItemsChanged
//      presence and on the numColumns / viewabilityConfig /
//      viewabilityConfigCallbackPairs source text. A disagreement without
//      distinct keys is the crash. The same comparison runs across the
//      `return` statements of one function (early returns render into the
//      same slot too; PortfolioScreen's empty and full lists are an example).
//   B  MatchesScreen pins: the Mutual list is keyed "matches-mutual" and still
//      holds matchesListRef and the viewability props (the push-arrival
//      scroll-and-mark depends on them); the Awaiting list is keyed
//      "matches-awaiting".
//   C  Self-tests, so A cannot pass vacuously: the scanner flags a minimal
//      fixture of the bug, and flags the real MatchesScreen source with its
//      two keys deleted (the code as it was on main before this fix).
//
// HONEST LABEL (G-035). This proves code SHAPE, not runtime behaviour. There
// is no React Native renderer in this project's node harness (no jest, no
// react-test-renderer; see tests/README.md), so FlatList's componentDidUpdate
// is not executed here. Element alignment is positional over static JSX: a
// list rendered from a helper function or a variable is not seen. The
// on-device proof is the operator's TestFlight / simulator pass.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const MOBILE = path.join(__dirname, '..');
let passes = 0;
let failures = 0;
const check = (cond, name, why) => {
  if (cond) { passes += 1; console.log(`PASS  ${name}`); }
  else { failures += 1; console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`); }
};

// DraggableFlatList hands these props through to an inner FlatList.
const FLATLISTS = new Set(['FlatList', 'Animated.FlatList', 'DraggableFlatList']);
const FRAGILE = ['numColumns', 'viewabilityConfig', 'viewabilityConfigCallbackPairs'];

const opening = (n) => (ts.isJsxElement(n) ? n.openingElement : n);
const tagOf = (n) => (ts.isJsxFragment(n) ? '<>' : opening(n).tagName.getText());
const attrs = (n) => {
  const out = new Map();
  if (ts.isJsxFragment(n)) return out;
  for (const a of opening(n).attributes.properties) {
    if (ts.isJsxAttribute(a)) out.set(a.name.getText(), a.initializer ? a.initializer.getText() : 'true');
  }
  return out;
};
const keyOf = (n) => attrs(n).get('key');
const unwrap = (e) => {
  while (e && (ts.isParenthesizedExpression(e) || ts.isAsExpression(e))) e = e.expression;
  return e;
};

// The elements an expression can put into its slot.
function leaves(e) {
  e = unwrap(e);
  if (!e) return [];
  if (ts.isJsxElement(e) || ts.isJsxSelfClosingElement(e) || ts.isJsxFragment(e)) return [e];
  if (ts.isConditionalExpression(e)) return [...leaves(e.whenTrue), ...leaves(e.whenFalse)];
  if (ts.isBinaryExpression(e)) {
    const op = e.operatorToken.kind;
    if (op === ts.SyntaxKind.AmpersandAmpersandToken) return leaves(e.right);
    if (op === ts.SyntaxKind.BarBarToken || op === ts.SyntaxKind.QuestionQuestionToken) {
      return [...leaves(e.left), ...leaves(e.right)];
    }
  }
  return [];
}

// JSX children as React's positional slots (whitespace-only text dropped).
function slots(n) {
  if (ts.isJsxSelfClosingElement(n)) return [];
  const out = [];
  for (const c of n.children) {
    if (ts.isJsxText(c)) { if (c.text.trim()) out.push([]); continue; }
    if (ts.isJsxExpression(c)) { out.push(c.expression ? leaves(c.expression) : []); continue; }
    out.push([c]);
  }
  return out;
}

const sameInstance = (a, b) => tagOf(a) === tagOf(b) && keyOf(a) === keyOf(b);

function listDiff(a, b) {
  const pa = attrs(a);
  const pb = attrs(b);
  const diffs = [];
  if (pa.has('onViewableItemsChanged') !== pb.has('onViewableItemsChanged')) diffs.push('onViewableItemsChanged presence');
  for (const p of FRAGILE) if (pa.get(p) !== pb.get(p)) diffs.push(p);
  return diffs;
}

// Walk two alternatives React would reconcile as one instance.
function compare(a, b, sf, rel, hazards, depth = 0) {
  if (depth > 40 || !sameInstance(a, b)) return;
  if (FLATLISTS.has(tagOf(a))) {
    const diffs = listDiff(a, b);
    if (diffs.length) {
      const line = (n) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
      hazards.push(`${rel}:${line(a)} and :${line(b)} <${tagOf(a)}> share a slot without distinct keys; differ in ${diffs.join(', ')}`);
    }
  }
  const sa = slots(a);
  const sb = slots(b);
  for (let i = 0; i < Math.min(sa.length, sb.length); i += 1) {
    for (const x of sa[i]) for (const y of sb[i]) if (x !== y) compare(x, y, sf, rel, hazards, depth + 1);
  }
}

function scan(source, rel) {
  const sf = ts.createSourceFile(rel, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const hazards = [];
  const visit = (n) => {
    if (ts.isFunctionLike(n) && n.body && ts.isBlock(n.body)) {
      const rets = [];
      const own = (m) => {
        if (ts.isFunctionLike(m)) return;
        if (ts.isReturnStatement(m) && m.expression) rets.push(...leaves(m.expression));
        ts.forEachChild(m, own);
      };
      ts.forEachChild(n.body, own);
      for (let i = 0; i < rets.length; i += 1) {
        for (let j = i + 1; j < rets.length; j += 1) compare(rets[i], rets[j], sf, rel, hazards);
      }
    }
    if (ts.isConditionalExpression(n)) {
      let p = n.parent;
      while (p && ts.isParenthesizedExpression(p)) p = p.parent;
      const top = !(p && ts.isConditionalExpression(p));
      if (top) {
        const ls = leaves(n);
        for (let i = 0; i < ls.length; i += 1) {
          for (let j = i + 1; j < ls.length; j += 1) compare(ls[i], ls[j], sf, rel, hazards);
        }
      }
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return hazards;
}

// ── A: every .tsx under src/ ─────────────────────────────────────────────
function walk(dir, out = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, out);
    else if (ent.name.endsWith('.tsx')) out.push(p);
  }
  return out;
}
const files = walk(path.join(MOBILE, 'src'));
const all = [];
for (const f of files) all.push(...scan(fs.readFileSync(f, 'utf8'), path.relative(MOBILE, f)));
check(files.length > 50, `A0. scanned ${files.length} .tsx files under src/`);
check(all.length === 0, 'A1. no FlatList pair in one conditional slot differs in a fly-unsafe prop without distinct keys',
  all.join('\n      '));

// ── B: MatchesScreen pins ────────────────────────────────────────────────
const MATCHES_REL = 'src/screens/MatchesScreen.tsx';
const matches = fs.readFileSync(path.join(MOBILE, MATCHES_REL), 'utf8');
const mutual = matches.match(/<FlatList\s+key="matches-mutual"[\s\S]*?\n {10}\/>/);
check(Boolean(mutual), 'B1. the Mutual FlatList is keyed "matches-mutual"');
check(Boolean(mutual) && /ref=\{matchesListRef\}/.test(mutual[0])
  && /viewabilityConfig=\{viewabilityConfig\}/.test(mutual[0])
  && /onViewableItemsChanged=\{onViewableItemsChanged\}/.test(mutual[0])
  && /onScrollToIndexFailed=\{onArrivalScrollFailed\}/.test(mutual[0]),
'B2. the Mutual list keeps matchesListRef and the push-arrival viewability / scroll props');
check(/<FlatList\s+key="matches-awaiting"\s+ref=\{awaitingListRef\}/.test(matches),
  'B3. the Awaiting FlatList is keyed "matches-awaiting"');

// ── C: the scanner is not vacuous ────────────────────────────────────────
const FIXTURE = `
export function S({ seg, a, b, cb, cfg }) {
  return (
    <View>
      {seg === 'one' ? (
        a.length === 0 ? <Empty /> : <FlatList data={a} viewabilityConfig={cfg} onViewableItemsChanged={cb} />
      ) : seg === 'two' ? (
        <FlatList data={b} />
      ) : null}
    </View>
  );
}`;
check(scan(FIXTURE, 'fixture.tsx').length === 1, 'C1. the scanner flags a minimal fixture of the bug');
const unkeyed = matches.replace(/\s+key="matches-(mutual|awaiting)"/g, '');
check(unkeyed !== matches && scan(unkeyed, MATCHES_REL).some((h) => /onViewableItemsChanged presence/.test(h)),
  'C2. the scanner flags MatchesScreen with its two list keys removed (main before this fix)');
const keyedFixture = FIXTURE.replace('<FlatList data={a}', '<FlatList key="one" data={a}')
  .replace('<FlatList data={b}', '<FlatList key="two" data={b}');
check(scan(keyedFixture, 'fixture.tsx').length === 0, 'C3. distinct keys clear the fixture');
const RETURNS = `
export function R({ rows, cb }) {
  if (rows.length === 0) return <Wrap><FlatList data={[]} /></Wrap>;
  return <Wrap><FlatList data={rows} onViewableItemsChanged={cb} /></Wrap>;
}`;
check(scan(RETURNS, 'returns.tsx').length === 1, 'C4. the scanner flags the hazard across early returns');

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
