import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  ScrollView,
  Dimensions,
  Modal,
  Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  runOnJS,
  Easing,
} from 'react-native-reanimated';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { haptics } from '../utils/haptics';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import TradeCardComp from '../components/TradeCard';
import Toast from '../components/Toast';
import OutlookSheet from '../components/OutlookSheet';
import LeaguePill from '../components/LeaguePill';
import LeagueSwitcherSheet from '../components/LeagueSwitcherSheet';
import QueueChip from '../components/QueueChip';
import {
  generateTrades,
  getTradeStatus,
  swipeTrade,
  getLikedTrades,
} from '../api/trades';
import {
  getLeaguePreferences,
  saveLeaguePreferences,
  getNewPartners,
  type Outlook,
} from '../api/league';
import { useSession } from '../state/useSession';
import { useTradeQueue } from '../state/useTradeQueue';
import { useFlag } from '../state/useFeatureFlags';
import NewPartnersBanner from '../components/NewPartnersBanner';
import type { Player, TradeCard, TradeJobSnapshot } from '../shared/types';

const SCREEN_W = Dimensions.get('window').width;
const SWIPE_THRESHOLD = 120;

// Stable empty-array reference so the zustand selector doesn't return a
// brand-new `[]` on every render (which would trigger an infinite re-render
// loop in React via reference inequality).
const EMPTY_QUEUE: never[] = [];

// Persisted user pref: is the fairness filter on (recommended trades must
// be reasonably balanced in consensus value) or off (recommend purely by
// ranking mismatch between owners)?
const FAIRNESS_PREF_KEY = 'ftf:trades:fairness_on';
// When fairness ON, ask the backend for balanced trades — same default the
// old slider opened to. When OFF, ask for the broadest pool the backend
// will return so client-side sort-by-mismatch sees real candidates.
const FAIRNESS_ON_THRESHOLD = 0.75;
const FAIRNESS_OFF_THRESHOLD = 0.5;

