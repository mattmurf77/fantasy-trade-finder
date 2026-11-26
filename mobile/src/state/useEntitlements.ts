import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getEntitlements, type LeaguePassEntry } from '../api/billing';
import {
  currentIdentityUserId,
  hasProEntitlement,
  onCustomerInfoChange,
  setOnPurchasesReady,
} from '../api/purchases';
import { customerInfoApplies } from './subscriptionSession';
import { useSession } from './useSession';

// useEntitlements — the client's cached view of Pro (pro-subscription LLD §4,
// scoped to what the IAP-enablement build needs: `{pro, expiresAt, refresh}`).
//
// ── The rule that governs this file ──────────────────────────────────────
// CLIENT RECEIPTS ARE NEVER TRUSTED; THE SERVER IS AUTHORITATIVE VIA
// check_pro(). Every gate that matters is enforced in `backend/entitlements`
// against rows the RevenueCat webhook wrote. What lives here is a UI cache so
// the app can paint a Pro surface without a round trip — and so a user who
// just paid does not stare at a locked screen while the webhook lands.
//
// Three inputs, in descending authority:
//   1. GET /api/me/entitlements — the truth. Overwrites everything, in both
//      directions (a server `false` locks the UI back down).
//   2. AsyncStorage cache — the last server answer, with a 72 h offline grace
//      (LLD §6 "Offline grace"). Past 72 h it is discarded and the UI reads
//      free, rather than failing open forever.
//   3. RevenueCat CustomerInfo — OPTIMISTIC ONLY. It may set `pro` true while
//      the server catches up; it is never persisted, never sets `pro` false
//      (an SDK cache miss is not a revocation — the server does that), and it
//      is erased by the next successful fetch either way.
//
// Store shape mirrors `useFeatureFlags`: a zustand store whose actions are
// called imperatively from App.tsx's boot + foreground legs, so non-React
// code can reach it via `.getState()`.

const CACHE_KEY = 'ftf.entitlements.v1';

/** Offline grace (LLD §6). Past this, a cached grant is ignored: gates lock
 *  to free behavior rather than failing open indefinitely. */
const GRACE_MS = 72 * 60 * 60 * 1000;

interface CachedEntitlements {
  pro: boolean;
  expiresAt: string | null;
  /** ms epoch of the last SUCCESSFUL server fetch — the grace clock. */
  fetchedAt: number;
  /** The user the answer is for (2026-11-22). Blobs written before it have
   *  none; see loadCached. */
  userId?: string;
  /** League pass (D-281): the server's `league_passes` and `sources`, under
   *  the same grace clock. Absent in older blobs ⇒ none. */
  leaguePasses?: LeaguePassEntry[];
  sources?: string[];
}

interface EntitlementState {
  /** Is this user Pro, as far as the client can tell? UI only. */
  pro: boolean;
  /** Furthest expiry of the active grant; null = perpetual or not Pro. */
  expiresAt: string | null;
  /** True while the held answer is the CURRENT session user's (server, or
   *  that user's cached answer inside the grace window). Surfaces that must
   *  not guess — Settings › Subscription, the Send pre-check — treat false as
   *  unknown. A boot or a token-less refresh with nothing to load never sets
   *  it (2026-11-22: that is what made a fresh install's first sign-in read
   *  "See plans" without ever asking). */
  loaded: boolean;
  /** The user id the held answer belongs to; null = none held. */
  answerFor: string | null;
  /** True while `pro` comes from a device receipt the server has not
   *  confirmed. Never persisted; cleared by the next successful refresh. */
  optimistic: boolean;
  /** The server's enforce predicate (#393 D7). The gate UI renders only
   *  while this is true. Read from `enforcing` alone: an unverified session's
   *  blanked subscription fields never make it false. Not persisted. */
  enforcing: boolean;
  /** Founding GMs member (S1). False on a blanked (unverified) response or an
   *  older server. Display only; never a gate input. Not persisted. */
  founder: boolean;
  /** League pass (flag `monetize.league_pass`, D-281): the server's
   *  `league_passes`, every live pass covering this user; [] when absent
   *  (flag off server-side, unverified, an older server). Read through
   *  `state/useLeaguePass` (`useProForLeague`), which ANDs in the client flag
   *  and the `covered_until` clock; never read it as a grant on its own.
   *  Server-only: no CustomerInfo push ever writes it. */
  leaguePasses: LeaguePassEntry[];
  /** The server's `sources` (grant provenance). Display decisions only: the
   *  league pass's one-time notice (an individual subscriber) and the unbound
   *  pass row. Never a gate input. */
  sources: string[];

