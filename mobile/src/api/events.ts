// events.ts — first-party analytics SDK (analytics-platform P1: LLD §2.5/§4.6).
//
// Batches client events into POST /api/events. Fire-and-forget by contract:
// analytics must NEVER block or break product UX, so every path here swallows
// its own errors (mirrors the backend record_event() contract).
//
//   • track(event_type, props?, screen?) — the only call sites need.
//   • In-memory queue, flushed every 10s, at 20 queued, and on app background.
//     Persisted to AsyncStorage ({v:1,events:[…]}) for offline; restored on
//     boot. A v0 plain-array blob under the same key hits the unknown-shape
//     discard path (LLD §1.1 — one-time transition loss, never a crash).
//   • Drop-oldest beyond 500 queued EXCEPT funnel-critical events, which
//     drop last (LLD §4.6); ≤50 events per POST.
//   • seq: per-session monotonic from 1, reset on session rotation — the
//     signal that makes event loss measurable server-side (SM-2).
//   • Response-driven purge (LLD §2.1): server always replies 200 with
//     {accepted, deduped, rejected, disposition}. rejected → purge always;
//     accepted+deduped+|rejected| == N → purge batch; sum < N (txn failure)
//     → requeue the non-rejected; batch_rejected:* → purge; disabled →
//     RETAIN + stop flushing + max backoff until the flag flips back on.
//   • Kill switch: track() is dark unless the FETCHED `analytics.client_events`
//     is true (undefined = off — the key is deliberately NOT baked into the
//     flag store's LAUNCHED_FLAG_DEFAULTS, so first-boot-before-fetch is dark).
//   • device_id: 'dev_' + UUID, minted once in SecureStore (Keychain —
//     survives reinstall). session_id: UUID, rotated on cold start + after
//     30 min inactivity.
//
// Layering note: unlike the other api/ modules this one reads the feature-flag
// store (zustand getState — no React) because the send gate lives client-side
// by spec; it owns AsyncStorage/SecureStore persistence for the same reason.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppState } from 'react-native';
import { getBaseUrl, getClientHeaders, getDeviceId, getSessionToken } from './client';
import { useFeatureFlags } from '../state/useFeatureFlags';
// draft-extensions W3 M-D: uuidv4, the backoff ladder and the disposition-
// parsing logic are shared with `recordedPicks.ts`'s offline queue (which
// copies this module's contract verbatim) — extracted to `_queue.ts` so the
// two cannot silently drift. Behavior here is unchanged; only the source of
// these three pieces moved.
import {
  uuidv4 as _sharedUuidv4,
  DEFAULT_BACKOFF_LADDER_MS,
  nextBackoffStep,
  parseQueueDisposition,
} from './_queue';

// Re-exported for API stability — the canonical mint now lives in client.ts
// so events.ts and flags.ts share one device id without an import cycle.
export { getDeviceId };

const FLAG_KEY = 'analytics.client_events';
const QUEUE_KEY = 'ftf.events.queue.v1';   // reused across the v0→P1 cutover
const QUEUE_SHAPE_VERSION = 1;

const MAX_QUEUE = 500;        // drop-oldest (non-critical) beyond this
const BATCH_MAX = 50;         // envelope cap per POST (backend contract)
const FLUSH_AT = 20;          // queue length that forces a flush
const FLUSH_INTERVAL_MS = 10_000;
const SESSION_IDLE_MS = 30 * 60_000;  // 30 min inactivity → new session_id
const SEND_TIMEOUT_MS = 10_000;       // own AbortController; NOT client.ts retry

// Backoff ladder (LLD §4.6): 30s → 2m → 10m cap, ±20% jitter, reset on a
// consumed batch or on foreground. Shared constant — see `_queue.ts`.
const BACKOFF_LADDER_MS = DEFAULT_BACKOFF_LADDER_MS;

// Funnel-critical event types drop LAST under queue pressure (LLD §4.6 —
// mirrors backend/analytics_taxonomy.py FUNNEL_CRITICAL; keep in sync).
const FUNNEL_CRITICAL = new Set<string>([
  'app_opened', 'signin_attempted', 'signin_succeeded', 'experiment_exposed',
]);

interface QueuedEvent {
  event_id: string;
  event_type: string;
  client_ts: string;          // ISO UTC
  screen?: string;
  props?: Record<string, unknown>;
  session_id: string;
  seq: number;                // per-session monotonic (LLD §4.6)
}

