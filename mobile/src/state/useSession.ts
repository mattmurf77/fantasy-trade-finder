import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  clearSessionToken,
  getSessionToken,
  setOnVerificationRequired,
} from '../api/client';
import { initLeagueSession, startDemoSession as apiStartDemoSession } from '../api/auth';
import { maybePregenTrades } from '../api/tradePregen';
import { connectLeague as apiConnectLeague } from '../api/league';
import { getLeagues } from '../api/sleeper';
import { setUser as sentrySetUser } from '../observability/sentry';
import { queryClient } from './queryClient';
import { getActiveScoringFormat } from '../api/rankings';
import type { LeagueSummary, ScoringFormat } from '../shared/types';

// Storage keys kept identical to the web app where practical, so the server
// sees consistent shape from both clients.
const SU_KEY = 'sleeper_user';
const SL_KEY = 'sleeper_league';
// B3 — cache the multi-league list so a returning user sees the switcher
// populated without waiting for a Sleeper round-trip.
const SLG_KEY = 'sleeper_leagues';
// Rank-home preference: which ranking flow the Rank tab opens at launch.
// Device-local; also POSTed to /api/ranking-method for analytics.
const RM_KEY = 'ftf_rank_method_pref';

export type RankMethodPref = 'quickset' | 'trio' | 'anchor' | 'tiers' | 'manual';
const RANK_METHOD_PREFS: readonly RankMethodPref[] = ['quickset', 'trio', 'anchor', 'tiers', 'manual'];

// FB-45 — revalidation bookkeeping (module-level: internal, not UI state).
// The throttle keeps quick app-switches from re-running the full league
// handshake; the in-flight flag prevents overlapping handshakes.
let _revalidating = false;
let _lastRevalidateMs = 0;
const REVALIDATE_MIN_INTERVAL_MS = 60_000;

export interface SavedUser {
  user_id: string;
  username: string;
  display_name: string;
  avatar_id: string | null;
  /** Account-first identity (P2.6): true when this user is an Apple/Google
   *  account with NO linked Sleeper source — user_id is the synthetic
   *  working key `acct_<account_id>`, the league is the "No league linked"
   *  sentinel, and Sleeper-side flows (league picker handshake, revalidate,
   *  connect-league, SleeperConnect verification) must not run. Cleared when
   *  a Sleeper username is linked in Settings. */
  account_only?: boolean;
}

/** Sentinel league pinned for account-only sessions — mirrors the backend's
 *  ACCOUNT_NO_LEAGUE_ID empty league so RootNav routes into Main. */
export const NO_LEAGUE_ID = 'no_league';

/** Verified-session state from the backend (account-auth P1). Shape mirrors
 *  session_init's additive `verification` response field. */
export interface SessionVerification {
  /** THIS session proved control of the account (Sleeper-JWT capture +
   *  live-token proof via SleeperConnectScreen). */
  session_verified: boolean;
  /** SOME session has verified this user_id. If true while
   *  session_verified is false, this session has already lost write access
   *  (first-verified-controller-wins). */
  user_verified: boolean;
  verified_via?: string | null;
  /** Grace period is over — unverified writes are hard-denied server-side. */
  enforced: boolean;
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
  /** Active scoring format — hydrated from AsyncStorage via rankings.ts.
   *  Null until bootstrap() completes (or the user hasn't set a format). */
  activeFormat: ScoringFormat | null;
  /** True when the CURRENT activeFormat was chosen explicitly by the user
   *  via the SF/1QB toggle (feedback #80). While true, the league-driven
   *  default applier (hooks/useScoringFormat.useLeagueFormatDefault) must
   *  not stomp the choice. In-memory only; reset on every league change
   *  so a new league's detected format becomes the default again. */
  formatExplicit: boolean;
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
  /** Preferred ranking flow — where the Rank tab opens at launch. Null =
   *  never chosen → the Rank tab shows the Build-your-board chooser
   *  (RankHomeScreen). Hydrated from AsyncStorage in bootstrap(); changed
   *  from the chooser or the Settings steer slider. */
  rankingMethodPref: RankMethodPref | null;
  /** Verified-session state (account-auth P1). Null until the first
   *  session_init response of this launch arrives. In-memory only — the
   *  server is authoritative and re-reports it on every session_init. */
  verification: SessionVerification | null;
  /** "Verify your account" banner dismissal — session-scoped (in-memory)
   *  so the quiet reminder returns on the next launch, never nags twice
   *  in one. */
  verifyBannerDismissed: boolean;

