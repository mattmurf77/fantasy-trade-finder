import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { loadFeatureFlags } from '../api/flags';
import type { FlagMap } from '../shared/types';

// AsyncStorage key for the last successfully-fetched feature flag map.
// Hydrating from this on boot keeps gated features visible during a
// cold-start network wait and preserves them through a transient backend
// outage — addresses review fix #10 / silent-bugs.md bug #4 (the bare
// `{}` fallback silently hid every gated feature on net error).
const FF_KEY = 'feature_flags_v1';

interface FlagState {
  flags: FlagMap;
  loaded: boolean;
  /** Local-only AsyncStorage hydrate. Awaited by the boot gate so flag-
   *  gated UI settles to cached values before the first screen renders.
   *  Never touches the network — safe inside the splash-gating set. */
  loadCachedFlags: () => Promise<void>;
  /** Network revalidate. Fetches the live flag map and persists it. Run
   *  detached (fire-and-forget) after boot — must NOT gate the splash. */
  revalidateFlags: () => Promise<void>;
}

export const useFeatureFlags = create<FlagState>((set) => ({
  flags: {},
  loaded: false,
  loadCachedFlags: async () => {
    // Optimistically hydrate from AsyncStorage before the network fetch
    // so users get cached flags during a cold-start wait. First-ever
    // launch (no stored entry) falls back to `{}`. Best-effort — a
    // storage read failure just means we wait for the network revalidate.
    try {
      const cachedRaw = await AsyncStorage.getItem(FF_KEY);
      if (cachedRaw) {
        const parsed = JSON.parse(cachedRaw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          set({ flags: parsed as FlagMap });
        }
      }
    } catch {
      /* non-fatal — hydrate is opportunistic */
    }
  },
  revalidateFlags: async () => {
    // Network fetch. On success, replace the in-memory map AND persist so
    // the next boot has a fresh cache. On failure, `loadFeatureFlags`
    // returns `{}` today — but we don't want that to clobber the hydrated
    // cache, so we detect the failure here and keep the cached flags.
    try {
      const flags = await loadFeatureFlags({ throwOnError: true });
      set({ flags, loaded: true });
      try {
        await AsyncStorage.setItem(FF_KEY, JSON.stringify(flags));
      } catch {
        /* non-fatal — cache write is opportunistic */
      }
    } catch {
      // Network fetch failed — keep whatever we hydrated (or `{}` on first
      // launch). Mark loaded=true so gated components stop waiting.
      set({ loaded: true });
    }
  },
}));

/** Convenience hook: `useFlag("swipe.community_compare")` returns bool. */
export function useFlag(key: string): boolean {
  return useFeatureFlags((s) => !!s.flags[key]);
}