// ── UUID ────────────────────────────────────────────────────────────────
// crypto.getRandomValues is present in the Expo runtime. If it were ever
// absent we fall back to a device-local unique id (timestamp + monotonic
// counter) — NEVER Math.random for an idempotency key (LLD §4.6). The
// fallback can only collide across devices, which is irrelevant to dedup and
// astronomically unlikely given it is virtually never taken.
// Shared with `recordedPicks.ts` via `_queue.ts` — see its comment.
const uuidv4 = _sharedUuidv4;

// ── Module state ────────────────────────────────────────────────────────
const APP_OPEN_TS = Date.now();

let queue: QueuedEvent[] = [];
let sessionId = uuidv4();           // rotated on cold start (module load)
let seq = 0;                        // per-session; ++ per track, reset on rotate
let lastActivityTs = Date.now();
let initPromise: Promise<void> | null = null;
let inFlight = false;

// Backoff / disabled gate.
let backoffIndex = -1;              // -1 = no active backoff
let nextAllowedFlushTs = 0;
let droppedShapeMismatch = 0;       // v0-blob discards (observability)

/** Milliseconds since this JS bundle loaded (cold app open). */
export function msSinceOpen(): number {
  return Date.now() - APP_OPEN_TS;
}

function flagEnabled(): boolean {
  try {
    return useFeatureFlags.getState().flags[FLAG_KEY] === true;  // undefined = off
  } catch {
    return false;
  }
}

// ── Init: queue restore + timers + background flush ─────────────────────
function ensureInit(): Promise<void> {
  if (!initPromise) {
    initPromise = (async () => {
      try {
        const raw = await AsyncStorage.getItem(QUEUE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          // P1 shape only: {v:1, events:[…]}. Anything else (the v0 plain
          // array, a future version, corruption) is discarded — never crash,
          // never resurrect an unknown shape (LLD §3.4/§1.1).
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)
              && parsed.v === QUEUE_SHAPE_VERSION && Array.isArray(parsed.events)) {
            queue = [...(parsed.events as QueuedEvent[]), ...queue];
            trimQueue();
          } else {
            droppedShapeMismatch += 1;
            AsyncStorage.removeItem(QUEUE_KEY).catch(() => {});
          }
        }
      } catch {
        droppedShapeMismatch += 1;   // corrupt JSON — discard, start empty
        AsyncStorage.removeItem(QUEUE_KEY).catch(() => {});
      }
      try {
        setInterval(() => void flush(), FLUSH_INTERVAL_MS);
        AppState.addEventListener('change', (next) => {
          if (next === 'active') resetBackoff();            // foreground → retry now
          if (next === 'background' || next === 'inactive') void flush();
        });
      } catch {
        /* timers/AppState unavailable (tests) — track still queues */
      }
    })();
  }
  return initPromise;
}

/** Boot hook (App.tsx): restore the offline queue and start the flush loop
 *  without waiting for the first track() call. Fire-and-forget. */
export function initAnalytics(): void {
  void ensureInit().then(() => void flush());
}

function persistQueue(): void {
  AsyncStorage.setItem(
    QUEUE_KEY, JSON.stringify({ v: QUEUE_SHAPE_VERSION, events: queue }),
  ).catch(() => {});
}

/** Trim to MAX_QUEUE, evicting non-critical events oldest-first before any
 *  funnel-critical one (LLD §4.6 drop-last). */
function trimQueue(): void {
  if (queue.length <= MAX_QUEUE) return;
  let over = queue.length - MAX_QUEUE;
  // First pass: drop oldest non-critical.
  const kept: QueuedEvent[] = [];
  for (const e of queue) {
    if (over > 0 && !FUNNEL_CRITICAL.has(e.event_type)) { over -= 1; continue; }
    kept.push(e);
  }
  // If still over (all remaining are critical), drop oldest critical.
  queue = over > 0 ? kept.slice(over) : kept;
}

// ── Public API ──────────────────────────────────────────────────────────
/** Queue an analytics event. Synchronous no-throw fire-and-forget; a no-op
 *  (nothing queued) while `analytics.client_events` is off. */