  bootstrap: () => Promise<void>;
  /** Persist the preferred ranking flow (see rankingMethodPref). */
  setRankingMethodPref: (m: RankMethodPref) => Promise<void>;
  /** Record the server-reported verification state. Called by api/auth's
   *  sessionInit (every response carries it) and by SleeperConnectScreen
   *  when a link capture upgrades the session to verified. */
  setVerification: (v: SessionVerification | null) => void;
  /** Hide the "Verify your account" banner for the rest of this launch. */
  dismissVerifyBanner: () => void;
  /** FB-45 — server sessions are in-memory; a deploy/restart orphans the
   *  stored token while the app still routes to Main. Re-run the league
   *  handshake to mint a fresh server session on cold launch and on
   *  foreground resume. No-ops without a persisted user+league (or in
   *  demo mode); throttled; never throws — offline keeps the cached
   *  token, which may still be valid. */
  revalidateSession: () => Promise<void>;
  setUser: (u: SavedUser | null) => Promise<void>;
  setLeague: (lg: SavedLeague | null) => Promise<void>;
  setLeagues: (lgs: LeagueSummary[]) => Promise<void>;
  /** Atomically swap the active league: re-runs initLeagueSession on the
   *  backend, then updates the persisted active league locally. Throws on
   *  failure; UI should wrap in try/catch. No-ops if `lg` matches the
   *  current league or another switch is in progress. */
  switchLeague: (lg: SavedLeague) => Promise<void>;
  /** Update the in-store active format after calling setActiveScoringFormat.
   *  Called by hooks/useScoringFormat so query keys that include
   *  activeFormat invalidate correctly. Pass `explicit: true` when the
   *  change came from the user's SF/1QB toggle (protects it from the
   *  league-default applier); league-driven applications omit it. */
  setActiveFormat: (fmt: ScoringFormat | null, opts?: { explicit?: boolean }) => void;
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
  activeFormat: null,
  formatExplicit: false,
  switching: false,
  isDemo: false,
  invitedBy: null,
  rankingMethodPref: null,
  verification: null,
  verifyBannerDismissed: false,

