// onboardingBus — tiny module-level mailbox for cross-screen onboarding
// handoffs (plan item 7). A rank surface finishes a board-changing walk and
// posts a pending forced-regen here; the next TradesScreen focus consumes it
// and forces a deck regeneration + diff banner (the s5.x reveal). Module
// state (not navigation params) because the posting screens live in the Rank
// tab stack and the handoff must survive the tab switch. Session-scoped by
// design: an app restart drops a pending regen, which is fine — the fresh
// mount generates a fresh deck anyway.
//
// ── Contract (guided-onboarding-v2 §5.3-A, N8 payoff wiring) ───────────────
// The mailbox originally carried ONLY the Quick-Set return (a position
// string). N8 makes the ranking method a user choice — import, trios, or
// Quick Set — so the payoff must fire method-agnostically. The generalized
// contract:
//
//   setPendingQuicksetRegen(position)      Quick Set walk completed.
//                                          Unchanged call site, unchanged
//                                          semantics; delegates to
//                                          setPendingGuidedRegen('quickset').
//   setPendingGuidedRegen(source, position?)
//                                          Any guided rank surface completed:
//                                          'quickset' | 'trios' | 'import'.
//   consumePendingQuicksetRegen()          Consume-once read (TradesScreen
//                                          focus). Return shape UNCHANGED:
//                                          `string | null`, truthy whenever a
//                                          regen is pending, for EVERY source.
//   consumeGuidedRegenSource()             Which source the last consume came
//                                          from. Read AFTER
//                                          consumePendingQuicksetRegen() in
//                                          the same handler; consume-once.
//
// **Marker semantics.** For `'quickset'` the returned marker is the position
// ('QB' | 'RB' | 'WR' | 'TE'), exactly as before. For sources that have no
// position ('trios', 'import') the marker is the SOURCE NAME — truthy, so
// every existing `if (!pos) return` guard keeps working, but it is not a
// position. Any caller that forwards the marker as an analytics `position`
// prop (e.g. `deck_regenerated`, whose allowlist is `{position, new_trades}`)
// must branch on `consumeGuidedRegenSource()` rather than assume a position.
// `isRegenPosition()` is the cheap test.

export type GuidedRegenSource = 'quickset' | 'trios' | 'import';

const POSITIONS = ['QB', 'RB', 'WR', 'TE'];

interface PendingRegen {
  source: GuidedRegenSource;
  /** Position for the Quick-Set walk; null for method-agnostic sources. */
  position: string | null;
}

let pendingRegen: PendingRegen | null = null;
/** Source of the most recent consume, awaiting its own consume-once read. */
let consumedSource: GuidedRegenSource | null = null;

/** Called by QuickSetTiersScreen when an onboarding-mode position walk
 *  completes. `position` = 'QB' | 'RB' | 'WR' | 'TE'. */
export function setPendingQuicksetRegen(position: string): void {
  setPendingGuidedRegen('quickset', position);
}

/** Post a forced-regen handoff from any guided rank surface (N8 payoff
 *  wiring). `position` is meaningful only for 'quickset'. */
export function setPendingGuidedRegen(
  source: GuidedRegenSource,
  position?: string | null,
): void {
  pendingRegen = { source, position: position ?? null };
}

/** Consume-once read from TradesScreen focus. Truthy for every source — see
 *  the marker semantics note above. */
export function consumePendingQuicksetRegen(): string | null {
  const p = pendingRegen;
  pendingRegen = null;
  consumedSource = p ? p.source : null;
  if (!p) return null;
  return p.position ?? p.source;
}

/** The source behind the marker just returned by
 *  `consumePendingQuicksetRegen()`. Consume-once; null when nothing was
 *  pending or when the source was already read. */
export function consumeGuidedRegenSource(): GuidedRegenSource | null {
  const s = consumedSource;
  consumedSource = null;
  return s;
}

/** True when a consumed marker is a real position (Quick-Set walk) rather
 *  than a method-agnostic source name. */
export function isRegenPosition(marker: string | null): boolean {
  return !!marker && POSITIONS.includes(marker);
}
