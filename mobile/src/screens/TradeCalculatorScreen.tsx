import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQuery } from '@tanstack/react-query';

import type { CalcPlayer, CalcPos } from '../data/calcTypes';
import {
  CalcSuggestion,
  evalFromConsensus,
  rankAddOnCandidates,
  rankPackageCandidates,
} from '../utils/tradeCalcMath';
import {
  evaluateTrade as evaluateTradeApi,
  evaluateTrades,
  getTradeValues,
  type TradeProbe,
} from '../api/calc';
import TradeSide from '../components/TradeSide';
import ConsensusVerdictCard from '../components/ConsensusVerdictCard';
import ShareTradeImage, { type ShareAsset } from '../components/ShareTradeImage';
import SuggestionCard from '../components/SuggestionCard';
import PlayerPickerModal from '../components/PlayerPickerModal';
import Toast from '../components/Toast';
import { Button, Card, Icon, TickLabel } from '../components/chalkline';
import { haptics } from '../utils/haptics';
import { track } from '../api/events';
import { resolveShareUrl } from '../utils/shareLinks';
import { chalk, fonts, ice, ink, radii, semantic, space, type } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { useFinderTargets } from '../state/useFinderTargets';
import { queueTradeForOpponent, type CalcQueueReason } from '../api/trades';
import {
  calcTourHandOffToDeck,
  calcTourScreenBlurred,
  startCalcTour,
} from '../utils/calcTour';
import { advanceGuideIfActive, guideV2Active, guidedAvatarActive } from '../state/useGuide';
import { registerGuideTarget, unregisterGuideTarget } from '../state/guideTargets';
import { useFlag } from '../state/useFeatureFlags';
import InLeagueCalculator from '../components/InLeagueCalculator';
import type { Player, ScoringFormat, Tier } from '../shared/types';

// Triage undo (S3 PRD-03, flag ux.swipe_undo): how long the cleared-trade
// snapshot (and its Undo toast) is held. Pure local state — nothing to POST.
const UNDO_HOLD_MS = 5000;

// Manual Trade Calculator. Two modes:
//   'live'   — REAL consensus values from the backend's universal pool.
//              Verdicts are server-authoritative (POST /api/trade/evaluate
//              reuses the finder's _fairness_v3), per the plan doc
//              docs/plans/manual-trade-calculator-plan.md. No login needed.
//              This is the league-free entry point #310 requires.
//   'league' — InLeagueCalculator, mounted below. Needs a real league.
//
// A third mode, 'demo' (a seeded mock dual-board league), was REMOVED on
// 2026-08-22 — feedback #384, operator: "let's also remove the demo calc,
// it's pointless". Its fixture module `data/tradeCalcMock.ts` went with it;
// the two types it also exported live on in `data/calcTypes.ts`.
// NOTE: this is unrelated to the demo SESSION (/api/session/demo,
// useSession.isDemo, onboarding.demo_bridge), which is untouched.

// Persisted draft trade — survives leaving the Trades stack / app restart.
const DRAFT_KEY = 'ftf:tradecalc:v1';

// Live-mode suggestion search runs over the top-N pool players (combos over
// the full ~500-player universe would be wasteful for no ranking benefit;
// 40 keeps the 1–3-piece combo scan around ~10k evaluations per edit).
const LIVE_SUGGEST_POOL = 40;

type CalcMode = 'live' | 'league';

const FORMATS: { key: ScoringFormat; label: string }[] = [
  { key: '1qb_ppr', label: '1QB PPR' },
  { key: 'sf_tep', label: 'SF TEP' },
];

/** Debounce list changes so the evaluate call fires ~250ms after the last tap. */
function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

// #384 W6-A — the ✓ cell's refusal copy, one line per server reason
// (D-152; the enum is a cross-client invariant). Every line names WHOSE
// preference refused it and why, because the alternative — a generic
// "couldn't queue that" — is the dishonest state the cell was disabled to
// avoid. `name` is the counterparty's username, already @-less.
function queueRefusalLine(reason: CalcQueueReason | undefined, name: string): string {
  switch (reason) {
    case 'opponent_untouchable':
      return `@${name} has someone in this trade marked untouchable.`;
    case 'opponent_not_interested':
      return `@${name} isn't interested in one of the players you're offering.`;
    case 'fails_fairness_floor':
      return `@${name}'s board reads this as a loss for them, so it won't surface.`;
    case 'assets_not_on_roster':
      return 'Those assets are no longer on the rosters this trade needs.';
    case 'not_league_member':
      return `@${name} isn't in this league.`;
    case 'likes_you_off':
      return 'Queueing trades for other managers is turned off right now.';
    default:
      return "Couldn't queue that. Try again.";
  }
}

// #384 ruling 2 — the canvas speaks CalcPlayer; the finder's pin store
// speaks Player. One mapping, here, so the two shapes meet in exactly one
// place. `pos` → `position` and `nflTeam` → `team` are the only renames;
// everything the pin store reads downstream is id + name + position.
function toFinderPlayer(p: CalcPlayer): Player {
  return {
    id: p.id,
    name: p.name,
    position: p.pos,
    team: p.nflTeam === '—' ? null : p.nflTeam,
    age: p.age,
  };
}

