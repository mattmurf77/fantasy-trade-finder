// Founders' review — the pure decisions of the label review page
// (docs/plans/founder-review/design.md §2.2, §7). ZERO runtime imports, so
// tests/check-founder-review.js transpiles and executes this file under node.
//
// Vocabulary and band order are a cross-client invariant: they equal the
// server's backend/founder_review.py LABELS / BANDS
// (docs/cross-client-invariants.md § Founders' review labels), and the guard
// compares the two files.

export type FounderLabel = 'cornerstone' | 'win_now' | 'rebuild' | 'depth';
export type Band = FounderLabel | 'none';
export type QbScope = 'superflex' | 'single_qb';
export type ReviewPosition = 'QB' | 'RB' | 'WR' | 'TE';

export const LABELS: readonly FounderLabel[] = ['cornerstone', 'win_now', 'rebuild', 'depth'];
export const BANDS: readonly Band[] = ['cornerstone', 'win_now', 'rebuild', 'depth', 'none'];
export const POSITIONS: readonly ReviewPosition[] = ['QB', 'RB', 'WR', 'TE'];

export const BAND_LABEL: Record<Band, string> = {
  cornerstone: 'Cornerstone',
  win_now: 'Win-now piece',
  rebuild: 'Rebuild piece',
  depth: 'Depth',
  none: 'No label',
};

/** One row of GET /api/founder/labels `players`. */
export interface FounderRow {
  id: string;
  name: string;
  position: ReviewPosition;
  team: string | null;
  age: number | null;
  ppg: number | null;
  line: number | null;
  value: number | null;
  future: number | null;
  startable: boolean | null;
  label: FounderLabel | null;          // what the engine uses here (after any override)
  engine_label: FounderLabel | null;   // the rule's own label here
  override: FounderLabel | null;       // the stored value in this league's scope
  why_unlabelled: 'borderline' | 'unprojected' | null;
  movable_to: FounderLabel[];
}

/** Local edits: player id -> the band the founder placed him in. */
export type Draft = Readonly<Record<string, FounderLabel>>;

export function bandOf(row: FounderRow, draft: Draft): Band {
  return draft[row.id] ?? row.label ?? 'none';
}

/** The labels a "Move to" chip may offer for this selection: legal for EVERY
 *  selected player (a starter: Cornerstone / Win-now; a bench player:
 *  Rebuild / Depth; borderline and unprojected: nothing). */
export function targetsFor(rows: readonly FounderRow[], selected: readonly string[]): FounderLabel[] {
  const picked = rows.filter((r) => selected.includes(r.id));
  if (picked.length === 0) return [];
  return LABELS.filter((l) => picked.every((r) => r.movable_to.includes(l)));
}

/** Move the selected players into `label`; a move that is not legal for a
 *  player is ignored for him. A move back to the server's label drops the edit. */
export function applyMove(draft: Draft, rows: readonly FounderRow[], ids: readonly string[], label: FounderLabel): Draft {
  const next: Record<string, FounderLabel> = { ...draft };
  for (const row of rows) {
    if (!ids.includes(row.id) || !row.movable_to.includes(label)) continue;
    if (row.label === label) delete next[row.id];
    else next[row.id] = label;
  }
  return next;
}

/** Ids whose band differs from what the server says now. */
export function changedIds(rows: readonly FounderRow[], draft: Draft): string[] {
  return rows.filter((r) => draft[r.id] !== undefined && draft[r.id] !== r.label).map((r) => r.id);
}

/** The write body: only changed players. Back to the engine's own label here
 *  clears the override (the row is deleted); anything else sets it. */
export function savePayload(
  leagueId: string, rows: readonly FounderRow[], draft: Draft,
): { league_id: string; set: Record<string, FounderLabel>; clear: string[] } {
  const set: Record<string, FounderLabel> = {};
  const clear: string[] = [];
  for (const id of changedIds(rows, draft)) {
    const row = rows.find((r) => r.id === id)!;
    const label = draft[id];
    if (label === row.engine_label) clear.push(id);
    else set[id] = label;
  }
  return { league_id: leagueId, set, clear };
}

/** Reset to engine: every movable row at `position` back to the engine's
 *  label (a local draft; Save commits it). */
export function resetToEngine(draft: Draft, rows: readonly FounderRow[], position: ReviewPosition): Draft {
  const next: Record<string, FounderLabel> = { ...draft };
  for (const row of rows) {
    if (row.position !== position || row.movable_to.length === 0 || row.engine_label == null) continue;
    if (row.label === row.engine_label) delete next[row.id];
    else next[row.id] = row.engine_label;
  }
  return next;
}

export function bandCounts(rows: readonly FounderRow[], draft: Draft): Record<Band, number> {
  const out = { cornerstone: 0, win_now: 0, rebuild: 0, depth: 0, none: 0 } as Record<Band, number>;
  for (const row of rows) out[bandOf(row, draft)] += 1;
  return out;
}

/** The "engine: …" note for a row whose band differs from the engine's label. */
export function engineNote(row: FounderRow, draft: Draft): string | null {
  const band = bandOf(row, draft);
  if (row.engine_label == null || band === row.engine_label) return null;
  return `engine: ${BAND_LABEL[row.engine_label]}`;
}

export function scopeHeading(scope: QbScope | null): string {
  return scope === 'superflex' ? 'QB labels · Superflex leagues' : 'QB labels · 1-QB leagues';
}

export function otherScopeLine(scope: QbScope | null): string {
  return scope === 'superflex'
    ? 'These QB labels apply to every superflex league. To edit 1-QB labels, select a 1-QB league.'
    : 'These QB labels apply to every 1-QB league. To edit superflex labels, select a superflex league.';
}

/** Why the page has no rows: the server's `evidence.reason` in words. */
export function emptyReason(reason: string | null | undefined): string {
  switch (reason) {
    case 'platform_unsupported': return 'Only Sleeper leagues have season forecasts, so there are no labels here.';
    case 'no_forecast': return 'No saved season forecast for this league yet, so there are no labels.';
    case 'old_model': return 'The saved forecast is from an older model. Refresh the forecast to see labels.';
    case 'stale': return 'The saved forecast is out of date. Refresh it to see labels.';
    case 'league_changed': return 'The league changed since the forecast was saved. Refresh it to see labels.';
    case 'no_upcoming_week': return 'No games left this season, so there are no labels.';
    case 'viewer_unprojected_asset': return 'A valuable player on your roster has no projection, so labels are off.';
    default: return 'Labels could not be read for this league.';
  }
}

export function unlabelledWhy(row: FounderRow): string {
  return row.why_unlabelled === 'unprojected' ? 'no projection' : 'near the starter line';
}
