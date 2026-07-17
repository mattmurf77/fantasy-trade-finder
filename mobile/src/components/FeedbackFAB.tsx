import React, { useEffect, useState } from 'react';
import { Pressable, Text, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ink, chalk, semantic, radii, fonts, shadowSheet } from '../theme/chalkline';
import { Icon } from './chalkline';
import FeedbackSheet from './FeedbackSheet';
import { useFeedback } from '../state/useFeedback';

interface Props {
  // Best-effort label of the active screen. Owned by the parent so the
  // FAB itself stays free of navigation-state coupling.
  activeScreen: string;
}

// Floating action button — sits bottom-right above the tab bar on every
// authed screen during TestFlight. Tap opens the FeedbackSheet, pre-
// populated with the screen name.
//
// The count pill shows the inbox count so the user can see at a glance
// how much feedback is pending export. Tap the count to jump to inbox
// directly; tap the body to open the capture sheet.
export default function FeedbackFAB({ activeScreen }: Props) {
  const insets = useSafeAreaInsets();
  const items  = useFeedback((s) => s.items);
  const hydrate = useFeedback((s) => s.hydrate);
  const [sheetOpen, setSheetOpen] = useState(false);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  return (
    <>
      <View
        pointerEvents="box-none"
        style={[
          styles.wrap,
          // Sit above the bottom tab bar (~ 52pt) + safe area inset.
          { bottom: insets.bottom + 64 },
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
