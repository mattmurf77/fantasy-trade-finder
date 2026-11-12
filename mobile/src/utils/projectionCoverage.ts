// Playoff-forecast coverage copy (model v6). Pure, zero runtime imports, so
// tests/check-league-projections.js transpiles and executes it under node.
// web/js/league-projections.js carries the same incomplete sentence and lineup-row marker.

/** Why an incomplete forecast is incomplete: a starter who already played has no recorded score. */
export function incompleteSentence(missingSlots?: number | null): string {
  const slots = missingSlots === 1 ? '1 lineup slot' : `${missingSlots ?? 'Some'} lineup slots`;
  return `${slots} had a starter whose score is not recorded yet, so these odds are incomplete.`;
}

type LineupRow = {slot: string; unpriced_locked_player?: {player_id: string; name?: string}; player: null | {name?: string; player_id: string; points: string; hypothetical?: boolean}};

/** One lineup row; a slot listed in `projection_coverage.free_agent_fills` is marked as a free agent. */
export function lineupRowText(row: LineupRow, index: number, fills?: {slot_index: number}[]): string {
  const p = row.player;
  if (p) {
    const name = p.hypothetical ? 'Hypothetical bye replacement' : p.name || p.player_id;
    const freeAgent = (fills ?? []).some(f => f.slot_index === index) ? ' (free agent)' : '';
    return `${row.slot}: ${name}${freeAgent} · ${p.points}`;
  }
  if (row.unpriced_locked_player) return `${row.slot}: Locked starter ${row.unpriced_locked_player.name || row.unpriced_locked_player.player_id}: actual score unavailable`;
  return `${row.slot}: Empty slot`;
}
