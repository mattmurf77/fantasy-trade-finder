import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { chalk, ice, ink, radii, space, type } from '../theme/chalkline';
import { Button, Meter, Text, TickLabel } from '../components/chalkline';
import GradingCard from '../components/GradingCard';
import GradingResults from '../components/GradingResults';
import Toast from '../components/Toast';
import { ApiError } from '../api/client';
import {
  GRADING_TAG_LABELS,
  answerGradingCard,
  getCurrentGradingSession,
  getGradingResults,
  getNextGradingCard,
  startGradingSession,
  type GradingAnswer,
  type GradingSession,
  type GradingTag,
} from '../api/grading';
import { NO_LEAGUE_ID, useSession } from '../state/useSession';

// Calibration — in-app blind grading of today's trade engine vs the value
// core (docs/plans/blind-grading/, lld.md §10). Open to every app user since
// 2026-10-05 (operator); every call 404s when `grading.blind` is off, and that
// 404 renders here as "Not available".
//
// Flow (specs.md §3.3 wins over lld §10.3 where they differ):
//   intro → Start POSTs → 202 `building` → poll GET /current every 1.5 s
//   (cap 60 s, then "taking longer than usual") → `open` → one card at a
//   time → grade 1–5 (+ tags) or Skip → … → done → Results → Done → intro.
//   `failed` renders a plain message per error code + Start over (POST again).
//
// A TAB-stack screen: it mounts NO FeedbackFAB — RootNav's single global
// mount already covers it (#188; a second one is the #196/#197 double-FAB
// bug). mobile/tests/check-blind-grading.js pins that, the static testIDs,
// and that no engine-identifying token appears in this file: the screen holds
// a card's trade and nothing else about it.

type Grade = 1 | 2 | 3 | 4 | 5;

// Static testIDs — two const tables of literal strings, mapped over, so
// testid-lint's grep and the blind-grading guard both resolve every id
// (scope.md §3). Never template these.
const GRADE_BUTTONS = [
  { grade: 1, testID: 'calibration.grade-1' },
  { grade: 2, testID: 'calibration.grade-2' },
  { grade: 3, testID: 'calibration.grade-3' },
  { grade: 4, testID: 'calibration.grade-4' },
  { grade: 5, testID: 'calibration.grade-5' },
] as const;
const TAG_CHIPS = [
  { tag: 'overpay', testID: 'calibration.tag.overpay' },
  { tag: 'they_wont_accept', testID: 'calibration.tag.they_wont_accept' },
  { tag: 'junk_filler', testID: 'calibration.tag.junk_filler' },
  { tag: 'too_small', testID: 'calibration.tag.too_small' },
  { tag: 'wrong_for_my_window', testID: 'calibration.tag.wrong_for_my_window' },
  { tag: 'wrong_for_their_window', testID: 'calibration.tag.wrong_for_their_window' },
  { tag: 'same_guy_again', testID: 'calibration.tag.same_guy_again' },
] as const;   // labels come from GRADING_TAG_LABELS in api/grading.ts

// §3.3 build poll: while the session is `building`, re-read GET /current on
// this cadence; past the cap, stop and offer a retry instead of spinning.
const BUILD_POLL_MS = 1500;
const BUILD_POLL_CAP_MS = 60_000;

