import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { chalk, ice, ink, radii, space, type } from '../theme/chalkline';
import { Button, Meter, Text, TickLabel } from '../components/chalkline';
import GradingCard from '../components/GradingCard';
import GradingResults from '../components/GradingResults';
import Toast from '../components/Toast';
import { ApiError, getSessionRevision, requestAborted } from '../api/client';
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
//   time → Yes / No (+ optional reasons) or Skip → … → done → Results → Done →
//   intro. Yes sends grade 5 and No grade 1 (operator, 2026-10-14: graders used
//   the extremes almost exclusively); the server still accepts 1–5.
//   `failed` renders a plain message per error code + Start over (POST again).
//
// A TAB-stack screen: it mounts NO FeedbackFAB — RootNav's single global
// mount already covers it (#188; a second one is the #196/#197 double-FAB
// bug). mobile/tests/check-blind-grading.js pins that, the static testIDs,
// and that no engine-identifying token appears in this file: the screen holds
// a card's trade and nothing else about it.

type CalibrationScope = { userId: string | null; leagueId: string | null; revision: number };
type Selection = { id: string; phase: 'waiting' | 'grading' | 'results'; scope: CalibrationScope };
type StartRequest = { leagueId: string; scope: CalibrationScope; beforeDispatch: () => void };
type AnswerRequest = {
  cardId: string; sessionId: string; answer: GradingAnswer;
  scope: CalibrationScope; beforeDispatch: () => void;
};

type Grade = 1 | 5;   // the server's 1–5 scale, used as No / Yes

