#!/usr/bin/env node
// Sleeper hand-off (#351 PRD §7.1): the subset of S1–S16 that is true on
// the build/open-external-helper branch.
//
// WHY THIS EXISTS. FTF handed off to Sleeper with
// `https://sleeper.com/leagues/...` links. sleeper.com's AASA claims no
// league path, so on an iPhone every one went Safari → Branch → Sleeper's
// HOME screen with the league dropped (#351 F1/F3), and a rejection was
// swallowed by `.catch(() => {})`. utils/sleeperHandoff.ts opens the
// `sleeper://` scheme instead, through utils/openExternal.ts, and shows the
// Get Sleeper alert (operator D2, 2026-10-20) when Sleeper isn't installed.
//
// Here (S-ids are the PRD's):
//   S2  SendInSleeperButton imports openInSleeperApp from
//       ../utils/sleeperHandoff and calls it from openInSleeper (target
//       'trade'). The ClaimSheet half belongs to league-eng.
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
//   S1, S2 (ClaimSheet half), S8, S9 → league-eng (ClaimSheet, Free Agents);
//       UsageTrendsScreen's S1 / `leagueName` → rankings-eng
//   S11, S12, S15 → trades-eng (TradesScreen, useTradeQueue)
//   S14 → platforms-eng follow-up: the Send-in-Sleeper steps confirm +
//       clipboard (PRD §4.3), waiting on design-lead / ux-lead copy
//
// HONEST LABEL (G-035): S2 and S16 prove wirings are present, not behavior.
// S3–S7, S10 and S13 execute the real modules.
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
