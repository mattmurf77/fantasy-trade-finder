'use strict';
// Shared by check-direction-card.js and check-direction-sheet.js (not a check
// itself). Renders the REAL HomePlayoffBanner against host stubs, the way
// check-home-playoff-banner.js does: the real utils (homePlayoffBanner,
// playoffOdds, directionCard and both copy modules) are executed; React,
// React Native, the query and the session are stubs. No simulator, network
// or account write (D-056).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const MOBILE = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(MOBILE, rel), 'utf8');
const readRoot = (rel) => fs.readFileSync(path.join(MOBILE, '..', rel), 'utf8');
const NOW = Date.parse('2026-11-07T15:00:00Z');

function load(rel, requireFn, jsx = false) {
  const m = { exports: {} };
  const out = ts.transpileModule(read(rel), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, ...(jsx ? { jsx: ts.JsxEmit.React } : {}),
  } }).outputText;
  vm.runInNewContext(out, { exports: m.exports, module: m, require: requireFn, Date, Math, JSON, Number, String, Array, Object });
  return m.exports;
}
const noImports = (name) => (r) => { throw new Error(`${name} has no imports, asked for ${r}`); };
const cardCopy = load('src/utils/directionCardCopy.ts', noImports('directionCardCopy'));
const pagesCopy = load('src/utils/directionPagesCopy.ts', noImports('directionPagesCopy'));
const cardUtil = load('src/utils/directionCard.ts', (r) => {
  if (r === './directionCardCopy') return cardCopy;
  if (r === './directionPagesCopy') return pagesCopy;
  throw new Error(`directionCard.ts must not require ${r} at runtime`);
});
const bannerUtil = load('src/utils/homePlayoffBanner.ts', noImports('homePlayoffBanner'));
const playoffOdds = load('src/utils/playoffOdds.ts', noImports('playoffOdds'));

// ── Fixtures ────────────────────────────────────────────────────────────
function forecast(probability = 0.624, state = 'current') {
  return { state, model_current: true, next_attempt_not_before: '2026-11-10T14:30:00Z', run: {
    status: 'complete', result: { captured_at: '2026-11-07T14:00:00Z', coverage: { estimate_status: 'complete' },
      teams: [{ roster_id: 1, playoff_probability: 0.99 }, { roster_id: 2, playoff_probability: probability }] },
  } };
}
function block(patch = {}) {
  return Object.assign({
    version: 1, state: 'ready', reason: null, captured_at: '2026-11-07T14:00:00Z',
    playoff_probability: 0.624, playoff_clinched: false, playoff_eliminated: false,
    projected_pick: { label: '1.08', slot: 8, owns_own_pick: true, owner_name: 'Mine' },
    band: 'middle', primary: 'playoffs',
    options: { playoffs: { offered: true, reason: null }, draft_pick: { offered: true, reason: null } },
  }, patch);
}

