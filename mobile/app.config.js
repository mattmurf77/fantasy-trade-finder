// Build-time env contract for the UI-test harness
// (docs/plans/mobile-testing/lld.md §2.4, prd.md R-01).
//
// Layers over app.json (passed in as `config`). With NO env set this must be
// byte-identical in effect to app.json alone — shipping builds are untouched.
//
//   FTF_API_BASE_URL  → extra.apiBaseUrl   (test builds point at local Flask)
//   FTF_ENV=test      → extra.sentryDsn null (Sentry.init short-circuits on a
//                       falsy DSN — mobile/src/observability/sentry.ts:33) and
//                       extra.testMode true (reserved; no runtime branch yet).
//
// NOTE: sentry.ts also reads EXPO_PUBLIC_SENTRY_DSN as a second DSN source —
// the test runner's preflight asserts that variable is unset in test builds.

export default ({ config }) => {
  const isTest = process.env.FTF_ENV === "test";
  return {
    ...config,
    extra: {
      ...config.extra,
      apiBaseUrl: process.env.FTF_API_BASE_URL ?? config.extra.apiBaseUrl,
      // "" not null: null survives expo-config serialization as {} (truthy!),
      // which would slip past sentry.ts's falsy-DSN guard. "" is falsy.
      sentryDsn: isTest ? "" : config.extra.sentryDsn,
      testMode: isTest,
    },
  };
};
