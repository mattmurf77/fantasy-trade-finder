import React, { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Icon, Text } from '../chalkline';
import { chalk, fonts, ice, ink, radii, space, type } from '../../theme/chalkline';
import { getLeagueProjectionBatch, type ProjectionOutlook } from '../../api/leagueProjections';
import { getLeaguePreferences } from '../../api/league';
import { NO_LEAGUE_ID, useSession } from '../../state/useSession';
import { useFlag } from '../../state/useFeatureFlags';
import { homePlayoffBanner } from '../../utils/homePlayoffBanner';
import { playoffOddsText } from '../../utils/playoffOdds';
import { track } from '../../api/events';
import {
  cardBlock, pickFigure, viewOpensSheet, shownProps, sheetRows, CARD_EVENTS,
  DIRECTION_CARD_FLAG, DIRECTION_SHEET_FLAG, type DirectionTap, type SheetRow,
} from '../../utils/directionCard';
import { DIRECTION_CARD_COPY as K } from '../../utils/directionCardCopy';
import { DIRECTION_COPY as C } from '../../utils/directionPagesCopy';
import { outlookDisplayName } from '../OutlookBiasReceipt';
import { RowAction } from './StatusRow';
import DirectionSheet from './DirectionSheet';

interface Props {
  rosterId: number | null;
  /** The percentage and the "View" link both open the Standings table. */
  onDetails: () => void;
  /** Opens the outlook selector with the suggestion marked. Saves nothing. */
  onReviewOutlook: (recommended: ProjectionOutlook) => void;
  /** The host's route name, for the card's own impression (spec H-11). */
  screen: string;
  /** Improve pages (D-270): "View" opening the half sheet, and a sheet row.
   *  The host tracks `home_tile_tapped {tile, via}` and navigates
   *  (`utils/directionCard.tapDestination`). */
  onDirectionTap: (tap: DirectionTap) => void;
}

// The row is 40pt like StatusRow; these bring each control to a 44pt target.
const LINK_SLOP = { top: 12, bottom: 12, left: 8, right: 8 };
const INFO_SLOP = { top: 2, bottom: 2, left: 6, right: 6 };
// "View" sits after the info button: 2pt into the 8pt gap (the info's own
// slop takes 6), the rest into the row's 12pt right padding.
const VIEW_SLOP = { top: 2, bottom: 2, left: 2, right: 12 };

