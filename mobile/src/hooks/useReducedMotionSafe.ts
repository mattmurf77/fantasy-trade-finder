import { useReducedMotion } from 'react-native-reanimated';
import { useFlag } from '../state/useFeatureFlags';

// Reduce Motion gate (teardown S2 PRD-02, flag `a11y.reduce_motion`).
//
// Returns true ONLY when the rollout flag is on AND the OS "Reduce Motion"
// accessibility setting is on. Flag off → always false, so every consumer
// renders today's motion unchanged (safe dark rollout).
//
// OS state comes from Reanimated's `useReducedMotion()` (installed 4.1.1 has
// it). Note its documented caveat: the value is read at app startup and does
// not live-update if the user flips the OS setting mid-session — acceptable
// for a visual-motion gate; do not use it for logic correctness.
//
// ── Usage note for wave-2 screen agents ─────────────────────────────────────
// At each animation site, branch to the motionless equivalent when this
// returns true (Reduce Motion permits gesture-DRIVEN movement — keep the
// deck's finger-tracking pan):
//   const reduceMotion = useReducedMotionSafe();
//   • TradesScreen card fling (1.5× screen-width exit)  → crossfade-out
//   • Toast bottom slide                                → fade in/out
//   • Modal/sheet `animationType="slide"`               → `"fade"`
//   • Card/list entry stagger (fade + 8px rise)         → plain fade, no rise
// No component owned by W1B animates today, so this ships consumer-less.
export function useReducedMotionSafe(): boolean {
  const flagOn = useFlag('a11y.reduce_motion');
  const osReduceMotion = useReducedMotion();
  return flagOn && osReduceMotion;
}
