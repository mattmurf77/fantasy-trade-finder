// 200 ms path (scope-eng-200ms §0b row 6, §6.4–§6.6): the paged deck's
// merge, prefetch and end-of-buffer rules, as pure functions.
//
// Pure and dependency-free BY CONTRACT: no React, no I/O, no module state and
// no runtime imports. tests/check-trade-pages.js and check-trade-buffer.js
// transpile this file and run it under plain node (the applyJobResult idiom);
// a runtime import added here breaks both suites loudly.
//
// Contract read: docs/api-reference.md "Opt-in paged responses (E2…)" and
// "First-page store (P1…)", plus the P2 design draft §2–§4 (`deck_id`,
// `rebased`, `pool_exhausted`, client dedupe by `trade_hash`).

/** Head-eng ruling 10: the device holds at least this many unseen cards.
 *  The server's `prefetch_remaining` wins; this is the client fallback. */
export const PREFETCH_REMAINING_FALLBACK = 50;

export interface DeckKeyed {
  trade_id: string;
  trade_hash?: string;
}

/** The deck's dedupe key: the server's stable trade identity when sent,
 *  else the card id (a server without `trade_hash` dedupes exactly as
 *  today). `trade_id` alone is minted per build, so it can't dedupe a
 *  rebased deck against the one it replaced. */
export function deckCardKey(card: DeckKeyed): string {
  return card.trade_hash || card.trade_id;
}

export interface PageEnvelope {
  status: 'running' | 'complete' | 'error';
  /** P2's deck identity. Present ⇔ the page store is on (head-eng's end
   *  rule keys on it: with it, only `pool_exhausted` ends the deck). */
  deck_id?: string;
  cursor?: number;
  total_ready?: number;
  replace?: boolean;
  rebased?: boolean;
  pool_exhausted?: boolean;
}

/** A response is paged when it carries a cursor. Without one it is the
 *  legacy cumulative snapshot, handled exactly as before this change. */
export function isPagedEnvelope(s: { cursor?: number } | null | undefined): boolean {
  return typeof s?.cursor === 'number';
}

/** Every field only a paged response carries (E2 / P1 / P2). */
export const PAGING_FIELDS = [
  'cursor', 'total_ready', 'replace', 'deck_id', 'rebased', 'pool_exhausted',
  'serve_source', 'freshness_state', 'prefetch_remaining',
] as const;

export interface DeckJob extends PageEnvelope {
  job_id: string;
  cards: readonly unknown[];
  search_id?: string;
  serve_source?: string;
  freshness_state?: string;
  prefetch_remaining?: number;
}

/**
 * The job the deck holds once a response to it lands (TradesScreen
 * `applyPage`), with `cards` the merged deck.
 *
 * - A PAGED response keeps the search's identity (`job_id`; `rebind` adopts
 *   the response's instead) and takes the page identity (`deck_id`; on a
 *   `revalidation`, the response's even when absent).
 * - A LEGACY response (no `cursor`: the server's paging kill switch,
 *   `model_config` `trade_paged_responses = 0`, flipped mid-deck) leaves
 *   paging for good: no paging field survives from `prev`, so the deck is no
 *   longer paged, the page loop stops (`wantsNextPage` is false) and the
 *   legacy poller takes over the response's job.
 */
export function nextDeckJob<J extends DeckJob>(
  prev: J | null,
  next: J,
  cards: J['cards'],
  opts: { revalidation?: boolean; rebind?: boolean } = {},
): J {
  if (!isPagedEnvelope(next)) {
    const legacy = {
      ...(prev ?? {}),
      ...next,
      job_id: next.job_id || prev?.job_id,
      search_id: prev?.search_id ?? next.search_id,
      cards,
    } as unknown as Record<string, unknown>;
    for (const field of PAGING_FIELDS) delete legacy[field];
    return legacy as unknown as J;
  }
  return {
    ...(prev ?? {}),
    ...next,
    job_id: opts.rebind ? next.job_id : prev?.job_id || next.job_id,
    deck_id: opts.revalidation ? next.deck_id : next.deck_id ?? prev?.deck_id,
    search_id: prev?.search_id ?? next.search_id,
    freshness_state: next.freshness_state,
    pool_exhausted: next.pool_exhausted,
    replace: undefined,
    rebased: undefined,
    cards,
  } as J;
}

/** The response's cards are the server's WHOLE current deck: E2's
 *  `replace: true`, or a rebased first page that already spans the new,
 *  finished deck. Only then may a held card be judged "no longer served";
 *  a rebased first page of a longer deck says nothing about later pages. */
export function isWholeDeck(r: PageEnvelope): boolean {
  if (r.replace === true) return true;
  return r.rebased === true
    && r.status === 'complete'
    && typeof r.cursor === 'number'
    && typeof r.total_ready === 'number'
    && r.cursor >= r.total_ready;
}

export interface MergeResult<T> {
  cards: T[];
  /** Cards the device did not hold before this response. */
  added: number;
  /** The fronted card is absent from a whole-deck response: withdraw it in
   *  place (it keeps its slot and shows a reason; U2). */
  withdrawFront: boolean;
}

/**
 * Merge one paged response into the cards the device holds.
 *
 * - The fronted card and every card before it (already seen) never move,
 *   change or disappear: no reorder, no jump (U3 row 1, AC-9, ruling 16).
 * - An append page puts its new cards BEHIND everything held, in server
 *   order, deduped by `deckCardKey`.
 * - A whole-deck response (`replace`, or a rebased page spanning the new
 *   deck) is taken only for what is BEHIND the front: the held behind-cards
 *   are replaced by the response's cards in server order, deduped against
 *   the kept head. A behind-card the server no longer serves is dropped
 *   silently; a fronted card it no longer serves is flagged `withdrawFront`.
 *
 * `frontKey` is the fronted card's `deckCardKey`, or null when nothing is
 * fronted (the user is past the last held card): then every held card is
 * already seen and the response can only append.
 */
