// matchMoment.ts — the deck's "you matched" moment, read off the swipe reply.
//
// POST /api/trades/swipe answers a like that completes a mutual match with
// `{ matched: true, match_id, partner_name, my_give, my_receive }`
// (backend/server.py swipe_trade). Until 2026-11-22 the deck only kept the
// match id for the share link: the user who completed a match on a
// "They're interested" card saw "Liked" and "1 liked trade awaiting their
// swipe", while Matches already listed "New match with @…" for both owners
// (Release sim pass). The moment is now a toast whose action lands on the
// match through the same Matches arrival a match push uses
// (`{ match_id, src, ts }`: scroll to the row and mark it, MatchesScreen R2).
//
// Pure and import-free: tests/check-match-moment.js transpiles and runs it.

export interface MatchMoment {
  matchId: string;
  /** The partner's handle, without the "@"; null when neither the reply
   *  nor the card names them. */
  partner: string | null;
}

/** The match a swipe reply reports, or null when the like did not match
 *  (or the reply is not a match reply). `fallbackPartner` is the card's own
 *  opponent handle, used when the reply carries no name. */
export function matchMomentFrom(res: unknown, fallbackPartner?: string | null): MatchMoment | null {
  const r = res as { matched?: unknown; match_id?: unknown; partner_name?: unknown } | null;
  if (!r || r.matched !== true) return null;
  if (typeof r.match_id !== 'number' && typeof r.match_id !== 'string') return null;
  const matchId = String(r.match_id);
  if (!matchId) return null;
  // The server falls back to the partner's raw user id when the card has no
  // handle (a held card's partner is redacted): never print an id.
  const named = typeof r.partner_name === 'string' && r.partner_name && !/^\d+$/.test(r.partner_name)
    ? r.partner_name : null;
  return { matchId, partner: fallbackPartner || named || null };
}

/** The toast line. Matches titles the same row "New match with @…". */
export function matchMomentLine(m: MatchMoment): string {
  return m.partner ? `New match with @${m.partner}` : 'New trade match';
}

/** The toast's action label: opens the match on the Matches tab. */
export const MATCH_MOMENT_ACTION = 'View match';

/** Long enough to read and reach the action; the undo window is 5 s. */
export const MATCH_MOMENT_HOLD_MS = 6000;
