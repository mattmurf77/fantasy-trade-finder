#!/usr/bin/env node
// WHY THIS EXISTS (head-eng ruling 10, scope-eng-200ms §6.4, AC-L4): the next
// page must already be on the device before the user can reach the end of
// the current one — there is no "Finding more" card to fall back on. A
// prefetch rule that waits for the last card, a threshold read from the
// wrong place, or a retry ladder that climbs while the builder is still
// producing would all let a fast swiper hit the end of the local deck, and
// nothing in a type check or a code read would show it.
// What it does: a deterministic discrete-event simulation of the screen's
// page loop against a MOCKED SLOW SERVER, driven by the SAME pure rules the
// screen calls (utils/tradePages.ts: wantsNextPage, mergeDeckPage,
// isWholeDeck, needsBackoff, nextRetryAttempt, pageRetryDelayMs,
// unseenCount), transpiled and executed. The loop glue mirrors
// TradesScreen's `fetchNextPage` + its trigger effect: one request in flight
// or scheduled, re-evaluated on every swipe, response and timer.
// The pinned case: a scripted 44-card burst at 0.4 s per card from a COLD
// first page never reaches the end of the local deck. Sabotage controls run
// the same burst with a broken policy and must FAIL, which proves the
// simulation can see the defect it guards.
// HONEST LABEL (G-035): this proves the policy against a model of the server
// (its latency and build rate are stated per scenario), not a device or the
// real backend. The TestFlight checklist's U3 three-page run covers those.
//
// Run: node tests/check-trade-buffer.js   (or: npm run test:trade-buffer)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
let ts;
try { ts = require('typescript'); } catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}
const SRC = path.join(__dirname, '..', 'src');
const P = (() => {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(SRC, 'utils/tradePages.ts'), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  }).outputText, { module, exports: module.exports, Set, Map, Math });
  return module.exports;
})();

// ── The mocked slow server (P2 semantics, scope §6.4/§6.5) ────────────────
// `ready(t)`: raw cards the deck holds at time t (ms). A status request at
// time t is answered after `latencyMs`, from the deck as it stood at the
// midpoint of the round trip; the page is at most `pageSize` cards.
function makeServer(o) {
  const ready = (t) => Math.min(o.pool, Math.floor(o.firstPage + Math.max(0, t) * o.ratePerMs));
  const built = (t) => ready(t) >= o.pool;
  return {
    firstPage() {
      const n = Math.min(o.firstPage, o.pageSize);
      return { status: built(0) ? 'complete' : 'running', cursor: n, total_ready: ready(0),
        prefetch_remaining: o.prefetchRemaining, pool_exhausted: built(0) && n >= o.pool ? true : false,
        cards: Array.from({ length: n }, (_, i) => card(i)) };
    },
    page(cursor, sentAt) {
      const at = sentAt + o.latencyMs / 2;
      const total = ready(at);
      const end = Math.min(total, cursor + o.pageSize);
      const done = built(at);
      return {
        arrivesAt: sentAt + o.latencyMs,
        res: { status: done ? 'complete' : 'running', cursor: Math.max(cursor, end), total_ready: total,
          prefetch_remaining: o.prefetchRemaining, pool_exhausted: done && end >= o.pool,
          cards: Array.from({ length: Math.max(0, end - cursor) }, (_, i) => card(cursor + i)) },
      };
    },
  };
}
const card = (i) => ({ trade_id: `t${i}`, trade_hash: `h${i}` });

