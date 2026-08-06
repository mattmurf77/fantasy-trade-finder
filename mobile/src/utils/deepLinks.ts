import * as Linking from 'expo-linking';
import { getActionFromState, getStateFromPath } from '@react-navigation/native';
import { useSession } from '../state/useSession';
import { useFeatureFlags } from '../state/useFeatureFlags';
import { navigationRef } from '../navigation/RootNav';

// ── Bundle 8 + teardown PRD 01-04: Deep link handling ─────────────────────
// Legacy (flag `ux.deeplink_router_v2` OFF — the shipping default):
//   • ?ref=<username>  — referral attribution. Stash in useSession so the
//     next /api/session/init carries invited_by. Web uses the same param
//     name (`ref`) and the same backend column.
//   • /u/<username>    — public profile. We navigate to the Profile screen
//     in the auth stack; react-navigation's Linking config maps the same
//     path to the same screen so cold-start tapped links land there too.
//
// V2 (flag ON): one route table (V2_LINKING) drives BOTH react-navigation's
// `linking` prop (RootNav) and this imperative handler, so push taps and
// share links resolve through a single code path. Unroutable paths land on
// home with a "Couldn't open that link" toast instead of silently no-oping,
// and navigation intents that arrive before the container is ready are
// buffered and replayed from RootNav's onReady (fixes the silent drop the
// teardown flagged at RootNav.tsx:139).
//
// Accepts both the app's custom scheme (dtf://…) and the production
// universal-link host. Tolerant of trailing slashes + uppercase chars.
//
// NOTE (import cycle): this module imports `navigationRef` from RootNav and
// RootNav imports the v2 linking config from here. Same documented pattern
// as TopBar ← RootNav — `navigationRef` is a top-level const only *read*
// lazily inside functions below, never at module-eval time. Keep it that way.

/** True if the navigation container is mounted and ready to handle a navigate(). */
function _navReady(): boolean {
  try {
    return navigationRef.isReady();
  } catch {
    return false;
  }
}

// ── Nav-intent buffer (PRD 01-04 item 4) ──────────────────────────────────
// Intents that arrive before the container is ready (cold-start push taps,
// early deep links) are queued and replayed by RootNav's onReady. Only the
// flag-ON paths enqueue, so with all flags off this stays empty and the
// flush is a no-op.
const _pendingNav: Array<() => void> = [];

/** Run `fn` now if navigation is ready, otherwise buffer it for replay. */
export function runWhenNavReady(fn: () => void): void {
  if (_navReady()) {
    fn();
    return;
  }
  _pendingNav.push(fn);
}

/** Called from RootNav's onReady: replay buffered navigation intents. */
export function flushPendingNavIntents(): void {
  while (_pendingNav.length) {
    const fn = _pendingNav.shift()!;
    try {
      fn();
    } catch {
      /* a single bad intent must not eat the rest of the queue */
    }
  }
}

// ── Unroutable-link fallback toast (PRD 01-04 item 3) ─────────────────────
// RootNav registers a notifier that shows the "Couldn't open that link"
// toast; kept as a callback so this module stays render-free.
let _linkFallbackNotify: (() => void) | null = null;
let _lastFallbackAt = 0;

export function setLinkFallbackNotifier(fn: (() => void) | null): void {
  _linkFallbackNotify = fn;
}

function _notifyLinkFallback(): void {
  // getInitialURL + the url event listener can both deliver the same URL on
  // cold start — debounce so the user sees one toast, not two.
  const now = Date.now();
  if (now - _lastFallbackAt < 1500) return;
  _lastFallbackAt = now;
  _linkFallbackNotify?.();
}

