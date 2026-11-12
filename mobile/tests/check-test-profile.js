#!/usr/bin/env node
// Static guard: the onboarding test profile's client half
// (docs/plans/onboarding-test-profile/). Source-text checks under plain node.
//
//   1  the Settings row is gated on the SERVER capability (available && !active)
//      and the Testing hub entry opens for it
//   2  the banner wraps RootNav (outside every navigator), shows Back + Reset
//      wired to exit/reset, and renders only children when not active
//   3  the profile choice survives restarts (ACTIVE_KEY written on enter,
//      removed on exit, read in App.tsx's boot gate)
//   4  no client-supplied target id anywhere in the wire client
//   5  entering clears ALL first-run state: only the flag cache + the marker
//      are kept; every known first-run key is profile state
//   6  switch-back restores the real token; enter stashes before the swap;
//      analytics never cross profiles
//   7  identity-minting calls are refused client-side while in the test
//      profile; no forked Sleeper step
//   8  no linking shortcut (removed per the operator's 2026-11-11 ruling)
//
// Run: node tests/check-test-profile.js

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

let failures = 0;
let checks = 0;
function check(cond, msg) {
  checks += 1;
  if (!cond) {
    failures += 1;
    console.error(`FAIL  ${msg}`);
  }
}

const state = read('src/state/testProfile.ts');
// The swap's storage steps live in the pure, crash-safe module (review M4);
// tests/check-test-profile-swap.js EXECUTES them at every kill point. Here we
// pin that the device half uses it and in which order.
const swap = read('src/utils/testProfileSwap.ts');
const api = read('src/api/testProfile.ts');
const client = read('src/api/client.ts');
const signInScreen = read('src/screens/SignInScreen.tsx');
const app = read('App.tsx');
const banner = read('src/components/TestProfileBanner.tsx');
const section = read('src/screens/settings/sections/TestingSection.tsx');
const surface = read('src/screens/settings/useTesterSurface.ts');
const espnSheet = read('src/components/EspnLinkSheet.tsx');
const platformSheet = read('src/components/PlatformLinkSheet.tsx');

function fnBody(src, name) {
  const i = src.search(new RegExp(`export (?:async )?function ${name}\\(`));
  if (i < 0) return '';
  const j = src.indexOf('\nexport ', i + 1);
  return src.slice(i, j < 0 ? undefined : j);
}

// ── 1 Settings row gated on the server capability ──────────────────────────
check(/testProfileOffered\s*=\s*useTestProfile\(\(s\)\s*=>\s*s\.available\s*&&\s*!s\.active\)/.test(section),
  '1a TestingSection: row gate is useTestProfile(available && !active)');
