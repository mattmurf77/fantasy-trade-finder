import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { clearSessionToken, getSessionToken } from '../api/client';
import { initLeagueSession, startDemoSession as apiStartDemoSession } from '../api/auth';
import { setUser as sentrySetUser } from '../observability/sentry';
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
  /** Set when /api/session/demo bootstrapped the active session. Reset on
   *  sign-out or a real signIn. Used by UI to gate demo banners / disable
   *  destructive actions (sharing, push registration) until a real account
   *  syncs. In-memory only — the demo session itself isn't meant to survive
   *  an app reinstall. */
  isDemo: boolean;
  /** Username captured from a `?ref=` query param on a deep link. Used to
   *  attribute new accounts to the inviter via session_init.invited_by.
   *  In-memory only — once consumed by a real session init it's cleared. */
  invitedBy: string | null;

  bootstrap: () => Promise<void>;
  setUser: (u: SavedUser | null) => Promise<void>;
  setLeague: (lg: SavedLeague | null) => Promise<void>;
  setLeagues: (lgs: LeagueSummary[]) => void;
  /** Atomically swap the active league: re-runs initLeagueSession on the
   *  backend, then updates the persisted active league locally. Throws on
   *  failure; UI should wrap in try/catch. No-ops if `lg` matches the
   *  current league or another switch is in progress. */
  switchLeague: (lg: SavedLeague) => Promise<void>;
  /** Record a referral attribution to forward on the next session_init.
   *  Stored in-memory only; the next sessionInit call picks it up via
   *  consumeInvitedBy(). Safe to call multiple times — last value wins. */
  setInvitedBy: (username: string) => void;
  /** Read the pending invited_by value and clear it. Intended to be called
   *  by initLeagueSession (or any other path that POSTs /api/session/init).
   *  Returns null when no referral was captured. */
  consumeInvitedBy: () => string | null;
  /** Boot a demo session from /api/session/demo. Sets a synthetic user +
   *  league so RootNav routes into Main tabs, marks the session as demo,
   *  and persists nothing to disk beyond the secure-store session token
   *  (handled inside api/auth). Throws on failure. */
  startDemoSession: () => Promise<void>;
  signOut: () => Promise<void>;
}

export const useSession = create<SessionState>((set, get) => ({
  user: null,
  league: null,
  leagues: [],
  hasToken: false,
  switching: false,
  isDemo: false,
  invitedBy: null,

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

  setInvitedBy: (username) => {
    const u = (username || '').trim().toLowerCase();
    if (!u) return;
    set({ invitedBy: u });
  },

  consumeInvitedBy: () => {
    const cur = get().invitedBy;
    if (cur) set({ invitedBy: null });
    return cur;
  },

  startDemoSession: async () => {
    // Backend mints the session, the league, and the seeded ranking +
    // trade services in one shot. We mirror what the web does: stash a
    // synthetic SavedUser / SavedLeague so RootNav's gating evaluates
    // user + league + token → 'Main' and the tabs render normally.
    const res = await apiStartDemoSession();
    const demoUser: SavedUser = {
      user_id:      res.user_id,
      username:     'demo',
      display_name: res.display_name || 'Demo User',
      avatar_id:    null,
    };
    const demoLeague: SavedLeague = {
      league_id:    res.league_id,
      league_name:  res.league_name || 'The Demo League',
    };
    await Promise.all([
      AsyncStorage.setItem(SU_KEY, JSON.stringify(demoUser)),
      AsyncStorage.setItem(SL_KEY, JSON.stringify(demoLeague)),
    ]);
    set({
      user:     demoUser,
      league:   demoLeague,
      hasToken: true,
      isDemo:   true,
    });
    sentrySetUser({ id: demoUser.user_id, username: demoUser.username });
  },

  signOut: async () => {
    await Promise.all([
      AsyncStorage.removeItem(SU_KEY),
      AsyncStorage.removeItem(SL_KEY),
      clearSessionToken(),
    ]);
    set({
      user:      null,
      league:    null,
      leagues:   [],
      hasToken:  false,
      isDemo:    false,
      invitedBy: null,
    });
  },
}));
