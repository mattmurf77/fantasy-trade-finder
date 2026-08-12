import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { loadFeatureFlags, flagProvenance } from '../api/flags';
import { track } from '../api/events';
import type { FlagMap } from '../shared/types';

// AsyncStorage key for the last successfully-fetched feature flag map.
// Hydrating from this on boot keeps gated features visible during a
// cold-start network wait and preserves them through a transient backend
// outage — addresses review fix #10 / silent-bugs.md bug #4 (the bare
// `{}` fallback silently hid every gated feature on net error).
const FF_KEY = 'feature_flags_v1';

interface FlagState {
  flags: FlagMap;
  loaded: boolean;
  /** Local-only AsyncStorage hydrate. Awaited by the boot gate so flag-
   *  gated UI settles to cached values before the first screen renders.
   *  Never touches the network — safe inside the splash-gating set. */
  loadCachedFlags: () => Promise<void>;
  /** Network revalidate. Fetches the live flag map and persists it. Run
   *  detached (fire-and-forget) after boot — must NOT gate the splash. */
  revalidateFlags: () => Promise<void>;
  /** Throttled foreground revalidate (analytics-platform §4.6b): refetches
   *  config at most once per 30 min on foreground resume. This is the
   *  mechanism the analytics kill-switch + experiment-pause client bounds
   *  ride on (FR-19/FR-38). Cold start always fetches via revalidateFlags. */
  maybeRevalidateFlags: () => Promise<void>;
}

// Last successful flag fetch (module scope; cold start re-fetches at boot so
// this need not survive a relaunch). Gates the §4.6b foreground refetch.
let _lastFlagFetchTs = 0;
const FLAG_REFETCH_THROTTLE_MS = 30 * 60_000;

// Launched features fail OPEN (feedback #115 recurrence, 2026-07-17): a
// first-ever boot has no cached map, and if the network revalidate fails or
// races the first screen, `{}` hid every gated surface — the operator's
// build 44 showed no ESPN linking anywhere despite the flag being live.
// These baked defaults make launched features visible from first paint;
// the server fetch remains authoritative BOTH ways (a server `false` still
// kill-switches on the next successful revalidate, since cached/network
// maps override these keys). Only add flags here once they are launched —
// dark features must stay absent so they default hidden.
const LAUNCHED_FLAG_DEFAULTS: FlagMap = {
  'espn.link': true,
  'auth.accounts': true,
  // #232 follow-on — rankings import ships ON (the flag is a kill switch,
  // not a dark launch), so the chooser entry is visible from first paint;
  // a server `false` still hides it on the next successful revalidate.
  'ranks.import': true,
  // #293/#294 — draft-pick value counted in every subset and position
  // filter. Graduated to ON at ship (operator: "293/294 ship live"), so it
  // must be visible from first paint; the flag stays a kill switch, and a
  // server `false` still turns it off on the next successful revalidate.
  'league.picks_always_counted': true,
  // ── #300, LIT (both true, operator direction 2026-08-12) ───────────────
  // `league.pos_candidates` = the median divider + Buyer/Seller band labels
  // on the ranked list; `league.player_trade_handoff` = the drill-in's
  // direction swap and its Offer/Target row actions.
  //
  // These MUST carry the same value as `config/features.json`, and that is
  // the whole reason they are listed rather than absent: `revalidateFlags`
  // does a whole-map `set({ flags })`, so a key that exists in only one of
  // the two places disagrees with itself across the first two paints — a
  // feature that paints for one frame and then vanishes, or the reverse.
  // Flipping either one is a one-word edit HERE **and** in
  // `config/features.json`; changing only one is the bug. Pinned by
  // `mobile/tests/check-league-candidates-300.js` §1, which compares the
  // two files rather than asserting a literal.
  'league.pos_candidates': true,
  'league.player_trade_handoff': true,
};

