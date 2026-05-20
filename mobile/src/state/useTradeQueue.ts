import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Linking, Alert } from 'react-native';
import { useSession } from './useSession';
import type { QueuedTrade } from '../shared/types';

// Trade queue store — Bundle 5 of the mobile-feature-parity plan.
//
// The web equivalent (see `web/js/app.js` "2K-STYLE TRADE QUEUE") lets users
// stack multiple trade ideas and "Send All" opens each on Sleeper's trade-
// propose URL with a 500ms stagger. We mirror that here.
//
// Persistence: AsyncStorage under key `ftf_trade_queue_<user_id>`. Per-user
// (not per-league) so signing in/out doesn't mix queues across accounts;
// per-league scoping lives in the in-memory `byLeague` map. Hydration reads
// only the current user's blob; if no user yet, hydrate is a no-op (the
// store stays empty until the next hydrate call after sign-in).

const STORAGE_KEY_PREFIX = 'ftf_trade_queue_';
const SEND_ALL_STAGGER_MS = 500;

function storageKey(userId: string): string {
  return `${STORAGE_KEY_PREFIX}${userId}`;
}

interface TradeQueueState {
  byLeague: Record<string, QueuedTrade[]>;
  hydrated: boolean;

  /** Load the persisted queue for the currently signed-in user. Safe to
   *  call multiple times (e.g. after sign-in). No-op if no user. */
  hydrate: () => Promise<void>;

  enqueue: (leagueId: string, trade: QueuedTrade) => void;
  dequeue: (leagueId: string, tradeId: string) => void;
  clear: (leagueId: string) => void;

  /** Open each queued trade's `sleeper_url` with a 500ms stagger, then
   *  clear the queue. Matches the web "Send All" UX. Falls back to an
   *  Alert when Linking.canOpenURL rejects a URL (very rare). */
  sendAll: (leagueId: string) => Promise<void>;
}

async function persist(byLeague: Record<string, QueuedTrade[]>): Promise<void> {
  const userId = useSession.getState().user?.user_id;
  if (!userId) return;
  try {
    await AsyncStorage.setItem(storageKey(userId), JSON.stringify(byLeague));
  } catch {
    // Quota full / disabled — non-fatal. The in-memory queue still works
    // for this session; we just can't survive a relaunch.
  }
}

export const useTradeQueue = create<TradeQueueState>((set, get) => ({
  byLeague: {},
  hydrated: false,

  hydrate: async () => {
    const userId = useSession.getState().user?.user_id;
    if (!userId) {
      // No user — clear in-memory state so a previous session's queue
      // doesn't leak (e.g. user A signs out, user B signs in).
      set({ byLeague: {}, hydrated: true });
      return;
    }
    try {
      const raw = await AsyncStorage.getItem(storageKey(userId));
      if (!raw) {
        set({ byLeague: {}, hydrated: true });
        return;
      }
      const parsed = JSON.parse(raw);
      // Defensive: shape may drift across versions. Accept only the
      // expected `Record<string, QueuedTrade[]>` shape; otherwise reset.
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        const clean: Record<string, QueuedTrade[]> = {};
        for (const [lid, arr] of Object.entries(parsed)) {
          if (Array.isArray(arr)) clean[lid] = arr as QueuedTrade[];
        }
        set({ byLeague: clean, hydrated: true });
      } else {
        set({ byLeague: {}, hydrated: true });
      }
    } catch {
      set({ byLeague: {}, hydrated: true });
    }
  },

  enqueue: (leagueId, trade) => {
    set((s) => {
      const existing = s.byLeague[leagueId] || [];
      // Dedupe by trade_id — re-tapping Queue on the same card is a no-op.
      if (existing.some((q) => q.trade_id === trade.trade_id)) return s;
      const byLeague = { ...s.byLeague, [leagueId]: [...existing, trade] };
      // Fire-and-forget persist; UI doesn't need to await.
      void persist(byLeague);
      return { byLeague };
    });
  },

  dequeue: (leagueId, tradeId) => {
    set((s) => {
      const existing = s.byLeague[leagueId];
      if (!existing) return s;
      const filtered = existing.filter((q) => q.trade_id !== tradeId);
      if (filtered.length === existing.length) return s;
      const byLeague = { ...s.byLeague, [leagueId]: filtered };
      void persist(byLeague);
      return { byLeague };
    });
  },

  clear: (leagueId) => {
    set((s) => {
      if (!s.byLeague[leagueId] || s.byLeague[leagueId].length === 0) return s;
      const byLeague = { ...s.byLeague, [leagueId]: [] };
      void persist(byLeague);
      return { byLeague };
    });
  },

  sendAll: async (leagueId) => {
    const queue = get().byLeague[leagueId] || [];
    if (queue.length === 0) return;

    for (let i = 0; i < queue.length; i++) {
      const url = queue[i].sleeper_url;
      try {
        const can = await Linking.canOpenURL(url);
        if (can) {
          await Linking.openURL(url);
        } else if (i === 0) {
          // Only alert once, on the first un-openable URL. If Linking
          // can't handle https at all, every URL will fail and we'd
          // otherwise spam the user.
          Alert.alert('Could not open Sleeper', 'Open Sleeper manually to propose the trade.');
        }
      } catch {
        // Swallow per-URL failures; one bad deep-link shouldn't abort
        // the rest of the queue.
      }
      // 500ms stagger between opens — matches the web behavior and
      // gives Sleeper / the OS time to handle each one in turn.
      if (i < queue.length - 1) {
        await new Promise((r) => setTimeout(r, SEND_ALL_STAGGER_MS));
      }
    }

    get().clear(leagueId);
  },
}));
