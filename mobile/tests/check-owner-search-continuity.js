#!/usr/bin/env node
'use strict';
// WHY THIS EXISTS: receive-only canvas selections vanished at the handoff,
// Retry changed request families, and synchronous anchored searches looked
// idle/forever-loading. Execute the actual request helper; source assertions
// prove wiring only. Navigation still requires the manual TestFlight checks.
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const ts = require('typescript');
const root = path.resolve(__dirname, '../src');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const mod = { exports: {} };
new Function('module', 'exports', ts.transpileModule(read('utils/tradeSearchRequest.ts'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText)(mod, mod.exports);
const { modelSelectionParams, reconcileCanvasScope } = mod.exports;
const pins = { giveIds: ['old-send'], receiveIds: ['old-target'] };
const receive = { giveIds: [], receiveIds: ['selected-target'] };
assert.deepEqual(modelSelectionParams(receive, pins, false, true), {
  pinned_give_players: undefined,
  pinned_receive_players: ['selected-target'],
  pinned_give_mode: undefined,
});
assert.deepEqual(modelSelectionParams({ giveIds: [], receiveIds: [] }, pins, true, true), {
  pinned_give_players: undefined, pinned_receive_players: undefined, pinned_give_mode: undefined,
});
assert.deepEqual(modelSelectionParams(null, pins, true, true).pinned_receive_players, ['old-target']);
assert.equal(modelSelectionParams(null, pins, false, true).pinned_receive_players, undefined);
const packageSelection = { giveIds: ['a', 'b'], receiveIds: ['c'] };
const payload = modelSelectionParams(packageSelection, pins, true, false);
assert.equal(payload.pinned_give_mode, 'all');
packageSelection.giveIds.push('later');
assert.deepEqual(payload.pinned_give_players, ['a', 'b']);
assert.equal(modelSelectionParams(null, { giveIds: ['a', 'b'], receiveIds: [] }, true, false).pinned_give_mode, undefined);

const searchedB = { opponentId: 'B', give: ['give'], receive: ['from-B'] };
assert.equal(reconcileCanvasScope(searchedB, 'A', 'A'), searchedB);
assert.equal(reconcileCanvasScope(searchedB, 'A', 'B'), searchedB);
const scopedC = reconcileCanvasScope(searchedB, 'A', 'C', ['edited-give']);
assert.deepEqual(scopedC, { opponentId: 'C', give: ['edited-give'], receive: [] });
assert.deepEqual(reconcileCanvasScope(searchedB, 'A', null), {
  opponentId: undefined, give: ['give'], receive: [],
});
assert.deepEqual(reconcileCanvasScope(scopedC, 'C', null), {
  opponentId: undefined, give: ['edited-give'], receive: [],
});
assert.deepEqual(reconcileCanvasScope(null, null, 'C', ['unsaved-draft']), {
  opponentId: 'C', give: ['unsaved-draft'], receive: [],
});

const trades = read('screens/TradesScreen.tsx');
const calc = read('screens/TradeCalculatorScreen.tsx');
const canvas = read('components/TradeBuildCanvas.tsx');

// Execute the screen's ACTUAL mutation function with only its dependencies
// stubbed: a helper-only test would miss a rank-return caller losing the
// consumed one-shot selection. The source guards below separately pin the
// semantic-regeneration call sites to repeat:true.
const ast = ts.createSourceFile('TradesScreen.tsx', trades, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let requestFn;
function visit(node) {
  if (ts.isPropertyAssignment(node) && node.name.getText(ast) === 'mutationFn'
      && node.initializer.getText(ast).includes('lastModelRequestRef')) requestFn = node.initializer;
  ts.forEachChild(node, visit);
}
visit(ast);
assert.ok(requestFn, 'actual model mutation function found');
const modelRef = { current: null };
const canvasRef = { current: { giveIds: [], receiveIds: ['selected-target'] } };
let storePins = { pinnedGive: [{ id: 'old-send' }], pinnedReceive: [{ id: 'old-target' }], packageMode: true };
const env = {
  useFinderTargets: { getState: () => storePins },
  lastModelRequestRef: modelRef, canvasSelectionRef: canvasRef,
  effectiveFairness: 0.9, leagueId: 'league', targetingEnabled: true,
  scopedOpponent: 'partner-B', tradeIntent: 'tier_up', modelSelectionParams,
  generateTrades: (request) => request,
};
const requestJs = ts.transpileModule(`module.exports = ${requestFn.getText(ast)};`, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const mutate = new Function('env', `const { ${Object.keys(env).join(', ')} } = env;
  const module = { exports: {} }; ${requestJs}; return module.exports;`)(env);
const first = mutate({});
assert.deepEqual(first.pinned_receive_players, ['selected-target']);
assert.equal(first.pinned_give_players, undefined);
assert.equal(canvasRef.current, null, 'one-shot canvas was consumed');
const rankReturnRequest = mutate({ force: true, repeat: true });
assert.deepEqual(rankReturnRequest.pinned_receive_players, ['selected-target']);
assert.equal(rankReturnRequest.opponent_user_id, 'partner-B');
assert.equal(rankReturnRequest.trade_intent, 'tier_up');
assert.equal(rankReturnRequest.force, true);
assert.equal(mutate({ repeat: true }).force, undefined, 'ordinary repeat does not inherit force');
modelRef.current = null; // the explicit-new-target reset
storePins = { pinnedGive: [], pinnedReceive: [{ id: 'new-target' }], packageMode: true };
assert.deepEqual(mutate({}).pinned_receive_players, ['new-target']);
assert.match(calc, /canvasSelection: \{ giveIds: fork.giveIds, receiveIds: fork.receiveIds \}/);
assert.match(trades, /canvasSelection: finderHandoff.canvasSelection/);
assert.match(trades, /canvasSelectionRef.current = rp.canvasSelection \?\? null/);
assert.match(trades, /modelSelectionParams\(canvasSelectionRef.current/);
assert.match(trades, /runFairPackages\(fairRequest.anchor, fairRequest.opponentId, source\)/);
assert.match(trades, /vars.repeat && lastModelRequestRef.current/);
assert.match(trades, /dispatchGenerate\(\{ repeat: true \}\)/);
assert.match(trades, /\.\.\.lastModelRequestRef.current,\s*fairness_threshold: effectiveFairness,\s*trade_intent: tradeIntent \?\? undefined/);
assert.match(trades, /if \(rp.tradeIntent !== undefined\) setTradeIntent\(rp.tradeIntent\)/);
assert.equal((trades.match(/\.\.\.\(fairnessReady \? \{ fairnessOn \} : \{\}\),\s*tradeIntent,/g) || []).length, 2);
assert.match(trades, /if \(!finderHubOn \|\| !finderMode \|\| !fairnessReady\) return/);
const rankReturn = trades.slice(trades.indexOf('consumePendingQuicksetRegen()'), trades.indexOf('// Item 8: first-Quick-Set-save'));
assert.match(rankReturn, /dispatchGenerate\(\s*\{ force: true, repeat: true \}/);
const suppressionUndo = trades.slice(trades.indexOf('async function handleSuppressionUndo()'), trades.indexOf('// #190 — hand the top card'));
assert.match(suppressionUndo, /if \(deckEpochRef.current !== epoch\) return;\s*resetDeckForNewTargets\(\);\s*lastModelRequestRef.current = request;\s*dispatchGenerate\(\{ force: true, repeat: true \}\)/);
const fairFn = trades.slice(trades.indexOf('async function runFairPackages('), trades.indexOf('const pinCount ='));
assert.match(fairFn, /fairness_threshold: effectiveFairness/);
assert.match(fairFn, /setFairPending\(true\)/);
assert.match(fairFn, /finally[\s\S]*deckEpochRef.current === epoch[\s\S]*setFairPending\(false\)/);
assert.match(trades, /!fairDeck &&\s*deck.length === 0/);
assert.match(trades, /fairPending \|\| generateMutation.isPending/);
assert.match(trades, /fairDeck && !fairPending \? \(/);
assert.match(trades, /testID="trades.fair-empty"/);
assert.match(trades, /testID="trades.fair-empty.back"/);
assert.match(trades, /canvasSelectionRef.current = null;[\s\S]*lastFairRequestRef.current = null;[\s\S]*setCanvasPrefill\(null\)/);
const inline = trades.slice(trades.indexOf('function handleInlineFindATrade('), trades.indexOf('async function handleInlineLikeTrade('));
const push = inline.slice(inline.indexOf('if (resultsPushLive)'), inline.indexOf('return;'));
assert.doesNotMatch(push, /setSheetOpponent\(/);
assert.match(inline, /if \(resultsPushLive && resultsPushPendingRef.current\) return/);
assert.match(canvas, /give: opts.give.map\(\(p\) => p.id\)/);
assert.match(canvas, /receive: opts.receive.map\(\(p\) => p.id\)/);
assert.match(canvas, /previousLeagueRef.current === leagueId/);
assert.match(canvas, /reconcileCanvasScope\(prefill, previousOpponentRef.current, opponentUserId, latestGiveRef.current\)/);
assert.match(canvas, /previousOpponentRef.current = opponentUserId;\s*setPrefill\(activePrefill\)/);
assert.match(canvas, /latestGiveRef.current = give;\s*onSidesChange\?\.\(give, receive\)/);
assert.match(canvas, /key=\{`\$\{leagueId\}-/);
console.log('owner-search-continuity: executable request cases and structural wiring passed');
