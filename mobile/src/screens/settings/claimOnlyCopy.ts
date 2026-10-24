// M11 claim-only delete (#354): the words, and who gets them.
//
// A session signed in with an ESPN or MFL league that hasn't been confirmed
// as the user's (an UNVERIFIED `entry:espn:…` / `entry:mfl:…` session) can't
// delete an account: the server's claim-only branch signs it out and removes
// what this device added, and nothing else. These are marketing-lead's G4
// strings (marketing-lead-copy.md §6 addendum 3; legal-lead R27), verbatim.
//
// HARD RULE: "Account deleted", or "deleted" as an outcome, never appears on
// this path — dialog, toast, Sign-in notice or accessibility label. Nothing
// here reuses the verified path's deletion copy. Pinned by
// tests/check-account-delete-paths.js.

import { SUPPORT_EMAIL } from '../../utils/supportContact';

export type ClaimPlatform = 'ESPN' | 'MFL';

/** ESPN / MFL for an entry user id, else null. */
export function claimPlatform(userId: string | null | undefined): ClaimPlatform | null {
  if (!userId) return null;
  if (userId.startsWith('entry:espn:')) return 'ESPN';
  if (userId.startsWith('entry:mfl:')) return 'MFL';
  return null;
}

export const G4_DELETE_TITLE = 'Sign out and remove this device?';
export const g4DeleteBody = (platform: ClaimPlatform): string =>
  `You're signed in with a ${platform} league that hasn't been confirmed as yours. ` +
  'This signs you out and removes what this device added. Records about the team stay, ' +
  `because they may belong to the team's owner. For anything else, email ${SUPPORT_EMAIL}.`;
export const G4_CONFIRM_PROMPT = 'Type DELETE to confirm.';
export const G4_CONFIRM_WORD = 'DELETE';
export const G4_CONFIRM_PRIMARY = 'Sign out and remove';
export const G4_CONFIRM_CANCEL = 'Cancel';
export const G4_EXPORT_UNAVAILABLE = "Download my data isn't available for this sign-in.";
export const G4_EXPORT_WHY =
  `A copy is available only for an account confirmed as yours. To ask about your data, email ${SUPPORT_EMAIL}.`;
export const G4_AFTER_NOTICE = "Signed out. This device's data is removed.";
/** Placeholder generic failure for this path (no G4 string exists yet; marketing-lead to confirm). */
export const CLAIM_DELETE_FAILED = 'Something went wrong. Try again.';
