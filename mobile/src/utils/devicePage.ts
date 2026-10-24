// 200 ms path, C — the device-held first page (scope-eng-200ms §2 "C device
// page", PRD #339 §10.1 approach B, AC-L1's P32 clause, §5.x row 5).
//
// The phone keeps the next unseen cards of the last validated organic deck,
// per (user, league, scoring format, default request scope), so a tap can
// render a card with no network wait. The server stays authoritative: the
// deck that renders it revalidates at once, and that response replaces the
// device copy with whole-deck semantics (U2, AC-L5).
//
// Pure BY CONTRACT, like utils/tradePages.ts (the one runtime import):
// no React, no I/O, no module state. tests/check-device-first-page.js
// transpiles this file and runs it under plain node.
import type { PagedTradeCard, PagedTradeJobSnapshot } from '../api/trades';
import { deckCardKey, mergeDeckPage, type DeckKeyed, type MergeResult } from './tradePages';

/** A device page renders at the tap only this long after it was last
 *  validated by the server (device clock). It is PRD #339 §5.1's viewer-
 *  roster bound (≤ 5 min since last confirmed); docs/cross-client-
 *  invariants.md "Device-held first page" holds the row. */
export const DEVICE_PAGE_MAX_AGE_S = 300;
/** Background refresh (approach B): at most once per key per this long. */
export const DEVICE_PAGE_REFRESH_MIN_S = 60;
/** One page: E2's default `trade_page_size`. */
export const DEVICE_PAGE_MAX_CARDS = 30;
/** "Updating" during a revalidation lasts at most this long; then the
 *  refresh-failed line shows (PRD §5.4 shared constraint 4). */
export const DEVICE_REVALIDATE_MAX_MS = 10_000;
/** Versioned AsyncStorage key prefix. A shape change bumps the version. */
export const DEVICE_PAGE_KEY_PREFIX = 'ftf_trade_device_page_v1:';

export interface DevicePage {
  v: 1;
  /** The organic request scope the cards answer (devicePageScope). */
  scope: string;
  /** Next unseen cards of the last validated deck, server order, ≤ one page. */
  cards: PagedTradeCard[];
  job_id: string;
  deck_id: string;
  cursor: number;
  total_ready: number | null;
  pool_exhausted: boolean | null;
  opponents_total: number;
  /** The server's page fingerprints, when a response carries them; stored,
   *  never compared on the device (revalidation is the server's job). */
  built_at: string | null;
  roster_fp: string | null;
  vsn: string | null;
  /** Device clock (ms epoch) of the last server response that validated it. */
  validated_at: number;
}

/** `ftf_trade_device_page_v1:<user>:<league>:<fmt>`, or null when any part is
 *  unknown. A league or format switch is a different key, so it never reads
 *  the other one's page. */
export function devicePageKey(
  userId: string | null | undefined,
  leagueId: string | null | undefined,
  fmt: string | null | undefined,
): string | null {
  if (!userId || !leagueId || !fmt) return null;
  return `${DEVICE_PAGE_KEY_PREFIX}${userId}:${leagueId}:${fmt}`;
}

/** The default (organic) request scope, as the server names it
 *  (`_trade_page_scope`: `organic:f=<threshold, 2 dp>`), or null for any
 *  request the server's page store doesn't serve either: pins, an opponent,
 *  an intent, `force`, the demo league, the account-only sentinel. */
export function devicePageScope(request: {
  league_id?: string;
  fairness_threshold?: number;
  pinned_give_players?: readonly string[];
  pinned_receive_players?: readonly string[];
  opponent_user_id?: string;
  trade_intent?: string;
  force?: boolean;
}): string | null {
  if (!request.league_id || request.league_id === 'league_demo' || request.league_id === 'no_league') {
    return null;
  }
  if (request.force || request.opponent_user_id || request.trade_intent
      || request.pinned_give_players?.length || request.pinned_receive_players?.length) {
    return null;
  }
  const f = request.fairness_threshold;
  if (typeof f !== 'number' || !Number.isFinite(f)) return null;
  return `organic:f=${f.toFixed(2)}`;
}

type ServerPage = Pick<PagedTradeJobSnapshot,
  'job_id' | 'status' | 'error' | 'opponents_total' | 'deck_id' | 'cursor' | 'total_ready'
  | 'pool_exhausted' | 'freshness_state'> & {
    cards: readonly PagedTradeCard[];
    built_at?: string;
    roster_fp?: string;
    values_snapshot_id?: string;
  };

/** Only a complete, non-error, ownership-checked page is kept: the job
 *  finished (page 1 is the final deck's top), the serve's I-1 check ran
 *  ("updating" means it failed or the fingerprints moved), and it is a P2
 *  deck (`deck_id`: `deck=` pages it across rebuilds and restarts, which a
 *  page held for minutes needs). */
export function storableResponse(r: ServerPage): boolean {
  return r.status === 'complete'
    && !r.error
    && r.freshness_state !== 'updating'
    && typeof r.deck_id === 'string' && r.deck_id.length > 0
    && typeof r.cursor === 'number';
}

/** The device page for a server response (or for a deck's unacted cards
 *  under that response's envelope, `cards`). Null when the response may not
 *  be kept, or nothing unseen is left: the caller then discards. */
