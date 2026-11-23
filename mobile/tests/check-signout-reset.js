#!/usr/bin/env node
// WHY THIS EXISTS (2026-11-22, Release simulator build, two verified accounts
// on one device). Sign-out cleared the session keys and the device-held trade
// pages, and nothing else:
//   1. Settings kept showing "@A" and "See plans" after signing in as B (Pro):
//      the hub reads ['account'] from the TanStack Query cache, which sign-out
//      never cleared, and useEntitlements only re-asked the server on an
//      A → B user change — never on the null → B sign-in after a sign-out.
//   2. Home showed A's outlook, rank and position tiles to B: those queries are
//      keyed by league, not account, and both accounts were in one league.
//   3. "Team review · done" showed for an account that never ran it: the
//      completion map was device-wide, keyed by league only.
//   4. "Verify account" sat under "Verified — your board and account actions
//      are locked to you".
//   5. Sign out happened on one tap with no confirmation.
//   6. (follow-up) a FRESH INSTALL's first sign-in never asked for
//      entitlements at all: boot's empty cache hydrate set `loaded`, so the
//      token-edge ask was skipped; Pro read "See plans", and sendPreCheck read
//      "not enforcing" and skipped the paywall.
// The fix: one account reset (src/state/accountReset.ts) that every sign-out
// path reaches through useSession.signOut, and that a sign-in as a different
// account reaches through setUser / startDemoSession.
//
// What it does: TRANSPILES and EXECUTES src/state/useSession.ts (signOut,
// setUser, startDemoSession against a recording reset), src/state/accountReset.ts
// on the app's real QueryClient (src/state/queryClient.ts on
// @tanstack/query-core) with the real src/state/useEntitlements.ts,
// teamReviewCompletion.ts and rosterSetup.ts, and SignOutRow's confirmSignOut
// against a stub Alert. Then pins by source shape that every UI sign-out goes
// through useSession.signOut, that nothing else clears the session token, and
// the Verify-row condition on both Settings surfaces.
//
// HONEST LABEL (G-035): the executed parts prove the reset and the session
// store's calls into it; the source pins prove the screens call signOut and
// render the row under that condition, not that a device paints it — the
// TestFlight checklist in the commit / report covers that.
//
// Run: node tests/check-signout-reset.js   (or: npm run test:signout-reset)
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const SRC = path.join(ROOT, 'src');
let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(1);
}

const pass = [];
const fail = [];
let finished = false;
process.on('exit', () => {
  if (!finished) {
    console.error('check-signout-reset did not finish (a check hung): FAILED');
    process.exitCode = 1;
  }
});

const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const exists = (rel) => fs.existsSync(path.join(ROOT, rel));
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1');
function between(src, start, end) {
  const i = src.indexOf(start);
  if (i < 0) return '';
  const j = src.indexOf(end, i + start.length);
  return j < 0 ? src.slice(i) : src.slice(i, j);
}

function load(rel, stubs) {
  const js = ts.transpileModule(read(rel), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019, jsx: ts.JsxEmit.React },
  }).outputText;
  const mod = { exports: {} };
  const req = (name) => {
    if (Object.prototype.hasOwnProperty.call(stubs, name)) {
      const v = stubs[name];
      return typeof v === 'function' && v.__lazy ? v() : v;
    }
    throw new Error(`${rel} gained an unexpected runtime import ("${name}") — stub it here deliberately.`);
  };
  // eslint-disable-next-line no-new-func
  new Function('module', 'exports', 'require', js)(mod, mod.exports, req);
  return mod.exports;
}
const lazy = (fn) => Object.assign(fn, { __lazy: true });

function makeCreate() {
  return function create(init) {
    let state;
    const listeners = new Set();
    const setState = (p, replace) => {
      const prev = state;
      const next = typeof p === 'function' ? p(state) : p;
      state = replace ? next : Object.assign({}, state, next);
      listeners.forEach((l) => l(state, prev));
    };
    const getState = () => state;
    state = init(setState, getState);
    const initial = state;
    const hook = (sel) => (sel ? sel(state) : state);
    hook.getState = getState;
    hook.setState = setState;
    hook.getInitialState = () => initial;
    hook.subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };
    return hook;
  };
}

function makeStorage(seed = {}) {
  const m = new Map(Object.entries(seed));
  return {
    map: m,
    default: {
      getItem: async (k) => (m.has(k) ? m.get(k) : null),
      setItem: async (k, v) => { m.set(k, v); },
      removeItem: async (k) => { m.delete(k); },
      getAllKeys: async () => [...m.keys()],
      multiRemove: async (ks) => { for (const k of ks) m.delete(k); },
    },
  };
}

