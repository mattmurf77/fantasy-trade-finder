// 200 ms path, C — where the device-held first page lives (rules:
// utils/devicePage.ts).
//
// An in-memory map is the read path: the tap reads it synchronously, so a
// held page renders with no wait. AsyncStorage keeps it across launches
// (hydrated once, on the first Trades focus). A discard bumps an epoch (all
// pages, or the one key), and a background refresh that started before it
// drops its response, so a page refreshed while a rankings write was in
// flight is never kept. A discard also stamps WHEN (device clock, all pages
// or the one key), and a save of cards validated before that is refused, so
// a deck that predates a re-rank can't write its cards back on its next
// swipe.
//
// Discards: a rankings or preference write or a format switch (api/client's
// write listener, discardsDevicePages: every page the user holds), sign-out
// / account switch / deletion (clearDevicePages, from useSession), and any
// server answer for the key that can't be kept (devicePageFrom → null). A
// league or format switch reads a different key, and the deck on screen
// writes only under the key it was validated for (TradesScreen deckKeyRef).
import AsyncStorage from '@react-native-async-storage/async-storage';
import { onlineManager } from '@tanstack/react-query';
import { setOnWriteRequest } from '../api/client';
import { generateTrades, type GenerateBody, type PagedTradeJobSnapshot } from '../api/trades';
import {
  DEVICE_PAGE_KEY_PREFIX,
  devicePageFrom,
  discardsDevicePages,
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
// The validation time a kept page must not predate: the last discard of
// every page (`discardedAt`) or of its key (`keyDiscardedAt`).
const keyDiscardedAt = new Map<string, number>();
let discardedAt = 0;
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

/** Drop the key's page. `asOf` is the validation time the discard answers
 *  (a server answer's, or a deck's): cards validated before it are never
 *  kept for this key again. */
export function discardDevicePage(key: string, asOf = Date.now()) {
  keyEpochs.set(key, (keyEpochs.get(key) ?? 0) + 1);
  keyDiscardedAt.set(key, Math.max(keyDiscardedAt.get(key) ?? 0, asOf));
  if (!pages.delete(key)) return;
  persist(key);
}

/** Keep `page` for `key`, or discard the key's page when it is null (a
 *  server answer that can't be kept supersedes what the device holds; `asOf`
 *  as in discardDevicePage). A page validated before the last discard of its
 *  key, or of every key, is refused: it predates what superseded it. */
export function saveDevicePage(key: string, page: DevicePage | null, asOf?: number) {
  if (!page) {
    discardDevicePage(key, asOf);
    return;
  }
  if (page.validated_at < Math.max(discardedAt, keyDiscardedAt.get(key) ?? 0)) return;
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
  // Emptied by swipes: nothing newer superseded it (asOf = its own time).
  saveDevicePage(key, next.cards.length > 0 ? next : null, page.validated_at);
}

/** Sign-out, account switch, account deletion: every device page goes,
 *  from memory and from disk. */
export async function clearDevicePages(): Promise<void> {
  epoch += 1;
  discardedAt = Math.max(discardedAt, Date.now());
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
  discardedAt = Math.max(discardedAt, Date.now());
  for (const key of [...pages.keys()]) {
    pages.delete(key);
    persist(key);
  }
}

// The client's own rankings / preference writes and format switches (sent,
// and again settled).
setOnWriteRequest((path) => {
  if (discardsDevicePages(path)) discardAllDevicePages();
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
    // #393 M2 (D2): a background refresh; its 402 opens nothing.
    res = await generateTrades(target.request, {}, { background: true });
  } catch {
    return;
  } finally {
    inFlight.delete(target.key);
  }
  // A discard happened while it was out: what it answered is superseded.
  if (epoch !== startEpoch || (keyEpochs.get(target.key) ?? 0) !== startKeyEpoch) return;
  const answeredAt = Date.now();
  saveDevicePage(target.key, devicePageFrom(res, { scope: target.scope, validatedAt: answeredAt }), answeredAt);
}