// Copy (lld.md §10.6 + §3.3). Kept as literals in one table so the JSX stays
// free of raw apostrophes and the guard's token scan reads them as strings.
const COPY = {
  introTitle: 'Calibration',
  intro: (league: string) =>
    `Grade up to 40 trade ideas for ${league}, one at a time. Some come from ` +
    "today's trade engine and some from the new one, shuffled — you won't know which is which.",
  purpose:
    'Why this exists: Calibration captures your honest reactions so we can improve the ' +
    'trade model. Your grades are compared across both engines and used to tune which trade ' +
    'ideas Fleeced suggests.',
  start: 'Start',
  resume: (k: number, n: number) => `Resume (${k} of ${n} answered)`,
  noLeague: 'Pick a league first.',
  unavailableTitle: 'Not available',
  unavailable: "Calibration isn't turned on for this account.",
  needsDeck: "Open Acquire for this league first so there's a fresh deck to compare against, then come back.",
  openAcquire: 'Open Acquire',
  tryAgain: 'Try again',
  startOver: 'Start over',
  building: 'Building your deck…',
  buildSlow: 'This is taking longer than usual. Try again.',
  tooFew: 'The new engine found too few trades for this league right now. Try another league.',
  notSynced: 'This league isn’t loaded yet. Reopen it from the league picker and try again.',
  startFailed: 'Something went wrong starting the session. Try again.',
  buildFailed: 'Something went wrong building the session. Start over to try again.',
  prompt: 'Would you send this?',
  anchorLow: '1 · No way',
  anchorHigh: '5 · Send it',
  next: 'Next',
  skip: 'Skip',
  done: 'Done',
  saveFailed: "Couldn't save that grade. Try again.",
  resultsFailed: "Couldn't load the results.",
} as const;

const is404 = (e: unknown) => e instanceof ApiError && e.status === 404;
const errorCode = (e: unknown): string | null =>
  e instanceof ApiError && e.body && typeof e.body === 'object'
    ? ((e.body as { error?: unknown }).error as string | undefined) ?? null
    : null;

// Copy for a session the server flipped to `failed` (§3.3). The code's
// prefix names the second engine, and this file is pinned never to spell it
// (the blinding guard), so the match is on the suffix alone.
const failedCopy = (session: GradingSession): string =>
  session.error?.code?.endsWith('too_few') ? COPY.tooFew : COPY.buildFailed;

const startErrorCopy = (e: unknown): string => {
  const code = errorCode(e);
  if (code === 'league_not_synced' || code === 'league_not_active') return COPY.notSynced;
  return COPY.startFailed;
};

type Phase =
  | 'no-league' | 'unavailable' | 'needs-deck' | 'error'
  | 'results' | 'grading' | 'failed' | 'building' | 'build-slow'
  | 'loading' | 'intro';

