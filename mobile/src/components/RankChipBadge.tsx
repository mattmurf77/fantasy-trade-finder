import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { ink, chalk, ice, radii, fonts } from '../theme/chalkline';
import { getRankChip } from '../api/league';

// #14 — league-card rank chip: "#3 of 12", consensus basis, from the open
// GET /api/league/rank-chip read. Silent-fail: any error or missing data
// renders nothing (old servers, ESPN edge cases, network) — the chip is an
// enrichment, never a dependency. Ice text when the user is top-3.
export default function RankChipBadge({ leagueId }: { leagueId: string }) {
  const q = useQuery({
    queryKey: ['league-rank-chip', leagueId],
    queryFn: () => getRankChip(leagueId),
    enabled: !!leagueId && leagueId !== 'league_demo',
    staleTime: 5 * 60_000,
    retry: false,
  });
  const d = q.data;
  if (!d || !d.rank || !d.team_count) return null;
  const hot = d.rank <= 3;
  return (
    <View testID={`league.rank-chip.${leagueId}`} style={styles.chip}>
      <Text style={[styles.text, hot && styles.textHot]}>
        {`#${d.rank} of ${d.team_count}`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: 6,
    paddingVertical: 2,
    alignSelf: 'flex-start',
  },
  text: {
    fontFamily: fonts.data,
    fontSize: 10,
    letterSpacing: 0.4,
    color: chalk.dim,
  },
  textHot: { color: ice.base },
});