  /** Local AsyncStorage hydrate + the 72 h grace evaluation. No network. */
  loadCached: () => Promise<void>;
  /** Fetch the server's answer and persist it. No-ops without a session
   *  token (nothing to authenticate with); never throws. */
  refresh: () => Promise<void>;
  /** Optimistic unlock from a RevenueCat CustomerInfo. Only ever raises. */
  noteCustomerInfo: (proActive: boolean) => void;
}

export const useEntitlements = create<EntitlementState>((set, get) => ({
  pro: false,
  expiresAt: null,
  loaded: false,
  answerFor: null,
  optimistic: false,
  enforcing: false,
  founder: false,
  leaguePasses: [],
  sources: [],

  loadCached: async () => {
    try {
      const raw = await AsyncStorage.getItem(CACHE_KEY);
      // Only the restored session's own answer counts. A blob from before
      // `userId` existed was written by the account still signed in (every
      // sign-out and switch dropped the cache), so it is adopted for it. No
      // session user, or another user's blob: nothing is held.
      const uid = useSession.getState().user?.user_id ?? null;
      if (raw && uid) {
        const c = JSON.parse(raw) as Partial<CachedEntitlements> | null;
        if (c && (c.userId === undefined || c.userId === uid)) {
          const fetchedAt = typeof c.fetchedAt === 'number' ? c.fetchedAt : 0;
          const fresh = fetchedAt > 0 && Date.now() - fetchedAt <= GRACE_MS;
          set({
            // Grace expired ⇒ read as free. Deliberately not "keep the last
            // value": an indefinitely-honored cached grant is a free Pro
            // subscription for anyone who stays offline.
            pro: fresh ? !!c.pro : false,
            expiresAt: fresh ? (c.expiresAt ?? null) : null,
            leaguePasses: fresh && Array.isArray(c.leaguePasses) ? c.leaguePasses : [],
            sources: fresh && Array.isArray(c.sources) ? c.sources : [],
            optimistic: false,
            answerFor: uid,
            loaded: true,
          });
        }
      }
    } catch {
      /* non-fatal — hydrate is opportunistic, same posture as the flag store */
    }
  },

  refresh: async () => {
    // The route is session-authed; without a token the call can only 401 and
    // clear nothing useful, so skip it and keep whatever the cache said.
    if (!useSession.getState().hasToken) return;
    // An answer for the account that has since left is not this account's.
    const askedFor = useSession.getState().user?.user_id;
    try {
      const res = await getEntitlements();
      if (useSession.getState().user?.user_id !== askedFor) return;
      // `=== true`: the server blanks every subscription field for an
      // unverified session (R28.9), and a blank reads as NOT entitled.
      const pro = res?.pro === true;
      const expiresAt = res?.expires_at ?? null;
      const founder = res?.founder === true;
      // `enforcing` stays the server's state even on a blanked response; it
      // is never inferred from the subscription fields (#393 D7, D16).
      const enforcing = res?.enforcing === true;
      // League pass: the server's list, or none (absent = flag off). Like
      // `pro`, it is overwritten in both directions: an ended pass goes.
      const leaguePasses = Array.isArray(res?.league_passes) ? res.league_passes : [];
      const sources = Array.isArray(res?.sources) ? res.sources : [];
      // Server wins in BOTH directions, and clearing `optimistic` here is the
      // point: a refund or a failed webhook must be able to take Pro away.
      set({ pro, expiresAt, founder, enforcing, leaguePasses, sources, loaded: true, answerFor: askedFor ?? null, optimistic: false });
      const blob: CachedEntitlements = { pro, expiresAt, leaguePasses, sources, fetchedAt: Date.now(), ...(askedFor ? { userId: askedFor } : {}) };
      try {
        await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(blob));
      } catch {
        /* non-fatal — cache write is opportunistic */
      }
    } catch {
      // Offline or backend down: keep the cached answer (still inside its
      // grace window) rather than locking a paying user out mid-flight. A
      // failure is not an answer: `loaded` stays what it was for this user.
      set({ loaded: get().answerFor !== null && get().answerFor === (askedFor ?? null) });
    }
  },

  noteCustomerInfo: (proActive) => {
    // Raise only. A CustomerInfo without the entitlement can mean the SDK has
    // not synced yet, so it must not be able to revoke; only `refresh` does.
    // Not persisted — a client-derived `true` must never survive a relaunch
    // and impersonate a server answer inside the grace window.
    if (proActive && !get().pro) set({ pro: true, optimistic: true, loaded: true });
  },
}));

/** Account reset (state/accountReset.ts): the leaving account's answer is
 *  dropped from memory and disk, and `loaded` goes false so surfaces that must
 *  not guess (Settings › Subscription) render nothing until the next account's
 *  own answer lands — the session subscriber in `initEntitlements` asks for it
 *  as soon as that account holds a token. Never throws. */
