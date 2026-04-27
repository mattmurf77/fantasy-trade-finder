import React, { useState } from 'react';
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  Modal,
  ScrollView,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { useNotifications } from '../state/useNotifications';
import { relativeTime } from '../utils/relativeTime';
// Circular at module-load (TopBar ← TabNav ← RootNav), but `navigationRef`
// is a top-level const created at RootNav import time and only *read*
// lazily inside onPress below. If you refactor navigationRef into the
// component body, this circular import will break silently.
import { navigationRef } from '../navigation/RootNav';

// Global top bar that sits above the tab navigator. The only widget today
// is the floating notifications bell on the right — it shows an unread
// dot when new pushes have arrived since the user last opened the sheet.
//
// Sized at 44pt + the system top inset so it sits flush under the status
// bar without overlapping screen content. Screens below this should opt
// out of the top safe-area inset (e.g. SafeAreaView edges={['bottom']})
// so we don't double-pad.
export const TOP_BAR_HEIGHT = 44;

export default function TopBar() {
  const insets = useSafeAreaInsets();
  const items       = useNotifications((s) => s.items);
  const unreadCount = useNotifications((s) => s.unreadCount);
  const markAllRead = useNotifications((s) => s.markAllRead);
  const clearAll    = useNotifications((s) => s.clear);
  const [open, setOpen] = useState(false);

  const openSheet = () => {
    setOpen(true);
    // Mark read when the sheet is opened so the dot disappears.
    markAllRead();
  };

  return (
    <>
      <View
        style={[
          styles.bar,
          { paddingTop: insets.top, height: insets.top + TOP_BAR_HEIGHT },
        ]}
      >
        <View style={styles.row}>
          <Pressable
            onPress={() => {
              if (navigationRef.isReady()) {
                // @ts-expect-error — top-level Settings route on AuthStack
                navigationRef.navigate('Settings');
              }
            }}
            hitSlop={12}
            style={({ pressed }) => [
              styles.bellBtn,
              { marginRight: spacing.sm },
              pressed && { opacity: 0.7 },
            ]}
            accessibilityRole="button"
            accessibilityLabel="Settings"
          >
            <Text style={styles.bellEmoji}>⚙️</Text>
          </Pressable>
          <Pressable
            onPress={openSheet}
            hitSlop={12}
            style={({ pressed }) => [
              styles.bellBtn,
              pressed && { opacity: 0.7 },
            ]}
            accessibilityRole="button"
            accessibilityLabel={
              unreadCount > 0
                ? `Notifications, ${unreadCount} unread`
                : 'Notifications'
            }
          >
            <Text style={styles.bellEmoji}>🔔</Text>
            {unreadCount > 0 && (
              <View style={styles.dot}>
                <Text style={styles.dotText}>
                  {unreadCount > 9 ? '9+' : String(unreadCount)}
                </Text>
              </View>
            )}
          </Pressable>
        </View>
      </View>

      <Modal
        visible={open}
        transparent
        animationType="slide"
        onRequestClose={() => setOpen(false)}
      >
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)} />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <View style={styles.sheetHead}>
            <Text style={styles.sheetTitle}>Notifications</Text>
            {items.length > 0 && (
              <Pressable
                onPress={() => {
                  clearAll();
                  setOpen(false);
                }}
                hitSlop={8}
              >
                <Text style={styles.clearText}>Clear all</Text>
              </Pressable>
            )}
          </View>

          {items.length === 0 ? (
            <View style={styles.empty}>
              <Text style={styles.emptyEmoji}>🛎️</Text>
              <Text style={styles.emptyTitle}>You're all caught up</Text>
              <Text style={styles.emptyBody}>
                Trade matches and other alerts will appear here.
              </Text>
            </View>
          ) : (
            <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
              {items.map((it) => (
                <View key={it.id} style={styles.item}>
                  <Text style={styles.itemTitle}>{it.title}</Text>
                  {it.body ? <Text style={styles.itemBody}>{it.body}</Text> : null}
                  <Text style={styles.itemTime}>
                    {relativeTime(new Date(it.receivedAt).toISOString())}
                  </Text>
                </View>
              ))}
            </ScrollView>
          )}
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  bar: {
    width: '100%',
    backgroundColor: colors.bg,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  row: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
  },
  bellBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  bellEmoji: { fontSize: 18 },
  dot: {
    position: 'absolute',
    top: -2,
    right: -2,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: colors.red,
    paddingHorizontal: 4,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.bg,
  },
  dotText: { color: '#fff', fontSize: 10, fontWeight: '800' },

  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  sheet: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    maxHeight: '80%',
    backgroundColor: colors.bg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.sm,
  },
  handle: {
    alignSelf: 'center',
    width: 44, height: 4, borderRadius: 2,
    backgroundColor: colors.border,
    marginBottom: spacing.sm,
  },
  sheetHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sheetTitle: { color: colors.text, fontSize: fontSize.xl, fontWeight: '800' },
  clearText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '700' },
  list: { maxHeight: 480 },
  item: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: 4,
  },
  itemTitle: { color: colors.text,  fontSize: fontSize.base, fontWeight: '800' },
  itemBody:  { color: colors.muted, fontSize: fontSize.sm,   lineHeight: 20 },
  itemTime:  { color: colors.muted, fontSize: fontSize.xs,   marginTop: 4 },

  empty: {
    paddingVertical: spacing.xxl,
    alignItems: 'center',
    gap: spacing.sm,
  },
  emptyEmoji: { fontSize: 36 },
  emptyTitle: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },
  emptyBody: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    lineHeight: 22,
  },
});