export const useFeatureFlags = create<FlagState>((set, get) => ({
  flags: { ...LAUNCHED_FLAG_DEFAULTS },
  loaded: false,
  loadCachedFlags: async () => {
    // Optimistically hydrate from AsyncStorage before the network fetch
    // so users get cached flags during a cold-start wait. First-ever
    // launch (no stored entry) falls back to the launched defaults.
    // Merge under the cache: a genuinely-cached `false` (server kill
    // switch seen on a prior boot) must win over the baked default.
    try {
      const cachedRaw = await AsyncStorage.getItem(FF_KEY);
      if (cachedRaw) {
        const parsed = JSON.parse(cachedRaw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          set({ flags: { ...LAUNCHED_FLAG_DEFAULTS, ...(parsed as FlagMap) } });
        }
      }
    } catch {
      /* non-fatal — hydrate is opportunistic */
    }
  },
  revalidateFlags: async () => {
    // Network fetch. On success, replace the in-memory map AND persist so
    // the next boot has a fresh cache. On failure, `loadFeatureFlags`
    // returns `{}` today — but we don't want that to clobber the hydrated
    // cache, so we detect the failure here and keep the cached flags.
    try {
      const flags = await loadFeatureFlags({ throwOnError: true });
      _lastFlagFetchTs = Date.now();
      set({ flags, loaded: true });
      try {
        await AsyncStorage.setItem(FF_KEY, JSON.stringify(flags));
      } catch {
        /* non-fatal — cache write is opportunistic */
      }
    } catch {
      // Network fetch failed — keep whatever we hydrated (or `{}` on first
      // launch). Mark loaded=true so gated components stop waiting.
      set({ loaded: true });
    }
  },
  maybeRevalidateFlags: async () => {
    if (Date.now() - _lastFlagFetchTs < FLAG_REFETCH_THROTTLE_MS) return;
    await get().revalidateFlags();
  },
}));

// ── P0-7 F1 · experiment_exposed ───────────────────────────────────────
// EXPOSURE, not assignment. backend/experiments.py uses assignment as a
// proxy and reports the dilution; for a first-session test the gap is
// large AND arm-correlated, so an assignment-based read is biased, not
// merely noisy.
//
// Fired at most ONCE PER FLAG KEY PER SESSION, and always DEFERRED —
// `useFlag` runs during render, and calling track() there would queue an
// AsyncStorage write from a render body. setTimeout(0) moves it to the
// next tick, after the commit.
const _exposed = new Set<string>();
function noteFlagConsumed(key: string): void {
  if (_exposed.has(key)) return;
  const p = flagProvenance()[key];
  if (!p) return;                 // not an overlaid key — no experiment, no exposure
  _exposed.add(key);              // claim BEFORE the deferral: two consumers in
                                  // one render must not queue two events
  setTimeout(() => {
    track('experiment_exposed', {
      experiment: p.experiment,
      variant: p.variant,
      key,
      // `unit` is registered in the taxonomy but not emitted: the client
      // cannot derive account-vs-device (the flag endpoint returns the
      // merged maps without unit_type). Adding it is a server change.
    });
  }, 0);
}

/** Convenience hook: `useFlag("swipe.community_compare")` returns bool. */
export function useFlag(key: string): boolean {
  noteFlagConsumed(key);                       // no-op unless key is overlaid
  return useFeatureFlags((s) => !!s.flags[key]);
}

// ── Onboarding redesign flag semantics (docs/plans/onboarding-conversion/plan.md) ──
// Every onboarding.* feature is live iff the master kill-switch
// `onboarding.v2` AND the feature's own flag are both true. All callers
// must go through these helpers — never read an onboarding.* key directly,
// or the master switch stops being a kill switch.

/** Hook form: `useOnboardingFeature("onboarding.trades_first")`. */
export function useOnboardingFeature(key: string): boolean {
  noteFlagConsumed('onboarding.v2');
  noteFlagConsumed(key);
  return useFeatureFlags((s) => !!s.flags['onboarding.v2'] && !!s.flags[key]);
}

/** Non-hook form for imperative code paths (nav handlers, api modules). */
export function onboardingEnabled(key: string): boolean {
  noteFlagConsumed('onboarding.v2');
  noteFlagConsumed(key);
  const flags = useFeatureFlags.getState().flags;
  return !!flags['onboarding.v2'] && !!flags[key];
}
