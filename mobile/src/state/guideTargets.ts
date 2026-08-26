// Spotlight target registry (guided-avatar-script.md §2). Screens register
// the views The Analyst points at by testID; the overlay measures them at
// show time. A missing/unmeasurable target degrades to bubble-only — never
// a blank cutout.
import type { View } from 'react-native';

export interface TargetFrame { x: number; y: number; width: number; height: number }

const targets = new Map<string, React.RefObject<View | null>>();

export function registerGuideTarget(testID: string, ref: React.RefObject<View | null>): void {
  targets.set(testID, ref);
}

export function unregisterGuideTarget(testID: string): void {
  targets.delete(testID);
}

export function measureGuideTarget(testID: string): Promise<TargetFrame | null> {
  const ref = targets.get(testID);
  const node = ref?.current;
  if (!node || typeof node.measureInWindow !== 'function') {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    let settled = false;
    // measureInWindow never calls back for unmounted nodes — time out to null.
    const t = setTimeout(() => { if (!settled) { settled = true; resolve(null); } }, 250);
    node.measureInWindow((x, y, width, height) => {
      if (settled) return;
      settled = true;
      clearTimeout(t);
      if ([x, y, width, height].some((v) => typeof v !== 'number' || Number.isNaN(v)) || width <= 0) {
        resolve(null);
      } else {
        resolve({ x, y, width, height });
      }
    });
  });
}

// ── Movement notifications (B1) ────────────────────────────────────────────
// `measureInWindow` returns absolute WINDOW coordinates, so a measured frame
// goes stale the moment the host ScrollView moves. Hosts announce movement
// here — one call, no guide internals imported — and the overlay re-measures
// the active target. With no overlay mounted this is a walk over an empty
// Set, i.e. a no-op on every screen that is not currently guided.

type GuideTargetsMovedListener = () => void;

const movedListeners = new Set<GuideTargetsMovedListener>();

export function subscribeGuideTargetsMoved(fn: GuideTargetsMovedListener): () => void {
  movedListeners.add(fn);
  return () => { movedListeners.delete(fn); };
}

export function notifyGuideTargetsMoved(): void {
  movedListeners.forEach((fn) => fn());
}

// ── Scroll-into-view (#384 device feedback, report 5) ──────────────────────
// A spotlight can resolve onto a node that is off-screen, or onto one so close
// to an edge that the avatar+bubble band has nowhere adjacent to sit. The
// overlay cannot scroll the host itself — it does not own the container and
// must not import a screen — so hosts register a minimal handle keyed by the
// SCREEN NAME their steps declare (`GuideStep.screen`), and the overlay asks
// that handle to bring the target into view.
//
// The handle is deliberately two functions, not a ScrollView ref: the overlay
// works in absolute WINDOW coordinates and the container works in CONTENT
// offsets, so it needs the host's current offset to convert between them. A
// screen with no scroll container simply never registers, and the overlay's
// lookup returns undefined — the same "degrade quietly" posture as a missing
// target.

export interface GuideScroller {
  /** Scroll the container so its content offset becomes `y`. */
  scrollTo: (y: number, animated?: boolean) => void;
  /** The container's CURRENT content offset, so a window-space delta can be
   *  turned into an absolute offset. */
  getScrollY: () => number;
}

const scrollers = new Map<string, GuideScroller>();

export function registerGuideScroller(screenKey: string, handle: GuideScroller): void {
  scrollers.set(screenKey, handle);
}

export function unregisterGuideScroller(screenKey: string): void {
  scrollers.delete(screenKey);
}

export function getGuideScroller(screenKey: string | undefined): GuideScroller | undefined {
  return screenKey ? scrollers.get(screenKey) : undefined;
}
