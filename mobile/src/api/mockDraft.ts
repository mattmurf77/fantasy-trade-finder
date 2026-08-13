// Mock draft — the four `/api/mock-draft` routes (draft-extensions W2,
// plan docs/plans/rookie-draft/mock-draft-plan.md §5). Flag `draft.mock`.
//
// The FTF-native simulation of a league's rookie draft: the user picks for
// their own team, computer drafters pick for everyone else. NOTHING here
// reaches a platform — the mock is a self-contained server-side row, and
// the room's read-only "never drafts for you" guarantee (D9) is untouched
// because a mock pick is never written anywhere but the mock.
//
// TWO response shapes on the same route, and the caller MUST branch:
//   · the full state payload — deliberately the SAME entry shapes as
//     `GET /api/draft/board` (`order[]`, `picks[]`, `undrafted[]`,
//     `my_picks[]`, `notice`), which is what lets the Draft Room's row
//     components render it verbatim (lld §2.3, "the I-6 vocabulary");
//   · M2's typed-empty `{schema, empty: true, reason}` — the ONLY way a
//     new refusal may appear without touching a closed client enum (D10).
//     `reason` is therefore read as an OPEN string: an unknown value falls
//     back to generic copy rather than crashing a screen.
//
// `schema` is load-bearing exactly as on the board: an unknown value means
// "update the app", not "best-effort parse".

import { api } from './client';
import { DraftSchemaError, type DraftBasis, type UndraftedRow } from './draft';

export const MOCK_DRAFT_SCHEMA = 1;

export type MockStatus = 'active' | 'complete' | 'abandoned';
export type MockDraftType = 'linear' | 'snake';
export type MockOrderSource = 'assigned' | 'randomized';
export type MockPickBy = 'user' | 'cpu';

/** #305 — who makes the picks. A CLOSED two-member enum on the wire
 *  (`docs/cross-client-invariants.md`): `cpu` = computer drafters pick the
 *  other teams; `manual` = the user picks for every team. Snapshotted into
 *  `settings` at create and immutable for the life of the mock. */
export type MockDraftMode = 'cpu' | 'manual';

/** The refusals the engine ships today. Open by construction (D10) — read
 *  any other value as "not available right now" rather than failing. */
export type MockEmptyReason =
  | 'no_active_mock'
  | 'class_not_loaded'
  | 'cpu_model_unvalidated'
  | 'user_not_in_draft'
  | (string & {});

export interface MockOnTheClock {
  pick_no: number;
  round: number;
  slot: number;
  /** The owning team's user id, or null when ownership can't be resolved. */
  roster_id: string | null;
  is_user: boolean;
}

export interface MockOrderSlot {
  slot: number;
  round: number;
  pick_no: number;
  owner_user_id: string | null;
  owner_username: string | null;
  original_user_id: string | null;
  original_username: string | null;
  is_traded: boolean;
}

export interface MockPick {
  round: number;
  pick_no: number;
  slot: number;
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  picked_by_user_id: string | null;
  /** Always null today — the engine does not stamp pick times (gap G8). */
  picked_at: string | null;
  by: MockPickBy;
}

/** A CPU team's drafting persona, snapshotted at creation. */
export interface MockPersona {
  outlook: string;
  source: 'declared' | 'inferred' | 'default' | (string & {});
}

export interface MockSettingsEcho {
  rounds: number | null;
  type: MockDraftType | null;
  teams: number | null;
  order_source: MockOrderSource | null;
  personas: Record<string, MockPersona> | null;
  noise: Record<string, number> | null;
  /** #305 — the ONLY source of mode truth. Never infer mode from `by`
   *  values, pick cadence, or `on_the_clock`. Nullable in the TYPE only
   *  (an old server omits it); the new server always sends it. */
  mode: MockDraftMode | null;
  /** #295/#305 — the caller's team id in this draft: THE join key for
   *  "my team" (`my_picks`, ticker highlight, `for_own_team`). Never key
   *  "my team" off `by` — in manual mode every pick is `by: "user"` while
   *  `picked_by_user_id` walks the order. Nullable in the TYPE only. */
  user_owner_id: string | null;
}

