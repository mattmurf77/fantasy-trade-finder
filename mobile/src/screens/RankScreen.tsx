import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  AccessibilityInfo,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useNavigation } from '@react-navigation/native';
import { haptics } from '../utils/haptics';
import { track } from '../api/events';
import { startSpan } from '../observability/sentry';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  flare,
  semantic,
  position as positionColors,
  space,
  radii,
  type,
  fonts,
  scrim,
  shadowSheet,
} from '../theme/chalkline';
import {
  Badge,
  Button,
  Icon,
  PositionBadge,
  RookieBadge,
  Text as ChalkText,
} from '../components/chalkline';
import FormatToggle from '../components/FormatToggle';
import Toast from '../components/Toast';
import { InfoButton } from '../components/HelpSheet';
import RookieScopeControl, { RookieScopeEmpty } from '../components/RookieScopeControl';
import { useRookieScope } from '../state/rookieScope';
import {
  getNextTrio,
  getProgress,
  getStreak,
  submitTrioRanking,
  isScopedEmpty,
  type ScopedEmpty,
} from '../api/rankings';
import type { Position, ScoringFormat, Trio, RankingProgress } from '../shared/types';
import { useFlag } from '../state/useFeatureFlags';
import { useSession } from '../state/useSession';
import { useScoringFormat } from '../hooks/useScoringFormat';

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];
const THRESHOLD_FALLBACK = 10;
const SPEED_MODE_KEY = 'ftf.trios.speedMode';

const posColorFor = (p: Position) =>
  positionColors[p.toLowerCase() as keyof typeof positionColors];

