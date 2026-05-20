import React, { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  Share,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { useFeedback, formatFeedbackAsMarkdown, type FeedbackItem } from '../state/useFeedback';
import { relativeTime } from '../utils/relativeTime';

const SEV_LABEL: Record<FeedbackItem['severity'], string> = {
  bug:    '🐞 Bug',
  polish: '✨ Polish',
  idea:   '💡 Idea',
};

// Settings → Test feedback → this screen.
// Lists every captured feedback note in newest-first order. The header
// has two destructive-ish actions:
//   • Share — opens the iOS share sheet with the inbox formatted as
//     markdown so the user can AirDrop / email / paste back into chat.
//   • Clear — wipes everything (with a confirm).
export default function FeedbackInboxScreen() {
  const items   = useFeedback((s) => s.items);
  const hydrate = useFeedback((s) => s.hydrate);
  const remove  = useFeedback((s) => s.remove);
  const clear   = useFeedback((s) => s.clear);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  async function onShare() {
    const md = formatFeedbackAsMarkdown(items);
    try {
      await Share.share({ message: md });
    } catch {
      /* user cancelled — ignore */
    }
  }

  function onClear() {
    if (items.length === 0) return;
    Alert.alert(
      'Clear all feedback?',
      `This will delete ${items.length} note${items.length === 1 ? '' : 's'}. Cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Clear', style: 'destructive', onPress: () => void clear() },
      ],
    );
  }

  function onDelete(item: FeedbackItem) {
    Alert.alert(
      'Delete note?',
      item.text.slice(0, 80) + (item.text.length > 80 ? '…' : ''),
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: () => void remove(item.id) },
      ],
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <View style={styles.headerRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Test feedback</Text>
          <Text style={styles.sub}>
            {items.length} note{items.length === 1 ? '' : 's'} saved on this device
          </Text>
        </View>
        <Pressable
          onPress={onShare}
          disabled={items.length === 0}
          style={({ pressed }) => [
            styles.btn,
            styles.btnPrimary,
            items.length === 0 && styles.btnDisabled,
            pressed && items.length > 0 && { opacity: 0.85 },
          ]}
        >
          <Text style={styles.btnPrimaryText}>Share</Text>
        </Pressable>
        <Pressable
          onPress={onClear}
          disabled={items.length === 0}
          style={({ pressed }) => [
            styles.btn,
            styles.btnGhost,
            items.length === 0 && styles.btnDisabled,
            pressed && items.length > 0 && { opacity: 0.85 },
          ]}
        >
          <Text style={styles.btnGhostText}>Clear</Text>
        </Pressable>
      </View>

      {items.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyEmoji}>📝</Text>
          <Text style={styles.emptyTitle}>No feedback yet</Text>
          <Text style={styles.emptySub}>
            Tap the floating <Text style={{ fontWeight: '800' }}>📝</Text> button on any screen to capture a note.
          </Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}
        >
          {items.map((it) => (
            <Pressable
              key={it.id}
              onLongPress={() => onDelete(it)}
              style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }]}
            >
              <View style={styles.cardHeader}>
                <Text style={styles.cardSev}>{SEV_LABEL[it.severity]}</Text>
                <Text style={styles.cardWhen}>{relativeTime(it.created_at)}</Text>
              </View>
              <Text style={styles.cardScreen}>{it.screen}</Text>
              <Text style={styles.cardText}>{it.text}</Text>
              <Text style={styles.cardHint}>Long-press to delete</Text>
            </Pressable>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },

  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: spacing.sm,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  title: { color: colors.text,  fontSize: fontSize.xl, fontWeight: '800' },
  sub:   { color: colors.muted, fontSize: fontSize.xs },

  btn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
  },
  btnPrimary: { backgroundColor: colors.accent },
  btnGhost:   { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.border },
  btnDisabled: { opacity: 0.4 },
  btnPrimaryText: { color: '#fff',        fontSize: fontSize.sm, fontWeight: '800' },
  btnGhostText:   { color: colors.muted,  fontSize: fontSize.sm, fontWeight: '700' },

  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  emptyEmoji: { fontSize: 48, marginBottom: spacing.md },
  emptyTitle: { color: colors.text, fontSize: fontSize.lg, fontWeight: '700', marginBottom: 6 },
  emptySub:   { color: colors.muted, fontSize: fontSize.sm, textAlign: 'center', lineHeight: 20 },

  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.md,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  cardSev:    { color: colors.accent, fontSize: fontSize.sm, fontWeight: '800' },
  cardWhen:   { color: colors.muted,  fontSize: fontSize.xs },
  cardScreen: { color: colors.muted,  fontSize: fontSize.xs, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.4, fontWeight: '700' },
  cardText:   { color: colors.text,   fontSize: fontSize.sm, lineHeight: 20 },
  cardHint:   { color: colors.muted,  fontSize: 10, marginTop: 6, fontStyle: 'italic' },
});
