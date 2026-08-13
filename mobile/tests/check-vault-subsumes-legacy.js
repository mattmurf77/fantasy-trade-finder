#!/usr/bin/env node
// Behavioral test for credentialVault.migrateLegacySlot (device-auth S0,
// LLD §2.7 / blocking fix 4).
//
// Pins the "subsume and delete" property: after a migration the legacy
// `sleeper.link.jwt` slot is GONE and the envelope carries the token; and on a
// write failure the legacy slot is RETAINED (never delete-then-lose). Two
// Keychain copies of a 365-day full-account credential — one outside the
// vault's accessibility/wipe logic — is the failure this guards.
//
// Idiom: transpile the REAL module with the project's typescript and run under
// node (same as check-espn-nav-policy.js). credentialVault imports
// expo-secure-store, so the require shim injects an in-memory mock rather than
// throwing — the vault is not import-free (only gqlGuard.ts is).
//
// Run: node tests/check-vault-subsumes-legacy.js

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

const srcPath = path.join(__dirname, '..', 'src', 'transport', 'credentialVault.ts');
const source = fs.readFileSync(srcPath, 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

let failures = 0;
function ok(name) { console.log(`ok    ${name}`); }
function fail(name, detail) { failures += 1; console.error(`FAIL  ${name}: ${detail}`); }

// In-memory SecureStore mock. `failSet` lets a test force a write failure.
function makeStore(initial, opts) {
  opts = opts || {};
  const map = new Map(Object.entries(initial || {}));
  const writes = []; // {key, options}
  return {
    _map: map,
    _writes: writes,
    WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'when-unlocked-this-device-only',
    async getItemAsync(k) { return map.has(k) ? map.get(k) : null; },
    async setItemAsync(k, v, options) {
      if (opts.failSet) throw new Error('simulated keychain write failure');
      writes.push({ key: k, options });
      map.set(k, v);
    },
    async deleteItemAsync(k) {
      if (opts.failDelete) throw new Error('simulated keychain delete failure');
      map.delete(k);
    },
  };
}

function load(store) {
  const shim = { exports: {} };
  new Function('module', 'exports', 'require', js)(
    shim,
    shim.exports,
    (name) => {
      if (name === 'expo-secure-store') return store;
      throw new Error(`unexpected import "${name}"`);
    },
  );
  return shim.exports;
}

const USER = 'sleeper-user-123';
const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.PAYLOAD.SIG';

(async () => {
  // 1. Happy path: legacy slot migrates, then is deleted; envelope carries token.
  {
    const store = makeStore({ 'sleeper.link.jwt': JSON.stringify({ user_id: USER, token: TOKEN }) });
    const vault = load(store);
    const result = await vault.migrateLegacySlot(USER);
    if (result !== 'migrated') fail('happy: returns migrated', `got ${result}`);
    else if ((await store.getItemAsync('sleeper.link.jwt')) !== null)
      fail('happy: legacy slot deleted', 'legacy key still present');
    else {
      const env = await vault.readEnvelope(USER);
      if (!env || env.secret !== TOKEN) fail('happy: envelope carries token', JSON.stringify(env));
      else ok('happy: migrate → legacy gone, token in vault');
    }
    // Every vault write pinned device-only accessibility.
    const bad = store._writes.filter((w) => w.options?.keychainAccessible !== store.WHEN_UNLOCKED_THIS_DEVICE_ONLY);
    if (bad.length) fail('happy: writes pin WHEN_UNLOCKED_THIS_DEVICE_ONLY', `${bad.length} without it`);
    else ok('happy: writes pin device-only accessibility');
  }

  // 2. Write failure: legacy slot RETAINED, returns 'failed', nothing lost.
  {
    const store = makeStore(
      { 'sleeper.link.jwt': JSON.stringify({ user_id: USER, token: TOKEN }) },
      { failSet: true },
    );
    const vault = load(store);
    const result = await vault.migrateLegacySlot(USER);
    if (result !== 'failed') fail('writefail: returns failed', `got ${result}`);
    else if ((await store.getItemAsync('sleeper.link.jwt')) === null)
      fail('writefail: legacy slot RETAINED', 'legacy key was deleted despite write failure');
    else ok('writefail: write fails → legacy retained, no data lost');
  }

  // 3. No legacy slot: returns 'none', no envelope created.
  {
    const store = makeStore({});
    const vault = load(store);
    const result = await vault.migrateLegacySlot(USER);
    if (result !== 'none') fail('none: returns none', `got ${result}`);
    else if ((await store.getItemAsync('ftf.platformCreds')) !== null)
      fail('none: no envelope written', 'vault key created from nothing');
    else ok('none: no legacy slot → none, no vault write');
  }

  // 4. readEnvelope on a user_id mismatch returns null and does NOT wipe (OI-14/D-047).
  {
    const env = { v: 1, user_id: USER, platform: 'sleeper', secret: TOKEN, updated_at: '2026-08-13T00:00:00Z' };
    const store = makeStore({ 'ftf.platformCreds': JSON.stringify(env) });
    const vault = load(store);
    const got = await vault.readEnvelope('a-different-user');
    if (got !== null) fail('mismatch: returns null', JSON.stringify(got));
    else if ((await store.getItemAsync('ftf.platformCreds')) === null)
      fail('mismatch: does NOT wipe', 'vault was wiped on a mismatched read');
    else ok('mismatch: wrong user → null, envelope retained (OI-14)');
  }

  if (failures) {
    console.error(`\n${failures} check(s) failed.`);
    process.exit(1);
  }
  console.log('\nAll credentialVault checks passed.');
})();
