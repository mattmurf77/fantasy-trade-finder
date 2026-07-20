import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  ScrollView,
  Dimensions,
  Modal,
  Alert,
  Platform,
  Share,
  type LayoutChangeEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withDelay,
  withRepeat,
  withSequence,
  cancelAnimation,
  runOnJS,
  Easing,
} from 'react-native-reanimated';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { haptics } from '../utils/haptics';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  semantic,
  space,
  radii,
  type,
  fonts,
  flare,
  shadowSheet,
  scrim,
} from '../theme/chalkline';
import { TickLabel, Button, Meter, Icon, Card } from '../components/chalkline';
import TradeCardComp from '../components/TradeCard';
import SendInSleeperButton from '../components/SendInSleeperButton';
import Toast from '../components/Toast';
import OutlookSheet from '../components/OutlookSheet';
import LeaguePill from '../components/LeaguePill';
import LeagueSwitcherSheet from '../components/LeagueSwitcherSheet';
import QueueChip from '../components/QueueChip';
import SwapPlayerSheet from '../components/SwapPlayerSheet';
import PlayerPickerModal from '../components/PlayerPickerModal';
import type { CalcPlayer } from '../data/tradeCalcMock';
import {
  generateTrades,
  getTradeStatus,
  swipeTrade,
  flagBadTrade,
  getLikedTrades,
} from '../api/trades';
import {
  getLeaguePreferences,
  saveLeaguePreferences,
  getNewPartners,
  getLeagueCoverage,
  copyTiersFromFormat,
  getAssetPrefs,
  setAssetPref,
  type Outlook,
} from '../api/league';
import { getLeagueRosters, getLeagueUsers } from '../api/sleeper';
import {
  getTradeValues,
  evaluateTradeInLeague,
  type CalcValueRow,
} from '../api/calc';
import { getProgress } from '../api/rankings';
import { track, msSinceOpen } from '../api/events';
import InviteLeaguematesBanner from '../components/InviteLeaguematesBanner';
import FormatGate, { formatLabel } from '../components/FormatGate';
import ProvenanceChip from '../components/ProvenanceChip';
import SkeletonTradeCard from '../components/SkeletonTradeCard';
import CoachMark from '../components/CoachMark';
import IdentityConfirmStrip from '../components/IdentityConfirmStrip';
import QuickSetPromptCard from '../components/QuickSetPromptCard';
import AppleSaveMomentSheet from '../components/AppleSaveMomentSheet';
import { consumePendingQuicksetRegen } from '../state/onboardingBus';
import {
  useGuide,
  requestGuideStep,
  advanceGuideIfActive,
  guidedAvatarActive,
} from '../state/useGuide';
import { registerGuideTarget, unregisterGuideTarget } from '../state/guideTargets';
import { S as GUIDE, nextUnrankedPosition } from '../components/analystScript';
import { useSession } from '../state/useSession';
import { useTradeQueue } from '../state/useTradeQueue';
import { useFlag, useOnboardingFeature, onboardingEnabled } from '../state/useFeatureFlags';
import {
  useOnboardingState,
  getOnboardingState,
  patchOnboardingState,
} from '../state/useOnboardingState';
import {
  FAIRNESS_PREF_KEY,
  FAIRNESS_ON_THRESHOLD,
  FAIRNESS_OFF_THRESHOLD,
} from '../api/tradePregen';
import { navigationRef } from '../navigation/RootNav';
import NewPartnersBanner from '../components/NewPartnersBanner';
import type { Player, TradeCard, TradeJobSnapshot, ScoringFormat } from '../shared/types';

const SCREEN_W = Dimensions.get('window').width;
const SWIPE_THRESHOLD = 120;

// Stable empty-array reference so the zustand selector doesn't return a
// brand-new `[]` on every render (which would trigger an infinite re-render
// loop in React via reference inequality).
const EMPTY_QUEUE: never[] = [];

// Persisted fairness pref + thresholds now live in api/tradePregen.ts —
// single source shared with the onboarding pregen hook so both request the
// same server cache slot (the job cache keys on fairness_threshold).
// Semantics unchanged: ON = balanced trades (old slider default), OFF =
// broadest pool for the client-side sort-by-mismatch.

// Player-swap (feedback #86): trade_id suffix marking a user-modified
// package. Deliberately unknown to the server — a like/flag under this id
// misses the in-memory ORIGINAL card and takes the FB-46 context-
// reconstruction path instead, so the EDITED give/receive ids echoed in
// the payload are what get recorded (Elo signal, persistence, and mutual-
// match detection all run on the modified package).
const EDITED_SUFFIX = '::edited';

// Analytics: true once this screen has shown the "Waking up server" copy
// (the >4s slow-switch overlay) at any point this app session. First-card
// trade_card_viewed events carry it as `cold_start` so time-to-first-card
// numbers can be split by Render cold starts.
let sawServerWakeThisSession = false;

// Onboarding item 4 (F5): the identity-confirm strip's X hides it for the
// rest of the app session (module-level so a tab remount doesn't resurrect
// it); it returns on the next cold start while first-run is still active.
let identityStripDismissedThisSession = false;

// Onboarding item 7 (F10/G8): the contextual Quick Set prompt shows at most
// once per app session, whatever the trigger path (module-level so a tab
// remount can't re-fire it).
let quicksetPromptShownThisSession = false;

// Guided tour session caps (script §3): S5.5 next-position ask and the S7
// trio ramp each show at most once per app session.
let guideS55ShownThisSession = false;
let guideS7ShownThisSession = false;

// Onboarding item 8 (F4): at most one Apple save-moment ask per app session
// across all trigger classes — asks never stack and never nag.
let appleAskShownThisSession = false;

