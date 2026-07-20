import { useCallback, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { useFlag } from '../state/useFeatureFlags';

// What's-new surface (teardown S7 PRD-04 item 5, flag `ux.whats_new`).
//
// Contract:
//   • ONE versioned entry per release, keyed by the app version
//     (Constants.expoConfig.version — the same source Sentry uses for its
//     release tag, so the key can never drift from the shipped build).
//   • Shown once per version: dismissal persists the version string to
//     AsyncStorage; the entry never re-renders for that version.
//   • Rendered as a single CoachMark-style INLINE tip anchored in the
//     League tab (LeagueScreen) — never a modal, never stacked (same rules
//     as the onboarding CoachMark it borrows its construction from).
//   • `route`, when present, is a react-navigation route name the anchor
//     screen navigates to on tap (tap = "show me" + dismiss). Absent →
//     tap just dismisses.
//
// Adding a release note = adding one WHATS_NEW entry for the new version
// in the same change that bumps app.json's version. Releases without an
// entry simply show nothing — no fallback copy, no placeholder UI.

export interface WhatsNewEntry {
  /** Short headline — one line, no period ("New: board search on Tiers"). */
  headline: string;
  /** Optional deep link: route name navigated to on tap (see contract). */
  route?: string;
}

// version → entry. ONE entry per release, matching app.json's `version`.
const WHATS_NEW: Record<string, WhatsNewEntry> = {
  // Placeholder for the teardown-remediation branch — replace the copy
  // when the branch's release notes are settled.
  '1.9.1': {
    headline: 'New: search your boards — find any player on Tiers and Overall Ranks.',
  },
};

const SEEN_KEY = 'ftf_whats_new_seen_version';
const APP_VERSION: string | null = Constants.expoConfig?.version ?? null;

/**
 * Returns the current release's what's-new entry (or null when the flag is
 * off, the version has no entry, or this version was already dismissed)
 * plus the dismiss handler the anchor screen calls on tap.
 */
export function useWhatsNew(): { entry: WhatsNewEntry | null; dismiss: () => void } {
  const enabled = useFlag('ux.whats_new');
  // undefined = AsyncStorage not hydrated yet — render nothing until the
  // read lands so an already-seen tip never flashes on mount.
  const [seenVersion, setSeenVersion] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    if (!enabled) return; // flag off — skip the storage read entirely
    let canceled = false;
    AsyncStorage.getItem(SEEN_KEY)
      .then((v) => {
        if (!canceled) setSeenVersion(v);
      })
      .catch(() => {
        // Read failure — treat as unseen; worst case the tip shows again.
        if (!canceled) setSeenVersion(null);
      });
    return () => {
      canceled = true;
    };
  }, [enabled]);

  const dismiss = useCallback(() => {
    if (!APP_VERSION) return;
    setSeenVersion(APP_VERSION);
    AsyncStorage.setItem(SEEN_KEY, APP_VERSION).catch(() => {
      /* persist is best-effort — in-memory state hides it this session */
    });
  }, []);

  const entry =
    enabled &&
    APP_VERSION != null &&
    seenVersion !== undefined &&
    seenVersion !== APP_VERSION
      ? WHATS_NEW[APP_VERSION] ?? null
      : null;

  return { entry, dismiss };
}
