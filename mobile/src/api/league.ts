import { api } from './client';
import type {
  ScoringFormat,
  ActivityEvent,
  ContrarianRow,
  NewPartnerEntry,
  PortfolioRow,
  PortfolioTier,
} from '../shared/types';

// ── League preferences (team outlook + positional prefs) ─────────
// Mirrors the web app's saveOutlookAndPreferences flow.
// The backend stores these on the session + league_preferences table.
//
// CONTRACT: backend uses `team_outlook` as the field name (see
// backend/server.py:set_league_preferences). Earlier code used
// `outlook_value` here which produced a 400 from the server.

export type Outlook =
  | 'championship'
  | 'contender'
  | 'rebuilder'
  | 'jets'
  | 'not_sure'
  | null;

export interface LeaguePreferences {
  team_outlook: Outlook;
  acquire_positions: string[];
  trade_away_positions: string[];
  /** Phase-2: backend's roster-derived outlook guess. Additive — present
   *  on GET only when no team_outlook is declared. Never POSTed back. */
  inferred_outlook?: Outlook;
  /** Phase-2: the per-signal scores behind inferred_outlook (additive,
   *  GET-only, same condition). Keys are backend signal names. */
  inferred_signals?: Record<string, number>;
  /** FB #156 (Trade-Finding Hub): the caller's own roster needs/surplus
   *  from analyze_roster_strengths — positions below the starter threshold
   *  (needs) and at/above the surplus threshold (surplus). GET-only,
   *  additive; power the hub's positions-needed / positions-to-shed
   *  recommendation chips. Never POSTed back. */
  position_needs?: string[];
  position_surplus?: string[];
}

export async function getLeaguePreferences(leagueId: string) {
  return api.get<LeaguePreferences>(
    `/api/league/preferences?league_id=${encodeURIComponent(leagueId)}`,
  );
}

export async function saveLeaguePreferences(leagueId: string, prefs: LeaguePreferences) {
  return api.post<any>('/api/league/preferences', {
    league_id: leagueId,
    ...prefs,
  });
}

// ── Asset preferences (untouchables + targets, backlog #2) ────────
// Backend: GET/POST /api/league/asset-prefs. `untouchable` = never offer
// this player FROM the caller's roster in generated trades (feedback #95);
// `target` = bias suggestions toward acquiring the player. A player holds
// at most one tag per league; list: 'none' removes the tag.
// Enum strings are a cross-client contract (docs/cross-client-invariants.md).

export interface AssetPrefs {
  untouchables: string[];
  targets: string[];
}

export async function getAssetPrefs(leagueId: string) {
  return api.get<AssetPrefs>(
    `/api/league/asset-prefs?league_id=${encodeURIComponent(leagueId)}`,
  );
}

export async function setAssetPref(
  leagueId: string,
  playerId: string,
  list: 'untouchable' | 'target' | 'none',
) {
  return api.post<{ ok: boolean } & AssetPrefs>('/api/league/asset-prefs', {
    league_id: leagueId,
    player_id: playerId,
    list,
  });
}

export interface LeagueCoverage {
  ranked: number;
  total: number;
  members?: Array<{ user_id: string; username: string; has_rankings: boolean }>;
}
export async function getLeagueCoverage(leagueId: string) {
  return api.get<LeagueCoverage>(
    `/api/league/coverage?league_id=${encodeURIComponent(leagueId)}`,
  );
}

// ── League summary ────────────────────────────────────────────────
// Roll-up shown on the League tab. Backend: GET /api/league/summary
//
// NB: deliberately named LeagueSummaryRollup, not LeagueSummary, to
// avoid colliding with the LeagueSummary in shared/types.ts (which
// describes a Sleeper league as the picker sees it — totally different
// shape). IDE auto-import + grep both stay unambiguous this way.
export interface LeagueSummaryRollup {
  league_id: string;
  league_name?: string;
  default_scoring?: string | null;
  // Mirror the Matches tab's segments (feedback #91): mutual = non-dismissed
  // trade_matches rows; awaiting = one-sided likes not yet matured.
  matches_mutual?: number;
  matches_awaiting?: number;
  // Deprecated status-split counts — servers still send them for pre-1.4
  // builds; new UI must not read them.
  matches_pending?: number;
  matches_accepted?: number;
  // FB #41 — TOTAL teams in the league (caller included). Sleeper's
  // total_rosters when the backend has it; else leaguemates_total + 1.
  // Prefer this over deriving the count from leaguemates_total.
  total_teams?: number;
  leaguemates_total?: number;
  leaguemates_joined?: number;
  leaguemates_unlocked_1qb?: number;
  leaguemates_unlocked_sf?: number;
  // Optional richer fields the backend may already return
  members?: Array<{
    user_id: string;
    username?: string;
    display_name?: string;
    avatar?: string | null;
    joined?: boolean;
    unlocked_1qb?: boolean;
    unlocked_sf?: boolean;
  }>;
}
export async function getLeagueSummary(leagueId: string) {
  return api.get<LeagueSummaryRollup>(
    `/api/league/summary?league_id=${encodeURIComponent(leagueId)}`,
  );
}

