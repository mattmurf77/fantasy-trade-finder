// ESPN pick assignment — the three `/api/league/pick-assignments` routes
// (draft-extensions W3 M-A, lld §2.4). Flag `picks.assign`, ships OFF.
//
// ── What this is ────────────────────────────────────────────────────────
// ESPN hosts no rookie drafts, so an ESPN dynasty league's rookie draft
// happens off-platform and FTF becomes the league's system of record for
// pick OWNERSHIP. A league member says who owns each slot; that is the
// whole input surface.
//
// ── No values, anywhere (D13) ───────────────────────────────────────────
// There is no value field on any request in this module and there never
// may be. Prices are a pure server-side function of (round, years_out,
// format) via the shipped `pick_pool_value`, which is what bounds the
// blast radius of a bad assignment: it can REDISTRIBUTE value inside a
// league, never CREATE it (plan §6.2, the conservation bound). The server
// rejects any value-shaped key with 400 `values_not_accepted`; the client
// simply never sends one.
//
// ── Concurrency is compare-and-swap, not last-write-wins ────────────────
// `assigned_at` is BOTH a timestamp and the CAS token. A PUT carries the
// value the client read (`if_assigned_at`); a mismatch — including the
// "row already assigned, token omitted" case — comes back 409
// `stale_assignment` with the WHOLE current row, so the UI can render
// "Dana changed this pick 4 minutes ago — keep theirs, or use yours?"
// without a second round trip. A silent overwrite is not reachable.
//
// ── Provenance is not optional ──────────────────────────────────────────
// Every row this module returns carries `source`; a `'user'` row is
// member-entered and must be labelled as such wherever it is displayed,
// with a one-action correction path (D17). ESPN will never contradict a
// wrong grid, so the label is the only thing standing between an honest
// mistake and "FTF says".

import { api, ApiError } from './client';

/** Operator decision 3 (plan §6, 2026-08-06): the payload always covers the
 *  current season plus three, matching Sleeper's `seasons_ahead=3`. Exported
 *  so the UI can state the span without hard-coding a second copy. */
export const PICK_SEASONS_AHEAD = 3;

/** Server-side clamp on `rounds` (`draft_status.ROOKIE_MAX_ROUNDS`). It is
 *  the conservation bound's only inflation lever, so it is enforced on the
 *  server; this constant exists to keep the stepper from proposing a value
 *  the route will reject, never as the enforcement itself. */
export const PICK_ROUNDS_MAX = 8;
export const PICK_ROUNDS_MIN = 1;
/** Operator decision 2: default 4, user-settable. */
export const PICK_ROUNDS_DEFAULT = 4;

/** Slot NUMBERING only — never ownership (plan §6.5). Flipping this
 *  renumbers the board and touches no `owner_user_id`, which is why the
 *  toggle is safe at any time and can never trigger a CAS conflict. */
export type PickOrderType = 'linear' | 'snake';

/** `draft_picks.source` — the provenance triple's discriminator. `'user'` is
 *  a member-asserted row, `'platform'` (and, on every pre-W3 row, NULL) is
 *  platform truth. ONE definition, imported by every payload that carries
 *  provenance (`api/league.ts`, `api/calc.ts`) and by the W3 M-C marker, so
 *  a client can never invent a third value or read the enum two ways. */
export type PickSource = 'platform' | 'user';

export interface PickAssignmentSettings {
  rounds: number;
  order_type: PickOrderType;
  /** League member ids in round-1 order. Position i is slot i+1. */
  order: string[];
}

