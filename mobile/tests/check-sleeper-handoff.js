#!/usr/bin/env node
// Sleeper hand-off (#351 PRD §7.1): the subset of S1–S16 that is true on
// the build/open-external-helper branch, plus league-eng's claim-sheet
// migration (build/b3-claim-handoff).
//
// WHY THIS EXISTS. FTF handed off to Sleeper with
// `https://sleeper.com/leagues/...` links. sleeper.com's AASA claims no
// league path, so on an iPhone every one went Safari → Branch → Sleeper's
// HOME screen with the league dropped (#351 F1/F3), and a rejection was
// swallowed by `.catch(() => {})`. utils/sleeperHandoff.ts opens the
// `sleeper://` scheme instead, through utils/openExternal.ts, and shows the
// Get Sleeper alert (operator D2, 2026-10-20) when Sleeper isn't installed.
//
// Here (S-ids are the PRD's; H-ids are the b3 brief's, not the PRD's):
//   S1  ClaimSheet, FreeAgentsScreen and UsageTrendsScreen: no
//       `sleeper.com/leagues` literal, no Linking.openURL to a Sleeper host [AST]
//   S2  SendInSleeperButton imports openInSleeperApp from
//       ../utils/sleeperHandoff and calls it from openInSleeper (target
//       'trade'). ClaimSheet half: the same import, and the
//       fa-claim.open-sleeper CTA's handler calls it with target 'add'
//       and no clipboardText (no on-sheet disclosure, so nothing is
//       copied). The sheet has no fa-claim.steps / fa-claim.step.* /
//       fa-claim.footer testID and no KeyboardAvoidingView: the operator
//       ruled out in-app claim instructions (2026-11-01), which retired
//       S8 (PRD §4.2's steps block) and P1 (its pinned footer)             [AST]
//   S9  the eight NO_ADD_REASON strings verbatim (the three platform
//       bodies are #385's, LEG-M10); explainNoAdd and resolveAddPlatform
//       byte-identical to 04eae95b (AC-10)                                 [AST]
//   H1  both ClaimSheet hosts pass `surface` (free_agents / usage_trends)
//       for the hand-off's ExternalTarget.surface                          [AST]
//   H2  FreeAgentsScreen's render chain tests query.isError before
//       query.isLoading (release-lead QA rule)                             [AST]
//   S3  scheme opens: one openURL, `sleeper://…`, outcome 'app', no alert  [executed]
//   S4  scheme rejects: the D2 alert, whose Get Sleeper opens
//       apps.apple.com/app/id987367543; outcome 'not_installed'; no
//       sleeper.com https open                                              [executed]
//   S5  canOpenURL (a throwing stub) is never touched, and neither helper
//       references it                                                       [executed + AST]
//   S6  clipboardText is copied BEFORE openURL                              [executed]
//   S7  sleeperAppUrl, add target: shipped rungs and a test-local ladder;
//       never https; never a league rung for a non-numeric id              [executed]
//   S10 SLEEPER_PROVEN_RUNGS is one exported declaration; every member is
//       in its target's closed ladder; `bare` is last; every non-bare member
//       has a PASS row in docs/plans/sleeper-fa-deeplink/device-results.md.
//       That file doesn't exist yet, so only `bare` passes                  [executed + file read]
//   S13 sleeperAppUrl, trade target: trades_tab when proven, the floor
//       otherwise, never an add-ladder path                                 [executed]
//   S16 SendInSleeperButton has no Linking at all, so doPropose /
//       confirmSend / goConnect can't open anything                        [AST]
//
// Deferred (not true on this branch; each owner adds its S-check with the
// migration):
//   S11, S12, S15 → trades-eng (TradesScreen, useTradeQueue)
//   S14 → platforms-eng follow-up: the Send-in-Sleeper steps confirm +
//       clipboard (PRD §4.3), waiting on design-lead / ux-lead copy
//
// HONEST LABEL (G-035): S1, S2, S9, S16, H1 and H2 prove wirings are
// present, not behavior: no claim-sheet code is executed here. S3–S7, S10
// and S13 execute the real modules.
//
// Run: node tests/check-sleeper-handoff.js

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
const HANDOFF = 'src/utils/sleeperHandoff.ts';
const HELPER = 'src/utils/openExternal.ts';
const BUTTON = 'src/components/SendInSleeperButton.tsx';
const CLAIM = 'src/components/ClaimSheet.tsx';
const FREE_AGENTS = 'src/screens/FreeAgentsScreen.tsx';
const USAGE_TRENDS = 'src/screens/UsageTrendsScreen.tsx';
const DEVICE_RESULTS = path.join(ROOT, '..', 'docs/plans/sleeper-fa-deeplink/device-results.md');
const APP_STORE_SLEEPER = 'https://apps.apple.com/app/id987367543';

