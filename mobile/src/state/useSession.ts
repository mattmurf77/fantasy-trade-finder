import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  api,
  clearSessionToken,
  getSessionToken,
  setOnSessionExpired,
  setOnVerificationRequired,
} from '../api/client';
import { initLeagueSession, startDemoSession as apiStartDemoSession } from '../api/auth';
import { maybePregenTrades } from '../api/tradePregen';
import { connectLeague as apiConnectLeague } from '../api/league';
import { getLeagues } from '../api/sleeper';
import { initPurchases } from '../api/purchases';
import { setUser as sentrySetUser } from '../observability/sentry';
import { queryClient, seedLeagueSessionCaches } from './queryClient';
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
// P0-3 — invite intent: the league + inviter captured from an invite link,
// awaiting a pin. Persisted (web's localStorage ftf_invited_by /
// ftf_invited_league are the parity precedent, web/js/app.js) because the
// invitee's real path is often tap → app opens → close → return later, and
// because an account-only invitee (P0-5) can be league-less for several
// launches before they link a platform.
const INVITE_KEY = 'ftf_invite_intent';
const INVITE_TTL_MS = 14 * 24 * 60 * 60 * 1000;   // 14 days (HLD S-15)

/** Persisted shape behind INVITE_KEY. Unknown fields are ignored on read;
 *  every field but `ts` may be null. */
interface InviteIntent {
  leagueId: string | null;
  invitedBy: string | null;
  /** Display name resolved once by SignInScreen's banner via
   *  GET /api/league/invite-meta. Cached here so the LeaguePicker companion
   *  state can name the league without a second call site (lld-p0-3 §2.0).
   *  Null when unresolved — every consumer degrades to "their league". */
  leagueName: string | null;
  /** Capture time, ms epoch. TTL is evaluated on READ, never by a timer. */
  ts: number;
}

export type RankMethodPref = 'quickset' | 'trio' | 'anchor' | 'tiers' | 'manual';
const RANK_METHOD_PREFS: readonly RankMethodPref[] = ['quickset', 'trio', 'anchor', 'tiers', 'manual'];

// FB-45 — revalidation bookkeeping (module-level: internal, not UI state).
// The throttle keeps quick app-switches from re-running the full league
// handshake; the in-flight flag prevents overlapping handshakes.
let _revalidating = false;
let _lastRevalidateMs = 0;
const REVALIDATE_MIN_INTERVAL_MS = 60_000;

// P0-3 — capture time of the live invite intent (ms epoch, 0 = none).
// Module-level rather than store state: nothing renders from it, it is only
// read to compute `ms_since_open` on the pin event and to evaluate the TTL.
let _inviteTs = 0;

/** Whole-blob write. Deliberately NOT a read-modify-write: every caller
 *  already holds the full intent in store state, so a full write is
 *  last-write-wins with no interleaving hazard. Never throws — a
 *  persistence failure costs the invite across a relaunch, not this one. */
async function _persistInviteIntent(blob: InviteIntent): Promise<void> {
  try {
    await AsyncStorage.setItem(INVITE_KEY, JSON.stringify(blob));
  } catch {
    /* non-fatal */
  }
}

/** Age of the live invite intent in ms, or null when there is none.
 *  Feeds `invite_league_pinned.ms_since_open`. Bounded by the 14-day TTL. */
