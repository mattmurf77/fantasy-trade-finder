import React, { useMemo, useRef } from 'react';
import { View, ScrollView, Pressable, ActivityIndicator, StyleSheet } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';
import { Button, Text } from './chalkline';
import { ink, chalk, ice, space, radii } from '../theme/chalkline';
import { getLeagueRosters, findMyRoster } from '../api/sleeper';
import { getLeagueProjectionBatch } from '../api/leagueProjections';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { MaxPfMovesBody } from './MaxPfMovesSection';
import { PlayoffTargetsBody } from './PlayoffTargetsSection';
import { deriveSection as deriveMaxPf } from '../utils/maxPfMoves';
import { deriveSection as deriveTargets } from '../utils/playoffTargets';
import { DIRECTION_COPY as C } from '../utils/directionPagesCopy';
import {
  pageView, summary, pageLinks, PAGE_FLAG, PAGE_TESTID, DIRECTION_PAGES_FLAG, type DirectionPage as Page,
} from '../utils/directionPages';

// Improve pages — the content shared by the two root-stack screens,
// ImprovePlayoffChancesScreen and ImproveDraftPickScreen (spec
// docs/plans/league-projections/direction-pages/spec.md §3, D-265). Each
// screen owns its SafeAreaView and its own FeedbackFAB (#188); RootNav gives
// it the Standings header (LeagueTopBarHeader + the #151 JS back).
//
// NO NEW REQUEST (P-4). The forecast is the one cached read Standings, Home
// and League rankings share (['league-projection-batch', userId, leagueId],
// same fetcher and staleTime as StandingsScreen); the live rosters are the
// session-seeded ['league-rosters', leagueId] query Standings also reads.
// Opening a page never starts a forecast.
//
// THE LIST IS THE EXISTING BODY (P-5): MaxPfMovesBody or PlayoffTargetsBody,
// rendered directly, not inside a Disclosure, so it is open on arrival
// (P-7). The page adds the two-figure summary above it (P-6) and the links
// under it (P-10), and no row, number or copy of its own for the rows.

export function DirectionPage({ page }: { page: Page }) {
  const leagueId = useSession((s) => s.league?.league_id) || null;
  const userId = useSession((s) => s.user?.user_id ?? null);
  // P-14: keyed by league, so a switch drops every piece of local state
  // (open row, Show all, the impression ref) with the old league's data.
  return <DirectionPageContent key={`${userId}:${leagueId}`} page={page} leagueId={leagueId} userId={userId} />;
}

