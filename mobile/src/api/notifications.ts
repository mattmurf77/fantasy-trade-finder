import { api } from './client';
import type { NotificationItem, NotificationPrefs } from '../shared/types';

// GET /api/notifications?user_id=X  — returns the bell inbox
export async function getNotifications(userId: string) {
  return api.get<{ notifications: NotificationItem[]; unread_count: number }>(
    `/api/notifications?user_id=${encodeURIComponent(userId)}`,
  );
}

// POST /api/notifications/read — mark one read.
// Backend (server.py:4878-4898) reads `body["ids"]` (a list). Previously
// this wrapper sent `{notification_id}`, which the backend silently
// ignored — server returned `{ok:true, updated:0}` and the row stayed
// unread. Latent until a UI caller wired it up (see review #A1 / Fix 11).
export async function markNotificationRead(notificationId: string | number) {
  return api.post<any>('/api/notifications/read', {
    ids: [notificationId],
  });
}

// POST /api/notifications/read — bulk variant. Backend supports a list of
// ids in one request, so expose that directly for callers that batch.
export async function markNotificationsRead(
  notificationIds: Array<string | number>,
) {
  return api.post<any>('/api/notifications/read', {
    ids: notificationIds,
  });
}

// POST /api/notifications/read-all
export async function markAllNotificationsRead() {
  return api.post<any>('/api/notifications/read-all', {});
}

// POST /api/notifications/register-device
// Added during Phase 5. Backend persists the token so the match-create
// hook can send pushes. Best-effort — we don't block the UX on it.
export async function registerDeviceForPush(
  token: string,
  platform: 'ios' | 'android',
) {
  try {
    return await api.post<any>('/api/notifications/register-device', {
      device_token: token,
      platform,
    });
  } catch {
    // Swallow — the endpoint may not exist yet during the Phase-5 rollout.
    return { ok: false };
  }
}

// GET /api/notifications/prefs
export async function getNotifPrefs() {
  return api.get<NotificationPrefs>('/api/notifications/prefs');
}

// PUT /api/notifications/prefs — partial update
export async function updateNotifPrefs(patch: Partial<NotificationPrefs>) {
  return api.put<NotificationPrefs>('/api/notifications/prefs', patch);
}
