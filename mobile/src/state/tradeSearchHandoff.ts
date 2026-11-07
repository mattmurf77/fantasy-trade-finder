import { getSessionRevision } from '../api/client';
import { useSession } from './useSession';

// One user tap may cross a stack boundary before its response arrives.
// Keep that exact request in memory, once, rather than issuing it twice.
// This is not a result cache: no cross-tap, disk or approximate-scope reuse.
let generation = 0;
const flights = new Map<string, { identity: string; request: string; promise: Promise<unknown>; at: number }>();
const MAX_HANDOFF_MS = 10_000;

export class TradeSearchContextChangedError extends Error {
  readonly code = 'trade_search_context_changed';
  constructor() { super('trade_search_context_changed'); }
}

/** Authority that cannot be rebound while an accepted tap waits for saves. */
export function tradeSearchContextIdentity(): string | null {
  const s = useSession.getState();
  if (!s.hasToken || s.switching || !s.user?.user_id || !s.league?.league_id || !s.activeFormat) return null;
  return JSON.stringify([getSessionRevision(), s.user.user_id, s.league.league_id, s.activeFormat]);
}

export function tradeSearchIdentity(): string | null {
  const s = useSession.getState();
  if (!s.hasToken || s.switching || !s.user?.user_id || !s.league?.league_id || !s.activeFormat) return null;
  return JSON.stringify([getSessionRevision(), s.user.user_id, s.league.league_id, s.activeFormat, generation]);
}

// Preserve array order (a stricter match is safe), normalize only object
// property order and omitted undefined fields; every future filter counts.
function requestKey(kind: string, request: object): string {
  const stable = (v: any): any => Array.isArray(v) ? v.map(stable)
    : v && typeof v === 'object'
      ? Object.fromEntries(Object.keys(v).sort().filter((k) => v[k] !== undefined).map((k) => [k, stable(v[k])]))
      : v;
  return JSON.stringify([kind, stable(request)]);
}

export function invalidateTradeSearchHandoffs(): void {
  generation += 1;
  flights.clear();
}

export function startTradeSearchHandoff<T>(
  searchId: string, kind: 'model' | 'fair', request: object, load: () => Promise<T>,
): boolean {
  const identity = tradeSearchIdentity();
  if (!identity) return false;
  const now = Date.now();
  const key = requestKey(kind, request);
  for (const [id, flight] of flights) if (now - flight.at > MAX_HANDOFF_MS) flights.delete(id);
  const previous = flights.get(searchId);
  if (previous) return previous.identity === identity && previous.request === key;
  while (flights.size >= 16) flights.delete(flights.keys().next().value!);
  let promise: Promise<T>;
  try { promise = load(); } catch (error) { promise = Promise.reject(error); }
  // A screen can disappear before it consumes the handoff; no unhandled
  // rejection and no stale screen callback are attached to this request.
  void promise.catch(() => {});
  flights.set(searchId, { identity, request: key, promise, at: now });
  return true;
}

export function takeTradeSearchHandoff<T>(searchId: string | undefined | null, kind: 'model' | 'fair', request: object): Promise<T> | null {
  const flight = searchId ? flights.get(searchId) : undefined;
  if (!flight || !searchId) return null;
  flights.delete(searchId);
  if (flight.identity !== tradeSearchIdentity() || flight.request !== requestKey(kind, request)
      || Date.now() < flight.at || Date.now() - flight.at > MAX_HANDOFF_MS) return null;
  return flight.promise.then((result) => {
    if (flight.identity !== tradeSearchIdentity()) throw new TradeSearchContextChangedError();
    return result as T;
  });
}
