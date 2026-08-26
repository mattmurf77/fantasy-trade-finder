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

// ── V2 (D-164): sessionless platform entry — no Apple dependency ─────────
const espnSheet = read('src/components/EspnLinkSheet.tsx');
const platformSheet = read('src/components/PlatformLinkSheet.tsx');
const entryApi = read('src/api/platformEntry.ts');
const serverPy = fs.readFileSync(
  path.join(__dirname, '..', '..', 'backend', 'server.py'), 'utf8');

// V2.1 — the panel opens the entry sheet; Apple is NOT in the panel.
assert(
  /signin\.platform-link-btn/.test(signIn) &&
    /setEntrySheet\(entryPlatform === 'espn' \? 'espn' : 'mfl'\)/.test(signIn),
  'V2: panel button opens the entry sheet',
);
assert(
  !/signin\.platform-apple-btn/.test(signIn),
  'V2: no Apple button inside the platform panel',
);

// V2.2 — the host pins an account_only entry user, then routes to the
// picker (whose platform-league merge + auto-skip finish the flow).
const entrySessionFn = signIn.match(
  /async function handleEntrySession[\s\S]{0,600}?\n  \}/,
);
assert(
  !!entrySessionFn && /account_only: true/.test(entrySessionFn[0]),
  'V2: handleEntrySession pins an account_only entry user',
);
assert(
  /function handleEntryLinked\(\) \{\s*\n\s*setEntrySheet\(null\);\s*\n\s*\(onAccountSignedIn \?\? onSignedIn\)\(\);/.test(signIn),
  'V2: entry link completion routes through the account callback',
);
assert(
  /<EspnLinkSheet\s*\n\s*entry\b/.test(signIn) &&
    /<PlatformLinkSheet\s*\n\s*entry\b/.test(signIn),
  'V2: SignIn hosts both sheets in entry mode',
);

// V2.3 — sheets: mint BEFORE the canonical import, inside pickTeam.
const espnPick = espnSheet.match(/async function pickTeam[\s\S]{0,900}?await linkEspnLeague/);
assert(
  !!espnPick && /if \(entry\) \{[\s\S]{0,400}entryPlatformMint\(/.test(espnPick[0]),
  'V2: ESPN pickTeam mints the entry session before the canonical import',
);
const mflPick = platformSheet.match(/async function pickTeam[\s\S]{0,900}?await linkPlatformLeague/);
assert(
  !!mflPick && /if \(entry\) \{[\s\S]{0,400}entryPlatformMint\(/.test(mflPick[0]),
  'V2: MFL pickTeam mints the entry session before the canonical import',
);

// V2.4 — sheets: session-dependent paths suppressed in entry mode.
assert(
  /if \(!leaguePicker \|\| entry\) return;/.test(espnSheet),
  'V2: entry mode skips the my-leagues fetch (stored-credential read)',
);
assert(
  /useFlag\('mfl\.auth_link'\) && platform === 'mfl' && !entry/.test(platformSheet),
  'V2: entry mode suppresses the MFL username/password path',
);
assert(
  /entry\s*\n?\s*\? await entryEspnPreview\(/.test(espnSheet) &&
    /entry\s*\n?\s*\? await entryMflPreview\(/.test(platformSheet),
  'V2: entry mode previews through the sessionless route',
);

// V2.5 — the api layer stores the minted token and carries the signin funnel.
assert(
  /await setSessionToken\(res\.session_token\);/.test(entryApi) &&
    /track\('signin_attempted', \{ method: args\.platform \}/.test(entryApi) &&
    /track\('signin_succeeded', \{ method: args\.platform \}/.test(entryApi) &&
    /signin_failed/.test(entryApi),
  'V2: mint stores the token and fires the signin funnel (method espn/mfl)',
);

// V2.6 — backend route exists, sessionless, dual-gated, deterministic ids.
const entryRoute = serverPy.match(
  /@app\.route\("\/api\/entry\/platform", methods=\["POST"\]\)\s*\ndef entry_platform\(\):[\s\S]{0,9000}?\n@app\.route/,
);
assert(!!entryRoute, 'V2: POST /api/entry/platform route exists');
assert(
  !!entryRoute &&
    /is_enabled\("landing\.platform_options"\)/.test(entryRoute[0]) &&
    /is_enabled\("espn\.link"\)/.test(entryRoute[0]) &&
    /is_enabled\("mfl\.link"\)/.test(entryRoute[0]),
  'V2: entry route gated on the feature flag AND each platform flag',
);
assert(
  !!entryRoute && !/_require_session\(\)/.test(entryRoute[0]),
  'V2: entry route is sessionless (no _require_session)',
);
assert(
  !!entryRoute &&
    /entry:espn:\{_espn\.canonical_swid\(team\.owner_swid\)\}/.test(entryRoute[0]) &&
    /entry:espn:\{league_id\}\.t\{team_id\}/.test(entryRoute[0]) &&
    /f"entry:\{_mfl_member_id\(league_id, franchise_id\)\}"/.test(entryRoute[0]),
  'V2: deterministic entry: ids, distinct from the espn:/mfl: placeholder class',
);
assert(
  !!entryRoute && /_extension_build_session\(/.test(entryRoute[0]),
  'V2: mint goes through the one reusable session builder',
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
