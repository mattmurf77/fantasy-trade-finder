#!/usr/bin/env node
// WHY THIS EXISTS: fairness-off re-sorted different models' incompatible
// mismatch scores, silently destroying the server's experiment positions.
// Execute the actual orderedDeck memo body; no React/simulator approximation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const filename = path.join(__dirname, '../src/screens/TradesScreen.tsx');
const text = fs.readFileSync(filename, 'utf8');
const source = ts.createSourceFile(filename, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let body, featuredBody, rerankBody;
function visit(node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(source) === 'orderedDeck') {
    assert.ok(ts.isCallExpression(node.initializer));
    const callback = node.initializer.arguments[0];
    assert.ok(ts.isArrowFunction(callback) && ts.isBlock(callback.body));
    body = callback.body.getText(source).slice(1, -1);
  }
  if (ts.isVariableDeclaration(node) && node.name.getText(source) === 'bestIdea') {
    featuredBody = node.initializer.arguments[0].body.getText(source).slice(1, -1);
  }
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'applySessionRerank') {
    rerankBody = node.body.getText(source).slice(1, -1);
  }
  ts.forEachChild(node, visit);
}
visit(source);
assert.ok(body, 'must execute actual orderedDeck callback');
const compute = new Function('deck', 'fairnessOn', 'laneFilter', 'canvasResultsOn', 'browseSession', body);
const run = (deck, fairness = false, lane = null, canvas = false, browse = null) =>
  compute(deck, fairness, lane, canvas, browse);
const owner = { id: 'owner', match_score: 1, lane: 'value', preserve_server_order: true };
const control = { id: 'control', match_score: 999, lane: 'value', preserve_server_order: true };
const outlook = { id: 'outlook', match_score: 500, lane: 'window', preserve_server_order: true };
const deck = [owner, control, outlook];
assert.strictEqual(run(deck), deck, 'trial: fairness off retains exact server order');
assert.strictEqual(run(deck, true), deck, 'trial: fairness on retains exact server order');
assert.deepEqual(run(deck, false, 'value'), [owner, control], 'lane filtering never ranks across models');
assert.deepEqual(run(deck, false, 'window'), [outlook]);
assert.deepEqual(deck, [owner, control, outlook], 'projection never mutates the captured deck');
const ordinary = [{ id: 'a', match_score: 1 }, { id: 'b', match_score: 2 }];
assert.deepEqual(run(ordinary).map(c => c.id), ['b', 'a'], 'flag-off legacy order unchanged');
assert.strictEqual(run(ordinary, true), ordinary, 'legacy fairness-on unchanged');
assert.strictEqual(run(ordinary, false, null, true, {}), ordinary, 'existing browse order freeze retained');
const pinned = { id: 'liked', match_score: -1, likesYou: true };
assert.deepEqual(run([...ordinary, pinned]).map(c => c.id), ['liked', 'b', 'a'], 'legacy likes-you pin retained');
const malformed = [{ ...ordinary[0], preserve_server_order: 'true' }, ordinary[1]];
assert.deepEqual(run(malformed).map(c => c.id), ['b', 'a'], 'only a real boolean true marks trial order');
assert.ok(rerankBody && featuredBody);
// No closure stubs: the trial must return before touching learning/reorder state.
new Function('card', rerankBody)({ preserve_server_order: true });
const bestIdea = new Function('assetIdeasQuery', featuredBody);
const desired = { id: 'desired', model_arm: 'owner_v1', recommendation_rank: 0, difference: 0 };
const lessSuitable = { id: 'gain', model_arm: 'owner_v1', recommendation_rank: 1, difference: 999 };
assert.strictEqual(bestIdea({ data: { groups: { upgrade: [lessSuitable], lateral: [desired], downgrade: [] } } }), desired,
  'featured treatment respects joint suitability order, not largest market gain');
const oldA = { id: 'oldA', difference: 1 }, oldB = { id: 'oldB', difference: 2 };
assert.strictEqual(bestIdea({ data: { groups: { upgrade: [oldA], lateral: [oldB], downgrade: [] } } }), oldB,
  'legacy featured selection is unchanged');
console.log('Owner trial order: 13 executable checks passed.');
