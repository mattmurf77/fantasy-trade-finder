#!/usr/bin/env node
// Pass-reason cadence (flag `trade.pass_reason_cadence`, offer-learnings WS3).
// Scope: docs/plans/offer-learnings/scope-pass-reason-cadence.md
//
// WHY THIS EXISTS. The operator wants a reason only "once every few passes",
// and a deck that never waits. Four properties would each regress silently:
//   1. THE CADENCE — ask after N consecutive passes, then quiet for M passes;
//      a like resets the run. An armed card whose why-pass frame never opened
//      (liked, or swiped) carries the ask. Executed against the real module.
//   2. FLAG OFF NEVER CHANGES ANYTHING — the state never moves, the card's
//      reasons object is returned untouched, the hook adds no props.
//   3. ONE TAP — a chip is the pass and the reason in one write and the deck
//      advances at once (no layer-2 deferral, no undo hold that would let an
//      Undo rewind a pass the reason write already committed).
//   4. THE CHIPS — the operator's six phrases, each on a code the API knows.
//   5. THE FRAME (TestFlight build 186 → operator 2026-11-11) — the asking
//      card keeps its ✕; the ✕ opens a frame over the card; every exit from
//      the frame is a pass; the non-cadence ✕ forms are unchanged.
// Not runtime proof: the TestFlight checklist in the scope block is.
//
// Run: node tests/check-pass-reason-cadence.js  (npm run test:pass-reason-cadence)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
let ts;
try { ts = require('typescript'); } catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const root = path.join(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
let passed = 0;
let failed = 0;
function check(name, fn) {
  try { fn(); passed++; console.log(`PASS  ${name}`); }
  catch (e) { failed++; console.error(`FAIL  ${name}: ${e.message}`); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg || 'assertion failed'); }
function eq(a, b, msg) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${msg || 'not equal'}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`);
  }
}

// ── Execute the real module ────────────────────────────────────────────────
const src = read('src/utils/passReasonCadence.ts');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(src, { compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
} }).outputText, { module: mod, exports: mod.exports, require: () => ({}) });
const C = mod.exports;

/** Feed a sequence and return, per card, whether it was asked (armed).
 *  'p' = pass with the ✕ (on an armed card the ✕ opens the frame, so the pass
 *  is prompted), 's' = swipe / VoiceOver pass (frame never opens), 'l' = like
 *  (frame never opens). */
function run(on, seq, cfg = C.DEFAULT_CADENCE) {
  let s = C.INITIAL_CADENCE;
  const asked = [];
  for (const ch of seq) {
    const armed = C.shouldAsk(on, s, cfg);
    asked.push(armed);
    s = C.recordDisposition(on, s, ch === 'l' ? 'like' : 'pass', cfg, ch === 'p' && armed);
  }
  return asked.map((a) => (a ? 'A' : '.')).join('');
}

check('1a. defaults are the operator starting values (N=3, M=5)', () => {
  eq(C.DEFAULT_CADENCE, { askAfter: 3, quietFor: 5 });
});
check('1b. asks on the card after N consecutive passes, not before', () => {
  eq(run(true, 'pppp'), '...A');
});
check('1c. quiet for exactly M passes after the ask, then asks again', () => {
  // card 4 asked; cards 5–9 are the five quiet passes; card 10 asks (run is 5 ≥ 3).
  eq(run(true, 'pppppppppppppppp'), '...A.....A.....A');
});
check('1d. quiet shorter than N: the run of N still has to rebuild', () => {
  eq(run(true, 'pppppppp', { askAfter: 3, quietFor: 1 }), '...A...A');
});
check('1e. a like resets the run of passes', () => {
  eq(run(true, 'pplpppp'), '......A');
});
check('1f. a like during the quiet period does not shorten it', () => {
  // ask at 4; pass(quiet 4) like pass×3 (quiet 3,2,1) → still quiet; 1 more pass ends it
  // the five quiet passes are cards 5, 7, 8, 9, 10 (card 6 is the like); card 11 asks.
  eq(run(true, 'pppp' + 'p' + 'l' + 'ppp' + 'p' + 'p'), '...A' + '.' + '.' + '...' + '.' + 'A');
});
check('1g. a like ON the armed card (frame never opened) carries the ask', () => {
  // card 4 armed, liked → card 5 still armed; its ✕ spends it → quiet.
  eq(run(true, 'ppplppp' + 'p'), '...AA...');
});
check('1g2. a swipe ON the armed card (frame never opened) carries the ask', () => {
  eq(run(true, 'pppssp' + 'p'), '...AAA.');
});
check('1g3. an unprompted pass of an armed card extends the run, quiet stays 0', () => {
  const ripe = { consecutivePasses: 3, quietRemaining: 0 };
  eq(C.recordDisposition(true, ripe, 'pass', C.DEFAULT_CADENCE, false), { consecutivePasses: 4, quietRemaining: 0 });
  ok(C.recordDisposition(true, ripe, 'like', C.DEFAULT_CADENCE, false) === ripe, 'like moved an armed state');
  eq(C.recordDisposition(true, ripe, 'pass', C.DEFAULT_CADENCE, true), { consecutivePasses: 0, quietRemaining: 5 });
});
check('1h. the asked pass starts a new run (N=1, M=0 asks every other card)', () => {
  eq(run(true, 'pppppp', { askAfter: 1, quietFor: 0 }), '.A.A.A');
});

check('2a. flag off: never asks, however long the run', () => {
  eq(run(false, 'p'.repeat(40)), '.'.repeat(40));
});
check('2b. flag off: the state object never moves', () => {
  const s = { consecutivePasses: 7, quietRemaining: 2 };
  ok(C.recordDisposition(false, s, 'pass', C.DEFAULT_CADENCE, true) === s, 'pass moved the state');
  ok(C.recordDisposition(false, s, 'like', C.DEFAULT_CADENCE, true) === s, 'like moved the state');
});
check('2b2. flag killed mid-run: a ripe state still never asks', () => {
  ok(!C.shouldAsk(false, { consecutivePasses: 9, quietRemaining: 0 }, C.DEFAULT_CADENCE),
    'asked with the flag off');
});
check('2c. no cadence field: the reasons object is returned untouched', () => {
  const r = { onLayer1() {} };
  ok(C.cadenceCardReasons(r) === r, 'reasons object replaced');
  ok(C.cadenceCardReasons(undefined) === undefined, 'undefined not preserved');
});
check('2d. quiet card gets no reasons (plain ✓/✕); asking card keeps them', () => {
  ok(C.cadenceCardReasons({ cadence: { mode: 'quiet' } }) === undefined, 'quiet kept reasons');
  const ask = { cadence: { mode: 'ask' } };
  ok(C.cadenceCardReasons(ask) === ask, 'ask lost reasons');
});

check('3a. server config: valid values pass through', () => {
  eq(C.normalizeCadence({ ask_after: 4, quiet_for: 0 }), { askAfter: 4, quietFor: 0 });
});
check('3b. server config: missing or malformed falls back per field', () => {
  for (const bad of [undefined, null, 'x', {}, { ask_after: 0, quiet_for: -1 },
    { ask_after: 2.5, quiet_for: '5' }, { ask_after: NaN, quiet_for: Infinity }]) {
    eq(C.normalizeCadence(bad), { askAfter: 3, quietFor: 5 }, `for ${JSON.stringify(bad)}`);
  }
});

// ── The chips ──────────────────────────────────────────────────────────────
const api = read('src/api/declineReasons.ts').replace(/\/\/.*$/gm, '');
const layer2 = (api.match(/export type Layer2Code =([\s\S]*?);/) || [])[1] || '';
const codes = [...layer2.matchAll(/'([a-z_]+)'/g)].map((m) => m[1]);
check('4a. the six operator phrases, in order', () => {
  eq(C.PASS_REASON_CHIPS.map((c) => c.label), [
    'Not moving that player', 'Keeping my picks', 'Wrong direction for my team',
    "Don't rate what I'd get", 'Waiting on something', 'Value too low',
  ]);
});
check('4b. every chip is a known Layer2Code under its own parent', () => {
  for (const c of C.PASS_REASON_CHIPS) {
    ok(codes.includes(c.detail), `${c.detail} not in Layer2Code`);
    ok(c.detail.startsWith(`${c.reason}_`), `${c.detail} not under ${c.reason}`);
  }
});
check('4c. mapping onto existing codes; only the two missing ones are new', () => {
  eq(C.PASS_REASON_CHIPS.map((c) => c.detail), [
    'other_player_keep', 'other_picks_keep', 'fit_outlook',
    'other_player_avoid', 'other_waiting', 'value_giving',
  ]);
});

// ── Wiring ────────────────────────────────────────────────────────────────
const screen = read('src/screens/TradesScreen.tsx');
const sf = ts.createSourceFile('TradesScreen.tsx', screen, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function fnText(name) {
  let out = '';
  const visit = (n) => {
    if (ts.isFunctionDeclaration(n) && n.name && n.name.text === name) out = n.getText(sf);
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}
const adv = fnText('advance');
const l1 = fnText('handleReasonLayer1');
check('5a. advance() records every disposition exactly once, after both guards', () => {
  const hits = adv.split('passCadence.record(decision)').length - 1;
  eq(hits, 1, 'record calls in advance');
  const g = adv.indexOf('guardBlockRef.current.key = null');
  ok(g > 0 && adv.indexOf('passCadence.record(decision)') > g, 'record runs before the guards');
  eq(screen.split('passCadence.record(').length - 1, 1, 'record calls in the screen');
});
check('5b. a reasoned pass (passAttempt supplied) never enters the undo hold', () => {
  // Merged with roster-first setup's `heldPass` (#637): one condition, read by
  // both the undo hold and the roster-setup pass trigger.
  ok(/const heldPass = swipeUndoOn && decision === 'pass' && !declineReasonsOn\s*&& !opts\?\.passAttempt && !!passAttempt;\s*if \(heldPass && passAttempt\)/.test(adv),
    'undo hold condition lost its !opts?.passAttempt');
});
check('5c. a chip (detail) advances at once: one POST, no deferral, no banking', () => {
  ok(/\.\.\.\(detail \? \{ detail \} : \{\}\)/.test(l1), 'detail not in the layer-1 POST');
  const i = l1.indexOf("if (detail) return advance('pass', { passAttempt: attempt });");
  ok(i > 0, 'chip advance missing');
  ok(i < l1.indexOf('reasonBankedIdRef.current = rawId'), 'chip path banks the card first');
  ok(/if \(detail\) track\('trade_pass_layer2', \{ reason, detail, has_free_text: false, \.\.\.reasonEventProps\(\) \}/.test(l1),
    'chip answer does not fire trade_pass_layer2');
  eq((l1.match(/postDeclineReason\(/g) || []).length, 1, 'layer-1 POST count');
});
check('5d. the deck card gets the cadence-filtered reasons and never the overlay while asking', () => {
  ok(screen.includes('reasons: cadenceCardReasons(declineReasons),'), 'card reasons not filtered');
  ok(screen.includes('reasonsAsOverlay={reasonsAsOverlay && !declineReasons?.cadence}'), 'overlay not suppressed');
});
check('5e. reason props: built when either flag is on, cadence props spread in', () => {
  ok(/declineReasonProps: DispositionReasons \| undefined = declineReasonsOn \|\| passCadence\.on\s*\?\s*\{\s*\.\.\.passCadence\.cardProps,/.test(screen),
    'declineReasonProps definition');
});
check('5f. the screen footprint stays small', () => {
  const lines = screen.split('\n').filter((l) => /passCadence|cadenceCardReasons|usePassReasonCadence/.test(l));
  ok(lines.length <= 9, `${lines.length} cadence lines in TradesScreen`);
});

const hook = read('src/hooks/usePassReasonCadence.ts');
check('6a. hook: flag off adds no props and never moves state', () => {
  ok(hook.includes("useFlag('trade.pass_reason_cadence')"), 'flag key');
  ok(/if \(!on\) return \{ on, record, cardProps: \{\} \};/.test(hook), 'flag-off cardProps not {}');
  ok(/const record = useCallback\(\s*\(decision: 'like' \| 'pass'\) => \{\s*if \(!on\) return;/.test(hook), 'record not inert when off');
});
check('6b. hook: N and M come from the server payload', () => {
  ok((hook.match(/normalizeCadence\(fetchedPassReasonCadence\(\)\)/g) || []).length === 2, 'config source');
  const flags = read('src/api/flags.ts');
  ok(/_passReasonCadence = res\?\.pass_reason_cadence;/.test(flags), 'flags.ts does not capture pass_reason_cadence');
});
check('6c. hook: prompt events are the two registered names', () => {
  ok(hook.includes("'pass_reason_prompt_shown'") && hook.includes("'pass_reason_prompt_dismissed'"), 'event names');
});
check('6d. hook: "shown" (frame opened) is what makes a pass spend the ask', () => {
  ok(/onShown: \(tradeId: string\) => \{\s*shownRef\.current = true;\s*track\(\s*'pass_reason_prompt_shown'/.test(hook),
    'onShown does not mark the frame shown before tracking');
  ok(/const prompted = shownRef\.current;\s*shownRef\.current = false;/.test(hook), 'record does not read-and-clear the marker');
  ok(hook.includes('recordDisposition(on, s, decision, cfg, prompted)'), 'record does not pass prompted');
});

const card = read('src/components/TradeCard.tsx');
check('7a. TradeCard: a cadence card mounts no inline panel/row under the card', () => {
  ok(card.includes('{disposition.reasons?.cadence ? null : disposition.reasons && !reasonsAsOverlay ? ('),
    'the cadence card is not excluded from the inline panel slot');
  eq((card.match(/<PassReasonChips\b/g) || []).length, 1, 'PassReasonChips mounts');
});
check('7b. TradeCard: a chip is onLayer1 with its detail; Just pass is the plain pass', () => {
  ok(card.includes("onChip={(r, d) => disposition.reasons!.onLayer1(r, 'none', d)}"), 'chip wiring');
  ok(/onSkip=\{\(\) => \{\s*disposition\.reasons!\.cadence!\.onDismissed\(data\.trade_id\);\s*disposition\.onPass\(\);\s*\}\}/.test(card),
    'Just pass wiring');
});
// Build 186 ("a card with no pass button") → operator 2026-11-11: the asking
// card keeps its ✕; the ✕ opens the frame over the card.
const passBtnAt = card.indexOf('testID="trades.pass-btn"');
const passBtnJsx = passBtnAt > 0
  ? card.slice(card.lastIndexOf('<Pressable', passBtnAt), card.indexOf('</Pressable>', passBtnAt)) : '';
check('7d. TradeCard: the ✕ unmounts only for the inline tile form, never on the asking card', () => {
  ok(passBtnJsx, 'trades.pass-btn not found');
  ok(card.includes('{disposition.reasons && !reasonsAsOverlay && !disposition.reasons.cadence ? null : ('),
    '✕ mount condition does not keep it on the cadence card (or no longer drops it for the inline tiles)');
  ok(/const passBtnMounted =\s*!!disposition && !\(disposition\.reasons && !reasonsAsOverlay && !disposition\.reasons\.cadence\);/.test(card),
    'passBtnMounted (guide target trades.pass-btn) does not follow the ✕ mount condition');
});
check('7e. TradeCard: on the asking card the ✕ opens the frame and does not pass', () => {
  ok(/: disposition\.reasons\?\.cadence\s*\?\s*\(\) => setReasonOverlayOpen\(true\)\s*: disposition\.onPass/.test(passBtnJsx),
    '✕ on the cadence card does not open the frame (or the plain-pass fallback is gone)');
});
check('7f. TradeCard: the frame mounts only when opened, after every card block', () => {
  const at = card.indexOf('{disposition?.reasons?.cadence && reasonOverlayOpen ? (');
  ok(at > 0, 'frame mount is not gated on cadence + open');
  // Only the Matches-only footer (never on a deck card; pinned last by
  // check-match-value-section S-2) may follow — the frame must cover the card.
  const tail = card.slice(at, card.indexOf('export default React.memo(TradeCardComp);'));
  ok(/\) : null\}\s*\{footer \?\? null\}\s*<\/View>\s*\);\s*\}\s*$/.test(tail), 'something other than the footer renders after the frame');
});
const chipsSrc = read('src/components/PassReasonChips.tsx');
check('7g. frame: covers the card, every exit is onSkip, modal region', () => {
  ok(/frame: \{\s*\.\.\.StyleSheet\.absoluteFillObject/.test(chipsSrc), 'frame is not an absolute fill over the card');
  ok(/backgroundColor: scrim,/.test(chipsSrc), 'scrim is not the scrim token');
  ok(/accessibilityViewIsModal\s*onAccessibilityEscape=\{skip\}/.test(chipsSrc), 'not a modal region with escape = pass');
  ok(/testID="trades\.pass-reason-scrim"\s*style=\{styles\.scrim\}\s*onPress=\{skip\}/.test(chipsSrc), 'scrim tap is not the pass');
  ok(/hardwareBackPress', \(\) => \{\s*if \(!disabledRef\.current\) skipRef\.current\(\);\s*return true;/.test(chipsSrc), 'Android back is not the pass');
  ok(/testID="trades\.pass-reason-skip"\s*onPress=\{skip\}/.test(chipsSrc), 'Just pass is not onSkip');
  ok(/testID="trades\.pass-reason-close"\s*onPress=\{skip\}/.test(chipsSrc), 'the close control is not onSkip');
  ok(/accessibilityLabel="Close and pass on this trade"/.test(chipsSrc), 'close a11y label does not say it passes');
  ok(/<Icon name="x" size=\{16\} color=\{pressed \? chalk\.base : chalk\.dim\} \/>/.test(chipsSrc), 'close is not a neutral chalk ✕');
  ok(/close: \{\s*width: 44,\s*height: 44,/.test(chipsSrc), 'close is under the 44pt floor');
  ok(/const skip = \(\) => \{\s*if \(!disabled\) onSkip\(\);\s*\};/.test(chipsSrc), 'skip ignores disabled');
  ok(/AccessibilityInfo\.setAccessibilityFocus\(node\)/.test(chipsSrc), 'focus does not move into the frame');
  ok(/Your answer helps us find better trades for you\./.test(chipsSrc), 'model-help copy line');
});
check('7c. chips: no truncation, 44pt floor, radius ≤ 8, no emoji, no blur', () => {
  ok(!/blur|BlurView|LinearGradient/i.test(chipsSrc), 'blur / gradient');
  ok(!/numberOfLines\s*=/.test(chipsSrc), 'truncates');
  ok(/minHeight: 44/.test(chipsSrc), 'touch floor');
  ok(!/borderRadius:\s*(9|[1-9]\d)/.test(chipsSrc), 'radius > 8');
  ok(!/[\u{1F300}-\u{1FAFF}]/u.test(chipsSrc), 'emoji');
});

// ── 8. Panel placement (coordinator review 2026-11-11) ────────────────────
// The deck card sits in a ScrollView and can be taller than the screen; a
// panel centred in the card opened off screen — the build-186 bug again.
// Executed: the whole panel ends inside the visible viewport after the
// returned scroll, and inside the card's padding, for every ✕ position.
const PAD = 12, EDGE = 8;
function landed(inp) {
  const p = C.placeWhyPassPanel({ pad: PAD, edge: EDGE, ...inp });
  const winTop = inp.frameWinY + p.top - p.scrollBy;
  return { ...p, winTop, winBottom: winTop + inp.panelH };
}
check('8a. ✕ at the BOTTOM edge of a tall card: panel lifted fully on screen, no scroll', () => {
  // viewport 100–800; card 1500 tall, top 600 above the screen; row at window 780.
  const r = landed({ anchorY: 1380, panelH: 320, frameH: 1500, frameWinY: -600, visTop: 100, visBottom: 800 });
  eq(r.scrollBy, 0, 'scrollBy');
  ok(r.winTop >= 108 && r.winBottom <= 792, `panel at ${r.winTop}–${r.winBottom}`);
});
check('8b. ✕ at the TOP edge of a tall card: panel dropped fully on screen, no scroll', () => {
  const r = landed({ anchorY: 1120, panelH: 320, frameH: 1500, frameWinY: -1000, visTop: 100, visBottom: 800 });
  eq(r.scrollBy, 0, 'scrollBy');
  ok(r.winTop >= 108 && r.winBottom <= 792, `panel at ${r.winTop}–${r.winBottom}`);
});
check('8c. room on screen: centred on the ✓/✕ row', () => {
  const r = landed({ anchorY: 400, panelH: 300, frameH: 900, frameWinY: 0, visTop: 100, visBottom: 800 });
  eq([r.top, r.scrollBy], [250, 0]);
});
check('8d. card mostly scrolled away: the page scrolls the panel in', () => {
  // only 108–150 of the card is visible; nothing fits without a scroll.
  const r = landed({ anchorY: 1110, panelH: 320, frameH: 1150, frameWinY: -1000, visTop: 100, visBottom: 800 });
  ok(r.scrollBy < 0, `scrollBy ${r.scrollBy}`);
  ok(r.winTop >= 108 && r.winBottom <= 792, `panel at ${r.winTop}–${r.winBottom}`);
});
check('8e. panel taller than the viewport: top-aligned, so label + copy + first chips show', () => {
  const r = landed({ anchorY: 600, panelH: 500, frameH: 1200, frameWinY: -200, visTop: 100, visBottom: 400 });
  eq(r.winTop, 108, 'panel top');
});
check('8f. sweep: ✕ anywhere on screen ⇒ whole panel on screen and inside the card', () => {
  let n = 0;
  for (const frameH of [420, 700, 1100, 1600]) {
    for (const panelH of [260, 340]) {
      if (panelH > frameH - 2 * PAD) continue;
      for (let frameWinY = -1400; frameWinY <= 760; frameWinY += 37) {
        for (let anchorY = 40; anchorY <= frameH - 40; anchorY += 53) {
          const rowWin = frameWinY + anchorY;
          if (rowWin < 128 || rowWin > 772) continue; // the ✕ (56pt) is on screen
          const r = landed({ anchorY, panelH, frameH, frameWinY, visTop: 100, visBottom: 800 });
          n++;
          ok(r.top >= PAD - 1e-9 && r.top + panelH <= frameH - PAD + 1e-9,
            `outside card: frameH ${frameH} panel ${panelH} y ${frameWinY} a ${anchorY} top ${r.top}`);
          ok(r.winTop >= 108 - 1e-9 && r.winBottom <= 792 + 1e-9,
            `off screen: frameH ${frameH} panel ${panelH} y ${frameWinY} a ${anchorY} → ${r.winTop}–${r.winBottom}`);
        }
      }
    }
  }
  ok(n > 500, `only ${n} cases`);
});
check('8g. wiring: TradeCard anchors on the ✓/✕ row; the frame places, hides, falls back', () => {
  ok(/onLayout=\{\s*disposition\.reasons\?\.cadence\s*\?\s*\(e\) => \{\s*actionRowMidRef\.current = e\.nativeEvent\.layout\.y \+ e\.nativeEvent\.layout\.height \/ 2;/.test(card),
    'the ✓/✕ row is not measured (cadence card only)');
  ok(card.includes('anchorY={actionRowMidRef.current}'), 'anchorY not passed to the frame');
  ok(/const p = placeWhyPassPanel\(\{ \.\.\.base, frameWinY, visTop, visBottom \}\);/.test(chipsSrc), 'frame does not place through placeWhyPassPanel');
  ok(/opacity: placed \? 1 : 0/.test(chipsSrc), 'panel is visible before it is placed');
  ok(/scroller\?\.measureViewport\) scroller\.measureViewport\(/.test(chipsSrc), 'the deck viewport is not used');
  ok(/scroller\.scrollTo\(Math\.max\(0, scroller\.getScrollY\(\) \+ p\.scrollBy\), true\)/.test(chipsSrc), 'scroll fallback missing');
  ok(/const fallback = setTimeout\(/.test(chipsSrc), 'no fallback when a measurement never answers');
  ok(/measureViewport: \(cb\) =>\s*mainScrollRef\.current\?\.getNativeScrollRef\(\)\?\.measureInWindow\(/.test(screen),
    'TradesScreen does not expose the deck ScrollView viewport');
});

// ── 9. The "Passed" toast offers Undo only when there is something to undo ─
check('9a. Undo action only on a held pass (a reasoned / unheld pass gets a plain "Passed")', () => {
  ok(adv.includes("action: heldPass ? { label: 'Undo', onPress: undoPass } : undefined,"),
    'Undo action is not gated on heldPass');
  eq((screen.match(/onPress: undoPass/g) || []).length, 1, 'undoPass toast actions');
});

console.log(`\ncheck-pass-reason-cadence: ${passed} passed, ${failed} failed`);
if (failed) process.exitCode = 1;
