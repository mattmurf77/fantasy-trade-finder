// The D1 claim sheet's decisions, as pure functions (components/ClaimSheet.tsx
// renders them and runs their effects). Which step a capability opens on,
// what each move outcome shows and does, the drop and bid the CTA names and
// the request sends, and whether the action block pins. No React and no I/O,
// so tests/check-fa-move.js executes them.

import {
  bidText,
  capabilityOrNull,
  fallbackCopy,
  faMoveGate,
  hasConnectScreen,
  isMoveCapability,
  isSubmitCapability,
  moveCopy,
  moveCtaLabel,
  rowMoveFields,
  waiverLines,
  type ConsentBlock,
  type CopyVars,
  type FallbackKey,
  type FaMoveCapability,
  type FaMoveRow,
  type GateStep,
  type LeaguePlatform,
  type MoveCopyKey,
  type MoveFailure,
  type MoveKind,
  type MoveRequest,
  type MoveResponse,
} from '../api/faMove';

// One inline line in a step: a refusal (--neg) or a plain notice (chalk).
export type Notice = { text: string; tone: 'neg' | 'chalk' };
export type ResultKind =
  | 'added' // 8
  | 'pending' // 9
  | 'player_taken' // 10c
  | 'platform_refused' // 10f
  | 'unavailable' // 10g
  | 'unknown' // 12
  | 'neutral' // 12-style: a 400 or an unrecognised 4xx
  | 'rejected'; // 13
// Each step replaces the sheet's content rather than stacking (scope §C (e)).
export type SheetView =
  | { step: 'handoff'; line: string | null } // 1, 14, F4
  | { step: 'unsupported' } // MFL / ESPN with no in-app path here: NO_ADD_REASON
  | { step: 'ready'; ctaNotice?: Notice; dropNotice?: Notice } // 6, with 10a/10b/10e/11 inline
  | { step: 'connect'; verify: boolean; line: string | null; backedOut: boolean } // 3, 4
  | { step: 'consent'; block: ConsentBlock; termsChanged: boolean } // 5
  | { step: 'result'; kind: ResultKind; title: string; lines: string[] }; // 8, 9, 10c, 10f, 10g, 12, 13

/** A league's FA read, as far as the sheet needs it. */
export interface FaListLike {
  move?: unknown;
  free_agents?: Array<{ player_id: string } & FaMoveRow>;
}

/** Copy for one capability: its server slots and the neutral fallbacks. */
export interface CopyFns {
  platform: LeaguePlatform;
  slot(key: MoveCopyKey, extra?: CopyVars): string | null;
  fallback(key: FallbackKey, extra?: CopyVars): string | null;
}

export function copyFns(move: FaMoveCapability | null, vars: CopyVars): CopyFns {
  const platform: LeaguePlatform = isMoveCapability(move) && move.league_platform ? move.league_platform : 'sleeper';
  return {
    platform,
    slot: (key, extra = {}) => moveCopy(move?.copy, key, { ...vars, ...extra }, platform),
    fallback: (key, extra = {}) => fallbackCopy(key, { ...vars, ...extra }, platform),
  };
}

function connectView(step: GateStep, connect: string | null | undefined, said: string | null, copy: CopyFns, backedOut: boolean): SheetView {
  const verify = step === 'verify';
  const line =
    said ??
    (verify
      ? copy.slot('verify_line')
      : connect === 'other_account'
        ? copy.slot('other_account_line') ?? copy.slot('connect_line')
        : copy.slot('connect_line'));
  return { step: 'connect', verify, line, backedOut };
}

/** The sheet's step for a capability (scope §C). No capability: the hand-off,
 *  with nothing from the capability or the row (fully legacy). */
export function initialView(move: FaMoveCapability | null, row: FaMoveRow, copy: CopyFns, backedOut = false): SheetView {
  const step = faMoveGate({ move, row, consentValid: false, ticked: false });
  switch (step) {
    case 'connect':
    case 'verify':
      return connectView(step, move?.connect, null, copy, backedOut);
    case 'consent':
    case 'submit':
    case 'submit_with_consent':
      return { step: 'ready' };
    case 'unsupported':
      // MFL / ESPN: that platform's NO_ADD_REASON in the sheet. A Sleeper
      // league (not a value the server sends) keeps the legacy hand-off.
      return copy.platform === 'sleeper' ? { step: 'handoff', line: null } : { step: 'unsupported' };
    case 'handoff':
      // A held row: the server's line; on another platform (no opener in
      // this binary) a neutral line when the server sends none.
      return { step: 'handoff', line: row.move_line ?? (copy.platform === 'sleeper' ? null : copy.fallback('held_line')) };
    default:
      return { step: 'handoff', line: null };
  }
}

