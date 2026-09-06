#!/usr/bin/env node
// WHY THIS EXISTS: selected-route offers had no observed-view denominator or
// impression-linked decisions. Execute the real exposure clock, normalizers
// and queue adapter; structure assertions cover native wiring, not device QA.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const ts = require('typescript');
const assert = require('assert/strict');
const root = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const copy = v => JSON.parse(JSON.stringify(v));
function compile(source, context = {}) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
  } }).outputText, { module, exports: module.exports, Set, Map, Number, ...context });
  return module.exports;
}
const pure = compile(read('src/utils/offerExposure.ts'));
const mapping = compile(read('src/utils/ideaToCard.ts'));
let request;
const api = compile(read('src/api/trades.ts') + '\nmodule.exports.normalizers = {normalizeTradeCard, normalizeAssetIdea};', {
  require: name => {
    assert.equal(name, './client');
    return { api: { post: async (route, body) => { request = { route, body }; return { queued: true }; } } };
  },
});
let count = 0;
function check(name, fn) { fn(); count++; console.log(`PASS ${name}`); }
const card = { trade_id: 'offer', impression_id: 'i1', league_id: 'L',
  opponent_user_id: 'P', give_player_ids: ['a'], receive_player_ids: ['b'] };

(async () => {
  check('500ms visible dwell required; prefetched/hidden does not count', () => {
    const c = pure.createOfferExposureClock(); c.setCard(card, 0);
    assert.equal(c.sample(false, 9000), null);
    assert.equal(c.sample(true, 10_000), null);
    assert.equal(c.sample(true, 10_499), null);
    assert.equal(c.sample(true, 10_500).impression_id, 'i1');
  });
  check('background/focus pauses reset continuous viewed clock and exclude dwell', () => {
    const c = pure.createOfferExposureClock(); c.setCard(card, 0); c.sample(true, 0);
    c.sample(true, 250); c.sample(false, 250);
    c.sample(false, 20_000); c.sample(true, 20_000);
    assert.equal(c.sample(true, 20_250), null);
    assert.equal(c.sample(true, 20_500).impression_id, 'i1');
    assert.equal(c.signalFor(card, 20_500).dwell_ms, 750);
  });
  check('one viewed event per impression even when returning through history', () => {
    const c = pure.createOfferExposureClock(); c.setCard(card, 0); c.sample(true, 0);
    assert.ok(c.sample(true, 500)); c.setCard(null, 1000); c.setCard(card, 1500);
    c.sample(true, 1500); assert.equal(c.sample(true, 2000), null);
    c.setCard({ ...card, impression_id: 'i2' }, 3000); c.sample(true, 3000);
    assert.equal(c.sample(true, 3500).impression_id, 'i2');
  });
  check('next page gets its own clock and cannot inherit the previous decision signal', () => {
    const c = pure.createOfferExposureClock(); c.setCard(card, 0); c.sample(true, 0);
    c.sample(true, 500); const held = c.signalFor(card, 700);
    const next = { ...card, trade_id: 'next', impression_id: 'i2' };
    c.setCard(next, 800); c.sample(true, 800); c.sample(true, 1400);
    assert.equal(c.signalFor(card, 2000), undefined);
    assert.equal(held.impression_id, 'i1'); assert.equal(held.dwell_ms, 700);
    assert.equal(c.signalFor(next, 2000).impression_id, 'i2');
  });
  check('edited package cannot reuse the original signal, and dwell is capped', () => {
    const c = pure.createOfferExposureClock(); c.setCard(card, 0); c.sample(true, 0);
    assert.equal(c.signalFor({ ...card, give_player_ids: ['edited'] }, 500), undefined);
    assert.equal(c.signalFor(card, 999999).dwell_ms, 120000);
    c.setCard({ ...card, impression_id: undefined }, 1000000);
    assert.equal(c.signalFor(card, 1001000), undefined);
  });
  check('viewport measurement rejects offscreen/zero/NaN frames', () => {
    assert.equal(pure.offerIsVisible(0, 0, 300, 400, 390, 800), true);
    assert.equal(pure.offerIsVisible(400, 0, 300, 400, 390, 800), false);
    assert.equal(pure.offerIsVisible(0, 900, 300, 400, 390, 800), false);
    assert.equal(pure.offerIsVisible(0, 0, 0, 400, 390, 800), false);
    assert.equal(pure.offerIsVisible(0, NaN, 300, 400, 390, 800), false);
  });
  const raw = { trade_id: 'owner-card', impression_id: 'owner-impression', model_arm: 'owner_v1',
    preserve_server_order: true,
    selection_coverage: 'partial', selection_notice: 'Includes part of your selection.', recommendation_rank: 0,
    generator_version: 'owner-v1', counterparty_user_id: 'P', counterparty_username: 'Partner',
    give_player_ids: ['a'], receive_player_ids: ['b'], give: [{ id: 'a' }], receive: [{ id: 'b' }],
    give_value: 1000, receive_value: 1000, fairness: 1, difference: 0 };
  check('selected ideas carry only whitelisted attribution through real normalizer→card', () => {
    const idea = api.normalizers.normalizeAssetIdea({ ...raw, owner_evaluation: { private: true } });
    const mapped = mapping.ideaToCard(idea, 'L');
    for (const key of ['trade_id', 'impression_id', 'model_arm', 'generator_version']) {
      assert.equal(mapped[key], raw[key]);
    }
    assert.equal(mapped.owner_evaluation, undefined);
    assert.equal(mapped.preserve_server_order, true);
    assert.equal(mapped.selection_coverage, 'partial');
    assert.equal(mapped.selection_notice, raw.selection_notice);
    assert.equal(mapped.recommendation_rank, 0);
    const old = mapping.ideaToCard(api.normalizers.normalizeAssetIdea({ ...raw,
      impression_id: null, model_arm: 23, generator_version: false, preserve_server_order: 'true' }), 'L');
    assert.equal(old.impression_id, undefined); assert.equal(old.model_arm, undefined);
    assert.equal(old.generator_version, undefined);
    assert.equal(old.preserve_server_order, undefined);
  });
  check('normal deck adapter also retains additive model/version', () => {
    const mapped = api.normalizers.normalizeTradeCard(raw);
    assert.equal(mapped.model_arm, 'owner_v1'); assert.equal(mapped.generator_version, 'owner-v1');
    assert.equal(mapped.preserve_server_order, true);
    assert.equal(mapped.selection_coverage, 'partial'); assert.equal(mapped.recommendation_rank, 0);
  });
  check('selection metadata and global recommendation rank reject malformed values', () => {
    for (const normalize of Object.values(api.normalizers)) {
      const mapped = normalize({ ...raw, selection_coverage: 'anything', selection_notice: false,
        recommendation_rank: -1 });
      assert.equal(mapped.selection_coverage, undefined); assert.equal(mapped.selection_notice, undefined);
      assert.equal(mapped.recommendation_rank, undefined);
      assert.equal(normalize({ ...raw, recommendation_rank: '0' }).recommendation_rank, undefined);
    }
  });
  await api.queueTradeForOpponent({ leagueId: 'L', opponentUserId: 'P', giveIds: ['a'], receiveIds: ['b'] });
  check('unattributed calculator queue wire body is unchanged', () => {
    assert.deepEqual(copy(request.body), { league_id: 'L', opponent_user_id: 'P',
      give_player_ids: ['a'], receive_player_ids: ['b'] });
  });
  await api.queueTradeForOpponent({ leagueId: 'L', opponentUserId: 'P', giveIds: ['a'], receiveIds: ['b'],
    signal: { impression_id: 'i1', dwell_ms: 700, detail_expanded: false, calc_opened: false } });
  check('queue uses existing flat SwipeSignal contract on existing endpoint', () => {
    assert.equal(request.route, '/api/trades/queue'); assert.equal(request.body.impression_id, 'i1');
    assert.equal(request.body.dwell_ms, 700); assert.equal(request.body.signal, undefined);
  });
  check('native hook gates on focus/app/flag and measures before emitting; cleanup cancels', () => {
    const hook = read('src/hooks/useSelectedOfferSignals.ts');
    for (const pattern of [/useIsFocused\(\)/, /useAppActive\(\)/, /useFlag\('deck.signal_v2'\)/,
      /measureInWindow/, /AppState.currentState === 'active'/, /offerIsVisible/,
      /cancelled = true/, /clearTimeout\(timer\)/, /clock.sample\(false/]) assert.match(hook, pattern);
  });
  check('Shop observes only current page and freezes pass signal before held Undo', () => {
    const shop = read('src/components/ShopOffersBody.tsx');
    assert.match(shop, /const activeIdea = visibleIdeas\[index\]/);
    assert.match(shop, /useSelectedOfferSignals\(activeCard, 'ShopAsset'/);
    assert.match(shop, /commitDismiss\(p.idea, p.signal\)/);
    assert.match(shop, /signal: signalForOffer\(ideaToCard\(idea, leagueId\)\)/);
    assert.match(shop, /swipeTrade\(ideaToCard\(idea, leagueId\), 'pass', signal, 'shop'\)/);
    assert.match(shop, /onScrollBeginDrag=\{\(\) => setPagerMoving\(true\)\}/);
  });
  check('Featured observes single current card, disables attribution after editing', () => {
    const feature = read('src/components/FeaturedTradeWindow.tsx');
    assert.match(feature, /useSelectedOfferSignals\(card, 'Trades', 0, measuredRef, !edited\)/);
    assert.match(feature, /onSidesChange=\{\(\) => setEdited\(true\)\}/);
  });
  check('partial selection notice is visible on all selected offer presentations', () => {
    for (const p of ['TradeCard.tsx', 'FeaturedTradeWindow.tsx', 'ShopOffersBody.tsx']) {
      const source = read(`src/components/${p}`);
      assert.match(source, /selection_coverage === 'partial'/);
      assert.match(source, /\{(?:data|idea|item).selection_notice\}/);
    }
  });
  check('both real Shop request builders and cache keys retain the captured fairness setting', () => {
    const source = read('src/components/ShopOffersBody.tsx');
    const parsed = ts.createSourceFile('ShopOffersBody.tsx', source,
      ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    let component;
    const configs = {};
    const visit = node => {
      if (ts.isFunctionDeclaration(node) && node.name?.text === 'ShopOffersBody') component = node;
      if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) &&
          ['ideasQuery', 'widenedQuery'].includes(node.name.text)) {
        assert.ok(ts.isCallExpression(node.initializer));
        configs[node.name.text] = node.initializer.arguments[0].getText(parsed);
      }
      ts.forEachChild(node, visit);
    };
    visit(parsed);
    assert.ok(component && configs.ideasQuery && configs.widenedQuery);
    const bodies = [];
    const actual = compile(`export function build(${component.parameters[0].getText(parsed)}) {
      return [${configs.ideasQuery}, ${configs.widenedQuery}];
    }`, { debouncedSwapKey: '', widenKey: 'RB+WR', widenEligible: true,
      fetchAssetIdeas: body => { bodies.push(copy(body)); } });
    const baseProps = { leagueId: 'L', asset: { id: 'a' }, onToast() {}, onToastRetract() {} };
    const defaults = actual.build(baseProps);
    const strict = actual.build({ ...baseProps, fairnessThreshold: .75 });
    for (let i = 0; i < 2; i++) {
      defaults[i].queryFn(); strict[i].queryFn();
      assert.equal(bodies[i * 2].fairness_threshold, .50);
      assert.equal(bodies[i * 2 + 1].fairness_threshold, .75);
      assert.notDeepEqual(copy(defaults[i].queryKey), copy(strict[i].queryKey));
    }
    assert.equal(bodies[0].swap_positions, undefined);
    assert.deepEqual(bodies[2].swap_positions, ['RB', 'WR']);
  });
  check('Shop navigation carries live fairness through its typed optional screen prop', () => {
    assert.match(read('src/navigation/RootNav.tsx'), /ShopAsset:\s*\{[^}]*fairnessThreshold\?: number/s);
    assert.match(read('src/screens/TradesScreen.tsx'), /navigate\('ShopAsset',\s*\{[^}]*fairnessThreshold: effectiveFairness/s);
    assert.match(read('src/screens/ShopAssetScreen.tsx'), /fairnessThreshold=\{fairnessThreshold\}/);
  });
  check('canvas queue joins only the exact original trial package, independent of side order', () => {
    const original = { ...card, preserve_server_order: true, give_player_ids: ['a', 'c'] };
    const target = { leagueId: 'L', opponentUserId: 'P', giveIds: ['c', 'a'], receiveIds: ['b'] };
    const captured = { impression_id: 'i1', dwell_ms: 750, detail_expanded: true, calc_opened: false };
    let reads = 0;
    const signal = offered => { assert.equal(offered, original); reads++; return captured; };
    assert.equal(pure.signalForExactTrialPackage(original, target, signal), captured);
    assert.equal(reads, 1);
    for (const changed of [
      { ...target, leagueId: 'other-league' }, { ...target, opponentUserId: 'other-manager' },
      { ...target, giveIds: ['a'] }, { ...target, receiveIds: ['replacement'] },
      { ...target, giveIds: ['b'], receiveIds: ['a', 'c'] },
      { ...target, giveIds: ['a', 'a'] },
    ]) assert.equal(pure.signalForExactTrialPackage(original, changed, signal), undefined);
    assert.equal(pure.signalForExactTrialPackage({ ...original, preserve_server_order: undefined }, target, signal), undefined);
    assert.equal(pure.signalForExactTrialPackage({ ...original, impression_id: undefined }, target, signal), undefined);
    assert.equal(pure.signalForExactTrialPackage(null, target, signal), undefined);
    assert.equal(reads, 1, 'mismatches must never consult or reuse a measured signal');
  });
  check('main trial canvas uses measured original visibility and joined queue/pass signals only once', () => {
    const main = read('src/screens/TradesScreen.tsx');
    assert.match(main, /const measuredTrial = rawTopCard\?\.preserve_server_order === true/);
    assert.match(main, /if \(measuredTrial\) return;[\s\S]*?if \(browseLive\) return;/);
    assert.match(main, /useSelectedOfferSignals\(rawTopCard \?\? null, 'Trades', deckIdx,[\s\S]*?browseLive \? trialCanvasRef : deckWrapRef/);
    assert.match(main, /measuredTrial && \(browseLive \? trialCanvasExact && !browseReasonOpen : trialDeckVisible\)/);
    assert.match(main, /browseSeededIdRef.current === rawTopCard\?\.trade_id && isExactOfferPackage\(rawTopCard/);
    assert.match(main, /giveIds: browseEditedPackage\?\.give \?\? canvasPrefill.give/);
    assert.match(main, /<View ref=\{trialCanvasRef\} collapsable=\{false\}>\s*<TradeBuildCanvas/);
    assert.match(main, /signal: browseLive \? signalForExactTrialPackage\(rawTopCard,[\s\S]*?\}, signalForCard\) : undefined/);
    assert.match(main, /if \(card.preserve_server_order === true\) \{\s*const measured = measuredTrialSignalFor\(card\)/);
    assert.match(main, /const dispatchSignal = signalForCard\(rawTopCard\)/);
    assert.match(main, /const signal = firstForThisCard \? signalForCard\(rawTopCard\) : undefined/);
    assert.match(main, /detail_expanded: engagementRef.current.detailExpanded/);
  });
  // Execute the actual screen functions and real transport adapters. This
  // catches asking the clock about rawTopCard while acting on an edited card.
  {
    const parsed = ts.createSourceFile('TradesScreen.tsx', read('src/screens/TradesScreen.tsx'),
      ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const names = ['actionImpressionId', 'signalForCard', 'makePassAttempt',
      'reasonWriteTarget', 'reasonEventProps', 'handleReasonLayer1', 'handleFlagBadTrade'];
    const functions = {};
    const visit = n => {
      if (ts.isFunctionDeclaration(n) && names.includes(n.name?.text)) functions[n.name.text] = n.getText(parsed);
      ts.forEachChild(n, visit);
    };
    visit(parsed);
    const declarations = Object.values(functions).join('\n');
    const exports = Object.keys(functions).join(',');
    const captured = { impression_id: 'i1', dwell_ms: 750, detail_expanded: false, calc_opened: false };
    const original = { ...card, preserve_server_order: true };
    const edited = { ...original, trade_id: 'offer::edited', give_player_ids: ['replacement'] };
    const writes = [];
    const reasonApi = compile(read('src/api/declineReasons.ts'), {
      require: name => { assert.equal(name, './client'); return { api: {
        post: async (route, body) => { writes.push({ route, body: copy(body) }); return { ok: true }; },
      } }; },
    });
    const run = ({ trial, exact, browse = false }) => {
      const raw = trial ? original : { ...original, preserve_server_order: undefined };
      const top = exact ? raw : { ...edited, preserve_server_order: raw.preserve_server_order };
      const attemptRef = { current: null };
      const events = [];
      const pending = [];
      const flags = [];
      const context = { signalV2On: true, rawTopCard: raw, topCard: top,
        browseLive: browse, trialCanvasExact: exact, trialDeckExact: exact,
        measuredTrialSignalFor: () => captured, currentDwellMs: () => 750,
        engagementRef: { current: { detailExpanded: true, calcOpened: false } },
        isExactOfferPackage: pure.isExactOfferPackage,
        captureTradeAction: () => ({ rawId: 'offer' }), reasonPassAttemptRef: attemptRef,
        reasonBankedIdRef: { current: null }, cardRenderedAtRef: { current: 0 },
        Platform: { OS: 'ios' }, track: (...args) => events.push(args),
        setReasonBankedId() {}, advance() {},
        flagMutation: { mutate: args => flags.push(args) }, rerankOn: false,
        swipeUndoOn: false, nextDispositionNotInterestedRef: { current: false }, setToast() {},
        observeReasonRequest: (_attempt, promise) => pending.push(promise),
        postDeclineReason: reasonApi.postDeclineReason };
      const actual = compile(`${declarations}\nmodule.exports = {${exports},
        restoreOriginal: () => { trialDeckExact = true; trialCanvasExact = true; topCard = rawTopCard; }
      };`, context);
      return { actual, raw, top, attemptRef, events, pending, flags };
    };
    const changed = run({ trial: true, exact: false });
    check('RED/GREEN actual trial dispatch drops raw-card signal when the acted package is edited', () => {
      assert.equal(changed.actual.signalForCard(changed.raw), undefined);
      assert.equal(changed.actual.signalForCard(changed.top), undefined);
    });
    await api.swipeTrade(changed.top, 'pass', changed.actual.signalForCard(changed.raw), 'deck');
    check('edited trial swipe transport keeps edited identity/assets but drops original impression', () => {
      assert.equal(request.body.impression_id, undefined);
      assert.equal(request.body.trade_id, 'offer::edited');
      assert.deepEqual(copy(request.body.give_player_ids), ['replacement']);
    });
    changed.actual.handleReasonLayer1('value', 'none');
    await Promise.all(changed.pending);
    check('actual edited layer-1 and captured layer-2 reason targets cannot reuse original attribution', () => {
      assert.equal(writes[0].body.impression_id, undefined);
      assert.equal(writes[0].body.dwell_ms, undefined);
      assert.equal(writes[0].body.trade_id, 'offer::edited');
      assert.deepEqual(writes[0].body.give_player_ids, ['replacement']);
      assert.equal(changed.attemptRef.current.card.impression_id, undefined);
      assert.equal(changed.actual.reasonWriteTarget().impressionId, undefined);
      assert.equal(changed.actual.reasonEventProps().impression_id, 'none');
    });
    changed.actual.handleFlagBadTrade();
    await api.flagBadTrade(changed.flags[0].card, undefined, changed.flags[0].impressionId);
    check('actual edited flag transport and provider-send binding use validated action attribution', () => {
      assert.equal(request.body.impression_id, undefined);
      assert.equal(request.body.trade_id, 'offer::edited');
      assert.deepEqual(copy(request.body.give_player_ids), ['replacement']);
      assert.match(read('src/screens/TradesScreen.tsx'),
        /impressionId=\{signalV2On \? actionImpressionId\(topCard\) : undefined\}/);
    });
    changed.actual.restoreOriginal();
    check('restoring the original display cannot reattribute an already captured edited reason', () => {
      assert.equal(changed.actual.signalForCard(changed.raw).impression_id, 'i1');
      assert.equal(changed.actual.reasonWriteTarget().impressionId, undefined);
      assert.equal(changed.actual.reasonWriteTarget().tradeId, 'offer::edited');
      assert.equal(changed.actual.reasonEventProps().impression_id, 'none');
    });
    const same = run({ trial: true, exact: true, browse: true });
    same.actual.handleReasonLayer1('fit', 'none');
    await Promise.all(same.pending);
    check('original trial reason keeps measured signal even while its visibility timer is paused', () => {
      assert.equal(same.actual.signalForCard(same.raw).impression_id, 'i1');
      assert.equal(writes[1].body.impression_id, 'i1');
      assert.equal(writes[1].body.dwell_ms, 750);
      assert.equal(writes[1].body.detail_expanded, true);
    });
    const legacy = run({ trial: false, exact: false });
    legacy.actual.handleReasonLayer1('value', 'none');
    await Promise.all(legacy.pending);
    check('legacy edited-action signal and decline attribution remain unchanged', () => {
      assert.equal(legacy.actual.signalForCard(legacy.raw).impression_id, 'i1');
      assert.equal(writes[2].body.impression_id, 'i1');
      assert.equal(writes[2].body.trade_id, 'offer::edited');
    });
  }
  console.log(`${count} owner offer signal checks passed`);
})().catch(e => { console.error(e); process.exitCode = 1; });
