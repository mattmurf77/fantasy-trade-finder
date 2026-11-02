// The delete-account dialog's first alert (legal R28.21 5a–5d, APPROVED
// 2026-10-29; marketing-lead §6 addendum 10, item 5). ONE source for both
// Settings screens (AccountDataSection and the legacy SettingsScreen), so
// the two dialogs can't drift. The strings are VERBATIM; change one only
// with legal.
//
// The message is the body, a blank line, then the sub-note:
//   DELETE_ACCOUNT_BODY + '\n\n' + DELETE_ACCOUNT_SUB_NOTE
// It shows to EVERYONE: no flag, demo, verification or subscription
// condition (legal 5c). ZERO imports, on purpose: check-paywall-gate §9f
// loads and executes this module under plain node.

/** Names the Sleeper, ESPN and MFL sign-ins and connections that deletion
 *  removes (legal R28.21 5a, 5b). */
export const DELETE_ACCOUNT_BODY =
  'This permanently deletes your rankings, comparison history, trade activity, notifications, push tokens, and any stored Sleeper, ESPN or MFL sign-in or connection from our servers. Trade matches shared with leaguemates are anonymized on your side. This cannot be undone.';

/** Legal's `mz.delete.sub_note`, verbatim (privacy §6; R28.3 #8 MUST). */
export const DELETE_ACCOUNT_SUB_NOTE =
  "Deleting your account doesn't cancel an active subscription. To stop future charges, cancel it in your Apple ID settings first.";
