import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { findMyRoster, getLeagueRosters } from '../api/sleeper';
import { getLeaguePicks, type OwnedPick } from '../api/league';

// The caller's roster as roster-first setup counts it (prd §3.1, §4.1):
// rostered player ids from the league rosters (owner OR co-owner, via
// `findMyRoster` — the same predicate the Trade DNA sheet's roster picker
// uses) plus owned pick ids from `GET /api/league/picks`.
//
// Both reads share the cache keys every other consumer uses —
// `['league-rosters', id]` is seeded by session init, `['league-picks', id]`
// is TradesScreen's — so the TradesHome card and the auto-push cost nothing
// on a warm session. A picks failure (ESPN has no ownership, a 409 during
// session init) degrades to "no picks", never to "no roster".

export interface MyRosterAssets {
  /** Rosters answered (picks may still be loading). */
  rostersReady: boolean;
  rostersError: boolean;
  /** Picks settled — answered, failed, or not applicable. */
  picksSettled: boolean;
  playerIds: string[];
  picks: OwnedPick[];
  /** Players then picks; what the device store snapshots as `seenAssetIds`. */
  assetIds: string[];
  refetch: () => void;
}

export function useMyRosterAssets(
  leagueId: string | null,
  userId: string,
  enabled: boolean,
): MyRosterAssets {
  const on = enabled && !!leagueId && leagueId !== 'league_demo';
  const rostersQuery = useQuery({
    queryKey: ['league-rosters', leagueId],
    queryFn: () => getLeagueRosters(leagueId!),
    enabled: on,
    staleTime: 5 * 60_000,
  });
  const picksQuery = useQuery({
    queryKey: ['league-picks', leagueId],
    queryFn: () => getLeaguePicks(leagueId!),
    enabled: on,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const playerIds = useMemo(
    () => (findMyRoster(rostersQuery.data, userId)?.players ?? []).map(String),
    [rostersQuery.data, userId],
  );
  const picks = useMemo(
    () => (picksQuery.data?.picks_supported === false ? [] : picksQuery.data?.my_picks ?? []),
    [picksQuery.data],
  );
  const assetIds = useMemo(
    () => [...playerIds, ...picks.map((p) => p.pick_id)],
    [playerIds, picks],
  );

  return {
    rostersReady: rostersQuery.isSuccess,
    rostersError: rostersQuery.isError,
    picksSettled: picksQuery.isSuccess || picksQuery.isError,
    playerIds,
    picks,
    assetIds,
    refetch: () => {
      void rostersQuery.refetch();
      void picksQuery.refetch();
    },
  };
}