// PRD §4.1, copied here on purpose: the module's own ladder is checked
// against this, so widening a target's ladder in code alone fails.
const CLOSED_LADDER = {
  add: ['add', 'player', 'players_tab', 'league', 'bare'],
  trade: ['trade', 'trades_tab', 'league', 'bare'],
  league: ['league', 'bare'],
};

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const parse = (rel) =>
  ts.createSourceFile(rel, read(rel), ts.ScriptTarget.Latest, true,
    rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
function walk(node, fn) {
  fn(node);
  ts.forEachChild(node, (c) => walk(c, fn));
}
function transpile(rel) {
  return ts.transpileModule(read(rel), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
}
const helperJs = transpile(HELPER);
const handoffJs = transpile(HANDOFF);

// Fresh helper + hand-off per scenario (the helper's in-flight lock is
// module state). `behave(url)` returns 'resolve' or 'reject'.
function env(behave) {
  const log = [];
  const alerts = [];
  const Linking = {
    openURL: (url) => {
      log.push(['open', url]);
      return behave(url) === 'resolve'
        ? Promise.resolve(true)
        : Promise.reject(new Error(`Unable to open URL: ${url}`));
    },
    canOpenURL: () => {
      log.push(['canOpen']);
      throw new Error('canOpenURL must never be called (#351 F8)');
    },
  };
  const Alert = { alert: (title, body, buttons) => alerts.push({ title, body, buttons }) };
  const helper = { exports: {} };
  new Function('module', 'exports', 'require', helperJs)(helper, helper.exports, (name) => {
    if (name === 'react-native') return { Linking, Alert };
    if (name === './clipboard') return { copyText: (s) => log.push(['copy', s]) };
    throw new Error(`openExternal.ts gained an unexpected runtime import ("${name}")`);
  });
  const handoff = { exports: {} };
  new Function('module', 'exports', 'require', handoffJs)(handoff, handoff.exports, (name) => {
    if (name === './openExternal') return helper.exports;
    // The granted sleeper_handoff_resolved; check-sleeper-handoff-event.js pins it.
    if (name === '../api/events') return { track: () => {} };
    throw new Error(
      `sleeperHandoff.ts gained an unexpected runtime import ("${name}") — it must ` +
        'open through ./openExternal only.',
    );
  });
  return {
    ...handoff.exports,
    log,
    alerts,
    opens: () => log.filter((e) => e[0] === 'open').map((e) => e[1]),
  };
}
const flush = () => new Promise((r) => setImmediate(r));

// ═══════════════════════════════════════════════════════════════════════
// S2 / S16 — SendInSleeperButton wiring
// ═══════════════════════════════════════════════════════════════════════
{
  const sf = parse(BUTTON);
  let imported = false;
  let linkingRefs = 0;
  const fnText = {};
  walk(sf, (n) => {
    if (
      ts.isImportDeclaration(n) &&
      n.moduleSpecifier.text === '../utils/sleeperHandoff' &&
      n.importClause && n.importClause.namedBindings &&
      ts.isNamedImports(n.importClause.namedBindings) &&
      n.importClause.namedBindings.elements.some((e) => e.name.text === 'openInSleeperApp')
    ) imported = true;
    if (ts.isIdentifier(n) && n.text === 'Linking') linkingRefs += 1;
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer) {
      fnText[n.name.text] = n.initializer.getText(sf);
    }
  });
  const open = fnText.openInSleeper || '';
  assert(imported, 'S2 SendInSleeperButton imports openInSleeperApp from ../utils/sleeperHandoff');
  assert(
    /\bopenInSleeperApp\(\s*\{[^}]*target:\s*'trade'/.test(open),
    "S2 openInSleeper calls openInSleeperApp({ target: 'trade', … })",
    open.slice(0, 200),
  );
  assert(linkingRefs === 0, 'S16 SendInSleeperButton has no Linking reference at all', `${linkingRefs} found`);
  for (const f of ['doPropose', 'confirmSend', 'goConnect']) {
    assert(
      !!fnText[f] && !/\bLinking\b|openInSleeperApp|openPlatform/.test(fnText[f]),
      `S16 ${f} opens nothing`,
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════
// S1 / S2 (ClaimSheet half) / S9 / H1 / H2 — the claim sheet and its hosts
// ═══════════════════════════════════════════════════════════════════════
const unparen = (n) => (ts.isParenthesizedExpression(n) ? unparen(n.expression) : n);
const squash = (s) => s.replace(/\s+/g, '');
// name → initializer text, for every `const name = …` in the file.
function declarations(sf) {
  const out = {};
  walk(sf, (n) => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer) {
      out[n.name.text] = n.initializer.getText(sf);
    }
  });
  return out;
}
// Attributes (name → initializer text) of each JSX element named `tag`.
function jsxMounts(sf, tag) {
  const out = [];
  walk(sf, (n) => {
    if ((ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) && n.tagName.getText(sf) === tag) {
      const attrs = {};
      for (const a of n.attributes.properties) {
        if (ts.isJsxAttribute(a)) attrs[a.name.getText(sf)] = a.initializer ? a.initializer.getText(sf) : 'true';
      }
      out.push(attrs);
    }
  });
  return out;
}

// S1 — no https Sleeper hand-off left in the claim path.
for (const rel of [CLAIM, FREE_AGENTS, USAGE_TRENDS]) {
  const sf = parse(rel);
  const literals = [];
  const sleeperOpens = [];
  walk(sf, (n) => {
    if (
      (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) ||
        ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) &&
      /sleeper\.com\/leagues/.test(n.text)
    ) literals.push(n.getText(sf));
    if (
      ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) &&
      ts.isIdentifier(n.expression.expression) && n.expression.expression.text === 'Linking' &&
      n.expression.name.text === 'openURL'
    ) {
      const arg = n.arguments[0] ? n.arguments[0].getText(sf) : '';
      if (/sleeper/i.test(arg)) sleeperOpens.push(arg);
    }
  });
  assert(literals.length === 0, `S1 ${path.basename(rel)} has no sleeper.com/leagues literal`, literals.join('; '));
  assert(sleeperOpens.length === 0, `S1 ${path.basename(rel)} has no direct Linking.openURL to a Sleeper host`, sleeperOpens.join('; '));
}

// S2 (ClaimSheet half) — the CTA hands off through openInSleeperApp.
{
  const sf = parse(CLAIM);
  let imported = false;
  walk(sf, (n) => {
    if (
      ts.isImportDeclaration(n) &&
      n.moduleSpecifier.text === '../utils/sleeperHandoff' &&
      n.importClause && n.importClause.namedBindings &&
      ts.isNamedImports(n.importClause.namedBindings) &&
      n.importClause.namedBindings.elements.some((e) => e.name.text === 'openInSleeperApp')
    ) imported = true;
  });
  const open = declarations(sf).openSleeper || '';
  const cta = jsxMounts(sf, 'Button').filter((a) => a.testID === '"fa-claim.open-sleeper"');
  assert(imported, 'S2 ClaimSheet imports openInSleeperApp from ../utils/sleeperHandoff');
  assert(
    cta.length === 1 && cta[0].onPress === '{openSleeper}' && cta[0].label === '"Open in Sleeper to claim"',
    'S2 one fa-claim.open-sleeper CTA, label unchanged, onPress={openSleeper}',
    JSON.stringify(cta),
  );
  assert(
    /\bopenInSleeperApp\(\s*\{[^}]*target:\s*'add'/.test(open),
    "S2 openSleeper calls openInSleeperApp({ target: 'add', … })",
    open.slice(0, 200),
  );
  assert(
    /\bleagueId\b/.test(open) && /\bplayerId:\s*row\.player_id\b/.test(open) && /\bsurface\b/.test(open),
    'S2 openSleeper passes leagueId, playerId: row.player_id and the host surface',
    open.slice(0, 200),
  );
}

// S2 (ClaimSheet half, continued) — the CTA is a plain hand-off. The
// operator ruled out in-app claim instructions (2026-11-01 design review;
// a later build submits the claim in-app), so the sheet has no steps block
// and no pinned footer, and with no on-sheet disclosure the CTA copies
// nothing (#351 PRD §4.2: never copy silently).
{
  const sf = parse(CLAIM);
  let openFn = null;
  const instructionIds = [];
  let kavRefs = 0;
  walk(sf, (n) => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === 'openSleeper') openFn = n.initializer;
    if (
      (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) ||
        ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) &&
      /fa-claim\.(steps|step\.|footer)/.test(n.text)
    ) instructionIds.push(n.getText(sf));
    if (ts.isIdentifier(n) && n.text === 'KeyboardAvoidingView') kavRefs += 1;
  });
  const calls = [];
  if (openFn) {
    walk(openFn, (n) => {
      if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === 'openInSleeperApp') calls.push(n);
    });
  }
  const arg = calls.length === 1 ? calls[0].arguments[0] : null;
  // A spread could carry clipboardText in, so it fails too.
  const copies = arg && ts.isObjectLiteralExpression(arg)
    ? arg.properties.filter((p) => ts.isSpreadAssignment(p) || (p.name && /clipboardText/.test(p.name.getText(sf))))
    : null;
  assert(
    !!copies && copies.length === 0,
    "S2 openSleeper's one openInSleeperApp call passes no clipboardText (nothing is copied without the on-sheet disclosure)",
    calls.length !== 1 ? `${calls.length} openInSleeperApp calls in openSleeper` : arg.getText(sf).slice(0, 240),
  );
  assert(instructionIds.length === 0,
    'S2 ClaimSheet has no fa-claim.steps / fa-claim.step.* / fa-claim.footer testID (no in-app claim instructions)',
    instructionIds.join('; '));
  assert(kavRefs === 0, 'S2 ClaimSheet has no KeyboardAvoidingView (no pinned footer)', `${kavRefs} found`);
}