/** The GET typed-empty's ride-along probe (#295 R9) — shipped-but-untyped
 *  until now. `reason` carries the refusal ladder's answer
 *  (`user_not_in_draft` included), which is what lets the entry card render
 *  disabled BEFORE any POST. */
export interface MockCapability {
  can_start: boolean;
  reason: MockEmptyReason | null;
  teams: number;
  min_teams: number;
  rounds_default: number;
  rounds_max: number;
  type: MockDraftType | null;
  order_source: MockOrderSource | null;
}

export interface MockDraftState {
  schema: number;
  mock_id: number | null;
  status: MockStatus;
  league_id: string;
  season: number;
  /** null ⇒ every slot is filled; the mock is over. */
  on_the_clock: MockOnTheClock | null;
  order: MockOrderSlot[];
  picks: MockPick[];
  /** Same row shape as the Draft Room's undrafted list, by construction. */
  undrafted: UndraftedRow[];
  undrafted_basis: DraftBasis;
  my_picks: MockPick[];
  settings_echo: MockSettingsEcho;
  notice: { code: string; message: string } | null;
}

export interface MockDraftEmpty {
  schema: number;
  empty: true;
  reason: MockEmptyReason;
  /** GET only — the POST typed-empty is exactly three keys. */
  capability?: MockCapability;
}

export type MockDraftResponse = MockDraftState | MockDraftEmpty;

export function isMockEmpty(res: MockDraftResponse): res is MockDraftEmpty {
  return (res as MockDraftEmpty)?.empty === true;
}

function checked(res: MockDraftResponse): MockDraftResponse {
  if (res?.schema !== MOCK_DRAFT_SCHEMA) throw new DraftSchemaError(res?.schema);
  return res;
}

/** The active mock, or the most recent complete one as a recap.
 *
 *  NOTE (contract gap G2): with no row this answers
 *  `{empty: true, reason: 'no_active_mock'}` and says NOTHING about whether
 *  a create would succeed — `class_not_loaded` and `cpu_model_unvalidated`
 *  are POST-only refusals. Callers that want to disable the entry in
 *  advance have to derive what they can from the board payload. */
export async function getMockDraft(
  leagueId: string,
  basis: DraftBasis = 'consensus',
): Promise<MockDraftResponse> {
  const qs =
    `league_id=${encodeURIComponent(leagueId)}` +
    `&basis=${encodeURIComponent(basis)}`;
  return checked(await api.get<MockDraftResponse>(`/api/mock-draft?${qs}`));
}

/** Create a mock, abandoning any prior active one for this user + league
 *  server-side in the same transaction — so "start over" is this call, not
 *  an abandon followed by a create. */
export async function createMockDraft(params: {
  leagueId: string;
  rounds?: number;
  type?: MockDraftType;
  mode?: MockDraftMode;
}): Promise<MockDraftResponse> {
  return checked(
    await api.post<MockDraftResponse>('/api/mock-draft', {
      league_id: params.leagueId,
      // The plan's "default = the platform draft's rounds" is a CLIENT
      // responsibility: the route defaults to a flat 4 (gap G9).
      ...(params.rounds != null ? { rounds: params.rounds } : {}),
      ...(params.type ? { type: params.type } : {}),
      // #305 — spread only when set, so a 1.12.x-shaped call is
      // byte-identical on the wire.
      ...(params.mode ? { mode: params.mode } : {}),
    }),
  );
}

/** Make the user's pick, then run the CPU tail. One request, one response —
 *  the server resolves every intervening CPU pick instantly. */
export async function pickInMockDraft(
  mockId: number,
  playerId: string,
): Promise<MockDraftResponse> {
  return checked(
    await api.post<MockDraftResponse>('/api/mock-draft/pick', {
      mock_id: mockId,
      player_id: playerId,
    }),
  );
}

export async function abandonMockDraft(mockId: number): Promise<{ ok: boolean }> {
  return api.post<{ ok: boolean }>('/api/mock-draft/abandon', { mock_id: mockId });
}
