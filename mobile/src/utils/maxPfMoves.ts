// Max PF moves — the section's pure decisions (flag `league.max_pf_moves`;
// contract: docs/plans/league-projections/max-pf-trade-away/contract.md).
// The app reads every number from the server's `max_pf_moves` block and
// never re-computes one; this module only decides what shows (§4.3, §6),
// formats (§11) and fills the copy (§10, utils/maxPfMovesCopy.ts).
// No React, no I/O. Its one runtime import is the zero-import copy table;
// tests/check-max-pf-moves.js transpiles both and executes them.
import type {
  MaxPfMoves, MaxPfMoveRow, MaxPfMovesState, MaxPfReplacement, DraftOrderRule,
} from '../api/leagueProjections';
import { MAXPF_COPY as C } from './maxPfMovesCopy';

export const MAXPF_VERSION = 1;
export const ROWS_BEFORE_SHOW_ALL = 5;
/** Inclusive (contract §6.1: the `REBUILDING_MAX` cut). */
export const DEFAULT_OPEN_MAX_PLAYOFF = 0.45;
export const SCREEN = 'Standings';

const KNOWN_STATES: readonly MaxPfMovesState[] = [
  'unavailable', 'season_over', 'after_trade_deadline', 'draft_order_not_maxpf', 'no_miss', 'no_moves', 'ready',
];
const KNOWN_REASONS = [
  'no_forecast', 'update_pending', 'refresh_failed', 'stale', 'old_model', 'incomplete', 'team_not_found',
  'unsupported', 'missing_projections', 'read_failed', 'not_computed',
];
export type DraftOrderAnswer = DraftOrderRule | 'not_sure';
export const DRAFT_ORDER_ANSWERS: readonly DraftOrderAnswer[] = [
  'maxpf_lowest_first', 'reverse_standings', 'lottery_or_other', 'not_sure',
];

// ── Device storage keys (contract §6.4) ─────────────────────────────────
export const RULES_NOTE_KEY = 'maxpf.rulesNoteShown';
export const draftOrderAskedKey = (leagueId: string) => `maxpf.draftOrderAsked.${leagueId}`;

// ── Analytics (contract §9) ─────────────────────────────────────────────
export const MAXPF_EVENTS = {
  viewed: 'maxpf_moves_viewed',
  expanded: 'maxpf_move_expanded',
  pinned: 'finder_target_pinned',
  answered: 'draft_order_rule_answered',
} as const;

// ── Formatting (contract §11) ───────────────────────────────────────────
const MINUS = '−';
export const ARROW = ' → ';
const halfAwayFromZero = (n: number) => Math.sign(n) * Math.floor(Math.abs(n) + 0.5 + 1e-9);
const thousands = (n: number) => String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

/** Whole points from the integer field; negatives with U+2212; 0 as `0`. */
export function formatPoints(n: number): string {
  const r = halfAwayFromZero(n);
  return r < 0 ? `${MINUS}${Math.abs(r)}` : String(r);
}
/** A week's change: one decimal, U+2212. */
export function formatWeekChange(n: number): string {
  const s = Math.abs(n).toFixed(1);
  return n < 0 && s !== '0.0' ? `${MINUS}${s}` : s;
}
/** Pick if you miss: one decimal; null → "—" (§6.6). */
export function formatPick(n: number | null | undefined): string {
  return n == null ? '—' : n.toFixed(1);
}
/** Whole percent, round half up; `<1%`, `>99%`; 0% and 100% exact. */
export function formatPct(p: number): string {
  if (p <= 0) return '0%';
  if (p >= 1) return '100%';
  if (p < 0.005) return '<1%';
  if (p >= 0.995) return '>99%';
  return `${Math.floor(p * 100 + 0.5 + 1e-9)}%`;
}
/** Baseline pick value: whole number, thousands separator. */
export function formatValue(n: number): string {
  const r = halfAwayFromZero(n);
  return `${r < 0 ? MINUS : ''}${thousands(r)}`;
}
/** Pick value change: whole number, leading + or −, thousands separator. */
export function formatValueChange(n: number): string {
  const r = halfAwayFromZero(n);
  return `${r < 0 ? MINUS : '+'}${thousands(r)}`;
}
const pair = (now: string, after: string) => `${now}${ARROW}${after}`;

