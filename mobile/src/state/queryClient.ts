import { QueryClient } from '@tanstack/react-query';

// Single QueryClient for the app lifetime. Shared between the
// QueryClientProvider in App.tsx (which makes it visible to every
// `useQuery` / `useMutation` hook) and non-React modules that need to
// invalidate caches imperatively (e.g. zustand stores like useSession
// that swap the active league outside any component tree).
//
// Defaults tuned for a consumer mobile app: retry once, keep data fresh
// for 30s, background-refresh on mount so reopening the app shows
// current info. `gcTime: 30min` (vs TanStack's 5min default) keeps
// cached query data around long enough that tab-switches and AppState
// suspensions don't silently nuke the cache — combined with
// `placeholderData: (prev) => prev` on screen-level queries, this gives
// "instant content, refetch silently" behavior across the tabs (Mobile
// review #M5).
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 30 * 60_000,
      retry: 1,
      refetchOnReconnect: true,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});
