#!/usr/bin/env node
// Calibration — in-app blind grading (docs/plans/blind-grading/, lld.md §10.8).
//
// WHY THIS EXISTS. Calibration is value-core Gate 2: a tester grades ~40 trade
// cards, half from today's engine and half from the new value core, shuffled,
// and the whole measurement is worthless if the grader can tell which engine
// made a card. The server enforces that on the wire (one neutral formatter,
// `arms_json` read only by results/report — backend/tests/test_blind_grading_e2e.py
// walks every response for leaked arm tokens). This file is the CLIENT half of
// the same promise, and it pins six things `tsc` cannot see:
//
//   • The card is `components/GradingCard.tsx`, a dedicated minimal card, never
//     `components/TradeCard.tsx` — TradeCard renders reasons, meters, lanes and
//     the likes-you pill, any one of which is a tell. A forbidden-token scan over
//     the comment-stripped source keeps engine-identifying fields out, and the
//     import list is closed.
//   • Arm names ("Today's engine" / "New engine", the `value_core` literal)
//     live in exactly two files: the wire types and the results reveal. The
//     screen holds a card's trade and nothing else about it.
//   • `CalibrationScreen` mounts NO FeedbackFAB. It is a tab-stack screen under
//     RootNav's single global mount; a second one is the #196/#197 double-FAB.
//   • The tab's presence is decided ONCE at mount from
//     `useFeatureFlags.getState().flags['grading.blind']`, never `useFlag(...)`
//     — a mid-session flag revalidation must not insert or remove a tab under
//     the user's thumb — and it takes the third slot AHEAD of the seasonal
//     Draft tab, whose own <Tab.Screen> survives unchanged behind it.
//   • Every testID is a static `calibration.`-namespaced literal (or a
//     `.testID` member of the two const tables), the required set is exactly
//     present, and nothing extra sneaks in.
//   • The session-start POST has the 30 s timeout (`SLOW_POST_PATHS`) and the
//     wire module hits the five user routes, never the admin report.
//
// HONEST LABEL. This proves CODE SHAPE — which tokens, imports and literals
// exist in which files — not runtime behavior. It cannot see what a card looks
// like on a device or whether the poll actually stops at 60 s; that is the
// manual TestFlight checklist in scope.md §3 and the code-walk in
// code-walk-mobile.md. A broken scanner would pass this file forever, so
// assertion 0 plants a violation and checks that the scan fires.
//
// Run: node tests/check-blind-grading.js   (or: npm run test:blind-grading)

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
const parse = (rel, text) => ts.createSourceFile(
  rel, text ?? read(rel), ts.ScriptTarget.Latest, /* setParentNodes */ true,
  rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
);

const CARD   = 'src/components/GradingCard.tsx';
const RESULTS = 'src/components/GradingResults.tsx';
const SCREEN = 'src/screens/CalibrationScreen.tsx';
const API    = 'src/api/grading.ts';
const TABNAV = 'src/navigation/TabNav.tsx';
const CLIENT = 'src/api/client.ts';

// ── Forbidden tokens (lld §10.8) ───────────────────────────────────────────
// Run on COMMENT-STRIPPED source: a comment may explain what the card must
// never show; the code may not show it.
const CARD_FORBIDDEN = /\b(reasons?|arms?|model_arm|value_core|valueCore|engine|basis|lane|narrative|composite|fairness|mismatch|match_context|valuation|impression|trade_id|tradeId|preserve_server_order|likes_you|score)\b/i;
// The screen drops `engine` and `score`: its intro copy legitimately says
// "today's trade engine … the new one". Neither word identifies a CARD's arm.
const SCREEN_FORBIDDEN = /\b(reasons?|arms?|model_arm|value_core|valueCore|basis|lane|narrative|composite|fairness|mismatch|match_context|valuation|impression|trade_id|tradeId|preserve_server_order|likes_you)\b/i;

// Comment stripping with the TypeScript scanner. Template literals need the
// parser's dance — after a `${…}` substitution's closing brace the scanner
// must be told to re-scan the rest of the template, or the tail would be
// tokenized as code (and could swallow or invent a comment).
function stripComments(text) {
  const sc = ts.createScanner(ts.ScriptTarget.Latest, /* skipTrivia */ false,
                              ts.LanguageVariant.Standard, text);
  const out = [];
  const tpl = []; // brace depth inside each open template substitution
  let tok = sc.scan();
  while (tok !== ts.SyntaxKind.EndOfFileToken) {
    if (tok === ts.SyntaxKind.TemplateHead) {
      tpl.push(0);
    } else if (tpl.length && tok === ts.SyntaxKind.OpenBraceToken) {
      tpl[tpl.length - 1] += 1;
    } else if (tpl.length && tok === ts.SyntaxKind.CloseBraceToken) {
      if (tpl[tpl.length - 1] === 0) {
        tok = sc.reScanTemplateToken(false);
        if (tok === ts.SyntaxKind.TemplateTail) tpl.pop();
      } else {
        tpl[tpl.length - 1] -= 1;
      }
    }
    const isComment = tok === ts.SyntaxKind.SingleLineCommentTrivia
                   || tok === ts.SyntaxKind.MultiLineCommentTrivia;
    out.push(isComment ? ' ' : sc.getTokenText());
    tok = sc.scan();
  }
  return out.join('');
}