const tick = () => new Promise((r) => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 8; i += 1) await tick(); };

async function check(name, fn) {
  try {
    await fn();
    pass.push(name);
  } catch (e) {
    fail.push(`${name}\n      ${e && e.message ? e.message : e}`);
  }
}
function assert(cond, msg) { if (!cond) throw new Error(msg); }

let qcore = null;
try { qcore = require('@tanstack/query-core'); } catch { /* reported below */ }

// ── useSession, executed against a recording reset ─────────────────────────
function sessionHarness() {
  const log = [];
  let tokenCleared = false;
  const storage = makeStorage();
  const S = load('src/state/useSession.ts', {
    zustand: { create: makeCreate() },
    '@react-native-async-storage/async-storage': storage,
    '../api/client': {
      api: { post: async () => ({}) }, ApiError: class ApiError extends Error {},
      clearSessionToken: async () => { await tick(); tokenCleared = true; log.push('token-cleared'); },
      getSessionRevision: () => 0, getSessionToken: async () => 'tok',
      isCurrentSessionExpiry: () => false, requestAborted: () => new Error('aborted'), runWithDeadline: (fn) => fn(),
      setOnSessionExpired: () => {}, setOnVerificationRequired: () => {},
    },
    '../api/auth': {
      initLeagueSession: async () => {}, refreshVerification: async () => {},
      startDemoSession: async () => ({ user_id: 'demo_user_1', league_id: 'demo_league', display_name: 'Demo', league_name: 'Demo League' }),
    },
    '../api/winNow': { getSeasonProjections: async () => ({}) },
    './leagueSession': {
      LEAGUE_ATTEMPT_MS: 1000,
      createLeagueSessionLifecycle: () => ({
        invalidate() {}, currentGeneration: () => 0, capture: async () => ({}), ensure: async () => {},
        onSuperseded: () => () => {}, reserveSelectionAuthorization: () => 0,
      }),
    },
    '../api/league': { connectLeague: async () => ({}) },
    '../api/sleeper': { getLeagues: async () => [] },
    '../api/purchases': { initPurchases: async () => {} },
    './subscriptionSession': { purchasesIdentityTarget: () => null },
    '../observability/sentry': { setUser: () => {} },
    './queryClient': { queryClient: { invalidateQueries() {} }, seedLeagueSessionCaches() {} },
    './devicePageStore': { clearDevicePages: async () => {} },
    '../utils/tradeInputChange': { noteTradeInputChange: () => {} },
    '../api/rankings': { getActiveScoringFormat: async () => null },
    './accountReset': { resetAccountState: async () => { log.push(tokenCleared ? 'reset-after-token' : 'reset-before-token'); } },
  });
  return { S: S.useSession, log, resetCount: () => log.filter((l) => l.startsWith('reset')).length };
}
const userA = { user_id: 'A', username: 'alpha', display_name: 'A', avatar_id: null };
const userB = { user_id: 'B', username: 'bravo', display_name: 'B', avatar_id: null };

