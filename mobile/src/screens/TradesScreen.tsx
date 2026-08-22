import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useFocusEffect, useIsFocused } from '@react-navigation/native';
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
  AppState,
  Platform,
  Share,
  Keyboard,
  type LayoutChangeEvent,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
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
import { useCardImpact, type CardImpactState } from '../state/useCardImpact';
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
import { posColor } from '../theme/colors';
import { TickLabel, Button, Meter, Icon, Card } from '../components/chalkline';
import TradeCardComp from '../components/TradeCard';
import { type DeclineReasonPanelProps } from '../components/DeclineReasonPanel';
import SendInSleeperButton from '../components/SendInSleeperButton';
import Toast from '../components/Toast';
import PlayerContextMenu, { type PlayerMenuAction } from '../components/PlayerContextMenu';
import HelpSheet, { InfoButton } from '../components/HelpSheet';
import { registerScrollToTop } from '../navigation/scrollToTop';
import OutlookSheet from '../components/OutlookSheet';
import TradeFinderModeBar from '../components/TradeFinderModeBar';
import OutlookBiasReceipt, {
  outlookReceiptCovers,
} from '../components/OutlookBiasReceipt';
import TradeDnaSheet, {
  TRADE_INTENT_LABEL,
  type TradeIntent,
} from '../components/TradeDnaSheet';
import TradeHomeUtilityRow from '../components/TradeHomeUtilityRow';
import TradingWithStrip from '../components/TradingWithStrip';
import TradeBuildCanvas from '../components/TradeBuildCanvas';
import LeagueSwitcherSheet from '../components/LeagueSwitcherSheet';
import QueueChip from '../components/QueueChip';
import SwapPlayerSheet from '../components/SwapPlayerSheet';
import PlayerPickerModal from '../components/PlayerPickerModal';
import type { CalcPlayer } from '../data/calcTypes';
import {
  generateTrades,
  getTradeStatus,
  swipeTrade,
  flagBadTrade,
  getLikedTrades,
  getAwaitingTrades,
  undoDeckSuppression,
  fetchAssetIdeas,
  type AssetIdea,
  type SwipeSignal,
} from '../api/trades';
import {
  postDeclineReason,
  type Layer1Code,
  type Layer2Code,
} from '../api/declineReasons';
import AssetIdeasPanel from '../components/AssetIdeasPanel';
import FeaturedTradeWindow, { assetIdeaKey } from '../components/FeaturedTradeWindow';
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
import { getLeagueRosters, getLeagueUsers, myOwnerId } from '../api/sleeper';
import {
  getTradeValues,
  evaluateTradeInLeague,
  evaluateForSwapSuggestions,
  type CalcValueRow,
  type CalcEvener,
} from '../api/calc';
import SwapSuggestSheet from '../components/SwapSuggestSheet';
import { getProgress } from '../api/rankings';
import { track, msSinceOpen } from '../api/events';
import { ApiError, getBaseUrl } from '../api/client';
import { resolveShareUrl } from '../utils/shareLinks';
import { useInterruptSlot } from '../state/useInterruptCoordinator';
import InviteLeaguematesBanner from '../components/InviteLeaguematesBanner';
import TeamReviewEntryCard from '../components/TeamReviewEntryCard';
import FormatGate, { formatLabel } from '../components/FormatGate';
import ProvenanceChip from '../components/ProvenanceChip';
import SkeletonTradeCard from '../components/SkeletonTradeCard';
import CoachMark from '../components/CoachMark';
import IdentityConfirmStrip from '../components/IdentityConfirmStrip';
import QuickSetPromptCard from '../components/QuickSetPromptCard';
import AppleSaveMomentSheet from '../components/AppleSaveMomentSheet';
import {
  consumePendingQuicksetRegen,
  consumeGuidedRegenSource,
  isRegenPosition,
} from '../state/onboardingBus';
import {
  useGuide,
  requestGuideStep,
  advanceGuideIfActive,
  guidedAvatarActive,
  guideV2Active,
  guideActiveStepId,
  dismissActiveGuideStep,
  recordGuideReceipt,
  markGuideStepConsumed,
  type GuideCompletionVia,
} from '../state/useGuide';
import {
  registerGuideTarget,
  unregisterGuideTarget,
  notifyGuideTargetsMoved,
} from '../state/guideTargets';
import {
  S as GUIDE,
  GUIDE_RECEIPTS,
  nextUnrankedPosition,
} from '../components/analystScript';
import { useSession } from '../state/useSession';
import { useTradeQueue } from '../state/useTradeQueue';
import { useFinderTargets } from '../state/useFinderTargets';
import { useFlag, useOnboardingFeature, onboardingEnabled } from '../state/useFeatureFlags';
import {
  useOnboardingState,
  getOnboardingState,
  patchOnboardingState,
} from '../state/useOnboardingState';
import {
  FAIRNESS_PREF_KEY,
  fairnessOnFromPref,
  fairnessThresholdFor,
} from '../api/tradePregen';
import { navigationRef } from '../navigation/RootNav';
import NewPartnersBanner from '../components/NewPartnersBanner';
// F4 session re-rank (flag deck.session_rerank): pure math lives in
// utils/sessionRerank — this screen only owns the session state (refs) and
// the wiring into advance()/undo/reset.
import {
  buildBoostVector,
  dispositionWeight,
  extractCardAttributes,
  isZeroVector,
  rerankRemaining,
  SESSION_RERANK_LAST_K,
  type RerankDisposition,
  type RerankEvent,
  type RerankMove,
} from '../utils/sessionRerank';
// F9 first-session win (flag deck.first_session): pure trigger math for the
// adaptation moment lives in utils/firstSessionMoment — this screen owns the
// session refs, the inline card, and the activation events.
import {
  cardMatchesAttribute,
  findDominantLikedAttribute,
  FIRST_SESSION_MIN_DISPOSITIONS,
  FIRST_SESSION_MIN_SHARED_LIKES,
  type FirstSessionLike,
} from '../utils/firstSessionMoment';
// P0-2 — the read gate's 403 gets its own copy on the deck-failure card.
import { readErrorCopy } from '../utils/verification';
import { applyJobResult } from '../utils/applyJobResult';
import type { Player, TradeCard, TradeJobSnapshot, ScoringFormat } from '../shared/types';

const SCREEN_W = Dimensions.get('window').width;
const SWIPE_THRESHOLD = 120;
// #216 — featured-trade window: per-pin-session back-stack cap. Full
// history (not 1-level) per the approved mock's interaction rules; the cap
// only bounds memory.
const FEATURED_HISTORY_CAP = 10;
// Triage undo (S3 PRD-03, flag ux.swipe_undo): how long a pass swipe's
// disposition POST is held (and the Undo toast shown) before committing.
const UNDO_HOLD_MS = 5000;
// A failed swipe's toast carries the only recovery affordance (Retry), so it
// outlasts the 1.5s default — the POST is held UNDO_HOLD_MS before it even
// fires, so the failure lands long after the tap that caused it.
const SWIPE_ERROR_HOLD_MS = 6000;

// `swipe_guard_blocked` volume policy (B4 / D-068 follow-up; tracking-plan
// addendum docs/business/analytics/2026-08-18-swipe-guard-blocked.md).
//
// A trapped user tapping repeatedly IS the phenomenon, so collapsing to one
// row per card would delete the measurement — but firing on every block is
// unbounded, and a stuck user in a tight loop could fill the 500-event SDK
// queue and evict real funnel rows. So: emit at LADDER points of the
// consecutive-block count per (card, guard), hard-capped per session.
// Six rows per trapped card; the B4 user's fifty taps land as six rows
// topping out at blocked_n 25 — same conclusion, 12% of the volume.
// Analysis reads max(blocked_n), NEVER count(rows).
const GUARD_BLOCK_LADDER = [1, 2, 3, 5, 10, 25];
const GUARD_BLOCK_SESSION_CAP = 50;

// F1 signal spine (flag deck.signal_v2, PRD F1): dwell timer cap (guards
// against left-open decks inflating dwell) and the front-of-deck threshold
// after which a card counts as `viewed` (served ≠ seen).
const DWELL_CAP_MS = 120_000;
const VIEWED_MIN_MS = 500;

// N6.1 (PRD §5.3): how long the empty-awaiting gate waits on the
// `['awaiting-trades']` fetch before falling back to the router-less
// variant. Well inside the beat's own 8 s lifetime — a bubble that lands
// four seconds after the swipe is no longer about that swipe.
const N61_AWAITING_TIMEOUT_MS = 2500;

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

// audit P1-1 / PR-14 — a package holding a draft pick cannot be rendered by
// the share landing (og_image resolves ids against the players table and a
// pick_id isn't in it), so those shares skip the mint. Derived from the row
// the card already carries, never from the id's shape.
const isPickAsset = (p: Player) => p.position === 'PICK' || p.pick_value != null;

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

// F9 (deck.first_session): the adaptation moment renders at most once per
// app session (module-level so a tab remount / regenerate can't re-fire it
// — "at most once per first session" with margin).
let adaptationMomentShownThisSession = false;

// ── P0-2: the failed-search state ────────────────────────────────────
// Three independent failure paths (POST error, job errors during polling,
// polling abandoned after MAX_POLL_FAILURES) previously all left the deck
// slot on the never-searched card, so "we tried and failed" and "you have
// never searched" were the same pixels. One funnel, LAST WRITE WINS, so the
// deck slot can render a named persistent state with a working retry.
//
// `message` is ALWAYS shipped user copy. job.error is never routed here
// verbatim — see jobErrorCopy below.
type DeckFailure = {
  kind: 'generate' | 'job_error' | 'poll_abandoned';
  message: string;
} | null;

const DECK_FAIL_GENERIC =
  "We couldn't finish that search — the server may still be waking up. Try again.";
const DECK_FAIL_NETWORK =
  'We lost the connection while searching. Your league is fine — try again.';
const DECK_FAIL_TIMEOUT =
  'That search took too long. The server may still be waking up — try again.';

// Maps the job snapshot's `error` field onto shipped copy. The raw value is
// str(e) of a server-side Python exception, or the reaper's literal
// "timeout"; neither is user-facing.
function jobErrorCopy(raw?: string | null): string {
  return raw === 'timeout' ? DECK_FAIL_TIMEOUT : DECK_FAIL_GENERIC;
}

// S-43 — identity of a trade as the USER experiences it: who it's with,
// what leaves, what arrives. Used by the post-Quick-Set reveal to count
// trades that are genuinely new.
//
// Why not `trade_id`: the backend mints a fresh uuid for every card on
// every generation (trade_service.py:3644/:3815/:4314, server.py:2921 for
// the likes-you injections) — it is never derived from the package. An
// id-based diff therefore reports 33-of-33 "new" for two back-to-back
// generations that produced the same 33 packages, so the celebrate beat
// would fire (with a meaningless N) even after a Quick Set the user
// skipped through. Content is the only honest basis.
//
// Both sides are sorted because within-side ordering is an engine
// artifact, not something the user sees change; leaving it unsorted would
// score a re-ordered but identical package as new.
function tradePackageKey(c: TradeCard): string {
  return [
    c.opponent_user_id,
    [...c.give_player_ids].sort().join(','),
    [...c.receive_player_ids].sort().join(','),
  ].join('|');
}

