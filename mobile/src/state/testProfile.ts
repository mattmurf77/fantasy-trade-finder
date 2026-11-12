// Onboarding test profile — the device half (docs/plans/onboarding-test-profile/).
//
// The operator's phone switches between their REAL profile and a server-side
// test profile (`qa_tp_<real id>`) that reads as a brand-new user. This module
// owns the swap:
//
//   enter  — the server mints the test session from the real one. The real
//            profile's ESPN / MFL link status is recorded. Then EVERY
//            AsyncStorage key (except the flag cache and this module's own
//            keys) is moved under `ftf_tp_stash:` and removed, and the real
//            session token, last username and Sleeper JWT go to SecureStore
//            stash slots. The test token goes in, the in-memory stores are
//            reset and re-read from the now-empty storage, and navigation
//            restarts at SignIn — a true first launch. There the Sleeper
//            username step is the real flow (the server keeps the test
//            identity); the ESPN / MFL tiles route to the real post-sign-in
//            linking flow (pinTestAccountForLinking); Apple / Google refuse.
//   exit   — the reverse: the test session is ended server-side, the test
//            profile's device keys are dropped, every stashed key and the real
//            token are put back exactly, memory is re-read, and navigation
//            lands where a cold start of the real profile would. No re-login:
//            the real token is a verified, durable 90-day session. Then the
//            real profile's ESPN / MFL links are re-read; one that was
//            connected before and is not now raises the re-link prompt.
//   reset  — the server wipes only the test profile's rows and hands back a
//            fresh test session; the device drops the test profile's keys and
//            restarts onboarding from zero. The stash is untouched.
//
// "Active" is the presence of ACTIVE_KEY, read in App.tsx's boot gate, so the
// banner and the profile survive restarts in whichever profile the app was.
// No target user id is ever sent: the server derives everything from the
// token (pinned by tests/check-test-profile.js).

import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { create } from 'zustand';

import {
  clearSessionToken,
  getLastUsername,
  getSessionToken,
  setSessionToken,
  setTestProfileActive,
} from '../api/client';
import { settleQueueForProfileSwitch } from '../api/events';
import { getEspnLinkStatus } from '../api/sendInEspn';
import { getMflLinkStatus } from '../api/sendInMfl';
import {
  enterTestProfileRemote,
  exitTestProfileRemote,
  getTestProfileStatus,
  resetTestProfileRemote,
} from '../api/testProfile';
import { clearDevicePages } from './devicePageStore';
import { usePremiumImport } from './premiumImport';
import { hydrateQuicksetProgress } from './quicksetProgress';
import { queryClient } from './queryClient';
import { useRosterSetup } from './rosterSetup';
import { useTeamReviewCompletion } from './teamReviewCompletion';
import { useFeatureFlags } from './useFeatureFlags';
import { useFeedback } from './useFeedback';
import { useOnboardingState } from './useOnboardingState';
import { resetSessionMemoryForProfileSwitch, useSession } from './useSession';
import { useTradeQueue } from './useTradeQueue';

export const ACTIVE_KEY = 'ftf_tp_active_v1';
export const STASH_PREFIX = 'ftf_tp_stash:';
/** Device-level keys that are not profile state: kept across a switch. */
/** The real profile's ESPN / MFL link status at enter, for the exit check. */
export const REAL_LINKS_KEY = 'ftf_tp_real_links_v1';
export const KEEP_KEYS: readonly string[] = ['feature_flags_v1', ACTIVE_KEY, REAL_LINKS_KEY];
const SECURE_REAL_TOKEN = 'ftf.tp.realSessionToken';
const SECURE_REAL_USERNAME = 'ftf.tp.realLastUsername';
const SECURE_LAST_USERNAME = 'ftf.lastUsername';
// One device slot holds the captured Sleeper JWT (api/sendInSleeper.ts). A
// Sleeper sign-in inside the test profile must never overwrite the real one.
const SECURE_SLEEPER_JWT = 'sleeper.link.jwt';
const SECURE_REAL_SLEEPER_JWT = 'ftf.tp.realSleeperJwt';
const SECURE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };

interface TestProfileState {
  /** The device is in the test profile (ACTIVE_KEY present). */
  active: boolean;
  /** The SERVER says this real account may use a test profile
   *  (GET /api/test-profile answered, not 404). Gates the Settings row. */
  available: boolean;
  busy: boolean;
  /** Real-profile links found broken after "Back to my profile" (drives
   *  components/TestProfileRelinkPrompt). */
  relink: Array<'espn' | 'mfl'>;
}

export const useTestProfile = create<TestProfileState>(() => ({
  active: false, available: false, busy: false, relink: [],
}));

export type RealLinks = { espn: boolean; mfl: boolean };

/** The CURRENT session's ESPN / MFL link status, via the production status
 *  reads (GET /api/espn/link, GET /api/mfl/auth-link). A route that is off
 *  or fails reads as not linked. */
