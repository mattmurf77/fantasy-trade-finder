#!/usr/bin/env node
// #384 W2 — the behaviour rulings, and the properties that keep each one
// honest when the flag is off.
//
// Run: node tests/check-calc-merged-behavior.js

'use strict';

const fs = require('fs');
const path = require('path');
const SRC = path.join(__dirname, '..', 'src');
let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures++; console.log(`  ✗ ${name}`); if (detail) console.log(`      ${detail}`); }
}
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const card = read('components/TradeCard.tsx');
const trades = read('screens/TradesScreen.tsx');
const screen = read('screens/TradeCalculatorScreen.tsx');
const calcSrc = read('components/InLeagueCalculator.tsx');
const featured = read('components/FeaturedTradeWindow.tsx');

console.log('check-calc-merged-behavior:');

// ── Ruling 1: the ✕ survives and pops an overlay; inline tiles stay OFF-path
//
// The overlay's scope is BOTH halves of one expression in the host: the flag
// (the feature exists) AND `deckOrigin === 'calculator'` (this deck is the one
// the calculator sent). Round-2 ruling 1 is "this calculator only" — a bare
// flag read inside TradeCard, which is what W2 shipped, gave the overlay to
// every deck for every user (review #7).
assert(!/useFlag\(\s*['"]calc\.merged_layout['"]\s*\)/.test(card),
  '1a. TradeCard reads NO flag for the overlay — it is a prop',
  'a flag read inside the card cannot know where the deck came from');
assert(/reasonsAsOverlay\?:\s*boolean/.test(card),
  '1b. TradeCard takes `reasonsAsOverlay` as a prop');
// Anchored to the STATEMENT TERMINATOR. Without the `;` the assertion matched
// `= calcMergedOn && deckOrigin === 'calculator' || true;` — the overlay on
// every deck for every user, which is the exact leak this line exists to stop.
assert(/const\s+reasonsAsOverlay\s*=\s*calcMergedOn\s*&&\s*deckOrigin\s*===\s*['"]calculator['"];/
  .test(trades),
  '1c. the host gates the overlay on the flag AND a calculator origin',
  'either half alone — or anything OR-ed onto the end — leaks the overlay '
  + 'onto decks the operator did not scope it to');
assert((trades.match(/const\s+reasonsAsOverlay\s*=/g) || []).length === 1,
  '1c-bis. there is exactly one definition of the overlay gate');
{
  const at = trades.indexOf('declineReasons={declineReasonProps}');
  const seg = trades.slice(at, at + 300);
  assert(/reasonsAsOverlay=\{reasonsAsOverlay\}/.test(seg),
    '1d. the top-card mount carrying `disposition` is passed the overlay flag');
}
// The origin is a one-shot, not a sticky mode: four clearing paths.
assert(/finderHandoff\.origin\s*===\s*['"]calculator['"]/.test(trades),
  '1e. the origin comes off the consumed handoff');
assert((trades.match(/setDeckOrigin\(null\)/g) || []).length >= 3,
  '1f. deckOrigin is cleared on league switch / pins emptied / mode switch',
  'a sticky origin would keep the overlay after the deck stopped being the calculator\'s');

// The ✕ must be RESTORED in overlay mode — the shipped form deletes it.
assert(/disposition\.reasons\s*&&\s*!reasonsAsOverlay\s*\?\s*null\s*:\s*\(/.test(card),
  '2. overlay mode keeps the single ✕ button',
  'the pass button is still suppressed whenever reasons are wired');

// Exactly one presentation at a time. Both mounted = two reason panels.
assert(/disposition\.reasons\s*&&\s*!reasonsAsOverlay\s*\?\s*\(\s*<DeclineReasonPanel/.test(card),
  '3. the inline panel is suppressed in overlay mode');
assert(/disposition\.reasons\s*&&\s*reasonsAsOverlay\s*\?\s*\(\s*<Modal/.test(card),
  '4. the overlay panel mounts only in overlay mode');

// Review #1 — layer 1 does NOT advance the deck. `handleReasonLayer1` banks
// the pass with `advance('pass', { deferDeckAdvance: true })` and only
// `commitReasonAdvance` (reached from layer 2) fronts the next card. Closing
// the sheet on the layer-1 tile therefore left the card banked with ✓/✕/swipe/
// VoiceOver all inert and layer 2 unreachable — a dead end on every card the
// overlay touched. The two ADVANCING callbacks still close.
// Each callback's own expression only. An earlier draft used a fixed 160/260
// char window, which let assertion 6 read the NEXT prop's body and fail on a
// close that wasn't its own — a window, not the code, was being tested.
function propBody(src, name) {
  const at = src.indexOf(`${name}={(`);
  if (at < 0) return null;
  // Balance braces from the prop's opening `{` to its partner.
  let i = src.indexOf('{', at + name.length);
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(i, j + 1); }
  }
  return null;
}
for (const cb of ['onLayer2Select', 'onLayer2Send']) {
  const body = propBody(card, cb);
  assert(!!body && /setReasonOverlayOpen\(false\)/.test(body),
    `5. ${cb} closes the overlay before committing`,
    body ? 'the sheet would stay up over the next card' : 'prop not found');
}
// ...and layer 1 must NOT close: it banks the pass and DEFERS the advance, so
// closing here strands the card with layer 2 unreachable.
{
  const body = propBody(card, 'onLayer1');
  assert(!!body && !/setReasonOverlayOpen\(false\)/.test(body),
    '5. onLayer1 does NOT close the overlay',
    'the pass is banked but the deck has not advanced — layer 2 must stay reachable');
}
// ...and onLayer2Bank must NOT close: it banks a code and opens a text box.
{
  const body = propBody(card, 'onLayer2Bank');
  assert(!!body && !/setReasonOverlayOpen\(false\)/.test(body),
    '6. onLayer2Bank does NOT close the overlay',
    'banking opens the free-text composer — closing would destroy the input');
}
// A backdrop dismiss AFTER a banked tile must commit the deferred advance, or
// the card is stranded exactly as a layer-1 close would have left it.
assert(/onOverlayDismissed\?\.\(banked\)/.test(card),
  '6a. a backdrop dismiss reports whether a tile was already banked');
assert(/function handleReasonOverlayDismissed\(banked: boolean\)[\s\S]{0,240}?if \(banked\) commitReasonAdvance\(\);/
  .test(trades),
  '6b. the host commits the deferred advance on a dismiss-after-bank',
  'without it the pass is written, the card is inert and nothing can front the next one');
// The composer must clear the keyboard inside the Modal — the host ScrollView
// the inline form scrolls is not reachable from there.
assert(/<KeyboardAvoidingView[\s\S]{0,700}?testID="trades\.pass-reason-overlay"/.test(card)
  && /behavior=\{Platform\.OS === 'ios' \? 'padding' : undefined\}/.test(card),
  '6c. the overlay sheet is inside a KeyboardAvoidingView (padding on iOS)');
assert(/onRevealRequest=\{disposition\.reasons!\.onRevealRequest\}/.test(card),
  '6d. the overlay passes onRevealRequest through, as the inline mount does');

// ── Ruling 8: the two end-of-deck exits, both gated
assert(/calcMergedOn\s*=\s*useFlag\(\s*['"]calc\.merged_layout['"]\s*\)/.test(trades),
  '7. TradesScreen reads the merged flag');
// Review #9 — BOTH exhausted branches carry both exits. They used to live only
// inside the `deck.replenishment` summary card, so a finished deck with that
// flag off (or with no disposition tallied) was a dead end.
for (const id of [
  'trades.deck-summary.back-to-calc',
  'trades.deck-summary.unpin-retry',
  'trades.deck-exhausted.back-to-calc',
  'trades.deck-exhausted.unpin-retry',
]) {
  const at = trades.indexOf(`testID="${id}"`);
  assert(at >= 0, `8. ${id} exists`);
  const before = trades.slice(Math.max(0, at - 700), at);
  assert(/calcMergedOn/.test(before), `8. ${id} is gated on the merged flag`,
    'it would appear on the shipped deck, where there is no calculator-first flow');
}
// The unpin exit must reuse handleClearPin — it restores the pre-pin deck
// snapshot and fires trade_pin_cleared. A hand-rolled unpin would do neither.
// And it must REGENERATE: handleClearPin alone leaves an empty deck, which is
// not the search the button's label promises.
{
  const at = trades.indexOf('function handleUnpinRetry()');
  assert(at >= 0, '9. handleUnpinRetry is the single unpin-exit handler');
  const seg = trades.slice(at, at + 1200);
  assert(/handleClearPin\(\)/.test(seg),
    '9. the unpin exit reuses handleClearPin',
    'a second unpin path would skip the snapshot restore and the analytics event');
  assert(/handleFindTrades\(/.test(seg),
    '9a. the unpin exit regenerates through the Find-a-Trade dispatch',
    'clearing the pins and stopping leaves the user staring at an empty deck');
}
// Review #9 — the exit renders for ANY pin count, and names the pin only when
// there is exactly one to name.
for (const id of ['trades.deck-summary.unpin-retry', 'trades.deck-exhausted.unpin-retry']) {
  const at = trades.indexOf(`testID="${id}"`);
  const before = trades.slice(Math.max(0, at - 300), at);
  assert(/pinCount > 0/.test(before),
    `10. ${id} shows for any pin count`,
    'gating on `singlePin` gave a 1-send + 1-receive canvas no unpin path at all');
}
assert(/pinCount === 1\s*\?\s*`Search without \$\{[^`]*\}`\s*:\s*'Search without the pinned players'/
  .test(trades),
  '10a. the label names the single pin, or says "the pinned players"');
// Review #9 — the back-to-calculator exit must carry the #190 prefill shape:
// a truthy prefill is what forces league mode and suppresses the auto-tour.
{
  const at = trades.indexOf('function handleBackToCalculator()');
  assert(at >= 0, '10b. handleBackToCalculator is the single back-to-calc handler');
  const seg = trades.slice(at, at + 1400);
  assert(/navigate\?\.\('TradeCalculator',\s*\{\s*prefill:/.test(seg),
    '10c. it navigates with a `prefill` object',
    'a bare navigate resets the calculator to Real values with an empty canvas');
  assert(/giveIds: pinnedGive\.map/.test(seg) && /receiveIds: pinnedReceive\.map/.test(seg),
    '10d. the canvas is rebuilt from the pins');
  assert(/scopedOpponent \? \{ opponentUserId: scopedOpponent \}/.test(seg),
    '10e. the partner rides along when one is scoped, and the prefill survives without one');
}

// ── D-153 (W6-B): the canvas is ALWAYS the anchor, and it never touches the
// pin store. The Include-players toggle is gone — the operator ruled "C works"
// — so the fork is decided by the canvas ITSELF: a give side means the
// fairness sweep, an empty canvas means the model deck.
assert(/useFinderTargets/.test(screen),
  '11. the finder hand-off goes through useFinderTargets');
assert(!/requireAssets/.test(screen),
  '12. no parallel requireAssets route param survives',
  'an invented param nothing reads would silently do nothing');
assert(!/includePlayers/.test(screen) && !/includePlayers/.test(calcSrc),
  '12a. no Include-players toggle survives anywhere on the calculator',
  'the control was REMOVED with its ruling; a leftover would be a switch with '
  + 'no contract behind it');
// D-158 (Wave B0, 2026-08-24) — the fork MOVED. It used to be inline in
// `TradeCalculatorScreen.onFindATrade`; the canvas now has two hosts (the
// pushed page and TradesScreen's inline mount), so the decision and its
// `calc_find_a_trade_tapped` row live in `utils/canvasSearch.forkCanvasSearch`
// and both hosts call it. The CONTRACT is unchanged and is still pinned here
// — only the file it is pinned in moved.
const fork = read('utils/canvasSearch.ts');
{
  // THE contract. The anchor is present iff the canvas has a GIVE side — the
  // fair sweep prices a give package, so a receive-only canvas is "empty" and
  // must fall to the model. `giveIds.length > 0` is the whole predicate;
  // anything looser (`|| receiveIds.length`) sends an unpriceable anchor.
  assert(/const fair = giveIds\.length > 0;/.test(fork),
    '13. the fair fork is decided by the GIVE side alone',
    'a receive-only canvas has nothing to price — it is the model deck\'s case');
  assert(/anchor: fair \? \{ giveIds, receiveIds \} : null,/.test(fork),
    '13a. the fork carries an anchor iff the canvas has a give side',
    'an unconditional anchor routes an empty canvas to a sweep with no '
    + 'anchor; an absent one silently reverts the whole feature to the model');
  assert(/path: fair \? 'fair' : 'model',/.test(fork),
    '13b. the analytics prop reports which fork was actually taken');
  // 13c — ONE definition, and both hosts go through it. A second inline fork
  // in either host is how the two entry points start pricing the same canvas
  // differently, which is the whole reason this was extracted.
  assert((fork.match(/export function forkCanvasSearch/g) || []).length === 1,
    '13c. forkCanvasSearch is defined exactly once');
  assert(/forkCanvasSearch\(/.test(screen) && /forkCanvasSearch\(/.test(trades),
    '13c-bis. both hosts of the canvas call it',
    'the pushed page and the inline landing must reach the same verdict');
  assert((screen.match(/track\(\s*\n?\s*['"]calc_find_a_trade_tapped['"]/g) || []).length === 0
      && (trades.match(/track\(\s*\n?\s*['"]calc_find_a_trade_tapped['"]/g) || []).length === 0,
    '13d. neither host emits calc_find_a_trade_tapped itself',
    'a second emitter is a second fork decision in disguise');
}
{
  const at = screen.indexOf('onFindATrade={(');
  const seg = screen.slice(at, at + 3000);
  assert(/\.\.\.\(anchor \? \{ fairAnchor: anchor \} : \{\}\)/.test(seg),
    '13e. the pushed page\'s handoff carries the fork\'s anchor verbatim',
    're-deriving the anchor here would re-introduce the second fork');
  // The pin-store writes W5 needed are GONE. The anchor travels in the
  // handoff and then in the request body; writing pins here would leave a
  // constraint behind for whatever search ran next (which is the only reason
  // the old `t.clear()` existed).
  assert(!/setSide\('give'/.test(seg) && !/setSide\('receive'/.test(seg)
      && !/setPackageMode\(/.test(seg) && !/t\.clear\(\)/.test(seg),
    '14. onFindATrade writes NO pins',
    'the canvas no longer rides the pin store — a write here strands a '
    + 'constraint on the next model search');
}
// The deck side of the same contract: a fairAnchor must NOT arm the model.
{
  const at = trades.indexOf('const autoRunOrigin = autoRunOriginRef.current;');
  const seg = trades.slice(Math.max(0, at - 1200), at);
  assert(/const fairAnchor = fairAnchorRef\.current;\s*\n\s*if \(fairAnchor\) \{/.test(seg),
    '15. the choke point takes the fair fork BEFORE the model gate',
    'reading the anchor after the generate dispatch runs both searches');
  assert(/runFairPackages\(fairAnchor\);[\s\S]{0,300}?return;/.test(seg),
    '15a. …and RETURNS, so a fair arrival never dispatches a generate',
    'falling through to the model gate is the exact sabotage this pins');
}
assert(/autoRunPendingRef\.current = !fair;/.test(trades),
  '16. the model auto-run is armed only when there is no fair anchor',
  '`= true` makes every calculator arrival run the model as well');
assert(!/finderHandoff\.includePlayers/.test(trades),
  '16a. the deck reads no includePlayers field',
  'the field is gone from FinderHandoff — a read here is a stale contract');
{
  // The fair deck's cards are built with the SHARED helper, so they carry the
  // give/receive ids, the counterparty and the server `fairpk_` trade_id that
  // `_reconstruct_swipe_card` needs. A hand-rolled card here is how a swipe
  // starts failing with "Unknown trade_id".
  assert(/setDeck\(res\.ideas\.map\(\(idea\) => ideaToCard\(idea, leagueId\)\)\)/.test(trades),
    '16b. the fair deck is built through utils/ideaToCard',
    'a local card literal drops whatever field the swipe reconstruct needs');
  assert(/from '\.\.\/utils\/ideaToCard'/.test(trades)
      && /from '\.\.\/utils\/ideaToCard'/.test(featured),
    '16c. both the deck and the featured window import the ONE helper');
}
{
  // The fair deck has no pins, so the W5 unpin-retry must not render on it —
  // it would be a button that unpinned nothing. "Search all trades" is its
  // replacement, and it runs the MODEL for the same partner.
  for (const id of ['trades.deck-summary.unpin-retry',
                    'trades.deck-exhausted.unpin-retry']) {
    const at = trades.indexOf(`testID="${id}"`);
    const before = trades.slice(Math.max(0, at - 300), at);
    assert(/!fairDeck/.test(before), `16d. ${id} does NOT render on a fair deck`,
      'there are no pins on a fair deck — the anchor rode the request body');
  }
  for (const id of ['trades.deck-summary.search-all',
                    'trades.deck-exhausted.search-all']) {
    const at = trades.indexOf(`testID="${id}"`);
    assert(at >= 0, `16e. ${id} exists`);
    const before = trades.slice(Math.max(0, at - 300), at);
    assert(/fairDeck/.test(before), `16e. ${id} renders only on a fair deck`);
  }
  const at = trades.indexOf('function handleSearchAllTrades()');
  assert(at >= 0, '16f. handleSearchAllTrades is the single search-all handler');
  const seg = trades.slice(at, at + 500);
  assert(/track\(\s*'deck_search_all_tapped'/.test(seg),
    '16g. the exit emits deck_search_all_tapped');
  assert(/handleFindTrades\(/.test(seg),
    '16h. …and dispatches the MODEL search through the shared entry point',
    'a private dispatch would skip the nudge-clearing and the fairDeck reset');
}
// Review #3/#9 — a calculator hand-off has to actually generate, including
// when no partner was chosen (the Team dropdown is optional there).
assert(/autoRunOrigin === ['"]calculator['"]/.test(trades),
  '17. the auto-run choke point knows a calculator hand-off from a league offer');
{
  const at = trades.indexOf('const autoRunOrigin = autoRunOriginRef.current;');
  const seg = trades.slice(at, at + 1400);
  assert(/scopedOpponent \|\| \(autoRun && autoRunOrigin === ['"]calculator['"]\)/.test(seg),
    '17a. a calculator hand-off generates with no scoped opponent',
    'gated on scopedOpponent alone, an unscoped canvas search never fires');
  // Re-keyed 2026-08-29 (canvas-results QA round): the choke point's
  // dispatch is dispatchGenerate — the same single mutate wrapped with the
  // browse-session lifecycle. Still the one choke point, still no new site.
  assert(/dispatchGenerate\(\{\}\)/.test(seg),
    '17b. it dispatches through the existing #330 choke point, not a new mutate site');
}

// ── #384 W6-A (D-151): the confirm cell queues the package ───────────────
//
// The cell shipped W1–W5 as a PERMANENTLY disabled control: nothing passed
// `onLikeTrade`, so `disabled={!onLikeTrade || ...}` was always true while
// beat n15 and the checklist described it as working (Q-029, review #5).
// These assertions exist so that state cannot return silently.
const calc = read('components/InLeagueCalculator.tsx');
const api = read('api/trades.ts');

// 18 — the SCREEN passes the handler. This is the whole regression: drop the
// prop and the cell is dead again, with every other assertion still green.
assert(/onLikeTrade=\{async \(\{ giveIds, receiveIds, opponent \}\) => \{/.test(screen),
  '18. the screen passes onLikeTrade to InLeagueCalculator',
  'without a handler the confirm cell is permanently disabled — the Q-029 state');
// D-158 (Wave B0, 2026-08-24) — the queue body MOVED to
// `utils/queueCalcTrade.ts` for the same reason the fork did: two hosts, one
// implementation. The screen still owns its Toast (it renders the descriptor
// the helper returns), which is why 18e now pins the DESCRIPTOR, not a local
// `setToast` call.
const queueUtil = read('utils/queueCalcTrade.ts');
{
  assert(/queueTradeForOpponent\(\{/.test(queueUtil),
    '18a. the shared helper calls the queue route, not a local no-op');
  assert(/opponentUserId: args\.opponent\.userId/.test(queueUtil),
    '18b. it addresses the partner the canvas chose',
    'the route is per-counterparty; a missing opponent id cannot be defaulted');
  assert((queueUtil.match(/track\(\s*\n?\s*['"]calc_trade_queued['"]/g) || []).length === 1,
    '18c. one calc_trade_queued event is emitted');
  assert(/queued: false, reason: res\?\.reason \?\? ['"]error['"]/.test(queueUtil),
    '18d. a refusal carries its reason, and a dead request carries `error`',
    'an event with no reason cannot tell a refusal from a network failure');
  assert(/msg: queueRefusalLine\(res\?\.reason, args\.opponent\.name\)/.test(queueUtil),
    '18e. the refusal toast is reason-specific',
    'a generic failure line is the dishonest state the disabled cell stood in for');
  // 18h — ONE implementation, and BOTH hosts call it. A host that rebuilds
  // the request inline is a second emitter of `calc_trade_queued` and a
  // second copy of the refusal table.
  assert((queueUtil.match(/export async function queueCalcTrade/g) || []).length === 1,
    '18h. queueCalcTrade is defined exactly once');
  assert(/queueCalcTrade\(\{/.test(screen) && /queueCalcTrade\(\{/.test(trades),
    '18h-bis. both hosts of the canvas call it');
  assert(!/queueTradeForOpponent\(/.test(screen) && !/queueTradeForOpponent\(/.test(trades),
    '18i. neither host calls the queue route directly',
    'bypassing the helper skips the analytics row and the refusal copy');
}
// 18f — every server reason has a line. The enum is a cross-client invariant;
// a reason with no case falls to the generic default and the user learns
// nothing.
for (const r of ['likes_you_off', 'not_league_member', 'assets_not_on_roster',
                 'opponent_untouchable', 'opponent_not_interested',
                 'fails_fairness_floor']) {
  assert(new RegExp(`case '${r}':`).test(queueUtil),
    `18f. queueRefusalLine handles '${r}'`);
  assert(new RegExp(`'${r}'`).test(api),
    `18g. CalcQueueReason declares '${r}'`);
}

// 19 — the disabled rule. Anchored to the whole expression: an unconditional
// `disabled` (or an `|| true`, or dropping the `onLikeTrade` term so a
// handler-less mount looks enabled) all fail here.
{
  const at = calc.indexOf('testID="calc.action.confirm"');
  assert(at > -1, '19. the confirm cell still exists');
  const seg = calc.slice(at, at + 900);
  assert(/disabled=\{!onLikeTrade \|\| !bothSides \|\| !opponent \|\| queueing\}/.test(seg),
    '19a. the confirm cell is disabled exactly for: no handler, half a trade, no partner, in flight',
    'a broader rule re-creates the permanently-dead control (Q-029)');
  assert(/onLikeTrade\(\{\s*giveIds,\s*receiveIds,\s*opponent: \{ userId: opponent\.user_id/
    .test(seg),
    '19b. the press hands the opponent up — the screen has no other source for it');
  assert(/setQueueing\(true\)/.test(seg) && /\.finally\(\(\) => setQueueing\(false\)\)/.test(seg),
    '19c. the in-flight lock is set before the call and released after it',
    'without the release a single tap disables the cell for the life of the mount');
}
// 19d — the queue is NOT a second like-recording path on the client either:
// the calculator must not reach for swipeTrade.
assert(!/swipeTrade\(/.test(calc) && !/swipeTrade\(/.test(screen),
  '19d. the calculator does not fake a swipe to record the like',
  'the queue route owns the record path; a client-side swipe would skip the '
  + 'counterparty-preference check entirely');

console.log(failures === 0
  ? 'check-calc-merged-behavior: all assertions passed'
  : `check-calc-merged-behavior: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