// ── accountReset, executed on the real QueryClient + real stores ────────────
function resetHarness() {
  const storage = makeStorage({
    REACT_QUERY_OFFLINE_CACHE: '{"clientState":{"queries":[{"queryKey":["progress","L1"]}]}}',
    'ftf.entitlements.v1': '{"pro":true}',
    'ftf_tiers_saved_cache_v1': '{"saved":["QB"]}',
    'ftf:tradecalc:v1': '{"liveSendIds":["4034"]}',
    'ftf_anchor_done_v1_sf_tep': '["QB"]',
    // device-level keys the reset must KEEP
    feature_flags_v1: '{}', ftf_onboarding_state_v1: '{}', ftf_rank_method_pref: 'trio',
    ftf_whats_new_seen_version: '1.13.2', ftf_trade_queue_A: '{}',
  });
  const session = makeCreate()(() => ({ user: userA, hasToken: true, verification: null }));
  const sessionMod = { useSession: session };
  let fetches = 0;
  let serverPro = false;
  const ent = load('src/state/useEntitlements.ts', {
    zustand: { create: makeCreate() },
    '@react-native-async-storage/async-storage': storage,
    '../api/billing': { getEntitlements: async () => { fetches += 1; return { pro: serverPro, enforcing: true }; } },
    '../api/purchases': { currentIdentityUserId: () => null, hasProEntitlement: () => false, onCustomerInfoChange: () => () => {}, setOnPurchasesReady: () => {} },
    './subscriptionSession': { customerInfoApplies: () => false },
    './useSession': sessionMod,
  });
  const team = load('src/state/teamReviewCompletion.ts', {
    zustand: { create: makeCreate() }, '@react-native-async-storage/async-storage': storage, './useSession': sessionMod,
  });
  const roster = load('src/state/rosterSetup.ts', {
    zustand: { create: makeCreate() }, '@react-native-async-storage/async-storage': storage, './useSession': sessionMod,
  });
  const qc = load('src/state/queryClient.ts', { '@tanstack/react-query': qcore });
  let quicksetCleared = 0;
  const queue = makeCreate()(() => ({ byLeague: { L1: [{ trade_id: 't1' }] }, hydrated: true }));
  const dismissed = makeCreate()(() => ({ byLeague: { L1: ['t9'] } }));
  const claims = makeCreate()(() => ({ keys: new Set(['L1:4034']) }));
  const notifs = makeCreate()((set) => ({ items: [{ id: 'n1' }], unreadCount: 1, clear: () => set({ items: [], unreadCount: 0 }) }));
  const premium = makeCreate()(() => ({ stamps: { fp: 'x' }, hydrated: true }));
  const reset = load('src/state/accountReset.ts', {
    '@react-native-async-storage/async-storage': storage,
    './queryClient': qc,
    './presentationDismissed': { usePresentationDismissed: dismissed },
    './claimsPending': { useClaimsPending: claims },
    './useNotifications': { useNotifications: notifs },
    './premiumImport': { usePremiumImport: premium },
    './useEntitlements': ent,
    './quicksetProgress': { clearQuicksetProgress: () => { quicksetCleared += 1; } },
    './useTradeQueue': { useTradeQueue: queue },
    './teamReviewCompletion': team,
    './rosterSetup': roster,
  });
  return {
    storage, session, ent, team, roster, qc: qc.queryClient, reset,
    queue, dismissed, claims, notifs, premium,
    fetches: () => fetches, setServerPro: (v) => { serverPro = v; }, quicksetCleared: () => quicksetCleared,
  };
}

