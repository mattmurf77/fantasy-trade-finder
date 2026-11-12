// Onboarding test profile — the crash-safe device swap (review M4).
//
// ZERO runtime imports: tests/check-test-profile-swap.js transpiles this file
// and runs every function against an in-memory store that is killed after
// each operation, then asserts that `reconcileSwap` always lands the device
// FULLY real or FULLY test — never mixed, and never with the real token lost.
//
// The swap is phased. `SWAP_KEY` names the phase in progress; it is written
// before a phase's first destructive step and cleared after its last, so a
// kill anywhere leaves a phase `reconcileSwap` knows how to finish or undo:
//
//   enter  entering → (stash copied) entering:stashed → token swapped → ACTIVE → done
//          A kill before ACTIVE rolls BACK to real (the test token lived only
//          in memory). Originals are removed only after the stash is complete.
//   exit   exiting → (test keys dropped) exiting:dropped → (real restored)
//          exiting:restored → ACTIVE removed → stash removed → done
//          Always rolls FORWARD to real. Test keys are dropped only while the
//          stash is complete, so a replay can never delete restored real keys.
//   reset  resetting → (test keys dropped) → new token → done. Rolls forward;
//          a kill before the new token keeps the old (now dead) test token,
//          which the app reads as "test profile ended".
//
// The real token is only ever replaced by the stashed real token, and is
// cleared only when the current token is a test token (`isTestToken`).

export const ACTIVE_KEY = 'ftf_tp_active_v1';
export const STASH_PREFIX = 'ftf_tp_stash:';
export const SWAP_KEY = 'ftf_tp_swap_v1';
export const STASH_DONE_KEY = 'ftf_tp_stash_done_v1';
export const REAL_LINKS_KEY = 'ftf_tp_real_links_v1';
/** Device-level keys that are not profile state: never stashed or dropped. */
export const KEEP_KEYS: readonly string[] = [
  'feature_flags_v1', ACTIVE_KEY, SWAP_KEY, STASH_DONE_KEY, REAL_LINKS_KEY,
];
/** Secure slots that are profile state, and where enter parks the real ones. */
export const SECURE_PROFILE_SLOTS: ReadonlyArray<readonly [string, string]> = [
  ['ftf.lastUsername', 'ftf.tp.realLastUsername'],
  // The captured Sleeper JWT (api/sendInSleeper.ts): a Sleeper sign-in inside
  // the test profile must never overwrite the real one.
  ['sleeper.link.jwt', 'ftf.tp.realSleeperJwt'],
];
export const SECURE_REAL_TOKEN = 'ftf.tp.realSessionToken';
/** Mirrors backend server._TP_TOKEN_PREFIX: every switch-minted test token. */
export const TEST_TOKEN_PREFIX = 'tp.';

export type Phase =
  | 'entering' | 'entering:stashed'
  | 'exiting' | 'exiting:dropped' | 'exiting:restored'
  | 'resetting';

export interface SwapStore {
  getAllKeys(): Promise<readonly string[]>;
  multiGet(keys: readonly string[]): Promise<ReadonlyArray<readonly [string, string | null]>>;
  multiSet(rows: Array<[string, string]>): Promise<void>;
  multiRemove(keys: readonly string[]): Promise<void>;
  getSecure(key: string): Promise<string | null>;
  setSecure(key: string, value: string): Promise<void>;
  deleteSecure(key: string): Promise<void>;
  getToken(): Promise<string | null>;
  setToken(token: string): Promise<void>;
  clearToken(): Promise<void>;
}

export function isTestToken(token: string | null | undefined): boolean {
  return !!token && token.startsWith(TEST_TOKEN_PREFIX);
}

function isProfileKey(key: string): boolean {
  return !KEEP_KEYS.includes(key) && !key.startsWith(STASH_PREFIX);
}

async function getOne(s: SwapStore, key: string): Promise<string | null> {
  const rows = await s.multiGet([key]);
  return rows.length ? rows[0][1] : null;
}

async function setPhase(s: SwapStore, phase: Phase): Promise<void> {
  await s.multiSet([[SWAP_KEY, phase]]);
}

async function dropTestKeys(s: SwapStore): Promise<void> {
  // Only ever called while the stash is complete: every real key is safe in it.
  const keys = (await s.getAllKeys()).filter(isProfileKey);
  if (keys.length) await s.multiRemove(keys);
  for (const [slot] of SECURE_PROFILE_SLOTS) await s.deleteSecure(slot);
}

/** Put the stashed real state back (idempotent: the stash is not removed). */
async function restoreFromStash(s: SwapStore): Promise<void> {
  const stashKeys = (await s.getAllKeys()).filter((k) => k.startsWith(STASH_PREFIX));
  const rows = (await s.multiGet(stashKeys)).filter(
    (r): r is readonly [string, string] => r[1] !== null,
  );
  if (rows.length) await s.multiSet(rows.map(([k, v]) => [k.slice(STASH_PREFIX.length), v]));
  for (const [slot, parked] of SECURE_PROFILE_SLOTS) {
    const v = await s.getSecure(parked);
    if (v !== null) await s.setSecure(slot, v);
  }
  const real = await s.getSecure(SECURE_REAL_TOKEN);
  const current = await s.getToken();
  if (real !== null) {
    if (current !== real) await s.setToken(real);
  } else if (isTestToken(current)) {
    await s.clearToken();       // no real token was ever stashed; never keep a test one
  }
}

