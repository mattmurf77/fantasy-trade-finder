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
      unreadCount: s.unreadCount + 1,
    }));
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
