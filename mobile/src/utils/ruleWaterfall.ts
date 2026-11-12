// Founders' review, use case 2 — the decline waterfall's pure decisions
// (docs/plans/founder-review/rule-waterfall-design.md §6). No React, no
// runtime imports: mobile/tests/check-founder-rule-waterfall.js transpiles and
// EXECUTES this file under node.
import type {
  CatalogRule, RowStatus, RuleNote, RuleWaterfallPage, Waterfall, WaterfallRow, WaterfallStatus,
} from '../api/founder';

/** The server's cap (backend/database.py FOUNDER_NOTE_MAX_CHARS). */
export const NOTE_MAX = 2000;
/** The character counter shows from here (near the cap). */
export const NOTE_COUNTER_FROM = 1800;
/** Poll every 2 s while a run is in progress (design §6.1). */
export const POLL_MS = 2000;

const WATERFALL_KINDS = ['rule', 'search_limit'];

/** A rule as the table shows it: the catalog row plus, after a run, its counts.
 *  `status` 'pending' = no run yet for this league (counts empty). */
export interface TableRow {
  key: string;
  name: string;
  description: string;
  stage: string;
  kind: string;
  live: boolean;
  question: string | null;
  status: RowStatus | 'pending';
  removed: number | null;
  remaining: number | null;
  share: number;          // share_of_started, 0-1
  shareReaching: number;  // share_of_reaching, 0-1
}

export interface TableSection {
  stage: string;
  title: string;
  removed: number | null;   // the stage total, null before a run
  rows: TableRow[];
}

