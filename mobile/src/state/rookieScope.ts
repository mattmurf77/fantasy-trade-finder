import { create } from 'zustand';
import { useFeatureFlags } from './useFeatureFlags';

// ── Rookie scope — THE shared model (rookie-draft M2, plan §M2 + lld §4.2)
//
// ONE control, ONE state, ONE copy set, consumed by every ranking surface
// (Pick Anchors · Tiers board · Quick Set · Quick Rank · Overall ranks ·
// Trios) plus the consolidated rookie view. Modelled on
// `navigation/rankChooserModel.ts`: the surfaces render shared content so
// they can never diverge — the same failure mode the rank-method chooser
// was consolidated to prevent.
//
// SESSION-ONLY by design (#133 scope-pill precedent). The store is plain
// module state: it survives screen remounts and tab switches inside one
// launch and resets on the next app start. It is deliberately NOT persisted
// and NOT a preference — a board filter should never outlive the session
// that asked for it, and a stale "rookies only" board on a cold start would
// read as data loss.
//
// Scope is a VIEW FILTER over the ONE board, not a second Elo space: the
// server applies it post-Elo (`?scope=rookie`), so a rookie's value is the
// same number whether you look at the whole board or just the rookies (D2).
// Everything the client does under scope therefore composes with the
// unscoped board — never a separate ranking.

export type RankScope = 'all' | 'rookie';

/** The flag that delivers the whole feature. Server-delivered; when it is
 *  off the control never renders, the query parameter is never sent, and
 *  the consolidated view has no entry point. */
export const ROOKIE_SCOPE_FLAG = 'ranks.rookie_subset';

interface ScopeOption {
  scope: RankScope;
  label: string;
  /** VoiceOver label — the segment's two-word label is too terse alone. */
  a11yLabel: string;
  /** Stable id segment shared by every surface's testID. */
  key: string;
}

/** The segmented control's content, in display order. */
export const SCOPE_OPTIONS: ScopeOption[] = [
  { scope: 'all',    label: 'All players', a11yLabel: 'All players',            key: 'all' },
  { scope: 'rookie', label: 'Rookies',     a11yLabel: 'Rookies only',            key: 'rookie' },
];

/** Entry-point copy for the consolidated cross-position rookie view
 *  (operator decision O1-expanded). Shared so the link reads identically
 *  from every rank page and from the chooser. */
export const CONSOLIDATED_VIEW = {
  route: 'RookieRanks' as const,
  title: 'All rookies, one list',
  body: 'Every rookie across QB/RB/WR/TE ranked together — same values as your position boards.',
  linkLabel: 'See all rookies in one list',
};

/** Copy for the server's typed empty response (`{empty:true, reason}`).
 *  A thin or unloaded rookie class is a real, expected state of this
 *  feature — not an error — so every surface renders the same honest line
 *  instead of a failure state. */
export function scopeEmptyCopy(reason: string | undefined, position?: string | null): string {
  const where = position && position !== 'ALL' ? ` ${position}` : '';
  switch (reason) {
    case 'class_not_loaded':
      return `This year's rookie class isn't loaded yet. Rookies appear once the NFL draft class lands (late April).`;
    case 'stale_player_cache':
      return 'Rookie data is out of date on this server. Switch back to all players for now.';
    case 'thin_pool':
    default:
      return `Not enough valued${where} rookies to rank yet. Switch back to all players, or try another position.`;
  }
}

interface RookieScopeState {
  scope: RankScope;
  setScope: (s: RankScope) => void;
}

const useRookieScopeStore = create<RookieScopeState>((set) => ({
  scope: 'all',
  setScope: (scope) => set({ scope }),
}));

/** Non-hook read of the live scope — for query functions and imperative
 *  paths. Returns `'rookie'` ONLY when the flag is on, so a stale scope can
 *  never leak a `?scope=` parameter onto an unflagged server. */
export function rookieScopeParam(): 'rookie' | undefined {
  if (!useFeatureFlags.getState().flags[ROOKIE_SCOPE_FLAG]) return undefined;
  return useRookieScopeStore.getState().scope === 'rookie' ? 'rookie' : undefined;
}

/** THE hook every ranking surface uses.
 *  - `enabled`: the flag is on (render the control / honour the scope)
 *  - `scope`:   'all' unless the flag is on AND the user chose rookies
 *  - `param`:   what to hand the API layer + the react-query key
 */
export function useRookieScope(): {
  enabled: boolean;
  scope: RankScope;
  isRookie: boolean;
  param: 'rookie' | undefined;
  setScope: (s: RankScope) => void;
} {
  const enabled = useFeatureFlags((s) => !!s.flags[ROOKIE_SCOPE_FLAG]);
  const stored = useRookieScopeStore((s) => s.scope);
  const setScope = useRookieScopeStore((s) => s.setScope);
  const scope: RankScope = enabled ? stored : 'all';
  return {
    enabled,
    scope,
    isRookie: scope === 'rookie',
    param: scope === 'rookie' ? 'rookie' : undefined,
    setScope,
  };
}
