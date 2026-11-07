import React, { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Button, Card, Text, TickLabel } from '../chalkline';
import { chalk, space } from '../../theme/chalkline';
import { getLeagueProjectionBatch } from '../../api/leagueProjections';
import { NO_LEAGUE_ID, useSession } from '../../state/useSession';
import { useFlag } from '../../state/useFeatureFlags';
import { homePlayoffBanner, type PlayoffTradeSide } from '../../utils/homePlayoffBanner';
import { SPLIT_POSITIONS, type SplitPos } from '../../utils/positionSplit';

interface Props {
  rosterId: number | null;
  onBuy?: (position: SplitPos) => void;
  onSell?: (position: SplitPos) => void;
  onDetails: () => void;
}

const POSITION_TEST_IDS: Record<SplitPos, string> = {
  QB: 'home.playoff.position.QB', RB: 'home.playoff.position.RB',
  WR: 'home.playoff.position.WR', TE: 'home.playoff.position.TE',
};

/** Same saved weekly result as Standings; no view-triggered calculation. */
export default function HomePlayoffBanner({ rosterId, onBuy, onSell, onDetails }: Props) {
  const leagueId = useSession(s => s.league?.league_id);
  const userId = useSession(s => s.user?.user_id);
  const hasToken = useSession(s => s.hasToken);
  const switching = useSession(s => s.switching);
  const platform = useSession(s => s.leagues.find(l => l.league_id === leagueId)?.platform ?? 'sleeper');
  const enabled = useFlag('league.projections');
  const available = enabled && hasToken && !switching && !!userId && !!leagueId && leagueId !== NO_LEAGUE_ID && platform === 'sleeper';
  const query = useQuery({ queryKey: ['league-projection-batch', userId, leagueId],
    queryFn: () => getLeagueProjectionBatch(leagueId!), enabled: available, staleTime: 60_000 });
  const [side, setSide] = useState<PlayoffTradeSide | null>(null);
  if (!available) return null;
  const view = homePlayoffBanner(query.data, rosterId, query.isError);
  const choosing = side && view.sides.includes(side) ? side : null;
  const choose = (position: SplitPos) => {
    if (!choosing) return;
    const action = choosing === 'buy' ? onBuy : onSell;
    setSide(null);
    action?.(position);
  };
  return <View testID="home.playoff.banner" style={styles.banner}>
    <Card>
      <TickLabel>{view.current ? 'Estimated playoff chance' : 'Playoff forecast'}</TickLabel>
      {view.probability != null ? <Text variant="heading" style={styles.spacing}>
        {(view.probability * 100).toFixed(1)}%{view.current ? '' : ' · last saved estimate'}
      </Text> : null}
      <Text variant="bodySm" style={styles.detail}>{query.isLoading ? 'Loading saved forecast…' : view.status}</Text>
      {view.capturedAt ? <Text variant="bodySm" style={styles.detail}>As of {new Date(view.capturedAt).toLocaleDateString()}{view.partial ? ' · uses partial Sleeper data' : ''}</Text> : null}
      {view.question ? <>
        <Text style={styles.spacing}>{view.question}</Text>
        <View style={styles.actions}>
          {view.sides.map(action => <Button key={action} label={action === 'buy' ? 'Buy a player' : 'Sell a player'}
            variant="secondary" testID={action === 'buy' ? 'home.playoff.buy' : 'home.playoff.sell'} disabled={action === 'buy' ? !onBuy : !onSell}
            onPress={() => setSide(side === action ? null : action)} />)}
        </View>
        {(!onBuy || !onSell) ? <Text variant="bodySm" style={styles.detail}>Player choices appear when your league’s roster values are available.</Text> : null}
      </> : null}
      {choosing ? <View testID="home.playoff.positions" style={styles.spacing}>
        <Text variant="bodySm">Which position would you like to {choosing}?</Text>
        <View style={styles.actions}>{SPLIT_POSITIONS.map(position => <Button key={position} label={position}
          variant="secondary" testID={POSITION_TEST_IDS[position]} accessibilityLabel={`${choosing === 'buy' ? 'Buy' : 'Sell'} a ${position}`}
          onPress={() => choose(position)} />)}</View>
      </View> : null}
      <Button label="View standings" variant="ghost" onPress={onDetails} testID="home.playoff.details" />
    </Card>
  </View>;
}

const styles = StyleSheet.create({
  banner: { marginBottom: space.lg },
  spacing: { marginTop: space.sm },
  detail: { color: chalk.dim, marginTop: space.xs },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.sm },
});
