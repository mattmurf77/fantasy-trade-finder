// _queue.ts — shared offline-write-queue primitives (draft-extensions W3 M-D).
//
// Extracted from `events.ts` (analytics-platform P1) the moment a SECOND
// offline queue (`recordedPicks.ts`, the live-draft pick recorder) needed
// the identical contract: uuidv4 idempotency keys, a backoff ladder with
// jitter, and the accepted/deduped/rejected response-driven purge rule. The
// task brief is explicit: "copy that contract; do not invent a second one."
// Extracting the pure pieces here — rather than duplicating them — is what
// keeps the two queues from drifting while only ONE of them (events.ts) has
// production evidence behind it.
//
// Deliberately NOT extracted: the stateful queue/flush/persist loop itself.
// events.ts's `queue`/`flush`/`ensureInit` machinery is battle-tested and
// carries analytics-specific concerns (the kill-switch flag gate, the
// funnel-critical drop-last trim policy, `session_id`/`seq`). Reimplementing
// that loop as a shared generic would be a bigger, riskier refactor of a
// production path this wave does not need to touch. `recordedPicks.ts`
// builds its own loop, structurally identical to events.ts's, from these
// primitives — "copy the contract" at the level of behavior, not a shared
// class neither queue's tests were written against.

// ── UUID ────────────────────────────────────────────────────────────────
// crypto.getRandomValues is present in the Expo runtime. If it were ever
// absent we fall back to a device-local unique id (timestamp + monotonic
// counter) — NEVER Math.random for an idempotency key. The fallback can
// only collide across devices, which is irrelevant to dedup (the SERVER
// idempotency key for recorded picks is (league, season, overall), not this
// uuid) and astronomically unlikely given it is virtually never taken.
let _idCounter = 0;
export function uuidv4(): string {
  const cryptoObj = (globalThis as { crypto?: Crypto }).crypto;
  if (cryptoObj?.getRandomValues) {
    const b = new Uint8Array(16);
    cryptoObj.getRandomValues(b);
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }
  _idCounter = (_idCounter + 1) % 1_000_000;
  return `loc-${Date.now().toString(36)}-${_idCounter.toString(36)}-${(_idCounter * 2654435761 >>> 0).toString(36)}`;
}

// ── Backoff ladder ─────────────────────────────────────────────────────
// events.ts's ladder verbatim: 30s -> 2m -> 10m cap, ±20% jitter (pacing
// only — the CAP is exact), reset on a consumed batch or on foreground.
export const DEFAULT_BACKOFF_LADDER_MS = [30_000, 120_000, 600_000];

/** Pure step function: given the ladder, the CURRENT index (-1 = no active
 *  backoff) and whether to jump straight to the max (the `disabled`
 *  disposition), returns the next index and the delay to wait. The caller
 *  owns the mutable `backoffIndex` / `nextAllowedFlushTs` state — this
 *  function only computes the next step, so it stays trivially testable. */
export function nextBackoffStep(
  ladderMs: number[],
  index: number,
  toMax: boolean,
): { index: number; delayMs: number } {
  const nextIndex = toMax
    ? ladderMs.length - 1
    : Math.min(index + 1, ladderMs.length - 1);
  const base = ladderMs[nextIndex];
  const jitter = base * 0.2 * (Math.random() * 2 - 1);   // ±20% pacing only
  return { index: nextIndex, delayMs: base + jitter };
}

// ── Response-driven purge (the accepted/deduped/rejected contract) ──────
// The reconciliation shape both queues' servers answer with. `disposition`
// is analytics-specific (the `analytics.client_events` kill switch /
// `batch_rejected*`) and OPTIONAL here — a server response with no
// `disposition` key (recorded-picks' shape) simply never takes those two
// branches, which is exactly what the recorder needs since it has no
// "disabled" business state of its own (the whole surface is either
// `draft.manual_picks` on, or the route 404s before any of this runs).
export interface QueueReconciliation {
  accepted?: number;
  deduped?: number;
  rejected?: { index: number; reason?: string }[];
  disposition?: string;
}

export type QueueDisposition =
  | { kind: 'retry' }
  | { kind: 'disabled' }
  | { kind: 'consumed'; purgeAll: boolean; rejectedIndices: number[] };

/** THE disposition ladder, lifted verbatim from `events.ts`'s `sendBatch`:
 *  5xx -> retry; a non-OK non-5xx status (an old/unexpected server
 *  contract) -> consumed + purgeAll (drop rather than storm); unparseable
 *  body -> consumed + purgeAll; `disposition:"disabled"` -> disabled;
 *  `disposition` starting `"batch_rejected"` -> consumed + purgeAll;
 *  otherwise, `sum(accepted, deduped, rejected.length) >= batchLength` ->
 *  the whole batch resolved (purgeAll), else a txn-failure short read ->
 *  purge only the rejected indices and requeue the rest. */
export function parseQueueDisposition(
  status: number,
  ok: boolean,
  body: QueueReconciliation | null,
  batchLength: number,
): QueueDisposition {
  if (status >= 500) return { kind: 'retry' };
  if (!ok) return { kind: 'consumed', purgeAll: true, rejectedIndices: [] };
  if (!body) return { kind: 'consumed', purgeAll: true, rejectedIndices: [] };
  if (body.disposition === 'disabled') return { kind: 'disabled' };
  if (typeof body.disposition === 'string'
      && body.disposition.startsWith('batch_rejected')) {
    return { kind: 'consumed', purgeAll: true, rejectedIndices: [] };
  }
  const accepted = body.accepted ?? 0;
  const deduped = body.deduped ?? 0;
  const rejected = body.rejected ?? [];
  const sum = accepted + deduped + rejected.length;
  return {
    kind: 'consumed',
    purgeAll: sum >= batchLength,
    rejectedIndices: rejected.map((r) => r.index),
  };
}
