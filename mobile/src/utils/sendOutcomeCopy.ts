// What the app says when it can't confirm whether a trade send reached the
// platform (a timeout, a dropped connection, or the server's own
// `*_outcome_unknown`; see api/sendOutcome.ts). Kept in this ONE place on
// purpose: every string here is a PLACEHOLDER pending marketing. The
// single-send message matches the server's C10 copy (#513).

/** Alert title. Not "Couldn’t send": the send may have worked. */
export const SEND_OUTCOME_UNKNOWN_TITLE = 'Check before resending';

/** One ESPN or MFL send. `platform` is the display name: 'ESPN' | 'MFL'. */
export function sendOutcomeUnknownMessage(platform: string): string {
  return `Couldn’t confirm whether this trade reached ${platform}. Check ${platform} before sending it again.`;
}

/** A team-overhaul batch send; shown over the plan, which lists each offer's status. */
export function overhaulSendOutcomeUnknownMessage(platform: string): string {
  return `Couldn’t confirm whether these offers reached ${platform}. Each offer’s status is on your plan. Check ${platform} before sending any of them again.`;
}
