import { api } from './client';
import type { NotificationItem } from '../shared/types';

// GET /api/notifications?user_id=X  — returns the bell inbox
export async function getNotifications(userId: string) {
  return api.get<{ notifications: NotificationItem[]; unread_count: number }>(
    `/api/notifications?user_id=${encodeURIComponent(userId)}`,
  );
}

// POST /api/notifications/read — mark one read
export async function markNotificationRead(notificationId: string | number) {
  return api.post<any>('/api/notifications/read', {
    notification_id: notificationId,
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