/** Fills `{key}` placeholders. Unknown keys stay as written. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{([a-z0-9_]+)\}/g, (m, k) => (k in values ? String(values[k]) : m));
}
/** "a", "a and b", "a, b and c" (the C-BYE.3 shape). */
export function listText(items: string[]): string {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}
const weeksText = (w: number) => (w === 1 ? C['C-REPL-N.one'] : `${w} weeks`);

// ── Mount rule (contract §4.3 "hidden", §8) ──────────────────────────────
export interface MountInputs {
  block: MaxPfMoves | null | undefined;
  flagOn: boolean;
  isSleeper: boolean;
  /** `team.roster_id === result.viewer_roster_id` (contract §2). */
  ownCard: boolean;
}
export function sectionMounts({ block, flagOn, isSleeper, ownCard }: MountInputs): boolean {
  return !!block && flagOn && isSleeper && ownCard && block.version === MAXPF_VERSION
    && KNOWN_STATES.includes(block.state);
}
export function isOwnCard(teamRosterId: number, resultViewer: number | null | undefined, block?: MaxPfMoves | null): boolean {
  const viewer = resultViewer ?? block?.viewer_roster_id ?? null;
  return viewer != null && teamRosterId === viewer;
}

// ── Derived state (contract §6) ─────────────────────────────────────────
const isListState = (s: MaxPfMovesState) => s === 'ready' || s === 'no_moves';

export function defaultOpen(block: MaxPfMoves): boolean {
  const p = block.baseline?.playoff_probability;
  return (p != null && p <= DEFAULT_OPEN_MAX_PLAYOFF)
    || block.saved_outlook === 'rebuilder' || block.saved_outlook === 'jets';
}
export function ownerGateActive(block: MaxPfMoves): boolean {
  return isListState(block.state) && block.pick_owner?.owns_own_pick === false;
}
/** The outer disclosure starts open only when default-open and not gated. */
export function initialOpen(block: MaxPfMoves): boolean {
  return isListState(block.state) && defaultOpen(block) && !ownerGateActive(block);
}
/** Live roster vs the forecast's roster; null when either is unavailable. */
export function rosterChanged(block: MaxPfMoves, liveIds: string[] | null | undefined): boolean {
  if (!isListState(block.state) || !liveIds || !block.roster_player_ids) return false;
  const live = new Set(liveIds);
  const saved = new Set(block.roster_player_ids);
  if (live.size !== saved.size) return true;
  for (const id of live) if (!saved.has(id)) return true;
  return false;
}
/** Passing rows in rank order, minus players no longer on the live roster. */
export function listedRows(block: MaxPfMoves, liveIds: string[] | null | undefined): MaxPfMoveRow[] {
  if (block.state !== 'ready') return [];
  const changed = rosterChanged(block, liveIds);
  const live = changed && liveIds ? new Set(liveIds) : null;
  return block.rows
    .filter((r) => r.passes_threshold === true && (!live || live.has(r.player_id)))
    .sort((a, b) => a.rank - b.rank);
}
export function visibleRows(listed: MaxPfMoveRow[], showAll: boolean) {
  return {
    rows: showAll ? listed : listed.slice(0, ROWS_BEFORE_SHOW_ALL),
    showAllButton: !showAll && listed.length > ROWS_BEFORE_SHOW_ALL,
  };
}
export function priced(block: MaxPfMoves): boolean {
  return block.baseline?.pick_value_status === 'priced';
}
/** The once-per-league question may show (before the device check). */
export function questionEligible(block: MaxPfMoves): boolean {
  return block.draft_order.rule === null
    && (block.state === 'ready' || block.state === 'no_moves' || block.state === 'no_miss');
}
export function questionAutoShown(block: MaxPfMoves, askedOnDevice: boolean): boolean {
  return questionEligible(block) && !askedOnDevice;
}

