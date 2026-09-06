#!/usr/bin/env node
// WHY THIS EXISTS: a saved pass could return under another card ID or lane,
// while a reason-bank HTTP 200 was mistaken for a durable disposition. Execute
// the production identity, settlement and cursor helpers, the real API adapter,
// and the screen's module-scoped acknowledgement bus. Wiring assertions cover
// the remaining React seams; this is not physical-device runtime proof.
// Optional unchanged-baseline proof: FTF_TRADE_DISPOSITION_BASELINE=4026ebc8 node ...
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const cp = require('child_process');
const ts = require('typescript');
const assert = require('assert/strict');
const root = path.join(__dirname, '../..');
const baseline = process.env.FTF_TRADE_DISPOSITION_BASELINE;
const read = (p) => baseline
  ? cp.execFileSync('git', ['show', `${baseline}:${p}`], { cwd: root, encoding: 'utf8' })
  : fs.readFileSync(path.join(root, p), 'utf8');
const screen = read('mobile/src/screens/TradesScreen.tsx');
const adapter = read('mobile/src/api/declineReasons.ts');
const sf = ts.createSourceFile('TradesScreen.tsx', screen, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function all(node, predicate, out = []) {
  if (predicate(node)) out.push(node);
  ts.forEachChild(node, (child) => { all(child, predicate, out); });
  return out;
}
function functionText(name) {
  return all(sf, (n) => ts.isFunctionDeclaration(n) && n.name?.text === name)[0]?.getText(sf) ?? '';
}
function compile(source, context = {}) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
  } }).outputText, { module, exports: module.exports, Set, Map, Promise, ...context });
  return module.exports;
}
let passed = 0;
let failed = 0;
async function test(name, fn) {
  try { await fn(); passed++; console.log(`PASS ${name}`); }
  catch (error) { failed++; console.error(`FAIL ${name}: ${error.message}`); }
}
const copy = (v) => JSON.parse(JSON.stringify(v));
const P = { trade_id: 'p', league_id: 'L', opponent_user_id: 'B', give_player_ids: ['g'], receive_player_ids: ['r'] };
const Q = { ...P, trade_id: 'q', give_player_ids: ['q'] };
const R = { ...P, trade_id: 'r', give_player_ids: ['s'] };

