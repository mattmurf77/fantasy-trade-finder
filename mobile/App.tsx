import React, { useEffect, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClientProvider } from '@tanstack/react-query';
import * as Linking from 'expo-linking';
import RootNav from './src/navigation/RootNav';
import { useSession } from './src/state/useSession';
import { useFeatureFlags } from './src/state/useFeatureFlags';
import { useFeedback } from './src/state/useFeedback';
import { queryClient } from './src/state/queryClient';
import { initSentry, wrap as sentryWrap } from './src/observability/sentry';
import { getTierConfig } from './src/api/rankings';
import { warmPlayerCache } from './src/api/sleeper';
import { setTierConfigCache } from './src/utils/tierBands';
import { handleDeepLink } from './src/utils/deepLinks';

// Initialize observability as early as possible so even crashes during
// bootstrap are captured. No-ops cleanly when no DSN is configured.
initSentry();

function App() {
  const [booted, setBooted] = useState(false);
  const bootstrap = useSession((s) => s.bootstrap);
  const loadFlags = useFeatureFlags((s) => s.load);

  useEffect(() => {
    // Restore persisted session + feature flags + tier config in parallel.
    // Tier config is the (format, position, tier) → {min, max} table that
    // backs autoBucket / tierForElo. Without it the app falls back to
    // hardcoded thresholds which can drift from the backend; the live
    // fetch keeps the two in sync. Treated as best-effort — a network
    // failure here just means we ride on the seeded fallback bands.
    const fetchTierConfig = async () => {
      try {
        const cfg = await getTierConfig();
        setTierConfigCache(cfg);
      } catch {
        // Fallback bands stay in effect; not worth failing the boot.
      }
    };
    // Fire-and-forget warm ping. On a sleeping Render dyno the cold-start
    // takes 30–60s; kicking it off during splash means the first user
    // action lands on a warm server. Errors are silent — boot must not
    // block on a network failure.
    Promise.all([
      bootstrap(),
      loadFlags(),
      fetchTierConfig(),
      warmPlayerCache().catch(() => {}),
    ])
      .catch(() => { /* bootstrap is best-effort */ })
      .finally(() => setBooted(true));
  }, [bootstrap, loadFlags]);

  // Deep-link handling. Two surfaces:
  //   • ?ref=<username>  — referral attribution. Captured into useSession's
  //     invitedBy and forwarded on the next /api/session/init.
  //   • /u/<username>    — public profile route (react-navigation Linking
  //     config also handles this; the explicit listener here covers the
  //     cold-start case where the navigator hasn't mounted yet).
  // Both the initial URL (cold start) and subsequent URL events (warm
  // start via tap or Universal Link) flow through the same handler.
  useEffect(() => {
    let canceled = false;
    Linking.getInitialURL().then((url) => {
      if (canceled || !url) return;
      handleDeepLink(url);
    });
    const sub = Linking.addEventListener('url', ({ url }) => {
      handleDeepLink(url);
    });
    return () => {
      canceled = true;
      sub.remove();
    };
  }, []);

  // Flush any queued / failed feedback notes whenever the app returns to
  // the foreground. retrySync() is a no-op when nothing is unsynced, so
  // this is safe to fire on every active transition (no rate-limiting
  // beyond that needed for now).
  useEffect(() => {
    const onChange = (next: AppStateStatus) => {
      if (next === 'active') {
        void useFeedback.getState().retrySync();
      }
    };
    const sub = AppState.addEventListener('change', onChange);
    return () => {
      sub.remove();
    };
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <RootNav booted={booted} />
          <StatusBar style="light" />
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

// sentryWrap installs the Sentry ErrorBoundary + touch event tracker
// around the root. When Sentry isn't initialized it returns the same
// component unchanged — safe to call unconditionally.
export default sentryWrap(App);