async function readLinks(): Promise<RealLinks> {
  const [espn, mfl] = await Promise.all([
    getEspnLinkStatus().catch(() => null),
    getMflLinkStatus().catch(() => null),
  ]);
  return { espn: !!espn?.connected && !espn?.expired, mfl: !!mfl?.connected };
}

/** Pure: which links were connected at enter and are not now. */
export function brokenLinks(before: RealLinks | null, after: RealLinks): Array<'espn' | 'mfl'> {
  if (!before) return [];
  return (['espn', 'mfl'] as const).filter((p) => before[p] && !after[p]);
}

const TEST_USER_DISPLAY = 'Test profile';

/** The landing screen's ESPN / MFL tiles sign in through the sessionless
 *  /api/entry/platform, which resolves a platform identity to an account —
 *  the operator's REAL account — so they cannot run inside the test profile.
 *  Instead the tile pins the test profile as a brand-new account with no
 *  league and the caller routes to the league picker with that platform's
 *  link sheet open: the real post-sign-in linking flow. */
export async function pinTestAccountForLinking(): Promise<void> {
  const status = await getTestProfileStatus();
  if (!status?.active || !status.user_id) throw new Error('The test profile is not active.');
  await useSession.getState().setUser({
    user_id: status.user_id, username: status.user_id, display_name: TEST_USER_DISPLAY,
    avatar_id: null, account_only: true,
  });
}

/** Detached, after boot's session revalidation and after a switch: ask the
 *  server whether this account may use a test profile. Never throws; any
 *  failure reads as not available. */
export async function refreshTestProfileAvailability(): Promise<void> {
  try {
    const status = await getTestProfileStatus();
    useTestProfile.setState({ available: !!status?.available });
  } catch {
    useTestProfile.setState({ available: false });
  }
}

function setActive(active: boolean): void {
  setTestProfileActive(active);
  useTestProfile.setState({ active });
}

/** Boot-gate leg (App.tsx): local read only. */
export async function hydrateTestProfile(): Promise<void> {
  try {
    setActive((await AsyncStorage.getItem(ACTIVE_KEY)) === '1');
  } catch {
    setActive(false);
  }
}

function isProfileKey(key: string): boolean {
  return !KEEP_KEYS.includes(key) && !key.startsWith(STASH_PREFIX);
}

async function profileKeys(): Promise<string[]> {
  return (await AsyncStorage.getAllKeys()).filter(isProfileKey);
}

async function stashRealDeviceState(): Promise<void> {
  const keys = await profileKeys();
  const rows = (await AsyncStorage.multiGet(keys)).filter(
    (r): r is [string, string] => r[1] !== null,
  );
  if (rows.length) await AsyncStorage.multiSet(rows.map(([k, v]) => [STASH_PREFIX + k, v]));
  if (keys.length) await AsyncStorage.multiRemove(keys);
  const token = await getSessionToken();
  if (token) await SecureStore.setItemAsync(SECURE_REAL_TOKEN, token, SECURE_OPTS);
  const username = await getLastUsername();
  if (username) await SecureStore.setItemAsync(SECURE_REAL_USERNAME, username, SECURE_OPTS);
  await SecureStore.deleteItemAsync(SECURE_LAST_USERNAME).catch(() => {});
  const jwt = await SecureStore.getItemAsync(SECURE_SLEEPER_JWT).catch(() => null);
  if (jwt) await SecureStore.setItemAsync(SECURE_REAL_SLEEPER_JWT, jwt, SECURE_OPTS);
  await SecureStore.deleteItemAsync(SECURE_SLEEPER_JWT).catch(() => {});
}

async function dropTestDeviceState(): Promise<void> {
  const keys = await profileKeys();
  if (keys.length) await AsyncStorage.multiRemove(keys);
  await SecureStore.deleteItemAsync(SECURE_LAST_USERNAME).catch(() => {});
  await SecureStore.deleteItemAsync(SECURE_SLEEPER_JWT).catch(() => {});
}

async function restoreRealDeviceState(): Promise<void> {
  await dropTestDeviceState();
  const stashKeys = (await AsyncStorage.getAllKeys()).filter((k) => k.startsWith(STASH_PREFIX));
  const rows = (await AsyncStorage.multiGet(stashKeys)).filter(
    (r): r is [string, string] => r[1] !== null,
  );
  if (rows.length) {
    await AsyncStorage.multiSet(rows.map(([k, v]) => [k.slice(STASH_PREFIX.length), v]));
  }
  if (stashKeys.length) await AsyncStorage.multiRemove(stashKeys);
  const token = await SecureStore.getItemAsync(SECURE_REAL_TOKEN).catch(() => null);
  if (token) await setSessionToken(token);
  else await clearSessionToken();
  const username = await SecureStore.getItemAsync(SECURE_REAL_USERNAME).catch(() => null);
  if (username) await SecureStore.setItemAsync(SECURE_LAST_USERNAME, username);
  const jwt = await SecureStore.getItemAsync(SECURE_REAL_SLEEPER_JWT).catch(() => null);
  if (jwt) await SecureStore.setItemAsync(SECURE_SLEEPER_JWT, jwt);
  await SecureStore.deleteItemAsync(SECURE_REAL_TOKEN).catch(() => {});
  await SecureStore.deleteItemAsync(SECURE_REAL_USERNAME).catch(() => {});
  await SecureStore.deleteItemAsync(SECURE_REAL_SLEEPER_JWT).catch(() => {});
}

