// Navigation continuity (docs/plans/nav-continuity/scope.md, D-275).
//
// The navigation decisions of the continuity work, pulled out as PURE
// functions so mobile/tests/check-nav-continuity.js can EXECUTE them (no
// React, no React Navigation, no store imports: this file must stay
// requirable by a plain-node transpile).
//
// Two server flags, both shipped on, each off ⇒ today's behaviour exactly:
//   * `nav.home_return`  — R5 / Q1 (a): a Home tile that crosses to another
//     tab arms a "Home" control that shows on that tab for the visit only.
//   * `nav.home_return_unified` — on top of `nav.home_return` (D-276): the
//     position tile body (D-269's roster arrival) arms the same "‹ Home"
//     control and League rankings drops its own header "Home" control, so
//     every Home tile has ONE Home control that looks and acts the same.
//   * `nav.continuity`   — R1-R4, R8, R9, R13: the picker's Close and its
//     in-app arrival, returning to pages already underneath, the own-stack
//     Back fallbacks, the stack reset on sign-out, Portfolio's Back and the
//     liked-trades link, the sentence links and the Tiers prompt.

export const HOME_RETURN_FLAG = 'nav.home_return';
export const CONTINUITY_FLAG = 'nav.continuity';
export const HOME_RETURN_UNIFIED_FLAG = 'nav.home_return_unified';

// ── R5 — the Home return control ────────────────────────────────────────

/** Tabs a Home tile can cross to that carry the control. */
export type HomeReturnTab = 'Trades' | 'Matches' | 'League';

/** Every Home hub tap that navigates (HomeHub.tsx). `direction` is the
 *  playoff card's half sheet rows; they open pushes, never a tab.
 *  `next_move` is the row under the playoff card (D-278): it opens Find a
 *  Trade on the Trades tab, as the "Find a trade" tile does. */
export type HomeTileTap =
  | 'outlook'
  | 'review_outlook'
  | 'standings'
  | 'direction'
  | 'overall_rank'
  | 'buy'
  | 'sell'
  | 'position_ranking'
  | 'position_roster'
  | 'link_league'
  | 'find_trade'
  | 'rank'
  | 'matches'
  | 'trends'
  | 'usage_rates'
  | 'free_agents'
  | 'next_move';

/**
 * Which tab a Home tap arms the control for, or null when it arms none:
 *   - pushes over the tabs (Standings, the half sheet's pages, Usage Rates,
 *     Free agents, Link a league) already have a Back that returns to Home;
 *   - `rank` and `trends` land on RANK PAGES, whose one exit is "More ways
 *     to rank" (operator ruling 2026-08-16, check-rank-nav-exit.js; Q5 not
 *     taken), so they are left exactly as they are;
 *   - `position_roster` is D-269's arrival. Not unified (the default): it
 *     has its own header "Home" control in League rankings (flag
 *     `nav.home_position_roster`), so arming the bar would show two.
 *     Unified (`homeReturnUnifiedOn`): it arms League like the other tiles,
 *     and League rankings draws no header control (`rosterHeaderHomeVisible`).
 */
export function homeReturnTabFor(tap: HomeTileTap, unified = false): HomeReturnTab | null {
  switch (tap) {
    case 'position_roster':
      return unified ? 'League' : null;
    case 'outlook':
    case 'review_outlook':
    case 'find_trade':
    case 'next_move':
      return 'Trades';
    case 'overall_rank':
    case 'buy':
    case 'sell':
    case 'position_ranking':
      return 'League';
    case 'matches':
      return 'Matches';
    default:
      return null;
  }
}

/** Unified mode (D-276): only when BOTH `nav.home_return` and
 *  `nav.home_return_unified` are on. Either off ⇒ D-269 and D-275 exactly as
 *  they were (two kinds of control, never both on one arrival). */
export function homeReturnUnifiedOn(homeReturnOn: boolean, unifiedOn: boolean): boolean {
  return homeReturnOn && unifiedOn;
}

/** The armed return: which tab it belongs to, or none. */
export interface HomeReturnState {
  tab: HomeReturnTab | null;
}

export const HOME_RETURN_IDLE: HomeReturnState = { tab: null };

/** A Home tap: arm for its tab (or disarm, for a tap that arms none). */
export function homeReturnArm(tap: HomeTileTap, unified = false): HomeReturnState {
  return { tab: homeReturnTabFor(tap, unified) };
}

/** A tab came into focus. Arriving on the armed tab keeps the control;
 *  focusing any other tab (Home included) ends the visit. */
export function homeReturnOnTabFocus(state: HomeReturnState, focusedTab: string): HomeReturnState {
  return state.tab != null && state.tab === focusedTab ? state : HOME_RETURN_IDLE;
}

/** Whether the control shows: flag on, armed, and on the armed tab. */
export function homeReturnVisible(
  state: HomeReturnState,
  focusedTab: string | null,
  flagOn: boolean,
): boolean {
  return flagOn && state.tab != null && state.tab === focusedTab;
}

/** A tap on "‹ Home": a one-shot signal, numbered so each tap is a new one,
 *  naming the tab the control was armed for. The bar knows nothing about
 *  the page underneath; a page that has something to close on the way out
 *  (League rankings' roster arrival) listens for it. */
export interface HomeReturnSignal {
  seq: number;
  tab: HomeReturnTab | null;
}