// S9 — the non-Sleeper claim paths match their pinned values (#351 AC-10).
// Titles, `local`, explainNoAdd and resolveAddPlatform are copied from
// 04eae95b; the espn / mfl / fleaflicker bodies are #385's (LEG-M10,
// re-baselined 2026-10-29 for release-lead), because the 04eae95b bodies
// are false copy that must not return.
{
  const EXPECTED_REASONS = {
    espn: {
      title: "Can't add in ESPN leagues yet",
      body: "Roster moves for this ESPN league can't be made from Fleeced. Open the ESPN Fantasy app to add this player.",
    },
    mfl: {
      title: "Can't add in MFL leagues yet",
      body: "Roster moves for this MFL league can't be made from Fleeced. Open MFL to add this player.",
    },
    fleaflicker: {
      title: "Can't add in Fleaflicker leagues yet",
      body: "Roster moves for this Fleaflicker league can't be made from Fleeced. Open Fleaflicker to add this player.",
    },
    local: {
      title: "Can't add in this league",
      body: 'This league isn’t connected to a fantasy platform, so there’s no roster to add this player to.',
    },
  };
  const EXPECTED_FUNCTIONS = {
    explainNoAdd: [
      "export function explainNoAdd(addPlatform: Exclude<AddPlatform, 'sleeper'>) {",
      '  const reason = NO_ADD_REASON[addPlatform];',
      '  Alert.alert(reason.title, reason.body);',
      '}',
    ].join('\n'),
    resolveAddPlatform: [
      'export function resolveAddPlatform(leagueId: string | undefined, isDemo: boolean): AddPlatform {',
      "  if (!leagueId || isDemo) return 'local';",
      "  if (isEspnLeague(leagueId)) return 'espn';",
      "  if (isMflLeague(leagueId)) return 'mfl';",
      "  if (isFleaflickerLeague(leagueId)) return 'fleaflicker';",
      '  // Real Sleeper league ids are numeric; anything else is a local league.',
      "  return /^\\d+$/.test(leagueId) ? 'sleeper' : 'local';",
      '}',
    ].join('\n'),
  };
  const sf = parse(CLAIM);
  // Evaluates a string literal or a `+` chain of them; null for anything else.
  const str = (n) => {
    n = unparen(n);
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) return n.text;
    if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      const l = str(n.left), r = str(n.right);
      return l === null || r === null ? null : l + r;
    }
    return null;
  };
  const reasons = {};
  const fns = {};
  walk(sf, (n) => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === 'NO_ADD_REASON' &&
        n.initializer && ts.isObjectLiteralExpression(n.initializer)) {
      for (const p of n.initializer.properties) {
        if (!ts.isPropertyAssignment(p) || !ts.isObjectLiteralExpression(p.initializer)) continue;
        reasons[p.name.getText(sf)] = {};
        for (const q of p.initializer.properties) {
          if (ts.isPropertyAssignment(q)) reasons[p.name.getText(sf)][q.name.getText(sf)] = str(q.initializer);
        }
      }
    }
    if (ts.isFunctionDeclaration(n) && n.name && n.name.text in EXPECTED_FUNCTIONS) fns[n.name.text] = n.getText(sf);
  });
  assert(
    JSON.stringify(Object.keys(reasons)) === JSON.stringify(Object.keys(EXPECTED_REASONS)),
    'S9 NO_ADD_REASON has exactly espn / mfl / fleaflicker / local',
    JSON.stringify(Object.keys(reasons)),
  );
  for (const [platform, want] of Object.entries(EXPECTED_REASONS)) {
    for (const field of ['title', 'body']) {
      const got = reasons[platform] && reasons[platform][field];
      assert(got === want[field], `S9 NO_ADD_REASON.${platform}.${field} verbatim`, JSON.stringify(got));
    }
  }
  for (const [name, want] of Object.entries(EXPECTED_FUNCTIONS)) {
    assert(fns[name] === want, `S9 ${name} byte-identical`, fns[name] ? fns[name].slice(0, 200) : 'not found');
  }
}

