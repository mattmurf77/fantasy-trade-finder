import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  Share,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ink, chalk, ice, flare, semantic, space, type, fonts } from '../theme/chalkline';
import { Button, Icon } from '../components/chalkline';
import { useFeedback, formatFeedbackAsMarkdown, type FeedbackItem } from '../state/useFeedback';
import type { FeedbackStatus } from '../api/feedback';
import { relativeTime } from '../utils/relativeTime';

const SEV_LABEL: Record<FeedbackItem['severity'], string> = {
  bug:    'Bug',
  polish: 'Polish',
  idea:   'Idea',
};

// Operator-set lifecycle status → user-facing chip. Vocabulary mirrors
// the backend's FEEDBACK_STATUSES (docs/cross-client-invariants.md).
const STATUS_LABEL: Record<FeedbackStatus, string> = {
  new:         'Received',
  planned:     'Planned',
  in_progress: 'In progress',
  fixed:       'Fixed — in next update',
  shipped:     'Shipped',
  declined:    'Not planned',
};
const STATUS_COLOR: Record<FeedbackStatus, string> = {
  new:         chalk.dim,
  planned:     chalk.base,
  in_progress: semantic.warn,
  fixed:       semantic.pos,
  shipped:     semantic.pos,
  declined:    chalk.faint,
};

