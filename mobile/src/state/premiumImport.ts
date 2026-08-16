// premiumImport.ts — client-side staleness stamps for premium rank-set
// imports (Connected Rankings addendum §2 lane 1, [D-058]).
//
// v1 is deliberately SCHEMA-FREE: there is no backend row behind a premium
// source (no `ranking_connections`, no provenance table yet — that is WS-A
// later), so "imported N weeks ago" is derived from a device-local stamp
// written after a successful apply. Nothing here is authoritative for
// anything except the nudge copy on the import sheet; losing it degrades to
// "no prior import", never to a wrong board.
//
// Storage mirrors the useOnboardingState pattern: zustand for the render
// path, AsyncStorage for durability, both writes opportunistic.

import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

import type { PremiumSource } from '../utils/rankPresets';

const KEY = 'ftf.premium_import.v1';

/** source → ISO timestamp of the last SUCCESSFUL apply from that source. */
export type ImportStamps = Partial<Record<PremiumSource, string>>;

interface State {
  stamps: ImportStamps;
  hydrated: boolean;
  load: () => Promise<void>;
  markImported: (source: PremiumSource, at?: Date) => Promise<void>;
}

export const usePremiumImport = create<State>((set, get) => ({
  stamps: {},
  hydrated: false,
  load: async () => {
    if (get().hydrated) return;
    try {
      const raw = await AsyncStorage.getItem(KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          set({ stamps: parsed as ImportStamps });
        }
      }
    } catch {
      /* non-fatal — the nudge simply doesn't render */
    } finally {
      set({ hydrated: true });
    }
  },
  markImported: async (source, at) => {
    const next = { ...get().stamps, [source]: (at ?? new Date()).toISOString() };
    set({ stamps: next });
    try {
      await AsyncStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* non-fatal */
    }
  },
}));

/** "imported 3 weeks ago" — the lane-1 staleness line. Returns null when
 *  there is no prior import for the source (the row then shows no line at
 *  all rather than a zero). */
export function stalenessLabel(
  iso: string | undefined,
  now: Date = new Date(),
): string | null {
  if (!iso) return null;
  const then = Date.parse(iso);
  if (!Number.isFinite(then)) return null;
  const days = Math.floor((now.getTime() - then) / 86_400_000);
  if (days < 0) return null;
  const weeks = Math.floor(days / 7);
  if (weeks < 1) return 'imported this week';
  return `imported ${weeks} week${weeks === 1 ? '' : 's'} ago`;
}