/** What an outcome changes, for the sheet to apply in one place. */
export interface Plan {
  view?: SheetView;
  /** Show the consent step for this block (ClaimSheet's showConsent). */
  consent?: ConsentBlock;
  connect?: string;
  consentOverride?: boolean;
  requireDrop?: boolean;
  clearDrop?: boolean;
  refresh?: boolean;
  serverRemaining?: number;
  trackConnect?: 'not_linked' | 'expired' | 'unverified';
  /** 10e: re-read the list, then planKindChanged. */
  reread?: boolean;
  markPending?: boolean;
  scrollToDrop?: boolean;
}

/** State 11 with nothing sent: offline at the tap, or a consent GET that
 *  never got an answer. The same named CTA is the retry. */
export function planNotSent(copy: CopyFns): Plan {
  return { view: { step: 'ready', ctaNotice: { text: copy.slot('not_sent_line') ?? '', tone: 'neg' } } };
}

/** 8 / 9. A pending claim also marks the host's row for the session. */
export function planResponse(res: MoveResponse, copy: CopyFns): Plan {
  const pending = res.status === 'pending';
  return {
    consentOverride: true,
    refresh: true,
    markPending: pending,
    view: {
      step: 'result',
      kind: pending ? 'pending' : 'added',
      title: res.title || copy.fallback(pending ? 'result_pending' : 'result_added') || '',
      lines: Array.isArray(res.lines) ? res.lines.filter((l) => typeof l === 'string') : [],
    },
  };
}

/** Every failure state (contract §4) → what the sheet shows and does. */
export function planFailure(f: MoveFailure, copy: CopyFns): Plan {
  const said = f.message ?? null;
  // MFL has no connect screen in this binary (contract §6): never a button
  // that does nothing, so its connect / verify / rejected are `unsupported`.
  const canConnect = hasConnectScreen(copy.platform);
  const result = (kind: ResultKind): Plan => ({
    refresh: true,
    view: { step: 'result', kind, title: f.title ?? copy.fallback('refusal_title') ?? '', lines: said ? [said] : [] },
  });
  switch (f.state) {
    case 'handoff': // 404 feature_disabled: moves are off; nothing was sent.
      return { view: { step: 'handoff', line: copy.slot('unavailable_line') } };
    case 'connect':
      if (!canConnect) return { view: { step: 'unsupported' } };
      return { connect: 'not_linked', trackConnect: 'not_linked', view: connectView('connect', 'not_linked', said, copy, false) };
    case 'verify': {
      if (!canConnect) return { view: { step: 'unsupported' } };
      const reason = f.errorCode === 'expired' ? 'expired' : 'unverified';
      return { connect: reason, trackConnect: reason, view: connectView('verify', reason, said, copy, false) };
    }
    case 'consent':
      return f.consent
        ? { consentOverride: false, consent: f.consent }
        : { consentOverride: false, view: { step: 'handoff', line: copy.slot('unavailable_line') } };
    case 'roster_full': // 10a: the drop list shows, with the server's reason and focus; the list refreshes.
      return {
        requireDrop: true,
        refresh: true,
        scrollToDrop: true,
        view: { step: 'ready', dropNotice: { text: said ?? copy.fallback('drop_to_make_room') ?? '', tone: 'neg' } },
      };
    case 'drop_gone': // 10b: clear the stale pick, refresh the drop list.
      return {
        clearDrop: true,
        refresh: true,
        view: { step: 'ready', dropNotice: { text: said ?? copy.fallback('refusal_title') ?? '', tone: 'neg' } },
      };
    case 'over_budget': // 10d: the bid error, against the server's remaining.
      return { ...(typeof f.remaining === 'number' ? { serverRemaining: f.remaining } : {}), view: { step: 'ready' } };
    case 'kind_changed':
      return { reread: true };
    case 'claims_off': // 14: the hand-off, bid and drop kept.
      return { view: { step: 'handoff', line: said ?? copy.slot('unavailable_line') } };
    case 'not_sent': // 11: nothing was sent; the same named CTA retries.
      return { view: { step: 'ready', ctaNotice: { text: said ?? copy.slot('not_sent_line') ?? '', tone: 'neg' } } };
    case 'player_taken':
    case 'platform_refused':
    case 'unavailable':
    case 'neutral':
      return result(f.state);
    case 'rejected': // 13: the server dropped the credential.
      return canConnect ? { connect: 'not_linked', ...result('rejected') } : { refresh: true, view: { step: 'unsupported' } };
    case 'unknown': {
      // 12: never "failed", never a retry (F3). The server's own words only
      // for its own codes; anything else gets the client's 8i copy.
      const own = f.errorCode === 'outcome_unknown' || f.errorCode === 'move_in_progress';
      return {
        refresh: true,
        view: {
          step: 'result',
          kind: 'unknown',
          title: (own && f.title) || copy.slot('unknown_title') || '',
          lines: [(own && said) || copy.slot('unknown_body') || ''],
        },
      };
    }
  }
}

/** 10e after the re-read: the row's corrected move_kind (or the other one
 *  when the re-read failed), the fresh capability when it has one, and a
 *  line saying why the CTA changed. */