export function devicePageFrom(
  r: ServerPage,
  opts: { scope: string; validatedAt: number; cards?: readonly PagedTradeCard[] },
): DevicePage | null {
  if (!storableResponse(r)) return null;
  const cards = (opts.cards ?? r.cards).slice(0, DEVICE_PAGE_MAX_CARDS);
  if (cards.length === 0) return null;
  return {
    v: 1,
    scope: opts.scope,
    cards,
    job_id: r.job_id,
    deck_id: r.deck_id as string,
    cursor: r.cursor as number,
    total_ready: typeof r.total_ready === 'number' ? r.total_ready : null,
    pool_exhausted: typeof r.pool_exhausted === 'boolean' ? r.pool_exhausted : null,
    opponents_total: r.opponents_total || 0,
    built_at: typeof r.built_at === 'string' ? r.built_at : null,
    roster_fp: typeof r.roster_fp === 'string' ? r.roster_fp : null,
    vsn: typeof r.values_snapshot_id === 'string' ? r.values_snapshot_id : null,
    validated_at: opts.validatedAt,
  };
}

/** May this page render at the tap? Same scope, cards left, and validated
 *  within DEVICE_PAGE_MAX_AGE_S. A clock that went backwards reads as stale. */
export function devicePageUsable(
  page: DevicePage | null | undefined,
  scope: string | null,
  now: number,
): page is DevicePage {
  if (!page || !scope || page.scope !== scope || page.cards.length === 0) return false;
  const age = now - page.validated_at;
  return age >= 0 && age <= DEVICE_PAGE_MAX_AGE_S * 1000;
}

/** Background refresh throttle: due when never tried, or tried at least
 *  DEVICE_PAGE_REFRESH_MIN_S ago (or the clock went backwards). */
export function refreshDue(lastAttemptAt: number | undefined, now: number): boolean {
  if (lastAttemptAt == null) return true;
  const since = now - lastAttemptAt;
  return since < 0 || since >= DEVICE_PAGE_REFRESH_MIN_S * 1000;
}

/** May a deck validated at `validatedAt` write its cards over `held`? Not
 *  over a page the server validated later (a background refresh landed
 *  after this deck's last answer): "the last validated deck" wins. */
export function deckMayWrite(held: DevicePage | null, validatedAt: number): boolean {
  return !held || held.validated_at <= validatedAt;
}

/** Swipe update: the page without the card the user just acted on (by
 *  `deckCardKey`), so it never comes back on the next tap. Same object when
 *  the card isn't held. */
export function withoutCard(page: DevicePage, cardKey: string): DevicePage {
  const cards = page.cards.filter((c) => deckCardKey(c) !== cardKey);
  return cards.length === page.cards.length ? page : { ...page, cards };
}

/** The revalidation merge: the response is authoritative for every card the
 *  device holds, so it merges with whole-deck semantics. Seen cards and the
 *  fronted one stay put; the unseen device cards are replaced by the
 *  server's order; a fronted card the response lacks is flagged
 *  `withdrawFront` (withdrawn in place, U2). */
export function mergeRevalidation<T extends DeckKeyed>(
  held: readonly T[],
  incoming: readonly T[],
  frontKey: string | null,
): MergeResult<T> {
  return mergeDeckPage(held, incoming, frontKey, true);
}

/** The adopted first page a tap renders from a device page: R2 reports
 *  `serve_source: 'device'`. Its envelope is informational until the
 *  revalidation lands (the deck pages only from the response). */
export function devicePageSnapshot(page: DevicePage, searchId: string): PagedTradeJobSnapshot {
  return {
    job_id: page.job_id,
    status: 'complete',
    cards: page.cards,
    opponents_done: page.opponents_total,
    opponents_total: page.opponents_total,
    error: null,
    cursor: page.cursor,
    ...(page.total_ready != null ? { total_ready: page.total_ready } : {}),
    deck_id: page.deck_id,
    ...(page.pool_exhausted != null ? { pool_exhausted: page.pool_exhausted } : {}),
    serve_source: 'device',
    freshness_state: 'fresh',
    search_id: searchId,
  } as PagedTradeJobSnapshot;
}

/** A stored value back into a page, or null for anything malformed. */
export function parseDevicePage(raw: string | null | undefined): DevicePage | null {
  if (!raw) return null;
  let p: any;
  try { p = JSON.parse(raw); } catch { return null; }
  if (!p || p.v !== 1 || typeof p.scope !== 'string' || !Array.isArray(p.cards)
      || typeof p.job_id !== 'string' || typeof p.deck_id !== 'string'
      || !Number.isInteger(p.cursor) || typeof p.validated_at !== 'number'
      || !Number.isFinite(p.validated_at)
      || !p.cards.every((c: any) => c && typeof c.trade_id === 'string')) {
    return null;
  }
  return p as DevicePage;
}

/** The client's own writes that change what an organic deck would hold for
 *  the viewer: every route that revokes the viewer's trade jobs server-side
 *  for a rankings or preference change (`_invalidate_trade_jobs` call sites:
 *  trio swipe, tiers save and copy, anchor, reorder, import, league
 *  outlook/preferences and asset preferences). Each discards every device
 *  page the user holds. */
export const RANKING_WRITE_PATHS: readonly string[] = [
  '/api/rank3',
  '/api/tiers/save',
  '/api/tiers/copy-from-format',
  '/api/anchor/save',
  '/api/rankings/reorder',
  '/api/rankings/import-apply',
  '/api/league/preferences',
  '/api/league/asset-prefs',
];

export function isRankingWritePath(path: string): boolean {
  const pathname = path.replace(/^https?:\/\/[^/]+/, '').split(/[?#]/)[0];
  return RANKING_WRITE_PATHS.includes(pathname);
}
