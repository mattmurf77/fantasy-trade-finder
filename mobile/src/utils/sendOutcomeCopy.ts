// What the ESPN/MFL send buttons say when a send is not confirmed. Kept in
// this ONE place on purpose. Final copy: marketing-lead, addendum 10 items
// 8a/8b/8e/8f/8i (docs/plans/org-bringup/leads/marketing-lead-copy.md,
// approved 2026-10-28), with straight apostrophes as written. Never in this
// copy: "failed", "error", raw provider text, or "nothing was sent" where the
// outcome is unknown (pinned by tests/check-send-timeout.js).

/** Title when the send may have reached the platform (8i). Not "Couldn't send". */
export const SEND_OUTCOME_UNKNOWN_TITLE = 'Check before resending';

/** Body for one ESPN or MFL send with no server answer: our timeout or a
 *  dropped connection (8e / 8f). `platform` is 'ESPN' | 'MFL'. */
export function sendOutcomeUnknownMessage(platform: string): string {
  return `Couldn't confirm whether this trade reached ${platform}. Check your league's pending trades on ${platform} before you send it again.`;
}

/** Outcome-unknown body: the server's own `detail` for its
 *  `espn_outcome_unknown` / `mfl_outcome_unknown` (8i), else the client line
 *  above. Any other code's text (e.g. `internal_error`'s message) is never shown. */
export function sendOutcomeUnknownBody(platform: string, code?: string, detail?: string): string {
  const own = code === `${platform.toLowerCase()}_outcome_unknown`;
  return own && typeof detail === 'string' && detail.trim() ? detail : sendOutcomeUnknownMessage(platform);
}

/** Title when the platform rejected the send (`*_write_failed`, both kinds; 8i). */
export const SEND_NOT_SENT_TITLE = 'Not sent';

/** `*_write_failed` body when the server sent no `detail`: the server's own
 *  rejection line (8a / 8b). With a `detail`, the body is `detail` alone. */
export function sendNotSentFallback(platform: string): string {
  return `${platform} didn't accept this trade, so nothing was sent. You can still propose it on ${platform}.`;
}

/** A team-overhaul batch send; shown over the plan, which lists each offer's
 *  status. PENDING MARKETING: not in addendum 10; routed by platforms-eng. */
export function overhaulSendOutcomeUnknownMessage(platform: string): string {
  return `Couldn’t confirm whether these offers reached ${platform}. Each offer’s status is on your plan. Check ${platform} before sending any of them again.`;
}
