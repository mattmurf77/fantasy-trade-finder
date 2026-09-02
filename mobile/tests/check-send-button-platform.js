#!/usr/bin/env node
// Platform-routing regression test for the trade send button ("Send in MFL",
// #177 follow-up; extends #146).
//
// WHY THIS EXISTS. Both Sleeper and MFL league ids are numeric, and before
// this feature SendInSleeperButton only self-gated on ESPN — so on an MFL
// league it RENDERED and a tap fired a real write at Sleeper's API for a
// league Sleeper has never heard of (research doc
// docs/plans/send-in-mfl-research-2026-08-11.md §1 "Notable gap"). The fix
// routes by platform in exactly ONE place (SendInSleeperButton, which every
// trade surface already mounts), so no mount point can pick the wrong
// platform's API. This test pins that routing structurally, like
// check-mock-mode-marker.js pins its marker: it parses the real TSX with the
// project's own TypeScript and walks the AST — a grep would pass on a branch
// that drifted inside an unrelated conditional.
//
// Pinned (post-merge with audit P0-6/P0-7 — the platform-generic copy
// fallback and the required `surface` prop):
//   1. SendInSleeperButton derives `platform` via resolveSendPlatform from
//      the session league cache (fail-open to 'sleeper').
//   2. platform === 'mfl' AND `trade.send_in_mfl` ON → it returns
//      <SendInMflButton/> (delegation, not a second mount point), forwarding
//      the same league/opponent/asset props plus the required `surface`.
//      The flag gate MUST live in the routing condition: with the flag OFF
//      an MFL league falls through to the P0-6 fallback (check 3), so
//      flag-off is a stated reason + Copy trade, never a live MFL send and
//      never null.
//   3. Every non-Sleeper platform that can't send (espn, fleaflicker, mfl
//      with the flag off) renders the P0-6 fallback — testIDs
//      `send-in-sleeper.unavailable` + `send-in-sleeper.copy` — and there is
//      NO `platform !== 'sleeper'` null-return gate (that would regress
//      P0-6's copy affordance to nothing).
//   4. SendInMflButton self-gates on `trade.send_in_mfl`, proposes ONLY via
//      proposeTradeToMfl (never the Sleeper propose), carries the registered
//      testID `trades.send-mfl-btn`, and REQUIRES `surface` (P0-7 parity —
//      a mount without it must be a compile error).
//   5. (Send-in-ESPN, 2026-08-11) platform === 'espn' AND `espn.send` ON →
//      the router returns <SendInEspnButton/>, forwarding the same props +
//      `surface`. The flag gate MUST live in the routing condition: with
//      `espn.send` OFF (today: everywhere — the flag is deliberately absent
//      from config/features.json until the auth probe clears, D-026) an ESPN
//      league falls through to the P0-6 fallback (check 3), never null.
//   6. SendInEspnButton self-gates on `espn.send`, proposes ONLY via
//      proposeTradeToEspn (never the Sleeper propose), carries testID
//      `trades.send-espn-btn`, and REQUIRES `surface`.
//   7–8. (#413, 2026-09-02) The Sleeper propose refuses a pick-bearing send
//      with 422 `sleeper_pick_unmapped` / `sleeper_pick_not_owned` instead of
//      sending pick ids to Sleeper as player keys. SendInSleeperButton's
//      doPropose error ladder gives each its own branch that calls
//      Alert.alert and never `goConnect` (a reconnect cannot fix a pick that
//      changed hands — the tempting "refresh" instinct). 7b pins both
//      branches INSIDE the if/else-if chain that starts at
//      `sleeper_not_linked` and ends at the catch-all `else`: a branch
//      appended after that `else` is a second `if` that double-alerts
//      (catch-all first, then the pick copy), so chain membership is the
//      claim. 7c pins the catch-all's own copy so the branches were added,
//      not substituted. Presence of exact wirings, not behavior.
//
// Run: node tests/check-send-button-platform.js
//   (or: npm run test:send-button-platform)

'use strict';

const fs = require('fs');
const path = require('path');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

let failures = 0;
function ok(name) {
  console.log(`PASS  ${name}`);
}
function fail(name, why) {
  failures += 1;
  console.error(`FAIL  ${name}\n      ${why}`);
}

function parse(rel) {
  const file = path.join(__dirname, '..', 'src', 'components', rel);
  const text = fs.readFileSync(file, 'utf8');
  return {
    text,
    sf: ts.createSourceFile(rel, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX),
  };
}

