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
import { AppState } from 'react-native';
import { onlineManager } from '@tanstack/react-query';
import { getSessionRevision, setOnWriteRequest, runWithDeadline } from '../api/client';
import { invalidateTradeSearchHandoffs, tradeSearchContextIdentity, TradeSearchContextChangedError } from './tradeSearchHandoff';
import { generateTrades, getTradeStatus, type GenerateBody, type PagedTradeJobSnapshot } from '../api/trades';
import {
  DEVICE_PAGE_KEY_PREFIX,
  devicePageFrom,
  devicePageScope,
  discardsDevicePages,
  parseDevicePage,
  refreshDue,
  withoutCard,
  type DevicePage,
} from '../utils/devicePage';

const pages = new Map<string, DevicePage>();
const lastAttemptAt = new Map<string, number>();
const inFlight = new Map<string, () => boolean>();
const activeScopes = new Map<string, string>();
const PREWARM_REQUEST = { background: true, headers: { 'X-FTF-Prewarm': '1' } };
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
// A dispatched storage write cannot be canceled. Clear must run after it,
// and a newer account/page write after that clear, in the same order.
let storageTail: Promise<void> = Promise.resolve();
function storageWrite(write: () => Promise<void>): Promise<void> {
  const next = storageTail.then(write);
  storageTail = next.catch(() => {});
  return next;
}

function persist(key: string) {
  const t = persistTimers.get(key);
  if (t) clearTimeout(t);
  persistTimers.set(key, setTimeout(() => {
    persistTimers.delete(key);
    void storageWrite(() => {
      // Read at execution, not enqueue: queued obsolete snapshots never win.
      const page = pages.get(key);
      return page ? AsyncStorage.setItem(key, JSON.stringify(page)) : AsyncStorage.removeItem(key);
    }).catch(() => { /* memory still holds it; the bound ages it out */ });
  }, PERSIST_DEBOUNCE_MS));
}

/** Load the stored pages into memory, once per process. Never throws. */
export function hydrateDevicePages(): Promise<void> {
  if (!hydration) {
    hydration = (async () => {
      const startEpoch = epoch;
      const startKeyEpochs = new Map(keyEpochs);
      try {
        const keys = (await AsyncStorage.getAllKeys())
          .filter((k) => k.startsWith(DEVICE_PAGE_KEY_PREFIX) || k.startsWith('ftf_trade_device_page_v1:'));
        if (keys.length === 0) return;
        const rows = await AsyncStorage.multiGet(keys);
        if (epoch !== startEpoch) return; // discarded while reading
        for (const [key, raw] of rows) {
          const page = parseDevicePage(raw);
          if (page && !pages.has(key)
              && (keyEpochs.get(key) ?? 0) === (startKeyEpochs.get(key) ?? 0)
              && page.validated_at >= Math.max(discardedAt, keyDiscardedAt.get(key) ?? 0)) pages.set(key, page);
        }
      } catch { /* no device page this launch */ }
    })();
  }
  return hydration;
}

/** The held page for a key (synchronous: the tap's read). */
export function readDevicePage(key: string | null): DevicePage | null {
  return key && !pendingTradeWrites ? pages.get(key) ?? null : null;
}

/** Drop the key's page. `asOf` is the validation time the discard answers
 *  (a server answer's, or a deck's): cards validated before it are never
 *  kept for this key again. */
export function discardDevicePage(key: string, asOf = Date.now()) {
  keyEpochs.set(key, (keyEpochs.get(key) ?? 0) + 1);
  keyDiscardedAt.set(key, Math.max(keyDiscardedAt.get(key) ?? 0, asOf));
  pages.delete(key);
  persist(key); // Also remove a disk-only page rejected during hydration.
}

/** Keep `page` for `key`, or discard the key's page when it is null (a
 *  server answer that can't be kept supersedes what the device holds; `asOf`
 *  as in discardDevicePage). A page validated before the last discard of its
 *  key, or of every key, is refused: it predates what superseded it. */
export function saveDevicePage(key: string, page: DevicePage | null, asOf?: number) {
  if (page && pendingTradeWrites) return;
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
  invalidateTradeSearchHandoffs();
  epoch += 1;
  discardedAt = Math.max(discardedAt, Date.now());
  pages.clear();
  lastAttemptAt.clear();
  activeScopes.clear();
  for (const t of persistTimers.values()) clearTimeout(t);
  persistTimers.clear();
  await storageWrite(async () => {
    const keys = (await AsyncStorage.getAllKeys())
      .filter((k) => k.startsWith(DEVICE_PAGE_KEY_PREFIX) || k.startsWith('ftf_trade_device_page_v1:'));
    if (keys.length > 0) await AsyncStorage.multiRemove(keys);
  }).catch(() => { /* best effort; the keys are per user, and the bound ages them */ });
}