// ── Lines ───────────────────────────────────────────────────────────────
export function unavailableLine(reason: string | null): string {
  const key = `C-U-${reason}` as keyof typeof C;
  return reason && KNOWN_REASONS.includes(reason) && key in C ? C[key] : C['C-U-other'];
}
/** The one line a non-list state shows; null for ready / no_moves. */
export function stateLine(block: MaxPfMoves): string | null {
  switch (block.state) {
    case 'unavailable': return unavailableLine(block.reason);
    case 'season_over': return C['C-SEASON-OVER'];
    case 'after_trade_deadline': return C['C-DEADLINE'];
    case 'draft_order_not_maxpf': return C['C-NOT-MAXPF'];
    case 'no_miss': return C['C-NO-MISS'];
    default: return null;
  }
}
/** The link after the state line or the order line ("Change" / "Change answer"). */
export function orderLine(block: MaxPfMoves): { text: string | null; link: string } | null {
  if (block.state === 'draft_order_not_maxpf') return { text: null, link: C['C-NOT-MAXPF.link'] };
  if (!(isListState(block.state) || block.state === 'no_miss')) return null;
  if (block.draft_order.rule === null) return { text: C['C-ORDER-ASSUMED'], link: C['C-ORDER.link'] };
  if (block.draft_order.rule === 'maxpf_lowest_first') return { text: C['C-ORDER-MAXPF'], link: C['C-ORDER.link'] };
  return null;
}
export function baselineLine(block: MaxPfMoves): string | null {
  const b = block.baseline;
  if (!b || !isListState(block.state)) return null;
  const full = C['C-BASE'];
  const season = block.draft_season ?? '';
  const template = b.label == null
    ? C['C-BASE.nolabel'] + full.slice(full.indexOf(' If you miss'))
    : full;
  let line = fill(template, {
    season, label: b.label ?? '', pick_if_miss: formatPick(b.pick_if_miss), top3: formatPct(b.top3_probability),
  });
  if (priced(block) && b.pick_value != null) line += fill(C['C-BASE.value'], { value: formatValue(b.pick_value) });
  return line;
}
export function headLine(block: MaxPfMoves): string | null {
  const n = block.baseline?.weeks_remaining;
  if (n == null) return null;
  if (n === 1) return C['C-HEAD'].replace('over the remaining {n} weeks', C['C-HEAD.final']);
  return fill(C['C-HEAD'], { n });
}
export function collapsedLine(block: MaxPfMoves): string {
  return fill(C['C-COLLAPSED'], { playoff: formatPct(block.baseline?.playoff_probability ?? 0) });
}
export function ownerLine(block: MaxPfMoves): string {
  return fill(C['C-OWNER'], { owner_name: block.pick_owner?.owner_name ?? '', season: block.draft_season ?? '' });
}

