// The Home playoff card's `team_direction` block and its half sheet (flags
// `league.direction_card`, `league.direction_view_sheet`; spec
// docs/plans/league-projections/direction-pages/spec.md §4, §5.6, §7, §9;
// D-265, D-270).
//
// THE SERVER DECIDES. The band, the leading direction, whether each Improve
// page is offered and why not, and the projected pick all arrive in the
// block; nothing here compares a probability or computes a pick. This module
// only decides which block to honour (version, flag), how the figures and the
// sheet's rows are drawn from it, and where a tap goes.
// No React, no I/O; tests/check-direction-card.js and
// tests/check-direction-sheet.js transpile and execute it.
import type { DirectionKey, ProjectionView, TeamDirection } from '../api/leagueProjections';
import { DIRECTION_CARD_COPY as K } from './directionCardCopy';
import { DIRECTION_COPY as C } from './directionPagesCopy';

/** The block and the projected pick on the card (spec §8). */
export const DIRECTION_CARD_FLAG = 'league.direction_card';
/** Cell C: "View" opens the half sheet; the card has no button row. */
export const DIRECTION_SHEET_FLAG = 'league.direction_view_sheet';
export const CARD_EVENTS = { shown: 'direction_card_shown', tapped: 'home_tile_tapped' } as const;

const fill = (s: string, team: string) => s.replace('{team}', team);

/** The block the card honours, or null for today's row (H-12): the flag
 *  off, no block (older server), or a version or shape this build does not
 *  know. */
export function cardBlock(data: ProjectionView | undefined, cardOn: boolean): TeamDirection | null {
  const b = data?.team_direction;
  if (!cardOn || !b || typeof b !== 'object' || b.version !== 1) return null;
  if (!b.options || typeof b.options !== 'object') return null;
  return b;
}

export interface PickFigure {
  label: string;
  /** H-4: "owned by [team]" when another team holds the pick; else null. */
  owner: string | null;
}

/** H-3 to H-6: the server's label as sent. The server already hides it for a
 *  non-max-PF draft order (H-5) and with no saved run (H-6); the card also
 *  hides it when it has no playoff-chance figure to stand beside. A run that
 *  is not current keeps it, marked "last saved" with the percentage. */
export function pickFigure(block: TeamDirection | null, hasPercent: boolean): PickFigure | null {
  const p = block?.projected_pick;
  if (!block || !hasPercent || !p || typeof p.label !== 'string' || !p.label) return null;
  return {
    label: p.label,
    owner: p.owns_own_pick === false ? fill(K['PICK.owned'], p.owner_name || K['PICK.owner_unknown']) : null,
  };
}

/** S-2, S-10: "View" opens the sheet whenever the card holds a block and
 *  the sheet is on, including when neither direction is offered. */
export function viewOpensSheet(block: TeamDirection | null, sheetOn: boolean): boolean {
  return !!block && sheetOn;
}

/** `direction_card_shown` (spec §9). `shown` is the buttons drawn on the
 *  card: none in this build (the button row, cells A and B, is deferred,
 *  D-270). */
export function shownProps(block: TeamDirection, sheetOn: boolean, pickShown: boolean) {
  const band = block.band === 'low' || block.band === 'middle' || block.band === 'high' ? block.band : 'none';
  const primary = block.primary === 'playoffs' || block.primary === 'draft_pick' ? block.primary : 'none';
  return { band, primary, shown: 'none' as const, sheet: sheetOn, pick_shown: pickShown };
}

// ── The half sheet (S-3 to S-6) ─────────────────────────────────────────
export type SheetTile = 'standings' | 'improve_playoffs' | 'improve_pick';
export interface SheetRow {
  key: 'standings' | DirectionKey;
  tile: SheetTile;
  label: string;
  enabled: boolean;
  /** S-6: why a direction is not offered; null on an enabled row. */
  note: string | null;
}
/** S-3: the same order for every team. */
export const SHEET_ORDER = ['standings', 'playoffs', 'draft_pick'] as const;
const DIRECTION_TILE: Record<DirectionKey, SheetTile> = { playoffs: 'improve_playoffs', draft_pick: 'improve_pick' };

/** §7.3: the disabled row's line for a reason; an unknown reason reads
 *  "Not available right now." */
export function reasonLine(reason: string | null, block: TeamDirection): string {
  if (reason === 'pick_owned_elsewhere') {
    return fill(K['REASON.pick_owned_elsewhere'], block.projected_pick?.owner_name || K['REASON.owner_unknown']);
  }
  const key = `REASON.${reason}` as keyof typeof K;
  return reason && reason !== 'unknown' && reason !== 'owner_unknown' && key in K ? K[key] : K['REASON.unknown'];
}

/** S-3 to S-6, read from the block only (S-9). "View projected standings" is
 *  always enabled; an offered direction is enabled; one not offered is
 *  disabled with its line; one whose feature flag is off (`feature_off`) is
 *  not listed. */
export function sheetRows(block: TeamDirection): SheetRow[] {
  const rows: SheetRow[] = [{ key: 'standings', tile: 'standings', label: C['LINK.standings'], enabled: true, note: null }];
  for (const key of ['playoffs', 'draft_pick'] as const) {
    const option = block.options?.[key];
    if (!option || option.reason === 'feature_off') continue;
    const enabled = option.offered === true;
    rows.push({ key, tile: DIRECTION_TILE[key], label: C[`TITLE.${key}` as const], enabled,
      note: enabled ? null : reasonLine(option.reason, block) });
  }
  return rows;
}

// ── Taps (spec §9: home_tile_tapped with `via`) ─────────────────────────
export type DirectionTap =
  | { tile: 'playoff_options'; via: 'card' }
  | { tile: SheetTile; via: 'sheet' };

/** Where a tap goes. The tap that opens the sheet goes nowhere (the card
 *  opens its own sheet). A page is told where it was opened from, for
 *  `direction_page_opened.source`. */
export function tapDestination(tap: DirectionTap):
  | { route: 'Standings' }
  | { route: 'ImprovePlayoffChances' | 'ImproveDraftPick'; params: { source: 'card' | 'sheet' } }
  | null {
  if (tap.tile === 'playoff_options') return null;
  if (tap.tile === 'standings') return { route: 'Standings' };
  return { route: tap.tile === 'improve_playoffs' ? 'ImprovePlayoffChances' : 'ImproveDraftPick', params: { source: tap.via } };
}
