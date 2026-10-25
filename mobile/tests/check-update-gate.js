#!/usr/bin/env node
// B8 minimum-version gate (head-eng ruling 35) — the mobile half.
// Scope: docs/plans/trade-time-to-suggestion/scope-min-version-gate.md §3.
// Server half: backend/tests/test_min_version_gate.py.
//
// WHY THIS EXISTS. The gate is a server kill switch that puts a blocking
// "Update required" wall in front of every build below `app_min_version`.
// Its one unforgivable failure is blocking a build that should not be
// blocked: a launch in a dead zone, a malformed knob, a version string the
// parser does not know. Under D-056 there is no simulator to catch that, so
// this guard:
//   1–2  EXECUTES utils/appVersion's versionInt + shouldBlockForUpdate over a
//        case table (equal, older, newer, 0 = off, null / garbage → open),
//        and appStoreLive over the release-date boundary;
//   3    pins every fail-open path in the wiring (success-path-only writes,
//        never persisted, never hydrated, one decision site);
//   4    pins that each gate event fires from exactly one place, with exactly
//        the two registered props, and that the backend registered them;
//   5    pins the screen: testIDs, no FeedbackFAB, Chalkline only, the three
//        final copy strings, and the Update target (TestFlight before
//        APP_STORE_LIVE_FROM, the eas.json ascAppId listing from it; a failed
//        open keeps the gate up);
//   6    pins that the version the gate parses equals the version the binary
//        ships (G-012: the bare workflow takes the marketing version from
//        ios/, while Constants.expoConfig.version comes from app.json);
//   7    pins that no Settings file is touched by the gate;
//   8    SABOTAGE: re-runs the case table against in-memory mutants of the
//        predicate and requires each mutant to be caught.
//
// HONEST LABEL (G-035): sections 1, 2 and 8 execute real code. Sections 3–7
// prove the presence of exact wirings, not runtime behavior; the manual
// TestFlight checklist in the scope block is the runtime evidence.
//
// Run: node tests/check-update-gate.js   (npm run test:update-gate)
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const MOBILE = path.join(__dirname, '..');
const REPO = path.join(MOBILE, '..');
const SRC = path.join(MOBILE, 'src');

let ts;
try {
  ts = require('typescript');
} catch (e) {
  console.error('FAIL  typescript is not installed (run npm ci in mobile/)');
  process.exit(1);
}

let failures = 0;
const assert = (cond, name, why) => {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`);
  }
};

const readAbs = (p) => fs.readFileSync(p, 'utf8');
const read = (rel) => readAbs(path.join(MOBILE, rel));
// Block comments, JSX comments and whole-line `//` comments (as
// check-home-hub.js). Trailing `//` comments are left alone.
const stripComments = (s) =>
  s
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
const count = (hay, needle) => hay.split(needle).length - 1;
const walk = (dir, out = []) => {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(ent.name)) out.push(p);
  }
  return out;
};
const transpile = (src) =>
  ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
const load = (src) => {
  const m = { exports: {} };
  new Function('module', 'exports', 'require', transpile(src))(m, m.exports, () => {
    throw new Error('utils/appVersion.ts must not require anything at runtime');
  });
  return m.exports;
};

const UTIL_REL = 'src/utils/appVersion.ts';
const utilSrc = read(UTIL_REL);
const flags = stripComments(read('src/api/flags.ts'));
const store = stripComments(read('src/state/useFeatureFlags.ts'));
const app = stripComments(read('App.tsx'));
const screenRaw = read('src/screens/UpdateGateScreen.tsx');
const screen = stripComments(screenRaw);
// The Update tap handler's body (`const onUpdate = () => { … };`, flat).
const tapAt = screen.indexOf('const onUpdate = () => {');
const tapBody = tapAt < 0 ? '' : screen.slice(tapAt, screen.indexOf('\n  };', tapAt));
const allSrc = [...walk(SRC), path.join(MOBILE, 'App.tsx')].map((p) => ({
  rel: path.relative(MOBILE, p),
  code: stripComments(readAbs(p)),
}));

// ═══════════════════════════════════════════════════════════════════════
// 1–2 — the pure half, executed.
// ═══════════════════════════════════════════════════════════════════════
assert(!/^\s*import\s+(?!type\b)/m.test(utilSrc),
  '0. utils/appVersion.ts has zero runtime imports',
  'a runtime import breaks plain-node execution of this guard');

