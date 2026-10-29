#!/usr/bin/env node
// B5 (the 11-06 binary copy batch, marketing-lead addendum 10, items 1, 3 and
// 4): each final string pinned word for word, the strings it replaced gone,
// and item 3's gates. D-056: structural, no simulator.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
let checks = 0;
const check = (name, fn) => {
  try { fn(); checks++; } catch (e) { e.message = `${name}: ${e.message}`; throw e; }
};
const once = (src, text) => assert.equal(src.split(text).length - 1, 1, `expected exactly one ${JSON.stringify(text)}`);

check('item 1: the Win Now receipt says "Uncalibrated estimate" in both clients', () => {
  for (const file of ['mobile/src/utils/winNow.ts', 'web/js/win-now.js']) {
    const src = read(file);
    once(src, "'Calibrated model' : 'Uncalibrated estimate'");
    assert.ok(!src.includes('Uncalibrated beta'), `${file} still says "Uncalibrated beta"`);
  }
});

const calc = read('mobile/src/components/InLeagueCalculator.tsx');
check('item 3: the ESPN picks note and its link, word for word', () => {
  once(calc, '<Text style={styles.note}>No draft picks are set up for this ESPN league yet.</Text>');
  once(calc, '<Text style={styles.noteLink}>Set up picks →</Text>');
});
check("item 3: both pick flags on (draft-eng's gates), each hook called every render", () => {
  assert.match(calc, /const picksAssign = useFlag\('picks\.assign'\);/);
  assert.match(calc, /const picksTradeable = useFlag\('picks\.assign_tradeable'\);/);
  assert.match(calc, /const picksSetup = picksAssign && picksTradeable;/);
  assert.ok(!/useFlag\([^)]*\)\s*&&\s*useFlag/.test(calc), 'a short-circuited hook call');
});
check('item 3: the new note shows only with no picks set up (the data test under both flags)', () => {
  assert.match(calc, /\{!picksSupported && picksSetup \? \(\s*<View style=\{styles\.picksNote\}>/);
  // The server side of the claim: with picks.assign_tradeable on,
  // picks_supported is false for an ESPN league only while it has no
  // assigned picks.
  const server = read('backend/server.py');
  assert.match(server, /if not supported and tradeable:\s*\n\s*supported = has_assigned_picks\(league_id\)/);
});
check("item 3: either flag off keeps today's line", () => {
  assert.match(calc, /\{!picksSupported && !picksSetup \? \(\s*<Text style=\{styles\.note\}>Draft picks aren't available for ESPN leagues\.<\/Text>/);
  once(calc, "Draft picks aren't available for ESPN leagues.");
});
check('item 3: the link needs a league and opens PickAssignment on the root stack', () => {
  assert.match(calc, /\{leagueId \? \(\s*<Pressable\s+testID="calc\.picks-setup-link"/);
  assert.match(calc, /if \(navigationRef\.isReady\(\)\) navigationRef\.navigate\('PickAssignment', \{ leagueId \}\);/);
  assert.match(calc, /import \{ navigationRef \} from '\.\.\/navigation\/RootNav';/);
});

check('item 3: no early return before the pick-flag hooks', () => {
  const start = calc.indexOf('export default function InLeagueCalculator(');
  const hooks = calc.indexOf("const picksAssign = useFlag('picks.assign');");
  assert.ok(start >= 0 && hooks > start);
  const body = calc.slice(start, hooks);
  assert.ok(!/\n  (?:if \([^\n]*\)\s*)?return\b/.test(body), 'a component-level return before the hooks');
});
check('item 3: saving picks refreshes the calculator\'s picks (#531 QA P1-1)', () => {
  const pa = read('mobile/src/screens/PickAssignmentScreen.tsx');
  assert.match(calc, /queryKey: \['league-picks', leagueId\]/);
  const inv = "void queryClient.invalidateQueries({ queryKey: ['league-picks', leagueId] });";
  assert.equal(pa.split(inv).length - 1, 2, 'invalidated in both the assign and the seed onSuccess');
  // In the onSuccess handlers, not their onError siblings.
  const assign = pa.slice(pa.indexOf("setToast({ msg: 'Pick updated', tone: 'success' });"));
  assert.ok(assign.indexOf(inv) >= 0 && assign.indexOf(inv) < assign.indexOf('onError:'), 'assign onSuccess');
  const seed = pa.slice(pa.indexOf("setToast({ msg: 'Board saved', tone: 'success' });"));
  assert.ok(seed.indexOf(inv) >= 0 && seed.indexOf(inv) < seed.indexOf('onError:'), 'seed onSuccess');
});

check('item 4: the ShopAsset button and its VoiceOver label, word for word', () => {
  const shop = read('mobile/src/components/ShopOffersBody.tsx');
  once(shop, 'label={`Show it to @${item.counterparty_username}`}');
  once(shop, 'accessibilityLabel={`Show this offer to @${item.counterparty_username} in their Fleeced deck`}');
  assert.ok(!shop.includes('Send this offer'));
  // The same Button as before: its testID and handler are untouched.
  assert.match(shop, /testID="shop\.like-btn"\s*\n\s*label=\{`Show it to @\$\{item\.counterparty_username\}`\}/);
});
check('item 4: the queue toasts, word for word, each on its own branch', () => {
  const q = read('mobile/src/utils/queueCalcTrade.ts');
  assert.match(q, /msg: res\?\.already_queued\s*\n\s*\? `It's already in @\$\{args\.opponent\.name\}'s Fleeced deck\.`\s*\n\s*: `It's waiting in @\$\{args\.opponent\.name\}'s Fleeced deck\.`,/);
  assert.ok(!q.includes('Queued for @') && !q.includes('Already queued for @'));
});
check('item 4: the shop name is normalized to a string, never undefined', () => {
  const t = read('mobile/src/api/trades.ts');
  const fn = t.slice(t.indexOf('function normalizeAssetIdea('));
  assert.match(fn.slice(0, 600), /counterparty_username: String\(raw\?\.counterparty_username \?\? ''\),/);
});

check('no banned words in the shipped strings (read from the source)', () => {
  const shop = read('mobile/src/components/ShopOffersBody.tsx');
  const q = read('mobile/src/utils/queueCalcTrade.ts');
  const strings = [
    ...['mobile/src/utils/winNow.ts', 'web/js/win-now.js'].map(f => read(f).match(/'Calibrated model' : '([^']+)'/)[1]),
    calc.match(/<Text style=\{styles\.note\}>(No draft picks[^<]+)<\/Text>/)[1],
    calc.match(/<Text style=\{styles\.noteLink\}>([^<]+)<\/Text>/)[1],
    shop.match(/label=\{`(Show it to [^`]+)`\}/)[1],
    shop.match(/accessibilityLabel=\{`(Show this offer [^`]+)`\}/)[1],
    ...[...q.matchAll(/`(It's (?:already|waiting) in [^`]+)`/g)].map(m => m[1]),
  ];
  assert.equal(strings.length, 8);
  for (const str of strings) assert.ok(!/\b(beta|read-only|failed|error)\b/i.test(str), str);
});

console.log(`check-b5-copy: ${checks} checks passed`);
