// Client-only selection contract. No React, state or runtime imports: tests
// execute this helper to distinguish an empty canvas from no canvas request.
export interface SearchSelection {
  giveIds: string[];
  receiveIds: string[];
}

export interface CanvasScopeDraft {
  opponentId?: string;
  give: string[];
  receive: string[];
  seeded?: boolean;
}

// A searched snapshot may outlive the parent's old scope. Only a later
// external scope CHANGE supersedes it; the matching in-place search sync
// must not empty its own canvas. Switching partners follows the calculator's
// existing rule: retain SEND, clear the incompatible GET side.
export function reconcileCanvasScope(
  prefill: CanvasScopeDraft | null,
  previousOpponentId: string | null,
  opponentId: string | null,
  latestGive?: string[],
): CanvasScopeDraft | null {
  if (previousOpponentId === opponentId
      || (prefill && prefill.opponentId === (opponentId ?? undefined))) return prefill;
  return {
    opponentId: opponentId ?? undefined,
    give: [...(latestGive ?? prefill?.give ?? [])],
    receive: [],
  };
}

export function modelSelectionParams(
  canvas: SearchSelection | null,
  pins: SearchSelection,
  targetingEnabled: boolean,
  packageMode: boolean,
) {
  const selection = canvas ?? (targetingEnabled ? pins : { giveIds: [], receiveIds: [] });
  return {
    pinned_give_players: selection.giveIds.length ? [...selection.giveIds] : undefined,
    pinned_receive_players: selection.receiveIds.length ? [...selection.receiveIds] : undefined,
    pinned_give_mode: selection.giveIds.length >= 2 && (canvas !== null || packageMode)
      ? 'all' as const
      : undefined,
  };
}
