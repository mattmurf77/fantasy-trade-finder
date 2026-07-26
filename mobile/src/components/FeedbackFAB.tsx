import React, { useEffect, useState } from 'react';
import { Pressable, Text, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ink, chalk, semantic, radii, fonts, shadowSheet } from '../theme/chalkline';
import { Icon } from './chalkline';
import FeedbackSheet from './FeedbackSheet';
import { useFeedback } from '../state/useFeedback';
import { openFeedbackCount } from '../utils/feedbackBadge';
import { useFlag } from '../state/useFeatureFlags';

interface Props {
  // Best-effort label of the active screen. Owned by the parent so the
  // FAB itself stays free of navigation-state coupling.
  activeScreen: string;
  // #188 mount pattern: the RootNav mount floats above the Main tab bar
  // (default). Root-stack screens pushed OVER Main (FreeAgents,
  // LeagueSummary, …) cover that mount, so they render their own FAB with
  // aboveTabBar={false} — no tab bar underneath, smaller bottom offset.
  aboveTabBar?: boolean;
}

// ── Pinned-bottom-bar registry (teardown S3 PRD-01, flag `ux.touch_polish`) ──
// Screens with a pinned bottom action bar (Tiers save bar, Quick set /
// Quick rank footers) report the bar's occupied height here so the FAB can
// rise above it instead of covering the primary CTA (screenshot-confirmed
// overlap on the Save-tiers button). Module-scope pub/sub — the FAB is
// mounted once in RootNav, screens are the writers.
//
// Rules for reporters:
//   • Report ONLY while focused (stack/tab screens stay mounted when
//     backgrounded — an unfocused Tiers board must not offset the FAB on
//     the Trades tab). Use useIsFocused().
//   • Report 0 (or call with 0) on blur/unmount.
//   • The FAB takes the MAX across keys — overlapping reporters don't sum.
// Flag off: the registry still accepts writes but the FAB ignores them —
// byte-identical rendering.
const barListeners = new Set<(h: number) => void>();
const barHeights = new Map<string, number>();

function maxBarHeight(): number {
  let max = 0;
  for (const h of barHeights.values()) if (h > max) max = h;
  return max;
}

/** Screens call this with the height their pinned bottom bar occupies
 *  (measured from the screen's bottom edge). 0 clears the entry. */
export function setPinnedBottomBarHeight(key: string, height: number) {
  if (height <= 0) barHeights.delete(key);
  else barHeights.set(key, height);
  const h = maxBarHeight();
  barListeners.forEach((l) => l(h));
}

// Floating action button — sits bottom-right above the tab bar on every
// authed screen during TestFlight. Tap opens the FeedbackSheet, pre-
// populated with the screen name.
//
// Mount pattern (#188): mounted once in RootNav's Main screen (covers every
// TAB screen), plus once per root-stack push that covers Main (those cards
// render above the RootNav mount — FreeAgents, LeagueSummary's legacy push
// variant, etc. mount their own with aboveTabBar={false}). Multiple mounts
// are safe: hydrate() is idempotent and only the topmost card's FAB is
// visible. Exceptions (no FAB): modals/sheets and onboarding flows — see
// the root CLAUDE.md convention.
//
// The count pill shows how many notes are still awaiting action (#184):
// closed notes (shipped/declined or no longer served to this account) and
// resolved statuses (fixed/shipped/declined) don't count — otherwise a
// long-time tester stares at "150+" forever. The inbox LIST still shows
// 'fixed' notes ("Fixed — in next update"); only the badge excludes them.
//
// Production-build exclusion (S3 PRD-01 item 3 — PLANNED, not implemented
// here): the existing removal note lives at the RootNav mount site
// (RootNav.tsx "Remove this <FeedbackFAB /> line…"). The durable plan is a
// build-time gate — an EAS build-profile env (e.g. EXPO_PUBLIC_TESTFLIGHT)
// checked at the mount site so App Store builds compile the FAB out
// entirely rather than hiding it at runtime. That change belongs to the
// RootNav owner + release config, not this component.
export default function FeedbackFAB({ activeScreen, aboveTabBar = true }: Props) {
  const insets = useSafeAreaInsets();
  const items  = useFeedback((s) => s.items);
  const hydrate = useFeedback((s) => s.hydrate);
  const refreshStatuses = useFeedback((s) => s.refreshStatuses);
  const [sheetOpen, setSheetOpen] = useState(false);
  // S3 PRD-01 — content-aware offset. Flag off → 0 extra offset always.
  const touchPolish = useFlag('ux.touch_polish');
  const [barHeight, setBarHeight] = useState(() => maxBarHeight());

  useEffect(() => {
    // Hydrate the local notes, then pull operator-set statuses so the badge
    // drops for closed/resolved notes without the user opening the inbox
    // (#184). refreshStatuses is best-effort and silent on failure; the FAB
    // mounts once in RootNav, so this is one GET per launch.
    void hydrate().then(() => refreshStatuses());
  }, [hydrate, refreshStatuses]);

  useEffect(() => {
    const listener = (h: number) => setBarHeight(h);
    barListeners.add(listener);
    // Sync in case a screen reported between first render and subscribe.
    setBarHeight(maxBarHeight());
    return () => {
      barListeners.delete(listener);
    };
  }, []);

  const extraOffset = touchPolish ? barHeight : 0;
  const openCount = openFeedbackCount(items);

  return (
    <>
      <View
        pointerEvents="box-none"
        style={[
          styles.wrap,
          // Sit above the bottom tab bar (~ 52pt) + safe area inset, plus
          // any pinned bottom bar the focused screen reported (flag-gated).
          // Root-stack pushes have no tab bar → smaller offset (#188).
          { bottom: insets.bottom + (aboveTabBar ? 64 : 16) + extraOffset },
        ]}
      >
        <Pressable
          testID="feedback.fab"
          onPress={() => setSheetOpen(true)}
          style={({ pressed }) => [styles.fab, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel={
            openCount > 0
              ? `Capture feedback, ${openCount} open`
              : 'Capture feedback'
          }
        >
          <Icon name="flag" size={20} color={chalk.base} />
          {openCount > 0 ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{openCount}</Text>
            </View>
          ) : null}
        </Pressable>
      </View>

      <FeedbackSheet
        visible={sheetOpen}
        onClose={() => setSheetOpen(false)}
        defaultScreen={activeScreen}
      />
    </>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    right: 16,
    // bottom set dynamically with safe area inset
  },
  fab: {
    width: 52,
    height: 52,
    borderRadius: radii.md,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadowSheet,
  },
  // Pressed state = surface color change only (no scale/translate).
  pressed: { backgroundColor: ink.ink3 },
  badge: {
    position: 'absolute',
    top: -4,
    right: -4,
    minWidth: 22,
    height: 22,
    paddingHorizontal: 6,
    borderRadius: radii.pill,
    backgroundColor: semantic.neg,
    borderWidth: 2,
    borderColor: ink.ink0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: {
    color: chalk.base,
    fontFamily: fonts.data,
    fontSize: 11,
    fontVariant: ['tabular-nums'],
  },
});