/** Same saved weekly result as Standings; no view-triggered calculation. */
export default function HomePlayoffBanner({ rosterId, onDetails, onReviewOutlook, screen, onDirectionTap }: Props) {
  const leagueId = useSession(s => s.league?.league_id);
  const userId = useSession(s => s.user?.user_id);
  const hasToken = useSession(s => s.hasToken);
  const switching = useSession(s => s.switching);
  const platform = useSession(s => s.leagues.find(l => l.league_id === leagueId)?.platform ?? 'sleeper');
  const enabled = useFlag('league.projections');
  const outlookOn = useFlag('league.projection_outlook');
  // Improve pages (spec §4, §5.6, §8; D-270). The sheet also needs the pages
  // flag: its rows are entry points to the pages, which that flag gates.
  const cardOn = useFlag(DIRECTION_CARD_FLAG);
  const sheetFlag = useFlag(DIRECTION_SHEET_FLAG);
  const pagesOn = useFlag('league.direction_pages');
  const available = enabled && hasToken && !switching && !!userId && !!leagueId && leagueId !== NO_LEAGUE_ID && platform === 'sleeper';
  const query = useQuery({ queryKey: ['league-projection-batch', userId, leagueId],
    queryFn: () => getLeagueProjectionBatch(leagueId!), enabled: available, staleTime: 60_000 });
  // The saved outlook, on the key every preference writer refreshes (the
  // hosts already read it, so this is a cache hit): the "Consider" prompt
  // hides the moment the saved outlook matches the recommendation.
  const prefsQuery = useQuery({ queryKey: ['league-prefs', leagueId],
    queryFn: () => getLeaguePreferences(leagueId!), enabled: available });
  const [open, setOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const shownRef = useRef(false);
  // The server's block, or null for today's row (H-12). Every figure and
  // row below is the block's; the card classifies nothing.
  const direction = available ? cardBlock(query.data, cardOn) : null;
  const sheetOn = cardOn && sheetFlag && pagesOn;
  const view = homePlayoffBanner(query.data, rosterId, query.isError, Date.now(), prefsQuery.data?.team_outlook);
  const percent = view.probability != null ? playoffOddsText(view.probability, view.proof, 0.1) : null;
  const pick = pickFigure(direction, percent != null);
  // direction_card_shown: once per mount, the first render with a block.
  useEffect(() => {
    if (!direction || shownRef.current) return;
    shownRef.current = true;
    track(CARD_EVENTS.shown, shownProps(direction, sheetOn, !!pick), screen);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [direction]);
  if (!available) return null;
  const savedOn = view.capturedAt ? new Date(view.capturedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : null;
  const status = query.isLoading ? 'Loading forecast…' : view.status;
  // The server classified the unrounded probability; this only names its pick.
  const recommendation = outlookOn ? view.recommendation : null;
  const consider = recommendation ? outlookDisplayName(recommendation.outlook) : null;
  const explanation = outlookOn ? view.explanation : null;
  // The server's suggestion sentence goes with the "Consider" prompt: same
  // conditions, shown in the expanded explanation above `explanation`.
  const suggestion = recommendation && consider ? recommendation.suggestion : null;
  // "View ›": the half sheet when the card holds a block and the sheet is on
  // (S-2, S-10), otherwise Standings as before. The percentage always opens
  // Standings.
  const opensSheet = viewOpensSheet(direction, sheetOn);
  const onView = opensSheet ? () => { onDirectionTap({ tile: 'playoff_options', via: 'card' }); setSheetOpen(true); } : onDetails;
  const onChoose = (row: SheetRow) => {
    setSheetOpen(false);
    onDirectionTap({ tile: row.tile, via: 'sheet' });
  };
  // H-1 to H-7: two figures side by side (they wrap onto two lines at large
  // text sizes, H-10), the info toggle beside the percentage, "View ›" last.
  // One value line: each figure is label / 40pt value line / notes, and the
  // "View ›" column mirrors it (same top padding, a hidden label-height
  // spacer, then its 40pt control), so the percentage, the info button, the
  // pick and "View ›" share one centre at any text size. "last saved" and
  // "owned by" sit under their value, never on the line: on the line, two
  // "last saved" notes pushed the pair past a 375pt screen and the pick
  // wrapped under the percentage at default text size.
  const figures = direction ? <View style={[styles.row, styles.figuresRow]} testID="home.playoff.figures">
    <View style={styles.figures}>
      <View style={styles.figure} testID="home.playoff.figure.playoff">
        <Text scale="dense" style={type.label}>{C['SUM.playoff']}</Text>
        <View style={styles.figureLine} testID="home.playoff.figure.playoff.line">
          {percent ? <Pressable testID="home.playoff.details" accessibilityRole="link" hitSlop={LINK_SLOP}
            accessibilityLabel={`${percent} playoff chance${view.current ? '' : ', last saved'}. View projected standings.`}
            onPress={onDetails}>
            <Text style={styles.link}>{percent}</Text>
          </Pressable> : <Text testID="home.playoff.status" style={styles.status}>{status}</Text>}
          <Pressable testID="home.playoff.explain" accessibilityRole="button" aria-expanded={open}
            accessibilityLabel="About playoff chance" hitSlop={INFO_SLOP}
            onPress={() => setOpen(value => !value)} style={styles.info}>
            <Icon name="info" size={16} color={chalk.base} />
          </Pressable>
        </View>
        {percent && !view.current ? <Text style={styles.note}>last saved</Text> : null}
      </View>
      {pick ? <View style={styles.figure} testID="home.playoff.pick" accessible
        accessibilityLabel={`${C['SUM.pick']} ${pick.label}${pick.owner ? `, ${pick.owner}` : ''}${view.current ? '' : ', last saved'}`}>
        <Text scale="dense" style={type.label}>{C['SUM.pick']}</Text>
        <View style={styles.figureLine} testID="home.playoff.pick.line">
          <Text testID="home.playoff.pick.value" style={styles.figureValue}>{pick.label}</Text>
        </View>
        {view.current ? null : <Text style={styles.note}>last saved</Text>}
        {pick.owner ? <Text testID="home.playoff.pick.owner" style={styles.note}>{pick.owner}</Text> : null}
      </View> : null}
    </View>
    <View style={styles.viewColumn} testID="home.playoff.view.column">
      <Text scale="dense" style={type.label} testID="home.playoff.view.spacer" aria-hidden
        accessibilityElementsHidden importantForAccessibility="no-hide-descendants">{' '}</Text>
      <Pressable testID="home.playoff.view" accessibilityRole={opensSheet ? 'button' : 'link'}
        accessibilityLabel={opensSheet ? K['SHEET.label'] : 'View full projections'}
        hitSlop={VIEW_SLOP} onPress={onView} style={styles.view}>
        <RowAction label="View" />
      </Pressable>
    </View>
  </View> : null;
  return <View testID="home.playoff.banner" style={styles.banner}>
    {figures ?? <View style={styles.row}>
      <Text scale="dense" style={[type.label, styles.key]}>Playoff chance</Text>
      <View style={styles.value}>
        {percent ? <>
          <Pressable testID="home.playoff.details" accessibilityRole="link" hitSlop={LINK_SLOP}
            accessibilityLabel={`${percent} playoff chance${view.current ? '' : ', last saved'}. View projected standings.`}
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
      <Pressable testID="home.playoff.view" accessibilityRole="link" accessibilityLabel="View full projections"
        hitSlop={VIEW_SLOP} onPress={onDetails} style={styles.view}>
        <RowAction label="View" />
      </Pressable>
    </View>}
    {open ? <View testID="home.playoff.explanation" style={styles.explanation}>
      <Text style={styles.body}>Share of simulated seasons in which your team makes the playoffs, from projected weekly lineups. Updated weekly.</Text>
      {percent && !view.current && savedOn ? <Text style={styles.body}>{`Last saved ${savedOn}. ${view.status}.`}</Text> : null}
      {view.incomplete ? <Text style={styles.body}>Incomplete: a played starter's score is not recorded yet.</Text> : null}
      {pick ? <Text testID="home.playoff.pick.explanation" style={styles.body}>{K['EXPLAIN.pick']}</Text> : null}
      {suggestion ? <Text testID="home.playoff.suggestion" style={styles.body}>{suggestion}</Text> : null}
      {explanation ? <Text style={styles.body}>{explanation}</Text> : null}
    </View> : null}
    {recommendation && consider ? <View testID="home.playoff.recommendation" style={[styles.row, styles.divider]}>
      <Text style={styles.consider}>{`Consider ${consider}`}</Text>
      <Pressable testID="home.playoff.review-outlook" accessibilityRole="button" hitSlop={LINK_SLOP}
        accessibilityLabel={`${playoffOddsText(recommendation.probability, view.proof, 1)} playoff chance. Consider ${consider}. Review outlook.`}
        onPress={() => onReviewOutlook(recommendation.outlook)}>
        <Text style={styles.action}>Review outlook</Text>
      </Pressable>
    </View> : null}
    {opensSheet ? <DirectionSheet visible={sheetOpen} rows={sheetRows(direction!)} onClose={() => setSheetOpen(false)}
      onChoose={onChoose} /> : null}
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
  // Never shrinks: on a narrow row the value column ("last saved") wraps.
  view: { minHeight: 40, flexShrink: 0, justifyContent: 'center' },
  // Improve pages (D-270): the two figures. Each keeps a minimum width, so
  // at large text sizes the second wraps under the first (H-10).
  // The figures row only: top-aligned, so "View ›" lines up with the value
  // line instead of centring on label + value (+ notes).
  figuresRow: { alignItems: 'flex-start' },
  figures: { flex: 1, minWidth: 0, flexDirection: 'row', flexWrap: 'wrap', columnGap: space.lg, paddingVertical: space.xs },
  figure: { minWidth: 120, gap: 2 },
  // Mirrors `figures` + `figure`: same padding and gap, a label-height spacer.
  viewColumn: { flexShrink: 0, paddingVertical: space.xs, gap: 2 },
  figureLine: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: space.sm, minHeight: 40 },
  figureValue: { fontFamily: fonts.dataSemi, fontSize: 14, lineHeight: 20, fontVariant: ['tabular-nums'], color: chalk.base },
  explanation: { gap: space.xs, paddingHorizontal: space.md, paddingBottom: space.sm },
  body: { ...type.bodySm, color: chalk.base },
  consider: { flex: 1, minWidth: 0, fontFamily: fonts.uiSemi, fontSize: 14, lineHeight: 20, color: chalk.base },
  action: { fontFamily: fonts.uiMedium, fontSize: 13, lineHeight: 18, color: ice.base },
});