// ── Leaguemate roster ──────────────────────────────────────────────
// Backend: GET /api/league/members. Powers the "Leaguemates" roster
// list on the League tab (joined ✓ / not-joined). Sorted joined first
// alpha, then not-joined alpha.
export interface LeagueMember {
  user_id: string;
  username: string;
  display_name: string;
  avatar: string | null;
  joined: boolean;
}
export async function getLeagueMembers(leagueId: string) {
  return api.get<{ members: LeagueMember[] }>(
    `/api/league/members?league_id=${encodeURIComponent(leagueId)}`,
  );
}

// ── League scoring format (auto-detected from Sleeper metadata) ────────
// GET /api/league/format-stats — the backend detects each league's format
// from Sleeper roster_positions / scoring_settings (SUPER_FLEX or 2 QB
// slots, or TE-premium bonus → 'sf_tep'; otherwise '1qb_ppr') and stores
// it on the leagues row. `default_scoring` is that detected value — the
// league-driven format default (feedback #80 / #89). The per-format
// ranking counts also on this payload are unused on mobile today.
export interface LeagueFormatStats {
  league_id: string;
  default_scoring: ScoringFormat;
  formats: Record<string, { ranking_count: number }>;
}
export async function getLeagueFormatStats(leagueId: string) {
  return api.get<LeagueFormatStats>(
    `/api/league/format-stats?league_id=${encodeURIComponent(leagueId)}`,
  );
}

// ── Copy tiers from one scoring format to the other ───────────────────
// POST /api/tiers/copy-from-format
//
// VALUE-AWARE copy (#124): the backend keeps the user's per-position
// rank order from `fromFormat` but re-seeds each player's value (and
// therefore tier label) from `toFormat`'s consensus at that rank —
// tier labels are pick-denominated and the formats' value curves
// differ, so labels do NOT carry over verbatim (QBs shift most).
// Response carries `mapping: 'value_rank'`.
//
// Sends X-Scoring-Format: toFormat so the backend's `_active_format`
// resolves to the target format explicitly — without this, a user who
// landed on Tiers already on SF TEP without ever toggling the format in
// this session would have sess['active_format'] still set to the
// session_init default (1qb_ppr), the endpoint would see from==to and
// error. Mirrors the web `onCopyTiersFromOtherFormat` belt-and-suspenders
// pattern (header AND body to_format).
//
// Destructive: replaces the target format's existing tier overrides
// wholesale. Caller should confirm before invoking.
export interface CopyTiersResponse {
  ok: boolean;
  from_format?: ScoringFormat;
  to_format?: ScoringFormat;
  mapping?: string; // 'value_rank' since #124
  position_counts?: Record<string, number>;
  total?: number;
  error?: string;
}
export async function copyTiersFromFormat(
  fromFormat: ScoringFormat,
  toFormat: ScoringFormat,
): Promise<CopyTiersResponse> {
  return api.post<CopyTiersResponse>(
    '/api/tiers/copy-from-format',
    { from_format: fromFormat, to_format: toFormat },
    { headers: { 'X-Scoring-Format': toFormat } },
  );
}
// ── League member unlock states (B7 — flag `league.unlock_badges_per_member`)
// Backend: GET /api/league/member-unlock-states. When the flag is off the
// backend returns `{members: [], flag_off: true}`. Used to chip each
// leaguemate row with "✓ Unlocked" / "in progress" on LeagueScreen.
export interface LeagueMemberUnlockState {
  user_id: string;
  username: string;
  display_name: string;
  avatar: string | null;
  joined: boolean;
  unlocked_formats: string[];   // e.g. ["1qb_ppr", "sf_tep"]
  unlocked_count: number;
  has_ranking_method: boolean;
}
export async function getLeagueMemberUnlockStates(leagueId: string) {
  return api.get<{ members: LeagueMemberUnlockState[]; flag_off?: boolean }>(
    `/api/league/member-unlock-states?league_id=${encodeURIComponent(leagueId)}`,
  );
}

