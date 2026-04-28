import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { clearSessionToken, getSessionToken } from '../api/client';
import { initLeagueSession } from '../api/auth';
import type { LeagueSummary } from '../shared/types';

// Storage keys kept identical to the web app where practical, so the server
// sees consistent shape from both clients.
const SU_KEY = 'sleeper_user';
const SL_KEY = 'sleeper_league';

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
  setLeagues: (lgs: LeagueSummary[]) => void;
  /** Atomically swap the active league: re-runs initLeagueSession on the
   *  backend, then updates the persisted active league locally. Throws on
   *  failure; UI should wrap in try/catch. No-ops if `lg` matches the
   *  current league or another switch is in progress. */
  switchLeague: (lg: SavedLeague) => Promise<void>;
  signOut: () => Promise<void>;
}

export const useSession = create<SessionState>((set, get) => ({
  user: null,
  league: null,
  leagues: [],
  hasToken: false,
  switching: false,

  bootstrap: async () => {
    const [userRaw, leagueRaw, tok] = await Promise.all([
      AsyncStorage.getItem(SU_KEY),
      AsyncStorage.getItem(SL_KEY),
      getSessionToken(),
    ]);
    let user: SavedUser | null = null;
    let league: SavedLeague | null = null;
    try { if (userRaw)   user   = JSON.parse(userRaw); } catch {}
    try { if (leagueRaw) league = JSON.parse(leagueRaw); } catch {}
    set({ user, league, hasToken: !!tok });
  },

  setUser: async (u) => {
    if (u) await AsyncStorage.setItem(SU_KEY, JSON.stringify(u));
    else   await AsyncStorage.removeItem(SU_KEY);
    set({ user: u });
  },

  setLeague: async (lg) => {
    if (lg) await AsyncStorage.setItem(SL_KEY, JSON.stringify(lg));
    else    await AsyncStorage.removeItem(SL_KEY);
    set({ league: lg });
  },

  setLeagues: (lgs) => set({ leagues: lgs }),

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

  signOut: async () => {
    await Promise.all([
      AsyncStorage.removeItem(SU_KEY),
      AsyncStorage.removeItem(SL_KEY),
      clearSessionToken(),
    ]);
    set({ user: null, league: null, leagues: [], hasToken: false });
  },
}));
