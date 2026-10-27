#!/usr/bin/env node
// External links: one opener, never silent (eng-external-links §4; operator
// D2, 2026-10-20).
//
// WHY THIS EXISTS. Before utils/openExternal.ts, mobile opened outside links
// in three styles and none of them reached the user: a silent
// `.catch(() => {})` (Send in Sleeper / ESPN / MFL, the claim sheet, Help),
// no catch at all (Draft Room, Settings and legal links), and
// `canOpenURL` + a swallowed catch (the trade queue). `canOpenURL` also
// REJECTS for any custom scheme missing from LSApplicationQueriesSchemes
// (#351 F8), so a `sleeper://` hand-off built that way is a silent no-op.
//
// Pinned:
//   (a) Every `Linking.openURL` in src/ is inside utils/openExternal.ts,
//       except the LEGACY allowlist below: other leads' call sites, not yet
//       migrated, each tagged with its owner. The allowlist is a RATCHET.
//       Each entry must match exactly one call site (same file, same call,
//       same argument text). An entry that matches none FAILS, so a
//       migration has to delete its entry. A second call can't hide behind
//       an existing entry.
//   (b) No `Linking.canOpenURL` anywhere outside the allowlist, and never in
//       openExternal.ts.
//   (c) openPlatform, transpiled and EXECUTED with stubbed Linking / Alert /
//       clipboard / timers:
//         C1 scheme opens                      → 'app', no alert
//         C2 scheme rejects, https opens       → 'web'
//         C3 scheme rejects, appMissing 'alert' → 'fallback', the D2 alert
//            with a Get Sleeper button that opens the App Store id; https
//            is never tried
//         C4 nothing opens                     → 'failed' + an alert
//         C5 re-tap while in flight            → no second open
//         C6 the lock lets go after LOCK_MS even if openURL never settles
//         C7 clipboard is written before any open
//       and canOpenURL (a stub that throws) is never touched.
//   (d) SLEEPER_PROVEN_RUNGS' device-results rule is S10 in
//       check-sleeper-handoff.js. It lives there once, not in both guards.
//
// HONEST LABEL (G-035): (a)/(b) prove where the calls are, not behavior.
// (c) executes the real module.
//
// Run: node tests/check-external-links.js

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
const HELPER = 'src/utils/openExternal.ts';
const APP_STORE_SLEEPER = 'https://apps.apple.com/app/id987367543';

// ── LEGACY allowlist. Delete an entry when its owner migrates the call to
//    utils/openExternal (the ratchet below forces it). Never add one for
//    new code. Owners per eng-external-links §4 "Phase-2 call-site
//    switches"; rows 21–25 have no owner yet ("app-shell, unassigned").
const LEGACY = [
  { owner: 'trades-eng', file: 'src/state/useTradeQueue.ts', call: 'canOpenURL', arg: 'url' },
  { owner: 'trades-eng', file: 'src/state/useTradeQueue.ts', call: 'openURL', arg: 'url' },
  { owner: 'draft-eng', file: 'src/screens/DraftRoomScreen.tsx', call: 'openURL',
    arg: 'board.deep_link as string' },
  { owner: 'app-shell, unassigned', file: 'src/components/HelpSheet.tsx', call: 'openURL',
    arg: 'readMoreUrl' },
  { owner: 'app-shell, unassigned', file: 'src/screens/PaywallScreen.tsx', call: 'openURL',
    arg: '`${getBaseUrl()}${path}`' },
  { owner: 'app-shell, unassigned', file: 'src/screens/SettingsScreen.tsx', call: 'openURL',
    arg: '`${WEB_ORIGIN}/faq.html`' },
  { owner: 'app-shell, unassigned', file: 'src/screens/SettingsScreen.tsx', call: 'openURL',
    arg: '`${WEB_ORIGIN}/privacy`' },
  { owner: 'app-shell, unassigned', file: 'src/screens/SettingsScreen.tsx', call: 'openURL',
    arg: '`${WEB_ORIGIN}/terms`' },
  { owner: 'app-shell, unassigned', file: 'src/screens/settings/sections/AboutSection.tsx',
    call: 'openURL', arg: '`${WEB_ORIGIN}/faq.html`' },
  { owner: 'app-shell, unassigned', file: 'src/screens/settings/sections/AboutSection.tsx',
    call: 'openURL', arg: '`${WEB_ORIGIN}/privacy`' },
  { owner: 'app-shell, unassigned', file: 'src/screens/settings/sections/AboutSection.tsx',
    call: 'openURL', arg: '`${WEB_ORIGIN}/terms`' },
  { owner: 'app-shell, unassigned', file: 'src/screens/SignInScreen.tsx', call: 'openURL',
    arg: "'https://fantasy-trade-finder.onrender.com/terms'" },
  { owner: 'app-shell, unassigned', file: 'src/screens/SignInScreen.tsx', call: 'openURL',
    arg: "'https://fantasy-trade-finder.onrender.com/privacy'" },
  { owner: 'app-shell, unassigned', file: 'src/screens/EspnConnectScreen.tsx', call: 'openURL',
    arg: "'https://fantasy-trade-finder.onrender.com/privacy'" },
  { owner: 'app-shell, unassigned', file: 'src/screens/SleeperConnectScreen.tsx', call: 'openURL',
    arg: "'https://fantasy-trade-finder.onrender.com/privacy'" },
];

