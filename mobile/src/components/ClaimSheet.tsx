import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Alert,
  Modal,
  ScrollView,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  AccessibilityInfo,
  findNodeHandle,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  semantic,
  space,
  radii,
  scrim,
  shadowSheet,
  type,
} from '../theme/chalkline';
import { Button, Icon, TickLabel } from './chalkline';
import PositionChip from './PositionChip';
import TierBadge from './TierBadge';
import type {
  FreeAgentDropCandidates,
  FreeAgentRosterCapacity,
  FreeAgentRow,
  FreeAgentsResponse,
  FreeAgentWaivers,
} from '../api/league';
import { isEspnLeague } from '../api/espn';
import { isMflLeague, isFleaflickerLeague } from '../api/platformLink';
import {
  attemptMove,
  capabilityOrNull,
  consentEcho,
  consentLinks,
  connectShownReason,
  consentShownReason,
  consentValidAt,
  consumeWithdrawal,
  faMoveGate,
  fetchConsentStep,
  fillTemplate,
  invalidateCapabilities,
  isSubmitCapability,
  moveCopy,
  rowMoveFields,
  termsChanged,
  trackFaMove,
  windowDateText,
  withTimeout,
  FA_MOVE_REREAD_WAIT_MS,
  FA_MOVE_STILL_SENDING_MS,
  type AttemptOutcome,
  type ConsentBlock,
  type ConsentEcho,
  type CopyVars,
  type FaMoveCapability,
  type FaMoveRow,
  type FaMoveSurface,
  type MoveKind,
} from '../api/faMove';
import { markClaimPending } from '../state/claimsPending';
import { useSession } from '../state/useSession';
import {
  actionBlockPinned,
  copyFns,
  dropListShown,
  initialView,
  moveSelection,
  planFailure,
  planKindChanged,
  planNotSent,
  planResponse,
  resumeAfterConnect,
  type Plan,
  type SheetView,
} from '../utils/claimSheetPlan';
import { openInSleeperApp } from '../utils/sleeperHandoff';
import { openPlatform, type ExternalSurface } from '../utils/openExternal';

// #179 claim sheet + the "where can an Add happen" resolver, shared by the
// Free Agents finder and Usage Trends (moved out of FreeAgentsScreen
// unchanged, 2026-10-10). The sheet only needs a player's identity; the
// board extras (pos_rank / tier / value) are optional because a Usage
// Trends row is not priced on the caller's board — absent, the header
// simply omits them. D1's per-row fields (move_kind / move_mode /
// move_line) ride along when the host has them.
export type ClaimTarget = Pick<FreeAgentRow, 'player_id' | 'name' | 'position' | 'team'> &
  Partial<Pick<FreeAgentRow, 'pos_rank' | 'tier' | 'value' | 'move_kind' | 'move_mode' | 'move_line'>>;

// #179 — where an "Add" can actually be executed, when the server sends no
// D1 capability (today's server). Sleeper leagues get the claim sheet's
// hand-off to the Sleeper app (utils/sleeperHandoff, #351). Platform-linked
// leagues (ESPN / MFL / Fleaflicker) are read-only imports today — no write
// path, so the Add affordance renders dimmed and explains why on tap.
// 'local' covers demo/local leagues that exist nowhere outside FTF. Hosts
// ask the capability first (api/faMove.ts faMoveOpensSheet).
export type AddPlatform = 'sleeper' | 'espn' | 'mfl' | 'fleaflicker' | 'local';

export function resolveAddPlatform(leagueId: string | undefined, isDemo: boolean): AddPlatform {
  if (!leagueId || isDemo) return 'local';
  if (isEspnLeague(leagueId)) return 'espn';
  if (isMflLeague(leagueId)) return 'mfl';
  if (isFleaflickerLeague(leagueId)) return 'fleaflicker';
  // Real Sleeper league ids are numeric; anything else is a local league.
  return /^\d+$/.test(leagueId) ? 'sleeper' : 'local';
}

const NO_ADD_REASON: Record<Exclude<AddPlatform, 'sleeper'>, { title: string; body: string }> = {
  espn: {
    title: "Can't add in ESPN leagues yet",
    body:
      "Roster moves for this ESPN league can't be made from Fleeced. " +
      'Open the ESPN Fantasy app to add this player.',
  },
  mfl: {
    title: "Can't add in MFL leagues yet",
    body:
      "Roster moves for this MFL league can't be made from Fleeced. " +
      'Open MFL to add this player.',
  },
  fleaflicker: {
    title: "Can't add in Fleaflicker leagues yet",
    body:
      "Roster moves for this Fleaflicker league can't be made from " +
      'Fleeced. Open Fleaflicker to add this player.',
  },
  local: {
    title: "Can't add in this league",
    body:
      'This league isn’t connected to a fantasy platform, so there’s ' +
      'no roster to add this player to.',
  },
};

// #179 — non-Sleeper Add handling: honest "why not" alert (read-only
// platform imports / local leagues). Sleeper leagues open the claim sheet
// instead (ClaimSheet below).
export function explainNoAdd(addPlatform: Exclude<AddPlatform, 'sleeper'>) {
  const reason = NO_ADD_REASON[addPlatform];
  Alert.alert(reason.title, reason.body);
}

// iOS drops a presentation that starts mid-dismissal: the sheet's slide-out
// finishes before the connect screen or Settings opens (UsageTrendsScreen's
// closeSheetFirst uses the same wait).
const SHEET_DISMISS_MS = 450;
// After the Modal's slide-in (about 300ms on iOS), so the flash is seen.
const FLASH_DELAY_MS = 400;
// The sheet's maxHeight below. Above half of it, the action block stops
// pinning and joins the end of the scroll (design-lead, accessibility sizes;
// utils/claimSheetPlan actionBlockPinned).
const SHEET_MAX_FRACTION = 0.85;

