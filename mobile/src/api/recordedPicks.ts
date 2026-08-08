// Live offline pick recording — draft-extensions W3 M-D (lld §2.6/§4.6).
// Flag `draft.manual_picks`, ships OFF.
//
// ── What this is ────────────────────────────────────────────────────────
// ESPN hosts no rookie drafts, so an ESPN dynasty league's rookie draft
// happens off-platform — and once M-A's assignment grid has been filled in,
// the app knows whose pick 1.03 is. Recording is therefore "confirm, not
// select": tap the player who was taken, the team comes from the grid, the
// cursor auto-advances. This module is the offline write path underneath
// that screen.
//
// ── The offline queue — COPIED from events.ts, not reinvented ───────────
// Live drafts happen in venues with bad wifi. `events.ts` (analytics
// platform P1) is a battle-tested AsyncStorage queue with exactly the right
// semantics: per-item uuid idempotency key, backoff, foreground flush,
// {accepted, deduped, rejected} server reconciliation. This module copies
// that contract field-for-field (see the table in
// docs/plans/draft-extensions/lld.md §4.6.1); the shared PURE pieces
// (uuidv4, the backoff ladder, the disposition parser) live in `_queue.ts`
// so the two queues cannot silently drift.
//
// Deliberate divergences from events.ts, both named in the LLD:
//   - FLUSH_AT = 1, not 20. A recorded pick is a user-visible commitment —
//     send immediately when online. The interval-driven flush still exists
//     for the offline backlog.
//   - Trim policy: EVERY recorded pick is critical (there is no funnel-
//     critical/non-critical split for a physical draft pick), so a trim is
//     a straight FIFO slice of the oldest items — and it is COUNTED
//     (`recordQueueDroppedCount`), because plan §6.8's zero-tolerance bar
//     treats any drop as an idempotency bug, not a UX metric.
//
// ── The server idempotency key is (league, season, overall) ─────────────
// NOT this queue's client uuid (`event_id`) — two devices recording the
// same physical pick will not share a uuid, so the SERVER dedupes on the
// slot. `event_id` is carried along for audit and rejection-matching only.
//
// ── Void is NOT queued ────────────────────────────────────────────────
// Undo is a deliberate, low-frequency corrective tap, not a recording
// event, and `void_recorded_pick` is naturally idempotent server-side (a
// second void of an already-voided slot is a no-op, never an error) — so it
// goes straight over the network via `api.post`, with no offline queue of
// its own. Documented deviation from a literal reading of "copy the queue
// contract": there is exactly one thing in this feature that MUST survive
// airplane mode, and it is recording a pick, not un-recording one.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppState } from 'react-native';
import { api, getBaseUrl, getClientHeaders, getDeviceId, getSessionToken } from './client';
import {
  uuidv4,
  DEFAULT_BACKOFF_LADDER_MS,
  nextBackoffStep,
  parseQueueDisposition,
  type QueueDisposition,
} from './_queue';

const QUEUE_KEY = 'ftf.recpicks.queue.v1';
const QUEUE_SHAPE_VERSION = 1;

const MAX_QUEUE = 500;                // a 192-slot draft cannot overflow this
const BATCH_MAX = 50;                 // envelope cap per POST (backend contract)
// The ONE deliberate divergence from events.ts: send immediately, not at a
// queue-length threshold. A pick is a commitment, not telemetry.
const FLUSH_AT = 1;
const FLUSH_INTERVAL_MS = 10_000;
const SEND_TIMEOUT_MS = 10_000;

const BACKOFF_LADDER_MS = DEFAULT_BACKOFF_LADDER_MS;

export interface RecordedPickInput {
  leagueId: string;
  season: number;
  overall: number;
  round: number;
  slot: number;
  /** The team ON THE CLOCK — defaulted by the CALLER from the M-A
   *  assignment grid's owner for this slot, editable only when the grid
   *  was wrong. `null` when the slot is unowned/orphaned. */
  pickingTeamId: string | null;
  playerId: string;
}

interface QueuedPick {
  event_id: string;
  league_id: string;
  season: number;
  overall: number;
  round: number;
  slot: number;
  picking_team_id: string | null;
  player_id: string;
  client_ts: string;                  // ISO UTC
}

export interface RecordPicksResult {
  accepted: number;
  deduped: number;
  rejected: { index: number; reason: string }[];
}

export interface VoidedPick {
  overall: number;
  round: number;
  slot: number;
  picking_team_id: string | null;
  player_id: string;
  recorded_at: string;
}

export interface VoidPickResult {
  ok: true;
  overall: number;
  picks: VoidedPick[];
}

// ── Module state — one queue for the currently-recording league+season.
// A real draft is one league/season at a time, so a single in-memory queue
// (persisted the same way events.ts persists its own) is sufficient; a
// second concurrent recording session is not a supported scenario. ────────
let queue: QueuedPick[] = [];
let initPromise: Promise<void> | null = null;
let inFlight = false;
let backoffIndex = -1;
let nextAllowedFlushTs = 0;
let droppedCount = 0;

function ensureInit(): Promise<void> {
  if (!initPromise) {
    initPromise = (async () => {
      try {
        const raw = await AsyncStorage.getItem(QUEUE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)
              && parsed.v === QUEUE_SHAPE_VERSION && Array.isArray(parsed.picks)) {
            queue = [...(parsed.picks as QueuedPick[]), ...queue];
            trimQueue();
          } else {
            await AsyncStorage.removeItem(QUEUE_KEY).catch(() => {});
          }
        }
      } catch {
        await AsyncStorage.removeItem(QUEUE_KEY).catch(() => {});
      }
      try {
        setInterval(() => void flush(), FLUSH_INTERVAL_MS);
        AppState.addEventListener('change', (next) => {
          if (next === 'active') resetBackoff();
          if (next === 'background' || next === 'inactive') void flush();
        });
      } catch {
        /* timers/AppState unavailable (tests) — recordPick still queues */
      }
    })();
  }
  return initPromise;
}