function discardAllDevicePages() {
  epoch += 1;
  // A ranking/format/roster write invalidates the warmed request itself;
  // its old throttle must not suppress preparation for the new inputs.
  lastAttemptAt.clear();
  discardedAt = Math.max(discardedAt, Date.now());
  pages.clear();
  for (const t of persistTimers.values()) clearTimeout(t);
  persistTimers.clear();
  // Include pages not yet hydrated. Queue this barrier before later valid
  // writes so a disk-only pre-mutation page cannot return on next launch.
  void storageWrite(async () => {
    const keys = (await AsyncStorage.getAllKeys())
      .filter((k) => k.startsWith(DEVICE_PAGE_KEY_PREFIX) || k.startsWith('ftf_trade_device_page_v1:'));
    if (keys.length > 0) await AsyncStorage.multiRemove(keys);
  }).catch(() => { /* best effort; the existing age bound still applies */ });
}

// A fresh page may be prepared when all overlapping writes have settled.
let pendingTradeWrites = 0;
export class TradeInputReadinessError extends Error {}
let lastInputSaveFailure: { context: string; at: number } | undefined;
export function hasPendingTradePageInputs(): boolean { return pendingTradeWrites > 0; }

function inputSaveFailedSince(tapAt: number): boolean {
  return !!lastInputSaveFailure && lastInputSaveFailure.at >= tapAt
    && lastInputSaveFailure.context === tradeSearchContextIdentity();
}
function inputSaveError(): TradeInputReadinessError {
  return new TradeInputReadinessError('Your preference changes could not be saved. Try again.');
}

/** Synchronous admission check closes promise-continuation gaps. */
export function assertTradePageInputsReady(tapAt: number): void {
  if (hasPendingTradePageInputs()) throw new TradeSearchContextChangedError();
  if (inputSaveFailedSince(tapAt)) throw inputSaveError();
}

/** Wait only within the original request deadline; no network or trace starts here. */
export async function waitForTradePageInputs(
  deadlineAt: number, current: () => boolean, tapAt: number,
): Promise<void> {
  await runWithDeadline(signal => new Promise<void>((resolve, reject) => {
    let unsubscribe = () => {};
    const finish = (error?: Error) => {
      unsubscribe();
      signal.removeEventListener('abort', aborted);
      if (error) reject(error); else resolve();
    };
    const aborted = () => finish(new Error('Trade readiness was interrupted. Try again.'));
    const check = () => {
      if (!current()) return finish(new TradeSearchContextChangedError());
      if (inputSaveFailedSince(tapAt)) return finish(inputSaveError());
      if (!hasPendingTradePageInputs()) finish();
    };
    unsubscribe = onTradePageInputsSettled(check);
    signal.addEventListener('abort', aborted, { once: true });
    if (signal.aborted) aborted(); else check();
  }), deadlineAt);
  if (!current()) throw new TradeSearchContextChangedError();
}
const settledListeners = new Set<() => void>();
export function onTradePageInputsSettled(listener: () => void): () => void {
  settledListeners.add(listener);
  return () => { settledListeners.delete(listener); };
}
export function notifyTradePageInputsSettled(): void {
  if (pendingTradeWrites === 0) settledListeners.forEach(listener => listener());
}

/** Hold the existing write fence through a server write's local mirrors too.
 * API settlement alone is earlier than scoring-format persistence/commit. */
export function beginTradePageInputTransition(saveContext?: string | null): (succeeded?: boolean) => void {
  pendingTradeWrites++;
  invalidateTradeSearchHandoffs();
  discardAllDevicePages();
  let finished = false;
  return (succeeded = true) => {
    if (finished) return;
    finished = true;
    if (!succeeded && saveContext && saveContext === tradeSearchContextIdentity()) {
      // Navigation can finish after a failed save, before the destination
      // begins waiting. Record it only for the account and league that saved.
      lastInputSaveFailure = { context: saveContext, at: globalThis.performance.now() };
    }
    pendingTradeWrites = Math.max(0, pendingTradeWrites - 1);
    invalidateTradeSearchHandoffs();
    discardAllDevicePages();
    notifyTradePageInputsSettled();
  };
}
setOnWriteRequest((path, phase) => {
  if (!discardsDevicePages(path)) return;
  if (phase === 'start') pendingTradeWrites++;
  if (phase === 'settled') pendingTradeWrites = Math.max(0, pendingTradeWrites - 1);
  invalidateTradeSearchHandoffs();
  discardAllDevicePages();
  if (phase === 'settled') notifyTradePageInputsSettled();
});

