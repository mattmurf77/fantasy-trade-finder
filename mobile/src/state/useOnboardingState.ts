import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

// ftf_onboarding_state — the persisted first-run/onboarding scaffold
// (docs/plans/onboarding-conversion/plan.md, build item 4; consumed by
// items 7 (prompt snooze semantics), 8 (Apple ask policy), and the v2.1
// guided layer (coach marks / celebration beats).
//
// The app previously had NO persisted first-run flags; everything here is
// additive and only read behind onboarding.* feature gates, so with the
// flags dark this store is inert. All writes merge-and-persist; a failed
// AsyncStorage write is non-fatal (worst case: a coach mark shows twice).

const OB_KEY = 'ftf_onboarding_state_v1';

export interface OnboardingPersisted {
  /** First-run Trades chrome collapse: set true after the first swipe. */
  firstSwipeDone: boolean;
  /** Lifetime swipe count (session-2 Apple banner trigger reads this). */
  totalSwipes: number;
  /** Distinct app opens with a session (session-2 detection). */
  sessionCount: number;

  // Item 7 — contextual Quick Set prompt (snooze, never dismissed-forever)
  quicksetPromptShows: number;
  quicksetPromptSnoozed: boolean;
  quicksetPromptSession2Shown: boolean;
  quicksetPromptRetired: boolean;
  quicksetCompletedPositions: string[]; // e.g. ['WR'] — drives provenance chip flip

  // #362 — standing-offer prompt ladder. Quickset semantics exactly: one
  // show per session → snooze → exactly one re-offer once sessionCount ≥ 2
  // → retired for good. PERSISTED, not a session counter: a session counter
  // resets on every cold start, so a user who dismisses and backgrounds the
  // app would be prompted again forever. "No" has to eventually mean no.
  // Additive and read only behind `trade.standing_offers`, so with the flag
  // dark these stay at their defaults and nothing reads them.
  standingOfferPromptShows: number;
  standingOfferPromptSnoozed: boolean;
  standingOfferPromptSession2Shown: boolean;
  standingOfferPromptRetired: boolean;

  // Item 8 — Apple save-moment ask policy: max ONE auto-modal per class
  applePromptShownFor: { like?: boolean; quickset_save?: boolean; mutual_match?: boolean };
  applePromptDeclined: boolean;
  appleSession2BannerShown: boolean;

  // Guided layer (≤4 coach marks, each shown once; celebration beats)
  coachMarksShown: {
    swipe_hint?: boolean;
    provenance_chip?: boolean;
    diff_banner?: boolean;
    trio_entry?: boolean;
  };
  celebrationsShown: { first_like?: boolean; first_quickset_save?: boolean };

  // Guided avatar tour (guided-avatar-script.md; flag onboarding.guided_avatar)
  guideDismissed: boolean;                 // "Skip tour" — permanent opt-out
  guideSeen: Record<string, boolean>;      // once-ever steps by script id
  guideTourCompleted: boolean;             // S8 reached → reactive-only mode

  // Guided Onboarding v2 eligibility layer (flag onboarding.guide_v2;
  // PRD §5.0/§5.1 FR-E2/E3/E9/E10). Every field below is written ONLY by
  // useGuide with `onboarding.guide_v2` on, so with the flag off they stay
  // at their defaults and the engine behaves exactly as v1.
  /** Lifetime display count per step id — enforces `maxDisplayCount`. */
  guideDisplayCounts: Record<string, number>;
  /** Client-observable receipt counts (`recordGuideReceipt`) — the input to
   *  `retireAfter` / `invalidateOn`. Server-fired events can never land here
   *  (delta §E: a retirement wired to an unobservable event is worse than
   *  none), so screens record their own receipts. */
  guideReceipts: Record<string, number>;
  /** Steps killed behaviorally (retired, invalidated, or consumed by a
   *  call site via `markGuideStepConsumed`). Re-enabling the tour replays
   *  everything EXCEPT these. */
  guideRetired: Record<string, boolean>;
  /** 0 = pre-v2 install. Set to 2 on the first launch with guide_v2 on;
   *  no seen-state is ever cleared by the bump (FR-E9). */
  guideScriptVersion: number;
  /** Captured at the version bump: this device had completed the v1 tour,
   *  so it gets at most one v2 beat per release. */
  guideV1Upgrader: boolean;
  /** App version whose single v2 beat has already been spent (v1 upgraders). */
  guideV2BeatShownVersion: string | null;

  // Push-primer backoff (teardown S4 PRD-04, flag ux.prompt_arbiter):
  // "Maybe later" declines are persisted so the primer re-arms only after
  // 3+ sessions or a want-it moment — never every session.
  pushPrimerDeclines: number;              // lifetime "Maybe later" count
  pushPrimerLastDeclineSession: number;    // sessionCount at last decline

  // Rating prompt (teardown S7 PRD-02, flag growth.rating_prompt):
  // app version the StoreReview request last fired for (once per version).
  ratingPromptShownVersion: string | null;
}

const DEFAULTS: OnboardingPersisted = {
  firstSwipeDone: false,
  totalSwipes: 0,
  sessionCount: 0,
  quicksetPromptShows: 0,
  quicksetPromptSnoozed: false,
  quicksetPromptSession2Shown: false,
  quicksetPromptRetired: false,
  quicksetCompletedPositions: [],
  // #362 — standing-offer prompt ladder (see the interface above).
  standingOfferPromptShows: 0,
  standingOfferPromptSnoozed: false,
  standingOfferPromptSession2Shown: false,
  standingOfferPromptRetired: false,
  applePromptShownFor: {},
  applePromptDeclined: false,
  appleSession2BannerShown: false,
  coachMarksShown: {},
  celebrationsShown: {},
  guideDismissed: false,
  guideSeen: {},
  guideTourCompleted: false,
  guideDisplayCounts: {},
  guideReceipts: {},
  guideRetired: {},
  guideScriptVersion: 0,
  guideV1Upgrader: false,
  guideV2BeatShownVersion: null,
  pushPrimerDeclines: 0,
  pushPrimerLastDeclineSession: 0,
  ratingPromptShownVersion: null,
};

