// onboardingBus — tiny module-level mailbox for cross-screen onboarding
// handoffs (plan item 7). QuickSetTiersScreen (Rank stack) finishes a
// position in onboarding-return mode and posts the position here; the next
// TradesScreen focus consumes it and forces a deck regeneration + diff
// banner. Module state (not navigation params) because the two screens live
// in different tab stacks and the handoff must survive the tab switch.
// Session-scoped by design: an app restart drops a pending regen, which is
// fine — the fresh mount generates a fresh deck anyway.

let pendingQuicksetRegen: string | null = null;

/** Called by QuickSetTiersScreen when an onboarding-mode position walk
 *  completes. `position` = 'QB' | 'RB' | 'WR' | 'TE'. */
export function setPendingQuicksetRegen(position: string): void {
  pendingQuicksetRegen = position;
}

/** Consume-once read from TradesScreen focus. */
export function consumePendingQuicksetRegen(): string | null {
  const p = pendingQuicksetRegen;
  pendingQuicksetRegen = null;
  return p;
}
