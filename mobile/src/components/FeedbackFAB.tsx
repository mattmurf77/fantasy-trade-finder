import React, { useEffect, useState } from 'react';
import { Pressable, Text, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ink, chalk, semantic, radii, fonts, shadowSheet } from '../theme/chalkline';
import { Icon } from './chalkline';
import FeedbackSheet from './FeedbackSheet';
import { useFeedback } from '../state/useFeedback';
import { useFlag } from '../state/useFeatureFlags';

interface Props {
  // Best-effort label of the active screen. Owned by the parent so the
  // FAB itself stays free of navigation-state coupling.
  activeScreen: string;
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
// The count pill shows the inbox count so the user can see at a glance
// how much feedback is pending export. Tap the count to jump to inbox
// directly; tap the body to open the capture sheet.
//
// Production-build exclusion (S3 PRD-01 item 3 — PLANNED, not implemented
// here): the existing removal note lives at the RootNav mount site
// (RootNav.tsx "Remove this <FeedbackFAB /> line…"). The durable plan is a
// build-time gate — an EAS build-profile env (e.g. EXPO_PUBLIC_TESTFLIGHT)
// checked at the mount site so App Store builds compile the FAB out
// entirely rather than hiding it at runtime. That change belongs to the
// RootNav owner + release config, not this component.
export default function FeedbackFAB({ activeScreen }: Props) {
  const insets = useSafeAreaInsets();
  const items  = useFeedback((s) => s.items);
  const hydrate = useFeedback((s) => s.hydrate);
  const [sheetOpen, setSheetOpen] = useState(false);
  // S3 PRD-01 — content-aware offset. Flag off → 0 extra offset always.
  const touchPolish = useFlag('ux.touch_polish');
  const [barHeight, setBarHeight] = useState(() => maxBarHeight());

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

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

  return (
    <>
      <View
        pointerEvents="box-none"
        style={[
          styles.wrap,
          // Sit above the bottom tab bar (~ 52pt) + safe area inset, plus
          // any pinned bottom bar the focused screen reported (flag-gated).
          { bottom: insets.bottom + 64 + extraOffset },
        ]}
      >
        <Pressable
          testID="feedback.fab"
          onPress={() => setSheetOpen(true)}
          style={({ pressed }) => [styles.fab, pressed && styles.pressed]}
          accessibilityLabel="Capture feedback"
        >
          <Icon name="flag" size={20} color={chalk.base} />
          {items.length > 0 ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{items.length}</Text>
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