export default function TradeCalculatorScreen({ route, navigation }: any) {
  // #190 — deck "Edit in calculator": land in In-league mode with the
  // card's opponent + both sides preloaded. Route param only — no
  // calculator restructuring (InLeagueCalculator accepts the initial
  // values as optional props and owns everything after mount).
  const prefill = route?.params?.prefill as
    | { opponentUserId?: string; giveIds?: string[]; receiveIds?: string[] }
    | undefined;
  const [mode, setMode] = useState<CalcMode>(prefill ? 'league' : 'live');
  const calcMergedOn = useFlag('calc.merged_layout');

  // #384 W4 — the tour's first beat points at the In-league tab, so it needs
  // a measurable node. Registered here because the tabs live on this screen.
  const leagueTabRef = useRef<View | null>(null);
  useEffect(() => {
    registerGuideTarget('calc.mode-tab.league', leagueTabRef);
    return () => unregisterGuideTarget('calc.mode-tab.league');
  }, []);

  // #384 W5 — n11's CTA opens the outlook sheet, which lives inside
  // InLeagueCalculator. The SCREEN starts the tour, so the opener is threaded
  // up through a ref the component fills on mount rather than the runner
  // reaching into a component it does not own.
  const outlookOpenerRef = useRef<(() => void) | null>(null);
  // #166/#167 — default to the LEAGUE's detected scoring format (same rule
  // as InLeagueCalculator); the chips still override per-session, and the
  // saved-draft restore below keeps precedence over this initial value.
  const sessionFormat = useSession.getState().activeFormat;
  const [format, setFormat] = useState<ScoringFormat>(
    sessionFormat === 'sf_tep' || sessionFormat === '1qb_ppr' ? sessionFormat : '1qb_ppr',
  );
  // Live-mode trade state.
  const [liveSendIds, setLiveSendIds] = useState<string[]>([]);
  const [liveReceiveIds, setLiveReceiveIds] = useState<string[]>([]);
  const [picker, setPicker] = useState<'send' | 'receive' | null>(null);
  const [hydrated, setHydrated] = useState(false);

  // ── Teardown-remediation flags (default false — flag off is
  // byte-identical behavior) ──────────────────────────────────────────
  const swipeUndoOn = useFlag('ux.swipe_undo');           // S3 PRD-03
  const shareLandingOn = useFlag('growth.share_landing'); // S7 PRD-01

  // S3 PRD-03 — "Clear trade" snapshot + Undo toast.
  const [toast, setToast] = useState<{
    msg: string;
    // 'error' added by #384 W6-A for a failed queue POST — Toast has always
    // supported the tone; only this local union was narrower.
    tone?: 'success' | 'warn' | 'error';
    holdMs?: number;
    action?: { label: string; onPress: () => void };
  } | null>(null);

  // #190 — a NEW prefill arriving on an already-mounted screen (deck →
  // edit → back → edit another card) re-asserts In-league mode; the key
  // on InLeagueCalculator below remounts it with the new package.
  const prefillKey = prefill ? JSON.stringify(prefill) : null;
  useEffect(() => {
    if (prefillKey) setMode('league');
  }, [prefillKey]);

  // In-league mode (Mode B) is only offered when a real league is active.
  const league = useSession((s) => s.league);
  const user = useSession((s) => s.user);
  const hasLeague = !!(league?.league_id && user?.user_id);
  const modeTabs: { key: CalcMode; label: string }[] = [
    ...(hasLeague ? [{ key: 'league' as CalcMode, label: 'In league' }] : []),
    { key: 'live', label: 'Real values' },
  ];

  // Entry point 1 (operator): the tour auto-starts the moment the user lands
  // on the calculator, "since the first step brings them to the league
  // version". Guarded four ways — the merged layout must be on (the tour
  // describes controls that only exist there), a prefilled arrival is a
  // deliberate hand-off from a card and must not be hijacked, a user with no
  // league has no In-league page for the first beat to carry them to, and
  // startCalcTour itself refuses when the guided experience is off or the
  // tour has already been completed once.
  useEffect(() => {
    if (!calcMergedOn || prefill || !hasLeague) return;
    startCalcTour('auto', { openOutlook: () => outlookOpenerRef.current?.() });
    // Leaving the screen abandons the run — otherwise the tour hold would
    // outlive the tour and mute every interstitial app-wide. NOT an
    // unconditional stop: Find a Trade unmounts this screen too, and that
    // departure is the tour continuing onto the deck.
    return () => calcTourScreenBlurred();
  }, [calcMergedOn, prefill, hasLeague]);

  // Unmount is not the only way to leave. A push over this screen (or a tab
  // change) leaves it MOUNTED, and a tour narrating a page nobody is looking
  // at holds the mute for nothing. Find a Trade is the one departure that is
  // the tour continuing rather than ending — `calcTourHandOffToDeck()` in
  // `onFindATrade` is what tells the runner that.
  useEffect(() => {
    const unsub = navigation.addListener('blur', () => calcTourScreenBlurred());
    return unsub;
  }, [navigation]);

  // Restore the persisted draft once; live ids validate lazily as the pool
  // loads (below).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(DRAFT_KEY);
        if (!cancelled && raw) {
          const draft = JSON.parse(raw);
          // #190 — a prefilled launch stays in In-league mode; the stored
          // draft's mode must not yank the user away from the handed-off
          // package (list drafts still restore for later manual visits).
          // A draft saved before 2026-08-22 may carry mode 'demo'; that
          // mode no longer exists, so it falls through to the 'live'
          // default rather than restoring into nothing.
          if (!prefill && draft?.mode === 'live') setMode(draft.mode);
          if (draft?.format === '1qb_ppr' || draft?.format === 'sf_tep') setFormat(draft.format);
          if (Array.isArray(draft.liveSendIds)) setLiveSendIds(draft.liveSendIds.map(String));
          if (Array.isArray(draft.liveReceiveIds))
            setLiveReceiveIds(draft.liveReceiveIds.map(String));
        }
      } catch {
        /* corrupt/unavailable storage — start fresh */
      }
      if (!cancelled) setHydrated(true);
    })();
    return () => { cancelled = true; };
  }, []);

  // Fire-and-forget save; gated on hydration so the initial empty state
  // never clobbers a stored draft.
  useEffect(() => {
    if (!hydrated) return;
    AsyncStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({ mode, format, liveSendIds, liveReceiveIds }),
    ).catch(() => {});
  }, [hydrated, mode, format, liveSendIds, liveReceiveIds]);

  // ── Live mode: real consensus values ─────────────────────────────────
  const valuesQuery = useQuery({
    queryKey: ['calc-values', format],
    queryFn: ({ signal }) => getTradeValues(format, signal),
    enabled: mode === 'live',
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });

  const liveBoard = useMemo(
    () =>
      Object.fromEntries((valuesQuery.data?.players ?? []).map((r) => [r.id, r.value])) as Record<
        string,
        number
      >,
    [valuesQuery.data],
  );
  // #263 — server-computed pick-value tier per player (RankingService.
  // tier_for_elo over the RAW seed Elo — see api/calc.ts CalcValueRow.tier).
  // Reused as-is for row display; never re-derived from `liveBoard` above,
  // which is on the elo_to_value scale, not the tier bands' Elo scale.
  const liveTierById = useMemo(
    () =>
      Object.fromEntries((valuesQuery.data?.players ?? []).map((r) => [r.id, r.tier])) as Record<
        string,
        Tier
      >,
    [valuesQuery.data],
  );
  const livePlayers = useMemo<CalcPlayer[]>(
    () =>
      (valuesQuery.data?.players ?? []).map((r) => ({
        id: r.id,
        name: r.name,
        pos: r.position as CalcPos,
        nflTeam: r.team ?? '—',
        age: r.age ?? 0,
        base: r.value,
        // Carry the server's canonical pick verdict through; consumers
        // prefer it over the pos/team inference (cross-client-invariants
        // § Pick identity on the wire). Undefined pre-deploy — not false.
        isPick: r.is_pick,
      })),
    [valuesQuery.data],
  );
  const livePlayerById = useMemo(
    () => Object.fromEntries(livePlayers.map((p) => [p.id, p])),
    [livePlayers],
  );

  // Prune stale draft ids that aren't in the loaded pool (players fall out
  // of the universal pool when they lose their consensus value).
  useEffect(() => {
    if (mode !== 'live' || !valuesQuery.data) return;
    setLiveSendIds((ids) => {
      const kept = ids.filter((id) => liveBoard[id] !== undefined);
      return kept.length === ids.length ? ids : kept;
    });
    setLiveReceiveIds((ids) => {
      const kept = ids.filter((id) => liveBoard[id] !== undefined);
      return kept.length === ids.length ? ids : kept;
    });
  }, [mode, valuesQuery.data, liveBoard]);

  // Server-authoritative evaluation, debounced ~250ms behind list edits.
  const debSendIds = useDebounced(liveSendIds, 250);
  const debReceiveIds = useDebounced(liveReceiveIds, 250);
  const evalQuery = useQuery({
    queryKey: ['calc-eval', format, debSendIds.join('+'), debReceiveIds.join('+')],
    queryFn: ({ signal }) => evaluateTradeApi(debSendIds, debReceiveIds, format, signal),
    enabled: mode === 'live' && (debSendIds.length > 0 || debReceiveIds.length > 0),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // Suggestion search pool: top-N valued players not already in the trade.
  const livePoolIds = useMemo(() => {
    const chosen = new Set([...liveSendIds, ...liveReceiveIds]);
    return livePlayers
      .filter((p) => !chosen.has(p.id))
      .slice(0, LIVE_SUGGEST_POOL)
      .map((p) => p.id);
  }, [livePlayers, liveSendIds, liveReceiveIds]);

  // ── Live-mode suggestions (#78) ──────────────────────────────────────
  // The verdict above is server-authoritative, so suggestions must be too:
  // candidates are shortlisted by a local mirror of the server's package
  // math (rank heuristic only), then every shortlisted combo is CONFIRMED
  // through the same POST /api/trade/evaluate before it can render. Add-ons
  // additionally must strictly improve the server's point_ratio — a card
  // can never propose an add the evaluator scores as less fair.
  const liveEval = mode === 'live' ? evalQuery.data : undefined;
  const liveAddOnPlan = useMemo(() => {
    if (mode !== 'live' || !liveEval || debSendIds.length === 0 || debReceiveIds.length === 0)
      return null;
    if (liveEval.verdict !== 'unfair' || !liveEval.gap?.add_to) return null;
    const forSide: 'send' | 'receive' = liveEval.gap.add_to === 'give' ? 'send' : 'receive';
    const cands = rankAddOnCandidates(debSendIds, debReceiveIds, forSide, livePoolIds, liveBoard);
    return { forSide, cands };
  }, [mode, liveEval, debSendIds, debReceiveIds, livePoolIds, liveBoard]);

  const livePkgForSide: 'send' | 'receive' | null =
    debSendIds.length > 0 ? 'receive' : debReceiveIds.length > 0 ? 'send' : null;
  const livePkgPlan = useMemo(() => {
    if (mode !== 'live' || !livePkgForSide) return null;
    const fixed = livePkgForSide === 'receive' ? debSendIds : debReceiveIds;
    return {
      forSide: livePkgForSide,
      cands: rankPackageCandidates(fixed, livePkgForSide, livePoolIds, liveBoard),
    };
  }, [mode, livePkgForSide, debSendIds, debReceiveIds, livePoolIds, liveBoard]);

  const suggestQuery = useQuery({
    queryKey: [
      'calc-suggest',
      format,
      debSendIds.join('+'),
      debReceiveIds.join('+'),
      liveAddOnPlan?.cands.map((c) => c.ids.join('.')).join('+') ?? '',
      livePkgPlan?.cands.map((c) => c.ids.join('.')).join('+') ?? '',
    ],
    enabled:
      mode === 'live' &&
      // Wait for the base evaluation to settle so add-on improvement is
      // judged against the CURRENT trade's server ratio, never a stale one.
      !evalQuery.isFetching &&
      ((liveAddOnPlan?.cands.length ?? 0) > 0 || (livePkgPlan?.cands.length ?? 0) > 0),
    staleTime: 60_000,
    // No placeholderData: a suggestion confirmed for a DIFFERENT trade must
    // never linger on screen while the new confirmation is in flight.
    queryFn: async ({ signal }) => {
      const addCands = liveAddOnPlan?.cands ?? [];
      const pkgCands = livePkgPlan?.cands ?? [];
      const addProbes: TradeProbe[] = addCands.map((c) =>
        liveAddOnPlan!.forSide === 'send'
          ? { give: [...debSendIds, ...c.ids], receive: debReceiveIds }
          : { give: debSendIds, receive: [...debReceiveIds, ...c.ids] },
      );
      const pkgProbes: TradeProbe[] = pkgCands.map((c) =>
        livePkgPlan!.forSide === 'receive'
          ? { give: debSendIds, receive: c.ids }
          : { give: c.ids, receive: debReceiveIds },
      );
      const evals = await evaluateTrades([...addProbes, ...pkgProbes], format, signal);
      const currentRatio = liveEval?.point_ratio ?? null;

      const toSuggestion = (ids: string[], e: { give_value: number; receive_value: number; point_ratio: number | null }): CalcSuggestion => ({
        players: ids.map((id) => livePlayerById[id]).filter(Boolean),
        evaluation: evalFromConsensus(e),
        score: e.point_ratio ?? 0,
      });

      const addOns = addCands
        .map((c, i) => ({ c, e: evals[i] }))
        .filter(
          ({ e }) =>
            e !== null &&
            (e.verdict === 'fair' || e.verdict === 'even') &&
            e.point_ratio !== null &&
            (currentRatio === null || e.point_ratio > currentRatio),
        )
        .sort((a, b) => (b.e!.point_ratio ?? 0) - (a.e!.point_ratio ?? 0))
        .slice(0, 3)
        .map(({ c, e }) => toSuggestion(c.ids, e!));

      const packages = pkgCands
        .map((c, i) => ({ c, e: evals[addCands.length + i] }))
        .filter(({ e }) => e !== null && (e.verdict === 'fair' || e.verdict === 'even'))
        .sort((a, b) => (b.e!.point_ratio ?? 0) - (a.e!.point_ratio ?? 0))
        .slice(0, 4)
        .map(({ c, e }) => toSuggestion(c.ids, e!));

      return { addOns, packages };
    },
  });

  // Only 'live' reaches the body below — 'league' returns InLeagueCalculator
  // in the render. The `active*` aliases survive the demo removal because the
  // JSX below reads them in ~30 places; they are now plain live bindings.
  const activeSendIds = liveSendIds;
  const activeReceiveIds = liveReceiveIds;
  const setActiveSendIds = setLiveSendIds;
  const setActiveReceiveIds = setLiveReceiveIds;
  const activeBoard = liveBoard;
  const activeOtherBoard = liveBoard;
  const activePlayerById = livePlayerById;

  // #263 — pick-value tier for a player row, read from the server-computed
  // `liveTierById`. Picks (pos 'PICK') have no tier of their own; callers
  // fall back to the numeric value for them. The board argument became
  // unused when the demo boards were removed (they were the only caller
  // that needed a client-side tierForElo mapping) — kept so the ~6 call
  // sites in the JSX below stay untouched by this change.
  const tierFor = (_board: Record<string, number>, p: CalcPlayer): Tier | null => {
    if (p.pos === 'PICK') return null;
    return liveTierById[p.id] ?? null;
  };

  // What the sections below render: {forSide, suggestions}. Server-confirmed
  // (#78) — the local dual-board rankings died with the demo boards.
  const addOns =
    liveAddOnPlan && (suggestQuery.data?.addOns.length ?? 0) > 0
      ? { forSide: liveAddOnPlan.forSide, suggestions: suggestQuery.data!.addOns }
      : null;
  const suggested = livePkgForSide
    ? { forSide: livePkgForSide, suggestions: suggestQuery.data?.packages ?? [] }
    : null;
  // Empty-state only once confirmation has settled (no flicker mid-probe).
  const suggestSettled = !!valuesQuery.data && !suggestQuery.isFetching;

  const bothSides = activeSendIds.length > 0 && activeReceiveIds.length > 0;
  const anySide = activeSendIds.length > 0 || activeReceiveIds.length > 0;

  const switchMode = (m: CalcMode) => {
    if (m === mode) return;
    haptics.selection();
    setMode(m);
    track('calc_mode_switched', { mode: m }, 'TradeCalculator');
    // n10 is an `advance: 'action'` beat — tap-anywhere is off for it, so the
    // REAL switch is the only thing that can move it on. Only the switch INTO
    // league mode counts: that is what the beat asked for, and it is what
    // mounts the targets n12–n18 point at.
    if (m === 'league') advanceGuideIfActive('n10', 'action');
  };

  const switchFormat = (f: ScoringFormat) => {
    if (f === format) return;
    haptics.selection();
    setFormat(f); // selections survive — values re-fetch for the new format
  };

  const applySuggestion = (playerIds: string[], side: 'send' | 'receive') => {
    haptics.selection();
    if (side === 'receive') setActiveReceiveIds(playerIds);
    else setActiveSendIds(playerIds);
  };

  const applyAddOn = (playerIds: string[], side: 'send' | 'receive') => {
    haptics.selection();
    if (side === 'receive') setActiveReceiveIds((ids) => [...ids, ...playerIds]);
    else setActiveSendIds((ids) => [...ids, ...playerIds]);
  };

  const shareTrade = async () => {
    haptics.selection();
    const names = (ids: string[]) =>
      ids.map((id) => activePlayerById[id]?.name ?? id).join(', ');
    const lines = [
      `Trade idea (DTF Trade Calculator · ${FORMATS.find((f) => f.key === format)?.label})`,
      `Side A: ${names(liveSendIds)}`,
      `Side B: ${names(liveReceiveIds)}`,
      evalQuery.data
        ? `Consensus: ${Math.round(evalQuery.data.give_value).toLocaleString()} vs ${Math.round(evalQuery.data.receive_value).toLocaleString()}${
            evalQuery.data.point_ratio !== null
              ? ` (ratio ${Math.round(evalQuery.data.point_ratio * 100)}%)`
              : ''
          }`
        : '',
      evalQuery.data?.verdict ? `Verdict: ${evalQuery.data.verdict}` : '',
    ];
    // S7 PRD-01 (growth.share_landing): shares carry a landing URL with
    // ?ref= attribution.
    //
    // audit P1-2: a hand-built calculator trade DOES have a server object —
    // POST /api/share/package (backend/server.py:16999) mints one and
    // /s/p/<short_id> (backend/server.py:17048) renders it as an OG card
    // with a "Build your own trade" CTA. The comment that used to sit here
    // claimed no such route existed; it was written before the route landed
    // and was never revisited. resolveShareUrl walks the ladder and falls
    // back to the plain ?ref= root whenever the mint can't be made.
    // Flag off: legacy link-free message, byte for byte.
    let landing = false;
    if (shareLandingOn) {
      const resolved = await resolveShareUrl({
        // Real consensus ids. `isDemo` below is the demo SESSION
        // (/api/session/demo), which the mint server-refuses — unrelated to
        // the demo CALCULATOR mode removed in #384.
        giveIds: liveSendIds,
        receiveIds: liveReceiveIds,
        username: user?.username,
        enabled: shareLandingOn,
        isDemo: useSession.getState().isDemo,
        surface: 'calc_live',
        hasPickAssets: false,
        onOutcome: (outcome, give_n, receive_n) =>
          track(
            'share_package_created',
            { surface: 'calc_live', give_n, receive_n, outcome },
            'Calculator',
          ),
      });
      lines.push(`Build your own: ${resolved.url}`);
      landing = resolved.rung === 'package';
    }
    try {
      const res = await Share.share({ message: lines.filter(Boolean).join('\n') });
      // Dismissal-gated, matching TradesScreen's convention: the event
      // counts completed shares, not opened sheets. Safe to narrow silently
      // — calc_trade_shared has never landed a row (the name was absent
      // from ALLOWED_CLIENT_EVENTS, so ingest dropped every envelope
      // behind a 200), so there is no series to break.
      if (shareLandingOn && res.action !== Share.dismissedAction) {
        track(
          'calc_trade_shared',
          { mode, landing, surface: 'calc_live' },
          'Calculator',
        );
      }
    } catch {
      /* user dismissed or share unavailable — nothing to do */
    }
  };

  const liveReady = !!valuesQuery.data;

  // Share-as-image (DynastyDealer teardown 2026-07-26) — live mode only:
  // the share card needs a server verdict and the pool's names/positions.
  const liveShareAssets = (ids: string[]): ShareAsset[] =>
    ids
      .map((id) => livePlayerById[id])
      .filter(Boolean)
      .map((p) => ({
        id: p.id,
        name: p.name,
        position: p.pos,
        value: liveBoard[p.id] ?? 0,
        // #277/#280 — share card matches the on-screen TradeSide labels.
        tier: tierFor(liveBoard, p),
      }));
  const liveVerdictLine = (d: { verdict: string | null; favors: string | null }) =>
    d.verdict
      ? `Verdict: ${d.verdict}` +
        (d.favors === 'give'
          ? ' · Side A sends more'
          : d.favors === 'receive'
          ? ' · Side B sends more'
          : '')
      : 'Package value';

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      {/* S3 PRD-03 — Clear-trade Undo toast (only ever set flag-on). */}
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        holdMs={toast?.holdMs ?? 1500}
        action={toast?.action}
        onDismiss={() => setToast(null)}
      />
      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Mode switch: In-league vs league-free real consensus values. */}
        <View style={styles.modeRow}>
          {modeTabs.map((m) => {
            const active = mode === m.key;
            return (
              <Pressable
                key={m.key}
                // #384 W4 — the tour's first beat spotlights the In-league
                // tab; only that one needs a measurable node.
                ref={m.key === 'league' ? leagueTabRef : undefined}
                testID={`calc.mode-tab.${m.key}`}
                style={[styles.modeChip, active && styles.modeChipActive]}
                onPress={() => switchMode(m.key)}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
              >
                <Text style={[styles.modeText, active && styles.modeTextActive]}>{m.label}</Text>
              </Pressable>
            );
          })}
        </View>

        {/* #213 — one quiet path from the hand-built calculator to the
            finder. A single text-link row under the mode tabs covers every
            calculator surface (In-league, live) with one affordance —
            InLeagueCalculator is only ever mounted here, so this is the one
            "Find a trade" entry for the whole create-a-trade feature.
            Chalk-dim text-link tier (the "More ways to rank" precedent),
            never a button — the calculator's own actions keep primacy.

            #384 review §15: the merged In-league page carries its own Find a
            Trade in the action row, and that one honours Include players.
            Two entries where one bypasses the canvas is a trap, so this row
            steps aside there. */}
        {calcMergedOn && mode === 'league' ? null : (
        <Pressable
          testID="calc.find-a-trade"
          accessibilityRole="button"
          accessibilityLabel="Find a trade"
          accessibilityHint="Opens the trade finder for suggested trades"
          // popTo, not navigate: `TradesHome` has no `getId`, so a plain
          // navigate() with no `pop` PUSHES a second copy (routers 7.5.3
          // StackRouter) and leaves this screen mounted underneath.
          onPress={() => navigation.popTo('TradesHome')}
          hitSlop={8}
          style={styles.findTradeRow}
        >
          {({ pressed }) => (
            <Text style={[styles.findTradeText, pressed && { color: chalk.base }]}>
              Want ideas instead? Find a trade →
            </Text>
          )}
        </Pressable>
        )}

        {mode === 'league' && league && user ? (
          <InLeagueCalculator
            // #190 — remount when a different card is handed off so a
            // second "Edit in calculator" from the deck re-applies its
            // prefill (navigate() to a mounted route only swaps params).
            // …and remount on a LEAGUE switch too (#384 review §10): the
            // component holds opponentId/giveIds/receiveIds in local state,
            // so without this the new league renders the old league's canvas
            // and evaluates the old opponent id against it.
            key={
              prefill
                ? `prefill-${prefill.opponentUserId}-${(prefill.giveIds ?? []).join('.')}-${(prefill.receiveIds ?? []).join('.')}`
                : `manual-${league.league_id}`
            }
            leagueId={league.league_id}
            userId={user.user_id}
            initialOpponentId={prefill?.opponentUserId}
            initialGiveIds={prefill?.giveIds}
            initialReceiveIds={prefill?.receiveIds}
            // Entry point 2 (ruling 4): re-runnable from the top right.
            // startCalcTour returns false when the guided experience is off,
            // and the component renders no link without a handler — so the
            // affordance never appears unless it can actually do something.
            // guideV2Active() as well: with `onboarding.guide_v2` off the
            // spotlights, caps and degrade lines do not exist and the tour is
            // incoherent, so the link must not offer it (startCalcTour
            // refuses on the same pair). Users who tapped "Skip the tour"
            // (guideDismissed, folded into guidedAvatarActive) still see no
            // link — whether an explicit "Show me around" should override a
            // permanent opt-out is an open product question, not decided here.
            onShowMeAround={
              guidedAvatarActive() && guideV2Active()
                ? () =>
                    startCalcTour('show_me_around', {
                      openOutlook: () => outlookOpenerRef.current?.(),
                    })
                : undefined
            }
            outlookOpenerRef={outlookOpenerRef}
            // #384 W6-A (D-152) — the ✓ cell. POST /api/trades/queue records
            // the package as the caller's LIKE only when the likes-you
            // injector would actually mirror it into @partner's deck, so the
            // toast can be specific about who refused and why instead of the
            // generic failure the disabled cell used to stand in for.
            // The SCREEN owns the request, the toast and the analytics; the
            // component owns the canvas and the in-flight lock.
            onLikeTrade={async ({ giveIds, receiveIds, opponent }) => {
              let res: Awaited<ReturnType<typeof queueTradeForOpponent>> | null = null;
              try {
                res = await queueTradeForOpponent({
                  leagueId: league.league_id,
                  opponentUserId: opponent.userId,
                  giveIds,
                  receiveIds,
                });
              } catch {
                res = null;
              }
              const queued = !!res?.queued;
              // ONE event, both outcomes. `reason` is absent on a success —
              // the taxonomy allows the prop, the emitter omits it.
              track(
                'calc_trade_queued',
                queued ? { queued: true } : { queued: false, reason: res?.reason ?? 'error' },
                'TradeCalculator',
              );
              if (queued) {
                haptics.success();
                setToast({
                  msg: res?.already_queued
                    ? `Already queued for @${opponent.name}.`
                    : `Queued for @${opponent.name} — it'll show in their suggestions.`,
                  tone: 'success',
                });
              } else {
                haptics.warning();
                setToast({
                  msg: queueRefusalLine(res?.reason, opponent.name),
                  tone: res ? 'warn' : 'error',
                });
              }
            }}
            // #384 — the merged layout's own controls. The component owns
            // the canvas; the SCREEN owns navigation, so the finder hand-off
            // and the tour re-entry are passed in rather than reached for.
            onFindATrade={({ includePlayers, give, receive, opponent }) => {
              track(
                'calc_find_a_trade_tapped',
                {
                  include_players: includePlayers,
                  give_count: give.length,
                  receive_count: receive.length,
                  has_partner: !!opponent,
                },
                'TradeCalculator',
              );
              // n18 ("Now tap Find a Trade") is an action beat: this tap is
              // the only thing that can move it, and it must move BEFORE the
              // navigation so the runner parks instead of being blurred out.
              advanceGuideIfActive('n18', 'action');
              calcTourHandOffToDeck();
              // Ruling 2 (#384): ON ⇒ the finder MUST include the canvas
              // assets; OFF ⇒ the search is unconstrained by them.
              //
              // This writes the canvas into `useFinderTargets` — the SAME
              // pin store #186's "build around this side" and the deck's
              // generate payload already read — rather than inventing a
              // route param nothing consumes. `packageMode` is what makes
              // the contract literal: with 2+ give pins the served card's
              // give side must carry EVERY pinned player.
              const t = useFinderTargets.getState();
              if (includePlayers && (give.length || receive.length)) {
                t.setSide('give', give.map(toFinderPlayer));
                t.setSide('receive', receive.map(toFinderPlayer));
                t.setPackageMode(true);
              } else {
                // Unconstrained means unconstrained: a stale pin from an
                // earlier run would silently re-apply the constraint the
                // user just switched off.
                t.clear();
              }
              // #384 review §3/§6 — pins alone do not start a search and are
              // not scoped to the partner the user chose in the Team
              // dropdown. The #330 handoff is the path that already
              // regenerates on arrival; `origin` lets the deck tell a
              // calculator arrival from a league-rankings one, and it
              // regenerates on that origin even with no partner — a
              // partner-less canvas is an unscoped sweep, not "no search".
              useFinderTargets.getState().setHandoff({
                opponent: opponent ?? null,
                autoRun: true,
                origin: 'calculator',
                includePlayers,
              });
              // popTo, not navigate: without `pop` (and with no `getId` on
              // TradesHome) routers 7.5.3 PUSHES a second TradesHome, leaving
              // this screen mounted and the tour hold up behind it.
              navigation.popTo('TradesHome');
            }}
          />
        ) : (
        <>
        <>
            <TickLabel>Scoring format</TickLabel>
            <View style={styles.partnerRow}>
              {FORMATS.map((f) => {
                const active = format === f.key;
                return (
                  <Pressable
                    key={f.key}
                    style={[styles.partnerChip, active && styles.partnerChipActive]}
                    onPress={() => switchFormat(f.key)}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                  >
                    <Text style={[styles.partnerText, active && styles.partnerTextActive]}>
                      {f.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={styles.tendency}>
              Live consensus values from the FTF engine — no league or login needed.
            </Text>
            {valuesQuery.isLoading ? (
              <Card>
                <View style={styles.loadingRow}>
                  <ActivityIndicator color={ice.base} />
                  <Text style={type.bodySm}>Loading player values…</Text>
                </View>
              </Card>
            ) : valuesQuery.isError && !valuesQuery.data ? (
              <Card>
                <View style={styles.loadingRow}>
                  <Text style={[type.bodySm, { flex: 1 }]}>
                    Couldn't reach the value server. Retry.
                  </Text>
                  <Button
                    label="Retry"
                    variant="secondary"
                    compact
                    onPress={() => valuesQuery.refetch()}
                  />
                </View>
              </Card>
            ) : null}
        </>

        <TradeSide
          title="Side A sends"
          teamName="any player"
          players={activeSendIds.map((id) => activePlayerById[id]).filter(Boolean)}
          valueOf={(p) => activeBoard[p.id] ?? 0}
          tierOf={(p) => tierFor(activeBoard, p)}
          accent={semantic.neg}
          addTestID="calc.side-a-add"
          onAdd={() => setPicker('send')}
          onRemove={(id) => {
            haptics.warning();
            setActiveSendIds((ids) => ids.filter((x) => x !== id));
          }}
        />

        <View style={styles.swapRule}>
          <View style={styles.rule} />
          <Icon name="swap" size={16} />
          <View style={styles.rule} />
        </View>

        <TradeSide
          title="Side B sends"
          teamName="any player"
          players={activeReceiveIds.map((id) => activePlayerById[id]).filter(Boolean)}
          valueOf={(p) => activeBoard[p.id] ?? 0}
          tierOf={(p) => tierFor(activeBoard, p)}
          accent={semantic.pos}
          addTestID="calc.side-b-add"
          onAdd={() => setPicker('receive')}
          onRemove={(id) => {
            haptics.warning();
            setActiveReceiveIds((ids) => ids.filter((x) => x !== id));
          }}
        />

        {
          anySide && evalQuery.data ? (
            <View testID="calc.verdict">
              <ConsensusVerdictCard
                evaluation={evalQuery.data}
                stale={evalQuery.isFetching}
                // Eveners (2026-07-26): add the recommended asset(s) to the
                // side gap.add_to points at; the debounced evaluate re-run
                // refreshes or clears the rows.
                onAddEvener={(e) => {
                  const addTo = evalQuery.data?.gap?.add_to;
                  if (!addTo) return;
                  haptics.selection();
                  const ids = e.ids ?? [e.id];
                  const setter = addTo === 'give' ? setLiveSendIds : setLiveReceiveIds;
                  setter((cur) => [...cur, ...ids.filter((id) => !cur.includes(id))]);
                }}
              />
            </View>
          ) : anySide && evalQuery.isLoading ? (
            <Card>
              <View style={styles.loadingRow}>
                <ActivityIndicator color={ice.base} />
                <Text style={type.bodySm}>Evaluating…</Text>
              </View>
            </Card>
          ) : null}

        {addOns && addOns.suggestions.length > 0 ? (
          <View style={styles.suggestions}>
            <TickLabel color={semantic.warn}>
              {addOns.forSide === 'send'
                ? 'To balance — add to Side A'
                : 'To balance — add to Side B'}
            </TickLabel>
            {addOns.suggestions.map((s) => (
              <SuggestionCard
                key={'addon:' + s.players.map((p) => p.id).join('+')}
                suggestion={s}
                onApply={() => applyAddOn(s.players.map((p) => p.id), addOns.forSide)}
              />
            ))}
          </View>
        ) : null}

        {suggested && suggested.suggestions.length > 0 ? (
          <View style={styles.suggestions}>
            <TickLabel>
              {suggested.forSide === 'receive'
                ? 'Fair returns (consensus)'
                : 'Fair offers (consensus)'}
            </TickLabel>
            {suggested.suggestions.map((s) => (
              <SuggestionCard
                key={s.players.map((p) => p.id).join('+')}
                suggestion={s}
                onApply={() => applySuggestion(s.players.map((p) => p.id), suggested.forSide)}
              />
            ))}
          </View>
        ) : anySide && suggested && suggestSettled ? (
          <Text style={styles.noSuggestions}>
            No fair {suggested.forSide === 'receive' ? 'return' : 'offer'} found for that package —
            try adding or removing a piece.
          </Text>
        ) : null}

        {anySide ? (
          <View style={styles.actions}>
            {bothSides && evalQuery.data ? (
              <Button label="Share trade" variant="secondary" onPress={shareTrade} />
            ) : null}
            {/* Share-as-image (DynastyDealer teardown 2026-07-26): PNG of
                the verdict card via the native sheet; text fallback. */}
            {bothSides && evalQuery.data ? (
              <ShareTradeImage
                caption={`Trade idea · ${FORMATS.find((f) => f.key === format)?.label ?? ''}`}
                sendTitle="Side A sends"
                receiveTitle="Side B sends"
                sendAssets={liveShareAssets(liveSendIds)}
                receiveAssets={liveShareAssets(liveReceiveIds)}
                sendTotal={evalQuery.data.give_value}
                receiveTotal={evalQuery.data.receive_value}
                verdictLine={liveVerdictLine(evalQuery.data)}
                giveIds={liveSendIds}
                receiveIds={liveReceiveIds}
                surface="calc_live"
                // The live pool is the universal consensus pool — real
                // Sleeper player ids, never pick ids.
                hasPickAssets={false}
                fallbackText={[
                  `Trade idea (DTF Trade Calculator · ${FORMATS.find((f) => f.key === format)?.label})`,
                  `Side A: ${liveSendIds.map((id) => livePlayerById[id]?.name ?? id).join(', ')}`,
                  `Side B: ${liveReceiveIds.map((id) => livePlayerById[id]?.name ?? id).join(', ')}`,
                  `Consensus: ${Math.round(evalQuery.data.give_value).toLocaleString()} vs ${Math.round(evalQuery.data.receive_value).toLocaleString()}`,
                  liveVerdictLine(evalQuery.data),
                ].join('\n')}
              />
            ) : null}
            <Button
              label="Clear trade"
              testID="calc.clear-btn"
              variant="ghost"
              onPress={() => {
                haptics.warning();
                track('calc_cleared', { mode }, 'TradeCalculator');
                // S3 PRD-03 (ux.swipe_undo): snapshot the hand-built trade
                // and offer a 5s Undo — no server state, pure restore.
                if (swipeUndoOn) {
                  const prevSend = activeSendIds;
                  const prevReceive = activeReceiveIds;
                  const restoreSend = setActiveSendIds;
                  const restoreReceive = setActiveReceiveIds;
                  setToast({
                    msg: 'Trade cleared',
                    tone: 'success',
                    holdMs: UNDO_HOLD_MS,
                    action: {
                      label: 'Undo',
                      onPress: () => {
                        restoreSend(prevSend);
                        restoreReceive(prevReceive);
                        track('calc_clear_undone', undefined, 'Calculator');
                      },
                    },
                  });
                }
                setActiveSendIds([]);
                setActiveReceiveIds([]);
              }}
            />
          </View>
        ) : null}
        </>
        )}
      </ScrollView>

      {mode !== 'league' && (
      <>
      <PlayerPickerModal
        visible={picker === 'send'}
        title="Add to Side A"
        players={livePlayers}
        selectedIds={[...activeSendIds, ...activeReceiveIds]}
        loading={valuesQuery.isLoading}
        ownerBoardValue={(p: CalcPlayer) => activeBoard[p.id] ?? 0}
        tierOf={(p: CalcPlayer) => tierFor(activeBoard, p)}
        // The secondary "them" column and the Sell high / Target badges were
        // the DEMO's dual-board comparison — one consensus board has no
        // second opinion to show. Removed with the demo boards (#384).
        onPick={(p) => {
          haptics.selection();
          setActiveSendIds((ids) => [...ids, p.id]);
        }}
        onClose={() => setPicker(null)}
      />

      <PlayerPickerModal
        visible={picker === 'receive'}
        title="Add to Side B"
        players={livePlayers}
        selectedIds={[...activeSendIds, ...activeReceiveIds]}
        loading={valuesQuery.isLoading}
        ownerBoardValue={(p: CalcPlayer) => activeOtherBoard[p.id] ?? 0}
        tierOf={(p: CalcPlayer) => tierFor(activeOtherBoard, p)}
        onPick={(p) => {
          haptics.selection();
          setActiveReceiveIds((ids) => [...ids, p.id]);
        }}
        onClose={() => setPicker(null)}
      />
      </>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, gap: space.md, paddingBottom: space.xxl + space.lg },
  modeRow: {
    flexDirection: 'row',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    overflow: 'hidden',
  },
  modeChip: {
    flex: 1,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
  modeChipActive: { backgroundColor: ink.ink3 },
  modeText: { fontFamily: fonts.uiSemi, fontSize: 13, lineHeight: 18, color: chalk.dim },
  modeTextActive: { color: ice.base },
  // #213 — quiet finder hand-off row under the mode tabs.
  findTradeRow: { alignSelf: 'flex-end' },
  findTradeText: { ...type.bodySm, color: chalk.dim, fontFamily: fonts.uiSemi },
  partnerRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  partnerChip: {
    minHeight: 44,
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: 'transparent',
    paddingHorizontal: space.md,
  },
  partnerChipActive: { borderColor: ice.base },
  partnerText: { fontFamily: fonts.uiSemi, fontSize: 13, lineHeight: 18, color: chalk.dim },
  partnerTextActive: { color: chalk.base },
  tendency: { ...type.bodySm },
  loadingRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  swapRule: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
  },
  rule: { flex: 1, height: 1, backgroundColor: ink.line },
  suggestions: { gap: space.sm },
  noSuggestions: { ...type.bodySm },
  actions: { gap: space.sm, alignItems: 'center' },
});