export function mergeDeckPage<T extends DeckKeyed>(
  held: readonly T[],
  incoming: readonly T[],
  frontKey: string | null,
  wholeDeck: boolean,
): MergeResult<T> {
  const frontIndex = frontKey == null
    ? -1
    : held.findIndex((c) => deckCardKey(c) === frontKey);
  const keepAll = !wholeDeck || frontIndex < 0;
  const head = keepAll ? held.slice() : held.slice(0, frontIndex + 1);
  const taken = new Set(head.map(deckCardKey));
  const behind: T[] = [];
  for (const card of incoming) {
    const key = deckCardKey(card);
    if (taken.has(key)) continue;
    taken.add(key);
    behind.push(card);
  }
  const heldKeys = new Set(held.map(deckCardKey));
  const added = behind.filter((c) => !heldKeys.has(deckCardKey(c))).length;
  const withdrawFront = wholeDeck
    && frontIndex >= 0
    && !incoming.some((c) => deckCardKey(c) === frontKey);
  return { cards: [...head, ...behind], added, withdrawFront };
}

/** Unseen = held cards behind the fronted one. With nothing fronted (the
 *  user is past the last held card) there are none. */
export function unseenCount(visibleLength: number, frontIndex: number): number {
  if (frontIndex >= visibleLength) return 0;
  return Math.max(0, visibleLength - frontIndex - 1);
}

/** No further page can arrive for this search (head-eng's end rule):
 *  - the job errored; or
 *  - responses carry `deck_id` (the page store is on, P2): the server said
 *    `pool_exhausted`, and nothing else ends the deck; or
 *  - no `deck_id` (flag off, E2 only): the job is `complete` and every ready
 *    card has been paged (cursor ≥ total_ready). */
export function deckFullyDelivered(s: PageEnvelope): boolean {
  if (s.status === 'error') return true;
  if (s.pool_exhausted === true) return true;
  if (typeof s.deck_id === 'string') return false;
  return s.status === 'complete'
    && typeof s.cursor === 'number'
    && typeof s.total_ready === 'number'
    && s.cursor >= s.total_ready;
}

/** Ruling 10: request the next page while FEWER than `prefetch_remaining`
 *  unseen cards are held (the server's value, else 50). At most one request
 *  in flight or scheduled (`busy`). Page 1 is usually below the threshold, so
 *  this fires right after the first card renders. */
export function wantsNextPage(s: PageEnvelope & {
  unseen: number;
  prefetch_remaining?: number;
  busy: boolean;
}): boolean {
  if (s.busy || !isPagedEnvelope(s) || deckFullyDelivered(s)) return false;
  return s.unseen < (s.prefetch_remaining ?? PREFETCH_REMAINING_FALLBACK);
}

/** After a page lands: wait before asking again? Yes when the deck is still
 *  building and the client has caught up with it (every ready card paged),
 *  or the cursor did not move. Otherwise the next request may go at once
 *  (a rebased page that came back short after dedupe, P2 §2). */
export function needsBackoff(r: PageEnvelope, requestedCursor: number): boolean {
  if (deckFullyDelivered(r)) return false;
  if (typeof r.cursor === 'number' && typeof r.total_ready === 'number'
      && r.cursor >= r.total_ready) return true;
  return r.rebased !== true && (r.cursor ?? requestedCursor) <= requestedCursor;
}

/** Silent retry ladder for an empty-while-building page or a failed fetch:
 *  0.5 s, 1 s, 2 s, then 4 s. Short on purpose: the buffer is the user's
 *  next few seconds of swiping. */
export function pageRetryDelayMs(attempt: number): number {
  return Math.min(4000, 500 * 2 ** Math.max(0, attempt));
}

/** The retry attempt after a page landed. A page that must wait but DID
 *  bring cards restarts the ladder (the builder is moving — ask again soon,
 *  the legacy poller's "reset on progress"); only a page that brought nothing
 *  climbs it. No wait ⇒ 0. The delay is pageRetryDelayMs(attempt - 1). */
export function nextRetryAttempt(prevAttempt: number, backoff: boolean, added: number): number {
  if (!backoff) return 0;
  return added > 0 ? 1 : prevAttempt + 1;
}

export type PageFetchPhase = 'idle' | 'loading' | 'retrying' | 'failed';

/** What the deck slot shows once the user is past the last held card of a
 *  paged deck (ux-lead U3; never a "Finding more" state):
 *  - 'end': P30's end card, when the deck is fully delivered by the end rule
 *    above (`pool_exhausted` with `deck_id`; else complete and fully paged)
 *    and nothing is in flight or retrying (U3 row 4). Same card both ways.
 *  - 'offline': the Offline state (row 3a).
 *  - 'error': the recoverable error, "Couldn't load more trades" (row 3b):
 *    the job errored, or fetches keep failing or come back empty.
 *  - 'pending': the first request for the next page is in flight; the slot
 *    stays empty until it lands (no spinner, no copy). */
export type DeckEnd = 'end' | 'offline' | 'error' | 'pending';

export function deckEndState(s: PageEnvelope & {
  phase: PageFetchPhase;
  online: boolean;
}): DeckEnd {
  if (s.status === 'error') return 'error';
  if (deckFullyDelivered(s) && s.phase === 'idle') return 'end';
  if (!s.online) return 'offline';
  if (s.phase === 'retrying' || s.phase === 'failed') return 'error';
  return 'pending';
}