(async () => {
  let body;
  let response = { ok: true, passed: false };
  let reject = false;
  const api = compile(adapter, { require: (name) => {
    assert.equal(name, './client');
    return { api: { post: async (route, payload) => {
      assert.equal(route, '/api/trades/pass-reason'); body = payload;
      if (reject) throw new Error('offline');
      return response;
    } } };
  } });
  const write = { tradeId: 'p::edited', leagueId: 'L', givePlayerIds: ['edited'],
    receivePlayerIds: ['r'], targetUserId: 'B', targetUsername: 'partner',
    layer: 1, reason: 'fit', dwellMs: 0, detailExpanded: false, calcOpened: false };
  await test('reason bank preserves passed:false as structured evidence', async () => {
    assert.deepEqual(copy(await api.postDeclineReason(write)), response);
  });
  await test('adapter echoes actual edited package and counterpart', async () => {
    await api.postDeclineReason(write);
    assert.equal(body.trade_id, 'p::edited');
    assert.deepEqual(body.give_player_ids && copy(body.give_player_ids), ['edited']);
    assert.deepEqual(body.receive_player_ids && copy(body.receive_player_ids), ['r']);
    assert.equal(body.target_user_id, 'B'); assert.equal(body.target_username, 'partner');
    assert.equal(body.league_id, 'L');
  });
  await test('verified true remains distinct from a transport failure', async () => {
    response = { ok: true, passed: true };
    assert.equal((await api.postDeclineReason(write))?.passed, true);
    reject = true; assert.equal(await api.postDeclineReason(write), null); reject = false;
  });

  if (baseline) {
    await test('unchanged baseline lane projection excludes the known passed package', () => {
      const sorted = all(sf, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === 'sortedDeck')[0];
      assert.ok(sorted?.initializer, 'baseline projection must actually exist');
      const result = compile(`module.exports = ${sorted.initializer.getText(sf)}`, {
        useMemo: (fn) => fn(), deck: [P, Q], laneFilter: null, fairnessOn: true,
        canvasResultsOn: false, browseSession: null, committedPasses: new Set(['p']),
      });
      assert.deepEqual(copy(result).map((c) => c.trade_id), ['q']);
    });
    console.log(`Baseline ${baseline}: ${passed} passed, ${failed} failed (expected regression assertions).`);
    process.exitCode = failed ? 1 : 0;
    return;
  }

  const helper = compile(read('mobile/src/utils/tradeDisposition.ts'));
  const key = (card = P, account = 'A', league = 'L') => helper.tradePassKey(account, league, card);
  const committed = new Set([key()]);
  const project = (cards, position, keys = committed, edits = {}, held = null) =>
    helper.projectTradePasses(cards, position, 'A', 'L', keys, edits, held);

  await test('exact identity ignores ID, side ordering and repeated IDs', () => {
    assert.equal(key(), key({ ...P, trade_id: 'regenerated' }));
    assert.equal(key({ ...P, give_player_ids: ['a', 'b', 'a'] }), key({ ...P, give_player_ids: ['b', 'a'] }));
  });
  await test('identity isolates orientation, package, partner, account and league', () => {
    assert.notEqual(key(), key({ ...P, give_player_ids: ['r'], receive_player_ids: ['g'] }));
    for (const card of [Q, { ...P, receive_player_ids: ['r', 'pick'] }, { ...P, opponent_user_id: 'C' }]) assert.notEqual(key(), key(card));
    assert.notEqual(key(), key(P, 'C'));
    assert.notEqual(key(), key({ ...P, league_id: 'M' }, 'A', 'M'));
    assert.equal(key({ ...P, opponent_user_id: '' }), null);
    assert.equal(key(P, 'A', 'M'), null);
  });
  await test('new IDs, same-length snapshots, lane reset, Find More and restored deck honor the mask', () => {
    for (const cards of [[P, Q], [{ ...P, trade_id: 'new' }, Q], [Q, P], [P, Q, R]]) {
      const result = project(cards, 0);
      assert.ok(result.cards.every((card) => key(card) !== key()));
    }
    const restored = project([P, Q, R], 1);
    assert.equal(restored.cards[restored.index].trade_id, 'q');
  });
  await test('edited pass excludes only that edited package, not the raw suggestion', () => {
    const edited = { ...P, trade_id: 'p::edited', give_player_ids: ['edit'] };
    const keys = new Set([key(edited)]);
    assert.equal(project([P, Q], 0, keys).cards.length, 2);
    assert.deepEqual(copy(project([P, Q], 0, keys, { p: edited }).cards).map((c) => c.trade_id), ['q']);
    assert.equal(project([{ ...edited, trade_id: 'new' }], 0, keys).cards.length, 0);
  });
  await test('late commitment behind cursor preserves its next card without skipping', () => {
    const before = project([P, Q, R], 0, new Set());
    const next = helper.tradeSourcePosition(before, before.index + 1);
    const after = project([P, Q, R], next);
    assert.equal(after.index, 0); assert.equal(after.cards[after.index].trade_id, 'q');
  });
  await test('layer 2 retains a committed current card and advances exactly once', () => {
    const held = project([P, Q, R], 0, committed, {}, 'p');
    assert.equal(held.cards[held.index].trade_id, 'p');
    const after = project([P, Q, R], helper.tradeSourcePosition(held, held.index + 1));
    assert.equal(after.cards[after.index].trade_id, 'q');
  });
  await test('cursor supports backward/forward moves, exhaustion, bounds and reordered sources', () => {
    const p = project([P, Q, R], 2);
    assert.equal(p.cards[p.index].trade_id, 'r');
    assert.equal(project([P, Q, R], helper.tradeSourcePosition(p, p.index - 1)).cards[0].trade_id, 'q');
    assert.equal(helper.tradeSourcePosition(p, 99), 3);
    for (const ordered of [[P, Q, R], [R, P, Q], [Q, R, P]]) for (let i = -1; i <= 4; i++) {
      const result = project(ordered, i);
      assert.ok(result.index >= 0 && result.index <= result.cards.length);
      assert.ok(result.sourceIndices.every((n, j) => n >= 0 && n < ordered.length && (!j || result.sourceIndices[j - 1] < n)));
    }
  });
  const start = () => ({ swipe: 'pending', reasonsPending: 0, reasonPassed: false });
  await test('held Undo has no commitment; both failures remain retryable', () => {
    assert.equal(helper.passWriteStatus({ ...start(), swipe: 'held' }), 'pending');
    let state = helper.settlePassWrite(start(), { type: 'reason_started' });
    state = helper.settlePassWrite(state, { type: 'swipe', status: 'failed' });
    assert.equal(helper.passWriteStatus(state), 'pending');
    state = helper.settlePassWrite(state, { type: 'reason_settled', passed: false });
    assert.equal(helper.passWriteStatus(state), 'failed');
  });
  await test('reason true survives failed swipe, false/missing refinement and duplicate true', () => {
    let state = helper.settlePassWrite(start(), { type: 'reason_settled', passed: true });
    state = helper.settlePassWrite(state, { type: 'swipe', status: 'failed' });
    for (const passed of [false, undefined, true]) {
      state = helper.settlePassWrite(state, { type: 'reason_settled', passed });
      assert.equal(helper.passWriteStatus(state), 'committed');
    }
  });
  await test('plain swipe acknowledgement and verified reason are independent sources', () => {
    const state = helper.settlePassWrite(start(), { type: 'swipe', status: 'acknowledged' });
    assert.equal(helper.passWriteStatus(state), 'committed');
    assert.equal(state.reasonPassed, false);
  });

  function deckHarness(cards, position, keys, rawId) {
    let deck = cards;
    let sourcePosition = position;
    let browse = { passed: 0, edits: {} };
    const attempt = { context: { rawId }, card: cards.find((c) => c.trade_id === rawId), state: start(), requests: [] };
    const projectionRef = { current: project(cards, position, keys, {}, rawId) };
    const deckRef = { current: deck };
    const bank = { current: rawId };
    const context = {
      ...helper, deckSourcePosition: position, deckProjectionRef: projectionRef,
      browseDeckSyncRef: deckRef, reasonBankedIdRef: bank,
      reasonPassAttemptRef: { current: attempt }, browseSession: browse,
      userId: 'A', leagueId: 'L', localPassSession: { committed: keys }, edits: {},
      browseLive: true, lastDispositionedRef: { current: rawId },
      browseSeededIdRef: { current: rawId }, actionCanUpdateScreen: () => true,
      setDeck: (update) => { deck = typeof update === 'function' ? update(deck) : update; },
      setDeckSourcePosition: (update) => { sourcePosition = typeof update === 'function' ? update(sourcePosition) : update; },
      setBrowseSession: (update) => { browse = update(browse); },
      setReasonBankedId: () => {}, setCanvasPrefill: () => {}, setCanvasPrefillSeq: () => {},
    };
    const code = ['setDeckIdx', 'removeBrowsedIdea', 'restoreBrowsedPass', 'commitReasonAdvance'].map(functionText).join('\n');
    const methods = compile(`${code}\nmodule.exports = { commitReasonAdvance, restoreBrowsedPass };`, context);
    return { ...methods, attempt, result: () => ({
      deck, browse, sourcePosition, projection: project(deck, sourcePosition, keys),
    }) };
  }
  await test('actual browse splice and deferred advance preserve next/last cards with earlier masks', () => {
    for (const [position, rawId, expected] of [[1, 'q', 'r'], [2, 'r', 'q']]) {
      const h = deckHarness([P, Q, R], position, committed, rawId);
      h.commitReasonAdvance();
      const result = h.result();
      assert.equal(result.projection.cards[result.projection.index].trade_id, expected);
      assert.equal(result.browse.passed, 1);
      h.commitReasonAdvance(); assert.equal(h.result().browse.passed, 1);
    }
  });
  await test('actual browse total-failure restoration makes the removed package retryable once', () => {
    const h = deckHarness([P, Q, R], 1, committed, 'q');
    h.commitReasonAdvance(); h.restoreBrowsedPass(h.attempt);
    const result = h.result();
    assert.deepEqual(copy(result.deck).map((c) => c.trade_id), ['p', 'q', 'r']);
    assert.equal(result.projection.cards[result.projection.index].trade_id, 'q');
    assert.equal(result.browse.passed, 0);
    h.restoreBrowsedPass(h.attempt); assert.equal(h.result().deck.length, 3);
  });

  // Execute the actual shared screen bus, including its useSession subscription.
  let session = { user: { user_id: 'A' }, league: { league_id: 'L' }, hasToken: true };
  let subscriber;
  const busStart = screen.indexOf('function localPassScope()');
  const busEnd = screen.indexOf('// audit P1-1', busStart);
  const bus = compile(screen.slice(busStart, busEnd) + '\nmodule.exports = { snapshot: () => localPassSession, commitLocalPass, observeReasonRequest, subscribeLocalPasses, currentPassContext };', {
    ...helper, useSession: { getState: () => session, subscribe: (fn) => { subscriber = fn; } },
  });
  function attempt() {
    const snapshot = bus.snapshot();
    return { context: { scope: snapshot.scope, scopeEpoch: snapshot.epoch, deckEpoch: 0, passKey: key(), rawId: 'p' },
      card: P, state: start(), requests: [] };
  }
  await test('shared record broadcasts once, survives another subscriber/remount, rejects A→B→A callbacks', () => {
    let notifications = 0;
    const unsubscribe = bus.subscribeLocalPasses(() => notifications++);
    const a = attempt(); a.state.swipe = 'acknowledged'; bus.commitLocalPass(a); bus.commitLocalPass(a);
    assert.equal(notifications, 1); assert.ok(bus.snapshot().committed.has(key()));
    unsubscribe(); assert.ok(bus.snapshot().committed.has(key()));
    const late = attempt(); late.state.reasonPassed = true;
    session = { ...session, league: { league_id: 'M' } }; subscriber();
    session = { ...session, league: { league_id: 'L' } }; subscriber();
    bus.commitLocalPass(late); assert.equal(bus.snapshot().committed.size, 0);
  });
  await test('actual reason observer commits only passed===true, including delayed sibling responses', async () => {
    const a = attempt(); a.state.swipe = 'failed';
    for (const result of [null, { ok: true }, { ok: true, passed: false }]) {
      bus.observeReasonRequest(a, Promise.resolve(result)); await Promise.all(a.requests);
      assert.equal(bus.snapshot().committed.size, 0);
    }
    bus.observeReasonRequest(a, Promise.resolve({ ok: true, passed: true })); await Promise.all(a.requests);
    assert.ok(bus.snapshot().committed.has(key()));
  });
  const swipeDeclaration = all(sf, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === 'swipeMutation')[0];
  const swipeOptions = swipeDeclaration.initializer.arguments[0];
  const onError = swipeOptions.properties.find((p) => p.name?.getText(sf) === 'onError').initializer.getText(sf);
  const tick = () => new Promise((resolve) => setImmediate(resolve));
  function errorHarness(a, options = {}) {
    let index = options.index ?? 1;
    let toasts = 0;
    let remounts = 0;
    const poisoned = { current: 'p' };
    const reason = { current: a };
    const context = {
      ...helper, Promise, ApiError: class extends Error {}, SWIPE_ERROR_HOLD_MS: 5000,
      actionCanUpdateScreen: (ctx) => bus.currentPassContext(ctx),
      sortedDeckRef: { current: options.cards ?? [P, Q, R] },
      setDeckIdx: (update) => { index = update(index); },
      lastDispositionedRef: poisoned, reasonPassAttemptRef: reason,
      reasonBankedIdRef: { current: 'p' }, setReasonBankedId: () => {},
      setPassRetryVersion: () => { remounts++; },
      latestTradeActionRef: { current: new Map([['p', options.latestAction ?? a.context]]) },
      localPassSession: { committed: new Set() },
      queryClient: { invalidateQueries: () => {} }, leagueId: 'L',
      setToast: () => { toasts++; }, restoreBrowsedPass: () => {},
    };
    const fn = compile(`module.exports = ${onError}`, context);
    return { fire: () => fn(new Error('offline'), { decision: 'pass', passAttempt: a }, { rawId: 'p', action: a.context }),
      result: () => ({ index, toasts, remounts, guard: poisoned.current, reason: reason.current }) };
  }
  await test('actual swipe error waits only for evidence, does not block the mutation, and repairs total failure', async () => {
    const a = attempt();
    let resolve;
    bus.observeReasonRequest(a, new Promise((r) => { resolve = r; }));
    const h = errorHarness(a);
    assert.equal(h.fire(), undefined); assert.equal(h.result().toasts, 0);
    resolve({ ok: true, passed: false }); await tick();
    assert.deepEqual(h.result(), { index: 0, toasts: 1, remounts: 1, guard: null, reason: null });
  });
  await test('actual swipe error never rewinds or toasts over a late verified reason', async () => {
    const a = attempt(); let resolve;
    bus.observeReasonRequest(a, new Promise((r) => { resolve = r; }));
    const h = errorHarness(a); h.fire();
    resolve({ ok: true, passed: true }); await tick();
    assert.equal(h.result().index, 1); assert.equal(h.result().toasts, 0);
  });
  await test('actual failure uses the current reordered deck and preserves a later fronted card', async () => {
    for (const options of [{ cards: [R, Q, P], index: 1 }, { cards: [P, Q, R], index: 2 }]) {
      const a = attempt(); const h = errorHarness(a, options);
      h.fire(); await tick();
      assert.equal(h.result().index, options.index);
      assert.equal(h.result().toasts, 1);
      assert.equal(h.result().guard, null);
    }
  });
  await test('actual failure cannot undo a newer disposition of the same raw card', async () => {
    const a = attempt(); const h = errorHarness(a, { latestAction: { ...a.context } });
    h.fire(); await tick();
    assert.equal(h.result().index, 1); assert.equal(h.result().guard, 'p');
    assert.equal(h.result().reason, a); assert.equal(h.result().toasts, 0);
  });
  await test('actual stale A→B→A failure callback does not change cursor, guard, reason or toast', async () => {
    const a = attempt(); const h = errorHarness(a);
    session = { ...session, user: { user_id: 'B' } }; subscriber();
    session = { ...session, user: { user_id: 'A' } }; subscriber();
    h.fire(); await tick();
    assert.equal(h.result().index, 1); assert.equal(h.result().guard, 'p');
    assert.equal(h.result().reason, a); assert.equal(h.result().toasts, 0);
  });

  await test('screen uses one shared external snapshot and pure projection at every render', () => {
    assert.match(screen, /useSyncExternalStore\(subscribeLocalPasses, \(\) => localPassSession\)/);
    assert.match(screen, /projectTradePasses\(orderedDeck, deckSourcePosition,[\s\S]*?localPassSnapshot\.committed, edits, reasonBankedId\)/);
    assert.match(screen, /const sortedDeck = deckProjection\.cards/);
    assert.match(screen, /const deckIdx = deckProjection\.index/);
  });
  await test('pre-single-pin restoration preserves the source cursor, not a masked visible offset', () => {
    assert.match(screen, /deckIdx: deckSourcePosition/);
    assert.match(screen, /setDeckSourcePosition\(snap\.deckIdx\)/);
    assert.ok(!screen.includes('setDeckIdx(snap.deckIdx)'));
  });
  await test('acted reason target uses frozen edited card and full existing echo', () => {
    const target = functionText('reasonWriteTarget');
    assert.match(target, /reasonPassAttemptRef\.current\?\.card \?\? topCard/);
    for (const field of ['trade_id', 'league_id', 'give_player_ids', 'receive_player_ids', 'opponent_user_id', 'opponent_username']) assert.ok(target.includes(`acted?.${field}`));
    assert.ok(!target.includes('rawTopCard'));
  });
  await test('four progressive reason calls share observation and retain layer-2 transition', () => {
    for (const name of ['handleReasonLayer1', 'handleReasonLayer2Select', 'handleReasonLayer2Bank', 'handleReasonLayer2Send']) {
      assert.match(functionText(name), /observeReasonRequest\(attempt, postDeclineReason\(/);
    }
    assert.ok(!functionText('handleReasonLayer2Bank').includes('commitReasonAdvance'));
    assert.match(functionText('commitReasonAdvance'), /setDeckIdx\(\(i\) => i \+ 1\)/);
  });
  await test('Undo never writes or commits; held flush retains captured action identity', () => {
    const undo = functionText('undoPass');
    assert.ok(!/swipeMutation|commitLocalPass|postDeclineReason/.test(undo));
    assert.match(functionText('flushPendingPass'), /context: p\.attempt\.context, passAttempt: p\.attempt/);
  });
  await test('callbacks fence UI mutations and total failure re-arms the panel', () => {
    assert.match(functionText('actionCanUpdateScreen'), /mountedRef\.current && currentPassContext\(context\) && context\.deckEpoch === deckEpochRef\.current/);
    assert.match(screen, /if \(!ctx \|\| !actionCanUpdateScreen\(ctx\.action\)\) return;/);
    assert.match(screen, /while \(passWriteStatus\(attempt\.state\) === 'pending'\) await Promise\.all\(attempt\.requests\)/);
    assert.match(screen, /if \(passWriteStatus\(attempt\.state\) === 'committed'\) return;/);
    assert.match(screen, /key=\{`\$\{topCard\.trade_id\}:\$\{passRetryVersion\}`\}/);
  });
  console.log(`Trade disposition: ${passed} passed, ${failed} failed.`);
  process.exitCode = failed ? 1 : 0;
})();