const firstHit = (re, text) => {
  const m = text.match(re);
  if (!m) return null;
  const line = text.slice(0, m.index).split('\n').length;
  return `'${m[0]}' at line ${line}`;
};

// ── AST helpers ────────────────────────────────────────────────────────────
const walk = (node, fn) => { fn(node); ts.forEachChild(node, (c) => walk(c, fn)); };

const importSpecifiers = (sf) => {
  const out = [];
  for (const st of sf.statements) {
    if (ts.isImportDeclaration(st) && ts.isStringLiteral(st.moduleSpecifier)) {
      out.push(st.moduleSpecifier.text);
    }
  }
  return out;
};

const attrOf = (attributes, want) => {
  for (const a of attributes.properties) {
    if (ts.isJsxAttribute(a) && a.name.getText() === want) return a;
  }
  return null;
};

const openingOf = (node) =>
  ts.isJsxSelfClosingElement(node) ? node
  : ts.isJsxElement(node) ? node.openingElement
  : null;

// Every `testID=` attribute in a file: {kind:'literal'|'member'|'other', text, line}.
function testIdAttrs(sf) {
  const out = [];
  walk(sf, (n) => {
    const op = openingOf(n);
    if (!op) return;
    const a = attrOf(op.attributes, 'testID');
    if (!a || !a.initializer) return;
    const line = sf.getLineAndCharacterOfPosition(a.getStart()).line + 1;
    const init = a.initializer;
    if (ts.isStringLiteral(init)) { out.push({ kind: 'literal', text: init.text, line }); return; }
    if (ts.isJsxExpression(init) && init.expression) {
      const e = init.expression;
      if (ts.isStringLiteral(e)) { out.push({ kind: 'literal', text: e.text, line }); return; }
      if (ts.isPropertyAccessExpression(e) && e.name.text === 'testID') {
        out.push({ kind: 'member', text: e.getText(), line }); return;
      }
      out.push({ kind: 'other', text: e.getText(), line }); return;
    }
    out.push({ kind: 'other', text: init.getText(), line });
  });
  return out;
}

const stringLiterals = (sf) => {
  const out = [];
  walk(sf, (n) => {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) out.push(n.text);
  });
  return out;
};

const listSrcFiles = (dir, out = []) => {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) listSrcFiles(p, out);
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
  }
  return out;
};

// The required testID set (scope.md §3). Exactly these, no more, no fewer.
const REQUIRED_IDS = [
  'calibration.loading', 'calibration.no-league', 'calibration.unavailable',
  'calibration.open-acquire', 'calibration.retry', 'calibration.start', 'calibration.purpose',
  'calibration.resume', 'calibration.progress', 'calibration.card',
  'calibration.grade-1', 'calibration.grade-2', 'calibration.grade-3',
  'calibration.grade-4', 'calibration.grade-5',
  'calibration.tag.overpay', 'calibration.tag.they_wont_accept',
  'calibration.tag.junk_filler', 'calibration.tag.too_small',
  'calibration.tag.wrong_for_my_window', 'calibration.tag.wrong_for_their_window',
  'calibration.tag.same_guy_again',
  'calibration.submit', 'calibration.skip', 'calibration.results', 'calibration.done',
];

// ── 0. Self-test ───────────────────────────────────────────────────────────
// A scanner that matched nothing would pass every assertion below forever.
{
  const planted = stripComments('const x = card.reasons;');
  const clean   = stripComments('const x = card.trade;');
  const commentOnly = stripComments('// card.reasons must never render\nconst x = card.trade;');
  const templated = stripComments('const s = `${a.nfl_team ?? "FA"} · ${a.age}`; // arms\nconst y = 1;');
  const hits = CARD_FORBIDDEN.test(planted);
  const stays = !CARD_FORBIDDEN.test(clean);
  const stripped = !CARD_FORBIDDEN.test(commentOnly);
  const tplOk = !CARD_FORBIDDEN.test(templated) && templated.includes('const y = 1;');
  if (hits && stays && stripped && tplOk) {
    ok('self-test: scanner fires on planted `card.reasons`, stays clean on `card.trade`, '
       + 'ignores a comment, and survives a template literal with substitutions');
  } else {
    fail('self-test: forbidden-token scanner',
         `fires on planted=${hits} clean=${stays} comment-stripped=${stripped} template=${tplOk}`);
  }
}

