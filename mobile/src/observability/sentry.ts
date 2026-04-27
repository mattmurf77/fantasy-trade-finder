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