let failures = 0;
function assert(cond, name, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════
// (a)/(b) Where Linking.openURL / canOpenURL may appear
// ═══════════════════════════════════════════════════════════════════════

function listSources(dir) {
  const out = [];
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) out.push(...listSources(p));
    else if (/\.(ts|tsx)$/.test(ent.name) && !ent.name.endsWith('.d.ts')) out.push(p);
  }
  return out;
}

// AST, not grep: comments that mention `Linking.openURL` (several do) must
// not count, and a call split across lines must.
const sites = [];
for (const abs of listSources(path.join(ROOT, 'src'))) {
  const rel = path.relative(ROOT, abs).split(path.sep).join('/');
  const text = fs.readFileSync(abs, 'utf8');
  const sf = ts.createSourceFile(abs, text, ts.ScriptTarget.Latest, true,
    abs.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const visit = (node) => {
    if (
      ts.isPropertyAccessExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === 'Linking' &&
      (node.name.text === 'openURL' || node.name.text === 'canOpenURL')
    ) {
      const parent = node.parent;
      const called = ts.isCallExpression(parent) && parent.expression === node;
      sites.push({
        file: rel,
        call: node.name.text,
        arg: called && parent.arguments[0] ? parent.arguments[0].getText(sf) : '<not a direct call>',
        line: sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1,
      });
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
}

const where = (s) => `${s.file}:${s.line} Linking.${s.call}(${s.arg})`;

const helperSites = sites.filter((s) => s.file === HELPER);
assert(
  helperSites.some((s) => s.call === 'openURL'),
  'a0 openExternal.ts is where Linking.openURL lives',
  'no Linking.openURL found in the helper',
);
assert(
  !helperSites.some((s) => s.call === 'canOpenURL'),
  'b0 openExternal.ts never calls Linking.canOpenURL (#351 F8)',
  helperSites.filter((s) => s.call === 'canOpenURL').map(where).join('; '),
);

const unlisted = [];
const hits = LEGACY.map(() => 0);
for (const s of sites) {
  if (s.file === HELPER) continue;
  const i = LEGACY.findIndex((e) => e.file === s.file && e.call === s.call && e.arg === s.arg);
  if (i === -1) unlisted.push(s);
  else hits[i] += 1;
}
const unlistedOpen = unlisted.filter((s) => s.call === 'openURL');
const unlistedCan = unlisted.filter((s) => s.call === 'canOpenURL');
assert(
  unlistedOpen.length === 0,
  'a1 every other Linking.openURL is a LEGACY entry (new code uses utils/openExternal)',
  unlistedOpen.map(where).join('; '),
);
assert(
  unlistedCan.length === 0,
  'b1 no Linking.canOpenURL outside the LEGACY allowlist',
  unlistedCan.map(where).join('; '),
);
LEGACY.forEach((e, i) => {
  assert(
    hits[i] === 1,
    `a2 ratchet: LEGACY ${e.file} Linking.${e.call}(${e.arg}) [${e.owner}] matches exactly one call`,
    hits[i] === 0
      ? 'it matches none. If the call was migrated to utils/openExternal, delete this entry'
      : `it matches ${hits[i]} calls; a second call can't share an entry`,
  );
});

// The three platforms-eng buttons are migrated: no Linking import left.
for (const f of ['SendInSleeperButton', 'SendInEspnButton', 'SendInMflButton']) {
  const src = fs.readFileSync(path.join(ROOT, 'src/components', `${f}.tsx`), 'utf8');
  assert(
    !/import\s*\{[^}]*\bLinking\b[^}]*\}\s*from\s*'react-native'/.test(src),
    `a3 ${f} no longer imports Linking (it opens through utils/openExternal)`,
  );
}

// ═══════════════════════════════════════════════════════════════════════
// (c) openPlatform, executed
// ═══════════════════════════════════════════════════════════════════════

function transpile(rel) {
  const source = fs.readFileSync(path.join(ROOT, rel), 'utf8');
  return ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
}

const helperJs = transpile(HELPER);

// A fresh module (and a fresh in-flight lock) per scenario. `behave(url)`
// returns 'resolve', 'reject', or a promise the scenario settles itself.
function env(behave) {
  const log = [];
  const alerts = [];
  const timers = [];
  const Linking = {
    openURL: (url) => {
      log.push(['open', url]);
      const b = behave(url);
      if (b === 'resolve') return Promise.resolve(true);
      if (b === 'reject') return Promise.reject(new Error(`Unable to open URL: ${url}`));
      return b;
    },
    canOpenURL: () => {
      log.push(['canOpen']);
      throw new Error('canOpenURL must never be called (#351 F8)');
    },
  };
  const Alert = { alert: (title, body, buttons) => alerts.push({ title, body, buttons }) };
  const fakeSetTimeout = (fn, ms) => {
    timers.push({ fn, ms, live: true });
    return timers.length;
  };
  const fakeClearTimeout = (id) => {
    if (timers[id - 1]) timers[id - 1].live = false;
  };
  const m = { exports: {} };
  new Function('module', 'exports', 'require', 'setTimeout', 'clearTimeout', helperJs)(
    m,
    m.exports,
    (name) => {
      if (name === 'react-native') return { Linking, Alert };
      if (name === './clipboard') return { copyText: (s) => log.push(['copy', s]) };
      throw new Error(
        `openExternal.ts gained an unexpected runtime import ("${name}") — ` +
          'extend the shim deliberately.',
      );
    },
    fakeSetTimeout,
    fakeClearTimeout,
  );
  return {
    openPlatform: m.exports.openPlatform,
    LOCK_MS: m.exports.LOCK_MS,
    log,
    alerts,
    timers,
    opens: () => log.filter((e) => e[0] === 'open').map((e) => e[1]),
    fireTimers: () => {
      for (const t of timers) if (t.live) { t.live = false; t.fn(); }
    },
  };
}

const flush = () => new Promise((r) => setImmediate(r));
function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}
const press = (alert, text) => {
  const b = (alert.buttons || []).find((x) => x.text === text);
  if (b && b.onPress) b.onPress();
  return !!b;
};

