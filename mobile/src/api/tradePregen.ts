// Shared preference for session-init warm-up and Find a Trade.

// Fairness pref — single source shared with TradesScreen so the pregen job
// lands in the SAME server cache slot the screen's Find-a-Trade tap reads
// (`_trade_job_is_fresh` keys on fairness_threshold; a mismatched pregen
// would be wasted work).
export const FAIRNESS_PREF_KEY = 'ftf:trades:fairness_on';
export const FAIRNESS_ON_THRESHOLD = 0.75;
export const FAIRNESS_OFF_THRESHOLD = 0.5;

/**
 * Resolve the stored fairness preference to a boolean.
 *
 * DEFAULT IS OFF (operator decision 2026-08-17): an unset preference now
 * means the wide net (0.5), so testers see and judge more trades and the
 * decline-reason capture has verdicts to collect. Only an explicit `'on'`
 * turns balancing on — a user who deliberately flipped the toggle keeps
 * their choice, and nothing rewrites or clears anyone's stored value.
 * (This inverts the old `raw === 'off' ? OFF : ON` reading, where unset
 * meant on.)
 *
 * THE WHOLE POINT OF THIS HELPER is that both readers agree. The screen's
 * Find-a-Trade and the session-init pregen must resolve the SAME threshold
 * or the pregen lands in a different server cache slot and is wasted work
 * (`_trade_job_is_fresh` keys on fairness_threshold — see the note above).
 * Neither caller may re-derive this; call it.
 */
export function fairnessOnFromPref(raw: string | null | undefined): boolean {
  return raw === 'on';
}

/** The `fairness_threshold` to send for a resolved preference. OFF still
 *  sends a (low) value rather than dropping the field, so the server cache
 *  key stays stable. */
export function fairnessThresholdFor(fairnessOn: boolean): number {
  return fairnessOn ? FAIRNESS_ON_THRESHOLD : FAIRNESS_OFF_THRESHOLD;
}