check(/\{testProfileOffered \? \(\s*<Pressable\s+testID="settings\.testing\.test-profile"/.test(section),
  '1b TestingSection: the row renders only under testProfileOffered');
check(/onPress=\{confirmTestProfile\}/.test(section) && /enterTestProfile\(\)/.test(section),
  '1c the row confirms, then calls enterTestProfile()');
check(/useTestProfile\(\(s\)\s*=>\s*s\.available \|\| s\.active\)/.test(surface)
  && /\|\| testProfile;/.test(surface), '1d useTesterSurface opens Testing for the offered account');
check(/available: !!status\?\.available/.test(state) && /getTestProfileStatus\(\)/.test(state),
  '1e `available` comes only from GET /api/test-profile');
check(/refreshTestProfileAvailability\(\)/.test(app), '1f App boot asks the server for availability');

// ── 2 banner always mounted while active ───────────────────────────────────
check(/<TestProfileBanner>\s*<RootNav /.test(app), '2a App.tsx: TestProfileBanner wraps RootNav');
check(/if \(!active\) return <>\{children\}<\/>;/.test(banner), '2b banner renders only children when inactive');
check(/testID="test-profile\.banner"/.test(banner), '2c banner testID present');
check(/testID="test-profile\.banner\.back"[\s\S]*?onPress=\{\(\) => exitTestProfile\(\)/.test(banner),
  '2d Back to my profile → exitTestProfile');
check(/testID="test-profile\.banner\.reset"[\s\S]*?onPress=\{confirmReset\}/.test(banner)
  && /onPress: \(\) => resetTestProfile\(\)/.test(banner), '2e Reset (confirmed) → resetTestProfile');
check(/Back to my profile/.test(banner) && /TEST PROFILE/.test(banner), '2f banner copy names the profile + the way back');

// ── 2b a dead test session never leads to a real one (review M3) ────────────
const clientSrc = read('src/api/client.ts');
const authHeaders = (clientSrc.match(/export async function testProfileAuthHeaders[\s\S]*?\n}\n/) || [''])[0];
check(/apiRequest<\{ active\?: boolean \}>\('\/api\/test-profile'/.test(authHeaders)
  && /if \(!status\?\.active\) throw testProfileEnded\(\)/.test(authHeaders)
  && /if \(!tok\) throw testProfileEnded\(\)/.test(authHeaders),
  '2b1 sign-in inside the test profile is refused unless the server says the session is active');
check(/res!\.status === 401 && _testProfileActive\)[\s\S]{0,80}_onTestProfileEnded/.test(clientSrc),
  '2b2 any 401 while in the test profile marks it ended');
check(/ended \? 'TEST PROFILE ENDED' : 'TEST PROFILE'/.test(banner) && /ended \? null : <Pressable\s+testID="test-profile\.banner\.reset"/.test(banner),
  '2b3 an ended test profile offers only "Back to my profile"');
check(/verifyTestProfileWithServer\(\)/.test(app), '2b4 boot asks the server whether the test session is still live');

// ── 3 survives restarts ────────────────────────────────────────────────────
const enter = fnBody(state, 'enterTestProfile');
const exit = fnBody(state, 'exitTestProfile');
const reset = fnBody(state, 'resetTestProfile');
check(/export const ACTIVE_KEY = 'ftf_tp_active_v1'/.test(swap), '3a ACTIVE_KEY defined');
check(/enterSwap\(SWAP_STORE, session\.session_token\)/.test(enter)
  && /multiSet\(\[\[ACTIVE_KEY, '1'\]\]\)/.test(fnBody(swap, 'enterSwap')), '3b enter persists ACTIVE_KEY (inside the swap)');
check(/exitSwap\(SWAP_STORE\)/.test(exit) && /multiRemove\(\[ACTIVE_KEY\]\)/.test(swap), '3c exit removes ACTIVE_KEY (inside the swap)');
check(/reconcileSwap\(SWAP_STORE\)/.test(fnBody(state, 'hydrateTestProfile')),
  '3d hydrateTestProfile reconciles an interrupted swap, then reads ACTIVE_KEY');
check(/hydrateTestProfile\(\)\.catch\(\(\) => \{\}\)\.then\(\(\) => Promise\.all\(\[/.test(app),
  '3e hydrateTestProfile runs FIRST in the boot gate, before every other storage read');

// ── 4 no client-supplied target id ─────────────────────────────────────────
const bodies = [...api.matchAll(/api\.(?:post|get)(?:<[^>]*>)?\(\s*('[^']*'|`[^`]*`)\s*(?:,\s*(\{[\s\S]*?\}))?/g)];
check(bodies.length >= 4, `4a found the wire calls (${bodies.length})`);
for (const [, url, body] of bodies) {
  check(!url.includes('${'), `4b no interpolated id in ${url}`);
  check(!/user_id|real_id|profile_id|target|account/.test(body || ''), `4c no target id in body of ${url}`);
}

// ── 5 entering clears ALL first-run state ──────────────────────────────────
check(/export const KEEP_KEYS: readonly string\[\] = \[\s*'feature_flags_v1', ACTIVE_KEY, SWAP_KEY, STASH_DONE_KEY, REAL_LINKS_KEY,\s*\];/.test(swap),
  '5a only the flag cache, the swap markers and the real-link record survive a switch');
const FIRST_RUN_KEYS = [
  'ftf_onboarding_state_v1', 'ftf_tiers_saved_cache_v1', 'REACT_QUERY_OFFLINE_CACHE',
  'ftf_rank_method_pref', 'sleeper_user', 'sleeper_league', 'sleeper_leagues', 'ftf_invite_intent',
  'ftf_whats_new_seen_version', 'ftf_team_review_collapsed', 'ftf_team_review_completed',
  'ftf_roster_setup_v1', 'ftf_pick_board_confirmed_v1', 'ftf_anchor_done_v1_sf_tep',
  'ftf.trios.speedMode', 'ftf:tradecalc:v1', 'ftf:trades:fairness_on', 'ftf_active_format',
  'ftf.premium_import.v1', 'ftf.rating.anchor_ts.v1', 'ftf_inapp_feedback_v1', 'ftf.entitlements.v1',
  'ftf.events.queue.v1', 'ftf.recpicks.queue.v1', 'ftf_trade_queue_123', 'ftf_founder_welcome_shown_123',
];
const keep = ['feature_flags_v1', 'ftf_tp_active_v1', 'ftf_tp_swap_v1', 'ftf_tp_stash_done_v1', 'ftf_tp_real_links_v1'];
for (const k of FIRST_RUN_KEYS) check(!keep.includes(k) && !k.startsWith('ftf_tp_stash:'), `5b ${k} is moved by the stash`);
check(/function isProfileKey\(key: string\): boolean \{\s*return !KEEP_KEYS\.includes\(key\) && !key\.startsWith\(STASH_PREFIX\);/.test(swap),
  '5c every key that is not kept is profile state');
check(/enterSwap\(/.test(enter) && /rehydrateMemory\(\)/.test(enter) && /restartNavigation\(\)/.test(enter),
  '5d enter: swap, re-read memory, restart navigation (no force-quit)');
check(/queryClient\.clear\(\)/.test(state) && /useOnboardingState\.getInitialState\(\)/.test(state)
  && /hydrateQuicksetProgress\(\)/.test(state) && /resetSessionMemoryForProfileSwitch\(\)/.test(state),
  '5e in-memory stores are reset and re-read');
check(/navigationRef\.reset\(/.test(state), '5f navigation restarts via navigationRef.reset');

// ── 6 switch-back restores the real token; ordering; analytics ─────────────
const stash = fnBody(swap, 'enterSwap');
const restore = (swap.match(/async function restoreFromStash[\s\S]*?\n}\n/) || [''])[0];
check(/setSecure\(SECURE_REAL_TOKEN, real\)/.test(stash), '6a enter stashes the real token');
check(/getSecure\(SECURE_REAL_TOKEN\)[\s\S]*?setToken\(real\)/.test(restore), '6b exit restores the real token');
check(/WHEN_UNLOCKED_THIS_DEVICE_ONLY/.test(state) && /key\.startsWith\('ftf\.tp\.'\) \? SECURE_OPTS/.test(state),
  '6c stashed token is device-only');
check(/\['sleeper\.link\.jwt', 'ftf\.tp\.realSleeperJwt'\]/.test(swap) && /SECURE_PROFILE_SLOTS/.test(stash)
  && /SECURE_PROFILE_SLOTS/.test(restore),
  '6c2 the device\'s single Sleeper JWT slot is stashed and restored');
const order = (s, a, b) => s.indexOf(a) >= 0 && s.indexOf(b) > s.indexOf(a);
check(order(enter, 'enterTestProfileRemote()', 'enterSwap(')
  && order(stash, "STASH_DONE_KEY, '1'", 'setToken(testToken)')
  && order(stash, 'setToken(testToken)', "[[ACTIVE_KEY, '1']]"),
  '6d enter: server first, then the complete stash, then the test token, then ACTIVE');
check(/settleQueueForProfileSwitch\(true\)/.test(enter), '6e enter sends queued REAL events first');
check(/settleQueueForProfileSwitch\(false\)/.test(exit) && /settleQueueForProfileSwitch\(false\)/.test(reset),
  '6f exit/reset drop test events, never send them under the real token');
check(/resetSwap\(SWAP_STORE, session\.session_token\)/.test(reset)
  && !/restoreFromStash|removeStash|STASH_PREFIX/.test((swap.match(/export async function resetSwap[\s\S]*?\n}\n/) || ['x'])[0]),
  '6g reset never touches the real stash');

// ── 7 identity-minting refused; Sleeper step resolves inside ───────────────
for (const p of ['/api/extension/auth', '/api/auth/apple', '/api/auth/google', '/api/entry/platform', '/api/session/demo']) {
  check(client.includes(`'${p}'`), `7a client blocks ${p} in the test profile`);
}
check(/if \(_testProfileActive && \(TEST_PROFILE_BLOCKED_PATHS\.some/.test(client), '7b blocked before any request');
check(/path\.split\('\?'\)\[0\] === TEST_PROFILE_TOKEN_REQUIRED_PATH && !opts\.headers\?\.\['X-Session-Token'\]/.test(client)
  && /TEST_PROFILE_TOKEN_REQUIRED_PATH = '\/api\/extension\/auth'/.test(client),
  '7b2 the Sleeper username step is refused unless it carries the test token');
const authTs = read('src/api/auth.ts');
check(/\.\.\.\(\(await testProfileAuthHeaders\?\.\(\)\) \?\? \{\}\)/.test(authTs),
  '7b3 signIn sends the test token inside the test profile (the real Sleeper step)');
check(!/testProfileSleeperSignIn|\/api\/test-profile\/sleeper/.test(signInScreen + api)
  && /const auth = await signIn\(usernameToAuth\);/.test(signInScreen),
  '7c no forked Sleeper step: SignIn calls the production signIn (operator rulings 2026-11-11/12)');
check(/setTestProfileActive\(active\)/.test(state), '7d state drives the client flag');

// ── 8 no linking shortcut (operator ruling 2026-11-11: linking must be the
//      real production flow; the 3(b) shortcut is removed, not toggled) ─────
check(!fs.existsSync(path.join(ROOT, 'src/components/TestProfileLinkPanel.tsx')),
  '8a the shortcut panel is gone');
check(!/TestProfileLinkPanel|useTestProfile/.test(espnSheet + platformSheet),
  '8b the ESPN / MFL sheets are the production sheets, untouched');
check(!/\/api\/test-profile\/link|testProfileLinkPlatform/.test(api), '8c no shortcut route in the wire client');

// ── 9 option A: start as a new account at "Connect a League"; real-link care ──
const relinkPrompt = read('src/components/TestProfileRelinkPrompt.tsx');
check(!/setUser\(/.test(enter) && !/setUser\(/.test(reset) && /restartNavigation\(\)/.test(reset),
  '9a enter and reset leave no user: navigation restarts at SignIn (a true first launch)');
check(/user_id: status\.user_id, username: status\.user_id, display_name: TEST_USER_DISPLAY,\s*avatar_id: null, account_only: true/.test(state)
  && /if \(isTestProfileActive\(\)\) \{[\s\S]*?pinTestAccountForLinking\(\)[\s\S]*?\(onAccountSignedIn \?\? onSignedIn\)\(intent\)/.test(signInScreen),
  '9b the landing ESPN/MFL tiles continue to the real post-sign-in linking flow as a new account');
check(order(enter, 'enterTestProfileRemote()', 'readLinks()') && order(enter, 'readLinks()', 'enterSwap('),
  '9c the real ESPN/MFL link status is read with the REAL token, before the swap');
check(/AsyncStorage\.setItem\(REAL_LINKS_KEY, JSON\.stringify\(realLinks\)\)/.test(enter),
  '9d the real link status is recorded for the exit check');
check(order(exit, 'exitSwap(', 'readLinks()') && /brokenLinks\(before, await readLinks\(\)\)/.test(exit)
  && /useTestProfile\.setState\(\{ relink \}\)/.test(exit), '9e exit re-reads the real links and flags broken ones');
check(/before\[p\] && !after\[p\]/.test(state), '9f a link is "broken" only if it was connected at enter and is not now');
check(/<\/TestProfileBanner>\s*<TestProfileRelinkPrompt \/>/.test(app), '9g the re-link prompt is mounted outside the banner');
check(/navigationRef\.navigate\('EspnConnect', \{ reason: 'send' \}\)/.test(relinkPrompt)
  && /<MflSignInSheet/.test(relinkPrompt), '9h the prompt opens the normal ESPN / MFL re-link surfaces');
for (const p of ['/api/espn/link', '/api/espn/import', '/api/mfl/link', '/api/mfl/import', '/api/mfl/auth-link', '/api/mfl/auth-import']) {
  check(!client.includes(`'${p}'`), `9i the real linking route ${p} is NOT client-blocked`);
}
check(client.includes("'/api/account/link-sleeper'"), '9j Sleeper linking stays refused in the test profile');
const section2 = read('src/screens/settings/sections/TestingSection.tsx');
check(/first launch/.test(section2) && /re-link/.test(section2),
  '9k the confirm sheet names the start screen and the re-link risk');

if (failures) {
  console.error(`\n${failures} of ${checks} test-profile check(s) failed.`);
  process.exit(1);
}
console.log(`ok    test-profile: ${checks} checks`);
