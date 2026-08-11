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
// Pinned:
//   1. SendInSleeperButton derives `platform` from the session league cache.
//   2. platform === 'mfl' → it returns <SendInMflButton/> (delegation, not a
//      second mount point), forwarding the same league/opponent/asset props.
//   3. Every other non-Sleeper platform returns null BEFORE the Sleeper
//      button can render (`platform !== 'sleeper'` in the null-gate) — ESPN,
//      Fleaflicker, and any future platform never reach Sleeper's API.
//   4. SendInMflButton self-gates on `trade.send_in_mfl`, proposes ONLY via
//      proposeTradeToMfl (never the Sleeper propose), and carries the
//      registered testID `trades.send-mfl-btn`.
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

  // 1. platform derived from the session league cache.
  if (/const platform\s*=[\s\S]{0,200}?leagues\.find\(/.test(text)) {
    ok('router: platform derived from session league cache');
  } else {
    fail('router: platform derived from session league cache',
         'expected `const platform = leagues.find(...)` in SendInSleeperButton.tsx');
  }

  // 2. An if on platform === 'mfl' whose branch returns <SendInMflButton/>.
  let mflDelegation = null;
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
      }
    });
  });
  if (mflDelegation) {
    ok('router: mfl branch delegates to <SendInMflButton/>');
    const attrs = mflDelegation.attributes.properties
      .filter((p) => ts.isJsxAttribute(p))
      .map((p) => p.name.getText(sf));
    const needed = ['leagueId', 'theirUserId', 'givePlayerIds', 'receivePlayerIds'];
    const missing = needed.filter((a) => !attrs.includes(a));
    if (missing.length === 0) {
      ok('router: delegation forwards league/opponent/asset props');
    } else {
      fail('router: delegation forwards league/opponent/asset props',
           `missing props on <SendInMflButton/>: ${missing.join(', ')}`);
    }
  } else {
    fail('router: mfl branch delegates to <SendInMflButton/>',
         "no `if (platform === 'mfl')` branch returning <SendInMflButton/> found");
  }

  // 3. The null-gate refuses every non-Sleeper platform (not just ESPN).
  let nullGate = false;
  walk(sf, (node) => {
    if (!ts.isIfStatement(node)) return;
    const cond = node.expression.getText(sf).replace(/\s+/g, ' ');
    if (!/platform\s*!==\s*'sleeper'/.test(cond)) return;
    walk(node.thenStatement, (inner) => {
      if (ts.isReturnStatement(inner) && inner.expression &&
          inner.expression.kind === ts.SyntaxKind.NullKeyword) {
        nullGate = true;
      }
    });
  });
  if (nullGate) {
    ok("router: non-Sleeper platforms return null (platform !== 'sleeper')");
  } else {
    fail("router: non-Sleeper platforms return null (platform !== 'sleeper')",
         'expected a null-return gate on `platform !== \'sleeper\'` — an ESPN-only check regresses Fleaflicker/future platforms');
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
}

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll send-button platform-routing checks passed.');
