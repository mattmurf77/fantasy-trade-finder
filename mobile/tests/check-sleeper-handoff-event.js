#!/usr/bin/env node
// `sleeper_handoff_resolved` (#351 / #379): analytics-lead's grant, G1–G7
// (2026-10-20, widened @ 8b63ef10). Addendum:
// docs/business/analytics/2026-10-28-sleeper-handoff-events.md.
//
// WHY THIS EXISTS. The event is INTENT and, on the Free Agents claim sheet,
// the only record of the tap. Its props are a closed contract: an extra key
// is stripped by ingest behind a 200, a `null` has_drop is ambiguous (G2),
// and an event fired after the D2 alert, or after a further await, is lost
// whenever iOS suspends FTF for the app switch (G3). This guard executes the
// real utils/sleeperHandoff.ts + utils/openExternal.ts under node, with
// `Linking.openURL` stubbed to resolve or reject and `track` stubbed to
// record, and pins:
//   E1  exact props per case: add with / without a drop, add with no
//       hasDrop passed, trade on send_button and trade_queue, add on
//       send_button. `has_drop` is an ABSENT key, never null, on every
//       target=trade row and on send_button (G2)                       [executed]
//   E2  outcome 'app' when openURL resolves, 'not_installed' when it
//       rejects (G4), matching openInSleeperApp's return               [executed]
//   E3  fired from the settle seam: after the open, BEFORE the D2 alert,
//       and before openInSleeperApp settles (G3)                       [executed]
//   E4  exactly one event per hand-off; a re-tap while the open is in
//       flight adds no open and no event                                [executed]
//   E5  surface 'unspecified' (or none) emits nothing; the open and the
//       D2 alert still happen                                           [executed]
//   E6  ESPN and MFL opens emit nothing; openExternal.ts has no track    [executed + AST]
//   E7  target 'league' (outside the granted `target` set) emits nothing [executed]
//   E8  no player id, name or league id; keys ⊆ the granted row; every
//       value is in its granted closed set; has_drop is boolean (G5)   [executed]
//   E9  `rung` is the rung actually opened, not a constant             [executed]
//   E10 one emitter in src/: the only 'sleeper_handoff_resolved' literal
//       is track()'s first argument in sleeperHandoff.ts; no
//       'external_link_opened' anywhere (not granted)                   [AST]
//   E11 the emitter and the onSchemeSettled callback are not async and
//       contain no await (G3)                                          [AST]
//
// HONEST LABEL (G-035): E1–E9 execute the real modules with stubbed
// Linking / Alert / clipboard / track. They prove what the client SENDS,
// not that ingest keeps it: backend/tests/test_analytics_taxonomy_sleeper_
// handoff.py covers the allowlist, the exact prop row and the INTENT split.
//
// Run: node tests/check-sleeper-handoff-event.js

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
const ESPN_BUTTON = 'src/components/SendInEspnButton.tsx';
const MFL_BUTTON = 'src/components/SendInMflButton.tsx';
const EVENT = 'sleeper_handoff_resolved';

// The grant, copied here on purpose: widening a set in code alone fails.
const GRANTED = {
  surface: ['free_agents', 'usage_trends', 'send_button', 'trade_queue'],
  target: ['add', 'trade'],
  rung: ['add', 'player', 'players_tab', 'league', 'bare', 'trade', 'trades_tab'],
  outcome: ['app', 'not_installed'],
};
const ROW = ['surface', 'target', 'rung', 'outcome', 'has_drop'];

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

