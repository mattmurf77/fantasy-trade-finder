#!/usr/bin/env node
// #531 follow-up (operator, 2026-11-01: "The intent is that the trade gets
// sent on the platform they play on, not in our app."): the ShopAsset tile's
// primary action proposes the trade on the league's platform through the
// existing send router, SendInSleeperButton (Sleeper / MFL / ESPN by
// platform), never the Fleeced deck queue (queueCalcTrade →
// POST /api/trades/queue). Send-only, head-eng 11-01: no queue, no likes-you
// card. The ✕ dismiss is unchanged. The router's own behaviour (confirm,
// outcome-unknown, per-platform blocks, copy) is pinned by
// check-send-button-platform.js and the platform suites.
//
// Run: node tests/check-shop-send.js
//   (or: npm run test:shop-send)

'use strict';

const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'src');
const read = (f) => fs.readFileSync(path.join(SRC, f), 'utf8');

const shop = read('components/ShopOffersBody.tsx');
const tradeText = read('utils/tradeText.ts');

let passed = 0;
let failed = 0;
function check(name, ok, detail) {
  if (ok) {
    passed += 1;
    console.log(`  ok   ${name}`);
  } else {
    failed += 1;
    console.log(`  FAIL ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

console.log('check-shop-send: Shop proposes on the platform, never queues');

// The one router mount on the tile, with the idea's own trade.
const mounts = shop.match(/<SendInSleeperButton[\s\S]*?\/>/g) || [];
check('the tile mounts SendInSleeperButton once', mounts.length === 1, `found ${mounts.length}`);
const mount = mounts[0] || '';
const props = {
  leagueId: /\bleagueId=\{leagueId\}/,
  theirUserId: /\btheirUserId=\{item\.counterparty_user_id\}/,
  givePlayerIds: /\bgivePlayerIds=\{item\.give_player_ids\}/,
  receivePlayerIds: /\breceivePlayerIds=\{item\.receive_player_ids\}/,
  givePlayerNames: /\bgivePlayerNames=\{item\.give\.map\(\(p\) => p\.name\)\}/,
  receivePlayerNames: /\breceivePlayerNames=\{item\.receive\.map\(\(p\) => p\.name\)\}/,
  opponentUsername: /\bopponentUsername=\{item\.counterparty_username\}/,
  surface: /\bsurface="shop"/,
};
for (const [name, re] of Object.entries(props)) {
  check(`the router gets ${name} from the idea`, re.test(mount));
}
check('the router is imported', /import SendInSleeperButton from '\.\/SendInSleeperButton';/.test(shop));

// Never the deck queue.
check('the Shop body never calls queueCalcTrade', !/\bqueueCalcTrade\s*\(/.test(shop));
check('the Shop body never names /api/trades/queue', !shop.includes('/api/trades/queue'));
check('the old queue button is gone (shop.like-btn, "Show it to")',
  !shop.includes('shop.like-btn') && !shop.includes('Show it to @') && !shop.includes('handleLike'));
check('only the QueueToast type is imported from queueCalcTrade',
  /import type \{ QueueToast \} from '\.\.\/utils\/queueCalcTrade';/.test(shop));

// The ✕ dismiss is unchanged.
check('the ✕ dismiss still dispatches handleDismiss',
  /testID="shop\.dismiss-btn"\s*\n\s*onPress=\{\(\) => handleDismiss\(item\)\}/.test(shop));

// head-eng 11-01, option A: each platform router tags a Shop send's propose
// request `source: 'shop'` (and only a Shop send's), so the server can record
// #531's kept Elo half. The payload types carry the optional field.
const TAG = "...(surface === 'shop' ? { source: 'shop' as const } : {}),";
const routers = {
  Sleeper: ['components/SendInSleeperButton.tsx', 'proposeTradeToSleeper', 'api/sendInSleeper.ts', 'ProposeTradePayload'],
  MFL: ['components/SendInMflButton.tsx', 'proposeTradeToMfl', 'api/sendInMfl.ts', 'ProposeMflTradePayload'],
  ESPN: ['components/SendInEspnButton.tsx', 'proposeTradeToEspn', 'api/sendInEspn.ts', 'ProposeEspnTradePayload'],
};
for (const [plat, [file, fn, apiFile, type]] of Object.entries(routers)) {
  const src = read(file);
  const call = (src.match(new RegExp(`await ${fn}\\(\\{[\\s\\S]*?\\}\\);`)) || [''])[0];
  check(`${plat}: the propose call tags source 'shop' only when surface is 'shop'`, call.includes(TAG), call ? 'tag missing' : 'call not found');
  check(`${plat}: the tag is the only source the propose call sends`, (call.match(/\bsource:/g) || []).length === 1);
  check(`${plat}: surface is read, not discarded`, !/surface: _surface/.test(src));
  const apiSrc = read(apiFile);
  const body = (apiSrc.match(new RegExp(`export interface ${type} \\{[\\s\\S]*?\\n\\}`)) || [''])[0];
  check(`${plat}: ${type} carries source?: 'shop'`, /\n  source\?: 'shop';/.test(body));
}

// The analytics dimension.
check("SendSurface includes 'shop'",
  /export type SendSurface = [^;]*'shop'[^;]*;/.test(tradeText) &&
  /export const SEND_SURFACES[^;]*'shop'[^;]*;/.test(tradeText));

console.log(`\n${passed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
