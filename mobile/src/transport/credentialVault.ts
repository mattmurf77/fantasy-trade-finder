import * as SecureStore from 'expo-secure-store';

// ── Credential vault (device-auth release 1, LLD §2.7) ──────────────────────
//
// ONE SecureStore key holds every platform credential the device keeps, in a
// versioned envelope. It subsumes the legacy `sleeper.link.jwt` slot: leaving
// two Keychain copies of a 365-day full-account credential — one outside this
// module's accessibility, wipe, and (later) epoch logic — is the failure this
// design prevents.
//
// Every write pins `WHEN_UNLOCKED_THIS_DEVICE_ONLY`, which excludes the item
// from an iCloud Keychain backup. The existing legacy write passes NO
// accessibility option, so today's JWT is backup-eligible — closing that is
// half of why this ships in S0, ahead of any send path that consumes it (S4).
//
// The JWT is stored verbatim as a JSON string field; no base64 or TextDecoder
// is used here (those are the guard/transport's concern, OI-12), so this
// module has no unnamed-primitive dependency.

export const VAULT_KEY = 'ftf.platformCreds';
const LEGACY_SLEEPER_KEY = 'sleeper.link.jwt'; // sendInSleeper.ts:72

const WRITE_OPTS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export interface PlatformCredentialEnvelope {
  v: 1;
  user_id: string; // the FTF session user this envelope belongs to
  platform: 'sleeper';
  secret: string; // the raw JWT, byte-verbatim
  updated_at: string; // ISO
}

function _isEnvelope(x: unknown): x is PlatformCredentialEnvelope {
  const e = x as PlatformCredentialEnvelope | null;
  return (
    !!e &&
    e.v === 1 &&
    typeof e.user_id === 'string' &&
    e.platform === 'sleeper' &&
    typeof e.secret === 'string' &&
    typeof e.updated_at === 'string'
  );
}

/**
 * Read the envelope, but only if it belongs to `userId`.
 *
 * On a user_id mismatch this returns `null` and does NOT wipe (operator
 * decision D-047 / OI-14, deviating from PRD:144's "wipe on mismatch"). The
 * wipe on mismatch fires only from the session-establishment path, where the
 * current user is authoritative — a wipe triggered by any caller passing a
 * stale id would be a self-inflicted denial of service.
 */
export async function readEnvelope(
  userId: string,
): Promise<PlatformCredentialEnvelope | null> {
  let raw: string | null;
  try {
    raw = await SecureStore.getItemAsync(VAULT_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!_isEnvelope(parsed)) return null;
  if (parsed.user_id !== userId) return null; // mismatch: null, never wipe
  return parsed;
}

/** Write the envelope with device-only accessibility. Returns false, never throws. */
export async function writeEnvelope(
  env: PlatformCredentialEnvelope,
): Promise<boolean> {
  try {
    await SecureStore.setItemAsync(VAULT_KEY, JSON.stringify(env), WRITE_OPTS);
    return true;
  } catch {
    return false; // matches the existing swallow-and-continue posture
  }
}

/** Delete the single vault key. */
export async function wipeEnvelope(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(VAULT_KEY);
  } catch {
    /* already gone */
  }
}

/**
 * Subsume the legacy `sleeper.link.jwt` slot into the vault.
 *
 * Order is load-bearing: WRITE the envelope with correct accessibility, VERIFY
 * the read-back byte-for-byte, and only THEN delete the legacy key. A
 * delete-then-write would lose the credential on a Keychain failure. On any
 * failure the legacy key is RETAINED and 'failed' is returned — never a
 * half-migrated state where both copies are gone.
 *
 * This READS the legacy slot; it does not remove the legacy WRITER in
 * sendInSleeper.ts. That writer keeps running until the transport ships (LLD
 * §7.2, S0 vs S5), so a fresh capture on an un-migrated build still persists.
 */
export async function migrateLegacySlot(
  userId: string,
): Promise<'migrated' | 'none' | 'failed'> {
  let legacyRaw: string | null;
  try {
    legacyRaw = await SecureStore.getItemAsync(LEGACY_SLEEPER_KEY);
  } catch {
    return 'failed';
  }
  if (!legacyRaw) return 'none';

  let legacy: { user_id?: unknown; token?: unknown };
  try {
    legacy = JSON.parse(legacyRaw);
  } catch {
    return 'failed';
  }
  // FTF user_id === Sleeper user_id; only migrate the current user's token.
  if (
    typeof legacy.token !== 'string' ||
    legacy.user_id !== userId ||
    typeof legacy.user_id !== 'string'
  ) {
    return 'failed';
  }

  const env: PlatformCredentialEnvelope = {
    v: 1,
    user_id: legacy.user_id,
    platform: 'sleeper',
    secret: legacy.token,
    updated_at: new Date().toISOString(),
  };

  if (!(await writeEnvelope(env))) return 'failed'; // legacy key retained

  // Verify the read-back byte-for-byte before deleting the legacy copy.
  const check = await readEnvelope(userId);
  if (!check || check.secret !== legacy.token) return 'failed';

  try {
    await SecureStore.deleteItemAsync(LEGACY_SLEEPER_KEY);
  } catch {
    // The credential is safely in the vault; a failed legacy delete just
    // leaves a dead copy to reap next time. Report success — the migration
    // (getting the credential into the vault) did complete.
    return 'migrated';
  }
  return 'migrated';
}