const VERSION_CASES = [
  ['1.22.0', 12200], ['1.21.4', 12104], ['1.21.3', 12103], ['0.0.1', 1],
  ['2.0.0', 20000], ['10.0.0', 100000], ['1.99.99', 19999], [' 1.22.0 ', 12200],
  // unparseable → null (fails open)
  [undefined, null], [null, null], ['', null], ['1.22', null], ['1', null],
  ['1.22.0.1', null], ['1.22.0-beta', null], ['v1.22.0', null],
  ['1.100.0', null], ['1.22.100', null], ['a.b.c', null], ['1..0', null],
  [12200, null], [{}, null], [['1', '22', '0'], null],
];
// [min, appInt, expected block?, label]
const BLOCK_CASES = [
  [12200, 12200, false, 'equal → open'],
  [12200, 12104, true, 'older → BLOCK'],
  [12200, 12199, true, 'one patch older → BLOCK'],
  [12200, 12201, false, 'newer → open'],
  [12200, 20000, false, 'major newer → open'],
  [0, 12104, false, '0 = off'],
  [0, 0, false, '0 = off (zero app int)'],
  [undefined, 12104, false, 'missing min → open'],
  [null, 12104, false, 'null min → open'],
  ['12200', 12104, false, 'string min → open'],
  [12200.5, 12104, false, 'fractional min → open'],
  [NaN, 12104, false, 'NaN min → open'],
  [Infinity, 12104, false, 'Infinity min → open'],
  [-1, 12104, false, 'negative min → open'],
  [1e20, 12104, false, 'unsafe-integer min → open'],
  [{}, 12104, false, 'object min → open'],
  [true, 0, false, 'boolean min → open'],
  [12200, null, false, 'unparseable app version → open'],
  [12200, undefined, false, 'missing app version → open'],
  [12200, NaN, false, 'NaN app version → open'],
  [12200, '12104', false, 'string app version → open'],
];
const MIN_CASES = [
  [12200, 12200], [1, 1], [0, 0], [-5, 0], [0.5, 0], [12200.5, 0], [NaN, 0],
  [Infinity, 0], [1e20, 0], [undefined, 0], [null, 0], ['12200', 0], [false, 0],
];
// [liveFrom, now (LOCAL time, so the table holds in any TZ), App Store?, label]
const LIVE_CASES = [
  ['2026-11-18', new Date(2026, 9, 25), false, 'weeks before → TestFlight'],
  ['2026-11-18', new Date(2026, 10, 17, 23, 59, 59, 999), false, 'last ms before local midnight → TestFlight'],
  ['2026-11-18', new Date(2026, 10, 18, 0, 0, 0, 0), true, 'local midnight → App Store'],
  ['2026-11-18', new Date(2026, 10, 18, 12), true, 'release day → App Store'],
  ['2026-11-18', new Date(2027, 0, 1), true, 'after → App Store'],
  ['garbage', new Date(2026, 9, 25), true, 'unparseable date → App Store (the permanent target)'],
  ['2026-11-18T00:00', new Date(2026, 9, 25), true, 'not YYYY-MM-DD → App Store'],
];

/** Every case-table miss for a loaded module; [] means all cases pass. */
const runCases = (mod) => {
  const miss = [];
  for (const [input, want] of VERSION_CASES) {
    const got = mod.versionInt(input);
    if (got !== want) miss.push(`versionInt(${JSON.stringify(input)}) = ${got}, want ${want}`);
  }
  for (const [min, appInt, want, label] of BLOCK_CASES) {
    const got = mod.shouldBlockForUpdate(min, appInt);
    if (got !== want) miss.push(`shouldBlockForUpdate(${String(min)}, ${String(appInt)}) = ${got}, want ${want} (${label})`);
  }
  for (const [raw, want] of MIN_CASES) {
    const got = mod.minVersionOrOff(raw);
    if (got !== want) miss.push(`minVersionOrOff(${String(raw)}) = ${got}, want ${want}`);
  }
  // Composition, as App.tsx calls it.
  const composed = [
    [12200, '1.21.4', true], [12200, '1.22.0', false], [12200, '1.22.1', false],
    [12200, 'garbage', false], [12200, undefined, false], [0, '1.21.4', false],
  ];
  for (const [min, ver, want] of composed) {
    const got = mod.shouldBlockForUpdate(min, mod.versionInt(ver));
    if (got !== want) miss.push(`block(${min}, versionInt(${JSON.stringify(ver)})) = ${got}, want ${want}`);
  }
  for (const [liveFrom, now, want, label] of LIVE_CASES) {
    const got = mod.appStoreLive(liveFrom, now);
    if (got !== want) miss.push(`appStoreLive(${liveFrom}, ${now.toString()}) = ${got}, want ${want} (${label})`);
  }
  return miss;
};
const CASE_COUNT = VERSION_CASES.length + BLOCK_CASES.length + MIN_CASES.length + 6 + LIVE_CASES.length;