function walk(node, cb) {
  cb(node);
  ts.forEachChild(node, (child) => walk(child, cb));
}

// ── 1–3: SendInSleeperButton is the single platform router ────────────────
{
  const { text, sf } = parse('SendInSleeperButton.tsx');

  // 1. platform derived from the session league cache via the pure resolver
  //    (P0-6's fail-open contract lives — and is unit-tested — in
  //    utils/tradeText.resolveSendPlatform, so the router must use it).
  if (/const platform\s*=\s*resolveSendPlatform\(\s*leagueId\s*,\s*leagues\s*\)/.test(text)) {
    ok('router: platform derived via resolveSendPlatform(leagueId, leagues)');
  } else {
    fail('router: platform derived via resolveSendPlatform(leagueId, leagues)',
         'expected `const platform = resolveSendPlatform(leagueId, leagues)` in SendInSleeperButton.tsx');
  }

  // 2. An if on platform === 'mfl' AND the trade.send_in_mfl flag whose
  //    branch returns <SendInMflButton/>. The flag MUST be part of the
  //    routing condition: that is what makes flag-off MFL fall through to
  //    the P0-6 copy fallback (check 3) instead of a live send or a null.
  let mflDelegation = null;
  let mflCondHasFlag = false;
  walk(sf, (node) => {
    if (!ts.isIfStatement(node)) return;
    const cond = node.expression.getText(sf).replace(/\s+/g, ' ');
    if (!/platform\s*===\s*'mfl'/.test(cond)) return;
    walk(node.thenStatement, (inner) => {
      if (
        (ts.isJsxSelfClosingElement(inner) || ts.isJsxOpeningElement(inner)) &&
        inner.tagName.getText(sf) === 'SendInMflButton'
      ) {
        mflDelegation = inner;
        mflCondHasFlag = /mflEnabled/.test(cond);
      }
    });
  });
  if (mflDelegation) {
    ok('router: mfl branch delegates to <SendInMflButton/>');
    if (mflCondHasFlag &&
        /const mflEnabled\s*=\s*useFlag\('trade\.send_in_mfl'\)/.test(text)) {
      ok('router: mfl delegation is gated on trade.send_in_mfl IN the condition');
    } else {
      fail('router: mfl delegation is gated on trade.send_in_mfl IN the condition',
           "expected `const mflEnabled = useFlag('trade.send_in_mfl')` and `platform === 'mfl' && mflEnabled` — otherwise flag-off MFL hits SendInMflButton's internal null and regresses the P0-6 copy fallback");
    }
    const attrs = mflDelegation.attributes.properties
      .filter((p) => ts.isJsxAttribute(p))
      .map((p) => p.name.getText(sf));
    const needed = ['leagueId', 'theirUserId', 'givePlayerIds', 'receivePlayerIds', 'surface'];
    const missing = needed.filter((a) => !attrs.includes(a));
    if (missing.length === 0) {
      ok('router: delegation forwards league/opponent/asset props + surface');
    } else {
      fail('router: delegation forwards league/opponent/asset props + surface',
           `missing props on <SendInMflButton/>: ${missing.join(', ')}`);
    }
  } else {
    fail('router: mfl branch delegates to <SendInMflButton/>',
         "no `if (platform === 'mfl' ...)` branch returning <SendInMflButton/> found");
  }

  // 2-espn. Same law for ESPN: an if on platform === 'espn' AND the
  //    espn.send flag whose branch returns <SendInEspnButton/>. The flag
  //    MUST be part of the routing condition: that is what makes flag-off
  //    ESPN (today: everywhere) fall through to the P0-6 copy fallback
  //    (check 3) instead of a live send or a null.
  let espnDelegation = null;
  let espnCondHasFlag = false;
  walk(sf, (node) => {
    if (!ts.isIfStatement(node)) return;
    const cond = node.expression.getText(sf).replace(/\s+/g, ' ');
    if (!/platform\s*===\s*'espn'/.test(cond)) return;
    walk(node.thenStatement, (inner) => {
      if (
        (ts.isJsxSelfClosingElement(inner) || ts.isJsxOpeningElement(inner)) &&
        inner.tagName.getText(sf) === 'SendInEspnButton'
      ) {
        espnDelegation = inner;
        espnCondHasFlag = /espnEnabled/.test(cond);
      }
    });
  });
  if (espnDelegation) {
    ok('router: espn branch delegates to <SendInEspnButton/>');
    if (espnCondHasFlag &&
        /const espnEnabled\s*=\s*useFlag\('espn\.send'\)/.test(text)) {
      ok('router: espn delegation is gated on espn.send IN the condition');
    } else {
      fail('router: espn delegation is gated on espn.send IN the condition',
           "expected `const espnEnabled = useFlag('espn.send')` and `platform === 'espn' && espnEnabled` — otherwise flag-off ESPN hits SendInEspnButton's internal null and regresses the P0-6 copy fallback");
    }
    const espnAttrs = espnDelegation.attributes.properties
      .filter((p) => ts.isJsxAttribute(p))
      .map((p) => p.name.getText(sf));
    const espnNeeded = ['leagueId', 'theirUserId', 'givePlayerIds', 'receivePlayerIds', 'surface'];
    const espnMissing = espnNeeded.filter((a) => !espnAttrs.includes(a));
    if (espnMissing.length === 0) {
      ok('router: espn delegation forwards league/opponent/asset props + surface');
    } else {
      fail('router: espn delegation forwards league/opponent/asset props + surface',
           `missing props on <SendInEspnButton/>: ${espnMissing.join(', ')}`);
    }
  } else {
    fail('router: espn branch delegates to <SendInEspnButton/>',
         "no `if (platform === 'espn' ...)` branch returning <SendInEspnButton/> found");
  }

  // 3a. The P0-6 fallback: platforms that can't send (espn/mfl with their
  //     flags off — espn.send is off everywhere today — and fleaflicker)
  //     render the stated reason + Copy trade —
  //     pinned by both registered testIDs inside the !canSend branch.
  let fallbackUnavailable = false;
  let fallbackCopy = false;
  walk(sf, (node) => {
    if (!ts.isIfStatement(node)) return;
    const cond = node.expression.getText(sf).replace(/\s+/g, ' ');
    if (!/^!canSend$/.test(cond.trim())) return;
    walk(node.thenStatement, (inner) => {
      if (ts.isJsxAttribute(inner) && inner.name.getText(sf) === 'testID' && inner.initializer) {
        const v = inner.initializer.getText(sf);
        if (/send-in-sleeper\.unavailable/.test(v)) fallbackUnavailable = true;
        if (/send-in-sleeper\.copy/.test(v)) fallbackCopy = true;
      }
    });
  });
  if (fallbackUnavailable && fallbackCopy) {
    ok('router: !canSend branch renders the P0-6 fallback (unavailable + copy)');
  } else {
    fail('router: !canSend branch renders the P0-6 fallback (unavailable + copy)',
         'expected `if (!canSend)` to render testIDs send-in-sleeper.unavailable and send-in-sleeper.copy — an MFL league with trade.send_in_mfl OFF (and ESPN/Fleaflicker always) must get the copy fallback, not null');
  }

  // 3b. No null-return gate on non-Sleeper platforms — that was the
  //     pre-P0-6 regression this merge had to avoid.
  let nullGate = false;
  walk(sf, (node) => {
    if (!ts.isIfStatement(node)) return;
    const cond = node.expression.getText(sf).replace(/\s+/g, ' ');
    if (!/platform\s*!==\s*'sleeper'|!canSend/.test(cond)) return;
    walk(node.thenStatement, (inner) => {
      if (ts.isReturnStatement(inner) && inner.expression &&
          inner.expression.kind === ts.SyntaxKind.NullKeyword) {
        nullGate = true;
      }
    });
  });
  if (!nullGate) {
    ok('router: no non-Sleeper null-return gate (P0-6 affordance preserved)');
  } else {
    fail('router: no non-Sleeper null-return gate (P0-6 affordance preserved)',
         'a `platform !== \'sleeper\'` / `!canSend` branch returns null — non-Sleeper leagues must render the copy fallback, not nothing');
  }

  // Guard: the old ESPN-only self-gate must not have crept back as the ONLY gate.
  if (/\bisEspn\b(?!League)/.test(text)) {   // isEspnLeague (api/espn) is a fine mention
    fail('router: ESPN-only gate removed',
         '`isEspn` still referenced — platform routing should subsume it');
  } else {
    ok('router: ESPN-only gate removed');
  }
}

