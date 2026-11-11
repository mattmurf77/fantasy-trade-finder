// Offer-learnings WS2b — consent to import the user's own Sleeper trade offers.
//
// Wire: GET / POST / DELETE /api/sleeper/offer-import (docs/api-reference.md).
// The server owns every word the switch shows (`label`, `terms_line`, the
// withdrawal `notice`) and the terms version; the app echoes the version it
// showed when it grants, so a changed wording is never consented to blind.
// GET is a background read: a 404 (flag off) or 403 (unverified) reads as
// "nothing to show", with no api_request_failed event and no VerifySheet.

import { apiRequest, ApiError } from './client';

export const OFFER_IMPORT_PATH = '/api/sleeper/offer-import';
const QUIET = [403, 404] as const;

export interface OfferImportState {
  consented: boolean;
  linked: boolean;
  terms_version: string;
  label: string;
  terms_line: string;
}

export interface OfferImportWithdrawal {
  consented: false;
  deleted: number;
  notice: string;
}

/** The switch's state, or null when the server has nothing to show. */
export async function readOfferImport(): Promise<OfferImportState | null> {
  try {
    return await apiRequest<OfferImportState>(OFFER_IMPORT_PATH, {
      quietStatuses: QUIET,
      background: true,
    });
  } catch (err) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 403)) return null;
    throw err;
  }
}

/** Switch on: a grant at the terms version the user was shown. */
export function grantOfferImport(termsVersion: string): Promise<OfferImportState> {
  return apiRequest<OfferImportState>(OFFER_IMPORT_PATH, {
    method: 'POST',
    body: { terms_version: termsVersion },
  });
}

/** Switch off: withdraws and deletes every imported offer. */
export function withdrawOfferImport(): Promise<OfferImportWithdrawal> {
  return apiRequest<OfferImportWithdrawal>(OFFER_IMPORT_PATH, { method: 'DELETE' });
}
