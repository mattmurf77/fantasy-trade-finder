import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Modal,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { useSession } from '../state/useSession';

interface Props {
  visible: boolean;
  onClose: () => void;
  /** Fired AFTER the league swap completes successfully. The screen using
   *  this sheet typically resets local state (e.g. trade deck) here. */
  onSwitched?: (leagueId: string) => void;
}

// Bottom-sheet picker for the user's leagues. Tapping a row triggers
// useSession.switchLeague which re-runs sessionInit on the backend; while
// that's in flight the row shows a spinner and the rest of the list is
// disabled (sessionInit can take several seconds on Render free tier and
// we don't want concurrent switches racing).
export default function LeagueSwitcherSheet({ visible, onClose, onSwitched }: Props) {
  const leagues       = useSession((s) => s.leagues);
  const activeLeague  = useSession((s) => s.league);
  const switchLeague  = useSession((s) => s.switchLeague);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error,  setError]  = useState<string | null>(null);

  async function handlePick(lgId: string, lgName: string) {
    if (busyId) return;
    if (lgId === activeLeague?.league_id) {
      onClose();
      return;
    }
    setBusyId(lgId);
    setError(null);
    try {
      await switchLeague({ league_id: lgId, league_name: lgName });
      onSwitched?.(lgId);
      onClose();
    } catch (e: any) {
      setError(e?.message || 'Failed to switch league');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={() => (busyId ? null : onClose())}
    >
      <Pressable
        style={styles.backdrop}
        onPress={() => (busyId ? null : onClose())}
      />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <Text style={styles.title}>Switch league</Text>
        <Text style={styles.sub}>
          Picking a league reloads your team rosters and trade pool.
        </Text>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <ScrollView style={styles.scroll} keyboardShouldPersistTaps="always">
          {leagues.length === 0 ? (
            <View style={styles.emptyWrap}>
              <Text style={styles.emptyText}>
                No leagues cached. Pull-to-refresh on the league picker.
              </Text>
            </View>
          ) : (
            leagues.map((lg) => {
              const isActive = lg.league_id === activeLeague?.league_id;
              const isBusy   = busyId === lg.league_id;
              const dim      = busyId !== null && !isBusy;
              return (
                <Pressable
                  key={lg.league_id}
                  onPress={() => handlePick(lg.league_id, lg.name)}
                  disabled={busyId !== null}
                  style={({ pressed }) => [
                    styles.row,
                    isActive && styles.rowActive,
                    dim && styles.rowDim,
                    pressed && !dim && { opacity: 0.7 },
                  ]}
                >
                  <View style={styles.rowAvatar}>
                    <Text style={styles.rowAvatarEmoji}>🏈</Text>
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={styles.rowName} numberOfLines={1}>{lg.name}</Text>
                    <Text style={styles.rowMeta}>
                      {(lg.total_rosters as number | undefined) || 12} teams
                    </Text>
                  </View>
                  {isBusy ? (
                    <ActivityIndicator color={colors.accent} />
                  ) : isActive ? (
                    <Text style={styles.check}>✓</Text>
                  ) : (
                    <Text style={styles.chevron}>›</Text>
                  )}
                </Pressable>
              );
            })
          )}
        </ScrollView>

        <Pressable
          onPress={() => (busyId ? null : onClose())}
          disabled={busyId !== null}
          style={({ pressed }) => [
            styles.cancel,
            (pressed || busyId) && { opacity: 0.6 },
          ]}
        >
          <Text style={styles.cancelText}>Cancel</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.55)' },
  sheet: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    maxHeight: '85%',
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
  title: { color: colors.text, fontSize: fontSize.xl,  fontWeight: '800' },
  sub:   { color: colors.muted, fontSize: fontSize.sm,  marginBottom: spacing.sm },
  error: { color: colors.red,  fontSize: fontSize.xs, marginBottom: spacing.xs },
  scroll: { maxHeight: 460 },
  emptyWrap: { paddingVertical: spacing.xl, alignItems: 'center' },
  emptyText: { color: colors.muted, fontSize: fontSize.sm, textAlign: 'center' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    marginBottom: spacing.sm,
  },
  rowActive: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.08)',
  },
  rowDim: { opacity: 0.45 },
  rowAvatar: {
    width: 40, height: 40, borderRadius: 10,
    backgroundColor: 'rgba(79,124,255,0.14)',
    alignItems: 'center', justifyContent: 'center',
  },
  rowAvatarEmoji: { fontSize: 20 },
  rowName:  { color: colors.text,  fontSize: fontSize.base, fontWeight: '700' },
  rowMeta:  { color: colors.muted, fontSize: fontSize.xs,   marginTop: 2 },
  check:    { color: colors.accent, fontSize: 22, fontWeight: '800' },
  chevron:  { color: colors.muted,  fontSize: 22 },
  cancel:   { marginTop: spacing.md, padding: spacing.md, alignItems: 'center' },
  cancelText: { color: colors.muted, fontWeight: '700', fontSize: fontSize.sm },
});
