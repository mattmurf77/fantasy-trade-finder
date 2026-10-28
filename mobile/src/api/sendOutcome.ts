// ESPN / MFL trade sends: how long the app waits for the server, and how a
// send whose outcome is unknown is recognised. The words the user then sees
// live in utils/sendOutcomeCopy.ts.
//
// Why: the default 15 s request timeout (api/client.ts) is shorter than what
// the server can legitimately spend on one ESPN/MFL send, so the app used to
// give up while the provider write was still running, show "Something went
// wrong … Please try again", and invite a duplicate send. Server side, C10
// (#513) answers a post-send provider timeout with 502 `espn_outcome_unknown`
// / `mfl_outcome_unknown`. This is the client half: wait out the server's
// worst case, and when the app still can't tell whether the trade went out,
// say so. Never "try again", and never an automatic retry (api/client.ts
// retries GETs only). Pinned by tests/check-send-timeout.js.

import { ApiError } from './client';

// ── Server worst case for ONE ESPN or MFL propose (origin/main bef9f5db) ──
// Every provider call a propose core can make, one after another, each
// counted once at its socket timeout:
//
// MFL, `_mfl_propose_core` (backend/server.py:37659):
//   15  crosswalk refresh: `get_crosswalk` → `fetch_crosswalk(timeout=15)`,
//       backend/espn_service.py:774 → :755. Only when the 24 h cache is
//       stale; reached through `_sleeper_to_mfl_map` (server.py:37756).
//   15  host resolution: `resolve_host(timeout=15)`, backend/mfl_service.py:129.
//       Only when the league row has no platform_host (server.py:37771).
//   15  I-2 rosters read: `fetch_rosters(timeout=15)`,
//       backend/mfl_service.py:441 (server.py:37813).
//   15  I-2 picks read: `fetch_future_draft_picks(timeout=15)`,
//       backend/mfl_service.py:401 (server.py:37843).
//    1  write spacing: `_REQUEST_SPACING_SECONDS = 1.0`, backend/mfl_write.py:63.
//   15  the write: `_HTTP_TIMEOUT = 15`, backend/mfl_write.py:58 (server.py:37892).
//   = 76 s
//
// ESPN, `_espn_propose_core` (backend/server.py:38259):
//   15  crosswalk refresh, as above (`_sleeper_to_espn_map`, server.py:38356).
//   15  pre-flight league read: `fetch_league(timeout=15)`,
//       backend/espn_service.py:139 (server.py:38381).
//   15  the write: `_HTTP_TIMEOUT = 15`, backend/espn_write.py:80 (server.py:38474).
//   = 45 s
//
// One constant covers both, so it is MFL's 76 s. Sleeper's core, which only
// the overhaul send reaches through this file, is at most rosters 15 +
// traded_picks 15 + league meta 10 + drafts 15 + write 15 = 70 s.
// urllib's timeout applies per blocking socket operation, not per request, so
// a provider that stalls at more than one stage can run longer. The app then
// shows the "couldn't confirm" message, which is the safe outcome.
export const SERVER_SEND_WORST_CASE_S = 15 + 15 + 15 + 15 + 1 + 15; // = 76

// Margin: one default request timeout (DEFAULT_TIMEOUT_MS in api/client.ts,
// 15 s) for the mobile round trip and the server's database work around the
// provider calls.
export const SEND_TIMEOUT_MARGIN_S = 15;

/** Request timeout for POST /api/trades/propose-espn and /propose-mfl: (76 + 15) s = 91 s. */
export const PLATFORM_SEND_TIMEOUT_MS = (SERVER_SEND_WORST_CASE_S + SEND_TIMEOUT_MARGIN_S) * 1000;

/** Request timeout for POST /api/overhauls/{id}/send. The server sends the
 *  batch's offers one after another inside that ONE request
 *  (`overhaul_send_route`, backend/overhaul_api.py), so each offer gets the
 *  single-send worst case: (offers × 76 + 15) s. */
export function overhaulSendTimeoutMs(offerCount: number): number {
  const offers = Number.isFinite(offerCount) && offerCount > 1 ? Math.ceil(offerCount) : 1;
  return (offers * SERVER_SEND_WORST_CASE_S + SEND_TIMEOUT_MARGIN_S) * 1000;
}

/** Error codes that mean the send may have landed: the server's own C10
 *  answers (#513), and the global handler's 500 `internal_error`
 *  (backend/server.py:2422), since an unhandled exception can be raised after
 *  the provider already took the write. */
export const SEND_OUTCOME_UNKNOWN_CODES: readonly string[] = [
  'espn_outcome_unknown',
  'mfl_outcome_unknown',
  'internal_error',
];

/** True when a failed ESPN/MFL/overhaul send may still have reached the
 *  platform, so the app must say "couldn't confirm, check before resending":
 *   - our request timeout fired (`isTimeout`): the server may still be sending;
 *   - no HTTP answer at all (status 0, or a non-ApiError such as fetch's
 *     network TypeError): the request may have gone out before the drop;
 *   - one of SEND_OUTCOME_UNKNOWN_CODES;
 *   - a 5xx with no error code (a gateway or crash page).
 *  Every other structured error (`*_write_failed`, `*_unavailable`,
 *  `*_auth_expired`, `asset_not_owned`, …) keeps its own handling. */
export function isSendOutcomeUnknown(err: unknown): boolean {
  if (!(err instanceof ApiError)) return true;
  if (err.isTimeout || err.status === 0) return true;
  const body = err.body;
  const code = body && typeof body === 'object' ? (body as { error?: unknown }).error : undefined;
  if (typeof code === 'string' && code) return SEND_OUTCOME_UNKNOWN_CODES.includes(code);
  return err.status >= 500;
}
