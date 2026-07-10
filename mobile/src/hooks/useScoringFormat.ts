// Scoring-format selection (feedback #80 / #89).
//
// Two hooks, one contract:
//
//   • useLeagueFormatDefault() — mounted ONCE (RootNav). Fetches the
//     selected league's detected scoring format from the backend
//     (/api/league/format-stats → default_scoring, auto-detected from
//     Sleeper roster_positions / scoring_settings) and applies it as the
//     app's active format whenever the selected league changes. Never
//     stomps an explicit in-session toggle choice (useSession.formatExplicit).
//
//   • useScoringFormat() — consumed by the SF/1QB toggle on the Tiers and
//     Trios screens. Returns the current format + a setFormat that records
//     the choice as explicit.
//
// Both paths funnel through applyFormat(), which owns the ordering that
// keeps client and server in agreement:
//   1. POST /api/scoring/switch — flip the SERVER session first. Most
//      format-scoped endpoints (getRankings, getProgress, getNextTrio…)
//      send no X-Scoring-Format header and read the session's format, so
//      the server must flip BEFORE any refetch fires.
//   2. Persist the local mirrors (AsyncStorage cache + zustand store).
//      The store update changes every ['…', activeFormat, …] query key,
//      which triggers the refetches.
//   3. Invalidate format-scoped caches whose keys DON'T carry the format.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useSession } from '../state/useSession';
import { setActiveScoringFormat, switchScoringFormat } from '../api/rankings';
import { getLeagueFormatStats } from '../api/league';
import type { ScoringFormat } from '../shared/types';

// Applications are serialized through a module-level chain so an in-flight
// league-default application and an explicit toggle tap can't interleave
// their server switch + local writes (last-write-wins on the server would
// otherwise let a slow league-default POST overwrite a fresh user choice).
// A queued NON-explicit application re-checks formatExplicit when it runs
// and skips itself if the user chose in the meantime.
let _applyChain: Promise<void> = Promise.resolve();

function applyFormat(
  qc: QueryClient,
  fmt: ScoringFormat,
  explicit: boolean,
): Promise<void> {
  const run = _applyChain.then(async () => {
    if (!explicit && useSession.getState().formatExplicit) return;
    await doApplyFormat(qc, fmt, explicit);
  });
  // Keep the chain alive past failures; callers still see the rejection.
  _applyChain = run.catch(() => {});
  return run;
}

async function doApplyFormat(
  qc: QueryClient,
  fmt: ScoringFormat,
  explicit: boolean,
): Promise<void> {
  await switchScoringFormat(fmt);      // server session first (see header note)
  await setActiveScoringFormat(fmt);   // AsyncStorage + module cache (formatHeader())
  useSession.getState().setActiveFormat(fmt, { explicit });
  // Keys that embed activeFormat (rankings/progress/streak) refetch via the
  // key change above — but they can also hold payloads served under the
  // OTHER session format (e.g. a server-side format carry-over across a
  // league switch), so sweep them too. The rest are format-scoped
  // server-side without a format segment in their keys.
  qc.invalidateQueries({ queryKey: ['rankings'] });
  qc.invalidateQueries({ queryKey: ['progress'] });
  qc.invalidateQueries({ queryKey: ['streak'] });
  qc.invalidateQueries({ queryKey: ['trio'] });
  qc.invalidateQueries({ queryKey: ['tiers-status'] });
  qc.invalidateQueries({ queryKey: ['trends'] });
}

/** League-driven default (mount once, in RootNav).
 *
 *  Applies the selected league's detected format whenever the league
 *  changes — including re-syncing the server session, whose session_init
 *  carries the PREVIOUS league's active_format over (backend priority:
 *  body > session carry-over > league default). Skipped while the user
 *  holds an explicit in-session toggle choice for this league. */
export function useLeagueFormatDefault(): void {
  const qc = useQueryClient();
  const leagueId       = useSession((s) => s.league?.league_id ?? null);
  const hasToken       = useSession((s) => s.hasToken);
  const formatExplicit = useSession((s) => s.formatExplicit);

  const statsQuery = useQuery({
    queryKey: ['league-format', leagueId],
    queryFn: () => getLeagueFormatStats(leagueId!),
    enabled: !!leagueId && hasToken,
    staleTime: 5 * 60_000,
    retry: 2,
  });
  const leagueDefault = statsQuery.data?.default_scoring;

  // Apply at most once per (league, detected format) so a failed switch
  // can't hot-loop, while a league A → B → A round trip re-applies (the
  // server session carried B's format back into A).
  const appliedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!leagueId || !leagueDefault) return;
    if (leagueDefault !== '1qb_ppr' && leagueDefault !== 'sf_tep') return;
    if (formatExplicit) return;                 // user's toggle choice wins
    const key = `${leagueId}:${leagueDefault}`;
    if (appliedKeyRef.current === key) return;
    appliedKeyRef.current = key;
    applyFormat(qc, leagueDefault, false).catch(() => {
      // Non-fatal: the server keeps whatever format the session already
      // had, and the user can still flip via the toggle. Allow a retry on
      // the next league change by clearing the guard.
      appliedKeyRef.current = null;
    });
  }, [leagueId, leagueDefault, formatExplicit, qc]);
}

/** Current format + explicit setter for the SF/1QB toggle (Tiers, Trios). */
export function useScoringFormat(): {
  format: ScoringFormat | null;
  /** Resolves true on success; false when the server switch failed
   *  (callers surface a toast — local state is left untouched on failure). */
  setFormat: (fmt: ScoringFormat) => Promise<boolean>;
  switching: boolean;
} {
  const qc = useQueryClient();
  const format = useSession((s) => s.activeFormat);
  const [switching, setSwitching] = useState(false);

  const setFormat = useCallback(
    async (fmt: ScoringFormat): Promise<boolean> => {
      if (switching) return false;
      if (fmt === useSession.getState().activeFormat) return true;
      setSwitching(true);
      try {
        await applyFormat(qc, fmt, true);
        return true;
      } catch {
        return false;
      } finally {
        setSwitching(false);
      }
    },
    [qc, switching],
  );

  return { format, setFormat, switching };
}
