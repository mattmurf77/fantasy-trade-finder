import { apiRequest, ApiError } from './client';
import { isInviteId } from '../utils/inviteId';

/** The mint body's `surface` (PRD §8.1). The five mobile values are the
 *  InviteSurface set in components/InviteLeaguematesBanner verbatim, so the
 *  mapping is identity; `web_invite` is the web modal's (FR-5). */
export type MintSurface =
  | 'league_home'
  | 'matches_empty'
  | 'trades_banner'
  | 'members_overlay'
  | 'notif_empty'
  | 'web_invite';

export type MintResult =
  | { outcome: 'ok'; invite_id: string }
  | { outcome: 'failed' | 'timeout' | 'rate_limited' };

/** POST /api/invite/token — mint a per-share invite id (referral FR-1).
 *  404 while `growth.referral_ledger` is off server-side; 403 for demo,
 *  unverified or non-member sessions; 429 at the per-inviter daily cap.
 *
 *  Contract: NEVER throws and never rejects, like api/calc's
 *  createSharePackage. Every failure comes back as an outcome so the share
 *  still opens with the league-only link (PRD §7.2 "mint failed") and
 *  `invite_shared.mint_outcome` is truthful.
 *
 *  `signal` is the caller's deadline (the banner aborts at 2 s): an abort,
 *  or the client's own request deadline, is `timeout`. A 2xx without a
 *  well-formed id is `failed`, so a bad id can never reach a URL. */
export async function mintInviteId(
  args: { leagueId: string; surface: MintSurface },
  signal?: AbortSignal,
): Promise<MintResult> {
  try {
    const r = await apiRequest<{ invite_id?: unknown }>('/api/invite/token', {
      method: 'POST',
      signal,
      body: { league_id: args.leagueId, surface: args.surface },
    });
    if (signal?.aborted) return { outcome: 'timeout' };
    const id = r?.invite_id;
    return isInviteId(id) ? { outcome: 'ok', invite_id: id } : { outcome: 'failed' };
  } catch (e) {
    if (signal?.aborted || (e as { name?: string } | null)?.name === 'AbortError') {
      return { outcome: 'timeout' };
    }
    if (e instanceof ApiError) {
      if (e.isTimeout) return { outcome: 'timeout' };
      if (e.status === 429) return { outcome: 'rate_limited' };
    }
    // 400 · 401 · 403 · 404 (flag dark / route not deployed) · 5xx · offline
    return { outcome: 'failed' };
  }
}
