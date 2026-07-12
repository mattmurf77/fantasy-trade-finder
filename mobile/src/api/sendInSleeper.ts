// "Send in Sleeper" — FTF backend routes that link a Sleeper account and
// propose trades directly (flagged beta; ToS-adverse — see
// docs/plans/sleeper-write-capture-runbook.md). All calls are session-authed
// by the shared client. Errors surface as ApiError; callers branch on
// `(err.body as any)?.error` (sleeper_not_linked | sleeper_expired |
// sleeper_write_failed | sleeper_unconfigured | feature_disabled).

import * as SecureStore from 'expo-secure-store';

import { api, apiRequest, ApiError } from './client';

export interface SleeperLinkStatus {
  connected: boolean;
  sleeper_user_id?: string;
  expires_at?: string;
  expired?: boolean;
  /** POST only (account-auth P1): true when the captured token's claim
   *  matched the session user AND the live-token proof passed — the
   *  session is now VERIFIED. False = linked but unverified (oracle
   *  unreachable); retry by reconnecting. */
  verified?: boolean;
}

export interface ProposeTradePayload {
  league_id: string;
  their_user_id: string;          // opponent's Sleeper user_id (== FTF user_id)
  give_player_ids: string[];      // players I send
  receive_player_ids: string[];   // players I receive
}

export interface ProposeTradeResult {
  status: string;                 // "proposed" on success
  transaction_id?: string;
}

// GET — is a Sleeper account linked, and is the token still valid?
export async function getSleeperLinkStatus(): Promise<SleeperLinkStatus> {
  return api.get<SleeperLinkStatus>('/api/sleeper/link');
}

// POST — store a freshly captured Sleeper JWT (from the login webview).
export async function linkSleeperToken(token: string): Promise<SleeperLinkStatus> {
  return api.post<SleeperLinkStatus>('/api/sleeper/link', { token });
}

// DELETE — disconnect (drop the stored token). Also clears this device's
// Keychain copy (#126 R-5) so a deliberate disconnect is never undone by
// the silent replay below; other devices self-neutralize via the R-2.2
// pre-check (`connected: false` → they delete their own copy).
export async function unlinkSleeper(): Promise<{ connected: boolean }> {
  const res = await apiRequest<{ connected: boolean }>('/api/sleeper/link', { method: 'DELETE' });
  await clearPersistedSleeperToken();
  return res;
}

// ── #126: durable verification — Keychain persistence + silent replay ────
//
// The captured Sleeper JWT is persisted device-side (expo-secure-store →
// iOS Keychain; survives app updates) and silently replayed through the
// existing hard-verified POST /api/sleeper/link on fresh sessions, so the
// user never re-captures after an app update / session eviction. The
// server's verification predicate is untouched — the client just repeats
// the same proof it presented at capture time. Single {user_id, token}
// slot (PRD N-4: per-user keys can never be swept — SecureStore has no
// key enumeration). Never AsyncStorage, never logged, never sent anywhere
// except our own /api/sleeper/link.

const SECURE_SLEEPER_JWT_KEY = 'sleeper.link.jwt';

interface PersistedSleeperToken {
  user_id: string;
  token: string;
}

export async function persistSleeperToken(userId: string, token: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(
      SECURE_SLEEPER_JWT_KEY,
      JSON.stringify({ user_id: userId, token }),
    );
  } catch {
    /* Keychain write failed — non-fatal; worst case is one manual recapture */
  }
}