// H1 — both hosts name their surface.
{
  const fa = parse(FREE_AGENTS);
  const faMounts = jsxMounts(fa, 'ClaimSheet');
  assert(faMounts.length === 1 && faMounts[0].surface === '"free_agents"',
    'H1 FreeAgentsScreen mounts ClaimSheet with surface="free_agents"', JSON.stringify(faMounts));

  const ut = parse(USAGE_TRENDS);
  const utMounts = jsxMounts(ut, 'ClaimSheet');
  assert(utMounts.length === 1 && utMounts[0].surface === '"usage_trends"',
    'H1 UsageTrendsScreen mounts ClaimSheet with surface="usage_trends"', JSON.stringify(utMounts));
}

// H2 — FreeAgentsScreen: an error renders the error state, never the spinner.
{
  const sf = parse(FREE_AGENTS);
  const conds = [];
  walk(sf, (n) => {
    if (ts.isConditionalExpression(n)) conds.push(n);
  });
  const test = (want) => conds.filter((c) => unparen(c.condition).getText(sf) === want);
  const err = test('query.isError');
  const load = test('query.isLoading');
  assert(
    err.length === 1 && load.length === 1 &&
      load[0].pos >= err[0].whenFalse.pos && load[0].end <= err[0].whenFalse.end,
    'H2 FreeAgentsScreen tests query.isError before query.isLoading (isLoading sits in the isError=false branch)',
    `${err.length} isError / ${load.length} isLoading conditionals`,
  );
}

