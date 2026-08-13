#!/usr/bin/env node
// Static test: every SecureStore.setItemAsync under src/transport/ passes
// keychainAccessible: WHEN_UNLOCKED_THIS_DEVICE_ONLY (device-auth S0, LLD §2.7).
//
// A write without that option is iCloud-backup eligible — which is exactly the
// exposure the vault exists to close. This is a source-text check, not a
// behavioral one: a new write added later without the option should fail CI
// before it ever reaches a device.
//
// Run: node tests/check-keychain-accessible.js

'use strict';

const fs = require('fs');
const path = require('path');

const TRANSPORT_DIR = path.join(__dirname, '..', 'src', 'transport');
const ACCESSIBLE = 'WHEN_UNLOCKED_THIS_DEVICE_ONLY';

let failures = 0;
function fail(msg) { failures += 1; console.error(`FAIL  ${msg}`); }

if (!fs.existsSync(TRANSPORT_DIR)) {
  console.error(`no ${TRANSPORT_DIR} — nothing to check (did the vault move?)`);
  process.exit(2);
}

const files = fs
  .readdirSync(TRANSPORT_DIR)
  .filter((f) => f.endsWith('.ts'))
  .map((f) => path.join(TRANSPORT_DIR, f));

// Match each setItemAsync(...) call and its argument list, tolerant of
// newlines, so we can assert the accessibility option rides along.
const CALL_RE = /setItemAsync\s*\(([\s\S]*?)\)\s*;/g;

let calls = 0;
for (const file of files) {
  const src = fs.readFileSync(file, 'utf8');
  let m;
  while ((m = CALL_RE.exec(src)) !== null) {
    calls += 1;
    const args = m[1];
    // The accessibility may be inlined at the call site, OR passed as an
    // options identifier defined in the same file. Resolve the identifier
    // case so `setItemAsync(K, V, WRITE_OPTS)` with a device-only WRITE_OPTS
    // const counts — but a bare call with no options, or an options object
    // that never mentions the accessibility, still fails.
    if (args.includes(ACCESSIBLE)) continue; // inline
    const optArg = (args.split(',')[2] || '').trim();
    const ident = /^[A-Za-z_$][\w$]*$/.test(optArg) ? optArg : null;
    const identOk =
      ident &&
      new RegExp(`const\\s+${ident}\\b[\\s\\S]*?${ACCESSIBLE}`).test(src);
    if (!identOk) {
      fail(
        `${path.basename(file)}: a setItemAsync call neither inlines ${ACCESSIBLE} nor ` +
          `passes an options const defined with it\n      ${args.trim().replace(/\s+/g, ' ').slice(0, 100)}`,
      );
    }
  }
}

if (calls === 0) {
  console.error('no setItemAsync calls found under src/transport/ — check the regex or the module');
  process.exit(2);
}

if (failures) {
  console.error(`\n${failures} of ${calls} SecureStore write(s) missing device-only accessibility.`);
  process.exit(1);
}
console.log(`ok    all ${calls} SecureStore write(s) under src/transport/ pin ${ACCESSIBLE}`);
