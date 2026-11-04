// The ONE tester-surface predicate (#354 D-7, ux-lead's review).
//
// True in dev builds and on any device delivered a tester flag:
// `testing.stage_users` (the "Test stages" row) or `testing.timing_readout`
// (trades-eng's 200 ms readout, delivered by an allowlist experiment). Both
// the hub's Testing row (SettingsHubScreen) and the Testing page body
// (SettingsTestingScreen) read it, so the row can never lead to a page that
// renders nothing. `timing_readout` has to be in it: the operator's phone gets
// only that flag, and a `stage_users`-only gate would hide the readout.
// `useFlag` accepts any key, so this works before that flag is registered.
//
// It lives beside the pages, not in sections/TestingSection.tsx: the hub
// imports no section module (tests/check-settings-ia.js §4), and each section
// is owned by one page. Each row inside the page keeps its own flag gate.
// Pinned by tests/check-settings-ia.js.

import { useFlag } from '../../state/useFeatureFlags';

export function useTesterSurface(): boolean {
  // Both hooks run on every render; only the result is combined.
  const stageUsers = useFlag('testing.stage_users');
  const timingReadout = useFlag('testing.timing_readout');
  return __DEV__ || stageUsers || timingReadout;
}