  bootstrap: async () => {
    const [userRaw, leagueRaw, leaguesRaw, tok, fmt, prefRaw] = await Promise.all([
      AsyncStorage.getItem(SU_KEY),
      AsyncStorage.getItem(SL_KEY),
      AsyncStorage.getItem(SLG_KEY),
      getSessionToken(),
      getActiveScoringFormat(),
      AsyncStorage.getItem(RM_KEY),
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
    const rankingMethodPref = RANK_METHOD_PREFS.includes(prefRaw as RankMethodPref)
      ? (prefRaw as RankMethodPref)
      : null;
    set({ user, league, leagues, hasToken: !!tok, activeFormat: fmt, rankingMethodPref });
  },

  setRankingMethodPref: async (m) => {
    set({ rankingMethodPref: m });
    try {
      await AsyncStorage.setItem(RM_KEY, m);
    } catch {
      /* non-fatal — worst case the chooser shows again next launch */
    }
  },

  setVerification: (v) => {
    set({ verification: v });
  },

  dismissVerifyBanner: () => {
    set({ verifyBannerDismissed: true });
  },

  revalidateSession: async () => {
    const { user, league, isDemo } = get();
    if (!user || !league || isDemo) return;
    // Account-only sessions (P2.6) have no Sleeper league to re-handshake
    // with — identity tokens are one-shot, so a lost server session needs a
    // fresh Apple tap at SignIn (documented limitation until P3 persists
    // sessions server-side).
    if (user.account_only || league.league_id === NO_LEAGUE_ID) return;
    const now = Date.now();
    if (_revalidating || now - _lastRevalidateMs < REVALIDATE_MIN_INTERVAL_MS) return;
    _revalidating = true;
    try {
      // initLeagueSession mints a fresh server session + token and stores
      // it in secure-store, replacing whatever (possibly orphaned) token
      // the app restored at boot.
      await initLeagueSession(user, {
        league_id: league.league_id,
        name:      league.league_name,
      });
      _lastRevalidateMs = Date.now();
      set({ hasToken: true });
      // Onboarding item 4 (hazard H3): the silent re-init is the returning-
      // user auto path — pregen the trade deck now so Trades opens warm.
      // Flag-gated + per-launch-deduped inside; fire-and-forget.
      maybePregenTrades(league.league_id);
    } catch {
      // Offline or backend down — keep current state. The cached token may
      // still be valid; never sign the user out from a failed revalidate.
    } finally {
      _revalidating = false;
    }
  },

  setActiveFormat: (fmt, opts) => {
    set({ activeFormat: fmt, formatExplicit: !!opts?.explicit });
  },

  setUser: async (u) => {
    if (u) await AsyncStorage.setItem(SU_KEY, JSON.stringify(u));
    else   await AsyncStorage.removeItem(SU_KEY);
    set({ user: u });
    // Tag Sentry events with the pseudonymous Sleeper user_id ONLY — no
    // username (privacy decision 2026-07-17, analytics-platform PRD OQ-1:
    // crash triage joins on id via our own DB; the handle never leaves us).
    // No-op when Sentry isn't initialized. Cleared on sign-out.
    sentrySetUser(u ? { id: u.user_id } : null);
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
    //
    // formatExplicit resets on every league change: the SF/1QB toggle is a
    // per-league in-session override, so the NEW league's detected format
    // becomes the default again (feedback #80).
    set({ league: lg, hasToken: !!lg, formatExplicit: false });
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
      // Invalidate league-agnostic caches whose CONTENTS change on a
      // league swap. `[leagueId]`-keyed queries auto-refetch on key
      // change, but stable keys don't — so portfolio, the cross-league
      // matches inbox, and awaiting-trades all keep the previous
      // league's data for up to staleTime (30s/15s respectively).
      // Mirrors api-layer review #A4.
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['matches', 'all'] });
      queryClient.invalidateQueries({ queryKey: ['awaiting-trades'] });
      // League switch means rankings/progress/streak are all stale —
      // invalidate all format/position variants by prefix.
      queryClient.invalidateQueries({ queryKey: ['rankings'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
      queryClient.invalidateQueries({ queryKey: ['streak'] });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
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
    sentrySetUser({ id: demoUser.user_id });   // pseudonymous id only (PRD OQ-1)
  },

  connectLeague: async (sleeperUrl) => {
    const state = get();
    // Account-only users (P2.6) have no Sleeper user_id to fetch leagues
    // for — they link a Sleeper username in Settings → Account first.
    if (!state.user || state.user.account_only) {
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
    set({
      user:           null,
      league:         null,
      leagues:        [],
      hasToken:       false,
      formatExplicit: false,
      isDemo:         false,
      invitedBy:      null,
      verification:   null,
      verifyBannerDismissed: false,
    });
  },
}));

// ── Read-gate signal (account-auth P2.5) ────────────────────────────────
// Any API call answered with 403 verification_required means this session
// is unverified while a verified controller exists for its user_id (the
// squatter / second-device case — the same condition session_init reports
// as user_verified=true). Mirror that into `verification` so the existing
// VerifyAccountBanner (mounted at the authed root) appears and routes the
// user into SleeperConnect. Central here — screens don't each map the 403;
// their query error states just show the shared "verify to view" copy
// (utils/verification.readErrorCopy).
setOnVerificationRequired(() => {
  const cur = useSession.getState().verification;
  // Already reflecting a banner-visible state? Don't churn the store on
  // every gated response.
  if (cur && !cur.session_verified && (cur.user_verified || cur.enforced)) {
    return;
  }
  useSession.setState({
    verification: {
      session_verified: false,
      user_verified:    true,
      verified_via:     cur?.verified_via ?? null,
      enforced:         cur?.enforced ?? false,
    },
  });
});
