// Improve pages — the pure decisions of the two dedicated pages, "Improve
// Playoff Chances" and "Improve Draft Pick" (flag `league.direction_pages`;
// spec docs/plans/league-projections/direction-pages/spec.md §3, D-265).
//
// The pages add no list, number or copy of their own for the rows (P-5): the
// body is the existing MaxPfMovesBody / PlayoffTargetsBody. This module only
// decides which branch a page shows (P-8, P-12), formats the two-figure
// summary above the list from the block's own `baseline` (P-6), and decides
// whether the link to the other page shows (P-10, by the spec §5.3 rule,
// which reads the server's `state` and never classifies a probability).
// No React, no I/O; tests/check-direction-pages.js transpiles and executes it.
import type { MaxPfMoves, PlayoffTargets, ProjectionView } from '../api/leagueProjections';
import { DIRECTION_COPY as C } from './directionPagesCopy';
import { playoffOddsText } from './playoffOdds';
import { sectionMounts as maxPfMounts } from './maxPfMoves';
import { sectionMounts as targetsMount } from './playoffTargets';

export type DirectionPage = 'playoffs' | 'draft_pick';

/** Gates the Standings link rows and every entry point to the pages (spec §8). */
export const DIRECTION_PAGES_FLAG = 'league.direction_pages';
/** P-1: root-stack routes, registered unconditionally. */
export const PAGE_ROUTE = { playoffs: 'ImprovePlayoffChances', draft_pick: 'ImproveDraftPick' } as const;
/** testID prefix per page. */
export const PAGE_TESTID = { playoffs: 'improve-playoffs', draft_pick: 'improve-pick' } as const;
/** The feature flag behind each page's list (P-12). */
export const PAGE_FLAG = { playoffs: 'league.playoff_targets', draft_pick: 'league.max_pf_moves' } as const;
export const pageTitle = (page: DirectionPage) => C[`TITLE.${page}` as const];
export const otherPage = (page: DirectionPage): DirectionPage => (page === 'playoffs' ? 'draft_pick' : 'playoffs');

// ── Which branch the page shows (P-8, P-12) ─────────────────────────────
export type PageView =
  | { kind: 'no_league' }
  | { kind: 'unavailable' }
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'draft_pick'; block: MaxPfMoves }
  | { kind: 'playoffs'; block: PlayoffTargets };

export interface PageInputs {
  page: DirectionPage;
  leagueId: string | null;
  userId: string | null;
  isSleeper: boolean;
  /** `league.projections`: without it there is no forecast read at all. */
  projectionsOn: boolean;
  /** PAGE_FLAG[page]. */
  featureOn: boolean;
  data: ProjectionView | undefined;
  isError: boolean;
}

/** No league → no_league. Not Sleeper, a flag off or no user → the
 *  unavailable card. Then the forecast read: nothing yet → loading or error.
 *  With a read, the block must pass the section's own mount rule (version,
 *  a known state; own card is always true on these pages, the block is the
 *  viewer's), otherwise the unavailable card. Every known state renders
 *  through the body, so no state leaves a blank page. */
export function pageView(i: PageInputs): PageView {
  if (!i.leagueId) return { kind: 'no_league' };
  if (!i.isSleeper || !i.projectionsOn || !i.featureOn || !i.userId) return { kind: 'unavailable' };
  if (!i.data) return { kind: i.isError ? 'error' : 'loading' };
  if (i.page === 'draft_pick') {
    const block = i.data.max_pf_moves;
    return block && maxPfMounts({ block, flagOn: true, isSleeper: true, ownCard: true })
      ? { kind: 'draft_pick', block } : { kind: 'unavailable' };
  }
  const block = i.data.playoff_targets;
  return block && targetsMount({ block, flagOn: true, isSleeper: true, ownCard: true })
    ? { kind: 'playoffs', block } : { kind: 'unavailable' };
}

// ── The two-figure summary (P-6) ────────────────────────────────────────
export interface Summary {
  /** "Playoff chance": whole percent under the D-262 rule (utils/playoffOdds). */
  playoff: string | null;
  /** "Projected pick": the D-257 label, as the server sent it. */
  pick: string | null;
}

/** The D-257 label for the viewer's own next-year 1st. Served today only as
 *  `max_pf_moves.baseline.label` (spec §2), so both pages read it there.
 *  Hidden when the league's stored draft order is not max PF (spec H-5 /
 *  §7.2: the forecast orders picks by max PF, so the figure would be wrong). */