(async () => {
  // ═══ 1. Every sign-out path reaches the reset ═══════════════════════════
  await check('1a. src/state/accountReset.ts exists and exports resetAccountState', () => {
    assert(exists('src/state/accountReset.ts'), 'no src/state/accountReset.ts — sign-out has no central reset');
    assert(/export async function resetAccountState\(/.test(read('src/state/accountReset.ts')), 'resetAccountState not exported');
  });

  await check('1b. [executed] useSession.signOut calls the reset exactly once, AFTER the session token is cleared', async () => {
    const h = sessionHarness();
    h.S.setState({ user: userA, league: { league_id: 'L1', league_name: 'L' }, hasToken: true });
    await h.S.getState().signOut();
    assert(h.resetCount() === 1, `reset ran ${h.resetCount()} time(s) on sign-out (want 1)`);
    assert(h.log.includes('reset-after-token'), `the reset ran before the token was gone (${h.log.join(', ')}) — an on-screen refetch could put the old account's answer back`);
    assert(h.S.getState().user === null && h.S.getState().hasToken === false, 'signOut did not end the session');
  });

  await check('1c. [executed] a sign-in as a DIFFERENT account resets; the first sign-in and the same account do not', async () => {
    const h = sessionHarness();
    await h.S.getState().setUser(userA);
    assert(h.resetCount() === 0, 'null → A (a first sign-in) reset the new account\'s state');
    await h.S.getState().setUser({ ...userA, display_name: 'A again' });
    assert(h.resetCount() === 0, 'A → A reset (a re-auth of the same account must keep its cache)');
    await h.S.getState().setUser(userB);
    assert(h.resetCount() === 1, `A → B reset ${h.resetCount()} time(s) (want 1) — an expiry then someone else's sign-in would inherit A's state`);
  });

  await check('1d. [executed] a demo started over another account resets', async () => {
    const h = sessionHarness();
    h.S.setState({ user: userA });
    await h.S.getState().startDemoSession();
    assert(h.resetCount() === 1, `demo over A reset ${h.resetCount()} time(s) (want 1)`);
  });

  // Every UI sign-out goes through the store's signOut — nobody signs out
  // by clearing storage or the token on their own.
  const files = [];
  (function walk(dir) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.(ts|tsx)$/.test(e.name)) files.push(p);
    }
  })(SRC);
  const rel = (p) => path.relative(ROOT, p).split(path.sep).join('/');

  await check('1e. [shape] every signOut() call in src is useSession\'s signOut (store selector or getState)', () => {
    const callers = [];
    for (const f of files) {
      const s = strip(fs.readFileSync(f, 'utf8'));
      if (rel(f) === 'src/state/useSession.ts') continue;
      if (!/\bsignOut\s*\(/.test(s)) continue;
      callers.push(rel(f));
      const viaStore = /useSession\(\s*\(s\)\s*=>\s*s\.signOut\s*\)/.test(s) || /useSession\.getState\(\)\.signOut\(\)/.test(s);
      assert(viaStore, `${rel(f)} calls signOut() that is not useSession's`);
      assert(!/import[^;]*\bsignOut\b[^;]*from/.test(s), `${rel(f)} imports some other signOut`);
    }
    // The paths named in the defect report must still be among them.
    for (const need of [
      'src/screens/settings/sections/SignOutRow.tsx',        // Settings › Account & data
      'src/screens/settings/sections/AccountDataSection.tsx', // Delete account
      'src/screens/SettingsScreen.tsx',                       // hub-off Settings
      'src/navigation/RootNav.tsx',                           // league picker's Sign out
      'src/screens/TradesScreen.tsx',                         // wrong-account alert
    ]) assert(callers.includes(need), `${need} no longer signs out through useSession.signOut`);
  });

  await check('1f. [shape] only the session store, the API client and the test-profile swap clear the session token', () => {
    const allowed = new Set(['src/api/client.ts', 'src/state/useSession.ts', 'src/state/testProfile.ts']);
    for (const f of files) {
      const s = strip(fs.readFileSync(f, 'utf8'));
      if (/\bclearSessionToken\s*\(/.test(s)) assert(allowed.has(rel(f)), `${rel(f)} clears the session token itself — a sign-out that skips the account reset`);
    }
  });

  await check('1g. [shape] the 401 handler keeps the user (no sign-out), so the next account\'s sign-in is an A → B setUser — which resets (1c)', () => {
    const s = strip(read('src/state/useSession.ts'));
    const h = between(s, 'setOnSessionExpired(() => {', '\n});');
    assert(h, 'setOnSessionExpired handler not found');
    assert(!/signOut\(|user:\s*null/.test(h), 'the 401 handler now signs out / nulls the user; the reset must be wired there too');
  });

  // ═══ 2. What the reset clears ══════════════════════════════════════════
  if (!qcore) {
    fail.push('2. @tanstack/query-core not resolvable — run `npm install` in mobile/ first');
  } else {
    await check('2a. [executed] the reset empties the app\'s QueryClient and drops its persisted copy', async () => {
      const h = resetHarness();
      h.qc.setQueryData(['account'], { sleeper_username: 'alpha' });
      h.qc.setQueryData(['league-summary', 'L1'], { my_rank: 3 });
      h.qc.setQueryData(['league-prefs', 'L1'], { outlook: 'contending' });
      h.qc.setQueryData(['progress', 'L1', 'sf_tep'], { pct: 1 });
      await h.reset.resetAccountState();
      assert(h.qc.getQueryCache().getAll().length === 0, `queries left: ${h.qc.getQueryCache().getAll().map((q) => JSON.stringify(q.queryKey)).join(' ')}`);
      assert(h.qc.getQueryData(['account']) === undefined, 'Settings would still read "@alpha" from [\'account\']');
      assert(!h.storage.map.has('REACT_QUERY_OFFLINE_CACHE'), 'the persisted query cache survived — a cold start would restore A\'s queries');
    });

    await check('2b. [executed] the reset drops the entitlement answer (memory + device cache) and marks it unknown', async () => {
      const h = resetHarness();
      h.ent.useEntitlements.setState({ pro: true, founder: true, enforcing: true, expiresAt: '2027-01-01', loaded: true, optimistic: false });
      await h.reset.resetAccountState();
      const st = h.ent.useEntitlements.getState();
      assert(st.pro === false && st.founder === false && st.expiresAt === null, 'the leaving account\'s Pro survived the reset');
      assert(st.loaded === false, 'loaded stayed true — Settings › Subscription would show "See plans" as if it knew');
      await settle();
      assert(!h.storage.map.has('ftf.entitlements.v1'), 'the entitlement device cache survived');
    });

    await check('2c. [executed] sign-out then a Pro account signs in: the server is asked as soon as it holds a token, and it reads Pro', async () => {
      const h = resetHarness();
      h.ent.initEntitlements();
      await settle();
      const before = h.fetches();
      // sign-out (useSession.signOut): user and token go, then the reset.
      h.session.setState({ user: null, hasToken: false });
      await h.reset.resetAccountState();
      // B signs in: user first, token when its league session is ready.
      h.setServerPro(true);
      h.session.setState({ user: userB });
      h.session.setState({ hasToken: true });
      await settle();
      assert(h.fetches() > before, 'no entitlement fetch after B got a token — "See plans" until the next foreground');
      const st = h.ent.useEntitlements.getState();
      assert(st.pro === true && st.loaded === true, `B reads pro=${st.pro} loaded=${st.loaded}`);
    });

    await check('2d. [executed] an answer for the account that has left is discarded', async () => {
      const h = resetHarness();
      let release;
      const gate = new Promise((r) => { release = r; });
      const slow = load('src/state/useEntitlements.ts', {
        zustand: { create: makeCreate() },
        '@react-native-async-storage/async-storage': h.storage,
        '../api/billing': { getEntitlements: async () => { await gate; return { pro: true }; } },
        '../api/purchases': { currentIdentityUserId: () => null, hasProEntitlement: () => false, onCustomerInfoChange: () => () => {}, setOnPurchasesReady: () => {} },
        './subscriptionSession': { customerInfoApplies: () => false },
        './useSession': { useSession: h.session },
      });
      const inflight = slow.useEntitlements.getState().refresh();
      h.session.setState({ user: userB });
      release();
      await inflight;
      assert(slow.useEntitlements.getState().pro === false, 'A\'s in-flight Pro answer landed in B\'s store');
    });

    await check('2e. [executed] the reset clears the in-memory per-account stores and the listed device keys, and keeps device preferences', async () => {
      const h = resetHarness();
      await h.reset.resetAccountState();
      assert(h.quicksetCleared() === 1, 'quickset snapshot not cleared');
      assert(Object.keys(h.queue.getState().byLeague).length === 0 && h.queue.getState().hydrated === false, 'trade queue memory kept');
      assert(Object.keys(h.dismissed.getState().byLeague).length === 0, 'dismissed set kept');
      assert(h.claims.getState().keys.size === 0, 'pending claims kept');
      assert(h.notifs.getState().items.length === 0, 'notification feed kept');
      assert(Object.keys(h.premium.getState().stamps).length === 0, 'premium import stamps kept');
      for (const k of ['ftf_tiers_saved_cache_v1', 'ftf:tradecalc:v1', 'ftf_anchor_done_v1_sf_tep']) {
        assert(!h.storage.map.has(k), `${k} survived the reset`);
      }
      for (const k of ['feature_flags_v1', 'ftf_onboarding_state_v1', 'ftf_rank_method_pref', 'ftf_whats_new_seen_version', 'ftf_trade_queue_A']) {
        assert(h.storage.map.has(k), `${k} (device-level or already account-keyed) was removed`);
      }
    });

    // ═══ 3. Team review "done" (and roster setup) are per account ═════════
    await check('3a. [executed] Team review completion marked by B is not "done" for C in the same league', async () => {
      const h = resetHarness();
      h.session.setState({ user: userB });
      await h.team.useTeamReviewCompletion.getState().hydrate();
      h.team.useTeamReviewCompletion.getState().mark('L1');
      await settle();
      assert(h.team.useTeamReviewCompletion.getState().byLeague.L1 === true, 'B\'s mark did not land');
      // B signs out (a mounted card may call hydrate with no user); C signs in.
      h.session.setState({ user: null });
      await h.reset.resetAccountState();
      await h.team.useTeamReviewCompletion.getState().hydrate();
      assert(h.team.useTeamReviewCompletion.getState().hydrated === false, 'a hydrate with no account marked the store hydrated — the next account would never read its own map');
      h.session.setState({ user: { ...userB, user_id: 'C' } });
      assert(h.team.useTeamReviewCompletion.getState().hydrated === false, 'the store stayed hydrated for B — the card would read B\'s map');
      await h.team.useTeamReviewCompletion.getState().hydrate();
      assert(!h.team.useTeamReviewCompletion.getState().byLeague.L1, 'C reads "Team review · done" for B\'s review');
      // B comes back: still done.
      await h.reset.resetAccountState();
      h.session.setState({ user: userB });
      await h.team.useTeamReviewCompletion.getState().hydrate();
      assert(h.team.useTeamReviewCompletion.getState().byLeague.L1 === true, 'B lost its own completion');
    });

    await check('3b. [executed] the pre-split device-wide map is adopted once by the first account, then gone', async () => {
      const h = resetHarness();
      h.storage.map.set('ftf_team_review_completed', JSON.stringify({ L1: true }));
      h.session.setState({ user: userA });
      await h.team.useTeamReviewCompletion.getState().hydrate();
      assert(h.team.useTeamReviewCompletion.getState().byLeague.L1 === true, 'an updated device forgot its completed review');
      assert(!h.storage.map.has('ftf_team_review_completed'), 'the device-wide map is still there for the next account');
      await h.reset.resetAccountState();
      h.session.setState({ user: userB });
      await h.team.useTeamReviewCompletion.getState().hydrate();
      assert(!h.team.useTeamReviewCompletion.getState().byLeague.L1, 'a second account inherited the adopted map');
    });

    await check('3c. [executed] roster-first setup records are per account the same way', async () => {
      const h = resetHarness();
      h.session.setState({ user: userB });
      await h.roster.useRosterSetup.getState().hydrate();
      h.roster.useRosterSetup.getState().write('L1', { status: 'done', seenAssetIds: ['4034'] });
      await settle();
      await h.reset.resetAccountState();
      h.session.setState({ user: { ...userB, user_id: 'C' } });
      await h.roster.useRosterSetup.getState().hydrate();
      assert(!h.roster.useRosterSetup.getState().byLeague.L1, 'C reads B\'s roster-setup record (and B\'s roster)');
    });
  }

  await check('3d. [shape] the Team review card and the roster-setup readers re-hydrate when the reset un-hydrates their store', () => {
    const card = strip(read('src/components/TeamReviewEntryCard.tsx'));
    assert(/void useTeamReviewCompletion\.getState\(\)\.hydrate\(\);\s*\}, \[hydrated, userId\]\)/.test(card), 'TeamReviewEntryCard hydrates once per mount only');
    assert(/collapsedKey\(userId\)/.test(card), 'the "Not now" collapse is still device-wide');
    const trig = strip(read('src/hooks/useRosterSetupPassTrigger.ts'));
    assert(/\}, \[enabled, hydrated, userId\]\)/.test(trig), 'useRosterSetupPassTrigger hydrates once per enable only');
    const rcard = strip(read('src/components/RosterSetupEntryCard.tsx'));
    assert(/void useRosterSetup\.getState\(\)\.hydrate\(\);\s*\}, \[hydrated, userId\]\)/.test(rcard), 'RosterSetupEntryCard hydrates once per mount only');
  });

  // ═══ 4. Verify row hidden for a verified session ═══════════════════════
  await check('4a. [shape] "Verify account" renders only while THIS session is not verified, on both Settings surfaces', () => {
    for (const f of ['src/screens/settings/sections/AccountIdentitySection.tsx', 'src/screens/SettingsScreen.tsx']) {
      const s = strip(read(f));
      const at = s.indexOf('>Verify account<');
      assert(at > 0, `${f}: no Verify account row`);
      const before = s.slice(Math.max(0, at - 900), at);
      const cond = before.lastIndexOf('{!user?.account_only');
      assert(cond >= 0, `${f}: the row's condition was not found`);
      assert(/^\{!user\?\.account_only && verification\?\.session_verified !== true \? \(/.test(before.slice(cond)),
        `${f}: the row is not gated on verification?.session_verified !== true — a verified account is asked to verify again`);
    }
  });

  // ═══ 5. Sign out asks first ════════════════════════════════════════════
  await check('5a. [executed] confirmSignOut asks with Cancel + a destructive Sign out, and signs out only on that button', () => {
    const calls = [];
    const mod = load('src/screens/settings/sections/SignOutRow.tsx', {
      react: { createElement: () => null, Fragment: 'Fragment' },
      'react-native': { View: 'View', Text: 'Text', Pressable: 'Pressable', Alert: { alert: (...a) => calls.push(a) } },
      '../../../theme/chalkline': { space: { xxl: 0 } },
      '../../../state/useSession': { useSession: () => () => {} },
      '../styles': { styles: {} },
    });
    assert(typeof mod.confirmSignOut === 'function', 'no confirmSignOut export');
    let confirmed = 0;
    mod.confirmSignOut(() => { confirmed += 1; });
    assert(calls.length === 1 && confirmed === 0, 'signed out before the user answered');
    const buttons = calls[0][2] || [];
    const cancel = buttons.find((b) => b.style === 'cancel');
    const go = buttons.find((b) => b.style === 'destructive');
    assert(cancel && !cancel.onPress, 'no inert Cancel');
    assert(go && /Sign out/.test(go.text), 'no destructive "Sign out" button');
    go.onPress();
    assert(confirmed === 1, 'the destructive button did not sign out');
  });

  await check('5b. [shape] both Settings sign-out rows go through confirmSignOut', () => {
    const row = strip(read('src/screens/settings/sections/SignOutRow.tsx'));
    assert(/onPress=\{\(\) => confirmSignOut\(async \(\) => \{\s*await signOut\(\);\s*onSignedOut\(\);/.test(row), 'SignOutRow signs out on a single tap');
    const legacy = strip(read('src/screens/SettingsScreen.tsx'));
    const block = between(legacy, 'const signOutBlock = (', '\n  );');
    assert(/onPress=\{\(\) => confirmSignOut\(async \(\) => \{\s*await signOut\(\);\s*toSignIn\(\);/.test(block), 'the hub-off Settings list signs out on a single tap');
  });

  // ═══ 6. Entitlements are asked for whenever a signed-in user's answer is not held ═══
  // (follow-up, 2026-11-22: a FRESH INSTALL's first sign-in never asked —
  // boot's cache hydrate marked the empty store loaded, and the only asks
  // were the A → B branch, the token edge gated on !loaded, and foreground.)
  function entHarness({ cache = null, session = { user: null, hasToken: false, verification: null }, answer = { pro: true, enforcing: true } } = {}) {
    const storage = makeStorage(cache ? { 'ftf.entitlements.v1': JSON.stringify(cache) } : {});
    const store = makeCreate()(() => ({ ...session }));
    let fetches = 0;
    let release = null;
    let hold = false;
    const ent = load('src/state/useEntitlements.ts', {
      zustand: { create: makeCreate() },
      '@react-native-async-storage/async-storage': storage,
      '../api/billing': { getEntitlements: async () => {
        fetches += 1;
        if (hold) await new Promise((r) => { release = r; });
        return typeof answer === 'function' ? answer() : answer;
      } },
      '../api/purchases': { currentIdentityUserId: () => null, hasProEntitlement: () => false, onCustomerInfoChange: () => () => {}, setOnPurchasesReady: () => {} },
      './subscriptionSession': { customerInfoApplies: () => false },
      './useSession': { useSession: store },
    });
    return { ent, store, storage, fetches: () => fetches, holdNext: () => { hold = true; }, release: () => { hold = false; release && release(); } };
  }
  const E = (h) => h.ent.useEntitlements.getState();

  for (const [label, steps] of [
    ['user, then token (Apple / typed sign-in: setUser, then setLeague)', [{ user: userB }, { hasToken: true }]],
    ['token, then user (separate updates)', [{ hasToken: true }, { user: userB }]],
    ['user and token in one update (demo / account-only)', [{ user: userB, hasToken: true }]],
  ]) {
    await check(`6a. [executed] fresh install, no token, no cache — first sign-in, ${label}: exactly one entitlement request, and a Pro answer reads Pro`, async () => {
      const h = entHarness();
      h.ent.initEntitlements();
      await settle();
      assert(h.fetches() === 0, `boot with no session asked ${h.fetches()} time(s)`);
      const bootLoaded = E(h).loaded;
      for (const st of steps) { h.store.setState(st); await settle(); }
      h.store.setState({ leagues: [] }); await settle();          // later unrelated session updates
      h.store.setState({ verification: { session_verified: true } }); await settle();
      assert(h.fetches() === 1, `asked ${h.fetches()} time(s) after the sign-in (want exactly 1)`);
      assert(E(h).pro === true && E(h).loaded === true && E(h).answerFor === 'B', `B reads pro=${E(h).pro} loaded=${E(h).loaded} answerFor=${E(h).answerFor}`);
      assert(bootLoaded === false, 'boot with nothing to load marked the store loaded — "nothing" would read as an answer');
    });
  }

  await check('6b. [executed] sendPreCheck while this user\'s answer is unknown: no "not enforcing" fall-through — it asks once, then re-runs the pre-check on the answer', async () => {
    const src = read('src/components/SendInSleeperButton.tsx');
    const sf = ts.createSourceFile('x.tsx', src, ts.ScriptTarget.ES2019, true, ts.ScriptKind.TSX);
    let node = null;
    (function find(n) { if (ts.isFunctionDeclaration(n) && n.name && n.name.text === 'sendPreCheck') node = n; else ts.forEachChild(n, find); })(sf);
    assert(node, 'sendPreCheck not found');
    const js = ts.transpileModule(node.getText(sf).replace(/^export\s+/, ''), { compilerOptions: { target: ts.ScriptTarget.ES2019 } }).outputText;
    const run = (st, after) => {
      const opened = [];
      let refreshed = 0;
      const deps = {
        useFeatureFlags: { getState: () => ({ flags: { 'monetize.paywall': true } }) },
        useEntitlements: { getState: () => ({ ...st, refresh: async () => { refreshed += 1; Object.assign(st, after); } }) },
        isUnverifiedSession: () => false,
        openVerify: async () => 'dismissed',
        openPaywall: (p) => { opened.push(p.kind); },
      };
      // eslint-disable-next-line no-new-func
      const pre = new Function(...Object.keys(deps), `${js}\nreturn sendPreCheck;`)(...Object.values(deps));
      return { pre, opened, refreshed: () => refreshed };
    };
    // unknown → enforcing, not Pro: the paywall, never "Connect Sleeper first"
    let resumed = 0;
    let r = run({ loaded: false, enforcing: false, pro: false }, { loaded: true, enforcing: true, pro: false });
    assert(r.pre(() => { resumed += 1; }) === true, 'an unknown answer was treated as not enforcing: the send went straight on');
    await settle();
    assert(r.refreshed() === 1, `asked ${r.refreshed()} time(s)`);
    assert(r.opened.join() === 'send' && resumed === 0, `opened=${r.opened.join()} resumed=${resumed}`);
    // unknown → Pro: the tap resumes once
    resumed = 0;
    r = run({ loaded: false, enforcing: false, pro: false }, { loaded: true, enforcing: true, pro: true });
    r.pre(() => { resumed += 1; }); await settle();
    assert(resumed === 1 && r.opened.length === 0, `Pro: resumed=${resumed} opened=${r.opened.join()}`);
    // still unknown after the one ask (offline): the send goes on, no second ask
    resumed = 0;
    r = run({ loaded: false, enforcing: false, pro: false }, {});
    r.pre(() => { resumed += 1; }); await settle();
    assert(resumed === 1 && r.refreshed() === 1, `offline: resumed=${resumed} asks=${r.refreshed()}`);
  });

  await check('6c. [executed] boot with a restored session asks exactly once — with this user\'s cache, with none, and with another user\'s cache (which is not shown as an answer)', async () => {
    const restored = { user: userA, hasToken: true, verification: null };
    const now = Date.now();
    for (const [label, cache, loadedBeforeAnswer] of [
      ['own cache', { pro: true, expiresAt: null, fetchedAt: now, userId: 'A' }, true],
      ['pre-split cache (no userId)', { pro: true, expiresAt: null, fetchedAt: now }, true],
      ['no cache', null, false],
      ['another user\'s cache', { pro: true, expiresAt: null, fetchedAt: now, userId: 'Z' }, false],
    ]) {
      const h = entHarness({ cache, session: restored, answer: { pro: false, enforcing: true } });
      h.holdNext();
      h.ent.initEntitlements();
      await settle();
      assert(h.fetches() === 1, `${label}: boot asked ${h.fetches()} time(s) (want 1)`);
      assert(E(h).loaded === loadedBeforeAnswer, `${label}: loaded=${E(h).loaded} before the answer (want ${loadedBeforeAnswer})`);
      if (label === 'another user\'s cache') assert(E(h).pro === false, 'another user\'s cached Pro was shown');
      h.release(); await settle();
      h.store.setState({ leagues: [] }); await settle();
      assert(h.fetches() === 1, `${label}: asked again on an unrelated update (${h.fetches()})`);
      assert(E(h).loaded === true && E(h).pro === false, `${label}: the server's answer did not land`);
    }
  });

  await check('6d. [executed] verification completing asks once more; sign-out then the same account again asks again; a failed ask is not an answer', async () => {
    const h = entHarness({ session: { user: userB, hasToken: true, verification: { session_verified: false } }, answer: { pro: false, enforcing: true } });
    h.ent.initEntitlements(); await settle();
    assert(h.fetches() === 1, `boot asked ${h.fetches()}`);
    h.store.setState({ verification: { session_verified: true } }); await settle();
    assert(h.fetches() === 2, `verify edge: ${h.fetches()} (want 2)`);
    h.store.setState({ user: null, hasToken: false }); await settle();
    h.store.setState({ user: userB }); h.store.setState({ hasToken: true }); await settle();
    assert(h.fetches() === 3, `B again after a sign-out: ${h.fetches()} (want 3)`);
    // A failed ask for a new user leaves the answer unknown.
    const f = entHarness({ answer: () => { throw new Error('offline'); } });
    f.ent.initEntitlements(); await settle();
    f.store.setState({ user: userB, hasToken: true }); await settle();
    assert(f.fetches() === 1 && E(f).loaded === false, `offline first sign-in: asks=${f.fetches()} loaded=${E(f).loaded}`);
  });

  finished = true;
  console.log(`\ncheck-signout-reset: ${pass.length} passed, ${fail.length} failed`);
  for (const p of pass) console.log(`  ✓ ${p}`);
  if (fail.length) {
    console.error('\nFAILURES:');
    for (const f of fail) console.error(`  ✗ ${f}`);
    process.exit(1);
  }
})().catch((e) => {
  finished = true;
  console.error(`check-signout-reset crashed: ${e && e.stack ? e.stack : e}`);
  process.exit(1);
});