export function planKindChanged(
  fresh: FaListLike | undefined,
  ctx: { move: FaMoveCapability | null; kind: MoveKind; said: string | null; connect: string | null; playerId: string; copy: CopyFns },
): { move: FaMoveCapability | null; row: FaMoveRow; view: SheetView } {
  const freshRow = fresh?.free_agents?.find((r) => r.player_id === ctx.playerId);
  const row: FaMoveRow = {
    move_kind: freshRow?.move_kind ?? (ctx.kind === 'add' ? 'claim' : 'add'),
    move_mode: freshRow?.move_mode,
    move_line: freshRow?.move_line,
  };
  const move = isSubmitCapability(fresh?.move) ? (fresh!.move as FaMoveCapability) : ctx.move;
  const line = ctx.said ?? ctx.copy.fallback('refusal_title') ?? '';
  const step = faMoveGate({ move, row, connect: ctx.connect, consentValid: false, ticked: false });
  const view: SheetView =
    step === 'handoff' ? { step: 'handoff', line } : step === 'unsupported' ? { step: 'unsupported' } : { step: 'ready', ctaNotice: { text: line, tone: 'chalk' } };
  return { move, row, view };
}

/** Back from the connect screen. A failed or timed-out re-read goes on as
 *  connected (to consent or Ready); the server's 409s are the safety net. */
export function resumeAfterConnect(
  fresh: FaListLike | undefined,
  ctx: { move: FaMoveCapability | null; row: FaMoveRow; playerId: string },
): { move: FaMoveCapability | null; row: FaMoveRow; assumedConnected: boolean } {
  if (!fresh) {
    const move = ctx.move ? { ...ctx.move, connect: 'ok' } : null;
    return { move, row: ctx.row, assumedConnected: true };
  }
  const move = capabilityOrNull(fresh.move);
  const tapped = fresh.free_agents?.find((r) => r.player_id === ctx.playerId);
  return { move, row: tapped ? rowMoveFields(move, tapped) : rowMoveFields(move, ctx.row), assumedConnected: false };
}

/** The drop and bid the CTA names, and the request sends: ONE source, so a
 *  drop that left the candidates (a refresh) is neither named nor sent. */
export function moveSelection(input: {
  rowName: string;
  kind: MoveKind;
  dropId: string | null;
  candidates: ReadonlyArray<{ id: string; name: string }>;
  faab: boolean;
  bid: string;
  copy: FaMoveCapability['copy'] | null | undefined;
  platform: LeaguePlatform;
}): {
  drop: { id: string; name: string } | null;
  bid: number | null;
  ctaLabel: string;
  waiverLines: string[];
  request: Pick<MoveRequest, 'drop_player_id' | 'move_kind' | 'faab_bid'>;
} {
  const drop = (input.dropId && input.candidates.find((c) => c.id === input.dropId)) || null;
  // Contract §7: an empty bid on a FAAB claim is $0; a priority-waiver claim has none.
  const bid = input.kind === 'claim' && input.faab ? (input.bid === '' ? 0 : Number(input.bid)) : null;
  const vars = { add: input.rowName, drop: drop?.name ?? null, bid: bid != null ? bidText(bid) : null };
  return {
    drop,
    bid,
    ctaLabel: moveCtaLabel(input.copy, input.kind, vars, input.platform),
    waiverLines: input.kind === 'claim' ? waiverLines(input.copy, vars, input.platform) : [],
    request: {
      ...(drop ? { drop_player_id: drop.id } : {}),
      move_kind: input.kind,
      ...(bid != null ? { faab_bid: bid } : {}),
    },
  };
}

/** Whether the drop list shows: whenever a drop is required (a 10a the
 *  client didn't foresee included), else as #509 decides it. */
export function dropListShown(input: { openSlots: number | null; candidates: number; requireDrop: boolean }): boolean {
  if (input.requireDrop) return true;
  return input.openSlots !== null ? input.openSlots === 0 : input.candidates > 0;
}

// The pinned block's own padding and hairline (ClaimSheet's blockPinned):
// 12 + 16 + 1. The sheet measures the block's content, which is the same in
// both parents, and adds this back.
export const PINNED_BLOCK_CHROME = 29;
// The band that stops a block near the threshold from flip-flopping.
export const PIN_HYSTERESIS = 24;

/** design-lead's accessibility-size rule: the action block stops pinning
 *  when it would be taller than half the sheet. Hysteresis: once unpinned it
 *  re-pins only when clearly under, so the decision never oscillates. */
export function actionBlockPinned(prevPinned: boolean, contentHeight: number, sheetMaxHeight: number): boolean {
  if (!(contentHeight > 0) || !(sheetMaxHeight > 0)) return prevPinned;
  const block = contentHeight + PINNED_BLOCK_CHROME;
  const half = sheetMaxHeight / 2;
  return prevPinned ? block <= half : block < half - PIN_HYSTERESIS;
}
