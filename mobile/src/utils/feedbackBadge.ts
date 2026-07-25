// FeedbackFAB badge math (#184) — pure, no runtime imports (type-only
// imports erase at compile time) so scripts/check-feedback-badge.js can
// transpile and exercise this exact module under plain node.

import type { FeedbackStatus } from '../api/feedback';

// Resolved statuses excluded from the FAB's count badge (#184). Superset of
// CLOSED_FEEDBACK_STATUSES (api/feedback.ts — keep in sync): 'fixed' notes
// stay visible in the inbox LIST (the "Fixed — in next update" chip) but no
// longer count toward the badge — the badge means "notes still awaiting
// action", not "notes in the inbox".
export const RESOLVED_FEEDBACK_STATUSES: readonly FeedbackStatus[] = [
  'fixed',
  'shipped',
  'declined',
];

// Minimal structural view of state/useFeedback.ts's FeedbackItem — only the
// fields the badge math reads (keeps this module free of state imports).
export interface FeedbackBadgeInput {
  status?: FeedbackStatus;
  closed?: boolean;
}

/** How many notes are still awaiting action: not hidden from the inbox
 *  (`closed` — shipped/declined or no longer served to this account) and
 *  not in a resolved status (fixed/shipped/declined). Notes with no status
 *  yet (unsynced, or statuses never fetched) count — from the user's POV
 *  they're open. */
export function openFeedbackCount(items: readonly FeedbackBadgeInput[]): number {
  return items.filter(
    (i) =>
      !i.closed &&
      (!i.status || !(RESOLVED_FEEDBACK_STATUSES as readonly string[]).includes(i.status)),
  ).length;
}
