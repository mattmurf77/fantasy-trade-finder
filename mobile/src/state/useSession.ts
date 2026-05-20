import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { clearSessionToken, getSessionToken } from '../api/client';
import { initLeagueSession } from '../api/auth';
import { connectLeague as apiConnectLeague } from '../api/league';
import { getLeagues } from '../api/sleeper';
import { setUser as sentrySetUser } from '../observability/sentry';
import type { LeagueSummary } from '../shared/types';

// Storage keys kept identical to the web app where practical, so the server
// sees consistent shape from both clients.
const SU_KEY = 'sleeper_user';
const SL_KEY = 'sleeper_league';
// B3 — cache the multi-league list so a returning user sees the switcher
// populated without waiting for a Sleeper round-trip.
const SLG_KEY = 'sleeper_leagues';

export interface SavedUser {
  user_id: string;
  username: string;
  display_name: string;
  avatar_id: string | null;
}
export interface SavedLeague {
  league_id: string;
  league_name: string;
}

interface SessionState {
  user: SavedUser | null;
  league: SavedLeague | null;
  leagues: LeagueSummary[];         // cached list for the switcher
  hasToken: boolean;
  /** True while a switchLeague() call is in flight. UI uses this to
   *  disable the switcher rows / show a spinner. */
  switching: boolean;

  bootstrap: () => Promise<void>;
  setUser: (u: SavedUser | null) => Promise<void>;
  setLeague: (lg: SavedLeague | null) => Promise<void>;
  setLeagues: (lgs: LeagueSummary[]) => Promise<void>;
  /** Atomically swap the active league: re-runs initLeagueSession on the
   *  backend, then updates the persisted active league locally. Throws on
   *  failure; UI should wrap in try/catch. No-ops if `lg` matches the
   *  current league or another switch is in progress. */
  switchLeague: (lg: SavedLeague) => Promise<void>;
  /** B3 — Add another Sleeper league to the cached list. Calls
   *  /api/league/parse-url to validate the URL, fetches the freshest
   *  league list from Sleeper, persists it, then triggers a full
   *  session_init against the new league (so the rest of the app is
   *  pointed at it). Throws on backend failure; surfaces a
   *  non-Sleeper-platform soft error via the returned `result`. */
  connectLeague: (sleeperUrl: string) => Promise<{
    ok: boolean;
    league_id: string;
    league_name: string;
    platform: string;
    supported: boolean;
  }>;
  signOut: () => Promise<void>;
}