// Settings → Test feedback → this screen.
// Lists every captured feedback note in newest-first order. The header
// has two destructive-ish actions:
//   • Share — opens the iOS share sheet with the inbox formatted as
//     markdown so the user can AirDrop / email / paste back into chat.
//   • Clear — wipes everything (with a confirm).
export default function FeedbackInboxScreen() {
  const items     = useFeedback((s) => s.items);
  const hydrate   = useFeedback((s) => s.hydrate);
  const remove    = useFeedback((s) => s.remove);
  const clear     = useFeedback((s) => s.clear);
  const retrySync = useFeedback((s) => s.retrySync);
  const refreshStatuses = useFeedback((s) => s.refreshStatuses);

  const [retrying, setRetrying] = useState(false);
  const unsyncedCount = items.filter((i) => !i.synced).length;
  // Closed notes (shipped/declined, or no longer served to this account)
  // are hidden from the inbox entirely — the local copy stays in storage
  // for sync bookkeeping, it just doesn't render.
  const visibleItems = items.filter((i) => !i.closed);

  useEffect(() => {
    // Hydrate local notes first, then pull operator-set statuses from the
    // backend (best-effort; merges by server_id/client_id).
    void hydrate().then(() => refreshStatuses());
  }, [hydrate, refreshStatuses]);

  async function onRetry() {
    if (retrying || unsyncedCount === 0) return;
    setRetrying(true);
    try {
      await retrySync();
    } finally {
      setRetrying(false);
    }
  }

  async function onShare() {
    const md = formatFeedbackAsMarkdown(visibleItems);
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
            <Text style={styles.subCount}>{visibleItems.length}</Text>
            {` note${visibleItems.length === 1 ? '' : 's'} saved on this device`}
          </Text>
        </View>
        {unsyncedCount > 0 &&
          (retrying ? (
            <View style={styles.retrySpinner}>
              <ActivityIndicator size="small" color={chalk.dim} />
            </View>
          ) : (
            <Button label="Retry sync" variant="ghost" onPress={onRetry} />
          ))}
        <Button
          label="Share"
          variant="primary"
          onPress={onShare}
          disabled={visibleItems.length === 0}
        />
        <Button
          label="Clear"
          variant="ghost"
          onPress={onClear}
          disabled={items.length === 0}
        />
      </View>

      {visibleItems.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>No feedback yet</Text>
          <Text style={styles.emptySub}>
            Tap the floating button on any screen to capture a note.
          </Text>
        </View>
      ) : (
        <ScrollView>
          {visibleItems.map((it) => {
            // Three visual states for the sync badge. Failed = there was
            // a sync attempt that errored; Pending = never attempted yet
            // OR the previous attempt is in flight. We can't distinguish
            // those two from state alone, so we lean on last_sync_error
            // as the proxy for "we tried and it didn't work".
            const failed = !it.synced && !!it.last_sync_error;
            const syncStyle =
              it.synced ? styles.syncSynced :
              failed    ? styles.syncFailed :
                          styles.syncPending;
            const syncText =
              it.synced ? 'Synced' :
              failed    ? `Sync failed: ${it.last_sync_error}` :
                          'Pending sync';
            // "Unread" analog for this inbox: the operator responded —
            // a lifecycle status beyond the automatic "new" receipt.
            const responded = !!it.status && it.status !== 'new';
            return (
              <Pressable
                key={it.id}
                onLongPress={() => onDelete(it)}
                style={({ pressed }) => [
                  styles.row,
                  responded && styles.rowUnread,
                  pressed && styles.rowPressed,
                ]}
              >
                <View style={styles.rowHeader}>
                  {responded && <View style={styles.unreadDot} />}
                  <Text style={styles.rowSev}>{SEV_LABEL[it.severity]}</Text>
                  <View style={{ flex: 1 }} />
                  <Text style={styles.rowWhen}>{relativeTime(it.created_at)}</Text>
                </View>
                <Text style={styles.rowScreen}>{it.screen}</Text>
                <Text style={styles.rowText}>{it.text}</Text>
                {it.status ? (
                  <Text style={[styles.statusLine, { color: STATUS_COLOR[it.status] }]}>
                    {STATUS_LABEL[it.status]}
                  </Text>
                ) : null}
                <View style={styles.syncRow}>
                  {it.synced && <Icon name="check" size={16} color={chalk.faint} />}
                  <Text style={[styles.syncText, syncStyle]} numberOfLines={2}>
                    {syncText}
                  </Text>
                </View>
              </Pressable>
            );
          })}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },

  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    gap: space.sm,
    borderBottomColor: ink.line,
    borderBottomWidth: 1,
  },
  title: { ...type.heading },
  sub:   { ...type.bodySm },
  subCount: { fontFamily: fonts.data, fontVariant: ['tabular-nums'], color: chalk.dim },
  retrySpinner: {
    height: 44,
    minWidth: 44,
    paddingHorizontal: space.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },

  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl },
  emptyTitle: { ...type.heading, marginBottom: space.sm },
  emptySub:   { ...type.bodySm, textAlign: 'center' },

  // NotificationRow pattern (docs/design/components.md → Feedback & status):
  // hairline-separated rows on ink-0; a row with an operator response gets
  // the ink-2 fill + ice 6px square dot. Pressed = ink-3 fill, color only.
  row: {
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomColor: ink.line,
    borderBottomWidth: 1,
  },
  rowUnread:  { backgroundColor: ink.ink2 },
  rowPressed: { backgroundColor: ink.ink3 },
  unreadDot: {
    width: 6,
    height: 6,
    backgroundColor: flare.base, // square — no radius (NotificationRow spec; flare = informational accent)
  },
  rowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginBottom: space.xs,
  },
  rowSev:    { ...type.label, color: chalk.base },
  rowWhen:   { ...type.data, color: chalk.faint },
  rowScreen: { ...type.label, marginBottom: space.xs },
  rowText:   { ...type.body },
  // Operator-set lifecycle status — the "what happened to my note" line.
  // Sits above the sync badge; color carries the state (see STATUS_COLOR).
  statusLine: {
    ...type.label,
    marginTop: space.sm,
  },
  // Per-row sync state. Three visual states; colors are chosen so a
  // glance at the inbox tells the tester at-a-glance which notes already
  // made it to the backend.
  syncRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    marginTop: space.sm,
  },
  syncText: { ...type.bodySm },
  syncSynced:  { color: chalk.faint },
  syncPending: { color: semantic.warn },
  syncFailed:  { color: semantic.neg },
});