// ── Rows (contract §10 C-ROW-*, C-OPEN-*, C-REPL-*, C-BYE, C-WEEK) ───────
export function rowLine1Parts(row: MaxPfMoveRow) {
  return { name: row.short_name, position: row.position, change: formatPoints(row.maxpf_change) };
}
export function rowLine1(row: MaxPfMoveRow): string {
  const p = rowLine1Parts(row);
  return fill(C['C-ROW-1'], { short_name: p.name, position: p.position, maxpf_change: p.change });
}
export function rowLine2(row: MaxPfMoveRow, isPriced: boolean): string {
  let line = fill(C['C-ROW-2'], { now: formatPick(row.pick_if_miss.now), after: formatPick(row.pick_if_miss.after) });
  if (isPriced && row.pick_value) line += fill(C['C-ROW-2.value'], { change: formatValueChange(row.pick_value.change) });
  return line;
}
type Named = Pick<MaxPfReplacement, 'player_id' | 'name' | 'free_agent'>;
/** A replacement's name: free agents marked, an empty slot in words. */
export function replacementName(r: Named, first = false): string {
  if (r.player_id == null) {
    const s = C['C-REPL-EMPTY'];
    return first ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  }
  const name = r.name ?? '';
  return r.free_agent ? fill(C['C-REPL-FA'], { name }) : name;
}
export function replacementLine(row: MaxPfMoveRow): string | null {
  const reps = row.replacements;
  if (reps.length === 0) return null;
  if (reps.length === 1 && row.replacements_more === 0 && reps[0].weeks === row.weeks_affected) {
    return fill(C['C-REPL-1'], { name: replacementName(reps[0], true) });
  }
  const tmpl = C['C-REPL-N'];
  const cut = tmpl.indexOf(', ');
  const head = tmpl.slice(0, cut);              // "{name1} starts instead ({w1} weeks)"
  const tail = tmpl.slice(cut + 2, -1);         // "{name2} ({w2} weeks)"
  const parts = reps.slice(0, 3).map((r, i) => (i === 0
    ? head.replace('{w1} weeks', weeksText(r.weeks)).replace('{name1}', () => replacementName(r, true))
    : tail.replace('{w2} weeks', weeksText(r.weeks)).replace('{name2}', () => replacementName(r))));
  const body = parts.join(', ');
  return row.replacements_more > 0 ? body + fill(C['C-REPL-N.more'], { k: row.replacements_more }) : `${body}.`;
}
export function byeLine(row: MaxPfMoveRow): string | null {
  const w = row.weeks.filter((x) => x.status === 'bye').map((x) => String(x.week));
  if (w.length === 0) return null;
  if (w.length === 1) return fill(C['C-BYE.1'], { w: w[0] });
  if (w.length === 2) return fill(C['C-BYE.2'], { a: w[0], b: w[1] });
  return C['C-BYE.3'].replace('{a}, {b} and {c}', listText(w));
}
export function weekLines(row: MaxPfMoveRow): string[] {
  return row.weeks.flatMap((w) => {
    switch (w.status) {
      case 'changed':
        return [fill(C['C-WEEK.changed'], {
          w: w.week, maxpf_change: formatWeekChange(w.maxpf_change),
          names: listText(w.replaced_by.map((r) => replacementName(r))),
        })];
      case 'bye': return [fill(C['C-WEEK.bye'], { w: w.week })];
      case 'no_change': return [fill(C['C-WEEK.no_change'], { w: w.week })];
      case 'played': return [fill(C['C-WEEK.played'], { w: w.week })];
      default: return []; // `not_projected` is reserved and cannot occur in a listed row
    }
  });
}
export interface RowDetail {
  top3: string;
  playoff: string;
  label: string | null;
  replacement: string | null;
  weeks: string[];
  /** Find trades button label; null on a Keep row. */
  button: string | null;
  /** C-KEEP-NOTE on a Keep row; null otherwise. */
  keepNote: string | null;
}
export function rowDetail(row: MaxPfMoveRow): RowDetail {
  const { now, after } = row.label;
  let label: string | null = null;
  if (now != null && after != null) {
    label = now === after ? fill(C['C-OPEN-LABEL.same'], { now }) : fill(C['C-OPEN-LABEL'], { now, after });
  }
  const repl = replacementLine(row);
  const bye = byeLine(row);
  return {
    top3: fill(C['C-OPEN-TOP3'], { now: formatPct(row.top3_probability.now), after: formatPct(row.top3_probability.after) }),
    playoff: fill(C['C-OPEN-PLAYOFF'], { now: formatPct(row.playoff_probability.now), after: formatPct(row.playoff_probability.after) }),
    label,
    replacement: repl && bye ? `${repl} ${bye}` : repl ?? bye,
    weeks: weekLines(row),
    button: row.keep ? null : fill(C['C-BUTTON'], { short_name: row.short_name }),
    keepNote: row.keep ? fill(C['C-KEEP-NOTE'], { short_name: row.short_name }) : null,
  };
}

