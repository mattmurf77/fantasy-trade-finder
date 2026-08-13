// Share-link ladder (audit P1-1 / P1-2).
//
// Every share artifact this app produces must carry a link back to the app.
// This module is the ONE place a mobile trade-share URL is built, and it
// resolves the best link it can actually deliver, degrading rather than
// failing:
//
//   rung A `package` — <base>/s/p/<short_id>?ref=<user>
//        A real server object minted by POST /api/share/package
//        (backend/server.py:16999 create_share_package_route). Renders the
//        trade as an OG card with a "Build your own trade" CTA.
//   rung B `ref`     — <base>/?ref=<user>       (today's behaviour)
//   rung C `root`    — <base>/                  (today's signed-out behaviour)
//
// The ladder NEVER throws and NEVER resolves to an empty url. Callers can
// concatenate `.url` into a message body unconditionally.

import { createSharePackage } from '../api/calc';
import { getBaseUrl } from '../api/client';

/** Which client surface produced the share. Closed enum — mirrors the
 *  `surface` prop registered in backend/analytics_taxonomy.py. Adding a
 *  value requires a taxonomy change first, or the prop is stripped
 *  silently at ingest.
 *
 *  Ranking/tier sharing is deliberately absent: it is not a product
 *  surface (DECISIONS-p1.md D-P1-12). */
export type ShareSurface = 'calc_live' | 'calc_in_league' | 'trades_liked';

/** Which rung of the ladder produced the URL. Also the on-screen testID
 *  suffix on the calculator's link row. */
export type ShareRung = 'package' | 'ref' | 'root';

/** Why rung A was or wasn't reached. `skipped` means no mint was attempted
 *  (flag off / no assets / over the side cap / picks present), so NO
 *  share_package_created event is fired for it. */
export type MintOutcome = 'ok' | 'rate_limited' | 'demo' | 'failed';

export interface ResolvedShareUrl {
  /** Absolute, always non-empty, always safe to put in a message. */
  url: string;
  rung: ShareRung;
  outcome: MintOutcome | 'skipped';
}

export interface ResolveArgs {
  giveIds: string[];
  receiveIds: string[];
  username?: string | null;
  /** growth.share_landing, read by the caller via useFlag. */
  enabled: boolean;
  /** useSession's isDemo — the server refuses demo sessions with a 400. */
  isDemo: boolean;
  surface: ShareSurface;
  /** PR-14: true when either side holds a league draft pick. The rich
   *  landing renders picks as "Unknown player" (backend/og_image.py's
   *  load_players_by_ids cannot resolve a pick_id), so those packages
   *  fall back to rung B.
   *
   *  Computed by the HOST from data it already holds (`pos === 'PICK'`),
   *  never sniffed from the id string: a pick_id is
   *  {league}_{season}_{round}_{roster} and league ids are bare digits
   *  too, so there is no shape that is safely a pick and not a player. */
  hasPickAssets: boolean;
  signal?: AbortSignal;
  /** Injected so this module has no import cycle with api/events.ts.
   *  Called once per mint attempt that REACHED the server (plus the demo
   *  short-circuit), never on a cache hit. */
  onOutcome?: (outcome: MintOutcome, giveN: number, receiveN: number) => void;
}

/** Mirrors _SHARE_PACKAGE_SIDE_MAX (backend/server.py:16979). Spending a
 *  request the server will 400 is worse than skipping the rung. */
const SIDE_MAX = 5;

/** In-memory only, no TTL: a shared_packages row is kept indefinitely, so a
 *  stale entry is never wrong, only old — and it dies with the process. */
const MINT_CACHE = new Map<string, ResolvedShareUrl>();

function enc(s: string): string {
  return encodeURIComponent(s);
}

/** Rung B/C. Pure, synchronous, never throws, never empty. Byte-identical
 *  to the URLs TradeCalculatorScreen and TradesScreen built before P1-1. */
export function refShareUrl(username?: string | null): ResolvedShareUrl {
  const u = String(username ?? '').trim();
  const base = getBaseUrl();
  return u
    ? { url: `${base}/?ref=${enc(u)}`, rung: 'ref', outcome: 'skipped' }
    : { url: `${base}/`, rung: 'root', outcome: 'skipped' };
}

/** Cache key for a package. ORDER-SENSITIVE on purpose: the server stores
 *  the arrays as given and the OG card renders them in order, so [A,B] and
 *  [B,A] are two different artifacts. */
export function packageCacheKey(giveIds: string[], receiveIds: string[]): string {
  return `${giveIds.join('+')}|${receiveIds.join('+')}`;
}

/** Test/debug seam only — clears the in-memory mint cache. */
export function __resetShareLinkCache(): void {
  MINT_CACHE.clear();
}

/** The A→B→C ladder. NEVER throws, NEVER returns an empty url. */
export async function resolveShareUrl(args: ResolveArgs): Promise<ResolvedShareUrl> {
  // `floor` is what EVERY failure path returns — computed first so no
  // branch below can produce a link-free result.
  const floor = refShareUrl(args.username);
  try {
    // 1. growth.share_landing off → byte-identical to pre-P1-1 behaviour.
    if (!args.enabled) return floor;

    // 2. Demo sessions are refused server-side (server.py:17011) — don't
    //    spend the call, but DO report the outcome so the funnel can tell
    //    "demo user" apart from "mint broken".
    if (args.isDemo) {
      args.onOutcome?.('demo', args.giveIds.length, args.receiveIds.length);
      return floor;
    }

    // 3/4. Server-side shape rules mirrored: at least one id overall, at
    //      most SIDE_MAX per side. No request made → no outcome to report.
    if (args.giveIds.length === 0 && args.receiveIds.length === 0) return floor;
    if (args.giveIds.length > SIDE_MAX || args.receiveIds.length > SIDE_MAX) return floor;

    // 5. PR-14 — draft picks render "Unknown player" on the landing.
    if (args.hasPickAssets) return floor;

    // 6. Cache hit: no request, and deliberately NO event — the event
    //    counts attempts that reached the server, so the mint rate and the
    //    share rate stay distinguishable.
    const key = packageCacheKey(args.giveIds, args.receiveIds);
    const hit = MINT_CACHE.get(key);
    if (hit) return hit;

    // 7. Mint. createSharePackage never throws (api/calc.ts).
    const res = await createSharePackage(args.giveIds, args.receiveIds, args.signal);
    args.onOutcome?.(res.outcome, args.giveIds.length, args.receiveIds.length);
    if (res.outcome !== 'ok') return floor;

    const u = String(args.username ?? '').trim();
    const resolved: ResolvedShareUrl = {
      url: `${getBaseUrl()}${res.url}${u ? `?ref=${enc(u)}` : ''}`,
      rung: 'package',
      outcome: 'ok',
    };
    MINT_CACHE.set(key, resolved);
    return resolved;
  } catch {
    // Nothing above is allowed to break a share. Degrade, never fail.
    return floor;
  }
}

/** Strip the scheme for on-screen/on-card display. The link itself is
 *  always the full absolute URL. */
export function displayUrl(url: string): string {
  return url.replace(/^https?:\/\//, '');
}
