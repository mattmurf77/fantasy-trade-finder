import { create } from 'zustand';
import {
  HOME_RETURN_IDLE,
  HOME_RETURN_NO_SIGNAL,
  homeReturnArm,
  homeReturnOnTabFocus,
  homeReturnSignal,
  type HomeReturnSignal,
  type HomeReturnState,
  type HomeTileTap,
} from '../navigation/navContinuity';

// The Home return control's state (flag `nav.home_return`, D-275; the
// generalisation of D-269's arrival-scoped "Home" control). HomeHub arms it
// before a tile crosses to another tab; TabNav reports every tab focus; the
// control (components/HomeReturnBar) shows while the armed tab is the
// focused one. Never persisted: an arrival must not replay on a cold start.
// The transitions are navigation/navContinuity's pure functions, executed by
// tests/check-nav-continuity.js.
//
// `returned` is the bar's one-shot tap signal (D-276, flag
// `nav.home_return_unified`): the bar bumps it before it navigates, naming
// the armed tab, and a page with something to close on the way out
// (LeagueSummaryScreen's roster arrival) reacts in a synchronous
// `useHomeReturn.subscribe` listener. The bar stays page-agnostic.

interface HomeReturnStore extends HomeReturnState {
  /** The tab that currently has focus in the bottom tabs, as last reported. */
  focusedTab: string | null;
  /** The last "‹ Home" tap (one-shot: a new `seq` per tap). */
  returned: HomeReturnSignal;
  arm: (tap: HomeTileTap, unified?: boolean) => void;
  noteTabFocus: (tab: string) => void;
  /** The bar was tapped: signal it, for the tab it was armed for. */
  requestReturn: () => void;
  clear: () => void;
}

export const useHomeReturn = create<HomeReturnStore>((set, get) => ({
  ...HOME_RETURN_IDLE,
  focusedTab: null,
  returned: HOME_RETURN_NO_SIGNAL,
  arm: (tap, unified = false) => set(homeReturnArm(tap, unified)),
  noteTabFocus: (tab) => set({ ...homeReturnOnTabFocus({ tab: get().tab }, tab), focusedTab: tab }),
  requestReturn: () => set({ returned: homeReturnSignal(get().returned, get().tab) }),
  clear: () => set(HOME_RETURN_IDLE),
}));

/** Non-hook arm for HomeHub's tap handlers. `unified` is
 *  navContinuity.homeReturnUnifiedOn(...) at the tap. */
export function armHomeReturn(tap: HomeTileTap, unified = false): void {
  useHomeReturn.getState().arm(tap, unified);
}