/** 45056 -> "45,056". Integers only; never locale-dependent. */
export function formatCount(n: number): string {
  const sign = n < 0 ? '-' : '';
  return sign + String(Math.round(Math.abs(n))).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** 0.914952 -> "91.5%"; a non-zero share under 0.05% reads "<0.1%". */
export function formatShare(x: number): string {
  if (x > 0 && x < 0.0005) return '<0.1%';
  return `${(x * 100).toFixed(1)}%`;
}

export function stageTitle(stage: string): string {
  return stage ? stage.charAt(0).toUpperCase() + stage.slice(1) : stage;
}

export function isWaterfallRule(rule: Pick<CatalogRule, 'kind'>): boolean {
  return WATERFALL_KINDS.includes(rule.kind);
}

/** Every waterfall rule in the server's order, grouped by stage, with counts
 *  when there is a run; and the catalog's other entries (the pool, liked trades,
 *  standing offers, the five-card floor, the repeat cap) for their notes. */
export function buildTable(page: Pick<RuleWaterfallPage, 'catalog' | 'waterfall'>): {
  sections: TableSection[]; others: TableRow[];
} {
  const w = page.waterfall;
  const byKey: Record<string, WaterfallRow> = {};
  for (const r of w?.rows ?? []) byKey[r.key] = r;
  const toRow = (c: CatalogRule): TableRow => {
    const r = byKey[c.key];
    return {
      key: c.key, name: c.name, description: c.description, stage: c.stage, kind: c.kind,
      live: c.live, question: c.question,
      status: r ? r.status : 'pending',
      removed: r && r.status === 'measured' ? r.removed : null,
      remaining: r && r.status === 'measured' ? r.remaining : null,
      share: r ? r.share_of_started : 0,
      shareReaching: r ? r.share_of_reaching : 0,
    };
  };
  // The server's order: the waterfall's own rows when there is a run, else the catalog's.
  const ordered = w
    ? w.rows.map((r) => page.catalog.find((c) => c.key === r.key)).filter((c): c is CatalogRule => !!c)
    : page.catalog.filter(isWaterfallRule);
  const sections: TableSection[] = [];
  for (const c of ordered) {
    let section = sections[sections.length - 1];
    if (!section || section.stage !== c.stage) {
      const total = w?.stages.find((s) => s.stage === c.stage);
      section = { stage: c.stage, title: stageTitle(c.stage), removed: total ? total.removed : null, rows: [] };
      sections.push(section);
    }
    section.rows.push(toRow(c));
  }
  const others = page.catalog.filter((c) => !isWaterfallRule(c)).map(toRow);
  return { sections, others };
}

/** A measured rule that removed nothing: shown, but quieter, and hideable. */
export function isZero(row: TableRow): boolean {
  return row.status === 'measured' && row.removed === 0;
}

/** Words, never a 0, for a row with no count. null = show the numbers. */
export function statusWords(row: TableRow): string | null {
  if (row.status === 'not_measured') return 'Not measured: this step writes data, so a run cannot replay it';
  if (row.status === 'not_run') return 'Not run for this deck (switched off or not used here)';
  return null;
}

/** VoiceOver, one line per row: "rule name, removed N, remaining M". */
export function rowA11yLabel(row: TableRow, hasNote: boolean): string {
  let counts: string;
  if (row.status === 'measured') {
    counts = `removed ${formatCount(row.removed ?? 0)}, remaining ${formatCount(row.remaining ?? 0)}`;
  } else if (row.status === 'not_measured') {
    counts = 'not measured';
  } else if (row.status === 'not_run') {
    counts = 'not run for this deck';
  } else {
    counts = 'not counted yet';
  }
  return `${row.name}, ${counts}${hasNote ? ', has a note' : ''}`;
}

export function headerLine(w: Waterfall): string {
  return `Started with ${formatCount(w.started)} candidate trades → ${formatCount(w.served)} served`;
}

/** The additions, never netted into a rule's row. null when nothing was added. */
export function addedLine(w: Waterfall): string | null {
  if (!w.added) return null;
  return `+${formatCount(w.added)} added after the deck was built: trades another manager already liked, or standing offers`;
}

export function pollInterval(status: WaterfallStatus | undefined): number | false {
  return status === 'running' ? POLL_MS : false;
}

/** "1,843 / 2,000" from NOTE_COUNTER_FROM characters, else null. */
export function noteCounter(length: number): string | null {
  return length >= NOTE_COUNTER_FROM ? `${formatCount(length)} / ${formatCount(NOTE_MAX)}` : null;
}

export function notesByKey(notes: RuleNote[] | undefined): Record<string, RuleNote> {
  const out: Record<string, RuleNote> = {};
  for (const n of notes ?? []) out[n.rule_key] = n;
  return out;
}

/** Rule keys whose draft differs from the saved note (compared trimmed, as the server stores). */
export function dirtyKeys(drafts: Record<string, string>, saved: Record<string, RuleNote>): string[] {
  return Object.keys(drafts).filter((k) => drafts[k].trim() !== (saved[k]?.body ?? ''));
}

/** "you · 2h ago" style byline for the saved note, null when there is none. */
export function noteByline(note: RuleNote | undefined, ago: (iso: string) => string): string | null {
  if (!note || !note.updated_at || !note.versions) return null;
  return `Last edited by ${note.author ?? 'founder'} · ${ago(note.updated_at)}`;
}

export function earlierVersions(note: RuleNote | undefined): number {
  return note && note.versions > 1 ? note.versions - 1 : 0;
}

/** What the page says about the latest run when it did not complete. */
export function statusMessage(page: Pick<RuleWaterfallPage, 'status' | 'error'>): string | null {
  if (page.status === 'failed') return `The last run failed. ${page.error ?? ''}`.trim();
  if (page.status === 'unsupported') return `This league can't be measured: ${page.error ?? 'its deck is not built rules-first.'}`;
  return null;
}

/** The Run button's error for a start the server refused. */
export function startErrorText(status: number | undefined, code: string | undefined): string {
  if (status === 409 || code === 'run_in_progress') return 'Another run is in progress on the server. Try again in a minute.';
  if (code === 'league_not_selected') return 'Switch the app to this league first, then run.';
  return 'Couldn’t start the run. Try again.';
}
