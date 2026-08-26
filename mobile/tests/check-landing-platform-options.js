#!/usr/bin/env node
// Landing platform options (flag `landing.platform_options`) — structural
// guard. docs/plans/landing-platform-options/scope.md §3.
//
// The entry page offers Sleeper · ESPN · MFL as supported platforms. The
// claims below are about code SHAPE, and each one protects a specific
// failure mode:
//
//   1. The chip row is gated on BOTH `onboarding.landing` and
//      `landing.platform_options` — losing either gate either strands the
//      row on the P2.6 layout it was never designed for, or removes the
//      deploy-free revert lever.
//   2. The ESPN/MFL chips are individually gated on `espn.link` / `mfl.link`,
//      and a de-flagged selection falls back to Sleeper — otherwise flipping
//      a platform flag off strands the user on a chip that renders nothing.
//   3. The Apple success branches forward `platformIntent` to BOTH
//      `onSignedIn` (linked account) and `onAccountSignedIn` (account-only) —
//      dropping either turns the ESPN/MFL door into a dead end on that path.
//   4. Selecting a non-Sleeper chip advances guide step s0.2 — the Analyst's
//      spotlight targets the username field the chip hides.
//   5. RootNav maps the intent onto LeaguePicker's auto-open params for both
//      callbacks (espn → espnLink, mfl → mflLink).
//   6. LeaguePicker's MFL auto-open keeps the #266 transition-settled
//      deferral (a sibling RN <Modal> presented mid-transition wedges), and
//      the single-league auto-skip blocks on `autoOpenMflLink` (the user
//      came to link MFL, not to be skipped into their one Sleeper league).
//   7. The flag exists in config/features.json AND backend FLAG_KEYS — a
//      key missing from FLAG_KEYS is ignored by the loader.
//
// Run: node tests/check-landing-platform-options.js
//   (or: npm run test:landing-platform-options)

'use strict';

const fs = require('fs');
const path = require('path');

let failures = 0;
function assert(cond, name, detail) {
  if (cond) console.log(`PASS  ${name}`);
  else {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
  }
}
function read(rel) {
  return fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');
}

const signIn = read('src/screens/SignInScreen.tsx');
const rootNav = read('src/navigation/RootNav.tsx');
const picker = read('src/screens/LeaguePickerScreen.tsx');
const features = fs.readFileSync(
  path.join(__dirname, '..', '..', 'config', 'features.json'), 'utf8');
const flagKeys = fs.readFileSync(
  path.join(__dirname, '..', '..', 'backend', 'feature_flags.py'), 'utf8');

// ── 1. dual gate on the chip row ─────────────────────────────────────────
assert(
  /useFlag\('landing\.platform_options'\)/.test(signIn),
  'SignIn reads landing.platform_options',
);
assert(
  /platformPickerShown\s*=\s*\n?\s*landingOn && platformOptionsFlag/.test(signIn),
  'chip row requires onboarding.landing AND landing.platform_options',
);
assert(
  /\{platformPickerShown \? \(\s*\n\s*<View style=\{styles\.platformRow\}/.test(signIn),
  'chip row renders only under platformPickerShown',
);

// ── 2. per-platform flag gates + de-flag fallback ────────────────────────
assert(
  /espnLinkOn = useFlag\('espn\.link'\)/.test(signIn) &&
    /mflLinkOn = useFlag\('mfl\.link'\)/.test(signIn),
  'ESPN/MFL chips read espn.link / mfl.link',
);
assert(
  /\.\.\.\(espnLinkOn \? \(\['espn'\] as const\) : \[\]\)/.test(signIn) &&
    /\.\.\.\(mflLinkOn \? \(\['mfl'\] as const\) : \[\]\)/.test(signIn),
  'chip list conditions each platform on its flag',
);
assert(
  /\(entryPlatform === 'espn' && !espnLinkOn\)[\s\S]{0,120}\(entryPlatform === 'mfl' && !mflLinkOn\)[\s\S]{0,80}setEntryPlatform\('sleeper'\)/.test(signIn),
  'de-flagged selection falls back to Sleeper',
);

// ── 3. intent forwarded on both Apple success branches ───────────────────
assert(
  /nonSleeperEntry \? entryPlatform : undefined/.test(signIn),
  'platformIntent derived from the selected chip',
);
assert(
  /onSignedIn\(platformIntent\)/.test(signIn),
  'linked-account branch forwards platformIntent',
);
assert(
  /\(onAccountSignedIn \?\? onSignedIn\)\(platformIntent\)/.test(signIn),
  'account-only branch forwards platformIntent',
);

// ── 4. guide spotlight cannot outlive its target ─────────────────────────
assert(
  /if \(p !== 'sleeper'\) \{[\s\S]{0,220}advanceGuideIfActive\('s0\.2'\)/.test(signIn),
  'non-Sleeper chip selection advances guide step s0.2',
);

// ── 5. RootNav intent → param mapping, both callbacks ────────────────────
assert(
  /if \(intent === 'espn'\) return \{ espnLink: true \};\s*\n\s*if \(intent === 'mfl'\) return \{ mflLink: true \};/.test(rootNav),
  'platformIntentParams maps espn→espnLink, mfl→mflLink',
);
assert(
  /onSignedIn=\{\(platformIntent\) =>\s*\n\s*navigation\.replace\('LeaguePicker', platformIntentParams\(platformIntent\)\)\}/.test(rootNav),
  'onSignedIn routes through platformIntentParams',
);
assert(
  /onAccountSignedIn=\{\(platformIntent\) =>\s*\n\s*navigation\.replace\('LeaguePicker', platformIntentParams\(platformIntent\)\)\}/.test(rootNav),
  'onAccountSignedIn routes through platformIntentParams',
);
assert(
  /autoOpenMflLink=\{route\.params\?\.mflLink === true\}/.test(rootNav),
  'LeaguePicker receives autoOpenMflLink from the mflLink param',
);

// ── 6. LeaguePicker MFL auto-open: #266 deferral + autoskip block ────────
const mflEffect = picker.match(
  /if \(!autoOpenMflLink \|\| !mflEnabled\) return;[\s\S]{0,700}?\}, \[autoOpenMflLink, mflEnabled, navigation\]\);/,
);
assert(!!mflEffect, 'MFL auto-open effect exists, gated on prop + mfl.link');
assert(
  !!mflEffect && /addListener\(\s*\n?\s*'transitionEnd'/.test(mflEffect[0]),
  'MFL auto-open defers to transitionEnd (#266)',
);
assert(
  !!mflEffect && /setPlatformOpen\('mfl'\)/.test(mflEffect[0]),
  'MFL auto-open opens the MFL PlatformLinkSheet',
);
assert(
  /if \(loading \|\| error \|\| selectingId \|\| autoOpenEspnLink \|\| autoOpenMflLink\) return;/.test(picker),
  'single-league auto-skip blocks on autoOpenMflLink',
);

// ── 7. flag registered on both sides ─────────────────────────────────────
assert(
  /"landing\.platform_options": true/.test(features),
  'config/features.json carries landing.platform_options',
);
assert(
  /"landing\.platform_options",/.test(flagKeys),
  'backend FLAG_KEYS registers landing.platform_options',
);

if (failures > 0) {
  console.error(`\n${failures} failure(s)`);
  process.exit(1);
}
console.log('\nAll landing-platform-options checks passed.');