// ── Activity feed (B7 — flag `league.activity_feed`) ───────────────
// Backend: GET /api/league/activity?league_id=...&limit=20
// Response shape (per backend/database.py:load_league_activity):
//   { events: [{ts, emoji, message, actor_user_id, event_type}, ...] }
// When the flag is off the backend returns {events: [], flag_off: true}.
// We normalise to ActivityEvent on the client so screen code sees a stable
// shape regardless of which backend key naming wins.
interface RawActivityRow {
  ts: string;
  emoji?: string;
  message: string;
  actor_user_id: string | null;
  event_type: string;
}
export async function getActivityFeed(
  leagueId: string,
  limit?: number,
): Promise<{ events: ActivityEvent[] }> {
  const qs =
    `league_id=${encodeURIComponent(leagueId)}` +
    (limit ? `&limit=${encodeURIComponent(String(limit))}` : '');
  const raw = await api.get<{ events: RawActivityRow[]; flag_off?: boolean }>(
    `/api/league/activity?${qs}`,
  );
  const rows = raw?.events || [];
  // Pull `@handle` from the backend's pre-formatted message as a best-effort
  // username — the activity row's own user table lookup already shaped this
  // string, so re-extracting it avoids a second roundtrip.
  const events: ActivityEvent[] = rows.map((r, i) => {
    const match = r.message?.match(/@([A-Za-z0-9_.\-]+)/);
    return {
      id:          `${r.ts || ''}-${r.actor_user_id || 'system'}-${i}`,
      occurred_at: r.ts,
      user_id:     r.actor_user_id || '',
      username:    match ? match[1] : '',
      event_type:  r.event_type,
      summary:     r.message,
      emoji:       r.emoji,
    };
  });
  return { events };
}

// ── Contrarian leaderboard (B7) ─────────────────────────────────────
// Backend: GET /api/league/contrarian?league_id=...&format=...
// Returns a per-position breakdown of {most_contrarian, most_consensus}.
// To surface a single sorted leaderboard on mobile, we flatten across
// positions: each user's `divergence_score` is the mean of their per-
// position deviations (deviation = mean abs ELO diff vs community).
interface RawContrarianUser {
  user_id: string;
  username: string;
  deviation: number;
  player_count?: number;
}
interface RawContrarianPositionBlock {
  most_contrarian: RawContrarianUser[];
  most_consensus:  RawContrarianUser[];
  ranked_users:    number;
  player_count:    number;
}
interface RawContrarianResponse {
  league_id: string;
  format: string;
  insufficient_data: boolean;
  ranked_users?: number;
  needed?: number;
  message?: string;
  qb: RawContrarianPositionBlock | null;
  rb: RawContrarianPositionBlock | null;
  wr: RawContrarianPositionBlock | null;
  te: RawContrarianPositionBlock | null;
}
export async function getContrarianLeaderboard(
  leagueId: string,
): Promise<{ rows: ContrarianRow[]; insufficient_data: boolean; message?: string }> {
  const raw = await api.get<RawContrarianResponse>(
    `/api/league/contrarian?league_id=${encodeURIComponent(leagueId)}`,
  );
  if (raw?.insufficient_data) {
    return { rows: [], insufficient_data: true, message: raw.message };
  }
  // Aggregate per user: collect every (user_id, deviation) tuple across all
  // four position blocks (both contrarian and consensus halves — they're the
  // top/bottom of the same per-user list). Average to get a single score.
  const acc = new Map<string, { username: string; sum: number; n: number }>();
  const blocks = [raw?.qb, raw?.rb, raw?.wr, raw?.te];
  for (const block of blocks) {
    if (!block) continue;
    const seenInBlock = new Set<string>();
    for (const u of [...(block.most_contrarian || []), ...(block.most_consensus || [])]) {
      if (!u?.user_id || seenInBlock.has(u.user_id)) continue;
      seenInBlock.add(u.user_id);
      const cur = acc.get(u.user_id);
      if (cur) {
        cur.sum += u.deviation;
        cur.n   += 1;
      } else {
        acc.set(u.user_id, { username: u.username, sum: u.deviation, n: 1 });
      }
    }
  }
  const rows: ContrarianRow[] = [...acc.entries()].map(([user_id, v]) => ({
    user_id,
    username:         v.username,
    divergence_score: Math.round((v.sum / v.n) * 10) / 10,
  }));
  rows.sort((a, b) => b.divergence_score - a.divergence_score);
  return { rows, insufficient_data: false };
}