// ── The client: TradesScreen's page loop, on the shared pure rules ────────
function simulate(scenario, policy) {
  const server = makeServer(scenario);
  const first = server.firstPage();
  let held = first.cards.slice();
  let env = { ...first };
  let front = 0; // the first card renders at t = 0 (the clock starts here)
  const loop = { inFlight: null, timer: null, attempt: 0 };
  const log = [];
  const requests = [];

  function evaluate(now) {
    if (loop.inFlight || loop.timer != null) return;
    const unseen = P.unseenCount(held.length, front);
    if (!policy.wants({ ...env, unseen, busy: false })) return;
    const sent = server.page(env.cursor, now);
    loop.inFlight = { requested: env.cursor, ...sent };
    requests.push(now);
  }
  function land(now) {
    const { requested, res } = loop.inFlight;
    loop.inFlight = null;
    const frontKey = front < held.length ? P.deckCardKey(held[front]) : null;
    const merged = P.mergeDeckPage(held, res.cards, frontKey, P.isWholeDeck(res));
    held = merged.cards;
    env = { ...env, ...res, cards: undefined };
    const backoff = P.needsBackoff(res, requested);
    loop.attempt = policy.attempt(loop.attempt, backoff, merged.added);
    if (backoff) loop.timer = now + policy.delay(loop.attempt - 1);
  }

  evaluate(0); // the effect right after the first card's frame commits
  const swipeEvery = scenario.swipeMs;
  let swipes = 0;
  let t = 0;
  while (swipes < scenario.burst) {
    const nextSwipe = (swipes + 1) * swipeEvery;
    const nextLand = loop.inFlight ? loop.inFlight.arrivesAt : Infinity;
    const nextTimer = loop.timer != null ? loop.timer : Infinity;
    t = Math.min(nextSwipe, nextLand, nextTimer);
    if (t === nextLand) { land(t); evaluate(t); continue; }
    if (t === nextTimer) { loop.timer = null; evaluate(t); continue; }
    // The user acts on the fronted card and needs the next one NOW.
    swipes++;
    if (front + 1 >= held.length) {
      return { ok: false, at: t, swipes, held: held.length, requests: requests.length, log };
    }
    front++;
    evaluate(t);
  }
  return { ok: true, at: t, swipes, held: held.length, requests: requests.length, firstRequestAt: requests[0] };
}

const realPolicy = {
  wants: (s) => P.wantsNextPage(s),
  attempt: (a, b, added) => P.nextRetryAttempt(a, b, added),
  delay: (n) => P.pageRetryDelayMs(n),
};

// The pinned burst: 44 cards at 0.4 s per card.
const BURST = { burst: 44, swipeMs: 400 };
const scenarios = {
  // Cold first page: page 1 came from a job still building (no stored page),
  // so it is small; the slow server answers in 1.2 s and builds 3 cards/s.
  'cold first page, slow server (1.2 s RTT, builds 3 cards/s)': {
    ...BURST, firstPage: 12, pool: 160, ratePerMs: 3 / 1000, latencyMs: 1200, pageSize: 30, prefetchRemaining: 50,
  },
  // Same cold start with the server sending NO prefetch_remaining (client
  // fallback 50) and a slower 2 s round trip, building 4 cards/s.
  'cold first page, no server threshold (fallback 50), 2 s RTT': {
    ...BURST, firstPage: 10, pool: 160, ratePerMs: 4 / 1000, latencyMs: 2000, pageSize: 30, prefetchRemaining: undefined,
  },
  // Warm: pages 1–3 stored (90 ready), 2.5 s round trip.
  'stored pages, very slow server (2.5 s RTT)': {
    ...BURST, firstPage: 90, pool: 200, ratePerMs: 2 / 1000, latencyMs: 2500, pageSize: 30, prefetchRemaining: 50,
  },
};

let failures = 0;
function check(name, cond, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}${detail ? `\n      ${detail}` : ''}`); }
}

console.log('check-trade-buffer:');
for (const [name, sc] of Object.entries(scenarios)) {
  const r = simulate(sc, realPolicy);
  check(`${name}: the 44-card burst never reaches the end of the local deck`, r.ok,
    `reached the end at t=${r.at}ms after ${r.swipes} swipes, holding ${r.held}, after ${r.requests} requests`);
  if (r.ok) {
    check(`${name}: page 2 is requested as the first card renders (t=0, outside the tap clock)`, r.firstRequestAt === 0,
      `first request at t=${r.firstRequestAt}`);
  }
}

// Sabotage controls — the simulation must SEE each defect.
const cold = Object.values(scenarios)[0];
const lazy = simulate(cold, { ...realPolicy, wants: (s) => P.wantsNextPage(s) && s.unseen === 0 });
check('control: fetching only at the last card FAILS the burst (the sim can see an empty buffer)', !lazy.ok,
  'a last-card-only prefetch passed — the simulation is too lenient to guard anything');
const climbing = simulate(cold, { ...realPolicy, attempt: (a, b) => (b ? a + 1 : 0), delay: () => 4000 });
check('control: a 4 s retry ladder that ignores progress FAILS the burst', !climbing.ok,
  'a slow ladder passed — the cold scenario no longer stresses the retry rule');

console.log(failures ? `check-trade-buffer: ${failures} FAILED` : 'check-trade-buffer: all passed');
process.exit(failures ? 1 : 0);
