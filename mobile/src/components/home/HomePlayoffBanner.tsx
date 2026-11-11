import React, { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Icon, Text } from '../chalkline';
import { chalk, fonts, ice, ink, radii, space, type } from '../../theme/chalkline';
import { getLeagueProjectionBatch, type ProjectionOutlook } from '../../api/leagueProjections';
import { NO_LEAGUE_ID, useSession } from '../../state/useSession';
import { useFlag } from '../../state/useFeatureFlags';
import { homePlayoffBanner } from '../../utils/homePlayoffBanner';
import { outlookDisplayName } from '../OutlookBiasReceipt';

interface Props {
  rosterId: number | null;
  /** The percentage is the link to Standings. */
  onDetails: () => void;
  /** Opens the outlook selector with the suggestion marked. Saves nothing. */
  onReviewOutlook: (recommended: ProjectionOutlook) => void;
}

// The row is 40pt like StatusRow; these bring each control to a 44pt target.
const LINK_SLOP = { top: 12, bottom: 12, left: 8, right: 8 };
const INFO_SLOP = { top: 2, bottom: 2, left: 6, right: 6 };

/** Same saved weekly result as Standings; no view-triggered calculation. */
export default function HomePlayoffBanner({ rosterId, onDetails, onReviewOutlook }: Props) {
  const leagueId = useSession(s => s.league?.league_id);
  const userId = useSession(s => s.user?.user_id);
  const hasToken = useSession(s => s.hasToken);
  const switching = useSession(s => s.switching);
  const platform = useSession(s => s.leagues.find(l => l.league_id === leagueId)?.platform ?? 'sleeper');
  const enabled = useFlag('league.projections');
  const outlookOn = useFlag('league.projection_outlook');
  const available = enabled && hasToken && !switching && !!userId && !!leagueId && leagueId !== NO_LEAGUE_ID && platform === 'sleeper';
  const query = useQuery({ queryKey: ['league-projection-batch', userId, leagueId],
    queryFn: () => getLeagueProjectionBatch(leagueId!), enabled: available, staleTime: 60_000 });
  const [open, setOpen] = useState(false);
  if (!available) return null;
  const view = homePlayoffBanner(query.data, rosterId, query.isError);
  const percent = view.probability != null ? `${(view.probability * 100).toFixed(1)}%` : null;
  const savedOn = view.capturedAt ? new Date(view.capturedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : null;
  const status = query.isLoading ? 'Loading forecast…' : view.status;
  // The server classified the unrounded probability; this only names its pick.
  const recommendation = outlookOn ? view.recommendation : null;
  const consider = recommendation ? outlookDisplayName(recommendation.outlook) : null;
  const explanation = outlookOn ? view.explanation : null;
  // The server's suggestion sentence goes with the "Consider" prompt: same
  // conditions, shown in the expanded explanation above `explanation`.
  const suggestion = recommendation && consider ? recommendation.suggestion : null;
  return <View testID="home.playoff.banner" style={styles.banner}>
    <View style={styles.row}>
      <Text scale="dense" style={[type.label, styles.key]}>Playoff chance</Text>
      <View style={styles.value}>
        {percent ? <>
          <Pressable testID="home.playoff.details" accessibilityRole="link" hitSlop={LINK_SLOP}
            accessibilityLabel={`${percent} playoff chance${view.current ? '' : ', last saved'}. View standings.`}
            onPress={onDetails}>
            <Text style={styles.link}>{percent}</Text>
          </Pressable>
          {view.current ? null : <Text style={styles.note}>last saved</Text>}
        </> : <Text testID="home.playoff.status" style={styles.status}>{status}</Text>}
      </View>
      <Pressable testID="home.playoff.explain" accessibilityRole="button" aria-expanded={open}
        accessibilityLabel="About playoff chance" hitSlop={INFO_SLOP}
        onPress={() => setOpen(value => !value)} style={styles.info}>
        <Icon name="info" size={16} color={chalk.base} />
      </Pressable>
    </View>
    {open ? <View testID="home.playoff.explanation" style={styles.explanation}>
      <Text style={styles.body}>Share of simulated seasons in which your team makes the playoffs, from projected weekly lineups. Updated weekly.</Text>
      {percent && !view.current && savedOn ? <Text style={styles.body}>{`Last saved ${savedOn}. ${view.status}.`}</Text> : null}
      {view.incomplete ? <Text style={styles.body}>Incomplete: some lineup slots had no projection.</Text> : null}
      {suggestion ? <Text testID="home.playoff.suggestion" style={styles.body}>{suggestion}</Text> : null}
      {explanation ? <Text style={styles.body}>{explanation}</Text> : null}
    </View> : null}
    {recommendation && consider ? <View testID="home.playoff.recommendation" style={[styles.row, styles.divider]}>
      <Text style={styles.consider}>{`Consider ${consider}`}</Text>
      <Pressable testID="home.playoff.review-outlook" accessibilityRole="button" hitSlop={LINK_SLOP}
        accessibilityLabel={`${Math.round(recommendation.probability * 100)}% playoff chance. Consider ${consider}. Review outlook.`}
        onPress={() => onReviewOutlook(recommendation.outlook)}>
        <Text style={styles.action}>Review outlook</Text>
      </Pressable>
    </View> : null}
  </View>;
}

const styles = StyleSheet.create({
  banner: {
    marginBottom: space.sm,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    overflow: 'hidden',
  },
  row: { minHeight: 40, flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingHorizontal: space.md },
  divider: { borderTopWidth: 1, borderTopColor: ink.line },
  key: { width: 100 },
  value: { flex: 1, minWidth: 0, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.sm },
  link: { fontFamily: fonts.dataSemi, fontSize: 14, lineHeight: 20, fontVariant: ['tabular-nums'], color: ice.base },
  note: { fontFamily: fonts.ui, fontSize: 12, lineHeight: 16, color: chalk.base },
  status: { fontFamily: fonts.uiSemi, fontSize: 14, lineHeight: 20, color: chalk.base },
  info: { width: 32, height: 40, alignItems: 'center', justifyContent: 'center' },
  explanation: { gap: space.xs, paddingHorizontal: space.md, paddingBottom: space.sm },
  body: { ...type.bodySm, color: chalk.base },
  consider: { flex: 1, minWidth: 0, fontFamily: fonts.uiSemi, fontSize: 14, lineHeight: 20, color: chalk.base },
  action: { fontFamily: fonts.uiMedium, fontSize: 13, lineHeight: 18, color: ice.base },
});
