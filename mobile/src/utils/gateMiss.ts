// #339 item 12 (ux-lead F-5, head-eng approved): a no-card gate miss names
// its reason, makes no timing promise, and ends.
//
// The server names two (S0, contract v0.4 §3b):
//   - a check error with no cards: `status: "error"`,
//     `error: "roster_check_unavailable"` → the named error state + Retry;
//   - the I-1 withhold wait: an additive `wait_reason: "roster_check"` on a
//     building `/generate` or `/status` response while S0 withholds → the
//     named wait in place of "Looking for trades…", which ends after
//     FIRST_CARD_TIMEOUT_MS (R2b's timeout) in the named error state.
// Absent, both behave as before.
//
// Pure and import-free: tests/check-gate-miss.js runs it under plain node.

/** The job `error` S0 sends when its roster check can't run. */
export const ROSTER_CHECK_UNAVAILABLE = 'roster_check_unavailable';
/** The `wait_reason` S0 sends while it withholds cards for the check. */
export const WAIT_REASON_ROSTER_CHECK = 'roster_check';

/** Is this job error the roster check's (the named error state)? */
export function isRosterCheckError(error: string | null | undefined): boolean {
  return error === ROSTER_CHECK_UNAVAILABLE;
}

/** The named withhold wait: no cards on the device, the job still building,
 *  and the server saying it is checking rosters. */
export function isRosterCheckWait(
  job: { status: string; wait_reason?: string } | null | undefined,
  cardCount: number,
): boolean {
  return cardCount === 0 && job?.status === 'running' && job.wait_reason === WAIT_REASON_ROSTER_CHECK;
}
