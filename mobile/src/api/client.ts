// apiClient — thin fetch wrapper. Mirrors the web's `apiFetch` in web/js/app.js:
//   - auto-attaches X-Session-Token (stored in expo-secure-store)
//   - JSON by default
//   - 401 → clears session and surfaces a recognisable error for the UI
//
// One place owns the base URL and the token getter so screen-level code
// never has to touch fetch directly.

import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const SECURE_TOKEN_KEY = 'ftf.sessionToken';
// Survives app deletion (Keychain default). Used to prefill SignInScreen
// for returning users, even after sign-out or token expiry.
const SECURE_LAST_USERNAME_KEY = 'ftf.lastUsername';
// Stable per-install anonymous id ('dev_' + UUID) for analytics + the
// pre-auth funnel (analytics-platform). Lives here (the lowest-level api
// module) so events.ts and flags.ts share ONE mint source without an import
// cycle through the flag store.
const SECURE_DEVICE_ID_KEY = 'ftf.deviceId';

// ── Client-info headers ─────────────────────────────────────────────────
// The backend's before_request middleware reads these on every authed call
// to maintain users.last_device_type/os/app_version + the snapshot fields
// on every user_events row. X-User-TZ powers local-day-aware streak math.
//
// Computed once per app launch — Device + Constants values don't change
// without a re-launch, and re-reading the IANA TZ on every request is
// wasted work.
//
//   X-Device      'iphone' | 'ipad' | 'macos' | 'web' (per backend taxonomy)
//   X-OS-Version  e.g. '17.4'
//   X-App-Version e.g. '1.2.3'
//   X-User-TZ     IANA name e.g. 'America/New_York'
function _resolveDeviceLabel(): string {
  if (Platform.OS === 'ios') {
    // expo-device DeviceType: UNKNOWN=0, PHONE=1, TABLET=2, DESKTOP=3, TV=4
    if (Device.deviceType === Device.DeviceType.TABLET) return 'ipad';
    if (Device.deviceType === Device.DeviceType.DESKTOP) return 'macos';
    return 'iphone';
  }
  if (Platform.OS === 'android') return 'android';
  if (Platform.OS === 'web') return 'web';
  return Platform.OS;
}

const _CLIENT_HEADERS: Record<string, string> = (() => {
  const h: Record<string, string> = {
    'X-Device': _resolveDeviceLabel(),
  };
  if (Device.osVersion) h['X-OS-Version'] = Device.osVersion;
  const appVersion = Constants.expoConfig?.version;
  if (appVersion) h['X-App-Version'] = appVersion;
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz) h['X-User-TZ'] = tz;
  } catch {
    /* Hermes without full ICU — skip; backend treats missing TZ as UTC */
  }
  return h;
})();

export function getBaseUrl(): string {
  // Expo puts values from app.json's `extra` here at build time; fall back
  // to the Render URL so a raw fetch still works during dev without extras.
  // Also exported for share/invite links — the backend origin serves the
  // web app at `/`, so invite URLs reuse it.
  const configured =
    (Constants.expoConfig?.extra as any)?.apiBaseUrl ??
    (Constants.manifest2?.extra as any)?.apiBaseUrl;
  return configured || 'https://fantasy-trade-finder.onrender.com';
}

/** Session-token helpers — call from auth screens only. */
export async function getSessionToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(SECURE_TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function setSessionToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(SECURE_TOKEN_KEY, token);
}

export async function clearSessionToken(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(SECURE_TOKEN_KEY);
  } catch {
    /* already gone */
  }
}

export async function getLastUsername(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(SECURE_LAST_USERNAME_KEY);
  } catch {
    return null;
  }
}

/** Stable per-install anonymous id ('dev_' + UUID), minted once and kept in
 *  SecureStore (Keychain — survives reinstall). Single-flight; never rejects.
 *  Canonical source for both events.ts and the flag fetch. */