export default function TradesScreen({ navigation }: any) {
  const queryClient = useQueryClient();
  const league = useSession((s) => s.league);
  const switching = useSession((s) => s.switching);
  const user = useSession((s) => s.user);
  // FB4-59 — the format this league resolves to. Used to key the progress
  // query (shared with RootNav/RankScreen) and to detect the single-format
  // gate state below.
  const activeFormat = useSession((s) => s.activeFormat);
  // B3 — Portfolio is only meaningful when the user has 2+ leagues. The
  // sub-route pill at the top of this screen hides itself otherwise.
  const leagues = useSession((s) => s.leagues);
  const showPortfolioPill = (leagues?.length || 0) >= 2;
  const leagueId = league?.league_id || null;
  const userId   = user?.user_id || '';
  const isDemo   = useSession((s) => s.isDemo);

  // ── Onboarding item 4 (docs/plans/onboarding-conversion/plan.md) ─────
  // Everything in this block is dark unless onboarding.v2 AND the feature
  // flag are both on (useOnboardingFeature/onboardingEnabled) — flags off,
  // this screen's behavior is unchanged.
  const tradesFirstOn = useOnboardingFeature('onboarding.trades_first');
  const guidedOn      = useOnboardingFeature('onboarding.guided_layer');
  const quicksetPromptOn = useOnboardingFeature('onboarding.quickset_prompt');
  const appleSaveOn  = useOnboardingFeature('onboarding.apple_save_moment');
  const shareSheetOn = useOnboardingFeature('onboarding.share_sheet');
  const rankRoutingOn = useOnboardingFeature('onboarding.rank_routing');
  const demoBridgeOn = useOnboardingFeature('onboarding.demo_bridge');
  // Item 10 (F12): redraft leagues get an honest values label — dynasty
  // values are wrong for them by construction, and an unlabeled wrong
  // number reads as a broken app.
  const activeLeagueSummary = leagues?.find((lg) => lg.league_id === leagueId);
  const isRedraftLeague = activeLeagueSummary?.settings_type === 0;
  // Item 8 — save-moment Apple ask + session-2 banner + share affordance.
  const verification = useSession((s) => s.verification);
  const [appleAsk, setAppleAsk] =
    useState<'like' | 'quickset_save' | 'session2_banner' | null>(null);
  const [lastLikedCard, setLastLikedCard] = useState<TradeCard | null>(null);
  const obSessionCount = useOnboardingState((s) => s.ob.sessionCount);
  const obTotalSwipes = useOnboardingState((s) => s.ob.totalSwipes);
  const session2BannerShown = useOnboardingState(
    (s) => s.ob.appleSession2BannerShown,
  );
  // Item 7 — inline prompt card + post-Quick-Set regeneration diff banner.
  const [quicksetPromptVisible, setQuicksetPromptVisible] = useState(false);
  const [quicksetDiffBanner, setQuicksetDiffBanner] =
    useState<{ position: string; count: number } | null>(null);
  // Set when an onboarding-mode Quick Set completion posts a pending regen;
  // holds the pre-regen deck ids so the banner can count NEW trades.
  const pendingRegenRef = useRef<{ position: string; prevIds: Set<string> } | null>(null);
  // Provenance chip flips CONSENSUS VALUES → YOUR BOARD once any position
  // has been Quick-Set (item 7 writes quicksetCompletedPositions).
  const quicksetPositions = useOnboardingState(
    (s) => s.ob.quicksetCompletedPositions,
  );
  const swipeHintDone = useOnboardingState(
    (s) => !!s.ob.coachMarksShown.swipe_hint,
  );
  const provenanceMarkDone = useOnboardingState(
    (s) => !!s.ob.coachMarksShown.provenance_chip,
  );
  // First-run mode (accepted F11) LATCHES at mount: chrome stays collapsed
  // for the rest of this mount even after the first swipe flips
  // firstSwipeDone — normal chrome returns on the next mount, never as a
  // jarring mid-session re-expand. Requires the onboarding store to be
  // hydrated (App.tsx boot) so a returning user is never mis-read as
  // first-run while AsyncStorage is still loading — fails toward normal.
  const [firstRun] = useState(() => {
    const st = useOnboardingState.getState();
    return (
      onboardingEnabled('onboarding.trades_first') &&
      st.hydrated &&
      !st.ob.firstSwipeDone
    );
  });
  // Identity-confirm strip (F5) — first-run only, dismissible per session.
  const [identityStripVisible, setIdentityStripVisible] = useState(
    () => firstRun && !identityStripDismissedThisSession,
  );
  // Guided layer bookkeeping. Coach marks never stack: if the swipe hint
  // shows on this mount, the provenance mark waits for the next mount.
  const [swipeHintActive, setSwipeHintActive] = useState(false);
  const swipeHintShownThisMountRef = useRef(false);
  const [provenanceMarkVisible, setProvenanceMarkVisible] = useState(false);
  const provenanceMarkShownRef = useRef(false);
  // First-run auto-generation lifecycle: idle → kicked → (retrying →)
  // failed. One silent retry ~4s later covers the LeaguePicker race where
  // the background session_init hasn't landed when Trades mounts.
  const autoGenRef = useRef<'idle' | 'kicked' | 'retrying' | 'failed'>('idle');
  const autoRetryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [autoGenFailed, setAutoGenFailed] = useState(false);

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
  // Cold-start invite banner — when no league-mate has ranked, every card
  // is a consensus-basis estimate, so nudge the user to invite. Shares the
  // ['league-coverage', leagueId] key with LeagueScreen's coverage bar.
  const coverageQuery = useQuery({
    queryKey: ['league-coverage', leagueId],
    queryFn:  () => getLeagueCoverage(leagueId!),
    enabled:  !!leagueId,
    staleTime: 5 * 60_000,
  });
  const coverage = coverageQuery.data;
  const showInviteBanner =
    !!coverage && (coverage.total ?? 0) > 0 && (coverage.ranked ?? 0) === 0;
  // Trade-fairness toggle. ON = backend filters to balanced trades and
  // sorts by composite_score (current behavior). OFF = broaden the
  // backend filter to its loosest (0.5) and re-sort the deck client-side
  // by ranking-mismatch magnitude (TradeCard.match_score, which is the
  // server's mismatch_score: how big the ELO gap between owners is on
  // the swapped players). Persisted across sessions via AsyncStorage.
  const [fairnessOn, setFairnessOn] = useState(true);
  const [deck, setDeck] = useState<TradeCard[]>([]);
  const [deckIdx, setDeckIdx] = useState(0);
  // Phase-2 lane filter: null = All. Tapping a lane pill filters the deck
  // to that lane; tapping the active pill again clears back to All. The
  // pill row only renders when at least one deck card carries a lane.
  const [laneFilter, setLaneFilter] = useState<'window' | 'value' | null>(null);
  // #107/#110 — measured layout height of the TOP card. The behind-card
  // peek is clipped to this so a taller next card (e.g. 2 player tiles
  // behind a 1-player top) can't leak its extra tile out from under the
  // top card. Updated via onLayout on every top-card mount/re-layout.
  const [topCardH, setTopCardH] = useState<number | null>(null);
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
    const t = setTimeout(() => {
      setSlowSwitch(true);
      sawServerWakeThisSession = true;
    }, 4000);
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
    setLaneFilter(null);
    setJob(null);
    setEdits({});
    setSwapTarget(null);
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

  // Phase-2: when the backend inferred an outlook from the roster, don't
  // force-open the sheet — the inline confirm banner (above the deck)
  // offers one-tap confirm instead. No outlook AND no inference keeps the
  // original force-open behavior.
  //
  // Onboarding item 4: on a first-run mount the deck is the whole show —
  // never front it with a modal sheet (plan: no interruption before the
  // first cards). The sheet resumes force-opening on the next mount; the
  // Edit path and the inferred-outlook one-tap confirm stay available.
  useEffect(() => {
    if (firstRun) return;
    if (
      prefsQuery.data &&
      !prefsQuery.data.team_outlook &&
      !prefsQuery.data.inferred_outlook
    ) {
      setOutlookOpen(true);
    }
  }, [prefsQuery.data, firstRun]);

  // Phase-2 inferred outlook — set only while no outlook is declared;
  // drives the one-tap confirm banner and the sheet's preselection.
  const inferredOutlook =
    prefsQuery.data && !prefsQuery.data.team_outlook
      ? prefsQuery.data.inferred_outlook ?? null
      : null;

  // One-tap confirm: persist the inferred outlook with empty position
  // arrays, then refetch prefs so the banner clears and the control card
  // shows the saved value.
  const confirmOutlookMutation = useMutation({
    mutationFn: (outlook: NonNullable<Outlook>) =>
      saveLeaguePreferences(leagueId!, {
        team_outlook: outlook,
        acquire_positions: [],
        trade_away_positions: [],
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['league-prefs', leagueId] });
      setToast({ msg: 'Outlook saved', tone: 'success' });
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Could not save outlook', tone: 'warn' });
    },
  });

  // ── Untouchables (feedback #95, flag trade.preference_lists) ─────────
  // Long-press a player on the YOU SEND side to mark/unmark them
  // untouchable — the trade engine then never offers them from your
  // roster. Mirrors MatchesScreen; single-league here, so one query.
  const untouchablesEnabled = useFlag('trade.preference_lists');
  const assetPrefsQuery = useQuery({
    queryKey: ['asset-prefs', leagueId],
    queryFn: () => getAssetPrefs(leagueId!),
    staleTime: 60_000,
    enabled: untouchablesEnabled && !!leagueId,
  });
  const untouchableIds = useMemo(
    () =>
      assetPrefsQuery.data
        ? new Set<string>(assetPrefsQuery.data.untouchables || [])
        : undefined,
    [assetPrefsQuery.data],
  );

  const untouchableMutation = useMutation({
    mutationFn: ({ playerId, list }: {
      playerId: string;
      list: 'untouchable' | 'none';
    }) => setAssetPref(leagueId!, playerId, list),
    onSuccess: (_res, vars) => {
      queryClient.invalidateQueries({ queryKey: ['asset-prefs', leagueId] });
      setToast({
        msg: vars.list === 'untouchable'
          ? 'Marked untouchable — never offered in trade ideas'
          : 'Untouchable removed',
        tone: 'success',
      });
    },
    onError: () => {
      setToast({ msg: 'Could not update untouchable — try again', tone: 'warn' });
    },
  });

  function handleToggleUntouchable(p: Player) {
    if (untouchableMutation.isPending || !leagueId) return;
    haptics.selection();
    const marked = untouchableIds?.has(p.id) ?? false;
    untouchableMutation.mutate({
      playerId: p.id,
      list: marked ? 'none' : 'untouchable',
    });
  }

  // ── FB4-59: single-format gate ───────────────────────────────────────
  // Trading requires the user to have established rankings for THIS league's
  // scoring format. /api/rankings/progress returns `scoring_format` (the
  // format this league resolves to) and `unlocked_formats` (every format the
  // user has actually set up). Shares the ['progress', leagueId, activeFormat]
  // key with RootNav/RankScreen so it adopts any in-flight fetch and reuses
  // the cache. We only surface the gate when we're CONFIDENT a format is
  // unset — never on a loading/error/placeholder state.
  const progressQuery = useQuery({
    queryKey: ['progress', leagueId, activeFormat],
    queryFn: getProgress,
    enabled: !!leagueId,
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  });

  // Detect "only the OTHER format is established". Conditions, all required:
  //  • progress data has loaded (not loading/fetching with no data),
  //  • the query isn't in an error state,
  //  • the league's format is known and NOT in unlocked_formats,
  //  • the OTHER format IS in unlocked_formats.
  // The last clause is what makes this specifically the single-format case:
  // a brand-new user with neither format set falls through to the normal
  // cold-start empty state, not this gate.
  const gateState = useMemo<{ needed: ScoringFormat; set: ScoringFormat } | null>(() => {
    const data = progressQuery.data;
    if (!data || progressQuery.isError) return null;
    const needed = data.scoring_format as ScoringFormat | undefined;
    if (needed !== '1qb_ppr' && needed !== 'sf_tep') return null;
    const unlocked = data.unlocked_formats ?? [];
    if (unlocked.includes(needed)) return null;               // needed format is set — no gate
    const other: ScoringFormat = needed === '1qb_ppr' ? 'sf_tep' : '1qb_ppr';
    if (!unlocked.includes(other)) return null;               // neither set — cold start, not this gate
    return { needed, set: other };
  }, [progressQuery.data, progressQuery.isError]);

  // Copy the established format's tiers into the league's format. Mirrors
  // TiersScreen's copyMutation: destructive confirm Alert → copyTiersFromFormat
  // → invalidate the rankings/tiers/progress caches so the gate clears and
  // Trades content unlocks on the next progress fetch.
  const copyFormatMutation = useMutation({
    mutationFn: ({ from, to }: { from: ScoringFormat; to: ScoringFormat }) =>
      copyTiersFromFormat(from, to),
    onSuccess: (data, vars) => {
      if (!data?.ok) {
        setToast({ msg: data?.error || 'Copy failed', tone: 'warn' });
        return;
      }
      const n = data.total ?? 0;
      setToast({ msg: `✓ Copied ${n} tier placements`, tone: 'success' });
      // A format copy establishes the target format — invalidate the caches
      // that gate Trades so the gate re-evaluates and clears. Progress is the
      // direct signal this screen reads; rankings/tiers-status keep the Rank
      // surfaces consistent (same set TiersScreen invalidates on copy).
      queryClient.invalidateQueries({ queryKey: ['progress', leagueId, vars.to] });
      queryClient.invalidateQueries({ queryKey: ['rankings', vars.to] });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Copy failed', tone: 'warn' });
    },
  });

  function onGateCopy(gate: { needed: ScoringFormat; set: ScoringFormat }) {
    // Destructive on the target format's existing overrides (there are none
    // when it's unset, but the copy endpoint replaces wholesale) — confirm
    // first, matching TiersScreen's pattern.
    Alert.alert(
      `Copy tiers from ${formatLabel(gate.set)}?`,
      `This sets up your ${formatLabel(gate.needed)} rankings using your ` +
        `${formatLabel(gate.set)} tiers. Each player keeps their tier and ` +
        `within-tier rank; only the underlying values change to fit ` +
        `${formatLabel(gate.needed)}'s bands.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Copy',
          onPress: () => {
            haptics.warning();
            copyFormatMutation.mutate({ from: gate.set, to: gate.needed });
          },
        },
      ],
    );
  }

  function onGateSetUpManually() {
    // Route to the Rank tab's Tiers entry. activeFormat already resolves to
    // the league's (needed) format, so Tiers opens on the right format. Sibling
    // tab navigation: the Trades stack's navigation prop reaches the parent
    // Tab navigator (mirrors TabNav's RankMenu dispatch).
    navigation?.navigate?.('Rank', { screen: 'Tiers' });
  }

  // ── FB-47 finder targeting (flag trade.finder_targeting) ─────────────
  // "Find a Trade" controls gain a direction toggle + player picker:
  // Trade away = pin players from YOUR roster (pinned_give_players),
  // Acquire = pin LEAGUEMATES' players you want (pinned_receive_players).
  // The two lists are independent — the toggle only selects which pool the
  // picker shows — so "move X to land Y" is expressible. Position-level
  // targeting already lives in OutlookSheet's acquire/trade-away chips.
  // Targets are session-local (reset on league switch, not persisted):
  // pinned jobs bypass the server cache, so a stale sticky pin would make
  // every future tap slow + narrow without the user remembering why.
  const targetingEnabled = useFlag('trade.finder_targeting');
  const [targetDirection, setTargetDirection] =
    useState<'trade_away' | 'acquire'>('trade_away');
  const [pinnedGive, setPinnedGive] = useState<Player[]>([]);
  const [pinnedReceive, setPinnedReceive] = useState<Player[]>([]);
  const [targetPickerOpen, setTargetPickerOpen] = useState(false);

  // ── Find-a-Trade: streaming job snapshot ─────────────────────────────
  // The backend runs generation in a background thread and we poll for
  // results. The job snapshot drives both the deck (cards stream in) and
  // the progress strip ("4/11 opponents searched").
  const [job, setJob] = useState<TradeJobSnapshot | null>(null);

  const generateMutation = useMutation({
    // `auto` marks the onboarding first-run auto-start (item 4): its
    // failures stay silent (retry below) instead of toasting. Manual taps
    // pass {} and behave exactly as before. `force` (item 7) skips the
    // server's complete-fresh job cache — used by the post-Quick-Set
    // regeneration, whose board change doesn't alter the cache key.
    mutationFn: (vars: { auto?: boolean; force?: boolean }) =>
      generateTrades({
        league_id: leagueId!,
        fairness_threshold: effectiveFairness,
        force: vars.force || undefined,
        // FB-47 — omit (not []) when unset so untargeted payloads stay
        // byte-identical to the pre-targeting shape.
        pinned_give_players:
          targetingEnabled && pinnedGive.length > 0
            ? pinnedGive.map((p) => p.id)
            : undefined,
        pinned_receive_players:
          targetingEnabled && pinnedReceive.length > 0
            ? pinnedReceive.map((p) => p.id)
            : undefined,
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
    onError: (e: Error, vars) => {
      if (vars?.auto) {
        // First-run auto-start failed — most likely the LeaguePicker
        // background session_init hasn't landed yet. Retry once, quietly;
        // a second failure surfaces the normal manual empty state (the
        // Find a Trade button is the recovery path).
        if (autoGenRef.current === 'kicked') {
          autoGenRef.current = 'retrying';
          autoRetryTimer.current = setTimeout(() => {
            autoRetryTimer.current = null;
            generateMutation.mutate({ auto: true });
          }, 4000);
        } else {
          autoGenRef.current = 'failed';
          setAutoGenFailed(true);
        }
        return;
      }
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
  // FB-47 targets are roster-specific, so they clear with the league too.
  useEffect(() => {
    setDeck([]);
    setDeckIdx(0);
    setLaneFilter(null);
    setJob(null);
    setEdits({});
    setSwapTarget(null);
    setPinnedGive([]);
    setPinnedReceive([]);
    setTargetPickerOpen(false);
    // Onboarding item 4 — reset the first-run auto-start lifecycle so a
    // league switch mid-first-run can auto-start against the new league.
    if (autoRetryTimer.current) {
      clearTimeout(autoRetryTimer.current);
      autoRetryTimer.current = null;
    }
    autoGenRef.current = 'idle';
    setAutoGenFailed(false);
  }, [leagueId]);

  // ── Onboarding item 4: first-run auto-start ──────────────────────────
  // On a first-run mount with no deck, kick generation immediately (the
  // pregen hook usually already warmed the server job — this call adopts
  // it) and show the skeleton deck instead of the manual empty state.
  // One kick per league; the silent retry lives in generateMutation.onError.
  useEffect(() => {
    if (!firstRun || !leagueId || gateState) return;
    if (autoGenRef.current !== 'idle') return;
    if (job || generateMutation.isPending || deck.length > 0) return;
    autoGenRef.current = 'kicked';
    generateMutation.mutate({ auto: true });
    // generateMutation identity churns per render; keying on the inputs
    // that matter keeps this a mount/league-scoped one-shot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstRun, leagueId, gateState, job, deck.length]);

  // Clear any pending auto-retry on unmount.
  useEffect(
    () => () => {
      if (autoRetryTimer.current) clearTimeout(autoRetryTimer.current);
    },
    [],
  );

  const swipeMutation = useMutation({
    mutationFn: ({ card, decision }: { card: TradeCard; decision: 'like' | 'pass' }) =>
      swipeTrade(card, decision),
    onMutate: ({ card }) => {
      const tradeId = card.trade_id;
      // Edited cards (player swap, feedback #86) carry a derived trade_id
      // (`<raw>::edited`); resolve back to the raw deck id so the rollback
      // bookkeeping below still finds the deck entry.
      const rawId = tradeId.endsWith(EDITED_SUFFIX)
        ? tradeId.slice(0, -EDITED_SUFFIX.length)
        : tradeId;
      // Snapshot the index this card was at when the swipe fired. On
      // error we use this to decide whether to rewind the deck — only
      // safe if the user hasn't already swiped past it. Capturing the
      // index inside the deck (rather than the position in `sortedDeck`)
      // keeps the rollback correct under fairness re-sorts that happen
      // between the swipe and the error.
      const dispatchedIdx = deck.findIndex((c) => c.trade_id === rawId);
      return { tradeId, rawId, dispatchedIdx };
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
        // Compare on the RAW id — sortedDeck holds the original cards even
        // when the swiped payload was an edited variant.
        const rawId = ctx?.rawId;
        if (!rawId) return cur;
        // The card that was at the top when we swiped lives at cur-1
        // post-advance. If sortedDeck no longer has it there, the user
        // has swiped further or the deck was re-sorted — don't rewind.
        const prevCard = sortedDeck[cur - 1];
        if (prevCard && prevCard.trade_id === rawId) return cur - 1;
        return cur;
      });
      queryClient.invalidateQueries({ queryKey: ['liked-trades', leagueId] });
      setToast({ msg: "Swipe didn't save — try again.", tone: 'warn' });
    },
  });

  // Bad-trade flag (feedback #85) — engine-quality signal, distinct from
  // pass. Best-effort: the deck has already advanced via the pass path, so
  // a failed flag just toasts instead of rewinding (the pass swipe carries
  // the "not interested" signal regardless).
  const flagMutation = useMutation({
    mutationFn: (card: TradeCard) => flagBadTrade(card),
    onError: () => {
      setToast({ msg: "Flag didn't save — try again.", tone: 'warn' });
    },
  });

  // ── Player swap (feedback #86) ───────────────────────────────────────
  // Tap the swap affordance next to any player on the top card to replace
  // them with another player from the same roster (give side → your
  // roster, receive side → the counterparty's). Edited variants live in
  // `edits`, keyed by the ORIGINAL trade_id — the top-card lookup below
  // overlays them without mutating the deck.
  const [edits, setEdits] = useState<Record<string, TradeCard>>({});
  const [swapTarget, setSwapTarget] = useState<{
    player: Player;
    side: 'give' | 'receive';
  } | null>(null);

  // Consensus values + league rosters feed the swap sheet's candidates and
  // "closest in value" suggestions. Query keys are shared with
  // InLeagueCalculator so the two surfaces reuse one cache. Fetched lazily
  // once the deck has cards — the sheet can't open before that — or when
  // the FB-47 target picker opens (it draws on the same two sources).
  const calcFormat: ScoringFormat = activeFormat ?? '1qb_ppr';
  const valuesQuery = useQuery({
    queryKey: ['calc-values', calcFormat],
    queryFn: ({ signal }) => getTradeValues(calcFormat, signal),
    enabled: deck.length > 0 || targetPickerOpen,
    staleTime: 5 * 60_000,
  });
  const rostersQuery = useQuery({
    queryKey: ['league-rosters', leagueId],
    queryFn: () => getLeagueRosters(leagueId!),
    enabled: !!leagueId && (deck.length > 0 || targetPickerOpen),
    staleTime: 5 * 60_000,
  });
  // FB-47 — owner display names for the acquire picker's @owner badges.
  // Only fetched while the picker is actually open.
  const leagueUsersQuery = useQuery({
    queryKey: ['league-users', leagueId],
    queryFn: () => getLeagueUsers(leagueId!),
    enabled: !!leagueId && targetingEnabled && targetPickerOpen,
    staleTime: 5 * 60_000,
  });
  const valueById = useMemo(() => {
    const m = new Map<string, CalcValueRow>();
    for (const r of valuesQuery.data?.players ?? []) m.set(r.id, r);
    return m;
  }, [valuesQuery.data]);
  const rosterByOwner = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const row of rostersQuery.data ?? []) {
      if (row.owner_id) m.set(row.owner_id, row.players ?? []);
    }
    return m;
  }, [rostersQuery.data]);

  // ── FB-47 targeting: picker pool + handlers ──────────────────────────
  // Trade away → the user's own roster; Acquire → every LEAGUEMATE roster.
  // Rows come from the consensus value pool (same source as the swap
  // sheet), mapped to PlayerPickerModal's CalcPlayer shape. Unvalued
  // players (K/DST, deep stashes) drop out — consistent with the swap
  // sheet's candidate rules.
  const ownerByPlayerId = useMemo(() => {
    const m = new Map<string, string>();
    for (const [ownerId, ids] of rosterByOwner) {
      if (ownerId === userId) continue;
      for (const id of ids) m.set(id, ownerId);
    }
    return m;
  }, [rosterByOwner, userId]);
  const usernameByOwner = useMemo(() => {
    const m = new Map<string, string>();
    for (const u of leagueUsersQuery.data ?? []) {
      m.set(u.user_id, u.display_name || u.username || u.user_id);
    }
    return m;
  }, [leagueUsersQuery.data]);
  const targetPickerPool = useMemo<CalcPlayer[]>(() => {
    if (!targetPickerOpen) return [];
    const ids =
      targetDirection === 'trade_away'
        ? rosterByOwner.get(userId) ?? []
        : [...ownerByPlayerId.keys()];
    return ids
      .map((id) => valueById.get(id))
      .filter((r): r is CalcValueRow => !!r)
      .map((r) => ({
        id: r.id,
        name: r.name,
        pos: r.position as CalcPlayer['pos'],
        nflTeam: r.team ?? 'FA',
        age: r.age ?? 0,
        base: r.value,
      }));
  }, [targetPickerOpen, targetDirection, rosterByOwner, ownerByPlayerId, valueById, userId]);

  // Any target change invalidates the current deck — the next "Find a
  // Trade" tap regenerates through the normal job flow (pinned jobs bypass
  // the server cache). Deliberately NOT auto-firing a job per chip change.
  function resetDeckForNewTargets() {
    setDeck([]);
    setDeckIdx(0);
    setLaneFilter(null);
    setJob(null);
    setEdits({});
    setSwapTarget(null);
  }

  function handleAddTarget(p: CalcPlayer) {
    const player: Player = {
      id: p.id,
      name: p.name,
      position: p.pos,
      team: p.nflTeam,
      age: p.age,
    };
    const setter = targetDirection === 'trade_away' ? setPinnedGive : setPinnedReceive;
    setter((prev) => (prev.some((x) => x.id === p.id) ? prev : [...prev, player]));
    haptics.selection();
    resetDeckForNewTargets();
  }

  function handleRemoveTarget(id: string, dir: 'trade_away' | 'acquire') {
    const setter = dir === 'trade_away' ? setPinnedGive : setPinnedReceive;
    setter((prev) => prev.filter((p) => p.id !== id));
    haptics.selection();
    resetDeckForNewTargets();
  }

  // Positions the user is trying to acquire — sharpens the card fit line's
  // copy ("They're deep at WR"). Pinned acquire targets + saved prefs.
  const fitTargetPositions = useMemo(() => {
    const set = new Set<string>();
    for (const p of pinnedReceive) if (p.position) set.add(String(p.position));
    for (const pos of prefsQuery.data?.acquire_positions ?? []) set.add(pos);
    return [...set];
  }, [pinnedReceive, prefsQuery.data]);

  // Re-price an edited package via /api/trade/evaluate Mode B — the same
  // dual-board math the finder used to build the card. Success refreshes
  // the edited card's fairness/basis; failure just toasts (fairness was
  // cleared on swap, so no stale number is ever shown).
  const repriceMutation = useMutation({
    mutationFn: ({ card }: { rawId: string; card: TradeCard }) =>
      evaluateTradeInLeague(
        card.give_player_ids,
        card.receive_player_ids,
        calcFormat,
        card.league_id || leagueId!,
        card.opponent_user_id,
      ),
    onSuccess: (ev, vars) => {
      setEdits((prev) => {
        const cur = prev[vars.rawId];
        // Apply only if the entry still holds the exact package we priced —
        // the user may have swapped again while this round-trip was in
        // flight (a newer mutation will land its own numbers).
        if (
          !cur ||
          cur.give_player_ids.join(',') !== vars.card.give_player_ids.join(',') ||
          cur.receive_player_ids.join(',') !== vars.card.receive_player_ids.join(',')
        ) {
          return prev;
        }
        return {
          ...prev,
          [vars.rawId]: {
            ...cur,
            fairness: (ev.fairness ?? undefined) as unknown as number,
            basis: ev.basis,
          },
        };
      });
    },
    onError: () => {
      setToast({
        msg: "Couldn't re-price the edited trade — fairness unavailable.",
        tone: 'warn',
      });
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
  // Likes-you cards are server-pinned to the top of the snapshot (the
  // counterparty already liked the mirror trade) — never let the client
  // re-sort bury them. Keep them first in server order; only the rest
  // get the mismatch re-sort.
  // Phase-2 lane filter applies BEFORE the sort so the likes-you pinning
  // below operates on the filtered pool (pinned lane cards stay pinned).
  const sortedDeck = useMemo(() => {
    const pool = laneFilter ? deck.filter((c) => c.lane === laneFilter) : deck;
    if (fairnessOn) return pool;
    const pinned = pool.filter((c) => c.likesYou);
    const rest = pool
      .filter((c) => !c.likesYou)
      .sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
    return [...pinned, ...rest];
  }, [deck, fairnessOn, laneFilter]);

  // Lane pills render only when the engine actually laned this deck.
  const deckHasLanes = useMemo(() => deck.some((c) => !!c.lane), [deck]);

  function handleLaneFilter(lane: 'window' | 'value') {
    haptics.selection();
    setLaneFilter((prev) => (prev === lane ? null : lane));
    // The filtered deck is a different list — restart from its top.
    setDeckIdx(0);
  }

  // Player-swap (feedback #86): overlay the user's edited variant of the
  // top card, if any. Everything downstream — swipe/like, bad-trade flag,
  // Queue, Send in Sleeper — reads `topCard`, so an edit automatically
  // carries the MODIFIED package into every payload.
  const rawTopCard = sortedDeck[deckIdx];
  const topCard = rawTopCard ? edits[rawTopCard.trade_id] ?? rawTopCard : undefined;
  const nextCard = sortedDeck[deckIdx + 1];

  // Analytics: one trade_card_viewed per card reaching the top of the
  // deck (keyed on trade_id, so re-renders don't re-fire). The first card
  // additionally carries time-from-app-open + the cold-start marker.
  const topTradeId = rawTopCard?.trade_id;
  useEffect(() => {
    if (!topTradeId) return;
    const props: Record<string, unknown> = {
      card_index: deckIdx,
      trade_id: topTradeId,
    };
    if (deckIdx === 0) {
      props.ms_since_open = msSinceOpen();
      props.cold_start = sawServerWakeThisSession;
    }
    track('trade_card_viewed', props, 'Trades');
    // deckIdx intentionally omitted: a new top card always has a new
    // trade_id, and index-only changes (lane filter resets) re-show a
    // card that was already counted as viewed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topTradeId]);

  // ── Onboarding guided layer (onboarding.guided_layer AND .trades_first,
  // v2.1): coach marks 1–2. Each shows once ever (persisted at show time),
  // never modal, never stacked — if the swipe hint claims this mount, the
  // provenance mark waits for the next one.
  useEffect(() => {
    if (!guidedOn || !tradesFirstOn) return;
    if (guidedAvatarActive()) return; // The Analyst owns these surfaces
    if (swipeHintDone || swipeHintShownThisMountRef.current) return;
    if (!topTradeId || deckIdx !== 0) return;
    swipeHintShownThisMountRef.current = true;
    setSwipeHintActive(true);
    patchOnboardingState({ coachMarksShown: { swipe_hint: true } });
    track('coach_mark_shown', { mark: 'swipe_hint' }, 'Trades');
  }, [guidedOn, tradesFirstOn, swipeHintDone, topTradeId, deckIdx]);

  function dismissSwipeHint() {
    if (!swipeHintActive) return;
    setSwipeHintActive(false);
    track('coach_mark_dismissed', { mark: 'swipe_hint' }, 'Trades');
  }

  useEffect(() => {
    if (!guidedOn || !tradesFirstOn) return;
    if (guidedAvatarActive()) return; // s2.3 carries this line instead
    if (provenanceMarkDone || provenanceMarkShownRef.current) return;
    // Never stack: yield this mount to the swipe hint if it ran.
    if (swipeHintShownThisMountRef.current || swipeHintActive) return;
    // The mark anchors near the provenance chip, which needs a card.
    if (!topTradeId) return;
    provenanceMarkShownRef.current = true;
    setProvenanceMarkVisible(true);
    patchOnboardingState({ coachMarksShown: { provenance_chip: true } });
    track('coach_mark_shown', { mark: 'provenance_chip' }, 'Trades');
  }, [guidedOn, tradesFirstOn, provenanceMarkDone, topTradeId, swipeHintActive]);

  function dismissProvenanceMark() {
    if (!provenanceMarkVisible) return;
    setProvenanceMarkVisible(false);
    track('coach_mark_dismissed', { mark: 'provenance_chip' }, 'Trades');
  }

  // ── Guided tour (The Analyst; onboarding.guided_avatar) ──────────────
  // Owns the S2/S3/S5/S5.5/S6/S7/S8 beats on this screen. Passive surfaces
  // (swipe hint, coach marks, prompt card, diff banner, celebration toasts)
  // are suppressed while he's active — same triggers, same funnel events.
  const guideActive = useGuide((s) => s.active);
  const [guidedS3Pending, setGuidedS3Pending] = useState(false);
  const [guidedS55Done, setGuidedS55Done] = useState<string | null>(null);
  const guidePromptPos = fitTargetPositions?.[0] ?? 'WR';

  // Spotlight targets The Analyst points at on this screen.
  const deckWrapRef = useRef<View | null>(null);
  const chipWrapRef = useRef<View | null>(null);
  const trioWrapRef = useRef<View | null>(null);
  useEffect(() => {
    registerGuideTarget('trades.card-body', deckWrapRef);
    registerGuideTarget('trades.provenance-chip', chipWrapRef);
    registerGuideTarget('trades.trio-entry', trioWrapRef);
    return () => {
      unregisterGuideTarget('trades.card-body');
      unregisterGuideTarget('trades.provenance-chip');
      unregisterGuideTarget('trades.trio-entry');
    };
  }, []);

  // S2.wait — computing pose while the first deck generates.
  useEffect(() => {
    if (!guidedAvatarActive() || !firstRun) return;
    if (deck.length === 0 && (job?.status === 'running' || generateMutation.isPending)) {
      requestGuideStep(GUIDE.s2_wait(job?.opponents_total ?? null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstRun, deck.length, job?.status, generateMutation.isPending]);

  // Cards arrived: close S2.wait, open S2.1 (the market intro).
  useEffect(() => {
    if (deck.length === 0) return;
    advanceGuideIfActive('s2.wait');
    if (!guidedAvatarActive() || !firstRun) return;
    if (!getOnboardingState().guideSeen['s2.1']) {
      requestGuideStep(GUIDE.s2_1());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deck.length, firstRun]);

  // Chain steps that wait for the bubble slot to free up (one at a time).
  useEffect(() => {
    if (guideActive || !guidedAvatarActive()) return;
    const ob = getOnboardingState();
    // s2.1 → s2.2 (swipe coaching; advances on the real first swipe)
    if (ob.guideSeen['s2.1'] && !ob.guideSeen['s2.2'] && !ob.firstSwipeDone && topCard) {
      requestGuideStep(GUIDE.s2_2());
      return;
    }
    // s3.1 → s3.2 (the pitch, CTAs in the bubble)
    if (guidedS3Pending) {
      setGuidedS3Pending(false);
      requestGuideStep(
        GUIDE.s3_2(guidePromptPos, !!fitTargetPositions?.length),
        {
          onAccept: () => acceptQuicksetPrompt('prompt', guidePromptPos),
          onDismiss: () => snoozeQuicksetPrompt(),
        },
      );
      return;
    }
    // s5 reveal → s5.5 (directed next position; once per session)
    if (guidedS55Done && !guideS55ShownThisSession) {
      const done = getOnboardingState().quicksetCompletedPositions;
      const next = nextUnrankedPosition(done);
      const donePos = guidedS55Done;
      setGuidedS55Done(null);
      if (next) {
        guideS55ShownThisSession = true;
        requestGuideStep(GUIDE.s5_5(donePos, next), {
          onAccept: () => {
            track('quickset_prompt_accepted', { via: 'guide_next_pos' }, 'Trades');
            navigation.navigate('Rank', {
              screen: 'QuickSetTiers',
              params: { onboardingReturn: true, position: next },
            });
          },
        });
      }
      return;
    }
    // s6.1 seen → S8 sign-off (tour complete)
    if (ob.guideSeen['s6.1'] && !ob.guideSeen['s8.1'] && !ob.guideTourCompleted) {
      requestGuideStep(GUIDE.s8_1());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guideActive, guidedS3Pending, guidedS55Done, topCard]);

  // S8 advanced → tour formally completes (reactive-only mode thereafter).
  const s81Seen = useOnboardingState((s) => !!s.ob.guideSeen['s8.1']);
  useEffect(() => {
    if (s81Seen && !getOnboardingState().guideTourCompleted) {
      useGuide.getState().completeTour();
    }
  }, [s81Seen]);

  // ── Onboarding item 7: contextual Quick Set prompt + regen aha ───────
  // Trigger (round-3 ruling D2): first pass after swipe 2, else after 3
  // swipes. One show per session; snooze → one re-offer in session 2 →
  // retired (the provenance chip stays as the evergreen entry, F10).
  function maybeShowQuicksetPrompt(decision: 'like' | 'pass') {
    if (!quicksetPromptOn || quicksetPromptShownThisSession || quicksetPromptVisible) return;
    const ob = getOnboardingState();
    if (ob.quicksetPromptRetired || ob.quicksetCompletedPositions.length > 0) return;
    if (ob.quicksetPromptSnoozed && (ob.sessionCount < 2 || ob.quicksetPromptSession2Shown)) {
      return;
    }
    const swipes = ob.totalSwipes; // includes the swipe that got us here
    if (!((decision === 'pass' && swipes >= 2) || swipes >= 3)) return;
    quicksetPromptShownThisSession = true;
    patchOnboardingState({
      quicksetPromptShows: ob.quicksetPromptShows + 1,
      ...(ob.quicksetPromptSnoozed ? { quicksetPromptSession2Shown: true } : {}),
    });
    track('quickset_prompt_shown', { show_count: ob.quicksetPromptShows + 1 }, 'Trades');
    if (guidedAvatarActive()) {
      // Guided arm: The Analyst delivers the pitch (s3.1 → s3.2 with
      // in-bubble CTAs) instead of the inline prompt card. Same trigger,
      // same bookkeeping, same funnel event above.
      if (!getOnboardingState().guideSeen['s3.1']) {
        requestGuideStep(GUIDE.s3_1());
      }
      setGuidedS3Pending(true);
      return;
    }
    setQuicksetPromptVisible(true);
  }

  function snoozeQuicksetPrompt() {
    setQuicksetPromptVisible(false);
    const ob = getOnboardingState();
    // A snooze of the session-2 re-offer retires the auto-prompt for good.
    const retire = ob.quicksetPromptSnoozed && ob.quicksetPromptSession2Shown;
    patchOnboardingState(
      retire ? { quicksetPromptRetired: true } : { quicksetPromptSnoozed: true },
    );
    track('quickset_prompt_snoozed', { retired: retire }, 'Trades');
  }

  function acceptQuicksetPrompt(via: 'prompt' | 'chip' = 'prompt', position?: string) {
    setQuicksetPromptVisible(false);
    track('quickset_prompt_accepted', { via }, 'Trades');
    // Unknown routes bubble from the Trades stack up to the tab navigator.
    navigation.navigate('Rank', {
      screen: 'QuickSetTiers',
      params: { onboardingReturn: true, ...(position ? { position } : {}) },
    });
  }

  // Consume the QuickSet→Trades handoff on focus: snapshot the old deck,
  // force a fresh job (server cache key doesn't see board changes), and
  // let the diff effect below count what's new.
  useFocusEffect(
    useCallback(() => {
      const pos = consumePendingQuicksetRegen();
      if (!pos || !leagueId) return;
      pendingRegenRef.current = {
        position: pos,
        prevIds: new Set(deck.map((c) => c.trade_id)),
      };
      setDeckIdx(0);
      generateMutation.mutate({ force: true });
      // Item 8: first-Quick-Set-save celebration beat, then the Apple ask
      // for this save-moment class (win-then-ask; the diff banner that
      // follows is a passive receipt, not an ask).
      if (guidedOn && !getOnboardingState().celebrationsShown.first_quickset_save) {
        setToast({
          msg: "That's your board now. The deck rebuilds around it.",
          tone: 'success',
        });
        patchOnboardingState({ celebrationsShown: { first_quickset_save: true } });
        track('celebration_fired', { beat: 'first_quickset_save' }, 'Trades');
      }
      maybeAskApple('quickset_save');
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [deck, leagueId]),
  );

  // Diff banner (F2 — the aha receipt): once the forced job completes,
  // count cards that weren't in the pre-Quick-Set deck. Voice doc #9;
  // suppressed when nothing changed.
  useEffect(() => {
    const pending = pendingRegenRef.current;
    if (!pending || job?.status !== 'complete') return;
    pendingRegenRef.current = null;
    const fresh = deck.filter((c) => !pending.prevIds.has(c.trade_id)).length;
    track(
      'deck_regenerated',
      { position: pending.position, new_trades: fresh },
      'Trades',
    );
    if (guidedAvatarActive()) {
      // Guided arm: The Analyst delivers the reveal himself — celebrate on
      // new trades, honest oops on the null result (script S5.1/S5.0) —
      // then arms the S5.5 next-position ask via the chain effect.
      requestGuideStep(
        fresh > 0 ? GUIDE.s5_1(fresh, pending.position) : GUIDE.s5_0(pending.position),
      );
      setGuidedS55Done(pending.position);
      return;
    }
    if (fresh > 0) {
      setQuicksetDiffBanner({ position: pending.position, count: fresh });
      if (guidedOn && !getOnboardingState().coachMarksShown.diff_banner) {
        patchOnboardingState({ coachMarksShown: { diff_banner: true } });
        track('coach_mark_shown', { mark: 'diff_banner' }, 'Trades');
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status, deck]);

  // Banner auto-dismisses; it's a receipt, not a control.
  useEffect(() => {
    if (!quicksetDiffBanner) return;
    const t = setTimeout(() => setQuicksetDiffBanner(null), 8000);
    return () => clearTimeout(t);
  }, [quicksetDiffBanner]);

  // Deck exhausted (items 7+9): record it once per episode, and give the
  // snoozed Quick Set prompt its F10 re-offer slot (the once-per-session
  // cap inside maybeShowQuicksetPrompt still applies).
  const deckExhausted =
    !topCard &&
    deck.length > 0 &&
    job?.status !== 'running' &&
    !generateMutation.isPending;
  const exhaustedTrackedRef = useRef(false);
  useEffect(() => {
    if (!deckExhausted) {
      exhaustedTrackedRef.current = false;
      return;
    }
    if (exhaustedTrackedRef.current) return;
    exhaustedTrackedRef.current = true;
    track('deck_exhausted_viewed', { deck_size: deck.length }, 'Trades');
    maybeShowQuicksetPrompt('like'); // swipes ≥3 path; pass-trigger n/a here
    // Guided tour S7 — the trio ramp, pointed at the real CTA below (once
    // per session; never preempts an active bubble).
    if (guidedAvatarActive() && !guideS7ShownThisSession) {
      if (requestGuideStep(GUIDE.s7_1())) guideS7ShownThisSession = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deckExhausted]);

  // ── Onboarding item 8: save-moment Apple ask (ADR-006 policy) ────────
  // One auto-modal per save-moment class, ever; one ask per session across
  // classes; only for unverified, non-demo, Sleeper-keyed iOS sessions.
  // Eligibility predicate shared with the guided tour (s6.2 must not run
  // its setup line for an ask that will never fire).
  function appleAskEligible(cls: 'like' | 'quickset_save'): boolean {
    if (!appleSaveOn || appleAskShownThisSession || appleAsk) return false;
    if (Platform.OS !== 'ios' || isDemo || user?.account_only) return false;
    if (verification?.user_verified) return false;
    return !getOnboardingState().applePromptShownFor[cls];
  }

  function maybeAskApple(cls: 'like' | 'quickset_save') {
    if (!appleAskEligible(cls)) return;
    appleAskShownThisSession = true;
    patchOnboardingState(
      cls === 'like'
        ? { applePromptShownFor: { like: true } }
        : { applePromptShownFor: { quickset_save: true } },
    );
    // Win-then-ask: the celebration toast lands before the modal.
    setTimeout(() => {
      setAppleAsk(cls);
      track('apple_prompt_shown', { trigger: cls }, 'Trades');
    }, 700);
  }

  function closeAppleAsk(bound: boolean) {
    const cls = appleAsk;
    setAppleAsk(null);
    if (bound) {
      track('apple_prompt_accepted', { trigger: cls }, 'Trades');
      setToast({ msg: 'Apple ID linked — rankings saved to your account.', tone: 'success' });
    } else {
      patchOnboardingState({ applePromptDeclined: true });
      track('apple_prompt_declined', { trigger: cls }, 'Trades');
    }
  }

  function openSession2Banner() {
    patchOnboardingState({ appleSession2BannerShown: true });
    appleAskShownThisSession = true;
    setAppleAsk('session2_banner');
    track('apple_prompt_shown', { trigger: 'session2_banner' }, 'Trades');
  }

  function dismissSession2Banner() {
    patchOnboardingState({ appleSession2BannerShown: true });
    track('apple_banner_dismissed', undefined, 'Trades');
  }

  // Item 8 (G4) — user-initiated share of the last liked trade. Text +
  // link v1: rendering the card to an image needs a view-shot dependency,
  // deliberately deferred.
  async function shareLikedTrade() {
    const c = lastLikedCard;
    if (!c) return;
    const give = c.give_players.map((p) => p.name).join(' + ');
    const recv = c.receive_players.map((p) => p.name).join(' + ');
    try {
      const res = await Share.share({
        message:
          `Trade idea for our league: I send ${give}, get ${recv} from ` +
          `@${c.opponent_username}. Found on Fantasy Trade Finder — ` +
          'https://fantasy-trade-finder.onrender.com',
      });
      if (res.action !== Share.dismissedAction) {
        track('trade_card_shared', { trade_id: c.trade_id }, 'Trades');
      }
    } catch {
      /* share sheet canceled or unavailable — nothing to record */
    }
  }

  // ── Onboarding item 4 (F5): identity-confirm strip actions ───────────
  function handleIdentityNotYou() {
    Alert.alert(
      'Not your team?',
      `You're trading as @${user?.username || ''}. Sign out and enter a ` +
        'different Sleeper username?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Sign out',
          style: 'destructive',
          onPress: async () => {
            await useSession.getState().signOut();
            // Tab screens can't replace() on the root stack — reset via
            // the exported container ref (same target LeaguePicker/Settings
            // use for their sign-out paths).
            if (navigationRef.isReady()) {
              navigationRef.reset({ index: 0, routes: [{ name: 'SignIn' }] });
            }
          },
        },
      ],
    );
  }

  function handleIdentityDismiss() {
    identityStripDismissedThisSession = true;
    setIdentityStripVisible(false);
  }

  // Swap-sheet candidates: the tapped side's roster (give → yours,
  // receive → the counterparty's), minus everyone already in the trade
  // and anyone the consensus pool doesn't price (K/DST).
  const swapCandidates = useMemo<CalcValueRow[]>(() => {
    if (!swapTarget || !topCard) return [];
    const ownerId = swapTarget.side === 'give' ? userId : topCard.opponent_user_id;
    const rosterIds = rosterByOwner.get(ownerId) ?? [];
    const inTrade = new Set([
      ...topCard.give_player_ids,
      ...topCard.receive_player_ids,
    ]);
    return rosterIds
      .filter((id) => !inTrade.has(id))
      .map((id) => valueById.get(id))
      .filter((r): r is CalcValueRow => !!r);
  }, [swapTarget, topCard, rosterByOwner, valueById, userId]);

  function handleSwapPick(replacement: CalcValueRow) {
    if (!swapTarget || !rawTopCard || !topCard) return;
    const rawId = rawTopCard.trade_id;
    const { player: outgoing, side } = swapTarget;
    const incoming: Player = {
      id: replacement.id,
      name: replacement.name,
      position: replacement.position,
      team: replacement.team,
      age: replacement.age,
    };
    const swapIn = (arr: Player[]) =>
      arr.map((p) => (p.id === outgoing.id ? incoming : p));
    const give = side === 'give' ? swapIn(topCard.give_players) : topCard.give_players;
    const receive =
      side === 'receive' ? swapIn(topCard.receive_players) : topCard.receive_players;
    const editedCard: TradeCard = {
      ...topCard,
      trade_id: `${rawId}${EDITED_SUFFIX}`,
      give_players: give,
      receive_players: receive,
      give_player_ids: give.map((p) => p.id),
      receive_player_ids: receive.map((p) => p.id),
      edited: true,
      // The engine's numbers described the ORIGINAL package. Clear them —
      // the fairness meter hides while undefined and the re-price below
      // fills it back in; reasons/sweetener narrated the old package; the
      // counterparty's like was for the original mirror, not this variant.
      fairness: undefined as unknown as number,
      reasons: undefined,
      sweetener: undefined,
      likesYou: false,
    };
    setEdits((prev) => ({ ...prev, [rawId]: editedCard }));
    setSwapTarget(null);
    haptics.selection();
    // Mode B needs a real counterparty id; without one the card just shows
    // EDITED with no fairness read (shouldn't happen on generated cards).
    if (editedCard.opponent_user_id) {
      repriceMutation.mutate({ rawId, card: editedCard });
    }
  }

  function advance(decision: 'like' | 'pass') {
    if (!topCard) return;
    // Onboarding item 4: persist first-swipe + lifetime swipe count
    // (items 7/8 read these for the prompt-card and Apple-ask triggers).
    // Gated on ANY consumer feature so each flag works independently
    // (individual enablement); flags-off leaves no writes behind.
    if (
      onboardingEnabled('onboarding.trades_first') ||
      onboardingEnabled('onboarding.quickset_prompt') ||
      onboardingEnabled('onboarding.apple_save_moment')
    ) {
      patchOnboardingState({
        firstSwipeDone: true,
        totalSwipes: getOnboardingState().totalSwipes + 1,
      });
    }
    maybeShowQuicksetPrompt(decision);
    // Guided tour: the real swipe advances the s2.2 coaching step; s2.3
    // (the provenance-chip beat) follows immediately in the freed slot.
    if (guidedAvatarActive()) {
      advanceGuideIfActive('s2.2');
      const seen = getOnboardingState().guideSeen;
      if (seen['s2.2'] && !seen['s2.3']) {
        requestGuideStep(GUIDE.s2_3());
      }
    }
    // Guided layer: any disposition (swipe or button) retires an active
    // swipe hint — the card it pointed at is leaving.
    if (swipeHintActive) dismissSwipeHint();
    swipeMutation.mutate({ card: topCard, decision });
    setDeckIdx((i) => i + 1);
    if (decision === 'like') {
      haptics.success();
      // Item 8: remember the liked card for the share affordance, fire the
      // first-like celebration beat (guided layer), then the Apple ask —
      // win-then-ask ordering, never two overlapping surfaces.
      setLastLikedCard(topCard);
      const firstLike = !getOnboardingState().celebrationsShown.first_like;
      if (guidedAvatarActive()) {
        // Guided arm: s6.1 celebrate replaces the toast; the honest Apple
        // setup line (s6.2) precedes the system sheet, which opens after
        // the auto-step clears (never two overlapping surfaces).
        if (firstLike) {
          patchOnboardingState({ celebrationsShown: { first_like: true } });
          track('celebration_fired', { beat: 'first_like' }, 'Trades');
          requestGuideStep(GUIDE.s6_1());
        } else {
          setToast({ msg: 'Liked', tone: 'success' });
        }
        if (!getOnboardingState().guideSeen['s6.2'] && appleAskEligible('like')) {
          setTimeout(() => {
            requestGuideStep(GUIDE.s6_2());
            setTimeout(() => maybeAskApple('like'), 2800);
          }, firstLike ? 2400 : 0);
        } else {
          maybeAskApple('like');
        }
      } else {
        let likeToast = 'Liked';
        if (guidedOn && firstLike) {
          likeToast = 'First target logged. Your front office is open for business.';
          patchOnboardingState({ celebrationsShown: { first_like: true } });
          track('celebration_fired', { beat: 'first_like' }, 'Trades');
        }
        setToast({ msg: likeToast, tone: 'success' });
        maybeAskApple('like');
      }
    } else {
      haptics.swipe();
    }
  }

  // Bad-trade flag (feedback #85): file the engine-quality flag, then move
  // past the card exactly like a pass — flagging implies "not interested",
  // so the pass swipe records the disposition while the flag row records
  // "the engine got this one wrong" for operator review.
  function handleFlagBadTrade() {
    if (!topCard) return;
    // No reason field in the mobile flag flow (flagBadTrade's `reason`
    // param is unused here), so the event carries the trade id only.
    track('trade_flagged', { trade_id: topCard.trade_id }, 'Trades');
    flagMutation.mutate(topCard);
    advance('pass');
    setToast({ msg: 'Flagged — thanks, this trains the engine', tone: 'success' });
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

  const topCardQueued = topCard ? isQueued(topCard.trade_id) : false;

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
        // Phase-2: with no saved outlook, preselect the backend's
        // roster-inferred guess so "Change" opens on the right option.
        initial={prefsQuery.data?.team_outlook ?? inferredOutlook}
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
          <ActivityIndicator color={ice.base} size="large" />
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
        {/* Onboarding item 4 (F5) — first-run identity confirm. A valid-
            but-wrong username silently loads a stranger's team; this is
            the escape hatch. Session-dismissible; demo sessions skip it. */}
        {firstRun && identityStripVisible && !isDemo && user?.username ? (
          <IdentityConfirmStrip
            username={user.username}
            avatarId={user.avatar_id}
            onNotYou={handleIdentityNotYou}
            onDismiss={handleIdentityDismiss}
          />
        ) : null}

        {/* B7 — new-partners alert. Banner self-dismisses via AsyncStorage
            keyed on the latest partner; renders null when the flag is off
            (query is gated upstream) or there are no new partners.
            First-run (onboarding item 4): pre-deck chrome — deferred. */}
        {!firstRun && newPartnersFlag && leagueId && userId && (newPartnersQuery.data?.partners?.length ?? 0) > 0 ? (
          <NewPartnersBanner
            partners={newPartnersQuery.data!.partners}
            userId={userId}
            leagueId={leagueId}
          />
        ) : null}

        {/* Cold-start invite nudge — no league-mate has ranked yet, so the
            divergence engine has nothing to work with. First-run: deferred
            until after the first swipe (onboarding item 4 / F11). */}
        {!firstRun && showInviteBanner && leagueId ? (
          <InviteLeaguematesBanner
            leagueId={leagueId}
            leagueName={league?.league_name}
            username={user?.username}
            total={coverage!.total}
          />
        ) : null}

        {/* B3 — Sub-route pills. Trades is the active screen here;
            Portfolio only shows when the user has 2+ connected leagues.
            Calculator (manual trade builder, demo data) is always
            reachable — it needs no league. Chalkline chip construction:
            1px border + label type on ink; active = ink-3 well + chalk. */}
        {!firstRun && (
        <View style={styles.subnavRow}>
          <View testID="trades.subnav.trades" style={[styles.subnavPill, styles.subnavPillActive]}>
            <Text style={[styles.subnavPillText, styles.subnavPillTextActive]}>
              Trades
            </Text>
          </View>
          {showPortfolioPill ? (
            <Pressable
              testID="trades.subnav.portfolio"
              onPress={() => navigation?.navigate?.('Portfolio')}
              style={({ pressed }) => [
                styles.subnavPill,
                pressed && styles.subnavPillPressed,
              ]}
            >
              <Text style={styles.subnavPillText}>Portfolio</Text>
            </Pressable>
          ) : null}
          <Pressable
            testID="trades.subnav.calculator"
            onPress={() => navigation?.navigate?.('TradeCalculator')}
            style={({ pressed }) => [
              styles.subnavPill,
              pressed && styles.subnavPillPressed,
            ]}
          >
            <Text style={styles.subnavPillText}>Calculator</Text>
          </Pressable>
        </View>
        )}

        {/* League selector pill — opens LeagueSwitcherSheet on tap.
            First-run: chrome-collapsed (LeagueSwitcherSheet stays reachable
            post-first-run; league choice just happened at the picker). */}
        {!firstRun && (
        <LeaguePill
          label="Trading in"
          onPress={() => setSwitcherOpen(true)}
        />
        )}

        {/* FB4-59 — single-format gate. When the league resolves to only the
            OTHER scoring format, show the gate in place of the trade UI;
            otherwise the normal Chalkline controls + deck render. */}
        {gateState ? (
          <FormatGate
            neededFormat={gateState.needed}
            setFormat={gateState.set}
            copying={copyFormatMutation.isPending}
            onCopy={() => onGateCopy(gateState)}
            onSetUpManually={onGateSetUpManually}
          />
        ) : (
        <>
        {/* Onboarding item 4 (accepted F11): first-run collapses this card
            to ONE control row — just Find a Trade + the progress strip.
            Outlook editing stays reachable via the inferred-outlook banner;
            everything else returns on the next mount after the first swipe. */}
        <Card>
          <View style={styles.controlInner}>
          {!firstRun && (
          <View style={styles.controlRow}>
            <View style={{ flex: 1 }}>
              <TickLabel>Outlook</TickLabel>
              <Text style={styles.controlValue}>
                {prefsQuery.data?.team_outlook
                  ? cap(prefsQuery.data.team_outlook)
                  : 'Not set'}
              </Text>
            </View>
            <Button
              variant="secondary"
              compact
              label="Edit"
              onPress={() => setOutlookOpen(true)}
            />
          </View>
          )}

          {/* Trade-fairness toggle. ON: backend filters to balanced
              trades and sorts by composite_score (fairness-weighted).
              OFF: broaden the backend filter to its loosest and re-sort
              the deck client-side by ranking mismatch (the ELO gap
              between owners on the swapped players). Rendered as the
              Chalkline slider construction: 4px ink-3 track, 16px square
              ice thumb — same boolean semantics as before. */}
          {!firstRun && (
          <View style={styles.fairnessRow}>
            <View style={{ flex: 1 }}>
              <TickLabel>Trade fairness</TickLabel>
              <Text style={styles.fairnessHint}>
                {fairnessOn
                  ? 'Recommend balanced trades'
                  : 'Rank by ranking mismatch only'}
              </Text>
            </View>
            <Pressable
              onPress={() => handleToggleFairness(!fairnessOn)}
              accessibilityRole="switch"
              accessibilityLabel="Trade fairness"
              accessibilityState={{ checked: fairnessOn }}
              style={styles.fairnessSliderTap}
              hitSlop={8}
            >
              <View style={styles.fairnessTrack}>
                <View
                  style={[
                    styles.fairnessThumb,
                    fairnessOn ? styles.fairnessThumbOn : styles.fairnessThumbOff,
                  ]}
                />
              </View>
            </Pressable>
          </View>
          )}

          {/* Phase-2 lane filter — Window moves / Value moves pills with an
              implicit All state (tap the active pill to clear). Mirrors the
              FB-47 direction-toggle construction; renders only when the
              deck actually carries lanes. */}
          {!firstRun && deckHasLanes && (
            <View style={styles.targetDirRow}>
              {(
                [
                  ['window', 'Window moves'],
                  ['value', 'Value moves'],
                ] as const
              ).map(([lane, label]) => {
                const active = laneFilter === lane;
                return (
                  <Pressable
                    key={lane}
                    onPress={() => handleLaneFilter(lane)}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                    style={({ pressed }) => [
                      styles.targetDirPill,
                      active && styles.targetDirPillActive,
                      pressed && styles.subnavPillPressed,
                    ]}
                  >
                    <Text
                      style={[
                        styles.subnavPillText,
                        active && styles.subnavPillTextActive,
                      ]}
                    >
                      {label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          )}

          {/* FB-47 — finder targeting (flag trade.finder_targeting).
              Direction toggle (Trade away / Acquire) + player picker.
              Position-level targeting stays in OutlookSheet's chips; this
              is the player-level entry point. Chip construction mirrors
              the subnav pills. */}
          {!firstRun && targetingEnabled && (
            <View style={styles.targetSection}>
              <View style={styles.controlRow}>
                <View style={{ flex: 1 }}>
                  <TickLabel>Target players</TickLabel>
                  <Text style={styles.fairnessHint}>
                    {targetDirection === 'trade_away'
                      ? 'Trades will send a targeted player'
                      : 'Trades will get you a targeted player'}
                  </Text>
                </View>
                <Button
                  variant="secondary"
                  compact
                  label="Add player"
                  onPress={() => setTargetPickerOpen(true)}
                />
              </View>
              <View style={styles.targetDirRow}>
                {(
                  [
                    ['trade_away', 'Trade away'],
                    ['acquire', 'Acquire'],
                  ] as const
                ).map(([dir, label]) => {
                  const active = targetDirection === dir;
                  return (
                    <Pressable
                      key={dir}
                      onPress={() => setTargetDirection(dir)}
                      accessibilityRole="button"
                      accessibilityState={{ selected: active }}
                      style={({ pressed }) => [
                        styles.targetDirPill,
                        active && styles.targetDirPillActive,
                        pressed && styles.subnavPillPressed,
                      ]}
                    >
                      <Text
                        style={[
                          styles.subnavPillText,
                          active && styles.subnavPillTextActive,
                        ]}
                      >
                        {label}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
              {(pinnedGive.length > 0 || pinnedReceive.length > 0) && (
                <View style={styles.targetChipsWrap}>
                  {pinnedGive.map((p) => (
                    <Pressable
                      key={`send-${p.id}`}
                      onPress={() => handleRemoveTarget(p.id, 'trade_away')}
                      accessibilityRole="button"
                      accessibilityLabel={`Remove ${p.name} from trade-away targets`}
                      style={({ pressed }) => [
                        styles.targetChip,
                        pressed && styles.subnavPillPressed,
                      ]}
                    >
                      <Text style={styles.targetChipDir}>SEND</Text>
                      <Text style={styles.subnavPillText}>{p.name}</Text>
                      <Icon name="x" size={12} color={chalk.dim} />
                    </Pressable>
                  ))}
                  {pinnedReceive.map((p) => (
                    <Pressable
                      key={`get-${p.id}`}
                      onPress={() => handleRemoveTarget(p.id, 'acquire')}
                      accessibilityRole="button"
                      accessibilityLabel={`Remove ${p.name} from acquire targets`}
                      style={({ pressed }) => [
                        styles.targetChip,
                        pressed && styles.subnavPillPressed,
                      ]}
                    >
                      <Text style={styles.targetChipDir}>GET</Text>
                      <Text style={styles.subnavPillText}>{p.name}</Text>
                      <Icon name="x" size={12} color={chalk.dim} />
                    </Pressable>
                  ))}
                </View>
              )}
            </View>
          )}

          {/* Find-a-Trade button. While a job is running, the button is
              disabled — the progress strip below acts as the live signal.
              `generateMutation.isPending` is only true during the brief
              POST round-trip; after that, status flows through `job`. */}
          <Button
            variant="primary"
            testID="trades.find-btn"
            label={deck.length > 0 && job?.status === 'complete' ? 'Find more trades' : 'Find a Trade'}
            disabled={!leagueId || generateMutation.isPending || job?.status === 'running'}
            onPress={() => {
              track('find_trades_tapped', undefined, 'Trades');
              generateMutation.mutate({});
            }}
            style={styles.findBtn}
          />

          {/* Progress strip — visible only during a running job. Cards are
              streaming into the deck above; this just narrates the work.
              Opponent coverage renders as a ice Meter with mono counts. */}
          {job?.status === 'running' && (
            <View testID="trades.progress-strip" style={styles.progressStrip}>
              <View style={styles.progressInfo}>
                <ActivityIndicator color={chalk.dim} size="small" />
                <Text style={styles.progressText}>
                  {'Searching… '}
                  <Text style={type.data}>
                    {`${job.opponents_done}/${job.opponents_total || '?'}`}
                  </Text>
                  {' opponents'}
                  {job.cards.length > 0 ? '  ·  ' : ''}
                  {job.cards.length > 0 ? (
                    <Text style={type.data}>{job.cards.length}</Text>
                  ) : null}
                  {job.cards.length > 0 ? ` trade${job.cards.length === 1 ? '' : 's'}` : ''}
                </Text>
                {/* "Hide", not "Stop": the server-side worker keeps running
                    so its results land in the warm cache for the next tap.
                    We just dismiss the in-progress UI on the client. */}
                <Button
                  variant="ghost"
                  compact
                  label="Hide"
                  onPress={() => setJob(null)}
                />
              </View>
              <Meter
                value={(job.opponents_done ?? 0) / Math.max(job.opponents_total || 0, 1)}
              />
            </View>
          )}

          {!firstRun && likedQuery.data && likedQuery.data.liked_count > 0 && (
            <Text style={styles.likedCount}>
              <Text style={type.data}>{likedQuery.data.liked_count}</Text>
              {` liked trade${likedQuery.data.liked_count === 1 ? '' : 's'} awaiting their swipe`}
            </Text>
          )}
          </View>
        </Card>

        {/* Phase-2 one-tap outlook confirm — replaces the force-opened
            OutlookSheet when the backend inferred an outlook from the
            roster. Confirm saves the inference with empty position prefs;
            Change opens the sheet (preselected) as before. Bordered-chalk
            (secondary) Confirm — the screen's ice budget is already spent
            (fairness thumb, Find a Trade, queued state). */}
        {inferredOutlook && (
          <View style={styles.inferredBanner}>
            <Text style={type.body}>
              Your roster reads as {cap(inferredOutlook)}.
            </Text>
            <View style={styles.inferredActions}>
              <Button
                variant="secondary"
                compact
                label="Confirm"
                disabled={confirmOutlookMutation.isPending || !leagueId}
                onPress={() => confirmOutlookMutation.mutate(inferredOutlook)}
              />
              <Button
                variant="ghost"
                compact
                label="Change"
                disabled={confirmOutlookMutation.isPending}
                onPress={() => setOutlookOpen(true)}
              />
            </View>
          </View>
        )}

        {/* Onboarding item 4 — provenance chip: which value basis built
            this deck. Deck-level (state is global to every card); item 7
            wires its tap-through to Quick Set. Coach mark 2 (guided layer)
            anchors directly beneath it, once, never stacked with the
            swipe hint. */}
        {/* Item 10 — demo→real bridge: the one demo investment (Q6). */}
        {demoBridgeOn && isDemo ? (
          <Pressable
            testID="trades.demo-bridge"
            style={styles.demoBridge}
            onPress={async () => {
              track('demo_bridge_tapped', undefined, 'Trades');
              // Landing is the username field — signing out routes there
              // (same container-ref reset the identity strip uses).
              await useSession.getState().signOut();
              if (navigationRef.isReady()) {
                navigationRef.reset({ index: 0, routes: [{ name: 'SignIn' }] });
              }
            }}
          >
            {({ pressed }) => (
              <Text style={[styles.demoBridgeText, pressed && { color: chalk.base }]}>
                Sample league. See this for YOUR team →
              </Text>
            )}
          </Pressable>
        ) : null}
        {/* Item 10 (F12) — honest label for redraft leagues. */}
        {demoBridgeOn && isRedraftLeague && !isDemo ? (
          <View testID="trades.redraft-label" style={styles.redraftLabel}>
            <Text style={styles.redraftLabelText}>Dynasty values shown</Text>
          </View>
        ) : null}
        {tradesFirstOn && topCard ? (
          <View ref={chipWrapRef} collapsable={false} style={{ alignSelf: 'flex-start' }}>
          <ProvenanceChip
            personalized={quicksetPositions.length > 0}
            // Item 7 (F10): the chip is the evergreen Quick Set entry once
            // the auto-prompt retires. Tap-through only while the prompt
            // feature is live and the board is still consensus.
            onPress={
              quicksetPromptOn && quicksetPositions.length === 0
                ? () => acceptQuicksetPrompt('chip')
                : undefined
            }
          />
          </View>
        ) : null}
        {quicksetDiffBanner ? (
          <View testID="trades.diff-banner" style={styles.diffBanner}>
            <Text style={styles.diffBannerText}>
              Re-ranked with your {quicksetDiffBanner.position} board —{' '}
              {quicksetDiffBanner.count} new trade
              {quicksetDiffBanner.count === 1 ? '' : 's'}.
            </Text>
          </View>
        ) : null}
        {/* Item 8 (round-3 D1): session-2 NON-MODAL Apple banner — the one
            softer ask for unbound users with real swipe investment. Shown
            until acted on or dismissed, then never again (persisted). */}
        {appleSaveOn &&
        !appleAsk &&
        Platform.OS === 'ios' &&
        !isDemo &&
        !user?.account_only &&
        !verification?.user_verified &&
        obSessionCount >= 2 &&
        obTotalSwipes >= 5 &&
        !session2BannerShown ? (
          <View testID="trades.apple-session2-banner" style={styles.appleBanner}>
            <Pressable style={styles.appleBannerBody} onPress={openSession2Banner} hitSlop={4}>
              <Text style={styles.appleBannerText}>
                {obTotalSwipes} swipes on this board. Sign in with Apple to
                save your rankings to your account →
              </Text>
            </Pressable>
            <Pressable
              testID="trades.apple-session2-banner.dismiss"
              onPress={dismissSession2Banner}
              hitSlop={8}
            >
              {({ pressed }) => (
                <Text style={[styles.appleBannerDismiss, pressed && { color: chalk.base }]}>
                  Dismiss
                </Text>
              )}
            </Pressable>
          </View>
        ) : null}
        {tradesFirstOn && guidedOn && provenanceMarkVisible && topCard ? (
          <CoachMark
            testID="trades.coach-mark.provenance"
            text="These are consensus values. After Quick Set, they're yours."
            onDismiss={dismissProvenanceMark}
          />
        ) : null}

        <View style={styles.deckWrap} ref={deckWrapRef} collapsable={false}>
          {quicksetPromptVisible ? (
            // Item 7 — inline prompt card holds the top-of-deck slot until
            // answered; the deck resumes underneath on either action.
            <QuickSetPromptCard
              onAccept={() => acceptQuicksetPrompt('prompt')}
              onDismiss={snoozeQuicksetPrompt}
            />
          ) : topCard ? (
            <>
              {/* Peek of the next card behind the top one. Clipped to the
                  TOP card's measured height (#107/#110): a taller next card
                  (2 player tiles behind a 1-player top) would otherwise poke
                  its extra tile out below the top card. The wrapper keeps
                  the stack aesthetic — 8px downward offset, scale, dim, and
                  the card-radius clip edge — so at most the 8px offset strip
                  ever peeks; content can never render beyond the top card's
                  bounds. A shorter next card is unaffected (it already fits).
                  Hidden until the first onLayout lands (one frame). */}
              {nextCard && topCardH != null && (
                <View
                  style={[styles.cardStack, styles.cardBehind, { height: topCardH }]}
                >
                  <TradeCardComp
                    data={nextCard}
                    untouchableIds={untouchablesEnabled ? untouchableIds : undefined}
                    fitTargetPositions={fitTargetPositions}
                  />
                </View>
              )}
              <SwipableTopCard
                key={topCard.trade_id}
                card={topCard}
                nudge={swipeHintActive}
                onFirstTouch={dismissSwipeHint}
                onCardLayout={(e) => setTopCardH(e.nativeEvent.layout.height)}
                onLike={() => advance('like')}
                onPass={() => advance('pass')}
                untouchableIds={untouchablesEnabled ? untouchableIds : undefined}
                onToggleUntouchable={
                  untouchablesEnabled ? handleToggleUntouchable : undefined
                }
                onSwapPlayer={(player, side) => setSwapTarget({ player, side })}
                repricing={topCard.edited === true && repriceMutation.isPending}
                fitTargetPositions={fitTargetPositions}
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
                    topCardQueued && styles.queueBtnQueued,
                    pressed && styles.queueBtnPressed,
                  ]}
                >
                  <Icon
                    name={topCardQueued ? 'check' : 'plus'}
                    size={16}
                    color={topCardQueued ? chalk.base : chalk.dim}
                  />
                  <Text
                    style={[
                      styles.queueBtnText,
                      topCardQueued && styles.queueBtnTextQueued,
                    ]}
                  >
                    {topCardQueued ? 'Queued' : 'Queue'}
                  </Text>
                </Pressable>
              ) : null}
              {/* Send in Sleeper — flagged beta. Directly proposes THIS found
                  trade to the opponent (skips the mutual-match wait). Hides
                  itself when trade.send_in_sleeper is off. */}
              <SendInSleeperButton
                leagueId={topCard.league_id}
                theirUserId={topCard.opponent_user_id}
                givePlayerIds={topCard.give_player_ids}
                receivePlayerIds={topCard.receive_player_ids}
                compact
                style={styles.sendInSleeper}
              />
              {/* Check / X disposition buttons — same outcome as swiping
                  right/left. Both wire to advance() so deck-advance, haptics,
                  and the API call are identical to the swipe path. Disabled
                  while a swipe mutation is in flight to prevent double-firing. */}
              <View style={styles.dispositionRow}>
                <Pressable
                  testID="trades.pass-btn"
                  onPress={() => advance('pass')}
                  disabled={swipeMutation.isPending}
                  style={({ pressed }) => [
                    styles.dispositionBtn,
                    styles.dispositionBtnPass,
                    pressed && styles.dispositionBtnPassPressed,
                    swipeMutation.isPending && styles.dispositionDisabled,
                  ]}
                  accessibilityLabel="Pass on this trade"
                  accessibilityRole="button"
                >
                  {({ pressed }) => (
                    <Icon name="x" color={pressed ? ink.ink0 : semantic.neg} />
                  )}
                </Pressable>
                <Pressable
                  testID="trades.like-btn"
                  onPress={() => advance('like')}
                  disabled={swipeMutation.isPending}
                  style={({ pressed }) => [
                    styles.dispositionBtn,
                    styles.dispositionBtnLike,
                    pressed && styles.dispositionBtnLikePressed,
                    swipeMutation.isPending && styles.dispositionDisabled,
                  ]}
                  accessibilityLabel="Accept this trade"
                  accessibilityRole="button"
                >
                  {({ pressed }) => (
                    <Icon name="check" color={pressed ? ink.ink0 : semantic.pos} />
                  )}
                </Pressable>
              </View>
              <Text style={styles.deckHint}>
                Swipe right to like · Swipe left to pass
              </Text>
              {/* Bad-trade flag (feedback #85) — tertiary to like/pass, so it
                  sits below the disposition row at hint-level prominence.
                  Tapping files an engine-quality flag (operator review, not
                  an ELO signal) and advances the deck like a pass. */}
              <Pressable
                onPress={handleFlagBadTrade}
                disabled={swipeMutation.isPending}
                style={({ pressed }) => [
                  styles.badTradeBtn,
                  pressed && styles.badTradeBtnPressed,
                  swipeMutation.isPending && styles.dispositionDisabled,
                ]}
                accessibilityLabel="Flag as a bad trade suggestion"
                accessibilityRole="button"
              >
                <Icon name="flag" size={14} color={chalk.dim} />
                <Text style={styles.badTradeText}>Bad trade?</Text>
              </Pressable>
              {/* Item 8 (G4) — user-initiated share of the last liked trade.
                  Appears only after a like, never alongside the Apple ask
                  (prompt resolves first, ruling: never two CTAs at the peak
                  moment). */}
              {shareSheetOn && lastLikedCard && !appleAsk ? (
                <Pressable
                  testID="trades.share-liked"
                  onPress={() => void shareLikedTrade()}
                  style={styles.shareRow}
                  hitSlop={8}
                >
                  {({ pressed }) => (
                    <Text style={[styles.shareRowText, pressed && { color: chalk.base }]}>
                      Share your last liked trade →
                    </Text>
                  )}
                </Pressable>
              ) : null}
            </>
          ) : firstRun &&
            deck.length === 0 &&
            job?.status !== 'complete' &&
            job?.status !== 'error' &&
            !autoGenFailed ? (
            // Onboarding item 4 — first-run skeleton deck: generation was
            // auto-started (or pregenerated at auth-return) and cards are
            // streaming in; the manual "Hit Find a Trade" empty state never
            // shows on first run. Falls through to the normal states if the
            // job completes empty or the silent auto-start gives up.
            <SkeletonTradeCard />
          ) : generateMutation.isPending || job?.status === 'running' ? (
            // Job is running but no cards have arrived yet (first ~3s of
            // the first opponent). Show a placeholder so the deck doesn't
            // look broken — the progress strip above narrates state.
            <Card>
              <View style={styles.emptyInner}>
                <ActivityIndicator color={ice.base} />
                <Text style={[styles.emptyTitle, { marginTop: space.sm }]}>
                  Looking for trades…
                </Text>
                <Text style={styles.emptyBody}>
                  Cards will appear here as they're found. First few should land within a few seconds.
                </Text>
              </View>
            </Card>
          ) : deck.length > 0 ? (
            <Card>
              <View style={styles.emptyInner}>
                <Text style={styles.emptyTitle}>That's all for now</Text>
                {rankRoutingOn ? (
                  // Item 9 (F8): the dead-end becomes the trio-habit ramp —
                  // the push-independent path to the daily sharpening loop.
                  <>
                    <Text style={styles.emptyBody}>
                      You've seen every trade. Sharpen your board with quick
                      head-to-heads →
                    </Text>
                    <View ref={trioWrapRef} collapsable={false} style={{ alignSelf: 'center' }}>
                    <Button
                      testID="trades.trio-entry"
                      label="Quick head-to-heads"
                      variant="secondary"
                      compact
                      onPress={() => {
                        advanceGuideIfActive('s7.1');
                        track('trio_entry_tapped', { from: 'deck_exhausted' }, 'Trades');
                        navigation.navigate('Rank', { screen: 'Trios' });
                      }}
                    />
                    </View>
                  </>
                ) : (
                  <Text style={styles.emptyBody}>
                    You've swiped on every generated trade. Rank more players or
                    invite leaguemates to unlock more.
                  </Text>
                )}
              </View>
            </Card>
          ) : (
            <Card>
              <View style={styles.emptyInner}>
                <Text testID="trades.empty-text" style={styles.emptyTitle}>Hit "Find a Trade" to start</Text>
                <Text style={styles.emptyBody}>
                  We'll pull trade ideas from your league and show them one at a time.
                </Text>
              </View>
            </Card>
          )}
        </View>
        </>
        )}
      </ScrollView>

      {/* Queue footer bar — anchored above the bottom tab nav. Tap the
          left side to expand the queue sheet; tap "Send All" to fire the
          staggered Sleeper deep-links and clear. Flag-gated. */}
      {queueEnabled && queuedTrades.length > 0 ? (
        <View style={styles.queueFooter}>
          <Pressable
            onPress={() => setQueueSheetOpen(true)}
            style={({ pressed }) => [
              styles.queueFooterTap,
              pressed && styles.queueFooterTapPressed,
            ]}
          >
            <Text style={styles.queueFooterCount}>{queuedTrades.length}</Text>
            <Text style={styles.queueFooterLabel}>
              queued · tap to review
            </Text>
          </Pressable>
          <Button
            variant="primary"
            compact
            label="Send All"
            onPress={handleSendAll}
          />
        </View>
      ) : null}

      {/* Queue bottom-sheet — lists each queued trade with dequeue. */}
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
              <Text style={type.data}>{queuedTrades.length}</Text>
              {' queued · "Send All" opens each on Sleeper'}
            </Text>
          </View>

          <ScrollView style={styles.queueSheetScroll} contentContainerStyle={{ gap: space.sm }}>
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
            <Button
              variant="secondary"
              label="Close"
              onPress={() => setQueueSheetOpen(false)}
              style={styles.queueSheetCancel}
            />
            <Button
              variant="primary"
              label="Send All"
              disabled={queuedTrades.length === 0}
              onPress={handleSendAll}
              style={styles.queueSheetSend}
            />
          </View>
        </View>
      </Modal>

      {/* Player-swap sheet (feedback #86) — replace one player on the top
          card with someone from the same roster. Suggested section = roster
          players within a tight value band of the outgoing player (#109);
          full roster below, grouped QB → RB → WR → TE. */}
      <SwapPlayerSheet
        visible={!!swapTarget}
        replacing={
          swapTarget
            ? {
                name: swapTarget.player.name,
                value: valueById.get(swapTarget.player.id)?.value ?? null,
              }
            : null
        }
        rosterLabel={
          swapTarget?.side === 'give'
            ? 'your roster'
            : topCard?.opponent_username
            ? `@${topCard.opponent_username}'s roster`
            : 'their roster'
        }
        candidates={swapCandidates}
        loading={valuesQuery.isLoading || rostersQuery.isLoading}
        onPick={handleSwapPick}
        onClose={() => setSwapTarget(null)}
      />

      {/* FB-47 — target picker. Trade away = the user's roster; Acquire =
          every leaguemate's roster (@owner badge per row). Reuses the
          calculator's search + position-filter picker; picking keeps the
          sheet open so multiple targets can be stacked, Done closes. */}
      <PlayerPickerModal
        visible={targetPickerOpen}
        title={
          targetDirection === 'trade_away'
            ? 'Target players to trade away'
            : 'Target players to acquire'
        }
        players={targetPickerPool}
        selectedIds={(targetDirection === 'trade_away' ? pinnedGive : pinnedReceive).map(
          (p) => p.id,
        )}
        ownerBoardValue={(p) => p.base}
        badgeFor={
          targetDirection === 'acquire'
            ? (p) => {
                const ownerId = ownerByPlayerId.get(p.id);
                const name = ownerId ? usernameByOwner.get(ownerId) : undefined;
                return name ? { label: `@${name}`, color: chalk.dim } : null;
              }
            : undefined
        }
        onPick={handleAddTarget}
        onClose={() => setTargetPickerOpen(false)}
      />

      {/* Item 8 — save-moment Apple ask (ADR-006 honest framing). */}
      <AppleSaveMomentSheet
        visible={!!appleAsk}
        trigger={appleAsk ?? 'like'}
        onClose={closeAppleAsk}
      />
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
  // #107/#110 — reports the card's laid-out height so the deck can clip
  // the behind-card peek to the top card's bounds. onLayout height is the
  // pre-transform layout box, so the swipe translation never re-fires it.
  onCardLayout: (e: LayoutChangeEvent) => void;
  onLike: () => void;
  onPass: () => void;
  untouchableIds?: ReadonlySet<string>;
  onToggleUntouchable?: (player: Player) => void;
  // Player-swap (feedback #86) — pass-throughs to TradeCard.
  onSwapPlayer?: (player: Player, side: 'give' | 'receive') => void;
  repricing?: boolean;
  // FB-47 — pass-through to TradeCard's partner-fit line copy.
  fitTargetPositions?: string[];
  // Onboarding guided layer (v2.1): swipe-gesture hint. While `nudge` is
  // true the card runs a subtle translateX nudge (twice, then rests);
  // the first touch anywhere on the card calls `onFirstTouch` — the
  // parent flips `nudge` off and the cleanup springs the card home. The
  // swipe itself remains the tutorial; no overlay, no modal.
  nudge?: boolean;
  onFirstTouch?: () => void;
}

function SwipableTopCard({
  card,
  onCardLayout,
  onLike,
  onPass,
  untouchableIds,
  onToggleUntouchable,
  onSwapPlayer,
  repricing,
  fitTargetPositions,
  nudge,
  onFirstTouch,
}: SwipableProps) {
  const translateX = useSharedValue(0);

  // Guided-layer nudge: two gentle right-and-back beats after a short
  // settle delay. Any touch dismisses (see onTouchStart below); a live
  // pan assignment overrides the animation frame-for-frame regardless.
  useEffect(() => {
    if (!nudge) return;
    translateX.value = withDelay(
      600,
      withRepeat(
        withSequence(
          withTiming(28, { duration: 320, easing: Easing.out(Easing.cubic) }),
          withTiming(0, { duration: 320, easing: Easing.out(Easing.cubic) }),
        ),
        2,
      ),
    );
    return () => {
      cancelAnimation(translateX);
      translateX.value = withTiming(0, { duration: 120 });
    };
  }, [nudge, translateX]);

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
      <Animated.View
        testID="trades.card-top"
        style={[styles.cardStack, animatedStyle]}
        onLayout={onCardLayout}
        onTouchStart={nudge ? () => onFirstTouch?.() : undefined}
      >
        <TradeCardComp
          data={card}
          untouchableIds={untouchableIds}
          onToggleUntouchable={onToggleUntouchable}
          onSwapPlayer={onSwapPlayer}
          repricing={repricing}
          fitTargetPositions={fitTargetPositions}
        />
      </Animated.View>
    </GestureDetector>
  );
}

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ── Styles — Chalkline (docs/design/design-system.md) ───────────────
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: 96 },
  // B3 — sub-route pill row (Trades / Portfolio / Calculator).
  // Chalkline chip construction: 1px hairline + label type on ink-1;
  // active = ink-3 well + line-strong border + chalk text.
  subnavRow: {
    flexDirection: 'row',
    gap: space.sm,
  },
  subnavPill: {
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  subnavPillActive: {
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink3,
  },
  subnavPillPressed: {
    backgroundColor: ink.ink3,
  },
  subnavPillText: {
    ...type.label,
  },
  subnavPillTextActive: {
    color: chalk.base,
  },
  switchingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: scrim,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.md,
    zIndex: 50,
  },
  switchingText: {
    ...type.title,
    textAlign: 'center',
    paddingHorizontal: space.xl,
  },
  controlInner: { gap: space.sm },
  controlRow: { flexDirection: 'row', alignItems: 'center' },
  controlValue: {
    ...type.title,
    marginTop: space.xs,
  },
  fairnessRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.xs,
  },
  fairnessHint: {
    ...type.bodySm,
    marginTop: space.xs,
  },
  // Chalkline slider construction (components.md → Forms): 4px ink-3
  // track, 16px square ice thumb at radius xs. Binary here — the thumb
  // sits at either end of the track.
  fairnessSliderTap: {
    width: 56,
    height: 44,
    justifyContent: 'center',
  },
  fairnessTrack: {
    height: 4,
    backgroundColor: ink.ink3,
  },
  fairnessThumb: {
    position: 'absolute',
    top: -6,
    width: 16,
    height: 16,
    borderRadius: radii.xs,
  },
  fairnessThumbOn: {
    right: 0,
    backgroundColor: ice.base,
  },
  fairnessThumbOff: {
    left: 0,
    backgroundColor: ink.lineStrong,
  },
  findBtn: {
    marginTop: space.sm,
  },
  // FB-47 — target players section. Direction pills reuse the subnav
  // chip construction; target chips add a mono direction prefix + x icon.
  targetSection: {
    gap: space.sm,
    paddingVertical: space.xs,
  },
  targetDirRow: {
    flexDirection: 'row',
    gap: space.sm,
  },
  targetDirPill: {
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  targetDirPillActive: {
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink3,
  },
  targetChipsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.sm,
  },
  targetChip: {
    minHeight: 32,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink1,
  },
  targetChipDir: {
    fontFamily: fonts.dataSemi,
    fontSize: 10,
    letterSpacing: 0.5,
    color: chalk.dim,
  },
  // Phase-2 inferred-outlook confirm banner — card construction (ink-1 +
  // hairline + md radius), sits between the controls card and the deck.
  inferredBanner: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    padding: space.lg,
    gap: space.sm,
  },
  inferredActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  progressStrip: {
    marginTop: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radii.sm,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    gap: space.sm,
  },
  progressInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minWidth: 0,
  },
  progressText: {
    ...type.bodySm,
    flex: 1,
    flexShrink: 1,
  },
  likedCount: {
    ...type.bodySm,
    textAlign: 'center',
    marginTop: space.xs,
  },
  deckWrap: {
    minHeight: 360,
    position: 'relative',
  },
  cardStack: {
    width: '100%',
  },
  // Height is set inline from the measured top card (#107/#110); overflow
  // hidden + the TradeCard radius keep the clipped bottom edge reading as
  // a card corner rather than a raw content cut.
  cardBehind: {
    position: 'absolute',
    top: 8,
    left: 0,
    right: 0,
    opacity: 0.55,
    transform: [{ scale: 0.97 }],
    overflow: 'hidden',
    borderRadius: radii.md,
  },
  deckHint: {
    ...type.bodySm,
    textAlign: 'center',
    marginTop: space.md,
  },
  emptyInner: {
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
  },
  emptyTitle: {
    ...type.heading,
    textAlign: 'center',
  },
  emptyBody: {
    ...type.bodySm,
    textAlign: 'center',
  },
  // Onboarding item 7 — post-Quick-Set regeneration receipt. Flare =
  // informational highlight per Chalkline (never an action color).
  diffBanner: {
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    marginBottom: space.md,
  },
  diffBannerText: {
    ...type.bodySm,
    color: chalk.base,
    fontFamily: fonts.uiSemi,
  },
  // Item 8 — session-2 non-modal Apple banner (round-3 D1).
  appleBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    marginBottom: space.md,
  },
  appleBannerBody: { flex: 1, minWidth: 0 },
  appleBannerText: {
    ...type.bodySm,
    color: chalk.base,
    fontFamily: fonts.uiSemi,
  },
  appleBannerDismiss: {
    ...type.bodySm,
    color: chalk.dim,
    fontFamily: fonts.uiSemi,
  },
  // Item 10 — demo→real bridge bar + redraft honesty label.
  demoBridge: {
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    marginBottom: space.md,
  },
  demoBridgeText: {
    ...type.bodySm,
    color: chalk.base,
    fontFamily: fonts.uiSemi,
  },
  redraftLabel: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: 3,
    marginBottom: space.sm,
  },
  redraftLabelText: {
    ...type.bodySm,
    color: chalk.dim,
    fontFamily: fonts.uiSemi,
  },
  // Item 8 — share affordance under the disposition area.
  shareRow: {
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  shareRowText: {
    ...type.bodySm,
    color: chalk.dim,
    fontFamily: fonts.uiSemi,
  },

  // Queue button — appears below the swipable card under the queue flag.
  // Chip construction: hairline border on ink-1; queued = ice border +
  // chalk text (active state).
  sendInSleeper: {
    alignSelf: 'center',
    marginTop: space.sm,
  },
  queueBtn: {
    alignSelf: 'center',
    marginTop: space.md,
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.lg,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink1,
  },
  queueBtnQueued: {
    borderColor: ice.base,
  },
  queueBtnPressed: {
    backgroundColor: ink.ink3,
  },
  queueBtnText: {
    ...type.label,
  },
  queueBtnTextQueued: { color: chalk.base },

  // Bad-trade flag (feedback #85) — deliberately hint-tier: borderless,
  // dim text, centered under the deck hint. It should never compete with
  // the like/pass dispositions.
  badTradeBtn: {
    alignSelf: 'center',
    marginTop: space.xs,
    minHeight: 32,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.md,
  },
  badTradeBtnPressed: {
    opacity: 0.6,
  },
  badTradeText: {
    ...type.label,
    color: chalk.dim,
  },

  // Queue footer — anchored above the tab bar (the SafeAreaView already
  // reserves the bottom inset). Visible only when queue has ≥ 1 item.
  // Floating bar → ink-2 + hairline + sheet shadow (toast-tier surface).
  queueFooter: {
    position: 'absolute',
    left: space.md,
    right: space.md,
    bottom: space.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    padding: space.sm,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink2,
    ...shadowSheet,
  },
  queueFooterTap: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.sm,
    paddingVertical: 6,
    borderRadius: radii.sm,
  },
  queueFooterTapPressed: {
    backgroundColor: ink.ink3,
  },
  queueFooterCount: {
    minWidth: 28,
    height: 28,
    paddingHorizontal: space.sm,
    textAlign: 'center',
    lineHeight: 28,
    borderRadius: radii.pill,
    backgroundColor: ink.ink3,
    color: chalk.base,
    fontFamily: fonts.dataSemi,
    fontSize: 13,
    fontVariant: ['tabular-nums'],
    overflow: 'hidden',
  },
  queueFooterLabel: {
    ...type.bodySm,
    color: chalk.base,
    flex: 1,
  },

  // Queue bottom-sheet modal — ink-2, hairline, sheet shadow, grabber.
  queueBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: scrim,
  },
  queueSheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '80%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  queueHandle: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  queueSheetHeader: { gap: space.xs },
  queueSheetTitle: {
    ...type.heading,
  },
  queueSheetSub: {
    ...type.bodySm,
  },
  queueSheetScroll: { maxHeight: 420, marginTop: space.sm },
  queueEmpty: {
    ...type.bodySm,
    textAlign: 'center',
    padding: space.xl,
  },
  queueSheetActions: {
    flexDirection: 'row',
    gap: space.sm,
    marginTop: space.md,
  },
  queueSheetCancel: { flex: 1 },
  queueSheetSend: { flex: 2 },

  // FB-05 — check / x disposition button row beneath the top trade card.
  // Icon-button construction (components.md → Buttons): square radius,
  // 1px semantic border; pressed = semantic fill + ink icon (color-only
  // state change, no transforms). 56px keeps the touch floor.
  dispositionRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: space.xl,
    marginTop: space.lg,
  },
  dispositionBtn: {
    width: 56,
    height: 56,
    borderRadius: radii.sm,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
  dispositionBtnPass: {
    borderColor: semantic.neg,
  },
  dispositionBtnPassPressed: {
    backgroundColor: semantic.neg,
  },
  dispositionBtnLike: {
    borderColor: semantic.pos,
  },
  dispositionBtnLikePressed: {
    backgroundColor: semantic.pos,
  },
  dispositionDisabled: {
    opacity: 0.45,
  },
});
