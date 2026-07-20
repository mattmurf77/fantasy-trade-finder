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
  applePromptShownFor: {},
  applePromptDeclined: false,
  appleSession2BannerShown: false,
  coachMarksShown: {},
  celebrationsShown: {},
  guideDismissed: false,
  guideSeen: {},
  guideTourCompleted: false,
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

/** FULL replace (defaults + given state) — the Test Stages QA tool uses
 *  this to materialize a device at an exact adoption stage. Not for
 *  product code: everything else patches. */
export function replaceOnboardingState(state: Partial<OnboardingPersisted>): void {
  const next = mergeState(DEFAULTS, state);
  useOnboardingState.setState({ ob: next });
  AsyncStorage.setItem(OB_KEY, JSON.stringify(next)).catch(() => {});
}