export const useSession = create<SessionState>((set, get) => ({
  user: null,
  league: null,
  leagues: [],
  hasToken: false,
  switching: false,

  bootstrap: async () => {
    const [userRaw, leagueRaw, leaguesRaw, tok] = await Promise.all([
      AsyncStorage.getItem(SU_KEY),
      AsyncStorage.getItem(SL_KEY),
      AsyncStorage.getItem(SLG_KEY),
      getSessionToken(),
    ]);
    let user: SavedUser | null = null;
    let league: SavedLeague | null = null;
    let leagues: LeagueSummary[] = [];
    try { if (userRaw)    user    = JSON.parse(userRaw); } catch {}
    try { if (leagueRaw)  league  = JSON.parse(leagueRaw); } catch {}
    try { if (leaguesRaw) {
      const parsed = JSON.parse(leaguesRaw);
      if (Array.isArray(parsed)) leagues = parsed;
    } } catch {}
    set({ user, league, leagues, hasToken: !!tok });
  },

  setUser: async (u) => {
    if (u) await AsyncStorage.setItem(SU_KEY, JSON.stringify(u));
    else   await AsyncStorage.removeItem(SU_KEY);
    set({ user: u });
    // Tag Sentry events with the Sleeper user_id + username for triage.
    // No-op when Sentry isn't initialized. Cleared on sign-out.
    sentrySetUser(u ? { id: u.user_id, username: u.username } : null);
  },

  setLeague: async (lg) => {
    if (lg) await AsyncStorage.setItem(SL_KEY, JSON.stringify(lg));
    else    await AsyncStorage.removeItem(SL_KEY);
    // When a league is pinned, a successful sessionInit just happened
    // upstream — which means a valid session token is now in secure-store.
    // Flip hasToken to true so consumers that gate on it (e.g. RootNav's
    // progressQuery) start working again. Without this, recovering from
    // a session-expired state would leave hasToken stuck at false even
    // though the new token is fine.
    set({ league: lg, hasToken: !!lg });
  },

  setLeagues: async (lgs) => {
    // Persist alongside the active league/user so the multi-league
    // switcher repopulates without a network round-trip on next launch.
    try {
      await AsyncStorage.setItem(SLG_KEY, JSON.stringify(lgs));
    } catch {
      /* non-fatal — cache is opportunistic */
    }
    set({ leagues: lgs });
  },

  switchLeague: async (lg) => {
    // Atomic check-and-acquire. Doing the guards inside the set() callback
    // means zustand serializes them — two near-simultaneous switchLeague
    // callers can't both observe `switching=false` and race past the
    // guard. The previous read-then-set pattern had a tiny but real
    // window between get() and set() where two callers could both
    // proceed (e.g. a push deep-link firing during a tap on the
    // LeagueSwitcherSheet). The UI's own busy lock prevented this in
    // practice, but the lower layer should be correct on its own.
    let acquired = false;
    let userSnapshot: SavedUser | null = null;
    set((state) => {
      if (state.switching) return state;                              // already swapping
      if (!state.user) return state;                                  // not signed in
      if (state.league?.league_id === lg.league_id) return state;     // same league, no-op
      acquired = true;
      userSnapshot = state.user;
      return { ...state, switching: true };
    });
    if (!acquired || !userSnapshot) return;

    try {
      // initLeagueSession owns the backend handshake (rosters → users →
      // /api/session/init). On success, persist the new active league.
      await initLeagueSession(userSnapshot, {
        league_id: lg.league_id,
        name:      lg.league_name,
      });
      await get().setLeague(lg);
    } finally {
      set({ switching: false });
    }
  },

  connectLeague: async (sleeperUrl) => {
    const state = get();
    if (!state.user) {
      return { ok: false, league_id: '', league_name: '', platform: '', supported: false };
    }
    // 1. Validate the URL with the backend. Sleeper-only is "supported";
    //    ESPN/MFL come back as supported=false so we bubble that up.
    const result = await apiConnectLeague(sleeperUrl);
    if (!result.ok) return result;

    // 2. Refresh the cached league list from Sleeper so the new league
    //    is in `leagues` for the switcher + Portfolio gate. This is
    //    authoritative — Sleeper's GET /v1/user/:id/leagues is what
    //    LeaguePickerScreen uses too.
    try {
      const lgs = await getLeagues(state.user.user_id);
      // Ensure the just-connected league is in the list. Sleeper returns
      // every NFL league the user is in, so this is usually a no-op, but
      // it guards against propagation delay.
      const hasIt = lgs.some((lg) => lg.league_id === result.league_id);
      const merged: LeagueSummary[] = hasIt
        ? lgs
        : [
            ...lgs,
            {
              league_id: result.league_id,
              name: result.league_name,
            },
          ];
      await get().setLeagues(merged);
    } catch {
      // Non-fatal — caller still gets ok=true; switcher may need a manual
      // refresh from LeaguePickerScreen.
    }

    // 3. Initialize a session against the new league and persist as
    //    active. Same handshake LeaguePickerScreen runs.
    await initLeagueSession(state.user, {
      league_id: result.league_id,
      name:      result.league_name,
    });
    await get().setLeague({
      league_id:   result.league_id,
      league_name: result.league_name,
    });
    return result;
  },

  signOut: async () => {
    await Promise.all([
      AsyncStorage.removeItem(SU_KEY),
      AsyncStorage.removeItem(SL_KEY),
      AsyncStorage.removeItem(SLG_KEY),
      clearSessionToken(),
    ]);
    set({ user: null, league: null, leagues: [], hasToken: false });
  },
}));
