import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getEntitlements } from '../api/billing';
import {
  hasProEntitlement,
  onCustomerInfoChange,
  setOnPurchasesReady,
} from '../api/purchases';
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
}

interface EntitlementState {
  /** Is this user Pro, as far as the client can tell? UI only. */
  pro: boolean;
  /** Furthest expiry of the active grant; null = perpetual or not Pro. */
  expiresAt: string | null;
  /** True once some source (cache or server) has answered. Surfaces that must
   *  not guess — the Settings hub's never-guess rule — render nothing until
   *  this flips. */
  loaded: boolean;
  /** True while `pro` comes from a device receipt the server has not
   *  confirmed. Never persisted; cleared by the next successful refresh. */
  optimistic: boolean;

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
  optimistic: false,

  loadCached: async () => {
    try {
      const raw = await AsyncStorage.getItem(CACHE_KEY);
      if (raw) {
        const c = JSON.parse(raw) as Partial<CachedEntitlements> | null;
        const fetchedAt = typeof c?.fetchedAt === 'number' ? c.fetchedAt : 0;
        const fresh = fetchedAt > 0 && Date.now() - fetchedAt <= GRACE_MS;
        set({
          // Grace expired ⇒ read as free. Deliberately not "keep the last
          // value": an indefinitely-honored cached grant is a free Pro
          // subscription for anyone who stays offline.
          pro: fresh ? !!c?.pro : false,
          expiresAt: fresh ? (c?.expiresAt ?? null) : null,
          optimistic: false,
        });
      }
    } catch {
      /* non-fatal — hydrate is opportunistic, same posture as the flag store */
    } finally {
      set({ loaded: true });
    }
  },

  refresh: async () => {
    // The route is session-authed; without a token the call can only 401 and
    // clear nothing useful, so skip it and keep whatever the cache said.
    if (!useSession.getState().hasToken) return;
    try {
      const res = await getEntitlements();
      const pro = !!res?.pro;
      const expiresAt = res?.expires_at ?? null;
      // Server wins in BOTH directions, and clearing `optimistic` here is the
      // point: a refund or a failed webhook must be able to take Pro away.
      set({ pro, expiresAt, loaded: true, optimistic: false });
      const blob: CachedEntitlements = { pro, expiresAt, fetchedAt: Date.now() };
      try {
        await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(blob));
      } catch {
        /* non-fatal — cache write is opportunistic */
      }
    } catch {
      // Offline or backend down: keep the cached answer (still inside its
      // grace window) rather than locking a paying user out mid-flight.
      set({ loaded: true });
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

let _listenerBound = false;

/** Boot hook (App.tsx): hydrate the cache, ask the server, and subscribe to
 *  RevenueCat's CustomerInfo pushes so a renewal or a purchase made outside
 *  the paywall unlocks the UI immediately. Fire-and-forget; never throws.
 *  The listener is a no-op subscription when purchases are unavailable. */
export function initEntitlements(): void {
  void useEntitlements
    .getState()
    .loadCached()
    .then(() => useEntitlements.getState().refresh())
    .catch(() => {});
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
      useEntitlements.getState().noteCustomerInfo(hasProEntitlement(info));
      // Ask the server too — the push is the hint, the fetch is the answer.
      void useEntitlements.getState().refresh();
    });
  });
}