// Fresh modules per scenario (the helper's in-flight lock is module state).
// `behave(url)` → 'resolve' | 'reject' | a Promise (settled by the test).
// One ordered log for opens, copies, events and alerts.
function env(behave) {
  const log = [];
  const Linking = {
    openURL: (url) => {
      log.push(['open', url]);
      const b = behave(url);
      if (b && typeof b.then === 'function') return b;
      return b === 'resolve'
        ? Promise.resolve(true)
        : Promise.reject(new Error(`Unable to open URL: ${url}`));
    },
    canOpenURL: () => {
      throw new Error('canOpenURL must never be called (#351 F8)');
    },
  };
  const Alert = { alert: (title) => log.push(['alert', title]) };
  const helper = { exports: {} };
  new Function('module', 'exports', 'require', helperJs)(helper, helper.exports, (name) => {
    if (name === 'react-native') return { Linking, Alert };
    if (name === './clipboard') return { copyText: (s) => log.push(['copy', s]) };
    throw new Error(`openExternal.ts gained an unexpected runtime import ("${name}")`);
  });
  const handoff = { exports: {} };
  new Function('module', 'exports', 'require', handoffJs)(handoff, handoff.exports, (name) => {
    if (name === './openExternal') return helper.exports;
    if (name === '../api/events') {
      return { track: (type, props, screen) => log.push(['track', type, props, screen]) };
    }
    throw new Error(`sleeperHandoff.ts gained an unexpected runtime import ("${name}")`);
  });
  return {
    ...handoff.exports,
    openPlatform: helper.exports.openPlatform,
    log,
    events: () => log.filter((e) => e[0] === 'track'),
    opens: () => log.filter((e) => e[0] === 'open').map((e) => e[1]),
    alerts: () => log.filter((e) => e[0] === 'alert'),
  };
}
const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const canon = (o) => JSON.stringify(Object.keys(o).sort().map((k) => [k, o[k]]));
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const L = '1048293';
const P = '4046';
const NAME = 'Bijan Robinson';
const resolveAll = () => 'resolve';
const rejectSleeper = (u) => (u.startsWith('sleeper:') ? 'reject' : 'resolve');
const all = []; // every recorded props object, for E8

// ═══════════════════════════════════════════════════════════════════════
// E10 / E11 / E6 (text half) — AST
// ═══════════════════════════════════════════════════════════════════════
{
  const files = [];
  (function list(dir) {
    for (const d of fs.readdirSync(path.join(ROOT, dir), { withFileTypes: true })) {
      const rel = `${dir}/${d.name}`;
      if (d.isDirectory()) list(rel);
      else if (/\.tsx?$/.test(d.name)) files.push(rel);
    }
  })('src');
  const hits = [];
  const banned = [];
  for (const rel of files) {
    const sf = parse(rel);
    walk(sf, (n) => {
      if (!ts.isStringLiteral(n) && !ts.isNoSubstitutionTemplateLiteral(n)) return;
      if (n.text === EVENT) {
        const call = n.parent;
        const asTrackArg0 =
          ts.isCallExpression(call) && call.arguments[0] === n &&
          ts.isIdentifier(call.expression) && call.expression.text === 'track';
        hits.push({ rel, asTrackArg0 });
      }
      if (n.text === 'external_link_opened') banned.push(rel);
    });
  }
  assert(
    hits.length === 1 && hits[0].rel === HANDOFF && hits[0].asTrackArg0,
    `E10 the only '${EVENT}' literal in src/ is track()'s first argument in sleeperHandoff.ts`,
    JSON.stringify(hits),
  );
  assert(banned.length === 0, "E10 no 'external_link_opened' literal in src/ (not granted)", banned.join(', '));

  // E11 — the track call's enclosing function, and the callback, are sync.
  const sf = parse(HANDOFF);
  const isFn = (n) =>
    ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n) || ts.isArrowFunction(n) || ts.isMethodDeclaration(n);
  const isAsync = (fn) => (ts.getCombinedModifierFlags(fn) & ts.ModifierFlags.Async) !== 0;
  const hasAwait = (fn) => {
    let found = false;
    walk(fn.body, (n) => { if (ts.isAwaitExpression(n)) found = true; });
    return found;
  };
  let emitterFn = null;
  let callback = null;
  walk(sf, (n) => {
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === 'track') {
      let p = n.parent;
      while (p && !isFn(p)) p = p.parent;
      emitterFn = p;
    }
    if (ts.isPropertyAssignment(n) && n.name.getText(sf) === 'onSchemeSettled') callback = n.initializer;
  });
  assert(
    !!emitterFn && !isAsync(emitterFn) && !hasAwait(emitterFn),
    'E11 the function that calls track() is not async and has no await',
    emitterFn ? emitterFn.getText(sf).slice(0, 120) : 'no track() call found',
  );
  assert(
    !!callback && isFn(callback) && !isAsync(callback) && !hasAwait(callback) &&
      /\btrackHandoff\(/.test(callback.getText(sf)),
    'E11 openInSleeperApp passes a sync onSchemeSettled that calls trackHandoff',
    callback ? callback.getText(sf) : 'no onSchemeSettled property',
  );

  // E6 (text half) — the generic helper and the ESPN/MFL buttons emit nothing.
  let helperTrack = 0;
  walk(parse(HELPER), (n) => {
    if (ts.isImportDeclaration(n) && /api\/events/.test(n.moduleSpecifier.text)) helperTrack += 1;
    if (ts.isIdentifier(n) && n.text === 'track') helperTrack += 1;
  });
  assert(helperTrack === 0, 'E6 openExternal.ts neither imports api/events nor calls track', `${helperTrack} found`);
  for (const rel of [ESPN_BUTTON, MFL_BUTTON]) {
    let refs = 0;
    walk(parse(rel), (n) => {
      if (ts.isIdentifier(n) && (n.text === 'onSchemeSettled' || n.text === 'openInSleeperApp')) refs += 1;
    });
    assert(refs === 0, `E6 ${path.basename(rel)} passes no onSchemeSettled and never calls openInSleeperApp`, `${refs} found`);
  }
}