export interface PickSlot {
  /** `{league}_{season}_{round}_{original_roster}` — round is unpadded, so
   *  this is NOT lexicographically sortable. Never sort on it. */
  pick_id: string;
  season: number;
  round: number;
  /** Opaque league-local team label. Never resolved against a platform. */
  original_roster_id: string;
  original_user_id: string;
  original_username: string;
  owner_user_id: string;
  owner_username: string;
  /** Owner differs from the original team — i.e. this slot deviates from
   *  the pristine seed. The marker and the review summary key off it. */
  is_traded: boolean;
  /** `'user'` = a league member asserted this row. `'platform'`/null = the
   *  platform wrote it (impossible for ESPN today, but the field is the
   *  containment and the client reads it rather than assuming). */
  source: PickSource | null;
  assigned_by: string | null;
  /** ISO-8601. ALSO the CAS token — pass it back verbatim on the PUT.
   *  `null` on a never-assigned row. */
  assigned_at: string | null;
  /** ≥2 distinct members assigned this slot to ≥2 DIFFERENT owners. The
   *  engine withholds a price from a contested slot rather than re-pricing
   *  it back and forth while two people correct each other. */
  contested: boolean;
  /** Owner is no longer a league member. Surfaced as a re-assign row and
   *  excluded from pricing — never silently dropped. */
  orphaned: boolean;
}

export interface PickAssignmentSeason {
  season: number;
  slots: PickSlot[];
}

export interface PickAssignmentProgress {
  assigned: number;
  total: number;
  traded: number;
  contested: number;
  orphaned: number;
}

export interface PickAssignments {
  league_id: string;
  settings: PickAssignmentSettings;
  /** Always current + 3, ascending. Not paginated — ~192 slots is one
   *  round trip, and four requests to render one screen is worse. */
  seasons: PickAssignmentSeason[];
  progress: PickAssignmentProgress;
  /** False before the pristine grid has been written. */
  seeded: boolean;

  // ── ESPN auto-derived round-1 order (draft-extensions, 2026-08-08) ────
  // A DEFAULT for the setup step's drag list, not state the server adopted:
  // `settings.order` is untouched and nothing is written until the user
  // saves. All four keys arrive together or not at all.
  //
  // **Present ONLY while the league has no stored order of its own**, which
  // is what makes "never overwrite a saved order" structural rather than a
  // client rule — once someone saves, the server stops deriving (and stops
  // reading ESPN) entirely. There is therefore no "reset to the ESPN order"
  // affordance; re-deriving would need a server that still offers it.
  //
  // Absent whenever the derivation cannot be honest — a non-ESPN league, a
  // league linked before its first season, an expired-cookie read, a
  // membership change since the snapshot. Absent is the shipped behaviour:
  // the user orders the list by hand, exactly as before.
  /** League member ids in the derived round-1 pick order (index 0 = 1.01). */
  suggested_order?: string[];
  /** Only value today. Read as an OPEN set — a future platform may add one. */
  suggested_order_source?: 'espn_standings' | (string & {});
  /** The ESPN season the standings were read from — the caption says it. */
  suggested_order_season?: number;
  /** Per-team "why this pick", in the same order as `suggested_order`. */
  suggested_order_detail?: SuggestedOrderEntry[];
}

/** One row of the derivation's reasoning. Carries NO value/price field and
 *  none may be added — D13 governs this payload too. */
export interface SuggestedOrderEntry {
  user_id: string;
  team_name: string;
  /** 1-based pick number. */
  pick: number;
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  /** ESPN's final regular-season seed. */
  playoff_seed: number;
  /** ESPN's post-playoff rank, 1 = champion. Only meaningful — and only
   *  used to order — when `made_playoffs` is true. */
  final_rank: number | null;
  made_playoffs: boolean;
}

export interface AssignPickResult {
  ok: true;
  slot: PickSlot;
  progress: PickAssignmentProgress;
}

export interface SeedGridResult {
  ok: true;
  seeded: number;
  /** Present when `reseed: true` overwrote existing edits. */
  reseeded_over?: number;
  progress: PickAssignmentProgress;
}

/** The route's documented error codes. Read as an OPEN set: an unknown
 *  value degrades to generic copy rather than crashing a screen. */
export type PickAssignmentErrorCode =
  | 'feature_disabled'
  | 'pick_not_found'
  | 'owner_not_in_league'
  | 'stale_assignment'
  | 'values_not_accepted'
  | 'rounds_out_of_range'
  | 'bad_order'
  | 'bad_order_type'
  | (string & {});