export default function CalibrationScreen() {
  const navigation = useNavigation<any>();
  const qc = useQueryClient();
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id ?? null;
  const hasLeague = !!leagueId && leagueId !== NO_LEAGUE_ID;
  const currentKey = ['grading', 'current', leagueId] as const;

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [completedId, setCompletedId] = useState<string | null>(null);
  const [grade, setGrade] = useState<Grade | null>(null);
  const [tags, setTags] = useState<GradingTag[]>([]);
  // When we first saw the server session `building` (ms epoch); null otherwise.
  const [buildSince, setBuildSince] = useState<number | null>(null);
  const [buildSlow, setBuildSlow] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // The server's view of this league's session: newest building / open /
  // failed, never a completed one. Polls itself while building (§3.3).
  // Not in PERSIST_KEYS (App.tsx), so nothing here survives a relaunch — the
  // server is the only resume source.
  const currentQ = useQuery({
    queryKey: currentKey,
    queryFn: () => getCurrentGradingSession(leagueId as string),
    enabled: hasLeague,
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchInterval: (q) =>
      q.state.data?.session?.status === 'building' && !buildSlow ? BUILD_POLL_MS : false,
  });
  const serverSession = currentQ.data?.session ?? null;

  const startM = useMutation({
    mutationFn: () => startGradingSession(leagueId as string),
    onSuccess: (r) => {
      // Seed the poll with the POST's own SessionView so the first 1.5 s tick
      // is not spent re-reading what we were just told.
      qc.setQueryData(currentKey, { session: r.session });
      if (r.session.status === 'open') setSessionId(r.session.session_id);
      // `building` ⇒ currentQ's refetchInterval takes over; the effect below
      // enters grading the moment the status flips to `open`.
    },
  });

  // §3.3 — track the build. Start the clock on the first `building` read;
  // when the status leaves `building`, enter grading on `open` (the `failed`
  // phase renders straight off serverSession) and clear the clock.
  const serverStatus = serverSession?.status ?? null;
  const serverSessionId = serverSession?.session_id ?? null;
  useEffect(() => {
    if (serverStatus === 'building') {
      if (buildSince == null) setBuildSince(Date.now());
      return;
    }
    if (buildSince != null) {
      if (serverStatus === 'open' && serverSessionId) setSessionId(serverSessionId);
      setBuildSince(null);
      setBuildSlow(false);
    }
  }, [serverStatus, serverSessionId, buildSince]);

  // The 60 s cap: stop polling and offer Try again instead of spinning.
  useEffect(() => {
    if (buildSince == null || buildSlow) return;
    const remaining = Math.max(0, buildSince + BUILD_POLL_CAP_MS - Date.now());
    const t = setTimeout(() => setBuildSlow(true), remaining);
    return () => clearTimeout(t);
  }, [buildSince, buildSlow]);

  const nextQ = useQuery({
    queryKey: ['grading', 'next', sessionId],
    queryFn: () => getNextGradingCard(sessionId as string),
    enabled: !!sessionId && !completedId,
    retry: false,
  });
  const card = nextQ.data && !nextQ.data.done ? nextQ.data.card : null;
  const cardId = card?.card_id ?? null;
  const progress = nextQ.data?.progress ?? null;

  // The server says every card is answered ⇒ results.
  const nextDone = nextQ.data?.done === true;
  useEffect(() => {
    if (nextDone && sessionId) setCompletedId(sessionId);
  }, [nextDone, sessionId]);

  // A new card starts with no grade and no tags.
  useEffect(() => {
    setGrade(null);
    setTags([]);
  }, [cardId]);

  const answerM = useMutation({
    mutationFn: (answer: GradingAnswer) => answerGradingCard(cardId as string, answer),
    onSuccess: (r) => {
      setGrade(null);
      setTags([]);
      if (r.session_status === 'completed') setCompletedId(r.session_id);
      else void qc.invalidateQueries({ queryKey: ['grading', 'next', sessionId] });
    },
    onError: (e) => {
      if (errorCode(e) === 'session_completed') {
        setCompletedId(sessionId);
        return;
      }
      if (!is404(e)) setToast(COPY.saveFailed);   // keep the selection
    },
  });

  const resultsQ = useQuery({
    queryKey: ['grading', 'results', completedId],
    queryFn: () => getGradingResults(completedId as string),
    enabled: !!completedId,
    retry: false,
  });

  // A session belongs to one league: switching leagues drops everything.
  // (currentQ re-keys on leagueId by itself.)
  const resetStart = startM.reset;
  useEffect(() => {
    setSessionId(null);
    setCompletedId(null);
    setGrade(null);
    setTags([]);
    setBuildSince(null);
    setBuildSlow(false);
    resetStart();
  }, [leagueId, resetStart]);

  const handleDone = () => {
    setSessionId(null);
    setCompletedId(null);
    startM.reset();
    void qc.invalidateQueries({ queryKey: currentKey });
  };

  // "Open Acquire" — the Acquire tab's route name is `Trades` (TabNav); the
  // parent of a tab-stack screen is the Tab navigator. Clear the start error
  // too, so coming back lands on intro → Start instead of this message.
  const handleOpenAcquire = () => {
    startM.reset();
    navigation.getParent()?.navigate('Trades');
  };

  // Past the cap: restart the clock and poll again. POSTing would only
  // return the same `building` session (resume), so re-reading is the honest
  // action; a genuinely failed build arrives as `failed`.
  const handleBuildRetry = () => {
    setBuildSlow(false);
    setBuildSince(Date.now());
    void currentQ.refetch();
  };

  const toggleTag = (t: GradingTag) =>
    setTags((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  const submit = () => {
    if (!grade || !cardId) return;
    answerM.mutate({ grade, tags });
  };
  const skip = () => {
    if (!cardId) return;
    answerM.mutate({ skip: true });
  };

  // Phase — derived in render, first match wins (lld §10.3 + §3.3).
  const errors = [currentQ.error, startM.error, nextQ.error, answerM.error, resultsQ.error];
  let phase: Phase;
  if (!hasLeague) phase = 'no-league';
  else if (errors.some(is404)) phase = 'unavailable';
  else if (startM.error && errorCode(startM.error) === 'needs_fresh_deck') phase = 'needs-deck';
  else if (startM.error) phase = 'error';
  else if (completedId) phase = 'results';
  else if (sessionId) phase = 'grading';
  else if (serverStatus === 'failed') phase = 'failed';
  else if (serverStatus === 'building') phase = buildSlow ? 'build-slow' : 'building';
  else if (currentQ.isPending || startM.isPending) phase = 'loading';
  else phase = 'intro';

  const renderBody = () => {
    switch (phase) {
      case 'no-league':
        return <Text variant="body" testID="calibration.no-league">{COPY.noLeague}</Text>;

      case 'unavailable':
        return (
          <View style={styles.block} testID="calibration.unavailable">
            <Text variant="heading">{COPY.unavailableTitle}</Text>
            <Text variant="body">{COPY.unavailable}</Text>
          </View>
        );

      case 'needs-deck':
        return (
          <View style={styles.block}>
            <Text variant="body">{COPY.needsDeck}</Text>
            <Button
              testID="calibration.open-acquire"
              label={COPY.openAcquire}
              variant="primary"
              onPress={handleOpenAcquire}
            />
          </View>
        );

      case 'error':
        return (
          <View style={styles.block}>
            <Text variant="body">{startErrorCopy(startM.error)}</Text>
            <Button
              testID="calibration.retry"
              label={COPY.tryAgain}
              variant="secondary"
              onPress={() => startM.mutate()}
            />
          </View>
        );

      case 'failed':
        return (
          <View style={styles.block}>
            <Text variant="body">{failedCopy(serverSession as GradingSession)}</Text>
            <Button
              testID="calibration.start"
              label={COPY.startOver}
              variant="primary"
              onPress={() => startM.mutate()}
            />
          </View>
        );

      case 'building':
        return (
          <View style={styles.center} testID="calibration.loading">
            <ActivityIndicator color={ice.base} />
            <Text variant="bodySm">{COPY.building}</Text>
          </View>
        );

      case 'build-slow':
        return (
          <View style={styles.block}>
            <Text variant="body">{COPY.buildSlow}</Text>
            <Button
              testID="calibration.retry"
              label={COPY.tryAgain}
              variant="secondary"
              onPress={handleBuildRetry}
            />
          </View>
        );

      case 'loading':
        return (
          <View style={styles.center} testID="calibration.loading">
            <ActivityIndicator color={ice.base} />
          </View>
        );

      case 'intro': {
        const open = serverSession?.status === 'open' ? serverSession : null;
        return (
          <View style={styles.block}>
            <TickLabel>{COPY.introTitle}</TickLabel>
            <Text variant="body">{COPY.intro(league?.league_name ?? 'this league')}</Text>
            <Text variant="bodySm" testID="calibration.purpose">{COPY.purpose}</Text>
            {open ? (
              <Button
                testID="calibration.resume"
                label={COPY.resume(open.progress.answered, open.progress.total)}
                variant="primary"
                onPress={() => setSessionId(open.session_id)}
              />
            ) : (
              <Button
                testID="calibration.start"
                label={COPY.start}
                variant="primary"
                onPress={() => startM.mutate()}
              />
            )}
          </View>
        );
      }

      case 'grading': {
        if (!card || !progress) {
          return (
            <View style={styles.center} testID="calibration.loading">
              <ActivityIndicator color={ice.base} />
            </View>
          );
        }
        const busy = answerM.isPending || nextQ.isFetching;
        return (
          <View style={styles.block}>
            <View style={styles.progressRow}>
              <Text variant="data" testID="calibration.progress">
                {`${card.position} / ${progress.total}`}
              </Text>
              <View style={styles.meter}>
                <Meter value={progress.total ? progress.answered / progress.total : 0} />
              </View>
            </View>

            <View testID="calibration.card">
              <GradingCard trade={card.trade} />
            </View>

            <Text variant="title">{COPY.prompt}</Text>

            <View style={styles.gradeRow}>
              {GRADE_BUTTONS.map((b) => {
                const selected = grade === b.grade;
                return (
                  <Pressable
                    key={b.testID}
                    testID={b.testID}
                    accessibilityRole="button"
                    accessibilityLabel={`Grade ${b.grade} of 5`}
                    accessibilityState={{ selected }}
                    onPress={() => setGrade(b.grade)}
                    style={[styles.gradeBtn, selected && styles.gradeBtnSelected]}
                  >
                    <Text
                      variant="dataLg"
                      style={selected ? styles.gradeNumSelected : undefined}
                    >
                      {String(b.grade)}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <View style={styles.anchors}>
              <Text variant="bodySm">{COPY.anchorLow}</Text>
              <Text variant="bodySm">{COPY.anchorHigh}</Text>
            </View>

            <View style={styles.tagWrap}>
              {TAG_CHIPS.map((c) => {
                const selected = tags.includes(c.tag);
                return (
                  <Pressable
                    key={c.testID}
                    testID={c.testID}
                    accessibilityRole="button"
                    accessibilityLabel={GRADING_TAG_LABELS[c.tag]}
                    accessibilityState={{ selected }}
                    hitSlop={6}
                    onPress={() => toggleTag(c.tag)}
                    style={[styles.tagChip, selected && styles.tagChipSelected]}
                  >
                    <Text
                      scale="dense"
                      style={[type.label, styles.tagText, selected && styles.tagTextSelected]}
                    >
                      {GRADING_TAG_LABELS[c.tag]}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            <View style={styles.actions}>
              <Button
                testID="calibration.submit"
                label={COPY.next}
                variant="primary"
                disabled={!grade || busy}
                loading={answerM.isPending}
                onPress={submit}
              />
              <Button
                testID="calibration.skip"
                label={COPY.skip}
                variant="ghost"
                disabled={busy}
                onPress={skip}
              />
            </View>
          </View>
        );
      }

      case 'results':
        return (
          <View style={styles.block} testID="calibration.results">
            {resultsQ.data ? (
              <GradingResults results={resultsQ.data} />
            ) : resultsQ.error ? (
              <Text variant="body">{COPY.resultsFailed}</Text>
            ) : (
              <View style={styles.center} testID="calibration.loading">
                <ActivityIndicator color={ice.base} />
              </View>
            )}
            {resultsQ.data || resultsQ.error ? (
              <Button
                testID="calibration.done"
                label={COPY.done}
                variant="primary"
                onPress={handleDone}
              />
            ) : null}
          </View>
        );
    }
  };

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {renderBody()}
      </ScrollView>
      <Toast
        visible={!!toast}
        message={toast ?? ''}
        tone="error"
        onDismiss={() => setToast(null)}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  content: { padding: space.lg, paddingBottom: space.xxl },
  block: { gap: space.lg },
  center: { alignItems: 'center', justifyContent: 'center', gap: space.md, paddingVertical: space.xxxl },
  progressRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  meter: { flex: 1 },
  gradeRow: { flexDirection: 'row', gap: space.sm },
  // Five equal-width cells, 44pt floor; selection = ice border + ice numeral
  // on an ink-3 well (ice = action/selection, never flare).
  gradeBtn: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: 'transparent',
  },
  gradeBtnSelected: { backgroundColor: ink.ink3, borderColor: ice.base },
  gradeNumSelected: { color: ice.base },
  anchors: { flexDirection: 'row', justifyContent: 'space-between', marginTop: -space.sm },
  tagWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  // Badges & chips construction: radius 2, label type, 1px border; 32pt tall
  // with 6pt hitSlop for an effective 44pt target.
  tagChip: {
    minHeight: 32,
    paddingHorizontal: space.md,
    justifyContent: 'center',
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrong,
  },
  tagChipSelected: { borderColor: ice.base },
  tagText: { color: chalk.base },
  tagTextSelected: { color: ice.base },
  actions: { gap: space.sm },
});
