// PRD 01-05 (flag `ux.retap_active_tab`): re-tap-to-top contract.
//
// TabNav's focused-tab tabPress handlers call requestScrollToTop(tab) when
// the tab is already at its stack root; each tab's ROOT screen registers a
// handler that scrolls its primary list to top. Kept as a tiny module
// registry (no React, no events lib) so screens owned by other agents can
// wire in without touching navigation files.
//
// Screen-side usage (W2B/W2C — TradesScreen, MatchesScreen, LeagueScreen):
//   useEffect(
//     () => registerScrollToTop('Trades', () =>
//       listRef.current?.scrollToOffset({ offset: 0, animated: true })),
//     [],
//   );
// A tab with no registered handler is a silent no-op (never throws).

export type TabName = 'Rank' | 'Trades' | 'Matches' | 'League';

const handlers = new Map<TabName, () => void>();

/** Register the focused-re-tap scroll handler for a tab's root screen.
 *  Returns an unsubscribe fn (safe to return directly from useEffect). */
export function registerScrollToTop(tab: TabName, fn: () => void): () => void {
  handlers.set(tab, fn);
  return () => {
    if (handlers.get(tab) === fn) handlers.delete(tab);
  };
}

/** Fire the tab's scroll-to-top handler, if any. Never throws. */
export function requestScrollToTop(tab: TabName): void {
  try {
    handlers.get(tab)?.();
  } catch {
    /* a broken screen handler must not crash the tab press */
  }
}
