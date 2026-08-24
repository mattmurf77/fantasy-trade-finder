#!/usr/bin/env node
/**
 * check-quickset-via.js — structural guard for the Quick Set `via` gap fix
 * (2026-08-24; docs/business/analytics/2026-08-24-quickset-via-gap.md).
 *
 * WHY THIS EXISTS
 * ---------------
 * `POST /api/tiers/save` has branched on `via == "quickset"` since analytics
 * P0 — it fires `quickset_completed` (FR-20), stamps `tier_save.props.via`,
 * and writes `ranking_method = 'quickset'` at the point of use (P0-1) — but
 * NO client ever sent that value, so all three reads were dark for every
 * production Quick Set walk while the docs called the server row "the
 * authoritative completion". The failure was invisible by construction:
 * the untagged save is a perfectly valid 'tiers' save, so nothing errored,
 * and the backend tests drive the branch with hand-built bodies no client
 * ever produced. This guard pins the client half to the server half.
 *
 * Absence assertions read COMMENT-STRIPPED source — the comments in these
 * files deliberately name the constructs they forbid.
 *
 * Run: node mobile/tests/check-quickset-via.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const rankingsText = read('mobile/src/api/rankings.ts');
const quicksetText = read('mobile/src/screens/QuickSetTiersScreen.tsx');
const tiersText = read('mobile/src/screens/TiersScreen.tsx');
const serverText = read('backend/server.py');

let failures = 0;
function assert(cond, label, why) {
  if (cond) {
    console.log(`PASS  ${label}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${label}${why ? `: ${why}` : ''}`);
  }
}

function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}
const rankingsCode = stripComments(rankingsText);
const quicksetCode = stripComments(quicksetText);
const tiersCode = stripComments(tiersText);

// ── 1. The API layer accepts the tag ───────────────────────────────────────
// saveTiers's opts.via union must carry 'quickset' alongside the rookie tags.
// Anchor to the function: rankings.ts has other, narrower via unions
// (reorderRankings, saveAnchor) that must NOT satisfy this pin.
const saveTiersAt = rankingsCode.indexOf('export async function saveTiers');
assert(saveTiersAt >= 0, 'saveTiers found in rankings.ts');
const viaUnion = rankingsCode
  .slice(saveTiersAt, saveTiersAt + 1200)
  .match(/via\?\s*:\s*((?:'[a-z_]+'\s*\|\s*)+'[a-z_]+')/);
assert(
  viaUnion !== null && viaUnion[1].includes("'quickset'"),
  "saveTiers opts.via union includes 'quickset'",
  'the unscoped Quick Set tag would be a type error and silently dropped',
);
for (const tag of ["'rookie_tiers'", "'rookie_quickset'", "'rookie_anchors'"]) {
  assert(
    viaUnion !== null && viaUnion[1].includes(tag),
    `saveTiers opts.via union keeps ${tag}`,
    'the rookie forensic tags are the board-restore trail (M2 KD-10)',
  );
}

// ── 2. The walk sends it ───────────────────────────────────────────────────
// The save mutation's opts expression: rookie scope keeps 'rookie_quickset',
// and the non-rookie arm passes via:'quickset' (not undefined — that was the
// gap). Match the ternary as a unit so the two arms cannot drift apart.
const ternary = quicksetCode.match(
  /rookieScope\.isRookie\s*\?\s*\{[^}]*via:\s*'rookie_quickset'[^}]*\}\s*:\s*(\{[^}]*\}|undefined)/,
);
assert(ternary !== null, 'QuickSetTiersScreen saveTiers opts ternary found');
assert(
  ternary !== null && /\{\s*via:\s*'quickset'\s*\}/.test(ternary[1]),
  "unscoped Quick Set saves pass { via: 'quickset' }",
  "the non-rookie arm reverted to undefined — every read of the tag goes dark again",
);

// ── 3. Nobody else sends it ────────────────────────────────────────────────
// TiersScreen (the full board) must stay on the 'tiers' default: tagging it
// 'quickset' would fire quickset_completed for ordinary board edits.
assert(
  !tiersCode.includes("'quickset'"),
  "TiersScreen never sends via:'quickset'",
  'the full-board editor is not the Quick Set walk',
);
// The G-031 deletion stays deleted: no mobile client emitter for the
// server-fired name (the taxonomy's disjointness assert would crash at boot).
assert(
  !quicksetCode.includes("track('quickset_completed'"),
  'no client quickset_completed emitter',
  'server-fired name; a client emitter trips the import-time disjointness assert',
);

// ── 4. The server half this pins against ───────────────────────────────────
// The tiers-save via whitelist accepts the tag, and the FR-20 branch exists.
assert(
  /in\s*\(\s*"tiers",\s*"quickset",\s*"rookie_tiers",\s*\n?\s*"rookie_quickset",\s*"rookie_anchors"\s*\)/.test(
    serverText,
  ),
  'server tiers-save via whitelist includes "quickset"',
  'an unrecognised via falls back to "tiers" and the event never fires',
);
assert(
  /if via == "quickset":/.test(serverText),
  'server fires quickset_completed on the tagged branch',
);
assert(
  /if scope != "rookie" and via in \("tiers", "quickset"\):/.test(serverText),
  "server notes ranking_method from via on unscoped saves",
  "P0-1's point-of-use ranking_method write is what the tag also feeds",
);

process.exit(failures === 0 ? 0 : 1);