export default function RankScreen() {
  const queryClient = useQueryClient();
  const navigation  = useNavigation();
  const activeFormat = useSession((s) => s.activeFormat);
  const leagueId = useSession((s) => s.league?.league_id ?? null);
  // FB #80 — SF/1QB toggle. setFormat flips the server session + local
  // mirrors and marks the choice explicit so the league-default applier
  // (RootNav) won't override it this session.
  const { setFormat, switching: formatSwitching } = useScoringFormat();
  const [position, setPosition] = useState<Position>('QB');
  const [selectionOrder, setSelectionOrder] = useState<('a' | 'b' | 'c')[]>([]);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  const [infoSheet, setInfoSheet] = useState<{ name: string; info: string } | null>(null);
  // I AM SPEED — when ON we auto-rank the 3rd choice + auto-submit after the
  // user picks 2. Default OFF (manual confirm). Persisted to AsyncStorage so
  // the toggle survives app restarts. Mirrors web/js/app.js's autoConfirmEnabled.
  const [speedMode, setSpeedMode] = useState(false);
  useEffect(() => {
    AsyncStorage.getItem(SPEED_MODE_KEY).then((v) => {
      if (v === '1') setSpeedMode(true);
    });
  }, []);

  // Onboarding 8b — trio retention metric: one event per screen visit
  // (week-1 "trio session on a later day" reads off this). Gated inside
  // track() by analytics.client_events; no onboarding flag needed.
  useEffect(() => {
    track('trio_session_started', undefined, 'Trios');
  }, []);
  const toggleSpeedMode = useCallback(() => {
    setSpeedMode((prev) => {
      const next = !prev;
      void AsyncStorage.setItem(SPEED_MODE_KEY, next ? '1' : '0');
      haptics.selection();
      return next;
    });
  }, []);

  const qcEnabled      = useFlag('swipe.qc_compliments');
  const gestureEnabled = useFlag('swipe.gesture_audit');
  // Teardown flags (default false — flag off is byte-identical):
  // S4 PRD-02 unlock-copy fixes ride the outlook-inline flag; S3 PRD-02
  // gives the long-press info sheet a visible ⓘ twin; S2 PRD-04 ride-along
  // promotes content-carrying faint text to dim.
  const unlockCopyOn = useFlag('ux.outlook_inline_default');
  const menuOn = useFlag('ux.player_context_menu');
  const cleanupOn = useFlag('visual.chalkline_cleanup');

  // FB #80 — explicit format switch from the header toggle. On failure the
  // local state is untouched (the toggle stays where it was) — just toast.
  const onFormatChange = useCallback(
    async (fmt: ScoringFormat) => {
      haptics.selection();
      const ok = await setFormat(fmt);
      if (!ok) setToast({ msg: 'Could not switch format', tone: 'warn' });
    },
    [setFormat],
  );

  // ── Data ────────────────────────────────────────────────────────────
  // rookie-draft M2 — Trios ships LAST in the scope rollout (plan §M2),
  // gated on M0's measurement: 85 valued rookies league-wide with TE=21,
  // so every format/position can still draw a 3-candidate matchup. Under
  // scope the rookie subset constrains CANDIDATE SELECTION only — the Elo
  // updates a submitted trio produces are unchanged full-board updates, so
  // ranking rookies here moves them on the one shared board.
  const rookieScope = useRookieScope();
  const trioQuery = useQuery({
    queryKey: rookieScope.isRookie ? ['trio', position, 'rookie'] : ['trio', position],
    queryFn: () => getNextTrio(position, { scope: rookieScope.param }),
    staleTime: 0,           // each trio is fresh; never reuse
    refetchOnMount: 'always',
  });

  const progressQuery = useQuery({
    queryKey: ['progress', leagueId, activeFormat],
    queryFn: getProgress,
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  });

  const streakQuery = useQuery({
    queryKey: ['streak', leagueId, activeFormat],
    queryFn: getStreak,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  const submitMutation = useMutation({
    // Wrap the network call in a Sentry span so we can see p50/p95
    // latency of trio submits in production. Span is a no-op when
    // Sentry isn't initialized.
    mutationFn: (rankedIds: [string, string, string]) =>
      startSpan({ name: 'trio.submit', op: 'mutation' }, () =>
        submitTrioRanking(rankedIds),
      ),
    onSuccess: (resp) => {
      // Local-merge the progress cache instead of invalidating — every
      // trio submit otherwise eats a ~250 ms /api/rankings/progress
      // refetch (API #A3 + Backend #B5). The /api/rank3 response
      // carries the new `interaction_count` for the submitted position
      // and the global `threshold`, which is all we need to keep the
      // progress bar + per-position counters live.
      //
      // Edge case: the very rank that pushes the user past
      // `total_required` flips `unlocked` server-side and unlocks the
      // Trade Finder banner. We can't derive `unlocked` purely from the
      // submitted position (it requires all positions to be at
      // threshold), so on a threshold cross we fall back to invalidating
      // ONCE — keeps the banner correct without paying the round-trip
      // on every swipe.
      const prevProgress = queryClient.getQueryData<RankingProgress>(['progress', leagueId, activeFormat]);
      const crossedThreshold =
        prevProgress != null &&
        !prevProgress.unlocked &&
        resp.threshold_met === true;
      if (crossedThreshold) {
        queryClient.invalidateQueries({ queryKey: ['progress', leagueId, activeFormat] });
      } else if (prevProgress) {
        const prevCount = prevProgress[position] ?? 0;
        // Don't decrement on a same-day re-rank (server returns the
        // same count) — `Math.max` keeps the local counter monotonic.
        const nextCount = Math.max(prevCount, resp.interaction_count);
        const delta = nextCount - prevCount;
        queryClient.setQueryData<RankingProgress>(['progress', leagueId, activeFormat], {
          ...prevProgress,
          [position]: nextCount,
          threshold: resp.threshold,
          total_completed: prevProgress.total_completed + delta,
        });
      }
      queryClient.invalidateQueries({ queryKey: ['trio', position] });
      // Submitting a trio rewrites per-position ELOs server-side; the
      // Overall / Manual / Tiers screens all read these via the
      // `['rankings', ...]` family. Scope to the submitted position +
      // 'all' so unrelated position caches aren't evicted unnecessarily.
      // Mirrors api-layer review #A2.
      queryClient.invalidateQueries({ queryKey: ['rankings', position] });
      queryClient.invalidateQueries({ queryKey: ['rankings', 'all'] });
      setSelectionOrder([]);
      // Detect streak increment from inline response — compare to the
      // currently-cached value before writing through. If the new value
      // jumped, celebrate. (Same-day re-ranks are a no-op server-side, so
      // current stays equal — no false positive.)
      const prev = streakQuery.data?.current ?? 0;
      const next = resp.streak?.current ?? 0;
      if (next > prev && next >= 2) {
        setToast({ msg: `${next}-day streak!`, tone: 'success' });
        haptics.success();
      }
      if (resp.streak) {
        queryClient.setQueryData(['streak', leagueId, activeFormat], resp.streak);
      }
      // S8 PRD-01 (inert a11y): the deck rotates silently on a plain
      // success — announce it so VoiceOver users know the rank landed.
      // (Failure + streak/QC paths already announce via Toast.)
      if (!(next > prev && next >= 2)) {
        AccessibilityInfo.announceForAccessibility('Ranking saved — next trio');
      }
    },
    onError: () => {
      // Submit failed (network or 5xx). Today the deck doesn't advance
      // because `['trio', position]` is only invalidated on success — so
      // the user is still looking at the same three cards. Clear the
      // selection so the rank badges don't visually imply "this saved",
      // refetch the trio to make sure we're aligned with whatever the
      // backend currently considers the active trio for this position
      // (in case of a partial commit), and surface a toast so the user
      // knows their rank didn't land. Mirrors the rollback pattern in
      // MatchesScreen.dispMutation.
      setSelectionOrder([]);
      queryClient.invalidateQueries({ queryKey: ['trio', position] });
      setToast({ msg: "Couldn't save your rank — try again.", tone: 'warn' });
    },
  });

  // Skip = "show me a different trio" — DOES NOT permanently remove
  // any player from the user's eligible pool. Aligned with the web
  // client (PR #13, agent #20). Backend /api/trio/skip endpoint is
  // intentionally left in place since older clients may still call it,
  // but we no longer wire it up from this screen.
  const isRefetchingTrio = trioQuery.isFetching && !trioQuery.isLoading;
  const skipTrio = useCallback(() => {
    setSelectionOrder([]);
    queryClient.invalidateQueries({ queryKey: ['trio', position] });
  }, [queryClient, position]);

  // ── Helpers ─────────────────────────────────────────────────────────
  // The scoped path can answer with the typed empty response instead of a
  // trio ({empty:true, reason:'thin_pool'} — a thin rookie pool at a
  // position is a designed state, never a 400). Narrow once here so the
  // rest of the screen keeps working with a plain `Trio | undefined`.
  const trioEmpty: ScopedEmpty | null = isScopedEmpty(trioQuery.data)
    ? trioQuery.data
    : null;
  const trio: Trio | undefined = trioEmpty ? undefined : (trioQuery.data as Trio | undefined);
  const progress = progressQuery.data;

  const rankOf = useCallback(
    (side: 'a' | 'b' | 'c'): 1 | 2 | 3 | null => {
      const idx = selectionOrder.indexOf(side);
      return idx === -1 ? null : ((idx + 1) as 1 | 2 | 3);
    },
    [selectionOrder],
  );

  const playerForSide = (t: Trio, side: 'a' | 'b' | 'c') =>
    side === 'a' ? t.player_a : side === 'b' ? t.player_b : t.player_c;

  // Submit the current selection — runs the QC celebration check then mutates.
  // Pulled out of the effect so it can be called from the Confirm button too.
  const submitCurrent = useCallback(
    (orderToSubmit: ('a' | 'b' | 'c')[]) => {
      if (orderToSubmit.length !== 3 || !trio || submitMutation.isPending) return;
      const rankedIds = orderToSubmit.map(
        (s) => playerForSide(trio, s).id,
      ) as [string, string, string];

      if (
        qcEnabled &&
        trio.is_qc_trio &&
        Array.isArray(trio.qc_expected_order) &&
        trio.qc_expected_order.length === 3 &&
        rankedIds.every((id, i) => id === trio.qc_expected_order![i])
      ) {
        setToast({ msg: 'Nice call — you helped verify the rankings!', tone: 'success' });
        haptics.success();
      }
      submitMutation.mutate(rankedIds);
    },
    [trio, submitMutation, qcEnabled],
  );

  // Rank a card. Tapping an already-ranked card removes it (and anything
  // ranked after it), matching the web app's behavior in selectCard().
  const rankSide = useCallback(
    (side: 'a' | 'b' | 'c') => {
      setSelectionOrder((prev) => {
        const existing = prev.indexOf(side);
        if (existing !== -1) {
          // Undo this card + all later ranks
          return prev.slice(0, existing);
        }
        if (prev.length >= 3) return prev;
        const next = [...prev, side];

        // I AM SPEED: after the user picks 2, auto-rank the 3rd (the only
        // remaining card) and submit immediately. Mirrors the web's
        // autoConfirmEnabled branch in selectCard().
        if (speedMode && next.length === 2 && trio) {
          const sides: ('a' | 'b' | 'c')[] = ['a', 'b', 'c'];
          const last = sides.find((s) => !next.includes(s));
          if (last) {
            const final = [...next, last] as ('a' | 'b' | 'c')[];
            // Defer the submit so React commits the visible rank-3 badge
            // before the trio rotates to the next one.
            setTimeout(() => submitCurrent(final), 0);
            return final;
          }
        }
        return next;
      });
      haptics.selection();
    },
    [speedMode, trio, submitCurrent],
  );

  const handleSkipEntireTrio = () => {
    // Refetch a new trio without removing any player. Matches web's
    // post-PR-#13 Skip semantics — Skip is now ephemeral.
    if (!trio) return;
    skipTrio();
  };

  // Open an info sheet for a player. Only exposed when the gesture-audit
  // flag is on; long-press is the trigger so it doesn't collide with tap.
  const showInfoSheet = (side: 'a' | 'b' | 'c') => {
    if (!gestureEnabled || !trio) return;
    const p = playerForSide(trio, side);
    const lines: string[] = [];
    if (p.team)             lines.push(`Team: ${p.team}`);
    if (p.position)         lines.push(`Position: ${p.position}`);
    if (p.age != null)      lines.push(`Age: ${p.age}`);
    if (p.years_experience != null) lines.push(`Experience: ${p.years_experience} yr${p.years_experience === 1 ? '' : 's'}`);
    if (p.injury_status)    lines.push(`Injury: ${p.injury_status}`);
    if (p.adp != null)      lines.push(`ADP: ${p.adp}`);
    setInfoSheet({ name: p.name, info: lines.join('\n') || 'No extra info on file.' });
  };

  const currentProgressForPos = progress?.[position] ?? 0;
  const threshold = progress?.threshold ?? THRESHOLD_FALLBACK;
  const isUnlockedEverywhere = progress?.unlocked ?? false;

  // ── Render ──────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        {/* Streak chip — only shown once the user has an active streak.
            Tap → jump to the League tab where leaderboards live. */}
        {(streakQuery.data?.current ?? 0) > 0 ? (
          <View style={styles.streakRow}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`${streakQuery.data!.current} day streak`}
              accessibilityHint="Opens the League tab leaderboards"
              onPress={() => {
                haptics.selection();
                // RankScreen is the inner screen of RankStack which is
                // hosted by the Tab navigator — getParent() returns the
                // tab nav directly. Cast because @react-navigation's
                // generic `navigate` doesn't know our route names here.
                // #181: the League tab now lands on the rankings stack root;
                // the leaderboards live on the classic page (LeagueHome).
                (navigation.getParent() as any)?.navigate('League', { screen: 'LeagueHome' });
              }}
              style={({ pressed }) => [
                styles.streakChip,
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <Icon name="trends" size={16} color={flare.base} />
              <Text style={styles.streakNum}>{streakQuery.data!.current}</Text>
              <Text style={styles.streakLabel}>day streak</Text>
              <Icon name="chevron-right" size={14} color={chalk.dim} />
            </Pressable>
          </View>
        ) : null}

        {/* S2 PRD-04 ride-along: content-carrying hint faint → dim. */}
        <Text style={[styles.modeHint, cleanupOn && styles.modeHintDim]}>
          Trios · tap Rank below for more modes
        </Text>

        {/* FB #80 — SF/1QB scoring-format toggle. Defaults to the selected
            league's detected format (useLeagueFormatDefault in RootNav);
            tapping here is an explicit in-session override so trios rank
            the other format's board. Same slot as TiersScreen's: directly
            above the position switcher. */}
        <FormatToggle
          value={activeFormat}
          onChange={onFormatChange}
          disabled={formatSwitching}
        />

        {/* rookie-draft M2 — the shared scope control (flush: this screen's
            ScrollView already pads). A flip clears the in-progress
            selection: the next trio is drawn from a different pool. */}
        <RookieScopeControl
          surface="trios"
          flush
          disabled={submitMutation.isPending}
          onChange={() => setSelectionOrder([])}
        />

        {/* Position switcher — Chalkline segmented control */}
        <View style={styles.switcher}>
          {POSITIONS.map((p, i) => {
            const isActive = p === position;
            const count = progress?.[p] ?? 0;
            return (
              <Pressable
                key={p}
                testID={`trios.pos-tab.${p.toLowerCase()}`}
                accessibilityRole="tab"
                accessibilityState={{ selected: isActive }}
                accessibilityLabel={
                  isUnlockedEverywhere
                    ? p
                    : `${p}, ${Math.min(count, threshold)} of ${threshold} ranked`
                }
                onPress={() => {
                  if (p === position) return;
                  setSelectionOrder([]);
                  setPosition(p);
                }}
                style={({ pressed }) => [
                  styles.switcherBtn,
                  i > 0 && styles.switcherBtnDivider,
                  pressed && { backgroundColor: ink.ink3 },
                  isActive && styles.switcherBtnActive,
                  { borderBottomColor: isActive ? posColorFor(p) : 'transparent' },
                ]}
              >
                <Text
                  style={[
                    styles.switcherText,
                    isActive && styles.switcherTextActive,
                  ]}
                >
                  {p}
                </Text>
                {!isUnlockedEverywhere && (
                  <Text
                    style={[
                      styles.switcherCount,
                      isActive && styles.switcherCountActive,
                    ]}
                  >
                    {Math.min(count, threshold)}/{threshold}
                  </Text>
                )}
              </Pressable>
            );
          })}
        </View>

        {/* Unlock progress — segmented 4px track, one segment per position,
            fill in that position's color (UnlockBar spec). */}
        <View style={styles.progressWrap}>
          <View style={styles.unlockTrack}>
            {POSITIONS.map((p) => {
              const c = Math.min(progress?.[p] ?? 0, threshold);
              return (
                <View key={p} style={styles.unlockSegment}>
                  <View
                    style={[
                      styles.unlockFill,
                      {
                        width: `${Math.min(100, (c / threshold) * 100)}%`,
                        backgroundColor: posColorFor(p),
                      },
                    ]}
                  />
                </View>
              );
            })}
          </View>
          {currentProgressForPos >= threshold ? (
            <View style={styles.progressTextRow}>
              <Icon name="check" size={14} color={semantic.pos} />
              <Text style={styles.progressText}>{position} rankings established</Text>
            </View>
          ) : (
            <Text style={styles.progressText}>
              <Text style={styles.progressCount}>{currentProgressForPos}</Text>
              {' of '}
              <Text style={styles.progressCount}>{threshold}</Text>
              {` ${position}s ranked`}
            </Text>
          )}
          {/* S4 PRD-02 (ux.outlook_inline_default): the bar states its
              reward BEFORE completion — a counter without a payoff reads
              as busywork. */}
          {unlockCopyOn && !isUnlockedEverywhere ? (
            <Text testID="rank.unlock-payoff" style={styles.progressText}>
              Rank {threshold} per position → trades priced off your board,
              not consensus.
            </Text>
          ) : null}
        </View>

        {/* Instruction — live region so the stepwise coaching line is
            announced as it changes (Android; iOS relies on the card
            state + submit announcements). */}
        <Text style={styles.instruction} accessibilityLiveRegion="polite">
          {submitMutation.isPending
            ? 'Submitting…'
            : selectionOrder.length === 0
            ? 'Tap in order of preference — best first'
            : selectionOrder.length === 1
            ? 'Good — now tap your 2nd choice'
            : selectionOrder.length === 2
            ? speedMode
              ? 'Speed mode — releasing now'
              : 'Last one — tap your 3rd choice'
            : speedMode
            ? 'Submitting…'
            : 'All ranked — confirm when ready'}
        </Text>

        {/* Cards — #243 3-up: three side-by-side mini-cards (approved mock
            trios-three-up-v2.html, Variant A) replace the vertical stack of
            full PlayerCards. The row is one fixed 128pt block (~324pt → 128pt)
            so the whole screen fits the 614pt Rank-stack budget. */}
        {trioEmpty ? (
          /* rookie-draft M2 — the scoped path's typed empty response. A
             position whose rookie pool can't field three candidates is a
             designed state, not a failed fetch, so it must not render as a
             perpetual skeleton or an error. */
          <RookieScopeEmpty
            surface="trios"
            empty={trioEmpty}
            position={position}
            flush
          />
        ) : trioQuery.isLoading || !trio ? (
          // Three skeleton cards keep the page shape stable during the
          // /api/trio round-trip (Mobile #M1). Mirrors the static-fill
          // pattern from MatchesScreen.tsx:253-264 — no animation
          // library, just muted boxes at the real card dimensions.
          <View style={styles.cards}>
            {[0, 1, 2].map((i) => (
              <View key={i} style={styles.skeletonCard}>
                <View style={styles.skeletonChip} />
                <View style={styles.skeletonName} />
                <View style={styles.skeletonMeta} />
              </View>
            ))}
          </View>
        ) : trioQuery.isError ? (
          <View style={styles.centered}>
            <Text style={styles.errorText}>
              {trioQuery.error instanceof Error
                ? trioQuery.error.message
                : 'Could not load next trio'}
            </Text>
            <Button
              variant="ghost"
              compact
              label="Try again"
              onPress={() => trioQuery.refetch()}
            />
          </View>
        ) : (
          <View style={styles.cards}>
            {(['a', 'b', 'c'] as const).map((side) => (
              <View key={`${trio.player_a.id}-${side}`} style={styles.trioCardWrap}>
                <TrioPlayerCard
                  trio={trio}
                  side={side}
                  rank={rankOf(side)}
                  anyRanked={selectionOrder.length > 0}
                  onTap={() => rankSide(side)}
                  onLongPress={() => showInfoSheet(side)}
                  disabled={submitMutation.isPending || isRefetchingTrio}
                  longPressMs={menuOn ? 500 : 400}
                />
                {/* S3 PRD-02 (ux.player_context_menu): visible ⓘ twin for
                    the 500ms-hold info sheet — the accelerator is never the
                    sole path. Bottom-right so it can't collide with the
                    top-right rank badge. 44pt effective target. */}
                {menuOn && gestureEnabled ? (
                  <View style={styles.trioInfoBtn}>
                    <InfoButton
                      testID={`trios.info.${side}`}
                      label={`Player info for ${playerForSide(trio, side).name}`}
                      onPress={() => {
                        track('player_menu_opened', { surface: 'trios' }, 'Trios');
                        showInfoSheet(side);
                      }}
                    />
                  </View>
                ) : null}
              </View>
            ))}
          </View>
        )}

        {/* I AM SPEED toggle — sits ABOVE the secondary action row per spec */}
        <Pressable
          testID="trios.speed-toggle"
          onPress={toggleSpeedMode}
          // S8 PRD-02: persisted on/off setting → switch + checked (the
          // fairness toggle pattern). Behavior copy rides as the hint.
          accessibilityRole="switch"
          accessibilityState={{ checked: speedMode }}
          accessibilityLabel="I am speed — auto-confirm ranking"
          accessibilityHint={
            speedMode
              ? 'Pick your top 2 — the 3rd is auto-ranked and saved'
              : 'Tap all 3, then tap Confirm to save'
          }
          style={({ pressed }) => [
            styles.speedTile,
            speedMode && styles.speedTileOn,
            pressed && { backgroundColor: ink.ink3 },
          ]}
        >
          <View style={styles.speedTileTitleRow}>
            <Icon name="trends" size={14} color={speedMode ? ice.base : chalk.dim} />
            <Text style={[styles.speedTileText, speedMode && styles.speedTileTextOn]}>
              {speedMode ? 'I AM SPEED — ON' : 'I AM SPEED — OFF'}
            </Text>
          </View>
          <Text style={styles.speedTileCaption}>
            {speedMode
              ? 'Pick your top 2 — we auto-rank the 3rd and save.'
              : 'Tap all 3, then tap Confirm to save.'}
          </Text>
        </Pressable>

        {/* Confirm button — appears only after the user has ranked all 3
            cards (in manual mode). Pre-3 we say nothing here; the
            instruction line above the cards already coaches the user. */}
        {!speedMode && selectionOrder.length === 3 && (
          <Button
            variant="primary"
            label="Confirm ranking"
            testID="trios.confirm-btn"
            onPress={() => submitCurrent(selectionOrder)}
            disabled={!trio || submitMutation.isPending}
            style={styles.confirmBtn}
          />
        )}

        {/* Bottom action — single Skip button. "I don't know" was removed
            in alignment with the web client (PR #13, agent #20). Skip is
            now ephemeral: refetches a different trio without persistently
            removing any player from the eligible pool. */}
        <View style={styles.actions}>
          <Button
            variant="secondary"
            label="Skip"
            testID="trios.skip-btn"
            onPress={handleSkipEntireTrio}
            disabled={!trio || isRefetchingTrio}
            style={styles.flex1}
          />
        </View>

        {isUnlockedEverywhere && (
          <View style={styles.unlockedBanner}>
            <View style={styles.bannerTick} />
            <Text style={styles.unlockedText}>
              {/* S4 PRD-02: "unlocked" copy drifted — trades already
                  generate pre-threshold on consensus values. The honest
                  payoff is board-priced trades. */}
              {unlockCopyOn
                ? 'Your board now prices your trades — see the Acquire tab'
                : 'Trade Finder unlocked — check the Acquire tab'}
            </Text>
          </View>
        )}
      </ScrollView>

      {/* Long-press info sheet, gesture-audit flag */}
      {infoSheet && (
        <View style={styles.infoOverlay}>
          <Pressable
            style={styles.infoBackdrop}
            onPress={() => setInfoSheet(null)}
            accessibilityRole="button"
            accessibilityLabel="Close"
          />
          <View style={styles.infoSheet}>
            <View style={styles.grabber} />
            <Text style={styles.infoTitle} accessibilityRole="header">{infoSheet.name}</Text>
            <Text style={styles.infoBody}>{infoSheet.info}</Text>
            <Button
              variant="ghost"
              label="Close"
              onPress={() => setInfoSheet(null)}
              style={styles.infoClose}
            />
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

// ── TrioPlayerCard — #243 3-up mini-card (mock trios-three-up-v2.html,
// Variant A + A2 winner state). Purpose-built for the trio arena: 128pt
// card, badge row, reserved TWO-LINE name box, team · age meta. Replaces
// the full-width PlayerCard stack; pick/submit semantics are untouched —
// rankSide() still runs on tap, only the visuals changed.
// FB-72: the swipe-left-to-skip / swipe-right-to-rank gesture was removed
// at operator request — it collided with scrolling and caused accidental
// skips. Tap-to-rank + the Skip button are the only interactions now.

// Suffix glue (#243 hard rule): join a name suffix to the surname with a
// non-breaking space so "Jr."/"III" can never wrap alone onto line 2 —
// "Marvin Harrison Jr." wraps "Marvin" / "Harrison Jr.", never
// "Marvin Harrison" / "Jr.".
const glueSuffix = (name: string) =>
  name.replace(/ (Jr\.?|Sr\.?|II|III|IV|V)$/, '\u00A0$1');

const RANK_ORDINAL: Record<1 | 2 | 3, string> = { 1: '1st', 2: '2nd', 3: '3rd' };

interface TrioCardProps {
  trio: Trio;
  side: 'a' | 'b' | 'c';
  rank: 1 | 2 | 3 | null;
  anyRanked: boolean;          // ≥1 pick made — un-ranked cards dim (A2 "loser" state)
  onTap: () => void;
  onLongPress?: () => void;
  disabled?: boolean;
  longPressMs: number;
}

function TrioPlayerCard({
  trio,
  side,
  rank,
  anyRanked,
  onTap,
  onLongPress,
  disabled,
  longPressMs,
}: TrioCardProps) {
  const player = side === 'a' ? trio.player_a : side === 'b' ? trio.player_b : trio.player_c;
  const ranked = rank != null;
  const railColor: string | undefined =
    positionColors[String(player.position).toLowerCase() as keyof typeof positionColors];
  const isStdPos =
    player.position === 'QB' ||
    player.position === 'RB' ||
    player.position === 'WR' ||
    player.position === 'TE';
  // #194 — PICK pseudo-assets ride the Player shape with years_experience 0,
  // which is "no experience", not "rookie season": never badge a pick RK.
  const isRookie =
    player.years_experience === 0 && String(player.position) !== 'PICK';
  const meta = [player.team || 'FA', player.age != null ? String(player.age) : null]
    .filter(Boolean)
    .join(' · ');
  // S8 PRD-01 (inert a11y): the signature interaction reads as one button
  // with its rank state — "Josh Allen, QB, Buffalo — ranked 1 of 3".
  const label = `${player.name}, ${player.position}, ${player.team || 'FA'}${
    rank != null ? ` — ranked ${rank} of 3` : ''
  }`;
  return (
    <Pressable
      testID={`trios.card.${side}`}
      onPress={onTap}
      onLongPress={onLongPress}
      disabled={disabled}
      delayLongPress={longPressMs}
      accessible
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={
        rank != null
          ? 'Removes this rank and any later picks'
          : 'Assigns the next rank to this player'
      }
      accessibilityState={{ selected: ranked, disabled: !!disabled }}
      style={({ pressed }) => [
        styles.miniCard,
        ranked && styles.miniCardWinner,
        !ranked && anyRanked && styles.miniCardDimmed,
        pressed && !disabled && { backgroundColor: ink.ink3 },
        disabled && styles.miniCardDisabled,
      ]}
    >
      {/* 3px position-color left rail (Card primitive pattern) */}
      {railColor ? <View style={[styles.miniRail, { backgroundColor: railColor }]} /> : null}

      {/* A2 winner tick — ice square + check, top-right */}
      {ranked && (
        <View style={styles.miniTick}>
          <Icon name="check" size={12} color={ice.on} />
        </View>
      )}

      <View style={styles.miniHead}>
        {isStdPos ? (
          <PositionBadge pos={player.position as 'QB' | 'RB' | 'WR' | 'TE'} />
        ) : (
          <Badge label={String(player.position)} />
        )}
        {isRookie && <RookieBadge />}
      </View>

      {/* Reserved 2-line name box (#243 hard rules): fixed height whether the
          name needs 1 or 2 lines, so all three cards keep identical internal
          rhythm; single-line names TOP-align (RN default in a fixed-height
          box). Whole-word wrap only — simple break strategy, hyphenation off. */}
      <ChalkText
        scale="dense"
        style={styles.miniName}
        numberOfLines={2}
        textBreakStrategy="simple"
        android_hyphenationFrequency="none"
      >
        {glueSuffix(player.name)}
      </ChalkText>

      <ChalkText scale="dense" style={styles.miniMeta} numberOfLines={1}>
        {meta}
      </ChalkText>

      {/* A2 winner label — bottom of the card's reserved slack */}
      {ranked && (
        <ChalkText scale="dense" style={styles.miniRankedLbl} numberOfLines={1}>
          Ranked {RANK_ORDINAL[rank]}
        </ChalkText>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: {
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.md,
  },
  flex1: { flex: 1 },
  streakRow: { alignItems: 'center' },
  streakChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    minHeight: 44, // touch floor
    borderRadius: radii.pill,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
  },
  streakNum: { ...type.data, color: chalk.base },
  streakLabel: { ...type.bodySm, color: chalk.dim },
  modeHint: {
    ...type.bodySm,
    color: chalk.faint,
    textAlign: 'center',
    marginTop: -space.xs,
  },
  modeHintDim: { color: chalk.dim },
  // S3 PRD-02 — trio card wrapper hosts the absolute ⓘ twin.
  // #243: each wrap is one third of the 3-up row.
  trioCardWrap: { flex: 1, position: 'relative' },
  trioInfoBtn: {
    position: 'absolute',
    right: space.sm,
    bottom: space.sm,
  },

  // Segmented control: 1px line-bordered group, radii.sm; active segment =
  // ink3 fill + 2px underline in that position's color (PositionTabs spec).
  switcher: {
    flexDirection: 'row',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.line,
    overflow: 'hidden',
  },
  switcherBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: space.sm,
    minHeight: 48,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  switcherBtnDivider: {
    borderLeftWidth: 1,
    borderLeftColor: ink.line,
  },
  switcherBtnActive: { backgroundColor: ink.ink3 },
  switcherText: { ...type.label, color: chalk.dim },
  switcherTextActive: { color: chalk.base },
  switcherCount: { ...type.data, color: chalk.dim, marginTop: 2 },
  switcherCountActive: { color: chalk.base },

  // Unlock progress: segmented 4px track, square ends, per-position fills,
  // 1px line gaps between segments (UnlockBar spec).
  progressWrap: { gap: space.sm - 2 },
  unlockTrack: {
    flexDirection: 'row',
    height: 4,
    backgroundColor: ink.line,
    gap: 1,
  },
  unlockSegment: {
    flex: 1,
    height: 4,
    backgroundColor: ink.ink3,
    overflow: 'hidden',
  },
  unlockFill: { height: 4 },
  progressTextRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
  },
  progressText: { ...type.bodySm, color: chalk.dim, textAlign: 'center' },
  progressCount: { ...type.data, color: chalk.base },

  instruction: {
    ...type.body,
    textAlign: 'center',
    paddingVertical: space.sm,
  },
  // #243 3-up: the three mini-cards sit side by side in one 128pt row
  // (mock trios-three-up-v2.html Variant A; was a ~324pt vertical stack).
  cards: { flexDirection: 'row', gap: space.sm },
  centered: {
    paddingVertical: space.xxl,
    alignItems: 'center',
    gap: space.md,
  },

  // ── #243 mini-card (Variant A, 115×128pt at 393pt-wide devices) ──────
  miniCard: {
    height: 128,
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: space.sm,
    gap: space.xs,
    position: 'relative',
    overflow: 'hidden',
  },
  // A2 winner state: ice border + surface step; losers dim.
  miniCardWinner: {
    borderColor: ice.base,
    backgroundColor: ink.ink2,
  },
  miniCardDimmed: { opacity: 0.55 },
  miniCardDisabled: { opacity: 0.45 },
  miniRail: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 3,
  },
  miniHead: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.xs,
    paddingLeft: 5, // 3px rail + 2px inset (mock .minihead)
  },
  // Reserved TWO-LINE name box — type.bodySm metrics (13/18) at uiSemi
  // weight; height fixes exactly 2 lines so a 1-line name top-aligns and
  // all three cards stay equal height (#243 hard rule).
  miniName: {
    fontFamily: fonts.uiSemi,
    fontSize: 13,
    lineHeight: 18,
    color: chalk.base,
    height: 36,
    paddingLeft: 5,
  },
  // 11px floor (dense-row precedent: PlayerCard.denseTeam).
  miniMeta: {
    fontFamily: fonts.ui,
    fontSize: 11,
    lineHeight: 14,
    color: chalk.dim,
    paddingLeft: 5,
  },
  miniTick: {
    position: 'absolute',
    top: space.sm - 2,
    right: space.sm - 2,
    width: 20,
    height: 20,
    borderRadius: radii.xs,
    backgroundColor: ice.base,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1,
  },
  miniRankedLbl: {
    ...type.label,
    color: ice.base,
    position: 'absolute',
    bottom: space.sm - 2,
    left: space.sm - 2,
    right: space.sm - 2,
  },

  // Skeleton tiles — match the real mini-card outer shape (ink1 surface,
  // hairline border, radii.md, 128pt) so the layout doesn't shift when
  // the /api/trio response lands. Static fills, no shimmer (consistent
  // with MatchesScreen skeleton — see Mobile #M1).
  skeletonCard: {
    flex: 1,
    height: 128,
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: space.sm,
    gap: space.sm,
  },
  skeletonChip: {
    width: 32,
    height: 18,
    borderRadius: radii.xs,
    backgroundColor: ink.ink3,
  },
  skeletonName: {
    width: '90%',
    height: 14,
    borderRadius: radii.xs,
    backgroundColor: ink.ink3,
  },
  skeletonMeta: {
    width: '60%',
    height: 10,
    borderRadius: radii.xs,
    backgroundColor: ink.ink3,
  },
  errorText: { ...type.bodySm, color: semantic.neg, textAlign: 'center' },

  speedTile: {
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.md,
    paddingVertical: space.md,
    paddingHorizontal: space.lg,
    marginTop: space.lg,
    alignItems: 'center',
    minHeight: 44, // touch floor
    gap: space.xs,
  },
  speedTileOn: {
    borderColor: ice.base,
  },
  speedTileTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm - 2,
  },
  speedTileText: { ...type.label, color: chalk.base },
  speedTileTextOn: { color: ice.base },
  speedTileCaption: {
    ...type.bodySm,
    color: chalk.dim,
    textAlign: 'center',
  },
  confirmBtn: { marginTop: space.sm },

  actions: {
    flexDirection: 'row',
    gap: space.md,
    marginTop: space.lg,
  },

  // Banner spec: ink2 surface, hairline, ice tick + body-sm.
  unlockedBanner: {
    marginTop: space.lg,
    padding: space.md,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
  },
  bannerTick: { width: 3, height: 14, backgroundColor: ice.base },
  unlockedText: { ...type.bodySm, color: chalk.base },

  infoOverlay: {
    position: 'absolute',
    inset: 0 as any,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 40,
    justifyContent: 'flex-end',
  },
  infoBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: scrim,
  },
  infoSheet: {
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.xl,
    paddingTop: space.md,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  infoTitle: { ...type.title },
  infoBody: {
    ...type.bodySm,
    color: chalk.dim,
    lineHeight: 22,
  },
  infoClose: { marginTop: space.md },
});
