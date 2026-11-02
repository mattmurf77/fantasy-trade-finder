// Trade share links (build O8). A mutual match is shared through a 128-bit
// token the SERVER mints — never through the sequential trade_matches.id,
// which let anyone walk /s/trade/<id> and read every match. Server side:
// backend/server.py create_share_trade_route (POST /api/share/trade).

import { ApiError, apiRequest } from './client';

/** POST /api/share/trade — mint (or get back) the caller's share token for a
 *  mutual match. Idempotent per (match, sharer): sharing the same match again
 *  returns the same link.
 *  404 `not_found` for a non-participant, a missing match or a malformed id
 *  (deliberately indistinguishable), and while `growth.share_landing` is
 *  dark; 400 `demo_session` for demo users; 429 `rate_limited` at 30
 *  mints/user/hour; 401 signed out; 403 unverified session.
 *
 *  Contract (mirrors createSharePackage in api/calc.ts): NEVER throws and
 *  never rejects. Every failure comes back as an outcome so the caller can
 *  fall back to the package mint, then the root. */
export async function createTradeShare(
  matchId: string | number,
  signal?: AbortSignal,
): Promise<
  | { outcome: 'ok'; token: string; url: string; og_image: string }
  | { outcome: 'rate_limited' | 'demo' | 'failed' }
> {
  try {
    const r = await apiRequest<{
      ok: boolean;
      token: string;
      url: string;
      og_image: string;
    }>('/api/share/trade', {
      method: 'POST',
      signal,
      body: { match_id: matchId },
    });
    if (!r?.ok || !r.url || !r.token) return { outcome: 'failed' };
    return { outcome: 'ok', token: r.token, url: r.url, og_image: r.og_image };
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 429) return { outcome: 'rate_limited' };
      if (e.status === 400 && (e.body as { error?: string } | null)?.error === 'demo_session') {
        return { outcome: 'demo' };
      }
    }
    // 404 not_found / flag dark · 401 signed out · 403 unverified · 5xx · offline · abort
    return { outcome: 'failed' };
  }
}
