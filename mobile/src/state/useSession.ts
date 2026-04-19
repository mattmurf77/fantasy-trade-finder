import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { clearSessionToken, getSessionToken } from '../api/client';
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

  bootstrap: () => Promise<void>;
  setUser: (u: SavedUser | null) => Promise<void>;
  setLeague: (lg: SavedLeague | null) => Promise<void>;
  setLeagues: (lgs: LeagueSummary[]) => void;
  signOut: () => Promise<void>;
}

export const useSession = create<SessionState>((set) => ({
  user: null,
  league: null,
  leagues: [],
  hasToken: false,

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

  signOut: async () => {
    await Promise.all([
      AsyncStorage.removeItem(SU_KEY),
      AsyncStorage.removeItem(SL_KEY),
      clearSessionToken(),
    ]);
    set({ user: null, league: null, leagues: [], hasToken: false });
  },
}));
