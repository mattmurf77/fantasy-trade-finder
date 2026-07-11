// Account-auth P2.5 — shared error-copy helper for read-gated screens.
//
// The backend 403s board-content reads (`verification_required`) from an
// unverified session once a verified controller exists for its user_id.
// The central handling lives in api/client.ts (listener) + state/useSession
// (flips `verification` so VerifyAccountBanner shows); screens only need
// their load-error copy to say WHY the data is missing instead of a generic
// "could not load".

import { ApiError } from '../api/client';

export const VERIFY_READS_COPY = 'Verify your account to view your data.';

/** Returns the verify prompt when `err` is the read gate's 403, else the
 *  screen's normal load-error copy. */
export function readErrorCopy(err: unknown, fallback: string): string {
  return err instanceof ApiError && err.isVerificationRequired
    ? VERIFY_READS_COPY
    : fallback;
}
