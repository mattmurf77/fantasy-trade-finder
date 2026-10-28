#!/usr/bin/env node
// Referral loop v1 — the invite link, the mint, and the invite id `t`
// (PRD FR-1, FR-2, FR-10; scope §3 items 1, 2, 3, 6, 7; analytics addendum
// PR #350 C1/C3).
//
// WHY THIS EXISTS. Every invite in the app goes through ONE function,
// InviteLeaguematesBanner's shareInvite, and the URL it emits is the whole
// attribution design: with `growth.referral_ledger` on it must carry the
// minted id `t` and NEVER the inviter's username (`ref`), and with the flag
// off it must be byte-identical to every link already sitting in a league
// chat. Each way this goes wrong is silent:
//   * a flag-off URL that drifts breaks links in the wild (AC-1a);
//   * a flag-on URL that still carries `ref=` leaks the username the id
//     exists to replace (FR-2);
//   * an event fired out of order hides the share-sheet abandon rate, and a
//     second tap during the 2 s mint opens two sheets and mints twice
//     (AC-1d, AC-1e);
//   * a malformed `t` stored from a link would ride into session init, and a
//     prop key containing "token" is dropped by ingest behind a 200 (C1).
//
// HOW. Sections A-E TRANSPILE AND EXECUTE the real shareInvite /
// buildInviteUrl (components/InviteLeaguematesBanner.tsx), the real mint
// client (api/invite.ts) and the real id rule (utils/inviteId.ts) under
// plain node, with stubs for React Native, the flag store, the session
// store, track() and the share sheet, and fake timers for the 2 s deadline.
// Sections F-H are STATIC (TypeScript AST over deepLinks.ts,
// LeagueJoinScreen.tsx, LeaguePickerScreen.tsx and useSession.ts).
//
// HONEST LABEL (G-035): F-H prove the presence of exact wirings, not
// runtime behaviour — handleDeepLink is not executed here (it needs
// expo-linking's real parser). The TestFlight checklist covers that leg.
//
// Run: node tests/check-invite-links.js   (or: npm run test:invite-links)

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

const SRC = path.join(__dirname, '..', 'src');
// AC-3: no invite share text names the old product, in any spacing or case
// (the web SMS line said "fantasy trade finder", the X line "@FantasyTradeFinder").
const OLD_NAME = /(dynasty|fantasy)\s*trade\s*finder/i;
const read = (rel) => fs.readFileSync(path.join(SRC, rel), 'utf8');

