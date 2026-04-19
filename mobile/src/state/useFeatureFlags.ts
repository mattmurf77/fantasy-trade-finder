import { create } from 'zustand';
import { loadFeatureFlags } from '../api/flags';
import type { FlagMap } from '../shared/types';

interface FlagState {
  flags: FlagMap;
  loaded: boolean;
  load: () => Promise<void>;
}

export const useFeatureFlags = create<FlagState>((set) => ({
  flags: {},
  loaded: false,
  load: async () => {
    const flags = await loadFeatureFlags();
    set({ flags, loaded: true });
  },
}));

/** Convenience hook: `useFlag("swipe.community_compare")` returns bool. */
export function useFlag(key: string): boolean {
  return useFeatureFlags((s) => !!s.flags[key]);
}
