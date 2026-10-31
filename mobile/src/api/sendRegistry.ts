// Which ESPN / MFL trades have a send in flight, or one that ended without a
// definitive answer (#527 QA P2-A, 2026-10-29).
//
// Why: a send's state used to live only in the button's useState, and the
// ESPN/MFL propose routes have no cross-request idempotency. With the send
// wait at up to 91 s (api/sendOutcome.ts), leaving and reopening a trade
// remounted its button as an idle Send while the first request was still
// running, and after an unknown outcome nothing reminded the user to check
// before sending again. This keeps that state per trade, outside React, so a
// remount reads it back. The buttons read it with useSyncExternalStore.
//
// In memory, per app run: it survives a remount, NOT an app restart (a cold
// start begins empty). Bounded: past SEND_REGISTRY_CAP trades, `sent` entries
// go first, then `unknown`, oldest first in each, and never one `in_flight`.
// Plain module state, no React, no imports.
// Pinned by tests/check-send-registry.js.

export type SendPlatform = 'espn' | 'mfl';

/** in_flight: the request is out. Set synchronously before it is sent.
 *  unknown:   it ended without a definitive answer (isSendOutcomeUnknown), so
 *             the trade may be in the league. The confirm dialog repeats 8e/8f.
 *  sent:      confirmed. The button shows "Proposal sent", on a remount too. */
export type SendState = 'in_flight' | 'unknown' | 'sent';

export interface SendRecord {
  state: SendState;
  /** Date.now() when the state was set. */
  at: number;
}

export const SEND_REGISTRY_CAP = 50;

const records = new Map<string, SendRecord>(); // insertion order: oldest first
const listeners = new Set<() => void>();

/** One trade, canonically: platform + league + counterparty + both sides'
 *  asset ids. These are the identifiers the propose payload carries
 *  (league_id, their_user_id, give_player_ids, receive_player_ids: player and
 *  FTF pick ids, never names). Each side is sorted, so the order the assets
 *  were added in doesn't matter. JSON keeps the fields from running together. */
export function tradeSendKey(
  platform: SendPlatform,
  leagueId: string,
  theirUserId: string,
  giveIds: readonly string[],
  receiveIds: readonly string[],
): string {
  return JSON.stringify([platform, leagueId, theirUserId, [...giveIds].sort(), [...receiveIds].sort()]);
}

export function getSendRecord(key: string): SendRecord | undefined {
  return records.get(key);
}

/** Call synchronously, before any await, when a send starts. False means this
 *  trade is already in flight (another mount, a same-frame double tap) or
 *  confirmed sent (a stale second confirm dialog): the caller must not send. */
export function beginSend(key: string): boolean {
  const state = records.get(key)?.state;
  if (state === 'in_flight' || state === 'sent') return false;
  put(key, 'in_flight');
  return true;
}

/** How the send ended. 'not_sent' is a definitive refusal (`*_write_failed`,
 *  `*_unavailable`, auth, unmapped assets, …): the trade is forgotten. */
export function settleSend(key: string, outcome: 'sent' | 'unknown' | 'not_sent'): void {
  if (outcome === 'not_sent') {
    records.delete(key);
    emit();
  } else {
    put(key, outcome);
  }
}

export function subscribeSends(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function put(key: string, state: SendState): void {
  records.delete(key); // re-inserted as the newest
  records.set(key, { state, at: Date.now() });
  evict(key);
  emit();
}

// Over the cap, drop what costs least to forget: a confirmed send (its button
// goes back to an idle Send), then an unknown outcome (its reminder is lost),
// oldest first in each. Never a send in flight: forgetting one would let a
// remount send it again, so if every entry is in flight the map stays over.
// Never the entry just written either: with the map over the cap because
// everything else is in flight, a send that just settled would otherwise be
// forgotten at once.
function evict(written: string): void {
  for (const state of ['sent', 'unknown'] as const) {
    for (const [key, record] of records) {
      if (records.size <= SEND_REGISTRY_CAP) return;
      if (record.state === state && key !== written) records.delete(key);
    }
  }
}

function emit(): void {
  for (const fn of listeners) fn();
}
