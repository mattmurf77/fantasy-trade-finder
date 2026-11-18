import { create } from 'zustand';
import {
  HOME_RETURN_IDLE,
  homeReturnArm,
  homeReturnOnTabFocus,
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

interface HomeReturnStore extends HomeReturnState {
  /** The tab that currently has focus in the bottom tabs, as last reported. */
  focusedTab: string | null;
  arm: (tap: HomeTileTap) => void;
  noteTabFocus: (tab: string) => void;
  clear: () => void;
}

export const useHomeReturn = create<HomeReturnStore>((set, get) => ({
  ...HOME_RETURN_IDLE,
  focusedTab: null,
  arm: (tap) => set(homeReturnArm(tap)),
  noteTabFocus: (tab) => set({ ...homeReturnOnTabFocus({ tab: get().tab }, tab), focusedTab: tab }),
  clear: () => set(HOME_RETURN_IDLE),
}));

/** Non-hook arm for HomeHub's tap handlers. */
export function armHomeReturn(tap: HomeTileTap): void {
  useHomeReturn.getState().arm(tap);
}