export default function TradesScreen({ navigation }: any) {
  const queryClient = useQueryClient();
  const league = useSession((s) => s.league);
  const switching = useSession((s) => s.switching);
  const user = useSession((s) => s.user);
  // B3 — Portfolio is only meaningful when the user has 2+ leagues. The
  // sub-route pill at the top of this screen hides itself otherwise.
  const leagues = useSession((s) => s.leagues);
  const showPortfolioPill = (leagues?.length || 0) >= 2;
  const leagueId = league?.league_id || null;
  const userId   = user?.user_id || '';

  // B7 — new-partners banner. Flag-gated; query only fires when the flag
  // is on AND we have both a league and a user (the banner's dismissal
  // key depends on both).
  const newPartnersFlag = useFlag('trades.new_partners_alerts');
  const newPartnersQuery = useQuery({
    queryKey: ['new-partners', leagueId, userId],
    queryFn:  () => getNewPartners(leagueId!),
    enabled:  !!leagueId && !!userId && newPartnersFlag,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
  // Trade-fairness toggle. ON = backend filters to balanced trades and
  // sorts by composite_score (current behavior). OFF = broaden the
  // backend filter to its loosest (0.5) and re-sort the deck client-side
  // by ranking-mismatch magnitude (TradeCard.match_score, which is the
  // server's mismatch_score: how big the ELO gap between owners is on
  // the swapped players). Persisted across sessions via AsyncStorage.
  const [fairnessOn, setFairnessOn] = useState(true);
  const [deck, setDeck] = useState<TradeCard[]>([]);
  const [deckIdx, setDeckIdx] = useState(0);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  const [outlookOpen, setOutlookOpen] = useState(false);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [queueSheetOpen, setQueueSheetOpen] = useState(false);
  const [slowSwitch, setSlowSwitch] = useState(false);

  // Render free-tier cold starts run 30–60s. Hold the friendly default for
  // the first 4s so warm switches never show the alarming "waking up" copy.
  useEffect(() => {
    if (!switching) {
      setSlowSwitch(false);
      return;
    }
    const t = setTimeout(() => setSlowSwitch(true), 4000);
    return () => clearTimeout(t);
  }, [switching]);

  // Trade queue (Bundle 5 — flag `trades.queue_2k`). When the flag is off,
  // the queue UI is hidden but the store stays functional; this keeps the
  // hook-call order stable so flag flips don't trip React's rules-of-hooks.
  const queueEnabled = useFlag('trades.queue_2k');
  const hydrateQueue  = useTradeQueue((s) => s.hydrate);
  const enqueueTrade  = useTradeQueue((s) => s.enqueue);
  const dequeueTrade  = useTradeQueue((s) => s.dequeue);
  const sendAllTrades = useTradeQueue((s) => s.sendAll);
  // Subscribe to just the slice for the active league so other-league
  // mutations don't trigger re-renders here.
  const queuedTrades = useTradeQueue(
    (s) => (leagueId ? s.byLeague[leagueId] || EMPTY_QUEUE : EMPTY_QUEUE),
  );

  // Re-hydrate when the signed-in user changes (incl. on first mount once
  // useSession.bootstrap finishes). Keyed on `userId` so a sign-out/sign-in
  // cycle picks up the new user's blob.
  useEffect(() => {
    if (!queueEnabled) return;
    void hydrateQueue();
  }, [userId, queueEnabled, hydrateQueue]);

  // Effective threshold sent to the backend. OFF still passes a (low)
  // value rather than dropping the field so the cache key on the server
  // stays stable — `_trade_job_is_fresh` keys on fairness_threshold.
  const effectiveFairness = fairnessOn ? FAIRNESS_ON_THRESHOLD : FAIRNESS_OFF_THRESHOLD;

  // Hydrate the persisted toggle on mount. Default is ON if nothing's
  // stored — matches the prior slider's 0.75 starting position.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(FAIRNESS_PREF_KEY);
        if (cancelled) return;
        if (raw === 'off') setFairnessOn(false);
        else if (raw === 'on') setFairnessOn(true);
      } catch {
        /* AsyncStorage unavailable — fall back to default ON */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  function handleToggleFairness(next: boolean) {
    setFairnessOn(next);
    // Fire-and-forget persistence; a write failure shouldn't block the UI.
    AsyncStorage.setItem(FAIRNESS_PREF_KEY, next ? 'on' : 'off').catch(() => {});
    // Toggling the threshold invalidates the current deck — the next
    // Find-a-Trade tap should request a fresh set under the new mode.
    // Also avoids visual shuffle if streaming cards were still arriving.
    setDeck([]);
    setDeckIdx(0);
    setJob(null);
  }

  // Preferences — open outlook sheet the first time the user lands here
  // without an outlook set.
  const prefsQuery = useQuery({
    queryKey: ['league-prefs', leagueId],
    queryFn: () => getLeaguePreferences(leagueId!),
    enabled: !!leagueId,
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });

  useEffect(() => {
    if (prefsQuery.data && !prefsQuery.data.team_outlook) {
      setOutlookOpen(true);
    }
  }, [prefsQuery.data]);

  // ── Find-a-Trade: streaming job snapshot ─────────────────────────────
  // The backend runs generation in a background thread and we poll for
  // results. The job snapshot drives both the deck (cards stream in) and
  // the progress strip ("4/11 opponents searched").
  const [job, setJob] = useState<TradeJobSnapshot | null>(null);

  const generateMutation = useMutation({
    mutationFn: () =>
      generateTrades({
        league_id: leagueId!,
        fairness_threshold: effectiveFairness,
      }),
    onSuccess: (snapshot) => {
      setJob(snapshot);
      // For instant cache-hit responses (status === 'complete') the deck
      // populates immediately via the snapshot effect below. For 'running'
      // responses the polling effect takes over.
      if (snapshot.status === 'complete' && snapshot.cards.length === 0) {
        setToast({
          msg: fairnessOn
            ? 'No fair trades found. Try turning Trade fairness off.'
            : 'No trades found. Rank more players or try again later.',
          tone: 'warn',
        });
      }
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Generate failed', tone: 'warn' });
    },
  });

  // Poll while a job is running. Self-scheduling setTimeout loop with
  // exponential backoff (INIT-13): starts at 800ms, resets on progress,
  // backs off to 4000ms when the backend isn't advancing.
  //
  // Failure handling: after MAX_POLL_FAILURES consecutive errors we
  // surface a toast and clear the local job so the UI returns to its
  // pre-tap state. The server-side worker keeps running so the next tap
  // can hit the warm cache.
  //
  // Shallow-equal guard (FR-3 / INIT-11a FR-W2-5): skip setJob when
  // nothing the UI reads has actually changed, avoiding a re-render on
  // every poll tick even when the job snapshot is identical.
  useEffect(() => {
    if (!job || job.status !== 'running' || !job.job_id) return;
    let cancelled = false;
    let failures = 0;
    const MAX_POLL_FAILURES = 4;
    let intervalMs = 800;
    let prevOpponentsDone = job.opponents_done ?? 0;

    const tick = async () => {
      if (cancelled) return;
      try {
        const next = await getTradeStatus(job.job_id);
        if (cancelled) return;
        failures = 0;

        // Shallow-equal guard: skip setState if nothing the UI reads has changed.
        const changed = (
          next.status !== job.status ||
          (next.opponents_done ?? 0) !== (job.opponents_done ?? 0) ||
          (next.opponents_total ?? 0) !== (job.opponents_total ?? 0) ||
          next.cards.length !== job.cards.length
        );
        if (changed) setJob(next);

        // Backoff: reset on progress, increase on no-change.
        if ((next.opponents_done ?? 0) > prevOpponentsDone) {
          intervalMs = 800;
          prevOpponentsDone = next.opponents_done ?? 0;
        } else {
          intervalMs = Math.min(Math.round(intervalMs * 1.5), 4000);
        }

        // Add ±10% jitter to spread polls and avoid thundering-herd.
        const jitter = intervalMs * 0.1 * (Math.random() * 2 - 1);
        const nextDelay = Math.round(intervalMs + jitter);

        if (!cancelled && next.status === 'running') {
          setTimeout(tick, nextDelay);
        }
      } catch {
        if (cancelled) return;
        failures += 1;
        if (failures >= MAX_POLL_FAILURES) {
          setToast({
            msg: 'Network hiccup — try Find a Trade again in a moment',
            tone: 'warn',
          });
          setJob(null);
        } else if (!cancelled) {
          setTimeout(tick, intervalMs);
        }
      }
    };

    const firstTimer = setTimeout(tick, intervalMs);
    return () => {
      cancelled = true;
      clearTimeout(firstTimer);
    };
  }, [job?.job_id, job?.status]);

  // Deck maintenance: append new cards as the snapshot grows, dedup by
  // trade_id so re-rendering doesn't duplicate. Don't reset the index —
  // the user may already be swiping on early cards.
  //
  // Deps note: depend on cards.length (and status), not the array
  // reference. Each poll returns a fresh array even when content hasn't
  // changed; using the array ref triggers a no-op re-render every 1.5s.
  // Length grows monotonically while a job is running, so any actual
  // growth still fires the effect. The rare same-length-different-
  // content case (e.g. backend resort after the last opponent) coincides
  // with a status flip from 'running' → 'complete', which is included.
  useEffect(() => {
    if (!job) return;
    setDeck((prev) => {
      const seen = new Set(prev.map((c) => c.trade_id));
      const fresh = job.cards.filter((c) => !seen.has(c.trade_id));
      return fresh.length === 0 ? prev : [...prev, ...fresh];
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.cards.length, job?.status]);

  // When the user switches leagues, drop the local deck/job so the next
  // "Find a Trade" tap kicks off a fresh job instead of streaming into
  // stale state. (The fairness toggle handles its own reset inline.)
  useEffect(() => {
    setDeck([]);
    setDeckIdx(0);
    setJob(null);
  }, [leagueId]);

  const swipeMutation = useMutation({
    mutationFn: ({ tradeId, decision }: { tradeId: string; decision: 'like' | 'pass' }) =>
      swipeTrade(tradeId, decision),
    onMutate: ({ tradeId }) => {
      // Snapshot the index this card was at when the swipe fired. On
      // error we use this to decide whether to rewind the deck — only
      // safe if the user hasn't already swiped past it. Capturing the
      // index inside the deck (rather than the position in `sortedDeck`)
      // keeps the rollback correct under fairness re-sorts that happen
      // between the swipe and the error.
      const dispatchedIdx = deck.findIndex((c) => c.trade_id === tradeId);
      return { tradeId, dispatchedIdx };
    },
    onSuccess: (_, vars) => {
      if (vars.decision === 'like') {
        // Liked-trades count is per-league (backend filters by session). Use a
        // league-scoped key so switching leagues doesn't show a stale count.
        queryClient.invalidateQueries({ queryKey: ['liked-trades', leagueId] });
      }
    },
    onError: (_err, _vars, ctx) => {
      // Silent-deck-advance was the bug (api-layer review onError + silent
      // bugs sweep). `advance()` bumps deckIdx synchronously regardless of
      // mutation outcome; on a network/5xx failure the deck has already
      // moved on and the user has no signal the swipe didn't land.
      //
      // Rewind ONLY when the failed card is exactly one swipe behind the
      // current top — i.e. the user hasn't already swiped past it. If
      // they have, jumping the deck backwards would be more disorienting
      // than just toasting; same logic the api-layer review describes.
      // Also refetch the liked-trades count in case the optimistic
      // `like` invalidation has populated a stale entry; idempotent
      // when no like was in flight.
      setDeckIdx((cur) => {
        const tradeId = ctx?.tradeId;
        if (!tradeId) return cur;
        // The card that was at the top when we swiped lives at cur-1
        // post-advance. If sortedDeck no longer has it there, the user
        // has swiped further or the deck was re-sorted — don't rewind.
        const prevCard = sortedDeck[cur - 1];
        if (prevCard && prevCard.trade_id === tradeId) return cur - 1;
        return cur;
      });
      queryClient.invalidateQueries({ queryKey: ['liked-trades', leagueId] });
      setToast({ msg: "Swipe didn't save — try again.", tone: 'warn' });
    },
  });

  const likedQuery = useQuery({
    queryKey: ['liked-trades', leagueId],
    queryFn: getLikedTrades,
    enabled: !!leagueId,
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  // When Trade fairness is OFF, the user wants trades ranked purely by
  // the ELO mismatch between owners — bigger gap = better trade. The
  // backend's `mismatch_score` (normalized to `TradeCard.match_score`)
  // is exactly that signal: opp_surplus + user_surplus across the swap.
  // When ON, the backend already sorts by composite_score (fairness +
  // mismatch + tier priority) and we leave that order alone.
  const sortedDeck = useMemo(() => {
    if (fairnessOn) return deck;
    return [...deck].sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
  }, [deck, fairnessOn]);

  const topCard = sortedDeck[deckIdx];
  const nextCard = sortedDeck[deckIdx + 1];

  function advance(decision: 'like' | 'pass') {
    if (!topCard) return;
    swipeMutation.mutate({ tradeId: topCard.trade_id, decision });
    setDeckIdx((i) => i + 1);
    if (decision === 'like') {
      haptics.success();
      setToast({ msg: 'Liked ✓', tone: 'success' });
    } else {
      haptics.swipe();
    }
  }

  // ── Queue helpers (flag `trades.queue_2k`) ─────────────────────────
  const isQueued = (tradeId: string): boolean =>
    queuedTrades.some((q) => q.trade_id === tradeId);

  function handleQueue(card: TradeCard) {
    if (!leagueId) return;
    // Re-tapping Queue on an already-queued card dequeues it (matches the
    // web's toggle behavior). Otherwise capture a light snapshot of the
    // card metadata needed for the deep-link + chip rendering.
    if (isQueued(card.trade_id)) {
      dequeueTrade(leagueId, card.trade_id);
      setToast({ msg: 'Removed from queue', tone: 'success' });
      return;
    }
    enqueueTrade(leagueId, {
      trade_id:        card.trade_id,
      league_id:       card.league_id || leagueId,
      sleeper_url:     buildSleeperUrl(card),
      give_summary:    summarizePlayers(card.give_players),
      receive_summary: summarizePlayers(card.receive_players),
      queued_at:       new Date().toISOString(),
    });
    haptics.swipe();
    setToast({ msg: `Added to queue (${queuedTrades.length + 1})`, tone: 'success' });
  }

  async function handleSendAll() {
    if (!leagueId) return;
    setQueueSheetOpen(false);
    await sendAllTrades(leagueId);
    setToast({ msg: 'Opened queued trades on Sleeper', tone: 'success' });
  }

  async function handleOutlookSubmit(
    outlook: NonNullable<Outlook>,
    acquire: string[],
    away: string[],
  ) {
    if (!leagueId) return;
    await saveLeaguePreferences(leagueId, {
      team_outlook: outlook,
      acquire_positions: acquire,
      trade_away_positions: away,
    });
    queryClient.invalidateQueries({ queryKey: ['league-prefs', leagueId] });
    setToast({ msg: 'Outlook saved', tone: 'success' });
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      <OutlookSheet
        visible={outlookOpen}
        initial={prefsQuery.data?.team_outlook}
        onClose={() => setOutlookOpen(false)}
        onSubmit={handleOutlookSubmit}
      />

      <LeagueSwitcherSheet
        visible={switcherOpen}
        onClose={() => setSwitcherOpen(false)}
        // No onSwitched callback — the [leagueId] useEffect above already
        // resets deck/job state when zustand's league slice changes, and
        // league-prefs refetches automatically via its query key.
      />

      {/* Full-screen overlay while a league swap is in flight. sessionInit
          can take 5–10s on Render's free tier; without this the user can
          still tap controls and trigger requests against the wrong league. */}
      {switching ? (
        <View style={styles.switchingOverlay} pointerEvents="auto">
          <ActivityIndicator color={colors.accent} size="large" />
          <Text style={styles.switchingText}>
            {slowSwitch
              ? 'Waking up server — first request after a quiet period can take 30s.'
              : 'Switching league…'}
          </Text>
        </View>
      ) : null}

      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        scrollEnabled={!topCard || !generateMutation.isPending}
      >
        {/* B7 — new-partners alert. Banner self-dismisses via AsyncStorage
            keyed on the latest partner; renders null when the flag is off
            (query is gated upstream) or there are no new partners. */}
        {newPartnersFlag && leagueId && userId && (newPartnersQuery.data?.partners?.length ?? 0) > 0 ? (
          <NewPartnersBanner
            partners={newPartnersQuery.data!.partners}
            userId={userId}
            leagueId={leagueId}
          />
        ) : null}

        {/* B3 — Sub-route pills. Trades is the active screen here;
            Portfolio is a sibling in the Trades stack and only shows
            when the user has 2+ connected leagues. */}
        {showPortfolioPill ? (
          <View style={styles.subnavRow}>
            <View style={[styles.subnavPill, styles.subnavPillActive]}>
              <Text style={[styles.subnavPillText, styles.subnavPillTextActive]}>
                Trades
              </Text>
            </View>
            <Pressable
              onPress={() => navigation?.navigate?.('Portfolio')}
              style={({ pressed }) => [
                styles.subnavPill,
                pressed && { opacity: 0.7 },
              ]}
            >
              <Text style={styles.subnavPillText}>Portfolio</Text>
            </Pressable>
          </View>
        ) : null}

        {/* League selector pill — opens LeagueSwitcherSheet on tap. */}
        <LeaguePill
          label="Trading in"
          onPress={() => setSwitcherOpen(true)}
        />

        <View style={styles.controlCard}>
          <View style={styles.controlRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.controlLabel}>Outlook</Text>
              <Text style={styles.controlValue}>
                {prefsQuery.data?.team_outlook
                  ? cap(prefsQuery.data.team_outlook)
                  : 'Not set'}
              </Text>
            </View>
            <Pressable
              style={({ pressed }) => [styles.editBtn, pressed && { opacity: 0.7 }]}
              onPress={() => setOutlookOpen(true)}
            >
              <Text style={styles.editBtnText}>Edit</Text>
            </Pressable>
          </View>

          {/* Trade-fairness toggle. ON: backend filters to balanced
              trades and sorts by composite_score (fairness-weighted).
              OFF: broaden the backend filter to its loosest and re-sort
              the deck client-side by ranking mismatch (the ELO gap
              between owners on the swapped players). */}
          <View style={styles.fairnessRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.fairnessLabel}>Trade fairness</Text>
              <Text style={styles.fairnessHint}>
                {fairnessOn
                  ? 'Recommend balanced trades'
                  : 'Rank by ranking mismatch only'}
              </Text>
            </View>
            <Switch
              value={fairnessOn}
              onValueChange={handleToggleFairness}
              trackColor={{ false: colors.border, true: colors.accent }}
              thumbColor="#fff"
              ios_backgroundColor={colors.border}
            />
          </View>

          {/* Find-a-Trade button. While a job is running, the button is
              disabled — the progress strip below acts as the live signal.
              `generateMutation.isPending` is only true during the brief
              POST round-trip; after that, status flows through `job`. */}
          <Pressable
            disabled={!leagueId || generateMutation.isPending || job?.status === 'running'}
            onPress={() => generateMutation.mutate()}
            style={({ pressed }) => [
              styles.findBtn,
              pressed && { opacity: 0.85 },
              (!leagueId || generateMutation.isPending || job?.status === 'running') && { opacity: 0.5 },
            ]}
          >
            {generateMutation.isPending ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.findBtnText}>
                {deck.length > 0 && job?.status === 'complete' ? '✨ Find more trades' : '✨ Find a Trade'}
              </Text>
            )}
          </Pressable>

          {/* Progress strip — visible only during a running job. Cards are
              streaming into the deck above; this just narrates the work. */}
          {job?.status === 'running' && (
            <View style={styles.progressStrip}>
              <View style={styles.progressInfo}>
                <ActivityIndicator color={colors.accent} size="small" />
                <Text style={styles.progressText}>
                  Searching… {job.opponents_done}/{job.opponents_total || '?'} opponents
                  {job.cards.length > 0 ? `  ·  ${job.cards.length} trade${job.cards.length === 1 ? '' : 's'}` : ''}
                </Text>
              </View>
              {/* "Hide", not "Stop": the server-side worker keeps running
                  so its results land in the warm cache for the next tap.
                  We just dismiss the in-progress UI on the client. */}
              <Pressable
                onPress={() => setJob(null)}
                style={({ pressed }) => [styles.stopBtn, pressed && { opacity: 0.6 }]}
                hitSlop={8}
              >
                <Text style={styles.stopBtnText}>Hide</Text>
              </Pressable>
            </View>
          )}

          {likedQuery.data && likedQuery.data.liked_count > 0 && (
            <Text style={styles.likedCount}>
              ❤ {likedQuery.data.liked_count} liked trade
              {likedQuery.data.liked_count === 1 ? '' : 's'} awaiting their swipe
            </Text>
          )}
        </View>

        <View style={styles.deckWrap}>
          {topCard ? (
            <>
              {/* Peek of the next card behind the top one */}
              {nextCard && (
                <View style={[styles.cardStack, styles.cardBehind]}>
                  <TradeCardComp data={nextCard} />
                </View>
              )}
              <SwipableTopCard
                key={topCard.trade_id}
                card={topCard}
                onLike={() => advance('like')}
                onPass={() => advance('pass')}
              />
              {/* Queue action — Pass / Interested are driven by swipe
                  gestures on the top card; Queue is a third option that
                  stashes the trade for "Send All" later. Flag-gated so the
                  feature can be tested before broad rollout. */}
              {queueEnabled && leagueId ? (
                <Pressable
                  onPress={() => handleQueue(topCard)}
                  style={({ pressed }) => [
                    styles.queueBtn,
                    isQueued(topCard.trade_id) && styles.queueBtnQueued,
                    pressed && { opacity: 0.7 },
                  ]}
                >
                  <Text
                    style={[
                      styles.queueBtnText,
                      isQueued(topCard.trade_id) && styles.queueBtnTextQueued,
                    ]}
                  >
                    {isQueued(topCard.trade_id) ? '✓ Queued' : '+ Queue'}
                  </Text>
                </Pressable>
              ) : null}
              {/* ✓ / ✗ disposition buttons — same outcome as swiping right/left.
                  Both wire to advance() so deck-advance, haptics, and the API
                  call are identical to the swipe path. Disabled while a swipe
                  mutation is in flight to prevent double-firing. */}
              <View style={styles.dispositionRow}>
                <Pressable
                  onPress={() => advance('pass')}
                  disabled={swipeMutation.isPending}
                  style={({ pressed }) => [
                    styles.dispositionBtn,
                    styles.dispositionBtnPass,
                    pressed && { opacity: 0.7 },
                    swipeMutation.isPending && { opacity: 0.4 },
                  ]}
                  accessibilityLabel="Pass on this trade"
                  accessibilityRole="button"
                >
                  <Text style={[styles.dispositionBtnText, styles.dispositionBtnTextPass]}>✗</Text>
                </Pressable>
                <Pressable
                  onPress={() => advance('like')}
                  disabled={swipeMutation.isPending}
                  style={({ pressed }) => [
                    styles.dispositionBtn,
                    styles.dispositionBtnLike,
                    pressed && { opacity: 0.7 },
                    swipeMutation.isPending && { opacity: 0.4 },
                  ]}
                  accessibilityLabel="Accept this trade"
                  accessibilityRole="button"
                >
                  <Text style={[styles.dispositionBtnText, styles.dispositionBtnTextLike]}>✓</Text>
                </Pressable>
              </View>
              <Text style={styles.deckHint}>
                Swipe right to like · Swipe left to pass
              </Text>
            </>
          ) : generateMutation.isPending || job?.status === 'running' ? (
            // Job is running but no cards have arrived yet (first ~3s of
            // the first opponent). Show a placeholder so the deck doesn't
            // look broken — the progress strip above narrates state.
            <View style={styles.emptyCard}>
              <ActivityIndicator color={colors.accent} />
              <Text style={[styles.emptyTitle, { marginTop: spacing.sm }]}>
                Looking for trades…
              </Text>
              <Text style={styles.emptyBody}>
                Cards will appear here as they're found. First few should land within a few seconds.
              </Text>
            </View>
          ) : deck.length > 0 ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>That's all for now ✓</Text>
              <Text style={styles.emptyBody}>
                You've swiped on every generated trade. Rank more players or
                invite leaguemates to unlock more.
              </Text>
            </View>
          ) : (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>Hit "Find a Trade" to start</Text>
              <Text style={styles.emptyBody}>
                We'll pull trade ideas from your league and show them one at a time.
              </Text>
            </View>
          )}
        </View>
      </ScrollView>

      {/* Queue footer bar — anchored above the bottom tab nav. Tap the
          left side to expand the queue sheet; tap "Send All" to fire the
          staggered Sleeper deep-links and clear. Flag-gated. */}
      {queueEnabled && queuedTrades.length > 0 ? (
        <View style={styles.queueFooter}>
          <Pressable
            onPress={() => setQueueSheetOpen(true)}
            style={({ pressed }) => [styles.queueFooterTap, pressed && { opacity: 0.7 }]}
          >
            <Text style={styles.queueFooterCount}>{queuedTrades.length}</Text>
            <Text style={styles.queueFooterLabel}>
              queued · tap to review
            </Text>
          </Pressable>
          <Pressable
            onPress={handleSendAll}
            style={({ pressed }) => [styles.queueSendBtn, pressed && { opacity: 0.85 }]}
          >
            <Text style={styles.queueSendText}>Send All →</Text>
          </Pressable>
        </View>
      ) : null}

      {/* Queue bottom-sheet — lists each queued trade with × dequeue. */}
      <Modal
        visible={queueSheetOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setQueueSheetOpen(false)}
      >
        <Pressable
          style={styles.queueBackdrop}
          onPress={() => setQueueSheetOpen(false)}
        />
        <View style={styles.queueSheet}>
          <View style={styles.queueHandle} />
          <View style={styles.queueSheetHeader}>
            <Text style={styles.queueSheetTitle}>Trade queue</Text>
            <Text style={styles.queueSheetSub}>
              {queuedTrades.length} queued · "Send All" opens each on Sleeper
            </Text>
          </View>

          <ScrollView style={styles.queueSheetScroll} contentContainerStyle={{ gap: spacing.sm }}>
            {queuedTrades.length === 0 ? (
              <Text style={styles.queueEmpty}>
                Queue is empty. Tap "+ Queue" on any trade card to stack it here.
              </Text>
            ) : (
              queuedTrades.map((q) => (
                <QueueChip
                  key={q.trade_id}
                  trade={q}
                  onRemove={() => leagueId && dequeueTrade(leagueId, q.trade_id)}
                />
              ))
            )}
          </ScrollView>

          <View style={styles.queueSheetActions}>
            <Pressable
              onPress={() => setQueueSheetOpen(false)}
              style={({ pressed }) => [styles.queueSheetCancel, pressed && { opacity: 0.6 }]}
            >
              <Text style={styles.queueSheetCancelText}>Close</Text>
            </Pressable>
            <Pressable
              disabled={queuedTrades.length === 0}
              onPress={handleSendAll}
              style={({ pressed }) => [
                styles.queueSheetSend,
                pressed && { opacity: 0.85 },
                queuedTrades.length === 0 && { opacity: 0.4 },
              ]}
            >
              <Text style={styles.queueSheetSendText}>Send All →</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

// Sleeper trade-propose URL. Mirrors web's `_buildSleeperTradeUrl`:
//   https://sleeper.com/leagues/<league_id>/trade?add_receiver_id=...
//   &give_player_id=...&add_player_id=...
// Sleeper doesn't publish a programmatic trade endpoint; this deep-link is
// the pragmatic v1 and lands the user on the league's trade surface even
// if the params are ignored.
function buildSleeperUrl(card: TradeCard): string {
  const params = new URLSearchParams();
  if (card.opponent_user_id) params.append('add_receiver_id', card.opponent_user_id);
  for (const id of card.give_player_ids || []) {
    if (id) params.append('give_player_id', id);
  }
  for (const id of card.receive_player_ids || []) {
    if (id) params.append('add_player_id', id);
  }
  const qs = params.toString();
  return `https://sleeper.com/leagues/${card.league_id}/trade${qs ? `?${qs}` : ''}`;
}

// "RB Bijan Robinson + WR DJ Moore" style summary for the queue chip.
// Caps at two names plus a "+N" suffix so a 3+ player side doesn't blow
// out the chip width.
function summarizePlayers(players: Player[]): string {
  if (!Array.isArray(players) || players.length === 0) return '?';
  const first = players.slice(0, 2).map((p) => {
    const pos = p.position ? `${p.position} ` : '';
    return `${pos}${p.name}`;
  });
  if (players.length <= 2) return first.join(' + ');
  return `${first.join(' + ')} +${players.length - 2}`;
}

// ── SwipableTopCard — Tinder-style gesture on the top card only ─────
interface SwipableProps {
  card: TradeCard;
  onLike: () => void;
  onPass: () => void;
}

function SwipableTopCard({ card, onLike, onPass }: SwipableProps) {
  const translateX = useSharedValue(0);

  const pan = useMemo(
    () =>
      Gesture.Pan()
        .activeOffsetX([-12, 12])
        .failOffsetY([-30, 30])
        .onUpdate((e) => {
          translateX.value = e.translationX;
        })
        .onEnd((e) => {
          if (e.translationX > SWIPE_THRESHOLD && e.velocityX > 200) {
            translateX.value = withTiming(SCREEN_W * 1.5, { duration: 220, easing: Easing.out(Easing.cubic) }, () => {
              runOnJS(onLike)();
              translateX.value = 0;
            });
          } else if (e.translationX < -SWIPE_THRESHOLD && e.velocityX < -200) {
            translateX.value = withTiming(-SCREEN_W * 1.5, { duration: 220, easing: Easing.out(Easing.cubic) }, () => {
              runOnJS(onPass)();
              translateX.value = 0;
            });
          } else {
            translateX.value = withTiming(0, { duration: 180 });
          }
        }),
    [onLike, onPass, translateX],
  );

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { rotate: `${translateX.value / 20}deg` },
    ],
  }));

  return (
    <GestureDetector gesture={pan}>
      <Animated.View style={[styles.cardStack, animatedStyle]}>
        <TradeCardComp data={card} />
      </Animated.View>
    </GestureDetector>
  );
}

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ── Styles ──────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, gap: spacing.lg, paddingBottom: 96 },
  // B3 — sub-route pill row (Trades / Portfolio)
  subnavRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  subnavPill: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  subnavPillActive: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.12)',
  },
  subnavPillText: {
    color: colors.muted,
    fontSize: fontSize.sm,
    fontWeight: '700',
  },
  subnavPillTextActive: {
    color: colors.accent,
  },
  switchingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(15,17,23,0.85)',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    zIndex: 50,
  },
  switchingText: {
    color: colors.text,
    fontSize: fontSize.base,
    fontWeight: '700',
    textAlign: 'center',
    paddingHorizontal: spacing.xl,
  },
  controlCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  controlRow: { flexDirection: 'row', alignItems: 'center' },
  controlLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  controlValue: { color: colors.text, fontSize: fontSize.base, fontWeight: '800' },
  editBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  editBtnText: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  fairnessRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  fairnessLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  fairnessHint: {
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '700',
    marginTop: 2,
  },
  findBtn: {
    backgroundColor: colors.accent,
    paddingVertical: 14,
    borderRadius: radius.md,
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  findBtnText: { color: '#fff', fontSize: fontSize.base, fontWeight: '800' },
  progressStrip: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: 'rgba(79,124,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(79,124,255,0.25)',
  },
  progressInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flex: 1,
    minWidth: 0,
  },
  progressText: {
    color: colors.accent,
    fontSize: fontSize.xs,
    fontWeight: '700',
    flexShrink: 1,
  },
  stopBtn: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  stopBtnText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.3,
  },
  likedCount: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    marginTop: 4,
  },
  deckWrap: {
    minHeight: 360,
    position: 'relative',
  },
  cardStack: {
    width: '100%',
  },
  cardBehind: {
    position: 'absolute',
    top: 8,
    left: 0,
    right: 0,
    opacity: 0.55,
    transform: [{ scale: 0.97 }],
  },
  deckHint: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    marginTop: spacing.md,
  },
  emptyCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    gap: spacing.sm,
  },
  emptyTitle: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },
  emptyBody: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    lineHeight: 22,
  },

  // Queue button — appears below the swipable card under the queue flag.
  queueBtn: {
    alignSelf: 'center',
    marginTop: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  queueBtnQueued: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.12)',
  },
  queueBtnText: {
    color: colors.muted,
    fontSize: fontSize.sm,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  queueBtnTextQueued: { color: colors.accent },

  // Queue footer — anchored above the tab bar (the SafeAreaView already
  // reserves the bottom inset). Visible only when queue has ≥ 1 item.
  queueFooter: {
    position: 'absolute',
    left: spacing.md,
    right: spacing.md,
    bottom: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    // Drop-shadow for elevation over the deck below.
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  queueFooterTap: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
  },
  queueFooterCount: {
    minWidth: 28,
    height: 28,
    paddingHorizontal: 8,
    textAlign: 'center',
    lineHeight: 28,
    borderRadius: 14,
    backgroundColor: colors.accent,
    color: '#fff',
    fontWeight: '800',
    fontSize: fontSize.sm,
    overflow: 'hidden',
  },
  queueFooterLabel: {
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '700',
    flex: 1,
  },
  queueSendBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.accent,
  },
  queueSendText: { color: '#fff', fontWeight: '800', fontSize: fontSize.sm },

  // Queue bottom-sheet modal
  queueBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  queueSheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '80%',
    backgroundColor: colors.bg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.sm,
  },
  queueHandle: {
    alignSelf: 'center',
    width: 44,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.border,
    marginBottom: spacing.sm,
  },
  queueSheetHeader: { gap: 2 },
  queueSheetTitle: { color: colors.text, fontSize: fontSize.xl, fontWeight: '800' },
  queueSheetSub: { color: colors.muted, fontSize: fontSize.sm },
  queueSheetScroll: { maxHeight: 420, marginTop: spacing.sm },
  queueEmpty: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    padding: spacing.xl,
  },
  queueSheetActions: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  queueSheetCancel: {
    flex: 1,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
  },
  queueSheetCancelText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '700' },
  queueSheetSend: {
    flex: 2,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.accent,
    alignItems: 'center',
  },
  queueSheetSendText: { color: '#fff', fontSize: fontSize.sm, fontWeight: '800' },

  // FB-05 — ✓ / ✗ disposition button row beneath the top trade card.
  // Placed between SwipableTopCard (and optional Queue button) and deckHint.
  dispositionRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.xl,
    marginTop: spacing.lg,
  },
  dispositionBtn: {
    width: 56,
    height: 56,
    borderRadius: radius.pill,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dispositionBtnPass: {
    borderColor: colors.red,
    backgroundColor: 'rgba(239,68,68,0.10)',
  },
  dispositionBtnLike: {
    borderColor: colors.green,
    backgroundColor: 'rgba(34,197,94,0.10)',
  },
  dispositionBtnText: {
    fontSize: fontSize.xl,
    fontWeight: '800',
  },
  dispositionBtnTextPass: { color: colors.red },
  dispositionBtnTextLike: { color: colors.green },
});
