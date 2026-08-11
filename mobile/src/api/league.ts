import { api } from './client';
import type { PickSource } from './pickAssignment';
import type {
  ScoringFormat,
  ActivityEvent,
  ContrarianRow,
  NewPartnerEntry,
  PortfolioRow,
  PortfolioTier,
  Tier,
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

// ── Asset preferences (untouchables + targets + not-interested, #2/#163) ──
// Backend: GET/POST /api/league/asset-prefs. `untouchable` = never offer
// this player FROM the caller's roster in generated trades (feedback #95);
// `target` = bias suggestions toward acquiring the player;
// `not_interested` = never offer this player TO the caller (receive-side
// exclusion, #163 — the caller can still trade the player away). A player
// holds at most one tag per league; list: 'none' removes the tag.
// Enum strings are a cross-client contract (docs/cross-client-invariants.md).

export interface AssetPrefs {
  untouchables: string[];
  targets: string[];
  /** #163 — absent on pre-#163 servers; treat missing as []. */
  not_interested?: string[];
}

export type AssetPrefList = 'untouchable' | 'target' | 'not_interested' | 'none';

export async function getAssetPrefs(leagueId: string) {
  return api.get<AssetPrefs>(
    `/api/league/asset-prefs?league_id=${encodeURIComponent(leagueId)}`,
  );
}

export async function setAssetPref(
  leagueId: string,
  playerId: string,
  list: AssetPrefList,
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
  // ranked_formats (#191/#192, additive — absent on old servers): which
  // scoring formats the member has stored rankings in, so clients can
  // distinguish ranked-in-this-format (R) from ranked-in-the-other-only
  // (derivable, R*) from never-ranked (NR). has_rankings stays the
  // format-blind any-format boolean.
  members?: Array<{
    user_id: string;
    username: string;
    has_rankings: boolean;
    ranked_formats?: string[];
  }>;
}
export async function getLeagueCoverage(leagueId: string) {
  return api.get<LeagueCoverage>(
    `/api/league/coverage?league_id=${encodeURIComponent(leagueId)}`,
  );
}

// ── Owned draft picks (#158) ──────────────────────────────────────
// Backend: GET /api/league/picks. Each pick is a per-league owned asset
// priced on the engine value scale (pool_value) with a display label
// ("2027 1st", "2026 2nd (from Jared)"). picks_supported=false for ESPN
// leagues (players-only) so the calculator can show an honest note.
export interface OwnedPick {
  pick_id: string;
  league_id: string;
  season: number;
  round: number;
  owner_user_id: string;
  owner_username?: string | null;
  original_user_id?: string | null;
  original_username?: string | null;
  is_traded?: number;
  /** Legacy 0-100 round-tier value (pick-share ratios). */
  pick_value?: number | null;
  /** Engine/calculator value scale — what the calculator prices on. */
  pool_value?: number | null;
  /** Display label, e.g. "2027 1st". */
  label: string;
  /** draft-extensions W3 M-C (D17) — `draft_picks.source`. `'user'` means a
   *  LEAGUEMATE asserted this ownership on the ESPN assignment grid and no
   *  platform will ever confirm it, so every surface that renders this
   *  pick's PRICE must carry `MemberEnteredMarker`. Absent / `'platform'`
   *  is platform truth (every pre-W3 row reads as platform — no backfill
   *  ran). Server-authoritative: the client never infers it. */
  source?: PickSource | null;
}
export interface LeaguePicksResponse {
  my_picks: OwnedPick[];
  all_picks: OwnedPick[];
  /** false for ESPN leagues — clients show a "picks unavailable" note. */
  picks_supported: boolean;
}
export async function getLeaguePicks(leagueId: string) {
  return api.get<LeaguePicksResponse>(
    `/api/league/picks?league_id=${encodeURIComponent(leagueId)}`,
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
export async function getLeagueMembers(
  leagueId: string,
  opts?: { includeSelf?: boolean },
) {
  const includeSelf = opts?.includeSelf ? '&include_self=1' : '';
  return api.get<{ members: LeagueMember[] }>(
    `/api/league/members?league_id=${encodeURIComponent(leagueId)}${includeSelf}`,
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
  /** #277/#278 — pick-value ladder tier walked off the SAME raw Elo (board
   *  or consensus seed) `value` was priced from, via the backend's
   *  canonical RankingService.tier_for_elo. Never re-derive a tier from
   *  `value` (elo_to_value scale ≠ the tier bands' Elo scale). Null for
   *  unpriceable rows (out-of-pool K/DEF); absent on old servers. */
  tier?: Tier | null;
}

export interface PowerRankedTeam {
  rank: number;
  user_id: string;
  username: string;
  display_name: string;
  is_you: boolean;
  total_value: number;
  /** #279 — pick-equivalent label ("≈14 firsts") for the team total. Present
   *  ONLY when the caller is targeted by the operator-only
   *  `aggregate_tier_labels` experiment (docs/feedback/items/
   *  279-aggregate-tier-labels/status.md); absent for everyone else and on
   *  old servers — clients must fall back to the numeric `total_value`.
   *  #285 (docs/feedback/items/285-pick-sums/status.md): the number is
   *  `positions_value`'s value→pick-equivalent firsts (same formula as "a
   *  Late 2nd" on trade cards) PLUS a literal count of the team's owned
   *  picks (1st = 1.0, 2nd = 1/3.5, 3rd+ = 0) — NOT `total_value`, which
   *  prices picks in dollar space and would double-count if added here. */
  total_value_label?: string;
  positions: Record<'QB' | 'RB' | 'WR' | 'TE', {
    count: number;
    value: number;
    /** #279 — pick-equivalent label for this position's `value`, same
     *  gating as `total_value_label` above. */
    value_label?: string;
  }>;
  /** Grouped QB→RB→WR→TE→other, value-desc within each group (#144). */
  roster: PowerRankedPlayer[];
  /** #14 FR1 — draft-capital group, priced via the generic pick ladder
   *  (pick_pool_value; year-discounted Mid tier). total_value INCLUDES this;
   *  positions_value is the positions-only sum. Absent on old servers. */
  picks?: {
    count: number;
    value: number;
    /** draft-extensions W3 M-C (D17/S2): `pick_id`/`season`/`source` ride
     *  each item so an ASSERTED pick can be marked and corrected from the
     *  draft-capital group. All three are optional — a Sleeper/MFL payload
     *  and any pre-M-C server omit them, and an item without `source ===
     *  'user'` renders exactly as it does today. */
    items: Array<{
      label: string;
      value: number;
      pick_id?: string | null;
      season?: number | null;
      source?: PickSource | null;
    }>;
  };
  positions_value?: number;
  /** League Analyzer replication (2026-07-26) — the team's DERIVED
   *  value-optimal starting lineup: the league's starting-slot template
   *  (Sleeper roster_positions) filled with the team's highest-value
   *  eligible players on the SAME basis as this payload's values (so a
   *  personal board reshapes the split). No per-week lineup data is read.
   *  null (or absent on old servers) = template unknown → the client hides
   *  the All/Starters/Bench filter (never fabricates). */
  starters?: string[] | null;
}

export interface PowerRankingsResponse {
  league_id: string;
  basis: PowerRankingsBasis;
  scoring_format: string;
  teams: PowerRankedTeam[];
  /** #14 FR6 — server compute time (ISO). Absent on old servers. */
  updated_at?: string;
  /** 2026-07-26 — true only when EVERY team carries a derived `starters`
   *  list and at least one is non-empty. Gates the All/Starters/Bench
   *  segmented control; absent on old servers (treat as false). */
  starters_available?: boolean;
}

/** #14 — rank chip for league cards. Consensus basis; deliberately open
 *  read (league-shared aggregate, no personal data). */
export interface RankChip {
  rank: number;
  team_count: number;
  basis: 'consensus';
  updated_at?: string;
}

export async function getRankChip(leagueId: string) {
  return api.get<RankChip>(
    `/api/league/rank-chip?league_id=${encodeURIComponent(leagueId)}`,
  );
}

export async function getPowerRankings(
  leagueId: string,
  basis: Exclude<PowerRankingsBasis, 'redraft'> = 'consensus',
) {
  return api.get<PowerRankingsResponse>(
    `/api/league/power-rankings?league_id=${encodeURIComponent(leagueId)}&basis=${basis}`,
  );
}

// ── League outlook — playoff / championship odds (#169, flag `outlook.odds`) ──
// Backend: GET /api/league/outlook?league_id=...&basis=consensus|personal
// The playoff/title-odds layer from the #169 "outlook odds" vision. Behind the
// DARK `outlook.odds` flag — the endpoint 404s until the modeling backend
// (league-state season simulator) ships, so callers MUST gate on the flag
// before requesting (see LeagueSummaryScreen). Never add `outlook.odds` to the
// launched-flag defaults.
//
// Every odds figure is a PROJECTION, not a settled fact. `meta.beta` /
// `meta.is_preseason` mark the numbers provisional; the UI labels the whole
// layer "Projected · preseason · beta" and NEVER shows a bare authoritative
// percentage — `playoff_pct` renders as a three-band chip whose keys,
// thresholds and colors are a cross-client invariant (see
// docs/cross-client-invariants.md § "Playoff outlook bands"). Percentages are
// 0..1 fractions. Teams arrive pre-sorted by `odds.playoff_pct` descending —
// which is NOT the projected-standings order; a surface presenting the rows AS
// the standings re-sorts by `odds.projected_seed` (LeagueSummaryScreen does).
export type OutlookBasis = 'consensus' | 'personal';

// Backend strength-source keys → friendly captions are mapped in the screen.
// Kept an open union (`string & {}`) so an unrecognised future key degrades to
// a generic caption instead of breaking the type.
export type OutlookStrengthSource =
  | 'roster_value'
  | 'trailing_scores'
  | 'blended'
  | (string & {});

// How much of the league's STARTING lineup the dynasty value board can price
// (BUG-5, 2026-08-10). The board carries QB/RB/WR/TE only, so an IDP or kicker
// league prices a minority of its slots — 7 of 15 in the operator's FFv3
// league. `fraction` is 0..1 over `total_slots`; `unpriced_slots` names the
// blind ones in roster order (e.g. ['K','DL','DL','LB','LB','DB','DB',
// 'IDP_FLEX']) so a caption can be specific rather than vague.
//
// `affects_strength` is the honest half: only the board-reading strength
// sources (`roster_value`, `blended`) consume the board at all, so a
// `trailing_scores` payload reports the coverage fact with
// `affects_strength: false` and its odds do not depend on the board.
// A client should qualify the numbers ("based on your offensive starters")
// only when `affects_strength` is true AND `fraction` < 1.
export interface OutlookPricedSlotCoverage {
  fraction: number; // 0..1
  total_slots: number;
  priced_slots: number;
  unpriced_slots: string[];
  affects_strength: boolean;
}

export interface OutlookMeta {
  strength_source: OutlookStrengthSource;
  completed_weeks: number;
  regular_season_weeks: number;
  playoff_slots: number;
  byes: number;
  sims: number;
  seed: number;
  is_preseason: boolean;
  beta: boolean;
  // Null when the measurement was not taken (the serializer emits null rather
  // than a fabricated 1.0). Optional so a pre-2026-08-10 server still parses.
  priced_slot_coverage?: OutlookPricedSlotCoverage | null;
}

export interface OutlookTeam {
  roster_id: number;
  user_id: string;
  username: string;
  display_name: string;
  is_you: boolean;
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  // Null when the strength provider produced no estimate for the team
  // (backend/outlook/serialize.py emits null rather than a fake number).
  strength: { mu: number | null; sigma: number | null };
  odds: {
    playoff_pct: number; // 0..1 — rendered as a BAND, never as a raw number
    bye_pct: number;     // 0..1
    /** SERVED BUT UNRENDERABLE (calibration-combined-2026-08-10.md §7): title
     *  odds have no demonstrated skill — the skill CI spans zero and 3 of 6
     *  backtested league-seasons do worse than a constant. No client may show
     *  this at any week, in any form, banded or numeric. The field stays on
     *  the type because the backend still serves it. */
    title_pct: number;   // 0..1
    projected_wins: number;
    projected_seed: number;
  };
}

export interface LeagueOutlookResponse {
  league_id: string;
  platform: string;
  basis: OutlookBasis;
  // Null when the session has no active scoring format attached to the run.
  scoring_format: string | null;
  meta: OutlookMeta;
  teams: OutlookTeam[];
}

export async function getOutlook(
  leagueId: string,
  basis: OutlookBasis = 'consensus',
) {
  return api.get<LeagueOutlookResponse>(
    `/api/league/outlook?league_id=${encodeURIComponent(leagueId)}&basis=${basis}`,
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
  /** #277 — see FreeAgentRow.tier. Absent on old servers. */
  tier?: Tier | null;
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
  /** #277 — pick-value ladder tier walked off the SAME raw board Elo
   *  `value` was priced from (backend RankingService.tier_for_elo). Never
   *  re-derive a tier from `value` client-side. Absent on old servers. */
  tier?: Tier | null;
}
// #179 — roster-capacity context for the claim sheet. Sleeper leagues
// only (null for platform/demo leagues); all fields best-effort — null
// when the backend couldn't resolve them. `limit` counts lineup+bench+IR+
// taxi slots; `my_count` is the caller's current Sleeper roster headcount;
// `open_slots` = max(limit - my_count, 0), null when either side is
// unknown (absent on pre-claim-sheet servers).
export interface FreeAgentRosterCapacity {
  my_count: number | null;
  limit: number | null;
  open_slots?: number | null;
}
// #179 claim sheet — the league's waiver context (Sleeper only, null
// otherwise). `faab` is the CALLER'S budget line and is null for
// priority-waiver leagues (type says which kind, so the sheet can say
// "waiver priority league" instead of showing a bid input).
export interface FreeAgentWaivers {
  type: 'faab' | 'rolling' | 'reverse_standings' | null;
  faab: {
    budget: number | null;
    used: number | null;
    remaining: number | null;
  } | null;
}
// #179 claim sheet — the caller's roster priced on their board, sorted
// value-ASCENDING (least valuable first), capped at 8. Untouchables
// (asset_prefs) never appear; `untouchables_excluded` counts how many were
// withheld so the sheet can say so.
export interface FreeAgentDropCandidate {
  id: string;
  name: string;
  position: string;
  value: number;
  /** #277 — see FreeAgentRow.tier. Absent on old servers. */
  tier?: Tier | null;
}
export interface FreeAgentDropCandidates {
  players: FreeAgentDropCandidate[];
  untouchables_excluded: number;
}
export interface FreeAgentsResponse {
  league_id: string;
  scoring_format: ScoringFormat;
  position: 'QB' | 'RB' | 'WR' | 'TE' | 'ALL';
  user_has_rankings: boolean;
  free_agents: FreeAgentRow[];
  /** Absent on pre-#179 servers. */
  roster_capacity?: FreeAgentRosterCapacity | null;
  /** Absent on pre-claim-sheet servers. Sleeper leagues only. */
  waivers?: FreeAgentWaivers | null;
  /** Absent on pre-claim-sheet servers. Sleeper leagues only. */
  drop_candidates?: FreeAgentDropCandidates | null;
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

// ── Invite meta (P0-3) ───────────────────────────────────────────────────
/** P0-3 — public league name for an invite banner. Unauthenticated,
 *  short-deadline, NEVER throws: a null return means "say 'their league'".
 *
 *  ONE call site by design (SignInScreen) — see lld-p0-3 §2.0. A second call
 *  site on a screen that can run with an UNSEEDED league id books a
 *  `vcr_misses` increment under the hermetic harness and fails the whole sim
 *  run (`mobile/scripts/sim-run.sh`), so this is a rail, not a style note. */
export interface InviteMeta {
  league_id: string;
  league_name: string | null;
  platform: string | null;
}

export async function fetchInviteMeta(leagueId: string): Promise<InviteMeta | null> {
  if (!leagueId) return null;
  const ac = new AbortController();
  // 4s deadline, not the client default: a sign-in screen must never wait on
  // a cosmetic string. (AbortSignal.timeout is not relied on — RN varies.)
  const t = setTimeout(() => ac.abort(), 4000);
  try {
    // skipAuth: the caller is a SIGNED-OUT screen; a stale token would be
    // meaningless and would let the 401-expiry hook fire on a cosmetic call.
    return await api.get<InviteMeta>(
      `/api/league/invite-meta?league_id=${encodeURIComponent(leagueId)}`,
      { skipAuth: true, signal: ac.signal },
    );
  } catch {
    // Swallow everything. `api_request_failed` still fires from the client
    // wrapper, so the failure stays observable without a UI state.
    return null;
  } finally {
    clearTimeout(t);
  }
}
