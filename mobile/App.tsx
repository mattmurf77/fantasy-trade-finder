import React, { useEffect, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { focusManager } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import AsyncStorage from '@react-native-async-storage/async-storage';
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

// INIT-07 — AsyncStorage persister for cold-cache restoration. Queries
// whose first key segment is in the allow-list below are dehydrated to
// AsyncStorage on every successful fetch and rehydrated on the next cold
// start — so the app shows cached data immediately while the network
// round-trip is in flight. maxAge = 30 minutes keeps stale data from
// being loaded hours later when player values may have shifted.
const asyncStoragePersister = createAsyncStoragePersister({ storage: AsyncStorage });
const PERSIST_KEYS = new Set(['rankings', 'progress', 'matches', 'tiers-status', 'liked-trades']);

function App() {
  const [booted, setBooted] = useState(false);
  const bootstrap = useSession((s) => s.bootstrap);
  const loadCachedFlags = useFeatureFlags((s) => s.loadCachedFlags);
  const revalidateFlags = useFeatureFlags((s) => s.revalidateFlags);

  useEffect(() => {
    // INIT-01 — gate the splash on LOCAL-state legs only.
    //
    // Routing (SignIn / LeaguePicker / Main) depends solely on what
    // bootstrap() restores from AsyncStorage/SecureStore plus the cached
    // feature-flag map. Both are local IO and resolve in milliseconds, so
    // the first screen renders without waiting on any network round-trip.
    Promise.all([bootstrap(), loadCachedFlags()])
      .catch(() => { /* both legs are best-effort */ })
      .finally(() => setBooted(true));

    // Detached network legs — fire-and-forget. None of these gate the
    // splash; the app already tolerates their failure via fallbacks.
    //
    // Tier config is the (format, position, tier) → {min, max} table that
    // backs autoBucket / tierForElo. Without it the app rides on the
    // seeded fallback bands; the live fetch keeps it in sync.
    void getTierConfig()
      .then(setTierConfigCache)
      .catch(() => {});
    // Network revalidate of the feature flags. Flag-gated UI settles to
    // cached values until this resolves, then updates in place.
    void revalidateFlags().catch(() => {});
    // Warm ping. On a sleeping Render dyno the cold-start takes 30–60s;
    // kicking it off during boot means the first user action lands on a
    // warm server. Errors are silent — boot must not block on it.
    void warmPlayerCache().catch(() => {});
  }, [bootstrap, loadCachedFlags, revalidateFlags]);

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

  // AppState → app-wide foreground signals. Two consumers ride this one
  // listener:
  //   1. Feedback sync — flush any queued / failed feedback notes on
  //      return to foreground. retrySync() is a no-op when nothing is
  //      unsynced, so it's safe on every active transition.
  //   2. INIT-05 — bridge TanStack Query's focusManager to AppState so
  //      `refetchOnWindowFocus: true` queries (e.g. ['progress']) actually
  //      revalidate on resume. We register focusManager's event listener
  //      separately so it owns its own subscription lifecycle (and gets
  //      handleFocus once at startup), per the TanStack RN guidance.
  useEffect(() => {
    const onChange = (next: AppStateStatus) => {
      if (next === 'active') {
        void useFeedback.getState().retrySync();
      }
    };
    const sub = AppState.addEventListener('change', onChange);

    focusManager.setEventListener((handleFocus) => {
      const focusSub = AppState.addEventListener('change', (state) => {
        handleFocus(state === 'active');
      });
      return () => focusSub.remove();
    });

    // TODO(wave2): wire onlineManager when NetInfo is added
    // (@react-native-community/netinfo is not a dependency in Wave 1, so
    // refetchOnReconnect stays unbridged for now).

    return () => {
      sub.remove();
    };
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <PersistQueryClientProvider
          client={queryClient}
          persistOptions={{
            persister: asyncStoragePersister,
            // 30 min — matches the period where cached player ELOs are
            // still fresh enough to be useful on cold start.
            maxAge: 30 * 60 * 1000,
            dehydrateOptions: {
              shouldDehydrateQuery: (query) => {
                const key = query.queryKey[0];
                return PERSIST_KEYS.has(key as string);
              },
            },
          }}
        >
          <RootNav booted={booted} />
          <StatusBar style="light" />
        </PersistQueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

// sentryWrap installs the Sentry ErrorBoundary + touch event tracker
// around the root. When Sentry isn't initialized it returns the same
// component unchanged — safe to call unconditionally.
export default sentryWrap(App);