/** Re-read every in-memory store from the (just swapped) storage. */
async function rehydrateMemory(): Promise<void> {
  resetSessionMemoryForProfileSwitch();
  queryClient.clear();
  for (const store of [useTradeQueue, useFeedback, usePremiumImport, useRosterSetup,
    useTeamReviewCompletion] as const) {
    (store as any).setState((store as any).getInitialState(), true);
  }
  useOnboardingState.setState(useOnboardingState.getInitialState(), true);
  await Promise.all([
    useSession.getState().bootstrap(),
    useOnboardingState.getState().hydrateOnboarding(),
    hydrateQuicksetProgress(),
  ]);
}

/** Navigate as a cold start would (RootNav's initialRoute predicate). */
function restartNavigation(): void {
  // Lazy require — RootNav imports state modules that import us.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { navigationRef } = require('../navigation/RootNav') as typeof import('../navigation/RootNav');
  if (!navigationRef.isReady()) return;
  const { user, league, hasToken } = useSession.getState();
  const hasRealLeague = !!league && league.league_id !== 'no_league';
  const route = !user ? 'SignIn' : !hasRealLeague || !hasToken ? 'LeaguePicker' : 'Main';
  navigationRef.reset({ index: 0, routes: [{ name: route as never }] });
}

async function withBusy<T>(fn: () => Promise<T>): Promise<T> {
  if (useTestProfile.getState().busy) throw new Error('Already switching profiles.');
  useTestProfile.setState({ busy: true });
  try {
    return await fn();
  } finally {
    useTestProfile.setState({ busy: false });
  }
}

/** Real profile → a brand-new test profile. Throws (nothing changed) when
 *  the server refuses. */
export function enterTestProfile(): Promise<void> {
  return withBusy(async () => {
    if (useTestProfile.getState().active) return;
    const session = await enterTestProfileRemote();          // real token still in place
    const realLinks = await readLinks();                       // read with the REAL token
    await settleQueueForProfileSwitch(true);                  // real events go out as real
    await clearDevicePages();                                 // per-account trade cache
    await AsyncStorage.setItem(ACTIVE_KEY, '1');              // first: a crash mid-swap still shows the banner
    await AsyncStorage.setItem(REAL_LINKS_KEY, JSON.stringify(realLinks));
    setActive(true);
    await stashRealDeviceState();
    await setSessionToken(session.session_token);
    await rehydrateMemory();
    void useFeatureFlags.getState().revalidateFlags().catch(() => {});
    restartNavigation();
  });
}

/** Test profile → the real profile, exactly as it was. Never throws on the
 *  network: the real token is restored even if the server is unreachable. */
export function exitTestProfile(): Promise<void> {
  return withBusy(async () => {
    await exitTestProfileRemote().catch(() => {});
    await settleQueueForProfileSwitch(false);                 // test events never go out as real
    await clearDevicePages();
    await restoreRealDeviceState();
    await AsyncStorage.removeItem(ACTIVE_KEY);
    setActive(false);
    await rehydrateMemory();
    void useFeatureFlags.getState().revalidateFlags().catch(() => {});
    restartNavigation();
    void useSession.getState().revalidateSession().then(refreshTestProfileAvailability);
    // (b) A real ESPN/MFL link that was connected at enter and is not now
    // gets the re-link prompt instead of failing silently at the next send.
    let before: RealLinks | null = null;
    try {
      before = JSON.parse((await AsyncStorage.getItem(REAL_LINKS_KEY)) || 'null');
    } catch {
      before = null;
    }
    await AsyncStorage.removeItem(REAL_LINKS_KEY);
    const relink = brokenLinks(before, await readLinks());
    if (relink.length) useTestProfile.setState({ relink });
  });
}

/** Wipe the test profile (server rows + its device state) and start
 *  onboarding again from zero. The real profile's stash is untouched. */
export function resetTestProfile(): Promise<void> {
  return withBusy(async () => {
    const session = await resetTestProfileRemote();
    await settleQueueForProfileSwitch(false);
    await clearDevicePages();
    await dropTestDeviceState();
    await setSessionToken(session.session_token);
    await rehydrateMemory();
    restartNavigation();
  });
}

/** The re-link prompt handled (or dismissed) one platform. */
export function clearRelink(platform: 'espn' | 'mfl'): void {
  useTestProfile.setState((s) => ({ relink: s.relink.filter((p) => p !== platform) }));
}