export function inviteIntentAgeMs(): number | null {
  if (!_inviteTs) return null;
  return Math.max(0, Date.now() - _inviteTs);
}

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
  /** "This device holds a session token." The canonical `enabled:` gate for
   *  authed queries — true from the moment a session is established
   *  (bootstrap restore / setLeague / revalidateSession / startDemoSession)
   *  and false the moment one is destroyed (sign-out, or a 401 that cleared
   *  the stored token — see setOnSessionExpired at the bottom of this file).
   *  Gate on THIS, not on `league?.league_id`: account-only sessions ride the
   *  `no_league` sentinel and must still be able to rank. */
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
  /** P0-3 — league id captured from an invite link (`?league=` or the
   *  /app/league/join path). PERSISTED with a 14-day TTL — unlike
   *  `invitedBy`, which is in-memory. Consumed when the league is pinned. */
  invitedLeagueId: string | null;
  /** P0-3 — resolved league name for the invite copy, or null. Resolved
   *  once by SignInScreen's banner and cached into the persisted blob. */
  invitedLeagueName: string | null;
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
  /** P0-3 — record the invited league. Trims; no-ops on blank. Stamps a
   *  fresh capture time and clears any cached league NAME when the id
   *  changed (a stale name on a new league is worse than no name). */
  setInvitedLeague: (leagueId: string) => Promise<void>;
  /** P0-3 — cache the resolved league name. No-ops without a live intent
   *  or on a blank name. Does NOT re-stamp the capture time: resolving a
   *  name is not a fresh invite. */
  setInvitedLeagueName: (name: string) => Promise<void>;
  /** P0-3 — read the invited league id and clear the intent (state +
   *  storage). Consume-on-PIN, never on read: only the caller that has
   *  actually pinned the league calls this. */
  consumeInvitedLeague: () => Promise<string | null>;
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
  invitedLeagueId: null,
  invitedLeagueName: null,
  rankingMethodPref: null,
  verification: null,
  verifyBannerDismissed: false,

  bootstrap: async () => {
    const [userRaw, leagueRaw, leaguesRaw, tok, fmt, prefRaw, inviteRaw] = await Promise.all([
      AsyncStorage.getItem(SU_KEY),
      AsyncStorage.getItem(SL_KEY),
      AsyncStorage.getItem(SLG_KEY),
      getSessionToken(),
      getActiveScoringFormat(),
      AsyncStorage.getItem(RM_KEY),
      AsyncStorage.getItem(INVITE_KEY),
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

    // P0-3 — hydrate the invite intent, evaluating the TTL ON READ (never by
    // a timer). An expired blob is treated as absent AND removed, so it is
    // not re-parsed on every launch for the rest of the install's life.
    let invitedLeagueId: string | null = null;
    let invitedLeagueName: string | null = null;
    let invitedByStored: string | null = null;
    _inviteTs = 0;
    try {
      if (inviteRaw) {
        const blob = JSON.parse(inviteRaw) as Partial<InviteIntent> | null;
        const ts = typeof blob?.ts === 'number' ? blob.ts : 0;
        if (!ts || Date.now() - ts > INVITE_TTL_MS) {
          void AsyncStorage.removeItem(INVITE_KEY).catch(() => {});
        } else {
          _inviteTs = ts;
          invitedLeagueId   = typeof blob?.leagueId   === 'string' ? blob.leagueId   : null;
          invitedLeagueName = typeof blob?.leagueName === 'string' ? blob.leagueName : null;
          invitedByStored   = typeof blob?.invitedBy  === 'string' ? blob.invitedBy  : null;
        }
      }
    } catch {
      /* malformed blob — treat as absent, same as its neighbours above */
    }

    set({
      user,
      league,
      leagues,
      hasToken: !!tok,
      activeFormat: fmt,
      rankingMethodPref,
      invitedLeagueId,
      invitedLeagueName,
      // Only hydrate the inviter when this launch has not already captured
      // one from a live link — a link tapped THIS launch is fresher.
      ...(get().invitedBy ? {} : invitedByStored ? { invitedBy: invitedByStored } : {}),
    });

    // Purchases identity bridge (iap-enablement). A RESTORED session is the
    // other half of the sign-in path below: RevenueCat must be configured with
    // the same working key the backend resolves entitlements against, or a
    // webhook lands on an app-user-id nothing here knows. Fire-and-forget and
    // fully no-op without an SDK key — see api/purchases.ts.
    if (user?.user_id) void initPurchases(user.user_id);
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
      const seed = await initLeagueSession(user, {
        league_id: league.league_id,
        name:      league.league_name,
      });
      // The handshake just fetched this league's rosters + users. Hand them
      // to the cache so Trades / the calculator / the DNA sheet / the hub
      // don't re-request the same two endpoints on their next mount.
      seedLeagueSessionCaches(league.league_id, seed);
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
    // Purchases identity bridge (iap-enablement): configure on the first
    // working key of the launch, `Purchases.logIn(userId)` on any later one.
    // This is the sign-in half; bootstrap() covers the restored-session half.
    //
    // The null branch is deliberately EMPTY. Signing out of FTF is not signing
    // out of the App Store account that owns the subscription, and
    // `Purchases.logOut()` would swap RevenueCat onto a fresh anonymous
    // app-user-id whose purchases then have to be aliased back — so we never
    // call it (RevenueCat's own guidance). The next sign-in calls logIn with a
    // real working key, which is the correct identity move.
    if (u?.user_id) void initPurchases(u.user_id);
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
      const seed = await initLeagueSession(userSnapshot, {
        league_id: lg.league_id,
        name:      lg.league_name,
      });
      // Seed the NEW league's roster/user caches from the handshake's own
      // fetches — see seedLeagueSessionCaches.
      seedLeagueSessionCaches(lg.league_id, seed);
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
    // P0-3 — mirror into the persisted invite blob so a `?ref=`-only capture
    // survives a relaunch the same way the league does. Fire-and-forget; the
    // in-memory semantics above (and consumeInvitedBy) are unchanged, so
    // api/auth keeps consuming it exactly as before.
    const st = get();
    if (!_inviteTs) _inviteTs = Date.now();
    void _persistInviteIntent({
      leagueId:   st.invitedLeagueId,
      invitedBy:  u,
      leagueName: st.invitedLeagueName,
      ts:         _inviteTs,
    });
  },

  consumeInvitedBy: () => {
    const cur = get().invitedBy;
    if (cur) set({ invitedBy: null });
    return cur;
  },

  setInvitedLeague: async (leagueId) => {
    const id = (leagueId || '').trim();
    if (!id) return;
    const st = get();
    const changed = st.invitedLeagueId !== id;
    // A NEW league invalidates any cached name — a stale name on a new
    // league is worse than no name at all.
    const leagueName = changed ? null : st.invitedLeagueName;
    _inviteTs = Date.now();
    set({ invitedLeagueId: id, invitedLeagueName: leagueName });
    await _persistInviteIntent({
      leagueId:   id,
      invitedBy:  st.invitedBy,
      leagueName,
      ts:         _inviteTs,
    });
  },

  setInvitedLeagueName: async (name) => {
    const n = (name || '').trim();
    const st = get();
    if (!st.invitedLeagueId || !n) return;
    set({ invitedLeagueName: n });
    await _persistInviteIntent({
      leagueId:   st.invitedLeagueId,
      invitedBy:  st.invitedBy,
      leagueName: n,
      // NOT re-stamped: resolving a name is not a fresh invite, and letting
      // it re-stamp would silently extend the 14-day TTL.
      ts:         _inviteTs || Date.now(),
    });
  },

  consumeInvitedLeague: async () => {
    const cur = get().invitedLeagueId;
    _inviteTs = 0;
    set({ invitedLeagueId: null, invitedLeagueName: null });
    try {
      await AsyncStorage.removeItem(INVITE_KEY);
    } catch {
      /* non-fatal — the TTL sweeps it eventually */
    }
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
      // P-1 (draft-extensions W3 M-A) — MERGE, don't replace. `getLeagues`
      // hits /api/sleeper/leagues/<user_id>, whose local-league append
      // filters to NON-NUMERIC ids, and a platform-imported league carries
      // its numeric platform-native id. So that response can never contain
      // an ESPN/MFL/Fleaflicker row, and the wholesale replace this used to
      // do silently dropped every one of them: connecting any Sleeper
      // league mid-session wiped the linked-platform leagues from the
      // cache. That is already why the ESPN re-sync button disappears, and
      // the League tab's ESPN-gated sections (draft picks, the ESPN badge
      // and re-sync row) would have inherited it. Carry the non-Sleeper
      // rows forward; a fresh row for the same league_id still wins.
      const prior = get().leagues ?? [];
      const fresh = new Set(lgs.map((lg) => lg.league_id));
      const carried = prior.filter(
        (lg) => (lg.platform ?? 'sleeper') !== 'sleeper' && !fresh.has(lg.league_id),
      );
      const merged: LeagueSummary[] = [...lgs, ...carried];
      // Ensure the just-connected league is in the list. Sleeper returns
      // every NFL league the user is in, so this is usually a no-op, but
      // it guards against propagation delay.
      if (!merged.some((lg) => lg.league_id === result.league_id)) {
        merged.push({
          league_id: result.league_id,
          name: result.league_name,
        });
      }
      await get().setLeagues(merged);
    } catch {
      // Non-fatal — caller still gets ok=true; switcher may need a manual
      // refresh from LeaguePickerScreen.
    }

    // 3. Initialize a session against the new league and persist as
    //    active. Same handshake LeaguePickerScreen runs.
    const seed = await initLeagueSession(state.user, {
      league_id: result.league_id,
      name:      result.league_name,
    });
    seedLeagueSessionCaches(result.league_id, seed);
    await get().setLeague({
      league_id:   result.league_id,
      league_name: result.league_name,
    });
    return result;
  },

  signOut: async () => {
    api.post('/api/session/signout').catch(() => {});   // best-effort server-side revoke (W2C handoff; route evicts the token + its durable row)
    await Promise.all([
      AsyncStorage.removeItem(SU_KEY),
      AsyncStorage.removeItem(SL_KEY),
      AsyncStorage.removeItem(SLG_KEY),
      // P0-3 — an invite intent belongs to the session that captured it.
      AsyncStorage.removeItem(INVITE_KEY),
      clearSessionToken(),
    ]);
    _inviteTs = 0;
    set({
      user:              null,
      league:            null,
      leagues:           [],
      hasToken:          false,
      formatExplicit:    false,
      isDemo:            false,
      invitedBy:         null,
      invitedLeagueId:   null,
      invitedLeagueName: null,
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

// ── Session-expired signal (teardown 06-03, flag auth.persistent_sessions) ──
// A 401 just cleared the stored token. Sleeper-keyed sessions silently
// re-mint via revalidateSession, and demo sessions just end — but an
// ACCOUNT-ONLY session (no sleeper_username) has no silent path: identity
// tokens are one-shot, so recovery needs a fresh Apple tap. Interim
// mitigation per the P3 PRD: route to SignIn pre-set for Apple re-auth
// instead of leaving the user stranded on failing screens. Flag-gated so
// flag-off behavior stays the legacy generic clear.

// One-shot hint for SignInScreen: "you're here for an Apple re-auth".
// Module-level (not store state) — it's routing context, not UI state.
let _appleReauthPending = false;
/** Read-and-clear the pending Apple re-auth hint (SignInScreen mount). */
export function consumeAppleReauthHint(): boolean {
  const v = _appleReauthPending;
  _appleReauthPending = false;
  return v;
}

setOnSessionExpired(() => {
  // First, unconditionally: the stored token is GONE (client.ts just
  // cleared it), so `hasToken` — the store's mirror of "this device holds
  // a session" — must stop claiming otherwise. It only ever fell to false
  // on sign-out, so a session that died mid-flight left every consumer
  // gated on it (RootNav's progress tail, the league format-stats applier,
  // the Rank surfaces, the feedback FAB) firing token-less requests that
  // could only 401 — the pre-auth 401 cluster in the 2026-08 production
  // analytics pull. Suppressing them is the whole point of the gate.
  //
  // Self-healing, not a stall: every path that establishes a session sets
  // it back to true (revalidateSession on boot/foreground resume,
  // setLeague after a sign-in or league switch, startDemoSession), which
  // flips the gated queries back to enabled and refetches. Queries that
  // already hold data keep showing it while disabled, so the screen falls
  // back to stale values rather than an error state.
  useSession.setState({ hasToken: false });

  const s = useSession.getState();
  if (s.isDemo || !s.user?.account_only) return;
  try {
    // Lazy require — the flag store imports api modules that import us.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { useFeatureFlags } = require('./useFeatureFlags') as typeof import('./useFeatureFlags');
    if (!useFeatureFlags.getState().flags['auth.persistent_sessions']) return;
  } catch {
    return; // can't read the flag → keep legacy behavior
  }
  _appleReauthPending = true;
  try {
    // Lazy require breaks the RootNav → useSession import cycle; resolved
    // only at 401 time, long after both modules initialized.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { navigationRef } = require('../navigation/RootNav') as typeof import('../navigation/RootNav');
    if (navigationRef.isReady() && navigationRef.getCurrentRoute?.()?.name !== 'SignIn') {
      navigationRef.navigate('SignIn' as never);
    }
  } catch {
    /* navigation not mounted yet — RootNav's gating handles the next boot */
  }
});
