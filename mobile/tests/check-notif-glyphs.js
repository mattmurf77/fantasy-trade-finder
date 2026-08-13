#!/usr/bin/env node
// Cross-client notification-type parity (notif-inbox-growth, 2026-08-13).
//
// WHY THIS EXISTS. `notifications.type` is a cross-client enum with FOUR
// independent consumers and no shared source:
//
//   mobile  ROW_GLYPHS          (src/components/TopBar.tsx)   → the glyph
//   mobile  V2_*_KINDS          (src/utils/deepLinks.ts)      → the tap
//   web     notifTypeIcon       (web/js/app.js)               → the glyph
//   web     clickNotif          (web/js/app.js)               → the tap
//
// An unknown type does not throw on either client. Mobile falls back to
// DEFAULT_ROW_GLYPH (a grey bell) and resolveNotificationTarget returns
// null (a dead tap); web falls back to ICON.bell and its router simply
// matches nothing. So adding a type to one client and forgetting the other
// produces NO error, NO warning and NO log line — it produces an anonymous,
// untappable row that nobody notices until someone reads the code. That is
// exactly what happened to `referral_joined`: written and live since the
// referral loop shipped, absent from all four tables, and the single most
// motivating row this product can show — "your invite worked" — rendered as
// a grey bell you could not tap.
//
// This test reads the REAL files (TSX via the project's TypeScript, web via
// its own source text) so the four tables cannot drift apart silently.
//
// Run: node tests/check-notif-glyphs.js   (or: npm run test:notif-glyphs)

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
const ok   = (n) => console.log(`PASS  ${n}`);
const fail = (n, why) => { failures += 1; console.error(`FAIL  ${n}\n      ${why}`); };

const read = (rel) => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');
const readRepo = (rel) => fs.readFileSync(path.join(__dirname, '..', '..', rel), 'utf8');

// The enum. Authoritative copy: docs/cross-client-invariants.md
// § Notification types. Every value here must be recognised by all four
// tables above.
const TYPES = [
  'trade_match', 'trade_accepted', 'trade_declined',
  'referral_joined',
  'league_member_joined', 'league_member_unlocked_trades',
  'match_expiring', 'deck_replenished', 'counter_offer',
];

// ── 1. mobile ROW_GLYPHS ──────────────────────────────────────────────────
{
  const text = read('src/components/TopBar.tsx');
  const sf = ts.createSourceFile('TopBar.tsx', text, ts.ScriptTarget.Latest,
                                 true, ts.ScriptKind.TSX);
  const keys = new Set();
  const walk = (node) => {
    if (ts.isVariableDeclaration(node)
        && node.name.getText(sf) === 'ROW_GLYPHS'
        && node.initializer
        && ts.isObjectLiteralExpression(node.initializer)) {
      for (const p of node.initializer.properties) {
        if (p.name) keys.add(p.name.getText(sf).replace(/['"]/g, ''));
      }
    }
    ts.forEachChild(node, walk);
  };
  walk(sf);

  if (keys.size === 0) {
    fail('mobile: ROW_GLYPHS parsed', 'no ROW_GLYPHS object literal found in TopBar.tsx');
  } else {
    const missing = TYPES.filter((t) => !keys.has(t));
    if (missing.length === 0) ok(`mobile: ROW_GLYPHS covers all ${TYPES.length} types`);
    else fail('mobile: ROW_GLYPHS covers all types',
              `grey-bell fallback for: ${missing.join(', ')}`);
  }
}

// ── 2. mobile tap routing ─────────────────────────────────────────────────
{
  const text = read('src/utils/deepLinks.ts');
  const sf = ts.createSourceFile('deepLinks.ts', text, ts.ScriptTarget.Latest, true);
  const routed = new Set();
  const walk = (node) => {
    if (ts.isVariableDeclaration(node) && /^V2_[A-Z_]+_KINDS$/.test(node.name.getText(sf))) {
      // new Set([...]) — collect the string literals.
      const init = node.initializer && node.initializer.getText(sf);
      if (init) {
        for (const m of init.matchAll(/'([a-z_]+)'/g)) routed.add(m[1]);
      }
    }
    ts.forEachChild(node, walk);
  };
  walk(sf);

  if (routed.size === 0) {
    fail('mobile: V2_*_KINDS parsed', 'no V2_*_KINDS declarations found in deepLinks.ts');
  } else {
    const missing = TYPES.filter((t) => !routed.has(t));
    if (missing.length === 0) ok(`mobile: every type resolves to a tab`);
    else fail('mobile: every type resolves to a tab',
              `resolveNotificationTarget returns null (dead tap) for: ${missing.join(', ')}`);
  }
}

// ── 3 + 4. web's independent glyph map and tap router ─────────────────────
{
  const web = readRepo('web/js/app.js');

  const slice = (startRe, name) => {
    const m = web.match(startRe);
    if (!m) return null;
    // Body = from the match to the next top-level `function ` at the same
    // indentation. Crude but stable for this file's single-indent style.
    const from = m.index;
    const next = web.indexOf('\n    function ', from + 10);
    return web.slice(from, next === -1 ? web.length : next);
  };

  const iconFn = slice(/\n    function notifTypeIcon\(/, 'notifTypeIcon');
  if (!iconFn) {
    fail('web: notifTypeIcon found', 'no notifTypeIcon in web/js/app.js — did it move?');
  } else {
    const missing = TYPES.filter((t) => !iconFn.includes(`'${t}'`));
    if (missing.length === 0) ok(`web: notifTypeIcon covers all ${TYPES.length} types`);
    else fail('web: notifTypeIcon covers all types',
              `grey-bell fallback on web for: ${missing.join(', ')}`);
  }

  const clickFn = slice(/\n    async function clickNotif\(/, 'clickNotif');
  if (!clickFn) {
    fail('web: clickNotif found', 'no clickNotif in web/js/app.js — did it move?');
  } else {
    const missing = TYPES.filter((t) => !clickFn.includes(`'${t}'`));
    if (missing.length === 0) ok('web: clickNotif routes every type');
    else fail('web: clickNotif routes every type',
              `inert tap on web for: ${missing.join(', ')}`);
  }

  // The match branch must navigate to the MATCHES view. `match-card-<id>`
  // is rendered by renderMatchesList into `matches-list`, which lives in
  // view-matches — routing to 'trades' (as this did until 2026-08-13) shows
  // one view and scrolls an element inside a hidden one.
  if (clickFn && /switchView\('matches'\)/.test(clickFn)) {
    ok("web: match notifications open the matches view");
  } else if (clickFn) {
    fail("web: match notifications open the matches view",
         "clickNotif does not call switchView('matches') — match-card-<id> "
         + 'lives inside view-matches, so any other view is a dead tap');
  }
}

console.log(failures === 0
  ? '\nAll notification-type parity checks passed.'
  : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