interface OnboardingStateStore {
  ob: OnboardingPersisted;
  hydrated: boolean;
  /** AsyncStorage hydrate — call once at boot (non-blocking is fine). */
  hydrateOnboarding: () => Promise<void>;
  /** Shallow-merge patch, persist. Nested objects are merged one level. */
  patchOnboarding: (patch: Partial<OnboardingPersisted>) => void;
}

function mergeState(
  base: OnboardingPersisted,
  patch: Partial<OnboardingPersisted>,
): OnboardingPersisted {
  return {
    ...base,
    ...patch,
    applePromptShownFor: { ...base.applePromptShownFor, ...patch.applePromptShownFor },
    coachMarksShown: { ...base.coachMarksShown, ...patch.coachMarksShown },
    celebrationsShown: { ...base.celebrationsShown, ...patch.celebrationsShown },
    guideSeen: { ...base.guideSeen, ...patch.guideSeen },
    guideDisplayCounts: { ...base.guideDisplayCounts, ...patch.guideDisplayCounts },
    guideReceipts: { ...base.guideReceipts, ...patch.guideReceipts },
    guideRetired: { ...base.guideRetired, ...patch.guideRetired },
  };
}

export const useOnboardingState = create<OnboardingStateStore>((set, get) => ({
  ob: DEFAULTS,
  hydrated: false,
  hydrateOnboarding: async () => {
    try {
      const raw = await AsyncStorage.getItem(OB_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          set({ ob: mergeState(DEFAULTS, parsed), hydrated: true });
          return;
        }
      }
    } catch {
      /* non-fatal — fall through to defaults */
    }
    set({ hydrated: true });
  },
  patchOnboarding: (patch) => {
    const next = mergeState(get().ob, patch);
    set({ ob: next });
    AsyncStorage.setItem(OB_KEY, JSON.stringify(next)).catch(() => {
      /* non-fatal — worst case a once-only surface shows again */
    });
  },
}));

/** Imperative read for non-component code. */
export function getOnboardingState(): OnboardingPersisted {
  return useOnboardingState.getState().ob;
}

/** Imperative patch for non-component code. */
export function patchOnboardingState(patch: Partial<OnboardingPersisted>): void {
  useOnboardingState.getState().patchOnboarding(patch);
}

/** #187 — Settings re-enable of The Analyst tour (full-replay semantics).
 *  Clears the permanent opt-out AND the seen-step/completion memory in one
 *  persisted write. A dedicated function because patchOnboarding can only
 *  MERGE `guideSeen` (mergeState keeps old keys), never clear it. */
export function resetGuideProgress(): void {
  const cur = useOnboardingState.getState().ob;
  const next: OnboardingPersisted = {
    ...cur,
    guideDismissed: false,
    guideSeen: {},
    guideTourCompleted: false,
  };
  useOnboardingState.setState({ ob: next });
  AsyncStorage.setItem(OB_KEY, JSON.stringify(next)).catch(() => {
    /* non-fatal — worst case the re-enable lasts only this session */
  });
}

/** FR-E10 — v2 re-enable ("replays only beats whose trigger can still fire",
 *  to the extent the engine can know it). Differences from the v1 wipe above:
 *
 *   • steps in `guideRetired` (behaviorally dead — retired, invalidated, or
 *     consumed) keep their `guideSeen` mark AND their display count, so a
 *     re-enable cannot re-teach something the user has already outgrown;
 *   • every other step is cleared on both, so the toggle visibly does
 *     something (the #187 "looks broken" failure mode);
 *   • `guideReceipts` is NEVER cleared — receipts are behavioral history,
 *     not tour progress. A step whose retirement receipt already fired but
 *     which was never re-requested (so never marked retired) is therefore
 *     still refused by `requestStep` on replay.
 *
 *  Called by `useGuide.enableTour()` when `onboarding.guide_v2` is on; the
 *  v1 `resetGuideProgress()` stays the behavior with the flag off. */
export function resetGuideProgressV2(): void {
  const cur = useOnboardingState.getState().ob;
  const keptSeen: Record<string, boolean> = {};
  const keptCounts: Record<string, number> = {};
  for (const id of Object.keys(cur.guideRetired)) {
    if (!cur.guideRetired[id]) continue;
    if (cur.guideSeen[id]) keptSeen[id] = true;
    if (cur.guideDisplayCounts[id] != null) keptCounts[id] = cur.guideDisplayCounts[id];
  }
  const next: OnboardingPersisted = {
    ...cur,
    guideDismissed: false,
    guideTourCompleted: false,
    guideSeen: keptSeen,
    guideDisplayCounts: keptCounts,
  };
  useOnboardingState.setState({ ob: next });
  AsyncStorage.setItem(OB_KEY, JSON.stringify(next)).catch(() => {
    /* non-fatal — worst case the re-enable lasts only this session */
  });
}

/** FULL replace (defaults + given state) — the Test Stages QA tool uses
 *  this to materialize a device at an exact adoption stage. Not for
 *  product code: everything else patches. */
export function replaceOnboardingState(state: Partial<OnboardingPersisted>): void {
  const next = mergeState(DEFAULTS, state);
  useOnboardingState.setState({ ob: next });
  AsyncStorage.setItem(OB_KEY, JSON.stringify(next)).catch(() => {});
}
