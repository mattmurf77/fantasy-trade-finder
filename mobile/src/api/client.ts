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

function getBaseUrl(): string {
  // Expo puts values from app.json's `extra` here at build time; fall back
  // to the Render URL so a raw fetch still works during dev without extras.
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

export async function apiRequest<T = unknown>(
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
            if (res!.status === 401) {
              await clearSessionToken();
            }
            const msg = (parsed && (parsed.message || parsed.error)) || `HTTP ${res!.status}`;
            throw new ApiError(res!.status, parsed, msg);
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