export function resetEntitlements(): void {
  _askedFor = null;
  useEntitlements.setState({
    pro: false, expiresAt: null, founder: false, enforcing: false, optimistic: false, loaded: false, answerFor: null,
    leaguePasses: [], sources: [],
  });
  AsyncStorage.removeItem(CACHE_KEY).catch(() => {});
}

let _listenerBound = false;
let _verifyEdgeBound = false;
/** The user the last automatic ask was for — one request per sign-in edge,
 *  never a retry loop (a failed ask waits for the foreground refresh). */
let _askedFor: string | null = null;

/** Ask the server once when a signed-in user with a token is present and the
 *  store does not hold THAT user's answer (2026-11-22). Covers a fresh
 *  install's first sign-in, a sign-in after sign-out, an account switch and a
 *  demo — whatever order the user and the token land in. `boot` asks even
 *  when a cached answer is held: a restored session gets the server's truth
 *  once per launch, as before. */
function askIfUnanswered(s: { hasToken: boolean; user: { user_id: string } | null }, boot = false): void {
  const uid = s.user?.user_id;
  if (!s.hasToken || !uid || _askedFor === uid) return;
  if (!boot && useEntitlements.getState().answerFor === uid) return;
  _askedFor = uid;
  void useEntitlements.getState().refresh();
}

/** Boot hook (App.tsx): hydrate the cache, ask the server, and subscribe to
 *  RevenueCat's CustomerInfo pushes so a renewal or a purchase made outside
 *  the paywall unlocks the UI immediately. Fire-and-forget; never throws.
 *  The listener is a no-op subscription when purchases are unavailable. */
export function initEntitlements(): void {
  void useEntitlements
    .getState()
    .loadCached()
    .then(() => askIfUnanswered(useSession.getState(), true))
    .catch(() => {});
  // #393 M3: a session that turns verified re-reads. While it was unverified
  // the server blanked every subscription field (R28.9), so the cached answer
  // is that blank one, and Settings › Subscription would show a member the
  // non-subscriber rows. Only the unverified → verified edge: boot's first
  // mirror (null → verified) is the fetch above.
  if (!_verifyEdgeBound) {
    _verifyEdgeBound = true;
    useSession.subscribe((s, prev) => {
      if (prev.verification?.session_verified === false && s.verification?.session_verified === true) {
        void useEntitlements.getState().refresh();
      }
    });
  }
  // A different user (sign-out, a switch) never keeps the last user's answer
  // (release-lead QA P3): the not-entitled defaults, the device cache dropped,
  // the server asked again. Boot's null → user hydrate isn't a change, so the
  // offline grace cache still applies there.
  useSession.subscribe((s, prev) => {
    const was = prev.user?.user_id;
    if (!was || s.user?.user_id === was) return;
    _askedFor = null;
    useEntitlements.setState({ pro: false, expiresAt: null, founder: false, enforcing: false, optimistic: false, loaded: false, answerFor: null, leaguePasses: [], sources: [] });
    AsyncStorage.removeItem(CACHE_KEY).catch(() => {});
  });
  // The server is asked whenever a signed-in user with a token is present and
  // its answer is not held — on every session update, so the order in which
  // the user and the token land (separate updates or one) does not matter.
  // Before 2026-11-22 a fresh install never asked: boot's cache hydrate marked
  // the empty store "loaded", the A → B branch above needs a previous user,
  // and the only other ask was the foreground refresh.
  useSession.subscribe((s) => askIfUnanswered(s));
  // Attach the CustomerInfo listener the moment purchases become usable —
  // which is when the session working key first reaches `initPurchases`, at
  // boot for a restored session and at sign-in otherwise. Attaching before
  // `configure` would silently bind nothing (purchases.onCustomerInfoChange
  // returns a no-op unsubscribe when the SDK is not configured), which is the
  // whole reason this goes through the ready callback rather than running
  // inline here.
  setOnPurchasesReady(() => {
    if (_listenerBound) return;
    _listenerBound = true;
    onCustomerInfoChange((info) => {
      // Believe the push only while this session is verified AND RevenueCat's
      // identity is this session's user (subscriptionSession): a device last
      // logged in as A never shows A's state to a session for B.
      if (customerInfoApplies(useSession.getState(), currentIdentityUserId())) {
        useEntitlements.getState().noteCustomerInfo(hasProEntitlement(info));
      }
      // Ask the server too — the push is the hint, the fetch is the answer.
      void useEntitlements.getState().refresh();
    });
  });
}
