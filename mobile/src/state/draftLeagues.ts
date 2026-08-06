import AsyncStorage from '@react-native-async-storage/async-storage';
import { getLeagues } from '../api/sleeper';
import { useSession, NO_LEAGUE_ID } from './useSession';
import type { LeagueSummary } from '../shared/types';
import { useFeatureFlags } from './useFeatureFlags';

// rookie-draft — the seasonal Draft tab's data source (operator decision
// "draft-surface placement", 2026-08-06, option A′).
//
// The tab bar is GLOBAL while #207's draft verdict is PER-LEAGUE, and
// `Tab.Navigator` decides its route array at first mount (the same contract
// `initialRouteName` and #244's completion-aware Rank routing already live
// under). So the predicate has to be answerable SYNCHRONOUSLY, pre-mount,
// over EVERY linked league — no round-trip, no mid-session tab insertion.
//
// Same two-beat shape as `quicksetProgress.ts` (#244):
//   • hydrate<X>()  — AsyncStorage read in the App.tsx boot gate (ms-fast,
//     awaited before the navigator mounts).
//   • refresh<X>()  — fire-and-forget after revalidateSession; persists the
//     snapshot for the NEXT launch. A league that starts (or finishes) its
//     draft mid-session therefore changes the tab bar at most once per
//     launch — never a navigator reshuffle under the user's thumb.
//
// THE PREDICATE (why `not_drafted` + `high` and nothing else):
// `backend/draft_status.py` only ever returns `not_drafted` at HIGH
// confidence from a PLATFORM signal — Sleeper's `sleeper_verdict` reaching
// its "every current-season rookie-shaped draft is pre_draft/drafting"
// branch, or MFL's `mfl_verdict` seeing a rookie-sized grid with unmade
// picks. Both mean exactly what the operator decision asks for: a
// current-season, rookie-shaped draft object exists and has not run.
// `not_drafted` at MEDIUM comes from the rosters heuristic (`rosters_verdict`
// — "no rookies on any roster"), which says nothing about a draft object
// existing, so it must NOT show the tab. `drafted` / `unknown` / no row are
// hidden by the same rule. Sleeper publishes no trustworthy scheduled start
// time, so "imminent" can only ever mean "a draft object exists and hasn't
// run" — there is no countdown to invent.
//
// Fail-safe matches `current_year_picks_visible()`: absence is
// self-correcting (the Acquire tab's Draft chip is the permanent home and is
// always there when `draft.room` is on), a tab that lies is not.

const KEY = 'ftf_draft_leagues_v1';

/** A linked league with a current-season rookie draft that hasn't run. */
export interface QualifyingDraftLeague {
  league_id: string;
  name: string;
}

let cached: QualifyingDraftLeague[] = [];

/** The predicate, in one place. Exported for tests and for any surface that
 *  needs to ask the same question of a league it already holds. */
export function leagueQualifiesForDraftTab(
  lg: LeagueSummary,
  mflBound: boolean = false,
): boolean {
  if (lg.draft_status !== 'not_drafted' || lg.draft_status_confidence !== 'high') {
    return false;
  }
  // A qualifying verdict is necessary but NOT sufficient: the tab must never
  // lead to a room that cannot render a board. `draft_board_service` only has
  // a bound adapter for Sleeper, and for MFL only behind `draft.mfl` — an
  // unbound platform returns `unsupported_board()`, i.e. a tab whose only
  // content is "not available for this platform yet". Bind the predicate to
  // what the room can actually serve.
  const platform = String(lg.platform || 'sleeper').toLowerCase();
  if (platform === 'sleeper') return true;
  if (platform === 'mfl') return mflBound;
  return false; // espn / fleaflicker / unknown — no adapter, no tab
}

function pick(leagues: LeagueSummary[], mflBound: boolean): QualifyingDraftLeague[] {
  return leagues
    .filter((lg) => lg.league_id && lg.league_id !== NO_LEAGUE_ID)
    .filter((lg) => leagueQualifiesForDraftTab(lg, mflBound))
    .map((lg) => ({ league_id: String(lg.league_id), name: lg.name || 'League' }));
}

/** Boot-gate leg (App.tsx): restore the snapshot so
 *  `qualifyingDraftLeagues()` is answerable before TabNav mounts. */
export async function hydrateDraftLeagues(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      cached = parsed.filter(
        (r: any) => r && typeof r.league_id === 'string' && typeof r.name === 'string',
      );
    }
  } catch {
    /* non-fatal — no snapshot means no tab, the fail-safe direction */
  }
}

/** Detached refresh (after revalidateSession): re-read the league list and
 *  persist the qualifying subset for the next launch's tab decision. Never
 *  throws — offline / signed-out keeps the previous snapshot. Deliberately
 *  does NOT touch `useSession.leagues`: the switcher's list has its own
 *  refresh cadence (sign-in, league picker) and must not be churned here. */
export async function refreshDraftLeagues(): Promise<void> {
  const s = useSession.getState();
  const userId = s.user?.user_id;
  if (!userId || s.user?.account_only || s.isDemo) return;
  try {
    const leagues = await getLeagues(userId);
    cached = pick(leagues, !!useFeatureFlags.getState().flags['draft.mfl']);
    await AsyncStorage.setItem(KEY, JSON.stringify(cached));
  } catch {
    /* offline or unauthenticated — keep the previous snapshot */
  }
}

/** Every linked league with a current-season rookie draft that hasn't run.
 *  Sync read over hydrated state — safe for a first-mount tab decision. */
export function qualifyingDraftLeagues(): QualifyingDraftLeague[] {
  return cached;
}

/** Test seam: replace the in-memory snapshot without touching storage. */
export function _setDraftLeaguesForTest(rows: QualifyingDraftLeague[]): void {
  cached = rows;
}