export function track(
  eventType: string,
  props?: Record<string, unknown>,
  screen?: string,
): void {
  try {
    if (!flagEnabled()) return;
    const now = Date.now();
    if (now - lastActivityTs > SESSION_IDLE_MS) { sessionId = uuidv4(); seq = 0; }
    lastActivityTs = now;
    seq += 1;
    const evt: QueuedEvent = {
      event_id: uuidv4(),
      event_type: eventType,
      client_ts: new Date(now).toISOString(),
      ...(screen ? { screen } : {}),
      ...(props ? { props } : {}),
      session_id: sessionId,
      seq,
    };
    void enqueue(evt);
  } catch {
    /* analytics must never break product UX */
  }
}

async function enqueue(evt: QueuedEvent): Promise<void> {
  try {
    await ensureInit();
    queue.push(evt);
    trimQueue();
    persistQueue();
    if (queue.length >= FLUSH_AT) void flush();
  } catch {
    /* swallow */
  }
}

// ── Backoff ─────────────────────────────────────────────────────────────
function resetBackoff(): void {
  backoffIndex = -1;
  nextAllowedFlushTs = 0;
}

function applyBackoff(toMax = false): void {
  const step = nextBackoffStep(BACKOFF_LADDER_MS, backoffIndex, toMax);
  backoffIndex = step.index;
  nextAllowedFlushTs = Date.now() + step.delayMs;
}

// ── Flush ───────────────────────────────────────────────────────────────
async function flush(): Promise<void> {
  if (inFlight) return;
  if (Date.now() < nextAllowedFlushTs) return;      // backoff window
  inFlight = true;
  try {
    await ensureInit();
    // Gate every send on the flag. Events stay queued while it's off — a
    // mid-hydration false must not drop a valid offline backlog.
    while (queue.length > 0 && flagEnabled()) {
      const batch = queue.slice(0, BATCH_MAX);
      const result = await sendBatch(batch);
      if (result.kind === 'retry') { applyBackoff(); break; }
      if (result.kind === 'disabled') { applyBackoff(true); break; }  // retain, stop
      // Consumed (ok / batch_rejected): purge per the LLD §2.1 rule.
      resetBackoff();
      if (result.purgeAll) {
        queue.splice(0, batch.length);
      } else {
        // Sum-short (txn failure): purge only rejected indices, requeue rest.
        const rejectedIdx = new Set(result.rejectedIndices);
        const survivors = batch.filter((_, i) => !rejectedIdx.has(i));
        queue.splice(0, batch.length, ...survivors);
        // Nothing more will succeed this pass; wait for the next tick.
        persistQueue();
        break;
      }
      persistQueue();
    }
  } catch {
    /* swallow */
  } finally {
    inFlight = false;
  }
}

// Shared with `recordedPicks.ts` — see `_queue.ts`.
type SendResult = import('./_queue').QueueDisposition;

async function sendBatch(batch: QueuedEvent[]): Promise<SendResult> {
  try {
    const [deviceId, token] = await Promise.all([getDeviceId(), getSessionToken()]);
    const headers: Record<string, string> = {
      // X-Device / X-OS-Version / X-App-Version / X-User-TZ — the backend
      // derives platform + app_version + os_version from these. Omitting them
      // (the pre-2026-08-05 bug) landed every client event with those columns
      // NULL, which blinded per-platform and per-release reporting.
      ...getClientHeaders(),
      'Content-Type': 'application/json',
      'X-Device-Id': deviceId,
    };
    if (token) headers['X-Session-Token'] = token;
    // Raw fetch, not apiRequest: the wrapper's 401 handling clears the stored
    // session token, and an analytics send must never do that. Own timeout.
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), SEND_TIMEOUT_MS);
    let res: Response;
    try {
      res = await fetch(`${getBaseUrl()}/api/events`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ events: batch }),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }
    // 5xx / non-OK short-circuit BEFORE parsing the body — preserved from
    // the pre-extraction control flow so a malformed 5xx body is never even
    // read. Everything past this point funnels through the shared
    // disposition parser (`_queue.ts`), which `recordedPicks.ts` also calls.
    if (res.status >= 500) return { kind: 'retry' };
    if (!res.ok) {
      return { kind: 'consumed', purgeAll: true, rejectedIndices: [] };
    }
    const body = await res.json().catch(() => null) as {
      accepted?: number; deduped?: number;
      rejected?: { index: number; reason: string }[];
      disposition?: string;
    } | null;
    return parseQueueDisposition(res.status, res.ok, body, batch.length);
  } catch {
    return { kind: 'retry' };   // network error / timeout
  }
}

/** Test/observability hook: count of v0-blob / corrupt-queue discards. */
export function _shapeMismatchCount(): number {
  return droppedShapeMismatch;
}