export const HOME_RETURN_NO_SIGNAL: HomeReturnSignal = { seq: 0, tab: null };

export function homeReturnSignal(prev: HomeReturnSignal, armedTab: HomeReturnTab | null): HomeReturnSignal {
  return { seq: prev.seq + 1, tab: armedTab };
}

/** D-269's header "Home" control in League rankings: on the tab root, for
 *  the drill-in the position tile arrival opened, while it is still open —
 *  and never in unified mode, where the "‹ Home" bar is the one control. */
export function rosterHeaderHomeVisible(
  isTabRoot: boolean,
  arrivalTeamId: string | null,
  selectedTeamId: string | null,
  unified: boolean,
): boolean {
  return !unified && isTabRoot && arrivalTeamId != null && selectedTeamId === arrivalTeamId;
}

/** Unified mode: a "‹ Home" tap armed for League closes the drill-in the
 *  roster arrival opened (`closeTeam('home_back')`, as D-269's control does)
 *  if it is still the open one; anything else is left as it is. */
export function rosterClosesOnHomeReturn(
  unified: boolean,
  signal: HomeReturnSignal,
  isTabRoot: boolean,
  arrivalTeamId: string | null,
  selectedTeamId: string | null,
): boolean {
  return (
    unified &&
    signal.tab === 'League' &&
    isTabRoot &&
    arrivalTeamId != null &&
    selectedTeamId === arrivalTeamId
  );
}

// ── R4 — "nothing to go back to" fallbacks ──────────────────────────────

/** Whether the page's OWN stack has a page under it. `canGoBack()` also asks
 *  the parent navigators, and the bottom tabs can always go back to the
 *  first tab (Home), so it never reaches the coded fallback (finding C1). */
export function ownStackCanPop(state: { index?: number } | null | undefined): boolean {
  return !!state && typeof state.index === 'number' && state.index > 0;
}

/** The decision a Back-or-fallback control makes: 'back' pops, 'fallback'
 *  opens the named page. Flag off ⇒ today's `canGoBack()` test. */
export function backOrFallback(
  ownState: { index?: number } | null | undefined,
  canGoBack: boolean,
  flagOn: boolean,
): 'back' | 'fallback' {
  if (flagOn) return ownStackCanPop(ownState) ? 'back' : 'fallback';
  return canGoBack ? 'back' : 'fallback';
}

// ── R1 / R2 — the league picker opened from inside the app ──────────────

/** True when the tabs ('Main') sit UNDER the picker in the root stack, i.e.
 *  it was opened from inside the app (league switcher, Home, Free agents,
 *  Usage Trends, Settings, a failed send, League home). At sign-in the
 *  picker REPLACES SignIn and is the stack's first page. */
export function pickerOpenedInApp(
  rootState: { routes?: { key: string; name: string }[] } | null | undefined,
  pickerKey: string,
): boolean {
  const routes = rootState?.routes ?? [];
  const self = routes.findIndex((r) => r.key === pickerKey);
  if (self <= 0) return false;
  return routes.slice(0, self).some((r) => r.name === 'Main');
}

/** What picking a league does: return to the tabs underneath (`popTo`) when
 *  the picker was opened in the app, else replace it with fresh tabs. */
export function pickerExit(inApp: boolean, flagOn: boolean): 'popTo' | 'replace' {
  return flagOn && inApp ? 'popTo' : 'replace';
}

/** Whether the one-league auto-forward may fire. Never for an in-app
 *  opening (the user came to add or link a league). */
export function pickerAutoSkipAllowed(inApp: boolean, flagOn: boolean): boolean {
  return !(flagOn && inApp);
}

// ── R3 — return to a page already underneath ────────────────────────────

/** React Navigation 7 `navigate` options. With `pop`, a navigate to a page
 *  already in the stack returns to it (removing what is above) instead of
 *  stacking a new copy (G-056); with no such page it opens one as before.
 *  `merge` keeps the existing page's params (the rank chooser's cards, so a
 *  Quick Set walk keeps its position). Flag off ⇒ undefined, today's push. */
export function returnOptions(
  flagOn: boolean,
  merge = false,
): { pop: true; merge?: true } | undefined {
  if (!flagOn) return undefined;
  return merge ? { pop: true, merge: true } : { pop: true };
}

// ── R8 — sign-out, account deletion and session expiry ──────────────────

/** The root-stack reset that leaves the sign-in page alone on the stack, the
 *  way the test-profile swap does (state/testProfile.ts restartNavigation). */
export function signInReset(): { index: 0; routes: { name: 'SignIn' }[] } {
  return { index: 0, routes: [{ name: 'SignIn' }] };
}

// ── R13 — Tiers' unsaved-changes prompt ─────────────────────────────────

/** Whether leaving Tiers (the page being removed from its stack: "More ways
 *  to rank" returning to the chooser, a tab re-tap, a swipe back) asks
 *  first. Only with moves that are not saved, never while a save is in
 *  flight (its success clears the moves), and never with the flag off.
 *  Never for a RESET: that is sign-out / deletion / session expiry (R8) or a
 *  profile swap tearing the whole app down; the session is already gone, so
 *  "Keep editing" would strand the user on a signed-out page. */
export function tiersLeavePrompts(
  dirty: boolean,
  saving: boolean,
  flagOn: boolean,
  actionType?: string,
): boolean {
  return flagOn && dirty && !saving && actionType !== 'RESET';
}
