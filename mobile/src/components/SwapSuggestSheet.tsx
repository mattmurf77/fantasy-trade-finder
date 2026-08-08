import React from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import MemberEnteredMarker, {
  MEMBER_ENTERED_COPY,
  isMemberEntered,
  openPickCorrection,
  usePicksTradeable,
} from './MemberEnteredMarker';
import PositionChip from './PositionChip';
import { Button, TickLabel } from './chalkline';
import { useReducedMotionSafe } from '../hooks/useReducedMotionSafe';
import type { CalcEvener } from '../api/calc';
import type { Player } from '../shared/types';
import {
  chalk,
  ice,
  ink,
  radii,
  scrim,
  shadowSheet,
  space,
  type,
} from '../theme/chalkline';

// Deck swap-suggestions sheet (2026-07-27 player-changer — operator follow-up
// to the calculator eveners: counter-suggestions "served as the player
// changer" on find-a-trade cards). The host evaluates the top card's trade
// MINUS one asset via POST /api/trade/evaluate and passes the returned
// `eveners` here as one-tap replacements for that asset: players + owned
// picks from the SAME side's roster, sized so the swapped trade stays close
// to even, plus at most one 2-piece package row. Picking one swaps it in and
// re-prices the card through the existing edit/reprice machinery.
//
// Honest states: a spinner while the evaluate round-trip runs, a plain
// explanation when it fails, and a no-candidates empty state — never padded
// with far-off values. "Browse full roster" hands off to the classic #86
// SwapPlayerSheet for the same asset in every state.
//
// Chalkline bottom-sheet construction mirrors PlayerContextMenu; slide falls
// back to fade under Reduce Motion. Ice stays on the action affordance.

interface Props {
  visible: boolean;
  /** The asset being replaced (null while closed). */
  replacing: Player | null;
  suggestions: CalcEvener[];
  loading: boolean;
  error: boolean;
  onPick: (evener: CalcEvener) => void;
  /** Escape hatch: open the classic full-roster swap sheet for this asset. */
  onBrowseRoster: () => void;
  /** W3 M-C (D17) — the league whose assignment grid holds any asserted
   *  pick offered here. Without it the marker has no correction target. */
  leagueId?: string | null;
  onClose: () => void;
}

export default function SwapSuggestSheet({
  visible,
  replacing,
  suggestions,
  loading,
  error,
  onPick,
  onBrowseRoster,
  leagueId,
  onClose,
}: Props) {
  const reduceMotion = useReducedMotionSafe();
  // See PlayerPickerModal: the option row is an accessible container, so the
  // disclosure + correction ride the ROW's a11y contract as well as the
  // marker's own. Sighted and VoiceOver users get the same two things.
  const picksTradeable = usePicksTradeable();
  return (
    <Modal
      visible={visible}
      transparent
      animationType={reduceMotion ? 'fade' : 'slide'}
      onRequestClose={onClose}
    >
      <Pressable
        style={styles.backdrop}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={styles.sheet} testID="trade-card.swap-suggest-sheet">
        <SafeAreaView edges={['bottom']}>
          <View style={styles.grabber} />
          <View style={styles.header}>
            <View style={styles.headerText}>
              <Text style={type.heading} numberOfLines={1} accessibilityRole="header">
                Swap {replacing?.name ?? 'asset'}
              </Text>
              <Text style={type.bodySm}>
                Replacements sized to keep this trade balanced
              </Text>
            </View>
            <Button label="Cancel" variant="ghost" onPress={onClose} />
          </View>

          {loading ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={ice.base} />
              <Text style={type.bodySm}>Pricing the trade without them…</Text>
            </View>
          ) : error ? (
            <Text style={styles.empty}>
              Couldn't price replacements right now — try again, or browse the
              full roster below.
            </Text>
          ) : suggestions.length === 0 ? (
            <Text style={styles.empty} testID="trade-card.swap-suggest-empty">
              No close-value replacements for this swap — swapping here would
              tip the trade. Browse the full roster below instead.
            </Text>
          ) : (
            <ScrollView style={styles.list}>
              <TickLabel>SUGGESTED REPLACEMENTS</TickLabel>
              {suggestions.map((e) => {
                const pickId = e.pick_id ?? e.id;
                const marked =
                  picksTradeable && isMemberEntered(e.source) && !!pickId && !!leagueId;
                return (
                <Pressable
                  key={e.id}
                  testID={`trade-card.swap-option.${e.id}`}
                  onPress={() => onPick(e)}
                  accessibilityRole="button"
                  accessibilityLabel={`Swap in ${e.name}${
                    replacing ? ` for ${replacing.name}` : ''
                  }${marked ? `. ${MEMBER_ENTERED_COPY}` : ''}`}
                  accessibilityActions={
                    marked ? [{ name: 'correct', label: 'Correct this pick' }] : undefined
                  }
                  onAccessibilityAction={
                    marked
                      ? (ev) => {
                          if (ev.nativeEvent.actionName === 'correct') {
                            openPickCorrection(leagueId as string, pickId, e.season);
                          }
                        }
                      : undefined
                  }
                  style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
                >
                  <PositionChip position={e.position} size="sm" />
                  <View style={styles.rowBody}>
                    <Text style={styles.rowName} numberOfLines={1}>
                      {e.name}
                    </Text>
                    {/* D17 — priced surface 2 of 5: the swap-suggestions
                        sheet. UNCONDITIONAL; the marker self-gates. */}
                    <MemberEnteredMarker
                      source={e.source}
                      pickId={pickId}
                      season={e.season}
                      leagueId={leagueId}
                      testID={`trade-card.swap-option.member-entered.${e.id}`}
                    />
                  </View>
                  <Text style={[type.data, styles.rowValue]}>
                    {Math.round(e.value).toLocaleString()}
                  </Text>
                </Pressable>
                );
              })}
            </ScrollView>
          )}

          <Button
            variant="secondary"
            label="Browse full roster"
            onPress={onBrowseRoster}
            style={styles.browseBtn}
          />
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '75%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
    marginBottom: space.sm,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: space.md,
    paddingBottom: space.sm,
  },
  headerText: { flex: 1, gap: space.xs },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.xl,
  },
  empty: {
    ...type.bodySm,
    paddingVertical: space.lg,
  },
  list: { marginBottom: space.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 48,
    paddingVertical: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  // The name column became a stack when the provenance marker joined it;
  // with no marker it renders exactly as the single Text did.
  rowBody: { flex: 1, gap: space.xs },
  rowName: { ...type.title, color: chalk.base },
  rowValue: { minWidth: 56, textAlign: 'right' },
  browseBtn: { marginTop: space.sm },
});