export function projectedPick(data: ProjectionView | undefined): string | null {
  const m = data?.max_pf_moves;
  const label = m?.baseline?.label;
  if (!label) return null;
  const rule = m?.draft_order?.rule;
  if (rule === 'reverse_standings' || rule === 'lottery_or_other') return null;
  return label;
}

/** Read from the page's own block `baseline` (the same block as the list);
 *  null when neither figure is available. */
export function summary(page: DirectionPage, data: ProjectionView | undefined): Summary | null {
  const baseline = page === 'draft_pick' ? data?.max_pf_moves?.baseline : data?.playoff_targets?.baseline;
  const playoff = baseline ? playoffOddsText(baseline.playoff_probability, baseline, 1) : null;
  const pick = projectedPick(data);
  return playoff || pick ? { playoff, pick } : null;
}

// ── When a direction is offered (spec §5.3) ─────────────────────────────
export interface OfferFlags {
  maxPfOn: boolean;
  targetsOn: boolean;
}
/** With the server's `team_direction` block on the read (flag
 *  `league.direction_card`, D-270), its `options` are the one rule: the card,
 *  the sheet and the pages read the same answer. Without it (flag off, older
 *  server), the step-1 rule over the two blocks: draft pick = its flag,
 *  `state` ready and you own your own pick; playoffs = its flag and `state`
 *  ready. `ready` is the server's word that at least one row clears the
 *  feature's threshold; nothing is computed here. */
export function offered(page: DirectionPage, data: ProjectionView | undefined, flags: OfferFlags): boolean {
  const direction = data?.team_direction;
  if (direction && direction.version === 1 && direction.options && typeof direction.options === 'object') {
    return direction.options[page]?.offered === true;
  }
  if (page === 'draft_pick') {
    const b = data?.max_pf_moves;
    return flags.maxPfOn && !!b && maxPfMounts({ block: b, flagOn: true, isSleeper: true, ownCard: true })
      && b.state === 'ready' && b.pick_owner?.owns_own_pick === true;
  }
  const b = data?.playoff_targets;
  return flags.targetsOn && !!b && targetsMount({ block: b, flagOn: true, isSleeper: true, ownCard: true })
    && b.state === 'ready';
}

// ── The links under the list (P-10) ─────────────────────────────────────
export interface PageLinks {
  standings: { label: string; route: 'Standings' };
  other: { label: string; route: (typeof PAGE_ROUTE)[DirectionPage]; page: DirectionPage } | null;
}
/** "View projected standings" always; the other page only when it has
 *  something to offer, and only while `league.direction_pages` is on (the
 *  flag gates every entry point to the pages, spec §8). */
export function pageLinks(page: DirectionPage, data: ProjectionView | undefined,
  flags: OfferFlags & { directionPagesOn: boolean }): PageLinks {
  const other = otherPage(page);
  return {
    standings: { label: C['LINK.standings'], route: 'Standings' },
    other: flags.directionPagesOn && offered(other, data, flags)
      ? { label: C[`LINK.other.${other}` as const], route: PAGE_ROUTE[other], page: other }
      : null,
  };
}

// ── direction_page_opened (spec §9, D-270) ──────────────────────────────
export type DirectionSource = 'card' | 'sheet' | 'standings' | 'other_page' | 'deep_link';
export const PAGE_EVENTS = { opened: 'direction_page_opened' } as const;
const SOURCES: readonly DirectionSource[] = ['card', 'sheet', 'standings', 'other_page', 'deep_link'];
/** Where the page was opened from: the route's `source` param, set by each
 *  entry point. A deep link carries none. */
export function pageSource(params: unknown): DirectionSource {
  const source = (params as { source?: unknown } | undefined)?.source;
  return SOURCES.includes(source as DirectionSource) ? (source as DirectionSource) : 'deep_link';
}
/** The event's `state`: the feature block's server `state` when the page
 *  shows its list, else the branch it shows (unavailable / error /
 *  no_league). Null while loading: the event waits for the answer. */
export function openedState(view: PageView): string | null {
  if (view.kind === 'loading') return null;
  if (view.kind === 'draft_pick' || view.kind === 'playoffs') return view.block.state;
  return view.kind;
}
export function openedProps(page: DirectionPage, source: DirectionSource, state: string) {
  return { page, source, state };
}