let _deviceIdPromise: Promise<string> | null = null;
export function getDeviceId(): Promise<string> {
  if (!_deviceIdPromise) {
    _deviceIdPromise = (async () => {
      try {
        const stored = await SecureStore.getItemAsync(SECURE_DEVICE_ID_KEY);
        if (stored) return stored;
      } catch {
        /* fall through to mint */
      }
      // crypto.getRandomValues is present in the Expo runtime; a device-local
      // timestamp+counter fallback avoids Math.random for this id.
      let uuid: string;
      const c = (globalThis as { crypto?: Crypto }).crypto;
      if (c?.getRandomValues) {
        const b = new Uint8Array(16);
        c.getRandomValues(b);
        b[6] = (b[6] & 0x0f) | 0x40;
        b[8] = (b[8] & 0x3f) | 0x80;
        const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
        uuid = `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
      } else {
        uuid = `loc-${Date.now().toString(36)}-${Math.floor(performance?.now?.() ?? 0).toString(36)}`;
      }
      const fresh = `dev_${uuid}`;
      try {
        await SecureStore.setItemAsync(SECURE_DEVICE_ID_KEY, fresh);
      } catch {
        /* non-fatal — id lives for this launch only */
      }
      return fresh;
    })();
  }
  return _deviceIdPromise;
}

export async function setLastUsername(username: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(SECURE_LAST_USERNAME_KEY, username);
  } catch {
    /* non-fatal */
  }
}

export class ApiError extends Error {
  // isTimeout marks an error produced by the internal request deadline (FR-4),
  // so UI layers can surface "Server is waking up — retry." instead of a
  // generic network failure. A caller-supplied signal abort (e.g. TanStack
  // Query cancellation) is NOT a timeout and never sets this.
  constructor(
    public status: number,
    public body: unknown,
    message?: string,
    public isTimeout = false,
  ) {
    super(message || `HTTP ${status}`);
    this.name = 'ApiError';
  }
  get isUnauthorized() {
    return this.status === 401;
  }
  /** Account-auth read/write gate: this session is unverified while a
   *  verified controller exists for the user_id (or enforcement is on).
   *  The fix is always the same — verify via SleeperConnect. */
  get isVerificationRequired() {
    return (
      this.status === 403 &&
      typeof this.body === 'object' &&
      this.body !== null &&
      (this.body as any).error === 'verification_required'
    );
  }
}

// ── verification_required listener (account-auth P2.5) ─────────────────────
// The backend read gate 403s board-content reads from unverified sessions
// once a verified controller exists for the user_id. One central hook — the
// session store registers a handler that flips useSession.verification so
// the existing VerifyAccountBanner appears, instead of every screen mapping
// the error itself. Registered as a callback (not a direct import) to keep
// this module free of state dependencies (useSession already imports us).
let _onVerificationRequired: (() => void) | null = null;
export function setOnVerificationRequired(fn: (() => void) | null): void {
  _onVerificationRequired = fn;
}

// ── session-expired listener (teardown 06-03, flag auth.persistent_sessions) ──
// Fired when a 401 just cleared the stored token (the "this session is dead"
// moment). The session store registers a handler that routes ACCOUNT-ONLY
// users to SignIn for an Apple re-auth — they have no Sleeper username for
// the silent re-mint, so without this they'd be stranded on failing screens.
// Same callback-not-import pattern as setOnVerificationRequired above.
let _onSessionExpired: (() => void) | null = null;
export function setOnSessionExpired(fn: (() => void) | null): void {
  _onSessionExpired = fn;
}

// ── Request deadlines (INIT-12 Wave 1, FR-1/FR-2) ───────────────────────────
// Default cap for any request; the known-slow cold-start POSTs get a generous
// cap so a legitimately-slow-but-progressing session_init isn't aborted.
const DEFAULT_TIMEOUT_MS = 15_000;
const SLOW_TIMEOUT_MS = 30_000;
// Paths documented at 5–10 s on Render's free tier (auth.ts:98–99). Matched by
// suffix so the base-URL prefix doesn't matter.
const SLOW_POST_PATHS = ['/api/session/init', '/api/trades/generate'];

// ── GET-only retry (INIT-12b) ─────────────────────────────────────────────
// Retry only safe GETs on transient gateway / network errors. Paths that
// trigger long-lived server-side side-effects (session init, generation,
// ranking submissions) are excluded so a retry doesn't double-book work.
const NO_RETRY_PATHS = [
  '/api/session/init',
  '/api/trades/generate',
  '/api/rank3',
  '/api/tiers',
  '/api/trades/swipe',
];
const RETRY_STATUSES = new Set([502, 503, 504]);
const MAX_RETRIES = 2;
const RETRY_BASE_MS = 400;
const RETRY_FACTOR = 3; // 400ms → 1200ms

// User-facing copy for a deadline abort (FR-4).
const TIMEOUT_MESSAGE = 'Server is waking up — please retry.';

function timeoutForRequest(path: string, method: string): number {
  if (method === 'POST' && SLOW_POST_PATHS.some((p) => path.includes(p))) {
    return SLOW_TIMEOUT_MS;
  }
  return DEFAULT_TIMEOUT_MS;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
  // If true, don't attach the session token. Used for the initial auth call.
  skipAuth?: boolean;
  // Abort signal for TanStack Query cancellation.
  signal?: AbortSignal;
}

// ── Universal API-failure observability (tracking plan addendum 2026-07-19) ──
// Every failed apiRequest emits ONE api_request_failed event with a
// cardinality-bounded route. Exclusions: the ingest endpoint itself
// (recursion) and caller aborts (navigation cancellations aren't failures).
// Deadline timeouts ARE failures (status 0, timeout:true).
function _normalizeRoute(path: string): string {
  let p = path.startsWith('http') ? path.replace(/^https?:\/\/[^/]+/, '') : path;
  p = p.split('?')[0];
  // Digit runs (sleeper ids, league ids, years in paths) → ':id' so the
  // route dimension stays enumerable and identifier-free.
  p = p.replace(/\d{4,}/g, ':id');
  return p.slice(0, 80);
}

function _reportApiFailure(path: string, method: string, err: unknown, ms: number): void {
  try {
    if (path.includes('/api/events')) return;
    if ((err as any)?.name === 'AbortError') return;
    const isApi = err instanceof ApiError;
    // Lazy require — events.ts imports getDeviceId from this module, so a
    // top-level import here would be a cycle. track() self-gates on the
    // analytics.client_events flag and never throws.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { track } = require('./events') as typeof import('./events');
    track('api_request_failed', {
      route: _normalizeRoute(path),
      method,
      status: isApi ? (err as ApiError).status : 0,
      ms,
      timeout: isApi ? (err as ApiError).isTimeout : false,
    });
  } catch {
    /* observability must never mask or alter the original error */
  }
}

export async function apiRequest<T = unknown>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const startedAt = Date.now();
  try {
    return await _apiRequestInner<T>(path, opts);
  } catch (err) {
    _reportApiFailure(path, opts.method || 'GET', err, Date.now() - startedAt);
    throw err;
  }
}

async function _apiRequestInner<T = unknown>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const base = getBaseUrl();
  const url = path.startsWith('http') ? path : `${base}${path}`;
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ..._CLIENT_HEADERS,
    ...(opts.headers || {}),
  };
  if (opts.body !== undefined) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }
  if (!opts.skipAuth) {
    const tok = await getSessionToken();
    if (tok) headers['X-Session-Token'] = tok;
  }

  const method = opts.method || 'GET';

  // ── Timeout (INIT-12 Wave 1, FR-1/2/3) ────────────────────────────────────
  // Compose an internal deadline controller with the caller's signal so that
  // either source can abort the request — whichever fires first wins. We track
  // *which* fired so a deadline abort can be reported as a typed timeout while
  // a caller cancellation (e.g. TanStack Query navigation) is left to bubble as
  // a plain AbortError. AbortSignal.any/.timeout aren't reliably present in the
  // Hermes/RN runtime, so the composition is done by hand.
  const timeoutController = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    timeoutController.abort();
  }, timeoutForRequest(path, method));

  const callerSignal = opts.signal;
  const onCallerAbort = () => timeoutController.abort();
  if (callerSignal) {
    if (callerSignal.aborted) {
      timeoutController.abort();
    } else {
      callerSignal.addEventListener('abort', onCallerAbort);
    }
  }

  // ── Retry eligibility (INIT-12b) ──────────────────────────────────────────
  // Only GET requests on non-side-effecting paths are candidates for retry.
  // We check caller abort + timeout abort during any retry delay so the user's
  // navigation or the deadline can still cancel cleanly mid-backoff.
  const canRetry =
    method === 'GET' &&
    !NO_RETRY_PATHS.some((p) => path.includes(p));

  let attempt = 0;
  let lastError: unknown;

  const fetchOnce = async (): Promise<Response> => {
    try {
      return await fetch(url, {
        method,
        headers,
        body:
          opts.body !== undefined
            ? typeof opts.body === 'string'
              ? opts.body
              : JSON.stringify(opts.body)
            : undefined,
        signal: timeoutController.signal,
      });
    } catch (err: any) {
      // Our deadline fired — and it wasn't the caller cancelling. Surface a
      // typed timeout the UI can act on. If the caller's own signal aborted,
      // let the original AbortError propagate untouched (not a timeout — FR-4).
      if (timedOut && !(callerSignal && callerSignal.aborted)) {
        throw new ApiError(0, null, TIMEOUT_MESSAGE, true);
      }
      throw err;
    }
  };

  try {
    // Retry loop — executes at least once (attempt 0), then up to MAX_RETRIES
    // additional times for eligible requests that hit transient errors.
    while (true) {
      let res: Response;
      let networkError = false;

      try {
        res = await fetchOnce();
      } catch (err: any) {
        // Don't retry timeouts or caller cancellations — those are intentional.
        const isTimeout = err instanceof ApiError && err.isTimeout;
        const isCallerAbort = callerSignal && callerSignal.aborted;
        if (isTimeout || isCallerAbort || !canRetry || attempt >= MAX_RETRIES) {
          throw err;
        }
        lastError = err;
        networkError = true;
        res = undefined as unknown as Response; // satisfies TS; networkError=true guards usage
      }

      if (!networkError) {
        // Gateway errors — retry on eligible status codes.
        if (canRetry && RETRY_STATUSES.has(res!.status) && attempt < MAX_RETRIES) {
          lastError = new ApiError(res!.status, null, `HTTP ${res!.status}`);
        } else {
          // Successful response or non-retryable error — process normally.
          const text = await res!.text();
          let parsed: any = null;
          if (text) {
            try {
              parsed = JSON.parse(text);
            } catch {
              parsed = text;
            }
          }

          if (!res!.ok) {
            // 401 = session expired. Caller should redirect to sign-in.
            // FB-45 guard: only clear when the token THIS request sent is
            // still the stored one — a background revalidateSession() may
            // have minted a fresh token while this request was in flight,
            // and a stale 401 must not destroy it.
            if (res!.status === 401) {
              const sent = headers['X-Session-Token'];
              const current = await getSessionToken();
              if (sent && current && sent === current) {
                await clearSessionToken();
                // The stored token is definitively dead — let the session
                // store decide whether to route to re-auth (account-only,
                // flag-gated inside the handler).
                if (_onSessionExpired) {
                  try {
                    _onSessionExpired();
                  } catch {
                    /* listener errors must never mask the API error */
                  }
                }
              }
            }
            const msg = (parsed && (parsed.message || parsed.error)) || `HTTP ${res!.status}`;
            const apiErr = new ApiError(res!.status, parsed, msg);
            // Central read-gate signal — see setOnVerificationRequired above.
            if (apiErr.isVerificationRequired && _onVerificationRequired) {
              try {
                _onVerificationRequired();
              } catch {
                /* listener errors must never mask the API error */
              }
            }
            throw apiErr;
          }

          return parsed as T;
        }
      }

      // Back off before the next attempt. Jitter ±20% to spread retried
      // requests across the backoff window and avoid thundering-herd.
      attempt += 1;
      const baseMs = attempt === 1 ? RETRY_BASE_MS : RETRY_BASE_MS * RETRY_FACTOR;
      const jitter = baseMs * 0.2 * (Math.random() * 2 - 1);
      const delay = Math.round(baseMs + jitter);

      await new Promise<void>((resolve, reject) => {
        const t = setTimeout(resolve, delay);
        // If the timeout fires or the caller aborts during the backoff delay,
        // cancel the wait and propagate the abort immediately.
        const onAbortDuringDelay = () => {
          clearTimeout(t);
          reject(
            timedOut && !(callerSignal && callerSignal.aborted)
              ? new ApiError(0, null, TIMEOUT_MESSAGE, true)
              : new DOMException('Aborted', 'AbortError'),
          );
        };
        timeoutController.signal.addEventListener('abort', onAbortDuringDelay, { once: true });
      });
    }
  } finally {
    clearTimeout(timer);
    if (callerSignal) callerSignal.removeEventListener('abort', onCallerAbort);
  }
}

// Convenience helpers so screen code reads naturally
export const api = {
  get: <T = unknown>(path: string, opts?: RequestOptions) =>
    apiRequest<T>(path, { ...opts, method: 'GET' }),
  post: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiRequest<T>(path, { ...opts, method: 'POST', body }),
  put: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiRequest<T>(path, { ...opts, method: 'PUT', body }),
};