export async function getPersistedSleeperToken(): Promise<PersistedSleeperToken | null> {
  try {
    const raw = await SecureStore.getItemAsync(SECURE_SLEEPER_JWT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.user_id === 'string' && typeof parsed.token === 'string') {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

export async function clearPersistedSleeperToken(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(SECURE_SLEEPER_JWT_KEY);
  } catch {
    /* already gone */
  }
}

export type ReplayOutcome = 'verified' | 'rejected' | 'inconclusive' | 'none';

// Single-flight: concurrent callers (signIn warm-up + sessionInit race)
// share one in-flight replay. Cleared on settle — a 'rejected' outcome is
// terminal via the Keychain delete (the delete is the memo); 'inconclusive'
// retries naturally on the next session establishment.
let _replayInFlight: { userId: string; promise: Promise<ReplayOutcome> } | null = null;

/** #126 silent verification replay (PRD R-2). Presents the persisted Sleeper
 *  JWT to the existing hard-verified POST /api/sleeper/link so a fresh
 *  server session re-verifies with zero user friction. Never throws. */
export function maybeReplaySleeperVerification(userId: string): Promise<ReplayOutcome> {
  if (_replayInFlight && _replayInFlight.userId === userId) {
    return _replayInFlight.promise;
  }
  const promise = _runReplay(userId).catch((): ReplayOutcome => 'inconclusive');
  _replayInFlight = { userId, promise };
  promise.finally(() => {
    if (_replayInFlight?.promise === promise) _replayInFlight = null;
  });
  return promise;
}

async function _runReplay(userId: string): Promise<ReplayOutcome> {
  // 1. Bail fast — no I/O beyond the Keychain read.
  const stored = await getPersistedSleeperToken();
  if (!stored || stored.user_id !== userId) return 'none';

  // 2. Revocation pre-check (R-2.2, non-negotiable): POST /api/sleeper/link
  //    stores the credential before stamping verification, so replay and
  //    re-link are inseparable. Without this check, Disconnect on device A
  //    would be silently resurrected by device B's next replay. Never POST
  //    the token without a confirmed live server-side link.
  let status: SleeperLinkStatus;
  try {
    status = await getSleeperLinkStatus();
  } catch {
    // 404 feature_disabled / 401 / network / anything else → skip + retain.
    console.log('[sleeper-replay] pre-check failed — inconclusive');
    return 'inconclusive';
  }
  if (!status?.connected) {
    // Sticky revocation: the user disconnected somewhere — honor it here.
    await clearPersistedSleeperToken();
    console.log('[sleeper-replay] server link disconnected — local copy cleared');
    return 'rejected';
  }
  // (`expired: true` describes the server's copy and does not short-circuit —
  //  the local token may differ; step 3's closed rule owns every outcome.)

  // 3. Replay the proof through the existing hard-verified route.
  //
  // 4. Outcomes — CLOSED RULE (R-2.4): the Keychain copy is deleted on
  //    EXACTLY four conditions (pre-check connected:false above, plus the
  //    three definitive rejection codes below) and no others. Every other
  //    outcome — named or unknown, present or future — retains the copy and
  //    returns 'inconclusive'. Deleting from the catch-all is a build error.
  try {
    const res = await linkSleeperToken(stored.token);
    if (res?.verified === true) {
      console.log('[sleeper-replay] verified');
      return 'verified';
    }
    // 200 verified:false — oracle inconclusive server-side. Retain.
    console.log('[sleeper-replay] linked but unverified — inconclusive');
    return 'inconclusive';
  } catch (e: any) {
    if (e instanceof ApiError) {
      const code = (e.body as any)?.error;
      if (
        (e.status === 400 && code === 'token_expired') ||
        (e.status === 403 && (code === 'token_rejected' || code === 'token_user_mismatch'))
      ) {
        // Definitive rejection — a rejected 365-day token cannot heal.
        await clearPersistedSleeperToken();
        console.log(`[sleeper-replay] rejected (${code}) — local copy cleared`);
        return 'rejected';
      }
    }
    // Catch-all: 404 feature_disabled, 401, 503, 500, other 4xx/5xx,
    // network/timeout/unparseable — RETAIN and retry next establishment.
    console.log('[sleeper-replay] replay failed — inconclusive');
    return 'inconclusive';
  }
}

// POST — propose the trade to Sleeper. Server resolves both roster_ids.
export async function proposeTradeToSleeper(
  payload: ProposeTradePayload,
): Promise<ProposeTradeResult> {
  return api.post<ProposeTradeResult>('/api/trades/propose', payload);
}