// ── V2 route table (PRD 01-04 item 1) ─────────────────────────────────────
// Single source of truth for URL-addressable screens. Consumed by:
//   • RootNav's `linking` prop when `ux.deeplink_router_v2` is on
//   • handleDeepLink below (warm-start URL events + fallback detection)
//   • routeNotificationTap (push taps + bell-row taps, `notif.tap_routing_v2`)
// Param naming: Matches uses `match_id` (matches the push payload key), so
// one contract reaches MatchesScreen from links, pushes, and bell rows.
const V2_SCREENS = {
  SignIn: 'signin',
  LeaguePicker: 'leagues',
  Settings: 'settings',
  Profile: 'u/:username',
  // Root-stack league-wide surfaces (#142/#143) — pushed over the tabs.
  LeagueSummary: 'app/league/summary',
  FreeAgents: 'app/league/free-agents',
  // rookie-draft M4. Addressable even while `draft.room` is off: the flag
  // gates the League tab's ENTRY TILE, not the route, and a link that
  // 404s at the API renders the room's honest error state rather than a
  // dead path.
  //
  // PLACEMENT WAVE (option A′): `DraftRoom` is now registered in TWO places
  // — here on the root stack, and inside the seasonal Draft tab's stack.
  // This entry stays the ONE canonical URL and always resolves to the
  // ROOT-stack registration, so `app/league/draft-room` behaves identically
  // whether the tab is present or hidden: it pushes the room over the tabs
  // and Back returns where the user was. The tab's copy deliberately has NO
  // path of its own — two paths for one screen is how a link starts
  // resolving differently depending on the season.
  DraftRoom: 'app/league/draft-room',
  Main: {
    path: 'app',
    screens: {
      Rank: {
        path: 'rank',
        screens: {
          RankHome: 'home',
          Trios: 'trios',
          Anchors: 'anchors',
          Tiers: 'tiers',
          QuickSetTiers: 'quickset',
          QuickRank: 'quickrank',
          ManualRanks: 'ranks',
          // rookie-draft M2 — the consolidated cross-position rookie view.
          // Addressable like every other rank surface; the screen itself
          // renders an honest unavailable state when `ranks.rookie_subset`
          // is off (there is no in-app entry point in that state).
          RookieRanks: 'rookies',
          Trends: 'trends',
        },
      },
      Trades: {
        path: 'trades',
        screens: {
          TradesHome: '',
          // FB #156 — the deck reached from the finder hub per mode (only
          // registered when flag `trades.finder_hub` is on; harmless as a
          // path otherwise).
          TradeDeck: 'finder',
          Portfolio: 'portfolio',
          TradeCalculator: 'calculator',
        },
      },
      Matches: 'matches/:match_id?',
      // #181 — the League tab is a stack: rankings at the root (the tab's
      // primary page), the classic league page pushed as LeagueHome. A bare
      // app/league lands on the rankings root. The legacy root-stack
      // LeagueSummary path above still resolves for old share links.
      League: {
        path: 'league',
        screens: {
          LeagueRankings: '',
          LeagueHome: 'home',
        },
      },
    },
  },
} as const;

const V2_CONFIG = { screens: V2_SCREENS } as any;