// ── 1. GradingCard: no forbidden token; closed import list ────────────────
{
  const sf = parse(CARD);
  const hit = firstHit(CARD_FORBIDDEN, stripComments(sf.getFullText()));
  if (!hit) ok(`${CARD}: no engine-identifying token in code`);
  else fail(`${CARD}: no engine-identifying token`, `found ${hit}`);

  const ALLOWED = new Set(['react', 'react-native', '../theme/chalkline', './chalkline', '../api/grading']);
  const specs = importSpecifiers(sf);
  const extra = specs.filter((s) => !ALLOWED.has(s));
  if (specs.length > 0 && extra.length === 0) {
    ok(`${CARD}: imports only {${[...ALLOWED].join(', ')}}`);
  } else {
    fail(`${CARD}: closed import list`,
         `unexpected import(s): ${extra.join(', ') || '(none parsed — did the file move?)'}`);
  }
}

// ── 2. api/grading.ts wire types ──────────────────────────────────────────
{
  const sf = parse(API);
  const text = sf.getFullText();
  const ifaceKeys = {};
  const aliasUnions = {};
  for (const st of sf.statements) {
    if (ts.isInterfaceDeclaration(st)) {
      ifaceKeys[st.name.text] = st.members
        .filter(ts.isPropertySignature)
        .map((m) => m.name.getText());
    } else if (ts.isTypeAliasDeclaration(st) && ts.isUnionTypeNode(st.type)) {
      aliasUnions[st.name.text] = st.type.types.map((t) =>
        ts.isTypeLiteralNode(t)
          ? t.members.filter(ts.isPropertySignature).map((m) => m.name.getText())
          : null);
    }
  }
  const same = (a, b) => a && a.length === b.length && b.every((k) => a.includes(k));
  const expect = {
    GradingAsset: ['id', 'name', 'position', 'nfl_team', 'age', 'value'],
    GradingTrade: ['partner_name', 'give', 'receive'],
    GradingCard:  ['card_id', 'position', 'trade'],
  };
  for (const [name, keys] of Object.entries(expect)) {
    if (same(ifaceKeys[name], keys)) ok(`${API}: ${name} = {${keys.join(', ')}}`);
    else fail(`${API}: ${name} keys`, `got {${(ifaceKeys[name] || []).join(', ')}}, want {${keys.join(', ')}}`);
  }
  const next = aliasUnions.GradingNext;
  const leak = /arm|reason|engine|basis|lane|score/i;
  if (next && next.length === 2 && next.every((m) => m && !m.some((k) => leak.test(k)))) {
    ok(`${API}: GradingNext's two members carry no arm/reason/engine/basis/lane/score key`);
  } else {
    fail(`${API}: GradingNext members`, `parsed ${JSON.stringify(next)}`);
  }
  if (text.includes('X-Device-Id') && text.includes('getDeviceId')) {
    ok(`${API}: sends X-Device-Id via getDeviceId (device-unit overlay resolution)`);
  } else {
    fail(`${API}: X-Device-Id`, 'the wire module must attach X-Device-Id from getDeviceId on every call');
  }
}

// ── 3. CalibrationScreen: no forbidden token, one results mount, no FAB ───
{
  const sf = parse(SCREEN);
  const code = stripComments(sf.getFullText());
  const hit = firstHit(SCREEN_FORBIDDEN, code);
  if (!hit) ok(`${SCREEN}: no arm-identifying token in code`);
  else fail(`${SCREEN}: no arm-identifying token`, `found ${hit}`);

  const mounts = (code.match(/<GradingResults\b/g) || []).length;
  if (mounts === 1) ok(`${SCREEN}: <GradingResults> mounted exactly once (the results phase)`);
  else fail(`${SCREEN}: <GradingResults> exactly once`, `found ${mounts}`);

  const specs = importSpecifiers(sf);
  const bad = specs.filter((s) => /TradeCard|api\/trades|shared\/types/.test(s));
  if (bad.length === 0) ok(`${SCREEN}: imports nothing from TradeCard, api/trades or shared/types`);
  else fail(`${SCREEN}: forbidden import`, bad.join(', '));

  if (!/FeedbackFAB/.test(code)) {
    ok(`${SCREEN}: no FeedbackFAB (tab-stack screen — RootNav's global mount covers it)`);
  } else {
    fail(`${SCREEN}: no FeedbackFAB`,
         'a tab-stack screen mounting its own FAB is the #196/#197 double-FAB bug');
  }
}

