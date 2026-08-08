// Draft Room — GET /api/draft/board (rookie-draft M3/M4, flag `draft.room`).
//
// ONE versioned read-only payload. The server never writes to a platform:
// the terminal CTA is `deep_link` into Sleeper's own draft room.
//
// `schema` is load-bearing. The contract says a client MUST reject an
// unknown value rather than best-effort parse a payload it does not
// understand — a future `schema: 2` may move fields, and a Draft Room that
// half-renders one is worse than a Draft Room that says "update the app".

import { api } from './client';

export const DRAFT_BOARD_SCHEMA = 1;

export type DraftState = 'upcoming' | 'live' | 'complete' | 'unavailable';
export type DraftKind = 'rookie' | 'startup' | 'unknown';
export type OrderConfidence = 'assigned' | 'unset' | 'unknown';
export type DraftBasis = 'consensus' | 'my_board';

/** Closed set — the server's `degraded.reason`. */
export type DegradedReason =
  | 'upstream_error'
  | 'breaker_open'
  | 'budget_exceeded'
  | 'auth_expired';

/** Closed set — the designed honest states. Each has its own render. */
export type NoticeCode =
  | 'order_not_set'
  | 'startup_draft'
  | 'platform_unsupported'
  | 'class_not_loaded'
  | 'mfl_reconnect'
  // draft-extensions W3 M-B (flag `picks.assign`) — an ESPN league whose
  // pick ownership nobody has entered yet. `state` stays `unavailable`; this
  // is the ONE new vocabulary item the wave adds, and it is an UNCONFIGURED
  // state with a user-performable fix, never an error. Older binaries fall
  // through to `notice.message` and behave correctly.
  | 'picks_not_assigned';

export interface DraftOrderSlot {
  /** null when the platform has not published an order (`order_confidence:
   *  'unset'`) — the row is round-level ownership, not a slot. */
  slot: number | null;
  round: number;
  pick_no: number | null;
  owner_user_id: string | null;
  owner_username: string | null;
  original_user_id: string | null;
  original_username: string | null;
  is_traded: boolean;
  /** Only present with flag `picks.slot_values` (M6). */
  slot_value?: number | null;
}

export interface DraftPick {
  round: number;
  pick_no: number;
  slot: number | null;
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  picked_by_user_id: string | null;
  picked_at: string | null;
}

export interface UndraftedRow {
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  rookie_year: string | null;
  /** null ⇒ no consensus value. The row is still rendered (D7). */
  value: number | null;
  valued: boolean;
  rank: number;
}

export interface DraftBoard {
  schema: number;
  league_id: string;
  platform: string;
  state: DraftState;
  kind: DraftKind;
  season: number;
  rounds: number | null;
  teams: number | null;
  order_confidence: OrderConfidence;
  order: DraftOrderSlot[];
  picks: DraftPick[];
  undrafted: UndraftedRow[];
  undrafted_basis: DraftBasis;
  undrafted_suppressed: boolean;
  my_picks: DraftOrderSlot[];
  /** ISO-8601 UTC of the last successful upstream read. ALWAYS rendered. */
  as_of: string;
  stale: boolean;
  degraded: { reason: DegradedReason; since: string } | null;
  notice: { code: NoticeCode; message: string } | null;
  deep_link: string | null;
}

/** Thrown when the server speaks a schema this build does not understand. */
export class DraftSchemaError extends Error {
  constructor(readonly received: unknown) {
    super('This draft board needs a newer version of the app.');
    this.name = 'DraftSchemaError';
  }
}

export async function getDraftBoard(
  leagueId: string,
  basis: DraftBasis = 'consensus',
): Promise<DraftBoard> {
  const qs =
    `league_id=${encodeURIComponent(leagueId)}` +
    `&basis=${encodeURIComponent(basis)}`;
  const board = await api.get<DraftBoard>(`/api/draft/board?${qs}`);
  if (board?.schema !== DRAFT_BOARD_SCHEMA) throw new DraftSchemaError(board?.schema);
  return board;
}