// ═══════════════════════════════════════════════════════════════════════
// S5 (text half) — neither helper references canOpenURL
// ═══════════════════════════════════════════════════════════════════════
for (const rel of [HANDOFF, HELPER]) {
  let refs = 0;
  walk(parse(rel), (n) => {
    if (ts.isIdentifier(n) && n.text === 'canOpenURL') refs += 1;
  });
  assert(refs === 0, `S5 ${path.basename(rel)} never references canOpenURL`, `${refs} found`);
}

// ═══════════════════════════════════════════════════════════════════════
// S10 — SLEEPER_PROVEN_RUNGS vs device-results.md
// ═══════════════════════════════════════════════════════════════════════
{
  let decls = 0;
  let exported = false;
  walk(parse(HANDOFF), (n) => {
    if (ts.isVariableStatement(n)) {
      for (const d of n.declarationList.declarations) {
        if (ts.isIdentifier(d.name) && d.name.text === 'SLEEPER_PROVEN_RUNGS') {
          decls += 1;
          exported = (n.modifiers || []).some((m) => m.kind === ts.SyntaxKind.ExportKeyword);
        }
      }
    }
  });
  assert(decls === 1 && exported, 'S10 SLEEPER_PROVEN_RUNGS is one exported declaration', `${decls} found`);

  const { SLEEPER_PROVEN_RUNGS: proven, SLEEPER_RUNG_LADDER: ladder } = env(() => 'resolve');
  assert(
    JSON.stringify(ladder) === JSON.stringify(CLOSED_LADDER),
    "S10 the module's SLEEPER_RUNG_LADDER is PRD §4.1's closed ladder",
    JSON.stringify(ladder),
  );

  const passRows = fs.existsSync(DEVICE_RESULTS)
    ? fs.readFileSync(DEVICE_RESULTS, 'utf8').split('\n')
        .filter((l) => l.trim().startsWith('|') && /\bPASS\b/.test(l))
    : [];
  const hasPass = (rung) => passRows.some((l) => l.includes(`\`${rung}\``));
  for (const target of Object.keys(CLOSED_LADDER)) {
    const rungs = proven[target] || [];
    assert(rungs.length > 0 && rungs[rungs.length - 1] === 'bare', `S10 ${target}: \`bare\` is last`, JSON.stringify(rungs));
    for (const r of rungs) {
      assert(CLOSED_LADDER[target].includes(r), `S10 ${target}: '${r}' is in the target's ladder`);
      if (r !== 'bare') {
        assert(
          hasPass(r),
          `S10 ${target}: '${r}' has a PASS row in device-results.md`,
          fs.existsSync(DEVICE_RESULTS) ? 'no PASS row names it' : 'device-results.md does not exist yet: only `bare` may ship',
        );
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════
// S7 / S13 — sleeperAppUrl, executed
// ═══════════════════════════════════════════════════════════════════════
{
  const { sleeperAppUrl, SLEEPER_PROVEN_RUNGS: shipped } = env(() => 'resolve');
  const L = '1048293', P = '4046';
  const inputs = [
    { leagueId: L, playerId: P },
    { leagueId: L },
    { leagueId: 'espn_123', playerId: P },
    { leagueId: undefined },
  ];

  // S7 add target
  for (const i of inputs) {
    const u = sleeperAppUrl({ target: 'add', ...i });
    assert(u === 'sleeper://', `S7 shipped rungs, add ${JSON.stringify(i)} → sleeper://`, u);
  }
  const playersTab = { ...shipped, add: ['players_tab', 'bare'] };
  const s7 = inputs.map((i) => sleeperAppUrl({ target: 'add', ...i }, playersTab));
  assert(s7[0] === `sleeper://leagues/${L}/players`, 'S7 players_tab: numeric league + player → the Players tab', s7[0]);
  assert(s7[1] === `sleeper://leagues/${L}/players`, 'S7 players_tab: league only → the Players tab', s7[1]);
  assert(s7[2] === 'sleeper://', "S7 players_tab: 'espn_123' never yields a league rung", s7[2]);
  assert(s7[3] === 'sleeper://', 'S7 players_tab: no league → the floor', s7[3]);
  const full = { ...shipped, add: CLOSED_LADDER.add };
  assert(sleeperAppUrl({ target: 'add', leagueId: L, playerId: P }, full) === `sleeper://players/${P}`,
    'S7 full add ladder: the deepest supported rung wins');
  assert(sleeperAppUrl({ target: 'add', leagueId: 'espn_123', playerId: P }, { ...shipped, add: ['player', 'league', 'bare'] }) === 'sleeper://',
    "S7 player/league rungs need a numeric league ('espn_123' → floor)");
  const every = [];
  for (const target of Object.keys(CLOSED_LADDER)) {
    for (const i of inputs) {
      every.push(sleeperAppUrl({ target, ...i }), sleeperAppUrl({ target, ...i }, { add: CLOSED_LADDER.add, trade: CLOSED_LADDER.trade, league: CLOSED_LADDER.league }));
    }
  }
  assert(every.every((u) => u.startsWith('sleeper://')), 'S7 sleeperAppUrl never returns https', every.find((u) => !u.startsWith('sleeper://')));

  // S13 trade target
  const tradesTab = { ...shipped, trade: ['trades_tab', 'bare'] };
  assert(sleeperAppUrl({ target: 'trade', leagueId: L }, tradesTab) === `sleeper://leagues/${L}/trades`,
    'S13 trades_tab: numeric league → the Trades tab');
  assert(sleeperAppUrl({ target: 'trade' }, tradesTab) === 'sleeper://', 'S13 trades_tab: no league → the floor');
  assert(sleeperAppUrl({ target: 'trade', leagueId: 'mfl_9' }, tradesTab) === 'sleeper://',
    'S13 trades_tab: non-numeric league → the floor');
  const tradeOnAddLadder = { ...shipped, trade: ['players_tab', 'player', 'add', 'bare'] };
  const t = sleeperAppUrl({ target: 'trade', leagueId: L, playerId: P }, tradeOnAddLadder);
  assert(t === 'sleeper://' && !/\/players/.test(t), "S13 'trade' never resolves to an add-ladder path", t);
  assert(sleeperAppUrl({ target: 'add', leagueId: L, playerId: P }, { ...shipped, add: ['trades_tab', 'bare'] }) === 'sleeper://',
    "S13 'add' never resolves to a trade-ladder path");
}

(async () => {
  // S3 scheme opens
  {
    const e = env(() => 'resolve');
    const out = await e.openInSleeperApp({ target: 'trade', leagueId: '1048293', surface: 'send_button' });
    assert(out === 'app', 'S3 scheme opens → app', `got ${out}`);
    assert(e.opens().length === 1 && e.opens()[0].startsWith('sleeper://'), 'S3 exactly one openURL, a sleeper:// URL', JSON.stringify(e.opens()));
    assert(e.alerts.length === 0, 'S3 no alert');
    assert(!e.log.some((x) => x[0] === 'canOpen'), 'S5 S3 run never touched canOpenURL');
  }

  // S4 not installed → D2
  {
    const e = env((u) => (u.startsWith('sleeper:') ? 'reject' : 'resolve'));
    const out = await e.openInSleeperApp({ target: 'add', leagueId: '1048293', playerId: '4046' });
    assert(out === 'not_installed', 'S4 scheme rejects → not_installed', `got ${out}`);
    assert(!e.opens().some((u) => /sleeper\.com/.test(u)), 'S4 never falls back to a sleeper.com https link', JSON.stringify(e.opens()));
    const a = e.alerts[0];
    const get = a && (a.buttons || []).find((b) => b.text === 'Get Sleeper');
    assert(e.alerts.length === 1 && !!get, 'S4 the D2 alert shows, with Get Sleeper', JSON.stringify(e.alerts.map((x) => x.title)));
    if (get) get.onPress();
    await flush();
    assert(e.opens()[1] === APP_STORE_SLEEPER, `S4 Get Sleeper opens ${APP_STORE_SLEEPER}`, JSON.stringify(e.opens()));
    assert(!e.log.some((x) => x[0] === 'canOpen'), 'S5 S4 run never touched canOpenURL');
  }

  // S6 copy before open
  {
    const e = env(() => 'resolve');
    await e.openInSleeperApp({ target: 'trade', clipboardText: 'Trade proposal — League' });
    assert(
      e.log[0] && e.log[0][0] === 'copy' && e.log[0][1] === 'Trade proposal — League' &&
        e.log[1] && e.log[1][0] === 'open',
      'S6 copyText runs before openURL',
      JSON.stringify(e.log),
    );
  }

  if (failures > 0) {
    console.error(`\n${failures} check(s) failed.`);
    process.exit(1);
  }
  console.log('\nAll Sleeper hand-off checks passed.');
})().catch((err) => {
  console.error('FAIL  guard crashed:', err);
  process.exit(1);
});