(async () => {
  // ═════════════════════════════════════════════════════════════════════
  // E1 / E2 — exact props per case, outcome by settle
  // ═════════════════════════════════════════════════════════════════════
  const cases = [
    {
      name: 'add, free_agents, a drop picked, Sleeper installed',
      input: { target: 'add', leagueId: L, playerId: P, clipboardText: NAME, surface: 'free_agents', hasDrop: true },
      behave: resolveAll,
      want: { surface: 'free_agents', target: 'add', rung: 'bare', outcome: 'app', has_drop: true },
    },
    {
      name: 'add, free_agents, no drop, not installed',
      input: { target: 'add', leagueId: L, playerId: P, clipboardText: NAME, surface: 'free_agents', hasDrop: false },
      behave: rejectSleeper,
      want: { surface: 'free_agents', target: 'add', rung: 'bare', outcome: 'not_installed', has_drop: false },
    },
    {
      name: 'add, usage_trends, hasDrop not passed',
      input: { target: 'add', leagueId: L, playerId: P, surface: 'usage_trends' },
      behave: resolveAll,
      want: { surface: 'usage_trends', target: 'add', rung: 'bare', outcome: 'app' },
    },
    {
      name: 'trade, send_button, installed',
      input: { target: 'trade', leagueId: L, surface: 'send_button' },
      behave: resolveAll,
      want: { surface: 'send_button', target: 'trade', rung: 'bare', outcome: 'app' },
    },
    {
      name: 'trade, send_button, hasDrop wrongly passed, not installed',
      input: { target: 'trade', leagueId: L, surface: 'send_button', hasDrop: true },
      behave: rejectSleeper,
      want: { surface: 'send_button', target: 'trade', rung: 'bare', outcome: 'not_installed' },
    },
    {
      name: 'trade, trade_queue (Send All), hasDrop wrongly passed',
      input: { target: 'trade', leagueId: L, surface: 'trade_queue', hasDrop: false },
      behave: resolveAll,
      want: { surface: 'trade_queue', target: 'trade', rung: 'bare', outcome: 'app' },
    },
    {
      name: 'add, send_button, hasDrop passed',
      input: { target: 'add', leagueId: L, playerId: P, surface: 'send_button', hasDrop: true },
      behave: resolveAll,
      want: { surface: 'send_button', target: 'add', rung: 'bare', outcome: 'app' },
    },
  ];
  for (const c of cases) {
    const e = env(c.behave);
    const out = await e.openInSleeperApp(c.input);
    const ev = e.events();
    assert(ev.length === 1 && ev[0][1] === EVENT, `E1 ${c.name}: exactly one ${EVENT}`, `${ev.length} events`);
    if (ev.length !== 1) continue;
    const props = ev[0][2];
    all.push(props);
    assert(canon(props) === canon(c.want), `E1 ${c.name}: props are exactly ${canon(c.want)}`, canon(props));
    if (!has(c.want, 'has_drop')) {
      assert(!has(props, 'has_drop'), `E1 ${c.name}: has_drop is an absent key (not null)`, canon(props));
    }
    assert(props.outcome === out, `E2 ${c.name}: outcome matches openInSleeperApp's return (${out})`, props.outcome);
  }

  // ═════════════════════════════════════════════════════════════════════
  // E3 — fired from the settle seam, before the D2 alert (G3)
  // ═════════════════════════════════════════════════════════════════════
  {
    const e = env(rejectSleeper);
    await e.openInSleeperApp({ target: 'add', leagueId: L, playerId: P, surface: 'free_agents', hasDrop: false });
    const kinds = e.log.map((x) => x[0]);
    assert(
      JSON.stringify(kinds) === JSON.stringify(['open', 'track', 'alert']),
      'E3 not installed: open → event → D2 alert, nothing in between',
      JSON.stringify(kinds),
    );
  }
  {
    const d = deferred();
    const e = env(() => d.promise);
    const run = e.openInSleeperApp({ target: 'trade', leagueId: L, surface: 'send_button' })
      .then(() => e.log.push(['settled']));
    await new Promise((r) => setImmediate(r));
    assert(e.events().length === 0, 'E3 nothing fires before openURL settles', `${e.events().length} events`);
    d.resolve(true);
    await run;
    const kinds = e.log.map((x) => x[0]);
    assert(
      JSON.stringify(kinds) === JSON.stringify(['open', 'track', 'settled']),
      'E3 installed: the event fires on settle, before openInSleeperApp resolves',
      JSON.stringify(kinds),
    );
  }

  // ═════════════════════════════════════════════════════════════════════
  // E4 — one per hand-off; a re-tap in flight adds nothing
  // ═════════════════════════════════════════════════════════════════════
  {
    const d = deferred();
    const e = env(() => d.promise);
    const input = { target: 'trade', leagueId: L, surface: 'trade_queue' };
    const a = e.openInSleeperApp(input);
    const b = e.openInSleeperApp(input);
    d.resolve(true);
    await Promise.all([a, b]);
    assert(
      e.opens().length === 1 && e.events().length === 1,
      'E4 a re-tap while the open is in flight: one open, one event',
      `${e.opens().length} opens, ${e.events().length} events`,
    );
  }

  // ═════════════════════════════════════════════════════════════════════
  // E5 — 'unspecified' emits nothing; the hand-off itself is unchanged
  // ═════════════════════════════════════════════════════════════════════
  for (const [label, extra] of [['no surface', {}], ["surface 'unspecified'", { surface: 'unspecified' }]]) {
    for (const [how, behave] of [['installed', resolveAll], ['not installed', rejectSleeper]]) {
      const e = env(behave);
      const out = await e.openInSleeperApp({ target: 'add', leagueId: L, playerId: P, hasDrop: true, ...extra });
      assert(e.events().length === 0, `E5 ${label}, ${how}: no event`, `${e.events().length} events`);
      assert(
        e.opens().length === 1 && e.alerts().length === (how === 'installed' ? 0 : 1) &&
          out === (how === 'installed' ? 'app' : 'not_installed'),
        `E5 ${label}, ${how}: the open and the D2 alert are unchanged`,
        JSON.stringify(e.log.map((x) => x[0])),
      );
    }
  }
  {
    const e = env(resolveAll);
    await e.openPlatform({ platform: 'sleeper', schemeUrl: 'sleeper://', surface: 'unspecified', appMissing: 'alert' });
    assert(e.events().length === 0, "E5 openPlatform, Sleeper, surface 'unspecified': no event");
  }

  // ═════════════════════════════════════════════════════════════════════
  // E6 — ESPN and MFL emit nothing
  // ═════════════════════════════════════════════════════════════════════
  for (const [platform, httpsUrl] of [['espn', 'https://fantasy.espn.com'], ['mfl', 'https://www.myfantasyleague.com']]) {
    for (const [how, behave] of [['resolves', resolveAll], ['rejects', () => 'reject']]) {
      const e = env(behave);
      await e.openPlatform({ platform, httpsUrl, surface: 'send_button', appMissing: 'https' });
      assert(e.events().length === 0, `E6 ${platform.toUpperCase()}, openURL ${how}: no event`, `${e.events().length} events`);
    }
  }

  // ═════════════════════════════════════════════════════════════════════
  // E7 — target 'league' is outside the granted `target` set
  // ═════════════════════════════════════════════════════════════════════
  {
    const e = env(resolveAll);
    const out = await e.openInSleeperApp({ target: 'league', leagueId: L, surface: 'free_agents' });
    assert(e.events().length === 0 && out === 'app', "E7 target 'league': no event, the open still happens",
      `${e.events().length} events, ${out}`);
  }

  // ═════════════════════════════════════════════════════════════════════
  // E9 — `rung` is the rung opened (a test-local proven set)
  // ═════════════════════════════════════════════════════════════════════
  {
    const runs = [
      [{ target: 'add', leagueId: L, playerId: P, surface: 'free_agents', hasDrop: false }, { add: ['players_tab', 'bare'] }, 'players_tab', `sleeper://leagues/${L}/players`],
      [{ target: 'add', playerId: P, surface: 'free_agents', hasDrop: false }, { add: ['players_tab', 'bare'] }, 'bare', 'sleeper://'],
      [{ target: 'trade', leagueId: L, surface: 'trade_queue' }, { trade: ['trades_tab', 'bare'] }, 'trades_tab', `sleeper://leagues/${L}/trades`],
      [{ target: 'trade', leagueId: 'mfl_9', surface: 'send_button' }, { trade: ['trades_tab', 'bare'] }, 'bare', 'sleeper://'],
    ];
    for (const [input, proven, rung, url] of runs) {
      const e = env(resolveAll);
      Object.assign(e.SLEEPER_PROVEN_RUNGS, proven);
      await e.openInSleeperApp(input);
      const ev = e.events();
      if (ev.length) all.push(ev[0][2]);
      assert(
        ev.length === 1 && ev[0][2].rung === rung && e.opens()[0] === url,
        `E9 ${input.target} with ${JSON.stringify(proven)}, league ${input.leagueId || 'none'}: rung '${rung}', opened ${url}`,
        `${ev.length ? ev[0][2].rung : 'no event'} / ${e.opens()[0]}`,
      );
    }
  }

  // ═════════════════════════════════════════════════════════════════════
  // E8 — closed sets, no identity (G5), has_drop boolean
  // ═════════════════════════════════════════════════════════════════════
  {
    const badKeys = all.filter((p) => Object.keys(p).some((k) => !ROW.includes(k)));
    assert(all.length > 0 && badKeys.length === 0, `E8 every event's keys ⊆ {${ROW.join(', ')}}`, JSON.stringify(badKeys));
    const missing = all.filter((p) => ['surface', 'target', 'rung', 'outcome'].some((k) => !has(p, k)));
    assert(missing.length === 0, 'E8 surface, target, rung and outcome are on every event', JSON.stringify(missing));
    const outside = [];
    for (const p of all) {
      for (const [k, vals] of Object.entries(GRANTED)) if (has(p, k) && !vals.includes(p[k])) outside.push(`${k}=${p[k]}`);
    }
    assert(outside.length === 0, 'E8 every value is in its granted closed set', outside.join(', '));
    const badDrop = all.filter((p) => has(p, 'has_drop') && typeof p.has_drop !== 'boolean');
    assert(badDrop.length === 0, 'E8 has_drop, when present, is a boolean (never null)', JSON.stringify(badDrop));
    const leaked = all.filter((p) => {
      const s = JSON.stringify(p);
      return s.includes(L) || s.includes(P) || s.includes('Bijan');
    });
    assert(leaked.length === 0, 'E8 no league id, player id or player name in any event (G5)', JSON.stringify(leaked));
  }

  if (failures > 0) {
    console.error(`\n${failures} check(s) failed.`);
    process.exit(1);
  }
  console.log(`\nAll ${EVENT} checks passed.`);
})().catch((err) => {
  console.error('FAIL  guard crashed:', err);
  process.exit(1);
});
