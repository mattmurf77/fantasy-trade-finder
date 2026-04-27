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
  constructor(
    public status: number,
    public body: unknown,
    message?: string,
  ) {
    super(message || `HTTP ${status}`);
    this.name = 'ApiError';
  }
  get isUnauthorized() {
    return this.status === 401;
  }
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

  const res = await fetch(url, {
    method: opts.method || 'GET',
    headers,
    body:
      opts.body !== undefined
        ? typeof opts.body === 'string'
          ? opts.body
          : JSON.stringify(opts.body)
        : undefined,
    signal: opts.signal,
  });

  const text = await res.text();
  let parsed: any = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!res.ok) {
    // 401 = session expired. Caller should redirect to sign-in.
    if (res.status === 401) {
      await clearSessionToken();
    }
    const msg = (parsed && (parsed.message || parsed.error)) || `HTTP ${res.status}`;
    throw new ApiError(res.status, parsed, msg);
  }

  return parsed as T;
}

// Convenience helpers so screen code reads naturally
export const api = {
  get: <T = unknown>(path: string, opts?: RequestOptions) =>
    apiRequest<T>(path, { ...opts, method: 'GET' }),
  post: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiRequest<T>(path, { ...opts, method: 'POST', body }),
};
