import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

// In-app feedback capture (TestFlight-era helper).
//
// Lives only on-device until the user explicitly shares it out via the
// Settings → Test feedback inbox screen. No backend round-trip — keeps
// the surface tiny and makes the feature trivially removable when the
// app graduates to a real release.

export type FeedbackSeverity = 'bug' | 'polish' | 'idea';

export interface FeedbackItem {
  id: string;
  created_at: string;        // ISO
  screen: string;            // e.g. 'Trades' / 'Tiers' / 'Rank/Trios'
  severity: FeedbackSeverity;
  text: string;
  // Lightweight context the user didn't have to think about. Useful when
  // we read these back weeks later.
  app_version?: string;
}

const STORAGE_KEY = 'ftf_inapp_feedback_v1';

interface FeedbackState {
  items: FeedbackItem[];
  hydrated: boolean;
  hydrate: () => Promise<void>;
  add: (entry: Omit<FeedbackItem, 'id' | 'created_at'>) => Promise<FeedbackItem>;
  remove: (id: string) => Promise<void>;
  clear: () => Promise<void>;
}

async function persist(items: FeedbackItem[]): Promise<void> {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* AsyncStorage full / privacy mode — best-effort */
  }
}

export const useFeedback = create<FeedbackState>((set, get) => ({
  items: [],
  hydrated: false,

  hydrate: async () => {
    if (get().hydrated) return;
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      const parsed: FeedbackItem[] = raw ? JSON.parse(raw) : [];
      // Newest first — display order matches what the user just typed.
      parsed.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
      set({ items: parsed, hydrated: true });
    } catch {
      set({ items: [], hydrated: true });
    }
  },

  add: async (entry) => {
    const item: FeedbackItem = {
      ...entry,
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      created_at: new Date().toISOString(),
    };
    const next = [item, ...get().items];
    set({ items: next });
    await persist(next);
    return item;
  },

  remove: async (id) => {
    const next = get().items.filter((i) => i.id !== id);
    set({ items: next });
    await persist(next);
  },

  clear: async () => {
    set({ items: [] });
    await persist([]);
  },
}));

// Format the inbox as a markdown blob the user can paste back into chat
// after sharing. Grouped by screen so the result is scannable.
export function formatFeedbackAsMarkdown(items: FeedbackItem[]): string {
  if (items.length === 0) return '_No feedback recorded yet._';
  const date = new Date().toISOString().slice(0, 10);
  const byScreen = new Map<string, FeedbackItem[]>();
  for (const it of items) {
    const arr = byScreen.get(it.screen) || [];
    arr.push(it);
    byScreen.set(it.screen, arr);
  }
  let out = `# DTF Mobile Feedback — ${date}\n\n`;
  for (const [screen, list] of byScreen) {
    out += `## ${screen}\n\n`;
    for (const it of list) {
      const stamp = it.created_at.slice(11, 16); // HH:MM (UTC; rough is fine)
      const sev =
        it.severity === 'bug'    ? '🐞 Bug'    :
        it.severity === 'polish' ? '✨ Polish' :
                                   '💡 Idea';
      out += `- **${sev}** _(${stamp})_\n  ${it.text.replace(/\n/g, '\n  ')}\n\n`;
    }
  }
  return out;
}