// ── 4. Arm names stay in one place ────────────────────────────────────────
{
  const files = listSrcFiles(path.join(MOBILE, 'src'));
  const rel = (p) => path.relative(MOBILE, p).split(path.sep).join('/');
  const vcAllowed = new Set([API, RESULTS]);
  const vcLeaks = files.filter((p) => !vcAllowed.has(rel(p)) && fs.readFileSync(p, 'utf8').includes('value_core'));
  const labelLeaks = files.filter((p) => rel(p) !== RESULTS
    && /Today's engine|New engine/.test(fs.readFileSync(p, 'utf8')));
  if (vcLeaks.length === 0) ok(`src/: the literal value_core appears only in ${API} and ${RESULTS}`);
  else fail('src/: value_core confined', vcLeaks.map(rel).join(', '));
  if (labelLeaks.length === 0) ok(`src/: "Today's engine" / "New engine" appear only in ${RESULTS}`);
  else fail('src/: arm labels confined', labelLeaks.map(rel).join(', '));
  const resultsText = read(RESULTS);
  if (/Today's engine/.test(resultsText) && /New engine/.test(resultsText)) {
    ok(`${RESULTS}: carries both arm labels (the reveal)`);
  } else {
    fail(`${RESULTS}: arm labels present`, 'the results component must name both arms');
  }
}

// ── 5. testIDs: static, namespaced, exactly the required set ──────────────
{
  const found = new Set();
  const problems = [];
  for (const rel of [CARD, RESULTS, SCREEN]) {
    const sf = parse(rel);
    for (const a of testIdAttrs(sf)) {
      if (a.kind === 'other') problems.push(`${rel}:${a.line} testID={${a.text}} is not a literal or a .testID table member`);
      else if (a.kind === 'literal') found.add(a.text);
    }
    for (const s of stringLiterals(sf)) if (s.startsWith('calibration.')) found.add(s);
  }
  const required = new Set(REQUIRED_IDS);
  const extra = [...found].filter((id) => !required.has(id));
  const missing = REQUIRED_IDS.filter((id) => !found.has(id));
  if (problems.length === 0) ok('testIDs: every testID= in the three new files is a string literal or a .testID table member');
  else fail('testIDs: static only', problems.join('; '));
  if (extra.length === 0 && missing.length === 0) {
    ok(`testIDs: exactly the ${REQUIRED_IDS.length} required calibration.* ids are present`);
  } else {
    fail('testIDs: required set',
         `${missing.length ? `missing: ${missing.join(', ')}` : ''}${missing.length && extra.length ? '; ' : ''}`
           + `${extra.length ? `not in scope.md §3: ${extra.join(', ')}` : ''}`);
  }
}

// ── 6. TabNav: mount-once presence, the slot, the Draft block survives ────
{
  const sf = parse(TABNAV);
  const code = stripComments(sf.getFullText());

  const declared = /const \[showCalibrationTab\] = useState\(\s*\(\) =>\s*!!useFeatureFlags\.getState\(\)\.flags\['grading\.blind'\]/.test(code);
  if (declared) ok(`${TABNAV}: showCalibrationTab decided once at mount from useFeatureFlags.getState().flags['grading.blind']`);
  else fail(`${TABNAV}: showCalibrationTab`, "expected `const [showCalibrationTab] = useState(() => !!useFeatureFlags.getState().flags['grading.blind'])`");

  if (!/useFlag\(\s*['"]grading\.blind['"]\s*\)/.test(code)) ok(`${TABNAV}: no useFlag('grading.blind') (a live read could insert/remove the tab mid-session)`);
  else fail(`${TABNAV}: no useFlag('grading.blind')`, 'tab presence must be imperative and mount-once');

  let calib = null;
  let draft = null;
  walk(sf, (n) => {
    const op = openingOf(n);
    if (!op || op.tagName.getText() !== 'Tab.Screen') return;
    const nameAttr = attrOf(op.attributes, 'name');
    const name = nameAttr && nameAttr.initializer && ts.isStringLiteral(nameAttr.initializer)
      ? nameAttr.initializer.text : null;
    const opt = attrOf(op.attributes, 'options');
    const lis = attrOf(op.attributes, 'listeners');
    const rec = {
      options: opt && opt.initializer ? opt.initializer.getText() : '',
      listeners: lis && lis.initializer ? lis.initializer.getText() : '',
      start: n.getStart(),
    };
    if (name === 'Calibration') calib = rec;
    if (name === 'Draft') draft = rec;
  });
  if (calib && /tabBarButtonTestID:\s*'tab\.calibration'/.test(calib.options)
      && /trackTab\('calibration'/.test(calib.listeners)) {
    ok(`${TABNAV}: <Tab.Screen name="Calibration"> with tabBarButtonTestID 'tab.calibration' and trackTab('calibration')`);
  } else {
    fail(`${TABNAV}: Calibration Tab.Screen`,
         calib ? `options=${calib.options.slice(0, 80)}… listeners=${calib.listeners.slice(0, 80)}…` : 'no <Tab.Screen name="Calibration"> found');
  }

  const iCal = code.indexOf('showCalibrationTab ?');
  const iCalName = code.indexOf('name="Calibration"');
  const iDraftTern = code.indexOf(': showDraftTab ?');
  const iDraftName = code.indexOf('name="Draft"');
  if (iCal >= 0 && iCal < iCalName && iCalName < iDraftTern && iDraftTern < iDraftName) {
    ok(`${TABNAV}: slot renders showCalibrationTab ? Calibration : showDraftTab ? Draft : null (Calibration ahead of Draft)`);
  } else {
    fail(`${TABNAV}: third-slot order`,
         `indices showCalibrationTab?=${iCal} name="Calibration"=${iCalName} : showDraftTab ?=${iDraftTern} name="Draft"=${iDraftName}`);
  }
  if (draft && /tabBarButtonTestID:\s*'tab\.draft'/.test(draft.options)) {
    ok(`${TABNAV}: the Draft <Tab.Screen> survives with tabBarButtonTestID 'tab.draft' (testid-lint still resolves draft-room@draft.yaml)`);
  } else {
    fail(`${TABNAV}: Draft Tab.Screen intact`, draft ? 'tab.draft missing from its options' : 'no <Tab.Screen name="Draft"> found');
  }
}

// ── 7. client.ts: the session-start POST gets the slow timeout ────────────
{
  const sf = parse(CLIENT);
  let paths = null;
  walk(sf, (n) => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === 'SLOW_POST_PATHS'
        && n.initializer && ts.isArrayLiteralExpression(n.initializer)) {
      paths = n.initializer.elements.filter(ts.isStringLiteral).map((e) => e.text);
    }
  });
  if (paths && paths.includes('/api/grading/sessions')) ok(`${CLIENT}: SLOW_POST_PATHS includes '/api/grading/sessions' (hld §7: 30 s cap on session start)`);
  else fail(`${CLIENT}: SLOW_POST_PATHS`, `got ${JSON.stringify(paths)}`);
}

// ── 8. api/grading.ts routes ──────────────────────────────────────────────
{
  const sf = parse(API);
  const text = sf.getFullText();
  let importsApi = false;
  for (const st of sf.statements) {
    if (ts.isImportDeclaration(st) && ts.isStringLiteral(st.moduleSpecifier) && st.moduleSpecifier.text === './client'
        && st.importClause && st.importClause.namedBindings && ts.isNamedImports(st.importClause.namedBindings)) {
      importsApi = st.importClause.namedBindings.elements.some((e) => e.name.text === 'api');
    }
  }
  if (importsApi) ok(`${API}: imports { api } from './client' (every call rides the shared transport)`);
  else fail(`${API}: transport`, "expected `import { api, … } from './client'`");
  const need = ['/api/grading/sessions', '/current', '/next', '/api/grading/cards/', '/results'];
  const missing = need.filter((p) => !text.includes(p));
  if (missing.length === 0) ok(`${API}: references the five user routes`);
  else fail(`${API}: routes`, `missing ${missing.join(', ')}`);
  if (!text.includes('/api/admin/')) ok(`${API}: never references /api/admin/ (the report is cron-secret only)`);
  else fail(`${API}: no admin route`, 'the mobile client must not call the admin report');
}

// ── 9. package.json script ────────────────────────────────────────────────
{
  const pkg = JSON.parse(read('package.json'));
  const want = 'node tests/check-blind-grading.js';
  if (pkg.scripts && pkg.scripts['test:blind-grading'] === want) ok(`package.json: scripts["test:blind-grading"] === "${want}"`);
  else fail('package.json: test:blind-grading script', `got ${JSON.stringify(pkg.scripts && pkg.scripts['test:blind-grading'])}`);
}

console.log(failures === 0
  ? '\nAll blind-grading checks passed.'
  : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
