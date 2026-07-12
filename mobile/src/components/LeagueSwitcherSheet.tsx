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
import { ink, chalk, ice, semantic, space, radii, type, shadowSheet, scrim } from '../theme/chalkline';
import { Badge, Button, Icon } from './chalkline';
import { useSession } from '../state/useSession';

interface Props {
  visible: boolean;
  onClose: () => void;
  /** Fired AFTER the league swap completes successfully. The screen using
   *  this sheet typically resets local state (e.g. trade deck) here. */
  onSwitched?: (leagueId: string) => void;
}

// Bottom-sheet picker for the user's leagues (Chalkline sheet construction:
// ink-2 surface, hairline border, sheet shadow, line-strong grabber, solid
// scrim; leagues render as hairline-separated LeagueRows). Tapping a row
// triggers useSession.switchLeague which re-runs sessionInit on the backend;
// while that's in flight the row shows a spinner and the rest of the list is
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
        <View style={styles.grabber} />
        <Text style={type.heading}>Switch league</Text>
        <Text style={[type.bodySm, styles.sub]}>
          Picking a league reloads your team rosters and trade pool.
        </Text>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <ScrollView style={styles.scroll} keyboardShouldPersistTaps="always">
          {leagues.length === 0 ? (
            <View style={styles.emptyWrap}>
              <Text style={[type.bodySm, styles.emptyText]}>
                No leagues cached. Pull-to-refresh on the league picker.
              </Text>
            </View>
          ) : (
            leagues.map((lg, idx) => {
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
                    idx === leagues.length - 1 && styles.rowLast,
                    dim && styles.rowDim,
                    pressed && !dim && styles.rowPressed,
                  ]}
                >
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <View style={styles.rowNameRow}>
                      <Text style={[type.title, styles.rowNameText]} numberOfLines={1}>
                        {lg.name}
                      </Text>
                      {/* ESPN read-only import (flag `espn.link`) — text
                          badge only, no logos. */}
                      {lg.platform === 'espn' ? <Badge label="ESPN" /> : null}
                    </View>
                    <Text style={[type.bodySm, styles.rowMeta]}>
                      {(lg.total_rosters as number | undefined) || 12} teams
                    </Text>
                  </View>
                  {isBusy ? (
                    <ActivityIndicator color={chalk.dim} />
                  ) : isActive ? (
                    <Icon name="check" size={20} color={ice.base} />
                  ) : (
                    <Icon name="chevron-right" size={20} color={chalk.dim} />
                  )}
                </Pressable>
              );
            })
          )}
        </ScrollView>

        <Button
          label="Cancel"
          variant="ghost"
          onPress={() => (busyId ? null : onClose())}
          disabled={busyId !== null}
          style={styles.cancel}
        />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  sub:   { marginBottom: space.sm },
  error: { ...type.bodySm, color: semantic.neg, marginBottom: space.xs },
  scroll: { maxHeight: 460 },
  emptyWrap: { paddingVertical: space.xl, alignItems: 'center' },
  emptyText: { textAlign: 'center' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    paddingHorizontal: space.xs,
    minHeight: 44,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  rowLast: { borderBottomWidth: 0 },
  rowPressed: { backgroundColor: ink.ink3 },
  rowDim: { opacity: 0.45 },
  rowMeta: { marginTop: 2 },
  rowNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  rowNameText: { flexShrink: 1 },
  cancel: { marginTop: space.md },
});
