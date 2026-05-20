import React, { useEffect, useState } from 'react';
import { Pressable, Text, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors } from '../theme/colors';
import { radius } from '../theme/spacing';
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
// The "📝 N" pill shows the inbox count so the user can see at a glance
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
          onPress={() => setSheetOpen(true)}
          style={({ pressed }) => [styles.fab, pressed && styles.pressed]}
          accessibilityLabel="Capture feedback"
        >
          <Text style={styles.fabText}>📝</Text>
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
    borderRadius: 26,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 6, // Android shadow
  },
  pressed: { opacity: 0.85, transform: [{ scale: 0.96 }] },
  fabText: { fontSize: 22, color: '#fff' },
  badge: {
    position: 'absolute',
    top: -4,
    right: -4,
    minWidth: 22,
    height: 22,
    paddingHorizontal: 6,
    borderRadius: 11,
    backgroundColor: colors.red,
    borderWidth: 2,
    borderColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: { color: '#fff', fontSize: 11, fontWeight: '800' },
});
