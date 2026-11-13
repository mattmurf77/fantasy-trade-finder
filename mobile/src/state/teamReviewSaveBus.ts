// teamReviewSaveBus — a one-slot mailbox from Team Review to Find a Trade.
//
// A Team Review save (outlook, Chase / Shop) changes what the trade engine
// reads, and the server already drops the cached deck on every save. But the
// deck Find a Trade is holding stays on screen when the user comes back, and
// only the Trade DNA sheet used to tell it so. Team Review posts here after a
// save that landed; TradesScreen consumes it on its next focus and does what
// a Trade DNA save does on sheet close: mark the deck stale and, when the
// same conditions hold, show the "Preferences changed — tap to refresh" strip.
// Nothing regenerates on its own, and nothing is posted when nothing saved.
//
// Module state, no imports: the two screens are siblings in the Trades stack,
// and a pending note must survive the pop. Session-scoped by design.

let pendingLeagueId: string | null = null;

/** Team Review: a preference save for this league landed. */
export function noteTeamReviewSave(leagueId: string): void {
  pendingLeagueId = leagueId;
}

/** Team Review: drop the note (Finish handed a scoped search to the deck,
 *  which builds a fresh deck under the saved preferences anyway). */
export function clearTeamReviewSave(): void {
  pendingLeagueId = null;
}

/** TradesScreen focus: consume-once. True only for a note about THIS league;
 *  a note about another league is discarded (a league switch resets the deck). */
export function consumeTeamReviewSave(leagueId: string | null | undefined): boolean {
  const hit = pendingLeagueId !== null && pendingLeagueId === leagueId;
  pendingLeagueId = null;
  return hit;
}

/** The one rule for when a preferences change shows the refresh strip, shared
 *  by the Trade DNA sheet's close and Team Review's return: only with a deck
 *  on screen to go stale and no search already in flight (that search runs
 *  under whatever preferences are current when it started). */
export function prefsChangedStripVisible(
  consolidateOn: boolean, deckLength: number, jobStatus: string | null | undefined,
): boolean {
  return consolidateOn && deckLength > 0 && jobStatus !== 'running';
}