// ── The whole section ───────────────────────────────────────────────────
export interface SectionModel {
  state: MaxPfMovesState;
  isList: boolean;
  line: string | null;
  order: { text: string | null; link: string } | null;
  defaultOpen: boolean;
  ownerGate: boolean;
  initialOpen: boolean;
  ownerLine: string | null;
  collapsedLine: string | null;
  baseline: string | null;
  head: string | null;
  rosterChanged: boolean;
  rosterLine: string | null;
  listed: MaxPfMoveRow[];
  noMovesLine: string | null;
  foot: string | null;
  priced: boolean;
  questionEligible: boolean;
}
export function deriveSection(block: MaxPfMoves, liveIds: string[] | null | undefined): SectionModel {
  const list = isListState(block.state);
  const changed = rosterChanged(block, liveIds);
  const listed = listedRows(block, liveIds);
  const open = list && defaultOpen(block);
  const gate = ownerGateActive(block);
  return {
    state: block.state,
    isList: list,
    line: stateLine(block),
    order: orderLine(block),
    defaultOpen: open,
    ownerGate: gate,
    initialOpen: initialOpen(block),
    ownerLine: gate ? ownerLine(block) : null,
    collapsedLine: list && !open ? collapsedLine(block) : null,
    baseline: baselineLine(block),
    head: listed.length > 0 ? headLine(block) : null,
    rosterChanged: changed,
    rosterLine: changed ? C['C-ROSTER'] : null,
    listed,
    // Every passing row dropped by the roster check ⇒ C-ROSTER only.
    noMovesLine: list && listed.length === 0 && !changed ? C['C-NO-MOVES'] : null,
    foot: listed.length > 0 ? C['C-FOOT'] : null,
    priced: priced(block),
    questionEligible: questionEligible(block),
  };
}

// ── Event properties (contract §9; never a player id or name) ───────────
export function viewedProps(block: MaxPfMoves, model: SectionModel) {
  return {
    state: block.state,
    n_moves: block.state === 'ready' ? model.listed.length : 0,
    band: block.baseline?.playoff_band ?? 'none',
  };
}
export const expandedProps = (row: MaxPfMoveRow) => ({ position: row.position, rank: row.rank });
export const PINNED_PROPS = { side: 'give', source: 'maxpf_moves' } as const;
export const answeredProps = (answer: DraftOrderAnswer, source: 'first_ask' | 'change') => ({ answer, source });

// ── Draft-order write (contract §7.2) ───────────────────────────────────
export function draftOrderRequest(leagueId: string, rule: DraftOrderAnswer) {
  return { path: `/api/leagues/${encodeURIComponent(leagueId)}/draft-order-rule`, body: { rule } };
}
export const answerLabel = (a: DraftOrderAnswer) => C[`C-Q-OPTS.${a}` as const];

// ── The Find trades hand-off (contract §12) ─────────────────────────────
export interface HandOffDeps {
  setSide: (side: 'give' | 'receive', players: { id: string; name: string; position: string }[]) => void;
  track: (event: string, props: Record<string, unknown>, screen: string) => void;
  navigate: () => void;
}
/** Pins the row's player on the give side, clears receive, logs, opens the
 *  deck. No hand-off object, no auto-run. A Keep row does nothing. */
export function handOffToFinder(row: MaxPfMoveRow, deps: HandOffDeps): boolean {
  if (row.keep) return false;
  deps.setSide('give', [{ id: row.player_id, name: row.name, position: row.position }]);
  deps.setSide('receive', []);
  deps.track(MAXPF_EVENTS.pinned, { ...PINNED_PROPS }, SCREEN);
  deps.navigate();
  return true;
}