export interface DevicePageTarget {
  key: string;
  scope: string;
  format: '1qb_ppr' | 'sf_tep';
  /** The organic request, exactly as the tap sends it. */
  request: GenerateBody;
}

/** Approach B's background refresh, for early tab mount, Trades focus and app foreground:
 *  E2's page 1 (P1 serves it from the page store, or it joins the running
 *  or pre-built job), under no search id. At most once per key per
 *  DEVICE_PAGE_REFRESH_MIN_S per key/scope, one current attempt, never offline. Keeps the page
 *  only when devicePageFrom does; any other answer discards the key's page.
 *  A failed request keeps what is held (the max age bounds it). */
export async function refreshDevicePage(
  target: DevicePageTarget,
  now = Date.now(),
  shouldContinue: () => boolean = () => true,
): Promise<void> {
  const { key, scope, format } = target;
  if ((format !== '1qb_ppr' && format !== 'sf_tep')
      || devicePageScope(target.request) !== scope) return;
  const request = { ...target.request };
  const requestOptions = { ...PREWARM_REQUEST,
    headers: { ...PREWARM_REQUEST.headers, 'X-Scoring-Format': format } };
  const startRevision = getSessionRevision();
  const attemptKey = JSON.stringify([key, scope]);
  const previous = inFlight.get(attemptKey);
  if (previous && !previous()) lastAttemptAt.delete(attemptKey);
  if (pendingTradeWrites || !shouldContinue() || AppState.currentState !== 'active' || !onlineManager.isOnline()
      || (previous && previous())
      || !refreshDue(lastAttemptAt.get(attemptKey), now)) {
    return;
  }
  lastAttemptAt.set(attemptKey, now);
  activeScopes.set(key, scope);
  const startEpoch = epoch;
  const startKeyEpoch = keyEpochs.get(key) ?? 0;
  const current = () => shouldContinue() && AppState.currentState === 'active' && onlineManager.isOnline()
    && getSessionRevision() === startRevision
    && epoch === startEpoch && (keyEpochs.get(key) ?? 0) === startKeyEpoch
    && activeScopes.get(key) === scope;
  inFlight.set(attemptKey, current);
  let res: PagedTradeJobSnapshot;
  try {
    // #393 M2 (D2): a background refresh; its 402 opens nothing.
    res = await generateTrades(request, {}, requestOptions);
    // Session-init can still be building this job. Previously its first
    // running response was discarded and the 60-second throttle prevented
    // adopting the completed page before the first calculator tap. Follow
    // THAT job for at most 40 polls over a 90-second window; never start
    // another generation or spend a paid preview. The server's prewarm
    // header guard refuses preview delivery until an actual user tap.
    // Provisional cards are never persisted. Every status response still passes the
    // server's ownership/freshness checks and devicePageFrom below.
    const pollUntil = Date.now() + 90_000;
    for (let poll = 0; poll < 40 && Date.now() < pollUntil && res.status === 'running'
        && typeof res.cursor === 'number'; poll += 1) {
      if (!current()) return;
      const delay = Math.min(3_000, 500 * 2 ** Math.floor(poll / 4));
      await new Promise<void>((resolve) => setTimeout(resolve, delay));
      if (!current()) return;
      if (Date.now() >= pollUntil) break;
      res = await getTradeStatus(res.job_id, { deck: res.deck_id || res.job_id, cursor: 0 }, requestOptions);
    }
  } catch (error) {
    // A passive request cannot claim a free preview. Its server refusal
    // revokes any previously held page too; the tap takes the normal gate.
    const denied = error as { status?: number; body?: { error?: string } };
    if (current() && denied.status === 409 && denied.body?.error === 'prewarm_requires_tap') {
      discardDevicePage(key);
    }
    return;
  } finally {
    const ownsAttempt = inFlight.get(attemptKey) === current;
    if (ownsAttempt) inFlight.delete(attemptKey);
    // Canceled or replaced work must not suppress a resumed foreground's
    // new attempt for the next minute.
    if (ownsAttempt && !current() && lastAttemptAt.get(attemptKey) === now) lastAttemptAt.delete(attemptKey);
  }
  // A discard happened while it was out: what it answered is superseded.
  if (!current()) return;
  const answeredAt = Date.now();
  saveDevicePage(key, devicePageFrom(res, { scope, validatedAt: answeredAt }), answeredAt);
}
