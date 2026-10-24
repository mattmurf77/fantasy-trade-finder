// 200 ms path, C — where the device-held first page lives (rules:
// utils/devicePage.ts).
//
// An in-memory map is the read path: the tap reads it synchronously, so a
// held page renders with no wait. AsyncStorage keeps it across launches
// (hydrated once, on the first Trades focus). A discard bumps an epoch (all
// pages, or the one key), and a background refresh that started before it
// drops its response, so a page refreshed while a rankings write was in
// flight is never kept.
//
// Discards: a rankings or preference write (api/client's write listener,
// isRankingWritePath: every page the user holds), sign-out / account switch
// / deletion (clearDevicePages, from useSession.signOut), and any server
// answer for the key that can't be kept (devicePageFrom → null). A league or
// format switch reads a different key.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { onlineManager } from '@tanstack/react-query';
import { setOnWriteRequest } from '../api/client';
import { generateTrades, type GenerateBody, type PagedTradeJobSnapshot } from '../api/trades';
import {
  DEVICE_PAGE_KEY_PREFIX,
  devicePageFrom,
  isRankingWritePath,
  parseDevicePage,
  refreshDue,
  withoutCard,
  type DevicePage,
} from '../utils/devicePage';

const pages = new Map<string, DevicePage>();
const lastAttemptAt = new Map<string, number>();
const inFlight = new Set<string>();
const persistTimers = new Map<string, ReturnType<typeof setTimeout>>();
const keyEpochs = new Map<string, number>();
let epoch = 0;
let hydration: Promise<void> | null = null;
// A swipe rewrites the page; the disk copy trails it by this much.
const PERSIST_DEBOUNCE_MS = 300;

function persist(key: string) {
  const t = persistTimers.get(key);
  if (t) clearTimeout(t);
  persistTimers.set(key, setTimeout(() => {
    persistTimers.delete(key);
    const page = pages.get(key);
    const write = page
      ? AsyncStorage.setItem(key, JSON.stringify(page))
      : AsyncStorage.removeItem(key);
    write.catch(() => { /* memory still holds it; the bound ages it out */ });
  }, PERSIST_DEBOUNCE_MS));
}

/** Load the stored pages into memory, once per process. Never throws. */
export function hydrateDevicePages(): Promise<void> {
  if (!hydration) {
    hydration = (async () => {
      const startEpoch = epoch;
      try {
        const keys = (await AsyncStorage.getAllKeys())
          .filter((k) => k.startsWith(DEVICE_PAGE_KEY_PREFIX));
        if (keys.length === 0) return;
        const rows = await AsyncStorage.multiGet(keys);
        if (epoch !== startEpoch) return; // discarded while reading
        for (const [key, raw] of rows) {
          const page = parseDevicePage(raw);
          if (page && !pages.has(key)) pages.set(key, page);
        }
      } catch { /* no device page this launch */ }
    })();
  }
  return hydration;
}

/** The held page for a key (synchronous: the tap's read). */
export function readDevicePage(key: string | null): DevicePage | null {
  return key ? pages.get(key) ?? null : null;
}

export function discardDevicePage(key: string) {
  keyEpochs.set(key, (keyEpochs.get(key) ?? 0) + 1);
  if (!pages.delete(key)) return;
  persist(key);
}

/** Keep `page` for `key`, or discard the key's page when it is null (a
 *  server answer that can't be kept supersedes what the device holds). */
export function saveDevicePage(key: string, page: DevicePage | null) {
  if (!page) {
    discardDevicePage(key);
    return;
  }
  pages.set(key, page);
  persist(key);
}

/** Swipe update: the acted-on card leaves the page, whichever deck it was
 *  acted on in, so it never comes back on the next tap. */
export function removeDeviceCard(key: string | null, cardKey: string) {
  const page = key ? pages.get(key) : undefined;
  if (!key || !page) return;
  const next = withoutCard(page, cardKey);
  if (next === page) return;
  saveDevicePage(key, next.cards.length > 0 ? next : null);
}

/** Sign-out, account switch, account deletion: every device page goes,
 *  from memory and from disk. */
export async function clearDevicePages(): Promise<void> {
  epoch += 1;
  pages.clear();
  lastAttemptAt.clear();
  for (const t of persistTimers.values()) clearTimeout(t);
  persistTimers.clear();
  try {
    const keys = (await AsyncStorage.getAllKeys())
      .filter((k) => k.startsWith(DEVICE_PAGE_KEY_PREFIX));
    if (keys.length > 0) await AsyncStorage.multiRemove(keys);
  } catch { /* best effort; the keys are per user, and the bound ages them */ }
}

function discardAllDevicePages() {
  epoch += 1;
  for (const key of [...pages.keys()]) {
    pages.delete(key);
    persist(key);
  }
}

// The client's own rankings / preference writes (sent, and again settled).
setOnWriteRequest((path) => {
  if (isRankingWritePath(path)) discardAllDevicePages();
});

export interface DevicePageTarget {
  key: string;
  scope: string;
  /** The organic request, exactly as the tap sends it. */
  request: GenerateBody;
}

/** Approach B's background refresh, for Trades focus and app foreground:
 *  E2's page 1 (P1 serves it from the page store, or it joins the running
 *  or pre-built job), under no search id. At most once per key per
 *  DEVICE_PAGE_REFRESH_MIN_S, one at a time, never offline. Keeps the page
 *  only when devicePageFrom does; any other answer discards the key's page.
 *  A failed request keeps what is held (the max age bounds it). */
export async function refreshDevicePage(target: DevicePageTarget, now = Date.now()): Promise<void> {
  if (!onlineManager.isOnline() || inFlight.has(target.key)
      || !refreshDue(lastAttemptAt.get(target.key), now)) {
    return;
  }
  lastAttemptAt.set(target.key, now);
  inFlight.add(target.key);
  const startEpoch = epoch;
  const startKeyEpoch = keyEpochs.get(target.key) ?? 0;
  let res: PagedTradeJobSnapshot;
  try {
    res = await generateTrades(target.request, {});
  } catch {
    return;
  } finally {
    inFlight.delete(target.key);
  }
  // A discard happened while it was out: what it answered is superseded.
  if (epoch !== startEpoch || (keyEpochs.get(target.key) ?? 0) !== startKeyEpoch) return;
  saveDevicePage(target.key, devicePageFrom(res, { scope: target.scope, validatedAt: Date.now() }));
}