/** Boot hook, mirroring `initAnalytics()` — restores the offline queue and
 *  starts the flush loop without waiting for the first `recordPick()` call.
 *  Safe to call unconditionally: with the flag off nothing ever enqueues,
 *  so this is an inert restore of an (almost certainly empty) queue. */
export function initRecordedPicksQueue(): void {
  void ensureInit().then(() => void flush());
}

function persistQueue(): void {
  AsyncStorage.setItem(
    QUEUE_KEY, JSON.stringify({ v: QUEUE_SHAPE_VERSION, picks: queue }),
  ).catch(() => {});
}

/** Every queued pick is critical — a straight FIFO trim, COUNTED (plan
 *  §6.8's zero-tolerance bar: any drop blocks the release). */
function trimQueue(): void {
  if (queue.length <= MAX_QUEUE) return;
  const over = queue.length - MAX_QUEUE;
  droppedCount += over;
  queue = queue.slice(over);
}

/** Test/observability hook — the zero-tolerance drop counter. A non-zero
 *  value here is a bug report, not a metric. */
export function recordQueueDroppedCount(): number {
  return droppedCount;
}

/** Queue one recorded pick and flush immediately (FLUSH_AT = 1). Fire-and-
 *  forget by contract, matching `events.ts`'s `track()` — the caller's UI
 *  updates OPTIMISTICALLY off this call; the reconciliation on the next
 *  successful flush is what confirms it server-side. */
export function recordPick(input: RecordedPickInput): void {
  try {
    const evt: QueuedPick = {
      event_id: uuidv4(),
      league_id: input.leagueId,
      season: input.season,
      overall: input.overall,
      round: input.round,
      slot: input.slot,
      picking_team_id: input.pickingTeamId,
      player_id: input.playerId,
      client_ts: new Date().toISOString(),
    };
    void enqueue(evt);
  } catch {
    /* recording must never throw into the UI thread */
  }
}

async function enqueue(evt: QueuedPick): Promise<void> {
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

function resetBackoff(): void {
  backoffIndex = -1;
  nextAllowedFlushTs = 0;
}

function applyBackoff(toMax = false): void {
  const step = nextBackoffStep(BACKOFF_LADDER_MS, backoffIndex, toMax);
  backoffIndex = step.index;
  nextAllowedFlushTs = Date.now() + step.delayMs;
}

async function flush(): Promise<void> {
  if (inFlight) return;
  if (Date.now() < nextAllowedFlushTs) return;
  inFlight = true;
  try {
    await ensureInit();
    while (queue.length > 0) {
      const batch = queue.slice(0, BATCH_MAX);
      const result = await sendBatch(batch);
      if (result.kind === 'retry' || result.kind === 'disabled') {
        // `disabled` cannot fire here (the server route has no such
        // disposition), but the shared parser's type includes it — treat
        // it identically to a retry rather than special-casing it away.
        applyBackoff(result.kind === 'disabled');
        break;
      }
      resetBackoff();
      if (result.purgeAll) {
        queue.splice(0, batch.length);
      } else {
        const rejectedIdx = new Set(result.rejectedIndices);
        const survivors = batch.filter((_, i) => !rejectedIdx.has(i));
        queue.splice(0, batch.length, ...survivors);
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

async function sendBatch(batch: QueuedPick[]): Promise<QueueDisposition> {
  try {
    const [deviceId, token] = await Promise.all([getDeviceId(), getSessionToken()]);
    const headers: Record<string, string> = {
      ...getClientHeaders(),
      'Content-Type': 'application/json',
      'X-Device-Id': deviceId,
    };
    if (token) headers['X-Session-Token'] = token;
    // Raw fetch, not apiRequest — the wrapper's 401 handling clears the
    // stored session token, which a queued write must never trigger.
    const leagueId = batch[0].league_id;
    const season = batch[0].season;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), SEND_TIMEOUT_MS);
    let res: Response;
    try {
      res = await fetch(`${getBaseUrl()}/api/league/recorded-picks`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          league_id: leagueId,
          season,
          picks: batch.map((p) => ({
            event_id: p.event_id, overall: p.overall, round: p.round,
            slot: p.slot, picking_team_id: p.picking_team_id,
            player_id: p.player_id, client_ts: p.client_ts,
          })),
        }),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }
    if (res.status >= 500) return { kind: 'retry' };
    if (!res.ok) {
      return { kind: 'consumed', purgeAll: true, rejectedIndices: [] };
    }
    const body = await res.json().catch(() => null) as RecordPicksResult | null;
    return parseQueueDisposition(res.status, res.ok, body, batch.length);
  } catch {
    return { kind: 'retry' };
  }
}

/** Non-destructive undo — see the module doc for why this is not queued.
 *  Returns the recomputed live slice on success, or throws (ApiError) on
 *  failure — the caller is a direct user tap, so a thrown/rejected promise
 *  is the right shape (unlike the fire-and-forget `recordPick`). */
export async function voidRecordedPick(args: {
  leagueId: string;
  season: number;
  overall: number;
}): Promise<VoidPickResult> {
  return api.post<VoidPickResult>('/api/league/recorded-picks/void', {
    league_id: args.leagueId,
    season: args.season,
    overall: args.overall,
  });
}
