import { create } from 'zustand';

// D1 free-agent moves (scope §C state 9): claims submitted from the claim
// sheet in this app session, keyed by league + player, so the host's list
// row reads "Claim pending" until the app restarts. In memory only, never
// persisted: it is display, and the server's own hold on that player (§B6)
// decides what the next tap may do. Written only from a `submit`-mode
// result, so it stays empty, and the lists unchanged, when the server sends
// no capability.

const keyOf = (leagueId: string, playerId: string) => `${leagueId}:${playerId}`;

interface ClaimsPendingState {
  keys: ReadonlySet<string>;
}

export const useClaimsPending = create<ClaimsPendingState>(() => ({ keys: new Set<string>() }));

/** A claim for this player in this league came back `pending`. */
export function markClaimPending(leagueId: string, playerId: string): void {
  const keys = new Set(useClaimsPending.getState().keys);
  keys.add(keyOf(leagueId, playerId));
  useClaimsPending.setState({ keys });
}

export function isClaimPending(
  keys: ReadonlySet<string>,
  leagueId: string | null | undefined,
  playerId: string,
): boolean {
  return !!leagueId && keys.has(keyOf(leagueId, playerId));
}
