import { Platform, Settings } from 'react-native';
import Constants from 'expo-constants';

// ─────────────────────────────────────────────────────────────────────────
// Launch-argument screen entry — capture-harness only.
//
// WHY THIS EXISTS
// The screen-library capture flows need to photograph screens that have no
// tappable path under release flags (RankHome — `ux.rank_tab_destination`
// turns "More ways to rank" into the RankMenu sheet, which does not list the
// chooser; Portfolio — the Acquire subnav is hidden while `trades.finder_hub`
// lands in a finder mode; QuickRank — reachable only through a native Alert
// at the end of the Quick-set walk; Profile — reachable only by deep link).
//
// Deep links were the original plan and are DEAD in this harness: on iOS 18
// `openLink dtf://…` raises a SpringBoard "Open in DTF?" confirmation that
// Maestro cannot dismiss (verified warm and cold). Launch arguments have no
// such prompt.
//
// MECHANISM
// Maestro's `launchApp: arguments: { FTFTestRoute: RankHome }` is converted
// by maestro-ios-driver's `util.IOSLaunchArguments.toIOSLaunchArguments` into
// the process argv pair `["-FTFTestRoute", "RankHome"]` (keys not already
// starting with "-" get the dash prefixed). iOS parses `-key value` argv into
// NSUserDefaults' **NSArgumentDomain**, and react-native's iOS `Settings`
// module is a thin wrapper over `[NSUserDefaults standardUserDefaults]
// dictionaryRepresentation` (RCTSettingsManager.mm), which includes that
// domain. So `Settings.get('FTFTestRoute')` returns the launch argument with
// zero native code. The argument domain is volatile: it exists for exactly
// the process that was launched with it and is never persisted, so a launch
// without the argument can never inherit a stale value.
//
// ─────────────────────────────────────────────────────────────────────────
// PRODUCTION GATE — review this constant in isolation.
//
// `extra.testMode` is baked into the bundle at BUILD time by app.config.js:
//
//     testMode: process.env.FTF_ENV === "test"
//
// The ONLY producer of `FTF_ENV=test` is mobile/scripts/sim-build.sh (the
// simulator/capture build). mobile/eas.json declares no `env` block on any
// profile, so every TestFlight / App Store bundle is built with FTF_ENV
// unset and carries `testMode: false`. There is no runtime path that can
// flip it — it is a build-time constant read once at module load, not a
// feature flag, not a remote value, not AsyncStorage.
//
// Consequence: in a production bundle `readTestRouteIntent()` returns null on
// its first line, `applyTestRouteEntry()` returns false without touching the
// navigator, and the launch argument (which nothing in production supplies
// anyway) is never even read. Behaviour change in production: zero.
// ─────────────────────────────────────────────────────────────────────────
const IS_TEST_BUILD =
  (Constants.expoConfig?.extra as { testMode?: boolean } | undefined)
    ?.testMode === true;

const ARG_ROUTE = 'FTFTestRoute';
const ARG_PARAMS = 'FTFTestRouteParams';

// Routes that live inside a tab's nested stack (TabNav.tsx). Everything not
// listed here is treated as a ROOT-stack route name (RootNav's AuthStack:
// Profile, Settings, LeagueSummary, FreeAgents, DraftRoom, …) and passed
// through verbatim, so future screens need no edit here.
const TAB_OF: Record<string, string> = {
  // Rank stack
  RankHome: 'Rank',
  QuickRank: 'Rank',
  QuickSetTiers: 'Rank',
  Tiers: 'Rank',
  Trios: 'Rank',
  Anchors: 'Rank',
  ManualRanks: 'Rank',
  RookieRanks: 'Rank',
  Trends: 'Rank',
  // Trades (tab label "Acquire") stack
  TradesHome: 'Trades',
  TradeDeck: 'Trades',
  Portfolio: 'Trades',
  TradeCalculator: 'Trades',
  // League stack
  LeagueRankings: 'League',
  LeagueHome: 'League',
};

// Tab route names themselves, so `-FTFTestRoute Matches` focuses the tab.
const TAB_NAMES = new Set(['Rank', 'Trades', 'Draft', 'Matches', 'League']);

export interface TestRouteIntent {
  route: string;
  params?: Record<string, unknown>;
}

/**
 * The route the harness asked for, or null. Null in every production build
 * (see the gate above), on non-iOS, and whenever the launch argument is
 * absent or malformed.
 */
export function readTestRouteIntent(): TestRouteIntent | null {
  if (!IS_TEST_BUILD) return null;
  if (Platform.OS !== 'ios') return null;

  let raw: unknown;
  try {
    raw = Settings.get(ARG_ROUTE);
  } catch {
    return null;
  }
  if (typeof raw !== 'string') return null;
  const route = raw.trim();
  if (!route) return null;

  // Optional route params, as a QUERY STRING:
  //   -FTFTestRouteParams 'username=qa_standard'
  //
  // Deliberately NOT JSON. NSUserDefaults' argument-domain parser treats a
  // value beginning with `{` as an old-style property list; a JSON object is
  // not valid old-style plist, so `{"username":"qa_standard"}` never reaches
  // the app at all — observed live: the route opened but ProfileScreen got no
  // username and the header rendered "@profile". A query string has no
  // characters the plist parser claims. All values arrive as strings, which is
  // all any capture entry needs.
  let params: Record<string, string> | undefined;
  const rawParams = Settings.get(ARG_PARAMS);
  if (typeof rawParams === 'string' && rawParams.trim()) {
    const out: Record<string, string> = {};
    for (const pair of rawParams.split('&')) {
      if (!pair) continue;
      const eq = pair.indexOf('=');
      if (eq <= 0) continue;
      try {
        out[decodeURIComponent(pair.slice(0, eq))] = decodeURIComponent(
          pair.slice(eq + 1),
        );
      } catch {
        // A malformed pair is not worth failing a capture over — the route
        // still opens and the screen renders its own missing-param state.
      }
    }
    if (Object.keys(out).length > 0) params = out;
  }

  return { route, params };
}

/**
 * Jump the navigator to the requested route. Returns true if a jump was
 * dispatched. Callers must only invoke this once the authed tree is the
 * live root (RootNav gates on `initialRoute === 'Main'`) — this helper
 * deliberately does not reach into session state.
 *
 * `navigate` (not `reset`) is used so the target keeps a real back stack.
 */
export function applyTestRouteEntry(nav: {
  isReady: () => boolean;
  navigate: (...args: never[]) => void;
}): boolean {
  const intent = readTestRouteIntent();
  if (!intent) return false;
  if (!nav.isReady()) return false;

  const tab = TAB_OF[intent.route];
  try {
    if (tab) {
      // Main → <tab> → <screen inside that tab's stack>
      (nav.navigate as unknown as (n: string, p: object) => void)('Main', {
        screen: tab,
        params: { screen: intent.route, params: intent.params },
      });
    } else if (TAB_NAMES.has(intent.route)) {
      (nav.navigate as unknown as (n: string, p: object) => void)('Main', {
        screen: intent.route,
        params: intent.params,
      });
    } else {
      // Root-stack route (Profile, Settings, LeagueSummary, …).
      (nav.navigate as unknown as (n: string, p?: object) => void)(
        intent.route,
        intent.params,
      );
    }
  } catch {
    return false;
  }
  return true;
}