export default function TradesScreen({ navigation, route }: any) {
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
  // holds the pre-regen deck's PACKAGE identities so the reveal can count
  // trades the user has not already seen (S-43 fix — see tradePackageKey).
  // `jobId` is stamped by the forced generate's own onSuccess: the reveal is
  // late-bound to THAT job, so a stale already-'complete' job cannot resolve
  // it early (the deck clear below re-runs the diff effect while the old job
  // is still in state).
  const pendingRegenRef = useRef<{
    /** Quick Set position, or null for trios/import guided returns. */
    position: string | null;
    jobId: string | null;
    prevPackages: Set<string>;
  } | null>(null);
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
  //
  // DEFAULT OFF since 2026-08-17 (operator decision — widen the net so
  // testers see and judge more trades, with the decline-reason capture
  // collecting their verdicts). The initial state MUST match what an unset
  // preference resolves to (`fairnessOnFromPref(null)` === false), or the
  // toggle would paint ON while 0.5 was being sent. An explicit 'on' is
  // restored by the hydrate below; nobody's stored value is rewritten.
  const [fairnessOn, setFairnessOn] = useState(fairnessOnFromPref(null));
  const [deck, setDeck] = useState<TradeCard[]>([]);
  const [deckIdx, setDeckIdx] = useState(0);
  // #288 — the deck snapshot from the moment a "Keep · more offers" tap
  // pins a single player and enters single-pin featured mode (the found-
  // trade-card → "other options for that player" flow). resetDeckForNew-
  // Targets wipes deck/deckIdx/job on every pin change, so without this
  // there's no way back to the original found trade once pinned. Captured
  // ONLY at that one entry point (not every pin path — e.g. the player-
  // mode target board pins from an empty deck already) so "back" always
  // means "the deck this player's card came from," never a stale unrelated
  // snapshot.
  const preSinglePinSnapshotRef = useRef<{
    deck: TradeCard[];
    deckIdx: number;
    job: TradeJobSnapshot | null;
  } | null>(null);
  // Phase-2 lane filter: null = All. Tapping a lane pill filters the deck
  // to that lane; tapping the active pill again clears back to All. The
  // pill row only renders when at least one deck card carries a lane.
  const [laneFilter, setLaneFilter] = useState<'window' | 'value' | null>(null);
  // #172 — trade intent modes ("I want to consolidate / tier up / tier
  // down"), a single-select shape filter sent to /api/trades/generate.
  // Chip UI lives only in the #257 full sheet (trades.edit_full_sheet);
  // this state exists regardless of that flag so it's always defined for
  // the mutation body, but nothing ever sets it when the chips don't render.
  const [tradeIntent, setTradeIntent] = useState<TradeIntent>(null);
  // #107/#110 — measured layout height of the TOP card. The behind-card
  // peek is clipped to this so a taller next card (e.g. 2 player tiles
  // behind a 1-player top) can't leak its extra tile out from under the
  // top card. Updated via onLayout on every top-card mount/re-layout.
  const [topCardH, setTopCardH] = useState<number | null>(null);
  // P0-2 — bottom edge of the mode-bar region in ScrollView content
  // coordinates, so the Toast can clear it instead of clipping the chips.
  // 0 = not measured yet / not mounted ⇒ Toast keeps its 32pt default.
  const [modeBarBottom, setModeBarBottom] = useState(0);
  const [toast, setToast] = useState<{
    msg: string;
    tone?: 'success' | 'warn' | 'error';
    holdMs?: number;
    action?: { label: string; onPress: () => void };
  } | null>(null);
  const [outlookOpen, setOutlookOpen] = useState(false);
  const [queueSheetOpen, setQueueSheetOpen] = useState(false);
  const [slowSwitch, setSlowSwitch] = useState(false);

  // ── Teardown-remediation flags (all default false — flag off is
  // byte-identical behavior) ──────────────────────────────────────────
  const swipeUndoOn = useFlag('ux.swipe_undo');           // S3 PRD-03
  const menuOn = useFlag('ux.player_context_menu');       // S3 PRD-02
  // F1 signal spine (flag deck.signal_v2): thread impression_id + dwell +
  // engagement bits through dispositions/events. Off ⇒ no timers, no extra
  // fields, byte-identical behavior.
  const signalV2On = useFlag('deck.signal_v2');
  // F10 (flag deck.replenishment, PRD F10): deck-done summary card. Session
  // disposition tallies feed the "N passed, M liked, K proposed" copy; both
  // reset whenever a new job starts / the deck resets (job_id effect below).
  // Off ⇒ tallies never update and the summary never renders — the existing
  // exhausted state is byte-identical.
  const replenishmentOn = useFlag('deck.replenishment');
  const [sessionTally, setSessionTally] = useState({ passed: 0, liked: 0, proposed: 0 });
  const [summaryDismissed, setSummaryDismissed] = useState(false);
  // F3 (flag deck.fatigue): deck header honoring note — shown when the job
  // snapshot carries suppression_note (≥1 near-duplicate of a declined trade
  // was hidden). Dismissal is per-job (a fresh generation may re-show it);
  // "Undo" lifts the newest decline suppression server-side and regenerates.
  const fatigueOn = useFlag('deck.fatigue');
  // F4 (flag deck.session_rerank, PRD F4): after each disposition the
  // REMAINING cards (position ≥ dispositioned+2) re-sort against a
  // session-local boost vector. Off ⇒ no events recorded, no reorder ever
  // runs — deck order stays exactly the served order (byte-identical).
  const rerankOn = useFlag('deck.session_rerank');
  // F9 (flag deck.first_session, PRD F9): first-deck activation layer.
  // Everything gates on firstSessionOn AND the server-marked job.first_deck
  // (the server checked deck history — existing users never carry it), so
  // flag off ⇒ no refs update, no events fire, no card renders. The board-
  // sourced header (amendment) reads job.board_refresh, which the server
  // emits for ANY board-refreshed deck while the flag is on.
  const firstSessionOn = useFlag('deck.first_session');
  // Decline-reason capture (flag `feedback.decline_reasons`, tester-allowlist
  // scoped, default OFF — SPEC §5). On ⇒ the card's ✕ is replaced by the
  // three layer-1 tiles and the pass commits on the tile tap, with the deck
  // advance deferred until layer 2 answers. Off ⇒ nothing below this flag
  // runs and the ✓/✕ row renders byte-identically.
  const declineReasonsOn = useFlag('feedback.decline_reasons');
  // The raw deck id whose pass is banked but whose deck advance is still
  // waiting on layer 2. Blocks a second disposition on the same card (the ✓,
  // the swipe gesture, the a11y actions) and is cleared on every advance.
  const [reasonBankedId, setReasonBankedId] = useState<string | null>(null);
  // Same value as the state above, readable synchronously: the layer-1 tap
  // and a fast follow-up gesture can land in one React batch.
  const reasonBankedIdRef = useRef<string | null>(null);
  // Card fronted → now, for the SPEC §6 `ms_since_render` property. Its own
  // stamp rather than the F1 dwell ref, which only runs under deck.signal_v2 /
  // deck.session_rerank and is capped + background-paused.
  const cardRenderedAtRef = useRef(Date.now());
  // Main-ScrollView offset, tracked only while this flag is on, so the
  // free-text composer can be scrolled clear of the keyboard.
  const mainScrollYRef = useRef(0);
  const [adaptationMoment, setAdaptationMoment] = useState<{
    phrase: string;
    attribute: string;
    likes: number;
    variant: 'rerank' | 'descriptive';
  } | null>(null);
  const [suppressionNoteDismissedJob, setSuppressionNoteDismissedJob] =
    useState<string | null>(null);
  const [suppressionUndoPending, setSuppressionUndoPending] = useState(false);
  // S1 PRD-05 (flag ux.retap_active_tab) — when the Trades stack is already
  // at TradesHome, a focused re-tap scrolls the main list to top. (TabNav
  // pops any pushed Portfolio/Calculator screen first.)
  const retapOn = useFlag('ux.retap_active_tab');
  const mainScrollRef = useRef<ScrollView>(null);
  // #276 — auto-scroll to the generated card once Find a Trade produces
  // one, so the user lands on the offer instead of the button they just
  // tapped. `deckCardY` mirrors the featuredWindowY pattern below (an
  // onLayout on the deck's wrapping View, same ScrollView coordinate
  // space); `pendingScrollToDeckRef` is armed by handleFindTrades and
  // consumed the first time the job reports any cards.
  const deckCardY = useRef(0);
  const pendingScrollToDeckRef = useRef(false);
  useEffect(
    () =>
      retapOn
        ? registerScrollToTop('Trades', () =>
            mainScrollRef.current?.scrollTo({ y: 0, animated: true }),
          )
        : undefined,
    [retapOn],
  );
  const outlookInlineOn = useFlag('ux.outlook_inline_default'); // S4 PRD-02
  const outlookDirectionOn = useFlag('trade.outlook_direction'); // #231/#254
  const helpOn = useFlag('ux.help_surface');              // S4 PRD-01
  const shareLandingOn = useFlag('growth.share_landing'); // S7 PRD-01
  // #257 — Controls Card → full edit sheet consolidation (variant C).
  const fullSheetOn = useFlag('trades.edit_full_sheet');
  // #172 — trade intent modes chip row (full sheet only).
  const intentModesOn = useFlag('trades.intent_modes');
  // #357/#358/#359 — Team Review entry (dark until the operator flips it).
  const teamReviewOn = useFlag('trades.team_review');
  // #269 — specific-team targeting + league picker move into the full
  // sheet; the mode-bar's Team and Player chips go away.
  const sheetTargetingOn = useFlag('trades.sheet_targeting');
  // #270/#272 — experiment `trades_home_inline` (docs/feedback/items/
  // 270-inline-trades-home/status.md). client_config.flags overlay carries
  // exactly one of these two booleans for an assigned unit (never both);
  // absent for everyone else, which keeps the control path byte-identical.
  // `canvas` wins if somehow both were true — it's the strictly bigger
  // surface, so a UI branch has to pick one, and never happens in practice
  // (a unit is assigned exactly one variant).
  const homeInlineStripOn = useFlag('trades_home_inline.strip');
  const homeInlineCanvasOn = useFlag('trades_home_inline.canvas');
  const homeInlineVariant: 'control' | 'strip' | 'canvas' = homeInlineCanvasOn
    ? 'canvas'
    : homeInlineStripOn
      ? 'strip'
      : 'control';

  // ── FB #156/#246 — finder modes (flag `trades.finder_hub`) ────────────
  // route.params carries which mode this screen is in and (team mode) the
  // scoped league-mate. #246 (guided-first landing): `TradesHome` itself
  // mounts this screen with initialParams {mode:'guided'} — the launcher
  // hub is unrouted, and the mode strip (TradeFinderModeBar) is the
  // switching home. Flag off ⇒ every value here is undefined and this
  // screen behaves exactly as the classic standalone Trades home.
  const finderHubOn = useFlag('trades.finder_hub');
  // rookie-draft placement, option B — gates the mode strip's leading Draft
  // chip (the room's permanent home). Off ⇒ no chip, strip unchanged.
  const draftRoomOn = useFlag('draft.room');
  // Presentation v2 (docs/plans/trade-presentation-v2/scope.md, operator
  // decision 2026-08-18). Gates the mode strip's leading "Today" chip, which
  // is the ONLY entry point to the additive TodaysTrade / TradeBrowseAll
  // screens. This flag changes NOTHING else in this file: no state, no
  // query, no render branch, no behaviour of the existing deck. Off ⇒ the
  // handler is omitted, the chip does not exist, and the strip renders
  // byte-identically to today. Pinned by mobile/tests/check-presentation-v2.js.
  const presentationV2On = useFlag('trades.presentation_v2');
  // Receipts (docs/plans/receipts/, flag `receipts.screen`). Same shape as the
  // flag above and changes nothing else in this file: off ⇒ the handler is
  // omitted, the utility row has no Track-record control, and ReceiptsScreen
  // is unreachable even though its route is registered. Pinned by
  // mobile/tests/check-receipts.js.
  const receiptsOn = useFlag('receipts.screen');
  // #269 — sheet-local team-targeting selection (declared ahead of
  // `scopedOpponent` below, which reads it). Single-select; `null` = no
  // opponent chosen (unscoped, today's behavior).
  const [sheetOpponent, setSheetOpponent] = useState<
    { userId: string; name: string } | null
  >(null);
  const finderMode: 'guided' | 'team' | 'player' | undefined = finderHubOn
    ? route?.params?.mode
    : undefined;
  // #270/#272 — both `trades_home_inline` variants are scoped to the guided
  // landing only; team/player deck modes (already rare post-#269, reachable
  // only via a stored deep link since the mode-bar's chips are hidden) keep
  // today's TradeFinderModeBar untouched regardless of assignment.
  const showInlineHome = finderMode === 'guided' && homeInlineVariant !== 'control';
  // #269 — with the mode-bar's Team chip gone under `sheetTargetingOn`, the
  // scoped opponent's SOURCE moves from route params to sheet-local state
  // (`sheetOpponent`, declared below); everything downstream that already
  // reads `scopedOpponent`/`scopedOpponentName` (generateMutation's
  // opponent_user_id, the FB-47 target-picker pool, asset ideas) is
  // untouched — only where the id comes from changes. Flag off ⇒ this is
  // exactly the original `finderMode === 'team'` expression.
  const scopedOpponent: string | undefined = sheetTargetingOn
    ? sheetOpponent?.userId
    : finderMode === 'team'
      ? route?.params?.opponentUserId
      : undefined;
  const scopedOpponentName: string | undefined = sheetTargetingOn
    ? sheetOpponent?.name
    : finderMode === 'team'
      ? route?.params?.opponentName
      : undefined;
  // #257 — the consolidation only replaces the Controls Card on the
  // finder-mode landing, where OutlookBiasReceipt exists as the entry
  // point. The classic flag-off home (no finderMode, `trades.finder_hub`
  // off) has no receipt, so it keeps the legacy Controls Card +
  // OutlookSheet regardless of `fullSheetOn` — there'd be nothing else to
  // reach fairness/lane/targeting from.
  const consolidateOn = fullSheetOn && !!finderMode;

  // Lateral switch handlers. All three deck modes switch IN PLACE
  // (setParams keeps this instance mounted, so pinned targets persist);
  // the Team chip opens an in-screen manager picker — both to enter team
  // mode and to change the scoped team (#156 finish item 4). Calculator
  // and Free Agents (#246) are separate pushed destinations.
  const [teamPickerOpen, setTeamPickerOpen] = useState(false);

  // #246 — Trade DNA sheet over the deck (guided-first landing, mock B3):
  // the receipt's "Change" link opens the hub's DNA editor as a bottom
  // sheet here instead of navigating to the (now unrouted) hub. The
  // legacy `editDna:true` route param — old deep links / stored routes
  // that used to auto-expand the hub's panel — opens the same sheet.
  const [dnaSheetOpen, setDnaSheetOpen] = useState(false);
  // Who opened the DNA sheet — labels outlook_saved.source (TradeDnaSheet's
  // openSource prop). Reset to the default on close.
  const [dnaOpenSource, setDnaOpenSource] = useState<'guide' | 'sheet' | 'strip'>('sheet');
  // #257 — "Preferences changed" refresh strip. Fairness/lane/targeting
  // edits already reset or re-filter the deck themselves; the only stale-
  // deck case is a DNA edit (outlook/chasing/shopping/untouchables), which
  // TradeDnaSheet reports via `full.onAnyChange`. Tracked since the last
  // generate (not since the sheet last opened) so an add-target hand-off
  // to PlayerPickerModal — which briefly closes this sheet, see
  // `pickerReturnsToSheet` below — can't lose the signal.
  const prefsChangedSinceGenerateRef = useRef(false);
  const [showPrefsChangedStrip, setShowPrefsChangedStrip] = useState(false);
  // The full sheet's "Add someone to get/send" closes this Modal before
  // opening PlayerPickerModal (iOS won't stack sibling Modals) and reopens
  // it when the picker closes — only when the picker was opened THIS way.
  const [pickerReturnsToSheet, setPickerReturnsToSheet] = useState(false);
  // #269 — same close-sheet/open-picker/reopen-sheet pattern as
  // `pickerReturnsToSheet` above, shared by the sheet's League row (opens
  // the global LeagueSwitcherSheet) and its "Trade with" row (opens the
  // existing team-picker Modal below).
  const [leaguePickerOpen, setLeaguePickerOpen] = useState(false);
  const [returnToSheetAfterPicker, setReturnToSheetAfterPicker] = useState<
    'team' | 'league' | null
  >(null);
  function handleEditSheetClose() {
    setDnaOpenSource('sheet');
    setDnaSheetOpen(false);
    // Only worth a nudge if there's an existing deck to go stale and no
    // search is already in flight (that search will land under whatever
    // prefs are current by the time it started).
    if (
      consolidateOn &&
      prefsChangedSinceGenerateRef.current &&
      deck.length > 0 &&
      job?.status !== 'running'
    ) {
      setShowPrefsChangedStrip(true);
    }
  }
  useEffect(() => {
    if (route?.params?.editDna) {
      if (finderHubOn) setDnaSheetOpen(true);
      navigation?.setParams?.({ editDna: undefined });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route?.params?.editDna]);
  const switchFinderMode = useCallback(
    (m: 'guided' | 'team' | 'player') => {
      if (m === 'team') {
        setTeamPickerOpen(true);
        return;
      }
      navigation?.setParams?.({ mode: m });
    },
    [navigation],
  );
  // #269 — the team-picker Modal now closes through this single path
  // whether it was opened from the mode-bar's Team chip (legacy) or the
  // sheet's "Trade with" row: it hands back to TradeDnaSheet only when
  // that's where it was opened from.
  function closeTeamPicker() {
    setTeamPickerOpen(false);
    if (returnToSheetAfterPicker === 'team') {
      setReturnToSheetAfterPicker(null);
      setDnaSheetOpen(true);
    }
  }
  function pickScopedTeam(opponentUserId: string, opponentName: string) {
    haptics.selection();
    closeTeamPicker();
    navigation?.setParams?.({ mode: 'team', opponentUserId, opponentName });
  }
  // #269 — sheet variant: single-select, tap the active manager again to
  // clear (unlike legacy Team mode, which always has an opponent once
  // entered). Autosaves like the sheet's other prefs — no deck reset here,
  // just the #257 "Preferences changed" nudge (prefsChangedSinceGenerateRef).
  function pickSheetOpponent(userId: string, name: string) {
    haptics.selection();
    setSheetOpponent((prev) => (prev?.userId === userId ? null : { userId, name }));
    prefsChangedSinceGenerateRef.current = true;
    closeTeamPicker();
  }
  function clearSheetOpponent() {
    haptics.selection();
    setSheetOpponent(null);
    prefsChangedSinceGenerateRef.current = true;
  }
  function openTeamPickerFromSheet() {
    haptics.selection();
    setDnaSheetOpen(false);
    setReturnToSheetAfterPicker('team');
    setTeamPickerOpen(true);
  }
  function openLeaguePickerFromSheet() {
    haptics.selection();
    setDnaSheetOpen(false);
    setReturnToSheetAfterPicker('league');
    setLeaguePickerOpen(true);
  }
  function closeLeaguePicker() {
    setLeaguePickerOpen(false);
    if (returnToSheetAfterPicker === 'league') {
      setReturnToSheetAfterPicker(null);
      setDnaSheetOpen(true);
    }
  }
  // #270 — TradingWithStrip's pills open the SAME pickers as the sheet's
  // League/Trade-with rows, but directly: `returnToSheetAfterPicker` stays
  // null, so `closeTeamPicker`/`closeLeaguePicker` just close on selection
  // instead of popping the full sheet back open (the strip's whole point is
  // staying off the sheet).
  function openTeamPickerFromStrip() {
    haptics.selection();
    setTeamPickerOpen(true);
  }
  function openLeaguePickerFromStrip() {
    haptics.selection();
    setLeaguePickerOpen(true);
  }

  // S4 PRD-01 — "How trades are priced" sheet next to the fairness toggle.
  const [pricingHelpOpen, setPricingHelpOpen] = useState(false);
  // S3 PRD-02 — shared player context menu target (long-press on any
  // player row of the top card while the flag is on).
  const [menuTarget, setMenuTarget] = useState<{
    player: Player;
    side: 'give' | 'receive';
  } | null>(null);

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
  // Derived through the SAME helper the session-init pregen uses — a second
  // derivation here is how the two drift and miss the server cache slot.
  const effectiveFairness = fairnessThresholdFor(fairnessOn);

  // Hydrate the persisted toggle on mount. Unset resolves to OFF (the
  // 2026-08-17 default); an explicit 'on' is restored here. Read-only —
  // this never writes the key back, so nobody's stored choice is touched.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(FAIRNESS_PREF_KEY);
        if (cancelled) return;
        setFairnessOn(fairnessOnFromPref(raw));
      } catch {
        /* AsyncStorage unavailable — keep the default (OFF) */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // #257 — shared Find-a-Trade entry point so every trigger (the on-screen
  // button in both flag states, and the "Preferences changed" strip)
  // clears the refresh nudge the same way.
  function handleFindTrades(source?: string) {
    setDeckFailure(null); // P0-2 — a search in flight has no failure
    setScopedEmpty(null); // #330 — re-set by the completion effect if the re-run is empty too
    // #298 — `mode` always present; `source` only when a caller named one.
    // `source` has been sent here since #257 and STRIPPED on every row by
    // an empty prop registry until 2026-08-11; it is registered now.
    track('find_trades_tapped',
          source ? { source, mode: deckMode } : { mode: deckMode },
          'Trades');
    prefsChangedSinceGenerateRef.current = false;
    setShowPrefsChangedStrip(false);
    setPinIdeaResumed(false); // #317 — a new search's deck re-takes the slot
    pendingScrollToDeckRef.current = true; // #276
    generateMutation.mutate({});
  }

  function handleToggleFairness(next: boolean) {
    setFairnessOn(next);
    // Fire-and-forget persistence; a write failure shouldn't block the UI.
    AsyncStorage.setItem(FAIRNESS_PREF_KEY, next ? 'on' : 'off').catch(() => {});
    // Toggling the threshold invalidates the current deck — the next
    // Find-a-Trade tap should request a fresh set under the new mode.
    // Also avoids visual shuffle if streaming cards were still arriving.
    flushPendingPassRef.current(); // commit any undoable pass before reset
    lastDispositionedRef.current = null; // regenerated decks can reuse ids
    setDeck([]);
    setDeckIdx(0);
    setLaneFilter(null);
    setJob(null);
    setDeckFailure(null); // P0-2 — the deck AND the reason it failed
    setScopedEmpty(null); // #330 — a fairness change can change results; drop the stale zero-result card
    setEdits({});
    setSwapTarget(null);
    setSuggestTarget(null);
  }

  // #172 — trade intent modes. Tapping the active chip clears it (single-
  // select, tap-again-to-clear). Unlike fairness/lane this does NOT reset
  // the deck outright — it autosaves like the sheet's other DNA prefs and
  // marks the #257 "Preferences changed" refresh strip (the same
  // prefsChangedSinceGenerateRef machinery outlook/positions use) so the
  // user opts into regenerating rather than losing the current deck.
  function handleTradeIntent(next: TradeIntent) {
    haptics.selection();
    setTradeIntent((prev) => (prev === next ? null : next));
    prefsChangedSinceGenerateRef.current = true;
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
  // S4 PRD-02 (ux.outlook_inline_default): the sheet NEVER force-opens —
  // the inline banner below is the universal first-visit path on every
  // flag configuration; the sheet opens only from an explicit Edit/Change/
  // Set-outlook tap.
  // #257 (operator decision Q5): the full sheet must never auto-open
  // either — `ux.outlook_inline_default` already suppresses this legacy
  // path in production (it ships true), but `consolidateOn` bails here too
  // so a future flip of that flag can't resurrect a force-opened sheet.
  useEffect(() => {
    if (firstRun || outlookInlineOn || consolidateOn) return;
    if (
      prefsQuery.data &&
      !prefsQuery.data.team_outlook &&
      !prefsQuery.data.inferred_outlook
    ) {
      setOutlookOpen(true);
    }
  }, [prefsQuery.data, firstRun, outlookInlineOn, consolidateOn]);

  // Phase-2 inferred outlook — set only while no outlook is declared;
  // drives the one-tap confirm banner and the sheet's preselection.
  const inferredOutlook =
    prefsQuery.data && !prefsQuery.data.team_outlook
      ? prefsQuery.data.inferred_outlook ?? null
      : null;

  // #254/#255 — the outlook was stated twice on this screen: the #231
  // minimized bar (OutlookBiasReceipt, mounted in finder modes) AND the
  // controls card's own "Outlook · Edit" row, which predates it. The bar
  // is the one that belongs — it names the BIAS, not just the label, and
  // its Change reaches the full DNA editor (outlook + Chasing/Shopping +
  // untouchables), which is a strict superset of OutlookSheet's outlook +
  // acquire/trade-away plays. So the row renders only when the bar does
  // NOT: no finder mode (classic flag-off home), the direction flag off,
  // or a non-directional outlook. Predicate is the receipt's own, so the
  // two can never both appear and can never both vanish.
  const outlookReceiptShown =
    !!finderMode &&
    outlookReceiptCovers(
      outlookDirectionOn,
      prefsQuery.data?.team_outlook ?? null,
      prefsQuery.data?.inferred_outlook ?? null,
    );

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

  // #315 — row 2 of the outlook receipt: the OTHER configurations set
  // through the sheet, so the banner honestly summarizes what "Change"
  // edits. Middle-dot separated, only set parts included. Team scope and
  // specific players are deliberately EXCLUDED — those are the interactive
  // filters mounted directly below the banner (#314); repeating them as
  // text one row above their own pills is the #205 "too much information"
  // failure. Empty ⇒ the receipt renders exactly its pre-#315 single row.
  const receiptDetails = useMemo(() => {
    const posLabel = (p: string) => (p === 'PICK' ? 'Picks' : p);
    const parts: string[] = [];
    const chasing = prefsQuery.data?.acquire_positions ?? [];
    const shopping = prefsQuery.data?.trade_away_positions ?? [];
    if (chasing.length > 0) {
      parts.push(`Chasing ${chasing.map(posLabel).join(', ')}`);
    }
    if (shopping.length > 0) {
      parts.push(`Shopping ${shopping.map(posLabel).join(', ')}`);
    }
    if (intentModesOn && tradeIntent) parts.push(TRADE_INTENT_LABEL[tradeIntent]);
    const offTable = untouchableIds?.size ?? 0;
    if (offTable > 0) parts.push(`${offTable} off the table`);
    return parts.join(' · ');
  }, [prefsQuery.data, intentModesOn, tradeIntent, untouchableIds]);

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
    // S3 PRD-02 discoverability metric — gated so flag-off emits nothing new.
    if (menuOn) {
      track('untouchable_toggled', { marked: !marked }, 'Trades');
    }
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
  // #156 finish — the pin lists moved to a session-only zustand store
  // (useFinderTargets) so the hub's Specific Player card can show live
  // counts. Semantics unchanged: session-local, cleared on league switch
  // (store subscription + the [leagueId] effect below). `packageMode` is
  // the #174 "Trade as one package" toggle (default ON, meaningful only
  // with 2+ give pins).
  const pinnedGive = useFinderTargets((s) => s.pinnedGive);
  const pinnedReceive = useFinderTargets((s) => s.pinnedReceive);
  const packageMode = useFinderTargets((s) => s.packageMode);
  const setPackageMode = useFinderTargets((s) => s.setPackageMode);
  const clearTargets = useFinderTargets((s) => s.clear);
  const [targetPickerOpen, setTargetPickerOpen] = useState(false);

  // ── #172/#189 follow-up — asset-centric grouped ideas (flag
  // trade.asset_ideas). When exactly ONE finder target is pinned (either
  // direction), fetch the Upgrade / Lateral / Downgrade sweep for it and
  // render the grouped panel ALONGSIDE the normal deck: the deck flow
  // (Find a Trade button, job polling, pins → generate payload) is
  // untouched, and 2+ pins keep today's behavior exactly. The query is
  // pin-driven (no button tap needed — the endpoint is a cheap synchronous
  // consensus sweep) and keyed on pin + direction + fairness so a re-pin
  // refetches. Tap-through hands the package to the calculator via the
  // #190 prefill param — the least-invasive full-detail view.
  const assetIdeasOn = useFlag('trade.asset_ideas');
  // #287 — the featured window renders the pinned idea as an editable
  // InLeagueCalculator instead of a read-only TradeCard tile.
  const playerOffersCalcOn = useFlag('trades.player_offers_calc');
  const singlePin =
    targetingEnabled &&
    assetIdeasOn &&
    pinnedGive.length + pinnedReceive.length === 1
      ? pinnedGive.length === 1
        ? { player: pinnedGive[0], direction: 'give' as const }
        : { player: pinnedReceive[0], direction: 'receive' as const }
      : null;
  // #298 (feedback 2026-08-10) — single-pin featured mode used to null out
  // BOTH the Find-a-Trade CTA and the whole deck wrapper, which took every
  // accept/decline path with it (swipe handlers, the pass/like row, the
  // VoiceOver actions — all of them funnel into `advance()`). Approved
  // variant V1 (mockups/polish-lab-2026-08-11/trades-single-pin-recovery
  // .html): the featured window BECOMES a deck card for the pinned asset.
  // The CTA is always mounted so a pinned deck can be generated at all; once
  // it lands, the deck leads and FeaturedTradeWindow steps aside so the two
  // never stack (that stacking was #241's "mystery second trade card").
  // `deck.length` — not `topCard` — so the deck keeps the slot through the
  // swiped-out and deck-summary states instead of snapping back to the
  // featured window mid-session.
  const singlePinFeatured = !firstRun && !!singlePin;
  // #317 — "the user tapped an idea tile AFTER finishing the pinned deck".
  // Flipped true ONLY inside handleSelectIdea's explicit-tap path (never
  // from an effect — #298 assertion 7 exists precisely to stop automatic
  // snap-backs to the featured window); reset on pin change/sweep (the
  // pinKey/ideasUpdatedAt effect below) and on every search start
  // (handleFindTrades / resetDeckForNewTargets / the legacy inline CTA),
  // so a new deck re-takes the slot exactly as #298 specified.
  const [pinIdeaResumed, setPinIdeaResumed] = useState(false);
  // #317: `&& !pinIdeaResumed` — while resumed, the layout IS the pre-deck
  // single-pin layout (featured window leads, rail at mount 1, deck
  // wrapper — summary card included — steps aside via its existing gate).
  // Still keyed on `deck.length`, still never `topCard` (#298 7a/7b).
  const singlePinDeckActive =
    singlePinFeatured && deck.length > 0 && !pinIdeaResumed;
  // #298 analytics — ONE derivation of the `mode` prop, read by both
  // find_trades_tapped and trade_card_viewed. Deliberately a property on
  // two events that already fire here, not a new event name: #298 is a
  // regression in WHERE existing controls render, so the question is "do
  // the existing events still fire from the pinned surface", and a new name
  // could not answer that (it would have no pre-fix baseline).
  // Two find_trades_tapped emitters exist below (:768 handleFindTrades and
  // the legacy `!consolidateOn` arm's inline track) — both read THIS const,
  // so the two arms can never disagree about the mode.
  const deckMode: 'single_pin' | 'deck' = singlePinFeatured ? 'single_pin' : 'deck';
  const assetIdeasQuery = useQuery({
    queryKey: [
      'asset-ideas',
      leagueId,
      singlePin?.player.id,
      singlePin?.direction,
      effectiveFairness,
      // #250 — team mode scopes the sweep to the picked league-mate.
      scopedOpponent ?? null,
    ],
    queryFn: () =>
      fetchAssetIdeas({
        league_id: leagueId!,
        asset_id: singlePin!.player.id,
        direction: singlePin!.direction,
        fairness_threshold: effectiveFairness,
        ...(scopedOpponent ? { opponent_user_id: scopedOpponent } : {}),
      }),
    enabled: !!leagueId && !!singlePin && !switching,
    staleTime: 60_000,
  });

  function handleOpenAssetIdea(idea: AssetIdea) {
    haptics.selection();
    navigation?.navigate?.('TradeCalculator', {
      prefill: {
        opponentUserId: idea.counterparty_user_id,
        giveIds: idea.give_player_ids,
        receiveIds: idea.receive_player_ids,
      },
    });
  }

  // ── #216/#209 — featured-trade window (single-pin mode) ──────────────
  // The best idea leads as a full trade card (Dynasty Value Swing verdict
  // via the reused TradeCard/TradeValueBar); the grouped list below is
  // tappable and swaps ideas into the window. History is a per-pin-session
  // stack (reset on pin change AND on a fresh sweep — a new payload
  // invalidates old idea references), capped at FEATURED_HISTORY_CAP.
  const [featuredIdea, setFeaturedIdea] = useState<AssetIdea | null>(null);
  const [ideaHistory, setIdeaHistory] = useState<AssetIdea[]>([]);
  // Window's y inside the ScrollView content (the mount is a direct child
  // of the content container) so a row tap can scroll it back into view.
  const featuredWindowY = useRef(0);
  const pinKey = singlePin
    ? `${singlePin.player.id}:${singlePin.direction}`
    : null;
  const ideasUpdatedAt = assetIdeasQuery.dataUpdatedAt;
  useEffect(() => {
    setFeaturedIdea(null);
    setIdeaHistory([]);
    // #317 — a new pin or a fresh sweep invalidates the resumed window
    // exactly like it invalidates the idea references above.
    setPinIdeaResumed(false);
  }, [pinKey, ideasUpdatedAt]);

  // #243 — pin-mode collapsed controls (V1, approved mock
  // mockups/polish-lab-2026-08/pin-mode-collapsed-controls.html B1/B2).
  // In single-pin featured mode the full Controls Card (~286pt) collapses
  // by default to a one-line "Pinned: <name> · Edit" row (~44pt); Edit
  // expands the exact existing card in place, Done collapses it again.
  // Entering the mode (or re-pinning) always starts collapsed — keyed on
  // pinKey, same reset trigger as the featured-window state above.
  const [pinEditOpen, setPinEditOpen] = useState(false);
  useEffect(() => {
    setPinEditOpen(false);
  }, [pinKey]);

  // Default featured trade = the idea with the best signed difference for
  // the user across all groups (the mock's "best" seed).
  const bestIdea = useMemo(() => {
    const g = assetIdeasQuery.data?.groups;
    if (!g) return null;
    const all = [...g.upgrade, ...g.lateral, ...g.downgrade];
    if (all.length === 0) return null;
    return all.reduce((best, i) => (i.difference > best.difference ? i : best));
  }, [assetIdeasQuery.data]);
  const featuredShown = featuredIdea ?? bestIdea;

  function handleSelectIdea(idea: AssetIdea) {
    // #317 — deck-done resume. With a pinned deck finished (summary or
    // exhausted card holding the slot, no live card, no job running — the
    // deckExhausted shape, which summaryVisible refines), an explicit tile
    // tap re-presents the featured window with this idea: the deck yields
    // the slot only on the user's own gesture, so #298's "never snap back
    // automatically" and #241's one-trade-summary both hold. The window is
    // HIDDEN here, so no row is "in window" (featuredKey is nulled at the
    // panel mount) and the usual same-idea no-op does not apply — tapping
    // the best-idea row must present it too, not dead-click.
    const deckFinished =
      singlePinFeatured && deck.length > 0 && !topCard && job?.status !== 'running';
    if (singlePinDeckActive && deckFinished) {
      haptics.selection();
      if (featuredShown && assetIdeaKey(idea) !== assetIdeaKey(featuredShown)) {
        setIdeaHistory((h) => [...h, featuredShown].slice(-FEATURED_HISTORY_CAP));
      }
      setFeaturedIdea(idea);
      setPinIdeaResumed(true);
      // No scrollTo: the window wasn't on screen, so its measured y is
      // stale (useRef(0) → a jump to page top); the layout swap surfaces
      // it at the top of the content anyway.
      return;
    }
    // No no-op taps: the in-window row is inert (also disabled in the row).
    if (!featuredShown || assetIdeaKey(idea) === assetIdeaKey(featuredShown)) {
      return;
    }
    haptics.selection();
    const replaced = featuredShown;
    setIdeaHistory((h) => [...h, replaced].slice(-FEATURED_HISTORY_CAP));
    setFeaturedIdea(idea);
    // #317 — mid-deck taps (live card showing, window hidden) keep their
    // behavior EXCEPT the stale-y scrollTo, which jumped to the page top.
    if (!singlePinDeckActive) {
      mainScrollRef.current?.scrollTo({
        y: featuredWindowY.current,
        animated: true,
      });
    }
  }

  function handleFeaturedBack() {
    const prev = ideaHistory[ideaHistory.length - 1];
    if (!prev) return;
    haptics.selection();
    setIdeaHistory((h) => h.slice(0, -1));
    setFeaturedIdea(prev);
    mainScrollRef.current?.scrollTo({
      y: featuredWindowY.current,
      animated: true,
    });
  }

  // ── Find-a-Trade: streaming job snapshot ─────────────────────────────
  // The backend runs generation in a background thread and we poll for
  // results. The job snapshot drives both the deck (cards stream in) and
  // the progress strip ("4/11 opponents searched").
  const [job, setJob] = useState<TradeJobSnapshot | null>(null);

  // P0-2 — the last search's failure, or null. Set by all three failure
  // paths, cleared by every path that starts or invalidates a search.
  const [deckFailure, setDeckFailure] = useState<DeckFailure>(null);

  // #330 R-6 — honest zero-result state for a SCOPED search: any generate
  // job that completes with zero cards while a player is pinned AND an
  // opponent is scoped (origin-independent — the handoff and a manual
  // "Find a Trade" tap get the same card). Set by the completion effect
  // below; cleared everywhere deckFailure is cleared (search start, league
  // switch, reset). Job errors stay deckFailure's; an exhausted swiped-out
  // deck stays the deck-summary's — zero cards GENERATED is the only
  // trigger.
  const [scopedEmpty, setScopedEmpty] = useState<{
    playerName: string;
    teamName: string;
    direction: 'give' | 'receive';
  } | null>(null);

  // #330 R-10 — generation epoch. Incremented by every
  // resetDeckForNewTargets(); onMutate stamps it into the mutation context
  // and every result-application site drops mismatched-epoch results via
  // applyJobResult (a stale in-flight search can never overwrite a scoped
  // run's deck). Two manual taps without an intervening reset share an
  // epoch — last-write-wins there is pre-existing behavior, out of scope.
  const deckEpochRef = useRef(0);

  const generateMutation = useMutation({
    // `auto` marks the onboarding first-run auto-start (item 4): its
    // failures stay silent (retry below) instead of toasting. Manual taps
    // pass {} and behave exactly as before. `force` (item 7) skips the
    // server's complete-fresh job cache — used by the post-Quick-Set
    // regeneration, whose board change doesn't alter the cache key.
    mutationFn: (vars: { auto?: boolean; force?: boolean }) => {
      // Pins are read from the store (not the render closure) so a
      // pin-then-generate in the same tick (#186 keep-side) always sends
      // the fresh lists.
      const {
        pinnedGive: pins,
        pinnedReceive: wants,
        packageMode: pkg,
      } = useFinderTargets.getState();
      return generateTrades({
        league_id: leagueId!,
        fairness_threshold: effectiveFairness,
        force: vars.force || undefined,
        // FB-47 — omit (not []) when unset so untargeted payloads stay
        // byte-identical to the pre-targeting shape.
        pinned_give_players:
          targetingEnabled && pins.length > 0
            ? pins.map((p) => p.id)
            : undefined,
        pinned_receive_players:
          targetingEnabled && wants.length > 0
            ? wants.map((p) => p.id)
            : undefined,
        // #174 — "Trade as one package": with 2+ give pins and the toggle
        // ON, every card must send ALL of them. Omitted otherwise.
        pinned_give_mode:
          targetingEnabled && pkg && pins.length >= 2 ? 'all' : undefined,
        // FB #156 Specific Team — scope the sweep to one league-mate. Omitted
        // (not null) when unset so untargeted payloads stay byte-identical.
        opponent_user_id: scopedOpponent || undefined,
        // #172 — trade intent modes. Omitted (not null) when unset so
        // byte-identical payloads hold for every user who never touches
        // the chips (flag off, or flag on but no selection made).
        trade_intent: tradeIntent ?? undefined,
      });
    },
    // #330 R-10 — stamp the dispatch-time epoch; onSuccess/onError compare
    // it against the current one and drop stale results entirely.
    onMutate: () => ({ epoch: deckEpochRef.current }),
    onSuccess: (snapshot, _vars, ctx) => {
      if (
        applyJobResult(snapshot, ctx?.epoch ?? deckEpochRef.current, deckEpochRef.current) === null
      ) {
        return; // stale epoch — a reset intervened; nothing is applied
      }
      setJob(snapshot);
      setDeckFailure(null); // P0-2 — covers the auto + force + inline callers
      // For instant cache-hit responses (status === 'complete') the deck
      // populates immediately via the snapshot effect below. For 'running'
      // responses the polling effect takes over.
      if (snapshot.status === 'complete' && snapshot.cards.length === 0) {
        // #330 R-6 — pinned + scoped zero-results get the honest empty CARD
        // (set by the completion effect below), never the toast: the card
        // is the single surface for that state.
        const { pinnedGive: pg, pinnedReceive: pr } = useFinderTargets.getState();
        if (pg.length + pr.length > 0 && scopedOpponent) return;
        // #172 — an active intent gets its own honest empty-state copy
        // (same mechanism as the existing fairness-aware message, not a
        // new one) so "no results" reads as "no results for THIS shape",
        // not "the finder is broken".
        const intentCopy: Record<NonNullable<TradeIntent>, string> = {
          consolidate: 'No consolidation trades found right now.',
          tier_up: 'No tier-up trades found right now.',
          tier_down: 'No tier-down trades found right now.',
        };
        setToast({
          msg: tradeIntent
            ? intentCopy[tradeIntent]
            : fairnessOn
              ? 'No fair trades found. Try turning Trade fairness off.'
              : 'No trades found. Rank more players or try again later.',
          tone: 'warn',
        });
      }
    },
    onError: (e: Error, vars, ctx) => {
      // #330 R-10 — a stale mutation's failure is as dead as its success:
      // no toast, no deckFailure, no auto-retry from a superseded dispatch.
      if (
        applyJobResult(e, ctx?.epoch ?? deckEpochRef.current, deckEpochRef.current) === null
      ) {
        return;
      }
      if (vars?.auto) {
        // First-run auto-start failed — most likely the LeaguePicker
        // background session_init hasn't landed yet. Retry once, quietly;
        // a second failure surfaces the P0-2 deck-failure card (S-08), whose
        // "Try again" is the recovery path. Auto failures stay toast-free —
        // the card is the whole surface.
        if (autoGenRef.current === 'kicked') {
          autoGenRef.current = 'retrying';
          autoRetryTimer.current = setTimeout(() => {
            autoRetryTimer.current = null;
            generateMutation.mutate({ auto: true });
          }, 4000);
        } else {
          autoGenRef.current = 'failed';
          setAutoGenFailed(true);
          setDeckFailure({ kind: 'generate', message: DECK_FAIL_GENERIC });
        }
        return;
      }
      setToast({ msg: e.message || 'Generate failed', tone: 'warn' });
      setDeckFailure({ kind: 'generate', message: readErrorCopy(e, DECK_FAIL_GENERIC) });
    },
  });

  // Poll while a job is running. Self-scheduling setTimeout loop with
  // exponential backoff (INIT-13): starts at 800ms, resets on progress,
  // backs off to 4000ms when the backend isn't advancing.
  //
  // Failure handling: after MAX_POLL_FAILURES consecutive errors we surface
  // a toast, clear the local job (the server-side worker keeps running so the
  // next tap can hit the warm cache) and record a `poll_abandoned` deckFailure
  // so the deck slot shows the named failure state rather than the
  // never-searched card (P0-2).
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
    // #330 R-10 — the epoch this poll loop attached under. A reset while a
    // status fetch is in flight nulls `job` (cleanup flips `cancelled`),
    // but the awaited response can still race the cleanup — route the
    // application through the same epoch guard as the mutation callbacks.
    const tickEpoch = deckEpochRef.current;

    const tick = async () => {
      if (cancelled) return;
      try {
        const next = await getTradeStatus(job.job_id);
        if (cancelled) return;
        if (applyJobResult(next, tickEpoch, deckEpochRef.current) === null) return;
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
          setDeckFailure({ kind: 'poll_abandoned', message: DECK_FAIL_NETWORK });
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

  // P0-2 — mirror a job-level failure into the one-funnel deckFailure state.
  //
  // Why an EFFECT and not a render-time read of `job?.status === 'error'`:
  // RECENCY. `job` is not cleared when a retry's POST fails (the onError
  // handler writes deckFailure and leaves `job` alone, deliberately — the
  // skeleton row's guard and the Find-a-Trade button both still read it). A
  // render-time read would therefore resurrect the OLD job's message over the
  // NEW failure the user just caused. Mirroring makes every path a write into
  // one slot, so last-write-wins is the whole conflict-resolution rule.
  //
  // One-directional by design: this effect only SETS. Clearing lives on the
  // transition sites above — a clear here would fight `handleFindTrades` on
  // the retry tick (job still 'error', deckFailure just cleared).
  useEffect(() => {
    if (job?.status !== 'error') return;
    setDeckFailure({ kind: 'job_error', message: jobErrorCopy(job.error) });
  }, [job?.status, job?.error]);

  // #330 R-6 — scoped-empty derivation, at COMPLETION time. Both zero-card
  // paths funnel through `job` (instant cache-hit onSuccess and the polled
  // completion), so one effect covers them. Keyed on job_id too: a manual
  // re-run of the same scoped search always creates a fresh job (pinned
  // jobs bypass the server cache in both directions), and without the key
  // a second zero-card completion — same status, same length — would never
  // re-fire after handleFindTrades cleared the card (the B-3 dishonesty
  // this exists to prevent). Names derive from the pin + scoped opponent at
  // completion, never from handoff origin. Errors never reach here
  // (status 'error' → deckFailure owns it); a completed job WITH cards
  // clears any stale card.
  useEffect(() => {
    if (job?.status !== 'complete') return;
    if (job.cards.length > 0) {
      setScopedEmpty(null);
      return;
    }
    const { pinnedGive: pg, pinnedReceive: pr } = useFinderTargets.getState();
    const pinned = pg[0] ?? pr[0];
    if (!pinned || !scopedOpponent) return;
    setScopedEmpty({
      playerName: pinned.name,
      teamName: scopedOpponentName || 'that team',
      direction: pg.length > 0 ? 'give' : 'receive',
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.job_id, job?.status, job?.cards.length]);

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
    // #276 — the generated card is now on screen (or about to be, once this
    // render commits): scroll it fully into view. Armed by handleFindTrades,
    // consumed the first time THIS job reports any cards at all (covers
    // both an empty-deck first search and a "Find more trades" tap that
    // streams fresh cards on top of an existing deck).
    if (pendingScrollToDeckRef.current && job.cards.length > 0) {
      pendingScrollToDeckRef.current = false;
      requestAnimationFrame(() => {
        mainScrollRef.current?.scrollTo({
          y: Math.max(deckCardY.current - space.md, 0),
          animated: true,
        });
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.cards.length, job?.status]);

  // When the user switches leagues, drop the local deck/job so the next
  // "Find a Trade" tap kicks off a fresh job instead of streaming into
  // stale state. (The fairness toggle handles its own reset inline.)
  // FB-47 targets are roster-specific, so they clear with the league too.
  useEffect(() => {
    // Commit any undoable pass against the OLD league before the reset,
    // and let the guard/match maps start fresh for the new one.
    flushPendingPassRef.current();
    lastDispositionedRef.current = null;
    matchIdByTradeRef.current.clear();
    setDeck([]);
    setDeckIdx(0);
    setLaneFilter(null);
    setTradeIntent(null); // #172 — a declared shape is league-specific
    setJob(null);
    setDeckFailure(null); // P0-2 — last league's failure never follows you
    setScopedEmpty(null); // #330 — ditto for the scoped zero-result card
    setEdits({});
    setSwapTarget(null);
    setSuggestTarget(null);
    clearTargets(); // store also self-clears via its league subscription
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

  // F10 (deck.replenishment): a new job (fresh generation) or any deck
  // reset (job → null: league switch, fairness toggle, target change) starts
  // a new tally episode. Keying on job_id + league covers every reset site
  // without touching them individually.
  useEffect(() => {
    if (!replenishmentOn) return;
    setSessionTally({ passed: 0, liked: 0, proposed: 0 });
    setSummaryDismissed(false);
  }, [replenishmentOn, job?.job_id, leagueId]);

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
    mutationFn: ({ card, decision, signal }: {
      card: TradeCard;
      decision: 'like' | 'pass';
      // F1 (deck.signal_v2): optional per-disposition signal fields; only
      // populated by advance() when the flag is on AND the card carries an
      // impression_id. Absent ⇒ the POST body is byte-identical to pre-F1.
      signal?: SwipeSignal;
    }) => swipeTrade(card, decision, signal),
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
    onSuccess: (res: any, vars, ctx) => {
      // S7 PRD-01 (growth.share_landing): a like that completes a mutual
      // match returns { matched: true, match_id } — remember the match id
      // so shareLikedTrade can point at the /s/trade/<match_id> landing
      // page (OG card) instead of the bare site root.
      if (ctx?.rawId && res?.matched === true && res?.match_id != null) {
        matchIdByTradeRef.current.set(ctx.rawId, String(res.match_id));
      }
      if (vars.decision === 'like') {
        // Liked-trades count is per-league (backend filters by session). Use a
        // league-scoped key so switching leagues doesn't show a stale count.
        queryClient.invalidateQueries({ queryKey: ['liked-trades', leagueId] });
        // N6.1 (PRD §5.3): first-like determination and the empty-awaiting
        // gate BOTH live here, on the swipe response. A like-time read lets
        // two rapid likes both see first-like true, and a like-time prefetch
        // races the POST and reads a list that cannot contain this like.
        // No-op unless guide_v2 is on.
        v2OnLikeSwipeSuccess(res);
      }
    },
    onError: (err, _vars, ctx) => {
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
      // The rewind above re-fronts the card `advance()` just stamped into the
      // double-fire guard, so clear it — otherwise every later ✕/✓/swipe on
      // that card is a silent no-op and the deck stalls with no error and no
      // visual change. Same reason handleLaneFilter clears when a lane change
      // re-surfaces an already-dispositioned card. Clearing on the id match
      // (not inside the rewind branch) also covers the no-rewind case, so a
      // poisoned id is never left behind.
      if (ctx?.rawId && lastDispositionedRef.current === ctx.rawId) {
        lastDispositionedRef.current = null;
      }
      queryClient.invalidateQueries({ queryKey: ['liked-trades', leagueId] });
      // No Retry action on either branch. The guard is cleared just above, so
      // the card's own ✕/✓ now re-POSTS *and* advances the deck — strictly
      // more than a Retry button could do, which would re-POST while leaving
      // the card fronted and invite a second, duplicate pass
      // (`save_trade_decision` is a plain INSERT: a repeat writes a second row
      // and replays `trade_k_pass` twice). The 403 is a standing gate rather
      // than a blip, so it says so and points at the verify banner the same
      // failure just raised.
      setToast({
        msg: err instanceof ApiError && err.isVerificationRequired
          ? 'Verify your account to save swipes — see the banner above.'
          : "Swipe didn't save. Tap again to retry.",
        tone: 'warn',
        holdMs: SWIPE_ERROR_HOLD_MS,
      });
    },
  });

  // ── Triage undo (S3 PRD-03, flag ux.swipe_undo) ──────────────────────
  // Design decision (documented for the build report): a pass swipe's
  // disposition POST is DELAYED for UNDO_HOLD_MS rather than reversed —
  // the swipe API has no void/unswipe endpoint (api/trades.ts:swipeTrade →
  // POST /api/trades/swipe is decision-final and feeds Elo), so holding the
  // write is the only path that keeps an undone pass out of the
  // disposition signal entirely. The deck advances optimistically as
  // always; Undo rewinds deckIdx and drops the pending write. Any newer
  // disposition, deck reset, league switch, or unmount FLUSHES the pending
  // pass first so ordering and at-most-one-pending invariants hold.
  const pendingPassRef = useRef<{
    card: TradeCard;
    rawId: string;
    timer: ReturnType<typeof setTimeout>;
    // F1 (deck.signal_v2): dwell/engagement captured at disposition time —
    // the held POST must carry the numbers from when the swipe happened,
    // not from when the undo window expires.
    signal?: SwipeSignal;
  } | null>(null);
  // Double-fire guard (S3B-08): last-dispositioned RAW trade_id — the tap
  // and gesture paths can both fire advance() for the same top card.
  const lastDispositionedRef = useRef<string | null>(null);
  // `swipe_guard_blocked` bookkeeping (B4 / D-068 follow-up). Consecutive
  // blocks on ONE (card, guard) pair — reset when either changes, so this
  // measures a single predicament and never accumulates across the deck.
  // `sessionEmitted` is the hard backstop: a user in a tight loop must not
  // be able to fill the 500-event SDK queue and evict real funnel rows.
  const guardBlockRef = useRef<{ key: string | null; n: number; sessionEmitted: number }>(
    { key: null, n: 0, sessionEmitted: 0 },
  );
  // S7 PRD-01 — trade_id → mutual-match id learned from swipe responses.
  const matchIdByTradeRef = useRef<Map<string, string>>(new Map());
  // Current sorted deck for callbacks whose closures may be stale (the
  // Undo toast action outlives the render that created it).
  const sortedDeckRef = useRef<TradeCard[]>([]);

  // ── F1 signal spine (flag deck.signal_v2) ────────────────────────────
  // Dwell = card fronted → disposition, paused while the app is
  // backgrounded, capped at DWELL_CAP_MS. Engagement bits reset per
  // fronted card. Ref-only bookkeeping — nothing is sent unless the flag
  // is on AND the served card carried an impression_id (signalForCard).
  const dwellRef = useRef<{
    startedAt: number;
    pausedAt: number | null;
    pausedTotal: number;
  }>({ startedAt: Date.now(), pausedAt: null, pausedTotal: 0 });
  const engagementRef = useRef({ detailExpanded: false, calcOpened: false });
  const viewedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function currentDwellMs(): number {
    const d = dwellRef.current;
    const end = d.pausedAt ?? Date.now();
    return Math.max(0, Math.min(DWELL_CAP_MS, end - d.startedAt - d.pausedTotal));
  }

  function signalForCard(card: TradeCard | undefined): SwipeSignal | undefined {
    if (!signalV2On || !card?.impression_id) return undefined;
    return {
      impression_id: card.impression_id,
      dwell_ms: currentDwellMs(),
      detail_expanded: engagementRef.current.detailExpanded,
      calc_opened: engagementRef.current.calcOpened,
    };
  }

  // Pause/resume the dwell timer on app background (PRD F1: backgrounding
  // must not inflate dwell). Flags off ⇒ no listener at all. F4 also rides
  // the dwell timer (pass classification), so deck.session_rerank keeps it
  // running even when deck.signal_v2 is off — no telemetry is sent in that
  // combination (signalForCard still gates on signalV2On).
  useEffect(() => {
    if (!signalV2On && !rerankOn) return;
    const sub = AppState.addEventListener('change', (st) => {
      const d = dwellRef.current;
      if (st === 'active') {
        if (d.pausedAt != null) {
          d.pausedTotal += Date.now() - d.pausedAt;
          d.pausedAt = null;
        }
      } else if (d.pausedAt == null) {
        d.pausedAt = Date.now();
      }
    });
    return () => sub.remove();
  }, [signalV2On, rerankOn]);

  // ── F4 session re-rank (flag deck.session_rerank) ────────────────────
  // Session state is ref-only and dies with the deck: reset on new job /
  // regenerate / league switch (effect below), on deck completion (the
  // deckExhausted effect), and trivially on unmount/relaunch (nothing is
  // ever persisted). Pure math lives in utils/sessionRerank.ts.
  //
  //   rerankEventsRef  — last-k dispositions (attrs + reward), newest last.
  //   servedIndexRef   — trade_id → order the server streamed the card in
  //                      (assigned at first sight, never reassigned; the
  //                      re-rank's base score is 1/(servedIndex+1)).
  //   pendingRerankMovesRef — moves computed inside the setDeck updater,
  //                      flushed to analytics by the [deck] effect below
  //                      (side effects don't belong in state updaters).
  //   lastRerankedRef  — max-ONE-reorder-per-disposition guard on the raw
  //                      trade_id (advance()'s own double-fire guard only
  //                      exists when ux.swipe_undo is on).
  const rerankEventsRef = useRef<RerankEvent[]>([]);
  const servedIndexRef = useRef<Map<string, number>>(new Map());
  const pendingRerankMovesRef = useRef<RerankMove[] | null>(null);
  const lastRerankedRef = useRef<string | null>(null);
  // Set by handleFlagBadTrade just before its advance('pass') so the
  // disposition records as `not_interested` (−2) instead of a pass.
  const nextDispositionNotInterestedRef = useRef(false);

  // Hard reset: a fresh job (generate/regenerate mints a new job_id) or a
  // league switch starts a clean session vector. Mirrors the F10 tally
  // effect's keying — every deck-reset site funnels through job/league.
  useEffect(() => {
    rerankEventsRef.current = [];
    servedIndexRef.current = new Map();
    pendingRerankMovesRef.current = null;
    lastRerankedRef.current = null;
  }, [rerankOn, job?.job_id, leagueId]);

  // ── F9 first-session win (flag deck.first_session) ───────────────────
  // Session tallies for the first-deck activation layer. Ref-only, reset
  // per job/league like the F4 vector; the once-per-app-session guard on
  // the adaptation moment is module-level (adaptationMomentShownThisSession).
  //   fsDispositionsRef — dispositions this deck session (1-based ordinal
  //                       feeds first_session_like.position).
  //   fsLikesRef        — attrs (+ counterparty) of each liked card, for
  //                       the dominant-attribute trigger.
  //   fsFirstLikeTrackedRef / fsCompletionTrackedRef — one-shot event guards.
  const fsDispositionsRef = useRef(0);
  const fsLikesRef = useRef<FirstSessionLike[]>([]);
  const fsFirstLikeTrackedRef = useRef(false);
  const fsCompletionTrackedRef = useRef(false);
  useEffect(() => {
    fsDispositionsRef.current = 0;
    fsLikesRef.current = [];
    fsFirstLikeTrackedRef.current = false;
    fsCompletionTrackedRef.current = false;
    setAdaptationMoment(null);
  }, [firstSessionOn, job?.job_id, leagueId]);

  // Served-order bookkeeping: cards enter `deck` in served order (the
  // append effect above dedups + appends), so first-sight index == served
  // index. Later reorders never touch existing entries.
  useEffect(() => {
    if (!rerankOn) return;
    const map = servedIndexRef.current;
    for (const c of deck) {
      if (!map.has(c.trade_id)) map.set(c.trade_id, map.size);
    }
  }, [rerankOn, deck]);

  // Telemetry flush (PRD F4 §5): when deck.signal_v2 is ALSO on, each
  // applied reorder logs through the existing F1 client event side-channel
  // (api/events track → /api/events). Set inside the setDeck updater,
  // flushed here after the commit. No backend endpoint is added.
  useEffect(() => {
    const moves = pendingRerankMovesRef.current;
    if (!moves || moves.length === 0) return;
    pendingRerankMovesRef.current = null;
    if (!signalV2On) return;
    const byId = new Map(deck.map((c) => [c.trade_id, c]));
    track(
      'deck_reranked',
      {
        moved: moves.length,
        // Cap the per-event payload; from/to are DECK positions (the F1
        // impression rows carry position_in_deck for the join).
        moves: moves.slice(0, 10).map((m) => ({
          trade_id: m.trade_id,
          ...(byId.get(m.trade_id)?.impression_id
            ? { impression_id: byId.get(m.trade_id)!.impression_id }
            : {}),
          from: m.from,
          to: m.to,
        })),
      },
      'Trades',
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deck]);

  /** Record one disposition into the session vector and apply AT MOST one
   *  reorder of the remaining cards. Called from advance() only. */
  function applySessionRerank(
    card: TradeCard,
    rawId: string,
    disposition: RerankDisposition,
    dwellMs: number,
  ) {
    if (lastRerankedRef.current === rawId) return; // one reorder/disposition
    lastRerankedRef.current = rawId;
    const events = rerankEventsRef.current;
    events.push({
      tradeId: rawId,
      attrs: extractCardAttributes(card),
      weight: dispositionWeight(disposition, dwellMs),
    });
    if (events.length > SESSION_RERANK_LAST_K) {
      events.splice(0, events.length - SESSION_RERANK_LAST_K);
    }
    // Reorder only while the DISPLAY order is the deck order — with the
    // fairness toggle off or a lane filter active, sortedDeck is a
    // different projection and deck indices aren't screen positions, so
    // moving deck entries could violate the next-card guard. The vector
    // keeps accumulating either way.
    if (!fairnessOn || laneFilter) return;
    const boost = buildBoostVector(events);
    if (isZeroVector(boost)) return;
    setDeck((prev) => {
      const curIdx = prev.findIndex((c) => c.trade_id === rawId);
      if (curIdx < 0) return prev;
      // Positions ≤ curIdx+1 are untouchable: curIdx+1 was the peeked next
      // card and fronts in this same commit (setDeckIdx is batched with
      // this update) — it must never swap under the user's thumb.
      const { order, moves } = rerankRemaining(
        prev,
        curIdx + 2,
        boost,
        servedIndexRef.current,
      );
      if (moves.length === 0) return prev;
      pendingRerankMovesRef.current = moves; // idempotent under re-invoke
      return order;
    });
  }

  function flushPendingPass() {
    const p = pendingPassRef.current;
    if (!p) return;
    pendingPassRef.current = null;
    clearTimeout(p.timer);
    swipeMutation.mutate({ card: p.card, decision: 'pass', signal: p.signal });
  }
  // Latest-instance ref so the unmount cleanup can flush without a stale
  // closure over swipeMutation.
  const flushPendingPassRef = useRef(flushPendingPass);
  flushPendingPassRef.current = flushPendingPass;

  function undoPass() {
    const p = pendingPassRef.current;
    if (!p) return;
    pendingPassRef.current = null;
    clearTimeout(p.timer);
    lastDispositionedRef.current = null;
    // F4 (deck.session_rerank): the undone pass never became a real
    // disposition — pop its event so the vector forgets it, and re-arm the
    // one-reorder guard so a re-swipe of this card records fresh. An
    // already-applied reorder stays (it only touched positions the user
    // hadn't seen); the next disposition recomputes from the corrected
    // vector.
    if (rerankOn) {
      const evts = rerankEventsRef.current;
      if (evts.length > 0 && evts[evts.length - 1].tradeId === p.rawId) {
        evts.pop();
      }
      if (lastRerankedRef.current === p.rawId) lastRerankedRef.current = null;
    }
    // F10 (deck.replenishment): an undone pass leaves the tally episode.
    if (replenishmentOn) {
      setSessionTally((t) => ({ ...t, passed: Math.max(0, t.passed - 1) }));
    }
    // F9 (deck.first_session): the undone pass never became a real
    // disposition — back it out of the session tally so the first-like
    // position ordinal stays honest (likes commit immediately, so
    // fsLikesRef needs no correction).
    if (firstSessionOn && job?.first_deck) {
      fsDispositionsRef.current = Math.max(0, fsDispositionsRef.current - 1);
    }
    setDeckIdx((cur) => {
      const idx = sortedDeckRef.current.findIndex((c) => c.trade_id === p.rawId);
      return idx >= 0 ? idx : Math.max(0, cur - 1);
    });
    // F1 (deck.signal_v2): the undo outcome rides the existing event as an
    // additive prop — the server's /api/events hook appends an `undo`
    // deck_outcomes row. (The held pass never POSTed, so no pass outcome
    // exists for this card; undo appends, nothing is mutated.)
    track(
      'swipe_undone',
      {
        trade_id: p.rawId,
        ...(p.signal?.impression_id ? { impression_id: p.signal.impression_id } : {}),
      },
      'Trades',
    );
  }

  // Commit any pending pass on unmount — leaving the screen ends the undo
  // window; the disposition must not be silently lost.
  useEffect(
    () => () => {
      flushPendingPassRef.current();
    },
    [],
  );

  // Bad-trade flag (feedback #85) — engine-quality signal, distinct from
  // pass. Best-effort: the deck has already advanced via the pass path, so
  // a failed flag just toasts instead of rewinding (the pass swipe carries
  // the "not interested" signal regardless).
  const flagMutation = useMutation({
    // F1 (deck.signal_v2): impressionId joins the flag to its impression as
    // a `not_interested` outcome; undefined (flag off / no id) is dropped
    // at the API layer so the body stays byte-identical to pre-F1.
    mutationFn: ({ card, impressionId }: { card: TradeCard; impressionId?: string }) =>
      flagBadTrade(card, undefined, impressionId),
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
  // Only fetched while a picker that needs it is actually open (#156
  // finish: the in-screen team picker shares the same cache key with the
  // hub's manager picker).
  const leagueUsersQuery = useQuery({
    queryKey: ['league-users', leagueId],
    queryFn: () => getLeagueUsers(leagueId!),
    enabled:
      !!leagueId &&
      ((targetingEnabled && targetPickerOpen) || teamPickerOpen),
    staleTime: 5 * 60_000,
  });
  // Which league member the caller IS: the primary owner of the roster they
  // own or CO-own. Every "not me" filter and "my roster" lookup below keys off
  // this, not the account id — a co-manager's own id owns no roster row, so
  // `userId` left their own team in the team picker and their trade-away pool
  // empty. Identical to `userId` for a sole owner (scope.md §0.1 A).
  const myOwner = useMemo(
    () => myOwnerId(rostersQuery.data, userId),
    [rostersQuery.data, userId],
  );
  // #156 finish — league-mates for the in-screen team picker.
  const teamPickerOpponents = useMemo(
    () => (leagueUsersQuery.data ?? []).filter((u) => u.user_id !== myOwner),
    [leagueUsersQuery.data, myOwner],
  );
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
      if (ownerId === myOwner) continue;
      for (const id of ids) m.set(id, ownerId);
    }
    return m;
  }, [rosterByOwner, myOwner]);
  const usernameByOwner = useMemo(() => {
    const m = new Map<string, string>();
    for (const u of leagueUsersQuery.data ?? []) {
      m.set(u.user_id, u.display_name || u.username || u.user_id);
    }
    return m;
  }, [leagueUsersQuery.data]);
  const targetPickerPool = useMemo<CalcPlayer[]>(() => {
    if (!targetPickerOpen) return [];
    // #250 — Specific Team mode: acquire options come ONLY from the scoped
    // opponent's roster. Trade-away (the user's own players) is unaffected,
    // and every other mode keeps the full leaguemate pool.
    const ids =
      targetDirection === 'trade_away'
        ? rosterByOwner.get(myOwner) ?? []
        : scopedOpponent
          ? rosterByOwner.get(scopedOpponent) ?? []
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
        // Canonical pick verdict from the server (see calc.ts is_pick).
        isPick: r.is_pick,
      }));
  }, [targetPickerOpen, targetDirection, rosterByOwner, ownerByPlayerId, valueById, myOwner, scopedOpponent]);

  // Any target change invalidates the current deck — the next "Find a
  // Trade" tap regenerates through the normal job flow (pinned jobs bypass
  // the server cache). Deliberately NOT auto-firing a job per chip change.
  function resetDeckForNewTargets() {
    // #330 R-10 — every reset opens a new generation epoch; results from
    // dispatches stamped under an older epoch are dropped on arrival.
    deckEpochRef.current += 1;
    flushPendingPassRef.current(); // commit any undoable pass before reset
    lastDispositionedRef.current = null; // regenerated decks can reuse ids
    setDeck([]);
    setDeckIdx(0);
    setLaneFilter(null);
    setJob(null);
    setScopedEmpty(null); // #330 — a reset invalidates the scoped zero-result card
    setEdits({});
    setSwapTarget(null);
    setPinIdeaResumed(false); // #317 — the next deck re-takes the slot
  }

  // FB #156 — entering or changing a hub finder mode/scope starts a clean
  // deck so team-scoped or player-targeted results never mix with a prior
  // mode's cards. Gated to hub launches; the standalone Trades home never
  // runs this (finderMode is undefined there).
  //
  // Finish item 4: an IN-PLACE team pick (mode-bar chip → picker →
  // setParams) also kicks generation immediately, so the deck re-fills
  // for the new opponent without a manual "Find a Trade" tap. The FIRST
  // run (entry from the hub) keeps the historical manual start.
  //
  // #298, second defect (2026-08-10) — the regenerate condition used to read
  // `finderMode === 'team'`, but since #269 the opponent's SOURCE moved to
  // sheet-local state and the #270 strip's "Trading with" pill scopes one
  // WITHOUT leaving guided mode. So picking a team in guided mode hit the
  // reset above and nothing else: the deck silently emptied and regenerated
  // nothing, dropping the user to "Hit Find a Trade to start". The condition
  // is now "an opponent is scoped", which is what the branch always meant —
  // legacy team mode is unchanged (there, scoping IS the mode), and with
  // `trades.sheet_targeting` off `scopedOpponent` can only come from team
  // mode's route params, so this reads exactly as it did before.
  // CLEARING an opponent still only resets: broadening the search is not a
  // request for a new sweep, and it matches how pin add/remove behaves.
  // ── #330 — Offer/Target handoff consumption (one-shot, focus-gated) ───
  // LeagueSummaryScreen's row action pins the player (store `setSide`, the
  // #300 contract) and now also parks a `handoff` {opponent, autoRun, seq}.
  // Consumed HERE, on focus, exactly once: null the store field, adopt the
  // opponent into sheet state, record the handoff's seq, and arm the
  // auto-run ref — then let the existing scoped-opponent choke point below
  // do the actual reset + dispatch. `navigation.navigate` in the row action
  // focuses this screen right after setHandoff, so consumption is prompt;
  // an un-consumed handoff (user never visits the tab) parks in the store
  // until focus, `clear()`, or the league-switch GC — no timeout.
  //
  // Degradation matrix (R-8): when the choke point is gated off
  // (`trades.finder_hub` OFF or no finderMode) the ref is NOT armed and the
  // seq NOT recorded — the handoff degrades to prefill-without-autorun
  // instead of leaving an armed ref to detonate on a later mode entry.
  const navFocused = useIsFocused();
  const finderHandoff = useFinderTargets((s) => s.handoff);
  const [autoRunSeq, setAutoRunSeq] = useState(0);
  const autoRunPendingRef = useRef(false);
  useEffect(() => {
    if (!navFocused || !finderHandoff) return;
    useFinderTargets.getState().setHandoff(null); // one-shot: consume first
    setSheetOpponent(finderHandoff.opponent);
    if (finderHubOn && finderMode) {
      autoRunPendingRef.current = true;
      setAutoRunSeq(finderHandoff.seq);
    }
  }, [navFocused, finderHandoff, finderHubOn, finderMode]);

  const finderScopeSeen = useRef(false);
  useEffect(() => {
    if (!finderHubOn || !finderMode) return;
    resetDeckForNewTargets();
    // #330 — an armed handoff widens the fresh-mount gate (generate even on
    // the first observation) and, via the `autoRunSeq` dep, re-fires this
    // effect for a repeat Offer to the SAME team (`scopedOpponent` is a
    // derived string — unchanged in that case). One choke point, one
    // dispatch per handoff; no new mutate site.
    const autoRun = autoRunPendingRef.current;
    if ((finderScopeSeen.current || autoRun) && scopedOpponent) {
      autoRunPendingRef.current = false;
      if (autoRun) {
        // R-4 — the auto-run is a find-trades dispatch the user asked for
        // with the Offer/Target tap; same event, attributable source.
        track('find_trades_tapped', { source: 'league_offer', mode: deckMode }, 'Trades');
      }
      generateMutation.mutate({});
      // The sweep about to land IS the current prefs — don't leave the #257
      // "Preferences changed" nudge armed by the pick that triggered it
      // (handleFindTrades clears these on the manual path).
      prefsChangedSinceGenerateRef.current = false;
      setShowPrefsChangedStrip(false);
    }
    finderScopeSeen.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finderMode, scopedOpponent, autoRunSeq]);

  function handleAddTarget(p: CalcPlayer) {
    const player: Player = {
      id: p.id,
      name: p.name,
      position: p.pos,
      team: p.nflTeam,
      age: p.age,
    };
    const store = useFinderTargets.getState();
    if (targetDirection === 'trade_away') store.addGive(player);
    else store.addReceive(player);
    haptics.selection();
    // N4's adoption receipt (PRD §5.3.1). `side` uses the give/receive
    // vocabulary the taxonomy registered; `source` separates the guided
    // hand-off off the deck-summary card from an organic board pin, so
    // adoption is attributable without a session join. The client receipt
    // is what actually retires the beat — a retirement wired to an event
    // the client can't observe never fires (FR-E3).
    if (guideV2Active()) {
      track(
        'finder_target_pinned',
        {
          side: targetDirection === 'trade_away' ? 'give' : 'receive',
          source: v2PinHandoffRef.current ? 'deck_summary' : 'board',
        },
        'Trades',
      );
      recordGuideReceipt(GUIDE_RECEIPTS.finderTargetPinned);
      v2PinHandoffRef.current = false;
    }
    resetDeckForNewTargets();
  }

  function handleRemoveTarget(id: string, dir: 'trade_away' | 'acquire') {
    const store = useFinderTargets.getState();
    if (dir === 'trade_away') store.removeGive(id);
    else store.removeReceive(id);
    haptics.selection();
    resetDeckForNewTargets();
  }

  // #186 — "keep this side": pin the top card's liked side wholesale and
  // regenerate, so the deck re-fills with other offers around it. Pure
  // shortcut into the existing FB-47 targeting machinery: keep-give pins
  // the send side (packageMode then holds it together per #174), keep-
  // receive pins the get side (cards must return ≥1 of them).
  function handleKeepSide(card: TradeCard, side: 'give' | 'receive') {
    haptics.selection();
    // #288 — snapshot the deck before resetDeckForNewTargets wipes it, so
    // the found-trade-card → "other options for that player" flow this
    // action enters can be undone. Captured only from a clean, unpinned
    // deck (this action's actual entry point) so a later re-pin from an
    // already-pinned state never clobbers the ORIGINAL context with a
    // stale in-between one.
    if (pinnedGive.length + pinnedReceive.length === 0) {
      preSinglePinSnapshotRef.current = { deck, deckIdx, job };
    }
    // F1 (deck.signal_v2): a keep-side tap is deeper-than-glance engagement.
    if (signalV2On) engagementRef.current.detailExpanded = true;
    useFinderTargets
      .getState()
      .setSide(side, side === 'give' ? card.give_players : card.receive_players);
    track('trade_keep_side_tapped', { side }, 'Trades');
    resetDeckForNewTargets();
    generateMutation.mutate({});
  }

  // #288 — the pin-summary row's clear/back affordance: unpin and, when
  // the pin was entered via "Keep · more offers" on a clean deck (the
  // found-trade-card → "other options" flow), restore that ORIGINAL deck
  // position + card exactly rather than leaving an empty deck behind. Pins
  // entered any other way (e.g. the player-mode target board) have no
  // snapshot to restore — clearing still unpins and leaves the ordinary
  // empty-deck state, where "Find a Trade" is always the recovery path, so
  // the user is never stranded either way.
  function handleClearPin() {
    haptics.selection();
    const snap = preSinglePinSnapshotRef.current;
    flushPendingPassRef.current();
    lastDispositionedRef.current = null;
    clearTargets();
    setLaneFilter(null);
    setEdits({});
    setSwapTarget(null);
    if (snap) {
      setDeck(snap.deck);
      setDeckIdx(snap.deckIdx);
      setJob(snap.job);
    } else {
      setDeck([]);
      setDeckIdx(0);
      setJob(null);
    }
    preSinglePinSnapshotRef.current = null;
    track('trade_pin_cleared', { restored: !!snap }, 'Trades');
  }

  // F3 (deck.fatigue) — deck-note "Undo": lift the newest decline
  // suppression server-side, then regenerate so the hidden trades can
  // come back. force:true — the server invalidated its cache on the lift,
  // but a stale in-flight snapshot must not short-circuit the re-run.
  async function handleSuppressionUndo() {
    if (!leagueId || suppressionUndoPending) return;
    haptics.selection();
    setSuppressionUndoPending(true);
    track('suppression_undo_tapped', undefined, 'Trades');
    try {
      await undoDeckSuppression(leagueId);
      resetDeckForNewTargets();
      generateMutation.mutate({ force: true });
    } catch {
      setToast({ msg: 'Could not undo — try again', tone: 'warn' });
    } finally {
      setSuppressionUndoPending(false);
    }
  }

  // #190 — hand the top card to the manual calculator, prefilled: In-league
  // mode with this card's opponent and both sides loaded. The swap-sheet
  // in-place edit stays; this is the "full editor" path.
  function handleEditInCalculator(card: TradeCard) {
    haptics.selection();
    // F1 (deck.signal_v2): calc_opened engagement bit for this card's
    // eventual disposition outcome.
    if (signalV2On) engagementRef.current.calcOpened = true;
    track('trade_edit_in_calculator_tapped', undefined, 'Trades');
    navigation?.navigate?.('TradeCalculator', {
      prefill: {
        opponentUserId: card.opponent_user_id,
        giveIds: card.give_player_ids,
        receiveIds: card.receive_player_ids,
      },
    });
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
            // Fresh pick-denominated verdict for the re-priced package — the
            // same {give_value, receive_value, favors, gap} shape the deck
            // cards carry, so the value bar re-appears with the new numbers.
            give_value: ev.give_value,
            receive_value: ev.receive_value,
            favors: ev.favors,
            gap: ev.gap,
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
  sortedDeckRef.current = sortedDeck;

  // Lane pills render only when the engine actually laned this deck.
  const deckHasLanes = useMemo(() => deck.some((c) => !!c.lane), [deck]);

  function handleLaneFilter(lane: 'window' | 'value') {
    haptics.selection();
    // A lane change can legitimately re-surface an already-dispositioned
    // card at the top (index resets to 0) — commit any pending pass and
    // clear the double-fire guard so re-swiping it isn't no-oped.
    flushPendingPassRef.current();
    lastDispositionedRef.current = null;
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

  // #357 — lineup movement + playoff-odds shift for the FRONTED card only
  // (operator, 2026-08-19: "compute on the fronted card only"). The with-trade
  // re-simulation is ~112 ms server-side; fetching it for all ~30 deck cards
  // would add ~3.4 s to deck generation and discard most of it, because the
  // median card is passed in under a second. Keyed on trade_id, so it fires
  // exactly once per card the user actually stops on.
  const topCardImpact = useCardImpact({
    enabled: !!topCard,
    tradeId: topCard?.trade_id ?? null,
    leagueId: topCard?.league_id ?? leagueId,
    opponentUserId: topCard?.opponent_user_id ?? null,
    givePlayerIds: topCard?.give_player_ids ?? [],
    receivePlayerIds: topCard?.receive_player_ids ?? [],
    // `calcFormat`, NOT the raw `activeFormat`: the session's format is
    // legitimately null in several states, and every other consumer in this
    // file already falls back through calcFormat. Passing the raw value made
    // the hook's key null, which DISABLED the fetch and rendered nothing at
    // all — no spinner, no error. That was the "still not there" bug.
    format: calcFormat,
  });
  const nextCard = sortedDeck[deckIdx + 1];

  // ── Swap suggestions (2026-07-27 player-changer) ─────────────────────
  // Operator follow-up to the calculator eveners: counter-suggestions
  // "served as the player changer" on find-a-trade cards. The top card's
  // context menu gets a "Swap suggestions" row per asset; opening it fires
  // ONE Mode B /api/trade/evaluate of the card's trade MINUS that asset —
  // the returned `eveners` (players + owned picks + the 2-piece package)
  // are one-tap replacements for it. `one_sided_eveners` covers the
  // 1-for-1 card whose minus-trade empties a side. Picking a candidate
  // swaps it in through the same edit/re-price machinery as the classic
  // swap sheet (#86).
  const [suggestTarget, setSuggestTarget] = useState<{
    player: Player;
    side: 'give' | 'receive';
  } | null>(null);
  const suggestQuery = useQuery({
    queryKey: [
      'swap-suggest',
      rawTopCard?.trade_id,
      suggestTarget?.player.id,
      suggestTarget?.side,
    ],
    enabled:
      !!suggestTarget &&
      !!topCard?.opponent_user_id &&
      !!(topCard?.league_id || leagueId),
    staleTime: 60_000,
    queryFn: ({ signal }) => {
      const { player, side } = suggestTarget!;
      const give = topCard!.give_player_ids.filter(
        (id) => !(side === 'give' && id === player.id),
      );
      const receive = topCard!.receive_player_ids.filter(
        (id) => !(side === 'receive' && id === player.id),
      );
      return evaluateForSwapSuggestions(
        give,
        receive,
        calcFormat,
        topCard!.league_id || leagueId!,
        topCard!.opponent_user_id,
        signal,
      );
    },
  });
  // Candidates: the minus-trade's eveners, but only when the shortfall is
  // on the REMOVED asset's side — otherwise they'd be additions from the
  // OTHER roster, not replacements (honest empty instead). The removed
  // asset itself is filtered out: it's no longer "in the trade" in the
  // request, so the server would happily return it as its own best
  // replacement.
  const swapSuggestions = useMemo<CalcEvener[]>(() => {
    const data = suggestQuery.data;
    if (!data || !suggestTarget || !topCard) return [];
    const { player, side } = suggestTarget;
    if (data.gap) {
      if (data.gap.add_to !== side) return [];
    } else {
      // One-sided read (gap null): the server built eveners for the EMPTY
      // side — trust them only when that side is the removed asset's (i.e.
      // the removed asset was its side's only one).
      const sideIds =
        side === 'give' ? topCard.give_player_ids : topCard.receive_player_ids;
      if (sideIds.length > 1) return [];
    }
    return (data.eveners ?? []).filter(
      (e) => e.id !== player.id && !(e.ids ?? []).includes(player.id),
    );
  }, [suggestQuery.data, suggestTarget, topCard]);

  // ── S4 PRD-04 (ux.prompt_arbiter): one-surface arbiter ───────────────
  // At most ONE instructional/promotional surface at a time on this screen.
  // Slots are claimed in priority order (hook call order IS the tiebreak):
  // quickset prompt > coach mark > apple banner > outlook banner. Flag off:
  // each slot is a passthrough of its `wants` condition — byte-identical.
  // The swipe-hint card nudge is gesture coaching on the card itself, not a
  // stacked surface, so it doesn't claim a slot. Root modals
  // (PushPrimingModal / AppleSaveMomentSheet) self-defer while any slot is
  // claimed — see those components.
  const quicksetPromptShown = useInterruptSlot(
    'quickset_prompt',
    quicksetPromptVisible,
    'Trades',
  );
  const provenanceMarkWants =
    tradesFirstOn && guidedOn && provenanceMarkVisible && !!topCard;
  const provenanceMarkShown = useInterruptSlot(
    'coach_mark',
    provenanceMarkWants,
    'Trades',
  );
  const appleBannerWants =
    appleSaveOn &&
    !appleAsk &&
    Platform.OS === 'ios' &&
    !isDemo &&
    !user?.account_only &&
    !verification?.user_verified &&
    obSessionCount >= 2 &&
    obTotalSwipes >= 5 &&
    !session2BannerShown;
  const appleBannerShown = useInterruptSlot('apple_banner', appleBannerWants, 'Trades');
  const outlookBannerWants =
    !!inferredOutlook ||
    (outlookInlineOn && !!prefsQuery.data && !prefsQuery.data.team_outlook);
  const outlookBannerShown = useInterruptSlot(
    'outlook_banner',
    outlookBannerWants,
    'Trades',
  );

  // Analytics: one trade_card_viewed per card reaching the top of the
  // deck (keyed on trade_id, so re-renders don't re-fire). The first card
  // additionally carries time-from-app-open + the cold-start marker.
  const topTradeId = rawTopCard?.trade_id;
  useEffect(() => {
    if (!topTradeId) return;
    const props: Record<string, unknown> = {
      card_index: deckIdx,
      trade_id: topTradeId,
      // #298 — the OUTCOME half of the mode pair. Read at the moment the
      // card was FRONTED (this effect only re-runs on a new trade_id), so
      // it records the surface the card actually rendered on. A
      // find_trades_tapped{mode:single_pin} with no matching
      // trade_card_viewed{mode:single_pin} is #298 reappearing.
      mode: deckMode,
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

  // ── F1 (flag deck.signal_v2): dwell reset + the ≥500ms `viewed` outcome.
  // The unflagged trade_card_viewed event above keeps its exact timing and
  // props; this ADDITIONALLY fires deck_card_viewed (impression-joined)
  // only when the card is still front-of-deck after VIEWED_MIN_MS, so the
  // backend can distinguish served-vs-seen. Keyed like the event above:
  // per fronted trade_id, not per index change.
  const topImpressionId = signalV2On ? rawTopCard?.impression_id : undefined;
  useEffect(() => {
    // F4 (deck.session_rerank) also needs the per-card dwell reset (pass
    // classification); with signal_v2 off, topImpressionId is undefined so
    // the deck_card_viewed timer below never arms — F1 telemetry unchanged.
    if (!signalV2On && !rerankOn) return;
    dwellRef.current = { startedAt: Date.now(), pausedAt: null, pausedTotal: 0 };
    engagementRef.current = { detailExpanded: false, calcOpened: false };
    if (viewedTimerRef.current) {
      clearTimeout(viewedTimerRef.current);
      viewedTimerRef.current = null;
    }
    if (!topImpressionId || !topTradeId) return;
    const impressionId = topImpressionId;
    const tradeId = topTradeId;
    const cardIndex = deckIdx;
    viewedTimerRef.current = setTimeout(() => {
      viewedTimerRef.current = null;
      track(
        'deck_card_viewed',
        { impression_id: impressionId, trade_id: tradeId, card_index: cardIndex },
        'Trades',
      );
    }, VIEWED_MIN_MS);
    return () => {
      if (viewedTimerRef.current) {
        clearTimeout(viewedTimerRef.current);
        viewedTimerRef.current = null;
      }
    };
    // deckIdx intentionally omitted (see the effect above).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signalV2On, rerankOn, topTradeId, topImpressionId]);

  // ── Decline reasons (flag `feedback.decline_reasons`): per-fronted-card
  // reset. Stamps the render clock for SPEC §6's `ms_since_render` and drops
  // any banked pass left over from a deck reset / job swap. Flag off ⇒ the
  // effect returns on its first line and nothing here ever runs.
  useEffect(() => {
    if (!declineReasonsOn) return;
    cardRenderedAtRef.current = Date.now();
    reasonBankedIdRef.current = null;
    setReasonBankedId(null);
  }, [declineReasonsOn, topTradeId]);

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

  // ── Guided Onboarding v2 bookkeeping (flag onboarding.guide_v2) ───────
  // Every ref below is written only under `guideV2Active()`, so with the
  // flag off they hold their initial values and no branch reads them.
  // N1 — dispositions THIS app session (the beat fires on the third).
  const v2SessionDispositionsRef = useRef(0);
  // N2 — the failure family: three consecutive passes with no like.
  const v2ConsecutivePassesRef = useRef(0);
  const v2SessionHadLikeRef = useRef(false);
  const [v2N2Armed, setV2N2Armed] = useState(false);
  // "No DECLARED outlook" — an INFERRED direction still counts as absent
  // (it is exactly the Form A case: the receipt resolves off the inference,
  // and the beat asks the user to declare).
  const v2OutlookDeclared =
    !!prefsQuery.data?.team_outlook && prefsQuery.data.team_outlook !== 'not_sure';
  // N1 arms from advance() and is requested from the chain effect, so it
  // never preempts a live bubble (s2.2 is usually still up on swipe 1).
  const [v2N1Armed, setV2N1Armed] = useState(false);
  // …and s3.2 waits on it. "Settled" is the PRD's "seen OR ineligible":
  // ineligible covers redraft leagues (N1 is suppressed there), a beat the
  // engine refused (retired/invalidated/display cap), and any session past
  // the first — N1's trigger is a first-session boundary, so after that it
  // can never fire and a strict after-N1 chain would kill s3.2 forever.
  const [v2N1Skipped, setV2N1Skipped] = useState(false);
  const v2N1Seen = useOnboardingState((s) => !!s.ob.guideSeen['n1']);
  const v2N1Retired = useOnboardingState((s) => !!s.ob.guideRetired['n1']);
  const v2SessionCount = useOnboardingState((s) => s.ob.sessionCount);
  const v2N1Settled =
    v2N1Seen ||
    v2N1Retired ||
    v2N1Skipped ||
    isRedraftLeague ||
    v2SessionCount > 1;
  // N6.1 — the first-like router. The claim is taken in
  // `swipeMutation.onSuccess`, so two rapid likes cannot both read
  // first-like true; it is released again if the beat is never shown, so a
  // refused request does not burn the moment (the P0-9 bug shape).
  const v2FirstLikeClaimedRef = useRef(false);
  // The s6.2 + Apple-ask chain is deferred behind N6.1's completion. When
  // the exit was the CTA (we navigated away), it runs on the next focus
  // of this screen instead — the other three exits never leave it.
  const v2LikeChainOnFocusRef = useRef(false);
  const v2N61NavigatedRef = useRef(false);
  // N4 — the deck-summary pin hand-off, for `finder_target_pinned.source`.
  const v2PinHandoffRef = useRef(false);

  // Spotlight targets The Analyst points at on this screen.
  const deckWrapRef = useRef<View | null>(null);
  const chipWrapRef = useRef<View | null>(null);
  const trioWrapRef = useRef<View | null>(null);
  // N2 Form A's target. The `trades.outlook-receipt.change` control lives
  // inside OutlookBiasReceipt (another agent's file this wave), so the
  // registration is hosted here on the wrapper around the mounted receipt —
  // a superset of the Change link that always contains it. TODO: move to a
  // per-instance registration inside the component when that file is free.
  const outlookReceiptWrapRef = useRef<View | null>(null);
  useEffect(() => {
    registerGuideTarget('trades.card-body', deckWrapRef);
    registerGuideTarget('trades.provenance-chip', chipWrapRef);
    registerGuideTarget('trades.trio-entry', trioWrapRef);
    registerGuideTarget('trades.outlook-receipt.change', outlookReceiptWrapRef);
    return () => {
      unregisterGuideTarget('trades.card-body');
      unregisterGuideTarget('trades.provenance-chip');
      unregisterGuideTarget('trades.trio-entry');
      unregisterGuideTarget('trades.outlook-receipt.change');
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
    const v2 = guideV2Active();
    // N1 — prices, and where yours come from (PRD §5.3; replaces s2.3).
    // Armed by the third disposition of the first session; requested from
    // here so it never preempts the s2.2 coaching bubble.
    if (v2 && v2N1Armed) {
      setV2N1Armed(false);
      if (!requestGuideStep(GUIDE.n1())) setV2N1Skipped(true);
      return;
    }
    // N2 — re-aim the deck (PRD §5.3, two-form). Form A spotlights the
    // outlook receipt's Change control when the receipt actually resolves;
    // otherwise Form B, whose CTA opens the DNA sheet directly. The form is
    // chosen HERE, before the request — copy never swaps after render.
    if (v2 && v2N2Armed) {
      setV2N2Armed(false);
      if (outlookReceiptShown) {
        requestGuideStep(GUIDE.n2a());
      } else {
        // Completion is "sheet opened + ≥1 preference write" — the sheet
        // records the `outlook_saved` receipt itself; this CTA only opens
        // it (NG-11: the sheet is a <Modal> and is never coached).
        requestGuideStep(GUIDE.n2b(), {
          onAccept: () => {
            setDnaOpenSource('guide');
            setDnaSheetOpen(true);
          },
        });
      }
      return;
    }
    // s3.1 → s3.2 (the pitch, CTAs in the bubble). Under guide_v2 the beat
    // waits for N1 to be seen or settled (§5.3): N1 owns the calibration
    // framing s3.2's ask depends on, and "or ineligible" is what keeps the
    // whole s3.2→s4.1→s5.x chain alive for redraft-only users (§5.4).
    if (guidedS3Pending && (!v2 || v2N1Settled)) {
      setGuidedS3Pending(false);
      requestGuideStep(
        GUIDE.s3_2(guidePromptPos, !!fitTargetPositions?.length),
        {
          // O-6 — the ranking process now opens on RankHome's guided entry
          // (N8 asks the import question there) instead of dropping the
          // user straight into QuickSetTiers.
          onAccept: () =>
            v2
              ? acceptGuidedRankEntry(guidePromptPos)
              : acceptQuicksetPrompt('prompt', guidePromptPos),
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
    // s2.2 (swipe coaching, ACTED ON) + s6.1 seen → S8 sign-off.
    // s2.2 is the precondition, not decoration: it is the tour's only
    // advance:'action' teaching beat, it is chained on s2.1 (⇒ firstRun ⇒
    // onboarding.trades_first), and guideSeen is durable. Without it a user
    // who saw nothing but the first-like celebration was told the tour was
    // over, having been taught one line — the P0-8 finding. The gate reads
    // product state, never a flag, so it is correct under both flag sets.
    //
    // Round-5 rewire: N6.1 REPLACES s6.1 as the first-like beat, so the
    // second conjunct reads `n6.1 || s6.1` or the tour permanently loses
    // its ending for every v2 user (the P0-8 failure shape). `guideSeen`
    // is written on all four of N6.1's exits AND on its matched-suppression
    // path, so this is true exactly when the first-like moment happened —
    // however it resolved. Unconditional: `guideSeen['n6.1']` can only be
    // written by v2 code paths, so with the flag off this is the v1
    // predicate verbatim.
    if (
      ob.guideSeen['s2.2'] &&
      (ob.guideSeen['n6.1'] || ob.guideSeen['s6.1']) &&
      !ob.guideSeen['s8.1'] &&
      !ob.guideTourCompleted
    ) {
      requestGuideStep(GUIDE.s8_1());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guideActive, guidedS3Pending, guidedS55Done, topCard, v2N1Armed, v2N2Armed, v2N1Settled]);

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
      // Guided arm: The Analyst delivers the pitch (s3.2, CTAs in the
      // bubble) instead of the inline prompt card. Same trigger, same
      // bookkeeping, same funnel event above.
      //
      // s3.1 is CUT (PRD §5.2 — the builder is gone from the script): its
      // content is absorbed by s3.2 and its "you and consensus disagree"
      // framing is N1's job now. Safe by construction: this
      // `setGuidedS3Pending(true)` was always unconditional and s3.2 chains
      // off it, never off `guideSeen['s3.1']`.
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

  // O-6 (PRD §5.3-A) — the guided entry to the ranking process. s3.2's CTA
  // lands on RankHome, where N8 asks the import question first, instead of
  // dropping the user straight into QuickSetTiers. `guidedEntry` is the
  // chain param RankHome reads to fire N8; the position is carried so the
  // Quick Set arm can still open on the position s3.2 named.
  function acceptGuidedRankEntry(position?: string) {
    track('quickset_prompt_accepted', { via: 'guide_rank_entry' }, 'Trades');
    navigation.navigate('Rank', {
      screen: 'RankHome',
      params: { guidedEntry: 'n8', ...(position ? { position } : {}) },
    });
  }

  // Consume the QuickSet→Trades handoff on focus: snapshot the old deck,
  // force a fresh job (server cache key doesn't see board changes), and
  // let the diff effect below count what's new.
  useFocusEffect(
    useCallback(() => {
      const marker = consumePendingQuicksetRegen();
      if (!marker || !leagueId) return;
      // R1's bus generalization: the marker is a position ONLY for the
      // Quick Set source; 'trios'/'import' returns carry the source name.
      const regenSource = consumeGuidedRegenSource() ?? 'quickset';
      const pos = regenSource === 'quickset' && isRegenPosition(marker) ? marker : null;
      flushPendingPassRef.current(); // regen rewinds the deck — commit first
      pendingRegenRef.current = {
        position: pos,
        jobId: null,
        prevPackages: new Set(deck.map(tradePackageKey)),
      };
      // The regen REPLACES this deck, it doesn't extend it. The append
      // effect de-dupes on trade_id and every newly GENERATED card carries a
      // fresh uuid, so without this clear the same packages land a second
      // time and the index rewind below drops the user onto a doubled deck.
      //
      // "Fresh uuid per card" is true of minting but does NOT make the ids
      // disjoint across this reset: `force: true` defeats the server's
      // complete-and-fresh cache branch but NOT its in-flight share, which
      // returns a still-`running` job verbatim (server.py, the
      // `existing.get("status") == "running"` return). So the old job can
      // refill this emptied deck with the very ids just dispositioned.
      // Clear the guard and drop the job for the same reason every other
      // deck-invalidating path does — see resetDeckForNewTargets below.
      deckEpochRef.current += 1;
      lastDispositionedRef.current = null; // regenerated decks can reuse ids
      setDeck([]);
      setDeckIdx(0);
      setJob(null); // stop the old job's poller refilling the deck we just cleared
      generateMutation.mutate(
        { force: true },
        {
          // Late-bind the reveal to the job this handoff forced. Without
          // it the deck clear above re-runs the diff effect on the commit
          // where `job` is still the PREVIOUS (already 'complete') job,
          // which would resolve the reveal against the wrong generation.
          onSuccess: (snapshot) => {
            if (pendingRegenRef.current) {
              pendingRegenRef.current.jobId = snapshot.job_id;
            }
          },
        },
      );
      // Item 8: first-Quick-Set-save celebration beat, then the Apple ask
      // for this save-moment class (win-then-ask; the diff banner that
      // follows is a passive receipt, not an ask).
      if (pos != null && guidedOn && !getOnboardingState().celebrationsShown.first_quickset_save) {
        setToast({
          msg: "That's your board now. The deck rebuilds around it.",
          tone: 'success',
        });
        patchOnboardingState({ celebrationsShown: { first_quickset_save: true } });
        track('celebration_shown', { beat: 'first_quickset_save' }, 'Trades');
      }
      // The save-moment Apple class belongs to Quick Set only — a trios or
      // import return must not burn it (consume-only-on-show, P0-9 class).
      if (pos != null) maybeAskApple('quickset_save');
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [deck, leagueId]),
  );

  // Diff banner (F2 — the aha receipt): once the forced job completes,
  // count packages that weren't in the pre-Quick-Set deck. Voice doc #9;
  // suppressed when nothing changed.
  //
  // S-43 — this reads `job.cards`, NOT `deck`. `deck` is written only from
  // inside the append effect above, so on the commit where the status flips
  // to 'complete' this effect's `deck` closure is still the render's
  // PRE-regeneration deck: the count came out 0 every time and the ref was
  // nulled before the new cards ever landed, which is why s5.1 had never
  // rendered. `job.cards` has no such lag — the worker publishes the final
  // card snapshot BEFORE flipping the status (server.py:5285-5291), and the
  // poll's shallow-equal guard always commits the status transition — so at
  // this point it IS the whole regenerated deck. It is also the same list
  // the append effect rebuilds `deck` from (cleared on the handoff), which
  // makes the two agree no matter how the cards streamed in: progressive
  // snapshots while 'running' are simply never read.
  useEffect(() => {
    const pending = pendingRegenRef.current;
    if (!pending || !pending.jobId) return;
    if (job?.job_id !== pending.jobId || job.status !== 'complete') return;
    pendingRegenRef.current = null;
    const fresh = job.cards.filter(
      (c) => !pending.prevPackages.has(tradePackageKey(c)),
    ).length;
    track(
      'deck_regenerated',
      pending.position != null
        ? { position: pending.position, new_trades: fresh }
        : { new_trades: fresh },
      'Trades',
    );
    if (guidedAvatarActive()) {
      // Guided arm: The Analyst delivers the reveal himself — celebrate on
      // new trades, honest oops on the null result (script S5.1/S5.0) —
      // then arms the S5.5 next-position ask via the chain effect.
      if (pending.position != null) {
        requestGuideStep(
          fresh > 0 ? GUIDE.s5_1(fresh, pending.position) : GUIDE.s5_0(pending.position),
        );
        setGuidedS55Done(pending.position);
      } else if (fresh > 0) {
        // Trios/import return: the positive reveal reads fine without a
        // position; the honest-null line (s5.0) is Quick-Set-worded, so a
        // null result stays silent here. TODO(guide-v2 phase 2): craft a
        // pos-less null line if trios/import null-reveals prove common.
        requestGuideStep(GUIDE.s5_1(fresh, undefined));
      }
      return;
    }
    if (fresh > 0 && pending.position != null) {
      setQuicksetDiffBanner({ position: pending.position, count: fresh });
      if (guidedOn && !getOnboardingState().coachMarksShown.diff_banner) {
        patchOnboardingState({ coachMarksShown: { diff_banner: true } });
        track('coach_mark_shown', { mark: 'diff_banner' }, 'Trades');
      }
    }
    // Deps are the job identity + its status: `deck` is no longer read, and
    // keeping it here would re-run this on every streamed card for nothing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.job_id, job?.status]);

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
    // F4 (deck.session_rerank): the session vector dies with the completed
    // deck (PRD §4) — completion is the one reset site the job/league
    // effect can't see (job_id doesn't change when the deck runs out).
    rerankEventsRef.current = [];
    lastRerankedRef.current = null;
    // F9 (deck.first_session): session-one completion — the user finished
    // their FIRST deck with ≥1 disposition this session (the PRD's
    // activation event, alongside ≥1 like). One-shot per deck session.
    if (
      firstSessionOn &&
      job?.first_deck &&
      !fsCompletionTrackedRef.current &&
      fsDispositionsRef.current > 0
    ) {
      fsCompletionTrackedRef.current = true;
      track(
        'first_session_deck_completed',
        {
          deck_size: deck.length,
          dispositions: fsDispositionsRef.current,
          liked: fsLikesRef.current.length,
        },
        'Trades',
      );
    }
    track('deck_exhausted_viewed', { deck_size: deck.length }, 'Trades');
    maybeShowQuicksetPrompt('like'); // swipes ≥3 path; pass-trigger n/a here
    // s7.1 (the trio ramp) is CUT (PRD §5.2, DELTA row A7 — the builder is
    // gone from the script): the step is deictic and its target
    // `trades.trio-entry` mounts only under `onboarding.rank_routing`,
    // which is false — and even with it on, the live `deck.replenishment`
    // summary card renders in place of that whole branch. It fired pointing
    // at nothing, every time. The exhausted-deck boundary belongs to the
    // summary card + N4 now (§5.3); Trios stay a pull surface.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deckExhausted]);

  // ── F10 (flag deck.replenishment): deck-done summary card ─────────────
  // Renders IN PLACE of the exhausted state when the user finished this
  // deck in this session (≥1 disposition tallied). Terminate on success:
  // no auto-regeneration, ever — "Done" returns to the hub (hub-launched
  // decks) or settles into the standalone exhausted state. Flag off ⇒
  // summaryVisible is always false and the exhausted state is untouched.
  const summaryVisible =
    replenishmentOn &&
    deckExhausted &&
    !summaryDismissed &&
    sessionTally.passed + sessionTally.liked > 0;
  const summaryTrackedRef = useRef(false);
  useEffect(() => {
    if (!summaryVisible) {
      summaryTrackedRef.current = false;
      return;
    }
    if (summaryTrackedRef.current) return;
    summaryTrackedRef.current = true;
    track('deck_summary_viewed', { ...sessionTally, deck_size: deck.length }, 'Trades');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summaryVisible]);

  // ── N4 — the empty deck (PRD §5.3) ───────────────────────────────────
  // Rides the shipped `trades.deck-summary` card as an added line + primary
  // action, never a competing card or an overlay bubble: one boundary, one
  // surface. Fails closed on all three owning flags (`deck.replenishment`
  // is inside `summaryVisible`, `trade.finder_targeting` is the pin board,
  // `trades.finder_hub` is what makes `finderMode` resolvable at all) and
  // on `!firstRun`, because the board the CTA hands off to is itself gated
  // on it — a taught control that cannot render is exactly the incoherence
  // the s7.1 cut exists to remove.
  const v2N4Retired = useOnboardingState(
    (s) => (s.ob.guideReceipts[GUIDE_RECEIPTS.finderTargetPinned] ?? 0) > 0,
  );
  const v2N4PinLine =
    guideV2Active() &&
    summaryVisible &&
    targetingEnabled &&
    finderHubOn &&
    !firstRun &&
    !v2N4Retired &&
    pinnedGive.length + pinnedReceive.length === 0;

  function handleSummaryPinTargets() {
    haptics.selection();
    // Attribution for the pin receipt below: this pin came from the guided
    // hand-off, not from someone browsing the board on their own.
    v2PinHandoffRef.current = true;
    switchFinderMode('player');
    mainScrollRef.current?.scrollTo({ y: 0, animated: true });
  }

  function handleSummaryDone() {
    haptics.selection();
    // #246 — the deck IS the landing now (the launcher hub is unrouted),
    // so "Done" settles into the regular exhausted state in every mode;
    // the pre-#246 finder-mode branch navigated back to the hub.
    setSummaryDismissed(true);
  }

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

  // P0-9 (PRD §5.2 `s6.2`): the once-per-class shot must be spent on a show
  // that actually happens. v1 consumed it here, BEFORE the 700 ms win-then-
  // ask delay, so an ask that never rendered still burned the class for
  // good — and under guide_v2 this call is deferred behind N6.1, which makes
  // that window much wider. Under the flag the consume moves inside the
  // timer; `applePendingRef` keeps two calls inside the same window from
  // stacking two sheets. Flag off = the shipped ordering, unchanged.
  const applePendingRef = useRef(false);
  function maybeAskApple(cls: 'like' | 'quickset_save') {
    if (!appleAskEligible(cls)) return;
    const v2 = guideV2Active();
    if (v2 && applePendingRef.current) return;
    const consume = () => {
      appleAskShownThisSession = true;
      patchOnboardingState(
        cls === 'like'
          ? { applePromptShownFor: { like: true } }
          : { applePromptShownFor: { quickset_save: true } },
      );
    };
    if (v2) applePendingRef.current = true;
    else consume();
    // Win-then-ask: the celebration toast lands before the modal.
    setTimeout(() => {
      if (v2) {
        applePendingRef.current = false;
        consume();
      }
      setAppleAsk(cls);
      track('apple_prompt_shown', { trigger: cls }, 'Trades');
    }, 700);
  }

  // ── N6.1 — first like → "Awaiting them" (PRD §5.3) ───────────────────
  // The s6.2 setup line + the Apple save-moment ask. Under guide_v2 this
  // chain no longer hangs off the like handler: N6.1 owns that moment, so
  // it fires from the beat's completion (all four exits, plus the paths
  // where the beat never renders) and re-checks `appleAskEligible` HERE, at
  // fire time — session and verification state can change in the interval.
  function v2RunLikeChain() {
    if (!getOnboardingState().guideSeen['s6.2'] && appleAskEligible('like')) {
      requestGuideStep(GUIDE.s6_2());
      setTimeout(() => maybeAskApple('like'), 2800);
    } else {
      maybeAskApple('like');
    }
  }

  function v2OnN61Complete(via: GuideCompletionVia) {
    // Only the CTA-navigation exit leaves this screen, so only it waits for
    // the next TradesScreen focus; `Later`, the ✕, the swipe-away and the
    // timeout all stay here, where a focus hook would never fire and would
    // starve the chain outright.
    if (via === 'cta' && v2N61NavigatedRef.current) {
      v2N61NavigatedRef.current = false;
      v2LikeChainOnFocusRef.current = true;
      return;
    }
    v2RunLikeChain();
  }

  function v2ShowN61(hasAwaiting: boolean) {
    const shown = hasAwaiting
      ? requestGuideStep(GUIDE.n6_1(true), {
          onAccept: () => {
            v2N61NavigatedRef.current = true;
            navigation.navigate('Matches', {
              segment: 'awaiting',
              at: Date.now(),
              // The guided-chain param: MatchesScreen reads it to suppress
              // N9 (that arrival already teaches) and, from Phase 2, to
              // mount N6.2 on the row this chain carried.
              guidedArrival: 'n6.1',
            });
          },
          onComplete: v2OnN61Complete,
        })
      : requestGuideStep(GUIDE.n6_1(false), { onComplete: v2OnN61Complete });
    if (shown) {
      // Consume the first-like moment only on a beat that actually
      // rendered, and keep the v1 celebration series continuous — N6.1 is
      // the same moment s6.1 owned, so the funnel does not step at the
      // flag flip.
      patchOnboardingState({ celebrationsShown: { first_like: true } });
      track('celebration_shown', { beat: 'first_like' }, 'Trades');
      return;
    }
    // Refused (slot busy, retired, invalidated…). Release the claim so a
    // later like can still take the moment — consuming it on a beat that
    // never rendered is the P0-9 shape — and give this like the shipped
    // receipt plus the chain the beat would have owned.
    v2FirstLikeClaimedRef.current = false;
    setToast({ msg: 'Liked', tone: 'success' });
    v2RunLikeChain();
  }

  // Called from swipeMutation.onSuccess for every like under guide_v2.
  function v2OnLikeSwipeSuccess(res: any) {
    if (!guideV2Active() || !guidedAvatarActive()) return;
    if (v2FirstLikeClaimedRef.current) return;
    const ob = getOnboardingState();
    if (
      ob.celebrationsShown.first_like ||
      ob.guideSeen['n6.1'] ||
      ob.guideRetired['n6.1']
    ) {
      return;
    }
    v2FirstLikeClaimedRef.current = true;
    // The like matured into a mutual match on the way in: there is no
    // "awaiting" row to route to and the copy would be false. Consume the
    // moment — `guideSeen['n6.1']` + retired + a measured suppression, no
    // `guide_step_shown` — so s8.1's rewired predicate still becomes true
    // for instant-matchers, and run the chain the beat would have owned.
    if (res?.matched === true) {
      markGuideStepConsumed('n6.1', 'matched');
      v2RunLikeChain();
      return;
    }
    // Otherwise ask the awaiting list whether there is anything to route
    // to, and pick the variant BEFORE requesting — the bubble's copy is
    // chosen once and never swaps after render. Empty, failed and slow all
    // take the router-less line rather than route the user one tap into
    // "No pending trades" at the most trust-critical moment of the tour.
    let settled = false;
    const decide = (hasAwaiting: boolean) => {
      if (settled) return;
      settled = true;
      v2ShowN61(hasAwaiting);
    };
    setTimeout(() => decide(false), N61_AWAITING_TIMEOUT_MS);
    queryClient
      .fetchQuery({ queryKey: ['awaiting-trades'], queryFn: getAwaitingTrades })
      .then((rows) => decide(Array.isArray(rows) && rows.length > 0))
      .catch(() => decide(false));
  }

  // The deferred chain's CTA exit: it ran only because we navigated away,
  // so it lands on the next focus of this screen.
  useFocusEffect(
    useCallback(() => {
      if (!v2LikeChainOnFocusRef.current) return;
      v2LikeChainOnFocusRef.current = false;
      v2RunLikeChain();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []),
  );

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
    // S7 PRD-01 (growth.share_landing): when the like completed a mutual
    // match, share the backend's /s/trade/<match_id> landing page (rich OG
    // card in iMessage/Discord) with ?ref= attribution.
    //
    // audit P1-2 / PR-11: liked-but-unmatched trades DO have a server
    // object available — POST /api/share/package (backend/server.py:16999)
    // mints one for an arbitrary give/receive build and /s/p/<short_id>
    // (backend/server.py:17048) renders it. The comment that used to sit
    // here said no /s/ route existed for them; it predated the route and
    // was never revisited, and this is the more common of the two share
    // paths. resolveShareUrl degrades to the ?ref= root when the mint
    // can't be made. Flag off: the legacy bare-root message, byte for byte.
    const rawId = c.trade_id.endsWith(EDITED_SUFFIX)
      ? c.trade_id.slice(0, -EDITED_SUFFIX.length)
      : c.trade_id;
    const matchId = matchIdByTradeRef.current.get(rawId);
    const ref = user?.username ? `ref=${encodeURIComponent(user.username)}` : '';
    let landing = false;
    let url: string;
    if (!shareLandingOn) {
      url = 'https://fantasy-trade-finder.onrender.com';
    } else if (matchId) {
      url = `${getBaseUrl()}/s/trade/${matchId}${ref ? `?${ref}` : ''}`;
      landing = true;
    } else {
      const resolved = await resolveShareUrl({
        giveIds: c.give_player_ids,
        receiveIds: c.receive_player_ids,
        username: user?.username,
        enabled: shareLandingOn,
        isDemo,
        surface: 'trades_liked',
        hasPickAssets:
          c.give_players.some(isPickAsset) || c.receive_players.some(isPickAsset),
        onOutcome: (outcome, give_n, receive_n) =>
          track(
            'share_package_created',
            { surface: 'trades_liked', give_n, receive_n, outcome },
            'Trades',
          ),
      });
      url = resolved.url;
      landing = resolved.rung === 'package';
    }
    try {
      const res = await Share.share({
        message:
          `Trade idea for our league: I send ${give}, get ${recv} from ` +
          `@${c.opponent_username}. Found on Fantasy Trade Finder — ` +
          url,
      });
      if (res.action !== Share.dismissedAction) {
        // `landing` widens from "a /s/trade/ landing was used" to "the
        // artifact carried a rich landing (/s/trade/ OR /s/p/)". Safe to
        // redefine silently: the prop has been stripped at ingest since it
        // shipped (it is not in trade_card_shared's CLIENT_EVENT_PROPS
        // row), so no row has ever carried it.
        track(
          'trade_card_shared',
          shareLandingOn
            ? { trade_id: c.trade_id, landing }
            : { trade_id: c.trade_id },
          'Trades',
        );
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
    const ownerId = swapTarget.side === 'give' ? myOwner : topCard.opponent_user_id;
    const rosterIds = rosterByOwner.get(ownerId) ?? [];
    const inTrade = new Set([
      ...topCard.give_player_ids,
      ...topCard.receive_player_ids,
    ]);
    return rosterIds
      .filter((id) => !inTrade.has(id))
      .map((id) => valueById.get(id))
      .filter((r): r is CalcValueRow => !!r);
  }, [swapTarget, topCard, rosterByOwner, valueById, myOwner]);

  // Shared tail for every top-card package edit — swap (#86), swap-
  // suggestion pick (2026-07-27), asset removal (#194): overlay the edited
  // card (engine numbers cleared) keyed by the ORIGINAL trade id, then
  // re-price via Mode B.
  function applyPackageEdit(give: Player[], receive: Player[]) {
    if (!rawTopCard || !topCard) return;
    const rawId = rawTopCard.trade_id;
    const editedCard: TradeCard = {
      ...topCard,
      trade_id: `${rawId}${EDITED_SUFFIX}`,
      give_players: give,
      receive_players: receive,
      give_player_ids: give.map((p) => p.id),
      receive_player_ids: receive.map((p) => p.id),
      edited: true,
      // The engine's numbers described the ORIGINAL package. Clear them —
      // the value bar hides while give/receive are undefined and the
      // re-price below fills them back in; reasons/sweetener narrated the old
      // package; the counterparty's like was for the original mirror, not
      // this variant.
      fairness: undefined as unknown as number,
      give_value: undefined,
      receive_value: undefined,
      favors: undefined,
      gap: undefined,
      reasons: undefined,
      sweetener: undefined,
      likesYou: false,
    };
    setEdits((prev) => ({ ...prev, [rawId]: editedCard }));
    haptics.selection();
    // Mode B needs a real counterparty id; without one the card just shows
    // EDITED with no fairness read (shouldn't happen on generated cards).
    if (editedCard.opponent_user_id) {
      repriceMutation.mutate({ rawId, card: editedCard });
    }
  }

  function handleSwapPick(replacement: CalcValueRow) {
    if (!swapTarget || !rawTopCard || !topCard) return;
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
    setSwapTarget(null);
    applyPackageEdit(
      side === 'give' ? swapIn(topCard.give_players) : topCard.give_players,
      side === 'receive' ? swapIn(topCard.receive_players) : topCard.receive_players,
    );
  }

  // Swap-suggestion pick (2026-07-27 player-changer): replace the target
  // asset with the chosen evener — both pieces for a 2-piece package.
  // Player pieces resolve names/positions from the consensus values pool;
  // a piece the pool doesn't price is an owned pick — name from the row
  // (package rows carry "A + B" in ids order), shape mirroring the
  // backend's pick pseudo-players (position/team 'PICK'). The re-price
  // resolves owned pick ids via the card's league_id (#158).
  function handleSuggestPick(evener: CalcEvener) {
    if (!suggestTarget || !topCard) return;
    const { player: outgoing, side } = suggestTarget;
    const pieceIds = evener.is_package && evener.ids ? evener.ids : [evener.id];
    const pieceNames = evener.is_package ? evener.name.split(' + ') : [evener.name];
    const incoming: Player[] = pieceIds.map((id, i) => {
      const row = valueById.get(id);
      if (row) {
        return {
          id,
          name: row.name,
          position: row.position,
          team: row.team,
          age: row.age,
        };
      }
      const pos = evener.is_package ? 'PICK' : evener.position;
      return {
        id,
        name: pieceNames[i] ?? evener.name,
        position: pos,
        team: pos === 'PICK' ? 'PICK' : null,
      };
    });
    const replaceIn = (arr: Player[]) =>
      arr.flatMap((p) => (p.id === outgoing.id ? incoming : [p]));
    track(
      'trade_swap_suggestion_picked',
      {
        side,
        asset_kind: evener.is_package ? 'package' : evener.is_pick ? 'pick' : 'player',
      },
      'Trades',
    );
    setSuggestTarget(null);
    applyPackageEdit(
      side === 'give' ? replaceIn(topCard.give_players) : topCard.give_players,
      side === 'receive' ? replaceIn(topCard.receive_players) : topCard.receive_players,
    );
  }

  function openSwapSuggestions(player: Player, side: 'give' | 'receive') {
    // F1 (deck.signal_v2): suggestion sheet = detail engagement.
    if (signalV2On) engagementRef.current.detailExpanded = true;
    track('trade_swap_suggest_opened', { side }, 'Trades');
    setSuggestTarget({ player, side });
  }

  // #194 — remove an asset from the top card (either side). At least one
  // asset must remain per side (honest hint instead of a silent no-op);
  // removing a PINNED give asset while "Trade as one package" (#174) is on
  // gets a small confirm — it breaks the whole-package request for this
  // card (the pins themselves stay set for future decks).
  function handleRemoveAsset(player: Player, side: 'give' | 'receive') {
    if (!rawTopCard || !topCard) return;
    const sidePlayers =
      side === 'give' ? topCard.give_players : topCard.receive_players;
    if (sidePlayers.length <= 1) {
      setToast({
        msg: 'A trade needs at least one asset on each side.',
        tone: 'warn',
      });
      return;
    }
    const doRemove = () => {
      track('trade_asset_removed', { side }, 'Trades');
      applyPackageEdit(
        side === 'give'
          ? topCard.give_players.filter((p) => p.id !== player.id)
          : topCard.give_players,
        side === 'receive'
          ? topCard.receive_players.filter((p) => p.id !== player.id)
          : topCard.receive_players,
      );
    };
    if (
      side === 'give' &&
      packageMode &&
      pinnedGive.some((p) => p.id === player.id)
    ) {
      Alert.alert(
        'Break up the package?',
        `You asked for ideas that send all your pinned players together. ` +
          `Removing ${player.name} breaks that package on this card — your ` +
          `pins stay set for the next deck.`,
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Remove', style: 'destructive', onPress: doRemove },
        ],
      );
      return;
    }
    doRemove();
  }

  // ── `swipe_guard_blocked` (B4 / D-068 follow-up) ──────────────────────
  // Tracking plan: docs/business/analytics/2026-08-18-swipe-guard-blocked.md.
  //
  // Both of advance()'s early-return double-fire guards report here. Until
  // this existed a poisoned guard swallowed every ✕/✓/swipe on a card and
  // produced NO telemetry of any kind — the B4 user tapped through a
  // permanent stall and generated zero events, so a human report was the
  // only detector. Emission never changes control flow: track() is no-throw
  // fire-and-forget and the caller returns exactly as it did before.
  //
  // `guard` is the discriminator (one event name, two guards); `decision` is
  // what the user was reaching for, which is the difference between a
  // double-tapped ✕ and a user hunting for an escape. The CONTROL (button vs
  // gesture vs VoiceOver) is deliberately not a prop — all three funnel
  // through one onLike/onPass pair before advance() sees them, so the
  // emitter cannot honestly tell them apart. NO `platform` prop: device
  // platform is a user_events COLUMN derived server-side (the NULL-platform
  // incident); the decline-reason family's prop is a specced exception this
  // event does not inherit.
  function reportGuardBlocked(
    guard: 'swipe_undo' | 'decline_reasons',
    decision: 'like' | 'pass',
    rawId: string,
  ) {
    const st = guardBlockRef.current;
    const key = `${guard}:${rawId}`;
    // A different card or a different guard is a different predicament.
    if (st.key !== key) {
      st.key = key;
      st.n = 0;
    }
    st.n += 1;
    if (!GUARD_BLOCK_LADDER.includes(st.n)) return;
    if (st.sessionEmitted >= GUARD_BLOCK_SESSION_CAP) return;
    st.sessionEmitted += 1;
    track(
      'swipe_guard_blocked',
      {
        guard,
        decision,
        trade_id: rawId,
        // The SERVE, not the card: a re-fronted card is a fresh predicament
        // on the same trade_id. Literal 'none' (reasonEventProps()'s
        // convention) so a missing serve is not a stripped prop.
        impression_id: rawTopCard?.impression_id ?? 'none',
        blocked_n: st.n,
        ms_since_render: Math.max(0, Date.now() - cardRenderedAtRef.current),
      },
      'Trades',
    );
  }

  function advance(
    decision: 'like' | 'pass',
    // Decline-reason capture (SPEC §3): the layer-1 tile tap IS the pass, but
    // layer 2 has to answer on the SAME card, so the disposition commits here
    // while the deck advance waits for `commitReasonAdvance()`. Nothing else
    // in this function changes.
    opts?: { deferDeckAdvance?: boolean },
  ) {
    if (!topCard) return;
    // S3 PRD-03 (ux.swipe_undo) — double-fire guard: the gesture's
    // animation-end callback and the disposition buttons can both fire for
    // the same top card; no-op the repeat on the RAW deck id.
    const dispatchRawId = rawTopCard?.trade_id ?? topCard.trade_id;
    // Decline reasons: once a card's pass is banked, the ✓, the swipe gesture
    // and the VoiceOver actions are all inert on it — layer 2 owns the
    // advance. Ref, not state: the layer-1 tap and a fast second gesture can
    // land in the same React batch.
    if (
      declineReasonsOn &&
      !opts?.deferDeckAdvance &&
      reasonBankedIdRef.current === dispatchRawId
    ) {
      reportGuardBlocked('decline_reasons', decision, dispatchRawId);
      return;
    }
    if (swipeUndoOn) {
      if (lastDispositionedRef.current === dispatchRawId) {
        reportGuardBlocked('swipe_undo', decision, dispatchRawId);
        return;
      }
      lastDispositionedRef.current = dispatchRawId;
      // A newer disposition always commits the previous pending pass first
      // (at most one undoable action in flight; ordering preserved).
      flushPendingPass();
    }
    // Past both guards: the disposition got through, so whatever streak of
    // blocks preceded it is over. Keeps `blocked_n` a count of CONSECUTIVE
    // blocks on one predicament rather than a session tally.
    guardBlockRef.current.key = null;
    // N6.1's lifetime bound (PRD §5.3): the bubble auto-dismisses on the
    // next swipe as well as after 8 s, so a cta step can never hold the
    // interrupt slot across further swipes and starve the push primer or
    // the Apple ask. Its `onComplete('swipe')` runs the deferred s6.2 +
    // Apple chain, so when THIS swipe is the dismissing one the inline
    // chain below is skipped — ownership is declared, not left to timing.
    let n61DismissedByThisSwipe = false;
    if (guideV2Active() && guideActiveStepId() === 'n6.1') {
      n61DismissedByThisSwipe = true;
      dismissActiveGuideStep('swipe');
    }
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
    // s2.3 is REPLACED by N1 (PRD §5.2): both pointed at
    // `trades.provenance-chip`, so keeping s2.3 would teach the same target
    // twice, the first time with the framing N1 exists to correct. Its
    // request site is gone; the script's builder is deprecated for deletion
    // alongside it.
    if (guidedAvatarActive()) {
      advanceGuideIfActive('s2.2');
      // Flag-off (v1) arm keeps the s2.3 provenance beat so the rollback
      // lever restores the shipped tour; the v2 arm replaces it with N1 at
      // the third disposition (PRD §5.2 REPLACE row).
      if (!guideV2Active()) {
        const seenV1 = getOnboardingState().guideSeen;
        if (seenV1['s2.2'] && !seenV1['s2.3']) requestGuideStep(GUIDE.s2_3());
      }
    }
    // ── v2 trigger accumulators (N1, N2) ────────────────────────────────
    if (guideV2Active() && guidedAvatarActive()) {
      v2SessionDispositionsRef.current += 1;
      if (decision === 'pass') {
        v2ConsecutivePassesRef.current += 1;
      } else {
        v2ConsecutivePassesRef.current = 0;
        v2SessionHadLikeRef.current = true;
      }
      const obv = getOnboardingState();
      // N1 — third disposition of the FIRST session (a post-success
      // boundary, never idle time). Suppressed for redraft leagues, where
      // "your swipes are teaching me your prices" has no dynasty board to
      // teach, and for anyone who already has a Quick-Set board.
      if (
        v2SessionDispositionsRef.current === 3 &&
        !isRedraftLeague &&
        obv.sessionCount <= 1 &&
        obv.quicksetCompletedPositions.length === 0
      ) {
        setV2N1Armed(true);
      }
      // N2 — the failure family: three consecutive passes, no like this
      // session, no DECLARED outlook, and all three owning flags on
      // (`consolidateOn` IS `edit_full_sheet && finder_hub`-in-a-mode —
      // without it the outlook entry points route to the legacy sheet and
      // the adoption receipt never renders). All fail closed.
      if (
        v2ConsecutivePassesRef.current >= 3 &&
        !v2SessionHadLikeRef.current &&
        outlookDirectionOn &&
        consolidateOn &&
        !v2OutlookDeclared
      ) {
        v2ConsecutivePassesRef.current = 0;
        setV2N2Armed(true);
      }
    }
    // Guided layer: any disposition (swipe or button) retires an active
    // swipe hint — the card it pointed at is leaving.
    if (swipeHintActive) dismissSwipeHint();
    // F1 (deck.signal_v2): freeze dwell/engagement at disposition time —
    // undefined when the flag is off or the card has no impression_id.
    const dispatchSignal = signalForCard(rawTopCard);
    // F4 (deck.session_rerank): fold this disposition into the session
    // vector and re-rank the remaining cards (positions ≥ current+2 only).
    // Attributes come from the card the user actually acted on (topCard —
    // the edited variant after a swap); identity is the raw deck id. Dwell
    // is read here, before the top-card-change effect resets the timer. A
    // bad-trade flag (#85) routes through advance('pass') with the ref set
    // and earns the strong `not_interested` reward instead.
    if (rerankOn) {
      const rerankDisposition: RerankDisposition =
        nextDispositionNotInterestedRef.current ? 'not_interested' : decision;
      nextDispositionNotInterestedRef.current = false;
      applySessionRerank(topCard, dispatchRawId, rerankDisposition, currentDwellMs());
    }
    // F9 (deck.first_session): first-deck activation tallies + the
    // adaptation moment. Only on the server-marked FIRST deck for this
    // league; flag off or any prior deck ⇒ this block never runs.
    if (firstSessionOn && job?.first_deck) {
      fsDispositionsRef.current += 1;
      if (decision === 'like') {
        fsLikesRef.current.push({
          attrs: extractCardAttributes(topCard),
          opponentUsername: topCard.opponent_username,
          opponentUserId: topCard.opponent_user_id,
        });
        if (!fsFirstLikeTrackedRef.current) {
          fsFirstLikeTrackedRef.current = true;
          // position = 1-based disposition ordinal of the session's first
          // like (the PRD's first_session_like_position metric).
          track(
            'first_session_like',
            {
              position: fsDispositionsRef.current,
              trade_id: dispatchRawId,
              ...(dispatchSignal?.impression_id
                ? { impression_id: dispatchSignal.impression_id }
                : {}),
            },
            'Trades',
          );
        }
      }
      // Adaptation moment — trigger conditions ARE the card's claims (PRD:
      // never claim adaptation that didn't happen): ≥5 dispositions, ≥3
      // likes sharing a phraseable dominant attribute, AND ≥1 unseen card
      // ahead carrying it. Variant: 'rerank' only when deck.session_rerank
      // is also on (the deck literally re-ranks toward the liked
      // attribute); otherwise the honest descriptive copy.
      if (
        !adaptationMomentShownThisSession &&
        fsDispositionsRef.current >= FIRST_SESSION_MIN_DISPOSITIONS &&
        fsLikesRef.current.length >= FIRST_SESSION_MIN_SHARED_LIKES
      ) {
        const signal = findDominantLikedAttribute(fsLikesRef.current);
        if (signal) {
          const ahead = sortedDeckRef.current
            .slice(deckIdx + 1)
            .some((c) => cardMatchesAttribute(c, signal.attribute));
          if (ahead) {
            adaptationMomentShownThisSession = true;
            // 'rerank' only when the F4 re-rank is actually operating on
            // this display order (flag on AND deck order is the display
            // order — applySessionRerank skips reorders under a lane
            // filter or the fairness-off client sort). Otherwise the
            // descriptive variant, whose only claim is the remaining
            // cards (verified above).
            const variant =
              rerankOn && fairnessOn && !laneFilter
                ? ('rerank' as const)
                : ('descriptive' as const);
            setAdaptationMoment({ ...signal, variant });
            track(
              'first_session_adaptation_shown',
              { variant, attribute: signal.attribute, likes: signal.likes },
              'Trades',
            );
          }
        }
      }
    }
    // Decline reasons suppress the undo window: the tile tap is a deliberate,
    // reasoned gesture (like the bad-trade flag), and an "Undo" toast under a
    // live layer-2 panel would offer to rewind a deck that has not moved yet.
    if (swipeUndoOn && decision === 'pass' && !declineReasonsOn) {
      // Hold the POST for the undo window (design note at pendingPassRef).
      const card = topCard;
      pendingPassRef.current = {
        card,
        rawId: dispatchRawId,
        timer: setTimeout(() => flushPendingPassRef.current(), UNDO_HOLD_MS),
        signal: dispatchSignal,
      };
    } else {
      swipeMutation.mutate({ card: topCard, decision, signal: dispatchSignal });
    }
    // F10 (deck.replenishment): session tally for the deck-done summary.
    if (replenishmentOn) {
      setSessionTally((t) =>
        decision === 'like'
          ? { ...t, liked: t.liked + 1 }
          : { ...t, passed: t.passed + 1 },
      );
    }
    // Decline reasons: the card must stay put so layer 2 can open beneath its
    // own tiles. `commitReasonAdvance()` does this line (and only this line)
    // once layer 2 answers — the next trade IS the confirmation (SPEC §1).
    if (!opts?.deferDeckAdvance) setDeckIdx((i) => i + 1);
    if (decision === 'like') {
      haptics.success();
      // Item 8: remember the liked card for the share affordance, fire the
      // first-like celebration beat (guided layer), then the Apple ask —
      // win-then-ask ordering, never two overlapping surfaces.
      setLastLikedCard(topCard);
      const firstLike = !getOnboardingState().celebrationsShown.first_like;
      if (guidedAvatarActive() && guideV2Active()) {
        // N6.1 (PRD §5.3) owns the first-like moment, and whether THIS like
        // is the first is decided in `swipeMutation.onSuccess` — a like-time
        // read lets two rapid likes both see first-like true, and the
        // empty-awaiting gate needs a response that a like-time prefetch
        // would race. So a like that is still a candidate fires nothing
        // here; the router (or its router-less variant) and the deferred
        // s6.2 + Apple chain both hang off that response.
        //
        // A like that is definitively NOT the first keeps today's inline
        // chain — except the one that just swipe-dismissed a live n6.1
        // bubble, whose chain that step's `onComplete` owns.
        if (!firstLike && !n61DismissedByThisSwipe) {
          setToast({ msg: 'Liked', tone: 'success' });
          v2RunLikeChain();
        }
      } else if (guidedAvatarActive()) {
        // Guided arm: s6.1 celebrate replaces the toast; the honest Apple
        // setup line (s6.2) precedes the system sheet, which opens after
        // the auto-step clears (never two overlapping surfaces).
        //
        // REQUEST FIRST, CONSUME ON SUCCESS (P0-9 D1). When the like is the
        // user's FIRST disposition, s2.3 was requested ~115 lines above and
        // owns the bubble slot, so requestStep refuses (useGuide.ts:93-94).
        // Marking the celebration spent before knowing that lost the beat
        // permanently: firstLike went false, s6.1 was never requested again,
        // guideSeen['s6.1'] was never written, and the tour had no ending.
        // The && short-circuits, so a non-first like still never requests.
        const shown = firstLike && requestGuideStep(GUIDE.s6_1());
        if (shown) {
          patchOnboardingState({ celebrationsShown: { first_like: true } });
          track('celebration_shown', { beat: 'first_like' }, 'Trades');
        } else {
          setToast({ msg: 'Liked', tone: 'success' });
        }
        if (!getOnboardingState().guideSeen['s6.2'] && appleAskEligible('like')) {
          setTimeout(() => {
            requestGuideStep(GUIDE.s6_2());
            setTimeout(() => maybeAskApple('like'), 2800);
          }, shown ? 2400 : 0);
        } else {
          maybeAskApple('like');
        }
      } else {
        let likeToast = 'Liked';
        if (guidedOn && firstLike) {
          likeToast = 'First target logged. Your front office is open for business.';
          patchOnboardingState({ celebrationsShown: { first_like: true } });
          track('celebration_shown', { beat: 'first_like' }, 'Trades');
        }
        setToast({ msg: likeToast, tone: 'success' });
        maybeAskApple('like');
      }
    } else {
      haptics.swipe();
      if (swipeUndoOn) {
        // "Passed — Undo": the toast's hold matches the pending-POST
        // window, so the affordance and the commit expire together.
        setToast({
          msg: 'Passed',
          tone: 'success',
          holdMs: UNDO_HOLD_MS,
          action: { label: 'Undo', onPress: undoPass },
        });
      }
    }
  }

  // ── Decline-reason capture (flag `feedback.decline_reasons`) ───────────
  // SPEC docs/plans/decline-reason-capture/SPEC.md; prototype
  // mockups/decline-reason-capture/07-two-step-diagnostic.html.
  //
  // PROGRESSIVE WRITES (SPEC §3). Three commit moments, each firing on its
  // own tap — nothing waits for a submit:
  //   layer-1 tile  → the pass disposition (the unchanged swipe POST) AND
  //                   the reason row. A tester who stops here leaves a
  //                   complete record; that is why the ✕ is gone.
  //   layer-2 option→ the detail, then the deck advances.
  //   "Other"       → the code banks BEFORE the box opens; the send upgrades
  //                   the same row with the free text and advances.
  // Free text is stored on the row and NEVER sent as an analytics property.
  // The per-card reset lives with the other fronted-card effects above.

  // Shared analytics props (SPEC §6). `platform` is set explicitly at the
  // emitter, never inferred — the NULL-platform incident is why.
  function reasonEventProps() {
    return {
      impression_id: rawTopCard?.impression_id ?? 'none',
      trade_id: rawTopCard?.trade_id ?? topCard?.trade_id ?? '',
      ms_since_render: Math.max(0, Date.now() - cardRenderedAtRef.current),
      platform:
        Platform.OS === 'android' ? 'android' : Platform.OS === 'web' ? 'web' : 'ios',
    };
  }

  function reasonWriteTarget() {
    return {
      impressionId: rawTopCard?.impression_id,
      tradeId: rawTopCard?.trade_id ?? topCard?.trade_id ?? '',
      leagueId: topCard?.league_id || undefined,
    };
  }

  // The deferred half of the pass: layer 2 answered, so front the next card.
  // No receipt, no toast — the next trade is the confirmation (SPEC §1).
  function commitReasonAdvance() {
    reasonBankedIdRef.current = null;
    setReasonBankedId(null);
    setDeckIdx((i) => i + 1);
  }

  function handleReasonLayer1(reason: Layer1Code, switchedFrom: Layer1Code | 'none') {
    if (!topCard) return;
    const rawId = rawTopCard?.trade_id ?? topCard.trade_id;
    const firstForThisCard = reasonBankedIdRef.current !== rawId;
    track(
      'trade_pass_layer1',
      { reason, switched_from: switchedFrom, ...reasonEventProps() },
      'Trades',
    );
    void postDeclineReason({ ...reasonWriteTarget(), layer: 1, reason, switchedFrom });
    // A tile switch refines the existing answer; only the FIRST tile tap on a
    // card carries the disposition.
    if (!firstForThisCard) return;
    reasonBankedIdRef.current = rawId;
    setReasonBankedId(rawId);
    advance('pass', { deferDeckAdvance: true });
  }

  function handleReasonLayer2Select(reason: Layer1Code, detail: Layer2Code) {
    track(
      'trade_pass_layer2',
      { reason, detail, has_free_text: false, ...reasonEventProps() },
      'Trades',
    );
    void postDeclineReason({ ...reasonWriteTarget(), layer: 2, reason, detail });
    commitReasonAdvance();
  }

  // "Other" tapped: bank the code so a tester who opens the box and bails
  // still leaves "none of the listed reasons" (SPEC §3.3). No analytics event
  // here — `trade_pass_layer2` fires at the two moments that ADVANCE (a fixed
  // option tap, or the free-text send), so the funnel never double-counts.
  function handleReasonLayer2Bank(reason: Layer1Code, detail: Layer2Code) {
    void postDeclineReason({ ...reasonWriteTarget(), layer: 2, reason, detail });
  }

  function handleReasonLayer2Send(
    reason: Layer1Code,
    detail: Layer2Code,
    freeText: string,
  ) {
    track(
      'trade_pass_layer2',
      {
        reason,
        detail,
        // The text itself is stored on the row only; the event carries the
        // BOOLEAN and nothing else (SPEC §3.4).
        has_free_text: freeText.length > 0,
        ...reasonEventProps(),
      },
      'Trades',
    );
    void postDeclineReason({
      ...reasonWriteTarget(),
      layer: 2,
      reason,
      detail,
      freeText: freeText || undefined,
    });
    Keyboard.dismiss();
    commitReasonAdvance();
  }

  // The composer's send button opens BELOW the text box, so focusing the
  // input is not enough. The panel measures the button against the keyboard's
  // top edge and asks for exactly the overlap; the ScrollView already carries
  // `keyboardShouldPersistTaps="handled"` (so the first tap lands) and gains
  // `automaticallyAdjustKeyboardInsets` while this flag is on (so the extra
  // scroll range exists at all).
  function handleReasonReveal(dy: number) {
    mainScrollRef.current?.scrollTo({
      y: mainScrollYRef.current + dy,
      animated: true,
    });
  }

  const declineReasonProps: DeclineReasonPanelProps | undefined = declineReasonsOn
    ? {
        onLayer1: handleReasonLayer1,
        onLayer2Select: handleReasonLayer2Select,
        onLayer2Bank: handleReasonLayer2Bank,
        onLayer2Send: handleReasonLayer2Send,
        onRevealRequest: handleReasonReveal,
      }
    : undefined;

  // Bad-trade flag (feedback #85): file the engine-quality flag, then move
  // past the card exactly like a pass — flagging implies "not interested",
  // so the pass swipe records the disposition while the flag row records
  // "the engine got this one wrong" for operator review.
  function handleFlagBadTrade() {
    if (!topCard) return;
    // No reason field in the mobile flag flow (flagBadTrade's `reason`
    // param is unused here), so the event carries the trade id only.
    track('trade_flagged', { trade_id: topCard.trade_id }, 'Trades');
    flagMutation.mutate({
      card: topCard,
      impressionId: signalV2On ? rawTopCard?.impression_id : undefined,
    });
    // F4 (deck.session_rerank): a bad-trade flag is the explicit "not
    // interested" — advance('pass') reads this ref for the −2 reward. The
    // trailing clear covers advance() no-oping on its double-fire guard,
    // so the marker can never leak onto a later card's disposition.
    if (rerankOn) nextDispositionNotInterestedRef.current = true;
    advance('pass');
    nextDispositionNotInterestedRef.current = false;
    // Flagging is deliberate — commit the pass immediately (no undo window;
    // the flag toast below replaces the pass-undo toast anyway).
    if (swipeUndoOn) flushPendingPass();
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

  // S3 PRD-02 — per-surface commands for the shared player context menu.
  // The menu header carries the player-info disclosure; commands below are
  // whichever of untouchable/swap apply to the held row.
  function menuActionsFor(target: {
    player: Player;
    side: 'give' | 'receive';
  }): PlayerMenuAction[] {
    const { player, side } = target;
    const actions: PlayerMenuAction[] = [];
    if (side === 'give' && untouchablesEnabled && leagueId) {
      const marked = untouchableIds?.has(player.id) ?? false;
      actions.push({
        key: marked ? 'untouchable-remove' : 'untouchable-add',
        label: marked ? 'Remove untouchable' : 'Mark untouchable',
        hint: marked
          ? 'Allow this player in trade ideas again'
          : 'Never offered from your roster in trade ideas',
        onPress: () => {
          setMenuTarget(null);
          handleToggleUntouchable(player);
        },
      });
    }
    // 2026-07-27 player-changer: server-priced replacement candidates for
    // this asset (the calculator's counter-suggestion eveners, served per
    // deck-card asset). Needs a real counterparty for the Mode B read —
    // generated cards always carry one.
    if (topCard?.opponent_user_id) {
      actions.push({
        key: 'swap-suggest',
        testID: `trade-card.swap-suggest.${player.id}`,
        label: 'Swap suggestions',
        hint: 'Replacements priced to keep this trade balanced',
        onPress: () => {
          setMenuTarget(null);
          openSwapSuggestions(player, side);
        },
      });
    }
    actions.push({
      key: 'swap',
      label: 'Swap player',
      hint:
        side === 'give'
          ? 'Replace with someone from your roster'
          : 'Replace with someone from their roster',
      onPress: () => {
        setMenuTarget(null);
        setSwapTarget({ player, side });
      },
    });
    // #194 — the on-card ✕ is the primary affordance; this row keeps the
    // command in the shared long-press vocabulary alongside swap.
    actions.push({
      key: 'remove-asset',
      label: 'Remove from trade',
      hint: 'Drop this asset and re-price the rest',
      onPress: () => {
        setMenuTarget(null);
        handleRemoveAsset(player, side);
      },
    });
    return actions;
  }

  // #298 — the Upgrade / Lateral / Downgrade rail has ONE instance rendered
  // at one of two positions: directly under the featured window (no pinned
  // deck yet, today's layout) or under the deck card once one exists, so the
  // actionable card always leads and the alternates read as "more trades"
  // beneath it. Built here rather than duplicated at both mount points.
  const assetIdeasPanel = singlePinFeatured ? (
    <AssetIdeasPanel
      data={assetIdeasQuery.data}
      loading={assetIdeasQuery.isFetching}
      pinnedName={singlePin!.player.name}
      direction={singlePin!.direction}
      // #317 — while the deck holds the slot the featured window is NOT on
      // screen, so no row may carry the "IN WINDOW" tag or be tap-disabled
      // (that inert row was half the dead click). Nulled exactly when the
      // window's own gate (:featuredShown && !singlePinDeckActive) hides it.
      featuredKey={
        singlePinDeckActive
          ? null
          : featuredShown
            ? assetIdeaKey(featuredShown)
            : null
      }
      onSelectIdea={handleSelectIdea}
    />
  ) : null;

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        holdMs={toast?.holdMs ?? 1500}
        action={toast?.action}
        onDismiss={() => setToast(null)}
        topOffset={modeBarBottom > 0 ? modeBarBottom + space.sm : undefined}
      />

      {/* #257 — cut entirely when the full sheet consolidates the Controls
          Card: its only entry point (the card's Outlook "Edit" row) no
          longer renders, and the inferred-outlook banner opens the full
          sheet instead (see its onPress below). */}
      {!consolidateOn ? (
        <OutlookSheet
          visible={outlookOpen}
          // Phase-2: with no saved outlook, preselect the backend's
          // roster-inferred guess so "Change" opens on the right option.
          initial={prefsQuery.data?.team_outlook ?? inferredOutlook}
          onClose={() => setOutlookOpen(false)}
          onSubmit={handleOutlookSubmit}
        />
      ) : null}

      {/* #246 — the hub's Trade DNA editor as a sheet over the deck
          (receipt "Change" / legacy editDna param). #236 autosave means
          Done is a pure dismiss; the #173 untouchables management sheet
          stays reachable inside it via Manage.
          #257: under `consolidateOn` this becomes the full sheet — the
          `full` prop is the only difference; omitting it (flag off, or any
          other DNA-only caller) keeps this byte-identical to before. */}
      <TradeDnaSheet
        visible={dnaSheetOpen}
        openSource={dnaOpenSource}
        onClose={handleEditSheetClose}
        full={
          consolidateOn
            ? {
                fairnessOn,
                onToggleFairness: handleToggleFairness,
                deckHasLanes,
                laneFilter,
                onLaneFilter: handleLaneFilter,
                targeting:
                  targetingEnabled && finderMode !== 'player'
                    ? {
                        pinnedGive,
                        pinnedReceive,
                        onAdd: (dir: 'trade_away' | 'acquire') => {
                          setTargetDirection(dir);
                          setDnaSheetOpen(false);
                          setPickerReturnsToSheet(true);
                          setTargetPickerOpen(true);
                        },
                        onRemove: handleRemoveTarget,
                      }
                    : null,
                onAnyChange: () => {
                  prefsChangedSinceGenerateRef.current = true;
                },
                // #172 — omitted entirely when the flag is off, which is
                // what keeps the chip row from rendering at all.
                tradeIntent: intentModesOn ? tradeIntent : undefined,
                onTradeIntent: intentModesOn ? handleTradeIntent : undefined,
                // #269 — omitted entirely when the flag is off, which is
                // what keeps the League/Trade-with block from rendering.
                teamTargeting: sheetTargetingOn
                  ? {
                      leagueName: league?.league_name ?? null,
                      onOpenLeaguePicker: openLeaguePickerFromSheet,
                      opponentName: scopedOpponentName ?? null,
                      onOpenPicker: openTeamPickerFromSheet,
                      onClear: clearSheetOpponent,
                    }
                  : undefined,
              }
            : undefined
        }
      />

      {/* #223 — league switching moved to the global TopBar (single sheet
          instance there). The [leagueId] useEffect above still resets
          deck/job state when zustand's league slice changes, and
          league-prefs refetches automatically via its query key — the
          switch's origin never mattered. */}

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
        ref={mainScrollRef}
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        scrollEnabled={!topCard || !generateMutation.isPending}
        // Decline reasons only (`undefined` when the flag is off, which is
        // identical to not passing it): the inline free-text composer needs
        // scroll range BELOW the keyboard for its send button.
        automaticallyAdjustKeyboardInsets={declineReasonsOn ? true : undefined}
        onScroll={(e: NativeSyntheticEvent<NativeScrollEvent>) => {
          // B1 — a measured spotlight frame is absolute window coordinates,
          // so the guide must re-measure whenever this list moves.
          notifyGuideTargetsMoved();
          // The decline-reason panel's reveal callback needs the offset to
          // scroll from; the ref write is flag-scoped, the listener is not.
          if (declineReasonsOn) mainScrollYRef.current = e.nativeEvent.contentOffset.y;
        }}
        scrollEventThrottle={16}
      >
        {/* FB #156/#246 — the persistent mode chip strip. Since the
            guided-first landing (#246) this renders on the tab's landing
            itself (TradesHome mounts with mode:'guided') and is the
            mode-switching home: Guided/Team/Player switch in place, Calc
            and Free agents push their screens. Replaces the Trades/
            Portfolio/Calculator subnav below for finder launches. The
            hint line renders only in the cold start (no deck yet, mock
            B2) — dropped once a deck exists. */}
        {/* #270/#272 — experiment `trades_home_inline`. `showInlineHome`
            (guided landing + an assigned variant) swaps the mode-bar's row
            for the bigger-icon utility row (Draft/Free agents/Manual calc,
            no league or player reference on the button itself, #272
            verbatim) and adds the League/Trading-with pill strip (#270
            verbatim, second sentence — mounted BELOW the outlook receipt
            since #314). Control (or any non-guided mode) renders
            `TradeFinderModeBar` exactly as before — byte-identical. */}
        {/* P0-2 — one conditional host View so the mode-bar region can be
            measured (onLayout) and the Toast can clear it instead of clipping
            the chips. The condition is HOISTED onto the wrapper: an
            unconditional wrapper would still be a flex child when the slot
            is null, and the ScrollView's own `gap` would then apply on both
            sides of a zero-height view. #314 moved the TradingWithStrip out
            of this wrapper (below the receipt); the wrapper keeps the
            utility-row/mode-bar slot. */}
        {finderMode || showInlineHome ? (
          <View
            style={styles.modeBarWrap}
            onLayout={(e) => {
              const { y, height } = e.nativeEvent.layout;
              setModeBarBottom(y + height);
            }}
          >
          {finderMode ? (
            showInlineHome ? (
              <TradeHomeUtilityRow
                onFreeAgents={() => navigation?.navigate?.('FreeAgents')}
                onManualCalc={() => navigation?.navigate?.('TradeCalculator')}
                onDraft={
                  draftRoomOn
                    ? () => navigation?.navigate?.('DraftRoom')
                    : undefined
                }
                // Presentation v2 — passing the handler is what creates the
                // control; flag off ⇒ omitted ⇒ this row is unchanged.
                onTodaysTrade={
                  presentationV2On
                    ? () => navigation?.navigate?.('TodaysTrade')
                    : undefined
                }
                // #376 — the finder's conditions, back on the surface that
                // replaced the mode bar. Gated on `consolidateOn` for the same
                // reason `hideTeamAndPlayer` is: that flag is what makes the
                // full sheet exist, so passing the handler without it would
                // open a DNA-only sheet and quietly not be "the filters".
                onConditions={
                  consolidateOn ? () => setDnaSheetOpen(true) : undefined
                }
                // Receipts (docs/plans/receipts/) — same optional-prop
                // convention as onTodaysTrade above: the handler's presence IS
                // the control, so with `receipts.screen` dark this row renders
                // exactly as it does today and the screen is unreachable.
                onTrackRecord={
                  receiptsOn
                    ? () => navigation?.navigate?.('Receipts')
                    : undefined
                }
              />
            ) : (
              <TradeFinderModeBar
                mode={finderMode}
                teamName={scopedOpponentName}
                onSwitch={switchFinderMode}
                onCalculator={() => navigation?.navigate?.('TradeCalculator')}
                onFreeAgents={() => navigation?.navigate?.('FreeAgents')}
                // rookie-draft placement, option B (operator decision
                // 2026-08-06): the Draft chip is the draft's PERMANENT home and
                // LEADS the strip. Passing the handler is what creates the chip,
                // so `draft.room` off ⇒ five chips exactly as today.
                onDraft={
                  draftRoomOn
                    ? () => navigation?.navigate?.('DraftRoom')
                    : undefined
                }
                // Presentation v2 — same convention as onDraft above: the
                // handler's presence IS the chip. Flag off ⇒ omitted ⇒ the
                // strip's chip array is unchanged.
                onTodaysTrade={
                  presentationV2On
                    ? () => navigation?.navigate?.('TodaysTrade')
                    : undefined
                }
                showHint={deck.length === 0}
                // #269 — Team and Player selection moved into the full sheet;
                // only hide the chips when that sheet actually exists (also
                // requires `consolidateOn`) so there's always a way to reach
                // them.
                hideTeamAndPlayer={sheetTargetingOn && consolidateOn}
              />
            )
          ) : null}
          </View>
        ) : null}
        {/* #231 — outlook bias receipt (self-contained for row 1; #315 adds
            the host-composed `details` row 2). #246: Change opens the DNA
            sheet over the deck. Also stands in as variant B's "prefs summary
            line" (canvas mock frames) — the page has no existing single
            string combining outlook + chasing/shopping positions +
            trade-idea lane, and building one just for this experiment would
            duplicate state TradeDnaSheet already owns privately; this
            receipt is the closest existing analog (same "Change"
            affordance, same data source) — see status doc. */}
        {finderMode ? (
          // The wrapper exists only to give N2 Form A's spotlight a frame
          // (see outlookReceiptWrapRef); it adds no layout of its own.
          <View ref={outlookReceiptWrapRef} collapsable={false}>
            <OutlookBiasReceipt
              details={receiptDetails}
              onChange={() => {
                // N2 form A is an `action` step: the real tap on the
                // control it spotlights is what advances it.
                advanceGuideIfActive('n2a');
                setDnaSheetOpen(true);
              }}
            />
          </View>
        ) : null}

        {/* #257 (operator decision Q2) — dismissing the full sheet does NOT
            auto-regenerate the deck. If a DNA preference (outlook/chasing/
            shopping/untouchables) changed while it was open, this one-line
            strip offers the refresh instead of silently leaving a stale
            deck on screen. */}
        {consolidateOn && showPrefsChangedStrip ? (
          <Pressable
            testID="trades.prefs-changed-strip"
            accessibilityRole="button"
            accessibilityLabel="Preferences changed — tap to refresh trades"
            onPress={() => handleFindTrades('prefs_changed_strip')}
            style={({ pressed }) => [
              styles.prefsChangedStrip,
              pressed && { backgroundColor: ink.ink3 },
            ]}
          >
            <View style={styles.prefsChangedTick} />
            <Text style={styles.prefsChangedText}>
              Preferences changed — tap to refresh
            </Text>
          </Pressable>
        ) : null}

        {/* #314 — the on-page filters sit BELOW the receipt and its
            transient refresh nudge (which stays glued to the banner it
            refers to): the banner summarizes the configuration, the
            filters act on it. Moved out of `modeBarWrap` above — so
            `modeBarBottom` now measures the utility row only and the
            Toast overlaps this zone, the same class of overlap the
            receipt already lived with (accepted, plan §3). The strip's
            own `showInlineHome` gate travels with it; the control
            variant renders none of this. Its pill row is flex, so the
            held-for-operator "Players" pill (#314's interpretive step)
            can later slot in beside "Trading with" without relayout. */}
        {showInlineHome ? (
          <TradingWithStrip
            leagueName={league?.league_name ?? null}
            opponentName={scopedOpponentName ?? null}
            onOpenLeaguePicker={openLeaguePickerFromStrip}
            onOpenTeamPicker={openTeamPickerFromStrip}
          />
        ) : null}

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

        {/* #357/#358/#359 — Team Review entry. Placed HERE and not as a
            seventh chip in TradeFinderModeBar, on that component's own
            measurement: its shipped chips already run ~402pt against ~361pt of
            usable width, so the strip is genuinely scrolled and an APPENDED
            chip would sit off-screen and never be seen. The user who most
            needs this feature is the least likely to scroll a chip rail to
            find it. #359 was filed against TradesHome, which is exactly here.
            Dismissing COLLAPSES it to a one-line row rather than removing it
            (the D-025 collapsed-strip pattern) — a permanently dismissible
            entry means one accidental tap loses the feature forever. */}
        {teamReviewOn && leagueId ? (
          <TeamReviewEntryCard
            leagueId={leagueId}
            onOpen={(source) => {
              try {
                track('team_review_opened', { league_id: leagueId, source });
              } catch { /* analytics must never block navigation */ }
              navigation.navigate('TeamReview' as never);
            }}
          />
        ) : null}

        {/* #224 — classic (flag-off) Trades home page title. With the
            TopBar carrying the league instead of the wordmark, this screen
            needs its own identity; matches the hub's in-page heading. The
            hub-launched TradeDeck mode gets its title from the mode bar,
            and first-run keeps its deliberately collapsed chrome. */}
        {!firstRun && !finderMode && (
          <Text style={styles.pageTitle} accessibilityRole="header">
            Find a Trade
          </Text>
        )}

        {/* B3 — Sub-route pills. Trades is the active screen here;
            Portfolio only shows when the user has 2+ connected leagues.
            Calculator (manual trade builder, demo data) is always
            reachable — it needs no league. Chalkline chip construction:
            1px border + label type on ink; active = ink-3 well + chalk. */}
        {!firstRun && !finderMode && (
        <View style={styles.subnavRow}>
          <View testID="trades.subnav.trades" style={[styles.subnavPill, styles.subnavPillActive]}>
            <Text style={[styles.subnavPillText, styles.subnavPillTextActive]}>
              Trades
            </Text>
          </View>
          {showPortfolioPill ? (
            <Pressable
              testID="trades.subnav.portfolio"
              accessibilityRole="button"
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
            accessibilityRole="button"
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

        {/* #223 — the "Trading in" LeaguePill row that sat here is gone:
            the global TopBar carries the active league + switcher now. */}

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
        {/* #243 — single-pin featured mode: the Controls Card collapses to
            a one-line pin summary by default (the card's primary action is
            gone in this mode per #241 — only the editable chrome remained).
            Edit expands the exact full card below in place; every other
            mode renders the full card unconditionally, exactly as before. */}
        {/* #257 — flag off (or the classic non-finder-mode home) renders
            this exact block, unchanged. Flag on replaces it below: the
            receipt is the sole entry point into the (now full) sheet, and
            only the on-screen remnants that don't belong in any sheet —
            the player-mode board (Q4), Find a Trade, the progress strip,
            the liked-trades count — render directly here. */}
        {!consolidateOn ? (
        <>
        {!firstRun && singlePin && !pinEditOpen ? (
          <View style={styles.pinSummaryCard} testID="trades.pin-summary">
            <View
              style={[
                styles.boardPosDot,
                {
                  backgroundColor: singlePin.player.position
                    ? posColor(singlePin.player.position as any)
                    : ink.lineStrong,
                },
              ]}
            />
            <Text style={styles.pinSummaryText} numberOfLines={1}>
              {'Pinned: '}
              <Text style={styles.pinSummaryName}>
                {singlePin.player.name}
              </Text>
            </Text>
            <Pressable
              testID="trades.pin-summary.edit"
              accessibilityRole="button"
              accessibilityLabel="Edit pin and trade controls"
              onPress={() => setPinEditOpen(true)}
              hitSlop={8}
              style={styles.pinSummaryEditTap}
            >
              <Text style={styles.pinSummaryEdit}>Edit</Text>
            </Pressable>
            {/* #288 — always-visible clear/back affordance: unpins and
                (when this pin came from a "Keep · more offers" tap on a
                clean deck) restores the ORIGINAL found-trade deck position
                exactly; otherwise leaves the ordinary empty-deck state
                where "Find a Trade" is the recovery path. Either way the
                user is never stranded in single-pin mode without a way out. */}
            <Pressable
              testID="trades.pin-summary.clear"
              accessibilityRole="button"
              accessibilityLabel={`Clear pinned player ${singlePin.player.name} and go back`}
              onPress={handleClearPin}
              hitSlop={8}
              style={styles.pinSummaryEditTap}
            >
              <Icon name="x" size={14} color={chalk.dim} />
            </Pressable>
          </View>
        ) : (
        <Card>
          <View style={styles.controlInner}>
          {/* #243 — expanded-state header: collapse affordance back to the
              one-liner. Only exists in single-pin mode (no such affordance
              elsewhere — the card is permanent there). */}
          {!firstRun && singlePin ? (
            <View style={styles.controlRow}>
              <View style={{ flex: 1 }}>
                <TickLabel>Editing pin</TickLabel>
              </View>
              <Pressable
                testID="trades.pin-summary.done"
                accessibilityRole="button"
                accessibilityLabel="Done editing pin"
                onPress={() => setPinEditOpen(false)}
                hitSlop={8}
                style={styles.pinSummaryEditTap}
              >
                <Text style={styles.pinSummaryEdit}>Done</Text>
              </Pressable>
            </View>
          ) : null}
          {/* #254/#255 — suppressed whenever the minimized outlook bar
              (OutlookBiasReceipt, above the deck) is on screen: it states
              the same outlook and its Change opens the superset editor.
              Kept for the configurations where that bar renders nothing
              (classic flag-off home, `trade.outlook_direction` off, or a
              non-directional outlook) so no state loses its outlook
              surface. */}
          {!firstRun && !outlookReceiptShown && (
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
              {/* S4 PRD-01 (ux.help_surface): ⓘ answers "why is this trade
                  fair?" at the moment of doubt. Flag off renders the bare
                  TickLabel exactly as before. */}
              {helpOn ? (
                <View style={styles.helpLabelRow}>
                  <TickLabel>Trade fairness</TickLabel>
                  <InfoButton
                    testID="trades.fairness-help"
                    label="How trades are priced"
                    size={16}
                    onPress={() => {
                      track('help_opened', { topic: 'trade_pricing' }, 'Trades');
                      setPricingHelpOpen(true);
                    }}
                  />
                </View>
              ) : (
                <TickLabel>Trade fairness</TickLabel>
              )}
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

          {/* Phase-2 lane filter — Team-fit moves / Value moves pills with
              an implicit All state (tap the active pill to clear). Mirrors
              the FB-47 direction-toggle construction; renders only when the
              deck actually carries lanes.
              #256: the pill said "Window moves" — the engine's word for the
              `window` lane, which nobody says out loud. "Team-fit moves" is
              the display label everywhere (mobile pill, web filter button,
              web card chip); the `window` / `value` ENUM is untouched (see
              docs/cross-client-invariants.md). Deliberately not "Win-now
              moves": the window lane is win-now for a contender and
              youth+picks for a rebuilder, so that label would lie to half
              the users. */}
          {!firstRun && deckHasLanes && (
            <View style={styles.targetDirRow}>
              {(
                [
                  ['window', 'Team-fit moves'],
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
              #156 finish item 1: in the hub's Specific Player mode the
              section renders as the mockup's two-column TRADE AWAY / TRADE
              FOR board (#209 order); everywhere else the original
              direction-toggle construction is untouched. Position-level
              targeting stays in OutlookSheet's chips; this is the
              player-level entry point. */}
          {!firstRun && targetingEnabled && finderMode === 'player' ? (
            <View style={styles.targetSection}>
              {/* #209 — give→get reading order everywhere: AWAY (what you
                  send) renders LEFT, FOR (what you get) RIGHT, matching the
                  featured card's and the idea rows' columns. */}
              <View style={styles.playerBoard}>
                <View style={[styles.boardCol, styles.boardColAway]}>
                  <Text style={[styles.boardColH, styles.boardColHAway]}>
                    TRADE AWAY
                  </Text>
                  {pinnedGive.map((p) => (
                    <Pressable
                      key={p.id}
                      testID={`trades.board.away.${p.id}`}
                      onPress={() => handleRemoveTarget(p.id, 'trade_away')}
                      accessibilityRole="button"
                      accessibilityLabel={`Remove ${p.name} from trade-away targets`}
                      style={({ pressed }) => [
                        styles.boardMini,
                        pressed && styles.subnavPillPressed,
                      ]}
                    >
                      {p.position ? (
                        <View
                          style={[
                            styles.boardPosDot,
                            { backgroundColor: posColor(p.position as any) },
                          ]}
                        />
                      ) : null}
                      <Text style={styles.boardMiniText} numberOfLines={1}>
                        {p.name}
                      </Text>
                      <Icon name="x" size={12} color={chalk.faint} />
                    </Pressable>
                  ))}
                  <Pressable
                    testID="trades.board.add-away"
                    accessibilityRole="button"
                    accessibilityLabel="Add a player to trade away"
                    onPress={() => {
                      setTargetDirection('trade_away');
                      setTargetPickerOpen(true);
                    }}
                    style={({ pressed }) => [
                      styles.boardAddBtn,
                      pressed && styles.subnavPillPressed,
                    ]}
                  >
                    <Text style={styles.boardAddText}>+ Add asset</Text>
                  </Pressable>
                </View>
                <View style={[styles.boardCol, styles.boardColFor]}>
                  <Text style={[styles.boardColH, styles.boardColHFor]}>
                    TRADE FOR
                  </Text>
                  {pinnedReceive.map((p) => (
                    <Pressable
                      key={p.id}
                      testID={`trades.board.for.${p.id}`}
                      onPress={() => handleRemoveTarget(p.id, 'acquire')}
                      accessibilityRole="button"
                      accessibilityLabel={`Remove ${p.name} from trade-for targets`}
                      style={({ pressed }) => [
                        styles.boardMini,
                        pressed && styles.subnavPillPressed,
                      ]}
                    >
                      {p.position ? (
                        <View
                          style={[
                            styles.boardPosDot,
                            { backgroundColor: posColor(p.position as any) },
                          ]}
                        />
                      ) : null}
                      <Text style={styles.boardMiniText} numberOfLines={1}>
                        {p.name}
                      </Text>
                      <Icon name="x" size={12} color={chalk.faint} />
                    </Pressable>
                  ))}
                  <Pressable
                    testID="trades.board.add-for"
                    accessibilityRole="button"
                    accessibilityLabel="Add a player to trade for"
                    onPress={() => {
                      setTargetDirection('acquire');
                      setTargetPickerOpen(true);
                    }}
                    style={({ pressed }) => [
                      styles.boardAddBtn,
                      pressed && styles.subnavPillPressed,
                    ]}
                  >
                    <Text style={styles.boardAddText}>+ Add target</Text>
                  </Pressable>
                </View>
              </View>
              {pinnedGive.length >= 2 ? (
                <PackageToggle
                  on={packageMode}
                  onToggle={() => {
                    haptics.selection();
                    setPackageMode(!packageMode);
                    resetDeckForNewTargets();
                  }}
                />
              ) : null}
            </View>
          ) : !firstRun && targetingEnabled ? (
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
              {pinnedGive.length >= 2 ? (
                <PackageToggle
                  on={packageMode}
                  onToggle={() => {
                    haptics.selection();
                    setPackageMode(!packageMode);
                    resetDeckForNewTargets();
                  }}
                />
              ) : null}
            </View>
          ) : null}

          {/* Find-a-Trade button. While a job is running, the button is
              disabled — the progress strip below acts as the live signal.
              `generateMutation.isPending` is only true during the brief
              POST round-trip; after that, status flows through `job`.
              #298 undoes #241's hiding of this button in single-pin featured
              mode: the generated cards DO have somewhere to render again
              (the deck takes the featured window's slot once it has cards),
              and without the button there was no way to reach an
              accept/declinable trade from a pinned surface at all. This is
              the `!consolidateOn` legacy layout's copy of the CTA — the
              consolidated layout has its own below; they are the two arms of
              one ternary and never render together. */}
          <Button
            variant="primary"
            testID="trades.find-btn"
            label={
              singlePinFeatured || (deck.length > 0 && job?.status === 'complete')
                ? 'Find more trades'
                : 'Find a Trade'
            }
            disabled={!leagueId || generateMutation.isPending || job?.status === 'running'}
            onPress={() => {
              track('find_trades_tapped', { mode: deckMode }, 'Trades');
              setPinIdeaResumed(false); // #317 — parity with handleFindTrades
              generateMutation.mutate({});
            }}
            style={styles.findBtn}
          />

          {/* Progress strip — visible only during a running job. Cards are
              streaming into the deck above; this just narrates the work.
              Opponent coverage renders as a ice Meter with mono counts.
              #298: shown in single-pin mode too, now that a generate there
              lands somewhere. */}
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
        )}
        </>
        ) : (
        <>
        {/* #257 — player mode keeps its on-screen TRADE AWAY/TRADE FOR
            board (operator decision Q4): the full sheet does not absorb
            it, so it renders here exactly as it did inside the old
            Controls Card, just no longer wrapped in that card. */}
        {!firstRun && targetingEnabled && finderMode === 'player' ? (
          <View style={styles.targetSection}>
            <View style={styles.playerBoard}>
              <View style={[styles.boardCol, styles.boardColAway]}>
                <Text style={[styles.boardColH, styles.boardColHAway]}>
                  TRADE AWAY
                </Text>
                {pinnedGive.map((p) => (
                  <Pressable
                    key={p.id}
                    testID={`trades.board.away.${p.id}`}
                    onPress={() => handleRemoveTarget(p.id, 'trade_away')}
                    accessibilityRole="button"
                    accessibilityLabel={`Remove ${p.name} from trade-away targets`}
                    style={({ pressed }) => [
                      styles.boardMini,
                      pressed && styles.subnavPillPressed,
                    ]}
                  >
                    {p.position ? (
                      <View
                        style={[
                          styles.boardPosDot,
                          { backgroundColor: posColor(p.position as any) },
                        ]}
                      />
                    ) : null}
                    <Text style={styles.boardMiniText} numberOfLines={1}>
                      {p.name}
                    </Text>
                    <Icon name="x" size={12} color={chalk.faint} />
                  </Pressable>
                ))}
                <Pressable
                  testID="trades.board.add-away"
                  accessibilityRole="button"
                  accessibilityLabel="Add a player to trade away"
                  onPress={() => {
                    setTargetDirection('trade_away');
                    setTargetPickerOpen(true);
                  }}
                  style={({ pressed }) => [
                    styles.boardAddBtn,
                    pressed && styles.subnavPillPressed,
                  ]}
                >
                  <Text style={styles.boardAddText}>+ Add asset</Text>
                </Pressable>
              </View>
              <View style={[styles.boardCol, styles.boardColFor]}>
                <Text style={[styles.boardColH, styles.boardColHFor]}>
                  TRADE FOR
                </Text>
                {pinnedReceive.map((p) => (
                  <Pressable
                    key={p.id}
                    testID={`trades.board.for.${p.id}`}
                    onPress={() => handleRemoveTarget(p.id, 'acquire')}
                    accessibilityRole="button"
                    accessibilityLabel={`Remove ${p.name} from trade-for targets`}
                    style={({ pressed }) => [
                      styles.boardMini,
                      pressed && styles.subnavPillPressed,
                    ]}
                  >
                    {p.position ? (
                      <View
                        style={[
                          styles.boardPosDot,
                          { backgroundColor: posColor(p.position as any) },
                        ]}
                      />
                    ) : null}
                    <Text style={styles.boardMiniText} numberOfLines={1}>
                      {p.name}
                    </Text>
                    <Icon name="x" size={12} color={chalk.faint} />
                  </Pressable>
                ))}
                <Pressable
                  testID="trades.board.add-for"
                  accessibilityRole="button"
                  accessibilityLabel="Add a player to trade for"
                  onPress={() => {
                    setTargetDirection('acquire');
                    setTargetPickerOpen(true);
                  }}
                  style={({ pressed }) => [
                    styles.boardAddBtn,
                    pressed && styles.subnavPillPressed,
                  ]}
                >
                  <Text style={styles.boardAddText}>+ Add target</Text>
                </Pressable>
              </View>
            </View>
            {pinnedGive.length >= 2 ? (
              <PackageToggle
                on={packageMode}
                onToggle={() => {
                  haptics.selection();
                  setPackageMode(!packageMode);
                  resetDeckForNewTargets();
                }}
              />
            ) : null}
          </View>
        ) : null}

        {/* Find-a-Trade — bare button (no Card): the mockup's "after"
            screen shows the landing as a trade, not a control panel.
            #298 — no longer hidden in single-pin featured mode: removing it
            there left the pinned surface with no way to get a swipeable,
            accept/declinable trade at all. In that mode it reads "Find more
            trades" from the start, because the featured window is already
            showing one (V1 mock: "CTA relabelled for the pinned context"). */}
        <Button
          variant="primary"
          testID="trades.find-btn"
          label={
            singlePinFeatured || (deck.length > 0 && job?.status === 'complete')
              ? 'Find more trades'
              : 'Find a Trade'
          }
          disabled={!leagueId || generateMutation.isPending || job?.status === 'running'}
          onPress={() => handleFindTrades()}
          style={styles.findBtn}
        />

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
        </>
        )}

        {/* #270 — variant `canvas`: the hand-built two-column trade canvas,
            fed by the guided deck's own suggestion rail (see
            TradeBuildCanvas). Scoped to the guided landing's mainline path
            only — excluded in first-run (still finding its onboarding pace)
            and single-pin featured mode (which already IS a build-canvas-
            like surface; layering a second one would be confusing, not
            additive). Deliberately additive, not a replacement: the swipe
            deck below still renders untouched — see TradeBuildCanvas's file
            header and the status doc for why. */}
        {homeInlineVariant === 'canvas' &&
        finderMode === 'guided' &&
        !firstRun &&
        !singlePin &&
        leagueId ? (
          <TradeBuildCanvas
            leagueId={leagueId}
            userId={userId}
            opponentUserId={scopedOpponent ?? null}
            suggestions={deck}
          />
        ) : null}

        {/* #216/#209 (flag trade.asset_ideas) — single-pin find-a-trade:
            the FEATURED TRADE window leads (best idea as a full trade card
            with the Dynasty Value Swing verdict + #190 edit-in-calculator),
            the grouped Upgrade / Lateral / Downgrade list sits beneath it,
            visible by default; row taps swap ideas into the window (the
            replaced trade becomes the ‹ Previous trade back target). 0 or
            2+ pins ⇒ nothing here; the deck flow is untouched. */}
        {/* #298 — once a pinned deck exists the deck card takes this slot
            (see the deck wrapper below) and the read-only featured window
            steps aside: two trade summaries stacked on one screen is exactly
            the "which one am I looking at?" confusion #241 removed. The
            alternates rail follows whichever card is leading. */}
        {singlePinFeatured ? (
          <>
            {featuredShown && !singlePinDeckActive ? (
              <View
                onLayout={(e) => {
                  featuredWindowY.current = e.nativeEvent.layout.y;
                }}
              >
                <FeaturedTradeWindow
                  idea={featuredShown}
                  leagueId={leagueId ?? ''}
                  onBack={ideaHistory.length > 0 ? handleFeaturedBack : undefined}
                  onEditInCalculator={() => handleOpenAssetIdea(featuredShown)}
                  calc={playerOffersCalcOn ? { userId } : undefined}
                />
              </View>
            ) : null}
            {singlePinDeckActive ? null : assetIdeasPanel}
          </>
        ) : null}

        {/* Phase-2 one-tap outlook confirm — replaces the force-opened
            OutlookSheet when the backend inferred an outlook from the
            roster. Confirm saves the inference with empty position prefs;
            Change opens the sheet (preselected) as before. Bordered-chalk
            (secondary) Confirm — the screen's ice budget is already spent
            (fairness thumb, Find a Trade, queued state). */}
        {outlookBannerShown && inferredOutlook ? (
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
                onPress={() =>
                  consolidateOn ? setDnaSheetOpen(true) : setOutlookOpen(true)
                }
              />
            </View>
          </View>
        ) : outlookBannerShown && outlookInlineOn ? (
          // S4 PRD-02 (ux.outlook_inline_default): no inference available —
          // the same inline banner is still the universal first-visit path;
          // the sheet opens only from this explicit tap.
          <View testID="trades.outlook-set-banner" style={styles.inferredBanner}>
            <Text style={type.body}>
              Set your team's outlook — it tunes which trades we find.
            </Text>
            <View style={styles.inferredActions}>
              <Button
                variant="secondary"
                compact
                label="Set outlook"
                onPress={() =>
                  consolidateOn ? setDnaSheetOpen(true) : setOutlookOpen(true)
                }
              />
            </View>
          </View>
        ) : null}

        {/* Onboarding item 4 — provenance chip: which value basis built
            this deck. Deck-level (state is global to every card); item 7
            wires its tap-through to Quick Set. Coach mark 2 (guided layer)
            anchors directly beneath it, once, never stacked with the
            swipe hint. */}
        {/* Item 10 — demo→real bridge: the one demo investment (Q6). */}
        {demoBridgeOn && isDemo ? (
          <Pressable
            testID="trades.demo-bridge"
            accessibilityRole="button"
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
        {appleBannerShown ? (
          <View testID="trades.apple-session2-banner" style={styles.appleBanner}>
            <Pressable
              style={styles.appleBannerBody}
              onPress={openSession2Banner}
              hitSlop={4}
              accessibilityRole="button"
            >
              <Text style={styles.appleBannerText}>
                {obTotalSwipes} swipes on this board. Sign in with Apple to
                save your rankings to your account →
              </Text>
            </Pressable>
            <Pressable
              testID="trades.apple-session2-banner.dismiss"
              onPress={dismissSession2Banner}
              hitSlop={8}
              accessibilityRole="button"
              accessibilityLabel="Dismiss"
            >
              {({ pressed }) => (
                <Text style={[styles.appleBannerDismiss, pressed && { color: chalk.base }]}>
                  Dismiss
                </Text>
              )}
            </Pressable>
          </View>
        ) : null}
        {provenanceMarkShown ? (
          <CoachMark
            testID="trades.coach-mark.provenance"
            text="These are consensus values. After Quick Set, they're yours."
            onDismiss={dismissProvenanceMark}
          />
        ) : null}

        {/* F9 (deck.first_session) — board-sourced header (2026-07-26
            amendment): the deck was generated from a board updated since
            the user's previous deck — say so (ranks are the loudest
            explicit input; the anti-control-theater rule applied to
            ranking). Server-truthed: board_refresh is only ever present
            when literally true. Mirrors the F3 note's quiet ink-2 bar;
            when both render they STACK, board header FIRST — deck
            provenance before removals (documented choice). */}
        {firstSessionOn && job?.board_refresh?.updated_since_last_deck ? (
          <View testID="trades.board-refresh-note" style={styles.boardRefreshNote}>
            <Text style={styles.boardRefreshText} numberOfLines={2}>
              Built from your updated board
              {job.board_refresh.basis === 'personal' &&
              (job.board_refresh.ranked_player_count ?? 0) > 0
                ? ` — ${job.board_refresh.ranked_player_count} players ranked`
                : ''}
            </Text>
          </View>
        ) : null}

        {/* F3 (deck.fatigue) — honoring note: the deck was shaped by a
            decline-window suppression, say so visibly (the anti-control-
            theater rule). One line, dismissible per job; Undo lifts the
            newest suppression and regenerates. */}
        {fatigueOn &&
        job?.suppression_note &&
        job.suppression_note.count > 0 &&
        suppressionNoteDismissedJob !== job.job_id ? (
          <View testID="trades.suppression-note" style={styles.suppressionNote}>
            <Text style={styles.suppressionNoteText} numberOfLines={2}>
              Hiding trades like ones you declined
            </Text>
            <Pressable
              testID="trades.suppression-note.undo"
              onPress={handleSuppressionUndo}
              disabled={suppressionUndoPending}
              hitSlop={8}
              accessibilityRole="button"
              accessibilityLabel="Undo — show these trades again"
            >
              {({ pressed }) => (
                <Text
                  style={[
                    styles.suppressionNoteUndo,
                    (pressed || suppressionUndoPending) && { color: chalk.dim },
                  ]}
                >
                  Undo
                </Text>
              )}
            </Pressable>
            <Pressable
              testID="trades.suppression-note.dismiss"
              onPress={() => setSuppressionNoteDismissedJob(job.job_id)}
              hitSlop={8}
              accessibilityRole="button"
              accessibilityLabel="Dismiss"
            >
              {({ pressed }) => (
                <Text
                  style={[
                    styles.suppressionNoteDismiss,
                    pressed && { color: chalk.base },
                  ]}
                >
                  Dismiss
                </Text>
              )}
            </Pressable>
          </View>
        ) : null}

        {/* #241 — single-pin featured mode: the featured window + idea list
            above IS the page (approved mock asset-ideas-layout-v3); the
            swipe deck must not also render beneath it. The #216 build left
            this block mounting alongside the new surface, so the old deck
            card showed up as a mystery second trade card under the idea
            rows. Multi-pin / no-pin / classic modes keep the deck exactly
            as before.

            #298 (V1) narrows that gate rather than removing it: hiding the
            deck also removed every accept/decline path from the pinned
            surface, since the swipe handlers, the pass/like row and the
            VoiceOver actions all live inside this block and all funnel into
            `advance()`. Now the deck renders in single-pin mode ONLY once it
            has cards — and the featured window yields the lead slot to it,
            so #241's two-cards-at-once is still impossible. With no cards
            (nothing generated yet) the block stays out entirely: the pinned
            surface must not show "Hit Find a Trade to start" under a
            featured trade it is already showing. */}
        {singlePinFeatured && !singlePinDeckActive ? null : (
        <View
          style={styles.deckWrap}
          ref={deckWrapRef}
          collapsable={false}
          onLayout={(e) => { deckCardY.current = e.nativeEvent.layout.y; }}
        >
          {/* #298 V1 — position counter, single-pin only. The pinned surface
              leads with ONE card and the alternates rail sits below it, so
              without a count it reads as a dead end rather than a deck you
              can swipe through. The classic deck has always been an obvious
              stack (the peek card behind the top one) and gets no counter. */}
          {singlePinDeckActive && topCard ? (
            <View testID="trades.single-pin-deck-count">
              <TickLabel>
                {`Featured trade · ${deckIdx + 1} of ${sortedDeck.length}`}
              </TickLabel>
            </View>
          ) : null}
          {quicksetPromptShown ? (
            // Item 7 — inline prompt card holds the top-of-deck slot until
            // answered; the deck resumes underneath on either action.
            <QuickSetPromptCard
              onAccept={() => acceptQuicksetPrompt('prompt')}
              onDismiss={snoozeQuicksetPrompt}
            />
          ) : adaptationMoment && topCard ? (
            // F9 (deck.first_session) — the adaptation moment: ONE inline
            // card between deck cards (QuickSetPromptCard precedent — it
            // holds the top-of-deck slot until dismissed; the deck resumes
            // underneath). Copy variants are literal truths enforced at
            // trigger time (advance()): 'rerank' only when
            // deck.session_rerank is on AND ≥1 matching card remains;
            // 'descriptive' claims only the remaining cards. Once per app
            // session, dismissible.
            <Card>
              <View style={styles.emptyInner} testID="trades.adaptation-moment">
                <Text style={styles.adaptationTitle}>
                  Noticed you're liking {adaptationMoment.phrase}
                </Text>
                <Text style={styles.emptyBody}>
                  {adaptationMoment.variant === 'rerank'
                    ? 'More of those ahead.'
                    : 'There are more of those in this deck.'}
                </Text>
                <Button
                  testID="trades.adaptation-moment.dismiss"
                  label="Keep swiping"
                  compact
                  onPress={() => {
                    haptics.selection();
                    setAdaptationMoment(null);
                  }}
                />
              </View>
            </Card>
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
                cardImpact={topCardImpact}
                nudge={swipeHintActive}
                onFirstTouch={dismissSwipeHint}
                onCardLayout={(e) => setTopCardH(e.nativeEvent.layout.height)}
                onLike={() => advance('like')}
                onPass={() => advance('pass')}
                dispositionDisabled={
                  swipeMutation.isPending ||
                  // Decline reasons: once the pass is banked the ✓ is inert —
                  // layer 2 owns what happens next on this card.
                  // (RAW deck id — an edited card's derived id would miss.)
                  (declineReasonsOn && reasonBankedId === rawTopCard?.trade_id)
                }
                declineReasons={declineReasonProps}
                untouchableIds={untouchablesEnabled ? untouchableIds : undefined}
                onToggleUntouchable={
                  untouchablesEnabled ? handleToggleUntouchable : undefined
                }
                onSwapPlayer={(player, side) => {
                  // F1 (deck.signal_v2): swap sheet = detail engagement.
                  if (signalV2On) engagementRef.current.detailExpanded = true;
                  setSwapTarget({ player, side });
                }}
                onPlayerMenu={
                  menuOn
                    ? (player, side) => {
                        haptics.selection();
                        // F1 (deck.signal_v2): menu open = detail engagement.
                        if (signalV2On) engagementRef.current.detailExpanded = true;
                        track(
                          'player_menu_opened',
                          { surface: 'trades', side },
                          'Trades',
                        );
                        setMenuTarget({ player, side });
                      }
                    : undefined
                }
                repricing={topCard.edited === true && repriceMutation.isPending}
                fitTargetPositions={fitTargetPositions}
                onKeepSide={
                  // #186 — needs the FB-47 pinning machinery; hidden when
                  // the targeting flag is off.
                  targetingEnabled
                    ? (side) => handleKeepSide(topCard, side)
                    : undefined
                }
                onEditInCalculator={() => handleEditInCalculator(topCard)}
                onRemoveAsset={handleRemoveAsset}
              />
              {/* Queue action — Pass / Interested are driven by swipe
                  gestures on the top card; Queue is a third option that
                  stashes the trade for "Send All" later. Flag-gated so the
                  feature can be tested before broad rollout. */}
              {queueEnabled && leagueId ? (
                <Pressable
                  onPress={() => handleQueue(topCard)}
                  accessibilityRole="button"
                  accessibilityLabel={topCardQueued ? 'Queued' : 'Queue this trade'}
                  accessibilityState={{ selected: topCardQueued }}
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
                givePlayerNames={topCard.give_players.map((p) => p.name)}
                receivePlayerNames={topCard.receive_players.map((p) => p.name)}
                opponentUsername={topCard.opponent_username}
                surface="deck"
                impressionId={signalV2On ? rawTopCard?.impression_id : undefined}
                onSent={
                  // F10 — deck-done summary "proposed" tally.
                  replenishmentOn
                    ? () =>
                        setSessionTally((t) => ({ ...t, proposed: t.proposed + 1 }))
                    : undefined
                }
                compact
                style={styles.sendInSleeper}
              />
              <Text style={styles.deckHint}>
                Swipe right to like · Swipe left to pass
              </Text>
              {/* S3 PRD-02 (ux.player_context_menu): the Matches hold-hint
                  carried onto the deck — the long-press menu needs a visible
                  pointer on its primary surface. */}
              {menuOn ? (
                <Text style={styles.deckHint}>
                  Hold a player for options — info, untouchable, swap.
                </Text>
              ) : null}
              {/* Bad-trade flag (feedback #85) — tertiary to like/pass (which
                  live inside the card since #169), so it sits below the deck
                  at hint-level prominence. Tapping files an engine-quality
                  flag (operator review, not an ELO signal) and advances the
                  deck like a pass. */}
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
                  accessibilityRole="button"
                  accessibilityLabel="Share your last liked trade"
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
            !autoGenFailed &&
            !deckFailure ? (
            // Onboarding item 4 — first-run skeleton deck: generation was
            // auto-started (or pregenerated at auth-return) and cards are
            // streaming in; the manual "Hit Find a Trade" empty state never
            // shows on first run. Falls through to the normal states if the
            // job completes empty or the silent auto-start gives up.
            //
            // P0-2 / G-029: `!deckFailure` is NOT redundant with the
            // `status !== 'error'` guard above it. The poll-abandon path sets
            // job to NULL (not to an errored snapshot), so `job?.status` is
            // `undefined`, the status guard misses, `autoGenFailed` is only
            // ever set from the POST path, and the auto-start effect refuses
            // to re-kick (autoGenRef.current !== 'idle'). Before this guard a
            // first-run user whose polling died sat on this skeleton FOREVER.
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
          ) : deck.length > 0 && summaryVisible ? (
            // F10 (deck.replenishment) — completion moment: deck ENDS on a
            // summary, never auto-advances into a new deck. Chalkline: ink
            // surfaces, mono tallies, ice only on the actions.
            <Card>
              <View style={styles.emptyInner} testID="trades.deck-summary">
                <Text style={styles.emptyTitle}>Deck done</Text>
                <Text style={styles.summaryTally}>
                  {sessionTally.passed} passed · {sessionTally.liked} liked ·{' '}
                  {sessionTally.proposed} proposed
                </Text>
                {/* #316 — never "after waivers": dynasty leagues barely use
                    waivers and the deck actually refreshes via the weekly
                    replenishment cron + the always-mounted Find-more-trades
                    CTA above. "Find more trades" is quoted verbatim from
                    that CTA's label in this exact state. Pinned by the
                    smoke/12 flow's deck-done step. */}
                <Text style={styles.emptyBody}>
                  Fresh ideas land every week — or tap Find more trades to
                  search again now.
                </Text>
                {/* N4 (PRD §5.3) — the pin line reads as content on the
                    card, not chrome, and its verb has a reachable control:
                    the CTA hands off to the FB-47 targeting board. */}
                {v2N4PinLine ? (
                  <Text style={styles.emptyBody}>{GUIDE.n4().line}</Text>
                ) : null}
                <View style={styles.summaryBtnRow}>
                  <Button
                    testID="trades.deck-summary.see-liked"
                    label="See liked"
                    variant="secondary"
                    compact
                    onPress={() => navigation.navigate('Portfolio')}
                  />
                  {/* Button budget (PRD §5.3): the card keeps ONE primary.
                      With the pin line up, `Pin targets →` is it and Done
                      demotes to ghost; See liked stays secondary. */}
                  <Button
                    testID="trades.deck-summary.done"
                    label="Done"
                    variant={v2N4PinLine ? 'ghost' : 'primary'}
                    compact
                    onPress={handleSummaryDone}
                  />
                  {v2N4PinLine ? (
                    <Button
                      testID="trades.deck-summary.pin"
                      label={GUIDE.n4().ctas?.[0]?.label ?? 'Pin targets →'}
                      compact
                      onPress={handleSummaryPinTargets}
                    />
                  ) : null}
                </View>
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
          ) : deckFailure ? (
            // P0-2 — the last search FAILED, and this is the only state that
            // says so. Sits below row 7 (deck.length > 0) so a job that errors
            // after banking cards keeps its partial deck (S-09), and above the
            // never-searched fallback so that card now means what it says.
            <Card>
              <View style={styles.emptyInner} testID="trades.deck-error">
                <Text style={styles.deckErrorTitle}>Search failed</Text>
                <Text style={styles.emptyBody}>{deckFailure.message}</Text>
                <Button
                  testID="trades.deck-error.retry"
                  label="Try again"
                  variant="secondary"
                  compact
                  onPress={() => handleFindTrades('deck_error_retry')}
                />
              </View>
            </Card>
          ) : scopedEmpty ? (
            // #330 R-6 — a SCOPED search (player pinned + opponent scoped)
            // completed with zero cards. Honest about what already happened:
            // the server's #189 relaxed pass has ALREADY widened the
            // fairness band before returning zero, so the copy claims the
            // stronger fact — do not "fix" it back to "under your current
            // settings". The pin and the scope stay locked (R-7): the only
            // ways out are this link and the sheet's own visible edits.
            <Card>
              <View style={styles.emptyInner} testID="trades.scoped-empty">
                <Text style={styles.emptyTitle}>No trade found</Text>
                <Text style={styles.emptyBody}>
                  {scopedEmpty.direction === 'give'
                    ? `We couldn't build a trade that sends ${scopedEmpty.playerName} to ${scopedEmpty.teamName} — even after stretching the fairness band. Your player and team stayed locked.`
                    : `We couldn't build a trade that gets ${scopedEmpty.playerName} from ${scopedEmpty.teamName} — even after stretching the fairness band. Your target and team stayed locked.`}
                </Text>
                <Button
                  testID="trades.scoped-empty.back"
                  label="Back to league rankings"
                  variant="secondary"
                  compact
                  onPress={() =>
                    navigation.navigate('League', { screen: 'LeagueRankings' })
                  }
                />
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
        )}

        {/* #298 — second mount point for the single instance built above:
            with a pinned deck leading, the Upgrade / Lateral / Downgrade
            alternates read as "more trades" underneath it. */}
        {singlePinDeckActive ? assetIdeasPanel : null}
        </>
        )}

        {/* #182 — Free-agents entry from the find-a-trade surface. Same
            explore-row construction as the League tab's Explore list
            (hairline list row, title + body-sm meta + chevron); FreeAgents
            is a ROOT-stack route, so navigate() bubbles up from the tab
            navigator exactly as it does from LeagueScreen. Hidden during
            first-run (collapsed chrome) and in hub-launched deck modes
            (focused surface). */}
        {!firstRun && !finderMode && (
          <View style={styles.exploreSection}>
            <TickLabel>Explore</TickLabel>
            <Pressable
              testID="trades.explore.free-agents"
              accessibilityRole="button"
              accessibilityLabel="Free agents"
              onPress={() => navigation.navigate('FreeAgents')}
              style={({ pressed }) => [
                styles.exploreRow,
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <View style={styles.exploreMain}>
                <Text style={type.title}>Free agents</Text>
                <Text style={[type.bodySm, styles.exploreSub]}>
                  Best available players in this league
                </Text>
              </View>
              <Icon name="chevron-right" size={16} color={chalk.dim} />
            </Pressable>
          </View>
        )}
      </ScrollView>

      {/* Queue footer bar — anchored above the bottom tab nav. Tap the
          left side to expand the queue sheet; tap "Send All" to fire the
          staggered Sleeper deep-links and clear. Flag-gated. */}
      {queueEnabled && queuedTrades.length > 0 ? (
        <View style={styles.queueFooter}>
          <Pressable
            onPress={() => setQueueSheetOpen(true)}
            accessibilityRole="button"
            accessibilityLabel={`${queuedTrades.length} queued, tap to review`}
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
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={styles.queueSheet}>
          <View style={styles.queueHandle} />
          <View style={styles.queueSheetHeader}>
            <Text style={styles.queueSheetTitle} accessibilityRole="header">Trade queue</Text>
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

      {/* #156 finish item 4 — in-screen manager picker for the Team chip;
          #269 — ALSO the sheet's "Trade with" row opens this same Modal
          (close-sheet/open-picker/reopen-sheet, see openTeamPickerFromSheet
          above). Legacy flow lands via setParams so the scope swaps IN
          PLACE; the sheet flow toggles `sheetOpponent` (tap-again-to-clear)
          and marks the "Preferences changed" strip instead of resetting
          the deck. Either way this closes through `closeTeamPicker`. */}
      <Modal
        visible={teamPickerOpen}
        transparent
        animationType="slide"
        onRequestClose={closeTeamPicker}
      >
        <Pressable
          style={styles.teamPickerBackdrop}
          onPress={closeTeamPicker}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={styles.teamPickerSheet}>
          <View style={styles.teamPickerGrabber} />
          <Text style={type.heading} accessibilityRole="header">
            Pick a manager
          </Text>
          <Text style={type.bodySm}>
            We'll surface only mutual-gain deals with their roster.
          </Text>
          {leagueUsersQuery.isLoading ? (
            <ActivityIndicator color={ice.base} style={{ marginTop: space.lg }} />
          ) : (
            <ScrollView style={styles.teamPickerScroll}>
              {teamPickerOpponents.map((o) => {
                const name = o.display_name || o.username || o.user_id;
                const active = o.user_id === scopedOpponent;
                return (
                  <Pressable
                    key={o.user_id}
                    testID={`trades.team-picker.${o.user_id}`}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                    accessibilityLabel={name}
                    onPress={() =>
                      sheetTargetingOn
                        ? pickSheetOpponent(o.user_id, name)
                        : pickScopedTeam(o.user_id, name)
                    }
                    style={({ pressed }) => [
                      styles.teamPickerRow,
                      pressed && { backgroundColor: ink.ink3 },
                    ]}
                  >
                    <Text style={type.title}>{name}</Text>
                    {active ? (
                      <Icon name="check" size={16} color={ice.base} />
                    ) : (
                      <Icon name="chevron-right" size={16} color={chalk.dim} />
                    )}
                  </Pressable>
                );
              })}
              {teamPickerOpponents.length === 0 ? (
                <Text style={styles.fairnessHint}>No league-mates found.</Text>
              ) : null}
            </ScrollView>
          )}
        </View>
      </Modal>

      {/* #269 — league picker, reused wholesale from the global TopBar
          instance (same component, own local visibility here). Opened only
          from the sheet's League row; closes back into the sheet via
          closeLeaguePicker. No onAddLeague — that flow stays reachable from
          TopBar, which is always mounted. */}
      <LeagueSwitcherSheet visible={leaguePickerOpen} onClose={closeLeaguePicker} />

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

      {/* Swap-suggestions sheet (2026-07-27 player-changer) — the
          calculator's counter-suggestion eveners served per deck-card
          asset. "Browse full roster" hands the same asset off to the
          classic #86 swap sheet above. */}
      <SwapSuggestSheet
        visible={!!suggestTarget}
        replacing={suggestTarget?.player ?? null}
        suggestions={swapSuggestions}
        loading={suggestQuery.isLoading}
        error={suggestQuery.isError}
        onPick={handleSuggestPick}
        leagueId={leagueId}
        onBrowseRoster={() => {
          if (suggestTarget) {
            setSwapTarget(suggestTarget);
            setSuggestTarget(null);
          }
        }}
        onClose={() => setSuggestTarget(null)}
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
        // Both queries are ENABLED by this picker opening (see their
        // `targetPickerOpen` guards), so on a cold deck they start from zero
        // here — without this the sheet would assert "No players match."
        // while the pool is still in flight.
        loading={valuesQuery.isLoading || rostersQuery.isLoading}
        ownerBoardValue={(p) => p.base}
        // #277 — target-picker rows show the tier label, not the numeric
        // (deferred here because the tier-pass agent didn't own this file).
        tierOf={(p) => (p.pos === 'PICK' ? null : valueById.get(p.id)?.tier ?? null)}
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
        onClose={() => {
          setTargetPickerOpen(false);
          // #257 — hand back to the full sheet if that's where this
          // picker was opened from (see the `full.targeting.onAdd`
          // wrapper above the Modal mounts).
          if (pickerReturnsToSheet) {
            setPickerReturnsToSheet(false);
            setDnaSheetOpen(true);
          }
        }}
      />

      {/* Item 8 — save-moment Apple ask (ADR-006 honest framing). */}
      <AppleSaveMomentSheet
        visible={!!appleAsk}
        trigger={appleAsk ?? 'like'}
        onClose={closeAppleAsk}
      />

      {/* S3 PRD-02 (ux.player_context_menu) — shared long-press menu.
          menuTarget is only ever set while the flag is on. */}
      <PlayerContextMenu
        visible={!!menuTarget}
        player={menuTarget?.player ?? null}
        actions={menuTarget ? menuActionsFor(menuTarget) : []}
        onClose={() => setMenuTarget(null)}
      />

      {/* S4 PRD-01 (ux.help_surface) — "How trades are priced" in place. */}
      {helpOn ? (
        <HelpSheet
          visible={pricingHelpOpen}
          title="How trades are priced"
          body={
            'Every trade is priced on two boards — yours and your ' +
            "leaguemate's. A trade surfaces when each side gives up less " +
            'value on their own board than they get back; the fairness ' +
            'meter compares the two packages by value. Rank more players ' +
            'and trades get priced off your board instead of consensus.'
          }
          readMoreUrl={`${getBaseUrl()}/ranking-method.html`}
          topic="trade_pricing"
          onClose={() => setPricingHelpOpen(false)}
        />
      ) : null}
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

// ── PackageToggle — #174 "Trade as one package" ─────────────────────
// Chalkline binary-slider construction (same track/thumb as the fairness
// toggle). Rendered only with 2+ pinned give players; ON sends
// pinned_give_mode='all' so every idea carries the whole package.
function PackageToggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <Pressable
      testID="trades.package-toggle"
      accessibilityRole="switch"
      accessibilityState={{ checked: on }}
      accessibilityLabel="Trade as one package"
      onPress={onToggle}
      style={styles.packageToggleRow}
    >
      <View style={styles.fairnessSliderTap} pointerEvents="none">
        <View style={styles.fairnessTrack} />
        <View
          style={[
            styles.fairnessThumb,
            on ? styles.fairnessThumbOn : styles.fairnessThumbOff,
          ]}
        />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={type.body}>Trade as one package</Text>
        <Text style={styles.fairnessHint}>
          {on
            ? 'Every idea sends ALL your trade-away players together.'
            : 'Ideas send at least one of your trade-away players.'}
        </Text>
      </View>
    </Pressable>
  );
}

// ── SwipableTopCard — Tinder-style gesture on the top card only ─────
interface SwipableProps {
  /** #357 — host-fetched impact for the fronted card (see useCardImpact).
   *  Only SwipableTopCard receives it; peek cards render without it. */
  cardImpact?: CardImpactState | null;
  card: TradeCard;
  // #107/#110 — reports the card's laid-out height so the deck can clip
  // the behind-card peek to the top card's bounds. onLayout height is the
  // pre-transform layout box, so the swipe translation never re-fires it.
  onCardLayout: (e: LayoutChangeEvent) => void;
  onLike: () => void;
  onPass: () => void;
  // #169 — disables the card's in-card Pass/Like row while a swipe
  // mutation is in flight (the same condition the old below-deck row used).
  dispositionDisabled?: boolean;
  // Decline-reason capture (flag `feedback.decline_reasons`) — pass-through
  // to TradeCard's `disposition.reasons`. Present ⇒ the ✕ is replaced by the
  // three layer-1 tiles; absent ⇒ today's ✓/✕ row, unchanged.
  declineReasons?: DeclineReasonPanelProps;
  untouchableIds?: ReadonlySet<string>;
  onToggleUntouchable?: (player: Player) => void;
  // Player-swap (feedback #86) — pass-throughs to TradeCard.
  onSwapPlayer?: (player: Player, side: 'give' | 'receive') => void;
  // Shared context menu (S3 PRD-02, ux.player_context_menu) — pass-through.
  onPlayerMenu?: (player: Player, side: 'give' | 'receive') => void;
  repricing?: boolean;
  // FB-47 — pass-through to TradeCard's partner-fit line copy.
  fitTargetPositions?: string[];
  // #186 — pass-through: pin one side + regenerate ("keep this side").
  onKeepSide?: (side: 'give' | 'receive') => void;
  // #190 — pass-through: open the manual calculator prefilled.
  onEditInCalculator?: () => void;
  // #194 — pass-through: remove one asset from the card and re-price.
  onRemoveAsset?: (player: Player, side: 'give' | 'receive') => void;
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
  cardImpact,
  onCardLayout,
  onLike,
  onPass,
  dispositionDisabled,
  declineReasons,
  untouchableIds,
  onToggleUntouchable,
  onSwapPlayer,
  onPlayerMenu,
  repricing,
  fitTargetPositions,
  onKeepSide,
  onEditInCalculator,
  onRemoveAsset,
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
        // S8 PRD-01 (inert a11y): the swipe gesture's power path — like/
        // pass as VoiceOver custom actions on the card itself, mirroring
        // the visible check/X buttons (identical advance() handlers).
        accessibilityActions={[
          { name: 'like', label: 'Like this trade' },
          { name: 'pass', label: 'Pass on this trade' },
        ]}
        onAccessibilityAction={({ nativeEvent }) => {
          if (nativeEvent.actionName === 'like') onLike();
          else if (nativeEvent.actionName === 'pass') onPass();
        }}
      >
        <TradeCardComp
          data={card}
          // #169 — the in-card Pass/Like row; top card only (the peek card
          // and every other mount get no `disposition`).
          disposition={{
            onPass,
            onLike,
            disabled: dispositionDisabled,
            reasons: declineReasons,
          }}
          untouchableIds={untouchableIds}
          onToggleUntouchable={onToggleUntouchable}
          onSwapPlayer={onSwapPlayer}
          onPlayerMenu={onPlayerMenu}
          repricing={repricing}
          fitTargetPositions={fitTargetPositions}
          onKeepSide={onKeepSide}
          onEditInCalculator={onEditInCalculator}
          onRemoveAsset={onRemoveAsset}
          cardImpact={cardImpact}
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
  // #182 — explore-row construction (mirrors LeagueScreen's Explore list).
  exploreSection: {
    marginTop: space.lg,
  },
  exploreRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  exploreMain: { flex: 1, gap: 2 },
  exploreSub: { color: chalk.dim },
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: 96 },
  // #224 — classic-home in-page title (same tier as the hub's page title).
  pageTitle: { ...type.heading },
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
  // S4 PRD-01 — TickLabel + ⓘ pair (flag ux.help_surface only).
  helpLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
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
  // #156 finish item 1 — two-column FOR/AWAY board (Specific Player mode).
  // Mirrors mockups/trade-finding-hub variant B: ink-1 columns with a 2px
  // semantic top rule (pos-green = incoming, flare = outgoing — both data
  // encodings, not actions per ADR-005), mini chips, dashed add button.
  playerBoard: {
    flexDirection: 'row',
    gap: space.sm,
  },
  boardCol: {
    flex: 1,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    padding: space.md,
    gap: space.sm,
    minHeight: 120,
  },
  boardColFor: { borderTopWidth: 2, borderTopColor: semantic.pos },
  boardColAway: { borderTopWidth: 2, borderTopColor: flare.base },
  boardColH: {
    ...type.label,
  },
  boardColHFor: { color: semantic.pos },
  boardColHAway: { color: flare.base },
  boardMini: {
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.sm,
    borderRadius: radii.sm,
    backgroundColor: ink.ink2,
  },
  boardMiniText: { ...type.bodySm, color: chalk.base, flex: 1 },
  boardPosDot: { width: 7, height: 7, borderRadius: radii.xs },
  // #243 — single-pin collapsed controls: one-line pin summary in a thin
  // card shell (the chalkline Card's fixed space.lg body padding would
  // defeat the collapse — this reuses its surface/border/radius tokens
  // with a 44pt row, matching the approved mock's pinRowCard).
  pinSummaryCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 44,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
  },
  pinSummaryText: { ...type.bodySm, color: chalk.base, flex: 1 },
  pinSummaryName: { fontFamily: fonts.uiSemi },
  pinSummaryEditTap: { minHeight: 44, justifyContent: 'center' },
  pinSummaryEdit: { ...type.bodySm, color: ice.base, fontFamily: fonts.uiSemi },
  boardAddBtn: {
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
  },
  boardAddText: { ...type.bodySm, color: chalk.dim },
  // #174 — "Trade as one package" toggle row.
  packageToggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.xs,
  },
  // #156 finish item 4 — in-screen team picker sheet (mirrors the hub's).
  teamPickerBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  teamPickerSheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    // #242 — tall enough that a 12-team league's 11 manager rows fit
    // without scrolling on modern iPhones; scrolling remains only as
    // overflow for very large leagues / small screens.
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.lg,
    gap: space.sm,
    ...shadowSheet,
  },
  teamPickerGrabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.xs,
  },
  // #242 — size to content (the fixed 360pt cap forced a 12-team league to
  // scroll); the sheet's maxHeight is the only bound, and flexShrink lets
  // the list compress into it (and scroll) when content exceeds it.
  teamPickerScroll: { flexGrow: 0, flexShrink: 1, marginTop: space.sm },
  teamPickerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.md,
    paddingHorizontal: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
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
  // #257 — "Preferences changed" refresh strip. Mirrors OutlookBiasReceipt's
  // tick + text construction; ice (not flare) since tapping it is an
  // action, not just information.
  prefsChangedStrip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: 10,
    paddingVertical: space.sm,
    marginBottom: space.md,
  },
  prefsChangedTick: { width: 3, height: 12, backgroundColor: ice.base },
  prefsChangedText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
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
  // P0-2 — the ONLY red headline in the deck slot. Same display ramp as
  // emptyTitle so the failure state reads in the same voice as "DECK DONE";
  // semantic.neg is what makes it non-confusable with a valid empty state at
  // a glance, before the copy is even read.
  deckErrorTitle: {
    ...type.heading,
    textAlign: 'center',
    color: semantic.neg,
  },
  // P0-2 — host view for the mode-bar measurement. `gap` REPLICATES the
  // ScrollView content container's gap between the two slots this wrapper
  // now contains; without it the strip would sit flush against the chip row.
  modeBarWrap: { gap: space.lg },
  emptyBody: {
    ...type.bodySm,
    textAlign: 'center',
  },
  // F10 — deck-done summary card. Tallies are data numerals → Plex Mono.
  summaryTally: {
    ...type.data,
    color: chalk.base,
    textAlign: 'center',
  },
  summaryBtnRow: {
    flexDirection: 'row',
    gap: space.sm,
    marginTop: space.xs,
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
  // F3 (deck.fatigue) — deck header honoring note. Same quiet ink-2 bar
  // family as the banners above; text-only actions, no icons.
  suppressionNote: {
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
  suppressionNoteText: {
    ...type.bodySm,
    color: chalk.base,
    fontFamily: fonts.uiSemi,
    flex: 1,
    minWidth: 0,
  },
  suppressionNoteUndo: {
    ...type.bodySm,
    color: ice.base,
    fontFamily: fonts.uiSemi,
  },
  suppressionNoteDismiss: {
    ...type.bodySm,
    color: chalk.dim,
    fontFamily: fonts.uiSemi,
  },
  // F9 (deck.first_session) — board-sourced deck header. Same quiet ink-2
  // bar family as the F3 suppression note above (mirrored styling per the
  // PRD); flare border = informational highlight, matching the quickset
  // diff banner's "your board changed" precedent. Stacks ABOVE the F3
  // note when both render.
  boardRefreshNote: {
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    marginBottom: space.md,
  },
  boardRefreshText: {
    ...type.bodySm,
    color: chalk.base,
    fontFamily: fonts.uiSemi,
  },
  // F9 — adaptation-moment inline card title (body copy reuses emptyBody).
  adaptationTitle: {
    ...type.title,
    textAlign: 'center',
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

  // FB-05 — the check / x disposition row moved inside the card (#169,
  // TradeCard's `disposition` prop). Only the shared in-flight opacity
  // stays here — the Bad-trade flag below the deck still uses it.
  dispositionDisabled: {
    opacity: 0.45,
  },
});
