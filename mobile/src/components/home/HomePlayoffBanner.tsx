import React, { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Button, Card, Icon, Text } from '../chalkline';
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
  const availableSides = view.sides.filter(action => action === 'buy' ? onBuy : onSell);
  const choosing = side && availableSides.includes(side) ? side : null;
  const probability = view.probability != null ? `${(view.probability * 100).toFixed(1)}%` : null;
  const asOf = view.capturedAt ? new Date(view.capturedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : null;
  const status = query.isLoading ? 'Loading forecast…' : view.status;
  const savedDate = asOf && !view.current && status !== 'Last saved' ? `Saved ${asOf}` : asOf;
  const subtitle = [status, savedDate, asOf && view.partial ? 'Partial data' : null].filter(Boolean).join(' · ');
  const choose = (position: SplitPos) => {
    if (!choosing) return;
    const action = choosing === 'buy' ? onBuy : onSell;
    setSide(null);
    action?.(position);
  };
  return <View testID="home.playoff.banner" style={styles.banner}>
    <Card padding={space.md}>
      <Pressable testID="home.playoff.details" accessibilityRole="button"
        accessibilityLabel={`Projected Season Finish. ${probability ? `${probability} ${view.current ? 'estimated playoff chance' : 'last saved estimate of playoff chance'}. ` : ''}${subtitle}. View standings.`}
        onPress={onDetails} style={styles.summary}>
        <View style={styles.heading}>
          <Text variant="title" style={styles.title}>Projected Season Finish</Text>
          <Text variant="bodySm">View</Text>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </View>
        <View style={styles.estimate}>
          {probability ? <Text variant="bodySm" style={styles.prompt}>{probability} playoff odds</Text> : null}
          <Text variant="bodySm" style={styles.subtitle}>{subtitle}</Text>
        </View>
      </Pressable>
      {availableSides.length > 0 ? <View style={styles.actions}>
        {availableSides.map(action => <Button key={action} label={action === 'buy' ? 'Buy a player' : 'Sell a player'}
          variant="secondary" testID={action === 'buy' ? 'home.playoff.buy' : 'home.playoff.sell'}
          onPress={() => setSide(side === action ? null : action)} />)}
      </View> : null}
      {choosing ? <View testID="home.playoff.positions" style={styles.spacing}>
        <Text variant="bodySm" style={styles.prompt}>{choosing === 'buy' ? 'Buy at which position?' : 'Sell at which position?'}</Text>
        <View style={styles.actions}>{SPLIT_POSITIONS.map(position => <Button key={position} label={position}
          variant="secondary" testID={POSITION_TEST_IDS[position]} accessibilityLabel={`${choosing === 'buy' ? 'Buy' : 'Sell'} a ${position}`}
          onPress={() => choose(position)} />)}</View>
      </View> : null}
    </Card>
  </View>;
}

const styles = StyleSheet.create({
  banner: { marginBottom: space.lg },
  spacing: { marginTop: space.sm },
  summary: { minHeight: 44, justifyContent: 'center' },
  heading: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  title: { flex: 1, minWidth: 0 },
  estimate: { flexDirection: 'row', flexWrap: 'wrap', columnGap: space.sm, alignItems: 'baseline' },
  subtitle: { flexShrink: 1 },
  prompt: { color: chalk.base },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.xs },
});
