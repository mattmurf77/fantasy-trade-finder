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

// ── Ruling 2: Include players writes the SHIPPED pin store, not a new param
assert(/useFinderTargets/.test(screen),
  '11. the finder hand-off goes through useFinderTargets');
assert(!/requireAssets/.test(screen),
  '12. no parallel requireAssets route param survives',
  'an invented param nothing reads would silently do nothing');
{
  const at = screen.indexOf('onFindATrade={(');
  // W5 grew this handler (analytics + the tour hand-off + the #330 handoff),
  // so the window is sized to the whole prop body, not to W2's shape.
  const seg = screen.slice(at, at + 3000);
  // The TOGGLE has to be inside the pin condition, not merely somewhere in
  // the handler. `if (give.length || receive.length)` pins the canvas with
  // Include players switched OFF — the search is then constrained by assets
  // the user explicitly excluded, and it is the precise case the operator's
  // ruling 2 and checklist step 13 are about. Verified green against the old
  // three assertions, which only looked for the calls.
  assert(/if \(includePlayers && \(give\.length \|\| receive\.length\)\) \{/.test(seg),
    '13a. `includePlayers` is IN the pin condition, not just in the handler',
    'the toggle must gate the write; a canvas-only condition pins with Include OFF');
  assert(/setSide\('give'/.test(seg) && /setSide\('receive'/.test(seg),
    '13. include-ON pins both sides of the canvas');
  assert(/setPackageMode\(true\)/.test(seg),
    '14. include-ON sets packageMode — the contract that makes "must include" literal');
  assert(/t\.clear\(\)/.test(seg),
    '15. include-OFF clears stale pins',
    'a leftover pin would re-apply the constraint the user just switched off');
}
// Review #16 — the deck re-asserts it on consumption. Belt-and-braces: the
// calculator already clears, but a pin that survived would silently re-apply
// the constraint the user just switched off.
assert(/finderHandoff\.includePlayers === false/.test(trades),
  '16. the deck re-checks the pins are empty on an include-OFF hand-off');
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
  assert(/generateMutation\.mutate\(\{\}\)/.test(seg),
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
{
  const at = screen.indexOf('onLikeTrade={async (');
  const seg = screen.slice(at, at + 2200);
  assert(/queueTradeForOpponent\(\{/.test(seg),
    '18a. the handler calls the queue route, not a local no-op');
  assert(/opponentUserId: opponent\.userId/.test(seg),
    '18b. it addresses the partner the canvas chose',
    'the route is per-counterparty; a missing opponent id cannot be defaulted');
  assert(/track\(\s*['"]calc_trade_queued['"]/.test(seg),
    '18c. one calc_trade_queued event is emitted');
  assert(/queued: false, reason: res\?\.reason \?\? ['"]error['"]/.test(seg),
    '18d. a refusal carries its reason, and a dead request carries `error`',
    'an event with no reason cannot tell a refusal from a network failure');
  assert(/queueRefusalLine\(res\?\.reason, opponent\.name\)/.test(seg),
    '18e. the refusal toast is reason-specific',
    'a generic failure line is the dishonest state the disabled cell stood in for');
}
// 18f — every server reason has a line. The enum is a cross-client invariant;
// a reason with no case falls to the generic default and the user learns
// nothing.
for (const r of ['likes_you_off', 'not_league_member', 'assets_not_on_roster',
                 'opponent_untouchable', 'opponent_not_interested',
                 'fails_fairness_floor']) {
  assert(new RegExp(`case '${r}':`).test(screen),
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
