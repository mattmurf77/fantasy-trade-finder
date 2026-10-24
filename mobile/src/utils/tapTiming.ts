// Time to trade suggestion — the device's last tap-to-card time, for the
// Testing readout (head-eng ruling 11; flag `testing.timing_readout`).
//
// In memory only, process lifetime: no server, no storage. The R2 emitter
// (state/tradeSearchTrace.reportFirstCardShown) writes it at T1; the
// readout (components/TimingReadoutRow) reads it with useSyncExternalStore.
// A deliberate exception to "utils hold no module state" (head-eng's
// placement for the readout store): it imports nothing, so a check-*.js
// guard can transpile and run it under plain node.

export interface TapTiming {
  /** R2's ms_from_tap (monotonic). */
  msFromTap: number;
  /** The AC-L1 cell it belongs to. */
  networkType: string;
  launchState: string;
}

let last: TapTiming | null = null;
const listeners = new Set<() => void>();

export function recordTapTiming(t: TapTiming): void {
  last = t;
  for (const fn of listeners) fn();
}

export function lastTapTiming(): TapTiming | null {
  return last;
}

export function subscribeTapTiming(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}