// ── New trade partners (B7 — flag `trades.new_partners_alerts`) ────
// No dedicated backend route exists for this — the web client derives the
// banner client-side from a per-league localStorage diff of trade_ids.
// On mobile we derive newly-unlocked leaguemates from the activity feed:
// every time a tier_save unlocks a format, backend appends an event with
// event_type === 'unlock' (see backend/database.py:2315). Those entries
// are the canonical "this leaguemate just became tradeable" signal.
export async function getNewPartners(
  leagueId: string,
): Promise<{ partners: NewPartnerEntry[] }> {
  // Pull a generous window so a returning user catches anything they
  // missed; the screen filters out already-dismissed entries.
  const { events } = await getActivityFeed(leagueId, 50);
  const seen = new Set<string>();
  const partners: NewPartnerEntry[] = [];
  for (const e of events) {
    if (e.event_type !== 'unlock' || !e.user_id) continue;
    if (seen.has(e.user_id)) continue;
    seen.add(e.user_id);
    partners.push({
      user_id:           e.user_id,
      username:          e.username,
      newly_unlocked_at: e.occurred_at,
    });
  }
  // Newest unlock first
  partners.sort((a, b) => (a.newly_unlocked_at < b.newly_unlocked_at ? 1 : -1));
  return { partners };
}

// ── Portfolio (cross-league exposure) ─────────────────────────────
// Backend: GET /api/portfolio.
// Server returns rows shaped like:
//   { player_id, name, pos, exposure (int), total_leagues,
//     leagues: [{league_id, league_name}, ...],
//     league_names: [..] }                     // legacy, kept for compat
// We adapt to the richer PortfolioRow shape the mobile UI expects.
// The backend doesn't currently emit per-league tier info, so each
// exposure entry is marked 'pool' — the UI shows a neutral chip.
//
// Prefer the structured `leagues` list so identically-named leagues
// (Sleeper allows duplicate display names across a user's leagues)
// keep distinct league_ids and don't render as visual duplicates that
// look like double-counting. Fall back to `league_names` only when an
// older backend is still in front.
export interface PortfolioApiLeague {
  league_id: string;
  league_name: string;
}
export interface PortfolioApiRow {
  player_id: string;
  name: string;
  pos: string;
  exposure: number;
  total_leagues: number;
  leagues?: PortfolioApiLeague[];
  league_names?: string[];
}
export async function getPortfolio(leagueIds?: string[]): Promise<{ players: PortfolioRow[] }> {
  // FB-48: scope to the current-season league list. Sleeper mints a new
  // league_id each season, so the backend's league_members table also holds
  // last season's instance of each league — unscoped, every carried-over
  // player double-counts.
  const qs = leagueIds && leagueIds.length > 0
    ? `?league_ids=${encodeURIComponent(leagueIds.join(','))}`
    : '';
  const raw = await api.get<{ players: PortfolioApiRow[] }>(`/api/portfolio${qs}`);
  const players: PortfolioRow[] = (raw?.players || []).map((r) => {
    const exposureSource: PortfolioApiLeague[] = r.leagues && r.leagues.length > 0
      ? r.leagues
      : (r.league_names || []).map((nm) => ({ league_id: nm, league_name: nm }));
    return {
      player: {
        id: r.player_id,
        name: r.name || r.player_id,
        position: r.pos || '',
      },
      exposure: exposureSource.map((lg) => ({
        league_id: lg.league_id,
        league_name: lg.league_name,
        tier: 'pool' as PortfolioTier,
      })),
      total_leagues: r.total_leagues || exposureSource.length,
    };
  });
  return { players };
}