// #179 claim sheet. Two modes, both decided by the server (D1, scope §B1):
//  - Hand-off (no capability, today's server; `move.mode` 'handoff'): FTF
//    prepares the claim — FAAB bid sizing against the caller's live budget,
//    drop selection from the value-ascending candidate list — and the CTA
//    hands off to the Sleeper app (utils/sleeperHandoff), where the user
//    executes it. No steps block, no clipboard (operator, 2026-11-01).
//  - Submit (`move.mode` 'submit'): the named CTA is the move (D10), behind
//    connect → consent → move (api/faMove.ts faMoveGate), with the result
//    stated as the platform reports it. The decisions are pure functions in
//    utils/claimSheetPlan; this component renders them and runs their effects.
export default function ClaimSheet({
  row,
  leagueId,
  surface = 'unspecified',
  capacity,
  waivers,
  dropCandidates,
  move: openedWith,
  refetch,
  leagueName: hostLeagueName,
  onClose,
}: {
  row: ClaimTarget;
  leagueId: string;
  /** Which host opened the sheet, for the hand-off's ExternalTarget.surface. */
  surface?: ExternalSurface;
  capacity: FreeAgentRosterCapacity | null | undefined;
  waivers: FreeAgentWaivers | null | undefined;
  dropCandidates: FreeAgentDropCandidates | null | undefined;
  /** D1: the league's capability as the host read it at the Add tap.
   *  Absent (today's server): the hand-off, exactly as before. */
  move?: FaMoveCapability | null;
  /** D1: re-reads the host's FA list (after Connect, and on 10e). */
  refetch?: () => Promise<FreeAgentsResponse | undefined>;
  /** D1: the host's name for this league. The named CTA names it (R28.26,
   *  D10(a)); absent, the session's league list is asked. */
  leagueName?: string | null;
  onClose: () => void;
}) {
  const navigation = useNavigation<any>();
  const queryClient = useQueryClient();
  const { height: windowHeight } = useWindowDimensions();
  const sessionLeagueName = useSession(
    (s) =>
      (s.leagues ?? []).find((l) => l.league_id === leagueId)?.name ??
      (s.league?.league_id === leagueId ? s.league.league_name : null),
  );
  const leagueName = hostLeagueName || sessionLeagueName || null;

  const [bid, setBid] = useState('');
  const [dropId, setDropId] = useState<string | null>(null);

  // D1 state. The capability is held from the tap and changes only on this
  // sheet's own re-reads, so a background refetch never swaps the CTA under
  // the user's thumb.
  // No usable capability: nothing of it is used, `move.copy` and the row's
  // move_* fields included (fully legacy).
  const [move, setMove] = useState<FaMoveCapability | null>(() => capabilityOrNull(openedWith));
  const [rowMove, setRowMove] = useState<FaMoveRow>(() => rowMoveFields(openedWith, row));
  // A refusal's correction of move.connect (409 not_linked, say). null = the capability's.
  const [connect, setConnect] = useState<string | null>(null);
  // A refusal's or the consent GET's correction of move.consent_until.
  const [consentOverride, setConsentOverride] = useState<boolean | null>(null);
  const [view, setView] = useState<SheetView>(() => {
    const cap = capabilityOrNull(openedWith);
    return initialView(cap, rowMoveFields(cap, row), copyFns(cap, { league: leagueName ?? null, name: row.name }));
  });
  const [viewSeq, setViewSeq] = useState(0);
  const [ticked, setTicked] = useState(false);
  const [sending, setSending] = useState(false);
  const [loadingConsent, setLoadingConsent] = useState(false);
  const [stillSending, setStillSending] = useState(false);
  // Hidden, not destroyed, while the connect screen is up (contract §6).
  const [hidden, setHidden] = useState(false);
  const [serverRemaining, setServerRemaining] = useState<number | null>(null);
  // Bumped on each 10d, so the bid error takes VoiceOver focus every time.
  const [budgetSeq, setBudgetSeq] = useState(0);
  const [requireDrop, setRequireDrop] = useState(false);
  const [pinned, setPinned] = useState(true);

  const mountedRef = useRef(true);
  const sendingRef = useRef(false);
  const consentInFlightRef = useRef(false);
  const awaitingConnectRef = useRef(false);
  // The consent pair from a Make the move that never left the phone
  // (offline): the retry sends it again, with no second consent step.
  const pendingConsentRef = useRef<ConsentEcho | null>(null);
  // The copy_version last shown, for F5's "terms changed" line.
  const shownVersionRef = useRef<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);
  const focusRef = useRef<View>(null);
  const bidErrorRef = useRef<React.ElementRef<typeof Text>>(null);
  const dropYRef = useRef(0);

  const busy = sending || loadingConsent;
  const submitLayout = isSubmitCapability(move);
  const vars: CopyVars = { league: leagueName ?? null, name: row.name };
  const copy = copyFns(move, vars);
  const { platform, slot, fallback } = copy;
  // The only external opener this binary has is Sleeper's (#509, #379).
  const opensSleeper = platform === 'sleeper';
  // Both hosts pass their surface (check-sleeper-handoff H1).
  const analyticsSurface: FaMoveSurface = surface === 'usage_trends' ? 'usage_trends' : 'free_agents';
  // contract §1: move_kind null in submit mode names an add.
  const kind: MoveKind = rowMove.move_kind === 'claim' ? 'claim' : 'add';

  const faab = waivers?.type === 'faab' ? waivers.faab : null;
  const remaining = serverRemaining ?? faab?.remaining ?? null;
  const bidNum = bid === '' ? null : Number(bid);
  const bidTooHigh = bidNum != null && remaining != null && bidNum > remaining;

  const openSlots = capacity?.open_slots ?? null;
  const candidates = dropCandidates?.players ?? [];
  const untouchablesExcluded = dropCandidates?.untouchables_excluded ?? 0;
  // Open slots known and > 0 ⇒ no drop needed; 0 (or unknown, when we have
  // candidates) ⇒ show the least-valuable-first drop list; and always when
  // the server said a drop is required (10a).
  const showDropList = dropListShown({ openSlots, candidates: candidates.length, requireDrop });

  // Note (d): an add spends no FAAB, so in-app adds hide the bid; a claim
  // and every hand-off show it on FAAB leagues.
  const bidApplies = view.step === 'handoff' || kind === 'claim';

  // D10(a): the named CTA is the per-move confirmation, and it names exactly
  // what the request sends: one selection (the drop that is still in the
  // list, the claim's bid) feeds the CTA, the consent step's "This move"
  // line, the waiver lines and the request.
  const sel = moveSelection({
    rowName: row.name,
    kind,
    dropId,
    candidates,
    faab: !!faab,
    bid,
    copy: move?.copy,
    platform,
  });
  const ctaLabel = sel.ctaLabel;
  const needsDrop = (openSlots === 0 || requireDrop) && !sel.drop;

  useEffect(
    () => () => {
      mountedRef.current = false;
    },
    [],
  );

  // Flash the scroll bar once when the in-app move sheet opens, so a drop
  // list running under the pinned block reads as scrollable (ux-lead's #509
  // condition, carried by design-lead). The hand-off sheet is unchanged.
  useEffect(() => {
    if (!submitLayout) return;
    const t = setTimeout(() => scrollRef.current?.flashScrollIndicators(), FLASH_DELAY_MS);
    return () => clearTimeout(t);
    // Once, at open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A selected drop that a refresh took out of the candidates is cleared
  // (the selection already stopped naming or sending it).
  useEffect(() => {
    if (dropId && !candidates.some((c) => c.id === dropId)) setDropId(null);
  }, [dropId, candidates]);

  // State 7: the "still sending" line after ~8 s; the CTA stays busy.
  useEffect(() => {
    if (!sending) {
      setStillSending(false);
      return;
    }
    const t = setTimeout(() => {
      setStillSending(true);
      // iOS: say it, since the line appears without focus moving.
      AccessibilityInfo.announceForAccessibility(slot('still_sending') ?? '');
    }, FA_MOVE_STILL_SENDING_MS);
    return () => clearTimeout(t);
  }, [sending]);

  // VoiceOver focus moves to each new step's title or line (scope §C (e)).
  useEffect(() => {
    if (viewSeq === 0) return;
    const t = setTimeout(() => {
      const node = focusRef.current ? findNodeHandle(focusRef.current) : null;
      if (node != null) AccessibilityInfo.setAccessibilityFocus(node);
    }, 150);
    return () => clearTimeout(t);
  }, [viewSeq]);

  // 10d: VoiceOver focus to the bid error each time the server's budget
  // answer changes it.
  useEffect(() => {
    if (budgetSeq === 0 || !bidTooHigh) return;
    const t = setTimeout(() => {
      const node = bidErrorRef.current ? findNodeHandle(bidErrorRef.current) : null;
      if (node != null) AccessibilityInfo.setAccessibilityFocus(node);
    }, 150);
    return () => clearTimeout(t);
  }, [budgetSeq, bidTooHigh]);

  // A connect step at open is shown, so it is counted (C1: submit only).
  useEffect(() => {
    if (view.step === 'connect') trackConnectShown(move, connect, analyticsSurface);
    // Once, at open; later connect steps are counted where they're shown.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Back from the connect screen: re-read the capability (bounded), then
  // resume at the next step needed. Never sends by itself (consent.md
  // :84-88, contract §6). A failed re-read goes on as connected.
  const onConnectReturn = useRef<() => void>(() => {});
  onConnectReturn.current = () => {
    if (!awaitingConnectRef.current) return;
    awaitingConnectRef.current = false;
    void (async () => {
      const fresh = await refetchSafe();
      if (!mountedRef.current) return;
      const next = resumeAfterConnect(fresh, { move, row: rowMove, playerId: row.player_id });
      const nextCopy = copyFns(next.move, vars);
      setMove(next.move);
      setRowMove(next.row);
      setConnect(null);
      setConsentOverride(null);
      setHidden(false);
      const valid = consentValidAt(next.move?.consent_until, Date.now());
      const step = faMoveGate({ move: next.move, row: next.row, consentValid: valid, ticked: false });
      if (step === 'connect' || step === 'verify') {
        // A cancelled or failed sign-in: the same step, bid and drop intact (F2).
        show(initialView(next.move, next.row, nextCopy, true));
        trackConnectShown(next.move, null, analyticsSurface);
      } else if (step === 'consent') {
        await openConsent(false, next.move);
      } else {
        show(initialView(next.move, next.row, nextCopy));
      }
    })();
  };
  useEffect(() => navigation.addListener('focus', () => onConnectReturn.current()), [navigation]);

  function show(next: SheetView) {
    setView(next);
    setViewSeq((n) => n + 1);
  }

  // Every in-sheet re-read is bounded, so the sheet never stays busy offline.
  function refetchSafe(): Promise<FreeAgentsResponse | undefined> {
    return refetch ? withTimeout(refetch(), FA_MOVE_REREAD_WAIT_MS) : Promise.resolve(undefined);
  }

  // F12: a terminal result refreshes the FA list, drop list, FAAB and the
  // capability together (all one read), on both hosts' keys. Usage Trends'
  // prefetched capabilities go stale too, so its next Add routes legacy
  // until they're read again.
  function refreshList() {
    void queryClient.invalidateQueries({ queryKey: ['free-agents', leagueId] });
    void invalidateCapabilities(queryClient);
  }

  function requestClose() {
    // State 7 is not dismissible: backdrop, Cancel and the close request do
    // nothing until the result or the client timeout (ux-lead A1).
    if (busy) return;
    onClose();
  }

  const openSleeper = () => {
    // Opens the Sleeper app (`sleeper://`, the deepest proven rung; today
    // `bare`, so Sleeper's last-viewed screen). Not installed → the Get
    // Sleeper alert, never silent. The hand-off: the user finishes in Sleeper.
    // `hasDrop` feeds #528's sleeper_handoff_resolved `has_drop` (a drop picked).
    void openInSleeperApp({ target: 'add', leagueId, playerId: row.player_id, surface, hasDrop: dropId != null });
  };

  // The consent step's legal links (R15.8 "Terms · Privacy"), through the
  // shared external opener: it alerts when nothing opens, so no catch here.
  const openConsentLink = (url: string) => {
    void openPlatform({ platform, httpsUrl: url, surface, appMissing: 'https' });
  };

  // "Do it in Sleeper instead" (K-F4): the sheet switches to the hand-off,
  // bid and drop kept.
  function doInPlatform() {
    if (busy) return;
    show({ step: 'handoff', line: null });
  }

  function goConnect() {
    if (busy || !isSubmitCapability(move)) return;
    const target = move.league_platform;
    if (target !== 'sleeper' && target !== 'espn') return;
    awaitingConnectRef.current = true;
    setHidden(true);
    setTimeout(() => {
      if (target === 'sleeper') navigation.navigate('SleeperConnect');
      // No `reason: 'send'`: that copy is about sending trades.
      else navigation.navigate('EspnConnect');
    }, SHEET_DISMISS_MS);
  }

  function turnOff() {
    onClose();
    setTimeout(() => navigation.navigate('SettingsLeagues'), SHEET_DISMISS_MS);
  }

  // The consent step (5) (`sendIfValid`: the CTA was tapped, so a grant the
  // capability didn't know about sends now). NetInfo comes first: offline,
  // or a GET with no answer, is state 11 with nothing sent; after a connect
  // (no tap) it is just Ready. A 403 `verification_required` is state 4,
  // Verify, the same plan as the move route's 403. Only another server
  // failure or an incomplete block is F4's hand-off.
  async function openConsent(sendIfValid: boolean, m: FaMoveCapability | null = move) {
    // One consent read at a time: a same-frame double tap (state not yet
    // busy) can't fire two GETs, or two sends after them.
    if (!isSubmitCapability(m) || consentInFlightRef.current) return;
    consentInFlightRef.current = true;
    try {
      setLoadingConsent(true);
      const step = await fetchConsentStep(m.league_platform);
      if (!mountedRef.current) return;
      setLoadingConsent(false);
      switch (step.kind) {
        case 'offline':
        case 'not_sent':
          if (sendIfValid) apply(planNotSent(copy));
          else show({ step: 'ready' });
          return;
        case 'valid':
          setConsentOverride(true);
          if (sendIfValid) await send(null, true);
          else show({ step: 'ready' });
          return;
        case 'verify':
          apply(planFailure({ state: 'verify', errorCode: 'verification_required', status: 403, message: step.message }, copy));
          return;
        case 'consent':
          showConsent(step.block, m);
          return;
        case 'unavailable':
          show({ step: 'handoff', line: slot('unavailable_line') });
          return;
      }
    } finally {
      consentInFlightRef.current = false;
    }
  }

  function showConsent(block: ConsentBlock, m: FaMoveCapability | null = move) {
    if (!isSubmitCapability(m)) return;
    // The server says the terms changed, or this sheet showed another version (F5).
    const changed = termsChanged(block, shownVersionRef.current);
    // The server's reason when the block carries one, else the client's reading.
    const reason = consentShownReason(block, {
      consentUntil: m.consent_until,
      shownVersion: shownVersionRef.current,
      offeredVersion: block.copy_version,
      withdrawnHere: consumeWithdrawal(m.league_platform),
    });
    shownVersionRef.current = block.copy_version;
    // D10(d): the step names the move. If it can't, no consent is asked.
    if (fillTemplate(block.this_move, { cta: ctaLabel, league: leagueName ?? null }) == null) {
      show({ step: 'handoff', line: slot('unavailable_line') });
      return;
    }
    // Unticked, always: the tick never carries over (F5), nor does a consent
    // an offline tap was holding.
    pendingConsentRef.current = null;
    setTicked(false);
    show({ step: 'consent', block, termsChanged: changed });
    trackFaMove(m, 'fa_move_consent_shown', { surface: analyticsSurface, reason });
  }

  // The named CTA (state 6, and state 11's retry: a fresh tap).
  async function onNamedCta() {
    if (busy) return;
    if (pendingConsentRef.current) {
      await send(pendingConsentRef.current, false);
      return;
    }
    const valid = consentOverride ?? consentValidAt(move?.consent_until, Date.now());
    const step = faMoveGate({ move, row: rowMove, connect, consentValid: valid, ticked: false });
    if (step === 'submit') await send(null, true);
    else if (step === 'consent') await openConsent(true);
    else show(initialView(move, rowMove, copy));
  }

  // The one call site of the move API, behind the gate's submit /
  // submit_with_consent (F7). One tap is one attempt (D10(f)).
  async function send(echo: ConsentEcho | null, consentValid: boolean) {
    const step = faMoveGate({
      move,
      row: rowMove,
      connect,
      consentValid: echo ? false : consentValid,
      ticked: echo ? ticked : false,
    });
    if (step !== 'submit' && step !== 'submit_with_consent') return;
    if (!isSubmitCapability(move) || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    const outcome = await attemptMove({
      move,
      surface: analyticsSurface,
      // Exactly what the CTA named (the selection), plus the consent echo.
      request: {
        league_id: leagueId,
        add_player_id: row.player_id,
        ...sel.request,
        ...(echo ? { consent: echo } : {}),
      },
    });
    if (!mountedRef.current) return;
    // Busy until the outcome is shown: 10e's re-read must not leave the old
    // CTA tappable.
    try {
      await applyOutcome(outcome, echo);
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }

  async function applyOutcome(outcome: AttemptOutcome, echo: ConsentEcho | null) {
    if (!outcome.sent) {
      // Offline at the tap (F17): state 11, nothing sent. A consent the user
      // gave goes with the retry, since it never reached the server.
      if (echo) pendingConsentRef.current = echo;
      apply(planNotSent(copy));
      return;
    }
    pendingConsentRef.current = null;
    if ('response' in outcome) {
      apply(planResponse(outcome.response, copy));
      return;
    }
    const plan = planFailure(outcome.failure, copy);
    if (!plan.reread) {
      apply(plan);
      return;
    }
    // 10e: re-read the list (bounded); the CTA then names what the server will send.
    const fresh = await refetchSafe();
    if (!mountedRef.current) return;
    const next = planKindChanged(fresh, {
      move,
      kind,
      said: outcome.failure.message ?? null,
      connect,
      playerId: row.player_id,
      copy,
    });
    setMove(next.move);
    setRowMove(next.row);
    show(next.view);
  }

  // Runs a plan's effects, then shows its step.
  function apply(plan: Plan) {
    if (plan.connect !== undefined) setConnect(plan.connect);
    if (plan.consentOverride !== undefined) setConsentOverride(plan.consentOverride);
    if (plan.requireDrop) setRequireDrop(true);
    if (plan.clearDrop) setDropId(null);
    if (plan.serverRemaining !== undefined) {
      setServerRemaining(plan.serverRemaining);
      setBudgetSeq((n) => n + 1);
    }
    // F12: a terminal result refreshes the list, drop list, FAAB and capability.
    if (plan.refresh) refreshList();
    // State 9: the host's row reads "Claim pending" for the app session.
    if (plan.markPending) markClaimPending(leagueId, row.player_id);
    if (plan.trackConnect) trackConnectShown(move, plan.trackConnect, analyticsSurface);
    if (plan.consent) showConsent(plan.consent);
    else if (plan.view) show(plan.view);
    if (plan.scrollToDrop) scrollRef.current?.scrollTo({ y: dropYRef.current, animated: true });
  }

  // ── Pieces ────────────────────────────────────────────────────────────
  const headerText =
    view.step === 'handoff'
      ? `Claim ${row.name}`
      : slot(kind === 'claim' ? 'header_claim' : 'header_add') ?? row.name;
  const footerText = moveCopy(move?.copy, 'handoff_footer', vars, 'sleeper');

  // The hand-off CTA (#509): one mount, placed in the scroll (hand-off
  // sheet) or the pinned block (an in-app move sheet that fell back).
  const handoffCta = (
    <Button
      testID="fa-claim.open-sleeper"
      label="Open in Sleeper to claim"
      variant="primary"
      disabled={bidTooHigh}
      onPress={openSleeper}
    />
  );
  const doInSleeper = opensSleeper ? (
    <Button
      testID="fa-claim.do-in-sleeper"
      label={slot('do_in_platform') ?? ''}
      variant="secondary"
      disabled={busy}
      onPress={doInPlatform}
    />
  ) : null;

  const header = (
    <View style={sheetStyles.header}>
      <View style={sheetStyles.headerText}>
        <Text style={type.heading} numberOfLines={1} accessibilityRole="header">
          {headerText}
        </Text>
        <View style={sheetStyles.headerMeta}>
          <PositionChip position={row.position} size="sm" />
          <Text style={type.bodySm}>
            {row.team ?? 'FA'} · FA {row.position}
            {row.pos_rank}
          </Text>
          {/* #277 — tier label instead of the numeric board value;
              numeric fallback only for old-server payloads. */}
          {row.tier ? (
            // TierBadge hardcodes alignSelf:'flex-start'; re-center
            // it in this vertically-centered row.
            <View style={sheetStyles.tierSlot}>
              <TierBadge tier={row.tier} size="sm" />
            </View>
          ) : row.value != null ? (
            <Text style={sheetStyles.headerValue}>
              {Math.round(row.value).toLocaleString('en-US')}
            </Text>
          ) : null}
        </View>
      </View>
      {/* No Cancel on results; disabled, not hidden, while sending. */}
      {view.step === 'result' ? null : (
        <Button label="Cancel" variant="ghost" compact disabled={busy} onPress={requestClose} />
      )}
    </View>
  );

  // FAAB bid — only for FAAB leagues; priority-waiver leagues get the
  // honest one-liner instead. An in-app add has no bid (note (d)).
  const bidSection = !bidApplies ? null : faab ? (
    <View style={sheetStyles.section}>
      <TickLabel>FAAB BID</TickLabel>
      <View style={sheetStyles.bidRow}>
        <Text style={sheetStyles.bidCurrency}>$</Text>
        <TextInput
          testID="fa-claim.bid"
          value={bid}
          onChangeText={(t) => setBid(t.replace(/[^0-9]/g, ''))}
          keyboardType="number-pad"
          accessibilityLabel="FAAB bid amount"
          style={[sheetStyles.bidInput, bidTooHigh && sheetStyles.bidInputInvalid]}
          placeholder="0"
          placeholderTextColor={chalk.faint}
          maxLength={4}
          editable={!busy}
        />
        {remaining != null ? (
          <Text style={type.bodySm}>
            Budget: ${remaining.toLocaleString('en-US')} remaining
          </Text>
        ) : null}
      </View>
      {bidTooHigh ? (
        <Text ref={bidErrorRef} style={sheetStyles.bidError}>
          That's more than your ${remaining!.toLocaleString('en-US')}{' '}
          remaining — lower the bid.
        </Text>
      ) : null}
    </View>
  ) : waivers?.type === 'rolling' || waivers?.type === 'reverse_standings' ? (
    <View style={sheetStyles.section}>
      <Text style={type.bodySm}>
        This is a waiver priority league — no FAAB bid needed.
      </Text>
    </View>
  ) : null;

  const dropNotice = view.step === 'ready' ? view.dropNotice : undefined;
  // Drop selection — least valuable first (or the open-slots all-clear when
  // no drop is needed).
  const dropSection = (
    <View
      style={sheetStyles.section}
      onLayout={(e) => {
        dropYRef.current = e.nativeEvent.layout.y;
      }}
    >
      {!showDropList ? (
        openSlots !== null ? (
          <Text style={type.bodySm}>
            You have {openSlots} open roster{' '}
            {openSlots === 1 ? 'slot' : 'slots'} — no drop needed.
          </Text>
        ) : null
      ) : (
        <>
          <TickLabel>SELECT A PLAYER TO DROP</TickLabel>
          {dropNotice ? (
            <View ref={focusRef} accessible>
              <Text style={dropNotice.tone === 'neg' ? sheetStyles.negLine : sheetStyles.chalkLine}>
                {dropNotice.text}
              </Text>
            </View>
          ) : (
            <Text style={sheetStyles.sectionHint}>
              {openSlots === 0
                ? 'Your roster is full — least valuable first.'
                : 'If your roster is full, pick a drop — least valuable first.'}
            </Text>
          )}
          {candidates.map((c) => {
            const selected = c.id === dropId;
            return (
              <Pressable
                key={c.id}
                testID={`fa-claim.drop.${c.id}`}
                accessibilityRole="radio"
                accessibilityState={{ selected, disabled: busy }}
                accessibilityLabel={`Drop ${c.name}`}
                disabled={busy}
                onPress={() => setDropId(selected ? null : c.id)}
                style={({ pressed }) => [
                  sheetStyles.dropRow,
                  selected && sheetStyles.dropRowSelected,
                  pressed && { backgroundColor: ink.ink3 },
                ]}
              >
                <View style={[sheetStyles.radio, selected && sheetStyles.radioSelected]}>
                  {selected ? <View style={sheetStyles.radioDot} /> : null}
                </View>
                <PositionChip position={c.position} size="sm" />
                <Text style={sheetStyles.dropName} numberOfLines={1}>
                  {c.name}
                </Text>
                {/* #277 — tier label per drop candidate; numeric
                    fallback for old-server payloads. The list stays
                    value-ASCENDING (server order — unchanged). */}
                {c.tier ? (
                  <View style={sheetStyles.tierSlot}>
                    <TierBadge tier={c.tier} size="sm" />
                  </View>
                ) : (
                  <Text style={type.data}>
                    {Math.round(c.value).toLocaleString('en-US')}
                  </Text>
                )}
              </Pressable>
            );
          })}
          {candidates.length === 0 ? (
            <Text style={type.bodySm}>
              No droppable players found on your roster.
            </Text>
          ) : null}
          {untouchablesExcluded > 0 ? (
            <Text style={sheetStyles.untouchableNote}>
              {untouchablesExcluded === 1
                ? '1 untouchable player was'
                : `${untouchablesExcluded} untouchable players were`}{' '}
              left out of the drop suggestions.
            </Text>
          ) : null}
        </>
      )}
    </View>
  );

  // A step's own line, which takes VoiceOver focus when the step opens.
  const focusLine = (text: string | null | undefined, style: object) =>
    text ? (
      <View ref={focusRef} accessible>
        <Text style={style}>{text}</Text>
      </View>
    ) : null;

  const handoffLine = view.step === 'handoff' ? view.line : null;
  // State 1 and 14. Sleeper's opener only; another platform gets the line.
  const handoffBlock = (
    <>
      {focusLine(handoffLine ?? (opensSleeper ? null : slot('unavailable_line')), sheetStyles.chalkLine)}
      {opensSleeper ? handoffCta : null}
      {opensSleeper ? <Text style={sheetStyles.footer}>{footerText}</Text> : null}
    </>
  );

  // ── The in-app move's pinned action block (design-lead slot table) ──
  const windowOpen = isSubmitCapability(move) && consentValidAt(move.consent_until, Date.now());
  let actionBlock: React.ReactNode = null;
  if (view.step === 'handoff') {
    actionBlock = handoffBlock;
  } else if (view.step === 'ready') {
    // R28.26 / D10(a): the league is named beside the named CTA in every step
    // that shows it: the server's league_line, else "In {league}" with the
    // host's league name. A move whose league can't be named gets no named
    // CTA (the hand-off instead).
    const leagueLine = slot('league_line');
    actionBlock = !leagueLine ? handoffBlock : (
      <>
        {focusLine(view.ctaNotice?.text, view.ctaNotice?.tone === 'neg' ? sheetStyles.negLine : sheetStyles.chalkLine)}
        <Text style={sheetStyles.dimLine}>{leagueLine}</Text>
        {needsDrop ? <Text style={sheetStyles.dimLine}>{fallback('drop_to_make_room')}</Text> : null}
        {/* D10: the label names the move; it wraps, never truncates. While
            busy it keeps full brightness with its spinner and takes no tap
            (#364's busy rule: `loading`, not `disabled`). */}
        <Button
          testID="fa-claim.make-move"
          label={ctaLabel}
          variant="primary"
          loading={busy}
          disabled={needsDrop || (kind === 'claim' && bidTooHigh)}
          onPress={() => void onNamedCta()}
          style={sheetStyles.namedCta}
        />
        {stillSending ? <Text style={sheetStyles.dimLine}>{slot('still_sending')}</Text> : null}
        {/* A claim: the waiver line (with or without the drop), then the bid line when it has one. */}
        {sel.waiverLines.map((l, i) => (
          <Text key={i} style={sheetStyles.dimLine}>
            {l}
          </Text>
        ))}
        <Text style={sheetStyles.dimLine}>{slot('finality')}</Text>
        {windowOpen ? (
          <View style={sheetStyles.windowRow}>
            <Text style={sheetStyles.dimLine}>
              {slot('window_line', { date: windowDateText(move?.consent_until) })}
              {' · '}
            </Text>
            {/* Its own accessible button, not nested text (VoiceOver); dims
                while sending, like Cancel and "Do it in Sleeper instead". */}
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={slot('turn_off') ?? undefined}
              accessibilityState={{ disabled: busy }}
              disabled={busy}
              onPress={turnOff}
              hitSlop={8}
              style={busy ? sheetStyles.linkDisabled : undefined}
            >
              <Text style={[sheetStyles.dimLine, sheetStyles.inlineLink]}>{slot('turn_off')}</Text>
            </Pressable>
          </View>
        ) : null}
        {doInSleeper}
      </>
    );
  } else if (view.step === 'connect') {
    actionBlock = (
      <>
        {focusLine(view.line, sheetStyles.chalkLine)}
        {view.backedOut ? <Text style={sheetStyles.dimLine}>{fallback('not_connected')}</Text> : null}
        <Button
          testID="fa-claim.connect"
          label={view.verify ? 'Verify' : 'Connect'}
          variant="primary"
          disabled={busy}
          onPress={goConnect}
        />
        {doInSleeper}
      </>
    );
  } else if (view.step === 'consent') {
    actionBlock = (
      <>
        <Pressable
          testID="fa-claim.consent.box"
          accessibilityRole="checkbox"
          accessibilityState={{ checked: ticked, disabled: busy }}
          accessibilityLabel={view.block.checkbox_label}
          disabled={busy}
          onPress={() => setTicked((t) => !t)}
          style={sheetStyles.checkRow}
        >
          <View style={[sheetStyles.checkBox, ticked && sheetStyles.checkBoxOn]}>
            {ticked ? <Icon name="check" size={14} color={ice.base} /> : null}
          </View>
          <Text style={sheetStyles.checkLabel}>{view.block.checkbox_label}</Text>
        </Pressable>
        {/* Ticking never sends: this is the only send on the step (A5). */}
        <Button
          testID="fa-claim.make-move"
          label={view.block.button_label}
          variant="primary"
          loading={busy}
          disabled={!ticked}
          accessibilityHint={ticked ? undefined : fallback('tick_hint') ?? undefined}
          onPress={() => void send(consentEcho(view.block), false)}
        />
        {stillSending ? <Text style={sheetStyles.dimLine}>{slot('still_sending')}</Text> : null}
        <Button
          label={fallback('not_now') ?? ''}
          variant="ghost"
          disabled={busy}
          onPress={() => {
            pendingConsentRef.current = null;
            setTicked(false);
            show({ step: 'ready' });
          }}
        />
        {doInSleeper}
        {/* R15.8 v1 ends "[Make the move] · [Not now] — Terms · Privacy". */}
        <View style={sheetStyles.linksRow}>
          {consentLinks(view.block).map((l, i) => (
            <React.Fragment key={`${i}:${l.url}`}>
              {i > 0 ? <Text style={sheetStyles.dimLine}>·</Text> : null}
              <Pressable
                accessibilityRole="link"
                accessibilityHint={fallback('link_hint') ?? undefined}
                hitSlop={8}
                onPress={() => openConsentLink(l.url)}
              >
                <Text style={sheetStyles.linkText}>{l.label}</Text>
              </Pressable>
            </React.Fragment>
          ))}
        </View>
      </>
    );
  } else if (view.step === 'unsupported') {
    actionBlock = <Button label="Done" variant="primary" onPress={onClose} />;
  } else {
    const openLabel = fallback('open_in_platform') ?? '';
    const k = view.kind;
    actionBlock = (
      <>
        {k === 'unknown' && opensSleeper ? (
          <Button testID="fa-claim.do-in-sleeper" label={openLabel} variant="primary" onPress={openSleeper} />
        ) : null}
        {k === 'rejected' ? (
          <Button testID="fa-claim.connect" label="Connect again" variant="primary" onPress={goConnect} />
        ) : null}
        {k === 'rejected' ? doInSleeper : null}
        <Button
          label="Done"
          variant={k === 'unknown' ? 'secondary' : k === 'rejected' ? 'ghost' : 'primary'}
          onPress={onClose}
        />
        {(k === 'platform_refused' || k === 'unavailable' || k === 'neutral') && opensSleeper ? (
          <Button testID="fa-claim.do-in-sleeper" label={openLabel} variant="secondary" onPress={openSleeper} />
        ) : null}
      </>
    );
  }

  // The body above the action block: the consent text or the result panel
  // replace bid and drop (body swap); every other step keeps them.
  let body: React.ReactNode;
  if (view.step === 'consent') {
    const thisMove = fillTemplate(view.block.this_move, { cta: ctaLabel, league: leagueName ?? null });
    body = (
      <View style={sheetStyles.section} testID="fa-claim.consent">
        {view.termsChanged ? <Text style={sheetStyles.chalkLine}>{fallback('terms_changed')}</Text> : null}
        <View ref={focusRef} accessible>
          <Text style={type.title} accessibilityRole="header">
            {view.block.title}
          </Text>
        </View>
        {view.block.body.map((p, i) => (
          <Text key={i} style={sheetStyles.chalkLine}>
            {p}
          </Text>
        ))}
        {thisMove ? <Text style={sheetStyles.thisMove}>{thisMove}</Text> : null}
      </View>
    );
  } else if (view.step === 'unsupported') {
    // MFL / ESPN with no in-app path in this binary (contract §6): that
    // platform's NO_ADD_REASON, as the host's alert would say it.
    const reason = NO_ADD_REASON[platform === 'sleeper' ? 'local' : platform];
    body = (
      <View style={sheetStyles.result}>
        <View ref={focusRef} accessible>
          <Text style={type.title} accessibilityRole="header" testID="fa-claim.result">
            {reason.title}
          </Text>
        </View>
        <Text style={sheetStyles.dimLine}>{reason.body}</Text>
      </View>
    );
  } else if (view.step === 'result') {
    // Refusals in --neg; 8, 9, 12 and the neutral panel (contract §4) dim.
    const neg = view.kind !== 'added' && view.kind !== 'pending' && view.kind !== 'unknown' && view.kind !== 'neutral';
    body = (
      <View style={sheetStyles.result}>
        {view.kind === 'added' ? <Icon name="check" size={24} color={chalk.base} /> : null}
        {view.kind === 'unknown' ? <Icon name="info" size={24} color={semantic.warn} /> : null}
        <View ref={focusRef} accessible>
          <Text style={type.title} accessibilityRole="header" testID="fa-claim.result">
            {view.title}
          </Text>
        </View>
        {view.lines.map((l, i) => (
          <Text key={i} style={neg ? sheetStyles.negLine : sheetStyles.dimLine}>
            {l}
          </Text>
        ))}
      </View>
    );
  } else {
    body = (
      <>
        {bidSection}
        {dropSection}
      </>
    );
  }

  // ── The hand-off sheet: #509's shape, unchanged ──────────────────────
  if (!submitLayout) {
    return (
      <Modal visible={!hidden} transparent animationType="slide" onRequestClose={requestClose}>
        <Pressable
          style={sheetStyles.backdrop}
          onPress={requestClose}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={sheetStyles.sheet} testID="fa-claim.sheet">
          <SafeAreaView edges={['bottom']}>
            <View style={sheetStyles.grabber} />
            <ScrollView
              contentContainerStyle={sheetStyles.content}
              keyboardShouldPersistTaps="handled"
            >
              {header}
              {bidSection}
              {dropSection}
              {handoffBlock}
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>
    );
  }

  // ── The in-app move sheet: header / scrolling body / pinned action
  // block (ink-2, top hairline). At accessibility sizes, a block taller
  // than half the sheet joins the end of the scroll instead (design-lead).
  // The measured view is the block's content, the same in both parents, and
  // the decision has hysteresis (utils/claimSheetPlan actionBlockPinned).
  const unpinned = !pinned;
  const block = (
    <View style={unpinned ? sheetStyles.blockInScroll : sheetStyles.blockPinned}>
      <View
        style={sheetStyles.blockContent}
        onLayout={(e) => {
          const h = e.nativeEvent.layout.height;
          setPinned((p) => actionBlockPinned(p, h, windowHeight * SHEET_MAX_FRACTION));
        }}
      >
        {actionBlock}
      </View>
    </View>
  );
  const submitLayoutSheet = (
    <View style={sheetStyles.sheetPinned} testID="fa-claim.sheet">
      <SafeAreaView edges={['bottom']} style={sheetStyles.sheetBody}>
        <View style={sheetStyles.grabber} />
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={sheetStyles.content}
          keyboardShouldPersistTaps="handled"
        >
          {header}
          {body}
          {unpinned ? block : null}
        </ScrollView>
        {unpinned ? null : block}
      </SafeAreaView>
    </View>
  );
  return (
    <Modal visible={!hidden} transparent animationType="slide" onRequestClose={requestClose}>
      <Pressable
        style={sheetStyles.backdrop}
        onPress={requestClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      {/* The sheet rises above the number pad (a claim's bid). */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={sheetStyles.kav}
        pointerEvents="box-none"
      >
        {submitLayoutSheet}
      </KeyboardAvoidingView>
    </Modal>
  );
}

// fa_move_connect_shown {reason} (C1: submit only). An unknown connect
// value shows the plain connect step, and is recorded as `unknown`.
function trackConnectShown(move: FaMoveCapability | null, override: string | null, surface: FaMoveSurface) {
  trackFaMove(move, 'fa_move_connect_shown', { surface, reason: connectShownReason(override ?? move?.connect) });
}

// #179 claim sheet — construction mirrors SwapPlayerSheet (components.md →
// Sheets, modals, menus): ink-2 surface, top radius, grabber, sheet shadow.
const sheetStyles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    ...shadowSheet,
  },
  // D1: fills the Modal and bottom-aligns the in-app move sheet.
  // KeyboardAvoidingView pads by its own onLayout frame, which is
  // parent-relative, so it starts at the screen's top for the padding to
  // equal the keyboard's height.
  kav: { flex: 1, justifyContent: 'flex-end' },
  sheetPinned: {
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    ...shadowSheet,
  },
  // Lets the body shrink to the sheet's maxHeight; the ScrollView absorbs
  // the cut, so the pinned block stays on screen.
  sheetBody: { flexShrink: 1 },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
  },
  content: {
    paddingHorizontal: space.lg,
    paddingBottom: space.xl,
    gap: space.lg,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: space.md,
    paddingTop: space.sm,
  },
  headerText: { flex: 1, gap: space.xs },
  headerMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  headerValue: { ...type.data, color: chalk.base },
  // TierBadge hardcodes alignSelf:'flex-start'; these rows center children.
  tierSlot: { alignSelf: 'center' },

  section: { gap: space.sm },
  sectionHint: { ...type.bodySm, color: chalk.dim },

  bidRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  bidCurrency: { ...type.data, color: chalk.dim },
  bidInput: {
    ...type.data,
    fontSize: 16,
    color: chalk.base,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minWidth: 72,
    textAlign: 'right',
  },
  bidInputInvalid: { borderColor: semantic.neg },
  bidError: { ...type.bodySm, color: semantic.neg },

  dropRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    paddingHorizontal: space.sm,
    borderWidth: 1,
    borderColor: 'transparent',
    borderRadius: radii.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  dropRowSelected: {
    borderColor: ice.base,
    borderBottomWidth: 1,
    borderBottomColor: ice.base,
    backgroundColor: ink.ink3,
  },
  dropName: { ...type.title, flex: 1 },
  // Selection tick — square per the radius rule (no radius >8px outside
  // specced pills); radio semantics live in accessibilityRole/state.
  radio: {
    width: 18,
    height: 18,
    borderRadius: radii.xs,
    borderWidth: 1.5,
    borderColor: ink.lineStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioSelected: { borderColor: ice.base },
  radioDot: {
    width: 8,
    height: 8,
    borderRadius: 1,
    backgroundColor: ice.base,
  },
  untouchableNote: { ...type.bodySm, color: chalk.dim },
  footer: {
    ...type.bodySm,
    color: chalk.dim,
    textAlign: 'center',
  },

  // D1 — the pinned action block (design-lead): ink-2, a top hairline,
  // padding 12/16/16, gap 8.
  // utils/claimSheetPlan's PINNED_BLOCK_CHROME is this padding + hairline.
  blockPinned: {
    backgroundColor: ink.ink2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ink.line,
    paddingTop: space.md,
    paddingHorizontal: space.lg,
    paddingBottom: space.lg,
  },
  // The same block at the end of the scroll (accessibility text sizes).
  blockInScroll: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ink.line,
    paddingTop: space.md,
  },
  // What's measured: the same width and height in both parents.
  blockContent: { gap: space.sm },
  // The named CTA grows to two lines and never truncates a name (D10).
  namedCta: { height: undefined, minHeight: 44, paddingVertical: space.sm },
  dimLine: { ...type.bodySm, color: chalk.dim },
  chalkLine: { ...type.bodySm, color: chalk.base },
  // Refusals are --neg text, never a fill.
  negLine: { ...type.bodySm, color: semantic.neg },
  inlineLink: { color: chalk.base, textDecorationLine: 'underline' },
  // The chalkline Button's disabled opacity, for the Turn off link.
  linkDisabled: { opacity: 0.45 },
  windowRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center' },
  linksRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.sm },
  linkText: { ...type.bodySm, color: chalk.dim, textDecorationLine: 'underline' },
  thisMove: { ...type.bodySm, color: chalk.base, fontStyle: 'italic' },
  result: { gap: space.sm, paddingTop: space.sm },
  // design-lead's #351 §2.3 checkbox: 20×20, --r-xs, 1.5px line-strong on
  // ink-2; checked = an ice border and the check in ice (not an ice fill, so
  // the CTA stays the sheet's only ice fill). The row is the 44pt target.
  checkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
  },
  checkBox: {
    width: 20,
    height: 20,
    borderRadius: radii.xs,
    borderWidth: 1.5,
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkBoxOn: { borderColor: ice.base },
  checkLabel: { ...type.bodySm, color: chalk.base, flex: 1 },
});