// ── 4: SendInMflButton fires only the MFL API, flag-gated, testID'd ──────
{
  const { text, sf } = parse('SendInMflButton.tsx');

  if (/useFlag\('trade\.send_in_mfl'\)/.test(text) &&
      /if \(!enabled\) return null;/.test(text)) {
    ok('mfl button: self-gates on trade.send_in_mfl');
  } else {
    fail('mfl button: self-gates on trade.send_in_mfl',
         "expected useFlag('trade.send_in_mfl') + `if (!enabled) return null;`");
  }

  if (/from '\.\.\/api\/sendInMfl'/.test(text) && /proposeTradeToMfl\(/.test(text)) {
    ok('mfl button: proposes via api/sendInMfl');
  } else {
    fail('mfl button: proposes via api/sendInMfl',
         'expected proposeTradeToMfl(...) imported from ../api/sendInMfl');
  }

  if (/proposeTradeToSleeper/.test(text)) {
    fail('mfl button: never touches the Sleeper propose',
         'proposeTradeToSleeper referenced in SendInMflButton.tsx');
  } else {
    ok('mfl button: never touches the Sleeper propose');
  }

  let hasTestId = false;
  walk(sf, (node) => {
    if (ts.isJsxAttribute(node) && node.name.getText(sf) === 'testID' &&
        node.initializer && /trades\.send-mfl-btn/.test(node.initializer.getText(sf))) {
      hasTestId = true;
    }
  });
  if (hasTestId) {
    ok('mfl button: carries testID trades.send-mfl-btn');
  } else {
    fail('mfl button: carries testID trades.send-mfl-btn',
         'the Maestro flow (flows/trade-send/mfl-send-gating.yaml) selects on this id');
  }

  // P0-7 parity: `surface` is a REQUIRED prop (no `?`), so a mount that
  // forgets it is a compile error — matching SendInSleeperButton's contract.
  if (/surface\s*:\s*SendSurface;/.test(text) && !/surface\?\s*:/.test(text)) {
    ok('mfl button: requires surface: SendSurface (P0-7 parity)');
  } else {
    fail('mfl button: requires surface: SendSurface (P0-7 parity)',
         'expected a required `surface: SendSurface` prop in SendInMflButton Props');
  }

  // ── Send-auth lazy flow (2026-08-11): unlinked MFL routes to an IN-FLOW
  //    sign-in, never a LeaguePicker punt ──────────────────────────────────
  if (/getMflLinkStatus/.test(text) &&
      /from '\.\.\/api\/sendInMfl'/.test(text) &&
      /getMflLinkStatus\(\)/.test(text)) {
    ok('mfl button: up-front link-status check (getMflLinkStatus)');
  } else {
    fail('mfl button: up-front link-status check (getMflLinkStatus)',
         'expected getMflLinkStatus imported from ../api/sendInMfl and called before the send — unlinked users must be offered sign-in, not a propose 409 dead end');
  }

  let mflSheetMounted = false;
  walk(sf, (node) => {
    if ((ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) &&
        node.tagName.getText(sf) === 'MflSignInSheet') {
      mflSheetMounted = true;
    }
  });
  if (mflSheetMounted) {
    ok('mfl button: mounts the in-flow MflSignInSheet');
  } else {
    fail('mfl button: mounts the in-flow MflSignInSheet',
         'expected <MflSignInSheet/> rendered by SendInMflButton — the send path needs an in-flow sign-in surface');
  }

  // The not-connected/expired error branch must open the in-flow sign-in,
  // not navigate to LeaguePicker (the pre-fix dead end).
  let mflReconnectInFlow = false;
  let mflReconnectPunts = false;
  walk(sf, (node) => {
    if (!ts.isIfStatement(node)) return;
    const cond = node.expression.getText(sf).replace(/\s+/g, ' ');
    if (!/mfl_not_connected/.test(cond) || !/mfl_auth_expired/.test(cond)) return;
    const branch = node.thenStatement.getText(sf);
    if (/openSignIn/.test(branch)) mflReconnectInFlow = true;
    if (/LeaguePicker/.test(branch)) mflReconnectPunts = true;
  });
  if (mflReconnectInFlow && !mflReconnectPunts) {
    ok('mfl button: not-connected/expired reconnect is in-flow (no LeaguePicker punt)');
  } else {
    fail('mfl button: not-connected/expired reconnect is in-flow (no LeaguePicker punt)',
         'the mfl_not_connected/mfl_auth_expired branch must open the sign-in sheet (openSignIn) and must NOT navigate to LeaguePicker');
  }
}

// ── 6: SendInEspnButton fires only the ESPN API, flag-gated, testID'd ─────
{
  const { text, sf } = parse('SendInEspnButton.tsx');

  if (/useFlag\('espn\.send'\)/.test(text) &&
      /if \(!enabled\) return null;/.test(text)) {
    ok('espn button: self-gates on espn.send');
  } else {
    fail('espn button: self-gates on espn.send',
         "expected useFlag('espn.send') + `if (!enabled) return null;`");
  }

  if (/from '\.\.\/api\/sendInEspn'/.test(text) && /proposeTradeToEspn\(/.test(text)) {
    ok('espn button: proposes via api/sendInEspn');
  } else {
    fail('espn button: proposes via api/sendInEspn',
         'expected proposeTradeToEspn(...) imported from ../api/sendInEspn');
  }

  if (/proposeTradeToSleeper|proposeTradeToMfl/.test(text)) {
    fail('espn button: never touches another platform\'s propose',
         'proposeTradeToSleeper/proposeTradeToMfl referenced in SendInEspnButton.tsx');
  } else {
    ok('espn button: never touches another platform\'s propose');
  }

  let hasEspnTestId = false;
  walk(sf, (node) => {
    if (ts.isJsxAttribute(node) && node.name.getText(sf) === 'testID' &&
        node.initializer && /trades\.send-espn-btn/.test(node.initializer.getText(sf))) {
      hasEspnTestId = true;
    }
  });
  if (hasEspnTestId) {
    ok('espn button: carries testID trades.send-espn-btn');
  } else {
    fail('espn button: carries testID trades.send-espn-btn',
         'the send-surface testID grammar registers this id');
  }

  // P0-7 parity: `surface` is a REQUIRED prop (no `?`), so a mount that
  // forgets it is a compile error — matching the other twins' contract.
  if (/surface\s*:\s*SendSurface;/.test(text) && !/surface\?\s*:/.test(text)) {
    ok('espn button: requires surface: SendSurface (P0-7 parity)');
  } else {
    fail('espn button: requires surface: SendSurface (P0-7 parity)',
         'expected a required `surface: SendSurface` prop in SendInEspnButton Props');
  }

  // ── Send-auth lazy flow (2026-08-11): unlinked ESPN routes to the IN-FLOW
  //    connect screen, never a "go to the league list" dead end ────────────
  if (/getEspnLinkStatus/.test(text) &&
      /from '\.\.\/api\/sendInEspn'/.test(text) &&
      /getEspnLinkStatus\(\)/.test(text)) {
    ok('espn button: up-front link-status check (getEspnLinkStatus)');
  } else {
    fail('espn button: up-front link-status check (getEspnLinkStatus)',
         'expected getEspnLinkStatus imported from ../api/sendInEspn and called before the send — unlinked users must be offered sign-in, not a propose 409 dead end');
  }

  if (/navigate\(\s*'EspnConnect',\s*\{\s*reason:\s*'send'\s*\}\s*\)/.test(text)) {
    ok("espn button: connects in-flow via EspnConnect with reason:'send'");
  } else {
    fail("espn button: connects in-flow via EspnConnect with reason:'send'",
         "expected navigation.navigate('EspnConnect', { reason: 'send' }) — the reason param is what keeps the connect screen from showing private-league copy to a public-league user");
  }

  // The not-connected/expired error branch must route to the connect screen
  // (goConnect), not navigate to LeaguePicker (the pre-fix dead end).
  // League-LEVEL problems (espn_not_linked / espn_team_unknown) may still
  // route to LeaguePicker — those need a re-link, not a login.
  let espnReconnectInFlow = false;
  let espnReconnectPunts = false;
  walk(sf, (node) => {
    if (!ts.isIfStatement(node)) return;
    const cond = node.expression.getText(sf).replace(/\s+/g, ' ');
    if (!/espn_not_connected/.test(cond) || !/espn_auth_expired/.test(cond)) return;
    const branch = node.thenStatement.getText(sf);
    if (/goConnect/.test(branch)) espnReconnectInFlow = true;
    if (/LeaguePicker/.test(branch)) espnReconnectPunts = true;
  });
  if (espnReconnectInFlow && !espnReconnectPunts) {
    ok('espn button: not-connected/expired reconnect is in-flow (no LeaguePicker punt)');
  } else {
    fail('espn button: not-connected/expired reconnect is in-flow (no LeaguePicker punt)',
         'the espn_not_connected/espn_auth_expired branch must route to the connect screen (goConnect) and must NOT navigate to LeaguePicker');
  }
}

// ── 7–8: #413 pick-refusal branches in SendInSleeperButton's error ladder ──
{
  const { sf } = parse('SendInSleeperButton.tsx');
  const condText = (node) => node.expression.getText(sf).replace(/\s+/g, ' ');
  const UNMAPPED = /code\s*===\s*'sleeper_pick_unmapped'/;
  const NOT_OWNED = /code\s*===\s*'sleeper_pick_not_owned'/;

  // 7 / 8 — presence: an `if` whose condition names the code, whose branch
  // calls Alert.alert and never references goConnect. Every matching `if`
  // must satisfy this, so folding a code into the reconnect branch (whose
  // condition would then also match) is caught even if a dedicated branch
  // survives beside it.
  function branchCheck(label, re) {
    const hits = [];
    walk(sf, (node) => {
      if (ts.isIfStatement(node) && re.test(condText(node))) hits.push(node);
    });
    if (hits.length === 0) {
      fail(label, `no \`if (code === '…')\` branch for this code in SendInSleeperButton.tsx — the 422 would fall to the catch-all and render the server's \`detail\` instead of the count-aware copy`);
      return;
    }
    const bad = hits.filter((node) => {
      const body = node.thenStatement.getText(sf);
      return !/Alert\.alert\(/.test(body) || /goConnect/.test(body);
    });
    if (bad.length === 0) {
      ok(label);
    } else {
      fail(label, 'the branch must call Alert.alert and must NOT reference goConnect — a pick refusal is not an auth error; reconnecting cannot fix it');
    }
  }
  branchCheck('sleeper button: sleeper_pick_unmapped has its own Alert branch, no goConnect', UNMAPPED);
  branchCheck('sleeper button: sleeper_pick_not_owned has its own Alert branch, no goConnect', NOT_OWNED);

  // 7b — reachability: follow elseStatement links from the chain's root
  // (`sleeper_not_linked`) to the terminal non-if `else`, collecting each
  // condition. Both codes must appear IN that chain. A branch appended after
  // the catch-all is a separate `if` that never joins the chain: it would
  // pass 7/8 and double-alert at runtime.
  let root = null;
  walk(sf, (node) => {
    if (!root && ts.isIfStatement(node) && /sleeper_not_linked/.test(condText(node))) root = node;
  });
  const chain = [];
  let finalElse = null;
  for (let cur = root; cur; ) {
    chain.push(condText(cur));
    const next = cur.elseStatement;
    if (next && ts.isIfStatement(next)) { cur = next; continue; }
    finalElse = next || null;
    break;
  }
  const unmappedInChain = chain.some((c) => UNMAPPED.test(c));
  const notOwnedInChain = chain.some((c) => NOT_OWNED.test(c));
  if (root && finalElse && unmappedInChain && notOwnedInChain) {
    ok('sleeper button: both pick branches sit inside the ladder before the catch-all else');
  } else {
    fail('sleeper button: both pick branches sit inside the ladder before the catch-all else',
         !root ? 'could not find the ladder root `if (code === \'sleeper_not_linked\' …)`'
         : !finalElse ? 'the ladder has no terminal `else` — the catch-all was removed'
         : `chain conditions: [${chain.join(' | ')}] — missing ${[!unmappedInChain && 'sleeper_pick_unmapped', !notOwnedInChain && 'sleeper_pick_not_owned'].filter(Boolean).join(', ')}; a branch appended after the catch-all is unreachable through the chain and double-alerts`);
  }

  // 7c — the catch-all still carries its own copy: the branches were added,
  // not swapped in for the fallback every unknown code depends on.
  if (finalElse && /Something went wrong sending to Sleeper/.test(finalElse.getText(sf))) {
    ok('sleeper button: the catch-all else still renders the generic failure copy');
  } else {
    fail('sleeper button: the catch-all else still renders the generic failure copy',
         "expected the terminal `else` to contain 'Something went wrong sending to Sleeper' — unknown codes must keep their fallback");
  }
}

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll send-button platform-routing checks passed.');
