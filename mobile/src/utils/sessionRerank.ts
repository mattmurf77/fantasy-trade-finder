// F4 — Session Re-rank (flag `deck.session_rerank`, PRD
// docs/plans/tiktok-discovery/prds/F4-session-rerank.md).
//
// Pure math for the deck's "responds in 3 swipes" behavior: after every
// disposition the REMAINING (unseen) cards re-sort against a short-lived
// session boost vector built from the last-k dispositions. No server calls,
// no persistence — the vector lives in a TradesScreen ref and dies with the
// deck (completion / regenerate / unmount / relaunch).
//
// This module is deliberately free of runtime imports (structural types
// only) so mobile/tests/check-session-rerank.js can transpile it with the
// project's typescript and run it under plain node — same idiom as
// feedbackBadge.ts.
//
// Contract highlights enforced here (guards; see rerankRemaining):
//   • Cards before the boundary index NEVER move — TradesScreen passes
//     boundary = dispositionedIndex + 2, so the top card and the peeked
//     next card are untouchable.
//   • Position-locked cards (likes-you pins, F3 retest cards, and F7's
//     future wildcard slot — see isPositionLocked) keep their exact index.
//   • The re-sort is stable: served order is the tiebreak, so a zero/equal
//     boost leaves the deck in served order (flag-on-but-no-signal is a
//     no-op reorder).

// ── Tunables (client-local; PRD F4 §1–2) ────────────────────────────────

/** η — bounded re-rank strength: newScore = servedScore × (1 + η·cos). */
export const SESSION_RERANK_ETA = 0.3;
/** Last-k window: only the k most recent dispositions feed the vector. */
export const SESSION_RERANK_LAST_K = 10;
/** Recency decay per subsequent card: weight × 0.8^(cards since). */
export const SESSION_RERANK_DECAY = 0.8;

/** Disposition rewards (PRD F4 §1). */
export const RERANK_WEIGHT_LIKE = 1;
export const RERANK_WEIGHT_LONG_DWELL_PASS = 0.3;
export const RERANK_WEIGHT_FAST_PASS = -0.5;
export const RERANK_WEIGHT_NOT_INTERESTED = -2;

/** Dwell thresholds for pass classification. The PRD suggests a per-
 *  complexity-bin 75th percentile; with no client-side dwell distribution
 *  yet, a flat 8s "they really considered it" / 2s "instant nope" split is
 *  the honest simple version (complexity binning deferred until F1 data
 *  exists to calibrate it). Passes between the two thresholds are neutral:
 *  they occupy a recency slot but contribute weight 0. */
export const RERANK_LONG_DWELL_MS = 8_000;
export const RERANK_FAST_PASS_MS = 2_000;

// ── Types ───────────────────────────────────────────────────────────────

/** Sparse attribute vector: attribute key → magnitude (all in [0, 1]). */
export type AttrVector = Record<string, number>;

export type RerankDisposition = 'like' | 'pass' | 'not_interested';

/** One recorded disposition. tradeId lets an undo pop the exact event. */
export interface RerankEvent {
  tradeId: string;
  attrs: AttrVector;
  weight: number;
}

/** Structural subset of shared/types#TradeCard this module reads — kept
 *  local (not imported) so the module stays transpile-and-run pure. Any
 *  TradeCard is assignable. */
export interface RerankCardLike {
  trade_id: string;
  give_players?: RerankPlayerLike[] | null;
  receive_players?: RerankPlayerLike[] | null;
  opponent_user_id?: string | null;
  give_value?: number | null;
  receive_value?: number | null;
  likesYou?: boolean;
  /** F3 (deck.fatigue): the ONE low-exposure retest of an expired decline
   *  window. Serve position is deliberate — never move it. */
  retest?: boolean;
  /** F7 (future wildcard/exploration slot): honored today so F7 needs no
   *  change here. */
  wildcard?: boolean;
}

export interface RerankPlayerLike {
  id?: string;
  position?: string | null;
  age?: number | null;
  pick_value?: number | null;
}

export interface RerankMove {
  trade_id: string;
  from: number;
  to: number;
}

export interface RerankResult<T extends RerankCardLike> {
  /** New deck order (same array reference iff nothing moved). */
  order: T[];
  /** Cards whose index changed, old → new. Empty ⇒ no reorder happened. */
  moves: RerankMove[];
}

