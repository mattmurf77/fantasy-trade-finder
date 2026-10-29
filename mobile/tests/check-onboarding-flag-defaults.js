#!/usr/bin/env node
// The launched onboarding flags are baked into first-paint defaults
// (Product's pre-launch review B2, 2026-10-27).
//
// WHY: a fresh install has no cached flag map, and the network fetch runs
// detached. Without these keys in LAUNCHED_FLAG_DEFAULTS, every first-ever
// boot, and every offline first open, paints the old Apple-first sign-in and
// the flat settings, and stays there until a revalidate.
//
// Pins:
//   1. each launched onboarding flag is in LAUNCHED_FLAG_DEFAULTS;
//   2. with the SAME value as config/features.json (`revalidateFlags` replaces
//      the whole map, so a mismatch flips the surface between the first two
//      paints; flipping one means editing both);
//   3. `espn.signin` is baked only when config/features.json carries it true
//      (ask 15), and then with the same value.
//   4. `landing.platform_options` is NOT baked (release-lead #502 QA P1-1):
//      while the server holds it off, a baked `true` paints chips whose entry
//      sheet dead-ends. The PR that turns the proof-based sign-in on bakes
//      it, and updates this pin.
//   5. A server or cached `false` still wins (release-lead #502 QA P3-1): the
//      store starts from the defaults, a cached map spreads OVER them, and a
//      successful fetch replaces the whole map with nothing merged under it.
// Dependency-free: plain node, comment-stripped source.
//
// Run: node tests/check-onboarding-flag-defaults.js

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const stripComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

let failures = 0;
function check(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const src = stripComments(read('src/state/useFeatureFlags.ts'));
const block = src.match(/const LAUNCHED_FLAG_DEFAULTS\s*:\s*FlagMap\s*=\s*\{([\s\S]*?)\n\};/);
check(!!block, 'LAUNCHED_FLAG_DEFAULTS is parseable');
const baked = {};
for (const m of (block ? block[1] : '').matchAll(/'([a-z0-9_.]+)'\s*:\s*(true|false)\s*,/g)) {
  if (m[1] in baked) check(false, `${m[1]} is baked once`, 'listed twice');
  baked[m[1]] = m[2] === 'true';
}
const features = JSON.parse(fs.readFileSync(path.join(ROOT, '..', 'config', 'features.json'), 'utf8'));

const LAUNCHED_ONBOARDING = [
  'onboarding.v2',
  'onboarding.landing',
  'mfl.link',
  'account.settings_hub',
];
for (const key of LAUNCHED_ONBOARDING) {
  check(key in baked, `1. ${key} is baked into first-paint defaults`);
  check(baked[key] === features[key],
    `2. ${key} matches config/features.json`,
    `baked ${baked[key]}, features.json ${features[key]}`);
}

if ('espn.signin' in baked) {
  check(features['espn.signin'] === true && baked['espn.signin'] === true,
    '3. espn.signin is baked only once config/features.json carries it true (ask 15)',
    `baked ${baked['espn.signin']}, features.json ${features['espn.signin']}`);
} else {
  check(true, '3. espn.signin is not baked (ask 15 not passed, or not launched)');
}

check(!('landing.platform_options' in baked),
  '4. landing.platform_options is not baked until the proof-based sign-in is live',
  'it is baked; while the server holds it off, its chips dead-end (release-lead #502 QA P1-1)');

const body = (name) => {
  const m = src.match(new RegExp(`\\n  ${name}: async \\(\\) => \\{([\\s\\S]*?)\\n  \\},`));
  return m ? m[1] : '';
};
check(/\n  flags: \{ \.\.\.LAUNCHED_FLAG_DEFAULTS \},/.test(src),
  '5a. the store starts from the baked defaults');
check(/set\(\{ flags: \{ \.\.\.LAUNCHED_FLAG_DEFAULTS, \.\.\.\(parsed as FlagMap\) \} \}\)/.test(body('loadCachedFlags')),
  '5b. a cached map spreads OVER the defaults (a cached false wins)');
const reval = body('revalidateFlags');
// The set() that follows the fetch takes `flags` whole (shorthand), whatever
// else it sets alongside (B8's appMinVersion / appStoreLive).
check(/const flags = await loadFeatureFlags\(/.test(reval) && /set\(\{\s*flags,\s*loaded: true[,\s]/.test(reval)
  && !/LAUNCHED_FLAG_DEFAULTS/.test(reval),
  '5c. a successful fetch replaces the whole map, with no defaults merged under it (a server false wins)');

if (failures) {
  console.error(`\n${failures} onboarding-flag-defaults check(s) failed.`);
  process.exit(1);
}
console.log('\nAll onboarding-flag-defaults checks passed.');