const util = load(utilSrc);
{
  const miss = runCases(util);
  assert(miss.length === 0,
    `1–2. versionInt / minVersionOrOff / shouldBlockForUpdate / appStoreLive pass all ${CASE_COUNT} executed cases`,
    miss.join('\n      '));
}

// ═══════════════════════════════════════════════════════════════════════
// 3 — fail-open wiring.
// ═══════════════════════════════════════════════════════════════════════
{
  // 3a–c: flags.ts writes the min on the SUCCESS path only.
  const write = '_appMinVersion = minVersionOrOff(res?.app_min_version);';
  assert(count(flags, 'let _appMinVersion = 0;') === 1,
    '3a. api/flags.ts: the module min starts at 0 (off)');
  assert(count(flags, write) === 1 && (flags.match(/_appMinVersion\s*=[^=]/g) || []).length === 2,
    '3b. …and has exactly one write, normalized by minVersionOrOff',
    `expected the initializer plus exactly: ${write}`);
  const fnAt = flags.indexOf('export async function loadFeatureFlags(');
  const awaitAt = flags.indexOf("await api.get<", fnAt);
  const writeAt = flags.indexOf(write);
  const returnAt = flags.indexOf('return merged;', fnAt);
  const catchAt = flags.indexOf('} catch (err) {', fnAt);
  assert(fnAt > 0 && awaitAt > fnAt && writeAt > awaitAt && writeAt < returnAt && returnAt < catchAt,
    '3c. …after the fetch resolves and before the success return — never in the catch',
    'a write in the catch (or before the await) would let a failed fetch set the gate');

  // 3d–g: the store sets appMinVersion only from a resolved revalidate.
  assert(count(store, 'appMinVersion: 0,') === 1,
    '3d. useFeatureFlags: appMinVersion starts at 0');
  const setSite = 'set({ flags, loaded: true, appMinVersion: fetchedAppMinVersion() });';
  const revalAt = store.indexOf('revalidateFlags: async () => {');
  const loadAt = store.indexOf('await loadFeatureFlags({ throwOnError: true });', revalAt);
  const setAt = store.indexOf(setSite);
  // The OUTER catch of revalidateFlags (the inner one guards the cache write).
  const revalBlock = store.slice(revalAt, store.indexOf('maybeRevalidateFlags: async', revalAt));
  const failSet = revalBlock.slice(revalBlock.lastIndexOf('} catch {'));
  assert(count(store, setSite) === 1 && revalAt > 0 && loadAt > revalAt && setAt > loadAt,
    '3e. …set once, in revalidateFlags, after the fetch resolves, in the SAME set() as the fetched flags');
  assert(/set\(\{ loaded: true \}\);/.test(failSet) && !/appMinVersion/.test(failSet),
    '3f. …and the failed-fetch branch never touches it (a timeout or dead zone cannot raise the gate)');
  assert((store.match(/appMinVersion/g) || []).length === 3,
    '3g. …no other read/write site in the store (interface, initializer, the one set)',
    `found ${(store.match(/appMinVersion/g) || []).length} mentions`);
  const cacheFn = store.slice(store.indexOf('loadCachedFlags: async () => {'), revalAt);
  assert(cacheFn.length > 0 && !/appMinVersion|app_min_version/.test(cacheFn),
    '3h. loadCachedFlags never hydrates a min (the gate is never persisted)');
  assert(/AsyncStorage\.setItem\(FF_KEY, JSON\.stringify\(flags\)\)/.test(store)
      && (store.match(/AsyncStorage\.setItem\(/g) || []).length === 1,
    '3i. the only persisted payload is the flag map');

  // 3j–m: one decision, one render fork, both in App.tsx.
  assert(count(app, 'const appMinVersion = useFeatureFlags((s) => s.appMinVersion);') === 1
      && count(app, 'const updateRequired = shouldBlockForUpdate(appMinVersion, APP_VERSION_INT);') === 1,
    '3j. App.tsx decides with shouldBlockForUpdate(store min, APP_VERSION_INT)');
  assert(/\{updateRequired && fontsSettled \? \(\s*<UpdateGateScreen minVersion=\{appMinVersion\} appVersionInt=\{APP_VERSION_INT as number\} \/>\s*\) : \(\s*<RootNav booted=\{booted && fontsSettled\} \/>\s*\)\}/.test(app),
    '3k. …and the gate REPLACES RootNav (nothing beneath it is mounted)');
  const mounts = allSrc.filter((f) => /<UpdateGateScreen\b/.test(f.code));
  assert(mounts.length === 1 && mounts[0].rel === 'App.tsx' && count(mounts[0].code, '<UpdateGateScreen') === 1,
    '3l. UpdateGateScreen has exactly one mount, App.tsx',
    `mounted in: ${mounts.map((f) => f.rel).join(', ')}`);
  const deciders = allSrc.filter((f) => /shouldBlockForUpdate\(/.test(f.code) && f.rel !== UTIL_REL);
  assert(deciders.length === 1 && deciders[0].rel === 'App.tsx'
      && count(deciders[0].code, 'shouldBlockForUpdate(') === 2,
    '3m. shouldBlockForUpdate is called only in App.tsx (render + foreground)',
    `callers: ${deciders.map((f) => f.rel).join(', ')}`);
  assert(/if \(shouldBlockForUpdate\(ff\.appMinVersion, APP_VERSION_INT\)\) \{\s*void ff\.revalidateFlags\(\);\s*\} else \{\s*void ff\.maybeRevalidateFlags\(\);\s*\}/.test(app),
    '3n. foreground: while blocked, refetch unthrottled (so a lift lands now); otherwise the ≥30-min throttle');
  assert(count(screen, 'export const APP_VERSION_INT = versionInt(Constants.expoConfig?.version);') === 1,
    '3o. the app version int is parsed from Constants.expoConfig?.version (as api/client.ts X-App-Version)');
}

// ═══════════════════════════════════════════════════════════════════════
// 4 — events: one emitter each, exact props, registered server-side.
// ═══════════════════════════════════════════════════════════════════════
{
  const PROPS = '{ min_version: minVersion, app_version_int: appVersionInt }';
  for (const name of ['update_gate_shown', 'update_gate_tapped']) {
    const sites = allSrc.filter((f) => f.code.includes(`'${name}'`) || f.code.includes(`"${name}"`));
    assert(sites.length === 1 && sites[0].rel === 'src/screens/UpdateGateScreen.tsx'
        && count(sites[0].code, `track('${name}', ${PROPS});`) === 1
        && count(sites[0].code, name) === 1,
      `4. ${name} fires from exactly one place, with exactly min_version + app_version_int`,
      `sites: ${sites.map((f) => f.rel).join(', ') || 'none'}`);
  }
  const effAt = screen.indexOf('useEffect(() => {');
  const effEnd = screen.indexOf('}, []);', effAt);
  assert(effAt > 0 && effEnd > effAt
      && screen.slice(effAt, effEnd).includes("track('update_gate_shown'"),
    '4a. update_gate_shown fires from a mount-once effect (once per gate show)');
  assert(tapAt > 0 && tapBody.indexOf("track('update_gate_tapped'") >= 0
      && tapBody.indexOf("track('update_gate_tapped'") < tapBody.indexOf('Linking.openURL(url)'),
    '4b. update_gate_tapped fires on the Update tap, before the store hand-off');

  const tax = readAbs(path.join(REPO, 'backend', 'analytics_taxonomy.py'));
  const q = readAbs(path.join(REPO, 'backend', 'analytics_queries.py'));
  const block = (txt, open) => {
    const at = txt.indexOf(open);
    return at < 0 ? '' : txt.slice(at, txt.indexOf('\n})', at));
  };
  const allowed = block(tax, 'ALLOWED_CLIENT_EVENTS: frozenset[str] = frozenset({');
  const nonIntent = block(q, 'NON_INTENT_EVENTS = frozenset({');
  for (const name of ['update_gate_shown', 'update_gate_tapped']) {
    assert(allowed.includes(`"${name}"`)
        && new RegExp(`"${name}":\\s*frozenset\\(\\{"min_version", "app_version_int"\\}\\)`).test(tax)
        && nonIntent.includes(`"${name}"`),
      `4c. backend: ${name} is allowlisted, has the exact two-prop row, and is NON_INTENT`,
      'default-deny ingest drops an unregistered name behind a 200 (G-031)');
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 5 — the screen.
// ═══════════════════════════════════════════════════════════════════════
{
  assert(count(screen, 'testID="update-gate.screen"') === 1 && count(screen, 'testID="update-gate.update"') === 1,
    '5a. static testIDs update-gate.screen + update-gate.update');
  assert(!/FeedbackFAB/.test(screen),
    '5b. no FeedbackFAB (blocking gate = modal/onboarding exception, root CLAUDE.md #188)');
  // 5c — the final copy (marketing-lead via head-eng). Title and button are
  // the b8.* rows; the body is option (B) until the operator's A8 pick.
  const COPY_PINS = [
    "const UPDATE_GATE_TITLE = 'Update required';",
    "const UPDATE_GATE_BUTTON = 'Update';",
    "// COPY: option (B), operator pick A8 due 11-03\n"
      + "const UPDATE_GATE_BODY = 'This version of the app is out of date. Update to keep using it.';",
  ];
  const missingCopy = COPY_PINS.filter((pin) => count(screenRaw, pin) !== 1);
  assert(missingCopy.length === 0,
    '5c. the three copy strings are the final copy, each in one named constant (body carries the A8 marker)',
    `missing or changed: ${missingCopy.join(' | ')}`);
  assert(!/COPY: placeholder/.test(screenRaw)
      && count(screen, '{UPDATE_GATE_TITLE}') === 1 && count(screen, '{UPDATE_GATE_BODY}') === 1
      && count(screen, 'label={UPDATE_GATE_BUTTON}') === 1,
    '5c2. no placeholder marker remains, and the screen renders exactly those three constants');

  // 5d — where Update goes: TestFlight before the App Store release date,
  // the App Store listing (eas.json ascAppId) from it. Failure keeps the gate.
  const eas = JSON.parse(read('eas.json'));
  const ascAppId = eas?.submit?.production?.ios?.ascAppId;
  assert(typeof ascAppId === 'string' && /^\d+$/.test(ascAppId)
      && count(screen, `export const APP_STORE_URL = 'https://apps.apple.com/app/id${ascAppId}';`) === 1,
    '5d. the App Store URL is the listing for eas.json\'s ascAppId');
  assert(count(screen, "export const APP_STORE_LIVE_FROM = '2026-11-18';") === 1
      && count(screen, "export const TESTFLIGHT_URL = 'itms-beta://';") === 1,
    '5d2. APP_STORE_LIVE_FROM is 2026-11-18 and the pre-release target is the TestFlight app');
  assert(count(tapBody, 'const url = appStoreLive(APP_STORE_LIVE_FROM, new Date()) ? APP_STORE_URL : TESTFLIGHT_URL;') === 1
      && count(screen, 'Linking.openURL(') === 1,
    '5d3. Update picks App Store from the live date, TestFlight before it, through utils/appVersion.appStoreLive');
  assert(/try \{\s*Linking\.openURL\(url\)\.catch\(\(\) => \{\}\);\s*\} catch \{\s*\}/.test(tapBody)
      && !/\bset[A-Z]\w*\(|\bset\(|setState|getState/.test(tapBody),
    '5d4. a failed open (sync throw or rejection) is swallowed and changes no gate state, so the gate stays up');
  assert(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(screen)
      && /from '\.\.\/theme\/chalkline'/.test(screen)
      && /import \{ Button, Text \} from '\.\.\/components\/chalkline';/.test(screen)
      && !/import \{[^}]*\bText\b[^}]*\} from 'react-native'/.test(screen),
    '5e. Chalkline only: no raw colors, tokens from theme/chalkline, chalkline Text + Button');
}

// ═══════════════════════════════════════════════════════════════════════
// 6 — the parsed version is the shipped version (G-012).
// ═══════════════════════════════════════════════════════════════════════
{
  const appJsonVersion = JSON.parse(read('app.json'))?.expo?.version;
  const plist = read('ios/DTFDynastyTradeFinder/Info.plist');
  const plistVersion = (/<key>CFBundleShortVersionString<\/key>\s*<string>([^<]*)<\/string>/.exec(plist) || [])[1];
  const marketing = [...read('ios/DTFDynastyTradeFinder.xcodeproj/project.pbxproj')
    .matchAll(/MARKETING_VERSION = ([^;]+);/g)].map((m) => m[1].trim());
  assert(util.versionInt(appJsonVersion) !== null,
    `6a. app.json expo.version (${appJsonVersion}) parses to a version int`,
    'an unparseable version silently disables the gate for this build');
  assert(plistVersion === appJsonVersion && marketing.length > 0 && marketing.every((v) => v === appJsonVersion),
    '6b. app.json version == Info.plist CFBundleShortVersionString == every MARKETING_VERSION',
    `app.json ${appJsonVersion}, Info.plist ${plistVersion}, MARKETING_VERSION ${marketing.join(', ')} — `
      + 'the gate parses app.json but the binary ships the native version (G-012); bump all three together');
}

// ═══════════════════════════════════════════════════════════════════════
// 7 — Settings is not the gate's (SettingsHubScreen / SettingsTestingScreen
//     belong to onboarding-eng).
// ═══════════════════════════════════════════════════════════════════════
{
  const SETTINGS_RE = /^mobile\/src\/screens\/(SettingsScreen\.tsx|settings\/)/;
  const settingsFiles = allSrc.filter((f) => SETTINGS_RE.test(`mobile/${f.rel}`));
  const leaks = settingsFiles.filter((f) =>
    /UpdateGate|update_gate|app_min_version|appMinVersion|shouldBlockForUpdate|versionInt|utils\/appVersion/.test(f.code));
  assert(settingsFiles.length > 0 && leaks.length === 0,
    '7a. no Settings file references the gate',
    `references in: ${leaks.map((f) => f.rel).join(', ')}`);
  // 7b — best effort, branch-scoped: when a diff against origin/main is
  // available AND it touches the gate, it must not also touch Settings.
  // Skips quietly where origin/main is absent (CI's shallow checkout).
  const base = spawnSync('git', ['merge-base', 'HEAD', 'origin/main'], { cwd: REPO, encoding: 'utf8' });
  if (base.status !== 0 || !base.stdout.trim()) {
    console.log('SKIP  7b. branch diff vs origin/main unavailable here');
  } else {
    const diff = spawnSync('git', ['diff', '--name-only', base.stdout.trim()], { cwd: REPO, encoding: 'utf8' });
    const changed = (diff.stdout || '').split('\n').filter(Boolean);
    const touchesGate = changed.some((p) => /mobile\/src\/(utils\/appVersion\.ts|screens\/UpdateGateScreen\.tsx)$/.test(p));
    const settingsChanged = changed.filter((p) => SETTINGS_RE.test(p));
    if (!touchesGate) {
      console.log('SKIP  7b. this branch does not change the gate');
    } else {
      assert(diff.status === 0 && settingsChanged.length === 0,
        '7b. a branch that changes the gate changes no Settings file',
        `Settings files changed: ${settingsChanged.join(', ')}`);
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 8 — SABOTAGE: the case table must catch broken predicates. Each mutant is
// built in memory from the real source (nothing on disk changes) and must
// FAIL at least one case. A mutant that passes means the table lost a tooth.
// ═══════════════════════════════════════════════════════════════════════
{
  const MUTANTS = [
    ['equal blocks', 'return appVersionInt < min;', 'return appVersionInt <= min;'],
    ['garbage min accepted', 'Number.isSafeInteger(raw) && raw > 0', 'raw > 0'],
    ['unparseable app version blocks',
      "if (typeof appVersionInt !== 'number' || !Number.isSafeInteger(appVersionInt)) return false;", ''],
    ['3-digit patch parses', '\\.(\\d{1,2})$/', '\\.(\\d{1,3})$/'],
    ['release-day midnight still TestFlight',
      'return now.getTime() >= liveFrom.getTime();', 'return now.getTime() > liveFrom.getTime();'],
  ];
  for (const [label, from, to] of MUTANTS) {
    const applies = count(utilSrc, from) === 1;
    let caught = false;
    if (applies) {
      try {
        caught = runCases(load(utilSrc.replace(from, to))).length > 0;
      } catch (e) {
        caught = true;   // a mutant that cannot even load is caught
      }
    }
    assert(applies && caught,
      `8. sabotage "${label}" is caught by the case table`,
      applies ? 'the mutant passed every case' : `mutation anchor not found exactly once: ${from}`);
  }
}

if (failures) {
  console.error(`\n${failures} update-gate check(s) failed.`);
  process.exit(1);
}
console.log('\nok    update gate: predicate executed, fail-open wiring, one emitter per event, screen, version parity, sabotage caught');
