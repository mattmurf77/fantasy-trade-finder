#!/usr/bin/env node
// Referral loop B7 — SignIn names the inviter from the invite id `t`
// (PRD FR-11 / AC-11 / §8.3; scope §3 item 8; marketing approval row
// `gp.join.headline` + U2; head-eng ruling 2026-10-24).
//
// WHY THIS EXISTS. B1 stops putting the inviter's username (`ref`) in invite
// links, so the only way SignIn can still say who invited you is to send the
// invite id `t` to `GET /api/league/invite-meta` and render the
// SERVER-resolved `inviter_display_name` through the approved four-rung
// headline ladder. The server half is not deployed when this binary ships,
// so each way this goes wrong is silent:
//   * a second invite-meta call site (the P0-3 rail: one call, SignIn's);
//   * a malformed `t` sent upstream, or `t` CONSUMED here instead of peeked
//     (session init must still carry it, B3);
//   * a banner that changes for a server that has never heard of `t`. The
//     head-eng ruling: whenever invite-meta yields no inviter name because of
//     an OLD server, a MISSING/INVALID `t`, or a REQUEST ERROR, the headline
//     is today's ladder EXACTLY. Sign-in never breaks or blanks;
//   * the legacy `?ref=` line drifting by a byte;
//   * a display name or the id itself taken from the URL and rendered.
//
// HOW.
//   A  TRANSPILES AND EXECUTES the real `fetchInviteMeta` (api/league.ts)
//      with a stubbed `api.get`, the real utils/inviteId and fake timers.
//   B  LIFTS the real `inviteHeadlineFor` out of SignInScreen.tsx and runs it
//      over the ladder grid. A reference copy of TODAY'S expression (base
//      441b9766, SignInScreen.tsx:249-255, verbatim) is the oracle for
//      "today's lines".
//   C  LIFTS the real invite-meta EFFECT callback out of SignInScreen.tsx and
//      runs it against the real fetchInviteMeta, a stub server (old shape,
//      §8.3 shape, error, throw, hang) and stub store/state setters. Its
//      output feeds the real ladder, so the ruling's three cases are pinned
//      end to end, minus React.
//   D  STATIC (TypeScript AST): one call site; `t` peeked by selector, never
//      consumed; the inviter state written only from the response; the
//      ladder fed from exactly those three values; the effect's deps; no URL
//      read on the screen.
//
// HONEST LABEL (G-035). C runs the effect body, not React: dep-change re-runs
// and render timing are not executed, which is why D pins the deps array
// and the render wiring as SHAPE. The TestFlight checklist covers runtime.
//
// Run: node tests/check-signin-inviter.js   (or: npm run test:signin-inviter)

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
const SIGNIN = 'screens/SignInScreen.tsx';
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

