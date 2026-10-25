#!/usr/bin/env node
// WHY THIS EXISTS (head-eng ruling 11; #339 §9.5): the AC-L1 session reads a
// per-tap timing off the device, so the build carries a Testing readout. It
// is a QA surface and must stay invisible to everyone else: a readout that
// renders with its flag off is a debug row in a shipped app. And onboarding-
// eng now owns the Settings files outright, so this Trades branch must not
// edit them — it ships a self-contained component they mount.
// What it does: EXECUTES components/TimingReadoutRow.tsx with React and the
// flag hook stubbed (null with the flag off; the row, its testID and the
// last ms_from_tap with it on), executes utils/tapTiming.ts, pins the flag's
// registrations. (A branch-only check that #363 touched no Settings file
// was removed before merge: on main it would fail every later Settings PR.)
// HONEST LABEL (G-035): rendering is a stubbed call, not a device render;
// the mount itself is onboarding-eng's.
//
// Run: node tests/check-timing-readout.js   (or: npm run test:timing-readout)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
let ts;
try { ts = require('typescript'); } catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}
const MOBILE = path.join(__dirname, '..');
const ROOT = path.join(MOBILE, '..');
const SRC = path.join(MOBILE, 'src');
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');

let failures = 0;
function check(name, cond, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}${detail ? `\n      ${detail}` : ''}`); }
}
function load(rel, requireMap) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(read(rel), { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React } }).outputText,
  { module, exports: module.exports, Set, Map,
    require: (name) => {
      if (!(name in requireMap)) throw new Error(`${rel}: unexpected require ${name}`);
      return requireMap[name];
    } });
  return module.exports;
}

console.log('check-timing-readout:');

const tapTiming = load('utils/tapTiming.ts', {});
let flagOn = false;
const el = (type, props, ...children) => ({ type, props: props || {}, children });
const React = { createElement: el, useSyncExternalStore: (_sub, get) => get() };
const row = load('components/TimingReadoutRow.tsx', {
  react: { __esModule: true, default: React, ...React },
  'react-native': { View: 'View', StyleSheet: { create: (x) => x } },
  './chalkline': { Text: 'Text' },
  '../theme/chalkline': { fonts: { data: 'mono' }, ink: { line: '#000' }, space: { xs: 4, md: 12 } },
  '../state/useFeatureFlags': { useFlag: (k) => (k === 'testing.timing_readout' ? flagOn : false) },
  '../utils/tapTiming': tapTiming,
});
const text = (node) => (node == null || typeof node !== 'object' ? String(node ?? '')
  : node.children.map(text).join(''));

{
  flagOn = false;
  check('1a. EXECUTED: flag off ⇒ the component renders null (safe to mount anywhere)',
    row.TimingReadoutRow({}) === null && row.useTimingReadoutEnabled() === false);
  flagOn = true;
  const empty = row.TimingReadoutRow({});
  check('1b. flag on, no search yet ⇒ the row with the default testID and an honest empty line',
    !!empty && empty.props.testID === 'settings.testing.timing-readout' && /No trade search yet/.test(text(empty)));
  tapTiming.recordTapTiming({ msFromTap: 187, networkType: 'wifi', launchState: 'repeat_tap' });
  const shown = row.TimingReadoutRow({ testID: 'x.readout' });
  check('1c. flag on ⇒ the device\'s last ms_from_tap with its cell (network_type, launch_state); the testID can be overridden',
    !!shown && shown.props.testID === 'x.readout' && /187 ms · wifi · repeat_tap/.test(text(shown))
      && row.useTimingReadoutEnabled() === true);
  flagOn = false;
  check('1d. …and null again the moment the flag goes off', row.TimingReadoutRow({}) === null);
}

{
  const comp = read('components/TimingReadoutRow.tsx');
  check('2a. the component reads ONLY the flag hook and the in-memory store (no request, no storage)',
    !/from '\.\.\/api\//.test(comp) && !/AsyncStorage|SecureStore|fetch\(/.test(comp));
  const trace = read('state/tradeSearchTrace.ts');
  check('2b. the R2 emitter writes the store with ms_from_tap and its cell',
    /recordTapTiming\(\{ msFromTap: ms, networkType: t\.networkType, launchState: t\.launchState \}\);/.test(trace));
}

{
  const features = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/features.json'), 'utf8'));
  const flags = fs.readFileSync(path.join(ROOT, 'backend/feature_flags.py'), 'utf8');
  const cref = fs.readFileSync(path.join(ROOT, 'docs/config-reference.md'), 'utf8');
  const fixtures = ['onboarding-v2', 'profiles-on', 'release-300', 'release-espn-send-off', 'release']
    .map((f) => JSON.parse(fs.readFileSync(path.join(ROOT, `backend/tests/fixtures/flags/${f}.json`), 'utf8')));
  check('3a. the flag ships dark everywhere it is declared (features.json, FLAG_KEYS, config-reference, flag fixtures)',
    features['testing.timing_readout'] === false
      && /"testing\.timing_readout",/.test(flags)
      && /\| `testing\.timing_readout` \| false \|/.test(cref)
      && fixtures.every((f) => f['testing.timing_readout'] === false));
}

console.log(failures ? `check-timing-readout: ${failures} FAILED` : 'check-timing-readout: all passed');
process.exit(failures ? 1 : 0);