// ── Universal-link aliases (FB #239) ──────────────────────────────────────
// The AASA file claims the web share paths (/s/*) so iOS opens the app
// instead of Safari/the App Store when it's installed. Those are web-first
// URLs with no screen of their own, so map them onto existing routes here
// rather than in V2_SCREENS (a screen can only own one path):
//   /s/trade/<match_id> → app/matches/<match_id>  (match share landing)
//   /s/p/<short_id>     → app/trades              (package share landing)
// Applied in BOTH resolution paths: react-navigation's `linking` config
// (cold start) via the getStateFromPath override below, and _routePathV2
// (warm-start url events through handleDeepLink).
export function rewriteUniversalPath(pathWithQuery: string): string {
  const qi = pathWithQuery.search(/[?#]/);
  const rawPath = qi === -1 ? pathWithQuery : pathWithQuery.slice(0, qi);
  const suffix = qi === -1 ? '' : pathWithQuery.slice(qi);
  const path = rawPath.replace(/^\/+/, '').replace(/\/+$/, '');
  const trade = /^s\/trade\/([^/?#]+)$/i.exec(path);
  if (trade) return `app/matches/${trade[1]}${suffix}`;
  if (/^s\/p\/[^/?#]+$/i.test(path)) return `app/trades${suffix}`;
  return pathWithQuery;
}

/** Full `linking` object for NavigationContainer when the v2 flag is on. */
export function getLinkingV2() {
  return {
    prefixes: [Linking.createURL('/'), 'https://fantasy-trade-finder.onrender.com'],
    config: V2_CONFIG,
    // Cold-start universal links arrive here as a path (+query); alias the
    // web-only share paths before the default resolver sees them.
    getStateFromPath: (path: string, options?: any) =>
      getStateFromPath(rewriteUniversalPath(path), options),
  };
}

/** Resolve a path (+query) through the v2 table and dispatch the resulting
 *  navigate action. Returns false when the path matches nothing. */
function _routePathV2(pathWithQuery: string): boolean {
  try {
    const state = getStateFromPath(rewriteUniversalPath(pathWithQuery), V2_CONFIG);
    if (!state) return false;
    const action = getActionFromState(state as any, V2_CONFIG);
    if (!action) return false;
    navigationRef.dispatch(action as any);
    return true;
  } catch {
    return false;
  }
}

/** Rebuild a query string from expo-linking's parsed queryParams. */
function _buildQuery(qp: Record<string, unknown> | null | undefined): string {
  if (!qp) return '';
  const parts: string[] = [];
  for (const [k, v] of Object.entries(qp)) {
    const val = Array.isArray(v) ? v[0] : v;
    if (typeof val === 'string') {
      parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(val)}`);
    }
  }
  return parts.length ? `?${parts.join('&')}` : '';
}

// ── Notification tap routing (S5 PRD-02, flag `notif.tap_routing_v2`) ─────
// V2 kind → destination map. Mirrors the legacy sets inline in
// usePushNotifications (which stay untouched for the flag-off path) and adds
// `bundle_summary` — the morning quiet-hours digest previously matched no
// set and performed zero navigation.
const V2_MATCH_KINDS = new Set([
  'trade_match', 'new_match', 'first_match', 'match_accepted',
  'match_expiring', 'counter_offer',
  'weekly_digest', 'pending_review',
  'winback_matches', 'winback_dormant', 'season_start',
  'bundle_summary',
]);
const V2_LEAGUE_KINDS = new Set([
  'league_member_joined', 'league_member_unlocked_trades',
]);
const V2_RANK_KINDS = new Set(['finish_ranking']);
// F10 (flag deck.replenishment): the weekly fresh-deck push lands on the
// Trades tab (hub home when trades.finder_hub is on, the deck otherwise —
// where the pre-generated deck is served from the job cache). Inert while
// the backend flag is off: the kind is never pushed.
const V2_TRADE_KINDS = new Set(['deck_replenished']);

export type NotificationTab = 'Matches' | 'League' | 'Rank' | 'Trades';

export interface NotificationTarget {
  tab: NotificationTab;
  matchId?: string | number;
}

/** Map a push/inbox payload (`data.type` = backend push kind) to an in-app
 *  destination. Returns null for unknown kinds (no navigation). */
export function resolveNotificationTarget(
  data: Record<string, unknown> | null | undefined,
): NotificationTarget | null {
  const kind = String((data as any)?.type ?? '');
  if (!kind) return null;
  if (V2_MATCH_KINDS.has(kind)) {
    const matchId = (data as any)?.match_id as string | number | undefined;
    return { tab: 'Matches', matchId };
  }
  if (V2_LEAGUE_KINDS.has(kind)) return { tab: 'League' };
  if (V2_RANK_KINDS.has(kind)) return { tab: 'Rank' };
  if (V2_TRADE_KINDS.has(kind)) return { tab: 'Trades' };
  return null;
}

const TAB_PATH: Record<NotificationTab, string> = {
  Rank: 'rank',
  Trades: 'trades',
  Matches: 'matches',
  League: 'league',
};

/** Navigate to a notification target. Buffers until the container is ready
 *  (cold-start taps), and when `ux.deeplink_router_v2` is also on, resolves
 *  through the same route table as URLs — with an imperative fallback so a
 *  tap never silently dies.
 *
 *  Matches param contract (consumed by MatchesScreen — W2B):
 *  `{ match_id: string, src: 'push', ts: number }`; `ts` changes per tap so
 *  repeat taps on the same match re-trigger the scroll/highlight effect. */
export function routeNotificationTap(tab: NotificationTab, matchId?: string | number): void {
  runWhenNavReady(() => {
    const flags = useFeatureFlags.getState().flags;
    if (flags['ux.deeplink_router_v2']) {
      const path =
        tab === 'Matches' && matchId != null
          ? `app/matches/${encodeURIComponent(String(matchId))}?src=push&ts=${Date.now()}`
          : `app/${TAB_PATH[tab]}`;
      if (_routePathV2(path)) return;
      // fall through to the imperative navigate if resolution fails
    }
    try {
      const params =
        tab === 'Matches' && matchId != null
          ? { screen: 'Matches', params: { match_id: String(matchId), src: 'push', ts: Date.now() } }
          : { screen: tab };
      // @ts-expect-error — nested tab nav route; types don't cover cross-stack
      navigationRef.navigate('Main', params);
    } catch {
      /* navigator mid-transition; non-fatal */
    }
  });
}

/** Parse a deep link, capture any referral, and route it.
 *  Safe to call repeatedly with the same URL — side effects are idempotent
 *  (setInvitedBy is last-write-wins; navigating to the same screen is a
 *  no-op on react-navigation). */
export function handleDeepLink(url: string | null | undefined): void {
  if (!url) return;
  let parsed: ReturnType<typeof Linking.parse>;
  try {
    parsed = Linking.parse(url);
  } catch {
    return;
  }

  // Referral: ?ref=<username>. queryParams may be Record<string, string | string[]>
  // Captured in BOTH router modes.
  const ref = parsed.queryParams?.ref;
  const refStr = Array.isArray(ref) ? ref[0] : ref;
  if (typeof refStr === 'string' && refStr.trim()) {
    useSession.getState().setInvitedBy(refStr);
  }

  const path = (parsed.path || '').replace(/^\/+/, '');

  if (useFeatureFlags.getState().flags['ux.deeplink_router_v2']) {
    // Bare open / referral-only URL (no path) — nothing to route, no toast.
    if (!path) return;
    const full = `${path.replace(/\/+$/, '')}${_buildQuery(parsed.queryParams)}`;
    runWhenNavReady(() => {
      if (_routePathV2(full)) return;
      // Unroutable → home + toast, never a silent no-op (PRD 01-04 item 3).
      try {
        navigationRef.navigate('Main');
      } catch {
        /* non-fatal */
      }
      _notifyLinkFallback();
    });
    return;
  }

  // ── Legacy parser (flag off — behavior unchanged) ──
  // Public profile: /u/<username>. expo-linking sets `path` without a
  // leading slash, so "u/teresa" matches the published route.
  const m = /^u\/([^\/?#]+)/i.exec(path);
  if (m && m[1]) {
    const username = decodeURIComponent(m[1]);
    if (_navReady()) {
      try {
        navigationRef.navigate('Profile', { username });
      } catch {
        /* navigator mid-transition; non-fatal */
      }
    }
  }
}
