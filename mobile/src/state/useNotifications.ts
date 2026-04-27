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

const ITEMS_CAP = 50;

/** Tri-state mirroring expo-notifications' permission status, plus a
 *  bootstrap value for "we haven't asked the OS yet." LeagueScreen reads
 *  this to surface a banner when the user denied — they need to flip the
 *  toggle in iOS Settings; we can't re-prompt. */
export type PushPermissionStatus =
  | 'unknown'        // pre-prompt, or simulator (push doesn't work)
  | 'undetermined'   // OS hasn't been asked yet
  | 'granted'
  | 'denied';

interface NotificationsState {
  items: AppNotification[];
  unreadCount: number;
  permissionStatus: PushPermissionStatus;

  add: (n: Omit<AppNotification, 'receivedAt' | 'read'>) => void;
  markAllRead: () => void;
  clear: () => void;
  setPermissionStatus: (s: PushPermissionStatus) => void;
}

export const useNotifications = create<NotificationsState>((set, get) => ({
  items: [],
  unreadCount: 0,
  permissionStatus: 'unknown',

  add: (n) => {
    const item: AppNotification = {
      ...n,
      receivedAt: Date.now(),
      read: false,
    };
    set((s) => ({
      items: [item, ...s.items].slice(0, ITEMS_CAP),
      // Cap unreadCount at the same cap as items. Without this, after 50+
      // distinct pushes the badge would say "9+" forever even after the
      // older items were dropped from the list.
      unreadCount: Math.min(s.unreadCount + 1, ITEMS_CAP),
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

  setPermissionStatus: (s) => {
    if (get().permissionStatus === s) return;   // skip no-op renders
    set({ permissionStatus: s });
  },
}));
