import Constants from 'expo-constants';
import * as Sentry from '@sentry/react-native';

// Sentry init wrapper.
//
// Behavior is "off until configured": if no DSN is found in
// app.json's `extra.sentryDsn` (or the EXPO_PUBLIC_SENTRY_DSN env var),
// we skip init entirely. Every Sentry.* call elsewhere becomes a
// no-op — no errors reported, no spans recorded, zero overhead.
//
// To turn it on:
//   1. Create a Sentry project (React Native platform)
//   2. Paste the DSN into mobile/app.json → `expo.extra.sentryDsn`
//   3. (Optional, for symbolicated stacks) install
//      `@sentry/react-native/expo` plugin and supply SENTRY_AUTH_TOKEN
//      at build time so sourcemaps + native debug symbols upload
//
// `navigationIntegration` is exported so RootNav can register it once
// the NavigationContainer mounts — gives auto-tagged spans per screen.

export const navigationIntegration = Sentry.reactNavigationIntegration({
  enableTimeToInitialDisplay: true,
});

let _initialized = false;

// ── Credential-leak scrub (device-auth S0, LLD §5.2) ────────────────────────
//
// The device transport (release 1+) attaches a raw Sleeper JWT to outbound
// platform requests. Without these hooks, Sentry's default fetch/xhr
// instrumentation would capture that request's URL, headers, and body as
// breadcrumbs and event context — a credential-leak path into a third-party
// SaaS that does not exist today. This closes it BEFORE the transport that
// would open it ships. Verified against a real capture with tracing forced to
// 1.0 at the pre-send gate (LLD §6.6 item 3) — not here, where CI cannot see a
// live event.
//
// Hosts whose request breadcrumbs are dropped entirely. Kept local (not
// imported from the transport's compiled allowlist) so this file has no
// dependency on release-1 code and closes the exposure on its own schedule.
const _SCRUB_HOSTS = new Set<string>(['sleeper.com']);

function _hostname(url: unknown): string | null {
  if (typeof url !== 'string') return null;
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
}

/** Drop any fetch/xhr breadcrumb aimed at a credentialed host. */
export function scrubBreadcrumb(crumb: any): any | null {
  if (crumb && (crumb.category === 'fetch' || crumb.category === 'xhr')) {
    const h = _hostname(crumb.data?.url);
    if (h && _SCRUB_HOSTS.has(h)) return null;
  }
  return crumb;
}

/** Strip request headers and body from every event, unconditionally. */
export function scrubEvent(event: any): any {
  if (event?.request) {
    delete event.request.headers;
    delete event.request.data;
  }
  return event;
}

export function initSentry(): boolean {
  if (_initialized) return true;
  const dsn =
    (Constants.expoConfig?.extra as any)?.sentryDsn ||
    process.env.EXPO_PUBLIC_SENTRY_DSN ||
    '';
  if (!dsn) {
    // Logged once at startup so devs know the wiring exists but is dormant.
    // In dev this nudges someone to add a DSN; in prod it's harmless.
    if (__DEV__) {
      console.info('[sentry] no DSN configured — observability disabled');
    }
    return false;
  }
  Sentry.init({
    dsn,
    // High in dev so every interaction creates a trace; low in prod so
    // we don't burn the free quota. Errors are 100% sampled either way.
    tracesSampleRate: __DEV__ ? 1.0 : 0.2,
    // Tag every event with the app version so we can correlate spikes
    // with releases. Constants.expoConfig.version comes from app.json.
    release: Constants.expoConfig?.version,
    enableAutoPerformanceTracing: true,
    enableNativeFramesTracking: true,
    integrations: [navigationIntegration],
    // Don't send PII by default. Username + Sleeper user_id is set
    // explicitly via setUser() from useSession when the user signs in.
    sendDefaultPii: false,
    // Credential-leak scrub (LLD §5.2): drop request breadcrumbs to a
    // credentialed host, strip headers/body from every event, and never
    // inject a sentry-trace/baggage header into an outbound platform request.
    beforeBreadcrumb: scrubBreadcrumb,
    beforeSend: scrubEvent,
    tracePropagationTargets: [],
  });
  _initialized = true;
  return true;
}

// Re-export the bits screens actually use so call sites only import from
// this file — keeps the "no-op when off" guarantee centralized.
export const captureException = Sentry.captureException;
export const captureMessage   = Sentry.captureMessage;
export const setUser          = Sentry.setUser;
export const startSpan        = Sentry.startSpan;

// Sentry.wrap() returns the original component when init never ran, so
// it's safe to call unconditionally on the App root.
export const wrap = Sentry.wrap;
