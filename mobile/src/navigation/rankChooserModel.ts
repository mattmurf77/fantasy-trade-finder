import type { IconName } from '../components/chalkline';
import type { RankMethodPref } from '../state/useSession';
import type { RankRoute } from './TabNav';

// #232 — rank-method chooser content model (approved mocks
// mockups/polish-lab-2026-08/rank-method-consolidation-v2.html + -v3.html).
//
// ONE source of truth consumed by BOTH chooser surfaces — the RankHome
// screen and the Rank-tab RankMenu sheet — so the two can never diverge
// (the operator-approved consolidation's core requirement). Three primary
// methods labeled by OUTCOME (Fastest / Most precise / Most control), with
// everything else behind a collapsed "More ways to rank" disclosure.
//
// Deliberate omissions:
// - Quick rank is NOT listed on either surface: per the approved mock it is
//   Quick set's follow-on pass ("Offered when you finish"), not a peer
//   method — its entry point is the Quick set finish prompt (and the route
//   stays registered for deep links).
// - Vocabulary: the Trios flow is "Head-to-heads" in chooser copy (mock's
//   unification); the ManualRanks flow is "Overall ranks".

export interface ChooserMethod {
  /** Saved routing preference; null = navigate only (Trends). */
  pref: RankMethodPref | null;
  route: RankRoute;
  icon: IconName;
  /** Outcome label: FASTEST / MOST PRECISE / MOST CONTROL (primary only). */
  role?: string;
  title: string;
  body: string;
  /** Follow-on subrow (Quick set's Quick-rank pass). */
  sub?: string;
  recommended?: boolean;
  /** Stable id segment shared by both surfaces' testIDs. */
  key: string;
}

/** The three primary cards/rows, in display order. */
export const PRIMARY_METHODS: ChooserMethod[] = [
  {
    pref: 'quickset',
    route: 'QuickSetTiers',
    icon: 'check',
    role: 'Fastest',
    title: 'Quick set',
    body:
      'Tap players into value tiers, one tier at a time. A usable board ' +
      'in a few minutes per position.',
    // Rendered behind a "Then, if you want:" lead-in by the surfaces.
    sub:
      'Quick rank — a follow-on pass that fine-tunes the order inside ' +
      'each tier. Offered when you finish.',
    recommended: true,
    key: 'quickset',
  },
  {
    pref: 'trio',
    route: 'Trios',
    icon: 'rank',
    role: 'Most precise',
    title: 'Head-to-heads',
    body:
      'Put three players in order at a time — a few seconds each, and ' +
      'your board sharpens with every answer.',
    key: 'trio',
  },
  {
    pref: 'tiers',
    route: 'Tiers',
    icon: 'crown',
    role: 'Most control',
    title: 'Tiers board',
    body:
      'Your whole board as drag-and-drop value tiers — every placement ' +
      'is your call, from 4+ 1sts down to FA.',
    key: 'tiers',
  },
];

/** "More ways to rank" disclosure rows (collapsed by default). */
export const MORE_METHODS: ChooserMethod[] = [
  {
    pref: 'anchor',
    route: 'Anchors',
    icon: 'swap',
    title: 'Pick Anchors',
    body: 'Price players in draft picks, one at a time',
    key: 'anchor',
  },
  {
    pref: 'manual',
    route: 'ManualRanks',
    icon: 'trends',
    title: 'Overall ranks',
    body: 'Order every player 1-to-N yourself — drag rows or tap a rank number',
    key: 'manual',
  },
  {
    pref: null,
    route: 'Trends',
    icon: 'trends',
    title: 'Trends',
    body: 'Your biggest movers vs consensus',
    key: 'trends',
  },
];
