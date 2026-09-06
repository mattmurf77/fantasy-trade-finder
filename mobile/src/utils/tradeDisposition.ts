// Exact local pass identity and cursor projection. No React, I/O or module state.
// The screen owns the session record; the server owns durable dispositions.
export interface DispositionCard {
  trade_id: string;
  league_id?: string;
  opponent_user_id?: string;
  give_player_ids: string[];
  receive_player_ids: string[];
}

export function tradePassKey(account: string, league: string, card: DispositionCard): string | null {
  if (!account || !league || !card.opponent_user_id ||
      (card.league_id && card.league_id !== league)) return null;
  const side = (ids: string[]) => [...new Set(ids)].sort();
  if (!card.give_player_ids.length || !card.receive_player_ids.length) return null;
  return JSON.stringify([account, league, card.opponent_user_id,
    side(card.give_player_ids), side(card.receive_player_ids)]);
}

export interface PassWriteState {
  swipe: 'held' | 'pending' | 'acknowledged' | 'failed';
  reasonsPending: number;
  reasonPassed: boolean;
}

export type PassWriteEvent =
  | { type: 'reason_started' }
  | { type: 'reason_settled'; passed: boolean }
  | { type: 'swipe'; status: PassWriteState['swipe'] };

export function settlePassWrite(state: PassWriteState, event: PassWriteEvent): PassWriteState {
  if (event.type === 'swipe') return { ...state, swipe: event.status };
  if (event.type === 'reason_started') return { ...state, reasonsPending: state.reasonsPending + 1 };
  return { ...state, reasonsPending: Math.max(0, state.reasonsPending - 1),
    reasonPassed: state.reasonPassed || event.passed === true };
}

export function passWriteStatus(state: PassWriteState): 'committed' | 'pending' | 'failed' {
  if (state.reasonPassed || state.swipe === 'acknowledged') return 'committed';
  return state.swipe === 'failed' && state.reasonsPending === 0 ? 'failed' : 'pending';
}

export interface DispositionProjection<T> {
  cards: T[];
  sourceIndices: number[];
  index: number;
  sourceLength: number;
}

/** Source positions keep the cursor stable when a later response hides a card
 * behind it. The currently open reason episode is retained until its transition. */
export function projectTradePasses<T extends DispositionCard>(
  ordered: T[], sourcePosition: number, account: string, league: string,
  committed: ReadonlySet<string>, edits: Readonly<Record<string, T>> = {},
  heldReasonId: string | null = null,
): DispositionProjection<T> {
  const cards: T[] = [];
  const sourceIndices: number[] = [];
  ordered.forEach((card, i) => {
    const key = tradePassKey(account, league, edits[card.trade_id] ?? card);
    if (card.trade_id !== heldReasonId && key && committed.has(key)) return;
    cards.push(card);
    sourceIndices.push(i);
  });
  const position = Math.max(0, Math.min(sourcePosition, ordered.length));
  const next = sourceIndices.findIndex((i) => i >= position);
  return { cards, sourceIndices, index: next < 0 ? cards.length : next, sourceLength: ordered.length };
}

/** Convert a visible cursor move back to the stable source coordinate. Zero is
 * also the reset sentinel for lane changes and new searches. */
export function tradeSourcePosition(projection: DispositionProjection<unknown>, visibleIndex: number): number {
  if (visibleIndex <= 0) return 0;
  return projection.sourceIndices[visibleIndex] ?? projection.sourceLength;
}
