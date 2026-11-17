import { api, ApiError, type RequestOptions } from './client';
import type { Band, FounderLabel, FounderRow, QbScope, ReviewPosition } from '../utils/founderReview';

// Founders' review (docs/plans/founder-review/design.md §5). Every route 404s
// unless the SERVER says this session is a founder's (flag `founder.review`,
// env FOUNDER_ACCOUNTS, a verified session). The app reads no flag and keeps no
// list: the capability answer is the only gate.

// A side the engine (or the founder) leaves unlabelled is 'none'.
export interface FounderCorrection { from: Band; to: Band; count: number; }

export interface FounderSummary {
  positions: Record<ReviewPosition, { moved: number; corrections: FounderCorrection[] }>;
  overrides_total: number;
  overrides_here: number;
}

export interface FounderPage {
  schema: 'founder-label-review-1';
  labels: FounderLabel[];
  bands: string[];
  qb_scope: QbScope | null;
  evidence: { state: string | null; reason: string | null; weeks: number[]; captured_at: string | null };
  line: Partial<Record<ReviewPosition, number | null>>;
  players: FounderRow[];
  summary: FounderSummary;
}

export interface FounderSaveBody { league_id: string; set: Record<string, FounderLabel>; clear: string[]; }
export interface FounderSaveResult { set: number; cleared: number; overrides_total: number; }

type Opts = Pick<RequestOptions, 'signal'>;

/** True only when the server answers 200; a 404 (not a founder, or off) is false. */
export async function getFounderCapability(options?: Opts): Promise<boolean> {
  try {
    const r = await api.get<{ founder_review?: boolean }>('/api/founder/capability', {
      ...options, quietStatuses: [404],
    });
    return r?.founder_review === true;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return false;
    throw e;
  }
}

export function getFounderLabels(leagueId: string, options?: Opts): Promise<FounderPage> {
  return api.get<FounderPage>(`/api/founder/labels?league_id=${encodeURIComponent(leagueId)}`, options);
}

export function saveFounderLabels(body: FounderSaveBody): Promise<FounderSaveResult> {
  return api.post<FounderSaveResult>('/api/founder/labels', body);
}

// ── Use case 2: the decline waterfall ("Trade rules") ───────────────────────
// docs/plans/founder-review/rule-waterfall-design.md §7. Same server gate: an
// older server without these routes answers 404, and the app then never shows
// the "Trade rules" choice (getRuleWaterfall returns null).

export type WaterfallStatus = 'none' | 'running' | 'complete' | 'failed' | 'unsupported';
export type RowStatus = 'measured' | 'not_measured' | 'not_run';

export interface CatalogRule {
  key: string;
  name: string;
  description: string;
  stage: string;
  kind: 'scope' | 'search_limit' | 'rule' | 'addition' | 'exception' | 'reorder';
  protects: string;
  setting: string;
  live: boolean;
  question: string | null;
}

export interface WaterfallRow {
  key: string;
  name: string;
  description: string;
  stage: string;
  kind: string;
  status: RowStatus;
  started: number;
  removed: number;
  remaining: number;
  share_of_started: number;
  share_of_reaching: number;
}

export interface Waterfall {
  version: string;
  generator_version: string;
  started_definition: string;
  teams: number;
  started: number;
  served_generated: number;
  added: number;
  served: number;
  stages: { stage: string; removed: number }[];
  rows: WaterfallRow[];
  elapsed_ms: number;
}

export interface RuleNote {
  rule_key: string;
  rule_name: string;
  body: string;
  author: 'you' | 'founder' | null;
  updated_at: string | null;
  created_at: string | null;
  versions: number;
}

export interface RuleNoteVersion { body: string; author: 'you' | 'founder'; created_at: string; }

export interface RuleWaterfallPage {
  status: WaterfallStatus;
  error: string | null;
  run_at: string | null;
  waterfall: Waterfall | null;
  catalog: CatalogRule[];
  notes: RuleNote[];
}

/** The page, or null when the server has no such route for this session (404). */
export async function getRuleWaterfall(leagueId: string, options?: Opts): Promise<RuleWaterfallPage | null> {
  try {
    return await api.get<RuleWaterfallPage>(
      `/api/founder/rule-waterfall?league_id=${encodeURIComponent(leagueId)}`,
      { ...options, quietStatuses: [404] },
    );
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/** 202 {status: running} or 200 {status: unsupported, error}; 409 run_in_progress throws ApiError. */
export function startRuleWaterfall(leagueId: string): Promise<{ status: WaterfallStatus; run_id?: string; error?: string }> {
  return api.post('/api/founder/rule-waterfall', { league_id: leagueId }, { quietStatuses: [409] });
}

export function saveRuleNote(ruleKey: string, body: string): Promise<RuleNote> {
  return api.put<RuleNote>(`/api/founder/rule-notes/${encodeURIComponent(ruleKey)}`, { body });
}

export function getRuleNoteHistory(ruleKey: string, options?: Opts): Promise<{ rule_key: string; history: RuleNoteVersion[] }> {
  return api.get(`/api/founder/rule-notes/${encodeURIComponent(ruleKey)}`, options);
}

// ── Review pages ────────────────────────────────────────────────────────────
// docs/plans/founder-review/pages-design.md. The operator's review documents,
// stored on the server (never in the repo) and opened in a web view. Same
// founder gate plus flag `founder.review_pages`, both server-side: a 404 on
// the list hides the "Review pages" choice (listFounderPages returns null).
// The page's HTML is fetched here, through the normal client, so no session
// token, cookie or API URL ever reaches the web view; its comments come back
// over the message bridge and are saved here too.

export interface FounderPageSummary {
  slug: string;
  title: string;
  bytes: number;
  updated_at: string;
  /** The caller's own notes on this page. */
  notes: number;
}

export interface FounderPageDocument {
  slug: string;
  title: string;
  updated_at: string;
  html: string;
  /** The caller's own notes: {box key: body}. */
  notes: Record<string, string>;
}

export type FounderPageNoteSet = Record<string, { label: string; body: string }>;

/** The pages, or null when the server has no such route for this session (404). */
export async function listFounderPages(options?: Opts): Promise<FounderPageSummary[] | null> {
  try {
    const r = await api.get<{ pages: FounderPageSummary[] }>('/api/founder/pages', {
      ...options, quietStatuses: [404],
    });
    return Array.isArray(r?.pages) ? r.pages : [];
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/** One page (about 2.5 MB): the slow cap, so a slow network is not "took too long". */
export function getFounderPage(slug: string, options?: Opts): Promise<FounderPageDocument> {
  return api.get<FounderPageDocument>(`/api/founder/pages/${encodeURIComponent(slug)}`, {
    ...options, timeoutMs: 45_000,
  });
}

/** Upsert the caller's notes (a blank body clears one). */
export function saveFounderPageNotes(slug: string, set: FounderPageNoteSet): Promise<{ saved: number; cleared: number }> {
  return api.put(`/api/founder/pages/${encodeURIComponent(slug)}/notes`, { set });
}