function DirectionPageContent({ page, leagueId, userId }: { page: Page; leagueId: string | null; userId: string | null }) {
  const navigation = useNavigation<any>();
  const id = PAGE_TESTID[page];
  // StandingsScreen's platform rule: unknown resolves to Sleeper.
  const platform = useSession((s) => s.leagues.find((l) => l.league_id === leagueId)?.platform) ?? 'sleeper';
  const isSleeper = platform === 'sleeper';
  const projectionsOn = useFlag('league.projections');
  const maxPfOn = useFlag(PAGE_FLAG.draft_pick);
  const targetsOn = useFlag(PAGE_FLAG.playoffs);
  const directionPagesOn = useFlag(DIRECTION_PAGES_FLAG);
  const featureOn = page === 'draft_pick' ? maxPfOn : targetsOn;

  const rostersQuery = useQuery({
    queryKey: ['league-rosters', leagueId],
    queryFn: () => getLeagueRosters(leagueId!),
    enabled: isSleeper && !!leagueId,
    staleTime: 5 * 60_000,
  });
  const forecastEnabled = projectionsOn && featureOn && isSleeper && !!leagueId && !!userId;
  const forecastQuery = useQuery({
    queryKey: ['league-projection-batch', userId, leagueId],
    queryFn: () => getLeagueProjectionBatch(leagueId!),
    enabled: forecastEnabled,
    staleTime: 60_000,
  });
  const data = forecastEnabled ? forecastQuery.data : undefined;
  const liveRosterIds = useMemo(() => {
    const rosters = rostersQuery.data;
    return rosters && userId ? findMyRoster(rosters, userId)?.players ?? null : null;
  }, [rostersQuery.data, userId]);
  // The body's impression fires once per arrival (this content remounts per league).
  const viewedRef = useRef(false);

  const view = pageView({
    page, leagueId, userId, isSleeper, projectionsOn, featureOn, data, isError: forecastQuery.isError,
  });

  if (view.kind === 'no_league') {
    return <View style={styles.center} testID={`${id}.no-league`}>
      <Text variant="heading">{C['NO-LEAGUE.title']}</Text>
      <Text variant="bodySm" style={styles.centerBody}>{C['NO-LEAGUE.body']}</Text>
    </View>;
  }

  let body: React.ReactNode;
  if (view.kind === 'unavailable') {
    body = <View style={styles.card} testID={`${id}.unavailable`}>
      <Text variant="heading" style={styles.cardTitle}>{C['UNAVAILABLE.title']}</Text>
      <Text variant="bodySm">{C['UNAVAILABLE.body']}</Text>
    </View>;
  } else if (view.kind === 'loading') {
    body = <View style={styles.center} testID={`${id}.loading`}><ActivityIndicator color={ice.base} /></View>;
  } else if (view.kind === 'error') {
    body = <View style={styles.center} testID={`${id}.error`}>
      <Text variant="bodySm" style={styles.centerBody}>{C['ERROR.body']}</Text>
      <Button label={C['ERROR.retry']} variant="secondary" compact loading={forecastQuery.isFetching}
        onPress={() => forecastQuery.refetch()} testID={`${id}.retry`} />
    </View>;
  } else {
    const figures = summary(page, data);
    const links = pageLinks(page, data, { directionPagesOn, maxPfOn, targetsOn });
    body = <>
      {figures ? <View style={styles.summary} testID={`${id}.summary`}>
        {figures.playoff ? <View style={styles.figure} testID={`${id}.summary.playoff`}>
          <Text variant="label">{C['SUM.playoff']}</Text>
          <Text variant="dataLg" style={styles.figureValue}>{figures.playoff}</Text>
        </View> : null}
        {figures.pick ? <View style={styles.figure} testID={`${id}.summary.pick`}>
          <Text variant="label">{C['SUM.pick']}</Text>
          <Text variant="dataLg" style={styles.figureValue}>{figures.pick}</Text>
        </View> : null}
      </View> : null}
      {view.kind === 'draft_pick'
        ? <MaxPfMovesBody block={view.block} model={deriveMaxPf(view.block, liveRosterIds)} leagueId={leagueId!}
            userId={userId} viewedRef={viewedRef} openOnArrival />
        : <PlayoffTargetsBody block={view.block} model={deriveTargets(view.block, rostersQuery.data ?? null)}
            viewedRef={viewedRef} />}
      <View style={styles.links}>
        {/* popTo: back to Standings or the other page when it is below in
            the stack, otherwise it replaces this page, so links never pile
            pages up. */}
        <Pressable accessibilityRole="button" testID={`${id}.link.standings`} style={styles.link}
          onPress={() => navigation.popTo(links.standings.route)}>
          <Text variant="bodySm" style={styles.linkText}>{links.standings.label}</Text>
        </Pressable>
        {links.other ? <Pressable accessibilityRole="button" testID={`${id}.link.other`} style={styles.link}
          onPress={() => navigation.popTo(links.other!.route)}>
          <Text variant="bodySm" style={styles.linkText}>{links.other.label}</Text>
        </Pressable> : null}
      </View>
    </>;
  }
  return <ScrollView contentContainerStyle={styles.scroll} testID={`${id}.content`}>{body}</ScrollView>;
}

// StandingsScreen's page construction: ink-0 page, ink-1 card with a hairline
// and radius md, mono numbers. Ice only on the tappable links (actions).
const styles = StyleSheet.create({
  scroll: { padding: space.lg, paddingBottom: space.xxl, gap: space.md },
  center: { alignItems: 'center', gap: space.md, paddingVertical: space.xl },
  centerBody: { textAlign: 'center' },
  card: { gap: space.sm, padding: space.lg, borderRadius: radii.md, borderWidth: 1, borderColor: ink.line, backgroundColor: ink.ink1 },
  cardTitle: { marginBottom: space.xs },
  // Two figures side by side; at large text sizes they wrap onto two lines.
  summary: { flexDirection: 'row', flexWrap: 'wrap', gap: space.lg, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: ink.line },
  figure: { gap: 2, minWidth: 120 },
  figureValue: { color: chalk.base },
  links: { borderTopWidth: 1, borderTopColor: ink.line, alignItems: 'flex-start' },
  link: { minHeight: 44, justifyContent: 'center' },
  linkText: { color: ice.base },
});