let failures = 0;
const ok = (n) => console.log(`PASS  ${n}`);
const fail = (n, why) => { failures += 1; console.error(`FAIL  ${n}\n      ${why}`); };
const check = (n, cond, why) => (cond ? ok(n) : fail(n, why));
const eq = (n, actual, expected) =>
  check(n, JSON.stringify(actual) === JSON.stringify(expected),
        `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

/** Transpile a real module and run it with an explicit import table. */
function load(rel, imports, globals = {}) {
  const js = ts.transpileModule(read(rel), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2019,
      jsx: ts.JsxEmit.React,
      esModuleInterop: false,
    },
    fileName: rel,
  }).outputText;
  const mod = { exports: {} };
  const names = Object.keys(globals);
  new Function('module', 'exports', 'require', ...names, js)(
    mod, mod.exports,
    (name) => {
      if (Object.prototype.hasOwnProperty.call(imports, name)) return imports[name];
      throw new Error(`${rel} gained an import this guard does not stub: "${name}"`);
    },
    ...names.map((k) => globals[k]),
  );
  return mod.exports;
}

const ID = 'Ab3dEf6hIj9k';                 // the minted shape: 12 URL-safe chars
const BASE = 'https://ftf.test';
const LEAGUE = '1180234567890123456';
const USER = 'tere sa';                     // a space, so encoding is exercised

// ── A. utils/inviteId — the one shape rule ───────────────────────────────
const inviteIdMod = load('utils/inviteId.ts', {});
{
  const { isInviteId, INVITE_ID_RE } = inviteIdMod;
  eq('A1 INVITE_ID_RE is ^[A-Za-z0-9_-]{8,64}$', String(INVITE_ID_RE), '/^[A-Za-z0-9_-]{8,64}$/');
  const good = [ID, 'a'.repeat(8), 'a'.repeat(64), '_-AZaz09'];
  const bad = ['a'.repeat(7), 'a'.repeat(65), 'has space1', 'abc$defgh', `${ID}\n`,
               '', null, undefined, 12345678, {}];
  eq('A2 isInviteId accepts well-formed ids', good.map(isInviteId), good.map(() => true));
  eq('A3 isInviteId rejects everything else', bad.map(isInviteId), bad.map(() => false));
}

// ── B. api/invite.ts — mintInviteId never throws, maps every outcome ─────
{
  class ApiError extends Error {
    constructor(status, body, message, isTimeout = false) {
      super(message || `HTTP ${status}`);
      this.status = status; this.body = body; this.isTimeout = isTimeout;
    }
  }
  let next;
  const calls = [];
  const apiRequest = (p, opts) => { calls.push([p, opts]); return next(); };
  const { mintInviteId } = load('api/invite.ts', {
    './client': { apiRequest, ApiError },
    '../utils/inviteId': inviteIdMod,
  });
  const abortErr = () => { const e = new Error('Aborted'); e.name = 'AbortError'; return e; };
  const cases = [
    ['201 with a well-formed id', () => Promise.resolve({ invite_id: ID, league_id: LEAGUE }), { outcome: 'ok', invite_id: ID }],
    ['2xx with a malformed id', () => Promise.resolve({ invite_id: 'bad id!' }), { outcome: 'failed' }],
    ['2xx with no body', () => Promise.resolve(null), { outcome: 'failed' }],
    ['429', () => Promise.reject(new ApiError(429, { error: 'rate_limited' })), { outcome: 'rate_limited' }],
    ['404 (flag dark / route not deployed)', () => Promise.reject(new ApiError(404, { error: 'not_found' })), { outcome: 'failed' }],
    ['403', () => Promise.reject(new ApiError(403, { error: 'not_member' })), { outcome: 'failed' }],
    ['500', () => Promise.reject(new ApiError(500, null)), { outcome: 'failed' }],
    ['client deadline (ApiError isTimeout)', () => Promise.reject(new ApiError(0, null, 'slow', true)), { outcome: 'timeout' }],
    ['caller abort (AbortError)', () => Promise.reject(abortErr()), { outcome: 'timeout' }],
    ['offline (TypeError)', () => Promise.reject(new TypeError('Network request failed')), { outcome: 'failed' }],
  ];
  (async () => {
    for (const [name, impl, expected] of cases) {
      next = impl;
      let got;
      try { got = await mintInviteId({ leagueId: LEAGUE, surface: 'trades_banner' }); }
      catch (e) { got = `THREW ${e && e.message}`; }
      eq(`B mint: ${name}`, got, expected);
    }
    // An abort that lands after the body resolved is still a timeout.
    const ctl = new AbortController();
    next = () => { ctl.abort(); return Promise.resolve({ invite_id: ID }); };
    eq('B mint: signal aborted before the body is read',
       await mintInviteId({ leagueId: LEAGUE, surface: 'notif_empty' }, ctl.signal), { outcome: 'timeout' });
    const [p, opts] = calls[0];
    eq('B mint: POST /api/invite/token with {league_id, surface} (§8.1)',
       [p, opts.method, opts.body], ['/api/invite/token', 'POST', { league_id: LEAGUE, surface: 'trades_banner' }]);
    check('B mint: the caller signal is forwarded', calls[calls.length - 1][1].signal === ctl.signal,
          'mintInviteId must pass its signal to apiRequest');
    runBanner();
  })().catch((e) => { fail('B mint harness', e && e.stack); finish(); });
}

// ── C-E. the banner's shareInvite / buildInviteUrl, executed ─────────────
function runBanner() {
  const state = {};
  const reset = (o = {}) => Object.assign(state, {
    flags: {}, isDemo: false, log: [], timers: [], shareResult: { action: 'sharedAction' },
    shareThrows: false, shareHang: false, mint: () => Promise.resolve({ outcome: 'ok', invite_id: ID }),
    lastSignal: null,
  }, o);
  reset();
  // useInviteBusy's store, captured through the useSyncExternalStore stub.
  const store = { subscribe: null, get: null };
  const anything = new Proxy({}, { get: () => anything });
  const RN = {
    View: 'View', Text: 'Text', Pressable: 'Pressable', ActivityIndicator: 'ActivityIndicator',
    StyleSheet: { create: (o) => o },
    Share: {
      sharedAction: 'sharedAction', dismissedAction: 'dismissedAction',
      share: async ({ message }) => {
        state.log.push(['share', message]);
        state.busyAtShare = store.get ? store.get() : null;
        if (state.shareThrows) throw new Error('sheet failed');
        if (state.shareHang) return new Promise((r) => { state.hung.push(() => r(state.shareResult)); });
        return state.shareResult;
      },
    },
  };
  const banner = load('components/InviteLeaguematesBanner.tsx', {
    react: {
      default: { createElement: () => null },
      useSyncExternalStore: (subscribe, get) => { store.subscribe = subscribe; store.get = get; return get(); },
    },
    'react-native': RN,
    '../theme/chalkline': { ink: anything, chalk: anything, ice: anything, space: anything,
                            radii: anything, type: anything, fonts: anything },
    '../api/client': { getBaseUrl: () => BASE },
    '../api/events': { track: (name, props, screen) => state.log.push(['track', name, props, screen]) },
    '../api/invite': {
      mintInviteId: (args, signal) => { state.log.push(['mint', args]); state.lastSignal = signal; return state.mint(args, signal); },
    },
    '../state/useFeatureFlags': { useFeatureFlags: { getState: () => ({ flags: state.flags }) } },
    '../state/useSession': { useSession: { getState: () => ({ isDemo: state.isDemo }) } },
  }, {
    setTimeout: (fn, ms) => { state.timers.push({ fn, ms, cleared: false }); return state.timers.length; },
    clearTimeout: (id) => { if (state.timers[id - 1]) state.timers[id - 1].cleared = true; },
  });
  const { shareInvite, buildInviteUrl, useInviteBusy } = banner;
  const args = (o = {}) => ({
    leagueId: LEAGUE, username: USER, surface: 'trades_banner',
    notJoined: null, totalMates: null, platform: 'sleeper', screen: 'Trades', ...o,
  });
  const urlOf = (log) => {
    const s = log.find((e) => e[0] === 'share');
    const m = s && /(https:\/\/\S+)/.exec(s[1]);
    return m ? m[1] : null;
  };
  const kinds = (log) => log.map((e) => (e[0] === 'track' ? e[1] : e[0]));
  const shared = (log) => (log.find((e) => e[0] === 'track' && e[1] === 'invite_shared') || [])[2];
  const L = encodeURIComponent(LEAGUE);
  const U = encodeURIComponent(USER);

  (async () => {
    // ── C. AC-1a — ledger flag OFF: today's URLs byte for byte, no call ──
    // The four strings below are what buildInviteUrl emitted before the
    // referral loop (origin/main 712dcbed). They are links in the wild.
    const today = [
      [{}, USER, `${BASE}/?league=${L}&ref=${U}`],
      [{}, null, `${BASE}/?league=${L}`],
      [{ 'growth.invite_join_link': true }, USER, `${BASE}/app/league/join/${L}?ref=${U}`],
      [{ 'growth.invite_join_link': true }, null, `${BASE}/app/league/join/${L}`],
    ];
    for (const ledger of [undefined, false]) {
      for (const [flags, user, expected] of today) {
        const f = { ...flags, ...(ledger === undefined ? {} : { 'growth.referral_ledger': ledger }) };
        reset({ flags: f });
        eq(`C AC-1a buildInviteUrl, ledger ${ledger}, join ${!!flags['growth.invite_join_link']}, ref ${!!user}`,
           buildInviteUrl(LEAGUE, user), expected);
        await shareInvite(args({ username: user }));
        eq(`C AC-1a shareInvite emits the same URL (ledger ${ledger}, join ${!!flags['growth.invite_join_link']}, ref ${!!user})`,
           urlOf(state.log), expected);
        check(`C AC-1a no mint call (ledger ${ledger})`, !kinds(state.log).includes('mint'),
              'the mint must not run while growth.referral_ledger is off');
      }
    }
    reset({ flags: {} });
    await shareInvite(args());
    eq('C AC-1a invite_shared: mint_outcome disabled, no invite_id', shared(state.log),
       { league_id: LEAGUE, surface: 'trades_banner', not_joined: null, total_mates: null,
         platform: 'sleeper', mint_outcome: 'disabled' });
    check('C AC-1a no pending callback without a mint',
          await (async () => { const seen = []; reset(); await shareInvite(args({ onMintPending: (v) => seen.push(v) })); return seen.length === 0; })(),
          'onMintPending fired with no mint in flight');

    // ── D. AC-2 — the 2x2x2 matrix (ledger x join-link x id) per §7.2 ──
    const matrix = [
      [false, 'ok', `${BASE}/?league=${L}&t=${ID}`],
      [false, 'failed', `${BASE}/?league=${L}`],
      [true, 'ok', `${BASE}/app/league/join/${L}?t=${ID}`],
      [true, 'failed', `${BASE}/app/league/join/${L}`],
    ];
    for (const [join, outcome, expected] of matrix) {
      for (const user of [USER, null]) {
        reset({
          flags: { 'growth.referral_ledger': true, ...(join ? { 'growth.invite_join_link': true } : {}) },
          mint: () => Promise.resolve(outcome === 'ok' ? { outcome: 'ok', invite_id: ID } : { outcome: 'failed' }),
        });
        await shareInvite(args({ username: user }));
        const url = urlOf(state.log);
        eq(`D AC-2 ledger on, join ${join}, mint ${outcome}, ref-known ${!!user}`, url, expected);
        check(`D FR-2 no flag-on URL carries ref= (join ${join}, mint ${outcome}, ref-known ${!!user})`,
              url && !/[?&]ref=/.test(url), `got ${url}`);
      }
    }
    for (const outcome of ['failed', 'timeout', 'rate_limited']) {
      reset({ flags: { 'growth.referral_ledger': true }, mint: () => Promise.resolve({ outcome }) });
      await shareInvite(args());
      const s = shared(state.log) || {};
      check(`D AC-1c mint ${outcome}: sheet still opens league-only, mint_outcome ${outcome}, no invite_id`,
            urlOf(state.log) === `${BASE}/?league=${L}` && s.mint_outcome === outcome && !('invite_id' in s),
            `url ${urlOf(state.log)}, props ${JSON.stringify(s)}`);
    }
    reset({ flags: { 'growth.referral_ledger': true } });
    await shareInvite(args());
    eq('D AC-1b mint ok: invite_shared carries invite_id + mint_outcome ok', shared(state.log),
       { league_id: LEAGUE, surface: 'trades_banner', not_joined: null, total_mates: null,
         platform: 'sleeper', invite_id: ID, mint_outcome: 'ok' });
    reset({ flags: { 'growth.referral_ledger': true }, isDemo: true });
    await shareInvite(args());
    check('D demo session: no mint, mint_outcome demo, league-only URL',
          !kinds(state.log).includes('mint') && (shared(state.log) || {}).mint_outcome === 'demo'
            && urlOf(state.log) === `${BASE}/?league=${L}`,
          JSON.stringify(state.log));
    for (const surface of ['league_home', 'matches_empty', 'trades_banner', 'members_overlay', 'notif_empty']) {
      reset({ flags: { 'growth.referral_ledger': true } });
      await shareInvite(args({ surface }));
      eq(`D §8.1 mint body surface for ${surface} is the InviteSurface value`,
         (state.log.find((e) => e[0] === 'mint') || [])[1], { leagueId: LEAGUE, surface });
    }

    // ── E. AC-1d order, the 2 s deadline, and the AC-1e in-flight guard ──
    reset({ flags: { 'growth.referral_ledger': true } });
    await shareInvite(args());
    eq('E AC-1d order: invite_cta_tapped → mint → Share.share → invite_shared',
       kinds(state.log).map((k, i) => (k === 'track' ? state.log[i][1] : k)),
       ['invite_cta_tapped', 'mint', 'share', 'invite_shared']);
    reset({ flags: { 'growth.referral_ledger': true }, shareResult: { action: 'dismissedAction' } });
    await shareInvite(args());
    check('E AC-1d dismissed sheet: no invite_shared', !shared(state.log), JSON.stringify(state.log));
    reset({ flags: { 'growth.referral_ledger': true } });
    await shareInvite(args());
    check('E FR-1 the mint deadline is 2000 ms and is cleared after the mint',
          state.timers.filter((t) => t.ms === 2000).length === 1 && state.timers[0].ms === 2000 && state.timers[0].cleared,
          JSON.stringify(state.timers.map((t) => ({ ms: t.ms, cleared: t.cleared }))));
    check('E ux-5 one 10 000 ms stale-sheet timer per share, cleared when the sheet settles',
          state.timers.filter((t) => t.ms === 10000).length === 1 && state.timers.filter((t) => t.ms === 10000)[0].cleared,
          JSON.stringify(state.timers.map((t) => ({ ms: t.ms, cleared: t.cleared }))));
    reset({
      flags: { 'growth.referral_ledger': true },
      mint: (a, signal) => new Promise((resolve) => signal.addEventListener('abort', () => resolve({ outcome: 'timeout' }))),
    });
    const pending = shareInvite(args());
    await null;
    state.timers[0] && state.timers[0].fn();          // the deadline fires
    await pending;
    check('E FR-1 the deadline aborts the mint signal → timeout, league-only link',
          state.lastSignal && state.lastSignal.aborted && (shared(state.log) || {}).mint_outcome === 'timeout'
            && urlOf(state.log) === `${BASE}/?league=${L}`,
          JSON.stringify(state.log));

    const releases = [];
    reset({ flags: { 'growth.referral_ledger': true }, mint: () => new Promise((r) => { releases.push(r); }) });
    eq('E ux-1 useInviteBusy is false at rest', useInviteBusy(), false);
    const busySeen = [];
    const unsubscribe = store.subscribe(() => busySeen.push(store.get()));
    const pend = [];
    const first = shareInvite(args({ onMintPending: (v) => pend.push(v) }));
    const second = shareInvite(args());                        // a second tap mid-mint
    const third = shareInvite(args({ surface: 'league_home' })); // another surface, same guard
    await null;
    const during = kinds(state.log);
    check('E ux-1 busy is true while the guard holds (taps are being dropped)', store.get() === true,
          'useInviteBusy must read the same value as the AC-1e guard');
    releases.forEach((r) => r({ outcome: 'ok', invite_id: ID }));
    await Promise.all([first, second, third]);
    check('E AC-1e taps while the mint is pending return at once (one tap, one mint)',
          during.filter((k) => k === 'mint').length === 1
            && state.log.filter((e) => e[1] === 'invite_cta_tapped').length === 1,
          JSON.stringify(during));
    check('E AC-1e one share sheet', kinds(state.log).filter((k) => k === 'share').length === 1,
          JSON.stringify(kinds(state.log)));
    eq('E pending state: true then false around the mint', pend, [true, false]);
    eq('E ux-1 subscribers see busy true then false, once each (one tap)', busySeen, [true, false]);
    unsubscribe();
    reset({ flags: {} });
    await shareInvite(args());
    check('E ux-1 busy also holds while the sheet is open with no mint (flag off)',
          state.busyAtShare === true && store.get() === false, `busyAtShare ${state.busyAtShare}`);
    reset({ flags: { 'growth.referral_ledger': true } });
    await shareInvite(args());
    check('E AC-1e the guard is released after a share', kinds(state.log).includes('share'),
          'a tap after a finished share was swallowed');
    reset({ flags: {}, shareThrows: true });
    await shareInvite(args());
    reset({ flags: {} });
    await shareInvite(args());
    check('E AC-1e the guard is released after a failed sheet', kinds(state.log).includes('share'),
          'a tap after a throwing Share.share was swallowed');
    // ux change 5 — a sheet that never settles releases the guard 10 s
    // after it was requested, and a late settle from that stale tap cannot
    // release a newer tap's guard.
    reset({ flags: {}, shareHang: true, hung: [] });
    const stuck = shareInvite(args());
    await null;
    await shareInvite(args());                                  // a tap while the sheet hangs
    const staleTimer = state.timers.find((t) => t.ms === 10000);
    check('E ux-5 a hanging sheet holds the guard until the stale release',
          store.get() === true && kinds(state.log).filter((k) => k === 'share').length === 1 && !!staleTimer,
          JSON.stringify(kinds(state.log)));
    staleTimer && staleTimer.fn();                              // 10 s pass
    check('E ux-5 the stale release frees the guard and the busy state', store.get() === false,
          'the guard stayed held after SHEET_STALE_MS');
    const newer = shareInvite(args());                          // a new tap now owns the guard
    await null;
    state.hung[0]();                                            // the stale sheet finally settles
    await stuck;
    check('E ux-5 a new tap after the release opens a sheet, and the stale settle leaves its guard held',
          kinds(state.log).filter((k) => k === 'share').length === 2 && store.get() === true,
          `shares ${kinds(state.log).filter((k) => k === 'share').length}, busy ${store.get()}`);
    state.hung[1]();
    await newer;
    check('E ux-5 the newer tap releases its own guard', store.get() === false, 'guard leaked');
    reset({ flags: { 'growth.referral_ledger': true } });
    await shareInvite(args());
    const keys = state.log.filter((e) => e[0] === 'track').flatMap((e) => Object.keys(e[2] || {}));
    check('E C1 no emitted invite prop key contains "token"', !keys.some((k) => /token/i.test(k)), keys.join(','));

    // K. AC-3 / copy §6 D — the share text is the approved m3.invite.msg and
    //    never names the old product.
    reset({ flags: {} });
    await shareInvite(args());
    const msg = (state.log.find((e) => e[0] === 'share') || [])[1];
    eq('K m3.invite.msg is the approved line, no league name',
       msg, `Join me on Fleeced to find trades we both like → ${BASE}/?league=${L}&ref=${U}`);
    check('K AC-3 the mobile invite text has no old product name', !OLD_NAME.test(msg || ''), msg);

    runStatic();
  })().catch((e) => { fail('banner harness', e && e.stack); finish(); });
}

// ── F-H. static wiring (AST) ─────────────────────────────────────────────
function sourceOf(rel) {
  return ts.createSourceFile(rel, read(rel), ts.ScriptTarget.Latest, true,
                             rel.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
}
function walk(node, fn) { fn(node); ts.forEachChild(node, (c) => walk(c, fn)); }
/** Every track('<name>', {...}) call → { name, keys (incl. nested spreads) }. */
function trackCalls(sf) {
  const out = [];
  walk(sf, (n) => {
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === 'track'
        && n.arguments[0] && ts.isStringLiteral(n.arguments[0])) {
      const keys = [];
      if (n.arguments[1]) {
        walk(n.arguments[1], (m) => {
          if ((ts.isPropertyAssignment(m) || ts.isShorthandPropertyAssignment(m)) && m.name) {
            keys.push(m.name.getText(sf).replace(/['"]/g, ''));
          }
        });
      }
      out.push({ name: n.arguments[0].text, keys, text: n.getText(sf) });
    }
  });
  return out;
}

function runStatic() {
  // F. INVITE_ID_RE is defined ONCE on mobile, and every reader imports it.
  const files = [];
  (function list(dir) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) list(p);
      else if (/\.(ts|tsx)$/.test(e.name)) files.push(p);
    }
  })(SRC);
  const defs = files.filter((p) => fs.readFileSync(p, 'utf8').includes('[A-Za-z0-9_-]{8,64}'))
    .map((p) => path.relative(SRC, p));
  eq('F INVITE_ID_RE is defined once in mobile/src (utils/inviteId.ts)', defs, ['utils/inviteId.ts']);
  for (const rel of ['utils/deepLinks.ts', 'screens/LeagueJoinScreen.tsx', 'api/invite.ts']) {
    check(`F ${rel} imports isInviteId from utils/inviteId`,
          /import \{ isInviteId \} from '(\.\.\/utils|\.)\/inviteId';/.test(read(rel)),
          'the one shape rule must be imported, never re-implemented');
  }

  // G. `t` is stored only via isInviteId, and only from invite links.
  for (const rel of ['utils/deepLinks.ts', 'screens/LeagueJoinScreen.tsx']) {
    const sf = sourceOf(rel);
    const sets = [];
    let guarded = false;
    walk(sf, (n) => {
      if (ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression)
          && n.expression.name.text === 'setInviteId') sets.push(n.arguments.map((a) => a.getText(sf)));
      if (ts.isVariableDeclaration(n) && n.name.getText(sf) === 'inviteId' && n.initializer
          && ts.isConditionalExpression(n.initializer)
          && /^isInviteId\(/.test(n.initializer.condition.getText(sf))
          && n.initializer.whenFalse.getText(sf) === 'null') guarded = true;
    });
    check(`G ${rel}: setInviteId is called, only with \`inviteId\``,
          sets.length >= 1 && sets.every((a) => a.length === 1 && a[0] === 'inviteId'), JSON.stringify(sets));
    check(`G ${rel}: \`inviteId\` = isInviteId(x) ? x : null`, guarded,
          'the stored value must come from the isInviteId gate');
  }
  check('G deepLinks captures `t` only on an invite link (join path or ?league=)',
        /if \(inviteId && \(isJoinPath \|\| \(typeof lgStr === 'string' && lgStr\.trim\(\)\)\)\) \{\s*useSession\.getState\(\)\.setInviteId\(inviteId\);/
          .test(read('utils/deepLinks.ts')),
        'the setInviteId call in handleDeepLink lost its invite-link condition');
  // The store does not re-validate (useSession stays free of new imports:
  // check-win-now-recovery.js loads it with a closed import table), so the
  // two gated call sites above must be the ONLY writers.
  const writers = files.filter((p) => /\.setInviteId\(/.test(fs.readFileSync(p, 'utf8')))
    .map((p) => path.relative(SRC, p)).sort();
  eq('G setInviteId is called only from the two gated call sites', writers,
     ['screens/LeagueJoinScreen.tsx', 'utils/deepLinks.ts']);

  // H. event props: invite_id where #350 grants it, share_link_opened's row,
  //    and no key containing "token" on any invite/share track() call.
  const calls = {
    'utils/deepLinks.ts': trackCalls(sourceOf('utils/deepLinks.ts')),
    'screens/LeagueJoinScreen.tsx': trackCalls(sourceOf('screens/LeagueJoinScreen.tsx')),
    'screens/LeaguePickerScreen.tsx': trackCalls(sourceOf('screens/LeaguePickerScreen.tsx')),
    'components/InviteLeaguematesBanner.tsx': trackCalls(sourceOf('components/InviteLeaguematesBanner.tsx')),
  };
  const find = (rel, name) => calls[rel].filter((c) => c.name === name);
  for (const [rel, name] of [
    ['utils/deepLinks.ts', 'invite_link_opened'],
    ['screens/LeagueJoinScreen.tsx', 'invite_link_opened'],
    ['screens/LeaguePickerScreen.tsx', 'invite_league_pinned'],
    ['screens/LeaguePickerScreen.tsx', 'invite_pin_failed'],
    ['components/InviteLeaguematesBanner.tsx', 'invite_shared'],
  ]) {
    const c = find(rel, name);
    check(`H ${rel}: ${name} carries invite_id`, c.length === 1 && c[0].keys.includes('invite_id'),
          JSON.stringify(c.map((x) => x.keys)));
  }
  const shareOpened = find('utils/deepLinks.ts', 'share_link_opened');
  eq('H deepLinks: share_link_opened props are exactly {kind, has_ref, auth_state}',
     shareOpened.map((c) => c.keys.slice().sort()), [['auth_state', 'has_ref', 'kind']]);
  const dl = read('utils/deepLinks.ts');
  check("H deepLinks: share_link_opened kinds are 'trade' | 'package' | 'ref_root'",
        /\? 'trade'/.test(dl) && /\? 'package'/.test(dl) && /\? 'ref_root'/.test(dl),
        'the kind enum drifted from the #350 grant');
  const picker = read('screens/LeaguePickerScreen.tsx');
  check('H LeaguePicker reads the id with a peek, never a consume',
        (picker.match(/useSession\.getState\(\)\.inviteId/g) || []).length === 2 && !/consumeInviteId/.test(picker),
        'invite_league_pinned / invite_pin_failed must not consume the id session init needs');
  const tokenKeys = Object.entries(calls).flatMap(([rel, cs]) => cs
    .filter((c) => /^(invite_|share_link_)/.test(c.name))
    .flatMap((c) => c.keys.filter((k) => /token/i.test(k)).map((k) => `${rel} ${c.name}.${k}`)));
  eq('H C1 no invite/share event prop key contains "token"', tokenKeys, []);

  // I. FR-19 — `referral_activated` taps to Trades on both clients, never to
  //    League (the join row keeps League). check-notif-glyphs pins the glyphs.
  const kindSet = (name) => {
    const m = new RegExp(`const ${name} = new Set\\(\\[([\\s\\S]*?)\\]\\)`).exec(dl);
    return m ? [...m[1].matchAll(/'([a-z_]+)'/g)].map((x) => x[1]) : [];
  };
  check('I FR-19 referral_activated is in V2_TRADE_KINDS', kindSet('V2_TRADE_KINDS').includes('referral_activated'),
        `V2_TRADE_KINDS = ${JSON.stringify(kindSet('V2_TRADE_KINDS'))}`);
  check('I FR-19 referral_activated is not in V2_LEAGUE_KINDS / V2_MATCH_KINDS',
        !kindSet('V2_LEAGUE_KINDS').includes('referral_activated') && !kindSet('V2_MATCH_KINDS').includes('referral_activated'),
        'the activation row must route to Trades only');
  const web = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'js', 'app.js'), 'utf8');
  const webTrade = /const TRADE_TYPES\s*=\s*\[([^\]]*)\]/.exec(web);
  check('I FR-19 web clickNotif TRADE_TYPES has referral_activated',
        !!webTrade && webTrade[1].includes("'referral_activated'"), webTrade ? webTrade[0] : 'TRADE_TYPES not found');

  // K (web). AC-3 / copy §6 D — the web invite builders.
  const webFn = (name) => {
    const at = web.indexOf(`\n    function ${name}(`);
    if (at === -1) return '';
    const next = web.indexOf('\n    function ', at + 10);
    return web.slice(at, next === -1 ? web.length : next);
  };
  const inviteMsg = webFn('buildInviteMessage');
  const channelMsg = webFn('buildChannelMessage');
  check('K web m3.app.invite_msg is the approved line',
        inviteMsg.includes('`Join me on Fleeced to find trades we both like → ${url}`'), inviteMsg.trim().split('\n').slice(-3).join(' '));
  check('K web m3.app.invite_sms is the approved line',
        /case 'sms':\s*body = `Join me on Fleeced to find trades we both like → \$\{url\}`;/.test(channelMsg), 'sms body drifted');
  check('K web m3.app.invite_x is the approved line',
        /case 'twitter':\s*body = `Finding dynasty trades in \$\{leagueName\} on Fleeced\. Join me → \$\{url\}`;/.test(channelMsg), 'x body drifted');
  check('K AC-3 no web invite text names the old product',
        !!inviteMsg && !!channelMsg && !OLD_NAME.test(inviteMsg) && !OLD_NAME.test(channelMsg),
        'buildInviteMessage / buildChannelMessage still carry the old name');

  // J. AC-3b — the banner spells it "leaguemates" in every RENDERED string
  //    and accessibility label (comments are not rendered and not checked).
  const bsf = sourceOf('components/InviteLeaguematesBanner.tsx');
  const rendered = [];
  walk(bsf, (n) => {
    if (ts.isJsxText(n) || ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)
        || ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) rendered.push(n.getText(bsf));
  });
  const hyphenated = rendered.filter((t) => /league-mate/i.test(t));
  eq('J AC-3b no "league-mates" in any banner string or a11y label', hyphenated, []);
  check('J AC-3b the a11y label reads "Invite leaguemates"',
        rendered.includes('"Invite leaguemates"'), 'accessibilityLabel changed beyond the respelling');

  // L. ux-lead #364 busy state + design F2 (AC-4b) on the Trades banner's
  //    Invite control. STATIC: the JSX is not rendered here (no RN renderer).
  const bannerSrc = read('components/InviteLeaguematesBanner.tsx');
  const bannerFn = bannerSrc.slice(bannerSrc.indexOf('export default function InviteLeaguematesBanner'));
  check('L ux-1 the banner renders busy from useInviteBusy(), not local state',
        /const busy = useInviteBusy\(\);/.test(bannerFn) && !/useState|onMintPending/.test(bannerFn),
        'the banner must read the shared guard, not a per-call pending flag');
  check('L ux-2 INVITE_BUSY_LABEL is "Preparing invite link", one constant, flagged pending marketing-lead',
        /\/\/ copy: pending marketing-lead\n(?:\/\*\*[\s\S]*?\*\/\n)?export const INVITE_BUSY_LABEL = 'Preparing invite link';/.test(bannerSrc)
          && (bannerSrc.match(/Preparing invite link/g) || []).length === 1,
        'the busy label string must live in the one flagged constant');
  check('L ux-2 busy swaps the a11y label and sets accessibilityState.busy',
        /accessibilityLabel=\{busy \? INVITE_BUSY_LABEL : "Invite leaguemates"\}/.test(bannerFn)
          && /accessibilityState=\{\{ busy \}\}/.test(bannerFn),
        'while busy VoiceOver must hear INVITE_BUSY_LABEL, and the normal label must return after');
  check('L ux-3 fixed width: the label stays in layout (opacity 0) under an absolute-fill spinner',
        /<Text style=\{\[styles\.inviteText, busy && styles\.hidden\]\}>Invite<\/Text>/.test(bannerFn)
          && /\{busy \? \(\s*<View style=\{styles\.spinner\}>\s*<ActivityIndicator/.test(bannerFn)
          && /hidden: \{ opacity: 0 \}/.test(bannerSrc)
          && /spinner: \{\s*\.\.\.StyleSheet\.absoluteFillObject,\s*alignItems: 'center',\s*justifyContent: 'center',/.test(bannerSrc),
        'swapping the label for the spinner narrows the button and reflows the banner');
  check('L ux-4 no pressed fill while busy',
        /pressed && !busy && styles\.inviteBtnPressed/.test(bannerFn),
        'a dropped repeat tap must not flash the pressed fill');
  check('L AC-4b 44pt target: minHeight 36 + 4pt top/bottom hitSlop, minWidth 44',
        /hitSlop=\{\{ top: 4, bottom: 4 \}\}/.test(bannerFn)
          && /inviteBtn: \{\s*minHeight: 36,\s*minWidth: 44,/.test(bannerSrc),
        'the banner Invite button fell under the 44pt touch floor');

  runButtonLoading();
  finish();
}

// ── M. chalkline Button `loading` (design-lead #364), EXECUTED ───────────
// The four Button-based Invite controls show busy through `loading`. It must
// keep the label in layout (invisible) under a centred spinner in the label
// colour, stay inactive (so no pressed fill) and set accessibilityState.busy;
// without `loading` the render is the plain label, as before.
function runButtonLoading() {
  const h = (type, props, ...children) => ({ type, props: props || {}, children });
  const tok = new Proxy({}, { get: (_, k) => new Proxy({}, { get: (_, j) => `${String(k)}.${String(j)}` }) });
  const { default: Button } = load('components/chalkline/Button.tsx', {
    react: { default: { createElement: h, Fragment: 'Fragment' } },
    'react-native': {
      ActivityIndicator: 'ActivityIndicator', Pressable: 'Pressable', View: 'View',
      StyleSheet: { create: (o) => o, absoluteFillObject: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0 } },
    },
    '../../theme/chalkline': tok,
    '../../state/useFeatureFlags': { useFlag: () => false },
    './Text': { default: 'Text' },
    './Icon': { default: 'Icon' },
  });
  const flat = (s) => (Array.isArray(s) ? Object.assign({}, ...s.filter(Boolean).map(flat)) : (s || {}));
  for (const variant of ['primary', 'secondary']) {
    const el = Button({ label: 'Invite leaguemates', variant, loading: true, accessibilityLabel: 'Preparing invite link' });
    const kids = el.children[0]({ pressed: false });
    const parts = kids.type === 'Fragment' ? kids.children : [kids];
    const content = parts.find((p) => p && p.type === 'View' && p.children.some((c) => c && c.type === 'Text'));
    const label = content && content.children.find((c) => c && c.type === 'Text');
    const overlay = parts.find((p) => p && p.type === 'View' && p.children.some((c) => c && c.type === 'ActivityIndicator'));
    const spinner = overlay && overlay.children.find((c) => c && c.type === 'ActivityIndicator');
    const labelColour = label && flat(label.props.style).color;
    check(`M loading (${variant}): the label stays in layout at opacity 0`,
          !!label && label.children.includes('Invite leaguemates') && flat(content.props.style).opacity === 0,
          'the spinner must not replace the label (width jump)');
    const o = overlay ? flat(overlay.props.style) : {};
    check(`M loading (${variant}): a small spinner in the label colour, centred over the label`,
          !!spinner && spinner.props.size === 'small' && spinner.props.color === labelColour
            && o.position === 'absolute' && o.alignItems === 'center' && o.justifyContent === 'center',
          JSON.stringify({ spinner: spinner && spinner.props, labelColour, overlay: o }));
    check(`M loading (${variant}): inactive (no pressed fill), accessibilityState.busy, label passthrough`,
          el.props.disabled === true && el.props.accessibilityState.busy === true
            && el.props.accessibilityLabel === 'Preparing invite link',
          JSON.stringify({ disabled: el.props.disabled, state: el.props.accessibilityState }));
  }
  const idle = Button({ label: 'Invite leaguemates', variant: 'secondary' });
  const idleKids = idle.children[0]({ pressed: false });
  check('M not loading: the plain label, no spinner, no hidden style, busy false',
        idleKids.type === 'View' && flat(idleKids.props.style).opacity === undefined
          && !JSON.stringify(idleKids).includes('ActivityIndicator')
          && idle.props.accessibilityState.busy === false && idle.props.disabled === false,
        JSON.stringify(idleKids).slice(0, 200));
}

// A stalled harness (an awaited promise that never settles) would let node
// exit 0 with nothing printed. That is a failure, not a pass.
process.on('beforeExit', () => {
  if (!finish.done) { fail('harness completes', 'the async checks stalled before reporting'); finish(); }
});

function finish() {
  if (finish.done) return;
  finish.done = true;
  console.log(failures === 0
    ? '\nAll invite-link checks passed.'
    : `\n${failures} check(s) failed.`);
  process.exit(failures === 0 ? 0 : 1);
}