// Static testIDs — two const tables of literal strings, mapped over, so
// testid-lint's grep and the blind-grading guard both resolve every id
// (scope.md §3). Never template these.
const VERDICT_BUTTONS = [
  { grade: 5, label: 'Yes', testID: 'calibration.yes' },
  { grade: 1, label: 'No', testID: 'calibration.no' },
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
    `Would you send these trades in ${league}? Rate one idea at a time, or skip it.`,
  snapshot: (date: string) => `League snapshot from ${new Date(date).toLocaleDateString()}. Rate the idea using that snapshot.`,
  purpose:
    'Your answers help improve the trades Fleeced suggests. Rating a trade never sends an offer.',
  start: 'Start',
  resume: (k: number, n: number) => `Resume (${k} of ${n} answered)`,
  noLeague: 'Pick a league first.',
  unavailableTitle: 'Not available',
  unavailable: "Calibration isn't available right now.",
  unsupported: 'This league has roster rules or player eligibility that Calibration cannot verify yet. Try another connected league.',
  accountLink: 'Calibration cannot yet verify this account’s team link in this league. Try another connected league.',
  reconnect: 'Calibration could not verify your current team in this league. Reconnect your own league account, select your team, and try again.',
  interrupted: 'This deck was interrupted while building. Start over for a fresh comparison.',
  needsDeck: "Open Acquire for this league first so there's a fresh deck to compare against, then come back.",
  openAcquire: 'Open Acquire',
  tryAgain: 'Try again',
  checkAgain: 'Check again',
  startOver: 'Start over',
  building: 'Building your deck…',
  buildSlow: 'Your comparison is still being prepared. This can take several minutes. You can leave this screen and check again later.',
  tooFew: 'There aren’t enough trade ideas for this league right now. Try another league.',
  notSynced: 'This league isn’t loaded yet. Reopen it from the league picker and try again.',
  sessionReadFailed: 'Couldn’t load your session.',
  cardReadFailed: 'Couldn’t load the next trade idea.',
  startFailed: 'Something went wrong starting the session. Try again.',
  buildFailed: 'Something went wrong building the session. Start over to try again.',
  prompt: 'Would you send this?',
  whyLabel: 'Why? (optional)',
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
const failedCopy = (session: GradingSession): string => {
  const code = session.error?.code ?? '';
  if (code.endsWith('too_few')) return COPY.tooFew;
  if (['unsupported_platform', 'provider_roster_coverage_unavailable', 'provider_lineup_unsupported', 'provider_cross_domain_eligibility', 'provider_player_eligibility_unsupported', 'provider_position_limits_unsupported', 'provider_roster_position_unsupported', 'provider_settings_unsupported'].includes(code)) return COPY.unsupported;
  if (code === 'provider_account_binding_unavailable') return COPY.accountLink;
  if (['league_membership_required', 'league_seat_changed', 'espn_auth_required', 'mfl_auth_required', 'espn_credentials_unavailable', 'mfl_credentials_unavailable'].includes(code)) return COPY.reconnect;
  if (['league_not_synced', 'league_not_connected', 'seat_changed', 'league_seat_changed', 'roster_unavailable', 'league_data_unavailable', 'league_rosters_unavailable', 'lineup_unavailable', 'pick_ownership_unavailable', 'player_availability_stale'].includes(code)) return COPY.notSynced;
  if (code === 'comparison_interrupted') return COPY.interrupted;
  return COPY.buildFailed;
};

const startErrorCopy = (e: unknown): string => {
  const code = errorCode(e);
  if (code === 'league_not_synced' || code === 'league_not_active') return COPY.notSynced;
  return COPY.startFailed;
};

type Phase =
  | 'no-league' | 'unavailable' | 'needs-deck' | 'error'
  | 'results' | 'grading' | 'failed' | 'building' | 'build-slow'
  | 'read-error' | 'loading' | 'intro';

export default function CalibrationScreen() {
  const navigation = useNavigation<any>();
  const qc = useQueryClient();
  const userId = useSession((s) => s.user?.user_id ?? null);
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id ?? null;
  const hasLeague = !!leagueId && leagueId !== NO_LEAGUE_ID;
  const revision = getSessionRevision();
  const scopeKey = [leagueId, userId, revision] as const;
  const currentKey = ['grading', 'current', ...scopeKey] as const;
  const recoveryScope = useRef<CalibrationScope>({ userId, leagueId, revision });
  if (recoveryScope.current.userId !== userId || recoveryScope.current.leagueId !== leagueId
      || recoveryScope.current.revision !== revision) {
    recoveryScope.current = { userId, leagueId, revision };
  }
  const screenScope = recoveryScope.current;
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const inScope = () => {
    const session = useSession.getState();
    return mounted.current && recoveryScope.current === screenScope
      && screenScope.revision === getSessionRevision()
      && screenScope.userId === (session.user?.user_id ?? null)
      && screenScope.leagueId === (session.league?.league_id ?? null);
  };
  const beforeDispatch = () => {
    if (!inScope()) throw requestAborted();
  };

  const [selection, setSelection] = useState<Selection | null>(null);
  const selected = selection?.scope === screenScope ? selection : null;
  const sessionId = selected?.phase === 'grading' ? selected.id : null;
  const completedId = selected?.phase === 'results' ? selected.id : null;
  const select = (id: string, phase: Selection['phase']) => setSelection({ id, phase, scope: screenScope });
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
    queryFn: ({ signal }) => getCurrentGradingSession(leagueId as string, { signal, beforeDispatch }),
    enabled: hasLeague && !!userId,
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchInterval: (q) =>
      q.state.data?.session?.status === 'building' && !buildSlow ? BUILD_POLL_MS : false,
  });
  const serverSession = currentQ.data?.session ?? null;

  const startM = useMutation({
    mutationFn: (request: StartRequest) =>
      startGradingSession(request.leagueId, { beforeDispatch: request.beforeDispatch }),
    onSuccess: (r, request) => {
      if (request.scope !== screenScope || !inScope()) return;
      const { session } = r;
      qc.setQueryData(currentKey, { session });
      if (session.status === 'open') select(session.session_id, 'grading');
      if (session.status === 'completed') select(session.session_id, 'results');
      if (session.status === 'building') select(session.session_id, 'waiting');
    },
  });
  const handleStart = () => {
    if (leagueId && inScope()) startM.mutate({ leagueId, scope: screenScope, beforeDispatch });
  };

  // A status poll can finish a build the user never asked to open. Only
  // proceed for the same session they explicitly started or chose to resume.
  const serverStatus = serverSession?.status ?? null;
  const serverSessionId = serverSession?.session_id ?? null;
  useEffect(() => {
    if (serverStatus === 'building') {
      if (buildSince == null) setBuildSince(Date.now());
      return;
    }
    if (buildSince != null) {
      setBuildSince(null);
      setBuildSlow(false);
    }
    if (selected?.phase === 'waiting' && selected.id === serverSessionId
        && serverStatus === 'open') {
      setSelection({ ...selected, phase: 'grading' });
    }
  }, [serverStatus, serverSessionId, buildSince, selected]);

  // The 60 s cap: stop polling and offer Try again instead of spinning.
  useEffect(() => {
    if (buildSince == null || buildSlow) return;
    const remaining = Math.max(0, buildSince + BUILD_POLL_CAP_MS - Date.now());
    const t = setTimeout(() => setBuildSlow(true), remaining);
    return () => clearTimeout(t);
  }, [buildSince, buildSlow]);

  const nextKey = ['grading', 'next', sessionId, ...scopeKey] as const;
  const nextQ = useQuery({
    queryKey: nextKey,
    queryFn: ({ signal }) => getNextGradingCard(sessionId as string, { signal, beforeDispatch }),
    enabled: !!sessionId && !completedId,
    retry: false,
  });
  const card = nextQ.data && !nextQ.data.done ? nextQ.data.card : null;
  const cardId = card?.card_id ?? null;
  const progress = nextQ.data?.progress ?? null;

  // The server says every card is answered ⇒ results.
  const nextDone = nextQ.data?.done === true;
  useEffect(() => {
    if (nextDone && selected?.phase === 'grading') setSelection({ ...selected, phase: 'results' });
  }, [nextDone, selected]);

  // A new card starts with no grade and no tags.
  useEffect(() => {
    setGrade(null);
    setTags([]);
  }, [cardId]);

  const answerM = useMutation({
    mutationFn: (request: AnswerRequest) =>
      answerGradingCard(request.cardId, request.answer, { beforeDispatch: request.beforeDispatch }),
    onSuccess: (r, request) => {
      if (request.scope !== screenScope || !inScope()) return;
      setGrade(null);
      setTags([]);
      if (r.session_status === 'completed') select(r.session_id, 'results');
      else void qc.invalidateQueries({ queryKey: ['grading', 'next', request.sessionId, ...scopeKey] });
    },
    onError: (e, request) => {
      if (request.scope !== screenScope || !inScope()) return;
      if (errorCode(e) === 'session_completed') {
        select(request.sessionId, 'results');
        return;
      }
      if (!is404(e)) setToast(COPY.saveFailed);   // keep the selection
    },
  });

  const resultsQ = useQuery({
    queryKey: ['grading', 'results', completedId, ...scopeKey],
    queryFn: ({ signal }) => getGradingResults(completedId as string, { signal, beforeDispatch }),
    enabled: !!completedId,
    retry: false,
  });

  // A session belongs to one league: switching leagues drops everything.
  // (currentQ re-keys on leagueId by itself.)
  const resetStart = startM.reset;
  const resetAnswer = answerM.reset;
  useEffect(() => {
    setSelection(null);
    setGrade(null);
    setTags([]);
    setBuildSince(null);
    setBuildSlow(false);
    setToast(null);
    resetStart();
    resetAnswer();
  }, [screenScope, resetStart, resetAnswer]);

  // An unopened exercise can be retired between /current and /next. Retry
  // discovers its replacement; retrying the retired ID can never succeed.
  // Only this exact conflict changes sessions. Ordinary read errors retry the
  // same endpoint, and recovery never enrolls or discards answered history.
  const handleReadRetry = async () => {
    if (!inScope()) return;
    if (!(sessionId && nextQ.error instanceof ApiError && nextQ.error.status === 409
          && errorCode(nextQ.error) === 'comparison_not_ready')) {
      void (sessionId ? nextQ : currentQ).refetch();
      return;
    }
    const result = await currentQ.refetch();
    if (!inScope() || result.isError) return;
    const replacement = result.data?.session;
    if (replacement?.status === 'open') select(replacement.session_id, 'grading');
    else if (replacement?.status === 'building') select(replacement.session_id, 'waiting');
    else if (replacement?.status === 'completed') select(replacement.session_id, 'results');
    else setSelection(null);
    setBuildSlow(false);
    setBuildSince(replacement?.status === 'building' ? Date.now() : null);
  };

  const handleDone = () => {
    if (!inScope()) return;
    setSelection(null);
    startM.reset();
    void qc.invalidateQueries({ queryKey: currentKey });
  };

  // "Open Acquire" — the Acquire tab's route name is `Trades` (TabNav); the
  // parent of a tab-stack screen is the Tab navigator. Clear the start error
  // too, so coming back lands on intro → Start instead of this message.
  const handleOpenAcquire = () => {
    if (!inScope()) return;
    startM.reset();
    navigation.getParent()?.navigate('Trades');
  };

  // Past the cap: restart the clock and poll again. POSTing would only
  // return the same `building` session (resume), so re-reading is the honest
  // action; a genuinely failed build arrives as `failed`.
  const handleBuildRetry = () => {
    if (!inScope()) return;
    setBuildSlow(false);
    setBuildSince(Date.now());
    void currentQ.refetch();
  };

  const toggleTag = (t: GradingTag) =>
    setTags((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  const save = (answer: GradingAnswer) => {
    if (!cardId || !sessionId || !inScope()) return;
    answerM.mutate({ cardId, sessionId, answer, scope: screenScope, beforeDispatch });
  };
  const submit = () => { if (grade) save({ grade, tags }); };
  const skip = () => save({ skip: true });

  // Phase — derived in render, first match wins (lld §10.3 + §3.3).
  const errors = [currentQ.error, startM.error, nextQ.error, answerM.error, resultsQ.error];
  let phase: Phase;
  if (!hasLeague) phase = 'no-league';
  else if (errors.some(is404)) phase = 'unavailable';
  else if (startM.error && errorCode(startM.error) === 'needs_fresh_deck') phase = 'needs-deck';
  else if (startM.error) phase = 'error';
  else if (completedId) phase = 'results';
  else if (sessionId && nextQ.isError) phase = 'read-error';
  else if (sessionId) phase = 'grading';
  else if (currentQ.isError) phase = 'read-error';
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

      case 'read-error':
        return (
          <View style={styles.block}>
            <Text variant="body">{sessionId ? COPY.cardReadFailed : COPY.sessionReadFailed}</Text>
            <Button
              testID="calibration.retry"
              label={COPY.tryAgain}
              variant="secondary"
              disabled={nextQ.isFetching || currentQ.isFetching}
              onPress={handleReadRetry}
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
              onPress={handleStart}
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
              onPress={handleStart}
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
              label={COPY.checkAgain}
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
            {serverSession?.captured_at ? <Text variant="bodySm">{COPY.snapshot(serverSession.captured_at)}</Text> : null}
            {open ? (
              <Button
                testID="calibration.resume"
                label={COPY.resume(open.progress.answered, open.progress.total)}
                variant="primary"
                onPress={() => { if (inScope()) select(open.session_id, 'grading'); }}
              />
            ) : (
              <Button
                testID="calibration.start"
                label={COPY.start}
                variant="primary"
                onPress={handleStart}
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

            {serverSession?.captured_at ? <Text variant="bodySm">{COPY.snapshot(serverSession.captured_at)}</Text> : null}
            <View testID="calibration.card">
              <GradingCard trade={card.trade} />
            </View>

            <Text variant="title">{COPY.prompt}</Text>

            <View style={styles.gradeRow}>
              {VERDICT_BUTTONS.map((b) => {
                const selected = grade === b.grade;
                return (
                  <Pressable
                    key={b.testID}
                    testID={b.testID}
                    accessibilityRole="button"
                    accessibilityLabel={`Would send: ${b.label}`}
                    accessibilityState={{ selected }}
                    onPress={() => setGrade(b.grade)}
                    style={[styles.gradeBtn, selected && styles.gradeBtnSelected]}
                  >
                    <Text
                      variant="title"
                      style={selected ? styles.gradeNumSelected : undefined}
                    >
                      {b.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            <Text variant="label">{COPY.whyLabel}</Text>

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
  // Two equal-width cells, 52pt tall; selection = ice border + ice label on an
  // ink-3 well (ice = action/selection, never flare).
  gradeBtn: {
    flex: 1,
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: 'transparent',
  },
  gradeBtnSelected: { backgroundColor: ink.ink3, borderColor: ice.base },
  gradeNumSelected: { color: ice.base },
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
