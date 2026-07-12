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
import { ink, chalk, ice, semantic, space, radii, type, fonts, shadowSheet, scrim } from '../theme/chalkline';
import { Icon, Button } from './chalkline';
import { useNotifications } from '../state/useNotifications';
import { relativeTime } from '../utils/relativeTime';
// Circular at module-load (TopBar ← TabNav ← RootNav), but `navigationRef`
// is a top-level const created at RootNav import time and only *read*
// lazily inside onPress below. If you refactor navigationRef into the
// component body, this circular import will break silently.
import { navigationRef } from '../navigation/RootNav';

// Global top bar that sits above the tab navigator. Chalkline TopNav:
// wordmark (ice tick + condensed caps) on the left, settings + bell icon
// buttons on the right. The bell shows an unread count when new pushes have
// arrived since the user last opened the sheet.
//
// Sized at 44pt + the system top inset so it sits flush under the status
// bar without overlapping screen content. Screens below this should opt
// out of the top safe-area inset (e.g. SafeAreaView edges={['bottom']})
// so we don't double-pad.
export const TOP_BAR_HEIGHT = 44;

// Backend used to prefix match-notification bodies with an emoji that's
// already conveyed by the visual icon badge — so it would render twice.
// Backend stopped emitting the prefix in PR #13 (commit 397d8f1), but
// older notifications already in the DB still carry it. Strip leading
// type-icon emojis defensively so re-deliveries / DB residue look clean.
// Mirrors the regex in web/js/app.js _renderNotifList.
const LEADING_TYPE_EMOJI_RE = /^\s*(?:🤝|✅|❌|🎯|🔔)\s*/u;
function stripLeadingTypeEmoji(body: string): string {
  return body.replace(LEADING_TYPE_EMOJI_RE, '');
}

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
          <View style={styles.wordmark}>
            <View style={styles.wordmarkTick} />
            <Text style={styles.wordmarkText}>Trade Finder</Text>
          </View>
          <View style={styles.actions}>
            <Pressable
              onPress={() => {
                if (navigationRef.isReady()) {
                  navigationRef.navigate('Settings');
                }
              }}
              hitSlop={12}
              style={({ pressed }) => [
                styles.iconBtn,
                { marginRight: space.sm },
                pressed && styles.iconBtnPressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel="Settings"
              testID="topbar.settings"
            >
              <Icon name="settings" color={chalk.dim} />
            </Pressable>
            <Pressable
              onPress={openSheet}
              hitSlop={12}
              style={({ pressed }) => [
                styles.iconBtn,
                pressed && styles.iconBtnPressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel={
                unreadCount > 0
                  ? `Notifications, ${unreadCount} unread`
                  : 'Notifications'
              }
            >
              <Icon name="bell" color={chalk.dim} />
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
            <Text style={type.heading}>Notifications</Text>
            {items.length > 0 && (
              <Button
                label="Clear all"
                variant="ghost"
                compact
                onPress={() => {
                  clearAll();
                  setOpen(false);
                }}
              />
            )}
          </View>

          {items.length === 0 ? (
            <View style={styles.empty}>
              <Icon name="bell" size={32} color={chalk.faint} />
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
                  {it.body ? (
                    <Text style={styles.itemBody}>{stripLeadingTypeEmoji(it.body)}</Text>
                  ) : null}
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
    backgroundColor: ink.ink0,
    borderBottomColor: ink.line,
    borderBottomWidth: 1,
  },
  row: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.md,
  },
  wordmark: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  wordmarkTick: { width: 3, height: 14, backgroundColor: ice.base },
  wordmarkText: {
    fontFamily: fonts.displaySemi,
    fontSize: 16,
    letterSpacing: 0.48,
    textTransform: 'uppercase',
    color: chalk.base,
  },
  actions: { flexDirection: 'row', alignItems: 'center' },
  iconBtn: {
    width: 36,
    height: 36,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  iconBtnPressed: { backgroundColor: ink.ink3 },
  dot: {
    position: 'absolute',
    top: -2,
    right: -2,
    minWidth: 18,
    height: 18,
    borderRadius: radii.pill,
    backgroundColor: semantic.neg,
    paddingHorizontal: 4,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: ink.ink0,
  },
  dotText: { color: chalk.base, fontFamily: fonts.data, fontSize: 10 },

  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: scrim,
  },
  sheet: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    maxHeight: '80%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  handle: {
    alignSelf: 'center',
    width: 32, height: 4, borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  sheetHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  list: { maxHeight: 480 },
  item: {
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    paddingVertical: space.md,
    gap: 4,
  },
  itemTitle: type.title,
  itemBody:  type.bodySm,
  itemTime:  { fontFamily: fonts.data, fontSize: 11, fontVariant: ['tabular-nums'], color: chalk.faint, marginTop: 4 },

  empty: {
    paddingVertical: space.xxl,
    alignItems: 'center',
    gap: space.sm,
  },
  emptyTitle: type.heading,
  emptyBody: {
    ...type.bodySm,
    textAlign: 'center',
  },
});
