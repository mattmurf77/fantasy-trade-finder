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

export interface LeagueCoverage {
  league_id: string;
  total_opponents: number;
  ranked_opponents: number;
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
  matches_pending?: number;
  matches_accepted?: number;
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

// ── Copy tiers from one scoring format to the other ───────────────────
// POST /api/tiers/copy-from-format
//
// Copies the user's tier assignments (tier label + within-tier rank) from
// `fromFormat` into `toFormat`. Backend handles the per-format band
// translation: a player at QB1 Elite in 1QB PPR stays at QB1 Elite in SF
// TEP, with new ELO values appropriate to SF TEP's bands.
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
export async function getPortfolio(): Promise<{ players: PortfolioRow[] }> {
  const raw = await api.get<{ players: PortfolioApiRow[] }>('/api/portfolio');
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