// ── The component, against stubs ────────────────────────────────────────
const state = {
  active: { user: { user_id: 'viewer' }, league: { league_id: 'league-a' },
    leagues: [{ league_id: 'league-a', platform: 'sleeper' }], hasToken: true, switching: false },
  data: forecast(),
  error: false,
  loading: false,
  flags: {},
  hooks: [],
  at: 0,
  tracked: [],
  calls: [],
};
function resetFlags(patch = {}) {
  state.flags = Object.assign({ 'league.projections': true, 'league.projection_outlook': true,
    'league.direction_card': true, 'league.direction_view_sheet': true, 'league.direction_pages': true }, patch);
}
resetFlags();
const React = { Fragment: 'Fragment', createElement: (type, props, ...children) => ({ type, props: props || {}, children }) };
const token = new Proxy({}, { get: (_, key) => new Proxy({}, { get: (__, inner) => `${String(key)}.${String(inner)}` }) });
const modules = {
  react: { __esModule: true, default: React,
    useState: (initial) => {
      const at = state.at++;
      if (!(at in state.hooks)) state.hooks[at] = initial;
      return [state.hooks[at], (v) => { state.hooks[at] = typeof v === 'function' ? v(state.hooks[at]) : v; }];
    },
    useRef: (initial) => { const at = state.at++; if (!(at in state.hooks)) state.hooks[at] = { current: initial }; return state.hooks[at]; },
    useEffect: (effect) => { state.at++; effect(); } },
  'react-native': { Pressable: 'Pressable', StyleSheet: { create: (v) => v }, View: 'View' },
  '@tanstack/react-query': { useQuery: () => ({ data: state.data, isError: state.error, isLoading: state.loading }) },
  '../chalkline': { Icon: 'Icon', Text: 'Text' },
  '../../theme/chalkline': token,
  '../../api/leagueProjections': { getLeagueProjectionBatch: () => { throw new Error('render must not fetch'); } },
  '../../state/useSession': { NO_LEAGUE_ID: 'no_league', useSession: (select) => select(state.active) },
  '../../state/useFeatureFlags': { useFlag: (name) => { assert(name in state.flags, `unexpected flag ${name}`); return state.flags[name]; } },
  '../../utils/homePlayoffBanner': { homePlayoffBanner: (v, r, f) => bannerUtil.homePlayoffBanner(v, r, f, NOW) },
  '../../utils/playoffOdds': playoffOdds,
  '../../api/events': { track: (...a) => state.tracked.push(a) },
  '../../utils/directionCard': cardUtil,
  '../../utils/directionCardCopy': cardCopy,
  '../../utils/directionPagesCopy': pagesCopy,
  '../OutlookBiasReceipt': { outlookDisplayName: (v) => (v ? { contender: 'Contending' }[v] ?? null : null) },
  './StatusRow': { RowAction: 'RowAction' },
  './DirectionSheet': { __esModule: true, default: 'DirectionSheet' },
};
const component = load('src/components/home/HomePlayoffBanner.tsx', (name) => {
  assert(name in modules, `unexpected component dependency: ${name}`);
  return modules[name];
}, true);
const props = {
  rosterId: 2, screen: 'Home',
  onDetails: () => state.calls.push('details'),
  onReviewOutlook: (o) => state.calls.push(`review:${o}`),
  onDirectionTap: (tap) => state.calls.push(tap),
};
/** A fresh mount: hooks and logs cleared. */
function mount(data, flagPatch) {
  state.hooks = []; state.tracked = []; state.calls = [];
  state.data = data; state.error = false; state.loading = false;
  resetFlags(flagPatch);
  return render();
}
function render() { state.at = 0; return component.default(props); }
const nodes = (n) => (Array.isArray(n) ? n.flatMap(nodes) : n && typeof n === 'object' ? [n, ...nodes(n.children)] : []);
const byId = (tree, id) => nodes(tree).find((n) => n.props && n.props.testID === id);
const byType = (tree, type) => nodes(tree).filter((n) => n.type === type);
const words = (n) => (Array.isArray(n) ? n.flatMap(words) : typeof n === 'string' ? [n] : n && typeof n === 'object' ? words(n.children) : []);
const strip = (s) => s.replace(/\{\/\*[\s\S]*?\*\/\}/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

let passes = 0;
let failures = 0;
function check(cond, name, why) {
  if (cond) { passes += 1; console.log(`PASS  ${name}`); } else { failures += 1; console.error(`FAIL  ${name}${why ? `\n      ${why}` : ''}`); }
}
function finish(label) {
  console.log('');
  if (failures) { console.error(`${failures} ${label} check(s) FAILED (${passes} passed).`); process.exit(1); }
  console.log(`All ${label} checks passed (${passes}).`);
}

module.exports = {
  read, readRoot, strip, cardUtil, cardCopy, pagesCopy, forecast, block, state, mount, render, props,
  nodes, byId, byType, words, check, finish,
};
