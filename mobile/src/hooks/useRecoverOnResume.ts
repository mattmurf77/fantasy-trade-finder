import { useEffect, useRef } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import { useSession } from '../state/useSession';

/** Minimal slice of a TanStack Query result this hook needs. */
interface RecoverableQuery {
  isError: boolean;
  isFetching: boolean;
  refetch: () => unknown;
}

// #121/#125 — self-heal a query that failed during the app-resume
// session-revalidation race.
//
// Server sessions are in-memory and die on every deploy. On foreground
// resume (and cold launch), App.tsx fires useSession.revalidateSession()
// to mint a fresh token — but that handshake takes seconds, and any query
// that fires meanwhile still carries the orphaned token, 401s, and lands
// in error state. Queries with `staleTime: Infinity` (e.g. the anchor
// wizard's pool snapshot) then never recover: refetchOnWindowFocus is off
// app-wide, the screen stays mounted in its stack, and nothing invalidates
// them — the screen shows its error state forever.
//
// Two recovery legs, both no-ops unless the query is currently errored:
//   1. Session-restore: revalidateSession() ends with set({ hasToken: true }).
//      Zustand notifies subscribers on every set() even when the value is
//      unchanged, so this fires right after a fresh token lands — the
//      refetch then succeeds where the pre-revalidation attempt 401'd.
//   2. Foreground resume: covers non-auth failures (network blip while
//      backgrounded, server hiccup) where no token change ever fires.
export function useRecoverOnResume(query: RecoverableQuery): void {
  // Ref so the stable listeners below always see the latest query state
  // without re-subscribing every render.
  const q = useRef(query);
  q.current = query;

  useEffect(() => {
    const tryRecover = () => {
      if (q.current.isError && !q.current.isFetching) {
        void q.current.refetch();
      }
    };

    const unsubStore = useSession.subscribe((state) => {
      if (state.hasToken) tryRecover();
    });

    const appStateSub = AppState.addEventListener(
      'change',
      (next: AppStateStatus) => {
        if (next === 'active') tryRecover();
      },
    );

    return () => {
      unsubStore();
      appStateSub.remove();
    };
  }, []);
}
