// Playoff-forecast coverage copy (model v6). Pure, zero runtime imports, so
// tests/check-league-projections.js transpiles and executes it under node.
// web/js/league-projections.js carries the same sentences.

/** Why an incomplete forecast is incomplete: a starter who already played has no recorded score. */
export function incompleteSentence(missingSlots?: number | null): string {
  const slots = missingSlots === 1 ? '1 lineup slot' : `${missingSlots ?? 'Some'} lineup slots`;
  return `${slots} had a starter whose score is not recorded yet, so these odds are incomplete.`;
}

/** One line saying how many open slots took a free agent or count as 0; null when neither (or an older run). */
export function freeAgentFillSentence(coverage?: {fa_filled_slots?: number; zero_filled_slots?: number} | null): string | null {
  const filled = coverage?.fa_filled_slots ?? 0;
  const zero = coverage?.zero_filled_slots ?? 0;
  if (filled > 0 && zero > 0) {
    return `${filled} open lineup ${filled === 1 ? 'slot uses' : 'slots use'} the best available free agent; ${zero} ${zero === 1 ? 'has none and counts' : 'have none and count'} as 0.`;
  }
  if (filled > 0) return `${filled} open lineup ${filled === 1 ? 'slot uses' : 'slots use'} the best available free agent.`;
  if (zero > 0) return `${zero} open lineup ${zero === 1 ? 'slot has' : 'slots have'} no free agent available and ${zero === 1 ? 'counts' : 'count'} as 0.`;
  return null;
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
