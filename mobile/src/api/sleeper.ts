import { api } from './client';
import type { LeagueSummary } from '../shared/types';

// Sleeper-backed endpoints the backend proxies (so we don't hit api.sleeper.app
// directly from the client — the Flask server caches responses). Matches the
// shape of the web app's calls in app.js.

// GET /api/sleeper/leagues/<user_id> — user's NFL 2026 leagues + any
// locally-created leagues tied to that user.
export async function getLeagues(userId: string): Promise<LeagueSummary[]> {
  const data = await api.get<any[]>(`/api/sleeper/leagues/${userId}`);
  return (data || []).map((lg) => ({
    league_id: String(lg.league_id),
    name: lg.name || 'League',
    avatar: lg.avatar ?? null,
    total_rosters: lg.total_rosters ?? undefined,
    platform: lg.platform ?? 'sleeper',
    // Sleeper settings.type (0 redraft / 1 keeper / 2 dynasty) — F12
    // redraft labeling + event segment tag. Absent on local leagues.
    settings_type: typeof lg.settings?.type === 'number' ? lg.settings.type : undefined,
    // rookie-draft placement (flag `draft.room`, server-side): #207's cached
    // per-league draft verdict. Null with the flag off. No client consumer
    // since 2026-08-06 — the Draft tab's per-league predicate was retired
    // for the seasonal `draft.tab` switch (see shared/types.ts).
    draft_status: lg.draft_status ?? null,
    draft_status_confidence: lg.draft_status_confidence ?? null,
  }));
}

// GET /api/sleeper/rosters/<league_id>
export interface RosterRow {
  owner_id: string;
  roster_id: number;
  players: string[] | null;
  starters?: string[] | null;
  /**
   * Sleeper co-managers. `null` for the (common) sole-owned roster. A
   * co-owner has full control of the team — see `ownsRoster` below.
   */
  co_owners?: string[] | null;
}
export async function getLeagueRosters(leagueId: string) {
  return api.get<RosterRow[]>(`/api/sleeper/rosters/${leagueId}`);
}

// ── Roster → user resolution (co-owner aware) ─────────────────────────────
// THE predicate, mirrored in backend/sleeper_roster.py and web/js/app.js and
// listed in docs/cross-client-invariants.md so the three cannot drift:
//
//     a roster is yours iff  user_id === owner_id  OR  user_id ∈ co_owners
//
// Matching on owner_id alone left a co-owner with no team in that league AND
// served their own roster back as an opponent. See
// docs/plans/sleeper-co-owner-rosters/scope.md.

export function ownsRoster(row: RosterRow | null | undefined, userId: string): boolean {
  if (!row || !userId) return false;
  if (row.owner_id === userId) return true;
  return (row.co_owners ?? []).some((c) => String(c) === userId);
}

/** The roster this user owns or co-owns, or undefined. */
export function findMyRoster(
  rows: RosterRow[] | null | undefined,
  userId: string,
): RosterRow | undefined {
  return (rows ?? []).find((r) => ownsRoster(r, userId));
}

/**
 * The user's LEAGUE identity: the `owner_id` of the roster they own or
 * co-own, falling back to their own id when they have no roster here.
 *
 * This — not the account id — is what every roster-owner comparison must use
 * (`rosterByOwner[…]`, "exclude my own team", `league_members` keys), because
 * a co-owned roster is keyed league-wide on its PRIMARY owner. Identical to
 * `userId` for a sole owner.
 */
export function myOwnerId(rows: RosterRow[] | null | undefined, userId: string): string {
  return findMyRoster(rows, userId)?.owner_id || userId;
}

// GET /api/sleeper/league_users/<league_id>
export interface LeagueUser {
  user_id: string;
  username: string;
  display_name?: string;
  avatar?: string | null;
}
export async function getLeagueUsers(leagueId: string) {
  return api.get<LeagueUser[]>(`/api/sleeper/league_users/${leagueId}`);
}

// Warmed-once-per-launch guard (INIT-12 Wave 1, FR-5). Set true after the first
// successful warm; lets redundant warm calls within the same launch short-
// circuit. Reset via resetWarmedFlag() when the backend signals its player
// cache was lost (e.g. a dyno restart after boot) so the next league pick
// re-warms before session_init.
let warmedThisLaunch = false;

/** True once warmPlayerCache() has succeeded in this app launch. */
export function isWarmedThisLaunch(): boolean {
  return warmedThisLaunch;
}

/** Clear the warmed-once flag so the next warmPlayerCache() hits the network
 *  again. Called when a session_init reports the player DB is not cached. */
export function resetWarmedFlag(): void {
  warmedThisLaunch = false;
}

// GET /api/sleeper/players/warm — triggers the same server-side cache
// hydration as /api/sleeper/players but returns only {ok, count}. The full
// route serializes ~4.8MB of player JSON the mobile client never reads;
// this variant keeps the response body to a few hundred bytes.
//
// Idempotent within a launch: the first success sets warmedThisLaunch and
// later calls return a synthetic ok without a round-trip (FR-5). App boot and
// initLeagueSession therefore warm the cache exactly once between them.
export async function warmPlayerCache(): Promise<{ ok: boolean; count?: number }> {
  if (warmedThisLaunch) {
    return { ok: true };
  }
  const res = await api.get<{ ok: boolean; count?: number }>('/api/sleeper/players/warm');
  warmedThisLaunch = true;
  return res;
}
