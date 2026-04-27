import React, { useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RootNav from './src/navigation/RootNav';
import { useSession } from './src/state/useSession';
import { useFeatureFlags } from './src/state/useFeatureFlags';
import { initSentry, wrap as sentryWrap } from './src/observability/sentry';

// Initialize observability as early as possible so even crashes during
// bootstrap are captured. No-ops cleanly when no DSN is configured.
initSentry();

// One QueryClient for the app lifetime. Defaults tuned for a consumer
// mobile app: retry once, keep data fresh for 30s, background-refresh
// on mount so reopening the app shows current info.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnReconnect: true,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});

function App() {
  const [booted, setBooted] = useState(false);
  const bootstrap = useSession((s) => s.bootstrap);
  const loadFlags = useFeatureFlags((s) => s.load);

  useEffect(() => {
    // Restore persisted session + feature flags in parallel.
    // Whichever resolves last flips booted=true so RootNav can render.
    Promise.all([bootstrap(), loadFlags()])
      .catch(() => { /* bootstrap is best-effort */ })
      .finally(() => setBooted(true));
  }, [bootstrap, loadFlags]);

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
