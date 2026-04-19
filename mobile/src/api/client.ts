// apiClient — thin fetch wrapper. Mirrors the web's `apiFetch` in web/js/app.js:
//   - auto-attaches X-Session-Token (stored in expo-secure-store)
//   - JSON by default
//   - 401 → clears session and surfaces a recognisable error for the UI
//
// One place owns the base URL and the token getter so screen-level code
// never has to touch fetch directly.

import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

const SECURE_TOKEN_KEY = 'ftf.sessionToken';

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
