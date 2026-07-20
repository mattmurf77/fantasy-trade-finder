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
