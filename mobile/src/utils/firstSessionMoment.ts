// F9 — First-Session Win (flag `deck.first_session`, PRD
// docs/plans/tiktok-discovery/prds/F9-first-session-win.md).
//
// Pure math for the mid-deck ADAPTATION MOMENT: after ≥
// FIRST_SESSION_MIN_DISPOSITIONS dispositions in the user's first deck
// session, if ≥ FIRST_SESSION_MIN_SHARED_LIKES likes share a dominant
// attribute AND at least one unseen card ahead carries that attribute, one
// inline card renders between deck cards ("Noticed you're liking
// <phrase> — …"). The trigger conditions here are deliberately the literal
// truth conditions of the card's claim (PRD: never claim adaptation that
// didn't happen):
//   - "Noticed you're liking X"   ⇔ ≥3 of this session's likes share X;
//   - "more of those ahead"       ⇔ ≥1 remaining card carries X (and, per
//     the caller's gate, deck.session_rerank is ON so the deck literally
//     re-ranks toward X);
//   - the descriptive variant ("there are more in this deck") makes only
//     the remaining-cards claim — the honest fallback when session_rerank
//     is off (the deck was already generated; nothing adapts).
//
// Attribute keys are the F4 session-rerank space (utils/sessionRerank.ts
// extractCardAttributes) — client-local, never leave the device except as
// the single `attribute` analytics prop. Only HUMAN-PHRASEABLE keys are
// eligible for dominance (value bands and give-side age/position keys are
// excluded — "deals sending away prime-age value-band 1500-2000" is not a
// sentence); an unphraseable dominant signal simply shows no card.
//
// Zero runtime imports beyond sessionRerank's pure module — same
// transpile-and-run idiom as sessionRerank.ts/feedbackBadge.ts.

import { extractCardAttributes, type AttrVector, type RerankCardLike } from './sessionRerank';

// ── Tunables (client-local; PRD F9 §2) ──────────────────────────────────

/** Dispositions (like/pass/flag) before the moment may trigger. */
export const FIRST_SESSION_MIN_DISPOSITIONS = 5;
/** Likes that must share the dominant attribute. */
export const FIRST_SESSION_MIN_SHARED_LIKES = 3;
/** An attribute "counts" for a like when its magnitude is ≥ this (side
 *  shares are fractional; binary keys are 1). */
export const FIRST_SESSION_ATTR_MIN = 0.5;

export interface FirstSessionLike {
  attrs: AttrVector;
  /** Counterparty display handle, for `partner:*` phrasing. */
  opponentUsername?: string;
  opponentUserId?: string;
}

export interface AdaptationSignal {
  /** Dominant attribute key (sessionRerank key space). */
  attribute: string;
  /** Human phrase for the card copy ("pick-heavy returns", …). */
  phrase: string;
  /** How many session likes share the attribute. */
  likes: number;
}

// ── Phrasing ────────────────────────────────────────────────────────────
// Priority-ordered: when several attributes tie on like-count, the earlier
// pattern wins (shape reads clearest, then picks, then landed positions,
// then age bands, then partner).

const POSITION_PHRASE: Record<string, string> = {
  QB: 'trades that land a QB',
  RB: 'trades that land RBs',
  WR: 'trades that land WRs',
  TE: 'trades that land a TE',
};

type PhraseRule = { match: (key: string) => boolean; rank: number };

const PHRASE_RULES: PhraseRule[] = [
  { match: (k) => k === 'shapeclass:consolidate', rank: 0 },
  { match: (k) => k === 'shapeclass:split', rank: 1 },
  { match: (k) => k === 'shapeclass:swap', rank: 2 },
  { match: (k) => k === 'pick:receive', rank: 3 },
  { match: (k) => k === 'pick:give', rank: 4 },
  { match: (k) => k.startsWith('pos:receive:') && !!POSITION_PHRASE[k.slice(12)], rank: 5 },
  { match: (k) => k === 'age:receive:young', rank: 6 },
  { match: (k) => k === 'age:receive:vet', rank: 7 },
  { match: (k) => k.startsWith('partner:'), rank: 8 },
];

function phraseRank(key: string): number | null {
  for (const r of PHRASE_RULES) if (r.match(key)) return r.rank;
  return null; // not human-phraseable → ineligible for dominance
}

export function phraseForAttribute(
  key: string,
  likes: readonly FirstSessionLike[],
): string | null {
  if (key === 'shapeclass:consolidate') return '2-for-1 consolidation deals';
  if (key === 'shapeclass:split') return 'deals that split one player into two';
  if (key === 'shapeclass:swap') return 'one-for-one swaps';
  if (key === 'pick:receive') return 'pick-heavy returns';
  if (key === 'pick:give') return 'deals that send picks away';
  if (key.startsWith('pos:receive:')) return POSITION_PHRASE[key.slice(12)] ?? null;
  if (key === 'age:receive:young') return 'deals bringing back young players';
  if (key === 'age:receive:vet') return 'deals for proven vets';
  if (key.startsWith('partner:')) {
    const uid = key.slice(8);
    const name = likes.find(
      (l) => l.opponentUserId === uid && l.opponentUsername,
    )?.opponentUsername;
    return name ? `trades with @${name}` : null;
  }
  return null;
}

// ── Dominance ───────────────────────────────────────────────────────────

/** The dominant liked attribute: the phraseable key shared (magnitude ≥
 *  FIRST_SESSION_ATTR_MIN) by the most likes — ties broken by phrase-rule
 *  priority. Null when no phraseable key reaches `minShared`. */
export function findDominantLikedAttribute(
  likes: readonly FirstSessionLike[],
  minShared: number = FIRST_SESSION_MIN_SHARED_LIKES,
): AdaptationSignal | null {
  const counts = new Map<string, number>();
  for (const like of likes) {
    for (const key of Object.keys(like.attrs)) {
      if (like.attrs[key] >= FIRST_SESSION_ATTR_MIN && phraseRank(key) !== null) {
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
    }
  }
  let best: { key: string; n: number; rank: number } | null = null;
  for (const [key, n] of counts) {
    if (n < minShared) continue;
    const rank = phraseRank(key)!;
    if (!best || n > best.n || (n === best.n && rank < best.rank)) {
      best = { key, n, rank };
    }
  }
  if (!best) return null;
  const phrase = phraseForAttribute(best.key, likes);
  if (!phrase) return null;
  return { attribute: best.key, phrase, likes: best.n };
}

/** True when `card` carries the attribute (the "more of those ahead"
 *  truth condition — callers require ≥1 match among the unseen cards). */
export function cardMatchesAttribute(card: RerankCardLike, attribute: string): boolean {
  const v = extractCardAttributes(card)[attribute];
  return typeof v === 'number' && v >= FIRST_SESSION_ATTR_MIN;
}
