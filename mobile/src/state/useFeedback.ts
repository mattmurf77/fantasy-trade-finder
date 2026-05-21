import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { submitFeedback } from '../api/feedback';

// In-app feedback capture (TestFlight-era helper).
//
// Local AsyncStorage is still the source of truth from the user's POV —
// every save lands on-device immediately and never blocks the UI. A
// background POST to /api/feedback then mirrors the note into the backend
// store; `synced` tracks whether the round-trip succeeded. Failures are
// silent except for the badge in FeedbackInboxScreen, and `retrySync()`
// + the App.tsx AppState foreground hook re-attempt unsynced items.

export type FeedbackSeverity = 'bug' | 'polish' | 'idea';

export interface FeedbackItem {
  id: string;
  created_at: string;        // ISO — client capture time, doubles as client_id payload field
  screen: string;            // e.g. 'Trades' / 'Tiers' / 'Rank/Trios'
  severity: FeedbackSeverity;
  text: string;
  // Lightweight context the user didn't have to think about. Useful when
  // we read these back weeks later.
  app_version?: string;

  // ── Sync state ───────────────────────────────────────────────────────
  // synced=true means the backend confirmed the row. Items hydrated from
  // pre-sync storage default to true (see hydrate()) so we don't re-POST
  // stale captures the user already moved on from.
  synced: boolean;
  server_id?: number;
  last_sync_attempt?: string; // ISO; debug-only visibility for the inbox
  last_sync_error?: string;   // short human string; cleared on success
}

const STORAGE_KEY = 'ftf_inapp_feedback_v1';

interface FeedbackState {
  items: FeedbackItem[];
  hydrated: boolean;
  hydrate: () => Promise<void>;
  add: (entry: Omit<FeedbackItem, 'id' | 'created_at' | 'synced'>) => Promise<FeedbackItem>;
  remove: (id: string) => Promise<void>;
  clear: () => Promise<void>;
  retrySync: () => Promise<void>;
}

async function persist(items: FeedbackItem[]): Promise<void> {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* AsyncStorage full / privacy mode — best-effort */
  }
}

// Best-effort short error string for last_sync_error. Avoids dumping a
// full stack into the inbox UI.
function _describeSyncError(err: unknown): string {
  if (err && typeof err === 'object') {
    const anyErr = err as { status?: number; message?: string };
    if (typeof anyErr.status === 'number') {
      return anyErr.message ? `HTTP ${anyErr.status} — ${anyErr.message}` : `HTTP ${anyErr.status}`;
    }
    if (anyErr.message) return anyErr.message;
  }
  return 'network error';
}

// POST a single item; merge the result back into the items array (returns
// the new array, not the state). Pure-ish helper so add() and retrySync()
// share the patch logic.
async function _syncOne(item: FeedbackItem): Promise<Partial<FeedbackItem>> {
  const nowIso = new Date().toISOString();
  try {
    const res = await submitFeedback({
      client_id: item.id,
      screen: item.screen,
      severity: item.severity,
      text: item.text,
      client_created_at: item.created_at,
    });
    return {
      synced: true,
      server_id: res.server_id,
      last_sync_attempt: nowIso,
      last_sync_error: undefined,
    };
  } catch (err) {
    return {
      synced: false,
      last_sync_attempt: nowIso,
      last_sync_error: _describeSyncError(err),
    };
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
      // Authoritative test for "actually synced": the backend assigned a
      // server_id. Anything else needs a sync attempt. This catches two
      // cases the prior hydrate logic mis-handled:
      //   1. Items written before the sync field existed (synced undefined).
      //   2. Items written by the first sync-aware build that got stamped
      //      synced=true by the old "default to true" hydrate but were
      //      never actually POSTed (no server_id present).
      // Real synced items always carry a server_id from _syncOne, so this
      // is also a no-op for them. The next foreground tick of retrySync()
      // will drain whatever this flips back to unsynced.
      const normalized = parsed.map((it) => ({
        ...it,
        synced: !!it.server_id,
      }));
      // Newest first — display order matches what the user just typed.
      normalized.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
      set({ items: normalized, hydrated: true });
    } catch {
      set({ items: [], hydrated: true });
    }
  },

  add: async (entry) => {
    const item: FeedbackItem = {
      ...entry,
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      created_at: new Date().toISOString(),
      synced: false,
    };
    const next = [item, ...get().items];
    set({ items: next });
    await persist(next);

    // Fire-and-forget background sync. Resolves into a patch on the item;
    // we never throw to the caller — UI shouldn't care whether the POST
    // landed (the badge will reflect it). Use an IIFE so we don't await.
    void (async () => {
      const patch = await _syncOne(item);
      const current = get().items;
      const merged = current.map((i) => (i.id === item.id ? { ...i, ...patch } : i));
      set({ items: merged });
      await persist(merged);
    })();

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

  retrySync: async () => {
    // Snapshot the unsynced ids up front; new items added during the loop
    // handle their own sync via add()'s background path.
    const initialPending = get().items.filter((i) => !i.synced);
    if (initialPending.length === 0) return;

    // Sequential — small N (a tester's feedback inbox) and we'd rather not
    // hammer the backend with parallel POSTs from a single device.
    for (const target of initialPending) {
      // Re-read in case state mutated mid-loop (delete, clear, etc.).
      const live = get().items.find((i) => i.id === target.id);
      if (!live || live.synced) continue;

      const patch = await _syncOne(live);
      const current = get().items;
      const merged = current.map((i) => (i.id === target.id ? { ...i, ...patch } : i));
      set({ items: merged });
      await persist(merged);
    }
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
