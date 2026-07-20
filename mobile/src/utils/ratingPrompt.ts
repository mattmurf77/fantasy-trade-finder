import AsyncStorage from '@react-native-async-storage/async-storage';
import * as StoreReview from 'expo-store-review';
import Constants from 'expo-constants';
import { useFeatureFlags, onboardingEnabled } from '../state/useFeatureFlags';
import { getOnboardingState, patchOnboardingState } from '../state/useOnboardingState';
import { useFeedback } from '../state/useFeedback';
import { track } from '../api/events';

// App Store rating prompt gate (teardown S7 PRD-02, flag
// `growth.rating_prompt`). One entry point: `maybeRequestReview(trigger)`,
// called at demonstrated-satisfaction moments (primary trigger: first
// successful Send-in-Sleeper). The OS decides whether a dialog actually
// appears — we only instrument the REQUEST (`rating_prompt_requested`).
//
// Gate (ALL must pass, checked in order — cheapest first):
//   1. flag `growth.rating_prompt` on (dark until GA)
//   2. sessionCount ≥ 5 (persisted onboarding store; incremented every cold
//      start in App.tsx, so it counts for all users, onboarding flags aside)
//   3. ≥ 7 days since the anchor timestamp. The anchor is minted on the
//      FIRST gate evaluation (there is no install-time hook we own), so the
//      clock starts at the first satisfaction moment — strictly more
//      conservative than install-time, never less.
//   4. not already requested for this app version (persisted
//      `ratingPromptShownVersion` in the onboarding store)
//   5. no feedback captured in the last 7 days (unhappy-user diversion —
//      proxy for "FeedbackSheet not opened recently": we can only observe
//      submissions, which is the stronger unhappiness signal anyway)
//   6. never during onboarding first-run (trades-first active and the user
//      hasn't completed their first swipe)
//
// Returns true iff the StoreReview request was actually issued.

const ANCHOR_KEY = 'ftf.rating.anchor_ts.v1';
const MIN_SESSIONS = 5;
const MIN_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const FEEDBACK_QUIET_MS = 7 * 24 * 60 * 60 * 1000;

function appVersion(): string {
  return Constants.expoConfig?.version ?? 'unknown';
}

export async function maybeRequestReview(trigger: string): Promise<boolean> {
  try {
    // 1. Flag — dark by default; flip at GA.
    if (useFeatureFlags.getState().flags['growth.rating_prompt'] !== true) {
      return false;
    }

    const ob = getOnboardingState();

    // 2. Session floor (also guarantees "never session one").
    if (ob.sessionCount < MIN_SESSIONS) return false;

    // 6. Never during the onboarding first-run.
    if (onboardingEnabled('onboarding.trades_first') && !ob.firstSwipeDone) {
      return false;
    }

    // 4. Once per version.
    const version = appVersion();
    if (ob.ratingPromptShownVersion === version) return false;

    // 3. Age anchor — mint on first evaluation, then require 7 days.
    const now = Date.now();
    let anchorRaw: string | null = null;
    try {
      anchorRaw = await AsyncStorage.getItem(ANCHOR_KEY);
    } catch {
      /* storage unavailable — treat as unset */
    }
    const anchor = anchorRaw ? Number(anchorRaw) : NaN;
    if (!Number.isFinite(anchor)) {
      AsyncStorage.setItem(ANCHOR_KEY, String(now)).catch(() => {});
      return false;
    }
    if (now - anchor < MIN_AGE_MS) return false;

    // 5. Recent feedback → route the pressure valve, not the prompt.
    const recentFeedback = useFeedback
      .getState()
      .items.some((i) => {
        const ts = Date.parse(i.created_at);
        return Number.isFinite(ts) && now - ts < FEEDBACK_QUIET_MS;
      });
    if (recentFeedback) return false;

    // All gates passed — persist BEFORE requesting so a crash mid-request
    // can't double-fire this version, then hand off to the OS.
    patchOnboardingState({ ratingPromptShownVersion: version });
    track('rating_prompt_requested', { trigger, version });
    if (await StoreReview.isAvailableAsync()) {
      await StoreReview.requestReview();
      return true;
    }
    return false;
  } catch {
    // Rating is never worth breaking product UX over.
    return false;
  }
}