const parse = (rel) =>
  ts.createSourceFile(rel, read(rel), ts.ScriptTarget.Latest, true,
                      rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
function findAll(node, pred, out = []) {
  if (pred(node)) out.push(node);
  // A block body: forEachChild stops at the first truthy callback return.
  ts.forEachChild(node, (c) => { findAll(c, pred, out); });
  return out;
}
const callsTo = (sf, name) => findAll(sf, (n) =>
  ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === name);
const within = (inner, outer) => inner.pos >= outer.pos && inner.end <= outer.end;
const squash = (s) => s.replace(/\s+/g, ' ').trim();

const flush = () => new Promise((r) => setImmediate(r));

const ID = 'Ab3dEf6hIj9k';                 // the minted shape: 12 URL-safe chars
const LEAGUE = '1180234567890123456';
const LG = 'Dynasty Bros';
const TAIL = " — sign in and we'll take you straight there.";
const BAD_IDS = ['a'.repeat(7), 'a'.repeat(65), 'has space1', 'abc$defgh', `${ID}\n`,
                 'x&t=Ab3dEf6hIj9k', '', null, undefined, 12345678, {}];

// TODAY's headline, verbatim from base 441b9766 SignInScreen.tsx:249-255.
// The oracle for "today's lines" — do NOT edit it to make a red go green.
const today = (invitedBy, invitedLeagueName) => invitedBy
    ? `@${invitedBy} invited you to ${invitedLeagueName || 'their league'} — ` +
      "sign in and we'll take you straight there."
    : invitedLeagueName
    ? `You were invited to ${invitedLeagueName} — ` +
      "sign in and we'll take you straight there."
    : null;

// ── A. api/league.ts — fetchInviteMeta ───────────────────────────────────
const inviteIdMod = load('utils/inviteId.ts', {});
let server = null;                  // (path, opts) => Promise | value; set per case
const apiCalls = [];
const timers = [];
const leagueMod = load('api/league.ts', {
  './client': { api: { get: (p, opts) => { apiCalls.push({ path: p, opts }); return server(p, opts); } } },
  '../utils/inviteId': inviteIdMod,
}, {
  // Fake timers: the 4 s deadline fires only when a case says so.
  setTimeout: (fn, ms) => { timers.push({ fn, ms, live: true }); return timers.length; },
  clearTimeout: (h) => { if (timers[h - 1]) timers[h - 1].live = false; },
});
const { fetchInviteMeta } = leagueMod;

class ApiError extends Error {
  constructor(status) { super(`HTTP ${status}`); this.status = status; }
}
const OLD_BODY = { league_id: LEAGUE, league_name: LG, platform: 'sleeper' };
/** Today's server: ignores `t` entirely. */
const oldServer = () => Promise.resolve({ ...OLD_BODY });
/** PRD §8.3 server: both new keys iff the query carries `t`. */
const newServer = (status, name) => (p) => {
  const m = /[?&]t=([^&]*)/.exec(p);
  if (!m) return Promise.resolve({ ...OLD_BODY });
  return Promise.resolve({ ...OLD_BODY, inviter_display_name: name, invite_status: status });
};
const rejectServer = (err) => () => Promise.reject(err);
const throwServer = () => { throw new TypeError('sync throw inside api.get'); };
const hangServer = (p, opts) => new Promise((_, reject) => {
  opts.signal.addEventListener('abort', () => {
    const e = new Error('Aborted'); e.name = 'AbortError'; reject(e);
  });
});
const TODAY_URL = `/api/league/invite-meta?league_id=${LEAGUE}`;

async function sectionA() {
  // A1 — no `t`: the request is byte-identical to today's, same options.
  server = oldServer; apiCalls.length = 0;
  const r1 = await fetchInviteMeta(LEAGUE);
  eq('A1 no t → today\'s exact URL', apiCalls.map((c) => c.path), [TODAY_URL]);
  check('A1 no t → still skipAuth + an abort signal',
        apiCalls[0] && apiCalls[0].opts.skipAuth === true && !!apiCalls[0].opts.signal,
        JSON.stringify(apiCalls[0] && Object.keys(apiCalls[0].opts)));
  eq('A1 no t → old body returned as-is', r1, OLD_BODY);

  // A2 — a well-formed `t` rides as `&t=`.
  apiCalls.length = 0;
  await fetchInviteMeta(LEAGUE, ID);
  eq('A2 valid t → sent as &t=', apiCalls.map((c) => c.path), [`${TODAY_URL}&t=${ID}`]);

  // A3 — a malformed `t` is NEVER sent; the request is today's.
  const sent = [];
  for (const bad of BAD_IDS) {
    apiCalls.length = 0;
    await fetchInviteMeta(LEAGUE, bad);
    sent.push(apiCalls.map((c) => c.path)[0]);
  }
  eq('A3 invalid t (short, long, space, $, newline, injected &, blank, null, undefined, number, object) → never sent',
     sent, BAD_IDS.map(() => TODAY_URL));

  // A4 — the new fields are returned when present.
  server = newServer('valid', 'Teresa');
  const r4 = await fetchInviteMeta(LEAGUE, ID);
  eq('A4 §8.3 fields returned when present', r4,
     { ...OLD_BODY, inviter_display_name: 'Teresa', invite_status: 'valid' });

  // A5 — never throws: every failure is null.
  const failing = [
    ['500', rejectServer(new ApiError(500))],
    ['404 (route not deployed)', rejectServer(new ApiError(404))],
    ['offline (TypeError)', rejectServer(new TypeError('Network request failed'))],
    ['sync throw inside api.get', throwServer],
  ];
  for (const [label, impl] of failing) {
    server = impl;
    let got;
    try { got = await fetchInviteMeta(LEAGUE, ID); } catch (e) { got = `THREW ${e && e.message}`; }
    eq(`A5 request error → null, no throw (${label})`, got, null);
  }

  // A6 — the 4 s deadline: a hung call aborts and resolves null.
  server = hangServer; timers.length = 0;
  const pending = fetchInviteMeta(LEAGUE, ID);
  await flush();
  const deadline = timers.find((t) => t.live);
  check('A6 a 4000 ms deadline is armed', deadline && deadline.ms === 4000,
        JSON.stringify(timers.map((t) => t.ms)));
  if (deadline) deadline.fn();
  let got6;
  try { got6 = await pending; } catch (e) { got6 = `THREW ${e && e.message}`; }
  eq('A6 deadline → null, no throw', got6, null);

  // A7 — no league id: no call at all.
  server = oldServer; apiCalls.length = 0;
  eq('A7 blank league id → null', await fetchInviteMeta('', ID), null);
  eq('A7 blank league id → no request', apiCalls.length, 0);
}

// ── B. SignInScreen.tsx — the headline ladder, lifted and executed ──────
const signinSf = parse(SIGNIN);
let ladder = null;
function sectionB() {
  const decl = findAll(signinSf, (n) =>
    ts.isFunctionDeclaration(n) && !!n.name && n.name.text === 'inviteHeadlineFor')[0];
  if (!decl) {
    fail('B0 SignInScreen declares a module-level inviteHeadlineFor',
         'the ladder is gone or inlined again; nothing here can execute it');
    return;
  }
  check('B0 inviteHeadlineFor is module-level (liftable)', decl.parent === signinSf,
        'it moved inside the component, where it can close over URL or store values');
  eq('B0 its inputs are exactly (invitedBy, invitedLeagueName, inviter)',
     decl.parameters.map((p) => p.name.getText(signinSf)),
     ['invitedBy', 'invitedLeagueName', 'inviter']);
  try {
    const js = ts.transpileModule(decl.getText(signinSf), {
      compilerOptions: { module: ts.ModuleKind.None, target: ts.ScriptTarget.ES2019 },
    }).outputText;
    // eslint-disable-next-line no-new-func
    ladder = new Function(`'use strict';\n${js}\nreturn inviteHeadlineFor;`)();
    ok('B0 inviteHeadlineFor lifts and compiles with no free variables in scope');
  } catch (e) {
    fail('B0 inviteHeadlineFor lifts and compiles', String(e && e.message));
    return;
  }
  const run = (...a) => {
    try { return ladder(...a); } catch (e) { return `THREW ${e && e.message}`; }
  };

  const NAMES = [LG, null, ''];
  const ANY_META = [
    null,
    { ...OLD_BODY },
    { ...OLD_BODY, inviter_display_name: 'Teresa', invite_status: 'valid' },
    { ...OLD_BODY, inviter_display_name: null, invite_status: 'unknown' },
    { ...OLD_BODY, inviter_display_name: null, invite_status: 'expired' },
    { ...OLD_BODY, inviter_display_name: null, invite_status: 'league_mismatch' },
  ];

  // (a) legacy ref outranks everything, byte-identical to today.
  const aGot = []; const aWant = [];
  for (const lg of NAMES) for (const m of ANY_META) {
    aGot.push(run('teresa', lg, m)); aWant.push(today('teresa', lg));
  }
  eq('B1 (a) legacy ref → today\'s line, byte-identical, whatever the server says', aGot, aWant);
  eq('B1 (a) literal', run('teresa', LG, null),
     "@teresa invited you to Dynasty Bros — sign in and we'll take you straight there.");
  eq('B1 (a) literal, no league name', run('teresa', null, null),
     "@teresa invited you to their league — sign in and we'll take you straight there.");

  // (b) server-resolved name → ladder rungs 1 and 2, tail kept.
  eq('B2 (b) ladder 1: {name} invited you to {league}',
     run(null, LG, ANY_META[2]), `Teresa invited you to Dynasty Bros${TAIL}`);
  eq('B2 (b) ladder 2: {name} invited you to their league',
     run(null, null, ANY_META[2]), `Teresa invited you to their league${TAIL}`);
  eq('B2 (b) a name outranks a no-name status',
     run(null, LG, { ...OLD_BODY, inviter_display_name: 'Teresa', invite_status: 'expired' }),
     `Teresa invited you to Dynasty Bros${TAIL}`);

  // (c) `t` known to the server, no name → ladder rungs 3 and 4.
  for (const st of ['unknown', 'expired', 'league_mismatch']) {
    const m = { ...OLD_BODY, inviter_display_name: null, invite_status: st };
    eq(`B3 (c) ${st} → ladder 3: A leaguemate invited you to {league}`,
       run(null, LG, m), `A leaguemate invited you to Dynasty Bros${TAIL}`);
    eq(`B3 (c) ${st} → ladder 4: A leaguemate invited you`,
       run(null, null, m), `A leaguemate invited you${TAIL}`);
  }

  // (d) the ruling: no inviter name from an old server / no or invalid `t` /
  // a failed call → today's ladder EXACTLY (including null = no banner).
  const NO_NAME = [
    ['request error / no t (null)', null],
    ['old server (neither new key)', { ...OLD_BODY }],
    ['old server, league_name null', { ...OLD_BODY, league_name: null }],
    ['status valid, name null', { ...OLD_BODY, inviter_display_name: null, invite_status: 'valid' }],
    ['status null', { ...OLD_BODY, inviter_display_name: null, invite_status: null }],
    ['status unrecognised', { ...OLD_BODY, invite_status: 'revoked' }],
    ['legacy key name token_status (never emitted, C1)', { ...OLD_BODY, token_status: 'unknown' }],
    ['name blank', { ...OLD_BODY, inviter_display_name: '   ' }],
    ['name a number', { ...OLD_BODY, inviter_display_name: 42 }],
    ['name an object', { ...OLD_BODY, inviter_display_name: { first: 'T' } }],
    ['name an array', { ...OLD_BODY, inviter_display_name: ['Teresa'] }],
    ['empty object', {}],
  ];
  for (const [label, m] of NO_NAME) {
    eq(`B4 (d) ${label} → today's lines`,
       NAMES.map((lg) => run(null, lg, m)), NAMES.map((lg) => today(null, lg)));
  }

  // Never throws, never renders junk, never renders the id.
  const junk = [];
  for (const by of [null, '', 'teresa']) for (const lg of NAMES)
    for (const [, m] of [...NO_NAME, ...ANY_META.map((x) => ['', x])]) {
      const m2 = m && typeof m === 'object' ? { ...m, t: ID, invite_id: ID } : m;
      const out = run(by, lg, m2);
      if (out !== null && (typeof out !== 'string' || /THREW|undefined|null|\[object|Ab3dEf6hIj9k/.test(out))) {
        junk.push(out);
      }
    }
  eq('B5 never throws, never renders undefined/null/[object], never renders the id', junk, []);

  // The ladder reads nothing it was not handed: no store, no URL, no id.
  const body = decl.body ? decl.body.getText(signinSf) : '';
  check('B6 the ladder references no inviteId / store / URL',
        !/\binviteId\b|\buseSession\b|\bLinking\b|\broute\b|\bparams\b|\binvitedLeagueId\b/.test(body),
        'inviteHeadlineFor reads something other than its three arguments');
}

// ── C. the invite-meta effect, lifted and executed ──────────────────────
let effectFactory = null;
let effectCall = null;
function liftEffect() {
  const metaCalls = callsTo(signinSf, 'fetchInviteMeta');
  const effects = callsTo(signinSf, 'useEffect').filter((c) =>
    metaCalls.some((m) => within(m, c)));
  if (effects.length !== 1) {
    fail('C0 exactly one useEffect owns the invite-meta call', `${effects.length} found`);
    return;
  }
  effectCall = effects[0];
  const fn = effectCall.arguments[0];
  try {
    const js = ts.transpileModule(`const __effect = ${fn.getText(signinSf)};`, {
      compilerOptions: { module: ts.ModuleKind.None, target: ts.ScriptTarget.ES2019 },
    }).outputText;
    // The effect's ONLY free variables. A new one is a new input — re-point the
    // lift and decide whether it can carry a URL value; don't widen blindly.
    // eslint-disable-next-line no-new-func
    effectFactory = new Function(
      'invitedLeagueId', 'inviteId', 'useSession', 'setInviterMeta', 'fetchInviteMeta',
      `'use strict';\n${js}\nreturn __effect;`);
    ok('C0 the invite-meta effect lifts with inputs (invitedLeagueId, inviteId, useSession, setInviterMeta, fetchInviteMeta)');
  } catch (e) {
    fail('C0 the invite-meta effect lifts', String(e && e.message));
  }
}

/** Run the real effect once against the real fetchInviteMeta + a stub server. */
async function runEffect({ leagueId = LEAGUE, inviteId = null, cachedName = null,
                           srv = oldServer, cancelEarly = false }) {
  server = srv; apiCalls.length = 0;
  const store = { invitedLeagueName: cachedName, consumed: false, nameWrites: [] };
  const useSession = {
    getState: () => ({
      invitedLeagueName: store.invitedLeagueName,
      inviteId,
      setInvitedLeagueName: async (n) => { store.nameWrites.push(n); store.invitedLeagueName = n; },
      consumeInviteId: () => { store.consumed = true; return inviteId; },
    }),
  };
  let inviterMeta = null;
  const metaWrites = [];
  const setInviterMeta = (v) => { metaWrites.push(v); inviterMeta = v; };
  let cleanup;
  try {
    cleanup = effectFactory(leagueId, inviteId, useSession, setInviterMeta, fetchInviteMeta)();
  } catch (e) {
    return { threw: String(e && e.message) };
  }
  if (cancelEarly && typeof cleanup === 'function') cleanup();
  await flush(); await flush();
  return {
    paths: apiCalls.map((c) => c.path),
    inviterMeta, metaWrites, leagueName: store.invitedLeagueName,
    nameWrites: store.nameWrites, consumed: store.consumed,
  };
}

async function sectionC() {
  if (!effectFactory || !ladder) {
    fail('C* skipped', 'the effect or the ladder did not lift (see C0 / B0)');
    return;
  }
  const headline = (r, invitedBy = null) => ladder(invitedBy, r.leagueName, r.inviterMeta);

  // Ruling case 1 — OLD server, valid `t`: today's line, and today's caching.
  for (const cached of [null, LG]) {
    const r = await runEffect({ inviteId: ID, cachedName: cached, srv: oldServer });
    eq(`C1 old server + valid t (name ${cached ? 'cached' : 'not cached'}) → today's line`,
       headline(r), today(null, LG));
    check(`C1 old server + valid t (name ${cached ? 'cached' : 'not cached'}) → t still sent, once`,
          r.paths.length === 1 && r.paths[0] === `${TODAY_URL}&t=${ID}`, JSON.stringify(r.paths));
  }

  // Ruling case 2 — MISSING `t`: today's call and today's skip, exactly.
  {
    const r = await runEffect({ inviteId: null, cachedName: null, srv: newServer('valid', 'Teresa') });
    eq('C2 no t, name not cached → today\'s request', r.paths, [TODAY_URL]);
    eq('C2 no t, name not cached → league name cached (today\'s P0-3 behaviour)', r.nameWrites, [LG]);
    eq('C2 no t → no inviter state written', r.metaWrites.filter((v) => v !== null), []);
    eq('C2 no t → today\'s line', headline(r), today(null, LG));
    const s = await runEffect({ inviteId: null, cachedName: LG, srv: newServer('valid', 'Teresa') });
    eq('C2 no t, name cached → no request (today\'s skip)', s.paths, []);
    eq('C2 no t, name cached → today\'s line', headline(s), today(null, LG));
    const u = await runEffect({ leagueId: null, inviteId: ID, srv: newServer('valid', 'Teresa') });
    eq('C2 no invited league → no request, no banner', [u.paths, headline(u)], [[], null]);
  }

  // Ruling case 2b — INVALID `t` (only reachable from a tampered blob): never
  // sent, so even a §8.3 server answers today's shape → today's line.
  {
    const lines = []; const urls = [];
    for (const bad of BAD_IDS.filter((b) => b)) {      // a falsy id is case 2
      const r = await runEffect({ inviteId: bad, cachedName: null, srv: newServer('valid', 'Teresa') });
      urls.push(r.paths[0]); lines.push(headline(r));
    }
    eq('C3 invalid t → never sent', urls, urls.map(() => TODAY_URL));
    eq('C3 invalid t → today\'s line', lines, lines.map(() => today(null, LG)));
  }

  // Ruling case 3 — REQUEST ERROR / throw / deadline: today's line (here the
  // league name was cached by an earlier launch, so it is still shown), and
  // with nothing cached, no banner — never a broken one.
  const errs = [
    ['500', rejectServer(new ApiError(500))],
    ['404', rejectServer(new ApiError(404))],
    ['offline', rejectServer(new TypeError('Network request failed'))],
    ['sync throw', throwServer],
  ];
  for (const [label, srv] of errs) {
    for (const cached of [LG, null]) {
      const r = await runEffect({ inviteId: ID, cachedName: cached, srv });
      check(`C4 request error (${label}, name ${cached ? 'cached' : 'not cached'}) → effect does not throw`,
            !r.threw, r.threw);
      eq(`C4 request error (${label}, name ${cached ? 'cached' : 'not cached'}) → today's line`,
         headline(r), today(null, cached));
    }
  }
  {
    timers.length = 0;
    server = hangServer;
    const pending = runEffect({ inviteId: ID, cachedName: LG, srv: hangServer });
    await flush();
    const deadline = timers.find((t) => t.live);
    if (deadline) deadline.fn();
    const r = await pending;
    eq('C4 deadline (hung call) → today\'s line', headline(r), today(null, LG));
  }

  // Positive controls — the same harness DOES move off today's line when the
  // §8.3 server answers, so C1-C4 are not vacuous.
  {
    const r = await runEffect({ inviteId: ID, cachedName: null, srv: newServer('valid', 'Teresa') });
    eq('C5 §8.3 valid → ladder 1', headline(r), `Teresa invited you to Dynasty Bros${TAIL}`);
    const s = await runEffect({ inviteId: ID, cachedName: LG, srv: newServer('valid', 'Teresa') });
    eq('C5 name cached + t → still asks, with t (scope §3 item 8)', s.paths, [`${TODAY_URL}&t=${ID}`]);
    eq('C5 name cached + t → ladder 1', headline(s), `Teresa invited you to Dynasty Bros${TAIL}`);
    const u = await runEffect({ inviteId: ID, cachedName: null, srv: newServer('unknown', null) });
    eq('C6 §8.3 unknown → ladder 3', headline(u), `A leaguemate invited you to Dynasty Bros${TAIL}`);
    eq('C7 legacy ref still outranks a resolved name', headline(r, 'teresa'), today('teresa', LG));
  }

  // Peek, never consume; an unmounted screen writes nothing (today's alive flag).
  {
    const r = await runEffect({ inviteId: ID, srv: newServer('valid', 'Teresa') });
    eq('C8 the effect never consumes the invite id', r.consumed, false);
    const c = await runEffect({ inviteId: ID, srv: newServer('valid', 'Teresa'), cancelEarly: true });
    eq('C9 cleanup before the response → no inviter state, no name write',
       [c.metaWrites.filter((v) => v !== null), c.nameWrites], [[], []]);
  }

  // The display name is the server's, never the id or anything URL-shaped.
  {
    const r = await runEffect({ inviteId: ID, srv: newServer('expired', null) });
    check('C10 the id itself is never rendered', !String(headline(r)).includes(ID), headline(r));
  }
}

// ── D. static wiring (shape, not behaviour) ─────────────────────────────
function sectionD() {
  // D1 — exactly one invite-meta call site in the app, and it is SignIn's.
  const sites = [];
  (function walk(dir) {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, ent.name);
      if (ent.isDirectory()) walk(p);
      else if (/\.tsx?$/.test(ent.name)) {
        const rel = path.relative(SRC, p);
        const sf = parse(rel);
        for (const c of callsTo(sf, 'fetchInviteMeta')) sites.push(rel);
        // A second caller could also go around the wrapper.
        if (rel !== 'api/league.ts' && /invite-meta/.test(fs.readFileSync(p, 'utf8').replace(/\/\/.*$|\/\*[\s\S]*?\*\//gm, ''))) {
          sites.push(`${rel} (raw invite-meta URL)`);
        }
      }
    }
  })(SRC);
  eq('D1 exactly one invite-meta call site, in SignInScreen', sites, [SIGNIN]);

  // D2 — the id is PEEKED by selector (or getState), never consumed here.
  const idDecls = findAll(signinSf, (n) =>
    ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === 'inviteId');
  const idInit = idDecls[0] && idDecls[0].initializer ? squash(idDecls[0].initializer.getText(signinSf)) : '';
  check('D2 inviteId is a store peek: useSession((s) => s.inviteId) or getState().inviteId',
        idDecls.length === 1 &&
          (/^useSession\(\((\w+)\) => \1\.inviteId\)$/.test(idInit) ||
           /^useSession\.getState\(\)\.inviteId$/.test(idInit)),
        `${idDecls.length} declaration(s): ${idInit}`);
  check('D2 SignIn never consumes the invite id (B3 does, at session init)',
        !/consumeInviteId/.test(read(SIGNIN)), 'consumeInviteId appears in SignInScreen.tsx');

  // D3 — the call passes that id; the inviter state is written only from the
  // response (so the name is server-resolved), or cleared with null.
  const call = callsTo(signinSf, 'fetchInviteMeta')[0];
  if (call) {
    eq('D3 fetchInviteMeta(id, inviteId)', call.arguments.map((a) => a.getText(signinSf)), ['id', 'inviteId']);
    const thenCall = call.parent && ts.isPropertyAccessExpression(call.parent) &&
      call.parent.name.text === 'then' ? call.parent.parent : null;
    const cb = thenCall && thenCall.arguments[0];
    const param = cb && cb.parameters && cb.parameters[0] ? cb.parameters[0].name.getText(signinSf) : null;
    const writes = callsTo(signinSf, 'setInviterMeta');
    const bad = writes.filter((w) => {
      const a = w.arguments.map((x) => x.getText(signinSf));
      if (a.length === 1 && a[0] === 'null') return false;
      return !(cb && within(w, cb) && a.length === 1 && a[0] === param);
    });
    check('D3 setInviterMeta is written only with the invite-meta response (or null)',
          writes.length > 0 && bad.length === 0 && !!param,
          bad.map((w) => w.getText(signinSf)).join(' | ') || 'no .then callback found');
  } else {
    fail('D3 fetchInviteMeta call found', 'none');
  }

  // D4 — the banner is fed by the ladder, from exactly those three values,
  // and the two store values are the P0-3 selectors.
  const ladderCalls = callsTo(signinSf, 'inviteHeadlineFor');
  eq('D4 one ladder call: inviteHeadlineFor(invitedBy, invitedLeagueName, inviterMeta)',
     ladderCalls.map((c) => c.arguments.map((a) => a.getText(signinSf))),
     [['invitedBy', 'invitedLeagueName', 'inviterMeta']]);
  const lc = ladderCalls[0];
  check('D4 its result is the banner\'s inviteHeadline',
        lc && ts.isVariableDeclaration(lc.parent) && lc.parent.name.getText(signinSf) === 'inviteHeadline',
        lc ? lc.parent.getText(signinSf) : 'no call');
  for (const [v, field] of [['invitedBy', 'invitedBy'], ['invitedLeagueName', 'invitedLeagueName']]) {
    const d = findAll(signinSf, (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === v);
    const init = d[0] && d[0].initializer ? squash(d[0].initializer.getText(signinSf)) : '';
    check(`D4 ${v} is the store selector s.${field}`,
          d.length === 1 && new RegExp(`^useSession\\(\\((\\w+)\\) => \\1\\.${field}\\)$`).test(init),
          `${d.length}: ${init}`);
  }
  check('D4 the banner still renders {inviteHeadline} as signin.invited-banner',
        /testID="signin\.invited-banner"[^>]*>\s*\{inviteHeadline\}/.test(read(SIGNIN)),
        'the invited-banner Text no longer renders inviteHeadline');

  // D5 — the inviter fields are read in ONE place: the ladder.
  const ladderDecl = findAll(signinSf, (n) =>
    ts.isFunctionDeclaration(n) && !!n.name && n.name.text === 'inviteHeadlineFor')[0];
  const fieldRefs = findAll(signinSf, (n) => ts.isIdentifier(n) &&
    (n.text === 'inviter_display_name' || n.text === 'invite_status'));
  check('D5 inviter_display_name / invite_status are read only inside the ladder',
        !!ladderDecl && fieldRefs.length > 0 && fieldRefs.every((n) => within(n, ladderDecl)),
        'an inviter field is read (or rendered) outside inviteHeadlineFor');
  const metaRefs = findAll(signinSf, (n) => ts.isIdentifier(n) && n.text === 'inviterMeta');
  check('D5 inviterMeta is used only as the ladder\'s input',
        metaRefs.length === 2 && !!lc && metaRefs.some((n) => within(n, lc)),
        `${metaRefs.length} reference(s)`);

  // D6 — the effect re-runs on the league or the id, NOT on the cached name:
  // with the name as a dep, caching it from the response would re-ask.
  if (effectCall) {
    eq('D6 the effect\'s deps are [invitedLeagueId, inviteId]',
       effectCall.arguments[1] ? squash(effectCall.arguments[1].getText(signinSf)) : null,
       '[invitedLeagueId, inviteId]');
  }

  // D7 — the screen reads no URL: no name can come from a link directly.
  check('D7 SignIn reads no URL (no getInitialURL / useURL / useRoute / Linking.parse / url listener)',
        !/getInitialURL|useURL|useRoute|Linking\.parse|addEventListener\(\s*['"]url/.test(read(SIGNIN)),
        'SignInScreen gained a URL read');
}

(async () => {
  await sectionA();
  sectionB();
  liftEffect();
  await sectionC();
  sectionD();
  if (failures) {
    console.error(`\n${failures} check(s) failed — check-signin-inviter`);
    process.exit(1);
  }
  console.log('\ncheck-signin-inviter: all checks passed');
})().catch((e) => {
  console.error('check-signin-inviter crashed:', e && e.stack ? e.stack : e);
  process.exit(1);
});
