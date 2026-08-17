// #330 R-10 — generation-epoch guard for trade-job results.
//
// Nothing orders two in-flight generate mutations: an Offer handoff while a
// prior search is streaming resets the deck and dispatches the scoped run,
// but the OLD mutation's onSuccess can land AFTER the new dispatch and
// resurrect the pre-scope snapshot. TradesScreen therefore keeps a monotonic
// generation epoch (a ref, incremented by every resetDeckForNewTargets());
// every dispatch stamps the current epoch, and every result-application site
// (onSuccess, onError, the polling attach) routes through this helper, which
// drops the result entirely when the epochs differ — no setJob, no toast, no
// scopedEmpty, no deckFailure from a stale mutation.
//
// Pure and dependency-free BY CONTRACT: mobile has no jest harness, so
// tests/check-offer-prefill-330-unit.js transpiles this file and runs it
// under plain node (same idiom as check-session-rerank.js). A runtime import
// added here breaks that suite loudly.

/** The result to apply, or null when it was dispatched under a stale epoch. */
export function applyJobResult<T>(
  result: T,
  dispatchEpoch: number,
  currentEpoch: number,
): T | null {
  return dispatchEpoch === currentEpoch ? result : null;
}