// ── Connect another league (paste a Sleeper URL) ──────────────────
// Backend: POST /api/league/parse-url. Returns
//   { platform, league_id, name, supported }
// We surface the same data shape callers expect: { ok, league_id, league_name }.
// Non-Sleeper platforms (supported=false) are reported as a soft error so
// the caller can render a friendly "Sleeper-only for now" toast.
export interface ConnectLeagueResult {
  ok: boolean;
  league_id: string;
  league_name: string;
  /** Sleeper / espn / mfl — set by the backend's URL parser. */
  platform: 'sleeper' | 'espn' | 'mfl' | string;
  /** When false, backend recognized the URL but full sync isn't wired up
   *  yet (ESPN / MFL today). UI should keep the user where they are. */
  supported: boolean;
}
// ── League power rankings (#142/#144) ─────────────────────────────
// Backend: GET /api/league/power-rankings. Every team in the league
// ranked by summed roster value; each team carries its full roster
// (grouped by position, value-desc within group) so the drill-in needs
// no second call. basis 'consensus' = universal-pool values;
// 'personal' = the caller's own board with consensus fallback for
// unranked players; 'redraft' is a reserved probe — the backend answers
// 501 not_available (dynasty values only today), so the UI renders it
// as a disabled "(soon)" chip and never actually requests it.
export type PowerRankingsBasis = 'consensus' | 'personal' | 'redraft';

export interface PowerRankedPlayer {
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  age: number | null;
  value: number;
}

export interface PowerRankedTeam {
  rank: number;
  user_id: string;
  username: string;
  display_name: string;
  is_you: boolean;
  total_value: number;
  positions: Record<'QB' | 'RB' | 'WR' | 'TE', { count: number; value: number }>;
  /** Grouped QB→RB→WR→TE→other, value-desc within each group (#144). */
  roster: PowerRankedPlayer[];
}

export interface PowerRankingsResponse {
  league_id: string;
  basis: PowerRankingsBasis;
  scoring_format: string;
  teams: PowerRankedTeam[];
}

export async function getPowerRankings(
  leagueId: string,
  basis: Exclude<PowerRankingsBasis, 'redraft'> = 'consensus',
) {
  return api.get<PowerRankingsResponse>(
    `/api/league/power-rankings?league_id=${encodeURIComponent(leagueId)}&basis=${basis}`,
  );
}

export async function connectLeague(sleeperUrl: string): Promise<ConnectLeagueResult> {
  const res = await api.post<{
    platform: string;
    league_id: string;
    name?: string | null;
    supported: boolean;
  }>('/api/league/parse-url', { url: sleeperUrl });
  return {
    ok: !!res?.supported && !!res?.league_id,
    league_id: res?.league_id || '',
    league_name: res?.name || (res?.league_id ? `League ${res.league_id}` : ''),
    platform: res?.platform || '',
    supported: !!res?.supported,
  };
}

// ── Free-agent finder (#143) ──────────────────────────────────────────────
// Backend: GET /api/league/free-agents?league_id=...&position=RB
// FA pool = universal pool minus every rostered player in the league,
// ranked by the CALLER'S board value (consensus fallback for unranked
// players — `user_has_rankings: false` means the whole list is consensus).
// `drop_suggestion` = the caller's lowest-valued same-position rostered
// player strictly below the FA's value (null when none); `delta` is the
// add/drop value gain. `pos_rank` is the FA's rank within its position
// across ALL free agents, so it's stable under position filters.
// Read-gated like /api/rankings (priced by the caller's board).
export interface FreeAgentDropSuggestion {
  player_id: string;
  name: string;
  position: string;
  value: number;
  delta: number;
}
export interface FreeAgentRow {
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  age: number | null;
  value: number;
  pos_rank: number;
  drop_suggestion: FreeAgentDropSuggestion | null;
}
export interface FreeAgentsResponse {
  league_id: string;
  scoring_format: ScoringFormat;
  position: 'QB' | 'RB' | 'WR' | 'TE' | 'ALL';
  user_has_rankings: boolean;
  free_agents: FreeAgentRow[];
}
export async function getFreeAgents(
  leagueId: string,
  position?: 'QB' | 'RB' | 'WR' | 'TE' | 'ALL',
) {
  const qs =
    `league_id=${encodeURIComponent(leagueId)}` +
    (position && position !== 'ALL' ? `&position=${position}` : '');
  return api.get<FreeAgentsResponse>(`/api/league/free-agents?${qs}`);
}