// ── Attribute extraction (PRD F4 §1 "engineered attributes") ────────────
// Mirrors the spirit of the server's F1 features_json (server.py — shape,
// positions, value bands, pick involvement, partner) but is derived purely
// from the card payload the deck already holds. Client-local: these keys
// never leave the device, so no cross-client invariant is created.

function isPick(p: RerankPlayerLike): boolean {
  return p.position === 'PICK' || (p.pick_value != null && p.pick_value > 0);
}

function ageBand(age: number | null | undefined): string | null {
  if (typeof age !== 'number' || age <= 0) return null;
  if (age < 24) return 'young';
  if (age < 29) return 'prime';
  return 'vet';
}

/** Coarse 500-wide package-value band — same banding rule as the server's
 *  _signal_value_band, re-derived locally from the card totals. */
function valueBand(value: number | null | undefined): string | null {
  if (typeof value !== 'number' || !isFinite(value)) return null;
  const lo = Math.floor(value / 500) * 500;
  return `${lo}-${lo + 500}`;
}

function addSideAttrs(
  attrs: AttrVector,
  side: 'give' | 'receive',
  players: RerankPlayerLike[],
): void {
  if (players.length === 0) return;
  const frac = 1 / players.length;
  let hasPick = false;
  for (const p of players) {
    if (isPick(p)) {
      hasPick = true;
      continue; // picks carry no position/age signal
    }
    if (p.position) {
      const key = `pos:${side}:${p.position}`;
      attrs[key] = (attrs[key] ?? 0) + frac;
    }
    const band = ageBand(p.age);
    if (band) {
      const key = `age:${side}:${band}`;
      attrs[key] = (attrs[key] ?? 0) + frac;
    }
  }
  if (hasPick) attrs[`pick:${side}`] = 1;
}

/** Derive the per-card attribute vector from the served payload.
 *  Keys (all values in [0,1]):
 *    shape:<G>x<R>            one-hot package shape ("2x1")
 *    shapeclass:consolidate | split | swap
 *    pos:<side>:<POS>         position share of that side (players only)
 *    age:<side>:<band>        age-band share (young <24 / prime / vet 29+)
 *    pick:<side>              1 when the side includes a draft pick
 *    partner:<user_id>        counterparty one-hot
 *    valueband:<side>:<lo-hi> 500-wide card-total band (absent w/o totals)
 */
export function extractCardAttributes(card: RerankCardLike): AttrVector {
  const attrs: AttrVector = {};
  const give = card.give_players ?? [];
  const receive = card.receive_players ?? [];
  const g = give.length;
  const r = receive.length;
  if (g > 0 || r > 0) {
    attrs[`shape:${g}x${r}`] = 1;
    attrs[`shapeclass:${g > r ? 'consolidate' : g < r ? 'split' : 'swap'}`] = 1;
  }
  addSideAttrs(attrs, 'give', give);
  addSideAttrs(attrs, 'receive', receive);
  if (card.opponent_user_id) attrs[`partner:${card.opponent_user_id}`] = 1;
  const gb = valueBand(card.give_value);
  if (gb) attrs[`valueband:give:${gb}`] = 1;
  const rb = valueBand(card.receive_value);
  if (rb) attrs[`valueband:receive:${rb}`] = 1;
  return attrs;
}

// ── Boost vector (PRD F4 §1) ────────────────────────────────────────────

/** Reward for a disposition. Passes split on dwell: long-dwell (they
 *  really considered it) is mildly positive, an instant flick is negative,
 *  in-between is neutral (0 — still consumes a recency slot). Unknown
 *  dwell (undefined) is treated as neutral. */
export function dispositionWeight(
  disposition: RerankDisposition,
  dwellMs?: number,
): number {
  if (disposition === 'like') return RERANK_WEIGHT_LIKE;
  if (disposition === 'not_interested') return RERANK_WEIGHT_NOT_INTERESTED;
  if (typeof dwellMs !== 'number') return 0;
  if (dwellMs > RERANK_LONG_DWELL_MS) return RERANK_WEIGHT_LONG_DWELL_PASS;
  if (dwellMs < RERANK_FAST_PASS_MS) return RERANK_WEIGHT_FAST_PASS;
  return 0;
}

/** Fold the last-k events into one recency-weighted vector:
 *  Σ weightᵢ × DECAY^(events after i) × attrsᵢ. Callers keep `events`
 *  trimmed to SESSION_RERANK_LAST_K; this also self-trims defensively. */
