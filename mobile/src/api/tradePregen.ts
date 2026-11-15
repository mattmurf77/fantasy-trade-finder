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

/** Flag `trade.fairness_window_v2` (docs/plans/fairness-window/spec.md): the
 *  server's configured "Balanced trades" threshold, the top-level
 *  `fairness_on_threshold` on GET /api/feature-flags (present only while the
 *  flag is on). api/flags.ts writes it on the success path only and never
 *  persists it; until then, and whenever it is absent or out of range, ON
 *  sends FAIRNESS_ON_THRESHOLD exactly as before. FAIRNESS_ON_THRESHOLD itself
 *  never moves: it is also the definition of "balanced" (NORMAL_LOW). */
export const SERVED_FAIRNESS_MIN = 0.55;
let _servedFairnessOn: number | null = null;
export function setServedFairnessOnThreshold(raw: unknown): void {
  _servedFairnessOn = typeof raw === 'number' && Number.isFinite(raw)
    && raw >= SERVED_FAIRNESS_MIN && raw <= FAIRNESS_ON_THRESHOLD ? raw : null;
}

/** The `fairness_threshold` to send for a resolved preference. OFF still
 *  sends a (low) value rather than dropping the field, so the server cache
 *  key stays stable. */
export function fairnessThresholdFor(fairnessOn: boolean): number {
  if (!fairnessOn) return FAIRNESS_OFF_THRESHOLD;
  return _servedFairnessOn ?? FAIRNESS_ON_THRESHOLD;
}