/** The whole board for a league. The server always answers current + 3
 *  seasons; the client is what decides to show one at a time. */
export async function getPickAssignments(leagueId: string) {
  return api.get<PickAssignments>(
    `/api/league/pick-assignments?league_id=${encodeURIComponent(leagueId)}`,
  );
}

/** Assign ONE slot. Saves are per slot on purpose — there is no giant
 *  dirty form to lose, and two members fixing two different picks never
 *  collide.
 *
 *  `ifAssignedAt` is the `assigned_at` the caller READ. Pass it verbatim,
 *  including `null` for a never-assigned row; omitting it on an assigned
 *  row is itself a 409, because a blind overwrite is never allowed. */
export async function assignPick(args: {
  leagueId: string;
  pickId: string;
  ownerUserId: string;
  ifAssignedAt: string | null;
}) {
  // #268: the route is `PUT /api/league/pick-assignments/<pick_id>` — the
  // slot id is a URL segment, not a body field. Every save 405ed until this
  // matched, because a 405 has no `{error: <code>}` body for
  // `pickAssignmentErrorCode`/`staleAssignment` to narrow, so the screen
  // fell through to its generic "Couldn't save that pick" toast on every
  // single attempt, not just the CAS-conflict path.
  return api.put<AssignPickResult>(
    `/api/league/pick-assignments/${encodeURIComponent(args.pickId)}`,
    {
      league_id: args.leagueId,
      owner_user_id: args.ownerUserId,
      if_assigned_at: args.ifAssignedAt,
    },
  );
}

/** The seeder AND the order/rounds setter — one route, because order is
 *  set ONCE for the whole board rather than per slot, and changing it is
 *  the same write as creating it.
 *
 *  `reseed: false` (the default, and what the UI sends) is idempotent: it
 *  writes the pristine grid where nothing exists and PRESERVES every
 *  edited slot. `reseed: true` is the explicit start-over. */
export async function seedPickGrid(args: {
  leagueId: string;
  rounds: number;
  orderType: PickOrderType;
  order: string[];
  reseed?: boolean;
}) {
  return api.post<SeedGridResult>('/api/league/pick-assignments/order', {
    league_id: args.leagueId,
    rounds: args.rounds,
    order_type: args.orderType,
    order: args.order,
    reseed: args.reseed ?? false,
  });
}

/** The error code on a failed assignment call, or null when the failure
 *  was not a typed route rejection (network, timeout, 5xx). */
export function pickAssignmentErrorCode(err: unknown): PickAssignmentErrorCode | null {
  if (!(err instanceof ApiError)) return null;
  const body = err.body as { error?: unknown } | null;
  if (!body || typeof body !== 'object') return null;
  return typeof body.error === 'string' ? body.error : null;
}

/** Narrows a PUT rejection to the CAS conflict and hands back the CURRENT
 *  row, which the 409 body carries so the conflict prompt can render the
 *  other person's answer without a second request. Returns null for every
 *  other failure. */
export function staleAssignment(err: unknown): PickSlot | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const body = err.body as { error?: unknown; current?: unknown } | null;
  if (!body || typeof body !== 'object' || body.error !== 'stale_assignment') return null;
  const current = body.current as PickSlot | undefined;
  return current && typeof current === 'object' ? current : null;
}

/** The League tab's sub-line, and the screen's progress line — ONE
 *  formatter so the two surfaces cannot disagree about what "done" reads
 *  like. Pure; lives beside the payload it describes. */
export function pickAssignmentSubline(
  progress: PickAssignmentProgress | undefined,
  seeded: boolean | undefined,
): string {
  if (!seeded || !progress || progress.total <= 0) return 'Not assigned yet';
  const base = `${progress.assigned} of ${progress.total} assigned`;
  return progress.traded > 0 ? `${base} · ${progress.traded} traded` : base;
}