async function removeStash(s: SwapStore): Promise<void> {
  const stashKeys = (await s.getAllKeys()).filter((k) => k.startsWith(STASH_PREFIX));
  if (stashKeys.length) await s.multiRemove(stashKeys);
  for (const [, parked] of SECURE_PROFILE_SLOTS) await s.deleteSecure(parked);
  await s.deleteSecure(SECURE_REAL_TOKEN);
  await s.multiRemove([STASH_DONE_KEY]);
}

/** Real → test. `testToken` is the session the server just minted. */
export async function enterSwap(s: SwapStore, testToken: string): Promise<void> {
  await setPhase(s, 'entering');
  const real = await s.getToken();
  if (real !== null) await s.setSecure(SECURE_REAL_TOKEN, real);
  for (const [slot, parked] of SECURE_PROFILE_SLOTS) {
    const v = await s.getSecure(slot);
    if (v !== null) await s.setSecure(parked, v);
  }
  const keys = (await s.getAllKeys()).filter(isProfileKey);
  const rows = (await s.multiGet(keys)).filter(
    (r): r is readonly [string, string] => r[1] !== null,
  );
  if (rows.length) await s.multiSet(rows.map(([k, v]) => [STASH_PREFIX + k, v]));
  await s.multiSet([[STASH_DONE_KEY, '1'], [SWAP_KEY, 'entering:stashed']]);
  await dropTestKeys(s);        // the originals: every one is in the stash now
  await s.setToken(testToken);
  await s.multiSet([[ACTIVE_KEY, '1']]);
  await s.multiRemove([SWAP_KEY]);
}

async function continueExit(s: SwapStore, phase: Phase): Promise<void> {
  if (phase === 'exiting') {
    await dropTestKeys(s);
    await setPhase(s, 'exiting:dropped');
    phase = 'exiting:dropped';
  }
  if (phase === 'exiting:dropped') {
    await restoreFromStash(s);
    await setPhase(s, 'exiting:restored');
  }
  await s.multiRemove([ACTIVE_KEY]);
  await removeStash(s);
  await s.multiRemove([SWAP_KEY]);
}

/** Test → real, exactly as it was. */
export async function exitSwap(s: SwapStore): Promise<void> {
  if ((await getOne(s, STASH_DONE_KEY)) !== '1') {
    // Nothing was stashed, so nothing may be dropped; only a test token goes.
    if (isTestToken(await s.getToken())) await s.clearToken();
    await s.multiRemove([ACTIVE_KEY, SWAP_KEY]);
    return;
  }
  await setPhase(s, 'exiting');
  await continueExit(s, 'exiting');
}

/** Test → a fresh test profile. The stash is untouched. */
export async function resetSwap(s: SwapStore, newTestToken: string): Promise<void> {
  await setPhase(s, 'resetting');
  if ((await getOne(s, STASH_DONE_KEY)) === '1') await dropTestKeys(s);
  await s.setToken(newTestToken);
  await s.multiRemove([SWAP_KEY]);
}

async function rollBackEnter(s: SwapStore): Promise<void> {
  if ((await getOne(s, STASH_DONE_KEY)) === '1') {
    await restoreFromStash(s);   // originals may be partly removed: put them back
  } else if (isTestToken(await s.getToken())) {
    await s.clearToken();
  }
  await removeStash(s);
  await s.multiRemove([ACTIVE_KEY, SWAP_KEY]);
}

/** Boot, before anything reads storage: finish or undo an interrupted phase,
 *  then repair a mixed state. Returns which profile the device is in. */
export async function reconcileSwap(s: SwapStore): Promise<'real' | 'test'> {
  const phase = (await getOne(s, SWAP_KEY)) as Phase | null;
  const active = (await getOne(s, ACTIVE_KEY)) === '1';
  if (phase === 'entering' || phase === 'entering:stashed') {
    if (active) await s.multiRemove([SWAP_KEY]);   // only the marker was left
    else await rollBackEnter(s);
  } else if (phase === 'exiting' || phase === 'exiting:dropped' || phase === 'exiting:restored') {
    await continueExit(s, phase);
  } else if (phase === 'resetting') {
    if ((await getOne(s, STASH_DONE_KEY)) === '1') await dropTestKeys(s);
    await s.multiRemove([SWAP_KEY]);
  } else if (phase !== null) {
    await s.multiRemove([SWAP_KEY]);             // unknown marker: ignore it
  }
  const nowActive = (await getOne(s, ACTIVE_KEY)) === '1';
  const stashed = (await getOne(s, STASH_DONE_KEY)) === '1';
  const testToken = isTestToken(await s.getToken());
  if (nowActive && stashed && testToken) return 'test';
  if (nowActive || stashed || testToken) {
    // Mixed (an older build's swap, or a lost token): go back to real.
    if (stashed) {
      await setPhase(s, 'exiting');
      await continueExit(s, 'exiting');
    } else {
      if (testToken) await s.clearToken();
      await s.multiRemove([ACTIVE_KEY]);
    }
  }
  return 'real';
}
