import { QueryClient } from '@tanstack/react-query';
import type { SessionInitSeed } from '../api/auth';

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
//
// `refetchOnReconnect: true` is LIVE as of the S7 PRD-04 NetInfo bridge:
// App.tsx wires onlineManager to @react-native-community/netinfo, so
// active queries revalidate when connectivity returns.
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

// Session init already fetches this league's Sleeper rosters + users to build
// the /api/session/init payload, then dropped them — and it runs on every cold
// start and foreground resume (useSession.revalidateSession), on league switch
// and on connect. Seconds later TradesScreen, InLeagueCalculator, TradeDnaSheet
// and TradeFinderHubScreen re-request the identical two endpoints. Handing the
// already-fetched arrays to the cache here removes that second round-trip.
//
// The api layer can't reach the QueryClient (api/* imports no state), so the
// builders hand back a `SessionInitSeed` and the seeding happens here.
//
// Why it holds: all four consumers carry `staleTime: 5 * 60_000`, so their
// `refetchOnMount` (true by default) sees fresh data and doesn't refetch.
// `setQueryData` stamps `dataUpdatedAt` at now (TanStack v5), which starts
// that window at the moment of the seed.
//
// Keys include `leagueId`, so a league switch needs no clearing — the new
// league is a different key. ESPN / MFL / Fleaflicker leagues never fetch
// these, so the seed comes back empty and nothing is written.
export function seedLeagueSessionCaches(
  leagueId: string | null | undefined,
  seed: SessionInitSeed | null | undefined,
): void {
  if (!leagueId || !seed) return;
  if (Array.isArray(seed.rosters)) {
    queryClient.setQueryData(['league-rosters', leagueId], seed.rosters);
  }
  if (Array.isArray(seed.leagueUsers)) {
    queryClient.setQueryData(['league-users', leagueId], seed.leagueUsers);
  }
}
