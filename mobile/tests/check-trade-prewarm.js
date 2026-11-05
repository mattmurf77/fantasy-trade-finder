#!/usr/bin/env node
// Executes the real prewarm effect with delayed storage/session replies.
// This proves request scope and cancellation, not physical-device latency.
'use strict';
const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const ts = require('typescript');
const src = path.join(__dirname, '../src');
const compile = (file, context) => {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(src, file), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  }).outputText, { module, exports: module.exports, ...context });
  return module.exports;
};
const pref = compile('api/tradePregen.ts');
const pages = compile('utils/devicePage.ts', { require: () => ({}) });
const flush = async () => { for (let i = 0; i < 5; i++) await new Promise(setImmediate); };
function boot(over = {}) {
  const env = { enabled: true, active: true, appState: 'active', calls: [], init: 0,
    user: 'a', league: 'league-a', format: 'sf', hasToken: true, switching: false, isDemo: false, ...over };
  let releasePref, releaseInit, cleanup;
  const state = () => ({ user: { user_id: env.user }, league: { league_id: env.league },
    activeFormat: env.format, hasToken: env.hasToken, switching: env.switching, isDemo: env.isDemo,
    revalidateSession: () => { env.init++; return new Promise((r) => { releaseInit = r; }); } });
  const useSession = (selector) => selector(state());
  useSession.getState = state;
  const app = { get currentState() { return env.appState; } };
  const hook = compile('hooks/useTradePagePrewarm.ts', { require: (name) => {
    switch (name) {
      case 'react': return { useEffect: (fn) => { cleanup = fn(); } };
      case 'react-native': return { AppState: app };
      case '@react-native-async-storage/async-storage': return { default: {
        getItem: () => new Promise((r) => { releasePref = r; }),
      } };
      case '../api/tradePregen': return pref;
      case '../state/devicePageStore': return { hydrateDevicePages: async () => {},
        refreshDevicePage: (target, now, current) => { env.calls.push({ target, current }); } };
      case '../state/useSession': return { useSession };
      case '../state/useFeatureFlags': return { useFlag: () => env.enabled,
        useFeatureFlags: { getState: () => ({ flags: { 'trade.first_page_store': env.enabled } }) } };
      case '../utils/devicePage': return pages;
      case './useAppActive': return { useAppActive: () => env.active };
      default: throw new Error('Unexpected import: ' + name);
    }
  } });
  hook.useTradePagePrewarm();
  return { env, pref: async (raw = null) => { releasePref?.(raw); await flush(); },
    init: async () => { releaseInit?.(); await flush(); }, cleanup: () => cleanup?.() };
}
(async () => {
  let count = 0;
  for (const raw of [null, 'on']) {
    const h = boot(); await h.pref(raw);
    assert.equal(h.env.calls.length, 0, 'session init must settle before warm request');
    assert.equal(h.env.init, 1); await h.init();
    assert.equal(h.env.calls.length, 1);
    assert.deepEqual(JSON.parse(JSON.stringify(h.env.calls[0].target)), {
      key: 'ftf_trade_device_page_v1:a:league-a:sf', scope: raw === 'on' ? 'organic:f=0.75' : 'organic:f=0.50',
      request: { league_id: 'league-a', fairness_threshold: raw === 'on' ? 0.75 : 0.5 },
    });
    assert.equal(h.env.calls[0].current(), true);
    h.env.user = 'other'; assert.equal(h.env.calls[0].current(), false); count++;
  }
  for (const over of [{ enabled: false }, { active: false }, { hasToken: false },
    { switching: true }, { isDemo: true }, { league: 'no_league' }, { league: 'league_demo' }, { user: '' }]) {
    const h = boot(over); await h.pref(); await h.init();
    assert.equal(h.env.calls.length, 0); assert.equal(h.env.init, 0); count++;
  }
  for (const change of [h => { h.env.user = 'b'; }, h => { h.env.league = 'league-b'; },
    h => { h.env.format = '1qb'; }, h => { h.env.switching = true; },
    h => { h.env.hasToken = false; }, h => { h.env.enabled = false; },
    h => { h.env.appState = 'background'; }, h => h.cleanup()]) {
    const h = boot(); await h.pref(); change(h); await h.init();
    assert.equal(h.env.calls.length, 0, 'late session reply must not warm a replaced context'); count++;
  }
  const nav = fs.readFileSync(path.join(src, 'navigation/TabNav.tsx'), 'utf8');
  assert.match(nav, /export default function TabNav\(\) \{\s*useTradePagePrewarm\(\);/);
  console.log(`${count + 1} trade prewarm cases passed (executed effect; no device timing claim).`);
})().catch(e => { console.error(e); process.exitCode = 1; });
