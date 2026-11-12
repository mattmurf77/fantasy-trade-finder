import { useCallback, useMemo } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';

import { getRankings, splitRankings } from '../api/rankings';
import { getTradeValues } from '../api/calc';
import { useSession } from '../state/useSession';
import { playerSection, SETUP_POSITIONS } from '../utils/rosterSetup';
import type { Position, RankedPlayer, ScoringFormat } from '../shared/types';

// The reads that decide which section roster setup lists a player under:
// the caller's own board per position (the SAME unscoped keys Quick Rank
// reads, so a warm cache is free and a save in setup invalidates them both)
// and the consensus values pool (`['calc-values', fmt]`, shared with the
// calculator and the deck). Used by RosterSetupScreen, which lists the
// players, and by RosterSetupEntryCard, which counts new ones: both apply
// `utils/rosterSetup.playerSection` to the same data, so the card never
// counts a player the screen cannot list (a kicker, a defense, an IDP player).

export function useSetupSections(enabled: boolean, boardStaleTime = 30_000) {
  const activeFormat = useSession((s) => s.activeFormat);
  const fmt: ScoringFormat = activeFormat || '1qb_ppr';
  const valuesQuery = useQuery({
    queryKey: ['calc-values', fmt],
    queryFn: ({ signal }) => getTradeValues(fmt, signal),
    enabled,
    staleTime: 5 * 60_000,
  });
  const boardQueries = useQueries({
    queries: SETUP_POSITIONS.map((p) => ({
      queryKey: ['rankings', activeFormat, p],
      queryFn: () => getRankings(p),
      enabled,
      staleTime: boardStaleTime,
    })),
  });
  const boardsSettled = boardQueries.every((q) => q.isSuccess || q.isError);
  const boardByPos = useMemo(() => {
    const out: Partial<Record<Position, Map<string, RankedPlayer>>> = {};
    SETUP_POSITIONS.forEach((p, i) => {
      const rows = splitRankings(boardQueries[i]?.data as any).rows as RankedPlayer[];
      out[p] = new Map(rows.map((r) => [String(r.id), r]));
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boardQueries.map((q) => q.dataUpdatedAt).join('|')]);
  const valuesById = useMemo(
    () => new Map((valuesQuery.data?.players ?? []).map((v) => [String(v.id), v])),
    [valuesQuery.data],
  );
  const sectionOf = useCallback(
    (id: string) => playerSection(id, boardByPos, valuesById.get(id)?.position),
    [boardByPos, valuesById],
  );
  return {
    fmt,
    valuesQuery,
    boardsSettled,
    boardByPos,
    valuesById,
    sectionOf,
    /** Both reads answered (a board error counts as settled, as on the screen). */
    settled: boardsSettled && (valuesQuery.isSuccess || valuesQuery.isError),
  };
}
