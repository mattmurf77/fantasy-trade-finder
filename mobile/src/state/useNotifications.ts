import { create } from 'zustand';

// In-memory notification feed. Driven by usePushNotifications which pumps
// every push received (foreground or tapped) into this store. The TopBar
// reads from here to render the bell badge + sheet contents.
//
// Persistence is intentionally NOT included — a notification feed should
// reset on relaunch so stale pushes don't pile up. The badge "unread"
// state is in-session only; once the user opens the bell sheet the items
// are marked read and the dot disappears until a new push arrives.

export interface AppNotification {
  id: string;
  title: string;
  body: string;
  receivedAt: number;
  read: boolean;
  /** Original push data payload (e.g. {type: 'trade_match', match_id: 42}) */
  data?: Record<string, unknown>;
}

interface NotificationsState {
  items: AppNotification[];
  unreadCount: number;
  add: (n: Omit<AppNotification, 'receivedAt' | 'read'>) => void;
  /** S5 PRD-02 (flag `notif.tap_routing_v2`): merge the server inbox
   *  (GET /api/notifications) into the feed. Server rows win on id clash;
   *  in-session pushes not yet persisted server-side are kept. Called with
   *  the bell sheet open (which marks everything read), so unreadCount
   *  settles to 0. */
  hydrateFromServer: (serverItems: AppNotification[]) => void;
  markAllRead: () => void;
  clear: () => void;
}

export const useNotifications = create<NotificationsState>((set, get) => ({
  items: [],
  unreadCount: 0,

  add: (n) => {
    const item: AppNotification = {
      ...n,
      receivedAt: Date.now(),
      read: false,
    };
    set((s) => ({
      items: [item, ...s.items].slice(0, 50), // cap so we don't grow forever
      // Cap the badge counter at the same number as items. Without this,
      // after 50+ pushes without markAllRead firing, `unreadCount` would
      // climb forever even though `items` stays at 50 — the badge would
      // read "9+" indefinitely with nothing to clear it short of opening
      // the bell sheet.
      unreadCount: Math.min(s.unreadCount + 1, 50),
    }));
  },

  hydrateFromServer: (serverItems) => {
    set((s) => {
      const serverIds = new Set(serverItems.map((it) => it.id));
      const localOnly = s.items.filter((it) => !serverIds.has(it.id));
      const merged = [...serverItems, ...localOnly]
        .sort((a, b) => b.receivedAt - a.receivedAt)
        .slice(0, 50);
      return { items: merged, unreadCount: 0 };
    });
  },

  markAllRead: () => {
    if (get().unreadCount === 0) return;
    set((s) => ({
      items: s.items.map((it) => ({ ...it, read: true })),
      unreadCount: 0,
    }));
  },

  clear: () => set({ items: [], unreadCount: 0 }),
}));
