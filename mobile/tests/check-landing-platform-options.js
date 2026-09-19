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
//   4. Guide step s0.2 follows the chip: it is requested for the SELECTED
//      platform, any switch ends AND re-arms an in-flight one, and the panel
//      button is a registered target that advances it. Losing any part either
//      strands a spotlight on an unmounted control or spends the once-ever
//      beat on the door the user just closed.
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

// ── 4. the guide beat follows the chip, and cannot outlive its target ────
//
// s0.2 rings whichever entry control the chip row is showing: the Sleeper
// username field, or the ESPN/MFL panel's link button. `GUIDE.s0_2(platform)`
// carries both the target and the line, so three things have to hold together
// and each protects a different failure:
//
//   a. The request is parameterized on the SELECTED chip. Losing this points
//      an ESPN user at a username field that is not on screen and tells them
//      to type a Sleeper name they do not have.
//   b. A switch ENDS an in-flight s0.2 — in either direction. Only the
//      non-Sleeper direction used to matter; now that the beat can ring the
//      platform button, switching BACK to Sleeper strands a ring the same way.
//   c. …and RE-ARMS it. `once: true` means the advance in (b) would otherwise
//      spend the beat on the door the user just closed, and the platform-entry
//      user is never shown where to start. Advance without re-arm is the
//      shipped-before behavior; re-arm without advance is the stranded ring.
//
// (d) pins the panel button as a real, measurable target — a beat aimed at an
// unregistered testID measures null and silently degrades to a bubble.
const selectFn = signIn.match(
  /function selectEntryPlatform\([\s\S]{0,1600}?\n  \}/,
);
assert(!!selectFn, 'selectEntryPlatform is parseable');
assert(
  /requestGuideStep\(GUIDE\.s0_2\(entryPlatform\)\)/.test(signIn),
  'a. s0.2 is requested for the SELECTED platform (target + line follow the chip)',
);
assert(
  !!selectFn &&
    /if \(p !== 'sleeper'\) \{\s*\n\s*Keyboard\.dismiss\(\);\s*\n\s*\}/.test(selectFn[0]),
  'b. only the keyboard dismissal is scoped to the non-Sleeper direction',
);
assert(
  !!selectFn &&
    /guideActiveStepId\(\) === 's0\.2'\) \{[\s\S]{0,160}advanceGuideIfActive\('s0\.2'\)/.test(
      selectFn[0],
    ),
  'b. ANY chip switch ends an active s0.2 (no spotlight outlives its target)',
);
assert(
  !!selectFn && /patchOnboardingState\(\{ guideSeen: \{ 's0\.2': false \} \}\)/.test(selectFn[0]),
  'c. …and re-arms it so the beat is re-offered against the new control',
);
assert(
  /registerGuideTarget\('signin\.platform-link-btn', platformLinkRef\)/.test(signIn) &&
    /<View ref=\{platformLinkRef\} collapsable=\{false\}>/.test(signIn),
  'd. the panel button is a registered, measurable guide target',
);
assert(
  /advanceGuideIfActive\('s0\.2'\);\s*\n\s*setEntrySheet\(/.test(signIn),
  'd. tapping the panel button advances s0.2 (the real action on that path)',
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
// (The V2 "entry suppresses the MFL sign-in path" claim was SUPERSEDED by
//  v2.1, which routes that path through the sessionless action instead —
//  pinned in the V2.1 block below.)
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
  /@app\.route\("\/api\/entry\/platform", methods=\["POST"\]\)\s*\ndef entry_platform\(\):[\s\S]{0,20000}?\n@app\.route/,
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

// ── V2.1: "log in" as a first-class entry option ─────────────────────────
//
// The v2 door led with "enter your league ID". v2.1 adds the account route
// for both platforms, still sessionless. Each claim below protects a
// specific failure mode:
//
//   a. The two new api fns must be skipAuth POSTs — a session header on an
//      entry call is at best meaningless and at worst wrong-user.
//   b. ESPN capture with no league id typed must reach the SESSIONLESS
//      my-leagues action; the stored-credential fetch can't work pre-mint,
//      so losing this branch silently restores the dead end.
//   c. The ESPN sign-in affordance must be first-class on the input step —
//      buried under "Private league?" is the state v2.1 exists to fix.
//   d. `mflAuthEnabled` must no longer exclude entry, and the entry sign-in
//      must mint DIRECTLY (franchise known) rather than reusing the
//      session-scoped bulk auth-import.
//   e. Backend: both actions gated on their own flag AND the platform flag,
//      running before any mint, storing nothing.

// a. api layer
assert(
  /export async function entryEspnMyLeagues\(/.test(entryApi) &&
    /action: 'my_leagues'/.test(entryApi),
  'V2.1: entryEspnMyLeagues posts the my_leagues action',
);
assert(
  /export async function entryMflAuthLeagues\(/.test(entryApi) &&
    /action: 'auth_leagues'/.test(entryApi),
  'V2.1: entryMflAuthLeagues posts the auth_leagues action',
);
const espnMyLeaguesFn = entryApi.match(
  /export async function entryEspnMyLeagues\([\s\S]{0,900}?return res\?\.leagues/,
);
const mflAuthLeaguesFn = entryApi.match(
  /export async function entryMflAuthLeagues\([\s\S]{0,900}?return res\?\.leagues/,
);
assert(
  !!espnMyLeaguesFn && /skipAuth: true/.test(espnMyLeaguesFn[0]) &&
    !!mflAuthLeaguesFn && /skipAuth: true/.test(mflAuthLeaguesFn[0]),
  'V2.1: both discovery calls are skipAuth (sessionless)',
);
assert(
  !!espnMyLeaguesFn && !/track\(/.test(espnMyLeaguesFn[0]) &&
    !!mflAuthLeaguesFn && !/track\(/.test(mflAuthLeaguesFn[0]),
  'V2.1: discovery calls fire no analytics (the funnel stays on the mint)',
);

// b. ESPN capture → sessionless my-leagues, populating the SAME picker
const captureCb = espnSheet.match(
  /onEspnCookiesCaptured\(\(pair\) => \{[\s\S]{0,1200}?\n    \}\);/,
);
assert(
  !!captureCb &&
    /\} else if \(entry\) \{[\s\S]{0,400}fetchEntryMyLeagues\(pair\.espnS2, pair\.swid\)/.test(
      captureCb[0],
    ),
  'V2.1: ESPN capture with no league id fetches leagues sessionlessly in entry mode',
);
const entryFetchFn = espnSheet.match(
  /async function fetchEntryMyLeagues\([\s\S]{0,900}?\n  \}/,
);
assert(
  !!entryFetchFn && /await entryEspnMyLeagues\(\{ espnS2: s2, swid: sw \}\)/.test(entryFetchFn[0]) &&
    /setMyLeagues\(leagues\)/.test(entryFetchFn[0]),
  'V2.1: fetchEntryMyLeagues populates the existing myLeagues picker state',
);
assert(
  !!entryFetchFn && /catch \{[\s\S]{0,300}setError\(/.test(entryFetchFn[0]),
  'V2.1: a failed my-leagues fetch is soft (manual league-id stays usable)',
);
assert(
  /showingPicker = leaguePicker && !useManualEntry && !!myLeagues && myLeagues\.length > 0/.test(
    espnSheet,
  ),
  'V2.1: the picker renders on data alone — not gated against entry mode',
);

// c. first-class ESPN sign-in on the input step, entry mode only
assert(
  /\{entry && webviewCapture && !showingPicker \? \(/.test(espnSheet) &&
    /testID="espn-link\.entry-signin"/.test(espnSheet),
  'V2.1: ESPN entry input step offers a first-class Sign in to ESPN button',
);
assert(
  /testID="espn-link\.entry-signin"[\s\S]{0,300}onPress=\{launchWebViewCapture\}/.test(espnSheet),
  'V2.1: the entry sign-in reuses the existing WebView capture launcher',
);
assert(
  /testID="espn-link\.private-toggle"/.test(espnSheet) &&
    /testID="espn-link\.s2-input"/.test(espnSheet),
  'V2.1: the manual cookie-paste fallback survives',
);

// d. MFL entry sign-in: enabled, single-select, mints directly
assert(
  /const mflAuthEnabled = useFlag\('mfl\.auth_link'\) && platform === 'mfl';/.test(
    platformSheet,
  ),
  'V2.1: mflAuthEnabled no longer excludes entry mode',
);
assert(
  /testID=\{entry \? 'platform-link\.entry-mfl-signin' : 'platform-link\.mfl-auth-toggle'\}/.test(
    platformSheet,
  ),
  'V2.1: the MFL sign-in entry point is present in entry mode',
);
const mflSignInFn = platformSheet.match(
  /async function mflSignIn\(\)[\s\S]{0,2200}?\n  \}/,
);
assert(
  !!mflSignInFn && /if \(entry\) \{[\s\S]{0,600}await entryMflAuthLeagues\(/.test(mflSignInFn[0]),
  'V2.1: entry sign-in goes through the sessionless auth_leagues action',
);
assert(
  !!mflSignInFn && /setMflPass\(''\)/.test(mflSignInFn[0]) &&
    /setStep\('entry-pick'\)/.test(mflSignInFn[0]),
  'V2.1: entry sign-in clears the password from state and opens the entry list',
);
const mflEntryPick = platformSheet.match(
  /async function mflEntryPickLeague\([\s\S]{0,2200}?\n  \}/,
);
assert(
  !!mflEntryPick && /entryPlatformMint\(\{/.test(mflEntryPick[0]) &&
    /teamId: franchiseId/.test(mflEntryPick[0]) &&
    /onEntrySession\?\.\(/.test(mflEntryPick[0]) &&
    /await linkPlatformLeague\(\{/.test(mflEntryPick[0]),
  'V2.1: an entry league tap mints directly, then runs the canonical import',
);
assert(
  !!mflEntryPick && !/mflAuthImport/.test(mflEntryPick[0]),
  'V2.1: the entry path never uses the session-scoped bulk auth-import',
);
assert(
  !!mflEntryPick &&
    /entryMflPassRef\.current = '';[\s\S]{0,300}await mflAuthLink\(/.test(mflEntryPick[0]) &&
    /catch \{/.test(mflEntryPick[0]),
  'V2.1: the credential re-store is best-effort and drops the password first',
);
assert(
  !/useState.{0,40}entryMflPass/.test(platformSheet) &&
    /const entryMflPassRef = useRef<string>\(''\);/.test(platformSheet),
  'V2.1: the in-flight password is held in a ref, never React state',
);
assert(
  /testID=\{`platform-link\.entry-league\.\$\{lg\.league_id\}`\}/.test(platformSheet) &&
    /disabled=\{!bindable \|\| busyTeamId !== null\}/.test(platformSheet),
  'V2.1: the entry league list is single-select and only franchise-bound rows tap',
);

// e. backend: both actions, gated, before the mint, storing nothing
const actionBlock =
  entryRoute && entryRoute[0].match(
    /action = str\(body\.get\("action"\)[\s\S]*?\n    if platform == "espn":/,
  );
assert(!!actionBlock, 'V2.1: the action branches exist inside the entry route');
assert(
  !!actionBlock &&
    /action != "my_leagues"/.test(actionBlock[0]) &&
    /action != "auth_leagues"/.test(actionBlock[0]),
  'V2.1: both actions are handled (unknown action rejected per platform)',
);
assert(
  !!actionBlock &&
    /is_enabled\("espn\.link"\) or not is_enabled\("espn\.league_picker"\)/.test(actionBlock[0]) &&
    /is_enabled\("mfl\.link"\) or not is_enabled\("mfl\.auth_link"\)/.test(actionBlock[0]),
  'V2.1: each action is gated on its platform flag AND its own flag',
);
assert(
  !!actionBlock && !/upsert_/.test(actionBlock[0]) &&
    !/_extension_build_session\(/.test(actionBlock[0]),
  'V2.1: the action branches store nothing and mint nothing',
);
assert(
  !!entryRoute && !!actionBlock &&
    entryRoute[0].indexOf(actionBlock[0]) <
      entryRoute[0].indexOf('_extension_build_session('),
  'V2.1: the action branches run BEFORE the mint',
);
assert(
  !!actionBlock && /fetch_fan_leagues\(espn_s2, swid\)/.test(actionBlock[0]) &&
    /_mfl\.login\(username, password, year\)/.test(actionBlock[0]) &&
    /_mfl\.fetch_my_leagues\(auth\["cookie"\], year\)/.test(actionBlock[0]),
  'V2.1: the actions reuse the same service functions the session routes use',
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
