#!/usr/bin/env node
// WS2b Sleeper offer-import switch guard
// (docs/plans/offer-learnings/scope-sleeper-offer-read.md).
//
// WHY THIS EXISTS. The import of a user's own Sleeper trade offers needs their
// explicit, revocable consent: one switch in Settings › Leagues, OFF by
// default. D-056 retired the simulator, so the shape that keeps that promise
// is pinned here:
//   1. The row reads the flag `trade.sleeper_offer_import` and renders nothing
//      while it is off, while the server has nothing to show (null), or while
//      the user has no Send-in-Sleeper link (`linked`).
//   2. The switch's value is the SERVER's `consented` (never a local default
//      of true; no AsyncStorage / persisted copy of it).
//   3. Switching on sends the `terms_version` the user was shown; switching
//      off calls the withdrawal (DELETE), and the server's notice is shown.
//   4. Every word is the server's: the label and the terms line come from the
//      state, never a hard-coded copy of the Terms line.
//   5. The API module: GET is background + quiet on 403/404 and maps them to
//      null; POST carries terms_version; DELETE is the withdrawal.
//   6. The row is mounted in SettingsLeaguesScreen (not TradesScreen), behind
//      !isDemo && !accountOnly.
//   7. Token-only styles (no hex literal); the switch has an accessibility
//      label; a testID exists.
//   8. `npm run test:offer-import` exists.
//
// Run: node tests/check-offer-import.js   (or: npm run test:offer-import)

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const ROW = path.join(ROOT, 'src/components/SleeperOfferImportRow.tsx');
const API = path.join(ROOT, 'src/api/offerImport.ts');
const HOST = path.join(ROOT, 'src/screens/settings/SettingsLeaguesScreen.tsx');
const TRADES = path.join(ROOT, 'src/screens/TradesScreen.tsx');
const PKG = path.join(ROOT, 'package.json');

const failures = [];
let passed = 0;
function check(name, cond, detail) {
  if (cond) passed++;
  else failures.push(`${name}${detail ? `\n      ${detail}` : ''}`);
}
function read(p) {
  if (!fs.existsSync(p)) { failures.push(`missing: ${path.relative(ROOT, p)}`); return ''; }
  return fs.readFileSync(p, 'utf8');
}
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\{\/\*[\s\S]*?\*\/\}/g, '');
}

const row = stripComments(read(ROW));
const api = stripComments(read(API));
const host = stripComments(read(HOST));
const trades = read(TRADES);
const pkg = JSON.parse(read(PKG) || '{}');

// 1. gates
check('1a reads the flag', /useFlag\(\s*'trade\.sleeper_offer_import'\s*\)/.test(row));
check('1b renders nothing when off / no state / not linked',
  /if\s*\(\s*!enabled\s*\|\|\s*!state\s*\|\|\s*!state\.linked\s*\)\s*return null;/.test(row));
check('1c the query is disabled with the flag off', /enabled,\s*\n/.test(row) || /enabled:\s*enabled/.test(row));

// 2. value is the server's
check('2a switch value is state.consented', /value=\{state\.consented\}/.test(row));
check('2b no persisted copy', !/AsyncStorage|SecureStore|persist/i.test(row));

// 3. grant / withdraw
check('3a grant echoes the shown terms version', /grantOfferImport\(\s*state\.terms_version\s*\)/.test(row));
check('3b off calls the withdrawal', /withdrawOfferImport\(\s*\)/.test(row));
check('3c the server notice is shown', /setNotice\(/.test(row) && /notice\s*\?\?\s*state\.terms_line/.test(row));
check('3d a 409 reloads the server state', /status\s*===\s*409/.test(row) && /invalidateQueries/.test(row));

// 4. server copy only
check('4a label from state', /\{state\.label\}/.test(row));
check('4b no hard-coded terms copy', !/never your messages|Never your messages/i.test(row));

// 5. API module
check('5a GET background + quiet 403/404', /background:\s*true/.test(api) && /\[\s*403\s*,\s*404\s*\]/.test(api));
check('5b GET maps 404/403 to null', /status\s*===\s*404\s*\|\|\s*err\.status\s*===\s*403\)\)\s*return null/.test(api));
check('5c POST carries terms_version', /method:\s*'POST'[\s\S]{0,80}terms_version:\s*termsVersion/.test(api));
check('5d DELETE is the withdrawal', /withdrawOfferImport[\s\S]{0,160}method:\s*'DELETE'/.test(api));
check('5e one path', /'\/api\/sleeper\/offer-import'/.test(api));

// 6. placement
check('6a mounted in SettingsLeaguesScreen behind !isDemo && !accountOnly',
  /!isDemo\s*&&\s*!accountOnly\s*\?\s*<SleeperOfferImportRow\s*\/>\s*:\s*null/.test(host));
check('6b imported there', /import SleeperOfferImportRow from '..\/..\/components\/SleeperOfferImportRow'/.test(host));
check('6c not in TradesScreen', !/SleeperOfferImportRow|offerImport/.test(trades));

// 7. tokens, a11y, testID
check('7a no hex literal', !/#[0-9a-fA-F]{3,8}\b/.test(row));
check('7b accessible switch', /accessibilityLabel=\{state\.label\}/.test(row));
check('7c testID', /testID="settings\.sleeper-offer-import\.switch"/.test(row));
check('7d chalkline Text', /import \{ Text \} from '\.\/chalkline'/.test(row));

// 8. script
check('8 npm script', (pkg.scripts || {})['test:offer-import'] === 'node tests/check-offer-import.js');

if (failures.length) {
  console.error(`check-offer-import: ${failures.length} FAILED, ${passed} passed`);
  for (const f of failures) console.error(`  ✗ ${f}`);
  process.exit(1);
}
console.log(`check-offer-import: all ${passed} checks passed`);