export function buildBoostVector(events: readonly RerankEvent[]): AttrVector {
  const window = events.slice(-SESSION_RERANK_LAST_K);
  const boost: AttrVector = {};
  const n = window.length;
  for (let i = 0; i < n; i++) {
    const e = window[i];
    if (e.weight === 0) continue;
    const w = e.weight * Math.pow(SESSION_RERANK_DECAY, n - 1 - i);
    for (const key of Object.keys(e.attrs)) {
      boost[key] = (boost[key] ?? 0) + w * e.attrs[key];
    }
  }
  return boost;
}

// ── Similarity ──────────────────────────────────────────────────────────

export function cosineSimilarity(a: AttrVector, b: AttrVector): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (const key of Object.keys(a)) {
    const av = a[key];
    na += av * av;
    const bv = b[key];
    if (bv !== undefined) dot += av * bv;
  }
  for (const key of Object.keys(b)) nb += b[key] * b[key];
  if (na === 0 || nb === 0) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

export function isZeroVector(v: AttrVector): boolean {
  for (const key of Object.keys(v)) if (v[key] !== 0) return false;
  return true;
}

// ── Position locks (contract §stability guards) ─────────────────────────

/** Cards the re-rank may NEVER move, wherever they sit:
 *   • likes-you pins (server pinned them; the mirror like is time-real)
 *   • F3 retest cards (`retest: true` served TODAY — their low-exposure
 *     position is the whole point of the retest)
 *   • F7 wildcard/exploration cards (`wildcard: true` — future; honored
 *     now so F7 lands without touching this module)
 *  This is the guard hook F7 should extend if its marker differs. */
export function isPositionLocked(card: RerankCardLike): boolean {
  return card.likesYou === true || card.retest === true || card.wildcard === true;
}

// ── The re-rank itself (PRD F4 §2–3) ────────────────────────────────────

/**
 * Stable re-sort of the cards at index ≥ `boundary` (callers pass
 * dispositionedIndex + 2 — the top card and the peeked next card never
 * move). Position-locked cards keep their exact index; the remaining
 * cards re-sort by
 *
 *     newScore = servedIndexScore × (1 + η·cos(attrs, boost))
 *
 * where servedIndexScore = 1 / (servedIndex + 1) (reciprocal of the
 * order the server streamed the card in — `servedIndex` map, assigned at
 * first sight and never reassigned) and served order breaks ties. With a
 * zero boost vector every multiplier is 1 and the sort reproduces served
 * order exactly ⇒ `moves` is empty and the input array is returned as-is.
 *
 * Cards missing from `servedIndex` (a mid-update race) fall back to their
 * current index — approximately their served position.
 */
export function rerankRemaining<T extends RerankCardLike>(
  cards: readonly T[],
  boundary: number,
  boost: AttrVector,
  servedIndex: ReadonlyMap<string, number>,
): RerankResult<T> {
  const start = Math.max(0, boundary);
  if (start >= cards.length - 1 || isZeroVector(boost)) {
    return { order: cards as T[], moves: [] };
  }

  const head = cards.slice(0, start);
  const tail = cards.slice(start);

  const movable: { card: T; served: number; score: number }[] = [];
  for (let i = 0; i < tail.length; i++) {
    const card = tail[i];
    if (isPositionLocked(card)) continue;
    const served = servedIndex.get(card.trade_id) ?? start + i;
    const sim = cosineSimilarity(extractCardAttributes(card), boost);
    movable.push({
      card,
      served,
      score: (1 / (served + 1)) * (1 + SESSION_RERANK_ETA * sim),
    });
  }
  movable.sort((a, b) => b.score - a.score || a.served - b.served);

  // Rebuild the tail: locked cards keep their slot, movable cards fill the
  // remaining slots in re-scored order.
  const newTail: T[] = new Array(tail.length);
  let mi = 0;
  for (let i = 0; i < tail.length; i++) {
    newTail[i] = isPositionLocked(tail[i]) ? tail[i] : movable[mi++].card;
  }

  const moves: RerankMove[] = [];
  for (let i = 0; i < tail.length; i++) {
    if (newTail[i].trade_id !== tail[i].trade_id) {
      // old index of the card now sitting at absolute index start+i
      const from = start + tail.findIndex((c) => c.trade_id === newTail[i].trade_id);
      moves.push({ trade_id: newTail[i].trade_id, from, to: start + i });
    }
  }
  if (moves.length === 0) return { order: cards as T[], moves };
  return { order: [...head, ...newTail], moves };
}