const SLEEPER = { platform: 'sleeper', schemeUrl: 'sleeper://', surface: 'send_button', appMissing: 'alert' };
const ESPN = { platform: 'espn', httpsUrl: 'https://fantasy.espn.com', surface: 'send_button', appMissing: 'https' };
let canOpenTouched = 0;

(async () => {
  // C1 scheme opens
  {
    const e = env(() => 'resolve');
    const out = await e.openPlatform(SLEEPER);
    assert(out === 'app', 'C1 scheme opens → app', `got ${out}`);
    assert(e.opens().length === 1 && e.opens()[0] === 'sleeper://', 'C1 one open, the scheme', JSON.stringify(e.opens()));
    assert(e.alerts.length === 0, 'C1 no alert');
    canOpenTouched += e.log.filter((x) => x[0] === 'canOpen').length;
  }

  // C2 scheme rejects, https fallback opens
  {
    const e = env((u) => (u.startsWith('sleeper:') ? 'reject' : 'resolve'));
    const out = await e.openPlatform({ ...SLEEPER, httpsUrl: 'https://sleeper.com', appMissing: 'https' });
    assert(out === 'web', 'C2 scheme rejects + https opens → web', `got ${out}`);
    assert(
      JSON.stringify(e.opens()) === JSON.stringify(['sleeper://', 'https://sleeper.com']),
      'C2 scheme first, then https',
      JSON.stringify(e.opens()),
    );
    assert(e.alerts.length === 0, 'C2 no alert');
    canOpenTouched += e.log.filter((x) => x[0] === 'canOpen').length;
  }

  // C3 scheme rejects, appMissing 'alert' → D2
  {
    const e = env((u) => (u.startsWith('sleeper:') ? 'reject' : 'resolve'));
    const out = await e.openPlatform({ ...SLEEPER, httpsUrl: 'https://sleeper.com' });
    assert(out === 'fallback', 'C3 scheme rejects + appMissing alert → fallback', `got ${out}`);
    assert(
      JSON.stringify(e.opens()) === JSON.stringify(['sleeper://']),
      'C3 https is never tried when D2 is the fallback',
      JSON.stringify(e.opens()),
    );
    const a = e.alerts[0];
    assert(e.alerts.length === 1 && !!a, 'C3 exactly one alert');
    const names = a ? (a.buttons || []).map((b) => b.text) : [];
    assert(
      names.includes('Get Sleeper') && (a.buttons || []).some((b) => b.style === 'cancel'),
      'C3 the alert offers Get Sleeper and a cancel',
      JSON.stringify(names),
    );
    press(a, 'Get Sleeper');
    await flush();
    assert(
      e.opens()[1] === APP_STORE_SLEEPER,
      `C3 Get Sleeper opens ${APP_STORE_SLEEPER}`,
      JSON.stringify(e.opens()),
    );
    assert(e.alerts.length === 1, 'C3 a successful App Store open shows nothing more');
    canOpenTouched += e.log.filter((x) => x[0] === 'canOpen').length;
  }

  // C3b the App Store open itself fails → still an alert
  {
    const e = env(() => 'reject');
    await e.openPlatform(SLEEPER);
    press(e.alerts[0], 'Get Sleeper');
    await flush();
    assert(e.alerts.length === 2, 'C3b Get Sleeper that fails to open shows the failure alert');
  }

  // C3c Cancel opens nothing
  {
    const e = env(() => 'reject');
    await e.openPlatform(SLEEPER);
    press(e.alerts[0], 'Cancel');
    await flush();
    assert(e.opens().length === 1, 'C3c Cancel opens nothing');
  }

  // C4 nothing opens → failed + alert
  {
    const e = env(() => 'reject');
    const out = await e.openPlatform({ ...SLEEPER, httpsUrl: 'https://sleeper.com', appMissing: 'https' });
    assert(out === 'failed', 'C4 scheme + https both reject → failed', `got ${out}`);
    assert(e.alerts.length === 1, 'C4 never silent: one alert');
  }
  {
    const e = env(() => 'reject');
    const out = await e.openPlatform(ESPN);
    assert(out === 'failed' && e.alerts.length === 1, 'C4b https-only rejects → failed + alert', `got ${out}`);
  }
  {
    const e = env(() => 'resolve');
    const out = await e.openPlatform(ESPN);
    assert(
      out === 'web' && e.opens().length === 1 && e.alerts.length === 0,
      'C4c https-only opens → web, no alert',
      `got ${out}`,
    );
    canOpenTouched += e.log.filter((x) => x[0] === 'canOpen').length;
  }

  // C5 re-tap while in flight is ignored; released once settled
  {
    const d = deferred();
    const e = env(() => d.promise);
    const p1 = e.openPlatform(SLEEPER);
    const p2 = e.openPlatform(SLEEPER);
    const p3 = e.openPlatform(ESPN);
    await flush();
    assert(e.opens().length === 1, 'C5 two re-taps while in flight open nothing more', JSON.stringify(e.opens()));
    assert(p1 === p2 && p1 === p3, 'C5 a re-tap gets the in-flight promise back');
    d.resolve(true);
    const outs = await Promise.all([p1, p2]);
    assert(outs[0] === 'app' && outs[1] === 'app', 'C5 both resolve with the one outcome');
    await flush();
    const e2 = await e.openPlatform(SLEEPER);
    assert(e2 === 'app' && e.opens().length === 2, 'C5 after it settles, the next tap opens again');
  }

  // C6 lock lets go after LOCK_MS even if openURL never settles
  {
    const e = env(() => new Promise(() => {}));
    assert(e.LOCK_MS === 2000, 'C6 LOCK_MS is 2 s', `got ${e.LOCK_MS}`);
    e.openPlatform(SLEEPER);
    e.openPlatform(SLEEPER);
    await flush();
    assert(e.opens().length === 1, 'C6 hung open: the re-tap is ignored');
    assert(e.timers.some((t) => t.live && t.ms === 2000), 'C6 a 2 s release timer is armed');
    e.fireTimers();
    e.openPlatform(SLEEPER);
    await flush();
    assert(e.opens().length === 2, 'C6 after LOCK_MS a tap opens again');
  }

  // C7 clipboard before any open
  {
    const e = env(() => 'resolve');
    await e.openPlatform({ ...SLEEPER, clipboardText: 'Trade proposal' });
    const first = e.log[0];
    assert(
      first && first[0] === 'copy' && first[1] === 'Trade proposal' && e.log[1] && e.log[1][0] === 'open',
      'C7 copyText runs before openURL',
      JSON.stringify(e.log),
    );
  }

  assert(canOpenTouched === 0, 'C8 no executed run touched canOpenURL (its stub throws)');

  if (failures > 0) {
    console.error(`\n${failures} check(s) failed.`);
    process.exit(1);
  }
  console.log('\nAll external-link checks passed.');
})().catch((err) => {
  console.error('FAIL  guard crashed:', err);
  process.exit(1);
});
